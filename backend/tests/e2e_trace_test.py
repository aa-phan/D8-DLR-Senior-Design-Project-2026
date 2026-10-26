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

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        text = " ".join(sql.lower().split())
        if text.startswith("set "):
            return _Cursor()
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
