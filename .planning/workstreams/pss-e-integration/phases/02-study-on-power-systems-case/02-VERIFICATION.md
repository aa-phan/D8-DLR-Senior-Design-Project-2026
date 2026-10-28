---
phase: 02-study-on-power-systems-case
verified: 2026-10-28T20:00:00Z
status: human_needed
score: 4/4 must-haves verified
covered_files:
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-01-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-01-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-02-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-02-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-03-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-03-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-04-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-04-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-05-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-05-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-06-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-06-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-07-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/02-study-on-power-systems-case/02-07-SUMMARY.md"
  - "backend/psse_job/contingency.py"
  - "backend/psse_job/dispatch.py"
  - "backend/psse_job/mapping.py"
  - "backend/psse_job/margin.py"
  - "backend/psse_job/probe.py"
  - "backend/psse_job/psse_api.py"
  - "backend/psse_job/settings.py"
  - "backend/psse_job/study.py"
  - "backend/psse_job/violations.py"
  - "backend/tests/psse_fake_psspy.py"
  - "backend/tests/psse_study_job_test.py"
  - "backend/tests/psse_study_test.py"
  - "docs/data-science/decisions/psse_study_definitions.md"
  - "docs/data-science/schema/psse_mapping_example.json"
covered_digest: "v3:sha256:b868775e3424498aea2101373d12bdf3e977b79970f61810e9c0c54679497d42"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Run probe.run_probe on the licensed laptop with the real psspy (first without write_check, then with write_check on a copy of the case), show_identifiers False."
    expected: "Every signature:<name> row PASS (or SKIP only where inspect.signature cannot read the function), including signature:branch_chng_3 and signature:scal_2; column_alignment, circuit_id_padding, option_strings and load_flow PASS; rating_write reads back; scale_load accepted."
    why_human: "The fake psspy was written from the same SURFACE table the adapter uses, so it cannot show that the real psspy has these functions, parameter names, return shapes or option strings. branch_chng_3 is marked UNVERIFIED in psse_api.SURFACE (research A1) and the combined scal_2 form is assumption A13."
  - test: "On the laptop, read one mapped branch with a known flow and compare the rating written (MVA) and one percent-of-rating value with a hand calculation at the case's base kV."
    expected: "Written rating equals sqrt(3) x base kV x amps x bundle / 1000; the MAXPCTRATEA (or MXPCTMVARATA) value is consistent with the flow and that rating."
    why_human: "Unit tests prove the arithmetic and that the case's base kV is the one used (345 and 138 kV cases). They cannot show that PSS/E's branch rating on Power Systems' network is per circuit in MVA as assumed, or that the percent-of-rating option strings exist in the installed version (A2)."
  - test: "An engineer at Power Systems reviews the voltage-margin numbers, the sink buses and the N-1 scope (neighbourhood, 2 hops, at most 200 outages, no transformer or generator outages) on the real case; confirm the eight questions in psse_study_definitions.md."
    expected: "Margins, limits and outage scope accepted, or the defaults changed in the mapping file's study section."
    why_human: "Units, margins and N-1 scope on the real network are engineering judgements. Every default is an assumption, not a decision of Power Systems. The result must not be called a full N-1 study until the scope is agreed."
  - test: "Run the whole study once on the laptop against a real case and measure wall-clock time; choose the interpreter and psycopg pin."
    expected: "Run finishes inside max_runtime_seconds (1500) with the extended margin walk (up to about 80 extra load flows per city) included; the interpreter runs the psse_job code."
    why_human: "Run time on a real case cannot be measured with a fake. The psse_job code has been checked only against Python 3.7 syntax, never run on PSS/E's bundled interpreter, and psycopg 3.3.6 needs Python 3.10 or later."
---

# Phase 2: Study on Power Systems' Case Verification Report

**Phase Goal:** Given the ratings, the job applies them to the mapped branches and produces load-flow, N-1, voltage-margin and dispatched-capacity results, proven on the Mac with a fake `psspy`.
**Verified:** 2026-10-28
**Status:** human_needed
**Re-verification:** No, initial verification

