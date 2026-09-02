# Constraints (from SPEC-classified documents)

12 SPEC-classified documents in this ingest batch: C1–C10 component specs, `pipeline_output_v1.md`, and `Project Definition.md`.

---

## C1 — Configuration & Parameterization
- source: docs/data-science/specs/C1-configuration.md
- type: schema
- content: `backend/config.py`, a plain Python constants module, no new dependencies, no side effects at import. Exposes `STATIC_RATINGS: dict[str, float]` (per-city static ratings for 5 TX cities: HOUSTON, AUSTIN, DALLAS, FORT_WORTH, SAN_ANTONIO — SAN_ANTONIO=1,761A cited to ERCOT Board Item 11.2 Aug 2023; the other four use an honestly-labeled uniform 900A baseline); `DEFAULT_STATIC_RATING = 900.0`; `DEFAULT_CONDUCTOR_CONFIG_KWARGS`; `DEFAULT_STATION_SOURCE`/`DEFAULT_START`/`DEFAULT_END`; `LINE_VOLTAGE_KV = 345.0`; `POWER_FACTOR = 0.95`. Not yet done: nothing selects a specific city's `STATIC_RATINGS` entry per run — every run uses `DEFAULT_STATIC_RATING` unconditionally. Blocks C2, C4, C5, C6 (transitively C3, C7 and everything downstream).

## C2 — Pipeline Data Contract
- source: docs/data-science/specs/C2-data-contract.md
- type: schema
- content: `backend/units_def.py::PIPELINE_SCHEMA` (line 324) is the single canonical schema — per column: unit, range (lo, hi), required. Columns: `air_temp` (degC), `wind_speed` (m/s), `wind_direction` (deg), `wind_perp_ms` (m/s), `solar_radiation` (W/m²), `relative_humidity` (%), `dlr_amps` (A), `dlr_capacity_mw` (MW), `static_capacity_mw` (MW), `ercot_west_load_mw` (MW). `validate_pipeline_row(row, strict=True) -> list[str]` and `validate_pipeline_output(df) -> int` (called automatically as the last step of `run_pipeline`, non-strict, logs a WARNING summary). `Q(value, unit, label)` dataclass with `.to()`, `.assert_unit`, `.assert_dimension`, `.assert_range`; `@check_units(**expected_units)` decorator. This spec's own text: "`PIPELINE_SCHEMA` is the data contract. Do not restate it in any other spec or doc — reference this file." Known duplication: `DLRSafetyMonitor.py`'s own `WIND_BOUNDS`/`TEMP_BOUNDS`/`SOLAR_BOUNDS` independently duplicate ranges already defined here (not yet consolidated).

## C3 — Export & Visualization
- source: docs/data-science/specs/C3-export-visualization.md
- type: api-contract
- content: `export_results(df, output_path, file_prefix)` writes one CSV per station to `outputs/station_data/` — columns: `stid, datetime_utc, air_temp, wind_speed, wind_direction, wind_perp_ms, solar_radiation, relative_humidity, dlr_amps, dlr_headroom_pct, dlr_uplift_flag`. This is a documented subset of `PIPELINE_SCHEMA` (C2) — `dlr_capacity_mw`/`static_capacity_mw` are computed later, in C6, not here. `plot_dlr_summary` produces a 4-panel PNG per station; `ercot_dlr_merger.py::plot_holistic_grid_view` produces a 2-panel PNG. This is the actual DS→Software-sub-team dashboard interface contract. Known issue: a station returning zero observation rows is silently dropped from output with no warning logged.

## C4 — Weather Ingestion
- source: docs/data-science/specs/C4-weather-ingestion.md
- type: api-contract
- content: `backend/weather_provider.py::fetch_weather(stids, start, end, provider="synoptic") -> pd.DataFrame` — provider-agnostic adapter interface. For `provider="synoptic"`, delegates to `dlr_pipeline.fetch_timeseries` unchanged; any other provider value raises `ValueError`. Deliberately does NOT implement a second provider (e.g. NOAA) — doing so would resolve the still-open provider decision (`PRD.md` §7.1) rather than just insulating callers from it. Output rows conform to the weather-observation subset of `PIPELINE_SCHEMA`: `air_temp`, `wind_speed`, `wind_direction`, `solar_radiation`, `relative_humidity`, indexed by `(stid, datetime_utc)`. Requires `SYNOPTIC_TOKEN` env var only for the underlying Synoptic path — module itself is importable without it.

