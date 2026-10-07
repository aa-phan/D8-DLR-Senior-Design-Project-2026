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

Exit codes (for a cron/launchd wrapper to alert on):
    0  every corridor was attempted and logged something (a non-fallback
       prediction, a fallback prediction, or a result -- `run_once`
       itself never lets a retrieval/model/anchor failure escape
       uncaught; see `forecast_shadow_pipeline.ShadowPipeline.predict`).
    1  a hard failure escaped `run_once` for at least one corridor
       (a bug, not an expected fallback condition) -- see stderr.
    2  skipped entirely: another invocation already holds the lock
       (duplicate-run protection -- see `_acquire_lock`). This is NOT a
       failure; a scheduler should not alert on exit code 2 unless it
       persists across many consecutive scheduled runs (which would
       indicate a previous run hung rather than completed).
"""
from __future__ import annotations

import fcntl
import os
import sys
import time
import traceback

import config
import forecast_shadow_demo

_LOCK_PATH = os.path.join("data", "shadow", ".collect.lock")

# INTER_CORRIDOR_DELAY_S: a pause between corridors' live-provider requests.
# Confirmed, not just hypothesized (2026-10-07): a one-off diagnostic run
# that reversed corridor processing order made the SECOND corridor fail and
# the first succeed, regardless of which corridor was which -- this is
# purely position-dependent (always whichever request goes second), not
# specific to either corridor or location. The exact real request (same
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
INTER_CORRIDOR_DELAY_S: float = 15.0


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


def collect_once() -> int:
    lock = _acquire_lock()
    if lock is None:
        print(f"forecast_shadow_collect: lock {_LOCK_PATH!r} held by another "
              f"process -- skipping this invocation (duplicate-run protection)", file=sys.stderr)
        return 2

    try:
        hard_failure = False
        for i, corridor in enumerate(config.CORRIDOR_ENDPOINTS):
            if i > 0:
                # Only between corridors, never before the first -- see
                # INTER_CORRIDOR_DELAY_S's own docstring for why this exists.
                time.sleep(INTER_CORRIDOR_DELAY_S)
            try:
                forecast_shadow_demo.run_once(corridor, "ml_wind_corrected")
            except Exception:
                # A failure HERE means something escaped run_once's own
                # try/except entirely (a real bug) -- the expected
                # fallback path for a missing anchor/model/forecast
                # source is already caught and logged inside run_once /
                # ShadowPipeline.predict. This is the failure-reporting
                # path a cron wrapper's exit-code check is for.
                hard_failure = True
                print(f"forecast_shadow_collect: hard failure for corridor {corridor!r}:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
        return 1 if hard_failure else 0
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(collect_once())
