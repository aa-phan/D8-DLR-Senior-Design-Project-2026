"""
Validation of the two per-city confirmation evaluators on FROZEN DEVELOPMENT
DATA (quick task 261013-285, Task 4).

What this module is. A hermetic reproduction and fault-injection suite for
`forecast_shadow_score.py` (the shadow-log scorer, the live-system check) and
`forecast_shadow_confirm.py` (the reconstructed-frame port, the headline). It
needs only the committed fixture plus synthetic inputs and mocked HTTP. It reads
nothing under `data/experiment`, `data/shadow/predictions` or
`data/shadow/models`; every file it writes lives under a pytest tmp directory.

This validation produces NO performance claim. Every prediction below is a
synthetic transformation of the fixture's weather (for example
`ml_wind_corrected = raw_forecast - 30 A`) or a stub model fitted in-test on a
few weeks of the fixture. The 12 real per-city artifacts are never loaded or
scored on a frozen period (runbook, "Fit-window decision"); the FRESH-calendar
tests load only stub artifacts saved into a tmp `SHADOW_MODEL_DIR`.

The fixture (`fixtures/shadow_eval_frozen_dev_frames.csv.gz`). Hourly rows
2026-03-30T00Z .. 2026-05-31T23Z for the four cities (1,512 rows each, 6,048
rows), every column of the frozen anchored-pair frame plus a `city` column. All
of it lies inside the frozen test split (2026-03-17 onward) that the frozen
experiment already inspected, and none of it is FRESH-dated. Reproduction
recipe (reads ONLY the four frozen-window caches, never any other file under
data/experiment, in particular never the FRESH-dated 2026-09-30_2026-10-04
files), run from the repository root with the project .venv:

    import pandas as pd
    parts = []
    for c in ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]:
        p = f"data/experiment/anchored_pair_frame_{c}_2024-01-20_2026-09-29_lead24_previous_runs.csv"
        f = pd.read_csv(p)
        f["datetime_utc"] = pd.to_datetime(f["datetime_utc"], utc=True)
        f = f[(f["datetime_utc"] >= "2026-03-30T00:00:00Z") & (f["datetime_utc"] < "2026-06-01T00:00:00Z")].copy()
        f.insert(0, "city", c)
        parts.append(f)
    pd.concat(parts, ignore_index=True).to_csv(
        "backend/tests/fixtures/shadow_eval_frozen_dev_frames.csv.gz", index=False)

sha256 of the four source caches (hashed 2026-10-13, and the recipe above was
re-run and shown to reproduce the committed fixture value for value):

    AUSTIN          dbe2ad2207b933730e45bc960922b8fef4199d73af923e8ed9a2623be0c228c5
    CORPUS_CHRISTI  585bf24623747bf9c21051b4b2e9674c2e5888707f23b267efa6caaddbb78043
    MIDLAND         a29edcf31480749b72c1a873157f0c349b34ea10bdf0071610e8fbca7c9b0cef
    EL_PASO         32ea0bab4dee2d462926b40b831c42d7f44e13adb3e3c8b990fae8f838dc82e4

Layout of the tests (one section each): fixture bounds; shadow-log scorer
reproduction against numpy oracles; port reproduction; fault-injection matrix;
guard end to end for both tools; FRESH-cache read prohibition; never pooled;
precision targets judged on effective n (end to end, both evaluators).
"""

from __future__ import annotations

import builtins
import copy
import functools
import hashlib
import json
import os
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import requests
from sklearn.linear_model import LinearRegression

import city_point
import config
import forecast_correction_models as fcm
import forecast_experiment
import forecast_shadow_confirm as conf
import forecast_shadow_decision as decision
import forecast_shadow_eval_core as core
import forecast_shadow_fit_models as fit_models
import forecast_shadow_pipeline as pipeline
import forecast_shadow_score as score_mod
import forecast_shadow_score_stats as stats
import forecast_training
import open_meteo_forecast_provider
import open_meteo_provider
import thermal_model

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "shadow_eval_frozen_dev_frames.csv.gz")
FIXTURE_SHA256 = "a397c82d5d541ee0941204a6c64c53782529b4a6593ed9bf83a9d22cdae26250"
CITIES = list(config.LOCATIONS)
WIND, COOL, RAW, PERSIST, REF = (
    "ml_wind_corrected", "ml_cooling_corrected", "raw_forecast", "persistence_24h", "reference_ml_refit_24h")
CANDS = (WIND, COOL, RAW, PERSIST, REF)
SENTINEL = 4321.987
SMALL = {"n_resamples": 300}     # development basis only; a FRESH run with this needs an override
DEV_NOW = "2026-10-13T08:00:00Z"
INSTANT = "2026-11-24T00:00:00Z"
BEFORE_INSTANT = "2026-11-23T23:59:59Z"
CUTOFF = core.VALID_TIME_CUTOFF_DEFAULT
DEV_WINDOW = ("2026-04-01T00:00:00Z", "2026-06-01T00:00:00Z")
SLOTS = pd.date_range("2026-04-01T00:00:00Z", "2026-05-31T18:00:00Z", freq="6h")   # 244 slots per city
PROD_SHIFT_DAYS = 182          # production-window dates 2026-09-28.. map onto fixture 2026-03-30..
FRESH_LOG_SHIFT_DAYS = 200     # FRESH-calendar logs: 2026-04-01 -> 2026-10-18
PROD_SLOTS = SLOTS[:192]       # fixture-time slots behind the 192 production-window slots
HALF = pd.Timedelta(hours=12)
DAY = pd.Timedelta(hours=24)
TOL = 1e-9


# --------------------------------------------------------------------------
# Fixture access and independent physics
# --------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _fx_all() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE)
    for col in ("datetime_utc", "anchor_datetime_utc", "fcst_anchor_datetime_utc"):
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


@functools.lru_cache(maxsize=None)
def city_fx(city: str) -> pd.DataFrame:
    """The fixture rows of one city, sorted. Treat as read-only (cached); copy before mutating."""
    return _fx_all()[_fx_all()["city"] == city].sort_values("datetime_utc").reset_index(drop=True)


def independent_amps(air, wind, direction, solar, city: str) -> np.ndarray:
    """IEEE 738 ampacity straight from thermal_model with city_point geometry (never the evaluators' helpers)."""
    point = city_point.city_point(city)
    perp = thermal_model.perpendicular_wind(np.asarray(wind, dtype=float), np.asarray(direction, dtype=float), point.bearing_deg)
    return np.asarray(thermal_model.ieee738_ampacity(
        np.asarray(air, dtype=float), perp, np.asarray(solar, dtype=float), point.conductor), dtype=float)


@functools.lru_cache(maxsize=None)
def world(city: str) -> SimpleNamespace:
    fx = city_fx(city)
    idx = pd.DatetimeIndex(fx["datetime_utc"])

    def amps(prefix: str) -> pd.Series:
        return pd.Series(independent_amps(fx[f"{prefix}_air_temp"], fx[f"{prefix}_wind_speed"],
                                          fx[f"{prefix}_wind_direction"], fx[f"{prefix}_solar_radiation"], city), index=idx)
    return SimpleNamespace(index=idx, truth=amps("truth"), fcst=amps("fcst"), anchor=amps("anchor"))


def np_metrics(err) -> dict:
    """The per-candidate descriptive metrics straight from numpy (error = prediction - truth)."""
    err = np.asarray(err, dtype=float)
    err = err[np.isfinite(err)]
    if err.size == 0:
        return {"n": 0}
    over = err[err > 0]
    return {"n": int(err.size), "bias": float(err.mean()), "mae": float(np.abs(err).mean()),
            "rmse": float(np.sqrt((err ** 2).mean())), "median_abs_error": float(np.median(np.abs(err))),
            "overprediction_rate": float((err > 0).mean()),
            "overshoot_mean": float(over.mean()) if over.size else None,
            "overshoot_p95": float(np.percentile(over, 95)) if over.size else None,
            "overshoot_max": float(over.max()) if over.size else None}


def assert_metrics_equal(got: dict, err, *, tol: float = TOL) -> None:
    want = np_metrics(err)
    assert got["n"] == want["n"]
    if want["n"] == 0:
        assert got["mae"] is None
        return
    for key, value in want.items():
        if key == "n":
            continue
        if value is None:
            assert got[key] is None, key
        else:
            assert got[key] == pytest.approx(value, abs=tol, rel=0), key


def oracle_family(errs_by_city: dict) -> dict:
    """{(a, b): {n, margin, per_city, rel}} on complete-case rows, margin = mean|e_B| - mean|e_A| (pooled, row-weighted)."""
    out = {}
    for a, b in core.HEADLINE_FAMILY:
        diffs, per_city, sa, sb = [], {}, 0.0, 0.0
        for city, frame in errs_by_city.items():
            both = frame[[a, b]].dropna()
            d = np.abs(both[b].to_numpy(dtype=float)) - np.abs(both[a].to_numpy(dtype=float))
            diffs.append(d)
            per_city[city] = float(d.mean()) if d.size else None
            sa += float(np.abs(both[a]).sum())
            sb += float(np.abs(both[b]).sum())
        alld = np.concatenate(diffs) if diffs else np.array([])
        n = int(alld.size)
        out[(a, b)] = {"n": n, "margin": float(alld.mean()) if n else None, "per_city": per_city,
                       "rel": (1.0 - (sa / n) / (sb / n)) if n and sb else None}
    return out


def assert_family_equals_oracle(family: dict, errs_by_city: dict) -> None:
    want = oracle_family(errs_by_city)
    assert len(family["comparisons"]) == 9
    for c in family["comparisons"]:
        w = want[(c["a"], c["b"])]
        assert c["n_paired"] == w["n"], (c["a"], c["b"])
        if w["n"] == 0:
            assert c["point_margin"] is None
            continue
        assert c["point_margin"] == pytest.approx(w["margin"], abs=TOL, rel=0), (c["a"], c["b"])
        assert c["relative_mae_reduction"] == pytest.approx(w["rel"], abs=TOL, rel=0)
        for city, m in w["per_city"].items():
            if m is None:
                assert c["per_city_margins"][city] is None
            else:
                assert c["per_city_margins"][city] == pytest.approx(m, abs=TOL, rel=0)


# --------------------------------------------------------------------------
# Synthetic v3 logs built from the fixture
# --------------------------------------------------------------------------

def _cand(amps, *, status="ok", fallback=False, anchor=None, window_end=None, reason=None):
    cand = {"status": status, "ampacity_amps": amps, "fallback_used": fallback, "fallback_reason": None,
            "model_version": "stub@0", "input_provenance": None, "reason": reason,
            "bundle": {"status": "ok", "bundle_ampacity_amps": SENTINEL}}
    if anchor is not None:
        cand["input_provenance"] = {"anchor_provenance": anchor}
    if window_end is not None:
        cand["input_provenance"] = {"truth_proxy_window_start": (window_end - pd.Timedelta(hours=6)).isoformat(),
                                    "truth_proxy_window_end": window_end.isoformat()}
    return cand


