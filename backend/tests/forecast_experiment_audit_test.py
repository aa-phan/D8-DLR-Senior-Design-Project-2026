"""
Tests for backend/forecast_experiment_audit.py (Phase 4, Plan 04-01).

Task 1's tests make NO network call and need NO fetch monkeypatching at all
-- every function they exercise is a pure transform over in-memory frames.
The one Task 1 test that touches disk
(`test_truth_provenance_finding_...disclosure`) writes to a pytest
`tmp_path` file and passes its path directly to `truth_provenance_finding`,
so the real `docs/data-science/decisions/forecast_correction_experiment.md`
is never read or written by this test.

Task 2's `build_basis_manifest` tests monkeypatch
`forecast_experiment_audit.forecast_experiment.corridor_anchored_pair_frame`,
`.anchored_pair_frame`, and `._resolve_window_end` -- on the AUDIT MODULE's
own reference to the harness module object, never by editing
`forecast_experiment.py` itself -- so these tests make no network call
either, and every manifest they write goes to a pytest `tmp_path`, never the
real `data/experiment/` cache.

Module-level plain-assert functions, no test classes, mirroring
`forecast_experiment_test.py`'s own convention.
"""

import json

import numpy as np
import pandas as pd
import pytest

import config
import corridor_discretization
import forecast_experiment_audit as fea


# ──────────────────────────────────────────────────────────────────────────
# AUDIT_BASES and the frozen-window pins
# ──────────────────────────────────────────────────────────────────────────

def test_audit_bases_has_exactly_three_names():
    assert sorted(fea.AUDIT_BASES) == ["ABLATION", "FRESH", "SYNTHETIC"]
    for description in fea.AUDIT_BASES.values():
        assert isinstance(description, str) and len(description) > 0


def test_frozen_window_pins_match_the_record():
    assert fea.FROZEN_WINDOW_START == "2024-01-20"
    assert fea.FROZEN_TEST_SPLIT_START == "2026-03-17"
    assert fea.FROZEN_WINDOW_END == "2026-09-29"


def test_unknown_basis_raises_naming_all_three():
    frame = pd.DataFrame({"datetime_utc": pd.to_datetime(["2025-01-01T00:00:00Z"])})
    with pytest.raises(ValueError) as exc_info:
        fea.assert_basis_excludes_frozen_test_rows(frame, basis="BOGUS")
    message = str(exc_info.value)
    for name in ("SYNTHETIC", "ABLATION", "FRESH"):
        assert name in message, message


# ──────────────────────────────────────────────────────────────────────────
# ABLATION basis
# ──────────────────────────────────────────────────────────────────────────

def test_ablation_accepts_frame_strictly_before_test_split_start():
    frame = pd.DataFrame({
        "datetime_utc": pd.to_datetime(["2025-06-01T00:00:00Z", "2025-06-01T06:00:00Z"]),
    })
    summary = fea.assert_basis_excludes_frozen_test_rows(frame, basis="ABLATION")
    assert summary["basis"] == "ABLATION"
    assert summary["rows"] == 2
    assert summary["first_timestamp"] is not None
    assert summary["last_timestamp"] is not None


def test_ablation_raises_on_frame_entirely_inside_frozen_window():
    frame = pd.DataFrame({"datetime_utc": pd.to_datetime(["2026-04-01T00:00:00Z"])})
    with pytest.raises(ValueError) as exc_info:
        fea.assert_basis_excludes_frozen_test_rows(frame, basis="ABLATION")
    assert "2026-04-01" in str(exc_info.value)


def test_ablation_raises_on_single_straddling_row_names_its_timestamp():
    # Straddles the boundary by exactly one row: the last row sits inside
    # the frozen test window, every earlier row does not.
    frame = pd.DataFrame({
        "datetime_utc": pd.to_datetime([
            "2026-03-16T18:00:00Z",  # strictly before FROZEN_TEST_SPLIT_START -- fine
            "2026-03-17T00:00:00Z",  # exactly the frozen test split start -- the straddling row
        ]),
    })
    with pytest.raises(ValueError) as exc_info:
        fea.assert_basis_excludes_frozen_test_rows(frame, basis="ABLATION")
    message = str(exc_info.value)
    assert "1 row(s)" in message, message
    assert "2026-03-17" in message, message


