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
PROBE_COLUMNS = ["probed_at", "city", "latest_valid_time", "age_seconds", "breach"]


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


def write_inputs(directory, writes, runs, run_rows, since=SINCE, until=None, hours=14, drop=(), writes_columns=None,
                 probes=None, mode="dry"):
    """Write the export files directly (the shape `export` produces); probes.csv only when `probes` is given."""
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
    if probes is not None and "probes.csv" not in drop:
        with open(directory / "probes.csv", "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=PROBE_COLUMNS, lineterminator="\n")
            writer.writeheader()
            for row in probes:
                writer.writerow({k: _csv_value(v) for k, v in row.items()})
    if "export_meta.json" not in drop:
        meta = {"mode": mode, "since": _iso(since), "until": _iso(until)}
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
    """Records every statement; answers the SELECTs from fixture dicts (probes only in soak mode)."""

    def __init__(self, writes, run_rows, probes=None):
        self.writes = writes
        self.run_rows = run_rows
        self.probes = probes or []
        self.calls = []
        self.closed = False
        self.autocommit = True  # what supabase_store.connect() opens; begin_read_only turns it off
        self.read_only = None
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        text = sql.lower()
        if "freshness_log" in text:
            return _Cursor(PROBE_COLUMNS, [tuple(p[c] for c in PROBE_COLUMNS) for p in self.probes])
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

    # a read-only transaction (it holds behind a transaction pooler), not a session-level SET (review WR-04)
    assert conn.autocommit is False and conn.read_only is True and conn.rollbacks == 1
    assert len(conn.calls) == 2
    for sql, params in conn.calls:
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


# ══════════════════════════════════════════════════════════════════════════════
# Soak mode (06-07, E2E-02): 72 h window, probe log, write-based breach list
# ══════════════════════════════════════════════════════════════════════════════

SOAK_HOURS = 72
MIN_5 = timedelta(minutes=5)


def soak_until(hours=SOAK_HOURS):
    return SINCE + timedelta(hours=hours)


def make_probes(writes, hours=SOAK_HOURS, skip=None):
    """
    What ops.log_freshness() would have logged every five minutes: for each probe time and city, the
    newest live rating first written BEFORE that instant (strictly: a probe at the very instant of a
    write has not yet seen it), its age in seconds and breach = strictly over 90 minutes (or none).
    `skip(t, city)` drops a row.
    """
    live = {}
    for w in writes:
        if w["origin"] == "live":
            live.setdefault(w["city"], []).append(w)
    for rows in live.values():
        rows.sort(key=lambda w: w["first_written_at"])
    pointer = {city: 0 for city in CITIES}
    newest = {city: None for city in CITIES}
    out = []
    t = SINCE
    while t < soak_until(hours):
        for city in CITIES:
            rows = live.get(city, [])
            i = pointer[city]
            while i < len(rows) and rows[i]["first_written_at"] < t:
                if newest[city] is None or rows[i]["valid_time"] > newest[city]:
                    newest[city] = rows[i]["valid_time"]
                i += 1
            pointer[city] = i
            if skip is not None and skip(t, city):
                continue
            age = None if newest[city] is None else (t - newest[city]).total_seconds()
            out.append({"probed_at": t, "city": city, "latest_valid_time": newest[city], "age_seconds": age,
                        "breach": newest[city] is None or age > 5400})
        t += MIN_5
    return out


def soak_report(directory, *extra, git=None):
    """Run the soak report CLI; returns (exit code, markdown, parsed json). `git` replaces the git runner."""
    out = directory / "report.md"
    out_json = directory / "report.json"
    code = soak.main(["report", "--mode", "soak", "--in-dir", str(directory), "--out", str(out),
                      "--json-out", str(out_json), *extra], git_runner=git)
    markdown = out.read_text() if out.exists() else ""
    parsed = json.loads(out_json.read_text()) if out_json.exists() else None
    return code, markdown, parsed


def soak_run(tmp_path, writes, runs, run_rows, probes="auto", hours=SOAK_HOURS, *extra, name="soak", git=None):
    probes = make_probes(writes, hours=hours) if isinstance(probes, str) else probes
    directory = write_inputs(tmp_path / name, writes, runs, run_rows, since=SINCE, until=soak_until(hours),
                             probes=probes, mode="soak")
    return soak_report(directory, *extra, git=git)


def drop_row(writes, city, valid_time):
    return [w for w in writes if not (w["city"] == city and w["valid_time"] == valid_time)]


def test_tracer_soak_export_then_report(tmp_path, capsys):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    probes = make_probes(writes)
    assert len(probes) == 864 * len(CITIES)
    conn = FakeConn(writes, run_rows, probes)
    directory = tmp_path / "soak"

    argv = ["export", "--mode", "soak", "--since", _iso(SINCE), "--until", _iso(soak_until()),
            "--out-dir", str(directory)]
    assert soak.main(argv, connect_fn=lambda: conn, fetch_runs_fn=lambda start, n: runs) == 0

    for name in ("writes.csv", "runs.csv", "gh_runs.json", "export_meta.json", "probes.csv"):
        assert (directory / name).is_file(), name
    meta = json.loads((directory / "export_meta.json").read_text())
    assert meta["mode"] == "soak"
    assert meta["rows"]["probes"] == len(probes)
    assert conn.closed is True
    assert len(conn.calls) == 3  # writes, runs, probes (inside one read-only transaction)

    code, markdown, result = soak_report(directory)

    assert code == 0, capsys.readouterr().out
    assert result["mode"] == "soak"
    assert result["verdict"] == "pass"
    assert result["hours"] == 72
    assert result["breaches"] == []
    coverage = result["probe_coverage"]
    assert (coverage["expected"], coverage["found"]) == (864, 864)
    assert coverage["gaps"] == [] and coverage["incomplete"] == []
    assert result["overall"]["peak"]["max_min"] == 68.0
    assert "PASS" in markdown
    assert "Probe coverage" in markdown and "864" in markdown
    assert "No breaches" in markdown


def test_soak_export_reads_probes_read_only_and_bound(tmp_path):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    conn = FakeConn(writes, run_rows, make_probes(writes))

    argv = ["export", "--mode", "soak", "--since", _iso(SINCE), "--until", _iso(soak_until()),
            "--out-dir", str(tmp_path / "soak")]
    assert soak.main(argv, connect_fn=lambda: conn, fetch_runs_fn=lambda start, n: runs) == 0

    assert conn.autocommit is False and conn.read_only is True and conn.rollbacks == 1
    assert len(conn.calls) == 3
    sql, params = conn.calls[2]
    assert "ops.freshness_log" in sql
    assert sql.lstrip().lower().startswith("select")
    assert "%(since)s" in sql and "%(until)s" in sql and "2026" not in sql
    assert params == {"since": SINCE, "until": soak_until()}
    for word in ("insert", "update", "delete", "drop", "alter", "truncate"):
        assert word not in sql.lower().split()


@pytest.mark.parametrize("landed, breaches, shown, code", [
    (timedelta(minutes=30), 0, None, 0),                  # exactly 90 min: within budget (OD-4)
    (timedelta(minutes=30, seconds=6), 1, 90.1, 0),       # 90.1 min: a breach, explained as a late run
    (timedelta(minutes=30, seconds=2), 1, 90.0, 0),       # displays as 90.0 but is over: exact timedelta decides
])
def test_soak_exactly_90_minutes_is_not_a_breach(tmp_path, landed, breaches, shown, code):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    for w in writes:
        if w["city"] == "MIDLAND" and w["valid_time"] == slot(5):
            w["first_written_at"] = w["computed_at"] = slot(5) + landed
    probes = make_probes(writes)

    got, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes)

    assert got == code
    assert len(result["breaches"]) == breaches
    if breaches:
        breach = result["breaches"][0]
        assert (breach["kind"], breach["city"]) == ("write", "MIDLAND")
        assert breach["id"] == f"write:MIDLAND:{_iso(slot(5) + timedelta(minutes=30))}"
        assert breach["peak_age_min"] == shown
        assert breach["probe_count"] == 0  # a few seconds between two probes: the log never saw it
        assert breach["cause"].startswith("late run: written +30")  # still counted; the rule names why
    # the probe log applies the same strict rule: at the instant the rating is exactly 90 min old it is fresh
    at_90 = next(p for p in probes if p["city"] == "MIDLAND" and p["probed_at"] == slot(5) + timedelta(minutes=30))
    assert at_90["age_seconds"] == 5400 and at_90["breach"] is False
    assert result["probe_coverage"]["found"] == 864


