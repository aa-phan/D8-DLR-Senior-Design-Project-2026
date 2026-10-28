"""
A one-off probe for the licensed laptop (pss-e-integration Phase 2, written for Phase 3).

It checks that the real psspy matches the psse_api.SURFACE table the fake psspy was built from,
and that the adapter's calls work on a case, without changing that case. The Phase 3 launcher
imports psspy and passes the module to run_probe, because importing psspy inside psse_job is
forbidden (backend/tests/psse_contract_test.py); there is no command-line entry point here.

run_probe returns ProbeRow(check, status, detail) rows, status "PASS", "FAIL" or "SKIP":
  - signature:<name> for every SURFACE row: the function exists and every parameter name the
    table lists is in its signature (extra parameters are counted); a signature that cannot be
    read is a SKIP, never a PASS (research assumption A6);
  - a read-only pass on the case: version, load_case, branch_table, bus_table,
    column_alignment (the bulk RATEA column against single-branch brndat reads, research
    Pitfall 8), circuit_id_padding (Pitfall 7), option_strings (A2), load_flow and, when a
    mapping is given, mapping;
  - with write_check True also rating_write (RATEA moved by one MVA on one circuit, read back,
    then undone by loading the case from disk again) and scale_load (the sink subsystem and
    scal_2 called with 1 MW, then the case loaded again). The probe never saves a case, so
    Power Systems' file is never written; the adapter's CaseProtected guard also applies.

A probe failure is a FAIL row, never an exception. By default the report carries no bus number,
circuit id, path or exception text, so it can be pasted into the public repository; a failing
adapter call is shown as its function name and ierr only. Pass show_identifiers=True to see
exception texts and mapping problems, on the laptop only.

Standard library and psse_job only, Python 3.7 syntax (D-05).
"""

import collections
import inspect

from psse_job import constants, psse_api, study

ProbeRow = collections.namedtuple("ProbeRow", ["check", "status", "detail"])

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

_ALIGNED_LINES = 3
_RATING_TOLERANCE = 1e-6
_PROBE_SUBSYSTEM = 9
_SIGNATURE_UNREADABLE = (
    "signature not inspectable (assumption A6); the read-only pass exercises the call")


def _failure_text(error, show_identifiers):
    """The exception class; the adapter's function and ierr; the text only when asked for."""
    text = type(error).__name__
    if isinstance(error, psse_api.PsseCallError):
        text += " (psspy.%s, ierr %s)" % (error.function, error.ierr)
    if show_identifiers:
        text += ": %s" % (error,)
    return text


def _count(number, noun):
    return "%d %s%s" % (number, noun, "" if number == 1 else "s")


# -- signatures ----------------------------------------------------------------------------------


def check_signatures(psspy_module):
    """One ProbeRow per SURFACE row, comparing the module's function with the table."""
    rows = []
    for surface in psse_api.SURFACE:
        check = "signature:" + surface.name
        try:
            function = getattr(psspy_module, surface.name, None)
        except Exception:
            function = None
        if function is None or not callable(function):
            rows.append(ProbeRow(check, FAIL, "missing"))
            continue
        try:
            signature = inspect.signature(function)
        except (TypeError, ValueError):
            rows.append(ProbeRow(check, SKIP, _SIGNATURE_UNREADABLE))
            continue
        except Exception as error:
            rows.append(ProbeRow(check, FAIL, "signature could not be read: %s" % type(error).__name__))
            continue
        names = set(signature.parameters)
        missing = [name for name in surface.parameters if name not in names]
        takes_any_keyword = any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values())
        if missing and takes_any_keyword:
            rows.append(ProbeRow(
                check, SKIP, "accepts any keyword, so the names %s cannot be confirmed; the "
                "read-only pass exercises the call" % ", ".join(missing)))
            continue
        if missing:
            rows.append(ProbeRow(check, FAIL, "missing parameter %s" % ", ".join(missing)))
            continue
        extra = len(names - set(surface.parameters))
        detail = "all %s present" % _count(len(surface.parameters), "parameter")
        if extra:
            detail += "; %s not in the table" % _count(extra, "extra parameter")
        rows.append(ProbeRow(check, PASS, detail))
    return rows


