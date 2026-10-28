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
