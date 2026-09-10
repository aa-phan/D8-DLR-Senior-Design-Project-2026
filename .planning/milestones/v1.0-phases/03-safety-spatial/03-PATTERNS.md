# Phase 3: Safety & Spatial - Pattern Map

**Mapped:** 2026-09-03
**Files analyzed:** 6 (2 modified, 1 new module, 1 new test file, config extension, test-fix)
**Analogs found:** 6 / 6

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/DLRSafetyMonitor.py` (modify `_compute_ampacity`, `__init__`, `RATING_BOUNDS`, G1/G2 fallback target) | service (safety-gating orchestration) | request-response (single-reading gate chain) | itself (existing file) — physics call pattern from `backend/dlr_pipeline.py` | exact (physics call site) |
| `backend/config.py` (extend: `CORRIDOR_ENDPOINTS`, per-city `RATING_BOUNDS`/conductor kwargs) | config | CRUD (static lookup) | `backend/config.py::STATIC_RATINGS` (existing dict shape) | exact |
| `backend/corridor_discretization.py` (NEW, C8) | service (orchestration, composes data-access layers) | batch (fan-out per-point compute + min-reduction) | `backend/ercot_dlr_merger.py::process_dlr_to_hourly` (min-reduction) + `backend/station_explorer.py::rank_by_corridor` (nearest-station ranking) | role-match (composed from two analogs, no single direct match — this is a new component type) |
| `backend/station_explorer.py` (extend: generalize `rank_by_corridor` → `nearest_stations(stations, lat, lon, n)`) | utility (geo ranking) | transform | itself (existing `rank_by_corridor`/`haversine_km`) | exact |
| `backend/tests/corridor_discretization_test.py` (NEW) | test | batch | `backend/tests/SafetyMonitor_TestSuite.py` (pytest fixture + assertion style) | role-match |
| `backend/tests/SafetyMonitor_TestSuite.py` (modify: fix gate-2 assertion, add wiring-equivalence test, update G1/G2 fallback-target assertions, add RATING_BOUNDS-aware fixtures) | test | request-response | itself (existing file) | exact |

## Pattern Assignments

### `backend/DLRSafetyMonitor.py` (service, request-response)

**Analog:** itself (`backend/DLRSafetyMonitor.py`, current state) + physics call convention from `backend/thermal_model.py`

**Current placeholder to replace** (`backend/DLRSafetyMonitor.py:62-64`):
```python
def _compute_ampacity(self, d):
    # Simplified IEEE 738 — replace with your full thermal model
    return 900 + d["wind"] * 30 - (d["temp"] - 20) * 4 - d["solar"] * 0.05
```

**Real model signature to call** (`backend/thermal_model.py:104-110`):
```python
def ieee738_ampacity(
    T_amb_c: Union[float, np.ndarray],
    wind_perp_ms: Union[float, np.ndarray],
    ghi_wm2: Union[float, np.ndarray],
    conductor: ConductorConfig,
    solar_altitude_deg: float = 45.0,
) -> np.ndarray
```

**Current constructor to extend** (`backend/DLRSafetyMonitor.py:13-16`):
```python
def __init__(self, static_rating: float, logger=None):
    self.static_rating   = static_rating
    self.last_good_rating = static_rating
    self.logger           = logger or print
```
Add `conductor: thermal_model.ConductorConfig` and `solar_altitude_deg: float = 45.0` params, one `DLRSafetyMonitor` instance per city/corridor (per RESEARCH.md Pattern 1) — mirrors `config.py::DEFAULT_CONDUCTOR_CONFIG_KWARGS`'s existing per-property dict shape (`backend/config.py:60-68`), just now instantiated with a per-corridor `line_azimuth` instead of the global default.

**Fallback dispatch to modify** (`backend/DLRSafetyMonitor.py:22-31`) — currently G1/G2 target `self.last_good_rating`, G3/G4 target `self.static_rating`; per RESEARCH.md's resolved recommendation (A1), change G1/G2 to also target `self.static_rating`:
```python
if not self._gate_sensor(raw_data):
    return self._fallback(result, "G1", "sensor timeout", self.last_good_rating)   # -> self.static_rating
if not self._gate_link(raw_data):
    return self._fallback(result, "G2", "link lost", self.last_good_rating)         # -> self.static_rating
if not self._gate_range(raw_data):
    return self._fallback(result, "G3", "out-of-range", self.static_rating)
