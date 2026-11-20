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
import json
import re

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower.networks as pandapower_networks  # noqa: E402

import pandapower_fixture as fixture  # noqa: E402
import private_leak_scan  # noqa: E402
from pandapower_job import convert, network, parity, raw  # noqa: E402

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


def test_a_switched_shunt_is_compared_as_the_shunt_it_is_built_as():
    records = fixture.case39_records(OFFSET)
    bus = records["load"][0]["I"]
    shunt = {"I": bus, "MODSW": 1, "ADJM": 0, "STAT": 1, "VSWHI": 1.05, "VSWLO": 0.95, "SWREM": 0,
             "RMPCT": 100.0, "RMIDNT": "", "BINIT": 40.0}
    for n in range(1, 9):
        shunt["N%d" % n] = 0
        shunt["B%d" % n] = 0.0
    records["switched_shunt"] = [shunt]
    case, net = _built(records)
    report = parity.parity_report(case, net)
    assert report.passed is True and report.differences == ()
    net.shunt.at[net.shunt.index[0], "q_mvar"] = 0.0
    assert _triples(parity.parity_report(case, net)) == {("shunts", "%d-sw" % bus, "BL")}


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


# -- the converted network copy (D-06) ------------------------------------------------------------

MARKER = "pandapower_" + "job_" + "network"      # assembled: the leak guard flags the literal key


def _values(case):
    return {name: [dict(record.values) for record in records]
            for name, records in case.sections.items()}


def _document(case):
    return json.loads(convert.case_to_json(case).decode("ascii"))


def _dump(document, **kwargs):
    return json.dumps(document, **kwargs).encode("ascii")


def test_converted_round_trip_and_equal_build():
    case, net = _built()
    data = convert.case_to_json(case)
    copy_of = convert.case_from_json(data)

    assert (copy_of.revision, copy_of.ic, copy_of.sbase_mva, copy_of.base_frequency_hz) == (
        case.revision, case.ic, case.sbase_mva, case.base_frequency_hz)
    assert set(copy_of.sections) == set(case.sections)
    assert _values(copy_of) == _values(case)
    assert all(record.line is None for records in copy_of.sections.values()
               for record in records)
    assert all(record.section == name for name, records in copy_of.sections.items()
               for record in records)

    built = network.build_network(copy_of)
    tables = [name for name, table in net.items() if hasattr(table, "equals")
              and hasattr(table, "columns")]
    assert len(tables) > 10
    for name in tables:
        assert built[name].equals(net[name]), name
    assert parity.parity_report(copy_of, built).passed is True
    # Reading the copy again and dumping it again gives the same bytes.
    assert convert.case_to_json(copy_of) == data


def test_converted_bytes_are_canonical_and_flagged_by_the_leak_guard():
    case, _ = _built()
    data = convert.case_to_json(case)

    assert convert.CONVERTED_MARKER == MARKER and convert.CONVERTED_SCHEMA == 1
    assert data.decode("ascii") and b"NaN" not in data and b"Infinity" not in data
    assert b", " not in data and b": " not in data              # compact separators
    document = json.loads(data.decode("ascii"))
    assert document[MARKER] == 1
    assert _dump(document, sort_keys=True, separators=(",", ":"), allow_nan=False) == data

    # Dict insertion order does not matter.
    flipped = {name: tuple(raw.Record(r.section, r.line, dict(reversed(list(r.values.items()))))
                           for r in records)
               for name, records in reversed(list(case.sections.items()))}
    assert convert.case_to_json(case._replace(sections=flipped)) == data

    # The leak guard's shape layer flags a copy of the converted file.
    pattern = private_leak_scan.SHAPE_PATTERNS["pandapower_marker"]
    assert any(pattern.search(line) for line in data.decode("ascii").splitlines())

    # A non-ASCII name (a Latin-1 byte in the RAW) is escaped, not written raw.
    records = fixture.case39_records(OFFSET)
    records["bus"][0]["NAME"] = "CAFÉ"
    accented = convert.case_to_json(_case(records))
    assert accented.decode("ascii") and b"\\u00c9" in accented
    assert _values(convert.case_from_json(accented))["bus"][0]["NAME"] == "CAFÉ"


def _bad_marker_removed(d):
    del d[MARKER]


def _bad_marker_renamed(d):
    d["pandapower_other"] = d.pop(MARKER)


def _bad_schema(d):
    d[MARKER] = 2


