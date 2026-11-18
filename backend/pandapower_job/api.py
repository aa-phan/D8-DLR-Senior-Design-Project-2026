"""
The pandapower adapter of the study engine (pandapower-solver Phase 2, plan 02-02: ENG-01 to ENG-04).

`PandapowerApi` offers the study code the same methods it uses from `psse_job.psse_api.PsseApi`
(`load_case`, `branch_table`, `bus_table`, `read_rate`, `set_rate`, `set_status`, `solve`,
`branch_loading`, `save_case`, `version`), over a pandapower network built by
`network.build_network`. The study code does not know which solver it talks to (D-01). This module
may import `psse_job`; `psse_job` never imports it.

The case file is read only by the project's own fail-closed parsers: `raw.parse_raw` for a RAW
file, or `convert.case_from_json` for the project's converted network document, chosen by the
`.json` suffix (assumption Q2 of this plan: the owner decides which of the two the hourly job
uses in plan 01-11; reversible). pandapower's own network readers and Python object
serialisation are never used on a file. The parsed case becomes a master network once per case
path; every `load_case` hands out a fresh deep copy and the master is never changed (D-09).

State machine (D-04, D-05). The adapter holds one working network and one state:

- FRESH   just loaded, nothing solved. `bus_table` answers with NaN voltages so a caller that
  skipped the solve fails closed; `branch_loading` is refused.
- SOLVED  the last solve converged and nothing has changed since. Every read works.
- FAILED  the last solve did not converge. `bus_table` and `branch_loading` are refused.
- STALE   `set_status` or `set_rate` changed the network after the last solve. Both are refused:
  pandapower keeps the old result tables after a change, and a tripped line would read its old
  loading.

`branch_table`, `read_rate` and the writes are allowed in every state. Nothing ever flips a status
back to repair a network: callers reload a snapshot (`save_case` keeps one in memory and writes no
file).

Outcome mapping of `solve` (RESEARCH Pattern 3), onto the existing `psse_api.SolveResult`:

    run_load_flow outcome                 SolveResult
    converged                             classify_solve(0, 0, iterations): converged
    reason "nan_voltage" (an island:      classify_solve(3, None): ierr 3, "buses in island
      pandapower says converged and         without swing bus"
      leaves the isolated buses NaN)
    reason "voltage_collapse"             classify_solve(0, 2): "blown up"
    any other reason (not_converged,      classify_solve(0, 1): "iteration limit exceeded"
      an exception class name)

pandapower's own `net.converged` flag is never the rule: the rule is `solve.run_load_flow` of
Phase 1, with the settings of the injected backend (D-06), never a constant in this module.

Every refusal is a ValueError, `psse_api.CaseProtected` or a `PandapowerCallError` (a
`psse_api.PsseCallError`). No message holds a bus number, a branch key, a path or a value; the
texts are reasons only, because stored errors reach the database and the logs.
"""

import collections
import copy
import math

import pandapower

from psse_job import psse_api
from pandapower_job import convert, network, raw, solve

PandapowerBackend = collections.namedtuple("PandapowerBackend", ["solve_settings", "scaling_details"])

FRESH = "fresh"
SOLVED = "solved"
FAILED = "failed"
STALE = "stale"

_NOT_LOADED = "no case is loaded"


class PandapowerCallError(psse_api.PsseCallError):
    """A pandapower adapter call failed. The message holds the function, the ierr and a reason only."""

    def __init__(self, function, ierr, meaning):
        self.function = function
        self.ierr = ierr
        self.meaning = meaning
        RuntimeError.__init__(self, "pandapower.%s failed: ierr=%s (%s)" % (function, ierr, meaning))


def _branch_parts(name):
    """(from bus, to bus, ckt) of a branch name `from-to-ckt`, or None when it is not one."""
    pieces = str(name).split("-", 2)
    if len(pieces) != 3 or not pieces[0].isdigit() or not pieces[1].isdigit() or not pieces[2]:
        return None
    return int(pieces[0]), int(pieces[1]), pieces[2]


