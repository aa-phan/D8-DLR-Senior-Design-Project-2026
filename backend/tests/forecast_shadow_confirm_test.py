"""
Tests for `backend/forecast_shadow_confirm.py`, the per-city point-metrics port
of the frozen FRESH harness on reconstructed frames (quick task 261013-285,
Task 3). Synthetic anchored frames, stub models fitted in-test and mocked HTTP
only; every file lives under `tmp_path`. Nothing here reads `data/experiment`,
loads a real `data/shadow/models` artifact for scoring, or touches the network.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os

import numpy as np
import pandas as pd
import pytest
import requests
from sklearn.linear_model import LinearRegression

import ampacity_forecast
import city_point
import config
import forecast_correction_models as fcm
import forecast_experiment
import forecast_shadow_confirm as conf
import forecast_shadow_eval_core as core
import forecast_shadow_fit_models as fit_models
import forecast_shadow_pipeline as pipeline
import forecast_training
import open_meteo_forecast_provider
import open_meteo_provider
import thermal_model

CITIES = list(config.LOCATIONS)
INSTANT = core.EVALUATION_INSTANT_DEFAULT
BEFORE_INSTANT = "2026-10-31T23:59:59Z"
AT_INSTANT = "2026-11-01T00:00:00Z"
FETCH_START, FETCH_END = core.RECON_FETCH_START, core.RECON_FETCH_END
SMALL = {"n_resamples": 200}  # non-default: only used on a development basis (a FRESH run refuses it)
DEV_WINDOW = ("2026-04-01T00:00:00Z", "2026-04-11T00:00:00Z")


# --------------------------------------------------------------------------
# Synthetic world: deterministic truth and forecast weather per city
# --------------------------------------------------------------------------

def truth_weather(ts: pd.DatetimeIndex, ci: int) -> pd.DataFrame:
    h = ts.hour.to_numpy(float)
    d = ts.dayofyear.to_numpy(float)
    return pd.DataFrame({
        "air_temp": 18 + 9 * np.sin(2 * np.pi * (h - 9) / 24) + 3 * np.sin(d / 3.0 + ci),
        "wind_speed": 2.5 + 1.5 * np.sin(2 * np.pi * h / 24 + ci) + ((d * h) % 5) * 0.3,
        "wind_direction": (h * 37 + d * 11 + ci * 40) % 360,
        "solar_radiation": np.where((h >= 6) & (h <= 18), 700 * np.sin(np.pi * (h - 6) / 12), 0.0),
        "relative_humidity": 50 + (d % 20) + 0 * h,
    }, index=ts)


def fcst_weather(ts: pd.DatetimeIndex, ci: int) -> pd.DataFrame:
    t = truth_weather(ts, ci)
    h = ts.hour.to_numpy(float)
    return pd.DataFrame({
        "air_temp": t.air_temp + 1.2 + 0.5 * np.sin(h),
        "wind_speed": t.wind_speed * 1.15 + 0.4,
        "wind_direction": (t.wind_direction + 12) % 360,
        "solar_radiation": t.solar_radiation * 0.9,
        "relative_humidity": t.relative_humidity,
    }, index=ts)


def city_index(city: str) -> int:
    return CITIES.index(city)


def make_frame(city: str, valid_start: str, valid_end: str) -> pd.DataFrame:
    """An anchored-pair-shaped frame (hourly valid times, anchor 24 h earlier)."""
    ci = city_index(city)
    vt = pd.date_range(valid_start, valid_end, freq="h", tz="UTC")
    anc = vt - pd.Timedelta(hours=24)
    cols = {"datetime_utc": vt}
    for prefix, ts, fn in (("truth", vt, truth_weather), ("fcst", vt, fcst_weather),
                           ("anchor", anc, truth_weather), ("fcst_anchor", anc, fcst_weather)):
        w = fn(ts, ci)
        for c in w.columns:
            cols[f"{prefix}_{c}"] = w[c].to_numpy()
    cols["anchor_datetime_utc"] = anc
    cols["truth_dlr_amps"] = 999.0      # corridor-geometry values must never be read (F4)
    cols["anchor_dlr_amps"] = 888.0
    return pd.DataFrame(cols)


def archive_weather(city: str, start: str, end: str) -> pd.DataFrame:
    ts = pd.date_range(start, end, freq="h", tz="UTC")
    return truth_weather(ts, city_index(city)).rename_axis("datetime_utc").reset_index()


def recon_frame(city: str) -> pd.DataFrame:
    """The frame `anchored_pair_frame(city, 2026-09-28, 2026-10-24)` (v4-read1's fetch window) would build."""
    frame = make_frame(city, "2026-09-28", "2026-10-24 23:00")
    return frame[frame["anchor_datetime_utc"] >= pd.Timestamp("2026-09-28", tz="UTC")].reset_index(drop=True)


def injected_provider(*, weather_edit=None, frame_edit=None, fail=()):
    """A frame provider (city, *, evidence_dir) over the synthetic world; optional edits per city."""
    def provider(city, *, evidence_dir):
        if city in fail:
            raise conf.FrameFetchError(f"{city}: injected fetch failure")
        frame = recon_frame(city)
        weather = archive_weather(city, "2026-09-28", "2026-10-24 23:00")
        if frame_edit is not None:
            frame = frame_edit(city, frame)
        if weather_edit is not None:
            weather = weather_edit(city, weather)
        return frame, weather, {"city": city, "provider": "injected"}
    return provider


def dev_provider(city, *, evidence_dir):
    frame = make_frame(city, "2026-03-30 00:00", "2026-04-10 23:00")
    frame = frame[frame["anchor_datetime_utc"] >= pd.Timestamp("2026-03-30", tz="UTC")].reset_index(drop=True)
    return frame, archive_weather(city, "2026-03-30", "2026-04-10 23:00"), {"city": city}


# --------------------------------------------------------------------------
# Stub models (fitted in-test; the real artifacts are never loaded for scoring)
# --------------------------------------------------------------------------

def fit_stub_models(city: str) -> dict:
    ci = city_index(city)
    frame = make_frame(city, "2026-01-05", "2026-02-20 23:00")
    point = city_point.city_point(city)
    frame = frame.sort_values("datetime_utc").reset_index(drop=True)
    frame["truth_dlr_amps"] = fit_models.weather_to_arm5_frame(frame, city, prefix="truth_")["dlr_amps"].to_numpy()
    frame["city"] = city
    exact = forecast_experiment._add_correction_columns(
        forecast_experiment.filter_to_exact_lead(frame, lead_hours=24), point)
    wind = fcm.fit_wind_correction(exact, fcm.WIND_CORRECTION_ESTIMATORS["LinearRegression"], pooling="per_city")
    cooling = fcm.fit_cooling_correction(exact, fcm.COOLING_CORRECTION_ESTIMATORS["LinearRegression"],
                                         target="log_ratio", conductor=point.conductor)
    X, y = forecast_training.build_training_matrix(
        fit_models.weather_to_arm5_frame(frame, city, prefix="truth_"), horizon_minutes=1440)
    reference = LinearRegression().fit(X.to_numpy(dtype=float), y.to_numpy(dtype=float))
    assert ci >= 0
    return {conf.WIND: wind, conf.COOLING: cooling, conf.REFERENCE: reference}


@pytest.fixture(scope="module")
def stub_models():
    return {city: fit_stub_models(city) for city in CITIES}


@pytest.fixture
def model_dir(tmp_path, monkeypatch, stub_models):
    """SHADOW_MODEL_DIR redirected to tmp and populated with the 12 stub artifacts."""
    path = tmp_path / "models"
    monkeypatch.setattr(pipeline, "SHADOW_MODEL_DIR", str(path))
    for city, models in stub_models.items():
        for method, model in models.items():
            pipeline.save_correction_model(model, city, method)
    return str(path)


def loader_for(stub_models):
    return lambda city, method: stub_models[city][method]


# --------------------------------------------------------------------------
# Fake Open-Meteo server (archive + previous-runs payloads for any dates)
# --------------------------------------------------------------------------

class FakeResponse:
    def __init__(self, payload=None, status=200, raw=None):
        self.status_code = status
        self.content = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self.headers = {"Date": "Tue, 24 Nov 2026 00:00:01 GMT", "Content-Type": "application/json"}

    def json(self):
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _payload(fn, ci, start, end, *, suffix=""):
    times = pd.date_range(pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(hours=23), freq="h", tz="UTC")
    w = fn(times, ci)
    keys = {"temperature_2m": "air_temp", "wind_speed_10m": "wind_speed", "wind_direction_10m": "wind_direction",
            "shortwave_radiation": "solar_radiation", "relative_humidity_2m": "relative_humidity"}
    hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}
    for key, col in keys.items():
        hourly[key + suffix] = [float(v) for v in w[col].to_numpy()]
    units = {"temperature_2m": "°C", "wind_speed_10m": "m/s", "wind_direction_10m": "°",
             "shortwave_radiation": "W/m²", "relative_humidity_2m": "%"}
    return {"hourly": hourly, "hourly_units": {k + suffix: v for k, v in units.items()}}


class FakeServer:
    def __init__(self, monkeypatch, *, fail_previous=(), fail_archive=()):
        self.calls = []
        self.fail_previous = set(fail_previous)
        self.fail_archive = set(fail_archive)
        monkeypatch.setattr(requests, "get", self.get)

    def get(self, url, params=None, **kwargs):
        self.calls.append((url, dict(params), kwargs))
        lat = params["latitude"]
        city = next(c for c, (la, _) in config.CITY_COORDINATES.items() if la == lat)
        ci = city_index(city)
        if url == open_meteo_provider.OPEN_METEO_ARCHIVE_BASE:
            if city in self.fail_archive:
                return FakeResponse(raw=b"unavailable", status=503)
            return FakeResponse(_payload(truth_weather, ci, params["start_date"], params["end_date"]))
        assert url == open_meteo_forecast_provider.OPEN_METEO_PREVIOUS_RUNS_BASE, url
        if city in self.fail_previous:
            return FakeResponse(raw=b"unavailable", status=503)
        return FakeResponse(_payload(fcst_weather, ci, params["start_date"], params["end_date"],
                                     suffix="_previous_day1"))

    def calls_for(self, city):
        lat = config.CITY_COORDINATES[city][0]
        return [c for c in self.calls if c[1]["latitude"] == lat]


# --------------------------------------------------------------------------
# Autouse fixtures
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("requests.get must not be called in this test")
    monkeypatch.setattr(requests, "get", boom)


@pytest.fixture(autouse=True)
def _redirected_cache(tmp_path, monkeypatch):
    path = str(tmp_path / "real_cache_stand_in")
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", path)
    return path


@pytest.fixture
def evidence_root(tmp_path):
    return str(tmp_path / "evidence")


@pytest.fixture(autouse=True)
def _fresh_cache_spy(monkeypatch, tmp_path):
    """Fail any test that opens or reads a FRESH-window anchored_pair_frame cache outside the evidence root."""
    allowed = str(tmp_path / "evidence")
    real_open = builtins.open
    real_read_csv = pd.read_csv

    def spy_open(file, *args, **kwargs):
        if isinstance(file, (str, os.PathLike)):
            core.assert_not_fresh_experiment_cache(os.fspath(file), allow_dir=allowed)
        return real_open(file, *args, **kwargs)

    def spy_read_csv(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)):
            core.assert_not_fresh_experiment_cache(os.fspath(path), allow_dir=allowed)
        return real_read_csv(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(pd, "read_csv", spy_read_csv)


def no_veto_record() -> dict:
    """A synthetic ABLATION + TEST veto record in which no candidate is vetoed (a FRESH read needs one, SEL-03)."""
    section = lambda: {"vetoes": {c: {"vetoed": False, "reasons": []} for c in core.REAL_CANDIDATES}}
    return {"protocol": "v4", "ablation": section(), "test": section()}


def run(evidence_root, *, now=AT_INSTANT, cities=None, **kwargs):
    kwargs.setdefault("guard_cfg", core.GuardConfig())
    kwargs.setdefault("vetoes", no_veto_record())        # pass vetoes=None explicitly to run without a record
    return conf.run_confirmation(cities=cities or CITIES, evidence_root=evidence_root, now=now, **kwargs)


def injected_run(evidence_root, stub_models, *, now=AT_INSTANT, cities=None, params=None, **kwargs):
    kwargs.setdefault("frame_provider", injected_provider())
    kwargs.setdefault("model_loader", loader_for(stub_models))
    return run(evidence_root, now=now, cities=cities, params=params, **kwargs)


def independent_amps(weather_row_cols: dict, city: str) -> np.ndarray:
    point = city_point.city_point(city)
    perp = thermal_model.perpendicular_wind(np.asarray(weather_row_cols["wind_speed"], dtype=float),
                                            np.asarray(weather_row_cols["wind_direction"], dtype=float), point.bearing_deg)
    return np.asarray(thermal_model.ieee738_ampacity(
        np.asarray(weather_row_cols["air_temp"], dtype=float), perp,
        np.asarray(weather_row_cols["solar_radiation"], dtype=float), point.conductor), dtype=float)


# --------------------------------------------------------------------------
# Constants and window arithmetic
# --------------------------------------------------------------------------

def test_default_window_is_the_100_slot_fresh_window_of_read_1():
    # rewritten for v4-read1: the retired v3 window had 192 slots (to 2026-11-16T18Z)
    win = conf.default_window()
    slots = win.slots()
    assert win.start == pd.Timestamp("2026-09-30T00:00:00Z") and win.end == core.VALID_TIME_CUTOFF_DEFAULT
    assert win.end == pd.Timestamp("2026-10-25T00:00:00Z")
    assert len(slots) == 100 == core.V4_READ1.slots_per_city
    assert slots[0] == pd.Timestamp("2026-09-30T00:00:00Z") and slots[-1] == pd.Timestamp("2026-10-24T18:00:00Z")
    assert pd.Timestamp("2026-10-25T00:00:00Z") not in set(slots)        # start <= valid_time < cutoff
    assert all(t.hour % 6 == 0 for t in slots)


def test_each_signed_round_has_its_registered_slot_count_and_window():
    for name, count, last in (("v4-read1", 100, "2026-10-24T18:00:00Z"), ("v4-read2", 128, "2026-10-31T18:00:00Z")):
        guard = core.guard_for_round(name)
        win = conf.default_window(guard)
        slots = win.slots()
        assert win.end == guard.valid_time_cutoff and len(slots) == count
        assert slots[-1] == pd.Timestamp(last) and win.end not in set(slots)


def test_fetch_window_constants_are_consistent():
    assert pd.Timestamp(core.RECON_FETCH_END, tz="UTC") == core.VALID_TIME_CUTOFF_DEFAULT.normalize() - pd.Timedelta(days=1)
    assert pd.Timestamp(core.RECON_FETCH_START, tz="UTC") == core.FRESH_BASIS_START - pd.Timedelta(days=2)


# --------------------------------------------------------------------------
# Guard first
# --------------------------------------------------------------------------

def test_guard_refuses_before_any_side_effect(monkeypatch, evidence_root, tmp_path):
    touched = []
    real_open = builtins.open

    def spy_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)) and "data/experiment" in os.fspath(file).replace(os.sep, "/"):
            touched.append(os.fspath(file))
        return real_open(file, *a, **k)

    def boom(*a, **k):
        raise AssertionError("must not be reached before the guard passes")

    monkeypatch.setattr(builtins, "open", spy_open)
    monkeypatch.setattr(forecast_experiment, "anchored_pair_frame", boom)
    monkeypatch.setattr(pipeline, "load_correction_model", boom)
    with pytest.raises(core.EvaluationGuardError, match="evaluation instant"):
        run(evidence_root, now=BEFORE_INSTANT)
    assert not os.path.exists(evidence_root)
    assert touched == []
    assert not os.path.exists(config.FORECAST_EXPERIMENT_CACHE_DIR)


