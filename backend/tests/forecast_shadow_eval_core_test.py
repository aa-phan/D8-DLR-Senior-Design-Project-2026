"""
Tests for `backend/forecast_shadow_eval_core.py` (quick task 261013-285,
Task 1): constants, the anti-peeking guard with its one-shot marker, the HTTP
evidence recorder, archive request/parse/truth, descriptive metrics,
provenance and the report writer.

Network-free: `requests.get` raises unless a test installs a fake. Every file
is written under `tmp_path`; nothing touches `data/`.

Plan 07-06 (protocol v4, signed 2026-11-02): the module defaults are the signed
round `v4-read1`, the guard is armed for every round (no override path for a
FRESH run) and the round constants are compared with the signing copy's
machine-checked registry.
"""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
import os
import re

import numpy as np
import pandas as pd
import pytest
import requests

import city_point
import config
import forecast_experiment_audit
import forecast_shadow_decision_v4
import forecast_shadow_eval_core as core
import forecast_shadow_pipeline
import open_meteo_forecast_provider
import open_meteo_provider
import protocol_v4_registry as reg
import thermal_model

FRESH_TIME = pd.Timestamp("2026-10-20T06:00:00Z")
DEV_TIME = pd.Timestamp("2026-04-10T06:00:00Z")
INSTANT = core.EVALUATION_INSTANT_DEFAULT


class _FakeResponse:
    def __init__(self, payload=None, status=200, raw=None):
        self.status_code = status
        self.content = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self.headers = {"Date": "Tue, 24 Nov 2026 00:00:01 GMT", "Content-Type": "application/json"}

    def json(self):
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _weather_at(ts: pd.Timestamp) -> dict:
    h = ts.hour + 24 * ts.dayofyear
    return {
        "temperature_2m": 20.0 + 8.0 * np.sin(2 * np.pi * ts.hour / 24) + (h % 3),
        "wind_speed_10m": 2.0 + (h % 7) * 0.5,
        "wind_direction_10m": float((h * 37) % 360),
        "shortwave_radiation": float(max(0.0, 700.0 * np.sin(np.pi * (ts.hour - 6) / 12))) if 6 <= ts.hour <= 18 else 0.0,
        "relative_humidity_2m": 55.0 + (h % 11),
    }


