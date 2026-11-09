---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
verified: 2026-11-09T12:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-01-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-01-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-02-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-02-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-03-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-03-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-04-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-04-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-05-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-05-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-06-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-06-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-07-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-07-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-08-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-08-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-09-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-09-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-10-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-10-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-11-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-11-SUMMARY.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-12-PLAN.md"
  - ".planning/workstreams/production-pipeline/phases/08-day-ahead-cooling-forecast-alongside-60-minute-g6/08-12-SUMMARY.md"
  - "backend/day_ahead_band.py"
  - "backend/day_ahead_contract.py"
  - "backend/day_ahead_forecast.py"
  - "backend/day_ahead_verify.py"
  - "backend/dlr_day_ahead.py"
  - "backend/dlr_live_check_models.py"
  - "backend/dlr_live_run.py"
  - "backend/live_run_log.py"
  - "backend/supabase_store.py"
  - "data/day_ahead/day_ahead_bands_v1.json"
  - "data/models/LIVE_ARTIFACT_HASHES.sha256"
  - "docs/data-science/decisions/pss_e_handoff.md"
  - "docs/data-science/schema/day_ahead_forecast_v1.md"
  - "docs/integration/examples/curl.sh"
  - "docs/integration/examples/read_ratings.py"
  - "docs/integration/examples/supabase_js.mjs"
  - "docs/integration/rest-api.md"
  - "docs/integration/software-team-handoff.md"
  - "supabase/migrations/20261108120000_day_ahead_forecast_store.sql"
  - "supabase/migrations/20261108120100_expose_day_ahead_forecast.sql"
covered_digest: "v3:sha256:626f4284dde5b703e5bd11e30e4005bb9162dcab19c330e0404e07ee677a330e"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 8: Day-Ahead Cooling Forecast Alongside 60-Minute G6 Verification Report

