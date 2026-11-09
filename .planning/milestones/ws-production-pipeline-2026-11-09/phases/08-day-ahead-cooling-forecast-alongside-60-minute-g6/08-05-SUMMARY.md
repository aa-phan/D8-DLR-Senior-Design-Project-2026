---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
plan: 05
subsystem: infra
tags: [day-ahead, preflight, manifest, sha256, github-actions, warning-tier, pytest]

requires:
  - phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
    provides: day_ahead_forecast.serving_model_path and make_model_loader, day_ahead_band.BAND_ARTIFACT_PATH and load_verified_band, the hashed band artifact (08-01)
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: the refit and frozen cooling artifacts and their manifests
provides:
  - dlr_live_check_models day-ahead tier (required_day_ahead_artifacts, check_day_ahead, DAY_AHEAD_KINDS) that reports problems as non-fatal ::warning:: lines
  - data/models/LIVE_ARTIFACT_HASHES.sha256 with 13 entries (8 live, 4 cooling, 1 band)
  - offline tests that fail hard on any committed day-ahead manifest/file mismatch
affects: [08-06, 08-07, 08-08, 08-09, 08-10, 08-11, 08-12]

actuals:
  tokens: 9000
  tasks: 2
  commits: 2
plan_head_before: 2cb4da8624366207793dc77448852332b533b640
plan_head_after: bb824507d733ba2694ee632e938d5768c31df4ee

tech-stack:
  added: []
  patterns:
    - "Non-fatal verification tier: the exit code is fixed from the safety-relevant artifacts first, then a second tier runs under one Exception+SystemExit guard and can only print warnings"
    - "Workflow-command escaping (%, CR, LF) for every message that reaches a ::warning:: line"
    - "Lazy imports inside functions to break the dlr_live_check_models / forecast_conductor_refit cycle"

key-files:
  created:
    - backend/tests/dlr_live_check_models_day_ahead_test.py
  modified:
    - backend/dlr_live_check_models.py
    - backend/tests/dlr_live_check_models_test.py
    - data/models/LIVE_ARTIFACT_HASHES.sha256

key-decisions:
  - "The band is strict-loaded from the path in the artifact list (load_verified_band(path=..., manifest_path=...)) rather than its default path, so the checked file and the loaded file are always the same one"
  - "A strict-load failure of one day-ahead file is its own warning line (one per file); only an exception that escapes check_day_ahead is turned into a single 'day-ahead check failed: <Type>' warning by the guard"
  - "The manifest header text is left unchanged (only its date moves), so the eight live lines and the header wording stay byte-identical to Phase 5"

patterns-established:
  - "Tier tests parametrise the failure site (import, list, path resolver, loader factory, band loader, sys.exit) and assert the exit code with and without a live-model problem"

requirements-completed: [DAY-02, DAY-04]

coverage:
  - id: D1
    description: "A day-ahead problem (tampered, missing or unlisted file, failing load, crash anywhere in the tier including sys.exit) is only a ::warning:: line and the pre-flight exits 0; live-model problems still exit 1"
    requirement: "DAY-04"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_warn_tamper_never_stops_the_ratings_and_never_loads"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_tier_crash_cannot_change_the_exit_code"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_tier_crash_with_a_live_problem_still_exits_one"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_live_problem_stays_fatal_with_healthy_day_ahead_files"
        status: pass
    human_judgment: false
  - id: D2
    description: "Hash before load: nothing day-ahead is unpickled while a day-ahead hash problem is open; warning text is escaped onto one line"
    requirement: "DAY-04"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_warn_tamper_never_stops_the_ratings_and_never_loads"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_warning_text_is_escaped_onto_one_line"
        status: pass
    human_judgment: false
  - id: D3
    description: "One manifest names all 13 artifacts; the four cooling hashes equal the refit and frozen manifests; the eight live entries are unchanged; the committed tree matches offline and the real pre-flight prints both OK lines in a fresh process"
    requirement: "DAY-02"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_committed_day_ahead_files_match_the_committed_manifest"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_cooling_hashes_equal_the_refit_and_frozen_manifests"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_the_eight_live_entries_are_unchanged"
        status: pass
      - kind: integration
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_full_preflight_in_a_fresh_process_prints_both_ok_lines_and_no_warning"
        status: pass
    human_judgment: false
  - id: D4
    description: "No circular import in either order with forecast_conductor_refit; Phase 5 check-model tests keep every assertion"
    requirement: "DAY-04"
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_day_ahead_test.py#test_import_order_has_no_circular_import"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_test.py"
        status: pass
    human_judgment: false