def test_city_without_a_prior_row_breaches_from_window_start(tmp_path):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    writes = [w for w in writes if not (w["city"] == "MIDLAND" and w["valid_time"] < slot(0))]
    # the slot before the window ran for everyone; only this city's row is missing
    runs.append(gh_run(BASE_ID - 1, slot(-1) + timedelta(minutes=5, seconds=20)))
    run_rows.append(run_row(BASE_ID - 1, slot(-1) + timedelta(minutes=5)))

    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows)

    assert code == 1
    assert [b["id"] for b in result["breaches"]] == [f"write:MIDLAND:{_iso(SINCE)}"]
    breach = result["breaches"][0]
    assert breach["start"] == _iso(SINCE)
    assert breach["end"] == _iso(slot(0) + LANDS_AT)
    assert breach["peak_age_min"] is None  # there was no rating whose age could be stated
    assert breach["probe_count"] == 2      # the probes at 00:00 and 00:05 saw no rating at all
    assert "no rating" in markdown.lower()


def test_probe_gaps_and_empty_or_short_windows_fail(tmp_path, capsys):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    all_probes = make_probes(writes)
    cut = SINCE + timedelta(hours=10)

    # one lost probe leaves 10 minutes between neighbours: tolerated (the limit is 2 x 5 + 1 = 11 min)
    one_lost = [p for p in all_probes if p["probed_at"] != cut + MIN_5]
    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, one_lost, name="one")
    assert code == 0
    assert result["probe_coverage"]["gaps"] == []
    assert result["probe_coverage"]["found"] == 863

    # two lost probes leave 15 minutes: a probe gap, city ALL
    two_lost = [p for p in all_probes if not (cut < p["probed_at"] < cut + 3 * MIN_5)]
    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, two_lost, name="two")
    assert code == 1
    assert [b["id"] for b in result["breaches"]] == [f"probe-gap:ALL:{_iso(cut)}"]
    gap = result["breaches"][0]
    assert (gap["kind"], gap["city"], gap["end"]) == ("probe-gap", "ALL", _iso(cut + 3 * MIN_5))
    assert gap["duration_min"] == 15.0
    assert result["probe_coverage"]["gaps"][0]["start"] == _iso(cut)

    # gaps at the window edges count
    late_start = [p for p in all_probes if p["probed_at"] >= SINCE + timedelta(minutes=20)]
    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, late_start, name="start")
    assert code == 1
    assert [b["id"] for b in result["breaches"]] == [f"probe-gap:ALL:{_iso(SINCE)}"]

    early_end = [p for p in all_probes if p["probed_at"] < soak_until() - timedelta(minutes=20)]
    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, early_end, name="end")
    assert code == 1
    assert result["breaches"][0]["kind"] == "probe-gap"
    assert result["breaches"][0]["end"] == _iso(soak_until())

    # no probes at all
    capsys.readouterr()
    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, [], name="none")
    assert code == 1
    assert "no probes" in capsys.readouterr().out
    assert result["verdict"] == "fail"
    assert result["probe_coverage"]["found"] == 0

    # a 48 h window fails the default minimum; the owner can lower it explicitly
    writes48, runs48, rows48 = healthy(48)
    code, markdown, result = soak_run(tmp_path, writes48, runs48, rows48, hours=48, name="short")
    assert code == 1
    assert "window shorter than 72 h" in capsys.readouterr().out
    code, markdown, result = soak_run(tmp_path, writes48, runs48, rows48, "auto", 48, "--min-hours", "48", name="lowered")
    assert code == 0


