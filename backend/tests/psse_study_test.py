"""
Tests for the base of the real PSS/E study (pss-e-integration Phase 2, plan 02-03): IN-02
(the mapping is checked against the case before anything is written), IN-03 (each city's
selected rating reaches PSS/E as read-back per-circuit MVA at the branch's base kV) and STU-01
(a base load flow that is not genuinely solved is a failed run), all at the study level against
the fake psspy.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain
asserts, no test classes, no network). Honest scope: the fake proves call order, value
flow and failure handling, not that real PSS/E accepts these calls (the Phase 3 probe does).
"""

import copy
import datetime
import json
import math
import os
import sys
import tempfile

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
import psse_fakes  # noqa: E402
from psse_job import (  # noqa: E402
    constants, contract, dispatch, mapping, psse_api, ratings, run_record, settings, study, units,
)

GOLDEN = os.path.join(_HERE, "data", "psse_call_surface.json")
EXAMPLE =os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)
AUSTIN_REF = settings.BranchRef(90001, 90002, "1")


def _registered(tmp_path, case=None, solver=None, fake=None):
    """(fake, case path): the case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy(solver=solver) if fake is None else fake
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _mapping(cities=None, **changes):
    """The example mapping (placeholder allowed); `cities` maps a city to CityMapping field
    replacements and `changes` replace study settings."""
    loaded = mapping.load_mapping(EXAMPLE, allow_placeholder=True)
    table = dict(loaded.cities)
    for city, fields in (cities or {}).items():
        table[city] = table[city]._replace(**fields)
    return loaded._replace(cities=table, settings=loaded.settings._replace(**changes))


def _selection(provisional=True):
    rows = psse_fakes.latest_rows(NOW, provisional=provisional)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)


def _writes(fake):
    """The recorded calls that change the case, solve it or save it."""
    return [call for call in fake.fake_calls
            if call[0] in ("branch_chng_3", "fnsl", "save", "bsys", "scal_2")]


def test_tracer_base_on_placeholder_case(tmp_path):
    fake, path = _registered(tmp_path)
    before = run_record.file_sha256(path)
    base = study.prepare_base(fake, path, _mapping(), _selection(provisional=True))
    try:
        austin = base.cities["AUSTIN"]
        assert austin.line_voltage_kv == 345.0
        expected = units.circuit_mva(1825.0, 2, 345.0)
        assert austin.applied_mva == expected
        assert round(austin.applied_mva, 1) == 2181.1
        assert fake.fake_state.branch(90001, 90002, "1")["rates"][0] == expected
        assert austin.rate_before_mva == (1500.0,)
        assert list(base.cities) == list(constants.CITIES)
        assert base.solve.converged is True
        assert base.rate_set == "RATEA"
        assert base.psse_version == "35.6.0"
        assert base.case_label == "PLACEHOLDER_CASE.sav"
        assert os.path.dirname(base.saved_path) == base.temp_dir
        assert os.path.normcase(base.saved_path) != os.path.normcase(path)
        assert fake.fake_saved_paths == [base.saved_path]
        assert os.path.isfile(base.saved_path)
    finally:
        study.cleanup_base(base)
    assert not os.path.exists(base.temp_dir)
    assert run_record.file_sha256(path) == before


# ──────────────────────────────────────────────────────────────────────────────
# The mapping check before any write, and the rating units
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


@pytest.fixture
def prepared(tmp_path):
    """prepare_base(...) -> (fake, case path, base); every base made is cleaned up afterwards."""
    made = []

    def run(case=None, solver=None, fake=None, mapping_=None, selection=None, budget=None):
        fake, path = _registered(tmp_path, case=case, solver=solver, fake=fake)
        base = study.prepare_base(
            fake, path, _mapping() if mapping_ is None else mapping_,
            _selection() if selection is None else selection, budget=budget)
        made.append(base)
        return fake, path, base

    yield run
    for base in made:
        study.cleanup_base(base)


def _fails(tmp_path, stage, case=None, mapping_=None, selection=None, fake=None, solver=None):
    """Run prepare_base expecting StudyFailed at `stage`; returns (fake, the failure)."""
    fake, path = _registered(tmp_path, case=case, fake=fake, solver=solver)
    with pytest.raises(contract.StudyFailed) as caught:
        study.prepare_base(fake, path, _mapping() if mapping_ is None else mapping_,
                           _selection() if selection is None else selection)
    assert caught.value.stage == stage
    return fake, caught.value


def _with_branch(case, from_bus, to_bus, buses=(), kv=345.0, kind="line", status=1):
    """`case` plus the given buses (number, kV, type) and one branch."""
    for number, bus_kv, type_code in buses:
        case.add_bus(number, type_code=type_code, base_kv=bus_kv)
    case.add_branch(from_bus, to_bus, "1", kind=kind, status=status, rates=(900.0, 990.0, 1080.0))
    return case


def _austin_also(*refs):
    return {"AUSTIN": {"branches": mapping.load_mapping(
        EXAMPLE, allow_placeholder=True).cities["AUSTIN"].branches + tuple(refs)}}


def test_check_missing_branch_fails_before_any_write(tmp_path):
    missing = settings.BranchRef(90001, 90099, "1")
    fake, failure = _fails(tmp_path, "mapping", mapping_=_mapping(
        cities={"AUSTIN": {"branches": (missing,)}}))
    assert "AUSTIN" in failure.message
    assert "90001-90099-1 is not in the case" in failure.message
    assert _writes(fake) == []
    assert fake.fake_saved_paths == []


def _case_out_of_service():
    case = fake_module.placeholder_case()
    case.branch(90001, 90002, "1")["status"] = 0
    return case


def _case_with_transformer():
    return _with_branch(fake_module.placeholder_case(), 90001, 90003,
                        buses=[(90003, 345.0, 1)], kind="transformer")


def _case_with_kv_step():
    return _with_branch(fake_module.placeholder_case(), 90002, 90090, buses=[(90090, 138.0, 1)])


def _case_with_second_voltage():
    return _with_branch(fake_module.placeholder_case(), 90091, 90092,
                        buses=[(90091, 138.0, 1), (90092, 138.0, 1)])


def _case_with_isolated_bus():
    case = fake_module.placeholder_case()
    case.add_bus(90093, type_code=4)
    return case


@pytest.mark.parametrize("cause, case_factory, edit, fragment", [
    ("out_of_service", _case_out_of_service, {}, "AUSTIN: branch 90001-90002-1 is out of service"),
    ("transformer", _case_with_transformer,
     {"cities": _austin_also(settings.BranchRef(90001, 90003, "1"))},
     "AUSTIN: branch 90001-90003-1 is a two-winding transformer, not a line"),
    ("endpoint_kv_mismatch", _case_with_kv_step,
     {"cities": _austin_also(settings.BranchRef(90002, 90090, "1"))},
     "AUSTIN: branch 90002-90090-1 has endpoints of different base kV"),
    ("mixed_city_kv", _case_with_second_voltage,
     {"cities": _austin_also(settings.BranchRef(90091, 90092, "1"))},
     "AUSTIN: mapped branches have different base kV [138.0, 345.0]"),
    ("sink_missing", fake_module.placeholder_case,
     {"cities": {"AUSTIN": {"sink_buses": (99999,)}}}, "AUSTIN: sink bus 99999 is not in the case"),
    ("sink_isolated", _case_with_isolated_bus,
     {"cities": {"AUSTIN": {"sink_buses": (90093,)}}}, "AUSTIN: sink bus 90093 is isolated"),
    ("extra_outage_missing", fake_module.placeholder_case,
     {"contingency_extra": (settings.BranchRef(90001, 90099, "1"),)},
     "contingency.extra: branch 90001-90099-1 is not a line in the case"),
])
def test_check_failure_matrix(tmp_path, cause, case_factory, edit, fragment):
    fake, failure = _fails(tmp_path, "mapping", case=case_factory(), mapping_=_mapping(**edit))
    assert fragment in failure.message, cause
    assert _writes(fake) == []
    assert fake.fake_saved_paths == []
    assert os.listdir(tempfile.gettempdir()) == []


def test_check_reports_all_problems_together(tmp_path):
    edit = {
        "AUSTIN": {"branches": (settings.BranchRef(90001, 90099, "1"),)},
        "MIDLAND": {"sink_buses": (99999,)},
    }
    fake, failure = _fails(tmp_path, "mapping", mapping_=_mapping(
        cities=edit, contingency_extra=(settings.BranchRef(90031, 90099, "1"),)))
    assert "AUSTIN: branch 90001-90099-1 is not in the case" in failure.message
    assert "MIDLAND: sink bus 99999 is not in the case" in failure.message
    assert "contingency.extra: branch 90031-90099-1" in failure.message
    assert failure.message.count("; ") == 2
    assert _writes(fake) == []


def test_check_accepts_reversed_orientation(prepared):
    reversed_ref = settings.BranchRef(90002, 90001, "1")
    fake, _, base = prepared(mapping_=_mapping(cities={"AUSTIN": {"branches": (reversed_ref,)}}))
    assert base.cities["AUSTIN"].branches == (study.ResolvedBranch(AUSTIN_REF, 345.0),)
    assert fake.fake_state.branch(90001, 90002, "1")["rates"][0] == base.cities["AUSTIN"].applied_mva
    writes = [call for call in fake.fake_calls if call[0] == "branch_chng_3"]
    assert [(call[2]["ibus"], call[2]["jbus"]) for call in writes][:1] == [(90001, 90002)]


def _expected_mva(city, kv=345.0):
    return units.circuit_mva(constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city],
                             constants.SUBCONDUCTORS_PER_PHASE[city], kv)


def test_units_written_mva_per_city_at_345_kv(prepared):
    fake, _, base = prepared()
    rounded = {}
    for city, (source, sink) in fake_module.PLACEHOLDER_CITY_BUSES.items():
        written = fake.fake_state.branch(source, sink, "1")["rates"][0]
        assert written == pytest.approx(_expected_mva(city), rel=1e-9)
        assert base.cities[city].applied_mva == written
        rounded[city] = round(written, 1)
        assert fake.fake_state.branch(source, sink, "2")["rates"][0] == 500.0
    assert rounded == {"AUSTIN": 2181.1, "CORPUS_CHRISTI": 1792.7, "MIDLAND": 2240.8,
                       "EL_PASO": 788.8}


def test_units_follow_case_base_kv_138(prepared):
    case = fake_module.placeholder_case()
    case.buses[90031]["base_kv"] = 138.0
    case.buses[90032]["base_kv"] = 138.0
    fake, _, base = prepared(case=case)
    el_paso = base.cities["EL_PASO"]
    assert el_paso.line_voltage_kv == 138.0
    assert el_paso.applied_mva == units.circuit_mva(1320.0, 1, 138.0)
    assert fake.fake_state.branch(90031, 90032, "1")["rates"][0] == el_paso.applied_mva
    assert base.cities["AUSTIN"].line_voltage_kv == 345.0


def test_units_parallel_circuits_each_get_the_circuit_mva(prepared):
    second = settings.BranchRef(90001, 90002, "2")
    fake, _, base = prepared(mapping_=_mapping(cities=_austin_also(second)))
    expected = units.circuit_mva(1825.0, 2, 345.0)
    assert fake.fake_state.branch(90001, 90002, "1")["rates"][0] == expected
    assert fake.fake_state.branch(90001, 90002, "2")["rates"][0] == expected
    assert round(expected, 1) == 2181.1
    assert base.cities["AUSTIN"].applied_mva == expected
    assert base.cities["AUSTIN"].rate_before_mva == (1500.0, 500.0)


def test_units_every_listed_rate_set_written(prepared):
    fake, _, base = prepared(mapping_=_mapping(rate_sets=("RATEA", "RATEB")))
    rates = fake.fake_state.branch(90001, 90002, "1")["rates"]
    expected = base.cities["AUSTIN"].applied_mva
    assert rates[0] == expected
    assert rates[1] == expected
    assert rates[2] == 1800.0
    assert base.rate_set == "RATEA+RATEB"
    writes = [call for call in fake.fake_calls if call[0] == "branch_chng_3"]
    assert len(writes) == 8


class _NoStore(fake_module.FakePsspy):
    """Accepts a rating write and silently keeps the old value."""

    def branch_chng_3(self, ibus, jbus, ckt, intgar, realar, ratings, namear):
        return 0


class _Reject(fake_module.FakePsspy):
    """Refuses every rating write as 'branch not found'."""

    def branch_chng_3(self, ibus, jbus, ckt, intgar, realar, ratings, namear):
        return 9


def test_units_read_back_enforced(tmp_path):
    fake, failure = _fails(tmp_path, "apply_ratings", fake=_NoStore())
    assert "read back" in failure.message
    assert "AUSTIN 90001-90002-1 RATEA" in failure.message
    assert [call for call in fake.fake_calls if call[0] == "fnsl"] == []
    assert fake.fake_saved_paths == []


def test_units_call_error_is_apply_ratings(tmp_path):
    fake, failure = _fails(tmp_path, "apply_ratings", fake=_Reject())
    assert "branch_chng_3" in failure.message
    assert "AUSTIN 90001-90002-1" in failure.message
    assert [call for call in fake.fake_calls if call[0] == "fnsl"] == []


def test_units_rate_before_recorded(prepared):
    _, _, base = prepared()
    assert base.cities["AUSTIN"].rate_before_mva == (1500.0,)
    assert all(city.rate_before_mva == (1500.0,) for city in base.cities.values())
    _, _, second = prepared(mapping_=_mapping(rate_sets=("RATEB", "RATEA")))
    assert second.cities["AUSTIN"].rate_before_mva == (1650.0,)


def test_static_fallback_applies_static_amps(prepared):
    selection = _selection(provisional=True)
    assert all(choice.source == constants.SOURCE_STATIC for choice in selection.choices.values())
    fake, _, base = prepared(selection=selection)
    austin = base.cities["AUSTIN"]
    assert austin.applied_amps_circuit == 1825.0 * 2
    assert austin.applied_mva == units.circuit_mva(1825.0, 2, 345.0)
    assert fake.fake_state.branch(90001, 90002, "1")["rates"][0] == austin.applied_mva
    writes = [call for call in fake.fake_calls if call[0] == "branch_chng_3"]
    assert len(writes) == 4


def test_static_fresh_row_applies_row_amps(prepared):
    selection = _selection(provisional=False)
    assert all(choice.source == constants.SOURCE_CITY_RATING
               for choice in selection.choices.values())
    fake, _, base = prepared(selection=selection)
    austin = base.cities["AUSTIN"]
    assert selection.choices["AUSTIN"].amps_per_conductor == pytest.approx(2007.5)
    assert austin.applied_mva == units.circuit_mva(selection.choices["AUSTIN"].amps_per_conductor,
                                                   2, 345.0)
    assert austin.applied_mva != units.circuit_mva(1825.0, 2, 345.0)
    for city, (source, sink) in fake_module.PLACEHOLDER_CITY_BUSES.items():
        choice = selection.choices[city]
        expected = units.circuit_mva(choice.amps_per_conductor, choice.subconductors_per_phase,
                                     345.0)
        assert fake.fake_state.branch(source, sink, "1")["rates"][0] == expected
    writes = [call for call in fake.fake_calls if call[0] == "branch_chng_3"]
    assert len(writes) == 4


# ──────────────────────────────────────────────────────────────────────────────
# The base load flow under the strict rule, the study area, the temporary file, the budget
# ──────────────────────────────────────────────────────────────────────────────


def _outcome(**fields):
    """A solver that always gives the same SolveOutcome (fields replace the defaults)."""
    outcome = fake_module.SolveOutcome(**fields)
    return lambda case: outcome


def _stale_zero_fake(tmp_path, solver):
    """A fake whose solved() already reads 0 from an earlier converged fnsl, then `solver`."""
    fake, path = _registered(tmp_path)
    assert fake.case(path) == 0
    assert fake.fnsl() == 0 and fake.solved() == 0
    fake.fake_solver = solver
    fake.fake_calls = []
    return fake


@pytest.mark.parametrize("behaviour, fragment", [
    ("solved_1", "iteration limit exceeded"),
    ("solved_2", "blown up"),
    ("solved_3", "terminated by non-divergent option"),
    ("solved_5", "singular Jacobian"),
    ("fnsl_2_with_stale_zero", "converted generators"),
    ("fnsl_3_with_stale_zero", "without swing bus"),
])
def test_load_flow_not_converged_matrix(tmp_path, behaviour, fragment):
    solvers = {
        "solved_1": _outcome(ierr=0, solved=1),
        "solved_2": _outcome(ierr=0, solved=2),
        "solved_3": _outcome(ierr=0, solved=3),
        "solved_5": _outcome(ierr=0, solved=5),
        "fnsl_2_with_stale_zero": _outcome(ierr=2, solved=None),
        "fnsl_3_with_stale_zero": _outcome(ierr=3, solved=None),
    }
    solver = solvers[behaviour]
    fake = _stale_zero_fake(tmp_path, solver) if "stale_zero" in behaviour else None
    fake, failure = _fails(tmp_path, "load_flow", fake=fake, solver=None if fake else solver)
    assert "did not converge" in failure.message
    assert fragment in failure.message
    assert fake.fake_saved_paths == []
    assert [call for call in fake.fake_calls if call[0] == "save"] == []
    assert os.listdir(tempfile.gettempdir()) == []


def test_load_flow_message_names_meaning_and_converted_generators(tmp_path):
    _, iteration = _fails(tmp_path, "load_flow", solver=_outcome(ierr=0, solved=1))
    assert iteration.message == (
        "load flow did not converge: ierr=0 solved=1 (iteration limit exceeded)")
    _, converted = _fails(tmp_path, "load_flow", solver=_outcome(ierr=2, solved=None))
    assert converted.message.startswith("load flow did not converge: ierr=2 solved=")
    assert "generators are converted" in converted.message
    assert "converted generators; Power Systems must supply an unconverted case" in converted.message
    assert "converted generators" not in iteration.message


def test_load_flow_mismatch_guard(tmp_path, prepared):
    _, failure = _fails(tmp_path, "load_flow", solver=_outcome(ierr=0, solved=0, mismatch=5.0))
    assert failure.message == "load flow mismatch 5 MVA exceeds 1 MVA"
    # exactly the configured limit is still accepted
    _, _, base = prepared(solver=_outcome(ierr=0, solved=0, mismatch=1.0))
    assert base.solve.mismatch_mva == 1.0
    # and the limit is the configured one
    _, failure = _fails(tmp_path, "load_flow", solver=_outcome(ierr=0, solved=0, mismatch=0.5),
                        mapping_=_mapping(max_mismatch_mva=0.25))
    assert "0.5 MVA exceeds 0.25 MVA" in failure.message


def test_load_flow_collapsed_solution_guard(tmp_path):
    fake, failure = _fails(tmp_path, "load_flow", solver=_outcome(
        ierr=0, solved=0, voltages={90002: 0.3}))
    assert failure.message == "collapsed solution: 1 in-service buses below 0.5 pu"
    assert fake.fake_saved_paths == []
    # an isolated bus (type 4) at 0 pu is not a collapse
    case = fake_module.placeholder_case()
    case.add_bus(90093, type_code=4, pu=0.0)
    fake, path = _registered(tmp_path, case=case)
    base = study.prepare_base(fake, path, _mapping(), _selection())
    study.cleanup_base(base)


def _resolved_of(base):
    return dict((city, base.cities[city].branches) for city in constants.CITIES)


def _sinks_of(base):
    return dict((city, base.cities[city].sink_buses) for city in constants.CITIES)


def test_base_area_neighbourhood_hops(prepared):
    case = fake_module.placeholder_case()
    case.branch(90001, 90002, "2")["status"] = 0
    _, _, base = prepared(case=case)

    def area(**changes):
        return study.study_area(base.lines, base.buses, _resolved_of(base),
                                base.settings._replace(**changes), _sinks_of(base))

    zero = area(contingency_hops=0)
    assert zero.by_city["AUSTIN"] == (frozenset(["90001-90002-1"]), frozenset([90001, 90002]))
    assert zero.branch_keys == frozenset(
        ["90001-90002-1", "90011-90012-1", "90021-90022-1", "90031-90032-1"])
    assert len(zero.buses) == 8
    one = area(contingency_hops=1)
    assert one.by_city["AUSTIN"] == (
        frozenset(["90001-90002-1", "90000-90001-1", "90000-90001-2"]),
        frozenset([90000, 90001, 90002]))
    two = area(contingency_hops=2)
    austin_keys, austin_buses = two.by_city["AUSTIN"]
    assert "90000-90011-1" in austin_keys and "90000-90031-2" in austin_keys
    assert austin_buses == frozenset([90000, 90001, 90002, 90011, 90021, 90031])
    assert "90011-90012-1" not in austin_keys
    everything = area(contingency_scope="all")
    assert len(everything.branch_keys) == 15  # 16 lines, one of them out of service
    assert "90001-90002-2" not in everything.branch_keys
    assert len(everything.buses) == 9
    assert everything.by_city["AUSTIN"] == area().by_city["AUSTIN"]  # the city's own neighbourhood
    high = area(contingency_hops=1, min_monitor_kv=400.0)
    assert high.by_city["AUSTIN"][1] == frozenset([90002])


def test_base_area_all_scope_counts_every_line(prepared):
    _, _, base = prepared()
    everything = study.study_area(base.lines, base.buses, _resolved_of(base),
                                  base.settings._replace(contingency_scope="all"), _sinks_of(base))
    assert len(everything.branch_keys) == 16
    assert base.area.by_city["AUSTIN"][0] == frozenset(
        ["90001-90002-1", "90001-90002-2", "90000-90001-1", "90000-90001-2",
         "90000-90011-1", "90000-90011-2", "90000-90021-1", "90000-90021-2",
         "90000-90031-1", "90000-90031-2"])


def test_base_saved_to_temp_never_case_path(prepared):
    fake, path, base = prepared()
    assert os.path.basename(base.temp_dir).startswith("psse_job_")
    assert os.path.dirname(base.temp_dir) == tempfile.gettempdir()
    assert os.path.dirname(base.saved_path) == base.temp_dir
    assert fake.fake_saved_paths == [base.saved_path]
    for saved in fake.fake_saved_paths:
        assert os.path.normcase(os.path.abspath(saved)) != os.path.normcase(os.path.abspath(path))
    with pytest.raises(psse_api.CaseProtected):
        base.api.save_case(path)
    assert fake.fake_saved_paths == [base.saved_path]
    with open(path, "rb") as handle:
        assert handle.read() == b"MARKER - Power Systems' case"


class _SaveFails(fake_module.FakePsspy):
    def save(self, sfile):
        return 3


def test_base_save_failure_is_stage_contingency_and_cleans_up(tmp_path):
    fake, failure = _fails(tmp_path, "contingency", fake=_SaveFails())
    assert "temporary file" in failure.message
    assert "file error" in failure.message
    assert os.listdir(tempfile.gettempdir()) == []


def test_base_cleanup_removes_temp_dir(prepared):
    _, path, base = prepared()
    before = run_record.file_sha256(path)
    assert os.path.isdir(base.temp_dir)
    study.cleanup_base(base)
    assert not os.path.exists(base.temp_dir)
    study.cleanup_base(base)  # a second call is harmless
    assert os.path.isfile(path)
    assert run_record.file_sha256(path) == before
    assert os.listdir(tempfile.gettempdir()) == []


def test_base_budget_exceeded_fails_stage(prepared):
    now = [100.0]
    budget = study.Budget(clock=lambda: now[0], max_seconds=10)
    now[0] = 109.0
    budget.check("contingency")
    now[0] = 110.0
    budget.check("contingency")
    now[0] = 111.0
    with pytest.raises(contract.StudyFailed) as caught:
        budget.check("contingency")
    assert caught.value.stage == "contingency"
    assert "run-time budget of 10 s exceeded" in caught.value.message
    assert budget.elapsed() == 11.0
    _, _, base = prepared(budget=budget)
    assert base.budget is budget
    _, _, default = prepared()
    assert default.budget.max_seconds == default.settings.max_runtime_seconds == 1500.0


def test_base_load_case_failure_names_label_only(tmp_path):
    fake = fake_module.FakePsspy()
    path = str(tmp_path / "private_dir" / "case.sav")
    with pytest.raises(contract.StudyFailed) as caught:
        study.prepare_base(fake, path, _mapping(), _selection())
    assert caught.value.stage == "load_case"
    assert "case.sav" in caught.value.message
    assert "private_dir" not in caught.value.message
    assert str(tmp_path) not in caught.value.message
    assert _writes(fake) == []


# ──────────────────────────────────────────────────────────────────────────────
# The whole study (plan 02-06): make_study and prepare_run against the fake psspy, no database
# ──────────────────────────────────────────────────────────────────────────────


def _run_study(fake, path, mapping_=None, selection=None):
    """One call of make_study's callable; returns the StudyResults."""
    callable_ = study.make_study(fake, path, _mapping() if mapping_ is None else mapping_)
    return callable_(_selection() if selection is None else selection, None)


