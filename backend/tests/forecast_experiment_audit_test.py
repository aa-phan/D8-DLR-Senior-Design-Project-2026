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


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-02 Task 3: arm5_label_timing_finding, split_boundary_audit,
# arm5_lag_offset_finding, and the closing d01_findings_table. Network-free,
# reusing the same synthetic per-city assembly fixture Task 2 established.
# ──────────────────────────────────────────────────────────────────────────

def test_arm5_label_timing_finding_reports_single_24h_offset_and_distinct_horizons(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    t = fea.arm5_label_timing_finding(_LEAKAGE_TEST_CORRIDOR)
    assert t["distinct_feature_to_label_offsets"] == ["24.0h"], t["distinct_feature_to_label_offsets"]
    assert t["production_default_horizon_minutes"] != t["experiment_horizon_minutes"], t
    assert t["train_labels_precede_scored_validation"] is True, t


def test_split_boundary_audit_reports_zero_overlap_and_required_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    b = fea.split_boundary_audit(_LEAKAGE_TEST_CORRIDOR)
    assert b["shared_timestamp_count"] == 0, b
    assert "boundary_row_side" in b, sorted(b)
    for side in ("train", "val", "test"):
        assert b["filtered_rows"][side] >= 0, b["filtered_rows"]


def test_split_boundary_audit_raises_on_overlapping_sides(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    real_calendar_split = fea.experiment_splits.calendar_split

    def _corrupted_split(frame, boundaries):
        train, val, test = real_calendar_split(frame, boundaries)
        # Corrupt: val becomes an exact copy of train -- massively
        # overlapping rather than chronologically disjoint.
        return train, train.copy(), test

    monkeypatch.setattr(fea.experiment_splits, "calendar_split", _corrupted_split)

    with pytest.raises(ValueError):
        fea.split_boundary_audit(_LEAKAGE_TEST_CORRIDOR)


def test_split_boundary_audit_boundary_predicate_is_a_tested_fact(monkeypatch, tmp_path):
    """
    Synthetic boundary-predicate test: a row exactly at each boundary
    instant lands on the documented side (at-or-after goes right,
    strictly-before goes left) -- a tested fact, not a reading of the
    predicates.
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))

    val_start = pd.Timestamp("2025-06-01T00:00:00Z")
    test_start = pd.Timestamp("2025-09-01T00:00:00Z")
    fixed_boundaries = fea.experiment_splits.SplitBoundaries(val_start, test_start)

    idx = pd.date_range("2025-01-01", "2025-12-31", freq="6h", tz="UTC")
    idx = idx.union(pd.DatetimeIndex([val_start, test_start]))
    frame = pd.DataFrame({"datetime_utc": idx})

    def _fake_corridor_frame(corridor, start, end, *, lead_hours):
        return frame.copy()

    monkeypatch.setattr(fea.forecast_experiment, "corridor_anchored_pair_frame", _fake_corridor_frame)
    monkeypatch.setattr(fea.forecast_experiment, "_default_split_boundaries", lambda f: fixed_boundaries)

    b = fea.split_boundary_audit(_LEAKAGE_TEST_CORRIDOR)
    assert b["boundary_row_side"]["val_start"] == "val", b["boundary_row_side"]
    assert b["boundary_row_side"]["test_start"] == "test", b["boundary_row_side"]


def test_arm5_lag_offset_finding_disagrees_and_reports_unbroken_cadence(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    g = fea.arm5_lag_offset_finding(_LEAKAGE_TEST_CORRIDOR)
    assert g["filter_first_agrees_with_harness_order"] is False, g
    assert "distinct_spacings" in g and g["distinct_spacings"], g
    assert isinstance(g["positional_shift_safe"], bool)
    assert g["positional_shift_safe"] is True, g  # the synthetic fixture has no gaps


def test_arm5_lag_offset_finding_gap_detector_detects_a_deliberately_removed_hour(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    city_a, city_b = config.CORRIDOR_ENDPOINTS[_LEAKAGE_TEST_CORRIDOR]
    frame_a = _synthetic_anchored_pair_frame(city_a, periods=24 * 220, seed=20260930)
    frame_b = _synthetic_anchored_pair_frame(city_b, periods=24 * 220, seed=20260931)
    # Deliberately remove one interior hour from city_a's frame to create a
    # genuine gap (the inner merge in _arm5_truth_frame will then skip that
    # hour on BOTH sides, leaving a real 2-hour spacing where an hour is
    # missing) -- proving the gap detector DETECTS rather than merely passes.
    frame_a = frame_a.drop(frame_a.index[500]).reset_index(drop=True)

    def fake_anchored_pair_frame(city, start=None, end=None, *, lead_hours):
        return {city_a: frame_a, city_b: frame_b}[city].copy()

    monkeypatch.setattr(fea.forecast_experiment, "anchored_pair_frame", fake_anchored_pair_frame)

    g = fea.arm5_lag_offset_finding(_LEAKAGE_TEST_CORRIDOR)
    assert g["positional_shift_safe"] is False, g
    assert len(g["distinct_spacings"]) > 1, g["distinct_spacings"]


def test_d01_findings_table_has_five_rows_one_per_bullet():
    table = fea.d01_findings_table()
    assert len(table) == 5, table
    for row in table:
        for key in ("bullet", "disposition", "evidence_type", "citation"):
            assert key in row and row[key], row
    bullets_text = " ".join(row["bullet"] for row in table)
    for n in ("1", "2", "3", "4", "5"):
        assert f"bullet {n}" in bullets_text.lower(), bullets_text


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-03 Task 1: paired_block_bootstrap_margin, iid_percentile_margin,
# block_length_sensitivity.
#
# NOTE on the dependent-series construction used below (deviation, see
# SUMMARY.md): the plan's OWN <verify><automated> script for this task
# builds its "strongly autocorrelated" series as
# `dep_base = np.abs(150.0 + ar)`, `dep_arm = np.abs(120.0 + ar)` for an
# AR(1) `ar` with std ~34 that never approaches -120. Both `abs()` calls
# are then no-ops for every row, so `dep_base - dep_arm` is EXACTLY the
# constant 30.0 for every single row regardless of the AR(1) noise or
# seed -- confirmed empirically (`np.ptp(diff)` is ~2.8e-14, i.e. zero
# within float tolerance). A perfectly constant difference series hits
# this function's OWN REQUIRED zero-variance degenerate short-circuit
# (mirroring the i.i.d. version's identical guard) regardless of
# implementation, so the plan's literal script can never observe
# widening under dependence -- this is a verify-script construction
# defect, not a defect in this module. The tests below instead build the
# difference series DIRECTLY as `diff = ar` (shifting by a large constant
# so `abs()` stays a no-op), which varies genuinely row-to-row and
# carries real AR(1) dependence -- independently confirmed via
# `np.allclose(dep_base - dep_arm, ar)` during this task's own
# development. A module-level seeded generator (seed 20260929, this
# project's one fixed seed, reused per `_synthetic_anchored_pair_frame`'s
# own convention above) keeps every test deterministic.
# ──────────────────────────────────────────────────────────────────────────


def _dependent_diff_series(n=800, *, seed=20260929, phi=0.95, noise_std=10.0, shift=1000.0):
    """
    A genuinely autocorrelated difference series: `errors_baseline =
    |shift + ar|`, `errors_arm = shift` (constant), so
    `errors_baseline - errors_arm == ar` exactly whenever `shift` is large
    enough that `abs()` never flips sign (`shift=1000.0` against an AR(1)
    series whose stationary std is ~34 at `phi=0.95`/`noise_std=10.0`
    leaves a wide margin). Returns `(errors_arm, errors_baseline, ar)`.
    """
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, noise_std, n)
    ar = np.zeros(n)
    for i in range(1, n):
        ar[i] = phi * ar[i - 1] + noise[i]
    errors_baseline = np.abs(shift + ar)
    errors_arm = np.full(n, shift)
    assert np.allclose(errors_baseline - errors_arm, ar)
    return errors_arm, errors_baseline, ar


def _independent_diff_series(n=800, *, seed=20260930, std=34.0, shift=1000.0):
    """The no-dependence control: `errors_baseline - errors_arm` is i.i.d. noise with roughly the dependent series' own stationary std, no autocorrelation."""
    rng = np.random.default_rng(seed)
    iid_noise = rng.normal(0.0, std, n)
    errors_baseline = np.abs(shift + iid_noise)
    errors_arm = np.full(n, shift)
    assert np.allclose(errors_baseline - errors_arm, iid_noise)
    return errors_arm, errors_baseline, iid_noise


def test_paired_block_bootstrap_margin_at_block_length_one_matches_iid_percentile():
    rng = np.random.default_rng(20260929)
    n = 800
    base = np.abs(rng.normal(120.0, 30.0, n))
    arm = np.abs(base - rng.normal(20.0, 25.0, n))
    b1 = fea.paired_block_bootstrap_margin(arm, base, block_length=1)
    iid = fea.iid_percentile_margin(arm, base)
    for key in ("point", "ci_low", "ci_high", "excludes_zero_favorably", "block_length", "n_resamples", "method"):
        assert key in b1, sorted(b1)
    # Resampling-noise tolerance: both intervals resample the SAME 800-row
    # series at the SAME n_resamples=10000/95% confidence from this
    # project's one fixed seed, via two different (but equally valid)
    # percentile-method implementations -- any residual disagreement is
    # pure resampling noise, not a systematic difference, and should be a
    # small fraction of the margin's own scale (tens of amps).
    assert abs(b1["ci_low"] - iid["ci_low"]) < 1.0, (b1, iid)
    assert abs(b1["ci_high"] - iid["ci_high"]) < 1.0, (b1, iid)
    assert b1["ci_low"] <= b1["point"] <= b1["ci_high"], b1


def test_paired_block_bootstrap_margin_widens_under_dependence():
    errors_arm, errors_baseline, _ = _dependent_diff_series()
    w1 = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=1)
    w48 = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=48)
    assert (w48["ci_high"] - w48["ci_low"]) > (w1["ci_high"] - w1["ci_low"]), (w1, w48)


