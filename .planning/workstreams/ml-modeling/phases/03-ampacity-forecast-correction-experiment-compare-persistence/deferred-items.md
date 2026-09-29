# Deferred Items — Phase 03 (Ampacity Forecast Correction Experiment)

Items discovered during execution that are out of scope for the discovering plan
(pre-existing, unrelated to the plan's `files_modified`) and therefore not auto-fixed
per the executor's scope-boundary rule.

## 03-01: Pre-existing `corridor_discretization_test.py` failures (23 tests)

**Found during:** Plan 03-01, Task 1 full-suite verification step.

**Symptom:** 23 tests in `backend/tests/corridor_discretization_test.py` fail on this
worktree's checkout, independent of any change made by Plan 03-01. Reproduced in
isolation (`pytest backend/tests/corridor_discretization_test.py` alone, no other test
file loaded) with the identical 23 failures — confirms this is not a test-order /
state-pollution artifact of the new `open_meteo_forecast_provider_test.py` file.

Representative failures:
- `assert 0 == 5` (fetcher call count) — several `test_rate_corridor_*` and
  `test_probe_*` tests, suggesting the injected fake fetcher is never invoked.
- `FileNotFoundError: [Errno 2] No such file or directory: '/private/var/folde...'` on
  `test_rate_corridor_archives_one_row_per_call` and two siblings — the archive-path
  fixture (`_isolate_historical_archive`, `tmp_path`-scoped) is not resolving as
  expected in this environment.
- `assert True is False` on `fallback` key checks.

**Scope determination:** `backend/corridor_discretization.py` and
`backend/tests/corridor_discretization_test.py` are neither in Plan 03-01's
`files_modified` list nor referenced by anything Plan 03-01 added
(`open_meteo_forecast_provider.py`, the `FORECAST_EXPERIMENT_*` config block). Grepped
both files for any reference to the new module/config additions — none found. Per the
executor's scope-boundary rule ("do not auto-fix pre-existing issues unrelated to
current task"), this was not fixed.

**Status:** Logged, not fixed. Full suite otherwise green (470 passed / 23 failed, all
23 confined to this one file). Whoever picks up `corridor_discretization.py` next
(or a dedicated debugging pass) should investigate — possibly a worktree-local
environment difference (this session runs against a symlinked shared `.venv`) or a
genuine regression introduced between the last `02-*` plan and now.

**Verified NOT caused by Plan 03-01:** `git diff --quiet HEAD -- backend/corridor_discretization.py backend/tests/corridor_discretization_test.py` exits 0 (no local modification to either file in this plan).
