"""
Tests for the N-1 branch-outage screen (pss-e-integration Phase 2, plan 02-04): STU-02, every
thermal overload and voltage violation of every screened outage with its element, limit,
observed value and the amount exceeded, a non-converging outage as one non_convergence row, and
a stage failure instead of a truncated screen, all against the fake psspy.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain asserts,
no test classes, no network). Honest scope: the fake proves call order, value flow and failure
handling, not that real PSS/E accepts these calls (the Phase 3 probe does).
"""

import datetime
import json
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
    constants, contingency, contract, mapping, psse_api, ratings, run_record, settings, study,
    violations,
)

EXAMPLE = os.path.join(_ROOT, "docs", "data-science", "schema", "psse_mapping_example.json")
NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)


def _registered(tmp_path, case=None, solver=None, fake=None):
    """(fake, case path): the case registered under a path whose file holds a marker."""
    fake = fake_module.FakePsspy(solver=solver) if fake is None else fake
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    with open(path, "wb") as handle:
        handle.write(b"MARKER - Power Systems' case")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    return fake, path


def _mapping(**changes):
    """The example mapping (placeholder allowed) with study settings replaced by `changes`."""
    loaded = mapping.load_mapping(EXAMPLE, allow_placeholder=True)
    return loaded._replace(settings=loaded.settings._replace(**changes))


def _selection(provisional=True):
    rows = psse_fakes.latest_rows(NOW, provisional=provisional)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)


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


def _results_for(selection, rows, n_contingencies):
    """StudyResults around `rows` with Phase 1's valid dispatch and margin rows."""
    template = psse_fakes.fake_results(selection)
    return contract.StudyResults(
        dispatch=template.dispatch, margins=template.margins, contingencies=list(rows),
        n_contingencies=n_contingencies, rate_set="RATEA", psse_version="35.6.0")


def _find(rows, contingency_id, kind, element_id):
    found = [row for row in rows if row["contingency_id"] == contingency_id
             and row["violation_kind"] == kind and row["element_id"] == element_id]
    assert len(found) == 1, (contingency_id, kind, element_id, found)
    return found[0]


def test_tracer_screen_placeholder_case_rows_validate(prepared):
    selection = _selection()
    fake, path, base = prepared(selection=selection)
    result = contingency.screen(base)
    rows = result.rows
    assert result.n_contingencies == 16
    assert len(result.outages) == 16
    assert len(rows) == 10
    assert len(set(row["contingency_id"] for row in rows)) == 7

    thermal = _find(rows, "90001-90002-1", "thermal_overload", "90001-90002-2")
    assert thermal["element_type"] == "branch"
    assert thermal["unit"] == "MVA"
    assert thermal["limit_value"] == pytest.approx(500.0)
    assert thermal["observed_value"] == pytest.approx(750.6, abs=0.1)
    assert thermal["exceeded_by"] == pytest.approx(thermal["observed_value"] - 500.0)
    assert thermal["exceeded_by"] > 0
    assert thermal["city"] is None
    assert thermal["details"]["in_base_case"] is False

    low = _find(rows, "90001-90002-1", "voltage_low", "90002")
    assert low["element_type"] == "bus"
    assert low["unit"] == "pu"
    assert low["limit_value"] == pytest.approx(0.90)
    assert low["observed_value"] == pytest.approx(0.869474, abs=1e-5)
    assert low["exceeded_by"] == pytest.approx(0.90 - low["observed_value"])
    assert low["city"] == "AUSTIN"
    assert low["details"]["in_base_case"] is True
    assert low["details"]["base_value"] == pytest.approx(0.934737, abs=1e-5)

    results = _results_for(selection, rows, result.n_contingencies)
    run_record.validate_results(results, selection)
    for row in rows:
        json.dumps(row["details"], allow_nan=False)


# ──────────────────────────────────────────────────────────────────────────────
# Violation evaluation as pure functions (BranchFlow and BusRow built directly)
# ──────────────────────────────────────────────────────────────────────────────

DEFAULTS = settings.DEFAULT_SETTINGS
NAN = float("nan")


def _flow(from_bus, to_bus, ckt, rate, pct, in_service=True):
    return psse_api.BranchFlow(from_bus, to_bus, ckt, in_service, rate, pct, 0.0, 0.0)


