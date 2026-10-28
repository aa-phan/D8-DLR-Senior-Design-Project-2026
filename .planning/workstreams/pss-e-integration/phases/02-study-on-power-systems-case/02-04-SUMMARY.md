---
phase: 02-study-on-power-systems-case
plan: 04
subsystem: psse-job-contingency-screen
tags: [pss-e, n-1, contingency, thermal, voltage, non-convergence, stdlib, python37]
requires:
  - phase: 01
    provides: "run_record.MAX_CONTINGENCY_ROWS, finite and validate_results; contract.StudyFailed and CONTINGENCY_COLUMNS; the 3.7 syntax and import gate"
  - phase: 02
    provides: "plan 02-02 PsseApi (load_case, set_status, solve, bus_table, branch_loading) and the fake psspy; plan 02-03 BaseCase, Budget, prepare_base and cleanup_base"
provides:
  - "psse_job.violations (pure): voltage_limits, thermal_violations, voltage_violations, non_convergence_row, city_maps"
  - "psse_job.contingency: ContingencyResult, select_outages, screen"
  - "backend/tests/psse_contingency_test.py: 23 tests (STU-02 against the fake psspy)"
affects: [02-06, 02-07]
tech-stack:
  added: []
  patterns:
    - "reload base.saved_path before every outage and once more at the end; never un-trip and re-solve"
    - "classify an outage from SolveResult.converged and a collapse guard over the monitored buses; non-convergence is a row, infrastructure limits are stage failures"
    - "pure row builders keyed by CONTINGENCY_COLUMNS; every details float through run_record.finite"
key-files:
  created:
    - backend/psse_job/violations.py
    - backend/psse_job/contingency.py
    - backend/tests/psse_contingency_test.py
  modified: []
key-decisions:
  - "A thermal observed value is computed as rating x pct / 100, in the same operation order as the limit (rating x limit_pct / 100), so a loading exactly at the limit percentage is exactly at the limit and is never a violation"
  - "non_convergence details.solved is recorded only when fnsl returned 0; after a failed fnsl solved() is stale, so it is None (the hand-off note of plan 02-03)"
  - "voltage rows record the limit source actually used (details.source is 'config' when a case pair was unusable and the configured pair was applied)"
  - "a NaN voltage at a monitored in-service bus counts as collapsed, as in the base load-flow guard"
requirements-completed: [STU-02]
duration: 40min
completed: 2026-10-28
status: complete
commits: 3
plan_head_before: 7ff718fae446cdecfde9d1bda5c8af3a394ff6ff
plan_head_after: b0f28fde046a7df3537b5ea25a68bdcfc2a50d74
actuals:
  tokens: 10400
  tasks: 3
  commits: 3
---

# Phase 2 Plan 04: N-1 branch-outage screen Summary

**`contingency.screen(base)` trips each in-service line of the study area on a freshly reloaded base, solves it under the strict convergence rule and returns one row per thermal overload (branch, MVA), voltage violation (bus, pu) or non-converging outage, all accepted by Phase 1's `validate_results`; an empty, oversized or over-budget screen fails the stage instead of being truncated.**

## Accomplishments
- `violations.py` (pure, no psspy): thermal rows with limit = rating x thermal_limit_pct / 100 on the first rate set and observed = pct / 100 x rating; voltage rows against configured or case limits (case pair used only when two finite positive values with low below high, else the configured pair); `in_base_case` and `base_value` in `details`; `non_convergence_row`; `city_maps` (a bus used by two cities belongs to neither).
- `contingency.py`: `select_outages` (neighbourhood or all, extras resolved to the case orientation, sorted, deduplicated; zero or above `contingency.max` fails) and `screen` (budget check, reload, trip, solve, classify, evaluate; row cap read from `run_record` at call time; final reload so the working case is the solved base again).
- Placeholder case with the default radial solver: 16 outages, 7 contingencies with rows, 10 rows, exactly the plan's expectations (AUSTIN observed 750.6 MVA on circuit 2, voltage_low 0.869474 at the sink with `in_base_case` true and `base_value` 0.934737, city set only for mapped branches and their buses).

## Task Commits
1. Task 1 (tracer): `76ea78b` feat(02-04): tracer - N-1 screen of the placeholder case with thermal and voltage rows that validate_results accepts
2. Task 2: `3127bf9` test(02-04): violation evaluation edge by edge (11 tests)
3. Task 3: `b0f28fd` test(02-04): outage loop - scope, caps, budget, non-convergence rows and reload before every outage (11 tests)