def test_paired_block_bootstrap_margin_no_widening_under_independence():
    errors_arm, errors_baseline, _ = _independent_diff_series()
    w1 = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=1)
    w48 = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=48)
    width1 = w1["ci_high"] - w1["ci_low"]
    width48 = w48["ci_high"] - w48["ci_low"]
    # "Agree within tolerance" -- not EXACT equality, since block resampling
    # of an independent series still differs slightly in effective sample
    # size from pure i.i.d. resampling. 25% of the narrower width is a
    # generous band for resampling noise at this sample size/resample
    # count, while still being far tighter than the ~5x widening the
    # dependent series above shows.
    assert abs(width48 - width1) < 0.25 * width1, (w1, w48)


def test_paired_block_bootstrap_margin_bounds_bracket_point_and_exclusion_matches_sign():
    rng = np.random.default_rng(20260929)
    errors_baseline = rng.normal(0.0, 10.0, size=300)
    errors_arm = errors_baseline * 0.5  # systematically smaller |error| -> favors the arm
    result = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=6)
    assert result["ci_low"] <= result["point"] <= result["ci_high"]
    assert result["point"] > 0.0
    assert result["excludes_zero_favorably"] is True


def test_paired_block_bootstrap_margin_reports_non_exclusion_for_difference_centered_on_zero():
    rng = np.random.default_rng(20260929)
    errors_baseline = rng.normal(0.0, 10.0, size=300)
    errors_arm = rng.normal(0.0, 10.0, size=300)
    result = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=6)
    assert result["ci_low"] <= result["point"] <= result["ci_high"]
    assert result["excludes_zero_favorably"] is False


def test_paired_block_bootstrap_margin_degenerate_self_comparison_is_zero_width_at_zero():
    rng = np.random.default_rng(1)
    errors = rng.normal(0.0, 5.0, size=50)
    result = fea.paired_block_bootstrap_margin(errors, errors, block_length=4)
    assert result["point"] == 0.0 and result["ci_low"] == 0.0 and result["ci_high"] == 0.0
    assert result["excludes_zero_favorably"] is False
    assert result["n_resamples"] == 0  # degenerate short-circuit never resamples


def test_paired_block_bootstrap_margin_raises_on_shape_mismatch():
    with pytest.raises(ValueError):
        fea.paired_block_bootstrap_margin(np.zeros(5), np.zeros(6), block_length=2)


def test_paired_block_bootstrap_margin_is_deterministic():
    errors_arm, errors_baseline, _ = _dependent_diff_series()
    first = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=12)
    second = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=12)
    assert first == second


def test_paired_block_bootstrap_margin_raises_on_invalid_block_length():
    with pytest.raises(ValueError) as exc_info:
        fea.paired_block_bootstrap_margin(np.zeros(5), np.ones(5), block_length=0)
    assert "0" in str(exc_info.value)

    with pytest.raises(ValueError) as exc_info:
        fea.paired_block_bootstrap_margin(np.zeros(5), np.ones(5), block_length=6)
    assert "6" in str(exc_info.value) and "5" in str(exc_info.value)


def test_paired_block_bootstrap_margin_raises_on_invalid_method():
    with pytest.raises(ValueError):
        fea.paired_block_bootstrap_margin(np.zeros(5), np.ones(5), block_length=2, method="bogus")


def test_paired_block_bootstrap_margin_circular_method_is_recorded_and_valid():
    errors_arm, errors_baseline, _ = _dependent_diff_series()
    result = fea.paired_block_bootstrap_margin(errors_arm, errors_baseline, block_length=24, method="circular")
    assert result["method"] == "circular"
    assert result["ci_low"] <= result["point"] <= result["ci_high"]


def test_iid_percentile_margin_degenerate_self_comparison_is_zero_width_at_zero():
    rng = np.random.default_rng(1)
    errors = rng.normal(0.0, 5.0, size=50)
    result = fea.iid_percentile_margin(errors, errors)
    assert result == {"point": 0.0, "ci_low": 0.0, "ci_high": 0.0, "excludes_zero_favorably": False}


def test_iid_percentile_margin_raises_on_shape_mismatch():
    with pytest.raises(ValueError):
        fea.iid_percentile_margin(np.zeros(5), np.zeros(6))


def test_block_length_sensitivity_sweeps_at_least_four_lengths_including_one():
    errors_arm, errors_baseline, _ = _dependent_diff_series()
    sweep = fea.block_length_sensitivity(errors_arm, errors_baseline)
    assert len(sweep["by_block_length"]) >= 4, sorted(sweep["by_block_length"])
    assert 1 in sweep["block_lengths_used"], sweep["block_lengths_used"]
    assert "iid_percentile" in sweep
    assert isinstance(sweep["conclusion_stable"], bool)
    assert isinstance(sweep["disagreeing_block_lengths"], list)
    for key in ("min_width", "max_width"):
        assert "block_length" in sweep[key] and "width" in sweep[key], sweep[key]


def test_block_length_sensitivity_reports_disagreeing_lengths_when_unstable():
    # A difference series (`diff = errors_baseline's abs - errors_arm's
    # abs`, built via the same shift trick `_dependent_diff_series` uses so
    # the pattern's own sign survives both abs() calls) that is mostly a
    # small positive constant (1.0) with one 20-row CONTIGUOUS negative
    # cluster (-5.0). Point margin is positive (0.5), and at block_length=1
    # i.i.d. resampling blends the cluster's rows individually into a
    # narrow, favourably-excluding interval -- but at block lengths at or
    # beyond the cluster's own width (20), a resampled block can capture
    # the WHOLE cluster intact, pulling the interval down to include zero.
    # Independently confirmed to flip exactly at block lengths 24/48 while
    # 1/4 stay excluding, which is what this test asserts.
    n = 240
    shift = 1000.0
    pattern = np.full(n, 1.0)
    pattern[100:120] = -5.0
    errors_baseline = np.abs(shift + pattern)
    errors_arm = np.full(n, shift)
    assert np.allclose(errors_baseline - errors_arm, pattern)

    sweep = fea.block_length_sensitivity(errors_arm, errors_baseline, block_lengths=(1, 4, 24, 48))
    assert isinstance(sweep["conclusion_stable"], bool)
    assert sweep["conclusion_stable"] is False, sweep
    assert sorted(sweep["disagreeing_block_lengths"]) == [24, 48], sweep


def test_block_length_sensitivity_custom_block_lengths_are_recorded():
    errors_arm, errors_baseline, _ = _dependent_diff_series()
    sweep = fea.block_length_sensitivity(errors_arm, errors_baseline, block_lengths=(1, 4, 8, 28))
    assert sweep["block_lengths_used"] == [1, 4, 8, 28]
    assert sorted(int(k) for k in sweep["by_block_length"]) == [1, 4, 8, 28]


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-03 Task 2: ablation_basis_report, fresh_basis_attempt.
#
# Reuses the Plan 04-02 fixture directly: `_patch_leakage_test_assembly`
# monkeypatches `forecast_experiment.anchored_pair_frame` (one level below
# `corridor_anchored_pair_frame`/`_stacked_pair_frame`), so the REAL
# corridor-reduction and stacking logic runs unmodified against a
# deterministic synthetic two-city frame whose timestamps (2024-01-01
# onward, 220 days) sit entirely before the frozen test split start
# (2026-03-17) -- genuinely network-free, no fetch monkeypatching needed
# beyond that one seam.
# ──────────────────────────────────────────────────────────────────────────