def _bus(number, pu, type_code=1, nvlmlo=0.95, nvlmhi=1.05, evlmlo=0.90, evlmhi=1.10):
    return psse_api.BusRow(number, type_code, 345.0, pu, nvlmlo, nvlmhi, evlmlo, evlmhi)


def _thermal(flows, settings_=DEFAULTS, keys=None, skip=None, base=None, cities=None):
    keys = frozenset(flow.key for flow in flows) if keys is None else keys
    return violations.thermal_violations(
        flows, keys, settings_, "1-2-1", {} if cities is None else cities,
        {} if base is None else dict((flow.key, flow) for flow in base), skip_key=skip)


def _voltage(buses, settings_=DEFAULTS, monitored=None, base=None, cities=None):
    table = dict((bus.number, bus) for bus in buses)
    monitored = frozenset(table) if monitored is None else monitored
    return violations.voltage_violations(
        table, monitored, settings_, "1-2-1", {} if cities is None else cities,
        {} if base is None else dict((bus.number, bus) for bus in base))


def test_violation_thermal_current_vs_mva_basis():
    row, = _thermal([_flow(10, 11, "1", 500.0, 150.0)])
    assert row["violation_kind"] == "thermal_overload"
    assert row["element_type"] == "branch"
    assert row["element_id"] == "10-11-1"
    assert row["unit"] == "MVA"
    assert row["limit_value"] == 500.0
    assert row["observed_value"] == 750.0
    assert row["exceeded_by"] == 250.0
    assert row["details"]["basis"] == "current"
    assert row["details"]["rate_set"] == "RATEA"
    assert row["details"]["pct_of_rating"] == 150.0

    ninety = DEFAULTS._replace(thermal_limit_pct=90.0, thermal_basis="mva",
                               rate_sets=("RATEB", "RATEC"))
    row, = _thermal([_flow(10, 11, "1", 500.0, 150.0)], ninety)
    assert row["limit_value"] == 450.0
    assert row["observed_value"] == 750.0
    assert row["exceeded_by"] == 300.0
    assert row["details"]["basis"] == "mva"
    assert row["details"]["rate_set"] == "RATEB"


def test_violation_thermal_skips_zero_rating_nan_tripped_and_out_of_service():
    flows = [
        _flow(1, 2, "1", 0.0, 500.0),            # rating 0 means no limit
        _flow(1, 3, "1", 500.0, NAN),            # no usable loading
        _flow(1, 4, "1", float("inf"), 200.0),   # no usable rating
        _flow(1, 5, "1", 500.0, 200.0, in_service=False),
        _flow(1, 6, "1", 500.0, 200.0),          # the outaged line
        _flow(1, 7, "1", 500.0, 200.0),          # not monitored
        _flow(1, 8, "1", 500.0, 200.0),          # the one that counts
    ]
    keys = frozenset(flow.key for flow in flows if flow.to_bus != 7)
    rows = _thermal(flows, keys=keys, skip="1-6-1")
    assert [row["element_id"] for row in rows] == ["1-8-1"]


def test_violation_thermal_exact_limit_is_not_a_violation():
    assert _thermal([_flow(1, 2, "1", 500.0, 100.0)]) == []
    ninety = DEFAULTS._replace(thermal_limit_pct=90.0)
    assert _thermal([_flow(1, 2, "1", 500.0, 90.0)], ninety) == []
    row, = _thermal([_flow(1, 2, "1", 500.0, 100.0001)])
    assert row["exceeded_by"] > 0


def test_violation_voltage_low_high_distance():
    low, = _voltage([_bus(1, 0.88)])
    assert low["violation_kind"] == "voltage_low"
    assert low["element_type"] == "bus"
    assert low["element_id"] == "1"
    assert low["unit"] == "pu"
    assert low["limit_value"] == 0.90
    assert low["observed_value"] == 0.88
    assert low["exceeded_by"] == pytest.approx(0.02)
    high, = _voltage([_bus(2, 1.07)])
    assert high["violation_kind"] == "voltage_high"
    assert high["limit_value"] == 1.05
    assert high["exceeded_by"] == pytest.approx(0.02)
    assert _voltage([_bus(3, 0.90), _bus(4, 1.05), _bus(5, 1.0)]) == []
    rows = _voltage([_bus(9, 1.07), _bus(7, 0.88), _bus(8, 1.0)])
    assert [row["element_id"] for row in rows] == ["7", "9"]


