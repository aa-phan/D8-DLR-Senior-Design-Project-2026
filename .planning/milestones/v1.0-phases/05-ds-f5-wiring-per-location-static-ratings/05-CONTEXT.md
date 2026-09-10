# Phase 5: DS-F5 Wiring: Per-Location Static Ratings - Context

**Gathered:** 2026-09-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the confirmed DS-F5 gap from the v1.0 milestone audit: `backend/dlr_pipeline.py` and
`backend/ercot_dlr_merger.py` both hardcode `config.DEFAULT_STATIC_RATING` (900.0 A) regardless
of station/city, ignoring the per-city `config.STATIC_RATINGS` table that already exists (and is
already correctly consumed by `backend/corridor_discretization.py`). This phase wires per-location
static ratings into those two files only — it does not touch corridor discretization (already
correct) or add new station discovery/geo-matching infrastructure.

</domain>

<decisions>
## Implementation Decisions

### Location resolution API shape
- **D-01:** `run_pipeline()` and `plot_dlr_summary()` in `backend/dlr_pipeline.py` gain an explicit `city: str = None` parameter, replacing the existing `static_rating: float` parameter. — **Reversibility:** costly — removing `static_rating` changes both functions' public signatures; any external caller passing `static_rating=` positionally or by keyword breaks. No known external callers today (repo-internal only), but this is the one signature change in this phase with real blast radius.
- **D-02:** Rating resolution happens internally: `config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)`. `city=None` or any city not in `STATIC_RATINGS` silently falls back to `DEFAULT_STATIC_RATING` — no warning, no exception. This matches `DEFAULT_STATIC_RATING`'s existing documented purpose ("preserves current behavior for stations outside the four cities") and keeps every call site backward-compatible by default.
- **D-03:** Do NOT add coordinate-based auto-resolution (nearest-city-via-haversine) in this phase. `city` is always caller-supplied. This mirrors how `corridor_discretization.py` already keys ratings off explicit city names (`config.CORRIDOR_ENDPOINTS` → `config.STATIC_RATINGS[city]`), not coordinates.

### Merger signature & MW conversion
- **D-04:** `process_dlr_to_hourly()` in `backend/ercot_dlr_merger.py` gains the same `city: str = None` parameter and the same `STATIC_RATINGS.get(city, DEFAULT_STATIC_RATING)` resolution for the `static_capacity_mw` column. Existing test `test_hourly_resample_uses_min_not_mean` (in `backend/tests/ercot_dlr_merger_test.py`) calls `process_dlr_to_hourly(str(csv_path))` with no city arg — must keep passing unchanged (defaults to `DEFAULT_STATIC_RATING`, same numeric behavior as today).
- **D-05:** One city per `process_dlr_to_hourly()` call/CSV — no per-row city column or per-row rating lookup. A single DLR CSV represents one station/city's data (matches current pipeline output shape); corridor-level multi-point handling is out of scope here (already handled separately by `corridor_discretization.py`).

### Demo/entry-point wiring
- **D-06:** Fix `backend/dlr_pipeline.py`'s `__main__` block (currently the exact line the audit cites, `dlr_pipeline.py:454`) to call `run_pipeline(..., city="AUSTIN")` instead of `static_rating=config.DEFAULT_STATIC_RATING`, and update the corresponding `plot_dlr_summary(..., city="AUSTIN")` call at line ~461. This is correct because `__main__` already hardcodes `config.DEFAULT_STATION_SOURCE = "data/wtm_stations_austin.csv"` — the demo run is unambiguously Austin data today.
- **D-07:** `backend/ercot_dlr_merger.py` also has a `__main__` driver block (confirmed to exist: `TARGET_STATION = "AN489"`, an Austin-network station). Update its `process_dlr_to_hourly(DLR_FILE)` call to `process_dlr_to_hourly(DLR_FILE, city="AUSTIN")` so both audit-flagged files are demonstrably fixed end-to-end, not just made fixable.

### Multi-city scope for this phase
- **D-08:** The `city` param + `STATIC_RATINGS.get()` lookup is generic and already supports all 4 cities (Austin, Corpus Christi, Midland, El Paso) the moment a caller passes that city name — no additional per-city code needed. Only the two `__main__` demo call sites are hardcoded to Austin (because `DEFAULT_STATION_SOURCE` only has an Austin station CSV today).
- **D-09:** Do NOT build a config-driven loop over all 4 cities in `__main__`, and do NOT add per-city station discovery/CSVs for the flat `dlr_pipeline.py` path in this phase. That would require station-set-per-city input that doesn't exist yet for this code path (only `corridor_discretization.py` + `station_explorer.py` have per-city station discovery, and that's a separate, already-working system). Explicitly deferred — see Deferred Ideas.

