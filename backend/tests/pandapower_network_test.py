"""
Tests for the pandapower network builder (pandapower-solver Phase 1, plan 01-06: NET-01).

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_fixture`), written into tmp_path only; no synthetic
file is committed. A pandapower solve of a pandapower-derived file proves transcription (the
parser's field tables and the builder's formulas), not PSS/E physics: the file, the builder and
the solver share one reading of the conventions. NET-03, against PSS/E's own answers, is the
independent check.

Failure messages are counts only.
"""

import copy
import os
import re

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower.networks as pandapower_networks  # noqa: E402

import pandapower_fixture as fixture  # noqa: E402
from pandapower_job import network, raw  # noqa: E402

OFFSET = fixture.OFFSET


def _parse(records, **kwargs):
    return raw.parse_raw(fixture.raw_text(records, **kwargs).encode("utf-8"))


def test_tracer_synthetic_raw_parses_builds_and_solves_like_case39(tmp_path):
    records = fixture.case39_records(OFFSET)
    path = fixture.write_raw(tmp_path / "synthetic.raw", records)
    case = raw.parse_raw(path.read_bytes())

    assert case.revision == 33
    counts = {name: len(items) for name, items in case.sections.items()}
    assert counts["bus"] == 39 and counts["load"] == 21 and counts["generator"] == 10
    assert counts["branch"] == 35 and counts["transformer"] == 11 and counts["area"] == 1
    unsupported = [name for name in raw.SECTION_ORDER[33] if name not in raw.SUPPORTED_SECTIONS]
    assert unsupported and all(counts[name] == 0 for name in unsupported)

    net = network.build_network(case)
    reference = pandapower_networks.case39()
    pandapower.runpp(reference)
    pandapower.runpp(net)
    assert net.converged and reference.converged

    # Voltage magnitudes and angles at every bus, matched by bus number.
    names = {int(reference.bus.at[i, "name"]): i for i in reference.bus.index}
    worst_vm = worst_va = 0.0
    for matpower_number, ref_index in names.items():
        built = OFFSET + matpower_number
        worst_vm = max(worst_vm, abs(net.res_bus.at[built, "vm_pu"]
                                     - reference.res_bus.at[ref_index, "vm_pu"]))
        worst_va = max(worst_va, abs(net.res_bus.at[built, "va_degree"]
                                     - reference.res_bus.at[ref_index, "va_degree"]))
    assert len(names) == 39
    assert worst_vm < 1e-9, "largest voltage magnitude difference is above 1e-9 pu"
    assert worst_va < 1e-7, "largest voltage angle difference is above 1e-7 degrees"

    # PSS/E numbers are the bus index and no index equals its position.
    assert list(net.bus.index) == sorted(OFFSET + n for n in names)
    assert all(index != position for position, index in enumerate(net.bus.index))

    # Names are the RAW keys and unique across both branch tables.
    expected = ([raw.branch_key(r.values["I"], r.values["J"], r.values["CKT"])
                 for r in case.sections["branch"]]
                + [raw.branch_key(r.values["I"], r.values["J"], r.values["CKT"])
                   for r in case.sections["transformer"]])
    assert list(net.line.name) + list(net.trafo.name) == expected
    assert len(set(expected)) == len(expected) == 46


# -- the builder fails closed -----------------------------------------------------------------


def _records():
    return fixture.case39_records(OFFSET)


def _first(records, section, **where):
    """The index of the first record of `section` whose fields equal `where`."""
    for index, record in enumerate(records[section]):
        if all(record[name] == value for name, value in where.items()):
            return index
    raise AssertionError("no such record")


def _key(record):
    return raw.branch_key(record["I"], record["J"], record["CKT"])


def _machine_key(record):
    return "%d-%s" % (record["I"], record["ID"])


