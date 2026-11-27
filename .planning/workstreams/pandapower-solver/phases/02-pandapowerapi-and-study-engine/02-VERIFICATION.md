---
phase: 02-pandapowerapi-and-study-engine
verified: 2026-11-24T05:46:10Z
status: passed
score: 6/6 must-haves verified
covered_files:
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-01-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-01-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-02-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-02-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-03-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-03-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-04-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-04-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-05-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-05-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-06-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-06-SUMMARY.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-07-PLAN.md
  - .planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-07-SUMMARY.md
  - backend/pandapower_job/api.py
  - backend/pandapower_job/engine.py
  - backend/pandapower_job/scaling.py
  - backend/pandapower_job/solve.py
  - backend/psse_job/study.py
  - backend/tests/pandapower_api_contract_test.py
  - backend/tests/pandapower_api_test.py
  - backend/tests/pandapower_engine_recorded_test.py
  - backend/tests/pandapower_engine_test.py
  - backend/tests/pandapower_import_gate_test.py
  - backend/tests/pandapower_study_behaviour_test.py
  - backend/tests/pandapower_study_fixture.py
  - backend/tests/pandapower_study_job_test.py
  - backend/tests/psse_study_solver_test.py
covered_digest: "v3:sha256:82b320a2b1e62310274de47c3e4bd5ed8a0d0dd75cca74052574c550a006beeb"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 2: PandapowerApi and Study Engine Verification Report

**Phase Goal:** The existing study code (`study`, `contingency`, `margin`, `violations`, `dispatch`) runs a full four-city study on pandapower, chosen through one factory argument, with the island, stale-result and rating-basis traps handled and no access to live data.
**Verified:** 2026-11-24
**Status:** passed, with real limits (listed under "Limits that stay attached to this pass"). The limits are about what the database proof of ENG-06 shows. None of them is a defect in the code.
**Re-verification:** No, initial verification.

Private data rule kept: nothing under `data/private/` was opened, read, grepped or printed by me. One owner-local test (`pandapower_engine_recorded_test.py`) reads it by itself and prints counts only; I judged it from its pass result and its public source. The leak scan (`backend/private_leak_scan.py`, whole tree) exits 0, `data/private/pandapower` is git-ignored, and `git ls-files data/private` lists nothing.

