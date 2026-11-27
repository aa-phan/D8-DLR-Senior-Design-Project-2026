"""
The owner's two commands (pandapower-solver Phase 1, plan 01-09: NET-02, NET-03, PSE-04).

    pandapower_net_check.py ingest --zip PATH [--sessions-dir DIR]
    pandapower_net_check.py check --session DIR --mapping PATH [--registry PATH] [--allow-placeholder]

`ingest` extracts the session zip from the private channel into the private sessions folder, after
`ingest.ingest_zip` has checked every entry (research Pitfall 9). `check` takes an extracted session
and runs the whole Mac side in order: session and mapping verification, RAW parse and network
build, the NET-02 parity report, the converted copy and the D-06 evidence, the solve settings
copied from the session, the three scaling details, each city's algorithm run and injected-snapshot
run against PSS/E's reference, and the NET-03 verdict.

Everything printed is counts, statuses, versions, city names and pass or fail words. One renderer
(`_Printer.say`) accepts only lines that match `CLI_LINE_PATTERNS`, so a bus number, a branch key,
a mapping target, a network value, a reference value or a deviation size cannot reach the terminal
by construction (T-01-34); a line outside the vocabulary is a programming error that stops the
command with the generic error line. Detailed differences, worst deviations, the converted copy
and the evidence go only into files under `<session>/check_<stamp>/`, each written through
`private.write_private_*` (inside data/private/, git-ignored, no symlink escape) and each carrying a
marker key that the leak guard flags (T-01-35).

Exit codes: 0 (ingest ok, or parity and NET-03 both pass), 1 (check ran and parity or NET-03 failed
or was incomplete, or the network was refused), 2 (usage, ingest refusal, mapping mismatch,
registry refusal, private-path refusal, unexpected error).

A city whose scaling cannot be done (a refusal or an undetermined detail), whose solve does not
converge or whose reference is missing is `incomplete`, never a pass. When the var-limit
classification is inconclusive both settings are solved and both must pass (labels
`algorithm:enforce_q_lims_off` and `algorithm:enforce_q_lims_on`); the injected-snapshot run is a
diagnostic and uses the first of them.
"""

import argparse
import copy
import datetime
import json
import math
import os
import re
import sys
import types

import pandapower

from psse_job import constants, mapping as mapping_module
from psse_session import bundle
from pandapower_job import (
    compare, convert, ingest, network, parity, private, raw, scaling, solve)

REPORT_MARKER = "pandapower_job_" + "report"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_SETTINGS_MEMBER = "settings/settings.json"
_EXPERIMENTS_MEMBER = "scaling/experiments.json"
_NETWORK_MEMBER = "network/network.raw"
_CHECK_PREFIX = "check_"
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_REGISTRY_BYTES = 1024 * 1024

_DETAIL_NAMES = ("swing_in_total", "clamped_at_limits", "q_scales_with_p")
_VERDICT_WORDS = ("pass", "fail", "incomplete")


# -- the vocabulary of the printed lines ---------------------------------------------------------


def _alt(words):
    return "(?:%s)" % "|".join(re.escape(word) for word in sorted(set(words), key=len, reverse=True))


_NUM = "[0-9]{1,9}"
_WORD = "[a-z_]{1,40}"
_CITY = _alt(constants.CITIES)
_NETWORK_REASONS = _alt(tuple(raw.REFUSAL_REASONS) + tuple(network.BUILD_REFUSAL_REASONS))

