"""
Offline tests for backend/e2e_trace.py (production-pipeline Phase 6, E2E-01).

The trace ties one cron-job.org execution to one Actions run, to the rows that run wrote, to what
the REST interface returns. Nothing here touches the network, GitHub, a database or a .env file:
`gh` is a recording fake runner, the database is a fake connection that records every statement,
and REST is the in-process FakePostgrest on 127.0.0.1. Every planted URL, password and key is
assembled from pieces so backend/tests/secret_scan_test.py never matches this file.

Fixture shape: the hourly cron-job.org job fires at minute 05 (here 14:05:02, HTTP 204), GitHub
creates the dispatch run 5 s later, the run writes one row per city at the 14:00 slot (OD-7).
"""

import copy
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import config
import e2e_trace as trace
import latest_rating_contract as contract
import supabase_rest as rest
import supabase_store
from fake_postgrest import FakePostgrest, make_rating_rows

CITIES = list(config.LOCATIONS)
KEY = "sb_" + "publishable_" + "TraceKey0123456789abcdef"
EXEC_AT = datetime(2026, 10, 19, 14, 5, 2, tzinfo=timezone.utc)
EXEC_ISO = "2026-10-19T14:05:02Z"
SLOT = datetime(2026, 10, 19, 14, 0, tzinfo=timezone.utc)
RUN_ID = 5550001
OTHER_RUN_ID = 5550777
LATER_RUN_ID = 5550999

TIMESTAMP_COLUMNS = ("valid_time", "observation_time", "computed_at")
PIPELINE_COLUMNS = ["run_id", "cities_ok", "cities_failed", "window_end", "finished_at"]


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ── fakes ─────────────────────────────────────────────────────────────────────

def gh_run(run_id=RUN_ID, created=None, event="workflow_dispatch", conclusion="success"):
    created = created if created is not None else EXEC_AT + timedelta(seconds=5)
    return {
        "databaseId": run_id,
        "createdAt": _iso(created),
        "startedAt": _iso(created + timedelta(seconds=3)),
        "updatedAt": _iso(created + timedelta(seconds=200)),
        "status": "completed",
        "conclusion": conclusion,
        "event": event,
        "attempt": 1,
    }


def gh_view(run_id=RUN_ID, **overrides):
    view = {
        "databaseId": run_id,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "createdAt": _iso(EXEC_AT + timedelta(seconds=5)),
        "startedAt": _iso(EXEC_AT + timedelta(seconds=8)),
        "updatedAt": _iso(EXEC_AT + timedelta(seconds=205)),
        "headSha": "ab12cd34" * 5,
        "workflowName": "DLR Live Ratings",
    }
    view.update(overrides)
    return view


class FakeGh:
    """A recording stand-in for subprocess.run: answers `gh run view <id> --json ...` with fixed JSON."""

    def __init__(self, view=None, returncode=0, stderr=""):
        self.view = view if view is not None else gh_view()
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), kwargs))
        return SimpleNamespace(returncode=self.returncode, stdout=json.dumps(self.view), stderr=self.stderr)


def make_rows(run_id=RUN_ID, slot=SLOT, **overrides):
    """The four city_rating rows one run writes (REST shape: ISO strings)."""
    return make_rating_rows([slot], run_id=str(run_id), **overrides)


def to_sql_row(row):
    """The SQL shape of a REST row: aware datetimes for the timestamp columns, the 31 columns only."""
    out = {}
    for column in contract.STORED_COLUMNS:
        value = row.get(column)
        if column in TIMESTAMP_COLUMNS and value is not None:
            value = rest.parse_ts(value)
        out[column] = copy.copy(value)
    return out


class _Description:
    def __init__(self, name):
        self.name = name


class _Cursor:
    def __init__(self, names=(), rows=()):
        self.description = [_Description(n) for n in names]
        self._rows = list(rows)

    def fetchall(self):
        return self._rows