def anchor_age_h(i: int) -> float:
    return 1.0 + (i % 7) * 0.25


def anchor_source(i: int) -> str:
    return "tceq" if i % 2 == 0 else "synoptic"


def log_record(city: str, i: int, v: pd.Timestamp, shift: pd.Timedelta, *, model="gfs_seamless") -> dict:
    """
    One v3 record for fixture slot `v` (the row's index in SLOTS is `i`), re-dated by `shift`.
    valid = v + shift; init = valid - 24 h; availability = init + 6 h; decision = valid - 12 h + 7 min; horizon 1440.
    raw = IEEE 738 of the fixture forecast; wind = raw - 30; cooling = 0.5 raw + 0.5 truth;
    persistence = fixture truth 24 h earlier (unavailable on every 10th row); reference = truth at its own
    target hour (valid + 12 h) + 40 (-1)^i.
    """
    w = world(city)
    valid = v + shift
    decision = valid - HALF + pd.Timedelta(minutes=7)
    raw, truth = float(w.fcst[v]), float(w.truth[v])
    tgt = v + HALF
    ref_truth = float(w.truth[tgt]) if tgt in w.truth.index else truth
    anchor = {"anchor_source": anchor_source(i), "anchor_station": "KAUS" if i % 2 == 0 else "SYN1",
              "anchor_observation_time": (decision - pd.Timedelta(hours=anchor_age_h(i))).isoformat()}
    persistence = (_cand(float(w.truth[v - DAY])) if i % 10 != 0
                   else _cand(None, status="unavailable", reason="no prior same-model cycle"))
    row = {
        "schema_version": 3, "city": city,
        "initialization_time": (valid - DAY).isoformat(), "availability_time": (valid - DAY + pd.Timedelta(hours=6)).isoformat(),
        "decision_time": decision.isoformat(), "valid_time": valid.isoformat(), "horizon_minutes": 1440,
        "logged_at": (decision + pd.Timedelta(minutes=1)).isoformat(), "basis_caveat": "synthetic validation row",
        "candidates": {
            WIND: _cand(raw - 30.0, anchor=anchor), COOL: _cand(0.5 * raw + 0.5 * truth, anchor=anchor),
            RAW: _cand(raw), PERSIST: persistence,
            REF: _cand(ref_truth + 40.0 * (-1) ** i, window_end=decision),
        },
    }
    if model is not None:
        row["forecast_model"] = model
    return row


def build_log_rows(city: str, shift_days: int = 0, indices=None) -> list[dict]:
    shift = pd.Timedelta(days=shift_days)
    return [log_record(city, i, SLOTS[i], shift) for i in (range(len(SLOTS)) if indices is None else indices)]


def sentinel_row(city: str, valid, *, model, logged_at=None) -> dict:
    """A well-formed v3 row whose every ampacity is the sentinel (it must never reach any metric)."""
    valid = pd.Timestamp(valid)
    decision = valid - HALF + pd.Timedelta(minutes=7)
    cands = {n: _cand(SENTINEL, anchor={"anchor_source": "tceq", "anchor_station": "KAUS",
                                        "anchor_observation_time": (decision - pd.Timedelta(hours=1)).isoformat()})
             for n in CANDS}
    row = {"schema_version": 3, "city": city, "initialization_time": (valid - DAY).isoformat(),
           "availability_time": (valid - DAY + pd.Timedelta(hours=6)).isoformat(), "decision_time": decision.isoformat(),
           "valid_time": valid.isoformat(), "horizon_minutes": 1440,
           "logged_at": (logged_at or decision + pd.Timedelta(minutes=1)).isoformat(), "basis_caveat": "x", "candidates": cands}
    if model is not None:
        row["forecast_model"] = model
    return row


def write_logs(directory, cities, shift_days: int = 0, *, edit=None, indices=None) -> None:
    """One JSONL per city. `edit(city, rows) -> rows | (rows, extra_lines)` changes a copy of the realistic log."""
    os.makedirs(directory, exist_ok=True)
    for city in cities:
        rows = build_log_rows(city, shift_days, indices)
        extra = []
        if edit is not None:
            out = edit(city, copy.deepcopy(rows))
            rows, extra = out if isinstance(out, tuple) else (out, [])
        with open(os.path.join(directory, f"{city}.jsonl"), "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
            for line in extra:
                fh.write(line + "\n")


# --------------------------------------------------------------------------
# Fake Open-Meteo servers (archive for the logs, archive + previous-runs for the port)
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


_UNITS = {"temperature_2m": "°C", "wind_speed_10m": "m/s", "wind_direction_10m": "°",
          "shortwave_radiation": "W/m²", "relative_humidity_2m": "%"}
_KEYS = {"temperature_2m": "air_temp", "wind_speed_10m": "wind_speed", "wind_direction_10m": "wind_direction",
         "shortwave_radiation": "solar_radiation", "relative_humidity_2m": "relative_humidity"}


def fixture_payload(city: str, start: str, end: str, *, source: str, shift_days: int, suffix: str = "",
                    null_hours=(), strict: bool = False) -> dict:
    """
    Hourly payload for the requested dates built from the fixture (`source` is "truth" or "fcst"). The request's
    dates are `shift_days` after the fixture's; an hour the fixture lacks is null (archive only; `strict` makes
    that an error, for the previous-runs endpoint, which rejects nulls).
    """
    fx = city_fx(city).set_index("datetime_utc")
    shift = pd.Timedelta(days=shift_days)
    times = pd.date_range(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC") + pd.Timedelta(hours=23), freq="h")
    nulls = {pd.Timestamp(t) for t in null_hours}
    hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}
    for key, col in _KEYS.items():
        values = []
        for t in times:
            src = t - shift
            if t in nulls or src not in fx.index:
                assert not strict or src in fx.index, f"fixture has no hour {src} for {city}"
                values.append(None)
            else:
                values.append(float(fx.at[src, f"{source}_{col}"]))
        hourly[key + suffix] = values
    return {"hourly": hourly, "hourly_units": {k + suffix: v for k, v in _UNITS.items()}}


class FakeServer:
    """requests.get replacement. `shift_days` re-dates the fixture; failures are per city; every call is recorded."""

    def __init__(self, mp, *, shift_days=0, fail_archive=(), fail_previous=(), null_hours=()):
        self.calls = []
        self.shift_days = shift_days
        self.fail_archive, self.fail_previous = set(fail_archive), set(fail_previous)
        self.null_hours = {pd.Timestamp(t) for t in null_hours}
        mp.setattr(requests, "get", self.get)

    def get(self, url, params=None, **kwargs):
        self.calls.append((url, dict(params), kwargs))
        city = next(c for c, (lat, _) in config.CITY_COORDINATES.items() if lat == params["latitude"])
        if url == open_meteo_provider.OPEN_METEO_ARCHIVE_BASE:
            if city in self.fail_archive:
                return FakeResponse(raw=b"service unavailable", status=503)
            return FakeResponse(fixture_payload(city, params["start_date"], params["end_date"], source="truth",
                                                shift_days=self.shift_days, null_hours=self.null_hours))
        assert url == open_meteo_forecast_provider.OPEN_METEO_PREVIOUS_RUNS_BASE, url
        if city in self.fail_previous:
            return FakeResponse(raw=b"service unavailable", status=503)
        return FakeResponse(fixture_payload(city, params["start_date"], params["end_date"], source="fcst",
                                            shift_days=self.shift_days, suffix="_previous_day1", strict=True))

    def calls_for(self, city):
        lat = config.CITY_COORDINATES[city][0]
        return [c for c in self.calls if c[1]["latitude"] == lat]


# --------------------------------------------------------------------------
# Stub models fitted on the fixture (the real artifacts are never loaded here)
# --------------------------------------------------------------------------

def fit_stub_models(city: str) -> dict:
    frame = city_fx(city)
    frame = frame[frame["datetime_utc"] < pd.Timestamp("2026-04-21", tz="UTC")].copy()
    point = city_point.city_point(city)
    frame["truth_dlr_amps"] = fit_models.weather_to_arm5_frame(frame, city, prefix="truth_")["dlr_amps"].to_numpy()
    exact = forecast_experiment._add_correction_columns(forecast_experiment.filter_to_exact_lead(frame, lead_hours=24), point)
    wind = fcm.fit_wind_correction(exact, fcm.WIND_CORRECTION_ESTIMATORS["LinearRegression"], pooling="per_city")
    cooling = fcm.fit_cooling_correction(exact, fcm.COOLING_CORRECTION_ESTIMATORS["LinearRegression"],
                                         target="log_ratio", conductor=point.conductor)
    X, y = forecast_training.build_training_matrix(fit_models.weather_to_arm5_frame(frame, city, prefix="truth_"),
                                                   horizon_minutes=1440)
    reference = LinearRegression().fit(X.to_numpy(dtype=float), y.to_numpy(dtype=float))
    return {conf.WIND: wind, conf.COOLING: cooling, conf.REFERENCE: reference}


@pytest.fixture(scope="module")
def stub_models():
    return {city: fit_stub_models(city) for city in CITIES}


def loader_for(models):
    return lambda city, method: models[city][method]


@pytest.fixture
def model_dir(tmp_path, monkeypatch, stub_models):
    """SHADOW_MODEL_DIR redirected to tmp and filled with the 12 STUB artifacts."""
    path = tmp_path / "models"
    monkeypatch.setattr(pipeline, "SHADOW_MODEL_DIR", str(path))
    for city, methods in stub_models.items():
        for method, model in methods.items():
            pipeline.save_correction_model(model, city, method)
    return str(path)


def dev_provider(city, *, evidence_dir):
    """Injected development provider: the fixture frame plus its hourly truth weather (with the 03-30/31 lead-in)."""
    frame = city_fx(city).copy()
    weather = frame[["datetime_utc"] + [f"truth_{c}" for c in ("air_temp", "wind_speed", "wind_direction",
                                                                  "solar_radiation", "relative_humidity")]].copy()
    weather.columns = ["datetime_utc", "air_temp", "wind_speed", "wind_direction", "solar_radiation", "relative_humidity"]
    return frame, weather, {"city": city, "provider": "fixture"}


# --------------------------------------------------------------------------
# Oracles for the two evaluators
# --------------------------------------------------------------------------

def oracle_log_errors(city: str, *, shift_days: int = 0, cutoff=None, only=None, drop_rows=(), cand_nan=None,
                      null_hours=()) -> pd.DataFrame:
    """
    Signed errors (prediction - truth) per candidate, indexed by fixture-time valid slot, computed independently from
    the fixture. The reference is scored at its own target hour (valid + 12 h); `ref_logged` is its logged-hour reading.
    Faults: `only` limits which row indices exist in the log, `drop_rows` removes whole rows, `cand_nan` blanks a
    candidate on given rows, `null_hours` (fixture time) are null in the archive, rows at/after `cutoff` (logged time)
    are excluded and a reference target at/after the cutoff blanks the reference.
    """
    w = world(city)
    shift = pd.Timedelta(days=shift_days)
    nulls = {pd.Timestamp(t) for t in null_hours}
    rows = []
    for i, v in enumerate(SLOTS):
        rec = {c: np.nan for c in CANDS}
        rec["ref_logged"] = np.nan
        exists = (only is None or i in only) and i not in drop_rows
        keep = exists and v not in nulls and (cutoff is None or v + shift < cutoff)
        if keep:
            t, raw = float(w.truth[v]), float(w.fcst[v])
            rec[RAW] = raw - t
            rec[WIND] = (raw - 30.0) - t
            rec[COOL] = (0.5 * raw + 0.5 * t) - t
            if i % 10 != 0:
                rec[PERSIST] = float(w.truth[v - DAY]) - t
            tgt = v + HALF
            if tgt in w.truth.index and tgt not in nulls and (cutoff is None or tgt + shift < cutoff):
                tt = float(w.truth[tgt])
                pred = tt + 40.0 * (-1) ** i
                rec[REF] = pred - tt
                rec["ref_logged"] = pred - t
            for cand, idxs in (cand_nan or {}).items():
                if i in idxs:
                    rec[cand] = np.nan
                    if cand == REF:
                        rec["ref_logged"] = np.nan
        rec["_exists"] = exists
        rows.append(rec)
    frame = pd.DataFrame(rows, index=SLOTS)
    return frame[frame["_exists"]].drop(columns="_exists")


def port_oracle(city: str, models: dict, slots) -> pd.DataFrame:
    """Truth and the five candidates for the port on fixture-time `slots`, from thermal_model and the vectorized frozen helpers."""
    fx = city_fx(city).set_index("datetime_utc")
    rows = fx.loc[slots]
    rows.index.name = "datetime_utc"
    point = city_point.city_point(city)
    amps = lambda p: independent_amps(rows[f"{p}_air_temp"], rows[f"{p}_wind_speed"], rows[f"{p}_wind_direction"],
                                      rows[f"{p}_solar_radiation"], city)
    out = pd.DataFrame({"truth_amps": amps("truth"), RAW: amps("fcst"), PERSIST: amps("anchor")}, index=slots)
    prep = rows.reset_index()
    prep["truth_dlr_amps"] = out["truth_amps"].to_numpy()
    prep["city"] = city
    prep = forecast_experiment._add_correction_columns(prep, point)
    out[WIND] = forecast_experiment._wind_corrected_ampacity(models[WIND], prep, point)
    out[COOL] = forecast_experiment._cooling_corrected_ampacity(models[COOL], prep, point)
    w = world(city)
    arm5 = pd.DataFrame({"datetime_utc": w.index, "dlr_amps": w.truth.to_numpy(),
                         "air_temp": fx["truth_air_temp"].to_numpy(), "wind_speed": fx["truth_wind_speed"].to_numpy(),
                         "solar_radiation": fx["truth_solar_radiation"].to_numpy()})
    X, _ = forecast_training.build_training_matrix(arm5, horizon_minutes=1440)
    out[REF] = models[REF].predict(X.loc[pd.DatetimeIndex(slots) - DAY].to_numpy(dtype=float))
    return out


def port_errors(oracle: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({c: oracle[c] - oracle["truth_amps"] for c in CANDS}, index=oracle.index)


# --------------------------------------------------------------------------
# Autouse isolation + the FRESH-cache spy
# --------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("requests.get must not be called outside a fake server")
    monkeypatch.setattr(requests, "get", boom)


@pytest.fixture(autouse=True)
def _isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "SHADOW_PREDICTIONS_DIR", str(tmp_path / "stand_in_predictions"))
    monkeypatch.setattr(pipeline, "SHADOW_MODEL_DIR", str(tmp_path / "stand_in_models"))
    monkeypatch.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(tmp_path / "stand_in_experiment_cache"))


