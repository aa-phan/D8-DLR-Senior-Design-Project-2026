# Requirements: DLR System — Production Pipeline Track

**Defined:** 2026-10-18
**Core Value:** Every city's dynamic rating is computed on a schedule, stored in one shared database,
and readable by the Power Systems and Software teams at any time, without anyone running a command
and without an unreliable input silently overstating what a line can carry.

**Launch condition:** this workstream starts when PR #7 ("Track 1 updates", branch
`track-1-updates`) has been updated by its author. Phase 1 is the review-and-merge of that PR.

**Supersedes:** the `pipeline-integration` workstream (v1.2, written for the retired corridor scope,
0% complete). Its requirements PIPE-01/02, CLEAN-01/02/03 and VAL-01/02 are carried over here with
the same IDs, restated for the per-city scope (`docs/data-science/decisions/point_scope.md`).

**Decision authority:** the DS team decides the integration architecture; the Power Systems and
Software teams consume it (owner decision, 2026-10-18). Contracts written here are decided, not
proposals.

## Decided architecture

- **Store:** hosted Postgres on Supabase. It replaces the CSV historical archive as the system of
  record for live ratings, because GitHub Actions runners are ephemeral and cannot keep a CSV
  between runs.
- **Read interface:** Supabase's built-in REST API (PostgREST), read-only for consumers via Row Level
  Security. No custom API server in this workstream (a FastAPI layer is out of scope; see below).
- **Writer:** the integrated per-city pipeline from PR #7 (`dlr_orchestrator.run_dlr_pipeline`),
  run in a GitHub Actions workflow.
- **Trigger:** cron-job.org calling GitHub's `workflow_dispatch`, the same pattern as
  `.github/workflows/shadow_collect.yml` since commit 2ec2bfd. No GitHub `schedule:` trigger.

## Requirements

### Merge PR #7 (Phase 1)

- [x] **LAND-01**: PR #7's modules live at their real paths (`backend/city_pipeline.py`,
  `backend/dlr_orchestrator.py`, `backend/observation_composer.py`, `backend/backfill_archive.py`,
  changes to `backend/city_rating.py`) on a branch based on current `main`, with LF line endings. No
  root-level duplicates of backend modules or docs are added, and the unchanged `dlr_pipeline.py`
  is dropped from the diff.
- [x] **LAND-02**: The full test suite passes on the merged result. This includes updating the 19
  `backend/tests/city_rating_test.py` fixtures that lack `wind_direction`, collecting the
  wind-projection test as `backend/tests/city_rating_wind_projection_test.py`, and fixing the cron
  test that already fails on `main`
  (`forecast_shadow_collect_test.py::test_workflow_cron_is_four_cycles_a_day_and_documents_the_revert`,
  broken by 2ec2bfd).
- [x] **LAND-03**: The PR's new modules have tests: the composer's provider priority and same-hour
  alignment, the city pipeline's fallback-row exclusion and degenerate-band handling, the
  orchestrator's per-city error isolation, and backfill's resume/skip behavior. All run offline
  with stub fetchers.
- [x] **LAND-04**: The PR's doc amendments land in the right files: the composition amendment in
  `docs/data-science/decisions/data_provider.md`, and the wind-projection amendment in
  `docs/data-science/PRD.md`, not the frontend PRD.
- [x] **PIPE-01** (carried over): one entry point runs history → forecast → anomaly detector →
  `rate_city` → archive for every city in `config.LOCATIONS`. Delivered in code by PR #7; this
  phase verifies it after LAND-01..04.

### Production gaps (Phases 2-3)

- [x] **CLEAN-01**: Across a city's history (not one row at a time), physically implausible values
  are flagged under a written policy (flag, exclude or impute): stuck-sensor runs, and spikes that
  are inconsistent with neighboring readings.
- [x] **CLEAN-02**: A documented gap-handling strategy covers missing hourly slots in a city's
  history before the forecast and anomaly detector consume it.
