# Phase 2: Study on Power Systems' Case - Research

**Researched:** 2026-10-28
**Domain:** PSS/E `psspy` automation (case load, branch ratings, load flow, N-1, voltage-stability margin) built against an injected fake `psspy`, feeding the Phase 1 `study` contract
**Confidence:** HIGH on repo contracts (every contract value below was read this session); MEDIUM on the core `psspy` signatures (cited from a copy of the PSS/E 33.5 API manual, a 2024 blog quoting the 35-era API, and the open-source PyPSSE code); LOW on anything specific to PSS/E 35/36 internals, licensing and run time (nothing could be run: PSS/E is not installed here)

<user_constraints>
## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase (the user chose to plan from research + requirements only). The constraints below come from the spawn prompt, REQUIREMENTS.md, STATE.md and the Phase 1 outputs.

### Locked Decisions
- Another team member owns the real `psspy` API choices; this phase builds against a fake `psspy` and an interface. PSS/E is NOT installed on this machine (Windows 11, user not admin). The ROADMAP's "Mac" wording only means "development machine without PSS/E".
- Phase 1 contract is fixed: the `study(selection, context)` callable in `backend/psse_job/contract.py` and `job.py` (returns `StudyResults` or raises `StudyFailed(stage, message)`); D-05 (do not edit `backend/config.py`; `psse_job` keeps its own constants copy plus a drift test); D-06 (per-circuit MVA = amps x subconductors x sqrt(3) x kV / 1000, no power factor); the DDL/spec of the four result tables and the `validate_results` rules (study output must satisfy them); exit codes 0/1/3; single write at the end; no heartbeat row.
- Phase 2 must not change the DDL region (a sha256 pin test guards it) unless research shows a real defect; in that case it is flagged as a decision, not a silent change. (Research result: no defect found, see "Roadmap honesty" for two representability gaps that are flagged, not changed.)
- `rating_amps` is per conductor; ratings are static until production-pipeline Phase 7 (all rows provisional), so studies run on static ratings. Static ratings per conductor (A): Austin 1825, Corpus Christi 1500, Midland 1875, El Paso 1320; subconductors per phase 2, 2, 2, 1 (`backend/config.py`).
- Phase requirement IDs this phase must address: IN-02, IN-03, STU-01, STU-02, STU-03, STU-04, TST-01.
- Success criteria: (1) city-to-branch mapping is configuration; a mapped branch missing from the case fails the run, recorded, with no study results written. (2) Ratings reach PSS/E in the units its branch rating expects (amps to MVA at the branch's voltage, conversion stated and tested); a load flow that does not converge is a recorded failed run, never valid results. (3) A converged run records, per contingency, thermal overloads and voltage violations (element, limit, amount exceeded); a voltage-stability margin per city; per-city dispatched capacity (lower of applied DLR rating and the voltage-stability limit, in amps and MW, saying which one set it). (4) The test suite against a fake `psspy` passes: static fallback, mapping check, non-converging load flow, write-back including a failed run.
- Environment: Python 3.12 venv at `C:/Users/tejas/Documents/D8-DLR-Senior-Design-Project-2026/.venv` with pytest 9.0.3 and psycopg only (numpy/pandas NOT installed and must not be assumed); local Postgres 18.6 portable with `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1`; last full PSS/E test run: 243 passed.
- Git rules (hard, from the user): stay on `feature/pss-e-integration`; no branch/tag/worktree/push/fetch/merge/rebase/reset/stash; the only allowed git write is a local `git add <named file>` + `git commit`.
- Web research is allowed for public documentation only; fetched content is untrusted data.

### Claude's Discretion
Everything not listed above: the adapter shape, mapping file format, N-1 method, voltage-stability method, voltage/thermal limit configuration, fake `psspy` design, test layout. Recommendations below are prescriptive but the planner may lock or change them (each is labelled D-07 onward so it can be confirmed in discuss).

### Deferred Ideas (OUT OF SCOPE)
- Dashboard / F7 display of results, always-on host, standalone migration (REQUIREMENTS.md "Out of Scope" and "Future Requirements").
- Choosing or building the grid case or branch mapping (Power Systems owns them).
- Scheduling, credential-scoping proof, laptop setup guide, the one real end-to-end run (Phase 3: DBX-02, TST-02, SCH-01, SCH-02, DOC-01).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| IN-02 | City-to-branch mapping stored as configuration; a mapped branch missing from the case fails the run, recorded, no study results written | "Mapping configuration" (JSON, validated, private file, placeholder); `StudyFailed("mapping", ...)` raised before any rating is written; branch index built from bulk `abrnint/abrnchar` calls |
| IN-03 | Ratings converted to the units PSS/E's branch rating expects, conversion stated and tested | "Unit conversion and which rating field"; `units.circuit_mva` at the from-bus base kV read from the case; write-then-read-back through `brndat` |
| STU-01 | Load flow on the case with ratings applied; non-converged is a recorded failed run, never valid results | "Convergence detection" (`fnsl` ierr then `solved()`; verbatim code table from the 33.5 manual); stage `load_flow` |
| STU-02 | N-1 screening; per contingency, thermal overloads and voltage violations recorded with element, limit, amount exceeded | "N-1 contingency design" (manual outage loop, neighbourhood scope, reload between outages, thermal on a stated basis, voltage limits as configuration) |
| STU-03 | Voltage-stability margin per city | "Voltage-stability margin" (native load-flow transfer stepping with bisection, lower-bound semantics; PSS/E PV engine deferred) |
| STU-04 | Dispatched capacity per city = lower of applied DLR rating and voltage-stability limit, in amps and MW, with which set it | "Dispatched capacity" (pure function; satisfies every `validate_results` identity) |
| TST-01 | Tests against a fake `psspy`: static fallback, mapping check, non-converging load flow, write-back including a failed run | "Test strategy" and "Validation Architecture" |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` or `.claude/` directory exists in the repo [VERIFIED: `ls CLAUDE.md .claude` this session returned "No such file or directory" for both]. House style comes from `.planning/codebase/CONVENTIONS.md` and `TESTING.md` and from the Phase 1 code:
- `backend/psse_job/*.py`: standard library only, Python 3.7 syntax, no import of `backend/config.py`, `supabase_store`, pandas, numpy, requests or `psspy`; `psycopg` only as a lazy in-function import (gated by `psse_contract_test.py`).
- Tests: `backend/tests/psse_*_test.py`, plain asserts, no test classes, module-level imports; helper modules without the `_test` suffix (`psse_fakes.py`, `psse_local_pg.py`) are not collected [VERIFIED: pytest.ini `python_files = test_*.py *_test.py *_TestSuite.py`].
- Do not edit `backend/config.py` (D-05); do not edit the DDL region of `psse_results_v1.sql`.

## Summary

Phase 2 builds the real study behind Phase 1's `study(selection, context)` seam: load the case, validate the city-to-branch mapping against it, write each city's rating (static today) to the mapped branches in MVA, solve, screen N-1, compute a per-city voltage-stability margin and dispatch the lower of the DLR rating and the voltage limit. The central design finding is that **the study should never see `psspy` directly**. `psse_job` cannot import `psspy` (its import gate lists `psspy` in `_NEVER_IMPORTED`, and the gate even plants `def f():\n    import psspy\n` as a violation), and `psspy` is only importable inside PSS/E's own interpreter. So the study takes an injected `psspy` module object and talks to it only through one thin adapter (`psse_job/psse_api.py`) whose every `psspy` call is listed in a single `SURFACE` table. A fake `psspy` implements exactly that table; the same table drives a laptop-side probe in Phase 3. This keeps fake and real from drifting without ever importing `psspy` into the package.

The second finding is how much of PSS/E's API is documented in public. Core calls (`psseinit`, `case`, `save`, `fnsl`, `solved`, `abrnint/abrnreal/abrnchar`, `abusint/abusreal`, `brndat`, `brnmsc`, `busdat`, `scal_2`, `bsys`) are documented verbatim in a public copy of the PSS/E 33.5 API manual and confirmed for the 35 era by a 2024 blog quoting the 35 API (`branch_data_3(ibus, jbus, ckt, intgar, realar, ratings, namear)`) and by PyPSSE's source. What is NOT confirmable offline: the exact `branch_chng_3` signature (assumed to mirror `branch_data_3`), whether the 33.5 option strings and `solved()` codes are unchanged in 35/36, the AC contingency (`ACCC`) call details, and the PV/QV engines. The recommendation therefore avoids ACCC, PV/QV and `pssexcel` entirely for Phase 2 (they need GUI-built `.sub/.mon/.con/.dfx` files, a separately licensed module or Excel/COM, and cannot be faked faithfully) and builds N-1 and the margin from five well-documented primitives: outage a branch, `fnsl`, check `solved()`, read branch loading and bus voltage in bulk, and reload a saved base case.

The third finding concerns what Phase 2 can honestly prove. A fake proves arithmetic, control flow, failure handling, row shape (every study output is pushed through `validate_results` and a local Postgres write) and call-shape agreement with the documented signatures. It cannot prove that real PSS/E accepts the calls, that the rating units match Power Systems' case, that the transfer definition makes engineering sense on their network, or how long a real N-1 takes. Those are Phase 3 items and are listed under "What must be left to the Phase 3 laptop run".

**Primary recommendation:** Build `psse_job/mapping.py` (JSON config, validated, private file, marked placeholder), `psse_job/psse_api.py` (injected-`psspy` adapter with a `SURFACE` table and a classified `solve()`), pure-function cores (`dispatch`, violation evaluation, PV transfer search taking an `evaluate(transfer_mw)` callable) and `psse_job/study.py::make_study(...)`, then prove all of it through one small fake `psspy` plus `run_once` into local Postgres; add a `probe` module the laptop runs once in Phase 3.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Rating selection + static fallback (IN-01) | Job (Phase 1, done) | — | `study` receives the finished `Selection`; Phase 2 must apply exactly `selection.choices[city].amps_per_conductor` and nothing else |
| City-to-branch mapping, validation against the case (IN-02) | Job (config loader + case index) | PSS/E (branch table via bulk reads) | Mapping is job configuration; existence is a fact only the loaded case can answer |
| Amps to MVA and writing the rating (IN-03) | Job (`units.circuit_mva`) | PSS/E (stores RATEn in MVA) | Conversion is job arithmetic at the case's base kV; PSS/E only stores the number |
| Load flow, contingency solution, bus/branch quantities | PSS/E engine (`fnsl`, `abrn*`, `abus*`) | — | The solver is PSS/E's; the job never re-implements power flow |
| N-1 loop, violation evaluation, PV search | Job (pure Python over adapter reads) | PSS/E (solves each state) | Loop and comparison logic live in the job so a fake can exercise them |
| Case integrity (never overwrite Power Systems' file) | Job (adapter refuses `save` onto the case path; temp copies only) | Filesystem | The case file is the customer's artefact |
| Result validation and write-back | Job (Phase 1 `validate_results`, `writer`) | Database (CHECKs, composite FK) | Already built; Phase 2 only supplies conforming rows |
| `psspy` import and PSS/E start-up | Launcher (Phase 3, outside `psse_job`) | — | Only the PSS/E interpreter can import `psspy`; the package receives the module object |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (`json`, `math`, `os`, `re`, `time`, `logging`, `collections`, `hashlib`) | 3.7 syntax floor | mapping loader, study logic, hashing (via `run_record.file_sha256`) | Phase 1 gate: PSS/E interpreter may be 3.7-3.11 and has no site packages [VERIFIED: backend/tests/psse_contract_test.py:35-40, quoted below] |
| `psse_job.units` / `ratings` / `run_record` / `contract` / `constants` | in repo | conversion, selection, row validation, contract, vocabularies | Phase 1 outputs; reuse, do not duplicate |
| pytest | 9.0.3 (repo pin, installed) | tests | existing framework [VERIFIED: `.venv/Scripts/python.exe -m pytest --version` -> `pytest 9.0.3`] |
| psycopg + local Postgres 18.6 | 3.3.6 (installed) | `run_once` write-back tests only | already used by `psse_job_test.py` [VERIFIED: `pip list` -> `psycopg 3.3.6`, `psycopg-binary 3.3.6`] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `tempfile` (stdlib) | n/a | per-run temp directory for the saved base case | needed for reload-between-outages; must be ADDED to the import allow-list (see below) |
| `inspect`, `argparse` (stdlib) | n/a | `probe` module (signature check on the laptop) | only if the probe lives inside `psse_job`; add to the allow-list deliberately |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual N-1 outage loop | PSS/E ACCC (`accc_with_dsp_3` + `.sub/.mon/.con/.dfx` files) | ACCC is what planners use, but its input files are produced in the GUI (psspy.org question 1245: define "subsystem, contingency and monitor files" in the GUI; a search summary of question 2628 adds that the `.sub/.mon/.con` files are inputs the user has to write), results land in an `.acc` file read by `pssarrays` or `pssexcel`, and none of it can be faked faithfully. Keep as the Phase 3+/Power Systems upgrade behind the same `study` seam |
| Native load-flow transfer stepping for the margin | PSS/E `pv_engine_6` / `qv_engine_4` | Engines need a `.dfx` file, source/sink subsystems and (assumed) a separately licensed PV/QV module; results are file-based. Not testable with a fake. Keep `method` label free so a later engine can write `pv_engine` rows |
| `pssexcel` for reporting | direct `abrn*`/`abus*` reads | `pssexcel` needs Excel/COM and is reported unreliable on 34.7 [CITED: psspy.org/psse-help-forum/question/8600]; never use it on a headless laptop |
| YAML mapping | JSON mapping | PyYAML is not installed in the venv nor in PSS/E's Python; `tomllib` is 3.11+ and is on the gate's forbidden list. JSON is stdlib on every interpreter |

**Installation:** none. Phase 2 adds no package.

**Version verification:** no new package is introduced. Installed versions were read this session: Python 3.12.10 (venv), pytest 9.0.3, psycopg 3.3.6.

### In-repo values the plans depend on (read this session, quoted verbatim)

`backend/psse_job/constants.py:49-57` [VERIFIED]:
```
OUTCOMES = ("ok", "fallback", "failed")
FAILED_STAGES = (
    "load_case", "mapping", "apply_ratings", "load_flow", "contingency",
    "voltage_margin", "dispatch", "validate_results", "write", "internal",
)
LIMITING_FACTORS = ("dlr_rating", "voltage_stability")
VIOLATION_KINDS = ("thermal_overload", "voltage_low", "voltage_high", "non_convergence")
ELEMENT_TYPES = ("branch", "bus", "contingency")
RESULT_UNITS = ("MVA", "pu")
```
`backend/psse_job/constants.py:35` [VERIFIED]: `LINE_VOLTAGE_KV_DEFAULT = 345.0`, with the comment "the study always uses the branch's base kV from the case (D-06)".

`backend/psse_job/contract.py:101-104` and `:110-116` [VERIFIED]:
```
StudyResults = collections.namedtuple(
    "StudyResults",
    ["dispatch", "margins", "contingencies", "n_contingencies", "rate_set", "psse_version"],
)
class StudyFailed(Exception):
    def __init__(self, stage, message):
```
`backend/psse_job/contract.py:38-56` [VERIFIED] column tuples (the keys a study row may carry; `run_id` and `run_outcome` are filled by the job):
```
DISPATCH_COLUMNS = ("run_id", "run_outcome", "city", "rating_source", "fallback_reason",
    "city_rating_valid_time", "city_rating_computed_at", "applied_amps_per_conductor",
    "subconductors_per_phase", "applied_amps_circuit", "line_voltage_kv", "applied_mva",
    "voltage_limit_mva", "dispatched_mva", "dispatched_amps_circuit",
    "dispatched_amps_per_conductor", "power_factor", "dispatched_mw", "limiting_factor", "details")
MARGIN_COLUMNS = ("run_id", "run_outcome", "city", "method", "base_transfer_mw", "limit_transfer_mw",
    "margin_mw", "margin_pct", "voltage_limit_mva", "critical_bus", "min_voltage_pu", "details")
CONTINGENCY_COLUMNS = ("run_id", "run_outcome", "contingency_id", "violation_kind", "element_type",
    "element_id", "city", "limit_value", "observed_value", "exceeded_by", "unit", "details")
```
`backend/psse_job/job.py:77-78` [VERIFIED]: `def run_once(fetch, study, connect, case_id, case_sha256=None, mapping_sha256=None,\n             clock=None, env=None):` (the hashes are arguments, computed by the caller before the study).

`backend/psse_job/run_record.py:29` [VERIFIED]: `MAX_CONTINGENCY_ROWS = 5000`. `run_record.py:391-395` [VERIFIED]: `if not _close(dispatched, min(applied, limit), 1e-6):` ... `expected = "dlr_rating" if applied <= limit else "voltage_stability"` ... `if row.get("limiting_factor") != expected:` (tie goes to `dlr_rating`). `run_record.py:453` [VERIFIED]: `want = limit - observed if kind == "voltage_low" else observed - limit` (the exceeded-by identity).

`backend/tests/psse_contract_test.py:35-40` [VERIFIED]:
```
_STDLIB_ALLOWED = frozenset([
    "__future__", "base64", "binascii", "collections", "contextlib", "datetime", "functools",
    "hashlib", "http", "json", "logging", "math", "numbers", "os", "re", "socket", "subprocess",
    "sys", "time", "typing", "urllib", "uuid",
])
_NEVER_IMPORTED = frozenset(["config", "supabase_store", "pandas", "numpy", "requests", "psspy"])
```
`tempfile`, `inspect`, `argparse` are NOT in this list, so a Phase 2 module that imports them fails the Phase 1 gate. Adding them is a deliberate edit to a Phase 1 test constant and must be an explicit plan step (not a silent change).

DDL rules the study output must satisfy [VERIFIED: docs/data-science/schema/psse_results_v1.sql:143-159]: thermal rows need `element_type = 'branch'` and `unit = 'MVA'`; voltage rows `element_type = 'bus'` and `unit = 'pu'`; `limit_value > 0`, `observed_value >= 0`, `exceeded_by > 0`; `non_convergence` rows have `element_id = contingency_id` and no limit/observed/exceeded/unit. `psse_dispatched_capacity.voltage_limit_mva` must be `> 0` (`:85`) and `psse_voltage_margin.voltage_limit_mva` likewise (`:116`).

## Package Legitimacy Audit

Not applicable: this phase installs no external package (standard library, pytest and psycopg already present and owner-approved in Phase 1). PyPSSE (NREL/NatLabRockies, BSD-3-Clause) was read as a source of real `psspy` call shapes only; it is not a dependency and must not be added (it imports pandas/pydantic/loguru and `helics`, none of which exist on the laptop interpreter). No `gsd-tools package-legitimacy` run was needed.

## The real `psspy` surface: what is certain and what is not

Evidence ranks used below: **M33** = text of the PSS/E 33.5 API manual, third-party copy [CITED: pdfcoffee.com/psse-9-pdf-free.html] (Siemens' own text, but an old version); **REF34** = a third-party "PSSPY Reference" PDF of 34-era calls [CITED: 3phaseee.com/static/docs/psspy.pdf]; **BLOG24** = a 2024 blog quoting the 35-era API [CITED: powersystemautomation.wordpress.com/2024/09/15/basic-automation-of-power-flow-activities-in-python/]; **PYPSSE** = open-source PyPSSE code [CITED: github.com/NatLabRockies/PyPSSE, formerly NREL/PyPSSE]; **FORUM** = psspy.org help forum (community). Version drift to 35/36 is unverified for everything cited only from M33/REF34.

| Call (Python syntax) | Returns | Evidence | Confidence |
|---|---|---|---|
| `ierr = psseinit(buses)` | ierr; M33: "No errors are currently defined"; `buses` "zero for default size level" | M33 12.13; BLOG24 `psspy.psseinit(buses = 150000)`; PYPSSE simulator.py:90 `ierr = psspy.psseinit(N_BUS)` | HIGH |
| `name,major,minor,modlvl,date,stat = psseversion()` | 6-tuple | M33 12.14 | MEDIUM (35/36 unverified) |
| `ierr = case(sfile)` | 0 ok; 1 blank; 2 error reading; 3 error opening; 4 prerequisites | M33 1.50 ("IERR = 3 error opening SFILE"); BLOG24 `ierr = psspy.case(<psse_case>)`; PYPSSE simulator.py:172 | HIGH |
| `ierr = read(_i, rawfile)` | ierr | BLOG24; PYPSSE simulator.py:174 `self.psse.read(0, str(...raw_file))` | MEDIUM (raw is not needed: Power Systems supplies a saved case) |
| `ierr = save(file)` | 0 ok; 1 blank; 2/3 file errors; 4 prerequisites | REF34 p.4; BLOG24 `psspy.save('tmp.sav')` | HIGH |
| `ierr = fnsl([options])` | ierr: 0 ok; 1 invalid OPTIONS; 2 "generators are converted"; 3 "buses in island without swing bus"; 4 "bus type and series element status inconsistencies"; 5 prerequisites | REF34 p.6 (options list of 8); PYPSSE static.py:25 `ierr = self.psse.fnsl()` (the no-argument form exists; that it means "program-setting defaults" is assumption A4) | HIGH |
| `ierr = fdns([options])` | same codes | REF34 p.5; BLOG24 `psspy.fdns([0,0,0,1,1,0,99,0])` | HIGH |
| `ival = solved()` | solution indicator, see table below | M33 7.142; BLOG24 `ival = psspy.solved()`; PYPSSE pcm.py:31-33 (`solved_flag == 0` is success), :54-55 (`> 0` is failure) | HIGH for 33.5; codes in 35/36 `[ASSUMED]` unchanged |
| `val = iterat()`, `mva = sysmsm()` | iterations of last solve; total system MVA mismatch | REF34 p.8; M33 7.155; FORUM question 6921 | HIGH |
| `ierr, [cols] = abrnint(sid, owner, ties, flag, entry, string)`; same for `abrnreal`, `abrnchar`, `abrncplx` | list of columns, one list per requested string | M33 8.12.2-8.12.5; BLOG24; FORUM answer: `ierr, [ibl,jbl] = psspy.abrnint(-1, flag=4, string=['FROMNUMBER','TONUMBER'])` | HIGH |
| `ierr, [cols] = abusint(sid, flag, string)`, `abusreal(...)` | list of columns | M33 8.3.2-8.3.3; BLOG24 `psspy.abusreal(-1, flag, string)` | HIGH |
| `ierr, rval = brndat(ibus,jbus,ickt,string)` | strings `'RATEA'`, `'RATEB'`, `'RATEC'`, `'RATE'`, `'LENGTH'`, `'CHARG'`...; ierr 1 bus not found, 2 branch not found, 3 invalid string, 4 invalid with multisection line identifier | M33 7.9 | HIGH |
| `ierr, ival = brnint(ibus,jbus,ickt,'STATUS')` | 0 out of service / 1 in service (via `brnstt` text) | M33 7.12 | HIGH |
| `ierr, rval = brnmsc(ibus,jbus,ickt,string)` | `'MVA'`, `'AMPS'`, `'PCTMVA'`, `'PCTRTA'`...; ierr 6 "Rating is zero; RVAL returned set to zero" | M33 7.13 | HIGH |
| `ierr, rval = busdat(ibus,string)` | `'BASE'` (kV), `'PU'`, `'NVLMLO'`, `'NVLMHI'`, `'EVLMLO'`, `'EVLMHI'` | M33 7.17 | HIGH |
| `ierr = branch_chng(i, j, ckt, intgar, realar)` (33.5) | REALAR(4..6) = RATEA, RATEB, RATEC; ierr 0 ok, >0 fatal (1 bus not found, 3 branch exists but is a two-winding transformer, 9 branch not found), -1 data warnings | M33 2.2-2.3 | HIGH for 33.5 |
| `ierr = branch_data_3(ibus, jbus, ckt, intgar, realar, ratings, namear)` (35 era) | `ratings` is a separate list of 12 values; RATE A/B/C moved out of `realar` ("List realar and ratings shall have a length of 12, not 15") | BLOG24; FORUM question 10559 | MEDIUM-HIGH |
| `ierr = branch_chng_3(i, j, ckt, intgar, realar, ratings, namear)` | acts only on an existing branch ("`branch_data_3` will add a branch if the branch does not exist") | FORUM question 10264 names `branch_chng_3` as "latest function"; FORUM question 3039 on add-versus-change; parameter list by analogy with `branch_data_3` | **UNVERIFIED** (signature `[ASSUMED]`) |
| `_i = getdefaultint()`, `_f = getdefaultreal()`, `_s = getdefaultchar()`; `from psspy import _i, _f, _s` | "no input" placeholders: passing `_f` leaves a value unchanged | M33 12.7-12.9; BLOG24; FORUM question 8382 | HIGH |
| `ierr,totals,moto = scal_2(sid, all, apiopt, status, scalval)` | `STATUS(2)=3` incremental powers; `SCALVAL(1)` load MW increment; `STATUS(4)=1` constant P/Q; `APIOPT=0` runs init and scaling in one call; ierr 1 invalid SID or subsystem not defined ... 8 prerequisites | M33 1.274; FORUM question 6830 (`_f` placeholders keep generation unchanged) | HIGH for 33.5 |
| `ierr = bsys(sid, usekv, basekv, numarea, areas, numbus, buses, numowner, owners, numzone, zones)` | defines subsystem `sid` (0 to 11) | REF34 p.9; BLOG24 | HIGH |
| `progress_output / prompt_output / report_output / alert_output (2, logfile, [0,0])` | redirect PSS/E text to a file | BLOG24; FORUM question 2241 (option 6 = no output; behaviour varies) | MEDIUM |
| `accc_with_dsp_3`, `accc_single_run_report_4`, `dfax_2`, `accc_parallel_2`, `n11_accc_parallel`, `pv_engine_6`, `qv_engine_4` | file-based AC contingency / PV / QV | names in M33 table of contents and REF34 (signatures for `dfax_2`, `accc_parallel_2`, `pv_engine_6`, `qv_engine_4` only) | names HIGH, current signatures **UNVERIFIED** |
| `pssexcel.accc(...)` | Excel report | FORUM question 8600: unreliable on 34.7 (COM/Excel) | LOW; do not use |
| `readrawversion(numnam=0, vernum='29', ifile=...)` | read an older-version raw file | FORUM question 119 | LOW; not needed |

### `solved()` codes (verbatim from M33 7.142)

> "IVAL = 0 Met convergence tolerance. IVAL = 1 Iteration limit exceeded. IVAL = 2 Blown up (only when non-divergent option disabled). IVAL = 3 Terminated by non-divergent option. IVAL = 4 Terminated by console interrupt. IVAL = 5 Singular Jacobian matrix or voltage of 0.0 detected. IVAL = 6 Inertial power flow dispatch error (INLF). IVAL = 7 OPF solution met convergence tolerance (NOPF). IVAL = 9 Solution not attempted."

The same entry opens with a warning that matters for design: "Use this API to check whether the last solution attempt reached tolerance. This is not a test for whether the working case is a solved case." So `solved()` after a `fnsl` that returned a non-zero `ierr` (island without swing bus, converted generators, prerequisites) describes an OLDER attempt and may read 0. **A load flow counts as converged only when `fnsl` returned `ierr == 0` AND `solved() == 0`.** Code 7 is >0 but belongs to the OPF; only 0 is success. The FORUM comment "blown up generally means solved returns 2, 1 might be still ok" (psspy.org question 3985) contradicts the manual and must not be followed: codes 1 and 3 are not converged.

### What the real `psspy` accepts that the fake must copy
- Keyword arguments use the manual's parameter names (`abrnint(-1, flag=4, string=[...])`, `branch_data_3(i=..., j=..., ckt='1', intgar1=0)` in FORUM question 3039, PYPSSE `load_chng_5(ibus=..., id=..., **values)` and `branch_data_3(ibus=..., jbus=..., ckt=..., **values)` at modes/abstract_mode.py:987). The adapter should call with keywords for every non-obvious argument so a misspelt name is a `TypeError` in the fake.
- Bulk reads return `(ierr, [column0, column1, ...])`, one list per requested string, aligned by branch/bus index (FORUM abrnint answer). Alignment across two separate calls with identical `(sid, owner, ties, flag, entry)` is `[ASSUMED]` (the manual says each column holds `BRNCHS` entries for those arguments); the probe checks it against single-branch `brndat` reads.
- `fnsl()` with no argument uses the program's solution settings (PYPSSE does this); passing `[options]` overrides them.

### Python and PSS/E versions (matters for the 3.7 syntax gate)
- PSS/E 35.3 and 35.4 ship a `PSSPY39` folder [CITED: psspy.org/psse-help-forum/question/9121 `pssepy_PATH=(r"""C:\Program Files\PTI\PSSE35\35.3\PSSPY39""")`; PYPSSE simulator.py:20 `sys.path.append('C:\\Program Files\\PTI\\PSSE35\\35.4\\PSSPY39\\')`]: Python 3.9 for those releases. PSS/E 34.7 is reported to bundle 3.7.3 [CITED: psspy.org question 11182 via search summary, not opened; LOW]. PSS/E 36.1 is reported to bundle 3.11 [CITED: psspy.org question 11182, "Python 3.11 comes with PSSE", release not stated; LOW]. The `-pyver` start-up flag selects the interpreter (same thread).
- Consequence: keep the Python 3.7 syntax floor (Phase 1 gate) and forbid 3.8+ features; the supported range is 3.7 to 3.11. Which one the laptop uses, and the psycopg pin for it, are Phase 3 facts.
- Importing `psspy` from an external interpreter uses `import psse35` then `import psspy` (the version package wires the path) or appends the `PSSPY39` folder to `sys.path` [CITED: psspy.org question 9121; PYPSSE simulator.py:84 `__import__(psse_version, fromlist=[""])` then :87 `import psspy`]. Importing happens in the Phase 3 launcher, outside `backend/psse_job/`.

## Architecture Patterns

### System Architecture Diagram

```
 Phase 3 launcher (outside psse_job, PSS/E's Python)          Config (laptop, NOT in the public repo)
   import psse35; import psspy; psspy.psseinit(0)              PSSE_MAPPING_PATH -> city_branch_mapping.json
   case_sha256 / mapping_sha256 from the file bytes            PSSE_CASE_PATH    -> Power Systems' .sav
              |                                                         |
              v                                                         v
        job.run_once(fetch, study, connect, case_id, case_sha256, mapping_sha256)   [Phase 1, unchanged]
              |  1. ratings read -> Selection (static today)
              |  2. study(selection, context)   <-- Phase 2
              v
  study.make_study(psspy_obj, case_path, mapping, settings)  ->  study(selection, context)
     |
     |  api = PsseApi(psspy_obj)   (only module that names psspy functions; SURFACE table)
     |
     |-- load_case(case_path) ------------------- ierr != 0 --> StudyFailed("load_case")
     |-- index branches/buses (bulk abrn*/abus* reads)
     |-- mapping check: every mapped branch present, in service, one base kV per city
     |                                          --> StudyFailed("mapping")  (nothing written to the case yet)
     |-- apply ratings: MVA = units.circuit_mva(selection amps, count, base kV)
     |       write RATEn, read back with brndat   --> StudyFailed("apply_ratings")
     |-- base solve: fnsl ierr==0 and solved()==0  --> StudyFailed("load_flow")   (STU-01)
     |-- save base to temp .sav (never the case path)
     |-- N-1 loop: for each outage: trip, solve, evaluate violations, reload base   (STU-02)
     |       non-convergent outage -> non_convergence row; infrastructure problem --> StudyFailed("contingency")
     |-- per city: transfer search (reload, scale sink load, solve, measure)        (STU-03)
     |       --> StudyFailed("voltage_margin") when the transfer does not load the mapped branches
     |-- dispatch rows: min(applied MVA, voltage limit MVA), amps, MW, limiting factor  (STU-04)
     v
  StudyResults(dispatch x4, margins x4, contingencies xN, n_contingencies, rate_set, psse_version)
     |
     v   run_record.validate_results -> writer.write_run (one transaction)   [Phase 1, unchanged]
