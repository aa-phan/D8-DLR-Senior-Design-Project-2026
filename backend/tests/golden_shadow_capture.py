"""
COND-02 golden helper: capture and compare the frozen shadow path (production-pipeline Phase 7, plan 01).

What COND-02 promises. Production rating moves to per-city conductor configs while the shadow collector,
the 12 frozen Drake artifacts and the frozen evaluation keep the Drake configuration. The shadow side imports
`config`, `city_point`, `forecast_training`, `ampacity_forecast`, `thermal_model`, `weather_provider` and
`wind_vector` from the production side, so every later edit sits next to code the frozen path runs. This module
produces and checks a payload that pins the frozen path's outputs: city_point geometry, the truth /
raw_forecast / persistence arms, the three shadow fits, the collector's per-row methods, the dev-basis
evaluation family and the sha256 of the 12 frozen artifacts.

Why the baseline is taken from a materialized d71c501 tree. A baseline captured from the working tree after the
first production edit would compare modified code with itself (research Pitfall 1). So `capture` runs
`git archive <commit> backend` into a temporary directory and computes the payload in a CHILD process whose
PYTHONPATH holds only that copy; the child refuses to emit when `config.__file__` (or any other imported
backend module) is not inside the copy.

What it never does. It never loads one of the 12 real frozen artifacts (joblib.load and
forecast_shadow_pipeline.load_correction_model are never called). The dev fixture is TEST-split data, and
TEST scoring of the real artifacts needs the signed v4 (research option (e)). Fits and the dev-basis run use
stub models fitted on the fixture, exactly the recipe of forecast_shadow_eval_validation_test.fit_stub_models.
Artifacts are only hashed (hashlib).

Commands (run from the repository root with the project venv):

    PYTHONPATH=backend .venv/bin/python backend/tests/golden_shadow_capture.py --capture
    PYTHONPATH=backend .venv/bin/python backend/tests/golden_shadow_capture.py --check

The module name matches neither `test_*.py` nor `*_test.py`, so pytest does not collect it.
"""

from __future__ import annotations

import argparse
import functools
import hashlib
import io
import json
import os
import platform
import subprocess
import sys
import tarfile
import tempfile

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))

BASELINE_COMMIT = "d71c501"
FIXTURE = os.path.join(_HERE, "fixtures", "shadow_eval_frozen_dev_frames.csv.gz")
FIXTURE_SHA256 = "a397c82d5d541ee0941204a6c64c53782529b4a6593ed9bf83a9d22cdae26250"
GOLDEN_PATH = os.path.join(_HERE, "fixtures", "golden_shadow_baseline_d71c501.json")
ARTIFACT_MANIFEST = os.path.join(REPO_ROOT, "data", "shadow", "models", "ARTIFACT_HASHES.sha256")
DEV_WINDOW = ("2026-04-01T00:00:00Z", "2026-06-01T00:00:00Z")
DEV_NOW = "2026-10-13T08:00:00Z"
FIT_SHIFT_DAYS = 365
N_RESAMPLES = 300
COLLECTOR_ROWS = 8
SECTIONS = ("geometry", "arms", "fits", "collector", "family", "artifacts")

# The frozen list (COND-02): nothing here may differ from BASELINE_COMMIT.
FROZEN_PATHS = (
    "backend/forecast_shadow_pipeline.py",
    "backend/forecast_shadow_fit_models.py",
    "backend/forecast_shadow_fit_reference_refit.py",
    "backend/forecast_shadow_demo.py",
    "backend/forecast_shadow_collect.py",
    "backend/forecast_shadow_check_models.py",
    "backend/forecast_shadow_healthcheck.py",
    "backend/forecast_shadow_render_table.py",
    "backend/forecast_shadow_score_stats.py",
    "backend/forecast_shadow_decision.py",
    "backend/legacy_corridor.py",
    "backend/forecast_experiment.py",
    "backend/forecast_experiment_audit.py",
    "backend/forecast_correction_models.py",
    "backend/experiment_splits.py",
    ".github/workflows/shadow_collect.yml",
    "data/shadow/models",
)
# Evaluation modules a signed confirmation protocol v4 may edit (and only then).
V4_PERMITTED_PATHS = (
    "backend/forecast_shadow_eval_core.py",
    "backend/forecast_shadow_confirm.py",
    "backend/forecast_shadow_score.py",
)
V4_SIGNING_COPY = os.path.join(
    "docs", "data-science", "decisions", "confirmation_protocol_v4_early_selection_SIGNING_COPY.md")

