# Roadmap: Dynamic Line Rating (DLR) System

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-09-10)
- 🚧 **v1.1 Multi-Provider Weather** — Phases 6-10 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-09-10</summary>

- [x] Phase 1: Foundation & Data Contract (pre-GSD, C1-C3) — completed 2026-08-24
- [x] Phase 2: Core Consolidation (pre-GSD, C4-C6) — completed 2026-08-31
- [x] Phase 3: Safety & Spatial (3/3 plans) — completed 2026-09-03
- [x] Phase 4: Predictive (3/3 plans) — completed 2026-09-09
- [x] Phase 5: DS-F5 Wiring: Per-Location Static Ratings (1/1 plan) — completed 2026-09-10

Full phase details (goals, success criteria, plans, requirements): `.planning/milestones/v1.0-ROADMAP.md`

</details>

### 🚧 v1.1 Multi-Provider Weather (In Progress)

**Milestone Goal:** Resolve `PRD.md` §7.1 (the open weather-data-provider decision) by adopting
and implementing the per-variable provider composition from `docs/data-science/decisions/data_provider.md`'s
vetting log — TCEQ CAMS + ASOS for wind/temp/RH, NREL NSRDB for solar, Open-Meteo for historical
backfill, Synoptic retained as fallback — with `PIPELINE_SCHEMA` provenance tracking so
exports/plots can show which provider supplied which value, and the decision documents (`PRD.md`
§7.1, `data_provider.md`) ratified to match.

**Sequencing rationale:** `weather_provider.py::fetch_weather(stids, start, end, provider)` is
station-ID-based today; NSRDB and Open-Meteo are lat/lon-based grid providers. `data_provider.md`'s
closing section flags this as a real design consequence that needs deciding deliberately, not
discovering mid-milestone — so the signature/schema work (Phase 6) comes first, before any new
provider is wired in. The two trivial, no-auth integrations (ASOS, Open-Meteo) come next to prove
the new design cheaply; NSRDB follows once its free API key is registered (external checkpoint);
TCEQ — the highest-integration-effort candidate, with no REST API — comes after; Synoptic's
fallback wiring and the documentation ratification close the milestone, once all primaries exist
to fall back from.

- [x] **Phase 6: Multi-Provider Adapter Foundation** - Redesign `fetch_weather`'s signature and extend `PIPELINE_SCHEMA` with provenance columns so station-based and grid-based providers can be combined without breaking existing callers (completed 2026-09-11)
- [x] **Phase 7: Trivial-Integration Providers** - Wire ASOS 1-minute (wind/temp supplement) and Open-Meteo (historical backfill) behind the new adapter to prove the design cheaply (completed 2026-09-12)
- [x] **Phase 8: NSRDB Solar Integration** - Wire NREL NSRDB (PSM v4) as the primary solar-irradiance source, gated on a registered developer API key (completed 2026-09-14)
- [ ] **Phase 9: TCEQ CAMS Integration** - Wire TCEQ CAMS as the primary wind/temp/RH source for all four cities via HTML-report scraping
- [ ] **Phase 10: Fallback Wiring & Documentation Ratification** - Wire Synoptic as the fallback behind the same adapter and ratify the provider-composition decision in `PRD.md`/`data_provider.md`

## Phase Details

### Phase 6: Multi-Provider Adapter Foundation

**Goal**: Redesign the weather adapter so a station-based provider (TCEQ/ASOS/Synoptic) and a
lat/lon-based grid provider (NSRDB/Open-Meteo) can both be combined into one row per timestamp
against the existing `PIPELINE_SCHEMA` weather columns, with per-field provenance tracked — before
any new provider is wired in, per `data_provider.md`'s own flagged design consequence.
**Depends on**: Phase 5
**Requirements**: WX-05, WX-07
**Success Criteria** (what must be TRUE):

  1. `fetch_weather` accepts either a station-ID-based request or a lat/lon-based (grid) request and returns one unified DataFrame conforming to `PIPELINE_SCHEMA`'s existing weather columns, regardless of which kind of provider services the request.
  2. Existing callers (C5 thermal model, C7 safety monitor, C8 corridor discretization) run unchanged against the new signature — the currently-working Synoptic-only path requires no call-site changes.
  3. `PIPELINE_SCHEMA` version increments with new per-field provenance columns (e.g. `wind_source`, `solar_source`) added as `required: False`, with no existing key's name, unit, or range changed.
  4. A pre-existing v2-era row (no provenance data) still validates successfully against the extended schema.
  5. `.venv/bin/python -m pytest -q` reports 0 failed after the interface change.

**Plans**: 3/3 plans executed

Plans:
**Wave 1**