@pytest.fixture(autouse=True)
def _fresh_cache_spy(monkeypatch, tmp_path):
    """Fail any test that opens or reads a FRESH-window anchored_pair_frame cache outside the run's evidence root."""
    allowed = str(tmp_path / "evidence")
    real_open, real_read_csv = builtins.open, pd.read_csv

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


@pytest.fixture
def evidence_root(tmp_path):
    return str(tmp_path / "evidence")


def score_logs(pred_dir, evidence_root, *, cities=("AUSTIN",), now=DEV_NOW, params=SMALL, guard_cfg=None, **kw):
    return score_mod.score(str(pred_dir), cities=list(cities), guard_cfg=guard_cfg or core.GuardConfig(),
                           evidence_root=str(evidence_root), now=now, params=params, **kw)


def run_port(evidence_root, models, *, cities=("AUSTIN",), now=DEV_NOW, params=SMALL, window=DEV_WINDOW,
             frame_provider=dev_provider, guard_cfg=None, **kw):
    return conf.run_confirmation(cities=list(cities), guard_cfg=guard_cfg or core.GuardConfig(),
                                 evidence_root=str(evidence_root), now=now, params=params, window=window,
                                 frame_provider=frame_provider, model_loader=loader_for(models), **kw)


def read_md(report) -> str:
    with open(os.path.join(report["evidence_dir"], "report.md"), encoding="utf-8") as fh:
        return fh.read()


