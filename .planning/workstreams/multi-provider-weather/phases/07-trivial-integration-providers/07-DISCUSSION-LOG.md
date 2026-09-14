# Phase 7: Trivial-Integration Providers - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-11
**Phase:** 7-trivial-integration-providers
**Areas discussed:** ASOS merge shape, ASOS trigger, Open-Meteo integration point, Failure handling, Sparse rows

---

## ASOS merge shape

| Option | Description | Selected |
|--------|-------------|----------|
| Union of timestamps | ASOS's extra between-Synoptic-sample timestamps become new rows — actually delivers the "higher-temporal-density" benefit for C9 feature engineering | ✓ |
| Same-timestamp value preference | Reuses Phase 6's `merge_observations` exactly as built (combine_first at existing timestamps only) — simpler, but wastes ASOS's density advantage | |

**User's choice:** Union of timestamps (recommended option).
**Notes:** None beyond the recommendation rationale.

---

## ASOS trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Automatic / transparent | Every station-based call silently also queries ASOS and merges it in — matches Phase 6's philosophy of C5/C7/C8 never needing to know which providers are involved | ✓ |
| Explicit opt-in | C5/C7/C8 keep calling fetch_weather exactly as today; ASOS only pulled when a caller deliberately asks for it | |

**User's choice:** Automatic / transparent (recommended option).
**Notes:** None.

---

## Open-Meteo integration point

| Option | Description | Selected |
|--------|-------------|----------|
| Wire as the grid provider | Implement Phase 6's `_fetch_grid(provider='open_meteo')` so it's reachable via `fetch_weather(location=(lat, lon), provider='open_meteo')` | ✓ |
| Dedicated standalone function | A separate function outside fetch_weather's dispatch, kept fully independent from the station/grid interface | |

**User's choice:** Wire as the grid provider (recommended option).
**Notes:** None.

---

## Failure handling

| Option | Description | Selected |
|--------|-------------|----------|
| Fail loud | Raise an exception — consistent with the project's "never silently overstate" philosophy | ✓ |
| Degrade gracefully | Log a warning and continue with whatever data the other provider(s) supplied | |

**User's choice:** Fail loud (recommended option).
**Notes:** None.

---

## Sparse rows

| Option | Description | Selected |
|--------|-------------|----------|
| Keep with nulls | PIPELINE_SCHEMA already allows null/absent values for fields a row's source didn't supply | ✓ |
| Drop ASOS-only timestamps lacking full coverage | Only add new rows where every PIPELINE_SCHEMA weather field has a value | |

**User's choice:** Keep with nulls (recommended option).
**Notes:** Direct follow-up to the "ASOS merge shape" decision — clarifies what happens to fields ASOS doesn't measure at ASOS-only timestamps.

---

## Claude's Discretion

- Exact ASOS station-ID mapping per city and where it lives in the codebase.
- Exact unit-conversion helper structure for ASOS (knots→m/s, °F→°C).
- Which Open-Meteo API variant (Archive vs. Historical Forecast) to request.
- Internal module/function layout for the ASOS union-of-timestamps merge logic.

## Deferred Ideas

None — discussion stayed within Phase 7's scope.
