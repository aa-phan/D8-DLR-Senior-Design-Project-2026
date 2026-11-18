"""
Study-level behaviour tests of the pandapower adapter (pandapower-solver Phase 2, plan 02-05:
ENG-03, ENG-04).

Plan 02-02 proved the adapter's rules for the adapter alone. These tests prove them through the
study's own loops, with the `psse_job` code unchanged: an outage that islands part of the grid
becomes one non_convergence row through `contingency.screen`, the order of the outages and a prior
failure change no other row, no reading follows a failed solve, and every city, outage and margin
step solves a freshly loaded copy.

Every input is a synthetic RAW file generated at test time from pandapower's own 39-bus case with
the bus numbers offset by 90000 (`pandapower_study_fixture`), written into tmp_path only. The ratings
come from `psse_fakes` rows, so no live data is read. The solver is the real pandapower.
"""

import json
import tempfile

import pytest

pandapower = pytest.importorskip("pandapower")

import pandapower_study_fixture as study_fixture  # noqa: E402
from psse_job import contingency, mapping as mapping_module, study  # noqa: E402
from pandapower_job import api as pandapower_api  # noqa: E402

ISLAND = study_fixture.ISLANDING_OUTAGE


@pytest.fixture(autouse=True)
def _private_temp(tmp_path, monkeypatch):
    """Every temporary directory of a test lives under tmp_path/scratch, so a leak shows."""
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    return scratch


def _extra(ref):
    return {"from_bus": ref.from_bus, "to_bus": ref.to_bus, "ckt": ref.ckt}


def _island_mapping(tmp_path):
    """The placeholder mapping with the islanding outage as `contingency.extra`, loaded."""
    path = study_fixture.write_placeholder_mapping(
        tmp_path, study={"contingency": {"extra": [_extra(ISLAND)]}})
    return mapping_module.load_mapping(path, allow_placeholder=True)


def _row_key(row):
    """A stable sort key for a result row (JSON text with sorted keys)."""
    return json.dumps(row, sort_keys=True, default=str)


def test_tracer_island_is_one_non_convergence_row(tmp_path):
    case_path = study_fixture.write_case(tmp_path)
    loaded = _island_mapping(tmp_path)
    base = study.prepare_base(study_fixture.fixture_backend(), case_path, loaded,
                              study_fixture.selection(), solver="pandapower")
    try:
        screened = contingency.screen(base, id_prefix="ALL:")
    finally:
        study.cleanup_base(base)

    assert ISLAND in screened.outages
    assert screened.n_contingencies == len(screened.outages)
    island_rows = [row for row in screened.rows if row["contingency_id"] == "ALL:" + ISLAND.key]
    assert len(island_rows) == 1
    row = island_rows[0]
    assert row["violation_kind"] == "non_convergence"
    details = row["details"]
    assert details["ierr"] == 3
    assert details["solved"] is None
    assert details["collapsed"] is False
    assert details["meaning"].startswith("fnsl ierr 3: buses in island without swing bus")
    # The screen did not stop at the island: another outage was screened (it has rows, or it
    # converged clean and has none), so more than one outage was selected and every one counted.
    assert len(screened.outages) > 1
    other_outages = [outage for outage in screened.outages if outage != ISLAND]
    assert other_outages

    # pandapower itself calls the very same solve converged: the row comes from the adapter's
    # explicit rule, not from pandapower's flag.
    api = pandapower_api.PandapowerApi(study_fixture.fixture_backend(), protected_path=case_path)
    api.load_case(case_path)
    assert api.solve().converged
    snapshot = str(tmp_path / "scratch" / "tracer.snapshot")
    api.save_case(snapshot)
    api.load_case(snapshot)
    api.set_status(ISLAND, False)
    result = api.solve()
    assert not result.converged
    assert result.ierr == 3
    assert api._net.converged is True