def test_violation_voltage_skips_isolated_and_unmonitored():
    buses = [_bus(1, 0.80, type_code=4), _bus(2, 0.80), _bus(3, 0.80), _bus(4, NAN),
             _bus(5, 0.0), _bus(6, 0.80, type_code=5)]
    rows = _voltage(buses, monitored=frozenset([1, 2, 4, 5, 6, 99]))
    assert [row["element_id"] for row in rows] == ["2"]


def test_violation_voltage_case_limits_source():
    case_settings = DEFAULTS._replace(voltage_source="case")
    bus = _bus(1, 0.88, nvlmlo=0.97, nvlmhi=1.03, evlmlo=0.92, evlmhi=1.08)
    assert violations.voltage_limits(bus, case_settings, True) == (0.92, 1.08)
    assert violations.voltage_limits(bus, case_settings, False) == (0.97, 1.03)
    assert violations.voltage_limits(bus, DEFAULTS, True) == (0.90, 1.05)
    assert violations.voltage_limits(bus, DEFAULTS, False) == (0.95, 1.05)
    base = _bus(1, 0.96, nvlmlo=0.97, nvlmhi=1.03, evlmlo=0.92, evlmhi=1.08)
    row, = _voltage([bus], case_settings, base=[base])
    assert row["violation_kind"] == "voltage_low"
    assert row["limit_value"] == 0.92
    assert row["details"]["source"] == "case"
    assert row["details"]["in_base_case"] is True      # 0.96 is below the case's 0.97
    row, = _voltage([bus], DEFAULTS, base=[base])
    assert row["limit_value"] == 0.90 and row["details"]["source"] == "config"
    # a case pair of (0, 0), a reversed pair and NaN fall back to the configured pair
    for pair in ((0.0, 0.0), (1.1, 0.9), (NAN, 1.05)):
        odd = _bus(1, 0.88, nvlmlo=pair[0], nvlmhi=pair[1], evlmlo=pair[0], evlmhi=pair[1])
        assert violations.voltage_limits(odd, case_settings, True) == (0.90, 1.05)
        assert violations.voltage_limits(odd, case_settings, False) == (0.95, 1.05)
        row, = _voltage([odd], case_settings)
        assert row["limit_value"] == 0.90 and row["details"]["source"] == "config"


def test_violation_in_base_case_flag():
    # thermal: already above the same limit in the base
    row, = _thermal([_flow(1, 2, "1", 500.0, 150.0)], base=[_flow(1, 2, "1", 500.0, 120.0)])
    assert row["details"]["in_base_case"] is True
    assert row["details"]["base_value"] == 600.0
    row, = _thermal([_flow(1, 2, "1", 500.0, 150.0)], base=[_flow(1, 2, "1", 500.0, 80.0)])
    assert row["details"]["in_base_case"] is False
    assert row["details"]["base_value"] == 400.0
    row, = _thermal([_flow(1, 2, "1", 500.0, 150.0)])
    assert row["details"]["in_base_case"] is False and row["details"]["base_value"] is None
    # an unusable base flow is no evidence of a base violation
    row, = _thermal([_flow(1, 2, "1", 500.0, 150.0)], base=[_flow(1, 2, "1", 500.0, NAN)])
    assert row["details"]["in_base_case"] is False and row["details"]["base_value"] is None
    # voltage: below base_low_pu in the base (0.95), or not
    row, = _voltage([_bus(1, 0.88)], base=[_bus(1, 0.93)])
    assert row["details"]["in_base_case"] is True
    assert row["details"]["base_value"] == 0.93
    row, = _voltage([_bus(1, 0.88)], base=[_bus(1, 0.97)])
    assert row["details"]["in_base_case"] is False
    assert row["details"]["base_value"] == 0.97
    # a high-voltage row is only in the base when the base was high
    row, = _voltage([_bus(1, 1.07)], base=[_bus(1, 0.93)])
    assert row["details"]["in_base_case"] is False
    row, = _voltage([_bus(1, 1.07)], base=[_bus(1, 1.06)])
    assert row["details"]["in_base_case"] is True