```

### Recommended Project Structure
```
backend/psse_job/
  mapping.py        # load_mapping(path) -> (Mapping, sha256); validation; MappingError; placeholder guard
  settings.py       # Settings defaults + validation of the optional "study" overrides (limits, steps, caps)
  psse_api.py       # SURFACE table, PsseApi(psspy_obj) adapter, SolveResult, BranchTable/BusTable
  violations.py     # pure: evaluate thermal and voltage violations from tables -> contingency rows
  margin.py         # pure: find_transfer_limit(evaluate, step_mw, max_mw, tol_mw, stop_flow_mva)
  dispatch.py       # pure: build_dispatch_row(...) satisfying every validate_results identity
  study.py          # make_study(...) -> study(selection, context); the orchestration over psse_api
  probe.py          # laptop probe (Phase 3 runs it): SURFACE vs real psspy signatures, one read-only pass
backend/tests/
  psse_fake_psspy.py     # helper (not collected): FakePsspy + placeholder case builder + scripted solvers
  psse_mapping_test.py   # IN-02 configuration side
  psse_api_test.py       # adapter, SURFACE drift, solve classification, case-path guard
  psse_study_test.py     # IN-02/IN-03/STU-01..04 against the fake, every output through validate_results
  psse_study_job_test.py # TST-01 write-back: fake psspy -> run_once -> local Postgres, incl. failed runs
