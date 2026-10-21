---
gsd_state_version: 1.0
milestone: v1.3
milestone_name: ML Model Development
current_phase: 05
current_phase_name: "Shadow Collector: Five-Method Side-by-Side Challenger Recording"
status: completed
stopped_at: Phase 05 complete (all 5 plans)
last_updated: "2026-10-08T00:42:13.533Z"
last_activity: 2026-10-21
last_activity_desc: "Shadow collection fix: persistence_24h cold start on every run (runner had an empty log); fixed and verified live 2026-10-21"
state_head: c6f73dd46e9aee09a146d444d43142f6bb4195fb
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 26
  completed_plans: 26
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-09-10) and this workstream's
.planning/workstreams/ml-modeling/REQUIREMENTS.md (updated 2026-09-14)

**Core value:** The end-to-end pipeline produces valid ampacity forecasts and runs without manual
intervention, while never letting an unreliable input silently overstate what a line can safely
carry.
**Current focus:** All five phases are built. The open item is the 2026-11-24 shadow evaluation
(owned by this workstream; see `docs/data-science/decisions/confirmation_protocol_v3_per_city.md`).
Phase 3 (the forecast correction experiment, promoted from backlog Phase 999.1) determined what
should replace Phase 1's "ml" forecasting method: `ml_cooling_corrected` (a 24-hour-lead
physics-plus-ML-corrected approach) beat persistence with a statistically distinguishable margin
at both corridors on the held-out test set (a corridor-era result) — see
`docs/data-science/decisions/forecast_correction_experiment.md`. The corridors were retired on
2026-10-12; the per-city retrain results are in `docs/data-science/PROJECT-STATUS.md`.

## Current Position

Phase: 05 (Shadow Collector: Five-Method Side-by-Side Challenger Recording) — COMPLETE
Plan: 5 of 5
Status: completed
Last activity: 2026-10-13 — Phase 05 complete (five-candidate shadow collection verified 11/11).
All 5 phases and 26 plans are complete; the milestone stays open pending the 2026-11-24 shadow
evaluation.

Progress: [██████████] 100%

## Performance Metrics

**Velocity:**

- Total plans completed: 26
- Average duration: N/A
- Total execution time: N/A

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 5 | - | - |
| 03 | 7 | - | - |
| 04 | 6 | - | - |
| 05 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: N/A
- Trend: N/A

**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 05 P01 | N/A | 1 tasks | 1 files |
| Phase 05 P03 | 20min | 2 tasks | 2 files |
| Phase 05 P04 | ~45 min | 3 tasks | 8 files |

## Accumulated Context

### Decisions

- Phase order was originally chosen as Forecasting Model -> Anomaly Detection Model, but with no hard
  dependency between them: the two models are independent components with no shared code path
  other than both being consumed by `DLRSafetyMonitor` — see ROADMAP.md Overview for full
  rationale. Phase 2 may be executed before or in parallel with Phase 1.
- FCST-01/FCST-02 combined into one phase, and ANOM-01/ANOM-02 combined into a second, rather
  than a design-then-validate split across all four requirements — each model's build and its
  real-data validation share the same setup (the same training/validation series), so splitting
  them would duplicate that assembly work across two phases.
- "Real historical data" for both phases' validation is defined as historical weather
  (Open-Meteo Archive API backfill, already shipped in the multi-provider-weather workstream)
  run through the existing IEEE 738 thermal model (plus real ERCOT historical load for ANOM-02),
  not the live `historical_archive.py` CSV — that CSV is empty today because Track 1 (Pipeline
  Integration) hasn't executed yet, and this workstream should not block on Track 1's live
  accrual timeline to get real data.
- Full decision log lives in .planning/PROJECT.md Key Decisions table (shared across workstreams).
- [Phase 05]: Approved as written - nested per-candidate JSONL schema (schema_version 2) with
  six-field legacy mirror for ml_wind_corrected, and no-migration strategy for already-committed
  flat-shape rows on shadow-collection-data (05-01).
