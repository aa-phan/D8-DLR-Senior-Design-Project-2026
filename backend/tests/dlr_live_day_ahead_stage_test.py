"""
Tests for the day-ahead stage of backend/dlr_live_run.py (production-pipeline Phase 8,
DAY-04; decisions D-02 and D-15).

The stage runs after the ratings have fixed the exit code. These tests prove it is
structurally unable to change that code, fits the shared time budget, and records its
own outcome. Every test runs offline. The rating children are the fake orchestrator
from dlr_live_run_test.py; the day-ahead children are a fake script under `tmp_path`
that follows the argv/output contract 08-04's real `dlr_day_ahead.py` will implement,
driven by FAKE_DA_BEHAVIOR_<CITY> = issued | partial | none_due | crash | hang |
nooutput | leak. `requests.get` is guarded and nothing connects to a database.
"""

import json
import logging
import os
import sys
import time
from types import SimpleNamespace

import pytest
import requests

import anomaly_detector
import config
import dlr_live_run
import live_run_log
from dlr_live_run_test import (
    _NOW,
    _RunConn,
    _calls,
    _db_url,
    _fake_orchestrator,
    _finishes,
    _live_env,
    _no_record,
    _set_required_env,
)

_T1 = "2025-06-01T12:00:00Z"
_T2 = "2025-06-01T18:00:00Z"
_T3 = "2025-06-02T00:00:00Z"
_TIMING_KEYS = ("started_at", "finished_at", "duration_s")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


@pytest.fixture(autouse=True)
def _no_database(monkeypatch):
    def refuse():
        raise AssertionError("a test opened a database connection")

    monkeypatch.setattr(live_run_log, "open_connection", refuse)


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    for name in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "default_archive.csv"))
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


_FAKE_DA_SOURCE = '''
import argparse, json, os, sys, time

CALLS_LOG = __CALLS_LOG__
parser = argparse.ArgumentParser()
parser.add_argument("--city")
parser.add_argument("--output")
args = parser.parse_args()

city = args.city
behavior = os.environ.get("FAKE_DA_BEHAVIOR_" + city, "issued")
with open(CALLS_LOG, "a") as fh:
    fh.write(json.dumps({
        "city": city, "pid": os.getpid(), "argv": sys.argv[1:], "started": time.time(),
        "cwd": os.getcwd(),
        "synoptic_token_empty": os.environ.get("SYNOPTIC_TOKEN") == "",
        "db_url_set": bool(os.environ.get("SUPABASE_DB_URL")),
        "run_id": os.environ.get("GITHUB_RUN_ID"),
    }) + "\\n")
print("fake day-ahead child " + city)

T1, T2, T3 = "2025-06-01T12:00:00Z", "2025-06-01T18:00:00Z", "2025-06-02T00:00:00Z"

if behavior == "crash":
    sys.stderr.write("Traceback (most recent call last):\\nRuntimeError: cooling down for " + city
                     + " using " + os.environ.get("SYNOPTIC_TOKEN", "") + "\\n")
    sys.exit(1)
if behavior == "hang":
    time.sleep(30)
    sys.exit(0)
if behavior == "nooutput":
    sys.exit(0)

out = {"city": city, "decision_time": "2025-06-01T10:55:00Z", "outcome": "issued",
       "due": [T1, T2], "already_present": [], "issued": [T1, T2], "not_issued": {},
       "band_sources": {T1: "test-split", T2: "live-rolling"}, "out_of_bounds": [],
       "cooling_model_sha256": "ab" * 32, "duration_s": 0.1}
if behavior == "partial":
    out.update(outcome="partial", due=[T1, T2, T3], already_present=[T1], issued=[T2],
               not_issued={T3: "cooling forecast failed"}, band_sources={T2: "test-split"})
elif behavior == "none_due":
    out.update(outcome="none_due", due=[], issued=[], band_sources={})
elif behavior == "leak":
    secret = os.environ.get("SYNOPTIC_TOKEN", "") + " via " + os.environ.get("SUPABASE_DB_URL", "")
    out.update(outcome="partial", due=[T1], issued=[], band_sources={},
               not_issued={T1: "failed with " + secret + " " + "x" * 3000 + " tail " + secret})
with open(args.output, "w") as fh:
    json.dump(out, fh)
'''


