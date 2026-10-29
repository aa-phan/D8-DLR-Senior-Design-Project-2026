"""
The install-time command that writes the filled Task Scheduler XML (pss-e-integration Phase 3,
plan 03-05, SCH-01). Run it with `python -X utf8 backend/psse_render_task.py`:

    --config FILE --work-dir DIR --out FILE [--python EXE] [--entry SCRIPT] [--start ISO]
    [--minute N] [--dry-run] [--allow-placeholder] [--template FILE] [--force]

It lives outside the gated psse_job package, so it may use argparse. The default interpreter is the
one that runs this command (so the validated interpreter is the scheduled one), the default entry
script is backend/psse_run_hourly.py beside it and the default template is the committed
docs/data-science/ops/psse_hourly_task.xml of the repository that holds this script.

Honest scope: the output is checked as text and against the launcher's argument parser only.
Whether Windows Task Scheduler accepts it and runs it is UNVERIFIED until runbook step 6 (plan 03-07).
"""

import argparse
import datetime
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from psse_job import taskxml  # noqa: E402

_DEFAULT_TEMPLATE = os.path.join(_HERE, "..", "docs", "data-science", "ops", "psse_hourly_task.xml")


def _parser():
    parser = argparse.ArgumentParser(prog="psse_render_task", allow_abbrev=False,
                                     description="Write the filled Task Scheduler XML for the hourly PSS/E job.")
    parser.add_argument("--config", required=True, metavar="FILE", help="the job's configuration file")
    parser.add_argument("--work-dir", required=True, dest="work_dir", metavar="DIR",
                        help="the task's working folder (a folder only you can write)")
    parser.add_argument("--out", required=True, metavar="FILE", help="where to write the filled XML")
    parser.add_argument("--python", default=None, metavar="EXE", help="the interpreter (default: this one)")
    parser.add_argument("--entry", default=None, metavar="SCRIPT",
                        help="the entry script (default: psse_run_hourly.py beside this script)")
    start = parser.add_mutually_exclusive_group()
    start.add_argument("--start", default=None, metavar="ISO", help="first start, local time, YYYY-MM-DDTHH:MM:SS")
    start.add_argument("--minute", type=int, default=15, metavar="N",
                       help="minute past the hour of the first start (default 15)")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="the task runs the study as a dry run (the smoke task)")
    parser.add_argument("--allow-placeholder", action="store_true", dest="allow_placeholder",
                        help="accept a placeholder mapping (only with --dry-run)")
    parser.add_argument("--template", default=None, metavar="FILE", help="the template (default: the committed one)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing output file")
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    with open(args.template or _DEFAULT_TEMPLATE, "rb") as handle:
        template_text = handle.read().decode("utf-8")
    text = taskxml.render(
        template_text,
        args.python or sys.executable,
        args.entry or os.path.join(_HERE, "psse_run_hourly.py"),
        args.config,
        args.work_dir,
        args.start or taskxml.next_start_boundary(datetime.datetime.now(), args.minute),
        dry_run=args.dry_run,
        allow_placeholder=args.allow_placeholder)
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print("wrote %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
