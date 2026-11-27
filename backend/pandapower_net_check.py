"""
The owner's entry script for the pandapower side of Phase 1 (plan 01-09).

    .venv/bin/python -I -B backend/pandapower_net_check.py ingest --zip PATH [--sessions-dir DIR]
    .venv/bin/python -I -B backend/pandapower_net_check.py check --session DIR --mapping PATH
        [--registry PATH] [--allow-placeholder]

All logic is in `pandapower_job.cli`; this file only makes the backend folder importable under
`python -I` (which leaves the script's folder off the path) and passes the arguments on. Exit
codes: 0 ok, 1 the check ran and failed or was incomplete, 2 usage or refusal. See
docs/data-science/decisions/psse_pandapower_session_guide.md for the owner's steps.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pandapower_job import cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(cli.main(sys.argv[1:]))
