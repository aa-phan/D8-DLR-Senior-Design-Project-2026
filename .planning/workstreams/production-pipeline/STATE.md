---
gsd_state_version: "1.0"
current_phase: 04
current_plan: 3
status: executing
stopped_at: Completed 04-02-PLAN.md
last_updated: "2026-10-21T23:09:51.416Z"
last_activity: 2026-10-21
last_activity_desc: Phase 04 execution started
state_head: 9e9d2250a8afc9ff0c64749974ee84fa131baaef
progress:
  total_phases: 7
  completed_phases: 3
  total_plans: 35
  completed_plans: 16
  percent: 43
milestone_name: Production Pipeline (Supabase + live ratings)
workstream: production-pipeline
created: 2026-10-18
current_phase_name: Supabase Store & Writer
---

# Project State

## Project Reference

See: this workstream's REQUIREMENTS.md and ROADMAP.md (both 2026-10-18).

**Core value:** Every city's dynamic rating is computed on a schedule, stored in Supabase Postgres,
and readable by the other teams at any time through a read-only REST interface.

**Scope note (owner, 2026-10-18):** this workstream strings the system together end to end. It
does not analyze the ratings themselves. Observations about output values are recorded below for
whoever owns that analysis; they are not work items here.

## Current Position

**Status:** Ready to execute
**Current Phase:** 04
**Current Plan:** 3
**Total Plans in Phase:** 6
**Last Activity:** 2026-10-21 — Phase 04 execution started
**Last Activity Description:** Phase 04 execution started

## Planning Summary (2026-10-19)

| Phase | Plans | Check | Revisions |
|-------|-------|-------|-----------|
| 1 Land PR #7 | 5 | passed | 0 |
| 2 Data Cleaning | 4 | passed | 1 (CSV first-write-wins marked CSV-only; Postgres follows OD-7) |
| 3 Real-Data Validation | 5 | passed | 0 |
| 4 Supabase Store & Writer | 6 | passed | 1 (pre-push manylinux wheel check for the psycopg pins) |
| 5 Scheduled Live Runs | 8 | passed | 1 (phase-wide secret scan; binary permanence shown at push) |
| 6 Exposure & E2E | 7 | passed | 1 (72 h soak starts only after the dry-soak review) |

Execution order is 1 → 2 → 3 → 4 → 5 → 6. Each phase's preconditions check the previous one.

**Cross-phase notes:**
- **Conflict rules:** the CSV archive is first-write-wins (Phase 2, for backfill resume). The Postgres `city_rating` upsert is `ON CONFLICT (city, valid_time) DO UPDATE` with `first_written_at` immutable (OD-7, Phase 4). The DB-03 backfill loader uses DO NOTHING, so it never overwrites live rows.
- **Phase 2 edits Phase 1's tests:** it changes fixture data in Phase 1's `city_pipeline_test.py` and in `predictive_tracer_test.py`. Assert lines stay pinned to the last `test(01-03)` commit.
- **Phase 5 extends Phase 1's pinned tests:** it adds to the pinned key lists in Phase 1's tests and removes no assertion. Each city runs in its own child process, so a station-discovery abort stays per city, and the behaviour pinned by Phase 1's orchestrator test is unchanged.
- **Phase 6 permissions:** Phase 6 revokes every anon/authenticated privilege in `public`, then grants SELECT on `city_rating` and `latest_rating` only. The `dlr_writer` role is untouched.

**Owner risks to settle before go-live:**
- **Actions minutes:** the repo is PRIVATE. Hourly live runs are estimated at about 2,900-4,300 min/month on top of about 600-660 for Shadow Collection. Running out of minutes stops every workflow, including Shadow Collection, before 2026-11-24. Plan 05-06 reads the real quota and offers "hold".
- **requirements.txt push:** adding psycopg affects Shadow Collection's install. Plan 04-06 gates the push on a manylinux cp312 wheel check.
- **Cold start:** the backfill window ends 2026-09-28, which is outside the 30-day read window by go-live. A fresh backfill before go-live avoids the cold start (raised in 04-05).
- **Wind feature mismatch:** the ml forecast was trained on measured wind but reads projected wind from the archive. Phase 3 records this as a finding with options for the owner.

