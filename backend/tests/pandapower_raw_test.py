"""
Tests for the fail-closed RAW parser (pandapower-solver Phase 1, plan 01-06: NET-01).

Inputs are built from `pandapower_fixture` text (a synthetic file made from pandapower's 39-bus
case, bus numbers offset by 90000) by string edits in memory; nothing is written to the repository.
The tests prove the parser's refusals, its handling of the empty and encoding edges, its defaults
and its purity. They cannot prove that PSS/E writes this layout: the hand-typed records in
`test_positional_layout_matches_the_v33_documentation` pin the field order to the PowerModels.jl
reader's documentation, and a real file is plan 01-10's job.

Failure messages are counts only.
"""

import copy
import re

import pytest

import pandapower_fixture as fixture
from pandapower_job import raw

OFFSET = fixture.OFFSET
PLANTED_BUS = OFFSET + 16
PLANTED_NAME = "PLANTEDNAME"
ANY_LINE = object()


def _records():
    return fixture.case39_records(OFFSET)


def _lines(text):
    return text.split("\n")


def _line_of(text, needle, start=0):
    """The 1-based number of the first line at or after index `start` that contains `needle`."""
    for index, line in enumerate(_lines(text)):
        if index >= start and needle in line:
            return index + 1
    raise AssertionError("the needle is not in the text")


def _replace_line(text, number, new):
    lines = _lines(text)
    lines[number - 1] = new
    return "\n".join(lines)


def _record_line(text, section, position=0):
    """The 1-based number of the `position`-th record line of `section` in the generated text."""
    order = fixture.V33_ORDER
    start = 3
    for name in order[:order.index(section)]:
        start = _line_of(text, fixture.terminator_line(name), start)
    return start + 1 + position * (4 if section == "transformer" else 1)


def _insert_before(text, section, new_lines):
    terminator = fixture.terminator_line(section)
    return text.replace(terminator, "\n".join(new_lines + [terminator]), 1)


