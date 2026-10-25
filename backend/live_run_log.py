"""
Live run log (production-pipeline Phase 5: SCHED-01, OD-9)
==================================================
One `public.pipeline_run` row per live run, written only by the runner
(`dlr_live_run.py`): inserted before the first city's child starts, updated after
every city and finished (`finished_at` set) at the end. A run that the job timeout
kills therefore leaves a row with `finished_at` null and the cities it reached.
The runner's children never write this row themselves (`--no-run-row`).

The row is keyed by `run_id` (GITHUB_RUN_ID, or a local id) with `run_attempt`
(GITHUB_RUN_ATTEMPT). Sending the row again for the same run is an upsert in place:
a manual re-run of the same Actions run (same id, attempt 2) replaces the row under
Phase 4's primary key, it does not add a second one.

`cities_ok` lists, in `config.LOCATIONS` order, the cities whose rating row was
written with a healthy ML path: `forecast_status` 'ok' or 'cold_start' and an
anomaly model loaded. Every other city reached so far is in `cities_failed`, an
object per city with its `outcome`:

    error     the child failed or produced no usable result; no rating row was
              written (OD-9), so this entry is the city's only record
    timeout   the child outlived its time budget and was killed; no rating row
    degraded  the rating row was written, but the ML forecast failed, no anomaly
              model loaded, or the city's history could not be cleaned

Error text lives here, not in `city_rating`, because `pipeline_run` is not readable
by consumers (Phase 4 revokes the anon and authenticated roles) while `city_rating`
is (OD-6). The runner redacts every error text before it reaches a record; this
module only truncates it. Values reach the database as bound parameters only, through
Phase 4's `supabase_store.upsert_run`, which names columns from its own constant.

`supabase_store` (and through it `psycopg`) is imported inside the functions that
need it, so building a row never needs a driver or a database.
"""

from datetime import datetime, timezone

import config

# forecast_status values that count as a healthy ML forecast (Phase 4's own set).
HEALTHY_FORECAST_STATUSES = ("ok", "cold_start")

PROVIDER = "composed"
FORECAST_METHOD = "ml"
ERROR_MAX_CHARS = 1000
FORECAST_ERROR_MAX_CHARS = 300

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _timestamp(value):
    """An aware UTC datetime from a runner timestamp string or a datetime; None stays None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return datetime.strptime(value, _TS_FMT).replace(tzinfo=timezone.utc)


def _truncate(text, limit):
    return None if text is None else str(text)[:limit]


def _city_rank(city) -> int:
    """Position in config.LOCATIONS; a city outside it sorts last."""
    try:
        return list(config.LOCATIONS).index(city)
    except ValueError:
        return len(config.LOCATIONS)


def pipeline_version(env=None) -> str:
    """
    GITHUB_SHA[:7], else `git rev-parse --short HEAD`, else "unknown": Phase 4's
    `supabase_store.run_context`, so a run row and its rating rows agree.
    """
    import supabase_store

    return supabase_store.run_context(env)["pipeline_version"]


def _is_healthy(record) -> bool:
    return (record.get("outcome") == "ok"
            and record.get("forecast_status") in HEALTHY_FORECAST_STATUSES
            and record.get("detector_model_loaded") is True
            and not record.get("cleaning_error"))


def build_run_row(state, env=None) -> dict:
    """
    The `pipeline_run` row for a run state (pure, no database access).

    `state` is the runner's run state: `run_id`, `run_attempt`, `end` (the shared
    window end), `started_at`, `finished_at` (None while the run is in progress) and
    `cities` (one outcome record per city reached so far). `state["pipeline_version"]`,
    when present, is used as is (the runner computes it once per run); otherwise it is
    looked up with `pipeline_version(env)`. Timestamps are aware UTC datetimes.
    """
    ordered = sorted(state.get("cities") or [], key=lambda rec: _city_rank(rec["city"]))
    cities_ok = []
    cities_failed = {}
    provider_errors = {}
    sources = {}
    for rec in ordered:
        city = rec["city"]
        if _is_healthy(rec):
            cities_ok.append(city)
        else:
            written = bool(rec.get("written"))
            cities_failed[city] = {
                # an 'ok' child that is not healthy wrote its row with a broken ML path
                "outcome": "degraded" if rec.get("outcome") == "ok" else rec.get("outcome"),
                "written": written,
                "exit_code": rec.get("exit_code"),
                "duration_s": rec.get("duration_s"),
                "forecast_status": rec.get("forecast_status"),
                "forecast_error": _truncate(rec.get("forecast_error"), FORECAST_ERROR_MAX_CHARS),
                "detector_model_loaded": bool(rec.get("detector_model_loaded")),
                "cleaning_error": _truncate(rec.get("cleaning_error"), FORECAST_ERROR_MAX_CHARS),
                "error": _truncate(rec.get("error"), ERROR_MAX_CHARS),
                "fault_injected": bool(rec.get("fault_injected")),
            }
        if rec.get("provider_errors"):
            provider_errors[city] = rec["provider_errors"]
        if rec.get("sources"):
            sources[city] = rec["sources"]
    return {
        "run_id": state["run_id"],
        "run_attempt": state.get("run_attempt"),
        "started_at": _timestamp(state.get("started_at")),
        "finished_at": _timestamp(state.get("finished_at")),
        "window_end": _timestamp(state.get("end")),
        "provider": PROVIDER,
        "forecast_method": FORECAST_METHOD,
        "pipeline_version": state.get("pipeline_version") or pipeline_version(env),
        "cities_ok": cities_ok,
        "cities_failed": cities_failed,
        "provider_errors": provider_errors,
        "sources": sources,
    }


def upsert_run_row(conn, row) -> None:
    """
    Upsert `row` into `public.pipeline_run` keyed by `run_id`, in one transaction.

    Delegates to Phase 4's `supabase_store.upsert_run`: it accepts any subset of
    the pipeline_run columns that includes run_id, updates every given non-key
    column on conflict, binds every value as a parameter and casts the jsonb
    columns, so a repeated send for the same run replaces the row in place.
    """
    import supabase_store

    supabase_store.upsert_run(conn, row)


def open_connection():
    """A new writer connection through Phase 4's `supabase_store.connect()` (SUPABASE_DB_URL)."""
    import supabase_store

    return supabase_store.connect()