## C5 — Thermal Model (IEEE 738)
- source: docs/data-science/specs/C5-thermal-model.md
- type: api-contract
- content: `backend/thermal_model.py`. `ConductorConfig` — 795 kcmil Drake ACSR defaults (diameter 0.02814 m, AC resistance 0.0726 Ω/km @25°C, temp coefficient 0.00404/°C, emissivity/absorptivity 0.8, max temp 75°C, line azimuth 90°, elevation 300 m). `perpendicular_wind(wind_speed_ms, wind_dir_deg, line_azimuth_deg)`. `ieee738_ampacity(T_amb_c, wind_perp_ms, ghi_wm2, conductor, solar_altitude_deg=45.0) -> np.ndarray` — output ampacity in Amps, matches `PIPELINE_SCHEMA["dlr_amps"]` range [100, 4000] A. No ingestion dependency, no `__main__` side effects, callable without `SYNOPTIC_TOKEN`. **Critical bug fixed this pass**: forced-convection term had an erroneous `* np.pi` factor (no basis in IEEE Std 738-2023 Eq. 9/10) — buggy formula computed ~1728A vs published-correct 1025A (~69% overestimate) for the standard's own worked example; fixed version now computes 1034.78A (0.95% deviation, within a derived 2% tolerance). Modeling assumptions: steady-state only (no transient/thermal-inertia modeling); `solar_altitude_deg` is a single fixed run-level value, not computed from time-of-day; `T_c` fixed at `conductor.T_max`, not solved iteratively.

## C6 — Grid Load Integration (ERCOT)
- source: docs/data-science/specs/C6-grid-load-integration.md
- type: api-contract
- content: `backend/ercot_data_retriever.py::pull_ercot_data(start, end)` — pulls via `gridstatus` library, sums ERCOT zone columns matching "WEST". `backend/ercot_dlr_merger.py::amps_to_mw(amps, voltage_kv, pf) -> float` — `P = sqrt(3) * V * I * pf / 1000`; defaults `LINE_VOLTAGE_KV = 345.0`, `POWER_FACTOR = 0.95`. `process_dlr_to_hourly(dlr_csv_path)` resamples 5-min DLR data to 1-hour bins, `.min()` for `dlr_amps` (worst-case-within-hour), `.mean()` for wind/temp. Output `merged_ercot_dlr_{stid}.csv` columns: `dlr_capacity_mw`, `static_capacity_mw`, `ercot_west_load_mw`, `datetime_utc` (MW subset of `PIPELINE_SCHEMA`). Known issue: `pull_ercot_data`'s live ERCOT path is currently non-functional — deterministic `Bad CRC-32` error in `gridstatus`'s own archive download/decompression, not this project's code. "Stress %" metric is explicitly labeled a simplified illustrative metric, not a real per-line utilization number.

## C7 — Safety Monitor & Fallback
- source: docs/data-science/specs/C7-safety-monitor.md
- type: protocol
- content: `backend/DLRSafetyMonitor.py::DLRSafetyMonitor(static_rating, logger=None)`. `run_check(raw_data: dict) -> dict` returns `{status, rating, fallback, alerts}`. Gate sequence: G1 sensor availability (fallback→`last_good_rating` on fail), G2 communication link (fallback→`last_good_rating`), G3 range validation — wind∈[0,50]m/s, temp∈[-20,60]°C, solar∈[0,1400]W/m² (fallback→`static_rating`), G4 ampacity plausibility — computed rating∈[400,1800]A (fallback→`static_rating`), G5 delta check — |rating−last_good_rating|≤150A (not a fallback, appends alert only). `_compute_ampacity` uses a placeholder linear formula (`900 + wind*30 - (temp-20)*4 - solar*0.05`), explicitly commented "Simplified IEEE 738 — replace with your full thermal model" — **does not call C5's `ieee738_ampacity`**. This is the concrete implementation of the project's fail-safe-by-default ethical commitment (per `Project Definition.md`).

