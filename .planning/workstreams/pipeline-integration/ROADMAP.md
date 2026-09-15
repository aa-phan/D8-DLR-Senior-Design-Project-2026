# Roadmap: Pipeline Integration & Real-Data Verification (v1.2)

## Overview

This workstream (Track 1 of `docs/data-science/DEVELOPMENT-TRACKS.md`) takes three already-built,
already-tested, but never-connected code paths — `corridor_discretization.rate_corridor`,
`anomaly_detector.AnomalyDetector`, and `ampacity_forecast.forecast_ampacity` — and wires them into
one real pipeline cycle that runs against accumulating real history, runs on its own on a schedule,
and gets checked against real ERCOT data instead of synthetic fixtures. The journey is: connect the
three modules into one sequence (Phase 1), make that sequence run unattended on a recurring cadence
so real history actually accrues (Phase 2), clean the archive of the data-quality defects that
accrual itself introduces (Phase 3), then prove the resulting ratings and statistical methods hold
up against real data (Phase 4).

This is a fresh, independent workstream — phase numbering starts at 1 and does not continue the
`multi-provider-weather` workstream's Phase 6-10 numbering.

### Why Data Cleaning (Phase 3) is sequenced before Real-Data Validation (Phase 4)

The originally-approved roadmap had "Real-Data Validation" as Phase 3, immediately after Phase 2.
Adding the Data Cleaning requirement category (CLEAN-01/02/03) forced a decision: is cleaning an
independent post-process that can be appended after validation, or a precondition validation must
be able to trust, which would require inserting it before validation and renumbering?

`historical_archive.py` settles this in favor of inserting before. `forecast_ampacity` and
`AnomalyDetector.for_corridor` (the two consumers Phase 1's own success criteria name) both read
`historical_archive.read_history`'s output directly, with nothing between them and the archive.
`read_history`'s only filtering today is `units_def.validate_pipeline_row`'s per-row unit/range
check — by construction a single-row check, it cannot see a stuck sensor repeating one value
across rows, a spike inconsistent with its neighbors, or a second row silently duplicating/
conflicting with an existing (`corridor`, `datetime_utc`) slot, because none of those are visible
from one row in isolation. Phase 4's VAL-02 charter is exactly to document the calibration quality
of those two consumers — the naive/EWM forecast band and the `mean ± k*std` anomaly baseline —
against real data. Both are silently biased by the defects CLEAN-01/02/03 target: a stuck-sensor
run flattens the rolling `std` an anomaly threshold is built from; an unfilled timestamp gap
distorts what "recent" means to `_extract_series`'s windowing; a duplicate (corridor,
datetime_utc) row double-counts one real observation in that same rolling window. Measuring
forecast/anomaly calibration against an uncleaned archive would produce a finding that has to be
re-measured once cleaning lands anyway — so Phase 3 (Data Cleaning) now precedes Phase 4
(Real-Data Validation, previously Phase 3). The original phase's goal, requirements (VAL-01,
VAL-02), and success criteria are unchanged verbatim — only its ordinal shifted, to keep this
roadmap's "phases execute in numeric order" contract true.

Phase 3 depends on Phase 2, not just Phase 1, for the same code-grounded reason: the defect
classes it targets only become real, inspectable problems once an archive has actually accrued
rows across multiple scheduled cycles — a scheduler-induced gap only exists because Phase 2's SC
#3 ("a single scheduled run that fails... does not crash the scheduler — the next scheduled cycle
still fires") tolerates a skipped cycle, and `append_observation`'s append-only write (no
`(corridor, datetime_utc)` uniqueness check) only produces a duplicate/conflicting row once more
than one cycle — potentially resolved through a different provider path — has written to the same
slot. A handful of manually-triggered Phase 1 rows have no such real gaps, repeats, or provider
disagreements to find.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Pipeline Integration** - Wire `rate_corridor`, `AnomalyDetector`, and `forecast_ampacity` into one orchestrating entry point that runs against real accumulating archive history
- [ ] **Phase 2: Automated Scheduling** - Run the integrated cycle unattended on a recurring schedule so archive history and ratings accrue without manual invocation
- [ ] **Phase 3: Data Cleaning** - Detect and handle outliers, timestamp gaps, and cross-provider duplicate/conflicting rows in the accumulating `historical_archive.py` history before it is trusted for validation
- [ ] **Phase 4: Real-Data Validation** - Verify the integrated pipeline's rating plausibility (vs. published SLR) and forecast/anomaly calibration against real historical ERCOT data

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

### Phase 3: Data Cleaning
**Goal**: The accumulating historical archive (`historical_archive.py`) is checked and cleaned of
physically-implausible outliers, unfilled timestamp gaps, and cross-provider duplicate/conflicting
rows — the three defect classes `units_def.validate_pipeline_row`'s per-row unit/range check
cannot catch, because each requires comparing a row to more than itself — before
`forecast_ampacity` and `AnomalyDetector.for_corridor` are trusted to consume that history for
validation.
**Depends on**: Phase 2 (needs a real, multi-cycle scheduled archive to clean; a handful of
manually-triggered Phase 1 rows have no real gaps, repeats, or provider disagreements to find)
**Requirements**: CLEAN-01, CLEAN-02, CLEAN-03
**Success Criteria** (what must be TRUE):
  1. A check that operates across a corridor's full `historical_archive.read_history` output (not
     `units_def.validate_pipeline_row`'s single-row unit/range check) flags physically-implausible
     values — e.g. an `air_temp`/`wind_speed`/`solar_radiation`/`dlr_amps` run that repeats one
     value unchanged across consecutive rows (stuck sensor) or jumps inconsistently against its
     immediate neighbors (spike) — and the flagging policy (flag-only vs. exclude vs. impute) is
     written down, per CLEAN-01.
  2. A documented gap-filling/interpolation function fills missing `datetime_utc` slots in a
     corridor's `read_history` output — including gaps left behind when a Phase 2 scheduled cycle
     failed and was skipped (Phase 2 SC #3) — before that history is handed to
     `forecast_ampacity` or `AnomalyDetector.for_corridor`, per CLEAN-02.
  3. `append_observation` (or a reconciliation pass run over what it has already written) enforces
     at most one row per (`corridor`, `datetime_utc`) slot in the archive, so a primary provider's
     reading and a later fallback-provider's reading (`weather_provider.py`'s station/grid
     provider composition) for that same slot cannot both land as two separate,
     possibly-conflicting rows, per CLEAN-03.
  4. Rows a cleaning pass touched (flagged, interpolated, or reconciled) are distinguishable from
     rows read straight off `append_observation`'s original writes, so Phase 4's real-data
     validation can tell which inputs were raw sensor readings and which were cleaned before
     drawing a calibration conclusion.
**Plans**: TBD

### Phase 4: Real-Data Validation
**Goal**: The integrated, real-data pipeline's output is verified as trustworthy — both the
physical plausibility of its corridor ratings and the statistical calibration of its forecast and
anomaly-detection methods — against real historical ERCOT data, not synthetic fixtures.
**Depends on**: Phase 3 (needs the archive's outliers, gaps, and duplicate/conflicting rows
addressed first, so its forecast/anomaly calibration findings measure real signal rather than
archive defects — see Overview)
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
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Pipeline Integration | 0/TBD | Not started | - |
| 2. Automated Scheduling | 0/TBD | Not started | - |
| 3. Data Cleaning | 0/TBD | Not started | - |
| 4. Real-Data Validation | 0/TBD | Not started | - |
