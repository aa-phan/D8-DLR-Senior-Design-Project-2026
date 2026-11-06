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

`write_env_gated_psspy_folder` (plan 03-09) models a PSS/E whose `psspy` cannot load until PSS/E's
environment helper module has run, the failure the first laptop session saw (`ImportError: DLL load
failed while importing psscommon`). The gated `psspy.py` raises that ImportError unless the variable
ENV_READY_VARIABLE equals "1"; the fake helper module sets it and both log one line (`helper`,
`psspy`) into one import log, so a test can read the order of the two imports. That the real helper
behaves like the fake is UNVERIFIED until runbook step 2 (U33): the fake models the order, the name
validation and the failure handling, nothing about real PSS/E. An in-process test must set
ENV_READY_VARIABLE through monkeypatch first, so that teardown removes what the helper sets.
"""

import functools
import os

from psse_fake_psspy import FakePsspy

OUTPUT_FUNCTIONS = ("report_output", "progress_output", "alert_output", "prompt_output")
LAUNCH_NAMES = ("psseinit",) + OUTPUT_FUNCTIONS

# The stub psspy source of the entry-script proofs: the module level functions the adapter reads
# (getdefault*, psseversion) plus psseinit and the four output-control functions.
STUB_PSSPY_SOURCE = (
    "def getdefaultint():\n"
    "    return 100000000\n"
    "def getdefaultreal():\n"
    "    return 1.0e20\n"
    "def getdefaultchar():\n"
    "    return '\\x01'\n"
    "def psseversion():\n"
    "    return ('PSS(R)E stub', 35, 6, 0, 'date', 0)\n"
    "def psseinit(buses=None):\n"
    "    return 0\n"
    "def report_output(islct, filarg, options):\n"
    "    return 0\n"
    "def progress_output(islct, filarg, options):\n"
    "    return 0\n"
    "def alert_output(islct, filarg, options):\n"
    "    return 0\n"
    "def prompt_output(islct, filarg, options):\n"
    "    return 0\n"
)

ENV_READY_VARIABLE = "FAKE_PSSE_ENV_READY"
DLL_FAILURE_TEXT = "DLL load failed while importing psscommon: The specified module could not be found."


def write_env_gated_psspy_folder(folder, env_module="psse3604"):
    """
    Write `psspy.py` (gated) and `<env_module>.py` (the fake helper) into the existing `folder` and
    return the import log's path (the file does not exist until the first import). Importing the
    gated psspy while ENV_READY_VARIABLE is not "1" raises ImportError with DLL_FAILURE_TEXT;
    importing the helper sets it to "1" and appends the line `helper`; a successful psspy import
    appends the line `psspy`.
    """
    log_path = os.path.join(str(folder), "import.log")
    gate = (
        "import os\n"
        "if os.environ.get(" + repr(ENV_READY_VARIABLE) + ") != '1':\n"
        "    raise ImportError(" + repr(DLL_FAILURE_TEXT) + ")\n"
        "with open(" + repr(log_path) + ", 'a') as _log:\n"
        "    _log.write('psspy\\n')\n"
    )
    helper = (
        "import os\n"
        "os.environ[" + repr(ENV_READY_VARIABLE) + "] = '1'\n"
        "with open(" + repr(log_path) + ", 'a') as _log:\n"
        "    _log.write('helper\\n')\n"
    )
    with open(os.path.join(str(folder), "psspy.py"), "w", encoding="utf-8") as handle:
        handle.write(gate + STUB_PSSPY_SOURCE)
    with open(os.path.join(str(folder), env_module + ".py"), "w", encoding="utf-8") as handle:
        handle.write(helper)
    return log_path


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