def _fresh_case_calls(fake, path):
    """The recorded case() calls that load Power Systems' case file itself."""
    return [call for call in fake.fake_calls
            if call[0] == "case" and os.path.normcase(os.path.abspath(call[1][0]))
            == os.path.normcase(os.path.abspath(path))]


def test_full_study_placeholder_results_validate(tmp_path):
    fake, path = _registered(tmp_path)
    selection = _selection()
    results = _run_study(fake, path, selection=selection)
    run_record.validate_results(results, selection)
    assert len(results.dispatch) == 4
    assert len(results.margins) == 4
    assert len(results.contingencies) == 10
    assert results.n_contingencies == 16
    assert results.rate_set == "RATEA"
    assert results.psse_version == "35.6.0"
    assert [row["city"] for row in results.dispatch] == list(constants.CITIES)
    assert [row["city"] for row in results.margins] == list(constants.CITIES)
    assert os.listdir(tempfile.gettempdir()) == []


def test_full_study_calls_stay_inside_surface(tmp_path):
    fake, path = _registered(tmp_path)
    _run_study(fake, path)
    assert fake.fake_calls
    for name, args, kwargs in fake.fake_calls:
        assert name in psse_api.SURFACE_BY_NAME, name
        row = psse_api.SURFACE_BY_NAME[name]
        assert set(kwargs) <= set(row.parameters), name
        assert len(args) + len(kwargs) <= len(row.parameters), name