def test_probe_breaches_merge_into_write_breaches(tmp_path):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    writes = drop_row(writes, "EL_PASO", slot(6))  # the run is there, one city's row is not
    probes = make_probes(writes)
    # breaches the probe log shows that no write explains: two in a row, then one alone
    for p in probes:
        if p["city"] == "MIDLAND" and p["probed_at"] in (slot(20) + timedelta(minutes=20),
                                                         slot(20) + timedelta(minutes=25),
                                                         slot(30) + timedelta(minutes=10)):
            p["breach"], p["age_seconds"] = True, 6000.0

    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes)

    assert code == 1
    first = slot(6) + timedelta(minutes=30)
    assert [b["id"] for b in result["breaches"]] == [
        f"write:EL_PASO:{_iso(first)}",
        f"probe:MIDLAND:{_iso(slot(20) + timedelta(minutes=20))}",
        f"probe:MIDLAND:{_iso(slot(30) + timedelta(minutes=10))}",
    ]
    write, pair, single = result["breaches"]
    assert write["peak_age_min"] == 128.0
    assert write["probe_count"] == 7  # probes from 06:35 to 07:05 saw the stale rating
    assert pair["probe_count"] == 2 and pair["end"] == _iso(slot(20) + timedelta(minutes=25))
    assert pair["peak_age_min"] == 100.0
    assert single["probe_count"] == 1
    assert [b["kind"] for b in result["breaches"]] == ["write", "probe", "probe"]


