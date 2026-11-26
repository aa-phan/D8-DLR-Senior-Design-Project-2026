"""
The hourly runner of the pandapower job (pandapower-solver Phase 5, plan 05-01: OPS-02, OPS-03;
decisions D-02, D-03, D-04, D-05, D-08, D-10, D-13, D-14).

    pandapower_hourly.py run

`run` is the command the workflow runs every hour. `soak` (plan 05-04: OPS-05; decisions D-04, D-09,
D-12) is the per-solver gap check and the trailing 24-slot count, run after it:

    pandapower_hourly.py soak [--since YYYY-MM-DDTHH:00:00Z]

Without `--since` it reports and exits 0 whatever the gaps are (6 only when the check cannot run), so
one missed hour does not keep every later hourly run red. With `--since` it is the owner's closing
check: exit 0 only when pandapower has no gap in the window and the count is at least 24, else 5.
The commands `bundle` and `scan-log` arrive in plan 05-05; the usage line names them already so it
does not change later.

What is printed (D-05, D-14). Everything printed goes through one printer (`_Printer.say`) that
accepts only lines matching `HOURLY_LINE_PATTERNS`: counts of one to nine digits and words of fixed
sets. A run id, a hash, a path, a bus number, a figure or any error text cannot reach it; an
unexpected error prints only its class name. No pattern admits a line that starts with two colons,
so a printed line can never be read as a workflow command. The output of the study, of the
libraries and of the run loop (file descriptors 1 and 2, `sys.stdout`, `sys.stderr`, logging and
warnings) is sent to the null device while a command runs.

What is private (D-08). The network, the mapping and the two recorded-settings documents arrive as
four single-line base64 values in environment variables, are decoded only into a new temporary
folder (under RUNNER_TEMP when set) and the folder is removed when the command ends, however it
ends. Nothing decoded is ever printed, logged or kept.

Dry by default (D-02, D-13). The run is live only when the environment variable PANDAPOWER_LIVE is
exactly the text `true`. A dry run takes no database connection at all: `dry_run` has no connect
parameter and this module imports the writer-side modules of the PSS/E job (`job`, `writer`, `gaps`)
only inside the live function, so a dry run never loads them (D-10). A live run is refused when the
recorded settings are a placeholder (D-03), before the ratings are read, before the study and
before any connection is opened.

Exit codes: 0 (the run is ok, a dry run passed), 1 (the study failed, or the run was recorded as
failed), 2 (usage, any refusal or unexpected error), 3 (a live run could not be recorded), 5 and 6
(the `soak` command: 5 gaps or a count below 24 under `--since`, 6 the check could not run), 130
(interrupted).
"""

import argparse
import base64
import binascii
import collections
import datetime
import functools
import io
import logging
import os
import re
import shutil
import sys
import tempfile
import warnings

from psse_job import constants, contract, ratings, run_record
from pandapower_job import cli, convert, engine, soak

PROGRAM = "pandapower_hourly.py"
LIVE_VARIABLE = "PANDAPOWER_LIVE"
TEMP_PREFIX = "pandapower_hourly_"

# (word, environment variable, file name in the temporary folder, size cap of the decoded bytes)
SECRET_ENV = (
    ("network", "PANDAPOWER_NETWORK_B64", "network.json", convert.MAX_CONVERTED_BYTES),
    ("mapping", "PANDAPOWER_MAPPING_B64", "mapping.json", engine.MAX_RECORD_BYTES),
    ("settings", "PANDAPOWER_SETTINGS_B64", "report.json", engine.MAX_RECORD_BYTES),
    ("scaling", "PANDAPOWER_SCALING_B64", "scaling_details.json", engine.MAX_RECORD_BYTES),
)
READ_ENV = (constants.ENV_SUPABASE_URL, constants.ENV_PUBLISHABLE_KEY)
INPUT_REFUSAL_REASONS = ("missing_secret", "bad_base64", "too_large", "unwritable")

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_NOT_RECORDED = 3
EXIT_GAPS = 5
EXIT_CHECK_FAILED = 6

