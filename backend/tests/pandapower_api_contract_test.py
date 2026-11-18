"""
Scaling, registry and contract tests of the pandapower adapter (pandapower-solver Phase 2, plan
02-03: ENG-01 and the scaling half of ENG-04).

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_study_fixture`), written into tmp_path only; the
placeholder mapping is written there too. The adapter runs on the real solver. The behavioural
contract compares `PsseApi` on the fake psspy with `PandapowerApi`: types, ordering and refusals,
never numbers (the two networks differ). Failure messages are counts only.
"""

import collections
import math
import os

import pytest

pandapower = pytest.importorskip("pandapower")

import pandas  # noqa: E402

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import mapping as mapping_module, psse_api, study  # noqa: E402
from pandapower_job import api as pandapower_api  # noqa: E402
from pandapower_job import scaling  # noqa: E402

OFFSET = study_fixture.OFFSET
Target = collections.namedtuple("Target", ["load_mw", "gen_mw"])
_APIS = {}


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


# -- shared state -----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def case_path(tmp_path_factory):
    return study_fixture.write_case(tmp_path_factory.mktemp("pp_contract"))


@pytest.fixture(scope="module")
def unraised_path(tmp_path_factory):
    return study_fixture.write_case(tmp_path_factory.mktemp("pp_unraised"), raise_pt=False)


def _api(path, details=("yes", "no", "yes")):
    """One adapter per case file and details for the module (the master is built once; every
    test starts from load_case, which hands out a fresh copy)."""
    key = (path, details)
    if key not in _APIS:
        _APIS[key] = pandapower_api.PandapowerApi(
            study_fixture.fixture_backend(details=details), protected_path=path)
    api = _APIS[key]
    api.load_case(path)
    return api


def _loads(api):
    return api._net.load.copy()


def _text_forms(*values):
    texts = set()
    for value in values:
        texts.update((repr(value), "%g" % value, "%.1f" % value))
    return sorted(texts)


# -- totals -----------------------------------------------------------------------------------


def test_read_totals_matches_case_totals_and_fixture(case_path):
    api = _api(case_path)
    totals = api.read_totals()
    assert isinstance(totals, psse_api.CaseTotals)
    load, gen = study_fixture.fixture_totals(study_fixture.fixture_records())
    assert abs(totals.load_mw - load) <= 1e-9
    assert abs(totals.gen_mw - gen) <= 1e-9
    shared = scaling.case_totals(api._net, api._backend.scaling_details)
    assert (totals.load_mw, totals.gen_mw) == shared
    assert all(type(value) is float for value in shared)

    # a read of input data is allowed in every state
    api.solve()
    assert api.read_totals() == totals
    api.set_rate(api.branch_table()[0][0], "RATEA", 1000.0)
    assert api.read_totals() == totals

    inconclusive = _api(case_path, details=("inconclusive", "no", "yes"))
    with pytest.raises(ValueError) as caught:
        inconclusive.read_totals()
    assert caught.value.reason == "swing_in_total"


def test_scale_case_reads_back_and_leaves_master(case_path, tmp_path):
    api = _api(case_path)
    master = api._masters[psse_api._normalise_path(case_path)]
    master_load, master_gen = master.load.copy(), master.gen.copy()
    api.solve()
    snapshot_path = os.path.join(str(tmp_path), "snapshot.sav")
    api.save_case(snapshot_path)
    base = api.read_totals()

    records = study_fixture.fixture_records()
    load_mw, gen_mw = study_fixture.placeholder_targets(records)["MIDLAND"]
    api.scale_case(load_mw, gen_mw)

    totals = api.read_totals()
    assert _relative(totals.load_mw, load_mw) <= study.SCALE_TOLERANCE
    assert _relative(totals.gen_mw, gen_mw) <= study.SCALE_TOLERANCE
    assert api._state == pandapower_api.STALE
    with pytest.raises(psse_api.PsseCallError):
        api.branch_loading("RATEA", "current")
    with pytest.raises(psse_api.PsseCallError):
        api.bus_table()

    pandas.testing.assert_frame_equal(master.load, master_load)
    pandas.testing.assert_frame_equal(master.gen, master_gen)
    api.load_case(snapshot_path)
    assert api.read_totals() == base
    assert api.solve().converged
    api.branch_loading("RATEA", "current")


def test_scale_case_refusal_reaches_the_study_as_apply_ratings(unraised_path):
    api = _api(unraised_path, details=("yes", "inconclusive", "yes"))
    own = api.read_totals()
    target = Target(own.load_mw, own.gen_mw * 1.5)

    with pytest.raises(ValueError) as caught:
        api.scale_case(target.load_mw, target.gen_mw)
    assert isinstance(caught.value, scaling.ScalingUndetermined)
    assert caught.value.reason == "clamped_at_limits"
    assert api.read_totals() == own

    with pytest.raises(study.StudyFailed) as failed:
        study.scale_city_case(api, "AUSTIN", target)
    assert failed.value.stage == "apply_ratings"
    assert failed.value.message.startswith("scaling: ")
    forbidden = (_text_forms(target.load_mw, target.gen_mw)
                 + study_fixture.synthetic_target_texts(study_fixture.fixture_records()))
    for text in forbidden:
        assert text not in str(failed.value), text
    assert api.read_totals() == own


def test_scale_case_bad_targets(case_path):
    api = _api(case_path)
    before = api.read_totals()
    for args, text in (
            ((0, 1), "load_mw must be a finite number above 0"),
            ((1, float("nan")), "gen_mw must be a finite number above 0"),
            ((True, 1), "load_mw must be a finite number above 0"),
            ((1, float("inf")), "gen_mw must be a finite number above 0"),
            ((-5.0, 1), "load_mw must be a finite number above 0")):
        with pytest.raises(ValueError) as caught:
            api.scale_case(*args)
        assert str(caught.value) == text
    assert api.read_totals() == before


