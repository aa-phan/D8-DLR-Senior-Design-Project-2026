"""
The reference section of the laptop session (pandapower-solver Phase 1, plan 01-03: PSE-03).

For each city of `constants.CITIES`, in that order, PSS/E's full solved answer for the city's
scaled copy of the case, for every outage the job itself would screen, and at the limit point of
the job's voltage-margin search (D-09, D-10). Every answer comes from the job's own functions
(Pattern 3 of the phase research): `study.scale_city_case` for the pre-solve snapshot,
`study.prepare_city_base` for the solved base (a fresh load, the city's scaling, static ratings,
the solve, the saved solved copy), `contingency.select_outages` for the outage list and
`margin.city_margin` for the margin search. The reference is therefore the job's study by
construction, and the outage list can never drift from the job's.

Members written for city `<city>` (the CITIES name in lower case) under `reference/<city>/`; every
JSON member also carries the member marker key `bundle.WorkFolder.add_json` adds:

- `presolve.raw`: the scaled copy before any rating or solve, as RAW text written by PSS/E.
- `solved.raw` and `base.json`: the solved base. `base.json` holds the city, the rate set and the
  thermal basis the job reads, `rating_source` ("static": the session has no database, so the
  static rating is the only rating there is, Pitfall 6; loading percentages are a diagnostic in
  Phase 1, the gate is voltage and flow), and the solved state. A city whose preparation failed
  gets a `base.json` with status failed and the failing stage word only.
- `outages.json`: one record per outage of `select_outages(base)`, in that order, never dropped.
  Each outage starts from a fresh reload of the saved solved base and is never un-tripped and
  re-solved (Pitfall 7: the start point decides the solution near a limit). A non-converged or
  islanded outage keeps its ierr, solved code and meaning with null states; a call that raised is
  recorded in `call_failed`. A converged outage also gets `outage_<nnn>.raw` (nnn is the
  zero-padded position in the list, never a bus number).
- `margin.json` and `margin_last_good.raw`, `margin_first_bad.raw`: the margin row's details and
  the bus voltages and solve status re-solved at the last good transfer and, when it exists, at
  the first bad transfer, each with a RAW snapshot (D-10: where a reactive-limit difference
  between the engines would show).

A solved state holds `solve`, `buses` (sorted by number), `line_flows` (the job's own
branch_loading, sorted by key), `branch_flows` and `machine_outputs` (extended reads that go
through the call gate directly, each `status` ok or unavailable with the function and the class
or ierr named in `reason`, never missing without saying so) and `snapshot` (the RAW member name or
null). Only the base is a Phase 1 gate (D-11); everything else is exported now because the session
is run once.

Per-city isolation: a city whose preparation, screen or margin fails is recorded as failed with
the StudyFailed stage word only (never its message, which can hold branch keys), and the other
cities still run. The saved .sav copies live in a temporary folder inside the work folder, are
never members, and are removed with `study.cleanup_base` on every path.

Honest scope: proven only against the fake psspy. The extended reads (abrn flag 4 with P, Q and
MAXMVA; the machine reads amachint, amachchar and amachreal) are UNVERIFIED on PSS/E 36.4. The
machine selection flag is tried as 2, 4, then 1 (the fake models 1 and 2; the plan's assumption
of 4 as for abrn is kept as the second try) and the flag that worked is recorded in
`machine_outputs.flag`; whether any of them works is for the session of plan 01-10 to learn.

Standard library plus psse_job only, Python 3.7 syntax (D-05).
"""

import collections
import math
import os

from psse_job import constants, contingency, margin, psse_api, study
from psse_session import bundle, session

SECTION = "reference"
RATING_SOURCE = "static"
BRANCH_FLAG = 4
MACHINE_FLAGS = (2, 4, 1)
_BRANCH_SELECTORS = dict(sid=-1, owner=1, ties=1, flag=BRANCH_FLAG, entry=1)


