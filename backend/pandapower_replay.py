"""
The owner's entry script for the replay and agreement check (pandapower-solver Phase 4, plan 04-03).

    .venv/bin/python -I -B backend/pandapower_replay.py ingest --export PATH [--mapping PATH]
        [--check-dir DIR]
    .venv/bin/python -I -B backend/pandapower_replay.py replay [--snapshot PATH] [--check-dir DIR]
        [--mapping PATH] [--ci]

All logic is in `pandapower_job.replay_cli`; this file only makes the backend folder importable under
`python -I` (which leaves the script's folder off the path) and passes the arguments on. Exit codes:
0 ok or pass, 1 the replay failed or was incomplete, 2 usage or refusal.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from pandapower_job import replay_cli  # noqa: E402

if __name__ == "__main__":
    sys.exit(replay_cli.main(sys.argv[1:]))
