"""
Tests for the dispatched-capacity row (pss-e-integration Phase 2, plan 02-05): STU-04, the lower
of the applied DLR rating and the voltage-stability limit in MVA, per-circuit amps, per-conductor
amps and MW, which of the two set it (a tie goes to the DLR rating), and the guard that keeps the
power-factor copy in psse_job/dispatch.py equal to backend/config.py.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain asserts,
no test classes, no network). The drift test imports backend/config.py, which a test may do and
job code may not.
"""

import datetime
import json
import os
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import config  # noqa: E402
import psse_fakes  # noqa: E402
from psse_job import (  # noqa: E402
    constants, contract, dispatch, ratings, run_record, settings, study, units,
)

NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)
KV = 345.0


def _selection(provisional=True):
    rows = psse_fakes.latest_rows(NOW, provisional=provisional)
    return ratings.select_ratings(psse_fakes.fake_fetch(rows), NOW)


def _applied(choice, kv=KV):
    return units.circuit_mva(choice.amps_per_conductor, choice.subconductors_per_phase, kv)


def test_dispatch_lower_of_rating_and_voltage_limit():
    choice = _selection().choices["AUSTIN"]
    applied = _applied(choice)
    assert applied == pytest.approx(2181.08, abs=0.01)
    above = dispatch.build_dispatch_row(choice, KV, 3000.0)
    assert above["limiting_factor"] == "dlr_rating"
    assert above["dispatched_mva"] == applied
    assert above["applied_mva"] == applied and above["voltage_limit_mva"] == 3000.0
    below = dispatch.build_dispatch_row(choice, KV, 500.0)
    assert below["limiting_factor"] == "voltage_stability"
    assert below["dispatched_mva"] == 500.0
    assert below["dispatched_mva"] < below["applied_mva"]


def test_dispatch_tie_goes_to_dlr_rating():
    choice = _selection().choices["AUSTIN"]
    applied = _applied(choice)
    tie = dispatch.build_dispatch_row(choice, KV, applied)
    assert tie["limiting_factor"] == "dlr_rating"
    assert tie["dispatched_mva"] == applied
    just_below = dispatch.build_dispatch_row(choice, KV, applied * (1 - 1e-12))
    assert just_below["limiting_factor"] == "voltage_stability"
    assert just_below["dispatched_mva"] < applied


def test_dispatch_voltage_limited_amps_and_mw():
    choice = _selection().choices["AUSTIN"]
    assert choice.amps_per_conductor == 1825.0 and choice.subconductors_per_phase == 2
    row = dispatch.build_dispatch_row(choice, KV, 500.0)
    assert row["limiting_factor"] == "voltage_stability"
    assert row["applied_amps_circuit"] == 3650.0
    assert row["dispatched_amps_circuit"] == pytest.approx(836.74, abs=0.01)
    assert row["dispatched_amps_per_conductor"] == pytest.approx(418.37, abs=0.01)
    assert row["dispatched_amps_per_conductor"] * 2 == pytest.approx(row["dispatched_amps_circuit"])
    assert row["dispatched_mw"] == pytest.approx(475.0)
    assert row["power_factor"] == 0.95
    # the power factor enters dispatched_mw only, never the MVA or the amps
    assert row["dispatched_mva"] == 500.0
    assert row["dispatched_amps_circuit"] == pytest.approx(
        units.mva_to_circuit_amps(500.0, KV))


def test_dispatch_static_choice_has_no_link_fresh_choice_keeps_it():
    static = _selection(provisional=True).choices["AUSTIN"]
    assert static.source == constants.SOURCE_STATIC
    row = dispatch.build_dispatch_row(static, KV, 500.0)
    assert row["rating_source"] == "static_fallback"
    assert row["fallback_reason"] == "provisional"
    assert row["city_rating_valid_time"] is None and row["city_rating_computed_at"] is None
    fresh = _selection(provisional=False).choices["AUSTIN"]
    assert fresh.source == constants.SOURCE_CITY_RATING
    row = dispatch.build_dispatch_row(fresh, KV, 500.0)
    assert row["rating_source"] == "city_rating" and row["fallback_reason"] is None
    assert row["city_rating_valid_time"] == fresh.row_valid_time
    assert row["city_rating_computed_at"] == fresh.row_computed_at
    assert row["city_rating_valid_time"] is not None
    assert row["applied_amps_per_conductor"] == fresh.amps_per_conductor
    assert row["subconductors_per_phase"] == fresh.subconductors_per_phase


