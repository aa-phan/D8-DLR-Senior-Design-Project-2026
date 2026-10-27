# Shadow Collection — Live Predictions

**Experimental/shadow prototype. Not field-validated operational safety data.** Every number here is a reanalysis-derived development comparison per this phase's own basis caveat -- see `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record.

> Static ratings are this project's own unverified per-conductor values (an owner-supplied 345 kV bundle average divided by the provisional subconductor count, 2026-10-13) -- explicitly flagged by the data-science team's own `C1-configuration.md` spec as "derived rather than independently sourced," and never confirmed for a specific line by the Power Systems sub-team. Do not treat a predicted ampacity below this number as a safety violation without that context.

**What the five candidates actually do.** All five answer the exact same question -- what will this city's ampacity be at the SAME future target time -- but differ in who does the forward-in-time extrapolation, and on what:

- **External-forecast-plus-local-physics** (`ml_wind_corrected`, `ml_cooling_corrected`, `raw_forecast`): the extrapolation of future WEATHER is done entirely by Open-Meteo's own independent NWP model. This project only transforms that already-future weather through IEEE 738 thermal physics (`raw_forecast`), or through that same physics plus a learned correction layer trained to reduce IEEE 738's own known bias (`ml_wind_corrected`/`ml_cooling_corrected`). This project does none of the weather extrapolation itself.
- **Self-contained statistical extrapolation** (`reference_ml_refit_24h`): no external forecast consulted at all. A model learns directly in ampacity-space, from this city's own recent lagged ampacity history plus the MOST RECENTLY OBSERVED (not forecast) weather, to extrapolate the next value. This project does 100% of the forward-looking work itself, with no outside NWP input.
- **No extrapolation at all** (`persistence_24h`): makes no new claim about how conditions evolve. It reuses -- unmodified -- this SAME collector's own `raw_forecast` prediction from ~24 hours ago for the matching target hour, betting only that today looks like yesterday at this same hour. What it reuses is itself a past FORECAST, never a sensor-measured observation -- this project has no sensor-measured ground truth anywhere in this pipeline.

