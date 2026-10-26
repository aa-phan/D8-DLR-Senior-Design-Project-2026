"""
Offline tests for backend/dlr_live_window_check.py (production-pipeline Phase 5,
SCHED-01 evidence for ROADMAP success criterion 2, SCHED-02 measured minutes).

`evaluate_window` is pure, so every behaviour is driven by fixture runs (the shape
`gh run list --json` returns), pipeline_run dicts and city_rating dicts: no gh, no
database. `fetch_rows` is checked against a stub connection.
"""

from datetime import datetime, timedelta, timezone

import pytest

import config
import dlr_live_window_check as wc

START = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)
CITIES = list(config.LOCATIONS)
BASE_ID = 7000


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def slot(i):
    return START + timedelta(hours=i)


def gh_run(run_id, started, conclusion="success", seconds=290, event="workflow_dispatch"):
    """A `gh run list` dict: started at `started`, last updated `seconds` later."""
    return {
        "databaseId": run_id,
        "createdAt": _iso(started - timedelta(seconds=5)),
        "startedAt": _iso(started),
        "updatedAt": _iso(started + timedelta(seconds=seconds)),
        "status": "completed" if conclusion else "in_progress",
        "conclusion": conclusion,
        "event": event,
        "attempt": 1,
    }


def run_row(run_id, window_end, cities_ok=None, cities_failed=None):
    return {
        "run_id": str(run_id),
        "run_attempt": 1,
        "window_end": window_end,
        "cities_ok": list(CITIES) if cities_ok is None else cities_ok,
        "cities_failed": cities_failed or {},
        "finished_at": window_end + timedelta(minutes=4),
    }


def rating_rows(run_id, valid_time, cities=None):
    return [{"city": c, "valid_time": valid_time, "run_id": str(run_id)} for c in (cities or CITIES)]


def healthy_window(hours=24):
    """One successful run per slot at hh:05, with its run row and four rating rows."""
    runs, rows, ratings = [], [], []
    for i in range(hours):
        rid = BASE_ID + i
        end = slot(i) + timedelta(minutes=5)
        runs.append(gh_run(rid, end + timedelta(seconds=20)))
        rows.append(run_row(rid, end))
        ratings.extend(rating_rows(rid, slot(i)))
    return runs, rows, ratings


def verdicts(result):
    return [s["verdict"] for s in result["slots"]]


def test_full_window_of_successful_runs_passes():
    runs, rows, ratings = healthy_window()

    result = wc.evaluate_window(runs, rows, ratings, START)

    assert len(result["slots"]) == 24
    assert verdicts(result) == ["ok"] * 24
    assert result["passed"] is True
    assert result["slots"][0]["slot"] == "2026-10-25T00:00:00Z"
    assert result["slots"][23]["slot"] == "2026-10-25T23:00:00Z"
    assert result["slots"][5]["run_ids"] == [str(BASE_ID + 5)]
    assert result["slots"][5]["conclusions"] == ["success"]
    assert result["minutes"]["count"] == 24

    # the same call with an explicit hour count and an ISO start gives the same verdicts
    again = wc.evaluate_window(runs, rows, ratings, "2026-10-25T00:00:00Z", hours=24)
    assert verdicts(again) == verdicts(result)

    # adjacency edges: runs one slot before the first and at the slot after the last belong to
    # neither window slot (they must not wrap onto slot 23 or change any count)
    for offset, rid in ((-1, BASE_ID + 900), (24, BASE_ID + 901)):
        end = slot(offset) + timedelta(minutes=5)
        runs.append(gh_run(rid, end + timedelta(seconds=20)))
        rows.append(run_row(rid, end))
        ratings.extend(rating_rows(rid, slot(offset)))
    edged = wc.evaluate_window(runs, rows, ratings, START)
    assert verdicts(edged) == ["ok"] * 24
    assert edged["slots"][23]["run_ids"] == [str(BASE_ID + 23)]
    assert edged["slots"][0]["run_ids"] == [str(BASE_ID)]
    assert edged["minutes"]["count"] == 24

    # a second successful run in a slot (a manual dispatch that listed only some cities) does not
    # undo the slot: one fully good run is enough
    extra = BASE_ID + 910
    end = slot(10) + timedelta(minutes=40)
    runs.append(gh_run(extra, end + timedelta(seconds=20)))
    rows.append(run_row(extra, end, cities_ok=CITIES[:2]))
    assert wc.evaluate_window(runs, rows, ratings, START)["slots"][10]["verdict"] == "ok"


@pytest.mark.parametrize("conclusion", ["failure", "timed_out", "cancelled", "startup_failure"])
def test_red_runs_count_as_visible_failures(conclusion):
    runs, rows, ratings = healthy_window()
    # slot 7: replace the successful run, its run row and its rating rows with a red run
    rid = BASE_ID + 7
    runs[7] = gh_run(rid, slot(7) + timedelta(minutes=5, seconds=20), conclusion=conclusion)
    rows[7] = run_row(rid, slot(7) + timedelta(minutes=5), cities_ok=[], cities_failed={"AUSTIN": {"outcome": "error"}})
    ratings = [r for r in ratings if r["valid_time"] != slot(7)]

    result = wc.evaluate_window(runs, rows, ratings, START)

    assert result["slots"][7]["verdict"] == "failed-visible"
    assert result["slots"][7]["conclusions"] == [conclusion]
    assert [v for i, v in enumerate(verdicts(result)) if i != 7] == ["ok"] * 23
    assert result["passed"] is True