def read_json(report) -> dict:
    with open(os.path.join(report["evidence_dir"], "report.json"), encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Module-scoped baselines (built outside the function-scoped autouse fixtures, with their own patches)
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def logs_base(tmp_path_factory):
    base = tmp_path_factory.mktemp("logs_base")
    pred = base / "predictions"
    write_logs(pred, CITIES, 0)
    with pytest.MonkeyPatch.context() as mp:
        server = FakeServer(mp)
        report = score_logs(pred, base / "evidence", cities=CITIES)
    return SimpleNamespace(report=report, pred_dir=pred, server=server)


@pytest.fixture(scope="module")
def port_base(tmp_path_factory, stub_models):
    base = tmp_path_factory.mktemp("port_base")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no network")))
        mp.setattr(config, "FORECAST_EXPERIMENT_CACHE_DIR", str(base / "cache_stand_in"))
        report = run_port(base / "evidence", stub_models, cities=CITIES)
    return SimpleNamespace(report=report)


# ==========================================================================
# 1. Fixture bounds
# ==========================================================================

def test_fixture_is_the_committed_frozen_window_slice_and_nothing_fresh():
    import forecast_experiment_audit as audit   # test-only import: the frozen window constants
    assert hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest() == FIXTURE_SHA256
    fx = _fx_all()
    assert set(fx["city"]) == set(CITIES) and len(fx) == 4 * 1512
    assert fx["datetime_utc"].min() == pd.Timestamp("2026-03-30T00:00:00Z")
    assert fx["datetime_utc"].max() == pd.Timestamp("2026-05-31T23:00:00Z")
    split_start = pd.Timestamp(audit.FROZEN_TEST_SPLIT_START, tz="UTC")
    window_end = pd.Timestamp(audit.FROZEN_WINDOW_END, tz="UTC") + pd.Timedelta(days=1)   # end of the last frozen day
    assert (fx["datetime_utc"] >= split_start).all()
    assert (fx["datetime_utc"] < window_end).all()
    assert (fx["datetime_utc"] < core.FRESH_BASIS_START).all()
    for city in CITIES:
        sub = city_fx(city)
        assert len(sub) == 1512 and sub["datetime_utc"].is_unique
        assert (sub["datetime_utc"].diff().dropna() == pd.Timedelta(hours=1)).all()          # hourly and gap-free
        assert ((sub["datetime_utc"] - sub["anchor_datetime_utc"]) == DAY).all()
        assert not sub.drop(columns=["city"]).isna().any().any()
    assert (np.asarray(SLOTS.hour) % 6 == 0).all() and len(SLOTS) == 244
    assert pd.Timestamp("2026-04-01", tz="UTC") + pd.Timedelta(days=PROD_SHIFT_DAYS) == core.FRESH_BASIS_START
    assert pd.Timestamp(core.RECON_FETCH_START, tz="UTC") - pd.Timedelta(days=PROD_SHIFT_DAYS) == pd.Timestamp("2026-03-30", tz="UTC")


# ==========================================================================
# 2. Shadow-log scorer reproduces independent numpy oracles
# ==========================================================================

def test_log_truth_is_the_fixture_truth_through_ieee_738(logs_base, tmp_path):
    # the archive body recorded as evidence parses to the fixture's truth weather bit for bit
    city = "AUSTIN"
    http = os.path.join(logs_base.report["evidence_dir"], "http")
    body = next(f for f in sorted(os.listdir(http)) if f.endswith(f"archive_{city}.body"))
    parsed = core.parse_archive_payload(json.loads(open(os.path.join(http, body), "rb").read().decode("utf-8")))
    fx = city_fx(city).set_index("datetime_utc")
    parsed = parsed.set_index("datetime_utc")
    common = parsed.index.intersection(fx.index)
    # the request spans 2026-04-01 .. 2026-06-01 (the last reference target day); hours past the fixture are null
    assert parsed.index.min() == pd.Timestamp("2026-04-01T00:00:00Z") and parsed.index.max() == pd.Timestamp("2026-06-01T23:00:00Z")
    assert len(common) == 61 * 24 and parsed.loc[parsed.index.difference(fx.index), "wind_speed"].isna().all()
    for col in ("air_temp", "wind_speed", "wind_direction", "solar_radiation", "relative_humidity"):
        assert np.array_equal(parsed.loc[common, col].to_numpy(dtype=float), fx.loc[common, f"truth_{col}"].to_numpy(dtype=float))
    # truth ampacity: core.truth_ampacity == weather_to_arm5_frame == an independent thermal_model computation
    truth_df, dropped = core.truth_ampacity(parsed.reset_index().loc[parsed.reset_index()["datetime_utc"].isin(common)], city)
    arm5 = fit_models.weather_to_arm5_frame(parsed.reset_index(), city)
    w = world(city)
    got = truth_df.set_index("datetime_utc")["truth_amps"].reindex(common)
    assert dropped == [] or all(pd.Timestamp(t) not in set(common) for t in dropped)
    assert np.allclose(got.to_numpy(), w.truth.reindex(common).to_numpy(), atol=TOL, rtol=0)
    assert np.allclose(arm5.set_index("datetime_utc")["dlr_amps"].reindex(common).to_numpy(), w.truth.reindex(common).to_numpy(),
                       atol=TOL, rtol=0)


def test_log_development_run_basis_banner_and_request_count(logs_base):
    report = logs_base.report
    assert report["basis"] == "development" and report["row_source"] == "shadow_logs"
    assert "DEVELOPMENT DATA - not a confirmation result" in read_md(report)
    assert len(logs_base.server.calls) == 4           # one archive request per city, no retry
    for city in CITIES:
        block = report["per_city"][city]
        assert block["n_in_scope"] == 244 and block["n_with_truth"] == 244
        assert report["exclusions"][city]["accounting"]["lines_accepted_equals_exclusions_plus_in_scope"]
        assert report["exclusions"][city]["accounting"]["in_scope_equals_truth_exclusions_plus_with_truth"]
        assert all(report["exclusions"][city]["accounting"]["per_candidate_with_truth_equals_scored_plus_exclusions"].values())


def test_log_metrics_equal_the_numpy_oracle_for_every_city_and_candidate(logs_base):
    for city in CITIES:
        oracle = oracle_log_errors(city)
        metrics = logs_base.report["per_city"][city]["metrics"]
        for cand in CANDS:
            assert_metrics_equal(metrics[cand], oracle[cand].to_numpy())
        # the reference is judged at its own target hour; its logged-hour reading sits alongside, flagged
        logged = logs_base.report["per_city"][city]["reference_logged_hour_reading"]
        assert logged["flag"] == core.FLAG_V2_LOGGED
        assert_metrics_equal(logged, oracle["ref_logged"].to_numpy())
        assert metrics[REF]["bias"] != pytest.approx(logged["bias"], abs=1.0)    # the two readings really are different hours
        assert logged["n"] == metrics[REF]["n"] == 242                            # the last two own target hours fall after the fixture
        n = logs_base.report["per_city"][city]["n_scored"]
        assert n == {WIND: 244, COOL: 244, RAW: 244, PERSIST: 219, REF: 242}
        assert logs_base.report["per_city"][city]["candidate_exclusions"][REF] == {"reference_target_truth_missing": 2}
        assert logs_base.report["per_city"][city]["candidate_exclusions"][PERSIST] == {"candidate_unavailable": 25}


def test_log_family_margins_equal_the_complete_case_oracle(logs_base):
    errs = {city: oracle_log_errors(city) for city in CITIES}
    assert_family_equals_oracle(logs_base.report["family"], errs)
    for c in logs_base.report["family"]["comparisons"]:
        assert c["row_source"] == "shadow_logs"
        assert core.FLAG_V4 in c["flags"]
        if REF in (c["a"], c["b"]):
            assert core.FLAG_V2 in c["flags"]
        if PERSIST in (c["a"], c["b"]):
            assert core.FLAG_V3 in c["flags"]
        if WIND in (c["a"], c["b"]) or COOL in (c["a"], c["b"]):
            assert core.FLAG_V1 in c["flags"]
    assert logs_base.report["decision"]["row_source"] == "shadow_logs"
    assert logs_base.report["decision"]["label"] == "live-system check"


def test_log_anchor_source_split_equals_the_oracle(logs_base):
    for city in CITIES:
        oracle = oracle_log_errors(city)
        breakdown = logs_base.report["diagnostics"][city]["anchor_breakdown"]
        assert "exploratory" in breakdown["label"]
        gap_h = (HALF - pd.Timedelta(minutes=7)) / pd.Timedelta(hours=1)
        for cand in (WIND, COOL):
            by_source = breakdown["candidates"][cand]["by_source"]
            assert set(by_source) == {"tceq", "synoptic"}
            for src in ("tceq", "synoptic"):
                idx = [i for i in range(len(SLOTS)) if anchor_source(i) == src]
                ages = np.array([anchor_age_h(i) for i in idx])
                err = oracle[cand].iloc[idx].to_numpy()
                got = by_source[src]
                assert got["n_rows"] == len(idx)
                assert got["anchor_age_h"]["n"] == len(idx)
                for key, fn in (("min", np.min), ("median", np.median), ("mean", np.mean), ("max", np.max)):
                    assert got["anchor_age_h"][key] == pytest.approx(float(fn(ages)), abs=TOL, rel=0)
                    assert got["anchor_to_valid_h"][key] == pytest.approx(float(fn(ages + gap_h)), abs=1e-9, rel=0)
                assert got["scored"]["n"] == len(idx)
                assert got["scored"]["bias"] == pytest.approx(float(err.mean()), abs=TOL, rel=0)
                assert got["scored"]["mae"] == pytest.approx(float(np.abs(err).mean()), abs=TOL, rel=0)
        assert sum(breakdown["candidates"][WIND]["by_source"][s]["n_rows"] for s in ("tceq", "synoptic")) == 244


def test_log_sample_size_leads_the_markdown_and_the_targets_are_unmet(logs_base):
    md = read_md(logs_base.report)
    assert md.index("## Sample size") < md.index("## Headline family")
    assert core.NOT_MEASURED_STATEMENT in md and core.TRUTH_LABEL in md
    ss = logs_base.report["sample_size"]
    for city in CITIES:
        t = ss["per_city"][city]["targets"]
        assert t["tail_rate_target_met"] is False and t["mdd_target_met"] is False


# ==========================================================================
# 3. Port reproduces independent oracles on the same fixture
# ==========================================================================

def _prepared_and_preds(city, models, window=DEV_WINDOW):
    frame, weather, _ = dev_provider(city, evidence_dir="")
    win = conf.ScoredWindow(core.to_utc(window[0]), core.to_utc(window[1]))
    prepared, diag = conf.prepare_city_frame(frame, city, window=win)
    preds, pdiag = conf.candidate_predictions(prepared, weather, city, models)
    return prepared, preds, diag, pdiag


def test_port_predictions_equal_the_independent_oracle(stub_models):
    for city in CITIES:
        prepared, preds, diag, pdiag = _prepared_and_preds(city, stub_models[city])
        # scored rows equal the oracle's count of exact-lead fixture rows in the window
        fx = city_fx(city)
        in_window = fx[(fx["datetime_utc"] >= pd.Timestamp("2026-04-01", tz="UTC")) & (fx["datetime_utc"] < pd.Timestamp("2026-06-01", tz="UTC"))]
        exact = in_window[(in_window["datetime_utc"].dt.hour % 6 == 0) & ((in_window["datetime_utc"] - in_window["anchor_datetime_utc"]) == DAY)]
        assert len(preds) == len(prepared) == len(exact) == 244 and diag["n_missing_from_reconstruction"] == 0
        assert list(preds.index) == list(SLOTS)
        want = port_oracle(city, stub_models[city], SLOTS)
        for col in ("truth_amps", *CANDS):
            assert np.allclose(preds[col].to_numpy(), want[col].to_numpy(), atol=TOL, rtol=0), (city, col)
        assert pdiag["archive_vs_frame_truth"]["max_abs_diff_weather"] == 0.0
        assert pdiag["reference_feature_gaps"]["n_rows"] == 0


def test_port_wind_and_cooling_equal_the_live_methods_row_by_row(stub_models):
    for city in ("AUSTIN", "EL_PASO"):
        prepared, preds, _, _ = _prepared_and_preds(city, stub_models[city])
        point = city_point.city_point(city)
        wind_method = pipeline.WindCorrectionShadowMethod(stub_models[city][conf.WIND])
        cooling_method = pipeline.CoolingCorrectionShadowMethod(stub_models[city][conf.COOLING])
        for i in range(0, len(prepared), 7):
            one = prepared.iloc[[i]]
            assert preds[WIND].iloc[i] == pytest.approx(wind_method.predict(one, point), abs=TOL, rel=0)
            assert preds[COOL].iloc[i] == pytest.approx(cooling_method.predict(one, point), abs=TOL, rel=0)


def test_port_metrics_and_family_margins_equal_numpy(port_base, stub_models):
    report = port_base.report
    assert report["basis"] == "development" and report["row_source"] == "reconstructed_frames"
    assert "DEVELOPMENT DATA - not a confirmation result" in read_md(report)
    errs = {}
    for city in CITIES:
        errs[city] = port_errors(port_oracle(city, stub_models[city], SLOTS))
        assert report["per_city"][city]["n_scored"] == {c: 244 for c in CANDS}
        for cand in CANDS:
            assert_metrics_equal(report["per_city"][city]["metrics"][cand], errs[city][cand].to_numpy())
        diag = report["diagnostics"][city]
        assert diag["leakage_probe"]["passed"] and diag["leakage_probe"]["oracle_changed"]
        assert diag["archive_vs_frame_truth"]["max_abs_diff_weather"] == 0.0
        assert diag["missing_slots"] == [] and diag["reference_feature_gaps"]["n_rows"] == 0
    assert_family_equals_oracle(report["family"], errs)
    for c in report["family"]["comparisons"]:
        assert c["row_source"] == "reconstructed_frames" and c["flags"] == [core.FLAG_V4]
    assert report["decision"]["row_source"] == "reconstructed_frames" and report["decision"]["label"] == "headline decision"


# ==========================================================================
# 4. Precision targets are judged on effective n, end to end, for BOTH evaluators
# ==========================================================================

def _assert_pooled_nominal_never_meets_a_target(report: dict) -> None:
    ss = report["sample_size"]
    pooled = ss["pooled_nominal"]
    n_pooled = max(pooled["n_scored"].values())
    assert n_pooled >= core.TAIL_RATE_TARGET_ROWS, "non-vacuous: the pooled nominal count exceeds ~590"
    # (1) nothing in report.json may read a pooled NOMINAL count as meeting a precision target
    targets = pooled.get("targets") or {}
    assert not targets.get("tail_rate_target_met") and not targets.get("mdd_target_met"), targets
    saved = read_json(report)["sample_size"]["pooled_nominal"].get("targets") or {}
    assert not saved.get("tail_rate_target_met") and not saved.get("mdd_target_met"), saved
    # (2) the per-pair targets are judged on EFFECTIVE n (never more than the nominal n)
    unmet_despite_big_nominal = 0
    for p in ss["pairs"]:
        t = p["targets"]
        assert t["basis"] == "effective" and t["n_effective"] is not None
        judged = min(p["n_paired"], p["n_eff_bootstrap"])
        assert t["tail_rate_target_met"] == (judged >= core.TAIL_RATE_TARGET_ROWS)
        assert t["mdd_target_met"] == (judged >= core.MDD_TARGET_ROWS)
        if p["n_paired"] >= core.TAIL_RATE_TARGET_ROWS and not t["tail_rate_target_met"]:
            unmet_despite_big_nominal += 1
        assert t["n_effective"] <= p["n_paired"] + 1e-9
    assert unmet_despite_big_nominal >= 1, "at least one pair has >= 590 nominal rows yet is judged unmet on effective n"
    # (3) the Markdown never says a pooled nominal count meets a target
    md = read_md(report)
    pooled_line = next(line for line in md.splitlines() if line.startswith("- Pooled NOMINAL"))
    assert "NOT an effective sample size" in pooled_line and "target met" not in pooled_line
    assert "| not met | not met |" in md
    # (4) the decision's sample-size sentence is consistent with the effective-n judgement
    sentence = report["decision"]["statements"][0]
    met = sum(1 for p in ss["pairs"] if p["targets"]["tail_rate_target_met"])
    if met == 0:
        assert "not met for any headline test" in sentence


def test_log_report_never_reads_a_pooled_nominal_count_as_meeting_a_precision_target(logs_base):
    _assert_pooled_nominal_never_meets_a_target(logs_base.report)


def test_port_report_never_reads_a_pooled_nominal_count_as_meeting_a_precision_target(port_base):
    _assert_pooled_nominal_never_meets_a_target(port_base.report)




# ==========================================================================
# 5. Fault-injection matrix
# ==========================================================================

def run_log_fault(monkeypatch, tmp_path, *, edit=None, cities=("AUSTIN",), shift_days=0, indices=None, now=DEV_NOW,
                  params=SMALL, guard_cfg=None, **server_kw):
    """Write a (possibly faulted) copy of the realistic log, install the fake archive and score it."""
    pred = tmp_path / "p"
    write_logs(pred, cities, shift_days, edit=edit, indices=indices)
    server = FakeServer(monkeypatch, shift_days=shift_days, **server_kw)
    report = score_logs(pred, tmp_path / "evidence", cities=cities, now=now, params=params, guard_cfg=guard_cfg)
    return report, server


def _base_metrics(logs_base, city="AUSTIN"):
    return logs_base.report["per_city"][city]["metrics"]


@pytest.mark.parametrize("cand", CANDS)
def test_fault_unavailable_failed_and_fallback_values_drop_only_that_candidate(cand, logs_base, monkeypatch, tmp_path):
    unavailable, failed, fallback = {5, 15, 25}, {6, 16, 26}, {7, 17, 27}

    def edit(city, rows):
        for i, row in enumerate(rows):
            c = row["candidates"][cand]
            if i in unavailable:
                c.update(status="unavailable", ampacity_amps=None, reason="injected")
            elif i in failed:
                c.update(status="failed", ampacity_amps=None, reason="injected")
            elif i in fallback:
                c.update(fallback_used=True)
        return rows

    report, server = run_log_fault(monkeypatch, tmp_path, edit=edit)
    injected = unavailable | failed | fallback
    block, base_block = report["per_city"]["AUSTIN"], logs_base.report["per_city"]["AUSTIN"]
    expected = dict(base_block["candidate_exclusions"][cand])
    for key, rows in (("candidate_unavailable", unavailable), ("candidate_failed", failed), ("candidate_fallback_used", fallback)):
        expected[key] = expected.get(key, 0) + len(rows)
    assert block["candidate_exclusions"][cand] == expected
    assert block["n_scored"][cand] == base_block["n_scored"][cand] - len(injected)
    assert len(server.calls) == 1
    for other in CANDS:
        if other != cand:                     # untouched candidates: same n, same exclusions, identical metrics
            assert block["n_scored"][other] == base_block["n_scored"][other]
            assert block["candidate_exclusions"][other] == base_block["candidate_exclusions"][other]
            assert block["metrics"][other] == _base_metrics(logs_base)[other]
    errs = {"AUSTIN": oracle_log_errors("AUSTIN", cand_nan={cand: injected})}
    assert_metrics_equal(block["metrics"][cand], errs["AUSTIN"][cand].to_numpy())
    assert_family_equals_oracle(report["family"], errs)
    clean = oracle_family({"AUSTIN": oracle_log_errors("AUSTIN")})
    for c in report["family"]["comparisons"]:                  # only pairs that contain the faulted candidate lose rows
        if cand in (c["a"], c["b"]):
            assert c["n_paired"] < clean[(c["a"], c["b"])]["n"]
        else:
            assert c["n_paired"] == clean[(c["a"], c["b"])]["n"]
            assert c["point_margin"] == pytest.approx(clean[(c["a"], c["b"])]["margin"], abs=TOL, rel=0)


def test_fault_null_truth_hours_are_truth_missing_with_one_request(monkeypatch, tmp_path):
    null_idx = (24, 64, 104, 144)                       # distinct days, valid hour 00
    null_hours = [SLOTS[i] for i in null_idx]
    report, server = run_log_fault(monkeypatch, tmp_path, null_hours=null_hours)
    block = report["per_city"]["AUSTIN"]
    assert len(server.calls) == 1                       # one archive request for the city, no retry
    assert block["excluded_by_reason"] == {"truth_missing": 4}
    assert block["n_with_truth"] == 240
    errs = {"AUSTIN": oracle_log_errors("AUSTIN", null_hours=null_hours)}
    for cand in CANDS:
        assert_metrics_equal(block["metrics"][cand], errs["AUSTIN"][cand].to_numpy())
    assert block["n_scored"] == {WIND: 240, COOL: 240, RAW: 240, PERSIST: 215, REF: 234}
    # the four rows whose own target hour is a null hour lose only the reference
    assert block["candidate_exclusions"][REF] == {"reference_target_truth_missing": 6}
    # the dropped null hours are the four injected ones plus 2026-06-01 (the request's last day, past the fixture's end)
    past_fixture = [t.isoformat() for t in pd.date_range("2026-06-01T00:00:00Z", periods=24, freq="h")]
    assert report["diagnostics"]["AUSTIN"]["truth_dropped_null_hours"] == [t.isoformat() for t in null_hours] + past_fixture
    assert_family_equals_oracle(report["family"], errs)
    assert report["exclusions"]["AUSTIN"]["accounting"]["in_scope_equals_truth_exclusions_plus_with_truth"]


def test_fault_http_503_for_one_city_archive_is_named_not_retried_and_others_are_scored(logs_base, monkeypatch, tmp_path):
    report, server = run_log_fault(monkeypatch, tmp_path, cities=("AUSTIN", "MIDLAND"), fail_archive=("MIDLAND",))
    assert len(server.calls) == 2 and len(server.calls_for("MIDLAND")) == 1 and len(server.calls_for("AUSTIN")) == 1
    midland = report["per_city"]["MIDLAND"]
    assert midland["excluded_by_reason"] == {"truth_fetch_failed": 244}
    assert midland["n_with_truth"] == 0 and all(n == 0 for n in midland["n_scored"].values())
    fetch = report["diagnostics"]["MIDLAND"]["truth_fetch"]
    assert fetch["error"] and "503" in fetch["error"]
    metas = [f for f in os.listdir(os.path.join(report["evidence_dir"], "http")) if f.endswith("_MIDLAND.meta.json")]
    assert len(metas) == 1
    meta = json.load(open(os.path.join(report["evidence_dir"], "http", metas[0]), encoding="utf-8"))
    assert meta["status_code"] == 503
    assert report["per_city"]["AUSTIN"]["metrics"] == _base_metrics(logs_base)       # the other city is untouched
    assert report["family"]["comparisons"][0]["per_city"]["MIDLAND"]["n_paired"] == 0


def test_fault_exact_duplicate_and_later_same_valid_time_entry_keep_the_first_line(logs_base, monkeypatch, tmp_path):
    def edit(city, rows):
        first = rows[50]
        later = copy.deepcopy(first)
        later["logged_at"] = (pd.Timestamp(first["logged_at"]) + pd.Timedelta(days=1)).isoformat()
        for c in later["candidates"].values():
            c["ampacity_amps"] = (c["ampacity_amps"] or 0.0) + 1000.0
        return rows, [json.dumps(first), json.dumps(later)]

    report, _ = run_log_fault(monkeypatch, tmp_path, edit=edit)
    excl = report["exclusions"]["AUSTIN"]
    assert excl["row_level"]["duplicate_valid_time"] == 2
    dups = excl["duplicates_excluded"]
    assert [d["line_no"] for d in dups] == [245, 246] and all(d["kept_line_no"] == 51 for d in dups)
    assert dups[0]["valid_time"] == SLOTS[50].isoformat() and dups[1]["logged_at"].startswith("2026-04-")
    assert report["diagnostics"]["AUSTIN"]["logged_at_inversions"] == 0
    assert report["per_city"]["AUSTIN"]["metrics"] == _base_metrics(logs_base)       # the first line won; nothing moved
    assert report["per_city"]["AUSTIN"]["n_in_scope"] == 244
    assert excl["accounting"]["lines_accepted_equals_exclusions_plus_in_scope"]


def test_fault_legacy_rows_are_skipped_by_name_and_corridor_files_are_never_opened(logs_base, monkeypatch, tmp_path):
    v1_flat = json.dumps({"city": "AUSTIN", "ampacity_amps": SENTINEL, "valid_time": "2026-04-01T00:00:00+00:00"})
    demo_flat = json.dumps({"city": "AUSTIN", "demo": True, "candidates": {RAW: {"ampacity_amps": SENTINEL}}})
    v2 = json.dumps({"schema_version": 2, "corridor": "AUSTIN_CORPUS_CHRISTI", "candidates": {RAW: {"ampacity_amps": SENTINEL}}})

    def edit(city, rows):
        return [v1_flat, v2, demo_flat, ""] + rows, ["{not json"]

    pred = tmp_path / "p"
    write_logs(pred, ["AUSTIN"], edit=edit)
    for name in ("AUSTIN_CORPUS_CHRISTI.jsonl", "MIDLAND_EL_PASO.jsonl"):
        with open(pred / name, "w", encoding="utf-8") as fh:
            fh.write(v2 + "\n")
    opened = []
    real_open = builtins.open

    def recording_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)):
            opened.append(os.path.basename(os.fspath(file)))
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", recording_open)
    FakeServer(monkeypatch)
    report = score_logs(pred, tmp_path / "evidence")
    reader = report["exclusions"]["AUSTIN"]["reader"]
    assert reader["legacy_v1_flat"] == 2 and reader["legacy_v2_corridor"] == 1
    assert reader["blank"] == 1 and reader["malformed"] == 1 and reader["accepted_rows"] == 244
    assert "AUSTIN.jsonl" in opened
    assert not {"AUSTIN_CORPUS_CHRISTI.jsonl", "MIDLAND_EL_PASO.jsonl"} & set(opened)
    assert report["per_city"]["AUSTIN"]["metrics"] == _base_metrics(logs_base)
    assert str(SENTINEL) not in core.dumps(report) and str(SENTINEL) not in read_md(report)
    counts = score_mod.count_only_report(str(pred), ["AUSTIN"], core.GuardConfig())
    assert counts["not_read_files"] == ["AUSTIN_CORPUS_CHRISTI.jsonl", "MIDLAND_EL_PASO.jsonl"]
    assert not {"AUSTIN_CORPUS_CHRISTI.jsonl", "MIDLAND_EL_PASO.jsonl"} & set(opened)


