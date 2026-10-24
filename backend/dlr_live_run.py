"""
Live DLR runner (production-pipeline Phase 5: PIPE-02, SCHED-01)
==================================================
Rates every city in `config.LOCATIONS` once, the way the hourly GitHub Actions
workflow (`.github/workflows/dlr_live.yml`) needs it: one `dlr_orchestrator.py`
child process per city, one after another, all sharing one window end.

Why one child per city: a hung HTTP call inside one Python process cannot be
interrupted, so a child gives each city a hard time budget (`CITY_TIMEOUT_S`) and
a fresh interpreter and TLS session. The shadow collector adopted the same model
after position-dependent timeouts on GitHub-hosted runners
(docs/data-science/decisions/shadow_collection_runbook.md, "Process model").

Each child runs the composed providers (OD-2) with the ML forecast (OD-3) against
the Postgres store (DB-02) and writes its own rating row through Phase 4's
writer. This runner never writes a rating itself: a city whose child failed or
timed out gets no row (OD-9) and is recorded here, in its outcome record.

Exit codes:
    0  every city is 'ok', with forecast_status 'ok' or 'cold_start'
    1  anything else (a city errored or timed out, or ran without its ML
       forecast or anomaly model), so the Actions run turns red
    2  a usage error (argparse)

CLI (local runs read `.env` through python-dotenv; tests never do):
    PYTHONPATH=backend python backend/dlr_live_run.py
    PYTHONPATH=backend python backend/dlr_live_run.py --cities MIDLAND --end 2026-10-24T14:00:00Z
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

import config

log = logging.getLogger(__name__)

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
# A module attribute so tests can point the runner at a fake child.
ORCHESTRATOR = os.path.join(BACKEND_DIR, "dlr_orchestrator.py")

CITY_TIMEOUT_S = 300
PROVIDER = "composed"
FORECAST_METHOD = "ml"
# Phase 4 (04-02 SUMMARY): `--store postgres` selects the Supabase store; the
# runner's per-city children skip the run row (the runner owns it, plan 05-03).
STORE_ARGS = ("--store", "postgres", "--no-run-row")
# Summary-row key that is True only when the rating row was written (04-02).
WRITE_FLAG_KEY = "archived"

PROVIDER_ENV = ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL")
DB_ENV = ("SUPABASE_DB_URL",)
REQUIRED_ENV = PROVIDER_ENV + DB_ENV

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
_STDERR_TAIL_LINES = 20


def _utc(now):
    """An aware UTC datetime; a naive value is taken as UTC."""
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _stamp(now) -> str:
    return _utc(now).strftime(_TS_FMT)


def run_end(now) -> str:
    """The shared window end: `now` (UTC) floored to 5 minutes, like the orchestrator's default."""
    now = _utc(now).replace(second=0, microsecond=0)
    return _stamp(now.replace(minute=now.minute - now.minute % 5))


def slot_of(end: str) -> str:
    """The run slot of a window end: the end truncated to the hour (OD-7 valid_time)."""
    parsed = datetime.strptime(end, _TS_FMT)
    return _stamp(parsed.replace(minute=0, second=0, microsecond=0))


def run_identity(env, now=None) -> tuple:
    """
    `(run_id, run_attempt)`: GITHUB_RUN_ID and GITHUB_RUN_ATTEMPT when GITHUB_RUN_ID
    is set, else a local id. Phase 4's writer reads the same two variables
    (`supabase_store.run_context`), so rating rows and the run log share the id.
    """
    run_id = env.get("GITHUB_RUN_ID")
    if run_id:
        try:
            attempt = int(env.get("GITHUB_RUN_ATTEMPT") or 1)
        except ValueError:
            attempt = 1
        return run_id, attempt
    now = datetime.now(timezone.utc) if now is None else now
    return f"local-{_utc(now).strftime('%Y%m%dT%H%M%SZ')}-{os.getpid()}", 1


def child_argv(city: str, end: str, output_path: str) -> list:
    """The command line of one city's orchestrator child."""
    return [
        sys.executable, ORCHESTRATOR,
        "--cities", city,
        "--end", end,
        "--window-hours", "1",
        "--provider", PROVIDER,
        "--forecast-method", FORECAST_METHOD,
        *STORE_ARGS,
        "--output", output_path,
    ]


def _tail(text, lines=_STDERR_TAIL_LINES) -> str:
    return "\n".join((text or "").strip().splitlines()[-lines:])


