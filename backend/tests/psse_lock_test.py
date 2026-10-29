"""
SCH-01 lock proofs of the PSS/E job (pss-e-integration Phase 3, plan 03-01): `psse_job.lock.RunLock`
is a non-blocking operating-system lock on one byte of a file, so a second run started while the
first is alive is refused at once and the operating system releases the lock when the holder
returns, raises or is killed.

This machine's native branch (msvcrt on Windows, fcntl elsewhere) is proved against a REAL second
Python process. The branch this machine does not use is proved only through a fake module that
records the call, so it proves the call shape (one byte, non-blocking, position 0; LOCK_EX and
LOCK_NB), never the other operating system's behaviour.

Honest scope: nothing here proves the laptop's Python, filesystem or Task Scheduler behave the same;
that is UNVERIFIED until runbook step 6 (plan 03-07).

No database, no network. Follows backend/tests/psse_job_test.py (module-level imports, plain
asserts, no test classes).
"""

import os
import subprocess
import sys
import types

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from psse_job import lock  # noqa: E402

# The second process: inserts the backend folder itself (it runs with -I, so no PYTHONPATH and no
# script folder), tries the lock once and reports. With "hold" it then waits for its stdin to close.
_PROBE_CODE = (
    "import sys\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "from psse_job.lock import RunLock\n"
    "with RunLock(sys.argv[2]) as held:\n"
    "    print('acquired' if held.acquired else 'locked', flush=True)\n"
    "    if len(sys.argv) > 3 and sys.argv[3] == 'hold':\n"
    "        sys.stdin.read()\n"
)


def probe(path, timeout=30):
    """'acquired' or 'locked': what a fresh Python process finds when it tries `path`."""
    done = subprocess.run(
        [sys.executable, "-I", "-B", "-c", _PROBE_CODE, _BACKEND, str(path)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=timeout, universal_newlines=True,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


class Holder(object):
    """A second process that holds the lock until `release()` closes its stdin or `kill()`."""

    def __init__(self, path):
        self.process = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", _PROBE_CODE, _BACKEND, str(path), "hold"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.first_line = self.process.stdout.readline().strip()

    def release(self):
        self.process.stdin.close()
        self.process.wait(timeout=30)

    def kill(self):
        self.process.kill()
        self.process.wait(timeout=30)

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=30)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            try:
                stream.close()
            except Exception:  # noqa: BLE001 - already closed
                pass


def test_tracer_lock_second_process_refused_then_acquires_after_release(tmp_path):
    """While this process holds the lock a second process is refused; after the block it acquires."""
    path = tmp_path / "run" / "psse_job.lock"
    with lock.RunLock(str(path)) as mine:
        assert mine.acquired is True
        assert probe(path) == "locked"
    assert probe(path) == "acquired"
    with lock.RunLock(str(path)) as again:
        assert again.acquired is True


def test_lock_released_when_holder_dies(tmp_path):
    """A holder that is killed (no clean exit) releases the lock: the operating system does it."""
    path = tmp_path / "psse_job.lock"
    holder = Holder(path)
    try:
        assert holder.first_line == "acquired"
        with lock.RunLock(str(path)) as refused:
            assert refused.acquired is False
        holder.kill()
        with lock.RunLock(str(path)) as taken:
            assert taken.acquired is True
    finally:
        holder.close()


def test_lock_released_after_exception(tmp_path):
    """An exception inside the with block propagates and still releases the lock."""
    path = tmp_path / "psse_job.lock"
    with pytest.raises(RuntimeError):
        with lock.RunLock(str(path)) as mine:
            assert mine.acquired is True
            raise RuntimeError("boom")
    assert probe(path) == "acquired"


def test_lock_second_handle_in_same_process_is_refused(tmp_path):
    """Two RunLock objects on one path in one process: the second reports not acquired."""
    path = str(tmp_path / "psse_job.lock")
    with lock.RunLock(path) as first:
        assert first.acquired is True
        with lock.RunLock(path) as second:
            assert second.acquired is False
        # a refused second handle must not have released the first
        assert probe(path) == "locked"
    assert probe(path) == "acquired"


def test_lock_creates_directory(tmp_path):
    """The parent directory and the file are created; the lock is never a PID file (it stays empty)."""
    path = tmp_path / "a" / "b" / "psse_job.lock"
    assert not path.parent.exists()
    with lock.RunLock(str(path)) as mine:
        assert mine.acquired is True
        assert path.is_file()
    assert path.is_file()
    assert path.stat().st_size == 0


def test_lock_backend_name_follows_os_name(monkeypatch):
    monkeypatch.setattr(lock.os, "name", "nt")
    assert lock._backend_name() == "msvcrt"
    monkeypatch.setattr(lock.os, "name", "posix")
    assert lock._backend_name() == "fcntl"


def test_lock_fcntl_branch_with_fake_module(tmp_path, monkeypatch):
    """Forced to fcntl with a fake module: LOCK_EX | LOCK_NB, and BlockingIOError means held."""
    calls = []
    state = {"held": False}

    def flock(fd, operation):
        calls.append(operation)
        if operation == fake.LOCK_UN:
            state["held"] = False
            return
        if state["held"]:
            raise BlockingIOError(11, "held")
        state["held"] = True

    fake = types.ModuleType("fcntl")
    fake.LOCK_EX = 2
    fake.LOCK_NB = 4
    fake.LOCK_UN = 8
    fake.flock = flock
    monkeypatch.setitem(sys.modules, "fcntl", fake)
    monkeypatch.setattr(lock, "_backend_name", lambda: "fcntl")
    path = str(tmp_path / "psse_job.lock")
    with lock.RunLock(path) as first:
        assert first.acquired is True
        with lock.RunLock(path) as second:
            assert second.acquired is False
    assert calls[0] == fake.LOCK_EX | fake.LOCK_NB
    assert fake.LOCK_UN in calls
    assert state["held"] is False


def test_lock_msvcrt_branch_with_fake_module(tmp_path, monkeypatch):
    """Forced to msvcrt with a fake module: one byte, non-blocking, at position 0; OSError means held."""
    calls = []
    state = {"held": False}

    def locking(fd, mode, nbytes):
        calls.append((mode, nbytes, os.lseek(fd, 0, os.SEEK_CUR)))
        if mode == fake.LK_UNLCK:
            state["held"] = False
            return
        if state["held"]:
            raise PermissionError(13, "held")
        state["held"] = True

    fake = types.ModuleType("msvcrt")
    fake.LK_NBLCK = 2
    fake.LK_UNLCK = 0
    fake.locking = locking
    monkeypatch.setitem(sys.modules, "msvcrt", fake)
    monkeypatch.setattr(lock, "_backend_name", lambda: "msvcrt")
    path = str(tmp_path / "psse_job.lock")
    with lock.RunLock(path) as first:
        assert first.acquired is True
        with lock.RunLock(path) as second:
            assert second.acquired is False
    assert calls[0] == (fake.LK_NBLCK, 1, 0)
    assert any(call[0] == fake.LK_UNLCK and call[1] == 1 and call[2] == 0 for call in calls)
    assert state["held"] is False