duration: 9min
completed: 2026-11-08
status: complete
---

# Phase 8 Plan 05: Day-Ahead Artifacts in the Live Manifest Summary

**The live pre-flight now verifies the four served cooling files and the band artifact (hash before any unpickling) as a warning-only tier under one Exception/SystemExit guard, and the committed manifest lists all 13 artifacts, so the eight live models stay fatal and a day-ahead problem can never stop live ratings.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-11-08T10:12Z
- **Completed:** 2026-11-08T10:21Z
- **Tasks:** 2
- **Files modified:** 4 (1 created, 3 edited)

## Accomplishments

- `dlr_live_check_models.main` fixes its exit code from the eight live models exactly as in Phase 5, then runs the day-ahead tier (lazy imports, artifact list, check, printing) inside one guard that catches `Exception` and `SystemExit` (not `KeyboardInterrupt`). A caught exception becomes one escaped `::warning title=day-ahead artifact::day-ahead check failed: <Type>: <text>` line. Verified for six failure sites, each with healthy live models (exit 0) and with a live-model problem (exit 1).
- Hash before load: `check_day_ahead` strict-loads the cooling models through `day_ahead_forecast.make_model_loader()` (the hash-checking headline loader) and the band through `load_verified_band` only when presence and sha256 found nothing open. The tamper tests assert both load spies stay empty.
- Warning text is escaped (`%` to `%25`, CR to `%0D`, LF to `%0A`) so a message cannot read as a workflow command.
- `write_manifest` hashes both lists, sorts by path, refuses (writes nothing) when any file of either list is missing; "Wrote N entries" counts both.
- `data/models/LIVE_ARTIFACT_HASHES.sha256` regenerated: the eight live lines are byte-identical (only the header date changed from 2026-11-02 to 2026-11-08), plus the AUSTIN refit cooling file (`31fe8d9b...`), the three frozen cooling files (`8f50c799...`, `cdd0a2c9...`, `f64f9872...`) and the band (`19b9c522...`, recomputed independently with `shasum` before pinning). No artifact file changed.
- `PYTHONPATH=backend python backend/dlr_live_check_models.py` on the real tree exits 0, strict-loads the real models and prints both OK lines with no warning. This also means 08-04's child can now find its band entry in the live manifest.
- Full suite with local Postgres: 2863 passed (2830 after 08-04, plus 33 new).

## Task Commits

1. **Task 1: day-ahead artifact list and the non-fatal warning tier** - `87b30cd` (feat)
2. **Task 2: regenerate the live manifest and fail hard offline on any day-ahead mismatch** - `bb82450` (feat)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Notes

Both tasks carry `tdd="true"` but the plan is `type: execute` and `workflow.tdd_mode` is not enabled, so the RED/GREEN gate is advisory; the plan prescribes one `feat(08-05)` commit per task, so there are no separate `test(08-05)` commits.

