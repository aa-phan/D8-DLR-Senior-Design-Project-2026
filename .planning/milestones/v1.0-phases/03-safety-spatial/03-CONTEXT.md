# Phase 3: Safety & Spatial - Context

**Gathered:** 2026-09-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 3 delivers two things, per ROADMAP.md's Success Criteria:

1. **Safety monitor unification (C7):** the fail-safe fallback (`DLRSafetyMonitor`) must evaluate the same ampacity value the real IEEE 738 thermal model (C5) would compute for identical inputs — replacing the current placeholder formula. Any missing sensor, broken link, out-of-range reading, implausible rating, or large rating swing must fall back toward the static rating, never an optimistic guess.
2. **Corridor spatial discretization (C8):** given a defined transmission corridor, discretize it into multiple geographic points and report the minimum ampacity across those points as the corridor-level rating.
3. **One consistent geographic/corridor model** across station discovery, static ratings, and corridor discretization — not three mutually inconsistent ones (this was the blocking item before Phase 3 planning could start; see Decisions below for its resolution).

This discussion focused on the corridor/spatial and weather-provider gray areas (D-01 through D-09 below). Two additional C7-specific gray areas — the G1/G2-vs-G3/G4 fallback-target semantics, and the gate-2 test contradiction fix — were surfaced during `analyze_phase` but explicitly **not** selected for discussion this session; they remain open for the planner/researcher to investigate against `docs/data-science/specs/C7-safety-monitor.md`'s own Open Questions, or a future discussion pass.

</domain>

<decisions>
## Implementation Decisions

### Geographic scope (resolved prior to this discussion)
- **D-00:** The 4-city scope (Austin, Corpus Christi, Midland, El Paso) is authoritative, per `docs/data-science/decisions/geographic_scope.md` — already implemented in `backend/config.py::STATIC_RATINGS`. Carried forward here as locked context, not re-discussed.

