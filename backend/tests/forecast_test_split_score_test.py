"""
Tests for `backend/forecast_test_split_score.py`, the per-city TEST-split scorer and its signed veto (07-10, SEL-03).

Synthetic frames written into a tmp cache directory, stub models fitted in-test and a tmp evidence root only.
Nothing here reads `data/experiment`, loads a real `data/shadow/models` artifact for scoring, opens a FRESH-dated
cache file or touches the network; an autouse spy turns any such access into a failure.
"""

from __future__ import annotations

import builtins
import json
import os

import numpy as np
import pandas as pd
import pytest
import requests

import city_point
import config
import forecast_experiment
import forecast_experiment_audit as audit
import forecast_shadow_confirm as conf
import forecast_conductor_refit as refit
import forecast_shadow_eval_core as core
import forecast_shadow_pipeline as pipeline
import forecast_test_split_score as tss
import protocol_v4_registry as reg

# Shared synthetic world and fixtures of the headline-port tests (fixtures are re-exported by import).
from forecast_shadow_confirm_test import (  # noqa: F401
    CITIES, austin_100c, fit_stub_models, loader_for, make_frame, refit_world, stub_models,
)

REPO_ROOT = reg.REPO_ROOT
REAL_EXPERIMENT_DIR = os.path.realpath(os.path.join(REPO_ROOT, "data", "experiment"))
RAW = "raw_forecast"
REAL = list(core.REAL_CANDIDATES)
# Ten days inside the TEST window, every slot present in the synthetic frames (40 six-hourly slots per city).
WINDOW = ("2026-04-01T00:00:00Z", "2026-04-11T00:00:00Z")
WINDOW_SLOTS = 40
NOW = "2026-11-02T09:00:00Z"
FRESH_START = pd.Timestamp("2026-09-30T00:00:00Z")


# --------------------------------------------------------------------------
# Autouse guards and helpers
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("requests.get must not be called in this test")
    monkeypatch.setattr(requests, "get", boom)


@pytest.fixture(autouse=True)
def _redirected_cache(tmp_path, monkeypatch):
    path = str(tmp_path / "cache")
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", path)
    return path