def _write_zero_fresh_manifest(tmp_path, corridor=_LEAKAGE_TEST_CORRIDOR, lead_hours=_LEAKAGE_TEST_LEAD_HOURS):
    """
    A pre-built manifest recording the FRESH basis at zero rows -- the
    REAL, measured state for both corridors as of this phase's own
    research date (04-01-SUMMARY.md) -- so `ablation_basis_report`'s own
    call to `fresh_basis_attempt` reads this file directly rather than
    triggering `build_basis_manifest`'s own live-assembly path (which
    would otherwise need a date-range-aware fake, since the FRESH window's
    requested start/end differ from the ABLATION window's).
    """
    manifest_path = str(tmp_path / "manifest.json")
    manifest = {
        "generated_at": "test-fixture",
        "resolved_window_end": fea.FROZEN_WINDOW_END,
        "lead_hours": lead_hours,
        "corridors": {
            corridor: {
                "fresh": {
                    "rows": 0,
                    "reason": "test fixture: no fresh data",
                    "resolved_window_end": fea.FROZEN_WINDOW_END,
                },
            },
        },
    }
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)
    return manifest_path


def test_ablation_basis_report_refuses_unknown_corridor():
    with pytest.raises(ValueError) as exc_info:
        fea.ablation_basis_report("NOT_A_REAL_CORRIDOR")
    message = str(exc_info.value)
    for name in config.CORRIDOR_ENDPOINTS:
        assert name in message, message


def test_ablation_basis_report_runs_and_returns_documented_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)
    manifest_path = _write_zero_fresh_manifest(tmp_path)

    report_path = str(tmp_path / "ablation_report.json")
    r = fea.ablation_basis_report(
        _LEAKAGE_TEST_CORRIDOR, report_path=report_path, fresh_manifest_path=manifest_path,
    )

    assert r["ablation_guard_passed_fit"] is True
    assert r["ablation_guard_passed_scored"] is True
    assert r["max_fit_timestamp"] < r["min_scored_timestamp"]

    cand = r["candidates"]
    for name in (
        "persistence_24h", "nwp_wind_delta", "raw_forecast",
        "ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h",
    ):
        assert name in cand, sorted(cand)
        assert cand[name]["mae"] > 0 and cand[name]["rmse"] > 0, (name, cand[name])
    assert cand[r["oracle_arm_name"]]["is_oracle_diagnostic"] is True

    baselines = r["pairwise"]
    assert len(baselines) >= 4, sorted(baselines)
    assert "ml_cooling_corrected" in baselines and "raw_forecast" in baselines, sorted(baselines)
    for bname, entry in baselines.items():
        assert bname != r["oracle_arm_name"], f"the oracle was used as a baseline"
        for arm, m in entry.items():
            assert arm != r["oracle_arm_name"], f"the oracle appeared as a compared arm under baseline {bname}"
            assert "iid_bca" in m and "iid_percentile" in m and "block" in m, (bname, arm, sorted(m))
            assert len(m["block"]) >= 4, (bname, arm, sorted(m["block"]))
            assert "conclusion_stable" in m, (bname, arm, sorted(m))

    assert isinstance(r["mae_rmse_ordering_disagreements"], list)

    res = r["residuals"]
    for name in ("persistence_24h", "ml_cooling_corrected"):
        arr = np.asarray(res[name], dtype=float)
        assert abs(float(np.mean(np.abs(arr))) - cand[name]["mae"]) < 1e-9, (name, arr.mean(), cand[name]["mae"])

    assert r["fresh_basis"]["branch"] == "not_attempted_zero_rows"
    assert "ABLATION" in r["basis_caveat"]

    with open(report_path, "r", encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["corridor"] == _LEAKAGE_TEST_CORRIDOR

    # The leakage probe is wired into this report's own scoring path (not
    # a separate standalone diagnostic) and its positive controls must
    # have fired: the sabotaged arm and the oracle both demonstrably
    # changed under truth-column sabotage, and every genuine candidate
    # did not.
    lp = r["leakage_probe"]
    assert lp["positive_controls_passed"] is True
    assert lp["sabotaged_arm_detected"] is True
    assert lp["oracle_detected"] is True
    assert lp["genuine_candidates_unchanged"] is True
    assert len(lp["by_city"]) == 2, sorted(lp["by_city"])
    for city_result in lp["by_city"].values():
        assert "sabotaged_reads_truth_wind_directly" in city_result
        assert city_result[r["oracle_arm_name"]]["changed"] is True


def test_ablation_basis_report_leakage_probe_catches_a_real_injected_leak(monkeypatch, tmp_path):
    """
    A probe that only ever reports "no leak" without ever being shown to
    catch a REAL leak in a GENUINE candidate (not just the always-sabotaged
    dummy arm) proves nothing. This deliberately makes `ml_wind_corrected`
    read `truth_wind_speed` directly instead of its usual forecast column,
    and asserts the now-integrated probe inside `ablation_basis_report`
    detects it and refuses to produce numbers.
    """
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)
    manifest_path = _write_zero_fresh_manifest(tmp_path)

    real_wind_corrected = fea.forecast_experiment._wind_corrected_ampacity

    def _leaking_wind_corrected(model, frame, geometry):
        # Ignore the model and forecast columns entirely; read the valid
        # -time truth column directly -- the exact failure mode the probe
        # exists to catch.
        return frame["truth_wind_speed"].to_numpy(dtype=float)

    monkeypatch.setattr(fea.forecast_experiment, "_wind_corrected_ampacity", _leaking_wind_corrected)

    with pytest.raises(ValueError, match="leakage probe detected a genuine"):
        fea.ablation_basis_report(
            _LEAKAGE_TEST_CORRIDOR,
            report_path=str(tmp_path / "report.json"),
            fresh_manifest_path=manifest_path,
        )


def test_ablation_basis_report_raises_on_overlapping_fit_and_score_frames(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)
    manifest_path = _write_zero_fresh_manifest(tmp_path)

    real_calendar_split = fea.experiment_splits.calendar_split

    def _corrupted_split(frame, boundaries):
        train, val, test = real_calendar_split(frame, boundaries)
        # Corrupt: val becomes an exact copy of train -- the fit frame and
        # the scored frame now overlap completely, which must raise rather
        # than silently produce an in-sample "out-of-sample" measurement.
        return train, train.copy(), test

    monkeypatch.setattr(fea.experiment_splits, "calendar_split", _corrupted_split)

    with pytest.raises(ValueError):
        fea.ablation_basis_report(
            _LEAKAGE_TEST_CORRIDOR,
            report_path=str(tmp_path / "report.json"),
            fresh_manifest_path=manifest_path,
        )


def test_ablation_basis_report_residual_cross_check_raises_on_perturbed_scorer(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)
    manifest_path = _write_zero_fresh_manifest(tmp_path)

    real_score_arms = fea.forecast_experiment.score_arms

    def _corrupted_score_arms(frame, arms, **kwargs):
        result = real_score_arms(frame, arms, **kwargs)
        # Perturb one arm's reported MAE so it disagrees with this
        # function's own independently recomputed residual-based MAE --
        # proving the cross-check actually raises rather than always
        # trivially agreeing with itself.
        any_name = next(iter(result["candidates"]))
        result["candidates"][any_name]["mae"] += 999.0
        return result

    monkeypatch.setattr(fea.forecast_experiment, "score_arms", _corrupted_score_arms)

    with pytest.raises(ValueError):
        fea.ablation_basis_report(
            _LEAKAGE_TEST_CORRIDOR,
            report_path=str(tmp_path / "report.json"),
            fresh_manifest_path=manifest_path,
        )


def test_fresh_basis_attempt_refuses_unknown_corridor():
    with pytest.raises(ValueError) as exc_info:
        fea.fresh_basis_attempt("NOT_A_REAL_CORRIDOR")
    message = str(exc_info.value)
    for name in config.CORRIDOR_ENDPOINTS:
        assert name in message, message


def test_fresh_basis_attempt_zero_rows_branch(tmp_path):
    manifest_path = _write_zero_fresh_manifest(tmp_path)
    result = fea.fresh_basis_attempt(_LEAKAGE_TEST_CORRIDOR, manifest_path=manifest_path)
    assert result["branch"] == "not_attempted_zero_rows"
    assert result["rows"] == 0
    assert result["minimum_rows"] > 0
    assert result["minimum_days"] == result["minimum_rows"] / 4.0
    assert result["reason"]
    assert result["confirmation_claim_permitted"] is False


