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
5. exposes the data through Supabase REST and proves end-to-end, always-fresh results (Phase 6).

Phase numbering starts at 1 and is independent of other workstreams. It supersedes
`pipeline-integration` (see REQUIREMENTS.md).

**Why cleaning and validation come before Supabase:** `backfill_archive.py` (in PR #7) produces a
multi-day, multi-city archive without any scheduler, so the defects cleaning targets and the data
validation needs both exist before production storage does. Validating first means Phase 4 loads
history that has already been checked, and the go/no-go (VAL-03) is made before any shared
infrastructure is created.

**Constraints that hold across every phase:**
- Do not modify `shadow_collect.yml`, the shadow logs, or the frozen evaluation modules before the
  2026-11-24 confirmation run. The live workflow is a separate file.
- Anti-peeking: nothing in this workstream may score shadow predictions against truth.
- Commit with explicit paths; ask before pushing anything that changes live CI.

## Phases

- [ ] **Phase 1: Land PR #7** — relocate, fix tests, add tests, merge
- [ ] **Phase 2: Data Cleaning** — cross-row outlier, gap and duplicate handling on city history
- [ ] **Phase 3: Real-Data Validation** — ratings and calibration on backfilled data; production go/no-go
- [ ] **Phase 4: Supabase Store & Writer** — schema migration, Postgres read/write, backfill load, secrets
- [ ] **Phase 5: Scheduled Live Runs** — new workflow, cron-job.org trigger, failure isolation, runbook
- [ ] **Phase 6: Exposure & E2E Verification** — REST via RLS, `latest_rating` view, soak test

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
**Plans**: 5 plans

Plans:
- [ ] 01-01-PLAN.md — Tracer: offline backfill -> orchestrator -> city pipeline -> composer run, plus backfill resume/log/interrupt tests (wave 1)
- [ ] 01-02-PLAN.md — observation_composer tests: priority, same-hour alignment, fallback pass, wind pairing, circuit breaker, provenance (wave 2)
- [ ] 01-03-PLAN.md — city_pipeline tests: fallback-row exclusion, forecast failure, degenerate band, pipeline key (wave 2)
- [ ] 01-04-PLAN.md — dlr_orchestrator tests: per-city error isolation, validation, composed wiring, summarize, main exit code (wave 2)
- [ ] 01-05-PLAN.md — Read-only evidence for LAND-01/02/04 and PIPE-01, plus the full suite with the new tests (wave 3)

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
     `append_observation` and the orchestrator path (not only backfill).
  4. Cleaned rows carry a marker (column or flag) that tells them apart from raw rows.
**Plans**: 4 plans

Plans:
- [ ] 02-01-PLAN.md — Tracer: data_cleaning.clean_history wired into city_pipeline (timestamp, duplicate, fallback rules; clean_flags/clean_excluded markers), one archive row per (city, instant) on append, orchestrator rerun test (wave 1)
- [ ] 02-02-PLAN.md — Archive tests for the one-row-per-slot guard (spellings, other cities, corridor-era files, unreadable files) and stable read order (wave 2)
- [ ] 02-03-PLAN.md — Hourly-slot, gap, stuck-run and spike rules, gap_slots marker, and the written policy docs/data-science/decisions/data_cleaning.md (wave 2)
- [ ] 02-04-PLAN.md — Forecast gap guard for G6 (stale history, ml lookback), skipped-cycle tests end to end, phase gate (wave 3)

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
**Plans**: 5 plans

Plans:
- [ ] 03-01-PLAN.md — Wave 1: backfill validation trace (`--trace-path`) and offline analysis CLI (completeness, manifest, VAL-01 report); phase tracer
- [ ] 03-02-PLAN.md — Wave 2: preflight, owner runs the 2026-09-08..09-28 backfill (ml, composed), completeness + manifest committed (checkpoint)
- [ ] 03-03-PLAN.md — Wave 2: VAL-02 band coverage and detector trip tables; offline naive replay with fidelity check
- [ ] 03-04-PLAN.md — Wave 3: run replay + report on the hashed archive, commit tables, write the validation doc with go/no-go options
- [ ] 03-05-PLAN.md — Wave 4: owner's go/no-go (blocking-human decision) recorded verbatim in the doc and STATE.md

### Phase 4: Supabase Store & Writer
**Goal**: Postgres on Supabase is the production system of record for per-city ratings.
**Depends on**: Phase 3 (go)
**Requirements**: DB-01, DB-02, DB-03, DB-04, DB-05
**Success Criteria**:
  1. Applying the committed migration to an empty Supabase project creates the schema. Re-applying
     it is a no-op or fails safely.
  2. A pipeline run pointed at Supabase reads history from Postgres and upserts one row per city.
     Re-running the same window changes no row count.
  3. The validated backfill is loaded, and per-city row counts match the Phase 3 archive.
  4. A GitHub-hosted runner can connect using only repository secrets. A secret scan of the repo
     finds no keys.
  5. The consumer schema doc is published under `docs/`, and `api-contract.md` /
     `pss_e_handoff.md` point to it.
**Plans**: 6 plans

Plans:
- [ ] 04-01-PLAN.md — psycopg legitimacy gate; tracer: migration, writer and history read for one city-hour on a throwaway Postgres; schema, privilege and secret-hygiene contract tests (wave 1)
- [ ] 04-02-PLAN.md — Pipeline seam: history reader and forecast_status in city_pipeline, `--store postgres` / `--no-run-row`, one pipeline_run row per run (OD-9), validated 30-day history (wave 2)
- [ ] 04-03-PLAN.md — Manifest-checked backfill loader (DO NOTHING, per-city parity), smoke test, secret scan, dispatch-only Actions smoke workflow (wave 2)
- [ ] 04-04-PLAN.md — Consumer schema contract `city_rating_v1.md`; api-contract.md and pss_e_handoff.md point to it (wave 3)
- [ ] 04-05-PLAN.md — Owner: CLI legitimacy gate, schema approval, [BLOCKING] schema push, writer credential, local smoke (wave 4)
- [ ] 04-06-PLAN.md — Owner: GitHub secret, approved push, Actions smoke, backfill load; executor verifies and commits the evidence (wave 5)

### Phase 5: Scheduled Live Runs
**Goal**: Ratings accrue in Supabase on a fixed cadence with no human involved.
**Depends on**: Phase 4
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
**Depends on**: Phase 5
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

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Land PR #7 | 0/5 | Blocked on PR author | - |
| 2. Data Cleaning | 0/4 | Planned | - |
| 3. Real-Data Validation | 0/5 | Planned | - |
| 4. Supabase Store & Writer | 0/6 | Planned | - |
| 5. Scheduled Live Runs | 0/TBD | Not started | - |
| 6. Exposure & E2E Verification | 0/7 | Planned | - |