class FakeConn:
    """
    Records every statement. `table` holds city_rating rows (SQL shape); the three SELECTs are
    answered from it and from `pipeline`, filtering on the BOUND parameters.
    """

    def __init__(self, table, pipeline=None):
        self.table = table
        self.pipeline = pipeline
        self.calls = []
        self.closed = False
        self.autocommit = True  # what supabase_store.connect() opens; begin_read_only turns it off
        self.read_only = None
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        text = " ".join(sql.lower().split())
        if "from public.pipeline_run" in text:
            rows = [self.pipeline] if self.pipeline and self.pipeline["run_id"] == params["run_id"] else []
            return _Cursor(PIPELINE_COLUMNS, [tuple(r[c] for c in PIPELINE_COLUMNS) for r in rows])
        if "where run_id = %(run_id)s" in text:
            rows = [r for r in self.table if r["run_id"] == params["run_id"]]
            rows.sort(key=lambda r: r["city"])
            names = contract.STORED_COLUMNS
            return _Cursor(names, [tuple(r[c] for c in names) for r in rows])
        if "where valid_time = %(valid_time)s" in text:
            rows = [r for r in self.table if r["valid_time"] == params["valid_time"]]
            rows.sort(key=lambda r: r["city"])
            return _Cursor(["city", "run_id"], [(r["city"], r["run_id"]) for r in rows])
        raise AssertionError("unexpected statement: %s" % sql)

    def close(self):
        self.closed = True


def pipeline_row(run_id=RUN_ID, cities_ok=None):
    return {
        "run_id": str(run_id),
        "cities_ok": list(CITIES) if cities_ok is None else list(cities_ok),
        "cities_failed": {},
        "window_end": SLOT + timedelta(minutes=5),
        "finished_at": SLOT + timedelta(minutes=8),
    }


class World:
    """One consistent scenario: the Actions list, gh view, the database and the REST service."""

    def __init__(self, rest_rows=None, sql_rows=None, pipeline=None, runs=None, view=None):
        base = make_rows()
        self.rest_rows = base if rest_rows is None else rest_rows
        self.sql_table = [to_sql_row(r) for r in base] if sql_rows is None else sql_rows
        self.pipeline = pipeline if pipeline is not None else pipeline_row()
        self.runs = [gh_run()] if runs is None else runs
        self.gh = FakeGh(view)
        self.conn = FakeConn(self.sql_table, self.pipeline)
        self.connects = 0
        self.fake = None

    def connect(self):
        self.connects += 1
        return self.conn

    def fetch_runs(self, start, hours):
        self.fetch_args = (start, hours)
        return self.runs


@pytest.fixture
def served(monkeypatch):
    """Start FakePostgrest for a World and point the environment at it; stopped after the test."""
    started = []

    def serve(world, **fake_kwargs):
        fake = FakePostgrest(rows=world.rest_rows, key=KEY, now=SLOT + timedelta(minutes=30), **fake_kwargs)
        fake.start()
        started.append(fake)
        world.fake = fake
        monkeypatch.setenv(rest.ENV_URL, fake.url)
        monkeypatch.setenv(rest.ENV_KEY, KEY)
        monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
        monkeypatch.delenv("SUPABASE_ADMIN_DB_URL", raising=False)
        return fake

    yield serve
    for fake in started:
        fake.stop()


def run_main(world, tmp_path, *extra, execution_time=EXEC_ISO, status="204"):
    argv = ["--execution-time", execution_time, "--execution-status", status,
            "--out", str(tmp_path / "trace.md"), "--json-out", str(tmp_path / "trace.json"), *extra]
    return trace.main(argv, fetch_runs_fn=world.fetch_runs, run_cmd=world.gh, connect_fn=world.connect)


def read_json(tmp_path):
    return json.loads((tmp_path / "trace.json").read_text())


def city_entry(result, city):
    return next(c for c in result["cities"] if c["city"] == city)


def link(result, name):
    return next(item for item in result["links"] if item["name"] == name)


# ── Task 1: the tracer and the comparison rules ───────────────────────────────