def test_full_study_never_saves_or_changes_the_case(tmp_path):
    fake, path = _registered(tmp_path)
    before = run_record.file_sha256(path)
    callable_ = study.make_study(fake, path, _mapping())
    first = callable_(_selection(), None)
    assert len(_fresh_case_calls(fake, path)) == 1
    first_saved = list(fake.fake_saved_paths)
    assert first_saved
    for saved in fake.fake_saved_paths:
        assert os.path.normcase(os.path.abspath(saved)) != os.path.normcase(os.path.abspath(path))
    assert run_record.file_sha256(path) == before

    calls_before = len(fake.fake_calls)
    second = callable_(_selection(), None)
    assert second == first
    assert len(_fresh_case_calls(fake, path)) == 2
    later = fake.fake_calls[calls_before:]
    assert [call for call in later if call[0] == "case"][0][1] == (path,)
    assert [call for call in later if call[0] == "save"][0][1][0] not in first_saved
    assert run_record.file_sha256(path) == before
    with open(path, "rb") as handle:
        assert handle.read() == b"MARKER - Power Systems' case"


def test_full_study_new_adapter_per_run(tmp_path, monkeypatch):
    made = []
    real = psse_api.PsseApi

    class Counting(real):
        def __init__(self, *args, **kwargs):
            real.__init__(self, *args, **kwargs)
            made.append(self)

    monkeypatch.setattr(psse_api, "PsseApi", Counting)
    fake, path = _registered(tmp_path)
    callable_ = study.make_study(fake, path, _mapping())
    callable_(_selection(), None)
    callable_(_selection(), None)
    assert len(made) == 2
    assert made[0] is not made[1]


