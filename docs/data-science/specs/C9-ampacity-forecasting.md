# C9 — Ampacity Forecasting

**Phase:** 4 (Predictive) · **Effort:** L · **Status:** Not started. Referenced in `System Design Report.md` §3.1 ("thermal limit forecasting via regression or neural network models") and in the Prior Art Report (IEEE Trans. Smart Grid MILP planning work) as intended, not completed, work — no discrepancy here, unlike C8/C10.

**Responsibility:** Forecast ampacity ahead of real time (rather than only reporting the current instantaneous rating), so the UI dashboard's "trusted duration" concept (per `Project Definition.md`'s I/O spec) has a forward-looking basis instead of just an assumed static window.

## Current Implementation

None. No model code, training pipeline, or feature-engineering step exists anywhere in the repo.

## Interface & Data Contract

Not yet designed. Conceptually needs:

- **Features:** historical weather (C4) and historical computed ampacity (C5) as a time series, likely with lagged/rolling features.
- **Target:** future ampacity at a defined horizon.
- **Output:** should extend `PIPELINE_SCHEMA` (C2) with new forecast-specific columns (e.g. a forecast horizon and a confidence/uncertainty band) — added to `PIPELINE_SCHEMA` when designed, not restated elsewhere.

## Blocked by

**C4** (weather features) and **C5** (ampacity as both a feature and the training target). Also depends on **accumulated historical data volume** — per `ROADMAP.md` Finding 5, this is a lead-time problem distinct from the component dependency graph: even once C4/C5 exist, C9 can't start productively until enough historical data has accrued, which is why C4's Phase 2 spec recommends starting a background historical-data job well before Phase 4 begins.

## Blocks

Nothing else in this roadmap depends on C9.

## Parallel-safe with

C10 — both Phase 4, but distinct models (forecasting vs. anomaly detection) with no obvious shared code beyond both consuming C4/C5 outputs. Should be workable by different people simultaneously once both land in Phase 4.

## Known Issues

Not applicable — no implementation exists yet.

## Acceptance Criteria

Not yet defined at implementation-testable detail, since design hasn't started. At minimum, per the general spirit of System Design Report §3.3's known-value validation approach: forecast accuracy should be evaluated against held-out historical data with an explicit, agreed error margin, not just "looks reasonable."

## Open Questions

- Regression vs. neural network — the Prior Art Report's MILP planning citation and the System Design Report both leave this open; no strong signal in the repo either way.
- What forecast horizon matters for the dashboard's "trusted duration" feature — minutes, hours?
- Does this feed C10 (e.g. using forecast/actual divergence as an anomaly signal), or are they fully independent models?
