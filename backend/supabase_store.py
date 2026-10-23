"""
Supabase Postgres store (production-pipeline Phase 4: DB-01, DB-02, DB-04, DB-06)
==================================================
The Postgres store for the production path. It writes one `public.city_rating`
row per city and hour and reads a city's recent rows back as the same frame
the CSV archive returns. The writer connects through the Supabase session
pooler as the least-privilege role `dlr_writer` using one secret,
`SUPABASE_DB_URL`. The CSV archive (`historical_archive`) stays the offline
default for tests and backfill; nothing here changes it.

Conflict rule (OD-7): the upsert is `INSERT ... ON CONFLICT (city, valid_time)
DO UPDATE`, so a same-hour retry overwrites the row with the retry's values
while `first_written_at` never changes. This is deliberately different from the
CSV archive's first-write-wins rule, which only exists because an append-only
file cannot replace a row.

`valid_time` is the UTC hour of the run window end (hour-truncated), so an
hourly run at 14:07 and a retry at 14:12 are the same key.

What produced a row (DB-06): every row names its inputs through `config_version`
(the human-readable label), `config_fingerprint` (an automatic per-city sha256
of every rating assumption, computed from the live config on every write, never
bumped by hand) and the sha256 of the forecast and anomaly model files the run
loaded. A conductor, model or forecast-method change therefore alters the
values written, never the schema.

`psycopg` is imported only inside `connect()`, so importing this module never
needs a database driver. Nothing secret is ever printed or logged: the URL, its
host, the project reference and the password are redacted from every message
(`redact`), and only redacted text reaches an exception or a log record. The
success log names only the role the server reports (`select current_user`),
never the pooler user the client supplied, which carries the project reference.
"""

import hashlib
import json
import logging
import math
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

import pandas as pd

import ampacity_forecast
import city_point
import config
import historical_archive
from ercot_dlr_merger import amps_to_mw

log = logging.getLogger(__name__)

CITY_RATING_TABLE = "public.city_rating"
PIPELINE_RUN_TABLE = "public.pipeline_run"
CITY_RATING_SCHEMA_VERSION = 1
KEY_COLUMNS = ("city", "valid_time")

# The pipeline_run columns, in migration order. run_id is the primary key; the
# jsonb columns are bound as JSON text and cast in the statement.
PIPELINE_RUN_COLUMNS = (
    "run_id",
    "run_attempt",
    "started_at",
    "finished_at",
    "window_end",
    "provider",
    "forecast_method",
    "pipeline_version",
    "cities_ok",
    "cities_failed",
    "provider_errors",
    "sources",
)
PIPELINE_RUN_JSONB = ("cities_failed", "provider_errors", "sources")
PIPELINE_RUN_KEY = "run_id"
_RUN_ERROR_MAX_CHARS = 1000
# A city whose forecast ran (or cold-started) and whose anomaly model loaded is healthy.
_HEALTHY_FORECAST_STATUSES = ("ok", "cold_start")

# The city_rating columns the writer supplies, in migration order. first_written_at
# and computed_at are set by the database and are not part of the row.
CITY_RATING_COLUMNS = (
    "city",
    "valid_time",
    "observation_time",
    "rating_amps",
    "rating_mw",
    "static_rating_amps",
    "static_rating_mw",
    "line_voltage_kv",
    "power_factor",
    "status",
    "fallback",
    "fallback_gates",
    "alerts",
    "exhausted",
    "station_id",
    "candidates_probed",
    "probe_trail",
    "air_temp_c",
    "wind_perp_ms",
    "wind_speed_ms",
    "wind_direction_deg",
    "solar_radiation_wm2",
    "temp_source",
    "wind_source",
    "solar_source",
    "forecast_method",
    "forecast_status",
    "forecast_amps",
    "forecast_ci_lower_amps",
    "forecast_ci_upper_amps",
    "forecast_horizon_min",
    "forecast_n_observations",
    "forecast_used_by_g6",
    "detector_signal",
    "detector_model_loaded",
    "history_rows",
    "usable_history_rows",
    "rating_basis",
    "config_version",
    "config_fingerprint",
    "forecast_model_sha256",
    "anomaly_model_sha256",
    "origin",
    "run_id",
    "run_attempt",
    "pipeline_version",
    "schema_version",
)