## Phase 1 Progress

| Req | Status | Evidence |
|-----|--------|----------|
| LAND-01 | Done | 151aac2: files at `backend/` / `docs/` paths, LF, root `dlr_pipeline.py` dropped. 5efe97d removed the `backup/` upload |
| LAND-02 | Done | b1e1d7b (19 `city_rating_test` fixtures get `wind_direction`), e330570 (cron test now checks the cron-job.org dispatch). Suite: 1236 passed, 0 failed |
| LAND-03 | **Open** | No tests yet for `observation_composer`, `city_pipeline`, `dlr_orchestrator`, `backfill_archive` |
| LAND-04 | Done | Amendments in `docs/data-science/PRD.md` §7.1 and `decisions/data_provider.md` |
| PIPE-01 | Done (live) | 2026-10-19 ~04:25Z `dlr_orchestrator --no-archive`, run by the owner: all 4 cities rated through composed weather → projection → G1-G6 |

**History note:** PR #7 was merged on GitHub at 35939cc (root-level uploads plus `backup/`) before
the restructured branch was pushed. Main was then fast-forwarded to 5efe97d, whose tree equals the
restructured branch (e330570) and contains no `backup/`. PR #8 (an accidental auto-revert of #7)
was closed and its branch deleted.

## Integration Items Found in the Live Run (2026-10-19)

These block or affect stringing the system together and belong to the phases named.

1. **Anomaly models are not available outside the main checkout** (Phase 4/5). `data/models/` is
   git-ignored, so the worktree run logged "no trained anomaly model" for all 4 cities, and a
   GitHub Actions runner will hit the same thing. The live workflow needs a way to provision
   `data/models/anomaly_{CITY}.joblib`: commit them, download a release/artifact, or train in CI.
2. **`dlr_orchestrator` does not load `.env`** (Phase 1 follow-up or Phase 5). Local CLI runs need
   the variables exported. `.env` uses `KEY = value` spacing that `source` rejects, so loading it
   through python-dotenv works. Actions will pass secrets as env vars, so this only affects local
   runs. Option: call `load_dotenv()` in `main()` as `forecast_shadow_pipeline.py` does.
3. **NSRDB fails 3 times per run for current windows** (Phase 5). It has no 2026 data (HTTP 400),
   so each live run spends 3 calls before the circuit breaker skips it. Option: skip NSRDB when
   the window is past its coverage.
4. **Stray `print` output** (Phase 5, log hygiene): `SUMMARY:`, `Returned stations`, `OBS keys`
   (Synoptic helpers) and `G4 FAIL ...` (`DLRSafetyMonitor`) go to stdout alongside logging.
   Backfill already redirects stdout to count gate failures, so a change here must keep that
   working.
5. **Cold start** (Phase 4, DB-03): 0 history rows for every city, so no forecast. Expected without
   an archive. The backfill load covers it.

## Output Observations (recorded only; not analyzed in this workstream)

- AUSTIN: computed 1080 A was below its lower bound (`config.RATING_BOUNDS_BY_LOCATION` 1150 A),
  so G4 fell back to the static 1825 A, a higher value than computed. MIDLAND's lower bound
  (1250 A) has the same exposure. Flagged for the owner of rating bounds and fallback policy.
- Other cities: CORPUS_CHRISTI 1259 A (static 1500), MIDLAND 1912 A (1875), EL_PASO 1048 A (1320).

## Decisions

- 2026-10-18: Supabase Postgres as the store, Supabase REST as the read interface, cron-job.org →
  `workflow_dispatch` as the trigger. The DS team holds decision authority on integration
  architecture.