# ──────────────────────────────────────────────────────────────────────────
# FRESH basis
# ──────────────────────────────────────────────────────────────────────────

def test_fresh_accepts_frame_strictly_after_window_end():
    frame = pd.DataFrame({
        "datetime_utc": pd.to_datetime(["2026-09-30T00:00:00Z", "2026-10-01T00:00:00Z"]),
    })
    summary = fea.assert_basis_excludes_frozen_test_rows(frame, basis="FRESH")
    assert summary["basis"] == "FRESH"
    assert summary["rows"] == 2


def test_fresh_raises_on_pre_frozen_window_row():
    frame = pd.DataFrame({"datetime_utc": pd.to_datetime(["2025-01-01T00:00:00Z"])})
    with pytest.raises(ValueError):
        fea.assert_basis_excludes_frozen_test_rows(frame, basis="FRESH")


def test_fresh_and_ablation_bases_are_not_interchangeable():
    # A frame that is a legitimate ABLATION basis (strictly before the
    # frozen test split) must be rejected when mislabelled as FRESH.
    ablation_shaped = pd.DataFrame({"datetime_utc": pd.to_datetime(["2025-06-01T00:00:00Z"])})
    fea.assert_basis_excludes_frozen_test_rows(ablation_shaped, basis="ABLATION")
    with pytest.raises(ValueError):
        fea.assert_basis_excludes_frozen_test_rows(ablation_shaped, basis="FRESH")


# ──────────────────────────────────────────────────────────────────────────
# Empty frame -- a zero-row basis is reportable, never an error
# ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("basis", ["SYNTHETIC", "ABLATION", "FRESH"])
def test_empty_frame_returns_zero_row_summary_for_every_basis(basis):
    empty = pd.DataFrame({"datetime_utc": pd.to_datetime([])})
    summary = fea.assert_basis_excludes_frozen_test_rows(empty, basis=basis)
    assert summary == {
        "basis": basis,
        "rows": 0,
        "first_timestamp": None,
        "last_timestamp": None,
    }


# ──────────────────────────────────────────────────────────────────────────
# SYNTHETIC basis
# ──────────────────────────────────────────────────────────────────────────

def test_synthetic_returns_immediately_with_no_real_corridor_marker():
    # A SYNTHETIC frame carrying a timestamp INSIDE the frozen test window
    # is still accepted -- SYNTHETIC has no calendar relationship to the
    # frozen window by construction.
    frame = pd.DataFrame({"datetime_utc": pd.to_datetime(["2026-04-01T00:00:00Z"])})
    summary = fea.assert_basis_excludes_frozen_test_rows(frame, basis="SYNTHETIC")
    assert summary["basis"] == "SYNTHETIC"
    assert summary["rows"] == 1


def test_synthetic_raises_on_real_corridor_marker():
    real_corridor = next(iter(config.CORRIDOR_ENDPOINTS))
    frame = pd.DataFrame({
        "datetime_utc": pd.to_datetime(["2025-01-01T00:00:00Z"]),
        "corridor": [real_corridor],
    })
    with pytest.raises(ValueError) as exc_info:
        fea.assert_basis_excludes_frozen_test_rows(frame, basis="SYNTHETIC")
    assert real_corridor in str(exc_info.value)


def test_synthetic_raises_on_real_city_marker():
    real_city = next(iter(config.CITY_COORDINATES))
    frame = pd.DataFrame({
        "datetime_utc": pd.to_datetime(["2025-01-01T00:00:00Z"]),
        "city": [real_city],
    })
    with pytest.raises(ValueError):
        fea.assert_basis_excludes_frozen_test_rows(frame, basis="SYNTHETIC")


# ──────────────────────────────────────────────────────────────────────────
# rederive_frozen_split_boundaries -- window-end dependence
# ──────────────────────────────────────────────────────────────────────────

def _synthetic_hourly_frame(end: str) -> pd.DataFrame:
    idx = pd.date_range(fea.FROZEN_WINDOW_START, end, freq="6h", tz="UTC")
    return pd.DataFrame({"datetime_utc": idx})


