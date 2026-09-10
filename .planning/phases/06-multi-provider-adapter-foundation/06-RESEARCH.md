# Phase 6: Multi-Provider Adapter Foundation - Research

**Researched:** 2026-09-10
**Domain:** Internal adapter/schema redesign (Python, pandas) — no new external providers, no new packages
**Confidence:** HIGH

## Summary

Phase 6 is a pure internal refactor: `backend/weather_provider.py::fetch_weather` currently has one
implementation (Synoptic, station-ID-based, delegating to `dlr_pipeline.fetch_timeseries`) and one
production caller path (`corridor_discretization.py::resolve_point_observation`, called once per
candidate station with a single-element `stids` list). This phase changes the signature to accept
either a `list[str]` of station IDs or a `(lat, lon)` tuple, keeps the Synoptic-only path working
unchanged (D-01/D-02), extends `PIPELINE_SCHEMA` with four new `required: False` provenance columns
(D-03), and proves the merge design with a test-only mock grid provider (D-07) — without wiring any
real second provider (that's Phases 7-9).

The riskiest under-specified piece the CONTEXT.md left open is D-06's "internal station→city
resolution": `resolve_point_observation` calls `fetch_weather([stid], start, end)` with **no
lat/lon**, so the city lookup must work from `stid` alone. Research below establishes the exact
mechanism: Synoptic's `/stations/timeseries` response — already fetched by every station-based call
— includes each station's `LATITUDE`/`LONGITUDE` fields (same as `/stations/metadata`), so the
adapter can resolve station→city with **zero additional network calls** by reading those fields out
of the response it already has and finding the nearest entry in `config.CITY_COORDINATES`. This
avoids either a second API round-trip or a brittle static CSV lookup (the two other options
considered, both worse).

The v2→v3 schema extension has a direct, already-tested precedent in this codebase: Phase 4's
v1→v2 additive extension (`backend/tests/units_def_test.py:410-475`) is the template to copy
mechanically for the v2→v3 provenance columns — same version-bump assertion shape, same
"pre-existing row still validates" test, same all-`required: False` assertion.

**Primary recommendation:** Implement `fetch_weather`'s type dispatch with a plain `isinstance`
check (`isinstance(location, tuple)` vs. list), resolve station→city by reading
`LATITUDE`/`LONGITUDE` already present in the Synoptic timeseries response (no new network call),
merge the station-row and grid-row DataFrames with `pandas.DataFrame.combine_first` keyed on
`(city, datetime_utc)`, and copy the Phase 4 `units_def_test.py` v1→v2 test pattern verbatim for the
v2→v3 assertions.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Request type dispatch (station-ID list vs. lat/lon tuple) | Backend adapter (`weather_provider.py`) | — | Sole integration point per CONTEXT.md `<code_context>`; callers never touch providers directly |
| Station ID → city resolution | Backend adapter (`weather_provider.py`, helper module) | Database/Storage (Synoptic API response already in hand) | D-06: must be internal, invisible to callers; must not require a second network call |
| Row merge / provenance assembly | Backend adapter (`weather_provider.py`) | — | "One row per timestamp" combination is the phase's core deliverable; belongs where both provider outputs converge |
| Schema definition & validation | Backend / Storage contract (`units_def.py`) | — | `PIPELINE_SCHEMA` is the shared contract every downstream consumer (C5, C7, C8, exports) validates against |
| Test-only mock grid provider | Test tier (`backend/tests/`) | — | D-07: explicitly test-only scaffolding, never registered in the real dispatch |

## User Constraints (from CONTEXT.md)

<user_constraints>

### Locked Decisions

- **D-01:** `fetch_weather` takes a single type-dispatched `location` param (renamed from `stids`): a `list[str]` of station IDs dispatches to the station-based path; a `(lat, lon)` tuple dispatches to the grid-based path. — **Reversibility:** costly.
- **D-02:** The rename from `stids` to `location` is invisible to existing callers because all 3 current call sites (`corridor_discretization.py`, tests) pass the argument positionally — no call-site changes required for WX-05.
- **D-03:** Four separate provenance columns are added to `PIPELINE_SCHEMA`: `wind_source`, `temp_source`, `humidity_source`, `solar_source` — one per weather-field family, not just the two literally named in `data_provider.md`. — **Reversibility:** one-way.
- **D-04:** Provenance columns store plain provider names as values (e.g. `"synoptic"`, `"tceq"`, `"nsrdb"`) rather than a separate primary/fallback flag or suffix.
- All four provenance columns are added as `required: False`, following the existing v1→v2 additive-only rule (`units_def.py:324-330`) — no existing key's name, unit, or range changes. `PIPELINE_SCHEMA_VERSION` increments accordingly.
- **D-05:** The join key for combining a station-based row and a grid-based row into "one row per timestamp" is **city name** (a key into `config.CITY_COORDINATES`/`STATIC_RATINGS`), not `stid` and not raw `(lat, lon)`.
- **D-06:** To preserve WX-05's "no call-site changes" requirement despite city-keying, `fetch_weather` resolves a station-based call's city **internally** (via `station_explorer.py`/`config.py` lookups) rather than requiring callers like `corridor_discretization.py` to pass a city explicitly. — **Reversibility:** costly.
- **D-07:** Add a synthetic/mock grid-based provider function used **only in Phase 6's own test suite** to exercise the full merge path end-to-end. This mock is not registered in `fetch_weather`'s real provider dispatch — test-only scaffolding.

### Claude's Discretion

- Exact internal helper function names/module layout for the station→city resolution logic (D-06) and the synthetic grid-provider test fixture (D-07).
- Whether the mock grid provider from D-07 is deleted once Phase 7 lands a real grid provider, or kept as a lightweight fixture for future adapter tests — no user preference expressed either way.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 6's scope. Fallback-provider semantics (WX-06) and real second-provider wiring (WX-01 through WX-04) were referenced only to inform Phase 6's design decisions (D-04, D-07); they remain Phase 7-10 work, not pulled forward.

</user_constraints>

## Phase Requirements

<phase_requirements>

| ID | Description | Research Support |
|----|-------------|------------------|
| WX-05 | `fetch_weather` combines TCEQ/ASOS (station-based) and NSRDB/Open-Meteo (grid-based) into one row per timestamp against `PIPELINE_SCHEMA`, without requiring callers (C5, C7, C8) to change. | `location` type-dispatch pattern (Pattern 1), station→city resolution via already-fetched Synoptic response fields (Pattern 2), `combine_first` merge pattern (Pattern 3), verified call-site signature (`corridor_discretization.py:439`). |
| WX-07 | `PIPELINE_SCHEMA` extended with per-field provenance columns, following the additive-only versioning rule. | Verified `PIPELINE_SCHEMA_VERSION`/rule text (`units_def.py:319-330`), Phase 4's v1→v2 precedent test pattern (`units_def_test.py:410-475`) as the mechanical template for v2→v3. |

</phase_requirements>

## Standard Stack

No new external packages are introduced by this phase. It is a refactor of existing, already-installed dependencies.

### Core (already installed — no action needed)
| Library | Version (verified in `.venv`) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 `[VERIFIED: .venv/bin/python -c "import pandas; print(pandas.__version__)"]` | DataFrame construction, indexing, merge/combine | Already the project's sole tabular data library; `PIPELINE_SCHEMA` and every provider function already produce/consume `pd.DataFrame` |
| Python | 3.12.13 `[VERIFIED: .venv/bin/python --version]` | Runtime | Project's existing interpreter; `list[str]` / tuple type hints used in this phase's signature are native syntax at this version |
| pytest | 9.0.3 `[VERIFIED: .venv/bin/python -m pytest --version]` | Test runner, gates Success Criteria #5 | Already configured via `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, collects `test_*.py`, `*_test.py`, `*_TestSuite.py`) |

### Supporting
No new supporting libraries needed. `math.radians`/`math.sin`/`math.asin`/`math.sqrt` (stdlib) already implement haversine distance in `station_explorer.py::haversine_km` — reuse this rather than adding a geo library.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `isinstance(location, tuple)` dispatch | `functools.singledispatch` | Only worth it if a 3rd dispatch shape is added later; for 2 shapes, `isinstance` is simpler and matches the codebase's existing plain-conditional style (no decorators used elsewhere in `weather_provider.py`) `[ASSUMED]` |
| `DataFrame.combine_first` for row merge | `DataFrame.merge(..., how="outer")` + manual `.fillna` per column | `combine_first` is purpose-built for "fill nulls from the other side, union both indexes" — exactly D-05's merge semantics — with less code than a manual outer-merge + per-column coalesce `[CITED: pandas.pydata.org/docs/reference/api/pandas.DataFrame.combine_first.html]` |

**Installation:** None required — no new packages.

## Package Legitimacy Audit

**Not applicable this phase.** No external packages are installed, upgraded, or newly imported.
`pandas`, `pytest`, and stdlib `math` are already present in `requirements.txt` / `.venv` and are
unaffected by this phase's changes. The Package Legitimacy Gate is skipped per its own trigger
condition ("whenever this phase installs external packages").

## Architecture Patterns

### System Architecture Diagram

```
                     corridor_discretization.py::resolve_point_observation
                                         │
                                         │  fetch_weather([stid], start, end)
                                         │  (existing call shape, WX-05 SC2: unchanged)
                                         ▼
                     ┌───────────────────────────────────────────────┐
                     │        weather_provider.py::fetch_weather      │
                     │        (single integration point, all callers) │
                     └───────────────────────────────────────────────┘
                                         │
                          isinstance(location, tuple)?
                    ┌────────────────────┴────────────────────┐
                    │ NO: list[str] of stids                   │ YES: (lat, lon)
                    ▼                                           ▼
         station-based path                             grid-based path
   dlr_pipeline.fetch_timeseries(stids,...)      [Phase 6: test-only mock only;
   → returns rows incl. LATITUDE/LONGITUDE        Phase 7+: real NSRDB/Open-Meteo]
   per station (already in Synoptic response)     → returns rows keyed by
                    │                                (lat, lon) → resolved city
                    ▼                                           │
      internal station→city resolution                          │
      (D-06: nearest CITY_COORDINATES entry                     │
       to the station's own lat/lon, read                       │
       from the response already fetched —                      │
       no second network call)                                  │
                    │                                           │
                    └────────────────┬──────────────────────────┘
                                      ▼
                    merge on (city, datetime_utc) key (D-05)
                    via DataFrame.combine_first — non-null
                    values from either side populate one row;
                    provenance columns (wind_source, temp_source,
                    humidity_source, solar_source) set to the
                    provider name(s) that supplied each field (D-04)
                                      │
                                      ▼
                    one unified DataFrame conforming to
                    PIPELINE_SCHEMA v3 (existing weather columns
                    unchanged + 4 new optional provenance columns)
                                      │
                                      ▼
              returned to caller unchanged (C5 thermal model,
              C7 safety monitor, C8 corridor discretization)
```

### Recommended Project Structure
```
backend/
├── weather_provider.py       # fetch_weather: type dispatch, merge, provenance assembly
├── units_def.py               # PIPELINE_SCHEMA v3 (this phase's 4 new columns)
├── station_explorer.py        # existing haversine_km, nearest_stations — reused, not duplicated
├── config.py                  # CITY_COORDINATES — reused as the city-resolution target set
└── tests/
    └── weather_provider_test.py   # new: dispatch tests, merge tests, D-07 mock grid provider,
                                     # schema v2→v3 precedent-pattern tests (or added to units_def_test.py
                                     # to match Phase 4's precedent location — Claude's Discretion)
```

### Pattern 1: Type-dispatched `location` parameter
**What:** `fetch_weather` inspects the runtime type/shape of its single `location` argument to choose station-based vs. grid-based handling, rather than a separate `mode` flag or two separate function names.
**When to use:** Exactly D-01's shape — a `list[str]` (station IDs) vs. a 2-tuple of floats (lat, lon). `isinstance(location, tuple)` is sufficient to distinguish the two, since callers never pass a station-ID list as a tuple today (`corridor_discretization.py:439` passes `[stid]`, a list).
**Example:**
```python
# Source: general Python idiom, not project-specific — isinstance(obj, (int, float))
# tuple-form is the standard way to check multiple types in one call.
# [CITED: bobbyhadz.com/blog/python-typeerror-isinstance-arg-2-must-be-type-type-of-types-or-union]
def fetch_weather(location, start, end, provider="synoptic"):
    if isinstance(location, tuple):
        lat, lon = location
        return _fetch_grid(lat, lon, start, end, provider)
    else:
        stids = location
        return _fetch_station(stids, start, end, provider)
```
Guard against ambiguity: validate `len(location) == 2 and all(isinstance(v, (int, float)) for v in location)` before unpacking, so a malformed 2-element list doesn't silently get misrouted. Per the project's fail-safe philosophy (CONTEXT.md `<code_context>`), an ambiguous shape should raise rather than guess.

### Pattern 2: Station→city resolution without a second network call
**What:** Synoptic's `/stations/timeseries` endpoint — the one `dlr_pipeline.fetch_timeseries` already calls — returns `LATITUDE` and `LONGITUDE` fields on every `STATION` object, identical to `/stations/metadata`. `[CITED: developers.synopticdata.com/mesonet/v2/stations/timeseries/]`
**When to use:** D-06's internal station→city resolution. Today, `dlr_pipeline.fetch_timeseries` (`backend/dlr_pipeline.py:145-158`) only extracts `STID` and `OBSERVATIONS` from each `STATION` object in the parsed JSON — `LATITUDE`/`LONGITUDE` are present in the response but currently discarded. Capturing them (either inside `fetch_timeseries` itself, or by having `weather_provider.py` re-parse the raw response before/alongside the call) and running them through `station_explorer.haversine_km` against each of `config.CITY_COORDINATES`'s 4 entries resolves the nearest city with zero additional API calls.
**Example:**
```python
# Illustrative sketch — exact call shape / module boundary is Claude's Discretion.
# CITY_COORDINATES keys/values verified: config.py:146-151 (AUSTIN, CORPUS_CHRISTI,
# MIDLAND, EL_PASO — see below for verbatim values).
def _resolve_city(station_lat: float, station_lon: float) -> str:
    return min(
        config.CITY_COORDINATES,
        key=lambda city: station_explorer.haversine_km(
            station_lat, station_lon, *config.CITY_COORDINATES[city]
        ),
    )
```
**Fallback if this route proves impractical during implementation:** call `station_explorer.get_all_stations(token)` once and filter by `stid` — this DOES cost a second network call per resolution unless cached, and requires a `SYNOPTIC_TOKEN` even when `weather_provider.py`'s own module-level import contract states "importing this module has no side effects" (`weather_provider.py:20-23`) — a token is only required at call time today, and this fallback would keep that true, just at a higher per-call cost. Treat Pattern 2's zero-network-call route as the target; this fallback is the documented Plan B if `fetch_timeseries`'s response shape turns out not to include lat/lon in practice (verify by inspecting one real response during Task 1, not by trusting docs alone — `data_provider.md`'s own convention is to distinguish "confirmed live" from "per documentation, unverified").

