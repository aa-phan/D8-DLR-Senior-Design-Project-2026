"""
Rating identity (production-pipeline Phase 4: DB-06)
==================================================
The recipe that names, per city, every assumption a rating depends on: the snapshot
schema, the fingerprinted and unfingerprinted config names, the modules on the rating
path, the source files the backfill materializes, the canonicalization and the
fingerprint itself. `supabase_store` re-exports every name here, so
`supabase_store.rating_config_fingerprint` is this function.

This module deliberately imports only the standard library, `config` and `city_point`.
The backfill loader (`supabase_load_backfill.phase3_config_fingerprints`) evaluates it
in an isolated child process against the Phase 3 copies of `config`, `city_point` and
`thermal_model` (materialized from the manifest's git head) and refuses to answer if any
other live backend module was imported. A live module that reads a config name the older
config lacks, at import time, therefore cannot break the backfill identity re-run.
Keep it that way: a new import here must be one the Phase 3 sources also provide.
"""

import hashlib
import json

import city_point
import config

# Chosen mechanism: an automatic per-city fingerprint next to the human label. No
# hand-bumped value is the identity.
#
# A conductor type change (Phase 7, COND-01) shows as changed ConductorConfig
# attributes; a new per-city conductor table in config is caught by the AST guard
# test and goes into FINGERPRINTED_CONFIG_NAMES. Changing the snapshot recipe also
# changes every fingerprint, so bump RATING_CONFIG_SNAPSHOT_SCHEMA when doing it.

RATING_CONFIG_SNAPSHOT_SCHEMA = 1

# The modules the snapshot reads (plan 04-03 materializes them from Phase 3's commit).
RATING_CONFIG_SOURCE_FILES = ("backend/config.py", "backend/city_point.py", "backend/thermal_model.py")

# Modules on the rating path; the drift guard test reads every `config.<NAME>` in them.
RATING_PATH_MODULES = (
    "city_point",
    "thermal_model",
    "city_rating",
    "DLRSafetyMonitor",
    "ampacity_forecast",
    "anomaly_detector",
    "data_cleaning",
    "city_pipeline",
    "ercot_dlr_merger",
    "wind_vector",
)

FINGERPRINTED_CONFIG_NAMES = (
    "STATIC_RATINGS",
    "RATING_BOUNDS_BY_LOCATION",
    "CITY_LINE_BEARING_DEG",
    "CITY_COORDINATES",
    "SUBCONDUCTORS_PER_PHASE",
    "DEFAULT_CONDUCTOR_CONFIG_KWARGS",
    "LINE_VOLTAGE_KV",
    "POWER_FACTOR",
    "ANOMALY_CONTROL_LIMIT_K_BY_LOCATION",
    "DEFAULT_ANOMALY_CONTROL_LIMIT_K",
    "ANOMALY_ML_FEATURE_COLUMNS",
    "ANOMALY_ML_RAW_DATA_KEYS",
    "FORECAST_HORIZON_MINUTES",
    "FORECAST_MIN_HISTORY_ROWS",
    "FORECAST_BACKTEST_QUANTILES",
    "FORECAST_EWM_HALFLIFE_MIN",
    "FORECAST_ML_FEATURE_WEATHER_COLUMNS",
    "FORECAST_ML_LAG_HOURS",
    "FORECAST_ML_ROLLING_WINDOW_HOURS",
)

# Config names the rating path reads that are deliberately not in the fingerprint,
# each with the reason.
UNFINGERPRINTED_CONFIG_NAMES = {
    "LOCATIONS": "the city set; city is a key column of the row",
    "conductor_kwargs_for": "a function; its result is fingerprinted as the city's ConductorConfig attributes",
    "DEFAULT_RATING_BOUNDS": "fallback for a monitor built without a city; the per-city path passes the city's bounds",
    "DELTA_FRACTION": "G5 is off on the per-city path: city_rating passes delta_fraction=inf",
    "DEFAULT_STATIC_RATING": "fallback for a location outside STATIC_RATINGS; the four cities all have an entry",
    "FORECAST_ML_MODEL_DIR": "artifact location; the artifact is identified by forecast_model_sha256",
    "FORECAST_ML_MODEL_FILENAME_TEMPLATE": "artifact location; the artifact is identified by forecast_model_sha256",
    "ANOMALY_ML_MODEL_DIR": "artifact location; the artifact is identified by anomaly_model_sha256",
    "ANOMALY_ML_MODEL_FILENAME_TEMPLATE": "artifact location; the artifact is identified by anomaly_model_sha256",
}


def _canon(value):
    """A deterministic JSON-ready form of a config value."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if hasattr(value, "item") and not isinstance(value, (int, float)):
        return _canon(value.item())
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, dict):
        return {str(k): _canon(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canon(v) for v in value]
    raise TypeError(f"cannot fingerprint a config value of type {type(value).__name__}")


def _per_city(value, city):
    """
    A dict any of whose keys is a project city becomes that city's entry, so a
    change for one city touches only that city's fingerprint. Any other dict is
    canonicalized whole; sequences and numpy scalars become plain JSON values.
    """
    if isinstance(value, dict) and any(k in config.LOCATIONS for k in value):
        return _canon(value.get(city))
    return _canon(value)


def rating_config_snapshot(city: str) -> dict:
    """
    Every assumption the rating of `city` depends on, as a JSON-ready dict:
    all attributes of the city's ConductorConfig, its point, static rating,
    bounds and bearing, and each fingerprinted config constant reduced to the
    city's entry.
    """
    point = city_point.city_point(city)
    return {
        "snapshot_schema": RATING_CONFIG_SNAPSHOT_SCHEMA,
        "city": city,
        "conductor": {
            name: _per_city(attr, city) for name, attr in sorted(vars(point.conductor).items())
        },
        "point": {
            "coordinate": list(point.coord),
            "line_bearing_deg": point.bearing_deg,
            "static_rating_amps": point.static_rating,
            "rating_bounds_amps": list(point.rating_bounds),
        },
        "config": {
            name: _per_city(getattr(config, name, None), city)
            for name in FINGERPRINTED_CONFIG_NAMES
        },
    }


def rating_config_fingerprint(city: str) -> str:
    """Lowercase hex sha256 of the canonical JSON of `rating_config_snapshot(city)`."""
    canonical = json.dumps(
        rating_config_snapshot(city), sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
