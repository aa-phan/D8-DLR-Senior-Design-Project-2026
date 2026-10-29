"""
A fake psspy with the launch functions (pss-e-integration Phase 3, plan 03-04).
Not collected by pytest (the file name does not match `*_test.py`).

`FakeLaunchPsspy` is `psse_fake_psspy.FakePsspy` plus the functions the launcher uses to start
PSS/E and to move its console output into a file: `psseinit` and `report_output`,
`progress_output`, `alert_output` and `prompt_output`. They are a subclass because the Phase 2
fake is frozen and its drift test pins its surface to `psse_job.psse_api.SURFACE`; these five
names are outside that table (`psse_job.launcher.LAUNCH_SURFACE` lists them).

Every launch call is recorded in `fake_calls` and in `fake_launch_calls` as (name, args, kwargs).
`fake_init_error` (an exception instance) makes `psseinit` raise it; `fake_output_error` (a set of
function names) makes those output functions raise RuntimeError. The functions return 0, as the
real ones return an error code.

Honest scope: this models call shapes and failure handling only. That real PSS/E has these
functions with these parameter names, and that `(2, file, [0, 0])` redirects anything, is
UNVERIFIED until runbook step 2 (the laptop).
"""

import functools

from psse_fake_psspy import FakePsspy

OUTPUT_FUNCTIONS = ("report_output", "progress_output", "alert_output", "prompt_output")
LAUNCH_NAMES = ("psseinit",) + OUTPUT_FUNCTIONS


def _launch_recorded(function):
    """Record each call (name, args, kwargs) in both lists, keeping the method's exact signature."""
    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        record = (function.__name__, args, dict(kwargs))
        self.fake_calls.append(record)
        self.fake_launch_calls.append(record)
        return function(self, *args, **kwargs)
    return wrapper


class FakeLaunchPsspy(FakePsspy):
    """FakePsspy plus psseinit and the four output-control functions; see the module docstring."""

    def __init__(self, solver=None):
        FakePsspy.__init__(self, solver=solver)
        self.fake_launch_calls = []
        self.fake_init_error = None
        self.fake_output_error = set()

    def _output(self, name):
        if name in self.fake_output_error:
            raise RuntimeError("fake output function failure in " + name)
        return 0

    @_launch_recorded
    def psseinit(self, buses=None):
        if self.fake_init_error is not None:
            raise self.fake_init_error
        return 0

    @_launch_recorded
    def report_output(self, islct, filarg, options):
        return self._output("report_output")

    @_launch_recorded
    def progress_output(self, islct, filarg, options):
        return self._output("progress_output")

    @_launch_recorded
    def alert_output(self, islct, filarg, options):
        return self._output("alert_output")

    @_launch_recorded
    def prompt_output(self, islct, filarg, options):
        return self._output("prompt_output")
