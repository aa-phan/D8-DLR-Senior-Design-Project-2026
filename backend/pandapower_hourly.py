"""
The entry script of the hourly pandapower job (pandapower-solver Phase 5, plan 05-01).

    .venv/bin/python -I -B backend/pandapower_hourly.py run

All logic is in `pandapower_job.hourly`; this file only makes the backend folder importable under
`python -I` (which leaves the script's folder off the path) and passes the arguments on. The run is
a dry run unless the environment variable PANDAPOWER_LIVE is exactly `true`. Everything printed is
a counts-only line of a closed vocabulary. Exit codes: 0 ok, 1 the study failed or the run was
recorded as failed, 2 usage, refusal or unexpected error, 3 a live run could not be recorded.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pandapower_job import hourly  # noqa: E402

if __name__ == "__main__":
    sys.exit(hourly.main(sys.argv[1:]))
