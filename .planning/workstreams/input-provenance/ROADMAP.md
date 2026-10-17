# Roadmap: Input Provenance & Power Systems Contract (v1.5)

## Overview

This workstream (Track 4 of `docs/data-science/DEVELOPMENT-TRACKS.md`, opened 2026-10-17 after
the corridor-geometry track was retired) closes the gap between the inputs the rating pipeline
treats as facts and the inputs it can actually cite. Today `max_temp_c = 75.0` has no documented
source while project reports state 100 °C; `STATIC_RATINGS` are "unverified midpoints" derived
from Power Systems bundle ranges whose normal/emergency basis and conductor temperature are
unknown; `CITY_LINE_BEARING_DEG` values are placeholders carried over from the retired
corridors; subconductor counts are provisional; and the DS → PSS/E hand-off is an informal note
(`docs/data-science/decisions/pss_e_handoff.md`) that Power Systems has never confirmed. The
journey is: audit every input and send Power Systems one consolidated data request (Phase 1),
measure how much the open questions matter and decide before the model freeze whether anything
must be refit (Phase 2), apply whatever Power Systems confirms (Phase 3), then turn the
hand-off into a confirmed, tested contract (Phase 4).

This is a fresh, independent workstream — phase numbering starts at 1 and does not continue any
other workstream's numbering.

### Why Sensitivity (Phase 2) does not wait for Power Systems' answers

The 2026-11-01 model freeze is a hard date; Power Systems' response time is not under this
team's control. Phase 2 therefore runs on the *candidate* values (75 / 90 / 100 °C, plausible
bearing and static-rating alternatives) as soon as Phase 1 has enumerated them, so the freeze
decision — does any of the 12 `data/shadow/models/` artifacts, or the per-city "ml" forecast and
anomaly models, need to be refit because an input might change? — can be made before the
answers arrive. If the sensitivity is small, the freeze proceeds and Phase 3 applies the
confirmed values as documentation and config-only changes. If it is large, the owner decides
before 2026-11-01, because a bearing change after the freeze invalidates the shadow evidence.

### Why the PSS/E contract (Phase 4) depends on Phase 1, not Phase 3

The contract needs the *rating basis* (normal vs. emergency, conductor temperature) as a field,
and Phase 1's Power Systems response is what establishes it. It does not need Phase 3's config
changes to be applied, only the answers. Phase 4 can therefore start as soon as the Phase 1
request is answered, in parallel with Phase 3.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3, 4): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

- [ ] **Phase 1: Provenance Audit & Power Systems Request** - Inventory every rating input's source and basis, resolve the 75 vs. 100 °C question as far as the repo allows, and send Power Systems one consolidated data request
- [ ] **Phase 2: Sensitivity & Freeze Decision** - Measure how much the open inputs move computed ampacity and record, before 2026-11-01, whether any model artifact must be refit
- [ ] **Phase 3: Apply Confirmed Values** - Update config, `ConductorConfig`, docs, and tests to the values Power Systems confirms, and label whatever stays unverified
- [ ] **Phase 4: Power Systems Contract** - Replace the informal PSS/E hand-off note with a confirmed interface contract and an emitter that is tested against it

## Phase Details

### Phase 1: Provenance Audit & Power Systems Request
**Goal**: Every input the rating depends on has a recorded source, basis, and confidence level,
and the open questions are sent to Power Systems as one request instead of piecemeal.
**Depends on**: Nothing (first phase in this workstream)
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04, PROV-06
**Success Criteria** (what must be TRUE):
  1. A provenance ledger lists, for `max_temp_c`, each city's `STATIC_RATINGS` and
     `RATING_BOUNDS_BY_LOCATION` entry, `CITY_LINE_BEARING_DEG`, and `SUBCONDUCTORS_PER_PHASE`:
     the value, where it came from, the date, and whether it is confirmed, provisional, or
     unknown.
  2. The ledger states where the project reports give 100 °C and what each report means by it
     (normal limit, emergency limit, or the IEEE 738 worked example), so the 75 vs. 100 °C
     conflict is described precisely rather than as a rumor. The IEEE 738 worked-example use of
     100 °C (`docs/data-science/PRD.md`) is kept distinct from any statement about the real lines.
  3. One written request to the Power Systems sub-team asks for: the conductor temperature
     behind each bundle range, whether each range is a normal or an emergency rating, confirmed
     subconductor counts, real line orientations, and the interface details Phase 4 needs.
  4. The `solar_radiation == 1000.0` pattern and the `Bad CRC-32` ERCOT pull are each either
     resolved with evidence or recorded as accepted risks with the reason.