def test_incomplete_probe_is_listed(tmp_path):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    when = SINCE + timedelta(hours=3)
    probes = make_probes(writes, skip=lambda t, city: t == when and city == "EL_PASO")

    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes)

    assert code == 0  # listed, not a failure: the probe happened, one city's row did not
    incomplete = result["probe_coverage"]["incomplete"]
    assert incomplete == [{"probed_at": _iso(when), "rows": 3, "missing": ["EL_PASO"]}]
    assert result["probe_coverage"]["found"] == 864
    assert "incomplete" in markdown.lower() and _iso(when) in markdown


def test_soak_late_fill_and_backfill_are_ignored(tmp_path):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    probes = make_probes(writes)
    clean = _load_soak(tmp_path / "clean", writes, runs, run_rows, probes)

    noisy = list(writes)
    noisy.append(write_row("AUSTIN", slot(-2), first_written_at=slot(6) + timedelta(minutes=20)))  # a past-slot re-run
    for city in CITIES:
        noisy.append(write_row(city, slot(3), run_id="backfill-1", origin="backfill",
                               first_written_at=slot(9) + timedelta(minutes=50)))
        noisy.append(write_row(city, slot(400), run_id="backfill-2", origin="backfill",
                               first_written_at=slot(9) + timedelta(minutes=55)))
    again = _load_soak(tmp_path / "noisy", noisy, runs, run_rows, probes)

    for key in ("breaches", "probe_coverage", "trailing_age", "verdict", "overall"):
        assert again[key] == clean[key], key
    assert again["late_fills"]["count"] == 1
    assert again["breaches"] == []
    code, markdown, result = soak_run(tmp_path, noisy, runs, run_rows, probes, name="cli")
    assert code == 0


def _load_soak(directory, writes, runs, run_rows, probes, hours=SOAK_HOURS):
    inputs = soak.load_inputs(write_inputs(directory, writes, runs, run_rows, since=SINCE,
                                           until=soak_until(hours), probes=probes, mode="soak"), mode="soak")
    return soak.evaluate_soak(inputs, SINCE, soak_until(hours), soak.DEFAULT_MAX_AGE_MIN, soak.SOAK_MIN_HOURS,
                              soak.PROBE_INTERVAL_MIN)


def test_soak_order_and_byte_identical_reports(tmp_path):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    # CORPUS_CHRISTI and AUSTIN lose slot 6 together (listed in the opposite of the config order)
    writes = drop_row(drop_row(writes, "CORPUS_CHRISTI", slot(6)), "AUSTIN", slot(6))
    breach_start = slot(6) + timedelta(minutes=30)
    # and the probe log has a 20 minute hole that starts at the same instant
    probes = make_probes(writes)
    probes = [p for p in probes if not (breach_start < p["probed_at"] < breach_start + timedelta(minutes=20))]

    first = tmp_path / "a"
    code, markdown, result = soak_run(tmp_path, list(reversed(writes)), runs, run_rows, list(reversed(probes)),
                                      name="a")
    assert code == 1
    stamp = _iso(breach_start)
    assert [b["id"] for b in result["breaches"]] == [
        f"write:AUSTIN:{stamp}", f"write:CORPUS_CHRISTI:{stamp}", f"probe-gap:ALL:{stamp}"]
    assert markdown.index("write:AUSTIN") < markdown.index("write:CORPUS_CHRISTI") < markdown.index("probe-gap:ALL")

    md_bytes = (first / "report.md").read_bytes()
    json_bytes = (first / "report.json").read_bytes()
    assert soak_report(first)[0] == 1
    assert (first / "report.md").read_bytes() == md_bytes
    assert (first / "report.json").read_bytes() == json_bytes

    # the same data in another row order gives the same bytes
    code, other_md, other_json = soak_run(tmp_path, writes, runs, run_rows, probes, name="b")
    assert code == 1
    assert (tmp_path / "b" / "report.md").read_bytes() == md_bytes
    assert (tmp_path / "b" / "report.json").read_bytes() == json_bytes
    assert "exported_at" not in markdown and "exported_at" not in json_bytes.decode()