@pytest.fixture(autouse=True)
def _never_touch_real_data(monkeypatch):
    """Any open or read_csv of a path inside the real data/experiment directory fails the test."""
    real_open = builtins.open
    real_read_csv = pd.read_csv

    def check(path):
        if isinstance(path, (str, os.PathLike)):
            real = os.path.realpath(os.fspath(path))
            if real == REAL_EXPERIMENT_DIR or real.startswith(REAL_EXPERIMENT_DIR + os.sep):
                raise AssertionError(f"a test opened the real experiment directory: {path}")

    def spy_open(file, *args, **kwargs):
        check(file)
        return real_open(file, *args, **kwargs)

    def spy_read_csv(path, *args, **kwargs):
        check(path)
        return real_read_csv(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(pd, "read_csv", spy_read_csv)


@pytest.fixture
def evidence_root(tmp_path):
    return str(tmp_path / "evidence")


def synthetic_frame(city: str, *, start: str = "2026-03-28", end: str = "2026-04-10 23:00") -> pd.DataFrame:
    frame = make_frame(city, start, end)
    return frame[frame["anchor_datetime_utc"] >= pd.Timestamp(start, tz="UTC")].reset_index(drop=True)


def dev_provider(city, *, evidence_dir):
    """Injected provider with the cached provider's contract: (frame, archive weather, meta)."""
    frame = synthetic_frame(city)
    cols = ["air_temp", "wind_speed", "wind_direction", "solar_radiation", "relative_humidity"]
    weather = frame[["datetime_utc"] + [f"truth_{c}" for c in cols]].copy()
    weather.columns = ["datetime_utc"] + cols
    return frame, weather, {"city": city, "provider": "fixture"}


def cache_path(city: str) -> str:
    return forecast_experiment._cache_path_for(city, audit.FROZEN_WINDOW_START, audit.FROZEN_WINDOW_END, lead_hours=24)


def write_cache(city: str, frame: pd.DataFrame | None = None) -> str:
    path = cache_path(city)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    (synthetic_frame(city) if frame is None else frame).to_csv(path, index=False)
    return path


def run(evidence_root, stub_models, *, now=NOW, cities=None, provider=dev_provider, **kwargs):
    kwargs.setdefault("window", WINDOW)
    kwargs.setdefault("expected_slots", None)
    kwargs.setdefault("params", {"n_resamples": 200})
    kwargs.setdefault("model_loader", loader_for(stub_models))
    return tss.run_test_split(cities or CITIES, evidence_root=evidence_root, now=now, provider=provider, **kwargs)


# --------------------------------------------------------------------------
# Constants and the TEST window
# --------------------------------------------------------------------------

def test_constants_equal_the_signed_registry():
    registry = reg.parse_registry(reg.SIGNING_COPY_PATH)
    assert tss.TEST_WINDOW_START == reg.as_timestamp(registry["test.window_start"])
    assert tss.TEST_WINDOW_END_EXCLUSIVE == reg.as_timestamp(registry["test.window_end_exclusive"])
    assert tss.TEST_SLOTS_PER_CITY == int(registry["test.slots_per_city"]) == 784
    assert tss.VETO_MIN_CITIES == int(registry["test.veto_min_cities"]) == 3
    assert tss.EVIDENCE_SUBDIR == "v4-test"
    assert tss.CONDUCTOR_BASES == ("frozen-drake", "production")
    assert tss.TEST_WINDOW_END_EXCLUSIVE == core.FRESH_BASIS_START


def test_the_test_window_has_784_slots_from_march_18_to_the_last_slot_before_fresh():
    slots = conf.ScoredWindow(tss.TEST_WINDOW_START, tss.TEST_WINDOW_END_EXCLUSIVE).slots()
    assert len(slots) == 784
    assert slots[0].isoformat() == "2026-03-18T00:00:00+00:00"
    assert slots[-1].isoformat() == "2026-09-29T18:00:00+00:00"
    assert all(t.hour % 6 == 0 for t in slots)


def test_boundary_edge_first_and_last_slot_in_scope_and_nothing_outside_it():
    slots = set(conf.ScoredWindow(tss.TEST_WINDOW_START, tss.TEST_WINDOW_END_EXCLUSIVE).slots())
    assert pd.Timestamp("2026-03-18T00:00:00Z") in slots                 # scored
    assert pd.Timestamp("2026-03-17T18:00:00Z") not in slots             # anchor in the fit window
    assert pd.Timestamp("2026-09-29T18:00:00Z") in slots                 # last scored slot
    assert pd.Timestamp("2026-09-30T00:00:00Z") not in slots             # FRESH is never in scope


def test_boundary_edge_the_port_scores_march_18_and_refuses_the_slot_whose_anchor_is_in_the_fit_window():
    frame = make_frame("AUSTIN", "2026-03-10", "2026-03-25 23:00")
    frame = frame[frame["anchor_datetime_utc"] >= pd.Timestamp("2026-03-10", tz="UTC")].reset_index(drop=True)
    end = pd.Timestamp("2026-03-19T00:00:00Z")
    prepared, diag = conf.prepare_city_frame(frame, "AUSTIN", window=conf.ScoredWindow(tss.TEST_WINDOW_START, end))
    assert prepared["datetime_utc"].min() == pd.Timestamp("2026-03-18T00:00:00Z")
    assert prepared["anchor_datetime_utc"].min() == pd.Timestamp("2026-03-17T00:00:00Z")
    assert diag["n_scored_slots"] == 4 == diag["n_expected_slots"]
    with pytest.raises(conf.ReconstructionError, match="fit window"):
        conf.prepare_city_frame(
            frame, "AUSTIN", window=conf.ScoredWindow(pd.Timestamp("2026-03-17T18:00:00Z"), end))


# --------------------------------------------------------------------------
# The cached-frame provider
# --------------------------------------------------------------------------

def test_the_provider_reads_only_the_frozen_window_cache_and_builds_archive_weather_from_its_truth_columns(tmp_path):
    path = write_cache("AUSTIN")
    frame, weather, meta = tss.cached_test_provider("AUSTIN", evidence_dir=str(tmp_path / "ev"))
    assert os.path.basename(path) == "anchored_pair_frame_AUSTIN_2024-01-20_2026-09-29_lead24_previous_runs.csv"
    assert meta["cache_path"] == path and meta["cache_sha256"] == core.sha256_file(path) and meta["city"] == "AUSTIN"
    assert len(frame) == len(synthetic_frame("AUSTIN"))
    assert list(weather.columns) == ["datetime_utc", "air_temp", "wind_speed", "wind_direction", "solar_radiation",
                                     "relative_humidity"]
    for field in ("air_temp", "wind_speed", "wind_direction", "solar_radiation", "relative_humidity"):
        assert np.array_equal(weather[field].to_numpy(), frame[f"truth_{field}"].to_numpy())
    assert (pd.to_datetime(weather["datetime_utc"], utc=True) == frame["datetime_utc"]).all()


def test_a_missing_cache_is_refused_naming_the_path_with_no_network_call_and_nothing_created(tmp_path, _redirected_cache):
    expected = cache_path("MIDLAND")
    with pytest.raises(conf.FrameFetchError) as exc:
        tss.cached_test_provider("MIDLAND", evidence_dir=str(tmp_path / "ev"))
    assert expected in str(exc.value) and "cache" in str(exc.value).lower()
    assert not os.path.exists(expected)                                   # nothing was fetched or written
    assert not os.path.exists(str(tmp_path / "ev"))


def test_a_cache_name_carrying_the_fresh_dates_is_refused_and_never_opened(tmp_path, monkeypatch):
    monkeypatch.setattr(tss, "CACHE_START", "2026-09-30")
    monkeypatch.setattr(tss, "CACHE_END", "2026-10-04")
    fresh_path = forecast_experiment._cache_path_for("AUSTIN", "2026-09-30", "2026-10-04", lead_hours=24)
    os.makedirs(os.path.dirname(fresh_path), exist_ok=True)
    with open(fresh_path, "w", encoding="utf-8") as fh:
        fh.write("datetime_utc\n")
    opened = []
    real_open, real_read_csv = builtins.open, pd.read_csv
    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: (opened.append(str(f)), real_open(f, *a, **k))[1])
    monkeypatch.setattr(pd, "read_csv", lambda p, *a, **k: (opened.append(str(p)), real_read_csv(p, *a, **k))[1])
    with pytest.raises(core.EvaluationGuardError, match="FRESH"):
        tss.cached_test_provider("AUSTIN", evidence_dir=str(tmp_path / "ev"))
    assert [p for p in opened if p.endswith("2026-09-30_2026-10-04_lead24_previous_runs.csv")] == []


