"""
The pandapower network builder (pandapower-solver Phase 1, plan 01-06: NET-01).

`build_network(case)` turns a `raw.ParsedCase` into a pandapower network. PSS/E bus numbers are the
`net.bus` index (never a position), lines and transformers are named `from-to-ckt` with the circuit
id stripped of PSS/E's padding, loads, fixed shunts and machines are named `bus-id`, and every
out-of-service flag is copied. It builds from the parsed values only: pandapower's converter and its
bundled test networks are never used here (they classify branches differently and lose bus numbers).

Conventions, each verified against pandapower's bundled 39-bus case to about 1e-15 pu in the research
for this phase:

- Per-unit R, X and B are on the system base. A line is built with `length_km=1` and ohms at the
  from bus's kV, so the per-unit model is exactly the file's; B becomes nF at the case frequency.
- A two-winding transformer has `hv_bus=I`, `lv_bus=J` whatever the kV, `vn_hv_kv = WINDV1 * kV_I`,
  `vn_lv_kv = kV_J`, `sn_mva` equal to the system base, so `vk_percent = 100 * |R + jX|` and
  `vkr_percent = 100 * R`, and no magnetizing branch. That PSS/E's convention (ratio at winding 1,
  impedance on the winding 2 side) equals MATPOWER's for winding codes 1 is assumed until NET-03
  passes against PSS/E's own answers (assumption A4).
- A fixed shunt's BL is positive for a capacitor and pandapower's shunt q_mvar is positive for an
  inductor, so `q_mvar = -BL` (and `p_mw = GL`).
- A transformer with local voltage control (COD1 1) is built at its initial tap WINDV1, the same
  assumption as for the switched shunt (A-tap); other control modes are refused.
- A switched shunt becomes a plain shunt at its initial setting, `q_mvar = -BINIT` (BINIT is Mvar at
  1.0 pu, positive for a capacitor). That equals PSS/E's answer only while PSS/E leaves the steps
  where they start, whatever the control mode (MODSW), so the choice is an explicit assumption
  (A-shunt, owner's choice 2026-11-19) that the base-case comparison against PSS/E's own answers
  tests; if it fails there, the upgrade is step control, never a tuned value. A switched shunt
  that regulates a remote bus is refused.
- The swing machine becomes the `ext_grid`; its RAW limits and output ride along in the extra
  columns `psse_pg_mw`, `psse_qg_mvar`, `psse_pt_mw`, `psse_pb_mw`, `psse_qt_mvar` and
  `psse_qb_mvar`. Machines at voltage-controlled buses become `gen` rows.

Fail closed: any feature the builder cannot reproduce exactly raises `BuildRefused` with one reason
from `BUILD_REFUSAL_REASONS`, after every offending element has been collected, so `count` and
`elements` are complete. The message holds the reason, the count and the first line number only; the
element keys live on the `elements` attribute for private reports and never in `str(error)`.

Pure: the parsed case is not changed and no module-level state is kept, so building twice gives
equal tables.
"""

import math

import pandapower as pp

from pandapower_job import raw

BUILD_REFUSAL_REASONS = (
    "no_buses", "no_swing_bus", "swing_bus_machines", "pv_bus_without_machine",
    "machine_at_load_bus", "conflicting_setpoints", "load_not_constant_power",
    "line_shunt_terminals", "remote_regulation", "transformer_winding_codes",
    "magnetizing_branch", "controlling_transformer", "phase_shift", "windv2_not_one",
    "zero_rating", "unknown_bus", "duplicate_name")

SWING_IDE = 3
OUT_OF_SERVICE_IDE = 4
VOLTAGE_CONTROLLED_IDE = 2
LOAD_IDE = 1


class BuildRefused(ValueError):
    """
    The case holds something the builder cannot reproduce. `reason` is one of
    BUILD_REFUSAL_REASONS, `count` the number of offending elements and `elements` their keys
    (for private reports; never in `str(error)`), `lines` their RAW line numbers.
    """

    def __init__(self, reason, elements=(), lines=()):
        self.reason = reason
        self.elements = tuple(elements)
        self.lines = tuple(lines)
        self.count = len(self.elements)
        text = "network refused: %s (%d element(s))" % (reason, self.count)
        if self.lines:
            text += " (first at line %d)" % min(self.lines)
        ValueError.__init__(self, text)


def _fixed_tap_ok(values):
    """
    True for a transformer with no control (COD1 0) or with local voltage control (COD1 1, the
    controlled bus is one of its own terminals or unset), which is built at its initial tap
    WINDV1 (assumption A-tap, the same owner's choice as A-shunt, 2026-11-19: the base-case
    comparison against PSS/E tests it; a failure upgrades to tap control, never a tuned value).
    Every other control mode, and a remote controlled bus, is refused.
    """
    code = values["COD1"]
    if code == 0:
        return True
    return code == 1 and abs(values["CONT1"]) in (0, values["I"], values["J"])