- [x] **CLEAN-03**: At most one row exists per (`city`, `datetime_utc`) slot. Re-running a window
  never appends a duplicate or conflicting row. Exception (owner, 2026-10-20, review WR-01): in the
  CSV a computed row may follow a fallback row for its instant so a rerun repairs a fallback cycle;
  cleaning keeps only the computed row.
- [x] **CLEAN-04**: Rows touched by cleaning stay distinguishable from rows as written, so
  validation can tell raw readings from cleaned ones.
- [x] **VAL-01**: Over a backfilled real-data window for all four cities, the pipeline's ratings
  are compared against each city's static rating (`config.STATIC_RATINGS`, provisional) and
  `RATING_BOUNDS_BY_LOCATION`. Fallback rate per gate and per city is reported, and implausible
  ratings are explained or fixed.
- [x] **VAL-02**: The naive/EWM forecast band's empirical coverage and the anomaly detector's flag
  rate are measured on that window and documented. This covers the current `city_pipeline` path
  only; it does not re-evaluate the ML shadow candidates.
- [x] **VAL-03**: A written go/no-go for production that cites VAL-01/02's results. Phase 4 does not
  start on a no-go. *(Amended 2026-10-21 by the owner: the NO-GO no longer blocks Phases 4-6; it gates
  lifting the provisional label, decided under REVAL-01.)*

### Supabase store and writer (Phase 4)

- [ ] **DB-01**: A versioned SQL migration in the repo creates the schema. At minimum it has a
  per-city rating table keyed uniquely on (`city`, `valid_time`) with: rating (A), rating (MW, via
  `ercot_dlr_merger.amps_to_mw`), static rating, status/fallback, fallback gates, alerts,
  exhausted, resolved station, forecast amps with CI bounds and horizon, detector signal, per-field
  provider sources, run id and pipeline version, and `computed_at`. Every value carries its unit in
  its column name or in the schema doc.
- [x] **DB-02**: The pipeline reads its forecast/detector history from Postgres and writes its
  result to Postgres, replacing the CSV archive on the production path. The CSV path stays usable
  offline for tests and backfill. Writes are idempotent upserts on the unique key, which also
  satisfies CLEAN-03 at the database level.
- [x] **DB-03**: The validated backfill window from Phase 3 is loaded into Postgres, so the
  forecast and detector do not cold-start in production.
- [x] **DB-04**: Secrets: the writer uses a service-role key or a pooler connection string stored
  only as GitHub Actions secrets. Nothing secret is committed or reaches a consumer. The connection
  works from GitHub-hosted runners (the pooler endpoint, because runners lack IPv6).
- [x] **DB-05**: A schema contract doc for consumers (tables, columns, units, the meaning of
  fallback, freshness expectations), replacing the corresponding open items in
  `docs/frontend/specs/api-contract.md` and `docs/data-science/decisions/pss_e_handoff.md`.
- [x] **DB-06**: Every rating row records what produced it: a rating config version that changes with
  any per-city conductor parameter, static rating, bound or bearing, and the identity (hash) of the
  forecast method/model and the anomaly model used. Conductor, model or forecast-method changes
  alter only the values pushed, never the schema; consumers see the change through these columns.

### Scheduled live runs (Phase 5)

- [ ] **PIPE-02** (carried over): a new workflow (`.github/workflows/dlr_live.yml` or similar) runs
  the integrated pipeline for all four cities on `workflow_dispatch`, triggered by cron-job.org at
  the decided cadence, and upserts into Supabase.
- [ ] **SCHED-01**: A failed city or provider in one run is recorded (row status or a run-log
  table) and does not stop the other cities or the next run. A failed run is visible in the
  Actions history.
- [ ] **SCHED-02**: The operating runbook documents the cron-job.org job (URL, token scope, how to
  pause it, how to change cadence) and estimates GitHub Actions minutes for the chosen cadence
  alongside the existing shadow-collection usage.

### Exposure and end-to-end verification (Phase 6)

