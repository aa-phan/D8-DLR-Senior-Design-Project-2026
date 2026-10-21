"""
Offline tests of the pipeline_run row (production-pipeline Phase 4, DB-02, OD-9):
`supabase_store.build_run_row` (pure) and `supabase_store.upsert_run` (SQL
shape, identifier allow-list, redaction), plus the orchestrator's refusal of a
store it cannot use.

A fake connection stands in for psycopg and records each statement with its
parameters. The real database behavior is proven in supabase_orchestrator_test.py.
Follows backend/tests/city_rating_test.py's conventions (module-level imports,
plain asserts, no test classes, no network).
"""

import contextlib
import json
import os
import re
from datetime import datetime, timezone

import pytest
import requests

import anomaly_detector
import config
import dlr_orchestrator as orch
import supabase_store

_MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "..", "supabase", "migrations",
    "20261019000000_create_city_rating.sql",
)
_RUN_CTX = {"run_id": "98765", "run_attempt": 2, "pipeline_version": "abcdef1"}
_END = "2025-06-01T14:07:00Z"
_STARTED = datetime(2025, 6, 1, 14, 7, 5, tzinfo=timezone.utc)
_FINISHED = datetime(2025, 6, 1, 14, 9, 41, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """
    Replace `requests.get` for every test. The composer and `rate_city` catch
    every provider exception, so raising alone could be swallowed; the teardown
    assert on the recorded attempts cannot be.
    """
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    # Another test module loads `.env` into the process at import time.
    for name in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL", "SUPABASE_DB_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "default_archive.csv"))
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


class FakeConn:
    """Records (normalized sql, params) and whether it ran inside `transaction()`."""

    def __init__(self, error=None):
        self.calls = []
        self.in_transaction = []
        self._depth = 0
        self._error = error

    def execute(self, sql, params=None):
        if self._error is not None:
            raise self._error
        self.calls.append((" ".join(sql.split()), params))
        self.in_transaction.append(self._depth > 0)

    @contextlib.contextmanager
    def transaction(self):
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1


def _record(city, written=True, error=None, forecast_status="ok", detector_model_loaded=True):
    return {"city": city, "written": written, "error": error,
            "forecast_status": forecast_status, "detector_model_loaded": detector_model_loaded}


def _build(records, **overrides):
    args = dict(window_end=_END, provider="composed", forecast_method="ml",
                started_at=_STARTED, finished_at=_FINISHED, city_records=records)
    args.update(overrides)
    return supabase_store.build_run_row(_RUN_CTX, **args)


def _migration_run_columns():
    sql = open(_MIGRATION, encoding="utf-8").read()
    block = re.search(
        r"create table if not exists public\.pipeline_run \((.*?)\n\);", sql, re.DOTALL).group(1)
    return tuple(re.match(r"\s*(\w+)\s", line).group(1) for line in block.strip().splitlines())


# ──────────────────────────────────────────────────────────────────────────────
# build_run_row
# ──────────────────────────────────────────────────────────────────────────────

def test_run_row_columns_are_the_migrations_columns_in_order():
    assert supabase_store.PIPELINE_RUN_COLUMNS == _migration_run_columns()
    assert len(supabase_store.PIPELINE_RUN_COLUMNS) == 12
    assert set(supabase_store.PIPELINE_RUN_JSONB) <= set(supabase_store.PIPELINE_RUN_COLUMNS)

    row = _build([_record("AUSTIN")])

    assert tuple(row) == supabase_store.PIPELINE_RUN_COLUMNS


def test_run_row_carries_the_run_identity_window_and_timestamps():
    row = _build([_record("AUSTIN")])

    assert row["run_id"] == "98765"
    assert row["run_attempt"] == 2
    assert row["pipeline_version"] == "abcdef1"
    assert row["provider"] == "composed"
    assert row["forecast_method"] == "ml"
    # window_end is the run end itself, not its hour slot
    assert row["window_end"] == datetime(2025, 6, 1, 14, 7, 0, tzinfo=timezone.utc)
    assert row["window_end"].tzinfo is not None
    assert row["started_at"] == _STARTED
    assert row["finished_at"] == _FINISHED


def test_run_row_classifies_ok_degraded_and_error_in_location_order():
    records = [
        _record("EL_PASO"),                                        # ok
        _record("MIDLAND", forecast_status="cold_start"),          # cold start is healthy
        _record("CORPUS_CHRISTI", forecast_status="failed"),       # written, forecast failed
        _record("AUSTIN", detector_model_loaded=False),            # written, no anomaly model
    ]
    row = _build(records + [])

    assert row["cities_ok"] == ["MIDLAND", "EL_PASO"]
    assert list(row["cities_failed"]) == ["AUSTIN", "CORPUS_CHRISTI"]
    assert row["cities_failed"]["CORPUS_CHRISTI"] == {
        "outcome": "degraded", "written": True, "forecast_status": "failed",
        "detector_model_loaded": True, "error": None,
    }
    assert row["cities_failed"]["AUSTIN"]["outcome"] == "degraded"
    assert row["cities_failed"]["AUSTIN"]["detector_model_loaded"] is False

    failed = _build([_record("AUSTIN", written=False, error="boom", forecast_status=None,
                             detector_model_loaded=False)])
    assert failed["cities_ok"] == []
    assert failed["cities_failed"]["AUSTIN"]["outcome"] == "error"
    assert failed["cities_failed"]["AUSTIN"]["written"] is False


