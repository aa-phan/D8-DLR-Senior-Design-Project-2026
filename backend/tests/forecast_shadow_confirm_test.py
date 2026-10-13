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
BEFORE_INSTANT = "2026-11-23T23:59:59Z"
AT_INSTANT = "2026-11-24T00:00:00Z"
FETCH_START, FETCH_END = core.RECON_FETCH_START, core.RECON_FETCH_END
SMALL = {"n_resamples": 200}  # non-default: only used with an override or on a development basis
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
    """The frame `anchored_pair_frame(city, 2026-09-28, 2026-11-16)` would build."""
    frame = make_frame(city, "2026-09-28", "2026-11-16 23:00")
    return frame[frame["anchor_datetime_utc"] >= pd.Timestamp("2026-09-28", tz="UTC")].reset_index(drop=True)


def injected_provider(*, weather_edit=None, frame_edit=None, fail=()):
    """A frame provider (city, *, evidence_dir) over the synthetic world; optional edits per city."""
    def provider(city, *, evidence_dir):
        if city in fail:
            raise conf.FrameFetchError(f"{city}: injected fetch failure")
        frame = recon_frame(city)
        weather = archive_weather(city, "2026-09-28", "2026-11-16 23:00")
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


def run(evidence_root, *, now=AT_INSTANT, cities=None, **kwargs):
    kwargs.setdefault("guard_cfg", core.GuardConfig())
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

def test_default_window_is_the_192_slot_fresh_window():
    win = conf.default_window()
    slots = win.slots()
    assert win.start == pd.Timestamp("2026-09-30T00:00:00Z") and win.end == core.VALID_TIME_CUTOFF_DEFAULT
    assert len(slots) == 192
    assert slots[0] == pd.Timestamp("2026-09-30T00:00:00Z") and slots[-1] == pd.Timestamp("2026-11-16T18:00:00Z")
    assert all(t.hour % 6 == 0 for t in slots)


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


def test_cli_refuses_before_the_instant_with_exit_2(monkeypatch, evidence_root, capsys):
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp("2026-10-13T08:00:00Z"))
    code = conf.main(["--evidence-root", evidence_root])
    assert code == 2
    assert "refused" in capsys.readouterr().err
    assert not os.path.exists(evidence_root)


def test_override_passes_and_is_recorded(monkeypatch, evidence_root, model_dir):
    server = FakeServer(monkeypatch)
    report = run(evidence_root, now=BEFORE_INSTANT, cities=["AUSTIN"], params=SMALL,
                 guard_cfg=core.GuardConfig(override_reason="rehearsal of the evaluation day"))
    assert report["guard"]["override_reason"] == "rehearsal of the evaluation day"
    saved = json.load(open(os.path.join(report["evidence_dir"], "report.json"), encoding="utf-8"))
    assert saved["guard"]["override_reason"] == "rehearsal of the evaluation day"
    md = open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()
    assert "Override: rehearsal of the evaluation day" in md
    assert len(server.calls) == 2


def test_nondefault_parameter_in_a_fresh_run_needs_an_override(evidence_root, stub_models):
    with pytest.raises(ValueError, match="PD-15"):
        injected_run(evidence_root, stub_models, params=SMALL)
    assert not os.path.exists(evidence_root)


def test_second_fresh_run_is_refused_without_override(evidence_root, stub_models):
    first = injected_run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND"])
    assert first["basis"] == "FRESH"
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        injected_run(evidence_root, stub_models, cities=["AUSTIN", "MIDLAND"], now="2026-11-24T00:00:05Z")
    assert len(os.listdir(evidence_root)) == 1
    again = injected_run(evidence_root, stub_models, cities=["AUSTIN"], now="2026-11-24T00:00:09Z",
                         guard_cfg=core.GuardConfig(override_reason="owner-approved rerun"))
    assert again["guard"]["prior_fresh_runs"] and again["guard"]["override_reason"] == "owner-approved rerun"


def test_a_run_that_crashed_after_its_guard_still_blocks_the_next_one(evidence_root, stub_models):
    leaky = {"leaky": lambda f: f["truth_wind_speed"].to_numpy(dtype=float)}
    with pytest.raises(core.LeakageProbeError):
        injected_run(evidence_root, stub_models, cities=["AUSTIN"], extra_probe_arms=leaky)
    (run_dir,) = os.listdir(evidence_root)
    assert os.path.isfile(os.path.join(evidence_root, run_dir, "run_started.json"))
    assert not os.path.exists(os.path.join(evidence_root, run_dir, "report.json"))
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        injected_run(evidence_root, stub_models, cities=["AUSTIN"], now="2026-11-24T00:01:00Z")


def test_a_prior_shadow_logs_marker_does_not_block_the_port(evidence_root, stub_models):
    prior = os.path.join(evidence_root, "shadow_logs_20261124T000000Z")
    os.makedirs(prior)
    with open(os.path.join(prior, "run_started.json"), "w", encoding="utf-8") as fh:
        json.dump({"row_source": "shadow_logs", "basis": "FRESH"}, fh)
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"], now="2026-11-24T00:02:00Z")
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
    assert weather["datetime_utc"].max() == pd.Timestamp("2026-11-16T23:00:00Z")
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
        assert report["per_city"][city]["n_scored"] == {name: 192 for name in core.CANDIDATES}
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
        assert report["per_city"][city]["n_scored"]["raw_forecast"] == 192
    assert len(report["family"]["comparisons"]) == 9
    assert "MIDLAND" in open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8").read()