**Phase Goal:** Production serves a day-ahead (24 h) ampacity forecast per city from `ml_cooling_corrected` as an additional output alongside the 60-minute G6 forecast, which stays `ml` and keeps gating G6. The day-ahead value is labelled as a higher-error future forecast, with its own uncertainty band, and never replaces or gates the live rating.
**Verified:** 2026-11-09
**Status:** passed (5 non-blocking warnings, all carried from 08-REVIEW.md; none undermines the goal)
**Re-verification:** No, initial verification

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Every hourly run after go-live issues each due target per city from the 24 h-old run through the unchanged shadow functions under the production conductor, parity-tested, and publishes nothing when cooling cannot produce a value | VERIFIED | `day_ahead_forecast.compute_value` calls only `shadow.fetch_live_forecast_for_valid_time`, `validate_and_prepare_shadow_row`, `_enrich_city_frame_for_correction`, `CoolingCorrectionShadowMethod.predict` under `city_point.production_city_point`; model via hash-verified `fcr.make_headline_loader`. Every failure becomes `DayAheadNotIssued` (no substitute method, no row). `due_targets` gives (now, now+18 h] on the 6 h grid; `dlr_day_ahead._execute` issues `missing = due - existing` (table is the state, so catch-up works). Parity tests `test_parity_production_equals_the_shadow_path_where_the_conductor_matches[x4]` and `test_parity_austin_...` exist and pass (re-run by me: 268 passed across the day-ahead suites with local Postgres). Live: run 42543631399 wrote 12 rows (3 per city) and 10/10 first-slot checks passed (08-08-first-slot.json: weather run 24 h before target, ml_cooling_corrected, horizon 1440, model sha equals manifest). Workflow runs `dlr_live_run.py`, whose `main()` turns the stage on. |
| 2 | Every row carries a 5-95% band (TEST artifact at launch, live rolling per band once 60 graded pairs exist), its source and size, model and band hashes, config identity, issue time and the label | VERIFIED | `build_row` emits exactly `contract.INSERT_COLUMNS` (band_source, band_n, band_pairs_through, band_artifact_sha256, cooling_model_sha256/source, config_version/fingerprint, issued_at, label). Migration CHECKs enforce label non-empty, sha formats, band contains point, band_pairs_through NULL iff live-rolling. `band_for` switches per (city x UTC hour) to live rolling at `LIVE_BAND_MIN_PAIRS`=60 using newest 120, only when 5% offset < 0 < 95% offset; `_LIVE_PAIRS_SQL` excludes fallback/exhausted/non-ok/non-live ratings and mismatched fingerprint/model. Live rows in 08-08-first-slot.json: test-split, n=196, artifact sha equals manifest entry, label D-11. Live path covered by Postgres-backed `day_ahead_band_test.py` (passed); not yet exercised in production (needs ~60 days of pairs; expected). |
| 3 | Live ratings, G6 `ml` forecast, exit code, `city_rating` and the 34-column `latest_rating` are unchanged; a day-ahead failure or bad file never stops or reddens a run and is recorded in `pipeline_run.day_ahead` | VERIFIED | `git diff 01c383d..HEAD` touches no rating, orchestrator, forecast-gate, workflow or `city_rating`/`latest_rating` migration file. `grep day_ahead` finds nothing in `dlr_orchestrator.py`, rating or config modules. In `run_live`, `state["exit_code"]` is fixed (dlr_live_run.py:628) before `_day_ahead_after_ratings`, which sits in its own `except Exception`, never assigns exit_code/cities/run_log, and writes only `{run_id, day_ahead}`. Behavioral tests pass: `test_a_crashing_hanging_or_silent_day_ahead_child_never_changes_the_rating_result`, `test_no_day_ahead_child_starts_before_the_ratings_finished_and_the_exit_code_was_set`, `test_a_failing_day_ahead_write_is_counted_separately...`, `test_a_stage_that_raises_as_a_whole...`. Shared budget 4 x 300 s; workflow `timeout-minutes: 30` unchanged. Live: run 42543631399 green, `pipeline_run.day_ahead` record equals its rows (check 10/10). |
| 4 | After the first live issue run is verified, anon reads the upcoming targets and a four-row status and nothing else new, writes are refused, and the permanent alarm also fails for a stalled feed | VERIFIED | Expose migration: SELECT-only grants, `day_ahead_upcoming` (26 cols), `day_ahead_status` (4 rows, 7 cols), `assert_fresh` same signature with `day_ahead_late` PT503 clause armed by first row; `pipeline_run` stays private. Order honoured: first run verified (08-08) before expose applied (08-11). Live evidence 08-11-live-checks.json: 8/8 REST checks ok (12 future ordered rows, 26 columns, 4 cities none late, `assert_fresh` 200 and `day_ahead_armed` true, anon INSERT refused 401/42501, view PATCH refused, `pipeline_run` hidden). Offline: `day_ahead_expose_test.py` passed; the 503 stall path is covered by those Postgres tests, not exercised live (a live stall would be a real incident). |
| 5 | The contract states label, owner-approved paragraph, band and late rules and the meaning of "24 h", and is published only after the expose step, together with the three consumer examples (which also read day-ahead and ran live first) and the Software and PSS/E handoff notes | VERIFIED | `docs/integration/rest-api.md` "Day-ahead forecast" section carries the label, the "more error ... because it looks further ahead" paragraph, band rule, late rule, "What '24 h' means" (age of the weather run, issued 0-18 h before target) and both column tables. Three examples read `day_ahead_upcoming` and `day_ahead_status`; env reads are only SUPABASE_URL / SUPABASE_PUBLISHABLE_KEY, no project value. Live runs of curl.sh, read_ratings.py (system 3.9 and venv 3.12) and supabase_js.mjs all exit 0 with the label seen (08-11-examples.json). Software handoff, api-contract and PSS/E notes extended. `origin/main` is at 4008477 and contains the expose migration and rest-api.md day-ahead section (publishing push done after expose apply). |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/day_ahead_forecast.py` | due targets, value, row, insert | VERIFIED | 299 lines, substantive, wired via `dlr_day_ahead.py` |
| `backend/day_ahead_band.py` | TEST artifact guards, live rolling band | VERIFIED | `band_for`/`live_pairs` real SQL, wired in `_issue` |
| `backend/dlr_day_ahead.py` | per-city child | VERIFIED | invoked by `dlr_live_run.day_ahead_child_argv` |
| `backend/dlr_live_run.py` (stage) | stage after exit code | VERIFIED | see truth 3 |
| `backend/live_run_log.py` / `supabase_store.py` | `pipeline_run.day_ahead` write | VERIFIED | optional column, separate upsert |
| `backend/dlr_live_check_models.py` + `data/models/LIVE_ARTIFACT_HASHES.sha256` | manifest lists 4 cooling files and band artifact; warn-only pre-flight tier | VERIFIED | manifest diff adds band JSON, AUSTIN refit, 3 frozen shadow cooling models |
| `supabase/migrations/20261108120000_*` | write-side table, RLS, writer select+insert only | VERIFIED | applied live, pinned by sha256 test |
| `supabase/migrations/20261108120100_*` | views, SELECT-only grants, assert_fresh clause | VERIFIED | applied live, pinned |
| `backend/day_ahead_verify.py`, `supabase/ops/verify_*.sql` | owner checks | VERIFIED | used live (10/10, 29/29, 7/7, 8/8) |
| `docs/integration/examples/*`, docs | consumer handoff | VERIFIED | live-run and published |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `.github/workflows/dlr_live.yml` | `dlr_live_run.main()` -> `run_live(day_ahead=True)` | `MAIN_RUNS_DAY_AHEAD` | WIRED (workflow file unchanged) |
| `run_live` | `dlr_day_ahead.py` child per city | `run_day_ahead_stage` | WIRED |
| child | `public.day_ahead_forecast` | `insert_row` ON CONFLICT DO NOTHING | WIRED (12 live rows) |
| runner | `pipeline_run.day_ahead` | `build_day_ahead_run_row` + `upsert_run` | WIRED (live check 10/10) |
| `day_ahead_status` | `assert_fresh` | `public.day_ahead_status` in the function | WIRED (`day_ahead_armed` true live) |
| band | live city_rating | `_LIVE_PAIRS_SQL` join | WIRED (tested; not yet live-exercised) |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| `day_ahead_upcoming` rows | forecast_amps and band | shadow cooling model on live Open-Meteo run + station anchor | Yes, 12 live rows with anchors (synoptic), distinct amps | FLOWING |
| `day_ahead_status` | missing_targets / is_late | table contents | Yes, 4 rows, none late live | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Day-ahead suites (forecast, band, child, stage, expose, migration, docs, pre-flight, examples) | `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest <9 day-ahead test files> -q` from repo root | 268 passed | PASS |
| Full suite (established this session, not re-run by me) | full suite at HEAD with Postgres autostart | 3000 passed, 0 failed, 0 skipped | PASS (reported) |
| Live first slot / expose / examples | evidence JSON files 08-08-first-slot, 08-11-live-checks, 08-11-examples | all ok, exit 0 | PASS (reviewed artifacts; no live service re-contacted) |

Note: running the day-ahead tests from `backend/` instead of the repo root errors on a relative `data/day_ahead/...` path; the suite is designed for repo-root execution. Not a defect.

### Probe Execution

No probe scripts declared by the phase plans. Step 7c: SKIPPED (not applicable).

### Requirements Coverage

Every `requirements:` ID in the 12 PLAN frontmatters maps to REQUIREMENTS.md; none orphaned (REQUIREMENTS.md maps exactly DAY-01..DAY-09 to Phase 8 and all nine are claimed).

| Requirement | Source plans | Status | Evidence |
|-------------|--------------|--------|----------|
| DAY-01 per-target issue, catch-up, nothing after target | 08-01, 08-04, 08-08 | SATISFIED | `due_targets`, `missing_targets`, `existing_targets`; CHECK `issued_at < valid_time`; live 12 rows |
| DAY-02 shadow functions unchanged, hash-verified loader, parity, manifest, warn-only pre-flight | 08-01, 08-04, 08-05 | SATISFIED | `compute_value`, parity tests, manifest diff, `dlr_live_check_models` day-ahead tier |
| DAY-03 5-95% band, TEST then live rolling, source and n recorded | 08-01, 08-03 | SATISFIED | `band_for`; live rows test-split n=196 |
| DAY-04 never delays/changes ratings; exit code fixed first; `pipeline_run.day_ahead`; shared budget | 08-02, 08-05, 08-06, 08-08 | SATISFIED | runner diff, stage tests, live run green |
| DAY-05 additive store migration, writer select+insert, RLS, unchanged `city_rating`/`latest_rating` | 08-01, 08-04, 08-07 | SATISFIED | migration 20261108120000, store checks 10/10 live |
| DAY-06 expose views and contract docs | 08-09, 08-10, 08-11, 08-12 | SATISFIED | migration 20261108120100, rest-api.md, verify_exposure 29/29 |
| DAY-07 `assert_fresh` day-ahead 503 clause | 08-09, 08-10, 08-11 | SATISFIED | function body; live 200 with `day_ahead_armed` true; stall path tested offline |
| DAY-08 owner-gated go-live order | 08-02, 08-06..08-11 | SATISFIED | git order: write migration (08-07) -> push 1088392 -> first run verified (08-08) -> expose applied and docs pushed (08-11) |
| DAY-09 consumer examples and handoff docs, run live before publishing push | 08-11, 08-12 | SATISFIED | 08-11-examples.json (4 runs, exit 0); origin/main 4008477 |

### Anti-Patterns Found

TBD/FIXME/XXX scan over the phase's Python and SQL files: none unreferenced (no debt-marker blocker). The code review (0 critical, 5 warnings, 10 info) found no blocker.

### Warnings (non-blocking; carried from 08-REVIEW.md, independently weighed)

| ID | Concern | Weighs on goal? |
|----|---------|-----------------|
| WR-01 | A failing live-band query blocks publication rather than falling back to the TEST band (`band_for` has no guard around `live_pairs`). Latent: every band is `test-split` today; live pairs exist only after ~60 days. Fails closed (no row, alarm fires at T-12 h), never publishes a wrong value, never touches ratings. | No, but fix before live pairs accrue (~Jan 2027). |
| WR-02 | Handoff docs and example headers say "next-day" and can be read as four values per city; `day_ahead_upcoming` holds at most 3 future targets per city (issued from T-18 h). `rest-api.md` states the 18 h rule and 0-18 h issue range correctly; PSS/E "Empty or late targets" advice misleads for targets >18 h away. | No (goal and contract hold); documentation fix. |
| WR-03 | Runbook section 17 says every `verify_day_ahead_store.sql` check must be true; one (`..._not_readable_by_anon_or_authenticated`) is false by design after the expose. Risk: an owner could revoke the public grant during an incident. | No; fix runbook wording. |
| WR-04 | The permanent alarm now also fails (PT503) for a late day-ahead feed and the 503 message changed. Owner-chosen (D-12) and documented in rest-api.md. | No; owner's call (optional separate RPC or doc note). |
| WR-05 | The "fails hard before a push" offline test is not enforced by any CI workflow; manifest/band drift would first show as the 12 h late alarm. | No; add a CI/pre-push step or drop the claim. |

Info items IN-01..IN-10 are cosmetic, doc or hardening notes; none affects a must-have.

### Human Verification Required

None required for status. Informational follow-ups for the owner: (a) the live-rolling band switch and the 503 stall path have been tested only on a local Postgres, not in production, and will first occur when pairs exist or a feed stalls; (b) later local commits (evidence/pin/summary/review) are not yet pushed, which is expected.

### Gaps Summary

No gaps. The goal is achieved in the codebase and on the live project: a day-ahead `ml_cooling_corrected` value per city, labelled as a higher-error forecast with its own band, is issued by a separate post-ratings stage, stored in its own table, exposed read-only, covered by the permanent alarm, and documented. The rating path (G6 `ml`, exit code, `city_rating`, `latest_rating`) is untouched by the diff and structurally isolated by the exit-code-first ordering, with tests and live evidence.

Schema-drift gate note: the bypass (false positive, owner-approved after a live dry run found nothing pending) is accepted; the live evidence (applied migrations, 29/29 and 7/7 checks, pinned sha256 tests matching the applied files) supports it.

---

_Verified: 2026-11-09_
_Verifier: Claude (gsd-verifier)_