def _build_upsert_sql() -> str:
    """
    Build the upsert once from fixed identifiers (never data). `first_written_at`
    is in neither the column list nor the SET list: it keeps the original insert
    time. `computed_at` is refreshed on every rewrite.
    """
    placeholders = [
        "%(probe_trail)s::jsonb" if column == "probe_trail" else f"%({column})s"
        for column in CITY_RATING_COLUMNS
    ]
    updates = [
        f"{column} = excluded.{column}"
        for column in CITY_RATING_COLUMNS
        if column not in KEY_COLUMNS
    ]
    return (
        f"insert into {CITY_RATING_TABLE} (\n  "
        + ", ".join(CITY_RATING_COLUMNS)
        + ")\nvalues (\n  "
        + ", ".join(placeholders)
        + ")\non conflict (city, valid_time) do update set\n  "
        + ",\n  ".join(updates)
        + ",\n  computed_at = date_trunc('second', now())"
    )


UPSERT_RATING_SQL = _build_upsert_sql()

# `valid_time < slot` keeps a same-hour retry from learning from its own earlier
# row (the forecast must be reproducible). Exhausted rows are excluded because
# the CSV archive never stored them.
HISTORY_SQL = (
    "select to_char(valid_time at time zone 'UTC', 'YYYY-MM-DD\"T\"HH24:MI:SS\"Z\"') as datetime_utc, "
    "city, air_temp_c as air_temp, wind_perp_ms as wind_speed, "
    "solar_radiation_wm2 as solar_radiation, rating_amps as dlr_amps, "
    "static_rating_amps as static_rating, status, fallback "
    f"from {CITY_RATING_TABLE} "
    "where city = %(city)s and valid_time < %(slot)s and valid_time >= %(since)s "
    "and not exhausted "
    "order by valid_time"
)


class StoreError(RuntimeError):
    """A configuration or database failure. The message is always redacted."""


# ──────────────────────────────────────────────────────────────────────────────
# Secret hygiene (DB-04)
# ──────────────────────────────────────────────────────────────────────────────

_URL_RE = re.compile(r"postgres(?:ql)?://\S+", re.IGNORECASE)
_KEY_VALUE_RE = re.compile(
    r"(?i)\b(password|token|api_key|apikey|key|secret)=([^\s&;,'\"]+)"
)
_ENV_URL_NAMES = ("SUPABASE_DB_URL", "SUPABASE_ADMIN_DB_URL")
_MAX_MESSAGE_CHARS = 300


def _url_secrets(url) -> list:
    """The URL itself and its password component, raw and percent-decoded."""
    if not url or not isinstance(url, str):
        return []
    found = [url]
    try:
        password = urlsplit(url).password
    except ValueError:
        password = None
    if password:
        found.extend([password, unquote(password)])
    return found


def _connection_identifiers(url) -> list:
    """
    The host, the user and the project reference (the part of a pooler user after the
    dot) of a connection URL. They name the project, so a connection-failure message
    must not carry them (DB-04).
    """
    if not url or not isinstance(url, str):
        return []
    try:
        parts = urlsplit(url)
        host, user = parts.hostname, parts.username
    except ValueError:
        return []
    found = []
    if user:
        user = unquote(user)
        found.append(user)
        if "." in user:
            found.append(user.split(".", 1)[1])
    if host:
        found.append(host)
    return [item for item in found if len(item) >= 3]


def _project_identifiers(url) -> list:
    """
    The project reference (the part of a pooler user after the dot) and the host of a
    connection URL, without the user itself: the success log redacts the server-reported
    role against these, so a bare role such as `dlr_writer` stays readable while a server
    echoing a dotted user still could not print the reference.
    """
    if not url or not isinstance(url, str):
        return []
    try:
        parts = urlsplit(url)
        host, user = parts.hostname, parts.username
    except ValueError:
        return []
    found = []
    if user:
        user = unquote(user)
        if "." in user:
            found.append(user.split(".", 1)[1])
    if host:
        found.append(host)
    return [item for item in found if len(item) >= 3]


# libpq's failure text names the server it tried, with its resolved address in parentheses.
_RESOLVED_ADDRESS_RE = re.compile(r"\((?:\d{1,3}\.){3}\d{1,3}\)|\((?:[0-9a-fA-F]{0,4}:){2,}[0-9a-fA-F:.]*\)")