def _fake_day_ahead(tmp_path):
    """Write the fake day-ahead child; returns `(script_path, calls_log_path)`."""
    calls_log = tmp_path / "da_calls.jsonl"
    script = tmp_path / "fake_day_ahead.py"
    script.write_text(_FAKE_DA_SOURCE.replace("__CALLS_LOG__", repr(str(calls_log))))
    return str(script), calls_log


def _da_calls(calls_log):
    if not calls_log.exists():
        return []
    return [json.loads(line) for line in calls_log.read_text().splitlines()]


def _patch_children(tmp_path, monkeypatch):
    rating_script, rating_log = _fake_orchestrator(tmp_path)
    da_script, da_log = _fake_day_ahead(tmp_path)
    monkeypatch.setattr(dlr_live_run, "ORCHESTRATOR", rating_script)
    monkeypatch.setattr(dlr_live_run, "DAY_AHEAD_CHILD", da_script)
    return rating_log, da_log


def _strip_timing(records):
    return [{k: v for k, v in rec.items() if k not in _TIMING_KEYS} for rec in records]


def _spy_timeouts(monkeypatch):
    seen = []
    real = dlr_live_run.run_day_ahead_city

    def spy(city, workdir, timeout_s, env):
        seen.append((city, timeout_s))
        return real(city, workdir, timeout_s, env)

    monkeypatch.setattr(dlr_live_run, "run_day_ahead_city", spy)
    return seen


# ──────────────────────────────────────────────────────────────────────────────
# the child contract
# ──────────────────────────────────────────────────────────────────────────────

def test_child_argv_follows_the_contract_and_carries_no_secret():
    argv = dlr_live_run.day_ahead_child_argv("MIDLAND", "/tmp/out.json")

    assert argv == [os.path.abspath(sys.executable), dlr_live_run.DAY_AHEAD_CHILD,
                    "--city", "MIDLAND", "--output", "/tmp/out.json"]
    assert os.path.isabs(argv[0])
    assert os.path.basename(dlr_live_run.DAY_AHEAD_CHILD) == "dlr_day_ahead.py"
    assert dlr_live_run.DAY_AHEAD_CITY_TIMEOUT_S == 150
    assert dlr_live_run.DAY_AHEAD_MIN_START_S == 60
    assert dlr_live_run.DAY_AHEAD_SHARED_BUDGET_S == len(config.LOCATIONS) * dlr_live_run.CITY_TIMEOUT_S
    assert dlr_live_run.DAY_AHEAD_OUTCOMES == (
        "none_due", "issued", "partial", "error", "timeout", "skipped_budget")


def test_classification_keeps_the_childs_outcome_and_computes_missing():
    env = _live_env()
    out = {"city": "MIDLAND", "outcome": "partial", "due": [_T1, _T2, _T3],
           "already_present": [_T1], "issued": [_T2], "not_issued": {_T3: "cooling failed"},
           "band_sources": {_T2: "test-split"}, "out_of_bounds": [_T2],
           "cooling_model_sha256": "cd" * 32}

    rec = dlr_live_run.classify_day_ahead("MIDLAND", 0, out, "", env=env)

    assert rec["outcome"] == "partial" and rec["city"] == "MIDLAND" and rec["exit_code"] == 0
    assert rec["due"] == [_T1, _T2, _T3] and rec["issued"] == [_T2]
    assert rec["missing"] == [_T3]  # due minus already present minus issued
    assert rec["reasons"] == {_T3: "cooling failed"}
    assert rec["band_sources"] == {_T2: "test-split"} and rec["out_of_bounds"] == [_T2]
    assert rec["cooling_model_sha256"] == "cd" * 32
    for outcome in ("none_due", "issued", "error"):
        assert dlr_live_run.classify_day_ahead(
            "MIDLAND", 0, dict(out, outcome=outcome), "", env=env)["outcome"] == outcome