USAGE_LINE = "usage: pandapower_hourly.py {run,soak,bundle,scan-log} ..."
# command -> its flags; later plans add keys
COMMAND_FLAGS = {"run": (), "soak": ("--since",)}
# the solver labels the gap check can print: the two tags, the gap check's own `unknown` for a
# label that is not a plain tag, and `other` for any other plain tag
SOLVER_WORDS = (contract.SOLVER_PSSE, engine.SOLVER, "unknown", "other")

_NUM = "[0-9]{1,9}"
_COUNT_LIMIT = 999999999


def _alt(words):
    return "(?:%s)" % "|".join(re.escape(word) for word in sorted(set(words), key=len, reverse=True))


HOURLY_LINE_PATTERNS = tuple(re.compile(pattern + r"\Z") for pattern in (
    "mode: (?:dry|live)",
    "inputs: ok",
    "inputs: refused \\(%s\\)" % _alt(INPUT_REFUSAL_REASONS),
    "records: refused \\(%s\\)" % _alt(engine.RECORD_REFUSAL_REASONS),
    "placeholder: refused",
    "ratings: city_rating=%s static=%s" % (_NUM, _NUM),
    "study: ok",
    "study: failed at stage %s" % _alt(constants.FAILED_STAGES),
    "outcome: (?:ok|fallback|failed)",
    "rows: run=%s dispatch=%s margin=%s contingency=%s" % (_NUM, _NUM, _NUM, _NUM),
    "dry run: nothing was written to the database",
    "run status: (?:written|already_recorded|failure_recorded|not_recorded)",
    re.escape(USAGE_LINE),
    "usage error: %s" % _alt(("unknown command", "bad or missing arguments")),
    "error: unexpected \\([A-Z][A-Za-z]{0,39}\\)",
    "gap check: solver %s runs=%s gaps=%s" % (_alt(SOLVER_WORDS), _NUM, _NUM),
    "gap check: solver %s no runs recorded" % _alt(SOLVER_WORDS),
    "gap check: could not run",
    "soak: consecutive_slots=%s of %d fallback_slots=%s" % (_NUM, soak.SOAK_SLOTS, _NUM),
    "soak: (?:pass|not yet)",
))


class InputsRefused(ValueError):
    """An input was refused; `reason` is one of INPUT_REFUSAL_REASONS and the message holds
    nothing else (no value, no path)."""

    def __init__(self, reason):
        self.reason = reason
        ValueError.__init__(self, "inputs refused: %s" % reason)


DryOutcome = collections.namedtuple(
    "DryOutcome", ["outcome", "failed_stage", "ratings", "rows", "exit_code"])
LiveOutcome = collections.namedtuple(
    "LiveOutcome", ["outcome", "status", "failed_stage", "ratings", "rows", "exit_code"])


# -- the printer -----------------------------------------------------------------------------------


class _Printer(object):
    """The only way a line reaches the output: it must match HOURLY_LINE_PATTERNS."""

    def __init__(self, stream):
        self.stream = stream

    def say(self, text):
        if not any(pattern.match(text) for pattern in HOURLY_LINE_PATTERNS):
            raise ValueError("a printed line is outside the command vocabulary")
        self.stream.write(text + "\n")

    def flush(self):
        try:
            self.stream.flush()
        except Exception:  # noqa: BLE001 - a closed stream must not hide the exit code
            pass


# -- the command line ------------------------------------------------------------------------------


class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    """An argument parser that raises instead of printing, so no argument text is ever echoed."""

    def error(self, message):
        raise _UsageError()

    def exit(self, status=0, message=None):
        raise _UsageError()


def _build_parser():
    parser = _Parser(prog=PROGRAM, add_help=False)
    commands = parser.add_subparsers(dest="command", parser_class=_Parser)
    for name, flags in COMMAND_FLAGS.items():
        command = commands.add_parser(name, add_help=False)
        for flag in flags:
            command.add_argument(flag, default=None)
    return parser


# -- the mode --------------------------------------------------------------------------------------


def decide_mode(environ):
    """`live` only when PANDAPOWER_LIVE is exactly the text `true` (no stripping, no case
    folding); every other value, including an absent or empty one, is `dry` (D-02, D-13)."""
    return "live" if environ.get(LIVE_VARIABLE) == "true" else "dry"


# -- the private inputs ----------------------------------------------------------------------------


