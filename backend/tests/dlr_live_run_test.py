"""
Tests for backend/dlr_live_run.py -- the live runner that rates every city in its
own `dlr_orchestrator.py` child process (production-pipeline Phase 5, PIPE-02 and
SCHED-01).

Every test runs offline. The children are a fake orchestrator script under
`tmp_path` (it parses the real orchestrator's arguments, logs what it was given
and writes an `--output` JSON shaped like the real one), `requests.get` is
guarded, and nothing is written outside `tmp_path`. Follows
backend/tests/dlr_orchestrator_test.py's conventions (no conftest.py, plain
asserts, no test classes).
"""

import contextlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests

import anomaly_detector
import config
import dlr_live_run
import dlr_orchestrator as orch
import live_run_log

_END = "2025-06-01T12:00:00Z"
_NOW = datetime(2025, 6, 1, 10, 59, 59, tzinfo=timezone.utc)


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
def _no_database(monkeypatch):
    """A test that reaches the default run-log writer fails loudly instead of connecting."""
    def refuse():
        raise AssertionError("a test opened a database connection")

    monkeypatch.setattr(live_run_log, "open_connection", refuse)


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    # Another test module loads `.env` into the process at import time.
    for name in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "default_archive.csv"))
    # Trained models are git-ignored, so a test must not depend on whether this
    # checkout has them.
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


_FAKE_SOURCE = '''
import argparse, json, os, sys, time

CALLS_LOG = __CALLS_LOG__
WRITE_FLAG_KEY = __WRITE_FLAG_KEY__

parser = argparse.ArgumentParser()
parser.add_argument("--cities", nargs="*")
parser.add_argument("--end")
parser.add_argument("--window-hours")
parser.add_argument("--provider")
parser.add_argument("--forecast-method")
parser.add_argument("--store")
parser.add_argument("--no-run-row", action="store_true")
parser.add_argument("--output")
args = parser.parse_args()

city = args.cities[0]
behavior = os.environ.get("FAKE_BEHAVIOR_" + city, "ok")
started = time.time()
with open(CALLS_LOG, "a") as fh:
    fh.write(json.dumps({
        "city": city, "pid": os.getpid(), "argv": sys.argv[1:], "started": started,
        "synoptic_token_empty": os.environ.get("SYNOPTIC_TOKEN") == "",
        "nrel_key_empty": os.environ.get("NREL_API_KEY") == "",
        "nrel_email_empty": os.environ.get("NREL_API_EMAIL") == "",
        "run_id": os.environ.get("GITHUB_RUN_ID"),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
    }) + "\\n")
print("fake orchestrator rating " + city)

if behavior == "crash":
    sys.stderr.write("Traceback (most recent call last):\\nRuntimeError: provider down for " + city
                     + " using " + os.environ.get("SYNOPTIC_TOKEN", "") + "\\n")
    sys.exit(1)

if behavior == "hang":
    time.sleep(30)
    sys.exit(0)
if behavior == "nooutput":
    sys.exit(0)

time.sleep(0.05)
row = {
    "city": city, "rating_a": 1000.0, "static_rating_a": 1500.0, "fallback": False,
    "exhausted": False, "station_id": "T1", "fallback_gates": [],
    WRITE_FLAG_KEY: True, "history_rows": 168, "forecast_amps": 1100.0,
    "detector_signal": "ok", "forecast_status": "ok", "forecast_error": None,
    "detector_model_loaded": True, "cleaning_error": None, "pid": os.getpid(),
}
if behavior == "notwritten":
    row[WRITE_FLAG_KEY] = False
elif behavior == "forecast_failed":
    row["forecast_status"] = "failed"
    row["forecast_error"] = "forecast blew up"
elif behavior == "cold_start":
    row["forecast_status"] = "cold_start"
elif behavior == "nodetector":
    row["detector_model_loaded"] = False
elif behavior == "nodetectorkey":
    del row["detector_model_loaded"]
elif behavior == "noforecaststatus":
    del row["forecast_status"]
elif behavior == "cleaning_failed":
    # no history rows, so the forecast status stays cold_start (city_pipeline WR-02)
    row["forecast_status"] = "cold_start"
    row["cleaning_error"] = "data cleaning failed: bad timestamps"
summary, errors = [row], {}
if behavior == "nosummary":
    summary, errors = [], {city: "station discovery failed"}
with open(args.output, "w") as fh:
    json.dump({"start": args.end, "end": args.end, "provider": args.provider,
               "forecast_method": args.forecast_method, "summary": summary, "errors": errors,
               "sources": {"temp": {"synoptic": 1}}, "provider_errors": {"synoptic: HTTP 429": 2}}, fh)
with open(CALLS_LOG, "a") as fh:
    fh.write(json.dumps({"city": city, "done": True, "finished": time.time()}) + "\\n")
'''


