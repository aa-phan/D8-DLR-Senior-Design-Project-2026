"""
Tests for backend/ercot_data_retriever.py (v1.3 Phase 2 Plan 02-03, D-02).

Covers the additive extension that makes `pull_ercot_data` usable in
process: a real return value, an explicit per-corridor zone selection, a
per-calendar-year download loop that works around the installed
`gridstatus` client's single-year-only post-settlements load download
(02-RESEARCH.md Pitfall 2), and the fallback to the total ERCOT column
when no zone matches. Follows this suite's established conventions:
module-level imports, plain asserts, no classes, `tmp_path` for any
write, and a monkeypatched fake `gridstatus.Ercot` client so no test ever
makes a network request.
"""

import numpy as np
import pandas as pd

import config
import ercot_data_retriever as edr


# The real ERCOT weather-zone column names (02-RESEARCH.md, verified this
# session from the installed gridstatus source), plus the time column the
# installed client's post-settlements download normalizes to.
_ZONE_COLUMNS = (
    "Coast", "East", "Far West", "North", "North Central",
    "South", "South Central", "West", "ERCOT",
)


def _zone_frame(year: int, n: int = 5) -> pd.DataFrame:
    """
    A deterministic fake post-settlements load frame for one calendar
    year: `n` hourly rows starting at `{year}-01-01T00:00:00Z`, one
    distinct numeric series per real ERCOT zone column, so a test can
    assert exactly which columns a zone selection summed.
    """
    idx = pd.date_range(f"{year}-01-01", periods=n, freq="h", tz="UTC")
    data = {"Interval Start": idx}
    for i, col in enumerate(_ZONE_COLUMNS):
        data[col] = np.arange(n, dtype=float) + (i + 1) * 100.0
    return pd.DataFrame(data)


def _make_fake_ercot(monkeypatch, frame_for_year=None):
    """
    Monkeypatches `ercot_data_retriever.gridstatus.Ercot` with a fake
    class whose `get_hourly_load_post_settlements(start, end)` records
    every `(start, end)` call it received (as strings) and returns
    `frame_for_year(pd.Timestamp(start).year)` -- defaulting to
    `_zone_frame` when no factory is supplied. Returns the shared `calls`
    list so a test can assert exactly how many downloads happened and for
    which years.
    """
    if frame_for_year is None:
        frame_for_year = _zone_frame

    calls = []

    class _FakeErcot:
        def __init__(self):
            pass

        def get_hourly_load_post_settlements(self, start, end=None):
            calls.append((str(start), str(end)))
            year = pd.Timestamp(start).year
            return frame_for_year(year)

    monkeypatch.setattr(edr.gridstatus, "Ercot", _FakeErcot)
    return calls


# ──────────────────────────────────────────────────────────────────────────────
# Additive return value, default call reproduces today's behavior exactly
# ──────────────────────────────────────────────────────────────────────────────