def _refusal_cases():
    """(id, data, reason, expected line or None) for every reason of REFUSAL_REASONS."""
    records = _records()
    text = fixture.raw_text(records)
    cases = []

    def add(name, data, reason, line=None):
        cases.append(pytest.param(data, reason, line, id=name))

    add("empty_bytes", b"", "empty")
    add("empty_blank_lines", b"  \n\r\n\t\n", "empty")
    add("too_large", b"0" * (raw.MAX_RAW_BYTES + 1), "too_large")
    add("header_sbase_not_a_number", _replace_line(text, 1, "0, abc, 33, 0, 1, 60.0"),
        "bad_header", 1)
    add("header_too_short", _replace_line(text, 1, "0, 100.0"), "bad_header", 1)
    add("header_only", "0, 100.0, 33, 0, 1, 60.0\n", "bad_header", 1)
    for revision in (34, 35, 36):
        add("revision_%d" % revision, fixture.raw_text(records, revision=revision),
            "unknown_revision", 1)

    bus_end = fixture.terminator_line("bus")
    bus_end_line = _line_of(text, bus_end)
    add("terminator_names_an_unknown_section",
        text.replace(bus_end, "0 / " + "END" + " OF " + "NOWHERE DATA", 1), "unknown_section",
        bus_end_line)
    add("terminator_names_a_section_out_of_order",
        text.replace(bus_end, fixture.terminator_line("load"), 1), "unknown_section",
        bus_end_line)
    add("begin_phrase_names_the_wrong_section",
        text.replace(bus_end, "0 / " + "END" + " OF BUS DATA, " + "BEG" + "IN GENERATOR DATA", 1),
        "unknown_section", bus_end_line)

    facts = fixture.terminator_line("facts")
    facts_line = _line_of(text, facts)
    add("facts_record",
        _insert_before(text, "facts", ["'F1', 90001, 0, 1"]),
        "unsupported_section", facts_line)
    switched_line = _line_of(text, fixture.terminator_line("switched_shunt"))
    add("switched_shunt_record_too_short",
        _insert_before(text, "switched_shunt", ["90001, 1, 0, 1, 1.1, 0.9"]),
        "field_count", switched_line)

    first_bus = _record_line(text, "bus")
    short_bus = ",".join(_lines(text)[first_bus - 1].split(",")[:5])
    add("bus_record_too_short", _replace_line(text, first_bus, short_bus), "field_count",
        first_bus)
    first_branch = _record_line(text, "branch")
    add("branch_record_too_long",
        _replace_line(text, first_branch, _lines(text)[first_branch - 1] + ", 5.0"),
        "field_count", first_branch)

    bad_bus = _lines(text)[first_bus - 1].split(",")
    bad_bus[2] = "abc"
    add("letter_in_a_numeric_field", _replace_line(text, first_bus, ",".join(bad_bus)),
        "bad_value", first_bus)
    inf_bus = _lines(text)[first_bus - 1].split(",")
    inf_bus[2] = "1e999"
    add("overflowing_number", _replace_line(text, first_bus, ",".join(inf_bus)), "bad_value",
        first_bus)

    first_trafo = _record_line(text, "transformer")
    add("three_winding_transformer",
        fixture.raw_text(fixture.mutate(records, "transformer", 0, "K", 90003)),
        "three_winding", first_trafo)

    def appended(section, record, reason):
        new = fixture.raw_text(fixture.append(records, section, record))
        add("duplicate_" + reason.split("_")[1] + "_" + section, new, reason,
            _line_of(new, fixture.terminator_line(section)) - 1)

    appended("bus", records["bus"][3], "duplicate_bus")
    appended("branch", records["branch"][3], "duplicate_branch")
    appended("generator", records["generator"][3], "duplicate_machine")
    appended("load", records["load"][3], "duplicate_load")

    clash = dict(records["transformer"][0], I=records["branch"][0]["I"],
                 J=records["branch"][0]["J"], CKT=records["branch"][0]["CKT"])
    new = fixture.raw_text(fixture.append(records, "transformer", clash))
    add("line_and_transformer_share_a_key", new, "duplicate_branch",
        _line_of(new, fixture.terminator_line("transformer")) - 4)

    add("no_final_q", text.replace("Q\n", ""), "unterminated", ANY_LINE)
    add("q_before_the_last_section", text.replace(fixture.terminator_line("owner"), "Q", 1),
        "unterminated", _line_of(text, fixture.terminator_line("owner")))
    add("record_after_q", text + "90001, 90002, 1\n", "trailing_data", len(_lines(text)))
    return cases


@pytest.mark.parametrize("data,reason,line", _refusal_cases())
def test_parser_refuses_each_malformed_input(data, reason, line):
    with pytest.raises(raw.RawRefused) as caught:
        raw.parse_raw(data)
    assert caught.value.reason == reason
    assert reason in raw.REFUSAL_REASONS
    if line is None:
        assert caught.value.line is None
    elif line is ANY_LINE:
        assert isinstance(caught.value.line, int) and caught.value.line >= 1
    else:
        assert caught.value.line == line


def test_every_reason_is_exercised():
    seen = set(case.values[1] for case in _refusal_cases())
    assert seen == set(raw.REFUSAL_REASONS)


def test_refusal_messages_hold_no_record_text():
    records = fixture.mutate(_records(), "bus", 15, "NAME", PLANTED_NAME)
    assert records["bus"][15]["I"] == PLANTED_BUS
    text = fixture.raw_text(records)
    planted = _record_line(text, "bus", 15)
    line = _lines(text)[planted - 1]
    assert PLANTED_NAME in line and str(PLANTED_BUS) in line
    fields = line.split(",")
    fields[2] = "abc"
    inputs = [
        _replace_line(text, planted, ",".join(fields)),
        fixture.raw_text(fixture.append(records, "bus", records["bus"][15])),
        fixture.raw_text(fixture.mutate(records, "transformer", 0, "K", PLANTED_BUS)),
        text.replace("Q\n", ""),
    ]
    shape = re.compile(r"^RAW refused: [a-z_]+( \(line [0-9]+\))?$")
    for data in inputs:
        with pytest.raises(raw.RawRefused) as caught:
            raw.parse_raw(data)
        message = str(caught.value)
        assert shape.match(message), "a message holds more than the reason and a line number"
        assert str(PLANTED_BUS) not in message and PLANTED_NAME not in message


