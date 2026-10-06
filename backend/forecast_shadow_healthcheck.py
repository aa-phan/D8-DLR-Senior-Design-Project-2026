"""
Health check for the scheduled `forecast_shadow_collect.py` collector
(2026-10-06 pass, "finish the persistent-collection deployment setup").

Not invoked by `dlr_pipeline.py` or any other production caller -- same
inertness discipline as the rest of this shadow prototype. Meant to be
polled by a human or a monitoring system, separately from the collector
itself, so a silently-stopped scheduler is visible without reading log
files by hand.

Runnable today, by hand:

    PYTHONPATH=backend .venv/bin/python3.12 backend/forecast_shadow_healthcheck.py

Exit codes:
    0  every corridor has at least one log entry within
       `--max-age-minutes` (default 1440 = 24h, generous for a
       once-or-twice-daily schedule; override for a tighter cadence).
    1  at least one corridor's most recent entry is older than that, or
       has no log file at all yet -- the scheduler is not running, or
       has not run successfully recently.

Prints one line per corridor: last entry's `logged_at`, its age, and
whether that entry was a fallback (fallback_used=True) or a genuine
corrected prediction -- an all-fallback run is NOT reported as unhealthy
by this script (a station gap is an expected, logged condition per
`forecast_shadow_collect.py`'s own exit-code contract, not a scheduler
failure); this check only answers "is the collector still running," not
"is every input source currently available."
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import config

PREDICTIONS_DIR = os.path.join("data", "shadow", "predictions")


def _last_entry(corridor: str) -> dict | None:
    path = os.path.join(PREDICTIONS_DIR, f"{corridor}.jsonl")
    if not os.path.exists(path):
        return None
    last = None
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if line:
                last = line
    if last is None:
        return None
    return json.loads(last)


def check(max_age_minutes: int) -> int:
    now = datetime.now(timezone.utc)
    max_age = timedelta(minutes=max_age_minutes)
    unhealthy = False
    for corridor in config.CORRIDOR_ENDPOINTS:
        entry = _last_entry(corridor)
        if entry is None:
            print(f"[UNHEALTHY] {corridor}: no log entries at all")
            unhealthy = True
            continue
        logged_at = datetime.fromisoformat(entry["logged_at"])
        age = now - logged_at
        status = "fallback" if entry.get("fallback_used") else "corrected"
        if age > max_age:
            print(f"[UNHEALTHY] {corridor}: last entry {age} ago ({status}) -- exceeds {max_age} threshold")
            unhealthy = True
        else:
            print(f"[OK] {corridor}: last entry {age} ago ({status})")
    return 1 if unhealthy else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-age-minutes", type=int, default=1440)
    args = parser.parse_args()
    sys.exit(check(args.max_age_minutes))