- [x] 06-01-PLAN.md — `PIPELINE_SCHEMA` v3 provenance columns, categorical validation, and end-to-end provenance on the station path (WX-07)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-02-PLAN.md — type-dispatched `location` parameter and internal station→city resolution (WX-05)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 06-03-PLAN.md — city-keyed merge, synthetic grid provider proof, and C4 spec/acknowledgements sync (WX-05)

### Phase 7: Trivial-Integration Providers

**Goal**: Prove the new adapter design cheaply by wiring the two no-auth, trivial-integration
providers — ASOS 1-minute (Iowa Environmental Mesonet) as a wind/temp supplement, and Open-Meteo as
a single-request historical backfill source — behind the Phase 6 interface.
**Depends on**: Phase 6
**Requirements**: WX-02, WX-04
**Success Criteria** (what must be TRUE):

  1. Given a target city, the system fetches higher-temporal-density wind/temp observations from ASOS 1-minute as a supplement to the primary wind/temp source, with units converted to `PIPELINE_SCHEMA` units (knots→m/s, °F→°C).
  2. Given a target city and a historical date range, one Open-Meteo request returns the full weather variable set (temp, wind speed/direction, solar, RH) for that window, standardized to `PIPELINE_SCHEMA` columns, for use as C9/C10 training data.
  3. Both providers' output rows carry the correct value in the Phase 6 provenance column(s).
  4. Neither integration requires a new secret or `.env` entry, matching each provider's no-auth access model confirmed live in `data_provider.md`.

**Plans**: 3/3 plans executed

Plans:
**Wave 1**

- [x] 07-01-PLAN.md — ASOS 1-minute supplement: `config.ASOS_STATIONS`, `asos_provider.fetch_asos_1min`, and the union-of-timestamps merge wired transparently into the station path (WX-02)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 07-02-PLAN.md — Open-Meteo Archive API as the grid path's first real provider: single-request full variable set, standardized to `PIPELINE_SCHEMA` (WX-04)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 07-03-PLAN.md — three-provider provenance proof, source-level no-new-secrets gate, C4 spec sync, and live-endpoint confirmation (WX-02, WX-04)

### Phase 8: NSRDB Solar Integration

**Goal**: NREL NSRDB (PSM v4) becomes the primary solar-irradiance source for all four cities.
**Depends on**: Phase 7
**Requirements**: WX-03
**Success Criteria** (what must be TRUE):

  1. Given a target city and time window, the system fetches solar irradiance (GHI) from NSRDB for that city's lat/lon coordinates (`config.CITY_COORDINATES`), for all four cities.
  2. The NREL developer API key is read only from `.env`/environment (never hardcoded or committed), matching the existing `SYNOPTIC_TOKEN` pattern.
  3. NSRDB-sourced solar rows are tagged with the correct provenance value and pass `PIPELINE_SCHEMA` range validation for `solar_radiation`.
  4. If the API key is absent or the NSRDB request fails, the adapter raises/surfaces a clear error rather than silently returning fabricated data (e.g. the legacy hardcoded 1000 W/m² constant).

**Plans**: 3/3 plans executed

Plans:
**Wave 1**

- [x] 08-01-PLAN.md — tracer: end-to-end NSRDB grid fetch (credential lookup, longitude-first WKT, GHI-only 60-minute request, CSV metadata-header parse, `_fetch_grid` dispatch, provenance) for one city and one calendar year (WX-03)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 08-02-PLAN.md — year-chunked window decomposition and reassembly, local 2018 coverage guard, dual-shape (JSON/CSV) error handling with credential redaction, GHI-units metadata check, solar-only provenance through the merge (WX-03)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 08-03-PLAN.md — credential-source gate, C4 spec / README / ACKNOWLEDGEMENTS sync, and the two blocking human checkpoints: register the key, then confirm a real NSRDB pull (WX-03)

**Checkpoint**: this phase is gated on a free NREL developer API key being registered — noted as
"being registered for this milestone" in PROJECT.md, and confirmed still unissued at Phase 8
context-gathering (08-CONTEXT.md D-01). Plans 08-01 and 08-02 are fully executable without it: every
automated test mocks the HTTP call. Plan 08-03's Task 2 (`checkpoint:human-action`) registers the key
and Task 3 (`checkpoint:human-verify`) makes the one live confirmation mocked tests cannot. If the key
is not issued, 08-03 halts at Task 2 and records the blocker; Phase 9 (TCEQ) does not depend on this
phase and may proceed independently if reordering is needed.

**Host note**: the developer portal was renamed — `developer.nrel.gov` no longer resolves and the live
host is `developer.nlr.gov` (National Laboratory of the Rockies), independently confirmed during Phase
8 research. Env-var naming deliberately keeps saying NREL to match WX-03's wording.

### Phase 9: TCEQ CAMS Integration