Every roadmap success criterion holds against the real code and tests on the Mac. The phase promised "proven with a fake `psspy`" and no more, and that is what was delivered. What the fake cannot prove (real psspy signatures, units and margins on Power Systems' network, N-1 scope, run time) is listed as human and laptop verification, not as a gap. There are no gaps.

## Goal Achievement

### Observable Truths (ROADMAP success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The city-to-branch mapping is configuration, and a mapped branch missing from the case makes the run fail, recorded, with no study results written | VERIFIED | `mapping.py` parses a JSON file (`json.loads` only, never executed), validates every problem at once and returns the sha256 of the parsed bytes. `study.check_mapping` runs before `apply_ratings` in `prepare_base`, and `StudyFailed("mapping", ...)` follows if there are problems. `test_recorded_mapping_missing_branch` (Postgres) asserts `failed_stage == "mapping"`, row counts `[1, 0, 0, 0]` (one psse_run row, no result rows), mapping and case hashes stored, case file hash unchanged and no `branch_chng_3`, `fnsl` or `save` call on the fake. Also covered: refused placeholder (no psspy call, mapping hash NULL), unreadable mapping, unloadable case. |
| 2 | Ratings reach PSS/E in the units its branch rating expects (amps to MVA at the branch's voltage), and a load flow that does not converge is recorded as a failed run, never written as valid results | VERIFIED (arithmetic and control flow); real-PSS/E acceptance is a human item | `apply_ratings` writes `units.circuit_mva(amps, bundle, kv)` = sqrt(3) x kV x circuit amps / 1000, with kV read from the case's bus table (not hard-coded) and read back to 1e-6 relative; a mismatch is `StudyFailed("apply_ratings")`. `test_units_written_mva_per_city_at_345_kv` and `test_units_follow_case_base_kv_138` pin both values; mixed-kV mappings fail at stage mapping. The convergence rule `classify_solve` accepts only fnsl ierr 0 and solved() 0, never trusts solved() after a failed fnsl, and is tested as a matrix. `solve_base` raises `StudyFailed("load_flow")` for non-convergence, excess mismatch and collapsed voltage. `test_recorded_non_converging_load_flow` (Postgres) asserts stage `load_flow`, "iteration limit exceeded", counts `[1, 0, 0, 0]`, no save. |
| 3 | A converged run records, for each contingency, thermal overloads and voltage violations with the element, limit and amount exceeded; a voltage-stability margin per city; and per-city dispatched capacity (lower of the applied DLR rating and the voltage limit, in amps and MW, saying which one set it) | VERIFIED on the fake network | `contingency.screen` reloads the saved base before each outage, trips one line, solves under the strict rule and calls `violations.thermal_violations` / `voltage_violations` (rows carry `element_id`, `limit_value`, `observed_value`, `exceeded_by`, unit; `non_convergence` and collapsed outages are one row each, other outages still screened; zero outages, more than `contingency.max` and an exhausted budget fail the stage rather than truncate). `margin.city_margin` runs a transfer search (walk plus bisection) with `bounded_by` in base_case, dlr_rating, non_convergence or voltage_criterion; the cap is never a stop (`NoTransferBound` fails the stage); a flat-transfer guard fails the stage rather than invent a limit. `dispatch.build_dispatch_row` computes `dispatched_mva = min(applied, voltage_limit)`, amps via `units.mva_to_circuit_amps`, `dispatched_mw = mva x 0.95`, `limiting_factor` (tie to dlr_rating); PF copy is pinned to `config` by `psse_dispatch_test.py`. `test_tracer_prepare_run_fake_psspy_to_postgres` writes 1 + 4 + 4 + 10 rows into local Postgres, asserts AUSTIN `voltage_stability`, EL_PASO `dlr_rating`, kinds include thermal_overload and voltage_low, and all DDL check queries OK. Zero-violation case (1 + 4 + 4 + 0) is a complete run. The numbers are right for the fake radial network only (see human items). |
| 4 | The Mac test suite against a fake `psspy` passes, covering static fallback, the mapping check, a non-converging load flow, and write-back including a failed run | VERIFIED | Static fallback: `test_written_static_fallback_records_reason`, `test_written_read_failure_still_studies_static`, `psse_ratings_test.py`. Mapping check: `psse_mapping_test.py` (every rule refused, all problems named) and `test_recorded_mapping_missing_branch`. Non-converging load flow: `test_recorded_non_converging_load_flow` and the matrix in `psse_api_test.py`. Write-back incl. failed run: 13 tests in `psse_study_job_test.py` plus Phase 1 `psse_writer_test.py` and `psse_job_test.py`. See the spot-checks below for the runs done here. |

**Score:** 4/4 truths verified (0 present-but-behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/psse_job/mapping.py`, `settings.py` | Validated mapping and settings | VERIFIED | Substantive (278 and 443 lines), wired: `study.prepare_run` calls `mapping.load_mapping`; defaults pinned against the doc by `psse_study_doc_test.py`. |
| `backend/psse_job/psse_api.py` | Only module naming psspy functions, SURFACE table, convergence rule, case-file guard | VERIFIED | `_call` refuses any name or keyword outside SURFACE; `save_case` refuses the protected path; golden `backend/tests/data/psse_call_surface.json` pins the call surface. |
| `backend/psse_job/study.py` | Base, `make_study`, `prepare_run` | VERIFIED | Wired to `contingency`, `margin`, `dispatch`; the temp directory is removed in `finally`; fits `job.run_once`'s `study(selection, context)` seam unchanged. |
| `backend/psse_job/contingency.py`, `violations.py` | N-1 screen | VERIFIED | See truth 3. |
| `backend/psse_job/margin.py`, `dispatch.py` | Margin and dispatch | VERIFIED | See truth 3. |
| `backend/psse_job/probe.py` | Laptop probe | VERIFIED as code; its result on the real psspy is a human item | Catches renamed parameter, missing function, uninspectable signature (SKIP, never PASS), misaligned columns, rating not read back, non-converging case, mapping problems; hides identifiers by default (`psse_probe_test.py`). |
| `backend/tests/psse_fake_psspy.py` | Fake psspy and placeholder case | VERIFIED | Buses 9xxxx only; used by every study test. |
| `docs/data-science/decisions/psse_study_definitions.md` | Definitions, honest scope, questions | VERIFIED | Held equal to the code by `psse_study_doc_test.py` (settings table, worked numbers, stage table, 8 questions). It states what the fake does and does not prove. |
| `docs/data-science/schema/psse_mapping_example.json` | Placeholder mapping | VERIFIED | `"placeholder": true`, fake buses 90001-90032; `load_mapping` refuses it unless `allow_placeholder`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `study.make_study` study callable | `job.run_once` | `study(selection, context)` returning `contract.StudyResults` or raising `StudyFailed` | WIRED | `job.py` is unchanged since d72ce2d; `test_tracer_prepare_run_fake_psspy_to_postgres` drives it end to end. |
| `study.prepare_base` | `check_mapping` before `apply_ratings` | call order | WIRED | No write call reaches the fake on a mapping failure (asserted). |
| `study.make_study` | `contingency.screen`, `margin.city_margin`, `dispatch.build_dispatch_row` | direct calls | WIRED | `dispatch.build_dispatch_row` receives `bounded_by`. |
| `dispatch.POWER_FACTOR_DEFAULT` | `backend/config.py` POWER_FACTOR | drift test | WIRED | `psse_dispatch_test.py` fails on drift; `config.py` itself is untouched. |
| `probe` | `psse_api.SURFACE` | `inspect.signature` per row | WIRED | Allow-list line for `inspect` in `psse_contract_test.py`. |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| psse_dispatched_capacity rows | `voltage_limit_mva` | `margin.city_margin` max `MAXMVA` over mapped branches at the last good point | Yes (from solved load flows) | FLOWING |
| psse_contingency_result rows | `limit_value`, `observed_value` | `api.branch_loading` / `api.bus_table` after each outage solve | Yes | FLOWING |
| psse_run `ratings_used` | rating MVA, kV | `apply_ratings` (case base kV) | Yes | FLOWING |

### Behavioral Spot-Checks and Test Runs

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Non-Postgres PSS/E tests (api, mapping, study, contingency, margin, dispatch, probe, doc, contract, ratings, job) | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider <those files>` | 361 passed, 17 skipped (the skips are the Postgres-backed tests in `psse_job_test.py`, which run under the Postgres command) | PASS |
| Study through `run_once` into local Postgres (13 tests) | `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1`, PATH prefixed, `psse_study_job_test.py` | 13 passed, 0 skipped; no postgres process left running | PASS |
| Full gate (run by the caller before this verification) | the full suite | 521 passed, 0 skipped | accepted as reported; not re-run |

### Probe Execution

Step 7c: the probe `probe.py` is a laptop function with no command-line entry point and needs a psspy module. Its run against the fake is `test_tracer_probe_against_fake_all_pass` (passes, included in the 361 above). No `scripts/*/tests/probe-*.sh` exists. The run against the real psspy is human item 1.

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| IN-02 | Mapping stored as configuration; a missing branch fails the run | SATISFIED | Truth 1 |
| IN-03 | Ratings converted to PSS/E units, conversion tested | SATISFIED on the fake; real-PSS/E units are human item 2 | Truth 2 |
| STU-01 | Load flow with ratings applied; non-convergence is a failed run | SATISFIED | Truth 2 |
| STU-02 | N-1 with thermal and voltage violations (element, limit, amount) | SATISFIED on the fake; scope is human item 3 | Truth 3 |
| STU-03 | Voltage-stability margin per city | SATISFIED on the fake; engineering review is human item 3 | Truth 3 |
| STU-04 | Dispatched capacity, lower of rating and voltage limit, amps and MW, which set it | SATISFIED | Truth 3 |
| TST-01 | Mac tests against a fake psspy | SATISFIED | Truth 4 |

No orphaned requirement: REQUIREMENTS.md maps exactly these seven IDs to Phase 2. The checkboxes and "Pending" status in REQUIREMENTS.md and ROADMAP.md (plans listed unchecked, progress 0/7) have not been updated; that is orchestrator bookkeeping after verification, not a code gap.

### Constraint Checks

| Check | Result |
|-------|--------|
| No real mapping or case file committed | PASS. `git ls-files` has no `*.sav`, `*.raw` or `psse_local/` path; the only mapping JSON is the placeholder example. `.gitignore` adds `/psse_local/`, `*.sav` and `*.raw` (confirmed with `git check-ignore`). Bus numbers in the fake case and example are 90001-90032. |
| Phase 1 files changed only by the two allow-list lines | PASS. Diff d72ce2d..HEAD: only `backend/tests/psse_contract_test.py` changed (`tempfile` for 02-03, `inspect` for 02-07, each with a comment). `job.py`, `ratings.py`, `run_record.py`, `writer.py`, `contract.py`, `constants.py`, `units.py`, `redaction.py` are untouched. |
| Protected paths untouched since d72ce2d | PASS. No diff in `backend/config.py`, `supabase/`, `docs/data-science/schema/psse_results_v1.sql` (the DDL), `psse_results_v1.md`, `psse_results_v1_checks.sql`, or any production-pipeline plan. The only `.planning` change outside this phase's directory is the pss-e-integration `ROADMAP.md` plan listing. |
| `psspy` never imported by the package | PASS. No import of `psspy`, `config`, `pandas`, `numpy` or `requests` in `backend/psse_job/` (contract test passes). |
| No debt markers | PASS. No TBD, FIXME, XXX, TODO or HACK in the phase's files. |
| Python 3.7 syntax | No walrus or f-string found in `psse_job` (grep). Not run on a 3.7 interpreter (human item 4). |

### Anti-Patterns Found

None blocking. Notes (info only, already stated in the definitions note):

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `backend/psse_job/study.py` | The `bounded_by` argument to `build_dispatch_row` is not pinned by a spy test | Info | Dropping it would leave the dlr_rating tripwire unwired and no test would fail. The note says so. |
| `backend/psse_job/study.py` | A failed `fnsl` message still prints a stale `solved=<n>` | Info | Cosmetic; the text says solved() is not trusted. |
| `backend/psse_job/study.py` | The case is hashed first, loaded later | Info | Accepted small gap, stated in the note. |

### Human Verification Required

These are laptop and domain checks that the fake psspy cannot give. They are not gaps; Phase 3 depends on them.

#### 1. Probe against the real psspy

**Test:** `probe.run_probe` on the licensed laptop, first read-only, then with `write_check` on a copy of the case, `show_identifiers` False.
**Expected:** All `signature:` rows PASS (SKIP only where a signature cannot be read), including `branch_chng_3` and `scal_2`; column alignment, circuit id padding, option strings and load flow PASS; the rating write reads back.
**Why human:** The fake was built from the same SURFACE table as the adapter, so agreement between them proves nothing about the real psspy. `branch_chng_3` is UNVERIFIED (A1) and the combined `scal_2` form is assumption A13.

#### 2. Units on a branch with a known flow

**Test:** Compare the rating written and one percent-of-rating value with a hand calculation at the case's base kV.
**Expected:** Rating = sqrt(3) x kV x amps x bundle / 1000 MVA per circuit; the percent-of-rating value is consistent.
**Why human:** Tests prove the arithmetic and that the case's own base kV is used, not that PSS/E's branch rating on Power Systems' network is per circuit in MVA, or that the percent-of-rating option strings exist in the installed version.

#### 3. Margins and N-1 scope on Power Systems' network

**Test:** An engineer reviews the margin numbers, sink buses and outage scope, and answers the eight questions in `docs/data-science/decisions/psse_study_definitions.md`.
**Expected:** Defaults accepted or changed in the mapping file's `study` section.
**Why human:** The margin is a load-transfer search of ordinary load flows labelled `pv_curve`, not a PSS/E PV analysis; the sink buses and the transfer source are assumptions; N-1 covers line outages near the mapped branches only. The output should not be called a full N-1 study until the scope is agreed.

#### 4. Run time and interpreter

**Test:** One full study on a real case with wall-clock time; pick the Python interpreter and `psycopg` pin.
**Expected:** Finishes inside `max_runtime_seconds` (1500) including the extended margin walk; the interpreter runs `psse_job`.
**Why human:** Needs the real case and licence. The budget cannot interrupt a single `fnsl`, so Task Scheduler needs its own limit (Phase 3). `psycopg` 3.3.6 needs Python 3.10 or later; the code has never run on PSS/E's bundled Python.

### Gaps Summary

No gaps. All four roadmap success criteria are met against the code and tests, including the failure paths (mapping, load flow, contingency cap, flat transfer, unbounded transfer, unloadable case, refused placeholder), each of which is one failed run record with no result rows. The status is `human_needed` only because four laptop and domain checks, listed above, cannot be done on the Mac.

---

_Verified: 2026-10-28_
_Verifier: Claude (gsd-verifier)_