def test_fault_rows_lacking_forecast_model_and_other_models_never_reach_a_metric(logs_base, monkeypatch, tmp_path):
    def edit(city, rows):
        out = []
        for i, row in enumerate(rows):
            if i == 40:   # a V6 row logged FIRST for a valid_time that a later gfs_seamless row also holds
                out.append(sentinel_row(city, row["valid_time"], model=None))
            out.append(row)
        for k in range(4):
            out.append(sentinel_row(city, pd.Timestamp("2026-03-25T00:00:00Z") + pd.Timedelta(hours=6 * k), model=None))
        out.append(sentinel_row(city, "2026-03-26T00:00:00Z", model="ecmwf_ifs"))
        return out

    report, _ = run_log_fault(monkeypatch, tmp_path, edit=edit)
    row_level = report["exclusions"]["AUSTIN"]["row_level"]
    assert row_level["missing_forecast_model"] == 5 and row_level["other_forecast_model"] == 1
    assert row_level["duplicate_valid_time"] == 0                      # V6 is excluded before first-logged dedupe
    assert report["exclusions"]["AUSTIN"]["other_forecast_model_by_model"] == {"ecmwf_ifs": 1}
    assert report["diagnostics"]["AUSTIN"]["forecast_model_counts"] == {"<missing>": 5, "gfs_seamless": 244, "ecmwf_ifs": 1}
    assert report["per_city"]["AUSTIN"]["n_in_scope"] == 244
    assert report["per_city"]["AUSTIN"]["metrics"] == _base_metrics(logs_base)   # the gfs row won; no sentinel in any metric
    assert str(SENTINEL) not in core.dumps(report) and str(SENTINEL) not in read_md(report)