def _refusal_cases():
    """(id, records, reason, expected element keys) for every reason a parsed file can reach."""
    base = _records()
    swing_bus = next(r["I"] for r in base["bus"] if r["IDE"] == 3)
    swing_machine = _first(base, "generator", I=swing_bus)
    pv_machine = next(i for i, r in enumerate(base["generator"]) if r["I"] != swing_bus)
    pv_bus = base["generator"][pv_machine]["I"]
    pv_bus_index = _first(base, "bus", I=pv_bus)
    swing_bus_index = _first(base, "bus", I=swing_bus)
    other_bus = next(r["I"] for r in base["bus"] if r["IDE"] == 1)
    cases = []

    def add(name, records, reason, keys):
        cases.append(pytest.param(records, reason, sorted(keys), id=name))

    add("no_buses", {}, "no_buses", [])
    add("no_swing_bus", fixture.mutate(base, "bus", swing_bus_index, "IDE", 2), "no_swing_bus", [])
    two_swings = fixture.mutate(base, "bus", pv_bus_index, "IDE", 3)
    add("two_swing_buses", two_swings, "no_swing_bus", [str(swing_bus), str(pv_bus)])

    doubled = fixture.append(base, "generator", dict(base["generator"][swing_machine], ID="2"))
    add("two_machines_at_the_swing_bus", doubled, "swing_bus_machines",
        ["%d-1" % swing_bus, "%d-2" % swing_bus])
    add("swing_machine_removed", fixture.remove(base, "generator", swing_machine),
        "swing_bus_machines", [])
    add("swing_machine_out_of_service",
        fixture.mutate(base, "generator", swing_machine, "STAT", 0), "swing_bus_machines", [])

    add("type_2_bus_machine_out_of_service",
        fixture.mutate(base, "generator", pv_machine, "STAT", 0), "pv_bus_without_machine",
        [str(pv_bus)])
    add("machine_at_a_type_1_bus", fixture.mutate(base, "bus", pv_bus_index, "IDE", 1),
        "machine_at_load_bus", [_machine_key(base["generator"][pv_machine])])
    rival = dict(base["generator"][pv_machine], ID="2",
                 VS=base["generator"][pv_machine]["VS"] + 0.01)
    add("two_machines_with_different_setpoints", fixture.append(base, "generator", rival),
        "conflicting_setpoints", [str(pv_bus)])

    for field in ("IP", "IQ", "YP", "YQ"):
        add("load_with_%s" % field.lower(), fixture.mutate(base, "load", 0, field, 5.0),
            "load_not_constant_power", [_machine_key(base["load"][0])])
    two_loads = fixture.mutate(fixture.mutate(base, "load", 0, "IP", 5.0), "load", 1, "YQ", -2.0)
    add("two_loads_with_other_than_constant_power", two_loads, "load_not_constant_power",
        [_machine_key(base["load"][0]), _machine_key(base["load"][1])])
    for field in ("GI", "BI", "GJ", "BJ"):
        add("branch_with_%s" % field.lower(), fixture.mutate(base, "branch", 2, field, 0.01),
            "line_shunt_terminals", [_key(base["branch"][2])])
    add("machine_regulating_another_bus",
        fixture.mutate(base, "generator", pv_machine, "IREG", other_bus), "remote_regulation",
        [_machine_key(base["generator"][pv_machine])])
    shunt_bus = base["load"][0]["I"]
    continuous = dict(base, switched_shunt=[dict(
        {"I": shunt_bus, "MODSW": 2, "ADJM": 0, "STAT": 1, "VSWHI": 1.05, "VSWLO": 0.95,
         "SWREM": 0, "RMPCT": 100.0, "RMIDNT": "", "BINIT": 0.0},
        **dict([("N%d" % n, 0) for n in range(1, 9)] + [("B%d" % n, 0.0) for n in range(1, 9)]))])
    add("continuous_control_switched_shunt", continuous, "switched_shunt_control",
        ["%d-sw" % shunt_bus])
    for field in ("CW", "CZ", "CM"):
        add("transformer_with_%s_2" % field.lower(),
            fixture.mutate(base, "transformer", 1, field, 2), "transformer_winding_codes",
            [_key(base["transformer"][1])])
    for field in ("MAG1", "MAG2"):
        add("transformer_with_%s" % field.lower(),
            fixture.mutate(base, "transformer", 1, field, 0.001), "magnetizing_branch",
            [_key(base["transformer"][1])])
    add("controlling_transformer", fixture.mutate(base, "transformer", 1, "COD1", 2),
        "controlling_transformer", [_key(base["transformer"][1])])
    add("transformer_controlling_a_remote_bus",
        fixture.mutate(fixture.mutate(base, "transformer", 1, "COD1", 1), "transformer", 1,
                       "CONT1", base["bus"][0]["I"] + 1000),
        "controlling_transformer", [_key(base["transformer"][1])])
    add("phase_shifting_transformer", fixture.mutate(base, "transformer", 1, "ANG1", 30.0),
        "phase_shift", [_key(base["transformer"][1])])
    add("windv2_not_one", fixture.mutate(base, "transformer", 1, "WINDV2", 1.05),
        "windv2_not_one", [_key(base["transformer"][1])])
    add("line_with_a_zero_rating", fixture.mutate(base, "branch", 2, "RATEA", 0.0),
        "zero_rating", [_key(base["branch"][2])])
    ghost = OFFSET + 5000
    add("branch_names_a_missing_bus", fixture.mutate(base, "branch", 2, "J", ghost),
        "unknown_bus", [raw.branch_key(base["branch"][2]["I"], ghost, base["branch"][2]["CKT"])])
    add("load_at_a_missing_bus", fixture.mutate(base, "load", 0, "I", ghost), "unknown_bus",
        ["%d-1" % ghost])
    return cases


