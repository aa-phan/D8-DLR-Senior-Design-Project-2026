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
- [ ] **Phase 4: Supabase Store & Writer** — schema migration, Postgres read/write, backfill load, secrets
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
**Plans**: 9/12 plans executed (04-07..04-12: gap closure G-04-2, all 12 code review findings)

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
- [ ] 04-10-PLAN.md — IN-01 1000-character run errors and count-preserving key redaction; IN-04 loader on the store's public helpers (gap wave 2)

**Gap Wave 3** *(blocked on 04-10)*
- [ ] 04-11-PLAN.md — WR-04 computed-first backfill de-duplication; WR-05 fingerprint child decoupled via `rating_identity.py` (gap wave 3)

**Gap Wave 4** *(blocked on all gap plans)*
- [ ] 04-12-PLAN.md — Owner: [BLOCKING] schema push of the new migration, local smoke, push and Actions smoke; executor records evidence and the 12/12 ledger (gap wave 4)

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
**Plans:** 8 plans

Plans:
- [ ] 05-01-PLAN.md — Live runner (one orchestrator child per city, timeouts, exit policy, fault drill) and dispatch-only `dlr_live.yml` (tracer)
- [ ] 05-02-PLAN.md — Forecast status/error and anomaly-model presence in run output, NSRDB skip for the current year, prints to logging, `.env` for script runs
- [ ] 05-03-PLAN.md — Runner records every run and failed city in Phase 4's `pipeline_run` (OD-9)
- [ ] 05-04-PLAN.md — Commit the eight live models via `.gitignore` carve-out (OD-10, main checkout) and run a SHA-256 pre-flight before rating
- [ ] 05-05-PLAN.md — Runbook (cron-job.org, token scope, pause, cadence, minutes budget) and the 24 h window check
- [ ] 05-06-PLAN.md — Owner: secrets and billing figures, go-live decision and push, first verified dispatch
- [ ] 05-07-PLAN.md — Owner: cron-job.org hourly job; one-city fault drill in production
- [ ] 05-08-PLAN.md — 24 h window evidence, measured Actions minutes, owner sign-off

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

**Plans**: 7 plans

Plans:
- [ ] 06-01-PLAN.md — `latest_rating` invoker view, SELECT-only anon grants, `assert_fresh` RPC, proven on a local Postgres; stdlib REST read check (tracer)
- [ ] 06-02-PLAN.md — Anon write-rejection check with unchanged-snapshot proof; owner applies the migration live and runs read/hidden/write checks
- [ ] 06-03-PLAN.md — REST interface contract (`docs/integration/rest-api.md`), curl / supabase-js / stdlib examples, pointers from the consumer docs
- [ ] 06-04-PLAN.md — `ops.freshness_log` soak migration, owner pg_cron scripts, soak export and report with exact ages and causes
- [ ] 06-05-PLAN.md — E2E trace (cron-job.org execution → run → rows → REST); supabase-js legitimacy check; owner runs examples and trace live; PSS/E question
- [ ] 06-06-PLAN.md — Owner: soak migration, pg_cron, freshness alarm; 12-24 h dry soak report; go/no-go for the 72 h clock
- [ ] 06-07-PLAN.md — 72 h soak report, end-of-soak privilege and write re-check, owner sign-off, soak job removal

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
     - fixes one early evaluation instant (about 2026-11-01) and its valid-time cutoff;
     - names the evidence bases (ABLATION re-score, per-city TEST-split scoring, one early FRESH
       read) and what each may support;
     - states the selection rule with a conductor-independent (relative) threshold;
     - states the outcome if no candidate qualifies.
  2. Per-city conductor configurations (conductor type, diameter, AC resistance, maximum operating
     temperature, elevation, azimuth) are in config with a recorded source per value. The production
     rating, training and validation paths use them. The shadow collector and the frozen
     evaluation keep the Drake configuration they were frozen with, proven by a byte-identical
     golden test. Power Systems' values replace provisional ones with a config-version bump and no
     code change.
  3. `ml_cooling_corrected` and `reference_ml_refit_24h` are refit per city under the production
     conductor configs. Only rows before 2026-03-17 are used (asserted). The refits are saved as new,
     hashed artifacts; the 12 frozen Drake artifacts are not overwritten. `ml_wind_corrected` is
     reused without a refit.
  4. Before the FRESH read, two analyses are run with criteria pre-registered in v4 and reported:
     - an ABLATION conductor-invariance re-score (fit on train, score on validation, under
       bracketing conductor configs);
     - per-city TEST-split scoring.
  5. By 2026-11-01, the single FRESH read runs once under v4, and a recorded owner decision names:
     - which shadow model moves forward, if any;
     - the interim G6 forecast method (OD-3 revisited: naive, or `ml` with B2 fixed).

     After that decision, B1, B2, B4 and B5 are closed, the Phase 3 validation is re-run on the same
     non-FRESH window, and a new go/no-go is signed. A GO lifts the provisional label on stored rows.
**Plans**: 0 plans (run `/gsd-discuss-phase 7` or `/gsd-plan-phase 7`)

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Land PR #7 | 5/5 | Complete    | 2026-10-19 |
| 2. Data Cleaning | 4/4 | Complete    | 2026-10-20 |
| 3. Real-Data Validation | 5/5 | Complete    | 2026-10-21 |
| 4. Supabase Store & Writer | 9/12 | In Progress | - |
| 5. Scheduled Live Runs | 0/8 | Planned | - |
| 6. Exposure & E2E Verification | 0/7 | Planned | - |
| 7. Per-City Conductors, Shadow Refit and Early Model Selection | 0/0 | Not planned | - |