- 2026-10-18: Supersedes the corridor-era `pipeline-integration` workstream.
- 2026-10-18: The workstream's job is to string the system together, not to analyze output values.
- [Phase 01]: 01-01: offline seams for Phase 1 tests are autouse _no_network (records requests.get attempts, asserts empty at teardown) and _offline_env (credentials unset, anomaly model loader patched to None, default archive redirected to tmp_path); stub providers via oc.<provider>.fetch_* with fixed timestamps
- [Phase 02]: Cleaning is a read-time view: clean_flags/clean_excluded live on the cleaned frame only, never persisted (ARCHIVE_COLUMNS is imported by forecast_training and the shadow collection)
- [Phase 02]: CSV append is first-write-wins on the exact (city, UTC instant); CSV-only, differs on purpose from OD-7 (Postgres: hour-slot key, retry overwrites)
- [Phase 02]: A clean_history exception gives forecast and detector an empty history (cold start), not unvetted history
- [Phase 02]: 02-02: historical_archive._parse_utc parses explicit-offset and naive timestamps in separate batches (pandas 2.3 carries an earlier offset into a later naive value); same defect in data_cleaning._parse_utc deferred to 02-03
- [Phase 02]: 02-03: Mark, never fill - a missing hourly slot is never imputed; the next usable row carries after_gap and gap_slots and the report measures missing, trailing and contiguous-tail slots for 02-04
- [Phase 02]: 02-03: at_or_after_run excludes rows whose slot is at or after as_of's slot, so reruns and out-of-order backfills have no look-ahead
- [Phase 02]: 02-03: stuck (6 rows, solar 0.0 exempt) and spike (10 degC, 10 m/s, 700 W/m2 per hour) thresholds are provisional and unfitted; Phase 3 measures flag rates; each rule family judges its fields against one shared row set
- [Phase 02]: A forecast is withheld from G6 when the newest usable row is more than 1 hourly slot before the run, or (ml only) when fewer than 7 newest usable rows sit on consecutive hours; both provisional until Phase 3
- [Phase 03]: Phase 03-01: rate denominators are the expected steps of the period, so exhausted, errored, untraced and missing steps stay in every rate
- [Phase 03]: Phase 03-01: a G4 fallback whose recomputed ampacity is inside the bounds is classed ERROR and counted as a computed-vs-reported mismatch
- [Phase 03]: Phase 03-01: archive rows without a trace record are NO_TRACE in outcomes and completeness, not archive-vs-trace mismatches
- [Phase 03]: 03-03: VAL-02 coverage population n_band = scored steps that reached G6 with a positive-width forecast band and a computed rating (used by G6 or withheld across a gap); every other step is counted in its own column
- [Phase 03]: 03-03: replay is a counterfactual reference (same traced observations, different forecast method), refuses without anomaly models or over existing outputs, and is gated by replay_fidelity mismatches == 0
- [Phase 03]: 03-02: real backfill window 2026-09-08..09-28 (168 h warm-up, 14 scored days) ran complete for all four cities with ml forecast; manifest pins archive sha256 18f999aa... and 504 rows per city for the Phase 4 DB-03 load
- [Phase 03]: 03-04: AUSTIN publishes above computed at 68.15% of scored steps (median +780 A), MIDLAND 20.83%: measured, findings and options recorded for the owner, no policy changed
- [Phase 03]: 03-04: the validation doc leaves the Decision section as 'Pending owner decision.'; GO / GO WITH CONDITIONS / NO-GO is taken at 03-05's checkpoint
- 2026-10-21: VAL-03 production go/no-go: NO-GO, signed by Aaron Phan (docs/data-science/decisions/real_data_validation.md).
- 2026-10-21: B6 (Finding 5, input provenance): owner accepts Open-Meteo reanalysis solar (Option A) and asks for it to be documented. Phase 4 input: the schema carries a per-row solar source column. Before Phase 5: confirm the Open-Meteo Archive API serves the current hour, else add a near-real-time solar source.
- [Phase 04]: valid_time is the hour-truncated UTC run slot (CHECK-enforced); upsert is ON CONFLICT (city, valid_time) DO UPDATE with first_written_at never updated (OD-7) — A same-hour retry must overwrite, not duplicate
- [Phase 04]: DB-06 identity: automatic per-city sha256 config_fingerprint plus model-file hashes on every row; RATING_CONFIG_VERSION v1-provisional-2026-10-13 is its label — Fingerprint is authoritative; a conductor or model change alters values, never the schema
- [Phase 04]: connect() pins session time zone to UTC; dlr_writer is policy-based (no BYPASSRLS) with no credential in the migration — Hour CHECK truncates in session zone; least privilege (DB-04)
- [Phase 04]: 04-02: forecast_status describes the forecast call (ok/cold_start/failed), not G6 use; a forecast withheld by the gap guard stays ok
- [Phase 04]: 04-02: with a store the orchestrator runs each city with archive=False and writes the rating row itself; a failed city or failed write has no row (OD-9) and is recorded in pipeline_run as error; written-but-unhealthy is degraded
- [Phase 04]: 04-02: Phase 5 children use --store postgres --no-run-row; row-written flag is summary archived; upsert_run(conn,row) takes any subset of PIPELINE_RUN_COLUMNS with run_id