def _bad_revision(d):
    d["revision"] = 99


def _bad_header(d):
    d["sbase_mva"] = -1.0


def _bad_section_name(d):
    d["sections"]["not_a_section"] = []


def _bad_missing_section(d):
    del d["sections"]["zone"]


def _bad_unsupported_record(d):
    d["sections"]["facts"] = [dict(d["sections"]["zone"][0])]


def _bad_field_name(d):
    d["sections"]["bus"][0]["ZZSECRETFIELD"] = 1


def _bad_missing_field(d):
    del d["sections"]["branch"][0]["X"]


def _bad_string_in_number(d):
    d["sections"]["branch"][0]["X"] = "ZZSECRETVALUE"


def _bad_bool_in_number(d):
    d["sections"]["branch"][0]["X"] = True


def _bad_float_in_int(d):
    d["sections"]["bus"][0]["I"] = 1.5


def _bad_number_in_string(d):
    d["sections"]["bus"][0]["NAME"] = 7


def _bad_range(d):
    d["sections"]["bus"][0]["BASKV"] = 0.0


def _bad_records_not_list(d):
    d["sections"]["bus"] = {"I": 1}


def _bad_record_not_object(d):
    d["sections"]["bus"][0] = [1, 2, 3]


def _bad_top_level(d):
    d["extra"] = 1


BAD_DOCUMENTS = {
    "bad_marker": [_bad_marker_removed, _bad_marker_renamed],
    "bad_schema": [_bad_schema],
    "unknown_revision": [_bad_revision],
    "bad_header": [_bad_header],
    "unknown_section": [_bad_section_name],
    "bad_structure": [_bad_missing_section, _bad_records_not_list, _bad_record_not_object,
                      _bad_top_level],
    "unsupported_section": [_bad_unsupported_record],
    "unknown_field": [_bad_field_name],
    "missing_field": [_bad_missing_field],
    "bad_value": [_bad_string_in_number, _bad_bool_in_number, _bad_float_in_int,
                  _bad_number_in_string, _bad_range],
}


@pytest.mark.parametrize("reason,mutator", [
    (reason, mutator) for reason, mutators in sorted(BAD_DOCUMENTS.items())
    for mutator in mutators])
def test_converted_copy_refuses_a_bad_document(reason, mutator):
    case, _ = _built()
    document = _document(case)
    mutator(document)
    with pytest.raises(convert.ConvertRefused) as caught:
        convert.case_from_json(_dump(document))
    assert caught.value.reason == reason
    assert "ZZSECRET" not in str(caught.value)
    assert reason in str(caught.value)


def test_converted_copy_refuses_bad_input():
    case, _ = _built()
    good = convert.case_to_json(case)
    nan_document = good.decode("ascii").replace('"X":', '"X":NaN,"XX":', 1)

    refused = {
        "not_json": [b"", b"{", b"[]\x00", b"\xc3\xa9", good[:-1], "text".encode("ascii")],
        "bad_value": [nan_document.encode("ascii"),
                      good.replace(b'"BASKV":', b'"BASKV":Infinity,"XX":', 1)],
        "bad_structure": [b'{"a":1,"a":2}', b"null", b"[1]", b"3"],
        "too_large": [good + b" " * convert.MAX_CONVERTED_BYTES],
    }
    for reason, inputs in refused.items():
        for data in inputs:
            with pytest.raises(convert.ConvertRefused) as caught:
                convert.case_from_json(data)
            assert caught.value.reason == reason, (reason, data[:20])
    with pytest.raises(convert.ConvertRefused) as caught:
        convert.case_from_json("not bytes")
    assert caught.value.reason == "not_json"
    # Bytes exactly at the cap are read (whitespace after the document is fine for JSON).
    padded = good + b" " * (convert.MAX_CONVERTED_BYTES - len(good))
    assert len(padded) == convert.MAX_CONVERTED_BYTES
    assert _values(convert.case_from_json(padded)) == _values(case)

    # Writing refuses a case that cannot be read back.
    broken = _case()
    first = broken.sections["bus"][0]
    values = dict(first.values, BASKV=float("nan"))
    sections = dict(broken.sections, bus=(raw.Record("bus", first.line, values),)
                    + tuple(broken.sections["bus"][1:]))
    with pytest.raises(convert.ConvertRefused) as caught:
        convert.case_to_json(broken._replace(sections=sections))
    assert caught.value.reason == "bad_value"


