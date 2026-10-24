"""
Live run log (production-pipeline Phase 5: SCHED-01, OD-9)
==================================================
Skeleton committed with the failing tests (TDD RED); the implementation follows.
"""

HEALTHY_FORECAST_STATUSES = ("ok", "cold_start")


def build_run_row(state, env=None) -> dict:
    return {
        "run_id": None, "run_attempt": None, "started_at": None, "finished_at": None,
        "window_end": None, "provider": None, "forecast_method": None,
        "pipeline_version": None, "cities_ok": [], "cities_failed": {},
        "provider_errors": {}, "sources": {},
    }


def upsert_run_row(conn, row) -> None:
    raise NotImplementedError


def open_connection():
    raise NotImplementedError