def test_default_call_returns_frame_with_datetime_utc_and_west_column(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = _make_fake_ercot(monkeypatch)

    result = edr.pull_ercot_data("2025-01-01", "2025-01-02")

    assert result is not None
    assert list(result.columns) == ["datetime_utc", "ercot_west_load_mw"]
    assert len(calls) == 1


def test_default_call_still_writes_the_same_csv_path(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _make_fake_ercot(monkeypatch)

    edr.pull_ercot_data("2025-01-01", "2025-01-02")

    expected_path = tmp_path / "outputs" / "ercot_data" / "ercot_west_load_2025-01-01_2025-01-02.csv"
    assert expected_path.exists()


def test_save_false_writes_no_file(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _make_fake_ercot(monkeypatch)

    result = edr.pull_ercot_data("2025-01-01", "2025-01-02", save=False)

    assert result is not None
    assert not (tmp_path / "outputs").exists()


# ──────────────────────────────────────────────────────────────────────────────
# Explicit zone selection
# ──────────────────────────────────────────────────────────────────────────────

def test_zone_substrings_south_selects_south_and_south_central_only(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _make_fake_ercot(monkeypatch)

    result = edr.pull_ercot_data(
        "2025-01-01", "2025-01-02", zone_substrings=("SOUTH",), save=False,
    )

    assert "ercot_south_load_mw" in result.columns
    assert "ercot_west_load_mw" not in result.columns

    frame = _zone_frame(2025)
    expected = frame["South"] + frame["South Central"]
    # Both series are indexed identically (same source timestamps, mask
    # keeps every row for this window) so a direct positional compare is
    # valid.
    assert np.allclose(result["ercot_south_load_mw"].to_numpy(), expected.to_numpy())
    # West/Far West must never leak into a south-zone selection's sum.
    assert not np.allclose(
        result["ercot_south_load_mw"].to_numpy(),
        (frame["West"] + frame["Far West"]).to_numpy(),
    )


def test_zone_substrings_west_default_matches_west_and_far_west(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _make_fake_ercot(monkeypatch)

    result = edr.pull_ercot_data("2025-01-01", "2025-01-02", save=False)

    frame = _zone_frame(2025)
    expected = frame["West"] + frame["Far West"]
    assert np.allclose(result["ercot_west_load_mw"].to_numpy(), expected.to_numpy())


def test_no_matching_zone_falls_back_to_total_ercot_column(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    _make_fake_ercot(monkeypatch)

    result = edr.pull_ercot_data(
        "2025-01-01", "2025-01-02", zone_substrings=("NONEXISTENT_ZONE",), save=False,
    )

    frame = _zone_frame(2025)
    assert np.allclose(
        result["ercot_nonexistent_zone_load_mw"].to_numpy(), frame["ERCOT"].to_numpy(),
    )
    captured = capsys.readouterr()
    assert "Could not find columns matching" in captured.out


# ──────────────────────────────────────────────────────────────────────────────
# Per-calendar-year download loop (02-RESEARCH.md Pitfall 2)
# ──────────────────────────────────────────────────────────────────────────────

def test_span_inside_one_year_issues_exactly_one_download_call(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = _make_fake_ercot(monkeypatch)

    edr.pull_ercot_data("2025-02-01", "2025-06-01", save=False)

    assert len(calls) == 1
    assert pd.Timestamp(calls[0][0]).year == 2025


def test_span_crossing_year_boundary_issues_one_call_per_spanned_year(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = _make_fake_ercot(monkeypatch)

    result = edr.pull_ercot_data("2024-01-01", "2025-01-01", save=False)

    called_years = sorted(pd.Timestamp(c[0]).year for c in calls)
    assert called_years == [2024, 2025]

    seen_years = sorted(set(pd.to_datetime(result["datetime_utc"]).dt.year))
    assert seen_years == [2024, 2025]


def test_concatenated_frame_is_sorted_by_time_with_duplicates_dropped(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    # Both requested years return the IDENTICAL frame (same timestamps) --
    # a deliberately pathological fake to prove the dedup step actually
    # collapses duplicate timestamps rather than merely concatenating.
    fixed_frame = _zone_frame(2025)
    _make_fake_ercot(monkeypatch, frame_for_year=lambda year: fixed_frame.copy())

    result = edr.pull_ercot_data("2025-01-01", "2026-01-01", save=False)

    assert result["datetime_utc"].is_monotonic_increasing
    assert not result["datetime_utc"].duplicated().any()


# ──────────────────────────────────────────────────────────────────────────────
# config coverage -- every corridor has an explicit zone selection
# ──────────────────────────────────────────────────────────────────────────────

def test_every_corridor_has_an_explicit_zone_substring_selection():
    assert sorted(config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CORRIDOR) == sorted(
        config.CORRIDOR_ENDPOINTS
    )


def test_the_two_corridors_zone_selections_differ():
    selections = [
        tuple(v) for v in config.ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CORRIDOR.values()
    ]
    assert len(set(selections)) == len(selections)


# ──────────────────────────────────────────────────────────────────────────────
# Frame attributes -- caller does not have to guess the resolved column
# name or the real zone columns actually matched (Plan 02-03 Task 2 reads
# these in anomaly_training.characterize_load)
# ──────────────────────────────────────────────────────────────────────────────

def test_frame_attrs_expose_load_column_and_matched_zones(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _make_fake_ercot(monkeypatch)

    result = edr.pull_ercot_data(
        "2025-01-01", "2025-01-02", zone_substrings=("SOUTH",), save=False,
    )

    assert result.attrs["load_column"] == "ercot_south_load_mw"
    assert sorted(result.attrs["zone_columns_matched"]) == ["South", "South Central"]


def test_frame_attrs_record_empty_matched_zones_on_fallback(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _make_fake_ercot(monkeypatch)

    result = edr.pull_ercot_data(
        "2025-01-01", "2025-01-02", zone_substrings=("NONEXISTENT_ZONE",), save=False,
    )

    assert result.attrs["zone_columns_matched"] == []


# Note: every test above monkeypatches `edr.gridstatus.Ercot` before calling
# `pull_ercot_data` -- none constructs a real client or issues a network
# request (this suite's own required convention, mirrored from
# `forecast_training_test.py`).
