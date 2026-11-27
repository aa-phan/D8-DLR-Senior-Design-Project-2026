# Phase 2: PandapowerApi and Study Engine - Pattern Map

**Mapped:** 2026-11-18
**Files analyzed:** 9 new, 1 modified (plus 1 optional edit to `scaling.py`)
**Analogs found:** 10 / 10 (all git-tracked; verified with `git ls-files`)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `backend/psse_job/study.py` (modify) | service (seam) | request-response | itself, lines 321-334 and 627-647 | exact (in place) |
| `backend/pandapower_job/api.py` | adapter/service | CRUD + request-response | `backend/psse_job/psse_api.py` | exact (same 14-method surface) |
| `backend/pandapower_job/engine.py` | service (wrapper, preflight) | request-response | `backend/psse_job/study.py` `prepare_run`/`failing_study` | role-match |
| `backend/pandapower_job/scaling.py` (optional `case_totals`) | utility | transform | `scaling.scale_city` (96-153) | exact (extract) |
| `backend/tests/pandapower_api_test.py` | test | request-response | `backend/tests/pandapower_network_test.py` + `psse_api_test.py` | role-match |
| `backend/tests/pandapower_engine_test.py` | test | batch | `backend/tests/psse_study_test.py` | role-match |
| `backend/tests/pandapower_study_job_test.py` | test | CRUD (DB) | `backend/tests/psse_study_job_test.py` | exact |
| `backend/tests/pandapower_import_gate_test.py` | test | static analysis | `backend/tests/psse_contract_test.py` | role-match |
| `backend/tests/psse_study_solver_test.py` | test | request-response | `backend/tests/psse_study_test.py` | role-match |
| `backend/tests/pandapower_study_fixture.py` (not collected) | test helper | file-I/O | `backend/tests/pandapower_fixture.py` | exact |

## Pattern Assignments

### `backend/psse_job/study.py` (modify; seam, request-response)

Constraint: 3.7 syntax, stdlib only, no pandapower or `importlib` (`psse_contract_test.py:40-44, 151-164`). Do not touch `contract.py`, `run_record.py`, `job.py`, `constants.py`, `gaps.py`.

**Current seam to change** (`study.py:321-334`):
```python
def _open_case(psspy_module, case_path):
    label = run_record.case_label(case_path)
    try:
        api = psse_api.PsseApi(psspy_module, protected_path=case_path)
        psse_version = api.version()
        api.load_case(case_path)
        lines, transformers = api.branch_table()
        buses = api.bus_table()
    except (psse_api.PsseCallError, ValueError) as error:
        raise StudyFailed("load_case", "case %s could not be loaded: %s" % (
            label, getattr(error, "meaning", error)))
    return api, label, psse_version, lines, transformers, buses
```
Apply: add `solver="psse"` as the LAST keyword to `_open_case` (321), `index_case` (383-392), `prepare_base` (347), `make_study` (569, after `clock=None`) and `prepare_run` (627, after `clock=None`). Thread it through the call chain (`index_case` -> `_open_case`; `make_study.study` -> `index_case`; `prepare_run` -> `make_study(..., clock, solver)` at line 646). Add `API_FACTORIES` + `register_solver` per RESEARCH Pattern 1. Unknown name -> `StudyFailed("load_case", ...)`. Note `prepare_run`'s `failing_study(...)` path and `PreparedRun` stay unchanged. Because `except (PsseCallError, ValueError)` already catches the builder refusals, the adapter's errors must subclass `PsseCallError` or `ValueError`.

**Study-side reads the adapter must satisfy** (`study.py:306-318`): `bus_table()` returns dict of `BusRow`; collapse guard is `bus.type_code < 4 and not bus.pu >= settings.collapse_voltage_pu` (so NaN `pu` fails closed). `solve_base` (266-282) calls `api.solve(settings.solve_options)` and uses `result.converged/ierr/solved_code/meaning/mismatch_mva` (mismatch `None` is skipped).