def test_a_frame_holding_a_row_on_or_after_the_fresh_start_is_refused(tmp_path):
    frame = make_frame("AUSTIN", "2026-09-27", "2026-09-30 05:00")
    frame = frame[frame["anchor_datetime_utc"] >= pd.Timestamp("2026-09-27", tz="UTC")].reset_index(drop=True)
    assert (frame["datetime_utc"] >= FRESH_START).any()
    write_cache("AUSTIN", frame)
    with pytest.raises(core.EvaluationGuardError, match="2026-09-30"):
        tss.cached_test_provider("AUSTIN", evidence_dir=str(tmp_path / "ev"))


def test_a_frame_whose_last_row_is_the_last_frozen_hour_is_accepted(tmp_path):
    frame = make_frame("AUSTIN", "2026-09-26", "2026-09-29 23:00")
    frame = frame[frame["anchor_datetime_utc"] >= pd.Timestamp("2026-09-26", tz="UTC")].reset_index(drop=True)
    write_cache("AUSTIN", frame)
    out, _, _ = tss.cached_test_provider("AUSTIN", evidence_dir=str(tmp_path / "ev"))
    assert out["datetime_utc"].max() == pd.Timestamp("2026-09-29T23:00:00Z")


# --------------------------------------------------------------------------
# run_test_split
# --------------------------------------------------------------------------

def test_unsigned_protocol_is_refused_before_any_provider_call_or_directory(evidence_root, stub_models, monkeypatch):
    monkeypatch.setattr(core, "v4_signed", lambda repo_root=None: False)
    calls = []

    def spy_provider(city, *, evidence_dir):
        calls.append(city)
        return dev_provider(city, evidence_dir=evidence_dir)

    with pytest.raises(core.EvaluationGuardError, match="not signed"):
        run(evidence_root, stub_models, provider=spy_provider)
    assert calls == [] and not os.path.exists(evidence_root)