def classify(city, returncode, output, stderr_text, fault_injected=False, timed_out=False) -> dict:
    """
    One city's outcome record, from what its child left behind (pure).

    'ok' only with positive evidence: exit 0, a summary row for the city and a
    true write flag. Everything else is 'error'; a row is never invented for it.
    """
    record = {
        "city": city, "outcome": "error", "exit_code": returncode,
        "rating_a": None, "fallback": None, "exhausted": None, "fallback_gates": [],
        "written": False, "forecast_status": "not_run", "forecast_error": None,
        "detector_model_loaded": False, "provider_errors": {}, "error": None,
        "fault_injected": fault_injected,
    }
    errors = (output or {}).get("errors") or {}
    if returncode != 0:
        record["error"] = errors.get(city) or _tail(stderr_text) or f"exit {returncode}"
        return record
    row = next((r for r in (output or {}).get("summary") or [] if r.get("city") == city), None)
    if row is None or not row.get(WRITE_FLAG_KEY):
        record["error"] = "child output is unusable"
        return record
    record.update(
        outcome="ok",
        rating_a=row.get("rating_a"), fallback=row.get("fallback"),
        exhausted=row.get("exhausted"), fallback_gates=row.get("fallback_gates") or [],
        written=True, forecast_status=row.get("forecast_status"),
        forecast_error=row.get("forecast_error"),
        detector_model_loaded=bool(row.get("detector_model_loaded")),
        provider_errors=output.get("provider_errors") or {},
    )
    return record


def _emit(city, stdout_text, stderr_text, env):
    """Re-emit a child's captured streams, grouped in the Actions log."""
    grouped = env.get("GITHUB_ACTIONS") == "true"
    if grouped:
        print(f"::group::{city}", flush=True)
    if stdout_text:
        sys.stdout.write(stdout_text)
    if stderr_text:
        sys.stderr.write(stderr_text)
    if grouped:
        print("::endgroup::", flush=True)
    sys.stdout.flush()
    sys.stderr.flush()


def _load_output(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def run_city(city, end, workdir, timeout_s, env) -> dict:
    """Run one city's child and return its outcome record, with timing."""
    output_path = os.path.join(workdir, f"{city}.json")
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    proc = subprocess.run(
        child_argv(city, end, output_path), cwd=REPO_ROOT, env=env,
        capture_output=True, text=True, timeout=timeout_s)
    duration = time.monotonic() - t0
    _emit(city, proc.stdout, proc.stderr, env)
    record = classify(city, proc.returncode, _load_output(output_path), proc.stderr)
    record.update(started_at=_stamp(started), finished_at=_stamp(datetime.now(timezone.utc)),
                  duration_s=round(duration, 1))
    return record


def run_live(cities=None, end=None, fault_city="", timeout_s=CITY_TIMEOUT_S, env=None, now=None) -> dict:
    """
    Run every city (default: all of config.LOCATIONS) strictly one after another, in
    that order, each in its own child sharing one window end. Returns the run
    record: ids, end, slot, times, one record per city and the exit code.
    """
    env = dict(os.environ if env is None else env)
    now = datetime.now(timezone.utc) if now is None else now
    cities = list(cities) if cities else list(config.LOCATIONS)
    end = end or run_end(now)
    run_id, run_attempt = run_identity(env, now)
    child_env = dict(env)
    if not env.get("GITHUB_RUN_ID"):
        child_env["GITHUB_RUN_ID"] = run_id
        child_env["GITHUB_RUN_ATTEMPT"] = str(run_attempt)

    started_at = _stamp(datetime.now(timezone.utc))
    records = []
    with tempfile.TemporaryDirectory() as workdir:
        for city in cities:
            record = run_city(city, end, workdir, timeout_s, child_env)
            log.info("%s: %s in %.1fs", city, record["outcome"], record["duration_s"])
            records.append(record)
    exit_code = 0 if all(r["outcome"] == "ok" for r in records) else 1
    log.info("live run %s attempt %s finished, exit code %d", run_id, run_attempt, exit_code)
    return {
        "run_id": run_id, "run_attempt": run_attempt, "end": end, "slot": slot_of(end),
        "started_at": started_at, "finished_at": _stamp(datetime.now(timezone.utc)),
        "cities": records, "exit_code": exit_code,
    }


def _end_arg(value):
    try:
        slot_of(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--end must look like 2026-10-24T14:00:00Z, got {value!r}")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run every city's live DLR pipeline, one child process each.")
    parser.add_argument("--cities", nargs="*", choices=config.LOCATIONS, default=None,
                        help="default: every city in config.LOCATIONS")
    parser.add_argument("--end", type=_end_arg, default=None,
                        help="window end (default: now floored to 5 minutes); for re-running a missed slot")
    parser.add_argument("--timeout-s", type=int, default=CITY_TIMEOUT_S,
                        help="per-city child time budget in seconds")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    return run_live(cities=args.cities, end=args.end, timeout_s=args.timeout_s)["exit_code"]


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