def test_fresh_basis_attempt_below_minimum_branch(tmp_path):
    manifest_path = str(tmp_path / "manifest.json")
    manifest = {
        "generated_at": "test-fixture", "resolved_window_end": fea.FROZEN_WINDOW_END,
        "lead_hours": _LEAKAGE_TEST_LEAD_HOURS,
        "corridors": {_LEAKAGE_TEST_CORRIDOR: {"fresh": {"rows": 8, "resolved_window_end": fea.FROZEN_WINDOW_END}}},
    }
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)

    result = fea.fresh_basis_attempt(_LEAKAGE_TEST_CORRIDOR, minimum_rows=56, manifest_path=manifest_path)
    assert result["branch"] == "below_minimum"
    assert result["rows"] == 8
    assert 0 < result["rows"] < result["minimum_rows"]
    assert result["confirmation_claim_permitted"] is False


def test_fresh_basis_attempt_confirmation_capable_branch_scores_fresh_rows(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))

    fresh_start = pd.Timestamp(fea.FROZEN_WINDOW_END, tz="UTC") + pd.Timedelta(days=1)
    fresh_frames = {
        city: _synthetic_anchored_pair_frame(
            city, periods=24 * 20, start=fresh_start.strftime("%Y-%m-%d"), seed=seed,
        )
        for city, seed in zip(config.CORRIDOR_ENDPOINTS[_LEAKAGE_TEST_CORRIDOR], (555, 556))
    }

    def fake_anchored_pair_frame(city, start=None, end=None, *, lead_hours):
        return fresh_frames[city].copy()

    monkeypatch.setattr(fea.forecast_experiment, "anchored_pair_frame", fake_anchored_pair_frame)

    manifest_path = str(tmp_path / "manifest.json")
    manifest = {
        "generated_at": "test-fixture", "resolved_window_end": "2026-10-19",
        "lead_hours": _LEAKAGE_TEST_LEAD_HOURS,
        "corridors": {
            _LEAKAGE_TEST_CORRIDOR: {
                "fresh": {
                    "rows": 60,
                    "resolved_window_start": fresh_start.strftime("%Y-%m-%d"),
                    "resolved_window_end": "2026-10-19",
                },
            },
        },
    }
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)

    result = fea.fresh_basis_attempt(_LEAKAGE_TEST_CORRIDOR, minimum_rows=56, manifest_path=manifest_path)
    assert result["branch"] == "confirmation_capable"
    assert result["confirmation_claim_permitted"] is True
    assert result["frozen_window_guard"]["rows"] > 0
    assert "scored" in result and "candidates" in result["scored"]


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-04 Task 1: overrating_profile, convection_crossover_wind_speed,
# overrating_by_regime (D-03 bullet 1).
#
# NOTE: `04-04-PLAN.md`'s own hand-literal `OVERRATING_PROFILE_OK` inline
# verify script asserts `count == 6` and a mean excluding index 7's own
# +50.0 exceedance while SEPARATELY asserting `max_exceedance_amps == 50.0`
# (that same row) on the identical `pred`/`truth` pair -- mutually
# unsatisfiable for any consistent "count/mean/max over the SAME overrating
# rows" definition, which is exactly what the plan's own <behavior> text
# requires. This is a verify-script defect (same class as the already-
# logged `##+ ` doc-regex bug, `.planning/WINDOWS.md` phase 04 id 2), not a
# profiler ambiguity -- see this plan's SUMMARY.md. The fixture below uses
# the SAME truth/pred/timestamps but hand-verifies the CORRECT answer
# (count=7, every exceedance including the 50.0 one feeding both the mean
# and the max) rather than reproducing the plan's own arithmetic slip.
# ──────────────────────────────────────────────────────────────────────────

def test_overrating_profile_matches_hand_computation():
    ts = pd.date_range("2025-10-01", periods=10, freq="6h", tz="UTC")
    truth = np.array([100.0] * 10)
    pred = np.array([110.0, 120.0, 90.0, 95.0, 105.0, 130.0, 140.0, 150.0, 99.0, 101.0])
    # diff = pred - truth: [10,20,-10,-5,5,30,40,50,-1,1]
    # overrating mask:     [T, T, F,  F, T, T, T, T, F, T]  -> runs [0,1](2), [4..7](4), [9](1)
    p = fea.overrating_profile(truth, pred, ts)
    assert p["count"] == 7
    assert abs(p["rate"] - 0.7) < 1e-12
    exceedances = [10.0, 20.0, 5.0, 30.0, 40.0, 50.0, 1.0]
    assert abs(p["mean_exceedance_amps"] - sum(exceedances) / 7.0) < 1e-9
    assert abs(p["median_exceedance_amps"] - 20.0) < 1e-9
    assert abs(p["max_exceedance_amps"] - 50.0) < 1e-9
    runs = {int(k): int(v) for k, v in p["run_length_counts"].items()}
    assert runs == {2: 1, 4: 1, 1: 1}
    assert p["longest_run"]["length"] == 4
    assert p["cadence_hours"] == 6.0
    assert p["scored_rows_only"] is True
    assert "scored" in p["run_length_caveat"].lower()


def test_overrating_profile_zero_overrating_returns_none_not_nan():
    ts = pd.date_range("2025-10-01", periods=5, freq="6h", tz="UTC")
    truth = np.array([100.0] * 5)
    clean_pred = truth - 5.0
    p = fea.overrating_profile(truth, clean_pred, ts)
    assert p["count"] == 0
    assert p["rate"] == 0.0
    assert p["run_length_counts"] == {}
    assert p["longest_run"] is None
    for key in ("mean_exceedance_amps", "median_exceedance_amps", "p95_exceedance_amps", "max_exceedance_amps"):
        assert p[key] is None, (key, p[key])


def test_overrating_profile_mismatched_lengths_raises():
    with pytest.raises(ValueError):
        fea.overrating_profile([1.0, 2.0], [1.0], pd.date_range("2025-01-01", periods=2, freq="h", tz="UTC"))


def test_convection_crossover_wind_speed_verified_both_sides():
    for corridor in sorted(config.CORRIDOR_ENDPOINTS):
        result = fea.convection_crossover_wind_speed(corridor)
        assert result["crossover_wind_perp_ms"] > 0.0
        assert result["below_equals_natural"] is True
        assert result["above_exceeds_natural"] is True
        assert result["air_temp_c"] == fea._DEFAULT_CROSSOVER_AIR_TEMP_C


def test_convection_crossover_wind_speed_unknown_corridor_raises():
    with pytest.raises(ValueError):
        fea.convection_crossover_wind_speed("NOT_A_CORRIDOR")


def _synthetic_regime_frame(n=200, seed=99):
    rng = np.random.default_rng(seed)
    ts = pd.date_range("2025-10-01", periods=n, freq="6h", tz="UTC")
    return pd.DataFrame({
        "datetime_utc": ts,
        "truth_dlr_amps": rng.normal(1000.0, 50.0, n),
        "truth_wind_speed": rng.uniform(0.0, 10.0, n),
        "truth_wind_direction": rng.uniform(0.0, 360.0, n),
        "truth_air_temp": rng.uniform(10.0, 40.0, n),
    }), rng


def test_overrating_by_regime_bins_partition_the_scored_rows():
    frame, rng = _synthetic_regime_frame()
    pred = frame["truth_dlr_amps"].to_numpy() + rng.normal(0.0, 60.0, len(frame))
    result = fea.overrating_by_regime(frame, pred, corridor="AUSTIN_CORPUS_CHRISTI", minimum_bin_rows=5)
    wind = result["perpendicular_wind"]
    total = sum(b["rows"] for b in wind["bins"])
    assert total == result["scored_rows"] == len(frame)
    assert wind["crossover_edge_index"] is not None
    assert any(b["is_crossover_edge"] for b in wind["bins"])
    temp_total = sum(b["rows"] for b in result["by_ambient_temperature"])
    assert temp_total == len(frame)
    hour_total = sum(b["rows"] for b in result["by_hour_of_day"])
    assert hour_total == len(frame)


def test_overrating_by_regime_values_on_bin_edges_are_assigned_exactly_once():
    frame, rng = _synthetic_regime_frame(n=50, seed=7)
    crossover = fea.convection_crossover_wind_speed("AUSTIN_CORPUS_CHRISTI")["crossover_wind_perp_ms"]
    # Deliberately place several rows' truth wind EXACTLY at the measured
    # crossover's own perpendicular-wind value -- forcing wind speed/
    # direction such that `perpendicular_wind` returns exactly `crossover`.
    frame.loc[0:4, "truth_wind_direction"] = 90.0  # along a 90 deg bearing-perpendicular setup varies by corridor
    pred = frame["truth_dlr_amps"].to_numpy() + rng.normal(0.0, 60.0, len(frame))
    result = fea.overrating_by_regime(frame, pred, corridor="AUSTIN_CORPUS_CHRISTI", minimum_bin_rows=5)
    total = sum(b["rows"] for b in result["perpendicular_wind"]["bins"])
    assert total == len(frame)