- [ ] **API-01**: The consumer tables or views are exposed through Supabase's REST API, read-only
  for the anon role under RLS. A `latest_rating` view returns one current row per city.
- [ ] **API-02**: Documented example requests that work as written: `curl` for any consumer,
  `supabase-js` for the frontend, and Python stdlib `urllib` for the PSS/E environment (no
  third-party packages).
- [ ] **E2E-01**: End to end, a cron-job.org trigger produces a workflow run, which produces new
  rows, which are visible through the REST API with matching values, for all four cities.
- [ ] **E2E-02**: Live at any time: over a soak window of at least 72 h, querying `latest_rating`
  at any moment returns, for every city, a row whose `valid_time` is no older than one cadence
  interval plus a stated grace period. Every breach is explained.
- [ ] **E2E-03**: Write protection: an anon-key request that tries to insert, update or delete is
  rejected.

### Per-city conductors, shadow refit and early model selection (Phase 7)

- [ ] **COND-01**: Each city has its own conductor configuration (conductor type, diameter, AC
  resistance, maximum operating temperature, elevation, azimuth) in config, with a recorded source
  for every value. Values are provisional until Power Systems confirms them; replacing them is a
  config change with a version bump, not a code change.
- [ ] **COND-02**: The production rating, training and validation paths use the per-city
  configurations. The shadow collector, the 12 frozen shadow artifacts and the frozen evaluation
  modules keep the Drake configuration they were frozen with. A golden test proves their outputs
  are byte-identical before and after the change.
- [ ] **SEL-01**: Confirmation protocol v4, amending signed v3, is drafted for the owner and signed
  before any FRESH-basis outcome is computed or read. It contains:
  - the retirement of the 2026-11-24 run;
  - one early evaluation instant (about 2026-11-01) and its cutoff;
  - the evidence bases and what each may support;
  - a conductor-independent (relative) selection threshold;
  - the action if no candidate qualifies.
- [ ] **SEL-02**: `ml_cooling_corrected` and `reference_ml_refit_24h` are refit per city under the
  production conductor configs, on rows before 2026-03-17 only (asserted). They are saved as new,
  hashed artifacts without overwriting the frozen Drake artifacts. `ml_wind_corrected` is reused
  without a refit.
- [ ] **SEL-03**: Before the FRESH read, two analyses are run and reported against criteria
  pre-registered in v4:
  - an ABLATION conductor-invariance re-score (fit on train, score on validation, under
    bracketing conductor configs);
  - per-city TEST-split scoring.
- [ ] **SEL-04**: By 2026-11-01 the single v4 FRESH read runs once. A recorded owner decision names
  which shadow model, if any, replaces `ml`, and the interim G6 forecast method (OD-3 revisited).
- [ ] **REVAL-01**: After SEL-04, B1, B2, B4 and B5 are closed, the Phase 3 validation is re-run on the
  same non-FRESH window with the new configs and models, and a new go/no-go is signed. A GO lifts
  the provisional label on stored rows.

## Owner decisions (fixed 2026-10-19)

