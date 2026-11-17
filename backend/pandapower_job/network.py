"""
The pandapower network builder (pandapower-solver Phase 1, plan 01-06: NET-01).

`build_network(case)` turns a `raw.ParsedCase` into a pandapower network. PSS/E bus numbers are the
`net.bus` index (never a position), lines and transformers are named `from-to-ckt` with the circuit
id stripped of PSS/E's padding, loads, fixed shunts and machines are named `bus-id`, and every
out-of-service flag is copied. It builds from the parsed values only: pandapower's converter and its
bundled test networks are never used here (they classify branches differently and lose bus numbers).

Conventions, each verified against `pandapower.networks.case39()` to about 1e-15 pu in the research
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


def _machine_key(values):
    return "%d-%s" % (values["I"], values["ID"])


def _in_service(flag):
    return flag == 1


def _refuse(reason, found):
    """Raise BuildRefused when `found` (a list of (key, line)) is not empty."""
    if found:
        raise BuildRefused(reason, [key for key, _ in found], [line for _, line in found])


def _check(case, buses):
    """Every fail-closed rule, in the order of BUILD_REFUSAL_REASONS; returns the swing machine."""
    if not buses:
        raise BuildRefused("no_buses")
    swing_buses = [number for number, rec in buses.items() if rec.values["IDE"] == SWING_IDE]
    if len(swing_buses) != 1:
        raise BuildRefused("no_swing_bus", [str(number) for number in sorted(swing_buses)])
    swing_bus = swing_buses[0]
    at_swing = [rec for rec in case.sections["generator"]
                if rec.values["I"] == swing_bus and _in_service(rec.values["STAT"])]
    if len(at_swing) != 1:
        raise BuildRefused("swing_bus_machines", [_machine_key(rec.values) for rec in at_swing],
                           [rec.line for rec in at_swing])
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
