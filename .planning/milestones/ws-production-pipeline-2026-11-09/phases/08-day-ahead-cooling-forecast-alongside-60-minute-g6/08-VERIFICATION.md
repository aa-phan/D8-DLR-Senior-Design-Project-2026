---
phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6
verified: 2026-11-09T18:30:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - ".github/workflows/day_ahead_manifest_check.yml"
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
  - "docs/data-science/decisions/dlr_live_runbook.md"
  - "docs/data-science/decisions/pss_e_handoff.md"
  - "docs/data-science/schema/day_ahead_forecast_v1.md"
  - "docs/integration/examples/curl.sh"
  - "docs/integration/examples/read_ratings.py"
  - "docs/integration/examples/supabase_js.mjs"
  - "docs/integration/rest-api.md"
  - "docs/integration/software-team-handoff.md"
  - "supabase/migrations/20261108120000_day_ahead_forecast_store.sql"
  - "supabase/migrations/20261108120100_expose_day_ahead_forecast.sql"
  - "supabase/ops/verify_day_ahead_store.sql"
  - "supabase/ops/verify_exposure.sql"
covered_digest: "v3:sha256:cb397fed19b15056181e853091fd6d8ac0175a6010c0e5848ed2699c2cde07a3"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 8: Day-Ahead Cooling Forecast Alongside 60-Minute G6 Verification Report