CLI_LINE_PATTERNS = tuple(re.compile(pattern + r"\Z") for pattern in (
    "ingest: ok",
    "ingest: refused \\(%s\\)" % _alt(ingest.INGEST_REFUSAL_REASONS),
    "members verified: %s" % _NUM,
    "section %s: %s" % (_alt(bundle.SECTION_WORDS), _alt(bundle.STATUS_WORDS)),
    "private path: refused \\(%s\\)" % _alt(private.REFUSAL_REASONS),
    "session: verified",
    "session: refused \\(%s\\)" % _alt(ingest.INGEST_REFUSAL_REASONS),
    "mapping: verified",
    "mapping: refused \\(%s\\)" % _alt(("mapping_mismatch", "mapping_invalid")),
    "registry: none",
    "registry: %s entries" % _NUM,
    "registry: refused \\(%s\\)" % _WORD,
    "network: built",
    "network: refused \\(%s\\)" % _NETWORK_REASONS,
    "parity: %s" % _alt(("pass", "fail")),
    "parity category %s: compared %s differing %s" % (_alt(parity.PARITY_CATEGORIES), _NUM, _NUM),
    "converted copy: written, bytes %s, gzip bytes %s, fits secret limit %s" % (
        _NUM, _NUM, _alt(("yes", "no"))),
    "converted copy: refused \\(%s\\)" % _alt(convert.CONVERT_REASONS),
    "d06 evidence: written",
    "settings enforce_q_lims: %s" % _alt(("on", "off", "inconclusive")),
    "settings deviations: %s" % _NUM,
    "settings: refused \\(var_limit_conflict\\)",
    "scaling %s: %s" % (_alt(_DETAIL_NAMES), _alt(scaling.DETAIL_VALUES)),
    "net03 %s algorithm: %s" % (_CITY, _alt(_VERDICT_WORDS)),
    "net03 %s counts: buses compared %s failed %s, flows compared %s failed %s" % (
        _CITY, _NUM, _NUM, _NUM, _NUM),
    "net03 %s injected: %s" % (_CITY, _alt(_VERDICT_WORDS + ("not run",))),
    "net03 %s note: %s" % (_CITY, _WORD),
    "net03: %s \\(%s of %s cities\\)" % (_alt(_VERDICT_WORDS), _NUM, _NUM),
    "report: written",
    "check: %s" % _alt(("pass", "fail")),
    "usage: pandapower_net_check.py \\{ingest,check\\} \\.\\.\\.",
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
    parser = _Parser(prog="pandapower_net_check.py", add_help=False)
    commands = parser.add_subparsers(dest="command", parser_class=_Parser)
    ingest_parser = commands.add_parser("ingest", add_help=False)
    ingest_parser.add_argument("--zip", required=True, dest="zip")
    ingest_parser.add_argument("--sessions-dir", dest="sessions_dir", default=None)
    check_parser = commands.add_parser("check", add_help=False)
    check_parser.add_argument("--session", required=True)
    check_parser.add_argument("--mapping", required=True)
    check_parser.add_argument("--registry", default=None)
    check_parser.add_argument("--allow-placeholder", action="store_true", dest="allow_placeholder")
    return parser


# -- reading an extracted session ----------------------------------------------------------------


class _Session(object):
    """Read access to the members of a verified session folder, by member name."""

    def __init__(self, directory, manifest):
        self.directory = directory
        self.manifest = manifest

    def has(self, name):
        return name in self.manifest["members"]

    def read_bytes(self, name):
        if not self.has(name):
            return None
        try:
            with open(os.path.join(self.directory, *name.split("/")), "rb") as handle:
                data = handle.read(_MAX_JSON_BYTES + 1)
        except OSError:
            return None
        return None if len(data) > _MAX_JSON_BYTES else data

    def json(self, name):
        """The dict of a JSON member, or None when it is missing, unreadable or not an object."""
        data = self.read_bytes(name)
        if data is None:
            return None
        try:
            document = json.loads(data.decode("utf-8"), parse_constant=_refuse_constant)
        except (ValueError, UnicodeDecodeError, RecursionError):
            return None
        return document if isinstance(document, dict) else None

    def raw(self, name):
        """The raw.ParsedCase of a RAW member, or None when it is missing or refused."""
        data = self.read_bytes(name)
        if data is None:
            return None
        try:
            return raw.parse_raw(data)
        except raw.RawRefused:
            return None


def _refuse_constant(_name):
    raise ValueError("not a finite number")


def _load_registry(path):
    """The registry dict (empty when `path` is None); compare.RegistryRefused or ValueError."""
    if path is None:
        return {}
    try:
        with open(path, "rb") as handle:
            data = handle.read(_MAX_REGISTRY_BYTES + 1)
    except OSError:
        raise compare.RegistryRefused("unreadable")
    if len(data) > _MAX_REGISTRY_BYTES:
        raise compare.RegistryRefused("too_large")
    try:
        document = json.loads(data.decode("utf-8"), parse_constant=_refuse_constant)
    except (ValueError, UnicodeDecodeError, RecursionError):
        raise compare.RegistryRefused("not_json")
    return compare.load_registry(document)


# -- the report file -----------------------------------------------------------------------------


def _safe(value):
    """`value` as something strict JSON holds: non-finite numbers become words, tuples lists."""
    if isinstance(value, float):
        return value if math.isfinite(value) else ("nan" if math.isnan(value) else (
            "inf" if value > 0 else "-inf"))
    if isinstance(value, dict):
        return dict((str(key), _safe(item)) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_safe(item) for item in value]
    if value is None or isinstance(value, (bool, int, str)):
        return value
    return str(value)


def _difference_record(item):
    return {"element": item.element, "quantity": item.quantity, "size": _safe(item.size)}


def _verdict_record(verdict):
    return {
        "city": verdict.city, "run": verdict.run, "complete": verdict.complete,
        "passed": verdict.passed, "buses_compared": verdict.buses_compared,
        "buses_failed": verdict.buses_failed, "flows_compared": verdict.flows_compared,
        "flows_failed": verdict.flows_failed, "transformer_flows": verdict.transformer_flows,
        "worst_voltage_pu": _safe(verdict.worst_voltage_pu),
        "worst_flow_excess_mva": _safe(verdict.worst_flow_excess_mva),
        "explained": [_difference_record(item) for item in verdict.explained],
        "unexplained": [_difference_record(item) for item in verdict.unexplained],
        "missing": [list(item) for item in verdict.missing],
        "deviations": list(verdict.deviations)}


def _parity_record(report):
    return {
        "passed": report.passed,
        "differences": [_safe(list(item)) for item in report.differences],
        "compared": _safe(dict(report.compared)), "elements": _safe(dict(report.elements))}


def _settings_record(settings):
    return {
        "enforce_q_lims": settings.enforce_q_lims, "tolerance_mva": _safe(settings.tolerance_mva),
        "max_iteration": settings.max_iteration,
        "collapse_voltage_pu": _safe(settings.collapse_voltage_pu),
        "sources": _safe(settings.sources), "deviations": list(settings.deviations)}


# -- the runs ------------------------------------------------------------------------------------


def _enforce_runs(settings):
    """((label, enforce_q_lims), ...): one run, or both settings when the classification is
    inconclusive."""
    if settings.enforce_q_lims is None:
        return (("algorithm:enforce_q_lims_off", False), ("algorithm:enforce_q_lims_on", True))
    return ((compare.RUN_ALGORITHM, settings.enforce_q_lims),)


def _unsolved():
    """A stand-in net for a run that produced no solved state: the comparator reads `converged`
    first and reports the comparison incomplete."""
    return types.SimpleNamespace(converged=False)


def _solve_note(outcome):
    return outcome.reason if outcome.reason in (
        "not_converged", "nan_voltage", "voltage_collapse",
        "shunt_control_not_settled") else "solver_error"


def _solved_or_stand_in(net, settings, enforce, notes):
    outcome = solve.run_load_flow(net, settings, enforce)
    if outcome.converged:
        return net
    notes.append(_solve_note(outcome))
    return _unsolved()


def _algorithm_verdicts(city, base_net, city_mapping, details, settings, reference, registry,
                        notes):
    verdicts = []
    runs = _enforce_runs(settings)
    try:
        scaled = scaling.scale_city(base_net, city_mapping.scaling, details)
    except (scaling.ScalingRefused, scaling.ScalingUndetermined) as problem:
        notes.append(problem.reason)
        scaled = None
    for label, enforce in runs:
        net = _unsolved()
        if scaled is not None:
            net = _solved_or_stand_in(copy.deepcopy(scaled), settings, enforce, notes)
        verdicts.append(compare.compare_city(
            city, label, net, reference, registry, settings.deviations))
    return verdicts


def _injected_verdict(city, base_net, session, settings, reference, registry, notes):
    """The injected-snapshot diagnostic, or None when the session has no pre-solve snapshot."""
    name = "reference/%s/presolve.raw" % city.lower()
    if not session.has(name):
        return None
    presolve = session.raw(name)
    net = _unsolved()
    if presolve is None:
        notes.append("snapshot_unreadable")
    else:
        try:
            injected = scaling.inject_snapshot(base_net, presolve)
        except scaling.ScalingRefused as problem:
            notes.append(problem.reason)
        else:
            net = _solved_or_stand_in(injected, settings, _enforce_runs(settings)[0][1], notes)
    return compare.compare_city(city, compare.RUN_INJECTED, net, reference, registry,
                                settings.deviations)


def _word(verdicts):
    if any(not item.complete for item in verdicts):
        return "incomplete"
    return "pass" if all(item.passed for item in verdicts) else "fail"


def _utc(now):
    value = now() if callable(now) else now
    if value is None:
        value = datetime.datetime.now(datetime.timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime.timezone.utc)
    return value


# -- ingest --------------------------------------------------------------------------------------


def _run_ingest(args, say, repo_root):
    try:
        private.require_private(args.zip, repo_root)
        result = ingest.ingest_zip(args.zip, args.sessions_dir, repo_root)
    except private.PrivatePathRefused as problem:
        say("private path: refused (%s)" % problem.reason, "err")
        return EXIT_USAGE
    except ingest.IngestRefused as problem:
        say("ingest: refused (%s)" % problem.reason, "err")
        return EXIT_USAGE
    say("ingest: ok")
    say("members verified: %d" % result.members_verified)
    for section in result.manifest["sections"]:
        name, status = section.get("name"), section.get("status")
        if name in bundle.SECTION_WORDS and status in bundle.STATUS_WORDS:
            say("section %s: %s" % (name, status))
    return EXIT_OK


# -- check ---------------------------------------------------------------------------------------


class _Check(object):
    """One run of the `check` command: its state, its private report and its exit decision."""

    def __init__(self, args, say, repo_root, now):
        self.args = args
        self.say = say
        self.repo_root = repo_root
        self.stamp = bundle.stamp(_utc(now))
        self.report = {"stamp": self.stamp, "pandapower": getattr(pandapower, "__version__", None),
                       "python": "%d.%d.%d" % tuple(sys.version_info[:3])}
        self.out_dir = None

    def write_json(self, name, document):
        return private.write_private_json(
            os.path.join(self.out_dir, name), document, REPORT_MARKER, self.repo_root)

    def finish_report(self):
        self.write_json("report.json", self.report)
        self.say("report: written")

    def run(self):
        args = self.args
        session_dir = args.session
        try:
            session_dir = private.require_private(session_dir, self.repo_root)
            manifest = ingest.verify_session_dir(session_dir)
        except private.PrivatePathRefused as problem:
            self.say("private path: refused (%s)" % problem.reason, "err")
            return EXIT_USAGE
        except ingest.IngestRefused as problem:
            self.say("session: refused (%s)" % problem.reason, "err")
            return EXIT_USAGE
        self.say("session: verified")
        try:
            mapping = ingest.check_mapping(manifest, args.mapping, args.allow_placeholder)
        except ingest.IngestRefused as problem:
            self.say("mapping: refused (%s)" % problem.reason, "err")
            return EXIT_USAGE
        except mapping_module.MappingError:
            self.say("mapping: refused (mapping_invalid)", "err")
            return EXIT_USAGE
        self.say("mapping: verified")
        registry_path = args.registry
        if registry_path is None:
            default = os.path.join(session_dir, ingest.REGISTRY_FILE_NAME)
            registry_path = default if os.path.isfile(default) else None
        try:
            registry = _load_registry(registry_path)
        except compare.RegistryRefused as problem:
            self.say("registry: refused (%s)" % problem.reason, "err")
            return EXIT_USAGE
        self.say("registry: none" if registry_path is None else "registry: %d entries" % len(registry))
        try:
            self.out_dir = private.make_private_dir(
                os.path.join(session_dir, _CHECK_PREFIX + self.stamp), self.repo_root)
        except private.PrivatePathRefused as problem:
            self.say("private path: refused (%s)" % problem.reason, "err")
            return EXIT_USAGE
        meta = dict((key, manifest.get(key)) for key in (
            "created_utc", "mode", "python_version", "psse_version", "case_sha256",
            "mapping_sha256", "mapping_placeholder"))
        self.report["session"] = meta
        return self.analyse(_Session(session_dir, manifest), mapping, registry)

    def analyse(self, session, mapping, registry):
        say = self.say
        network_bytes = session.read_bytes(_NETWORK_MEMBER)
        try:
            if network_bytes is None:
                raise raw.RawRefused("empty")
            case = raw.parse_raw(network_bytes)
            net = network.build_network(case)
        except raw.RawRefused as problem:
            self.report["network"] = {"refused": problem.reason, "line": problem.line}
            say("network: refused (%s)" % problem.reason)
            self.finish_report()
            return EXIT_FAILED
        except network.BuildRefused as problem:
            self.report["network"] = {
                "refused": problem.reason, "count": problem.count,
                "elements": list(problem.elements), "lines": list(problem.lines)}
            say("network: refused (%s)" % problem.reason)
            self.finish_report()
            return EXIT_FAILED
        say("network: built")
        self.report["network"] = {"refused": None}
        healthy = self.parity_and_copies(case, net)

        try:
            fingerprints = {}
            settings_json = session.json(_SETTINGS_MEMBER) or {}
            for item in settings_json.get("fingerprints") or ():
                member = item.get("member") if isinstance(item, dict) else None
                payload = session.json(member) if isinstance(member, str) else None
                if payload is not None:
                    fingerprints[member] = payload
            settings = solve.settings_from_session(
                settings_json, fingerprints, mapping.settings.collapse_voltage_pu)
        except ValueError:
            say("settings: refused (var_limit_conflict)")
            self.report["settings"] = {"refused": "var_limit_conflict"}
            self.finish_report()
            return EXIT_FAILED
        say("settings enforce_q_lims: %s" % {True: "on", False: "off", None: "inconclusive"}[
            settings.enforce_q_lims])
        say("settings deviations: %d" % len(settings.deviations))
        self.report["settings"] = _settings_record(settings)

        details = self.scaling_details(session)
        verdicts = self.cities(session, mapping, registry, net, settings, details)
        overall = compare.net03_verdict(verdicts)
        say(self.net03_line(overall))
        self.report["net03"] = {
            "passed": overall.passed, "cities_passed": overall.cities_passed,
            "cities_complete": overall.cities_complete,
            "verdicts": [_verdict_record(item) for item in verdicts]}
        self.finish_report()
        ok = healthy and overall.passed
        say("check: %s" % ("pass" if ok else "fail"))
        return EXIT_OK if ok else EXIT_FAILED

    def parity_and_copies(self, case, net):
        say = self.say
        report = parity.parity_report(case, net)
        say("parity: %s" % ("pass" if report.passed else "fail"))
        for category, (made, differing) in report.category_counts().items():
            say("parity category %s: compared %d differing %d" % (category, made, differing))
        self.report["parity"] = _parity_record(report)
        healthy = report.passed
        try:
            data = convert.case_to_json(case)
        except convert.ConvertRefused as problem:
            say("converted copy: refused (%s)" % problem.reason)
            healthy = False
        else:
            size = convert.size_report(data)
            private.write_private_bytes(
                os.path.join(self.out_dir, "converted_network.json"), data, self.repo_root)
            say("converted copy: written, bytes %d, gzip bytes %d, fits secret limit %s" % (
                size["bytes"], size["gzip_bytes"], "yes" if size["fits_secret_limit"] else "no"))
            self.report["converted_copy"] = size
        evidence = parity.case39_evidence(case)
        self.write_json("d06_evidence.json", _safe(evidence._asdict()))
        say("d06 evidence: written")
        self.report["d06_evidence"] = _safe(evidence._asdict())
        return healthy

    def scaling_details(self, session):
        experiments = session.json(_EXPERIMENTS_MEMBER) or {}
        snapshots = {}
        wanted = 0
        for record in experiments.get("experiments") or ():
            if not isinstance(record, dict):
                continue
            for field in ("before", "after"):
                member = record.get(field)
                if isinstance(member, str) and member not in snapshots:
                    wanted += 1
                    case = session.raw(member)
                    if case is not None:
                        snapshots[member] = case
        details = scaling.analyse_scaling_details(experiments, snapshots)
        for name in _DETAIL_NAMES:
            self.say("scaling %s: %s" % (name, getattr(details, name)))
        document = {
            "swing_in_total": details.swing_in_total, "clamped_at_limits": details.clamped_at_limits,
            "q_scales_with_p": details.q_scales_with_p, "evidence": _safe(details.evidence),
            "snapshots_wanted": wanted, "snapshots_read": len(snapshots)}
        self.write_json("scaling_details.json", document)
        self.report["scaling"] = document
        return details

    def cities(self, session, mapping, registry, net, settings, details):
        say = self.say
        verdicts = []
        by_city = {}
        for city in constants.CITIES:
            notes = []
            reference = session.json("reference/%s/base.json" % city.lower())
            algorithm = _algorithm_verdicts(
                city, net, mapping.cities[city], details, settings, reference, registry, notes)
            injected = _injected_verdict(city, net, session, settings, reference, registry, notes)
            verdicts.extend(algorithm)
            if injected is not None:
                verdicts.append(injected)
            say("net03 %s algorithm: %s" % (city, _word(algorithm)))
            say("net03 %s counts: buses compared %d failed %d, flows compared %d failed %d" % (
                city, sum(item.buses_compared for item in algorithm),
                sum(item.buses_failed for item in algorithm),
                sum(item.flows_compared for item in algorithm),
                sum(item.flows_failed for item in algorithm)))
            say("net03 %s injected: %s" % (
                city, "not run" if injected is None else _word([injected])))
            for note in sorted(set(notes)):
                say("net03 %s note: %s" % (city, note))
            by_city[city] = notes
        self.report["city_notes"] = by_city
        return verdicts

    @staticmethod
    def net03_line(overall):
        total = len(overall.cities)
        if overall.passed:
            word = "pass"
        else:
            decided = {}
            for item in overall.verdicts:
                if item.run == compare.RUN_ALGORITHM or item.run.startswith(
                        compare.RUN_ALGORITHM + ":"):
                    decided.setdefault(item.city, []).append(item)
            word = "incomplete" if any(
                not all(item.complete for item in items) for items in decided.values()
            ) or len(decided) < total else "fail"
        return "net03: %s (%d of %d cities)" % (word, overall.cities_passed, total)


# -- main ----------------------------------------------------------------------------------------


def main(argv, out=None, err=None, repo_root=None, now=None):
    """
    Run the owner's command `argv` (without the program name) and return the exit code. `out` and
    `err` are text streams (default stdout and stderr), `repo_root` points the private-path guard
    at another repository (tests), `now` is a datetime or a function returning one (the stamp of
    the check folder). Never raises.
    """
    printer = _Printer(sys.stdout if out is None else out, sys.stderr if err is None else err)

    def say(text, stream=None):
        printer.say(text, printer.err if stream == "err" else None)

    try:
        try:
            args = _build_parser().parse_args(list(argv))
            if args.command is None:
                raise _UsageError()
        except _UsageError:
            printer.problem("usage: pandapower_net_check.py {ingest,check} ...")
            printer.problem("usage error: bad or missing arguments")
            return EXIT_USAGE
        if args.command == "ingest":
            return _run_ingest(args, say, repo_root)
        return _Check(args, say, repo_root, now).run()
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
