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


# ── Task 2: edge cases ────────────────────────────────────────────────────────

def run_report(tmp_path, writes, runs, run_rows, hours=14, *extra, **kwargs):
    directory = write_inputs(tmp_path / "in", writes, runs, run_rows, hours=hours, **kwargs)
    return report(directory, *extra)


def test_retry_rewrite_does_not_inflate_lag(tmp_path, capsys):
    writes, runs, run_rows = healthy(14)
    for w in writes:
        if w["city"] == "AUSTIN" and w["valid_time"] == slot(5):
            w["computed_at"] = w["first_written_at"] + timedelta(minutes=40)  # an OD-7 same-hour rewrite

    code, markdown, result = run_report(tmp_path, writes, runs, run_rows)

    assert code == 0
    event = next(e for e in result["events"] if e["city"] == "AUSTIN" and e["valid_time"] == _iso(slot(5)))
    assert event["write_lag_min"] == 8.0
    assert event["peak_age_min"] == 68.0
    assert event["last_write_lag_min"] == 48.0
    assert city_entry(result, "AUSTIN")["last_write_lag_max_min"] == 48.0
    assert city_entry(result, "AUSTIN")["lag"]["max_min"] == 8.0
    assert result["overall"]["peak"]["max_min"] == 68.0


def test_backfill_rows_are_ignored(tmp_path):
    writes, runs, run_rows = healthy(14)
    baseline = soak.evaluate_dry(_load(tmp_path / "a", writes, runs, run_rows), SINCE, until_for(14))

    noisy = list(writes)
    for city in CITIES:
        # a backfill row whose load time lands inside the window, and one that would advance the maximum
        noisy.append(write_row(city, slot(3), run_id="backfill-1", origin="backfill",
                               first_written_at=slot(9) + timedelta(minutes=50)))
        noisy.append(write_row(city, slot(40), run_id="backfill-2", origin="backfill",
                               first_written_at=slot(9) + timedelta(minutes=55)))
    again = soak.evaluate_dry(_load(tmp_path / "b", noisy, runs, run_rows), SINCE, until_for(14))

    assert again == baseline
    assert again["verdict"] == "pass"


def _load(directory, writes, runs, run_rows, hours=14):
    return soak.load_inputs(write_inputs(directory, writes, runs, run_rows, hours=hours))


def test_missing_slot_is_a_128_minute_breach(tmp_path, capsys):
    writes, runs, run_rows = healthy(14)
    # EL_PASO alone loses the slot-6 row; the run itself is still there
    one_city = [w for w in writes if not (w["city"] == "EL_PASO" and w["valid_time"] == slot(6))]

    code, markdown, result = run_report(tmp_path / "one", one_city, runs, run_rows)

    assert code == 1
    assert result["verdict"] == "fail"
    el_paso = city_entry(result, "EL_PASO")
    assert el_paso["peak"]["max_min"] == 128.0
    assert el_paso["peak"]["above_max"] == 1
    assert all(city_entry(result, c)["peak"]["above_max"] == 0 for c in CITIES if c != "EL_PASO")
    assert result["slots"]["slots"][6]["verdict"] == "incomplete"
    assert "128.0" in markdown

    # the whole slot missing: no run, no row for any city
    gone = [w for w in writes if w["valid_time"] != slot(6)]
    gone_runs = [r for r in runs if r["databaseId"] != BASE_ID + 6]
    gone_rows = [r for r in run_rows if r["run_id"] != str(BASE_ID + 6)]
    code, markdown, result = run_report(tmp_path / "all", gone, gone_runs, gone_rows)

    assert code == 1
    assert result["slots"]["slots"][6]["verdict"] == "missing"
    assert all(city_entry(result, c)["peak"]["above_max"] == 1 for c in CITIES)


@pytest.mark.parametrize("landed, breaches, shown, code", [
    (timedelta(minutes=30), 0, 90.0, 0),                    # exactly 90 min: within budget (OD-4)
    (timedelta(minutes=30, seconds=6), 1, 90.1, 1),         # 90.1 min: a breach
    (timedelta(minutes=30, seconds=2), 1, 90.0, 1),         # displays as 90.0 but is over: exact timedelta decides
])
def test_exactly_90_minutes_is_within_budget(tmp_path, landed, breaches, shown, code):
    writes, runs, run_rows = healthy(14)
    for w in writes:
        if w["city"] == "MIDLAND" and w["valid_time"] == slot(5):
            w["first_written_at"] = w["computed_at"] = slot(5) + landed

    got, markdown, result = run_report(tmp_path, writes, runs, run_rows)

    assert got == code
    midland = city_entry(result, "MIDLAND")
    assert midland["peak"]["max_min"] == shown
    assert midland["peak"]["above_max"] == breaches
    assert result["verdict"] == ("pass" if code == 0 else "fail")


def test_peak_over_75_warns_but_passes(tmp_path, capsys):
    writes, runs, run_rows = healthy(14)
    for w in writes:
        if w["city"] == "CORPUS_CHRISTI" and w["valid_time"] == slot(7):
            w["first_written_at"] = w["computed_at"] = slot(7) + timedelta(minutes=16)  # peak age 76

    code, markdown, result = run_report(tmp_path, writes, runs, run_rows)

    assert code == 0
    assert city_entry(result, "CORPUS_CHRISTI")["peak"]["max_min"] == 76.0
    assert city_entry(result, "CORPUS_CHRISTI")["peak"]["above_75"] == 1
    assert "a single slow hour would breach" in capsys.readouterr().out
    assert "a single slow hour would breach" in markdown
    assert result["warnings"]

    # a healthy window prints no such warning
    writes, runs, run_rows = healthy(14)
    code, markdown, result = run_report(tmp_path / "healthy", writes, runs, run_rows)
    assert code == 0
    assert "a single slow hour" not in capsys.readouterr().out
    assert result["warnings"] == []