### Pattern 3: Row merge via `combine_first`
**What:** `pandas.DataFrame.combine_first(other)` fills NaN values in the calling frame with non-null values from `other`, unioning both frames' indexes. `[CITED: pandas.pydata.org/docs/reference/api/pandas.DataFrame.combine_first.html]`
**When to use:** Combining a station-row DataFrame and a grid-row DataFrame that share a `(city, datetime_utc)` index but populate different weather columns (e.g. station has wind/temp/humidity, grid has solar) into one row per timestamp (D-05).
**Example:**
```python
# Source: pandas official docs pattern, applied to this phase's D-05 key.
station_df = station_df.set_index(["city", "datetime_utc"])
grid_df = grid_df.set_index(["city", "datetime_utc"])
combined = station_df.combine_first(grid_df)
```
Note: `combine_first` fills nulls column-by-column, not row-by-row wholesale — if both frames provide `wind_speed` for the same key, the calling frame's (station's) non-null value wins, which matches D-04's "primary" precedent from `data_provider.md`'s Recommended Composition (station-based wind/temp as primary, grid-based solar as the piece station data lacks).

### Anti-Patterns to Avoid
- **Requiring callers to pass a city explicitly:** Directly contradicts D-06 and breaks WX-05 Success Criteria #2 (`corridor_discretization.py`'s 3 call sites must keep working unchanged).
- **Adding a second network call to resolve station→city on every `fetch_weather` invocation:** Works, but is the fallback (Pattern 2), not the target — every one of `resolve_point_observation`'s up-to-10-candidates-per-point probe calls (`corridor_discretization.py:370-373`, `MAX_PROBE_CANDIDATES`) would double its request volume against a provider whose spec already documents no rate-limit handling.
- **Changing an existing `PIPELINE_SCHEMA` key's name, unit, or range to accommodate provenance:** Violates the additive-only rule (`units_def.py:319-330`) and directly fails WX-05 Success Criteria #3/#4.
- **Storing a primary/fallback boolean or suffixed column instead of a plain provider name:** Explicitly rejected by D-04 — the four provenance columns should hold `"synoptic"`, `"tceq"`, `"nsrdb"`, etc., not `wind_is_fallback`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Great-circle distance between a station and a city center | A new distance formula | `station_explorer.haversine_km` (already exists, already tested via `nearest_stations`) | Duplicate haversine implementations risk silently drifting apart in precision/sign conventions; one already lives in this codebase |
| Filling nulls from one partially-populated frame with another's values | Manual `for col in ...: df[col] = df[col].fillna(other[col])` loop | `pandas.DataFrame.combine_first` | Built-in, index-aware, handles column-set mismatches between the two frames automatically |
| Multi-type argument dispatch | A `mode: str` parameter with `"station"`/`"grid"` string literals | `isinstance` check on the `location` argument's shape (D-01 locked this) | D-01 is a locked decision — do not introduce a second dispatch mechanism alongside it |