def archive_payload(start: str, end: str, *, null_hours=(), units=None) -> dict:
    times = pd.date_range(pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(hours=23), freq="h")
    hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}
    for key in open_meteo_provider.HOURLY_TO_PIPELINE:
        hourly[key] = [_weather_at(t.tz_localize("UTC"))[key] for t in times]
    for ts in null_hours:
        i = hourly["time"].index(pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M"))
        hourly["wind_speed_10m"][i] = None
    return {"hourly": hourly, "hourly_units": units or dict(open_meteo_provider.EXPECTED_HOURLY_UNITS)}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("requests.get must not be called in this test")
    monkeypatch.setattr(requests, "get", boom)


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

def test_constants_are_pinned():
    # v4-read1 is the default round (signed 2026-11-02); the retired v3 instant is kept only to be refused.
    assert core.EVALUATION_INSTANT_DEFAULT == pd.Timestamp("2026-11-01T00:00:00Z")
    assert core.VALID_TIME_CUTOFF_DEFAULT == pd.Timestamp("2026-10-25T00:00:00Z")
    assert core.V3_RETIRED_INSTANT == pd.Timestamp("2026-11-24T00:00:00Z")
    assert core.MODEL_FREEZE == pd.Timestamp("2026-11-01T00:00:00Z")
    assert core.FRESH_BASIS_START == pd.Timestamp(forecast_experiment_audit.FROZEN_WINDOW_END, tz="UTC") + pd.Timedelta(days=1)
    assert core.FROZEN_WINDOW_END_DATE == forecast_experiment_audit.FROZEN_WINDOW_END
    assert core.RECON_FETCH_START == "2026-09-28"
    assert core.RECON_FETCH_END == "2026-10-24"
    assert pd.Timestamp(core.RECON_FETCH_END, tz="UTC") == core.VALID_TIME_CUTOFF_DEFAULT - pd.Timedelta(days=1)
    assert (core.LEAD_HOURS, core.SLOT_HOURS, core.DECISION_GAP_HOURS) == (24, 6, (11, 17))
    assert core.SCORED_FORECAST_MODEL == open_meteo_forecast_provider.PREVIOUS_RUNS_MODEL_ID == "gfs_seamless"
    assert (core.TAIL_RATE_TARGET_ROWS, core.MDD_TARGET_ROWS) == (590, 1575)
    assert core.CANDIDATES == forecast_shadow_pipeline.CANDIDATE_METHOD_NAMES
    assert core.REAL_CANDIDATES == ("ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h")
    assert (core.DEFAULT_CHOICE, core.FALLBACK_CHOICE) == ("ml_wind_corrected", "raw_forecast")
    assert core.ROW_SOURCES == ("reconstructed_frames", "shadow_logs")
    assert core.HEADLINE_ROW_SOURCE == "reconstructed_frames"
    assert core.BLOCK_LENGTHS_SLOTS == (1, 4, 8, 28)
    assert core.N_RESAMPLES == 10000
    assert core.SEED == config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE == 20260929
    assert (core.MIN_PAIRED_ROWS, core.POWER, core.FAMILY_ALPHA) == (8, 0.8, 0.05)
    assert (core.DECISION_MARGIN_AMPS, core.CONSISTENCY_MIN_CITIES) == (5.0, 3)
    assert core.RELATIVE_MARGIN_FRACTION == 0.02 == forecast_shadow_decision_v4.RELATIVE_MARGIN_FRACTION
    assert "never sensor-validated" in core.TRUTH_LABEL
    assert "No 8% ceiling was applied" in core.NOT_MEASURED_STATEMENT
    assert len(core.PLANNER_DEFAULTS) == 18
    assert all(f"PD-{i:02d}" in core.PLANNER_DEFAULTS for i in range(1, 19))
    assert set(core.VALIDITY_FLAGS) == {f"V{i}" for i in range(1, 7)}
    assert core.VALIDITY_FLAGS["V4"]["applies_to"] == ["shadow_logs", "reconstructed_frames"]
    for fid in ("V1", "V2", "V3", "V5", "V6"):
        assert core.VALIDITY_FLAGS[fid]["applies_to"] == ["shadow_logs"]
        assert core.VALIDITY_FLAGS[fid]["not_applicable_reason"]


def test_headline_family_is_the_nine_fixed_pairs():
    fam = core.HEADLINE_FAMILY
    assert len(fam) == 9 == core.FAMILY_SIZE
    assert len(set(fam)) == 9
    assert all(a in core.REAL_CANDIDATES for a, _ in fam)
    assert sum(b in core.REAL_CANDIDATES for _, b in fam) == 3
    assert sum(b == "raw_forecast" for _, b in fam) == 3
    assert sum(b == "persistence_24h" for _, b in fam) == 3
    assert all(a != b for a, b in fam)


def test_round_half_up_to_hour():
    assert core.round_half_up_to_hour("2026-10-20T10:29:59Z") == pd.Timestamp("2026-10-20T10:00:00Z")
    assert core.round_half_up_to_hour("2026-10-20T10:30:00Z") == pd.Timestamp("2026-10-20T11:00:00Z")
    assert core.round_half_up_to_hour("2026-10-20T10:00:00Z") == pd.Timestamp("2026-10-20T10:00:00Z")


def test_core_does_not_import_the_frozen_audit_module():
    path = os.path.join(os.path.dirname(core.__file__), "forecast_shadow_eval_core.py")
    tree = ast.parse(open(path, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(a.name != "forecast_experiment_audit" for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "forecast_experiment_audit"


# --------------------------------------------------------------------------
# Guard
# --------------------------------------------------------------------------

def _guard(**kw):
    return core.GuardConfig(**kw)


def test_guard_refuses_fresh_before_instant_without_calling_network_or_creating_dirs(tmp_path):
    root = tmp_path / "evidence"
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="shadow_logs",
                         now=INSTANT - pd.Timedelta(seconds=1), evidence_root=str(root))
    assert not root.exists()


def test_guard_passes_at_the_instant_and_records_basis(tmp_path):
    rec = core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="shadow_logs", now=INSTANT,
                           evidence_root=str(tmp_path / "e"))
    assert rec["basis"] == "FRESH"
    assert rec["defaults_used"] is True and rec["override_reason"] is None
    assert rec["now_evaluated"] == INSTANT.isoformat()
    assert rec["evaluation_instant"] == INSTANT.isoformat()
    assert rec["valid_time_cutoff"] == core.VALID_TIME_CUTOFF_DEFAULT.isoformat()
    assert rec["prior_fresh_runs"] == []


def test_guard_override_text_no_longer_lets_a_fresh_run_through(tmp_path):
    # v4 (SEL-01, SEL-04): the old override path skipped both refusals; a FRESH run now takes no override.
    for now in (pd.Timestamp("2026-10-21T00:00:00Z"), INSTANT, INSTANT + pd.Timedelta(days=30)):
        with pytest.raises(core.EvaluationGuardError, match="take no override"):
            core.check_guard(_guard(override_reason="rehearsal for the owner"), valid_times=[FRESH_TIME],
                             row_source="shadow_logs", now=now, evidence_root=str(tmp_path / "e"))
    assert not (tmp_path / "e").exists()


def test_guard_override_text_is_still_recorded_for_a_development_run(tmp_path):
    rec = core.check_guard(_guard(override_reason="rehearsal for the owner"), valid_times=[DEV_TIME],
                           row_source="shadow_logs", now=pd.Timestamp("2026-10-21T00:00:00Z"),
                           evidence_root=str(tmp_path / "e"))
    assert rec["basis"] == "development" and rec["override_reason"] == "rehearsal for the owner"


def test_guard_blank_override_reason_is_not_an_override(tmp_path):
    # blank text is not an override: it neither passes a FRESH run early nor trips the no-override refusal
    with pytest.raises(core.EvaluationGuardError, match="evaluation instant"):
        core.check_guard(_guard(override_reason="   "), valid_times=[FRESH_TIME], row_source="shadow_logs",
                         now=pd.Timestamp("2026-10-21T00:00:00Z"), evidence_root=str(tmp_path / "e"))


def test_guard_development_times_are_scorable_at_any_time(tmp_path):
    rec = core.check_guard(_guard(), valid_times=[DEV_TIME], row_source="shadow_logs",
                           now=pd.Timestamp("2026-10-13T00:00:00Z"), evidence_root=str(tmp_path / "e"))
    assert rec["basis"] == "development"


def test_guard_fresh_basis_starts_exactly_at_2026_09_30(tmp_path):
    before = pd.Timestamp("2026-09-29T23:00:00Z")
    rec = core.check_guard(_guard(), valid_times=[before], row_source="shadow_logs",
                           now=pd.Timestamp("2026-10-01T00:00:00Z"), evidence_root=str(tmp_path / "e"))
    assert rec["basis"] == "development"
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(_guard(), valid_times=[core.FRESH_BASIS_START], row_source="shadow_logs",
                         now=pd.Timestamp("2026-10-01T00:00:00Z"), evidence_root=str(tmp_path / "e"))


@pytest.mark.parametrize("kwargs", [
    {"evaluation_instant": pd.Timestamp("2026-11-02T00:00:00Z")},
    {"valid_time_cutoff": pd.Timestamp("2026-10-24T00:00:00Z")},
])
def test_guard_nondefault_dates_need_an_override_and_never_pass_a_fresh_run(tmp_path, kwargs):
    with pytest.raises(ValueError):
        core.check_guard(_guard(**kwargs), valid_times=[DEV_TIME], row_source="shadow_logs", now=INSTANT,
                         evidence_root=str(tmp_path / "e"))
    rec = core.check_guard(_guard(override_reason="why", **kwargs), valid_times=[DEV_TIME],
                           row_source="shadow_logs", now=INSTANT, evidence_root=str(tmp_path / "e"))
    assert rec["defaults_used"] is False
    assert set(rec["nondefault_params"]) & {"evaluation_instant", "valid_time_cutoff"}
    # the same dates in a FRESH run: refused without an override (ValueError) and with one (guard error)
    with pytest.raises(ValueError):
        core.check_guard(_guard(**kwargs), valid_times=[FRESH_TIME], row_source="shadow_logs",
                         now=pd.Timestamp("2027-01-01T00:00:00Z"), evidence_root=str(tmp_path / "e"))
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(_guard(override_reason="why", **kwargs), valid_times=[FRESH_TIME],
                         row_source="shadow_logs", now=pd.Timestamp("2027-01-01T00:00:00Z"),
                         evidence_root=str(tmp_path / "e"))


def test_guard_cutoff_at_or_after_instant_is_refused_even_with_override(tmp_path):
    with pytest.raises(ValueError):
        core.check_guard(_guard(valid_time_cutoff=INSTANT, override_reason="x"), valid_times=[DEV_TIME],
                         row_source="shadow_logs", now=INSTANT, evidence_root=str(tmp_path / "e"))


def test_guard_nondefault_parameters_are_refused_in_fresh_runs_and_free_in_development(tmp_path):
    nd = core.nondefault_params({**core.default_params(), "n_resamples": 2000, "block_lengths": (1, 4)})
    assert nd == {"n_resamples": 2000, "block_lengths": [1, 4]}
    with pytest.raises(ValueError):
        core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="shadow_logs", now=INSTANT,
                         evidence_root=str(tmp_path / "e"), nondefault_params=nd)
    # no override text can help (PD-15, signed v4 rounds take no override)
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(_guard(override_reason="owner changed it"), valid_times=[FRESH_TIME],
                         row_source="shadow_logs", now=INSTANT, evidence_root=str(tmp_path / "e"),
                         nondefault_params=nd)
    # development runs may use any parameter without an override
    rec = core.check_guard(_guard(), valid_times=[DEV_TIME], row_source="shadow_logs", now=INSTANT,
                           evidence_root=str(tmp_path / "e"), nondefault_params=nd)
    assert rec["basis"] == "development" and rec["nondefault_params"] == nd


def test_nondefault_params_ignores_defaults_and_list_vs_tuple():
    assert core.nondefault_params(core.default_params()) == {}
    assert core.nondefault_params({"block_lengths": [1, 4, 8, 28]}) == {}
    assert core.nondefault_params(None) == {}


def test_one_shot_marker_blocks_a_second_fresh_run_even_without_a_report(tmp_path):
    root = str(tmp_path / "evidence")
    rec = core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="shadow_logs", now=INSTANT, evidence_root=root)
    path = core.new_evidence_dir(root, "shadow_logs", INSTANT, rec, {"x": 1})
    assert os.path.basename(path) == "shadow_logs_20261101T000000Z"
    first = os.listdir(path)
    assert first == ["run_started.json"]          # no report.json: the first run "crashed"
    marker = json.loads(open(os.path.join(path, "run_started.json")).read())
    assert marker["basis"] == "FRESH" and marker["row_source"] == "shadow_logs"
    assert marker["guard"]["now_evaluated"] == INSTANT.isoformat() and marker["config"] == {"x": 1}
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="shadow_logs",
                         now=INSTANT + pd.Timedelta(hours=1), evidence_root=root)
    # the old "override after a crash" path is gone: a second FRESH run is refused whatever text is given
    with pytest.raises(core.EvaluationGuardError, match="take no override"):
        core.check_guard(_guard(override_reason="rerun after crash"), valid_times=[FRESH_TIME],
                         row_source="shadow_logs", now=INSTANT + pd.Timedelta(hours=1), evidence_root=root)