**Phase Goal:** Production serves a day-ahead (24 h) ampacity forecast per city from `ml_cooling_corrected` as an additional output alongside the 60-minute G6 forecast, which stays `ml` and keeps gating G6. The day-ahead value is labelled as a higher-error future forecast (it carries more error because it is further ahead, like any forecast), with its own uncertainty band, and never replaces or gates the live rating.
**Verified:** 2026-11-09
**Status:** passed (1 non-blocking warning, WR-06, a comment-wording issue; 14 info items carried from 08-REVIEW.md)
**Re-verification:** Yes. The earlier report (covering 08-01..08-12) was stale because the code-review fixes WR-01..WR-05 and two follow-ups changed covered files. This run re-read the code at HEAD (d2942dc) and re-ran the day-ahead tests; it did not trust SUMMARY.md, the earlier report or the review text. The previous report had no `gaps:`, so every truth was re-checked against the current code, with extra weight on the files the fixes touched.

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Every hourly run after go-live issues each due target per city from the 24 h-old weather run through the unchanged shadow functions under the production conductor, parity-tested, and publishes nothing when cooling cannot produce a value | VERIFIED | `day_ahead_forecast.compute_value` (read in full) calls only `shadow.fetch_live_forecast_for_valid_time`, `validate_and_prepare_shadow_row`, `_enrich_city_frame_for_correction` and `CoolingCorrectionShadowMethod(model).predict(frame, point)`, with `point = city_point.production_city_point(city)`. The model comes from hash-verified `fcr.make_headline_loader` (`make_model_loader`). Every failure is wrapped by `_step` into `DayAheadNotIssued`; no other method is named (a source-scan test enforces it). `due_targets` returns the 6 h grid targets in (now, now + 24 h - publication lag]; `dlr_day_ahead._execute` issues `missing = due - existing`, so a missed target is caught up by a later run, and a target in the past is never due. `forecast_run_init_time = valid_time - 1440 min`, enforced again by a DB CHECK. Tests present and passing in my run: `test_parity_production_equals_the_shadow_path_where_the_conductor_matches[CORPUS_CHRISTI/MIDLAND/EL_PASO]`, `test_parity_austin_equals_the_same_chain_with_the_refit_model_and_differs_from_drake`, nine `test_no_substitute_*` tests in `day_ahead_forecast_test.py` and five in `dlr_day_ahead_test.py`. `dlr_live_run.main()` passes `day_ahead=MAIN_RUNS_DAY_AHEAD and not args.no_day_ahead`, and `MAIN_RUNS_DAY_AHEAD = True`. Live evidence (recorded file, not re-contacted): `08-08-first-slot.json` shows run 42543631399 wrote 12 rows, ml_cooling_corrected, horizon 1440, model sha equal to the manifest. |
| 2 | Every row carries a 5-95% band (TEST artifact at launch, live rolling per band once 60 graded pairs exist), its source and size, model and band hashes, config identity, issue time and the label | VERIFIED | `build_row` emits exactly `contract.INSERT_COLUMNS` (and raises if the keys differ): `band_source`, `band_n`, `band_pairs_through`, `band_artifact_sha256`, `cooling_model_sha256`/`source`, `config_version`/`config_fingerprint`, `issued_at`, `label = DAY_AHEAD_LABEL`. Migration CHECKs enforce label non-empty, sha formats (64 lowercase hex), band contains the point, `band_pairs_through` NULL iff `live-rolling`, `issued_at < valid_time`. `band_for` starts on the hashed TEST offsets (`data/day_ahead/day_ahead_bands_v1.json`, sha256 19b9c522... equals the manifest entry, checked by hand), switches per (city x UTC hour) to `live-rolling` at `LIVE_BAND_MIN_PAIRS = 60` using the newest `LIVE_BAND_WINDOW = 120` pairs, only when the 5% offset < 0 < the 95% offset. `_LIVE_PAIRS_SQL` keeps only status ok, not fallback, not exhausted, origin live, same fingerprint and model, target before the decision time. WR-01 fix verified in code: `band_for` wraps `_live_offsets` in `try/except Exception`, keeps the TEST band, logs only the exception type; the connection is autocommit (`supabase_store.connect`), so a failed query cannot poison the following insert. Pinned by `test_a_failing_live_query_falls_back_to_the_test_band_and_logs_only_the_exception_type` and an end-to-end test in `dlr_day_ahead_test.py` (both passed against local Postgres). The live-rolling switch has only been exercised on local Postgres (production has no 60 pairs yet; expected). |
| 3 | Live ratings, G6 `ml` forecast, exit code, `city_rating` and the 34-column `latest_rating` are unchanged; a day-ahead failure or bad file never stops or reddens a run and is recorded in `pipeline_run.day_ahead` | VERIFIED | `git diff 01c383d..HEAD` (code, non-docs) shows no change to `ampacity_forecast.py`, `city_pipeline.py`, `config.py`, `dlr_orchestrator.py` or `.github/workflows/dlr_live.yml`, and `grep day_ahead` finds nothing in them. The only edits to shared files are additive: `supabase_store.upsert_run` accepts an optional `day_ahead` column that the rating-stage rows never name, `live_run_log.build_day_ahead_run_row` (own `{run_id, day_ahead}` write), and `supabase_smoke` (narrowed a policy lookup to the two original tables). In `run_live`, `state["exit_code"]` is set at line 628 and the comment at 631 states nothing after may assign it; `_day_ahead_after_ratings` has its own `except Exception` around the stage and around the write, and never assigns `exit_code`, `cities` or `run_log`. Per-city children run under the shared 4 x 300 s budget, killed at `min(DAY_AHEAD_CITY_TIMEOUT_S, remaining)`. The write-side migration only adds `pipeline_run.day_ahead jsonb` (`add column if not exists`); no `city_rating`/`latest_rating` migration is edited. The stage tests (`dlr_live_day_ahead_stage_test.py`) passed in my run. |
| 4 | After the first live issue run is verified, anon reads the upcoming targets and a four-row status and nothing else new, writes are refused, and the permanent alarm also fails for a stalled feed | VERIFIED | Expose migration read in full: `day_ahead_upcoming` (25 stored columns + `lead_minutes` = 26, `valid_time > now()`, ordered), `day_ahead_status` (7 columns, four hard-coded cities, so always four rows), both `security_invoker`, `revoke all` then `grant select` only, one SELECT policy on the table; `dlr_writer` holds select + insert only (write-side migration); `assert_fresh` has the same signature and adds a `day_ahead_late` clause that raises PT503 only when `exists(select 1 from day_ahead_forecast)` (armed by the first row) and a city has a target missing within 12 h. No new cron job. "Nothing else new" holds with one documented reading: the base table `day_ahead_forecast` is also anon-readable (OD-6 owner decision: full history public; the security_invoker views need it, same pattern as `city_rating` + `latest_rating`); the contract doc lists it as a read endpoint. Order honoured (first run verified in 08-08 before the expose migration applied in 08-11). Recorded live evidence `08-11-live-checks.json`: 8/8 checks ok (12 future ordered rows, 26 columns, four cities none late, `assert_fresh` 200 with `day_ahead_armed` true, anon INSERT refused 42501, view write refused, `pipeline_run` hidden). `day_ahead_expose_test.py` passed in my run, including the full-message pin for the PT503 case (WR-04 fix). The 503 stall path is exercised on local Postgres only; a live stall would be a real incident. |
| 5 | The contract states the label, the owner-approved paragraph, the band and late rules and the meaning of "24 h", and is published only after the expose step, together with the three consumer examples (which also read the day-ahead targets and status and ran live first) and the Software and PSS/E handoff notes | VERIFIED | `docs/integration/rest-api.md` carries the label, the paragraph ("It has more error than the 60-minute forecast because it looks further ahead ... never sets or checks the live rating"), band and late rules, "24 h" as the weather run's age, and the column tables (guarded by `rest_api_doc_test.py`, passed). WR-02 fix present in the consumer docs: they state the 18 h lookahead and at most three upcoming targets per city. All three examples read `day_ahead_upcoming` and `day_ahead_status` and print the label (`curl.sh` lines 62-71, `supabase_js.mjs` 80-110, `read_ratings.py` 183-262, the 49131d4 fix confirmed). Required env is only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`; the optional `CITY`/`START`/`END` knobs are pre-existing (identical at 01c383d) and not secrets. `grep` for project URLs/keys in the examples finds none; `read_ratings.py` header states Python 3.7+ standard library. Live runs recorded in `08-11-examples.json` (exit 0). The expose-before-publish order is recorded in the 08-11 summary and pre-flight; I did not re-contact git remotes or the live service. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/day_ahead_forecast.py` | due targets, value, row, insert | VERIFIED | 299 lines, read in full; real logic, wired via `dlr_day_ahead._issue` |
| `backend/day_ahead_band.py` | TEST artifact guards, live rolling band, WR-01 fallback | VERIFIED | 420 lines; `load_verified_band` hashes before parsing; `band_for` fallback present |
| `backend/dlr_day_ahead.py` | per-city child | VERIFIED | 303 lines; started by `dlr_live_run.day_ahead_child_argv` |
| `backend/dlr_live_run.py` (stage) | stage after exit code | VERIFIED | `_day_ahead_after_ratings`, `run_day_ahead_stage`, budget constants |
| `backend/live_run_log.py`, `backend/supabase_store.py` | `pipeline_run.day_ahead` write | VERIFIED | additive, optional column, separate upsert |
| `data/models/LIVE_ARTIFACT_HASHES.sha256`, `data/day_ahead/day_ahead_bands_v1.json` | manifest lists the band file, AUSTIN refit and 3 frozen cooling models | VERIFIED | diff read; band file sha matches its manifest line |
| `backend/dlr_live_check_models.py` | warn-only pre-flight tier | VERIFIED | `dlr_live_check_models_day_ahead_test.py` passed |
| `.github/workflows/day_ahead_manifest_check.yml` | offline guard in CI (WR-05) | VERIFIED | read in full; runs the guard test, fails on any skip, `contents: read`, no secrets; reported green on GitHub (33 passed) |
| `supabase/migrations/20261108120000_*` | write-side table, RLS, writer select+insert only | VERIFIED | read in full |
| `supabase/migrations/20261108120100_*` | views, SELECT-only grants, `assert_fresh` clause | VERIFIED | read in full |
| `backend/day_ahead_verify.py`, `supabase/ops/verify_*.sql` | owner checks | VERIFIED | covered by `day_ahead_verify_test.py` (passed) |
| `docs/integration/examples/*`, rest-api, handoff docs | consumer handoff | VERIFIED | see truth 5 |