def test_full_chain_matches(served, tmp_path, capsys):
    world = World()
    served(world)

    code = run_main(world, tmp_path)

    out = capsys.readouterr().out
    assert code == 0
    assert "E2E TRACE OK" in out
    markdown = (tmp_path / "trace.md").read_text()
    result = read_json(tmp_path)
    assert result["ok"] is True
    assert [c["city"] for c in result["cities"]] == CITIES  # config.LOCATIONS order, always
    for entry in result["cities"]:
        assert entry["match"] is True
        assert entry["currency"] == "current"
        assert entry["mismatches"] == []
    assert result["run"]["id"] == str(RUN_ID)
    assert str(RUN_ID) in markdown
    for city in CITIES:
        assert "| %s |" % city in markdown
    assert markdown.count("yes") >= 4
    # the stored columns of every city were compared on both sides
    assert set(city_entry(result, CITIES[0])["sql"]) == set(contract.STORED_COLUMNS)
    assert set(city_entry(result, CITIES[0])["rest"]) == set(contract.STORED_COLUMNS)
    # the REST read used the run id and the publishable key, never the latest view alone
    queries = [dict(r["query"]) for r in world.fake.requests if r["path"].endswith("/city_rating")]
    assert queries and all(q.get("run_id") == "eq.%s" % RUN_ID for q in queries)
    assert all(r["headers"].get("apikey") == KEY for r in world.fake.requests)


def test_row_order_does_not_matter(served, tmp_path):
    world = World()
    world.sql_table = list(reversed(world.sql_table))
    world.conn.table = world.sql_table
    # the SQL fake sorts by city, so also hand compare_rows both orders directly
    rows = make_rows()
    sql = [to_sql_row(r) for r in rows]
    assert trace.compare_rows(sql, list(reversed(rows))) == []
    assert trace.compare_rows(list(reversed(sql)), rows) == []
    # and through the CLI with REST rows stored in reverse order
    world.rest_rows = list(reversed(world.rest_rows))
    served(world)
    assert run_main(world, tmp_path) == 0
    assert [c["city"] for c in read_json(tmp_path)["cities"]] == CITIES


def test_timestamp_forms_and_exact_floats(served, tmp_path, capsys):
    # a REST valid_time with Z against a SQL datetime with +00:00 is the same instant
    rows = make_rows()
    for row in rows:
        row["valid_time"] = "2026-10-19T14:00:00Z"
        row["computed_at"] = "2026-10-19T14:06:00.000Z"
    sql = [to_sql_row(r) for r in make_rows()]
    assert trace.compare_rows(sql, rows) == []
    assert rest.parse_ts("2026-10-19T14:00:00Z") == rest.parse_ts("2026-10-19T14:00:00+00:00")
    # an offset spelled in another zone is still the same instant
    rows[0]["valid_time"] = "2026-10-19T09:00:00-05:00"
    assert trace.compare_rows(sql, rows) == []

    # a difference of 1e-9 in rating_amps is a mismatch that names the city and the column
    drifted = make_rows()
    drifted[1]["rating_amps"] = drifted[1]["rating_amps"] + 1e-9
    found = trace.compare_rows([to_sql_row(r) for r in make_rows()], drifted)
    assert [(m.city, m.column) for m in found] == [(CITIES[1], "rating_amps")]

    # and the same through the CLI: exit 1 and the failure line names both
    world = World(rest_rows=drifted)
    served(world)
    code = run_main(world, tmp_path)
    out = capsys.readouterr().out
    assert code == 1
    assert CITIES[1] in out and "rating_amps" in out
    assert city_entry(read_json(tmp_path), CITIES[1])["match"] is False


def test_arrays_and_nulls_are_compared_exactly():
    rows = make_rows()
    sql = [to_sql_row(r) for r in rows]
    # element by element: order matters, and a different element is named
    changed = copy.deepcopy(rows)
    sql[0]["alerts"] = ["G4 first", "G2 second"]
    changed[0]["alerts"] = ["G2 second", "G4 first"]
    found = trace.compare_rows(sql, changed)
    assert [(m.city, m.column) for m in found] == [(CITIES[0], "alerts")]
    # a null only equals a null: None against 0, "" and [] all differ
    for stand_in in (0, "", [], False):
        sql = [to_sql_row(r) for r in make_rows()]
        other = make_rows()
        sql[2]["forecast_amps"] = None
        other[2]["forecast_amps"] = stand_in
        assert [(m.city, m.column) for m in trace.compare_rows(sql, other)] == [(CITIES[2], "forecast_amps")]
    sql = [to_sql_row(r) for r in make_rows()]
    other = make_rows()
    sql[2]["forecast_amps"] = None
    other[2]["forecast_amps"] = None
    assert trace.compare_rows(sql, other) == []
    # a boolean never equals the number 1
    sql = [to_sql_row(r) for r in make_rows()]
    other = make_rows()
    sql[0]["fallback"] = True
    other[0]["fallback"] = 1
    assert [(m.city, m.column) for m in trace.compare_rows(sql, other)] == [(CITIES[0], "fallback")]


