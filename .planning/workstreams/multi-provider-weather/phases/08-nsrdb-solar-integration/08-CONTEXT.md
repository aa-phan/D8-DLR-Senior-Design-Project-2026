# Phase 8: NSRDB Solar Integration - Context

**Gathered:** 2026-09-12
**Status:** Ready for planning (execution gated on NREL API key — see Claude's Discretion / Deferred)

<domain>
## Phase Boundary

Wire NREL NSRDB (PSM v4, GOES CONUS) as a new `provider="nsrdb"` implementation on Phase 6's
grid path (`weather_provider._fetch_grid`), reachable via
`fetch_weather(location=(lat, lon), provider="nsrdb")` — the same dispatch shape Open-Meteo
(Phase 7) already uses. NSRDB becomes the primary solar-irradiance (GHI) source for all four
cities. No fallback/primary-selection logic is built here (that's WX-06 / Phase 10); this phase
only makes NSRDB a legal, working provider choice on the grid path. Requirements: WX-03.

</domain>

<decisions>
## Implementation Decisions

### API key availability
- **D-01:** The NREL developer API key (`developer.nrel.gov`) is **not yet registered** as of
  this discussion. This phase is planned now so it's ready, but the live-fetch execution tasks
  cannot run to completion until the key is issued. The plan must surface this explicitly as a
  documented checkpoint/precondition rather than assuming the key exists at execution time. —
  **Reversibility:** reversible — no code depends on the key existing at plan time; it only
  blocks running the live-network tasks.

### Field scope (solar-only, not full variable set)
- **D-02:** NSRDB's PSM v4 response includes 23 variables, including `wind_speed`,
  `wind_direction`, `air_temperature`, and `relative_humidity` alongside solar
  (`ghi`/`dni`/`dhi`). NREL's own documentation states the wind field ("2m MERRA-2 reanalysis")
  "should not be used for wind power calculations" — `data_provider.md`'s vetting already flagged
  this as untrustworthy for IEEE 738. The adapter populates **only `solar_radiation`** from the
  NSRDB response; `wind_speed`, `wind_direction`, `air_temp`, and `relative_humidity` stay null
  on NSRDB-sourced rows even though the raw response contains values for them, so nothing
  downstream (thermal model, anomaly detector, fail-safe gates) can accidentally consume the
  untrustworthy reanalysis wind data. — **Reversibility:** costly — once downstream code is
  written assuming NSRDB rows never carry wind/temp/humidity, later deciding to surface those
  fields means auditing every consumer for accidental reliance on the null.

### Integration library
- **D-03:** Fetch NSRDB data via **raw HTTP requests** (`requests`, matching the exact pattern
  already used for ASOS and Open-Meteo in Phase 7 — see `backend/asos_provider.py` and
  `backend/open_meteo_provider.py`), not `pvlib.iotools.get_psm3`. This keeps the provider
  modules consistent with each other and avoids adding `pvlib` as a new project dependency for
  what NREL's own REST API + CSV response already makes straightforward without it.

### Temporal resolution
- **D-04:** Request NSRDB data at **60-minute intervals** (of the {5, 15, 30, 60} options NSRDB
  supports), matching Open-Meteo's hourly cadence from Phase 7 and TCEQ's typical reporting
  interval. GHI does not vary enough minute-to-minute at ampacity-relevant timescales to justify
  the row-count cost of finer resolution for this phase's scope.

### NSRDB integration point
- **D-05:** NSRDB is wired as a new `provider="nsrdb"` branch inside `_fetch_grid`, parallel to
  the existing `provider="open_meteo"` branch from Phase 7 — same dispatch function, same
  `attach_provenance`/`attach_city` post-processing, same lat/lon-based signature. It is reachable
  only via the grid path; station-based calls (`_fetch_station`) never trigger it.

### Claude's Discretion
- Exact NSRDB request parameter names/values (`attributes` list limited to `ghi` plus whatever
  minimum set the API requires, `interval=60`, `utc=true`, date formatting) — confirm exact API
  contract during research, since no live pull has been confirmed yet per `data_provider.md`.
- Whether the API-key-absent case is a `ValueError` at call time (matching the existing
  `dlr_pipeline._token()` / `SYNOPTIC_TOKEN` precedent: "set env var or raise, naming the
  variable") or something else — default to that exact precedent unless research finds a reason
  not to.
- Historical-depth handling: NSRDB PSM v4 GOES CONUS only covers 2018–2025 — if a request falls
  outside that window, follow the fail-loud precedent (D-05 from Phase 7 CONTEXT.md): raise
  rather than silently returning nothing or a different product's data.
- Exact module name/location for the new provider (`backend/nsrdb_provider.py`, following the
  `asos_provider.py`/`open_meteo_provider.py` naming convention already established).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Provider decision & design consequence
- `docs/data-science/decisions/data_provider.md` §"NREL NSRDB — PSM v4 (GOES CONUS)" (lines
  86-107) — full vetting: free key required, 23-variable response, 60-min recommended cadence
  reasoning, 2018-2025 historical depth, rate limits (10,000 req/day, 1 req/sec, 20 concurrent),
  and the explicit "do not use for wind" verdict this phase's D-02 is built on.
- `docs/data-science/decisions/data_provider.md` §"Recommended Composition" (lines 211-224) — the
  design consequence Phase 6 built for and this phase (solar leg) partially fulfills.
- `docs/data-science/PRD.md` §7.1 — Open Decisions: Weather data provider (WX-08/Phase 10 marks
  this ratified; not this phase's job).

### Prior-phase precedent this phase follows
- `.planning/phases/07-trivial-integration-providers/07-CONTEXT.md` D-05 — fail-loud philosophy
  (raise rather than degrade silently) this phase's key-absent and out-of-range handling follow.
- `backend/asos_provider.py`, `backend/open_meteo_provider.py` — the exact raw-`requests`
  integration pattern D-03 says to replicate for NSRDB (no new library).
- `backend/dlr_pipeline.py::_token()` (lines 59+) — the `SYNOPTIC_TOKEN` env-var-or-raise pattern
  ROADMAP Success Criterion 2 says the NREL key must match.

### Adapter interface this phase wires into
- `backend/weather_provider.py::_fetch_grid` (line 449) — currently only implements
  `provider="open_meteo"`; this phase adds the `provider="nsrdb"` branch alongside it, in the
  same function, same `attach_provenance`/`attach_city` calls (lines 452-460 show the existing
  Open-Meteo branch's shape to mirror).
- `backend/config.py::CITY_COORDINATES` (line 146) — lat/lon input for all four cities, already
  used by Open-Meteo's grid-path call.
- `backend/units_def.py::KNOWN_PROVIDER_NAMES` — `"nsrdb"` is **already registered** (seeded in
  Phase 6, confirmed present) — no schema change needed for provenance to accept it.

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — WX-03 (this phase's sole requirement).
- `.planning/ROADMAP.md` §"Phase 8" — 4 concrete Success Criteria already locked (fetch GHI for
  all 4 cities, key read from `.env`/environment only, correct provenance + schema-range
  validation, fail-loud on missing key or failed request).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/config.py::CITY_COORDINATES` — lat/lon for all 4 cities, direct input to the NSRDB
  request, same as Open-Meteo's usage.
- `backend/weather_provider.py::attach_provenance` / `PROVENANCE_FIELD_MAP` — reusable as-is;
  already handles "set provenance only where the mapped column is present and non-null" — this
  is also the mechanism that naturally leaves NSRDB's wind/temp/humidity provenance null per D-02
  (those columns are simply never populated for NSRDB rows).
- `backend/units_def.py::KNOWN_PROVIDER_NAMES` — `"nsrdb"` already present; no change needed.

### Established Patterns
- Phase 7's `asos_provider.py`/`open_meteo_provider.py` module shape (fetch function returning a
  `PIPELINE_SCHEMA`-shaped frame, no side effects on import) is the template for the new
  `nsrdb_provider.py` module (D-03, D-05).
- `dlr_pipeline._token()`'s env-var-or-raise pattern is the template for NSRDB key handling
  (ROADMAP Success Criterion 2).

### Integration Points
- `backend/weather_provider.py::_fetch_grid` remains the sole integration point — same function
  Open-Meteo uses, new `provider="nsrdb"` branch alongside it.

</code_context>

<specifics>
## Specific Ideas

No UI/output-format requests — this is an internal adapter/provider-wiring phase with no
user-facing surface. The concrete specifics are the decisions above: solar-only field population
(D-02), raw-requests integration (D-03), 60-minute interval (D-04), and the key-not-yet-available
planning caveat (D-01).

</specifics>

<deferred>
## Deferred Ideas

- **Fallback/primary-selection logic** (if NSRDB fails, fall back to Synoptic or another provider)
  was raised implicitly by the ROADMAP checkpoint note but is explicitly WX-06 / Phase 10 scope —
  not this phase.
- **Live execution of the NSRDB fetch tasks** is blocked on the NREL API key registration
  completing (D-01). Planning proceeds now; running the plan's live-network verification tasks
  should wait for the key, or be executed with an explicit human checkpoint confirming the key is
  available.

### Reviewed Todos (not folded)
None — `todo.match-phase` was not run with any matches surfaced for Phase 8.

</deferred>

---

*Phase: 8-nsrdb-solar-integration*
*Context gathered: 2026-09-12*