def test_report_rule_matches_the_contract():
    import latest_rating_contract

    assert soak.DEFAULT_MAX_AGE_MIN == latest_rating_contract.STALE_AFTER_MINUTES == 90
    assert soak.SOAK_MIN_HOURS == 72
    args = soak._build_parser().parse_args(["report", "--mode", "soak", "--in-dir", "x", "--out", "y"])
    assert args.max_age_min == latest_rating_contract.STALE_AFTER_MINUTES
    assert args.probe_interval_min == 5
    assert args.annotations is None

    # the write-based rule and the view's own rule agree on both sides of the boundary
    seed = write_row("AUSTIN", slot(0), first_written_at=slot(0) + LANDS_AT)
    for extra in (timedelta(minutes=-1), timedelta(0), timedelta(microseconds=1), timedelta(seconds=1)):
        age = timedelta(minutes=90) + extra
        until = slot(0) + age
        found = soak.write_breaches([seed], SINCE + timedelta(hours=1), until, soak.DEFAULT_MAX_AGE_MIN)
        austin = [b for b in found if b["city"] == "AUSTIN"]
        assert bool(austin) == latest_rating_contract.is_stale(slot(0), until), extra


def test_unexplained_breach_fails_without_annotation(tmp_path, capsys):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    writes = drop_row(writes, "EL_PASO", slot(6))
    probes = make_probes(writes)
    breach_id = f"write:EL_PASO:{_iso(slot(6) + timedelta(minutes=30))}"

    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes)
    assert code == 1
    assert result["verdict"] == "fail"
    assert result["breaches"][0]["cause"] is None and result["breaches"][0]["explanation"] is None
    assert breach_id in capsys.readouterr().out
    assert "no cause" in markdown.lower()

    note = {"explanation": "owner paused the cron-job.org dispatch job for maintenance", "by": "A. Owner",
            "date": "2026-10-28"}
    annotations = tmp_path / "annotations.json"
    annotations.write_text(json.dumps({"breaches": {breach_id: note}}))
    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes, SOAK_HOURS, "--annotations",
                                      str(annotations), name="soak2")
    assert code == 0
    assert result["verdict"] == "pass"
    assert result["breaches"][0]["explanation"] == note
    for text in (note["explanation"], "A. Owner", "2026-10-28"):
        assert text in markdown

    # an annotation for a different breach does not excuse this one
    annotations.write_text(json.dumps({"breaches": {"write:AUSTIN:2026-10-26T00:00:00Z": note}}))
    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes, SOAK_HOURS, "--annotations",
                                      str(annotations), name="soak3")
    assert code == 1


# ══════════════════════════════════════════════════════════════════════════════
# Task 2: breach causes, derived deploys, owner annotations (D-08)
# ══════════════════════════════════════════════════════════════════════════════

class FakeGit:
    """The injectable git runner: records (argv, cwd) and answers `git diff --name-only` from a path list."""

    def __init__(self, paths=(), code=0, raises=None):
        self.paths, self.code, self.raises = list(paths), code, raises
        self.calls = []

    def __call__(self, argv, cwd):
        self.calls.append((list(argv), cwd))
        if self.raises is not None:
            raise self.raises
        return self.code, "".join(path + "\n" for path in self.paths)


def set_versions(writes, old, new, from_slot):
    """pipeline_version `old` for rows before slot `from_slot`, `new` from it on."""
    for w in writes:
        w["pipeline_version"] = new if w["valid_time"] >= slot(from_slot) else old
    return writes


def _hunter_url():
    marker = "hunter" + "2" + "-marker"
    return marker, "postgresql://dlr_writer:" + marker + "@db.example.invalid:5432/postgres"


def _case_missing(writes, runs, run_rows):
    writes = [w for w in writes if w["valid_time"] != slot(6)]
    runs = [r for r in runs if r["databaseId"] != BASE_ID + 6]
    run_rows = [r for r in run_rows if r["run_id"] != str(BASE_ID + 6)]
    return writes, runs, run_rows, CITIES, f"no workflow run for slot {_iso(slot(6))} (dispatch missing)"


def _case_failed_visible(writes, runs, run_rows):
    writes = [w for w in writes if w["valid_time"] != slot(6)]
    for r in runs:
        if r["databaseId"] == BASE_ID + 6:
            r["conclusion"] = "failure"
    for r in run_rows:
        if r["run_id"] == str(BASE_ID + 6):
            r["cities_ok"], r["cities_failed"] = [], {}
    return writes, runs, run_rows, CITIES, f"workflow run {BASE_ID + 6} concluded failure"


