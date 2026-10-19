# Phase 3: Safety & Spatial - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-03
**Phase:** 3-Safety & Spatial
**Areas discussed:** Corridor endpoint definition, Discretization density & geometry source, Weather data provider

---

## Corridor endpoint definition

| Option | Description | Selected |
|--------|-------------|----------|
| Pair cities into line segments | Real routes matching C8's acceptance criteria (a corridor is a route, not a point) | ✓ |
| Each city as its own degenerate corridor | Single-point "corridor", matches original I/O spec but doesn't exercise C8's per-point logic | |
| Synthetic radiating corridors | Fixed distance/direction from each city; avoids pairing but endpoint is arbitrary | |

**User's choice:** Pair cities into line segments.

**Follow-up: which pairing?**

| Option | Description | Selected |
|--------|-------------|----------|
| 2 pairs: Austin↔Corpus Christi, Midland↔El Paso | Natural geographic grouping, minimal scope | ✓ |
| Single chain through all 4 cities | One long corridor with all 4 as waypoints | |
| All 6 pairs (full mesh) | Every city connected to every other | |

**User's choice:** 2 pairs — Austin↔Corpus Christi, Midland↔El Paso.

**Follow-up: endpoint coordinates?**

| Option | Description | Selected |
|--------|-------------|----------|
| City-center lat/lon | Simple, matches station_explorer.py's existing precision level | ✓ |
| Nearest known substation/station coordinates | More realistic, requires new research per city | |

**User's choice:** City-center lat/lon.

**Notes:** None beyond the selections above.

---

## Discretization density & geometry source

| Option | Description | Selected |
|--------|-------------|----------|
| Synthetic straight-line interpolation | Matches C8 spec's stated "initially synthetic" fallback | ✓ |
| Wait for real GIS transmission-line data | More accurate, blocks phase on external data acquisition | |

**User's choice:** Synthetic straight-line interpolation.

**Follow-up: how many points per corridor?**

| Option | Description | Selected |
|--------|-------------|----------|
| 5 points | Endpoints + 3 interior — balances bottleneck detection vs. API load | ✓ |
| 3 points | Minimal API load, coarser detection | |
| 10 points | Finer resolution, ~2x fetch calls | |

**User's choice:** 5 points.

**Follow-up: weather fetch per point?**

| Option | Description | Selected |
|--------|-------------|----------|
| One weather fetch per point | Simplest, most accurate, matches C8's anticipated synchronous pattern | ✓ |
| Nearest-station sharing | Fewer API calls, coarser per-point accuracy | |

**User's choice:** One weather fetch per point.

**Notes:** None beyond the selections above.

---

## Weather data provider

**Initial question:** adopt `data_provider.md`'s full multi-provider composition (TCEQ CAMS + NSRDB + ASOS + Open-Meteo) now for Phase 3?

| Option | Description | Selected |
|--------|-------------|----------|
| Adopt full per-variable composition | Most complete/accurate; requires 3 new adapters + station→lat/lon mapping | ✓ (initial) |
| Minimal fix: Synoptic Open Access only | Zero code change, resolves account-tier failure, doesn't fix solar/4-city gap | |
| Two-provider subset: TCEQ + NSRDB | Covers required variables with fewer new adapters | |

**User's initial choice:** Adopt full per-variable composition.

**Follow-up questions asked (adapter signature, Synoptic Open Access application) before the pivot:**

| Question | User's answer |
|---|---|
| How should `fetch_weather`'s station-ID vs. lat/lon mismatch be handled? | Add a station→lat/lon mapping layer, keep existing signature |
| Should applying for Synoptic Open Access happen as part of this phase? | User noted they already have Synoptic Open Access credentials, and questioned whether the actual *depth* of access (not just having a key) was sufficient — asked Claude to verify live rather than assume |

**Live verification performed:** At the user's explicit request ("research into this to verify whether that is possible, otherwise we should reconsider using synoptic"), Claude wrote a one-off diagnostic script. The user ran it themselves via their own shell (`!` prefix), sourcing `SYNOPTIC_TOKEN` from their local `.env` file — the token was never pasted into the conversation, read by Claude directly, or committed to the repo. The script was deleted after use.

