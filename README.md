# West Texas Mesonet → Dynamic Line Rating Pipeline

## Overview

This pipeline fetches 5-minute weather data from the **West Texas Mesonet (WTM)**
via the Synoptic Data API and computes **IEEE 738** conductor ampacity (dynamic line
ratings) for ERCOT transmission corridors.

---

## Architecture

```
Synoptic Data API
  └── WTM network (~168 stations, 5-min obs)
        │
        ▼
backend/dlr_pipeline.py
  ├── 1. Fetch timeseries  (air_temp, wind_speed, wind_dir, solar_rad, RH)
  ├── 2. Perpendicular wind component  (line azimuth projection)
  ├── 3. IEEE 738 heat balance  → ampacity (A)
  ├── 4. DLR headroom vs static rating
  └── 5. Export CSV + 4-panel plot
```

---

## Setup

### 1 — Install dependencies

```bash
pip install -r requirements.txt
```

### 2 — Get a Synoptic API token

Register for a **free research token** at https://synopticdata.com/

```bash
export SYNOPTIC_TOKEN=your_token_here
```

### 3 — Get an NREL/NLR developer API key (NSRDB solar data)

Register for a **free developer key** on the `developer.nlr.gov` developer portal
(the National Laboratory of the Rockies — the organization's institutional rename
of NREL; the old `developer.nrel.gov` hostname no longer resolves). NSRDB requires
a syntactically valid contact address on every request, and it must be the same
address the key was registered with. Put both in `.env` or your shell environment
— never in source:

```bash
export NREL_API_KEY=your_key_here
export NREL_API_EMAIL=your_registered_email@example.com
```

### 4 — Discover stations near your corridors

```bash
python backend/station_explorer.py
# → writes data/wtm_stations_austin.csv with nearest-corridor ranking
```

### 5 — Run the DLR pipeline

Edit the bottom of `backend/dlr_pipeline.py` to set:
- `TARGET_STATIONS`  — stids from the explorer output
- `START` / `END`    — analysis window (ISO-8601 UTC)
- `ConductorConfig`  — your actual conductor specs

```bash
python backend/dlr_pipeline.py
# → writes outputs/station_data/*.csv + outputs/station_plots/*.png
```

All commands are run from the repo root.

---

## Repository Layout

```
backend/    Data Science subsystem (this pipeline) — see docs/data-science/
  tests/    pytest suite + a standalone validation script (see docs/data-science/specs/C2-data-contract.md)
frontend/   UI dashboard — not started, see frontend/README.md
api/        Backend-for-frontend layer — not started, see api/README.md
data/       Checked-in reference inputs (station metadata)
outputs/    Generated pipeline output (gitignored)
docs/       data-science/ (PRD, roadmap, component specs) and frontend/ (PRD, roadmap, component specs F1–F8, developer guides)
```

---

## Key Parameters to Tune

| Parameter | Where | Notes |
|---|---|---|
| `line_azimuth` | `ConductorConfig` | Compass bearing of your line — critical for perpendicular wind |
| `max_temp_c` | `ConductorConfig` | ERCOT emergency rating limit (often 75–100°C for ACSR) |
| `resistance_ac` | `ConductorConfig` | From ACSR table at 25°C; look up by conductor code name |
| `city` | `run_pipeline()`, `plot_dlr_summary()` | Selects the per-city static rating from `config.STATIC_RATINGS` (e.g. `"AUSTIN"` at 1900 A); an omitted or unrecognised city falls back to `config.DEFAULT_STATIC_RATING` at 900 A |
| `solar_alt_deg` | `run_pipeline()` | Use seasonal midday average for your latitude |

---

## IEEE 738 Heat Balance Summary

```
Q_conv + Q_rad = I² × R(Tc) + Q_solar

Solve for I:
  I = sqrt( (Q_conv + Q_rad - Q_solar) / R(Tc) )
```

- **Q_conv** = forced + natural convection (dominant at wind > 0.5 m/s)
- **Q_rad** = radiative heat loss (significant at high conductor temps)
- **Q_solar** = solar heat gain (peaks ~200–400 W/m on exposed conductors)
- **R(Tc)** = conductor resistance at operating temperature Tc

---

## West Texas DLR Corridor Targets

| Corridor | Counties | Expected DLR Uplift |
|---|---|---|
| Panhandle Export | Lubbock, Crosby, Garza | High — persistent S/SW winds |
| Permian Basin 345 kV | Ector, Midland, Andrews | High — nightly thermal + wind |
| Sweetwater Wind Hub | Nolan, Mitchell | Very high — wind farm co-location |
| Big Spring | Howard, Glasscock | High |
| West TX → Hill Country | Tom Green, McCulloch | Moderate |