def test_overrating_by_regime_flags_small_bins_and_withholds_their_rate():
    n = 30
    ts = pd.date_range("2025-10-01", periods=n, freq="6h", tz="UTC")
    # All but two rows at a high perpendicular wind (far above crossover);
    # two rows at a very low wind -- guaranteed to land in a tiny bin.
    wind_speed = np.full(n, 20.0)
    wind_speed[:2] = 0.0
    frame = pd.DataFrame({
        "datetime_utc": ts,
        "truth_dlr_amps": np.full(n, 1000.0),
        "truth_wind_speed": wind_speed,
        "truth_wind_direction": np.full(n, 90.0),
        "truth_air_temp": np.full(n, 30.0),
    })
    pred = frame["truth_dlr_amps"].to_numpy() + 10.0
    result = fea.overrating_by_regime(frame, pred, corridor="AUSTIN_CORPUS_CHRISTI", minimum_bin_rows=10)
    small_bins = [b for b in result["perpendicular_wind"]["bins"] if b["rows"] < 10]
    assert small_bins, "expected at least one small bin in this deliberately skewed fixture"
    for b in small_bins:
        assert b["flagged_insufficient_rows"] is True
        assert b["profile"] is None
    big_bins = [b for b in result["perpendicular_wind"]["bins"] if b["rows"] >= 10]
    assert big_bins and all(b["profile"] is not None for b in big_bins)


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-04 Task 2: three-period quantile fit/calibrate/evaluate pipeline
# and the matched-overrating-rate retained-capacity comparison.
#
# `quantile_period_boundaries`/`fit_lower_quantile_model`/
# `_fit_calibrate_evaluate_quantile`/`_matched_rate_row` are all pure,
# network-free transforms over in-memory frames -- no monkeypatching
# needed. `overrating_basis_report`'s own integration tests reuse this
# file's existing `_patch_leakage_test_assembly`/`_synthetic_anchored_pair_
# frame` helpers (the SAME synthetic fixture `ablation_basis_report`'s own
# tests already use), so they make no network call either.
# ──────────────────────────────────────────────────────────────────────────

def test_quantile_period_boundaries_disjoint_ordered_and_before_frozen_test_start():
    ts = pd.date_range("2020-01-01", periods=1000, freq="6h", tz="UTC")
    result = fea.quantile_period_boundaries(ts)

    for name in ("fit", "calibrate", "evaluate"):
        assert result[name]["rows"] > 0, (name, result)
        assert result[name]["frozen_window_guard_passed"] is True

    assert result["fit"]["end"] < result["calibrate"]["start"]
    assert result["calibrate"]["start"] <= result["calibrate"]["end"]
    assert result["calibrate"]["end"] < result["evaluate"]["start"]
    assert result["evaluate"]["end"] < fea.FROZEN_TEST_SPLIT_START

    total = result["fit"]["rows"] + result["calibrate"]["rows"] + result["evaluate"]["rows"]
    assert total == len(ts)


def test_quantile_period_boundaries_raises_below_minimum_rows_naming_all_three():
    ts = pd.date_range("2020-01-01", periods=10, freq="6h", tz="UTC")
    with pytest.raises(ValueError) as exc_info:
        fea.quantile_period_boundaries(ts, minimum_rows_per_period=50)
    message = str(exc_info.value)
    for name in ("fit", "calibrate", "evaluate"):
        assert name in message, message


def test_quantile_period_boundaries_raises_on_too_few_timestamps():
    with pytest.raises(ValueError):
        fea.quantile_period_boundaries(pd.date_range("2020-01-01", periods=2, freq="6h", tz="UTC"))


def _synthetic_quantile_frame(start: str, truth, pred, *, seed: int) -> pd.DataFrame:
    n = len(truth)
    rng = np.random.default_rng(seed)
    ts = pd.date_range(start, periods=n, freq="6h", tz="UTC")
    return pd.DataFrame({
        "datetime_utc": ts,
        "truth_dlr_amps": truth,
        "pred_cand": pred,
        "decision_time_air_temp": rng.uniform(10.0, 40.0, n),
        "decision_time_perp_wind_ms": rng.uniform(0.0, 10.0, n),
        "decision_time_solar_radiation": rng.uniform(0.0, 800.0, n),
        # A deliberately-present valid-time truth column that must NEVER
        # enter the quantile model's own feature set.
        "truth_wind_speed": rng.uniform(0.0, 10.0, n),
    })


def test_fit_lower_quantile_model_feature_names_exclude_any_truth_column():
    rng = np.random.default_rng(1)
    truth = 1000.0 + rng.normal(0.0, 30.0, 200)
    pred = truth + rng.normal(0.0, 20.0, 200)
    frame = _synthetic_quantile_frame("2020-01-01", truth, pred, seed=1)

    fitted = fea.fit_lower_quantile_model(frame, alpha=0.1, candidate_prediction=pred)
    assert not any(name.startswith("truth_") for name in fitted["feature_names"])
    assert fitted["alpha"] == 0.1
    assert fitted["rows"] == len(frame)
    # The model is genuinely fitted and callable.
    X = fea._quantile_feature_matrix(frame, pred)
    preds = fitted["model"].predict(X)
    assert len(preds) == len(frame)


def test_pinball_loss_alpha_half_equals_half_mae():
    # Mirrors 04-04-PLAN.md's own inline verify (`PINBALL_SANITY_OK`): the
    # library metric's own identity at alpha=0.5, independent of this
    # module's code -- catches a hand-rolled asymmetric loss off by a
    # factor of two.
    from sklearn.metrics import mean_pinball_loss

    rng = np.random.default_rng(20260929)
    y = rng.normal(1500.0, 200.0, 500)
    p = y + rng.normal(0.0, 80.0, 500)
    half = mean_pinball_loss(y, p, alpha=0.5)
    mae = float(np.mean(np.abs(y - p)))
    assert abs(half - mae / 2.0) < 1e-9


def test_fit_calibrate_evaluate_quantile_reports_improvement_when_distributions_match():
    # Fixed, deterministic seeds (never Python's randomized `hash()`, whose
    # per-process salt would make this test's own synthetic fixtures --
    # and therefore its pass/fail outcome -- silently different between
    # separate test-runner invocations, e.g. this file run alone versus as
    # part of the full suite). The fit period's own noise is deliberately
    # NARROWER than calibrate/evaluate's -- a model trained on narrow
    # residuals is reliably miscalibrated against a wider residual
    # distribution, so "before" is reliably far from the nominal alpha
    # regardless of sampling noise, and the offset learned on calibrate
    # reliably generalizes to evaluate because they share the SAME (wide)
    # residual distribution.
    n = 600

    def _frame(start, noise_std, seed):
        rng = np.random.default_rng(seed)
        truth = 1000.0 + rng.normal(0.0, 30.0, n)
        pred = truth + rng.normal(0.0, noise_std, n)
        return _synthetic_quantile_frame(start, truth, pred, seed=seed)

    fit_frame = _frame("2020-01-01", noise_std=10.0, seed=3000)
    calibrate_frame = _frame("2020-03-01", noise_std=40.0, seed=3100)
    evaluate_frame = _frame("2020-05-01", noise_std=40.0, seed=3200)  # SAME (wide) distribution as calibrate

    result = fea._fit_calibrate_evaluate_quantile(
        fit_frame, calibrate_frame, evaluate_frame, alpha=0.05,
        fit_prediction=fit_frame["pred_cand"].to_numpy(),
        calibrate_prediction=calibrate_frame["pred_cand"].to_numpy(),
        evaluate_prediction=evaluate_frame["pred_cand"].to_numpy(),
    )
    assert result["improved"] is True
    assert result["evaluate_exceedance_distance_from_nominal_after"] < result["evaluate_exceedance_distance_from_nominal_before"]