def _fake_orchestrator(tmp_path):
    """
    Write a fake `dlr_orchestrator.py`. Returns `(script_path, calls_log_path)`;
    the log gets one JSON line per child start. The fake's behaviour for a city
    comes from the child's env var FAKE_BEHAVIOR_<CITY> (default "ok").
    """
    calls_log = tmp_path / "calls.jsonl"
    script = tmp_path / "fake_orchestrator.py"
    script.write_text(
        _FAKE_SOURCE.replace("__CALLS_LOG__", repr(str(calls_log)))
                    .replace("__WRITE_FLAG_KEY__", repr(dlr_live_run.WRITE_FLAG_KEY)))
    return str(script), calls_log


def _log_lines(calls_log):
    return [json.loads(line) for line in calls_log.read_text().splitlines()]


def _calls(calls_log):
    """One entry per child start."""
    return [entry for entry in _log_lines(calls_log) if "done" not in entry]


def _finishes(calls_log):
    """One entry per child that ran to its end."""
    return [entry for entry in _log_lines(calls_log) if "done" in entry]


def _live_env(**extra):
    """The process env plus a dummy value for every required variable."""
    env = dict(os.environ)
    for name in dlr_live_run.REQUIRED_ENV:
        env[name] = f"dummy-{name.lower()}"
    env.update(extra)
    return env


def _arg(argv, flag):
    return argv[argv.index(flag) + 1]


def _no_record(row):
    """A run-log writer that records nothing, for tests of everything but the run log."""


# ──────────────────────────────────────────────────────────────────────────────
# Tracer: one child per city, in order, through the real argument contract
# ──────────────────────────────────────────────────────────────────────────────

def test_tracer_every_city_runs_in_its_own_child_and_the_run_exits_zero(tmp_path, monkeypatch):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)

    run = dlr_live_run.run_live(env=_live_env(), now=_NOW, record_fn=_no_record)

    assert run["exit_code"] == 0
    assert [r["city"] for r in run["cities"]] == list(config.LOCATIONS)
    assert [r["outcome"] for r in run["cities"]] == ["ok"] * len(config.LOCATIONS)
    assert run["end"] == "2025-06-01T10:55:00Z" and run["slot"] == "2025-06-01T10:00:00Z"

    calls = _calls(calls_log)
    assert [c["city"] for c in calls] == list(config.LOCATIONS)  # config.LOCATIONS order
    assert len({c["pid"] for c in calls}) == len(config.LOCATIONS)  # four distinct children
    store = list(dlr_live_run.STORE_ARGS)
    for call in calls:
        argv = call["argv"]
        assert _arg(argv, "--cities") == call["city"]
        assert _arg(argv, "--end") == run["end"]  # one shared end
        assert _arg(argv, "--provider") == "composed"
        assert _arg(argv, "--forecast-method") == "ml"
        assert any(argv[i:i + len(store)] == store for i in range(len(argv)))
    # ordering edge: strictly one after another, each child done before the next starts
    finishes = _finishes(calls_log)
    assert [f["city"] for f in finishes] == list(config.LOCATIONS)
    for done, following in zip(finishes, calls[1:]):
        assert done["finished"] <= following["started"]


def test_child_argv_is_accepted_by_the_real_orchestrator_cli(tmp_path, monkeypatch, capsys):
    seen = []

    def fake(**kwargs):
        seen.append(kwargs)
        return {"start": "2025-06-01T11:00:00Z", "end": _END, "provider": "composed",
                "forecast_method": "ml", "summary": [], "errors": {}, "sources": {},
                "provider_errors": {}}

    monkeypatch.setattr(orch, "run_dlr_pipeline", fake)
    argv = dlr_live_run.child_argv("MIDLAND", _END, str(tmp_path / "out.json"))
    assert argv[0] == os.path.abspath(sys.executable) and argv[1] == dlr_live_run.ORCHESTRATOR

    assert orch.main(argv[2:]) == 0

    assert len(seen) == 1
    call = seen[0]
    assert call["cities"] == ["MIDLAND"]
    assert call["end"] == _END
    assert call["provider"] == "composed"
    assert call["forecast_method"] == "ml"
    assert call["store"] == "postgres" and call["record_run"] is False  # STORE_ARGS (DB-02)
    assert json.loads((tmp_path / "out.json").read_text())["end"] == _END