def test_classification_of_a_crash_a_missing_output_a_kill_and_a_bad_outcome():
    env = _live_env()

    crash = dlr_live_run.classify_day_ahead("MIDLAND", 1, None, "boom\nRuntimeError: no model", env=env)
    nothing = dlr_live_run.classify_day_ahead("MIDLAND", 0, None, "", env=env)
    killed = dlr_live_run.classify_day_ahead("MIDLAND", None, None, "partial", timed_out=True, env=env)
    odd = dlr_live_run.classify_day_ahead("MIDLAND", 0, {"outcome": "great"}, "", env=env)
    crashed_with_output = dlr_live_run.classify_day_ahead(
        "MIDLAND", 3, {"outcome": "issued", "issued": [_T1]}, "", env=env)

    assert crash["outcome"] == "error" and "RuntimeError: no model" in crash["reasons"]["child"]
    assert nothing["outcome"] == "error" and nothing["reasons"]["child"] == "no output"
    assert killed["outcome"] == "timeout" and "killed" in killed["reasons"]["child"]
    assert odd["outcome"] == "error"
    assert crashed_with_output["outcome"] == "error"  # a non-zero exit is never trusted as issued
    for rec in (crash, nothing, killed, odd):
        assert rec["issued"] == [] and rec["missing"] == []


def test_classification_redacts_and_cuts_every_reason_text():
    token = "dummy-synoptic_token"
    env = _live_env(SUPABASE_DB_URL=_db_url())
    long_reason = "failed with " + token + " via " + _db_url() + " email=a@b.test " + "x" * 3000
    out = {"outcome": "partial", "due": [_T1], "issued": [], "not_issued": {_T1: long_reason}}

    rec = dlr_live_run.classify_day_ahead("MIDLAND", 0, out, "", env=env)
    short = dlr_live_run.classify_day_ahead(
        "MIDLAND", 0, {"outcome": "partial", "due": [_T1], "not_issued": {_T1: "bad " + token + " " + _db_url()}},
        "", env=env)
    crash = dlr_live_run.classify_day_ahead("MIDLAND", 1, None, "Traceback\nValueError: " + token, env=env)

    assert len(rec["reasons"][_T1]) <= 1000
    for text in (rec["reasons"][_T1], short["reasons"][_T1], crash["reasons"]["child"]):
        assert token not in text and "pw-secret-1" not in text and "pooler.example.test" not in text
    assert "***" in short["reasons"][_T1]


# ──────────────────────────────────────────────────────────────────────────────
# default off, main() on
# ──────────────────────────────────────────────────────────────────────────────

def test_run_live_starts_no_day_ahead_child_by_default(tmp_path, monkeypatch):
    _, da_log = _patch_children(tmp_path, monkeypatch)
    rows = []

    run = dlr_live_run.run_live(env=_live_env(), now=_NOW, record_fn=rows.append)

    assert run["exit_code"] == 0
    assert _da_calls(da_log) == []
    assert "day_ahead" not in run and "day_ahead_run_log" not in run
    assert len(rows) == 6 and all("day_ahead" not in row for row in rows)


def test_main_runs_the_stage_unless_no_day_ahead(tmp_path, monkeypatch):
    _, da_log = _patch_children(tmp_path, monkeypatch)
    _set_required_env(monkeypatch)
    monkeypatch.setattr(dlr_live_run, "MAIN_RUNS_DAY_AHEAD", True)

    assert dlr_live_run.main(["--cities", "AUSTIN", "--no-run-log"]) == 0
    assert [c["city"] for c in _da_calls(da_log)] == ["AUSTIN"]

    da_log.unlink()
    assert dlr_live_run.main(["--cities", "AUSTIN", "--no-run-log", "--no-day-ahead"]) == 0
    assert _da_calls(da_log) == []

    monkeypatch.setattr(dlr_live_run, "MAIN_RUNS_DAY_AHEAD", False)
    assert dlr_live_run.main(["--cities", "AUSTIN", "--no-run-log"]) == 0
    assert _da_calls(da_log) == []


# ──────────────────────────────────────────────────────────────────────────────
# isolation and order (D-02, D-15)
# ──────────────────────────────────────────────────────────────────────────────

