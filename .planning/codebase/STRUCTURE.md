# Codebase Structure

**Analysis Date:** 2026-09-02

## Directory Layout

```
Senior_Design/
├── backend/
│   ├── __pycache__/           # Python bytecode (gitignored)
│   ├── tests/
│   │   ├── SafetyMonitor_TestSuite.py   # DLRSafetyMonitor gate tests
│   │   ├── ercot_dlr_merger_test.py     # Grid integration tests
│   │   ├── thermal_model_test.py        # IEEE 738 vs. published reference
│   │   └── units_def_test.py            # Unit conversion and validation
│   ├── config.py                         # C1: Centralized configuration & parameters
│   ├── DLRSafetyMonitor.py               # C7: Deterministic anomaly-detection gates (not yet unified with thermal model)
│   ├── dlr_pipeline.py                   # Main orchestration: fetch → compute → export + visualize
│   ├── ercot_dlr_merger.py               # C6: Merge DLR with ERCOT load, convert Amps → MW
│   ├── station_explorer.py               # Discover WTM stations near corridors
│   ├── thermal_model.py                  # C5: IEEE 738 pure physics (perpendicular wind, heat balance, ampacity)
│   ├── units_def.py                      # C2: Unit validation, Quantity wrapper, PIPELINE_SCHEMA
│   ├── weather_provider.py               # C4: Provider-agnostic weather ingestion adapter
│   └── ercot_data_retriever.py           # Fetch ERCOT hourly load data
│
├── data/
│   ├── fixtures/                         # Test fixtures (reference data for validation)
│   └── wtm_stations_austin.csv           # WTM station metadata ranked by corridor proximity
│
├── docs/
│   ├── data-science/
│   │   ├── PRD.md                        # Product Requirements (phase overview, open decisions, doc discrepancies)
│   │   ├── ROADMAP.md                    # Phase order, dependencies, rationale (C1–C10)
│   │   ├── citations.md                  # Bibliography for AI-assisted research + verification checklist
│   │   ├── decisions/
│   │   │   └── data_provider.md          # Weather provider decision (Synoptic vs. NOAA vs. hybrid)
│   │   ├── schema/
│   │   │   └── pipeline_output_v1.md     # Export schema documentation (CSV columns, units, ranges)
│   │   └── specs/
│   │       ├── README.md                 # Index of C1–C10 component specs
│   │       ├── C1-configuration.md       # Config module (centralize hardcoded values)
│   │       ├── C2-data-contract.md       # Units, dimensional analysis, PIPELINE_SCHEMA
│   │       ├── C3-export-visualization.md # CSV export, 4-panel plots
│   │       ├── C4-weather-ingestion.md   # Provider-agnostic adapter (Synoptic today)
│   │       ├── C5-thermal-model.md       # IEEE 738 heat balance, ConductorConfig
│   │       ├── C6-grid-load-integration.md # Merge DLR with ERCOT load, Amps→MW
│   │       ├── C7-safety-monitor.md      # Deterministic gates (G1–G5), fallback logic
│   │       ├── C8-corridor-discretization.md # Spatial pipeline (not started)
│   │       ├── C9-ampacity-forecasting.md # ML-based forecasting (not started)
│   │       └── C10-anomaly-detection.md  # Trained anomaly detection (not started)
│   ├── frontend/
│   │   └── README.md                     # Frontend subsystem placeholder (React UI, not started)
│   ├── Project Definition.md             # Course deliverable: problem statement, I/O spec, ethical commitment
│   ├── System Design Report.md           # Course deliverable: design concept, risk reduction, test plan
│   └── Prior Art Report.md               # Course deliverable: related work bibliography
│
├── frontend/
│   └── README.md                         # Frontend subsystem placeholder (React, not started)
│
├── api/
│   └── README.md                         # API subsystem placeholder (Flask BFF, not started)
│
├── outputs/
│   ├── ercot_data/                       # ERCOT load data fetched from API (CSV, gitignored)
│   ├── station_data/                     # Pipeline output CSVs per station (gitignored)
│   └── station_plots/                    # 4-panel PNG summaries per station (gitignored)
│
├── .planning/
│   └── codebase/
│       ├── ARCHITECTURE.md               # This file: architecture, layers, data flow, abstractions
│       └── STRUCTURE.md                  # (This file) Directory purposes, naming conventions, where to add code
│
├── README.md                             # Project overview, setup instructions, DLR background
├── ACKNOWLEDGEMENTS.md                   # AI-use disclosure (ECE 464 requirement)
└── .gitignore                            # Ignores .env, __pycache__, outputs/, .venv/
```