def test_a_crashing_city_is_recorded_and_the_rest_still_run(tmp_path, monkeypatch):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)

    run = dlr_live_run.run_live(
        env=_live_env(FAKE_BEHAVIOR_MIDLAND="crash"), now=_NOW, record_fn=_no_record)

    by_city = {r["city"]: r for r in run["cities"]}
    assert by_city["MIDLAND"]["outcome"] == "error"
    assert by_city["MIDLAND"]["error"]
    assert [by_city[c]["outcome"] for c in config.LOCATIONS if c != "MIDLAND"] == ["ok"] * 3
    assert [c["city"] for c in _calls(calls_log)] == list(config.LOCATIONS)
    assert run["exit_code"] == 1


def test_run_end_and_slot_edges():
    """Adjacency: the end is floored to 5 minutes, the slot to the hour (OD-7)."""
    def at(h, m, s):
        return datetime(2025, 6, 1, h, m, s, tzinfo=timezone.utc)

    assert dlr_live_run.run_end(at(10, 0, 0)) == "2025-06-01T10:00:00Z"
    assert dlr_live_run.slot_of(dlr_live_run.run_end(at(10, 0, 0))) == "2025-06-01T10:00:00Z"
    assert dlr_live_run.run_end(at(10, 59, 59)) == "2025-06-01T10:55:00Z"
    assert dlr_live_run.slot_of(dlr_live_run.run_end(at(10, 59, 59))) == "2025-06-01T10:00:00Z"
    # two dispatches in the same UTC hour share a slot; the next hour has its own
    assert (dlr_live_run.slot_of(dlr_live_run.run_end(at(10, 7, 30)))
            == dlr_live_run.slot_of(dlr_live_run.run_end(at(10, 52, 1))))
    assert dlr_live_run.slot_of(dlr_live_run.run_end(at(11, 0, 0))) == "2025-06-01T11:00:00Z"
    # an aware datetime in another zone is read as the instant it is, a naive one as UTC
    central = timezone(timedelta(hours=-5))
    assert dlr_live_run.run_end(datetime(2025, 6, 1, 5, 59, 59, tzinfo=central)) == "2025-06-01T10:55:00Z"
    assert dlr_live_run.run_end(datetime(2025, 6, 1, 10, 59, 59)) == "2025-06-01T10:55:00Z"

    # run_identity: GITHUB_RUN_ID / GITHUB_RUN_ATTEMPT when set, else a local id
    assert dlr_live_run.run_identity({"GITHUB_RUN_ID": "12345", "GITHUB_RUN_ATTEMPT": "3"}) == ("12345", 3)
    assert dlr_live_run.run_identity({"GITHUB_RUN_ID": "12345"}) == ("12345", 1)
    run_id, attempt = dlr_live_run.run_identity({}, now=_NOW)
    assert run_id == f"local-20250601T105959Z-{os.getpid()}" and attempt == 1


# ──────────────────────────────────────────────────────────────────────────────
# Task 2: timeouts, empty output, model status, fault drill, env, redaction, summary
# ──────────────────────────────────────────────────────────────────────────────

def _run_one(tmp_path, monkeypatch, behavior, city="MIDLAND", **kwargs):
    """Run a single city whose fake child behaves as `behavior`; returns (run, record)."""
    script, _ = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)
    run = dlr_live_run.run_live(
        cities=[city], env=_live_env(**{f"FAKE_BEHAVIOR_{city}": behavior}), now=_NOW,
        record_fn=_no_record, **kwargs)
    return run, run["cities"][0]


def _set_required_env(monkeypatch):
    for name in dlr_live_run.REQUIRED_ENV:
        monkeypatch.setenv(name, f"dummy-{name.lower()}")