def test_is_provisional_is_checked_against_the_labels(served, tmp_path, capsys):
    # the real labels carry the word, so the view must say true
    rows = make_rows()
    assert contract.is_provisional(rows[0]["rating_basis"], rows[0]["config_version"]) is True
    world = World()
    fake = served(world)
    assert run_main(world, tmp_path) == 0
    assert read_json(tmp_path)["ok"] is True

    # a view that says false for one city while its labels say provisional fails, naming the city
    wrong = fake.latest_view_rows()
    for row in wrong:
        if row["city"] == CITIES[3]:
            row["is_provisional"] = False
    fake.latest_override = wrong
    code = run_main(world, tmp_path)
    out = capsys.readouterr().out
    assert code == 1
    assert "FAIL is_provisional" in out and CITIES[3] in out
    result = read_json(tmp_path)
    assert link(result, "is_provisional")["ok"] is False
    assert link(result, "SQL equals REST")["ok"] is True  # the stored columns were fine

    # labels without the word and a view that says false agree
    clean = make_rows(rating_basis="Per-conductor amperes (final)", config_version="v-final")
    world = World(rest_rows=clean, sql_rows=[to_sql_row(r) for r in clean])
    served(world)
    assert run_main(world, tmp_path) == 0


def test_current_or_superseded_column(served, tmp_path):
    # the run's rows are still the newest per city
    world = World()
    served(world)
    assert run_main(world, tmp_path) == 0
    assert {c["currency"] for c in read_json(tmp_path)["cities"]} == {"current"}

    # a later hourly slot has replaced two cities in latest_rating: informational, still a match
    later = make_rating_rows([SLOT + timedelta(hours=1)], cities=CITIES[:2], run_id=str(LATER_RUN_ID))
    world = World(rest_rows=make_rows() + later)
    served(world)
    assert run_main(world, tmp_path) == 0
    result = read_json(tmp_path)
    assert [c["currency"] for c in result["cities"]] == [
        "superseded by a later slot", "superseded by a later slot", "current", "current"]
    assert all(c["match"] for c in result["cities"])
    assert "superseded by a later slot" in (tmp_path / "trace.md").read_text()


# ── Task 2: every failing link is named ───────────────────────────────────────

def _exec_offset(seconds):
    return EXEC_AT + timedelta(seconds=seconds)


@pytest.mark.parametrize("offsets, found, expect", [
    ([-61], False, "no workflow_dispatch run"),      # one second before the 60 s allowance
    ([-60], True, None),                              # exactly 60 s before is inside
    ([0], True, None),
    ([300], True, None),                              # exactly 300 s after is inside
    ([301], False, "no workflow_dispatch run"),       # one second later is not
    ([], False, "no workflow_dispatch run"),          # zero candidates
    ([10, 20], False, "2 workflow_dispatch runs"),    # two candidates: the correlation is ambiguous
    ([301, 10], True, None),                          # an excluded neighbour is not a second candidate
])
def test_candidate_window_edges(offsets, found, expect, served, tmp_path, capsys):
    # a run inside the window is the one the fixture rows belong to; the others get their own ids
    runs = [gh_run(RUN_ID if -60 <= s <= 300 else RUN_ID + 100 + i, created=_exec_offset(s))
            for i, s in enumerate(offsets)]
    run, reason = trace.find_run(EXEC_AT, runs)
    assert (run is not None) is found
    if not found:
        assert expect in reason
    else:
        assert run["databaseId"] == RUN_ID

    # through the CLI: a missing or ambiguous run is a failed link and nothing else is claimed
    world = World(runs=runs)
    served(world)
    code = run_main(world, tmp_path)
    out = capsys.readouterr().out
    if found:
        assert code == 0
    else:
        assert code == 1
        assert "FAIL Actions run" in out and expect in out
        result = read_json(tmp_path)
        assert result["run"] is None and all(not c["match"] for c in result["cities"])
        assert world.connects == 0  # no run, so no database read


