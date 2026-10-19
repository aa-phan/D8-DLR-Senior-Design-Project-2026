"""
Tests for C6 (Grid Load Integration / ERCOT) — backend/ercot_dlr_merger.py.

Covers the three acceptance criteria flagged as "currently unverified" in
docs/data-science/specs/C6-grid-load-integration.md:

1. Worst-case-within-hour survives resampling (process_dlr_to_hourly uses
   .min() for dlr_amps, not .mean()/first/last).
2. amps_to_mw matches independently hand-calculated values.
3. The inner join in ercot_dlr_merger.py's __main__ block behaves as
   documented: it keeps only overlapping datetime_utc timestamps, with no
   row loss/duplication among the overlap.

Also covers DS-F5 (D-04, D-05): process_dlr_to_hourly's per-location static
rating resolution via the new `city` parameter.
"""
import math
import sys
import warnings
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ercot_dlr_merger import amps_to_mw, process_dlr_to_hourly
import config
from ercot_dlr_merger import LINE_VOLTAGE_KV, POWER_FACTOR


# ──────────────────────────────────────────────────────────────────────────
# 1. Worst-case-within-hour survives resampling
# ──────────────────────────────────────────────────────────────────────────
def test_hourly_resample_uses_min_not_mean(tmp_path):
    # Build 5-minute samples spanning one full hour (12 samples: :00 .. :55).
    # dlr_amps is a steady 800 A except for a 15-minute dip (three 5-min
    # samples) down to 250 A, simulating "wind died for 15 minutes".
    timestamps = pd.date_range("2025-07-01T00:00:00Z", periods=12, freq="5min")
    amps = [800.0] * 12
    dip_idxs = [4, 5, 6]  # 00:20, 00:25, 00:30
    for i in dip_idxs:
        amps[i] = 250.0

    df = pd.DataFrame(
        {
            "datetime_utc": timestamps,
            "dlr_amps": amps,
            "wind_speed": [5.0] * 12,
            "air_temp": [30.0] * 12,
        }
    )

    csv_path = tmp_path / "dlr_synthetic.csv"
    df.to_csv(csv_path, index=False)

    hourly = process_dlr_to_hourly(str(csv_path))

    assert len(hourly) == 1
    expected_min = min(amps)
    assert expected_min == 250.0
    assert hourly.loc[0, "dlr_amps"] == pytest.approx(expected_min)

    # Sanity: mean of the samples is well above the min, so this really is
    # testing .min() behavior and not something that happens to coincide.
    mean_amps = sum(amps) / len(amps)
    assert mean_amps > expected_min
    assert hourly.loc[0, "dlr_amps"] != pytest.approx(mean_amps)

    # And it isn't just picking the first or last sample either.
    assert hourly.loc[0, "dlr_amps"] != pytest.approx(amps[0])
    assert hourly.loc[0, "dlr_amps"] != pytest.approx(amps[-1])


# ──────────────────────────────────────────────────────────────────────────
# 2. amps_to_mw correctness against independently hand-calculated values
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "amps,voltage_kv,pf,expected_mw",
    [
        # P = sqrt(3) * V(kV) * I(A) * pf / 1000
        # sqrt(3) ~= 1.7320508075688772
        (1000.0, 100.0, 1.0, 173.20508075688772),
        (900.0, 345.0, 0.95, 510.91168696262963),
        (500.0, 138.0, 0.9, 107.56035515002728),
    ],
)
def test_amps_to_mw_matches_hand_calculation(amps, voltage_kv, pf, expected_mw):
    result = amps_to_mw(amps, voltage_kv, pf)
    assert result == pytest.approx(expected_mw, rel=1e-9)


def test_amps_to_mw_simple_round_number_sanity_check():
    # Easy-to-verify-by-hand case: 1000 A at 100 kV, pf=1.0.
    # sqrt(3) ~= 1.732, so P ~= 1.732 * 100 * 1000 / 1000 = 173.2 MW.
    result = amps_to_mw(1000.0, 100.0, 1.0)
    assert result == pytest.approx(173.2, abs=0.01)


