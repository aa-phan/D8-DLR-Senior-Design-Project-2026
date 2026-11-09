---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
reviewed: 2026-11-09T00:00:00Z
depth: standard
files_reviewed: 13
diff_base: d195943
files_reviewed_list:
  - .github/workflows/day_ahead_manifest_check.yml
  - backend/day_ahead_band.py
  - backend/dlr_live_check_models.py
  - backend/tests/day_ahead_band_test.py
  - backend/tests/day_ahead_expose_test.py
  - backend/tests/dlr_day_ahead_test.py
  - docs/data-science/decisions/dlr_live_runbook.md
  - docs/data-science/decisions/pss_e_handoff.md
  - docs/integration/examples/curl.sh
  - docs/integration/examples/read_ratings.py
  - docs/integration/rest-api.md
  - docs/integration/software-team-handoff.md
  - supabase/ops/verify_day_ahead_store.sql
findings:
  critical: 0
  warning: 1
  info: 14
  total: 15
status: issues_found
---

# Phase 8: Code Review Report (incremental re-review)

**Reviewed:** 2026-11-09
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found
**Scope:** `git diff d195943..HEAD` of the 13 files above (the fix commits 1d090de, 41ac760, 558157f, 73949c2, 88eb5f7, c04c1d6, 1047814, 49131d4). The first review's WR-01..WR-05 are fixed and dropped; its Info findings IN-01..IN-10 are carried over. New findings start at WR-06 and IN-11.

## Summary

All five earlier warnings are fixed correctly, and the fixes introduced no blocker and no new defect in code.

- **WR-01 (live-band fallback), correct.**
  - `band_for` wraps only the `_live_offsets` call. The `BandArtifactError` for a missing TEST band is raised before the guard, so it still propagates.
  - The runner opens its connection with `autocommit=True` (`supabase_store.connect`), so a failed query leaves no aborted transaction that would break the following `insert_row`.
  - Only `type(exc).__name__` is logged. The new tests check that the fallback row is `test-split` with `pairs_through` None and `n` taken from the artifact. They also check that neither the secret nor the message text is logged. The connection string is assembled at run time, so `secret_scan_test` passes.
- **WR-02, WR-03, WR-04 (docs), correct.**
  - The 18 h lookahead and "at most three per city" agree with `due_targets`.
  - The runbook and the SQL header now say that `day_ahead_forecast_not_readable_by_anon_or_authenticated` is false by design after `20261108120100`. None of the other checks in `verify_day_ahead_store.sql` depends on the public grant.
  - The pinned PT503 text `stale or missing city rating or late day-ahead forecast` matches `20261108120100_expose_day_ahead_forecast.sql:208` exactly.
  - The `rest-api.md` reading rule (empty `missing=`/`stale=` means the ratings are fine) matches the test's `missing={}` / `stale={}` assertions.
- **WR-05 (CI), mostly correct.**
  - The job needs no secret and runs with `contents: read`.
  - `fetch-depth: 0` is needed by `test_the_eight_live_entries_are_unchanged`. Without it the test would skip, and the skip grep would then fail the job.
  - Model files, manifest and band artifact are all tracked, so no LFS checkout is needed.
  - `pipefail` plus the `[0-9]+ skipped` grep correctly catch a failing or skipped guard.
  - One overstatement remains (WR-06 below).

Reviewer runs: `dlr_live_check_models_day_ahead_test.py` (33 passed, 0 skipped), then `day_ahead_band_test.py`, `dlr_day_ahead_test.py`, `day_ahead_expose_test.py` and `secret_scan_test.py` (47 passed, 54 skipped as Postgres-only). I did not run the Postgres-backed tests here. No live service, GitHub or `.env` was touched.

## Warnings

