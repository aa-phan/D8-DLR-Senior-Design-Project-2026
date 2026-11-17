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
