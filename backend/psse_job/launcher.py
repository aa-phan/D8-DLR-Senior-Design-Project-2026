"""
The launcher core of the hourly PSS/E job (pss-e-integration Phase 3, plan 03-01: SCH-01, TST-02).

`main(["run", "--config", FILE], psspy_loader)` is the whole hourly job: it reads every setting
from FILE, takes the run lock, checks the database host answers, starts PSS/E through the injected
`psspy_loader(cfg)`, runs study.prepare_run and job.run_once, prints one summary line and returns
an exit code. `psspy` is never imported here (the loader is injected; plan 03-04's entry script is
the only code that imports it), and psycopg is imported only by writer.connect. Standard library
and psse_job only, Python 3.7 syntax.

Decisions (the plan's D-01 to D-11):

  D-01  The configuration file is the whole configuration. The process environment is never read
        for a setting (a stray variable could silently point an unattended job at another
        database), and `--config` is required, so no default path depends on the environment
        either. `read_config` returns one resolved dict: PSSE_LOG_DIR (a `logs` folder next to the
        config file), PSSE_LOCK_PATH (`psse_job.lock` next to it), PSSE_MAX_BUSES (20000) and
        PSSE_PREFLIGHT (1) are filled in, so every consumer sees the same values. libpq's own PG*
        variables (PGSSLMODE, PGSERVICE, PGPASSFILE, ...) are read by libpq itself and are NOT
        isolated by this launcher.
  D-02  One command with subcommands; this plan builds `run` (with --config, --dry-run and
        --allow-placeholder). `main` dispatches through the module-level RUNNERS table keyed by
        mode, so plan 03-04 adds selftest, probe, gaps, credcheck and hold-lock without
        restructuring. A usage error is exit 2 and its text is redacted.
  D-03  Exit codes (EXIT_CODES is the one source for the guide and the other modules):
          0 ok, fallback written, or already recorded       job.EXIT_OK
          1 a failed run was recorded (dry-run: the study or its validation failed)
                                                            job.EXIT_FAILED_RECORDED
          2 usage or configuration error; nothing ran
          3 no record could be written: the SCH-02 gap      job.EXIT_NOT_RECORDED
          4 another instance holds the run lock; skipped, nothing recorded
          5 gaps found with --fail-on-gaps (plan 03-04's gaps mode)
          6 a check mode (selftest, probe, credcheck, gaps) could not complete or found a failure
            (plan 03-04)
          7 unexpected launcher error (redacted log line; nothing recorded)
  D-04  The lock is held from before PSS/E starts until after run_once returns (one PSS/E process
        per run). A second instance exits 4 and records nothing, because it never started a study.
  D-05  Before PSS/E starts, `run` opens a TCP connection to the database host and port (5 second
        timeout, port default 5432; PSSE_PREFLIGHT=0 switches it off). Failure is exit 3 and no
        licence is checked out. The 5 seconds bound the TCP connect only, not name resolution.
  D-06  If the loader raises (PsseUnavailable or anything else) the run is still recorded: a failed
        run at stage load_case whose message names the exception class and a path-scrubbed text,
        never a path, with the case file's label and sha256 and mapping_sha256 None.
  D-07  `run --dry-run` mirrors run_once up to the connect and never connects.
  D-08  A non-loopback database host needs sslmode require, verify-ca or verify-full in the URL
        (libpq's default `prefer` falls back to plaintext); loopback hosts are exempt.
  D-09  `--allow-placeholder` is accepted only together with `--dry-run`, so a real run always
        refuses a mapping marked placeholder and no configuration key can switch that off.
  D-10  PSSE_SITE_DIR, PSSE_PSSPY_DIR and PSSE_BIN_DIR are APPENDED to sys.path, never inserted
        first, so a module planted in a user-writable folder cannot shadow the standard library.
  D-11  The case and mapping paths are not checked for existence by the reader: a missing file must
        become a recorded failed run, not a silent exit 2 each hour. They must be absolute,
        because Task Scheduler's working directory is not the repository's.

Secrets: every log record passes a redacting filter against the configuration's own secrets, every
printed line passes redact(), and configuration errors name keys and line numbers only, never a
value or a line's text. UNVERIFIED until the laptop session (plans 03-07 and 03-08): that
os.add_dll_directory is needed or enough, that Task Scheduler passes the exit code through, and
anything about real PSS/E.
"""

import argparse
import collections
import contextlib
import datetime
import inspect
import logging
import logging.handlers
import os
import re
import socket
import sys
import urllib.parse