### WR-06: The CI guard is described as running "before it reaches main", but it also triggers on direct pushes to main, and nothing blocks a merge
**File:** `.github/workflows/day_ahead_manifest_check.yml:3-6, 12-17`; `backend/tests/dlr_live_check_models_day_ahead_test.py` (committed-tree group comment, "fails here, offline, before any push")
**Issue:** The header says a mismatch "fails hard, before it reaches main", and the test file says "before any push". The job triggers on `pull_request` and on `push` to `main`. This repo commits straight to `main` (see the recent history). A direct push runs the job after the bad manifest or model is already on `main`. The day-ahead stage then refuses the files on the next hourly run, and the first operational signal is still the 12 h late alarm. The header does say that blocking a merge needs branch protection, which only the owner can set. As written, the "before" claim is true only if that rule is configured and every change goes through a PR.
**Fix:** Reword both comments to say what is true. For example: "fails hard on every pull request and on every push to main (red check); it blocks a merge only once 'Day-ahead manifest check' is a required status check". Optionally add `.github/workflows/day_ahead_manifest_check.yml` to the owner checklist in the runbook, so the required-check setting is not forgotten.

## Info

### IN-01: `missing` is reported as empty for timeout, no-output and crash records
**File:** `backend/dlr_live_run.py:383-388, 411-416, 664-671`
**Issue:** `classify_day_ahead` keeps `due=[]` and `missing=[]` for these records, so the summary table and `pipeline_run.day_ahead` show "issued 0, missing 0" next to `timeout` or `error`.
**Fix:** Mark `missing` as unknown (None, or `?` in the table) for `timeout` and for `error` with no output.

### IN-02: The summary reason cell shows only the tail of the joined reasons
**File:** `backend/dlr_live_run.py:666-670`
**Issue:** `_cell` keeps the last 120 characters of the joined reasons. With three targets refused for the same reason, only the last is visible and the city-level reason is lost.
**Fix:** Format each reason separately, or show the first reason plus a count.

### IN-03: The `supabase_js.mjs` header omits Part 3
**File:** `docs/integration/examples/supabase_js.mjs:1-8`
**Issue:** The header lists steps (1) and (2) only, but the script covers day-ahead as step (3).
**Fix:** Add the step (3) line.

### IN-04: The schema doc overstates the issue rate
**File:** `docs/data-science/schema/day_ahead_forecast_v1.md:69`
**Issue:** It says "afterwards a normal run writes one new target per city". Targets are 6-hourly, so about one hourly run in six issues a target and the rest are `none_due`.
**Fix:** Say "about one run in six issues a new target per city".

### IN-05: Constants are hard-coded where code derives them
**File:** `backend/day_ahead_verify.py:108,111`; `backend/day_ahead_contract.py:42`; `supabase/migrations/20261108120100_expose_day_ahead_forecast.sql`
**Issue:** `MAX_LEAD` (18 h) and `TEST_BAND_N` (196) are literals in the verifier. `due_targets` derives the 18 h from `shadow._resolve_publication_lag_hours()`, and 196 comes from the artifact. `LATE_WINDOW_HOURS=12` is mirrored by a SQL literal: if the publication lag ever rises toward 12 h, the feed is permanently late.
**Fix:** Derive the verifier's values (24 h minus lag, and the artifact's `n`), and add a test that the lag is below `LATE_WINDOW_HOURS`.

### IN-06: Dead and duplicated code
**File:** `backend/dlr_live_check_models.py:65`; `backend/live_run_log.py:147`; several modules
**Issue:**
- `DAY_AHEAD_KINDS` is unused by production code, because `required_day_ahead_artifacts` re-types the kind strings.
- `env` is unused in `build_day_ahead_run_row`.
- `contract.BAND_SOURCES` is unused by `band_for`, which hard-codes the literals.
- `_utc`/`_iso` helpers are re-implemented in five modules.

**Fix:** Reuse the constants, drop the unused parameter, and share one helper.

### IN-07: `verify_exposure.sql` raises instead of returning false when a day-ahead object is missing
**File:** `supabase/ops/verify_exposure.sql` (`day_ahead_status_has_the_four_cities`, `anon_can_select_day_ahead_*`)
**Issue:** These checks reference `public.day_ahead_status` and `'public.day_ahead_forecast'` directly. On a database without the expose migration the whole query errors, which hides the Phase 6 rows too and breaks the "missing turns false" convention. This matters more now, because the runbook sends owners to this file after the exposure.
**Fix:** Guard them with `to_regclass(...)`, as the store check does.

