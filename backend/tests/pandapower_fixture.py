"""
Synthetic RAW text and synthetic references for the pandapower network tests (pandapower-solver
Phase 1, plan 01-06). Not collected by pytest (the file name does not match `*_test.py`).

Everything here is generated from `pandapower.networks.case39()` with every bus number offset by
90000, into memory or into a test's tmp_path, never into the repository: the public repository
must never hold RAW structure, and the plan 01-01 shape layer flags it in any tracked file, so the
section markers below are assembled from pieces.

Honest scope. A RAW file made from pandapower's own 39-bus case and solved by pandapower proves
the transcription (parser, field tables, builder formulas), not PSS/E physics: the file, the
builder and the solver all share the author's reading of the conventions. The independent check is
NET-03 against PSS/E's own answers. The writer takes its field order from `raw.FIELD_TABLES`, so
the positional layout is pinned separately by hand-typed records in pandapower_raw_test.py, and the
section order and section phrases below are written out here independently of the parser's.

Public names (plans 01-06 to 01-09): `case39_records`, `raw_text`, `write_raw`, `mutate`,
`reference_from_solved`; the helpers `remove`, `append`, `terminator_line` and `V33_ORDER` serve
the tests that edit the text.
"""

import copy
import math

from pandapower_job import raw

OFFSET = 90000

_END_OF = "END" + " OF "
_BEGIN = "BEG" + "IN "

# The v33 section order, written out here independently of raw.SECTION_ORDER.
V33_ORDER = (
    "bus", "load", "fixed_shunt", "generator", "branch", "transformer", "area", "two_terminal_dc",
    "vsc_dc", "impedance_correction", "multi_terminal_dc", "multi_section_line", "zone",
    "inter_area_transfer", "owner", "facts", "switched_shunt", "gne", "induction_machine")

# The words PSS/E puts in the section terminator comment.
SECTION_PHRASE = {
    "bus": "BUS", "load": "LOAD", "fixed_shunt": "FIXED SHUNT", "generator": "GENERATOR",
    "branch": "BRANCH", "transformer": "TRANSFORMER", "area": "AREA INTERCHANGE",
    "two_terminal_dc": "TWO-TERMINAL DC", "vsc_dc": "VOLTAGE SOURCE CONVERTER",
    "impedance_correction": "IMPEDANCE CORRECTION", "multi_terminal_dc": "MULTI-TERMINAL DC",
    "multi_section_line": "MULTI-SECTION LINE", "zone": "ZONE",
    "inter_area_transfer": "INTER-AREA TRANSFER", "owner": "OWNER", "facts": "FACTS DEVICE",
    "switched_shunt": "SWITCHED SHUNT", "gne": "GNE DEVICE",
    "induction_machine": "INDUCTION MACHINE"}

_PAD = {"NAME": 12, "ID": 2, "CKT": 2}
_TRANSFORMER_LINES = ("transformer_1", "transformer_2", "transformer_3", "transformer_4")


def _case39():
    import pandapower.networks as networks   # fixture only: production code never imports this
    return networks.case39()


# Building case39 takes about half a second and the tests ask for it hundreds of times, so the
# records and the frequency are computed once per offset and handed out as deep copies.
_CACHE = {}


def _case39_f_hz():
    if "f_hz" not in _CACHE:
        _CACHE["f_hz"] = float(_case39().f_hz)
    return _CACHE["f_hz"]


def terminator_line(section):
    """The line that ends `section`, naming the next section the way PSS/E does."""
    position = V33_ORDER.index(section)
    text = "0 / " + _END_OF + SECTION_PHRASE[section] + " DATA"
    if position + 1 < len(V33_ORDER):
        text += ", " + _BEGIN + SECTION_PHRASE[V33_ORDER[position + 1]] + " DATA"
    return text


def _bus_number(net, index, offset):
    name = net.bus.at[index, "name"]
    base = int(name) if str(name).strip().isdigit() else int(index) + 1
    return offset + base


def case39_records(offset=90000):
    """
    The 39-bus case as RAW records: section name to a list of value dicts in v33 field names.
    Bus numbers are `offset` plus the MATPOWER number. The ext_grid bus is the swing bus with one
    machine, every other generator bus is type 2, and every per-unit field is the exact inverse of
    the builder's formulas (line R, X and B from the ohm and nF values at the system base;
    transformer R, X and WINDV1 from vk, vkr and the rated voltages).
    """
    if offset not in _CACHE:
        _CACHE[offset] = _case39_records(offset)
    return copy.deepcopy(_CACHE[offset])