@pytest.mark.parametrize("records,reason,keys", _refusal_cases())
def test_builder_refuses_each_unsupported_feature(records, reason, keys):
    case = _parse(records)
    with pytest.raises(network.BuildRefused) as caught:
        network.build_network(case)
    error = caught.value
    assert error.reason == reason
    assert error.count == len(keys)
    assert sorted(error.elements) == keys


def test_every_build_reason_is_exercised():
    seen = set(case.values[1] for case in _refusal_cases()) | {"duplicate_name"}
    assert seen == set(network.BUILD_REFUSAL_REASONS)


def test_build_refusal_messages_hold_no_key():
    shape = re.compile(r"^network refused: [a-z0-9_]+ \([0-9]+ element\(s\)\)"
                       r"( \(first at line [0-9]+\))?$")
    for param in _refusal_cases():
        records, reason, keys = param.values
        with pytest.raises(network.BuildRefused) as caught:
            network.build_network(_parse(records))
        message = str(caught.value)
        assert shape.match(message), "a message holds more than the reason, count and a line"
        assert re.search(r"[0-9]{4}", message) is None, "a bus number is in the message"
        for key in keys:
            assert key not in message


def test_duplicate_names_from_a_hand_made_case_are_refused():
    case = _parse(_records())
    lines, trafos = case.sections["branch"], case.sections["transformer"]
    buses, loads = case.sections["bus"], case.sections["load"]

    def refused(**sections):
        edited = case._replace(sections=dict(case.sections, **sections))
        with pytest.raises(network.BuildRefused) as caught:
            network.build_network(edited)
        assert caught.value.reason == "duplicate_name"
        return caught.value

    twice = refused(branch=lines + (lines[0],))
    values = lines[0].values
    assert twice.elements == (raw.branch_key(values["I"], values["J"], values["CKT"]),)
    clash = trafos[0]._replace(values=dict(trafos[0].values, I=values["I"], J=values["J"],
                                           CKT=values["CKT"]))
    assert refused(transformer=(clash,) + trafos[1:]).count == 1
    assert refused(bus=buses + (buses[0],)).count == 1
    assert refused(load=loads + (loads[0],)).count == 1


def test_the_first_rule_in_the_documented_order_wins():
    records = fixture.mutate(_records(), "branch", 2, "RATEA", 0.0)
    records = fixture.mutate(records, "transformer", 1, "COD1", 1)
    records = fixture.mutate(records, "load", 0, "IP", 5.0)
    with pytest.raises(network.BuildRefused) as caught:
        network.build_network(_parse(records))
    assert caught.value.reason == "load_not_constant_power"
    order = network.BUILD_REFUSAL_REASONS
    assert (order.index("load_not_constant_power") < order.index("controlling_transformer")
            < order.index("zero_rating"))


def test_empty_cases_and_empty_sections():
    empty = raw.parse_raw(fixture.raw_text({}))
    with pytest.raises(network.BuildRefused) as caught:
        network.build_network(empty)
    assert caught.value.reason == "no_buses" and caught.value.count == 0

    records = _records()
    assert records["fixed_shunt"] == []
    net = network.build_network(_parse(records))
    assert len(net.shunt) == 0 and len(net.load) == 21

    bare = dict(records, load=[])
    assert len(network.build_network(_parse(bare)).load) == 0