class _Refusal(Exception):
    """An extended read the engine refused; `text` names the function and the class or ierr only."""

    def __init__(self, function, reason):
        Exception.__init__(self, function)
        self.text = "%s: %s" % (function, reason)


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _num(value):
    """`value` as a float, or None for anything that is not a finite number (JSON has no NaN)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _int_or_none(value):
    return value if _is_int(value) else None


def _failure_text(error):
    """The function and class of a failed call, never its message."""
    function = getattr(error, "function", None)
    name = bundle.class_word(error)
    return "%s %s" % (function, name) if isinstance(function, str) else name


def _solve_dict(result):
    return {
        "converged": bool(result.converged),
        "ierr": _int_or_none(result.ierr),
        "solved_code": _int_or_none(result.solved_code),
        "meaning": result.meaning if isinstance(result.meaning, str) else None,
        "iterations": _int_or_none(result.iterations),
        "mismatch_mva": _num(result.mismatch_mva),
    }


def _bus_rows(buses):
    rows = []
    for number in sorted(buses):
        row = buses[number]
        rows.append({"number": row.number, "type_code": row.type_code,
                     "base_kv": _num(row.base_kv), "pu": _num(row.pu)})
    return rows


def _flow_rows(flows):
    rows = []
    for flow in sorted(flows, key=lambda item: item.key):
        rows.append({
            "key": flow.key, "from_bus": flow.from_bus, "to_bus": flow.to_bus, "ckt": flow.ckt,
            "in_service": bool(flow.in_service), "rate_mva": _num(flow.rate_mva),
            "pct": _num(flow.pct), "p_mw": _num(flow.p_mw), "max_mva": _num(flow.max_mva)})
    return rows


# -- the extended reads (through the call gate directly) ------------------------------------------


def _bulk(gated, name, count, **kwargs):
    """The `count` equal-length columns of a bulk read; _Refusal for an exception, a non-zero ierr
    or a malformed return. Mirrors psse_api.PsseApi._bulk, which only serves SURFACE functions."""
    try:
        result = getattr(gated, name)(**kwargs)
    except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
        raise _Refusal(name, bundle.class_word(exc))
    if not isinstance(result, (tuple, list)) or len(result) != 2 or not _is_int(result[0]):
        raise _Refusal(name, "UnexpectedReturn")
    if result[0] != 0:
        raise _Refusal(name, "ierr %d" % result[0])
    columns = result[1]
    if (not isinstance(columns, (tuple, list)) or len(columns) != count
            or any(not isinstance(column, (tuple, list)) for column in columns)
            or len(set(len(column) for column in columns)) > 1):
        raise _Refusal(name, "UnexpectedColumns")
    return [list(column) for column in columns]


def _require(name, columns, kinds):
    """Every column holds the kind its slot names: "int", "str" or "real" (a number)."""
    for column, kind in zip(columns, kinds):
        for value in column:
            if kind == "int" and not _is_int(value):
                raise _Refusal(name, "ColumnType")
            if kind == "str" and not isinstance(value, str):
                raise _Refusal(name, "ColumnType")
            if kind == "real" and (isinstance(value, bool) or not isinstance(value, (int, float))):
                raise _Refusal(name, "ColumnType")


class _Reader(object):
    """The all-branch and machine reads of the case in memory, each ok or unavailable."""

    def __init__(self, ctx):
        self._gated = ctx.gated
        self._transformers = set(row.key for row in ctx.index.transformers)
        self._machine_flag = None

    def branch_flows(self):
        try:
            ints = _bulk(self._gated, "abrnint", 3, string=["FROMNUMBER", "TONUMBER", "STATUS"],
                         **_BRANCH_SELECTORS)
            chars = _bulk(self._gated, "abrnchar", 1, string=["ID"], **_BRANCH_SELECTORS)
            reals = _bulk(self._gated, "abrnreal", 3, string=["P", "Q", "MAXMVA"],
                          **_BRANCH_SELECTORS)
            _require("abrnint", ints, ("int", "int", "int"))
            _require("abrnchar", chars, ("str",))
            _require("abrnreal", reals, ("real", "real", "real"))
            if len(chars[0]) != len(ints[0]) or len(reals[0]) != len(ints[0]):
                raise _Refusal("abrnreal", "UnequalColumns")
        except _Refusal as refusal:
            return {"status": "unavailable", "reason": refusal.text, "flag": BRANCH_FLAG,
                    "rows": []}
        rows = []
        for index in range(len(ints[0])):
            from_bus, to_bus, ckt = ints[0][index], ints[1][index], chars[0][index].strip()
            key = "%d-%d-%s" % (from_bus, to_bus, ckt)
            rows.append({
                "key": key, "is_transformer": key in self._transformers,
                "in_service": ints[2][index] == 1, "p_mw": _num(reals[0][index]),
                "q_mvar": _num(reals[1][index]), "max_mva": _num(reals[2][index])})
        rows.sort(key=lambda row: row["key"])
        return {"status": "ok", "reason": None, "flag": BRANCH_FLAG, "rows": rows}

    def _machines_at(self, flag):
        selectors = dict(sid=-1, flag=flag)
        ints = _bulk(self._gated, "amachint", 2, string=["NUMBER", "STATUS"], **selectors)
        chars = _bulk(self._gated, "amachchar", 1, string=["ID"], **selectors)
        reals = _bulk(self._gated, "amachreal", 6,
                      string=["PGEN", "QGEN", "PMAX", "PMIN", "QMAX", "QMIN"], **selectors)
        _require("amachint", ints, ("int", "int"))
        _require("amachchar", chars, ("str",))
        _require("amachreal", reals, ("real",) * 6)
        if len(chars[0]) != len(ints[0]) or len(reals[0]) != len(ints[0]):
            raise _Refusal("amachreal", "UnequalColumns")
        rows = []
        for index in range(len(ints[0])):
            rows.append({
                "bus": ints[0][index], "id": chars[0][index].strip(),
                "in_service": ints[1][index] == 1, "p_mw": _num(reals[0][index]),
                "q_mvar": _num(reals[1][index]), "p_max_mw": _num(reals[2][index]),
                "p_min_mw": _num(reals[3][index]), "q_max_mvar": _num(reals[4][index]),
                "q_min_mvar": _num(reals[5][index])})
        rows.sort(key=lambda row: (row["bus"], row["id"]))
        return rows

    def machine_outputs(self):
        flags = MACHINE_FLAGS if self._machine_flag is None else (self._machine_flag,)
        reasons = []
        for flag in flags:
            try:
                rows = self._machines_at(flag)
            except _Refusal as refusal:
                reasons.append("flag %d: %s" % (flag, refusal.text))
                continue
            self._machine_flag = flag
            return {"status": "ok", "reason": None, "flag": flag, "rows": rows}
        self._machine_flag = None
        return {"status": "unavailable", "reason": "; ".join(reasons), "flag": None, "rows": []}


# -- one solved state -----------------------------------------------------------------------------


def _snapshot(ctx, member):
    """`member` when PSS/E wrote it as RAW text, else None (the JSON member is written anyway)."""
    if ctx.raw_writer is None:
        return None
    try:
        record = ctx.raw_writer(member)
    except Exception:  # noqa: BLE001 - a missing snapshot is recorded as null, never fatal
        return None
    return member if isinstance(record, dict) and record.get("status") == "ok" else None


def _read_state(ctx, reader, tally, member, solve, buses, flows):
    """The solved state of the case in memory: the job's own bus and line reads (passed in), the
    RAW snapshot and the two extended reads."""
    snapshot = _snapshot(ctx, member)
    branch_flows = reader.branch_flows()
    machine_outputs = reader.machine_outputs()
    for read in (branch_flows, machine_outputs):
        if read["status"] != "ok":
            tally["extended_reads_unavailable"] += 1
    return {
        "solve": _solve_dict(solve),
        "buses": _bus_rows(buses),
        "line_flows": _flow_rows(flows),
        "branch_flows": branch_flows,
        "machine_outputs": machine_outputs,
        "snapshot": snapshot,
    }


# -- the pieces of one city -----------------------------------------------------------------------


def _remove_folder(path):
    """Delete the tree at `path`, best effort."""
    for root, dirs, files in os.walk(path, topdown=False):
        for name in files:
            try:
                os.remove(os.path.join(root, name))
            except OSError:
                pass
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


def _presolve(ctx, city, prefix):
    """The scaled copy before any rating or solve, exported as RAW through the session's writer."""
    api = ctx.index.api
    api.load_case(ctx.case_path)
    study.scale_city_case(api, city, ctx.mapping.cities[city].scaling)
    if ctx.raw_writer is not None:
        _snapshot(ctx, prefix + "presolve.raw")


