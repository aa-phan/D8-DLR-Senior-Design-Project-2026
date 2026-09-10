# Phase 5: DS-F5 Wiring: Per-Location Static Ratings - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-09
**Phase:** 5-DS-F5 Wiring: Per-Location Static Ratings
**Areas discussed:** Location resolution API shape, Merger signature & MW conversion, Demo/entry-point wiring, Multi-city scope for this phase

---

## Location resolution API shape

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit city param | Add `city: str` param; function resolves `STATIC_RATINGS.get(city, DEFAULT)` internally | ✓ |
| Auto-resolve from station coordinates | Nearest-city-via-haversine from station lat/lon | |
| Keep static_rating a plain float, caller resolves | No city concept added; caller passes resolved float | |

**User's choice:** Explicit city param

| Option | Description | Selected |
|--------|-------------|----------|
| city replaces static_rating | Removes static_rating float param entirely | ✓ |
| Keep both, city is optional override | static_rating stays, city wins if given | |

**User's choice:** city replaces static_rating

| Option | Description | Selected |
|--------|-------------|----------|
| Silent fallback to DEFAULT_STATIC_RATING | No exception, no warning | ✓ |
| Log a warning, then fallback | Same fallback, but logged | |
| Raise an error | No silent fallback | |

**User's choice:** Silent fallback to DEFAULT_STATIC_RATING

| Option | Description | Selected |
|--------|-------------|----------|
| Optional, defaults to None | Backward compatible | ✓ |
| Required, no default | Forces every call site to be explicit | |

**User's choice:** Optional, defaults to None

---

## Merger signature & MW conversion

| Option | Description | Selected |
|--------|-------------|----------|
| Add city: str = None param | Mirrors dlr_pipeline decision | ✓ |
| Derive city from CSV path/filename | Couples correctness to a filename convention | |

**User's choice:** Add city: str = None param

| Option | Description | Selected |
|--------|-------------|----------|
| One city per csv/call | Matches current pipeline output shape | ✓ |
| Per-row city (needs a city/stid column) | Bigger change, not needed today | |

**User's choice:** One city per csv/call

---

## Demo/entry-point wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, fix __main__ to pass city='AUSTIN' | Concrete end-to-end proof, closes audit's cited evidence | ✓ |
| No, leave __main__ unchanged | Audit-flagged line stays unfixed | |

**User's choice:** Yes, fix __main__ to pass city='AUSTIN'
**Notes:** Confirmed during discussion that `dlr_pipeline.py`'s `__main__` uses `config.DEFAULT_STATION_SOURCE` ("data/wtm_stations_austin.csv"), making the demo data unambiguously Austin.

| Option | Description | Selected |
|--------|-------------|----------|
| Check for a __main__ or driver call site and wire it if one exists | Keep the fix consistent across both flagged files | ✓ |
| Leave as library-only, no driver to update | Only if no such call site exists | |

**User's choice:** Check for a __main__ or driver call site and wire it if one exists
**Notes:** Confirmed `backend/ercot_dlr_merger.py` has a `__main__` block with `TARGET_STATION = "AN489"` (an Austin-network station) — will be wired to pass `city="AUSTIN"`.

---

## Multi-city scope for this phase

| Option | Description | Selected |
|--------|-------------|----------|
| API supports all 4 cities; demo proves 1 | Generic lookup works for any city; only demo call sites hardcoded to Austin | ✓ |
| Also wire a config-driven city loop over all 4 cities | Bigger scope, needs per-city station discovery that doesn't exist for this code path | |

**User's choice:** API supports all 4 cities; demo proves 1

---

## Claude's Discretion

- Exact parameter ordering/placement of the new `city` param in each function signature.
- Whether to add an inline comment at the `STATIC_RATINGS.get(city, DEFAULT_STATIC_RATING)` call sites.
- Test coverage approach for asserting per-city ratings are applied correctly.

## Deferred Ideas

- Config-driven multi-city loop / per-city station discovery for `dlr_pipeline.py`'s flat station-list path (future phase, if the flat pipeline needs to run across multiple cities in one invocation).
- Coordinate-based nearest-city auto-resolution for stations outside the 4 known cities.