def test_every_convert_reason_is_exercised():
    exercised = set(BAD_DOCUMENTS) | {"not_json", "bad_value", "bad_structure", "too_large"}
    assert exercised == set(convert.CONVERT_REASONS)


def test_size_report_and_the_secret_limit():
    case, _ = _built()
    data = convert.case_to_json(case)
    report = convert.size_report(data)

    assert convert.SECRET_LIMIT_BYTES == 49152 and convert.MAX_CONVERTED_BYTES == 1048576
    assert report["bytes"] == len(data) < convert.SECRET_LIMIT_BYTES
    assert report["fits_secret_limit"] is True
    assert 0 < report["gzip_bytes"] < report["bytes"]

    at_limit = data + b" " * (convert.SECRET_LIMIT_BYTES - len(data))
    assert convert.size_report(at_limit)["fits_secret_limit"] is True
    over = at_limit + b" "
    assert convert.size_report(over)["bytes"] == convert.SECRET_LIMIT_BYTES + 1
    assert convert.size_report(over)["fits_secret_limit"] is False
    assert convert.size_report(data + b" " * convert.SECRET_LIMIT_BYTES)[
        "fits_secret_limit"] is False
    # Equal input, equal report (gzip is written without a timestamp).
    assert convert.size_report(data) == report


# -- the evidence against the public 39-bus case (D-06) ---------------------------------------------


def _export_counts(report):
    return report.element_counts["export"]


def test_case39_evidence_counts():
    # Offset 0: the synthetic export is the public case, so nothing differs.
    records = fixture.case39_records(0)
    report = parity.case39_evidence(_case(records))
    assert report.unmatched_buses == 0 and report.classification_differences == 0
    assert report.threshold == parity.D06_RELATIVE_THRESHOLD == 1e-6
    assert set(report.differing_beyond) == {"impedance", "rating", "voltage_limits", "setpoints",
                                            "machine_limits", "loads", "shunts"}
    assert all(count == 0 for count in report.differing_beyond.values())
    export, reference = report.element_counts["export"], report.element_counts["reference"]
    assert export == reference
    assert (export["buses"], export["lines"], export["transformers"]) == (39, 35, 11)
    assert (export["loads"], export["machines"], export["shunts"]) == (21, 10, 0)
    assert report.element_counts["matched"]["buses"] == 39

    # Offset 90000: every bus number differs, so no bus is matched.
    far = parity.case39_evidence(_case(fixture.case39_records(OFFSET)))
    assert far.unmatched_buses == 39
    assert far.element_counts["matched"]["buses"] == 0
    assert far.element_counts["matched"]["branches"] == 0

    # One line's reactance changed by 1 percent: one element differs, in impedance.
    changed = fixture.mutate(records, "branch", 3, "X", records["branch"][3]["X"] * 1.01)
    drift = parity.case39_evidence(_case(changed))
    assert drift.differing_beyond["impedance"] == 1
    assert sum(drift.differing_beyond.values()) == 1
    assert drift.classification_differences == 0
    # ... and one changed by far less than the threshold is not counted.
    tiny = fixture.mutate(records, "branch", 3, "X", records["branch"][3]["X"] * (1 + 1e-9))
    assert parity.case39_evidence(_case(tiny)).differing_beyond["impedance"] == 0

    # The same data classified differently: a line exported as a transformer.
    moved = fixture.remove(records, "branch", 3)
    line = records["branch"][3]
    template = dict(records["transformer"][0], I=line["I"], J=line["J"], CKT=line["CKT"])
    moved = fixture.append(moved, "transformer", template)
    kinds = parity.case39_evidence(_case(moved))
    assert kinds.classification_differences == 1
    assert kinds.element_counts["export"]["lines"] == 34
    assert kinds.element_counts["export"]["transformers"] == 12


def test_evidence_render_holds_counts_only_and_decides_nothing():
    case = _case(fixture.case39_records(OFFSET))
    text = parity.case39_evidence(case).render_counts()
    assert "decides nothing" in text and "D-06" in text
    assert not re.search(r"9[0-9]{4}", text)
    assert not re.search(r"[0-9]+-[0-9]+-", text)
    assert "unmatched buses: 39" in text
    # Evidence never raises or gates: the reference may be passed in.
    reference = pandapower_networks.case39()
    again = parity.case39_evidence(case, reference_net=reference)
    assert again.render_counts() == text
