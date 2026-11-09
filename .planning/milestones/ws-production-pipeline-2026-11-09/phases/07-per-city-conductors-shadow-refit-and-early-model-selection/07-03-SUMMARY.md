---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 03
subsystem: model-selection
tags: [refit, ablation, conductor-sensitivity, artifact-integrity, sha256-manifest, veto, python, pytest]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: per-city production conductor table, config.production_conductor_kwargs_for, city_point.production_city_point, the COND-02 golden (plan 07-01)
provides:
  - forecast_conductor_refit - point-explicit refit of ml_cooling_corrected and reference_ml_refit_24h, hashed write to data/models/conductor_refit/<config_version>/, verify-before-load, the headline loader with a served record, production_differs and the D-10 CLI
  - forecast_conductor_ablation - the bracketing-set conductor-invariance re-score (train-only refits in memory) and the pre-registered veto evaluation
  - .gitignore carve-out so data/models/conductor_refit/ is tracked
affects: [07-10 registry check of the ABLATION criteria, 07-11 real ABLATION run, caller repoint plans, REVAL-01 re-run, FRESH read 1 headline loader]

actuals:
  tokens: 29700
  tasks: 2
  commits: 6
plan_head_before: 8d12f1725cf312d921ea2b1e3f3e0d535f642415
plan_head_after: bda99335a2ee4c3c26d685ce4f1c23c40d6ef4a7

tech-stack:
  added: []
  patterns:
    - "Frozen helpers wrapped, never edited: the refit re-implements only the thin point-taking arm5 frame and reuses restrict_to_train_val, assert_no_test_leak, fit_* and predict_arm"
    - "Verify-before-deserialize: refit bytes are hashed and the same bytes are handed to joblib.load; frozen files are hashed against their manifest before load_correction_model"
    - "Subset variants are compared with a matched control restricted to the same cities"

key-files:
  created:
    - backend/forecast_conductor_refit.py
    - backend/tests/forecast_conductor_refit_test.py
    - backend/forecast_conductor_ablation.py
    - backend/tests/forecast_conductor_ablation_test.py
  modified:
    - .gitignore

key-decisions:
  - "load_refit_model hashes the file bytes once and passes those same bytes to joblib.load (BytesIO), so there is no window between the check and the load; frozen artifacts still go through the path-based load_correction_model, a residual window documented in the module docstring"
  - "The refit CLI checks every requested city (and every target path) before fitting any, so a mixed request that includes a Drake-parity city exits 2 with nothing written; an existing target exits 2 with 'refusing to overwrite' rather than a traceback"
  - "A variant that applies to a subset of the requested cities (Drake-75-AUSTIN-163m) is compared with the control restricted to the same cities (a matched control stored in the report); the v4 draft does not say how that comparison is made, so this is flagged for the 07-10 signing review"
  - "A margin that cannot be computed under a variant (insufficient data) vetoes the candidate with a reason; the draft is silent and the conservative reading was taken"
  - "The ranking used for Kendall tau is by pooled MAE on rows where every candidate is scored (ties by name); identical orders return exactly 1.0 instead of a scipy value that could differ in the last bit"

patterns-established:
  - "Spy fixtures that fail a test on any FRESH-dated data/experiment open, any joblib.dump under the real data/shadow/models, or any real frozen-artifact load"
  - "Mutation spot checks on the guards (restriction, hash check, overwrite, fit_end, boundary, sign rules, 3-city line, matched control): each mutant fails a named test"

requirements-completed: [SEL-02, SEL-03]

