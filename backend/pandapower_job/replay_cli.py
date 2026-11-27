"""
The owner's two replay commands (pandapower-solver Phase 4, plan 04-03: AGR-04; decisions D-01,
D-03 and D-04).

    pandapower_replay.py ingest --export PATH [--mapping PATH] [--check-dir DIR]
    pandapower_replay.py replay [--snapshot PATH] [--check-dir DIR] [--mapping PATH] [--ci]

`ingest` takes the file the owner of the Supabase project exported with the read-only SQL of
`supabase/ops/export_psse_runs_for_replay.sql` (D-01), validates it and writes a private snapshot
(`pandapower_job.recorded`). `replay` replays every eligible recorded run through pandapower with
that run's stored ratings (`pandapower_job.replay`), judges the runs (`pandapower_job.agree`) and
prints the verdict.

What is printed (D-03). Everything printed, to the terminal or a CI log, goes through one renderer
(`_Printer.say`) that accepts only lines matching `CLI_LINE_PATTERNS`: counts of one to nine digits
and words of fixed sets (the verdict, a closed reason, a violation kind, a failed stage, a data
check). A run id, a hash, a path, an element or a figure cannot reach it, not even the largest
deviation; a line outside the vocabulary is a programming error that stops the command with the
generic error line. There is no verbose flag, no override of a hash or a placeholder switch, and no
option that prints a figure.

What is private. In local mode the whole detail (settings in force, the tolerance rules, the largest
deviation even on a pass, the worst per quantity, the exclusions with their run ids and reasons,
every finding with its values) is written as `report.json` in a new folder
`data/private/pandapower/replays/replay_STAMP`, through `pandapower_job.private` (git-ignored,
owner-only, never overwritten, the report marker key present so the leak guard flags a stray copy).
CI mode is on with `--ci`, and also whenever the environment variable GITHUB_ACTIONS equals the text
`true`, whatever the flag (fail safe: a runner log is public): it creates no file and no folder, and
prints exactly the local lines without the final `report: written`.

Exit codes: 0 (ingest ok, or replay pass), 1 (replay fail or incomplete), 2 (usage, any refusal,
private-path refusal, unexpected error). This module and everything it imports write nothing to any
database: no module of the phase imports a driver, a network module or a writer-side module of the
PSS/E job.
"""

import argparse
import datetime
import hashlib
import os
import re
import sys

import pandapower

from psse_job import constants, study
from pandapower_job import agree, cli, engine, private, recorded, replay

REPORT_MARKER = cli.REPORT_MARKER
EXIT_OK = cli.EXIT_OK
EXIT_FAILED = cli.EXIT_FAILED
EXIT_USAGE = cli.EXIT_USAGE

_PROGRAM = "pandapower_replay.py"
_NUM = "[0-9]{1,9}"


def _alt(words):
    return "(?:%s)" % "|".join(re.escape(word) for word in sorted(set(words), key=len, reverse=True))


CLI_LINE_PATTERNS = tuple(recorded.PROFILE_LINE_PATTERNS) + tuple(re.compile(pattern + r"\Z") for pattern in (
    "ingest: ok",
    "ingest: refused \\(%s\\)" % _alt(recorded.EXPORT_REFUSAL_REASONS),
    re.escape("ingest hint: " + recorded.EXPORT_REFUSAL_HINTS["too_large"]),
    "snapshot: written",
    "snapshot: refused \\(%s\\)" % _alt(recorded.EXPORT_REFUSAL_REASONS),
    "records: refused \\(%s\\)" % _alt(engine.RECORD_REFUSAL_REASONS),
    "private path: refused \\(%s\\)" % _alt(private.REFUSAL_REASONS),
    "replay: %s" % _alt(agree.VERDICT_WORDS),
    "replay: refused \\(%s\\)" % _alt(replay.REFUSAL_REASONS),
    "runs in snapshot: %s" % _NUM,
    "runs replayed: %s" % _NUM,
    "runs passed: %s" % _NUM,
    "runs failed: %s" % _NUM,
    "runs excluded %s: %s" % (_alt(agree.EXCLUSION_REASONS), _NUM),
    "distinct configurations: %s" % _NUM,
    "pairs compared: %s" % _NUM,
    "margin comparisons: %s" % _NUM,
    "dispatch comparisons: %s" % _NUM,
    "borderline: %s" % _NUM,
    "runs with disagreeing results: %s" % _NUM,
    "runs failed at stage %s: %s" % (_alt(constants.FAILED_STAGES), _NUM),
    "runs with differing data %s: %s" % (_alt(agree.DATA_CHECK_WORDS), _NUM),
    "non-empty comparisons %s: %s" % (_alt(agree.KINDS), _NUM),
    "not exercised: %s" % _alt(agree.KINDS),
    "report: written",
    "usage: pandapower_replay.py \\{ingest,replay\\} \\.\\.\\.",
    "usage error: %s" % _alt(("unknown command", "bad or missing arguments")),
    "error: unexpected \\([A-Z][A-Za-z]{0,39}\\)",
))


