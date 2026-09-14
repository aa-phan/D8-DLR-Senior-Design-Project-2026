# Roadmap: Pipeline Integration & Real-Data Verification (v1.2)

## Overview

This workstream (Track 1 of `docs/data-science/DEVELOPMENT-TRACKS.md`) takes three already-built,
already-tested, but never-connected code paths — `corridor_discretization.rate_corridor`,
`anomaly_detector.AnomalyDetector`, and `ampacity_forecast.forecast_ampacity` — and wires them into
one real pipeline cycle that runs against accumulating real history, runs on its own on a schedule,
and gets checked against real ERCOT data instead of synthetic fixtures. The journey is: connect the
three modules into one sequence (Phase 1), make that sequence run unattended on a recurring cadence
so real history actually accrues (Phase 2), then prove the resulting ratings and statistical methods
hold up against real data (Phase 3).

This is a fresh, independent workstream — phase numbering starts at 1 and does not continue the
`multi-provider-weather` workstream's Phase 6-10 numbering.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Pipeline Integration** - Wire `rate_corridor`, `AnomalyDetector`, and `forecast_ampacity` into one orchestrating entry point that runs against real accumulating archive history
- [ ] **Phase 2: Automated Scheduling** - Run the integrated cycle unattended on a recurring schedule so archive history and ratings accrue without manual invocation
- [ ] **Phase 3: Real-Data Validation** - Verify the integrated pipeline's rating plausibility (vs. published SLR) and forecast/anomaly calibration against real historical ERCOT data

## Phase Details

### Phase 1: Pipeline Integration
**Goal**: The DLR pipeline runs corridor discretization, anomaly detection, and ampacity
forecasting as one connected sequence against real accumulating historical data — replacing three
independently-tested code paths connected only by their own test suites.
**Depends on**: Nothing (first phase in this workstream)
**Requirements**: PIPE-01
**Success Criteria** (what must be TRUE):
  1. A single orchestrating entry point runs corridor discretization -> anomaly check -> ampacity
     forecast as one sequence for a real corridor, producing one rated result per invocation, in
     place of three separately-invoked code paths.
  2. Each invocation reads the corridor's real accumulating archive history
     (`historical_archive.read_history`) to build both the forecast (`forecast_ampacity`) and the
     anomaly detector (`AnomalyDetector.for_corridor`), so a second run's inputs reflect the first
     run's archived result rather than a reset fixture.
  3. The pipeline still resolves to a safe fallback rating — no unhandled exception — when history
     is too sparse to forecast yet (cold start) or a component raises, consistent with the existing
     G1-G6 fail-safe chain.
  4. The same entry point runs for both configured corridors (Austin<->Corpus Christi,
     Midland<->El Paso) driven by `config.CORRIDOR_ENDPOINTS`, with no corridor-specific code.
**Plans**: TBD

### Phase 2: Automated Scheduling
**Goal**: The integrated pipeline cycle from Phase 1 runs automatically on a recurring schedule, so
historical archive data and ratings accrue continuously without a human running it each time.
**Depends on**: Phase 1
**Requirements**: PIPE-02
**Success Criteria** (what must be TRUE):
  1. A scheduler (cron entry, or an in-process scheduling loop) invokes Phase 1's orchestrating
     entry point on a defined recurring interval with no human running a command per cycle.
  2. Leaving the scheduler running across multiple consecutive intervals produces multiple new rows
     in the historical archive for each corridor, each with a distinct `datetime_utc`, with no
     manual re-invocation between them.
  3. A single scheduled run that fails (e.g., a transient network/provider error) is logged and does
     not crash the scheduler process — the next scheduled cycle still fires.
  4. The scheduling mechanism, its configured interval, and how to start/stop it are documented, so
     a team member other than its author can operate it without reading source code.
**Plans**: TBD

### Phase 3: Real-Data Validation
**Goal**: The integrated, real-data pipeline's output is verified as trustworthy — both the
physical plausibility of its corridor ratings and the statistical calibration of its forecast and
anomaly-detection methods — against real historical ERCOT data, not synthetic fixtures.
**Depends on**: Phase 2
**Requirements**: VAL-01, VAL-02
**Success Criteria** (what must be TRUE):
  1. The integrated pipeline is run against real historical ERCOT weather/load data over a real
     date range for both existing corridors, producing a CSV/plot output with corridor, rating,
     forecast, and anomaly columns all populated from that one run.
  2. For each corridor, the resulting DLR ratings are compared against that corridor's published
     static line rating (`config.STATIC_RATINGS`) and documented as physically reasonable (not
     orders-of-magnitude off), per VAL-01.
  3. The forecast band (`ampacity_forecast.py`'s naive/EWM methods) produced from real data is
     checked for calibration — e.g., what fraction of real out-of-sample observations actually fall
     inside the reported confidence band — and the result is documented, per VAL-02.
  4. The anomaly-detection thresholds (`anomaly_detector.py`'s forecast-residual and
     rolling-baseline `mean ± k*std` checks) are checked against real data for plausible trip
     frequency (false-positive/false-negative behavior), and the result is documented, per VAL-02.
  5. Findings from both checks are written down in a validation document that states whether
     real-data results matched expectations or exposed problems, rather than being eyeballed once
     and discarded.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Pipeline Integration | 0/TBD | Not started | - |
| 2. Automated Scheduling | 0/TBD | Not started | - |
| 3. Real-Data Validation | 0/TBD | Not started | - |