### Key Link Verification

| From | To | Via | Status |
|------|----|-----|--------|
| `dlr_live.yml` | `dlr_live_run.main()` then `run_live(day_ahead=True)` | `MAIN_RUNS_DAY_AHEAD` | WIRED (workflow file unchanged since 01c383d) |
| `run_live` | `dlr_day_ahead.py` child per city | `run_day_ahead_stage` / `day_ahead_child_argv` | WIRED |
| child | `public.day_ahead_forecast` | `insert_row`, `ON CONFLICT (city, valid_time) DO NOTHING` | WIRED |
| runner | `pipeline_run.day_ahead` | `build_day_ahead_run_row` + `upsert_run` | WIRED |
| `day_ahead_status` | `assert_fresh` | `from public.day_ahead_status` in the function body | WIRED |
| band | `city_rating` | `_LIVE_PAIRS_SQL` join | WIRED (tested on local Postgres; not yet live-exercised) |
| band artifact | manifest | `load_verified_band` (hash before parse) and CI guard | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `day_ahead_upcoming` rows | `forecast_amps`, band edges | shadow cooling model on the 24 h-old Open-Meteo run + station anchor, band from the hashed TEST artifact | Yes (12 live rows with distinct amps in `08-08-first-slot.json`) | FLOWING |
| `day_ahead_status` | `missing_targets`, `is_late` | table contents | Yes (four rows live, none late in `08-11-live-checks.json`) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Day-ahead, live-runner, REST doc, examples, expose, runbook, conductor and parity tests | `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest backend/tests -k "day_ahead or dlr_live or rest_api or example or expose or runbook or production_conductor or parity" -q -p no:cacheprovider` | 529 passed, 0 skipped, 0 failed (2473 deselected) | PASS |
| Full suite (reported by the caller, not re-run by me) | `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest backend/tests` at HEAD | 3002 passed, 0 skipped, 0 failed (reported) | PASS (reported) |
| Live first slot / expose / examples / UAT | recorded evidence `08-08-first-slot.json`, `08-11-live-checks.json`, `08-11-examples.json`, `08-UAT.md` (53/53 passed) | all ok | PASS (recorded artifacts; no live service or `.env` touched by me) |