def test_rederive_frozen_split_boundaries_returns_comparison_fields():
    result = fea.rederive_frozen_split_boundaries(_synthetic_hourly_frame(fea.FROZEN_WINDOW_END))
    for key in (
        "boundaries", "rederived_test_start", "pinned_test_start",
        "matches_pinned_test_start", "frame_min", "frame_max",
    ):
        assert key in result, sorted(result)
    assert result["pinned_test_start"] == fea.FROZEN_TEST_SPLIT_START
    assert isinstance(result["matches_pinned_test_start"], bool)


def test_rederive_frozen_split_boundaries_is_window_end_dependent():
    short = fea.rederive_frozen_split_boundaries(_synthetic_hourly_frame(fea.FROZEN_WINDOW_END))
    long = fea.rederive_frozen_split_boundaries(_synthetic_hourly_frame("2027-03-31"))
    assert pd.Timestamp(long["boundaries"].test_start) > pd.Timestamp(short["boundaries"].test_start)
    assert short["rederived_test_start"] != long["rederived_test_start"]


# ──────────────────────────────────────────────────────────────────────────
# truth_provenance_finding
# ──────────────────────────────────────────────────────────────────────────

def test_truth_provenance_finding_has_citations_and_structure():
    finding = fea.truth_provenance_finding()
    assert "backend/open_meteo_provider.py" in finding["truth_source_citation"]
    assert "backend/forecast_experiment.py" in finding["physics_path_citation"]
    assert "backend/forecast_experiment.py" in finding["truth_dlr_amps_computation_citation"]
    assert finding["frozen_record_states_limitation"] is False
    assert finding["frozen_record_quotation"] is None
    assert finding["severity"] == "high"
    assert len(finding["consequence"]) > 0


def test_truth_provenance_finding_scans_rather_than_hardcodes(tmp_path):
    # A frozen record WITHOUT a disclosure marker -> False, no quotation.
    no_disclosure = tmp_path / "no_disclosure.md"
    no_disclosure.write_text(
        "## Data provenance\n\nSome prose with no relevant marker.\n\n"
        "## Limitations\n\nMore prose, still no marker.\n\n## Verdict\n\nDone.\n"
    )
    finding = fea.truth_provenance_finding(frozen_record_path=str(no_disclosure))
    assert finding["frozen_record_states_limitation"] is False
    assert finding["frozen_record_quotation"] is None

    # A frozen record WITH a disclosure marker -> True, with the quoted line.
    with_disclosure = tmp_path / "with_disclosure.md"
    with_disclosure.write_text(
        "## Data provenance\n\nThe truth side is not sensor-measured and "
        "carries no observational validation.\n\n## Limitations\n\nNone.\n"
    )
    finding = fea.truth_provenance_finding(frozen_record_path=str(with_disclosure))
    assert finding["frozen_record_states_limitation"] is True
    assert finding["frozen_record_quotation"] is not None
    assert "sensor" in finding["frozen_record_quotation"].lower()


# ──────────────────────────────────────────────────────────────────────────
# build_basis_manifest (Task 2) -- network-free via monkeypatched assembly
# helpers on the audit module's own `forecast_experiment` reference
# ──────────────────────────────────────────────────────────────────────────

def _fake_corridor_frame(corridor, start, end, *, lead_hours):
    """A small, deterministic, already-exact-lead-filtered (6h cadence) synthetic corridor frame."""
    idx = pd.date_range(start, end, freq="6h", tz="UTC")
    return pd.DataFrame({"datetime_utc": idx})


def _fake_city_frame(city, start, end, *, lead_hours):
    """A small, deterministic, full-hourly-cadence synthetic per-city frame."""
    idx = pd.date_range(start, end, freq="h", tz="UTC")
    return pd.DataFrame({"datetime_utc": idx})


def _patch_harness_assembly(monkeypatch, *, resolved_end=None):
    monkeypatch.setattr(fea.forecast_experiment, "corridor_anchored_pair_frame", _fake_corridor_frame)
    monkeypatch.setattr(fea.forecast_experiment, "anchored_pair_frame", _fake_city_frame)
    if resolved_end is not None:
        monkeypatch.setattr(fea.forecast_experiment, "_resolve_window_end", lambda end: resolved_end)


def test_build_basis_manifest_refuses_unknown_corridor():
    with pytest.raises(ValueError) as exc_info:
        fea.build_basis_manifest(corridors=["NOT_A_REAL_CORRIDOR"])
    message = str(exc_info.value)
    for name in config.CORRIDOR_ENDPOINTS:
        assert name in message, message