def test_the_dev_fixture_run_scores_every_city_and_builds_the_family_without_naming_a_pick(evidence_root, stub_models):
    report = run(evidence_root, stub_models)
    assert report["basis"] == "development" and report["failed_cities"] == {}
    assert set(report["per_city"]) == set(CITIES)
    for city in CITIES:
        block = report["per_city"][city]
        assert block["n_in_scope"] == WINDOW_SLOTS == block["n_with_truth"]
    assert len(report["family"]["comparisons"]) == core.FAMILY_SIZE
    assert report["conductor_basis"]["name"] == "frozen-drake"
    assert report["decision"] is None                                     # TEST vetoes; it never picks (D-02)
    assert "pick" not in json.dumps(report["decision"])
    on_disk = json.loads(open(report["report_paths"]["report_json"], encoding="utf-8").read())
    assert on_disk["decision"] is None and on_disk["conductor_basis"]["name"] == "frozen-drake"
    assert os.path.dirname(report["evidence_dir"]) == evidence_root


def test_the_frozen_drake_basis_scores_with_the_frozen_artifacts_under_the_drake_point(evidence_root, stub_models, monkeypatch):
    seen = {}
    real = conf.run_confirmation

    def spy(**kwargs):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(conf, "run_confirmation", spy)
    run(evidence_root, stub_models, cities=["AUSTIN"])
    assert seen.get("point_resolver") is None
    assert seen["window"] == conf.ScoredWindow(core.to_utc(WINDOW[0]), core.to_utc(WINDOW[1]))
    assert seen["vetoes"] is None and seen.get("secondary") is None
    assert seen["guard_cfg"] == core.GuardConfig()


def test_the_default_loader_of_the_frozen_basis_checks_hashes_before_deserializing(
        evidence_root, stub_models, refit_world, monkeypatch):
    seen = {}
    real = conf.run_confirmation

    def spy(**kwargs):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(conf, "run_confirmation", spy)
    run(evidence_root, stub_models, cities=["MIDLAND"], model_loader=None)
    loader = seen["model_loader"]
    assert loader.frozen_manifest == refit_world["manifest"]
    assert len(loader.served) == 3 and {s["source"] for s in loader.served} == {"frozen"}
    assert all(len(s["sha256"]) == 64 for s in loader.served)
    # a tampered frozen artifact is refused by the loader before it is deserialized
    with open(pipeline._model_path_for("EL_PASO", conf.WIND), "ab") as fh:
        fh.write(b"x")
    with pytest.raises(refit.ArtifactIntegrityError, match="hash mismatch"):
        run(os.path.join(evidence_root, "tampered"), stub_models, cities=["EL_PASO"], model_loader=None,
            now="2026-11-02T09:00:09Z")


def test_expected_slots_is_asserted_per_city_and_a_mismatch_names_the_city_and_both_counts(evidence_root, stub_models):
    with pytest.raises(tss.ScoringScopeError) as exc:
        run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND"], expected_slots=WINDOW_SLOTS + 1)
    text = str(exc.value)
    assert "AUSTIN" in text and str(WINDOW_SLOTS) in text and str(WINDOW_SLOTS + 1) in text
    ok = run(os.path.join(evidence_root, "ok"), stub_models, cities=["AUSTIN", "MIDLAND"], expected_slots=WINDOW_SLOTS)
    assert ok["per_city"]["MIDLAND"]["n_in_scope"] == WINDOW_SLOTS


def test_a_city_whose_frame_failed_breaks_the_slot_assertion_instead_of_being_scored_short(evidence_root, stub_models):
    def failing(city, *, evidence_dir):
        if city == "EL_PASO":
            raise conf.FrameFetchError("EL_PASO: injected fetch failure")
        return dev_provider(city, evidence_dir=evidence_dir)

    with pytest.raises(tss.ScoringScopeError, match="EL_PASO"):
        run(evidence_root, stub_models, provider=failing, expected_slots=WINDOW_SLOTS)


@pytest.mark.parametrize("window", [
    ("2026-09-29T00:00:00Z", "2026-10-02T00:00:00Z"),      # reaches into FRESH
    ("2026-09-30T00:00:00Z", "2026-10-25T00:00:00Z"),      # the FRESH read-1 window itself
    ("2026-03-17T00:00:00Z", "2026-04-01T00:00:00Z"),      # starts before the first TEST day
    ("2026-04-11T00:00:00Z", "2026-04-01T00:00:00Z"),      # empty and reversed
])
def test_a_window_outside_the_test_window_is_refused_before_any_provider_call(evidence_root, stub_models, window):
    calls = []

    def spy_provider(city, *, evidence_dir):
        calls.append(city)
        return dev_provider(city, evidence_dir=evidence_dir)

    with pytest.raises(ValueError, match="TEST window"):
        run(evidence_root, stub_models, provider=spy_provider, window=window)
    assert calls == [] and not os.path.exists(evidence_root)