# -- the margin's subsystem increment ---------------------------------------------------------


def test_scale_load_q_rules(case_path):
    members = [OFFSET + 3, OFFSET + 4]
    for rule in ("yes", "no"):
        api = _api(case_path, details=("yes", "no", rule))
        before = _loads(api)
        api.define_subsystem(0, members)
        api.scale_load(0, 100.0)
        after = _loads(api)
        inside = before.bus.isin(members)
        assert inside.sum() == 2
        factor = (before.p_mw[inside].sum() + 100.0) / before.p_mw[inside].sum()
        for index in before.index[inside]:
            assert _relative(after.p_mw[index], before.p_mw[index] * factor) < 1e-12
            expected_q = before.q_mvar[index] * (factor if rule == "yes" else 1.0)
            assert _relative(after.q_mvar[index], expected_q) < 1e-12
        assert abs(after.p_mw[inside].sum() - (before.p_mw[inside].sum() + 100.0)) < 1e-9
        outside = ~inside
        pandas.testing.assert_frame_equal(after[outside], before[outside])
        assert api._state == pandapower_api.STALE

    api = _api(case_path, details=("yes", "no", "inconclusive"))
    before = _loads(api)
    api.define_subsystem(0, members)
    with pytest.raises(ValueError) as caught:
        api.scale_load(0, 100.0)
    assert caught.value.reason == "q_scales_with_p"
    pandas.testing.assert_frame_equal(_loads(api), before)


def test_scale_load_subsystem_without_load_is_a_no_op(case_path):
    api = _api(case_path)
    before = _loads(api)
    assert not before.bus.isin([OFFSET + 2, OFFSET + 6]).any()
    api.define_subsystem(0, [OFFSET + 2, OFFSET + 6])
    api.scale_load(0, 100.0)
    pandas.testing.assert_frame_equal(_loads(api), before)

    # an out-of-service load does not count either
    api = _api(case_path)
    index = api._net.load.index[api._net.load.bus == OFFSET + 3][0]
    api._net.load.at[index, "in_service"] = False
    before = _loads(api)
    api.define_subsystem(1, [OFFSET + 3])
    api.scale_load(1, 100.0)
    pandas.testing.assert_frame_equal(_loads(api), before)

    # nor does a load that carries no P: there is nothing to share the increment over
    api = _api(case_path)
    index = api._net.load.index[api._net.load.bus == OFFSET + 3][0]
    api._net.load.at[index, "p_mw"] = 0.0
    before = _loads(api)
    api.define_subsystem(1, [OFFSET + 3])
    api.scale_load(1, 100.0)
    pandas.testing.assert_frame_equal(_loads(api), before)


def test_scale_load_and_subsystem_refusals(case_path):
    api = _api(case_path)
    api._subsystems.clear()   # the module shares one adapter, and a subsystem outlives load_case
    bus = OFFSET + 3
    sid_text = "sid must be an integer from 0 to 11"
    buses_text = "buses must be a non-empty list of positive bus numbers"
    for call, text in (
            ((12, [bus]), sid_text), ((True, [bus]), sid_text), ((-1, [bus]), sid_text),
            ((0, []), buses_text), ((0, [0]), buses_text), ((0, [True]), buses_text)):
        with pytest.raises(ValueError) as caught:
            api.define_subsystem(*call)
        assert str(caught.value) == text
    assert api._subsystems == {}

    missing = OFFSET + 500
    with pytest.raises(psse_api.PsseCallError) as caught:
        api.define_subsystem(0, [bus, missing])
    assert str(missing) not in str(caught.value)
    assert api._subsystems == {}

    with pytest.raises(psse_api.PsseCallError):
        api.scale_load(0, 1.0)
    for call in ((13, 1.0), (True, 1.0)):
        with pytest.raises(ValueError) as caught:
            api.scale_load(*call)
        assert str(caught.value) == sid_text

    api.define_subsystem(0, [bus])
    for value in (float("nan"), float("inf"), True, "5", None):
        with pytest.raises(ValueError) as caught:
            api.scale_load(0, value)
        assert str(caught.value) == "increment_mw must be a finite number"

    before = _loads(api)
    for value in (-1e6, -float(before.p_mw[before.bus == bus].sum())):
        with pytest.raises(psse_api.PsseCallError) as caught:
            api.scale_load(0, value)
        assert "whole load" in str(caught.value)
    pandas.testing.assert_frame_equal(_loads(api), before)

    # a subsystem is kept across load_case and is re-defined by the margin before every step
    api.load_case(case_path)
    assert api._subsystems[0] == (bus,)


def test_margin_step_reloads_a_fresh_copy(case_path, tmp_path):
    api = _api(case_path)
    assert api.solve().converged
    base_loads = _loads(api)
    base_flows = api.branch_loading("RATEA", "current")
    snapshot_path = os.path.join(str(tmp_path), "base.sav")
    api.save_case(snapshot_path)

    api.define_subsystem(0, [OFFSET + 3, OFFSET + 4])
    api.scale_load(0, 100.0)
    assert api.solve().converged
    stepped = api.branch_loading("RATEA", "current")
    assert stepped != base_flows

    api.load_case(snapshot_path)
    pandas.testing.assert_frame_equal(_loads(api), base_loads)
    assert api._state == pandapower_api.SOLVED
    assert api.branch_loading("RATEA", "current") == base_flows

    api.load_case(case_path)
    pandas.testing.assert_frame_equal(_loads(api), base_loads)