def test_cli_refuses_before_the_instant_with_exit_2(monkeypatch, evidence_root, capsys, tmp_path):
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp("2026-10-13T08:00:00Z"))
    vetoes_path = write_veto_files(tmp_path)[0]
    code = conf.main(["--evidence-root", evidence_root, "--vetoes", vetoes_path, "--protocol-status", "signed"])
    assert code == 2
    err = capsys.readouterr().err
    assert "refused" in err and "evaluation instant" in err
    assert not os.path.exists(evidence_root)


def test_override_text_is_refused_for_a_fresh_run_before_any_request(monkeypatch, evidence_root, model_dir):
    # v4: the old "rehearsal of the evaluation day" override ran FRESH rows early; it is now refused outright
    server = FakeServer(monkeypatch)
    for now in (BEFORE_INSTANT, AT_INSTANT):
        with pytest.raises(core.EvaluationGuardError, match="take no override"):
            run(evidence_root, now=now, cities=["AUSTIN"], params=SMALL,
                guard_cfg=core.GuardConfig(override_reason="rehearsal of the evaluation day"))
    assert server.calls == [] and not os.path.exists(evidence_root)


def test_development_override_is_recorded_in_the_report(evidence_root, stub_models):
    report = run(evidence_root, now="2026-10-13T08:00:00Z", cities=["AUSTIN"], frame_provider=dev_provider,
                 model_loader=loader_for(stub_models), window=DEV_WINDOW, params=SMALL,
                 guard_cfg=core.GuardConfig(override_reason="rehearsal on development data"))
    assert report["basis"] == "development"
    assert report["guard"]["override_reason"] == "rehearsal on development data"
    md = open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()
    assert "Override: rehearsal on development data" in md and "Round: v4-read1" in md


def test_nondefault_parameter_in_a_fresh_run_is_refused_and_no_override_helps(evidence_root, stub_models):
    with pytest.raises(ValueError, match="PD-15"):
        injected_run(evidence_root, stub_models, params=SMALL)
    with pytest.raises(core.EvaluationGuardError, match="take no override"):
        injected_run(evidence_root, stub_models, params=SMALL, guard_cfg=core.GuardConfig(override_reason="smaller"))
    assert not os.path.exists(evidence_root)


def test_second_fresh_run_is_refused_without_override(evidence_root, stub_models):
    first = injected_run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND"])
    assert first["basis"] == "FRESH"
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        injected_run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND"], now="2026-11-01T00:00:05Z")
    assert len(os.listdir(evidence_root)) == 1
    # an "owner-approved rerun" text no longer reopens the one-shot read
    with pytest.raises(core.EvaluationGuardError, match="take no override"):
        injected_run(evidence_root, stub_models, cities=["AUSTIN"], now="2026-11-01T00:00:09Z",
                     guard_cfg=core.GuardConfig(override_reason="owner-approved rerun"))
    assert len(os.listdir(evidence_root)) == 1


def test_a_run_that_crashed_after_its_guard_still_blocks_the_next_one(evidence_root, stub_models):
    leaky = {"leaky": lambda f: f["truth_wind_speed"].to_numpy(dtype=float)}
    with pytest.raises(core.LeakageProbeError):
        injected_run(evidence_root, stub_models, cities=["AUSTIN"], extra_probe_arms=leaky)
    (run_dir,) = os.listdir(evidence_root)
    assert os.path.isfile(os.path.join(evidence_root, run_dir, "run_started.json"))
    assert not os.path.exists(os.path.join(evidence_root, run_dir, "report.json"))
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        injected_run(evidence_root, stub_models, cities=["AUSTIN"], now="2026-11-01T00:01:00Z")


def test_a_prior_shadow_logs_marker_does_not_block_the_port(evidence_root, stub_models):
    prior = os.path.join(evidence_root, "shadow_logs_20261101T000000Z")
    os.makedirs(prior)
    with open(os.path.join(prior, "run_started.json"), "w", encoding="utf-8") as fh:
        json.dump({"row_source": "shadow_logs", "basis": "FRESH"}, fh)
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"], now="2026-11-01T00:02:00Z")
    assert report["guard"]["prior_fresh_runs"] == []


# --------------------------------------------------------------------------
# Production provider, network-free
# --------------------------------------------------------------------------

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def test_production_provider_records_two_requests_and_redirects_the_cache(monkeypatch, tmp_path):
    server = FakeServer(monkeypatch)
    ev = str(tmp_path / "evidence" / "run")
    os.makedirs(ev)
    before = config.FORECAST_EXPERIMENT_CACHE_DIR
    frame, weather, meta = conf.production_frame_provider("AUSTIN", evidence_dir=ev)
    assert len(server.calls) == 2
    archive_call, prev_call = server.calls
    assert archive_call[0] == open_meteo_provider.OPEN_METEO_ARCHIVE_BASE
    assert prev_call[0] == open_meteo_forecast_provider.OPEN_METEO_PREVIOUS_RUNS_BASE
    for _, params, _ in server.calls:
        assert params["start_date"] == FETCH_START and params["end_date"] == FETCH_END
    assert archive_call[1] == core.build_archive_request("AUSTIN", FETCH_START, FETCH_END)[1]
    assert prev_call[1] == conf.build_previous_runs_request("AUSTIN", FETCH_START, FETCH_END)[1]
    assert prev_call[1]["models"] == "gfs_seamless" and "previous_day1" in prev_call[1]["hourly"]
    metas = sorted(f for f in os.listdir(os.path.join(ev, "http")) if f.endswith(".meta.json"))
    assert metas == ["01_AUSTIN.meta.json", "02_AUSTIN.meta.json"]
    for stem in ("01_AUSTIN", "02_AUSTIN"):
        m = json.load(open(os.path.join(ev, "http", stem + ".meta.json"), encoding="utf-8"))
        body = os.path.join(ev, "http", stem + ".body")
        assert m["sha256"] == sha(body) and m["byte_length"] == os.path.getsize(body)
        assert m["retrieval_started_at_utc"] <= m["retrieval_completed_at_utc"]
    frames = os.listdir(os.path.join(ev, "frames"))
    assert frames == [f"anchored_pair_frame_AUSTIN_{FETCH_START}_{FETCH_END}_lead24_previous_runs.csv"]
    assert not os.path.exists(before)
    assert config.FORECAST_EXPERIMENT_CACHE_DIR == before
    assert weather["datetime_utc"].min() == pd.Timestamp("2026-09-28T00:00:00Z")
    assert weather["datetime_utc"].max() == pd.Timestamp("2026-10-24T23:00:00Z")
    assert frame["datetime_utc"].min() == pd.Timestamp("2026-09-29T00:00:00Z")
    assert meta["fetch_window"] == [FETCH_START, FETCH_END]


def test_cache_dir_is_restored_after_an_exception(monkeypatch, tmp_path):
    FakeServer(monkeypatch, fail_previous={"MIDLAND"})
    ev = str(tmp_path / "evidence" / "run")
    os.makedirs(ev)
    before = config.FORECAST_EXPERIMENT_CACHE_DIR
    with pytest.raises(conf.FrameFetchError):
        conf.production_frame_provider("MIDLAND", evidence_dir=ev)
    assert config.FORECAST_EXPERIMENT_CACHE_DIR == before
    assert not os.path.exists(before)


def test_preexisting_redirected_cache_refuses_before_anchored_pair_frame(monkeypatch, tmp_path):
    server = FakeServer(monkeypatch)
    ev = str(tmp_path / "evidence" / "run")
    os.makedirs(os.path.join(ev, "frames"))
    name = f"anchored_pair_frame_AUSTIN_{FETCH_START}_{FETCH_END}_lead24_previous_runs.csv"
    with open(os.path.join(ev, "frames", name), "w", encoding="utf-8") as fh:
        fh.write("datetime_utc\n")
    called = []
    real = forecast_experiment.anchored_pair_frame
    monkeypatch.setattr(forecast_experiment, "anchored_pair_frame",
                        lambda *a, **k: called.append(a) or real(*a, **k))
    with pytest.raises(core.EvaluationGuardError, match="already exists"):
        conf.production_frame_provider("AUSTIN", evidence_dir=ev)
    assert called == [] and server.calls == []


def test_production_provider_rejects_any_other_window(tmp_path):
    with pytest.raises(ValueError, match="pre-registered fetch window"):
        conf.production_frame_provider("AUSTIN", evidence_dir=str(tmp_path), window=("2026-09-30", "2026-10-04"))
    with pytest.raises(ValueError, match="default window"):
        conf.run_confirmation(cities=["AUSTIN"], guard_cfg=core.GuardConfig(), evidence_root=str(tmp_path / "ev"),
                              now=AT_INSTANT, window=DEV_WINDOW)


def test_full_production_run_at_the_instant_with_default_parameters(monkeypatch, evidence_root, model_dir):
    server = FakeServer(monkeypatch)
    report = run(evidence_root, now=AT_INSTANT)
    assert report["basis"] == "FRESH" and report["guard"]["override_reason"] is None and report["guard"]["defaults_used"]
    assert len(server.calls) == 8
    for city in CITIES:
        assert len(server.calls_for(city)) == 2
        assert report["per_city"][city]["n_scored"] == {name: 100 for name in core.CANDIDATES}
    ev = report["evidence_dir"]
    assert len([f for f in os.listdir(os.path.join(ev, "http")) if f.endswith(".body")]) == 8
    assert len(os.listdir(os.path.join(ev, "frames"))) == 4
    assert not os.path.exists(config.FORECAST_EXPERIMENT_CACHE_DIR)
    assert len(report["evidence"]) == 8 and all(len(e["sha256"]) == 64 for e in report["evidence"])
    assert report["provenance"]["freeze_check"]["model_freeze"] == core.MODEL_FREEZE.isoformat()
    assert len(report["provenance"]["artifacts"]) == 12
    assert all(len(a["sha256"]) == 64 for a in report["provenance"]["artifacts"])


def test_one_city_previous_runs_503_is_named_and_not_retried(monkeypatch, evidence_root, model_dir):
    server = FakeServer(monkeypatch, fail_previous={"MIDLAND"})
    report = run(evidence_root, now=AT_INSTANT)
    assert list(report["failed_cities"]) == ["MIDLAND"]
    assert report["failed_cities"]["MIDLAND"]["stage"] == "frame_fetch_failed"
    assert len(server.calls_for("MIDLAND")) == 2  # archive, then previous-runs once: no retry
    assert all(len(server.calls_for(c)) == 2 for c in CITIES)
    http_dir = os.path.join(report["evidence_dir"], "http")
    midland = sorted(f for f in os.listdir(http_dir) if f.endswith("_MIDLAND.meta.json"))
    assert len(midland) == 2  # numbered run-wide, so after the first two cities' four files
    statuses = [json.load(open(os.path.join(http_dir, f), encoding="utf-8"))["status_code"] for f in midland]
    assert statuses == [200, 503]
    assert os.path.isfile(os.path.join(http_dir, midland[0].replace(".meta.json", ".body")))  # archive body kept
    assert report["per_city"]["MIDLAND"]["excluded_by_reason"] == {"city_failed:frame_fetch_failed": 1}
    for city in ("AUSTIN", "CORPUS_CHRISTI", "EL_PASO"):
        assert report["per_city"][city]["n_scored"]["raw_forecast"] == 100
    assert len(report["family"]["comparisons"]) == 9
    assert "MIDLAND" in open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()


# --------------------------------------------------------------------------
# Scored rows
# --------------------------------------------------------------------------

def test_scored_rows_are_exact_lead_fresh_and_at_most_100():
    prepared, diag = conf.prepare_city_frame(recon_frame("AUSTIN"), "AUSTIN")
    assert len(prepared) == 100 == diag["n_expected_slots"] == diag["n_scored_slots"]
    forecast_experiment.assert_exact_lead(prepared, lead_hours=24)
    vt = prepared["datetime_utc"]
    assert (vt.dt.hour % 6 == 0).all()
    assert vt.min() == pd.Timestamp("2026-09-30T00:00:00Z") and vt.max() == pd.Timestamp("2026-10-24T18:00:00Z")
    assert (vt < core.VALID_TIME_CUTOFF_DEFAULT).all() and (vt >= core.FRESH_BASIS_START).all()
    assert diag["missing_from_reconstruction"] == [] and diag["anchor_after_fit_end"]
    fit_end = pd.Timestamp(fit_models.train_val_window_end(), tz="UTC")
    assert prepared["anchor_datetime_utc"].min() > fit_end
    # the first FRESH day is kept (F5): 2026-09-30T00Z is scored, its anchor is 2026-09-29T00Z
    assert prepared.iloc[0]["anchor_datetime_utc"] == pd.Timestamp("2026-09-29T00:00:00Z")


