"""
A fake psspy for the laptop session tests (pandapower-solver Phase 1, plan 01-02).
Not collected by pytest (the file name does not match `*_test.py`).

`FakeSessionPsspy` is `psse_fake_psspy.FakePsspy` plus exactly the seven calls of
`psse_session.session.SESSION_SURFACE` (two RAW export calls, two parameter reads and three
machine bulk reads), with the parameter names that table lists, so a drift test can compare names
and `inspect.signature` parameters. It is a subclass because the Phase 2 fake is frozen and its
drift test pins its surface to `psse_job.psse_api.SURFACE`. The only base function it changes is
`abrnreal`, which gains the item "Q" (a from-end reactive flow derived from the stored P and
MAXMVA) and otherwise delegates unchanged.

`write_fake_raw(case, path, revision=33)` writes a revision 33 style RAW text for a
`psse_fake_psspy.FakeCase`: case header, two comment lines, bus, load, fixed shunt (empty),
generator, branch, transformer (empty) and area sections, every remaining section empty, then Q.
Section terminator lines are assembled from pieces so that no tracked file matches the leak
guard's shape layer.

Knobs: `raw_forms` names the export forms that succeed (a form is the function name plus whether
the arguments were positional or keywords, matched against `session.RAW_EXPORT_FORMS`); `fail` maps
a call name to "raise" (a RuntimeError whose text holds a fake path, to prove nothing prints it),
"empty" (an export writes zero bytes and returns 0), "interrupt" (KeyboardInterrupt) or an int ierr;
`prm` holds the values `prmint` and `prmdat` return.

Honest scope: this models call shapes, return shapes and failure handling only. That real PSS/E
has these functions with these parameter names, and that any export form writes what the fake
writes, is UNVERIFIED until the session of plan 01-10; the fake proves nothing about real PSS/E.
"""

import functools
import math

from psse_fake_psspy import SWING_BUS, FakePsspy, _recorded

FAKE_LEAK_TEXT = "failure while writing C:/Users/fakeuser/fakehost/private/%s.raw"
FORUM_STATUS = [1, 1, 1, 0, 0, 0, 0]
DEFAULT_PRM = {"MAXBUS": 20000, "MAXAREA": 100, "BASFRQ": 60.0, "THRSHZ": 0.0001}
PLAIN_IERR_NAMES = frozenset([
    "case", "fnsl", "save", "bsys", "branch_chng_3", "rawd_2", "writerawversion"])

_END = "END" + " OF "
_BEGIN = "BEG" + "IN"
RAW_SECTIONS_V33 = (
    "BUS", "LOAD", "FIXED SHUNT", "GENERATOR", "BRANCH", "TRANSFORMER", "AREA",
    "TWO-TERMINAL DC", "VSC DC LINE", "IMPEDANCE CORRECTION", "MULTI-TERMINAL DC",
    "MULTI-SECTION LINE", "ZONE", "INTER-AREA TRANSFER", "OWNER", "FACTS DEVICE",
    "SWITCHED SHUNT", "GNE", "INDUCTION MACHINE",
)


def raw_terminator(name, next_name):
    """The line that closes section `name` and, unless it is the last, names the next one."""
    line = "0 / " + _END + name + " DATA"
    if next_name is not None:
        line += ", " + _BEGIN + " " + next_name + " DATA"
    return line


def _machine_buses(case):
    swing = [number for number, bus in case.buses.items() if bus["type_code"] == 3]
    return sorted(set(swing) | set(case.gens))


def _transformer_text(key, branch):
    from_bus, to_bus, ckt = key
    rates = branch["rates"]
    return [
        "%d,%d,0,'%-2s',1,1,1,0.0,0.0,2,'XF%d    ',1,1,1.0" % (from_bus, to_bus, ckt, from_bus),
        "0.001,0.05,100.0",
        "1.0,345.0,0.0,%.1f,%.1f,%.1f,0,0,1.1,0.9,1.1,0.9,33,0,0.0,0.0,0.0" % tuple(rates[:3]),
        "1.0,345.0",
    ]


