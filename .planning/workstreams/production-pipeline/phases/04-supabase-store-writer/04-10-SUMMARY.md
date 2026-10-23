---
phase: 04-supabase-store-writer
plan: 10
subsystem: database
tags: [postgres, supabase, redaction, run-log, helpers, gap-closure]
gap_closure: true
gap_ids: [G-04-2]

requires:
  - phase: 04-supabase-store-writer
    provides: "04-07 (supabase_store.py connection handling) and 04-08 (dlr_orchestrator.py exit and cleaning-error handling) that this plan builds on"
provides:
  - "supabase_store.redact(text, secrets=None, limit=300): the cut is a parameter, default unchanged"
  - "build_run_row stores up to 1000 characters of redacted error text per city, as its docstring says"
  - "provider-error keys are redacted at 1000 characters and keys that become equal after redaction keep the sum of their counts (build_run_row and the orchestrator)"
  - "supabase_store.finite (public) and supabase_store.file_sha256 are the only value-hygiene and file-hash helpers; the loader has no copies and reads no private store name"
affects: [05 scheduled runner (05-03 calls redact(str(exc))), 06 read view (06-04, 06-05), 04-11, 04-12]

actuals:
  tokens: 4640
  tasks: 2
  commits: 4
plan_head_before: ea32e68fc51ca9068d808c6af9411f17534ff666
plan_head_after: d9a0d31a65b5d645309a036404655aacc1f70023
commits: 4

tech-stack:
  added: []
  patterns:
    - "Redact first, cut second: a longer limit is only ever applied to text that has already passed redact()"
    - "Row shaping in one place: the orchestrator hands raw provider-error deltas to build_run_row, which redacts, cuts and merges them"
    - "A repo-wide AST scan test (no `supabase_store._x` outside the store) keeps cross-module private access from returning"

key-files:
  created: []
  modified:
    - backend/supabase_store.py
    - backend/dlr_orchestrator.py
    - backend/supabase_load_backfill.py
    - backend/tests/supabase_run_log_test.py
    - backend/tests/supabase_orchestrator_test.py
    - backend/tests/supabase_load_backfill_test.py

key-decisions:
  - "redact() keeps its 300-character default so every existing caller (Phase 5 and 6 plans call redact(str(exc))) is unchanged; only the run-log error text and provider-error keys opt into 1000"
  - "Colliding provider-error keys are summed; a non-numeric value cannot be added, so the last one seen wins (documented in _redact_keys)"
  - "The orchestrator no longer redacts provider-error keys itself: build_run_row is the single place where the run row is redacted, cut and merged"

patterns-established:
  - "Public store helpers (file_sha256, finite) are what other modules import; underscore names stay private to supabase_store.py"

requirements-completed: [DB-02, DB-03, DB-04]

coverage:
  - id: D1
    description: "IN-01: redact() takes a limit (default 300) and a run-row error keeps up to 1000 characters of redacted text; a secret at character 600 is redacted before the cut"
    requirement: "DB-04"
    verification:
      - kind: unit
        ref: "backend/tests/supabase_run_log_test.py#test_redact_limit_defaults_to_300_and_can_be_raised"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_run_log_test.py#test_run_row_error_text_keeps_up_to_1000_characters"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_store_test.py#test_redact_removes_urls_key_values_and_env_secrets"
        status: pass
    human_judgment: false
  - id: D2
    description: "IN-01: distinct provider-error keys both survive, keys equal after redaction and the 1000-character cut keep the sum of their counts, and the orchestrator run row carries every count"
    requirement: "DB-02"
    verification:
      - kind: unit
        ref: "backend/tests/supabase_run_log_test.py#test_provider_error_keys_that_collide_after_redaction_keep_their_total"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_orchestrator_keeps_every_provider_error_count_for_a_city"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_orchestrator_test.py#test_run_row_classifies_ok_degraded_and_error_with_per_city_provider_counts"
        status: pass
    human_judgment: false
  - id: D3
    description: "IN-04: the loader has no sha256_file, uses supabase_store.file_sha256 and supabase_store.finite, and no backend module other than the store reads an underscore attribute of supabase_store; the archive hash and run id are unchanged"
    requirement: "DB-03"
    verification:
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_loader_reuses_the_store_helpers_instead_of_copies"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_loader_refuses_an_archive_that_does_not_match_the_manifest"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_load_backfill_test.py#test_rows_map_to_city_rating_columns_with_backfill_labels"
        status: pass
    human_judgment: false

duration: 5min
completed: 2026-10-23
status: complete
---

# Phase 4 Plan 10: Run-log and helper gap closure (G-04-2, IN-01 and IN-04) Summary

