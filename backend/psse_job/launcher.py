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
import logging
import logging.handlers
import os
import re
import socket
import sys

from psse_job import constants, job, ratings, run_record, study, writer
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


def read_config(path, mode=None):
    """
    The resolved configuration of the file at `path`: a dict of text to text holding the known
    keys that have a value, plus the defaults of D-01. Raises ConfigError (every problem at once,
    naming keys and line numbers only) for an unreadable file, a malformed line, an unknown or
    repeated key and, when `mode` is given, a key that mode requires and the file lacks.
    """
    values, problems = _parse_lines(_read_text(path))
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


def _prepare(deps, cfg, allow_placeholder):
    """study.PreparedRun for the configured case and mapping, started through the injected loader."""
    psspy = deps.psspy_loader(cfg)
    return study.prepare_run(psspy, cfg["PSSE_CASE_PATH"], cfg["PSSE_MAPPING_PATH"], allow_placeholder)


def _run_mode(args, cfg, deps):
    secrets = env_secrets(cfg)
    prepared = _prepare(deps, cfg, False)
    if prepared.mapping_error:
        log.warning("the mapping could not be used: %s", redact(prepared.mapping_error, secrets))
    outcome = job.run_once(
        deps.fetch, prepared.study, deps.connect, prepared.case_id, prepared.case_sha256,
        prepared.mapping_sha256, deps.clock, env=cfg)
    _say(deps.out, "run_id=%s outcome=%s status=%s exit=%d" % (
        outcome.run_id, outcome.outcome, outcome.status, outcome.exit_code), secrets)
    return outcome.exit_code


RUNNERS = {"run": _run_mode}
# Modes that start PSS/E hold the run lock (D-04); plan 03-04 adds selftest and probe.
LOCK_MODES = frozenset(["run", "dry-run"])


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