def test_dispatch_rows_pass_validate_results():
    selection = _selection(provisional=False)
    limits = {"AUSTIN": 500.0, "CORPUS_CHRISTI": 600.0, "MIDLAND": 9000.0, "EL_PASO": 2000.0}
    template = psse_fakes.fake_results(selection)
    dispatch_rows = []
    margin_rows = []
    for margin_row in template.margins:
        city = margin_row["city"]
        dispatch_rows.append(dispatch.build_dispatch_row(selection.choices[city], KV, limits[city]))
        margin_rows.append(dict(margin_row, voltage_limit_mva=limits[city]))
    factors = dict((row["city"], row["limiting_factor"]) for row in dispatch_rows)
    assert factors == {"AUSTIN": "voltage_stability", "CORPUS_CHRISTI": "voltage_stability",
                       "MIDLAND": "dlr_rating", "EL_PASO": "dlr_rating"}
    results = contract.StudyResults(
        dispatch=dispatch_rows, margins=margin_rows, contingencies=template.contingencies,
        n_contingencies=template.n_contingencies, rate_set="RATEA", psse_version="35.6.0")
    run_record.validate_results(results, selection)


def test_dispatch_refuses_bad_inputs():
    choice = _selection().choices["AUSTIN"]
    refused = [
        dict(line_voltage_kv=0.0, voltage_limit_mva=500.0),
        dict(line_voltage_kv=-345.0, voltage_limit_mva=500.0),
        dict(line_voltage_kv=KV, voltage_limit_mva=float("nan")),
        dict(line_voltage_kv=KV, voltage_limit_mva=float("inf")),
        dict(line_voltage_kv=KV, voltage_limit_mva=0.0),
        dict(line_voltage_kv=KV, voltage_limit_mva=-1.0),
        dict(line_voltage_kv=KV, voltage_limit_mva=True),
        dict(line_voltage_kv=KV, voltage_limit_mva=None),
        dict(line_voltage_kv=KV, voltage_limit_mva=500.0, power_factor=0.0),
        dict(line_voltage_kv=KV, voltage_limit_mva=500.0, power_factor=1.1),
        dict(line_voltage_kv=KV, voltage_limit_mva=500.0, power_factor=True),
        dict(line_voltage_kv=KV, voltage_limit_mva=500.0, power_factor=float("nan")),
        dict(line_voltage_kv=KV, voltage_limit_mva=500.0, bounded_by="max_transfer"),
    ]
    for arguments in refused:
        with pytest.raises(ValueError):
            dispatch.build_dispatch_row(choice, **arguments)
    ok = dispatch.build_dispatch_row(choice, KV, 500.0, power_factor=1.0)
    assert ok["dispatched_mw"] == 500.0


def test_dispatch_details_shape():
    branch = settings.BranchRef(90001, 90002, "1")
    city_base = study.CityBase(
        "AUSTIN", (study.ResolvedBranch(branch, KV),), KV, (90002,), 1000.0, 3650.0, 2181.08,
        (1500.0, float("nan")))
    details = dispatch.dispatch_details(city_base, ("RATEA", "RATEB"), "voltage_criterion")
    assert details == {
        "branches": ["90001-90002-1"],
        "rate_sets": ["RATEA", "RATEB"],
        "rate_before_mva": [1500.0, None],
        "voltage_limit_bounded_by": "voltage_criterion",
    }
    json.dumps(details, allow_nan=False)
    row = dispatch.build_dispatch_row(_selection().choices["AUSTIN"], KV, 500.0, details=details)
    assert row["details"] == details


def test_dispatch_power_factor_default_is_the_project_value():
    assert dispatch.POWER_FACTOR_DEFAULT == 0.95
    choice = _selection().choices["AUSTIN"]
    assert dispatch.build_dispatch_row(choice, KV, 500.0)["power_factor"] == dispatch.POWER_FACTOR_DEFAULT
    assert dispatch.build_dispatch_row(choice, KV, 500.0, power_factor=0.9)["power_factor"] == 0.9


def test_dispatch_power_factor_copy_matches_config():
    assert dispatch.POWER_FACTOR_DEFAULT == config.POWER_FACTOR, (
        "re-copy backend/config.py POWER_FACTOR into psse_job/dispatch.py")


def test_dispatch_rating_bound_never_reports_voltage_stability():
    choice = _selection(provisional=False).choices["EL_PASO"]
    applied = _applied(choice)
    assert applied == pytest.approx(867.65, abs=0.01)
    # the cap flow of the fresh EL_PASO search is 852.63 MVA: a rating-bounded margin that
    # reports it as the voltage limit is a bug, not a dispatch row
    with pytest.raises(ValueError):
        dispatch.build_dispatch_row(choice, KV, 852.63, bounded_by="dlr_rating")
    row = dispatch.build_dispatch_row(choice, KV, 878.95, bounded_by="dlr_rating")
    assert row["limiting_factor"] == "dlr_rating" and row["dispatched_mva"] == applied
    row = dispatch.build_dispatch_row(choice, KV, applied, bounded_by="dlr_rating")
    assert row["limiting_factor"] == "dlr_rating"
    for bound in ("voltage_criterion", "non_convergence"):
        row = dispatch.build_dispatch_row(choice, KV, 852.63, bounded_by=bound)
        assert row["limiting_factor"] == "voltage_stability"
        assert row["dispatched_mva"] == 852.63