def test_names_and_ext_grid_columns():
    records = _records()
    case = _parse(records)
    net = network.build_network(case)
    line_keys = [_key(r) for r in records["branch"]]
    trafo_keys = [_key(r) for r in records["transformer"]]
    assert list(net.line.name) == line_keys and list(net.trafo.name) == trafo_keys
    assert len(set(line_keys) | set(trafo_keys)) == len(line_keys) + len(trafo_keys)
    assert list(net.load.name) == [_machine_key(r) for r in records["load"]]
    swing_bus = next(r["I"] for r in records["bus"] if r["IDE"] == 3)
    gens = [r for r in records["generator"] if r["I"] != swing_bus]
    assert list(net.gen.name) == [_machine_key(r) for r in gens]
    assert list(net.bus.name) == [str(r["I"]) for r in records["bus"]]
    assert len(net.ext_grid) == 1
    swing = next(r for r in records["generator"] if r["I"] == swing_bus)
    row = net.ext_grid.iloc[0]
    assert row["name"] == _machine_key(swing) and int(row["bus"]) == swing_bus
    assert row["psse_pg_mw"] == swing["PG"] and row["psse_qg_mvar"] == swing["QG"]
    assert row["psse_pt_mw"] == swing["PT"] and row["psse_pb_mw"] == swing["PB"]
    assert row["psse_qt_mvar"] == swing["QT"] and row["psse_qb_mvar"] == swing["QB"]
    assert row["vm_pu"] == swing["VS"]
    first = records["bus"][0]
    assert net.bus.at[first["I"], "vn_kv"] == first["BASKV"]
    assert net.bus.at[first["I"], "max_vm_pu"] == first["NVHI"]
    assert net.bus.at[first["I"], "min_vm_pu"] == first["NVLO"]
    line = records["branch"][0]
    assert net.line.at[0, "max_i_ka"] == pytest.approx(line["RATEA"] / (3 ** 0.5 * 345.0))
    assert net.line.at[0, "length_km"] == 1.0


def test_out_of_service_flags_are_copied():
    records = _records()
    swing_bus = next(r["I"] for r in records["bus"] if r["IDE"] == 3)
    pv = next(r for r in records["generator"] if r["I"] != swing_bus)
    records["fixed_shunt"] = [{"I": records["load"][0]["I"], "ID": "1", "STATUS": 0,
                               "GL": 0.0, "BL": 100.0}]
    records = fixture.mutate(records, "bus", 0, "IDE", 4)
    records = fixture.mutate(records, "branch", 3, "ST", 0)
    records = fixture.mutate(records, "transformer", 2, "STAT", 0)
    records = fixture.mutate(records, "load", 4, "STATUS", 0)
    records = fixture.append(records, "generator", dict(pv, ID="2", STAT=0))
    net = network.build_network(_parse(records))
    assert list(net.bus.in_service).count(False) == 1 and not net.bus.in_service.iloc[0]
    assert list(net.line.in_service).count(False) == 1 and not net.line.in_service.iloc[3]
    assert list(net.trafo.in_service).count(False) == 1 and not net.trafo.in_service.iloc[2]
    assert list(net.load.in_service).count(False) == 1 and not net.load.in_service.iloc[4]
    assert list(net.shunt.in_service) == [False]
    assert list(net.gen.in_service).count(False) == 1
    assert not net.gen.in_service[net.gen.name == "%d-2" % pv["I"]].iloc[0]
    assert bool(net.ext_grid.in_service.iloc[0])


def test_fixed_shunt_sign():
    records = _records()
    bus = records["load"][0]["I"]
    assert next(r for r in records["bus"] if r["I"] == bus)["IDE"] == 1
    plain = network.build_network(_parse(records))
    capacitor = dict(records)
    capacitor["fixed_shunt"] = [{"I": bus, "ID": "1", "STATUS": 1, "GL": 5.0, "BL": 100.0}]
    shunted = network.build_network(_parse(capacitor))
    pandapower.runpp(plain)
    pandapower.runpp(shunted)
    assert shunted.res_bus.at[bus, "vm_pu"] > plain.res_bus.at[bus, "vm_pu"]
    assert shunted.res_shunt.at[0, "q_mvar"] < 0.0, "a positive BL must inject"
    assert shunted.res_shunt.at[0, "q_mvar"] == pytest.approx(
        -100.0 * shunted.res_bus.at[bus, "vm_pu"] ** 2, rel=1e-9)
    assert shunted.res_shunt.at[0, "p_mw"] == pytest.approx(
        5.0 * shunted.res_bus.at[bus, "vm_pu"] ** 2, rel=1e-9)


def _with_switched_shunt(records, **changes):
    bus = records["load"][0]["I"]
    shunt = dict({"I": bus, "MODSW": 1, "ADJM": 0, "STAT": 1, "VSWHI": 1.05, "VSWLO": 0.95,
                  "SWREM": 0, "RMPCT": 100.0, "RMIDNT": "", "BINIT": 100.0, "N1": 4, "B1": 25.0},
                 **changes)
    for n in range(1, 9):
        shunt.setdefault("N%d" % n, 0)
        shunt.setdefault("B%d" % n, 0.0)
    return dict(records, switched_shunt=[shunt]), bus


