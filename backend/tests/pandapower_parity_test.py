"""
Tests for the parity report and the converted network copy (pandapower-solver Phase 1, plan 01-07:
NET-02 and the evidence for decision D-06).

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_fixture`); nothing synthetic is committed. The parity
report proves transcription only: a network built from a file and read back to that file agrees
with it even if both misread a PSS/E convention. NET-03, against PSS/E's own answers, is the
independent check. The tests here prove the report can fail: one mutation per category, each
naming exactly the element that was changed.

Failure messages are counts only.
"""

import copy
import re

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_fixture as fixture  # noqa: E402
from pandapower_job import network, parity, raw  # noqa: E402

OFFSET = fixture.OFFSET


def _case(records=None):
    records = fixture.case39_records(OFFSET) if records is None else records
    return raw.parse_raw(fixture.raw_text(records).encode("utf-8"))


def _built(records=None):
    case = _case(records)
    return case, network.build_network(case)


def test_tracer_parity_is_zero_on_a_clean_synthetic_build():
    case, net = _built()
    report = parity.parity_report(case, net)

    assert report.differences == ()
    assert report.passed is True
    counts = report.category_counts()
    assert tuple(counts) == parity.PARITY_CATEGORIES
    # No shunt section in the synthetic case: that category has no elements and no comparison.
    assert report.elements["shunts"] == 0 and report.compared["shunts"] == 0
    for category in parity.PARITY_CATEGORIES:
        if report.elements[category] > 0:
            assert report.compared[category] > 0, category
            assert counts[category][1] == 0
    # 39 buses, 46 branches, 21 loads and 10 machines were each matched by key.
    assert report.compared["counts"] == 5
    assert report.compared["voltage_limits"] == 39 * 3
    assert report.compared["loads"] == 21 * 2
    assert report.compared["rating"] == 35


def test_render_counts_holds_no_key_or_value():
    case, net = _built()
    report = parity.parity_report(case, net)
    text = report.render_counts()

    lines = text.splitlines()
    assert lines[0] == parity.PARITY_SCOPE_NOTE
    assert "NET-03" in lines[0] and "transcription" in lines[0]
    assert [line.split(":")[0] for line in lines[1:-1]] == list(parity.PARITY_CATEGORIES)
    assert lines[-1] == "parity: pass"
    assert not re.search(r"9[0-9]{4}", text)
    assert not re.search(r"[0-9]+-[0-9]+-", text)  # no from-to-circuit key
    # A failing build still prints counts only: no key, no value.
    broken_case, broken = _built()
    broken.line.loc[broken.line.index[0], "x_ohm_per_km"] *= 1.5
    failing = parity.parity_report(broken_case, broken).render_counts()
    assert failing.splitlines()[0] == parity.PARITY_SCOPE_NOTE
    assert failing.splitlines()[-1].startswith("parity: fail (1 difference(s)")
    assert not re.search(r"9[0-9]{4}", failing)
    assert "impedance: " in failing


# -- one mutation per category -------------------------------------------------------------------


def _shunt_record(bus_number):
    return {"I": bus_number, "ID": "1", "STATUS": 1, "GL": 0.0, "BL": 50.0}


def _line_key(net, position):
    return str(net.line.iloc[position]["name"])


def _set(table_name, position, column, change):
    """A mutator: `change(value)` replaces `column` of the row at `position` of the table."""
    def apply(net):
        table = getattr(net, table_name)
        index = table.index[position]
        table.loc[index, column] = change(table.at[index, column])
    return apply


def _drop_line(net):
    net.line.drop(net.line.index[3], inplace=True)


def _line_as_transformer(net):
    position = 3
    row = net.line.iloc[position]
    key, from_bus, to_bus = str(row["name"]), int(row["from_bus"]), int(row["to_bus"])
    net.line.drop(net.line.index[position], inplace=True)
    kv_from, kv_to = net.bus.at[from_bus, "vn_kv"], net.bus.at[to_bus, "vn_kv"]
    pandapower.create_transformer_from_parameters(
        net, hv_bus=from_bus, lv_bus=to_bus, sn_mva=100.0, vn_hv_kv=kv_from, vn_lv_kv=kv_to,
        vk_percent=10.0, vkr_percent=1.0, pfe_kw=0.0, i0_percent=0.0, name=key)


def _bus_text(net, position=5):
    return str(int(net.bus.index[position]))


