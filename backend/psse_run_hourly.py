"""
The entry script of the hourly PSS/E job (pss-e-integration Phase 3, plan 03-04).

Run it as `python -X utf8 backend/psse_run_hourly.py run --config FILE` (Task Scheduler does);
the other commands are `selftest`, `probe`, `hold-lock`, `gaps` and `credcheck` (see
psse_job/launcher.py). This file is the ONLY place `psspy` is imported, and only inside
`load_psspy`: importing this module never imports it (backend/tests/psse_entry_test.py proves
both). Everything else lives in psse_job.launcher, which receives the loader as an argument. Keep
this file small.

Honest scope: every statement about how real PSS/E behaves here is UNVERIFIED until runbook step 2
(plan 03-07): that `import psspy` works from the configured folder, that `psseinit` and the four
output-control calls accept the parameters launcher.start_psspy passes, that sending the console
output to a file works, and that os.add_dll_directory (registered by launcher.add_search_dirs)
is needed or enough.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    # Under `python -I` the script's folder is not on the path; psse_job lives next to this file.
    sys.path.insert(0, _HERE)

from psse_job import launcher  # noqa: E402

_OUTPUT_LOG_NAME = "psse_output.log"


def load_psspy(cfg):
    """
    The started psspy module (the loader contract of launcher.main). launcher.main has already
    appended PSSE_PSSPY_DIR, PSSE_BIN_DIR and PSSE_SITE_DIR to sys.path (never first, so a planted
    module cannot shadow the standard library) and registered the DLL folder. Raises
    launcher.PsseUnavailable, naming only the exception class, when psspy is not found or cannot be
    loaded or psseinit fails.
    """
    if not cfg.get("PSSE_PSSPY_DIR"):
        raise launcher.PsseUnavailable("PSSE_PSSPY_DIR is not set")
    try:
        import psspy  # the only import of psspy in the repository
    except (ImportError, OSError) as exc:
        raise launcher.PsseUnavailable("psspy could not be imported (%s)" % type(exc).__name__)
    launcher.start_psspy(
        psspy, int(cfg.get("PSSE_MAX_BUSES", "20000")), os.path.join(cfg["PSSE_LOG_DIR"], _OUTPUT_LOG_NAME))
    return psspy


def _prepare_streams():
    """
    UTF-8 output with replacement for what cannot be encoded, and a real stream where pythonw.exe
    leaves None (research Pitfall 8 and 10); a stream that cannot be reconfigured is left as it is.
    """
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main(argv=None):
    _prepare_streams()
    return launcher.main(argv if argv is not None else sys.argv[1:], load_psspy)


if __name__ == "__main__":
    sys.exit(main())
