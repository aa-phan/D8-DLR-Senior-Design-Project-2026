"""
Tests for the scheduler-ready collection entry point
(`backend/forecast_shadow_collect.py`). Network-free: `run_once` itself
is monkeypatched so these tests check the lock/exit-code contract, not
live retrieval (that's `forecast_shadow_pipeline_test.py`'s job).

`INTER_CORRIDOR_DELAY_S` is pinned to 0 in every test via an autouse
fixture -- real runs need the delay (see its own docstring in
`forecast_shadow_collect.py`), but these tests would otherwise sleep for
real wall-clock seconds per corridor for no reason.
"""
import fcntl

import pytest

import config
import forecast_shadow_collect as collect
import forecast_shadow_demo


@pytest.fixture(autouse=True)
def _no_real_delay(monkeypatch):
    monkeypatch.setattr(collect, "INTER_CORRIDOR_DELAY_S", 0.0)


def test_collect_once_returns_zero_and_calls_every_corridor(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "_LOCK_PATH", str(tmp_path / "collect.lock"))
    called = []
    monkeypatch.setattr(forecast_shadow_demo, "run_once", lambda corridor, method: called.append(corridor))
    assert collect.collect_once() == 0
    assert set(called) == set(config.CORRIDOR_ENDPOINTS)


def test_collect_once_sleeps_between_corridors_but_not_before_the_first(monkeypatch, tmp_path):
    """
    The delay exists specifically to space out BACK-TO-BACK requests (the
    suspected per-IP rate-limit trigger) -- sleeping before the FIRST
    corridor too would add latency with no corresponding benefit, since
    there is no prior request for it to be spaced apart from.
    """
    monkeypatch.setattr(collect, "_LOCK_PATH", str(tmp_path / "collect.lock"))
    monkeypatch.setattr(collect, "INTER_CORRIDOR_DELAY_S", 5.0)
    sleeps = []
    monkeypatch.setattr(collect.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(forecast_shadow_demo, "run_once", lambda corridor, method: None)

    assert collect.collect_once() == 0

    n_corridors = len(config.CORRIDOR_ENDPOINTS)
    assert len(sleeps) == n_corridors - 1
    assert all(s == 5.0 for s in sleeps)


def test_collect_once_returns_one_on_a_hard_failure_but_still_tries_every_corridor(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "_LOCK_PATH", str(tmp_path / "collect.lock"))
    attempted = []

    def _flaky(corridor, method):
        attempted.append(corridor)
        raise RuntimeError("a bug, not an expected fallback condition")

    monkeypatch.setattr(forecast_shadow_demo, "run_once", _flaky)
    assert collect.collect_once() == 1
    assert set(attempted) == set(config.CORRIDOR_ENDPOINTS)


def test_collect_once_returns_two_and_skips_entirely_when_lock_already_held(monkeypatch, tmp_path):
    lock_path = str(tmp_path / "collect.lock")
    monkeypatch.setattr(collect, "_LOCK_PATH", lock_path)
    called = []
    monkeypatch.setattr(forecast_shadow_demo, "run_once", lambda corridor, method: called.append(corridor))

    # Hold the lock ourselves, simulating a still-running prior invocation.
    holder = open(lock_path, "w")
    fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        assert collect.collect_once() == 2
        assert called == []  # never even attempted -- the whole point of the lock
    finally:
        holder.close()


def test_collect_once_releases_the_lock_so_a_later_invocation_can_proceed(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "_LOCK_PATH", str(tmp_path / "collect.lock"))
    monkeypatch.setattr(forecast_shadow_demo, "run_once", lambda corridor, method: None)
    assert collect.collect_once() == 0
    assert collect.collect_once() == 0  # second call must not see a stale held lock