### Claude's Discretion
- Exact parameter ordering/placement of the new `city` param in each function signature.
- Whether to add an inline comment at the `STATIC_RATINGS.get(city, DEFAULT_STATIC_RATING)` call sites referencing this phase/the audit — keep minimal, only if non-obvious.
- Test coverage approach (unit tests asserting `city="AUSTIN"` produces `static_capacity_mw` computed from 1900.0 A, not 900.0 A) — planner/executor to decide specifics.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Audit finding driving this phase
- `.planning/v1.0-MILESTONE-AUDIT.md` — the DS-F5 gap finding this phase closes; cites exact evidence: `backend/dlr_pipeline.py:454` and `backend/ercot_dlr_merger.py:44` both hardcode `config.DEFAULT_STATIC_RATING`.

### Config / data source of truth
- `backend/config.py` lines 41-51 — `STATIC_RATINGS` dict (per-city Amps) and `DEFAULT_STATIC_RATING` fallback; this module's own docstring explains it exists specifically to prevent the "two independent 900.0 A literals" problem this phase is now finishing the fix for.
- `backend/config.py` line 170 — `DEFAULT_STATION_SOURCE = "data/wtm_stations_austin.csv"`, why the demo entry points are Austin-specific.

### Existing correct reference implementation (pattern to follow)
- `backend/corridor_discretization.py` lines 248-264 (`corridor_geometry` function) — the ALREADY-CORRECT per-location wiring: looks up `config.STATIC_RATINGS[city_a]` / `config.STATIC_RATINGS[city_b]` by explicit city key. This phase's `dlr_pipeline.py`/`ercot_dlr_merger.py` changes should follow the same "explicit city key, not coordinates" pattern.

### Requirements
- `.planning/REQUIREMENTS.md` — DS-F5 row (currently marked "In Progress (partial)").

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `config.STATIC_RATINGS` / `config.DEFAULT_STATIC_RATING` — already exist, just need to be consulted at the two flagged call sites. No new config needed.

### Established Patterns
- `corridor_discretization.py`'s `city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor_name]` → `config.STATIC_RATINGS[city_a]` pattern is the precedent to mirror — explicit city-string keys, not coordinate-based resolution.

### Integration Points
- `backend/dlr_pipeline.py`: `run_pipeline()` (~line 182-234, uses `static_rating` at line 233-234) and `plot_dlr_summary()` (~line 324, uses `static_rating` at lines 348-352); `__main__` block (~lines 428-461).
- `backend/ercot_dlr_merger.py`: `process_dlr_to_hourly()` (~line 24-42, uses `config.DEFAULT_STATIC_RATING` at line 39); `__main__` block (~lines 119-146, `TARGET_STATION = "AN489"`).
- `backend/tests/ercot_dlr_merger_test.py`: `test_hourly_resample_uses_min_not_mean` calls `process_dlr_to_hourly(str(csv_path))` with no `city` arg — must remain passing with unchanged behavior (new param must default to `None` → `DEFAULT_STATIC_RATING`).
- No existing tests for `run_pipeline()` or `plot_dlr_summary()` — free to design new signature without breaking test coverage.

</code_context>

<specifics>
## Specific Ideas

No specific UI/UX-style requirements — this is a backend wiring fix. The concrete "I want it like X" reference is the existing `corridor_discretization.py` pattern (D-01–D-09 above all point back to it).

</specifics>

<deferred>
## Deferred Ideas

- **Config-driven multi-city loop / per-city station discovery for `dlr_pipeline.py`'s flat station-list path** — would require building a station-set-per-city input mechanism that doesn't exist for this code path today (unlike `corridor_discretization.py`, which already has this via `station_explorer.py`). Belongs in a future phase if/when the flat pipeline needs to run across multiple cities in one invocation, not just prove per-location wiring works.
- **Coordinate-based nearest-city auto-resolution** for stations that aren't explicitly the 4 known cities — deferred; explicit `city` param is sufficient for closing DS-F5 as audited.

</deferred>

---

*Phase: 5-DS-F5 Wiring: Per-Location Static Ratings*
*Context gathered: 2026-09-09*