```

**`RATING_BOUNDS` to recalibrate** (`backend/DLRSafetyMonitor.py:10`):
```python
RATING_BOUNDS = (400, 1800) # A — plausibility check
```
Incompatible with 3 of 4 `STATIC_RATINGS` (`backend/config.py:41-46`). Follow the `config.py` centralization convention already used for `STATIC_RATINGS` — either widen to a single (600, 5000) band matching the combined per-city documented range, or add a per-city dict in `config.py` next to `STATIC_RATINGS`, consumed the same way.

**Float-wrap pitfall** — `ieee738_ampacity` returns `np.ndarray` even for scalar input (`backend/thermal_model.py:128-130,180-181`); wrap with `float(...)` in `_compute_ampacity` so existing scalar comparisons (`_gate_plausible`, G5 delta check at `backend/DLRSafetyMonitor.py:39-40`) keep working unmodified.

---

### `backend/config.py` (config, CRUD)

**Analog:** `backend/config.py::STATIC_RATINGS` (`backend/config.py:41-46`) — the existing per-city dict shape to extend, not replace:
```python
STATIC_RATINGS: dict[str, float] = {
    "AUSTIN": 1900.0,          # midpoint of documented 800-3000 A range
    "CORPUS_CHRISTI": 3000.0,  # midpoint of documented 1000-5000 A range
    "MIDLAND": 1800.0,         # midpoint of documented 600-3000 A range
    "EL_PASO": 1450.0,         # midpoint of documented 600-2300 A range
}
```
Add `CORRIDOR_ENDPOINTS` (2 city-pairs per D-01) following this same dict-of-tuples convention, and (if per-city RATING_BOUNDS chosen) a parallel dict. `DEFAULT_CONDUCTOR_CONFIG_KWARGS` (`backend/config.py:60-68`) is the analog for a new per-corridor conductor-kwargs structure — same key set, but `line_azimuth` computed per corridor instead of the hardcoded `90.0` at line 66.

---

### `backend/corridor_discretization.py` (NEW — service/orchestration, batch)

**Analog 1 (min-reduction):** `backend/ercot_dlr_merger.py::process_dlr_to_hourly` (`backend/ercot_dlr_merger.py:25-46`), specifically the resample/min step:
```python
hourly = df.resample("1h").agg({
    "dlr_amps": "min",         # Safety first: worst-case capacity
    "wind_speed": "mean",      # Averages for context
    "air_temp": "mean"
}).dropna()
```
C8 analog: `min(point_ampacities)` across the 5 discretized points — same "weakest link" principle, space axis instead of time axis.

**Analog 2 (nearest-station ranking to generalize):** `backend/station_explorer.py::rank_by_corridor` (`backend/station_explorer.py:75-88`):
```python
def rank_by_corridor(stations: pd.DataFrame) -> pd.DataFrame:
    if stations.empty:
        return stations
    for name, (clat, clon) in CORRIDORS.items():
        stations[f"km_to_{name}"] = stations.apply(
            lambda r: haversine_km(r["lat"], r["lon"], clat, clon),
            axis=1,
        )
    dist_cols = [c for c in stations.columns if c.startswith("km_to_")]
    stations["nearest_corridor"] = stations[dist_cols].idxmin(axis=1).str.replace("km_to_", "", regex=False)
    stations["nearest_corridor_km"] = stations[dist_cols].min(axis=1)
    return stations.sort_values("nearest_corridor_km").reset_index(drop=True)
```
Generalize to an arbitrary `(lat, lon)` point (see RESEARCH.md's `nearest_stations` example) rather than the fixed `CORRIDORS` dict — reuses `haversine_km` (`backend/station_explorer.py:17-23`) unchanged.

**Analog 3 (weather fetch, unchanged interface):** `backend/weather_provider.py::fetch_weather` (`backend/weather_provider.py:31-63`):
```python
def fetch_weather(
    stids: list[str],
    start: str,
    end: str,
    provider: str = "synoptic",
) -> pd.DataFrame:
    if provider == "synoptic":
        return dlr_pipeline.fetch_timeseries(stids, start, end)
    raise ValueError(...)
```
Call through this unchanged; do not bypass into `dlr_pipeline` directly (D-07).

**Analog 4 (ampacity call):** same `thermal_model.ieee738_ampacity` call shown under `DLRSafetyMonitor.py` above — C8 must call the identical function, not a second formula.

**Import/module-header convention** to follow (from `backend/weather_provider.py:1-24`): module docstring stating what component (`C8`) this is, no side effects at import time (no network calls / file I/O outside functions).

---

### `backend/station_explorer.py` (utility, transform — extend)

**Analog:** itself. Existing `haversine_km` (`backend/station_explorer.py:17-23`) stays unchanged; `get_all_stations` (`backend/station_explorer.py:48-73`) already supports `network_id: Optional[str] = None` — pass `None` to satisfy D-06's broadened query instead of the hardcoded `network_id = 152` at line 99 (`__main__` block only, not the function default).

**Hardcoded network_id to retire in `__main__`** (`backend/station_explorer.py:96-100`):
```python
# network_id = get_network_id(token, "wtm")
#network_id = get_network_id(token, "WTEXAS")
network_id = 152
# network_id = None
```

---

### `backend/tests/SafetyMonitor_TestSuite.py` (test, request-response)

**Analog:** itself — existing pytest fixture/assertion conventions to follow for new tests.

**Fixture pattern to reuse** (`backend/tests/SafetyMonitor_TestSuite.py:6-19`):
```python
@pytest.fixture
def monitor():
    return DLRSafetyMonitor(static_rating=1000, logger=lambda msg: None)