from psse_job import constants, contract, job, probe, psse_api, ratings, run_record, study, writer
from psse_job.lock import RunLock
from psse_job.redaction import env_secrets, redact

log = logging.getLogger("psse_job.launcher")

EXIT_OK = job.EXIT_OK
EXIT_FAILED_RECORDED = job.EXIT_FAILED_RECORDED
EXIT_USAGE = 2
EXIT_NOT_RECORDED = job.EXIT_NOT_RECORDED
EXIT_LOCKED = 4
EXIT_GAPS = 5
EXIT_CHECK_FAILED = 6
EXIT_UNEXPECTED = 7

# (name, code, meaning) in code order: the one source for the guide's table.
EXIT_CODES = (
    ("ok", EXIT_OK, "an ok or fallback run was written, or the run was already recorded"),
    ("failed_recorded", EXIT_FAILED_RECORDED,
     "the run failed and a failed record exists (dry-run: the study or its validation failed)"),
    ("usage", EXIT_USAGE, "usage or configuration error; nothing ran"),
    ("not_recorded", EXIT_NOT_RECORDED, "no record could be written (the gap SCH-02 detects)"),
    ("locked", EXIT_LOCKED, "another instance holds the run lock; skipped, nothing recorded"),
    ("gaps", EXIT_GAPS, "gaps found with --fail-on-gaps"),
    ("check_failed", EXIT_CHECK_FAILED,
     "a check mode (selftest, probe, credcheck, gaps) could not complete or found a failure"),
    ("unexpected", EXIT_UNEXPECTED, "unexpected launcher error (redacted log line, nothing recorded)"),
)

_MAX_CONFIG_BYTES = 65536
_LOG_FILE_NAME = "psse_job.log"
_LOCK_FILE_NAME = "psse_job.lock"
_PREFLIGHT_TIMEOUT_SECONDS = 5
_DEFAULT_MAX_BUSES = "20000"
_DEFAULT_PORT = 5432

DLL_DIRECTORY_HANDLES = []

ConfigKey = collections.namedtuple("ConfigKey", ["name", "kind", "secret", "required_for", "meaning"])

# kind: url | secret | path | dir | int | flag | text. `required_for` names the modes that need the
# key; modes this plan does not build yet are recorded now so the guide and plan 03-04 have one
# source ("credcheck-rest" marks the keys of the REST leg that --skip-rest turns off).
CONFIG_KEYS = (
    ConfigKey("SUPABASE_PSSE_DB_URL", "url", True, ("run", "gaps", "credcheck"),
              "postgres URL of the dlr_psse_writer role (session pooler)"),
    ConfigKey("SUPABASE_URL", "url", True, ("run", "credcheck-rest"),
              "Supabase project URL, for the ratings read"),
    ConfigKey("SUPABASE_PUBLISHABLE_KEY", "secret", True, ("run", "credcheck-rest"),
              "publishable key, for the ratings read"),
    ConfigKey("PSSE_CASE_PATH", "path", False, ("run", "dry-run", "probe"),
              "absolute path of Power Systems' case file"),
    ConfigKey("PSSE_MAPPING_PATH", "path", False, ("run", "dry-run"),
              "absolute path of the mapping file"),
    ConfigKey("PSSE_PSSPY_DIR", "dir", False, ("run", "dry-run", "selftest", "probe"),
              "folder holding psspy for the installed PSS/E"),
    ConfigKey("PSSE_BIN_DIR", "dir", False, (), "PSS/E program folder for the DLL search path"),
    ConfigKey("PSSE_SITE_DIR", "dir", False, (), "folder with extra Python packages (psycopg)"),
    ConfigKey("PSSE_LOG_DIR", "dir", False, (), "local log folder (default: logs next to the file)"),
    ConfigKey("PSSE_LOCK_PATH", "path", False, (), "run lock file (default: next to the file)"),
    ConfigKey("PSSE_MAX_BUSES", "int", False, (), "bus limit passed to psseinit (default 20000)"),
    ConfigKey("PSSE_JOB_VERSION", "text", False, (), "job version label stored with each run"),
    ConfigKey("PSSE_PREFLIGHT", "flag", False, (), "1 (default) checks the database host first, 0 skips"),
)
_KEYS_BY_NAME = dict((key.name, key) for key in CONFIG_KEYS)