## Open Decisions

None open. OD-1 to OD-10 were decided on 2026-10-19 (REQUIREMENTS.md "Owner decisions"):
- OD-1 to OD-5: hourly cadence, composed providers, ml forecast, 30-min grace, labelled provisional.
- OD-6: public history.
- OD-7: hour-slot `valid_time`; a retry overwrites.
- OD-8: 30-day read window.
- OD-9: a failed city appears in the run log only.
- OD-10: models committed to git.

## Blockers

- VAL-03 NO-GO (2026-10-21) blockers B1 (fallback policy and rating basis: conductor type, max operating temperature, elevation, azimuth; with Power Systems), B2 (ml wind feature train/serve alignment), B4 (CORPUS_CHRISTI detector trip rate 11.01%) and B5 (fallback effect on forecast availability) now gate only lifting the provisional label (re-sequenced by the owner 2026-10-21; closed in Phase 7, REVAL-01). Phases 4-6 are no longer blocked. See docs/data-science/decisions/real_data_validation.md.
- Phase 7 external gate: Power Systems' per-city conductor answers (provisional values with sources until then). Protocol v4 must be signed before any FRESH-basis outcome is read; until then v3 (2026-11-24) governs. Options and conductor analysis: docs/data-science/decisions/shadow_early_decision_options.md.
- Superseded (2026-10-21): the earlier timing note that B1/B2 wait for 2026-11-24. Phase 7 decouples the production conductor from the frozen shadow path (COND-02) and moves the evaluation to about 2026-11-01 under v4.

## Session Continuity

**Last session:** 2026-10-21T23:09:51.317Z

**Stopped At:** Completed 04-02-PLAN.md
**Resume File:** None

## Performance Metrics

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 8 min | 2 tasks | 1 files |
| Phase 01 P02 | 25min | 2 tasks | 1 files |
| Phase 01 P03 | 8min | 2 tasks | 1 files |
| Phase 01 P04 | 6 min | 2 tasks | 1 files |
| Phase 01 P05 | 9 min | 2 tasks | 0 files |
| Phase 02 P01 | 22 min | 2 tasks | 6 files |
| Phase 02 P02 | 9 min | 2 tasks | 2 files |
| Phase 02 P03 | 40 min | 3 tasks | 5 files |
| Phase 02 P04 | 6 min | 2 tasks | 4 files |
| Phase 03 P01 | 15 min | 3 tasks | 4 files |
| Phase 03 P03 | 12 min | 2 tasks | 3 files |
| Phase 03 P02 | 336 min | 3 tasks | 2 files |
| Phase 03 P04 | 14min | 2 tasks | 13 files |
| Phase 03 P05 | 6min | 2 tasks | 2 files |
| Phase 04 P01 | 55 min | 3 tasks | 8 files |
| Phase 04 P02 | 10 min | 3 tasks | 8 files |

## Accumulated Context

### Roadmap Evolution

- Phase 7 added: Per-City Conductors, Shadow Refit and Early Model Selection (protocol v4 retires the 2026-11-24 run; selection by 2026-11-01; parallel with 4-6)
- Phase 4 edited: NO-GO no longer blocks Phases 4-6 (owner 2026-10-21); rows provisional until Phase 7 GO; DB-06 config/model identity per row; 04-01 precondition needs re-plan
- Phase 6 edited: Not gated on Phase 7; web app and PSS/E read provisional rows
