---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 01
subsystem: rating-identity
tags: [conductor-config, golden-test, shadow-isolation, rating-identity, python, pytest]

requires:
  - phase: 04-supabase-store
    provides: rating_identity fingerprint recipe and the Phase 3 backfill identity child
provides:
  - COND-02 golden baseline of the frozen shadow path, captured from a materialized d71c501 tree
  - Per-city production conductor table (PRODUCTION_CONDUCTORS) with a source per value and a strict range-checked resolver
  - city_point.production_city_point (production-only) next to the byte-unchanged shadow city_point
  - Rating identity that fingerprints the production table (snapshot schema 2) and still reproduces the Phase 3 backfill fingerprints
affects: [07-02, 07-03, caller repoint plans, shadow refit plans, REVAL-01 re-run]

actuals:
  tokens: 21000
  tasks: 2
  commits: 3
plan_head_before: 7336d70a28334aa7d9cdc6b4c3fbfefb77c70110
plan_head_after: e6fdeb70d5d52b4eba48727f77429dfa9b20337c

tech-stack:
  added: []
  patterns:
    - "Golden captured from `git archive <commit> backend` in a child process whose PYTHONPATH holds only that copy, with import-path and stray-module guards"
    - "Strict per-city closed-set table plus a parallel sources table and inclusive range table"
    - "Identity resolves the point with getattr(city_point, 'production_city_point', city_point.city_point) so older copies fall back"

key-files:
  created:
    - backend/tests/golden_shadow_capture.py
    - backend/tests/fixtures/golden_shadow_baseline_d71c501.json
    - backend/tests/cond02_shadow_golden_test.py
    - backend/tests/production_conductor_test.py
  modified:
    - backend/config.py
    - backend/city_point.py
    - backend/rating_identity.py
    - backend/tests/rating_identity_test.py

key-decisions:
  - "Legacy identity path: when city_point has no production resolver (Phase 3 copies) rating_config_snapshot emits the schema-1 recipe without PRODUCTION_CONDUCTORS, so the Phase 3 backfill fingerprints still reproduce"
  - "RATING_CONFIG_VERSION not bumped in this plan: the plan did not list it, the fingerprint (schema 2 plus the new table) already changes automatically, and the version label is pinned to the schema doc by supabase_schema_doc_test; bump with the doc edit when callers are repointed or Power Systems values land"
  - "The golden compares float64 digests and fit row counts (research A1), not joblib bytes of refit models"

patterns-established:
  - "Frozen-path guard: test reads git diff --name-only against the baseline commit over an explicit frozen list, with a signed-v4 exemption only for the three evaluation modules"
  - "Negative control inside the golden test (change the Drake max_temp_c, geometry and arms must differ)"

requirements-completed: [COND-01, COND-02]

coverage:
  - id: D1
    description: "COND-02 golden: shadow geometry, arms, fits, collector methods, dev-basis family and the 12 artifact hashes reproduce the d71c501 baseline exactly on the live tree"
    requirement: COND-02
    verification:
      - kind: unit
        ref: "backend/tests/cond02_shadow_golden_test.py#test_shadow_section_is_identical_to_the_baseline"
        status: pass
    human_judgment: false
  - id: D2
    description: "Frozen shadow sources and the 12 artifacts have no diff since d71c501; the golden has power (negative control) and never loads a real artifact"
    requirement: COND-02
    verification:
      - kind: unit
        ref: "backend/tests/cond02_shadow_golden_test.py#test_frozen_sources_are_unchanged_since_baseline"
        status: pass
      - kind: unit
        ref: "backend/tests/cond02_shadow_golden_test.py#test_golden_has_power"
        status: pass
      - kind: unit
        ref: "backend/tests/cond02_shadow_golden_test.py#test_no_real_artifact_is_loaded"
        status: pass
    human_judgment: false
  - id: D3
    description: "Per-city production conductor table with a non-empty source per value, strict resolver (closed set, ranges, missing and extra fields) and production_city_point"
    requirement: COND-01
    verification:
      - kind: unit
        ref: "backend/tests/production_conductor_test.py"
        status: pass
    human_judgment: false
  - id: D4
    description: "Row identity fingerprints the production table per city (field, precision, ordering, adjacency and sources-only edges) and the Phase 3 backfill fingerprints still reproduce"
    requirement: COND-01
    verification:
      - kind: unit
        ref: "backend/tests/rating_identity_test.py"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_phase3_fingerprints_at_the_manifest_commit_equal_the_loaded_backfill"
        status: pass
    human_judgment: false
  - id: D5
    description: "Whether provisional Drake values for every city (D-09) are acceptable until Power Systems answers"
    requirement: COND-01
    verification: []
    human_judgment: true
    rationale: "Owner decision D-09 already made; the table values are provisional by design and need Power Systems' real values, which no test can supply"

duration: ~25min (start time not recorded; estimated from file timestamps)
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 01: Golden shadow baseline and per-city production conductor table Summary

**COND-02 golden of the frozen shadow path captured from a materialized d71c501 tree in a child process, then a per-city production conductor table (Drake 795 ACSR / 75 C / 900 m / current bearings, a source per value) with a range-checked production resolver and a row identity that fingerprints it while the Phase 3 backfill fingerprints still reproduce**

