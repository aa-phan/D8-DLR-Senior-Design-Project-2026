---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
fixed_at: 2026-11-09T00:00:00Z
review_path: .planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 5
skipped: 0
status: all_fixed
---

# Phase 8: Code Review Fix Report

**Fixed at:** 2026-11-09
**Source review:** .planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5 (0 critical, 5 warning; Info findings out of scope)
- Fixed: 5
- Skipped: 0

**Verification ran in:** the isolated review-fix worktree (a fresh checkout of `main` at `1faa044`, using the main checkout's `.venv` interpreter), with `DLR_TEST_PG_AUTOSTART=1` so the Postgres-backed tests ran against a throwaway local cluster. The final run was `pytest backend/tests -k "day_ahead or dlr_live or rest_api or example"`: 442 passed, 0 skipped. No live service was contacted. The worktree is removed after the run, so re-run the same command in the main checkout to reproduce.

## Fixed Issues

### WR-01: A failing live-band query blocks publication; it does not fall back to the TEST band

**Files modified:** `backend/day_ahead_band.py`, `backend/tests/day_ahead_band_test.py`, `backend/tests/dlr_day_ahead_test.py`
**Commit:** 1d090de
**Status:** fixed: requires human verification (logic change)
**Applied fix:** `band_for` now wraps the `_live_offsets` call in `try/except Exception`. On failure it keeps the TEST offsets with `source="test-split"` and logs a warning naming only the exception type (the message could carry the database URL). Two tests added: an offline one that makes `live_pairs` raise (with a URL and "statement timeout" in the message) and asserts a `test-split` band is returned and neither string is logged; and an end-to-end one in `dlr_day_ahead_test.py` that makes `live_pairs` raise and asserts all three due targets are still issued with `band_source == "test-split"` in the table. Both ran against local Postgres and passed (no skips).

### WR-02: Consumer docs describe a "next-day" horizon the data does not have, and conflate "not yet issued" with "late"

**Files modified:** `docs/integration/software-team-handoff.md`, `docs/data-science/decisions/pss_e_handoff.md`, `docs/integration/examples/read_ratings.py`, `docs/integration/examples/curl.sh`
**Commit:** 41ac760
**Applied fix:** The docs now say a value appears about 18 hours before its target, the view holds at most three upcoming targets per city, and a target further out is not late, only not yet due (`is_late` stays false). The PSS/E "Which target hour to use" and "Empty or late targets" sections were corrected to match, and the two example headers no longer read as four values per city. The consumer-docs, REST-doc and example tests pass (the examples still parse; `bash -n` clean).

### WR-03: The standing runbook says `verify_day_ahead_store.sql` must be all-true, but one check is false by design after the exposure

**Files modified:** `docs/data-science/decisions/dlr_live_runbook.md`, `supabase/ops/verify_day_ahead_store.sql`
**Commit:** 558157f
**Applied fix:** The runbook step now says to run the script once, after the store migration and before the exposure migration, and that after the exposure `day_ahead_forecast_not_readable_by_anon_or_authenticated` is false on purpose (do not revoke the public grant; use `verify_exposure.sql` instead). A matching comment was added to the header of the ops script (a comment only; it is an ops script, not a migration). `day_ahead_migration_test.py` runs the script and passed (25 passed with Postgres).

### WR-04: The permanent freshness alarm is coupled to the day-ahead feed, and its 503 message changed

**Files modified:** `docs/integration/rest-api.md`, `backend/tests/day_ahead_expose_test.py`
**Commit:** 73949c2
**Applied fix:** Low-risk option only, per the owner's guardrails. `rest-api.md` now explains in plain words that the 503 message is `stale or missing city rating or late day-ahead forecast` (it used to be `stale or missing city rating`), and that a `PT503` whose `missing=` and `stale=` are both empty means the ratings are fine and only the day-ahead forecast is late. `day_ahead_expose_test.py` now pins the full message string for both the late-day-ahead case and the stale-rating case (it previously matched only a substring). The tests ran against local Postgres and passed.
**Left for the owner:** the other option, a separate `assert_day_ahead_fresh()` RPC in a new additive migration, was not done. No file under `supabase/migrations/` was edited, no migration was added, and the live database was not touched.

### WR-05: The "fails hard before a push" safety net is not enforced anywhere

**Files modified:** `.github/workflows/day_ahead_manifest_check.yml` (new), `backend/dlr_live_check_models.py`
**Commit:** 88eb5f7
**Applied fix:** Adding CI was feasible: `backend/tests/dlr_live_check_models_day_ahead_test.py` needs no database, secret or network, and passes in a fresh checkout (33 passed, 0 skipped). The new workflow runs it on pull requests, pushes to main and manual dispatch, with `contents: read` only and no environment or secrets, and fails the job if pytest reports any skip. It follows the existing workflow style (Python 3.12, `requirements.txt` install, `actions/checkout@v4`, `actions/setup-python@v5`). The pre-flight docstring now points at the workflow instead of promising a check "before a push". The step's skip-detection shell logic was run locally and behaves as intended. The workflow YAML parses (checked with Ruby; the project venv has no PyYAML). It has not run on GitHub (no push, as instructed).
**Owner follow-up:** to make the check block merges, add "Day-ahead manifest check" as a required status check in the GitHub branch protection settings.

---

_Fixed: 2026-11-09_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
