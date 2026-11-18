"""
Tests for the pandapower adapter (pandapower-solver Phase 2, plan 02-02: ENG-02 to ENG-04).

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_study_fixture`), written into tmp_path only. The
adapter runs on the real solver. Failure messages are counts only.
"""

import math

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import psse_api  # noqa: E402,F401
from pandapower_job.api import PandapowerApi  # noqa: E402


def _relative(first, second):
    return abs(first - second) / max(abs(first), abs(second), 1e-300)


def _records_rate(records, ref):
    for rec in records["branch"]:
        if (rec["I"], rec["J"], rec["CKT"]) == (ref.from_bus, ref.to_bus, ref.ckt):
            return rec["RATEA"]
    raise AssertionError("branch not in the fixture records")


def test_tracer_case_file_to_current_basis_loading(tmp_path):
    path = study_fixture.write_case(tmp_path)
    api = PandapowerApi(study_fixture.fixture_backend(), protected_path=path)
    api.load_case(path)

    lines, _ = api.branch_table()
    ref = lines[0]
    records = study_fixture.fixture_records()
    assert _relative(api.read_rate(ref, "RATEA"), _records_rate(records, ref)) < 1e-9

    api.set_rate(ref, "RATEA", 1000.0)
    assert _relative(api.read_rate(ref, "RATEA"), 1000.0) < 1e-9

    result = api.solve()
    assert result.converged is True
    assert result.ierr == 0
    assert result.solved_code == 0

    rows = api.branch_loading("RATEA", "current")
    assert [row.key for row in rows] == sorted(row.key for row in rows)
    assert len(rows) == len(lines)
    row = [item for item in rows if item.key == ref.key][0]
    assert _relative(row.rate_mva, 1000.0) < 1e-9
    net = api._net
    index = api._line_index(net, ref.from_bus, ref.to_bus, ref.ckt)
    result_row = net.res_line.loc[index]
    expected = (max(result_row.i_from_ka, result_row.i_to_ka) / net.line.at[index, "max_i_ka"]
                * 100.0)
    assert _relative(row.pct, expected) < 1e-12
    for item in rows:
        if item.in_service:
            assert math.isfinite(item.pct)