**`redact()` gained a `limit` so the run log really keeps 1000 characters of redacted error text and sums provider-error counts whose keys collide, and the backfill loader now uses the store's public `file_sha256` and `finite` instead of a copy and a private import.**

## Performance

- **Duration:** about 5 min of agent time (wall clock 22:00:43Z to 22:05:08Z, plus SUMMARY and state updates)
- **Started:** 2026-10-23T22:00:43Z
- **Completed:** 2026-10-23T22:05:08Z (last code commit)
- **Tasks:** 2 (both TDD, RED then GREEN)
- **Files modified:** 6 (151 insertions, 43 deletions)

## Accomplishments

- IN-01: `_RUN_ERROR_MAX_CHARS = 1000` is no longer dead. `redact()` takes `limit` (default stays 300) and `build_run_row` calls `redact(error, limit=_RUN_ERROR_MAX_CHARS)`, so a 5000-character error is stored at exactly 1000 and a secret planted at character 600 is gone (redaction runs before the cut).
- IN-01: `_redact_keys` redacts every provider-error key at the same limit and adds the counts of keys that become equal, so two provider errors sharing a long prefix keep both counts instead of one overwriting the other.
- IN-01: the orchestrator no longer cuts provider-error keys to 300 before `build_run_row`; it passes the provider's own error text and the run row is shaped, redacted and merged in one place.
- IN-04: `supabase_store._finite` is public as `finite` (with a docstring), `supabase_load_backfill.sha256_file` and its `hashlib` import are deleted, and the loader calls `supabase_store.file_sha256` in `main` and `prepare_rows`. An AST scan test fails if any other backend module reads `supabase_store._<name>`.

## Findings: commit and failing-first evidence

| Finding | Commits | Failing-first evidence |
|---|---|---|
| IN-01 (Task 1) | `1748e4f` test (RED), `6a53ae2` fix (GREEN) | All four new tests failed on the old code: `test_redact_limit_defaults_to_300_and_can_be_raised` with `TypeError: redact() got an unexpected keyword argument 'limit'`; `test_run_row_error_text_keeps_up_to_1000_characters` with `assert 300 == 1000`; `test_provider_error_keys_that_collide_after_redaction_keep_their_total` and `test_orchestrator_keeps_every_provider_error_count_for_a_city` because the two 400-character-prefix keys had collapsed into one 300-character key holding only the last count (3). Result `4 failed, 31 deselected`. After GREEN: 71 passed, 3 skipped on the verify set. |
| IN-04 (Task 2) | `b302d70` test (RED), `d9a0d31` refactor (GREEN) | `test_loader_reuses_the_store_helpers_instead_of_copies` failed on its first assertion, `assert not hasattr(loader, "sha256_file")` (the loader still defined its copy). After GREEN: 67 passed, 3 skipped on the first verify command; full suite 1537 passed, 48 skipped, 0 failed. |

RED evidence is pytest console output, which `gsd check tdd-red-evidence` has no adapter for (TAP, JUnit, swift-testing and unittest only), so the classifier was not run. Semantic assessment by inspection: each target test executed and failed on the planned assertion for the intended reason, with nothing failing on setup, import or collection.

## Task Commits

1. **Task 1 (IN-01): run-log error text up to 1000 characters and no lost provider-error counts** - `1748e4f` (test, RED), `6a53ae2` (fix, GREEN)
2. **Task 2 (IN-04): the loader uses the store's public helpers** - `b302d70` (test, RED), `d9a0d31` (refactor, GREEN)

**Plan metadata:** committed separately as `docs(04-10): complete run-log and helper gap-closure plan`, then the state and roadmap commit.

## Files Created/Modified

- `backend/supabase_store.py` - `redact(limit=...)`; `build_run_row` redacts errors with `limit=_RUN_ERROR_MAX_CHARS` and its docstring states 1000 characters and summed colliding keys; `_redact_keys` sums colliding counts; `_finite` renamed to public `finite`; `import numbers`.
- `backend/dlr_orchestrator.py` - per-city provider-error deltas keyed by the provider's own error text (redaction and merging left to `build_run_row`).
- `backend/supabase_load_backfill.py` - `sha256_file` and `import hashlib` removed; `supabase_store.file_sha256` and `supabase_store.finite` used.
- `backend/tests/supabase_run_log_test.py` - three IN-01 tests.
- `backend/tests/supabase_orchestrator_test.py` - one IN-01 test (`_fake_city_pipeline` `provider_errors` behavior with a `FakeStore`).
- `backend/tests/supabase_load_backfill_test.py` - one IN-04 test; `ast` and `numpy` imports added.

## Decisions Made

