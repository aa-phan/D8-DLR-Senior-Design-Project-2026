<!-- refreshed: 2026-09-02 -->
# Architecture

**Analysis Date:** 2026-09-02

## System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                  Synoptic Data API (West Texas Mesonet)              │
│                    5-minute weather observations                     │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    WEATHER INGESTION LAYER                           │
│              `backend/weather_provider.py` (C4 adapter)              │
│      Abstracts Synoptic API, delegates to dlr_pipeline.py           │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  THERMAL COMPUTATION LAYER                           │
│  `backend/thermal_model.py` (IEEE 738 pure physics, C5)             │
│  ┌─ perpendicular_wind()  — line azimuth projection                │
│  ├─ ieee738_ampacity()    — steady-state heat balance              │
│  └─ ConductorConfig       — ACSR properties                         │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│              VALIDATION & ORCHESTRATION LAYER                        │
│  `backend/dlr_pipeline.py::run_pipeline()` (C1, C2, C3)             │
│  ┌─ fetch_timeseries()        — Synoptic API fetch                 │
│  ├─ validate_pipeline_output()— units_def.py schema check (C2)     │
│  ├─ DLR computation           — perpendicular wind + IEEE 738       │
│  └─ Headroom calculation      — DLR vs static rating comparison    │
└────────────────────────────┬─────────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
                ▼                         ▼
    ┌─────────────────────┐    ┌──────────────────────┐
    │ DATA EXPORT (C3)    │    │ VISUALIZATION (C3)   │
    │ CSV → outputs/      │    │ 4-panel plots        │
    │ station_data/       │    │ PNG → outputs/       │
    │                     │    │ station_plots/       │
    └─────────────────────┘    └──────────────────────┘
            │
            ▼
    ┌─────────────────────────────────────────────────┐
    │  INTEGRATION LAYER (C6)                         │
    │  `backend/ercot_dlr_merger.py`                 │
    │  Merge DLR output with ERCOT grid load data    │
    │  Convert Amps → MW for holistic capacity view  │
    └─────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Weather Ingestion | Fetch 5-min observations from Synoptic API; provider-agnostic interface to shield downstream from provider changes | `backend/weather_provider.py` (C4) |
| Thermal Model | IEEE 738 steady-state ampacity calculation; pure physics, no I/O or orchestration | `backend/thermal_model.py` (C5) |
| Pipeline Orchestration | Fetch → validate inputs → compute wind component → compute ampacity → validate output → export | `backend/dlr_pipeline.py::run_pipeline()` |
| Data Contract | Unit validation (Quantity wrapper), dimensional analysis, plausibility ranges for all pipeline columns | `backend/units_def.py` (C2) |
| Configuration | Centralize parameters: conductor properties, static ratings per location, analysis window defaults | `backend/config.py` (C1) |
| Export & Visualization | Serialize results to CSV, produce 4-panel summary plots (DLR vs static, wind, temperature, headroom histogram) | `backend/dlr_pipeline.py::plot_dlr_summary()`, `export_results()` (C3) |
| Grid Integration | Merge DLR with ERCOT load data, convert Amps → MW, compute utilization metrics | `backend/ercot_dlr_merger.py` (C6) |
| Safety Monitor | Deterministic gate-based anomaly detection (G1–G5: sensor, link, range, plausibility, delta checks); fallback to static rating on failure | `backend/DLRSafetyMonitor.py` (C7, not yet unified with thermal model) |
| Station Discovery | Query Synoptic for WTM stations near transmission corridors; rank by proximity | `backend/station_explorer.py` |

## Pattern Overview

**Overall:** Modular data-science pipeline with explicit component boundaries, provider-agnostic weather ingestion, unit-aware validation, and fail-safe-by-default anomaly detection.