def test_a_crashing_hanging_or_silent_day_ahead_child_never_changes_the_rating_result(
        tmp_path, monkeypatch):
    _patch_children(tmp_path, monkeypatch)
    monkeypatch.setattr(dlr_live_run, "DAY_AHEAD_CITY_TIMEOUT_S", 2)
    austin, corpus, midland, el_paso = config.LOCATIONS[:4]
    baseline = dlr_live_run.run_live(env=_live_env(), now=_NOW, record_fn=_no_record)
    began = time.monotonic()

    run = dlr_live_run.run_live(
        env=_live_env(FAKE_DA_BEHAVIOR_AUSTIN="crash", FAKE_DA_BEHAVIOR_CORPUS_CHRISTI="hang",
                      FAKE_DA_BEHAVIOR_MIDLAND="nooutput"),
        now=_NOW, record_fn=_no_record, day_ahead=True)

    assert time.monotonic() - began < 25  # the hung child slept for 30 s
    outcomes = {city: rec["outcome"] for city, rec in run["day_ahead"]["cities"].items()}
    assert outcomes == {austin: "error", corpus: "timeout", midland: "error", el_paso: "issued"}
    assert list(run["day_ahead"]["cities"]) == list(config.LOCATIONS)
    assert run["exit_code"] == 0 and baseline["exit_code"] == 0
    assert _strip_timing(run["cities"]) == _strip_timing(baseline["cities"])
    assert run["run_log"] == baseline["run_log"] == {"writes": 6, "failed": 0}


def test_a_failing_rating_child_keeps_exit_one_whatever_the_day_ahead_result(tmp_path, monkeypatch):
    _patch_children(tmp_path, monkeypatch)

    run = dlr_live_run.run_live(
        env=_live_env(FAKE_BEHAVIOR_MIDLAND="crash"), now=_NOW, record_fn=_no_record, day_ahead=True)

    assert run["exit_code"] == 1
    assert {r["outcome"] for r in run["day_ahead"]["cities"].values()} == {"issued"}


def test_no_day_ahead_child_starts_before_the_ratings_finished_and_the_exit_code_was_set(
        tmp_path, monkeypatch, caplog):
    rating_log, da_log = _patch_children(tmp_path, monkeypatch)
    caplog.set_level(logging.INFO)

    run = dlr_live_run.run_live(env=_live_env(), now=_NOW, record_fn=_no_record, day_ahead=True)

    first_da_start = min(c["started"] for c in _da_calls(da_log))
    assert first_da_start >= max(f["finished"] for f in _finishes(rating_log))
    exit_logged = next(r for r in caplog.records if "finished, exit code" in r.getMessage())
    assert exit_logged.created <= first_da_start
    assert [c["city"] for c in _da_calls(da_log)] == list(config.LOCATIONS)  # config.LOCATIONS order
    assert len({c["pid"] for c in _da_calls(da_log)}) == len(config.LOCATIONS)
    assert run["finished_at"] is not None and run["exit_code"] == 0


def test_day_ahead_children_run_in_the_repo_root_with_the_unmodified_environment(
        tmp_path, monkeypatch):
    _, da_log = _patch_children(tmp_path, monkeypatch)

    dlr_live_run.run_live(
        cities=["MIDLAND"], env=_live_env(), now=_NOW, record_fn=_no_record, day_ahead=True)

    (call,) = _da_calls(da_log)
    assert os.path.realpath(call["cwd"]) == os.path.realpath(dlr_live_run.REPO_ROOT)
    assert call["argv"][:2] == ["--city", "MIDLAND"]
    assert call["synoptic_token_empty"] is False and call["db_url_set"] is True
    assert call["run_id"]  # the local run id reaches the child like the rating children's


def test_fault_drill_blanks_only_the_rating_child_not_the_day_ahead_child(tmp_path, monkeypatch):
    rating_log, da_log = _patch_children(tmp_path, monkeypatch)

    dlr_live_run.run_live(
        cities=["MIDLAND", "AUSTIN"], fault_city="MIDLAND", env=_live_env(), now=_NOW,
        record_fn=_no_record, day_ahead=True)

    assert {c["city"]: c["synoptic_token_empty"] for c in _calls(rating_log)} == {
        "MIDLAND": True, "AUSTIN": False}
    assert {c["city"]: c["synoptic_token_empty"] for c in _da_calls(da_log)} == {
        "MIDLAND": False, "AUSTIN": False}


# ──────────────────────────────────────────────────────────────────────────────
# the shared budget (D-02)
# ──────────────────────────────────────────────────────────────────────────────

