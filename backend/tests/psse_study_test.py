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

import datetime
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
from psse_job import constants, contract, mapping, psse_api, ratings, run_record, settings, study, units  # noqa: E402

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
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