class _Printer(object):
    """The only way a line reaches the terminal: it must match CLI_LINE_PATTERNS."""

    def __init__(self, out, err):
        self.out = out
        self.err = err

    def say(self, text, stream=None):
        if not any(pattern.match(text) for pattern in CLI_LINE_PATTERNS):
            raise ValueError("a printed line is outside the command vocabulary")
        target = self.out if stream is None else stream
        target.write(text + "\n")

    def problem(self, text):
        self.say(text, self.err)

    def flush(self):
        for stream in (self.out, self.err):
            try:
                stream.flush()
            except Exception:  # noqa: BLE001 - a closed stream must not hide the exit code
                pass


# -- the command line ----------------------------------------------------------------------------


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """An argument parser that raises instead of printing, so no argument text is ever echoed."""

    def error(self, message):
        raise _UsageError()

    def exit(self, status=0, message=None):
        raise _UsageError()


def _build_parser():
    parser = _Parser(prog=_PROGRAM, add_help=False)
    commands = parser.add_subparsers(dest="command", parser_class=_Parser)
    ingest_parser = commands.add_parser("ingest", add_help=False)
    ingest_parser.add_argument("--export", required=True)
    ingest_parser.add_argument("--mapping", default=None)
    ingest_parser.add_argument("--check-dir", dest="check_dir", default=None)
    replay_parser = commands.add_parser("replay", add_help=False)
    replay_parser.add_argument("--snapshot", default=None)
    replay_parser.add_argument("--check-dir", dest="check_dir", default=None)
    replay_parser.add_argument("--mapping", default=None)
    replay_parser.add_argument("--ci", action="store_true")
    return parser


# -- the lines of a summary ------------------------------------------------------------------------


def render_summary_lines(summary):
    """The printed lines of an `agree.Summary`, verdict first; every one matches CLI_LINE_PATTERNS
    (the printer checks again). A reason, stage or check appears only with a non-zero count."""
    lines = [
        "replay: %s" % summary.word,
        "runs in snapshot: %d" % summary.runs_in_snapshot,
        "runs replayed: %d" % summary.runs_replayed,
        "runs passed: %d" % summary.runs_passed,
        "runs failed: %d" % summary.runs_failed,
    ]
    for reason in agree.EXCLUSION_REASONS:
        if summary.excluded[reason]:
            lines.append("runs excluded %s: %d" % (reason, summary.excluded[reason]))
    lines += [
        "distinct configurations: %d" % summary.configurations,
        "pairs compared: %d" % summary.pairs_compared,
        "margin comparisons: %d" % summary.margin_comparisons,
        "dispatch comparisons: %d" % summary.dispatch_comparisons,
        "borderline: %d" % summary.borderline,
        "runs with disagreeing results: %d" % summary.runs_disagreeing,
    ]
    for stage in constants.FAILED_STAGES:
        if summary.failed_stages[stage]:
            lines.append("runs failed at stage %s: %d" % (stage, summary.failed_stages[stage]))
    for check in agree.DATA_CHECK_WORDS:
        if summary.data_differences[check]:
            lines.append("runs with differing data %s: %d" % (check, summary.data_differences[check]))
    for kind in agree.KINDS:
        lines.append("non-empty comparisons %s: %d" % (kind, summary.nonempty[kind]))
    for kind in summary.not_exercised:
        lines.append("not exercised: %s" % kind)
    return lines


# -- the private report ----------------------------------------------------------------------------


def _deviation(item):
    return None if item is None else study.json_safe(item._asdict())