What changed in the environment today, stated plainly: until now the database tier of ENG-06 (4 of the 5 tests in `pandapower_study_job_test.py`) only skipped here, because this Windows machine had no Postgres (02-06-SUMMARY says so). PostgreSQL 17.12 is now installed. I ran the whole database tier myself, and it passes. The Windows guard for `pg_ctl` that these tests need is in `backend/tests/psse_local_pg.py`, committed long before this phase. The harness edit committed today (`c10f8dc`, `backend/tests/local_pg.py`) is a different harness (the production-pipeline one) and is not used by any Phase 2 test. So no harness change was needed to get ENG-06 green.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1 / ENG-01: a test fails if any `PandapowerApi` method name or signature differs from `PsseApi`; `study.py` chooses the solver through one new factory argument; the existing PSS/E tests pass unchanged | VERIFIED | `pandapower_api_contract_test.py::test_public_surface_equals_psse_api` compares the 14 public names and every `inspect.signature` with `PsseApi`; `test_constructor_matches_psse_api` pins the constructor; `test_study_code_calls_only_the_pinned_surface` walks the AST of the study modules and requires the called set to equal the 14 pinned methods. `study.py:332-368`: `API_FACTORIES`, `register_solver`, and a last keyword `solver="psse"` on `_open_case`, `index_case`, `prepare_base`, `make_study`, `prepare_run`; `api.py:459-472` registers the factory under `"pandapower"` on import. Existing PSS/E tests: plan 02-01's commits add two test files and change no existing test (`git diff --name-status 9100fb1 5540b86`). I ran `psse_study_test.py`, `psse_contract_test.py` and `psse_study_job_test.py` (its 14 database tests too): 72 passed. See Finding F-3 for the wording "one factory argument". |
| 2 | SC2 / ENG-02: a city's rating is a current limit per circuit and loading is read on the current basis; a mapping asking for a basis pandapower cannot reproduce is refused with a clear failure | VERIFIED | `api.py` `set_rate` writes `max_i_ka = MVA / (sqrt(3) * from-bus kV)` per line; `read_rate` converts back; `branch_loading` refuses any basis other than `current` and refuses a net whose line `df` or `parallel` is not 1 (the two silent denominator changes). `engine.preflight` refuses `thermal.basis != "current"`, PSS/E `solve.options`, `voltage.source != "config"` and an undecided reactive-limit setting, at stage `mapping`, before any adapter is built. Tests: `pandapower_api_test.py::test_rating_is_a_current_limit_per_circuit`, `test_line_derating_and_parallel_are_pinned`, `test_refuse_mva_basis_and_unknown_names`; `pandapower_engine_test.py::test_preflight_refuses_*` (4) and `test_preflight_refusal_builds_no_adapter_and_keeps_the_hash`. Database: `test_recorded_preflight_refusal` stores the refusal as one `failed` run at stage `mapping` with no result rows. |
| 3 | SC3 / ENG-03: a solve is converged only if it raises no error, leaves no in-service bus without a voltage and none below the collapse limit; an islanding outage is a `non_convergence` row | VERIFIED | `solve.py:124-140` `_solve_once`: any exception is a non-converged outcome (class name kept, message dropped); `net.converged` false is non-converged; any NaN voltage on an in-service bus is `nan_voltage`; any in-service bus below `collapse_voltage_pu` is `voltage_collapse`. `api.py` `solve` maps these to `classify_solve` (ierr 3 for an island, 2 for collapse, 1 for the iteration limit). Behavioural evidence (run, not read): `pandapower_api_test.py::test_island_is_not_converged_while_pandapower_says_converged`, `test_nonconv_iteration_limit`, `test_collapse_voltage`; `pandapower_study_behaviour_test.py::test_tracer_island_is_one_non_convergence_row`; database: `test_written_island_row_is_stored` finds exactly one `non_convergence` row per city with `details.ierr == 3` in a written run. |
| 4 | SC4 / ENG-04: each city, outage and margin step solves a fresh copy; running outages in another order, or after a failed solve, gives identical results; no result is read after a failed solve | VERIFIED | `api.py` state machine FRESH / SOLVED / FAILED / STALE: `bus_table` and `branch_loading` are refused in FAILED and STALE, `load_case` hands out a `copy.deepcopy` of a never-modified master. Behavioural tests that ran: `pandapower_study_behaviour_test.py::test_order_does_not_change_the_screen`, `test_a_failed_outage_does_not_change_the_others`, `test_recorded_calls_never_read_after_a_failed_solve` (a recording adapter logs every call across a full four-city study), `test_every_solve_runs_on_a_freshly_loaded_copy`, `test_each_city_loads_the_case_afresh`, `test_master_unchanged_after_a_full_study`, `test_two_runs_give_equal_results`; `pandapower_api_test.py::test_order_and_a_failed_solve_do_not_change_results`, `test_state_stale_after_status_or_rating_change`; `pandapower_api_contract_test.py::test_margin_step_reloads_a_fresh_copy`. These are behaviour-dependent truths and each has a passing behavioural test, so none is left presence-only. |
| 5 | SC5 / ENG-05: the solve settings come from the values recorded in PSE-02 and are stored with each run | VERIFIED | `engine.load_recorded_backend` / `backend_from_records` read the Phase 1 check output fail-closed (11 refusal reasons; a source that says "placeholder" is refused). `engine._recording_study` writes a `solve_settings` record (`SETTINGS_RECORD_KEYS`) into every dispatch row's `details`; `psse_version` is None for a pandapower run. `pandapower_engine_test.py` (21 tests) covers the loader and refusals. Owner-local: `pandapower_engine_recorded_test.py` 2 passed, not skipped, on this machine (the recorded PSE-02 output is present; `DLR_PANDAPOWER_REQUIRE_RECORDS` was not needed because nothing skipped); it asserts `is_placeholder` is False and that all four dispatch rows carry exactly the recorded settings. 02-07-SUMMARY records the owner's confirmation of the five engine choices on 2026-11-20. Limit: that recorded-settings run is in memory on the public fixture; it is not the database tier (see Limits). |
| 6 | SC5 / ENG-06: a full four-city study runs end to end on a throwaway local database with the placeholder mapping and no access to live data | VERIFIED (with limits) | See "ENG-06: what the database tier proves, and what it does not" below. 5 of 5 tests passed with Postgres 17.12, `PSSE_REQUIRE_PG=1`, none skipped; the same file with `PSSE_REQUIRE_PG=1` and no database fails 4 of 5 (the gate works). |

