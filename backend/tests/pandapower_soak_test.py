"""
OPS-05 proofs of the 24-slot soak count `pandapower_job.soak` (pandapower-solver workstream,
phase 5, plan 05-02, decision D-04).

The count is the number of consecutive complete UTC hours, counting back from the hour before the
database's current hour, in which the pandapower solver has at least one run that is not failed.
It must agree with an independent plain-loop oracle on 300 seeded histories, and with the existing
per-solver gap check `psse_job.gaps.compute_gaps`: the counted hours are not gaps there, and the
hour before them is.

Pure Python, nothing skipped: the function takes plain tuples, so no database and no pandapower
are needed. Follows backend/tests/psse_gaps_solver_test.py (module-level functions, plain asserts).
"""

import ast
import datetime
import os
import random
import sys

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from pandapower_job import soak  # noqa: E402
from psse_job import gaps  # noqa: E402

HOUR = datetime.timedelta(hours=1)
UTC = datetime.timezone.utc
H = datetime.datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)  # the database's current hour in these tests
PP = "pandapower"
PSSE = "psse"


def _ok_run(first_back, last_back, solver=PP, outcome="ok"):
    """One row per hour from H - first_back hours down to H - last_back hours (first_back >= last_back)."""
    return [(H - n * HOUR, solver, outcome) for n in range(last_back, first_back + 1)]


# --------------------------------------------------------------------------- the tracer


def test_tracer_exactly_24_consecutive_slots_pass():
    rows = _ok_run(24, 1)
    count = soak.trailing_slots(rows, H, PP)
    assert count == soak.SoakCount(24, 0)
    assert soak.soak_passed(count)
    assert soak.SOAK_SLOTS == 24
    # one hour short, with a missing hour before them, does not pass
    short = soak.trailing_slots(_ok_run(23, 1), H, PP)
    assert short == soak.SoakCount(23, 0)
    assert not soak.soak_passed(short)


# --------------------------------------------------------------------------- hand cases


def test_hand_cases():
    # 23 hours and none at H-24h: 23, not passed; the hour before the run is empty
    rows = _ok_run(23, 1) + [(H - 25 * HOUR, PP, "ok")]
    count = soak.trailing_slots(rows, H, PP)
    assert count.slots == 23 and not soak.soak_passed(count)
    # 30 consecutive hours count 30 and pass
    count = soak.trailing_slots(_ok_run(30, 1), H, PP)
    assert count.slots == 30 and soak.soak_passed(count)
    # no row at H-1h: zero, even when the 24 hours before it are full
    count = soak.trailing_slots(_ok_run(25, 2), H, PP)
    assert count == soak.SoakCount(0, 0) and not soak.soak_passed(count)
    # a failed-only hour at H-5h stops the count at 4
    rows = _ok_run(30, 1)
    rows = [r for r in rows if r[0] != H - 5 * HOUR] + [(H - 5 * HOUR, PP, "failed"), (H - 5 * HOUR, PP, "failed")]
    assert soak.trailing_slots(rows, H, PP).slots == 4
    # an hour with one failed and one ok row counts
    rows = [r for r in _ok_run(6, 1) if r[0] != H - 3 * HOUR] + [(H - 3 * HOUR, PP, "failed"), (H - 3 * HOUR, PP, "ok")]
    assert soak.trailing_slots(rows, H, PP).slots == 6
    # a PSS/E row at an hour with no pandapower row does not count for pandapower
    rows = [r for r in _ok_run(10, 1) if r[0] != H - 4 * HOUR] + [(H - 4 * HOUR, PSSE, "ok")]
    assert soak.trailing_slots(rows, H, PP).slots == 3
    assert soak.trailing_slots(rows, H, PSSE).slots == 0
    # a PSS/E row in an hour that also has a failed pandapower row does not rescue it
    rows = [(H - 1 * HOUR, PP, "ok"), (H - 2 * HOUR, PP, "failed"), (H - 2 * HOUR, PSSE, "ok"), (H - 3 * HOUR, PP, "ok")]
    assert soak.trailing_slots(rows, H, PP).slots == 1
    # rows labelled `Pandapower` are not a plain tag: they are `unknown`, never `pandapower`
    rows = [(H - n * HOUR, "Pandapower", "ok") for n in range(1, 6)]
    assert soak.trailing_slots(rows, H, PP).slots == 0
    assert soak.trailing_slots(rows, H, "unknown").slots == 5
    rows = [(H - 1 * HOUR, None, "ok"), (H - 2 * HOUR, "a" * 33, "ok")]
    assert soak.trailing_slots(rows, H, PP).slots == 0
    assert soak.trailing_slots(rows, H, "unknown").slots == 2
    # rows only in the current hour, or in a later hour, give zero; an empty list gives zero
    assert soak.trailing_slots([(H, PP, "ok")], H, PP).slots == 0
    assert soak.trailing_slots([(H + HOUR, PP, "ok"), (H + 2 * HOUR, PP, "ok")], H, PP).slots == 0
    assert soak.trailing_slots([], H, PP) == soak.SoakCount(0, 0)
    # rows in the current hour and later never add to a run that already exists
    rows = _ok_run(5, 1) + [(H, PP, "ok"), (H + HOUR, PP, "ok")]
    assert soak.trailing_slots(rows, H, PP).slots == 5


