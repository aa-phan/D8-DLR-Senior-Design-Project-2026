# Roadmap: Dynamic Line Rating (DLR) System

## Overview

The DS subsystem turns raw weather telemetry into a trustworthy, physically-grounded ampacity
rating and guarantees it never silently overstates what a line can carry. The journey moves from
an explicit, validated data/config contract (Phase 1), through packaging the working
ingestion→thermal-model→grid-integration logic into provider-agnostic modules that produce a real
end-to-end ampacity value (Phase 2), to making the fail-safe fallback trustworthy by unifying it
with the real thermal model and extending single-station ratings to full corridors (Phase 3), and
finally layering forward-looking, learned intelligence on top of that safety-validated foundation
(Phase 4). This structure is adopted directly from `docs/data-science/ROADMAP.md` / `PRD.md` §4,
which already derived it from the real component dependency graph — Phases 1 and 2 are already
built and committed; Phases 3 and 4 are what's ahead.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [x] **Phase 1: Foundation & Data Contract** - Centralize config, define one canonical pipeline data contract, and make export/visualization work end-to-end
- [x] **Phase 2: Core Consolidation** - Package weather ingestion, IEEE 738 thermal modeling, and ERCOT grid integration into provider-agnostic, validated modules that produce a real ampacity value
- [ ] **Phase 3: Safety & Spatial** - Unify the safety monitor with the real thermal model and extend ratings from single stations to full transmission corridors
- [ ] **Phase 4: Predictive** - Add ampacity forecasting and learned anomaly detection on top of the Phase 3 safety foundation

## Phase Details

### Phase 1: Foundation & Data Contract
**Goal**: Establish one canonical data/config contract so every downstream module validates against a single source of truth and produces reproducible, auditable output.
**Depends on**: Nothing (first phase)
**Requirements**: DS-F6, DS-F9, DS-NF1, DS-NF2, DS-NF3, DS-NF4
**Success Criteria** (what must be TRUE):
  1. Running the pipeline twice with identical inputs (station IDs, time window, conductor config) produces the same output — no wall-clock-dependent or non-deterministic logic.
  2. Every pipeline output row is validated against `PIPELINE_SCHEMA` before being returned or exported; schema violations are logged, not silently dropped.
  3. A CSV export and a 4-panel summary plot are produced per station without manual post-processing.
  4. No API tokens or secrets appear in committed source; `SYNOPTIC_TOKEN` is read only from environment/`.env`.
  5. Config values (static ratings, conductor defaults, analysis window) live in one module (`config.py`) with no duplicate hardcoded literals scattered across other modules.
**Plans**: Complete (pre-GSD implementation — commit `9680772`, `3d5b64e`)

### Phase 2: Core Consolidation
**Goal**: Package the working weather-ingestion, thermal-model, and grid-integration logic into importable, provider-agnostic, validated modules that produce a real DLR end-to-end.
**Depends on**: Phase 1
**Requirements**: DS-F1, DS-F2, DS-F3, DS-F4, DS-F5, DS-F8
**Success Criteria** (what must be TRUE):
  1. Given a target corridor, the system discovers and lists nearby weather stations without manual lookup.
  2. Given station IDs and a time window, the system fetches weather observations behind a provider-agnostic adapter — swapping the underlying provider requires no changes to callers.
  3. Given weather + conductor properties, the system computes IEEE 738 steady-state ampacity that matches the published standard's own worked example within a documented tolerance.
  4. The computed DLR is compared against a static rating and flagged when it exceeds it (uplift/headroom).
  5. DLR output is merged with real ERCOT West-zone load data and converted to MW for a holistic capacity-vs-demand view.
**Plans**: Complete (pre-GSD implementation — commit `ffbea4f`)

**Known gap carried into Phase 3**: DS-F5's per-run location selection is not yet wired (uses a uniform fallback rating) — completing it depends on resolving the open geographic/corridor scope decision (see PROJECT.md Key Decisions), which Phase 3's corridor discretization work (C8) will force a resolution of.

### Phase 3: Safety & Spatial
**Goal**: Make the fail-safe fallback trustworthy by unifying it with the real thermal model, and extend ratings from single stations to full transmission corridors.
**Depends on**: Phase 2
**Requirements**: DS-F7, DS-F10, DS-NF5
**Success Criteria** (what must be TRUE):
  1. The safety monitor's plausibility gate evaluates the same ampacity value the real IEEE 738 thermal model would compute for the same inputs — no second, disagreeing formula.
  2. Any missing sensor, broken communication link, out-of-range reading, implausible computed rating, or large rating swing causes the reported rating to fall back toward the static rating, never toward an optimistic guess.
  3. Given a defined transmission corridor, the system discretizes it into multiple geographic points and reports the minimum ampacity across those points as the corridor-level rating.
  4. The geographic/corridor scope used across station discovery, static ratings, and corridor discretization is one explicitly chosen model — not three mutually inconsistent ones.
**Plans**: TBD

**Before planning this phase**: the geographic/corridor scope conflict (4 cities vs. 5 cities vs. 5 West-Texas corridors — see `.planning/INGEST-CONFLICTS.md` and PROJECT.md Key Decisions) should be resolved explicitly, since C8's corridor definition depends on knowing which location model is authoritative.

### Phase 4: Predictive
**Goal**: Move from reactive, current-conditions ratings to forward-looking, learned intelligence layered on top of the Phase 3 safety-validated foundation.
**Depends on**: Phase 3
**Requirements**: DS-F11, DS-F12
**Success Criteria** (what must be TRUE):
  1. Given historical weather and computed ampacity, the system produces a forecasted ampacity at a defined horizon ahead of real time.
  2. Forecast output extends `PIPELINE_SCHEMA` with new versioned columns (horizon, confidence/uncertainty band) rather than redefining the schema ad hoc.
  3. A learned anomaly-detection signal augments — not replaces — C7's fallback path: it can trigger the same fallback, through the same `{status, rating, fallback, alerts}` result shape.
  4. Given synthetic/injected anomalous conditions, the system falls back to the static rating rather than propagating a bad reading.
**Plans**: TBD

**Note**: historical data accumulation for C9/C10 has its own lead time distinct from phase ordering — starting a background historical weather/ampacity archive job during Phase 3 (rather than waiting until Phase 4 begins) avoids Phase 4 idling on data volume.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Data Contract | Pre-GSD (C1–C3 implemented) | Complete | 2026-08-24 |
| 2. Core Consolidation | Pre-GSD (C4–C6 implemented) | Complete | 2026-08-31 |
| 3. Safety & Spatial | 0/TBD | Not started | - |
| 4. Predictive | 0/TBD | Not started | - |