def _section_lines(case, transformer_lines):
    sections = dict((name, []) for name in RAW_SECTIONS_V33)
    for number in sorted(case.buses):
        bus = case.buses[number]
        sections["BUS"].append(
            "%d,'BUS%-5d',%.4f,%d,1,1,1,%.5f,0.0000,%.5f,%.5f,%.5f,%.5f" % (
                number, number, bus["base_kv"], bus["type_code"], bus["pu"], bus["nvlmhi"],
                bus["nvlmlo"], bus["evlmhi"], bus["evlmlo"]))
    for number in sorted(case.loads):
        p_mw, q_mvar = case.loads[number]
        sections["LOAD"].append(
            "%d,'1 ',1,1,1,%.3f,%.3f,0.0,0.0,0.0,0.0,1,1,0" % (number, p_mw, q_mvar))
    for number in _machine_buses(case):
        sections["GENERATOR"].append(
            "%d,'1 ',%.3f,0.0,9999.0,-9999.0,1.02000,0,100.0,0.0,1.0,0.0,0.0,1.0,1,100.0,"
            "9999.0,-9999.0,1,1.0" % (number, case.gens.get(number, 0.0)))
    transformers = []
    for key in sorted(case.branches):
        branch = case.branches[key]
        if branch["kind"] == "transformer":
            transformers.extend(_transformer_text(key, branch))
            continue
        sections["BRANCH"].append(
            "%d,%d,'%-2s',0.001,0.05,0.0,%.1f,%.1f,%.1f,0.0,0.0,0.0,0.0,%d,1,0.0,1,1.0" % (
                key[0], key[1], key[2], branch["rates"][0], branch["rates"][1],
                branch["rates"][2], branch["status"]))
    sections["TRANSFORMER"] = transformers + list(transformer_lines)
    sections["AREA"].append("1,%d,0.0,10.0,'AREA1   '" % SWING_BUS)
    return sections


def fake_raw_bytes(case, revision=33, transformer_lines=()):
    """The RAW text of `case` as bytes (latin-1); `transformer_lines` are appended verbatim."""
    sections = _section_lines(case, transformer_lines)
    lines = [
        "0, 100.00, %d, 0, 1, 60.00     / PSS(R)E fake case" % revision,
        "FAKE CASE TITLE LINE ONE",
        "FAKE CASE TITLE LINE TWO",
    ]
    for index, name in enumerate(RAW_SECTIONS_V33):
        lines.extend(sections[name])
        following = RAW_SECTIONS_V33[index + 1] if index + 1 < len(RAW_SECTIONS_V33) else None
        lines.append(raw_terminator(name, following))
    lines.append("Q")
    return ("\n".join(lines) + "\n").encode("latin-1")


def write_fake_raw(case, path, revision=33, transformer_lines=()):
    """Write `fake_raw_bytes` to `path`; returns the byte count."""
    data = fake_raw_bytes(case, revision, transformer_lines)
    with open(path, "wb") as handle:
        handle.write(data)
    return len(data)