**First pass (single station per city, no `sensorvars=1`):** returned 0 solar-reporting stations for all 4 cities — later determined to be a script bug (the Synoptic metadata endpoint requires `sensorvars=1` to include `SENSOR_VARIABLES` in its response at all), not a real finding. Corrected before drawing any conclusion.

**Second pass (corrected script, `sensorvars=1`, `limit=100`, one live timeseries pull per city):** confirmed the token sees 424 networks nationally (not WTM-restricted) and found solar-tagged stations near all 4 cities, but a single live timeseries pull per city showed 3/4 succeeding and Midland's sampled station denied (`response_code=2`) — a real per-station access restriction, not just a metadata artifact. The user correctly pushed back that a 1-station-per-city sample wasn't sufficient evidence.

**Third pass (8 candidate stations tested per city, checking for actual non-null solar values):**

| City | Solar-tagged stations (50km) | Tested | Usable (real data) | Denied |
|---|---|---|---|---|
| Austin | 628 | 8 | 6 (75%) | 2 |
| Corpus Christi | 64 | 8 | 2 (25%) | 6 |
| Midland | 30 | 8 | 2 (25%) | 5 |
| El Paso | 94 | 8 | 3 (38%) | 4 |

**Revised decision, presented to the user given this evidence:**

| Option | Description | Selected |
|--------|-------------|----------|
| Broadened Synoptic with fallback-probe, defer other providers | Reuse existing fetch_weather path, no new adapters, per-location candidate probing | ✓ |
| Full per-variable composition anyway | Build TCEQ+NSRDB+ASOS+Open-Meteo despite Synoptic being viable | |
| Hybrid: broadened Synoptic now, composition for Phase 4 | Cheap fix now, schedule fuller composition later | |

**User's final choice:** Broadened Synoptic with fallback-probe, defer other providers — **this supersedes the initial "adopt full composition" answer above.**

**Follow-up: candidate probe count?**

| Option | Description | Selected |
|--------|-------------|----------|
| 5 candidates | Nearest 5 solar-equipped stations, probed in distance order | (superseded, see below) |
| 10 candidates | More exhaustive, up to 2x probe calls | (superseded, see below) |

**User's actual answer:** neither cleanly — user clarified a two-tier approach: probe nearest 5 first, then expand to the next 5 (10 total nearest) if all fail. Captured as D-08 in CONTEXT.md.

**Follow-up: terminal fallback after 10 exhausted?**

| Option | Description | Selected |
|--------|-------------|----------|
| Fall back to the static rating | Consistent with C7's fail-safe-by-default philosophy (DS-NF5) | ✓ |
| Keep expanding further | Try progressively more candidates | |

**User's choice:** Fall back to the static rating.

**Notes:** This area's live-verification detour was the most significant deviation from a standard discuss-phase flow this session — it directly overturned an assumption from the pre-existing `data_provider.md` vetting document (that Synoptic access was WTM-network-restricted with minimal solar coverage) and changed the phase's implementation approach from "build 3 new provider adapters" to "extend the existing Synoptic integration."

---

## Claude's Discretion

- Exact interior-point spacing algorithm for the 5-point geodesic interpolation.
- Implementation location for the station→lat/lon mapping layer (new module vs. extending `weather_provider.py`/`station_explorer.py`).
- Fallback-target semantics for G1/G2 vs. G3/G4 in `DLRSafetyMonitor` — surfaced as a gray area during analysis, not selected for discussion this session.
- Gate-2 test contradiction fix approach — same, not selected for discussion this session.

## Deferred Ideas

- Full multi-provider weather composition (TCEQ CAMS + NSRDB + ASOS + Open-Meteo) per `data_provider.md` — deferred to a later phase (likely Phase 4, given overlap with C9/C10 historical-backfill needs) pending evidence the broadened-Synoptic approach proves insufficient.
