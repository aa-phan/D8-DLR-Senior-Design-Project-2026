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
wtm_dlr_pipeline.py
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
pip install requests pandas numpy scipy matplotlib rich
```

### 2 — Get a Synoptic API token

Register for a **free research token** at https://synopticdata.com/

```bash
export SYNOPTIC_TOKEN=your_token_here
```

### 3 — Discover stations near your corridors

```bash
python wtm_station_explorer.py
# → writes wtm_stations.csv with nearest-corridor ranking
```

### 4 — Run the DLR pipeline

Edit the bottom of `wtm_dlr_pipeline.py` to set:
- `TARGET_STATIONS`  — stids from the explorer output
- `START` / `END`    — analysis window (ISO-8601 UTC)
- `ConductorConfig`  — your actual conductor specs

```bash
python wtm_dlr_pipeline.py
# → writes dlr_results.csv + dlr_{STID}.png plots
```

---

## Key Parameters to Tune

| Parameter | Where | Notes |
|---|---|---|
| `line_azimuth` | `ConductorConfig` | Compass bearing of your line — critical for perpendicular wind |
| `max_temp_c` | `ConductorConfig` | ERCOT emergency rating limit (often 75–100°C for ACSR) |
| `resistance_ac` | `ConductorConfig` | From ACSR table at 25°C; look up by conductor code name |
| `static_rating` | `run_pipeline()` | Conventional normal/emergency rating to compare against |
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
| `dlr_results.csv` | Per-timestamp DLR, headroom %, uplift flag for each station |
| `dlr_{STID}.png` | 4-panel summary: DLR vs static, wind, temp, headroom histogram |
| `wtm_stations.csv` | Station metadata ranked by corridor proximity |

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