**Plans**: TBD

### Phase 2: Sensitivity & Freeze Decision
**Goal**: The team knows, in amperes and as a percentage of the static rating, how much each
unresolved input could change a computed rating, and the owner has a recorded decision on
refitting before the 2026-11-01 model freeze.
**Depends on**: Phase 1 (needs the enumerated candidate values; does not need Power Systems'
answers — see "Why Sensitivity does not wait" above)
**Requirements**: PROV-05
**Success Criteria** (what must be TRUE):
  1. For each of the four cities, `ieee738_ampacity` is evaluated across the candidate conductor
     temperatures (at least 75, 90, and 100 °C) under representative weather, and the resulting
     rating spread is tabulated against that city's static rating.
  2. The effect of plausible line-bearing alternatives on perpendicular-wind ampacity is
     quantified for each city, with the existing `decisions/line_bearing_check.md` and
     `line_bearing_check.py` reused rather than rebuilt.
  3. The write-up states which inputs matter and which do not, and says explicitly whether each
     existing model artifact (the 12 shadow artifacts and the per-city "ml" models) would need to
     be refit if the input changed.
  4. The owner's decision (refit, freeze as-is with the assumption documented, or defer) is
     recorded with a date before 2026-11-01. No analysis in this phase uses FRESH outcome data,
     consistent with the anti-peeking rules in `confirmation_protocol_v3_per_city.md`.
**Plans**: TBD

### Phase 3: Apply Confirmed Values
**Goal**: Code, config, and documentation agree with each other and with what Power Systems has
confirmed, and anything still unconfirmed is labeled as such wherever it is shown.
**Depends on**: Phase 2 (the freeze decision determines whether a change is config-only or
forces a refit); Power Systems' answers to the Phase 1 request
**Requirements**: PROV-01, PROV-02, PROV-03, PROV-04
**Success Criteria** (what must be TRUE):
  1. `max_temp_c` is the same value in `backend/config.py`, the `ConductorConfig` default in
     `backend/thermal_model.py`, `README.md`, and the C5 spec, and every location says whether it
     is a normal or an emergency limit.
  2. Each `STATIC_RATINGS` and `RATING_BOUNDS_BY_LOCATION` entry carries its provenance and
     basis in `config.py`, and `BUNDLE_CONFIG_VERSION` is bumped if the subconductor counts or
     the basis change.
  3. `CITY_LINE_BEARING_DEG` is either a cited real value per city or an explicitly labeled
     placeholder, and no document describes it as a measurement while it is not one.
  4. The full test suite passes, golden CSVs that depend on a changed value are regenerated
     deliberately and listed in the commit message, and frozen modules and legacy checksums are
     unchanged.
**Plans**: TBD

### Phase 4: Power Systems Contract
**Goal**: The DS → PSS/E hand-off is a confirmed interface that the pipeline can emit and a test
can verify, replacing the informal understanding.
**Depends on**: Phase 1 (the rating basis answers); can run in parallel with Phase 3
**Requirements**: PSSE-01, PSSE-02
**Success Criteria** (what must be TRUE):
  1. A contract document records file format, cadence, exact fields and units, per-city
     granularity, whether the value is current or forecast, and the rating basis, and it is
     marked as agreed with the Power Systems sub-team with a date and a named counterpart.
  2. The pipeline emits a file matching the contract from its per-city outputs, carrying the
     rating-basis and provenance fields, and falls back to the static rating (never a higher
     number) when the DLR value is flagged by the fail-safe chain.
  3. A test validates an emitted file against the contract's schema, using the same
     `units_def.PIPELINE_SCHEMA` unit labels the rest of the pipeline uses.
  4. `docs/frontend/PRD.md` OD-9 and `docs/data-science/decisions/pss_e_handoff.md` point to the
     contract, so the frontend's F7 has something to build against.
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3, with Phase 4 startable once Phase 1's Power Systems
answers arrive (parallel with Phase 3).

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Provenance Audit & Power Systems Request | 0/TBD | Not started | - |
| 2. Sensitivity & Freeze Decision | 0/TBD | Not started | - |
| 3. Apply Confirmed Values | 0/TBD | Not started | - |
| 4. Power Systems Contract | 0/TBD | Not started | - |
