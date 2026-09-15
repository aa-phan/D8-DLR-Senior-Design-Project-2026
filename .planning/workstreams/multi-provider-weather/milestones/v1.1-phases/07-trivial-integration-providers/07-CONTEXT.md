# Phase 7: Trivial-Integration Providers - Context

**Gathered:** 2026-09-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the two no-auth, trivial-integration weather providers behind the Phase 6 adapter
interface: **ASOS 1-minute** (Iowa Environmental Mesonet) as a wind/temp supplement to the
existing Synoptic station path, and **Open-Meteo** as the first real implementation of Phase
6's grid path, used as a standalone historical-backfill source for C9/C10 training data. No
other provider integration happens in this phase. Requirements: WX-02, WX-04.

</domain>

<decisions>
## Implementation Decisions

### ASOS merge semantics
- **D-01:** ASOS's finer-grained timestamps are added as **new rows** (union of timestamps with the existing Synoptic series), not merely used to improve values at Synoptic's existing timestamps. This is what actually delivers "higher-temporal-density" — the stated reason ASOS was chosen over alternatives in `data_provider.md`. — **Reversibility:** costly — once C9 feature-engineering code is written against a denser union-of-timestamps series, collapsing back to same-timestamp-only merging would change the shape (row count) of every derived dataset built on it.
- **D-02:** At an ASOS-only timestamp (a minute where Synoptic has no sample), fields ASOS doesn't measure (`solar_radiation`, `relative_humidity`) are left **null**, not backfilled or dropped. This is consistent with how `PIPELINE_SCHEMA` already treats absent per-field data (`required: False` columns, Phase 6 precedent) — C9 feature code decides how to handle sparsity per-feature, not this adapter.

### ASOS trigger
- **D-03:** ASOS supplementation is **automatic and transparent** inside every existing `fetch_weather(..., provider="synoptic")` station-based call — C5/C7/C8 do not need to know ASOS is involved, matching Phase 6's established philosophy that provider composition is an adapter-internal concern. — **Reversibility:** costly — every existing station-based call site starts making an additional network request; reversing this to opt-in later means auditing whether any caller came to implicitly depend on ASOS's presence in the merged result.

### Open-Meteo integration point
- **D-04:** Open-Meteo is wired as Phase 6's `_fetch_grid`'s first real `provider="open_meteo"` implementation, reachable via `fetch_weather(location=(lat, lon), provider="open_meteo")` — reusing the existing dispatch rather than adding a new standalone function. It remains reachable only via the grid path; C5/C7/C8's station-based calls never trigger it (that path continues to raise for any provider other than the ones actually implemented there).

### Failure handling
- **D-05:** If ASOS's or Open-Meteo's network call fails or returns malformed/unparseable data, `fetch_weather` **raises** rather than degrading silently to a partial result — consistent with the project's established "never silently overstate" provenance philosophy (Phase 6 D-04, `data_provider.md`). A caller relying on the ASOS supplement or an Open-Meteo backfill should know immediately that it didn't arrive, rather than unknowingly getting Synoptic-only data.