## Performance

- **Duration:** about 25 min (the start time was not captured; estimated from file timestamps)
- **Completed:** 2026-11-02T05:00Z (UTC)
- **Tasks:** 2 (a tracer and a TDD task)
- **Files modified:** 8 (4 created, 4 modified)
- **Commits:** 3 (golden, RED, GREEN), measured from `plan_head_before`

## Accomplishments

- The tracer: `golden_shadow_capture.py --capture` runs `git archive d71c501 backend` into a temp directory and computes the payload in a child process whose PYTHONPATH holds only that copy. The child exits 3 unless `config.__file__` is inside the copy and no other module came from the live backend directory. The committed baseline covers city_point geometry, the truth / raw_forecast / persistence arms, the three shadow fits on a time-shifted fixture, the collector's per-row methods, the dev-basis 9-test family with per-city metrics, and the sha256 of the 12 frozen artifacts (also cross-checked against the blobs committed at d71c501).
- `cond02_shadow_golden_test.py` (12 tests, none skipped) reproduces every section exactly on the live tree, guards the frozen sources with `git diff --name-only d71c501`, proves the golden has power (a changed Drake `max_temp_c` makes geometry and arms differ) and spies that `joblib.load` and `load_correction_model` are never called.
- `config.PRODUCTION_CONDUCTORS`, `_SOURCES`, `_FIELDS`, `_RANGES`, `_SOURCE_PROVISIONAL` and `production_conductor_kwargs_for` (strict KeyError / ValueError contract, inclusive ranges). `city_point.production_city_point` builds the point from the table with `bearing_deg = line_azimuth`. `DEFAULT_CONDUCTOR_CONFIG_KWARGS`, `conductor_kwargs_for` and `city_point.city_point` are untouched (city_point.py diff is 38 added, 0 removed lines).
- `rating_identity` resolves the point with `getattr(city_point, "production_city_point", city_point.city_point)` at call time, fingerprints `PRODUCTION_CONDUCTORS` per city, classifies the new names, and keeps its imports to json, hashlib, config, city_point.

## Task Commits

1. **Task 1 (tracer): golden baseline of the frozen shadow path** - `92a923b` (test)
2. **Task 2: per-city production conductor table, resolver, identity (TDD)**
   - RED - `813d1cb` (test)
   - GREEN - `e6fdeb7` (feat)
   - REFACTOR: none needed

**Plan metadata:** the docs commit that carries this summary (see git log, `docs(07-01)`).

## TDD (Task 2)

- **RED:** `production_conductor_test.py` and the extended `rating_identity_test.py` were committed failing (56 failed, 14 passed). Every failure was an `AttributeError` for a name the task creates (`config.PRODUCTION_CONDUCTORS`, `PRODUCTION_CONDUCTOR_RANGES`, `PRODUCTION_CONDUCTOR_SOURCES`, `PRODUCTION_CONDUCTOR_FIELDS`, `config.production_conductor_kwargs_for`, `city_point.production_city_point`). Semantic assessment: the targeted tests executed and failed because the planned feature is absent, not because of syntax, collection or fixture faults. The machine classifier (`check tdd-red-evidence`) was not run: `workflow.tdd_mode` is false for this project and pytest's console output is not one of the classifier's supported report formats.
- **GREEN:** the table, resolver, production point and identity change; 115 passed, 3 skipped (DB tests) across the five verify files.
- **REFACTOR:** none.

## Files Created/Modified

- `backend/tests/golden_shadow_capture.py` - capture (parent), `--emit-payload` (child), `--check`; payload sections and frozen path lists
- `backend/tests/fixtures/golden_shadow_baseline_d71c501.json` - committed golden: source commit, versions, payload
- `backend/tests/cond02_shadow_golden_test.py` - COND-02 byte-identical proof, frozen-source guard, negative control
- `backend/tests/production_conductor_test.py` - table completeness, sources, resolver edges, provisional parity
- `backend/config.py` - per-city production conductor table, sources, fields, ranges, resolver
- `backend/city_point.py` - `production_city_point`
- `backend/rating_identity.py` - production resolver via getattr, schema 2, new classified names, legacy path
- `backend/tests/rating_identity_test.py` - patches the production table; new identity cases and fallback test

## Decisions Made