def test_a_hung_city_is_killed_at_the_timeout_and_the_rest_still_run(tmp_path, monkeypatch):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)
    began = time.monotonic()

    run = dlr_live_run.run_live(
        env=_live_env(FAKE_BEHAVIOR_MIDLAND="hang"), now=_NOW, timeout_s=2, record_fn=_no_record)

    assert time.monotonic() - began < 25  # the hung child slept for 30 s
    by_city = {r["city"]: r for r in run["cities"]}
    assert by_city["MIDLAND"]["outcome"] == "timeout"
    assert by_city["MIDLAND"]["exit_code"] is None
    assert by_city["MIDLAND"]["written"] is False
    assert by_city["MIDLAND"]["forecast_status"] == "not_run"
    assert [r["city"] for r in run["cities"]] == list(config.LOCATIONS)
    # the city after the hung one still ran, and the run is red
    assert by_city["EL_PASO"]["outcome"] == "ok"
    assert [c["city"] for c in _calls(calls_log)] == list(config.LOCATIONS)
    assert run["exit_code"] == 1


@pytest.mark.parametrize("behavior, expected_text", [
    ("nooutput", "no output"),
    ("nosummary", "no summary row"),
    ("notwritten", "row not written"),
])
def test_exit_zero_without_a_written_row_is_an_error(tmp_path, monkeypatch, behavior, expected_text):
    run, record = _run_one(tmp_path, monkeypatch, behavior)

    assert record["exit_code"] == 0  # the child said it was fine; the missing row says otherwise
    assert record["outcome"] == "error"
    assert expected_text in record["error"]
    assert record["written"] is False
    assert record["forecast_status"] == "not_run"
    assert run["exit_code"] == 1
    if behavior == "nosummary":
        assert "station discovery failed" in record["error"]  # the child's own errors[city]


@pytest.mark.parametrize("behavior, expected_exit", [
    ("forecast_failed", 1),
    ("nodetector", 1),
    ("nodetectorkey", 1),  # a missing detector_model_loaded counts as false
    ("noforecaststatus", 1),  # no forecast status is not evidence of an ML forecast
    ("cleaning_failed", 1),  # any stored reason makes a written city degraded
    ("cold_start", 0),
])
def test_failed_forecast_or_missing_anomaly_model_fails_the_run_but_keeps_the_row(
        tmp_path, monkeypatch, behavior, expected_exit):
    run, record = _run_one(tmp_path, monkeypatch, behavior)

    assert record["outcome"] == "ok"  # the row was written; the run is judged separately
    assert record["written"] is True
    assert run["exit_code"] == expected_exit
    if behavior == "forecast_failed":
        assert record["forecast_status"] == "failed"
        assert record["forecast_error"] == "forecast blew up"
    if behavior == "cold_start":
        assert record["forecast_status"] == "cold_start"
    if behavior in ("nodetector", "nodetectorkey"):
        assert record["detector_model_loaded"] is False
    if behavior == "noforecaststatus":
        assert record["forecast_status"] is None
    if behavior == "cleaning_failed":
        assert record["cleaning_error"] == "data cleaning failed: bad timestamps"
    else:
        assert record["cleaning_error"] is None
    assert record["provider_errors"] == {"synoptic: HTTP 429": 2}


def test_fault_city_blanks_provider_credentials_for_that_child_only(tmp_path, monkeypatch):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)
    env = _live_env()

    run = dlr_live_run.run_live(fault_city="MIDLAND", env=env, now=_NOW, record_fn=_no_record)

    calls = {c["city"]: c for c in _calls(calls_log)}
    for city, call in calls.items():
        blanked = city == "MIDLAND"
        assert call["synoptic_token_empty"] is blanked, city
        assert call["nrel_key_empty"] is blanked, city
        assert call["nrel_email_empty"] is blanked, city
    assert {r["city"]: r["fault_injected"] for r in run["cities"]} == {
        c: c == "MIDLAND" for c in config.LOCATIONS}
    assert env["SYNOPTIC_TOKEN"] == "dummy-synoptic_token"  # the caller's env is never edited

    # DLR_LIVE_FAULT_CITY in the environment is the default of --fault-city
    calls_log.unlink()
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DLR_LIVE_FAULT_CITY", "EL_PASO")
    assert dlr_live_run.main(["--cities", "EL_PASO", "AUSTIN", "--no-run-log"]) == 0
    assert {c["city"]: c["synoptic_token_empty"] for c in _calls(calls_log)} == {
        "EL_PASO": True, "AUSTIN": False}


