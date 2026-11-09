---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 19
subsystem: training-feature-and-rating-label
tags: [b2, projected-wind, rating-config-version, schema-doc, python, pytest]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: "07-04 production callers on city_point.production_city_point; 07-01 snapshot schema 2"
provides:
  - city_training_frame stores the line-perpendicular wind in wind_speed (B2, D-14), so the 07-14 retrain learns the feature serving reads
  - forecast_training_test production expectation on production_city_point, plus test_city_training_frame_stores_projected_wind for all four cities
  - config.RATING_CONFIG_VERSION v2-provisional-2026-11-02 and the schema-doc paragraph "Conductor basis per city (Phase 7)" and DB-06 snapshot-schema-2 sentence
affects: [07-11 (AUSTIN 100 C apply-answers path, now safe), 07-14 retrain, 07-09 late-descriptive gate, 07-17 GO label lift, 07-18 promotion]

actuals:
  tokens: 3000
  tasks: 2
  commits: 2
plan_head_before: 32903c55ff49e78b4b9817f796bc154c5234a9eb
plan_head_after: 9a5f1db35d9d95a5faee42652a47df064f484202

tech-stack:
  added: []
  patterns:
    - "Training frame stores the same projected wind the live archive carries (city_rating._project_wind), computed once as perp and reused for dlr_amps and wind_speed"

key-files:
  created: []
  modified:
    - backend/forecast_training.py
    - backend/tests/forecast_training_test.py
    - backend/config.py
    - docs/data-science/schema/city_rating_v1.md

key-decisions:
  - "B2 is confined to city_training_frame (hunks lie in lines 191-230 of a function spanning 180-258); build_training_matrix, build_ml_features and the COND-02 golden are untouched and green"
  - "RATING_CONFIG_VERSION v2-provisional-2026-11-02 (UTC date of the commit); the word provisional stays, RATING_BASIS unchanged, so is_provisional still reads provisional until 07-17's signed GO"
  - "The 'Conductor basis per city (Phase 7)' text is a bold lead-in paragraph inside the Provisional label section, not a new heading, so the doc's pinned heading list is unchanged"

patterns-established: []

requirements-completed: []

coverage:
  - id: D1
    description: "city_training_frame stores the projected (line-perpendicular) wind in wind_speed; dlr_amps unchanged"
    requirement: REVAL-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_training_test.py#test_city_training_frame_stores_projected_wind"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_training_test.py#test_city_training_frame_uses_own_ampacity"
        status: pass
      - kind: unit
        ref: "backend/tests/cond02_shadow_golden_test.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "forecast_training_test production expectation reads city_point.production_city_point"
    requirement: COND-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_training_test.py#test_city_training_frame_uses_own_ampacity"
        status: pass
    human_judgment: false
  - id: D3
    description: "RATING_CONFIG_VERSION bumped to v2-provisional-2026-11-02 and the schema doc names it, explains the per-city table, snapshot schema 2 and the one-time fingerprint change"
    requirement: COND-01
    verification:
      - kind: unit
        ref: "backend/tests/supabase_schema_doc_test.py#test_doc_quotes_the_current_provisional_labels"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_schema_doc_test.py#test_doc_has_every_required_section_once"
        status: pass
    human_judgment: false

duration: 6min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 19: B2 projected training wind and v2 rating config label Summary

**The ml training frame now stores the line-perpendicular wind that serving reads (B2, D-14), and RATING_CONFIG_VERSION is v2-provisional-2026-11-02 with a schema-doc paragraph explaining the per-city conductor table and snapshot schema 2**

## Performance

- **Duration:** about 6 min (4 min of it the full suite)
- **Started:** 2026-11-02T08:01:33Z
- **Completed:** 2026-11-02T08:07Z
- **Tasks:** 2
- **Files modified:** 4 (0 created)
- **Commits:** 2, measured from `plan_head_before`

## Accomplishments

- `city_training_frame` stores `np.asarray(perp, dtype=float)` in `wind_speed`, the same array that feeds `dlr_amps`; the docstring says the stored value is the projected component, as the live archive and Postgres history carry (`city_rating._project_wind`). No other function changed; `build_training_matrix`, `build_ml_features` and the COND-02 golden are unchanged and pass. No model was trained and `data/models` is untouched (07-14 retrains).
- `forecast_training_test.py` reads its production expectation through `city_point.production_city_point`, which closes 07-04's handoff, so 07-11 can change AUSTIN's conductor without the test going stale. `test_city_training_frame_stores_projected_wind` (parametrized over all four cities) pins `wind_speed == perpendicular_wind(5.0, 90.0, production bearing)` at rtol 1e-9 and that it differs from the measured 5.0 (1.71 m/s for the carried-over bearing).
- `config.RATING_CONFIG_VERSION` is `v2-provisional-2026-11-02`, with a comment recording the v2 change (production reads the per-city table, values unchanged, snapshot schema 2, provisional stays). `RATING_BASIS` is unchanged.
- `docs/data-science/schema/city_rating_v1.md`: the "Provisional label (OD-5)" section names the new version and gains "Conductor basis per city (Phase 7)" (per-city table with a source per value, today the Drake default for every city, provisional until Power Systems answers, a Power Systems value is a config change plus a version bump, earlier rows carry `v1-provisional-2026-10-13`, backfill rows keep their Phase 3 label). "What produced each row (DB-06)" gains the snapshot-schema-2 sentence (fingerprints comparable only within a schema, every live fingerprint changes once at the switch). No heading or other section changed.