def report_document(result, backend, snapshot, header_extra):
    """The private report as a JSON-safe dictionary (`study.json_safe`): the header (pandapower
    version, the tolerance rules, the settings in force, the snapshot's counts, `header_extra`),
    the summary, the largest deviation even on a pass, the worst per quantity, the largest
    borderline excess, the exclusions with run ids, every finding with its detail, and each run's
    outcome. Only local mode calls this."""
    detail = result.gate.detail
    version = pandapower.__version__
    document = {
        "header": dict(
            header_extra, pandapower_version=version, tolerances=agree.tolerance_header(),
            settings=engine.settings_record(backend, version),
            snapshot_counts=dict(snapshot.counts)),
        "verdict": result.gate.word,
        "summary": result.gate.summary.as_dict(),
        "largest_deviation": _deviation(detail.largest),
        "worst_per_quantity": dict((name, _deviation(item)) for name, item in detail.worst.items()),
        "largest_borderline": _deviation(detail.borderline_largest),
        "exclusions": [{"run_id": run_id, "reason": reason} for run_id, reason in detail.exclusions],
        "findings": [
            {"run_id": run_id, "class": found.klass, "check": found.check, "where": found.where,
             "detail": found.detail} for run_id, found in detail.findings],
        "notes": dict(detail.notes),
        "outcomes": [
            {"run_id": outcome.run_id, "status": outcome.status, "reason": outcome.reason}
            for outcome in result.outcomes],
    }
    return study.json_safe(document)


# -- finding the inputs ----------------------------------------------------------------------------

_CHECK_FILES = ("report.json", "scaling_details.json", "converted_network.json")


def _pandapower_root(repo_root):
    return os.path.join(private.private_root(repo_root), "pandapower")


def _newest_snapshot(repo_root):
    folder = os.path.join(_pandapower_root(repo_root), "snapshots")
    try:
        names = sorted(name for name in os.listdir(folder)
                       if name.startswith("snapshot_") and name.endswith(".json"))
    except OSError:
        return None
    return os.path.join(folder, names[-1]) if names else None


def _newest_check(repo_root):
    sessions = os.path.join(_pandapower_root(repo_root), "sessions")
    found = []
    try:
        for session in os.listdir(sessions):
            base = os.path.join(sessions, session)
            for name in os.listdir(base):
                folder = os.path.join(base, name)
                if name.startswith("check_") and all(
                        os.path.isfile(os.path.join(folder, member)) for member in _CHECK_FILES):
                    found.append((name, session, folder))
    except OSError:
        return None
    return max(found)[2] if found else None


def _default_mapping(repo_root):
    return os.path.join(_pandapower_root(repo_root), "mapping.json")


def _file_sha256(path):
    digest = hashlib.sha256()
    try:
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _moment(now):
    value = now() if callable(now) else now
    if value is None:
        value = datetime.datetime.now(datetime.timezone.utc)
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc)
    return value


def _stamp(moment):
    return moment.strftime("%Y%m%dT%H%M%SZ")


# -- the two commands ------------------------------------------------------------------------------


class _Refused(Exception):
    """A refusal that has already been said; main only returns the exit code."""


def _run_ingest(args, say, repo_root, now):
    export = private.require_private(args.export, repo_root)
    mapping = args.mapping if args.mapping is not None else _default_mapping(repo_root)
    mapping = private.require_private(mapping, repo_root)
    check = args.check_dir if args.check_dir is not None else _newest_check(repo_root)
    check = None if check is None else private.require_private(check, repo_root)
    try:
        result = recorded.ingest_export(export, repo_root=repo_root, now=_moment(now))
    except recorded.ExportRefused as problem:
        say("ingest: refused (%s)" % problem.reason, "err")
        if problem.hint is not None:
            say("ingest hint: %s" % problem.hint, "err")
        return EXIT_USAGE
    mapping_sha = _file_sha256(mapping) if os.path.isfile(mapping) else None
    case_sha = None
    if check is not None:
        try:
            case_sha = engine.load_session_hashes(check)[0]
        except engine.RecordsRefused:
            case_sha = None
    say("ingest: ok")
    say("snapshot: written")
    for line in recorded.profile_lines(recorded.profile(result.snapshot, mapping_sha, case_sha)):
        say(line)
    return EXIT_OK