def _machine_key(values):
    return "%d-%s" % (values["I"], values["ID"])


def _branch_key(rec):
    values = rec.values
    return raw.branch_key(values["I"], values["J"], values["CKT"])


def _in_service(flag):
    return flag == 1


def _refuse(reason, found):
    """Raise BuildRefused when `found` (a list of (key, line)) is not empty."""
    if found:
        raise BuildRefused(reason, [key for key, _ in found], [line for _, line in found])


def _duplicates(items):
    """(key, line) of every key that occurs more than once in `items` [(key, line)], once each."""
    seen, repeated = set(), {}
    for key, line in items:
        if key in seen and key not in repeated:
            repeated[key] = line
        seen.add(key)
    return sorted(repeated.items())


def _check(case, buses):
    """Every fail-closed rule, in the order of BUILD_REFUSAL_REASONS; returns the swing machine."""
    sections = case.sections
    if not buses:
        raise BuildRefused("no_buses")
    swing_buses = [number for number, rec in buses.items() if rec.values["IDE"] == SWING_IDE]
    if len(swing_buses) != 1:
        raise BuildRefused("no_swing_bus", [str(number) for number in sorted(swing_buses)])
    swing_bus = swing_buses[0]
    machines = sections["generator"]
    live = [rec for rec in machines if _in_service(rec.values["STAT"])]
    at_swing = [rec for rec in live if rec.values["I"] == swing_bus]
    if len(at_swing) != 1:
        raise BuildRefused("swing_bus_machines", [_machine_key(rec.values) for rec in at_swing],
                           [rec.line for rec in at_swing])

    def ide(number):
        return buses[number].values["IDE"] if number in buses else None

    controlled = {rec.values["I"] for rec in live}
    _refuse("pv_bus_without_machine",
            [(str(number), rec.line) for number, rec in sorted(buses.items())
             if rec.values["IDE"] == VOLTAGE_CONTROLLED_IDE and number not in controlled])
    _refuse("machine_at_load_bus",
            [(_machine_key(rec.values), rec.line) for rec in live
             if ide(rec.values["I"]) == LOAD_IDE])
    by_bus = {}
    for rec in live:
        by_bus.setdefault(rec.values["I"], []).append(rec)
    _refuse("conflicting_setpoints",
            [(str(number), group[0].line) for number, group in sorted(by_bus.items())
             if ide(number) == VOLTAGE_CONTROLLED_IDE
             and len({rec.values["VS"] for rec in group}) > 1])
    _refuse("load_not_constant_power",
            [(_machine_key(rec.values), rec.line) for rec in sections["load"]
             if any(rec.values[name] != 0.0 for name in ("IP", "IQ", "YP", "YQ"))])
    _refuse("line_shunt_terminals",
            [(_branch_key(rec), rec.line) for rec in sections["branch"]
             if any(rec.values[name] != 0.0 for name in ("GI", "BI", "GJ", "BJ"))])
    _refuse("remote_regulation",
            [(_machine_key(rec.values), rec.line) for rec in machines
             if rec.values["IREG"] not in (0, rec.values["I"])])
    _refuse("remote_regulation",
            [(_machine_key(dict(rec.values, ID="sw")), rec.line) for rec in sections["switched_shunt"]
             if rec.values["SWREM"] not in (0, rec.values["I"])])
    transformers = sections["transformer"]
    _refuse("transformer_winding_codes",
            [(_branch_key(rec), rec.line) for rec in transformers
             if any(rec.values[name] != 1 for name in ("CW", "CZ", "CM"))])
    _refuse("magnetizing_branch",
            [(_branch_key(rec), rec.line) for rec in transformers
             if rec.values["MAG1"] != 0.0 or rec.values["MAG2"] != 0.0])
    _refuse("controlling_transformer",
            [(_branch_key(rec), rec.line) for rec in transformers
             if not _fixed_tap_ok(rec.values)])
    _refuse("phase_shift",
            [(_branch_key(rec), rec.line) for rec in transformers if rec.values["ANG1"] != 0.0])
    _refuse("windv2_not_one",
            [(_branch_key(rec), rec.line) for rec in transformers
             if rec.values["WINDV2"] != 1.0])
    _refuse("zero_rating",
            [(_branch_key(rec), rec.line) for rec in sections["branch"]
             if rec.values["RATEA"] <= 0.0])
    unknown = []
    for name in ("load", "fixed_shunt", "switched_shunt", "generator"):
        for rec in sections[name]:
            if rec.values["I"] not in buses:
                unknown.append((_machine_key(rec.values), rec.line))
    for name in ("branch", "transformer"):
        for rec in sections[name]:
            if rec.values["I"] not in buses or rec.values["J"] not in buses:
                unknown.append((_branch_key(rec), rec.line))
    _refuse("unknown_bus", unknown)
    names = [(_branch_key(rec), rec.line) for rec in sections["branch"] + transformers]
    _refuse("duplicate_name", _duplicates(names))
    for name in ("load", "fixed_shunt", "generator"):
        _refuse("duplicate_name",
                _duplicates([(_machine_key(rec.values), rec.line) for rec in sections[name]]))
    _refuse("duplicate_name",
            _duplicates([(str(rec.values["I"]), rec.line) for rec in sections["switched_shunt"]]))
    _refuse("duplicate_name",
            _duplicates([(str(rec.values["I"]), rec.line) for rec in sections["bus"]]))
    return at_swing[0]


