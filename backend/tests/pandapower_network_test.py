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
