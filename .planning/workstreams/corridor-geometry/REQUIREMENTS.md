# Requirements: Dynamic Line Rating (DLR) System — Real Corridor Geometry Track

**Defined:** 2026-09-14
**Core Value:** The end-to-end pipeline produces valid ampacity forecasts — weather ingestion through thermal model through export — and runs without manual intervention, while never letting an unreliable input silently overstate what a line can safely carry.

## v1.4 Requirements

Requirements for the Real Corridor Geometry track (one of three independent post-v1.1
development tracks — see `docs/data-science/DEVELOPMENT-TRACKS.md` Track 3). Each maps to
roadmap phases in this workstream.

`backend/config.py::CORRIDOR_ENDPOINTS` defines the two existing corridors (Austin↔Corpus
Christi, Midland↔El Paso) as straight city-centroid-to-city-centroid pairs — a known
placeholder. The System Design Report states explicitly that "during the implementation phase,
this will be replaced with actual transmission line geometry that traces the true conductor
path." That replacement has not happened. This track does it.

### Data Sourcing

- [ ] **GEOM-01**: Real substation-to-substation transmission-line route geometry is obtained
  for the two existing corridors, coordinated with the Power Systems (PSS/E) sub-team as the
  source (they likely already have or need the same real line geometry for their own grid
  simulation work).
- [ ] **GEOM-02**: The team decides whether corridor coverage should expand beyond the current
  two pairs once real geometry sourcing is in place. This is a decision record, not necessarily
  new code — it may or may not produce additional corridors in this milestone.

### Integration

- [ ] **GEOM-03**: `backend/config.py::CORRIDOR_ENDPOINTS` (or its replacement) and
  `corridor_discretization.py`'s point-generation logic use the real route geometry from
  GEOM-01 instead of straight-line city-centroid interpolation, with existing corridor rating
  behavior (thermal model calculation, fail-safe fallback, provenance) unaffected by the
  geometry change.

## Out of Scope

Explicitly excluded from this workstream. Documented to prevent scope creep and duplicate work
across tracks.

| Feature | Reason |
|---------|--------|
| Pipeline wiring / scheduling the integrated run | Track 1 (Pipeline Integration)'s responsibility |
| Building or training an ML forecasting/anomaly-detection model | Track 2 (ML Model Development)'s responsibility |
| PSS/E's own grid simulation / load-flow work | Owned by the Power Systems sub-team — this track only consumes their line-geometry data as an input, per `PROJECT.md` "Out of Scope" |
| `api/`/`frontend/` serving layer | Software sub-team's scope, per `PROJECT.md` "Out of Scope" |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| GEOM-01 | Phase 1 (Define & Request Real Corridor Geometry) | Pending |
| GEOM-02 | Phase 1 (Define & Request Real Corridor Geometry) | Pending |
| GEOM-03 | Phase 2 (Integrate Real Corridor Geometry into Point Generation) | Pending |

**Coverage:**
- v1.4 requirements: 3 total
- Mapped to phases: 3
- Unmapped: 0 ✓

**Note on GEOM-01 phasing:** GEOM-01 is mapped to Phase 1 because that is the first (and only
unilaterally completable) phase that delivers DS-side progress on it — defining the geometry data
contract and formally requesting it from the Power Systems sub-team. The requirement's full
real-world resolution (actual geometry data in hand) is an external dependency tracked as a
blocker in STATE.md; Phase 2 (GEOM-03) is explicitly gated on that external response arriving,
per ROADMAP.md's "External Dependency" section.

---
*Requirements defined: 2026-09-14*
*Last updated: 2026-09-14 after roadmap creation (v1.4, 2 phases, 3/3 requirements mapped)*
