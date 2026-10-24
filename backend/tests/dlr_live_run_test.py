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

import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import requests

import anomaly_detector
import config
import dlr_live_run
import dlr_orchestrator as orch

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

time.sleep(0.05)
row = {
    "city": city, "rating_a": 1000.0, "static_rating_a": 1500.0, "fallback": False,
    "exhausted": False, "station_id": "T1", "fallback_gates": [],
    WRITE_FLAG_KEY: True, "history_rows": 168, "forecast_amps": 1100.0,
    "detector_signal": "ok", "forecast_status": "ok", "forecast_error": None,
    "detector_model_loaded": True, "pid": os.getpid(),
}
with open(args.output, "w") as fh:
    json.dump({"start": args.end, "end": args.end, "provider": args.provider,
               "forecast_method": args.forecast_method, "summary": [row], "errors": {},
               "sources": {}, "provider_errors": {}}, fh)
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


# ──────────────────────────────────────────────────────────────────────────────
# Tracer: one child per city, in order, through the real argument contract
# ──────────────────────────────────────────────────────────────────────────────

def test_tracer_every_city_runs_in_its_own_child_and_the_run_exits_zero(tmp_path, monkeypatch):
    script, calls_log = _fake_orchestrator(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", script)

    run = dlr_live_run.run_live(env=_live_env(), now=_NOW)

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
    assert argv[0] == sys.executable and argv[1] == dlr_live_run.ORCHESTRATOR

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

    run = dlr_live_run.run_live(env=_live_env(FAKE_BEHAVIOR_MIDLAND="crash"), now=_NOW)

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