def test_fault_rows_at_or_after_the_cutoff_and_a_reference_target_at_or_after_it(monkeypatch, tmp_path):
    # FRESH-calendar log (+200 days) restricted to logged valid times 2026-11-15T00Z .. 2026-11-17T06Z
    indices = range(112, 122)
    report, server = run_log_fault(monkeypatch, tmp_path, shift_days=FRESH_LOG_SHIFT_DAYS, indices=indices,
                                   now=INSTANT, params=None)
    assert report["basis"] == "FRESH" and report["guard"]["defaults_used"]
    excl = report["exclusions"]["AUSTIN"]
    assert excl["row_level"]["at_or_after_cutoff"] == 2          # exactly the cutoff and cutoff + 6 h
    block = report["per_city"]["AUSTIN"]
    assert block["n_in_scope"] == 8                              # cutoff - 6 h (2026-11-16T18Z) is kept
    assert server.calls[0][1]["end_date"] == "2026-11-16"        # never fetches the cutoff day
    # own target hour (valid + 12 h) at or after the cutoff: the rows valid 2026-11-16T12Z and T18Z
    assert block["candidate_exclusions"][REF] == {"reference_target_at_or_after_cutoff": 2}
    assert block["n_scored"] == {WIND: 8, COOL: 8, RAW: 8, PERSIST: 8, REF: 6}
    errs = {"AUSTIN": oracle_log_errors("AUSTIN", shift_days=FRESH_LOG_SHIFT_DAYS, cutoff=CUTOFF, only=set(indices))}
    for cand in CANDS:
        assert_metrics_equal(block["metrics"][cand], errs["AUSTIN"][cand].to_numpy())


def test_fault_lead_structure_violations_are_counted_and_excluded(logs_base, monkeypatch, tmp_path):
    def edit(city, rows):
        rows[33]["horizon_minutes"] = 60                                               # horizon 60
        rows[30]["valid_time"] = (pd.Timestamp(rows[30]["valid_time"]) + pd.Timedelta(hours=1)).isoformat()   # valid hour 13
        rows[32]["decision_time"] = (pd.Timestamp(rows[32]["valid_time"]) - pd.Timedelta(hours=20)).isoformat()  # gap 20 h
        return rows

    report, _ = run_log_fault(monkeypatch, tmp_path, edit=edit)
    excl = report["exclusions"]["AUSTIN"]
    assert excl["row_level"]["lead_structure_mismatch"] == 3
    assert {"horizon_not_1440", "valid_time_off_6h_grid", "decision_gap_outside_11_17h"} <= set(excl["lead_structure_detail"])
    errs = {"AUSTIN": oracle_log_errors("AUSTIN", drop_rows={30, 32, 33})}
    block = report["per_city"]["AUSTIN"]
    assert block["n_in_scope"] == 241
    for cand in CANDS:
        assert_metrics_equal(block["metrics"][cand], errs["AUSTIN"][cand].to_numpy())
    assert_family_equals_oracle(report["family"], errs)
    assert block["metrics"][RAW] != _base_metrics(logs_base)[RAW]


def test_port_fault_a_nan_weather_hour_is_missing_from_reconstruction_and_poisons_only_its_reference_rows(stub_models, evidence_root):
    hour = pd.Timestamp("2026-04-20T12:00:00Z")

    def provider(city, *, evidence_dir):
        frame, weather, meta = dev_provider(city, evidence_dir=evidence_dir)
        frame, weather = frame.copy(), weather.copy()
        frame.loc[frame["datetime_utc"] == hour, "truth_wind_speed"] = np.nan                  # the hour itself
        frame.loc[frame["datetime_utc"] == hour + DAY, "anchor_wind_speed"] = np.nan            # its 24 h-later anchor copy
        weather.loc[weather["datetime_utc"] == hour, "wind_speed"] = np.nan
        return frame, weather, meta

    report = run_port(evidence_root, stub_models, frame_provider=provider)
    block = report["per_city"]["AUSTIN"]
    assert block["excluded_by_reason"] == {"missing_from_reconstruction": 2}
    assert report["diagnostics"]["AUSTIN"]["missing_slots"] == [hour.isoformat(), (hour + DAY).isoformat()]
    assert report["diagnostics"]["AUSTIN"]["preparation"]["n_rows_dropped_null_weather"] == 2
    # reference features at anchor a read hours a-6..a, so the rows whose anchor lies in [hour, hour + 6 h] lose the reference;
    # the one at hour + 24 h is already missing, leaving valid hour + 30 h
    gaps = report["diagnostics"]["AUSTIN"]["reference_feature_gaps"]
    assert gaps["valid_times"] == [(hour + pd.Timedelta(hours=30)).isoformat()] and gaps["n_rows"] == 1
    assert block["candidate_exclusions"][REF] == {conf.REASON_REFERENCE_FEATURES: 1}
    assert block["n_scored"] == {WIND: 242, COOL: 242, RAW: 242, PERSIST: 242, REF: 241}
    want = port_oracle("AUSTIN", stub_models["AUSTIN"], SLOTS)
    errs = port_errors(want).drop(index=[hour, hour + DAY])
    errs.loc[hour + pd.Timedelta(hours=30), REF] = np.nan
    for cand in CANDS:
        assert_metrics_equal(block["metrics"][cand], errs[cand].to_numpy())
    # untouched rows are what the clean fixture produces
    _, clean, _, _ = _prepared_and_preds("AUSTIN", stub_models["AUSTIN"])
    frame, weather, _ = provider("AUSTIN", evidence_dir="")
    prepared, _ = conf.prepare_city_frame(frame, "AUSTIN", window=conf.ScoredWindow(core.to_utc(DEV_WINDOW[0]), core.to_utc(DEV_WINDOW[1])))
    faulted, _ = conf.candidate_predictions(prepared, weather, "AUSTIN", stub_models["AUSTIN"])
    common = faulted.index
    assert len(common) == 242
    for col in ("truth_amps", RAW, PERSIST, WIND, COOL):
        assert np.allclose(faulted[col].to_numpy(), clean.loc[common, col].to_numpy(), atol=TOL, rtol=0)
    ok = faulted[REF].notna()
    assert np.allclose(faulted.loc[ok, REF].to_numpy(), clean.loc[faulted.index[ok], REF].to_numpy(), atol=TOL, rtol=0)


def prod_run(monkeypatch, evidence_root, *, cities=CITIES, now=INSTANT, fail_previous=(), params=None, guard_cfg=None, **kw):
    """The production path: anchored_pair_frame behind the recorder, fed by a fake server that re-dates the fixture."""
    server = FakeServer(monkeypatch, shift_days=PROD_SHIFT_DAYS, fail_previous=fail_previous)
    report = conf.run_confirmation(cities=list(cities), guard_cfg=guard_cfg or core.GuardConfig(), evidence_root=str(evidence_root),
                                   now=now, params=params, **kw)
    return report, server


def test_port_fault_http_503_on_one_citys_previous_runs_is_named_not_retried_and_others_match_the_oracle(
        monkeypatch, evidence_root, model_dir, stub_models):
    report, server = prod_run(monkeypatch, evidence_root, fail_previous=("MIDLAND",))
    assert list(report["failed_cities"]) == ["MIDLAND"] and report["failed_cities"]["MIDLAND"]["stage"] == "frame_fetch_failed"
    assert all(len(server.calls_for(c)) == 2 for c in CITIES)                      # archive + previous-runs once each: no retry
    http = os.path.join(report["evidence_dir"], "http")
    midland = sorted(f for f in os.listdir(http) if f.endswith("_MIDLAND.meta.json"))
    assert [json.load(open(os.path.join(http, f), encoding="utf-8"))["status_code"] for f in midland] == [200, 503]
    assert os.path.isfile(os.path.join(http, midland[0].replace(".meta.json", ".body")))      # the archive body is still recorded
    assert report["per_city"]["MIDLAND"]["excluded_by_reason"] == {"city_failed:frame_fetch_failed": 1}
    errs = {}
    for city in ("AUSTIN", "CORPUS_CHRISTI", "EL_PASO"):
        errs[city] = port_errors(port_oracle(city, stub_models[city], PROD_SLOTS))
        assert report["per_city"][city]["n_scored"] == {c: 192 for c in CANDS}
        for cand in CANDS:
            assert_metrics_equal(report["per_city"][city]["metrics"][cand], errs[city][cand].to_numpy())
    errs["MIDLAND"] = pd.DataFrame({c: pd.Series(dtype=float) for c in CANDS})
    assert_family_equals_oracle(report["family"], errs)


# ==========================================================================
# 6. Guard end to end, both tools (FRESH-calendar but fabricated data)
# ==========================================================================

