"""
Conductor-explicit refit of the two conductor-dependent shadow candidates (SEL-02, D-10), plus the loaders that
verify a model file against its hash manifest before it is deserialized.

**Run by a human, offline -- never by the scheduled collector.** Command:
`PYTHONPATH=backend .venv/bin/python backend/forecast_conductor_refit.py --cities-from-production-diff
[--config-version V] [--root DIR]` (or `--cities CITY [CITY ...]`).

What it does. `ml_cooling_corrected` and `reference_ml_refit_24h` are fit for ONE city under an explicit
`CityPoint` (its bearing and its conductor), using the frozen recipe in `forecast_shadow_fit_models` with the
point passed in rather than hardcoded to `city_point.city_point`. `ml_wind_corrected` does not depend on the
conductor and is reused, never refit here (SEL-02). Every frame that reaches a fit goes through
`forecast_shadow_fit_models.restrict_to_train_val` and `assert_no_test_leak`, so no row with `datetime_utc` or
`anchor_datetime_utc` on or after 2026-03-17 is used.

Where artifacts go. Only `data/models/conductor_refit/<config_version>/<method>_<CITY>.joblib` with an
`ARTIFACT_HASHES.sha256` manifest beside them (sha256sum format, the format `dlr_live_check_models` reads).
Nothing is ever written under `data/shadow/models`: `refit_dir` refuses that directory (including through a
symlink) and this module never calls `forecast_shadow_pipeline.save_correction_model`. An existing artifact is
never overwritten; a new refit takes a new `config_version`.

Why hashes are checked before loading. A joblib file is a pickle and runs code when it is loaded. So
`load_refit_model` and the headline loader compare the file's sha256 with the manifest entry first and refuse
to deserialize on any mismatch, missing entry or missing manifest (`ArtifactIntegrityError`). For refit
artifacts the verified bytes are the bytes that get deserialized (no window between check and load). For the
frozen artifacts the existing path-based `forecast_shadow_pipeline.load_correction_model` is used, so a file
swapped between the check and the load is outside what this module can prevent; the manifests are tracked in
git beside the artifacts, which defends against an accidental change, not against someone who can edit both.

D-10. The production refit is conditional on the production conductor differing from the frozen Drake point.
While every city is at Drake parity the CLI refuses ("the frozen artifacts serve as its production models"), so
no duplicate refit is produced. `production_differs` is the test.

The headline loader. `make_headline_loader` returns `loader(city, method)` for the confirmation evaluator's
`model_loader` seam. It serves the refit artifact for `refit_cities x REFIT_METHODS` and the frozen artifact
for everything else, and records each artifact it served (city, method, path, sha256, source) in
`loader.served` so the FRESH report can list exactly what was scored (research pitfall 7).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

import city_point
import config
import dlr_live_check_models
import forecast_correction_models
import forecast_experiment
import forecast_shadow_fit_models
import forecast_shadow_pipeline
import thermal_model

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
REFIT_ROOT = os.path.join("data", "models", "conductor_refit")
REFIT_METHODS: tuple[str, ...] = ("ml_cooling_corrected", "reference_ml_refit_24h")
MANIFEST_NAME = "ARTIFACT_HASHES.sha256"
LEAD_HOURS = 24
FROZEN_MANIFEST = os.path.join(REPO_ROOT, "data", "shadow", "models", MANIFEST_NAME)

_VERSION = re.compile(r"[A-Za-z0-9._-]+")
_PARITY_MESSAGE = (
    "production config equals the frozen Drake configuration for {city}; "
    "the frozen artifacts serve as its production models (D-10)"
)


class ArtifactIntegrityError(RuntimeError):
    """A model file is missing, unlisted, or its sha256 differs from its manifest entry; it was not loaded."""


# --------------------------------------------------------------------------
# Paths and manifests
# --------------------------------------------------------------------------

def _manifest_key(path: str) -> str:
    """Manifest key for `path`: repo-relative with forward slashes, or the absolute path outside the repo."""
    absolute = os.path.abspath(path)
    relative = os.path.relpath(absolute, REPO_ROOT)
    key = absolute if relative == os.pardir or relative.startswith(os.pardir + os.sep) else relative
    return key.replace(os.sep, "/")


def _is_inside(path: str, directory: str) -> bool:
    real, base = os.path.realpath(path), os.path.realpath(directory)
    return real == base or real.startswith(base + os.sep)


def refit_dir(config_version: str, root: str = REFIT_ROOT) -> str:
    """
    `<root>/<config_version>` (not created). Raises ValueError for a version that is empty, holds a path
    separator or '..', or has characters outside [A-Za-z0-9._-], and for any directory that is or lies inside
    `forecast_shadow_pipeline.SHADOW_MODEL_DIR` (the frozen artifacts), including through a symlink.
    """
    if (not isinstance(config_version, str) or not _VERSION.fullmatch(config_version)
            or config_version in (".", "..") or ".." in config_version):
        raise ValueError(
            f"config_version {config_version!r} is not a safe directory name (letters, digits, '.', '_', '-'; "
            f"no path separators and no '..')"
        )
    directory = os.path.join(root, config_version)
    if _is_inside(directory, forecast_shadow_pipeline.SHADOW_MODEL_DIR):
        raise ValueError(
            f"refit directory {directory!r} is the frozen directory data/shadow/models (SHADOW_MODEL_DIR) or lies "
            f"inside it; refits go only under {REFIT_ROOT} (SEL-02)"
        )
    return directory


def _artifact_path(directory: str, city: str, method: str) -> str:
    return os.path.join(directory, f"{method}_{city}.joblib")


def _require_city(city: str) -> None:
    if city not in config.LOCATIONS:
        raise KeyError(f"Unknown city {city!r}. Valid cities: {sorted(config.LOCATIONS)}")


def write_manifest(directory: str) -> str:
    """
    (Re)write `<directory>/ARTIFACT_HASHES.sha256`: one `<sha256>  <path>` line per `*.joblib` in the directory,
    sorted by path, forward slashes, under a `#` header naming the config version and the UTC time. Returns the
    manifest path. Never deserializes an artifact.
    """
    keyed = sorted(
        (_manifest_key(os.path.join(directory, name)), os.path.join(directory, name))
        for name in os.listdir(directory) if name.endswith(".joblib")
    )
    header = (
        f"# {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')} SHA-256 of the Phase 7 conductor refit "
        f"artifacts for config version {os.path.basename(os.path.normpath(directory))} (written by "
        f"forecast_conductor_refit; every load checks this manifest first)"
    )
    lines = [header] + [f"{dlr_live_check_models.sha256_file(path)}  {key}" for key, path in keyed]
    manifest = os.path.join(directory, MANIFEST_NAME)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".manifest-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, manifest)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return manifest


def _entries(manifest_path: str) -> dict:
    try:
        return dlr_live_check_models.read_manifest(manifest_path)
    except OSError as exc:
        raise ArtifactIntegrityError(
            f"manifest missing or unreadable: {manifest_path}: {type(exc).__name__}: {exc}"
        ) from exc
    except ValueError as exc:
        raise ArtifactIntegrityError(f"manifest malformed: {manifest_path}: {exc}") from exc


def _expected_hash(path: str, manifest_path: str) -> str:
    entries = _entries(manifest_path)
    key = _manifest_key(path)
    expected = entries.get(key)
    if expected is None:
        raise ArtifactIntegrityError(f"manifest {manifest_path} has no entry for {key}")
    return expected


# --------------------------------------------------------------------------
# Point-explicit frames and fits
# --------------------------------------------------------------------------

def arm5_frame_for_point(truth: pd.DataFrame, point, prefix: str = "") -> pd.DataFrame:
    """
    `forecast_shadow_fit_models.weather_to_arm5_frame`'s columns and maths, but with the given point's bearing
    and conductor instead of `city_point.city_point(city)`: `datetime_utc`, `dlr_amps`, `air_temp`,
    `wind_speed`, `solar_radiation`. `prefix` is "truth_" for anchored-pair-frame columns.
    """
    truth = truth.sort_values("datetime_utc").reset_index(drop=True)
    air = truth[f"{prefix}air_temp"].to_numpy(dtype=float)
    wind = truth[f"{prefix}wind_speed"].to_numpy(dtype=float)
    solar = truth[f"{prefix}solar_radiation"].to_numpy(dtype=float)
    perp = thermal_model.perpendicular_wind(
        wind, truth[f"{prefix}wind_direction"].to_numpy(dtype=float), point.bearing_deg,
    )
    dlr_amps = np.asarray(thermal_model.ieee738_ampacity(air, perp, solar, point.conductor), dtype=float)
    return pd.DataFrame({
        "datetime_utc": truth["datetime_utc"], "dlr_amps": dlr_amps,
        "air_temp": air, "wind_speed": wind, "solar_radiation": solar,
    })


def prepare_fit_frame(frame: pd.DataFrame, point, city: str, fit_end=None):
    """
    The frame and its exact-24h-lead subset, ready to fit or score under `point`. Rows on or after the frozen
    test split are removed (`restrict_to_train_val`), then rows after `fit_end` when given; the leak assertion
    runs on both frames. `truth_dlr_amps` is recomputed under `point`. Returns (frame, exact).
    """
    frame = forecast_shadow_fit_models.restrict_to_train_val(frame)
    for column in ("datetime_utc", "anchor_datetime_utc"):
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], utc=True)
    if fit_end is not None:
        frame = frame[frame["datetime_utc"] <= pd.Timestamp(fit_end)].reset_index(drop=True)
    forecast_shadow_fit_models.assert_no_test_leak(frame)

    frame = frame.sort_values("datetime_utc").reset_index(drop=True)
    frame["truth_dlr_amps"] = arm5_frame_for_point(frame, point, prefix="truth_")["dlr_amps"].to_numpy()
    frame["city"] = city

    exact = forecast_experiment.filter_to_exact_lead(frame, lead_hours=LEAD_HOURS)
    exact = forecast_experiment._add_correction_columns(exact, point)
    forecast_shadow_fit_models.assert_no_test_leak(exact)
    return frame, exact


def fit_for_point(city: str, frame: pd.DataFrame, point, methods=REFIT_METHODS, fit_end=None) -> dict:
    """
    Fit `methods` (a subset of `forecast_shadow_fit_models.FIT_METHODS`) for `city` under `point`, network-free
    and without writing anything. Returns `{"models": {method: model}, "n_rows_fit": {method: int}}`.
    """
    _require_city(city)
    methods = tuple(methods)
    unknown = [m for m in methods if m not in forecast_shadow_fit_models.FIT_METHODS]
    if unknown:
        raise ValueError(
            f"fit_for_point: unknown method(s) {unknown}; allowed {list(forecast_shadow_fit_models.FIT_METHODS)}"
        )
    frame, exact = prepare_fit_frame(frame, point, city, fit_end=fit_end)

    models: dict = {}
    n_rows: dict = {}
    if forecast_shadow_fit_models.WIND_METHOD in methods:
        wind = forecast_correction_models.fit_wind_correction(
            exact,
            forecast_correction_models.WIND_CORRECTION_ESTIMATORS[
                forecast_shadow_fit_models.WIND_CONFIGURATION["estimator"]],
            pooling=forecast_shadow_fit_models.WIND_CONFIGURATION["pooling"],
        )
        models[forecast_shadow_fit_models.WIND_METHOD] = wind
        n_rows[forecast_shadow_fit_models.WIND_METHOD] = int(wind.n_rows_fit)
    if forecast_shadow_fit_models.COOLING_METHOD in methods:
        cooling_cfg = forecast_shadow_fit_models.COOLING_CONFIGURATION
        cooling = forecast_correction_models.fit_cooling_correction(
            exact,
            forecast_correction_models.COOLING_CORRECTION_ESTIMATORS[cooling_cfg["estimator"]],
            target=cooling_cfg["target"], conductor=point.conductor,
        )
        models[forecast_shadow_fit_models.COOLING_METHOD] = cooling
        n_rows[forecast_shadow_fit_models.COOLING_METHOD] = int(cooling.n_rows_fit)
    if forecast_shadow_fit_models.REFERENCE_METHOD in methods:
        arm5 = arm5_frame_for_point(frame, point, prefix="truth_")
        forecast_shadow_fit_models.assert_no_test_leak(arm5)
        reference, n_ref = forecast_shadow_fit_models.fit_reference_estimator(arm5)
        models[forecast_shadow_fit_models.REFERENCE_METHOD] = reference
        n_rows[forecast_shadow_fit_models.REFERENCE_METHOD] = int(n_ref)
    return {"models": models, "n_rows_fit": n_rows}


# --------------------------------------------------------------------------
# Write and verified load
# --------------------------------------------------------------------------

def write_refit(city: str, models: dict, config_version: str, root: str = REFIT_ROOT) -> dict:
    """
    Persist `models` (keys only from REFIT_METHODS) as `<root>/<config_version>/<method>_<CITY>.joblib` and
    regenerate the manifest. All-or-nothing per call: nothing is written if any target already exists. Returns
    `{method: path}`.
    """
    _require_city(city)
    if forecast_shadow_fit_models.WIND_METHOD in models:
        raise ValueError(f"{forecast_shadow_fit_models.WIND_METHOD} is reused, never refit (SEL-02)")
    unknown = [m for m in models if m not in REFIT_METHODS]
    if unknown:
        raise ValueError(f"write_refit: unknown method(s) {unknown}; allowed {list(REFIT_METHODS)}")
    directory = refit_dir(config_version, root)
    targets = {method: _artifact_path(directory, city, method) for method in models}
    for path in targets.values():
        if os.path.lexists(path):
            raise FileExistsError(f"refusing to overwrite the existing refit artifact {path}")
    os.makedirs(directory, exist_ok=True)

    written: dict = {}
    reserved: list[str] = []
    try:
        for method, model in models.items():
            target = targets[method]
            # reserve the name exclusively (a racing writer gets FileExistsError), then swap the dump in
            os.close(os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            reserved.append(target)
            fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{method}_{city}-", suffix=".tmp")
            os.close(fd)
            try:
                joblib.dump(model, tmp)
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
            written[method] = target
    except BaseException:
        for path in reserved:
            if os.path.exists(path):
                os.remove(path)
        raise
    write_manifest(directory)
    return written


def load_refit_model(city: str, method: str, config_version: str, root: str = REFIT_ROOT):
    """
    Load one refit artifact after checking its sha256 against `<dir>/ARTIFACT_HASHES.sha256`. Raises
    ArtifactIntegrityError (and does not call joblib.load) for a missing file, manifest or entry, or a mismatch.
    """
    model, _ = _load_verified_refit(city, method, config_version, root)
    return model


def _load_verified_refit(city: str, method: str, config_version: str, root: str):
    _require_city(city)
    if method not in REFIT_METHODS:
        raise ValueError(f"load_refit_model: method {method!r} is not a refit method {list(REFIT_METHODS)}")
    directory = refit_dir(config_version, root)
    path = _artifact_path(directory, city, method)
    expected = _expected_hash(path, os.path.join(directory, MANIFEST_NAME))
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ArtifactIntegrityError(f"refit artifact missing or unreadable: {path}: {type(exc).__name__}: {exc}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise ArtifactIntegrityError(
            f"hash mismatch: {path}: manifest {expected}, file {actual}; not loading it"
        )
    return joblib.load(io.BytesIO(data)), {"path": path, "sha256": actual}


def make_headline_loader(config_version: str, refit_cities, root: str = REFIT_ROOT,
                         frozen_manifest: str = FROZEN_MANIFEST):
    """
    A `model_loader(city, method)` for the confirmation evaluator: the refit artifact for
    `refit_cities x REFIT_METHODS`, otherwise the frozen artifact (hash checked against `frozen_manifest`
    before `forecast_shadow_pipeline.load_correction_model`). `loader.served` lists every artifact served as
    dicts with city, method, path, sha256 and source ("refit" or "frozen"); a repeat is not listed twice.
    A frozen artifact that is absent raises FileNotFoundError (the evaluator reads that as unavailable).
    """
    refit_cities = frozenset(refit_cities)
    for city in sorted(refit_cities):
        _require_city(city)
    served: list[dict] = []

    def record(entry: dict) -> None:
        if entry not in served:
            served.append(entry)

    def loader(city: str, method: str):
        _require_city(city)
        if method not in forecast_shadow_fit_models.FIT_METHODS:
            raise ValueError(f"headline loader: unknown method {method!r}")
        if city in refit_cities and method in REFIT_METHODS:
            model, info = _load_verified_refit(city, method, config_version, root)
            record({"city": city, "method": method, "path": info["path"], "sha256": info["sha256"],
                    "source": "refit"})
            return model
        path = forecast_shadow_pipeline._model_path_for(city, method)
        if not os.path.exists(path):
            return forecast_shadow_pipeline.load_correction_model(city, method)  # raises FileNotFoundError
        expected = _expected_hash(path, frozen_manifest)
        actual = dlr_live_check_models.sha256_file(path)
        if actual != expected:
            raise ArtifactIntegrityError(
                f"hash mismatch: {path}: manifest {expected}, file {actual}; not loading it"
            )
        model = forecast_shadow_pipeline.load_correction_model(city, method)
        record({"city": city, "method": method, "path": path, "sha256": actual, "source": "frozen"})
        return model

    loader.served = served
    loader.frozen_manifest = frozen_manifest
    return loader


# --------------------------------------------------------------------------
# D-10 and the CLI
# --------------------------------------------------------------------------

def production_differs(city: str) -> bool:
    """True if the production point's bearing or any conductor value differs from the frozen Drake point."""
    production = city_point.production_city_point(city)
    frozen = city_point.city_point(city)
    return bool(production.bearing_deg != frozen.bearing_deg
                or vars(production.conductor) != vars(frozen.conductor))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Refit ml_cooling_corrected and reference_ml_refit_24h under each city's production "
                    "conductor into data/models/conductor_refit/<config-version>/ (SEL-02).")
    parser.add_argument("--config-version", default=config.RATING_CONFIG_VERSION)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--cities", nargs="+", choices=sorted(config.LOCATIONS), metavar="CITY",
                       help="explicit cities to refit")
    which.add_argument("--cities-from-production-diff", action="store_true",
                       help="every city whose production conductor differs from the frozen Drake point")
    parser.add_argument("--root", default=REFIT_ROOT)
    args = parser.parse_args(argv)

    cities = args.cities if args.cities else [c for c in config.LOCATIONS if production_differs(c)]
    if args.cities_from_production_diff and not cities:
        print("no city differs from the frozen Drake configuration; nothing to refit (D-10)")
        return 0

    parity = [c for c in cities if not production_differs(c)]
    if parity:
        for city in parity:
            print(_PARITY_MESSAGE.format(city=city), file=sys.stderr)
        return 2
    try:
        directory = refit_dir(args.config_version, args.root)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    existing = [_artifact_path(directory, c, m) for c in cities for m in REFIT_METHODS
                if os.path.lexists(_artifact_path(directory, c, m))]
    if existing:
        for path in existing:
            print(f"ERROR: refusing to overwrite the existing refit artifact {path}; use a new --config-version",
                  file=sys.stderr)
        return 2

    for city in cities:
        point = city_point.production_city_point(city)
        frame = forecast_shadow_fit_models.load_city_frame(city)  # cached frames only, never the network
        fitted = fit_for_point(city, frame, point)
        paths = write_refit(city, fitted["models"], args.config_version, args.root)
        for method in REFIT_METHODS:
            print(f"{city} {method} n_rows_fit={fitted['n_rows_fit'][method]} {paths[method]} "
                  f"{dlr_live_check_models.sha256_file(paths[method])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