def test_all_empty_sections_parse_to_zero_records():
    case = raw.parse_raw(fixture.raw_text({}))
    assert case.revision == 33
    assert set(case.sections) == set(raw.SECTION_ORDER[33])
    assert all(len(items) == 0 for items in case.sections.values())


def _without_names(case):
    return {name: [{key: value for key, value in rec.values.items()
                    if key not in ("NAME", "ARNAME", "ZONAME", "OWNAME")}
                   for rec in records]
            for name, records in case.sections.items()}


def test_bom_crlf_tabs_latin1_and_quoted_separators_parse():
    records = _records()
    text = fixture.raw_text(records)
    baseline = raw.parse_raw(text)
    base = _without_names(baseline)

    assert _without_names(raw.parse_raw(b"\xef\xbb\xbf" + text.encode("utf-8"))) == base
    assert _without_names(raw.parse_raw(text.replace("\n", "\r\n").encode("utf-8"))) == base
    tabbed = "\n".join(
        line.replace(",", "\t,\t") if not line.startswith(("0 /", "Q")) else line
        for line in _lines(text))
    assert _without_names(raw.parse_raw(tabbed.encode("utf-8"))) == base

    accented = fixture.mutate(records, "bus", 0, "NAME", "BUS \xe9")
    data = fixture.raw_text(accented).encode("latin-1")
    with pytest.raises(UnicodeDecodeError):
        data.decode("utf-8")
    parsed = raw.parse_raw(data)
    assert parsed.sections["bus"][0].values["NAME"] == "BUS \xe9"
    assert _without_names(parsed) == base

    tricky = fixture.mutate(records, "bus", 0, "NAME", "A,B/C")
    parsed = raw.parse_raw(fixture.raw_text(tricky))
    assert parsed.sections["bus"][0].values["NAME"] == "A,B/C"
    assert _without_names(parsed) == base
    assert len(parsed.sections["bus"]) == len(baseline.sections["bus"])


def test_circuit_ids_compare_after_stripping():
    assert raw.branch_key(5, 6, "1 ") == raw.branch_key(5, 6, "1") == "5-6-1"
    records = _records()
    text = fixture.raw_text(records)
    number = _record_line(text, "branch")
    fields = _lines(text)[number - 1].split(",")
    keys = set()
    for ckt in ("'1 '", "'1'", "1", " ' 1' "):
        edited = list(fields)
        edited[2] = ckt
        case = raw.parse_raw(_replace_line(text, number, ",".join(edited)))
        values = case.sections["branch"][0].values
        keys.add(raw.branch_key(values["I"], values["J"], values["CKT"]))
    assert len(keys) == 1 and keys.pop().endswith("-1")

    # Two branches that differ only in padding are one key.
    second = list(fields)
    second[2] = "1"
    doubled = _insert_before(text, "branch", [",".join(second)])
    with pytest.raises(raw.RawRefused) as caught:
        raw.parse_raw(doubled)
    assert caught.value.reason == "duplicate_branch"