def _fresh_logs(tmp_path, cities=("AUSTIN",)):
    pred = tmp_path / "p"
    write_logs(pred, cities, FRESH_LOG_SHIFT_DAYS)
    return pred


def _assert_pooled_nominal_not_judged(report):
    pooled = report["sample_size"]["pooled_nominal"]
    assert not pooled["targets"]["tail_rate_target_met"] and not pooled["targets"]["mdd_target_met"]


def test_logs_guard_refuses_one_second_before_the_instant_with_no_request_no_directory_no_fresh_read(monkeypatch, tmp_path, evidence_root):
    pred = _fresh_logs(tmp_path, CITIES)
    opened = []
    real_open = builtins.open

    def recording_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)):
            opened.append(os.fspath(file))
        return real_open(file, *a, **k)

    monkeypatch.setattr(builtins, "open", recording_open)     # requests.get stays the autouse boom
    with pytest.raises(core.EvaluationGuardError, match="evaluation instant"):
        score_logs(pred, evidence_root, cities=CITIES, now=BEFORE_INSTANT, params=None)
    assert not os.path.exists(evidence_root)
    assert not any("anchored_pair_frame" in p or "data/experiment" in p.replace(os.sep, "/") for p in opened)
    assert all(os.path.dirname(p) == str(pred) for p in opened if p.endswith(".jsonl"))


def test_logs_at_the_instant_score_fresh_rows_and_exclude_everything_from_the_cutoff_on(monkeypatch, tmp_path, evidence_root):
    pred = _fresh_logs(tmp_path, CITIES)
    server = FakeServer(monkeypatch, shift_days=FRESH_LOG_SHIFT_DAYS)
    report = score_logs(pred, evidence_root, cities=CITIES, now=INSTANT, params=None)
    assert report["basis"] == "FRESH" and report["guard"]["defaults_used"] and report["guard"]["override_reason"] is None
    assert len(server.calls) == 4
    errs = {}
    for city in CITIES:
        assert report["exclusions"][city]["row_level"]["at_or_after_cutoff"] == 124        # logged 2026-11-17 .. 2026-12-17
        assert report["per_city"][city]["n_in_scope"] == 120
        errs[city] = oracle_log_errors(city, shift_days=FRESH_LOG_SHIFT_DAYS, cutoff=CUTOFF)
        for cand in CANDS:
            assert_metrics_equal(report["per_city"][city]["metrics"][cand], errs[city][cand].to_numpy())
    assert_family_equals_oracle(report["family"], errs)
    assert "DEVELOPMENT DATA" not in read_md(report)
    _assert_pooled_nominal_not_judged(report)


def test_logs_override_is_recorded_in_json_and_markdown(monkeypatch, tmp_path, evidence_root):
    pred = _fresh_logs(tmp_path)
    FakeServer(monkeypatch, shift_days=FRESH_LOG_SHIFT_DAYS)
    report = score_logs(pred, evidence_root, now=BEFORE_INSTANT, guard_cfg=core.GuardConfig(override_reason="rehearsal of the evaluation day"))
    assert report["guard"]["override_reason"] == "rehearsal of the evaluation day"
    assert read_json(report)["guard"]["override_reason"] == "rehearsal of the evaluation day"
    assert "Override: rehearsal of the evaluation day" in read_md(report)


def test_logs_second_fresh_run_is_refused_even_after_a_first_run_that_crashed(monkeypatch, tmp_path, evidence_root):
    pred = _fresh_logs(tmp_path)
    FakeServer(monkeypatch, shift_days=FRESH_LOG_SHIFT_DAYS)
    first = score_logs(pred, evidence_root, now=INSTANT, params=None)
    assert first["basis"] == "FRESH"
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        score_logs(pred, evidence_root, now="2026-11-24T00:00:05Z", params=None)
    assert len(os.listdir(evidence_root)) == 1
    again = score_logs(pred, evidence_root, now="2026-11-24T00:00:09Z",
                       guard_cfg=core.GuardConfig(override_reason="owner-approved rerun"), params=None)
    assert again["guard"]["prior_fresh_runs"] and again["guard"]["override_reason"] == "owner-approved rerun"

    other_root = str(tmp_path / "evidence_crash")
    with monkeypatch.context() as m:
        m.setattr(stats, "build_family_report", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash after the guard passed")))
        with pytest.raises(RuntimeError, match="crash after"):
            score_logs(pred, other_root, now=INSTANT, params=None)
    (run_dir,) = os.listdir(other_root)
    assert os.path.isfile(os.path.join(other_root, run_dir, "run_started.json"))
    assert not os.path.exists(os.path.join(other_root, run_dir, "report.json"))
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        score_logs(pred, other_root, now="2026-11-24T00:01:00Z", params=None)


def test_logs_nondefault_block_lengths_in_a_fresh_run_are_refused_without_an_override(monkeypatch, tmp_path, evidence_root, capsys):
    pred = _fresh_logs(tmp_path)
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp(INSTANT))
    code = score_mod.main(["--predictions-dir", str(pred), "--cities", "AUSTIN", "--evidence-root", evidence_root,
                           "--block-lengths", "1", "2"])
    assert code == 2 and "override" in capsys.readouterr().err
    assert not os.path.exists(evidence_root)
    with pytest.raises(SystemExit):
        score_mod.build_parser().parse_args(["--row-gate", "1"])


def test_port_guard_refuses_before_the_instant_before_any_request_frame_build_artifact_load_or_directory(monkeypatch, evidence_root):
    def boom(*a, **k):
        raise AssertionError("must not be reached before the guard passes")

    monkeypatch.setattr(forecast_experiment, "anchored_pair_frame", boom)
    monkeypatch.setattr(pipeline, "load_correction_model", boom)
    with pytest.raises(core.EvaluationGuardError, match="evaluation instant"):
        conf.run_confirmation(cities=CITIES, guard_cfg=core.GuardConfig(), evidence_root=evidence_root, now=BEFORE_INSTANT)
    assert not os.path.exists(evidence_root)
    assert not os.path.exists(config.FORECAST_EXPERIMENT_CACHE_DIR)


def test_port_at_the_instant_scores_192_fresh_slots_per_city_and_matches_the_oracle(monkeypatch, evidence_root, model_dir, stub_models):
    report, server = prod_run(monkeypatch, evidence_root)
    assert report["basis"] == "FRESH" and report["guard"]["defaults_used"] and report["guard"]["override_reason"] is None
    assert len(server.calls) == 8 and all(len(server.calls_for(c)) == 2 for c in CITIES)
    for call in server.calls:
        assert call[1]["start_date"] == core.RECON_FETCH_START and call[1]["end_date"] == core.RECON_FETCH_END
    assert report["config"]["model_loader"] == "load_correction_model"
    errs = {}
    for city in CITIES:
        errs[city] = port_errors(port_oracle(city, stub_models[city], PROD_SLOTS))
        assert report["per_city"][city]["n_scored"] == {c: 192 for c in CANDS}
        for cand in CANDS:
            assert_metrics_equal(report["per_city"][city]["metrics"][cand], errs[city][cand].to_numpy())
        diag = report["diagnostics"][city]
        assert diag["leakage_probe"]["passed"] and diag["archive_vs_frame_truth"]["max_abs_diff_weather"] == 0.0
        assert diag["missing_slots"] == []
    assert_family_equals_oracle(report["family"], errs)
    ev = report["evidence_dir"]
    assert len([f for f in os.listdir(os.path.join(ev, "http")) if f.endswith(".body")]) == 8
    assert len(os.listdir(os.path.join(ev, "frames"))) == 4
    assert not os.path.exists(config.FORECAST_EXPERIMENT_CACHE_DIR)                # nothing under the (real-path stand-in) cache dir
    assert "DEVELOPMENT DATA" not in read_md(report)
    _assert_pooled_nominal_not_judged(report)
    assert report["sample_size"]["pooled_nominal"]["n_scored"][RAW] == 768


def test_port_override_is_recorded_in_json_and_markdown(monkeypatch, evidence_root, model_dir):
    report, _ = prod_run(monkeypatch, evidence_root, cities=["AUSTIN"], now=BEFORE_INSTANT,
                         guard_cfg=core.GuardConfig(override_reason="rehearsal of the evaluation day"))
    assert report["guard"]["override_reason"] == "rehearsal of the evaluation day"
    assert read_json(report)["guard"]["override_reason"] == "rehearsal of the evaluation day"
    assert "Override: rehearsal of the evaluation day" in read_md(report)


def test_port_second_fresh_run_is_refused_even_after_a_first_run_that_crashed(monkeypatch, evidence_root, model_dir, tmp_path):
    first, _ = prod_run(monkeypatch, evidence_root, cities=["AUSTIN"])
    assert first["basis"] == "FRESH"
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        prod_run(monkeypatch, evidence_root, cities=["AUSTIN"], now="2026-11-24T00:00:05Z")
    assert len(os.listdir(evidence_root)) == 1
    again, _ = prod_run(monkeypatch, evidence_root, cities=["AUSTIN"], now="2026-11-24T00:00:09Z",
                        guard_cfg=core.GuardConfig(override_reason="owner-approved rerun"))
    assert again["guard"]["prior_fresh_runs"] and again["guard"]["override_reason"] == "owner-approved rerun"

    other_root = str(tmp_path / "evidence_crash")
    with monkeypatch.context() as m:
        m.setattr(stats, "build_family_report", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("crash after the guard passed")))
        with pytest.raises(RuntimeError, match="crash after"):
            prod_run(m, other_root, cities=["AUSTIN"])
    (run_dir,) = os.listdir(other_root)
    assert os.path.isfile(os.path.join(other_root, run_dir, "run_started.json"))
    assert not os.path.exists(os.path.join(other_root, run_dir, "report.json"))
    with pytest.raises(core.EvaluationGuardError, match="second FRESH run"):
        prod_run(monkeypatch, other_root, cities=["AUSTIN"], now="2026-11-24T00:01:00Z")


def test_port_nondefault_block_lengths_in_a_fresh_run_are_refused_without_an_override(monkeypatch, evidence_root, capsys):
    monkeypatch.setattr(core, "utcnow", lambda: pd.Timestamp(INSTANT))
    assert conf.main(["--evidence-root", evidence_root, "--block-lengths", "1", "2"]) == 2
    assert "override" in capsys.readouterr().err
    assert not os.path.exists(evidence_root)


# ==========================================================================
# 7. FRESH-cache read prohibition
# ==========================================================================

REAL_FRESH_CACHE = "data/experiment/anchored_pair_frame_{city}_2026-09-30_2026-10-04_lead24_previous_runs.csv"
FROZEN_CACHE = "data/experiment/anchored_pair_frame_{city}_2024-01-20_2026-09-29_lead24_previous_runs.csv"


