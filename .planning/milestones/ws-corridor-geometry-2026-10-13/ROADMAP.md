# Roadmap: Real Corridor Geometry (v1.4)

**Workstream:** `corridor-geometry` (Track 3 of 3 post-v1.1 parallel DS-subsystem tracks — see
`docs/data-science/DEVELOPMENT-TRACKS.md`)

## Overview

`backend/config.py::CORRIDOR_ENDPOINTS` currently defines the two existing corridors
(Austin↔Corpus Christi, Midland↔El Paso) as straight-line, great-circle interpolations between
city centroids (`CITY_COORDINATES`, consumed by `corridor_discretization.py::interpolate_great_circle`).
This was always a known placeholder — the System Design Report states explicitly that "during
the implementation phase, this will be replaced with actual transmission line geometry that
traces the true conductor path." That replacement is this milestone's job.

Unlike the other two parallel v1.1+ tracks (Pipeline Integration, ML Model Development), this
workstream has a real, unresolved **external coordination dependency**: the real route geometry
must come from the Power Systems (PSS/E) sub-team, who likely already have — or need — the same
line geometry for their own grid simulation work. As of this roadmap's creation, the team does
**not** yet have this data and has not yet formally requested it. This roadmap reflects that
honestly rather than assuming the data simply arrives mid-roadmap:

- **Phase 1** is scoped to what the DS side can concretely do and verify *without* that data in
  hand: define the exact geometry data contract, formally request it from Power Systems, and
  record the team's coverage-expansion decision (GEOM-02).
- **Phase 2** is the actual code integration (GEOM-03) — and it is explicitly blocked on Phase 1's
  external request being answered. It cannot be planned in fine-grained detail, let alone
  executed, until real geometry data is in hand, because the concrete integration tasks depend on
  the shape of the data Power Systems actually returns.

## External Dependency — Read Before Planning Phase 2

**Phase 2 is blocked on an external deliverable outside this repo's control:** the Power Systems
sub-team returning real substation-to-substation route geometry that conforms to the data
contract Phase 1 produces. Do not plan or execute Phase 2 as if this data is already available —
check the Phase 1 decision record / STATE.md blockers section first. If Power Systems has not yet
responded, Phase 2 planning should wait, or (if partial/preliminary geometry is available) be
scoped explicitly to what has actually been received.

## Phases

**Phase Numbering:**
- Integer phases (1, 2): Planned milestone work
- This workstream starts at Phase 1 (independent phase numbering — this is a standalone
  workstream directory, not a continuation of any other track's phase sequence)

- [ ] **Phase 1: Define & Request Real Corridor Geometry** - Specify the exact geometry data
  contract needed, formally hand that request to the Power Systems sub-team, and record the
  team's corridor-coverage-expansion decision.
- [ ] **Phase 2: Integrate Real Corridor Geometry into Point Generation** - Once Power Systems
  delivers real route geometry, wire it into `CORRIDOR_ENDPOINTS`/`corridor_discretization.py`'s
  point generation in place of straight-line city-centroid interpolation, leaving corridor rating
  behavior unchanged. BLOCKED pending Phase 1's external request being answered.

## Phase Details

### Phase 1: Define & Request Real Corridor Geometry
**Goal**: The DS side has a complete, written specification of what "real corridor geometry"
must contain, that specification has been formally handed to the Power Systems sub-team as a
data request, and the team has decided (and recorded) whether corridor coverage should expand
beyond the current two pairs once real geometry sourcing is in place.
**Depends on**: Nothing (first phase)
**Requirements**: GEOM-01, GEOM-02
**Success Criteria** (what must be TRUE):
  1. A written corridor-geometry data contract exists (e.g.
     `docs/data-science/decisions/corridor_geometry_contract.md`) specifying: the geometry
     representation this pipeline needs — a real, ordered list of (lat, lon) points per corridor
     tracing the true substation-to-substation conductor path, not merely an assertion that data
     was "obtained" — which corridor keys it covers (`AUSTIN_CORPUS_CHRISTI`,
     `MIDLAND_EL_PASO`, matching `config.CORRIDOR_ENDPOINTS`), and the expected units/coordinate
     system.
  2. That contract has been formally communicated to the Power Systems sub-team as an explicit,
     dated data request — not merely drafted for internal use. The request itself (what was
     asked, of whom, and when) is recorded in a decision log or equivalent artifact.
  3. A decision record exists resolving GEOM-02: whether corridor coverage expands beyond the
     current two pairs (Austin↔Corpus Christi, Midland↔El Paso) once real geometry sourcing is
     in place, with the rationale for whatever was decided.
  4. This workstream's STATE.md explicitly records the unmet external dependency (real geometry
     data not yet in hand) as an active blocker, so no future session assumes Phase 2 can start
     without it.
**Plans**: TBD

### Phase 2: Integrate Real Corridor Geometry into Point Generation
**Goal**: `backend/config.py::CORRIDOR_ENDPOINTS` (or its replacement) and
`corridor_discretization.py`'s point-generation logic consume the real transmission-line route
geometry Power Systems delivered, in place of straight-line city-centroid interpolation, with
existing corridor rating behavior (thermal-model calculation, fail-safe fallback, archive
provenance) unaffected by the geometry change.
**Depends on**: Phase 1 — AND an external deliverable outside this repo's control: the Power
Systems sub-team actually returning real route geometry conforming to the Phase 1 contract. This
phase is BLOCKED until that data arrives and cannot be meaningfully detail-planned before then.
**Requirements**: GEOM-03
**Success Criteria** (what must be TRUE):
  1. Real route geometry received from Power Systems (an ordered list of (lat, lon) points per
     corridor tracing the true conductor path, per the Phase 1 contract) is validated against
     that contract and stored in the repo (a new data file or `config.py` structure) for
     `AUSTIN_CORPUS_CHRISTI` and `MIDLAND_EL_PASO` (plus any corridors added per the GEOM-02
     decision).
  2. `corridor_discretization.py`'s `discretize_corridor`/`corridor_geometry` generate corridor
     points from the real route geometry instead of `interpolate_great_circle`-based straight-line
     interpolation between `config.CITY_COORDINATES` city centroids.
  3. `rate_corridor`'s existing behavior is unchanged by the geometry swap: IEEE 738 thermal-model
     ampacity via `DLRSafetyMonitor`, the D-09 fail-safe fallback to `geometry.static_rating` for
     an exhausted point, and archive provenance (`historical_archive.build_archive_row`) all still
     function correctly against the new point set — confirmed by
     `backend/tests/corridor_discretization_test.py` (updated as needed) passing against real
     geometry inputs.
  4. `config.py`'s corridor-geometry section no longer documents itself as a "known placeholder"
     — the module comments are updated to reflect real geometry as the source of truth for
     corridor point generation.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 (Phase 2 additionally gated on the external dependency
above, independent of GSD phase-ordering mechanics)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Define & Request Real Corridor Geometry | 0/TBD | Not started | - |
| 2. Integrate Real Corridor Geometry into Point Generation | 0/TBD | Blocked (external dependency — pending Power Systems geometry delivery) | - |