def _replay_inputs(args, repo_root, say):
    """(snapshot path, check folder, mapping path) after every refusal; each is inside data/private."""
    snapshot = args.snapshot if args.snapshot is not None else _newest_snapshot(repo_root)
    if snapshot is None or not os.path.isfile(snapshot):
        say("replay: refused (snapshot_missing)", "err")
        raise _Refused()
    check = args.check_dir if args.check_dir is not None else _newest_check(repo_root)
    if check is None or not all(os.path.isfile(os.path.join(check, member)) for member in (
            "report.json", "scaling_details.json")):
        say("replay: refused (records_missing)", "err")
        raise _Refused()
    mapping = args.mapping if args.mapping is not None else _default_mapping(repo_root)
    if not os.path.isfile(mapping):
        say("replay: refused (mapping_missing)", "err")
        raise _Refused()
    network = os.path.join(check, "converted_network.json")
    if not os.path.isfile(network):
        say("replay: refused (network_missing)", "err")
        raise _Refused()
    for path in (snapshot, check, mapping, network):
        private.require_private(path, repo_root)
    return snapshot, check, mapping


def _run_replay(args, say, repo_root, now, environ, replay_fn):
    ci = bool(args.ci) or environ.get("GITHUB_ACTIONS") == "true"
    snapshot_path, check, mapping = _replay_inputs(args, repo_root, say)
    network = os.path.join(check, "converted_network.json")
    try:
        snapshot = recorded.load_snapshot(snapshot_path, repo_root)
    except recorded.ExportRefused as problem:
        say("snapshot: refused (%s)" % problem.reason, "err")
        return EXIT_USAGE
    try:
        backend = engine.load_recorded_backend(check)
        session_case = engine.load_session_hashes(check)[0]
    except engine.RecordsRefused as problem:
        say("records: refused (%s)" % problem.reason, "err")
        return EXIT_USAGE
    try:
        result = replay_fn(snapshot, backend, network, mapping, session_case)
    except replay.ReplayRefused as problem:
        say("replay: refused (%s)" % problem.reason, "err")
        return EXIT_USAGE
    if not ci:
        folder = os.path.join(_pandapower_root(repo_root), "replays",
                              "replay_%s" % _stamp(_moment(now)))
        private.make_private_dir(folder, repo_root)
        document = report_document(result, backend, snapshot, {"mode": "local"})
        private.write_private_json(os.path.join(folder, "report.json"), document, REPORT_MARKER,
                                   repo_root)
    for line in render_summary_lines(result.gate.summary):
        say(line)
    if not ci:
        say("report: written")
    return EXIT_OK if result.gate.word == "pass" else EXIT_FAILED


# -- main ------------------------------------------------------------------------------------------


def main(argv, out=None, err=None, repo_root=None, now=None, environ=None, replay_fn=None):
    """
    Run the owner's command `argv` (without the program name) and return the exit code. `out` and
    `err` are text streams (default stdout and stderr), `repo_root` points the private-path guard at
    another repository (tests), `now` is a datetime or a function returning one (the stamp of the
    snapshot and the report folder), `environ` the environment (default os.environ) and `replay_fn`
    the replay (default `replay.replay_snapshot`; a test seam called as replay_fn(snapshot, backend,
    network_path, mapping_path, session_case_sha256)). Never raises.
    """
    printer = _Printer(sys.stdout if out is None else out, sys.stderr if err is None else err)
    environment = os.environ if environ is None else environ
    runner = replay.replay_snapshot if replay_fn is None else replay_fn

    def say(text, stream=None):
        printer.say(text, printer.err if stream == "err" else None)

    try:
        try:
            args = _build_parser().parse_args(list(argv))
            if args.command is None:
                raise _UsageError()
        except _UsageError:
            printer.problem("usage: pandapower_replay.py {ingest,replay} ...")
            printer.problem("usage error: bad or missing arguments")
            return EXIT_USAGE
        if args.command == "ingest":
            return _run_ingest(args, say, repo_root, now)
        return _run_replay(args, say, repo_root, now, environment, runner)
    except _Refused:
        return EXIT_USAGE
    except private.PrivatePathRefused as problem:
        _quiet(printer, "private path: refused (%s)" % problem.reason)
        return EXIT_USAGE
    except KeyboardInterrupt:
        return 130
    except Exception as problem:  # noqa: BLE001 - nothing may escape as a traceback
        word = type(problem).__name__
        _quiet(printer, "error: unexpected (%s)" % (
            word if re.match(r"[A-Z][A-Za-z]{0,39}\Z", word) else "Exception"))
        return EXIT_USAGE
    finally:
        printer.flush()


def _quiet(printer, text):
    try:
        printer.problem(text)
    except Exception:  # noqa: BLE001
        pass
