"""
The 24-slot soak count (OPS-05; decisions D-04, D-09, D-12 of the pandapower-solver workstream,
phase 5).

The count is the number of consecutive complete UTC hours, counting back from the hour before the
database's current hour, in which the pandapower solver has at least one run whose outcome is not
`failed`. It passes at 24 or more (`soak_passed`). Any missed hour (no run, or only failed runs)
ends the walk, so the count restarts from the next good hour and nothing is stored between calls.

Why the walk starts at the hour before the current hour: the per-solver gap check
(`psse_job.gaps.compute_gaps`) never walks the current hour, so the same rule is used here. The
24th slot therefore first shows on the run made 24 hours after the first live run, which is the
25th run.

Fallback hours: an hour whose only non-failed runs are `fallback` still counts toward the soak, and
`SoakCount.fallback_slots` says how many of the counted hours were like that, so the soak line can
show them (D-12).

Only the standard library is imported, so the hourly dry path that imports this module loads no
writer-side module (D-10). The hourly runner gets the rows from `gaps.fetch_runs` and the hour from
`gaps.fetch_current_slot`; this module does no database access and prints nothing.
"""

import collections
import datetime
import re

SOAK_SLOTS = 24

SoakCount = collections.namedtuple("SoakCount", ["slots", "fallback_slots"])

_HOUR = datetime.timedelta(hours=1)
_SOLVER_LABEL = re.compile(r"[a-z][a-z0-9_]{0,31}")
_UNKNOWN_SOLVER = "unknown"


def _utc(value):
    """Same rule as `gaps._utc`: a naive datetime is taken as UTC, an aware one is converted."""
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def _label(value):
    """Same rule as `gaps._solver_label`: a plain tag unchanged, anything else `unknown`."""
    if isinstance(value, str) and _SOLVER_LABEL.fullmatch(value):
        return value
    return _UNKNOWN_SOLVER


def trailing_slots(runs, current_slot, solver):
    """
    `SoakCount(slots, fallback_slots)` for `solver`. `runs` holds (slot_time, solver, outcome)
    tuples, `current_slot` is the database's current UTC hour. Starting at the hour before
    `current_slot`, each hour that has at least one run of `solver` whose outcome is not `failed`
    adds one to `slots` (and one to `fallback_slots` when none of its runs is `ok`); the first hour
    that does not stops the count. Rows in the current hour or later are never counted, and another
    solver's rows never fill an hour.
    """
    by_slot = {}
    for slot, name, outcome in runs:
        if _label(name) == solver:
            by_slot.setdefault(_utc(slot), []).append(outcome)
    slots = 0
    fallback_slots = 0
    hour = _utc(current_slot) - _HOUR
    while True:
        outcomes = by_slot.get(hour)
        if outcomes is None or all(outcome == "failed" for outcome in outcomes):
            break
        slots += 1
        if "ok" not in outcomes:
            fallback_slots += 1
        hour -= _HOUR
    return SoakCount(slots, fallback_slots)


def soak_passed(count):
    """True when `count` (a `SoakCount`) holds at least `SOAK_SLOTS` consecutive hours."""
    return count.slots >= SOAK_SLOTS
