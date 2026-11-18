"""
Scaling, registry and contract tests of the pandapower adapter (pandapower-solver Phase 2, plan
02-03: ENG-01 and the scaling half of ENG-04).

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_study_fixture`), written into tmp_path only; the
placeholder mapping is written there too. The adapter runs on the real solver. The behavioural
contract compares `PsseApi` on the fake psspy with `PandapowerApi`: types, ordering and refusals,
never numbers (the two networks differ). Failure messages are counts only.
"""

import math
import os

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import mapping as mapping_module, study  # noqa: E402
from pandapower_job import api as pandapower_api  # noqa: E402
from pandapower_job import scaling  # noqa: E402


def _relative(first, second):
    return abs(first - second) / max(abs(first), abs(second), 1e-300)


def _scratch(tmp_path):
    path = tmp_path / "scratch"
    path.mkdir()
    return str(path)


def test_tracer_one_city_base_through_the_registry(tmp_path):
    case_path = study_fixture.write_case(tmp_path)
    mapping_path = study_fixture.write_placeholder_mapping(tmp_path)
    loaded = mapping_module.load_mapping(mapping_path, allow_placeholder=True)
    records = study_fixture.fixture_records()
    targets = study_fixture.placeholder_targets(records)["AUSTIN"]

    index = study.index_case(study_fixture.fixture_backend(), case_path, loaded,
                             solver="pandapower")
    assert isinstance(index.api, pandapower_api.PandapowerApi)
    assert index.psse_version == pandapower.__version__

    temp_dir = _scratch(tmp_path)
    base = study.prepare_city_base(index, loaded, study_fixture.selection(), "AUSTIN",
                                   study.Budget(max_seconds=1500.0), temp_dir)
    assert base.solve.converged

    totals = index.api.read_totals()
    assert _relative(totals.load_mw, targets[0]) <= study.SCALE_TOLERANCE
    assert _relative(totals.gen_mw, targets[1]) <= study.SCALE_TOLERANCE

    city = base.cities["AUSTIN"]
    read = index.api.read_rate(city.branches[0].ref, "RATEA")
    assert _relative(read, city.applied_mva) < 1e-6

    assert base.base_flows
    for flow in base.base_flows:
        if flow.in_service:
            assert math.isfinite(flow.pct)
    for bus in base.base_buses.values():
        if bus.type_code < 4:
            assert math.isfinite(bus.pu)

    assert os.listdir(temp_dir) == []