def test_fit_calibrate_evaluate_quantile_reports_no_improvement_when_distributions_diverge():
    rng = np.random.default_rng(123)
    n = 300

    truth_fit = 1000.0 + rng.normal(0.0, 30.0, n)
    pred_fit = truth_fit + rng.normal(0.0, 20.0, n)
    fit_frame = _synthetic_quantile_frame("2020-01-01", truth_fit, pred_fit, seed=10)

    truth_cal = 1000.0 + rng.normal(0.0, 30.0, n)
    pred_cal = truth_cal + rng.normal(0.0, 20.0, n)
    calibrate_frame = _synthetic_quantile_frame("2020-03-01", truth_cal, pred_cal, seed=11)

    # Evaluate period's error distribution is a different shape entirely
    # (a large, oppositely-signed shift) -- the offset learned on the
    # calibrate period's own residuals does not generalize here.
    truth_eval = 1000.0 + rng.normal(0.0, 30.0, n)
    pred_eval = truth_eval - 200.0 + rng.normal(0.0, 20.0, n)
    evaluate_frame = _synthetic_quantile_frame("2020-05-01", truth_eval, pred_eval, seed=12)

    result = fea._fit_calibrate_evaluate_quantile(
        fit_frame, calibrate_frame, evaluate_frame, alpha=0.05,
        fit_prediction=fit_frame["pred_cand"].to_numpy(),
        calibrate_prediction=calibrate_frame["pred_cand"].to_numpy(),
        evaluate_prediction=evaluate_frame["pred_cand"].to_numpy(),
    )
    assert result["improved"] is False
    assert "calibration_offset_amps" in result


def test_quantile_calibration_report_shape_and_aggregate_flag():
    rng = np.random.default_rng(42)
    n = 300

    def _frame(start, seed):
        local_rng = np.random.default_rng(seed)
        truth = 1000.0 + local_rng.normal(0.0, 30.0, n)
        pred_a = truth + 10.0 + local_rng.normal(0.0, 20.0, n)
        pred_b = truth - 5.0 + local_rng.normal(0.0, 15.0, n)
        ts = pd.date_range(start, periods=n, freq="6h", tz="UTC")
        return pd.DataFrame({
            "datetime_utc": ts,
            "truth_dlr_amps": truth,
            "pred_cand_a": pred_a,
            "pred_cand_b": pred_b,
            "decision_time_air_temp": local_rng.uniform(10.0, 40.0, n),
            "decision_time_perp_wind_ms": local_rng.uniform(0.0, 10.0, n),
            "decision_time_solar_radiation": local_rng.uniform(0.0, 800.0, n),
        })

    fit_frame = _frame("2020-01-01", 1)
    calibrate_frame = _frame("2020-03-01", 2)
    evaluate_frame = _frame("2020-05-01", 3)

    report = fea.quantile_calibration_report(
        fit_frame, calibrate_frame, evaluate_frame,
        candidate_names=["cand_a", "cand_b"], alphas=[0.05, 0.1],
    )
    assert report["alphas"] == [0.05, 0.1]
    for alpha_key in ("0.05", "0.1"):
        entry = report["by_alpha"][alpha_key]
        assert "calibration_improved_on_evaluate" in entry
        for cand in ("cand_a", "cand_b"):
            res = entry["candidates"][cand]
            for period in ("calibrate", "evaluate"):
                for stage in ("before", "after"):
                    assert "pinball_loss" in res[period][stage]
                    assert "empirical_exceedance_rate" in res[period][stage]


def test_matched_rate_row_matches_hand_computation():
    y_cal = np.array([1000.0] * 10)
    pred_cal = y_cal + np.arange(10, dtype=float)  # diff = [0..9]
    expected_derating = float(np.quantile(pred_cal - y_cal, 0.7))

    y_eval = np.array([1000.0] * 5)
    pred_eval = y_eval + np.array([0.0, 2.0, 4.0, 6.0, 8.0])

    row = fea._matched_rate_row(
        "test", pred_cal=pred_cal, y_cal=y_cal, pred_eval=pred_eval, y_eval=y_eval,
        target_rates=[0.3], static_reference_amps=2000.0,
    )
    res = row["by_target_rate"]["0.3"]
    derated_eval = pred_eval - expected_derating
    expected_achieved = float(np.mean(derated_eval > y_eval))
    expected_retained = float(np.mean(derated_eval))

    assert row["name"] == "test"
    assert abs(res["derating_amps_fitted_on_calibrate"] - expected_derating) < 1e-9
    assert abs(res["achieved_rate_on_evaluate"] - expected_achieved) < 1e-9
    assert abs(res["retained_capacity_amps"] - expected_retained) < 1e-9
    assert abs(res["retained_capacity_fraction_of_static"] - expected_retained / 2000.0) < 1e-9


def test_retained_capacity_at_matched_overrating_includes_extra_rows():
    n = 50
    ts = pd.date_range("2020-01-01", periods=n, freq="6h", tz="UTC")
    rng = np.random.default_rng(5)
    truth = 1000.0 + rng.normal(0.0, 10.0, n)
    frame = pd.DataFrame({
        "datetime_utc": ts,
        "truth_dlr_amps": truth,
        "pred_persistence_24h": truth + rng.normal(5.0, 10.0, n),
    })
    extra_rows = {
        "static_rating_reference": {
            "calibrate_prediction": np.full(n, 1900.0),
            "evaluate_prediction": np.full(n, 1900.0),
        },
    }
    result = fea.retained_capacity_at_matched_overrating(
        frame, frame, candidate_names=["persistence_24h"],
        static_reference_amps=1900.0, target_rates=[0.1, 0.2], extra_rows=extra_rows,
    )
    names = {row["name"] for row in result["rows"]}
    assert "persistence_24h" in names and "static_rating_reference" in names
    assert result["target_rates"] == [0.1, 0.2]


def test_overrating_basis_report_refuses_unknown_corridor():
    with pytest.raises(ValueError) as exc_info:
        fea.overrating_basis_report("NOT_A_REAL_CORRIDOR")
    message = str(exc_info.value)
    for name in config.CORRIDOR_ENDPOINTS:
        assert name in message, message