def redact(text, secrets=None) -> str:
    """
    Return `text` with every secret removed: postgres(ql):// URLs, key=value
    secrets (password, token, api_key, apikey, key, secret), and every non-empty
    string in `secrets` (default: the URLs in SUPABASE_DB_URL and
    SUPABASE_ADMIN_DB_URL and their password components, raw and
    percent-decoded). Truncated to 300 characters.
    """
    text = "" if text is None else str(text)
    if secrets is None:
        secrets = []
        for name in _ENV_URL_NAMES:
            secrets.extend(_url_secrets(os.environ.get(name)))
    # Longest first, so a URL is replaced before the password inside it.
    for secret in sorted({s for s in secrets if s}, key=len, reverse=True):
        text = text.replace(secret, "REDACTED")
    text = _URL_RE.sub("postgresql://REDACTED", text)
    text = _KEY_VALUE_RE.sub(lambda m: f"{m.group(1)}=REDACTED", text)
    return text[:_MAX_MESSAGE_CHARS]


def connect(url=None):
    """
    Open the writer connection. `url` defaults to the SUPABASE_DB_URL secret.
    Raises `StoreError` naming the variable when it is missing or blank (before
    any driver import or connection attempt) and a redacted `StoreError` when
    the connection fails; the original exception is not chained, so no part of
    the URL reaches a traceback.
    """
    if url is None:
        url = os.environ.get("SUPABASE_DB_URL")
    if url is None or not str(url).strip():
        raise StoreError("SUPABASE_DB_URL is not set")
    # A secret pasted with a trailing newline must connect: the stripped URL is the one
    # that is redacted and the one handed to libpq.
    url = str(url).strip()

    secrets = _url_secrets(url)
    for name in _ENV_URL_NAMES:
        secrets.extend(_url_secrets(os.environ.get(name)))

    failure = None
    conn = None
    try:
        import psycopg  # imported here so importing this module needs no driver

        # prepare_threshold=None keeps a pasted transaction-pooler URL (port 6543) working.
        conn = psycopg.connect(url, connect_timeout=10, prepare_threshold=None, autocommit=True)
        conn.execute("set statement_timeout = '30s'")
        # The valid_time CHECK truncates in the session time zone; pin it to UTC so a
        # session default can never make an hour-aligned UTC slot look off-hour.
        conn.execute("set timezone = 'UTC'")
        # The role the server reports; the client-supplied user carries the project reference.
        role = conn.execute("select current_user").fetchone()[0]
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
        failure = _RESOLVED_ADDRESS_RE.sub(
            "(REDACTED)", redact(str(exc), secrets + _connection_identifiers(url))
        )
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
    # Raised outside the except block so no exception context (and thus no part of
    # the original message) is attached to the StoreError.
    if failure is not None:
        raise StoreError(f"database connection failed: {failure}")
    log.info("connected to Postgres as %s", redact(role, secrets + _project_identifiers(url)))
    return conn


# ──────────────────────────────────────────────────────────────────────────────
# Run slot and run context
# ──────────────────────────────────────────────────────────────────────────────

def _to_utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        raise ValueError(f"not a timestamp: {value!r}")
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def slot_of(end) -> datetime:
    """
    The run slot of window end `end`: the UTC hour containing it, as a
    timezone-aware datetime. A naive value is taken as UTC.
    """
    try:
        ts = _to_utc(end)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"cannot read run end {end!r} as a timestamp: {exc}") from None
    return ts.floor("h").to_pydatetime()


def _repository_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_context(env=None) -> dict:
    """
    run_id, run_attempt and pipeline_version for the rows of one run. The
    scheduled runner sets GITHUB_RUN_ID / GITHUB_RUN_ATTEMPT for its children,
    so rating rows and the run-log row share the id.
    """
    env = os.environ if env is None else env
    run_id = env.get("GITHUB_RUN_ID")
    if not run_id:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"local-{stamp}-{uuid.uuid4().hex[:8]}"
    try:
        run_attempt = int(env.get("GITHUB_RUN_ATTEMPT") or 1)
    except ValueError:
        run_attempt = 1
    sha = (env.get("GITHUB_SHA") or "").strip()
    if sha:
        pipeline_version = sha[:7]
    else:
        pipeline_version = "unknown"
        try:
            out = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=_repository_root(), capture_output=True, text=True, timeout=5, check=True,
            )
            pipeline_version = out.stdout.strip() or "unknown"
        except Exception:  # noqa: BLE001 - version is a label, never a reason to fail a run
            pass
    return {"run_id": str(run_id), "run_attempt": run_attempt, "pipeline_version": pipeline_version}