def test_unknown_fault_city_is_a_usage_error(tmp_path, monkeypatch):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)

    with pytest.raises(SystemExit) as raised:
        dlr_live_run.main(["--fault-city", "HOUSTON"])
    assert raised.value.code == 2

    # the same value arriving through the workflow's env mapping
    monkeypatch.setenv("DLR_LIVE_FAULT_CITY", "HOUSTON")
    with pytest.raises(SystemExit) as raised:
        dlr_live_run.main([])
    assert raised.value.code == 2

    with pytest.raises(ValueError):
        dlr_live_run.run_live(fault_city="HOUSTON", env=_live_env(), now=_NOW)
    assert not calls_log.exists()  # no child ever started


def test_missing_required_env_stops_before_any_child_and_never_prints_values(
        tmp_path, monkeypatch, capsys, caplog):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)
    _set_required_env(monkeypatch)
    monkeypatch.delenv("NREL_API_KEY")  # unset
    monkeypatch.setenv("SUPABASE_DB_URL", "")  # empty
    caplog.set_level(logging.INFO)

    assert dlr_live_run.main([]) == 1

    assert not calls_log.exists()
    out, err = capsys.readouterr()
    shown = caplog.text + out + err
    assert "NREL_API_KEY" in shown and "SUPABASE_DB_URL" in shown
    for name in ("SYNOPTIC_TOKEN", "NREL_API_EMAIL"):
        assert name not in shown  # only the missing names are listed
        assert f"dummy-{name.lower()}" not in shown  # and no value is ever printed


def _db_url():
    """A database URL built at run time, so no tracked file holds a credential-shaped literal."""
    return "".join(["post", "gresql://", "writer.proj", ":", "pw-", "secret-1", "@", "pooler.example.test", ":5432/db"])


def test_redact_removes_secret_values_query_credentials_and_db_urls():
    env = {name: f"value-of-{name.lower()}" for name in dlr_live_run.PROVIDER_ENV}
    env["SUPABASE_DB_URL"] = _db_url()
    env["NREL_API_KEY"] = "abc"  # shorter than 4 characters: too short to be worth matching as a value
    text = " ".join([
        "GET /obs?" + "to" + "ken=abc123&x=1", "api_" + "key=k-1", "apikey=k-2", "KEY=k-3",
        "email=someone@example.test", "pass" + "word=pw-3", "driver said " + _db_url(),
        "plain " + "postgres" + "://other-user:other-pw@host/db",
        "echo " + env["SYNOPTIC_TOKEN"] + " and " + env["NREL_API_EMAIL"],
        "bare password pw-secret-1 and abc",
    ])

    cleaned = dlr_live_run.redact(text, env)

    for leaked in ("abc123", "k-1", "k-2", "k-3", "someone@example.test", "pw-3", "pw-secret-1",
                   "pooler.example.test", "other-pw", env["SYNOPTIC_TOKEN"], env["NREL_API_EMAIL"]):
        assert leaked not in cleaned, leaked
    assert "token=***" in cleaned and "email=***" in cleaned
    assert "postgresql://***" in cleaned
    assert "x=1" in cleaned  # only the credential is removed, not the whole query
    assert "abc" in cleaned.split("bare password ***")[-1]  # values shorter than 4 characters stay

    assert len(dlr_live_run.redact("x" * 5000, {})) == 1000
    assert dlr_live_run.redact("head-" + "x" * 1500 + "-tail", {}).endswith("-tail")