def test_fresh_basis_zero_row_branch_carries_explicit_reason(monkeypatch):
    _patch_harness_assembly(monkeypatch, resolved_end=fea.FROZEN_WINDOW_END)
    resolved = fea.forecast_experiment._resolve_window_end(None)
    assert resolved == fea.FROZEN_WINDOW_END
    entry = fea._build_fresh_basis_entry(
        next(iter(config.CORRIDOR_ENDPOINTS)), lead_hours=24, resolved_window_end=resolved,
    )
    assert entry["rows"] == 0
    assert entry.get("reason"), "a zero-row FRESH basis must carry an explicit reason string"
    assert fea.FROZEN_WINDOW_END in entry["reason"]


def test_fresh_basis_nonzero_when_resolved_end_is_later(monkeypatch):
    later_end = "2027-01-15"
    _patch_harness_assembly(monkeypatch, resolved_end=later_end)
    entry = fea._build_fresh_basis_entry(
        next(iter(config.CORRIDOR_ENDPOINTS)), lead_hours=24, resolved_window_end=later_end,
    )
    assert entry["rows"] > 0
    assert entry["frozen_window_guard_passed"] is True


def test_build_basis_manifest_atomic_merge_preserves_prior_corridor(tmp_path, monkeypatch):
    _patch_harness_assembly(monkeypatch, resolved_end=fea.FROZEN_WINDOW_END)
    manifest_path = str(tmp_path / "audit_basis_manifest.json")
    corridor_a, corridor_b = sorted(config.CORRIDOR_ENDPOINTS)

    fea.build_basis_manifest(corridors=[corridor_a], manifest_path=manifest_path)
    first = json.load(open(manifest_path))
    assert corridor_a in first["corridors"]
    assert corridor_b not in first["corridors"]

    fea.build_basis_manifest(corridors=[corridor_b], manifest_path=manifest_path)
    second = json.load(open(manifest_path))
    assert corridor_a in second["corridors"], (
        "a second corridor's write must preserve the first corridor's entry"
    )
    assert corridor_b in second["corridors"]


def test_build_basis_manifest_roundtrips_with_documented_keys(tmp_path, monkeypatch):
    _patch_harness_assembly(monkeypatch, resolved_end=fea.FROZEN_WINDOW_END)
    manifest_path = str(tmp_path / "audit_basis_manifest.json")
    corridor = next(iter(config.CORRIDOR_ENDPOINTS))

    fea.build_basis_manifest(corridors=[corridor], manifest_path=manifest_path)
    loaded = json.load(open(manifest_path))

    for key in ("generated_at", "note", "resolved_window_end", "lead_hours", "corridors"):
        assert key in loaded, sorted(loaded)

    entry = loaded["corridors"][corridor]
    for key in ("ablation", "fresh", "cities"):
        assert key in entry, sorted(entry)

    for key in (
        "train_rows", "val_rows", "rederived_test_start",
        "matches_pinned_test_start", "frozen_window_guard_passed",
    ):
        assert key in entry["ablation"], sorted(entry["ablation"])
    assert entry["ablation"]["train_rows"] > 0
    assert entry["ablation"]["val_rows"] > 0

    assert "rows" in entry["fresh"]

    for city_entry in entry["cities"].values():
        for key in ("assembled_rows", "dropped_rows", "method", "hourly_span_expectation"):
            assert key in city_entry, sorted(city_entry)


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-02 Task 1: decision_time_availability_finding (D-01 bullet 2) and
# frame_time_reference_groups (D-01 bullet 3, first half). Both network-free.
# ──────────────────────────────────────────────────────────────────────────

def test_decision_time_availability_finding_has_required_fields():
    f = fea.decision_time_availability_finding()
    for key in (
        "compared_products", "compared_quantity", "success_condition",
        "supported_claim", "unsupported_claim", "differs_from_recorded_limitation",
        "reachable_fetch_functions", "citations",
    ):
        assert key in f, sorted(f)
    assert len(f["compared_products"]) == 2
    for product in f["compared_products"].values():
        assert "endpoint" in product and product["endpoint"]
    assert len(f["reachable_fetch_functions"]) >= 2