_LINE_RE = re.compile(r"^([A-Z_][A-Z0-9_]*)[ \t]*=(.*)$")
_KEY_NAME_MAX = 40
_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_WHOLE_RE = re.compile(r"^[0-9]{1,9}$")
_MAX_BUSES_LIMIT = 2000000
_LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
_TLS_MODES = ("require", "verify-ca", "verify-full")
# A path in an exception text: a drive path (a folder name may hold spaces, but a segment never
# crosses a colon, semicolon or comma, so the text after the file name survives), a UNC path or a
# POSIX path with at least one folder.
_PATH_RE = re.compile(
    r"[A-Za-z]:[\\/](?:[^\\/'\"<>|:;,\r\n]*[\\/])*[^\\/'\"<>|\s]*"
    r"|\\\\[^\s'\"<>|]+"
    r"|/(?:[^/\s'\"<>|]+/)+[^/\s'\"<>|]*"
)
_LOAD_FAILURE_MAX_CHARS = 300


class ConfigError(Exception):
    """The configuration is unusable. `problems` name keys and line numbers only, never a value."""

    def __init__(self, problems):
        self.problems = list(problems)
        Exception.__init__(self, "; ".join(self.problems))


class PsseUnavailable(RuntimeError):
    """PSS/E could not be started (raised by a psspy loader)."""


# --------------------------------------------------------------------------- configuration


def _read_text(path):
    """The decoded text of the configuration file, or a ConfigError with no value in it."""
    problem = None
    data = b""
    try:
        with open(path, "rb") as handle:
            data = handle.read(_MAX_CONFIG_BYTES + 1)
    except OSError:
        problem = "the configuration file could not be read"
    if problem is None and len(data) > _MAX_CONFIG_BYTES:
        problem = "the configuration file is larger than %d bytes" % _MAX_CONFIG_BYTES
    text = None
    if problem is None:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeError:
            problem = "the configuration file is not UTF-8 text"
    if problem is not None:
        raise ConfigError([problem])
    return text


def _unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_lines(text):
    """(values, problems): KEY=VALUE lines of the known keys; problems carry keys and line numbers."""
    values = {}
    seen = set()
    problems = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _LINE_RE.match(line)
        if match is None:
            problems.append("line %d: not in KEY=VALUE form" % number)
            continue
        name = match.group(1)
        if name not in _KEYS_BY_NAME:
            if len(name) <= _KEY_NAME_MAX:
                problems.append("line %d: unknown key %s" % (number, name))
            else:
                problems.append("line %d: unknown key" % number)
            continue
        if name in seen:
            problems.append("line %d: repeated key %s" % (number, name))
            continue
        seen.add(name)
        value = _unquote(match.group(2).strip())
        if value:
            values[name] = value
    return values, problems


def _missing(values, mode):
    return [key.name for key in CONFIG_KEYS if mode in key.required_for and key.name not in values]


def _is_absolute(value):
    """A drive path (either slash), a UNC path, or (off Windows) a rooted POSIX path."""
    if _DRIVE_RE.match(value) or value.startswith("\\\\") or value.startswith("//"):
        return True
    return os.name != "nt" and value.startswith("/")


def _db_address(url):
    """(host, port) of a database URL, or None when it is not a postgres URL with a host and a valid port."""
    try:
        parts = urllib.parse.urlsplit(url)
        host = parts.hostname
        port = parts.port
    except ValueError:
        return None
    if parts.scheme.lower() not in ("postgres", "postgresql") or not host:
        return None
    return host, port or _DEFAULT_PORT


def _db_url_problem(url):
    """Why `url` cannot be the database URL, in words that contain no part of it; None when it can."""
    address = _db_address(url)
    if address is None:
        return "must be a postgres or postgresql URL with a host and a valid port"
    if address[0] in _LOOPBACK_HOSTS:
        return None
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    except ValueError:
        query = {}
    if (query.get("sslmode") or [""])[-1] not in _TLS_MODES:
        return "a non-local host needs sslmode=require, verify-ca or verify-full in the URL"
    return None


def _value_problems(values):
    """Problems with the values that are present, naming each key and never a value."""
    problems = []
    for key in CONFIG_KEYS:
        value = values.get(key.name)
        if value is None:
            continue
        message = None
        if key.kind in ("path", "dir"):
            if not _is_absolute(value):
                message = "must be an absolute path"
        elif key.kind == "int":
            if not _WHOLE_RE.match(value) or not 1 <= int(value) <= _MAX_BUSES_LIMIT:
                message = "must be a whole number from 1 to %d" % _MAX_BUSES_LIMIT
        elif key.kind == "flag":
            if value not in ("0", "1"):
                message = "must be 0 or 1"
        elif key.name == "SUPABASE_PSSE_DB_URL":
            message = _db_url_problem(value)
        if message:
            problems.append("key %s: %s" % (key.name, message))
    return problems