### Probe Execution

No probe scripts are declared by the phase plans. Step 7c: SKIPPED (not applicable).

### Requirements Coverage

Every `requirements:` ID in the 12 PLAN frontmatters is in REQUIREMENTS.md, and REQUIREMENTS.md maps exactly DAY-01..DAY-09 to Phase 8. None are orphaned. The traceability table marks all nine Complete.

| Requirement | Source plans | Status | Evidence |
|-------------|--------------|--------|----------|
| DAY-01 per-target issue, catch-up, nothing after the target | 08-01, 08-04, 08-08 | SATISFIED | `due_targets`, `missing_targets`, `existing_targets`; CHECK `issued_at < valid_time`; 12 live rows |
| DAY-02 unchanged shadow functions, hash-verified loader, parity, manifest, warn-only pre-flight, offline mismatch test | 08-01, 08-04, 08-05 | SATISFIED | `compute_value`, parity tests, manifest diff, day-ahead pre-flight tier, CI workflow |
| DAY-03 5-95% band, TEST then live rolling, source and n recorded | 08-01, 08-03 | SATISFIED | `band_for`, `_LIVE_PAIRS_SQL`; live rows test-split n=196 |
| DAY-04 never delays/changes ratings; exit code fixed first; `pipeline_run.day_ahead`; shared budget | 08-02, 08-05, 08-06, 08-08 | SATISFIED | `run_live` ordering, `_day_ahead_after_ratings`, stage tests |
| DAY-05 additive store migration, writer select+insert, RLS, unchanged `city_rating`/`latest_rating` | 08-01, 08-04, 08-07 | SATISFIED | migration 20261108120000 read in full |
| DAY-06 expose views and contract docs | 08-09, 08-10, 08-11, 08-12 | SATISFIED | migration 20261108120100, rest-api.md |
| DAY-07 `assert_fresh` day-ahead 503 clause, armed by first row, no new cron | 08-09, 08-10, 08-11 | SATISFIED | function body; `day_ahead_expose_test.py`; live 200 with `day_ahead_armed` true |
| DAY-08 owner-gated go-live order | 08-02, 08-06..08-11 | SATISFIED | summaries and evidence files record write migration, push, first-run verification (08-08), then expose and publish (08-11); not independently re-derived from the remote |
| DAY-09 consumer examples and handoff docs, run live before the publishing push | 08-11, 08-12 | SATISFIED | examples read in full; `08-11-examples.json` exit 0; docs tests passed |

### Anti-Patterns Found

TBD/FIXME/XXX scan over the phase's Python, SQL, workflow, example and doc files: none. TODO/HACK/PLACEHOLDER scan over the day-ahead modules: none. The `except Exception` blocks in the stage and band fallback are deliberate, named, and log only exception types or redacted text. No stubs or hollow props.

### Warnings (non-blocking)

| ID | Concern | Weighs on goal? |
|----|---------|-----------------|
| WR-06 | The CI workflow header and one test comment say a manifest mismatch "fails hard, before it reaches main". The job also runs on direct pushes to main, and nothing blocks a merge until the owner sets "Day-ahead manifest check" as a required status check. The code and the workflow behave correctly; only the comment overstates. | No. Comment rewording; optional runbook checklist item. |

Info items IN-01..IN-14 in 08-REVIEW.md are cosmetic, doc or hardening notes; none affects a must-have. Two worth keeping in view: the `missing` field reads empty for timeout/crash day-ahead records (IN-01), and the live-rolling band and 503 stall paths have only local-Postgres evidence.

### Human Verification Required

None. 08-UAT.md is complete (53/53 passed, including the owner running the live curl example and the 8/8 REST check). Informational only: the live-rolling band switch (first possible when 60 graded pairs exist, about January 2027) and the 503 stall path have not occurred in production.

### Gaps Summary

No gaps. The goal is achieved in the codebase: a day-ahead `ml_cooling_corrected` value per city, labelled as a higher-error, engineering-selected, not-validated forecast with its own empirical 5-95% band, is issued by a separate post-ratings stage through the unchanged shadow functions, stored in its own table (first write wins), exposed read-only, covered by the permanent alarm, and documented. The rating path (G6 `ml`, exit code, `city_rating`, `latest_rating`) is untouched by the diff and structurally isolated by the exit-code-first ordering, with tests and recorded live evidence. The code-review fixes WR-01..WR-05 are present in the code and each is pinned by a passing test or a read-through of the changed file.

---

_Verified: 2026-11-09_
_Verifier: Claude (gsd-verifier)_