### Claude's Discretion
- Exact ASOS station-ID mapping per city (Austin-Bergstrom/KAUS, Corpus Christi Intl/KCRP, Midland Intl/KMAF, El Paso Intl/KELP — all already named in `data_provider.md`, no research needed) and where that mapping lives (e.g. alongside `config.CITY_COORDINATES` vs. a new lookup table).
- Exact unit-conversion helper structure for ASOS (knots→m/s, °F→°C) — whether inline or a shared conversion utility.
- Whether Open-Meteo's `provider="open_meteo"` dispatch requests a specific historical API variant (Archive API vs. Historical Forecast API) — both are documented as viable in `data_provider.md`; pick based on what best matches the phase's date-range needs during research/planning.
- Internal module/function layout for the ASOS fetch + merge-into-union-of-timestamps logic.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider decision & design consequence
- `docs/data-science/decisions/data_provider.md` §"ASOS 1-minute data" (lines 134-155) — full ASOS vetting: no-auth CGI endpoint, variable list (no solar), unit conversions needed, per-city airport station codes.
- `docs/data-science/decisions/data_provider.md` §"Open-Meteo" (lines 156-176) — full Open-Meteo vetting: no-auth REST/JSON, confirmed-live full variable set from a single request, Archive API (1940-present) vs. Historical Forecast API (2021-present) tradeoff.
- `docs/data-science/decisions/data_provider.md` §"Recommended Composition" (lines 211-224) — the design consequence Phase 6 built for and Phase 7 now fulfills.
- `docs/data-science/PRD.md` §7.1 — Open Decisions: Weather data provider (this milestone's driving requirement; WX-08/Phase 10 marks it ratified).

### Adapter interface this phase wires into
- `backend/weather_provider.py` — Phase 6's provider-agnostic adapter. Key seams for this phase: `_fetch_station` (currently only handles `provider="synoptic"`, raises otherwise — ASOS wiring happens here or in a helper it calls), `_fetch_grid` (currently unconditionally raises — Open-Meteo's `provider="open_meteo"` implementation goes here), `merge_observations`/`_prepare_merge_side` (Phase 6's `combine_first`-based same-timestamp merge — ASOS's union-of-timestamps merge (D-01) is a different shape and may need its own function alongside these, not a reuse of `merge_observations` as-is), `attach_provenance`/`PROVENANCE_FIELD_MAP` (must be called for both new providers per Success Criteria #3).
- `backend/units_def.py` — `PIPELINE_SCHEMA`, `KNOWN_PROVIDER_NAMES` (must add `"asos"` and `"open_meteo"` as legal provenance values — both are currently absent from the frozenset seeded in Phase 6).

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — WX-02, WX-04 (this phase's requirements).
- `.planning/ROADMAP.md` — Phase 7 section has 4 concrete Success Criteria already locked (ASOS supplement with unit conversion, Open-Meteo single-request backfill, correct provenance for both, no new secrets/.env entries for either).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/config.py::CITY_COORDINATES` — already has lat/lon for all 4 target cities; the natural input to an Open-Meteo grid request.
- `backend/weather_provider.py::attach_provenance` / `PROVENANCE_FIELD_MAP` — directly reusable for both new providers; already handles "set to provider name only where the mapped source column is present and non-null" (Success Criteria #3 requirement).
- `backend/units_def.py::KNOWN_PROVIDER_NAMES` — needs `"asos"` and `"open_meteo"` added (currently only seeded with the names anticipated in Phase 6: `"synoptic"`, `"tceq"`, `"asos"`, `"nsrdb"`, `"open_meteo"` per Phase 6's SUMMARY — verify during research whether `"asos"`/`"open_meteo"` are already present or still need adding).

### Established Patterns
- Phase 6's `combine_first`-based `merge_observations` is the precedent for "value from whichever side supplied it, non-null wins" merges — but it is a **same-index** merge (union of index labels, not union of a denser time axis within one label). ASOS's union-of-timestamps requirement (D-01) needs new logic; do not assume `merge_observations` can be reused unmodified for the ASOS case, though `_prepare_merge_side`'s indexing pattern is a useful precedent.
- Fail-loud philosophy (D-05) is a direct continuation of Phase 6 D-04's "never default a provenance value" and the project's standing "never silently overstate" ethical commitment.

### Integration Points
- `backend/weather_provider.py::fetch_weather` remains the sole integration point for C5/C7/C8 (station path, now transparently ASOS-supplemented per D-03) and for the new standalone C9/C10 historical-backfill use case (grid path, Open-Meteo per D-04).

</code_context>

<specifics>
## Specific Ideas

No UI/output-format requests — this is an internal adapter/provider-wiring phase with no user-facing surface. The concrete specifics for this phase are the decisions above: union-of-timestamps ASOS merging, automatic ASOS transparency, Open-Meteo on the grid path, and fail-loud error handling.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 7's scope. NSRDB solar integration (Phase 8) and fallback-provider semantics (WX-06, later) were not raised.

### Reviewed Todos (not folded)
None — `todo.match-phase` query returned 0 matches for Phase 7.

</deferred>

---

*Phase: 7-trivial-integration-providers*
*Context gathered: 2026-09-11*