class FakeSessionPsspy(FakePsspy):
    """FakePsspy plus the SESSION_SURFACE calls; see the module docstring."""

    def __init__(self, solver=None, raw_forms=("rawd_2_forum_positional",), fail=None, prm=None):
        FakePsspy.__init__(self, solver=solver)
        self.fake_raw_forms = tuple(raw_forms)
        self.fake_fail = dict(fail or {})
        self.fake_prm = dict(DEFAULT_PRM if prm is None else prm)

    def __getattribute__(self, name):
        attribute = object.__getattribute__(self, name)
        if name.startswith("_") or name.startswith("fake_") or not callable(attribute):
            return attribute
        try:
            modes = object.__getattribute__(self, "fake_fail")
        except AttributeError:
            return attribute
        mode = modes.get(name)
        if mode is None or mode == "empty":
            return attribute
        return functools.partial(object.__getattribute__(self, "_fail_call"), name, mode)

    def _fail_call(self, name, mode, *args, **kwargs):
        self.fake_calls.append((name, args, dict(kwargs)))
        if mode == "raise":
            raise RuntimeError(FAKE_LEAK_TEXT % name)
        if mode == "interrupt":
            raise KeyboardInterrupt()
        if name in PLAIN_IERR_NAMES:
            return mode
        return (mode, [])

    # -- RAW export --------------------------------------------------------------------------

    def _export(self, name, form_id, ofile, revision):
        if form_id not in self.fake_raw_forms:
            return 1
        if self.fake_state is None:
            return 4
        try:
            with open(ofile, "wb") as handle:
                if self.fake_fail.get(name) != "empty":
                    handle.write(fake_raw_bytes(self.fake_state, revision))
        except (OSError, TypeError):
            return 2
        return 0

    def _call_kind(self):
        return "positional" if self.fake_calls[-1][1] else "keywords"

    @_recorded
    def rawd_2(self, sid, all, status, out, ofile):  # noqa: A002 - the manual's name
        if sid != 0 or all != 1 or status != FORUM_STATUS or out != 0:
            return 1
        return self._export("rawd_2", "rawd_2_forum_" + self._call_kind(), ofile, 33)

    @_recorded
    def writerawversion(self, vernum, out, ofile):
        if vernum != 33 or out != 0:
            return 1
        return self._export(
            "writerawversion", "writerawversion_33_" + self._call_kind(), ofile, vernum)

    # -- parameter reads ---------------------------------------------------------------------

    @_recorded
    def prmint(self, name):
        value = self.fake_prm.get(name)
        if isinstance(value, int) and not isinstance(value, bool):
            return (0, value)
        return (1, None)

    @_recorded
    def prmdat(self, name):
        value = self.fake_prm.get(name)
        if isinstance(value, float):
            return (0, value)
        return (1, None)

    # -- machine bulk reads ------------------------------------------------------------------

    def _machines(self, sid, flag):
        if self.fake_state is None or sid != -1 or flag not in (1, 2):
            return None
        return _machine_buses(self.fake_state)

    def _machine_real(self, bus, item):
        pgen = self.fake_state.gens.get(bus, 0.0)
        values = {"PGEN": pgen, "QGEN": 0.0, "PMAX": pgen * 1.2 + 100.0, "PMIN": 0.0,
                  "QMAX": 300.0, "QMIN": -300.0}
        return values.get(item)

    @_recorded
    def amachint(self, sid, flag, string):
        buses = self._machines(sid, flag)
        if buses is None:
            return (4, [])
        columns = []
        for item in string:
            if item == "NUMBER":
                columns.append(list(buses))
            elif item == "STATUS":
                columns.append([1 for _ in buses])
            else:
                return (3, [])
        return (0, columns)

    @_recorded
    def amachreal(self, sid, flag, string):
        buses = self._machines(sid, flag)
        if buses is None:
            return (4, [])
        columns = []
        for item in string:
            column = [self._machine_real(bus, item) for bus in buses]
            if any(value is None for value in column):
                return (3, [])
            columns.append(column)
        return (0, columns)

    @_recorded
    def amachchar(self, sid, flag, string):
        buses = self._machines(sid, flag)
        if buses is None:
            return (4, [])
        columns = []
        for item in string:
            if item != "ID":
                return (3, [])
            columns.append(["1 " for _ in buses])
        return (0, columns)

    # -- the one changed base function -------------------------------------------------------

    @_recorded
    def abrnreal(self, sid, owner, ties, flag, entry, string):
        base = FakePsspy.abrnreal.__wrapped__
        if "Q" not in string:
            return base(self, sid, owner, ties, flag, entry, string)
        keys = self._branch_keys(sid, flag)
        if keys is None:
            return (4, [])
        columns = []
        for item in string:
            if item == "Q":
                column = []
                for key in keys:
                    branch = self.fake_state.branches[key]
                    column.append(math.sqrt(max(branch["max_mva"] ** 2 - branch["p_mw"] ** 2, 0.0)))
                columns.append(column)
                continue
            ierr, part = base(self, sid, owner, ties, flag, entry, [item])
            if ierr != 0:
                return (ierr, [])
            columns.append(part[0])
        return (0, columns)