_DATETIME_COLUMNS = ("datetime_utc", "anchor_datetime_utc", "fcst_anchor_datetime_utc")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def array_digest(values) -> dict:
    """{n, sha256, first, last}: NaN becomes -1e300 before hashing the little-endian float64 bytes."""
    arr = np.asarray(values, dtype=float).reshape(-1)
    cleaned = np.nan_to_num(arr, nan=-1e300, posinf=np.inf, neginf=-np.inf)
    return {
        "n": int(arr.size),
        "sha256": sha256_bytes(np.ascontiguousarray(cleaned, dtype="<f8").tobytes()),
        "first": repr(float(arr[0])) if arr.size else None,
        "last": repr(float(arr[-1])) if arr.size else None,
    }


def _jsonable(value):
    """Plain-JSON form: tuples to lists, numpy scalars to Python, floats stay exact Python floats."""
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return repr(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    return value


def versions() -> dict:
    import scipy
    import sklearn
    return {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
            "sklearn": sklearn.__version__, "scipy": scipy.__version__}


@functools.lru_cache(maxsize=1)
def _fixture_all() -> pd.DataFrame:
    actual = sha256_path(FIXTURE)
    if actual != FIXTURE_SHA256:
        raise RuntimeError(f"dev fixture sha256 {actual} != pinned {FIXTURE_SHA256}")
    df = pd.read_csv(FIXTURE)
    for col in _DATETIME_COLUMNS:
        df[col] = pd.to_datetime(df[col], utc=True)
    return df


def fixture_city(city: str) -> pd.DataFrame:
    """A fresh copy of one city's fixture rows, sorted by valid time."""
    df = _fixture_all()
    return df[df["city"] == city].sort_values("datetime_utc").reset_index(drop=True).copy()


def _cities() -> list:
    import config
    return list(config.LOCATIONS)


def stub_models(city: str) -> dict:
    """The validation suite's fit_stub_models recipe, verbatim (never a real frozen artifact)."""
    from sklearn.linear_model import LinearRegression

    import city_point
    import forecast_correction_models as fcm
    import forecast_experiment
    import forecast_shadow_confirm as conf
    import forecast_shadow_fit_models as fit_models
    import forecast_training

    frame = fixture_city(city)
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


# --------------------------------------------------------------------------
# Sections
# --------------------------------------------------------------------------

def _section_geometry() -> dict:
    import city_point
    import config

    out = {}
    for city in _cities():
        point = city_point.city_point(city)
        out[city] = {
            "conductor": {k: v for k, v in sorted(vars(point.conductor).items())},
            "bearing_deg": point.bearing_deg,
            "coord": point.coord,
            "static_rating": point.static_rating,
            "rating_bounds": point.rating_bounds,
            "conductor_kwargs_for_bearing": dict(sorted(config.conductor_kwargs_for(point.bearing_deg).items())),
        }
    return _jsonable(out)


def _window():
    import forecast_shadow_confirm as conf
    import forecast_shadow_eval_core as core
    return conf.ScoredWindow(core.to_utc(DEV_WINDOW[0]), core.to_utc(DEV_WINDOW[1]))


def _section_arms() -> dict:
    import city_point
    import forecast_shadow_confirm as conf

    out = {}
    for city in _cities():
        prepared, diag = conf.prepare_city_frame(fixture_city(city), city, window=_window())
        point = city_point.city_point(city)
        arms = conf._arms(point, {})
        raw, raw_failed = conf.predict_arm(arms["raw_forecast"], prepared)
        persist, persist_failed = conf.predict_arm(arms["persistence_24h"], prepared)
        out[city] = {
            "n_prepared": int(len(prepared)),
            "n_scored_slots": diag["n_scored_slots"],
            "truth_dlr_amps": array_digest(prepared["truth_dlr_amps"].to_numpy(dtype=float)),
            "raw_forecast": array_digest(raw),
            "raw_forecast_failed": int(raw_failed.sum()),
            "persistence_24h": array_digest(persist),
            "persistence_24h_failed": int(persist_failed.sum()),
        }
    return _jsonable(out)


def _section_fits() -> dict:
    import city_point
    import forecast_experiment
    import forecast_shadow_confirm as conf
    import forecast_shadow_fit_models as fit_models
    import forecast_training

    out = {}
    for city in _cities():
        shifted = fixture_city(city)
        for col in _DATETIME_COLUMNS:
            shifted[col] = shifted[col] - pd.Timedelta(days=FIT_SHIFT_DAYS)
        fit = fit_models.fit_from_frame(city, shifted)
        models = fit["models"]
        point = city_point.city_point(city)

        frame = fit_models.restrict_to_train_val(shifted).sort_values("datetime_utc").reset_index(drop=True)
        frame["truth_dlr_amps"] = fit_models.weather_to_arm5_frame(frame, city, prefix="truth_")["dlr_amps"].to_numpy()
        frame["city"] = city
        exact = forecast_experiment._add_correction_columns(forecast_experiment.filter_to_exact_lead(frame, lead_hours=24), point)
        wind_amps = forecast_experiment._wind_corrected_ampacity(models[conf.WIND], exact, point)
        cooling_amps = forecast_experiment._cooling_corrected_ampacity(models[conf.COOLING], exact, point)
        X, _ = forecast_training.build_training_matrix(
            fit_models.weather_to_arm5_frame(shifted, city, prefix="truth_"), horizon_minutes=1440)
        ref_pred = models[conf.REFERENCE].predict(X.to_numpy(dtype=float))
        out[city] = {
            "n_rows_fit": dict(sorted(fit["n_rows_fit"].items())),
            "n_exact_rows": int(len(exact)),
            "wind_corrected_ampacity": array_digest(wind_amps),
            "cooling_corrected_ampacity": array_digest(cooling_amps),
            "reference_predictions": array_digest(ref_pred),
        }
    return _jsonable(out)


def _section_collector() -> dict:
    import forecast_experiment
    import forecast_shadow_confirm as conf
    import forecast_shadow_pipeline as pipeline

    window = _window()
    out = {}
    for city in _cities():
        models = stub_models(city)
        frame = fixture_city(city)
        exact = forecast_experiment.filter_to_exact_lead(frame, lead_hours=24)
        inside = exact[(exact["datetime_utc"] >= window.start) & (exact["datetime_utc"] < window.end)]
        rows = []
        for _, row in inside.head(COLLECTOR_ROWS).iterrows():
            validated = pipeline.validate_and_prepare_shadow_row(row, city=city)
            geometry = validated.attrs["geometry"]
            # The collector's own pure enrichment (perpendicular-wind columns) from the row's anchor values.
            anchor = pd.Series({
                "anchor_wind_speed": row["anchor_wind_speed"], "anchor_wind_direction": row["anchor_wind_direction"],
                "anchor_air_temp": row["anchor_air_temp"], "anchor_observation_time": row["anchor_datetime_utc"],
                "anchor_source": "fixture", "anchor_station": "fixture"})
            prepared = pipeline._enrich_city_frame_for_correction(
                validated, anchor=anchor, city=city, valid_time=row["datetime_utc"], geometry=geometry)
            rows.append({
                "valid_time": row["datetime_utc"].isoformat(),
                "raw_forecast": repr(float(pipeline.RawForecastShadowMethod().predict(prepared, geometry))),
                "ml_wind_corrected": repr(float(pipeline.WindCorrectionShadowMethod(models[conf.WIND]).predict(prepared, geometry))),
                "ml_cooling_corrected": repr(float(pipeline.CoolingCorrectionShadowMethod(models[conf.COOLING]).predict(prepared, geometry))),
            })
        out[city] = rows
    return _jsonable(out)


def _section_family() -> dict:
    import forecast_shadow_confirm as conf
    import forecast_shadow_eval_core as core

    cities = _cities()
    models = {city: stub_models(city) for city in cities}

    def provider(city, *, evidence_dir):
        frame = fixture_city(city)
        weather = frame[["datetime_utc"] + [f"truth_{c}" for c in ("air_temp", "wind_speed", "wind_direction",
                                                                      "solar_radiation", "relative_humidity")]].copy()
        weather.columns = ["datetime_utc", "air_temp", "wind_speed", "wind_direction", "solar_radiation", "relative_humidity"]
        return frame, weather, {"city": city, "provider": "fixture"}

    with tempfile.TemporaryDirectory() as tmp:
        report = conf.run_confirmation(
            cities=cities, guard_cfg=core.GuardConfig(), evidence_root=os.path.join(tmp, "evidence"),
            now=DEV_NOW, params={"n_resamples": N_RESAMPLES}, window=DEV_WINDOW,
            frame_provider=provider, model_loader=lambda city, method: models[city][method],
            repo_root=REPO_ROOT)
    comparisons = []
    for c in report["family"]["comparisons"]:
        head = c["headline"]
        comparisons.append({
            "a": c["a"], "b": c["b"], "n_paired": c["n_paired"], "point_margin": c["point_margin"],
            "mae_a": c["mae_a"], "mae_b": c["mae_b"], "per_city_margins": c["per_city_margins"],
            "p_headline": head["p_headline"], "p_holm_adjusted": head["p_holm_adjusted"],
        })
    per_city = {city: report["per_city"][city]["metrics"] for city in cities}
    return _jsonable({"comparisons": comparisons, "per_city_metrics": per_city})


def _section_artifacts() -> dict:
    out = {}
    with open(ARTIFACT_MANIFEST, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            _, rel = line.split(None, 1)
            out[rel.strip()] = sha256_path(os.path.join(REPO_ROOT, rel.strip()))
    return out


_SECTION_FUNCS = {
    "geometry": _section_geometry, "arms": _section_arms, "fits": _section_fits,
    "collector": _section_collector, "family": _section_family, "artifacts": _section_artifacts,
}


def compute_section(name: str) -> dict:
    """One payload section on whatever backend modules the interpreter's sys.path supplies."""
    return json.loads(json.dumps(_SECTION_FUNCS[name](), sort_keys=True))


def compute_payload() -> dict:
    return {name: compute_section(name) for name in SECTIONS}


# --------------------------------------------------------------------------
# Capture (parent) and emit (child)
# --------------------------------------------------------------------------

def _git(*args: str, text: bool = True):
    return subprocess.run(["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=text).stdout


def _artifact_hashes_at(commit: str) -> dict:
    """sha256 of every manifest-listed artifact as committed at `commit` (independent of the working tree)."""
    manifest = _git("show", f"{commit}:data/shadow/models/ARTIFACT_HASHES.sha256")
    out = {}
    for line in manifest.splitlines():
        line = line.strip()
        if line:
            _, rel = line.split(None, 1)
            out[rel.strip()] = sha256_bytes(_git("show", f"{commit}:{rel.strip()}", text=False))
    return out


def capture(commit: str, out_path: str) -> dict:
    full = _git("rev-parse", f"{commit}^{{commit}}").strip()
    head = _git("rev-parse", "HEAD").strip()
    archive = _git("archive", full, "backend", text=False)
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(tmp, filter="data")
        materialized = os.path.join(tmp, "backend")
        if sha256_path(FIXTURE) != FIXTURE_SHA256:
            raise RuntimeError("dev fixture sha256 does not match the pinned value")
        env = {
            "PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""),
            "PYTHONPATH": materialized, "PYTHONHASHSEED": "0", "MPLBACKEND": "Agg",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--emit-payload", "--materialized", materialized],
            cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            raise RuntimeError(f"child exited {proc.returncode}\n{proc.stderr[-4000:]}")
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    committed = _artifact_hashes_at(full)
    if payload["artifacts"] != committed:
        raise RuntimeError(f"artifact hashes on disk differ from the ones committed at {full}")
    record = {"source_commit": full, "captured_from_head": head, "fixture_sha256": FIXTURE_SHA256,
              "versions": versions(), "payload": payload}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, sort_keys=True, indent=1)
        fh.write("\n")
    return record


def _emit_payload(materialized: str) -> int:
    materialized = os.path.realpath(materialized)
    # Script-directory entry first, then ours: the materialized copy must win every import.
    sys.path[:] = [p for p in sys.path if os.path.realpath(p or ".") != os.path.realpath(_HERE)]
    sys.path.insert(0, materialized)
    import config
    if not os.path.realpath(config.__file__).startswith(materialized + os.sep):
        print(f"config.__file__ {config.__file__} is not inside the materialized copy {materialized}", file=sys.stderr)
        return 3
    import requests

    def no_network(*args, **kwargs):
        raise AssertionError("requests.get must not be called while capturing the golden")

    requests.get = no_network
    payload = compute_payload()
    live_backend = os.path.join(REPO_ROOT, "backend") + os.sep
    strays = sorted(
        name for name, mod in list(sys.modules.items())
        if getattr(mod, "__file__", None)
        and os.path.realpath(mod.__file__) != os.path.realpath(__file__)   # this script, as __main__ / __mp_main__
        and os.path.realpath(mod.__file__).startswith(live_backend))
    if strays:
        print(f"modules imported from the live tree instead of the copy: {strays}", file=sys.stderr)
        return 3
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0


def check(golden_path: str = GOLDEN_PATH) -> list:
    """Section names whose live-tree payload differs from the committed golden."""
    with open(golden_path, encoding="utf-8") as fh:
        golden = json.load(fh)
    live = compute_payload()
    return [name for name in SECTIONS if live[name] != golden["payload"][name]]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--capture", action="store_true", help="write the golden from a materialized commit")
    parser.add_argument("--commit", default=BASELINE_COMMIT)
    parser.add_argument("--out", default=GOLDEN_PATH)
    parser.add_argument("--emit-payload", action="store_true", help="child mode: print the payload as one JSON line")
    parser.add_argument("--materialized", default=None, help="child mode: the materialized backend directory")
    parser.add_argument("--check", action="store_true", help="compare the live tree with the committed golden")
    args = parser.parse_args(argv)
    if args.emit_payload:
        if not args.materialized:
            parser.error("--emit-payload needs --materialized")
        return _emit_payload(args.materialized)
    if args.capture:
        record = capture(args.commit, args.out)
        print(f"wrote {args.out} from {record['source_commit']}")
        return 0
    if args.check:
        differing = check()
        if differing:
            print("differing sections: " + ", ".join(differing))
            return 1
        print("golden matches: " + ", ".join(SECTIONS))
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