def test_an_unknown_conductor_basis_is_refused(evidence_root, stub_models):
    with pytest.raises(ValueError, match="conductor basis"):
        run(evidence_root, stub_models, conductor_basis="live")


def test_the_full_window_is_the_default_and_the_preflight_names_a_missing_cache_before_creating_evidence(
        evidence_root, stub_models):
    write_cache("AUSTIN")                                                 # the other three caches are absent
    with pytest.raises(conf.FrameFetchError, match="MIDLAND|CORPUS_CHRISTI|EL_PASO"):
        tss.run_test_split(CITIES, evidence_root=evidence_root, now=NOW, model_loader=loader_for(stub_models))
    assert not os.path.exists(evidence_root)


def test_a_whole_run_through_the_cached_provider_reads_only_the_tmp_cache(evidence_root, stub_models):
    for city in CITIES:
        write_cache(city)
    report = tss.run_test_split(CITIES, evidence_root=evidence_root, now=NOW, window=WINDOW, expected_slots=WINDOW_SLOTS,
                                params={"n_resamples": 200}, model_loader=loader_for(stub_models))
    for city in CITIES:
        meta = report["diagnostics"][city]["frame_fetch"]
        assert meta["cache_path"] == cache_path(city) and meta["cache_sha256"] == core.sha256_file(cache_path(city))
        assert report["per_city"][city]["n_with_truth"] == WINDOW_SLOTS


# --- production basis ---

def test_production_basis_with_every_city_at_parity_is_refused_with_no_city_differs(evidence_root, stub_models):
    with pytest.raises(ValueError, match="no city differs"):
        run(evidence_root, stub_models, conductor_basis="production")
    assert not os.path.exists(evidence_root)


