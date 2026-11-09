---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
reviewed: 2026-11-09T00:00:00Z
depth: standard
files_reviewed: 42
diff_base: 01c383d
findings:
  critical: 0
  warning: 5
  info: 10
  total: 15
status: issues_found
---

# Phase 8: Code Review Report

**Depth:** standard. **Status:** issues_found. **Scope:** `git diff 01c383d..HEAD` (42 files: day-ahead modules, runner stage, pre-flight, store, both migrations, ops SQL, examples, consumer docs, tests).

## Summary

No blocker. The exit-code invariant holds: `run_live` fixes `state["exit_code"]` (`backend/dlr_live_run.py:628`) before `_day_ahead_after_ratings` runs (632-633). The stage and its own `pipeline_run` write are each wrapped in `except Exception`, and nothing there assigns `exit_code`, `cities` or `run_log`; the step-summary and JSON paths guard the day-ahead part. The stage shares the 1200 s budget from `t0`, and the final write is bounded by `connect_timeout=10` and `statement_timeout=30s`, so the 30-minute job envelope holds.

The migrations match the Python twin: `INSERT_COLUMNS` and the CHECKs line up, including NaN and Infinity; the late rule agrees with `due_targets` (issuable at T-18 h, alarmed at T-12 h); the `pipeline_run` upsert of `{run_id, day_ahead}` satisfies NOT NULL through column defaults. No SQL injection or secret leak found.

The warnings concern design and documentation:
- a failing live-band query blocks publication instead of falling back to the TEST band;
- the consumer docs overstate the forecast horizon;
- one standing runbook step is wrong after the exposure;
- the permanent alarm is coupled to the day-ahead feed;
- no CI step enforces the guard the docs rely on.

Both migrations are applied live and pinned by sha256 tests. Any finding against them needs a new additive migration, not an edit.

Reviewer runs: the offline day-ahead tests (67 passed, 36 skipped as Postgres-only) and the Postgres-backed suites on a throwaway local cluster (264 passed). No live service was contacted.

## Warnings

### WR-01: A failing live-band query blocks publication; it does not fall back to the TEST band
**File:** `backend/day_ahead_band.py:314-337, 359-366`; `backend/dlr_day_ahead.py:165-194`
**Issue:** `band_for` calls `_live_offsets` → `live_pairs` with no guard around the database call. Any psycopg error there (statement timeout, a future `city_rating` change, a transient fault) escapes `band_for`, `_issue` catches it as unexpected, and the target gets no row. The contract says the TEST artifact "is the fallback band". This is latent today, because every band is `test-split`. Once live pairs exist (about 60 days in), a persistent live-query failure would silently stop all publication until the D-12 alarm fires, even with a valid TEST band in hand.
**Fix:** In `band_for`, wrap `_live_offsets` in `try/except Exception`, log the redacted type and keep the TEST offsets with `source="test-split"`. Add a test that makes `live_pairs` raise and asserts a `test-split` row is still issued.

### WR-02: Consumer docs describe a "next-day" horizon the data does not have, and conflate "not yet issued" with "late"
**File:** `docs/integration/software-team-handoff.md` (Day-ahead section and table row); `docs/data-science/decisions/pss_e_handoff.md` ("Which target hour to use", "Empty or late targets"); `docs/integration/examples/read_ratings.py:12-14`; `docs/integration/examples/curl.sh:9-10`
**Issue:** `due_targets` issues only targets in (now, now+18 h], so `day_ahead_upcoming` holds at most 3 future rows per city (`lead_minutes` ≤ 1080). A next-day panel or study cannot get a value for an hour more than 18 h away.
- The PSS/E doc says to read `day_ahead_status` when a target is missing. For a target beyond 18 h, `is_late` stays false and `missing_targets` is empty, so that advice misleads.
- The examples say "one value per city at each 00, 06, 12 and 18 UTC target", which reads as four per city.

**Fix:** State the lookahead: values appear about 18 h before the target, the view shows at most three targets per city, and a target further out is not late, only not yet due.

### WR-03: The standing runbook says `verify_day_ahead_store.sql` must be all-true, but one check is false by design after the exposure
**File:** `docs/data-science/decisions/dlr_live_runbook.md:814-815`; `supabase/ops/verify_day_ahead_store.sql:80-91`
**Issue:** `day_ahead_forecast_not_readable_by_anon_or_authenticated` is false once `20261108120100` is applied, and it now is. Runbook section 17 says "every `ok` must be true" with no caveat. An owner re-running the check during an incident would see a FAIL and might revoke the public grant, taking the consumer endpoint down.
**Fix:** Change the runbook: run it once, after the store migration and before the exposure; after the exposure that one check is expected false, so use `verify_exposure.sql`. Optionally add a header note to the SQL file, which is an ops script, not a pinned migration.

### WR-04: The permanent freshness alarm is coupled to the day-ahead feed, and its 503 message changed
**File:** `supabase/migrations/20261108120100_expose_day_ahead_forecast.sql:169-221` (applied; any change needs a new additive migration)
**Issue:** The replaced `assert_fresh` now raises `PT503` for a late day-ahead city, and the 503 message changed from `stale or missing city rating` to `... or late day-ahead forecast`. A consumer or monitor that treats `PT503` as "ratings are stale", or matches the old text, would misread a day-ahead stall as a rating outage. `rest-api.md` section 5 documents this RPC to consumers. This follows the D-12 owner decision, so it is a risk note, not a defect to revert.
**Fix (owner's call):** Either add a separate `assert_day_ahead_fresh()` in a new migration, or have `rest-api.md` state that a 503 with an empty `missing=`/`stale=` means the ratings are fine. At minimum, add a test that pins the full message string.

### WR-05: The "fails hard before a push" safety net is not enforced anywhere
**File:** `backend/dlr_live_check_models.py:36-46` (docstring); `.github/workflows/`
**Issue:** The docstring says an offline test fails hard on any manifest or file mismatch before a push, because the live pre-flight only warns for the day-ahead tier. No workflow runs pytest, so model, band or manifest drift reaches `main` silently. The day-ahead stage then refuses the files, and the first signal is the 12 h late alarm. The tests also skip without Postgres.
**Fix:** Add a CI job or pre-push hook that runs `dlr_live_check_models_day_ahead_test.py` and fails on skips, or drop the "before a push" claim.

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
**Issue:** These checks reference `public.day_ahead_status` and `'public.day_ahead_forecast'` directly. On a database without the expose migration the whole query errors, which hides the Phase 6 rows too and breaks the "missing turns false" convention.
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
**File:** `backend/tests/fake_postgrest.py` (`make_day_ahead_view_rows`); `docs/integration/rest-api.md:186`
**Issue:** The fake's default upcoming rows set `band_source="test-split"` with a non-null `band_pairs_through`, but the contract (and a DB CHECK) requires NULL for `test-split`. The consumer contract also embeds a dated anecdote ("on the first live run two MIDLAND values were below 1250 A").
**Fix:** Set `band_pairs_through` to None in the fixture, and move the anecdote out of the contract.

---
_Reviewed: 2026-11-09_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
