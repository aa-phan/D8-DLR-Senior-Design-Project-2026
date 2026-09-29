# Deferred Items — Phase 03 (Ampacity Forecast Correction Experiment)

Items discovered during execution that are out of scope for the discovering plan
(pre-existing, unrelated to the plan's `files_modified`) and therefore not auto-fixed
per the executor's scope-boundary rule.

## Pre-existing `corridor_discretization_test.py` failures (23 tests)

**Found during:** Plan 03-01 (Task 1 full-suite verification) and independently confirmed
during Plan 03-02 (Task 1 baseline run) — both plans hit the same 23 failures on the same base
commit, in complete isolation, unrelated to anything either plan touches.

**Symptom:** 23 tests in `backend/tests/corridor_discretization_test.py` fail on this workstream's
current base commit, reproducible when the file is run alone
(`.venv/bin/python3 -m pytest -q backend/tests/corridor_discretization_test.py` -> 23 failed,
29 passed). Representative failures:
- `assert 0 == 5` (fetcher call count) — several `test_rate_corridor_*` and `test_probe_*` tests,
  suggesting the injected fake fetcher is never invoked.
- `FileNotFoundError: [Errno 2] No such file or directory: '/private/var/folde...'` on
  `test_rate_corridor_archives_one_row_per_call` and two siblings — the archive-path fixture
  (`_isolate_historical_archive`, `tmp_path`-scoped) is not resolving as expected.
- `assert True is False` on `fallback` key checks.

**Root cause, confirmed by the orchestrator (not the executors) via direct investigation:** this is
**not** an environment/worktree artifact. The same 23 failures reproduce identically against
`origin/main`'s own merged version of `corridor_discretization.py` (commit `6dae229`, the
`track-1-updates-v2` PR merge) — i.e. Track 1's own merged code broke its own tests, before either
Plan 03-01 or 03-02 started. Confirmed via `git diff --quiet` that neither plan modifies
`corridor_discretization.py` or its test file.

**Disposition:** Not fixed by either plan — out of scope per each executor's scope-boundary rule
and this phase's D-03 no-unrelated-file-change boundary. `corridor_discretization.py` is not in
either plan's `files_modified` list. Whoever owns Track 1 should pick this up as a dedicated
debugging pass; it predates Phase 3 entirely.

**Recorded:** `.planning/WINDOWS.md` (kind: deviation, phase 03) for cross-phase tracking.

**Verification that Phase 3's own work is unaffected:** every plan's own task-level `<verify>`
commands pass cleanly; the 23-failure baseline is unchanged before and after each plan's edits —
i.e. neither plan introduces any new failure, and the two known-full-suite-failure counts recorded
during execution (Plan 03-01: 470 passed/23 failed; Plan 03-02: 450→468 passed, 23 failed
throughout) are consistent with each other and with the pre-existing baseline.
