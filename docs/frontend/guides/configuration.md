<!-- generated-by: gsd-doc-writer -->
# Configuration

This guide covers the configuration surface the Software sub-team needs when working with the DLR backend: environment variables and API tokens, the central `backend/config.py` module, and where the backend reads and writes files (`data/` and `outputs/`).

`frontend/` and `api/` are structural placeholders today (see `frontend/README.md` and `api/README.md`). They have no config files, `.env` variables, or build settings of their own yet. Everything below describes the Python backend that the frontend and API layer will consume.

## Environment variables

There is no `.env.example` in the repository. The variables below were found by searching the source for `os.getenv` and `os.environ`.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SYNOPTIC_TOKEN` | Required for any live Synoptic fetch | none (empty string) | Synoptic Data API token. Read in `backend/dlr_pipeline.py` (`fetch_timeseries` and related), `backend/station_explorer.py`, and `backend/smoke_test.py`. Missing token raises an error ("Set SYNOPTIC_TOKEN env var") at the moment of the fetch, not at import. |
| `NREL_API_KEY` | Required only for NSRDB solar data | none (empty string) | NREL/NLR developer API key. Read in `backend/nsrdb_provider.py`. Raises `EnvironmentError` if unset or empty. |
| `NREL_API_EMAIL` | Required only for NSRDB solar data | none (empty string) | Contact email NSRDB requires on each request. Must be the same address the key was registered with. Read in `backend/nsrdb_provider.py`. |

The ASOS, TCEQ, and Open-Meteo providers read no credential (`backend/asos_provider.py`, `backend/tceq_provider.py`, `backend/open_meteo_provider.py`, `backend/open_meteo_forecast_provider.py`). Open-Meteo and ERCOT access need no env var in this repo.

### Tokens and where to get them

- **Synoptic**: register for a free research token at https://synopticdata.com/ (per `README.md` and `backend/dlr_pipeline.py`).
- **NREL/NLR**: register a free developer key on the `developer.nlr.gov` portal (per `README.md`).
- Account ownership, how the team shares these credentials, and the token's rate limits or expiry are not documented in the repo. <!-- VERIFY: who holds the team's Synoptic token and NREL key, and any rate limit or expiry on them -->
- Per `docs/data-science/specs/C4-weather-ingestion.md`, the two stations in `data/wtm_stations_austin.csv` (`MOFWL`, `MOLOK`) returned zero observation rows under the project's token at the time of that check, so `python backend/dlr_pipeline.py` with default config may produce empty output.
- Only the `KAUS` station has been confirmed to return rows under the project's Synoptic token. The other three fallback stations in `backend/config.py` are marked unconfirmed in the code comments.

### Providing the variables

Never commit a real token value. `.env` is git-ignored (`.gitignore`).

1. Export them in your shell:

   ```bash
   export SYNOPTIC_TOKEN=your_token_here
   export NREL_API_KEY=your_key_here
   export NREL_API_EMAIL=your_registered_email@example.com
   ```

2. Or create a `.env` file in the project root (one `NAME=value` per line). Note the loading caveat below.

`python-dotenv` is in `requirements.txt`, but `load_dotenv()` is called in only one place: `backend/forecast_shadow_pipeline.py` (module import time), which the shadow collector uses. A variable already exported in the shell takes precedence over `.env` (`load_dotenv()` default behavior). `backend/config.py` deliberately does not load `.env`, because it promises no side effects on import. For other scripts (`dlr_pipeline.py`, `station_explorer.py`, `smoke_test.py`) the variable must be in the shell environment, since those call `os.getenv` directly and do not load `.env` themselves.

### CI secret

The scheduled workflow `.github/workflows/shadow_collect.yml` reads `SYNOPTIC_TOKEN` from the GitHub repository secret of the same name and passes it to `backend/forecast_shadow_collect.py` as an environment variable. It also uses the built-in `github.token` (as `GH_TOKEN`) to push to the data branch. Whether the repository secret has actually been added is not verifiable from the repo. <!-- VERIFY: the SYNOPTIC_TOKEN secret is set in the GitHub repository's Actions secrets -->

## backend/config.py

`backend/config.py` (component C1) is the single place for tunable constants. Importing it does no file I/O and no network calls, and needs no env var. Import it as `import config` when running with `PYTHONPATH=backend` (the form `pytest.ini` and the workflow both use).

Most values are literal constants in the file. The groups most likely to matter to the dashboard are:

| Constant | Type | What it holds |
|----------|------|---------------|
| `STATIC_RATINGS` | `dict[str, float]` | Static line rating in per-conductor amps per city: AUSTIN 1825, CORPUS_CHRISTI 1500, MIDLAND 1875, EL_PASO 1320. Each is the owner-supplied 345 kV bundle average (3650, 3000, 3750, 1320 A) divided by `SUBCONDUCTORS_PER_PHASE` (2, 2, 2, 1). Each city is its own rating point and uses its own entry; previously a corridor used the `min()` of its two endpoint cities. |
| `DEFAULT_STATIC_RATING` | `float` | 900.0 A fallback for a location not in `STATIC_RATINGS`. |
| `RATING_BOUNDS_BY_LOCATION` / `DEFAULT_RATING_BOUNDS` | `dict` / `tuple` | Per-city plausibility bounds (per-conductor amps) used by the safety monitor: AUSTIN (1150, 2500), CORPUS_CHRISTI (800, 2200), MIDLAND (1250, 2500), EL_PASO (640, 2000) since 2026-10-13 (the Power Systems bundle ranges divided by subconductors; expect more fallbacks than before). Default for an unlisted city is `(400.0, 1800.0)`. Previously the minimum of the two endpoint cities' bounds. |
| `DELTA_FRACTION` | `float` | 0.15. Large-swing threshold as a fraction of the static rating. |
| `SUBCONDUCTORS_PER_PHASE`, `BUNDLE_CONFIG_VERSION`, `BUNDLE_RATING_BASIS` | `dict`, `str`, `str` | Provisional per-city bundle counts (AUSTIN 2, CORPUS_CHRISTI 2, MIDLAND 2, EL_PASO 1) supplied by the Power Systems sub-team. The code states these are a regional assumption, not confirmed for any line segment. Surface the `BUNDLE_RATING_BASIS` caveat wherever bundle ratings are displayed. |
| `CITY_COORDINATES` | `dict[str, tuple[float, float]]` | City-center `(lat, lon)` for the four cities. |
| `LOCATIONS` | `tuple[str, ...]` | The four rating points: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO` (the keys of `CITY_COORDINATES`). The authoritative location list. Replaces `CORRIDOR_ENDPOINTS`; there are no corridors. |
| `CITY_LINE_BEARING_DEG` | `dict[str, float]` | Line azimuth per city, used for the perpendicular-wind component: Austin and Corpus Christi 173.15 degrees, Midland and El Paso 267.54 degrees. An **assumption** carried over from the retired corridor bearings, not a measured line orientation. |
| `LEGACY_CORRIDOR_ENDPOINTS` | `dict[str, tuple[str, str]]` | Retired corridor pairing, kept only for the frozen 2026 forecast-correction experiment. Not for dashboard or API use. |
| `DEFAULT_CONDUCTOR_CONFIG_KWARGS`, `conductor_kwargs_for(azimuth)` | `dict`, function | 795 kcmil Drake ACSR defaults (diameter, resistance, emissivity, absorptivity, 75 C max temp, azimuth, elevation). |
| `LINE_VOLTAGE_KV`, `POWER_FACTOR` | `float` | 345.0 kV and 0.95, used when converting amps to MW. |
| `DEFAULT_STATION_SOURCE`, `DEFAULT_START`, `DEFAULT_END` | `str` | Default station CSV (`data/wtm_stations_austin.csv`) and analysis window (`2025-07-01T00:00:00Z` to `2025-07-04T23:55:00Z`). |
| `ASOS_STATIONS`, `TCEQ_STATIONS`, `SYNOPTIC_FALLBACK_STATIONS` | `dict[str, str]` | Per-city weather station IDs for each provider (ASOS uses 3-letter FAA codes, Synoptic uses 4-letter ICAO codes, TCEQ uses CAMS site IDs). |
| `FORECAST_*`, `ANOMALY_*`, `FORECAST_ML_*`, `ANOMALY_ML_*`, `FORECAST_EXPERIMENT_*` | various | Forecast horizon (60 min), minimum history rows (12), model and cache directories, filename templates, training years, random seeds, and anomaly thresholds for the predictive layers. Read the comments in the file before changing any. |