### IN-08: `apply_band` discards a valid edge when only one edge is bad
**File:** `backend/day_ahead_band.py:247-260`
**Issue:** If only `lower > point`, both edges collapse to a zero-width band at the point. This mirrors the 60-minute guard, but it publishes a 5-95% band that is not one.
**Fix:** Clamp only the offending edge, or mark the row so consumers can see it.

### IN-09: `build_band_artifact` ignores minutes and seconds in `valid_time`
**File:** `backend/day_ahead_band.py:122-125`
**Issue:** It checks only `dt.hour`, so a 06:30 row is accepted as the 06 UTC target.
**Fix:** Also require `minute == second == 0`.

### IN-10: A test fixture and a doc anecdote are inconsistent with the contract
**File:** `backend/tests/fake_postgrest.py` (`make_day_ahead_view_rows`); `docs/integration/rest-api.md:188`
**Issue:** The fake's default upcoming rows set `band_source="test-split"` with a non-null `band_pairs_through`, but the contract (and a DB CHECK) requires NULL for `test-split`. The consumer contract also embeds a dated anecdote ("on the first live run two MIDLAND values were below 1250 A").
**Fix:** Set `band_pairs_through` to None in the fixture, and move the anecdote out of the contract.

### IN-11: The TEST-band fallback is silent in the stored data and the run log
**File:** `backend/day_ahead_band.py:361-374`; `backend/dlr_day_ahead.py:178-190`
**Issue:** When the live query fails, `band_for` returns the same `test-split` choice that it returns when fewer than `LIVE_BAND_MIN_PAIRS` pairs exist. The only trace of the fault is one `logger.warning` line in the runner log. Rows are first-write-wins and never rewritten, so a transient fault permanently stamps that target with the TEST band, even though a live band was available. `band_sources` in the run output cannot tell "not enough pairs" from "query failed". This is acceptable, because the fallback is the contract, but a persistent fault would be invisible until someone reads the log.
**Fix:** Optionally return a flag on `BandChoice` (for example `live_query_failed`). Carry it into `run.refuse`-style notes or the `pipeline_run.day_ahead` JSON, so the summary can show "n targets on the TEST band after a live-query fault".

### IN-12: Consumer docs still call the feed "next-day" next to an 18 h lookahead
**File:** `docs/integration/software-team-handoff.md:56`; `docs/data-science/decisions/pss_e_handoff.md:83`
**Issue:** The fixes added the 18 h lookahead, but the table row still names the use "The next-day panel", and the PSS/E text still says "For a next-day study". A reader who stops at those phrases still expects a value for a hour 24 h or more away. The new qualifying sentences appear only after them.
**Fix:** Say "the next-18-hours panel" or "the coming-hours panel", and "for a study within the next 18 hours", or add "(only the coming 18 hours)" to the phrase itself.

### IN-13: `curl.sh` hard-codes the label that `read_ratings.py` reads from the data
**File:** `docs/integration/examples/curl.sh:70-72`
**Issue:** The new "Day-ahead note" block echoes a constant label. `read_ratings.py` prints the `label` values the service returned (falling back to the constant). If the label ever changes, the curl example would keep printing the old text, and a copied script would display a label the data no longer carries. The `label` column is already in the `day_ahead_upcoming` select above, so the label is on screen anyway.
**Fix:** Keep the note, but add a comment that it is a reminder and that the authoritative text is the `label` field above. Or drop the label echo and keep only the "not the live rating" line.

### IN-14: Actions in the new workflow are pinned by tag, while `supabase_smoke.yml` pins by SHA
**File:** `.github/workflows/day_ahead_manifest_check.yml:38, 45`
**Issue:** `actions/checkout@v4` and `actions/setup-python@v5` follow a moving tag. This matches `dlr_live.yml` and `shadow_collect.yml`, and this job holds no secret and has `contents: read` only, so the risk is low. It is inconsistent with the one workflow that pins by commit.
**Fix:** Optionally pin both to the same commit SHAs as `supabase_smoke.yml`.

---

_Reviewed: 2026-11-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