| # | Decision | Needed by | Decided |
|---|----------|-----------|---------|
| OD-1 | Live cadence | Phase 5 | **Hourly.** Actions minutes must be checked against the plan's quota alongside the 4/day shadow runs (SCHED-02) |
| OD-2 | Production weather provider mode | Phase 5 | **`composed`.** The workflow needs `SYNOPTIC_TOKEN`, `NREL_API_KEY`, `NREL_API_EMAIL` as secrets |
| OD-3 | Forecast method on the live path | Phase 3 | **`ml`.** Consequence: the per-city forecast models (`data/models/forecast_{CITY}.joblib`, git-ignored) must be available to the live runner alongside the anomaly models (`data/models/anomaly_{CITY}.joblib`). Provisioning them is in scope for Phases 4-5. `city_pipeline` catches a forecast failure and continues without a forecast, so a missing model degrades silently. The live run must detect that case and record it |
| OD-4 | Freshness grace period for E2E-02 | Phase 6 | **30 min** past one cadence interval (a city's latest `valid_time` no older than 90 min at hourly cadence) |
| OD-5 | Labelling of values based on provisional static ratings / assumed bearings | Phase 4 | **Labelled provisional** in the schema doc and per row (e.g. a `rating_basis` / `config_version` column) |
| OD-6 | What the anon (publishable) key may read | Phase 4/6 | **Full history is public.** Anon gets SELECT on both the `latest_rating` view and the full per-city rating table. It gets no write privileges at all: writes are revoked explicitly, not only blocked by RLS (06-RESEARCH: with grants left in place, PATCH/DELETE return 200 `[]`) |
| OD-7 | Meaning of a rating row's `valid_time` key | Phase 4 | **Run slot, hour-truncated UTC** of the run window end (a 14:07 run and a 14:12 retry share the 14:00 key, and the retry overwrites). The aligned weather hour is stored separately as `observation_time` |
| OD-8 | History read window for forecast/detector on the live path | Phase 4 | **Last 30 days** per city |
| OD-9 | How a city that fails outright (exception, not a safety fallback) appears | Phase 4/5 | **Run log only.** No rating row is written; the failure is recorded in the `pipeline_run` log. `latest_rating` keeps the last good row, and the freshness check (E2E-02) flags persistent failures |
| OD-10 | How the runner gets the per-city forecast/anomaly models (8 `.joblib` files, <1 MB) | Phase 5 | **Commit them to git** through a `.gitignore` carve-out, following the `data/shadow/models` precedent. Supabase Storage is not used |

## Out of Scope

| Item | Reason |
|------|--------|
| Custom FastAPI/Flask server | Supabase REST covers read access. Add one later only if consumers need shaped endpoints |
| `frontend/` dashboard build | Software team, who consume this workstream's contract |
| PSS/E-side ingestion and N-1 analysis | Power Systems team, who consume this workstream's contract |
| PSS/E results back into the database (F7) | A follow-on table once Power Systems produce output |
| Changes to `shadow_collect.yml`, the shadow logs, or the frozen evaluation modules | Frozen except as signed protocol v4 (SEL-01) explicitly allows; v3 governs until then |
| Wiring a selected shadow model into the live path (runtime forecast fetch, hourly series, band for G6) | A follow-on phase, added once SEL-04 names a model |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| LAND-01 | Phase 1 | Complete |
| LAND-02 | Phase 1 | Complete |
| LAND-03 | Phase 1 | Complete |
| LAND-04 | Phase 1 | Complete |
| PIPE-01 | Phase 1 | Complete |
| CLEAN-01 | Phase 2 | Complete |
| CLEAN-02 | Phase 2 | Complete |
| CLEAN-03 | Phase 2 | Complete |
| CLEAN-04 | Phase 2 | Complete |
| VAL-01 | Phase 3 | Complete |
| VAL-02 | Phase 3 | Complete |
| VAL-03 | Phase 3 | Complete |
| DB-01 | Phase 4 | Pending |
| DB-02 | Phase 4 | Complete |
| DB-03 | Phase 4 | Complete |
| DB-04 | Phase 4 | Complete |
| DB-05 | Phase 4 | Complete |
| DB-06 | Phase 4 | Complete |
| PIPE-02 | Phase 5 | Pending |
| SCHED-01 | Phase 5 | Pending |
| SCHED-02 | Phase 5 | Pending |
| API-01 | Phase 6 | Pending |
| API-02 | Phase 6 | Pending |
| E2E-01 | Phase 6 | Pending |
| E2E-02 | Phase 6 | Pending |
| E2E-03 | Phase 6 | Pending |
| COND-01 | Phase 7 | Pending |
| COND-02 | Phase 7 | Pending |
| SEL-01 | Phase 7 | Pending |
| SEL-02 | Phase 7 | Pending |
| SEL-03 | Phase 7 | Pending |
| SEL-04 | Phase 7 | Pending |
| REVAL-01 | Phase 7 | Pending |