def read_config(path, mode=None):
    """
    The resolved configuration of the file at `path`: a dict of text to text holding the known
    keys that have a value, plus the defaults of D-01. Raises ConfigError (every problem at once,
    naming keys and line numbers only) for an unreadable file, a malformed line, an unknown or
    repeated key and, when `mode` is given, a key that mode requires and the file lacks.
    """
    values, problems = _parse_lines(_read_text(path))
    problems.extend(_value_problems(values))
    if mode is not None:
        problems.extend("missing key %s" % name for name in _missing(values, mode))
    if problems:
        raise ConfigError(problems)
    folder = os.path.dirname(os.path.abspath(path))
    values.setdefault("PSSE_LOG_DIR", os.path.join(folder, "logs"))
    values.setdefault("PSSE_LOCK_PATH", os.path.join(folder, _LOCK_FILE_NAME))
    values.setdefault("PSSE_MAX_BUSES", _DEFAULT_MAX_BUSES)
    values.setdefault("PSSE_PREFLIGHT", "1")
    return dict((key.name, values[key.name]) for key in CONFIG_KEYS if key.name in values)


# --------------------------------------------------------------------------- command line


class _UsageError(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message


class _UsageExit(Exception):
    def __init__(self, status):
        Exception.__init__(self, status)
        self.status = status


class _Parser(argparse.ArgumentParser):
    """An ArgumentParser that raises instead of printing the error and exiting."""

    def error(self, message):
        raise _UsageError(message)

    def exit(self, status=0, message=None):
        raise _UsageExit(status)


def build_parser():
    """The command line: `run --config FILE [--dry-run] [--allow-placeholder]` (more modes: plan 03-04)."""
    parser = _Parser(prog="psse-job", allow_abbrev=False,
                     description="Hourly PSS/E job launcher (settings come from the config file only).")
    modes = parser.add_subparsers(dest="mode", metavar="mode")
    modes.required = True
    run = modes.add_parser("run", allow_abbrev=False, help="run the study and record the run")
    run.add_argument("--config", required=True, metavar="FILE", help="the configuration file")
    run.add_argument("--dry-run", action="store_true", dest="dry_run",
                     help="run the study and its validation, print counts only, never connect")
    run.add_argument("--allow-placeholder", action="store_true", dest="allow_placeholder",
                     help="accept a placeholder mapping (only with --dry-run)")
    selftest = modes.add_parser(
        "selftest", allow_abbrev=False,
        help="start PSS/E from the configured folder and report the interpreter, version and launch functions")
    selftest.add_argument("--config", required=True, metavar="FILE", help="the configuration file")
    return parser


Deps = collections.namedtuple("Deps", ["out", "err", "psspy_loader", "clock", "connect", "fetch", "modes"])


# --------------------------------------------------------------------------- output and log


def _say(stream, text, secrets):
    """One line to `stream`, redacted against `secrets` (always an explicit list: never the environment)."""
    stream.write(redact(text, secrets, constants.ERROR_MAX_CHARS) + "\n")
    try:
        stream.flush()
    except Exception:  # noqa: BLE001 - a closed stream is not a reason to fail the run
        pass


class _RedactingFilter(logging.Filter):
    """Redacts every record of the handler against the configuration's own secrets."""

    def __init__(self, secrets):
        logging.Filter.__init__(self)
        self._secrets = list(secrets)

    def filter(self, record):
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a bad format string must not lose the record
            message = str(record.msg)
        if record.exc_info:
            message += " [%s]" % getattr(record.exc_info[0], "__name__", "exception")
            record.exc_info = None
            record.exc_text = None
        record.msg = redact(message, self._secrets, constants.ERROR_MAX_CHARS)
        record.args = ()
        return True


def _attach_log(cfg, secrets):
    """Rotating local log (1 MB, 5 backups, UTF-8) on the psse_job logger; returns what to undo."""
    folder = cfg["PSSE_LOG_DIR"]
    os.makedirs(folder, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        os.path.join(folder, _LOG_FILE_NAME), maxBytes=1024 * 1024, backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    handler.addFilter(_RedactingFilter(secrets))
    logger = logging.getLogger("psse_job")
    saved = (logger.level, logger.propagate)
    logger.setLevel(logging.INFO)
    logger.propagate = False  # nothing unredacted flows to a handler this module did not filter
    logger.addHandler(handler)
    return handler, saved


def _detach_log(handler, saved):
    logger = logging.getLogger("psse_job")
    logger.removeHandler(handler)
    handler.close()
    logger.setLevel(saved[0])
    logger.propagate = saved[1]


def add_search_dirs(cfg):
    """
    Append PSSE_SITE_DIR, PSSE_PSSPY_DIR and PSSE_BIN_DIR to sys.path (never first, D-10) and
    register PSSE_BIN_DIR as a DLL folder where os.add_dll_directory exists (Windows with Python
    3.8 or newer; absent on 3.7 and off Windows). Whether the DLL folder is needed or enough is
    UNVERIFIED until the laptop session.
    """
    for name in ("PSSE_SITE_DIR", "PSSE_PSSPY_DIR", "PSSE_BIN_DIR"):
        folder = cfg.get(name)
        if folder and folder not in sys.path:
            sys.path.append(folder)
    bin_dir = cfg.get("PSSE_BIN_DIR")
    if bin_dir and hasattr(os, "add_dll_directory") and os.path.isdir(bin_dir):
        try:
            DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(bin_dir))
        except OSError:
            log.warning("the PSS/E program folder could not be registered as a DLL folder")


# --------------------------------------------------------------------------- the run mode


def _scrub_paths(text):
    return _PATH_RE.sub("<path>", text)


def _preflight(cfg):
    """Open and close one TCP connection to the database host (D-05); raises OSError when it fails."""
    host, port = _db_address(cfg["SUPABASE_PSSE_DB_URL"])
    socket.create_connection((host, port), timeout=_PREFLIGHT_TIMEOUT_SECONDS).close()


def _prepare(deps, cfg, allow_placeholder):
    """
    study.PreparedRun for the configured case and mapping, started through the injected loader.
    A loader that raises (PsseUnavailable or anything else) does not stop the run: it becomes a
    study that fails at load_case with the exception class and a path-scrubbed text (D-06), the
    case file's label and sha256, and no mapping hash.
    """
    case_path = cfg["PSSE_CASE_PATH"]
    try:
        psspy = deps.psspy_loader(cfg)
    except Exception as exc:  # noqa: BLE001 - recorded as a failed run, never silent
        text = "%s: %s" % (type(exc).__name__, exc)
        text = _scrub_paths(redact(text, env_secrets(cfg), constants.ERROR_MAX_CHARS))
        text = text[:_LOAD_FAILURE_MAX_CHARS]
        log.warning("PSS/E could not be started: %s", text)
        return study.PreparedRun(
            study.failing_study("load_case", "PSS/E could not be started: " + text),
            run_record.case_label(case_path), run_record.file_sha256(case_path), None, None)
    return study.prepare_run(psspy, case_path, cfg["PSSE_MAPPING_PATH"], allow_placeholder)


def _run_mode(args, cfg, deps):
    secrets = env_secrets(cfg)
    if cfg["PSSE_PREFLIGHT"] != "0":
        failure = None
        try:
            _preflight(cfg)
        except Exception as exc:  # noqa: BLE001 - only the class is reported, never the address
            failure = type(exc).__name__
        if failure is not None:
            log.warning("database host did not answer the preflight (%s)", failure)
            _say(deps.err, "database host did not answer (%s); no run was started" % failure, secrets)
            return EXIT_NOT_RECORDED
    prepared = _prepare(deps, cfg, False)
    if prepared.mapping_error:
        log.warning("the mapping could not be used: %s", redact(prepared.mapping_error, secrets))
    outcome = job.run_once(
        deps.fetch, prepared.study, deps.connect, prepared.case_id, prepared.case_sha256,
        prepared.mapping_sha256, deps.clock, env=cfg)
    _say(deps.out, "run_id=%s outcome=%s status=%s exit=%d" % (
        outcome.run_id, outcome.outcome, outcome.status, outcome.exit_code), secrets)
    return outcome.exit_code


def _dry_fetch(deps, cfg):
    """The ratings read of a dry run: a missing SUPABASE_URL or key is a failed read, so no credential is needed."""
    if not cfg.get(constants.ENV_SUPABASE_URL) or not cfg.get(constants.ENV_PUBLISHABLE_KEY):
        def unconfigured():
            raise ratings.ReadFailed("the ratings read is not configured")
        return unconfigured
    return deps.fetch


def _dry_failure_report(deps, secrets, failure):
    text = _scrub_paths(redact(failure.message, secrets, constants.ERROR_MAX_CHARS))
    _say(deps.out, "dry run: nothing was written to the database", secrets)
    _say(deps.out, "study failed at stage %s: %s" % (failure.stage, text), secrets)
    return EXIT_FAILED_RECORDED


def _dry_run_mode(args, cfg, deps):
    """
    D-07: the real study, Phase 1's validation and the row building, in the order job.run_once
    follows up to the connect; never a connect, never a preflight. Prints counts only.
    """
    secrets = env_secrets(cfg)
    prepared = _prepare(deps, cfg, bool(getattr(args, "allow_placeholder", False)))
    if prepared.mapping_error:
        log.warning("the mapping could not be used: %s", redact(prepared.mapping_error, secrets))
    clock = deps.clock or (lambda: datetime.datetime.now(datetime.timezone.utc))
    started_at = clock()
    context = contract.RunContext(
        run_record.new_run_id(started_at), started_at, run_record.case_label(cfg["PSSE_CASE_PATH"]),
        prepared.case_sha256, prepared.mapping_sha256, run_record.job_version(cfg))
    selection = ratings.select_ratings(_dry_fetch(deps, cfg), started_at)
    try:
        results = prepared.study(selection, context)
    except Exception as exc:  # noqa: BLE001 - every study failure is reported, never raised
        return _dry_failure_report(deps, secrets, run_record.failure_from_exception("internal", exc))
    finished_at = clock()
    if finished_at.tzinfo is None or finished_at < started_at:
        finished_at = started_at
    try:
        run_record.validate_results(results, selection)
        record = run_record.build_run_record(context, selection, finished_at, results=results)
        rows = run_record.result_rows(record, results)
    except Exception as exc:  # noqa: BLE001 - an invalid set would never be written
        return _dry_failure_report(
            deps, secrets, run_record.failure_from_exception("validate_results", exc))
    from_rows = sum(1 for choice in selection.choices.values() if choice.source == constants.SOURCE_CITY_RATING)
    for line in (
        "dry run: nothing was written to the database",
        "rows: psse_run=1 %s" % " ".join(
            "%s=%d" % (table.split(".")[-1], len(rows[table]))
            for table in (contract.DISPATCH_TABLE, contract.MARGIN_TABLE, contract.CONTINGENCY_TABLE)),
        "contingencies: screened=%s with_results=%s" % (
            record["n_contingencies"], record["n_contingencies_with_results"]),
        "ratings: city_rating=%d static=%d" % (from_rows, len(selection.choices) - from_rows),
        "outcome: %s" % record["outcome"],
        "rate_set: %s" % record["rate_set"],
        "psse_version: %s" % record["psse_version"],
        "study_seconds: %.1f" % (finished_at - started_at).total_seconds(),
        "validation: ok",
    ):
        _say(deps.out, line, secrets)
    return EXIT_OK


# --------------------------------------------------------------------------- starting PSS/E (plan 03-04)

LaunchRow = collections.namedtuple("LaunchRow", ["name", "parameters", "confidence"])

# The functions the entry script's loader calls to start PSS/E and to move its console output into
# a file. They are outside psse_api.SURFACE (Phase 2 is frozen), so the launcher checks them here.
# Every row is UNVERIFIED until runbook step 2: the names and the (2, file, [0, 0]) form come from
# forum answers and a vendor blog (research assumptions A2 and A3), not from a PSS/E manual.
LAUNCH_SURFACE = (
    LaunchRow("psseinit", ("buses",), "UNVERIFIED"),
    LaunchRow("report_output", ("islct", "filarg", "options"), "UNVERIFIED"),
    LaunchRow("progress_output", ("islct", "filarg", "options"), "UNVERIFIED"),
    LaunchRow("alert_output", ("islct", "filarg", "options"), "UNVERIFIED"),
    LaunchRow("prompt_output", ("islct", "filarg", "options"), "UNVERIFIED"),
)
_OUTPUT_FUNCTIONS = ("report_output", "progress_output", "alert_output", "prompt_output")
_OUTPUT_TO_FILE = 2  # UNVERIFIED (runbook step 2): the "write to a file" selector of the output calls
_OUTPUT_OPTIONS = (0, 0)

# One short, path-free sentence per output function from the latest start_psspy call, so that
# selftest can print them although a loader returns only the module. Replaced on every call.
LAST_START_NOTES = []


def check_launch_signatures(psspy_module):
    """
    One probe.ProbeRow `launch:NAME` per LAUNCH_SURFACE row, with the rules of probe.check_signatures
    (probe.py is frozen, so the thirty lines are repeated here on purpose): a missing function is a
    FAIL, a signature that cannot be read is a SKIP, a missing parameter name is a FAIL, and a
    signature that takes any keyword with missing names is a SKIP.
    """
    rows = []
    for surface in LAUNCH_SURFACE:
        check = "launch:" + surface.name
        try:
            function = getattr(psspy_module, surface.name, None)
        except Exception:  # noqa: BLE001 - a module whose attribute access raises has no such function
            function = None
        if function is None or not callable(function):
            rows.append(probe.ProbeRow(check, probe.FAIL, "missing"))
            continue
        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError):
            rows.append(probe.ProbeRow(
                check, probe.SKIP, "signature not inspectable; the start itself exercised the call"))
            continue
        except Exception as exc:  # noqa: BLE001
            rows.append(probe.ProbeRow(
                check, probe.FAIL, "signature could not be read: %s" % type(exc).__name__))
            continue
        names = set(signature.parameters)
        missing = [name for name in surface.parameters if name not in names]
        takes_any_keyword = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())
        if missing and takes_any_keyword:
            rows.append(probe.ProbeRow(
                check, probe.SKIP, "accepts any keyword, so the names %s cannot be confirmed" % ", ".join(missing)))
        elif missing:
            rows.append(probe.ProbeRow(check, probe.FAIL, "missing parameter %s" % ", ".join(missing)))
        else:
            rows.append(probe.ProbeRow(
                check, probe.PASS, "all %d parameter name%s present" % (
                    len(surface.parameters), "" if len(surface.parameters) == 1 else "s")))
    return rows


