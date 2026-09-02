# Requirements: Dynamic Line Rating (DLR) System

**Defined:** 2026-09-02
**Core Value:** The end-to-end pipeline produces valid ampacity forecasts — weather ingestion
through thermal model through export — and runs without manual intervention, while never letting
an unreliable input silently overstate what a line can safely carry.

**Source:** `docs/data-science/PRD.md` (single PRD, no competing variants). Requirement IDs
(`DS-F1`–`DS-F12`, `DS-NF1`–`DS-NF5`) match the PRD's own numbering so this file stays traceable
back to the source document and its component specs (`docs/data-science/specs/C1`–`C10`).
Checkboxes reflect actual repo state as of 2026-09-02 (brownfield onboarding — status pulled from
`PRD.md` §5/§6 and each owning component's spec, not re-derived from scratch).

## v1 Requirements

All requirements below are in v1 scope — the source PRD does not distinguish a v1/v2 split; every
functional and non-functional requirement it lists is part of this subsystem's committed scope.

### Weather Ingestion

- [x] **DS-F1**: Discover weather stations near defined transmission corridors — owned by C4
- [x] **DS-F2**: Fetch time-series weather observations (temp, wind speed/direction, solar,
      humidity) for target stations, behind a provider-agnostic adapter — owned by C4

### Thermal Modeling & Rating Comparison

- [x] **DS-F3**: Compute wind component perpendicular to the line for forced-convection cooling —
      owned by C5
- [x] **DS-F4**: Compute steady-state IEEE 738 ampacity from weather + conductor properties,
      validated against a published reference — owned by C5
- [ ] **DS-F5**: Compare DLR against a static rating and flag uplift/headroom — owned by C1, C5.
      Partial: per-location lookup table exists (`config.py::STATIC_RATINGS`, now the 4 documented
      TX cities per `docs/data-science/decisions/geographic_scope.md`) but is not yet wired to
      select a location per run (uses a uniform fallback). The scope decision that previously
      blocked this is resolved; remaining work is pure wiring, not a decision gap.

### Data Contract & Validation

- [x] **DS-F6**: Validate units and physical ranges across all pipeline data — owned by C2
      (`PIPELINE_SCHEMA`, enforced automatically at the end of `run_pipeline`)

### Safety & Fallback

- [ ] **DS-F7**: Detect unreliable/anomalous inputs and fall back to SLR (Static Line Rating) —
      owned by C7. Partial: deterministic threshold gates (G1–G5) exist, but the gated ampacity
      value is computed with a placeholder formula that disagrees with the real thermal model
      (C5 not yet wired into C7).

### Grid Integration

- [x] **DS-F8**: Merge DLR output with real ERCOT grid load for a holistic capacity-vs-demand
      view — owned by C6. Note: the live ERCOT pull currently fails with a deterministic
      `Bad CRC-32` error inside the third-party `gridstatus` library — an external dependency
      issue, not a gap in this requirement's implementation.

### Export & Visualization

- [x] **DS-F9**: Export results to CSV and produce summary plots — owned by C3

### Spatial (Corridor Discretization)

- [ ] **DS-F10**: Discretize a transmission corridor into multiple geographic points and take the
      minimum ampacity as the corridor-level rating — owned by C8. Not started. The only existing
      artifact (`station_explorer.py::CORRIDORS`) ranks station proximity to five fixed points —
      no notion of a line, route, or per-point ampacity reduction exists yet.

### Predictive (Forecasting & Learned Anomaly Detection)

- [ ] **DS-F11**: Forecast ampacity ahead of real time (regression/ML) — owned by C9. Not started;
      blocked by accumulated historical data volume as well as by phase ordering.
- [ ] **DS-F12**: Anomaly detection via a model trained on historical baselines, additive to (not
      a replacement of) C7's fallback path — owned by C10. Not started; hard-blocked by C7 (needs
      the gating framework and a correct ampacity computation to detect anomalies against).

### Non-Functional Requirements

- [x] **DS-NF1**: Unit correctness at every module boundary (API response → pipeline row →
      safety monitor → MW) — enforced by C2's `Q` quantity wrapper and `@check_units` decorator
- [x] **DS-NF2**: Reproducibility — same station IDs, time window, and conductor config always
      produce the same output; no wall-clock-dependent logic in the ampacity math
- [x] **DS-NF3**: No secrets committed — `SYNOPTIC_TOKEN` lives in `.env`/environment only,
      `.env` is gitignored
- [x] **DS-NF4**: Modularity — components remain independently workable; no component requires
      another dev's in-progress, uncommitted changes to compile or run
- [ ] **DS-NF5**: Fail-safe by default — any missing sensor, broken link, out-of-range reading,
      implausible rating, or large rating swing must resolve toward the static rating, never an
      optimistic guess. Structurally present (C7's gates exist), but not fully realized until C7
      is unified with the real thermal model (Phase 3) — a gated value can currently disagree with
      what IEEE 738 would actually compute for the same inputs.

## v2 Requirements

None identified. The source PRD defines a single, complete v1 scope for this subsystem (all 12
functional + 5 non-functional requirements above); no deferred backlog exists in this ingest set.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| PSS/E grid simulation and load-flow integration | Owned by the Power Systems sub-team; this subsystem only supplies ampacity/MW values as input |
| N-1 contingency screening, reactive power / voltage stability analysis | `PRD.md` §1 explicitly scopes this to other sub-teams |
| UI dashboard implementation | Owned by the Software sub-team (`docs/frontend/`, `frontend/`, `api/` are placeholders); this subsystem only needs to publish a stable output schema (C3) |
| A second weather provider (NOAA/NSRDB) implemented now | Provider choice is a genuinely open decision (`PRD.md` §7.1); implementing NOAA now would prematurely resolve it. `weather_provider.py`'s adapter boundary exists specifically to defer this without blocking downstream work |

## Traceability

Which phases cover which requirements. Phase numbers match `.planning/ROADMAP.md`.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DS-F6 | Phase 1 | Complete |
| DS-F9 | Phase 1 | Complete |
| DS-NF1 | Phase 1 | Complete |
| DS-NF2 | Phase 1 | Complete |
| DS-NF3 | Phase 1 | Complete |
| DS-NF4 | Phase 1 | Complete |
| DS-F1 | Phase 2 | Complete |
| DS-F2 | Phase 2 | Complete |
| DS-F3 | Phase 2 | Complete |
| DS-F4 | Phase 2 | Complete |
| DS-F5 | Phase 2 | In Progress (partial — see note above) |
| DS-F8 | Phase 2 | Complete |
| DS-F7 | Phase 3 | Pending |
| DS-F10 | Phase 3 | Pending |
| DS-NF5 | Phase 3 | In Progress (partial — see note above) |
| DS-F11 | Phase 4 | Pending |
| DS-F12 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0 ✓

---
*Requirements defined: 2026-09-02*
*Last updated: 2026-09-02 after initial project setup (doc-ingest synthesis)*