def test_full_study_cleans_temp_dir_on_success_and_failure(tmp_path):
    fake, path = _registered(tmp_path)
    _run_study(fake, path)
    assert os.listdir(tempfile.gettempdir()) == []
    assert fake.fake_saved_paths
    assert not any(os.path.exists(saved) for saved in fake.fake_saved_paths)

    flat = lambda case: fake_module.radial_solver(_frozen(case))  # noqa: E731
    fake, path = _registered(tmp_path, solver=flat)
    with pytest.raises(contract.StudyFailed) as caught:
        _run_study(fake, path, mapping_=_mapping(transfer_extra_steps=3))
    assert caught.value.stage == "voltage_margin"
    assert fake.fake_saved_paths
    assert os.listdir(tempfile.gettempdir()) == []
    assert not any(os.path.exists(saved) for saved in fake.fake_saved_paths)


def _frozen(case):
    """A copy of `case` whose sink loads never rise (the transfer then loads nothing)."""
    frozen = copy.deepcopy(case)
    for bus in frozen.loads:
        frozen.loads[bus] = [620.0, 620.0 * math.tan(math.acos(0.95))]
    return frozen


def test_full_study_details_are_json_safe(tmp_path, monkeypatch):
    real = dispatch.dispatch_details

    def hostile(city_base, rate_sets, bounded_by):
        details = real(city_base, rate_sets, bounded_by)
        details["not_a_number"] = float("nan")
        details["unbounded"] = float("inf")
        details["when"] = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.timezone.utc)
        details["nested"] = {1: (float("-inf"), 2.5)}
        return details

    monkeypatch.setattr(dispatch, "dispatch_details", hostile)
    fake, path = _registered(tmp_path)
    results = _run_study(fake, path)
    for rows in (results.dispatch, results.margins, results.contingencies):
        for row in rows:
            json.dumps(row["details"], allow_nan=False)
    first = results.dispatch[0]["details"]
    assert first["not_a_number"] is None
    assert first["unbounded"] is None
    assert first["when"] == "2026-10-28T12:00:00+00:00"
    assert first["nested"] == {"1": [None, 2.5]}


