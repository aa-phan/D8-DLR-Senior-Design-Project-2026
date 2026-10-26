"""
Offline tests for backend/e2e_soak_report.py (production-pipeline Phase 6, E2E-02, D-07).

The module has two subcommands: `export` (the owner's read-only copy of the live rows Phase 5
already wrote) and `report` (the dry-soak numbers, computed offline from those files). Nothing
here touches the network, a database or a `.env` file: `export` runs against a fake connection
and a fake `gh run list`, and `report` runs on the files that export wrote (or on files the
fixture builders write directly).

Fixture shape: one live row per city per hour, valid_time on the hour, first written at minute 08
(write lag 8 min, so the "current" rating is at most 68 min old when the next one lands), with a
pipeline_run row and a `gh run list` dict for the run that dispatched at minute 05.
"""

import csv
import json
from datetime import datetime, timedelta, timezone

import pytest

import config
import e2e_soak_report as soak

SINCE = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)
CITIES = list(config.LOCATIONS)
BASE_ID = 9000
LANDS_AT = timedelta(minutes=8)

WRITE_COLUMNS = [
    "city", "valid_time", "first_written_at", "computed_at", "run_id", "origin", "status",
    "fallback", "pipeline_version", "config_fingerprint", "forecast_model_sha256",
    "anomaly_model_sha256", "forecast_method", "config_version",
]
RUN_COLUMNS = ["run_id", "run_attempt", "started_at", "finished_at", "window_end", "cities_ok", "cities_failed"]


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def slot(i):
    return SINCE + timedelta(hours=i)


def until_for(hours):
    """An until half an hour after the last whole slot, so `hours` slots fall in the window."""
    return slot(hours) + timedelta(minutes=30)