---

### `backend/pandapower_job/api.py` (adapter, CRUD)

**Analog:** `backend/psse_job/psse_api.py` (surface to match exactly; signatures at 325, 333, 371, 389, 407, 443, 473, 489, 502, 515, 553, 603, 628, 636).

**Value types and error classes to REUSE (do not redefine)** (`psse_api.py:199-262`):
```python
classify_solve(ierr, solved_code, iterations=None, mismatch_mva=None)  # -> SolveResult
class PsseCallError(RuntimeError):
    def __init__(self, function, ierr, meaning):
        self.function = function; self.ierr = ierr; self.meaning = meaning
        RuntimeError.__init__(self, "psspy.%s failed: ierr=%s (%s)" % (function, ierr, meaning))
class CaseProtected(RuntimeError): ...
BranchRow(from_bus, to_bus, ckt, in_service, is_transformer)   # .key = "%d-%d-%s"
BusRow(number, type_code, base_kv, pu, nvlmlo, nvlmhi, evlmlo, evlmhi)
BranchFlow(from_bus, to_bus, ckt, in_service, rate_mva, pct, p_mw, max_mva)
```
Subclass: `class PandapowerCallError(psse_api.PsseCallError)` overriding the message to say `pandapower.<function>`; keep `.function/.ierr/.meaning` (`study._open_case` reads `getattr(error, "meaning", error)`).

**Constructor / path protection / argument validation** (`psse_api.py:264-280, 497-513, 593-645`):
```python
def _normalise_path(path):
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path must be a non-empty string")
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))

def __init__(self, psspy_module, protected_path=None):      # PandapowerApi(backend, protected_path=None)
    self._protected = None if protected_path is None else _normalise_path(protected_path)
    self.warnings = []

def _subsystem_id(sid):
    if not _is_int(sid) or not 0 <= sid <= 11:
        raise ValueError("sid must be an integer from 0 to 11")

def save_case(self, path):
    if _normalise_path(path) == self._protected:
        raise CaseProtected("refusing to save onto the case file that was loaded")
```
Reuse `_normalise_path`/`_is_int`/`_is_number` by importing from `psse_api` (private but same repo) or copy; set_status requires `isinstance(in_service, bool)` else `ValueError` (489-494); `scale_load` coerces to finite float else `ValueError("increment_mw must be a finite number")` (515-527).

**Solve outcome mapping** (RESEARCH Pattern 3) around `solve.run_load_flow` (`solve.py:62-85`):
```python
outcome = solve.run_load_flow(self._net, settings, settings.enforce_q_lims)   # SolveOutcome(converged, reason, iterations)
# converged -> classify_solve(0, 0, outcome.iterations, None)
# "nan_voltage" -> classify_solve(3, None)
# "voltage_collapse" -> classify_solve(0, 2)
# anything else -> classify_solve(0, 1)
```
`solve(self, options=None)`: any non-None options -> `ValueError` (PSS/E form validates a list of 8 ints at `psse_api.py:339-345`). Settings come from the injected backend object, never module-level (D-06).

**State machine** (RESEARCH Pattern 2): `_state` in fresh/solved/failed/stale; mutators set stale; reads call `_require_solved` which raises `PandapowerCallError(function, None, "no valid solution (state: %s)")`. `bus_table` allowed in `fresh` (pu = NaN) because `_open_case` reads it before any solve.

**Phase 1 builder facts to key off** (`network.py:197-238`): line `name = raw.branch_key(I, J, CKT)`; `max_i_ka = RATEA / (sqrt(3) * kV)` (so `read_rate = max_i_ka * sqrt(3) * vn_kv`); bus index = PSS/E number; bus limits in `min_vm_pu/max_vm_pu`; ext_grid carries `psse_pg_mw` etc.; transformers have no rating. Split ckt with `name.split("-", 2)[2]`.