**Key Characteristics:**
- **Layered architecture:** Ingestion → Computation → Validation → Integration → Export
- **Provider abstraction:** `weather_provider.py` shields thermal model and downstream from Synoptic-specific details; open weather-provider decision (Synoptic vs. NOAA) contained at a single boundary
- **Dimensional analysis:** All pipeline rows validated against `PIPELINE_SCHEMA` (C2); Quantity wrapper (`Q` class) enforces unit correctness across conversions
- **Fail-safe defaults:** Any missing or out-of-range input triggers fallback to static rating; non-strict validation logs warnings rather than crashing multi-station runs
- **Pure physics core:** `thermal_model.py` importable without side effects (no file I/O, no env vars, no network calls) — other components (C7, C8, C9) can call it directly
- **Phased implementation:** Ten components (C1–C10) organized into four phases per `docs/data-science/ROADMAP.md`; each phase unblocks the next

## Layers

**Weather Ingestion (C4):**
- **Purpose:** Abstract away the choice of weather data provider; today Synoptic, potentially NOAA or other sources in future
- **Location:** `backend/weather_provider.py`
- **Contains:** `fetch_weather()` provider-agnostic interface; today delegates to `dlr_pipeline.fetch_timeseries()` (Synoptic only)
- **Depends on:** `backend/dlr_pipeline.py::fetch_timeseries()` for Synoptic implementation
- **Used by:** `dlr_pipeline.py::run_pipeline()`, `station_explorer.py`, tests

**Thermal Computation (C5):**
- **Purpose:** Steady-state IEEE 738 ampacity from weather + conductor properties; pure physics, no orchestration
- **Location:** `backend/thermal_model.py`
- **Contains:** 
  - `ieee738_ampacity()` — heat balance solver (forced + natural convection, radiative loss, solar gain)
  - `perpendicular_wind()` — line-azimuth wind component for forced-convection cooling
  - `ConductorConfig` class — ACSR properties (diameter, resistance, emissivity, temperature limits)
  - Air property helpers: `_air_density()`, `_dynamic_viscosity()`, `_thermal_conductivity()`
- **Depends on:** `numpy`, `math` (no imports of other backend modules)
- **Used by:** `dlr_pipeline.py::run_pipeline()`, `DLRSafetyMonitor.py`, future C7/C8/C9 components
- **Note:** Bug fixed in Phase 2: erroneous `* np.pi` factor in forced-convection formula (was overstating capacity ~69%) — now validated against IEEE Standard worked example within 0.95% tolerance