### Corridor endpoint definition
- **D-01:** Corridors are defined by pairing the 4 cities into 2 line segments: **Austin↔Corpus Christi** and **Midland↔El Paso** — a natural geographic grouping (south-central pair, West Texas pair), not a full 6-pair mesh or a single 4-city chain. — **Reversibility:** reversible — a config-level pairing choice, easy to change or extend later.
- **D-02:** Corridor endpoint coordinates use **city-center lat/lon** (same precision level as `station_explorer.py`'s existing `CORRIDORS` dict), not a specific substation lookup. — **Reversibility:** reversible.

### Discretization density & geometry source
- **D-03:** Corridor geometry for Phase 3 is **synthetic straight-line (geodesic) interpolation** between the two city endpoints — matches C8 spec's own stated "initially synthetic" fallback path. Real GIS transmission-line geometry is explicitly deferred, not blocking. — **Reversibility:** reversible — C8 spec already anticipates swapping in real geometry later without an interface break.
- **D-04:** Each corridor is discretized into **5 points** (2 endpoints + 3 interior, evenly spaced along the line) — balances bottleneck-detection resolution against per-run API call volume. — **Reversibility:** reversible — a constant.
- **D-05:** Each of the 5 corridor points gets **its own independent weather fetch** (no nearest-station sharing across points) — simplest, most accurate per-point, matches C8's anticipated synchronous per-point call pattern. This means **10 weather fetches per run** across the 2 corridors (5 points × 2 corridors), before accounting for the candidate-probe fallback in D-08. — **Reversibility:** reversible.

### Weather data provider (revised mid-discussion based on live verification)
- **D-06:** Use a **broadened Synoptic query (not restricted to the WTM network)** with a per-location candidate-probe fallback, instead of adopting `docs/data-science/decisions/data_provider.md`'s full multi-provider composition (TCEQ CAMS + NSRDB + ASOS + Open-Meteo) for Phase 3. This decision was **revised live during discussion**: the user first chose to adopt the full composition based on `data_provider.md`'s existing vetting, then asked for a live access-level check against the actual Synoptic token before finalizing. A one-off diagnostic script (run by the user via their own shell, token never exposed to the assistant or committed to the repo) confirmed:
  - The current token sees **424 networks nationally**, not just the WTM network `station_explorer.py`/`config.py::DEFAULT_STATION_SOURCE` are currently hardcoded to.
  - Solar-tagged stations within 50km of each city: Austin 628, Corpus Christi 64, Midland 30, El Paso 94.
  - A live timeseries pull (8 candidate stations per city) returned **real non-null solar data** for Austin 6/8 (75%), Corpus Christi 2/8 (25%), Midland 2/8 (25%), El Paso 3/8 (38%) — access is real and non-zero for every city, but inconsistent per-station (not every listed station is actually pullable under this token's tier).
  - Given this, broadening the existing Synoptic integration (reusing `backend/weather_provider.py::fetch_weather` / `backend/dlr_pipeline.py::fetch_timeseries`) is viable and far cheaper than building 4 new provider adapters. `data_provider.md`'s full composition is **deferred, not rejected** — a natural Phase 4 candidate given its overlap with C9/C10's historical-backfill needs (see Deferred Ideas). — **Reversibility:** costly — reverting to (or later adding) the full multi-provider composition is real, non-trivial adapter-building work, but it is purely additive: nothing about the broadened-Synoptic approach needs to be torn out first.
- **D-07:** `backend/weather_provider.py::fetch_weather`'s station-ID-based signature is **preserved for callers**; a new internal station→lat/lon mapping layer resolves IDs before any future grid-based provider call, rather than changing the public signature to accept lat/lon directly. — **Reversibility:** reversible — internal implementation detail behind an unchanged public interface.
- **D-08:** Per-location (per city endpoint AND per corridor interior point) weather lookup probes candidate stations **nearest-5 first**; if all 5 return no usable (non-null) data, expand to the next 5 nearest (10 total) before giving up. — **Reversibility:** reversible — a tunable constant/algorithm, not a structural commitment.
- **D-09:** If all 10 nearest candidates are exhausted with no usable data for a given location, **fall back to the static rating** for that point — consistent with C7's fail-safe-by-default philosophy (DS-NF5), treated the same as any other data-loss gate rather than as a special case. — **Reversibility:** reversible.

### Claude's Discretion
- Exact interior-point spacing algorithm for the 5-point geodesic interpolation (equal-distance vs. equal-fraction-of-great-circle) — not discussed, left to planner/implementer as a standard interpolation choice.
- Whether the station→lat/lon mapping layer (D-07) is a new module, a method on the existing `weather_provider.py`, or folded into `station_explorer.py` — an implementation-location choice, not a user-facing decision.
- Exact fallback-target semantics for G1/G2 vs. G3/G4 in `DLRSafetyMonitor` (surfaced as a gray area, not selected for discussion) — planner/researcher should investigate against C7 spec's own Open Questions before locking behavior.
- Gate-2 test contradiction fix approach (surfaced as a gray area, not selected for discussion) — same, defer to planner/researcher investigation of C7 spec's Open Questions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Geographic scope & weather provider (this phase's core decisions)
- `docs/data-science/decisions/geographic_scope.md` — the 4-city scope resolution (D-00), plus its own Open Questions on city→corridor mapping — largely answered by D-01/D-02 here, but re-read for the parts not covered (e.g. re-sourcing static ratings)
- `docs/data-science/decisions/data_provider.md` — the full provider vetting log; its "Recommended Composition" is the deferred Phase 4 candidate referenced in D-06 and Deferred Ideas
- `backend/weather_provider.py` — existing adapter boundary; D-06/D-07 build on this, do not replace it
- `backend/station_explorer.py` — existing `CORRIDORS` dict and nearest-station pattern; D-01/D-08 extend this pattern rather than inventing a new one
- `backend/config.py` — `STATIC_RATINGS` (4-city, per D-00), `DEFAULT_STATION_SOURCE` (currently WTM-only, needs updating per D-06)

### Component specs
- `docs/data-science/specs/C7-safety-monitor.md` — safety monitor spec, including the two gray areas (fallback-target semantics, gate-2 test contradiction) left to Claude's discretion above
- `docs/data-science/specs/C8-corridor-discretization.md` — corridor discretization spec; D-01 through D-05 directly answer this spec's own Open Questions ("Real geometry source", "How many points per corridor", "synchronous vs batched fetch")
- `docs/data-science/specs/C4-weather-ingestion.md` — current Synoptic ingestion implementation D-06/D-07/D-08 build on

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — DS-F7, DS-F10, DS-NF5 (this phase's requirements)
- `.planning/ROADMAP.md` — Phase 3 Success Criteria (the 4 criteria this phase must satisfy)
- `.planning/codebase/CONCERNS.md` — documents the specific known issues this phase addresses (outdated ampacity formula, undocumented fallback distinction, duplicate range bounds, corridor-not-started)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/thermal_model.py::ieee738_ampacity` — the real, bug-fixed (Phase 2) IEEE 738 implementation C7 must call instead of its placeholder formula
- `backend/station_explorer.py::CORRIDORS` + `haversine_km` — existing corridor-naming and distance-calculation pattern; D-01 extends this dict's shape (city-pair endpoints) rather than replacing the haversine logic
- `backend/weather_provider.py::fetch_weather` — existing adapter boundary C8's per-point fetches and the new candidate-probe logic (D-08) should call through, not bypass
- `backend/ercot_dlr_merger.py::process_dlr_to_hourly` — existing `.min()` resampling pattern C8's spec explicitly analogizes to for the corridor-level minimum-ampacity reduction (same "weakest link" principle, time axis vs. space axis)

### Established Patterns
- Fail-safe-by-default (DS-NF5): every prior safety/data-loss gate in this codebase (C7's G1-G5) falls back toward the static rating on any inability to trust a value — D-09 extends this same pattern to weather-provider exhaustion, not a new philosophy
- Config centralization (C1): per-location values live in `config.py`, not scattered literals — the new candidate-probe / station-mapping logic should follow this convention

### Integration Points
- C7 (`DLRSafetyMonitor._compute_ampacity`) → `thermal_model.ieee738_ampacity` (currently disconnected, this phase's core fix)
- C8 (new corridor discretization module) → `weather_provider.fetch_weather` (per D-06/D-08, via the new candidate-probe + station-mapping layer) → `thermal_model.ieee738_ampacity` (per-point) → new min-reduction step (per D-04/D-05, analogous to C6's `.min()` pattern)

</code_context>

<specifics>
## Specific Ideas

No particular UI/output-format requests — this phase is backend logic (safety gating + spatial discretization), not user-facing. The live Synoptic access verification (D-06) was itself a specific, concrete request: "research into this to verify whether that is possible" — i.e. don't take the earlier vetting doc's assumptions at face value where a live check is possible and cheap.

</specifics>

<deferred>
## Deferred Ideas

- **Full multi-provider weather composition** (TCEQ CAMS + NSRDB PSM v4 + ASOS 1-minute + Open-Meteo), per `data_provider.md`'s "Recommended Composition" — deferred pending evidence that the broadened-Synoptic fallback-probe approach (D-06) proves insufficient in practice. Natural Phase 4 candidate given its overlap with C9/C10's historical-backfill needs (`ROADMAP.md`'s note on starting historical accumulation during Phase 3 lead time).
- **G1/G2 vs. G3/G4 fallback-target semantics** and the **gate-2 test contradiction** — real open questions in C7's spec, surfaced during analysis but not selected for discussion this session. Not out-of-phase-scope (they're squarely C7 work), just not discussed yet — left to Claude's discretion / a future discussion pass per the Decisions section above.

### Reviewed Todos (not folded)
None — no `todo.match-phase` matches were surfaced for Phase 3 in this session.

</deferred>

---

*Phase: 3-Safety & Spatial*
*Context gathered: 2026-09-03*
