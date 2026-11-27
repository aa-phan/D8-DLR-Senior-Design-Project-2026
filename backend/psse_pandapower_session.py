"""
The one command the teammate runs on the PSS/E laptop (pandapower-solver Phase 1, plan 01-02):

    python -I -X utf8 backend/psse_pandapower_session.py run --config <CONFIG> \
        --mapping <MAPPING COPY> --out-dir <DESKTOP>

It reads PSS/E, writes one verified zip into the out folder, deletes the mapping copy and its own
work folder, and prints a masked summary (counts, statuses and versions only). It never writes the
case file, opens a network connection, touches a database or prints a path or a name. `check`
loads PSS/E, checks the mapping against the case and solves one base case without writing a zip.

psspy is reached only through psse_run_hourly.load_psspy, so the repository keeps one psspy import
(backend/tests/psse_session_test.py proves it). Everything else lives in psse_session.session.
Honest scope: all of this is UNVERIFIED on real PSS/E until the session of plan 01-10.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    # Under `python -I` the script's folder is not on the path; psse_job and psse_session live here.
    sys.path.insert(0, _HERE)

import psse_run_hourly  # noqa: E402
from psse_session import session  # noqa: E402


def main(argv=None):
    psse_run_hourly._prepare_streams()
    return session.main(sys.argv[1:] if argv is None else argv, psse_run_hourly.load_psspy)


if __name__ == "__main__":
    sys.exit(main())