**Data Validation (C2):**
- **Purpose:** Dimensional analysis and plausibility checking; unit-aware validation across pipeline
- **Location:** `backend/units_def.py`
- **Contains:**
  - `PIPELINE_SCHEMA` — column specs (unit, range, required flag) for all DLR outputs
  - `Q` class — Quantity wrapper tracking physical units; supports conversions (A ↔ MW via voltage/power factor)
  - `validate_pipeline_row()` — non-strict row-by-row validation (logs warnings, doesn't drop rows)
  - Unit registry and conversions for 20+ physical dimensions
- **Depends on:** `numpy` (for range-checking arrays)
- **Used by:** `dlr_pipeline.py::validate_pipeline_output()`, tests

**Configuration (C1):**
- **Purpose:** Centralize hardcoded values that were previously scattered and could drift independently
- **Location:** `backend/config.py`
- **Contains:**
  - `STATIC_RATINGS` — per-location normal ratings (San Antonio 1761 A, others defaulting to 900 A)
  - `DEFAULT_CONDUCTOR_CONFIG_KWARGS` — 795 kcmil Drake ACSR properties
  - `DEFAULT_STATION_SOURCE`, `DEFAULT_START`, `DEFAULT_END` — analysis window
  - `LINE_VOLTAGE_KV`, `POWER_FACTOR` — grid electrical parameters for Amps ↔ MW conversion
- **Depends on:** None (pure data)
- **Used by:** `dlr_pipeline.py`, `ercot_dlr_merger.py`, tests

**Pipeline Orchestration (main flow):**
- **Purpose:** Coordinate data fetch, validation, computation, and export
- **Location:** `backend/dlr_pipeline.py::run_pipeline()`
- **Flow:**
  1. Fetch timeseries observations via Synoptic API
  2. Profile missing data per station; drop rows with missing critical variables (air_temp, wind_speed, wind_direction)
  3. Compute perpendicular wind component from line azimuth
  4. Compute IEEE 738 ampacity
  5. Calculate DLR headroom vs. static rating
  6. Validate entire output against PIPELINE_SCHEMA (non-strict)
  7. Return DataFrame for export + visualization
- **Depends on:** `thermal_model`, `units_def`, `config`
- **Used by:** `dlr_pipeline.py::__main__` block, tests, future C6/C8 components

**Export & Visualization (C3):**
- **Purpose:** Serialize results and produce human-readable summaries
- **Location:** `backend/dlr_pipeline.py::export_results()`, `plot_dlr_summary()`
- **Contains:**
  - CSV export with full pipeline output columns
  - 4-panel matplotlib summary: DLR vs. static, wind speed profile, temperature, headroom histogram
  - Plots saved per station
- **Depends on:** `pandas`, `matplotlib`
- **Used by:** `dlr_pipeline.py::__main__`

**Grid Integration (C6):**
- **Purpose:** Merge DLR output with ERCOT load data; convert Amps → MW; assess utilization
- **Location:** `backend/ercot_dlr_merger.py`
- **Contains:**
  - `process_dlr_to_hourly()` — resample 5-min DLR to hourly worst-case (min ampacity per hour)
  - `load_ercot_west_data()` — load/filter real ERCOT load data to DLR window
  - `amps_to_mw()` — 3-phase power conversion: P = √3 × V × I × PF
  - `plot_holistic_grid_view()` — capacity vs. demand visualization
- **Depends on:** `config`, `pandas`
- **Used by:** Research paper analysis, future UI/API

**Safety Monitor (C7, partial):**
- **Purpose:** Deterministic anomaly detection; fallback to static rating on any failure
- **Location:** `backend/DLRSafetyMonitor.py`
- **Contains:** Five gates (G1–G5): sensor availability, communication link, input range, ampacity plausibility, large-change detection
- **Status:** Not yet integrated with thermal model (uses simplified 900 A + linear adjustments); full integration planned in Phase 3
- **Used by:** Real-time monitoring (future)

## Data Flow

### Primary Request Path (run_pipeline)

1. **Entry:** `backend/dlr_pipeline.py::run_pipeline(stids, start, end, conductor, solar_alt_deg, static_rating)` (line ~198)
2. **Fetch observations:** `fetch_timeseries(stids, start, end)` calls Synoptic API via `requests` (lines ~104–150)
   - Returns DataFrame indexed by (stid, datetime_utc) with columns: air_temp, wind_speed, wind_direction, wind_gust, solar_radiation, relative_humidity
3. **Drop missing:** Remove rows with NaN in (air_temp, wind_speed, wind_direction); fill solar_radiation with 1000 W/m² if missing (lines ~213–214)
4. **Perpendicular wind:** `thermal_model.perpendicular_wind()` projects wind onto line azimuth using sine component + low-wind floor (line ~217)
5. **IEEE 738 ampacity:** `thermal_model.ieee738_ampacity()` solves heat balance: I = sqrt((Q_conv + Q_rad - Q_solar) / R(Tc)) (line ~224)
6. **Headroom calculation:** DLR headroom % = (dlr_amps - static_rating) / static_rating × 100; uplift flag if dlr_amps > static_rating (lines ~233–234)
7. **Validation:** `validate_pipeline_output()` runs every row against PIPELINE_SCHEMA (non-strict, logs only); returns number of violations (line ~246)
8. **Return:** DataFrame with added columns: wind_perp_ms, dlr_amps, dlr_headroom_pct, dlr_uplift_flag

### Secondary Flow: Station Discovery

1. **Entry:** `backend/station_explorer.py::discover_stations()` (or manual execution)
2. **Query Synoptic:** `get_wtm_stations(bbox=...)` fetches all WTM network stations in West Texas bounding box
3. **Filter to corridors:** For each defined corridor (Panhandle Export, Permian Basin, etc.), compute distance from corridor center to each station
4. **Rank and export:** Write `data/wtm_stations_austin.csv` with nearest stations per corridor; stores for later pipeline input

### Tertiary Flow: Grid Integration (C6)

1. **Load DLR results:** `process_dlr_to_hourly()` reads CSV output from run_pipeline, resamples to hourly (min ampacity per hour for safety)
2. **Convert to MW:** `amps_to_mw(dlr_amps, 345 kV, 0.95 PF)` → capacity_mw
3. **Load ERCOT data:** `load_ercot_west_data()` reads real ERCOT load CSV, filters to DLR time window
4. **Merge:** Join on datetime; compute utilization = (load_mw / capacity_mw) × 100
5. **Visualize:** `plot_holistic_grid_view()` creates 2-panel plot (capacity vs. demand, utilization %)

**State Management:**
- **Stateless pipelines:** `run_pipeline()` and `ercot_dlr_merger.process_dlr_to_hourly()` are pure functions; all state in DataFrames
- **DLRSafetyMonitor:** Stateful (`self.last_good_rating`), used for real-time gate sequencing; future integration with thermal model (C7)
- **Config module:** Module-level constants; no mutable state

## Key Abstractions

**ConductorConfig:**
- **Purpose:** Encapsulates ACSR physical properties and line parameters for reuse across calculations
- **Examples:** `backend/thermal_model.py::ConductorConfig`, instantiated via `config.DEFAULT_CONDUCTOR_CONFIG_KWARGS`
- **Pattern:** Data class holding diameter, resistance, temp coefficient, emissivity, max temp, line azimuth, elevation
- **Usage:** Passed to `ieee738_ampacity()` to access properties during heat-balance solve

**Quantity (Q):**
- **Purpose:** Unit-aware value wrapper; enforces dimensional consistency and enables automatic conversions
- **Examples:** `Q(900.0, "A")`, `Q(35.0, "degC")`, `Q(5.2, "m/s")`
- **Pattern:** Supports `.to()` conversion with special cases (A ↔ MW requires voltage/power-factor kwargs)
- **Usage:** Tests and future validation decorators (`@check_units`) can enforce expectations at function boundaries

**Provider Adapter:**
- **Purpose:** Abstract away weather data source choice; keep implementation change contained
- **Examples:** `weather_provider.fetch_weather()` today delegates to `dlr_pipeline.fetch_timeseries()` (Synoptic); could add NOAA without changing callers
- **Pattern:** Single-function interface hiding multiple possible implementations

**PIPELINE_SCHEMA:**
- **Purpose:** Data contract: single source of truth for all DLR output columns (unit, valid range, required flag)
- **Examples:** `units_def.PIPELINE_SCHEMA["dlr_amps"]` → `{"unit": "A", "range": (100.0, 4000.0), "required": False}`
- **Pattern:** Dict-of-dicts enabling both row-level validation and API documentation

## Entry Points

**Command-line (main pipeline run):**
- **Location:** `backend/dlr_pipeline.py::__main__` block (line ~440)
- **Triggers:** `python backend/dlr_pipeline.py` from repo root
- **Responsibilities:**
  - Load/parse station source CSV (or query Synoptic interactively)
  - Construct ConductorConfig from config.py defaults
  - Call run_pipeline() with target stations, time window, conductor
  - Export CSV to `outputs/station_data/`
  - Plot 4-panel summaries to `outputs/station_plots/`
- **Environment:** Requires SYNOPTIC_TOKEN env var set

**Programmatic (imported modules):**
- **thermal_model.py:** `from backend.thermal_model import ieee738_ampacity, perpendicular_wind, ConductorConfig`
  - Pure-physics entry point; no side effects; safe to import anywhere
- **weather_provider.py:** `from backend.weather_provider import fetch_weather`
  - Provider-agnostic weather fetch; delegates to Synoptic implementation
- **config.py:** `from backend.config import STATIC_RATINGS, DEFAULT_CONDUCTOR_CONFIG_KWARGS`
  - Import centralized parameters; no functions, just data

**Test entry points:**
- `backend/tests/thermal_model_test.py` — unit tests for IEEE 738 against published worked example
- `backend/tests/units_def_test.py` — unit conversions and dimensional analysis
- `backend/tests/ercot_dlr_merger_test.py` — grid integration calculations
- `backend/tests/SafetyMonitor_TestSuite.py` — deterministic gate logic

## Architectural Constraints

- **Threading:** Single-threaded event loop; no worker threads. Synoptic API calls are blocking; future real-time mode may require async refactor
- **Global state:** `config.py` contains module-level constants (immutable); `DLRSafetyMonitor` holds mutable state (`last_good_rating`) for gate sequencing
- **Circular imports:** None known; `weather_provider.py` imports `dlr_pipeline.py`, but `dlr_pipeline.py` does not import `weather_provider.py` — safe delegation
- **Memory:** Pipeline stores full timeseries in memory (5-min observations × N stations × weeks of data). Kriging/interpolation (C8) may require chunking if scaling to many stations
- **API rate limits:** Synoptic free research tier has per-query station limits (~500 stations) and rate-limit windows (50–100 queries/hour typical); production mode (C9) may need paid tier or NOAA migration
- **Synchronous I/O:** All file reads/writes and API calls are blocking; no concurrent requests. Real-time / near-real-time updates (future) would need async refactor
- **Temporal determinism:** All calculations use UTC timestamps; no wall-clock-dependent logic; same inputs always produce same outputs (reproducibility requirement met)

## Anti-Patterns

### Hardcoded Constants Scattered Across Modules

**What happens:** `static_rating=900.0` appeared independently in `dlr_pipeline.py::__main__` and `ercot_dlr_merger.py` (two independent literals); developers could edit one without the other, silently breaking grid integration.

**Why it's wrong:** Leads to subtle state mismatches; two "sources of truth" for one value; no test catches drift.

**Do this instead:** Centralize in `config.py` — `DEFAULT_STATIC_RATING` and `STATIC_RATINGS` per location. Both modules now read from the same place (`config.DEFAULT_STATIC_RATING` in ercot_dlr_merger.py line 44, `static_rating` parameter in run_pipeline pulled from config elsewhere).

### Deterministic Anomaly Detection Disconnected from Thermal Model

**What happens:** `DLRSafetyMonitor` (C7) uses a simplified 900 + linear formula for ampacity; the real thermal model is in `thermal_model.py`. They compute different ratings for the same inputs.

**Why it's wrong:** Safety gates should validate the actual computation logic, not approximate it. A failing gate's "fallback" value may be wrong by orders of magnitude relative to the real model. Phase 3 will unify them.

**Do this instead:** Import and call `thermal_model.ieee738_ampacity()` inside `DLRSafetyMonitor._compute_ampacity()` instead of the simplified formula.

### Weather Provider Decision Unresolved but Code Tightly Coupled to Synoptic

**What happens:** Every working ingestion path calls Synoptic API directly. Course deliverables (System Design Report) claim NOAA + NSRDB was selected, but no NOAA code exists.

**Why it's wrong:** Scope creep; code doesn't match documentation; switching providers requires rewriting multiple modules.

**Do this instead:** `weather_provider.py` adapter exists but is thin. The open decision (docs/data-science/PRD.md §7.1) is documented, and C4 defines the boundary correctly — future developers can add NOAA behind this interface without touching thermal model, ercot_dlr_merger, etc.

---

*Architecture analysis: 2026-09-02*