def test_prior_run_of_the_other_row_source_does_not_block(tmp_path):
    root = str(tmp_path / "evidence")
    rec = core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="reconstructed_frames", now=INSTANT, evidence_root=root)
    core.new_evidence_dir(root, "reconstructed_frames", INSTANT, rec, {})
    rec2 = core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="shadow_logs", now=INSTANT, evidence_root=root)
    assert rec2["prior_fresh_runs"] == []


def test_development_marker_does_not_block_a_fresh_run(tmp_path):
    root = str(tmp_path / "evidence")
    rec = core.check_guard(_guard(), valid_times=[DEV_TIME], row_source="shadow_logs", now=INSTANT, evidence_root=root)
    core.new_evidence_dir(root, "shadow_logs", INSTANT - pd.Timedelta(days=1), rec, {})
    rec2 = core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="shadow_logs", now=INSTANT, evidence_root=root)
    assert rec2["prior_fresh_runs"] == []


def test_unreadable_marker_is_treated_as_a_prior_run(tmp_path):
    root = tmp_path / "evidence" / "shadow_logs_20261101T000000Z"
    root.mkdir(parents=True)
    (root / "run_started.json").write_text("{not json")
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(_guard(), valid_times=[FRESH_TIME], row_source="shadow_logs", now=INSTANT,
                         evidence_root=str(tmp_path / "evidence"))


def test_new_evidence_dir_refuses_a_same_second_collision(tmp_path):
    rec = {"basis": "development"}
    core.new_evidence_dir(str(tmp_path), "shadow_logs", INSTANT, rec, {})
    with pytest.raises(FileExistsError):
        core.new_evidence_dir(str(tmp_path), "shadow_logs", INSTANT, rec, {})


def test_unknown_row_source_is_refused(tmp_path):
    with pytest.raises(ValueError):
        core.check_guard(_guard(), valid_times=[DEV_TIME], row_source="corridor", now=INSTANT, evidence_root=str(tmp_path))


# --------------------------------------------------------------------------
# Signed protocol rounds (07-06, confirmation protocol v4)
# --------------------------------------------------------------------------

READ1_INSTANT = pd.Timestamp("2026-11-01T00:00:00Z")
READ2_INSTANT = pd.Timestamp("2026-11-08T00:00:00Z")
READ1_FRESH_TIME = pd.Timestamp("2026-10-24T18:00:00Z")      # the last scored slot of read 1
READ2_FRESH_TIME = pd.Timestamp("2026-10-31T18:00:00Z")      # the last scored slot of read 2


def test_rounds_match_the_signed_registry():
    registry = reg.parse_registry(reg.SIGNING_COPY_PATH)
    for key, rnd in (("read1", core.V4_READ1), ("read2", core.V4_READ2)):
        assert rnd.name == registry[f"{key}.name"]
        assert rnd.instant == reg.as_timestamp(registry[f"{key}.instant"])
        assert rnd.cutoff == reg.as_timestamp(registry[f"{key}.cutoff"])
        assert rnd.fetch_start == registry[f"{key}.fetch_start"]
        assert rnd.fetch_end == registry[f"{key}.fetch_end"]
        assert rnd.slots_per_city == int(registry[f"{key}.slots_per_city"])
        assert rnd.family_alpha == float(registry[f"{key}.family_alpha"])
        assert rnd.descriptive_only is False
        assert rnd.evidence_subdir == rnd.name
    late = core.V4_LATE_DESCRIPTIVE
    assert late.name == registry["late.name"]
    # the late-answer descriptive re-score reuses read 1's dates and only describes
    assert (late.instant, late.cutoff, late.fetch_start, late.fetch_end) == (
        core.V4_READ1.instant, core.V4_READ1.cutoff, core.V4_READ1.fetch_start, core.V4_READ1.fetch_end)
    assert late.descriptive_only is True and late.evidence_subdir == "v4-late-descriptive"
    assert core.V3_RETIRED_INSTANT == reg.as_timestamp(registry["v3_retired_instant"])
    assert core.FRESH_BASIS_START == reg.as_timestamp(registry["fresh_basis_start"])
    assert core.MODEL_FREEZE == reg.as_timestamp(registry["model_freeze"])
    assert core.RELATIVE_MARGIN_FRACTION == float(registry["rule.relative_margin_fraction"])
    assert core.PRE_REGISTERED_PARAM_DEFAULTS["relative_margin_fraction"] == core.RELATIVE_MARGIN_FRACTION
    assert core.CONSISTENCY_MIN_CITIES == int(registry["rule.consistency_min_cities"])
    assert core.FAMILY_SIZE == int(registry["rule.family_size"])
    assert list(core.BLOCK_LENGTHS_SLOTS) == [int(v) for v in reg.as_list(registry["rule.block_lengths"])]
    assert core.N_RESAMPLES == int(registry["rule.n_resamples"])


def test_slot_counts_follow_from_the_signed_windows():
    for rnd in (core.V4_READ1, core.V4_READ2):
        slots = pd.date_range(core.FRESH_BASIS_START, rnd.cutoff, freq=f"{core.SLOT_HOURS}h", inclusive="left")
        assert len(slots) == rnd.slots_per_city
        assert pd.Timestamp(rnd.fetch_end, tz="UTC") == rnd.cutoff - pd.Timedelta(days=1)
    assert (core.V4_READ1.slots_per_city, core.V4_READ2.slots_per_city) == (100, 128)


def test_the_registry_names_exactly_the_three_signed_rounds_and_read1_is_the_default():
    assert sorted(core.PROTOCOL_ROUNDS) == ["v4-late-descriptive", "v4-read1", "v4-read2"]
    assert all(core.PROTOCOL_ROUNDS[name].name == name for name in core.PROTOCOL_ROUNDS)
    assert core.DEFAULT_ROUND is core.V4_READ1
    assert core.EVALUATION_INSTANT_DEFAULT == core.DEFAULT_ROUND.instant
    assert core.VALID_TIME_CUTOFF_DEFAULT == core.DEFAULT_ROUND.cutoff
    assert (core.RECON_FETCH_START, core.RECON_FETCH_END) == (core.DEFAULT_ROUND.fetch_start, core.DEFAULT_ROUND.fetch_end)
    assert core.GuardConfig().round_name == "v4-read1"
    assert core.round_named("v4-read2") is core.V4_READ2


def test_a_protocol_round_cannot_be_edited():
    with pytest.raises(dataclasses.FrozenInstanceError):
        core.V4_READ1.instant = pd.Timestamp("2026-11-24T00:00:00Z")


def test_round_named_lists_the_three_names_for_anything_else():
    for bad in ("v3", "v4-read3", ""):
        with pytest.raises(KeyError) as err:
            core.round_named(bad)
        for name in ("v4-late-descriptive", "v4-read1", "v4-read2"):
            assert name in str(err.value)
    with pytest.raises(KeyError):
        core.guard_for_round("v3")


def test_round_evidence_root_is_one_subroot_per_round(tmp_path):
    base = str(tmp_path / "evaluation")
    roots = {name: core.round_evidence_root(base, core.round_named(name)) for name in core.PROTOCOL_ROUNDS}
    assert roots == {name: os.path.join(base, name) for name in core.PROTOCOL_ROUNDS}
    assert len(set(roots.values())) == 3
    assert core.EVIDENCE_ROOT_DEFAULT == os.path.join("data", "shadow", "evaluation")


