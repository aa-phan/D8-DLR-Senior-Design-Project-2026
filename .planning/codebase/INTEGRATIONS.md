# External Integrations

**Analysis Date:** 2026-09-02

## APIs & External Services

**Weather Observations:**
- Synoptic Data API - Fetches 5-minute weather timeseries for West Texas Mesonet (WTM) stations
  - SDK/Client: requests 2.32.5 (raw HTTP calls)
  - Endpoint: `https://api.synopticdata.com/v2/`
  - Auth: `SYNOPTIC_TOKEN` environment variable (API token)
  - Implementation: `backend/dlr_pipeline.py::fetch_timeseries()` and `backend/weather_provider.py`
  - Required variables: air_temp, wind_speed, wind_direction, wind_gust, solar_radiation, relative_humidity
  - Network ID: "wtm" (West Texas Mesonet)
  - Bounding box: (28.5, -106.5, 36.5, -99.0) — West Texas default, configurable

**Grid Operations Data:**
- ERCOT (Electric Reliability Council of Texas) - Historical load data retrieval
  - SDK/Client: gridstatus 0.35.0 (abstraction layer)
  - Implementation: `backend/ercot_data_retriever.py::pull_ercot_data()`
  - Data: Hourly load settlements by ERCOT zone (FAR_WEST, WEST, etc.)
  - No explicit authentication required; public data
  - Uses `gridstatus.Ercot()` client to auto-download and parse yearly archives

## Data Storage

**Databases:**
- None (no persistent database configured)
- Workflow: API data → pandas DataFrame → CSV export

**File Storage:**
- Local filesystem only
  - Inputs: `data/wtm_stations_austin.csv` (static station metadata)
  - Outputs: `outputs/station_data/*.csv` (DLR timeseries) and `outputs/station_plots/*.png` (visualization)
  - No cloud storage integration

**Caching:**
- None - Pipeline fetches fresh data each run
- Synoptic and ERCOT data are pulled on-demand and written to disk immediately

## Authentication & Identity

**Auth Provider:**
- Custom API token management (no OAuth/SAML)
- Synoptic Data:
  - Auth method: Bearer token in URL query parameter
  - Token source: Environment variable `SYNOPTIC_TOKEN`
  - Registration: Free research tokens at https://synopticdata.com/
  - Token validation: `backend/dlr_pipeline.py::_token()` function raises `EnvironmentError` if missing
- ERCOT:
  - No auth required (public data service via gridstatus)

## Monitoring & Observability

**Error Tracking:**
- None (no external error tracking service)
- Errors logged to stdout via Python `logging` module (see `backend/dlr_pipeline.py::log`)

**Logs:**
- Stdout only
  - Logging level: INFO (configurable in `backend/dlr_pipeline.py::logging.basicConfig()`)
  - Format: `%(levelname)s | %(message)s`
  - Examples: "Fetching WTM station metadata …", "Success! Saved X hourly records to …"

## CI/CD & Deployment

**Hosting:**
- None yet (code is experimental/research phase)
- Designed for local execution or future cloud scheduling

**CI Pipeline:**
- None (no GitHub Actions or similar)
- Manual testing via pytest: `pytest backend/tests -v`

**Deployment:**
- Manual: Run `python backend/dlr_pipeline.py` from repo root
- No containerization (Dockerfile not present)
- Output files written to local `outputs/` directory (gitignored)

## Environment Configuration

**Required env vars:**
- `SYNOPTIC_TOKEN` - Synoptic Data API authentication token (no default, raises error if missing)

**Optional env vars:**
- None explicitly declared; all configuration via Python constants in `backend/config.py`

**Configuration File:**
- `backend/config.py` - Centralized configuration
  - Static line ratings per ERCOT corridor (SAN_ANTONIO: 1761 A, others: 900 A default)
  - Conductor specs: Drake ACSR (795 kcmil) with 0.02814 m diameter
  - Analysis window defaults: 2025-07-01 to 2025-07-04 (UTC)
  - Line voltage: 345 kV (ERCOT backbone standard)
  - Power factor: 0.95 (conservative grid assumption)

**Secrets location:**
- `.env` file (local, gitignored) — contains `SYNOPTIC_TOKEN` value
- Never committed to git
- See `.gitignore`: `.env` listed as ignored

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Data Integration Patterns

**Weather-ERCOT Merger:**
- Workflow: `backend/ercot_dlr_merger.py` combines Synoptic weather with ERCOT load
  - Input 1: Synoptic timeseries (5-min intervals, per-station)
  - Input 2: ERCOT zone load (hourly intervals)
  - Merge: Time-indexed on `datetime_utc`, aggregated by zone
  - Output: Combined CSV with columns for both DLR and demand

**Planned Frontend Integration:**
- Backend exports to CSV/PNG in `outputs/`
- API layer (`api/`) will serve this data to React dashboard (`frontend/`)
- Flask endpoint pattern: Not yet implemented
- Real-time vs. batch: Current design is batch (manual run), future may add scheduled polling

---

*Integration audit: 2026-09-02*
