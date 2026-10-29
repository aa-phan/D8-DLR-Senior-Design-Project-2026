"""
The run lock of the PSS/E job (pss-e-integration Phase 3, plan 03-01: SCH-01, D-04, T-03-03).

Two runs must never overlap: psspy state is process-global, a licence seat is released only when
the process exits, and a second study would only duplicate a slot. `RunLock` is a NON-BLOCKING lock
on one byte of a file opened with os.open: it is never a PID file (the file stays empty), so no
stale file can ever block a run. The operating system releases the lock when the holder returns,
raises or is killed, so a crash cannot leave the job locked.

  Windows  msvcrt.locking(fd, LK_NBLCK, 1) at byte 0 (a second handle, in this process or another,
           is refused with PermissionError)
  elsewhere  fcntl.flock(fd, LOCK_EX | LOCK_NB) (BlockingIOError)

Each module is imported inside a function (the import gate allows them by name). `acquired` is
True or False after `__enter__`; "held by someone else" never raises. The launcher holds the lock
from before PSS/E starts until after job.run_once returns.

Windows semantics are proved on the Windows development machine (a second handle in the same
process and a second process are both refused, a killed holder releases the lock). The branch this
machine does not use is proved only through a fake module (call shape, not behaviour). The laptop's
Python and filesystem are UNVERIFIED until runbook step 6 (plan 03-07).

Standard library only, Python 3.7 syntax.
"""

import os


def _backend_name():
    """'msvcrt' on Windows (os.name 'nt'), else 'fcntl'. Tests replace it to force the other branch."""
    return "msvcrt" if os.name == "nt" else "fcntl"


def _try_lock(fd, backend):
    """One attempt, no waiting; raises OSError when another handle holds the byte."""
    if backend == "msvcrt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(fd, backend):
    if backend == "msvcrt":
        import msvcrt
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)


class RunLock(object):
    """Context manager over the lock file `path`; check `.acquired` after entering."""

    def __init__(self, path):
        self.path = path
        self.acquired = False
        self._fd = None
        self._backend = None

    def __enter__(self):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0)
        fd = os.open(self.path, flags, 0o600)
        backend = _backend_name()
        try:
            _try_lock(fd, backend)
        except OSError:
            # PermissionError (Windows) or BlockingIOError (elsewhere): another handle holds it.
            os.close(fd)
            self.acquired = False
            return self
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        self._backend = backend
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._fd is not None:
            fd, backend = self._fd, self._backend
            self._fd = None
            try:
                _unlock(fd, backend)
            except Exception:  # noqa: BLE001 - closing the descriptor releases it anyway
                pass
            try:
                os.close(fd)
            except OSError:
                pass
        self.acquired = False
        return False