def test_a_city_below_the_start_floor_is_skipped_and_no_child_starts(tmp_path, monkeypatch):
    _, da_log = _patch_children(tmp_path, monkeypatch)
    monkeypatch.setattr(dlr_live_run, "DAY_AHEAD_SHARED_BUDGET_S", dlr_live_run.DAY_AHEAD_MIN_START_S - 30)
    seen = _spy_timeouts(monkeypatch)

    run = dlr_live_run.run_live(env=_live_env(), now=_NOW, record_fn=_no_record, day_ahead=True)

    assert {r["outcome"] for r in run["day_ahead"]["cities"].values()} == {"skipped_budget"}
    assert list(run["day_ahead"]["cities"]) == list(config.LOCATIONS)
    assert seen == [] and _da_calls(da_log) == []
    assert run["exit_code"] == 0


def test_a_child_is_killed_at_the_smaller_of_its_cap_and_the_remaining_budget(tmp_path, monkeypatch):
    _patch_children(tmp_path, monkeypatch)
    seen = _spy_timeouts(monkeypatch)

    dlr_live_run.run_live(
        cities=["AUSTIN"], env=_live_env(), now=_NOW, record_fn=_no_record, day_ahead=True)
    assert seen == [("AUSTIN", dlr_live_run.DAY_AHEAD_CITY_TIMEOUT_S)]

    seen.clear()
    monkeypatch.setattr(dlr_live_run, "DAY_AHEAD_SHARED_BUDGET_S", 100)
    dlr_live_run.run_live(
        cities=["AUSTIN"], env=_live_env(), now=_NOW, record_fn=_no_record, day_ahead=True)
    (city, timeout), = seen
    assert city == "AUSTIN" and 90 < timeout <= 100  # the remaining budget, under the 150 s cap


def test_the_budget_is_shared_so_later_cities_are_skipped_once_it_runs_low(monkeypatch):
    clock = {"now": 900.0}
    monkeypatch.setattr(dlr_live_run, "time", SimpleNamespace(monotonic=lambda: clock["now"]))
    seen = []

    def fake_city(city, workdir, timeout_s, env):
        seen.append((city, timeout_s))
        clock["now"] += 60.0  # each child uses 60 s
        return dlr_live_run.classify_day_ahead(city, 0, {"outcome": "none_due"}, "", env=env)

    monkeypatch.setattr(dlr_live_run, "run_day_ahead_city", fake_city)

    stage = dlr_live_run.run_day_ahead_stage(list(config.LOCATIONS), {}, deadline=1000.0)

    assert seen == [("AUSTIN", 100.0)]  # min(150, 100 s remaining)
    assert [r["outcome"] for r in stage["cities"].values()] == [
        "none_due", "skipped_budget", "skipped_budget", "skipped_budget"]
    assert set(stage) >= {"started_at", "finished_at", "budget_s", "cities"}
    skipped = stage["cities"][config.LOCATIONS[1]]
    assert skipped["issued"] == [] and skipped["missing"] == [] and "budget" in skipped["reasons"]["child"]


def test_a_failure_inside_one_city_is_recorded_and_the_next_city_still_runs(monkeypatch):
    calls = []

    def fake_city(city, workdir, timeout_s, env):
        calls.append(city)
        if city == "AUSTIN":
            raise OSError("cannot start dummy-synoptic_token")
        return dlr_live_run.classify_day_ahead(city, 0, {"outcome": "none_due"}, "", env=env)

    monkeypatch.setattr(dlr_live_run, "run_day_ahead_city", fake_city)
    env = _live_env()

    stage = dlr_live_run.run_day_ahead_stage(
        list(config.LOCATIONS), env, deadline=time.monotonic() + 1000)

    assert calls == list(config.LOCATIONS)
    austin = stage["cities"]["AUSTIN"]
    assert austin["outcome"] == "error" and "OSError" in austin["reasons"]["child"]
    assert "dummy-synoptic_token" not in json.dumps(stage)


# ──────────────────────────────────────────────────────────────────────────────
# the stage's own run-log write
# ──────────────────────────────────────────────────────────────────────────────