def test_decision_time_availability_finding_supported_and_unsupported_claims_distinct():
    f = fea.decision_time_availability_finding()
    for key in ("supported_claim", "unsupported_claim", "differs_from_recorded_limitation"):
        assert isinstance(f[key], str) and f[key].strip(), (key, f.get(key))
    assert f["supported_claim"].strip() != f["unsupported_claim"].strip()


def test_decision_time_availability_finding_citations_parse_and_cover_calibration_module():
    import re
    f = fea.decision_time_availability_finding()
    blob = repr(f)
    cites = re.findall(r"[A-Za-z_./-]+\.(?:py|md):\d+", blob)
    assert len(cites) >= 4, f"only {len(cites)} citation(s): {cites}"
    assert any("forecast_leadtime_calibration.py" in c for c in cites), cites
    sources = f.get("reachable_fetch_functions") or f.get("fetch_functions")
    assert sources and len(sources) >= 2, sources


def test_decision_time_availability_finding_distinguishes_from_recorded_limitation():
    f = fea.decision_time_availability_finding()
    limitation = f["differs_from_recorded_limitation"].lower()
    # The distinction must actually be argued, not merely asserted: it must
    # name both the existing coverage limitation and the new claim-type one.
    assert "coverage" in limitation or "reach" in limitation
    assert "claim-type" in limitation or "claim type" in limitation


_PER_CITY_FRAME_COLUMNS = [
    "datetime_utc", "anchor_datetime_utc", "fcst_anchor_datetime_utc", "hour_mod_remainder",
    "truth_air_temp", "truth_wind_speed", "truth_wind_direction", "truth_solar_radiation",
    "truth_relative_humidity", "truth_dlr_amps",
    "anchor_air_temp", "anchor_wind_speed", "anchor_wind_direction", "anchor_solar_radiation",
    "anchor_relative_humidity", "anchor_dlr_amps",
    "fcst_air_temp", "fcst_wind_speed", "fcst_wind_direction", "fcst_solar_radiation", "fcst_relative_humidity",
    "fcst_anchor_air_temp", "fcst_anchor_wind_speed", "fcst_anchor_wind_direction",
    "fcst_anchor_solar_radiation", "fcst_anchor_relative_humidity",
]


def _synthetic_per_city_frame():
    frame = pd.DataFrame({c: [0.0] for c in _PER_CITY_FRAME_COLUMNS})
    frame["datetime_utc"] = pd.to_datetime(["2025-06-01T00:00:00Z"])
    frame["anchor_datetime_utc"] = pd.to_datetime(["2025-05-31T00:00:00Z"])
    frame["fcst_anchor_datetime_utc"] = pd.to_datetime(["2025-05-31T00:00:00Z"])
    return frame


def _synthetic_corridor_frame():
    return pd.DataFrame({
        "datetime_utc": pd.to_datetime(["2025-06-01T00:00:00Z"]),
        "anchor_datetime_utc": pd.to_datetime(["2025-05-31T00:00:00Z"]),
        "hour_mod_remainder": [0],
        "truth_dlr_amps": [1000.0],
        "bottleneck_index_truth": [0],
        "truth_air_temp": [25.0], "truth_wind_speed": [3.0],
        "truth_wind_direction": [180.0], "truth_solar_radiation": [500.0],
        "anchor_dlr_amps": [980.0],
        "bottleneck_index_anchor": [1],
        "anchor_air_temp": [24.0], "anchor_wind_speed": [2.5],
        "anchor_wind_direction": [170.0], "anchor_solar_radiation": [480.0],
        "nwp_wind_delta_clamped_a": [False], "nwp_wind_delta_clamped_b": [True],
        "pred_persistence_24h": [990.0], "bottleneck_index_persistence_24h": [0],
        "pred_oracle_observed_future_wind": [1005.0],
        "bottleneck_index_oracle_observed_future_wind": [1],
    })


