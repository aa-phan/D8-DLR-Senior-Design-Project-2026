# Requirements: Dynamic Line Rating (DLR) System — v1.1

**Defined:** 2026-09-10
**Core Value:** The end-to-end pipeline produces valid ampacity forecasts — weather ingestion through thermal model through export — and runs without manual intervention, while never letting an unreliable input silently overstate what a line can safely carry.

## v1.1 Requirements

Requirements for the Multi-Provider Weather milestone. Each maps to roadmap phases.

### Wind/Temp Ingestion

- [ ] **WX-01**: Given a target city, the system fetches wind speed, wind direction, temperature, and relative humidity from TCEQ CAMS as the primary real-station source, for all four cities (Austin, Corpus Christi, Midland, El Paso).
- [x] **WX-02**: Given a target city, the system can additionally fetch higher-temporal-density wind/temp observations from ASOS 1-minute data as a supplement to TCEQ.

### Solar Ingestion

- [ ] **WX-03**: Given a target city and time window, the system fetches solar irradiance (GHI) from NREL NSRDB (PSM v4) as the primary solar source, using a registered NREL developer API key stored the same way `SYNOPTIC_TOKEN` is (`.env`/environment only, never committed).

### Historical Backfill

- [ ] **WX-04**: Given a target city and a historical date range, the system fetches the full weather variable set (temp, wind speed/direction, solar, RH) from Open-Meteo in a single request, for use as C9/C10 training data.

### Provider Composition & Fallback

- [x] **WX-05**: `weather_provider.py::fetch_weather` combines TCEQ/ASOS (station-based) and NSRDB/Open-Meteo (grid/lat-lon-based) into one row per timestamp against the existing `PIPELINE_SCHEMA` weather columns, without requiring callers (C5, C7, C8) to change.
- [ ] **WX-06**: If a primary provider (TCEQ or NSRDB) fails or returns no usable data for a request, the system falls back to Synoptic behind the same adapter interface, rather than raising or returning an empty result.
- [x] **WX-07**: `PIPELINE_SCHEMA` is extended with per-field provenance columns (e.g. `wind_source`, `solar_source`) recording which provider supplied each field's value for a given row, following the additive-only versioning rule already established for schema changes (new keys, `required: False`, no changes to existing keys).

### Documentation

- [ ] **WX-08**: `docs/data-science/PRD.md` §7.1 and `docs/data-science/decisions/data_provider.md` are updated to record the per-variable provider composition as the ratified decision, resolving the previously "Pending" status.

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Weather Provider Hardening

- **WX-09**: Live per-site solar-availability check for TCEQ stations in Midland and El Paso (unverified in `data_provider.md`'s vetting pass — confirmed only for Austin and Corpus Christi).
- **WX-10**: A station→lat/lon standardization layer if a future provider needs to be added that doesn't fit the station-based/grid-based split this milestone establishes.

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Retiring Synoptic entirely | Kept as fallback — it's the one path proven end-to-end since Phase 2, and removing it now would remove the safety net WX-06 depends on |
| NOAA RTMA/URMA, MADIS, Meteostat, NWS/api.weather.gov | `data_provider.md` vetted these as supplement-only or dominated by better-fitting candidates (Open-Meteo, ASOS) already in scope — not worth the added integration cost this milestone |
| USCRN | Disqualified in `data_provider.md` — no wind direction data, a hard blocker for `thermal_model.py::perpendicular_wind()` |
| Wiring the forecasting/anomaly-detection production loop (`api`/`frontend` serving layer) | Carried over from v1.0 as a known gap, but owned by the Software sub-team — not this subsystem's scope; unrelated to the weather-provider decision |

## Traceability

Which phases cover which requirements. Phase numbers match `.planning/ROADMAP.md`.

| Requirement | Phase | Status |
|-------------|-------|--------|
| WX-01 | Phase 9 (TCEQ CAMS Integration) | Pending |
| WX-02 | Phase 7 (Trivial-Integration Providers) | Complete |
| WX-03 | Phase 8 (NSRDB Solar Integration) | Pending |
| WX-04 | Phase 7 (Trivial-Integration Providers) | Pending |
| WX-05 | Phase 6 (Multi-Provider Adapter Foundation) | Complete |
| WX-06 | Phase 10 (Fallback Wiring & Documentation Ratification) | Pending |
| WX-07 | Phase 6 (Multi-Provider Adapter Foundation) | Complete |
| WX-08 | Phase 10 (Fallback Wiring & Documentation Ratification) | Pending |

**Coverage:**

- v1.1 requirements: 8 total
- Mapped to phases: 8/8 ✓
- Unmapped: 0

---
*Requirements defined: 2026-09-10*
*Last updated: 2026-09-10 after v1.1 ROADMAP.md creation (Phases 6-10)*