def _write_base(ctx, base, city, prefix, reader, tally):
    state = _read_state(ctx, reader, tally, prefix + "solved.raw", base.solve, base.base_buses,
                        base.base_flows)
    document = {
        "city": city, "status": "ok", "rate_set": base.settings.rate_sets[0],
        "thermal_basis": base.settings.thermal_basis, "rating_source": RATING_SOURCE}
    document.update(state)
    ctx.work.add_json(prefix + "base.json", document, SECTION)


def _outage_record(ctx, base, reader, tally, prefix, position, outage):
    record = {
        "position": position, "key": outage.key, "from_bus": outage.from_bus,
        "to_bus": outage.to_bus, "ckt": outage.ckt, "converged": False, "ierr": None,
        "solved_code": None, "meaning": None, "call_failed": None, "solve": None,
        "buses": None, "line_flows": None, "branch_flows": None, "machine_outputs": None,
        "snapshot": None}
    api = base.api
    try:
        api.load_case(base.saved_path)
        api.set_status(outage, False)
        result = api.solve(base.settings.solve_options)
    except (psse_api.PsseCallError, ValueError) as error:
        record["call_failed"] = _failure_text(error)
        return record
    record.update(converged=bool(result.converged), ierr=_int_or_none(result.ierr),
                  solved_code=_int_or_none(result.solved_code),
                  meaning=result.meaning if isinstance(result.meaning, str) else None,
                  solve=_solve_dict(result))
    if not result.converged:
        return record
    try:
        buses = api.bus_table()
        flows = api.branch_loading(base.settings.rate_sets[0], base.settings.thermal_basis)
        state = _read_state(ctx, reader, tally, "%soutage_%03d.raw" % (prefix, position), result,
                            buses, flows)
    except (psse_api.PsseCallError, ValueError) as error:
        record["call_failed"] = _failure_text(error)
        return record
    record.update(state)
    return record