@pytest.fixture
def valid_data():
    return {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 5.0,
        "temp": 25.0,
        "solar": 500.0,
    }
```
New tests (wiring-equivalence, C8) should extend `monitor()` to accept `conductor`/`solar_altitude_deg` per the constructor change above.

**Bug to fix** (`backend/tests/SafetyMonitor_TestSuite.py:57-66`), line 62 `assert result["status"] == "ok"` → `"fallback"` (contradicts every sibling fallback-path test, e.g. G1 at line 39, G3 at line 74, G4 at line 108).

**Assertions needing target-flip if A1 (G1/G2 fallback target) lands** (`backend/tests/SafetyMonitor_TestSuite.py:189-215`): `test_gate_1_fallback_uses_last_good_rating_after_prior_success` and `test_gate_2_fallback_uses_last_good_rating_after_prior_success` currently assert `result["rating"] == good_rating`; change to `result["rating"] == monitor.static_rating`, matching the existing sibling pattern already used at lines 217-228 (`test_gate_3_fallback_uses_static_rating_not_last_good`).

**Wiring-equivalence test to add** — no existing analog in this file (new), but follow the direct-comparison style already used in `test_plausibility_bounds_are_inclusive` (`backend/tests/SafetyMonitor_TestSuite.py:264-270`) which instantiates `DLRSafetyMonitor` standalone and calls a method directly — same style works for asserting `monitor._compute_ampacity(d) == thermal_model.ieee738_ampacity(...)`.

---

### `backend/tests/corridor_discretization_test.py` (NEW test file)

**Analog:** `backend/tests/SafetyMonitor_TestSuite.py`'s overall file structure (imports at top, `@pytest.fixture`s, one `test_*` function per behavior, plain `assert`s, no test classes) — no corridor-specific test file exists yet to copy from directly (confirmed via RESEARCH.md's repo-wide grep returning zero matches). Use `backend/tests/thermal_model_test.py` as a secondary structural reference for testing pure numeric/geo functions (interpolation, bearing) without mocks, since those functions (`discretize_corridor`, `initial_bearing_deg`, `nearest_stations`) are pure/offline like `thermal_model.py`'s functions.

## Shared Patterns

### Fail-safe-by-default fallback (DS-NF5)
**Source:** `backend/DLRSafetyMonitor.py::_fallback` (`backend/DLRSafetyMonitor.py:66-71`):
```python
def _fallback(self, result, gate, reason, rating):
    msg = f"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"
    self.logger(msg)
    result.update({"status": "fallback", "rating": rating, "fallback": True,
                    "alerts": [msg]})
    return result
```
**Apply to:** any new C8 per-point/per-corridor code path that runs out of usable weather data (D-09) — reuse `static_rating` as the terminal fallback target, same as C7's G3/G4 (and, post-A1, G1/G2).

### Config centralization (C1)
**Source:** `backend/config.py` (whole file) — every per-location numeric value (`STATIC_RATINGS`, `DEFAULT_CONDUCTOR_CONFIG_KWARGS`, line electrical params) lives here, not as scattered literals in the modules that use them (see `ercot_dlr_merger.py:12-13` importing `config.LINE_VOLTAGE_KV`/`config.POWER_FACTOR` rather than hardcoding).
**Apply to:** `CORRIDOR_ENDPOINTS`, per-corridor `line_azimuth`, any new `RATING_BOUNDS` values — all belong in `config.py`, read by `DLRSafetyMonitor.py` and `corridor_discretization.py`.

### Single source of truth for ampacity physics
**Source:** `backend/thermal_model.py::ieee738_ampacity` (`backend/thermal_model.py:104-181`).
**Apply to:** both `DLRSafetyMonitor._compute_ampacity` and every per-point computation inside `corridor_discretization.py` — never a second formula.

### Haversine / great-circle math style (stdlib `math` only, no geo library)
**Source:** `backend/station_explorer.py::haversine_km` (`backend/station_explorer.py:17-23`):
```python
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
```
**Apply to:** new geodesic interpolation (`interpolate_great_circle`) and bearing (`initial_bearing_deg`) functions in `corridor_discretization.py` — same `math`-only style, no `geopy`/`pyproj`.

## No Analog Found

None — every new/modified file has at least a role-match analog in the existing codebase (see table above); `corridor_discretization.py` is genuinely new but is explicitly composed from three existing analogs rather than left without one.

## Metadata

**Analog search scope:** `backend/` (all `.py` files), `backend/tests/`
**Files scanned:** `backend/DLRSafetyMonitor.py`, `backend/thermal_model.py`, `backend/station_explorer.py`, `backend/weather_provider.py`, `backend/config.py`, `backend/ercot_dlr_merger.py`, `backend/dlr_pipeline.py` (referenced, not re-read in full), `backend/tests/SafetyMonitor_TestSuite.py`
**Pattern extraction date:** 2026-09-03