def test_one_day_ahead_row_is_written_after_the_stage_and_never_counted_in_run_log(
        tmp_path, monkeypatch):
    _patch_children(tmp_path, monkeypatch)
    rows = []

    run = dlr_live_run.run_live(
        env=_live_env(FAKE_DA_BEHAVIOR_AUSTIN="partial", FAKE_DA_BEHAVIOR_MIDLAND="none_due"),
        now=_NOW, record_fn=rows.append, day_ahead=True)

    assert len(rows) == 7  # six rating writes, then one day-ahead write
    assert all("day_ahead" not in row for row in rows[:6])  # rating-stage writes never name it
    last = rows[-1]
    assert set(last) == {"run_id", "day_ahead"} and last["run_id"] == run["run_id"]
    cities = last["day_ahead"]["cities"]
    assert list(cities) == list(config.LOCATIONS)
    assert cities["AUSTIN"]["outcome"] == "partial" and cities["AUSTIN"]["missing"] == [_T3]
    assert cities["MIDLAND"]["outcome"] == "none_due"
    assert run["run_log"] == {"writes": 6, "failed": 0}
    assert run["day_ahead_run_log"] == {"writes": 1, "failed": 0}
    assert run["exit_code"] == 0


def test_a_failing_day_ahead_write_is_counted_separately_and_logged_redacted(
        tmp_path, monkeypatch, caplog):
    _patch_children(tmp_path, monkeypatch)
    caplog.set_level(logging.INFO)
    secret_url = _db_url()

    def record(row):
        if "day_ahead" in row:
            raise RuntimeError("connection to " + secret_url + " refused for dummy-synoptic_token")

    run = dlr_live_run.run_live(
        env=_live_env(SUPABASE_DB_URL=secret_url), now=_NOW, record_fn=record, day_ahead=True)

    assert run["day_ahead_run_log"] == {"writes": 1, "failed": 1}
    assert run["run_log"] == {"writes": 6, "failed": 0}
    assert run["exit_code"] == 0
    assert "day-ahead" in caplog.text and "RuntimeError" in caplog.text
    for secret in (secret_url, "pw-secret-1", "pooler.example.test", "dummy-synoptic_token"):
        assert secret not in caplog.text, secret


def test_no_run_log_sends_no_day_ahead_row(tmp_path, monkeypatch):
    _patch_children(tmp_path, monkeypatch)
    rows = []

    run = dlr_live_run.run_live(
        env=_live_env(), now=_NOW, record_fn=rows.append, record_run=False, day_ahead=True)

    assert rows == []
    assert run["run_log"] is None and "day_ahead_run_log" not in run
    assert {r["outcome"] for r in run["day_ahead"]["cities"].values()} == {"issued"}


def test_a_stage_that_raises_as_a_whole_is_logged_and_leaves_the_result_alone(
        tmp_path, monkeypatch, caplog):
    _patch_children(tmp_path, monkeypatch)
    caplog.set_level(logging.INFO)

    def explode(cities, env, deadline):
        raise RuntimeError("stage blew up dummy-synoptic_token")

    monkeypatch.setattr(dlr_live_run, "run_day_ahead_stage", explode)
    baseline_rows = []

    run = dlr_live_run.run_live(
        env=_live_env(), now=_NOW, record_fn=baseline_rows.append, day_ahead=True)

    assert run["exit_code"] == 0 and run["run_log"] == {"writes": 6, "failed": 0}
    assert [r["outcome"] for r in run["cities"]] == ["ok"] * len(config.LOCATIONS)
    assert "RuntimeError" in caplog.text and "dummy-synoptic_token" not in caplog.text
    assert run["day_ahead"]["error"] == "RuntimeError"


def test_every_reason_stored_or_printed_is_redacted_and_cut(tmp_path, monkeypatch, capsys):
    _patch_children(tmp_path, monkeypatch)
    rows = []
    env = _live_env(SUPABASE_DB_URL=_db_url(), FAKE_DA_BEHAVIOR_AUSTIN="leak",
                    FAKE_DA_BEHAVIOR_MIDLAND="crash")

    run = dlr_live_run.run_live(env=env, now=_NOW, record_fn=rows.append, day_ahead=True)

    out, err = capsys.readouterr()
    stored = json.dumps([run["day_ahead"], rows[-1]], default=str)
    for secret in ("dummy-synoptic_token", "pw-secret-1", "pooler.example.test", _db_url()):
        assert secret not in stored, secret
        assert secret not in out + err, secret
    for reason in rows[-1]["day_ahead"]["cities"]["AUSTIN"]["reasons"].values():
        assert len(reason) <= 1000
    assert "RuntimeError" in run["day_ahead"]["cities"]["MIDLAND"]["reasons"]["child"]


