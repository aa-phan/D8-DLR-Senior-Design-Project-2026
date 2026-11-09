---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 04
subsystem: conductor-resolver
tags: [conductor-config, caller-split, ast-test, shadow-isolation, python, pytest]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: "07-01 PRODUCTION_CONDUCTORS table, city_point.production_city_point, COND-02 golden"
provides:
  - Production rating, training and validation callers resolve the conductor through city_point.production_city_point (COND-02 production half)
  - AST caller-split guard (production vs static-only vs shadow modules) and a production-follows-the-table behavior test
  - Synthetic test city with a production table entry and sources
  - Production expectations in the wind-projection, real-data-validation and VAL-02 tests read the production resolver
affects: [07-19 (B2 feature change and v2 label), 07-11 (AUSTIN 100 C config change), shadow refit plans, REVAL-01]

actuals:
  tokens: 5000
  tasks: 2
  commits: 3
plan_head_before: cc48ff72567006a14907ebc814406bf81bbccd3b
plan_head_after: 95e78da065293216c8b83450a9a2c9855770fb45

tech-stack:
  added: []
  patterns:
    - "Caller-split AST test: named tuples PRODUCTION_CALLERS / STATIC_ONLY_CALLERS / SHADOW_MODULES; static-only calls must be the value of a .static_rating attribute"
    - "Behavior pin that production follows a patched table while the shadow Drake conductor does not move"

key-files:
  created: []
  modified:
    - backend/city_rating.py
    - backend/anomaly_training.py
    - backend/forecast_training.py
    - backend/real_data_validation.py
    - backend/tests/city_rating_test.py
    - backend/tests/production_conductor_test.py
    - backend/tests/city_rating_wind_projection_test.py
    - backend/tests/real_data_validation_test.py
    - backend/tests/real_data_validation_val02_test.py

key-decisions:
  - "Docstrings name the production resolver without a call paren so `grep -c 'production_city_point('` reports exactly the plan's 1, 1, 1, 3 call sites"
  - "TDD split into a RED test commit (44e0f74) and a feat commit for the four modules, instead of one six-file feat commit, following the tdd.md commit contract"
  - "No config value, shadow module, schema doc or model changed; forecast_training_test.py:287 and the B2 change stay for 07-19"

patterns-established:
  - "Static-only callers (dlr_orchestrator, supabase_store, supabase_smoke) keep city_point.city_point, enforced by the AST test to be read only for .static_rating"

requirements-completed: [COND-02, COND-01]

coverage:
  - id: D1
    description: "Production rating (city_rating.rate_city), training (forecast_training.city_training_frame, anomaly_training._dlr_amps_for) and validation (real_data_validation, 3 call sites) resolve through production_city_point"
    requirement: COND-02
    verification:
      - kind: unit
        ref: "backend/tests/production_conductor_test.py#test_caller_split"
        status: pass
      - kind: unit
        ref: "backend/tests/production_conductor_test.py#test_production_follows_the_table_and_shadow_does_not"
        status: pass
    human_judgment: false
  - id: D2
    description: "Shadow and frozen-evaluation modules never name production_city_point; COND-02 golden stays green"
    requirement: COND-02
    verification:
      - kind: unit
        ref: "backend/tests/production_conductor_test.py#test_caller_split"
        status: pass
      - kind: unit
        ref: "backend/tests/cond02_shadow_golden_test.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Synthetic test city resolves under the strict production resolver"
    requirement: COND-01
    verification:
      - kind: unit
        ref: "backend/tests/city_rating_test.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Production expectations in wind-projection, real-data-validation and VAL-02 tests read the production resolver and follow a patched table"
    requirement: COND-02
    verification:
      - kind: unit
        ref: "backend/tests/real_data_validation_test.py#test_computed_amps_expectation_follows_production_table"
        status: pass
      - kind: unit
        ref: "backend/tests/city_rating_wind_projection_test.py"
        status: pass
      - kind: unit
        ref: "backend/tests/real_data_validation_val02_test.py"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 04: Production callers on the per-city resolver Summary

**Production rating, training and validation now resolve the conductor through `city_point.production_city_point` (six call sites in four modules), guarded by an AST caller-split test over production, static-only and shadow module lists, with the production-expectation tests switched to the same resolver**

## Performance

- **Duration:** about 8 min (4 min of it the full suite)
- **Started:** 2026-11-02T06:46:30Z
- **Completed:** 2026-11-02T06:53:25Z
- **Tasks:** 2 (both TDD)
- **Files modified:** 9 (0 created)
- **Commits:** 3, measured from `plan_head_before`

## Accomplishments

- `city_rating.rate_city`, `anomaly_training._dlr_amps_for`, `forecast_training.city_training_frame` and the three `real_data_validation` call sites (`computed_amps` and two more) call `production_city_point`; their docstrings name it. `dlr_orchestrator`, `supabase_store` and `supabase_smoke` still call `city_point.city_point` only for `.static_rating`.
- `test_caller_split` (AST) pins the split: each production caller calls `production_city_point` and no `<module>.city_point(...)`; every static-only `city_point()` call is the value of `.static_rating`; the eleven shadow and frozen-evaluation modules contain no name `production_city_point`; `city_point.py` is the only module defining it.
- `test_production_follows_the_table_and_shadow_does_not`: with AUSTIN's `max_temp_c` patched to 100, `rate_city`'s ampacity for a fixed in-band observation rises (1266.3 A before) while `city_point.city_point("AUSTIN")` keeps its 75 C Drake conductor.
- `synthetic_city` gets a `PRODUCTION_CONDUCTORS` entry (Drake values, azimuth 90.0) and a source per field, so the strict resolver accepts it.
- Eight production-expectation lines across the wind-projection, real-data-validation and VAL-02 tests (plus `city_rating_test.py:397`) read `production_city_point`; `test_computed_amps_expectation_follows_production_table` shows the `_record` expectation follows a patched table.