def test_guard_for_round_carries_the_round_dates():
    g1, g2 = core.guard_for_round("v4-read1"), core.guard_for_round("v4-read2")
    assert (g1.round_name, g1.evaluation_instant, g1.valid_time_cutoff, g1.override_reason) == (
        "v4-read1", READ1_INSTANT, pd.Timestamp("2026-10-25T00:00:00Z"), None)
    assert (g2.round_name, g2.evaluation_instant, g2.valid_time_cutoff, g2.override_reason) == (
        "v4-read2", READ2_INSTANT, pd.Timestamp("2026-11-01T00:00:00Z"), None)
    assert core.guard_for_round("v4-late-descriptive").evaluation_instant == READ1_INSTANT


@pytest.mark.parametrize("name, instant, fresh_time", [
    ("v4-read1", READ1_INSTANT, READ1_FRESH_TIME),
    ("v4-read2", READ2_INSTANT, READ2_FRESH_TIME),
])
def test_a_round_is_refused_one_second_before_its_instant_and_runs_at_it_with_no_override(tmp_path, name, instant, fresh_time):
    root = tmp_path / "evidence"
    guard = core.guard_for_round(name)
    with pytest.raises(core.EvaluationGuardError, match="evaluation instant"):
        core.check_guard(guard, valid_times=[fresh_time], row_source="reconstructed_frames",
                         now=instant - pd.Timedelta(seconds=1), evidence_root=str(root))
    assert not root.exists()                                  # refused before anything is created
    rec = core.check_guard(guard, valid_times=[fresh_time], row_source="reconstructed_frames",
                           now=instant, evidence_root=str(root))
    assert rec["round"] == name and rec["basis"] == "FRESH"
    assert rec["defaults_used"] is True and rec["nondefault_params"] == {} and rec["override_reason"] is None
    assert rec["evaluation_instant"] == instant.isoformat()
    assert rec["round_descriptive_only"] is False


def test_the_read1_boundary_edge(tmp_path):
    guard = core.guard_for_round("v4-read1")
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(guard, valid_times=[FRESH_TIME], row_source="shadow_logs",
                         now=pd.Timestamp("2026-10-31T23:59:59Z"), evidence_root=str(tmp_path))
    rec = core.check_guard(guard, valid_times=[FRESH_TIME], row_source="shadow_logs",
                           now=pd.Timestamp("2026-11-01T00:00:00Z"), evidence_root=str(tmp_path))
    assert rec["basis"] == "FRESH"
    # a cutoff equal to the instant (or later) is a ValueError, with or without text
    for bad_cutoff in (READ1_INSTANT, READ1_INSTANT + pd.Timedelta(days=1)):
        with pytest.raises(ValueError, match="strictly before"):
            core.check_guard(core.GuardConfig(valid_time_cutoff=bad_cutoff), valid_times=[DEV_TIME],
                             row_source="shadow_logs", now=READ1_INSTANT, evidence_root=str(tmp_path))
    # the scored window is start <= valid_time < cutoff: 2026-10-25T00:00:00Z is the first unscored slot
    slots = pd.date_range(core.FRESH_BASIS_START, guard.valid_time_cutoff, freq="6h", inclusive="left")
    assert slots[0] == core.FRESH_BASIS_START and slots[-1] == READ1_FRESH_TIME
    assert pd.Timestamp("2026-10-25T00:00:00Z") not in set(slots) and len(slots) == 100


def test_the_late_descriptive_round_is_marked_descriptive_in_the_record(tmp_path):
    rec = core.check_guard(core.guard_for_round("v4-late-descriptive"), valid_times=[FRESH_TIME],
                           row_source="reconstructed_frames", now=READ1_INSTANT, evidence_root=str(tmp_path))
    assert rec["round"] == "v4-late-descriptive" and rec["round_descriptive_only"] is True
    assert rec["defaults_used"] is True


def test_a_second_round_is_not_a_non_default_date_but_a_wrong_round_name_is_refused(tmp_path):
    # the default dates belong to v4-read1: read 2's dates are non-default for a guard that names read 1
    mixed = core.GuardConfig(evaluation_instant=READ2_INSTANT, valid_time_cutoff=core.V4_READ2.cutoff)
    with pytest.raises(ValueError, match="non-default"):
        core.check_guard(mixed, valid_times=[DEV_TIME], row_source="shadow_logs", now=READ2_INSTANT,
                         evidence_root=str(tmp_path))
    with pytest.raises(KeyError):
        core.check_guard(core.GuardConfig(round_name="v3"), valid_times=[DEV_TIME], row_source="shadow_logs",
                         now=READ1_INSTANT, evidence_root=str(tmp_path))


def test_one_shot_applies_per_round_subroot(tmp_path):
    base = str(tmp_path / "evaluation")
    r1_root = core.round_evidence_root(base, core.V4_READ1)
    r2_root = core.round_evidence_root(base, core.V4_READ2)
    g1, g2 = core.guard_for_round("v4-read1"), core.guard_for_round("v4-read2")
    rec1 = core.check_guard(g1, valid_times=[FRESH_TIME], row_source="reconstructed_frames",
                            now=READ1_INSTANT, evidence_root=r1_root)
    core.new_evidence_dir(r1_root, "reconstructed_frames", READ1_INSTANT, rec1, {})
    # a second run into the read-1 subroot is refused, whatever the row-source-matching clock says
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        core.check_guard(g1, valid_times=[FRESH_TIME], row_source="reconstructed_frames",
                         now=READ1_INSTANT + pd.Timedelta(hours=1), evidence_root=r1_root)
    # the read-1 marker does not refuse read 2, and the other way round
    rec2 = core.check_guard(g2, valid_times=[FRESH_TIME], row_source="reconstructed_frames",
                            now=READ2_INSTANT, evidence_root=r2_root)
    assert rec2["prior_fresh_runs"] == []
    core.new_evidence_dir(r2_root, "reconstructed_frames", READ2_INSTANT, rec2, {})
    shadow_marker_root = core.round_evidence_root(base, core.V4_LATE_DESCRIPTIVE)
    assert core.check_guard(core.guard_for_round("v4-late-descriptive"), valid_times=[FRESH_TIME],
                            row_source="reconstructed_frames", now=READ1_INSTANT,
                            evidence_root=shadow_marker_root)["prior_fresh_runs"] == []
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(g2, valid_times=[FRESH_TIME], row_source="reconstructed_frames",
                         now=READ2_INSTANT + pd.Timedelta(days=1), evidence_root=r2_root)
    # the one-shot rule is per row source as well
    assert core.check_guard(g1, valid_times=[FRESH_TIME], row_source="shadow_logs",
                            now=READ1_INSTANT, evidence_root=r1_root)["prior_fresh_runs"] == []


@pytest.mark.parametrize("name, fresh_time", [("v4-read1", READ1_FRESH_TIME), ("v4-read2", READ2_FRESH_TIME)])
@pytest.mark.parametrize("text", ["owner approved it", "x", "2026-11-24 rehearsal"])
def test_a_fresh_run_is_refused_whatever_override_text_is_given(tmp_path, name, fresh_time, text):
    base = core.guard_for_round(name)
    guard = core.GuardConfig(base.evaluation_instant, base.valid_time_cutoff, text, name)
    for now in (base.evaluation_instant - pd.Timedelta(days=3), base.evaluation_instant,
                base.evaluation_instant + pd.Timedelta(days=60)):
        with pytest.raises(core.EvaluationGuardError, match="take no override"):
            core.check_guard(guard, valid_times=[fresh_time], row_source="reconstructed_frames", now=now,
                             evidence_root=str(tmp_path / "e"))
    assert not (tmp_path / "e").exists()