# name -> (mutator, expected difference set as a function of the unmutated net)
MUTATIONS = {
    "reactance": (_set("line", 3, "x_ohm_per_km", lambda v: v * 1.01),
                  lambda net: {("impedance", _line_key(net, 3), "X")}),
    "rating": (_set("line", 3, "max_i_ka", lambda v: v * 1.01),
               lambda net: {("rating", _line_key(net, 3), "RATEA")}),
    "setpoint": (_set("gen", 2, "vm_pu", lambda v: v + 0.01),
                 lambda net: {("setpoints", str(net.gen.iloc[2]["name"]), "VS")}),
    "voltage_limit": (_set("bus", 5, "max_vm_pu", lambda v: v + 0.01),
                      lambda net: {("voltage_limits", _bus_text(net), "NVHI")}),
    "machine_limit": (_set("gen", 2, "max_q_mvar", lambda v: v + 1.0),
                      lambda net: {("machine_limits", str(net.gen.iloc[2]["name"]), "QT")}),
    "load": (_set("load", 4, "q_mvar", lambda v: v + 1.0),
             lambda net: {("loads", str(net.load.iloc[4]["name"]), "QL")}),
    "shunt": (_set("shunt", 0, "q_mvar", lambda v: v + 1.0),
              lambda net: {("shunts", str(net.shunt.iloc[0]["name"]), "BL")}),
    "in_service": (_set("line", 3, "in_service", lambda v: not v),
                   lambda net: {("in_service", _line_key(net, 3), "ST")}),
    "dropped_line": (_drop_line,
                     lambda net: {("counts", "branches", "count"),
                                  ("names", _line_key(net, 3), "missing")}),
    "reclassified_line": (_line_as_transformer,
                          lambda net: {("classification", _line_key(net, 3), "kind")}),
}


def _shunt_case():
    records = fixture.append(fixture.case39_records(OFFSET), "fixed_shunt",
                             _shunt_record(OFFSET + 7))
    return _built(records)


def _triples(report):
    return {(item.category, item.element, item.quantity) for item in report.differences}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_each_single_mutation_is_named_exactly(name):
    mutate, expected_of = MUTATIONS[name]
    case, net = _shunt_case()
    assert parity.parity_report(case, net).passed is True
    expected = expected_of(net)          # keys read before the mutation changes the tables
    mutate(net)
    report = parity.parity_report(case, net)

    assert report.passed is False
    assert _triples(report) == expected
    assert len(report.differences) == len(expected)


def test_a_mutation_leaves_every_other_category_clean():
    case, net = _shunt_case()
    MUTATIONS["reactance"][0](net)
    counts = parity.parity_report(case, net).category_counts()
    assert counts["impedance"][1] == 1
    assert sum(found for _, found in counts.values()) == 1


def test_difference_carries_expected_and_got():
    case, net = _built()
    key = _line_key(net, 3)
    MUTATIONS["reactance"][0](net)
    (item,) = parity.parity_report(case, net).differences
    exported = {raw.branch_key(r.values["I"], r.values["J"], r.values["CKT"]): r.values
                for r in case.sections["branch"]}[key]
    assert item.expected == exported["X"]
    assert item.got == pytest.approx(exported["X"] * 1.01, rel=1e-12)


# -- the edges -----------------------------------------------------------------------------------


def test_tolerance_boundary(monkeypatch):
    # With a tolerance that is exact in binary, "equal to the tolerance" is exactly representable.
    monkeypatch.setattr(parity, "PARITY_RELATIVE_TOLERANCE", 2.0 ** -10)
    assert parity._differs(1.0, 1.0 + 2.0 ** -10) is False
    assert parity._differs(1.0, 1.0 - 2.0 ** -10) is False
    assert parity._differs(1.0, 1.0 + 2.0 ** -9) is True
    assert parity._differs(1.0, 1.0 + 2.0 ** -10 + 2.0 ** -40) is True
    assert parity._differs(1024.0, 1024.0 * (1.0 + 2.0 ** -10)) is False
    # The absolute floor governs near zero.
    assert parity._differs(0.0, parity.PARITY_ABSOLUTE_FLOOR) is False
    assert parity._differs(0.0, 2.0 * parity.PARITY_ABSOLUTE_FLOOR) is True
    # Missing and non-finite values always differ, text is exact.
    assert parity._differs(1.0, None) is True
    assert parity._differs(1.0, float("nan")) is True
    assert parity._differs(1.0, float("inf")) is True
    assert parity._differs("a", "a") is False and parity._differs("a", "b") is True


def test_tolerance_boundary_on_a_real_element():
    # Binary floats cannot land exactly on 1e-9, so the real element is tried at half the
    # tolerance (passes) and twice the tolerance (listed); the exact boundary is the test above.
    tolerance = parity.PARITY_RELATIVE_TOLERANCE
    inside_case, inside = _built()
    inside.line.loc[inside.line.index[3], "x_ohm_per_km"] *= 1.0 + 0.5 * tolerance
    assert parity.parity_report(inside_case, inside).differences == ()

    outside_case, outside = _built()
    key = _line_key(outside, 3)
    outside.line.loc[outside.line.index[3], "x_ohm_per_km"] *= 1.0 + 2.0 * tolerance
    assert _triples(parity.parity_report(outside_case, outside)) == {("impedance", key, "X")}