**Score:** 6/6 truths verified, 0 present-but-behavior-unverified.

### ENG-06: what the database tier proves, and what it does not

What I ran: `pandapower_study_job_test.py` with `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1` (verbose, 5 passed in 103 s, the four database tests taking 22 to 29 s each), and as a negative control the same file with `PSSE_REQUIRE_PG=1` and no database (1 passed, 4 errors from `psse_local_pg.py:104`). Neither `DLR_TEST_DATABASE_URL` nor any other connection string was set, so the database was the throwaway cluster the fixture starts on `127.0.0.1` under pytest's temp directory.

**It proves:**

- The full four-city pandapower study built by `engine.prepare_run` with the placeholder backend and the generated placeholder mapping goes through `job.run_once` and the real writer, connecting as the local `dlr_psse_writer` role, into a throwaway local Postgres 17.12 (initdb under pytest's temp dir, stopped afterwards). It stores 1 run, 4 dispatch, 4 margin and at least 1 contingency row, outcome `fallback` (the fake ratings are provisional), status `written`, and every row of `psse_results_v1_checks.sql` reports ok.
- The stored run holds `psse_version` NULL, `rate_set` RATEA, the case and mapping hashes of the files, `n_contingencies_with_results` equal to the number of distinct contingency ids actually stored, and `solver = pandapower`, `solver_version =` the installed pandapower version, a `pp-` run id. Every dispatch row's `solve_settings` says solver pandapower and `placeholder` true. The scratch folder is empty afterwards and the case file's hash is unchanged.
- A refused preflight is stored as one `failed` run at stage `mapping` with no result rows and the mapping hash kept. A one-city scaling refusal (CORPUS_CHRISTI at 25 times its case load) is stored as one failed run at stage `apply_ratings` whose error names each city's outcome, with none of the 14 target texts in the stored error or in any log line. An islanding outage is one `non_convergence` row per city in an otherwise complete, written run.
- The database's own CHECK constraints, writer-role grants and the completeness checks accepted these rows. That is exactly what the 02-06 SUMMARY said it could not show without a database (it had only run the scenarios against a recording stand-in).
- No live host is named in the test file or its fixture (`grep -ci "supabase.co|pooler.supabase"` gives 0 for both), the ratings come from `psse_fakes.fake_fetch`, and the harness fails any non-local `DLR_TEST_DATABASE_URL`.

**It does not prove:**

- Anything about live data or the live Supabase project. No live connection was made and none could be made by this file. The migration, the writer role and the policies of the live project are untouched; the owner applies SQL there (Phase 3 and 6 boundary).
- Anything about the real mapping or the real network. The mapping is the generated placeholder, the network is the public 39-bus fixture with one limit raised (`pandapower_study_fixture.py`), the scaling targets are synthetic, the ratings are fake. The solve settings in the database tier are the placeholder constants, so the stored `placeholder` flag is true by design. The real recorded PSE-02 settings (truth 5) have been run through four cities in memory only, not through the writer into Postgres.
- Engineering agreement with PSS/E. That is Phase 4's replay (see its VERIFICATION.md) and Phase 1's NET-03, not this phase.
- An hourly cloud run. The hourly GitHub Actions workflow is not built (Phase 5 is unbuilt: no workflow, no dry run, no 24-hour soak, no live write). Nothing here has ever run on a schedule or in GitHub Actions.
- Behaviour on Supabase's own Postgres version, extensions, connection pooler or row-level-security policies. The proof is on a local PostgreSQL 17.12 cluster with the reference DDL and the migrations applied by the harness.
- That the test file is Phase 2 alone. Phase 3 plan 03-04 (`89e3a92`) edited `pandapower_study_job_test.py` after the Phase 2 summary: its fixture now applies the solver-tag migration (`apply_solver_schema`), `_run` passes `solver=engine.SOLVER`, and the tests assert `solver`, `solver_version` and the `pp-` prefix. Phase 3 also changed `job.py`, `writer.py` and `run_record.py` in default-preserving ways. So what passed today is the Phase 2 run plus the Phase 3 tag, against a local database that carries a migration that is not applied to the live project. This does not weaken the Phase 2 claim (the file still contains every Phase 2 assertion) but the file can no longer be run against a schema without that migration.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/pandapower_job/api.py` (472 lines) | `PandapowerApi`, state machine, scaling four, registration | VERIFIED | Substantive (read in full); wired: imported by `engine.py`, registers the factory with `study` and the tag with `contract` on import; import boundary one-way (`pandapower_import_gate_test.py`, 4 passed). |
| `backend/pandapower_job/engine.py` (360 lines) | `prepare_run`, `preflight`, placeholder and recorded backends, settings record | VERIFIED | Read in full; called by the database tier, the behaviour tests and Phase 4's replay. |
| `backend/pandapower_job/scaling.py`, `solve.py` | one totals definition, convergence rule | VERIFIED | `solve.py:124-140` read; `scaling.case_totals` and `scale_city` are what `read_totals` and `scale_case` call (`api.py`). |
| `backend/psse_job/study.py` | solver registry and `solver=` keyword | VERIFIED | `study.py:332-368`; default `"psse"` on every entry point; `psse_study_solver_test.py` 8 passed. |
| Test files (11) | proofs | VERIFIED | All present, substantive, all ran green (counts below). |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `engine.prepare_run` | `study.make_study(..., solver="pandapower")` | `engine.py` (call with `api.SOLVER_NAME`) | WIRED |
| `study._open_case` | `PandapowerApi` | `API_FACTORIES["pandapower"]`, registered by `api.py` on import, which `engine.py` imports | WIRED |
| `PandapowerApi.solve` | `solve.run_load_flow` | `api.py` `solve`, with the backend's settings, never a constant | WIRED |
| `engine._recording_study` | every dispatch row's `details.solve_settings` | `engine.py`; read back from Postgres by the tracer test | WIRED |
| `engine.prepare_run` | `job.run_once` and writer | `PreparedRun` fields into `run_once`; stored rows read back as superuser | WIRED |
| `psse_job` | no pandapower import | `pandapower_import_gate_test.py` (text scan, AST walk, fresh `python -I`) | WIRED (boundary holds) |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| stored dispatch rows | `details.solve_settings` | `engine.settings_record(run_backend, ...)` from the backend given to `prepare_run` | The placeholder backend in the database tier; the recorded backend in `pandapower_engine_recorded_test.py` | FLOWING (read back from Postgres in the tier that stores it) |
| stored contingency rows | screen results | unchanged `contingency`/`violations` over `PandapowerApi` solves on the fixture | Yes, real pandapower solves | FLOWING |
| `non_convergence` rows | island outage | `PandapowerApi.solve` ierr 3, `violations.non_convergence_row` | Yes | FLOWING |

### Behavioral Spot-Checks (I ran these)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Method names and signatures pinned to `PsseApi`; core adapter; engine and loader; import boundary; solver seam | `pytest backend/tests/pandapower_api_contract_test.py pandapower_engine_test.py pandapower_api_test.py pandapower_import_gate_test.py psse_study_solver_test.py` (16 + 21 + 25 + 4 + 8) | 74 passed, 63.7 s | PASS |
| Study-level island, order and stale-result proofs (real solver); database tier (ENG-06); owner-local recorded settings | `pytest backend/tests/pandapower_study_job_test.py pandapower_study_behaviour_test.py pandapower_engine_recorded_test.py` (5 + 9 + 2), `-rs` showing no skip | 16 passed, 200 s, 0 skipped | PASS |
| Database tier alone, verbose | `pytest -v backend/tests/pandapower_study_job_test.py` | 5 passed, 103 s | PASS |
| Negative control: missing database must fail, not skip | same file, `PSSE_REQUIRE_PG=1`, no autostart, no URL | 1 passed, 4 errors (`psse_local_pg.py:104`) | PASS (gate works) |
| Existing PSS/E tests unchanged and green, including their database tier | `pytest backend/tests/psse_study_test.py psse_contract_test.py psse_study_job_test.py` (48 + 10 + 14) | 72 passed, 32.8 s | PASS |
| Whole-tree leak scan | `python -I -B backend/private_leak_scan.py` | exit 0 | PASS |

Environment for all runs: Git Bash, `PATH` with `C:\Program Files\PostgreSQL\17\bin`, `DLR_TEST_PG_AUTOSTART=1`, `PSSE_REQUIRE_PG=1`, `PYTHONDONTWRITEBYTECODE=1`, `.venv/Scripts/python.exe` (Python 3.12.10, pytest 9.0.3, pandapower present). Total for this phase's own test files: 90 tests (74 + 16), 0 failed, 0 skipped. The 72 PSS/E tests are an extra regression check on "existing tests pass unchanged".

Not run, and not Phase 2 defects: the Windows-only failures you named (CRLF byte-hash tests, `pandapower_cli_test.py` and `pandapower_ingest_test.py` on file mode 0o600 and zip member name) and the files that need matplotlib or sklearn, which the venv lacks. None of the eight Phase 2 files above depends on them. I did not re-run the Phase 1, 3 or 4 test files.

### Probe Execution

Step 7c: SKIPPED (no probe scripts declared by the phase; no `scripts/*/tests/probe-*.sh` relevant).

### Requirements Coverage

| Requirement | Source Plans | Description | Verdict | Evidence |
|-------------|-------------|-------------|---------|----------|
| ENG-01 | 02-01, 02-03 | Same methods as `PsseApi`, chosen by one factory argument, tests pin names and signatures | MET | Truth 1. |
| ENG-02 | 02-02, 02-04 | Rating as current limit per circuit, current basis, unreproducible basis refused | MET | Truth 2. |
| ENG-03 | 02-02, 02-05 | Converged only on no error, no voltage-less in-service bus, none below collapse; island is `non_convergence` | MET | Truth 3; behaviour and database tests ran green. |
| ENG-04 | 02-02, 02-05 | Fresh copy per city, outage and margin step; no read after a failed solve | MET | Truth 4. |
| ENG-05 | 02-04, 02-07 | Solve settings from PSE-02, stored with each run | MET | Truth 5. Stored as a record in every dispatch row; since Phase 3 the run row also carries solver and version. |
| ENG-06 | 02-04, 02-06 | Four-city study end to end on a throwaway local database, placeholder mapping, no live data | MET WITH LIMITS | Truth 6 and the section above. First time the database tier has run green anywhere (today, Postgres 17.12, Windows). |

No orphaned requirements: REQUIREMENTS.md maps exactly ENG-01 to ENG-06 to Phase 2 and each is claimed by a plan.

### Anti-Patterns Found

None. Debt-marker grep (`TBD|FIXME|XXX|TODO|HACK`) over the phase's source and test files returned no matches. No stub, placeholder return or hardcoded-empty value reaches stored output (placeholder settings are a named, flagged, tested constant, stored with `placeholder: true`).

## Findings

| ID | Severity | Finding |
|----|----------|---------|
| F-1 | WARNING (tracker, not code) | `REQUIREMENTS.md` still shows ENG-06 unchecked and "Pending" (lines 29 and 93), and `ROADMAP.md` still shows Phase 2 as `[ ]` with "7/7 plans executed" in the plan list but no completion line; 02-06-SUMMARY says ENG-06 stays Pending until the database tier ran green, and it now has. Update ENG-06, the Phase 2 line and STATE.md when this verification is accepted. I edited none of them (orchestrator-owned). When ENG-06 is ticked, the limits below should travel with it, not only the tick. |
| F-2 | WARNING (scope of the proof) | The ENG-06 database tier proves flow-through and storage on the public fixture with placeholders, locally. It says nothing about live Supabase, the real mapping, real ratings, agreement with PSS/E or an hourly run (see "What it does not prove"). Phase 5 owns the workflow and the live-write gate. |
| F-3 | INFO (wording) | The roadmap says "one new factory argument". It is one keyword (`solver`, default `"psse"`) threaded through five `study.py` entry points and resolved through a registry rather than a literal import, because the existing import-boundary test forbids the laptop job from importing another solver. The owner confirmed this form on 2026-11-20 (02-07-SUMMARY). It meets the intent: the caller passes one plain string, the default is PSS/E, existing tests are unchanged. |
| F-4 | INFO | The Phase 2 database tests were extended by Phase 3 (see the last "does not prove" bullet). They now need the solver-tag migration. A reader checking Phase 2 alone should know the file carries Phase 3 assertions. |
| F-5 | INFO | 02-06-SUMMARY's statement that the database tests "have not run green anywhere" was true when written and is now superseded by this report. Its description of what it did and did not check without a database matches what I found (the tests do exercise CHECK constraints, writer role and completeness checks, which that summary said it could not). |
| F-6 | INFO | The cluster is PostgreSQL 17.12 on Windows. The reference platform for the workstream (the owner's Mac, CI, Supabase) was not exercised. The Phase 2 database tests carry no platform-specific assertions, but the proof is for this platform. |
| F-7 | INFO | The CORPUS_CHRISTI scaling-refusal test has a roughly 0.1 percent chance per run of a false leak failure (a digit-only target text could occur inside the random 8-hex run id). Disclosed in 02-06-SUMMARY; PSS/E's test has the same exposure. It passed here. |

No finding is a BLOCKER.

## Limits that stay attached to this pass

- Database tier: one local throwaway PostgreSQL 17.12 on one Windows machine, public 39-bus fixture, generated placeholder mapping, fake ratings, placeholder solve settings. Not live data, not the real mapping, not Supabase.
- The recorded PSE-02 settings have been run in memory only (truth 5); the combination "recorded settings, real mapping, written to a database" has not been exercised by this phase.
- Not an hourly cloud run. The hourly GitHub Actions workflow is not built; nothing has run on a schedule, in GitHub Actions, or against the live project. This phase does not make any figure available to the dashboard.
- Engineering agreement with PSS/E is not this phase's claim; it is Phase 1 (NET-03, base case) and Phase 4 (replay, with its own limits).
- The database test file now depends on Phase 3's solver-tag migration, which the owner has not applied to the live project.

## Human Verification Required

None required to close this phase. Optional, owner-side: run the same database tier on the owner's Mac or in CI before relying on it there (F-6).

## Gaps Summary

No gaps. All five roadmap success criteria hold against the code and the tests I ran (90 tests of the phase's own files, 0 failed, 0 skipped, plus 72 existing PSS/E tests green). The status is passed with the limits above; the actionable follow-ups are tracker updates (F-1) and keeping the ENG-06 wording honest (F-2).

---

_Verified: 2026-11-24_
_Verifier: Claude (gsd-verifier)_