def materialize(environ, folder):
    """Decode the four secrets of SECRET_ENV into new private files in `folder`; return a dict
    from the secret's word to the file's path. A missing value is InputsRefused missing_secret,
    text that is not strict base64 (or decodes to nothing) bad_base64, a decoded size above the
    secret's cap too_large and a file that cannot be created unwritable. Nothing is echoed."""
    paths = {}
    for word, name, file_name, cap in SECRET_ENV:
        value = environ.get(name)
        if value is None or not str(value).strip():
            raise InputsRefused("missing_secret")
        text = str(value).strip(" \t\r\n\f\v")
        try:
            data = base64.b64decode(text, validate=True)
        except (binascii.Error, ValueError):
            raise InputsRefused("bad_base64") from None
        if not data:
            raise InputsRefused("bad_base64")
        if len(data) > cap:
            raise InputsRefused("too_large")
        path = os.path.join(folder, file_name)
        try:
            with open(path, "xb") as handle:
                handle.write(data)
        except OSError:
            raise InputsRefused("unwritable") from None
        paths[word] = path
    return paths


# -- the dry path (D-10): no connection exists in it -----------------------------------------------


def _moment(clock):
    value = clock() if clock is not None else datetime.datetime.now(datetime.timezone.utc)
    return value


def _rating_counts(selection):
    chosen = [selection.choices[city].source for city in constants.CITIES]
    return (sum(1 for source in chosen if source == constants.SOURCE_CITY_RATING),
            sum(1 for source in chosen if source == constants.SOURCE_STATIC))


def _row_counts(results):
    return (1, len(results.dispatch or []), len(results.margins or []),
            len(results.contingencies or []))


def dry_run(prepared, fetch, environ, clock=None):
    """One pandapower run with nothing written anywhere. It repeats `job.run_once`'s sequence up
    to the stored rows and then stops: the start time, the ratings selection, the study, the
    validation of its results, the run record and the result rows. It takes no connection and
    imports nothing that could open one. Returns a DryOutcome."""
    started_at = _moment(clock)
    context = contract.RunContext(
        run_record.new_run_id(started_at, engine.SOLVER), started_at,
        run_record.case_label(prepared.case_id), prepared.case_sha256, prepared.mapping_sha256,
        run_record.job_version(environ), engine.SOLVER)
    selection = ratings.select_ratings(fetch, started_at)
    counts = _rating_counts(selection)

    results = None
    failure = None
    try:
        results = prepared.study(selection, context)
    except Exception as exc:  # noqa: BLE001 - every study failure is a failed dry run
        failure = run_record.failure_from_exception("internal", exc)

    rows = None
    if failure is None:
        try:
            finished_at = _moment(clock)
            if finished_at < started_at:
                finished_at = started_at
            run_record.validate_results(results, selection)
            record = run_record.build_run_record(context, selection, finished_at, results=results)
            run_record.result_rows(record, results)
            rows = _row_counts(results)
        except Exception as exc:  # noqa: BLE001 - an invalid set would never be written
            failure = run_record.failure_from_exception("validate_results", exc)
    if failure is not None:
        return DryOutcome("failed", failure.stage, counts, None, EXIT_FAILED)
    return DryOutcome(run_record.outcome_for(selection, False), None, counts, rows, EXIT_OK)


# -- the live path (D-04): the only code that imports the writer side ------------------------------


def live_run(prepared, fetch, connect, environ, clock=None):
    """One recorded run: `job.run_once` with this engine's solver tag (a run started with the
    default tag would be stored as a failed PSS/E run with no figures). `job` and `writer` are
    imported here and nowhere else, so a dry run never loads them (D-10). `connect` defaults to the
    writer connection built from SUPABASE_PSSE_DB_URL of `environ`; this function never calls it,
    `job.run_once` does, after the study. Returns a LiveOutcome; the run id is not part of it."""
    from psse_job import job, writer

    if connect is None:
        connect = functools.partial(writer.connect, env=environ)
    seen = {}

    def recording_study(selection, context):
        seen["selection"] = selection
        results = prepared.study(selection, context)
        seen["results"] = results
        return results

    outcome = job.run_once(
        fetch, recording_study, connect, prepared.case_id, prepared.case_sha256,
        prepared.mapping_sha256, clock=clock, env=environ, solver=engine.SOLVER)
    selection = seen.get("selection")
    counts = None if selection is None else _rating_counts(selection)
    rows = None
    if outcome.status == "written" and seen.get("results") is not None:
        rows = _row_counts(seen["results"])
    return LiveOutcome(outcome.outcome, outcome.status, outcome.failed_stage, counts, rows,
                       outcome.exit_code)


