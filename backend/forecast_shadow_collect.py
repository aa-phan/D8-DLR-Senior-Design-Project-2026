"""
Scheduler-ready collection entry point for the experimental shadow
prototype (2026-10-06, "make collection repeatable").

Not invoked by `dlr_pipeline.py` or any other production caller -- same
inertness discipline as `forecast_shadow_pipeline.py`/`forecast_shadow_demo.py`.
This script is meant to be invoked by an EXTERNAL scheduler (cron,
launchd, a hosted job runner) on a recurring interval; it is not itself a
scheduler and holds no persistent state between invocations other than
the lock file and the append-only prediction logs.

Runnable today, by hand:

    PYTHONPATH=backend .venv/bin/python3 backend/forecast_shadow_collect.py

Process model (2026-10-13): each city runs in its OWN child process
(`python backend/forecast_shadow_collect.py --city CITY`, spawned by
`_run_city_subprocess`), one after another, with `INTER_CITY_DELAY_S` between
them. The parent holds the lock and aggregates exit codes; a child takes no
lock of its own. Rationale: on GitHub-hosted runners the second and later
`single-runs-api.open-meteo.com` requests inside one Python process timed out
position-dependently (first city ok, later cities `unavailable`) even with
`Connection: close` on that call, while the identical request from a fresh
process succeeded every time. A fresh process per city gives every city a
fresh interpreter, connection state and TLS session. `--city` is also usable
by hand to collect ONE city, but it takes NO lock, so do not run it while the
scheduled collector may be running.

Exit codes (for a cron/launchd wrapper to alert on):
    0  every city in `config.LOCATIONS` (all four) was attempted and logged something (all five
       candidates' results, each independently ok/fallback/unavailable/
       failed -- `run_once_all_methods` itself never lets a retrieval/
       model/anchor failure escape uncaught; see
       `forecast_shadow_pipeline.ShadowPipeline.predict`).
    1  a hard failure escaped `run_once_all_methods` for at least one
       city (a bug, not an expected fallback/unavailable condition
       for any individual candidate) -- see stderr. A city's child process
       exiting non-zero counts as a hard failure.
       A child killed for exceeding `CITY_TIMEOUT_S` is NOT a hard failure
       (it is an environmental stall, not a bug): it is reported loudly on
       stderr, the other cities are unaffected, and the run still exits 0 so
       the other cities' logs are committed; the health check flags a city
       whose log stops advancing.
    2  skipped entirely: another invocation already holds the lock
       (duplicate-run protection -- see `_acquire_lock`). This is NOT a
       failure; a scheduler should not alert on exit code 2 unless it
       persists across many consecutive scheduled runs (which would
       indicate a previous run hung rather than completed).
"""
from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
import time
import traceback

import config
import forecast_shadow_demo

_LOCK_PATH = os.path.join("data", "shadow", ".collect.lock")

# INTER_CITY_DELAY_S: a pause between cities' live-provider requests.
# Confirmed, not just hypothesized (2026-10-07, when the unit was a
# two-corridor cycle): a one-off diagnostic run that reversed processing
# order made the SECOND unit fail and the first succeed, regardless of
# which one was which -- this is purely position-dependent (always
# whichever request goes second), not specific to any corridor, city or
# location. The exact real request (same
# run, same params) succeeds in well under a second when issued directly
# from a non-CI machine, so this is not a defect in the request itself or
# in Open-Meteo's run availability. Leading hypothesis: a per-IP rate limit
# on Open-Meteo's side, triggered by GitHub-hosted runners' shared outbound
# IP pool. 15.0s was tried and measured INSUFFICIENT -- the second request
# still timed out with this delay in place, so whatever throttling window
# is in effect is longer than 15s (or a fixed delay isn't the right fix at
# all, e.g. a retry-with-backoff might be needed instead). Do not assume
# a larger number here is automatically correct without measuring it the
# same way this value was tested.
INTER_CITY_DELAY_S: float = 15.0

