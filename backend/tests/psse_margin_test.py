"""
Tests for the voltage-stability margin and the dispatched capacity (pss-e-integration Phase 2,
plan 02-05): STU-03 and STU-04 against the fake psspy and an analytic two-bus model. The margin
is a transfer search on plain load flows; the dispatched capacity is the lower of the applied DLR
rating and the voltage-stability limit.

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
    constants, contract, dispatch, mapping, margin, ratings, run_record, study,
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


def test_tracer_austin_margin_and_dispatch_validate(prepared):
    selection = _selection()
    fake, path, base = prepared(selection=selection)
    result = margin.city_margin(base, "AUSTIN")
    row = result.row
    assert result.bounded_by == "voltage_criterion"
    assert set(row) == set(contract.MARGIN_COLUMNS) - set(["run_id", "run_outcome"])
    assert row["city"] == "AUSTIN"
    assert row["method"] == "pv_curve"
    assert row["base_transfer_mw"] == pytest.approx(310.0)
    assert 474.0 <= row["limit_transfer_mw"] <= 475.0
    assert row["margin_mw"] == pytest.approx(row["limit_transfer_mw"] - row["base_transfer_mw"])
    assert 499.0 <= row["voltage_limit_mva"] <= 500.0
    assert result.voltage_limit_mva == row["voltage_limit_mva"]
    assert row["critical_bus"] == "90002"
    assert row["min_voltage_pu"] >= 0.90
    assert row["details"]["bounded_by"] == "voltage_criterion"
    assert row["details"]["extended_past_cap"] is False
    assert row["details"]["lower_bound"] is False

    assert dispatch.POWER_FACTOR_DEFAULT == 0.95
    choice = selection.choices["AUSTIN"]
    dispatched = dispatch.build_dispatch_row(
        choice, 345.0, result.voltage_limit_mva, bounded_by=result.bounded_by)
    assert set(dispatched) == set(contract.DISPATCH_COLUMNS) - set(["run_id", "run_outcome"])
    assert dispatched["limiting_factor"] == "voltage_stability"
    assert dispatched["dispatched_mva"] == result.voltage_limit_mva
    assert dispatched["dispatched_mw"] == pytest.approx(0.95 * dispatched["dispatched_mva"])
    assert dispatched["voltage_limit_mva"] == row["voltage_limit_mva"]
    assert dispatched["rating_source"] == "static_fallback"
    assert dispatched["city_rating_valid_time"] is None
    assert dispatched["city_rating_computed_at"] is None

    template = psse_fakes.fake_results(selection)
    swap_dispatch = [dispatched if r["city"] == "AUSTIN" else r for r in template.dispatch]
    swap_margins = [row if r["city"] == "AUSTIN" else r for r in template.margins]
    results = contract.StudyResults(
        dispatch=swap_dispatch, margins=swap_margins, contingencies=template.contingencies,
        n_contingencies=template.n_contingencies, rate_set="RATEA", psse_version="35.6.0")
    run_record.validate_results(results, selection)
    json.dumps(row["details"], allow_nan=False)