def _write_outages(ctx, city, prefix, status, records):
    ctx.work.add_json(prefix + "outages.json", {
        "city": city, "status": status, "count": len(records), "outages": records}, SECTION)


def _screen(ctx, base, city, prefix, reader, tally, entry):
    """Every outage of the job's own list; outages.json is written whatever happens."""
    try:
        outages = contingency.select_outages(base)
    except study.StudyFailed as failure:
        if "exceed" in str(failure.message):
            _write_outages(ctx, city, prefix, "failed", [])
            raise
        _write_outages(ctx, city, prefix, "none_selected", [])
        entry["notes"].append("none selected")
        return
    records = []
    status = "failed"
    try:
        for position, outage in enumerate(outages):
            ctx.budget.check("contingency")
            records.append(_outage_record(ctx, base, reader, tally, prefix, position, outage))
        status = "ok"
    finally:
        tally["outages"] += len(records)
        tally["converged"] += sum(1 for record in records if record["converged"])
        _write_outages(ctx, city, prefix, status, records)


def _margin_point(ctx, base, reader, tally, prefix, name, increment, sink_buses):
    point = {"increment_mw": increment, "call_failed": None, "solve": None, "buses": None,
             "line_flows": None, "branch_flows": None, "machine_outputs": None, "snapshot": None}
    api = base.api
    try:
        api.load_case(base.saved_path)
        api.define_subsystem(margin.SINK_SID, sink_buses)
        if increment > 0:
            api.scale_load(margin.SINK_SID, increment)
        result = api.solve(base.settings.solve_options)
        point["solve"] = _solve_dict(result)
        if result.converged:
            buses = api.bus_table()
            flows = api.branch_loading(base.settings.rate_sets[0], base.settings.thermal_basis)
            point.update(_read_state(
                ctx, reader, tally, "%smargin_%s.raw" % (prefix, name), result, buses, flows))
    except (psse_api.PsseCallError, ValueError) as error:
        point["call_failed"] = _failure_text(error)
    tally["margin_points"] += 1
    return point