- **Task 1 RED:** the new test file was run before the implementation: 26 failed on missing behavior (`AttributeError` for `required_day_ahead_artifacts`/`_escape_workflow_data`/`DAY_AHEAD_KINDS`, and the tier lines absent from `main`'s output); the 2 import-order tests passed, as nothing had changed yet. GREEN: after the implementation all 101 tests in the four plan files passed.
- **Task 2 RED:** the five committed-tree tests were run before the manifest was regenerated: all 5 failed on the missing day-ahead manifest entries. GREEN: after `--write-manifest`, 52 passed across the three verify files.

## Files Created/Modified

- `backend/dlr_live_check_models.py` - `DAY_AHEAD_KINDS`, `required_day_ahead_artifacts`, `check_day_ahead`, shared manifest/hash helpers, the guarded warning tier in `main`, `write_manifest` over both lists, docstring
- `backend/tests/dlr_live_check_models_day_ahead_test.py` - 33 tests: all_ok, warn_tamper, warn_missing_entry, live_still_fatal, escaping, tier_crash (12 parametrised), writer, import_order, committed_match, cross_manifest, live_unchanged, band_default, full_preflight
- `backend/tests/dlr_live_check_models_test.py` - only the autouse fixture `_live_models_only` added (no line removed)
- `data/models/LIVE_ARTIFACT_HASHES.sha256` - 13 entries

## Decisions Made

- The band is loaded from the path in the artifact list, not the function default, so the file that was hashed is the file that is loaded.
- A failed load of one file is its own warning line; only an exception that escapes `check_day_ahead` becomes the single "day-ahead check failed" warning.
- The manifest header wording is unchanged so the eight live lines and the header stay as in Phase 5 apart from the date.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Import-failure test named the wrong exception type**
- **Found during:** Task 1 (GREEN run)
- **Issue:** the plan expects `monkeypatch.setitem(sys.modules, "day_ahead_forecast", None)` to give `ImportError`; Python raises `ModuleNotFoundError` (an `ImportError` subclass), and the warning correctly names that real type, so my first assertion on the string "ImportError" failed.
- **Fix:** the test expects `ModuleNotFoundError`; the implementation was right.
- **Files modified:** backend/tests/dlr_live_check_models_day_ahead_test.py
- **Verification:** `-k tier_crash` 12 passed
- **Committed in:** 87b30cd

---

**Total deviations:** 1 auto-fixed (1 test expectation). **Impact on plan:** none on behavior.

### Notes (no code change)

- `test_the_eight_live_entries_are_unchanged` reads the pre-plan manifest with `git show e0a00a9e...` (the last commit that touched the manifest, recorded as a constant). It skips only when that commit is not in the checkout (a shallow clone); it ran and passed here.
- The 13-entry manifest is committed but not pushed. Promoting these artifacts to live CI is part of the owner-approved push in 08-08.

## Issues Encountered

None.

## Known Stubs

None.

## Threat Flags

None. The new surface (strict load of the day-ahead files, warning text on stdout) is covered by T-08-14, T-08-15, T-08-16 and T-08-35 in the plan's threat model.

## User Setup Required

None. Nothing was pushed, and the live Supabase project and live job were not touched.

## Next Phase Readiness

- Ready for the next wave plan. The live manifest names the band path 08-04's child reads, so real child runs no longer refuse every target with "no entry in the manifest".
- The `.github/workflows/dlr_live.yml` pre-flight run line is unchanged; exit 1 still comes only from the eight live models.

## Self-Check: PASSED

- Files present: `backend/dlr_live_check_models.py`, `backend/tests/dlr_live_check_models_day_ahead_test.py`, `backend/tests/dlr_live_check_models_test.py`, `data/models/LIVE_ARTIFACT_HASHES.sha256`.
- Commits `87b30cd` and `bb82450` are ancestors of HEAD; `git rev-list --count 2cb4da8..HEAD` = 2.
- Acceptance: verify commands pass (101 passed for Task 1 files; 52 passed for Task 2 files; real pre-flight exits 0 with both OK lines and no `::warning`); `-k tier_crash` 12 passed; `grep -c "def check_day_ahead"` = 1; zero removed lines in `dlr_live_check_models_test.py`; manifest has 13 entries and 1 band line; `git status --porcelain data/shadow/models data/models/conductor_refit` prints nothing.
- Full suite with `DLR_TEST_PG_AUTOSTART=1`: 2863 passed.

---
*Phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6*
*Completed: 2026-11-08*