def test_the_retired_v3_instant_is_refused_for_a_fresh_run(tmp_path):
    retired = core.GuardConfig(evaluation_instant=core.V3_RETIRED_INSTANT,
                               valid_time_cutoff=pd.Timestamp("2026-11-17T00:00:00Z"))
    with pytest.raises(ValueError, match="retired by signed protocol v4"):
        core.check_guard(retired, valid_times=[FRESH_TIME], row_source="reconstructed_frames",
                         now=core.V3_RETIRED_INSTANT + pd.Timedelta(days=1), evidence_root=str(tmp_path))
    # the other v3 cutoff and instant alone are non-default dates, refused too
    with pytest.raises(ValueError):
        core.check_guard(core.GuardConfig(evaluation_instant=core.V3_RETIRED_INSTANT), valid_times=[FRESH_TIME],
                         row_source="reconstructed_frames", now=core.V3_RETIRED_INSTANT + pd.Timedelta(days=1),
                         evidence_root=str(tmp_path))
    assert not os.listdir(tmp_path)


def test_a_fresh_run_is_refused_while_v4_is_unsigned_and_a_development_run_is_not(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "v4_signed", lambda *a, **k: False)
    for name, fresh_time in (("v4-read1", READ1_FRESH_TIME), ("v4-read2", READ2_FRESH_TIME)):
        guard = core.guard_for_round(name)
        with pytest.raises(core.EvaluationGuardError, match=r"protocol v4 is not signed.*\(SEL-01\)"):
            core.check_guard(guard, valid_times=[fresh_time], row_source="reconstructed_frames",
                             now=guard.evaluation_instant + pd.Timedelta(days=1), evidence_root=str(tmp_path))
    rec = core.check_guard(core.guard_for_round("v4-read1"), valid_times=[DEV_TIME], row_source="shadow_logs",
                           now=READ1_INSTANT - pd.Timedelta(days=3), evidence_root=str(tmp_path))
    assert rec["basis"] == "development" and rec["round"] == "v4-read1"
    assert not os.listdir(tmp_path)


def test_development_runs_are_unaffected_by_the_fresh_refusals(tmp_path):
    # development rows: no instant, no one-shot, any parameter; override text is recorded as before
    g = core.guard_for_round("v4-read1")
    before_instant = READ1_INSTANT - pd.Timedelta(days=30)
    rec = core.check_guard(g, valid_times=[DEV_TIME], row_source="shadow_logs", now=before_instant,
                           evidence_root=str(tmp_path / "e"))
    assert rec["basis"] == "development" and rec["prior_fresh_runs"] == []
    for text in ("a", "b"):
        with_text = core.GuardConfig(g.evaluation_instant, g.valid_time_cutoff, text, g.round_name)
        r = core.check_guard(with_text, valid_times=[DEV_TIME], row_source="shadow_logs", now=before_instant,
                             evidence_root=str(tmp_path / "e"))
        assert r["override_reason"] == text and r["basis"] == "development"


def test_the_old_armed_before_instant_line_is_gone_for_good():
    src = open(os.path.join(os.path.dirname(core.__file__), "forecast_shadow_eval_core.py"), encoding="utf-8").read()
    assert "if now_ts < instant and override is None" not in src
    assert "if prior and override is None" not in src


def test_relative_margin_fraction_is_a_pre_registered_parameter():
    assert core.default_params()["relative_margin_fraction"] == 0.02
    assert core.nondefault_params(core.default_params()) == {}
    assert core.nondefault_params({"relative_margin_fraction": 0.03}) == {"relative_margin_fraction": 0.03}
    assert core.nondefault_params({"relative_margin_fraction": 0.02}) == {}


def test_a_non_default_relative_margin_refuses_a_fresh_run_and_override_text_cannot_help(tmp_path):
    nd = core.nondefault_params({"relative_margin_fraction": 0.03})
    g = core.guard_for_round("v4-read1")
    with pytest.raises(ValueError, match="relative_margin_fraction"):
        core.check_guard(g, valid_times=[FRESH_TIME], row_source="reconstructed_frames", now=READ1_INSTANT,
                         evidence_root=str(tmp_path), nondefault_params=nd)
    with pytest.raises(core.EvaluationGuardError):
        core.check_guard(core.GuardConfig(g.evaluation_instant, g.valid_time_cutoff, "0.03 was my idea", g.round_name),
                         valid_times=[FRESH_TIME], row_source="reconstructed_frames", now=READ1_INSTANT,
                         evidence_root=str(tmp_path), nondefault_params=nd)
    # development runs may try it
    rec = core.check_guard(g, valid_times=[DEV_TIME], row_source="reconstructed_frames", now=READ1_INSTANT,
                           evidence_root=str(tmp_path), nondefault_params=nd)
    assert rec["nondefault_params"] == nd


def test_planner_defaults_describe_the_v4_rule_and_round():
    pd_ = core.PLANNER_DEFAULTS
    assert "relative" in pd_["PD-10"]["default"] and "2%" in pd_["PD-10"]["default"]
    assert "3" in pd_["PD-10"]["default"] and "consistency" in pd_["PD-10"]["default"]
    assert "signed v4 rounds take no override" in pd_["PD-15"]["default"]
    assert pd_["PD-18"] == {"title": "protocol round", "default": "v4-read1"}
    assert core._PD_PARAM_MAP["relative_margin_fraction"] == "PD-10"
    r = core.planner_defaults_in_force({"relative_margin_fraction": 0.03})
    assert r["PD-10"]["non_default"] and r["PD-10"]["changed"] == {"relative_margin_fraction": 0.03}
    assert core.PLANNER_DEFAULTS["PD-02"]["default"] == "2026-09-28..2026-10-24"


def test_owner_pending_points_at_the_signing_copy_only():
    assert len(core.OWNER_PENDING) == 1
    assert "confirmation_protocol_v4_early_selection_SIGNING_COPY.md" in core.OWNER_PENDING[0]
    assert "v3_per_city" not in core.OWNER_PENDING[0]
    assert core.V4_SIGNING_COPY == os.path.join(
        "docs", "data-science", "decisions", "confirmation_protocol_v4_early_selection_SIGNING_COPY.md")


def test_rendered_header_names_the_round():
    r = _report()
    assert "Round: v4-read1" in core.render_header(r)
    assert r["guard"]["round"] == "v4-read1"


def test_retired_instant_appears_in_the_module_text_only_as_retired():
    path = os.path.join(os.path.dirname(core.__file__), "forecast_shadow_eval_core.py")
    for number, line in enumerate(open(path, encoding="utf-8").read().splitlines(), start=1):
        if "2026-11-24" in line:
            assert "retired" in line.lower() or "V3_RETIRED_INSTANT" in line, f"line {number}: {line}"


# --- v4_signed: the signature line of the signing copy

def _signing_copy_in(tmp_path, signature_line):
    folder = tmp_path / "docs" / "data-science" / "decisions"
    folder.mkdir(parents=True)
    (folder / "confirmation_protocol_v4_early_selection_SIGNING_COPY.md").write_text(
        "# v4\n\n## Sign-off\n\n- Project owner (name): ____\n" + signature_line + "\n- Date (UTC): ____\n",
        encoding="utf-8")
    return str(tmp_path)