City keys are always the uppercase underscore form: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`. The static-rating, bounds, coordinates, line-bearing, station, and bundle dicts all use the same keys, so an API layer can join on them directly. ERCOT zone selection is also per city (`ANOMALY_ML_ERCOT_ZONE_SUBSTRINGS_BY_CITY`: Austin and Corpus Christi `SOUTH`, Midland and El Paso `WEST`). The migration to per-city scope (`docs/data-science/decisions/point_scope.md`) was in progress when this guide was updated, so check `backend/config.py` for the current constant names.

### Changing a value

Edit the constant in `backend/config.py`; there is no config file format (JSON/YAML/TOML) and no runtime override mechanism. Changing values the shadow collector persists (such as `SUBCONDUCTORS_PER_PHASE`) requires bumping `BUNDLE_CONFIG_VERSION`, because that version string is written into every persisted bundle record.

## Data and output locations

All paths below are relative to the process working directory, so run backend scripts from the project root. The workflow runs them from the checkout root with `PYTHONPATH=backend`.

| Path | Tracked in git | Written by | Purpose |
|------|----------------|-----------|---------|
| `data/wtm_stations.csv`, `data/wtm_stations_austin.csv` | Yes | checked in (read, not written, by `backend/station_explorer.py`, which writes `data/tx_stations_unrestricted.csv`) | Weather station lists. `data/wtm_stations_austin.csv` is `config.DEFAULT_STATION_SOURCE`. |
| `data/fixtures/sample_pipeline_output.csv` | Yes | n/a | Sample pipeline output, usable as frontend mock data. |
| `data/shadow/predictions/<CITY>.jsonl` | No (git-ignored) | `backend/forecast_shadow_pipeline.py`, `backend/forecast_shadow_collect.py` | Append-only shadow prediction log, one JSON line per cycle, one file per city (`AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`), `schema_version: 3`. Per-city logs start empty. The older `AUSTIN_CORPUS_CHRISTI.jsonl` and `MIDLAND_EL_PASO.jsonl` are legacy corridor-era files (v1 flat and v2) and must be tolerated, not mixed into per-city views. |
| `data/shadow/models/*.joblib` | Yes (deliberately not ignored) | `backend/forecast_shadow_pipeline.py` (model persistence at `SHADOW_MODEL_DIR`) | Trained shadow-model artifacts, named `{method}_{CITY}.joblib` under the per-city model. They are committed so the GitHub Actions runner can load them. Existing corridor-named artifacts are legacy and not loaded; per-city models have not been refit, so ML shadow candidates report `unavailable` until they are. |
| `data/models/` | No (git-ignored) | `backend/forecast_training.py`, `backend/anomaly_training.py` | Forecast and anomaly model artifacts, training frames, and JSON evidence reports. Names come from `config.FORECAST_ML_*` and `config.ANOMALY_ML_*` templates (per city: `forecast_{city}.joblib`, `anomaly_{city}.joblib`). |
| `data/experiment/` | No (git-ignored) | `backend/forecast_experiment.py`, `backend/forecast_leadtime_calibration.py` | Cached fetches and experiment reports (`config.FORECAST_EXPERIMENT_CACHE_DIR`). |
| `data/historical/ampacity_history.csv` | No (git-ignored) | `backend/historical_archive.py` | Append-only ampacity history (`config.HISTORICAL_ARCHIVE_PATH`). Not present in a fresh clone. `corridor` is now `city` and `bottleneck_index` was dropped on 2026-10-13; older files with either header remain readable. |
| `outputs/station_data/*.csv` | No (git-ignored) | `backend/dlr_pipeline.py` | Per-station pipeline CSVs named `<start>_<end>_<STID>.csv`. This is the primary flat-file source `api/README.md` describes for the dashboard. |
| `outputs/station_plots/*.png` | No (git-ignored) | `backend/dlr_pipeline.py` | Per-station plots. |
| `outputs/ercot_data/ercot_west_load_*.csv` | No (git-ignored) | `backend/ercot_data_retriever.py` | ERCOT load pulls. |
| `outputs/merged_ercot_dlr_*.csv`, `outputs/holistic_view_*.png` | No (git-ignored) | `backend/ercot_dlr_merger.py` (plot) | Merged DLR and ERCOT load output and its plot. The merger script itself saves the plot as `holistic_view_<stid>.png` in the current working directory, so the copies under `outputs/` were likely moved there by hand. <!-- VERIFY: how outputs/merged_ercot_dlr_AN489.csv and outputs/holistic_view_AN489.png were produced --> |

Notes for the software team:

- `/outputs` is git-ignored as a whole, so a fresh clone has no `outputs/` files until you run the pipeline (`python backend/dlr_pipeline.py`, which edits its inputs at the bottom of the file rather than taking CLI arguments). For UI work without credentials, start from `data/fixtures/sample_pipeline_output.csv`.
- The scheduled workflow appends new predictions to `data/shadow/predictions/*.jsonl` on a separate branch named `shadow-collection-data` and renders a README table there with `backend/forecast_shadow_render_table.py`. Read live shadow data from that branch, not from `main`. <!-- VERIFY: the shadow-collection-data branch currently exists on the remote and is the intended source for frontend work -->
- The workflow runs four cycles a day at 00:00, 06:00, 12:00 and 18:00 UTC (`cron: '0 0,6,12,18 * * *'`; GitHub often starts scheduled runs hours late) and can be triggered manually from the Actions tab. Each city is collected in its own child process, and every v3 row records the underlying weather model in `forecast_model` (`config.SHADOW_LIVE_FORECAST_MODEL`, currently `gfs_seamless`). To go back to two cycles a day, set the cron to `0 6,18 * * *`; to go back to the earlier underlying weather model, set `SHADOW_LIVE_FORECAST_MODEL` to `"ecmwf_ifs"`.

## Per-environment overrides

The repo defines no `.env.development` or `.env.production` files and no `NODE_ENV`-style switching. The only environment distinction is how credentials are supplied: a local shell export or `.env` file for development, and the GitHub Actions secret for the scheduled collector. Any deployment target for `api/` or `frontend/` has not been decided. <!-- VERIFY: hosting platform and production environment variable management for the future api/ and frontend/ services -->

## Dependencies

Python dependencies are pinned in `requirements.txt` (pandas, numpy, scipy, pytest, beautifulsoup4, scikit-learn, python-dotenv, requests, matplotlib). The workflow uses Python 3.12. Install with:

```bash
python -m pip install -r requirements.txt
```
