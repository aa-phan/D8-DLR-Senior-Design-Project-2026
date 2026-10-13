"""
Tests for the scheduler-ready collection entry point
(`backend/forecast_shadow_collect.py`). Network-free: the per-city child
process is replaced by a recorder (`_run_city_subprocess`) or, for the
child-side body, `run_once_all_methods` itself is monkeypatched, so these tests
check the process-per-city / lock / exit-code contract, not live retrieval
(that's `forecast_shadow_pipeline_test.py`'s job). One test really spawns a
Python child to prove the `--city` CLI wiring (it exits before any network
call because the city is invalid).

`INTER_CITY_DELAY_S` is pinned to 0 in every test via an autouse
fixture -- real runs need the delay (see its own comment in
`forecast_shadow_collect.py`), but these tests would otherwise sleep for
real wall-clock seconds per city for no reason.
"""
import fcntl
import os
import subprocess
import sys

import pytest

import config
import forecast_shadow_collect as collect
import forecast_shadow_demo


@pytest.fixture(autouse=True)
def _no_real_delay(monkeypatch):
    monkeypatch.setattr(collect, "INTER_CITY_DELAY_S", 0.0)


def _use_tmp_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "_LOCK_PATH", str(tmp_path / "collect.lock"))


def test_collect_once_runs_every_city_in_its_own_child_in_order_and_returns_zero(monkeypatch, tmp_path):
    _use_tmp_lock(monkeypatch, tmp_path)
    spawned = []
    monkeypatch.setattr(collect, "_run_city_subprocess", lambda city: spawned.append(city) or 0)
    # The parent must never run a city in-process.
    monkeypatch.setattr(
        forecast_shadow_demo, "run_once_all_methods",
        lambda city: pytest.fail("parent collect_once must not run a city in its own process"),
    )
    assert collect.collect_once() == 0
    assert spawned == list(config.LOCATIONS)
    assert set(spawned) == {"AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"}