def test_schedule_runs_are_not_candidates():
    runs = [gh_run(RUN_ID, event="schedule"), gh_run(RUN_ID + 1, event="push")]
    assert trace.find_run(EXEC_AT, runs)[0] is None


def test_run_must_be_a_successful_dispatch_of_the_live_workflow(served, tmp_path, capsys):
    world = World()
    served(world)
    assert run_main(world, tmp_path) == 0
    argv = world.gh.calls[0][0]
    assert argv == ["gh", "run", "view", str(RUN_ID), "--json", trace.GH_VIEW_FIELDS]  # an argv list, no shell
    assert "shell" not in world.gh.calls[0][1]
    capsys.readouterr()

    cases = [
        ({"conclusion": "failure"}, "conclusion"),
        ({"conclusion": None}, "conclusion"),
        ({"event": "schedule"}, "event"),
        ({"workflowName": "Some Other Workflow"}, "workflowName"),
        ({"databaseId": RUN_ID + 1}, "databaseId"),
    ]
    for overrides, field in cases:
        world = World(view=gh_view(**overrides))
        served(world)
        code = run_main(world, tmp_path)
        out = capsys.readouterr().out
        assert code == 1, overrides
        failing = [line for line in out.splitlines() if line.startswith("FAIL Actions run result")]
        assert failing and field in failing[0], (overrides, out)

    # gh itself failing is a failed link, not a crash
    world = World()
    world.gh = FakeGh(returncode=1, stderr="HTTP 404: Not Found")
    served(world)
    assert run_main(world, tmp_path) == 1
    assert "FAIL Actions run result" in capsys.readouterr().out


def test_superseded_rows_fail_with_the_newer_run_named(served, tmp_path, capsys):
    # a later run in the same hourly slot overwrote the fourth city (OD-7 rewrites run_id)
    rest_rows = make_rows()
    taken = rest_rows.pop()
    overwritten = dict(taken, run_id=str(OTHER_RUN_ID))
    sql_table = [to_sql_row(r) for r in rest_rows] + [to_sql_row(overwritten)]
    world = World(rest_rows=rest_rows + [overwritten], sql_rows=sql_table)
    served(world)

    code = run_main(world, tmp_path)

    out = capsys.readouterr().out
    assert code == 1
    assert "superseded by run %s" % OTHER_RUN_ID in out
    result = read_json(tmp_path)
    entry = city_entry(result, taken["city"])
    assert entry["currency"] == "superseded by run %s" % OTHER_RUN_ID
    assert entry["match"] is False and entry["sql"] is None
    assert link(result, "SQL rows")["ok"] is False and taken["city"] in link(result, "SQL rows")["detail"]
    # the three untouched cities still matched; the verdict is never "match" for the overwritten one
    assert [c["match"] for c in result["cities"]].count(True) == 3
    # the slot lookup ran once, bound to the slot, and only because rows were missing
    slot_calls = [c for c in world.conn.calls if "valid_time = %(valid_time)s" in " ".join(c[0].split())]
    assert len(slot_calls) == 1 and slot_calls[0][1] == {"valid_time": SLOT}
    healthy = World()
    healthy_fake = served(healthy)
    assert run_main(healthy, tmp_path) == 0
    assert not [c for c in healthy.conn.calls if "valid_time = %(valid_time)s" in " ".join(c[0].split())]
    assert healthy_fake is not None


def test_empty_or_one_sided_rows_fail(served, tmp_path, capsys):
    # empty against empty never matches
    found = trace.compare_rows([], [])
    assert [m.city for m in found] == CITIES and all("no SQL row and no REST row" in m.reason for m in found)

    # REST answers an empty list
    world = World(rest_rows=[])
    served(world)
    assert run_main(world, tmp_path) == 1
    assert "no REST rows" in capsys.readouterr().out

    # one city present on the SQL side only
    rows = make_rows()
    gone = rows.pop(2)
    world = World(rest_rows=rows)
    served(world)
    assert run_main(world, tmp_path) == 1
    out = capsys.readouterr().out
    assert "FAIL SQL equals REST" in out and gone["city"] in out and "no REST row" in out
    assert city_entry(read_json(tmp_path), gone["city"])["match"] is False

    # one city present on the REST side only (nothing else holds its slot)
    sql = [to_sql_row(r) for r in make_rows()]
    missing = sql.pop(0)
    world = World(sql_rows=sql)
    served(world)
    assert run_main(world, tmp_path) == 1
    out = capsys.readouterr().out
    assert "FAIL SQL rows" in out and missing["city"] in out and "no SQL row" in out

    # nothing at all on either side
    world = World(rest_rows=[], sql_rows=[])
    served(world)
    assert run_main(world, tmp_path) == 1
    assert all(c["match"] is False for c in read_json(tmp_path)["cities"])
    capsys.readouterr()