def test_missing_slots_and_null_weather_rows_are_counted_never_imputed():
    frame = recon_frame("AUSTIN")
    drop_a = pd.Timestamp("2026-10-05T12:00:00Z")
    drop_b = pd.Timestamp("2026-10-06T06:00:00Z")
    frame = frame[frame["datetime_utc"] != drop_a].copy()
    frame.loc[frame["datetime_utc"] == drop_b, "fcst_wind_speed"] = np.nan
    prepared, diag = conf.prepare_city_frame(frame, "AUSTIN")
    assert len(prepared) == 98 and diag["n_missing_from_reconstruction"] == 2
    assert sorted(diag["missing_from_reconstruction"]) == [drop_a.isoformat(), drop_b.isoformat()]
    assert diag["n_rows_dropped_null_weather"] == 1
    assert drop_a not in set(prepared["datetime_utc"]) and drop_b not in set(prepared["datetime_utc"])


def test_an_anchor_inside_the_artifact_fit_window_is_refused():
    frame = make_frame("AUSTIN", "2026-03-10", "2026-03-20 23:00")
    with pytest.raises(conf.ReconstructionError, match="fit window"):
        conf.prepare_city_frame(frame, "AUSTIN", window=conf.ScoredWindow(pd.Timestamp("2026-03-12", tz="UTC"),
                                                                           pd.Timestamp("2026-03-20", tz="UTC")))


def test_a_non_24_hour_anchor_gap_is_refused():
    frame = recon_frame("AUSTIN")
    frame["anchor_datetime_utc"] = frame["anchor_datetime_utc"] + pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match="anchor gap"):
        conf.prepare_city_frame(frame, "AUSTIN")


# --------------------------------------------------------------------------
# Candidates
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def austin_inputs():
    frame = recon_frame("AUSTIN")
    weather = archive_weather("AUSTIN", "2026-09-28", "2026-10-24 23:00")
    return frame, weather


def predictions(city, frame, weather, models):
    prepared, _ = conf.prepare_city_frame(frame, city)
    preds, diag = conf.candidate_predictions(prepared, weather, city, models)
    return prepared, preds, diag


def test_truth_raw_and_persistence_match_an_independent_city_point_computation(austin_inputs, stub_models):
    frame, weather = austin_inputs
    prepared, preds, _ = predictions("AUSTIN", frame, weather, stub_models["AUSTIN"])
    vt = preds.index
    w = weather.set_index("datetime_utc")
    anchor = w.loc[preds["anchor_time"]]
    truth = independent_amps({c: w.loc[vt, c] for c in ("air_temp", "wind_speed", "wind_direction", "solar_radiation")}, "AUSTIN")
    persistence = independent_amps({c: anchor[c] for c in ("air_temp", "wind_speed", "wind_direction", "solar_radiation")}, "AUSTIN")
    fc = prepared
    raw = independent_amps({"air_temp": fc["fcst_air_temp"], "wind_speed": fc["fcst_wind_speed"],
                            "wind_direction": fc["fcst_wind_direction"], "solar_radiation": fc["fcst_solar_radiation"]}, "AUSTIN")
    assert np.allclose(preds["truth_amps"], truth, atol=1e-9, rtol=0)
    assert np.allclose(preds["raw_forecast"], raw, atol=1e-9, rtol=0)
    assert np.allclose(preds["persistence_24h"], persistence, atol=1e-9, rtol=0)
    # the corridor-geometry sentinels in the input frame were never used
    assert not np.allclose(preds["truth_amps"], 999.0)


def test_dlr_amps_columns_are_never_read(austin_inputs, stub_models):
    frame, weather = austin_inputs
    _, base, _ = predictions("AUSTIN", frame, weather, stub_models["AUSTIN"])
    nan_frame = frame.copy()
    for col in [c for c in nan_frame.columns if c.endswith("_dlr_amps")]:
        nan_frame[col] = np.nan
    _, other, _ = predictions("AUSTIN", nan_frame, weather, stub_models["AUSTIN"])
    cols = ["truth_amps", *core.CANDIDATES]
    assert np.array_equal(base[cols].to_numpy(), other[cols].to_numpy(), equal_nan=True)


def test_wind_and_cooling_equal_the_live_methods_row_by_row(austin_inputs, stub_models):
    frame, weather = austin_inputs
    models = stub_models["AUSTIN"]
    prepared, preds, _ = predictions("AUSTIN", frame, weather, models)
    point = city_point.city_point("AUSTIN")
    wind_method = pipeline.WindCorrectionShadowMethod(models[conf.WIND])
    cooling_method = pipeline.CoolingCorrectionShadowMethod(models[conf.COOLING])
    for i in (0, 1, 37, 60, 99):
        one = prepared.iloc[[i]]
        assert preds[conf.WIND].iloc[i] == pytest.approx(wind_method.predict(one, point), abs=1e-9, rel=0)
        assert preds[conf.COOLING].iloc[i] == pytest.approx(cooling_method.predict(one, point), abs=1e-9, rel=0)


def test_reference_features_equal_the_training_matrix_at_the_anchor(austin_inputs, stub_models):
    frame, weather = austin_inputs
    models = stub_models["AUSTIN"]
    _, preds, diag = predictions("AUSTIN", frame, weather, models)
    arm5 = fit_models.weather_to_arm5_frame(weather, "AUSTIN")
    X, _ = forecast_training.build_training_matrix(arm5, horizon_minutes=1440)
    expected = models[conf.REFERENCE].predict(X.loc[pd.DatetimeIndex(preds["anchor_time"])].to_numpy(dtype=float))
    assert np.allclose(preds[conf.REFERENCE].to_numpy(), expected, atol=1e-9, rtol=0)
    assert diag["reference_feature_gaps"]["n_rows"] == 0


def test_reference_prediction_ignores_truth_after_its_anchor(stub_models):
    frame = recon_frame("AUSTIN")
    weather = archive_weather("AUSTIN", "2026-09-28", "2026-10-24 23:00")
    models = stub_models["AUSTIN"]
    _, base, _ = predictions("AUSTIN", frame, weather, models)
    cut = pd.Timestamp("2026-10-14T00:00:00Z")  # perturb truth strictly after this hour, in both sources
    f2, w2 = frame.copy(), weather.copy()
    for col, delta in (("air_temp", 3.0), ("wind_speed", 1.0), ("solar_radiation", 50.0)):
        w2.loc[w2["datetime_utc"] > cut, col] = w2.loc[w2["datetime_utc"] > cut, col] + delta
        f2.loc[f2["datetime_utc"] > cut, f"truth_{col}"] = f2.loc[f2["datetime_utc"] > cut, f"truth_{col}"] + delta
    _, shifted, _ = predictions("AUSTIN", f2, w2, models)
    unaffected = base["anchor_time"] <= cut
    assert unaffected.sum() > 50
    assert np.array_equal(base.loc[unaffected, conf.REFERENCE].to_numpy(), shifted.loc[unaffected, conf.REFERENCE].to_numpy())
    assert not np.allclose(base.loc[~unaffected, conf.REFERENCE], shifted.loc[~unaffected, conf.REFERENCE])


def test_a_missing_hour_makes_exactly_the_dependent_rows_reference_features_missing(austin_inputs, stub_models):
    frame, weather = austin_inputs
    removed = [pd.Timestamp("2026-10-10T03:00:00Z"), pd.Timestamp("2026-10-21T15:00:00Z")]
    nulled = pd.Timestamp("2026-10-23T09:00:00Z")
    w2 = weather[~weather["datetime_utc"].isin(removed)].copy()
    w2.loc[w2["datetime_utc"] == nulled, "wind_speed"] = np.nan
    prepared, preds, diag = predictions("AUSTIN", frame, w2, stub_models["AUSTIN"])
    bad_hours = removed + [nulled]
    expected = [a for a in preds["anchor_time"] if any(a - pd.Timedelta(hours=6) <= h <= a for h in bad_hours)]
    flagged = preds.loc[preds[f"{conf.REFERENCE}__excl"].notna(), "anchor_time"].tolist()
    assert len(expected) == 3 and flagged == expected
    assert preds.loc[preds[f"{conf.REFERENCE}__excl"].notna(), conf.REFERENCE].isna().all()
    assert preds[conf.REFERENCE].notna().sum() == len(preds) - 3
    assert (preds[f"{conf.REFERENCE}__excl"].dropna() == conf.REASON_REFERENCE_FEATURES).all()
    assert diag["reference_feature_gaps"]["n_rows"] == 3
    assert diag["archive_vs_frame_truth"]["archive_null_hours_dropped"] == [nulled.isoformat()]


def test_frame_truth_that_disagrees_with_the_archive_raises(austin_inputs, stub_models):
    frame, weather = austin_inputs
    f2 = frame.copy()
    f2.loc[f2["datetime_utc"] == pd.Timestamp("2026-10-12T06:00:00Z"), "truth_wind_speed"] += 0.5
    prepared, _ = conf.prepare_city_frame(f2, "AUSTIN")
    with pytest.raises(conf.ReconstructionError, match="differs from the recorded archive"):
        conf.candidate_predictions(prepared, weather, "AUSTIN", stub_models["AUSTIN"])


def test_a_prepared_hour_absent_from_the_archive_raises(austin_inputs, stub_models):
    frame, weather = austin_inputs
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN")
    gone = weather[weather["datetime_utc"] != pd.Timestamp("2026-10-12T06:00:00Z")]
    with pytest.raises(conf.ReconstructionError, match="absent from the archive"):
        conf.candidate_predictions(prepared, gone, "AUSTIN", stub_models["AUSTIN"])


def test_a_row_the_cooling_physics_rejects_loses_only_that_row(austin_inputs, stub_models):
    frame, weather = austin_inputs
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN")

    real = fcm.predict_cooling_correction
    bad_time = pd.Timestamp("2026-10-15T12:00:00Z")

    def picky(model, frame_):
        if (pd.to_datetime(frame_["datetime_utc"], utc=True) == bad_time).any():
            raise ValueError("predicted a non-positive convective term")
        return real(model, frame_)

    import unittest.mock as mock
    with mock.patch.object(fcm, "predict_cooling_correction", picky):
        preds, diag = conf.candidate_predictions(prepared, weather, "AUSTIN", stub_models["AUSTIN"])
    assert preds[conf.COOLING].isna().sum() == 1 and np.isnan(preds.loc[bad_time, conf.COOLING])
    assert preds.loc[bad_time, f"{conf.COOLING}__excl"] == conf.REASON_FAILED
    assert preds[conf.WIND].notna().all() and diag["candidate_failed_rows"][conf.COOLING] == 1


# --------------------------------------------------------------------------
# Leakage probe
# --------------------------------------------------------------------------

def test_leakage_probe_passes_for_genuine_candidates_and_the_oracle_changes(austin_inputs, stub_models):
    frame, _ = austin_inputs
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN")
    result = conf.leakage_probe(prepared, "AUSTIN", stub_models["AUSTIN"])
    assert result["passed"] and result["oracle_changed"] and result["oracle_max_abs_change_amps"] > 0
    assert set(result["arms_checked"]) == {"raw_forecast", "persistence_24h", conf.WIND, conf.COOLING}


def test_leakage_probe_catches_a_candidate_reading_truth_and_writes_no_report(evidence_root, stub_models):
    frame, _ = recon_frame("AUSTIN"), None
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN")
    leaky = {"leaky_arm": lambda f: f["truth_wind_speed"].to_numpy(dtype=float)}
    with pytest.raises(core.LeakageProbeError, match="leaky_arm"):
        conf.leakage_probe(prepared, "AUSTIN", stub_models["AUSTIN"], extra_arms=leaky)
    with pytest.raises(core.LeakageProbeError):
        injected_run(evidence_root, stub_models, cities=["AUSTIN"], extra_probe_arms=leaky)
    for root, _, files in os.walk(evidence_root):
        assert "report.json" not in files and "report.md" not in files


def test_leakage_probe_without_a_working_oracle_fails(austin_inputs, stub_models, monkeypatch):
    frame, _ = austin_inputs
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN")
    monkeypatch.setitem(forecast_experiment.NON_FITTED_ARMS, forecast_experiment.ORACLE_ARM_NAME,
                        lambda geometry: (lambda f: f["fcst_air_temp"].to_numpy(dtype=float) * 0.0))
    with pytest.raises(core.LeakageProbeError, match="positive control"):
        conf.leakage_probe(prepared, "AUSTIN", stub_models["AUSTIN"])


# --------------------------------------------------------------------------
# Model source
# --------------------------------------------------------------------------

def test_fresh_basis_loads_artifacts_through_load_correction_model(monkeypatch, evidence_root, model_dir):
    loaded = []
    real = pipeline.load_correction_model
    monkeypatch.setattr(pipeline, "load_correction_model", lambda c, m: loaded.append((c, m)) or real(c, m))
    report = run(evidence_root, now=AT_INSTANT, cities=["AUSTIN"], frame_provider=injected_provider())
    assert sorted(loaded) == sorted(("AUSTIN", m) for m in conf.MODEL_METHODS)
    assert report["config"]["model_loader"] == "load_correction_model"


def test_missing_artifact_is_candidate_unavailable_with_the_file_not_found_text(monkeypatch, evidence_root, model_dir):
    os.remove(os.path.join(model_dir, f"{conf.COOLING}_MIDLAND.joblib"))
    report = run(evidence_root, now=AT_INSTANT, cities=["MIDLAND"], frame_provider=injected_provider())
    block = report["per_city"]["MIDLAND"]
    assert block["n_scored"][conf.COOLING] == 0 and block["n_scored"][conf.WIND] == 100
    assert block["candidate_exclusions"][conf.COOLING] == {"candidate_unavailable": 100}
    reason = report["diagnostics"]["MIDLAND"]["unavailable_reasons"][conf.COOLING]
    assert "no persisted" in reason and "MIDLAND" in reason
    assert report["provenance"]["artifacts"][1]["sha256"] == "missing"
    cooling = next(c for c in report["family"]["comparisons"] if (c["a"], c["b"]) == (conf.COOLING, "raw_forecast"))
    assert cooling["headline"]["outcome"] == "insufficient_data"


def test_development_basis_requires_an_injected_model_loader(evidence_root):
    with pytest.raises(ValueError, match="must not be scored on frozen periods"):
        run(evidence_root, now="2026-10-13T08:00:00Z", cities=["AUSTIN"], frame_provider=dev_provider,
            window=DEV_WINDOW, params=SMALL)
    assert not os.path.exists(evidence_root)