# -- the soak command (D-04, D-09, D-12): reads only; imports the writer side inside its functions ---

_SINCE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:00:00Z\Z")
_SOLVER_SECTION = re.compile(r"solver ([a-z][a-z0-9_]*): ([0-9]+) runs recorded\Z")
_SOLVER_EMPTY = re.compile(r"solver ([a-z][a-z0-9_]*): no runs recorded\Z")
_GAPS_FOUND = re.compile(r"([0-9]+) gaps(?: |\Z)")
_NO_GAPS = re.compile(r"no gaps(?: |\Z)")
SOAK_CHECK_FAILED = "gap check: could not run"


def parse_since(text):
    """The aware UTC datetime of `text`, which must be a whole UTC hour spelled exactly
    `YYYY-MM-DDTHH:00:00Z`; anything else (minutes set, no `Z`, a date only, an impossible date) is
    a usage error."""
    if not isinstance(text, str) or _SINCE.match(text) is None:
        raise _UsageError()
    try:
        value = datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise _UsageError() from None
    return value.replace(tzinfo=datetime.timezone.utc)


def _solver_word(name):
    return name if name in SOLVER_WORDS else "other"


def gap_lines(text):
    """The counts-only lines of the report `gaps.format_solver_report` built: one
    `gap check: solver NAME runs=N gaps=N` line per solver section (gaps from its `N gaps` or
    `no gaps` line) and `gap check: solver NAME no runs recorded` for a solver with no rows. A label
    outside the solver words prints as `other`. Slot times and gap lines are never copied."""
    lines = []
    pending = None
    for line in text.splitlines():
        empty = _SOLVER_EMPTY.match(line)
        if empty is not None:
            pending = None
            lines.append("gap check: solver %s no runs recorded" % _solver_word(empty.group(1)))
            continue
        section = _SOLVER_SECTION.match(line)
        if section is not None:
            pending = (_solver_word(section.group(1)), min(int(section.group(2)), _COUNT_LIMIT))
            continue
        if pending is None:
            continue
        found = _GAPS_FOUND.match(line)
        if found is not None:
            gaps_count = min(int(found.group(1)), _COUNT_LIMIT)
        elif _NO_GAPS.match(line) is not None:
            gaps_count = 0
        else:
            continue
        lines.append("gap check: solver %s runs=%d gaps=%d" % (pending[0], pending[1], gaps_count))
        pending = None
    return lines


def read_runs(connect):
    """`(runs, current_slot)`: every run as (slot_time, solver, outcome) and the database's current
    UTC hour, read on a new connection that is made read-only before its first statement and closed
    at the end. `psycopg` applies `read_only` only to transactions it opens itself, and the writer
    connection is autocommit, so autocommit is left first (as `gaps.run_by_solver` does)."""
    from psse_job import gaps

    conn = connect()
    try:
        conn.autocommit = False
        conn.read_only = True
        runs = gaps.fetch_runs(conn)
        current = gaps.fetch_current_slot(conn)
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass
    return runs, current