- [Phase 05]: collect_once wired to run_once_all_methods for every corridor (05-03); real two-corridor live cycle exits 0 in ~32s, well under the 15-minute workflow budget
- [Phase 05]: reference_ml_refit_24h's real artifact fit via fit_fitted_arms's exact arm-5 recipe on the pinned train-plus-validation window (18834 rows/corridor); real live truth-proxy predict path replaces 05-02's honest unavailable stub

### Pending Todos

None yet.

### Roadmap Evolution

- Phase 5 added (2026-10-07): Shadow Collector: Five-Method Side-by-Side Challenger Recording —
  extend the existing shadow prototype (Phase 4's `forecast_shadow_pipeline.py`) to record
  `ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`, `raw_forecast`, and
  `persistence_24h` side by side per cycle, keeping `ml_wind_corrected` as the provisional
  production default. No candidate is established as an overall winner by this phase — purely a
  data-collection expansion feeding the existing Nov 24 evaluation protocol. Production
  (`dlr_pipeline.py`) is unchanged.

### Blockers/Concerns

- **Resolved:** the new ML dependency was added in Phase 1 (`scikit-learn==1.9.1` is pinned in
  `requirements.txt`, with its legitimacy audit recorded there).
- The live `historical_archive.py` archive (`config.HISTORICAL_ARCHIVE_PATH`) was empty when this
  workstream was scoped because Track 1 had not executed; Track 1 (`pipeline-integration`) is
  still not started. The phases assembled their own real-data training/validation series from
  Open-Meteo backfill (+ ERCOT historical load for Phase 2) — see ROADMAP.md Overview.
- Phase 4 planning (2026-09-30): the automated `check.decision-coverage-plan` gate returned
  `passed: false, reason: could-not-parse` against `04-CONTEXT.md` — its `- **D-NN:**` bullet
  parser doesn't match this CONTEXT.md's `### D-01:`-heading decision format (5 sections, `uncovered`
  list came back empty, not a real gap list). Proceeded anyway: the independently-spawned
  `gsd-plan-checker` verification pass read the actual PLAN.md files and CONTEXT.md directly and
  confirmed exhaustive coverage of D-01 through D-05 across the 6 plans (see
  `04-01-PLAN.md`..`04-06-PLAN.md`). Override recorded per plan-phase workflow §13a.

## Deferred Items

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-21 (complete). Fixed the shadow collector running against an empty log on the runner, which
made persistence_24h a cold start (`unavailable`) in every v3 row. shadow_collect.yml now clones
shadow-collection-data before collecting and symlinks data/shadow/predictions into it; the push replays
only this run's rows if rejected; the health check uses --max-age-minutes 60. The data branch README
reconstructs past persistence_24h values (28-29 per city, matching Persistence24hShadowMethod exactly);
the JSONL logs are unchanged and no reconstructed rows were written to them (owner decision). Commit
762a0cd; verified by run 39666133426 (data commit 208ee80). The first live persistence match is expected
on the next scheduled run (prior row valid 2026-10-22T00Z). The live-log check has no persistence rows
before 2026-10-21.
Stopped at: Phase 05 complete (all 5 plans); awaiting the 2026-11-24 shadow evaluation
Resume file: None

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 261013-149 | Retrain per-city ml forecast and anomaly models after the corridor-to-city rescope | 2026-10-13 | 85ec2b7 | [261013-149-retrain-per-city-ml-forecast-and-anomaly](./quick/261013-149-retrain-per-city-ml-forecast-and-anomaly/) |
| 261013-285 | Per-city shadow-log scorer and per-city confirmation port (live-log scorer, stats + 9-test Holm family, ship rule, frozen-harness port, frozen-data validation) | 2026-10-13 | 6869095 | [261013-285-plan-the-per-city-shadow-log-scorer](./quick/261013-285-plan-the-per-city-shadow-log-scorer/) |