def test_a_fault_drill_run_does_not_stand_in_for_a_missed_slot():
    # WR-02: the drill always ends red; in an hour whose scheduled dispatch never happened it must
    # not turn 'missing' into 'failed-visible'
    runs, rows, ratings = healthy_window()
    del runs[7], rows[7]
    ratings = [r for r in ratings if r["valid_time"] != slot(7)]
    drill = BASE_ID + 700
    end = slot(7) + timedelta(minutes=30)
    runs.append(gh_run(drill, end + timedelta(seconds=20), conclusion="failure"))
    rows.append(run_row(drill, end, cities_ok=CITIES[1:],
                        cities_failed={CITIES[0]: {"outcome": "error", "fault_injected": True}}))

    result = wc.evaluate_window(runs, rows, ratings, START)

    assert result["slots"][7]["verdict"] == "missing"
    assert str(drill) not in result["slots"][7]["run_ids"]
    assert str(drill) in result["slots"][7]["note"]
    assert result["passed"] is False
    assert result["minutes"]["count"] == 24  # the drill still billed: 23 healthy runs plus the drill

    # a red run that is not a drill still counts as visible
    rows[-1] = run_row(drill, end, cities_ok=[], cities_failed={CITIES[0]: {"outcome": "error"}})
    again = wc.evaluate_window(runs, rows, ratings, START)
    assert again["slots"][7]["verdict"] == "failed-visible"
    assert again["passed"] is True


def test_a_fault_drill_in_a_good_slot_leaves_it_ok_even_when_it_overwrote_rating_rows():
    runs, rows, ratings = healthy_window()
    drill = BASE_ID + 701
    end = slot(4) + timedelta(minutes=45)
    runs.append(gh_run(drill, end + timedelta(seconds=20), conclusion="failure"))
    rows.append(run_row(drill, end, cities_ok=CITIES[1:],
                        cities_failed={CITIES[0]: {"outcome": "error", "fault_injected": True}}))
    # the drill's healthy cities overwrote the original run's rows (OD-7)
    ratings = [r for r in ratings if not (r["valid_time"] == slot(4) and r["city"] in CITIES[1:])]
    ratings += rating_rows(drill, slot(4), cities=CITIES[1:])

    result = wc.evaluate_window(runs, rows, ratings, START)

    assert result["slots"][4]["verdict"] == "ok"
    assert result["slots"][4]["run_ids"] == [str(BASE_ID + 4)]
    assert str(drill) in result["slots"][4]["note"]
    assert result["passed"] is True


def test_a_slot_with_no_run_fails_the_window():
    runs, rows, ratings = healthy_window()
    del runs[3], rows[3]
    ratings = [r for r in ratings if r["valid_time"] != slot(3)]

    result = wc.evaluate_window(runs, rows, ratings, START)

    assert result["slots"][3]["verdict"] == "missing"
    assert result["slots"][3]["run_ids"] == []
    assert result["passed"] is False
    assert [v for i, v in enumerate(verdicts(result)) if i != 3] == ["ok"] * 23
    # the report names the slot
    report = wc.format_report(result)
    assert "2026-10-25T03:00:00Z" in report
    assert "missing" in report


def test_a_successful_run_missing_a_city_is_incomplete():
    runs, rows, ratings = healthy_window()
    rows[9] = run_row(BASE_ID + 9, slot(9) + timedelta(minutes=5), cities_ok=CITIES[:3])
    ratings = [r for r in ratings if not (r["valid_time"] == slot(9) and r["city"] == CITIES[3])]

    result = wc.evaluate_window(runs, rows, ratings, START)

    assert result["slots"][9]["verdict"] == "incomplete"
    assert result["passed"] is False

    # four cities listed in cities_ok but a rating row absent is incomplete too
    runs2, rows2, ratings2 = healthy_window()
    ratings2 = [r for r in ratings2 if not (r["valid_time"] == slot(2) and r["city"] == CITIES[0])]
    assert wc.evaluate_window(runs2, rows2, ratings2, START)["slots"][2]["verdict"] == "incomplete"