---

## Output Files

| File | Description |
|---|---|
| `outputs/station_data/*.csv` | Per-timestamp DLR, headroom %, uplift flag for each station |
| `outputs/station_plots/*.png` | 4-panel summary: DLR vs static, wind, temp, headroom histogram |
| `data/wtm_stations_austin.csv` | Station metadata ranked by corridor proximity |

---

## Next Steps

1. **Spatial interpolation**: Kriging or IDW between stations along a line segment
2. **Line segment mapping**: Assign stations to specific spans using GIS shapefiles
3. **Real-time mode**: Schedule hourly pulls → feed into SCADA or ADMS
4. **Probabilistic DLR**: Use wind direction uncertainty to compute 10th/50th/90th percentile ratings
5. **ERCOT integration**: Compare DLR headroom against day-ahead congestion reports

---

## References

- IEEE Std 738-2012: *Standard for Calculating the Current-Temperature Relationship of Bare Overhead Conductors*
- CIGRE TB 601: *Guide for Thermal Rating of Overhead Lines*
- Synoptic Data API docs: https://docs.synopticdata.com/
- WTM station info: https://www.mesonet.ttu.edu/

---

## For the Software Sub-Team (`frontend/` and `api/`)

`frontend/` (React) and `api/` (Flask) are structural placeholders with no code yet. This section orients you to what the Data Science backend already produces and where the software-side docs live.

### What the backend gives you

| Artifact | Location | Notes |
|---|---|---|
| Per-station DLR CSVs | `outputs/station_data/{file_prefix}_{stid}.csv` | Written by `backend/dlr_pipeline.py::export_results`. Gitignored, so you must run the pipeline (see Setup above) to generate them. |
| Output schema (v1) | `docs/data-science/schema/pipeline_output_v1.md` | Column names, units, valid ranges, and which columns are derived. Treat as the contract: any column change bumps it to `pipeline_output_v2.md`. |
| Sample fixture | `data/fixtures/sample_pipeline_output.csv` | One station (`AP140`), 10 rows at 5-minute cadence, matching the v1 schema exactly. Checked in, so you can build against it without a Synoptic or NREL key. |
| Station metadata | `data/wtm_stations_austin.csv`, `data/wtm_stations.csv` | Checked-in station reference data. |
| Merged ERCOT + DLR output | `outputs/ercot_data/merged_ercot_dlr_*.csv` | Adds MW capacity and ERCOT load columns on top of the v1 CSV (produced by `backend/ercot_dlr_merger.py`, see `docs/data-science/specs/C6-grid-load-integration.md`). Not part of the v1 schema. |
| Shadow forecast records | `data/shadow/predictions/*.jsonl` | Per-corridor forecast prediction logs from the shadow-mode forecast pipeline (`backend/forecast_shadow_pipeline.py`). Check the Data Science docs before depending on their shape. |

### Suggested way to start

1. Build against `data/fixtures/sample_pipeline_output.csv` first. Its column set is exactly what the pipeline exports, so no backend run is needed.
2. Read `docs/data-science/schema/pipeline_output_v1.md` for the meaning, units, and ranges of each of the 11 columns. In particular, `dlr_headroom_pct` and `dlr_uplift_flag` depend on the static rating the pipeline was run with (`backend/config.py`).
3. Decide with the team whether `api/` is a thin file-serving layer or a live-polling service (an open question noted in `api/README.md`), then document it in the PRD below before writing code.
4. Swap the fixture for real `outputs/station_data/*.csv` files once you have API keys and have run the pipeline.

Timestamps in the CSVs are UTC ISO-8601 strings (`datetime_utc`); convert to local time in the UI layer.

### Software-side documentation

- `docs/frontend/README.md` — documentation convention for the Software sub-team (PRD, roadmap, specs)
- `docs/frontend/PRD.md` — frontend and API requirements
- `docs/frontend/ROADMAP.md` — phased implementation order and dependencies
- `docs/frontend/specs/` — per-component specs
- `docs/frontend/guides/` — how-to guides (see the individual `*.md` files)
- `frontend/README.md` and `api/README.md` — code-side status of each subsystem

### Related project documents

- `docs/Project Definition.md` — what the dashboard is meant to accomplish
- `docs/System Design Report.md` — system design and Bill of Materials (Appendix E lists React and Flask)
- `docs/data-science/PRD.md` and `docs/data-science/ROADMAP.md` — the backend's requirements and plan
- `docs/data-science/specs/` — component specs (C1 to C10) for each backend module, including `C3-export-visualization.md` for the export this layer reads