- The legacy (Phase 3) identity path emits the schema-1 recipe, see Deviation 1.
- No `RATING_CONFIG_VERSION` bump here (see key-decisions). Flagged for the plan that repoints callers or adopts Power Systems values.
- Callers (`city_rating`, `anomaly_training`, `forecast_training`, `real_data_validation`) still use `city_point.city_point`; repointing is a later plan. Row identity now describes the production table, which equals the Drake point under D-09.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan's unconditional schema 2 and appended name broke the Phase 3 backfill fingerprints**
- **Found during:** Task 2 (GREEN verify)
- **Issue:** Setting `RATING_CONFIG_SNAPSHOT_SCHEMA = 2` and appending `PRODUCTION_CONDUCTORS` to `FINGERPRINTED_CONFIG_NAMES` changed the snapshot for the Phase 3 copies too (`snapshot_schema` and a `PRODUCTION_CONDUCTORS: null` key), so `supabase_load_backfill_test.py::test_phase3_fingerprints_at_the_manifest_commit_equal_the_loaded_backfill` failed against `backfill_parity.json`. The must-have says that test passes and the Phase 3 child still reproduces the backfill rows.
- **Fix:** `rating_config_snapshot` detects the legacy case (`resolve is city_point.city_point`, i.e. no production resolver) and then emits `snapshot_schema` 1 without the `_SCHEMA_2_CONFIG_NAMES`. The constant stays 2 for the live recipe. Added a test that pins the legacy snapshot.
- **Files modified:** backend/rating_identity.py, backend/tests/rating_identity_test.py
- **Verification:** all five verify files pass (115 passed, 3 skipped); full suite 2023 passed, 82 skipped
- **Committed in:** e6fdeb7

**2. [Rule 1 - Plan inconsistency] CORPUS_CHRISTI given AUSTIN's entry cannot change only CORPUS_CHRISTI**
- **Found during:** Task 2 (writing the identity cases)
- **Issue:** The plan expects `{"CORPUS_CHRISTI"}` for that case, but under D-09 the AUSTIN and CORPUS_CHRISTI entries are already identical (same Drake values, both bearing 173.15), so assigning one to the other changes nothing.
- **Fix:** Two cases cover the intent. A parametrized case gives both cities one new shared entry (`max_temp_c` 90.0) and expects `{"AUSTIN", "CORPUS_CHRISTI"}`. A dedicated test makes the entries identical and asserts all four fingerprints stay distinct (the city is part of the snapshot).
- **Files modified:** backend/tests/rating_identity_test.py
- **Committed in:** 813d1cb (RED)

**3. [Rule 3 - Blocking] The collector's cooling method needs the pipeline's enrichment**
- **Found during:** Task 1
- **Issue:** `CoolingCorrectionShadowMethod.predict` on a plain validated row raised `KeyError: 'fcst_perp_wind_ms'`.
- **Fix:** The golden's collector section calls the pipeline's own pure `_enrich_city_frame_for_correction` (anchor values from the fixture row) before the three methods, which is what the live collector does.
- **Files modified:** backend/tests/golden_shadow_capture.py
- **Committed in:** 92a923b

### Other differences from the plan text (no behavior impact)

- The plan asks for one `feat` commit of five files; TDD was followed with a separate RED `test(07-01)` commit (813d1cb) and a GREEN `feat(07-01)` commit (e6fdeb7). The plan's ancestor check passes.
- Commit trailers use this session's attribution (Co-Authored-By: Claude Sonnet 5.5 plus the session link) instead of the plan's literal "Claude Opus 5.5" line, because that line names a model that did not write the commits.
- The capture script adds two guards the plan did not list: the child fails if any module is imported from the live backend directory, and `capture()` checks the artifact hashes against the blobs committed at d71c501.

---

**Total deviations:** 3 auto-fixed (2 Rule 1, 1 Rule 3)
**Impact on plan:** All three were needed for correctness of the stated must-haves. No scope creep.

## Issues Encountered

- The working tree had 116 commits after d71c501 that edit backend modules outside the shadow path (Supabase store, live run, e2e tools). The golden's live-vs-baseline match shows none of them touches the frozen path. The baseline records `captured_from_head` 7336d70.
- The three DB tests in the verify set skipped (they need `DLR_TEST_PG_AUTOSTART=1`); the full suite also skips 82 for the same reason. Not run in this plan.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None. The table values are the intended D-09 provisional values with provisional source strings, not stubs.

## Next Phase Readiness

- Ready: the golden runs in the default suite, so later plans that repoint production callers (`city_rating`, `anomaly_training`, `forecast_training`, `real_data_validation`) and edit the frozen evaluation modules (only after the signed v4) have a byte-identical guard to run against.
- Open for later plans: the `RATING_CONFIG_VERSION` bump with the schema-doc edit, `city_rating_test.py::synthetic_city` gaining a table entry once a caller resolves through `production_city_point`, and Power Systems' real values (a table edit, not a code change).

## Self-Check: PASSED

- Created files exist: golden_shadow_capture.py, golden_shadow_baseline_d71c501.json, cond02_shadow_golden_test.py, production_conductor_test.py (all FOUND).
- Commits are ancestors of HEAD: 92a923b, 813d1cb, e6fdeb7 (all FOUND); the golden commit is an ancestor of the feat commit; the latest `test(07-01)` commit is an ancestor of the latest `feat(07-01)` commit.
- `--check` reports all six sections matching; `shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256` is clean; `git status --porcelain data/shadow` is empty; `git diff --quiet d71c501` over the shadow pipeline, fit models and confirm modules exits 0.
- Task 2 acceptance: `git diff --numstat d71c501 -- backend/city_point.py` shows 38 added, 0 removed; MIDLAND production bearing prints 267.54; `grep -c '"max_temp_c": 75.0,' backend/config.py` prints 5.

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*