def test_the_row_builder_cuts_reasons_and_carries_only_the_run_id_and_day_ahead():
    state = {"run_id": "r9", "day_ahead": {
        "started_at": "2025-06-01T11:00:00Z", "finished_at": "2025-06-01T11:01:00Z", "budget_s": 900.0,
        "cities": {"AUSTIN": {"city": "AUSTIN", "outcome": "partial", "due": [_T1], "issued": [],
                               "missing": [_T1], "reasons": {_T1: "r" * 5000},
                               "band_sources": {}, "out_of_bounds": [], "cooling_model_sha256": None,
                               "exit_code": 0, "duration_s": 3.2}}}}

    row = live_run_log.build_day_ahead_run_row(state, env={})

    assert set(row) == {"run_id", "day_ahead"} and row["run_id"] == "r9"
    reason = row["day_ahead"]["cities"]["AUSTIN"]["reasons"][_T1]
    assert len(reason) == live_run_log.ERROR_MAX_CHARS
    assert row["day_ahead"]["cities"]["AUSTIN"]["missing"] == [_T1]
    json.dumps(row)  # plain JSON all the way down, so upsert_run can bind it


# ──────────────────────────────────────────────────────────────────────────────
# the step summary
# ──────────────────────────────────────────────────────────────────────────────

def _summary_run(tmp_path, monkeypatch, **extra_env):
    """Run main() with the stage on and a step summary; returns the summary text."""
    _patch_children(tmp_path, monkeypatch)
    _set_required_env(monkeypatch)
    for key, value in extra_env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(dlr_live_run, "MAIN_RUNS_DAY_AHEAD", True)
    summary = tmp_path / "step_summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("GITHUB_RUN_ID", "9001")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    conns = []

    def open_conn():
        conns.append(_RunConn())
        return conns[-1]

    monkeypatch.setattr(live_run_log, "open_connection", open_conn)
    code = dlr_live_run.main([])
    return code, summary.read_text(), conns


def test_the_step_summary_gains_a_separate_day_ahead_table_and_keeps_the_pipeline_run_line(
        tmp_path, monkeypatch):
    code, text, conns = _summary_run(
        tmp_path, monkeypatch, FAKE_DA_BEHAVIOR_AUSTIN="partial", FAKE_DA_BEHAVIOR_MIDLAND="crash")

    assert code == 0  # a crashed day-ahead child leaves the job green
    assert "pipeline_run: 6 writes, 0 failed" in text  # the rating line keeps its meaning
    assert "pipeline_run day_ahead: 1 writes, 0 failed" in text
    assert len(conns) == 7
    assert text.index("pipeline_run: 6 writes") < text.index("### Day-ahead forecast (does not affect the exit code)")
    section = text.split("### Day-ahead forecast (does not affect the exit code)")[1]
    rows = [line for line in section.splitlines() if line.startswith("| ") and "---" not in line][1:]
    assert [row.split("|")[1].strip() for row in rows] == list(config.LOCATIONS)
    assert "partial" in next(r for r in rows if "AUSTIN" in r)
    assert "error" in next(r for r in rows if "MIDLAND" in r)
    assert "live-rolling" in next(r for r in rows if "EL_PASO" in r)
    assert "dummy-synoptic_token" not in text


def test_the_step_summary_has_no_day_ahead_section_when_the_stage_did_not_run(tmp_path):
    run = {"run_id": "r1", "run_attempt": 1, "slot": "2025-06-01T10:00:00Z", "run_log": {"writes": 6, "failed": 0},
           "cities": [{"city": "AUSTIN", "outcome": "ok", "rating_a": 1000.0, "fallback": False,
                       "written": True, "forecast_status": "ok", "detector_model_loaded": True,
                       "fault_injected": False, "error": None}]}
    path = tmp_path / "s.md"

    dlr_live_run.write_step_summary(run, str(path))

    text = path.read_text()
    assert "Day-ahead" not in text and "pipeline_run: 6 writes, 0 failed" in text


# ──────────────────────────────────────────────────────────────────────────────
# render_guard: a malformed day-ahead entry can never change main()'s return
# ──────────────────────────────────────────────────────────────────────────────