def test_truncated_records_get_documented_defaults():
    records = _records()
    text = fixture.raw_text(records)

    bus_line = _record_line(text, "bus")
    bus = ",".join(_lines(text)[bus_line - 1].split(",")[:11])
    gen_line = _record_line(text, "generator")
    gen = ",".join(_lines(text)[gen_line - 1].split(",")[:7])
    branch_line = _record_line(text, "branch")
    branch = ",".join(_lines(text)[branch_line - 1].split(",")[:6])
    edited = _replace_line(text, bus_line, bus)
    edited = _replace_line(edited, gen_line, gen)
    edited = _replace_line(edited, branch_line, branch)
    trafo_line = _record_line(text, "transformer")
    edited = _replace_line(edited, trafo_line + 2, "1.025")
    edited = _replace_line(edited, trafo_line + 3, "1.0")
    edited = _replace_line(edited, trafo_line + 1, "0.001, 0.05")

    case = raw.parse_raw(edited)
    bus_values = case.sections["bus"][0].values
    assert bus_values["EVHI"] == 1.1 and bus_values["EVLO"] == 0.9
    assert bus_values["NVHI"] == records["bus"][0]["NVHI"]
    gen_values = case.sections["generator"][0].values
    assert gen_values["IREG"] == 0 and gen_values["STAT"] == 1 and gen_values["ZX"] == 1.0
    assert gen_values["PT"] == 9999.0 and gen_values["PB"] == -9999.0
    assert gen_values["RMPCT"] == 100.0 and gen_values["O1"] == 0 and gen_values["F1"] == 1.0
    assert gen_values["VS"] == records["generator"][0]["VS"]
    branch_values = case.sections["branch"][0].values
    assert branch_values["RATEA"] == 0.0 and branch_values["ST"] == 1
    assert branch_values["GI"] == 0.0 and branch_values["MET"] == 1
    trafo_values = case.sections["transformer"][0].values
    assert trafo_values["WINDV1"] == 1.025 and trafo_values["COD1"] == 0
    assert trafo_values["ANG1"] == 0.0 and trafo_values["WINDV2"] == 1.0
    assert trafo_values["X1-2"] == 0.05 and trafo_values["CW"] == 1 and trafo_values["STAT"] == 1


def test_empty_fields_take_defaults_but_a_missing_key_field_is_refused():
    text = fixture.raw_text(_records())
    number = _record_line(text, "load")
    fields = _lines(text)[number - 1].split(",")
    fields[2] = ""                      # STATUS empty: the default (in service)
    case = raw.parse_raw(_replace_line(text, number, ",".join(fields)))
    assert case.sections["load"][0].values["STATUS"] == 1
    bus_number = _record_line(text, "bus")
    bus_fields = _lines(text)[bus_number - 1].split(",")
    bus_fields[2] = ""                  # BASKV empty: no default exists
    with pytest.raises(raw.RawRefused) as caught:
        raw.parse_raw(_replace_line(text, bus_number, ",".join(bus_fields)))
    assert caught.value.reason == "bad_value"


def test_parse_is_pure():
    tables = copy.deepcopy(raw.FIELD_TABLES)
    text = fixture.raw_text(_records())
    first = raw.parse_raw(text)
    second = raw.parse_raw(text)
    third = raw.parse_raw(text.encode("utf-8"))
    assert first == second == third
    first.sections["bus"][0].values["BASKV"] = -1.0
    first.sections["bus"][0].values["EXTRA"] = 1
    first.sections["load"] = ()
    assert second.sections["bus"][0].values["BASKV"] == 345.0
    assert "EXTRA" not in second.sections["bus"][0].values
    assert len(second.sections["load"]) == 21
    assert raw.parse_raw(text) == third
    assert raw.FIELD_TABLES == tables


# -- the layout itself --------------------------------------------------------------------------

