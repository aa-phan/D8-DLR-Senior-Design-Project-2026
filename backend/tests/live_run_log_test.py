"""
Tests for backend/live_run_log.py -- the `public.pipeline_run` row of one live run
(production-pipeline Phase 5, SCHED-01 and OD-9).

Every test runs offline. The database is a stub connection that records the SQL
text and the bound parameters (the style of backend/tests/supabase_store_test.py);
no driver is imported and nothing is written outside `tmp_path`. Secret-shaped
fixtures are built at run time from pieces so no tracked file holds a literal.
"""

import contextlib
import glob
import json
import os
import re
from datetime import datetime, timezone

import config
import live_run_log

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_END = "2025-06-01T10:55:00Z"
_STARTED = "2025-06-01T10:55:03Z"
_FINISHED = "2025-06-01T11:01:40Z"


def _utc(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _record(city, outcome="ok", **over):
    """One runner outcome record (backend/dlr_live_run.py), healthy unless `over` says otherwise."""
    ok = outcome == "ok"
    rec = {
        "city": city, "outcome": outcome, "exit_code": 0 if ok else (None if outcome == "timeout" else 1),
        "rating_a": 1000.0 if ok else None, "fallback": False if ok else None,
        "exhausted": False if ok else None, "fallback_gates": [], "written": ok,
        "forecast_status": "ok" if ok else "not_run", "forecast_error": None,
        "detector_model_loaded": ok, "cleaning_error": None, "provider_errors": {}, "sources": {},
        "error": None if ok else f"{outcome} text for {city}", "fault_injected": False,
        "started_at": _STARTED, "finished_at": _FINISHED, "duration_s": 12.3,
    }
    rec.update(over)
    return rec


def _state(cities, finished_at=_FINISHED, **over):
    state = {"run_id": "9001", "run_attempt": 1, "end": _END, "slot": "2025-06-01T10:00:00Z",
             "started_at": _STARTED, "finished_at": finished_at, "cities": cities, "exit_code": None}
    state.update(over)
    return state


_ENV = {"GITHUB_SHA": "abcdef0123456789"}


class StubConn:
    """Records (normalized sql, params) and whether each statement ran inside `transaction()`."""

    def __init__(self):
        self.calls = []
        self.in_transaction = []
        self.transactions = 0
        self._depth = 0

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))
        self.in_transaction.append(self._depth > 0)

    @contextlib.contextmanager
    def transaction(self):
        self.transactions += 1
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1