def test_empty_sections_and_one_sided_elements():
    # An empty section on both sides: zero comparisons for it, nothing listed, still a pass.
    records = fixture.case39_records(OFFSET)
    records["load"] = []
    case, net = _built(records)
    report = parity.parity_report(case, net)
    assert report.compared["loads"] == 0 and report.elements["loads"] == 0
    assert report.differences == () and report.passed is True

    # An export load missing from the net: under names, and the family count under counts.
    case, net = _built()
    key = str(net.load.iloc[4]["name"])
    net.load.drop(net.load.index[4], inplace=True)
    assert _triples(parity.parity_report(case, net)) == {
        ("names", key, "missing"), ("counts", "loads", "count")}

    # A load in the net that the export does not have: also listed, as extra.
    case, net = _built()
    pandapower.create_load(net, int(net.bus.index[0]), p_mw=1.0, q_mvar=0.0, name="not-in-export")
    assert _triples(parity.parity_report(case, net)) == {
        ("names", "not-in-export", "extra"), ("counts", "loads", "count")}

    # An export shunt with no shunt in the net.
    shunt_case, shunt_net = _shunt_case()
    shunt_net.shunt.drop(shunt_net.shunt.index, inplace=True)
    report = parity.parity_report(shunt_case, shunt_net)
    assert report.passed is False and report.compared["shunts"] == 0
    assert report.elements["shunts"] == 1


def test_a_category_that_could_not_be_compared_is_not_a_pass():
    full = {name: 5 for name in parity.PARITY_CATEGORIES}
    compared = dict(full)
    compared["loads"] = 0
    report = parity.ParityReport((), compared, full)
    assert report.passed is False
    assert "parity: fail" in report.render_counts()
    assert "1 category(ies) not compared" in report.render_counts()
    # With nothing to compare in that category it is not required.
    elements = dict(full)
    elements["loads"] = 0
    assert parity.ParityReport((), compared, elements).passed is True
    # A report that compared nothing at all is not a pass either.
    nothing = {name: 0 for name in parity.PARITY_CATEGORIES}
    assert parity.ParityReport((), nothing, nothing).passed is False


def test_an_unreadable_value_is_a_difference_not_a_skip():
    case, net = _built()
    swing = str(net.ext_grid.iloc[0]["name"])
    net.ext_grid.drop(columns=["psse_qt_mvar"], inplace=True)
    report = parity.parity_report(case, net)
    assert _triples(report) == {("machine_limits", swing, "QT")}
    (item,) = report.differences
    assert item.got is None
    net.gen.loc[net.gen.index[0], "vm_pu"] = float("nan")
    assert len(parity.parity_report(case, net).differences) == 2


def _shuffle_rows(net):
    shuffled = copy.deepcopy(net)
    for table in ("line", "trafo", "load", "gen"):
        setattr(shuffled, table, getattr(shuffled, table).sample(frac=1, random_state=7))
    return shuffled


def test_differences_are_sorted_and_row_order_free():
    case, net = _built()
    for name in ("reactance", "rating", "setpoint", "voltage_limit", "load", "in_service"):
        MUTATIONS[name][0](net)
    _set("line", 9, "x_ohm_per_km", lambda v: v * 1.02)(net)
    _set("load", 1, "p_mw", lambda v: v + 1.0)(net)
    report = parity.parity_report(case, net)

    order = {name: position for position, name in enumerate(parity.PARITY_CATEGORIES)}
    keys = [(order[d.category], str(d.element), d.quantity) for d in report.differences]
    assert keys == sorted(keys) and len(keys) == 8

    shuffled = _shuffle_rows(net)
    assert list(shuffled.line.index) != list(net.line.index)
    assert parity.parity_report(case, shuffled) == report

    clean_case, clean = _built()
    assert parity.parity_report(clean_case, _shuffle_rows(clean)) == parity.parity_report(
        clean_case, clean)


def test_report_reads_the_net_only():
    case, net = _shunt_case()
    pandapower.runpp(net)
    MUTATIONS["reactance"][0](net)
    before = {name: table.copy(deep=True) for name, table in net.items()
              if hasattr(table, "equals") and hasattr(table, "columns")}
    assert len(before) > 10
    first = parity.parity_report(case, net)
    second = parity.parity_report(case, net)
    assert first == second and len(first.differences) == 1
    for name, table in before.items():
        assert net[name].equals(table), name