def test_step_summary_lists_cities_in_order_with_redacted_errors(tmp_path, monkeypatch):
    script, _ = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)
    _set_required_env(monkeypatch)
    summary = tmp_path / "step_summary.md"
    summary.write_text("earlier step output\n")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_RUN_ID", "9001")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "2")
    monkeypatch.setenv("FAKE_BEHAVIOR_MIDLAND", "crash")
    out_json = tmp_path / "run.json"

    assert dlr_live_run.main(
        ["--end", "2025-06-01T10:55:00Z", "--summary-json", str(out_json), "--no-run-log"]) == 1

    text = summary.read_text()
    assert text.startswith("earlier step output\n")  # appended, never overwritten
    assert "## DLR live run 9001 attempt 2 (slot 2025-06-01T10:00:00Z)" in text
    rows = [line for line in text.splitlines() if line.startswith("| ") and "---" not in line][1:]
    assert [row.split("|")[1].strip() for row in rows] == list(config.LOCATIONS)
    midland = next(row for row in rows if "MIDLAND" in row)
    assert "error" in midland
    assert "dummy-synoptic_token" not in text  # the crash text echoed the token; it is redacted
    assert json.loads(out_json.read_text())["exit_code"] == 1

    # a long error is cut to its last 120 characters and its pipes are escaped, whatever the child printed
    run = {"run_id": "r1", "run_attempt": 1, "slot": "2025-06-01T10:00:00Z", "cities": [
        {"city": "AUSTIN", "outcome": "error", "rating_a": None, "fallback": None, "written": False,
         "forecast_status": "not_run", "detector_model_loaded": False, "fault_injected": True,
         "error": "head-marker " + "z" * 400 + " a|b " + _db_url()}]}
    other = tmp_path / "other.md"
    dlr_live_run.write_step_summary(run, str(other), env={"SUPABASE_DB_URL": _db_url()})
    row = next(line for line in other.read_text().splitlines() if line.startswith("| AUSTIN"))
    cell = row.rstrip().removesuffix(" |").split(" | ")[-1].strip()
    assert "a\\|b" in cell and "pw-secret-1" not in cell
    assert len(cell.replace("\\|", "|")) <= 120
    assert "head-marker" not in cell


def test_step_summary_error_cell_shows_the_exception_line_of_a_traceback(tmp_path):
    # WR-01: the reason is the LAST line of a traceback; the cell must not cut it off
    traceback_text = (
        "Traceback (most recent call last):\n"
        '  File "/work/backend/dlr_orchestrator.py", line 411, in <module>\n'
        "    main()\n"
        '  File "/work/backend/dlr_orchestrator.py", line 300, in main\n'
        "    token = _require_token()\n"
        "OSError: Set SYNOPTIC_TOKEN in .env before running"
    )
    run = {"run_id": "r1", "run_attempt": 1, "slot": "2025-06-01T10:00:00Z", "cities": [
        {"city": "AUSTIN", "outcome": "error", "rating_a": None, "fallback": None, "written": False,
         "forecast_status": "not_run", "detector_model_loaded": False, "fault_injected": True,
         "error": traceback_text}]}
    path = tmp_path / "summary.md"
    dlr_live_run.write_step_summary(run, str(path), env={})
    row = next(line for line in path.read_text().splitlines() if line.startswith("| AUSTIN"))
    cell = row.rstrip().removesuffix(" |").split(" | ")[-1].strip()
    assert cell.endswith("OSError: Set SYNOPTIC_TOKEN in .env before running")
    assert len(cell) <= 120


# ──────────────────────────────────────────────────────────────────────────────
# Plan 05-03: the runner keeps the run's pipeline_run row (SCHED-01, OD-9)
# ──────────────────────────────────────────────────────────────────────────────

def _reached(row):
    """How many cities a pipeline_run row covers."""
    return len(row["cities_ok"]) + len(row["cities_failed"])


class _RunConn:
    """A stand-in writer connection: records statements and whether it was closed."""

    def __init__(self):
        self.calls = []
        self.closed = False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))

    @contextlib.contextmanager
    def transaction(self):
        yield

    def close(self):
        self.closed = True