def write_row(city, valid_time, landed=LANDS_AT, *, run_id=None, origin="live", fallback=False,
              rewritten_after=None, first_written_at=None):
    first = first_written_at if first_written_at is not None else valid_time + landed
    computed = first + (rewritten_after or timedelta(0))
    return {
        "city": city,
        "valid_time": valid_time,
        "first_written_at": first,
        "computed_at": computed,
        "run_id": str(run_id if run_id is not None else BASE_ID + int((valid_time - SINCE).total_seconds() // 3600)),
        "origin": origin,
        "status": "fallback" if fallback else "computed",
        "fallback": fallback,
        "pipeline_version": "abc1234",
        "config_fingerprint": "f" * 8,
        "forecast_model_sha256": "a" * 8,
        "anomaly_model_sha256": "b" * 8,
        "forecast_method": "open-meteo",
        "config_version": "v1-test",
    }


def gh_run(run_id, started, conclusion="success"):
    return {
        "databaseId": run_id,
        "createdAt": _iso(started - timedelta(seconds=5)),
        "startedAt": _iso(started),
        "updatedAt": _iso(started + timedelta(seconds=200)),
        "status": "completed",
        "conclusion": conclusion,
        "event": "schedule",
        "attempt": 1,
    }


def run_row(run_id, window_end, cities_ok=None, cities_failed=None):
    return {
        "run_id": str(run_id),
        "run_attempt": 1,
        "started_at": window_end + timedelta(seconds=20),
        "finished_at": window_end + timedelta(minutes=4),
        "window_end": window_end,
        "cities_ok": list(CITIES) if cities_ok is None else cities_ok,
        "cities_failed": cities_failed or {},
    }


def healthy(hours=14):
    """
    Writes for slots -1 (the row a consumer sees at the window start) to `hours` for every city, the
    pipeline_run rows and the gh runs of slots 0..hours.
    """
    writes, runs, run_rows = [], [], []
    for i in range(-1, hours + 1):
        for city in CITIES:
            writes.append(write_row(city, slot(i)))
        if i >= 0:
            rid = BASE_ID + i
            end = slot(i) + timedelta(minutes=5)
            runs.append(gh_run(rid, end + timedelta(seconds=20)))
            run_rows.append(run_row(rid, end))
    return writes, runs, run_rows


def _csv_value(value):
    if isinstance(value, datetime):
        return _iso(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return value


def write_inputs(directory, writes, runs, run_rows, since=SINCE, until=None, hours=14, drop=(), writes_columns=None):
    """Write the four export files directly (the shape `export` produces)."""
    directory.mkdir(parents=True, exist_ok=True)
    until = until if until is not None else until_for(hours)
    columns = writes_columns or WRITE_COLUMNS
    if "writes.csv" not in drop:
        with open(directory / "writes.csv", "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
            writer.writeheader()
            for row in writes:
                writer.writerow({k: _csv_value(v) for k, v in row.items()})
    if "runs.csv" not in drop:
        with open(directory / "runs.csv", "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=RUN_COLUMNS, lineterminator="\n")
            writer.writeheader()
            for row in run_rows:
                writer.writerow({k: _csv_value(v) for k, v in row.items()})
    if "gh_runs.json" not in drop:
        (directory / "gh_runs.json").write_text(json.dumps(runs))
    if "export_meta.json" not in drop:
        meta = {"mode": "dry", "since": _iso(since), "until": _iso(until)}
        (directory / "export_meta.json").write_text(json.dumps(meta))
    return directory


def report(directory, *extra):
    """Run the report CLI; returns (exit code, markdown text, parsed json)."""
    out = directory / "report.md"
    out_json = directory / "report.json"
    code = soak.main(["report", "--mode", "dry", "--in-dir", str(directory), "--out", str(out),
                      "--json-out", str(out_json), *extra])
    markdown = out.read_text() if out.exists() else ""
    parsed = json.loads(out_json.read_text()) if out_json.exists() else None
    return code, markdown, parsed


def city_entry(result, city):
    return next(c for c in result["cities"] if c["city"] == city)


# ── fakes for export ──────────────────────────────────────────────────────────

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
    """Records every statement; answers the two SELECTs from fixture dicts."""

    def __init__(self, writes, run_rows):
        self.writes = writes
        self.run_rows = run_rows
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        text = sql.lower()
        if "city_rating" in text:
            return _Cursor(WRITE_COLUMNS, [tuple(w[c] for c in WRITE_COLUMNS) for w in self.writes])
        if "pipeline_run" in text:
            return _Cursor(RUN_COLUMNS, [tuple(r[c] for c in RUN_COLUMNS) for r in self.run_rows])
        return _Cursor()

    def close(self):
        self.closed = True


def export(directory, conn, runs, hours=14, extra=()):
    argv = ["export", "--mode", "dry", "--since", _iso(SINCE), "--until", _iso(until_for(hours)),
            "--out-dir", str(directory), *extra]
    return soak.main(argv, connect_fn=lambda: conn, fetch_runs_fn=lambda start, n: runs)


# ── tests ─────────────────────────────────────────────────────────────────────

def test_tracer_export_then_dry_report(tmp_path, capsys):
    writes, runs, run_rows = healthy(14)
    conn = FakeConn(writes, run_rows)
    directory = tmp_path / "dry"

    assert export(directory, conn, runs) == 0

    for name in ("writes.csv", "runs.csv", "gh_runs.json", "export_meta.json"):
        assert (directory / name).is_file(), name
    meta = json.loads((directory / "export_meta.json").read_text())
    assert meta["mode"] == "dry"
    assert meta["since"] == _iso(SINCE)
    assert meta["until"] == _iso(until_for(14))
    assert meta["rows"]["writes"] == len(writes)
    assert conn.closed is True

    code, markdown, result = report(directory)

    assert code == 0, capsys.readouterr().out
    assert result["verdict"] == "pass"
    assert result["hours"] == 14
    overall = result["overall"]
    assert overall["peak"]["max_min"] == 68.0
    assert overall["peak"]["above_75"] == 0
    assert overall["peak"]["above_max"] == 0
    assert overall["lag"]["median_min"] == 8.0
    assert overall["lag"]["p95_min"] == 8.0
    assert overall["lag"]["max_min"] == 8.0
    for city in CITIES:
        entry = city_entry(result, city)
        assert entry["status"] == "ok"
        assert entry["lag"]["count"] == 15  # slots 0..14 land before until; slot -1 is the seed
        assert entry["peak"]["max_min"] == 68.0
    assert [s["verdict"] for s in result["slots"]["slots"]] == ["ok"] * 14
    assert "PASS" in markdown
    assert "| city |" in markdown and "write lag" in markdown
    assert "Slot verdicts" in markdown


def test_export_is_read_only_and_bound(tmp_path):
    writes, runs, run_rows = healthy(14)
    conn = FakeConn(writes, run_rows)

    assert export(tmp_path / "dry", conn, runs) == 0

    assert len(conn.calls) == 3
    first_sql, first_params = conn.calls[0]
    assert first_sql.strip().lower() == "set default_transaction_read_only = on"
    assert first_params is None
    for sql, params in conn.calls[1:]:
        assert sql.lstrip().lower().startswith("select")
        for word in ("insert", "update", "delete", "drop", "alter", "truncate"):
            assert word not in sql.lower().split()
        assert "2026" not in sql
        assert isinstance(params, dict)
        assert params["since"] == SINCE
        assert params["until"] == until_for(14)
        assert "%(since)s" in sql and "%(until)s" in sql
    assert any("public.city_rating" in sql and "origin = 'live'" in sql for sql, _ in conn.calls)
    assert any("public.pipeline_run" in sql for sql, _ in conn.calls)


def test_export_never_leaks_the_url(tmp_path, monkeypatch, capsys):
    marker = "hunter" + "2" + "-marker"
    url = "postgresql://dlr_writer:" + marker + "@db.example.invalid:5432/postgres"
    monkeypatch.setenv("SUPABASE_DB_URL", url)
    directory = tmp_path / "dry"

    def boom():
        raise RuntimeError(f"connection to {url} refused (password {marker})")

    with pytest.raises(Exception) as raised:
        soak.export_dry(SINCE, until_for(14), directory, connect_fn=boom, fetch_runs_fn=lambda s, n: [])
    assert marker not in str(raised.value)
    assert "RuntimeError" in str(raised.value)

    code = soak.main(["export", "--mode", "dry", "--since", _iso(SINCE), "--until", _iso(until_for(14)),
                      "--out-dir", str(directory)], connect_fn=boom, fetch_runs_fn=lambda s, n: [])
    captured = capsys.readouterr()
    assert code == 1
    assert marker not in captured.out and marker not in captured.err
    assert "RuntimeError" in captured.err + captured.out
    # nothing was written for a failed export, and no file anywhere carries the marker
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert marker not in path.read_text()

    # a good export carries no URL either
    writes, runs, run_rows = healthy(14)
    assert export(tmp_path / "ok", FakeConn(writes, run_rows), runs) == 0
    for path in (tmp_path / "ok").iterdir():
        text = path.read_text()
        assert marker not in text and "postgres" not in text.lower()