coverage:
  - id: D1
    description: "Conductor-explicit refit of cooling and reference under a CityPoint, using only rows before 2026-03-17 (asserted on every fitted frame), fit_end honoured, wind never refit"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_fit_for_point_fits_only_rows_before_the_split"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_anchor_reaching_the_split_after_restriction_raises"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_fit_end_restricts_the_rows_fit"
        status: pass
    human_judgment: false
  - id: D2
    description: "Hashed artifact store: writes only under data/models/conductor_refit/<version>/ with a manifest, refuses wind, overwrite, unsafe versions and the frozen directory (including a symlink), and the new location is tracked"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_write_refit_writes_artifacts_and_a_verifiable_manifest"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_refit_dir_refuses_the_frozen_directory"
        status: pass
      - kind: other
        ref: "git check-ignore -q data/models/conductor_refit/v-test/ARTIFACT_HASHES.sha256 (exit 1)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Verify-before-load for refit and frozen artifacts (a flipped byte, a missing entry or manifest raises ArtifactIntegrityError and joblib.load is not called) and the headline loader's served record"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_a_flipped_byte_raises_and_joblib_load_is_not_called"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_headline_loader_checks_the_frozen_hash_before_loading"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_headline_loader_serves_refit_cooling_and_reference_and_frozen_the_rest"
        status: pass
    human_judgment: false
  - id: D4
    description: "D-10 refusal: the CLI exits 2 with the D-10 message for a Drake-parity city and makes no file; production_differs sees a conductor or bearing change"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_conductor_refit_test.py#test_cli_refuses_a_parity_city_with_the_d10_message_and_makes_no_file"
        status: pass
      - kind: other
        ref: "PYTHONPATH=backend .venv/bin/python backend/forecast_conductor_refit.py --cities AUSTIN --root $(mktemp -d) (exit 2)"
        status: pass
    human_judgment: false
  - id: D5
    description: "ABLATION re-score: bracketing set values, boundary edge (train <= 2025-09-01T18:00Z, validation 2025-09-02..2026-03-16) with the 2,360/784 per-city assertion, wind fit once per city, cooling and reference fit on train only, nothing written"
    requirement: SEL-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_conductor_ablation_test.py#test_split_puts_the_boundary_rows_on_the_right_side"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_ablation_test.py#test_wind_is_fit_once_per_city_and_cooling_reference_fit_on_train_only"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_ablation_test.py#test_run_ablation_returns_variant_reports_metrics_ranks_and_tau"
        status: pass
      - kind: other
        ref: "counts-only check on the four real cached frames: train 2360 and validation 784 for every city (rows before 2026-03-17, no prediction computed)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Veto evaluation on unrounded margins: raw and wind sign flips, the 3-of-4 line, positive-to-0.0, Kendall tau, unavailable margins, matched control for the AUSTIN-only variant"
    requirement: SEL-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_conductor_ablation_test.py#test_a_positive_margin_changing_to_exactly_zero_counts_as_a_sign_flip"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_ablation_test.py#test_crossing_the_three_of_four_line_vetoes_in_both_directions"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_conductor_ablation_test.py#test_signs_come_from_unrounded_values"
        status: pass
    human_judgment: false
  - id: D7
    description: "Whether the veto criteria, the matched-control handling of the AUSTIN-only variant and the unavailable-margin-vetoes reading are what the owner intended"
    requirement: SEL-03
    verification: []
    human_judgment: true
    rationale: "The criteria are pre-registered in the signed v4 and checked against its registry in 07-10; two readings here (matched control, unavailable margin) fill gaps the text leaves, which only the owner or the 07-10 review can settle"

duration: 22min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 03: Conductor refit driver and ABLATION invariance driver Summary

**A one-command, hash-verified refit of the cooling and reference candidates under any explicit conductor point (refused while a city is at Drake parity, never touching data/shadow/models), and the ABLATION driver that refits on train in memory, scores validation under six bracketing conductors and evaluates the pre-registered veto on unrounded margins, both tested on fixtures only.**

## Performance

- **Duration:** about 22 min
- **Started:** 2026-11-02T05:09:58Z
- **Completed:** 2026-11-02T05:33Z (approximately; written at SUMMARY time)
- **Tasks:** 2 (both TDD)
- **Files modified:** 5 (4 created, 1 modified)
- **Commits:** 6 measured from `plan_head_before`, of which 4 are this plan's code commits (RED and GREEN for each task). The other 2 are orchestrator commits that landed on main while this plan ran: `fbe3948` (owner's v4 signature) and `fe200d2` (07-02 close-out). The SUMMARY commit follows.

## Accomplishments