_LITERALS = {
    "bus": ["90001,'BUS A',345.0,3,1,1,1,1.02,-5.5,1.06,0.94,1.07,0.93"],
    "load": ["90001,'1 ',1,1,1,100.5,20.25,1.0,2.0,3.0,4.0,1,1,0"],
    "fixed_shunt": ["90001,'1 ',1,0.5,-12.5"],
    "generator": ["90001,'1 ',500.0,10.0,300.0,-100.0,1.01,90001,550.0,0.0,1.0,0.0,0.0,1.0,1,"
                  "100.0,600.0,50.0,1,1.0,0,1.0,0,1.0,0,1.0,0,1.0"],
    "branch": ["90001,90002,'1 ',0.01,0.1,0.02,500.0,600.0,700.0,0.001,0.002,0.003,0.004,1,1,"
               "12.5,1,1.0,0,1.0,0,1.0,0,1.0"],
    "transformer": ["90002,90003,0,'1 ',1,1,1,0.001,0.002,2,'TR',1,1,1.0,0,1.0,0,1.0,0,1.0,'VG'",
                    "0.005,0.08,100.0",
                    "1.025,345.0,0.0,500.0,600.0,700.0,0,0,1.1,0.9,1.1,0.9,33,0,0.0,0.0,0.0",
                    "1.0,138.0"],
    "switched_shunt": ["90001,1,0,1,1.05,0.95,0,100.0,'',25.0,2,12.5"],
    "area": ["1,90001,10.5,5.0,'AREA ONE'"],
    "zone": ["1,'ZONE ONE'"],
    "owner": ["1,'OWNER ONE'"],
}

_EXPECTED = {
    "bus": {"I": 90001, "NAME": "BUS A", "BASKV": 345.0, "IDE": 3, "AREA": 1, "ZONE": 1,
            "OWNER": 1, "VM": 1.02, "VA": -5.5, "NVHI": 1.06, "NVLO": 0.94, "EVHI": 1.07,
            "EVLO": 0.93},
    "load": {"I": 90001, "ID": "1", "STATUS": 1, "AREA": 1, "ZONE": 1, "PL": 100.5, "QL": 20.25,
             "IP": 1.0, "IQ": 2.0, "YP": 3.0, "YQ": 4.0, "OWNER": 1, "SCALE": 1, "INTRPT": 0},
    "fixed_shunt": {"I": 90001, "ID": "1", "STATUS": 1, "GL": 0.5, "BL": -12.5},
    "generator": {"I": 90001, "ID": "1", "PG": 500.0, "QG": 10.0, "QT": 300.0, "QB": -100.0,
                  "VS": 1.01, "IREG": 90001, "MBASE": 550.0, "ZR": 0.0, "ZX": 1.0, "RT": 0.0,
                  "XT": 0.0, "GTAP": 1.0, "STAT": 1, "RMPCT": 100.0, "PT": 600.0, "PB": 50.0,
                  "O1": 1, "F1": 1.0, "O2": 0, "F2": 1.0, "O3": 0, "F3": 1.0, "O4": 0, "F4": 1.0,
                  "WMOD": 0, "WPF": 1.0},
    "branch": {"I": 90001, "J": 90002, "CKT": "1", "R": 0.01, "X": 0.1, "B": 0.02, "RATEA": 500.0,
               "RATEB": 600.0, "RATEC": 700.0, "GI": 0.001, "BI": 0.002, "GJ": 0.003,
               "BJ": 0.004, "ST": 1, "MET": 1, "LEN": 12.5, "O1": 1, "F1": 1.0, "O2": 0,
               "F2": 1.0, "O3": 0, "F3": 1.0, "O4": 0, "F4": 1.0},
    "transformer": {"I": 90002, "J": 90003, "K": 0, "CKT": "1", "CW": 1, "CZ": 1, "CM": 1,
                    "MAG1": 0.001, "MAG2": 0.002, "NMETR": 2, "NAME": "TR", "STAT": 1, "O1": 1,
                    "F1": 1.0, "O2": 0, "F2": 1.0, "O3": 0, "F3": 1.0, "O4": 0, "F4": 1.0,
                    "VECGRP": "VG", "R1-2": 0.005, "X1-2": 0.08, "SBASE1-2": 100.0,
                    "WINDV1": 1.025, "NOMV1": 345.0, "ANG1": 0.0, "RATA1": 500.0,
                    "RATB1": 600.0, "RATC1": 700.0, "COD1": 0, "CONT1": 0, "RMA1": 1.1,
                    "RMI1": 0.9, "VMA1": 1.1, "VMI1": 0.9, "NTP1": 33, "TAB1": 0, "CR1": 0.0,
                    "CX1": 0.0, "CNXA1": 0.0, "WINDV2": 1.0, "NOMV2": 138.0},
    "switched_shunt": dict(
        {"I": 90001, "MODSW": 1, "ADJM": 0, "STAT": 1, "VSWHI": 1.05, "VSWLO": 0.95, "SWREM": 0,
         "RMPCT": 100.0, "RMIDNT": "", "BINIT": 25.0, "N1": 2, "B1": 12.5},
        **dict([("N%d" % n, 0) for n in range(2, 9)] + [("B%d" % n, 0.0) for n in range(2, 9)])),
    "area": {"I": 1, "ISW": 90001, "PDES": 10.5, "PTOL": 5.0, "ARNAME": "AREA ONE"},
    "zone": {"I": 1, "ZONAME": "ZONE ONE"},
    "owner": {"I": 1, "OWNAME": "OWNER ONE"},
}