def test_the_real_fresh_cache_paths_are_refused_and_the_frozen_window_paths_are_not(tmp_path):
    for city in CITIES:
        path = REAL_FRESH_CACHE.format(city=city)
        with pytest.raises(core.EvaluationGuardError):
            core.assert_not_fresh_experiment_cache(path)
        with pytest.raises(core.EvaluationGuardError):
            open(path)                                    # the autouse spy, which is what protects every other test
        with pytest.raises(core.EvaluationGuardError):
            pd.read_csv(path)
        core.assert_not_fresh_experiment_cache(FROZEN_CACHE.format(city=city))
    # a FRESH-window cache is allowed only inside the run's own evidence directory
    inside = tmp_path / "evidence" / "reconstructed_frames_x" / "frames" / "anchored_pair_frame_AUSTIN_2026-09-28_2026-11-16_lead24_previous_runs.csv"
    core.assert_not_fresh_experiment_cache(str(inside), allow_dir=str(tmp_path / "evidence"))
    with pytest.raises(core.EvaluationGuardError):
        core.assert_not_fresh_experiment_cache(str(inside), allow_dir=str(tmp_path / "elsewhere"))


def test_no_evaluator_mode_opens_a_fresh_experiment_cache_outside_its_own_evidence_directory(
        monkeypatch, tmp_path, evidence_root, model_dir, stub_models):
    opened = []
    real_open, real_read_csv = builtins.open, pd.read_csv

    def rec_open(file, *a, **k):
        if isinstance(file, (str, os.PathLike)):
            opened.append(os.fspath(file))
        return real_open(file, *a, **k)

    def rec_read_csv(path, *a, **k):
        if isinstance(path, (str, os.PathLike)):
            opened.append(os.fspath(path))
        return real_read_csv(path, *a, **k)

    monkeypatch.setattr(builtins, "open", rec_open)
    monkeypatch.setattr(pd, "read_csv", rec_read_csv)
    dev_logs, fresh_logs = tmp_path / "dev_logs", tmp_path / "fresh_logs"
    write_logs(dev_logs, ["AUSTIN"], 0)
    write_logs(fresh_logs, ["AUSTIN"], FRESH_LOG_SHIFT_DAYS)
    # count-only (permitted at any time: no request, no ampacity)
    counts = score_mod.count_only_report(str(fresh_logs), ["AUSTIN"], core.GuardConfig())
    assert counts["cities"]["AUSTIN"]["counters"]["in_scope_rows"] == 120
    # dry run of the port
    plan = conf.dry_run(cities=CITIES, guard_cfg=core.GuardConfig(), evidence_root=evidence_root, now=DEV_NOW)
    assert len(plan["planned_requests"]) == 8
    # log scoring on a development basis and on a FRESH-calendar basis, the port on a development basis and the production provider
    with monkeypatch.context() as m:
        FakeServer(m)
        score_logs(dev_logs, tmp_path / "ev_dev_logs")
    with monkeypatch.context() as m:
        FakeServer(m, shift_days=FRESH_LOG_SHIFT_DAYS)
        score_logs(fresh_logs, tmp_path / "ev_fresh_logs", now=INSTANT, params=None)
    run_port(tmp_path / "ev_dev_port", stub_models)
    with monkeypatch.context() as m:
        prod_run(m, evidence_root, cities=["AUSTIN"])
    names = [(p, core._CACHE_NAME.match(os.path.basename(p))) for p in opened]
    fresh_like = [p for p, match in names if match and pd.Timestamp(match.group("end")) > pd.Timestamp(core.FROZEN_WINDOW_END_DATE)]
    allowed = os.path.realpath(evidence_root) + os.sep
    assert all(os.path.realpath(p).startswith(allowed) for p in fresh_like)      # only the port's own redirected frame cache
    assert not any("data/experiment" in p.replace(os.sep, "/") for p in opened)


def test_the_port_refuses_a_preexisting_fresh_window_cache_before_anchored_pair_frame(monkeypatch, evidence_root, model_dir):
    server = FakeServer(monkeypatch, shift_days=PROD_SHIFT_DAYS)
    called = []
    real_new_dir = core.new_evidence_dir
    real_frame = forecast_experiment.anchored_pair_frame

    def seeded_new_evidence_dir(*args, **kwargs):
        path = real_new_dir(*args, **kwargs)
        os.makedirs(os.path.join(path, "frames"))
        name = f"anchored_pair_frame_AUSTIN_{core.RECON_FETCH_START}_{core.RECON_FETCH_END}_lead24_previous_runs.csv"
        with open(os.path.join(path, "frames", name), "w", encoding="utf-8") as fh:
            fh.write("datetime_utc\n")
        return path

    monkeypatch.setattr(core, "new_evidence_dir", seeded_new_evidence_dir)
    monkeypatch.setattr(forecast_experiment, "anchored_pair_frame", lambda *a, **k: called.append(a) or real_frame(*a, **k))
    with pytest.raises(core.EvaluationGuardError, match="already exists"):
        conf.run_confirmation(cities=["AUSTIN"], guard_cfg=core.GuardConfig(), evidence_root=evidence_root, now=INSTANT)
    assert called == [] and server.calls == []


# ==========================================================================
# 8. Never pooled
# ==========================================================================

def _row_sources_in(obj) -> set:
    found = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "row_source":
                found.add(value)
            found |= _row_sources_in(value)
    elif isinstance(obj, list):
        for value in obj:
            found |= _row_sources_in(value)
    return found


@pytest.fixture
def small_reports(monkeypatch, tmp_path, stub_models):
    """The two development reports at n = 50 (logs, AUSTIN, first 50 slots) and n = 190 (port, AUSTIN)."""
    pred = tmp_path / "small_logs"
    write_logs(pred, ["AUSTIN"], 0, indices=range(50))
    FakeServer(monkeypatch)
    logs = score_logs(pred, tmp_path / "ev_logs")
    port = run_port(tmp_path / "ev_port", stub_models, window=("2026-04-01T00:00:00Z", "2026-05-18T12:00:00Z"))
    return SimpleNamespace(logs=logs, port=port)


def test_each_tool_reports_only_its_own_row_source(logs_base, port_base):
    assert _row_sources_in(logs_base.report) == {"shadow_logs"}
    assert _row_sources_in(port_base.report) == {"reconstructed_frames"}
    for report, source in ((logs_base.report, "shadow_logs"), (port_base.report, "reconstructed_frames")):
        saved = read_json(report)
        assert saved["row_source"] == source and _row_sources_in(saved) == {source}


def test_apply_ship_rule_refuses_a_family_that_mixes_row_sources(port_base, logs_base):
    mixed = copy.deepcopy(port_base.report["family"])
    mixed["comparisons"][4]["row_source"] = "shadow_logs"
    with pytest.raises(ValueError, match="mixes row sources"):
        decision.apply_ship_rule(mixed)
    relabelled = copy.deepcopy(logs_base.report["family"])
    relabelled["row_source"] = "reconstructed_frames"
    with pytest.raises(ValueError, match="row source"):
        decision.apply_ship_rule(relabelled)


def test_build_family_report_refuses_error_frames_tagged_with_two_row_sources(monkeypatch, tmp_path, stub_models):
    captured = {}
    real = stats.build_family_report

    def spy(errors_by_city, **kwargs):
        captured["frames"] = {c: f.copy() for c, f in errors_by_city.items()}
        captured["tags"] = {c: dict(f.attrs) for c, f in errors_by_city.items()}
        return real(errors_by_city, **kwargs)

    monkeypatch.setattr(stats, "build_family_report", spy)
    write_logs(tmp_path / "p", ["AUSTIN"], 0, indices=range(40))
    with monkeypatch.context() as m:
        FakeServer(m)
        score_logs(tmp_path / "p", tmp_path / "ev_a")
    log_frames, log_tags = captured["frames"], captured["tags"]
    run_port(tmp_path / "ev_b", stub_models, window=("2026-04-01T00:00:00Z", "2026-04-11T00:00:00Z"))
    port_frames, port_tags = captured["frames"], captured["tags"]
    assert log_tags["AUSTIN"].get("row_source") == "shadow_logs"
    assert port_tags["AUSTIN"].get("row_source") == "reconstructed_frames"
    for frame, tags in ((log_frames["AUSTIN"], log_tags["AUSTIN"]), (port_frames["AUSTIN"], port_tags["AUSTIN"])):
        frame.attrs.update(tags)
    with pytest.raises(ValueError, match="row source"):
        real({"AUSTIN": log_frames["AUSTIN"], "MIDLAND": port_frames["AUSTIN"]}, row_source="shadow_logs")
    with pytest.raises(ValueError, match="row source"):
        real({"AUSTIN": log_frames["AUSTIN"]}, row_source="reconstructed_frames")
    ok = real({"AUSTIN": log_frames["AUSTIN"]}, row_source="shadow_logs")
    assert ok["row_source"] == "shadow_logs" and all(c["row_source"] == "shadow_logs" for c in ok["comparisons"])
    with pytest.raises(ValueError, match="unknown row_source"):
        real({"AUSTIN": log_frames["AUSTIN"]}, row_source="pooled")


def test_combined_summary_keeps_the_two_sources_apart_and_never_adds_their_counts(small_reports):
    logs, port = small_reports.logs, small_reports.port
    assert logs["per_city"]["AUSTIN"]["n_scored"][RAW] == 50 and port["per_city"]["AUSTIN"]["n_scored"][RAW] == 190
    text = decision.combined_summary(port, logs)
    head, rest = text.split("## Live-system check")
    live, agreement = rest.split("## Agreement")
    assert "row source: reconstructed_frames" in head and "190 to 190" in head
    assert "row source: shadow_logs" in live and "45 to 50" in live and "190" not in live
    assert "240" not in text and "235" not in text                      # 50 + 190 and 45 + 190 never appear
    # the headline decision is exactly the reconstructed report's decision; the live check is the logs report's own
    assert f"Action: ship {port['decision']['action']['ship']} ({port['decision']['action']['level']})" in head
    assert f"Action: ship {logs['decision']['action']['ship']} ({logs['decision']['action']['level']})" in live
    assert f"Working choice: {port['decision']['working_choice']}" in head
    assert "never changes the headline decision" in agreement
    assert port["decision"]["label"] == "headline decision" and logs["decision"]["label"] == "live-system check"
    with pytest.raises(ValueError, match="never swapped or duplicated"):
        decision.combined_summary(logs, port)
    with pytest.raises(ValueError, match="never swapped or duplicated"):
        decision.combined_summary(port, port)
    with pytest.raises(ValueError, match="never swapped or duplicated"):
        decision.combined_summary(logs, logs)