def test_frame_time_reference_groups_per_city_frame_fully_classified():
    frame = _synthetic_per_city_frame()
    groups = fea.frame_time_reference_groups(frame)
    assert groups["unclassified"] == [], groups["unclassified"]
    assert groups["distinct_clock_instants_per_row"] == 2, groups["distinct_clock_instants_per_row"]
    assert set(groups["observed_at_valid_time"]) == {
        "truth_air_temp", "truth_wind_speed", "truth_wind_direction",
        "truth_solar_radiation", "truth_relative_humidity", "truth_dlr_amps",
    }
    assert set(groups["observed_at_decision_time"]) == {
        "anchor_air_temp", "anchor_wind_speed", "anchor_wind_direction",
        "anchor_solar_radiation", "anchor_relative_humidity", "anchor_dlr_amps",
    }
    assert set(groups["forecast_valid_at_valid_time"]) == {
        "fcst_air_temp", "fcst_wind_speed", "fcst_wind_direction",
        "fcst_solar_radiation", "fcst_relative_humidity",
    }
    assert set(groups["forecast_valid_at_decision_time"]) == {
        "fcst_anchor_air_temp", "fcst_anchor_wind_speed", "fcst_anchor_wind_direction",
        "fcst_anchor_solar_radiation", "fcst_anchor_relative_humidity",
    }
    assert groups["corridor_reduced_predictions"] == []
    assert groups["bottleneck_selection_diagnostics"] == []
    assert set(groups["index_and_diagnostic_columns"]) == {
        "datetime_utc", "anchor_datetime_utc", "fcst_anchor_datetime_utc", "hour_mod_remainder",
    }


def test_frame_time_reference_groups_unrecognized_column_is_unclassified_not_absorbed():
    frame = _synthetic_per_city_frame()
    frame["midwindow_truth_wind_speed_t_minus_12h"] = 0.0
    groups = fea.frame_time_reference_groups(frame)
    assert "midwindow_truth_wind_speed_t_minus_12h" in groups["unclassified"], groups["unclassified"]
    # It must NOT have been absorbed into observed_at_valid_time just
    # because "truth_" appears as a substring rather than a real prefix.
    assert "midwindow_truth_wind_speed_t_minus_12h" not in groups["observed_at_valid_time"]


def test_frame_time_reference_groups_corridor_frame_fully_classified_and_differs():
    frame = _synthetic_corridor_frame()
    groups = fea.frame_time_reference_groups(frame)
    assert groups["unclassified"] == [], groups["unclassified"]
    assert groups["distinct_clock_instants_per_row"] == 2, groups["distinct_clock_instants_per_row"]
    # The corridor frame carries corridor-reduced predictions and
    # bottleneck-selection diagnostics the per-city frame does not, and
    # carries NO forecast_valid_at_* groups (no fcst_*/fcst_anchor_* columns
    # in the corridor-level frame at all) -- the documented difference from
    # the per-city frame's own classification.
    assert set(groups["corridor_reduced_predictions"]) == {
        "pred_persistence_24h", "pred_oracle_observed_future_wind",
    }
    assert set(groups["bottleneck_selection_diagnostics"]) == {
        "bottleneck_index_truth", "bottleneck_index_anchor",
        "bottleneck_index_persistence_24h", "bottleneck_index_oracle_observed_future_wind",
    }
    assert groups["forecast_valid_at_valid_time"] == []
    assert groups["forecast_valid_at_decision_time"] == []
    assert "nwp_wind_delta_clamped_a" in groups["index_and_diagnostic_columns"]
    assert "nwp_wind_delta_clamped_b" in groups["index_and_diagnostic_columns"]


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-02 Task 2: leakage_probe_coverage_report. Network-free -- patches
# `forecast_experiment_audit.forecast_experiment.anchored_pair_frame` (the
# per-city assembly helper both `corridor_anchored_pair_frame` and
# `_stacked_pair_frame` call internally), on the AUDIT MODULE's own
# reference to the harness module object, exactly like Plan 04-01's own
# `_patch_harness_assembly`. Patching one level lower than that (at
# `anchored_pair_frame` rather than `corridor_anchored_pair_frame`/
# `_stacked_pair_frame` directly) makes the REAL harness code responsible
# for corridor-level reduction and stacking, so Mode A's corridor-level
# frame and Mode B's per-city frames are guaranteed internally consistent
# (built from the identical underlying synthetic per-city series) without
# hand-duplicating that reduction logic in this test file.
# ──────────────────────────────────────────────────────────────────────────

