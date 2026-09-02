# Technology Stack

**Analysis Date:** 2026-09-02

## Languages

**Primary:**
- Python 3.12.13 - Backend data science pipeline, thermal modeling, ERCOT integration
- TypeScript/JavaScript (planned) - Frontend dashboard and API (not yet implemented)
- Python 3.9+ - System Python for development tools

**Secondary:**
- Markdown - Documentation and project specs (in `docs/`)

## Runtime

**Environment:**
- Python 3.12.13 via pyenv/Homebrew for virtual environment
- Virtual environment at `.venv/` (excluded from git)

**Package Manager:**
- pip - Python package management
- Lockfile: No explicit requirements.txt or pyproject.toml; dependencies declared in README.md

## Frameworks

**Core Data Science:**
- pandas 2.3.3 - Data manipulation and timeseries handling (`backend/dlr_pipeline.py`, `backend/ercot_data_retriever.py`)
- numpy 2.4.3 - Numerical computation and array operations (used by thermal models)
- scipy 1.17.1 - Scientific computing (referenced in README, likely for signal processing)

**Testing:**
- pytest 9.0.3 - Test runner and framework
  - Config: `pytest.ini` with pythonpath pointing to `backend/`
  - Test paths: `backend/tests/`

**Visualization:**
- matplotlib 3.10.8 - Plotting and visualization (IEEE 738 thermal balance plots in `dlr_pipeline.py`)
- matplotlib.dates - Timeseries plot formatting

**HTTP & API:**
- requests 2.32.5 - HTTP client for Synoptic Data API calls

**External Integrations:**
- gridstatus 0.35.0 - ERCOT data retrieval abstraction layer (`backend/ercot_data_retriever.py`)

**Planned (Not Yet Implemented):**
- Flask - Backend-for-frontend API layer (per `api/README.md`)
- React - Frontend dashboard UI (per `frontend/README.md`)

## Key Dependencies

**Critical:**
- pandas 2.3.3 - Powers the entire data pipeline; required for reading/writing CSV outputs
- requests 2.32.5 - Synoptic API communication; blocks weather data ingestion without it
- gridstatus 0.35.0 - ERCOT load data retrieval; enables demand-side analysis without manual export
- numpy 2.4.3 - IEEE 738 thermal calculations depend on vectorized math

**Infrastructure:**
- scipy 1.17.1 - Available for advanced thermal modeling and curve fitting (reserve dependency)
- matplotlib 3.10.8 - 4-panel visualization output for headroom analysis

## Configuration

**Environment:**
- `.env` file present (gitignored, contains sensitive data)
- Environment variable required: `SYNOPTIC_TOKEN` - API token for Synoptic Data weather service (set via `export SYNOPTIC_TOKEN=...`)
- Optional environment variables documented in code but not explicitly validated

**Build:**
- No build step; Python scripts run directly
- pytest.ini - Configures test discovery and Python path
  - pythonpath: `backend/` (allows `from units_def import ...` without path manipulation)
  - testpaths: `backend/tests/`
  - file patterns: `test_*.py`, `*_test.py`, `*_TestSuite.py`

**Source Organization:**
- Main pipeline entry: `backend/dlr_pipeline.py` (uses `__main__` block for execution)
- Configuration centralization: `backend/config.py` (centralizes hardcoded values like static ratings)
- Thermal model: `backend/thermal_model.py` (IEEE 738 heat balance equations)
- Units validation: `backend/units_def.py` (type-safe unit checking for pipeline rows)

## Platform Requirements

**Development:**
- macOS (current dev machine: Darwin 24.5.0)
- Python 3.12+ (with venv support)
- Bash or zsh shell (for environment variable setup)
- `pip` for dependency management

**Production:**
- Any system supporting Python 3.12 (Linux, macOS, Windows possible but untested)
- Network access to Synoptic Data API (HTTPS)
- Network access to ERCOT data via gridstatus client
- File system access to read/write CSV and PNG outputs (in `outputs/` directory)
- Elevation as configuration parameter for wind velocity adjustments (set in `backend/config.py`)

## Data I/O

**Input Sources:**
- Synoptic Data API - 5-minute weather observations via `backend/dlr_pipeline.py::fetch_timeseries()`
- ERCOT historical load data - via gridstatus client in `backend/ercot_data_retriever.py`
- Local CSV metadata - `data/wtm_stations_austin.csv` (West Texas Mesonet station list with proximity rankings)

**Output Formats:**
- CSV files - `outputs/station_data/*.csv` (per-station DLR timeseries with headroom analysis)
- PNG images - `outputs/station_plots/*.png` (4-panel matplotlib visualizations)

---

*Stack analysis: 2026-09-02*