**Key insight:** Every piece of infrastructure this phase needs (distance calc, city table, schema
validator, test harness pattern) already exists in this codebase from prior phases. The work is
composition and one net-new lookup helper (station→city), not new infrastructure.

## Common Pitfalls

### Pitfall 1: Assuming `fetch_timeseries`'s parsed response includes lat/lon today
**What goes wrong:** `dlr_pipeline.fetch_timeseries` (`backend/dlr_pipeline.py:145-158`) currently only reads `station["STID"]` and `station.get("OBSERVATIONS", {})` from each `STATION` object — even though the raw Synoptic response includes `LATITUDE`/`LONGITUDE` per station, the current parsing code discards them.
**Why it happens:** The function was written before city-keying was a requirement; it only needed `stid` and the observation series.
**How to avoid:** Extend the parsing (either inside `fetch_timeseries` or in a `weather_provider.py`-level wrapper that inspects the same raw response) to also capture `LATITUDE`/`LONGITUDE`, then feed them to the city-resolution helper. Confirm with one real API call during implementation that these fields are actually present in this account's response (per `data_provider.md`'s own "confirmed live" vs. "per documentation, unverified" distinction) — treat the docs-cited field names as `[CITED]`, not yet `[VERIFIED]` for this specific token/account tier.
**Warning signs:** A `KeyError` or `None` where `LATITUDE`/`LONGITUDE` was expected in the parsed row; falling back silently to a wrong/default city would be a fail-safe violation (CONTEXT.md's standing ethical commitment) — raise or flag instead.

### Pitfall 2: City-key case mismatch
**What goes wrong:** `config.CITY_COORDINATES` and `config.STATIC_RATINGS` use UPPERCASE, underscore-separated keys — `"AUSTIN"`, `"CORPUS_CHRISTI"`, `"MIDLAND"`, `"EL_PASO"` `[VERIFIED: backend/config.py:146-151, quoted below]`. A city-resolution helper that returns a differently-cased or -formatted string (e.g. `"Corpus Christi"`) will merge-key-mismatch against grid-provider rows keyed the "correct" way, silently producing two separate rows per timestamp instead of one.

  Verbatim (`backend/config.py:146-151`):
  ```
  CITY_COORDINATES: dict[str, tuple[float, float]] = {
      "AUSTIN": (30.2711, -97.7437),
      "CORPUS_CHRISTI": (27.7635, -97.4033),
      "MIDLAND": (31.9974, -102.0779),
      "EL_PASO": (31.7601, -106.4870),
  }
  ```
**Why it happens:** Easy to introduce a second, differently-formatted city label when writing new merge/resolution code without re-checking the canonical dict's exact key casing.
**How to avoid:** Always resolve city as one of the literal keys of `config.CITY_COORDINATES` (e.g. return the dict key itself from the `min(...)` lookup in Pattern 2, never a reformatted string), and use that same key on both the station-path and grid-path DataFrames before merging.
**Warning signs:** A merge that produces more output rows than input timestamps; a provenance column full of correct values but two "duplicate" rows per timestamp that never combined.

### Pitfall 3: Provenance columns violating the additive-only rule
**What goes wrong:** Adding a required or defaulted-non-`None` provenance column, or reusing an existing schema key's name for a provenance value.
**Why it happens:** Easy to reach for `"required": True` by habit, or to think "well every row *should* have a source, so why not required" — but Success Criteria #4 (a pre-existing v2-era row with no provenance data must still validate) directly falsifies that instinct.

  Verbatim additive-only rule comment (`backend/units_def.py:324-330`):
  ```
  # PIPELINE_SCHEMA_VERSION: version 1 is the Phase 1-3 baseline (the ten
  # columns below, unchanged). Version 2 adds five Phase 4 (C9/C10) columns.
  # The rule this version exists to enforce: keys are only ever ADDED, always
  # with "required": False, and no existing key's name, unit or range is ever
  # changed. Downstream consumers that only know v1 keep working unmodified
  # against a v2-produced row — see RESEARCH.md Pattern 1, ROADMAP SC2.
  PIPELINE_SCHEMA_VERSION: int = 2
  ```
**How to avoid:** Follow the exact test pattern already proven for v1→v2 (see Validation Architecture below) — a frozen `_V2_SCHEMA_SNAPSHOT` dict, a version-bump assertion, an all-`required: False` assertion over the new keys, and a "pre-existing row still validates" test using only v1/v2-era fields.
**Warning signs:** `test_pre_phase4_row_still_validates`-equivalent test failing after the v3 change; a `MISSING required column` `UnitError` raised for a provenance column on an old row.

### Pitfall 4: Provenance value type not covered by `validate_pipeline_row`'s numeric assumptions
**What goes wrong:** `validate_pipeline_row` (`backend/units_def.py:413-461`) computes `float(np.mean(value))` and range-checks every present column against `spec["range"]` — but provenance columns hold strings (`"synoptic"`, `"tceq"`), not numbers. Adding `wind_source` etc. to `PIPELINE_SCHEMA` with a numeric `"range"` tuple the way every existing column has would either crash (`float()` on a string) or require the schema entry's shape to change for these 4 keys specifically.
**Why it happens:** The Phase 4 precedent (`forecast_horizon_min` etc.) added only numeric columns — this phase is the first to add string-valued schema columns, so there's no exact precedent for the `range` field's meaning on a categorical column.
**How to avoid:** Design a schema shape that works for `validate_pipeline_row`'s existing loop — either (a) special-case string-typed columns in `validate_pipeline_row` to skip/replace the numeric range check with an allowed-provider-name-set check, or (b) give the 4 provenance columns a `range` entry the current code can tolerate ("range" could be an enumerated set of allowed provider-name strings if the validator is extended to check `value in spec["range"]` when `spec.get("unit") == "categorical"` or similar). **This is a genuine open design point for the planner** — flagged below in Open Questions, not resolved here, since CONTEXT.md's `<decisions>` didn't specify the exact schema-entry shape for a non-numeric column and it directly affects whether Success Criteria #4/#5 pass.
**Warning signs:** `TypeError` or `UnitError` from `float(np.mean("synoptic"))` inside `validate_pipeline_row` the first time a provenance-bearing row is validated.

## Code Examples

### Existing `fetch_weather` signature being replaced (verbatim)
`[VERIFIED: backend/weather_provider.py:31-63]`
```python
def fetch_weather(
    stids: list[str],
    start: str,
    end: str,
    provider: str = "synoptic",
) -> pd.DataFrame:
    ...
    if provider == "synoptic":
        return dlr_pipeline.fetch_timeseries(stids, start, end)

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' is "
        "currently implemented."
    )
```

### The one production call site that must keep working unchanged
`[VERIFIED: backend/corridor_discretization.py:438-439]`
```python
try:
    frame = fetch_weather([stid], start, end)
except Exception as exc:
    ...
```
This passes `[stid]` positionally with no `provider=` kwarg — confirming D-02's claim that a rename
from `stids` to `location` is invisible here (positional call, no keyword usage of the old name).

### Phase 4's v1→v2 additive-schema test pattern (the template to copy for v2→v3)
`[VERIFIED: backend/tests/units_def_test.py:422-475]`
```python
_V1_SCHEMA_SNAPSHOT = {
    "air_temp": {"unit": "degC", "range": (-20.0, 60.0), "required": True},
    "wind_speed": {"unit": "m/s", "range": (0.0, 50.0), "required": True},
    "wind_direction": {"unit": "deg", "range": (0.0, 360.0), "required": True},
    "wind_perp_ms": {"unit": "m/s", "range": (0.0, 50.0), "required": False},
    "solar_radiation": {"unit": "W/m²", "range": (0.0, 1400.0), "required": False},
    "relative_humidity": {"unit": "%", "range": (0.0, 100.0), "required": False},
    "dlr_amps": {"unit": "A", "range": (100.0, 4000.0), "required": False},
    "dlr_capacity_mw": {"unit": "MW", "range": (50.0, 2500.0), "required": False},
    "static_capacity_mw": {"unit": "MW", "range": (50.0, 2500.0), "required": False},
    "ercot_west_load_mw": {"unit": "MW", "range": (0.0, 30_000.0), "required": False},
}

def test_schema_version_bumped_and_v1_columns_are_byte_identical():
    assert _units_def_module.PIPELINE_SCHEMA_VERSION == 2
    for name, spec in _V1_SCHEMA_SNAPSHOT.items():
        assert _units_def_module.PIPELINE_SCHEMA[name] == spec

def test_v2_columns_are_all_optional():
    v2_keys = set(_units_def_module.PIPELINE_SCHEMA) - set(_V1_SCHEMA_SNAPSHOT)
    assert v2_keys == {
        "forecast_horizon_min", "forecast_amps", "forecast_ci_lower_amps",
        "forecast_ci_upper_amps", "anomaly_score",
    }
    for key in v2_keys:
        assert _units_def_module.PIPELINE_SCHEMA[key]["required"] is False

def test_pre_phase4_row_still_validates():
    row = {"air_temp": 25.0, "wind_speed": 5.0, "wind_direction": 180.0}
    errors = validate_pipeline_row(row, strict=False)
    assert errors == []
```
For Phase 6, the direct analogue is: freeze the current (v2) schema as `_V2_SCHEMA_SNAPSHOT`, assert
`PIPELINE_SCHEMA_VERSION == 3`, assert the new v3 keys are exactly `{"wind_source", "temp_source",
"humidity_source", "solar_source"}` and all `required is False`, and assert a v2-era row (no
provenance keys) still validates — this is the literal mechanism behind Success Criteria #4.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `fetch_weather(stids, start, end, provider="synoptic")` — station-ID-only, single implementation | `fetch_weather(location, start, end, provider="synoptic")` — type-dispatched, station or grid | This phase (Phase 6) | Enables Phase 7-9's NSRDB/Open-Meteo/TCEQ/ASOS integrations without another signature change |
| `PIPELINE_SCHEMA_VERSION = 2` (Phase 4, forecast/anomaly columns) | `PIPELINE_SCHEMA_VERSION = 3` (this phase, provenance columns) | This phase | Third additive-only version bump; downstream consumers (exports, plots) that only know v1/v2 keys keep working unmodified |

**Deprecated/outdated:** None — no prior pattern is removed, only extended (additive-only rule).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | An `isinstance(location, tuple)` check (vs. `functools.singledispatch` or a `mode` string) is the appropriate dispatch mechanism for exactly 2 shapes, matching the codebase's existing plain-conditional style. | Architecture Patterns, Pattern 1 | Low — this is a reversible implementation-detail choice within an already-locked D-01 signature; wrong choice costs a refactor of one function's internals, not a call-site change. |
| A2 | Synoptic's `/stations/timeseries` response for *this project's specific account/token* actually includes populated (non-null) `LATITUDE`/`LONGITUDE` fields per station, not just per the general docs. | Architecture Patterns Pattern 2; Common Pitfalls Pitfall 1 | Medium — if the fields are absent or null for this account tier, the zero-network-call resolution path fails and the phase must fall back to a second `get_all_stations` call (documented as Plan B in Pattern 2), adding latency/token-dependency to every station-based `fetch_weather` call. Must be confirmed live during Task 1, not assumed. |
| A3 | The provenance columns' `PIPELINE_SCHEMA` entry shape (specifically the `"range"` field's meaning for a string-valued column) can be resolved by either extending `validate_pipeline_row` to special-case categorical columns, or giving them a tolerable placeholder `range`/`unit` value — exact mechanism not specified by CONTEXT.md. | Common Pitfalls, Pitfall 4 | High if unresolved before implementation — directly risks Success Criteria #4/#5 (schema validates, tests pass) if `validate_pipeline_row`'s numeric-range logic crashes on a string value. Flagged explicitly as an Open Question below; planner should make this an early task with a checkpoint, not a late discovery. |