## Task Commits

1. **Task 1: callers, synthetic city, caller-split guard (TDD)**
   - RED - `44e0f74` (test)
   - GREEN - `4aeb533` (feat)
2. **Task 2: production expectations in three test files** - `95e78da` (test)

**Plan metadata:** the docs commit carrying this summary (see git log, `docs(07-04)`).

## TDD

- **RED (Task 1):** `test_caller_split` failed with `city_rating does not call production_city_point`; `test_production_follows_the_table_and_shadow_does_not` failed on `assert 1266.3 > 1266.3` (production ignored the patched table). Semantic assessment: both targets executed and failed on the planned assertion for the planned reason (callers not yet repointed), not on collection, import or fixture faults. The machine classifier (`check tdd-red-evidence`) was not run: `workflow.tdd_mode` is off and pytest console output is not a supported report format.
- **GREEN (Task 1):** four modules repointed; the six verify files pass (173 passed).
- **RED (Task 2):** the new `test_computed_amps_expectation_follows_production_table` failed on `after_record["rating_a"] > before_record["rating_a"]` (1614.9 A equal both times, `_record` still on the Drake resolver) before the expectation lines were switched. The switch and the new test are in one commit (`95e78da`) because Task 2 is test-only.
- **REFACTOR:** none.

## Files Created/Modified

- `backend/city_rating.py`, `backend/anomaly_training.py`, `backend/forecast_training.py`, `backend/real_data_validation.py` - one-line repoints and docstring wording
- `backend/tests/production_conductor_test.py` - `PRODUCTION_CALLERS`, `STATIC_ONLY_CALLERS`, `SHADOW_MODULES`, `test_caller_split`, `test_production_follows_the_table_and_shadow_does_not`
- `backend/tests/city_rating_test.py` - synthetic city table entry and sources; `:397` expectation switched
- `backend/tests/city_rating_wind_projection_test.py`, `backend/tests/real_data_validation_test.py`, `backend/tests/real_data_validation_val02_test.py` - production expectations switched; new follows-the-table test in the validation file

## Decisions Made

- Docstrings were written without a call paren after `production_city_point` so the plan's grep-count acceptance (1, 1, 1, 3) holds.
- RED test commit before the feat commit (see Deviations).
- `PRODUCTION_CONDUCTORS` values are untouched: AUSTIN stays Drake 75 C here; the O4 switch to Drake 100 C lands in plan 07-11.

## Deviations from Plan

### Other differences from the plan text (no behavior impact)

- The plan asks for one `feat` commit of six files for Task 1. A separate RED `test(07-04)` commit (`44e0f74`: `city_rating_test.py`, `production_conductor_test.py`) precedes a `feat(07-04)` commit of the four modules (`4aeb533`), per the `tdd.md` commit contract (07-01 did the same). The plan's acceptance checks (`git log --grep='^feat(07-04): production rating'`, `git diff --quiet C^ C` over the four shadow modules) pass on the feat commit.
- The plan lists `supabase_store.py:547`; the static-only call is now at line 580. The AST test does not depend on line numbers.
- Commit trailers use this session's attribution (Co-Authored-By: Claude Sonnet 5.5 plus the session link).

**Total deviations:** 0 auto-fixed (Rules 1-3); 3 cosmetic differences above.
**Impact on plan:** none; scope as planned.

## Issues Encountered

- `forecast_training_test.py:287` still reads `city_point.city_point` (intentionally left for 07-19). It passes because the production and shadow conductors are identical under the provisional D-09 values; it will need 07-19's switch before the values diverge (07-11).
- The 82 DB-dependent tests are skipped as in the baseline (need `DLR_TEST_PG_AUTOSTART=1`).

## Verification

- Task 1 verify (six files): 173 passed. Task 2 verify (four files): 68 passed.
- Full suite: 2168 passed, 82 skipped (baseline 2165 + the 3 new tests), golden included.
- `grep -c "production_city_point("`: city_rating 1, anomaly_training 1, forecast_training 1, real_data_validation 3.
- `git diff --numstat d71c501 -- backend/city_point.py`: 38 added, 0 removed.
- The four shadow modules show no diff in the feat commit; `git diff --stat` of the Task 2 commit over `backend/config.py data docs` is empty; `git status --porcelain data` is empty.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path, file access or schema change; T-07-09 (shadow modules picking up the production resolver) is mitigated by `test_caller_split` and the COND-02 golden, which passed in every verify run.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready: 07-19 (B2 training-feature change, `forecast_training_test` switch, v2 `RATING_CONFIG_VERSION` label with its schema-doc paragraph) depends on this plan and can proceed.
- Note for 07-11: live rows now follow `PRODUCTION_CONDUCTORS` through rate, train and validate, so the AUSTIN 100 C change should land only after 07-19's label and the `forecast_training_test` switch.

## Self-Check: PASSED

- Modified files exist (all nine FOUND via `git diff --stat`); commits `44e0f74`, `4aeb533`, `95e78da` are ancestors of HEAD; the latest `test(07-04)` RED commit precedes the `feat(07-04)` commit.
- Plan acceptance criteria re-run and passing; full suite green.

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*