def test_fallback_slots_are_counted():
    # hours 1..6 back: 2 and 5 are fallback-only; 3 has one ok and one fallback row (not a fallback slot)
    rows = [
        (H - 1 * HOUR, PP, "ok"),
        (H - 2 * HOUR, PP, "fallback"),
        (H - 3 * HOUR, PP, "ok"), (H - 3 * HOUR, PP, "fallback"),
        (H - 4 * HOUR, PP, "ok"),
        (H - 5 * HOUR, PP, "fallback"), (H - 5 * HOUR, PP, "fallback"),
        (H - 6 * HOUR, PP, "ok"),
    ]
    assert soak.trailing_slots(rows, H, PP) == soak.SoakCount(6, 2)
    # a fallback hour beyond the broken hour is not part of the run, so it is not counted
    rows = [(H - 1 * HOUR, PP, "fallback"), (H - 3 * HOUR, PP, "fallback")]
    assert soak.trailing_slots(rows, H, PP) == soak.SoakCount(1, 1)
    # a fallback hour with a failed row alongside is still a fallback slot
    rows = [(H - 1 * HOUR, PP, "fallback"), (H - 1 * HOUR, PP, "failed")]
    assert soak.trailing_slots(rows, H, PP) == soak.SoakCount(1, 1)


def test_timezone_normalisation_matches_the_gap_check():
    naive_h = H.replace(tzinfo=None)
    plus5 = datetime.timezone(datetime.timedelta(hours=5))
    minus7 = datetime.timezone(datetime.timedelta(hours=-7))
    samples = [
        naive_h,
        H,
        H.astimezone(plus5),
        H.astimezone(minus7),
        (H - 3 * HOUR).astimezone(plus5),
        (H - 3 * HOUR).replace(tzinfo=None),
    ]
    for value in samples:
        assert soak._utc(value) == gaps._utc(value)
        assert soak._utc(value).tzinfo is not None
    # naive rows are UTC, aware rows in another zone are converted, and so is the current hour
    rows = [
        (naive_h - 1 * HOUR, PP, "ok"),
        ((H - 2 * HOUR).astimezone(plus5), PP, "ok"),
        ((H - 3 * HOUR).astimezone(minus7), PP, "ok"),
        ((H - 4 * HOUR), PP, "failed"),
    ]
    for current in (H, naive_h, H.astimezone(plus5), H.astimezone(minus7)):
        assert soak.trailing_slots(rows, current, PP).slots == 3
        assert gaps.compute_gaps(rows, current)[PP] == [gaps.GapRow(H - 4 * HOUR, "failed_only", 1, 1)]


# --------------------------------------------------------------------------- the oracle and the gap check