- **Refit driver (SEL-02).** `fit_for_point` fits `ml_cooling_corrected` and `reference_ml_refit_24h` for one city under an explicit `CityPoint` through the frozen recipe (`restrict_to_train_val`, `assert_no_test_leak` on the loaded frame, the exact-lead frame and the reference frame), with an optional `fit_end`. `write_refit` writes only `data/models/conductor_refit/<config_version>/<method>_<CITY>.joblib` plus an `ARTIFACT_HASHES.sha256` manifest in sha256sum format, all-or-nothing and never over an existing file; it refuses `ml_wind_corrected` ("reused, never refit (SEL-02)"), unsafe versions (separators, `..`, odd characters) and any root that is or resolves inside `SHADOW_MODEL_DIR`, symlinks included.
- **Verify before load (T-07-07).** `load_refit_model` and the headline loader compare sha256 with the manifest before deserializing and raise `ArtifactIntegrityError` on a tampered byte, a missing entry, a missing or malformed manifest or a missing refit file, without calling `joblib.load`. The headline loader serves refits for `refit_cities x REFIT_METHODS` and frozen artifacts (checked against `data/shadow/models/ARTIFACT_HASHES.sha256`) for the rest, and `loader.served` records city, method, path, sha256 and source for the FRESH report. A missing frozen file stays a `FileNotFoundError`, which the evaluator reads as candidate unavailable.
- **D-10 refusal.** `production_differs` compares the production point with the frozen Drake point. The CLI exits 2 with the D-10 message for a parity city (checking every requested city before any fit), exits 0 with "nothing to refit" when `--cities-from-production-diff` finds no differing city, and prints `<CITY> <method> n_rows_fit=<n> <path> <sha256>` per refit.
- **ABLATION driver (SEL-03).** `BRACKETING_SET` carries the six registered variants (Drake-75 control, Drake-100, Falcon-90, Suwannee-150, Suwannee-200, Drake-75-AUSTIN-163m for AUSTIN only) with values matching the signed registry rows. `run_ablation` fits wind once per city on train under the control point, cooling and reference on train under each variant (`fit_end=TRAIN_END`, in memory), recomputes truth, raw and persistence under each variant, and returns per-variant family reports, per-city and pooled metrics, metrics relative to mean truth, rank order, Kendall tau against the control and margins over raw in A and percent. `split` asserts the boundary and the 2,360/784 per-city counts, naming the city and both counts on a miss. `veto` implements the three clauses plus `ranking_invariant`; `write_report` writes `ablation.json` and `ablation.md` (plain-English summary first) into a new directory and refuses the frozen one.
- **Real-frame count check.** Counts only, on the four cached `_2024-01-20_2026-09-29_` frames restricted to rows before 2026-03-17: 2,360 train and 784 validation exact-lead rows for every city, so the constants are right. No prediction or error was computed on real data; the real ABLATION run is 07-11.
- **Tracking carve-out.** `!/data/models/conductor_refit/` in `.gitignore` (new directory and files report not ignored; `data/models/other.joblib` is still ignored).

## Task Commits

1. **Task 1: Conductor refit driver (TDD)**
   - RED - `858ea22` (test)
   - GREEN - `45dd87d` (feat; module, tests and `.gitignore`)
2. **Task 2: ABLATION driver and veto (TDD)**
   - RED - `887aed3` (test)
   - GREEN - `bda9933` (feat)

**Plan metadata:** the docs commit that carries this summary (`docs(07-03)`).

## TDD

- **RED (both tasks):** the test files were committed with the module absent, so every run stopped at `ModuleNotFoundError` for `forecast_conductor_refit` / `forecast_conductor_ablation` at collection. Semantic assessment: this is the feature being absent, but it is a collection-level failure, not an assertion on planned behavior, so strictly it is the INVALID_RED class (`fixture_or_load_failure`) the reference warns about. The machine classifier (`check tdd-red-evidence`) was not run: `workflow.tdd_mode` is false for this project, pytest console output is not a supported report format, and a new module has no earlier shape to fail against. To compensate, the guards were checked by mutation after GREEN (below).
- **GREEN:** refit test file 57 passed; ablation test file 52 passed; with the golden, 121 passed. The full suite passed (2165 passed, 82 skipped, the skips being DB tests that need `DLR_TEST_PG_AUTOSTART=1`).
- **REFACTOR:** none.
- **Mutation spot checks after GREEN (each mutant failed a named test, source restored byte-identical):** restriction removed, hash check removed (refit and frozen), overwrite allowed, `fit_end` ignored (refit and ablation), train boundary `<` and validation boundary `>`, zero-sign rounding, positive-to-zero treated as no flip, wind clause removed, 3-city line moved to 2, matched control ignored, tau ignored, wind refit per variant.

