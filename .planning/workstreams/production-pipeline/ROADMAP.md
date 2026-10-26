# Roadmap: Production Pipeline (Supabase + live ratings)

## Overview

PR #7 connects the per-city pipeline (history → forecast → anomaly detector → `rate_city` →
archive) but nothing runs it, nobody has validated its output, and its archive is a local CSV. This
workstream:

1. lands PR #7 cleanly (Phase 1);
2. closes the gaps that block production: data cleaning (Phase 2) and real-data validation ending
   in a go/no-go (Phase 3);
3. moves storage to Supabase Postgres (Phase 4);
4. runs the pipeline on a cron-job.org schedule (Phase 5);
5. exposes the data through Supabase REST and proves end-to-end, always-fresh results (Phase 6);
6. in parallel with Phases 4-6, moves to per-city conductor configurations, refits the
   conductor-dependent shadow candidates and selects the forecast method by 2026-11-01 (Phase 7).

**Re-sequencing (owner, 2026-10-21).** The VAL-03 NO-GO no longer blocks the database. Supabase
(Phase 4) runs first because the web app and the PSS/E hand-off both depend on reading the data.
Conductor, model and forecast-method changes only alter the values the pipeline pushes, and every
row records the configuration and models behind it. Phases 4-6 therefore proceed with rows
labelled provisional (OD-5). The NO-GO now gates only lifting that label: Phase 7 closes B1, B2, B4
and B5, re-runs the Phase 3 validation and records a new go/no-go. Phase 7 has no dependency on
Phases 4-6 and starts now.

Phase numbering starts at 1 and is independent of other workstreams. It supersedes
`pipeline-integration` (see REQUIREMENTS.md).