def test_build_run_row_splits_ok_failed_and_degraded_cities():
    austin, corpus, midland, el_paso = config.LOCATIONS[:4]
    long_error = "e" * 5000
    records = [
        _record(austin, provider_errors={"synoptic: HTTP 429": 2}, sources={"temp": {"synoptic": 4}}),
        _record(corpus, "error", error=long_error),
        _record(midland, "timeout"),
        _record(el_paso, forecast_status="failed", forecast_error="forecast failed: " + "f" * 1000,
                provider_errors={"nrel: HTTP 500": 1}),
    ]

    row = live_run_log.build_run_row(_state(records), env=_ENV)

    assert row["cities_ok"] == [austin]
    assert list(row["cities_failed"]) == [corpus, midland, el_paso]
    # OD-9: an errored or timed-out city has no rating row; the run log is its only record
    failed = row["cities_failed"]
    assert failed[corpus]["outcome"] == "error" and failed[corpus]["written"] is False
    assert failed[corpus]["exit_code"] == 1 and failed[corpus]["forecast_status"] == "not_run"
    assert failed[corpus]["error"] == long_error[:1000]
    assert failed[midland]["outcome"] == "timeout" and failed[midland]["written"] is False
    assert failed[midland]["exit_code"] is None
    # degraded: the rating row was written, but the ML forecast failed
    assert failed[el_paso]["outcome"] == "degraded" and failed[el_paso]["written"] is True
    assert failed[el_paso]["forecast_status"] == "failed"
    assert failed[el_paso]["forecast_error"] == ("forecast failed: " + "f" * 1000)[:300]
    assert set(failed[el_paso]) == {
        "outcome", "written", "exit_code", "duration_s", "forecast_status", "forecast_error",
        "detector_model_loaded", "cleaning_error", "error", "fault_injected"}
    assert failed[corpus]["duration_s"] == 12.3 and failed[el_paso]["detector_model_loaded"] is True
    # each child's composer counts are keyed by city; cities with none are omitted
    assert row["provider_errors"] == {austin: {"synoptic: HTTP 429": 2}, el_paso: {"nrel: HTTP 500": 1}}
    assert row["sources"] == {austin: {"temp": {"synoptic": 4}}}
    assert (row["run_id"], row["run_attempt"], row["provider"], row["forecast_method"]) == (
        "9001", 1, "composed", "ml")
    assert row["window_end"] == _utc(_END)

    # health edges: a missing anomaly model or a missing forecast status is degraded, cold_start is healthy
    edge = live_run_log.build_run_row(_state([
        _record(austin, detector_model_loaded=False),
        _record(corpus, forecast_status=None),
        _record(midland, forecast_status="cold_start"),
    ]), env=_ENV)
    assert edge["cities_ok"] == [midland]
    assert {c: edge["cities_failed"][c]["outcome"] for c in (austin, corpus)} == {
        austin: "degraded", corpus: "degraded"}

    # a history-cleaning failure makes a written city degraded even at cold_start, with the reason kept
    cleaning = live_run_log.build_run_row(_state([
        _record(austin, forecast_status="cold_start", cleaning_error="data cleaning failed: " + "c" * 1000),
        _record(corpus),
    ]), env=_ENV)
    assert cleaning["cities_ok"] == [corpus]
    assert cleaning["cities_failed"][austin]["outcome"] == "degraded"
    assert cleaning["cities_failed"][austin]["cleaning_error"] == ("data cleaning failed: " + "c" * 1000)[:300]

    # config.LOCATIONS order, whatever order the records arrive in
    shuffled = live_run_log.build_run_row(_state([_record(el_paso), _record(austin)]), env=_ENV)
    assert shuffled["cities_ok"] == [austin, el_paso]


def test_in_progress_and_finished_rows():
    austin, corpus = config.LOCATIONS[:2]

    start = live_run_log.build_run_row(_state([], finished_at=None), env=_ENV)
    assert start["finished_at"] is None  # a run killed by the job timeout keeps this
    assert start["cities_ok"] == [] and start["cities_failed"] == {}
    assert start["provider_errors"] == {} and start["sources"] == {}
    assert start["started_at"] == _utc(_STARTED) and start["window_end"] == _utc(_END)

    midway = live_run_log.build_run_row(_state([_record(austin)], finished_at=None), env=_ENV)
    assert midway["finished_at"] is None and midway["cities_ok"] == [austin]

    done = live_run_log.build_run_row(_state([_record(austin), _record(corpus, "error")]), env=_ENV)
    assert done["finished_at"] == _utc(_FINISHED)
    assert done["started_at"] == _utc(_STARTED)
    assert done["window_end"] == _utc(_END)  # the shared end, in progress and finished alike
    assert done["pipeline_version"] == "abcdef0"  # GITHUB_SHA[:7]
    assert live_run_log.build_run_row(_state([], pipeline_version="cached1"), env=_ENV)[
        "pipeline_version"] == "cached1"

    # the same run with a second attempt keeps its id and carries the attempt
    again = live_run_log.build_run_row(_state([], run_attempt=2), env=_ENV)
    assert (again["run_id"], again["run_attempt"]) == ("9001", 2)


def test_drill_city_is_marked():
    austin, corpus = config.LOCATIONS[:2]
    row = live_run_log.build_run_row(_state([
        _record(austin, "error", fault_injected=True),
        _record(corpus, "error"),
    ]), env=_ENV)

    assert row["cities_failed"][austin]["fault_injected"] is True
    assert row["cities_failed"][corpus]["fault_injected"] is False


