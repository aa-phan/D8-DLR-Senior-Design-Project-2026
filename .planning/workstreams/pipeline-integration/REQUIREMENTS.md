# Requirements: Dynamic Line Rating (DLR) System — Pipeline Integration Track

**Defined:** 2026-09-14
**Core Value:** The end-to-end pipeline produces valid ampacity forecasts — weather ingestion through thermal model through export — and runs without manual intervention, while never letting an unreliable input silently overstate what a line can safely carry.

## v1.2 Requirements

Requirements for the Pipeline Integration & Real-Data Verification track (one of three
independent post-v1.1 development tracks — see `docs/data-science/DEVELOPMENT-TRACKS.md`
Track 1). Each maps to roadmap phases in this workstream.

### Pipeline Integration

- [ ] **PIPE-01**: The DLR pipeline runs corridor discretization, anomaly detection, and
  ampacity forecasting as one connected sequence against real accumulating historical data —
  not three separate code paths (`rate_corridor`, `AnomalyDetector`, `forecast_ampacity`)
  connected only by their own test suites, as today.
- [ ] **PIPE-02**: The integrated pipeline run executes automatically on a recurring schedule,
  not only via manual invocation, so historical archive data and ratings accrue continuously
  without a human running it each time.

### Real-Data Validation

- [ ] **VAL-01**: The integrated pipeline, run against real historical ERCOT data for the two
  existing corridors (Austin↔Corpus Christi, Midland↔El Paso), produces ampacity ratings that
  are reasonable when compared against published static line ratings (SLR) for those lines.
- [ ] **VAL-02**: Today's statistical forecast band (naive/EWM in `ampacity_forecast.py`) and
  anomaly-detection thresholds (`mean ± k·std` in `anomaly_detector.py`) are checked against
  real historical data, and their calibration quality is documented. Scoped to the *current*
  code — re-validating whatever model Track 2 (ML Model Development) eventually builds is
  Track 2's own responsibility, not repeated here.

## Out of Scope

Explicitly excluded from this workstream. Documented to prevent scope creep and duplicate work
across tracks.

| Feature | Reason |
|---------|--------|
| Building or training an ML forecasting/anomaly-detection model | Track 2 (ML Model Development)'s responsibility |
| Sourcing real transmission-line corridor geometry | Track 3 (Real Corridor Geometry)'s responsibility |
| `api/`/`frontend/` serving layer | Software sub-team's scope, per `PROJECT.md` "Out of Scope" |
| Synoptic fallback wiring + `PRD.md`/`data_provider.md` ratification (WX-06, WX-08) | Already scoped and roadmapped in the `multi-provider-weather` workstream's Phase 10 — not duplicated here |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PIPE-01 | Phase 1 (Pipeline Integration) | Pending |
| PIPE-02 | Phase 2 (Automated Scheduling) | Pending |
| VAL-01 | Phase 3 (Real-Data Validation) | Pending |
| VAL-02 | Phase 3 (Real-Data Validation) | Pending |

**Coverage:**
- v1.2 requirements: 4 total
- Mapped to phases: 4
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-14*
*Last updated: 2026-09-14 after ROADMAP.md creation (3 phases, 100% coverage)*