def run_soak(environ, connect=None, since=None):
    """The per-solver gap check with pandapower expected, plus the trailing 24-slot count.

    Returns `(lines, exit_code)`. The report of `gaps.run_by_solver` goes to a buffer and only its
    counts are printed (`gap_lines`); the runs are then read once more, read-only, for the count
    of `soak.trailing_slots`. Without `since` the exit is 0 whatever the gaps are (D-09, so one
    missed hour does not keep every later hourly run red); with `since` (an aware UTC datetime) it is
    0 only when the check found no pandapower gap in the window and the count is at least 24, else 5.
    The exit is 6 and the only line `gap check: could not run` whenever the check cannot run; the
    buffer's text and any error text are never printed."""
    from psse_job import gaps, writer

    if connect is None:
        connect = functools.partial(writer.connect, env=environ)
    buffer = io.StringIO()
    try:
        code = gaps.run_by_solver(
            environ, since=since, fail_on_gaps=since is not None, out=buffer, connect=connect,
            expected=(engine.SOLVER,))
        if code == EXIT_CHECK_FAILED:
            return [SOAK_CHECK_FAILED], EXIT_CHECK_FAILED
        runs, current = read_runs(connect)
        lines = gap_lines(buffer.getvalue())
        count = soak.trailing_slots(runs, current, engine.SOLVER)
    except Exception:  # noqa: BLE001 - the check could not run; no error text is ever printed
        return [SOAK_CHECK_FAILED], EXIT_CHECK_FAILED
    passed = soak.soak_passed(count)
    lines.append("soak: consecutive_slots=%d of %d fallback_slots=%d" % (
        min(count.slots, _COUNT_LIMIT), soak.SOAK_SLOTS, min(count.fallback_slots, _COUNT_LIMIT)))
    lines.append("soak: pass" if passed else "soak: not yet")
    if since is None:
        return lines, EXIT_OK
    return lines, (EXIT_OK if code == EXIT_OK and passed else EXIT_GAPS)


def _soak_command(say, environ, connect, since_text):
    since = None if since_text is None else parse_since(since_text)
    lines, code = run_soak(environ, connect=connect, since=since)
    for line in lines:
        say(line)
    return code


# -- the main --------------------------------------------------------------------------------------


class OutputSink(object):
    """A context manager that closes every public-log route while a command runs (D-05, D-14).

    On enter it opens the printer's stream as a duplicate of the real standard output (unless the
    caller supplied `out`), then points file descriptors 1 and 2, `sys.stdout` and `sys.stderr` at
    the null device, disables logging and ignores warnings. It returns the printer's stream. On exit,
    each step guarded so one failure does not skip the rest, it closes the printer's stream, puts
    warnings, logging, `sys.stdout`, `sys.stderr` and descriptors 1 and 2 back and closes every
    descriptor and stream it opened. Output of the study, of pandapower, of the run loop's logger
    (which logs the stored error text, and a mapping error can name a bus) and of a traceback
    therefore goes nowhere; only the printer's lines are shown.
    """

    def __init__(self, out=None):
        self.out = out
        self._undo = []
        self._printer_stream = None

    def _push(self, step):
        self._undo.append(step)

    def __enter__(self):
        try:
            return self._enter()
        except BaseException:
            self._unwind()
            raise

    def _enter(self):
        for stream in (sys.stdout, sys.stderr):
            try:
                stream.flush()
            except Exception:  # noqa: BLE001
                pass
        target = self.out
        if target is None:
            target = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
            self._printer_stream = target
        saved = []
        for number in (1, 2):
            saved.append((number, os.dup(number)))
        self._push(lambda: self._restore_descriptors(saved))
        null = os.open(os.devnull, os.O_WRONLY)
        self._push(lambda: os.close(null))
        for number in (1, 2):
            os.dup2(null, number)
        previous = (sys.stdout, sys.stderr)
        quiet = [open(os.devnull, "w", encoding="utf-8") for _ in (1, 2)]
        sys.stdout, sys.stderr = quiet
        self._push(lambda: [setattr(sys, "stdout", previous[0]), setattr(sys, "stderr", previous[1]),
                            [stream.close() for stream in quiet]])
        level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        self._push(lambda: logging.disable(level))
        caught = warnings.catch_warnings()
        caught.__enter__()
        self._push(lambda: caught.__exit__(None, None, None))
        warnings.simplefilter("ignore")
        return target

    @staticmethod
    def _restore_descriptors(saved):
        for number, copy in saved:
            try:
                os.dup2(copy, number)
            except Exception:  # noqa: BLE001 - the other descriptor is still restored
                pass
            finally:
                try:
                    os.close(copy)
                except Exception:  # noqa: BLE001
                    pass

    def _unwind(self):
        # The printer's stream is flushed and closed first, so the lines leave before anything
        # else is put back.
        stream, self._printer_stream = self._printer_stream, None
        if stream is not None:
            try:
                stream.flush()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
        steps, self._undo = self._undo, []
        for step in reversed(steps):
            try:
                step()
            except Exception:  # noqa: BLE001 - one failed step must not skip the rest
                pass

    def __exit__(self, exc_type, exc, tb):
        self._unwind()
        return False