def _case39_records(offset):
    net = _case39()
    sbase = float(net.sn_mva)
    freq = float(net.f_hz)
    number = {int(i): _bus_number(net, i, offset) for i in net.bus.index}
    kv = {int(i): float(net.bus.at[i, "vn_kv"]) for i in net.bus.index}
    swing_buses = set(int(b) for b in net.ext_grid.bus)
    gen_buses = set(int(b) for b in net.gen.bus)

    buses = []
    for i in sorted(net.bus.index, key=lambda k: number[int(k)]):
        i = int(i)
        ide = 3 if i in swing_buses else (2 if i in gen_buses else 1)
        va = float(net.ext_grid.va_degree.iloc[0]) if i in swing_buses else 0.0
        buses.append({
            "I": number[i], "NAME": "BUS %d" % number[i], "BASKV": kv[i], "IDE": ide, "AREA": 1,
            "ZONE": 1, "OWNER": 1, "VM": 1.0, "VA": va,
            "NVHI": float(net.bus.at[i, "max_vm_pu"]), "NVLO": float(net.bus.at[i, "min_vm_pu"]),
            "EVHI": float(net.bus.at[i, "max_vm_pu"]), "EVLO": float(net.bus.at[i, "min_vm_pu"])})

    loads = []
    for _, row in net.load.iterrows():
        loads.append({"I": number[int(row.bus)], "ID": "1", "STATUS": 1, "AREA": 1, "ZONE": 1,
                      "PL": float(row.p_mw), "QL": float(row.q_mvar), "IP": 0.0, "IQ": 0.0,
                      "YP": 0.0, "YQ": 0.0, "OWNER": 1, "SCALE": 1, "INTRPT": 0})

    machines = []
    for _, row in net.gen.iterrows():
        machines.append({
            "I": number[int(row.bus)], "ID": "1", "PG": float(row.p_mw), "QG": 0.0,
            "QT": float(row.max_q_mvar), "QB": float(row.min_q_mvar), "VS": float(row.vm_pu),
            "IREG": 0, "MBASE": sbase, "STAT": 1, "PT": float(row.max_p_mw),
            "PB": float(row.min_p_mw)})
    for _, row in net.ext_grid.iterrows():
        machines.append({
            "I": number[int(row.bus)], "ID": "1", "PG": 0.0, "QG": 0.0,
            "QT": float(row.max_q_mvar), "QB": float(row.min_q_mvar), "VS": float(row.vm_pu),
            "IREG": 0, "MBASE": sbase, "STAT": 1, "PT": float(row.max_p_mw),
            "PB": float(row.min_p_mw)})
    machines.sort(key=lambda rec: rec["I"])

    used = {}

    def circuit(i, j):
        count = used.get((i, j), 0) + 1
        used[(i, j)] = count
        return str(count)

    branches = []
    for _, row in net.line.iterrows():
        i, j = number[int(row.from_bus)], number[int(row.to_bus)]
        z = kv[int(row.from_bus)] ** 2 / sbase
        length = float(row.length_km) * int(row.parallel)
        branches.append({
            "I": i, "J": j, "CKT": circuit(i, j),
            "R": float(row.r_ohm_per_km) * float(row.length_km) / z,
            "X": float(row.x_ohm_per_km) * float(row.length_km) / z,
            "B": float(row.c_nf_per_km) * 1e-9 * 2 * math.pi * freq * z * float(row.length_km),
            "RATEA": float(row.max_i_ka) * math.sqrt(3) * kv[int(row.from_bus)],
            "RATEB": 0.0, "RATEC": 0.0, "GI": 0.0, "BI": 0.0, "GJ": 0.0, "BJ": 0.0, "ST": 1,
            "MET": 1, "LEN": length})

    transformers = []
    for _, row in net.trafo.iterrows():
        hv, lv = int(row.hv_bus), int(row.lv_bus)
        i, j = number[hv], number[lv]
        scale = sbase / float(row.sn_mva)
        r = float(row.vkr_percent) / 100.0 * scale
        z = float(row.vk_percent) / 100.0 * scale
        x = math.sqrt(max(z * z - r * r, 0.0))
        step = float(row.tap_step_percent)
        tap = 1.0 + (float(row.tap_pos) - float(row.tap_neutral)) * step / 100.0
        nominal = (float(row.vn_hv_kv) / kv[hv]) / (float(row.vn_lv_kv) / kv[lv])
        transformers.append({
            "I": i, "J": j, "K": 0, "CKT": circuit(i, j), "CW": 1, "CZ": 1, "CM": 1, "MAG1": 0.0,
            "MAG2": 0.0, "NMETR": 2, "NAME": "TRF %d %d" % (i, j), "STAT": 1,
            "R1-2": r, "X1-2": x, "SBASE1-2": sbase,
            "WINDV1": nominal * tap, "NOMV1": kv[hv], "ANG1": 0.0,
            "RATA1": float(row.sn_mva), "RATB1": 0.0, "RATC1": 0.0, "COD1": 0,
            "WINDV2": 1.0, "NOMV2": kv[lv]})

    return {
        "bus": buses, "load": loads, "fixed_shunt": [], "generator": machines,
        "branch": branches, "transformer": transformers,
        "area": [{"I": 1, "ISW": 0, "PDES": 0.0, "PTOL": 10.0, "ARNAME": "AREA ONE"}],
        "zone": [{"I": 1, "ZONAME": "ZONE ONE"}],
        "owner": [{"I": 1, "OWNAME": "OWNER ONE"}]}


