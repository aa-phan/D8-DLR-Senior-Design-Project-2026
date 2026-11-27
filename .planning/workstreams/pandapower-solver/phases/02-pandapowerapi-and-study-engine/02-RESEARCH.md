# Phase 2: PandapowerApi and Study Engine - Research

**Researched:** 2026-11-18
**Domain:** a duck-typed second solver adapter (pandapower 3.5.6) behind the unchanged PSS/E study code, plus a mapping/settings preflight and an in-memory four-city study
**Confidence:** HIGH on the integration seam and the pandapower behaviour (both read from code and re-run this session); MEDIUM on agreement with PSS/E (cannot be known until PSE-02 and Phase 4); LOW only where marked `[ASSUMED]`

## User Constraints (from CONTEXT.md)

<user_constraints>

### Locked Decisions

Gathered with the owner's "use your defaults" instruction (2026-11-18): the owner reviewed a plain-language summary of four open choices and asked Claude to apply its recommendations. The owner can change any of them before or during planning.

**Where the code lives**
- **D-01:** `PandapowerApi` goes in `backend/pandapower_job/` (Phase 1 already put the builder, scaling and solve code there), not in the stdlib-only `backend/psse_job/`. `psse_job` must not import pandapower. - **Reversibility:** costly - moving it later touches every import of the module.
- **D-02:** `study.py` selects the solver through one new factory argument, a plain string (`"psse"` default, `"pandapower"`). The default keeps every existing PSS/E test passing unchanged.
- **D-03:** A test pins every `PandapowerApi` public method name and signature to `PsseApi` (success criterion 1).

**Islands and non-convergence**
- **D-04:** Copy PSS/E's behaviour. An outage that islands any in-service bus from the main grid is recorded as a `non_convergence` row, whatever pandapower itself returns. Detection is explicit: any in-service bus with no voltage, or below `settings.collapse_voltage_pu`, makes the solve not converged. pandapower's automatic dropping of isolated buses is not relied on.
- **D-05:** No result is ever read after a failed solve (ENG-04).

**Settings before PSE-02**
- **D-06:** Until the laptop session records the real values, the solve settings (reactive limits, iteration limit, tolerance) are explicit placeholders, clearly named and stored with each run as placeholder values. Plans must not hard-wire them. ENG-05 is finished once PSE-02 is recorded. Consistent with Phase 1 D-14: copy whatever PSS/E reports, no physics-based override.

