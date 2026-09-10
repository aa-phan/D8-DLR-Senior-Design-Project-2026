# Phase 6: Multi-Provider Adapter Foundation - Context

**Gathered:** 2026-09-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Redesign `backend/weather_provider.py::fetch_weather`'s signature and extend `PIPELINE_SCHEMA`
(`backend/units_def.py`) with per-field provenance columns so a station-based provider (TCEQ/ASOS/
Synoptic) and a lat/lon-based grid provider (NSRDB/Open-Meteo) can both be combined into one row
per timestamp — **before any new provider is actually wired in** (that's Phases 7-9). No new
provider integration happens in this phase. Requirements: WX-05, WX-07.

</domain>

<decisions>
## Implementation Decisions

### Request interface shape
- **D-01:** `fetch_weather` takes a single type-dispatched `location` param (renamed from `stids`): a `list[str]` of station IDs dispatches to the station-based path; a `(lat, lon)` tuple dispatches to the grid-based path. — **Reversibility:** costly — every caller and every future provider adapter reads this signature; changing the dispatch shape again after Phase 7-9 land would touch every provider implementation.
- **D-02:** The rename from `stids` to `location` is invisible to existing callers because all 3 current call sites (`corridor_discretization.py`, tests) pass the argument positionally — no call-site changes required for WX-05.

### Provenance column granularity
- **D-03:** Four separate provenance columns are added to `PIPELINE_SCHEMA`: `wind_source`, `temp_source`, `humidity_source`, `solar_source` — one per weather-field family, not just the two (`wind_source`, `solar_source`) literally named as examples in `data_provider.md`. — **Reversibility:** one-way — `PIPELINE_SCHEMA`'s additive-only versioning rule (v2 precedent) means once these columns exist and are consumed downstream (exports/plots), collapsing them back into fewer columns would be a breaking schema change, not just an addition.
- **D-04:** Provenance columns store plain provider names as values (e.g. `"synoptic"`, `"tceq"`, `"nsrdb"`) rather than a separate primary/fallback flag or suffix. Whether a row came from a fallback (WX-06, Phase 10) is inferable from which provider name is present — Phase 10 adds new provider-name values with no schema change needed.
- All four provenance columns are added as `required: False`, following the existing v1→v2 additive-only rule (`units_def.py:324-330`) — no existing key's name, unit, or range changes. `PIPELINE_SCHEMA_VERSION` increments accordingly (per Roadmap Success Criteria #3).

### Row-keying / merge identity
- **D-05:** The join key for combining a station-based row and a grid-based row into "one row per timestamp" is **city name** (a key into `config.CITY_COORDINATES`/`STATIC_RATINGS`), not `stid` and not raw `(lat, lon)`. Every request in this codebase already resolves to one of the four cities.
- **D-06:** To preserve WX-05's "no call-site changes" requirement despite city-keying, `fetch_weather` resolves a station-based call's city **internally** (via `station_explorer.py`/`config.py` lookups) rather than requiring callers like `corridor_discretization.py` to pass a city explicitly. City-keying is an internal adapter implementation detail, not part of the public call signature. — **Reversibility:** costly — reversing this would require re-auditing every call site that currently passes bare stids to confirm none silently depended on city resolution happening internally.

### Proving the design in Phase 6
- **D-07:** Add a synthetic/mock grid-based provider function used **only in Phase 6's own test suite** to exercise the full merge path end-to-end (station row + grid row → one combined row, correct provenance columns) before Phase 7 wires the first real grid provider (Open-Meteo/ASOS). This mock is not registered in `fetch_weather`'s real provider dispatch — test-only scaffolding.

### Claude's Discretion
- Exact internal helper function names/module layout for the station→city resolution logic (D-06) and the synthetic grid-provider test fixture (D-07).
- Whether the mock grid provider from D-07 is deleted once Phase 7 lands a real grid provider, or kept as a lightweight fixture for future adapter tests — no user preference expressed either way.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider decision & design consequence
- `docs/data-science/decisions/data_provider.md` — full vetting log for all candidate weather providers; §"Recommended Composition" (lines 211-224) states the exact design consequence Phase 6 exists to resolve: `fetch_weather`'s station-ID-based signature vs. NSRDB/Open-Meteo's lat/lon-based requests, plus the standardization/provenance requirement this phase implements.
- `docs/data-science/PRD.md` §7.1 — Open Decisions: Weather data provider (the requirement this whole v1.1 milestone resolves; WX-08/Phase 10 will mark it ratified).

### Schema & versioning rule
- `backend/units_def.py:319-330` — `PIPELINE_SCHEMA` additive-only versioning rule (comment block directly above `PIPELINE_SCHEMA_VERSION`): keys are only ever added, always `required: False`, no existing key's name/unit/range ever changes. Phase 6's new provenance columns MUST follow this rule.

### Current adapter implementation
- `backend/weather_provider.py` — the module being redesigned; current signature is `fetch_weather(stids, start, end, provider="synoptic")`, delegates to `dlr_pipeline.fetch_timeseries`.
- `backend/corridor_discretization.py:392,439,531-617` — the only production caller that must keep working unchanged per WX-05; calls `fetch_weather([stid], start, end)` once per candidate station inside `rate_corridor`.

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — WX-05, WX-07 (this phase's requirements).
- `.planning/ROADMAP.md` — Phase 6 section has 5 concrete Success Criteria already locked (unified DataFrame output, unchanged callers, schema version increment, v2-era-row backward compatibility, `pytest -q` passing).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/config.py::CITY_COORDINATES` — already has lat/lon for all 4 target cities (Austin, Corpus Christi, Midland, El Paso); this is the natural target for grid-based `location` params and the internal station→city resolution (D-06).
- `backend/station_explorer.py` — existing station discovery/lookup logic; likely home for the station→city resolution helper needed by D-06 (exact lookup path not yet confirmed against current station_explorer.py contents — check during planning/research).

### Established Patterns
- `PIPELINE_SCHEMA_VERSION` additive-only pattern (v1→v2, Phase 4) is the direct precedent for this phase's v2→v3(?) schema extension — same rule, same review bar (`.venv/bin/python -m pytest -q` must show 0 failed after the change, per Success Criteria #5).
- Fail-safe philosophy (never silently overstate ampacity) — while not directly exercised by this phase's adapter-signature work, any ambiguity in provenance/merge logic should default toward being explicit (e.g., raising or flagging) rather than silently guessing a provider or city, consistent with the project's standing ethical commitment.

### Integration Points
- `backend/weather_provider.py::fetch_weather` is the sole integration point — every downstream consumer (C5 thermal model via C7 safety monitor, C8 corridor discretization) goes through it, never a provider directly.

</code_context>

<specifics>
## Specific Ideas

No specific UI/output-format requests — this is an internal adapter/schema phase with no user-facing surface. The design choices above (type-dispatched `location` param, city-keyed merge, 4-column provenance) are the concrete "specifics" for this phase.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 6's scope. Fallback-provider semantics (WX-06) and real second-provider wiring (WX-01 through WX-04) were referenced only to inform Phase 6's design decisions (D-04, D-07); they remain Phase 7-10 work, not pulled forward.

### Reviewed Todos (not folded)
None — `todo.match-phase` query returned 0 matches for Phase 6.

</deferred>

---

*Phase: 6-multi-provider-adapter-foundation*
*Context gathered: 2026-09-10*