def start_psspy(psspy_module, max_buses, log_path):
    """
    Start PSS/E in `psspy_module` and move its console output into the file `log_path`; returns the
    notes (one sentence per output function: redirected, missing, or failed with the exception
    class) and replaces LAST_START_NOTES. `psseinit(max_buses)` failing, or not existing, raises
    PsseUnavailable naming the exception class only (never its text, which may hold a path or a
    licence server). A missing or failing output function is a note, never fatal: a console banner
    is a nuisance, not a failed run. Whether real psspy takes these calls with these names is
    UNVERIFIED until runbook step 2.
    """
    global LAST_START_NOTES
    LAST_START_NOTES = []
    init = getattr(psspy_module, "psseinit", None)
    if init is None or not callable(init):
        raise PsseUnavailable("psspy has no psseinit function")
    try:
        init(max_buses)
    except Exception as exc:  # noqa: BLE001 - reported as the class only
        raise PsseUnavailable("psseinit failed (%s)" % type(exc).__name__)
    notes = []
    for name in _OUTPUT_FUNCTIONS:
        function = getattr(psspy_module, name, None)
        if function is None or not callable(function):
            notes.append("%s: missing, output not redirected" % name)
            continue
        try:
            function(_OUTPUT_TO_FILE, log_path, list(_OUTPUT_OPTIONS))
        except Exception as exc:  # noqa: BLE001 - reported as the class only
            notes.append("%s: failed (%s), output not redirected" % (name, type(exc).__name__))
            continue
        notes.append("%s: redirected to the log folder" % name)
    LAST_START_NOTES = notes
    return notes