def test_incomplete_pipeline_run_or_bad_status_fails(served, tmp_path, capsys):
    # the run listed only three cities in cities_ok
    world = World(pipeline=pipeline_row(cities_ok=CITIES[:3]))
    served(world)
    assert run_main(world, tmp_path) == 1
    out = capsys.readouterr().out
    assert "FAIL pipeline_run" in out and CITIES[3] in out

    # no pipeline_run row at all
    world = World()
    world.conn.pipeline = None
    served(world)
    assert run_main(world, tmp_path) == 1
    assert "FAIL pipeline_run" in capsys.readouterr().out

    # a non-2xx execution status
    for status in ("500", "404", "199", "301"):
        world = World()
        served(world)
        assert run_main(world, tmp_path, status=status) == 1
        out = capsys.readouterr().out
        assert "FAIL cron-job.org execution" in out and status in out
    world = World()
    served(world)
    assert run_main(world, tmp_path, status="204") == 0


def test_explicit_run_id_must_agree(served, tmp_path, capsys):
    world = World()
    served(world)
    assert run_main(world, tmp_path, "--run-id", str(RUN_ID)) == 0

    code = run_main(world, tmp_path, "--run-id", str(RUN_ID + 5))
    out = capsys.readouterr().out
    assert code == 1
    assert str(RUN_ID + 5) in out and str(RUN_ID) in out and "disagrees" in out
    assert [c[0][3] for c in world.gh.calls] == [str(RUN_ID)]  # the disagreeing id was never traced

    # usage and configuration errors are exit 2, never 1
    assert run_main(world, tmp_path, "--run-id", "12ab") == 2
    assert run_main(world, tmp_path, execution_time="2026-10-19T14:05:02") == 2  # no offset: maybe local time
    assert run_main(world, tmp_path, execution_time="not a time") == 2
    assert run_main(world, tmp_path, status="ok") == 2
    assert trace.main([], fetch_runs_fn=world.fetch_runs) == 2  # required arguments missing
    capsys.readouterr()


def test_missing_configuration_is_exit_2(monkeypatch, tmp_path, capsys):
    world = World()
    monkeypatch.delenv(rest.ENV_URL, raising=False)
    monkeypatch.delenv(rest.ENV_KEY, raising=False)
    assert run_main(world, tmp_path) == 2
    assert "SUPABASE_URL" in capsys.readouterr().err
    # no database URL and no injected connection
    monkeypatch.setenv(rest.ENV_URL, "http://127.0.0.1:9")
    monkeypatch.setenv(rest.ENV_KEY, KEY)
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    code = trace.main(["--execution-time", EXEC_ISO, "--execution-status", "204"], fetch_runs_fn=world.fetch_runs)
    assert code == 2
    assert "SUPABASE_DB_URL" in capsys.readouterr().err


def test_sql_read_is_read_only_and_bound(served, tmp_path):
    world = World()
    served(world)
    assert run_main(world, tmp_path) == 0

    assert world.connects == 1 and world.conn.closed
    # a read-only transaction (it holds behind a transaction pooler), not a session-level SET (review WR-04)
    assert world.conn.autocommit is False and world.conn.read_only is True and world.conn.rollbacks == 1
    assert len(world.conn.calls) == 2
    for sql, params in world.conn.calls:
        assert sql.lstrip().lower().startswith("select")
        assert set(sql.lower().split()).isdisjoint({"insert", "update", "delete", "drop", "alter", "truncate", "grant"})
        assert params == {"run_id": str(RUN_ID)}
        assert str(RUN_ID) not in sql and "%(run_id)s" in sql  # a bound parameter, never formatted in
    for column in contract.STORED_COLUMNS:
        assert column in world.conn.calls[0][0]
    assert "age_minutes" not in world.conn.calls[0][0] and "is_stale" not in world.conn.calls[0][0]
    # REST: GET only
    assert {r["method"] for r in world.fake.requests} == {"GET"}