def _failing_city(writes, runs, run_rows, conclusion):
    writes = drop_row(writes, "EL_PASO", slot(6))
    marker, url = _hunter_url()
    for r in runs:
        if r["databaseId"] == BASE_ID + 6:
            r["conclusion"] = conclusion
    for r in run_rows:
        if r["run_id"] == str(BASE_ID + 6):
            r["cities_ok"] = [c for c in CITIES if c != "EL_PASO"]
            r["cities_failed"] = {"EL_PASO": {"outcome": "timeout", "written": False, "fault_injected": False,
                                              "error": f"child exceeded 600 s talking to {url}"}}
    return writes, runs, run_rows, ["EL_PASO"]


def _case_city_failure(writes, runs, run_rows):
    writes, runs, run_rows, cities = _failing_city(writes, runs, run_rows, "success")
    return writes, runs, run_rows, cities, "city failure: timeout (child exceeded 600 s talking to"


def _case_red_run_and_city_failure(writes, runs, run_rows):
    writes, runs, run_rows, cities = _failing_city(writes, runs, run_rows, "failure")
    return (writes, runs, run_rows, cities,
            f"workflow run {BASE_ID + 6} concluded failure; city failure: timeout (child exceeded 600 s")


def _case_late_run(writes, runs, run_rows):
    for w in writes:
        if w["city"] == "EL_PASO" and w["valid_time"] == slot(6):
            w["first_written_at"] = w["computed_at"] = slot(6) + timedelta(minutes=40)
    return writes, runs, run_rows, ["EL_PASO"], "late run: written +40 min after the slot"


@pytest.mark.parametrize("case", [_case_missing, _case_failed_visible, _case_city_failure,
                                  _case_red_run_and_city_failure, _case_late_run],
                         ids=["missing", "failed-visible", "city-failure", "red-run-and-city-failure", "late-run"])
def test_causes_follow_the_slot_verdicts(tmp_path, case, capsys):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    writes, runs, run_rows, cities, expected = case(writes, runs, run_rows)

    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows)

    assert code == 0, capsys.readouterr().out
    assert result["verdict"] == "pass"
    breaches = result["breaches"]
    assert [b["city"] for b in breaches] == cities
    assert all(b["kind"] == "write" for b in breaches)
    for b in breaches:
        assert b["cause"].startswith(expected) or b["cause"] == expected, b["cause"]
        assert b["explanation"] is None
    assert "no cause" not in markdown.lower()
    marker, _ = _hunter_url()
    assert marker not in markdown and marker not in json.dumps(result)  # the error text is redacted
    # a cause appears in the table the owner reads
    assert expected.split(" (child")[0] in markdown


def test_annotation_explains_an_unexplained_breach(tmp_path, capsys):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    writes = drop_row(writes, "EL_PASO", slot(6))  # run fine, row missing: no rule explains it
    probes = make_probes(writes)
    breach_id = f"write:EL_PASO:{_iso(slot(6) + timedelta(minutes=30))}"
    note = {"explanation": "Supabase maintenance window; the city child could not connect | retried at 07:08",
            "by": "A. Owner", "date": "2026-10-28"}
    path = tmp_path / "annotations.json"
    path.write_text(json.dumps({"breaches": {breach_id: note}, "events": []}))

    parsed = soak.load_annotations(str(path))
    assert parsed["breaches"][breach_id] == note and parsed["events"] == []

    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes, SOAK_HOURS, "--annotations",
                                      str(path))
    assert code == 0, capsys.readouterr().out
    assert result["breaches"][0]["cause"] is None
    assert result["breaches"][0]["explanation"] == note
    assert note["explanation"] in markdown  # verbatim, pipe and all
    assert "A. Owner" in markdown and "2026-10-28" in markdown
    # the table row stays one row even though the text has a pipe
    row = next(line for line in markdown.splitlines() if line.startswith(f"| {breach_id}"))
    assert row.count("|") == 9


