# Requirements: Dynamic Line Rating (DLR) System — Input Provenance & Power Systems Contract Track

**Defined:** 2026-10-17
**Core Value:** Every number the rating depends on — conductor temperature limit, static ratings, line orientation, bundle configuration — has a named source, a stated basis, and a known sensitivity, so a computed ampacity is never silently built on an undocumented assumption, and the hand-off to Power Systems is a confirmed contract rather than an informal understanding.

## v1.5 Requirements

Requirements for the Input Provenance & Power Systems Contract track (a fourth post-v1.1
development track, opened after the corridor-geometry track was retired on 2026-10-12). Each
maps to roadmap phases in this workstream.

### Input Provenance

- [ ] **PROV-01**: The maximum conductor temperature (`max_temp_c`, which `ieee738_ampacity`
  uses as the fixed conductor temperature `T_max`) has a documented source and basis, and the
  75 °C in `backend/config.py` / `ConductorConfig` is reconciled with the 100 °C the project
  reports state. Code, config comments, `README.md`, and `docs/data-science/specs/C5-thermal-model.md`
  all state the same value and say whether it is a normal or an emergency limit.
- [ ] **PROV-02**: Every `STATIC_RATINGS` and `RATING_BOUNDS_BY_LOCATION` entry records its
  provenance: the Power Systems bundle range it derives from, whether that range is a normal or
  emergency rating, the conductor temperature it assumes, who supplied it, and on what date.
  Where Power Systems cannot say, the entry is labeled unverified rather than left implicit.
- [ ] **PROV-03**: Each city's line bearing (`config.CITY_LINE_BEARING_DEG`) is either replaced
  by a real line orientation with a cited source, or kept as an explicitly documented placeholder
  with its effect on perpendicular-wind ampacity quantified.
- [ ] **PROV-04**: The per-city subconductor-per-phase counts (`SUBCONDUCTORS_PER_PHASE`,
  currently the Power Systems team's provisional assumption) are confirmed with Power Systems or
  remain labeled provisional in every place the derived per-conductor numbers are shown.
- [ ] **PROV-05**: The sensitivity of computed ampacity to the unresolved inputs is measured and
  written down: the effect of 75 / 90 / 100 °C on rating, and of plausible bearing and
  static-rating alternatives, with a recorded decision on whether any shadow-collection model
  artifact must be refit before the 2026-11-01 model freeze.
- [ ] **PROV-06**: Two input-data anomalies are resolved or explicitly accepted: the constant
  `solar_radiation == 1000.0` on five of the six committed station files (placeholder or real),
  and the unreproduced `Bad CRC-32` failure in `ercot_data_retriever.py::pull_ercot_data`.

### Power Systems Contract

- [ ] **PSSE-01**: The DS → Power Systems (PSS/E) hand-off is a confirmed interface contract —
  file format, cadence, exact fields, granularity (per city), the rating basis (normal vs.
  emergency, conductor temperature), and whether the value is current or forecast — agreed with
  the Power Systems sub-team and recorded in place of the informal
  `docs/data-science/decisions/pss_e_handoff.md` note.
- [ ] **PSSE-02**: The DS pipeline can emit the contract's file from its per-city outputs, with
  the rating basis and provenance flags from PROV-01 and PROV-02 carried through, and a test
  that checks the emitted file against the contract.

## Out of Scope

Explicitly excluded from this workstream. Documented to prevent scope creep and duplicate work
across tracks.

| Feature | Reason |
|---------|--------|
| Shadow-evaluation scoring, the confirmation protocol v3 signature, and the 2026-11-24 evaluation | `ml-modeling` workstream; this track only reports whether an input change forces a refit |
| Wiring `rate_city`, anomaly detection, and forecasting into one scheduled run | `pipeline-integration` workstream (needs rescoping for per-city rating) |
| Dashboard and API (F1–F8, OD-1 to OD-13) | Software sub-team scope; consumes this track's contract but does not belong to it |
| Sag computation (OD-4) and "trusted duration" definition (OD-3) | Scope decisions owned by the team; not input provenance |
| Re-opening the corridor model | Retired 2026-10-12 (`decisions/point_scope.md`) |
| Editing frozen modules and data (`forecast_experiment.py`, `forecast_experiment_audit.py`, `legacy_corridor.py`, legacy corridor-era artifacts) | Frozen by the owner; checksummed |
| Changing model artifacts after the 2026-11-01 freeze based on FRESH data | Violates the anti-peeking rules in `confirmation_protocol_v3_per_city.md` |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| PROV-01 | Phase 1 (Provenance Audit), Phase 3 (Apply Confirmed Values) | Pending |
| PROV-02 | Phase 1 (Provenance Audit), Phase 3 (Apply Confirmed Values) | Pending |
| PROV-03 | Phase 1 (Provenance Audit), Phase 3 (Apply Confirmed Values) | Pending |
| PROV-04 | Phase 1 (Provenance Audit), Phase 3 (Apply Confirmed Values) | Pending |
| PROV-05 | Phase 2 (Sensitivity & Freeze Decision) | Pending |
| PROV-06 | Phase 1 (Provenance Audit) | Pending |
| PSSE-01 | Phase 4 (Power Systems Contract) | Pending |
| PSSE-02 | Phase 4 (Power Systems Contract) | Pending |

**Coverage:** 8/8 requirements mapped.