# ──────────────────────────────────────────────────────────────────────────────
# Value hygiene
# ──────────────────────────────────────────────────────────────────────────────

def _finite(x):
    """A Python float, or None for None and for NaN / infinity."""
    if x is None:
        return None
    if hasattr(x, "item") and not isinstance(x, (int, float, str, bool)):
        x = x.item()
    if isinstance(x, bool):
        return float(x)
    try:
        value = float(x)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _json_safe(value):
    """A JSON-serializable form of one probe-trail value (no numpy, no NaN)."""
    if value is None or isinstance(value, (str, bool)):
        return value
    if hasattr(value, "item") and not isinstance(value, (int, float)):
        value = value.item()
        if value is None or isinstance(value, (str, bool)):
            return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return _finite(value)
    return str(value)


def _opt_int(x):
    return None if x is None else int(x)


def _opt_str(x):
    return None if x is None else str(x)


def _opt_bool(x):
    return None if x is None else bool(x)


# ──────────────────────────────────────────────────────────────────────────────
# Rating identity (DB-06)
# ──────────────────────────────────────────────────────────────────────────────
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


def file_sha256(path) -> str:
    """Lowercase hex sha256 of a file's bytes (read in 1 MiB chunks)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# Forecast methods that load a model file, and the function giving that file's
# path (the path `ampacity_forecast._load_model` reads). Together with
# FORECAST_METHODS_WITHOUT_ARTIFACT they must cover ampacity_forecast.FORECAST_METHODS
# (a test enforces it), so a new forecast method cannot write rows without saying
# whether it has an artifact.
FORECAST_ARTIFACT_PATHS = {"ml": ampacity_forecast._model_path_for}
FORECAST_METHODS_WITHOUT_ARTIFACT = ("naive", "ewm")


def model_identity(city: str, pipeline: dict) -> dict:
    """
    forecast_model_sha256 / anomaly_model_sha256 of the model files this run loaded.

    The forecast hash is the file `ampacity_forecast._load_model(city)` reads, and
    only when the method has an artifact and a forecast was produced (so that file
    was loaded); otherwise None. The anomaly hash is the file named by
    `pipeline["detector_model"]`, else None. The files are hashed at write time;
    each run process loads a model once and Phase 5 starts one process per city
    per run, so the hashed file is the loaded file unless it is replaced during
    that process. A method in neither table raises ValueError; a missing file
    raises, so a NULL never hides a model that was used.
    """
    method = pipeline.get("forecast_method")
    if method in FORECAST_ARTIFACT_PATHS:
        forecast_sha = None
        if pipeline.get("forecast") is not None:
            forecast_sha = file_sha256(FORECAST_ARTIFACT_PATHS[method](city))
    elif method in FORECAST_METHODS_WITHOUT_ARTIFACT:
        forecast_sha = None
    else:
        raise ValueError(
            f"forecast method {method!r} is not classified for model identity; add it to "
            "FORECAST_ARTIFACT_PATHS or FORECAST_METHODS_WITHOUT_ARTIFACT"
        )
    detector_path = pipeline.get("detector_model")
    anomaly_sha = None if detector_path is None else file_sha256(detector_path)
    return {"forecast_model_sha256": forecast_sha, "anomaly_model_sha256": anomaly_sha}


# ──────────────────────────────────────────────────────────────────────────────
# Row shaping (DB-01)
# ──────────────────────────────────────────────────────────────────────────────

def _provenance_hour(provenance):
    hour = (provenance or {}).get("hour")
    if hour is None:
        return None
    try:
        return _to_utc(hour).to_pydatetime()
    except (ValueError, TypeError):
        log.warning("observation hour %r in provenance is not a timestamp; storing NULL", hour)
        return None


def build_rating_row(result: dict, end, run_ctx: dict, provenance=None) -> dict:
    """
    One `city_rating` row (no database access) from a `run_city_pipeline` result.

    Keys are exactly `CITY_RATING_COLUMNS`, values Python-native; NaN and infinity
    become None. A missing, non-finite or non-positive rating raises ValueError
    (a poisoned rating is never written; the table CHECK is the backstop).
    `provenance` is the composer's record for the resolved station
    (`hour`, `air_temp`, `wind_speed`, `solar_radiation`), or None.
    """
    city = result["city"]
    pipeline = result.get("pipeline") or {}
    provenance = provenance or {}

    rating = _finite(result.get("rating"))
    if rating is None or rating <= 0:
        raise ValueError(f"refusing to store a non-positive or non-finite rating for {city}: {result.get('rating')!r}")
    static = float(city_point.city_point(city).static_rating)
    voltage = float(config.LINE_VOLTAGE_KV)
    power_factor = float(config.POWER_FACTOR)

    alerts = [str(a) for a in (result.get("alerts") or [])]
    gates = sorted({a.split(" ")[0] for a in alerts})

    observation = result.get("observation")
    obs = observation if observation is not None else {}

    trail = [
        {str(k): _json_safe(v) for k, v in entry.items()} if isinstance(entry, dict) else _json_safe(entry)
        for entry in (result.get("probe_trail") or [])
    ]

    forecast = pipeline.get("forecast")
    fc = forecast if forecast is not None else {}

    identity = model_identity(city, pipeline)

    row = {
        "city": city,
        "valid_time": slot_of(end),
        "observation_time": _provenance_hour(provenance),
        "rating_amps": rating,
        "rating_mw": float(amps_to_mw(rating, voltage, power_factor)),
        "static_rating_amps": static,
        "static_rating_mw": float(amps_to_mw(static, voltage, power_factor)),
        "line_voltage_kv": voltage,
        "power_factor": power_factor,
        "status": str(result["status"]),
        "fallback": bool(result["fallback"]),
        "fallback_gates": gates,
        "alerts": alerts,
        "exhausted": bool(result.get("exhausted", False)),
        "station_id": _opt_str(result.get("station_id")),
        "candidates_probed": _opt_int(result.get("candidates_probed")),
        "probe_trail": json.dumps(trail, allow_nan=False),
        "air_temp_c": _finite(obs.get("temp")),
        "wind_perp_ms": _finite(obs.get("wind")),
        "wind_speed_ms": _finite(obs.get("wind_raw")),
        "wind_direction_deg": _finite(obs.get("wind_direction")),
        "solar_radiation_wm2": _finite(obs.get("solar")),
        "temp_source": _opt_str(provenance.get("air_temp")),
        "wind_source": _opt_str(provenance.get("wind_speed")),
        "solar_source": _opt_str(provenance.get("solar_radiation")),
        "forecast_method": _opt_str(pipeline.get("forecast_method")),
        "forecast_status": _opt_str(pipeline.get("forecast_status")),
        "forecast_amps": _finite(fc.get("amps")),
        "forecast_ci_lower_amps": _finite(fc.get("ci_lower_amps")),
        "forecast_ci_upper_amps": _finite(fc.get("ci_upper_amps")),
        "forecast_horizon_min": _finite(fc.get("horizon_min")),
        "forecast_n_observations": _opt_int(fc.get("n_observations")),
        "forecast_used_by_g6": _opt_bool(pipeline.get("forecast_used_by_g6")),
        "detector_signal": _opt_str(pipeline.get("detector_signal")),
        # The model path itself is never stored: the base table is publicly readable (OD-6).
        "detector_model_loaded": pipeline.get("detector_model") is not None,
        "history_rows": _opt_int(pipeline.get("history_rows")),
        "usable_history_rows": _opt_int(pipeline.get("usable_history_rows")),
        "rating_basis": config.RATING_BASIS,
        "config_version": config.RATING_CONFIG_VERSION,
        "config_fingerprint": rating_config_fingerprint(city),
        "forecast_model_sha256": identity["forecast_model_sha256"],
        "anomaly_model_sha256": identity["anomaly_model_sha256"],
        "origin": "live",
        "run_id": run_ctx.get("run_id"),
        "run_attempt": run_ctx.get("run_attempt"),
        "pipeline_version": run_ctx.get("pipeline_version"),
        "schema_version": CITY_RATING_SCHEMA_VERSION,
    }
    if tuple(row) != CITY_RATING_COLUMNS:
        raise RuntimeError("build_rating_row keys drifted from CITY_RATING_COLUMNS")
    return row


# ──────────────────────────────────────────────────────────────────────────────
# Database access
# ──────────────────────────────────────────────────────────────────────────────

def upsert_rating(conn, row: dict) -> None:
    """Upsert one row on (city, valid_time) in one transaction (OD-7)."""
    failure = None
    try:
        with conn.transaction():
            conn.execute(UPSERT_RATING_SQL, row)
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
        failure = redact(str(exc))
    if failure is not None:
        raise StoreError(f"could not write the {row.get('city')} rating: {failure}")


def _city_rank(city) -> int:
    """Position in config.LOCATIONS; a city outside it sorts last."""
    try:
        return list(config.LOCATIONS).index(city)
    except ValueError:
        return len(config.LOCATIONS)


def _redact_keys(by_city):
    """A per-city dict of dicts with every key of the inner dicts redacted (error keys can echo secrets)."""
    if by_city is None:
        return None
    return {
        str(city): {redact(key): value for key, value in (inner or {}).items()}
        for city, inner in by_city.items()
    }


def build_run_row(run_ctx: dict, *, window_end, provider, forecast_method, started_at,
                  finished_at, city_records, provider_errors=None, sources=None) -> dict:
    """
    One `pipeline_run` row (no database access). Keys are exactly
    `PIPELINE_RUN_COLUMNS`.

    `city_records` holds one dict per city the run reached (city, written, error,
    forecast_status, detector_model_loaded). A city that was written with a
    forecast_status of "ok" or "cold_start" and an anomaly model loaded is in
    `cities_ok`; one that was written otherwise is in `cities_failed` with
    outcome "degraded"; one that was not written is there with outcome "error"
    (OD-9: it has no rating row, so this row is its only record). Every error
    string goes through `redact()` and is cut to 1000 characters. `cities_ok` and
    `cities_failed` follow config.LOCATIONS order. `provider_errors` and `sources`
    are dicts keyed by city (or None).
    """
    ordered = sorted(city_records, key=lambda rec: _city_rank(rec["city"]))
    cities_ok = []
    cities_failed = {}
    for rec in ordered:
        city = rec["city"]
        written = bool(rec.get("written"))
        status = rec.get("forecast_status")
        loaded = bool(rec.get("detector_model_loaded"))
        if written and status in _HEALTHY_FORECAST_STATUSES and loaded:
            cities_ok.append(city)
            continue
        error = rec.get("error")
        cities_failed[city] = {
            "outcome": "degraded" if written else "error",
            "written": written,
            "forecast_status": status,
            "detector_model_loaded": loaded,
            "error": None if error is None else redact(error)[:_RUN_ERROR_MAX_CHARS],
        }
    row = {
        "run_id": run_ctx.get("run_id"),
        "run_attempt": run_ctx.get("run_attempt"),
        "started_at": _to_utc(started_at).to_pydatetime(),
        "finished_at": _to_utc(finished_at).to_pydatetime(),
        "window_end": _to_utc(window_end).to_pydatetime(),
        "provider": _opt_str(provider),
        "forecast_method": _opt_str(forecast_method),
        "pipeline_version": run_ctx.get("pipeline_version"),
        "cities_ok": cities_ok,
        "cities_failed": cities_failed,
        "provider_errors": _redact_keys(provider_errors),
        "sources": None if sources is None else {str(c): v for c, v in sources.items()},
    }
    if tuple(row) != PIPELINE_RUN_COLUMNS:
        raise RuntimeError("build_run_row keys drifted from PIPELINE_RUN_COLUMNS")
    return row


def upsert_run(conn, row: dict) -> None:
    """
    Upsert one `pipeline_run` row keyed by run_id, in one transaction. `row` may
    be any subset of `PIPELINE_RUN_COLUMNS` that includes run_id; every given
    non-key column is updated on conflict, so a re-run attempt (same
    GITHUB_RUN_ID) replaces the row. Column names are only ever taken from
    `PIPELINE_RUN_COLUMNS` (an unknown key raises ValueError); values are bound
    parameters. Phase 5's live_run_log may delegate to this function.
    """
    unknown = [key for key in row if key not in PIPELINE_RUN_COLUMNS]
    if unknown:
        raise ValueError(f"not pipeline_run columns: {unknown}")
    if row.get(PIPELINE_RUN_KEY) is None:
        raise ValueError("a pipeline_run row needs a run_id")

    columns = [column for column in PIPELINE_RUN_COLUMNS if column in row]
    placeholders = [
        f"%({column})s::jsonb" if column in PIPELINE_RUN_JSONB else f"%({column})s"
        for column in columns
    ]
    updates = [f"{column} = excluded.{column}" for column in columns if column != PIPELINE_RUN_KEY]
    if updates:
        conflict = "on conflict (run_id) do update set " + ", ".join(updates)
    else:
        conflict = "on conflict (run_id) do nothing"
    sql = (
        f"insert into {PIPELINE_RUN_TABLE} ({', '.join(columns)}) "
        f"values ({', '.join(placeholders)}) {conflict}"
    )
    params = {
        column: (
            json.dumps(row[column], allow_nan=False, default=str)
            if column in PIPELINE_RUN_JSONB and row[column] is not None else row[column]
        )
        for column in columns
    }

    failure = None
    try:
        with conn.transaction():
            conn.execute(sql, params)
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
        failure = redact(str(exc))
    if failure is not None:
        raise StoreError(f"could not write the pipeline_run row: {failure}")


def read_history(conn, city: str, end, days=None) -> pd.DataFrame:
    """
    The last `days` (default config.DB_HISTORY_WINDOW_DAYS, OD-8) days of `city`
    rows strictly before the run's slot, as a historical_archive.ARCHIVE_COLUMNS
    frame in the CSV archive's spelling, ascending by time. Empty result: an
    empty ARCHIVE_COLUMNS frame.
    """
    slot = slot_of(end)
    window = config.DB_HISTORY_WINDOW_DAYS if days is None else days
    since = slot - pd.Timedelta(days=window).to_pytimedelta()
    params = {"city": city, "slot": slot, "since": since}

    failure = None
    try:
        cursor = conn.execute(HISTORY_SQL, params)
        rows = cursor.fetchall()
        names = [d.name for d in cursor.description]
    except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
        failure = redact(str(exc))
    if failure is not None:
        raise StoreError(f"could not read {city} history: {failure}")

    if rows:
        frame = pd.DataFrame(rows, columns=names)
        for column in ("air_temp", "wind_speed", "solar_radiation", "dlr_amps", "static_rating"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce").astype("float64")
        frame["fallback"] = frame["fallback"].astype(bool)
        frame["schema_version"] = historical_archive.ARCHIVE_SCHEMA_VERSION
        # The same row check the CSV archive applies before history trains anything.
        frame = historical_archive.validate_history_frame(frame, f"postgres:{city}")
        frame = frame[historical_archive.ARCHIVE_COLUMNS].reset_index(drop=True)
    else:
        frame = pd.DataFrame(columns=historical_archive.ARCHIVE_COLUMNS)
    if frame.empty:
        log.warning(
            "%s: no usable history in Postgres for the %d days before %s -- cold start "
            "(after the backfill load this points at the RLS policy or the writer role)",
            city, window, slot.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    return frame


class SupabaseStore:
    """
    The pipeline's Postgres store: history in, rating rows out. One instance
    holds one connection and one run context, so every row of a run shares its
    run_id, run_attempt and pipeline_version.
    """

    def __init__(self, conn, run_ctx=None, history_days=None):
        self.conn = conn
        self.run_ctx = run_context() if run_ctx is None else run_ctx
        self.history_days = history_days

    @classmethod
    def from_env(cls, url=None):
        return cls(connect(url))

    def read_history(self, city: str, end) -> pd.DataFrame:
        return read_history(self.conn, city, end, days=self.history_days)

    def write_rating(self, result: dict, end, provenance=None) -> bool:
        row = build_rating_row(result, end, self.run_ctx, provenance)
        upsert_rating(self.conn, row)
        return True

    def record_run(self, row: dict) -> None:
        """Upsert the run's `pipeline_run` row (see `upsert_run`)."""
        upsert_run(self.conn, row)

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False