def test_violation_non_convergence_row_shape():
    failed = psse_api.classify_solve(3, 0)
    row = violations.non_convergence_row("5-6-1", failed)
    assert row["contingency_id"] == "5-6-1"
    assert row["violation_kind"] == "non_convergence"
    assert row["element_type"] == "contingency"
    assert row["element_id"] == "5-6-1"
    assert row["city"] is None
    for key in ("limit_value", "observed_value", "exceeded_by", "unit"):
        assert row[key] is None
    assert row["details"]["ierr"] == 3
    assert row["details"]["solved"] is None            # solved() is stale after a failed fnsl
    assert row["details"]["collapsed"] is False
    assert "fnsl ierr 3" in row["details"]["meaning"]
    iterated = psse_api.classify_solve(0, 1, 99, 5.0)
    row = violations.non_convergence_row("5-6-1", iterated)
    assert row["details"]["ierr"] == 0 and row["details"]["solved"] == 1
    collapsed = violations.non_convergence_row("5-6-1", psse_api.classify_solve(0, 0, 4, 0.1),
                                               collapsed=True)
    assert collapsed["details"]["collapsed"] is True
    assert "collapsed" in collapsed["details"]["meaning"]


def test_violation_rows_pass_validate_results():
    selection = _selection()
    rows = []
    rows += violations.thermal_violations(
        [_flow(1, 2, "1", 500.0, 150.0)], frozenset(["1-2-1"]), DEFAULTS, "7-8-1",
        {"1-2-1": "AUSTIN"}, {})
    rows += violations.voltage_violations(
        {10: _bus(10, 0.88), 11: _bus(11, 1.07)}, frozenset([10, 11]), DEFAULTS, "7-8-1",
        {10: "MIDLAND"}, {10: _bus(10, 0.93)})
    rows.append(violations.non_convergence_row("9-9-1", psse_api.classify_solve(3, 0)))
    assert [row["violation_kind"] for row in rows] == [
        "thermal_overload", "voltage_low", "voltage_high", "non_convergence"]
    assert rows[0]["city"] == "AUSTIN" and rows[1]["city"] == "MIDLAND" and rows[2]["city"] is None
    results = _results_for(selection, rows, 2)
    run_record.validate_results(results, selection)
    assert set(rows[0]) == set(contract.CONTINGENCY_COLUMNS) - {"run_id", "run_outcome"}
    # the validator is the judge: a wrong amount exceeded is refused
    broken = dict(rows[0], exceeded_by=rows[0]["exceeded_by"] + 1.0)
    with pytest.raises(contract.ResultsInvalid):
        run_record.validate_results(_results_for(selection, [broken], 1), selection)


def test_violation_details_json_safe():
    nasty = psse_api.BranchFlow(1, 2, "1", True, 500.0, 150.0, NAN, NAN)
    rows = violations.thermal_violations(
        [nasty], frozenset(["1-2-1"]), DEFAULTS, "7-8-1", {},
        {"1-2-1": psse_api.BranchFlow(1, 2, "1", True, 500.0, float("inf"), NAN, NAN)})
    rows += violations.voltage_violations(
        {1: _bus(1, 0.88)}, frozenset([1]), DEFAULTS, "7-8-1", {},
        {1: _bus(1, NAN)})
    rows.append(violations.non_convergence_row("9-9-1", psse_api.classify_solve(0, 1, 5, NAN)))
    assert len(rows) == 3
    for row in rows:
        json.dumps(row["details"], allow_nan=False)
        json.dumps(row, allow_nan=False)
    assert rows[0]["details"]["base_value"] is None
    assert rows[1]["details"]["base_value"] is None


def test_violation_city_maps():
    # a bus used by two cities belongs to neither
    one = study.CityBase("AUSTIN", (study.ResolvedBranch(settings.BranchRef(1, 2, "1"), 345.0),
                                    study.ResolvedBranch(settings.BranchRef(1, 3, "1"), 345.0)),
                         345.0, (2,), 1000.0, 1.0, 1.0, (1.0,))
    two = study.CityBase("MIDLAND", (study.ResolvedBranch(settings.BranchRef(3, 4, "1"), 345.0),),
                         345.0, (4,), 1000.0, 1.0, 1.0, (1.0,))
    by_branch, by_bus = violations.city_maps({"AUSTIN": one, "MIDLAND": two})
    assert by_branch == {"1-2-1": "AUSTIN", "1-3-1": "AUSTIN", "3-4-1": "MIDLAND"}
    assert by_bus == {1: "AUSTIN", 2: "AUSTIN", 4: "MIDLAND"}