def test_the_child_command_is_a_fresh_interpreter_running_this_script_for_one_city(monkeypatch):
    seen = {}

    def _fake_run(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(collect.subprocess, "run", _fake_run)
    assert collect._run_city_subprocess("MIDLAND") == 0
    assert seen["cmd"][0] == sys.executable
    assert os.path.isabs(seen["cmd"][1]) and seen["cmd"][1].endswith("forecast_shadow_collect.py")
    assert seen["cmd"][2:] == ["--city", "MIDLAND"]
    assert seen["kwargs"]["timeout"] == collect.CITY_TIMEOUT_S
    # stdout/stderr are inherited (not captured) so CI shows the child's logs live.
    assert "capture_output" not in seen["kwargs"] and "stdout" not in seen["kwargs"]


def test_the_inter_city_delay_keeps_its_value_and_the_old_name_is_gone(monkeypatch):
    monkeypatch.undo()  # drop this file's autouse zero-delay patch to read the real constant
    assert collect.INTER_CITY_DELAY_S == 15.0
    assert not hasattr(collect, "INTER_CORRIDOR_DELAY_S")


def test_the_per_city_timeout_fits_four_cities_inside_the_workflow_timeout(monkeypatch):
    monkeypatch.undo()
    workflow_minutes = 30
    worst_case_s = len(config.LOCATIONS) * collect.CITY_TIMEOUT_S + (len(config.LOCATIONS) - 1) * collect.INTER_CITY_DELAY_S
    assert worst_case_s < workflow_minutes * 60


def test_collect_once_sleeps_between_cities_but_not_before_the_first(monkeypatch, tmp_path):
    """
    The delay exists specifically to space out BACK-TO-BACK requests -- sleeping
    before the FIRST city too would add latency with no corresponding benefit.
    """
    _use_tmp_lock(monkeypatch, tmp_path)
    monkeypatch.setattr(collect, "INTER_CITY_DELAY_S", 5.0)
    sleeps = []
    monkeypatch.setattr(collect.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(collect, "_run_city_subprocess", lambda city: 0)

    assert collect.collect_once() == 0

    n_cities = len(config.LOCATIONS)
    assert n_cities == 4
    assert len(sleeps) == n_cities - 1 == 3
    assert all(s == 5.0 for s in sleeps)


def test_a_child_exiting_nonzero_is_a_hard_failure_but_every_city_is_still_attempted(monkeypatch, tmp_path):
    _use_tmp_lock(monkeypatch, tmp_path)
    attempted = []

    def _flaky(city):
        attempted.append(city)
        return 1 if city == "CORPUS_CHRISTI" else 0

    monkeypatch.setattr(collect, "_run_city_subprocess", _flaky)
    assert collect.collect_once() == 1
    assert attempted == list(config.LOCATIONS)


def test_a_timed_out_child_is_reported_but_is_not_a_hard_failure(monkeypatch, tmp_path, capsys):
    _use_tmp_lock(monkeypatch, tmp_path)
    attempted = []

    def _stall_one(city):
        attempted.append(city)
        if city == "MIDLAND":
            raise subprocess.TimeoutExpired(cmd="x", timeout=collect.CITY_TIMEOUT_S)
        return 0

    monkeypatch.setattr(collect, "_run_city_subprocess", _stall_one)
    assert collect.collect_once() == 0  # other cities' logs still get committed
    assert attempted == list(config.LOCATIONS)  # EL_PASO still ran after MIDLAND stalled
    assert "MIDLAND" in capsys.readouterr().err


def test_collect_once_returns_two_and_skips_entirely_when_lock_already_held(monkeypatch, tmp_path):
    lock_path = str(tmp_path / "collect.lock")
    monkeypatch.setattr(collect, "_LOCK_PATH", lock_path)
    spawned = []
    monkeypatch.setattr(collect, "_run_city_subprocess", lambda city: spawned.append(city) or 0)

    # Hold the lock ourselves, simulating a still-running prior invocation.
    holder = open(lock_path, "w")
    fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert collect.collect_once() == 2
        assert spawned == []  # never even attempted -- the whole point of the lock
    finally:
        holder.close()


def test_collect_once_releases_the_lock_so_a_later_invocation_can_proceed(monkeypatch, tmp_path):
    _use_tmp_lock(monkeypatch, tmp_path)
    monkeypatch.setattr(collect, "_run_city_subprocess", lambda city: 0)
    assert collect.collect_once() == 0
    assert collect.collect_once() == 0  # second call must not see a stale held lock


# --- child-process side -------------------------------------------------

def test_collect_city_runs_exactly_that_city_and_takes_no_lock(monkeypatch, tmp_path):
    # An already-held lock must not matter to a child: the parent owns it.
    lock_path = str(tmp_path / "collect.lock")
    monkeypatch.setattr(collect, "_LOCK_PATH", lock_path)
    holder = open(lock_path, "w")
    fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    called = []
    monkeypatch.setattr(forecast_shadow_demo, "run_once_all_methods", lambda city: called.append(city))
    try:
        assert collect.main(["--city", "EL_PASO"]) == 0
    finally:
        holder.close()
    assert called == ["EL_PASO"]


def test_collect_city_returns_one_and_prints_the_traceback_on_a_hard_failure(monkeypatch, capsys):
    def _boom(city):
        raise RuntimeError("a bug, not an expected fallback condition")

    monkeypatch.setattr(forecast_shadow_demo, "run_once_all_methods", _boom)
    assert collect.collect_city("AUSTIN") == 1
    err = capsys.readouterr().err
    assert "hard failure for city 'AUSTIN'" in err and "RuntimeError" in err


def test_the_cli_really_spawns_a_python_child_and_rejects_an_unknown_city():
    """Real subprocess, no network: argparse rejects the city before any work."""
    proc = subprocess.run(
        [sys.executable, os.path.abspath(collect.__file__), "--city", "NOT_A_CITY"],
        capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode != 0
    assert "invalid choice" in proc.stderr