# CITY_TIMEOUT_S: wall-clock cap for ONE city's child process. A degraded
# city (every provider call timing out and retrying) has been measured at
# roughly 7 minutes in the worst case; the GitHub Actions job allows 30
# minutes for four cities plus pauses, so a stuck child must be killed rather
# than allowed to consume the whole job and lose every city's logs.
CITY_TIMEOUT_S: float = 360.0


def _acquire_lock():
    """
    Exclusive, non-blocking file lock -- the duplicate-run protection a
    real cron/launchd wrapper needs: if a previous invocation is still
    running (a slow network call, a hung process) when the next
    scheduled invocation fires, this one skips rather than racing the
    first for the same append-only log files or double-logging the same
    decision_time.

    Returns an open file handle to keep the lock held for the process's
    lifetime (closing/exiting releases it), or None if the lock is
    already held by another process.
    """
    os.makedirs(os.path.dirname(_LOCK_PATH), exist_ok=True)
    fh = open(_LOCK_PATH, "w")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        fh.close()
        return None
    fh.write(str(os.getpid()))
    fh.flush()
    return fh


def _run_city_subprocess(city: str) -> int:
    """
    Run one city's full five-candidate cycle in a FRESH child process and
    return its exit code. Raises `subprocess.TimeoutExpired` (after killing
    the child) if it exceeds `CITY_TIMEOUT_S`. stdout/stderr are inherited so
    the child's log lines stream into the parent's (and CI's) output.
    """
    cmd = [sys.executable, os.path.abspath(__file__), "--city", city]
    return subprocess.run(cmd, timeout=CITY_TIMEOUT_S).returncode


def collect_city(city: str) -> int:
    """
    Child-process body: collect ONE city in this process. Returns 0, or 1 if
    a hard failure escaped `run_once_all_methods` (printed to stderr). Takes
    no lock -- the parent `collect_once` holds it.
    """
    try:
        forecast_shadow_demo.run_once_all_methods(city)
    except Exception:
        # A failure HERE means something escaped run_once_all_methods's own
        # try/except entirely (a real bug) -- each of the five candidates'
        # own expected fallback/unavailable/failed paths is already caught
        # and logged inside run_once_all_methods / ShadowPipeline.predict.
        print(f"forecast_shadow_collect: hard failure for city {city!r}:", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1
    return 0


def collect_once() -> int:
    lock = _acquire_lock()
    if lock is None:
        print(f"forecast_shadow_collect: lock {_LOCK_PATH!r} held by another "
              f"process -- skipping this invocation (duplicate-run protection)", file=sys.stderr)
        return 2

    try:
        hard_failure = False
        for i, city in enumerate(config.LOCATIONS):
            if i > 0:
                # Only between cities, never before the first -- see
                # INTER_CITY_DELAY_S's own comment for why this exists.
                time.sleep(INTER_CITY_DELAY_S)
            try:
                returncode = _run_city_subprocess(city)
            except subprocess.TimeoutExpired:
                print(f"forecast_shadow_collect: city {city!r} exceeded "
                      f"{CITY_TIMEOUT_S:.0f}s and its child process was killed -- "
                      f"no prediction was logged for it this cycle; continuing with "
                      f"the remaining cities", file=sys.stderr)
                continue
            if returncode != 0:
                hard_failure = True
                print(f"forecast_shadow_collect: city {city!r} child process exited "
                      f"with code {returncode}", file=sys.stderr)
        return 1 if hard_failure else 0
    finally:
        lock.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shadow forecast collector (one child process per city).")
    parser.add_argument(
        "--city", choices=sorted(config.LOCATIONS), default=None,
        help="Collect only this city, in this process, WITHOUT taking the lock "
             "(used by the parent collector's per-city child processes).",
    )
    args = parser.parse_args(argv)
    if args.city is not None:
        return collect_city(args.city)
    return collect_once()


if __name__ == "__main__":
    sys.exit(main())
