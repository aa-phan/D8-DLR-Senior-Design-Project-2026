---
phase: 04-supabase-store-writer
plan: 11
subsystem: database
tags: [postgres, supabase, backfill, fingerprint, de-duplication, gap-closure]
gap_closure: true
gap_ids: [G-04-2]

requires:
  - phase: 04-supabase-store-writer
    provides: "04-10 (redact(limit=...), supabase_store.finite and file_sha256 used by the loader) and 04-03 (the backfill loader and the Phase 3 fingerprint child)"
provides:
  - "prepare_rows keeps the first computed row of a city and UTC instant, and the first fallback row only when every row of the slot is a fallback row; kept rows stay in file order"
  - "backend/rating_identity.py: the DB-06 identity recipe (snapshot schema, fingerprinted and unfingerprinted config names, rating-path modules, source files, canonicalization, fingerprint) with standard-library, config and city_point imports only"
  - "supabase_store re-exports every identity name unchanged"
  - "The Phase 3 fingerprint child loads rating_identity from live code and config, city_point and thermal_model from the materialized copies, refuses any other live backend module, and never imports supabase_store"
  - "A failing child surfaces its whole stderr, redacted, with the first and last lines kept past 4000 characters"
affects: [07 re-validation (config changes no longer break the backfill identity re-run), 05 scheduled runner, 04-12]

actuals:
  tokens: 8800
  tasks: 2
  commits: 4
plan_head_before: 8dce7685eed7f740cb089703ed2fdee937297c24
plan_head_after: 85996bd5666cf6c52cb46547c020a439c3e1eb0c
commits: 4

tech-stack:
  added: []
  patterns:
    - "Rank-then-mark de-duplication: a stable sort on a class flag, keep-first duplicate mark over the ranking, mark mapped back to the original index so file order is kept"
    - "An isolated child may import only a module whose dependency set the older sources also satisfy; the child proves it by listing every module loaded from the live backend directory"
    - "Redact the whole text first, then cut to head and tail, so the last line of a traceback is never lost"

key-files:
  created:
    - backend/rating_identity.py
  modified:
    - backend/supabase_load_backfill.py
    - backend/supabase_store.py
    - backend/tests/supabase_load_backfill_test.py
    - backend/tests/rating_identity_test.py

key-decisions:
  - "The identity block moved to rating_identity.py byte-for-byte (comments and order kept); supabase_store imports the names at the top of the module with the other imports instead of mid-module, so build_rating_row still resolves rating_config_fingerprint through supabase_store's globals"
  - "A child stderr longer than 4000 characters keeps its first 1000 and last 3000 characters of the redacted text instead of redact(limit=4000) alone, because a plain cut would drop the exception line at the bottom of a traceback"
  - "The child lists every module loaded from the live backend directory (not only the names it imported), so a transitive import is caught too"

patterns-established:
  - "A Phase 3 identity child depends on one live module whose imports are a subset of what the Phase 3 sources provide"

requirements-completed: [DB-03, DB-06]

coverage:
  - id: D1
    description: "WR-04: for one city and UTC instant the loader keeps the first computed row, the first fallback row only when all rows are fallback, counts the rest in duplicates_dropped and keeps file order; the kept fallback-then-computed row equals the row data_cleaning.clean_history keeps usable"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_same_slot_keeps_the_first_computed_row_before_any_fallback_row"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_backfill_keeps_the_row_the_cleaning_step_keeps_usable"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_same_hour_duplicates_keep_the_first_row_and_are_counted"
        status: pass
    human_judgment: false
  - id: D2
    description: "WR-05: the recipe lives in rating_identity.py (stdlib, config, city_point only), supabase_store re-exports every name as the same object, and every live fingerprint is unchanged"
    requirement: "DB-06"
    verification:
      - kind: unit
        ref: "backend/tests/rating_identity_test.py#test_store_reexports_the_identity_recipe"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_fingerprint_child_imports_only_the_identity_module_from_live_code"
        status: pass
      - kind: unit
        ref: "backend/tests/rating_identity_test.py#test_fingerprint_is_hex_per_city_and_stable_across_processes"
        status: pass
      - kind: unit
        ref: "backend/tests/rating_identity_test.py#test_each_rating_assumption_changes_only_its_citys_fingerprint"
        status: pass
    human_judgment: false
  - id: D3
    description: "WR-05/DB-06: the Phase 3 child survives a config that lacks names a live module reads at import, refuses another live backend module, and at the committed manifest commit returns exactly the four fingerprints in backfill_parity.json"
    requirement: "DB-06"
    verification:
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_phase3_fingerprints_survive_a_config_missing_names_live_modules_read_at_import"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_the_fingerprint_child_refuses_another_live_backend_module"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_phase3_fingerprints_at_the_manifest_commit_equal_the_loaded_backfill"
        status: pass
    human_judgment: false
  - id: D4
    description: "WR-05: a failing child surfaces its whole stderr, redacted (first and last lines both present, a planted connection URL replaced by REDACTED, a very long stderr keeps both ends)"
    requirement: "DB-06"
    verification:
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_a_failing_fingerprint_child_surfaces_its_whole_redacted_stderr"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_a_very_long_child_stderr_keeps_its_first_and_last_lines"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-10-23
status: complete
---

