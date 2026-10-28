"""
Tests for the PSS/E adapter (pss-e-integration Phase 2, plan 02-02; research D-07, D-10,
D-15). STU-01: only fnsl ierr 0 with solved() 0 is a converged load flow. TST-01: a fake psspy
that implements exactly the documented call surface, with drift guards so the adapter, the
SURFACE table and the fake cannot part ways unnoticed.

Follows backend/tests/psse_contract_test.py's conventions (module-level imports, plain
asserts, no test classes, no network). Honest scope: the fake proves call shapes, control
flow and failure handling, not that real PSS/E accepts these calls (the Phase 3 probe does).
"""

import inspect
import os
import sys

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import psse_fake_psspy as fake_module  # noqa: E402
from psse_job import psse_api, settings  # noqa: E402


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


# ──────────────────────────────────────────────────────────────────────────────
# Reads, rating writes with read-back, outages, subsystems and the case-file guard
# ──────────────────────────────────────────────────────────────────────────────

AUSTIN_LINE = settings.BranchRef(90001, 90002, "1")


def _last_call(fake, name):
    return [call for call in fake.fake_calls if call[0] == name][-1]


def _placeholder_with_transformer():
    case = fake_module.placeholder_case()
    case.add_bus(90033)
    case.add_branch(90031, 90033, "1", kind="transformer", rates=(800.0, 880.0, 960.0))
    return case


def test_io_branch_table_strips_padded_ids_and_splits_transformers(tmp_path):
    fake, api, _ = _loaded(tmp_path, case=_placeholder_with_transformer())
    lines, transformers = api.branch_table()
    assert len(lines) == 16
    assert [row.key for row in transformers] == ["90031-90033-1"]
    assert all(row.is_transformer for row in transformers)
    assert not any(row.is_transformer for row in lines)
    assert {row.ckt for row in lines} == {"1", "2"}
    assert [row.key for row in lines] == sorted(row.key for row in lines)
    padded = fake.abrnchar(-1, 1, 1, 4, 1, ["ID"])[1][0]
    assert all(len(text) == 2 for text in padded)
    flag_four = _last_call(fake, "abrnint")[2]
    assert flag_four["flag"] == 4 and flag_four["sid"] == -1 and flag_four["entry"] == 1