def test_v4_signed_reads_the_signature_line(tmp_path):
    assert core.v4_signed() is True                                  # this repository's signing copy
    assert core.v4_signed(str(tmp_path)) is False                    # no signing copy at all
    assert core.v4_signed(_signing_copy_in(tmp_path / "blank", "- Signature: ____________")) is False
    assert core.v4_signed(_signing_copy_in(tmp_path / "spaces", "- Signature:    ")) is False
    assert core.v4_signed(_signing_copy_in(tmp_path / "none", "no signature line here")) is False
    assert core.v4_signed(_signing_copy_in(tmp_path / "signed", "- Signature: aaphan")) is True


# --------------------------------------------------------------------------
# FRESH experiment cache path guard
# --------------------------------------------------------------------------

def test_fresh_cache_path_guard(tmp_path):
    fresh = os.path.join("data", "experiment", "anchored_pair_frame_AUSTIN_2026-09-30_2026-10-04_lead24_previous_runs.csv")
    with pytest.raises(core.EvaluationGuardError):
        core.assert_not_fresh_experiment_cache(fresh)
    frozen = os.path.join("data", "experiment", "anchored_pair_frame_AUSTIN_2024-01-20_2026-09-29_lead24_previous_runs.csv")
    core.assert_not_fresh_experiment_cache(frozen)          # frozen window end: allowed
    core.assert_not_fresh_experiment_cache("some/other/file.csv")
    inside = tmp_path / "run" / "frames" / "anchored_pair_frame_AUSTIN_2026-09-28_2026-10-24_lead24_previous_runs.csv"
    core.assert_not_fresh_experiment_cache(str(inside), allow_dir=str(tmp_path / "run"))
    with pytest.raises(core.EvaluationGuardError):
        core.assert_not_fresh_experiment_cache(str(inside), allow_dir=str(tmp_path / "other"))
    sibling = tmp_path / "run_evil" / "anchored_pair_frame_AUSTIN_2026-09-28_2026-10-24_lead24_x.csv"
    with pytest.raises(core.EvaluationGuardError):
        core.assert_not_fresh_experiment_cache(str(sibling), allow_dir=str(tmp_path / "run"))


# --------------------------------------------------------------------------
# HTTP evidence recorder
# --------------------------------------------------------------------------

def test_record_http_writes_verbatim_body_sha256_and_timestamps(tmp_path, monkeypatch):
    body = b'{"x": 1}\n\xc3\xa9'
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append((url, params, kwargs))
        return _FakeResponse(raw=body)
    monkeypatch.setattr(requests, "get", fake_get)
    with core.record_http(str(tmp_path), "probe") as rec:
        resp = requests.get("https://example.test/a", params={"k": "v"}, timeout=5)
    assert resp.content == body
    assert requests.get is fake_get                       # restored
    assert calls == [("https://example.test/a", {"k": "v"}, {"timeout": 5})]
    http = tmp_path / "http"
    assert sorted(os.listdir(http)) == ["01_probe.body", "01_probe.meta.json"]
    assert (http / "01_probe.body").read_bytes() == body
    meta = json.loads((http / "01_probe.meta.json").read_text())
    assert meta["sha256"] == hashlib.sha256(body).hexdigest()
    assert meta["byte_length"] == len(body)
    assert meta["url"] == "https://example.test/a" and meta["params"] == {"k": "v"}
    assert meta["status_code"] == 200
    assert meta["date_header"] == "Tue, 24 Nov 2026 00:00:01 GMT" and meta["content_type"] == "application/json"
    assert pd.Timestamp(meta["retrieval_started_at_utc"]) <= pd.Timestamp(meta["retrieval_completed_at_utc"])
    assert meta["error"] is None and rec.records[0]["sha256"] == meta["sha256"]


def test_record_http_numbers_successive_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, params=None, **k: _FakeResponse(raw=b"abc"))
    with core.record_http(str(tmp_path), "a"):
        requests.get("u1", params={})
        requests.get("u2", params={})
    assert sorted(os.listdir(tmp_path / "http")) == ["01_a.body", "01_a.meta.json", "02_a.body", "02_a.meta.json"]


def test_record_http_restores_get_and_records_and_reraises_errors(tmp_path, monkeypatch):
    def failing_get(url, params=None, **kwargs):
        raise requests.ConnectionError("boom")
    monkeypatch.setattr(requests, "get", failing_get)
    with pytest.raises(requests.ConnectionError):
        with core.record_http(str(tmp_path), "bad"):
            requests.get("https://example.test/x", params={"a": 1})
    assert requests.get is failing_get
    meta = json.loads((tmp_path / "http" / "01_bad.meta.json").read_text())
    assert "ConnectionError: boom" in meta["error"] and meta["sha256"] is None
    assert not (tmp_path / "http" / "01_bad.body").exists()
    # an exception raised in the body (not by get) also restores the original
    with pytest.raises(RuntimeError):
        with core.record_http(str(tmp_path), "body"):
            raise RuntimeError("in body")
    assert requests.get is failing_get


def test_collect_evidence_lists_files(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda url, params=None, **k: _FakeResponse(raw=b"zz"))
    with core.record_http(str(tmp_path), "c"):
        requests.get("u", params={})
    ev = core.collect_evidence(str(tmp_path))
    assert len(ev) == 1 and ev[0]["sha256"] == hashlib.sha256(b"zz").hexdigest() and ev[0]["body_file"] == "01_c.body"
    assert core.collect_evidence(str(tmp_path / "nothing")) == []


# --------------------------------------------------------------------------
# Archive truth
# --------------------------------------------------------------------------

def _capture_fetch_open_meteo(monkeypatch, city, start, end, payload):
    seen = []

    def fake_get(url, params=None, **kwargs):
        seen.append((url, dict(params), kwargs))
        return _FakeResponse(payload)
    monkeypatch.setattr(requests, "get", fake_get)
    lat, lon = config.CITY_COORDINATES[city]
    frame = open_meteo_provider.fetch_open_meteo(lat, lon, start, end)
    return frame, seen


def test_archive_request_matches_fetch_open_meteo(tmp_path, monkeypatch):
    payload = archive_payload("2026-10-01", "2026-10-03")
    frame, seen = _capture_fetch_open_meteo(monkeypatch, "AUSTIN", "2026-10-01", "2026-10-03", payload)
    url, params = core.build_archive_request("AUSTIN", "2026-10-01", "2026-10-03")
    assert (url, params) == (seen[0][0], seen[0][1])
    # and the scorer's own fetch sends the same params, one request, timeout 60
    mine = []
    monkeypatch.setattr(requests, "get", lambda u, params=None, **k: (mine.append((u, dict(params), k)), _FakeResponse(payload))[1])
    out, meta = core.fetch_archive_truth("AUSTIN", "2026-10-01", "2026-10-03", evidence_dir=str(tmp_path))
    assert len(mine) == 1 and mine[0][0] == url and mine[0][1] == params and mine[0][2] == {"timeout": 60}
    pd.testing.assert_frame_equal(out, frame)
    assert meta["error"] is None and meta["n_hours"] == 72
    assert meta["http_records"][0]["sha256"] == hashlib.sha256(json.dumps(payload).encode()).hexdigest()


def test_parse_archive_payload_equals_fetch_open_meteo_frame(monkeypatch):
    payload = archive_payload("2026-10-01", "2026-10-02")
    frame, _ = _capture_fetch_open_meteo(monkeypatch, "MIDLAND", "2026-10-01", "2026-10-02", payload)
    pd.testing.assert_frame_equal(core.parse_archive_payload(payload), frame)