## Files Created/Modified

- `backend/forecast_conductor_refit.py` - refit, hashed write, verify-before-load, headline loader, `production_differs`, CLI
- `backend/tests/forecast_conductor_refit_test.py` - 57 tests with spies for FRESH-dated opens, frozen-directory writes and real artifact loads
- `backend/forecast_conductor_ablation.py` - bracketing set, `variant_point`, `split`, `candidate_errors`, `run_ablation`, `veto`, `write_report`, CLI
- `backend/tests/forecast_conductor_ablation_test.py` - 52 tests (catalogue, split edges, count edges, run on the shifted fixture, veto cases, report files, isolation)
- `.gitignore` - tracking carve-out for `data/models/conductor_refit/`

## Decisions Made

See key-decisions. Two are open for review rather than settled: the matched control for the AUSTIN-only variant and the "unavailable margin vetoes" reading (D7).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Refit CLI checked cities and target paths only as it went**
- **Found during:** Task 1 (writing the CLI tests)
- **Issue:** Following the plan literally, a request such as `--cities AUSTIN MIDLAND` with only AUSTIN differing would refit and write AUSTIN, then exit 2 on MIDLAND, leaving a partial refit; an existing artifact would surface as a traceback.
- **Fix:** `main` checks every city for Drake parity and every target path for existence before fitting anything, and turns `refit_dir` and existing-target refusals into exit 2 with a message.
- **Files modified:** backend/forecast_conductor_refit.py
- **Verification:** `test_cli_checks_every_city_before_fitting_any`, `test_cli_does_not_overwrite_an_existing_refit`, `test_cli_refuses_an_unsafe_version_and_the_frozen_directory`
- **Committed in:** 45dd87d

**2. [Rule 2 - Missing critical] Refit load had a window between the hash check and the load**
- **Found during:** Task 1
- **Issue:** Hashing the file and then calling `joblib.load(path)` leaves a window in which the file could be replaced after the check.
- **Fix:** read the bytes once, hash them, and `joblib.load` the same bytes (`BytesIO`). The behavior the plan lists (tamper raises, `joblib.load` not called) is unchanged. The frozen path keeps the path-based loader and its documented residual window.
- **Files modified:** backend/forecast_conductor_refit.py
- **Verification:** `test_a_flipped_byte_raises_and_joblib_load_is_not_called`, `test_a_real_fitted_refit_round_trips_and_predicts`
- **Committed in:** 45dd87d

**3. [Rule 2 - Missing critical] A subset variant cannot be compared with an all-city control**
- **Found during:** Task 2
- **Issue:** `Drake-75-AUSTIN-163m` applies to AUSTIN only, so its pooled margins are over one city while the control's are over four; comparing signs across those is not a like-for-like test of conductor invariance.
- **Fix:** such a variant is compared with the control restricted to the same cities (`matched_control` in the report, used by `veto` and by the tau). The rule's wording is otherwise applied literally, so on one city the "at least 3 cities" clause can never change.
- **Files modified:** backend/forecast_conductor_ablation.py
- **Verification:** `test_the_austin_only_variant_is_scored_for_austin_against_a_matched_control`, `test_a_subset_variant_is_compared_with_its_matched_control`
- **Committed in:** bda9933

### Other differences from the plan text (no behavior impact)