## Open Questions

1. **How should `validate_pipeline_row` handle the four new string-valued provenance columns?**
   - What we know: Every existing `PIPELINE_SCHEMA` entry has a numeric `"range": (lo, hi)` tuple, and `validate_pipeline_row` unconditionally does `float(np.mean(value))` then a numeric range check on any present column (`units_def.py:449-451`).
   - What's unclear: CONTEXT.md's D-03/D-04 lock the column names and value semantics (provider-name strings) but not how `PIPELINE_SCHEMA`'s per-column spec dict or `validate_pipeline_row`'s validation loop should represent/handle a non-numeric column — no prior schema column has needed this.
   - Recommendation: Plan should include an early task that decides and implements one of: (a) special-case string-typed schema entries in `validate_pipeline_row` (e.g. `spec.get("dtype") == "str"` → check `value in spec.get("allowed_values", KNOWN_PROVIDER_NAMES)` instead of a numeric range), or (b) skip range/type checking entirely for any column whose value is a `str` instance, falling through to a lighter presence-only check. Either resolves Pitfall 4; (a) is more consistent with the schema's existing self-documenting intent (explicit allowed values, catchable typos in provider names) and is the recommended default absent further user input.

2. **Where should the D-07 mock grid-provider fixture and the new dispatch/merge tests live — a new `weather_provider_test.py`, or appended to the existing `units_def_test.py` (which already carries the Phase 4 schema-precedent tests) or `corridor_discretization_test.py` (which already injects fake `fetch_weather` callables)?**
   - What we know: CONTEXT.md explicitly marks this "Claude's Discretion." `pytest.ini`'s `python_files = test_*.py *_test.py *_TestSuite.py` collects any of those name shapes equally.
   - What's unclear: No `weather_provider_test.py` exists yet — this would be the first dedicated test file for that module.
   - Recommendation: Create `backend/tests/weather_provider_test.py` as a new file (module has no existing test file to append to, and it's the module actually being redesigned) for dispatch/merge/mock-grid-provider tests; keep the v2→v3 schema precedent tests in `units_def_test.py` alongside the existing v1→v2 tests they mirror (same file, same convention, easiest side-by-side diff for a reviewer).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pandas | DataFrame construction/merge | ✓ `[VERIFIED]` | 2.3.3 | — |
| Python 3.12 | Runtime, `list[str]`/tuple type hints | ✓ `[VERIFIED]` | 3.12.13 | — |
| pytest | Success Criteria #5 gate | ✓ `[VERIFIED]` | 9.0.3 | — |
| `SYNOPTIC_TOKEN` env var | Live station-path calls (existing behavior, unaffected by this phase) | Not probed this session — phase does not require live network calls to plan or implement (only the test-only mock grid provider and unit tests are exercised) | — | Tests inject fake `fetch_weather`/mock providers; no live token needed for Phase 6's own test suite (matches `corridor_discretization_test.py`'s existing convention of never hitting the network in tests) |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `SYNOPTIC_TOKEN` — not needed for this phase's test suite; only needed if a task chooses to manually smoke-test the real station path end-to-end (optional, not required by any Success Criterion).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 `[VERIFIED: .venv/bin/python -m pytest --version]` |
| Config file | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) `[VERIFIED: pytest.ini:1-4]` |
| Quick run command | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py backend/tests/units_def_test.py -q` |
| Full suite command | `.venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WX-05 | `fetch_weather` dispatches on `location` shape (list vs. tuple) | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k dispatch -q` | ❌ Wave 0 |
| WX-05 | Station-based call resolves city internally, no call-site change | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k city_resolution -q` | ❌ Wave 0 |
| WX-05 | Station row + mock grid row merge into one row per timestamp with correct provenance | unit (D-07 mock) | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k merge -q` | ❌ Wave 0 |
| WX-05 | Existing `corridor_discretization.py` call sites still pass with new signature | regression | `.venv/bin/python -m pytest backend/tests/corridor_discretization_test.py -q` | ✅ (existing file, must stay green) |
| WX-07 | `PIPELINE_SCHEMA_VERSION` bumped, v2 columns byte-identical | unit | `.venv/bin/python -m pytest backend/tests/units_def_test.py -k schema_version -q` | ❌ Wave 0 (new test, existing file) |
| WX-07 | New v3 columns are exactly the 4 named, all `required: False` | unit | `.venv/bin/python -m pytest backend/tests/units_def_test.py -k v3_columns -q` | ❌ Wave 0 |
| WX-07 / SC4 | A pre-existing v2-era row (no provenance) still validates | unit | `.venv/bin/python -m pytest backend/tests/units_def_test.py -k pre_v3_row -q` | ❌ Wave 0 |
| SC5 | Full suite passes after the interface change | regression (gate) | `.venv/bin/python -m pytest -q` | ✅ (existing suite; must report 0 failed) |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest backend/tests/weather_provider_test.py backend/tests/units_def_test.py backend/tests/corridor_discretization_test.py -q`
- **Per wave merge:** `.venv/bin/python -m pytest -q`
- **Phase gate:** Full suite green before `/gsd-verify-work` (this is Success Criteria #5, verbatim).

### Wave 0 Gaps
- [ ] `backend/tests/weather_provider_test.py` — new file; covers WX-05's dispatch, city-resolution, and merge behaviors, plus the D-07 mock grid-provider fixture.
- [ ] New `test_*` functions appended to `backend/tests/units_def_test.py` — covers WX-07's schema version bump, v3-columns-optional, and pre-existing-row-still-validates assertions (mirrors `units_def_test.py:441-464` exactly, per the Code Examples section above).
- [ ] No new fixture/conftest infrastructure needed — `backend/tests/corridor_discretization_test.py`'s existing `fake_fetch(stids, start, end)` closures already demonstrate the injection pattern this phase's new tests should follow.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | No auth surface changes; `SYNOPTIC_TOKEN` handling is untouched by this phase |
| V3 Session Management | No | N/A — no session concept in this batch pipeline |
| V4 Access Control | No | Internal library function, no access-control boundary |
| V5 Input Validation | Yes | `location` argument shape must be validated before unpacking (Pattern 1's guard); malformed input should raise, not silently misroute or default (project's fail-safe philosophy) |
| V6 Cryptography | No | No new secrets or cryptographic material introduced |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed `location` argument (e.g. a 2-element list of strings misread as lat/lon) silently misrouted to the wrong dispatch path | Tampering (of internal contract, not external attacker) | Explicit type+length validation before unpacking (Pattern 1); raise `ValueError` on ambiguous shape rather than guessing, consistent with `fetch_weather`'s existing `ValueError` precedent for unknown `provider` values (`weather_provider.py:60-63`) |
| Provenance column silently overstating data quality (e.g. defaulting to `"synoptic"` when the actual source is unknown) | Information Disclosure / Repudiation (false provenance record) | Never default a provenance value — leave it `None`/absent (schema already allows `required: False`) rather than guessing a provider name, matching the project's standing "never silently overstate" commitment (CONTEXT.md `<code_context>`) |

## Sources

### Primary (HIGH confidence — verified this session via Read/Bash tools against the actual repo)
- `backend/weather_provider.py` — current `fetch_weather` implementation (full file read)
- `backend/units_def.py` — `PIPELINE_SCHEMA`, `PIPELINE_SCHEMA_VERSION`, `validate_pipeline_row` (full file read)
- `backend/config.py` — `CITY_COORDINATES`, `STATIC_RATINGS`, `CORRIDOR_ENDPOINTS` (lines 1-170 read)
- `backend/station_explorer.py` — `haversine_km`, `nearest_stations`, `get_all_stations` (full file read)
- `backend/corridor_discretization.py` — `resolve_point_observation`, `rate_corridor` call sites (lines 370-630 read)
- `backend/dlr_pipeline.py` — `fetch_timeseries` response parsing (lines 60-235 read)
- `backend/tests/units_def_test.py` — Phase 4 v1→v2 schema-extension test pattern (lines 405-475 read)
- `backend/tests/corridor_discretization_test.py` — existing `fetch_weather` injection/mocking conventions (grep + targeted reads)
- `pytest.ini` — test collection configuration (full file read)
- `.venv/bin/python` — verified installed versions of pandas, Python, pytest via direct invocation

### Secondary (MEDIUM confidence — WebSearch verified against official documentation)
- Synoptic Mesonet `/stations/timeseries` response fields (`LATITUDE`/`LONGITUDE` present on `STATION` objects) — `[CITED: developers.synopticdata.com/mesonet/v2/stations/timeseries/]`
- `pandas.DataFrame.combine_first` semantics — `[CITED: pandas.pydata.org/docs/reference/api/pandas.DataFrame.combine_first.html]`

### Tertiary (LOW confidence — WebSearch only, general Python idiom, not project-specific)
- `isinstance(obj, (type1, type2))` tuple-form multi-type-check idiom — `[CITED: bobbyhadz.com/blog/python-typeerror-isinstance-arg-2-must-be-type-type-of-types-or-union]` (general Python knowledge, low novelty, included for completeness rather than as a load-bearing claim)

## Project Constraints (from CLAUDE.md)

No project-level `./CLAUDE.md` or `./.claude/CLAUDE.md` exists in this repository (checked this
session; only a user-global `~/.claude/CLAUDE.md` exists, which is process guidance — see note
below — not a code convention). No project-specific skills directory (`.claude/skills/` or
`.agents/skills/`) exists either.

**Carried process constraint (user-global, not project CLAUDE.md, but binds this work per
project's own MEMORY.md):** ECE 464 requires updating `ACKNOWLEDGEMENTS.md` before any
significant AI-assisted commit — the planner should include this as a task/checkpoint before the
phase's final commit, consistent with `.planning/STATE.md`'s "Blockers/Concerns" entry on this
exact rule.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all versions verified live against `.venv`.
- Architecture: HIGH for locked decisions (all sourced from CONTEXT.md + verified code reads); MEDIUM for the station→city zero-network-call resolution mechanism (Pattern 2) pending a live confirmation task in Wave 0 (A2).
- Pitfalls: HIGH — Pitfalls 1-3 verified directly against source files; Pitfall 4 is a genuine open design question, flagged rather than guessed at.

**Research date:** 2026-09-10
**Valid until:** 30 days (stable internal refactor; no external API surface is changing during this phase, so it isn't fast-moving, but codebase drift from concurrent work is the main freshness risk)