@pytest.mark.parametrize("mutate", [
    lambda p: p.update(hourly_units={**p["hourly_units"], "wind_speed_10m": "km/h"}),
    lambda p: p["hourly"].update(wind_speed_10m=p["hourly"]["wind_speed_10m"][:-1]),
    lambda p: p["hourly"].update(temperature_2m=[999.0] * len(p["hourly"]["time"])),
    lambda p: p["hourly"].pop("shortwave_radiation"),
    lambda p: p.update(hourly=None),
    lambda p: p["hourly"].update(time=[]),
])
def test_parse_archive_payload_raises_like_fetch_open_meteo(monkeypatch, mutate):
    payload = archive_payload("2026-10-01", "2026-10-02")
    mutate(payload)
    with pytest.raises(ValueError) as mine:
        core.parse_archive_payload(payload)
    _capture = []
    monkeypatch.setattr(requests, "get", lambda u, params=None, **k: _FakeResponse(payload))
    lat, lon = config.CITY_COORDINATES["AUSTIN"]
    with pytest.raises(ValueError) as theirs:
        open_meteo_provider.fetch_open_meteo(lat, lon, "2026-10-01", "2026-10-02")
    assert str(mine.value) == str(theirs.value)


def test_fetch_archive_truth_503_is_one_call_and_no_retry(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(requests, "get", lambda u, params=None, **k: (calls.append(1), _FakeResponse(raw=b"unavailable", status=503))[1])
    frame, meta = core.fetch_archive_truth("AUSTIN", "2026-10-01", "2026-10-02", evidence_dir=str(tmp_path))
    assert frame is None and len(calls) == 1
    assert "HTTPError" in meta["error"]
    assert meta["http_records"][0]["status_code"] == 503
    assert (tmp_path / "http" / "01_archive_AUSTIN.body").read_bytes() == b"unavailable"


def test_fetch_archive_truth_bad_json_is_recorded_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "get", lambda u, params=None, **k: _FakeResponse(raw=b"not json"))
    frame, meta = core.fetch_archive_truth("AUSTIN", "2026-10-01", "2026-10-02", evidence_dir=str(tmp_path))
    assert frame is None and "ValueError" in meta["error"]


@pytest.mark.parametrize("city", list(config.LOCATIONS))
def test_truth_ampacity_matches_an_independent_computation(city):
    payload = archive_payload("2026-10-01", "2026-10-02")
    weather = core.parse_archive_payload(payload)
    out, dropped = core.truth_ampacity(weather, city)
    assert dropped == [] and list(out.columns) == ["datetime_utc", "truth_amps"]
    point = city_point.city_point(city)
    perp = thermal_model.perpendicular_wind(weather["wind_speed"].to_numpy(float), weather["wind_direction"].to_numpy(float), point.bearing_deg)
    expected = np.asarray(thermal_model.ieee738_ampacity(weather["air_temp"].to_numpy(float), perp, weather["solar_radiation"].to_numpy(float), point.conductor), dtype=float)
    np.testing.assert_allclose(out["truth_amps"].to_numpy(), expected, rtol=0, atol=1e-9)
    assert list(out["datetime_utc"]) == list(weather["datetime_utc"])


def test_truth_ampacity_drops_null_hours_and_never_imputes():
    null_hour = pd.Timestamp("2026-10-01T05:00:00Z")
    payload = archive_payload("2026-10-01", "2026-10-01", null_hours=[null_hour])
    weather = core.parse_archive_payload(payload)
    out, dropped = core.truth_ampacity(weather, "AUSTIN")
    assert dropped == [null_hour.isoformat()]
    assert null_hour not in set(out["datetime_utc"]) and len(out) == 23
    assert out["truth_amps"].notna().all()


def test_truth_ampacity_all_null_gives_empty_frame():
    payload = archive_payload("2026-10-01", "2026-10-01", null_hours=list(pd.date_range("2026-10-01", periods=24, freq="h", tz="UTC")))
    out, dropped = core.truth_ampacity(core.parse_archive_payload(payload), "AUSTIN")
    assert len(out) == 0 and len(dropped) == 24


# --------------------------------------------------------------------------
# Descriptive metrics
# --------------------------------------------------------------------------

def test_descriptive_metrics_on_a_hand_fixture():
    truth = np.array([100.0, 100.0, 100.0, 100.0, 100.0, 100.0])
    pred = np.array([110.0, 90.0, 100.0, 130.0, 95.0, 101.0])
    err = np.array([10.0, -10.0, 0.0, 30.0, -5.0, 1.0])
    m = core.descriptive_metrics(pred, truth)
    assert m["n"] == 6
    assert m["bias"] == pytest.approx(26.0 / 6)
    assert m["mae"] == pytest.approx(56.0 / 6)
    assert m["rmse"] == pytest.approx(np.sqrt((100 + 100 + 0 + 900 + 25 + 1) / 6))
    assert m["median_abs_error"] == pytest.approx(7.5)             # |e| = 0,1,5,10,10,30
    assert m["overprediction_rate"] == pytest.approx(3 / 6)          # 10, 30, 1
    assert m["overshoot_mean"] == pytest.approx((10 + 30 + 1) / 3)
    assert m["overshoot_max"] == pytest.approx(30.0)
    assert m["overshoot_p95"] == pytest.approx(float(np.percentile([10.0, 30.0, 1.0], 95)))
    assert "not the calibrated 5%-target rate" in m["overprediction_label"]
    assert err.sum() == 26.0


def test_descriptive_metrics_empty_and_no_overshoot():
    m = core.descriptive_metrics([], [])
    assert m["n"] == 0 and m["mae"] is None and m["bias"] is None
    m = core.descriptive_metrics([90.0, 80.0], [100.0, 100.0])
    assert m["overshoot_mean"] is None and m["overprediction_rate"] == 0.0 and m["bias"] == pytest.approx(-15.0)


def test_precision_targets_are_met_only_at_the_target():
    assert core.precision_targets(589)["tail_rate_target_met"] is False
    assert core.precision_targets(590)["tail_rate_target_met"] is True
    assert core.precision_targets(1574)["mdd_target_met"] is False
    assert core.precision_targets(1575)["mdd_target_met"] is True


# --------------------------------------------------------------------------
# Provenance and report
# --------------------------------------------------------------------------

def test_provenance_git_sha_artifact_hashes_and_freeze_flagging(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    present = model_dir / "ml_wind_corrected_AUSTIN.joblib"
    present.write_bytes(b"artifact-bytes")
    monkeypatch.setattr(forecast_shadow_pipeline, "SHADOW_MODEL_DIR", str(model_dir))

    def fake_git(repo_root, *args):
        if args[:2] == ("log", "--format=%H %cI"):
            return ("a" * 40 + " 2026-11-02T10:00:00+00:00\n" + "b" * 40 + " 2026-10-12T21:35:00-05:00\n"
                    if args[-1].endswith("ml_wind_corrected_AUSTIN.joblib") else "")
        if args[0] == "rev-parse":
            return "c" * 40 + "\n"
        if args[0] == "status":
            return " M file\n"
        return None
    monkeypatch.setattr(core, "_run_git", fake_git)
    prov = core.provenance(str(tmp_path), ["AUSTIN", "MIDLAND"], source_commit="d" * 40)
    assert prov["git_sha"] == "c" * 40 and prov["git_dirty"] is True and prov["logs_source_commit"] == "d" * 40
    assert len(prov["artifacts"]) == 6
    by = {(a["method"], a["city"]): a for a in prov["artifacts"]}
    assert by[("ml_wind_corrected", "AUSTIN")]["sha256"] == hashlib.sha256(b"artifact-bytes").hexdigest()
    assert by[("ml_wind_corrected", "MIDLAND")]["sha256"] == "missing"
    flagged = prov["freeze_check"]["flagged"]
    assert len(flagged) == 1 and flagged[0]["commit"] == "a" * 40
    assert set(prov["versions"]) == {"python", "numpy", "pandas", "scipy", "sklearn"}


def test_provenance_unknown_when_git_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "_run_git", lambda *a, **k: None)
    prov = core.provenance(str(tmp_path), ["AUSTIN"])
    assert prov["git_sha"] == "unknown" and prov["git_dirty"] is None
    assert all(a["commits"] == "unknown" for a in prov["artifacts"])