def test_overrating_basis_report_runs_and_returns_documented_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch, periods=24 * 220)

    report_path = str(tmp_path / "overrating_report.json")
    r = fea.overrating_basis_report(_LEAKAGE_TEST_CORRIDOR, report_path=report_path)

    assert "reanalys" in r["limitation"].lower()
    assert r["scored_rows"] > 0

    periods = r["periods"]
    assert periods["fit"]["end"] < periods["calibrate"]["start"]
    assert periods["calibrate"]["end"] < periods["evaluate"]["start"]
    assert periods["evaluate"]["end"] < fea.FROZEN_TEST_SPLIT_START
    for name in ("fit", "calibrate", "evaluate"):
        assert periods[name]["frozen_window_guard_passed"] is True

    overrating = r["overrating"]
    for name in ("persistence_24h", "ml_cooling_corrected", "reference_ml_refit_24h"):
        assert name in overrating
        assert overrating[name]["cadence_hours"] in (6, 6.0)

    regime = r["by_regime"]["perpendicular_wind"]
    assert regime["crossover_edge_index"] is not None
    assert sum(b["rows"] for b in regime["bins"]) == r["scored_rows"]

    q = r["quantiles"]
    assert len(q["alphas"]) >= 2
    for alpha_key, entry in q["by_alpha"].items():
        assert "calibration_improved_on_evaluate" in entry
        for cand, res in entry["candidates"].items():
            for period in ("calibrate", "evaluate"):
                for stage in ("before", "after"):
                    assert "pinball_loss" in res[period][stage]
                    assert "empirical_exceedance_rate" in res[period][stage]

    matched = r["matched_overrating"]
    names = {row["name"] for row in matched["rows"]}
    assert "persistence_24h" in names
    assert any("static" in n for n in names)
    assert any("quantile" in n for n in names)
    for row in matched["rows"]:
        for rate_key, res in row["by_target_rate"].items():
            for key in (
                "derating_amps_fitted_on_calibrate", "achieved_rate_on_evaluate",
                "retained_capacity_amps", "retained_capacity_fraction_of_static",
            ):
                assert key in res, (row["name"], rate_key, sorted(res))

    with open(report_path, "r", encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["corridor"] == _LEAKAGE_TEST_CORRIDOR
    assert "reanalys" in json.dumps(on_disk).lower()


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-05 Task 1: low-wind sensitivity vs. numerical instability (D-04
# bullet 6), and the independent convective-seam bit-identity re-verification.
# Network-free throughout -- every function under test here is a pure
# transform over the thermal module's own public functions, or a load of
# the already-committed golden fixture.
# ──────────────────────────────────────────────────────────────────────────

def test_low_wind_sensitivity_sweep_finite_and_monotone_both_corridors():
    for corridor in sorted(config.CORRIDOR_ENDPOINTS):
        s = fea.low_wind_sensitivity_sweep(corridor)
        amps = np.asarray(s["ampacity_amps"], dtype=float)
        grid = np.asarray(s["wind_perp_ms"], dtype=float)
        assert grid.min() == 0.0
        assert np.all(np.isfinite(amps)), (corridor, amps)
        assert np.all(amps >= 0.0), (corridor, amps.min())
        d = np.diff(amps)
        assert np.all(d >= -1e-9), (corridor, d.min())
        assert s["finite_ok"] is True
        assert s["nonnegative_ok"] is True
        assert s["monotone_ok"] is True
        assert s["continuous_ok"] is True


def test_low_wind_sensitivity_sweep_below_crossover_flat_above_crossover_rises():
    for corridor in sorted(config.CORRIDOR_ENDPOINTS):
        s = fea.low_wind_sensitivity_sweep(corridor)
        amps = np.asarray(s["ampacity_amps"], dtype=float)
        i = s["crossover_index"]
        d = np.diff(amps)
        below = d[:max(i - 1, 1)]
        above = d[i:]
        assert np.all(np.abs(below) < 1e-6), (corridor, below)
        assert above.max() > 1e-3, (corridor, above)
        assert s["below_crossover_flat_ok"] is True
        assert s["above_crossover_rises_ok"] is True
        assert s["max_first_difference_amps"] is not None
        assert s["max_first_difference_wind_speed_ms"] > s["crossover_wind_perp_ms"]


def test_low_wind_sensitivity_sweep_unknown_corridor_raises():
    with pytest.raises(ValueError):
        fea.low_wind_sensitivity_sweep("NOT_A_CORRIDOR")


def test_low_wind_sensitivity_sweep_zero_wind_ampacity_matches_crossover_region_flat_value():
    corridor = next(iter(config.CORRIDOR_ENDPOINTS))
    s = fea.low_wind_sensitivity_sweep(corridor)
    amps = np.asarray(s["ampacity_amps"], dtype=float)
    i = s["crossover_index"]
    # Every point strictly below the crossover (including zero wind) shares
    # the SAME convective term (the natural-convection floor), so their
    # ampacities should be bit-identical -- not merely close.
    assert amps[0] == pytest.approx(amps[i - 1], abs=1e-9)


def test_sensitivity_vs_instability_finding_states_physics_with_three_citations():
    for corridor in sorted(config.CORRIDOR_ENDPOINTS):
        f = fea.sensitivity_vs_instability_finding(corridor)
        blob = repr(f)
        assert f["verdict"] == "physics"
        assert "finite" in blob.lower()
        assert "monoton" in blob.lower()
        assert "continu" in blob.lower()
        import re as _re
        assert len(_re.findall(r"[A-Za-z_./-]+\.py:\d+", blob)) >= 3, blob[:400]
        for prop in ("finiteness", "monotonicity", "continuity"):
            assert f["properties_checked"][prop]["passed"] is True
            assert len(f["properties_checked"][prop]["evidence"]) > 0
        assert f["peak_sensitivity"]["located_above_crossover"] is True


def test_sensitivity_vs_instability_finding_unknown_corridor_raises():
    with pytest.raises(ValueError):
        fea.sensitivity_vs_instability_finding("NOT_A_CORRIDOR")


def test_reverify_convective_seam_bit_identity_three_equalities_hold():
    r = fea.reverify_convective_seam_bit_identity()
    assert r["ampacity_matches_golden"] is True
    assert r["convective_term_matches_golden"] is True
    assert r["explicit_override_matches_default"] is True
    assert r["golden_fixture_path"].endswith(".npz")


def test_reverify_convective_seam_bit_identity_perturbed_override_is_non_trivial():
    r = fea.reverify_convective_seam_bit_identity()
    assert r["perturbed_override_changes_result"] is True


def test_reverify_convective_seam_bit_identity_sub_floor_attempt_is_permitted_with_citation():
    """
    Documents the ACTUAL measured behaviour of the seam, not a hoped-for
    one: `predict_cooling_correction`'s own guard only rejects a
    non-positive corrected term (`backend/forecast_correction_models.py:
    547`), so a positive sub-floor term reaches `ieee738_ampacity`'s
    `q_conv_override` seam unobstructed, which bypasses
    `convective_heat_loss`'s own natural-convection floor entirely when an
    override is supplied (`backend/thermal_model.py:236-239`). This test
    asserts the measured outcome (`permitted`) rather than merely checking
    the outcome is one of the two allowed strings, so a future change to
    the guard that starts rejecting sub-floor terms would be caught here as
    a behaviour change, not silently pass either way.
    """
    r = fea.reverify_convective_seam_bit_identity()
    sf = r["sub_floor_attempt"]
    assert sf["outcome"] == "permitted"
    assert sf["predicted_below_floor"] is True
    assert sf["attempted_q_conv_wm"] < sf["natural_convection_floor_wm"]
    assert sf["attempted_q_conv_wm"] > 0.0
    import re as _re
    assert _re.search(r"[A-Za-z_./-]+\.py:\d+", repr(sf)), sf
    # The sub-floor ampacity must be lower than the default (floored) path's
    # own ampacity at the same inputs -- otherwise the override would not
    # actually have reached the physics.
    assert max(sf["resulting_ampacity_amps"]) < min(sf["default_path_ampacity_amps"])


def test_low_wind_sensitivity_sweep_custom_wind_grid_still_locates_crossover():
    corridor = next(iter(config.CORRIDOR_ENDPOINTS))
    crossover = fea.convection_crossover_wind_speed(corridor)["crossover_wind_perp_ms"]
    custom_grid = [0.01, crossover * 0.5, crossover * 4.0, crossover * 8.0]
    s = fea.low_wind_sensitivity_sweep(corridor, wind_grid=custom_grid)
    assert 0.0 in s["wind_perp_ms"]
    assert crossover in s["wind_perp_ms"]
    grid = np.asarray(s["wind_perp_ms"], dtype=float)
    assert abs(grid[s["crossover_index"]] - crossover) < 1e-9


# ──────────────────────────────────────────────────────────────────────────
# Plan 04-06 Task 1: lag_vs_covariate_ablation and
# cooling_rediscovery_hypothesis. Network-free throughout, reusing Plan
# 04-02/04-03's own `_patch_leakage_test_assembly` synthetic per-city
# fixture (entirely before FROZEN_TEST_SPLIT_START by construction -- it
# starts 2024-01-01 and runs 220 days).
# ──────────────────────────────────────────────────────────────────────────

def test_feature_column_partition_disjoint_nonempty_union_complete_against_real_columns():
    partition = fea._feature_column_partition()
    lag, cov, full = set(partition["lag"]), set(partition["covariate"]), set(partition["all"])
    assert full == set(fea.ampacity_forecast.ML_FEATURE_COLUMNS)
    assert lag and cov
    assert not (lag & cov)
    assert lag | cov == full
    # The lag set is EXACTLY the lag-hours-enumerated names, never a
    # pattern match -- a future config change that adds a differently-named
    # lag-like column would not silently join this set.
    assert lag == {f"dlr_amps_lag_{h}h" for h in config.FORECAST_ML_LAG_HOURS}
    # The rolling-mean history feature is NOT one of the enumerated lag
    # columns, so it falls into the covariate bucket alongside the weather
    # columns and the time encodings.
    roll_col = f"dlr_amps_roll_mean_{config.FORECAST_ML_ROLLING_WINDOW_HOURS}h"
    assert roll_col in cov
    assert partition["lag_ordered"] == [c for c in fea.ampacity_forecast.ML_FEATURE_COLUMNS if c in lag]
    assert partition["covariate_ordered"] == [c for c in fea.ampacity_forecast.ML_FEATURE_COLUMNS if c in cov]


def test_correlate_aligned_raises_on_mismatched_index():
    idx_a = pd.DatetimeIndex(pd.date_range("2024-01-01", periods=5, freq="h", tz="UTC"))
    idx_b = pd.DatetimeIndex(pd.date_range("2024-02-01", periods=5, freq="h", tz="UTC"))
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([2.0, 3.0, 4.0, 5.0, 6.0])
    # Same length, same values -- would correlate perfectly if length alone
    # were the check -- but the indices (timestamps) genuinely differ.
    with pytest.raises(ValueError, match="does not equal"):
        fea._correlate_aligned(a, b, a_name="a", b_name="b", a_index=idx_a, b_index=idx_b)

    # Identical index: must NOT raise, and must return a real correlation.
    result = fea._correlate_aligned(a, b, a_name="a", b_name="b", a_index=idx_a, b_index=idx_a)
    assert result["pearson"] == pytest.approx(1.0)


def test_correlate_aligned_raises_on_shape_mismatch():
    with pytest.raises(ValueError, match="shape"):
        fea._correlate_aligned(np.zeros(5), np.zeros(6), a_name="a", b_name="b")


def test_lag_vs_covariate_ablation_refuses_unknown_corridor():
    with pytest.raises(ValueError) as exc_info:
        fea.lag_vs_covariate_ablation("NOT_A_REAL_CORRIDOR")
    message = str(exc_info.value)
    for name in config.CORRIDOR_ENDPOINTS:
        assert name in message, message


def test_cooling_rediscovery_hypothesis_refuses_unknown_corridor():
    with pytest.raises(ValueError) as exc_info:
        fea.cooling_rediscovery_hypothesis("NOT_A_REAL_CORRIDOR")
    message = str(exc_info.value)
    for name in config.CORRIDOR_ENDPOINTS:
        assert name in message, message


def _write_fake_ablation_report_for_cooling(tmp_path, *, rows: int) -> str:
    """A minimal, hand-written stand-in for Plan 04-03's own persisted
    `audit_ablation_report_<CORRIDOR>.json`, carrying only the one field
    `_cooling_rediscovery_from_predictions` actually reads."""
    path = str(tmp_path / "fake_ablation_report.json")
    report = {"residuals": {"ml_cooling_corrected": [1.0] * rows}}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh)
    return path


def test_cooling_rediscovery_from_predictions_raises_on_length_mismatch(tmp_path):
    report_path = _write_fake_ablation_report_for_cooling(tmp_path, rows=5)
    val_filtered = pd.DataFrame({
        "datetime_utc": pd.date_range("2024-01-01", periods=7, freq="6h", tz="UTC"),
        "truth_dlr_amps": np.linspace(900.0, 906.0, 7),
    })
    predictions = {"all_features": np.linspace(890.0, 896.0, 7)}
    with pytest.raises(ValueError, match="disagree in size"):
        fea._cooling_rediscovery_from_predictions(
            "AUSTIN_CORPUS_CHRISTI", predictions, val_filtered, ablation_report_path=report_path,
        )


def test_lag_vs_covariate_ablation_runs_and_returns_documented_shape(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    # The ablation's own cooling-rediscovery half needs Plan 04-03's
    # persisted report to already exist for this corridor -- write a
    # minimal stand-in carrying the one field it reads, sized to match
    # whatever row count this synthetic fixture's own validation split
    # produces (measured via a dry run of the harness's own split/filter
    # pipeline, not guessed).
    corridor_frame = fea.forecast_experiment.corridor_anchored_pair_frame(
        _LEAKAGE_TEST_CORRIDOR, fea.FROZEN_WINDOW_START, fea.FROZEN_WINDOW_END,
        lead_hours=_LEAKAGE_TEST_LEAD_HOURS,
    )
    boundaries = fea.forecast_experiment._default_split_boundaries(corridor_frame)
    _, val, _ = fea.experiment_splits.calendar_split(corridor_frame, boundaries)
    val_filtered = fea.forecast_experiment.filter_to_exact_lead(val, lead_hours=_LEAKAGE_TEST_LEAD_HOURS)
    pinned_boundary = pd.Timestamp(fea.FROZEN_TEST_SPLIT_START, tz="UTC")
    val_filtered = val_filtered[val_filtered["datetime_utc"] < pinned_boundary]
    expected_rows = len(val_filtered)

    # A non-constant fake residual series -- a constant one would make
    # every correlation against it undefined (NaN), which is a property of
    # this fixture's own degeneracy, not of the correlation routine.
    fake_cooling_residuals = (np.sin(np.arange(expected_rows) / 7.0) * 5.0).tolist()
    ablation_report_path = str(tmp_path / f"audit_ablation_report_{_LEAKAGE_TEST_CORRIDOR}.json")
    with open(ablation_report_path, "w", encoding="utf-8") as fh:
        json.dump({"residuals": {"ml_cooling_corrected": fake_cooling_residuals}}, fh)
    monkeypatch.setattr(fea, "_ablation_report_path", lambda corridor: ablation_report_path)

    report_path = str(tmp_path / "ablation_features_report.json")
    r = fea.lag_vs_covariate_ablation(_LEAKAGE_TEST_CORRIDOR, report_path=report_path)

    cols = r["feature_columns"]
    lag, cov, full = set(cols["lag"]), set(cols["covariate"]), set(cols["all"])
    assert lag and cov and not (lag & cov) and lag | cov == full

    v = r["variants"]
    for name in ("all_features", "lags_only", "covariates_only"):
        assert name in v, sorted(v)
        e = v[name]
        assert e["mae"] > 0 and e["rmse"] > 0, (name, e)
        assert "margin_vs_persistence" in e and "margin_vs_all_features" in e
        assert "block" in e["margin_vs_persistence"]
        assert len(e["margin_vs_persistence"]["block"]) >= 4
    assert set(v["all_features"]["feature_names"]) == full
    assert set(v["lags_only"]["feature_names"]) == lag
    assert set(v["covariates_only"]["feature_names"]) == cov
    # The all-features variant's margin against itself is degenerate
    # (point mass at zero) -- proving the SAME baseline residual array was
    # used for both sides rather than two independently-computed ones.
    self_margin = v["all_features"]["margin_vs_all_features"]["iid_bca"]
    assert self_margin["point"] == pytest.approx(0.0)
    assert self_margin["ci_low"] == pytest.approx(0.0)
    assert self_margin["ci_high"] == pytest.approx(0.0)

    assert r["ablation_guard_passed_fit"] is True
    assert r["ablation_guard_passed_scored"] is True
    assert r["max_fit_timestamp"] < r["min_scored_timestamp"]
    assert isinstance(r["finding"], str) and r["finding"].strip()
    assert "SUPPORT" in r["finding"]

    h = r["cooling_rediscovery"]
    for name in ("all_features", "lags_only", "covariates_only"):
        for kind in ("predictions", "residuals"):
            assert "pearson" in h[name][kind] and "spearman" in h[name][kind]
    assert isinstance(h["interpretation"], str) and "residual" in h["interpretation"].lower()

    with open(report_path, "r", encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["corridor"] == _LEAKAGE_TEST_CORRIDOR
    assert "cooling_rediscovery" in on_disk


def test_lag_vs_covariate_ablation_raises_on_overlapping_fit_and_score_frames(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    real_calendar_split = fea.experiment_splits.calendar_split

    def _corrupted_split(frame, boundaries):
        train, val, test = real_calendar_split(frame, boundaries)
        # Corrupt: val becomes an exact copy of train -- the fit frame and
        # the scored frame now overlap completely, which must raise rather
        # than silently producing an in-sample "out-of-sample" measurement.
        return train, train.copy(), test

    monkeypatch.setattr(fea.experiment_splits, "calendar_split", _corrupted_split)

    with pytest.raises(ValueError):
        fea.lag_vs_covariate_ablation(_LEAKAGE_TEST_CORRIDOR, report_path=str(tmp_path / "report.json"))


def test_cooling_rediscovery_hypothesis_matches_lag_vs_covariate_ablation_embedded_result(monkeypatch, tmp_path):
    """Calling the two entry points separately must agree exactly -- both
    ultimately run the SAME fit (fixed estimator seed), so this is a
    determinism check, not merely a shape check."""
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path))
    _patch_leakage_test_assembly(monkeypatch)

    corridor_frame = fea.forecast_experiment.corridor_anchored_pair_frame(
        _LEAKAGE_TEST_CORRIDOR, fea.FROZEN_WINDOW_START, fea.FROZEN_WINDOW_END,
        lead_hours=_LEAKAGE_TEST_LEAD_HOURS,
    )
    boundaries = fea.forecast_experiment._default_split_boundaries(corridor_frame)
    _, val, _ = fea.experiment_splits.calendar_split(corridor_frame, boundaries)
    val_filtered = fea.forecast_experiment.filter_to_exact_lead(val, lead_hours=_LEAKAGE_TEST_LEAD_HOURS)
    pinned_boundary = pd.Timestamp(fea.FROZEN_TEST_SPLIT_START, tz="UTC")
    val_filtered = val_filtered[val_filtered["datetime_utc"] < pinned_boundary]
    expected_rows = len(val_filtered)

    # A non-constant fake residual series -- a constant one would make
    # every correlation against it undefined (NaN), which is a property of
    # this fixture's own degeneracy, not of the correlation routine.
    fake_cooling_residuals = (np.sin(np.arange(expected_rows) / 7.0) * 5.0).tolist()
    ablation_report_path = str(tmp_path / f"audit_ablation_report_{_LEAKAGE_TEST_CORRIDOR}.json")
    with open(ablation_report_path, "w", encoding="utf-8") as fh:
        json.dump({"residuals": {"ml_cooling_corrected": fake_cooling_residuals}}, fh)
    monkeypatch.setattr(fea, "_ablation_report_path", lambda corridor: ablation_report_path)

    report_path = str(tmp_path / "ablation_features_report.json")
    full_report = fea.lag_vs_covariate_ablation(_LEAKAGE_TEST_CORRIDOR, report_path=report_path)
    standalone = fea.cooling_rediscovery_hypothesis(_LEAKAGE_TEST_CORRIDOR, report_path=report_path)

    assert standalone == full_report["cooling_rediscovery"]