def test_production_basis_scores_the_differing_city_under_its_production_conductor(evidence_root, stub_models, refit_world):
    prod = run(os.path.join(evidence_root, "prod"), stub_models, conductor_basis="production", model_loader=None,
               now="2026-11-02T09:00:01Z")
    frozen = run(os.path.join(evidence_root, "frozen"), stub_models, model_loader=None, now="2026-11-02T09:00:02Z")
    assert prod["conductor_basis"]["name"] == "production" and prod["conductor_basis"]["differing"] == ["AUSTIN"]
    assert frozen["conductor_basis"]["name"] == "frozen-drake"
    # AUSTIN at 100 C rates higher; the cities that did not change are identical under both bases.
    assert prod["truth_stats"]["AUSTIN"]["mean_truth_amps"] > frozen["truth_stats"]["AUSTIN"]["mean_truth_amps"]
    for city in ("CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        assert prod["truth_stats"][city] == frozen["truth_stats"][city]
    sources = {(a["city"], a["method"]): a["source"] for a in prod["scored_artifacts"]}
    assert sources[("AUSTIN", conf.COOLING)] == "refit" and sources[("AUSTIN", conf.REFERENCE)] == "refit"
    assert sources[("AUSTIN", conf.WIND)] == "frozen" and sources[("MIDLAND", conf.COOLING)] == "frozen"
    assert {a["source"] for a in frozen["scored_artifacts"]} == {"frozen"}


def test_production_basis_refuses_an_unsound_refit_artifact_before_any_provider_call(evidence_root, stub_models, refit_world):
    art = refit_world["dir"] / f"{conf.COOLING}_AUSTIN.joblib"
    art.write_bytes(art.read_bytes() + b"x")
    calls = []

    def spy_provider(city, *, evidence_dir):
        calls.append(city)
        return dev_provider(city, evidence_dir=evidence_dir)

    with pytest.raises(core.EvaluationGuardError, match="hash_mismatch"):
        run(evidence_root, stub_models, conductor_basis="production", provider=spy_provider, model_loader=None)
    assert calls == [] and not os.path.exists(evidence_root)


# --------------------------------------------------------------------------
# evaluate_test_vetoes
# --------------------------------------------------------------------------

def fake_report(margins: dict, maes: dict | None = None) -> dict:
    """A report with only the family: margins[candidate] = {city: margin of candidate over raw_forecast or None}."""
    comparisons = []
    for cand in REAL:
        per_city_margins = margins.get(cand, {c: 1.0 for c in CITIES})
        per_city = {}
        for city, margin in per_city_margins.items():
            if margin is None:
                per_city[city] = {"n_paired": 0, "mae_a": None, "mae_b": None}
            else:
                raw_mae = 50.0 if maes is None else maes[cand][city][1]
                cand_mae = raw_mae - margin if maes is None else maes[cand][city][0]
                per_city[city] = {"n_paired": 100, "mae_a": cand_mae, "mae_b": raw_mae}
        comparisons.append({"a": cand, "b": RAW, "per_city_margins": per_city_margins, "per_city": per_city})
    return {"family": {"comparisons": comparisons}, "per_city": {c: {} for c in CITIES}}


def losing(*cities, margin=-2.0):
    return {c: (margin if c in cities else 3.0) for c in CITIES}


def test_a_candidate_losing_to_raw_in_three_of_four_cities_is_vetoed():
    result = tss.evaluate_test_vetoes(fake_report({"ml_cooling_corrected": losing("AUSTIN", "MIDLAND", "EL_PASO")}))
    verdict = result["ml_cooling_corrected"]
    assert verdict["vetoed"] is True
    assert sorted(verdict["cities_losing_to_raw"]) == ["AUSTIN", "EL_PASO", "MIDLAND"]
    assert verdict["reasons"] and "AUSTIN" in verdict["reasons"][0] and "3" in verdict["reasons"][0]
    assert result["ml_wind_corrected"]["vetoed"] is False and result["reference_ml_refit_24h"]["vetoed"] is False


def test_a_candidate_losing_in_two_cities_is_not_vetoed():
    verdict = tss.evaluate_test_vetoes(fake_report({"ml_wind_corrected": losing("AUSTIN", "MIDLAND")}))["ml_wind_corrected"]
    assert verdict["vetoed"] is False and verdict["reasons"] == []
    assert len(verdict["cities_losing_to_raw"]) == 2


def test_a_tie_is_not_losing():
    margins = {"reference_ml_refit_24h": {"AUSTIN": 0.0, "CORPUS_CHRISTI": 0.0, "MIDLAND": 0.0, "EL_PASO": -1.0}}
    verdict = tss.evaluate_test_vetoes(fake_report(margins))["reference_ml_refit_24h"]
    assert verdict["vetoed"] is False and verdict["cities_losing_to_raw"] == ["EL_PASO"]


def test_the_smallest_possible_loss_counts_as_losing():
    margins = {"ml_wind_corrected": losing("AUSTIN", "MIDLAND", "EL_PASO", margin=-1e-9)}
    assert tss.evaluate_test_vetoes(fake_report(margins))["ml_wind_corrected"]["vetoed"] is True


def test_a_city_without_data_is_not_counted():
    # three cities have data and two of them lose: not vetoed, and the empty city is not a third loss
    two_of_three = {"AUSTIN": -1.0, "CORPUS_CHRISTI": -1.0, "MIDLAND": 2.0, "EL_PASO": None}
    verdict = tss.evaluate_test_vetoes(fake_report({"ml_wind_corrected": two_of_three}))["ml_wind_corrected"]
    assert verdict["vetoed"] is False and sorted(verdict["cities_losing_to_raw"]) == ["AUSTIN", "CORPUS_CHRISTI"]
    assert "EL_PASO" not in verdict["per_city_mae"] or verdict["per_city_mae"]["EL_PASO"] == (None, None)
    # three cities have data and all three lose: vetoed (at least 3 of the cities with data)
    three_of_three = {"AUSTIN": -1.0, "CORPUS_CHRISTI": -1.0, "MIDLAND": -2.0, "EL_PASO": None}
    assert tss.evaluate_test_vetoes(fake_report({"ml_wind_corrected": three_of_three}))["ml_wind_corrected"]["vetoed"] is True


def test_per_city_mae_pairs_come_from_the_complete_case_maes():
    maes = {cand: {c: (40.0, 50.0) for c in CITIES} for cand in REAL}
    maes["ml_wind_corrected"]["MIDLAND"] = (61.5, 50.0)
    margins = {"ml_wind_corrected": {c: (50.0 - maes["ml_wind_corrected"][c][0]) for c in CITIES}}
    verdict = tss.evaluate_test_vetoes(fake_report(margins, maes))["ml_wind_corrected"]
    assert verdict["per_city_mae"]["MIDLAND"] == (61.5, 50.0) and verdict["per_city_mae"]["AUSTIN"] == (40.0, 50.0)
    assert verdict["cities_losing_to_raw"] == ["MIDLAND"]


def test_min_cities_is_a_parameter_and_defaults_to_the_signed_three():
    report = fake_report({"ml_wind_corrected": losing("AUSTIN", "MIDLAND")})
    assert tss.evaluate_test_vetoes(report)["ml_wind_corrected"]["vetoed"] is False
    assert tss.evaluate_test_vetoes(report, min_cities=2)["ml_wind_corrected"]["vetoed"] is True


def test_a_report_missing_a_candidate_comparison_is_refused_not_unvetoed():
    report = fake_report({})
    report["family"]["comparisons"] = [c for c in report["family"]["comparisons"] if c["a"] != "ml_cooling_corrected"]
    with pytest.raises(ValueError, match="ml_cooling_corrected"):
        tss.evaluate_test_vetoes(report)
    with pytest.raises(ValueError, match="family"):
        tss.evaluate_test_vetoes({"family": None})


def test_the_veto_of_a_real_run_agrees_with_an_independent_per_city_mae_computation(evidence_root, stub_models):
    report = run(evidence_root, stub_models)
    result = tss.evaluate_test_vetoes(report)
    assert set(result) == set(REAL)
    for cand in REAL:
        entry = next(c for c in report["family"]["comparisons"] if (c["a"], c["b"]) == (cand, RAW))
        losers = sorted(c for c in CITIES if entry["per_city"][c]["mae_a"] > entry["per_city"][c]["mae_b"])
        assert sorted(result[cand]["cities_losing_to_raw"]) == losers
        assert result[cand]["vetoed"] is (len(losers) >= 3)
        for city in CITIES:
            assert result[cand]["per_city_mae"][city] == (entry["per_city"][city]["mae_a"], entry["per_city"][city]["mae_b"])


# --------------------------------------------------------------------------
# write_test_report
# --------------------------------------------------------------------------

def test_write_test_report_writes_json_and_a_plain_english_markdown_first(tmp_path, evidence_root, stub_models):
    report = run(evidence_root, stub_models)
    vetoes = tss.evaluate_test_vetoes(report)
    out = str(tmp_path / "report_x")
    paths = tss.write_test_report(report, vetoes, out)
    assert os.path.basename(paths["json"]) == "test_split.json" and os.path.basename(paths["markdown"]) == "test_split.md"
    body = json.loads(open(paths["json"], encoding="utf-8").read())
    assert body["vetoes"].keys() == vetoes.keys() and body["conductor_basis"]["name"] == "frozen-drake"
    assert body["veto_rule"]["min_cities"] == 3 and body["decision"] is None
    md = open(paths["markdown"], encoding="utf-8").read()
    assert md.startswith("# TEST-split re-score")
    plain = md.split("## ", 2)[1]
    assert plain.startswith("In plain English")
    for city in CITIES:
        assert city in md
    for cand in REAL:
        assert cand in md
    assert "veto" in plain.lower() and "never" in plain.lower() and "pick" in plain.lower()


def test_write_test_report_refuses_an_existing_directory_and_the_frozen_model_directory(tmp_path, evidence_root, stub_models):
    report = run(evidence_root, stub_models)
    vetoes = tss.evaluate_test_vetoes(report)
    existing = tmp_path / "already"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        tss.write_test_report(report, vetoes, str(existing))
    with pytest.raises(ValueError, match="frozen"):
        tss.write_test_report(report, vetoes, os.path.join(pipeline.SHADOW_MODEL_DIR, "report"))
    assert os.listdir(existing) == []


def test_the_markdown_names_which_candidates_beat_raw_and_which_would_be_vetoed():
    margins = {"ml_cooling_corrected": losing("AUSTIN", "MIDLAND", "EL_PASO")}
    report = {**fake_report(margins), "conductor_basis": {"name": "frozen-drake"}, "decision": None,
              "window": [str(tss.TEST_WINDOW_START), str(tss.TEST_WINDOW_END_EXCLUSIVE)]}
    vetoes = tss.evaluate_test_vetoes(report)
    text = tss.summary_markdown(report, vetoes)
    assert "ml_cooling_corrected: WOULD BE VETOED" in text
    assert "ml_wind_corrected: not vetoed" in text
    assert "beats raw_forecast in" in text


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_defaults_and_choices():
    args = tss.build_parser().parse_args([])
    assert args.conductor_basis == "frozen-drake" and args.cities == list(config.LOCATIONS)
    assert args.evidence_root == os.path.join(core.EVIDENCE_ROOT_DEFAULT, "v4-test") and args.out_dir is None
    with pytest.raises(SystemExit):
        tss.build_parser().parse_args(["--conductor-basis", "live"])
    with pytest.raises(SystemExit):
        tss.build_parser().parse_args(["--cities", "ATLANTIS"])


def test_default_out_dir_is_a_stamped_report_directory_beside_the_evidence_runs():
    out = tss._default_out_dir(os.path.join("data", "shadow", "evaluation", "v4-test"), now="2026-11-03T04:05:06Z")
    assert out == os.path.join("data", "shadow", "evaluation", "v4-test", "report_20261103T040506Z")


def test_cli_with_production_at_parity_exits_2_with_no_city_differs(tmp_path, capsys, evidence_root):
    code = tss.main(["--conductor-basis", "production", "--evidence-root", evidence_root,
                     "--out-dir", str(tmp_path / "rep")])
    assert code == 2
    assert "no city differs" in capsys.readouterr().err
    assert not os.path.exists(evidence_root) and not os.path.exists(tmp_path / "rep")


def test_cli_when_unsigned_exits_2_before_any_work(tmp_path, capsys, monkeypatch, evidence_root):
    monkeypatch.setattr(core, "v4_signed", lambda repo_root=None: False)
    code = tss.main(["--evidence-root", evidence_root, "--out-dir", str(tmp_path / "rep")])
    assert code == 2 and "not signed" in capsys.readouterr().err
    assert not os.path.exists(evidence_root)


def test_cli_with_a_missing_cache_exits_2_naming_it(tmp_path, capsys, evidence_root):
    code = tss.main(["--evidence-root", evidence_root, "--out-dir", str(tmp_path / "rep")])
    assert code == 2
    assert "cache" in capsys.readouterr().err.lower()
    assert not os.path.exists(evidence_root)


def test_cli_runs_scores_and_writes_the_report_through_the_scorer(tmp_path, capsys, monkeypatch, evidence_root, stub_models):
    for city in CITIES:
        write_cache(city)
    real = tss.run_test_split

    def narrowed(cities, **kwargs):
        kwargs.update(window=WINDOW, expected_slots=WINDOW_SLOTS, params={"n_resamples": 200},
                      model_loader=loader_for(stub_models), now=NOW)
        return real(cities, **kwargs)

    monkeypatch.setattr(tss, "run_test_split", narrowed)
    out = str(tmp_path / "rep")
    code = tss.main(["--cities", "AUSTIN", "MIDLAND", "--evidence-root", evidence_root, "--out-dir", out])
    assert code == 0
    assert os.path.isfile(os.path.join(out, "test_split.json")) and os.path.isfile(os.path.join(out, "test_split.md"))
    printed = capsys.readouterr().out
    assert "TEST report written to" in printed and "ml_wind_corrected" in printed
    body = json.loads(open(os.path.join(out, "test_split.json"), encoding="utf-8").read())
    assert sorted(body["cities"]) == ["AUSTIN", "MIDLAND"]


def test_cli_refuses_an_existing_out_dir_with_exit_2(tmp_path, capsys, monkeypatch, evidence_root, stub_models):
    for city in CITIES:
        write_cache(city)
    real = tss.run_test_split

    def narrowed(cities, **kwargs):
        kwargs.update(window=WINDOW, expected_slots=WINDOW_SLOTS, params={"n_resamples": 200},
                      model_loader=loader_for(stub_models), now=NOW)
        return real(cities, **kwargs)

    monkeypatch.setattr(tss, "run_test_split", narrowed)
    existing = tmp_path / "rep"
    existing.mkdir()
    code = tss.main(["--cities", "AUSTIN", "--evidence-root", evidence_root, "--out-dir", str(existing)])
    assert code == 2 and "refused" in capsys.readouterr().err


def test_the_module_never_names_a_fresh_dated_cache_or_the_scorers_of_the_one_shot_read():
    source = open(os.path.join(REPO_ROOT, "backend", "forecast_test_split_score.py"), encoding="utf-8").read()
    assert "2026-09-30_" not in source and "2026-10-04" not in source
    assert "forecast_shadow_score" not in source.replace("forecast_shadow_score_stats", "")
    assert "data/experiment" not in source        # the cache directory is reached only through the helpers
