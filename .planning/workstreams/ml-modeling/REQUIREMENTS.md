# Requirements: Dynamic Line Rating (DLR) System — ML Model Development Track

**Defined:** 2026-09-14
**Core Value:** The end-to-end pipeline produces valid ampacity forecasts — weather ingestion through thermal model through export — and runs without manual intervention, while never letting an unreliable input silently overstate what a line can safely carry.

## v1.3 Requirements

Requirements for the ML Model Development track (one of three independent post-v1.1
development tracks — see `docs/data-science/DEVELOPMENT-TRACKS.md` Track 2). Each maps to
roadmap phases in this workstream.

Today's code satisfies the naming and test contracts for "Ampacity Forecasting" (C9) and
"Learned Anomaly Detection" (C10) but is not ML: `ampacity_forecast.py` implements only naive
last-value and EWM statistical methods, and `anomaly_detector.py` implements only a rolling
`mean ± k·std` threshold. Both are tested exclusively against synthetic fixtures. This track
builds the actual trained models the PRD originally scoped.

### Forecasting

- [ ] **FCST-01**: An ML model (regression or neural network, per PRD §8's original C9 scope
  and the IEEE Trans. Smart Grid prior art in `Prior Art Report.md`) forecasts ampacity ahead
  of real time, dropped in behind `ampacity_forecast.py`'s existing `forecast_ampacity`
  function signature and `PIPELINE_SCHEMA` output columns — replacing or extending, not
  discarding, the current naive/EWM methods.
- [ ] **FCST-02**: The forecasting model's accuracy and calibration are validated against real
  historical archive data (not synthetic fixtures) and the results are documented.

### Anomaly Detection

- [ ] **ANOM-01**: A trained model — trained on historical per-variable baselines (wind, temp,
  solar, load), per PRD §8's original C10 scope — replaces or augments the `mean ± k·std`
  threshold in `anomaly_detector.py`, dropped in behind the existing `AnomalyDetector` interface
  so it plugs into `DLRSafetyMonitor`'s G6 gate unchanged.
- [ ] **ANOM-02**: The anomaly-detection model's false-positive/false-negative behavior is
  validated against real historical data and the results are documented.

## Out of Scope

Explicitly excluded from this workstream. Documented to prevent scope creep and duplicate work
across tracks.

| Feature | Reason |
|---------|--------|
| Pipeline wiring / scheduling the integrated run | Track 1 (Pipeline Integration)'s responsibility |
| Sourcing real transmission-line corridor geometry | Track 3 (Real Corridor Geometry)'s responsibility |
| Changing the fail-safe contract (any gate resolving to an optimistic guess instead of the static rating) | Standing ethical commitment (`Project Definition.md`) — models must plug into the existing gate framework, not alter its fail-safe guarantee |
| `api/`/`frontend/` serving layer | Software sub-team's scope, per `PROJECT.md` "Out of Scope" |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FCST-01 | TBD | Pending |
| FCST-02 | TBD | Pending |
| ANOM-01 | TBD | Pending |
| ANOM-02 | TBD | Pending |

**Coverage:**
- v1.3 requirements: 4 total
- Mapped to phases: 0
- Unmapped: 4 ⚠️ (roadmap not yet created)

---
*Requirements defined: 2026-09-14*
*Last updated: 2026-09-14 after initial definition*
