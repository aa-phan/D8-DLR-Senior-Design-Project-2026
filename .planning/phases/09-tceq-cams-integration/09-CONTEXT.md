# Phase 9: TCEQ CAMS Integration - Context

**Gathered:** 2026-09-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire TCEQ CAMS as a new `provider="tceq"` implementation on Phase 6's station-based path
(`weather_provider._fetch_station`), reachable via `fetch_weather(stids, start, end,
provider="tceq")` — the same dispatch shape Synoptic already uses on that path. TCEQ becomes the
primary source for wind speed, wind direction, and temperature (RH where the site reports it)
across all four cities, via HTML-report scraping of `daily_summary.pl` (or an equivalent TCEQ
report endpoint) rather than a REST/JSON client. No fallback/primary-selection logic is built here
(that's WX-06 / Phase 10); this phase only makes TCEQ a legal, working provider choice on the
station path. Requirements: WX-01.

</domain>

<decisions>
## Implementation Decisions

### CAMS site selection
- **D-01:** For each of the four cities, the specific CAMS site ID is chosen during research by
  live-fetching that city's region listing (`monitors.pl?region=<n>`) and confirming which
  candidate site has the most complete wind/temp/RH data, then hard-coding that CAMS ID —
  the same evidence-based approach `data_provider.md` already used to confirm Corpus Christi
  CAMS 83. Applies to Austin (11 candidate sites in region 11) and the as-yet-unconfirmed
  Midland/El Paso sites alike. — **Reversibility:** reversible — a hard-coded site ID is a
  config-level change if a better site is found later.
- **D-02:** Site-selection criteria weigh wind/temp/RH completeness **only** — not proximity to
  the corridor endpoint, solar availability, or any other secondary factor. Matches how Corpus
  Christi CAMS 83 was already chosen.
- **D-03:** If no candidate site in a city has fully complete wind/temp/RH data, pick the
  most-complete site anyway; missing individual fields go null per-row rather than blocking the
  city's integration or requiring a checkpoint. Consistent with D-06 (null-when-absent) and the
  NSRDB/Open-Meteo null-if-absent precedent (Phase 7/8).

### RH availability handling
- **D-04:** TCEQ's confirmed field set (per `data_provider.md`) is wind speed/direction/temp —
  RH is not confirmed present at every site. When the chosen site's report has no RH field,
  `relative_humidity` is left **null** on TCEQ-sourced rows, not backfilled, dropped, or used to
  disqualify a site — same precedent as NSRDB's solar-only population (Phase 8 D-02) and
  Open-Meteo's null-if-absent handling (Phase 7 D-02).
- **D-05:** When RH is null for a TCEQ row, the `humidity_source` provenance column is left
  null/unset for that row — provenance is only set where the mapped field itself has a value,
  matching the existing `attach_provenance` behavior already used for NSRDB's null
  wind/temp/humidity rows. No new sentinel provenance value is introduced.

### Failure/fallback scope
- **D-06:** On an unreachable, malformed, or missing-required-field CAMS report,
  `fetch_weather(..., provider="tceq")` **raises** — it does not fall back to Synoptic or any
  other provider. Fallback-to-Synoptic wiring is explicitly WX-06/Phase 10 scope and stays out of
  this phase entirely; this phase only needs to fail loud, matching the fail-loud precedent
  already established for ASOS/Open-Meteo (Phase 7 D-05) and NSRDB (Phase 8). —
  **Reversibility:** reversible — Phase 10 wraps this call in fallback logic later without
  needing to change this phase's raise behavior.
- **D-07:** "Missing a needed field" that triggers a raise means **wind speed, wind direction, or
  temperature** are absent from the site's report — these are the fields confirmed present at
  every TCEQ site checked in `data_provider.md`, so their absence signals a broken or
  unexpectedly-shaped report. RH's absence is expected (per D-04) and is never itself a reason to
  raise.

### "Current" vs range semantics
- **D-08:** TCEQ implements the same station-based `fetch_weather(stids, start, end,
  provider="tceq")` signature as Synoptic/ASOS — "current" readings (ROADMAP Success Criterion 1)
  just means a caller passes a narrow/recent window; there is no separate single-reading code
  path. Keeps the adapter interface uniform across all station providers.
- **D-09:** Because `daily_summary.pl` reports one calendar day per request, a multi-day `(start,
  end)` range is served by fetching one report per calendar day in the range and concatenating
  the resulting hourly rows — not restricted to same-day requests only.

### Claude's Discretion
- Exact HTML parsing approach for `daily_summary.pl` (table structure, field-name matching,
  handling of the report's specific column layout) — confirm exact structure live during
  research, per the same "confirm live, don't just trust docs" approach `data_provider.md` used
  for Corpus Christi/Austin.
- Exact module name/location for the new provider (`backend/tceq_provider.py`, following the
  `asos_provider.py`/`open_meteo_provider.py`/`nsrdb_provider.py` naming convention already
  established).
- Unit conversions needed for TCEQ's reported units (confirm exact units live — e.g. wind speed
  may be mph, needing mph→m/s like ASOS's knots→m/s).
- Whether Midland/El Paso's CAMS site regions need additional discovery beyond the region
  numbers already suspected (region 7 for Midland/Odessa, region 6 for El Paso) — confirm live.
- Whether TAMISWeb (an alternate TCEQ interface, not yet checked per `data_provider.md`) is worth
  investigating if `daily_summary.pl` proves insufficient for any of the four cities — default to
  `daily_summary.pl` unless research finds a blocking reason not to.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider decision & design consequence
- `docs/data-science/decisions/data_provider.md` §"TCEQ CAMS (Continuous Ambient Monitoring
  Stations)" (lines 64-78) — full vetting: no-API HTML scraping via `daily_summary.pl`, hourly
  (not 5-min) resolution, confirmed-live evidence for Austin/Corpus Christi, solar
  non-universality, Midland/El Paso unconfirmed, 1998+ historical depth.
- `docs/data-science/decisions/data_provider.md` §"Recommended Composition" (lines 211-224) — the
  design consequence this phase (wind/temp/RH leg) fulfills.
- `docs/data-science/PRD.md` §7.1 — Open Decisions: Weather data provider (WX-08/Phase 10 marks
  this ratified; not this phase's job).

### Prior-phase precedent this phase follows
- `.planning/phases/07-trivial-integration-providers/07-CONTEXT.md` D-05 — fail-loud philosophy
  (raise rather than degrade silently) this phase's D-06/D-07 follow.
- `.planning/phases/08-nsrdb-solar-integration/08-CONTEXT.md` D-02 — the null-when-a-field-is-not-
  populated-by-this-provider precedent D-04/D-05 follow (NSRDB leaves wind/temp/humidity null;
  TCEQ leaves RH null where the site doesn't report it).
- `backend/asos_provider.py`, `backend/open_meteo_provider.py`, `backend/nsrdb_provider.py` — the
  provider-module naming/shape convention (fetch function returning a `PIPELINE_SCHEMA`-shaped
  frame) to replicate for TCEQ.

### Adapter interface this phase wires into
- `backend/weather_provider.py::_fetch_station` (line 441) — currently only implements
  `provider="synoptic"` (raises `ValueError` for anything else); this phase adds a
  `provider="tceq"` branch alongside it, in the same function.
- `backend/weather_provider.py::attach_provenance` / `PROVENANCE_FIELD_MAP` (line 66) — reusable
  as-is; already handles "set provenance only where the mapped column is present and non-null,"
  which is also the mechanism D-05 relies on for TCEQ's null RH rows.
- `backend/units_def.py::KNOWN_PROVIDER_NAMES` (line 329) — `"tceq"` is **already registered**
  (seeded in Phase 6) — no schema change needed for provenance to accept it.
- `backend/config.py::CITY_COORDINATES` / `CORRIDOR_ENDPOINTS` — the four target cities'
  identifying data; TCEQ's per-city CAMS site IDs (D-01) are a new lookup table alongside these,
  following the `config.ASOS_STATIONS`-per-city-station-code precedent from Phase 7.

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — WX-01 (this phase's sole requirement).
- `.planning/ROADMAP.md` §"Phase 9" — 4 concrete Success Criteria already locked (real-station
  fetch for all 4 cities, unit conversion + range validation, correct provenance, fail-clear
  on unreachable/malformed/missing-field reports).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/weather_provider.py::attach_provenance` / `PROVENANCE_FIELD_MAP` — directly reusable;
  already handles "set provenance only where the mapped column is present and non-null" (D-05's
  mechanism for null RH).
- `backend/units_def.py::KNOWN_PROVIDER_NAMES` — `"tceq"` already present; no change needed.
- `backend/config.py::ASOS_STATIONS` (Phase 7 precedent) — the per-city station-code lookup-table
  pattern to replicate for TCEQ's per-city CAMS site IDs (D-01).

### Established Patterns
- Phase 7/8's provider-module shape (`asos_provider.py`, `open_meteo_provider.py`,
  `nsrdb_provider.py` — fetch function returning a `PIPELINE_SCHEMA`-shaped frame, no side
  effects on import) is the template for the new `tceq_provider.py` module.
- Fail-loud philosophy (D-06/D-07) is a direct continuation of Phase 7 D-05 and Phase 8's
  key-absent/out-of-range handling — the project's standing "never silently overstate" ethical
  commitment (`PROJECT.md` Constraints).
- Null-when-not-populated-by-this-provider (D-04/D-05) is a direct continuation of NSRDB's
  solar-only field population (Phase 8 D-02).

### Integration Points
- `backend/weather_provider.py::_fetch_station` is the sole integration point — same function
  Synoptic/ASOS use, new `provider="tceq"` branch alongside them.
- `daily_summary.pl?cams=<id>` (`tceq.texas.gov/cgi-bin/compliance/monops/`) is the confirmed-live
  scrape target; `monitors.pl?region=<n>` is the confirmed-live region-listing endpoint used for
  D-01's site-selection research.

</code_context>

<specifics>
## Specific Ideas

No UI/output-format requests — this is an internal adapter/provider-wiring phase with no
user-facing surface. The concrete specifics are the decisions above: research-confirmed CAMS
site selection weighing completeness only (D-01/D-02/D-03), null-when-absent RH handling
(D-04/D-05), raise-only failure scope with no Phase-10 fallback wiring (D-06/D-07), and the
existing-signature range semantics with per-day report concatenation (D-08/D-09).

</specifics>

<deferred>
## Deferred Ideas

- **Fallback/primary-selection logic** (if TCEQ fails, fall back to Synoptic) was raised and
  explicitly locked out of this phase's scope (D-06) — it is WX-06 / Phase 10's job.
- **TAMISWeb** as an alternate TCEQ data interface was noted in `data_provider.md` as
  unchecked; left as Claude's Discretion to investigate only if `daily_summary.pl` proves
  insufficient — not a planned deliverable of this phase.
- **Live per-site solar-availability confirmation for Midland/El Paso** (WX-09, out of scope per
  REQUIREMENTS.md) — not raised again here; solar is not part of this phase's field scope
  (wind/temp/RH only).

### Reviewed Todos (not folded)
None — `todo.match-phase` query returned 0 matches for Phase 9.

</deferred>

---

*Phase: 9-tceq-cams-integration*
*Context gathered: 2026-09-13*