**Goal**: TCEQ CAMS becomes the primary real-station source for wind speed, wind direction, and
temperature (RH where available) across all four cities, despite TCEQ exposing no REST API.
**Depends on**: Phase 8
**Requirements**: WX-01
**Success Criteria** (what must be TRUE):

  1. Given any of the four target cities (Austin, Corpus Christi, Midland, El Paso), the system retrieves current wind speed, wind direction, and temperature from a real TCEQ CAMS site for that city by parsing `daily_summary.pl` (or an equivalent TCEQ report endpoint).
  2. Scraped values are converted into `PIPELINE_SCHEMA`-conformant units and pass range validation for `air_temp`, `wind_speed`, `wind_direction`.
  3. TCEQ-sourced rows are tagged with the correct provenance value in the wind/temp provenance column(s).
  4. If a targeted CAMS site's report is unreachable, malformed, or missing a needed field (e.g. no solar radiation at that site), the adapter fails clearly or falls through rather than silently fabricating a reading.

**Plans**: 2/3 plans executed

Plans:
**Wave 1**

- [x] 09-01-PLAN.md — tracer: end-to-end TCEQ station fetch (bs4 legitimacy gate, `config.TCEQ_STATIONS`, `daily_summary.pl` scrape with `select_date=user`, exact-label row extraction, fixed never-DST UTC offset, `Q` unit conversion, range check, `_fetch_station` dispatch, provenance) for one city and one calendar day (WX-01)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 09-02-PLAN.md — multi-day per-calendar-day decomposition with deterministic ordering and a self-imposed day cap, all four cities, null-RH sites with null humidity provenance, MST-vs-CST offset split, and the full fail-loud suite (WX-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 09-03-PLAN.md — no-credential source gate, C4 spec / ACKNOWLEDGEMENTS sync, and the blocking human checkpoint confirming a real four-site TCEQ pull (WX-01)

**Design note**: this is the highest-integration-effort provider in the milestone — HTML report
scraping, not a JSON/REST client — per `data_provider.md`'s own assessment. Plan for a scraper
module, not an API wrapper, and budget for it independently of Phase 7's trivial integrations.

**Checkpoint**: Plan 09-01 Task 1 is a blocking package-legitimacy checkpoint — `bs4` is this
codebase's first HTML-parser dependency and carries a `[SUS]` verdict (`unknown-downloads`,
`no-repository`) in 09-RESEARCH.md's audit. Contrary to that document's Pitfall 8, `requirements.txt`
does **not** already declare `bs4`; the pin is genuinely new, so the gate is a real one. Plan 09-03
Task 2 is a second blocking checkpoint: every automated test in this phase mocks `requests.get`, so a
live four-site fetch is the only evidence supporting Success Criterion 1 and the only way to close
09-RESEARCH.md assumptions A1 and A3 before its 2026-10-13 validity window expires.

### Phase 10: Fallback Wiring & Documentation Ratification

**Goal**: Synoptic is wired as the fallback provider behind the same adapter for any primary
provider failure, and the ratified per-variable provider composition decision is recorded in the
project's canonical docs.
**Depends on**: Phase 9
**Requirements**: WX-06, WX-08
**Success Criteria** (what must be TRUE):

  1. If TCEQ or NSRDB fails or returns no usable data for a request, the adapter automatically falls back to Synoptic for that request and still returns a usable row, rather than raising or returning an empty result.
  2. The fallback is observable in provenance — a fallback-sourced row's provenance column records "synoptic", not the failed primary.
  3. `docs/data-science/PRD.md` §7.1 and `docs/data-science/decisions/data_provider.md`'s status line are updated from "Pending"/"Open — vetting in progress" to record the ratified per-variable composition, matching what's actually implemented.
  4. `.venv/bin/python -m pytest -q` reports 0 failed with the full multi-provider adapter (all four providers + fallback) in place.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 6 → 7 → 8 → 9 → 10

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation & Data Contract | v1.0 | Pre-GSD (C1-C3) | Complete | 2026-08-24 |
| 2. Core Consolidation | v1.0 | Pre-GSD (C4-C6) | Complete | 2026-08-31 |
| 3. Safety & Spatial | v1.0 | 3/3 | Complete | 2026-09-03 |
| 4. Predictive | v1.0 | 3/3 | Complete | 2026-09-09 |
| 5. DS-F5 Wiring | v1.0 | 1/1 | Complete | 2026-09-10 |
| 6. Multi-Provider Adapter Foundation | v1.1 | 3/3 | Complete    | 2026-09-11 |
| 7. Trivial-Integration Providers | v1.1 | 3/3 | Complete    | 2026-09-12 |
| 8. NSRDB Solar Integration | v1.1 | 3/3 | In Progress|  |
| 9. TCEQ CAMS Integration | v1.1 | 2/3 | In Progress|  |
| 10. Fallback Wiring & Documentation Ratification | v1.1 | 0/TBD | Not started | - |