class _PlainStream(object):
    """The output stream without redirects (a test seam; the entry script always redirects)."""

    def __init__(self, out):
        self.out = out

    def __enter__(self):
        return sys.stdout if self.out is None else self.out

    def __exit__(self, exc_type, exc, tb):
        return False


def _say_result(say, result):
    """The lines of a finished run after the mode and inputs lines."""
    if result.ratings is not None:
        say("ratings: city_rating=%d static=%d" % result.ratings)
    if result.failed_stage is None:
        say("study: ok")
    else:
        say("study: failed at stage %s" % result.failed_stage)
    say("outcome: %s" % result.outcome)
    if result.rows is not None:
        say("rows: run=%d dispatch=%d margin=%d contingency=%d" % result.rows)


def _require_present(environ, mode):
    """Every secret, both read settings and, in live mode, the writer value must be non-blank;
    checked before any folder exists (InputsRefused missing_secret)."""
    names = [name for _word, name, _file, _cap in SECRET_ENV] + list(READ_ENV)
    if mode == "live":
        names.append(constants.ENV_PSSE_DB_URL)
    for name in names:
        value = environ.get(name)
        if value is None or not str(value).strip():
            raise InputsRefused("missing_secret")


def _run_command(say, environ, fetch, connect, clock, prepare, backend_loader):
    mode = decide_mode(environ)
    say("mode: %s" % mode)
    try:
        _require_present(environ, mode)
        folder = tempfile.mkdtemp(prefix=TEMP_PREFIX, dir=environ.get("RUNNER_TEMP") or None)
        try:
            paths = materialize(environ, folder)
            say("inputs: ok")
            backend = (backend_loader or engine.load_recorded_backend)(folder)
            if mode == "live" and engine.is_placeholder(backend):
                say("placeholder: refused")
                return EXIT_USAGE
            prepared = (prepare or engine.prepare_run)(
                backend, paths["network"], paths["mapping"], allow_placeholder=False)
            read = fetch if fetch is not None else (lambda: ratings.fetch_latest_rating(environ))
            if mode == "dry":
                result = dry_run(prepared, read, environ, clock)
                _say_result(say, result)
                say("dry run: nothing was written to the database")
            else:
                result = live_run(prepared, read, connect, environ, clock)
                _say_result(say, result)
                say("run status: %s" % result.status)
            return result.exit_code
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    except InputsRefused as problem:
        say("inputs: refused (%s)" % problem.reason)
        return EXIT_USAGE
    except engine.RecordsRefused as problem:
        say("records: refused (%s)" % problem.reason)
        return EXIT_USAGE


def main(argv, out=None, environ=None, repo_root=None, fetch=None, connect=None, clock=None,
         prepare=None, backend_loader=None, sink=True):
    """
    Run the command `argv` (without the program name) and return the exit code. `out` is a text
    stream for the printed lines (default stdout), `environ` the environment (default a copy of
    os.environ), `fetch` the ratings read, `connect` the writer connection of a live run, `clock` a
    function returning an aware datetime, `prepare` the engine's `prepare_run`, `backend_loader` the
    loader of the recorded backend and `repo_root` the repository root; each of the last six
    defaults to the real one and is a test seam. `sink` false leaves the output redirects off (a
    test seam). Never raises.
    """
    environment = dict(os.environ) if environ is None else environ
    stream = OutputSink(out) if sink else _PlainStream(out)
    try:
        with stream as target:
            printer = _Printer(target)
            return _dispatch(argv, printer, environment, fetch, connect, clock, prepare,
                             backend_loader)
    except Exception:  # noqa: BLE001 - nothing may escape, not even a failing output stream
        return EXIT_USAGE


def _dispatch(argv, printer, environment, fetch, connect, clock, prepare, backend_loader):
    say = printer.say
    try:
        try:
            args = _build_parser().parse_args(list(argv))
            if args.command is None:
                raise _UsageError()
            if args.command == "soak":
                return _soak_command(say, environment, connect, args.since)
        except _UsageError:
            say(USAGE_LINE)
            say("usage error: bad or missing arguments")
            return EXIT_USAGE
        return _run_command(say, environment, fetch, connect, clock, prepare, backend_loader)
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
        printer.say(text)
    except Exception:  # noqa: BLE001
        pass