**Why cleaning and validation come before Supabase:** `backfill_archive.py` (in PR #7) produces a
multi-day, multi-city archive without any scheduler, so the defects cleaning targets and the data
validation needs both exist before production storage does. Validating first means Phase 4 loads
history that has already been checked. (The original rule that the go/no-go comes before any shared
infrastructure was replaced on 2026-10-21; see "Re-sequencing" above.)

**Constraints that hold across every phase:**
- Do not modify `shadow_collect.yml`, the shadow logs, the 12 frozen Drake shadow artifacts or the
  frozen evaluation modules, except as a signed confirmation protocol v4 (Phase 7) explicitly
  allows. The live workflow is a separate file.
- Anti-peeking: no outcome for any shadow prediction with `valid_time` after 2026-09-29 is computed
  or read except in the single evaluation v4 defines, at the instant it defines. Until v4 is
  signed, protocol v3 (instant 2026-11-24T00:00Z) governs.
- Commit with explicit paths; ask before pushing anything that changes live CI.

## Phases

- [x] **Phase 1: Land PR #7** — relocate, fix tests, add tests, merge (completed 2026-10-19)
- [x] **Phase 2: Data Cleaning** — cross-row outlier, gap and duplicate handling on city history (completed 2026-10-20)
- [x] **Phase 3: Real-Data Validation** — ratings and calibration on backfilled data; production go/no-go (completed 2026-10-21)
- [x] **Phase 4: Supabase Store & Writer** — schema migration, Postgres read/write, backfill load, secrets (completed 2026-10-24)
- [ ] **Phase 5: Scheduled Live Runs** — new workflow, cron-job.org trigger, failure isolation, runbook
- [ ] **Phase 6: Exposure & E2E Verification** — REST via RLS, `latest_rating` view, soak test
- [ ] **Phase 7: Per-City Conductors, Shadow Refit and Early Model Selection** — protocol v4, per-city conductor configs, cooling/reference refit, selection by 2026-11-01, re-validation and go/no-go (parallel with 4-6)

## Phase Details

### Phase 1: Land PR #7

**Goal**: PR #7's integrated pipeline is on `main` at the correct paths, with a green suite and
tests for every new module.
**Depends on**: PR #7 author finishing their update (external gate)
**Requirements**: LAND-01, LAND-02, LAND-03, LAND-04, PIPE-01
**Success Criteria**:
  1. `git diff main...<merged>` shows changes only under `backend/`, `backend/tests/` and the two
     doc files. No root-level `.py` or `.md` files are added.
  2. `.venv/bin/python -m pytest -q -p no:cacheprovider` reports 0 failures, including the cron
     test that is currently red on `main`.
  3. `python backend/dlr_orchestrator.py --no-archive` runs for all four cities against live
     providers and prints a rating row per city. The owner runs this, because it needs `.env`.
  4. The re-review checklist from the 2026-10-18 review (relocation, CRLF, unchanged
     `dlr_pipeline.py`, 19 fixture failures, uncollected test, misplaced PRD amendment) is
     resolved item by item.
**Plans**: 5/5 plans complete

Plans:
- [x] 01-01-PLAN.md — Tracer: offline backfill -> orchestrator -> city pipeline -> composer run, plus backfill resume/log/interrupt tests (wave 1)
- [x] 01-02-PLAN.md — observation_composer tests: priority, same-hour alignment, fallback pass, wind pairing, circuit breaker, provenance (wave 2)
- [x] 01-03-PLAN.md — city_pipeline tests: fallback-row exclusion, forecast failure, degenerate band, pipeline key (wave 2)
- [x] 01-04-PLAN.md — dlr_orchestrator tests: per-city error isolation, validation, composed wiring, summarize, main exit code (wave 2)
- [x] 01-05-PLAN.md — Read-only evidence for LAND-01/02/04 and PIPE-01, plus the full suite with the new tests (wave 3)

### Phase 2: Data Cleaning

**Goal**: The history the forecast and detector consume is checked across rows and kept to one row
per slot.
**Depends on**: Phase 1
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03, CLEAN-04
**Success Criteria**:
  1. A cleaning step sits between `historical_archive.read_history` and `forecast_ampacity` /
     `AnomalyDetector.for_city` in `city_pipeline`. It flags stuck runs and spikes under a written
     policy.
  2. Missing hourly slots are handled by the documented strategy, and tests cover a skipped-cycle
     gap.
  3. Appending an already-present (`city`, `datetime_utc`) never creates a second row, for both
     `append_observation` and the orchestrator path (not only backfill). Exception (owner,
     2026-10-20): a computed row may follow a fallback row, and cleaning keeps only the computed one.
  4. Cleaned rows carry a marker (column or flag) that tells them apart from raw rows.

**Plans**: 4/4 plans complete

Plans:
- [x] 02-01-PLAN.md — Tracer: data_cleaning.clean_history wired into city_pipeline (timestamp, duplicate, fallback rules; clean_flags/clean_excluded markers), one archive row per (city, instant) on append, orchestrator rerun test (wave 1)
- [x] 02-02-PLAN.md — Archive tests for the one-row-per-slot guard (spellings, other cities, corridor-era files, unreadable files) and stable read order (wave 2)
- [x] 02-03-PLAN.md — Hourly-slot, gap, stuck-run and spike rules, gap_slots marker, and the written policy docs/data-science/decisions/data_cleaning.md (wave 2)
- [x] 02-04-PLAN.md — Forecast gap guard for G6 (stale history, ml lookback), skipped-cycle tests end to end, phase gate (wave 3)

### Phase 3: Real-Data Validation

**Goal**: Evidence that the pipeline's ratings and statistical methods are fit for production, and
a recorded go/no-go.
**Depends on**: Phase 2
**Requirements**: VAL-01, VAL-02, VAL-03
**Success Criteria**:
  1. A backfill over a stated real window (at least 14 days, all four cities) is run through the
     cleaned pipeline, and the window and command are recorded.
  2. A validation doc reports, per city: rating distribution against the static rating and bounds,
     fallback rate per gate, forecast-band empirical coverage, and detector flag rate, with
     explanations for outliers.
  3. A go/no-go decision is written and signed by the owner. On no-go, the blocking fixes are listed
     and Phase 4 does not start.
**Plans**: 5/5 plans complete

Plans:
- [x] 03-01-PLAN.md — Wave 1: backfill validation trace (`--trace-path`) and offline analysis CLI (completeness, manifest, VAL-01 report); phase tracer
- [x] 03-02-PLAN.md — Wave 2: preflight, owner runs the 2026-09-08..09-28 backfill (ml, composed), completeness + manifest committed (checkpoint)
- [x] 03-03-PLAN.md — Wave 2: VAL-02 band coverage and detector trip tables; offline naive replay with fidelity check
- [x] 03-04-PLAN.md — Wave 3: run replay + report on the hashed archive, commit tables, write the validation doc with go/no-go options
- [x] 03-05-PLAN.md — Wave 4: owner's go/no-go (blocking-human decision) recorded verbatim in the doc and STATE.md

### Phase 4: Supabase Store & Writer

**Goal**: Postgres on Supabase is the production system of record for per-city ratings.
**Depends on**: Phase 3 (complete). The VAL-03 NO-GO does not block this phase (owner, 2026-10-21);
rows are labelled provisional until Phase 7's go.
**Requirements**: DB-01, DB-02, DB-03, DB-04, DB-05, DB-06
**Success Criteria**:
  1. Applying the committed migration to an empty Supabase project creates the schema. Re-applying
     it is a no-op or fails safely.
  2. A pipeline run pointed at Supabase reads history from Postgres and upserts one row per city.
     Re-running the same window changes no row count.
  3. The Phase 3 backfill archive is loaded, labelled provisional, and per-city row counts match
     the Phase 3 archive.
  4. A GitHub-hosted runner can connect using only repository secrets. A secret scan of the repo
     finds no keys.
  5. The consumer schema doc is published under `docs/`, and `api-contract.md` /
     `pss_e_handoff.md` point to it.
  6. Every row names what produced it: a rating config version that changes with any per-city
     conductor parameter (type, diameter, resistance, maximum temperature, elevation, azimuth)
     as well as static ratings, bounds and bearings, plus the identity (hash) of the forecast
     method/model and anomaly model used. A conductor or model change therefore alters only the
     values pushed, never the schema.
**Re-plan note (2026-10-21, done)**: plans revised the same day: 04-01 no longer requires a Phase 3
GO, and DB-06 (`config_fingerprint`, `forecast_model_sha256`, `anomaly_model_sha256`) is covered
across 04-01..04-06. Plan checker: passed, info advisories only.
**Plans**: 12/12 plans complete (04-07..04-12: gap closure G-04-2, all 12 code review findings)

Plans:
**Wave 1**
- [x] 04-01-PLAN.md — psycopg legitimacy gate; tracer: migration, writer and history read for one city-hour on a throwaway Postgres; schema, privilege and secret-hygiene contract tests (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 04-02-PLAN.md — Pipeline seam: history reader and forecast_status in city_pipeline, `--store postgres` / `--no-run-row`, one pipeline_run row per run (OD-9), validated 30-day history (wave 2)
- [x] 04-03-PLAN.md — Manifest-checked backfill loader (DO NOTHING, per-city parity), smoke test, secret scan, dispatch-only Actions smoke workflow (wave 2)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 04-04-PLAN.md — Consumer schema contract `city_rating_v1.md`; api-contract.md and pss_e_handoff.md point to it (wave 3)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 04-05-PLAN.md — Owner: CLI legitimacy gate, schema approval, [BLOCKING] schema push, writer credential, local smoke (wave 4)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 04-06-PLAN.md — Owner: GitHub secret, approved push, Actions smoke, backfill load; executor verifies and commits the evidence (wave 5)

**Gap closure G-04-2** (owner, 2026-10-23: fix all 04-REVIEW.md findings in Phase 4)

**Gap Wave 1**
- [x] 04-07-PLAN.md — Store connection: CR-01 tracer (log the server role, not the pooler user, end to end from `main`), IN-02 stripped URL, WR-03 reconnect once (gap wave 1)
- [x] 04-08-PLAN.md — Run health: WR-01 postgres-store exit 1 on any failed city, WR-02 cleaning failure reported as failed forecast and degraded city (gap wave 1)
- [x] 04-09-PLAN.md — Additive migration 20261023000000 (IN-06 UTC hour CHECK, IN-03 run-log comments), smoke zone checks, IN-05 workflow hardening (gap wave 1)

**Gap Wave 2** *(blocked on 04-07 and 04-08)*
- [x] 04-10-PLAN.md — IN-01 1000-character run errors and count-preserving key redaction; IN-04 loader on the store's public helpers (gap wave 2)

**Gap Wave 3** *(blocked on 04-10)*
- [x] 04-11-PLAN.md — WR-04 computed-first backfill de-duplication; WR-05 fingerprint child decoupled via `rating_identity.py` (gap wave 3)

**Gap Wave 4** *(blocked on all gap plans)*
- [x] 04-12-PLAN.md — Owner: [BLOCKING] schema push of the new migration, local smoke, push and Actions smoke; executor records evidence and the 12/12 ledger (gap wave 4)

### Phase 5: Scheduled Live Runs

**Goal**: Ratings accrue in Supabase on a fixed cadence with no human involved.
**Depends on**: Phase 4. Live rows stay labelled provisional until Phase 7's go; adopting Phase 7's
conductor configs, refit models or forecast method later is a config/model swap, not a re-plan.
**Requirements**: PIPE-02, SCHED-01, SCHED-02
**Success Criteria**:
  1. A new workflow file, separate from `shadow_collect.yml`, has a `workflow_dispatch` trigger
     only, and cron-job.org calls it at the decided cadence (OD-1).
  2. Over 24 h, every scheduled slot has either a successful run or a visible failed run, and each
     successful run wrote one row per city.
  3. Forcing one city's provider to fail still lets the other three write, and the failure is
     recorded.
  4. The runbook covers the cron-job.org setup, pausing, changing cadence, and Actions-minute
     budget.
**Plans:** 8/8 plans executed

Plans:
- [x] 05-01-PLAN.md — Live runner (one orchestrator child per city, timeouts, exit policy, fault drill) and dispatch-only `dlr_live.yml` (tracer)
- [x] 05-02-PLAN.md — Forecast status/error and anomaly-model presence in run output, NSRDB skip for the current year, prints to logging, `.env` for script runs
- [x] 05-03-PLAN.md — Runner records every run and failed city in Phase 4's `pipeline_run` (OD-9)
- [x] 05-04-PLAN.md — Commit the eight live models via `.gitignore` carve-out (OD-10, main checkout) and run a SHA-256 pre-flight before rating
- [x] 05-05-PLAN.md — Runbook (cron-job.org, token scope, pause, cadence, minutes budget) and the 24 h window check
- [x] 05-06-PLAN.md — Owner: secrets and billing figures, go-live decision and push, first verified dispatch
- [x] 05-07-PLAN.md — Owner: cron-job.org hourly job; one-city fault drill in production
- [x] 05-08-PLAN.md — 24 h window evidence, measured Actions minutes, owner sign-off

### Phase 6: Exposure & E2E Verification

**Goal**: Consumers can read current ratings for every city at any time through a documented,
read-only REST interface.
**Depends on**: Phase 5. Not gated on Phase 7: the web app and PSS/E read provisional rows (the label
is visible per row), and Phase 7's go lifts the label.
**Requirements**: API-01, API-02, E2E-01, E2E-02, E2E-03
**Success Criteria**:
  1. `GET /rest/v1/latest_rating` with the anon key returns exactly four rows (one per city) with
     units documented.
  2. The `curl`, `supabase-js` and stdlib-`urllib` examples in the docs run as written and return
     data.
  3. A trace from cron-job.org trigger → Actions run → database rows → REST response matches values
     for all four cities.
  4. A ≥72 h soak shows every city's latest `valid_time` within the cadence plus grace (OD-4) at
     every probe. Breaches are listed with causes.
  5. Insert, update and delete attempts with the anon key are all rejected.

**Re-plan note (2026-10-25)**: plans rewritten for CONTEXT D-01..D-15 (34-column contract with
`age_minutes` / `is_stale` / `is_provisional`, dry soak from existing rows, probe smoke check, deploy
annotations, permanent alarm, env-var examples for Python 3.7+, secret-scan extension, post-10-30
re-check folding T-04-22). Offline build first (waves 1-3); every live step waits for 05-08's sign-off (D-06).
**Plans**: 13 plans

Plans:
**Wave 1**
- [ ] 06-01-PLAN.md — Tracer: `latest_rating` invoker view with the 34-column contract, SELECT-only grants, `assert_fresh`, real-label `is_provisional` and 90-minute boundary proofs on a local Postgres; `verify_exposure.sql`
- [ ] 06-02-PLAN.md — Secret scan catches the project host, pooler reference and publishable key; owner-local exact-value scan (D-10)
- [ ] 06-03-PLAN.md — Dry-soak export and report from the live rows written since 2026-10-25T00:00Z (D-07)

**Wave 2** *(blocked on Wave 1 completion)*
- [ ] 06-04-PLAN.md — Stdlib REST client with URL/key redaction, fake PostgREST, live read / hidden-table / write-rejection checks (API-01, E2E-03)
- [ ] 06-05-PLAN.md — `ops.freshness_log` soak migration reading `is_stale`, owner pg_cron scripts, probe smoke check

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 06-06-PLAN.md — REST contract `docs/integration/rest-api.md`, curl / supabase-js / Python 3.7+ examples (current rows and paged history), consumer-doc pointers
- [ ] 06-07-PLAN.md — 72 h soak report (breaches, causes, derived deploy annotations, owner annotations); runbook sections for the permanent alarm, soak monitoring and the 10-31 re-check
- [ ] 06-08-PLAN.md — E2E trace tool: cron-job.org execution → run → rows → REST (E2E-01)

**Wave 4** *(blocked on Wave 3 completion and 05-08 sign-off)*
- [ ] 06-09-PLAN.md — Owner: confirm the published contract, [BLOCKING] schema push of both migrations, live read/hidden/write checks

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 06-10-PLAN.md — Owner: 5-minute log, permanent freshness alarm and drill, probe smoke check, dry-soak report; go/no-go for the 72 h clock
- [ ] 06-11-PLAN.md — Owner: supabase-js legitimacy check, examples and E2E trace live, PSS/E interpreter question

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 06-12-PLAN.md — Owner: 72 h soak export and report, end-of-soak checks, sign-off, soak job removal (alarm stays)

**Wave 7** *(blocked on Wave 6 completion and 2026-10-31)*
- [ ] 06-13-PLAN.md — Owner: permission re-check after Supabase's 2026-10-30 grant change, with T-04-22's smoke

### Phase 7: Per-City Conductors, Shadow Refit and Early Model Selection

**Goal**: Each city is rated with its own conductor configuration; the conductor-dependent shadow
candidates are refit under it; and a signed, pre-registered procedure decides by 2026-11-01 which
shadow model, if any, replaces the `ml` forecast. That decision replaces the 2026-11-24 evaluation.
The phase ends with the NO-GO blockers closed and a new go/no-go.
**Depends on**: Phase 3 (findings B1, B2, B4, B5). Runs in parallel with Phases 4-6.
External gate: Power Systems' conductor answers. Provisional per-city values, each with a source,
are used until they arrive.
**Requirements**: COND-01, COND-02, SEL-01, SEL-02, SEL-03, SEL-04, REVAL-01
**Context**: `docs/data-science/decisions/shadow_early_decision_options.md` (options, conductor
analysis, proposed non-FRESH test); `confirmation_protocol_v3_per_city.md` (signed v3, which v4
amends); `real_data_validation.md` (B1-B5);
`phases/03-real-data-validation/03-05-CONDUCTOR-RESEARCH.md`. The amendment changes the
ml-modeling workstream's evaluation; record it in that workstream's STATE.md as well.
**Success Criteria**:
  1. Confirmation protocol v4 is signed by the owner before any FRESH-basis outcome is computed or
     read. It does all of the following:
     - retires the 2026-11-24 run;
     - fixes one early evaluation instant (2026-11-01T00:00Z, valid-time cutoff strictly before
       2026-10-25T00:00Z) and a pre-registered conditional re-test (instant 2026-11-08T00:00Z,
       cutoff 2026-11-01T00:00Z) that runs only if the first read names no winner (D-05, D-08);
     - names the evidence bases (ABLATION re-score, per-city TEST-split scoring, the FRESH read)
       and what each may support (FRESH decides; ABLATION and TEST only veto, D-02);
     - states the selection rule with a conductor-independent (relative) threshold (2% of the
       city's mean truth ampacity, D-06);
     - states the outcome if no candidate qualifies (no pick, then the conditional re-test, D-07).
  2. Per-city conductor configurations (conductor type, diameter, AC resistance, maximum operating
     temperature, elevation, azimuth) are in config with a recorded source per value. The production
     rating, training and validation paths use them. The shadow collector and the frozen
     evaluation keep the Drake configuration they were frozen with, proven by a byte-identical
     golden test. Power Systems' values replace provisional ones with a config-version bump and no
     code change.
  3. `ml_cooling_corrected` and `reference_ml_refit_24h` are refit per city under the production
     conductor configs when those differ from the frozen Drake configuration (D-10): for every city
     whose Power Systems values arrive by 2026-10-31T00:00Z, the two are refit on rows before
     2026-03-17 only (asserted) and saved as new, hashed artifacts; the 12 frozen Drake artifacts
     are not overwritten. A city still on the Drake assumption at that deadline uses its frozen
     artifacts as its production-conductor models (no duplicate refit). The refit tooling is built
     and tested either way, and the ABLATION refits under the bracketing set always run.
     `ml_wind_corrected` is reused without a refit.
  4. Before the FRESH read, two analyses are run with criteria pre-registered in v4 and reported:
     - an ABLATION conductor-invariance re-score (fit on train, score on validation, under
       bracketing conductor configs);
     - per-city TEST-split scoring.
  5. At or after 2026-11-01T00:00Z the v4 read 1 runs once. If it names no winner, the
     pre-registered conditional re-test (read 2) runs once at or after 2026-11-08T00:00Z under the
     same rules, grading all rows including read 1's (D-08). A recorded owner decision names:
     - which shadow model moves forward, if any;
     - the interim G6 forecast method (OD-3 revisited: naive, or `ml` with B2 fixed).

     After that decision, B1, B2, B4 and B5 are closed, the Phase 3 validation is re-run on the same
     non-FRESH window, and a new go/no-go is signed. A GO lifts the provisional label on stored rows.
**Plans**: 19 plans

Plans:
*Waiting on owner gates:* while the v4 signature (07-02) is pending, 07-01, 07-03, 07-04, 07-08 and
07-19 run (none depends on 07-02). At the Power Systems gate (07-11 Task 2), 07-11's ABLATION/TEST run
and veto record are already done; only the read-1 dry-run rehearsal remains, since 07-12 waits for its
instant and 07-14 waits for 07-12.

**Wave 1**
- [ ] 07-01-PLAN.md — Tracer: COND-02 golden of the frozen shadow path captured from the untouched d71c501 tree; per-city production conductor table, `production_city_point` resolver and rating identity (COND-01, COND-02)
- [ ] 07-02-PLAN.md — Draft confirmation protocol v4 in plain English with a machine-checked registry; owner signs (blocking-human); record the amendment in both STATE files (SEL-01)

**Wave 2** *(07-03, 07-04 after 07-01; 07-05, 07-06 after the v4 signature)*
- [ ] 07-03-PLAN.md — Conductor refit tooling (new hashed location, verify-before-load, headline loader) and the ABLATION conductor-invariance driver (SEL-02, SEL-03)
- [ ] 07-04-PLAN.md — Production callers on the per-city resolver, caller-split guard, production expectations in tests (COND-02, COND-01)
- [ ] 07-05-PLAN.md — v4 ship rule (relative 2% bar, 3-of-4 cities, vetoes, no pick) in a new decision module (SEL-01, SEL-04)
- [ ] 07-06-PLAN.md — Signed round registry (v4-read1, v4-read2, v4-late-descriptive) and an armed guard with no override in the evaluation core; `--round` for the live-system check (SEL-01, SEL-04)

**Wave 3** *(07-07 after 07-05 and 07-06; 07-08, 07-19 after 07-04)*
- [ ] 07-07-PLAN.md — Headline port on signed rounds with a required, hash-checked veto record; v4 rule in both evaluators (SEL-04, SEL-03)
- [ ] 07-08-PLAN.md — B5: naive band for G6 when the ml lookback withholds the forecast; `g6_forecast_method` in trace and the band-engagement table (REVAL-01)
- [ ] 07-19-PLAN.md — B2 projected-wind training feature; v2 rating config label and schema-doc conductor-basis paragraph (split from 07-04) (REVAL-01, COND-01)

**Wave 4**
- [ ] 07-09-PLAN.md — Production-conductor geometry seam, frozen-Drake secondary, scored-artifact provenance, D-03 descriptive gate (SEL-04, SEL-02, COND-02)

**Wave 5**
- [ ] 07-10-PLAN.md — TEST-split scorer and the signed TEST veto; registry parity test pinning every signed value (SEL-03, SEL-01)

**Wave 6**
- [ ] 07-11-PLAN.md — Run ABLATION and TEST, write the veto record; owner's Power Systems gate at 2026-10-31T00:00Z with conditional config bump, refit and TEST re-score (SEL-03, SEL-02, COND-01)

**Wave 7**
- [ ] 07-12-PLAN.md — Owner's go after an automated preflight, then v4 read 1 at or after 2026-11-01T00:00Z, once (SEL-04)

**Wave 8** *(07-14 after 07-12, so nothing rewrites tracked files during the read-1 preflight)*
- [ ] 07-13-PLAN.md — Read-1 results in plain English and the owner's recorded SEL-04 decision (SEL-04)
- [ ] 07-14-PLAN.md — REVAL re-run: B2 retrain with a new live manifest (not pushed), ml and naive replays with zero fidelity mismatches, report tables (REVAL-01)

**Wave 9**
- [ ] 07-15-PLAN.md — Conditional read 2 at or after 2026-11-08T00:00Z, only if read 1 named no winner (SEL-04)
- [ ] 07-17-PLAN.md — Re-validation report, B1/B2/B4/B5 closures, owner-signed go/no-go and label text (REVAL-01)

**Wave 10**
- [ ] 07-16-PLAN.md — Read-2 results (or not-run note) and the owner's final SEL-04 decision (SEL-04)
- [ ] 07-18-PLAN.md — Owner-approved promotion push, first live run verified, optional owner-run relabel of stored rows (REVAL-01)

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Land PR #7 | 5/5 | Complete    | 2026-10-19 |
| 2. Data Cleaning | 4/4 | Complete    | 2026-10-20 |
| 3. Real-Data Validation | 5/5 | Complete    | 2026-10-21 |
| 4. Supabase Store & Writer | 12/12 | Complete    | 2026-10-24 |
| 5. Scheduled Live Runs | 8/8 | In Progress | - |
| 6. Exposure & E2E Verification | 0/13 | Planned | - |
| 7. Per-City Conductors, Shadow Refit and Early Model Selection | 0/19 | Planned | - |