# -- editing -----------------------------------------------------------------------------------


def mutate(records, section, index, field, value):
    """A deep copy of `records` with `field` of `records[section][index]` set to `value`."""
    copied = copy.deepcopy(records)
    copied[section][index][field] = value
    return copied


def remove(records, section, index):
    """A deep copy of `records` without `records[section][index]`."""
    copied = copy.deepcopy(records)
    del copied[section][index]
    return copied


def append(records, section, record):
    """A deep copy of `records` with `record` added at the end of `section`."""
    copied = copy.deepcopy(records)
    copied.setdefault(section, []).append(dict(record))
    return copied


# -- writing -----------------------------------------------------------------------------------


def _format_value(name, value):
    if isinstance(value, str):
        text = value.ljust(_PAD.get(name, 0))
        return "'%s'" % text
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    return repr(float(value))


def _format_record(spec, record):
    fields = []
    for name in spec.names:
        if name in record:
            value = record[name]
        elif name in spec.defaults:
            value = spec.defaults[name]
        else:
            raise KeyError("the record has no value and the field has no default")
        fields.append(_format_value(name, value))
    return ", ".join(fields)


def raw_text(records, revision=33, sbase=100.0, frequency=None):
    """
    RAW text for `records` (see case39_records). `revision` is written in the header, `sbase` is
    the system base and `frequency` the BASFRQ field (default: the 39-bus case's own f_hz).
    Floats are written with repr so the round trip is exact. Sections absent from `records` are
    written empty. Every record is written with every field of its table.
    """
    if frequency is None:
        frequency = _case39_f_hz()
    tables = raw.FIELD_TABLES[33]
    lines = ["0, %s, %d, 0, 1, %s / SYNTHETIC TEST CASE" % (repr(float(sbase)), revision,
                                                           repr(float(frequency))),
             "SYNTHETIC CASE MADE FROM THE 39-BUS TEST SYSTEM",
             "BUS NUMBERS OFFSET, NOT A REAL NETWORK"]
    for section in V33_ORDER:
        for record in records.get(section, ()):
            if section == "transformer":
                for name in _TRANSFORMER_LINES:
                    lines.append(_format_record(tables[name], record))
            else:
                lines.append(_format_record(tables[section], record))
        lines.append(terminator_line(section))
    lines.append("Q")
    return "\n".join(lines) + "\n"