# ──────────────────────────────────────────────────────────────────────────
# 3. Inner join: no row loss/duplication among overlapping timestamps
# ──────────────────────────────────────────────────────────────────────────
def test_inner_join_keeps_only_overlap_no_duplicates():
    # DLR hours: 00:00, 01:00, 02:00, 03:00 (mimics process_dlr_to_hourly output)
    dlr_hours = pd.to_datetime(
        [
            "2025-07-01T00:00:00Z",
            "2025-07-01T01:00:00Z",
            "2025-07-01T02:00:00Z",
            "2025-07-01T03:00:00Z",
        ]
    )
    dlr_df = pd.DataFrame(
        {
            "datetime_utc": dlr_hours,
            "dlr_capacity_mw": [500.0, 505.0, 510.0, 495.0],
        }
    )

    # ERCOT hours: 01:00, 02:00, 03:00, 04:00 (mimics load_ercot_west_data output)
    # Overlap with dlr_hours is exactly {01:00, 02:00, 03:00} -> 3 rows expected.
    ercot_hours = pd.to_datetime(
        [
            "2025-07-01T01:00:00Z",
            "2025-07-01T02:00:00Z",
            "2025-07-01T03:00:00Z",
            "2025-07-01T04:00:00Z",
        ]
    )
    ercot_df = pd.DataFrame(
        {
            "datetime_utc": ercot_hours,
            "ercot_west_load_mw": [1000.0, 1010.0, 1020.0, 1030.0],
        }
    )

    merged = pd.merge(dlr_df, ercot_df, on="datetime_utc", how="inner")

    expected_overlap = sorted(set(dlr_hours) & set(ercot_hours))
    assert len(merged) == len(expected_overlap) == 3
    assert list(merged["datetime_utc"].sort_values()) == expected_overlap
    # No duplicate timestamps introduced by the merge.
    assert merged["datetime_utc"].is_unique
    # The 00:00 (DLR-only) and 04:00 (ERCOT-only) hours must be dropped.
    assert pd.Timestamp("2025-07-01T00:00:00Z") not in set(merged["datetime_utc"])
    assert pd.Timestamp("2025-07-01T04:00:00Z") not in set(merged["datetime_utc"])


# ──────────────────────────────────────────────────────────────────────────
# 4. DS-F5 (D-04, D-05): per-location static rating resolution
# ──────────────────────────────────────────────────────────────────────────
@pytest.fixture
def dlr_csv(tmp_path):
    """Writes a small synthetic 5-minute DLR CSV and returns its path."""
    timestamps = pd.date_range("2025-07-01T00:00:00Z", periods=12, freq="5min")
    df = pd.DataFrame(
        {
            "datetime_utc": timestamps,
            "dlr_amps": [800.0] * 12,
            "wind_speed": [5.0] * 12,
            "air_temp": [30.0] * 12,
        }
    )
    csv_path = tmp_path / "dlr_synthetic_city.csv"
    df.to_csv(csv_path, index=False)
    return str(csv_path)


def test_city_austin_uses_per_location_static_rating(dlr_csv):
    hourly = process_dlr_to_hourly(dlr_csv, city="AUSTIN")
    expected_austin = amps_to_mw(config.STATIC_RATINGS["AUSTIN"], LINE_VOLTAGE_KV, POWER_FACTOR)
    expected_default = amps_to_mw(config.DEFAULT_STATIC_RATING, LINE_VOLTAGE_KV, POWER_FACTOR)
    assert hourly["static_capacity_mw"].to_numpy() == pytest.approx(expected_austin)
    # This is the assertion that would have caught the audit finding: the
    # resolved value must NOT be the unconditional default-rating read.
    assert hourly["static_capacity_mw"].to_numpy() != pytest.approx(expected_default)


def test_omitted_city_preserves_default_static_rating(dlr_csv):
    hourly = process_dlr_to_hourly(dlr_csv)
    expected_default = amps_to_mw(config.DEFAULT_STATIC_RATING, LINE_VOLTAGE_KV, POWER_FACTOR)
    assert hourly["static_capacity_mw"].to_numpy() == pytest.approx(expected_default)


def test_explicit_none_city_matches_omitted_city(dlr_csv):
    hourly_omitted = process_dlr_to_hourly(dlr_csv)
    hourly_none = process_dlr_to_hourly(dlr_csv, city=None)
    assert (hourly_omitted["static_capacity_mw"] == hourly_none["static_capacity_mw"]).all()


def test_unknown_city_falls_back_silently(dlr_csv):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        hourly = process_dlr_to_hourly(dlr_csv, city="NOT_A_CITY")
    expected_default = amps_to_mw(config.DEFAULT_STATIC_RATING, LINE_VOLTAGE_KV, POWER_FACTOR)
    assert hourly["static_capacity_mw"].to_numpy() == pytest.approx(expected_default)


@pytest.mark.parametrize("city,amps", sorted(config.STATIC_RATINGS.items()))
def test_every_configured_city_resolves_its_own_rating(dlr_csv, city, amps):
    hourly = process_dlr_to_hourly(dlr_csv, city=city)
    expected = amps_to_mw(amps, LINE_VOLTAGE_KV, POWER_FACTOR)
    assert hourly["static_capacity_mw"].to_numpy() == pytest.approx(expected)


def test_default_static_rating_is_below_every_configured_city():
    assert min(config.STATIC_RATINGS.values()) > config.DEFAULT_STATIC_RATING


def test_city_argument_changes_only_the_static_column(dlr_csv):
    hourly_austin = process_dlr_to_hourly(dlr_csv, city="AUSTIN")
    hourly_default = process_dlr_to_hourly(dlr_csv)

    for col in ("dlr_amps", "dlr_capacity_mw", "wind_speed", "air_temp"):
        assert hourly_austin[col].to_numpy() == pytest.approx(hourly_default[col].to_numpy())

    assert hourly_austin["static_capacity_mw"].to_numpy() != pytest.approx(hourly_default["static_capacity_mw"].to_numpy())