def _bits():
    return 64 if sys.maxsize > 2 ** 32 else 32


def _start_report(deps, cfg, secrets):
    """
    The module from the loader, or None after printing "PSS/E could not be started: Class: text"
    with absolute paths scrubbed (the text of a loader error may hold a path or a licence server).
    """
    try:
        return deps.psspy_loader(cfg)
    except Exception as exc:  # noqa: BLE001 - reported, never a traceback
        text = "%s: %s" % (type(exc).__name__, exc)
        text = _scrub_paths(redact(text, secrets, constants.ERROR_MAX_CHARS))[:_LOAD_FAILURE_MAX_CHARS]
        log.warning("PSS/E could not be started: %s", text)
        _say(deps.out, "PSS/E could not be started: %s" % text, secrets)
        return None


def _selftest_mode(args, cfg, deps):
    """
    D-04: Python line, PSS/E started, the start notes, then exactly six rows (version and the five
    launch rows) and a count line over them. The first three are printed lines, never rows and never
    counted. Exit 0 when no row is a FAIL and PSS/E started, else 6.
    """
    global LAST_START_NOTES
    secrets = env_secrets(cfg)
    _say(deps.out, "Python %s, %d-bit" % (sys.version.split()[0], _bits()), secrets)
    LAST_START_NOTES = []
    module = _start_report(deps, cfg, secrets)
    if module is None:
        return EXIT_CHECK_FAILED
    _say(deps.out, "PSS/E started", secrets)
    for note in list(LAST_START_NOTES):
        _say(deps.out, note, secrets)
    try:
        text = psse_api.PsseApi(module).version()
        if text == "unknown":
            version = probe.ProbeRow("version", probe.FAIL, "the version could not be read from psseversion")
        else:
            version = probe.ProbeRow("version", probe.PASS, "PSS/E %s" % text)
    except Exception as exc:  # noqa: BLE001 - a FAIL row, never an exception
        version = probe.ProbeRow(
            "version", probe.FAIL, "the PSS/E adapter could not be built (%s)" % type(exc).__name__)
    rows = [version] + check_launch_signatures(module)
    for line in probe.format_report(rows).splitlines():
        _say(deps.out, line, secrets)
    return EXIT_OK if probe.probe_ok(rows) else EXIT_CHECK_FAILED