- The plan asks for one `feat` commit per task; TDD was followed with a separate RED `test(07-03)` commit before each GREEN `feat(07-03)` commit, as in plan 07-01.
- Commit trailers use this session's attribution (Co-Authored-By: Claude Sonnet 5.5 plus the session link) instead of the plan's literal model line.
- `write_manifest` and `_manifest_key` are part of the module's surface beyond the plan's list (the manifest key is repo-relative, or absolute outside the repo, which is what the temp-directory tests use).
- Added `report["skipped_variants"]`, per-variant `caveat`, `rank_basis` and `cities_favoured_over_wind` fields to the ABLATION report; the plan's required content is all present.

---

**Total deviations:** 3 auto-fixed (all Rule 2)
**Impact on plan:** All three tighten a stated must-have (no duplicate or partial refit, verify before deserialize, like-for-like veto). No scope creep; no frozen file changed.

## Issues Encountered

- The v4 protocol was signed by the owner while this plan ran (`fbe3948`, with one change: AUSTIN to Drake at 100 degrees C). This plan did not read the signing copy. The ABLATION design section of the draft is unchanged by that commit (checked by diff of the non-signing document), and every constant and the six variant definitions match the registry rows in that document. The signed O4 change means that once the production table adopts AUSTIN at 100 degrees C, `production_differs("AUSTIN")` becomes true and the refit CLI will refit AUSTIN; nothing in this plan edits the table.
- An early mutation-check script used GNU `sed -i` on macOS and printed errors; those mutants were re-run with Python replacements. The mutated source was restored byte-identical each time (verified by `diff`), and the final test run is from the restored files.
- The full-suite skips (82) are DB tests needing `DLR_TEST_PG_AUTOSTART=1`; not run here.

## Verification results

- `pytest backend/tests/forecast_conductor_refit_test.py backend/tests/cond02_shadow_golden_test.py`: 69 passed. With the ablation tests: 121 passed. Full suite: 2165 passed, 82 skipped.
- `git check-ignore -q data/models/conductor_refit/v-test/ARTIFACT_HASHES.sha256` exits 1 (tracked).
- `PYTHONPATH=backend .venv/bin/python backend/forecast_conductor_refit.py --cities AUSTIN --root "$(mktemp -d)"` exits 2 with the D-10 message.
- `grep -c "def make_headline_loader\|def load_refit_model\|class ArtifactIntegrityError"` prints 3; the bracketing-set names print in the registered order.
- `git diff --quiet d71c501 -- backend/forecast_shadow_fit_models.py backend/forecast_experiment.py backend/forecast_shadow_confirm.py` exits 0; `git diff --quiet -- data/shadow/models` exits 0; `git status --porcelain data/shadow` is empty; `shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256` is clean.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Threat Flags

None. The new surface (a CLI that writes under `data/models/conductor_refit/`, and loaders that deserialize joblib files) is the one the plan's threat register covers (T-07-06, T-07-07, T-07-08) and is mitigated and tested.

## Next Phase Readiness

- Ready: 07-10 can check the ABLATION criteria against the signed registry (the constants already match); 07-11 can run `forecast_conductor_ablation.py` on the real frames (counts already confirmed) and, if a city's production conductor differs by then, `forecast_conductor_refit.py --cities-from-production-diff`. `make_headline_loader(...).served` is the hook for the FRESH report's scored-artifact list.
- Open: owner or 07-10 review of D7 (matched control, unavailable-margin veto). The production table still holds Drake for every city, so the refit CLI refuses until the AUSTIN 100 degrees C value is applied.
- Not done here by design: no refit artifact exists yet, the real ABLATION has not been run, and no FRESH or TEST figure was computed or read.

## Self-Check: PASSED

- Created files exist: `backend/forecast_conductor_refit.py`, `backend/forecast_conductor_ablation.py`, `backend/tests/forecast_conductor_refit_test.py`, `backend/tests/forecast_conductor_ablation_test.py` (all FOUND).
- Commits are ancestors of HEAD: `858ea22`, `45dd87d`, `887aed3`, `bda9933` (all FOUND); each RED commit is an ancestor of its GREEN commit.
- No unexpected deletions in any task commit; STATE.md, ROADMAP.md and REQUIREMENTS.md were not touched by this plan.

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*