def test_provenance_real_repo_sha_is_40_hex_or_unknown():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    prov = core.provenance(root, ["AUSTIN"])
    assert re.fullmatch(r"[0-9a-f]{40}", prov["git_sha"]) or prov["git_sha"] == "unknown"


def _report(**kw):
    guard = core.check_guard(_guard(), valid_times=[DEV_TIME], row_source="shadow_logs", now=INSTANT, evidence_root="unused")
    prov = {"git_sha": "e" * 40, "git_dirty": False, "artifacts": [],
            "freeze_check": {"flagged": [], "model_freeze": core.MODEL_FREEZE.isoformat()}, "versions": {}}
    return core.new_report(row_source=kw.pop("row_source", "shadow_logs"), basis=guard["basis"], protocol_status="unsigned",
                           guard=guard, config_record={"k": 1}, prov=prov, **kw)


def test_new_report_has_the_s6_keys():
    r = _report()
    assert set(r) >= {"row_source", "basis", "protocol_status", "guard", "config", "provenance", "sample_size", "family",
                      "decision", "per_city", "exclusions", "validity_flags", "diagnostics", "not_measured",
                      "planner_defaults", "owner_pending", "evidence"}
    assert r["not_measured"] == core.NOT_MEASURED_STATEMENT
    assert len(r["planner_defaults"]) == 18 and not any(v["non_default"] for v in r["planner_defaults"].values())
    flags = {f["id"]: f for f in r["validity_flags"]}
    assert flags["V4"]["applies"] and flags["V6"]["applies"]
    rr = _report(row_source="reconstructed_frames")
    flags = {f["id"]: f for f in rr["validity_flags"]}
    assert flags["V4"]["applies"] and not any(flags[k]["applies"] for k in ("V1", "V2", "V3", "V5", "V6"))
    assert all(flags[k]["not_applicable_reason"] for k in ("V1", "V2", "V3", "V5", "V6"))


def test_planner_defaults_mark_nondefault_values():
    r = _report(params={**core.default_params(), "n_resamples": 2000, "decision_margin_amps": 7.0})
    pd_ = r["planner_defaults"]
    assert pd_["PD-09"]["non_default"] and pd_["PD-09"]["changed"] == {"n_resamples": 2000}
    assert pd_["PD-10"]["non_default"] and pd_["PD-10"]["changed"] == {"decision_margin_amps": 7.0}
    assert not pd_["PD-03"]["non_default"]


def test_render_markdown_order_and_required_lines(tmp_path):
    r = _report()
    r["guard"]["override_reason"] = "owner rehearsal"
    r["sample_size"] = {
        "per_city": {"AUSTIN": {"n_in_scope": 5, "n_scored": {"raw_forecast": 5}, "targets": core.precision_targets(5)}},
        "pooled_nominal": {"label": "nominal, not effective", "n_scored": {"raw_forecast": 5}, "targets": core.precision_targets(5)},
    }
    md = core.render_markdown(r)
    assert md.startswith("# Per-city shadow evaluation - row source: shadow logs (live-system check)")
    assert core.TRUTH_LABEL in md
    assert "DEVELOPMENT DATA - not a confirmation result" in md
    assert "Round: v4-read1" in md
    assert "Evaluation instant: 2026-11-01T00:00:00+00:00" in md
    assert "Valid-time cutoff (strict, valid_time < cutoff): 2026-10-25T00:00:00+00:00" in md
    assert "Override: owner rehearsal" in md
    assert core.NOT_MEASURED_STATEMENT in md
    assert core.EXPLORATORY_STATEMENT in md
    idx = [md.index(h) for h in ("## Sample size", "## Headline family", "## Decision", "## Per-city descriptive metrics",
                                  "## Per-city comparisons", "## Validity flags", "## Scope and exclusions",
                                  "## Not measured", "## Planner defaults", "## Evidence files")]
    assert idx == sorted(idx)
    assert "~590" in md and "Nominal count is below ~590" in md and "target met" not in md
    assert md.index("## Sample size") < md.index("## Headline family")
    assert "Override: none" in core.render_markdown(_report())


def test_write_report_is_atomic_and_round_trips(tmp_path):
    r = _report()
    r["per_city"] = {"AUSTIN": {"x": np.float64(1.5), "y": np.int64(3), "t": pd.Timestamp("2026-10-01T00:00:00Z"), "nan": float("nan")}}
    paths = core.write_report(r, str(tmp_path))
    assert sorted(os.listdir(tmp_path)) == ["report.json", "report.md"]
    data = json.loads(open(paths["report_json"]).read())
    assert data["per_city"]["AUSTIN"] == {"x": 1.5, "y": 3, "t": "2026-10-01T00:00:00+00:00", "nan": None}
    assert open(paths["report_md"]).read().startswith("# Per-city shadow evaluation")


def test_dumps_is_deterministic_and_nan_free():
    a = {"b": [1.0, float("inf")], "a": np.float64("nan")}
    assert core.dumps(a) == core.dumps(dict(reversed(list(a.items()))))
    assert json.loads(core.dumps(a)) == {"a": None, "b": [1.0, None]}


# --- 2026-10-13: precision targets are judged on EFFECTIVE n, never on a pooled nominal count ----

def test_precision_targets_are_judged_on_effective_n_when_it_is_given():
    t = core.precision_targets(768, n_eff=150.0)
    assert t["basis"] == "effective" and t["n"] == 768 and t["n_effective"] == 150.0
    assert t["tail_rate_target_met"] is False and t["mdd_target_met"] is False
    # an effective n can never be larger than the nominal n it came from
    assert core.precision_targets(100, n_eff=900.0)["tail_rate_target_met"] is False
    # no effective n supplied: nominal basis, as before
    assert core.precision_targets(768)["basis"] == "nominal"
    assert core.precision_targets(768)["tail_rate_target_met"] is True


def test_sample_size_render_never_reports_a_pooled_nominal_count_as_meeting_a_target():
    report = {"sample_size": {
        "pooled_nominal": {"targets": core.precision_targets(768)},
        "per_city": {"AUSTIN": {"n_scored": {"raw_forecast": 192}, "targets": core.precision_targets(192)}},
        "pairs": [{
            "a": "ml_wind_corrected", "b": "raw_forecast", "n_paired": 768, "n_eff_bootstrap": 140.0,
            "n_eff_acf_by_city": {"AUSTIN": 60.0}, "mdd": 20.0, "rows_needed_for_5A": 2400,
            "targets": core.precision_targets(768, 140.0),
        }],
    }}
    md = core.render_sample_size(report)
    pooled_line = [l for l in md.splitlines() if l.startswith("- Pooled NOMINAL")][0]
    assert "NOT an effective sample size" in pooled_line and "target met" not in pooled_line
    assert "| not met | not met |" in md  # the pair row, judged on effective n = 140
    assert "met | met" not in md


def test_pooled_nominal_targets_are_never_judged_against_the_precision_targets():
    # 2026-10-13 (Task 4 validation): report.json carried `tail_rate_target_met: True` for a pooled nominal 976.
    t = core.pooled_nominal_targets(976)
    assert t["n"] == 976 and t["basis"] == "nominal_not_judged" and t["n_effective"] is None
    assert t["tail_rate_target_met"] is False and t["mdd_target_met"] is False
    assert core.pooled_nominal_targets(10 ** 6)["tail_rate_target_met"] is False
    assert core.pooled_nominal_targets(10 ** 6)["mdd_target_met"] is False