RUNNERS = {"run": _run_mode, "dry-run": _dry_run_mode, "selftest": _selftest_mode}
# Modes that start PSS/E hold the run lock (D-04): plan 03-04 adds selftest, probe and hold-lock.
LOCK_MODES = frozenset(["run", "dry-run", "selftest"])


def _mode_of(args):
    if args.mode == "run" and getattr(args, "dry_run", False):
        return "dry-run"
    return args.mode


def _main(argv, psspy_loader, out, err, clock, connect, fetch):
    parser = build_parser()
    try:
        with contextlib.redirect_stdout(out):
            args = parser.parse_args(list(argv))
    except _UsageExit as stop:
        return EXIT_OK if stop.status == 0 else EXIT_USAGE
    except _UsageError as problem:
        _say(err, "usage error: %s" % problem.message, [])
        return EXIT_USAGE
    mode = _mode_of(args)
    if getattr(args, "allow_placeholder", False) and mode != "dry-run":
        _say(err, "usage error: --allow-placeholder is accepted only together with --dry-run", [])
        return EXIT_USAGE

    try:
        cfg = read_config(args.config, mode)
    except ConfigError as problem:
        for text in problem.problems:
            _say(err, "configuration error: %s" % text, [])
        return EXIT_USAGE
    runner = RUNNERS.get(mode)
    if runner is None:
        _say(err, "mode %s is not available" % mode, [])
        return EXIT_USAGE

    secrets = env_secrets(cfg)
    deps = Deps(
        out, err, psspy_loader, clock,
        connect or (lambda: writer.connect(env=cfg)),
        fetch or (lambda: ratings.fetch_latest_rating(cfg)),
        None)
    handler, saved = _attach_log(cfg, secrets)
    try:
        try:
            add_search_dirs(cfg)
            if mode in LOCK_MODES:
                with RunLock(cfg["PSSE_LOCK_PATH"]) as held:
                    if not held.acquired:
                        log.warning("another instance holds the run lock; this run is skipped")
                        _say(err, "another instance holds the run lock; this run is skipped", secrets)
                        return EXIT_LOCKED
                    return runner(args, cfg, deps)
            return runner(args, cfg, deps)
        except Exception as exc:  # noqa: BLE001 - every unexpected error is exit 7, never silent
            name = type(exc).__name__
            log.error("unexpected launcher error: %s: %s", name, redact(str(exc), secrets))
            _say(err, "unexpected launcher error (%s); see the log" % name, secrets)
            return EXIT_UNEXPECTED
    finally:
        _detach_log(handler, saved)


def main(argv, psspy_loader, out=None, err=None, clock=None, connect=None, fetch=None):
    """
    Run the launcher and return the exit code (D-03). Never raises except KeyboardInterrupt.
    `psspy_loader(cfg)` returns the psspy module (or a fake) or raises; `connect` and `fetch` are
    test seams (defaults: writer.connect(env=cfg) and ratings.fetch_latest_rating(cfg)).
    """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    try:
        return _main(argv, psspy_loader, out, err, clock, connect, fetch)
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001 - nothing may escape to Task Scheduler as a traceback
        try:
            _say(err, "unexpected launcher error (%s)" % type(exc).__name__, [])
        except Exception:  # noqa: BLE001
            pass
        return EXIT_UNEXPECTED