## Task Commits

1. **Task 1: B2 projected wind as the training feature (TDD)** - `e4c74b4` (fix)
2. **Task 2: Bump the rating config version and document the per-city conductor basis** - `9a5f1db` (docs)

**Plan metadata:** the docs commit carrying this summary (see git log, `docs(07-19)`).

## TDD

- **RED (Task 1):** `test_city_training_frame_stores_projected_wind` failed for all four cities on the planned assertion (`ACTUAL` 5.0 per row, `DESIRED` 1.710101 for AUSTIN), after the `:287` expectation was switched (still passing). Semantic assessment: the target tests executed and failed on the planned assertion for the planned reason (the frame stored the measured speed), not on collection, import or fixture faults. The machine classifier (`check tdd-red-evidence`) was not run: `workflow.tdd_mode` is off and pytest console output is not a supported report format.
- **GREEN:** one-line change plus docstring; 77 passed across the three verify files.
- **REFACTOR:** none.
- The plan asks for one `fix` commit holding both files, so RED and GREEN are in `e4c74b4` (tests were written and run red first, as the plan's "Tests first" says).

## Decisions Made

- Used the UTC date of the commit (2026-11-02) in the label; the commit landed at about 08:07Z.
- Wrote the "Conductor basis per city (Phase 7)" text as a bold lead-in rather than a heading: `supabase_schema_doc_test` pins the `## ` heading list, and the plan forbids adding or removing headings.

## Deviations from Plan

None - plan executed exactly as written.

Notes (no behavior impact): the commit trailers use this session's attribution (Co-Authored-By: Claude Sonnet 5.5 plus the session link). Both commits were made on `main`, as the sequential dispatch instructed; the agent-branch rule applies to worktree runs only.

**Total deviations:** 0.
**Impact on plan:** none.

## Issues Encountered

None. Task 2's precondition (clean `config.py` and schema doc, so no concurrent Phase 6 edit) held at both the start and immediately before editing.

## Verification

- Task 1 verify (forecast_training, production_conductor, cond02 golden): 77 passed. Task 2 verify (schema doc, rating identity, supabase store, backfill loader): 109 passed, 3 skipped.
- Full suite: 2416 passed, 82 skipped (previous 2412 + the 4 new parametrized cases), golden included.
- `grep -c '"wind_speed": np.asarray(perp, dtype=float)' backend/forecast_training.py` prints 1.
- `git diff --stat e4c74b4^ e4c74b4 -- data/models` is empty; `git status --porcelain data` is empty.
- The Task 1 diff of `forecast_training.py` has two hunks (new lines 191-196 and line 230), both inside `city_training_frame` (def at 180, next def at 260).
- `config.RATING_CONFIG_VERSION` prints `v2-provisional-2026-11-02`; `grep -c "snapshot schema 2"` on the doc prints 1; the Task 2 diff of the doc has 0 removed `-#` lines.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path, file access or schema change. T-07-10 (identity changed without a label change) is mitigated by the v2 label; T-07-38 by the precondition and the two-section edit; T-07-39 by the confined hunks and the COND-02 golden.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready: 07-11 (depends on 07-19) may apply O4 (AUSTIN Drake 100 C) in `PRODUCTION_CONDUCTORS`; the production expectation in `forecast_training_test` now follows the table. That change needs a further `RATING_CONFIG_VERSION` bump with the matching schema-doc edit (supabase_schema_doc_test pins both), per the config comment.
- 07-14 must retrain on the projected wind; the shipped models in `data/models` were trained on measured wind and are unchanged until then. Nothing is pushed: live rows change only after 07-18's owner-approved promotion.
- REVAL-01 is shared with 07-14/17/18 and was not marked complete; COND-01 is not marked here either (07-17's signed GO lifts the label).

## Self-Check: PASSED

- Modified files exist (four FOUND); commits `e4c74b4` and `9a5f1db` are ancestors of HEAD.
- Plan acceptance criteria re-run and passing; full suite green.

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*
