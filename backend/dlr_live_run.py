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

A city is 'ok' only with positive evidence: its child exited 0, left an --output
file with a summary row for the city, and that row says the rating row was
written. A child that exits non-zero is 'error', one that outlives
`CITY_TIMEOUT_S` is killed and recorded as 'timeout', and in both cases the
remaining cities still run.

Exit codes:
    0  every city is 'ok', with forecast_status 'ok' or 'cold_start', a loaded
       anomaly model and no history-cleaning failure
    1  anything else (a city errored or timed out, ran without its ML forecast
       or anomaly model, or could not clean its history), so the Actions run
       turns red
    2  a usage error (argparse), for example an unknown --fault-city

Fault drill (SCHED-01): `--fault-city CITY`, or the DLR_LIVE_FAULT_CITY variable
the workflow maps from its `fault_city` input, runs that one city with its
provider credentials blanked so it fails, proving the failure path end to end.
The value is checked against `config.LOCATIONS`; it never reaches a shell.

Run log (SCHED-01, OD-9): the runner alone keeps the run's `public.pipeline_run`
row (`live_run_log.py`). `run_live` records it before the first child starts, after
every city and at the end with `finished_at` set, so a run killed by the job timeout
leaves a row with `finished_at` null. The children run with `--no-run-row` and never
write it. A write that fails is logged (redacted), counted, and makes the exit code 1;
it never stops the remaining cities. `--no-run-log` skips recording (local dry runs).

Secrets: every error text that enters a record or the Actions step summary goes
through `redact()` first.

CLI (local runs read `.env` through python-dotenv; tests never do):
    PYTHONPATH=backend python backend/dlr_live_run.py
    PYTHONPATH=backend python backend/dlr_live_run.py --cities MIDLAND --end 2026-10-24T14:00:00Z
