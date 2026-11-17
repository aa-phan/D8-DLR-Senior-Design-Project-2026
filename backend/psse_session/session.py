"""
The laptop session of the pandapower reference work (pandapower-solver Phase 1, plan 01-02: PSE-01).

One command (backend/psse_pandapower_session.py) loads PSS/E the way the job does, checks the
mapping against the case, exports the network as RAW text written by PSS/E's own export call,
collects every output in one work folder, writes one verified zip (psse_session.bundle), deletes
the mapping copy and its own folder and prints a masked summary. Sections run in the fixed order
of SECTIONS, each inside its own isolation: a section that raises is recorded in the manifest
with the exception class name only and the other sections still produce their members. This plan
builds the spine and the network section; the reference, settings and scaling sections arrive as
modules (psse_session.reference, settings_probe, scaling_probe) in plans 01-03 and 01-04 and are
imported by the section table below without an edit here.

What it never does: write the case file, open a network connection, touch a database, write
anywhere but its own work folder and the final zip, or print a bus number, a branch key, a mapping
target, a network value, a path, a user name or a machine name. psspy is reached only through
GatedPsspy, which refuses a function outside psse_api.SURFACE_NAMES | SESSION_SURFACE_NAMES, a
`save` or RAW export outside the work folder and a `case` of any file but the configured one or
one inside the work folder.

Honest scope: everything here is proven only against a fake psspy (backend/tests/psse_session_fake.py)
and is UNVERIFIED for real PSS/E 36.4 until the session of plan 01-10. In particular every
SESSION_SURFACE call is UNVERIFIED (forum evidence and analogy only, confidence LOW or MEDIUM),
every RAW export form in RAW_EXPORT_FORMS is UNVERIFIED (which call works, which argument layout it
takes and which revision it writes), that PSS/E writes the revision it was asked for is UNVERIFIED,
and that Windows lets the work folder be deleted while PSS/E holds its console log open is
UNVERIFIED (removal is best effort and the summary then says the wrapper deletes the folder).

Standard library plus psse_job only, Python 3.7 syntax (D-05).
"""

import argparse
import collections
import datetime
import inspect
import os
import re
import sys

from psse_job import launcher, mapping as mapping_module, psse_api, ratings, redaction, run_record, study
from psse_job import constants
from psse_session import bundle

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_USAGE = 2
EXIT_PSSE = 6
EXIT_UNEXPECTED = 7
EXIT_INTERRUPTED = 130

SESSION_MAX_SECONDS = 6 * 3600.0
MAX_LOG_BYTES = 8 * 1024 * 1024
RAW_REVISIONS = (33, 34, 35, 36)

SessionCall = collections.namedtuple(
    "SessionCall", ["name", "parameters", "returns", "evidence", "confidence"])

_AMACH_PARAMETERS = ("sid", "flag", "string")
# One row per psspy function this session calls beyond psse_api.SURFACE, in the style of that
# table. Evidence: psspy.org (the community forum) question numbers and analogy with abusint.
SESSION_SURFACE = (
    SessionCall("rawd_2", ("sid", "all", "status", "out", "ofile"), "ierr",
                "psspy.org questions 3777 and 10100: rawd_2(0, 1, [1,1,1,0,0,0,0], 0, file); a "
                "reply reports the bus-name option misbehaves in revisions 35 and 36", "LOW"),
    SessionCall("writerawversion", ("vernum", "out", "ofile"), "ierr",
                "psspy.org question 11652 and a search summary of 12001 and 10593; argument "
                "meanings not documented, layout assumed", "LOW"),
    SessionCall("prmint", ("name",), "(ierr, value)",
                "psspy.org question 11652; by analogy with abusint", "MEDIUM"),
    SessionCall("prmdat", ("name",), "(ierr, value)",
                "psspy.org question 11652; by analogy with abusint", "MEDIUM"),
    SessionCall("amachint", _AMACH_PARAMETERS, "(ierr, [columns])",
                "by analogy with abusint (psse_api.SURFACE); psspy.org question 10100", "MEDIUM"),
    SessionCall("amachreal", _AMACH_PARAMETERS, "(ierr, [columns])",
                "by analogy with abusreal (psse_api.SURFACE); psspy.org question 10100", "MEDIUM"),
    SessionCall("amachchar", _AMACH_PARAMETERS, "(ierr, [columns])",
                "by analogy with abusint (psse_api.SURFACE); psspy.org question 10100", "MEDIUM"),
)
SESSION_SURFACE_NAMES = frozenset(row.name for row in SESSION_SURFACE)
ALLOWED_NAMES = psse_api.SURFACE_NAMES | SESSION_SURFACE_NAMES