def test_run_row_is_written_at_start_after_each_city_and_at_the_end(tmp_path, monkeypatch):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)
    events = []

    def record(row):
        events.append({"row": row, "at": time.time()})

    run = dlr_live_run.run_live(
        env=_live_env(FAKE_BEHAVIOR_CORPUS_CHRISTI="crash", FAKE_BEHAVIOR_MIDLAND="hang"),
        now=_NOW, timeout_s=2, record_fn=record)

    austin, corpus, midland, el_paso = config.LOCATIONS[:4]
    rows = [e["row"] for e in events]
    assert len(rows) == 6  # once at start, once per city, once at the end
    # the first row exists before any child runs, with nothing in it and no finish time
    assert rows[0]["cities_ok"] == [] and rows[0]["cities_failed"] == {} and rows[0]["finished_at"] is None
    assert [_reached(r) for r in rows[:5]] == [0, 1, 2, 3, 4]
    assert rows[1]["cities_ok"] == [austin]
    assert rows[2]["cities_failed"][corpus]["outcome"] == "error"
    assert rows[3]["cities_failed"][midland]["outcome"] == "timeout"
    assert rows[3]["cities_failed"][midland]["written"] is False  # OD-9: no rating row
    assert rows[4]["cities_ok"] == [austin, el_paso]
    # finished only by the last write, which repeats the final cities
    assert [r["finished_at"] is None for r in rows] == [True] * 5 + [False]
    assert rows[5]["cities_ok"] == rows[4]["cities_ok"] and rows[5]["cities_failed"] == rows[4]["cities_failed"]
    # every row names this run and its window
    window_end = datetime.strptime(run["end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    for row in rows:
        assert (row["run_id"], row["run_attempt"], row["window_end"]) == (
            run["run_id"], run["run_attempt"], window_end)
    # each child's composer counts arrive keyed by city; a failed child has none
    assert rows[5]["sources"] == {austin: {"temp": {"synoptic": 1}}, el_paso: {"temp": {"synoptic": 1}}}
    assert rows[5]["provider_errors"][austin] == {"synoptic: HTTP 429": 2}
    assert corpus not in rows[5]["provider_errors"]
    # the crashed child echoed a secret on stderr; no row carries it
    assert "dummy-synoptic_token" not in json.dumps(rows, default=str)
    # ordering: the AUSTIN update arrives before the CORPUS_CHRISTI child starts, the first row before AUSTIN
    started = {c["city"]: c["started"] for c in _calls(calls_log)}
    assert events[0]["at"] <= started[austin]
    assert events[1]["at"] <= started[corpus]
    assert events[5]["at"] >= max(f["finished"] for f in _finishes(calls_log))
    assert run["run_log"] == {"writes": 6, "failed": 0}
    assert run["exit_code"] == 1  # a crashed and a timed-out city


def test_a_run_log_failure_fails_the_run_but_not_the_other_cities(tmp_path, monkeypatch, caplog):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)
    caplog.set_level(logging.INFO)
    secret_url = _db_url()
    recorded = []

    def record(row):
        if _reached(row) == 2:  # the update after the second city, CORPUS_CHRISTI
            raise RuntimeError("connection to " + secret_url + " refused for dummy-synoptic_token")
        recorded.append(row)

    run = dlr_live_run.run_live(env=_live_env(SUPABASE_DB_URL=secret_url), now=_NOW, record_fn=record)

    # every city still ran and was recorded; the run is red only because of the run log
    assert [c["city"] for c in _calls(calls_log)] == list(config.LOCATIONS)
    assert [r["outcome"] for r in run["cities"]] == ["ok"] * len(config.LOCATIONS)
    assert len(recorded) == 5  # six writes, one of them raised
    assert recorded[-1]["finished_at"] is not None and recorded[-1]["cities_ok"] == list(config.LOCATIONS)
    assert run["run_log"] == {"writes": 6, "failed": 1}
    assert run["exit_code"] == 1
    # the logged message names the exception type and is redacted
    assert "pipeline_run write failed" in caplog.text and "RuntimeError" in caplog.text
    for secret in (secret_url, "pw-secret-1", "pooler.example.test", "dummy-synoptic_token"):
        assert secret not in caplog.text, secret


def test_no_run_log_flag_skips_recording(tmp_path, monkeypatch):
    script, _ = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)
    _set_required_env(monkeypatch)
    summary = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    opened = []

    def refuse():
        opened.append(1)
        raise AssertionError("--no-run-log must not open a connection")

    monkeypatch.setattr(live_run_log, "open_connection", refuse)

    assert dlr_live_run.main(["--cities", "AUSTIN", "--no-run-log"]) == 0

    assert opened == []
    assert "pipeline_run: skipped (--no-run-log)" in summary.read_text()

    # without the flag: the default writer takes a fresh connection for every write and closes it
    conns = []

    def open_conn():
        conns.append(_RunConn())
        return conns[-1]

    monkeypatch.setattr(live_run_log, "open_connection", open_conn)

    assert dlr_live_run.main(["--cities", "AUSTIN"]) == 0

    assert len(conns) == 3  # start, after AUSTIN, end
    assert all(c.closed and len(c.calls) == 1 for c in conns)
    assert [c.calls[0][1]["finished_at"] is None for c in conns] == [True, True, False]
    assert all("insert into public.pipeline_run" in c.calls[0][0] for c in conns)
    assert "pipeline_run: 3 writes, 0 failed" in summary.read_text()