def test_overwritten_rows_from_a_later_run_in_the_same_slot_still_pass():
    runs, rows, ratings = healthy_window()
    # a later drill run in slot 4 (red: its fault city failed) rewrote three cities' rows (OD-7)
    drill_id = BASE_ID + 500
    drill_end = slot(4) + timedelta(minutes=50)
    runs.append(gh_run(drill_id, drill_end + timedelta(seconds=20), conclusion="failure"))
    rows.append(run_row(drill_id, drill_end, cities_ok=CITIES[1:], cities_failed={CITIES[0]: {"outcome": "error"}}))
    for r in ratings:
        if r["valid_time"] == slot(4) and r["city"] in CITIES[1:]:
            r["run_id"] = str(drill_id)

    result = wc.evaluate_window(runs, rows, ratings, START)

    assert result["slots"][4]["verdict"] == "ok"
    assert sorted(result["slots"][4]["run_ids"]) == sorted([str(BASE_ID + 4), str(drill_id)])
    assert result["passed"] is True

    # rows whose run belongs to another slot do not count for this slot
    ratings2 = [dict(r) for r in ratings]
    for r in ratings2:
        if r["valid_time"] == slot(4):
            r["run_id"] = str(BASE_ID + 9)
    assert wc.evaluate_window(runs, rows, ratings2, START)["slots"][4]["verdict"] == "incomplete"


def test_empty_window_reports_every_slot_missing():
    result = wc.evaluate_window([], [], [], START)

    assert verdicts(result) == ["missing"] * 24
    assert result["passed"] is False
    assert result["minutes"]["count"] == 0
    assert result["minutes"]["median"] is None
    assert result["minutes"]["max"] is None
    assert result["minutes"]["projected_30d"] is None


def test_run_without_a_pipeline_run_row_is_placed_by_its_start_time():
    runs, rows, ratings = healthy_window()
    # slot 6: the run died before the runner wrote a pipeline_run row
    rid = BASE_ID + 6
    runs[6] = gh_run(rid, slot(6) + timedelta(minutes=5, seconds=30), conclusion="failure")
    del rows[6]
    ratings = [r for r in ratings if r["valid_time"] != slot(6)]
    # slot 8: a "successful" run with no pipeline_run row cannot show its cities, so it is incomplete
    rid8 = BASE_ID + 8
    del rows[7]  # rows list shifted by the deletion above: index 7 is now slot 8's row
    ratings = [r for r in ratings if r["valid_time"] != slot(8)]

    result = wc.evaluate_window(runs, rows, ratings, START)

    assert result["slots"][6]["verdict"] == "failed-visible"
    assert result["slots"][6]["run_ids"] == [str(rid)]
    assert result["slots"][8]["verdict"] == "incomplete"
    assert result["slots"][8]["run_ids"] == [str(rid8)]
    assert result["passed"] is False


def test_billed_minutes_round_up_per_run():
    runs = [
        gh_run(1, slot(0) + timedelta(minutes=5), seconds=61),
        gh_run(2, slot(1) + timedelta(minutes=5), seconds=300),
        gh_run(3, slot(2) + timedelta(minutes=5), seconds=301),
    ]

    result = wc.evaluate_window(runs, [], [], START)

    minutes = result["minutes"]
    assert minutes["count"] == 3
    assert minutes["max"] == 6  # 301 s rounds up to 6
    assert minutes["median"] == 5  # [2, 5, 6]
    assert minutes["projected_30d"] == 5 * 24 * 30

    assert wc.billed_minutes(gh_run(9, slot(0), seconds=60)) == 1
    assert wc.billed_minutes(gh_run(9, slot(0), seconds=1)) == 1
    assert wc.billed_minutes(gh_run(9, slot(0), seconds=0)) == 1  # a job bills at least one minute


class _Description:
    def __init__(self, name):
        self.name = name


class _Cursor:
    def __init__(self, names, rows):
        self.description = [_Description(n) for n in names]
        self._rows = rows

    def fetchall(self):
        return self._rows


class _StubConn:
    def __init__(self):
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if "pipeline_run" in sql:
            return _Cursor(
                ["run_id", "run_attempt", "window_end", "cities_ok", "cities_failed", "finished_at"],
                [("42", 1, slot(1) + timedelta(minutes=5), CITIES, {}, slot(1) + timedelta(minutes=9))],
            )
        return _Cursor(["city", "valid_time", "run_id"], [("AUSTIN", slot(1), "42")])

    def close(self):
        self.closed = True


def test_fetch_rows_binds_parameters():
    conn = _StubConn()
    hostile_start = START

    run_rows, ratings = wc.fetch_rows(hostile_start, 24, conn=conn)

    assert len(conn.calls) == 2
    for sql, params in conn.calls:
        assert sql.lstrip().lower().startswith("select")
        for word in ("insert", "update", "delete", "drop", "alter", "truncate"):
            assert word not in sql.lower().split()
        # values travel as bound parameters, never inside the SQL text
        assert isinstance(params, dict)
        assert params["start"] == START
        assert params["end"] == START + timedelta(hours=24)
        assert "2026" not in sql
        assert "%(start)s" in sql and "%(end)s" in sql
    assert any("public.pipeline_run" in sql for sql, _ in conn.calls)
    assert any("public.city_rating" in sql for sql, _ in conn.calls)

    assert run_rows == [{
        "run_id": "42", "run_attempt": 1, "window_end": slot(1) + timedelta(minutes=5),
        "cities_ok": CITIES, "cities_failed": {}, "finished_at": slot(1) + timedelta(minutes=9),
    }]
    assert ratings == [{"city": "AUSTIN", "valid_time": slot(1), "run_id": "42"}]
    # a connection handed in by the caller is the caller's to close
    assert conn.closed is False