# -- the checks on a case ------------------------------------------------------------------------


class _Probe(object):
    """The state shared by the checks of one run_probe call."""

    def __init__(self, psspy_module, case_path, mapping, show_identifiers):
        self.psspy_module = psspy_module
        self.case_path = case_path
        self.mapping = mapping
        self.show = show_identifiers
        self.api = None
        self.loaded = False
        self.lines = []
        self.transformers = []
        self.buses = {}
        self.resolved = None
        self.rows = []

    def record(self, check, status, detail):
        self.rows.append(ProbeRow(check, status, detail))

    def run(self, check, function, needs_case=True, creates_adapter=False):
        """Run one check in its own try block: a ProbeRow from `function`, FAIL on an exception."""
        if self.api is None and not creates_adapter:
            self.record(check, SKIP, "not run: the adapter could not be created")
            return
        if needs_case and not self.loaded:
            self.record(check, SKIP, "not run: the case did not load")
            return
        try:
            status, detail = function()
        except Exception as error:
            status, detail = FAIL, _failure_text(error, self.show)
        self.record(check, status, detail)

    # -- read-only checks --

    def version(self):
        self.api = psse_api.PsseApi(self.psspy_module, protected_path=self.case_path)
        text = self.api.version()
        if text == "unknown":
            return FAIL, "the version could not be read from psseversion"
        return PASS, "PSS/E %s" % text

    def load_case(self):
        self.api.load_case(self.case_path)
        self.loaded = True
        return PASS, "the case loaded"

    def branch_table(self):
        self.lines, self.transformers = self.api.branch_table()
        return PASS, "%s, %s" % (_count(len(self.lines), "line"),
                                 _count(len(self.transformers), "transformer"))

    def bus_table(self):
        self.buses = self.api.bus_table()
        return PASS, _count(len(self.buses), "bus")

    def column_alignment(self):
        flows = [row for row in self.api.branch_loading("RATEA", "current") if row.in_service]
        flows = flows[:_ALIGNED_LINES]
        if not flows:
            return SKIP, "no in-service line to compare"
        different = 0
        for row in flows:
            if abs(self.api.read_rate(row, "RATEA") - row.rate_mva) > _RATING_TOLERANCE:
                different += 1
        if different:
            return FAIL, ("%d of %s: the bulk RATEA column differs from the single-branch "
                          "read (the columns may not be aligned)" % (
                              different, _count(len(flows), "line")))
        return PASS, "%s: the bulk RATEA column equals the single-branch read" % _count(
            len(flows), "line")

    def circuit_id_padding(self):
        result = self.api._call("abrnchar", sid=-1, owner=1, ties=1, flag=2, entry=1,
                                string=["ID"])
        if (not isinstance(result, (tuple, list)) or len(result) != 2 or result[0] != 0
                or not isinstance(result[1], (tuple, list)) or len(result[1]) != 1):
            return FAIL, "the raw circuit-id read did not return (0, [column])"
        ids = result[1][0]
        if not ids:
            return PASS, "no branch to read"
        if not all(isinstance(text, str) for text in ids):
            return FAIL, "the raw circuit-id column holds a value that is not text"
        if all(len(text) == 2 for text in ids):
            return PASS, "ids come back padded to two characters (the adapter strips them)"
        if any(len(text) == 2 for text in ids):
            return PASS, "ids come back padded to two characters in part (the adapter strips them)"
        return PASS, "ids come back without padding (the adapter strips either way)"

    def option_strings(self):
        self.api.branch_loading("RATEA", "current")
        self.api.branch_loading("RATEA", "mva")
        return PASS, "both percent-of-rating item names (current and mva) are accepted"

    def load_flow(self):
        result = self.api.solve()
        if result.converged:
            return PASS, "the load flow converged"
        return FAIL, "the load flow did not converge: %s" % result.meaning

    def mapping_check(self):
        if not self.lines and not self.buses:
            return SKIP, "no branch or bus table to check the mapping against"
        resolved, problems = study.check_mapping(
            self.mapping, self.lines, self.transformers, self.buses)
        self.resolved = resolved
        kv = []
        for city in constants.CITIES:
            values = sorted(set(round(branch.base_kv, 3) for branch in resolved.get(city, ())))
            kv.append("%s %s" % (city, "/".join("%g kV" % value for value in values)
                                 if values else "no line"))
        detail = "%s; %s" % (_count(len(problems), "problem"), ", ".join(kv))
        if problems:
            if self.show:
                detail += "; " + "; ".join(problems)
            return FAIL, detail
        return PASS, detail

    # -- opt-in write checks --

    def _target(self):
        """The circuit to write on: the first resolved mapped line, else the first in-service line."""
        if self.resolved is not None:
            for city in constants.CITIES:
                if self.resolved.get(city):
                    return self.resolved[city][0].ref
        for row in self.lines:
            if row.in_service:
                return row
        return None

    def rating_write(self):
        target = self._target()
        if target is None:
            return SKIP, "no in-service line to write on"
        original = self.api.read_rate(target, "RATEA")
        changed = original + (1.0 if original else 100.0)
        problem = None
        try:
            self.api.set_rate(target, "RATEA", changed)
            written = self.api.read_rate(target, "RATEA")
            if abs(written - changed) > _RATING_TOLERANCE * max(1.0, abs(changed)):
                problem = "the rating written was not read back"
        finally:
            self.api.load_case(self.case_path)
        restored = self.api.read_rate(target, "RATEA")
        if abs(restored - original) > _RATING_TOLERANCE * max(1.0, abs(original)):
            return FAIL, "reloading the case did not restore the original rating"
        if problem:
            return FAIL, problem
        return PASS, "RATEA was changed by one MVA, read back and restored by reloading the case"

    def scale_load(self):
        target = self._target()
        sinks = []
        if self.mapping is not None:
            for city in constants.CITIES:
                sinks = list(self.mapping.cities[city].sink_buses)
                if sinks:
                    break
        if sinks:
            bus = sinks[0]
        elif target is not None:
            bus = target.to_bus
        else:
            return SKIP, "no bus to define the subsystem on"
        try:
            self.api.define_subsystem(_PROBE_SUBSYSTEM, [bus])
            self.api.scale_load(_PROBE_SUBSYSTEM, 1.0)
        finally:
            self.api.load_case(self.case_path)
        return PASS, "the subsystem was defined and 1 MW of load added; the case was reloaded"