## Directory Purposes

**backend/:**
- **Purpose:** Data Science subsystem — weather ingestion, IEEE 738 thermal computation, grid integration, safety monitoring
- **Contains:** Core pipeline modules (dlr_pipeline.py, thermal_model.py, weather_provider.py, etc.), configuration, unit validation
- **Key files:**
  - `dlr_pipeline.py` — main entry point; orchestrates fetch → compute → export
  - `thermal_model.py` — pure physics; IEEE 738 ampacity solver
  - `config.py` — centralized parameters (conductor, static ratings, analysis window)
  - `units_def.py` — data contract; PIPELINE_SCHEMA, Quantity wrapper
  - `ercot_dlr_merger.py` — grid integration; resample to hourly, merge with ERCOT load
- **Tests:** `backend/tests/` contains pytest modules for all core logic

**data/:**
- **Purpose:** Checked-in reference inputs; fixture data for testing and station discovery
- **Contains:** WTM station metadata CSV; test fixtures
- **Key files:** `wtm_stations_austin.csv` — station list with lat/lon/elevation ranked by corridor proximity

**docs/data-science/:**
- **Purpose:** Technical documentation following a three-level structure: PRD (what), ROADMAP (when + why), specs (how)
- **Contains:** Phase definitions, component specs (C1–C10), decisions, schema documentation, citations
- **Key files:**
  - `PRD.md` — product requirements, open decisions, documented discrepancies vs. course deliverables
  - `ROADMAP.md` — phased delivery (4 phases), dependency graph, parallel-safe components
  - `specs/C*-*.md` — per-component technical specs (acceptance criteria, interfaces, known issues)
  - `citations.md` — AI-assisted research bibliography with verification status

**docs/frontend/, docs/frontend/README.md:**
- **Purpose:** Placeholder structure for UI subsystem documentation (mirrors data-science/ structure)
- **Status:** Not started; will follow PRD → ROADMAP → component specs pattern once development begins