_LEAKAGE_TEST_CORRIDOR = "AUSTIN_CORPUS_CHRISTI"
_LEAKAGE_TEST_LEAD_HOURS = 24


def _synthetic_anchored_pair_frame(city: str, *, periods=24 * 220, start="2024-01-01", seed: int) -> pd.DataFrame:
    """
    A deterministic, fully-populated hourly per-city frame carrying the
    REAL `anchored_pair_frame` schema (truth_*/anchor_*/fcst_*/fcst_anchor_*,
    `datetime_utc`/`anchor_datetime_utc`/`fcst_anchor_datetime_utc`,
    `hour_mod_remainder`) with the SAME anchor-group semantics the real
    function uses (the anchor group is the truth series shifted forward by
    `lead_hours` -- built here via `.shift(lead_hours)` on a contiguous
    hourly index, which is equivalent since the synthetic index has no
    gaps). `truth_dlr_amps` is computed through the REAL
    `forecast_experiment._city_ampacity` physics, never reinvented, so
    arm 5's real training pipeline sees a physically coherent target.
    """
    idx = pd.date_range(start, periods=periods, freq="h", tz="UTC")
    t = np.arange(len(idx), dtype=float)
    rng = np.random.default_rng(seed)
    lead_td = pd.Timedelta(hours=_LEAKAGE_TEST_LEAD_HOURS)

    corridor = next(
        c for c, cities in config.CORRIDOR_ENDPOINTS.items() if city in cities
    )
    geometry = corridor_discretization.corridor_geometry(corridor)

    truth_air_temp = 25.0 + 8.0 * np.sin(t / 24.0)
    truth_wind_speed = 3.0 + rng.random(len(idx)) * 2.0
    truth_wind_direction = (t * 7.0) % 360.0
    truth_solar_radiation = np.clip(600.0 * np.sin(t / 24.0), 0.0, None)
    truth_relative_humidity = 50.0 + rng.random(len(idx)) * 10.0
    truth_dlr_amps = fea.forecast_experiment._city_ampacity(
        truth_air_temp, truth_wind_speed, truth_wind_direction, truth_solar_radiation, geometry,
    )

    frame = pd.DataFrame({"datetime_utc": idx})
    frame["truth_air_temp"] = truth_air_temp
    frame["truth_wind_speed"] = truth_wind_speed
    frame["truth_wind_direction"] = truth_wind_direction
    frame["truth_solar_radiation"] = truth_solar_radiation
    frame["truth_relative_humidity"] = truth_relative_humidity
    frame["truth_dlr_amps"] = truth_dlr_amps

    frame["fcst_air_temp"] = truth_air_temp + rng.normal(0, 0.5, len(idx))
    frame["fcst_wind_speed"] = np.clip(truth_wind_speed + rng.normal(0, 0.3, len(idx)), 0.0, None)
    frame["fcst_wind_direction"] = truth_wind_direction
    frame["fcst_solar_radiation"] = truth_solar_radiation
    frame["fcst_relative_humidity"] = truth_relative_humidity

    for col in ("air_temp", "wind_speed", "wind_direction", "solar_radiation", "relative_humidity", "dlr_amps"):
        frame[f"anchor_{col}"] = frame[f"truth_{col}"].shift(_LEAKAGE_TEST_LEAD_HOURS)
    for col in ("air_temp", "wind_speed", "wind_direction", "solar_radiation", "relative_humidity"):
        frame[f"fcst_anchor_{col}"] = frame[f"fcst_{col}"].shift(_LEAKAGE_TEST_LEAD_HOURS)

    frame["anchor_datetime_utc"] = frame["datetime_utc"] - lead_td
    frame["fcst_anchor_datetime_utc"] = frame["datetime_utc"] - lead_td
    frame["hour_mod_remainder"] = (
        frame["datetime_utc"].dt.hour % config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    )
    return frame.dropna().reset_index(drop=True)


def _patch_leakage_test_assembly(monkeypatch, *, periods=24 * 220):
    city_a, city_b = config.CORRIDOR_ENDPOINTS[_LEAKAGE_TEST_CORRIDOR]
    frames = {
        city_a: _synthetic_anchored_pair_frame(city_a, periods=periods, seed=20260930),
        city_b: _synthetic_anchored_pair_frame(city_b, periods=periods, seed=20260931),
    }

    def fake_anchored_pair_frame(city, start=None, end=None, *, lead_hours):
        return frames[city].copy()

    monkeypatch.setattr(fea.forecast_experiment, "anchored_pair_frame", fake_anchored_pair_frame)