See `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record this summary is drawn from.

Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.

## Latest cycle per city

| City | Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|---|
| AUSTIN | 2026-10-27 23:00 UTC (18:00 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1238.2 | ✓ 1303.2 | ✓ 1339.2 | ✓ 1183.7 | ✓ 1281.9 |  |
| CORPUS_CHRISTI | 2026-10-27 23:01 UTC (18:01 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1117.4 | ✓ 1176.4 | ✓ 973.3 | ✓ 1668.0 | ✓ 1531.2 |  |
| EL_PASO | 2026-10-27 23:03 UTC (18:03 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1131.4 | ✓ 1258.1 | ✓ 1329.3 | ✓ 1274.2 | ✓ 1240.6 |  |
| MIDLAND | 2026-10-27 23:02 UTC (18:02 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1867.0 | ✓ 1870.3 | ✓ 1830.9 | ✓ 1573.9 | ✓ 1528.1 |  |

## AUSTIN

74 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 74 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 23:00 UTC (18:00 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1238.2 | ✓ 1303.2 | ✓ 1339.2 | ✓ 1183.7 | ✓ 1281.9 |  |
| 2026-10-27 17:00 UTC (12:00 CDT) | 2026-10-28 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 887.9 | ✓ 1138.9 | unavailable | ml_wind_corrected: anchor unavailable for AUSTIN: fetch_live_anchor_observation: no usable wind observation for 'AUSTIN' at/before decision_time 2026-10-27 17:00:52.553190+00:00 within the 6.0h lookba… |
| 2026-10-27 11:00 UTC (06:00 CDT) | 2026-10-28 00:00 UTC (2026-10-27 19:00 CDT) | gfs_seamless | ✓ 1184.1 | ✓ 1105.9 | ✓ 1183.7 | ✓ 1011.3 | ✓ 1197.2 |  |
| 2026-10-27 05:00 UTC (00:00 CDT) | 2026-10-27 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1164.6 | ✓ 1145.8 | ✓ 1138.9 | ✓ 1069.0 | ✓ 1264.3 |  |
| 2026-10-26 23:00 UTC (18:00 CDT) | 2026-10-27 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 891.9 | ✓ 1160.9 | ✓ 1011.3 | ✓ 1310.3 | ✓ 1260.3 |  |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_69 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 74 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 23:00 UTC (18:00 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2476.3 | ✓ 2606.5 | ✓ 2678.3 | ✓ 2367.4 | ✓ 2563.9 |  |
| 2026-10-27 17:00 UTC (12:00 CDT) | 2026-10-28 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 1775.8 | ✓ 2277.9 | unavailable | ml_wind_corrected: anchor unavailable for AUSTIN: fetch_live_anchor_observation: no usable wind observation for 'AUSTIN' at/before decision_time 2026-10-27 17:00:52.553190+00:00 within the 6.0h lookba… |
| 2026-10-27 11:00 UTC (06:00 CDT) | 2026-10-28 00:00 UTC (2026-10-27 19:00 CDT) | gfs_seamless | ✓ 2368.3 | ✓ 2211.9 | ✓ 2367.4 | ✓ 2022.6 | ✓ 2394.5 |  |
| 2026-10-27 05:00 UTC (00:00 CDT) | 2026-10-27 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2329.1 | ✓ 2291.5 | ✓ 2277.9 | ✓ 2138.0 | ✓ 2528.6 |  |
| 2026-10-26 23:00 UTC (18:00 CDT) | 2026-10-27 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1783.8 | ✓ 2321.8 | ✓ 2022.6 | ✓ 2620.6 | ✓ 2520.6 |  |


## CORPUS_CHRISTI

74 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 74 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 23:01 UTC (18:01 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1117.4 | ✓ 1176.4 | ✓ 973.3 | ✓ 1668.0 | ✓ 1531.2 |  |
| 2026-10-27 17:01 UTC (12:01 CDT) | 2026-10-28 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1402.2 | ✓ 1330.5 | ✓ 1100.9 | ✓ 1129.9 | ✓ 1467.5 |  |
| 2026-10-27 11:02 UTC (06:02 CDT) | 2026-10-28 00:00 UTC (2026-10-27 19:00 CDT) | gfs_seamless | ✓ 1685.8 | ✓ 1736.8 | ✓ 1668.0 | ✓ 1395.6 | ✓ 1434.8 |  |
| 2026-10-27 05:01 UTC (00:01 CDT) | 2026-10-27 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1276.3 | ✓ 1247.5 | ✓ 1129.9 | ✓ 1496.1 | ✓ 1411.1 |  |
| 2026-10-26 23:01 UTC (18:01 CDT) | 2026-10-27 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1564.5 | ✓ 1441.6 | ✓ 1395.6 | ✓ 1772.3 | ✓ 1695.5 |  |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_69 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 74 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 23:01 UTC (18:01 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2234.9 | ✓ 2352.8 | ✓ 1946.6 | ✓ 3336.1 | ✓ 3062.4 |  |
| 2026-10-27 17:01 UTC (12:01 CDT) | 2026-10-28 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2804.4 | ✓ 2661.0 | ✓ 2201.8 | ✓ 2259.8 | ✓ 2934.9 |  |
| 2026-10-27 11:02 UTC (06:02 CDT) | 2026-10-28 00:00 UTC (2026-10-27 19:00 CDT) | gfs_seamless | ✓ 3371.7 | ✓ 3473.6 | ✓ 3336.1 | ✓ 2791.2 | ✓ 2869.7 |  |
| 2026-10-27 05:01 UTC (00:01 CDT) | 2026-10-27 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2552.5 | ✓ 2495.0 | ✓ 2259.8 | ✓ 2992.1 | ✓ 2822.2 |  |
| 2026-10-26 23:01 UTC (18:01 CDT) | 2026-10-27 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3128.9 | ✓ 2883.3 | ✓ 2791.2 | ✓ 3544.6 | ✓ 3391.0 |  |


## EL_PASO

74 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 74 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 23:03 UTC (18:03 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1131.4 | ✓ 1258.1 | ✓ 1329.3 | ✓ 1274.2 | ✓ 1240.6 |  |
| 2026-10-27 17:01 UTC (12:01 CDT) | 2026-10-28 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1245.1 | ✓ 1190.1 | ✓ 1025.1 | ✓ 1134.4 | ✓ 1125.5 |  |
| 2026-10-27 11:04 UTC (06:04 CDT) | 2026-10-28 00:00 UTC (2026-10-27 19:00 CDT) | gfs_seamless | ✓ 1064.7 | ✓ 1175.8 | ✓ 1274.2 | ✓ 1140.1 | ✓ 1163.7 |  |
| 2026-10-27 05:03 UTC (00:03 CDT) | 2026-10-27 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1019.2 | ✓ 1076.4 | ✓ 1134.4 | ✓ 1316.5 | ✓ 1252.9 |  |
| 2026-10-26 23:03 UTC (18:03 CDT) | 2026-10-27 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1152.0 | ✓ 1178.1 | ✓ 1140.1 | ✓ 1182.8 | ✓ 1246.3 |  |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_69 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 74 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 23:03 UTC (18:03 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1131.4 | ✓ 1258.1 | ✓ 1329.3 | ✓ 1274.2 | ✓ 1240.6 |  |
| 2026-10-27 17:01 UTC (12:01 CDT) | 2026-10-28 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1245.1 | ✓ 1190.1 | ✓ 1025.1 | ✓ 1134.4 | ✓ 1125.5 |  |
| 2026-10-27 11:04 UTC (06:04 CDT) | 2026-10-28 00:00 UTC (2026-10-27 19:00 CDT) | gfs_seamless | ✓ 1064.7 | ✓ 1175.8 | ✓ 1274.2 | ✓ 1140.1 | ✓ 1163.7 |  |
| 2026-10-27 05:03 UTC (00:03 CDT) | 2026-10-27 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1019.2 | ✓ 1076.4 | ✓ 1134.4 | ✓ 1316.5 | ✓ 1252.9 |  |
| 2026-10-26 23:03 UTC (18:03 CDT) | 2026-10-27 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1152.0 | ✓ 1178.1 | ✓ 1140.1 | ✓ 1182.8 | ✓ 1246.3 |  |


## MIDLAND

74 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 74 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 23:02 UTC (18:02 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1867.0 | ✓ 1870.3 | ✓ 1830.9 | ✓ 1573.9 | ✓ 1528.1 |  |
| 2026-10-27 17:01 UTC (12:01 CDT) | 2026-10-28 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1684.3 | ✓ 1715.4 | ✓ 1671.7 | ✓ 1723.4 | ✓ 1584.4 |  |
| 2026-10-27 11:03 UTC (06:03 CDT) | 2026-10-28 00:00 UTC (2026-10-27 19:00 CDT) | gfs_seamless | ✓ 1600.0 | ✓ 1596.0 | ✓ 1573.9 | ✓ 1312.2 | ✓ 1595.3 |  |
| 2026-10-27 05:02 UTC (00:02 CDT) | 2026-10-27 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1720.3 | ✓ 1626.8 | ✓ 1723.4 | ✓ 1415.9 | ✓ 1575.1 |  |
| 2026-10-26 23:02 UTC (18:02 CDT) | 2026-10-27 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1093.0 | ✓ 1422.0 | ✓ 1312.2 | ✓ 1499.7 | ✓ 1490.0 |  |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_69 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 74 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-27 23:02 UTC (18:02 CDT) | 2026-10-28 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3733.9 | ✓ 3740.6 | ✓ 3661.8 | ✓ 3147.8 | ✓ 3056.1 |  |
| 2026-10-27 17:01 UTC (12:01 CDT) | 2026-10-28 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3368.6 | ✓ 3430.8 | ✓ 3343.3 | ✓ 3446.8 | ✓ 3168.7 |  |
| 2026-10-27 11:03 UTC (06:03 CDT) | 2026-10-28 00:00 UTC (2026-10-27 19:00 CDT) | gfs_seamless | ✓ 3200.0 | ✓ 3192.1 | ✓ 3147.8 | ✓ 2624.4 | ✓ 3190.6 |  |
| 2026-10-27 05:02 UTC (00:02 CDT) | 2026-10-27 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3440.6 | ✓ 3253.7 | ✓ 3446.8 | ✓ 2831.7 | ✓ 3150.2 |  |
| 2026-10-26 23:02 UTC (18:02 CDT) | 2026-10-27 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2186.0 | ✓ 2844.0 | ✓ 2624.4 | ✓ 2999.5 | ✓ 2980.0 |  |


## Reconstructed persistence_24h (rows logged before 2026-10-21)

Before 2026-10-21 the collector ran against an empty log on the GitHub runner, so `persistence_24h` was logged `unavailable` (cold start) in every row. The values below are recomputed from this branch's logs each time this README renders, using the collector's own rule: the city's raw_forecast from the earlier row, same NWP model, whose valid time is closest to this row's decision time (within 90 minutes), looking only at rows logged before this one. They were not logged live and the JSONL rows are unchanged; rows with no match are omitted.

<details><summary>AUSTIN: 28 row(s)</summary>

| Decision time | Valid time | NWP model | persistence_24h (reconstructed) | Bundle (reconstructed) | Reused from row valid at |
|---|---|---|---|---|---|
| 2026-10-21 17:00 UTC (12:00 CDT) | 2026-10-22 06:00 UTC (01:00 CDT) | gfs_seamless | 1337.8 | ✓ 2675.6 | 2026-10-21 18:00 UTC (13:00 CDT) |
| 2026-10-21 11:00 UTC (06:00 CDT) | 2026-10-22 00:00 UTC (2026-10-21 19:00 CDT) | gfs_seamless | 1173.3 | ✓ 2346.6 | 2026-10-21 12:00 UTC (07:00 CDT) |
| 2026-10-21 05:00 UTC (00:00 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | 1151.6 | ✓ 2303.3 | 2026-10-21 06:00 UTC (01:00 CDT) |
| 2026-10-20 23:00 UTC (18:00 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | 1331.1 | ✓ 2662.3 | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) |
| 2026-10-20 17:00 UTC (12:00 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | 1326.9 | ✓ 2653.7 | 2026-10-20 18:00 UTC (13:00 CDT) |
| 2026-10-20 11:00 UTC (06:00 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | 1051.9 | ✓ 2103.8 | 2026-10-20 12:00 UTC (07:00 CDT) |
| 2026-10-20 05:00 UTC (00:00 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | 1226.1 | ✓ 2452.1 | 2026-10-20 06:00 UTC (01:00 CDT) |
| 2026-10-19 23:00 UTC (18:00 CDT) | 2026-10-20 12:00 UTC (07:00 CDT) | gfs_seamless | 1007.2 | ✓ 2014.5 | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) |
| 2026-10-19 17:00 UTC (12:00 CDT) | 2026-10-20 06:00 UTC (01:00 CDT) | gfs_seamless | 1285.1 | ✓ 2570.2 | 2026-10-19 18:00 UTC (13:00 CDT) |
| 2026-10-19 11:00 UTC (06:00 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | 1150.5 | ✓ 2300.9 | 2026-10-19 12:00 UTC (07:00 CDT) |
| 2026-10-19 05:00 UTC (00:00 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | 1180.8 | ✓ 2361.5 | 2026-10-19 06:00 UTC (01:00 CDT) |
| 2026-10-18 23:00 UTC (18:00 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | 1321.5 | ✓ 2643.0 | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) |
| 2026-10-18 17:00 UTC (12:00 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | 1258.2 | ✓ 2516.3 | 2026-10-18 18:00 UTC (13:00 CDT) |
| 2026-10-18 11:00 UTC (06:00 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | 1263.4 | ✓ 2526.8 | 2026-10-18 12:00 UTC (07:00 CDT) |
| 2026-10-18 05:00 UTC (00:00 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | 1184.8 | ✓ 2369.7 | 2026-10-18 06:00 UTC (01:00 CDT) |
| 2026-10-17 23:00 UTC (18:00 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | 1413.5 | ✓ 2827.0 | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) |
| 2026-10-17 17:00 UTC (12:00 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | 1422.2 | ✓ 2844.3 | 2026-10-17 18:00 UTC (13:00 CDT) |
| 2026-10-17 11:00 UTC (06:00 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | 1414.2 | ✓ 2828.4 | 2026-10-17 12:00 UTC (07:00 CDT) |
| 2026-10-17 05:00 UTC (00:00 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | 1495.9 | ✓ 2991.8 | 2026-10-17 06:00 UTC (01:00 CDT) |
| 2026-10-16 23:00 UTC (18:00 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | 1570.2 | ✓ 3140.4 | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) |
| 2026-10-16 17:00 UTC (12:00 CDT) | 2026-10-17 06:00 UTC (01:00 CDT) | gfs_seamless | 1589.8 | ✓ 3179.5 | 2026-10-16 18:00 UTC (13:00 CDT) |
| 2026-10-16 11:00 UTC (06:00 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | 1463.9 | ✓ 2927.8 | 2026-10-16 12:00 UTC (07:00 CDT) |
| 2026-10-16 10:38 UTC (05:38 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | 1463.9 | ✓ 2927.8 | 2026-10-16 12:00 UTC (07:00 CDT) |
| 2026-10-16 05:00 UTC (00:00 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | 1199.8 | ✓ 2399.6 | 2026-10-16 06:00 UTC (01:00 CDT) |
| 2026-10-16 00:30 UTC (2026-10-15 19:30 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | 1293.8 | ✓ 2587.6 | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) |
| 2026-10-15 10:49 UTC (05:49 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | 1144.5 | ✓ 2289.1 | 2026-10-15 12:00 UTC (07:00 CDT) |
| 2026-10-14 11:07 UTC (06:07 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | 1038.2 | ✓ 2076.4 | 2026-10-14 12:00 UTC (07:00 CDT) |
| 2026-10-14 00:24 UTC (2026-10-13 19:24 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | 1177.8 | ✓ 2355.5 | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) |

</details>

<details><summary>CORPUS_CHRISTI: 28 row(s)</summary>

| Decision time | Valid time | NWP model | persistence_24h (reconstructed) | Bundle (reconstructed) | Reused from row valid at |
|---|---|---|---|---|---|
| 2026-10-21 17:01 UTC (12:01 CDT) | 2026-10-22 06:00 UTC (01:00 CDT) | gfs_seamless | 1359.2 | ✓ 2718.4 | 2026-10-21 18:00 UTC (13:00 CDT) |
| 2026-10-21 11:02 UTC (06:02 CDT) | 2026-10-22 00:00 UTC (2026-10-21 19:00 CDT) | gfs_seamless | 1302.8 | ✓ 2605.5 | 2026-10-21 12:00 UTC (07:00 CDT) |
| 2026-10-21 05:01 UTC (00:01 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | 1630.2 | ✓ 3260.3 | 2026-10-21 06:00 UTC (01:00 CDT) |
| 2026-10-20 23:01 UTC (18:01 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | 1633.1 | ✓ 3266.2 | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) |
| 2026-10-20 17:01 UTC (12:01 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | 1346.0 | ✓ 2691.9 | 2026-10-20 18:00 UTC (13:00 CDT) |
| 2026-10-20 11:02 UTC (06:02 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | 1494.4 | ✓ 2988.9 | 2026-10-20 12:00 UTC (07:00 CDT) |
| 2026-10-20 05:01 UTC (00:01 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | 1742.4 | ✓ 3484.9 | 2026-10-20 06:00 UTC (01:00 CDT) |
| 2026-10-19 23:01 UTC (18:01 CDT) | 2026-10-20 12:00 UTC (07:00 CDT) | gfs_seamless | 1790.6 | ✓ 3581.1 | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) |
| 2026-10-19 17:02 UTC (12:02 CDT) | 2026-10-20 06:00 UTC (01:00 CDT) | gfs_seamless | 1552.3 | ✓ 3104.7 | 2026-10-19 18:00 UTC (13:00 CDT) |
| 2026-10-19 11:02 UTC (06:02 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | 1663.3 | ✓ 3326.5 | 2026-10-19 12:00 UTC (07:00 CDT) |
| 2026-10-19 05:01 UTC (00:01 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | 1518.3 | ✓ 3036.6 | 2026-10-19 06:00 UTC (01:00 CDT) |
| 2026-10-18 23:01 UTC (18:01 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | 1126.5 | ✓ 2253.1 | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) |
| 2026-10-18 17:01 UTC (12:01 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | 1268.2 | ✓ 2536.4 | 2026-10-18 18:00 UTC (13:00 CDT) |
| 2026-10-18 11:02 UTC (06:02 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | 1266.7 | ✓ 2533.4 | 2026-10-18 12:00 UTC (07:00 CDT) |
| 2026-10-18 05:01 UTC (00:01 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | 1349.5 | ✓ 2698.9 | 2026-10-18 06:00 UTC (01:00 CDT) |
| 2026-10-17 23:01 UTC (18:01 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | 1282.0 | ✓ 2563.9 | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) |
| 2026-10-17 17:01 UTC (12:01 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | 1396.9 | ✓ 2793.8 | 2026-10-17 18:00 UTC (13:00 CDT) |
| 2026-10-17 11:01 UTC (06:01 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | 1527.1 | ✓ 3054.1 | 2026-10-17 12:00 UTC (07:00 CDT) |
| 2026-10-17 05:02 UTC (00:02 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | 1543.0 | ✓ 3086.0 | 2026-10-17 06:00 UTC (01:00 CDT) |
| 2026-10-16 23:01 UTC (18:01 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | 1519.8 | ✓ 3039.6 | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) |
| 2026-10-16 17:02 UTC (12:02 CDT) | 2026-10-17 06:00 UTC (01:00 CDT) | gfs_seamless | 1495.9 | ✓ 2991.8 | 2026-10-16 18:00 UTC (13:00 CDT) |
| 2026-10-16 11:02 UTC (06:02 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | 1075.1 | ✓ 2150.2 | 2026-10-16 12:00 UTC (07:00 CDT) |
| 2026-10-16 10:40 UTC (05:40 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | 1075.1 | ✓ 2150.2 | 2026-10-16 12:00 UTC (07:00 CDT) |
| 2026-10-16 05:01 UTC (00:01 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | 1487.2 | ✓ 2974.4 | 2026-10-16 06:00 UTC (01:00 CDT) |
| 2026-10-16 00:31 UTC (2026-10-15 19:31 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | 1520.3 | ✓ 3040.5 | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) |
| 2026-10-15 10:49 UTC (05:49 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | 1265.9 | ✓ 2531.7 | 2026-10-15 12:00 UTC (07:00 CDT) |
| 2026-10-14 11:09 UTC (06:09 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | 1047.8 | ✓ 2095.5 | 2026-10-14 12:00 UTC (07:00 CDT) |
| 2026-10-14 00:25 UTC (2026-10-13 19:25 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | 1419.7 | ✓ 2839.4 | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) |

</details>

<details><summary>EL_PASO: 28 row(s)</summary>

| Decision time | Valid time | NWP model | persistence_24h (reconstructed) | Bundle (reconstructed) | Reused from row valid at |
|---|---|---|---|---|---|
| 2026-10-21 17:03 UTC (12:03 CDT) | 2026-10-22 06:00 UTC (01:00 CDT) | gfs_seamless | 1258.7 | ✓ 1258.7 | 2026-10-21 18:00 UTC (13:00 CDT) |
| 2026-10-21 11:04 UTC (06:04 CDT) | 2026-10-22 00:00 UTC (2026-10-21 19:00 CDT) | gfs_seamless | 1183.2 | ✓ 1183.2 | 2026-10-21 12:00 UTC (07:00 CDT) |
| 2026-10-21 05:03 UTC (00:03 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | 1246.7 | ✓ 1246.7 | 2026-10-21 06:00 UTC (01:00 CDT) |
| 2026-10-20 17:03 UTC (12:03 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | 1104.9 | ✓ 1104.9 | 2026-10-20 18:00 UTC (13:00 CDT) |
| 2026-10-20 11:04 UTC (06:04 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | 1164.0 | ✓ 1164.0 | 2026-10-20 12:00 UTC (07:00 CDT) |
| 2026-10-20 05:03 UTC (00:03 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | 1128.6 | ✓ 1128.6 | 2026-10-20 06:00 UTC (01:00 CDT) |
| 2026-10-19 23:03 UTC (18:03 CDT) | 2026-10-20 12:00 UTC (07:00 CDT) | gfs_seamless | 1445.3 | ✓ 1445.3 | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) |
| 2026-10-19 17:03 UTC (12:03 CDT) | 2026-10-20 06:00 UTC (01:00 CDT) | gfs_seamless | 1101.7 | ✓ 1101.7 | 2026-10-19 18:00 UTC (13:00 CDT) |
| 2026-10-19 11:05 UTC (06:05 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | 1170.2 | ✓ 1170.2 | 2026-10-19 12:00 UTC (07:00 CDT) |
| 2026-10-19 05:03 UTC (00:03 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | 1155.2 | ✓ 1155.2 | 2026-10-19 06:00 UTC (01:00 CDT) |
| 2026-10-18 23:03 UTC (18:03 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | 1193.8 | ✓ 1193.8 | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) |
| 2026-10-18 17:03 UTC (12:03 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | 1268.2 | ✓ 1268.2 | 2026-10-18 18:00 UTC (13:00 CDT) |
| 2026-10-18 11:05 UTC (06:05 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | 1240.8 | ✓ 1240.8 | 2026-10-18 12:00 UTC (07:00 CDT) |
| 2026-10-18 05:03 UTC (00:03 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | 1272.3 | ✓ 1272.3 | 2026-10-18 06:00 UTC (01:00 CDT) |
| 2026-10-17 23:03 UTC (18:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | 1538.2 | ✓ 1538.2 | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) |
| 2026-10-17 17:02 UTC (12:02 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | 1526.2 | ✓ 1526.2 | 2026-10-17 18:00 UTC (13:00 CDT) |
| 2026-10-17 11:03 UTC (06:03 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | 1531.7 | ✓ 1531.7 | 2026-10-17 12:00 UTC (07:00 CDT) |
| 2026-10-17 05:04 UTC (00:04 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | 1461.9 | ✓ 1461.9 | 2026-10-17 06:00 UTC (01:00 CDT) |
| 2026-10-16 23:03 UTC (18:03 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | 1539.0 | ✓ 1539.0 | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) |
| 2026-10-16 17:04 UTC (12:04 CDT) | 2026-10-17 06:00 UTC (01:00 CDT) | gfs_seamless | 1617.2 | ✓ 1617.2 | 2026-10-16 18:00 UTC (13:00 CDT) |
| 2026-10-16 11:06 UTC (06:06 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | 1717.5 | ✓ 1717.5 | 2026-10-16 12:00 UTC (07:00 CDT) |
| 2026-10-16 10:42 UTC (05:42 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | 1717.5 | ✓ 1717.5 | 2026-10-16 12:00 UTC (07:00 CDT) |
| 2026-10-16 05:03 UTC (00:03 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | 1721.9 | ✓ 1721.9 | 2026-10-16 06:00 UTC (01:00 CDT) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | 1415.3 | ✓ 1415.3 | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) |
| 2026-10-15 10:53 UTC (05:53 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | 1474.8 | ✓ 1474.8 | 2026-10-15 12:00 UTC (07:00 CDT) |
| 2026-10-14 16:31 UTC (11:31 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | 1262.5 | ✓ 1262.5 | 2026-10-14 18:00 UTC (13:00 CDT) |
| 2026-10-14 11:13 UTC (06:13 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | 1172.0 | ✓ 1172.0 | 2026-10-14 12:00 UTC (07:00 CDT) |
| 2026-10-14 00:27 UTC (2026-10-13 19:27 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | 1117.2 | ✓ 1117.2 | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) |

</details>

<details><summary>MIDLAND: 29 row(s)</summary>

| Decision time | Valid time | NWP model | persistence_24h (reconstructed) | Bundle (reconstructed) | Reused from row valid at |
|---|---|---|---|---|---|
| 2026-10-21 17:02 UTC (12:02 CDT) | 2026-10-22 06:00 UTC (01:00 CDT) | gfs_seamless | 1484.9 | ✓ 2969.7 | 2026-10-21 18:00 UTC (13:00 CDT) |
| 2026-10-21 11:03 UTC (06:03 CDT) | 2026-10-22 00:00 UTC (2026-10-21 19:00 CDT) | gfs_seamless | 1283.5 | ✓ 2567.0 | 2026-10-21 12:00 UTC (07:00 CDT) |
| 2026-10-21 05:02 UTC (00:02 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | 1509.7 | ✓ 3019.4 | 2026-10-21 06:00 UTC (01:00 CDT) |
| 2026-10-20 23:02 UTC (18:02 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | 1562.8 | ✓ 3125.6 | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) |
| 2026-10-20 17:01 UTC (12:01 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | 1605.1 | ✓ 3210.3 | 2026-10-20 18:00 UTC (13:00 CDT) |
| 2026-10-20 11:03 UTC (06:03 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | 1267.1 | ✓ 2534.2 | 2026-10-20 12:00 UTC (07:00 CDT) |
| 2026-10-20 05:02 UTC (00:02 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | 1510.5 | ✓ 3021.0 | 2026-10-20 06:00 UTC (01:00 CDT) |
| 2026-10-19 23:02 UTC (18:02 CDT) | 2026-10-20 12:00 UTC (07:00 CDT) | gfs_seamless | 1528.7 | ✓ 3057.5 | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) |
| 2026-10-19 17:02 UTC (12:02 CDT) | 2026-10-20 06:00 UTC (01:00 CDT) | gfs_seamless | 1535.3 | ✓ 3070.5 | 2026-10-19 18:00 UTC (13:00 CDT) |
| 2026-10-19 11:03 UTC (06:03 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | 1525.3 | ✓ 3050.6 | 2026-10-19 12:00 UTC (07:00 CDT) |
| 2026-10-19 05:02 UTC (00:02 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | 1718.9 | ✓ 3437.8 | 2026-10-19 06:00 UTC (01:00 CDT) |
| 2026-10-18 23:02 UTC (18:02 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | 1546.8 | ✓ 3093.6 | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) |
| 2026-10-18 17:02 UTC (12:02 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | 1658.5 | ✓ 3317.0 | 2026-10-18 18:00 UTC (13:00 CDT) |
| 2026-10-18 11:04 UTC (06:04 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | 1549.9 | ✓ 3099.7 | 2026-10-18 12:00 UTC (07:00 CDT) |
| 2026-10-18 05:02 UTC (00:02 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | 1204.6 | ✓ 2409.2 | 2026-10-18 06:00 UTC (01:00 CDT) |
| 2026-10-17 23:02 UTC (18:02 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | 1150.4 | ✓ 2300.7 | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) |
| 2026-10-17 17:01 UTC (12:01 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | 1352.7 | ✓ 2705.4 | 2026-10-17 18:00 UTC (13:00 CDT) |
| 2026-10-17 11:02 UTC (06:02 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | 1610.4 | ✓ 3220.8 | 2026-10-17 12:00 UTC (07:00 CDT) |
| 2026-10-17 05:03 UTC (00:03 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | 1555.8 | ✓ 3111.7 | 2026-10-17 06:00 UTC (01:00 CDT) |
| 2026-10-16 23:02 UTC (18:02 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | 1868.6 | ✓ 3737.2 | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) |
| 2026-10-16 17:03 UTC (12:03 CDT) | 2026-10-17 06:00 UTC (01:00 CDT) | gfs_seamless | 2109.3 | ✓ 4218.7 | 2026-10-16 18:00 UTC (13:00 CDT) |
| 2026-10-16 11:04 UTC (06:04 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | 2072.1 | ✓ 4144.1 | 2026-10-16 12:00 UTC (07:00 CDT) |
| 2026-10-16 10:41 UTC (05:41 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | 2072.1 | ✓ 4144.1 | 2026-10-16 12:00 UTC (07:00 CDT) |
| 2026-10-16 05:02 UTC (00:02 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | 2055.9 | ✓ 4111.8 | 2026-10-16 06:00 UTC (01:00 CDT) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | 1884.5 | ✓ 3769.0 | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) |
| 2026-10-15 10:50 UTC (05:50 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | 1793.5 | ✓ 3587.0 | 2026-10-15 12:00 UTC (07:00 CDT) |
| 2026-10-14 16:30 UTC (11:30 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | 1630.8 | ✓ 3261.7 | 2026-10-14 18:00 UTC (13:00 CDT) |
| 2026-10-14 11:11 UTC (06:11 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | 1467.9 | ✓ 2935.9 | 2026-10-14 12:00 UTC (07:00 CDT) |
| 2026-10-14 00:26 UTC (2026-10-13 19:26 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | 1572.7 | ✓ 3145.4 | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) |

</details>

_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