def test_unknown_or_malformed_annotations(tmp_path, capsys):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    directory = write_inputs(tmp_path / "in", writes, runs, run_rows, since=SINCE, until=soak_until(),
                             probes=make_probes(writes), mode="soak")
    note = {"explanation": "x", "by": "A. Owner", "date": "2026-10-28"}
    path = tmp_path / "annotations.json"

    # an id that matches no breach is a warning, not a failure and not an excuse
    path.write_text(json.dumps({"breaches": {"write:AUSTIN:2026-10-26T00:00:00Z": note}}))
    code, markdown, result = soak_report(directory, "--annotations", str(path))
    assert code == 0
    assert "unknown breach id write:AUSTIN:2026-10-26T00:00:00Z" in capsys.readouterr().out
    assert any("unknown breach id" in w for w in result["warnings"])

    good_id = "write:AUSTIN:2026-10-26T00:00:00Z"
    malformed = {
        "not json": "{not json",
        "top level list": [],
        "unknown key": {"breach": {}},
        "breaches not an object": {"breaches": []},
        "entry not an object": {"breaches": {good_id: "because"}},
        "missing by": {"breaches": {good_id: {"explanation": "x", "date": "2026-10-28"}}},
        "empty explanation": {"breaches": {good_id: dict(note, explanation="  ")}},
        "bad date": {"breaches": {good_id: dict(note, date="last tuesday")}},
        "extra entry key": {"breaches": {good_id: dict(note, why="x")}},
        "events not a list": {"events": {}},
        "event without what": {"events": [{"time": "2026-10-26T10:00:00Z", "by": "A"}]},
        "event bad time": {"events": [{"time": "noon", "what": "w", "by": "A"}]},
    }
    for label, content in malformed.items():
        path.write_text(content if isinstance(content, str) else json.dumps(content))
        capsys.readouterr()
        code, _, _ = soak_report(directory, "--annotations", str(path))
        err = capsys.readouterr().err
        assert code == 2, label
        assert "annotations" in err, label
    capsys.readouterr()
    assert soak_report(directory, "--annotations", str(tmp_path / "missing.json"))[0] == 2
    assert "annotations" in capsys.readouterr().err


def _deploy_writes(old="aaaaaaa", new="bbbbbbb", from_slot=5):
    writes, _, _ = healthy(14)
    return set_versions(writes, old, new, from_slot)


@pytest.mark.parametrize("paths, expected", [
    (["data/models/forecast_AUSTIN.joblib"], "model"),
    (["backend/config.py"], "config"),
    (["backend/city_point.py", "docs/notes.md"], "config"),
    ([".github/workflows/dlr_live.yml"], "workflow"),
    (["backend/other_module.py"], "code"),
    (["requirements.txt"], "code"),
    (["backend/config.py", "data/models/forecast_AUSTIN.joblib"], "model"),   # the first class in the order wins
    (["docs/guide.md", ".planning/notes.md"], "no runtime change"),
    (["backend/tests/some_test.py", "data/shadow/2026-10-26.csv"], "no runtime change"),
    (["frontend/app.js"], "other"),                                            # never guessed as harmless
])
def test_derive_deploys_classifies_version_changes(paths, expected):
    git = FakeGit(paths)

    deploys = soak.derive_deploys(_deploy_writes(), SINCE, soak_until(), git_runner=git, repo_root="/repo/root")

    assert len(deploys) == 1
    deploy = deploys[0]
    assert (deploy["old"], deploy["new"]) == ("aaaaaaa", "bbbbbbb")
    assert deploy["class"] == expected
    assert deploy["is_event"] is (expected != "no runtime change")
    assert deploy["first_slot"] == _iso(slot(5))
    assert deploy["first_written_at"] == _iso(slot(5) + LANDS_AT)
    assert deploy["cities"] == CITIES
    assert "pipeline_version" in deploy["changed"]
    assert git.calls == [(["git", "diff", "--name-only", "aaaaaaa", "bbbbbbb"], "/repo/root")]


@pytest.mark.parametrize("git", [FakeGit(code=128), FakeGit(raises=OSError("git missing"))], ids=["exit", "raises"])
def test_derive_deploys_flags_a_commit_it_cannot_compare(git):
    deploys = soak.derive_deploys(_deploy_writes(), SINCE, soak_until(), git_runner=git)

    assert len(deploys) == 1
    assert deploys[0]["class"] == "unknown: commit not available locally (run git fetch)"
    assert deploys[0]["is_event"] is True


def test_a_config_change_without_a_version_change_is_still_listed():
    writes, _, _ = healthy(14)
    for w in writes:
        if w["valid_time"] >= slot(5):
            w["config_fingerprint"] = "e" * 8
    git = FakeGit(["backend/config.py"])

    deploys = soak.derive_deploys(writes, SINCE, soak_until(), git_runner=git)

    assert len(deploys) == 1
    assert deploys[0]["old"] == deploys[0]["new"] == "abc1234"
    assert deploys[0]["changed"] == ["config_fingerprint"]
    assert deploys[0]["class"].startswith("unknown")
    assert git.calls == []  # nothing to compare: the version did not move