docs/data-science/decisions/
  psse_study_definitions.md   # the stated definitions (conversion, limits, margin, N-1) + open questions
docs/data-science/schema/
  psse_mapping_example.json   # clearly marked PLACEHOLDER (fake bus numbers)
```
Do NOT edit `docs/data-science/schema/psse_results_v1.md` or the DDL for study definitions; the study definitions go in the new decision note (the spec and DDL are pinned by tests and handed to Phase 6).

### Pattern 1: Injected `psspy` behind one adapter (D-07)
**What:** `PsseApi.__init__(self, psspy_module)` stores the object; no module in `psse_job` ever executes `import psspy`. `study.make_study(psspy_module, ...)` builds the adapter. The Phase 3 launcher does `import psse35; import psspy` and passes the module. Tests pass `FakePsspy()`.
**Why it satisfies the gate:** `_NEVER_IMPORTED` forbids the import statement, not an object that happens to be `psspy`; `test_importing_psse_job_loads_no_heavy_module` imports every module in a subprocess with no `psspy` present, which now also proves no module needs it at import time.
**SURFACE table (single source of truth):** a module-level tuple `SURFACE` of `(name, parameter_names, evidence, confidence)` rows, one per `psspy` function the adapter calls. The adapter's private `_call(name, **kwargs)` refuses any name not in `SURFACE` and records each call (`self.calls`). Three tests and one laptop probe hang off this table (see "Test strategy").

### Pattern 2: Pure cores, thin PSS/E layer (D-07)
**What:** everything that can be a pure function over plain Python data is one: mapping validation, unit conversion (already `units.py`), violation evaluation, the transfer search (takes an `evaluate(transfer_mw)` callable), dispatch-row construction. They are unit-tested with no fake at all. Only `study.py` and `psse_api.py` touch the adapter.
**When to use:** always; it keeps the fake small (it need only be right about the call shapes and return shapes, not about physics, except in the one margin test).

### Pattern 3: Reload, never undo (D-14)
**What:** after loading the case and applying ratings, save the solved base once to a temp file; before each outage and each transfer evaluation, `case(temp)` to restore it. Never "un-trip" a branch and re-solve.
**Why:** a blown-up or non-converged working case holds a meaningless state (`solved()` 2/3/5); restoring by reload is exact and cheap to reason about. A forum thread uses the same pattern (save a temp file before `fnsl`, reload if `solved()` reports failure) [CITED: psspy.org question 2441 via search summary; LOW]. **Never save onto the case path:** the adapter's `save_case(path)` raises if `path` resolves to the original case file; temp files live in a per-run `tempfile.mkdtemp()` removed in `finally`.

### Pattern 4: Fail closed, never fabricate
**What:** any condition that stops a number from being measured (missing branch, rating write not read back, load flow not converged, no contingency selected, the transfer does not load the mapped branch, a city's margin not computable) raises `StudyFailed(stage, message)`. The DDL has no "not computed" value (`margin_mw` and `voltage_limit_mva` are NOT NULL; four dispatch and four margin rows per non-failed run), so a partial city set is not representable: one city failing fails the run. This is intended (WB-02) and is flagged as a consequence in "Roadmap honesty".

## Modelling decisions (answers to the research questions)

### Mapping configuration (IN-02) - D-08
- **Format:** one JSON file (stdlib `json`; YAML and TOML are unavailable, see Alternatives). `mapping_sha256` is the sha256 of the file bytes (`run_record.file_sha256`, or hash the bytes that were parsed so hash and content cannot differ). One file with a required `cities` section (Power Systems' branch choices) and an optional `study` section (job parameters, defaults in code), so the single recorded hash covers every parameter that shaped the result.
- **Shape (validated by hand-written code; unknown keys rejected):**
  ```json
  {
    "schema_version": 1,
    "placeholder": true,
    "note": "PLACEHOLDER - not Power Systems data",
    "cities": {
      "AUSTIN": {"branches": [{"from_bus": 90001, "to_bus": 90002, "ckt": "1"}], "sink_buses": [90002]},
      "CORPUS_CHRISTI": {"branches": [{"from_bus": 90011, "to_bus": 90012, "ckt": "1"}], "sink_buses": [90012]},
      "MIDLAND": {"branches": [{"from_bus": 90021, "to_bus": 90022, "ckt": "1"}], "sink_buses": [90022]},
      "EL_PASO": {"branches": [{"from_bus": 90031, "to_bus": 90032, "ckt": "1"}], "sink_buses": [90032]}
    },
    "study": {}
  }
  ```
  The four city keys must equal `constants.CITIES` exactly; each city needs at least one branch; bus numbers are positive integers; `ckt` is 1 to 2 printable characters (PSS/E rejects longer identifiers: M33 BRANCH_CHNG "IERR = 2 circuit identifier is more than two characters"); no branch may appear under two cities (the DDL has one `city` per violation row); a city lists its parallel circuits as separate entries; `sink_buses` defaults to the `to_bus` of the first branch if omitted; the file size is capped (for example 64 KiB) before parsing.
- **Private, not committed:** Power Systems' bus numbers and branch identifiers are grid element identifiers. The repository is public (OD-6) and the result tables are private for exactly that reason [VERIFIED: docs/data-science/schema/psse_results_v1.md:25: "The tables are private (D-03): `anon` and `authenticated` have no access, because the rows carry grid element identifiers from Power Systems' case while this repository and the `city_rating` history are public (OD-6)."]. So the real mapping and case live on the laptop (paths from `PSSE_MAPPING_PATH`, `PSSE_CASE_PATH`); the repo carries only `psse_mapping_example.json` with obviously fake numbers (9xxxx) and a `"placeholder": true` marker. Add a `.gitignore` rule for a local directory (for example `/psse_local/`) so a real file dropped there cannot be committed.
- **Placeholder guard:** `load_mapping(path, allow_placeholder=False)`; with a placeholder file and `allow_placeholder=False` it raises `MappingError` (stage `mapping`). Tests pass `allow_placeholder=True`. The launcher in Phase 3 may pass `True` only behind an explicit flag for a plumbing smoke run against PSS/E's sample case; the sample case shipped with PSS/E is `savnw.sav` (the 23-bus case used throughout the API reference examples) [CITED: REF34 examples `psspy.case('savnw.sav')`; whether it is installed on the laptop `[ASSUMED]`].
- **Missing branch (the IN-02 failure):** build the case index first (bulk reads), then check every mapped branch before anything is written to the case. Collect all problems (missing, out of service, endpoints with different base kV, a city whose branches have different base kV, a multisection-line identifier) into one message; raise `StudyFailed("mapping", message)`. Because mapping is checked before `apply_ratings`, `fnsl` and every other write, "no study results written" holds by construction, and the run record shows `failed_stage = mapping`. A mapping file that cannot be read or parsed is the same failure; the launcher then passes `mapping_sha256=None` (the DDL allows NULL: "the mapping was not loaded").
- **Orientation:** look up `(from, to, ckt)` exactly as listed; also accept the reversed orientation by normalising to the case's orientation (whether `branch_chng` accepts reversed ends is `[ASSUMED]` unknown, so the adapter always calls with the case's own orientation).
- **Branch kinds:** `branch_chng`-family calls act only on non-transformer branches (M33: "IERR = 3 branch exists but it is a two-winding transformer"). The case index reads non-transformer branches (`flag=2`); a mapped transformer or multisection line (`brndat` "IERR = 4 'BRNDAT' invalid with multisection line identifier") is a mapping failure with a clear message.

### Unit conversion and which rating field (IN-03) - D-09
- **Conversion (stated, already implemented):** `circuit MVA = sqrt(3) x kV x circuit amps / 1000`, with circuit amps = amps per conductor x subconductors, from `psse_job/units.py` (D-06). Phase 2 supplies the kV.
- **Which kV:** the base kV of the branch's from-bus read from the case, `busdat(from_bus, 'BASE')` [CITED: M33 7.17 "'BASE' Bus base voltage, in kV"]. For a line both ends share a base kV; if the two ends differ the element is not a line (a transformer or a data error) and the mapping fails. All mapped branches of one city must share one base kV (the DDL stores one `line_voltage_kv` per city row; the spec's own assumption at `psse_results_v1.md:196` says the same) or the mapping fails; this makes Open Question 3 of the spec answerable on first contact with the case.
- **PSS/E side:** a branch rating is an MVA value (PTI raw format: "RATEA is the MVA rating A, and RATEB and RATEC are the higher MVA ratings" [CITED: cialab.ece.uw.edu/research/pstca/formats/pti.txt]); the practitioner formula is "Rate = In * Vbase * sqrt(3) ... a 500 kV line rated 1.5 kA has the rating 1299 MVA" [CITED: psspy.org question 7299]. So the value to write is exactly `units.circuit_mva(...)`, with no power factor. The "percent loading units" program setting only changes how PCT quantities are computed ("according to the appropriate percent loading units program option setting", M33 `PCTCPA`), not the number to write; the recommended thermal check names its basis explicitly (below), so it does not depend on that setting.
- **Which rating set (D-09):** DLR is an ambient-adjusted continuous ampacity, the analogue of Rate A. ERCOT practice, from search summaries of ERCOT planning documents not opened in full: Rate A is the continuous ("Normal") rating used for base-case checks, Rate B the two-hour ("Emergency") rating used for N-1 [CITED: ercot.com/files/docs/2014/02/03/031pgrr_16_calpine_comments_020314.doc, via search summary; MEDIUM-LOW]; planners expect Rate C >= Rate B >= Rate A. Recommendation: `settings.rate_sets = ["RATEA"]` by default; the DLR MVA is written to every listed set (so a deployment can list `["RATEA", "RATEB"]` if Power Systems decides N-1 limits must follow the DLR value); the FIRST listed set is the limit used for every thermal check; `psse_run.rate_set` records the list joined with `+`. Writing only RATEA while checking N-1 against an untouched RATEB would make the DLR value irrelevant to N-1, which is why this is Open Question 1 for Power Systems.
- **Per-branch versus per-circuit:** the rating is per circuit: `city_rating` is per conductor, so amps x subconductors is the per-circuit current and the MVA is per circuit. When a city maps to several parallel circuits each circuit receives the same per-circuit MVA (not divided); when it maps to series sections of one circuit, the same value goes on each section. The mapping lists branches, not a topology claim.
- **Never write zero:** `RATEA = 0` means "no limit" [CITED: psspy.org question 8490 via search summary: "RATEA of zero means no current limit"]; `units` already rejects non-positive amps and kV, and the adapter re-checks the MVA is finite and `> 0` before the call.
- **Read back (the check that makes IN-03 "tested" on the real engine too):** after each write, `brndat(i, j, ckt, 'RATEA')` (the set that was written) must equal the written MVA to 1e-6 relative; otherwise `StudyFailed("apply_ratings", ...)`. Also record the rating the case had before (`rate_before_mva`) in `psse_dispatched_capacity.details`: the static rating in this project's configuration may differ from Power Systems' own value, and overwriting it is a decision Power Systems should see (Open Question 5).
- **Error tolerance on the write call:** M33 `branch_chng` returns `ierr = -1` for data warnings (for example "branch reactance is 0.0", "invalid owner number") and `> 0` for fatal errors. Treat `ierr > 0` as failure and `ierr <= 0` as acceptable, relying on the read-back for the rating itself.

### Convergence detection and mismatch (STU-01) - D-10
- **Rule:** call `fnsl()`; converged only if `ierr == 0` and `solved() == 0` (see the verbatim table and warning above). The adapter returns `SolveResult(converged, ierr, solved_code, meaning, iterations, mismatch_mva)`; `meaning` comes from the code table (an unknown code reads "unknown solved code N"). For the base case a non-converged result raises `StudyFailed("load_flow", "load flow did not converge: ierr=<n> solved=<code> (<meaning>)")`. For an outage or a transfer evaluation it is data (a `non_convergence` row or the search's stopping point).
- **Mismatch tolerance:** `solved() == 0` already means PSS/E met its own Newton tolerance (TOLN; the M33 ACCC text says its `TOL` defaults to "Newton solution convergence tolerance, TOLN"). Do not override TOLN through the API unless Power Systems asks (`solution_parameters_4` is the current routine per the M33 "obsolete" notes; its 35 signature is unverified). As a second belt, read `sysmsm()` and `iterat()` after every solve, record them in `details`, and treat `sysmsm() > max_mismatch_mva` (default 1.0 MVA, `[ASSUMED]`) on the BASE case as `load_flow` failure: it catches a case saved with a loose tolerance.
- **Plausibility guard (optional, recommended):** a converged solution with a monitored bus below, say, 0.5 pu is a collapsed solution; treat it as non-converged for the margin and N-1 purposes (`[ASSUMED]` threshold).
- **Solution method and options:** `fnsl()` with no argument (program settings) by default; the optional `settings.solve_options` (8 integers) is passed through when set. The "non-divergent solution" option (OPTIONS(8)) turns "blown up" into "terminated by non-divergent option": both are non-zero, so both fail the rule.
- **Prerequisites that look like failures:** `fnsl` ierr 2 ("generators are converted") means the saved case was left in the converted state; the failure text must say so, because the remedy is Power Systems' case, not the job.

### Thermal limit for violations (STU-02) - D-11
- **Quantity:** the comparison should follow what the rating means. DLR ratings are ampacities, so conductor heating follows current, and an MVA flow understates current loading when voltage is low (at 0.90 pu, 10 percent more current for the same MVA). PSS/E provides both bases in bulk: current basis `'MAXPCTRATEA'` ("Larger of percent from/to bus current of rating set A") and MVA basis `'MXPCTMVARATA'` ("Larger of percent from/to bus MVA of rating set A") [CITED: M33 aBrnReal 8.12.3]; the B and C variants exist. Recommendation: `settings.thermal_basis = "current"` (default) or `"mva"`; the adapter reads `RATEn` and the chosen percent column for all in-service non-transformer branches in one `abrnreal` call.
- **Row values:** `limit_value = rate_mva x thermal_limit_pct / 100`; `observed_value = pct / 100 x rate_mva` (current-expressed-as-MVA when the basis is current); `exceeded_by = observed - limit`; `unit = "MVA"`; `limit_value > 0` always because a branch whose rating is 0 ("no limit") is skipped. `thermal_limit_pct` default 100.0 (configuration, `[ASSUMED]`). Put `{"basis": "current", "pct_of_rating": ...}` in `details`.
- **For a mapped branch** the rating in the case is the DLR value just written, so its limit is the applied rating; this is what makes the N-1 result about the DLR rating (STU-02).

### Voltage limits (STU-02) - D-11
- Configuration, not code: `settings.voltage = {"contingency_low_pu": 0.90, "contingency_high_pu": 1.05, "base_low_pu": 0.95, "base_high_pu": 1.05, "min_monitor_kv": 100.0}`. Defaults follow ERCOT's Planning Guide 4.1.1.4 as restated in a 2015 ERCOT PGRR comment document: transmission buses above 100 kV within 0.95 to 1.05 pu before any contingency and 0.90 to 1.05 pu after P1-P7 events (the same sources also cite an 8 percent post-contingency voltage deviation rule at load-serving buses, deliberately not implemented here) [CITED: ercot.com/files/docs/2015/03/17/041PGRR_11_ROS_Report_031215.doc, via search summary, not opened; MEDIUM-LOW]. Current Planning Guide text must be confirmed by Power Systems.
- The case also carries per-bus limits (`'NVLMLO'`, `'NVLMHI'`, `'EVLMLO'`, `'EVLMHI'` via `abusreal`, M33 8.3.3). Offer `settings.voltage.source = "config"` (default) or `"case"`; with `"case"` the emergency limits apply after an outage. Default config because case limits are often left at PSS/E defaults.
- Violation rows: `voltage_low` when `pu < low` (`exceeded_by = limit - observed`), `voltage_high` when `pu > high` (`exceeded_by = observed - limit`), `unit = "pu"`, `element_type = "bus"`, `element_id` = the bus number as text. Skip buses with type code 4 or greater (isolated; `abusint 'TYPE'`, M33 8.3.2) and buses below `min_monitor_kv`.

### N-1 contingency design (STU-02) - D-12
- **Method:** a manual single-branch outage loop (not ACCC): for each selected outage, `branch_chng_3(..., intgar1=0)` sets the status to 0 (the 33.5 form is `intgar[0] = ST`; FORUM question 3039 shows `psspy.branch_chng(12345,34567,'1',0)`), `fnsl`, classify with the SolveResult, bulk-read bus voltages and branch loading, evaluate, then reload the saved base. This is slower than ACCC but needs only primitives that a fake can serve and a laptop can confirm in minutes.
- **Scope (D-12):** the outage set is configuration with a neighbourhood default: every mapped branch of every city, plus every in-service non-transformer branch within `contingency.hops` (default 2) branches of a mapped branch endpoint, found by breadth-first search over the branch table in pure Python; `contingency.extra` adds explicit outages; `contingency.scope = "all"` allows every non-transformer branch for a small case. Monitored elements are the branches and buses in the same neighbourhood (a rule that keeps row volume bounded; the existing `MAX_CONTINGENCY_ROWS = 5000` check stays the backstop).
- **A full-system AC contingency solution is not what this does.** Transformer, generator and multi-element outages are not screened; `psse_run.n_contingencies` counts branch outages only. State this in `psse_study_definitions.md`. Upgrading to ACCC is a Phase 3+ option behind the same `study` seam.
- **Row rules:** `contingency_id = "%d-%d-%s" % (from, to, ckt)` (the spec example is "the tripped branch as from-to-circuit"); `element_id` for a branch is the same format; a non-converged outage writes one `non_convergence` row (`element_type = "contingency"`, `element_id = contingency_id`, no values, no unit) and counts as a contingency with results; the outaged branch itself is not evaluated. `city` is set when the element is one of a city's mapped branches. A violation already present in the base case is still written, with `details = {"in_base_case": true}`, so a reader can filter new from pre-existing (the DDL has no base-case slot; see Roadmap honesty).
- **Infrastructure failures are not data:** zero selected outages (a "screening" that screened nothing), more outages than `contingency.max` (default 200, `[ASSUMED]`), more than `MAX_CONTINGENCY_ROWS` rows, or the run-time budget exceeded raise `StudyFailed("contingency", ...)`. Never truncate silently; a truncated set must not look complete.
- **Run-time budget:** `settings.max_runtime_seconds` (default 1500, `[ASSUMED]`) is checked between solves with an injected monotonic clock; a single `fnsl` cannot be interrupted, so Phase 3 still needs a Task Scheduler time limit and no-overlap rule (SCH-01).

### Voltage-stability margin (STU-03) - D-13
- **Definition (feasible, testable, laptop-hourly):** a PV-style transfer margin from plain load flows. For each city: take the sink buses (`sink_buses`), and for transfer step `d` MW: reload the base case, increase the sink load by `d` MW at constant P/Q ratio with one `scal_2` call (a subsystem of the sink buses defined with `bsys`; `STATUS = [_i, 3, 0, 1, 0]` incremental, `SCALVAL = [d, 0, 0, 0, 0, 0, 0]`, the combined `APIOPT = 0` form), `fnsl`, and measure. Generation is untouched so the swing bus absorbs the increase; this is a documented simplification (the source of the transfer is Open Question 4).
- **Stopping rule (bisection after a coarse walk):** step up by `transfer.step_mw` (default 25.0) until the first of: not converged (`ierr != 0` or `solved() != 0`); the minimum monitored bus voltage falls below `voltage.contingency_low_pu`; `transfer.max_mw` reached; or the largest per-circuit flow on the mapped branches reaches the applied rating (`stop_flow_mva = applied_mva`, nothing more to learn: the DLR rating binds). Then bisect between the last good and first bad step to `transfer.tolerance_mw` (default 1.0). Each evaluation is independent (reload, scale, solve), so a blown-up case never contaminates the next.
- **Reported quantities:** `base_transfer_mw` = sum of active power at the from end of the city's mapped branches at the base case (`abrnreal 'P'`, M33: "Active power flow at from bus end", MW); `limit_transfer_mw` = the same sum at the last good step; `margin_mw = limit - base` (>= 0; 0 with `details.bounded_by = "base_case"` when the base case already breaks the voltage criterion); `margin_pct = margin_mw / base x 100` or null when base is below 0.1 MW; `critical_bus`/`min_voltage_pu` from the last good step; `method = "pv_curve"` (the DDL's own example label); `details = {"bounded_by": "non_convergence" | "voltage_criterion" | "dlr_rating" | "max_transfer" | "base_case", "step_mw": ..., "evaluations": n, "sink_buses": [...], "criterion_pu": ...}`.
- **Lower-bound semantics (state it):** when the search stops because the DLR rating binds or `max_transfer` was reached, the margin is "at least this much", not the nose. That is exactly what dispatch needs (the lower of the two), and it keeps the number of solves bounded.
- **What the voltage limit means (D-13):** `voltage_limit_mva` is the largest per-circuit apparent flow (`abrnreal 'MAXMVA'`, M33: "|P + j Q| at from bus or to bus end, whichever is larger") over the city's mapped branches at the last good point. The DDL requires it `> 0` and in per-circuit MVA, the same unit as `applied_mva`; the margin row and the dispatch row carry the same value (`validate_results` checks they agree).
- **Guard against a meaningless transfer:** if the mapped branches' P and flow do not rise by at least a configured fraction (default 1 percent of `step_mw`) when the sink load is increased by one step, the transfer does not load the mapped branches (wrong sink, no scalable load, parallel path dominates). Raise `StudyFailed("voltage_margin", ...)`; never report the flat flow as a limit.
- **PSS/E PV/QV engines (deferred):** `pv_engine_6` takes OPTIONS(25), VALUES(8), LABELS, a `.dfx` file and writes a `.pv` results file; `qv_engine_4` is the reactive analogue (REF34 pp.16-22). They require DFAX inputs and (assumed) a licensed PV/QV module, so they cannot be exercised with a fake and are not in Phase 2. The `method` label stays free text so an engine-based margin can replace the native one later without a schema change.

### Dispatched capacity (STU-04) - D-13
- Pure function `build_dispatch_row(choice, line_voltage_kv, voltage_limit_mva, power_factor, details)` using exactly `psse_fakes.fake_results`' formulas (already proven against `validate_results` and the DDL): `applied_amps_circuit = units.circuit_amps(...)`, `applied_mva = units.circuit_mva(...)`, `dispatched_mva = min(applied_mva, voltage_limit_mva)`, `dispatched_amps_circuit = units.mva_to_circuit_amps(dispatched_mva, kv)`, `dispatched_amps_per_conductor = dispatched_amps_circuit / subconductors`, `dispatched_mw = dispatched_mva x power_factor`, `limiting_factor = "dlr_rating" if applied_mva <= voltage_limit_mva else "voltage_stability"` (a tie goes to the DLR rating). Fields from the selection (`rating_source`, `fallback_reason`, amps, subconductors, the `city_rating` link only when the source is `city_rating`) are copied from `selection.choices[city]`, never recomputed.
- **Power factor (D-13):** constant 0.95, the project's own `POWER_FACTOR`, so `dispatched_mw` stays comparable in convention with the stored `rating_mw` (the Phase 1 research decided "same convention as `rating_mw`; the factor is stored"). Add `POWER_FACTOR_DEFAULT = 0.95` to `psse_job/constants.py` with a drift test against `config.POWER_FACTOR` (same D-05 pattern as the other copies); do not import `config`. A measured branch power factor is a possible later refinement, not needed for the DDL (any value in (0, 1] satisfies `dispatched_mw = dispatched_mva x power_factor`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Power flow, outage solution | Your own load-flow or DC approximation in the job | `psspy.fnsl` through the adapter | The solver is the product; a home-made one would "prove" nothing about the grid |
| AC contingency file formats | A writer for `.sub/.mon/.con/.dfx` or a parser for `.acc` | Manual outage loop now; ACCC later by Power Systems | File formats are GUI-produced and version-sensitive (FORUM question 1245) |
| Excel reporting | `pssexcel` calls | Direct `abrn*`/`abus*` reads | Needs Excel/COM; reported unreliable on 34.7 |
| Unit conversion | A second amps-to-MVA formula | `psse_job.units.circuit_mva`, `circuit_amps`, `mva_to_circuit_amps` | Already tested; D-06 |
| Row correctness | Ad-hoc checks of dispatch/margin/contingency rows | `run_record.validate_results` as the test oracle on every study output | Encodes every DDL identity |
| File hashing | New sha256 code | `run_record.file_sha256` | Existing and tested |
| Secret/error redaction | New redaction | `redaction.redact` (done inside `run_once` and `failure_from_exception`) | Phase 1 |
| YAML/TOML parsing | PyYAML or `tomllib` | `json` | Not available on PSS/E's interpreter or forbidden by the 3.7 gate |
| Importing `psspy` in tests | A `sys.modules['psspy']` shim | Inject the fake object | The import gate's own planted case `def f(): import psspy` must stay a violation |
| Case copies | `shutil.copy` of Power Systems' file, or `psspy.save` onto it | `psspy.save` to a temp path only; refuse the case path | The case file is the customer's artefact |

**Key insight:** the value of this phase is in the seam (adapter, SURFACE table, pure cores, honest failure), not in new physics. Every place where a number could be invented (a margin the engine did not produce, a rating that was not read back, a truncated N-1) is a place the design raises `StudyFailed` instead.

## Common Pitfalls

### Pitfall 1: Trusting `solved()` after a failed `fnsl`
**What goes wrong:** `fnsl` returns `ierr = 3` (island without swing bus) or `2` (generators converted) without solving; `solved()` still reports the previous attempt, possibly 0; the run looks converged. **Avoid:** converged means `ierr == 0 and solved() == 0`, both checked in the adapter and unit-tested with a fake that returns `ierr = 2` while `solved()` reads 0. **Warning sign:** a "converged" result with an old iteration count.

### Pitfall 2: Following the forum reading of `solved()` codes
**What goes wrong:** "1 might be still ok" lets an iteration-limit result through. **Avoid:** only 0 is success (manual table).

### Pitfall 3: Continuing from a blown-up working case
**What goes wrong:** the next outage or transfer step starts from a garbage state. **Avoid:** reload the saved base before every evaluation (Pattern 3).

### Pitfall 4: Overwriting Power Systems' case file
**What goes wrong:** `psspy.save(case_path)` after applying DLR ratings silently rewrites the customer's file. **Avoid:** adapter refuses a save onto the case path (compare resolved real paths); temp directory per run; test that no `save` call ever targets the case path.

### Pitfall 5: Writing a zero or unit-confused rating
**What goes wrong:** `RATEA = 0` removes the limit; writing per-conductor amps or `rating_mw` (1036 for Austin instead of 2181.1 MVA) understates the rating 2.1x. **Avoid:** MVA only from `units.circuit_mva`; positive/finite check before the call; read-back after; the existing `psse_contract_test` gate that bans the `rating_mw` string constant stays green.

### Pitfall 6: Mapped branch present but out of service, a transformer, or a multisection line
**What goes wrong:** ratings written to something the flow does not use; `brndat` rejects multisection identifiers. **Avoid:** mapping check covers status (`brnint 'STATUS'`/`abrnint 'STATUS'`), kind (non-transformer flag) and identifier shape; any miss is a `mapping` failure.

### Pitfall 7: Circuit identifier padding and orientation
**What goes wrong:** `abrnchar 'ID'` returns two-character identifiers (M33: "'ID' Circuit identifier (2 characters)"), so `'1'` and `'1 '` do not compare equal. **Avoid:** strip both sides for matching and pass the stripped identifier back; normalise endpoint orientation to the case's. Whether PSS/E ever returns leading-space identifiers is `[ASSUMED]`; the probe prints the raw representation of every mapped identifier.

### Pitfall 8: Bulk read columns misaligned
**What goes wrong:** `abrnint` and `abrnreal` called separately return rows in different orders. **Avoid:** identical `(sid, owner, ties, flag, entry)` for every bulk call, assert equal lengths, and check three sample branches against single-element `brndat`/`brnint` reads in the Phase 3 probe.

### Pitfall 9: Base-case violations flooding the N-1 result
**What goes wrong:** every pre-existing overload repeats once per outage and hits the 5000-row cap. **Avoid:** monitored set limited to the neighbourhood, `details.in_base_case`, and the cap raising `StudyFailed("contingency", ...)` rather than truncating. If Power Systems' case already has base overloads in the neighbourhood, expect `in_base_case` rows; the decision whether to suppress them is theirs.

### Pitfall 10: PV search that never loads the mapped branch
**What goes wrong:** the sink is not downstream of the mapped branch, the load is fixed (not scalable), or a parallel path carries the increase; the "limit" is just the flat base flow. **Avoid:** the flow-must-rise guard (STU-03), plus a test with a sink on the wrong side.

### Pitfall 11: Low-voltage solution accepted
**What goes wrong:** Newton converges to a collapsed low-voltage solution on the far side of the nose. **Avoid:** voltage criterion stops the search before the nose; plausibility guard.

### Pitfall 12: Process-global PSS/E state
**What goes wrong:** `psspy` holds one working case per process; two runs in one process (or a leftover subsystem `sid`) leak state. **Avoid:** one study per process (the hourly job is one process), define subsystems with a fixed `sid` and redefine each time, never reuse an adapter across runs. `[ASSUMED]` that `psspy` state is process-global (consistent with all examples).

### Pitfall 13: NaN/datetimes in `details`
**What goes wrong:** the writer does `json.dumps(value, allow_nan=False)` on JSON columns [VERIFIED: backend/psse_job/writer.py:107], so a `float('nan')` or a `datetime` in `details` makes the whole write fail after a long study. **Avoid:** sanitise `details` (`run_record.finite` for floats, ISO strings for times) and unit-test it.

### Pitfall 14: Real mapping or case committed
**What goes wrong:** grid element identifiers leak into a public repo. **Avoid:** see Mapping; `.gitignore` rule, placeholder-only example, a test that the example is marked `placeholder` and uses only the fake 9xxxx range.

### Pitfall 15: Fake that accepts anything
**What goes wrong:** a permissive fake (`**kwargs`) hides wrong parameter names that the real `psspy` would reject. **Avoid:** the fake's methods take the manual's exact parameter names, and a test compares their `inspect.signature` to the `SURFACE` table.

## Code Examples

### Convergence classification (the rule, in the adapter)
```python
# Source: derived from M33 7.142 SOLVED table (quoted above) and REF34 fnsl error codes.
SOLVED_MEANING = {
    0: "met convergence tolerance", 1: "iteration limit exceeded",
    2: "blown up (non-divergent option disabled)", 3: "terminated by non-divergent option",
    4: "terminated by console interrupt", 5: "singular Jacobian matrix or voltage of 0.0 detected",
    6: "inertial power flow dispatch error (INLF)", 7: "OPF solution met convergence tolerance (NOPF)",
    9: "solution not attempted",
}