"""

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

import config
import live_run_log

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

# forecast_status values (Phase 4) that count as a healthy ML forecast.
HEALTHY_FORECAST_STATUSES = live_run_log.HEALTHY_FORECAST_STATUSES

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
_STDERR_TAIL_LINES = 20
_MAX_TEXT_CHARS = 1000
_MIN_SECRET_CHARS = 4
_SUMMARY_ERROR_CHARS = 120
# Left boundary: `?token=`, `&api_key=` and a bare `key=` are masked, but `cache_key=` and
# `monkey=` (ordinary diagnostics) are not.
_CREDENTIAL_PARAM_RE = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(token|api_key|apikey|key|email|password)=[^&\s]+")
_DB_URL_RE = re.compile(r"postgres(?:ql)?://\S+")


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
        # absolute: the child runs with cwd=REPO_ROOT, and a relative venv path would not resolve there
        os.path.abspath(sys.executable), ORCHESTRATOR,
        "--cities", city,
        "--end", end,
        "--window-hours", "1",
        "--provider", PROVIDER,
        "--forecast-method", FORECAST_METHOD,
        *STORE_ARGS,
        "--output", output_path,
    ]


def redact(text, env=None, limit=_MAX_TEXT_CHARS) -> str:
    """
    `text` with secrets removed, cut to its last `limit` characters (1000; None keeps
    all of it, for the raw child streams re-emitted to the log). Removed, in this
    order: every REQUIRED_ENV value of 4 or more characters (and the password of
    a database URL), postgres URLs (-> `postgresql://***`), and the values of
    `token=`, `api_key=`, `key=`, `email=` and `password=` parameters (-> `name=***`;
    a name that is the tail of a longer word, like `cache_key=`, is left alone).
    The cut comes last, so a longer text never lets a secret through. `env`
    defaults to the process environment.
    """
    env = os.environ if env is None else env
    text = "" if text is None else str(text)
    secrets = set()
    for name in REQUIRED_ENV:
        value = (env.get(name) or "").strip()
        if len(value) >= _MIN_SECRET_CHARS:
            secrets.add(value)
        if name in DB_ENV and value:
            try:
                password = urlsplit(value).password
            except ValueError:
                password = None
            for part in (password, unquote(password or "")):
                if part and len(part) >= _MIN_SECRET_CHARS:
                    secrets.add(part)
    # Longest first, so a URL is replaced before the password inside it.
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, "***")
    text = _DB_URL_RE.sub("postgresql://***", text)
    text = _CREDENTIAL_PARAM_RE.sub(lambda m: f"{m.group(1)}=***", text)
    return text if limit is None else text[-limit:]


def _redact_counts(counts, env=None) -> dict:
    """
    A `{text: count}` dict with every key redacted (provider error text can echo a
    credential). Keys that become equal after redaction keep the sum of their counts.
    """
    out = {}
    for key, value in (counts or {}).items():
        safe = redact(key, env)
        if safe in out and isinstance(value, (int, float)) and isinstance(out[safe], (int, float)):
            value = out[safe] + value
        out[safe] = value
    return out


def _tail(text, lines=_STDERR_TAIL_LINES) -> str:
    return "\n".join((text or "").strip().splitlines()[-lines:])


def classify(city, returncode, output, stderr_text, fault_injected=False, timed_out=False,
             env=None) -> dict:
    """
    One city's outcome record, from what its child left behind (pure).

    Outcomes, first match wins: timed out -> 'timeout'; non-zero exit -> 'error';
    no usable --output -> 'error' ("no output"); no summary row for the city ->
    'error' ("no summary row", plus the child's own `errors[city]`); write flag
    false -> 'error' ("row not written"); otherwise 'ok'. Whenever an --output file
    was left, its `provider_errors` and `sources` are kept, whatever the outcome.
    Every 'error' text is redacted (`env` defaults to the process environment) and a row is never
    invented for a city that has none (OD-9).
    """
    output = output if isinstance(output, dict) else None
    record = {
        "city": city, "outcome": "error", "exit_code": returncode,
        "rating_a": None, "fallback": None, "exhausted": None, "fallback_gates": [],
        "written": False, "forecast_status": "not_run", "forecast_error": None,
        "detector_model_loaded": False, "cleaning_error": None, "provider_errors": {},
        "sources": {}, "error": None, "fault_injected": fault_injected,
    }
    child_error = ((output or {}).get("errors") or {}).get(city)
    if output is not None:
        # Kept for a failed city too: its per-provider counts are the only record of why (OD-9).
        provider_errors, sources = output.get("provider_errors"), output.get("sources")
        record["provider_errors"] = _redact_counts(provider_errors if isinstance(provider_errors, dict) else {}, env)
        record["sources"] = sources if isinstance(sources, dict) else {}

    def fail(outcome, text):
        record["outcome"] = outcome
        record["error"] = redact(text, env)
        return record

    if timed_out:
        return fail("timeout", "killed at its time budget\n" + _tail(stderr_text))
    if returncode != 0:
        return fail("error", child_error or _tail(stderr_text) or f"exit {returncode}")
    if output is None:
        return fail("error", "no output")
    row = next((r for r in output.get("summary") or [] if r.get("city") == city), None)
    if row is None:
        return fail("error", "no summary row" + (f": {child_error}" if child_error else ""))
    if not row.get(WRITE_FLAG_KEY):
        return fail("error", "row not written")
    record.update(
        outcome="ok",
        rating_a=row.get("rating_a"), fallback=row.get("fallback"),
        exhausted=row.get("exhausted"), fallback_gates=row.get("fallback_gates") or [],
        written=True, forecast_status=row.get("forecast_status"),
        forecast_error=None if row.get("forecast_error") is None else redact(row["forecast_error"], env),
        detector_model_loaded=bool(row.get("detector_model_loaded")),
        cleaning_error=None if row.get("cleaning_error") is None else redact(row["cleaning_error"], env),
    )
    return record


def _healthy(record) -> bool:
    """True when a record is 'ok', ran with its ML forecast and anomaly model, and cleaned its history."""
    return (record["outcome"] == "ok"
            and record["forecast_status"] in HEALTHY_FORECAST_STATUSES
            and record["detector_model_loaded"] is True
            and not record.get("cleaning_error"))


def _defang(text) -> str:
    """
    `text` with every line that would be an Actions workflow command (`::name::...`,
    possibly indented) prefixed with `[child] `. The child's output is re-emitted at
    line starts, where the runner would act on `::add-mask::` or `::stop-commands::`.
    """
    return "".join(f"[child] {line}" if line.lstrip().startswith("::") else line
                   for line in text.splitlines(keepends=True))


def _emit(city, stdout_text, stderr_text, env):
    """
    Re-emit a child's captured streams, grouped in the Actions log. The repo is public,
    so the logs are too: both streams go through `redact()` (uncut) first, because
    Actions masks only the exact secret values it holds, not a database password's
    URL-encoded form or a credential inside a request URL in a traceback. A line that
    would be a workflow command is defanged (`_defang`).
    """
    grouped = env.get("GITHUB_ACTIONS") == "true"
    if grouped:
        print(f"::group::{city}", flush=True)
    if stdout_text:
        sys.stdout.write(_defang(redact(stdout_text, env, limit=None)))
    if stderr_text:
        sys.stderr.write(_defang(redact(stderr_text, env, limit=None)))
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


def _as_text(value) -> str:
    """Partial output of a killed child: bytes, str or None."""
    if value is None:
        return ""
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value


def run_city(city, end, workdir, timeout_s, env, fault_injected=False) -> dict:
    """
    Run one city's child and return its outcome record, with timing. A child
    still running after `timeout_s` has been killed by `subprocess.run`; its
    partial output is kept and the record is 'timeout'.
    """
    output_path = os.path.join(workdir, f"{city}.json")
    started = datetime.now(timezone.utc)
    t0 = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            child_argv(city, end, output_path), cwd=REPO_ROOT, env=env,
            capture_output=True, text=True, timeout=timeout_s)
        returncode, stdout_text, stderr_text = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        returncode, stdout_text, stderr_text = None, _as_text(exc.stdout), _as_text(exc.stderr)
        log.error("%s: child exceeded %ss and was killed", city, timeout_s)
    duration = time.monotonic() - t0
    _emit(city, stdout_text, stderr_text, env)
    record = classify(city, returncode, None if timed_out else _load_output(output_path),
                      stderr_text, fault_injected=fault_injected, timed_out=timed_out, env=env)
    record.update(started_at=_stamp(started), finished_at=_stamp(datetime.now(timezone.utc)),
                  duration_s=round(duration, 1))
    return record


def write_run_row(row) -> None:
    """
    The default `record_fn`: upsert `row` into pipeline_run over a fresh connection,
    closed afterwards. A new connection per write means an idle session dropped
    while a child ran (up to 300 s) can never fail the next write.
    """
    conn = live_run_log.open_connection()
    try:
        live_run_log.upsert_run_row(conn, row)
    finally:
        conn.close()


def run_live(cities=None, end=None, fault_city="", timeout_s=CITY_TIMEOUT_S, env=None, now=None,
             record_fn=None, record_run=True) -> dict:
    """
    Run every city (default: all of config.LOCATIONS) strictly one after another, in
    that order, each in its own child sharing one window end. Returns the run
    record: ids, end, slot, times, one record per city, the exit code and `run_log`
    (`{"writes": N, "failed": M}`, None when recording is off).

    The run's pipeline_run row goes to `record_fn(row)` (default: `write_run_row`)
    before the first child, after each city and after the last with `finished_at`
    set. A `record_fn` that raises is logged (type and redacted message) and counted,
    the remaining cities still run, and the exit code is 1. `record_run=False`
    (the CLI's `--no-run-log`) records nothing.

    `fault_city` ('' or a key of config.LOCATIONS) runs that city's child with its
    provider credentials set to empty strings, so it fails (the drill); every other
    child gets the environment unmodified. The exit code is 0 only when every
    record is healthy: 'ok' with a forecast_status of 'ok' or 'cold_start' and a
    loaded anomaly model.
    """
    if fault_city and fault_city not in config.LOCATIONS:
        raise ValueError(f"fault_city must be empty or one of {list(config.LOCATIONS)}, got {fault_city!r}")
    env = dict(os.environ if env is None else env)
    now = datetime.now(timezone.utc) if now is None else now
    cities = list(cities) if cities else list(config.LOCATIONS)
    end = end or run_end(now)
    run_id, run_attempt = run_identity(env, now)
    child_env = dict(env)
    if not env.get("GITHUB_RUN_ID"):
        child_env["GITHUB_RUN_ID"] = run_id
        child_env["GITHUB_RUN_ATTEMPT"] = str(run_attempt)
    if fault_city and fault_city not in cities:
        log.warning("fault city %s is not among the cities being run; no drill happens", fault_city)

    record_fn = write_run_row if record_fn is None else record_fn
    run_log = {"writes": 0, "failed": 0}
    state = {
        "run_id": run_id, "run_attempt": run_attempt, "end": end, "slot": slot_of(end),
        "started_at": _stamp(datetime.now(timezone.utc)), "finished_at": None,
        "cities": [], "exit_code": None,
    }
    records = state["cities"]

    def save_run_row():
        if not record_run:
            return
        run_log["writes"] += 1
        try:
            record_fn(live_run_log.build_run_row(state, env=env))
        except Exception as exc:  # noqa: BLE001 - a run-log fault must never stop the cities
            run_log["failed"] += 1
            # No traceback: its message text would bypass redact().
            log.error("pipeline_run write failed (%s): %s", type(exc).__name__, redact(exc, env))

    if record_run:
        try:
            state["pipeline_version"] = live_run_log.pipeline_version(env)
        except Exception as exc:  # noqa: BLE001 - the version is a label, never a reason to fail a run
            log.error("pipeline version lookup failed (%s): %s", type(exc).__name__, redact(exc, env))
            state["pipeline_version"] = "unknown"
    save_run_row()
    with tempfile.TemporaryDirectory() as workdir:
        for city in cities:
            faulted = city == fault_city
            city_env = child_env
            if faulted:
                # Present but empty, so a `.env` loaded by the child's load_dotenv() cannot refill it.
                city_env = dict(child_env, **{name: "" for name in PROVIDER_ENV})
                log.warning("%s: fault drill, provider credentials blanked for this child", city)
            record = run_city(city, end, workdir, timeout_s, city_env, fault_injected=faulted)
            log.info("%s: %s in %.1fs", city, record["outcome"], record["duration_s"])
            records.append(record)
            save_run_row()
    state["finished_at"] = _stamp(datetime.now(timezone.utc))
    save_run_row()
    state["exit_code"] = 0 if all(_healthy(r) for r in records) and run_log["failed"] == 0 else 1
    state["run_log"] = run_log if record_run else None
    log.info("live run %s attempt %s finished, exit code %d", run_id, run_attempt, state["exit_code"])
    return state


def _cell(text, limit=_SUMMARY_ERROR_CHARS) -> str:
    """
    A markdown table cell: one line, cut to `limit` characters, backslashes and pipes
    escaped. A longer text keeps its END behind a "..." marker: for a crash traceback the exception
    line is the last one, and the head is only the frame that raised it.
    """
    flat = " ".join(str(text).split())
    if len(flat) > limit:
        flat = "..." + flat[-(limit - 3):]
    # backslashes first, so a text ending in "\\" cannot turn the next "\\|" into an escaped backslash
    return flat.replace("\\", "\\\\").replace("|", "\\|")


def write_step_summary(run, path, env=None) -> None:
    """
    Append the run to the Actions step summary: a heading, one table row per
    city, in run order, and a `pipeline_run: N writes, M failed` line. The error
    column is redacted, cut to its last 120 characters (the exception line of a
    traceback comes last) and has its pipes escaped.
    """
    lines = [
        f"## DLR live run {run['run_id']} attempt {run['run_attempt']} (slot {run['slot']})",
        "",
        "| city | outcome | rating A | fallback | written | forecast | anomaly model | fault | error |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in run["cities"]:
        rating = "-" if r.get("rating_a") is None else f"{float(r['rating_a']):.0f}"
        fallback = "-" if r.get("fallback") is None else str(bool(r["fallback"])).lower()
        cells = [
            r["city"], r["outcome"], rating, fallback,
            "yes" if r.get("written") else "no",
            str(r.get("forecast_status")),
            "loaded" if r.get("detector_model_loaded") else "missing",
            "yes" if r.get("fault_injected") else "",
            _cell(redact(r.get("error") or "", env)),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    if "run_log" in run:
        counts = run["run_log"]
        lines += ["", "pipeline_run: skipped (--no-run-log)" if counts is None
                  else f"pipeline_run: {counts['writes']} writes, {counts['failed']} failed"]
    with open(path, "a") as fh:
        fh.write("\n".join(lines) + "\n\n")


def _end_arg(value, now=None):
    try:
        slot_of(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--end must look like 2026-10-24T14:00:00Z, got {value!r}")
    now = datetime.now(timezone.utc) if now is None else now
    if datetime.strptime(value, _TS_FMT).replace(tzinfo=timezone.utc) > _utc(now):
        # a future slot has no weather: it would store static-fallback rows under a future valid_time
        raise argparse.ArgumentTypeError(f"--end must not be in the future, got {value!r}")
    return value


def _positive_int(value):
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"must be a whole number of seconds, got {value!r}") from None
    if number < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1 second, got {value!r}")
    return number


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run every city's live DLR pipeline, one child process each.")
    parser.add_argument("--cities", nargs="*", choices=config.LOCATIONS, default=None,
                        help="default: every city in config.LOCATIONS")
    parser.add_argument("--end", type=_end_arg, default=None,
                        help="window end (default: now floored to 5 minutes); for re-running a missed slot")
    parser.add_argument("--timeout-s", type=_positive_int, default=CITY_TIMEOUT_S,
                        help="per-city child time budget in seconds")
    parser.add_argument("--fault-city", default=os.environ.get("DLR_LIVE_FAULT_CITY", ""),
                        help="drill only: run this city with its provider credentials blanked "
                             "(default: $DLR_LIVE_FAULT_CITY)")
    parser.add_argument("--summary-json", help="write the whole run record as JSON to this path")
    parser.add_argument("--no-run-log", action="store_true",
                        help="local dry runs only: do not write the pipeline_run row "
                             "(the scheduled workflow never passes this)")
    args = parser.parse_args(argv)
    if args.fault_city and args.fault_city not in config.LOCATIONS:
        parser.error(f"--fault-city must be empty or one of {list(config.LOCATIONS)}, got {args.fault_city!r}")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    missing = [name for name in REQUIRED_ENV if not (os.environ.get(name) or "").strip()]
    if missing:
        # names only, never values
        log.error("required environment variables are unset or empty: %s", ", ".join(missing))
        return 1

    run = run_live(cities=args.cities, end=args.end, fault_city=args.fault_city,
                   timeout_s=args.timeout_s, record_run=not args.no_run_log)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        write_step_summary(run, summary_path)
    if args.summary_json:
        with open(args.summary_json, "w") as fh:
            json.dump(run, fh, indent=2)
    return run["exit_code"]


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