def test_switched_shunt_is_a_fixed_shunt_at_its_initial_setting():
    records = _records()
    plain = network.build_network(_parse(records))
    switched_records, bus = _with_switched_shunt(records)
    shunted = network.build_network(_parse(switched_records))
    assert list(shunted.shunt.name) == ["%d-sw" % bus] and shunted.shunt.at[0, "q_mvar"] == -100.0
    assert shunted.shunt.at[0, "p_mw"] == 0.0 and bool(shunted.shunt.at[0, "in_service"])
    pandapower.runpp(plain)
    pandapower.runpp(shunted)
    assert shunted.res_bus.at[bus, "vm_pu"] > plain.res_bus.at[bus, "vm_pu"]
    assert shunted.res_shunt.at[0, "q_mvar"] == pytest.approx(
        -100.0 * shunted.res_bus.at[bus, "vm_pu"] ** 2, rel=1e-9)
    # locked and discrete control both start at the initial setting
    for mode in (0, 1):
        again, _ = _with_switched_shunt(records, MODSW=mode)
        assert network.build_network(_parse(again)).shunt.at[0, "q_mvar"] == -100.0


def test_a_discrete_control_shunt_carries_its_band_and_levels_and_a_locked_one_does_not():
    records = _records()
    stepped, _ = _with_switched_shunt(records)
    row = network.build_network(_parse(stepped)).shunt.iloc[0]
    assert row["psse_ctl"] == 1.0 and row["psse_vswlo"] == 0.95 and row["psse_vswhi"] == 1.05
    assert row["psse_levels"] == "0.0,25.0,50.0,75.0,100.0"
    two_blocks, _ = _with_switched_shunt(records, N2=2, B2=10.0)
    assert network.build_network(_parse(two_blocks)).shunt.iloc[0]["psse_levels"] == (
        "0.0,25.0,50.0,75.0,100.0,110.0,120.0")
    locked, _ = _with_switched_shunt(records, MODSW=0)
    assert "psse_ctl" not in network.build_network(_parse(locked)).shunt.columns
    off, _ = _with_switched_shunt(records, STAT=0)
    assert "psse_ctl" not in network.build_network(_parse(off)).shunt.columns


@pytest.mark.parametrize("change", [
    {"MODSW": 2}, {"ADJM": 1}, {"BINIT": 30.0}, {"VSWLO": 1.1, "VSWHI": 0.9},
    {"N1": 0, "B1": 0.0, "BINIT": 0.0}], ids=["continuous", "sorted_blocks", "off_level",
                                           "inverted_band", "no_levels"])
def test_unsupported_switched_shunt_control_is_refused(change):
    records, _ = _with_switched_shunt(_records(), **change)
    with pytest.raises(network.BuildRefused) as caught:
        network.build_network(_parse(records))
    assert caught.value.reason == "switched_shunt_control" and caught.value.count == 1


def test_out_of_service_switched_shunt_is_copied_and_a_remote_one_is_refused():
    records = _records()
    off, _ = _with_switched_shunt(records, STAT=0)
    assert list(network.build_network(_parse(off)).shunt.in_service) == [False]
    remote_bus = records["load"][1]["I"]
    remote, _ = _with_switched_shunt(records, SWREM=remote_bus)
    with pytest.raises(network.BuildRefused) as caught:
        network.build_network(_parse(remote))
    assert caught.value.reason == "remote_regulation" and caught.value.count == 1


def test_local_voltage_control_transformer_is_built_at_its_initial_tap():
    records = _records()
    plain = network.build_network(_parse(records))
    controlled = fixture.mutate(records, "transformer", 1, "COD1", 1)
    net = network.build_network(_parse(controlled))
    assert net.trafo.equals(plain.trafo), "local voltage control must not change the built tap"
    own_bus = records["transformer"][1]["J"]
    own = fixture.mutate(controlled, "transformer", 1, "CONT1", own_bus)
    assert network.build_network(_parse(own)).trafo.equals(plain.trafo)


def test_build_is_pure_and_leaves_the_case_unchanged():
    case = _parse(_records())
    before = copy.deepcopy(case)
    first = network.build_network(case)
    second = network.build_network(case)
    for table in ("bus", "line", "trafo", "load", "gen", "ext_grid", "shunt"):
        assert getattr(first, table).equals(getattr(second, table)), "a table differs"
    assert case == before


def test_production_modules_build_from_parsed_values_only():
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "pandapower_job")
    pattern = re.compile(r"pandapower\.(networks|converter)|from pandapower import "
                         r"(networks|converter)")
    for name in ("raw.py", "network.py"):
        with open(os.path.join(folder, name), encoding="utf-8") as handle:
            source = handle.read()
        imports = [line for line in source.split("\n")
                   if line.lstrip().startswith(("import ", "from "))]
        assert not [line for line in imports if pattern.search(line)]