## Verification
- `psse_contingency_test.py -k tracer`: 1 passed. `-k violation`: 11 passed (plan minimum 10). `-k outage`: 11 passed (plan minimum 11). Whole module: 23 passed (plan minimum 22).
- `psse_contract_test.py psse_api_test.py psse_study_test.py psse_contingency_test.py`: 113 passed. Wider psse suite (`+ psse_mapping_test psse_job_test psse_ratings_test psse_writer_test psse_run_record_test`): 351 passed, 28 skipped (Postgres-backed; no Postgres needed by this plan, none started).
- Own-changes gate over the protected paths (study.py, psse_fake_psspy.py, config.py, supabase/migrations, production-pipeline plans, the DDL file and its doc): exits 0 before the tracer and Task 3 commits; neither study.py nor the fake nor any Phase 1 file was touched.
- Mutation checks (each turned the named test red; the files were restored byte-for-byte and `git diff` on `backend/psse_job/` was empty afterwards; a control run of the same five tests in the same stripped environment was green): truncate at the cap instead of failing (test_outage_row_cap_fails_never_truncates); drop the reload before an outage (test_outage_reload_before_every_outage); report a non-converged outage as no rows (test_outage_non_converged_row); `observed >= limit` (test_violation_thermal_exact_limit_is_not_a_violation); swap the voltage_low sign (test_violation_voltage_low_high_distance). Harness: `scratchpad/mutate_0204.py`.

## Deviations from Plan

### Auto-fixed Issues
None.

### Notes (choices inside the plan's latitude, not deviations of behaviour)
- **Only the tracer test was run red first.** Task 1's test was run before any implementation and failed at import (`cannot import name 'contingency'`). `violations.py` and `contingency.py` were written whole in Task 1 (the tracer is the full screen, not a stub), so the Task 2 and Task 3 tests were first run against finished code and passed, apart from one bug in a test of mine (a 0.91 pu bus is not low against the configured 0.90, fixed in the test). The five mutation checks above are the evidence those tests can fail. The Task 3 commit therefore contains tests only; `contingency.py` needed no change after the tracer.
- **Eleventh violation test:** `test_violation_city_maps` was added beyond the plan's ten (`city_maps` shared-bus rule).
- **`details.solved` is None after a failed fnsl** (the plan lists the key; the value is withheld because `solved()` is stale there). With `ierr` 0 and a non-zero `solved()` the code is recorded.
- **A collapsed outage's `details.meaning`** reads "collapsed voltage solution; met convergence tolerance", so the text is not read as success.
- **The outaged line is excluded twice over:** the `skip_key` rule and the out-of-service rule (the case reports the tripped line as status 0). The pure test `test_violation_thermal_skips_zero_rating_nan_tripped_and_out_of_service` proves `skip_key` on an in-service flow; the loop test `test_outage_outaged_branch_not_evaluated` proves no branch row names its own contingency.
- **Bash and tooling:** one no-op empty heredoc was attempted by mistake (it wrote nothing). My mutation harness, run with a stripped environment, made a stray untracked `%SystemDrive%/` directory in the repo root (Windows cache files); it was removed with `rm -rf` of that one path, nothing tracked was affected.
- STATE.md, ROADMAP.md and REQUIREMENTS.md were not updated, per the user's rules; `.planning/config.json`, `milestone.lock` and `state.json` remain uncommitted.

## Known Stubs
None.

## Threat Flags
None. The module adds no filesystem, network or auth surface; it reads only through `base.api` and reloads the private temp file of plan 02-03. T-02-17 to T-02-21 are mitigated and each has its named test.

## Hand-off notes for later plans
- `screen(base)` returns `ContingencyResult(rows, n_contingencies, outages)`; rows are dicts keyed by `CONTINGENCY_COLUMNS` without `run_id` and `run_outcome`. `n_contingencies` is the number of outages screened; the number "with results" (plan 02-06) is the count of distinct `contingency_id` in `rows`.
- The caller owns the base: call `study.cleanup_base(base)` on every exit path. `screen` leaves the working case reloaded to the solved base, so the transfer search (plan 02-05, same wave) can start from it, though it must still reload `base.saved_path` before each step.
- Failures are `StudyFailed("contingency", ...)`: no outage selected, more outages than `contingency.max`, more rows than `run_record.MAX_CONTINGENCY_ROWS`, budget exceeded, a failed reload, trip or read (`outage <key>: <meaning>`).
- Base-case violations are written and flagged `details.in_base_case`; `details.base_value` carries the base observation (open question 6 is not resolved here).

## Self-Check: PASSED
- FOUND: backend/psse_job/violations.py, backend/psse_job/contingency.py, backend/tests/psse_contingency_test.py
- FOUND commits: 76ea78b, 3127bf9, b0f28fd (each an ancestor of HEAD); measured `git rev-list --count` from the ledger base is 3