def test_upsert_is_keyed_on_the_run_and_updates_in_place():
    from supabase_store import PIPELINE_RUN_COLUMNS

    austin, corpus = config.LOCATIONS[:2]
    conn = StubConn()
    first = live_run_log.build_run_row(_state([], finished_at=None), env=_ENV)
    second = live_run_log.build_run_row(_state([_record(austin), _record(corpus, "error")]), env=_ENV)

    live_run_log.upsert_run_row(conn, first)
    live_run_log.upsert_run_row(conn, second)

    assert len(conn.calls) == 2 and conn.transactions == 2  # one statement per call, committed each time
    assert all(conn.in_transaction)
    for sql, params in conn.calls:
        assert sql.startswith("insert into public.pipeline_run (")
        assert " on conflict (run_id) do update set " in sql  # the primary key Phase 4 shipped
        update_set = sql.split(" do update set ")[1]
        updated = [part.split(" = ")[0] for part in update_set.split(", ")]
        assert updated == [c for c in PIPELINE_RUN_COLUMNS if c != "run_id"]  # every non-key column
        assert all(f"{c} = excluded.{c}" in update_set for c in updated)
        assert params["run_id"] == "9001"
    # the second send replaces the first in place: same key, now with the end time and the cities
    assert conn.calls[0][1]["finished_at"] is None
    assert conn.calls[1][1]["finished_at"] == _utc(_FINISHED)
    assert json.loads(conn.calls[1][1]["cities_failed"])[corpus]["outcome"] == "error"
    assert conn.calls[1][1]["cities_ok"] == [austin]

    # adjacency: a manual re-run of the same Actions run (attempt 2) is the same key, so it replaces the row
    rerun = live_run_log.build_run_row(_state([], run_attempt=2), env=_ENV)
    live_run_log.upsert_run_row(conn, rerun)
    sql, params = conn.calls[2]
    assert "on conflict (run_id) do update" in sql and "run_attempt = excluded.run_attempt" in sql
    assert params["run_id"] == "9001" and params["run_attempt"] == 2


def test_values_are_bound_parameters_never_sql_text():
    austin, corpus = config.LOCATIONS[:2]
    hostile = "it's \"bad\"'); " + "drop " + "table public.pipeline_run; --"
    quoted_id = "run'; " + "delete " + "from public.pipeline_run; --"
    conn = StubConn()
    row = live_run_log.build_run_row(_state(
        [_record(austin), _record(corpus, "error", error=hostile)], run_id=quoted_id,
        pipeline_version="v'1"), env=_ENV)

    live_run_log.upsert_run_row(conn, row)

    (sql, params), = conn.calls
    for text in (hostile, quoted_id, "drop table", "delete from", "bad", "v'1", austin, corpus,
                 "9001", "composed", "abcdef0"):
        assert text not in sql, text
    assert re.findall(r"%\((\w+)\)s", sql) == [c for c in params]  # every value is a named placeholder
    assert json.loads(params["cities_failed"])[corpus]["error"] == hostile  # it arrives only as a parameter
    assert params["run_id"] == quoted_id and params["pipeline_version"] == "v'1"


def _migration_columns(table="pipeline_run"):
    """Column names and the primary-key column of `public.<table>`, parsed from Phase 4's migration."""
    for path in sorted(glob.glob(os.path.join(_ROOT, "supabase", "migrations", "*.sql"))):
        with open(path) as fh:
            text = fh.read()
        match = re.search(
            rf"create table if not exists public\.{table} \(\n(.*?)\n\);", text, re.DOTALL)
        if match:
            break
    else:
        raise AssertionError(f"no migration creates public.{table}")
    columns, key = [], None
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("constraint "):
            continue
        name = line.split()[0]
        columns.append(name)
        if "primary key" in line:
            key = name
    return columns, key


def test_insert_columns_exist_in_the_phase4_migration():
    columns, key = _migration_columns()
    assert key == "run_id" and "cities_failed" in columns  # the parse found the shipped table
    conn = StubConn()
    row = live_run_log.build_run_row(_state([_record(config.LOCATIONS[0])]), env=_ENV)

    live_run_log.upsert_run_row(conn, row)

    (sql, _), = conn.calls
    inserted = re.match(r"insert into public\.pipeline_run \(([^)]*)\)", sql).group(1).split(", ")
    assert inserted and set(inserted) <= set(columns)  # no column the table lacks
    assert set(row) <= set(columns)
    assert f"on conflict ({key}) do update" in sql  # the conflict target is the shipped primary key