def test_io_bus_table_reads_base_kv_and_limits(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    table = api.bus_table()
    assert len(table) == 9
    assert {bus.base_kv for bus in table.values()} == {345.0}
    assert table[fake_module.SWING_BUS].type_code == 3
    assert {bus.type_code for number, bus in table.items() if number != fake_module.SWING_BUS} == {1}
    sink = table[90002]
    assert (sink.nvlmlo, sink.nvlmhi, sink.evlmlo, sink.evlmhi) == (0.95, 1.05, 0.90, 1.10)
    assert sink.number == 90002
    assert table[fake_module.SWING_BUS].pu == 1.02


def test_io_branch_loading_basis_strings(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    current = api.branch_loading("RATEA", "current")
    assert _last_call(fake, "abrnreal")[2]["string"] == ["RATEA", "MAXPCTRATEA", "P", "MAXMVA"]
    assert len(current) == 16
    austin = [flow for flow in current if flow.key == "90001-90002-1"][0]
    apparent = 620.0 / 0.95
    sink_pu = 1.0 - 1e-4 * apparent * 2.0 / 2
    assert austin.rate_mva == 1500.0
    assert austin.max_mva == pytest.approx(apparent / 2)
    assert austin.p_mw == pytest.approx(310.0)
    assert austin.pct == pytest.approx(100.0 * (apparent / 2 / sink_pu) / 1500.0)
    assert austin.in_service is True
    by_mva = api.branch_loading("RATEB", "mva")
    assert _last_call(fake, "abrnreal")[2]["string"] == ["RATEB", "MXPCTMVARATB", "P", "MAXMVA"]
    austin_mva = [flow for flow in by_mva if flow.key == "90001-90002-1"][0]
    assert austin_mva.rate_mva == 1650.0
    assert austin_mva.pct == pytest.approx(100.0 * (apparent / 2) / 1650.0)
    assert psse_api.pct_string("RATEC", "current") == "MAXPCTRATEC"
    assert psse_api.pct_string("RATEA", "mva") == "MXPCTMVARATA"
    calls_before = len(fake.fake_calls)
    for rate_set, basis in (("RATED", "current"), ("RATEA", "amps")):
        with pytest.raises(ValueError):
            api.branch_loading(rate_set, basis)
    assert len(fake.fake_calls) == calls_before


def test_io_rate_write_then_read_back(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    api.set_rate(AUSTIN_LINE, "RATEA", 2181.1)
    sentinel_real = fake_module.REAL_SENTINEL
    keywords = _last_call(fake, "branch_chng_3")[2]
    assert sorted(keywords) == sorted(psse_api.SURFACE_BY_NAME["branch_chng_3"].parameters)
    assert keywords["ratings"][0] == 2181.1
    assert keywords["ratings"][1:] == [sentinel_real] * 11
    assert keywords["realar"] == [sentinel_real] * 12
    assert keywords["intgar"] == [fake_module.INT_SENTINEL] * 6
    assert keywords["namear"] == fake_module.CHAR_SENTINEL
    assert (keywords["ibus"], keywords["jbus"], keywords["ckt"]) == (90001, 90002, "1")
    assert api.read_rate(AUSTIN_LINE, "RATEA") == 2181.1
    assert api.read_rate(AUSTIN_LINE, "RATEB") == 1650.0
    api.set_rate(AUSTIN_LINE, "RATEB", 2400.5)
    assert _last_call(fake, "branch_chng_3")[2]["ratings"][1] == 2400.5
    assert _last_call(fake, "branch_chng_3")[2]["ratings"][0] == sentinel_real
    assert api.read_rate(AUSTIN_LINE, "RATEB") == 2400.5
    assert api.read_rate(AUSTIN_LINE, "RATEA") == 2181.1
    assert api.warnings == []
    assert sorted(_last_call(fake, "brndat")[2]) == ["ibus", "ickt", "jbus", "string"]


def test_io_set_rate_refuses_bad_values(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    fake_calls_before = len(fake.fake_calls)
    api_calls_before = len(api.calls)
    for bad in (0, 0.0, -1, -2181.1, float("nan"), float("inf"), float("-inf"), True, False,
                "2181", None, 10 ** 400):
        with pytest.raises(ValueError):
            api.set_rate(AUSTIN_LINE, "RATEA", bad)
    with pytest.raises(ValueError):
        api.set_rate(AUSTIN_LINE, "RATED", 100.0)
    with pytest.raises(ValueError):
        api.set_rate(settings.BranchRef("90001", 90002, "1"), "RATEA", 100.0)
    assert len(fake.fake_calls) == fake_calls_before
    assert len(api.calls) == api_calls_before
    assert api.read_rate(AUSTIN_LINE, "RATEA") == 1500.0


def test_io_set_status_outages_branch(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    api.set_status(AUSTIN_LINE, False)
    keywords = _last_call(fake, "branch_chng_3")[2]
    assert keywords["intgar"][0] == 0
    assert keywords["intgar"][1:] == [fake_module.INT_SENTINEL] * 5
    assert keywords["ratings"] == [fake_module.REAL_SENTINEL] * 12
    lines, _ = api.branch_table()
    assert [row.in_service for row in lines if row.key == "90001-90002-1"] == [False]
    assert api.read_rate(AUSTIN_LINE, "RATEA") == 1500.0
    assert api.solve().converged is True
    api.set_status(AUSTIN_LINE, True)
    assert _last_call(fake, "branch_chng_3")[2]["intgar"][0] == 1
    lines, _ = api.branch_table()
    assert [row.in_service for row in lines if row.key == "90001-90002-1"] == [True]
    with pytest.raises(ValueError):
        api.set_status(AUSTIN_LINE, 0)


def test_io_save_refuses_the_case_path(tmp_path, monkeypatch):
    fake, api, path = _loaded(tmp_path)
    (tmp_path / "PLACEHOLDER_CASE.sav").write_text("marker")
    spellings = [
        path,
        path.replace("\\", "/"),
        os.path.join(str(tmp_path), "sub", "..", "PLACEHOLDER_CASE.sav"),
    ]
    if os.name == "nt":
        spellings.append(path.swapcase())
    for spelling in spellings:
        with pytest.raises(psse_api.CaseProtected):
            api.save_case(spelling)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(psse_api.CaseProtected):
        api.save_case("PLACEHOLDER_CASE.sav")
    assert not [call for call in fake.fake_calls if call[0] == "save"]
    assert fake.fake_saved_paths == []
    assert (tmp_path / "PLACEHOLDER_CASE.sav").read_text() == "marker"


def test_io_save_to_temp_and_reload_restores(tmp_path):
    fake, api, path = _loaded(tmp_path)
    base = str(tmp_path / "base.sav")
    api.save_case(base)
    assert os.path.exists(base)
    assert fake.fake_saved_paths == [base]
    assert _last_call(fake, "save")[1] == (base,)
    api.set_rate(AUSTIN_LINE, "RATEA", 999.0)
    api.set_status(AUSTIN_LINE, False)
    assert api.read_rate(AUSTIN_LINE, "RATEA") == 999.0
    api.load_case(base)
    assert api.read_rate(AUSTIN_LINE, "RATEA") == 1500.0
    lines, _ = api.branch_table()
    assert [row.in_service for row in lines if row.key == "90001-90002-1"] == [True]
    api.load_case(path)
    assert api.read_rate(AUSTIN_LINE, "RATEA") == 1500.0


def test_io_psspy_exception_becomes_call_error(tmp_path):
    fake, api, path = _loaded(tmp_path)

    def broken(*args, **kwargs):
        raise RuntimeError("boom at " + path)

    fake.fnsl = broken
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.solve()
    error = excinfo.value
    assert error.function == "fnsl"
    assert error.ierr is None
    assert error.meaning == "RuntimeError"
    assert str(error) == "psspy.fnsl failed: ierr=None (RuntimeError)"
    assert path not in str(error) and "boom" not in str(error)
    fake.abrnint = broken
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.branch_table()
    assert excinfo.value.function == "abrnint"


def test_io_nonzero_ierr_becomes_call_error_with_meaning(tmp_path):
    fake, api, path = _loaded(tmp_path)
    secret = str(tmp_path / "secret_dir_xyz" / "missing.sav")
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.load_case(secret)
    error = excinfo.value
    assert (error.function, error.ierr, error.meaning) == ("case", 3, "error opening the case file")
    assert str(error) == "psspy.case failed: ierr=3 (error opening the case file)"
    assert "secret_dir_xyz" not in str(error)
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.load_case("")
    assert (excinfo.value.ierr, excinfo.value.meaning) == (1, "case file name is blank")
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.read_rate(settings.BranchRef(90001, 90002, "9"), "RATEA")
    assert (excinfo.value.function, excinfo.value.ierr) == ("brndat", 2)
    assert excinfo.value.meaning == "branch not found"
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.read_rate(settings.BranchRef(1, 90002, "1"), "RATEA")
    assert (excinfo.value.ierr, excinfo.value.meaning) == (1, "bus not found")
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.set_rate(settings.BranchRef(90001, 90002, "7"), "RATEA", 100.0)
    assert (excinfo.value.function, excinfo.value.ierr) == ("branch_chng_3", 9)
    assert excinfo.value.meaning == "branch not found"
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.save_case(str(tmp_path / "secret_dir_xyz" / "out.sav"))
    assert (excinfo.value.function, excinfo.value.ierr) == ("save", 3)
    assert "secret_dir_xyz" not in str(excinfo.value)


def test_io_transformer_refuses_rating_write(tmp_path):
    fake, api, _ = _loaded(tmp_path, case=_placeholder_with_transformer())
    transformer = settings.BranchRef(90031, 90033, "1")
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.set_rate(transformer, "RATEA", 100.0)
    assert (excinfo.value.ierr, excinfo.value.meaning) == (3, "branch is a two-winding transformer")


def test_io_bulk_columns_unequal_length_is_call_error(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    fake.abrnint = lambda **kwargs: (0, [[1, 2], [3], [1, 1]])
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.branch_table()
    assert excinfo.value.function == "abrnint"
    assert "unequal" in excinfo.value.meaning
    assert str(excinfo.value) == "psspy.abrnint failed: ierr=None (columns of unequal length)"
    fake_two, api_two, _ = _loaded(tmp_path)
    original = fake_two.abrnchar
    fake_two.abrnchar = lambda **kwargs: (0, [original(**kwargs)[1][0][:-1]])
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api_two.branch_table()
    assert excinfo.value.function == "abrnchar"
    fake_three, api_three, _ = _loaded(tmp_path)
    fake_three.abusreal = lambda **kwargs: (0, [[1.0]] * 6)
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api_three.bus_table()
    assert excinfo.value.function == "abusreal"
    fake_four, api_four, _ = _loaded(tmp_path)
    fake_four.abrnreal = lambda **kwargs: (0, [[1.0]] * 3)
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api_four.branch_loading("RATEA", "current")
    assert "shape" in excinfo.value.meaning


def test_io_subsystem_and_scale_load(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    ratio = fake.fake_state.loads[90002][1] / fake.fake_state.loads[90002][0]
    api.define_subsystem(9, [90002])
    assert fake.fake_subsystems[9] == [90002]
    bsys = _last_call(fake, "bsys")[2]
    assert sorted(bsys) == sorted(psse_api.SURFACE_BY_NAME["bsys"].parameters)
    assert bsys["numbus"] == 1 and bsys["buses"] == [90002]
    api.scale_load(9, 25.0)
    scal = _last_call(fake, "scal_2")[2]
    assert scal["status"] == [fake_module.INT_SENTINEL, 3, 0, 1, 0]
    assert scal["scalval"] == [25.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert scal["all"] == 0 and scal["apiopt"] == 0
    p_mw, q_mvar = fake.fake_state.loads[90002]
    assert p_mw == pytest.approx(645.0)
    assert q_mvar / p_mw == pytest.approx(ratio)
    api.define_subsystem(8, [90001])
    api.scale_load(8, 10.0)
    assert fake.fake_state.loads[90002][0] == pytest.approx(645.0)
    assert 90001 not in fake.fake_state.loads
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.scale_load(7, 10.0)
    assert (excinfo.value.function, excinfo.value.ierr) == ("scal_2", 1)
    with pytest.raises(psse_api.PsseCallError) as excinfo:
        api.define_subsystem(6, [1])
    assert excinfo.value.function == "bsys"
    calls_before = len(fake.fake_calls)
    for bad in ((12, [90002]), (-1, [90002]), (True, [90002]), (3, []), (3, [0]), (3, ["90002"])):
        with pytest.raises(ValueError):
            api.define_subsystem(*bad)
    for bad in (float("nan"), float("inf"), True, "5", 10 ** 400):
        with pytest.raises(ValueError):
            api.scale_load(9, bad)
    assert len(fake.fake_calls) == calls_before


def test_io_version_text(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    assert api.version() == "35.6.0"

    def broken():
        raise RuntimeError("no version")

    fake.psseversion = broken
    assert api.version() == "unknown"
    fake.psseversion = lambda: ("PSS(R)E", "35", 6)
    assert api.version() == "unknown"
    fake.psseversion = lambda: None
    assert api.version() == "unknown"


def test_io_radial_solver_base_values(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    assert fake.fnsl() == 0
    state = fake.fake_state
    assert round(state.buses[90002]["pu"], 6) == 0.934737
    assert round(state.buses[90032]["pu"], 6) == 0.983684
    for source, sink in fake_module.PLACEHOLDER_CITY_BUSES.values():
        for ckt in ("1", "2"):
            assert round(state.branch(source, sink, ckt)["max_mva"], 6) == 326.315789
    assert state.buses[90001]["pu"] == 1.0
    assert state.buses[fake_module.SWING_BUS]["pu"] == 1.02
    for ckt in ("1", "2"):
        state.branch(90001, 90002, ckt)["status"] = 0
    solved_before = fake.solved()
    assert fake.fnsl() == 3
    assert fake.solved() == solved_before


# ──────────────────────────────────────────────────────────────────────────────
# The convergence rule as a matrix (STU-01) and the SURFACE drift guards (TST-01)
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ierr, solved_code, converged", [
    (0, 0, True),
    (0, 1, False), (0, 2, False), (0, 3, False), (0, 4, False), (0, 5, False), (0, 6, False),
    (0, 7, False), (0, 9, False), (0, 42, False),
    (1, 0, False), (2, 0, False), (3, 0, False), (4, 0, False), (5, 0, False),
    (0, None, False), (None, 0, False), (0, True, False), (False, 0, False),
])
def test_solve_classification(ierr, solved_code, converged):
    result = psse_api.classify_solve(ierr, solved_code)
    assert result.converged is converged
    assert result.ierr is ierr
    assert result.solved_code is solved_code
    assert isinstance(result.meaning, str) and result.meaning


def test_solve_meaning_text():
    assert psse_api.classify_solve(0, 42).meaning == "unknown solved code 42"
    assert psse_api.classify_solve(0, 0).meaning == "met convergence tolerance"
    assert psse_api.classify_solve(0, 1).meaning == "iteration limit exceeded"
    assert psse_api.classify_solve(0, 7).meaning == "OPF solution met convergence tolerance (NOPF)"
    generators = psse_api.classify_solve(2, 0).meaning
    assert "generators are converted" in generators and "not trusted" in generators
    assert "buses in island without swing bus" in psse_api.classify_solve(3, 0).meaning
    assert "unknown fnsl error" in psse_api.classify_solve(77, 0).meaning
    assert psse_api.classify_solve(0, 0, 3, 0.02) == psse_api.SolveResult(
        True, 0, 0, "met convergence tolerance", 3, 0.02)
    assert set(psse_api.SOLVED_MEANING) == {0, 1, 2, 3, 4, 5, 6, 7, 9}


def test_solve_stale_solved_after_failed_fnsl(tmp_path):
    scripted = [fake_module.radial_solver,
                lambda case: fake_module.SolveOutcome(ierr=3, solved=None, iterations=0, mismatch=0.0),
                lambda case: fake_module.SolveOutcome(ierr=2, solved=None, iterations=0, mismatch=0.0)]

    def solver(case):
        return scripted.pop(0)(case)

    fake, api, _ = _loaded(tmp_path, solver=solver)
    first = api.solve()
    assert first.converged is True and first.iterations == 3
    stale = api.solve()
    assert fake.solved() == 0
    assert stale.converged is False
    assert (stale.ierr, stale.solved_code) == (3, 0)
    assert "island without swing bus" in stale.meaning
    assert stale.iterations is None and stale.mismatch_mva is None
    converted = api.solve()
    assert fake.solved() == 0
    assert converted.converged is False
    assert (converted.ierr, converted.solved_code) == (2, 0)
    assert "generators are converted" in converted.meaning


def test_solve_not_converged_codes_are_results_not_exceptions(tmp_path):
    outcome = fake_module.SolveOutcome(ierr=0, solved=1, iterations=20, mismatch=50.0)
    fake, api, _ = _loaded(tmp_path, solver=lambda case: outcome)
    result = api.solve()
    assert result.converged is False
    assert (result.ierr, result.solved_code) == (0, 1)
    assert result.meaning == "iteration limit exceeded"
    assert (result.iterations, result.mismatch_mva) == (20, 50.0)


def test_solve_options_passed_through(tmp_path):
    fake, api, _ = _loaded(tmp_path)
    api.solve()
    assert _last_call(fake, "fnsl")[1:] == ((), {})
    assert api.calls[-4] == ("fnsl", 0, ())
    options = (1, 0, 0, 1, 1, 0, 99, 0)
    assert api.solve(options=options).converged is True
    assert _last_call(fake, "fnsl")[1:] == ((), {"options": list(options)})
    assert api.calls[-4] == ("fnsl", 0, ("options",))
    calls_before = len(fake.fake_calls)
    for bad in ((1, 0, 0), (1, 0, 0, 1, 1, 0, 99, True), (1, 0, 0, 1, 1, 0, 99, "0"), ()):
        with pytest.raises(ValueError):
            api.solve(options=bad)
    assert len(fake.fake_calls) == calls_before


def _public_fake_names(fake):
    return {name for name in dir(fake)
            if not name.startswith("_") and not name.startswith("fake_")
            and callable(getattr(fake, name))}


def test_surface_names_equal_fake_methods():
    fake = fake_module.FakePsspy()
    assert _public_fake_names(fake) == set(psse_api.SURFACE_NAMES)
    assert psse_api.SURFACE_NAMES == frozenset(psse_api.SURFACE_BY_NAME)
    assert len(psse_api.SURFACE) == len(psse_api.SURFACE_NAMES) == 19
    for unlisted in ("psseinit", "accc_with_dsp_3", "branch_chng", "brnint", "busdat"):
        with pytest.raises(AttributeError):
            getattr(fake, unlisted)


def test_surface_parameters_equal_fake_signatures():
    fake = fake_module.FakePsspy()
    for row in psse_api.SURFACE:
        signature = inspect.signature(getattr(fake, row.name))
        assert tuple(signature.parameters) == tuple(row.parameters), row.name
        kinds = {parameter.kind for parameter in signature.parameters.values()}
        assert inspect.Parameter.VAR_KEYWORD not in kinds, row.name
        assert inspect.Parameter.VAR_POSITIONAL not in kinds, row.name
    with pytest.raises(TypeError):
        fake.abrnint(sid=-1, owner=1, ties=1, flag=2, entry=1, strings=["ID"])
    with pytest.raises(TypeError):
        fake.case(path="x.sav")


def test_surface_rows_have_evidence_and_confidence():
    assert [row.name for row in psse_api.SURFACE] == [
        "psseversion", "getdefaultint", "getdefaultreal", "getdefaultchar", "case", "save",
        "fnsl", "solved", "iterat", "sysmsm", "abrnint", "abrnreal", "abrnchar", "abusint",
        "abusreal", "brndat", "branch_chng_3", "bsys", "scal_2"]
    for row in psse_api.SURFACE:
        assert isinstance(row.evidence, str) and row.evidence.strip(), row.name
        assert row.confidence in psse_api.CONFIDENCE_LEVELS, row.name
        assert isinstance(row.returns, str) and row.returns, row.name
        assert all(isinstance(name, str) for name in row.parameters), row.name
    assert psse_api.SURFACE_BY_NAME["branch_chng_3"].confidence == "UNVERIFIED"
    assert [row.name for row in psse_api.SURFACE if row.confidence == "UNVERIFIED"] == ["branch_chng_3"]
    assert psse_api.SURFACE_BY_NAME["abrnint"].parameters == (
        "sid", "owner", "ties", "flag", "entry", "string")


def test_surface_refuses_unlisted_names_and_keywords(tmp_path):
    fake, api, path = _loaded(tmp_path)
    fake_before = len(fake.fake_calls)
    api_before = list(api.calls)
    with pytest.raises(ValueError):
        api._call("accc_with_dsp_3")
    with pytest.raises(ValueError):
        api._call("fnsl", option=[1, 0, 0, 1, 1, 0, 99, 0])
    with pytest.raises(ValueError):
        api._call("case", "a.sav", "b.sav")
    with pytest.raises(ValueError):
        api._call("case", path, sfile=path)
    with pytest.raises(ValueError):
        api._call("abrnint", sid=-1, owner=1, ties=1, flag=2, entry=1, string=["ID"], extra=1)
    assert len(fake.fake_calls) == fake_before
    assert api.calls == api_before


def test_surface_recorded_calls_stay_inside_table(tmp_path):
    fake, api, path = _loaded(tmp_path)
    api.solve()
    api.solve(options=(1, 0, 0, 1, 1, 0, 99, 0))
    api.branch_table()
    api.bus_table()
    api.branch_loading("RATEA", "current")
    api.branch_loading("RATEB", "mva")
    api.read_rate(AUSTIN_LINE, "RATEA")
    api.set_rate(AUSTIN_LINE, "RATEA", 2181.1)
    api.set_status(AUSTIN_LINE, False)
    api.define_subsystem(9, [90002])
    api.scale_load(9, 25.0)
    api.save_case(str(tmp_path / "base.sav"))
    api.version()
    seen = set()
    for name, args, kwargs in fake.fake_calls:
        row = psse_api.SURFACE_BY_NAME[name]
        assert set(kwargs) <= set(row.parameters), name
        assert len(args) + len(kwargs) <= len(row.parameters), name
        seen.add(name)
    assert seen == set(psse_api.SURFACE_NAMES)
    assert [(name, len(args), tuple(sorted(kwargs))) for name, args, kwargs in fake.fake_calls] == api.calls
    assert [call for call in fake.fake_calls if call[0] == "save"][0][1] == (str(tmp_path / "base.sav"),)
    assert not [call for call in fake.fake_calls
                if call[0] == "save" and call[1] == (path,)]