_PARAMETERS = dict((row.name, row.parameters) for row in psse_api.SURFACE)
_PARAMETERS.update((row.name, row.parameters) for row in SESSION_SURFACE)
# The functions that take a file, and the parameter that names it.
_FILE_ARGUMENTS = {"save": "sfile", "rawd_2": "ofile", "writerawversion": "ofile", "case": "sfile"}


class SessionRefused(RuntimeError):
    """A call the session may not make. The message names the function, never an argument."""


def _normalise(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


class GatedPsspy(object):
    """The only way the session reaches psspy: an allow-list of names and a path rule for files."""

    def __init__(self, module, work_dir, case_path):
        self._module = module
        self._work = _normalise(work_dir)
        self._case = _normalise(case_path)
        self.calls = []

    def _inside_work(self, path):
        return path.startswith(self._work + os.sep)

    def _check_file(self, name, args, kwargs):
        parameter = _FILE_ARGUMENTS[name]
        index = _PARAMETERS[name].index(parameter)
        if len(args) > index:
            value = args[index]
        elif parameter in kwargs:
            value = kwargs[parameter]
        else:
            raise SessionRefused("psspy.%s was called without its file argument" % name)
        if not isinstance(value, str) or not value.strip():
            raise SessionRefused("psspy.%s was called with a file argument that is not a path" % name)
        path = _normalise(value)
        if name == "case":
            if path != self._case and not self._inside_work(path):
                raise SessionRefused("psspy.case refused: not the configured case or a work file")
        elif not self._inside_work(path):
            raise SessionRefused("psspy.%s refused: the path is outside the work folder" % name)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in ALLOWED_NAMES:
            raise SessionRefused("psspy.%s is not on the session allow-list" % name)
        function = getattr(self._module, name)

        def gated(*args, **kwargs):
            if name in _FILE_ARGUMENTS:
                self._check_file(name, args, kwargs)
            self.calls.append(name)
            return function(*args, **kwargs)

        return gated

    def _allowed_function(self, name):
        if name not in ALLOWED_NAMES:
            raise SessionRefused("psspy.%s is not on the session allow-list" % name)
        return getattr(self._module, name, None)

    def signature_text(self, name):
        """The signature of psspy.`name` as text, or "unavailable" (the session records it)."""
        function = self._allowed_function(name)
        if function is None:
            return "unavailable"
        try:
            return str(inspect.signature(function))
        except Exception:  # noqa: BLE001 - a builtin without a signature is not an error
            return "unavailable"

    def doc_text(self, name, limit=4000):
        """The docstring of psspy.`name` cut to `limit` characters, or an empty string."""
        function = self._allowed_function(name)
        doc = getattr(function, "__doc__", None) if function is not None else None
        return doc[:limit] if isinstance(doc, str) else ""


# -- sections ------------------------------------------------------------------------------------

SECTIONS = bundle.SECTION_WORDS
SectionResult = collections.namedtuple("SectionResult", ["status", "detail", "counts"])


class SessionContext(object):
    """What every section receives; see the plan's interface list."""

    def __init__(self, gated, api, cfg, case_path, mapping, case_sha256, work, now, budget, only):
        self.gated = gated
        self.api = api
        self.cfg = cfg
        self.case_path = case_path
        self.mapping = mapping
        self.case_sha256 = case_sha256
        self.work = work
        self.now = now
        self.budget = budget
        self.only = only
        self.index = None
        self.index_stage = None
        self.selection = None
        self.raw_writer = None
        self.results = {}
        self.statuses = {}


# -- the RAW export ------------------------------------------------------------------------------

_FORUM_STATUS = (1, 1, 1, 0, 0, 0, 0)
# (form_id, function name, positional arguments builder, keyword arguments builder); exactly one
# builder is not None. The forum option list is used, never a bus-name option. UNVERIFIED.
RAW_EXPORT_FORMS = (
    ("writerawversion_33_positional", "writerawversion",
     lambda path: (33, 0, path), None),
    ("writerawversion_33_keywords", "writerawversion",
     None, lambda path: dict(vernum=33, out=0, ofile=path)),
    ("rawd_2_forum_positional", "rawd_2",
     lambda path: (0, 1, list(_FORUM_STATUS), 0, path), None),
    ("rawd_2_forum_keywords", "rawd_2",
     None, lambda path: dict(sid=0, all=1, status=list(_FORUM_STATUS), out=0, ofile=path)),
)

_BEGIN_RE = re.compile(r"\b" + "BEG" + "IN" + r"\s+([A-Z0-9][A-Z0-9 \-]*?)\s+DATA\b")
_TERMINATOR_RE = re.compile(r"^\s*0\s*/")
_V33_ORDER = (
    "BUS", "LOAD", "FIXED SHUNT", "GENERATOR", "BRANCH", "TRANSFORMER", "AREA",
    "TWO-TERMINAL DC", "VSC DC LINE", "IMPEDANCE CORRECTION", "MULTI-TERMINAL DC",
    "MULTI-SECTION LINE", "ZONE", "INTER-AREA TRANSFER", "OWNER", "FACTS DEVICE",
    "SWITCHED SHUNT", "GNE", "INDUCTION MACHINE",
)
_RECORD_SECTIONS = (
    ("BUS", "buses"), ("LOAD", "loads"), ("FIXED SHUNT", "fixed_shunts"),
    ("GENERATOR", "machines"), ("BRANCH", "lines"), ("AREA", "areas"),
    ("SWITCHED SHUNT", "switched_shunts"),
)
_TRANSFORMER_COD1_INDEX = 6


def _field(text):
    return text.split("/")[0].strip()


def _header_revision(head):
    """The revision (third field of the first line) of RAW bytes or text, or None."""
    text = head.decode("latin-1") if isinstance(head, (bytes, bytearray)) else head
    first = text.split("\n", 1)[0]
    fields = first.split("/")[0].split(",")
    if len(fields) < 3:
        return None
    try:
        return int(fields[2].strip())
    except ValueError:
        return None


def _transformer_counts(lines):
    """(transformers, three_winding, controlling) of a transformer section's lines, or None."""
    index = total = three = controlling = 0
    while index < len(lines):
        first = lines[index].split(",")
        if len(first) < 3:
            return None
        try:
            winding_count_flag = int(_field(first[2]).strip("'"))
        except ValueError:
            return None
        size = 5 if winding_count_flag != 0 else 4
        if index + size > len(lines):
            return None
        third = lines[index + 2].split(",")
        try:
            code = int(_field(third[_TRANSFORMER_COD1_INDEX]))
        except (ValueError, IndexError):
            return None
        total += 1
        three += 1 if size == 5 else 0
        controlling += 1 if code != 0 else 0
        index += size
    return total, three, controlling


def count_raw(data):
    """Record counts of a RAW file's bytes (or text) as a dict, None for any count not established.

    Keys: buses, loads, fixed_shunts, machines, lines, transformers, three_winding,
    switched_shunts, areas, controlling_transformers. Sections are located by their terminator
    lines (a zero then a slash) and named by the begin phrase when present, otherwise by the
    revision 33 order. A section that was never terminated is not counted.
    """
    counts = dict((name, None) for name in bundle.NETWORK_COUNT_NAMES)
    try:
        text = data.decode("latin-1") if isinstance(data, (bytes, bytearray)) else str(data)
    except Exception:  # noqa: BLE001
        return counts
    lines = text.splitlines()
    if len(lines) < 3:
        return counts
    revision = _header_revision(lines[0])
    sections = []
    name = None
    current = []
    for line in lines[3:]:
        if _TERMINATOR_RE.match(line):
            sections.append((name, current))
            current = []
            begin = _BEGIN_RE.search(line)
            name = begin.group(1).strip() if begin else None
            continue
        stripped = line.strip()
        if stripped == "Q":
            break
        if stripped:
            current.append(line)
    named = {}
    for position, (section_name, section_lines) in enumerate(sections):
        if section_name is None and revision == 33 and position < len(_V33_ORDER):
            section_name = _V33_ORDER[position]
        if section_name is not None and section_name not in named:
            named[section_name] = section_lines

    def find(key):
        for section_name in named:
            if section_name == key or section_name.startswith(key + " "):
                return named[section_name]
        return None

    for key, count_name in _RECORD_SECTIONS:
        found = find(key)
        if found is not None:
            counts[count_name] = len(found)
    transformer_lines = find("TRANSFORMER")
    if transformer_lines is not None:
        result = _transformer_counts(transformer_lines)
        if result is not None:
            counts["transformers"], counts["three_winding"], counts["controlling_transformers"] = result
    return counts


def _attempt(ctx, form, member_name):
    """One export attempt into `member_name`; the record holds ierr or class, bytes and revision."""
    form_id, function_name, positional, keywords = form
    path = ctx.work.member_path(member_name)
    record = {"form_id": form_id, "function": function_name, "member": member_name,
              "status": "failed", "ierr": None, "error_class": None, "bytes": 0, "revision": None}
    try:
        function = getattr(ctx.gated, function_name)
        if positional is not None:
            result = function(*positional(path))
        else:
            result = function(**keywords(path))
        if isinstance(result, int) and not isinstance(result, bool):
            record["ierr"] = result
        else:
            record["error_class"] = "UnexpectedReturn"
    except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
        record["error_class"] = bundle.class_word(exc)
    try:
        if os.path.isfile(path):
            ctx.work.register(member_name, "network")
            record["bytes"] = os.path.getsize(path)
            with open(path, "rb") as handle:
                record["revision"] = _header_revision(handle.read(512))
    except OSError:
        record["error_class"] = record["error_class"] or "OSError"
        record["bytes"] = 0
    if record["ierr"] == 0 and record["bytes"] > 0 and record["revision"] in RAW_REVISIONS:
        record["status"] = "ok"
    return record


def export_raw(ctx, member_name):
    """Write the in-memory case as RAW into `member_name` with the selected form; returns the record."""
    if ctx.raw_writer is None:
        raise SessionRefused("no RAW export form was established")
    return ctx.raw_writer(member_name)


def _network_section(ctx):
    for name in ("rawd_2", "writerawversion"):
        text = "signature: %s\n\n%s\n" % (ctx.gated.signature_text(name), ctx.gated.doc_text(name))
        ctx.work.add_bytes("network/docs/%s.txt" % name, text.encode("utf-8", "replace"), "network")
    if ctx.index is None:
        ctx.results["network"] = {"revision": None, "counts": {}, "form_id": None}
        return SectionResult("failed", ("no case index", ctx.index_stage or "internal"), {})
    ctx.api.load_case(ctx.case_path)
    attempts = []
    first_ok = selected = None
    for number, form in enumerate(RAW_EXPORT_FORMS, 1):
        record = _attempt(ctx, form, "network/attempt_%d_%s.raw" % (number, form[0]))
        attempts.append(record)
        if record["status"] == "ok":
            first_ok = first_ok or record
            if record["revision"] == 33:
                selected = record
                break
    chosen = selected or first_ok
    counts = {"attempts": len(attempts), "revision": None}
    ctx.work.add_json(
        "network/export_attempts.json",
        {"attempts": attempts, "selected": chosen["form_id"] if chosen else None}, "network")
    if chosen is None:
        ctx.results["network"] = {"revision": None, "counts": {}, "form_id": None}
        return SectionResult("failed", ("no raw export",), counts)
    with open(ctx.work.member_path(chosen["member"]), "rb") as handle:
        data = handle.read()
    ctx.work.add_bytes("network/network.raw", data, "network")
    form = [item for item in RAW_EXPORT_FORMS if item[0] == chosen["form_id"]][0]
    ctx.raw_writer = lambda member_name: _attempt(ctx, form, member_name)
    raw_counts = count_raw(data)
    counts.update(raw_counts)
    counts["revision"] = chosen["revision"]
    detail = []
    try:
        lines, transformers = ctx.api.branch_table()
        expected = {"buses": len(ctx.api.bus_table()), "lines": len(lines),
                    "transformers": len(transformers)}
        if any(raw_counts[key] is not None and raw_counts[key] != value
               for key, value in expected.items()):
            detail.append("count mismatch")
    except Exception:  # noqa: BLE001 - the cross-check is informative, never fatal
        detail.append("unavailable")
    ctx.results["network"] = {
        "revision": chosen["revision"], "counts": raw_counts, "form_id": chosen["form_id"]}
    return SectionResult("ok", tuple(detail), counts)


def _reference_section(ctx):
    from psse_session import reference
    return reference.run(ctx)


def _settings_section(ctx):
    from psse_session import settings_probe
    return settings_probe.run(ctx)


def _scaling_section(ctx):
    from psse_session import scaling_probe
    return scaling_probe.run(ctx)


SECTION_FUNCTIONS = {
    "network": _network_section,
    "reference": _reference_section,
    "settings": _settings_section,
    "scaling": _scaling_section,
}


def _run_section(name, ctx):
    """One section in its own isolation: a SectionResult, never an exception (but an interrupt)."""
    try:
        result = SECTION_FUNCTIONS[name](ctx)
        if not isinstance(result, SectionResult):
            return SectionResult("failed", ("TypeError",), {})
        return result
    except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
        return SectionResult("failed", (bundle.class_word(exc),), {})


# -- the command line ----------------------------------------------------------------------------


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
    parser = _Parser(
        prog="psse_pandapower_session.py",
        description="The laptop session: read PSS/E, write one zip, print a masked summary.")
    modes = parser.add_subparsers(dest="mode")
    modes.required = True
    for name, text in (("run", "run the session and write the zip"),
                       ("check", "load PSS/E, check the mapping and solve one base case; no zip")):
        sub = modes.add_parser(name, help=text)
        sub.add_argument("--config", required=True, help="the configuration file")
        sub.add_argument("--mapping", required=True, help="the private mapping copy")
        sub.add_argument("--out-dir", required=True, help="the folder for the zip")
        sub.add_argument("--allow-placeholder", action="store_true",
                         help="accept a mapping marked placeholder (plumbing runs only)")
        if name == "run":
            sub.add_argument("--only", default=None,
                             help="run only these sections (comma list); network always runs")
    return parser


_PATH_RE = re.compile(
    r"[A-Za-z]:[\\/](?:[^\\/'\"<>|:;,\r\n]*[\\/])*[^\\/'\"<>|\s]*"
    r"|\\\\[^\s'\"<>|]+"
    r"|/(?:[^/\s'\"<>|]+/)+[^/\s'\"<>|]*"
)


def _say(stream, text, environ, extra=()):
    """One line to `stream`, with identity values masked and secrets redacted."""
    text = _PATH_RE.sub("<path>", text)
    text = bundle.mask_identity(text, environ, extra)
    text = redaction.redact(text, redaction.env_secrets(environ), constants.ERROR_MAX_CHARS)
    stream.write(text.encode("ascii", "replace").decode("ascii") + "\n")
    try:
        stream.flush()
    except Exception:  # noqa: BLE001 - a closed stream is not a reason to fail the run
        pass


# -- the session ---------------------------------------------------------------------------------


class _StartFailed(Exception):
    def __init__(self, word):
        Exception.__init__(self, word)
        self.word = word


class _State(object):
    """What a run or check leaves for the report."""

    def __init__(self):
        self.psse_version = "unknown"
        self.sections = []
        self.checks = []
        self.notes = []
        self.members = 0
        self.zip_written = False
        self.start_failed = None
        self.all_ok = False


def _clean_counts(counts):
    clean = {}
    for name, value in dict(counts or {}).items():
        if name in bundle.COUNT_NAMES and (
                value is None or (isinstance(value, int) and not isinstance(value, bool))):
            clean[name] = value
    return clean


def _start(loader, cfg, work):
    started = dict(cfg)
    started["PSSE_LOG_DIR"] = work.path
    launcher.add_search_dirs(started)
    try:
        return loader(started)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - reported as the class only
        raise _StartFailed(bundle.class_word(exc))


def _index(gated, case_path, loaded):
    """(index, stage word): the case index, or None with the failing stage or class word."""
    try:
        return study.index_case(gated, case_path, loaded), None
    except study.StudyFailed as failure:
        return None, bundle.safe_item(failure.stage)
    except Exception as exc:  # noqa: BLE001
        return None, bundle.class_word(exc)


def _version_of(index, api):
    if index is not None:
        return index.psse_version
    return api.version() if api is not None else "unknown"


def _build_context(gated, cfg, loaded, case_sha256, work, now, only, state):
    case_path = cfg["PSSE_CASE_PATH"]
    try:
        api = psse_api.PsseApi(gated, protected_path=case_path)
    except Exception:  # noqa: BLE001
        api = None
    ctx = SessionContext(gated, api, cfg, case_path, loaded, case_sha256, work, now,
                         study.Budget(max_seconds=SESSION_MAX_SECONDS), only)
    ctx.index, ctx.index_stage = _index(gated, case_path, loaded)
    if ctx.api is None and ctx.index is not None:
        ctx.api = ctx.index.api
    ctx.selection = ratings.select_ratings(lambda: [], now)
    state.psse_version = _version_of(ctx.index, ctx.api)
    return ctx


def _copy_log(work, state):
    try:
        with open(os.path.join(work.path, "psse_output.log"), "rb") as handle:
            data = handle.read(MAX_LOG_BYTES)
        work.add_bytes("logs/psse_output.txt", data, "session")
    except OSError:
        state.notes.append("log unreadable")


def _manifest_meta(args, cfg, loaded, case_sha256, now, state):
    return {
        "created_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": args.mode,
        "python_version": "%d.%d.%d" % tuple(sys.version_info[:3]),
        "psse_version": state.psse_version,
        "case_sha256": case_sha256,
        "mapping_sha256": loaded.sha256,
        "mapping_placeholder": bool(loaded.placeholder),
    }


def _do_run(args, cfg, loaded, case_sha256, now, work, loader, only, state):
    module = _start(loader, cfg, work)
    gated = GatedPsspy(module, work.path, cfg["PSSE_CASE_PATH"])
    ctx = _build_context(gated, cfg, loaded, case_sha256, work, now, only, state)
    skipped_by_only = set()
    for name in SECTIONS:
        if name != "network" and only is not None and name not in only:
            skipped_by_only.add(name)
            ctx.statuses[name] = SectionResult("skipped", ("not run",), {})
            continue
        ctx.statuses[name] = _run_section(name, ctx)
    _copy_log(work, state)
    state.sections = [
        (name, ctx.statuses[name].status,
         tuple(bundle.safe_item(item) for item in ctx.statuses[name].detail),
         _clean_counts(ctx.statuses[name].counts))
        for name in SECTIONS]
    state.all_ok = all(status == "ok" for name, status, _d, _c in state.sections
                       if name not in skipped_by_only)
    state.members = len(work.members())
    try:
        work.write_manifest(
            _manifest_meta(args, cfg, loaded, case_sha256, now, state),
            [{"name": name, "status": status, "detail": list(detail), "counts": counts}
             for name, status, detail, counts in state.sections])
        work.zip_and_verify()
        state.zip_written = True
    except (bundle.BundleRefused, OSError):
        state.zip_written = False


def _do_check(args, cfg, loaded, now, work, loader, state):
    module = _start(loader, cfg, work)
    gated = GatedPsspy(module, work.path, cfg["PSSE_CASE_PATH"])
    case_path = cfg["PSSE_CASE_PATH"]
    index, stage = _index(gated, case_path, loaded)
    state.psse_version = _version_of(index, None)
    if index is None:
        state.checks = [("case index", "failed", (stage,)), ("base solve", "failed", ("not run",))]
        return
    state.checks.append(("case index", "ok", ()))
    temp_dir = os.path.join(work.path, "check_tmp")
    os.makedirs(temp_dir)
    try:
        study.prepare_city_base(
            index, loaded, ratings.select_ratings(lambda: [], now), constants.CITIES[0],
            study.Budget(max_seconds=SESSION_MAX_SECONDS), temp_dir)
        state.checks.append(("base solve", "ok", ()))
    except study.StudyFailed as failure:
        state.checks.append(("base solve", "failed", (bundle.safe_item(failure.stage),)))
    except Exception as exc:  # noqa: BLE001
        state.checks.append(("base solve", "failed", (bundle.class_word(exc),)))
    state.all_ok = all(status == "ok" for _name, status, _detail in state.checks)


def _delete_mapping(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        return "deleted"
    except OSError:
        return "not deleted"
    return "deleted"


def _parse(argv, out, err, environ):
    """(args, exit code): the parsed arguments, or None and the code to return."""
    parser = build_parser()
    saved = sys.stdout
    sys.stdout = out
    try:
        args = parser.parse_args(argv)
    except _UsageExit as stop:
        return None, EXIT_OK if stop.status == 0 else EXIT_USAGE
    except _UsageError as problem:
        _say(err, "usage: psse_pandapower_session.py {run,check} --config FILE --mapping FILE "
                  "--out-dir FOLDER", environ)
        _say(err, "usage error: %s" % problem.message, environ)
        return None, EXIT_USAGE
    finally:
        sys.stdout = saved
    return args, None


def _only_sections(args, err, environ):
    """(frozenset of names or None, ok): the validated --only list."""
    text = getattr(args, "only", None)
    if text is None:
        return None, True
    names = [item.strip() for item in text.split(",")]
    if any(item not in SECTIONS for item in names):
        _say(err, "usage error: --only names a section that does not exist", environ)
        return None, False
    return frozenset(names), True


def _read_inputs(args, err, environ):
    """(cfg, mapping) or (None, None) after printing the problem."""
    try:
        cfg = launcher.read_config(args.config)
    except launcher.ConfigError as problem:
        for text in problem.problems:
            _say(err, "configuration error: %s" % text, environ)
        return None, None
    missing = [key for key in ("PSSE_PSSPY_DIR", "PSSE_CASE_PATH") if not cfg.get(key)]
    for key in missing:
        _say(err, "configuration error: missing key %s" % key, environ)
    if missing:
        return None, None
    try:
        loaded = mapping_module.load_mapping(args.mapping, allow_placeholder=args.allow_placeholder)
    except mapping_module.MappingError as problem:
        _say(err, "mapping refused: %d problem(s); PSS/E was not started" % len(problem.problems),
             environ)
        return None, None
    return cfg, loaded


def _report(args, state, outcome, mapping_state, work_state):
    return bundle.SummaryReport(
        args.mode, outcome, "%d.%d.%d" % tuple(sys.version_info[:3]), state.psse_version,
        tuple(state.sections), tuple(state.checks), tuple(state.notes), state.members,
        "written" if state.zip_written else "not written", mapping_state, work_state)


def _main(argv, loader, out, err, clock, environ):
    args, code = _parse(argv, out, err, environ)
    if args is None:
        return code
    only, ok = _only_sections(args, err, environ)
    if not ok:
        return EXIT_USAGE
    cfg, loaded = _read_inputs(args, err, environ)
    if cfg is None:
        return EXIT_USAGE
    if not os.path.isdir(args.out_dir):
        _say(err, "usage error: the out folder does not exist", environ)
        return EXIT_USAGE
    now = clock() if clock is not None else datetime.datetime.now(datetime.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=datetime.timezone.utc)
    try:
        work = bundle.WorkFolder(args.out_dir, bundle.stamp(now))
    except bundle.BundleRefused:
        _say(err, "refused: a session with this stamp already exists in the out folder; "
                  "nothing was changed", environ)
        return EXIT_USAGE
    case_sha256 = run_record.file_sha256(cfg["PSSE_CASE_PATH"])
    state = _State()
    interrupted = False
    try:
        try:
            if args.mode == "check":
                _do_check(args, cfg, loaded, now, work, loader, state)
            else:
                _do_run(args, cfg, loaded, case_sha256, now, work, loader, only, state)
        except KeyboardInterrupt:
            interrupted = True
        except _StartFailed as failure:
            state.start_failed = failure.word
    finally:
        mapping_state = "kept" if args.mode == "check" else _delete_mapping(args.mapping)
        work_state = "deleted" if work.remove() == 0 else "left for the wrapper"
    if interrupted:
        state.zip_written = False
        outcome, code = "interrupted", EXIT_INTERRUPTED
    elif state.start_failed is not None:
        _say(err, "PSS/E could not be started (%s)" % state.start_failed, environ)
        outcome, code = "failed", EXIT_PSSE
    elif args.mode == "check":
        outcome, code = ("checked", EXIT_OK) if state.all_ok else ("failed", EXIT_PARTIAL)
    elif state.zip_written and state.all_ok:
        outcome, code = "complete", EXIT_OK
    elif state.zip_written:
        outcome, code = "partial", EXIT_PARTIAL
    else:
        outcome, code = "failed", EXIT_PARTIAL
    text = bundle.render_summary(
        _report(args, state, outcome, mapping_state, work_state), environ, (work.out_dir,))
    out.write(text + "\n")
    try:
        out.flush()
    except Exception:  # noqa: BLE001
        pass
    return code


def main(argv, psspy_loader, out=None, err=None, clock=None, environ=None):
    """Run the session and return the exit code. Never raises (an interrupt is exit 130).

    `psspy_loader(cfg)` returns the started psspy module (or a fake) or raises; `clock()` returns
    the current datetime (default: now in UTC); `environ` is the environment used for masking.
    """
    out = sys.stdout if out is None else out
    err = sys.stderr if err is None else err
    environ = os.environ if environ is None else environ
    try:
        return _main(list(argv), psspy_loader, out, err, clock, environ)
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except Exception as exc:  # noqa: BLE001 - nothing may escape as a traceback
        try:
            _say(err, "unexpected session error (%s)" % bundle.class_word(exc), environ)
        except Exception:  # noqa: BLE001
            pass
        return EXIT_UNEXPECTED

