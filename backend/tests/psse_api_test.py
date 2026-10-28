"""
Tests for the PSS/E adapter (pss-e-integration Phase 2, plan 02-02; research D-07, D-10,
D-15). STU-01: only fnsl ierr 0 with solved() 0 is a converged load flow. TST-01: a fake psspy
that implements exactly the documented call surface, with drift guards so the adapter, the
SURFACE table and the fake cannot part ways unnoticed.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain
asserts, no test classes, no network). Honest scope: the fake proves call shapes, control
flow and failure handling, not that real PSS/E accepts these calls (the Phase 3 probe does).
"""

import os
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
from psse_job import psse_api  # noqa: E402


def _loaded(tmp_path, case=None, solver=None):
    """(fake, api, case path) with the placeholder case registered and loaded."""
    fake = fake_module.FakePsspy(solver=solver)
    path = str(tmp_path / "PLACEHOLDER_CASE.sav")
    fake.fake_register_case(path, fake_module.placeholder_case() if case is None else case)
    api = psse_api.PsseApi(fake, protected_path=path)
    api.load_case(path)
    return fake, api, path


def test_tracer_adapter_loads_indexes_and_solves_placeholder_case(tmp_path):
    fake, api, path = _loaded(tmp_path)
    lines, transformers = api.branch_table()
    assert len(lines) == 16
    assert transformers == []
    austin = [row for row in lines if row.key == "90001-90002-1"]
    assert len(austin) == 1
    assert austin[0].in_service is True
    assert austin[0].ckt == "1"
    assert fake.abrnchar(-1, 1, 1, 2, 1, ["ID"])[1][0][0] == "1 "
    result = api.solve()
    assert result == psse_api.SolveResult(True, 0, 0, "met convergence tolerance", 3, 0.02)
    assert fake.fake_calls
    assert {name for name, _, _ in fake.fake_calls} <= psse_api.SURFACE_NAMES