**load_case** copies: master built once via `raw.parse_raw(bytes)` + `network.build_network` (or `convert.case_from_json` for `.json`), then `copy.deepcopy`; saved snapshot paths -> deepcopy of snapshot; anything else -> `PandapowerCallError("case", 3, "error opening the case file")` (mirrors `psse_api.CASE_ERRORS[3]`).

**scale_case / read_totals**: delegate to `scaling.scale_city(net, obj_with_load_mw_gen_mw, details)` (`scaling.py:96-153`, returns a deepcopy; raises `ScalingRefused`/`ScalingUndetermined`, both `ValueError`, which `study.scale_city_case` catches at `study.py:420-421`). `read_totals` must use the same totals expression as `scale_city` lines 105-113: in-service `load.p_mw` sum; in-service `gen.p_mw` sum plus `ext_grid.psse_pg_mw` sum when `swing_in_total == "yes"`. Extract it as `scaling.case_totals(net, details)` and call from both (keep Phase 1 tests green).

**Messages:** no bus numbers, keys or figures in any exception text (Phase 1 convention).

---

### `backend/pandapower_job/engine.py` (wrapper, request-response)

**Analog:** `study.prepare_run` and `failing_study` (`study.py:464-473, 627-647`).

**Core pattern to copy:**
```python
PreparedRun = collections.namedtuple("PreparedRun", ["study", "case_id", "case_sha256", "mapping_sha256", "mapping_error"])

def failing_study(stage, message):
    def failing(selection, context):
        raise StudyFailed(stage, message)
    return failing

# prepare_run: load_mapping(mapping_path, allow_placeholder) except MappingError -> PreparedRun(failing_study("mapping", "mapping file not usable: %s" % text), ...)
```
Apply: `engine.prepare_run(backend, case_path, mapping_path, ...)` imports `pandapower_job.api` (side-effect registration), calls `study.prepare_run(..., solver="pandapower")`, runs the preflight (RESEARCH "Engine preflight" sketch: thermal basis `current`, `solve_options is None`, `voltage_source == "config"`, `enforce_q_lims is not None`), returning `PreparedRun` with `failing_study("mapping", "pandapower: " + reason)` on refusal. Wrap the returned study to add the solve/scaling record to each dispatch row `details` (use `study.json_safe`, `study.py:476-497`) and set `psse_version` to None. Placeholder constants and `is_placeholder(backend)` per RESEARCH "Placeholder constants". `SolveSettings` and `ScalingDetails` namedtuples from `solve.py:44-47` / `scaling.py:67-68`. `collapse_voltage_pu` copied from `mapping.settings`.

---

### `backend/tests/pandapower_api_test.py`, `pandapower_engine_test.py`, `psse_study_solver_test.py` (tests)

**Analogs:** `backend/tests/pandapower_network_test.py` (header and fixture use), `psse_study_test.py` (study-level tests), `psse_api_test.py`.

**Header pattern** (`pandapower_network_test.py:1-34`):
```python
import pytest
pandapower = pytest.importorskip("pandapower")
import pandapower.networks as pandapower_networks  # noqa: E402
import pandapower_fixture as fixture  # noqa: E402
from pandapower_job import network, raw  # noqa: E402
OFFSET = fixture.OFFSET

def _parse(records, **kwargs):
    return raw.parse_raw(fixture.raw_text(records, **kwargs).encode("utf-8"))
# records = fixture.case39_records(OFFSET); path = fixture.write_raw(tmp_path / "synthetic.raw", records)
```
Rules: plain module-level functions, plain asserts, no classes; failure messages are counts only; leak assertions list synthetic targets in `repr`, `%g`, `%.1f` forms (as `psse_study_job_test._synthetic_target_texts`). `psse_study_solver_test.py` needs no pandapower (default `"psse"`, unknown solver and unregistered `"pandapower"` fail at `load_case`). Signature pin test: RESEARCH "pinned-signature test" (`inspect.signature` equality across `_public_methods`). Order-independence test: RESEARCH D-09 sketch, reload snapshot before each outage.