def test_late_fill_of_an_old_slot_is_not_a_breach(tmp_path):
    writes, runs, run_rows = healthy(14)
    # a manual past-slot re-run: the 22:00 slot of the day before is first written at 06:20 inside the window
    writes.append(write_row("AUSTIN", slot(-2), first_written_at=slot(6) + timedelta(minutes=20)))

    code, markdown, result = run_report(tmp_path, writes, runs, run_rows)

    assert code == 0
    austin = city_entry(result, "AUSTIN")
    assert austin["peak"]["max_min"] == 68.0
    assert austin["peak"]["above_max"] == 0
    assert austin["lag"]["count"] == 15  # the late fill is not an advancing write
    assert result["late_fills"]["count"] == 1
    assert "late fill" in markdown.lower()


def test_fallback_share_is_informational(tmp_path):
    writes, runs, run_rows = healthy(14)
    expected = 0
    for w in writes:
        index = int((w["valid_time"] - SINCE).total_seconds() // 3600)
        if w["city"] == "AUSTIN" and 0 <= index <= 14 and index % 4 != 0:
            w["fallback"] = True
            w["status"] = "fallback"
            expected += 1

    code, markdown, result = run_report(tmp_path, writes, runs, run_rows)

    assert code == 0
    assert result["failures"] == []
    austin = city_entry(result, "AUSTIN")
    assert austin["fallback"]["fallback"] == expected
    assert austin["fallback"]["rows"] == 15
    assert city_entry(result, "MIDLAND")["fallback"]["fallback"] == 0
    assert "informational" in markdown.lower()
    assert austin["peak"]["above_max"] == 0


def test_short_or_empty_window_fails(tmp_path, capsys):
    writes, runs, run_rows = healthy(11)
    code, markdown, result = run_report(tmp_path / "short", writes, runs, run_rows, hours=11)
    assert code == 1
    assert "window shorter than 12 h" in capsys.readouterr().out
    assert result["verdict"] == "fail"

    # the same 11 hours pass when the owner lowers the minimum
    code, markdown, result = run_report(tmp_path / "lowered", writes, runs, run_rows, 11, "--min-hours", "6")
    assert code == 0

    # no live rows inside the window: only the seed row written before --since
    seed_only = [w for w in healthy(14)[0] if w["valid_time"] == slot(-1)]
    code, markdown, result = run_report(tmp_path / "empty", seed_only, [], [])
    assert code == 1
    assert "no live rows in the window" in capsys.readouterr().out
    assert result["verdict"] == "fail"

    code, markdown, result = run_report(tmp_path / "nothing", [], [], [])
    assert code == 1
    assert "no live rows in the window" in capsys.readouterr().out
    assert [c["status"] for c in result["cities"]] == ["missing"] * 4


def test_bad_input_exits_2(tmp_path, capsys):
    writes, runs, run_rows = healthy(14)

    directory = write_inputs(tmp_path / "nofile", writes, runs, run_rows, drop=("writes.csv",))
    assert report(directory)[0] == 2
    assert "writes.csv" in capsys.readouterr().err

    columns = [c for c in WRITE_COLUMNS if c != "first_written_at"]
    directory = write_inputs(tmp_path / "nocolumn", writes, runs, run_rows, writes_columns=columns)
    assert report(directory)[0] == 2
    err = capsys.readouterr().err
    assert "writes.csv" in err and "first_written_at" in err

    directory = write_inputs(tmp_path / "nometa", writes, runs, run_rows, drop=("export_meta.json",))
    assert report(directory)[0] == 2
    assert "export_meta.json" in capsys.readouterr().err

    directory = write_inputs(tmp_path / "badtime", writes, runs, run_rows)
    text = (directory / "writes.csv").read_text().replace(_iso(slot(3)), "not-a-time", 1)
    (directory / "writes.csv").write_text(text)
    assert report(directory)[0] == 2
    err = capsys.readouterr().err
    assert "writes.csv" in err and "valid_time" in err


def test_output_order_and_byte_identical_reports(tmp_path):
    writes, runs, run_rows = healthy(14)
    shuffled = list(reversed(writes))

    directory = write_inputs(tmp_path / "in", shuffled, runs, run_rows, hours=14)
    code, first_md, first_json = report(directory)
    assert code == 0
    md_bytes = (directory / "report.md").read_bytes()
    json_bytes = (directory / "report.json").read_bytes()
    assert report(directory)[0] == 0
    assert (directory / "report.md").read_bytes() == md_bytes
    assert (directory / "report.json").read_bytes() == json_bytes

    # four cities that share one first_written_at come out in config.LOCATIONS order
    assert [e["city"] for e in first_json["events"][:4]] == CITIES
    assert [c["city"] for c in first_json["cities"]] == CITIES
    positions = [first_md.index(f"| {c} |") for c in CITIES]
    assert positions == sorted(positions)
    assert "exported_at" not in first_md and "exported_at" not in json_bytes.decode()