class PandapowerApi(object):
    """The study's way to pandapower: an injected backend over one working network."""

    def __init__(self, backend, protected_path=None):
        if not isinstance(backend, PandapowerBackend):
            raise ValueError("backend must be a PandapowerBackend")
        self._backend = backend
        self._protected = None if protected_path is None else psse_api._normalise_path(protected_path)
        self.warnings = []
        self._masters = {}
        self._snapshots = {}
        self._net = None
        self._state = FRESH
        self._last_reason = None

    # -- case ----------------------------------------------------------------------------

    def _build_master(self, normalised):
        is_json = normalised.endswith(".json")
        cap = convert.MAX_CONVERTED_BYTES if is_json else raw.MAX_RAW_BYTES
        try:
            with open(normalised, "rb") as handle:
                data = handle.read(cap + 1)
        except OSError:
            raise PandapowerCallError("load_case", 3, psse_api.CASE_ERRORS[3]) from None
        if len(data) > cap:
            raise PandapowerCallError("load_case", 2, psse_api.CASE_ERRORS[2])
        case = convert.case_from_json(data) if is_json else raw.parse_raw(data)
        return network.build_network(case)

    def load_case(self, path):
        """Make a fresh deep copy of the case at `path` the working network (state FRESH).

        The file is read and built once per path; the master is never handed out or changed.
        A parser or builder refusal is a ValueError and passes through unchanged.
        """
        normalised = psse_api._normalise_path(path)
        snapshot = self._snapshots.get(normalised)
        if snapshot is not None:
            saved_net, saved_state = snapshot
            self._net = copy.deepcopy(saved_net)
            self._state = SOLVED if saved_state == SOLVED else FRESH
            self._last_reason = None
            return
        master = self._masters.get(normalised)
        if master is None:
            master = self._build_master(normalised)
            self._masters[normalised] = master
        self._net = copy.deepcopy(master)
        self._state = FRESH
        self._last_reason = None

    def save_case(self, path):
        """Keep a deep copy of the working network and its state in memory under `path`.

        No file is written (D-09). A later `load_case(path)` restores the copy: state SOLVED when
        it was saved solved, FRESH otherwise (a failed or stale state is never restored). Never onto
        the case file that was loaded.
        """
        normalised = psse_api._normalise_path(path)
        if normalised == self._protected:
            raise psse_api.CaseProtected("refusing to save onto the case file that was loaded")
        net = self._need_net("save_case")
        self._snapshots[normalised] = (copy.deepcopy(net), self._state)

    # -- helpers -------------------------------------------------------------------------

    def _need_net(self, function):
        if self._net is None:
            raise PandapowerCallError(function, None, _NOT_LOADED)
        return self._net

    def _require_solved(self, function):
        net = self._need_net(function)
        if self._state != SOLVED:
            raise PandapowerCallError(function, None, "no valid solution (state: %s)" % self._state)
        return net

    @staticmethod
    def _line_index(net, from_bus, to_bus, ckt):
        """The `net.line` index of the branch in either orientation, or None."""
        wanted = (raw.branch_key(from_bus, to_bus, ckt), raw.branch_key(to_bus, from_bus, ckt))
        for index, name in net.line["name"].items():
            if name in wanted:
                return index
        return None

    @staticmethod
    def _is_transformer(net, from_bus, to_bus, ckt):
        wanted = (raw.branch_key(from_bus, to_bus, ckt), raw.branch_key(to_bus, from_bus, ckt))
        return any(name in wanted for name in net.trafo["name"])

    @staticmethod
    def _from_kv(net, line_index):
        return float(net.bus.at[net.line.at[line_index, "from_bus"], "vn_kv"])

    # -- reads that need no solution -----------------------------------------------------

    def branch_table(self):
        """(lines, transformers): BranchRow lists sorted by key, any status."""
        net = self._need_net("branch_table")
        lines = {}
        for index in net.line.index:
            from_bus, to_bus = int(net.line.at[index, "from_bus"]), int(net.line.at[index, "to_bus"])
            parts = _branch_parts(net.line.at[index, "name"])
            if parts is None or parts[0] != from_bus or parts[1] != to_bus:
                raise PandapowerCallError("branch_table", None, "branch name does not match its buses")
            row = psse_api.BranchRow(from_bus, to_bus, parts[2],
                                     bool(net.line.at[index, "in_service"]), False)
            if row.key in lines:
                raise PandapowerCallError("branch_table", None, "duplicate branch key")
            lines[row.key] = row
        transformers = {}
        for index in net.trafo.index:
            from_bus, to_bus = int(net.trafo.at[index, "hv_bus"]), int(net.trafo.at[index, "lv_bus"])
            parts = _branch_parts(net.trafo.at[index, "name"])
            if parts is None or parts[0] != from_bus or parts[1] != to_bus:
                raise PandapowerCallError("branch_table", None, "branch name does not match its buses")
            row = psse_api.BranchRow(from_bus, to_bus, parts[2],
                                     bool(net.trafo.at[index, "in_service"]), True)
            if row.key not in lines:
                if row.key in transformers:
                    raise PandapowerCallError("branch_table", None, "duplicate branch key")
                transformers[row.key] = row
        return ([lines[key] for key in sorted(lines)],
                [transformers[key] for key in sorted(transformers)])

    def read_rate(self, ref, rate_set):
        """The rating (MVA) of `ref`: its one current limit expressed at the from-bus voltage.

        Every rate set reads the same limit (D-07): the line has one current limit.
        """
        if rate_set not in psse_api.RATE_INDEX:
            raise ValueError("rate_set must be one of %s" % ", ".join(sorted(psse_api.RATE_INDEX)))
        from_bus, to_bus, ckt = psse_api.PsseApi._ref_parts(ref)
        net = self._need_net("read_rate")
        index = self._line_index(net, from_bus, to_bus, ckt)
        if index is None:
            raise PandapowerCallError("read_rate", 2, psse_api.BRNDAT_ERRORS[2])
        return float(net.line.at[index, "max_i_ka"]) * math.sqrt(3) * self._from_kv(net, index)

    # -- writes --------------------------------------------------------------------------

    def set_rate(self, ref, rate_set, mva):
        """Write `mva` (finite, above 0) as the line's current limit; the state becomes STALE (D-07)."""
        if rate_set not in psse_api.RATE_INDEX:
            raise ValueError("rate_set must be one of %s" % ", ".join(sorted(psse_api.RATE_INDEX)))
        if not psse_api._is_number(mva):
            raise ValueError("mva must be a number")
        try:
            value = float(mva)
        except OverflowError:
            raise ValueError("mva is out of range") from None
        if not (math.isfinite(value) and value > 0):
            raise ValueError("mva must be finite and greater than 0")
        from_bus, to_bus, ckt = psse_api.PsseApi._ref_parts(ref)
        net = self._need_net("set_rate")
        index = self._line_index(net, from_bus, to_bus, ckt)
        if index is None:
            if self._is_transformer(net, from_bus, to_bus, ckt):
                raise PandapowerCallError("set_rate", 3, psse_api.BRANCH_CHNG_ERRORS[3])
            raise PandapowerCallError("set_rate", 9, psse_api.BRANCH_CHNG_ERRORS[9])
        net.line.at[index, "max_i_ka"] = value / (math.sqrt(3) * self._from_kv(net, index))
        self._state = STALE

    def set_status(self, ref, in_service):
        """Put the line in service (True) or out of service (False); the state becomes STALE.

        Ratings are untouched. A status is never flipped back to repair a network: callers
        reload a snapshot.
        """
        if not isinstance(in_service, bool):
            raise ValueError("in_service must be True or False")
        from_bus, to_bus, ckt = psse_api.PsseApi._ref_parts(ref)
        net = self._need_net("set_status")
        index = self._line_index(net, from_bus, to_bus, ckt)
        if index is None:
            if self._is_transformer(net, from_bus, to_bus, ckt):
                raise PandapowerCallError("set_status", 3, psse_api.BRANCH_CHNG_ERRORS[3])
            raise PandapowerCallError("set_status", 9, psse_api.BRANCH_CHNG_ERRORS[9])
        net.line.at[index, "in_service"] = in_service
        self._state = STALE

    # -- load flow -----------------------------------------------------------------------

    def solve(self, options=None):
        """Solve the working network and classify the result; non-convergence is a result.

        See the module docstring for the outcome mapping. The settings come from the injected
        backend (D-06).
        """
        if options is not None:
            raise ValueError("solve options are PSS/E fnsl options and are not supported by "
                             "pandapower; use null")
        net = self._need_net("solve")
        settings = self._backend.solve_settings
        try:
            outcome = solve.run_load_flow(net, settings, settings.enforce_q_lims)
        except ValueError:
            self._state = FAILED
            raise
        self._last_reason = outcome.reason
        if outcome.converged:
            self._state = SOLVED
            return psse_api.classify_solve(0, 0, outcome.iterations, None)
        self._state = FAILED
        if outcome.reason == "nan_voltage":
            return psse_api.classify_solve(3, None)
        if outcome.reason == "voltage_collapse":
            return psse_api.classify_solve(0, 2)
        return psse_api.classify_solve(0, 1)

    # -- reads that need a solution ------------------------------------------------------

    def bus_table(self):
        """dict bus number -> BusRow for every bus.

        FRESH gives NaN voltages (never read from the result tables), so a caller that skipped
        the solve fails closed; FAILED and STALE are refused. Type code: 4 out of service, 3 an
        in-service external grid on it, 2 an in-service machine, else 1. The builder does not carry
        emergency limits, so evlmlo and evlmhi are 0.0; nvlmlo and nvlmhi are NaN when absent.
        """
        net = self._need_net("bus_table")
        if self._state not in (FRESH, SOLVED):
            self._require_solved("bus_table")
        swing = set(int(bus) for bus in net.ext_grid.bus[net.ext_grid.in_service.astype(bool)])
        machines = set(int(bus) for bus in net.gen.bus[net.gen.in_service.astype(bool)])
        table = {}
        for index in net.bus.index:
            number = int(index)
            if not bool(net.bus.at[index, "in_service"]):
                code = 4
            elif number in swing:
                code = 3
            elif number in machines:
                code = 2
            else:
                code = 1
            if self._state == SOLVED and index in net.res_bus.index:
                pu = float(net.res_bus.at[index, "vm_pu"])
            else:
                pu = float("nan")
            table[number] = psse_api.BusRow(
                number, code, float(net.bus.at[index, "vn_kv"]), pu,
                float(net.bus.at[index, "min_vm_pu"]), float(net.bus.at[index, "max_vm_pu"]),
                0.0, 0.0)
        return table

    def branch_loading(self, rate_set, basis):
        """BranchFlow for every line (any status), sorted by key, on pandapower's current basis."""
        psse_api.pct_string(rate_set, basis)
        if basis != "current":
            raise ValueError("thermal basis mva cannot be reproduced by pandapower; use current")
        net = self._require_solved("branch_loading")
        flows = {}
        for index in net.line.index:
            from_bus, to_bus = int(net.line.at[index, "from_bus"]), int(net.line.at[index, "to_bus"])
            parts = _branch_parts(net.line.at[index, "name"])
            if parts is None or parts[0] != from_bus or parts[1] != to_bus:
                raise PandapowerCallError("branch_loading", None, "branch name does not match its buses")
            result = net.res_line.loc[index]
            p_from, q_from = float(result.p_from_mw), float(result.q_from_mvar)
            p_to, q_to = float(result.p_to_mw), float(result.q_to_mvar)
            row = psse_api.BranchFlow(
                from_bus, to_bus, parts[2], bool(net.line.at[index, "in_service"]),
                math.sqrt(3) * self._from_kv(net, index) * float(net.line.at[index, "max_i_ka"]),
                float(result.loading_percent), p_from,
                max(math.hypot(p_from, q_from), math.hypot(p_to, q_to)))
            if row.key in flows:
                raise PandapowerCallError("branch_loading", None, "duplicate branch key")
            flows[row.key] = row
        return [flows[key] for key in sorted(flows)]

    def version(self):
        """The pandapower version as a string, or 'unknown' on any failure."""
        try:
            return str(pandapower.__version__)
        except Exception:
            return "unknown"