def test_failures_never_leak_url_or_key(served, tmp_path, monkeypatch, capsys):
    marker = "hunter" + "2" + "-marker"
    db_url = "postgresql://dlr_writer:" + marker + "@db.example.invalid:5432/postgres"
    world = World()
    fake = served(world)
    monkeypatch.setenv("SUPABASE_DB_URL", db_url)

    def boom():
        raise RuntimeError("connection to %s refused (password %s)" % (db_url, marker))

    world.connect = boom
    with pytest.raises(supabase_store.StoreError) as raised:
        trace.sql_rows(RUN_ID, connect_fn=boom)
    assert marker not in str(raised.value) and "RuntimeError" in str(raised.value)
    assert raised.value.__cause__ is None  # no exception chained, so no traceback carries the URL

    # a REST error that echoes the project URL and the key
    fake.route_overrides["city_rating"] = (500, {"message": "upstream %s/rest/v1/city_rating failed apikey=%s" % (fake.url, KEY)})
    code = run_main(world, tmp_path)
    captured = capsys.readouterr()
    assert code == 1
    assert "FAIL SQL rows" in captured.out and "FAIL REST rows" in captured.out
    seen = captured.out + captured.err
    for path in tmp_path.iterdir():
        seen += path.read_text()
    for secret in (marker, db_url, fake.url, KEY, "127.0.0.1", "db.example.invalid"):
        assert secret not in seen, secret
    assert "RuntimeError" in seen  # the failure is still named, just redacted

    # an Actions listing that fails while echoing the project URL
    def bad_list(start, hours):
        raise RuntimeError("gh said %s and %s" % (fake.url, KEY))

    world = World()
    served(world)
    fake2 = world.fake
    code = trace.main(["--execution-time", EXEC_ISO, "--execution-status", "204", "--out", str(tmp_path / "x.md")],
                      fetch_runs_fn=lambda s, h: (_ for _ in ()).throw(RuntimeError("gh said %s and %s" % (fake2.url, KEY))),
                      run_cmd=world.gh, connect_fn=world.connect)
    captured = capsys.readouterr()
    assert code == 1
    assert fake2.url not in captured.out and KEY not in captured.out
    assert fake2.url not in (tmp_path / "x.md").read_text() and KEY not in (tmp_path / "x.md").read_text()


def test_evidence_is_deterministic_and_clean(served, tmp_path):
    world = World()
    fake = served(world)
    first, second = tmp_path / "one", tmp_path / "two"
    for directory in (first, second):
        directory.mkdir()
        assert run_main(world, directory) == 0
    for name in ("trace.md", "trace.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    text = (first / "trace.md").read_text() + (first / "trace.json").read_text()
    for secret in (fake.url, KEY, "127.0.0.1", "postgres", "apikey", "sb_publishable"):
        assert secret not in text, secret
    parsed = json.loads((first / "trace.json").read_text())
    assert parsed["execution"] == {"time": EXEC_ISO, "status": 204}
    assert parsed["run"]["id"] == str(RUN_ID)
    assert parsed["cities"][0]["sql"]["valid_time"] == "2026-10-19T14:00:00Z"
    assert (first / "trace.md").read_text().endswith("E2E TRACE OK\n")


def test_a_run_landing_during_the_trace_is_not_a_mismatch(served, tmp_path):
    # the next hourly run replaces latest_rating for every city between the run-id read and the latest read
    world = World()
    later = make_rating_rows([SLOT + timedelta(hours=1)], run_id=str(LATER_RUN_ID))
    landed = []

    def hook(fake, record):
        if record["path"].endswith("/latest_rating") and not landed:
            fake.rows.extend(later)
            landed.append(True)

    served(world, before_request=hook)
    assert run_main(world, tmp_path) == 0
    result = read_json(tmp_path)
    assert landed and all(c["match"] for c in result["cities"])
    assert {c["currency"] for c in result["cities"]} == {"superseded by a later slot"}
