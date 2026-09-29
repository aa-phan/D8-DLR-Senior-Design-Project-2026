# Deferred Items — Phase 03 (Ampacity Forecast Correction Experiment)

## Pre-existing `backend/tests/corridor_discretization_test.py` failures (out of scope for Plan 03-02)

**Found during:** Plan 03-02, Task 1 (baseline full-suite run before any edit).

**Issue:** 23 tests in `backend/tests/corridor_discretization_test.py` fail on the plan's own base
commit (`0fa8ffd42fd04b03b9673a7d5c5d326241cdc7d9`), reproducible when the file is run in complete
isolation (`.venv/bin/python3 -m pytest -q backend/tests/corridor_discretization_test.py` ->
23 failed, 29 passed). This is not caused by, and not related to, any file Plan 03-02 touches
(`backend/wind_vector.py`, `backend/thermal_model.py`, `backend/forecast_training.py`, and their
test files) — `corridor_discretization.py` and its test file carry zero diff from this plan.

Symptoms span several unrelated assertion families in the same file (probe-trail sequencing,
bottleneck-index selection, archive-write `FileNotFoundError`s against `tmp_path`), suggesting a
single shared root cause internal to `corridor_discretization.py` or a fixture in its own test
file, not something introduced by this plan.

**Disposition:** Not fixed — out of scope per the executor's scope-boundary rule ("Only auto-fix
issues DIRECTLY caused by the current task's changes"). `corridor_discretization.py` is not in
Plan 03-02's `files_modified` list and touching it would violate this plan's D-03 boundary anyway.

**Recorded:** `.planning/WINDOWS.md` (kind: deviation, phase 03) for cross-phase tracking.

**Verification that Plan 03-02's own work is unaffected:** All three of Plan 03-02's own task-level
`<verify>` commands (scoped to `wind_vector_test.py`, `thermal_model_test.py`,
`forecast_training_test.py`) pass cleanly. The plan's own full-suite `<verify>` gates
(`.venv/bin/python3 -m pytest -q`) are documented in `03-02-SUMMARY.md` as passing net-new tests
while the pre-existing 23-failure baseline is unchanged before and after this plan's edits — i.e.
this plan introduces zero new failures.