def test_run_row_error_text_is_redacted_and_bounded():
    secret_url = "postgresql" + "://svc:" + "Zq9Mk7Leak" + "@db.example.com:5432/postgres"
    records = [
        _record("AUSTIN", written=False, error=f"token=abc123 failed at {secret_url}"),
        _record("EL_PASO", written=False, error="x" * 5000),
    ]

    row = _build(records)

    text = row["cities_failed"]["AUSTIN"]["error"]
    assert "abc123" not in text and "Zq9Mk7Leak" not in text and "db.example.com" not in text
    assert "token=REDACTED" in text
    assert len(row["cities_failed"]["EL_PASO"]["error"]) <= 1000


def test_run_row_passes_provider_errors_and_sources_through_keyed_by_city():
    errors = {"AUSTIN": {"nsrdb: ValueError: down": 2}, "EL_PASO": {}}
    sources = {"AUSTIN": {"air_temp": {"synoptic": 1}}, "EL_PASO": {}}

    row = _build([_record("AUSTIN")], provider_errors=errors, sources=sources)

    assert row["provider_errors"] == errors
    assert row["sources"] == sources
    bare = _build([_record("AUSTIN")])
    assert bare["provider_errors"] is None and bare["sources"] is None


# ──────────────────────────────────────────────────────────────────────────────
# upsert_run
# ──────────────────────────────────────────────────────────────────────────────

def test_upsert_run_binds_values_and_updates_every_given_non_key_column():
    conn = FakeConn()
    row = _build([_record("AUSTIN")], provider_errors={"AUSTIN": {}}, sources={"AUSTIN": {}})

    supabase_store.upsert_run(conn, row)

    (sql, params), = conn.calls
    assert conn.in_transaction == [True]
    assert sql.startswith("insert into public.pipeline_run (" + ", ".join(row) + ")")
    assert "on conflict (run_id) do update set" in sql
    assert "run_id = excluded.run_id" not in sql
    for column in row:
        if column != "run_id":
            assert f"{column} = excluded.{column}" in sql
    for column in supabase_store.PIPELINE_RUN_JSONB:
        assert f"%({column})s::jsonb" in sql
    # values are bound parameters, never SQL text
    assert "98765" not in sql and "composed" not in sql
    assert json.loads(params["cities_failed"]) == {}
    assert params["cities_ok"] == ["AUSTIN"]
    assert json.loads(params["sources"]) == {"AUSTIN": {}}
    assert params["run_id"] == "98765"


def test_upsert_run_with_a_subset_updates_only_those_columns():
    conn = FakeConn()

    supabase_store.upsert_run(conn, {"run_id": "7", "finished_at": _FINISHED})

    (sql, params), = conn.calls
    assert "(run_id, finished_at)" in sql
    assert sql.endswith("do update set finished_at = excluded.finished_at")
    assert params == {"run_id": "7", "finished_at": _FINISHED}


def test_upsert_run_rejects_unknown_columns_and_a_missing_run_id():
    conn = FakeConn()

    with pytest.raises(ValueError, match="not_a_column"):
        supabase_store.upsert_run(conn, {"run_id": "7", "not_a_column": 1})
    with pytest.raises(ValueError, match="run_id"):
        supabase_store.upsert_run(conn, {"finished_at": _FINISHED})
    # an identifier is never built from data, even a plausible-looking injection
    with pytest.raises(ValueError):
        supabase_store.upsert_run(conn, {"run_id": "7", "provider) values (1); drop table x; --": 1})

    assert conn.calls == []


def test_upsert_run_failure_is_a_redacted_store_error():
    leaked = "connection to postgresql" + "://svc:" + "Zq9Mk7Leak" + "@db.example.com/postgres failed"
    conn = FakeConn(error=RuntimeError(leaked))

    with pytest.raises(supabase_store.StoreError) as excinfo:
        supabase_store.upsert_run(conn, {"run_id": "7"})

    assert "Zq9Mk7Leak" not in str(excinfo.value)
    assert "db.example.com" not in str(excinfo.value)
    assert excinfo.value.__cause__ is None and excinfo.value.__context__ is None


# ──────────────────────────────────────────────────────────────────────────────
# orchestrator: store validation
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["sqlite", "csv", 42, object()], ids=["name", "csv", "int", "object"])
def test_run_dlr_pipeline_rejects_a_store_it_cannot_use_before_any_city_runs(monkeypatch, bad):
    calls = []
    monkeypatch.setattr(orch, "run_city_pipeline", lambda *a, **k: calls.append(a))

    with pytest.raises(ValueError, match="store"):
        orch.run_dlr_pipeline(stations=None, end=_END, archive=False, store=bad)

    assert calls == []