# Phase 4 Plan 11: Backfill de-duplication and fingerprint-child gap closure (G-04-2, WR-04 and WR-05) Summary

**The backfill loader now keeps the first computed row of a slot (the archive's and the cleaning step's rule), and the Phase 3 fingerprint child evaluates a new standard-library-and-config-only `rating_identity` module instead of the live store, so a Phase 7 config change cannot break the identity re-run and a child failure shows its whole redacted stderr.**

## Performance

- **Duration:** about 8 min of agent time (first commit 22:07:33Z, last code commit 22:12:20Z, plus reading and SUMMARY)
- **Started:** 2026-10-23T22:05:00Z (approximate)
- **Completed:** 2026-10-23T22:12:20Z (last code commit)
- **Tasks:** 2 (both TDD, RED then GREEN)
- **Files modified:** 5 (432 insertions, 143 deletions), one of them new

## Accomplishments

- WR-04: `prepare_rows` ranks computed rows ahead of fallback rows with a stable sort, marks duplicates on (city, UTC instant) keep-first over that ranking, maps the mark back to the original index and drops those rows, so the kept rows stay in file order. A fallback row followed by a computed row for one slot now loads the computed row, the same row `data_cleaning.clean_history` keeps usable. The docstring and comment state the rule and its source (`historical_archive.append_observation`, the cleaning step's `duplicate` flag).
- WR-05 root cause: the Phase 3 child imported the live `supabase_store`, which pulls in `ampacity_forecast`, `historical_archive` and `ercot_dlr_merger`; `ercot_dlr_merger` reads `config.LINE_VOLTAGE_KV` and `config.POWER_FACTOR` at import, so any live module that reads a config name the Phase 3 `config.py` lacks breaks the re-run. The recipe now lives in `backend/rating_identity.py` (imports `json`, `hashlib`, `config`, `city_point` only). The child imports `config, city_point, thermal_model, rating_identity`, keeps the materialized-copy check, and exits 3 naming any other module loaded from the live backend directory.
- `supabase_store` imports the seven identity names from `rating_identity`, so `supabase_store.rating_config_fingerprint` is the same function object and `build_rating_row` is untouched. `file_sha256`, `FORECAST_ARTIFACT_PATHS`, `FORECAST_METHODS_WITHOUT_ARTIFACT` and `model_identity` stay in the store.
- WR-05 diagnostics: a non-zero child status raises `ValueError("could not evaluate the Phase 3 config fingerprints: ...")` with the whole stderr, redacted before any cut, and the first and last lines kept past 4000 characters.
- The four Phase 3 fingerprints recomputed after the move, at the manifest's git head `175b32b` (older `config.py` without `DB_HISTORY_WINDOW_DAYS`, `RATING_BASIS` and `RATING_CONFIG_VERSION`), equal the four `config_fingerprint` values in `docs/data-science/decisions/supabase_store/backfill_parity.json` (AUSTIN `a47b92e4...`, CORPUS_CHRISTI `33de6fc4...`, EL_PASO `9a064f9c...`, MIDLAND `deaf0733...`). The live fingerprints are also identical before and after the move (checked against the pre-move `supabase_store.py` at `8dce768`).

## Findings: commit and failing-first evidence

| Finding | Commits | Failing-first evidence |
|---|---|---|
| WR-04 (Task 1) | `db8ca5c` test (RED), `1cdaa2a` fix (GREEN) | `test_same_slot_keeps_the_first_computed_row_before_any_fallback_row[fallback_then_computed]` failed on `assert austin_01[0]["rating_amps"] == kept` with `1825.0 == 1300.0`, and `test_backfill_keeps_the_row_the_cleaning_step_keeps_usable` failed with `assert 1825.0 == 1300.0` against the `clean_history` usable row. The other three orders passed on the old code (they were already correct). Result `2 failed, 3 passed`. After GREEN: 14 passed, 3 skipped (env-gated live tests) in the loader test file. |
| WR-05 (Task 2) | `2f27cd1` test (RED), `85996bd` fix (GREEN) | Five of six new tests failed on the old code: `test_fingerprint_child_imports_only_the_identity_module_from_live_code` on `assert 'import config, city_point, thermal_model, rating_identity' in <old child>`; `test_phase3_fingerprints_survive_a_config_missing_names_live_modules_read_at_import` with `ValueError: ... AttributeError: module 'config' has no attribute 'LINE_VOLTAGE_KV'` (the live store's import graph failing in the child); `test_a_failing_fingerprint_child_surfaces_its_whole_redacted_stderr` on `assert 'Traceback (most recent call last)' in <message holding only the last line>`; `test_the_fingerprint_child_refuses_another_live_backend_module` on `assert wider != original` (the old child has no such import to widen); `test_store_reexports_the_identity_recipe` with `ModuleNotFoundError: No module named 'rating_identity'`. The sixth, `test_phase3_fingerprints_at_the_manifest_commit_equal_the_loaded_backfill`, passed on the old code and the new code: it is the pin that proves no fingerprint value moved, not a defect test. It ran (not skipped): commit `175b32b` is in this repository. `test_a_very_long_child_stderr_keeps_its_first_and_last_lines` was added with the GREEN commit (it covers the head-and-tail cut). |

RED evidence is pytest console output, which `gsd check tdd-red-evidence` has no adapter for (TAP, JUnit, swift-testing and unittest only), so the classifier was not run. Semantic assessment by inspection: each target test executed and failed on the planned assertion for the intended reason, with nothing failing on collection or fixtures (the new-module test imports `rating_identity` inside the test body so its absence fails that test only).

## Task Commits

1. **Task 1 (WR-04): backfill de-duplication keeps the first computed row of a slot** - `db8ca5c` (test, RED), `1cdaa2a` (fix, GREEN)
2. **Task 2 (WR-05): the Phase 3 fingerprint child no longer loads the live store's import graph** - `2f27cd1` (test, RED), `85996bd` (fix, GREEN)

**Plan metadata:** committed separately as `docs(04-11): complete backfill de-duplication and fingerprint-child gap-closure plan`, then the state and roadmap commit.

## Files Created/Modified

- `backend/rating_identity.py` (new) - the DB-06 identity recipe, content and order unchanged from `supabase_store.py`, module docstring stating the import constraint.
- `backend/supabase_store.py` - the identity block replaced by a comment; the seven names imported from `rating_identity` with the other imports; module docstring points at the new module.
- `backend/supabase_load_backfill.py` - computed-first de-duplication and docstring; `_FINGERPRINT_CHILD` rewritten; `RATING_CONFIG_SOURCE_FILES` read from `rating_identity`; `_redacted_head_and_tail` and `_CHILD_STDERR_MAX_CHARS`; module docstring updated.
- `backend/tests/supabase_load_backfill_test.py` - WR-04 orders and cleaning cross-check; WR-05 static, behavioral, refusal, stderr (short and long) and manifest-commit pin tests; `ast` use and a `data_cleaning` import.
- `backend/tests/rating_identity_test.py` - `test_store_reexports_the_identity_recipe`.

## Decisions Made

- The recipe moved verbatim, so no fingerprint input, key name, JSON option or hash changed (DB-06 prohibition); the parity pin and the existing stability and sensitivity tests prove it.
- The re-export import sits at the top of `supabase_store.py` with the other imports rather than where the block was; the behavior is the same and it avoids a mid-module import and its lint exception.
- Head-and-tail trimming for very long child stderr instead of a plain `redact(limit=4000)`, so the exception line survives (see Deviations).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A plain `redact(stderr, limit=4000)` would drop the last line of a long traceback**
- **Found during:** Task 2 GREEN (designing the stderr surface)
- **Issue:** The plan says to redact with `limit=4000` and the truth says the first and last lines surface. A cut at 4000 characters keeps the first lines and loses the exception line at the bottom of a traceback longer than 4000 characters, which is the line a reader needs.
- **Fix:** `_redacted_head_and_tail` redacts the whole text first (so the cut still comes after redaction and no secret can pass), then keeps the first 1000 and last 3000 characters when the text exceeds 4000, joined by `[...]`. Added `test_a_very_long_child_stderr_keeps_its_first_and_last_lines`.
- **Files modified:** `backend/supabase_load_backfill.py`, `backend/tests/supabase_load_backfill_test.py`
- **Verification:** loader test file 20 passed, 3 skipped; the redaction test still replaces the planted URL.
- **Committed in:** `85996bd` (part of the GREEN commit)

### Notes (no behavior change)

1. **Commit split for TDD tasks.** The plan names one commit per task. Both tasks are `tdd="true"`, so each has a `test(04-11)` RED commit first (4 commits, not 2). The GREEN messages are the ones the plan names.
2. **Co-Authored-By line.** The plan text names `Claude Opus 5.5`; the harness attribution reminder names `Claude Sonnet 5.5`, which matches the model that ran, so the commits carry that (same choice as 04-10).
3. **Commits on `main`.** The plan ran sequentially on the main working tree as dispatched (worktree isolation was degraded), so the per-agent branch allow-list in the executor protocol does not apply; no commit touched anything outside the five plan files, and the pre-existing unrelated working-tree changes were never staged.
4. **Pin test passed before the change.** `test_phase3_fingerprints_at_the_manifest_commit_equal_the_loaded_backfill` was green on the old code by design (the old child could still load the older config at `175b32b`); the plan lists it as a pin, not a failing-first test.

**Total deviations:** 1 auto-fixed (Rule 1), 4 notes. **Impact on plan:** none beyond the added long-stderr test; no scope added.

## Issues Encountered

- None blocking. `.planning/config.json` and other unrelated files have pre-existing uncommitted changes that were not touched or staged. The loader was never run against any real database; the live-local tests used the throwaway Postgres (`DLR_TEST_PG_AUTOSTART=1`).

## Known Stubs

None.

## Threat Flags

None. T-04-43 (a fallback row loaded over a computed row) is covered by the four-order test and the `clean_history` cross-check; T-04-44 (fingerprint drift from the move) by the content-identical move, the `backfill_parity.json` pin test, the unchanged stability and sensitivity tests, the re-export identity test and a before/after comparison of the live fingerprints; T-04-45 (stderr disclosure) by redacting the whole text before the cut and the planted-URL test; T-04-46 (child executing unexpected live modules) by the module-listing refusal (exit 3) and the unchanged `python -I`. No new endpoint, auth path or schema change.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- G-04-2 findings WR-04 and WR-05 are closed. The remaining review findings belong to the sibling gap-closure plans.
- Phase 7 can add config names that live modules read at import time without breaking `phase3_config_fingerprints`. A later change to `rating_identity.py` must keep its imports to the standard library, `config` and `city_point` (the module docstring and the static test say so).
- No stored value, fingerprint or loaded row changed; the committed archive had 0 duplicates, so the fix applies to future loads only.

## Verification Results

- Task 1 verify (`supabase_load_backfill_test.py`): 14 passed, 3 skipped (env-gated live tests) at the GREEN commit.
- Task 2 verify 1 (`supabase_load_backfill_test`, `rating_identity_test`, `supabase_store_test`, `supabase_migration_test`): 93 passed, 3 skipped before the long-stderr test was added; the loader file alone then ran 20 passed, 3 skipped. The three skips are the pre-existing live-Postgres tests that need `DLR_TEST_PG_AUTOSTART=1`. The manifest-commit pin test ran and passed (not skipped).
- Task 2 verify 2 (`DLR_TEST_PG_AUTOSTART=1`: `supabase_load_backfill_test`, `supabase_live_test`, `supabase_orchestrator_test`): 79 passed, 0 skipped.
- Task 2 verify 3, full suite `pytest -q -p no:cacheprovider`: 1549 passed, 48 skipped, 0 failed (1537 passed at the end of 04-10; the 12 new tests are this plan's).
- `grep -n "import config, city_point, thermal_model, rating_identity" backend/supabase_load_backfill.py` matches (line 193); `grep -n "from rating_identity import" backend/supabase_store.py` matches (line 57); `grep -n "first computed row" backend/supabase_load_backfill.py` matches the `prepare_rows` docstring (line 274).

## TDD Gate Compliance

RED (`test(04-11)`) precedes GREEN for both tasks (`db8ca5c` before `1cdaa2a`, `2f27cd1` before `85996bd`). The GREEN commits use `fix` as the plan specified rather than `feat`. No separate REFACTOR commit was needed.

---
*Phase: 04-supabase-store-writer*
*Completed: 2026-10-23*

## Self-Check: PASSED

- Files exist: `backend/rating_identity.py` (created) and the four modified files, all listed in `git diff --name-only 8dce768 HEAD`.
- Commits `db8ca5c`, `1cdaa2a`, `2f27cd1`, `85996bd` are ancestors of HEAD; `git rev-list --count 8dce768..HEAD` = 4 (matches `commits:`).
- Acceptance criteria re-checked: the fallback-then-computed case and five of the six WR-05 tests failed first and pass; the pin test ran and passed; the three greps as stated; all three Task 2 verify commands exit 0.