### `backend/tests/pandapower_import_gate_test.py`

**Analog:** `psse_contract_test.py:40-44` (allow-list), `151-164` (`_import_problems`). Reuse `_collect_imports`/AST walk idea: assert no `psse_job` source names `pandapower` or `pandapower_job`, and that `import psse_job.study` leaves `pandapower` out of `sys.modules` (run in a subprocess).

### `backend/tests/pandapower_study_job_test.py` (DB tier)

**Analog:** `backend/tests/psse_study_job_test.py:1-60`.
```python
import psse_local_pg as pg_helper  # noqa: E402
from psse_job import constants, job, run_record, study, writer  # noqa: E402

@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    with pg_helper.cluster(tmp_path_factory) as admin_url:
        pg_helper.apply_schema(admin_url)
        yield admin_url
```
Skips unless `DLR_TEST_PG_AUTOSTART=1` or `DLR_TEST_DATABASE_URL`; `PSSE_REQUIRE_PG=1` makes missing DB a failure. Local only, never Supabase. Fetch is a fake. Assert nothing about the `solver` column (Phase 3 owns it). Expect `1 + 4 + 4 + N` rows.

### `backend/tests/pandapower_study_fixture.py` (helper, not collected)

**Analog:** `backend/tests/pandapower_fixture.py` (`case39_records` 84, `mutate` 189, `write_raw` 263, `_split_key` 278). Name does not match `test_*.py`/`*_test.py`, so pytest skips it. Use `fixture.mutate(records, "generator", i, "PT", 5000)` to raise PT; placeholder mapping sinks from RESEARCH Pitfall 6 (AUSTIN `90002-90003-1` sink `90003`; CORPUS_CHRISTI `90003-90004-1` sink `90004`; MIDLAND `90006-90007-1` sink `90007`; EL_PASO `90007-90008-1` sink `90008`; targets 0.90/0.92/0.94/0.96 of fixture totals 6254.2 MW load, 5620.0 MW gen). Details `ScalingDetails("yes","no","yes", {"placeholder": True})`.

## Shared Patterns

### Error handling and refusal
**Source:** `study.py:266-282, 395-426`; `scaling.py:54-68`.
**Apply to:** api.py, engine.py. Every refusal is a `ValueError` or `PsseCallError` subclass with a reason word and no figure; `StudyFailed(stage, message)` is the study-level carrier; non-StudyFailed exceptions are programming errors.

### Fresh copy per solve (D-09, ENG-04)
**Source:** `scaling.scale_city` (`copy.deepcopy(net)` first line of work); `contingency.screen` reloads the saved case before each outage (do not flip status back).
**Apply to:** `load_case`, `scale_case`, `save_case` (snapshot is a deepcopy), master never mutated.

### Convergence rule
**Source:** `solve.py:62-85` (reads only `res_bus` for in-service buses; `net.converged` is True with NaN islands).
**Apply to:** `PandapowerApi.solve`. Do not re-implement.

### Placeholder/no private data
**Source:** `pandapower_fixture.py` offset 90000 case39 generated into `tmp_path`.
**Apply to:** all tests; run the staged leak scan before each commit.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| solver registry (`API_FACTORIES`, `register_solver`) inside `study.py` | seam | registry | No registry exists in `psse_job`; use RESEARCH Pattern 1 verbatim |
| API state machine (`_state`) | adapter | state | `PsseApi` is stateless wrt results; use RESEARCH Pattern 2 |

## Metadata

**Analog search scope:** `backend/psse_job/`, `backend/pandapower_job/`, `backend/tests/`
**Files scanned:** about 14 read or grepped (study.py, psse_api.py, solve.py, scaling.py, network.py, three test files, fixture, local_pg)
**Pattern extraction date:** 2026-11-18