def reference_trailing(rows, current, solver):
    """
    The independent oracle: for k from 1 to 200, scan the whole row list for rows of `solver` at
    the hour `current` minus k hours; stop at the first hour with no qualifying row. Returns
    (slots, fallback_slots). Plain loops, no grouping, no helper from the module.
    """
    slots = 0
    fallback = 0
    for k in range(1, 201):
        hour = current - k * HOUR
        has_good = False
        has_ok = False
        for slot, name, outcome in rows:
            if slot == hour and name == solver:
                if outcome != "failed":
                    has_good = True
                if outcome == "ok":
                    has_ok = True
        if not has_good:
            break
        slots += 1
        if not has_ok:
            fallback += 1
    return slots, fallback


def _random_rows(rng):
    """
    With probability 0.3 a run of 20 to 40 consecutive pandapower hours ending at H-1h with
    occasional holes, failed rows and PSS/E rows mixed in; otherwise 0 to 40 scattered rows.
    """
    rows = []
    if rng.random() < 0.3:
        length = rng.randint(20, 40)
        for n in range(1, length + 1):
            roll = rng.random()
            if roll < 0.015:
                continue  # a hole: no pandapower row at this hour
            if roll < 0.03:
                rows.append((H - n * HOUR, PP, "failed"))  # a failed-only hour
                continue
            rows.append((H - n * HOUR, PP, rng.choice(["ok", "ok", "fallback"])))
            if rng.random() < 0.15:
                rows.append((H - n * HOUR, PP, rng.choice(["ok", "fallback", "failed"])))
            if rng.random() < 0.2:
                rows.append((H - n * HOUR, PSSE, rng.choice(["ok", "fallback", "failed"])))
        if rng.random() < 0.3:
            rows.append((H, PP, "ok"))  # a row in the current hour
    else:
        for _ in range(rng.randint(0, 40)):
            back = rng.randint(0, 30)
            solver = rng.choice([PP, PP, PSSE, "Pandapower"])
            rows.append((H - back * HOUR, solver, rng.choice(["ok", "fallback", "failed"])))
        if rng.random() < 0.4:
            # a short chain from the last hour, so many scattered histories end between 1 and 23
            for n in range(1, rng.randint(1, 12) + 1):
                rows.append((H - n * HOUR, PP, rng.choice(["ok", "fallback"])))
    rng.shuffle(rows)
    return rows


def test_matches_the_oracle_on_300_histories():
    rng = random.Random(20261125)
    reached = 0
    partial = 0
    fallback_seen = 0
    for _ in range(300):
        rows = _random_rows(rng)
        count = soak.trailing_slots(rows, H, PP)
        expected = reference_trailing(rows, H, PP)
        assert (count.slots, count.fallback_slots) == expected
        assert soak.soak_passed(count) == (expected[0] >= 24)
        reached += count.slots >= 24
        partial += 1 <= count.slots <= 23
        fallback_seen += count.fallback_slots > 0
    # the histories really do reach the threshold and fall short of it, so the comparison is not vacuous
    assert reached >= 30
    assert partial >= 50
    assert fallback_seen >= 20


def test_agrees_with_the_per_solver_gap_check():
    rng = random.Random(20261125)
    checked_before = 0
    for _ in range(300):
        rows = _random_rows(rng)
        count = soak.trailing_slots(rows, H, PP)
        result = gaps.compute_gaps(rows, H)
        mine = [slot for slot, name, _ in rows if name == PP]
        if not mine:
            assert PP not in result
            assert count.slots == 0
            continue
        gap_hours = {gap.slot_time for gap in result[PP]}
        # no counted hour is a gap
        for k in range(1, count.slots + 1):
            assert H - k * HOUR not in gap_hours
        # the hour before the run is a gap whenever the solver's own walk reaches it
        before = H - (count.slots + 1) * HOUR
        if min(mine) <= before:
            assert before in gap_hours
            checked_before += 1
        else:
            assert before not in gap_hours
    assert checked_before >= 100


# --------------------------------------------------------------------------- the import rule


def test_soak_module_imports_only_the_standard_library():
    path = os.path.join(_BACKEND, "pandapower_job", "soak.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "no relative import"
            imported.add((node.module or "").split(".")[0])
    assert imported, "the module imports something"
    stdlib = set(sys.stdlib_module_names)
    assert imported <= stdlib, sorted(imported - stdlib)
    assert imported <= {"collections", "datetime", "re"}, sorted(imported)