**Rating basis and testing**
- **D-07:** A rating is applied as a current limit per circuit and loading is read on the current basis. A mapping that asks for any other basis is refused with a clear failure (ENG-02).
- **D-08:** Test against the public IEEE 39-bus case (pandapower's built-in `case39`) as a fixture only, plus a contract test against `PsseApi`. No private data in the repository.
- **D-09:** Each city, each outage and each margin step solves a fresh copy of its base network. A test shows that outage order, or running after a failed solve, does not change the results.

### Claude's Discretion

Internal structure of `PandapowerApi`, helper names, and test layout, as long as the decisions above hold.

### Deferred Ideas (OUT OF SCOPE)

None - discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENG-01 | `PandapowerApi` provides the same methods the study code uses from `PsseApi`, chosen through one new factory argument in `study.py`; a test pins method names and signatures | The study code calls exactly 14 public methods (table in "Architecture Patterns"); one construction line (`study.py:326`) is the whole seam; registry-string design that keeps `psse_job` free of any pandapower import (the gate test would flag a direct import) |
| ENG-02 | Rating applied as a per-circuit current limit; loading read on the current basis; other basis refused | `max_i_ka = mva / (sqrt(3) * kV)` round-trips through `apply_ratings`' read-back; `loading_percent` verified equal to `max(i_from, i_to) / max_i_ka * 100`; refusal at two layers (engine preflight at stage `mapping`, API at `branch_loading`) |
| ENG-03 | Converged only if no error, no in-service bus without a voltage, none below collapse; an island becomes `non_convergence` | `solve.run_load_flow` (Phase 1) already implements the rule; verified `net.converged` is True with NaN islanded buses on pandapower 3.5.6; `SolveResult` mapping table below (island -> ierr 3, as PSS/E) |
| ENG-04 | Fresh copy per city, outage, margin step; no result read after a failed solve | `copy.deepcopy` of a master / snapshot in `load_case` (measured 10-23 ms); verified stale `res_*` survive a status change without a re-solve, so an API-level "valid solution" state machine is required, not optional |
| ENG-05 | Solve settings from PSE-02 values, stored with each run | `solve.SolveSettings` + `scaling.ScalingDetails` are the carriers; placeholder constants now, drop-in loader for the recorded `settings` record and `scaling_details.json` later; stored in each dispatch row's `details` (no schema change) |
| ENG-06 | Full four-city study end to end on a throwaway local database with the placeholder mapping, no live data | Spike (throwaway ~150-line adapter, not committed) ran all four cities on the case39 fixture in 35.5 s and passed `run_record.validate_results`; two test tiers (in-memory always, local Postgres when available) |

</phase_requirements>

## Summary

The study code is already solver-neutral. `study`, `contingency`, `margin`, `violations` and `dispatch` touch the solver only through 14 public `PsseApi` methods, the value types (`BranchRow`, `BusRow`, `BranchFlow`, `SolveResult`, `CaseTotals`) and the exception `PsseCallError`; the only hard-coded PSS/E construction is `psse_api.PsseApi(psspy_module, protected_path=case_path)` in `study._open_case` [VERIFIED: backend/psse_job/study.py:326]. This session a throwaway adapter of about 150 lines, injected by swapping that one name, ran a complete four-city study on the public 39-bus case through the unchanged study code, produced 38 outages and 54 violation rows, and passed `run_record.validate_results` [VERIFIED: spike run, pandapower 3.5.6, scratchpad, 2026-11-18]. So the phase is an engineering-quality problem (traps, state discipline, settings provenance, tests), not a feasibility problem.

Phase 1 already delivered most of the numerical machinery: `network.build_network` (builder), `scaling.scale_city` (the `scal_2` new-total rule, with refusals), `solve.run_load_flow` (the convergence rule of ENG-03, including NaN and collapse) and `SolveSettings`. Phase 2 wraps these in a stateful adapter, adds the explicit "no valid solution" discipline, a mapping/settings preflight, the factory seam in `study.py`, and the test suite. The decisive traps, each verified in this session: (1) pandapower returns `converged = True` with NaN voltages on islanded buses; (2) `res_line` keeps stale numbers after a status change until the next solve; (3) an out-of-service line reads `loading_percent = 0.0`, not NaN; (4) the case39 fixture's machines sit at their P maximum so scaling above 1 is refused unless the fixture raises `PT`; (5) several case39 buses (2, 6) carry no load, so a sink there makes the margin guard fail (`the transfer does not load the mapped branches`) - correct behaviour, but the placeholder test mapping must choose loaded sinks.

**Primary recommendation:** add `solver="psse"` (string, last keyword) to `study.py`'s five entry points with a small registry (`API_FACTORIES`, `register_solver`) so `psse_job` never imports `pandapower_job`; implement `PandapowerApi` in `backend/pandapower_job/api.py` as a state machine (`fresh -> solved | failed`, every mutation invalidates, reads need `solved`), reuse `scaling.scale_city` and `solve.run_load_flow` unchanged, put the mapping and settings preflight plus the "stored with each run" record in a thin `pandapower_job/engine.py` wrapper around `study.prepare_run`, and prove it with two test tiers (in-memory always, local Postgres when available).

## Project Constraints (from CLAUDE.md)

No `./CLAUDE.md`, no `./.claude/CLAUDE.md` and no `.claude/skills/` or `.agents/skills/` directory exist in this checkout [VERIFIED: `ls CLAUDE.md .claude` returned "No such file or directory"]. The binding project conventions come from code and the workstream, and the planner must treat them as constraints:

- `backend/psse_job/` is stdlib-only, Python 3.7 syntax, and may import nothing outside `psse_job` and an allow-list (`test_imports_stay_inside_the_laptop_boundary`, `test_syntax_parses_as_python37`). Any `study.py` edit must pass both. `importlib` is not on the allow-list.
- `backend/pandapower_job/` is Python 3.12 (Mac-side venv, CI 3.12), may import `psse_job` and `psse_session.bundle`; `psse_job` never imports it.
- Tests: plain module-level functions, plain asserts, no classes; pandapower tests start with `pytest.importorskip("pandapower")`; failure messages are counts only (no bus numbers or values).
- Nothing private in the repository: fixtures come from `pandapower_fixture` (case39 with bus numbers offset by 90000, generated into `tmp_path` only); the staged leak scan must exit 0 before every commit (Phase 1 convention).
- No change to the PSS/E job's behaviour (REQUIREMENTS "Out of Scope"); only default-preserving additions.
- Do not edit `contract.py`, `run_record.py`, `job.py`, `constants.py` or `gaps.py`: Phase 3 (parallel) owns them for the `solver` column. Phase 2's only `psse_job` edit is `study.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Solver selection (`"psse"` / `"pandapower"`) | `psse_job/study.py` (factory registry) | `pandapower_job/engine.py` (registers and wraps) | One string argument per D-02; the registry keeps the dependency one-way |
| Network load, copy, snapshot, reads, writes | `pandapower_job/api.py` (`PandapowerApi`) | `network.py`, `convert.py`, `raw.py` (Phase 1) | Adapter owns state; builder stays pure |
| Convergence rule, island detection | `pandapower_job/solve.py` (rule) | `api.py` (maps outcome to `SolveResult`) | Rule already exists; adapter only translates and enforces "no read after failure" |
| Scaling to city targets | `pandapower_job/scaling.py` (`scale_city`) | `api.py` (`scale_case`, `read_totals`) | Same logic as NET-03 (ROADMAP: "rather than writing it twice") |
| Mapping/settings preflight (thermal basis, solve options, voltage source, placeholder flag) | `pandapower_job/engine.py` | `study.py` (stage `mapping` failure path) | Needs the parsed mapping, which the API never sees |
| Settings provenance stored with each run | `engine.py` (adds to dispatch `details`) | database `details` jsonb (no schema change) | Phase 3 owns schema; `details` is free JSON |
| Study loops (N-1, margin, dispatch) | `psse_job` (unchanged) | - | Success criterion: runs unchanged |
| Result validation and write | `psse_job.run_record` / `job.run_once` / `writer` (unchanged) | local Postgres test harness | ENG-06 uses the existing path |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandapower | 3.5.6 (pinned, released 2026-10-07) | Load-flow solver | Already pinned and owner-approved in `requirements-pandapower.txt`; `pip index versions` reports 3.5.6 as latest [VERIFIED: pip index versions pandapower, 2026-11-18] |
| numpy / pandas / scipy | 2.4.3 / 2.3.3 / 1.17.1 | pandapower's numerics | Identical to `requirements.txt` pins by Phase 1 decision |
| pytest | 9.0.3 (in `.venv`) | Tests | Existing framework; `pytest.ini` has `pythonpath = backend`, `python_files = test_*.py *_test.py *_TestSuite.py` [VERIFIED: pytest.ini] |

No new package is installed by this phase. Phase 2 imports only `pandapower`, `copy`, `math`, `os`, `inspect` plus `psse_job` and existing `pandapower_job` modules.

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `psse_job.psse_api` | in repo | `PsseCallError`, `CaseProtected`, `BranchRow`, `BusRow`, `BranchFlow`, `SolveResult`, `CaseTotals`, `classify_solve`, `RATE_INDEX`, `THERMAL_BASES` | Reuse the same classes so the study's `except` clauses and value readers work unchanged |
| `pandapower_job.scaling` | in repo | `scale_city`, `ScalingDetails`, `ScalingRefused`, `ScalingUndetermined` | `scale_case`, `scale_load` rule |
| `pandapower_job.solve` | in repo | `run_load_flow`, `SolveSettings`, `settings_from_session` | `solve()` and the ENG-05 loader |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| String + registry in `study.py` | Injected `api_factory` callable (the earlier ARCHITECTURE.md sketch) | Callable is simplest and import-free, but D-02 says "a plain string". The registry satisfies D-02 and the one-way import rule at the cost of one registration side effect. A callable can be supported later without breaking the string. |
| Lazy `importlib.import_module("pandapower_job.api")` inside `study.py` | - | Rejected: `importlib` is not in `_STDLIB_ALLOWED` (the list reads `"__future__", "argparse", "base64", "binascii", "collections", "contextlib", "datetime", "fcntl", "functools", "hashlib", "http", "inspect", "json", "logging", "math", "msvcrt", "numbers", "os", "re", "socket", "subprocess", "sys", "tempfile", "time", "typing", "urllib", "uuid"` [VERIFIED: backend/tests/psse_contract_test.py:40-44]) and a literal `from pandapower_job import api` in `psse_job` fails `test_imports_stay_inside_the_laptop_boundary` (any non-stdlib, non-`psse_job` name outside `psycopg` is flagged, even inside a function) [VERIFIED: backend/tests/psse_contract_test.py:151-164] |
| Emulating `psspy` over pandapower (keep `PsseApi`) | - | Rejected in research and REQUIREMENTS "Out of Scope" |
| `pandapower.to_json` / `from_json` / pickle for network persistence | the project's own marker JSON (`convert.py`) | Never use pandapower's serialisers: they are a code-execution surface and break the fail-closed parser rule; the builder is the only constructor |
| `init="results"` warm starts | cold start each solve | Warm starts reintroduce contamination (D-09). Cold start is the Phase 1 setting. |

**Installation:** none. Existing: `python -m pip install -r requirements-pandapower.txt` (Mac venv / CI).

**Version verification:** `pip index versions pandapower` -> latest 3.5.6; the pinned set installed cleanly on Windows Python 3.12.10 in a scratch venv and the three existing Phase 1 pandapower test files passed there (100 passed in 42 s) [VERIFIED: scratch venv run, 2026-11-18].

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pandapower | PyPI | long-established (3.5.6 published 2026-10-07) | not reported by the seam (`unknown-downloads`) | github.com/e2nIEE/pandapower | SUS (only signal: unknown-downloads; no postinstall; not deprecated) | Already approved by the owner at plan 01-05 Task 1 on 2026-11-16 (wheel sha256 recorded in `requirements-pandapower.txt`); this phase installs nothing new and must not change the pin. No new checkpoint needed unless the pin moves. |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** pandapower (pre-approved, see above). numba is deliberately not added (not installed; pandapower warns it may be slow; the whole study ran in 35.5 s without it); adding it would need its own legitimacy checkpoint.

## Architecture Patterns

### System Architecture Diagram

```
hourly entry (Phase 5) / test
        |
        v
pandapower_job.engine.prepare_run(case_path, mapping_path, backend, ...)
  1. import pandapower_job.api  -> registers "pandapower" in study.API_FACTORIES
  2. psse_job.study.prepare_run(backend, case_path, mapping_path, solver="pandapower")
        -> PreparedRun(study, case_id, case_sha256, mapping_sha256, mapping_error)
  3. if mapping loads: PREFLIGHT  (thermal.basis == "current", solve.options is null,
        voltage.source == "config", backend settings decided and not None)
        -> refusal = failing_study("mapping", reason)
  4. wrap study: after StudyResults, add solve/scaling record to each dispatch details,
        psse_version -> None (version travels as solver_version for Phase 3)
        |
        v   study(selection, context)   (psse_job code, unchanged)
make_study -> index_case -> study._open_case -> API_FACTORIES["pandapower"](backend, case_path)
        |                                         = PandapowerApi(backend, protected_path=case_path)
        |   load_case(case_path)  -> build master once (raw/json -> build_network), deepcopy
        |   branch_table, bus_table  (structural reads, pu = NaN: nothing solved yet)
        v
 per city:  load_case(case_path)  [fresh deepcopy of master]
            read_totals / scale_case   -> scaling.scale_city (deepcopy, refusals)
            read_rate / set_rate       -> max_i_ka = MVA / (sqrt(3) kV)
            solve                      -> solve.run_load_flow -> SolveResult
                                          state: solved | failed
            bus_table / branch_loading -> only if state == solved, else PsseCallError
            save_case(tmp/CITY.sav)    -> in-memory snapshot (no file written)
            per outage:  load_case(snapshot) -> set_status -> solve -> (reads iff converged)
            per margin step: load_case(snapshot) -> define_subsystem -> scale_load -> solve -> reads
        v
 StudyResults -> run_record.validate_results -> job.run_once -> writer (local DB only in tests)
```

### Recommended Project Structure
```
backend/
  psse_job/study.py                 # ONLY psse_job edit: solver="psse" + API_FACTORIES registry (3.7 syntax)
  pandapower_job/
    api.py                          # PandapowerApi, PandapowerCallError, PandapowerBackend, registration
    engine.py                       # prepare_run wrapper, preflight, placeholder constants, record builder
    scaling.py                      # EXISTING; optional: extract case_totals(net, details) shared helper
    solve.py, network.py, ...       # EXISTING, unchanged
  tests/
    pandapower_api_test.py          # surface pin, contract vs PsseApi, reads/writes, state machine
    pandapower_engine_test.py       # preflight, island/non-convergence, order independence, ENG-06 in memory
    pandapower_study_job_test.py    # ENG-06 local-Postgres tier (skips without a database)
    pandapower_import_gate_test.py  # psse_job never imports or names pandapower; importing study loads neither
    psse_study_solver_test.py       # the new study.py argument: default, unknown solver, unregistered
    pandapower_study_fixture.py     # helper (not collected): case39 RAW with PT raised, placeholder mapping writer
```

### Pattern 1: The seam in `study.py` (registry, string argument)
**What:** one keyword `solver="psse"` on `_open_case`, `index_case`, `make_study`, `prepare_run` and `prepare_base`, resolved through a module-level dict. `psse_job` names no pandapower module; `pandapower_job.api` registers itself on import.
**When to use:** always; this is the whole of ENG-01's `study.py` change.
**Example:**
```python
# Source: derived from backend/psse_job/study.py:321-334 (read this session); 3.7-safe syntax
def _psse_factory(backend, case_path):
    return psse_api.PsseApi(backend, protected_path=case_path)

API_FACTORIES = {"psse": _psse_factory}

def register_solver(name, factory):
    """Called once by a solver package on import; never replaces an existing name."""
    if name in API_FACTORIES and API_FACTORIES[name] is not factory:
        raise ValueError("solver %r is already registered" % (name,))
    API_FACTORIES[name] = factory

def _open_case(psspy_module, case_path, solver="psse"):
    label = run_record.case_label(case_path)
    factory = API_FACTORIES.get(solver)
    if factory is None:
        raise StudyFailed("load_case", "solver %r is not available" % (solver,))
    try:
        api = factory(psspy_module, case_path)
        ...  # rest unchanged
```
Existing callers pass positionally up to `clock`/`budget`; the new parameter is last with a default, so every existing PSS/E test is untouched.

### Pattern 2: A state machine, not a flag, for "no result after a failed solve"
**What:** `PandapowerApi._state` in `{"fresh", "solved", "failed", "stale"}`. `load_case(case)` -> `fresh`; `load_case(snapshot)` -> `solved` only if the snapshot was saved from a solved state; `set_rate`, `set_status`, `scale_*`, `define_subsystem` -> `stale`; `solve` -> `solved` or `failed`. `branch_loading` requires `solved`. `bus_table` is allowed in `fresh` (structure, `pu` = NaN, because `study._open_case` reads it before any solve) and in `solved`; it raises in `failed` and `stale`.
**Why:** verified this session that `res_line` keeps its old numbers after `in_service` is changed without a re-solve (an outaged line still read `loading_percent = 28.593`), and that after a failed solve the result tables are not reliable. A NaN `pu` in the `fresh` state also makes `_read_solved_base` fail closed (`not bus.pu >= collapse_voltage_pu` is True for NaN) if a solve were ever skipped.
**Example:**
```python
# Source: pattern verified by the spike; messages carry no identifiers
def _require_solved(self, function):
    if self._state != "solved":
        raise PandapowerCallError(function, None, "no valid solution (state: %s)" % self._state)
```

### Pattern 3: `SolveResult` mapping (ENG-03)
`solve.run_load_flow` returns `SolveOutcome(converged, reason, iterations)` with `reason` in `{None, "not_converged", "nan_voltage", "voltage_collapse", <exception class name>}` [VERIFIED: backend/pandapower_job/solve.py:62-85]. Translate to the existing value type with the existing helper:

| pandapower outcome | `SolveResult` | PSS/E counterpart |
|--------------------|---------------|-------------------|
| converged | `classify_solve(0, 0, iterations, None)` | `fnsl` 0, `solved()` 0 |
| `nan_voltage` (island, unsupplied bus) | `classify_solve(3, None)` -> meaning `"fnsl ierr 3: buses in island without swing bus; ..."` | `FNSL_ERRORS[3]: "buses in island without swing bus"` |
| `not_converged`, `LoadflowNotConverged`, any other exception | `classify_solve(0, 1)` -> `"iteration limit exceeded"` (`SOLVED_MEANING[1]`) | non-converged `solved()` code |
| `voltage_collapse` | `classify_solve(0, 2)` -> `"blown up (non-divergent option disabled)"` | closest PSS/E code; D-04 is deliberately stricter (all in-service buses, not only monitored ones) |

Keep the exception class name (never its message) in a private attribute for tests; never in the stored meaning. `mismatch_mva` is `None`: `solve_base` skips the mismatch check when it is None [VERIFIED: study.py:279].

### Pattern 4: Reuse Phase 1, do not rewrite
`scale_case(load_mw, gen_mw)` = `self._net = scaling.scale_city(self._net, <obj with .load_mw/.gen_mw>, details)`. `scale_city` already deep-copies, applies the bounds and read-back imported from `psse_job.study`, and raises `ScalingRefused` / `ScalingUndetermined` (both `ValueError`, so `study.scale_city_case` turns them into `StudyFailed("apply_ratings", "scaling: <CITY>: ...")` with no figure) [VERIFIED: scaling.py:54-62, study.py:420-421]. `read_totals()` must use the same total definition as `scale_city` (generation = in-service `gen` P, plus the ext_grid's `psse_pg_mw` when `swing_in_total == "yes"`; raise `ScalingUndetermined("swing_in_total")` when inconclusive). Extract that one expression into `scaling.case_totals(net, details)` and have both call it; Phase 1 tests must stay green. `scale_load(sid, inc)`: scale P (and Q when `q_scales_with_p == "yes"`) of in-service loads on the subsystem's buses by `(P + inc) / P`; when `"no"`, add to P only; when `"inconclusive"` raise `ScalingUndetermined("q_scales_with_p")`; a subsystem with no load is a no-op, so `margin._check_loads_mapped_branches` fires exactly as on PSS/E (verified in the spike: the guard caught buses 2 and 6, which have no load).

### Pattern 5: The 14-method surface
The study code calls exactly these `PsseApi` methods (grep of `api.` in `psse_job/*.py`, this session): `branch_loading`, `branch_table`, `bus_table`, `define_subsystem`, `load_case`, `read_rate`, `read_totals`, `save_case`, `scale_case`, `scale_load`, `set_rate`, `set_status`, `solve`, `version`. Signatures to copy exactly [VERIFIED: backend/psse_job/psse_api.py]:

| Method | Signature |
|--------|-----------|
| `load_case` | `(self, path)` |
| `solve` | `(self, options=None)` |
| `branch_table` | `(self)` -> `(lines, transformers)` of `BranchRow`, sorted by key |
| `bus_table` | `(self)` -> `dict[int, BusRow]` |
| `branch_loading` | `(self, rate_set, basis)` -> `BranchFlow` list for lines only, sorted by key |
| `read_rate` | `(self, ref, rate_set)` |
| `set_rate` | `(self, ref, rate_set, mva)` |
| `set_status` | `(self, ref, in_service)` |
| `define_subsystem` | `(self, sid, buses)` |
| `scale_load` | `(self, sid, increment_mw)` |
| `read_totals` | `(self)` -> `CaseTotals(load_mw, gen_mw)` |
| `scale_case` | `(self, load_mw, gen_mw)` |
| `save_case` | `(self, path)` |
| `version` | `(self)` |

Constructor: `PandapowerApi(backend, protected_path=None)` (PsseApi's is `(psspy_module, protected_path=None)`); pin the public methods by `inspect.signature` equality, and the constructor by arity (`protected_path` is the second parameter). `calls` and `warnings` attributes are read only by `psse_api_test.py`, never by the study code; provide `warnings = []` for symmetry, skip `calls`.

### Pattern 6: Value mapping details
- **Keys:** bus number = `net.bus.index` (PSS/E numbers, builder); branch key = `"%d-%d-%s" % (from_bus, to_bus, ckt)` with `ckt = name.split("-", 2)[2]` (builder names are `raw.branch_key`; a circuit id can itself contain `-`, so split at most twice) [VERIFIED: network.py:197-213; the fixture splits the same way, pandapower_fixture.py `_split_key`].
- **`BranchRow`:** lines from `net.line` (`from_bus`, `to_bus`), transformers from `net.trafo` (`hv_bus`, `lv_bus`), `is_transformer` accordingly.
- **`BusRow`:** `type_code` 4 if not in service, 3 if an in-service ext_grid bus, 2 if an in-service gen bus, else 1 (downstream only compares `< 4`); `base_kv = vn_kv`; `pu = res_bus.vm_pu` when solved else NaN; `nvlmlo/nvlmhi = min_vm_pu/max_vm_pu` (the builder carries RAW NVLO/NVHI); `evlmlo/evlmhi = 0.0` (the builder does not carry EVLO/EVHI), which is why the engine refuses `voltage.source == "case"` (see Pitfall 7).
- **`BranchFlow`:** `rate_mva = sqrt(3) * vn_kv(from bus) * max_i_ka`; `pct = res_line.loading_percent`; `p_mw = p_from_mw`; `max_mva = max(hypot(p_from, q_from), hypot(p_to, q_to))`; `in_service` from the table. Lines only (PSS/E flag 2 = non-transformers).
- **`read_rate` / `set_rate`:** `max_i_ka = mva / (sqrt(3) * vn_kv)`; every rate set aliases the single limit (`RATE_INDEX` validation reused); `set_rate` and `set_status` on a transformer raise `PsseCallError`-compatible "branch is a two-winding transformer" (`BRANCH_CHNG_ERRORS[3]`), as PSS/E does; `read_rate` on a transformer: "branch not found" (the builder does not carry a transformer rating).
- **`load_case(path)`:** normalised path equal to the protected path -> build the master once (suffix `.json` -> `convert.case_from_json`, otherwise `raw.parse_raw`, then `network.build_network`) and return a deep copy; a path saved by `save_case` -> deep copy of that snapshot; anything else -> `PandapowerCallError("case", 3, "error opening the case file")` (`CASE_ERRORS[3]`). `save_case` onto the protected path raises `psse_api.CaseProtected`; otherwise it stores an in-memory snapshot and writes no file.
- **Errors:** raise a subclass `PandapowerCallError(psse_api.PsseCallError)` whose message says `pandapower.<function>` (the parent's text says `psspy.<function>`, misleading but harmless). It keeps `.function`, `.ierr`, `.meaning`, so `contingency._call_failure` (`getattr(error, "meaning", error)`) works. Builder and parser refusals (`RawRefused`, `BuildRefused`, `ConvertRefused`) are `ValueError` subclasses and are already caught by `study._open_case` [VERIFIED: raw.py:43, network.py:54, convert.py:46; study.py:331].

### Anti-Patterns to Avoid
- **Un-trip and re-solve:** never flip `in_service` back on the working net; always `load_case(snapshot)` (a deep copy). This is what `contingency.screen` documents.
- **Reading `res_gen` to detect an island:** verified the isolated generator's `res_gen.vm_pu` is not NaN while its bus is; check `res_bus` only (as `solve.run_load_flow` does).
- **Relying on `net.converged`:** True with NaN islanded buses on 3.5.6.
- **Hard-wiring settings:** the backend carries them; no module-level `SolveSettings(...)` used by the API itself (D-06).
- **Mutating the master:** assert in a test that the master's tables are unchanged after a full study.
- **Naming identifiers in messages:** no bus numbers, branch keys or targets in any exception text (Phase 1 convention; stored errors reach the database and logs).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Convergence rule (NaN, collapse, exception) | A second implementation in the API | `solve.run_load_flow` | Already tested at the boundaries in Phase 1 (`test_convergence_rule_nan_and_collapse`) |
| City scaling | New scaling arithmetic | `scaling.scale_city` | Refusals, bounds, read-back, clamp handling exist and are tested |
| Solve-result classification | New meaning strings | `psse_api.classify_solve`, `SOLVED_MEANING`, `FNSL_ERRORS` | `violations.non_convergence_row` reads these fields |
| Result validation | A pandapower-specific validator | `run_record.validate_results` | DDL-identity checks that make a row writable |
| Network construction | `pp.from_mpc`, `pp.networks.case39()` for the study, `pp.from_json` | `network.build_network` | Keeps PSS/E bus numbers and circuit names; case39 is a fixture only (REQUIREMENTS) |
| Per-solve isolation | Snapshot-and-restore of selected columns | `copy.deepcopy` | Measured 10-23 ms; the whole study is dominated by the ~65 ms solve; exactness beats a micro-optimisation |
| Local database | A mock connection | `psse_local_pg.cluster` + `job.run_once` | Existing harness; refuses non-local hosts |

**Key insight:** the risk in this phase is not computing anything new; it is silently diverging from the PSS/E study's observable behaviour (stale reads, islands read as clean, mislabelled basis). Every divergence has to be a loud, tested refusal.

## Runtime State Inventory

Not a rename/refactor/migration phase (additive code): omitted.

## Common Pitfalls

### Pitfall 1: Island read as a clean pass
**What goes wrong:** `net.converged` is True and islanded buses have NaN voltages; NaN compares false against every limit, so no violation row is raised and a worse grid looks fine.
**Why it happens:** pandapower's `check_connectivity` sets unsupplied buses out of service in the internal case. [CITED: pandapower.readthedocs.io/en/latest/powerflow/ac.html "If check finds unsupplied buses, they are set out of service in the ppc."] Verified: tripping `90016-90019-1` on the fixture gave `converged=True` with 4 NaN buses; an island holding a generator behaves the same.
**How to avoid:** `solve.run_load_flow` already returns `nan_voltage`; map it to `classify_solve(3, None)`. Test with a net built to island (case39 outage `90016-90019-1` with `contingency.scope: "all"`, or `contingency.extra`).
**Warning signs:** an outage with no row in pandapower where PSS/E has a `non_convergence` row.

### Pitfall 2: Stale results after a status change or a failed solve
**What goes wrong:** `res_line`/`res_bus` keep old numbers until the next solve (outaged line still read 28.593 percent loading after `in_service = False` with no re-solve).
**How to avoid:** the state machine (Pattern 2); test by calling every read in every state; record the call sequence of `contingency.screen` through a recording subclass and assert no read follows a failed solve before the next `load_case`.

### Pitfall 3: Out-of-service line reads as healthy
**What goes wrong:** after a converged non-islanding outage the tripped line has `loading_percent = 0.0` (not NaN) [VERIFIED: spike]. `violations._usable_flow` skips it only because `BranchFlow.in_service` is False, so `in_service` must come from the table, not from the results.

### Pitfall 4: Wrong thermal basis consumes the tolerance
**What goes wrong:** pandapower's `loading_percent = i_ka / (max_i_ka * df * parallel) * 100` [CITED: pandapower.readthedocs.io/en/latest/elements/line.html] is current-based; verified equal to `max(i_from, i_to) / max_i_ka * 100` to full precision. An MVA-basis reading differs by about 3 points on the public case (PITFALLS Pitfall 4), more than the 2 percent agreement tolerance.
**How to avoid:** refuse `thermal.basis == "mva"` (D-07); assert `df == 1` and `parallel == 1` on every line (builder defaults, but pin it in a test, because either silently changes the denominator).

### Pitfall 5: `scale_city` refuses on a fixture with binding limits
**What goes wrong:** several case39 machines sit at their `PT`, so any generation factor above 1 passes a limit; with the clamp detail inconclusive `scale_city` raises `ScalingUndetermined("clamped_at_limits")` [VERIFIED: 01-08-SUMMARY.md deviation 2].
**How to avoid:** the ENG-06 fixture raises every `PT` to 5000 (the spike did) and uses details `("yes", "no", "yes")`, clearly labelled placeholder; clamping behaviour keeps its own tests.

### Pitfall 6: Placeholder mapping sinks with no load
**What goes wrong:** case39 buses 2 and 6 carry no load; a sink there makes the margin guard raise `the transfer does not load the mapped branches (flow rose 0 MW ...)`. This is correct behaviour.
**How to avoid:** choose mapped lines whose far end is a loaded bus. Verified working placeholder (matpower numbers plus 90000): AUSTIN `90002-90003-1` sink `90003`; CORPUS_CHRISTI `90003-90004-1` sink `90004`; MIDLAND `90006-90007-1` sink `90007`; EL_PASO `90007-90008-1` sink `90008`; scaling targets 0.90, 0.92, 0.94, 0.96 of the fixture totals (load 6254.2 MW, generation 5620.0 MW).

### Pitfall 7: Settings the API cannot honour must not be ignored
**What goes wrong:** the mapping's `study` section is PSS/E-shaped. `solve.options` (8 integers for `fnsl`) cannot be honoured; `voltage.source == "case"` would read EVLMLO/EVLMHI that the pandapower net does not carry (they would be 0.0, and `violations._limits_and_source` silently falls back to the configured pair, a hidden difference from PSS/E); `thermal.basis == "mva"` cannot be reproduced; `rate_sets` with several entries all alias one limit (acceptable, the read-back passes).
**How to avoid:** `engine.prepare_run` preflight refuses the first three at stage `mapping` with a one-line, figure-free reason; the API also refuses `solve(options)` with options and `branch_loading(..., "mva")` as defence in depth. Default settings are `thermal_basis="current"`, `voltage_source="config"`, `solve_options=None` [VERIFIED: backend/psse_job/settings.py:88, 92, 113, quoted verbatim], so the placeholder and the default mapping pass.

### Pitfall 8: `enforce_q_lims` undecided
**What goes wrong:** `SolveSettings.enforce_q_lims` is `None` when PSE-02's var-limit classification is inconclusive ("the caller solves both ways", solve.py docstring). The hourly engine cannot run both and cannot guess.
**How to avoid:** the preflight refuses `None` for a study run (stage `mapping`, "reactive-limit setting is undecided"); resolving it is a D-14 human decision (see Open Questions). `run_load_flow` itself raises `ValueError` for a non-bool.

### Pitfall 9: A pandapower run stored as `psse`
**What goes wrong:** until Phase 3's migration, a run written through the v1 schema has run id `psse-...` and no `solver` column, i.e. it looks like PSS/E.
**How to avoid:** in Phase 2 write only to the throwaway local database (the Postgres tier), never to a live project; the Phase 2 end-to-end test must assert nothing about the `solver` column so it still passes after Phase 3 (and is extended there); `psse_version` is set to `None` for pandapower rows, the version travels as `solver_version` for Phase 3.

### Pitfall 10: Logging identifiers
**What goes wrong:** `job._log_run` logs `error[:300]` at WARNING and study failures name outages and buses; pandapower has its own logger.
**How to avoid:** Phase 2 messages are figure-free by construction (test: planted targets, bus numbers and branch keys must not appear in any `StudyFailed` message or `caplog` text, as `psse_study_job_test` does for targets). The public-log filter is Phase 5's job; record it as a hand-off.

## Code Examples

### The pinned-signature test (D-03, success criterion 1)
```python
# Source: pattern of psse_api_test.test_scale_layout_matches_the_fake; names verified in psse_api.py
import inspect
from psse_job import psse_api
from pandapower_job import api as pp_api

def _public_methods(cls):
    return sorted(n for n, v in inspect.getmembers(cls, inspect.isfunction) if not n.startswith("_"))

def test_public_surface_equals_psse_api():
    assert _public_methods(pp_api.PandapowerApi) == _public_methods(psse_api.PsseApi)
    for name in _public_methods(psse_api.PsseApi):
        want = inspect.signature(getattr(psse_api.PsseApi, name))
        got = inspect.signature(getattr(pp_api.PandapowerApi, name))
        assert got == want, name          # names, kinds and defaults, in order
    assert list(inspect.signature(pp_api.PandapowerApi.__init__).parameters)[2:] == ["protected_path"]
```

### Order and failed-solve independence (D-09, success criterion 4)
```python
# Source: derived from contingency.screen (reload before every outage); sketch
def test_outage_order_and_a_failed_solve_do_not_change_results(api_on_case39, outages):
    def run(order):
        out = {}
        for ref in order:
            api.load_case(saved_path)
            api.set_status(ref, False)
            result = api.solve()
            out[ref.key] = (result.converged,
                            api.branch_loading("RATEA", "current") if result.converged else None)
        return out
    forward = run(outages)
    backward = run(list(reversed(outages)))           # includes the islanding outage
    assert forward == backward                        # BranchFlow is a namedtuple: exact equality
```
`BranchFlow` and `BusRow` are namedtuples, so equality is exact; identical inputs on a cold start gave bitwise identical results in earlier research (PITFALLS Pitfall 9), and each solve here starts from a fresh copy.

### Engine preflight (ENG-02, Pitfall 7)
```python
# Source: settings.py (THERMAL_BASES, voltage_source, solve_options fields); sketch
def preflight(mapping, backend):
    s = mapping.settings
    if s.thermal_basis != "current":
        return "thermal basis %r cannot be reproduced by pandapower; use 'current'" % s.thermal_basis
    if s.solve_options is not None:
        return "solve.options are PSS/E fnsl options and are not supported; use null"
    if s.voltage_source != "config":
        return "voltage.source 'case' is not supported (emergency limits are not carried); use 'config'"
    if backend.solve_settings.enforce_q_lims is None:
        return "the reactive-limit setting is undecided; PSE-02 must decide it"
    return None
# refusal -> psse_job.study.failing_study("mapping", "pandapower: " + reason)
```

### Placeholder constants (D-06)
```python
# Source: solve.SolveSettings / scaling.ScalingDetails field lists (read this session)
PLACEHOLDER_NOTE = "placeholder: PSE-02 not recorded"
PLACEHOLDER_SOLVE = solve.SolveSettings(
    enforce_q_lims=False, tolerance_mva=1e-8, max_iteration=30, collapse_voltage_pu=0.5,
    sources={name: PLACEHOLDER_NOTE for name in ("enforce_q_lims", "tolerance_mva", "max_iteration")},
    deviations=("placeholder: not copied from PSS/E",))
PLACEHOLDER_DETAILS = scaling.ScalingDetails("yes", "no", "yes", {"placeholder": True})
```
`collapse_voltage_pu` must come from `mapping.settings.collapse_voltage_pu` at preparation time (default 0.5) so there is one source of truth; the API never sees the mapping, so `engine.prepare_run` copies it into the backend. A predicate `is_placeholder(backend)` (any `sources` value starting with `placeholder`) lets Phase 5 refuse live writes on placeholder settings.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Emulate `psspy` over pandapower (earlier idea) | Duck-typed adapter with the same 14 methods | Research 2026-11-16 | No SURFACE/`scal_2` state machine to re-create |
| Injected `api_factory` callable (ARCHITECTURE.md sketch) | String + registry (D-02) | 2026-11-18 (CONTEXT) | Same single seam; keeps `psse_job` import-clean |
| `pandapower.networks.case39()` as the network | Builder from the RAW / converted JSON; case39 as fixture only | Phase 1 | PSS/E bus numbers and circuit names preserved |

**Deprecated/outdated:** pandapower's `tap_dependency_table` DeprecationWarning appears in the existing tests (cosmetic, pandapower 3.5.6). Out-of-service results: lines read 0.0 loading, buses NaN [VERIFIED: spike on 3.5.6]; older research notes on 3.2.2 differ in detail.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PSS/E's current-basis loading (`MAXPCTRATE`) equals pandapower's `loading_percent` (larger-end current over the rating's current at nominal kV) | Pattern 6, Pitfall 4 | Uniform few-percent offset in every thermal row; consumes the AGR 2 percent tolerance. Pandapower side is verified; PSS/E side is not. Phase 4 decides. |
| A2 | The PSS/E increment form used by the margin (`scal_2`, status mode 3) distributes the increment proportionally over the sink loads and scales Q per `q_scales_with_p` | Pattern 4 | Margin differs from PSS/E; settles when PSE-02 records the detail |
| A3 | The real private mapping uses the defaults `thermal.basis "current"`, `voltage.source "config"`, `solve.options null` | Pitfall 7 | The preflight would refuse the real mapping on first use (loud, safe, but a schedule hit) |
| A4 | PSS/E's recorded `non_convergence` rows for islands carry `ierr 3`; mapping an island to `classify_solve(3, None)` mirrors them | Pattern 3 | Only the stored `details.ierr/solved/meaning` text would differ; AGR-02 compares outage ids, not codes |
| A5 | A GitHub Actions runner solves the four-city study in a similar time (35.5 s measured on a Windows laptop) | Summary | Budget (1500 s default, workflow under one hour) has about 40x headroom, so low risk |
| A6 | A local Postgres (initdb/pg_ctl) is installed where the owner runs Phase 2 tests | Validation Architecture | The ENG-06 database tier skips (it is not installed on this research machine); the in-memory tier still proves the study |
| A7 | Putting the solve/scaling record in each dispatch row's `details` satisfies "stored with each run" | ENG-05 | If the owner wants a run-level column, Phase 3's migration would have to carry it |

## Open Questions

1. **What if PSE-02's var-limit classification is inconclusive?**
   - What we know: `settings_from_session` returns `enforce_q_lims = None` and Phase 1's NET-03 solves both ways.
   - What's unclear: the hourly engine needs one value.
   - Recommendation: the engine refuses `None` (preflight); escalate to the owner as a D-14 decision when 01-10 records PSE-02. Do not pick a physics default.

2. **`case_path` for the pandapower study: RAW or converted JSON?**
   - What we know: `prepare_run` hashes the file (`case_sha256`) and labels it (`case_id`); Phase 1 plan 01-11 decides whether the converted network is committed, or stored as a GitHub secret.
   - Recommendation: `PandapowerApi` accepts both (suffix `.json` -> `convert.case_from_json`, else `raw.parse_raw`); tests use a RAW generated into `tmp_path`.

3. **Where are the recorded PSE-02 values loaded from for ENG-05?**
   - What we know: `pandapower_net_check.py check` writes `report.json` (key `settings`: enforce_q_lims, tolerance_mva, max_iteration, collapse_voltage_pu, sources, deviations) and `scaling_details.json` (three details plus evidence) under `<session>/check_<stamp>/`, both private, both free of identifiers [VERIFIED: cli.py:283-290, 547-567].
   - Recommendation: add `engine.backend_from_records(settings_record, scaling_details)` (fail-closed validation, values must be of the right type) so closing ENG-05 is a data drop-in once 01-10 finishes; keep the final "wire the real values" step as a separate plan or task gated on 01-10 (autonomous: false).

4. **`voltage.source "case"`:** refuse (recommended), or extend the builder to carry EVHI/EVLO as extra bus columns? Phase 1 code and its parity tests would change; refusal is cheaper and fail-closed.

5. **Phase 1 reference answers for outages and margins** (private, exported by the session for "Phase 2 to test against", 01-CONTEXT D-09/D-10): they exist only on the owner's machine after 01-10. Recommendation: do not build that comparison in Phase 2 (it is AGR-02's job in Phase 4); keep Phase 2 on the public fixture.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | all tests | yes | 3.12.10 (repo `.venv`) | - |
| pytest | tests | yes | 9.0.3 (`.venv`) | - |
| pandapower + pins | `pandapower_*` tests | not in the repo `.venv` on this machine; installed cleanly in a scratch venv from `requirements-pandapower.txt` | 3.5.6 | tests `importorskip`; run them in the Mac venv (Phase 1 convention) |
| Local Postgres (`initdb`, `pg_ctl`) | ENG-06 database tier | no (`which postgres pg_ctl initdb` found none) | - | In-memory tier (study + `validate_results` + `build_run_record` + `result_rows`) always runs; the database tier skips unless `DLR_TEST_PG_AUTOSTART=1` or `DLR_TEST_DATABASE_URL` is set; `PSSE_REQUIRE_PG=1` makes a missing database a failure |
| numba | speed | no (not installed, not wanted) | - | none needed (35.5 s whole study) |

**Missing dependencies with no fallback:** none for Phase 2 code.
**Missing dependencies with fallback:** Postgres on this machine (use the Mac or the in-memory tier).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Quick run command | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_api_test.py backend/tests/pandapower_engine_test.py backend/tests/psse_study_solver_test.py backend/tests/pandapower_import_gate_test.py` (run in a venv with `requirements-pandapower.txt`) |
| Full suite command | the quick files plus the PSS/E regression set `backend/tests/psse_study_test.py psse_contingency_test.py psse_margin_test.py psse_api_test.py psse_contract_test.py psse_dispatch_test.py psse_scaling_test.py` and Phase 1's `pandapower_network_test.py pandapower_compare_test.py pandapower_raw_test.py` |

Measured baselines this session: the seven PSS/E files, 201 passed in 16.5 s (no pandapower needed); the three Phase 1 pandapower files, 100 passed in 42 s. The study spike took 35.5 s, so the in-memory end-to-end test should use `contingency.scope: "neighbourhood"` with the default hops to stay near that, and a module-scoped fixture so it runs once.

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENG-01 | Public method names and signatures equal `PsseApi`'s; the exceptions raised are `PsseCallError`/`ValueError`/`CaseProtected` instances | unit | `pytest backend/tests/pandapower_api_test.py -k "surface or contract" -x` | Wave 0 |
| ENG-01 | `solver` defaults to `"psse"`; unknown solver and unregistered `"pandapower"` fail closed at `load_case`; importing `psse_job.study` loads no pandapower and `psse_job` never names it | unit/gate | `pytest backend/tests/psse_study_solver_test.py backend/tests/pandapower_import_gate_test.py -x` | Wave 0 |
| ENG-01 | Existing PSS/E tests pass unchanged | regression | the seven PSS/E files above | exists (201 pass) |
| ENG-01 | Behavioural contract: the same call script on `PsseApi(FakePsspy)` and `PandapowerApi` returns the same types, ordering and refusal behaviour (not values) | contract | `pytest backend/tests/pandapower_api_test.py -k contract` | Wave 0 |
| ENG-02 | After `apply_ratings`, `max_i_ka == circuit_amps / 1000`; `read_rate` round-trips; `loading_percent` equals `max(i_from, i_to) / max_i_ka * 100`; `df == 1`, `parallel == 1` | unit | `pytest backend/tests/pandapower_api_test.py -k rating` | Wave 0 |
| ENG-02 | `thermal.basis "mva"` refused at stage `mapping` (engine) and by `branch_loading` (API); `solve.options` and `voltage.source "case"` likewise | unit | `pytest backend/tests/pandapower_engine_test.py -k preflight` | Wave 0 |
| ENG-03 | Island outage -> one `non_convergence` row (`ierr 3`) while `net.converged` is True; non-convergence (heavy load) -> row; collapse -> row; no violation rows for that outage; other outages still screened | unit | `pytest backend/tests/pandapower_engine_test.py -k "island or nonconv or collapse"` | Wave 0 |
| ENG-04 | Outage order reversed and a failed solve in between give equal `BranchFlow`/`BusRow` results; reads after a failed solve raise; the recorded call sequence of `contingency.screen` has no read between a failed solve and the next `load_case`; master unchanged after a study | unit | `pytest backend/tests/pandapower_engine_test.py -k "order or stale or fresh"` | Wave 0 |
| ENG-05 | The settings and scaling details come from the backend (no module-level hard-wiring); placeholders are labelled and stored in each dispatch row's `details`; `is_placeholder` true for placeholders and false for recorded records; `backend_from_records` refuses bad shapes; `enforce_q_lims None` refused | unit | `pytest backend/tests/pandapower_engine_test.py -k "settings or placeholder"` | Wave 0 (final wiring to recorded values gated on plan 01-10) |
| ENG-06 | Four cities end to end with a placeholder mapping on the case39 fixture: `StudyResults` for four cities, `validate_results` passes, no network access, no file left in the temp directory, nothing private in output | integration (in memory) | `pytest backend/tests/pandapower_engine_test.py -k end_to_end` | Wave 0 |
| ENG-06 | Same study through `job.run_once` and the real writer into a throwaway local Postgres: `1 + 4 + 4 + N` rows, completeness checks ok; fetch is a fake (no REST), connection is a local role | integration (database) | `DLR_TEST_PG_AUTOSTART=1 pytest backend/tests/pandapower_study_job_test.py` | Wave 0 (skips without a database) |

### Sampling Rate
- **Per task commit:** the quick command for the file touched (api: `pandapower_api_test.py`; study.py edit: `psse_study_solver_test.py` plus the seven PSS/E files).
- **Per wave merge:** quick command plus the PSS/E regression set plus Phase 1's three pandapower files.
- **Phase gate:** full suite green (database tier green where Postgres exists, with `PSSE_REQUIRE_PG=1` on that machine) and the staged leak scan exit 0, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/pandapower_api_test.py` - ENG-01, ENG-02, ENG-04 (API-level state machine, reads, writes, contract vs `PsseApi`)
- [ ] `backend/tests/pandapower_engine_test.py` - ENG-02 preflight, ENG-03, ENG-04, ENG-05, ENG-06 in memory
- [ ] `backend/tests/pandapower_study_job_test.py` - ENG-06 database tier
- [ ] `backend/tests/pandapower_import_gate_test.py`, `backend/tests/psse_study_solver_test.py` - the seam
- [ ] `backend/tests/pandapower_study_fixture.py` (not collected) - case39 RAW with `PT` raised, a placeholder-mapping writer (`placeholder: true`, loaded sinks above), the placeholder backend
- [ ] Framework install: none (`pytest` present); pandapower venv per `requirements-pandapower.txt`

Two reminders for the test author: (1) a stub that returns a made-up `SolveResult` proves nothing about islands; test the real `PandapowerApi.solve` on a net that really islands; (2) the leak convention: any text assertion that a value did not leak should list the synthetic targets in every text form (`repr`, `%g`, `%.1f`) as `psse_study_job_test._synthetic_target_texts` does.

## Security Domain

`security_enforcement` is not set to `false` in `.planning/workstreams/pandapower-solver/config.json` (keys: `workflow._auto_chain_active` only), so it is treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no new credential; Phase 2 touches no database role except the throwaway local one in tests) | - |
| V3 Session Management | no | - |
| V4 Access Control | no (private data stays under `data/private/`, git-ignored; Phase 2 adds no endpoint) | existing ignore rules and leak scan |
| V5 Input Validation | yes | the network file is parsed only by `raw.parse_raw` / `convert.case_from_json` (fail closed, reason-only messages); the mapping only by `mapping.parse_mapping`; the API validates every argument (finite numbers, integer buses, `sid` 0 to 11, rate set names) before use; never `pp.from_json` / pickle |
| V6 Cryptography | no (the existing sha256 of the case file, `run_record.file_sha256`, is reused, not new crypto) | - |
| V7 Error handling and logging | yes | exception messages hold a reason or function name only, never a bus number, branch key or target; `redaction.redact` already applies on the stored path |
| V14 Configuration | yes | settings come from the backend object with recorded provenance; placeholders are flagged so a live write can refuse them |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Private grid identifiers or study values in an exception, log or committed fixture | Information disclosure | figure-free messages; fixtures only from case39 + offset 90000 generated into `tmp_path`; staged leak scan before every commit; planted-value leak tests |
| Untrusted network file reaching a deserialiser that executes code | Tampering / EoP | only the project's own fail-closed parsers; no pandapower (de)serialisers, no pickle |
| A pandapower result stored as, or mistaken for, a PSS/E result | Spoofing / Repudiation | local database only in Phase 2; `psse_version = None`; `solver` tag is Phase 3's job; a placeholder predicate guards live writes |
| Stale or partial results presented as current | Tampering (integrity) | state machine, fresh deep copy per solve, reads refused after a failed solve |
| Mapping that silently selects an unsupported mode (MVA basis, case voltage limits, fnsl options) | Tampering (integrity) | preflight refusal at stage `mapping` |

## Sources

### Primary (HIGH confidence)
- Repository, read in full this session: `backend/psse_job/psse_api.py`, `study.py`, `contingency.py`, `margin.py`, `violations.py`, `dispatch.py`, `settings.py`, `mapping.py`, `contract.py`, `constants.py`, `units.py`, `job.py`; `run_record.py` (lines 100-230, 300-494); `backend/pandapower_job/network.py`, `scaling.py`, `solve.py`, `convert.py`, `cli.py` (settings and scaling-record parts); `backend/tests/psse_contract_test.py`, `pandapower_fixture.py`, `pandapower_network_test.py` (head), `psse_study_job_test.py` (head), `psse_api_test.py` (head), `psse_fake_psspy.py` (head), `psse_local_pg.py` (head); `pytest.ini`, `requirements-pandapower.txt`.
- Workstream: `02-CONTEXT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, `research/ARCHITECTURE.md`, `research/PITFALLS.md`, `01-CONTEXT.md` (head), `01-08-SUMMARY.md`.
- Scratch-venv experiments (pandapower 3.5.6, Python 3.12.10, pins from `requirements-pandapower.txt`, 2026-11-18): island behaviour, `LoadflowNotConverged` location, stale results, out-of-service line results, loading percent, deep-copy and solve timing, and a throwaway four-city study through the unchanged study code.
- [pandapower line element docs](https://pandapower.readthedocs.io/en/latest/elements/line.html) - loading_percent formula, `df`, `parallel`.
- [pandapower AC power flow docs](https://pandapower.readthedocs.io/en/latest/powerflow/ac.html) - `check_connectivity`, `enforce_q_lims`.

### Secondary (MEDIUM confidence)
- `pip index versions pandapower` (3.5.6 latest) and the legitimacy seam (`SUS`, only `unknown-downloads`).

### Tertiary (LOW confidence)
- None used for a recommendation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new package; pins re-installed and Phase 1 tests re-run
- Architecture: HIGH - the seam was exercised end to end by a spike through unchanged study code
- Pitfalls: HIGH for pandapower behaviour (re-run), MEDIUM for agreement with PSS/E (A1, A2, A4 unverified until PSE-02 and Phase 4)

**Research date:** 2026-11-18
**Valid until:** 2026-12-18 (pandapower is pinned, so drift is a deliberate act; the PSE-02 values arriving can change the settings plan sooner)