## C8 — Corridor Spatial Discretization
- source: docs/data-science/specs/C8-corridor-discretization.md
- type: protocol
- content: Not yet designed/implemented. Conceptual contract: a corridor definition (substation endpoints, lat/lon minimum), a discretization step (N points along the corridor), per-point weather (via C4) and per-point ampacity (via C5), and a reduction step — corridor-level rating = `min()` across points (same "weakest link" principle as C6's hourly `.min()` resampling, different axis: space vs. time). Closest existing artifact: `backend/station_explorer.py::CORRIDORS` — five hardcoded (lat, lon) tuples used only to rank nearby stations by proximity to a single reference point per corridor; this is explicitly NOT corridor discretization (no notion of a line, route, or multiple points along one).

## C9 — Ampacity Forecasting
- source: docs/data-science/specs/C9-ampacity-forecasting.md
- type: schema
- content: Not yet designed/implemented. Conceptual contract: features = historical weather (C4) + historical computed ampacity (C5) as a time series, likely lagged/rolling; target = future ampacity at a defined horizon; output should extend `PIPELINE_SCHEMA` (C2) with new forecast-specific columns (forecast horizon, confidence/uncertainty band) — to be added to `PIPELINE_SCHEMA` when designed, not restated elsewhere. Blocked by accumulated historical data volume, distinct from the component dependency graph itself.

## C10 — Learned Anomaly Detection
- source: docs/data-science/specs/C10-anomaly-detection.md
- type: protocol
- content: Not yet designed/implemented. Contract must be additive to C7's `run_check` result shape (`status`, `rating`, `fallback`, `alerts`), not a replacement of its interface — a learned anomaly signal should trigger the same fallback path C7 already implements, not a second parallel fallback mechanism. Hard-blocked by C7 (needs the gating framework and a correct ampacity computation to detect anomalies against).

## Pipeline Output Schema — v1
- source: docs/data-science/schema/pipeline_output_v1.md
- type: schema
- content: Describes the current exported CSV shape from `backend/dlr_pipeline.py::export_results` (`outputs/station_data/{file_prefix}_{stid}.csv`). Explicitly a subset of `PIPELINE_SCHEMA` (C2) — `dlr_capacity_mw`, `static_capacity_mw`, `ercot_west_load_mw` are NOT present in this export (added later by C6). 11 columns in order: `stid` (identifier, unvalidated), `datetime_utc` (identifier, unvalidated), `air_temp` (degC, [-20,60], required), `wind_speed` (m/s, [0,50], required), `wind_direction` (deg, [0,360], required), `wind_perp_ms` (m/s, [0,50], optional), `solar_radiation` (W/m², [0,1400], optional), `relative_humidity` (%, [0,100], optional), `dlr_amps` (A, [100,4000], optional), `dlr_headroom_pct` (%, derived, not schema-validated), `dlr_uplift_flag` (bool, derived, not schema-validated). Any change to this column list is a breaking change and should bump to `pipeline_output_v2.md`.

## Project Definition — Input/Output Specification
- source: docs/Project Definition.md
- type: schema
- content: I/O spec table for 4 Texas cities — Austin, Corpus Christi, Midland, El Paso. Per city: ambient temp range (°C), wind speed range (m/s), solar irradiance range (W/m²), worst-case static limit (A), new thermal limit (A), trusted duration (s). Austin: temp -5.50–41.70, wind 0.20–8.00, solar 0–563, static 800–3000A, new limit 800–4500A, trusted duration 10s. Corpus Christi: temp 1.40–37.10, wind 0.30–12.10, solar 0–579, static 1000–5000A, new limit 1000–7500A, duration 10s. Midland: temp -9.40–43.80, wind 0.20–11.70, solar 0–574, static 600–3000A, new limit 600–4500A, duration 10s. El Paso: temp -5.10–41.40, wind 0.20–13.50, solar 0–533, static 600–2300A, new limit 600–3450A, duration 20s.

## Project Definition — UI, Operating Environment & Performance Specifications
- source: docs/Project Definition.md
- type: nfr
- content: UI dashboard must follow HMI safety standards, ISO 9241 (clear/consistent/readable design), IEEE Std 2030.2, IEEE Std 1815 (DNP3), IEEE Std C37.118 (synchrophasor measurement). Mock-up dashboard: user selects from a preset list of locations in the database; system computes new dynamic thermal limit + trusted duration; displays current line sag and current weather condition. Operating environment: DLR software/UI operated centrally at a distribution center; requires stable network connection to ingest external weather data streams "from sensors or NOAA"; supported by power system simulation platforms (PSS/E or EMTP) for grid reliability evaluation; data processing pipelines (Python/Jupyter) preprocess incoming datasets, execute forecasting ML models, feed the UI dashboard. Performance: implement N-1 contingency checking (given failure of one of N components, remaining N-1 can compensate for missing load). Ethical/fail-safe commitment: strict fail-safe protocols — if weather data becomes unreliable, system defaults to static ratings to prevent clearance violations/thermal runaway; ethical duty to design fail-safe mechanisms against data interruption, hacking, or spoofing (false data injection).