def test_full_study_dispatch_failure_is_stage_dispatch(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise ValueError("inconsistent search")

    monkeypatch.setattr(dispatch, "build_dispatch_row", refuse)
    fake, path = _registered(tmp_path)
    with pytest.raises(contract.StudyFailed) as caught:
        _run_study(fake, path)
    assert caught.value.stage == "dispatch"
    assert caught.value.message == "AUSTIN: inconsistent search"
    assert os.listdir(tempfile.gettempdir()) == []


def test_full_study_passes_the_search_bound_to_the_dispatch_tripwire(tmp_path, monkeypatch):
    """build_dispatch_row's tripwire is off without bounded_by, and no search the fake can run
    trips it, so only a spy shows make_study keeps passing the margin's own bound."""
    seen = []
    real = dispatch.build_dispatch_row

    def spy(*args, **kwargs):
        seen.append(kwargs.get("bounded_by"))
        return real(*args, **kwargs)

    monkeypatch.setattr(dispatch, "build_dispatch_row", spy)
    fake, path = _registered(tmp_path)
    results = _run_study(fake, path)
    assert len(seen) == len(constants.CITIES)
    assert all(bound in dispatch.BOUNDS for bound in seen)
    assert seen[constants.CITIES.index("AUSTIN")] == "voltage_criterion"
    assert seen[constants.CITIES.index("EL_PASO")] == "dlr_rating"
    assert [row["limiting_factor"] for row in results.dispatch][:1] == ["voltage_stability"]


def _call_surface(fake):
    """First-seen ordered [name, sorted keyword names] of every recorded call."""
    seen = []
    for name, args, kwargs in fake.fake_calls:
        item = [name, sorted(kwargs)]
        if item not in seen:
            seen.append(item)
    return seen


def test_call_surface_matches_golden(tmp_path):
    fake, path = _registered(tmp_path)
    _run_study(fake, path)
    surface = _call_surface(fake)
    if os.environ.get("PSSE_UPDATE_CALL_SURFACE") == "1":
        os.makedirs(os.path.dirname(GOLDEN), exist_ok=True)
        with open(GOLDEN, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(surface, handle, indent=2)
            handle.write("\n")
        return
    with open(GOLDEN, encoding="utf-8") as handle:
        golden = json.load(handle)
    assert surface == golden, (
        "the study's psspy call surface changed; if that is intended, regenerate "
        "backend/tests/data/psse_call_surface.json deliberately with PSSE_UPDATE_CALL_SURFACE=1 "
        "and review the diff")


def test_json_safe_converts_nan_and_datetimes():
    moment = datetime.datetime(2026, 10, 28, 12, 0, tzinfo=datetime.timezone.utc)
    safe = study.json_safe({
        "nan": float("nan"), "inf": float("inf"), "ok": 1.5, "n": 3, "flag": True, "none": None,
        "text": "x", "when": moment, "day": datetime.date(2026, 10, 28), "tuple": (1, 2),
        7: [float("-inf")], "object": object,
    })
    assert safe["nan"] is None and safe["inf"] is None
    assert safe["ok"] == 1.5 and safe["n"] == 3 and safe["flag"] is True and safe["none"] is None
    assert safe["text"] == "x"
    assert safe["when"] == "2026-10-28T12:00:00+00:00"
    assert safe["day"] == "2026-10-28"
    assert safe["tuple"] == [1, 2]
    assert safe["7"] == [None]
    assert safe["object"] == str(object)
    json.dumps(safe, allow_nan=False)


def test_prepare_run_hashes_and_labels(tmp_path):
    fake, path = _registered(tmp_path)
    prepared = study.prepare_run(fake, path, EXAMPLE, allow_placeholder=True)
    assert prepared.case_id == "PLACEHOLDER_CASE.sav"
    assert prepared.case_sha256 == run_record.file_sha256(path)
    assert prepared.mapping_sha256 == run_record.file_sha256(EXAMPLE)
    assert prepared.mapping_error is None
    assert fake.fake_calls == []
    results = prepared.study(_selection(), None)
    assert results.n_contingencies == 16


def test_prepare_run_bad_mapping_becomes_mapping_failure(tmp_path):
    fake, path = _registered(tmp_path)
    bad = str(tmp_path / "bad_mapping.json")
    with open(bad, "w", encoding="utf-8") as handle:
        handle.write("{not json")
    prepared = study.prepare_run(fake, path, bad, allow_placeholder=True)
    assert prepared.mapping_sha256 is None
    assert prepared.mapping_error
    assert prepared.case_id == "PLACEHOLDER_CASE.sav"
    assert prepared.case_sha256 == run_record.file_sha256(path)
    with pytest.raises(contract.StudyFailed) as caught:
        prepared.study(_selection(), None)
    assert caught.value.stage == "mapping"
    assert "mapping file not usable" in caught.value.message
    assert fake.fake_calls == []
    refused = study.prepare_run(fake, path, EXAMPLE)
    assert refused.mapping_sha256 is None
    assert "placeholder" in refused.mapping_error
