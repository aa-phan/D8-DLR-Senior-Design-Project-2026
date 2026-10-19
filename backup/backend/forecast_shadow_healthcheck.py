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
    0  every city in `config.LOCATIONS` has at least one log entry within
       `--max-age-minutes` (default 1440 = 24h, generous for a
       once-or-twice-daily schedule; override for a tighter cadence).
    1  at least one city's most recent entry is older than that, or
       has no log file at all yet -- the scheduler is not running, or
       has not run successfully recently.

Legacy corridor-era logs (`AUSTIN_CORPUS_CHRISTI.jsonl`,
`MIDLAND_EL_PASO.jsonl`) are never consulted and can neither pass nor fail
the check; a city's own log is also read tolerantly (malformed or legacy
rows are skipped, so one bad trailing line cannot crash the check).

Prints one line per city: last entry's `logged_at`, its age, and
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


def _last_entry(city: str) -> dict | None:
    """
    The positionally-last usable entry in `{CITY}.jsonl`: a JSON object
    keyed by this `city` with a `logged_at` timestamp. Malformed lines and
    legacy/other-city rows are skipped, never raised on.
    """
    path = os.path.join(PREDICTIONS_DIR, f"{city}.jsonl")
    if not os.path.exists(path):
        return None
    last = None
    with open(path, "r") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict) or entry.get("city") != city:
                continue
            if not isinstance(entry.get("logged_at"), str):
                continue
            last = entry
    return last


def check(max_age_minutes: int) -> int:
    now = datetime.now(timezone.utc)
    max_age = timedelta(minutes=max_age_minutes)
    unhealthy = False
    for city in config.LOCATIONS:
        entry = _last_entry(city)
        if entry is None:
            print(f"[UNHEALTHY] {city}: no log entries at all")
            unhealthy = True
            continue
        try:
            logged_at = datetime.fromisoformat(entry["logged_at"])
        except ValueError:
            print(f"[UNHEALTHY] {city}: last entry has an unparseable logged_at {entry['logged_at']!r}")
            unhealthy = True
            continue
        if logged_at.tzinfo is None:
            logged_at = logged_at.replace(tzinfo=timezone.utc)
        age = now - logged_at
        status = "fallback" if entry.get("fallback_used") else "corrected"
        if age > max_age:
            print(f"[UNHEALTHY] {city}: last entry {age} ago ({status}) -- exceeds {max_age} threshold")
            unhealthy = True
        else:
            print(f"[OK] {city}: last entry {age} ago ({status})")
    return 1 if unhealthy else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-age-minutes", type=int, default=1440)
    args = parser.parse_args()
    sys.exit(check(args.max_age_minutes))