def solve(self, options=None):
    ierr = self._call("fnsl") if options is None else self._call("fnsl", options=options)
    code = self._call("solved")           # only meaningful when ierr == 0
    converged = (ierr == 0 and code == 0)
    return SolveResult(converged, ierr, code,
                       SOLVED_MEANING.get(code, "unknown solved code %s" % code))
```

### Mapping check before anything is written (IN-02)
```python
# Source: design; stage name is in constants.FAILED_STAGES ("mapping").
problems = []
for city in constants.CITIES:
    kv_values = set()
    for b in mapping.cities[city].branches:
        found = table.find(b.from_bus, b.to_bus, b.ckt)      # normalised orientation
        if found is None:
            problems.append("%s: branch %d-%d-%s is not in the case" % (city, b.from_bus, b.to_bus, b.ckt))
        elif not found.in_service:
            problems.append("%s: branch %s is out of service" % (city, found.key))
        else:
            kv_values.add(round(api.base_kv(found.from_bus), 6))
    if len(kv_values) > 1:
        problems.append("%s: mapped branches have different base kV %s" % (city, sorted(kv_values)))
if problems:
    raise contract.StudyFailed("mapping", "; ".join(problems))
```

### Rating write with read-back (IN-03)
```python
# Source: units.circuit_mva (Phase 1) and M33 BRNDAT 'RATEA'; the write call shape is UNVERIFIED for 35.
mva = units.circuit_mva(choice.amps_per_conductor, choice.subconductors_per_phase, kv)
for rate_set in settings.rate_sets:                       # default ["RATEA"]
    api.set_rate(branch, rate_set, mva)                   # adapter: branch_chng_3(..., ratings=[mva, _f x 11])
    written = api.read_rate(branch, rate_set)             # brndat(i, j, ckt, 'RATEA')
    if abs(written - mva) > 1e-6 * mva:
        raise contract.StudyFailed("apply_ratings", "%s %s read back %r, wrote %r"
                                   % (branch.key, rate_set, written, mva))
