# Phase 6: Multi-Provider Adapter Foundation - Pattern Map

**Mapped:** 2026-09-10
**Files analyzed:** 4 (2 modified, 1 new test file, 1 test-file-extension)
**Analogs found:** 4 / 4 (all analogs are the files' own prior versions / sibling test files — this is a self-referential refactor phase, not a greenfield one)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|---------------|
| `backend/weather_provider.py` (modify `fetch_weather`) | service/adapter | request-response (type-dispatch + merge) | itself (current implementation) + `backend/station_explorer.py::nearest_stations` (city-resolution helper pattern) | exact (own prior version) / role-match (helper) |
| `backend/units_def.py` (extend `PIPELINE_SCHEMA`) | model/schema | CRUD (schema definition + validation) | itself, v1→v2 Phase-4 addition (lines 384-409) | exact (direct precedent, same file) |
| `backend/tests/weather_provider_test.py` (new) | test | request-response / event-driven (mock provider) | `backend/tests/corridor_discretization_test.py` (`fake_fetch` injection convention, lines 284-410) | role-match (closest test-injection convention in repo) |
| `backend/tests/units_def_test.py` (extend, append v2→v3 tests) | test | CRUD (schema validation) | itself, v1→v2 test block (lines 422-479) | exact (direct mechanical template) |

No files are being created outside the test suite — this phase modifies exactly 2 production files and touches 2 test files. No controller/component/route files are in scope (backend-only internal library, C4 spec, no HTTP surface added).

## Pattern Assignments

### `backend/weather_provider.py` (service/adapter, request-response)

**Analog:** its own current implementation (`backend/weather_provider.py:1-64`) — full file, ≤2000 lines, already read in one pass.

**Imports pattern** (lines 26-28):
```python
import pandas as pd

import dlr_pipeline
```
New imports needed for Phase 6: `import config` (for `CITY_COORDINATES`) and `import station_explorer` (for `haversine_km`), following the same bare top-level `import <module>` style (no relative-import syntax, no aliasing) used throughout `backend/`.

**Module-level docstring / side-effect contract** (lines 1-24): preserve verbatim intent — "Importing this module has no side effects (no file I/O, no network calls)." Any new helper (station→city resolution) must not perform I/O at import time; only inside `fetch_weather`'s call path, matching the existing contract this module already documents and that `corridor_discretization_test.py::test_module_importable_with_no_synoptic_token_and_no_network` enforces for the sibling module.

**Core dispatch pattern to replace** (lines 31-63, full function — this is what's being redesigned):
```python
def fetch_weather(
    stids: list[str],
    start: str,
    end: str,
    provider: str = "synoptic",
) -> pd.DataFrame:
    """
    ... (full docstring, Args/Returns/Raises shape to preserve) ...
    """
    if provider == "synoptic":
        return dlr_pipeline.fetch_timeseries(stids, start, end)

    raise ValueError(
        f"Unknown weather provider: {provider!r}. Only 'synoptic' is "
        "currently implemented."
    )
```
**Error handling pattern to preserve:** `raise ValueError(f"...")` on an unrecognized/ambiguous input, not a silent fallback — this is the exact precedent the new `location`-shape validation guard (Pattern 1 in RESEARCH.md) should follow: raise `ValueError` on ambiguous `location` shape, mirroring this file's own existing convention for unknown `provider` values (RESEARCH.md's Security Domain section explicitly calls this out as the precedent to match).

**Docstring convention to preserve** (Google-style Args/Returns/Raises, lines 37-56): keep this shape when documenting the new `location: list[str] | tuple[float, float]` parameter — update the "Args" description to explain the type-dispatch, keep "Raises: ValueError" for both the unknown-provider case and the new ambiguous-shape case.

**City-resolution helper pattern to borrow** (`backend/station_explorer.py:75-98`, `nearest_stations`):
```python
def nearest_stations(stations: pd.DataFrame, lat: float, lon: float, n: int = 5) -> pd.DataFrame:
    if stations.empty:
        return stations
    stations = stations.copy()
    stations["km_to_point"] = stations.apply(
        lambda r: haversine_km(r["lat"], r["lon"], lat, lon),
        axis=1,
    )
    return stations.sort_values(["km_to_point", "stid"]).head(n).reset_index(drop=True)
```
Use `station_explorer.haversine_km` (lines 17-23, already imported as a plain function, no class) directly — do not reimplement great-circle distance. The `min(config.CITY_COORDINATES, key=lambda city: haversine_km(...))` sketch in RESEARCH.md Pattern 2 is the concrete shape to implement; return the literal dict key (e.g. `"AUSTIN"`), never a reformatted string (Pitfall 2).

**haversine_km signature** (`backend/station_explorer.py:17`):
```python
def haversine_km(lat1, lon1, lat2, lon2):
```
Plain function, no type hints, positional args — match this style when calling it from `weather_provider.py`.

**CITY_COORDINATES verbatim source** (`backend/config.py:146-151`):
```python
CITY_COORDINATES: dict[str, tuple[float, float]] = {
    "AUSTIN": (30.2711, -97.7437),
    "CORPUS_CHRISTI": (27.7635, -97.4033),
    "MIDLAND": (31.9974, -102.0779),
    "EL_PASO": (31.7601, -106.4870),
}
```
Keys are UPPERCASE, underscore-separated — the city-resolution helper's return value MUST be one of these exact dict keys (Pitfall 2 in RESEARCH.md).

**Underlying station-fetch response shape to extend** (`backend/dlr_pipeline.py:145-158`, `fetch_timeseries`):
```python
for station in data.get("STATION", []):
    print("STID:", station.get("STID"))
    print("OBS keys:", list(station.get("OBSERVATIONS", {}).keys()))

frames = []
for station in data.get("STATION", []):
    stid = station["STID"]
    obs  = station.get("OBSERVATIONS", {})
    times = pd.to_datetime(obs.get("date_time", []), utc=True)
    row = {"stid": stid, "datetime_utc": times}
    for var in DLR_VARS:
        key = f"{var}_set_1"
        row[var] = obs.get(key, [None] * len(times))
    frames.append(pd.DataFrame(row))
...
df = pd.concat(frames, ignore_index=True)
df = df.set_index(["stid", "datetime_utc"]).sort_index()
```
This is where `LATITUDE`/`LONGITUDE` currently get discarded (Pitfall 1) — either extend this loop to also capture `station["LATITUDE"]`/`station["LONGITUDE"]` per row, or have `weather_provider.py` independently parse the same raw JSON response. Match this file's existing `.set_index([...]).sort_index()` convention when building the merge-ready DataFrame in `weather_provider.py`.

**Merge pattern (new, no in-repo precedent — apply RESEARCH.md Pattern 3 directly):**
```python
station_df = station_df.set_index(["city", "datetime_utc"])
grid_df = grid_df.set_index(["city", "datetime_utc"])
combined = station_df.combine_first(grid_df)
```
Follow the existing `.set_index([...])` idiom already used in `dlr_pipeline.fetch_timeseries` (above) for consistency of index-shape conventions across the two adapter-layer modules.

---

### `backend/units_def.py` (model/schema, CRUD)

**Analog:** itself, the v1→v2 Phase-4 addition block (`backend/units_def.py:319-410`), already fully in context above.

**Version-bump comment pattern** (lines 324-330):
```python
# PIPELINE_SCHEMA_VERSION: version 1 is the Phase 1-3 baseline (the ten
# columns below, unchanged). Version 2 adds five Phase 4 (C9/C10) columns.
# The rule this version exists to enforce: keys are only ever ADDED, always
# with "required": False, and no existing key's name, unit or range is ever
# changed. Downstream consumers that only know v1 keep working unmodified
# against a v2-produced row — see RESEARCH.md Pattern 1, ROADMAP SC2.
PIPELINE_SCHEMA_VERSION: int = 2
```
Copy this comment shape, updating to describe v2→v3: "version 3 adds four Phase 6 (C4 multi-provider) provenance columns," and bump `PIPELINE_SCHEMA_VERSION: int = 3`.

**Additive column-block pattern** (lines 384-409, the v2 additions inside `PIPELINE_SCHEMA`):
```python
    # --- v2 additions (Phase 4 / C9 forecasting, C10 anomaly detection) ---
    "forecast_horizon_min": {
        "unit":      "min",
        "range":     (0.0, 1440.0),
        "required":  False,
    },
    ...
```
Add a parallel `# --- v3 additions (Phase 6 / C4 provider provenance) ---` comment block with the four new keys (`wind_source`, `temp_source`, `humidity_source`, `solar_source`), each `"required": False`. **Open design point (RESEARCH.md Pitfall 4/Open Question 1, unresolved by CONTEXT.md):** every existing entry's `"range"` is a numeric `(lo, hi)` tuple consumed by `validate_pipeline_row`'s `float(np.mean(value))` numeric check (lines 449-451) — a string-valued provenance column will crash that path unless `validate_pipeline_row` is extended to special-case string/categorical columns first. Plan must include this as an explicit task before adding the four schema entries.

**Validator function to extend** (`backend/units_def.py:413-461`, `validate_pipeline_row`):
```python
for col, spec in PIPELINE_SCHEMA.items():
    value = row.get(col)
    if value is None:
        if spec["required"]:
            msg = f"MISSING required column '{col}' (expected unit: {spec['unit']})"
            if strict: raise UnitError(msg)
            errors.append(msg)
        continue
    if isinstance(value, (int, float)) and not math.isfinite(float(value)):
        ...
    lo, hi = spec["range"]
    v = float(np.mean(value))
    if not (lo <= v <= hi):
        ...
```
The `lo, hi = spec["range"]` / `float(np.mean(value))` lines (449-450) are exactly where a string value breaks — insert a branch before that (e.g. `if isinstance(value, str): ... continue`) that checks presence/allowed-value-set instead of numeric range, per RESEARCH.md's recommended default (option (a): `value in spec.get("allowed_values", KNOWN_PROVIDER_NAMES)`).

---

### `backend/tests/units_def_test.py` (test, CRUD schema validation)

**Analog:** itself, v1→v2 test block (`backend/tests/units_def_test.py:410-479`), fully in context above — copy mechanically.

**Frozen-snapshot + version-bump test pattern** (lines 422-444):
```python
import units_def as _units_def_module  # noqa: E402

_V1_SCHEMA_SNAPSHOT = {
    "air_temp": {"unit": "degC", "range": (-20.0, 60.0), "required": True},
    ... # all pre-Phase-4 keys, byte-identical
}

def test_schema_version_bumped_and_v1_columns_are_byte_identical():
    assert _units_def_module.PIPELINE_SCHEMA_VERSION == 2
    for name, spec in _V1_SCHEMA_SNAPSHOT.items():
        assert _units_def_module.PIPELINE_SCHEMA[name] == spec
```
For Phase 6: add `_V2_SCHEMA_SNAPSHOT` (freeze the current, post-Phase-4 schema — all 15 existing keys byte-identical), assert `PIPELINE_SCHEMA_VERSION == 3`.

**New-keys-all-optional test pattern** (lines 447-454):
```python
def test_v2_columns_are_all_optional():
    v2_keys = set(_units_def_module.PIPELINE_SCHEMA) - set(_V1_SCHEMA_SNAPSHOT)
    assert v2_keys == {
        "forecast_horizon_min", "forecast_amps", "forecast_ci_lower_amps",
        "forecast_ci_upper_amps", "anomaly_score",
    }
    for key in v2_keys:
        assert _units_def_module.PIPELINE_SCHEMA[key]["required"] is False
```
For Phase 6: `v3_keys == {"wind_source", "temp_source", "humidity_source", "solar_source"}`, same all-`required is False` assertion.

**Backward-compat test pattern** (lines 457-464):
```python
def test_pre_phase4_row_still_validates():
    row = {"air_temp": 25.0, "wind_speed": 5.0, "wind_direction": 180.0}
    errors = validate_pipeline_row(row, strict=False)
    assert errors == []
```
For Phase 6: `test_pre_phase6_row_still_validates` — a v2-era row (no provenance keys present) must still validate cleanly under the v3 schema (this is the literal mechanism behind Success Criteria #4).

**Positive-case test pattern for new optional columns** (lines 467-478, `test_row_with_valid_forecast_columns_validates`): mirror with a `test_row_with_valid_provenance_columns_validates` that includes all four provenance string values (e.g. `"synoptic"`, `"tceq"`) and asserts `errors == []` once the validator special-case (Pitfall 4 fix) is in place.

---

### `backend/tests/weather_provider_test.py` (new file, test)

**Analog:** `backend/tests/corridor_discretization_test.py` — injection convention (`fake_fetch` closures) and no-network-at-import convention.

**Fake-fetcher injection pattern** (`backend/tests/corridor_discretization_test.py:263-330`, representative excerpt):
```python
def test_rate_corridor_calls_fetcher_once_per_point_even_with_shared_station(...):
    def fake_fetch(stids, start, end):
        ...  # returns a synthetic DataFrame shaped like a real fetch_weather result
    result = rate_corridor(
        synthetic_corridor, "2025-01-01", "2025-01-02", stations, fetch_weather=fake_fetch
    )
```
D-07's mock grid-provider fixture should follow this same closure-based shape: a plain function (not a class, not a fixture decorator) that returns a synthetic `pd.DataFrame` matching the grid-path's expected columns (solar-family fields, keyed by `(lat, lon)` before city resolution).

**No-network-at-import test pattern** (`backend/tests/corridor_discretization_test.py:162-189`, `test_module_importable_with_no_synoptic_token_and_no_network`): write an equivalent test for `weather_provider.py` confirming the module's existing "no side effects on import" contract (docstring lines 20-23) still holds after Phase 6's changes — no new module-level network/env-var access should be introduced by the city-resolution helper.

**Plain-assert, module-level-import convention:** no test classes, no `pytest.fixture` decorators observed in `corridor_discretization_test.py`'s excerpted sections — module-level `import` statements and top-level `def test_*` functions with bare `assert`. Match this style in the new `weather_provider_test.py` file (consistent with `pytest.ini`'s `python_files = test_*.py *_test.py *_TestSuite.py` collection and this repo's established convention).

---

## Shared Patterns

### Fail-safe / explicit-raise-over-silent-guess
**Source:** `backend/weather_provider.py:60-63` (`raise ValueError(f"Unknown weather provider: {provider!r}. ...")`)
**Apply to:** the new `location`-shape validation guard in `fetch_weather`, and any station→city resolution failure (never default to a city or provider name — raise or flag, per CONTEXT.md's fail-safe philosophy and RESEARCH.md's Security Domain table).

### Additive-only schema versioning
**Source:** `backend/units_def.py:319-330` (comment above `PIPELINE_SCHEMA_VERSION`)
**Apply to:** the four new provenance columns — must be `"required": False`, must not alter any existing key's name/unit/range, version bump to 3.

### Frozen-snapshot regression test template
**Source:** `backend/tests/units_def_test.py:422-479` (full v1→v2 test block)
**Apply to:** `units_def_test.py`'s new v2→v3 tests — copy the four-test shape (version-bump+snapshot, new-keys-optional, pre-existing-row-still-validates, new-columns-positive-case) verbatim, substituting v2→v3 names.

### Test-double / fake-fetcher injection over network mocking
**Source:** `backend/tests/corridor_discretization_test.py:284,325,371,397,658` (`fake_fetch` closures passed as `fetch_weather=` kwarg)
**Apply to:** `weather_provider_test.py`'s D-07 mock grid provider and any dispatch/merge tests — never hit the network in tests; use plain closures returning synthetic DataFrames, matching this repo's one established mocking convention.

### Bare top-level imports, no aliasing, no relative-import syntax
**Source:** `backend/weather_provider.py:26-28`, `backend/station_explorer.py:1-5`
**Apply to:** any new `import config` / `import station_explorer` added to `weather_provider.py`.

## No Analog Found

None — every file in scope this phase is either a modification of an existing file (with the file's own prior version as the analog) or a test file with a clear sibling-test-file convention to follow. This phase introduces no new architectural role (no new controller/component/route class).

## Metadata

**Analog search scope:** `backend/` (weather_provider.py, units_def.py, station_explorer.py, dlr_pipeline.py, corridor_discretization.py, config.py) and `backend/tests/` (units_def_test.py, corridor_discretization_test.py)
**Files scanned:** 8 (all fully or targeted-range read; all ≤ 2000 lines, no large-file Grep-first strategy needed)
**Pattern extraction date:** 2026-09-10