**frontend/, api/:**
- **Purpose:** Subsystem placeholders; structural directories with READMEs
- **Status:** Not started; owned by Software sub-team
- **frontend/** will contain React dashboard code once started
- **api/** will contain Flask BFF (Backend-for-Frontend) once started

**outputs/:**
- **Purpose:** Runtime outputs (CSV results, plots, ERCOT data); all gitignored
- **Contains:**
  - `station_data/` — per-station DLR CSVs written by `dlr_pipeline.py::export_results()`
  - `station_plots/` — per-station 4-panel PNGs written by `dlr_pipeline.py::plot_dlr_summary()`
  - `ercot_data/` — ERCOT load CSVs fetched by `ercot_data_retriever.py`

## Key File Locations

**Entry Points:**
- `backend/dlr_pipeline.py` — main pipeline entry point; run with `python backend/dlr_pipeline.py` from repo root
- `backend/station_explorer.py` — discover stations; run with `python backend/station_explorer.py`
- `backend/ercot_data_retriever.py` — fetch ERCOT load data; run with `python backend/ercot_data_retriever.py`

**Configuration:**
- `backend/config.py` — centralized parameters: conductor properties, static ratings, analysis window, line voltage, power factor
- `.env` — environment variables (SYNOPTIC_TOKEN); must be created locally, never committed

**Core Logic:**
- `backend/dlr_pipeline.py::run_pipeline()` — main orchestration function (lines ~198–248)
  - Fetch observations → drop missing → compute wind component → compute ampacity → validate → return
- `backend/thermal_model.py::ieee738_ampacity()` — heat balance solver (lines ~104–181)
  - Forced convection, natural convection, radiative loss, solar gain → ampacity
- `backend/thermal_model.py::perpendicular_wind()` — line azimuth projection (lines ~22–55)
- `backend/weather_provider.py::fetch_weather()` — provider-agnostic interface (lines ~31–63)

**Data Validation:**
- `backend/units_def.py::PIPELINE_SCHEMA` — column specifications (line ~324)
- `backend/units_def.py::validate_pipeline_row()` — row-by-row validation (line ~378)
- `backend/units_def.py::Q` class — Quantity wrapper (line ~142)

**Grid Integration:**
- `backend/ercot_dlr_merger.py::process_dlr_to_hourly()` — resample DLR to hourly (line ~25)
- `backend/ercot_dlr_merger.py::amps_to_mw()` — 3-phase power conversion (line ~15)
- `backend/ercot_dlr_merger.py::plot_holistic_grid_view()` — capacity vs. demand visualization (line ~72)

**Safety & Anomaly Detection:**
- `backend/DLRSafetyMonitor.py::DLRSafetyMonitor.run_check()` — gate sequencing (line ~18)
- `backend/DLRSafetyMonitor.py::DLRSafetyMonitor._compute_ampacity()` — simplified ampacity (currently not unified with thermal model)

**Testing:**
- `backend/tests/thermal_model_test.py` — IEEE 738 reference validation (published worked example)
- `backend/tests/units_def_test.py` — unit conversions, dimensional analysis
- `backend/tests/ercot_dlr_merger_test.py` — Amps ↔ MW, hourly resampling
- `backend/tests/SafetyMonitor_TestSuite.py` — deterministic gates (G1–G5)

## Naming Conventions

**Files:**
- **Module names:** snake_case (`dlr_pipeline.py`, `thermal_model.py`, `weather_provider.py`)
- **Test files:** `{module}_test.py` or `{feature}_TestSuite.py` (e.g., `thermal_model_test.py`, `SafetyMonitor_TestSuite.py`)
- **Output files:** `dlr_{stid}.png`, `{stid}.csv` in `outputs/`
- **Config files:** lowercase, often prefixed by purpose (`config.py`)

**Directories:**
- **Backend subsystem:** `backend/` (Python DS pipeline)
- **Tests:** `{subsystem}/tests/` (co-located near code; e.g., `backend/tests/`)
- **Documentation:** `docs/{subsystem}/` (e.g., `docs/data-science/`, `docs/frontend/`)
- **Outputs:** `outputs/{category}/` (e.g., `outputs/station_data/`, `outputs/station_plots/`)
- **Configuration:** module-level in `config.py` or env vars (`.env`)

**Python Identifiers:**
- **Functions:** snake_case (`run_pipeline()`, `ieee738_ampacity()`, `perpendicular_wind()`)
- **Classes:** PascalCase (`ConductorConfig`, `DLRSafetyMonitor`, `Q`)
- **Constants:** UPPER_SNAKE_CASE (`STATIC_RATINGS`, `PIPELINE_SCHEMA`, `WTM_NETWORK`, `DLR_VARS`)
- **Module-level imports:** Standard library, then third-party, then local (implicit order in all backend modules)

**Column Names (DataFrames):**
- **Meteorological inputs:** `air_temp`, `wind_speed`, `wind_direction`, `wind_gust`, `solar_radiation`, `relative_humidity` (from Synoptic API)
- **Derived / computed:** `wind_perp_ms` (perpendicular component), `dlr_amps` (IEEE 738 rating)
- **Output metrics:** `dlr_headroom_pct` (% above static), `dlr_uplift_flag` (boolean)
- **Timestamps:** `datetime_utc` (ISO 8601 UTC strings, converted to pandas Timestamp)
- **Identifiers:** `stid` (Synoptic station ID)

## Where to Add New Code

**New Physics Component (e.g., alternate wind model, radiative formula refinement):**
- **Implementation:** `backend/thermal_model.py` (extend or add new function alongside existing IEEE 738 logic)
- **Example:** To add a different radiance model, add a parameter to `ieee738_ampacity()` to select model; keep `ConductorConfig` unchanged
- **Tests:** `backend/tests/thermal_model_test.py` (add reference-validation cases)

**New Data Provider (e.g., NOAA, NSRDB):**
- **Implementation:** 
  - Add provider-specific fetch function to `backend/dlr_pipeline.py` or a new module `backend/noaa_provider.py`
  - Extend `backend/weather_provider.py::fetch_weather()` to detect provider and route accordingly
- **Example:** `weather_provider.fetch_weather(..., provider="noaa")` branches to `noaa_provider.fetch_noaa_timeseries()`
- **Tests:** Add provider-specific test cases to existing test suite

**New Anomaly-Detection Gate (augment C7):**
- **Implementation:** 
  - Add gate method to `backend/DLRSafetyMonitor.py` (e.g., `_gate_ml_anomaly()`)
  - Chain into `run_check()` sequence after G5
  - For Phase 3 unification: import and call `thermal_model.ieee738_ampacity()` in `_compute_ampacity()` instead of simplified formula
- **Tests:** `backend/tests/SafetyMonitor_TestSuite.py` (add gate logic cases)

**New Component in Phased Roadmap (C7, C8, C9, C10):**
- **Implementation:** 
  - Create new module: `backend/{feature_name}.py` (e.g., `backend/corridor_discretization.py` for C8)
  - Follow spec in `docs/data-science/specs/C{N}-*.md` (existing acceptance criteria, interfaces, constraints)
  - Import from lower-layer components only (thermal_model, units_def, weather_provider)
- **Documentation:** Update `docs/data-science/specs/README.md` index to reflect new component
- **Tests:** Create `backend/tests/{feature_name}_test.py`
- **Entry:** Add new `__main__` block in module, or integrate into orchestration in `dlr_pipeline.py`

**New Visualization or Report:**
- **Implementation:** Add function to `backend/dlr_pipeline.py` or create new module `backend/reporting.py`
- **Example:** `plot_dlr_summary()` (4-panel per-station) or `plot_holistic_grid_view()` (capacity vs. demand, already exists in ercot_dlr_merger.py)
- **Output:** Write to `outputs/{category}/` subdirectory

**New Unit or Quantity Type:**
- **Implementation:** Add to `backend/units_def.py`
  - Extend `UNIT_DIMENSIONS` dict with new unit and its dimension
  - Add conversion factor to `CONVERSIONS` dict (or handle via formula if non-linear)
  - Extend `PIPELINE_SCHEMA` if it's an output column
- **Example:** Adding `"kA"` (kiloamps) to handle large conductor currents
- **Tests:** `backend/tests/units_def_test.py` (conversion, range-check, schema-validation cases)

**New Static Rating or Configuration Value:**
- **Implementation:** `backend/config.py`
  - Add to appropriate constant dict (`STATIC_RATINGS`, `DEFAULT_CONDUCTOR_CONFIG_KWARGS`, etc.)
  - Document source/rationale as inline comment
- **Rationale:** Centralizes values so they're not scattered and prone to drift

**UI Dashboard or API Endpoint (future):**
- **Frontend:** Create in `frontend/` directory; follow `docs/frontend/README.md` structure (PRD → ROADMAP → component specs)
- **API:** Create in `api/` directory; define endpoints that consume `backend/dlr_pipeline.py::run_pipeline()` output or call modules directly
- **Integration:** Import from `backend/` modules (thermal_model, config, weather_provider, ercot_dlr_merger)

## Special Directories

**outputs/:**
- **Purpose:** Runtime-generated results (gitignored)
- **Generated:** Yes — created by `dlr_pipeline.py::export_results()` and `plot_dlr_summary()`, and by `ercot_dlr_merger.py`
- **Committed:** No (gitignored)
- **Subdirectories:**
  - `station_data/` — CSV files per station (created by run)
  - `station_plots/` — PNG 4-panel plots per station (created by run)
  - `ercot_data/` — ERCOT load CSVs fetched from API

**data/:**
- **Purpose:** Checked-in reference inputs (not generated at runtime)
- **Generated:** No (manually maintained or bootstrap script)
- **Committed:** Yes
- **Subdirectories:**
  - `fixtures/` — test fixture data for validation
  - Top-level: `wtm_stations_austin.csv` (generated once by `station_explorer.py`, then checked in)

**.planning/codebase/:**
- **Purpose:** Codebase analysis documents (ARCHITECTURE.md, STRUCTURE.md, etc.)
- **Generated:** Yes — created by orchestrator tools (gsd-map-codebase)
- **Committed:** Yes (analysis documents are persisted for reference)

---

*Structure analysis: 2026-09-02*