# --------------------------------------------------------------------------
# Scored rows
# --------------------------------------------------------------------------

def test_scored_rows_are_exact_lead_fresh_and_at_most_192():
    prepared, diag = conf.prepare_city_frame(recon_frame("AUSTIN"), "AUSTIN")
    assert len(prepared) == 192 == diag["n_expected_slots"] == diag["n_scored_slots"]
    forecast_experiment.assert_exact_lead(prepared, lead_hours=24)
    vt = prepared["datetime_utc"]
    assert (vt.dt.hour % 6 == 0).all()
    assert vt.min() == pd.Timestamp("2026-09-30T00:00:00Z") and vt.max() == pd.Timestamp("2026-11-16T18:00:00Z")
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
    assert len(prepared) == 190 and diag["n_missing_from_reconstruction"] == 2
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
    weather = archive_weather("AUSTIN", "2026-09-28", "2026-11-16 23:00")
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
    for i in (0, 1, 37, 95, 191):
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
    weather = archive_weather("AUSTIN", "2026-09-28", "2026-11-16 23:00")
    models = stub_models["AUSTIN"]
    _, base, _ = predictions("AUSTIN", frame, weather, models)
    cut = pd.Timestamp("2026-11-01T00:00:00Z")  # perturb truth strictly after this hour, in both sources
    f2, w2 = frame.copy(), weather.copy()
    for col, delta in (("air_temp", 3.0), ("wind_speed", 1.0), ("solar_radiation", 50.0)):
        w2.loc[w2["datetime_utc"] > cut, col] = w2.loc[w2["datetime_utc"] > cut, col] + delta
        f2.loc[f2["datetime_utc"] > cut, f"truth_{col}"] = f2.loc[f2["datetime_utc"] > cut, f"truth_{col}"] + delta
    _, shifted, _ = predictions("AUSTIN", f2, w2, models)
    unaffected = base["anchor_time"] <= cut
    assert unaffected.sum() > 100
    assert np.array_equal(base.loc[unaffected, conf.REFERENCE].to_numpy(), shifted.loc[unaffected, conf.REFERENCE].to_numpy())
    assert not np.allclose(base.loc[~unaffected, conf.REFERENCE], shifted.loc[~unaffected, conf.REFERENCE])


def test_a_missing_hour_makes_exactly_the_dependent_rows_reference_features_missing(austin_inputs, stub_models):
    frame, weather = austin_inputs
    removed = [pd.Timestamp("2026-10-10T03:00:00Z"), pd.Timestamp("2026-10-21T15:00:00Z")]
    nulled = pd.Timestamp("2026-11-02T09:00:00Z")
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
    assert block["n_scored"][conf.COOLING] == 0 and block["n_scored"][conf.WIND] == 192
    assert block["candidate_exclusions"][conf.COOLING] == {"candidate_unavailable": 192}
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
    assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 191
    assert report["per_city"]["MIDLAND"]["n_scored"]["raw_forecast"] == 192


def test_rows_at_or_after_the_cutoff_are_never_scored(evidence_root, stub_models):
    extra = lambda c, f: pd.concat([f, make_frame(c, "2026-11-17 00:00", "2026-11-20 00:00")], ignore_index=True)
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"], frame_provider=injected_provider(frame_edit=extra))
    assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 192


def test_a_structural_failure_in_one_city_is_named_and_the_others_are_scored(evidence_root, stub_models):
    def broken(city, frame):
        return frame.drop(columns=["fcst_wind_speed"]) if city == "EL_PASO" else frame
    report = injected_run(evidence_root, stub_models, frame_provider=injected_provider(frame_edit=broken))
    assert list(report["failed_cities"]) == ["EL_PASO"]
    assert "fcst_wind_speed" in report["failed_cities"]["EL_PASO"]["error"]
    assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 192


def test_unsigned_status_is_labelled_exploratory(evidence_root, stub_models):
    report = injected_run(evidence_root, stub_models, cities=["AUSTIN"])
    assert any(core.EXPLORATORY_STATEMENT in s for s in report["decision"]["statements"])
    signed = injected_run(evidence_root, stub_models, cities=["AUSTIN"], protocol_status="signed",
                          now="2026-11-24T00:05:00Z", guard_cfg=core.GuardConfig(override_reason="x"))
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
    assert result["expected_slots_per_city"] == 192


def test_dry_run_reports_a_prior_fresh_run(evidence_root, model_dir):
    prior = os.path.join(evidence_root, "reconstructed_frames_20261124T000000Z")
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


def test_cli_nondefault_parameter_in_a_fresh_run_is_refused(monkeypatch, evidence_root, capsys):
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp("2026-11-24T00:00:00Z"))
    assert conf.main(["--evidence-root", evidence_root, "--block-lengths", "1", "2"]) == 2
    assert "override" in capsys.readouterr().err
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