def build_network(case):
    """The pandapower network of a parsed RAW case (see the module docstring)."""
    buses = {}
    for rec in case.sections["bus"]:
        buses.setdefault(rec.values["I"], rec)
    swing = _check(case, buses)
    kv = {number: rec.values["BASKV"] for number, rec in buses.items()}
    sbase = case.sbase_mva
    frequency = case.base_frequency_hz

    net = pp.create_empty_network(f_hz=frequency, sn_mva=sbase)
    for number in sorted(buses):
        v = buses[number].values
        pp.create_bus(net, vn_kv=v["BASKV"], index=number, name=str(number),
                      in_service=v["IDE"] != OUT_OF_SERVICE_IDE, max_vm_pu=v["NVHI"],
                      min_vm_pu=v["NVLO"])

    for rec in case.sections["branch"]:
        v = rec.values
        z_base = kv[v["I"]] ** 2 / sbase
        pp.create_line_from_parameters(
            net, v["I"], v["J"], length_km=1.0, r_ohm_per_km=v["R"] * z_base,
            x_ohm_per_km=v["X"] * z_base,
            c_nf_per_km=v["B"] / (z_base * 2.0 * math.pi * frequency) * 1e9,
            max_i_ka=v["RATEA"] / (math.sqrt(3.0) * kv[v["I"]]),
            name=raw.branch_key(v["I"], v["J"], v["CKT"]), in_service=_in_service(v["ST"]))

    for rec in case.sections["transformer"]:
        v = rec.values
        pp.create_transformer_from_parameters(
            net, hv_bus=v["I"], lv_bus=v["J"], sn_mva=sbase, vn_hv_kv=v["WINDV1"] * kv[v["I"]],
            vn_lv_kv=kv[v["J"]], vk_percent=100.0 * math.hypot(v["R1-2"], v["X1-2"]),
            vkr_percent=100.0 * v["R1-2"], pfe_kw=0.0, i0_percent=0.0, shift_degree=0.0,
            name=raw.branch_key(v["I"], v["J"], v["CKT"]), in_service=_in_service(v["STAT"]))

    for rec in case.sections["load"]:
        v = rec.values
        pp.create_load(net, v["I"], p_mw=v["PL"], q_mvar=v["QL"],
                       name="%d-%s" % (v["I"], v["ID"]), in_service=_in_service(v["STATUS"]))

    for rec in case.sections["fixed_shunt"]:
        v = rec.values
        pp.create_shunt(net, v["I"], q_mvar=-v["BL"], p_mw=v["GL"], vn_kv=kv[v["I"]],
                        name="%d-%s" % (v["I"], v["ID"]), in_service=_in_service(v["STATUS"]))

    for rec in case.sections["switched_shunt"]:
        v = rec.values
        pp.create_shunt(net, v["I"], q_mvar=-v["BINIT"], p_mw=0.0, vn_kv=kv[v["I"]],
                        name="%d-sw" % v["I"], in_service=_in_service(v["STAT"]))

    for rec in case.sections["generator"]:
        if rec is swing:
            continue
        v = rec.values
        pp.create_gen(net, v["I"], p_mw=v["PG"], vm_pu=v["VS"], max_q_mvar=v["QT"],
                      min_q_mvar=v["QB"], max_p_mw=v["PT"], min_p_mw=v["PB"],
                      name=_machine_key(v), in_service=_in_service(v["STAT"]))

    v = swing.values
    pp.create_ext_grid(net, v["I"], vm_pu=v["VS"], va_degree=buses[v["I"]].values["VA"],
                       name=_machine_key(v), psse_pg_mw=v["PG"], psse_qg_mvar=v["QG"],
                       psse_pt_mw=v["PT"], psse_pb_mw=v["PB"], psse_qt_mvar=v["QT"],
                       psse_qb_mvar=v["QB"])
    return net
