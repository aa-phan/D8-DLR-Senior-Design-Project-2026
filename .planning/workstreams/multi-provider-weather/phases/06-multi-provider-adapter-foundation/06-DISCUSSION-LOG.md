# Phase 6: Multi-Provider Adapter Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-10
**Phase:** 6-multi-provider-adapter-foundation
**Areas discussed:** Request interface shape, Provenance column granularity, Row-keying / merge identity, Proving the design in Phase 6

---

## Request interface shape

| Option | Description | Selected |
|--------|-------------|----------|
| Single location param, type-dispatched | `fetch_weather(location, start, end, provider=...)` — `location` is either `list[str]` stids or a `(lat, lon)` tuple, dispatched on type | ✓ |
| Explicit location_type flag | `fetch_weather(location, start, end, location_type='station'\|'grid', provider=...)` — unambiguous but requires new kwarg at call sites | |
| Two separate functions, merged by caller | `fetch_weather_station()` / `fetch_weather_grid()` stay separate, merged by a new `fetch_weather_combined()` | |

**User's choice:** Single location param, type-dispatched (Recommended)
**Notes:** Follow-up question asked whether to keep the `stids` param name or rename it to `location`. User chose renaming to `location`, since existing callers pass the argument positionally (e.g. `corridor_discretization.py`'s `fetch_weather([stid], start, end)`) and are unaffected by an internal parameter rename.

---

## Provenance column granularity

| Option | Description | Selected |
|--------|-------------|----------|
| Separate: wind_source, temp_source, humidity_source, solar_source | One column per PIPELINE_SCHEMA weather field family | ✓ |
| Combined: wind_source, solar_source only | Matches data_provider.md's literal example wording; fewer columns | |

**User's choice:** Separate: wind_source, temp_source, humidity_source, solar_source (Recommended)
**Notes:** Follow-up question asked whether provenance values should distinguish fallback vs. primary (e.g. `"synoptic_fallback"` vs `"synoptic"`). User chose to design it now: values are just plain provider names, and fallback-vs-primary is inferable from which provider name is present — no separate flag needed. Phase 10 (WX-06) just adds new provider-name values, no schema change.

---

## Row-keying / merge identity

| Option | Description | Selected |
|--------|-------------|----------|
| City name | Join on `(city, datetime_utc)` — every request already resolves to one of the 4 cities via `config.CITY_COORDINATES` | ✓ |
| Lat/lon coordinate | Join on `(lat, lon, datetime_utc)` directly, station-based providers get a coordinate lookup | |
| Keep `stid` as key, grid rows get synthetic pseudo-stid | e.g. `"GRID_AUSTIN"` — lowest call-site churn but introduces a fake station ID | |

**User's choice:** City name (Recommended)
**Notes:** Follow-up flagged a tension: joining on city name conflicts with WX-05's "no call-site changes" requirement since `corridor_discretization.py` passes a bare stid list today, not a city. User resolved this by choosing to have `fetch_weather` derive the city internally (via `station_explorer.py`/`config.py` lookups) rather than pushing the city-passing requirement onto callers — city-keying stays an internal adapter detail, not a caller-visible contract change.

---

## Proving the design in Phase 6

| Option | Description | Selected |
|--------|-------------|----------|
| Synthetic/mock grid provider in tests only | Fake grid-based provider used only in Phase 6's test suite to exercise the merge path end-to-end; not wired into the real provider registry | ✓ |
| Signature/schema-only unit tests, no second provider at all | Test only that the existing Synoptic path still works under the new signature; defer proving the merge to Phase 7 | |

**User's choice:** Synthetic/mock grid provider in tests only (Recommended)
**Notes:** None.

---

## Claude's Discretion

- Exact internal helper function names/module layout for the station→city resolution logic.
- Whether the mock grid provider (D-07) is deleted once Phase 7 lands a real grid provider, or kept as a lightweight test fixture — no user preference expressed.

## Deferred Ideas

None — discussion stayed within Phase 6's scope. Fallback-provider semantics (WX-06, Phase 10) and real second-provider wiring (WX-01 through WX-04, Phases 7-9) were referenced only to inform Phase 6's design decisions, not pulled forward as new scope.