def run_probe(psspy_module, case_path, mapping=None, write_check=False, show_identifiers=False):
    """The signature rows followed by the checks on the case, as a list of ProbeRow.

    Never raises for a probe failure. The case at `case_path` is only ever loaded, never saved;
    the write checks (opt-in) change the working case in memory and reload it from disk.
    """
    rows = check_signatures(psspy_module)
    probe = _Probe(psspy_module, case_path, mapping, show_identifiers)
    probe.rows = rows
    probe.run("version", probe.version, needs_case=False, creates_adapter=True)
    probe.run("load_case", probe.load_case, needs_case=False)
    probe.run("branch_table", probe.branch_table)
    probe.run("bus_table", probe.bus_table)
    probe.run("column_alignment", probe.column_alignment)
    probe.run("circuit_id_padding", probe.circuit_id_padding)
    probe.run("option_strings", probe.option_strings)
    probe.run("load_flow", probe.load_flow)
    if mapping is not None:
        probe.run("mapping", probe.mapping_check)
    if write_check:
        probe.run("rating_write", probe.rating_write)
        probe.run("scale_load", probe.scale_load)
    return probe.rows


def format_report(rows):
    """One line per row (status, check, detail) and a final '<n> PASS, <m> FAIL, <k> SKIP' line."""
    lines = ["%-4s  %s  %s" % (row.status, row.check, row.detail) for row in rows]
    counts = dict((status, 0) for status in (PASS, FAIL, SKIP))
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    lines.append("%d PASS, %d FAIL, %d SKIP" % (counts[PASS], counts[FAIL], counts[SKIP]))
    return "\n".join(lines)


def probe_ok(rows):
    """True when no row is a FAIL (a SKIP is not a pass but is not a failure either)."""
    return not any(row.status == FAIL for row in rows)