def test_leakage_probe_coverage_report_refuses_unknown_corridor():
    with pytest.raises(ValueError) as exc_info:
        fea.leakage_probe_coverage_report("NOT_A_REAL_CORRIDOR")
    message = str(exc_info.value)
    for name in config.CORRIDOR_ENDPOINTS:
        assert name in message, message


def test_leakage_probe_coverage_report_runs_and_returns_documented_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    report_path = str(tmp_path / "leakage_report.json")
    report = fea.leakage_probe_coverage_report(_LEAKAGE_TEST_CORRIDOR, report_path=report_path)

    for key in ("mode_a", "mode_b", "comparison", "finding"):
        assert key in report, sorted(report)
    for mode_key in ("mode_a", "mode_b"):
        mode = report[mode_key]
        assert "arms" in mode and "frozen_window_guard_passed" in mode
        assert mode["frozen_window_guard_passed"] is True

    b_arms = report["mode_b"]["arms"]
    assert len(b_arms) >= 8, sorted(b_arms)
    sabotaged = [n for n in b_arms if "sabotag" in n]
    assert sabotaged, sorted(b_arms)
    assert b_arms[sabotaged[0]]["changed"] is True

    oracle_name = fea.forecast_experiment.ORACLE_ARM_NAME
    assert b_arms[oracle_name]["changed"] is True
    for name, res in b_arms.items():
        if name == oracle_name or "sabotag" in name:
            continue
        assert res["changed"] is False, (name, res)

    assert isinstance(report["finding"], str) and report["finding"].strip()
    assert "oracle_distinguished" in report["comparison"]

    # Report round-trips through JSON.
    with open(report_path) as fh:
        reloaded = json.load(fh)
    assert reloaded["corridor"] == _LEAKAGE_TEST_CORRIDOR
    assert set(reloaded["mode_b"]["arms"]) == set(b_arms)


def test_leakage_probe_coverage_report_mode_a_shows_no_power_via_column_reader_shape(monkeypatch, tmp_path):
    """
    Mode A's callable shape (a reader of an already-computed pred_<arm>
    column) is structurally blind to sabotaging truth_* columns -- every
    arm, including the oracle, must report unchanged.
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    report = fea.leakage_probe_coverage_report(_LEAKAGE_TEST_CORRIDOR)
    a_arms = report["mode_a"]["arms"]
    for name, res in a_arms.items():
        assert res["changed"] is False, (name, res)
    assert report["comparison"]["oracle_distinguished"] is False
    assert report["comparison"]["mode_a_all_unchanged_including_oracle"] is True


def test_leakage_probe_coverage_report_guard_runs_before_probe(monkeypatch, tmp_path):
    """
    Prove the frozen-window guard executes BEFORE `leakage_probe` by
    forcing the guard to raise on its first invocation and tracking whether
    `leakage_probe` was ever reached. If the guard truly runs first,
    `leakage_probe` must never be called.
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))

    def _fake_corridor_frame(corridor, start, end, *, lead_hours):
        idx = pd.date_range("2024-01-01", periods=24 * 40, freq="h", tz="UTC")
        return pd.DataFrame({"datetime_utc": idx})

    monkeypatch.setattr(fea.forecast_experiment, "corridor_anchored_pair_frame", _fake_corridor_frame)

    probe_called = {"value": False}
    real_probe = fea.forecast_experiment.leakage_probe

    def _tracking_probe(frame, arms):
        probe_called["value"] = True
        return real_probe(frame, arms)

    monkeypatch.setattr(fea.forecast_experiment, "leakage_probe", _tracking_probe)

    def _raising_guard(frame, *, basis):
        raise ValueError("forced frozen-window violation for ordering test")

    monkeypatch.setattr(fea, "assert_basis_excludes_frozen_test_rows", _raising_guard)

    with pytest.raises(ValueError, match="forced frozen-window violation"):
        fea.leakage_probe_coverage_report(_LEAKAGE_TEST_CORRIDOR)
    assert probe_called["value"] is False, "leakage_probe was reached despite the guard raising first"
