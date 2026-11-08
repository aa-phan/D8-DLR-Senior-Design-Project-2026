"""
The day-ahead uncertainty band (production-pipeline Phase 8, DAY-03, D-05, D-06, D-07).

Every day-ahead value carries a 5-95% empirical residual-quantile band, one band per city and
per 00/06/12/18 UTC target hour (16 bands). At launch each band comes from the TEST-split residuals
of `ml_cooling_corrected` (valid times from 2026-03-18 up to, not including, the evaluation cut-off
of 2026-09-30, production conductor basis). The residuals are computed once, offline, and saved as
a hashed JSON artifact: `data/day_ahead/day_ahead_bands_v1.json`. The live runner verifies the
artifact's sha256 against the live manifest before it parses a byte, exactly as the model files are
verified before they are unpickled. JSON is not a pickle, so nothing runs on load.

Residual and sign: `truth_amps - ml_cooling_corrected`, in amperes. The artifact stores OFFSETS,
`np.quantile(residual, 0.05)` and `np.quantile(residual, 0.95)`, so a band is `point + offset`,
the same convention as the 60-minute band in `ampacity_forecast.forecast_ampacity`. The band is an
empirical quantile band, never mean plus or minus k sigma (house rule, D-07). A band that excludes
its own centre is clamped to the point with a logged warning, the same guard that function uses.

Anti-peeking (protocol): the builder reads ONLY the tracked TEST rows CSV of the horizon-comparison
report and refuses any row outside the TEST window. It never opens the shadow prediction logs, the
shadow-log reader, or any cache dated after the TEST window ends.

This task implements the TEST-split branch of `band_for`. Plan 08-03 adds the live-rolling branch
behind the same signature.

CLI (run from the repository root, PYTHONPATH=backend):
    python backend/day_ahead_band.py --build    # write the artifact
    python backend/day_ahead_band.py --check    # exit 0 only if a fresh build equals the committed bytes
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

import config
import day_ahead_contract as contract
import dlr_live_check_models

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

BAND_ARTIFACT_PATH = os.path.join("data", "day_ahead", "day_ahead_bands_v1.json")
ROWS_CSV = os.path.join(
    "docs", "data-science", "exploratory", "2026-11-02_horizon_comparison", "rows_production.csv"
)
TEST_START = pd.Timestamp("2026-03-18T00:00:00Z")
TEST_END_EXCLUSIVE = pd.Timestamp("2026-09-30T00:00:00Z")
ARTIFACT_SCHEMA = 1

_ROW_COLUMNS = ("city", "valid_time", "truth_amps", contract.FORECAST_METHOD)


class BandArtifactError(RuntimeError):
    """The band artifact is missing, unlisted, differs from its manifest hash, or is not a valid artifact."""


@dataclass(frozen=True)
class BandChoice:
    """One band as applied to one point forecast, with where it came from (D-05)."""

    lower_amps: float
    upper_amps: float
    source: str
    n: int
    pairs_through: object
    artifact_sha256: str


def _resolve(path: str) -> str:
    """A repo-relative path resolves from the repository root, so the result never depends on the cwd."""
    return path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)


def _key(path: str) -> str:
    """Manifest paths use forward slashes whatever the platform."""
    return path.replace(os.sep, "/")


# --------------------------------------------------------------------------------------------------
# Building the artifact (offline)
# --------------------------------------------------------------------------------------------------

def build_band_artifact(rows_csv: str = ROWS_CSV) -> dict:
    """
    The band artifact as a dict, built from the tracked TEST rows CSV only. Raises ValueError for a
    missing column or value, a valid_time before TEST_START or at or after TEST_END_EXCLUSIVE, a city
    outside config.LOCATIONS or a target hour off the 00/06/12/18 grid, and a group with no rows.
    """
    path = _resolve(rows_csv)
    frame = pd.read_csv(path)
    missing_columns = [c for c in _ROW_COLUMNS if c not in frame.columns]
    if missing_columns:
        raise ValueError(f"{rows_csv}: missing column(s) {missing_columns}")
    frame = frame[list(_ROW_COLUMNS)].copy()
    if frame.isnull().any().any():
        raise ValueError(f"{rows_csv}: a row has a missing value in {list(_ROW_COLUMNS)}")
    frame["valid_time"] = pd.to_datetime(frame["valid_time"], utc=True)
    truth = frame["truth_amps"].to_numpy(dtype=float)
    predicted = frame[contract.FORECAST_METHOD].to_numpy(dtype=float)
    if not (np.isfinite(truth).all() and np.isfinite(predicted).all()):
        raise ValueError(f"{rows_csv}: a truth or prediction value is not finite")
    if frame.empty:
        raise ValueError(f"{rows_csv}: no rows")
    earliest, latest = frame["valid_time"].min(), frame["valid_time"].max()
    if earliest < TEST_START:
        raise ValueError(f"{rows_csv}: valid_time {earliest} is before the TEST window start {TEST_START}")
    if latest >= TEST_END_EXCLUSIVE:
        raise ValueError(f"{rows_csv}: valid_time {latest} is at or after the TEST window end {TEST_END_EXCLUSIVE}")
    unknown = sorted(set(frame["city"]) - set(config.LOCATIONS))
    if unknown:
        raise ValueError(f"{rows_csv}: unknown city value(s) {unknown}")
    frame["hour"] = frame["valid_time"].dt.hour
    off_grid = sorted(set(frame["hour"]) - set(contract.TARGET_HOURS_UTC))
    if off_grid:
        raise ValueError(f"{rows_csv}: valid_time hour(s) {off_grid} are not on the 00/06/12/18 UTC grid")
    frame["residual"] = truth - predicted  # truth - forecast, amperes

    q_lo, q_hi = config.FORECAST_BACKTEST_QUANTILES
    bands: dict = {}
    for city in config.LOCATIONS:
        bands[city] = {}
        for hour in contract.TARGET_HOURS_UTC:
            residuals = frame.loc[(frame["city"] == city) & (frame["hour"] == hour), "residual"].to_numpy(dtype=float)
            if residuals.size == 0:
                raise ValueError(f"{rows_csv}: no rows for {city} at {hour:02d} UTC")
            bands[city][str(hour)] = {
                "n": int(residuals.size),
                "lower_offset_amps": float(np.quantile(residuals, q_lo)),
                "upper_offset_amps": float(np.quantile(residuals, q_hi)),
            }
    return {
        "schema": ARTIFACT_SCHEMA,
        "method": contract.FORECAST_METHOD,
        "quantiles": [q_lo, q_hi],
        "residual": "truth_amps - ml_cooling_corrected, amperes",
        "conductor_basis": "production: city_point.production_city_point",
        "rows_file": _key(rows_csv),
        "rows_sha256": dlr_live_check_models.sha256_file(path),
        "valid_time_min": earliest.isoformat(),
        "valid_time_max": latest.isoformat(),
        "bands": bands,
    }


def artifact_bytes(obj: dict) -> bytes:
    """The deterministic serialisation: sorted keys, two-space indent, one trailing newline."""
    return (json.dumps(obj, sort_keys=True, indent=2) + "\n").encode("utf-8")


# --------------------------------------------------------------------------------------------------
# Loading the artifact (runner)
# --------------------------------------------------------------------------------------------------

def parse_band_artifact(data: bytes) -> dict:
    """The artifact dict from its bytes. JSON only, never a pickle. Raises BandArtifactError."""
    try:
        artifact = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise BandArtifactError(f"band artifact is not valid JSON: {type(exc).__name__}") from exc
    if not isinstance(artifact, dict):
        raise BandArtifactError("band artifact is not a JSON object")
    if artifact.get("schema") != ARTIFACT_SCHEMA:
        raise BandArtifactError(f"band artifact schema {artifact.get('schema')!r} is not {ARTIFACT_SCHEMA}")
    if artifact.get("method") != contract.FORECAST_METHOD:
        raise BandArtifactError(
            f"band artifact method {artifact.get('method')!r} is not {contract.FORECAST_METHOD!r}"
        )
    if artifact.get("quantiles") != list(config.FORECAST_BACKTEST_QUANTILES):
        raise BandArtifactError(
            f"band artifact quantiles {artifact.get('quantiles')!r} are not {list(config.FORECAST_BACKTEST_QUANTILES)}"
        )
    bands = artifact.get("bands")
    if not isinstance(bands, dict):
        raise BandArtifactError("band artifact has no 'bands' object")
    for city in config.LOCATIONS:
        if not isinstance(bands.get(city), dict):
            raise BandArtifactError(f"band artifact has no bands for city {city}")
        for hour in contract.TARGET_HOURS_UTC:
            _check_band(city, hour, bands[city].get(str(hour)))
    return artifact


def _check_band(city: str, hour: int, band) -> None:
    """One band must hold an integer n > 0 and finite offsets with lower <= upper, or BandArtifactError."""
    where = f"band artifact band {city} at {hour:02d} UTC"
    if not isinstance(band, dict):
        raise BandArtifactError(f"{where} is missing or not an object (key {str(hour)!r})")
    n = band.get("n")
    if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
        raise BandArtifactError(f"{where}: field n {n!r} is not a positive integer")
    offsets = {}
    for field in ("lower_offset_amps", "upper_offset_amps"):
        value = band.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
            raise BandArtifactError(f"{where}: field {field} {value!r} is not a finite number")
        offsets[field] = float(value)
    if offsets["lower_offset_amps"] > offsets["upper_offset_amps"]:
        raise BandArtifactError(
            f"{where}: field lower_offset_amps {offsets['lower_offset_amps']} is above upper_offset_amps "
            f"{offsets['upper_offset_amps']}"
        )


def load_verified_band(path: str = BAND_ARTIFACT_PATH,
                       manifest_path: str = dlr_live_check_models.MANIFEST_PATH) -> tuple[dict, str]:
    """
    (artifact, sha256). The bytes are read once, hashed, compared with the manifest entry for the
    forward-slash `path`, and only then parsed: the same bytes that were hashed. Raises
    BandArtifactError, before any parsing, for a missing file, manifest or entry, or a mismatch.
    """
    try:
        entries = dlr_live_check_models.read_manifest(_resolve(manifest_path))
    except OSError as exc:
        raise BandArtifactError(f"manifest missing or unreadable: {manifest_path}: {type(exc).__name__}") from exc
    except ValueError as exc:
        raise BandArtifactError(f"manifest malformed: {manifest_path}: {exc}") from exc
    expected = entries.get(_key(path))
    if expected is None:
        raise BandArtifactError(f"band artifact {_key(path)} has no entry in the manifest {manifest_path}")
    try:
        with open(_resolve(path), "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise BandArtifactError(f"band artifact missing or unreadable: {path}: {type(exc).__name__}") from exc
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        raise BandArtifactError(
            f"hash mismatch: {_key(path)}: manifest {expected}, file {actual}; not parsing it"
        )
    return parse_band_artifact(data), actual


# --------------------------------------------------------------------------------------------------
# Applying a band
# --------------------------------------------------------------------------------------------------

def apply_band(point: float, lower_offset: float, upper_offset: float) -> tuple[float, float]:
    """
    `(point + lower_offset, point + upper_offset)`, the 60-minute band's convention. A band that
    excludes its own centre is a defect, not a valid result: both edges are clamped to the point and
    a warning is logged (the guard in `ampacity_forecast.forecast_ampacity`).
    """
    lower, upper = point + lower_offset, point + upper_offset
    if lower > point or upper < point:
        logger.warning(
            "apply_band: computed band [%.3f, %.3f] excluded its own center %.3f -- clamping both edges "
            "to the point forecast", lower, upper, point,
        )
        return point, point
    return lower, upper


def _utc_hour(valid_time) -> int:
    stamp = pd.Timestamp(valid_time)
    return int((stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")).hour)


def band_for(conn, city: str, valid_time, point_amps: float, artifact: dict, artifact_sha256: str, *,
             config_fingerprint: str, cooling_model_sha256: str, decision_time) -> BandChoice:
    """
    The band for one point forecast. This is the TEST-split branch: the offsets of
    artifact["bands"][city][str(UTC hour)], source "test-split", no live pairs. Plan 08-03 adds the
    live-rolling branch behind this signature, which is why the connection, the identity arguments
    and the decision time are already part of it.
    """
    try:
        offsets = artifact["bands"][city][str(_utc_hour(valid_time))]
        lower_offset = float(offsets["lower_offset_amps"])
        upper_offset = float(offsets["upper_offset_amps"])
        n = int(offsets["n"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BandArtifactError(
            f"band artifact has no usable band for {city} at {_utc_hour(valid_time):02d} UTC"
        ) from exc
    lower, upper = apply_band(float(point_amps), lower_offset, upper_offset)
    return BandChoice(
        lower_amps=lower, upper_amps=upper, source="test-split", n=n, pairs_through=None,
        artifact_sha256=artifact_sha256,
    )


# --------------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build or check the day-ahead TEST band artifact (DAY-03).")
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--build", action="store_true", help="write the artifact")
    which.add_argument("--check", action="store_true",
                       help="exit 0 only when a fresh build equals the committed bytes")
    args = parser.parse_args(argv)

    fresh = artifact_bytes(build_band_artifact())
    target = _resolve(BAND_ARTIFACT_PATH)
    if args.build:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(fresh)
        print(f"wrote {_key(BAND_ARTIFACT_PATH)} sha256 {hashlib.sha256(fresh).hexdigest()}")
        return 0
    try:
        with open(target, "rb") as fh:
            committed = fh.read()
    except OSError as exc:
        print(f"ERROR: cannot read {_key(BAND_ARTIFACT_PATH)}: {type(exc).__name__}", file=sys.stderr)
        return 1
    if committed != fresh:
        print(f"ERROR: {_key(BAND_ARTIFACT_PATH)} differs from a fresh build of the tracked TEST rows",
              file=sys.stderr)
        return 1
    print(f"{_key(BAND_ARTIFACT_PATH)} matches a fresh build")
    return 0


if __name__ == "__main__":
    sys.exit(main())