def test_development_basis_run_matches_numpy_and_carries_the_banner(evidence_root, stub_models):
    report = run(evidence_root, now="2026-10-13T08:00:00Z", cities=["AUSTIN", "EL_PASO"], frame_provider=dev_provider,
                 model_loader=loader_for(stub_models), window=DEV_WINDOW, params=SMALL)
    assert report["basis"] == "development"
    md = open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()
    assert "DEVELOPMENT DATA - not a confirmation result" in md
    for city in ("AUSTIN", "EL_PASO"):
        frame = dev_provider(city, evidence_dir="")[0]
        weather = archive_weather(city, "2026-03-30", "2026-04-10 23:00").set_index("datetime_utc")
        vt = pd.date_range("2026-04-01", "2026-04-10 18:00", freq="6h", tz="UTC")
        assert report["per_city"][city]["n_scored"]["raw_forecast"] == len(vt) == 40
        w_truth = weather.loc[vt]
        truth = independent_amps({c: w_truth[c] for c in ("air_temp", "wind_speed", "wind_direction", "solar_radiation")}, city)
        fr = frame.set_index("datetime_utc").loc[vt]
        raw = independent_amps({"air_temp": fr["fcst_air_temp"], "wind_speed": fr["fcst_wind_speed"],
                                "wind_direction": fr["fcst_wind_direction"], "solar_radiation": fr["fcst_solar_radiation"]}, city)
        err = raw - truth
        m = report["per_city"][city]["metrics"]["raw_forecast"]
        assert m["bias"] == pytest.approx(err.mean(), abs=1e-9)
        assert m["mae"] == pytest.approx(np.abs(err).mean(), abs=1e-9)
        assert m["rmse"] == pytest.approx(np.sqrt((err ** 2).mean()), abs=1e-9)
        assert m["median_abs_error"] == pytest.approx(np.median(np.abs(err)), abs=1e-9)
        assert m["overprediction_rate"] == pytest.approx((err > 0).mean(), abs=1e-12)
    pair = next(c for c in report["family"]["comparisons"] if (c["a"], c["b"]) == (conf.WIND, "raw_forecast"))
    assert pair["n_paired"] == 80 and pair["row_source"] == "reconstructed_frames"


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------

def test_report_shape_flags_and_provenance(evidence_root, stub_models, model_dir):
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND"])
    saved = json.load(open(os.path.join(report["evidence_dir"], "report.json"), encoding="utf-8"))
    assert saved["row_source"] == "reconstructed_frames" and saved["basis"] == "FRESH"
    for key in ("guard", "config", "provenance", "sample_size", "family", "decision", "per_city", "exclusions",
                "validity_flags", "diagnostics", "not_measured", "planner_defaults", "owner_pending", "evidence"):
        assert key in saved, key
    assert len(saved["family"]["comparisons"]) == 9
    assert all(c["row_source"] == "reconstructed_frames" for c in saved["family"]["comparisons"])
    assert saved["decision"]["row_source"] == "reconstructed_frames" and saved["decision"]["label"] == "headline decision"
    flags = {f["id"]: f for f in saved["validity_flags"]}
    assert flags["V4"]["applies"]
    for fid in ("V1", "V2", "V3", "V5", "V6"):
        assert not flags[fid]["applies"] and flags[fid]["not_applicable_reason"]
    assert saved["not_measured"] == core.NOT_MEASURED_STATEMENT
    assert len(saved["provenance"]["artifacts"]) == 6  # two cities x three methods
    md = open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()
    assert md.index("## Sample size") < md.index("## Headline family") < md.index("## Decision (headline decision)")
    assert core.NOT_MEASURED_STATEMENT in md
    diag = saved["diagnostics"]["AUSTIN"]
    assert diag["leakage_probe"]["passed"] and diag["leakage_probe"]["oracle_changed"]
    assert diag["missing_slots"] == [] and diag["reference_feature_gaps"]["n_rows"] == 0
    assert diag["archive_vs_frame_truth"]["max_abs_diff_weather"] == 0.0
    assert saved["exclusions"]["AUSTIN"]["accounting"]["expected_slots_equals_scored_plus_missing"]
    assert saved["config"]["model_source"].startswith("the 12 frozen per-city artifacts")


def test_report_lists_twelve_artifact_hashes_for_four_cities(evidence_root, stub_models, model_dir):
    report = injected_run(evidence_root, stub_models)
    arts = report["provenance"]["artifacts"]
    assert len(arts) == 12 and all(len(a["sha256"]) == 64 for a in arts)
    assert {(a["city"], a["method"]) for a in arts} == {(c, m) for c in CITIES for m in conf.MODEL_METHODS}


def test_missing_slots_flow_into_the_report(evidence_root, stub_models):
    drop = pd.Timestamp("2026-10-05T12:00:00Z")
    provider = injected_provider(frame_edit=lambda c, f: f[f["datetime_utc"] != drop] if c == "AUSTIN" else f)
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND"], frame_provider=provider)
    assert report["per_city"]["AUSTIN"]["excluded_by_reason"] == {"missing_from_reconstruction": 1}
    assert report["diagnostics"]["AUSTIN"]["missing_slots"] == [drop.isoformat()]
    assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 99
    assert report["per_city"]["MIDLAND"]["n_scored"]["raw_forecast"] == 100


def test_rows_at_or_after_the_cutoff_are_never_scored(evidence_root, stub_models):
    extra = lambda c, f: pd.concat([f, make_frame(c, "2026-10-25 00:00", "2026-10-28 00:00")], ignore_index=True)
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"], frame_provider=injected_provider(frame_edit=extra))
    assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 100


def test_a_structural_failure_in_one_city_is_named_and_the_others_are_scored(evidence_root, stub_models):
    def broken(city, frame):
        return frame.drop(columns=["fcst_wind_speed"]) if city == "EL_PASO" else frame
    report = injected_run(evidence_root, stub_models, frame_provider=injected_provider(frame_edit=broken))
    assert list(report["failed_cities"]) == ["EL_PASO"]
    assert "fcst_wind_speed" in report["failed_cities"]["EL_PASO"]["error"]
    assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 100


def test_unsigned_status_is_labelled_exploratory(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"])
    assert any(core.EXPLORATORY_STATEMENT in s for s in report["decision"]["statements"])
    # a separate evidence root: the one-shot rule would refuse a second FRESH run in the first one, and no
    # override text can reopen it
    signed = injected_run(evidence_root + "_signed", stub_models, cities=["AUSTIN"], protocol_status="signed",
                          now="2026-11-01T00:05:00Z")
    assert not any(core.EXPLORATORY_STATEMENT in s for s in signed["decision"]["statements"])


# --------------------------------------------------------------------------
# Dry run and CLI
# --------------------------------------------------------------------------

def test_dry_run_plans_eight_requests_and_twelve_artifacts_without_side_effects(evidence_root, model_dir, monkeypatch, tmp_path):
    out = str(tmp_path / "dry.json")
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp("2026-10-13T08:00:00Z"))
    assert conf.main(["--dry-run", "--evidence-root", evidence_root, "--out", out]) == 0
    result = json.load(open(out, encoding="utf-8"))
    assert set(result) >= {"guard", "planned_requests", "artifacts", "freeze_check", "evidence_root"}
    assert result["guard"]["would_refuse"] is True and "evaluation instant" in result["guard"]["reason"]
    assert len(result["planned_requests"]) == 8
    assert {(r["city"], r["label"]) for r in result["planned_requests"]} == {(c, l) for c in CITIES for l in ("archive", "previous_runs")}
    assert len(result["artifacts"]) == 12 and all(len(a["sha256"]) == 64 for a in result["artifacts"])
    assert result["freeze_check"]["model_freeze"] == core.MODEL_FREEZE.isoformat()
    assert not os.path.exists(evidence_root)
    assert not os.path.exists(config.FORECAST_EXPERIMENT_CACHE_DIR)


def test_dry_run_planned_requests_equal_what_the_provider_sends(monkeypatch, model_dir, evidence_root, tmp_path):
    plan = {(r["city"], r["label"]): r for r in conf.dry_run(
        cities=CITIES, guard_cfg=core.GuardConfig(), evidence_root=evidence_root,
        now="2026-10-13T08:00:00Z")["planned_requests"]}
    server = FakeServer(monkeypatch)
    ev = str(tmp_path / "evidence" / "run")
    os.makedirs(ev)
    conf.production_frame_provider("EL_PASO", evidence_dir=ev)
    (a_url, a_params, _), (p_url, p_params, _) = server.calls
    assert plan[("EL_PASO", "archive")]["url"] == a_url and plan[("EL_PASO", "archive")]["params"] == a_params
    assert plan[("EL_PASO", "previous_runs")]["url"] == p_url and plan[("EL_PASO", "previous_runs")]["params"] == p_params


def test_dry_run_says_it_would_not_refuse_at_the_instant(evidence_root, model_dir):
    result = conf.dry_run(cities=CITIES, guard_cfg=core.GuardConfig(), evidence_root=evidence_root, now=AT_INSTANT)
    assert result["guard"] == {"would_refuse": False, "reason": None}
    assert result["expected_slots_per_city"] == 100


def test_dry_run_reports_a_prior_fresh_run(evidence_root, model_dir):
    prior = os.path.join(evidence_root, "reconstructed_frames_20261101T000000Z")
    os.makedirs(prior)
    with open(os.path.join(prior, "run_started.json"), "w", encoding="utf-8") as fh:
        json.dump({"row_source": "reconstructed_frames", "basis": "FRESH"}, fh)
    result = conf.dry_run(cities=CITIES, guard_cfg=core.GuardConfig(), evidence_root=evidence_root, now="2026-12-01T00:00:00Z")
    assert result["guard"]["would_refuse"] is True and "second FRESH run" in result["guard"]["reason"]


def test_cli_has_no_row_gate_or_family_size_flags():
    for flag in ("--row-gate", "--family-size"):
        with pytest.raises(SystemExit):
            conf.build_parser().parse_args([flag, "1"])


def test_cli_unknown_city_exits_2(capsys):
    assert conf.main(["--dry-run", "--cities", "AUSTIN_CORPUS_CHRISTI"]) == 2
    assert "unknown cities" in capsys.readouterr().err


def test_cli_nondefault_parameter_in_a_fresh_run_is_refused(monkeypatch, evidence_root, capsys, tmp_path):
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp(AT_INSTANT))
    deciding = ["--vetoes", write_veto_files(tmp_path)[0], "--protocol-status", "signed"]
    assert conf.main(["--evidence-root", evidence_root, *deciding, "--block-lengths", "1", "2"]) == 2
    err = capsys.readouterr().err
    assert "refused" in err and "no override" in err
    assert conf.main(["--evidence-root", evidence_root, *deciding, "--block-lengths", "1", "2",
                      "--override-reason", "smaller blocks"]) == 2
    assert "no override" in capsys.readouterr().err
    assert not os.path.exists(evidence_root)


# --------------------------------------------------------------------------
# FRESH-cache spy (the AST check on the 590-row gate lives in forecast_shadow_decision_test.py)
# --------------------------------------------------------------------------

def test_the_cache_spy_would_fail_a_fresh_cache_read(tmp_path):
    real_path = "data/experiment/anchored_pair_frame_AUSTIN_2026-09-30_2026-10-04_lead24_previous_runs.csv"
    with pytest.raises(core.EvaluationGuardError):
        open(real_path)
    with pytest.raises(core.EvaluationGuardError):
        pd.read_csv(real_path)
    core.assert_not_fresh_experiment_cache(
        "data/experiment/anchored_pair_frame_AUSTIN_2024-01-20_2026-09-29_lead24_previous_runs.csv")


def test_no_evaluator_mode_opens_a_fresh_cache_file(monkeypatch, evidence_root, model_dir, tmp_path):
    # runs under the autouse spy: production provider through fake HTTP, injected provider, dry run
    FakeServer(monkeypatch)
    run(evidence_root, now=AT_INSTANT, cities=["AUSTIN"])
    conf.dry_run(cities=CITIES, guard_cfg=core.GuardConfig(), evidence_root=evidence_root, now=AT_INSTANT)


# --------------------------------------------------------------------------
# Signed v4 rounds, the veto record (SEL-03) and the v4 decision (07-07)
# --------------------------------------------------------------------------

def write_veto_files(tmp_path, *, ablation_vetoed=(), test_vetoed=(), name="vetoes.json"):
    """Two synthetic source reports and a veto record naming them with their sha256 values (the 07-11 shape)."""
    ab, te = tmp_path / "ablation_report.json", tmp_path / "test_report.json"
    ab.write_text(json.dumps({"synthetic": "ablation source report"}), encoding="utf-8")
    te.write_text(json.dumps({"synthetic": "test source report"}), encoding="utf-8")

    def section(path, vetoed):
        return {"report": str(path), "sha256": sha(str(path)),
                "vetoes": {c: {"vetoed": c in vetoed, "reasons": ["synthetic"] if c in vetoed else []}
                           for c in core.REAL_CANDIDATES}}

    record = {"protocol": "v4",
              "ablation": {**section(ab, ablation_vetoed), "ranking_invariant": True},
              "test": {**section(te, test_vetoed), "conductor_basis": "synthetic"},
              "created_at_utc": "2026-11-02T00:00:00Z"}
    path = tmp_path / name
    path.write_text(json.dumps(record), encoding="utf-8")
    return str(path), record, (ab, te)


def capture_main(monkeypatch, argv, *, now=AT_INSTANT):
    """Run main with the clock pinned and run_confirmation replaced by a recorder: nothing real can run."""
    seen = {}
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp(now))

    def fake_run(**kwargs):
        seen.update(kwargs)
        return {"evidence_dir": "stub-evidence-dir"}

    monkeypatch.setattr(conf, "run_confirmation", fake_run)
    return conf.main(argv), seen


def test_cli_lists_the_signed_rounds_and_takes_a_vetoes_path():
    args = conf.build_parser().parse_args([])
    assert args.round == core.DEFAULT_ROUND.name == "v4-read1" and args.vetoes is None
    help_text = conf.build_parser().format_help()
    for name in sorted(core.PROTOCOL_ROUNDS):
        assert name in help_text
    with pytest.raises(SystemExit):
        conf.build_parser().parse_args(["--round", "v3-final"])


@pytest.mark.parametrize("argv_tail", [
    ["--round", "v4-read1"],
    ["--round", "v4-read2"],
    ["--round", "v4-read1", "--protocol-status", "signed"],          # signed but no veto record
])
def test_a_deciding_round_without_a_veto_record_is_refused_before_anything_runs(monkeypatch, evidence_root, capsys, argv_tail):
    code, seen = capture_main(monkeypatch, [*argv_tail, "--evidence-root", evidence_root])
    assert code == 2 and seen == {}
    err = capsys.readouterr().err
    assert err.startswith("refused:") and "--vetoes" in err
    assert not os.path.exists(evidence_root)