@pytest.mark.parametrize("version", ["unknown", "--output=/tmp/evil", "ABCDEF1", "abc123", "a" * 41, "abc1234; rm -rf /"])
def test_unknown_pipeline_version_is_flagged(version, tmp_path):
    git = FakeGit(["backend/config.py"])
    writes = _deploy_writes("abc1234", version)

    deploys = soak.derive_deploys(writes, SINCE, soak_until(), git_runner=git)

    assert len(deploys) == 1
    assert deploys[0]["class"].startswith("unknown")
    assert deploys[0]["is_event"] is True
    assert git.calls == []  # a value from the database never reaches git unless it is 7-40 lowercase hex

    # and it is in the report the owner reads, without failing a healthy window
    full, runs, run_rows = healthy(SOAK_HOURS)
    set_versions(full, "abc1234", version, 5)
    code, markdown, result = soak_run(tmp_path, full, runs, run_rows, git=git)
    assert code == 0
    assert result["deploys"][0]["class"].startswith("unknown")
    assert "not a commit id" in markdown
    assert git.calls == []


def test_deploy_is_context_not_an_excuse(tmp_path, capsys):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    set_versions(writes, "aaaaaaa", "bbbbbbb", 5)
    writes = drop_row(writes, "EL_PASO", slot(6))  # the breach starts at 07:30 (slot 6 + 30 min)
    probes = make_probes(writes)
    git = FakeGit(["backend/config.py"])

    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes, git=git)

    assert code == 1  # a deploy two hours before it does not explain a breach
    breach = result["breaches"][0]
    assert breach["cause"] is None and breach["explanation"] is None
    assert [(c["old"], c["new"], c["class"], c["first_written_at"]) for c in breach["context"]] == [
        ("aaaaaaa", "bbbbbbb", "config", _iso(slot(5) + LANDS_AT))]
    assert breach["id"] in capsys.readouterr().out
    assert "aaaaaaa" in markdown and "bbbbbbb" in markdown

    # an annotation is what explains it; the deploy stays as context
    note = {"explanation": "deploy of backend/config.py broke the EL_PASO child", "by": "A. Owner", "date": "2026-10-28"}
    path = tmp_path / "annotations.json"
    path.write_text(json.dumps({"breaches": {breach["id"]: note}}))
    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, probes, SOAK_HOURS, "--annotations",
                                      str(path), name="annotated", git=git)
    assert code == 0
    assert result["breaches"][0]["context"] and result["breaches"][0]["explanation"] == note

    # a deploy more than two hours before the breach is not its context, but it is still listed
    far = healthy(SOAK_HOURS)[0]
    set_versions(far, "aaaaaaa", "bbbbbbb", 1)
    far = drop_row(far, "EL_PASO", slot(6))
    code, markdown, result = soak_run(tmp_path, far, runs, run_rows, make_probes(far), name="far", git=git)
    assert code == 1
    assert result["breaches"][0]["context"] == []
    assert len(result["deploys"]) == 1


def test_manual_events_are_listed_in_time_order(tmp_path):
    writes, runs, run_rows = healthy(SOAK_HOURS)
    set_versions(writes, "aaaaaaa", "bbbbbbb", 5)
    events = [
        {"time": "2026-10-26T10:00:00Z", "what": "owner paused cron-job.org for ten minutes", "by": "A. Owner"},
        {"time": "2026-10-25T09:30:00Z", "what": "edited the dispatch job's timeout", "by": "A. Owner"},
        {"time": "2026-10-27T01:15:00Z", "what": "GitHub status incident", "by": "A. Owner"},
    ]
    path = tmp_path / "annotations.json"
    path.write_text(json.dumps({"events": events}))

    code, markdown, result = soak_run(tmp_path, writes, runs, run_rows, "auto", SOAK_HOURS, "--annotations",
                                      str(path), git=FakeGit(["data/models/forecast_AUSTIN.joblib"]))

    assert code == 0
    assert [e["time"] for e in result["events"]] == ["2026-10-25T09:30:00Z", "2026-10-26T10:00:00Z",
                                                     "2026-10-27T01:15:00Z"]
    assert result["events"][0] == {"time": "2026-10-25T09:30:00Z", "what": "edited the dispatch job's timeout",
                                   "by": "A. Owner"}
    assert [d["class"] for d in result["deploys"]] == ["model"]
    section = markdown.split("## Deploys and events during the window", 1)[1].split("\n## ", 1)[0]
    positions = [section.index(text) for text in ("edited the dispatch job's timeout",
                                                  "owner paused cron-job.org for ten minutes",
                                                  "GitHub status incident")]
    assert positions == sorted(positions)
    assert "bbbbbbb" in section and "model" in section  # the derived deploy sits beside the owner's events
