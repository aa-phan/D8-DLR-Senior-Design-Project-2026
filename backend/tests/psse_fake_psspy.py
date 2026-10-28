"""
A fake psspy for the PSS/E job tests (pss-e-integration Phase 2, plan 02-02; research D-15).
Not collected by pytest (the file name does not match `*_test.py`).

`FakePsspy` implements exactly `psse_job.psse_api.SURFACE`, with the PSS/E API manual's
parameter names, so a misspelt keyword is a TypeError here as it would be on the laptop and
any other attribute is an AttributeError. It models only call shapes, return shapes and
failure handling, plus one simple radial network (`placeholder_case`, `radial_solver`); it
never does real power flow, and it proves nothing about what real PSS/E accepts (that is the
Phase 3 probe's job).

Every SURFACE method is recorded in `fake_calls` as (name, args, kwargs) by a wrapper that
keeps the method's own signature (functools.wraps), so inspect.signature still shows the
exact parameter names and no method has a catch-all keyword parameter. Helper attributes
start with "fake_" so the drift test can tell them from the psspy surface.

Radial solver (placeholder case): per city one source bus behind two ties from the swing bus
and one sink bus behind two parallel city lines. With S = hypot(sink P, sink Q) the sink
voltage is 1.0 - drop x S x 2 / n_line, every in-service city line carries S / n_line, and a
city with no in-service tie or no in-service city line is islanded (fnsl ierr 3).
"""

import collections
import copy
import functools
import math
import os

SWING_BUS = 90000
PLACEHOLDER_CITY_BUSES = {
    "AUSTIN": (90001, 90002),
    "CORPUS_CHRISTI": (90011, 90012),
    "MIDLAND": (90021, 90022),
    "EL_PASO": (90031, 90032),
}

INT_SENTINEL = 100000000
REAL_SENTINEL = 1.0e20
CHAR_SENTINEL = "\x01"

_LOAD_POWER_FACTOR = 0.95
_SINK_LOAD_MW = 620.0
_DROP_PER_MVA = {"AUSTIN": 1e-4, "CORPUS_CHRISTI": 1e-4, "MIDLAND": 1e-4, "EL_PASO": 2.5e-5}
_COLLAPSE_PU = 0.6
_RATE_SLOTS = 12

SolveOutcome = collections.namedtuple(
    "SolveOutcome", ["ierr", "solved", "voltages", "flows", "iterations", "mismatch"]
)
# ierr, solved code, voltages (bus -> pu) and flows (key -> dict) to apply, iteration count and
# mismatch reported afterwards; voltages and flows are None when the case is left as it was.
SolveOutcome.__new__.__defaults__ = (0, 0, None, None, 3, 0.02)


def _branch_key(from_bus, to_bus, ckt):
    return (from_bus, to_bus, ckt.strip())