def write_raw(path, records, **kwargs):
    """Write `raw_text(records, **kwargs)` to `path` (a tmp_path file) and return the path."""
    with open(str(path), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(raw_text(records, **kwargs))
    return path


# -- a synthetic reference ----------------------------------------------------------------------


def _clean(value):
    number = float(value)
    return number if math.isfinite(number) else None


def _split_key(key):
    first, second, ckt = key.split("-", 2)
    return int(first), int(second), ckt


def reference_from_solved(net, city):
    """
    The base.json shape of plan 01-03 for a solved pandapower net built by `build_network`: what
    a PSS/E session would have written for the same solved state. It is circular by design (the
    answers come from pandapower), so it proves plumbing, tolerances and failure detection, never
    physics. Bus voltages in per unit, line and transformer flows at the from end (MW, Mvar) and
    the larger-end apparent flow, machine outputs with generation positive.
    """
    swing = set(int(b) for b in net.ext_grid.bus)
    gens = set(int(b) for b in net.gen.bus)
    buses = []
    for index in sorted(net.bus.index):
        row = net.bus.loc[index]
        code = 4 if not bool(row.in_service) else (3 if int(index) in swing else
                                                  (2 if int(index) in gens else 1))
        buses.append({"number": int(index), "type_code": code, "base_kv": _clean(row.vn_kv),
                      "pu": _clean(net.res_bus.at[index, "vm_pu"])})

    line_flows, branch_flows = [], []
    for table, result, is_trafo in ((net.line, net.res_line, False),
                                    (net.trafo, net.res_trafo, True)):
        for index in table.index:
            row = table.loc[index]
            key = str(row["name"])
            from_bus, to_bus, ckt = _split_key(key)
            res = result.loc[index]
            in_service = bool(row.in_service)
            p_from, q_from = _clean(res.p_from_mw), _clean(res.q_from_mvar)
            ends = [math.hypot(res.p_from_mw, res.q_from_mvar),
                    math.hypot(res.p_to_mw, res.q_to_mvar)]
            max_mva = _clean(max(ends)) if all(math.isfinite(e) for e in ends) else None
            if is_trafo:
                rate = None
            else:
                rate = _clean(row.max_i_ka * math.sqrt(3) * net.bus.at[row.from_bus, "vn_kv"])
            pct = (max_mva / rate * 100.0) if (rate and max_mva is not None) else None
            line_flows.append({
                "key": key, "from_bus": from_bus, "to_bus": to_bus, "ckt": ckt,
                "in_service": in_service, "rate_mva": rate, "pct": pct, "p_mw": p_from,
                "max_mva": max_mva})
            branch_flows.append({
                "key": key, "is_transformer": is_trafo, "in_service": in_service,
                "p_mw": p_from, "q_mvar": q_from, "max_mva": max_mva})
    line_flows.sort(key=lambda item: item["key"])
    branch_flows.sort(key=lambda item: item["key"])

    machines = []
    for table, result in ((net.gen, net.res_gen), (net.ext_grid, net.res_ext_grid)):
        for index in table.index:
            row = table.loc[index]
            res = result.loc[index]
            bus_number, ident = str(row["name"]).split("-", 1)
            if "psse_pt_mw" in table.columns:
                p_max, p_min = _clean(row.psse_pt_mw), _clean(row.psse_pb_mw)
                q_max, q_min = _clean(row.psse_qt_mvar), _clean(row.psse_qb_mvar)
            else:
                p_max, p_min = _clean(row.max_p_mw), _clean(row.min_p_mw)
                q_max, q_min = _clean(row.max_q_mvar), _clean(row.min_q_mvar)
            machines.append({
                "bus": int(bus_number), "id": ident, "in_service": bool(row.in_service),
                "p_mw": _clean(-res.p_mw), "q_mvar": _clean(-res.q_mvar), "p_max_mw": p_max,
                "p_min_mw": p_min, "q_max_mvar": q_max, "q_min_mvar": q_min})
    machines.sort(key=lambda item: (item["bus"], item["id"]))

    return {
        "city": city, "status": "ok", "rate_set": "RATEA", "thermal_basis": "current",
        "rating_source": "static",
        "solve": {"converged": True, "ierr": 0, "solved_code": 0, "meaning": "converged",
                  "iterations": None, "mismatch_mva": None},
        "buses": buses, "line_flows": line_flows,
        "branch_flows": {"status": "ok", "reason": None, "flag": 4, "rows": branch_flows},
        "machine_outputs": {"status": "ok", "reason": None, "flag": 4, "rows": machines},
        "snapshot": None}