def test_a_deciding_round_with_an_unsigned_status_is_refused_even_with_a_valid_veto_record(monkeypatch, evidence_root, capsys, tmp_path):
    vetoes_path = write_veto_files(tmp_path)[0]
    code, seen = capture_main(monkeypatch, ["--round", "v4-read1", "--vetoes", vetoes_path, "--evidence-root", evidence_root])
    assert code == 2 and seen == {}
    err = capsys.readouterr().err
    assert err.startswith("refused:") and "signed" in err
    assert not os.path.exists(evidence_root)


def test_a_tampered_source_report_refuses_the_run_at_the_cli(monkeypatch, evidence_root, capsys, tmp_path):
    vetoes_path, _, (ablation_report, _) = write_veto_files(tmp_path)
    ablation_report.write_text(json.dumps({"synthetic": "edited after the veto record was written"}), encoding="utf-8")
    code, seen = capture_main(monkeypatch, ["--round", "v4-read1", "--vetoes", vetoes_path, "--protocol-status", "signed",
                                            "--evidence-root", evidence_root])
    assert code == 2 and seen == {}
    err = capsys.readouterr().err
    assert err.startswith("refused:") and "sha256" in err and "ablation" in err
    assert not os.path.exists(evidence_root)


@pytest.mark.parametrize("round_name", ["v4-read1", "v4-read2"])
def test_a_valid_veto_record_and_a_signed_status_reach_run_confirmation_in_the_round_subroot(monkeypatch, evidence_root,
                                                                                           tmp_path, round_name):
    vetoes_path, record, _ = write_veto_files(tmp_path, ablation_vetoed=("ml_cooling_corrected",))
    code, seen = capture_main(monkeypatch, ["--round", round_name, "--vetoes", vetoes_path, "--protocol-status", "signed",
                                            "--evidence-root", evidence_root])
    assert code == 0
    assert seen["round_name"] == round_name and seen["protocol_status"] == "signed"
    assert seen["evidence_root"] == os.path.join(evidence_root, round_name)        # the one-shot rule is per round
    assert seen["guard_cfg"] == core.guard_for_round(round_name)
    assert seen["vetoes"]["ablation"]["vetoes"]["ml_cooling_corrected"]["vetoed"] is True
    assert seen["vetoes"]["file"]["sha256"] == sha(vetoes_path)
    assert not os.path.exists(evidence_root)


def test_the_descriptive_round_needs_no_veto_record_and_still_uses_its_own_subroot(monkeypatch, evidence_root):
    # D-03 gate (07-09): the late re-score needs a read-1 report recorded under an older rating config version
    write_read1_report(evidence_root, "v1-older-than-the-current-config")
    code, seen = capture_main(monkeypatch, ["--round", "v4-late-descriptive", "--evidence-root", evidence_root])
    assert code == 0 and seen["round_name"] == "v4-late-descriptive" and seen["vetoes"] is None
    assert seen["evidence_root"] == os.path.join(evidence_root, "v4-late-descriptive")


def test_dry_run_for_read_2_lists_requests_ending_2026_10_31_and_128_slots(tmp_path):
    out = str(tmp_path / "dry_r2.json")
    assert conf.main(["--dry-run", "--round", "v4-read2", "--out", out]) == 0
    result = json.load(open(out, encoding="utf-8"))
    assert result["round"] == "v4-read2" and result["expected_slots_per_city"] == 128
    assert len(result["planned_requests"]) == 8
    assert {r["params"]["end_date"] for r in result["planned_requests"]} == {"2026-10-31"}
    assert {r["params"]["start_date"] for r in result["planned_requests"]} == {"2026-09-28"}
    assert result["scored_window"][1] == "2026-11-01T00:00:00+00:00"


def test_dry_run_for_read_1_keeps_the_read_1_window(tmp_path):
    out = str(tmp_path / "dry_r1.json")
    assert conf.main(["--dry-run", "--round", "v4-read1", "--out", out]) == 0
    result = json.load(open(out, encoding="utf-8"))
    assert (result["round"], result["expected_slots_per_city"]) == ("v4-read1", 100)
    assert {r["params"]["end_date"] for r in result["planned_requests"]} == {"2026-10-24"}


# --- load_vetoes ---

def test_load_vetoes_accepts_a_matching_record_and_reports_its_own_sha256(tmp_path):
    path, record, _ = write_veto_files(tmp_path, ablation_vetoed=("ml_wind_corrected",), test_vetoed=("reference_ml_refit_24h",))
    loaded = conf.load_vetoes(path)
    assert loaded["ablation"]["vetoes"]["ml_wind_corrected"]["vetoed"] is True
    assert loaded["test"]["vetoes"]["reference_ml_refit_24h"]["vetoed"] is True
    assert loaded["test"]["vetoes"]["ml_wind_corrected"]["vetoed"] is False
    assert loaded["file"] == {"path": os.path.abspath(path), "sha256": sha(path)}
    assert loaded["ablation"]["ranking_invariant"] is True and loaded["test"]["conductor_basis"] == "synthetic"


def _edit_record(tmp_path, edit):
    path, record, files = write_veto_files(tmp_path)
    edit(record)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    return path


@pytest.mark.parametrize("label, edit, match", [
    ("ablation sha256 differs", lambda r: r["ablation"].update(sha256="0" * 64), "ablation.*sha256"),
    ("test sha256 differs", lambda r: r["test"].update(sha256="f" * 64), "test.*sha256"),
    ("ablation section missing", lambda r: r.pop("ablation"), "ablation"),
    ("test section missing", lambda r: r.pop("test"), "test"),
    ("vetoed flag is a string", lambda r: r["ablation"]["vetoes"]["ml_wind_corrected"].update(vetoed="no"), "bool"),
    ("vetoed flag is an integer", lambda r: r["test"]["vetoes"]["ml_cooling_corrected"].update(vetoed=0), "bool"),
    ("unknown candidate key", lambda r: r["ablation"]["vetoes"].update(raw_forecast={"vetoed": False}), "raw_forecast"),
    ("wrong-case candidate key", lambda r: r["test"]["vetoes"].update(ML_WIND_CORRECTED=r["test"]["vetoes"].pop("ml_wind_corrected")), "ML_WIND_CORRECTED"),
    ("a candidate is absent", lambda r: r["ablation"]["vetoes"].pop("reference_ml_refit_24h"), "reference_ml_refit_24h"),
    ("source report file is gone", lambda r: r["test"].update(report=r["test"]["report"] + ".gone"), "test.*report"),
    ("protocol is not v4", lambda r: r.update(protocol="v3"), "protocol"),
])
def test_load_vetoes_refuses_a_broken_record(tmp_path, label, edit, match):
    path = _edit_record(tmp_path, edit)
    with pytest.raises(ValueError, match=match):
        conf.load_vetoes(path)


def test_load_vetoes_refuses_a_file_that_is_not_a_json_object(tmp_path):
    for text in ("", "not json", "[1, 2]", "null"):
        p = tmp_path / "bad.json"
        p.write_text(text, encoding="utf-8")
        with pytest.raises(ValueError):
            conf.load_vetoes(str(p))
    with pytest.raises(ValueError, match="cannot read"):
        conf.load_vetoes(str(tmp_path / "does_not_exist.json"))


def test_load_vetoes_resolves_a_relative_report_path_against_the_base_dir(tmp_path):
    path, record, (ab, te) = write_veto_files(tmp_path)
    record["ablation"]["report"], record["test"]["report"] = ab.name, te.name
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    assert conf.load_vetoes(path, base_dir=str(tmp_path))["ablation"]["report"] == ab.name
    with pytest.raises(ValueError, match="report"):
        conf.load_vetoes(path, base_dir=str(tmp_path / "elsewhere"))


# --- run_confirmation: the veto record is checked before the guard ---

def test_a_fresh_run_without_a_veto_record_raises_before_the_guard_and_leaves_the_root_empty(monkeypatch, evidence_root):
    def boom(*a, **k):
        raise AssertionError("must not be reached: the veto record is checked before the guard")

    monkeypatch.setattr(core, "check_guard", boom)
    monkeypatch.setattr(core, "new_evidence_dir", boom)
    for round_name, now in (("v4-read1", AT_INSTANT), ("v4-read2", "2026-11-08T00:00:00Z")):
        with pytest.raises(ValueError, match="SEL-03"):
            conf.run_confirmation(cities=CITIES, guard_cfg=core.guard_for_round(round_name), evidence_root=evidence_root,
                                  now=now, vetoes=None)
    assert not os.path.exists(evidence_root)


def test_a_malformed_veto_record_given_directly_also_raises_before_the_guard(monkeypatch, evidence_root):
    monkeypatch.setattr(core, "check_guard", lambda *a, **k: (_ for _ in ()).throw(AssertionError("guard reached")))
    broken = no_veto_record()
    broken["test"]["vetoes"]["ml_wind_corrected"]["vetoed"] = "yes"
    with pytest.raises(ValueError, match="bool"):
        run(evidence_root, vetoes=broken)
    assert not os.path.exists(evidence_root)


def test_round_name_and_guard_must_agree(evidence_root):
    with pytest.raises(ValueError, match="round"):
        run(evidence_root, guard_cfg=core.guard_for_round("v4-read2"), round_name="v4-read1")


def test_the_report_and_config_record_the_round_and_the_veto_file_with_its_hash(evidence_root, stub_models, tmp_path):
    path, record, (ab, te) = write_veto_files(tmp_path)
    vetoes = conf.load_vetoes(path)
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"], vetoes=vetoes, protocol_status="signed")
    assert report["round"] == report["config"]["round"] == "v4-read1"
    src = report["config"]["vetoes"]
    assert src["path"] == os.path.abspath(path) and src["sha256"] == sha(path)
    assert src["ablation_report"] == {"report": str(ab), "sha256": sha(str(ab))}
    assert src["test_report"] == {"report": str(te), "sha256": sha(str(te))}
    assert report["vetoes"]["source"] == src and report["vetoes"]["record"]["ablation"]["vetoes"].keys() == set(core.REAL_CANDIDATES)
    saved = json.load(open(os.path.join(report["evidence_dir"], "report.json"), encoding="utf-8"))
    assert saved["vetoes"]["source"]["sha256"] == sha(path) and saved["round"] == "v4-read1"
    started = json.load(open(os.path.join(report["evidence_dir"], "run_started.json"), encoding="utf-8"))
    assert started["config"]["vetoes"]["sha256"] == sha(path)           # recorded before any row is read