```

### Transfer search as a pure function (STU-03)
```python
# Source: design. `evaluate(d)` reloads the base, scales the sink by d MW, solves and returns
# Point(ok, min_v, critical_bus, p_mapped_mw, max_flow_mva). ok means converged AND voltage criterion met.
def find_transfer_limit(evaluate, step_mw, max_mw, tol_mw, stop_flow_mva):
    base = evaluate(0.0)
    if not base.ok:
        return Limit(base, base, "base_case", 1)
    good, bad, n, d = base, None, 1, 0.0
    while d + step_mw <= max_mw:
        d += step_mw
        point = evaluate(d); n += 1
        if not point.ok:
            bad = (d - step_mw, d, point)
            break
        good = point
        if point.max_flow_mva >= stop_flow_mva:
            return Limit(base, good, "dlr_rating", n)
    if bad is None:
        return Limit(base, good, "max_transfer", n)
    lo, hi = bad[0], bad[1]
    while hi - lo > tol_mw:
        mid = 0.5 * (lo + hi)
        point = evaluate(mid); n += 1
        if point.ok:
            lo, good = mid, point
        else:
            hi = mid
    return Limit(base, good, bad_reason(bad[2]), n)       # "non_convergence" or "voltage_criterion"
```

### Closed-form model for the one physical fake test (margin)
A two-bus system: source voltage `E` (pu) behind reactance `X`, load `P + jQ` with `Q = P tan(phi)`. Voltage solves `V^4 + (2QX - E^2) V^2 + X^2 (P^2 + Q^2) = 0`, so `V^2 = (E^2/2 - QX) + sqrt((E^2/2 - QX)^2 - X^2 (P^2 + Q^2))`; the load flow "converges" exactly when the discriminant is >= 0; current `|I| = |S|/V` and the sending-end flow is `E |S| / V`. [VERIFIED: numerically this session with E = 1.0, X = 0.2, pf = 0.95: nose at P = 1.809869 pu; at P = 0.8 x nose the formula gives V = 0.8193, (P, Q) = (1.4479, 0.4759) and a phasor power balance gives the same (1.4479, 0.4759); sending MVA 1.8603 equals E x |S| / V.] The margin test computes the nose independently by bisection on the discriminant and asserts the study's `limit_transfer_mw` lies within `tol_mw` (and below the nose). The fake's `solver` callable returns "not converged" past the nose.

### Mapping JSON (placeholder)
See the Mapping section; the bus numbers 9xxxx must also be the buses of the fake case builder, so one builder produces both the example file and the in-memory case.

## Test strategy

### Fake `psspy` design (D-15)
- `FakePsspy` (in `backend/tests/psse_fake_psspy.py`, not collected) implements exactly the rows of `SURFACE` and nothing else (anything else raises `AttributeError`, so an unlisted call fails the test). Method names and parameter names are the manual's (`abrnint(sid=-1, owner=1, ties=1, flag=1, entry=1, string=None)` etc.); `_i`, `_f`, `_s`, `getdefault*` exist. Every call is appended to `fake.calls` as `(name, args, kwargs)`.
- State: an in-memory case (buses with base kV and scripted voltages; branches with status, RATEA/B/C, scripted flows and percent loadings, loads at sink buses), a registry of "saved case" copies keyed by normalised path (`save` stores a deep copy, `case` restores it, an unknown path returns `ierr = 3`; a `PLACEHOLDER_CASE.sav` marker file written by the test lets `file_sha256` produce a real hash).
- Behaviour: a `solver` callable `solver(case_state) -> Outcome(ierr, solved_code, voltages, flows, pct)` decides what `fnsl`/`solved` report. Defaults: converge with the base values. Per-test scripts: converge, `solved = 1`, `ierr = 3`, "converge except when branch X is out of service", "converge for increments below D", or the closed-form two-bus model for the margin test. `scal_2` adds the increment to the sink load; `branch_chng_3` sets status and ratings (and validates the `ratings` list length 12 and that no `_f` leaks into a rating).
- Keep it to roughly 200 lines; it needs to be right about call and return shapes, not about physics (except the one analytic margin test).

### Keeping fake and real from drifting
1. `SURFACE` in `psse_api.py` is the only list of `psspy` functions the job calls, each with parameter names and evidence/confidence.
2. `psse_api_test.py` asserts (a) `FakePsspy` has exactly those names, (b) `inspect.signature` of each fake method has those parameter names, (c) a recording run of the full study calls only `SURFACE` names and only with keyword names from the table.
3. A golden call-sequence file `backend/tests/data/psse_call_surface.json` (the ordered distinct `(name, keyword names)` seen in the happy-path study) is regenerated deliberately; a change to the study's call pattern shows up as a reviewed diff.
4. `psse_job/probe.py` (run once on the laptop in Phase 3, tested here against the fake): for each `SURFACE` name on the real module, compare `inspect.signature(...)` parameter names with the table (assumption: the real `psspy` functions are Python wrappers with named parameters, `[ASSUMED]`); run the read-only pass on the sample case (`psseinit`, `case`, `psseversion`, bulk branch/bus reads, `brndat` on three branches to confirm column alignment, `fnsl` plus `solved`); with a flag, write a rating to one branch, read it back and reload. Output is a plain pass/fail table the teammate pastes into the Phase 3 verification. Probe failures are the intended discovery mechanism for the `branch_chng_3` signature.

### What must be left to the Phase 3 laptop run
- That real PSS/E accepts each adapter call (above all `branch_chng_3`'s `ratings` argument and the `scal_2` combined form), and that the 33.5 option strings (`'MAXPCTRATEA'`, `'MAXMVA'`, ...) exist in the installed version.
- That the rating written is in the units Power Systems' case expects (read-back and one `PCTMVARATEA`/`MAXPCTRATEA` comparison on a branch with known flow), and which rate set Power Systems intends.
- That the sink/transfer definition per city produces a meaningful margin on their network (an engineer reviews the numbers); that a real N-1 over the chosen neighbourhood finishes within the hourly budget; the solve options and non-divergent setting behave as assumed.
- That the interpreter, psycopg pin and import path work (`psse_job` has only been syntax-checked against 3.7, never run on one).
- Anything involving licence modules (PV/QV, ACCC) if Power Systems later wants them.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `branch_chng(..., realar)` with RATEA-C at `realar[3:6]` | `branch_chng_3`/`branch_data_3` with a separate 12-value `ratings` list | PSS/E 34/35 ("from rev 34 there are twelve ratings", FORUM question 5279; "Rate A, B and C have been moved from realar to the new argument ratings", FORUM question 10559) | The rating write must target `ratings`, not `realar`; the exact 35 `branch_chng_3` signature is the first thing to confirm |
| `accc(...)` | `accc_with_dsp_3` (M33 marks `accc` obsolete and "implemented by a call to ACCC_WITH_DSP_3") | 33.x | Irrelevant to Phase 2 (manual loop) but the name to look for later |
| `solution_parameters` | `solution_parameters_4` (M33 "obsolete ... replaced by SOLUTION_PARAMETERS_4") | 33.x | Do not call the old one; Phase 2 does not set tolerances |
| Python 2.7 PSS/E (33) | Python 3.7 (34.7) / 3.9 (35.x) / 3.11 (36.1 reported) | 34 to 36 | Keep the 3.7 floor; no `psycopg` 3.3.6 below 3.10 (Phase 3 pins per interpreter) |
| Bare `import psspy` after PATH edits | `import psse35` then `import psspy` | 35 | Launcher concern; never inside `psse_job` |

**Deprecated/outdated:** `pssexcel` for headless reporting (unreliable), `BRNCUR`/`BRNMVA`/`BRNSTT` (obsolete, replaced by `brnmsc 'AMPS'`/`'MVA'` and `brnint 'STATUS'`, M33 7.8, 7.14, 7.15).

## Roadmap honesty (where the phase boundary is wrong or risky)

1. **"Proven here with a fake `psspy`" proves less than the success criteria read.** SC2's "units PSS/E expects" and SC3's margin/N-1 numbers are about the real engine and Power Systems' network. The fake proves arithmetic, control flow, failure handling and row shape. State this in the phase VERIFICATION, and keep a written list of Phase 3 confirmations (above).
2. **The voltage-stability margin has no single textbook definition and Power Systems has not defined one.** The recommended transfer-stepping definition is a defensible default, but the sink, the source and the stopping criterion are engineering choices for Power Systems. A placeholder mapping cannot validate them. Open Question 4.
3. **Representability gaps in the DDL (flagged, NOT changed; no defect found):** (a) no home for base-case violations (the study marks `in_base_case` inside `details`); (b) no "not computed" value for a city's margin or dispatch, so one city's failure fails all four (the intended all-or-nothing, but brittle for an hourly job; a later additive migration could allow it); (c) `psse_run.rate_set` is one text value (a joined label works). If the user wants (b) relaxed it is a Phase 6 coordination item, not a Phase 2 edit.
4. **Transformer, generator and multi-element contingencies are out of the recommended N-1 scope**, and so is a full-system screen by default. The ROADMAP says "N-1 contingency screening"; the definition above should be agreed with Power Systems before it is called that in a report.
5. **Static ratings overwrite the case's own ratings.** IN-01's fallback is the project's static rating, not Power Systems' value; applying it replaces the case's RATEA on mapped branches. The run records `rate_before_mva` so the difference is visible; whether Power Systems wants the static value or their own is Open Question 5.
6. **Deadline pressure (about 2026-11-02, five days).** If time is short, the cut order that preserves the success criteria is: keep mapping + apply + base solve + N-1 loop with `hops = 1` + the transfer search with a coarse step and no bisection; do not drop the read-back, the reload discipline or the failure paths.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `branch_chng_3(i, j, ckt, intgar, realar, ratings, namear)` mirrors the documented `branch_data_3`; `ratings` has 12 values and unspecified entries can be left with `_f` | Surface; Rating write | The write call fails or writes the wrong slot; the probe and read-back catch it; adapter is the single place to fix |
| A2 | The 33.5 option strings (`MAXPCTRATEA`, `MXPCTMVARATA`, `MAXMVA`, `P`, `TYPE`, `STATUS`, `ID`, `BASE`, `PU`, `NVL/EVL`) exist unchanged in 35/36 | Surface; Thermal | A bulk read returns ierr 9 (invalid string); probe catches it |
| A3 | `solved()` codes are unchanged in 35/36 | Convergence | A new non-zero code would still fail (only 0 is success), so low risk |
| A4 | `fnsl()` with no arguments uses program settings (PyPSSE does it) | Convergence | Different default options; optional `solve_options` covers it |
| A5 | PSS/E 34.7 bundles Python 3.7.3; 35.x 3.9; 36.1 3.11 | Python versions | Only affects which interpreter the laptop uses; the 3.7 floor already covers all |
| A6 | Real `psspy` functions are Python wrappers whose `inspect.signature` exposes the manual's parameter names | Probe | Probe falls back to call-and-observe; fake drift check weaker |
| A7 | Power Systems supplies a `.sav` case with non-transformer city lines, one base kV per city, and in-service mapped branches | Mapping | More mapping failures on first contact; they are reported, not hidden |
| A8 | ERCOT-style voltage bands (0.95-1.05 normal, 0.90-1.05 contingency, above 100 kV) are the right defaults | Voltage limits | Wrong violation counts; limits are configuration |
| A9 | Rate A is the right set for DLR; N-1 limits use the same set | Rate set | N-1 limit mismatch with Power Systems' practice; Open Question 1 |
| A10 | Constant power factor 0.95 for `dispatched_mw` | Dispatch | MW differs from the physical branch value; stored and labelled, DDL-valid |
| A11 | Defaults `thermal_limit_pct` 100, `step_mw` 25, `tolerance_mw` 1, `max_mw` per city, `contingency.max` 200, `hops` 2, `max_mismatch_mva` 1.0, `max_runtime_seconds` 1500 | Settings | Tuning only; all configuration |
| A12 | `psspy` holds process-global state; one study per process | Pitfall 12 | Leaked subsystem/case state if reused |
| A13 | `scal_2` with `STATUS = [_i, 3, 0, 1, 0]` and `SCALVAL = [d, 0, ...]` increases only the load of the subsystem at constant P/Q, leaving generation unchanged | Margin | The swing absorbs a different amount; flow-must-rise guard catches a no-op |
| A14 | Bulk columns from separate calls with identical arguments are aligned | Pitfall 8 | Wrong ratings/flows per branch; probe check and equal-length assertion |
| A15 | The PV/QV engines need a licensed module and DFAX inputs | Margin | If not, an engine-based margin could be easier later; no Phase 2 impact |
| A16 | `savnw.sav` ships with PSS/E on the laptop | Mapping | Phase 3 smoke needs another sample case |
| A17 | A real N-1 over the neighbourhood (tens of outages) fits an hourly budget | N-1 | Needs a smaller neighbourhood or ACCC; measured only in Phase 3 |

## Open Questions

1. **Which rate set receives the DLR value, and does N-1 use B?** (for Power Systems; same as the spec's open question 1)
   - Known: Rate A is continuous, B is two-hour emergency in ERCOT practice (search summaries); DLR is an ampacity.
   - Unclear: their case's convention and whether N-1 limits come from RATEB.
   - Recommendation: default `["RATEA"]` used for every check; make `rate_sets` configuration so `["RATEA","RATEB"]` is a file edit.
2. **Which branch(es) per city, and are they all one base kV?** (spec open question 3). Recommendation: the mapping check fails loudly on a mixed-kV city; ask for the mapping early because a placeholder cannot answer it.
3. **Case size and N-1 volume / run time** (spec open question 2). Recommendation: neighbourhood scope with caps; measure on the laptop in Phase 3.
4. **Transfer definition for the voltage margin: which buses are the sink, what supplies the increase?** Recommendation: default sink = the far end of the mapped branch, swing absorbs; Power Systems confirms or replaces per city in the mapping file.
5. **Should the static rating overwrite the case's own rating on mapped branches?** Recommendation: yes per IN-01, with `rate_before_mva` recorded so the difference is visible.
6. **Should base-case violations be written in the N-1 table?** Recommendation: yes, flagged `in_base_case`; a reader filters. Decision is Power Systems'.
7. **Does the laptop's PSS/E have a PV/QV or ACCC licence, and does Power Systems want those used instead of the native loops?** Recommendation: defer; the `study` seam and the free `method` label allow it.
8. **Which Python version, `psycopg` pin and `psse35`/`psse36` import** (Phase 3; the 01-VERIFICATION human item). Recommendation: probe plus the Phase 3 setup guide.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (venv) | all tests | yes | 3.12.10 | none needed |
| pytest | all tests | yes | 9.0.3 | none needed |
| psycopg + psycopg-binary | `run_once` write-back tests | yes | 3.3.6 | PG tests are required (`PSSE_REQUIRE_PG=1`) |
| Local Postgres binaries | write-back and DDL tests | yes (per spawn prompt: portable 18.6 on PATH `C:/Users/tejas/Downloads/postgresql-18.6-5-windows-x64-binaries/pgsql/bin`) | 18.6 | none; a skip is a failed gate |
| PSS/E / `psspy` | real adapter behaviour | NO (`import psspy` -> `ModuleNotFoundError: No module named 'psspy'`; no `C:/Program Files/PTI`, no `C:/Program Files/Siemens`) | n/a | `FakePsspy` for Phase 2; real run in Phase 3 |
| numpy / pandas | nothing in this phase | NO (must not be assumed) | n/a | stdlib only |
| A real Python 3.7 interpreter | syntax confidence | NO | n/a | `ast.parse(feature_version=(3, 7))` gate only (documented best-effort) |
| Network | web research only | yes | n/a | n/a |

**Missing dependencies with no fallback:** none for Phase 2 execution.
**Missing dependencies with fallback:** PSS/E (fake), real 3.7 interpreter (syntax gate; Phase 3 probe).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3, plain asserts, no classes [VERIFIED: pytest --version this session; TESTING.md house style] |
| Config file | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Quick run command | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/psse_contract_test.py backend/tests/psse_mapping_test.py backend/tests/psse_api_test.py backend/tests/psse_study_test.py` (the four Phase 1 non-database files ran 162 passed in 10.6 s this session) |
| Full suite command | `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_*_test.py backend/tests/secret_scan_test.py` (Postgres `bin` on PATH; Phase 1 baseline 243 passed, 0 skipped, about 109 s) |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| IN-02 | Mapping loads/validates (four cities, ckt length, duplicates across cities, placeholder refused unless allowed, size cap, unknown keys rejected, `mapping_sha256` equals file bytes) | unit | `pytest backend/tests/psse_mapping_test.py` | Wave 0 |
| IN-02 | A mapped branch missing from the case, out of service, a transformer, or mixed kV raises `StudyFailed("mapping")` before any rating write; the fake saw no `branch_chng_3` and no `fnsl` | unit (fake) | `pytest backend/tests/psse_study_test.py -k mapping` | Wave 0 |
| IN-02 | Through `run_once` into Postgres: one `failed` row, `failed_stage = mapping`, zero result rows, exit 1 | integration (PG) | `pytest backend/tests/psse_study_job_test.py -k mapping` | Wave 0 |
| IN-03 | Written MVA equals `units.circuit_mva(selection amps, count, case base kV)` for every city (Austin 2181.1 MVA at 345 kV, El Paso 788.8; a 138 kV case gives a different number); the read-back is enforced (fake that ignores the write fails the run); never zero/NaN | unit (fake) | `pytest backend/tests/psse_study_test.py -k units` | Wave 0 |
| IN-03 | Static fallback applies static amps (provisional rows, today's state) and a fresh non-provisional row applies the row's amps; nothing else reaches `set_rate` | unit (fake) | `pytest backend/tests/psse_study_test.py -k static` | Wave 0 |
| STU-01 | `solved` 1, 2, 3, 5, and `fnsl` ierr 2/3 with `solved` 0 are all non-converged; only (0, 0) converges; base failure is `StudyFailed("load_flow")`; the message names the code meaning | unit (fake) | `pytest backend/tests/psse_api_test.py -k solve` and `psse_study_test.py -k load_flow` | Wave 0 |
| STU-01 | Through `run_once`: non-converging base case leaves one `failed` row at `load_flow`, no result rows | integration (PG) | `pytest backend/tests/psse_study_job_test.py -k non_converg` | Wave 0 |
| STU-02 | Scripted outages produce thermal and voltage rows with limit, observed, exceeded_by, unit, city for mapped branches; non-converged outage gives a `non_convergence` row; `in_base_case` flag; zero outages and over-cap fail at `contingency`; every row passes `validate_results` | unit (fake) | `pytest backend/tests/psse_study_test.py -k contingency` | Wave 0 |
| STU-02 | Violation evaluation pure functions (low/high voltage distance, thermal basis current vs mva, rating 0 skipped, isolated bus skipped) | unit | `pytest backend/tests/psse_study_test.py -k violation` | Wave 0 |
| STU-03 | Analytic two-bus fake: reported limit within tolerance of the independently bisected nose and below it; `bounded_by` variants (non_convergence, voltage_criterion, dlr_rating, max_transfer, base_case); flat-flow guard fails at `voltage_margin` | unit (fake, analytic) | `pytest backend/tests/psse_study_test.py -k margin` | Wave 0 |
| STU-04 | Dispatch row identities via `validate_results`; tie goes to `dlr_rating`; voltage-limited case reports `voltage_stability`; amps and MW consistent | unit | `pytest backend/tests/psse_study_test.py -k dispatch` | Wave 0 |
| TST-01 | Static fallback, mapping check, non-converging load flow, write-back with a failed run, all through `run_once` with the real writer and the fake `psspy`; a successful run has 1 + 4 + 4 + N rows and every completeness check ok | integration (PG) | `pytest backend/tests/psse_study_job_test.py` | Wave 0 |
| Drift | Fake method names and parameter names equal `SURFACE`; recorded study calls are inside `SURFACE`; golden call-surface file unchanged | unit | `pytest backend/tests/psse_api_test.py -k surface` | Wave 0 |
| Hygiene | New modules parse as 3.7 syntax and import nothing outside the (deliberately extended) allow-list; no `psspy` import; no `rating_mw` constant; `POWER_FACTOR_DEFAULT` equals `config.POWER_FACTOR`; case path never passed to `save`; no secret or grid identifier in logs | unit | `pytest backend/tests/psse_contract_test.py` | exists; allow-list edit + new drift test in Wave 0 |

### Sampling Rate
- **Per task commit:** the quick run command (no database).
- **Per wave merge:** the full suite command (any skip is a failure, `PSSE_REQUIRE_PG=1`).
- **Phase gate:** full suite green plus a mutation check like Phase 1's (plant at least: skip the read-back, treat `solved() == 1` as converged, trust `solved()` after a failed `fnsl`, write ratings before the mapping check, `save` onto the case path, truncate N-1 silently, accept a flat transfer, tie goes to `voltage_stability`; each plant must turn a test red).

### Wave 0 Gaps
- [ ] `backend/tests/psse_fake_psspy.py` (helper), `psse_mapping_test.py`, `psse_api_test.py`, `psse_study_test.py`, `psse_study_job_test.py`, `backend/tests/data/psse_call_surface.json`
- [ ] `psse_contract_test.py`: add `tempfile` (and `inspect`, `argparse` if the probe lives in the package) to `_STDLIB_ALLOWED` as a deliberate edit; add the `POWER_FACTOR_DEFAULT` drift assertion
- [ ] `backend/psse_job/constants.py`: `POWER_FACTOR_DEFAULT`, `RATE_SETS = ("RATEA", "RATEB", "RATEC")`, settings defaults
- [ ] `docs/data-science/schema/psse_mapping_example.json`, `.gitignore` rule for a local PSS/E directory, `docs/data-science/decisions/psse_study_definitions.md`
- [ ] No framework install needed (pytest, psycopg, Postgres already present)

## Security Domain

`security_enforcement` is not disabled (no such key in `.planning/config.json`), so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (Phase 3 owns the DB credential) | n/a here |
| V3 Session Management | no | not interactive |
| V4 Access Control | yes (files) | the case file is never written; temp copies in a per-run directory; mapping and case paths come from environment on the laptop, not the repo |
| V5 Input Validation | yes | mapping JSON validated by hand-written code: type and range checks, bounded size, closed key set, `ckt` shape, no `eval`, no pickle, no YAML; `psspy` receives only validated ints/strings |
| V6 Cryptography | partial | `hashlib` sha256 only (`run_record.file_sha256`); nothing hand-rolled |
| V7 Error handling / logging | yes | every failure text goes through `redact` (done by `run_once`); grid identifiers appear only in the private tables and local logs, never in the public repo |
| V14 Configuration | yes | real mapping/case not committed; `.gitignore` rule; example file marked placeholder with fake numbers |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Grid identifiers committed to a public repo | Information disclosure | placeholder-only example, `.gitignore`, a test that the example is `placeholder: true` and in the fake range |
| Study rewrites Power Systems' case | Tampering | adapter refuses `save` onto the case path; test asserts no such call |
| Malicious or malformed mapping (huge file, wrong types, path-like `ckt`) | Tampering / DoS | size cap, closed schema, `ckt` 1 to 2 printable characters, ints only |
| Unbounded N-1 or search consuming the hourly slot | Denial of service | `contingency.max`, `MAX_CONTINGENCY_ROWS`, `max_runtime_seconds` between solves; Phase 3 adds the scheduler time limit |
| A stale or fabricated number written as a result | Tampering (integrity of meaning) | rating read-back, only `(ierr == 0 and solved() == 0)` converges, fail closed, `validate_results` on every output |
| Secret/URL in error text | Information disclosure | existing redaction; `details` limited to numbers, ids, labels |
| Case hash taken from a different file than the one loaded | Tampering | hash and load the same path in one launcher step; record both |

## Sources

### Primary (HIGH confidence, read this session)
- Repo: `backend/psse_job/{constants,contract,job,ratings,run_record,units,writer,__init__}.py`, `backend/tests/{psse_contract_test,psse_fakes,psse_job_test}.py`, `backend/tests/psse_local_pg.py` (function list), `docs/data-science/schema/psse_results_v1.md` and `.sql`, `docs/data-science/decisions/pss_e_handoff.md`, `.planning/workstreams/pss-e-integration/{REQUIREMENTS,STATE,ROADMAP}.md`, Phase 1 `01-RESEARCH.md` and `01-VERIFICATION.md`, `pytest.ini`.
- Local runs: `pytest --version`, `pip list`, the four non-database Phase 1 test files (162 passed), `import psspy` (absent), numerical check of the two-bus PV closed form.

### Secondary (MEDIUM confidence, official text via a third-party copy or open-source code)
- PSS/E 33.5 API manual text (Siemens), third-party copy: https://pdfcoffee.com/psse-9-pdf-free.html (sections BRANCH_CHNG 2.2, BRNDAT 7.9, BRNINT 7.12, BRNMSC 7.13, BUSDAT 7.17, SOLVED 7.142, SYSMSM 7.155, aBus/aBrn families 8.3 and 8.12, CASE 1.50, SCAL_2 1.274, PSSEINIT/PSSEVERSION/GETDEFAULT* chapter 12)
- "PSSPY Reference" PDF (34 era): https://www.3phaseee.com/static/docs/psspy.pdf (fnsl/fdns options and error codes, save, bsys, dfax_2, accc_parallel_2, pv_engine_6, qv_engine_4)
- 2024 blog quoting the 35-era API: https://powersystemautomation.wordpress.com/2024/09/15/basic-automation-of-power-flow-activities-in-python/
- PyPSSE source (BSD-3-Clause), files `pypsse/simulator.py` (lines 20, 84, 87, 90, 172-174), `pypsse/modes/static.py` (25, 36), `pypsse/modes/pcm.py` (31-33, 54-55), `pypsse/modes/abstract_mode.py` (43-139 string tables, 987): https://github.com/NatLabRockies/PyPSSE
- PTI raw format description: https://cialab.ece.uw.edu/research/pstca/formats/pti.txt (via search summary)

### Tertiary (LOW confidence, community or search summaries not opened in full)
- psspy.org help forum: questions 3985 (solved codes comment), 6921 (iterat/sysmsm/solved), 7299 (Rate = In x Vbase x sqrt(3); percent loading and voltage), 5279 (twelve ratings), 10559 (35 `ratings` argument), 10264 and 3039 (`branch_chng_3`, change versus data), 8382 (`_i`/`_f` placeholders), 6830 (`scal_2`), 9121 (`psse35`, PSSPY39), 11182 (bundled Python, `-pyver`, via summary), 8600 (`pssexcel` unreliable), 119 (`readrawversion`), 2241 (silencing output), 1245 and 11170 (ACCC input files are user-built), 2441 (save/reload around `fnsl`, via summary), 8490 (RATEA = 0 means no limit, via summary)
- ERCOT planning documents (search summaries only): voltage bands and 8 percent rule https://www.ercot.com/files/docs/2015/03/17/041PGRR_11_ROS_Report_031215.doc; Rate A/B usage https://www.ercot.com/files/docs/2014/02/03/031pgrr_16_calpine_comments_020314.doc; AEP restatement https://AEP.com/assets/docs/requiredpostings/TransmissionStudies/docs/2024/TransmissionPlanningReliabilityCriteria-AEP_ERCOT-2024_Filing.pdf
- Vendor blogs on Python/PSS/E version pairing (keentelengineering.com): reference only, contradicted or unconfirmed on several rows

## Metadata

**Confidence breakdown:**
- Repo contracts and failure plumbing: HIGH (read this session; Phase 1 verified 243 tests)
- Core `psspy` signatures and `solved()`/`fnsl` codes: MEDIUM-HIGH for 33.5, MEDIUM for 35 (blog and PyPSSE), LOW for 36
- `branch_chng_3`, option strings in 35/36, probe's `inspect` assumption: LOW (flagged UNVERIFIED/ASSUMED)
- Modelling choices (rate set, thermal basis, voltage bands, margin definition, N-1 scope): MEDIUM as recommendations, LOW as facts about Power Systems' case
- Pitfalls and test strategy: HIGH (derived from verified contracts and the manual's error tables)

**Research date:** 2026-10-28
**Valid until:** about 7 days for the Phase 1/Phase 6 coupling facts; the `psspy` documentation facts are stable but must be re-confirmed against the laptop's installed PSS/E on first contact (Phase 3 probe).

## RESEARCH COMPLETE