def _margin(ctx, base, city, prefix, reader, tally, entry):
    """The job's voltage-margin search, then the solved state at its last good and first bad point."""
    try:
        result = margin.city_margin(base, city)
    except study.StudyFailed as failure:
        ctx.work.add_json(prefix + "margin.json", {
            "city": city, "status": "failed", "failed_stage": bundle.safe_item(failure.stage),
            "details": None, "bounded_by": None, "last_good": None, "first_bad": None}, SECTION)
        raise
    details = dict(result.row["details"])
    sink_buses = list(details.get("sink_buses") or ())
    points = {}
    for name, key in (("last_good", "increment_mw"), ("first_bad", "first_bad_mw")):
        increment = _num(details.get(key))
        if increment is None or not sink_buses:
            points[name] = None
        else:
            points[name] = _margin_point(ctx, base, reader, tally, prefix, name, increment,
                                         sink_buses)
    ctx.work.add_json(prefix + "margin.json", {
        "city": city, "status": "ok", "details": details, "bounded_by": result.bounded_by,
        "last_good": points["last_good"], "first_bad": points["first_bad"]}, SECTION)
    entry["margin_increments"] = (_num(details.get("increment_mw")),
                                  _num(details.get("first_bad_mw")))
    entry["sink_buses"] = sink_buses


def _write_failed_base(ctx, city, prefix, detail):
    if prefix + "base.json" in ctx.work.members():
        return
    try:
        ctx.work.add_json(prefix + "base.json", {
            "city": city, "status": "failed", "failed_stage": detail[0]}, SECTION)
    except Exception:  # noqa: BLE001 - the failure is already in the section result
        pass


def _run_city(ctx, reader, tally, tmp_root, city):
    entry = {"status": "ok", "detail": (), "notes": [], "margin_increments": None,
             "sink_buses": None}
    prefix = "reference/%s/" % city.lower()
    folder = os.path.join(tmp_root, city.lower())
    base = None
    try:
        os.makedirs(folder, exist_ok=True)
        _presolve(ctx, city, prefix)
        base = study.prepare_city_base(
            ctx.index, ctx.mapping, ctx.selection, city, ctx.budget, folder)
        _write_base(ctx, base, city, prefix, reader, tally)
        _screen(ctx, base, city, prefix, reader, tally, entry)
        _margin(ctx, base, city, prefix, reader, tally, entry)
    except study.StudyFailed as failure:
        entry["status"] = "failed"
        entry["detail"] = (bundle.safe_item(failure.stage),)
    except Exception as exc:  # noqa: BLE001 - recorded as the class only, never the text
        entry["status"] = "failed"
        entry["detail"] = (bundle.class_word(exc),)
    finally:
        if base is not None:
            study.cleanup_base(base)
        _remove_folder(folder)
    if entry["status"] == "failed":
        _write_failed_base(ctx, city, prefix, entry["detail"])
    return entry


def run(ctx):
    """The reference section; see the module docstring. Returns a session.SectionResult."""
    if ctx.index is None:
        # failed, not skipped: "skipped" means "--only did not ask for it", and an answer that
        # could not be produced is a failure (the network section reports the same way)
        ctx.results[SECTION] = collections.OrderedDict()
        return session.SectionResult("failed", ("no case index", ctx.index_stage or "internal"), {})
    tmp_root = os.path.join(ctx.work.path, "tmp_sav")
    os.makedirs(tmp_root, exist_ok=True)
    tally = {"outages": 0, "converged": 0, "margin_points": 0, "extended_reads_unavailable": 0}
    results = collections.OrderedDict()
    reader = _Reader(ctx)
    try:
        for city in constants.CITIES:
            results[city] = _run_city(ctx, reader, tally, tmp_root, city)
    finally:
        _remove_folder(tmp_root)
        ctx.results[SECTION] = results
    detail = []
    for entry in results.values():
        for word in tuple(entry["detail"]) + tuple(entry["notes"]):
            if word not in detail:
                detail.append(word)
    cities_ok = sum(1 for entry in results.values() if entry["status"] == "ok")
    counts = {
        "cities": len(results), "cities_ok": cities_ok, "outages": tally["outages"],
        "converged": tally["converged"], "not_converged": tally["outages"] - tally["converged"],
        "margin_points": tally["margin_points"],
        "extended_reads_unavailable": tally["extended_reads_unavailable"]}
    status = "ok" if cities_ok == len(results) else "failed"
    return session.SectionResult(status, tuple(detail), counts)
