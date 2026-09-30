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

import pandas as pd
import pytest

import config
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