def test_a_synthetic_record_is_recorded_as_injected_not_as_a_file(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"])
    assert report["config"]["vetoes"]["injected"] is True and report["config"]["vetoes"]["path"] is None


def test_a_development_run_without_a_veto_record_records_none(evidence_root, stub_models):
    report = run(evidence_root, now="2026-10-13T08:00:00Z", cities=["AUSTIN"], frame_provider=dev_provider,
                 model_loader=loader_for(stub_models), window=DEV_WINDOW, params=SMALL, vetoes=None)
    assert report["config"]["vetoes"] is None and report["vetoes"] is None and report["round"] == "v4-read1"


# --- the v4 decision in the headline port ---

def test_a_development_basis_run_decides_with_the_v4_rule_and_the_exploratory_statement(monkeypatch, evidence_root, stub_models):
    import forecast_shadow_decision_v4 as v4
    calls = []
    real = v4.apply_ship_rule_v4
    monkeypatch.setattr(v4, "apply_ship_rule_v4", lambda *a, **k: calls.append(k) or real(*a, **k))
    report = run(evidence_root, now="2026-10-13T08:00:00Z", cities=["AUSTIN", "EL_PASO"], frame_provider=dev_provider,
                 model_loader=loader_for(stub_models), window=DEV_WINDOW, params=SMALL, vetoes=None)
    (kwargs,) = calls
    assert kwargs["label"] == "headline" and kwargs["require_vetoes"] is False and kwargs["vetoes"] is None
    assert kwargs["round_name"] == "v4-read1" and kwargs["fraction"] == 0.02 and kwargs["min_cities"] == 3
    dec = report["decision"]
    assert dec["rule"] == "v4" and dec["label"] == "headline decision" and dec["row_source"] == "reconstructed_frames"
    assert core.EXPLORATORY_STATEMENT in dec["statements"]
    assert "working_choice" not in dec and "action" not in dec                  # no v3 field survives
    assert set(report["truth_stats"]) == {"AUSTIN", "EL_PASO"}
    for city in ("AUSTIN", "EL_PASO"):
        stats_c = report["truth_stats"][city]
        assert stats_c["n_truth_rows"] == 40 and report["per_city"][city]["truth_stats"] == stats_c
        assert dec["bars"]["per_city"][city] == pytest.approx(0.02 * stats_c["mean_truth_amps"], abs=1e-12, rel=0)


def test_truth_stats_are_the_unrounded_mean_of_the_independent_truth_ampacity(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND"])
    vt = pd.date_range("2026-09-30", "2026-10-24 18:00", freq="6h", tz="UTC")
    for city in ("AUSTIN", "MIDLAND"):
        w = archive_weather(city, "2026-09-28", "2026-10-24 23:00").set_index("datetime_utc").loc[vt]
        truth = independent_amps({c: w[c] for c in ("air_temp", "wind_speed", "wind_direction", "solar_radiation")}, city)
        stats_c = report["truth_stats"][city]
        assert stats_c["n_truth_rows"] == len(vt) == 100
        assert stats_c["mean_truth_amps"] == pytest.approx(float(truth.mean()), abs=1e-9, rel=0)
        assert isinstance(stats_c["mean_truth_amps"], float) and isinstance(stats_c["n_truth_rows"], int)
        assert report["decision"]["bars"]["per_city"][city] == pytest.approx(0.02 * float(truth.mean()), abs=1e-9, rel=0)


def test_a_fresh_run_decides_and_a_vetoed_candidate_is_never_picked(tmp_path, stub_models):
    free = injected_run(str(tmp_path / "ev_free"), stub_models, protocol_status="signed")
    dec = free["decision"]
    assert dec["rule"] == "v4" and dec["label"] == "headline decision" and dec["round"] == "v4-read1"
    assert free["basis"] == "FRESH" and dec["pick"] is not None and dec["pick"] in dec["qualifying"], dec["reasons"]
    winner = dec["pick"]
    assert not any(dec["vetoes"][c]["vetoed"] for c in core.REAL_CANDIDATES)

    for basis_name, vetoed_section in (("ablation", "ablation_vetoed"), ("test", "test_vetoed")):
        (tmp_path / basis_name).mkdir()
        path = write_veto_files(tmp_path / basis_name, **{vetoed_section: (winner,)})[0]
        vetoed_run = injected_run(str(tmp_path / f"ev_{basis_name}"), stub_models, protocol_status="signed",
                                  vetoes=conf.load_vetoes(path))
        vdec = vetoed_run["decision"]
        assert vdec["vetoes"][winner]["vetoed"] is True and vdec["vetoes"][winner][basis_name] is True
        assert winner not in vdec["qualifying"] and vdec["pick"] != winner
        assert any(f"{winner} does not qualify" in r and "vetoed" in r for r in vdec["reasons"])
        # the family statistics do not depend on the veto record
        assert vetoed_run["family"] == free["family"]


def test_vetoing_every_candidate_gives_no_pick_and_the_signed_read_2_text(tmp_path, stub_models):
    path = write_veto_files(tmp_path, test_vetoed=core.REAL_CANDIDATES)[0]
    report = injected_run(str(tmp_path / "ev"), stub_models, protocol_status="signed", vetoes=conf.load_vetoes(path))
    dec = report["decision"]
    assert dec["pick"] is None and dec["qualifying"] == []
    assert "No candidate qualifies under signed protocol v4" in dec["statement"]
    assert "v4-read2" in dec["statement"]
    md = open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()
    assert "No candidate qualifies under signed protocol v4" in md and "\nPick:" not in md


def test_read_2_is_scored_with_the_read_2_round_window_and_decision_text(tmp_path, stub_models):
    path = write_veto_files(tmp_path, test_vetoed=core.REAL_CANDIDATES)[0]

    def provider(city, *, evidence_dir):
        # the frame `anchored_pair_frame(city, 2026-09-28, 2026-10-31)` would build for read 2
        frame = make_frame(city, "2026-09-28", "2026-10-31 23:00")
        frame = frame[frame["anchor_datetime_utc"] >= pd.Timestamp("2026-09-28", tz="UTC")].reset_index(drop=True)
        return frame, archive_weather(city, "2026-09-28", "2026-10-31 23:00"), {"city": city}

    report = run(str(tmp_path / "ev"), now="2026-11-08T00:00:00Z", guard_cfg=core.guard_for_round("v4-read2"),
                 frame_provider=provider, model_loader=loader_for(stub_models), vetoes=conf.load_vetoes(path),
                 protocol_status="signed")
    assert report["round"] == "v4-read2" and report["decision"]["round"] == "v4-read2"
    assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 128 == core.V4_READ2.slots_per_city
    assert report["config"]["fetch_window"] == ["2026-09-28", "2026-10-31"]
    assert report["scored_window"] == ["2026-09-30T00:00:00+00:00", "2026-11-01T00:00:00+00:00"]
    assert report["decision"]["pick"] is None and "Read 2 (v4-read2) also names no winner" in report["decision"]["statement"]


def test_the_descriptive_round_never_picks_and_needs_no_veto_record(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND", "EL_PASO", "CORPUS_CHRISTI"],
                          guard_cfg=core.guard_for_round("v4-late-descriptive"), vetoes=None, protocol_status="signed")
    dec = report["decision"]
    assert dec["label"] == "descriptive re-score (D-03), cannot overturn" and dec["pick"] is None
    assert dec["round"] == "v4-late-descriptive" and report["round"] == "v4-late-descriptive"
    assert "Round: v4-late-descriptive (descriptive only)" in open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()


def test_a_city_whose_fetch_fails_has_no_truth_stats_and_the_decision_uses_the_other_three(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, frame_provider=injected_provider(fail=("MIDLAND",)))
    assert list(report["failed_cities"]) == ["MIDLAND"]
    assert report["failed_cities"]["MIDLAND"]["stage"] == "frame_fetch_failed"
    assert "injected fetch failure" in report["failed_cities"]["MIDLAND"]["error"]
    assert "MIDLAND" not in report["truth_stats"] and "truth_stats" not in report["per_city"]["MIDLAND"]
    assert set(report["truth_stats"]) == {"AUSTIN", "CORPUS_CHRISTI", "EL_PASO"}
    dec = report["decision"]
    assert "MIDLAND" not in dec["bars"]["per_city"]
    for cand in core.REAL_CANDIDATES:
        assert dec["consistency"][cand]["cities_with_data"] == 3
    assert dec["pick"] is not None                                            # three cities can still decide


def test_two_failed_cities_leave_fewer_than_three_and_no_pick_is_made(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, frame_provider=injected_provider(fail=("MIDLAND", "EL_PASO")))
    assert sorted(report["failed_cities"]) == ["EL_PASO", "MIDLAND"]
    dec = report["decision"]
    assert dec["pick"] is None and dec["qualifying"] == []
    assert all(dec["consistency"][c]["cities_with_data"] == 2 and not dec["consistency"][c]["possible"] for c in core.REAL_CANDIDATES)
    assert any("only 2 cities" in r for r in dec["reasons"])


def test_a_failed_city_is_never_retried_in_a_decision_run(monkeypatch, evidence_root, stub_models):
    attempts = []
    base = injected_provider(fail=("MIDLAND",))

    def counting(city, *, evidence_dir):
        attempts.append(city)
        return base(city, evidence_dir=evidence_dir)

    injected_run(evidence_root, stub_models, frame_provider=counting)
    assert attempts.count("MIDLAND") == 1 and sorted(attempts) == sorted(CITIES)


def test_candidates_are_matched_as_exact_strings(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"])
    dec = report["decision"]
    assert tuple(dec["levels"]) == core.REAL_CANDIDATES == ("ml_wind_corrected", "ml_cooling_corrected", "reference_ml_refit_24h")
    assert set(dec["vetoes"]) == set(core.REAL_CANDIDATES) and set(dec["consistency"]) == set(core.REAL_CANDIDATES)
    assert dec["pick"] is None or dec["pick"] in core.REAL_CANDIDATES


@pytest.mark.parametrize("instant_text, refused", [
    ("2026-11-01T02:00:00+02:00", False),     # the same moment as 2026-11-01T00:00:00Z, written with an offset
    ("2026-11-01T01:59:59+02:00", True),      # one second before it
    ("2026-10-31T19:00:00-05:00", False),     # also the same moment (UTC-5)
    ("2026-10-31T18:59:59-05:00", True),
])
def test_instants_are_compared_as_utc_moments_never_as_text(evidence_root, stub_models, instant_text, refused):
    # text order would put "2026-10-31..." before "2026-11-01..." and "2026-11-01T01:59:59+02:00" after "2026-11-01T00:00:00Z"
    if refused:
        with pytest.raises(core.EvaluationGuardError, match="evaluation instant"):
            injected_run(evidence_root, stub_models, cities=["AUSTIN"], now=instant_text)
        assert not os.path.exists(evidence_root)
    else:
        report = injected_run(evidence_root, stub_models, cities=["AUSTIN"], now=instant_text)
        assert report["guard"]["now_evaluated"] == "2026-11-01T00:00:00+00:00" and report["guard"]["defaults_used"]


def test_a_naive_or_offset_guard_instant_equal_to_the_round_is_still_the_default(evidence_root, stub_models):
    for i, instant in enumerate((pd.Timestamp("2026-11-01T00:00:00"), pd.Timestamp("2026-11-01T02:00:00+02:00"))):
        guard = core.GuardConfig(evaluation_instant=instant, valid_time_cutoff=pd.Timestamp("2026-10-25T02:00:00+02:00"))
        report = injected_run(f"{evidence_root}_{i}", stub_models, cities=["AUSTIN"], guard_cfg=guard)
        assert report["guard"]["defaults_used"] and report["guard"]["valid_time_cutoff"] == "2026-10-25T00:00:00+00:00"
        assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 100


def test_the_report_renders_the_v4_decision_in_plain_form(evidence_root, stub_models, tmp_path):
    path = write_veto_files(tmp_path, ablation_vetoed=("reference_ml_refit_24h",))[0]
    report = injected_run(evidence_root, stub_models, protocol_status="signed", vetoes=conf.load_vetoes(path))
    md = open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()
    section = md.split("## Decision (headline decision)")[1].split("\n## ")[0]
    for city in CITIES:
        assert any(line.startswith(f"- Bar {city}:") and line.endswith(" A") for line in section.splitlines()), city
    dec = report["decision"]
    for cand in core.REAL_CANDIDATES:
        line = next(l for l in section.splitlines() if l.startswith(f"- {cand} vs raw_forecast:"))
        assert dec["levels"][cand]["level"] in line and "pooled bar" in line and "favoured in" in line and "of 4 cities" in line
    ref_line = next(l for l in section.splitlines() if l.startswith("- reference_ml_refit_24h vs raw_forecast:"))
    assert "vetoed by ABLATION" in ref_line
    wind_line = next(l for l in section.splitlines() if l.startswith("- ml_wind_corrected vs raw_forecast:"))
    assert "not vetoed" in wind_line
    assert dec["pick"] is not None and f"\nPick: {dec['pick']}\n" in section
    assert "Label: headline decision" in section and "Round: v4-read1" in section
    assert core.NOT_MEASURED_STATEMENT in section and "working choice" not in section.lower()


def test_the_v4_decision_block_of_a_development_run_leaves_family_and_metrics_alone(evidence_root, stub_models):
    # same fixture, once without and once with a veto record: only the decision block (and its inputs) may differ
    a = run(evidence_root + "_a", now="2026-10-13T08:00:00Z", cities=["AUSTIN", "EL_PASO"], frame_provider=dev_provider,
            model_loader=loader_for(stub_models), window=DEV_WINDOW, params=SMALL, vetoes=None)
    b = run(evidence_root + "_b", now="2026-10-13T08:00:00Z", cities=["AUSTIN", "EL_PASO"], frame_provider=dev_provider,
            model_loader=loader_for(stub_models), window=DEV_WINDOW, params=SMALL)
    assert a["family"] == b["family"]
    assert {c: a["per_city"][c]["metrics"] for c in a["per_city"]} == {c: b["per_city"][c]["metrics"] for c in b["per_city"]}


# --------------------------------------------------------------------------
# 07-09 Task 1: the opt-in production-conductor seam, the frozen-Drake secondary, scored-artifact provenance
# (D-01, D-09, SEL-02, COND-02). Synthetic frames, stub models, a tmp refit root; nothing real is scored.
# --------------------------------------------------------------------------

import forecast_conductor_refit as refit  # noqa: E402  (grouped with the plan's tests)

SECONDARY_TEXT = "secondary: frozen Drake artifacts, never decides"
DEV_NOW = "2026-10-13T08:00:00Z"


@pytest.fixture
def austin_100c(monkeypatch):
    """The signed O4 table: AUSTIN at Drake 100 C, every other city untouched (patched, never edited in config.py)."""
    table = {c: dict(v) for c, v in config.PRODUCTION_CONDUCTORS.items()}
    table["AUSTIN"]["max_temp_c"] = 100.0
    monkeypatch.setattr(config, "PRODUCTION_CONDUCTORS", table)
    return table


def dev_run(evidence_root, stub_models, *, cities=None, loader=None, **kwargs):
    kwargs.setdefault("frame_provider", dev_provider)
    kwargs.setdefault("window", DEV_WINDOW)
    kwargs.setdefault("params", SMALL)
    kwargs.setdefault("vetoes", None)
    return run(evidence_root, now=DEV_NOW, cities=cities,
               model_loader=loader or loader_for(stub_models), **kwargs)


def _secondary_spec(stub_models, **over):
    spec = {"label": "secondary", "point_resolver": None, "model_loader": loader_for(stub_models)}
    spec.update(over)
    return spec


def _no_arm5_spies(monkeypatch):
    calls = {"city_point": [], "production": [], "weather_to_arm5": 0, "arm5_for_point": 0}
    real_cp, real_prod = city_point.city_point, city_point.production_city_point
    real_w, real_a = fit_models.weather_to_arm5_frame, refit.arm5_frame_for_point
    monkeypatch.setattr(city_point, "city_point", lambda c: calls["city_point"].append(c) or real_cp(c))
    monkeypatch.setattr(city_point, "production_city_point", lambda c: calls["production"].append(c) or real_prod(c))

    def w(*a, **k):
        calls["weather_to_arm5"] += 1
        return real_w(*a, **k)

    def a(*args, **k):
        calls["arm5_for_point"] += 1
        return real_a(*args, **k)

    monkeypatch.setattr(fit_models, "weather_to_arm5_frame", w)
    monkeypatch.setattr(refit, "arm5_frame_for_point", a)
    return calls


def test_the_geometry_functions_take_an_optional_keyword_only_point():
    import inspect
    for fn in (conf.prepare_city_frame, conf._arm5_from_weather, conf.candidate_predictions, conf.leakage_probe):
        p = inspect.signature(fn).parameters["point"]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY and p.default is None, fn.__name__


def test_without_a_point_the_default_path_uses_city_point_and_weather_to_arm5_frame(monkeypatch, austin_inputs, stub_models):
    frame, weather = austin_inputs
    calls = _no_arm5_spies(monkeypatch)
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN")
    preds, _ = conf.candidate_predictions(prepared, weather, "AUSTIN", stub_models["AUSTIN"])
    conf.leakage_probe(prepared, "AUSTIN", stub_models["AUSTIN"])
    assert "AUSTIN" in calls["city_point"] and calls["production"] == []
    assert calls["weather_to_arm5"] >= 2 and calls["arm5_for_point"] == 0
    assert len(preds) == 100


def test_with_a_point_the_geometry_comes_from_the_point_and_city_point_is_not_asked(monkeypatch, austin_inputs, stub_models):
    frame, weather = austin_inputs
    point = city_point.city_point("AUSTIN")
    calls = _no_arm5_spies(monkeypatch)
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN", point=point)
    preds, _ = conf.candidate_predictions(prepared, weather, "AUSTIN", stub_models["AUSTIN"], point=point)
    conf.leakage_probe(prepared, "AUSTIN", stub_models["AUSTIN"], point=point)
    assert calls["city_point"] == [] and calls["production"] == []
    assert calls["weather_to_arm5"] == 0 and calls["arm5_for_point"] >= 2
    assert len(preds) == 100


def test_an_explicit_drake_point_gives_exactly_the_default_numbers(austin_inputs, stub_models):
    frame, weather = austin_inputs
    base_prepared, base = predictions("AUSTIN", frame, weather, stub_models["AUSTIN"])[:2]
    point = city_point.city_point("AUSTIN")
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN", point=point)
    other, _ = conf.candidate_predictions(prepared, weather, "AUSTIN", stub_models["AUSTIN"], point=point)
    cols = ["truth_amps", *core.CANDIDATES]
    assert np.array_equal(base[cols].to_numpy(), other[cols].to_numpy(), equal_nan=True)


def test_a_production_point_raises_austin_truth_and_raw_and_persistence(austin_inputs, stub_models, austin_100c):
    frame, weather = austin_inputs
    _, base = predictions("AUSTIN", frame, weather, stub_models["AUSTIN"])[:2]
    point = city_point.production_city_point("AUSTIN")
    assert point.conductor.T_max == 100.0
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN", point=point)
    hot, _ = conf.candidate_predictions(prepared, weather, "AUSTIN", stub_models["AUSTIN"], point=point)
    for col in ("truth_amps", "raw_forecast", "persistence_24h"):
        assert (hot[col].to_numpy() > base[col].to_numpy()).all(), col
    w = weather.set_index("datetime_utc").loc[hot.index]
    expected = thermal_model.ieee738_ampacity(
        w["air_temp"].to_numpy(float),
        thermal_model.perpendicular_wind(w["wind_speed"].to_numpy(float), w["wind_direction"].to_numpy(float), point.bearing_deg),
        w["solar_radiation"].to_numpy(float), point.conductor)
    assert np.allclose(hot["truth_amps"], expected, atol=1e-9, rtol=0)


def test_the_leakage_probe_passes_under_a_production_point_and_still_catches_a_leaky_arm(austin_inputs, stub_models, austin_100c):
    frame, _ = austin_inputs
    point = city_point.production_city_point("AUSTIN")
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN", point=point)
    result = conf.leakage_probe(prepared, "AUSTIN", stub_models["AUSTIN"], point=point)
    assert result["passed"] and result["oracle_changed"]
    leaky = {"leaky_arm": lambda f: f["truth_wind_speed"].to_numpy(dtype=float)}
    with pytest.raises(core.LeakageProbeError, match="leaky_arm"):
        conf.leakage_probe(prepared, "AUSTIN", stub_models["AUSTIN"], extra_arms=leaky, point=point)


def test_a_run_without_a_resolver_never_asks_for_the_production_point_and_matches_an_explicit_drake_resolver(
        monkeypatch, evidence_root, stub_models):
    calls = _no_arm5_spies(monkeypatch)
    default = dev_run(evidence_root + "_default", stub_models, cities=CITIES)
    assert calls["production"] == [] and calls["city_point"] and calls["arm5_for_point"] == 0
    assert default["secondary"] is None and default["config"]["point_resolver"] == "city_point (frozen Drake)"
    drake = dev_run(evidence_root + "_drake", stub_models, cities=CITIES, point_resolver=city_point.city_point)
    assert core.dumps(default["family"]) == core.dumps(drake["family"])
    assert default["truth_stats"] == drake["truth_stats"]


def test_a_production_resolver_changes_only_the_differing_citys_truth(evidence_root, stub_models, austin_100c):
    base = dev_run(evidence_root + "_base", stub_models, cities=CITIES)
    prod = dev_run(evidence_root + "_prod", stub_models, cities=CITIES, point_resolver=city_point.production_city_point)
    assert prod["truth_stats"]["AUSTIN"]["mean_truth_amps"] > base["truth_stats"]["AUSTIN"]["mean_truth_amps"]
    for city in ("CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        assert prod["truth_stats"][city] == base["truth_stats"][city], city
    assert prod["config"]["point_resolver"] == "production_city_point"
    assert prod["failed_cities"] == {}


def test_the_secondary_equals_a_drake_only_run_on_the_same_inputs_and_never_decides(evidence_root, stub_models, austin_100c):
    drake_only = dev_run(evidence_root + "_drake", stub_models, cities=CITIES)
    both = dev_run(evidence_root + "_both", stub_models, cities=CITIES, point_resolver=city_point.production_city_point,
                   secondary=_secondary_spec(stub_models))
    sec = both["secondary"]
    assert sec["label"] == SECONDARY_TEXT and sec["row_source"] == "reconstructed_frames"
    assert core.dumps(sec["family"]) == core.dumps(drake_only["family"])
    assert sec["truth_stats"] == drake_only["truth_stats"]
    assert {c: sec["per_city"][c]["metrics"] for c in CITIES} == {c: drake_only["per_city"][c]["metrics"] for c in CITIES}
    assert sec["decision"]["pick"] is None and sec["decision"]["label"] == SECONDARY_TEXT
    assert sec["decision"]["rule_outcome"] == drake_only["decision"]["rule_outcome"]
    assert sec["failed_cities"] == {}
    # the headline is under the production conductor, so it is not the Drake result for AUSTIN
    assert both["truth_stats"]["AUSTIN"] != drake_only["truth_stats"]["AUSTIN"]
    assert both["decision"]["label"] == "headline decision"
    # the two are separate reports: nothing pooled, nothing shared
    assert sec["family"] is not both["family"] and sec["decision"] is not both["decision"]
    assert both["config"]["secondary"]["label"] == SECONDARY_TEXT


def test_the_secondary_report_is_accepted_by_the_combined_summary_with_its_own_label(evidence_root, stub_models, austin_100c):
    import forecast_shadow_decision_v4 as v4
    both = dev_run(evidence_root + "_both", stub_models, cities=CITIES, point_resolver=city_point.production_city_point,
                   secondary=_secondary_spec(stub_models))
    live = {"row_source": "shadow_logs", "decision": {**both["secondary"]["decision"], "row_source": "shadow_logs",
                                                        "label": v4.LABELS["live"]}, "sample_size": {}}
    text = v4.combined_summary_v4(both, live, both["secondary"])
    assert "Secondary result (frozen Drake artifacts)" in text
    with pytest.raises(ValueError):
        v4.combined_summary_v4(both, live, both)             # a duplicated source is still refused


def test_a_bad_secondary_spec_is_refused_before_the_guard_and_leaves_the_root_empty(evidence_root, stub_models):
    for spec in ({"label": "headline", "point_resolver": None, "model_loader": loader_for(stub_models)},
                 {"label": "secondary", "point_resolver": None},
                 "secondary"):
        with pytest.raises(ValueError, match="secondary"):
            dev_run(evidence_root, stub_models, cities=["AUSTIN"], secondary=spec)
    assert not os.path.exists(evidence_root)


def test_a_secondary_failure_in_one_city_is_recorded_and_the_headline_keeps_that_city(evidence_root, stub_models):
    def sec_loader(city, method):
        if city == "MIDLAND":
            raise ValueError("injected secondary load failure")
        return stub_models[city][method]

    report = dev_run(evidence_root, stub_models, cities=CITIES, secondary=_secondary_spec(stub_models, model_loader=sec_loader))
    assert report["failed_cities"] == {} and "MIDLAND" in report["truth_stats"]
    sec = report["secondary"]
    assert list(sec["failed_cities"]) == ["MIDLAND"]
    assert sec["failed_cities"]["MIDLAND"]["stage"] == "models"
    assert "MIDLAND" not in sec["truth_stats"] and set(sec["truth_stats"]) == set(CITIES) - {"MIDLAND"}
    assert sec["per_city"]["MIDLAND"]["failed"]["stage"] == "models"


def test_a_frame_fetch_failure_fails_both_the_headline_and_the_secondary_city_without_a_retry(evidence_root, stub_models):
    seen = []

    def provider(city, *, evidence_dir):
        seen.append(city)
        if city == "EL_PASO":
            raise conf.FrameFetchError("EL_PASO: injected")
        return dev_provider(city, evidence_dir=evidence_dir)

    report = dev_run(evidence_root, stub_models, cities=CITIES, frame_provider=provider, secondary=_secondary_spec(stub_models))
    assert seen.count("EL_PASO") == 1 and set(report["failed_cities"]) == {"EL_PASO"}
    assert list(report["secondary"]["failed_cities"]) == ["EL_PASO"]


def test_a_leaky_arm_in_the_secondary_probe_still_aborts_the_run(evidence_root, stub_models):
    leaky = {"leaky_arm": lambda f: f["truth_wind_speed"].to_numpy(dtype=float)}
    with pytest.raises(core.LeakageProbeError, match="leaky_arm"):
        dev_run(evidence_root, stub_models, cities=["AUSTIN"], secondary=_secondary_spec(stub_models), extra_probe_arms=leaky)


def _frozen_world(tmp_path, monkeypatch, stub_models):
    """12 stub 'frozen' artifacts in a tmp SHADOW_MODEL_DIR plus a matching tmp manifest; returns the manifest path."""
    monkeypatch.setattr(pipeline, "SHADOW_MODEL_DIR", str(tmp_path / "frozen"))
    lines = []
    for city, models in stub_models.items():
        for method, model in models.items():
            pipeline.save_correction_model(model, city, method)
            path = pipeline._model_path_for(city, method)
            lines.append(f"{core.sha256_file(path)}  {refit._manifest_key(path)}")
    manifest = tmp_path / "frozen_manifest.sha256"
    manifest.write_text("# stub\n" + "\n".join(lines) + "\n", encoding="utf-8")
    return str(manifest)


def test_scored_artifacts_lists_every_headline_and_secondary_artifact_with_hash_and_source(
        tmp_path, monkeypatch, evidence_root, stub_models, austin_100c):
    manifest = _frozen_world(tmp_path, monkeypatch, stub_models)
    root = tmp_path / "refit"
    refit.write_refit("AUSTIN", {conf.COOLING: stub_models["AUSTIN"][conf.COOLING],
                                 conf.REFERENCE: stub_models["AUSTIN"][conf.REFERENCE]}, "v-test", root=str(root))
    head = refit.make_headline_loader("v-test", {"AUSTIN"}, root=str(root), frozen_manifest=manifest)
    sec = refit.make_headline_loader("v-test", set(), root=str(root), frozen_manifest=manifest)
    report = dev_run(evidence_root, stub_models, cities=CITIES, loader=head, point_resolver=city_point.production_city_point,
                     secondary=_secondary_spec(stub_models, model_loader=sec))
    arts = report["scored_artifacts"]
    assert len(arts) == 24
    for entry in arts:
        assert set(entry) >= {"city", "method", "path", "sha256", "source", "role"}
        assert len(entry["sha256"]) == 64 and entry["sha256"] == core.sha256_file(entry["path"])
    by = {(a["role"], a["city"], a["method"]): a for a in arts}
    assert len(by) == 24
    for method in (conf.COOLING, conf.REFERENCE):
        a = by[("headline", "AUSTIN", method)]
        assert a["source"] == "refit" and a["path"].startswith(str(root))
    assert by[("headline", "AUSTIN", conf.WIND)]["source"] == "frozen"
    assert by[("headline", "MIDLAND", conf.COOLING)]["source"] == "frozen"
    assert {a["source"] for a in arts if a["role"] == "secondary"} == {"frozen"}
    assert by[("secondary", "AUSTIN", conf.COOLING)]["path"] != by[("headline", "AUSTIN", conf.COOLING)]["path"]
    # the headline's served list is what the loader itself recorded
    assert {(s["city"], s["method"], s["sha256"]) for s in head.served} == {
        (a["city"], a["method"], a["sha256"]) for a in arts if a["role"] == "headline"}


def test_scored_artifacts_for_an_injected_loader_say_injected_and_hash_nothing_that_does_not_exist(evidence_root, stub_models):
    report = dev_run(evidence_root, stub_models, cities=["AUSTIN"])
    arts = report["scored_artifacts"]
    assert {(a["role"], a["city"], a["method"]) for a in arts} == {("headline", "AUSTIN", m) for m in conf.MODEL_METHODS}
    assert all(a["source"] == "injected" for a in arts)


def test_the_recording_loader_returns_the_model_and_records_each_served_artifact_once(tmp_path, monkeypatch, stub_models):
    _frozen_world(tmp_path, monkeypatch, stub_models)
    wrapped = conf._recording_loader(pipeline.load_correction_model, "frozen")
    first = wrapped("AUSTIN", conf.WIND)
    wrapped("AUSTIN", conf.WIND)
    assert type(first) is type(stub_models["AUSTIN"][conf.WIND])
    (entry,) = wrapped.records
    assert entry["source"] == "frozen" and entry["sha256"] == core.sha256_file(entry["path"])
    with pytest.raises(FileNotFoundError):
        wrapped("AUSTIN", "no_such_method")


# --------------------------------------------------------------------------
# 07-09 Task 2: CLI conductor-basis selection, the refit pre-check, the D-03 descriptive gate, dry-run reporting
# --------------------------------------------------------------------------

import joblib  # noqa: E402

PARITY_SECONDARY = "identical to the headline by construction; not computed separately"
NOTHING_TO_RESCORE = "nothing to re-score descriptively (D-03)"
SIGNED_ARGS = ["--round", "v4-read1", "--protocol-status", "signed"]


def write_read1_report(evidence_root, version, *, stamp="20261101T000500Z"):
    """A synthetic read-1 headline report on disk (only its rating_config_version matters to the D-03 gate)."""
    directory = os.path.join(evidence_root, "v4-read1", f"reconstructed_frames_{stamp}")
    os.makedirs(directory, exist_ok=True)
    body = {"round": "v4-read1", "synthetic": True}
    if version is not None:
        body["rating_config_version"] = version
    with open(os.path.join(directory, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(body, fh)
    return directory


@pytest.fixture
def refit_world(tmp_path, monkeypatch, stub_models, austin_100c):
    """AUSTIN differs from Drake (100 C); its refit cooling and reference for the CURRENT RATING_CONFIG_VERSION sit in a
    tmp root with a manifest; the frozen stubs sit in a tmp SHADOW_MODEL_DIR with their own manifest."""
    manifest = _frozen_world(tmp_path, monkeypatch, stub_models)
    root = tmp_path / "refit"
    refit.write_refit("AUSTIN", {conf.COOLING: stub_models["AUSTIN"][conf.COOLING],
                                 conf.REFERENCE: stub_models["AUSTIN"][conf.REFERENCE]},
                      config.RATING_CONFIG_VERSION, root=str(root))
    monkeypatch.setattr(refit, "REFIT_ROOT", str(root))
    monkeypatch.setattr(refit, "FROZEN_MANIFEST", manifest)

    def no_load(*a, **k):
        raise AssertionError("joblib.load must not be called by a pre-check")
    return {"root": root, "manifest": manifest, "dir": root / config.RATING_CONFIG_VERSION, "no_load": no_load}


def _vetoes_path(tmp_path):
    return write_veto_files(tmp_path)[0]


# --- conductor_basis ---

def test_conductor_basis_at_parity_says_production_equals_drake_and_the_secondary_is_not_computed_twice():
    basis = conf.conductor_basis(CITIES)
    assert basis["differing"] == [] and basis["config_version"] == config.RATING_CONFIG_VERSION
    assert "Drake" in basis["headline"] and "production" in basis["headline"]
    assert basis["secondary"] == PARITY_SECONDARY
    assert basis["refit_artifacts"] == [] and basis["problems"] == []


def test_conductor_basis_with_a_differing_city_lists_its_verified_refit_artifacts_without_loading_them(refit_world, monkeypatch):
    monkeypatch.setattr(joblib, "load", refit_world["no_load"])
    basis = conf.conductor_basis(CITIES)
    assert basis["differing"] == ["AUSTIN"] and basis["problems"] == []
    arts = {(a["city"], a["method"]): a for a in basis["refit_artifacts"]}
    assert set(arts) == {("AUSTIN", conf.COOLING), ("AUSTIN", conf.REFERENCE)}
    for a in arts.values():
        assert a["status"] == "verified" and a["verified"] is True and a["expected_sha256"] == a["actual_sha256"]
        assert a["path"].startswith(str(refit_world["root"]).replace(os.sep, "/"))
    assert "AUSTIN" in basis["headline"] and "refit" in basis["headline"]
    assert PARITY_SECONDARY not in basis["secondary"] and "frozen Drake" in basis["secondary"]


def test_conductor_basis_flags_a_missing_and_a_tampered_refit_artifact(refit_world):
    (refit_world["dir"] / f"{conf.COOLING}_AUSTIN.joblib").unlink()
    ref = refit_world["dir"] / f"{conf.REFERENCE}_AUSTIN.joblib"
    ref.write_bytes(ref.read_bytes() + b"x")
    basis = conf.conductor_basis(CITIES)
    status = {a["method"]: a["status"] for a in basis["refit_artifacts"]}
    assert status == {conf.COOLING: "missing_file", conf.REFERENCE: "hash_mismatch"}
    assert len(basis["problems"]) == 2 and basis["refit_verified"] is False


def test_conductor_basis_flags_a_missing_manifest_and_an_unlisted_artifact(refit_world):
    manifest = refit_world["dir"] / refit.MANIFEST_NAME
    manifest.write_text("# no entries\n", encoding="utf-8")
    assert {a["status"] for a in conf.conductor_basis(CITIES)["refit_artifacts"]} == {"not_in_manifest"}
    manifest.unlink()
    basis = conf.conductor_basis(CITIES)
    assert {a["status"] for a in basis["refit_artifacts"]} == {"manifest_unreadable"} and basis["problems"]


def test_conductor_basis_flags_a_tampered_frozen_artifact_but_not_an_absent_one(refit_world):
    frozen = pipeline._model_path_for("MIDLAND", conf.WIND)
    with open(frozen, "ab") as fh:
        fh.write(b"x")
    problems = conf.conductor_basis(CITIES)["problems"]
    assert len(problems) == 1 and "hash_mismatch" in problems[0] and "MIDLAND" in problems[0]
    with open(frozen, "wb"):
        pass
    os.remove(frozen)
    assert conf.conductor_basis(CITIES)["problems"] == []          # a missing frozen file stays candidate_unavailable


def test_conductor_basis_considers_only_the_cities_asked_for(refit_world):
    assert conf.conductor_basis(["MIDLAND", "EL_PASO"])["differing"] == []
    assert conf.conductor_basis(["AUSTIN"])["differing"] == ["AUSTIN"]


# --- main: the basis picks the run ---

def test_main_with_a_differing_city_builds_the_production_resolver_the_headline_loader_and_a_secondary(
        monkeypatch, evidence_root, tmp_path, refit_world):
    code, seen = capture_main(monkeypatch, [*SIGNED_ARGS, "--vetoes", _vetoes_path(tmp_path), "--evidence-root", evidence_root])
    assert code == 0
    assert seen["point_resolver"] is city_point.production_city_point
    head = seen["model_loader"]
    assert head("AUSTIN", conf.COOLING) is not None and head("MIDLAND", conf.COOLING) is not None
    sources = {(s["city"], s["method"]): s["source"] for s in head.served}
    assert sources == {("AUSTIN", conf.COOLING): "refit", ("MIDLAND", conf.COOLING): "frozen"}
    sec = seen["secondary"]
    assert sec["label"] == "secondary" and sec["point_resolver"] is None
    sec["model_loader"]("AUSTIN", conf.COOLING)
    assert [(s["city"], s["source"]) for s in sec["model_loader"].served] == [("AUSTIN", "frozen")]
    assert seen["conductor_basis"]["differing"] == ["AUSTIN"]
    assert seen["conductor_basis"]["config_version"] == config.RATING_CONFIG_VERSION


@pytest.mark.parametrize("damage", ["missing", "tampered", "no_manifest", "frozen_tampered"])
def test_main_refuses_with_exit_2_before_any_request_when_the_refit_or_frozen_artifacts_are_not_sound(
        monkeypatch, evidence_root, tmp_path, capsys, refit_world, damage):
    vetoes = _vetoes_path(tmp_path)
    art = refit_world["dir"] / f"{conf.COOLING}_AUSTIN.joblib"
    if damage == "missing":
        art.unlink()
    elif damage == "tampered":
        art.write_bytes(art.read_bytes() + b"x")
    elif damage == "no_manifest":
        (refit_world["dir"] / refit.MANIFEST_NAME).unlink()
    else:
        with open(pipeline._model_path_for("EL_PASO", conf.REFERENCE), "ab") as fh:
            fh.write(b"x")
    code, seen = capture_main(monkeypatch, [*SIGNED_ARGS, "--vetoes", vetoes, "--evidence-root", evidence_root])
    assert code == 2 and seen == {}                       # run_confirmation never reached; requests.get is a bomb
    err = capsys.readouterr().err
    assert err.startswith("refused:") and "conductor" in err.lower()
    assert not os.path.exists(evidence_root)


def test_main_at_parity_runs_the_default_path_with_no_secondary_and_records_the_statement(
        monkeypatch, evidence_root, tmp_path):
    code, seen = capture_main(monkeypatch, [*SIGNED_ARGS, "--vetoes", _vetoes_path(tmp_path), "--evidence-root", evidence_root])
    assert code == 0
    assert seen.get("point_resolver") is None and seen.get("secondary") is None and seen.get("model_loader") is None
    assert seen["conductor_basis"]["differing"] == [] and seen["conductor_basis"]["secondary"] == PARITY_SECONDARY


def test_a_missing_production_entry_is_refused_not_a_traceback(monkeypatch, evidence_root, capsys):
    table = {c: dict(v) for c, v in config.PRODUCTION_CONDUCTORS.items()}
    del table["MIDLAND"]
    monkeypatch.setattr(config, "PRODUCTION_CONDUCTORS", table)
    code, seen = capture_main(monkeypatch, ["--dry-run", "--round", "v4-read1", "--evidence-root", evidence_root])
    assert code == 2 and seen == {} and capsys.readouterr().err.startswith("refused:")


# --- rating_config_version and the basis in every report ---

def test_every_report_and_its_run_started_marker_record_the_rating_config_version(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, protocol_status="signed")
    assert report["rating_config_version"] == config.RATING_CONFIG_VERSION
    assert report["config"]["rating_config_version"] == config.RATING_CONFIG_VERSION
    marker = json.load(open(os.path.join(report["evidence_dir"], "run_started.json"), encoding="utf-8"))
    assert marker["config"]["rating_config_version"] == config.RATING_CONFIG_VERSION
    assert report["conductor_basis"] is None and report["config"]["conductor_basis"] is None
    on_disk = json.load(open(os.path.join(report["evidence_dir"], "report.json"), encoding="utf-8"))
    assert on_disk["rating_config_version"] == config.RATING_CONFIG_VERSION


def test_a_given_conductor_basis_is_recorded_in_the_report_and_the_config(evidence_root, stub_models):
    basis = conf.conductor_basis(CITIES)
    report = injected_run(evidence_root, stub_models, conductor_basis=basis)
    assert report["conductor_basis"] == basis and report["config"]["conductor_basis"] == basis
    assert report["secondary"] is None


# --- D-03: the late descriptive round ---

def test_the_late_descriptive_round_is_refused_without_any_read_1_report(monkeypatch, evidence_root, capsys):
    code, seen = capture_main(monkeypatch, ["--round", "v4-late-descriptive", "--evidence-root", evidence_root])
    assert code == 2 and seen == {}
    err = capsys.readouterr().err
    assert err.startswith("refused:") and NOTHING_TO_RESCORE in err and "v4-read1" in err
    assert not os.path.exists(os.path.join(evidence_root, "v4-late-descriptive"))


def test_the_late_descriptive_round_is_refused_when_the_rating_config_version_is_unchanged(monkeypatch, evidence_root, capsys):
    write_read1_report(evidence_root, config.RATING_CONFIG_VERSION)
    code, seen = capture_main(monkeypatch, ["--round", "v4-late-descriptive", "--evidence-root", evidence_root])
    assert code == 2 and seen == {} and NOTHING_TO_RESCORE in capsys.readouterr().err


def test_the_late_descriptive_round_is_refused_when_the_read_1_report_records_no_version(monkeypatch, evidence_root, capsys):
    write_read1_report(evidence_root, None)
    code, seen = capture_main(monkeypatch, ["--round", "v4-late-descriptive", "--evidence-root", evidence_root])
    assert code == 2 and seen == {} and NOTHING_TO_RESCORE in capsys.readouterr().err


def test_the_late_descriptive_round_proceeds_when_the_version_differs_and_uses_the_newest_read_1_report(
        monkeypatch, evidence_root):
    write_read1_report(evidence_root, "v1-older", stamp="20261101T000100Z")
    write_read1_report(evidence_root, config.RATING_CONFIG_VERSION, stamp="20261101T000000Z")   # older directory
    code, seen = capture_main(monkeypatch, ["--round", "v4-late-descriptive", "--evidence-root", evidence_root])
    assert code == 0 and seen["round_name"] == "v4-late-descriptive"
    # newest directory name wins: flip the order and the same run is refused
    write_read1_report(evidence_root, config.RATING_CONFIG_VERSION, stamp="20261101T000900Z")
    code, seen = capture_main(monkeypatch, ["--round", "v4-late-descriptive", "--evidence-root", evidence_root])
    assert code == 2 and seen == {}


def test_the_late_gate_does_not_apply_to_the_deciding_rounds(monkeypatch, evidence_root, tmp_path):
    code, seen = capture_main(monkeypatch, [*SIGNED_ARGS, "--vetoes", _vetoes_path(tmp_path), "--evidence-root", evidence_root])
    assert code == 0 and seen["round_name"] == "v4-read1"


def test_after_the_gate_the_late_round_still_meets_the_instant_and_one_shot_guards(monkeypatch, evidence_root, capsys):
    write_read1_report(evidence_root, "v1-older")
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp(BEFORE_INSTANT))
    assert conf.main(["--round", "v4-late-descriptive", "--evidence-root", evidence_root]) == 2
    assert "evaluation instant" in capsys.readouterr().err
    late_root = os.path.join(evidence_root, "v4-late-descriptive", "reconstructed_frames_20261101T000000Z")
    os.makedirs(late_root)
    with open(os.path.join(late_root, "run_started.json"), "w", encoding="utf-8") as fh:
        json.dump({"basis": "FRESH", "row_source": "reconstructed_frames"}, fh)
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp(AT_INSTANT))
    assert conf.main(["--round", "v4-late-descriptive", "--evidence-root", evidence_root]) == 2
    assert "second FRESH run" in capsys.readouterr().err


# --- dry run ---

def test_dry_run_reports_the_conductor_basis_and_the_rating_config_version_at_parity(tmp_path, evidence_root):
    out = str(tmp_path / "dry.json")
    assert conf.main(["--dry-run", "--round", "v4-read1", "--out", out, "--evidence-root", evidence_root]) == 0
    result = json.load(open(out, encoding="utf-8"))
    assert result["conductor_basis"]["differing"] == [] and result["conductor_basis"]["secondary"] == PARITY_SECONDARY
    assert result["rating_config_version"] == config.RATING_CONFIG_VERSION and result["rating_config_version"][:3] == "v2-"
    assert not os.path.exists(evidence_root)


def test_dry_run_with_a_differing_city_lists_the_refit_artifacts_and_their_hash_status_without_network_or_load(
        monkeypatch, tmp_path, evidence_root, refit_world):
    monkeypatch.setattr(joblib, "load", refit_world["no_load"])
    (refit_world["dir"] / f"{conf.REFERENCE}_AUSTIN.joblib").write_bytes(b"tampered")
    out = str(tmp_path / "dry.json")
    assert conf.main(["--dry-run", "--round", "v4-read1", "--out", out, "--evidence-root", evidence_root]) == 0
    basis = json.load(open(out, encoding="utf-8"))["conductor_basis"]
    assert basis["differing"] == ["AUSTIN"]
    assert {a["method"]: a["status"] for a in basis["refit_artifacts"]} == {conf.COOLING: "verified", conf.REFERENCE: "hash_mismatch"}
    assert basis["problems"] and not os.path.exists(evidence_root)


def test_dry_run_for_the_late_round_reports_the_gate_and_does_not_refuse(tmp_path, evidence_root):
    out = str(tmp_path / "dry.json")
    assert conf.main(["--dry-run", "--round", "v4-late-descriptive", "--out", out, "--evidence-root", evidence_root]) == 0
    gate = json.load(open(out, encoding="utf-8"))["late_descriptive_gate"]
    assert gate["allowed"] is False and NOTHING_TO_RESCORE in gate["reason"]
    write_read1_report(evidence_root, "v1-older")
    assert conf.main(["--dry-run", "--round", "v4-late-descriptive", "--out", out, "--evidence-root", evidence_root]) == 0
    gate = json.load(open(out, encoding="utf-8"))["late_descriptive_gate"]
    assert gate["allowed"] is True and gate["read1_rating_config_version"] == "v1-older"
    assert not os.path.exists(os.path.join(evidence_root, "v4-late-descriptive"))