def _normalise(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


class FakeCase(object):
    """The working case: buses, branches, loads and the radial solver's per-sink voltage drop."""

    def __init__(self):
        self.buses = {}
        self.branches = {}
        self.loads = {}
        self.drop_per_mva = {}

    def add_bus(self, number, type_code=1, base_kv=345.0, pu=1.0, nvlmlo=0.95, nvlmhi=1.05,
                evlmlo=0.90, evlmhi=1.10):
        self.buses[number] = {
            "type_code": type_code, "base_kv": base_kv, "pu": pu,
            "nvlmlo": nvlmlo, "nvlmhi": nvlmhi, "evlmlo": evlmlo, "evlmhi": evlmhi,
        }

    def add_branch(self, from_bus, to_bus, ckt, kind="line", status=1, rates=(0.0, 0.0, 0.0)):
        slots = [float(value) for value in rates] + [0.0] * (_RATE_SLOTS - len(rates))
        self.branches[_branch_key(from_bus, to_bus, ckt)] = {
            "status": status, "kind": kind, "rates": slots,
            "p_mw": 0.0, "max_mva": 0.0, "current_mva": 0.0,
        }

    def branch(self, from_bus, to_bus, ckt):
        return self.branches[_branch_key(from_bus, to_bus, ckt)]


def apply_outcome(case, outcome):
    """Write a converged outcome's voltages and flows into `case`."""
    for number, pu in (outcome.voltages or {}).items():
        case.buses[number]["pu"] = pu
    for key, values in (outcome.flows or {}).items():
        case.branches[key].update(values)


def radial_solver(case):
    """The default solver: a radial network per city of PLACEHOLDER_CITY_BUSES (see module doc)."""
    voltages = {}
    flows = {}
    for number, bus in case.buses.items():
        voltages[number] = 1.02 if bus["type_code"] == 3 else bus["pu"]
    for key, branch in case.branches.items():
        if branch["status"] != 1:
            flows[key] = {"p_mw": 0.0, "max_mva": 0.0, "current_mva": 0.0}
    for city, (source, sink) in PLACEHOLDER_CITY_BUSES.items():
        if source not in case.buses or sink not in case.buses:
            continue
        ties = [key for key, branch in case.branches.items()
                if key[0] == SWING_BUS and key[1] == source and branch["status"] == 1]
        lines = [key for key, branch in case.branches.items()
                 if key[0] == source and key[1] == sink and branch["status"] == 1]
        if not ties or not lines:
            return SolveOutcome(ierr=3, solved=None, iterations=0, mismatch=0.0)
        p_mw, q_mvar = case.loads.get(sink, [0.0, 0.0])
        apparent = math.hypot(p_mw, q_mvar)
        sink_pu = 1.0 - case.drop_per_mva.get(sink, 0.0) * apparent * 2.0 / len(lines)
        if sink_pu < _COLLAPSE_PU:
            return SolveOutcome(ierr=0, solved=1, iterations=20, mismatch=50.0)
        for key in lines:
            flows[key] = {"p_mw": p_mw / len(lines), "max_mva": apparent / len(lines),
                          "current_mva": apparent / len(lines) / sink_pu}
        for key in ties:
            flows[key] = {"p_mw": p_mw / len(ties), "max_mva": apparent / len(ties),
                          "current_mva": apparent / len(ties)}
        voltages[source] = 1.0
        voltages[sink] = sink_pu
    return SolveOutcome(ierr=0, solved=0, voltages=voltages, flows=flows)


def placeholder_case():
    """The placeholder network: the same 9xxxx buses as docs/data-science/schema/psse_mapping_example.json."""
    case = FakeCase()
    case.add_bus(SWING_BUS, type_code=3, pu=1.02)
    for city, (source, sink) in PLACEHOLDER_CITY_BUSES.items():
        case.add_bus(source)
        case.add_bus(sink)
        case.add_branch(SWING_BUS, source, "1", rates=(4000.0, 4400.0, 4800.0))
        case.add_branch(SWING_BUS, source, "2", rates=(4000.0, 4400.0, 4800.0))
        case.add_branch(source, sink, "1", rates=(1500.0, 1650.0, 1800.0))
        case.add_branch(source, sink, "2", rates=(500.0, 550.0, 600.0))
        case.loads[sink] = [_SINK_LOAD_MW, _SINK_LOAD_MW * math.tan(math.acos(_LOAD_POWER_FACTOR))]
        case.drop_per_mva[sink] = _DROP_PER_MVA[city]
    apply_outcome(case, radial_solver(case))
    return case


def _recorded(function):
    """Record each call (name, args, kwargs) while keeping the method's exact signature."""
    @functools.wraps(function)
    def wrapper(self, *args, **kwargs):
        self.fake_calls.append((function.__name__, args, dict(kwargs)))
        return function(self, *args, **kwargs)
    return wrapper


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


class FakePsspy(object):
    """Exactly the psse_api.SURFACE functions; see the module docstring."""

    def __init__(self, solver=None):
        self.fake_solver = radial_solver if solver is None else solver
        self.fake_state = None
        self.fake_calls = []
        self.fake_saved_paths = []
        self.fake_subsystems = {}
        self._registry = {}
        self._solved = 9
        self._iterations = 0
        self._mismatch = 0.0

    def fake_register_case(self, path, case):
        """Make `path` loadable: keeps a deep copy of `case` under the normalised path."""
        self._registry[_normalise(path)] = copy.deepcopy(case)

    # -- general ---------------------------------------------------------------------------

    @_recorded
    def psseversion(self):
        return ("PSS(R)E fake", 35, 6, 0, "2026-10-28", 0)

    @_recorded
    def getdefaultint(self):
        return INT_SENTINEL

    @_recorded
    def getdefaultreal(self):
        return REAL_SENTINEL

    @_recorded
    def getdefaultchar(self):
        return CHAR_SENTINEL

    # -- case and load flow ------------------------------------------------------------------

    @_recorded
    def case(self, sfile):
        if not isinstance(sfile, str) or not sfile.strip():
            return 1
        stored = self._registry.get(_normalise(sfile))
        if stored is None:
            return 3
        self.fake_state = copy.deepcopy(stored)
        return 0

    @_recorded
    def fnsl(self, options=None):
        if options is not None and not (
                isinstance(options, (list, tuple)) and len(options) == 8
                and all(_is_int(value) for value in options)):
            return 1
        if self.fake_state is None:
            return 5
        outcome = self.fake_solver(self.fake_state)
        if outcome.ierr != 0:
            return outcome.ierr
        self._solved = outcome.solved
        self._iterations = outcome.iterations
        self._mismatch = outcome.mismatch
        if outcome.solved == 0:
            apply_outcome(self.fake_state, outcome)
        return 0

    @_recorded
    def solved(self):
        return self._solved

    @_recorded
    def iterat(self):
        return self._iterations

    @_recorded
    def sysmsm(self):
        return self._mismatch

    # -- bulk branch reads -------------------------------------------------------------------

    def _branch_keys(self, sid, flag):
        """Keys for the abrn* flag (1 in-service lines, 2 all lines, 3 in-service lines and
        transformers, 4 all), in key order; None for an unsupported sid, flag or no case."""
        if self.fake_state is None or sid != -1 or flag not in (1, 2, 3, 4):
            return None
        keys = []
        for key in sorted(self.fake_state.branches):
            branch = self.fake_state.branches[key]
            if branch["kind"] == "transformer" and flag in (1, 2):
                continue
            if flag in (1, 3) and branch["status"] != 1:
                continue
            keys.append(key)
        return keys

    @_recorded
    def abrnint(self, sid, owner, ties, flag, entry, string):
        keys = self._branch_keys(sid, flag)
        if keys is None:
            return (4, [])
        columns = []
        for item in string:
            if item == "FROMNUMBER":
                columns.append([key[0] for key in keys])
            elif item == "TONUMBER":
                columns.append([key[1] for key in keys])
            elif item == "STATUS":
                columns.append([self.fake_state.branches[key]["status"] for key in keys])
            else:
                return (3, [])
        return (0, columns)

    @_recorded
    def abrnchar(self, sid, owner, ties, flag, entry, string):
        keys = self._branch_keys(sid, flag)
        if keys is None:
            return (4, [])
        columns = []
        for item in string:
            if item == "ID":
                columns.append(["%-2s" % key[2] for key in keys])
            else:
                return (3, [])
        return (0, columns)