- `redact()`'s default stays 300, so the existing `test_redact_removes_urls_key_values_and_env_secrets` (`len(redact("x" * 1000)) == 300`) and every later-phase caller of `redact(str(exc))` are unchanged. This is IN-01's first suggested fix (keep the documented 1000).
- A non-numeric provider-error value cannot be summed; the last one seen is kept and the docstring says so.
- The orchestrator hands raw error text to `build_run_row`. The deltas never leave the process except through it, so T-04-41 (keys no longer redacted in the orchestrator) is mitigated; the existing classification test still asserts the redacted `synoptic: token=REDACTED` key.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The new 1000-character test planted its secret without a word boundary**
- **Found during:** Task 1 GREEN (verify run)
- **Issue:** `test_run_row_error_text_keeps_up_to_1000_characters` built `"x" * 600 + "token=..."`, so `token` had no `\b` boundary before it and `redact()`'s key=value pattern correctly did not match; the test failed on its own text, not on the code.
- **Fix:** the secret is now surrounded by spaces (`"x" * 599 + " " + secret + " " + ...`), putting it at character 600 as the plan specifies. The RED run was unaffected: that test had already failed on `assert 300 == 1000` before reaching the secret assertion.
- **Files modified:** `backend/tests/supabase_run_log_test.py`
- **Verification:** verify set 71 passed, 3 skipped
- **Committed in:** `6a53ae2` (part of the GREEN commit)

### Notes (no behavior change)

1. **Commit split for TDD tasks.** The plan names one `fix`/`refactor` commit per task. Both tasks are `tdd="true"`, so each has a `test(04-10)` RED commit first (4 commits, not 2). The GREEN commit messages are the ones the plan names.
2. **Co-Authored-By line.** The plan and dispatch text name `Claude Opus 5.5`; the harness attribution reminder names `Claude Sonnet 5.5`, which matches the model that ran, so the commits carry that. The first commit (`1748e4f`) was amended once, before any other commit, to carry the same trailer.

**Total deviations:** 1 auto-fixed (Rule 1, a defect in my own new test), 2 notes. **Impact on plan:** none; no scope added.

## Issues Encountered

- None blocking. `.planning/config.json` has a pre-existing uncommitted change that was not touched or staged.

## Known Stubs

None.

## Threat Flags

None. T-04-40 (longer error text) is covered by the secret-at-character-600 test and by `redact()` running before the cut; T-04-41 by `build_run_row` redacting every key and the unchanged classification test; T-04-42 by the distinct and colliding cases. No new endpoint, auth path or schema change.

## User Setup Required

None - no external service configuration required. Nothing connected to the real Supabase project; the live-local run used the throwaway Postgres (`DLR_TEST_PG_AUTOSTART=1`).

## Next Phase Readiness

- G-04-2 findings IN-01 and IN-04 are closed. Other review findings belong to the sibling gap-closure plans.
- Signatures stay backward compatible (`limit` is an optional keyword; `finite` is a rename of a private name with no outside users), so 05-03, 06-04 and 06-05 callers are unaffected.

## Verification Results

- Task 1 verify (`supabase_run_log_test`, `supabase_orchestrator_test`, `supabase_store_test`, `secret_scan_test`): 71 passed, 3 skipped (pre-existing env-gated tests).
- Task 2 verify 1 (`supabase_load_backfill_test`, `supabase_store_test`, `rating_identity_test`): 67 passed, 3 skipped.
- Full suite `pytest -q -p no:cacheprovider`: 1537 passed, 48 skipped, 0 failed.
- Live-local (`DLR_TEST_PG_AUTOSTART=1`) loader, orchestrator and run-log tests: 47 passed, 0 skipped.
- `grep -c "def sha256_file" backend/supabase_load_backfill.py` prints 0; `grep -c "def finite" backend/supabase_store.py` prints 1; `grep -n "limit=_RUN_ERROR_MAX_CHARS" backend/supabase_store.py` matches in `_redact_keys` and `build_run_row`.

## TDD Gate Compliance

RED (`test(04-10)`) precedes GREEN for both tasks (`1748e4f` before `6a53ae2`, `b302d70` before `d9a0d31`). The GREEN commits use `fix` and `refactor` as the plan specified rather than `feat`. No separate REFACTOR commit was needed.

---
*Phase: 04-supabase-store-writer*
*Completed: 2026-10-23*

## Self-Check: PASSED

- Files exist: `backend/supabase_store.py`, `backend/dlr_orchestrator.py`, `backend/supabase_load_backfill.py` and the three test files (modified, listed in `git diff --stat ea32e68..HEAD`).
- Commits `1748e4f`, `6a53ae2`, `b302d70`, `d9a0d31` are ancestors of HEAD; `git rev-list --count ea32e68..HEAD` = 4 (matches `commits:`).
- Acceptance criteria re-checked: four IN-01 tests and the IN-04 test failed first and pass; both greps as stated; both Task 2 verify commands exit 0.