def test_positional_layout_matches_the_v33_documentation():
    # Records typed by hand in the PowerModels.jl pti.jl field order, so a wrong table is not
    # hidden by a writer that reads the same table.
    text = fixture.raw_text({})
    for section, lines in _LITERALS.items():
        text = _insert_before(text, section, lines)
    case = raw.parse_raw(text)
    for section, expected in _EXPECTED.items():
        assert len(case.sections[section]) == 1
        assert case.sections[section][0].values == expected, "a field of one section moved"


def test_field_tables_are_self_consistent_and_match_the_fixture_order():
    assert raw.SECTION_ORDER[33] == fixture.V33_ORDER
    assert set(raw.SUPPORTED_SECTIONS) <= set(raw.SECTION_ORDER[33])
    tables = raw.FIELD_TABLES[33]
    assert {"transformer_1", "transformer_2", "transformer_3", "transformer_4"} <= set(tables)
    for name, spec in tables.items():
        assert len(set(spec.names)) == len(spec.names)
        assert 1 <= spec.required <= len(spec.names)
        for field in spec.names[spec.required:]:
            assert field in spec.defaults, "a field after the required ones has no default"
        assert set(spec.defaults) <= set(spec.names)
    lengths = {name: len(spec.names) for name, spec in tables.items()}
    assert lengths["bus"] == 13 and lengths["load"] == 14 and lengths["fixed_shunt"] == 5
    assert lengths["generator"] == 28 and lengths["branch"] == 24 and lengths["switched_shunt"] == 26
    assert [lengths["transformer_%d" % n] for n in (1, 2, 3, 4)] == [21, 3, 17, 2]


def test_terminator_comments_and_comment_lines_are_tolerated():
    text = fixture.raw_text(_records())
    bus_end = fixture.terminator_line("bus")
    plain = text.replace(bus_end, "0", 1)
    older = text.replace(bus_end, "0 / " + "END" + " OF BUS DATA", 1)
    commented = text.replace(bus_end, "@! a comment line\n\n" + bus_end, 1)
    base = raw.parse_raw(text)
    counts = [len(items) for items in base.sections.values()]
    for variant in (plain, older, commented):
        parsed = raw.parse_raw(variant)
        assert [len(items) for items in parsed.sections.values()] == counts
        assert _without_names(parsed) == _without_names(base)
    # The base frequency comes from the header and defaults to 60 when the field is absent.
    assert base.base_frequency_hz == 60.0 and base.sbase_mva == 100.0 and base.ic == 0
    short = _replace_line(text, 1, "0, 100.0, 33")
    assert raw.parse_raw(short).base_frequency_hz == 60.0
    fifty = raw.parse_raw(fixture.raw_text(_records(), frequency=50.0))
    assert fifty.base_frequency_hz == 50.0