def _cyclic():
    value = {"cities": {"AUSTIN": {"outcome": "issued"}}}
    value["cities"]["AUSTIN"]["self"] = value
    value["self"] = value
    return value


_MALFORMED = {
    "string": (lambda: "not a dict at all", False),
    "cities_is_a_list": (lambda: {"cities": ["AUSTIN", "MIDLAND"]}, False),
    "reasons_int_issued_none": (
        lambda: {"cities": {"AUSTIN": {"outcome": "partial", "reasons": 3, "issued": None}}}, False),
    "set_and_object": (
        lambda: {"cities": {"AUSTIN": {"outcome": {"a", "b"}, "issued": object(), "missing": object(),
                                       "reasons": {"x": object()}, "band_sources": {"y": {1, 2}}}}}, False),
    "self_referencing": (_cyclic, True),
}


def _canned_run(exit_code):
    cities = []
    for index, city in enumerate(config.LOCATIONS):
        failed = exit_code == 1 and index == 2
        cities.append({
            "city": city, "outcome": "error" if failed else "ok", "exit_code": 1 if failed else 0,
            "rating_a": None if failed else 1000.0, "fallback": None if failed else False,
            "written": not failed, "forecast_status": "not_run" if failed else "ok",
            "detector_model_loaded": not failed, "fault_injected": False,
            "error": "child failed" if failed else None})
    return {"run_id": "r1", "run_attempt": 1, "end": "2025-06-01T10:55:00Z",
            "slot": "2025-06-01T10:00:00Z", "started_at": "2025-06-01T11:00:00Z",
            "finished_at": "2025-06-01T11:05:00Z", "exit_code": exit_code,
            "run_log": {"writes": 6, "failed": 0}, "cities": cities}


@pytest.mark.parametrize("exit_code", [0, 1])
@pytest.mark.parametrize("shape", sorted(_MALFORMED))
def test_render_guard_a_malformed_day_ahead_entry_leaves_the_return_code_alone(
        tmp_path, monkeypatch, shape, exit_code):
    factory, unserialisable = _MALFORMED[shape]
    canned = _canned_run(exit_code)
    canned["day_ahead"] = factory()
    monkeypatch.setattr(dlr_live_run, "run_live", lambda **kwargs: canned)
    _set_required_env(monkeypatch)
    summary = tmp_path / "step_summary.md"
    out_json = tmp_path / "run.json"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))

    code = dlr_live_run.main(["--summary-json", str(out_json), "--no-run-log"])

    assert code == exit_code
    text = summary.read_text()
    assert "| AUSTIN | ok |" in text  # the rating table is still written
    assert "pipeline_run: 6 writes, 0 failed" in text
    not_rendered = [line for line in text.splitlines() if "Day-ahead table not rendered" in line]
    heading = "### Day-ahead forecast (does not affect the exit code)" in text
    assert len(not_rendered) == 1 or (heading and not not_rendered)
    for line in not_rendered:
        assert "the exit code is unaffected" in line
        assert "{" not in line and "object at" not in line  # the exception type only, no value text
    data = json.loads(out_json.read_text())  # always parses
    assert data["cities"] == canned["cities"] and data["exit_code"] == exit_code
    if unserialisable:
        assert list(data["day_ahead"]) == ["not_serialisable"]
        assert data["day_ahead"]["not_serialisable"] == "ValueError"


def test_the_summary_json_is_unchanged_for_a_run_that_serialises(tmp_path, monkeypatch):
    canned = _canned_run(0)
    canned["day_ahead"] = {"cities": {"AUSTIN": {"outcome": "issued", "issued": [_T1]}}}
    monkeypatch.setattr(dlr_live_run, "run_live", lambda **kwargs: canned)
    _set_required_env(monkeypatch)
    out_json = tmp_path / "run.json"

    assert dlr_live_run.main(["--summary-json", str(out_json), "--no-run-log"]) == 0

    assert out_json.read_text() == json.dumps(canned, indent=2)
    no_stage = _canned_run(0)
    monkeypatch.setattr(dlr_live_run, "run_live", lambda **kwargs: no_stage)
    other = tmp_path / "other.json"
    assert dlr_live_run.main(["--summary-json", str(other), "--no-run-log"]) == 0
    assert other.read_text() == json.dumps(no_stage, indent=2)
