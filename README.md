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
| AUSTIN | 2026-11-08 06:00 UTC (00:00 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1165.2 | ✓ 1191.3 | ✓ 1165.4 | ✓ 1389.8 | ✓ 1328.1 |  |
| CORPUS_CHRISTI | 2026-11-08 06:01 UTC (00:01 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1856.0 | ✓ 1914.9 | ✓ 1982.8 | ✓ 1713.5 | unavailable | reference_ml_refit_24h: fetch_live_truth_proxy_series: city 'CORPUS_CHRISTI': solar-proxy (Open-Meteo historical forecast) window fetch failed after 2 attempt(s): HTTPSConnectionPool(host='historical-… |
| EL_PASO | 2026-11-08 06:05 UTC (00:05 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1293.7 | ✓ 1290.8 | ✓ 1372.4 | ✓ 1351.9 | ✓ 1313.1 |  |
| MIDLAND | 2026-11-08 06:03 UTC (00:03 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1298.1 | ✓ 1388.0 | ✓ 1376.4 | ✓ 1096.1 | ✓ 1686.9 |  |

## AUSTIN

119 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 119 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-08 06:00 UTC (00:00 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1165.2 | ✓ 1191.3 | ✓ 1165.4 | ✓ 1389.8 | ✓ 1328.1 |  |
| 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | 2026-11-08 12:00 UTC (06:00 CST) | gfs_seamless | ✓ 1345.5 | ✓ 1453.1 | ✓ 1551.0 | ✓ 1383.2 | ✓ 1311.3 |  |
| 2026-11-07 18:00 UTC (12:00 CST) | 2026-11-08 06:00 UTC (00:00 CST) | gfs_seamless | ✓ 1363.9 | ✓ 1352.2 | ✓ 1389.8 | ✓ 1422.1 | ✓ 1283.5 |  |
| 2026-11-07 12:00 UTC (06:00 CST) | 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | gfs_seamless | ✓ 1305.3 | ✓ 1339.3 | ✓ 1383.2 | ✓ 1200.6 | ✓ 1323.9 |  |
| 2026-11-07 06:00 UTC (00:00 CST) | 2026-11-07 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1213.3 | ✓ 1280.9 | ✓ 1422.1 | ✓ 1283.0 | ✓ 1258.4 |  |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_114 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 119 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-08 06:00 UTC (00:00 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 2330.3 | ✓ 2382.5 | ✓ 2330.8 | ✓ 2779.5 | ✓ 2656.2 |  |
| 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | 2026-11-08 12:00 UTC (06:00 CST) | gfs_seamless | ✓ 2691.1 | ✓ 2906.2 | ✓ 3101.9 | ✓ 2766.4 | ✓ 2622.5 |  |
| 2026-11-07 18:00 UTC (12:00 CST) | 2026-11-08 06:00 UTC (00:00 CST) | gfs_seamless | ✓ 2727.8 | ✓ 2704.4 | ✓ 2779.5 | ✓ 2844.1 | ✓ 2566.9 |  |
| 2026-11-07 12:00 UTC (06:00 CST) | 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | gfs_seamless | ✓ 2610.7 | ✓ 2678.7 | ✓ 2766.4 | ✓ 2401.3 | ✓ 2647.9 |  |
| 2026-11-07 06:00 UTC (00:00 CST) | 2026-11-07 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 2426.7 | ✓ 2561.8 | ✓ 2844.1 | ✓ 2565.9 | ✓ 2516.7 |  |


## CORPUS_CHRISTI

119 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 119 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-08 06:01 UTC (00:01 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1856.0 | ✓ 1914.9 | ✓ 1982.8 | ✓ 1713.5 | unavailable | reference_ml_refit_24h: fetch_live_truth_proxy_series: city 'CORPUS_CHRISTI': solar-proxy (Open-Meteo historical forecast) window fetch failed after 2 attempt(s): HTTPSConnectionPool(host='historical-… |
| 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | 2026-11-08 12:00 UTC (06:00 CST) | gfs_seamless | ✓ 1705.3 | ✓ 1680.8 | ✓ 1774.5 | ✓ 1766.7 | ✓ 1621.3 |  |
| 2026-11-07 18:01 UTC (12:01 CST) | 2026-11-08 06:00 UTC (00:00 CST) | gfs_seamless | ✓ 1702.1 | ✓ 1767.3 | ✓ 1713.5 | ✓ 1496.0 | ✓ 1430.2 |  |
| 2026-11-07 12:01 UTC (06:01 CST) | 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | gfs_seamless | ✓ 1653.7 | ✓ 1561.6 | ✓ 1766.7 | ✓ 1405.7 | ✓ 1336.6 |  |
| 2026-11-07 06:00 UTC (00:00 CST) | 2026-11-07 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1435.4 | ✓ 1478.4 | ✓ 1496.0 | ✓ 1432.8 | ✓ 1404.7 |  |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_114 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 119 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-08 06:01 UTC (00:01 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 3712.1 | ✓ 3829.8 | ✓ 3965.5 | ✓ 3426.9 | unavailable | reference_ml_refit_24h: no ampacity available for this candidate |
| 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | 2026-11-08 12:00 UTC (06:00 CST) | gfs_seamless | ✓ 3410.7 | ✓ 3361.6 | ✓ 3549.1 | ✓ 3533.4 | ✓ 3242.6 |  |
| 2026-11-07 18:01 UTC (12:01 CST) | 2026-11-08 06:00 UTC (00:00 CST) | gfs_seamless | ✓ 3404.3 | ✓ 3534.6 | ✓ 3426.9 | ✓ 2991.9 | ✓ 2860.4 |  |
| 2026-11-07 12:01 UTC (06:01 CST) | 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | gfs_seamless | ✓ 3307.4 | ✓ 3123.1 | ✓ 3533.4 | ✓ 2811.5 | ✓ 2673.1 |  |
| 2026-11-07 06:00 UTC (00:00 CST) | 2026-11-07 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 2870.8 | ✓ 2956.9 | ✓ 2991.9 | ✓ 2865.5 | ✓ 2809.5 |  |


## EL_PASO

119 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 119 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-08 06:05 UTC (00:05 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1293.7 | ✓ 1290.8 | ✓ 1372.4 | ✓ 1351.9 | ✓ 1313.1 |  |
| 2026-11-08 00:02 UTC (2026-11-07 18:02 CST) | 2026-11-08 12:00 UTC (06:00 CST) | gfs_seamless | ✓ 1229.2 | ✓ 1365.4 | ✓ 1404.3 | ✓ 1403.3 | unavailable | reference_ml_refit_24h: fetch_live_truth_proxy_series: city 'EL_PASO': required hour 2026-11-07T18:02:41.739400+00:00 unusable at both providers (tceq CAMS '41': no usable station row within tolerance… |
| 2026-11-07 18:03 UTC (12:03 CST) | 2026-11-08 06:00 UTC (00:00 CST) | gfs_seamless | ✓ 1182.7 | ✓ 1339.7 | ✓ 1351.9 | ✓ 1413.0 | ✓ 1357.7 |  |
| 2026-11-07 12:03 UTC (06:03 CST) | 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | gfs_seamless | ✓ 1252.6 | ✓ 1390.6 | ✓ 1403.3 | ✓ 1522.6 | ✓ 1346.2 |  |
| 2026-11-07 06:02 UTC (00:02 CST) | 2026-11-07 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1366.2 | ✓ 1128.5 | ✓ 1413.0 | ✓ 1646.0 | ✓ 1463.4 |  |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_114 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 119 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-08 06:05 UTC (00:05 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1293.7 | ✓ 1290.8 | ✓ 1372.4 | ✓ 1351.9 | ✓ 1313.1 |  |
| 2026-11-08 00:02 UTC (2026-11-07 18:02 CST) | 2026-11-08 12:00 UTC (06:00 CST) | gfs_seamless | ✓ 1229.2 | ✓ 1365.4 | ✓ 1404.3 | ✓ 1403.3 | unavailable | reference_ml_refit_24h: no ampacity available for this candidate |
| 2026-11-07 18:03 UTC (12:03 CST) | 2026-11-08 06:00 UTC (00:00 CST) | gfs_seamless | ✓ 1182.7 | ✓ 1339.7 | ✓ 1351.9 | ✓ 1413.0 | ✓ 1357.7 |  |
| 2026-11-07 12:03 UTC (06:03 CST) | 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | gfs_seamless | ✓ 1252.6 | ✓ 1390.6 | ✓ 1403.3 | ✓ 1522.6 | ✓ 1346.2 |  |
| 2026-11-07 06:02 UTC (00:02 CST) | 2026-11-07 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1366.2 | ✓ 1128.5 | ✓ 1413.0 | ✓ 1646.0 | ✓ 1463.4 |  |


## MIDLAND

119 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 119 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-08 06:03 UTC (00:03 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1298.1 | ✓ 1388.0 | ✓ 1376.4 | ✓ 1096.1 | ✓ 1686.9 |  |
| 2026-11-08 00:02 UTC (2026-11-07 18:02 CST) | 2026-11-08 12:00 UTC (06:00 CST) | gfs_seamless | ✓ 974.0 | ✓ 1248.6 | ✓ 1045.9 | ✓ 1642.0 | ✓ 1485.8 |  |
| 2026-11-07 18:02 UTC (12:02 CST) | 2026-11-08 06:00 UTC (00:00 CST) | gfs_seamless | ✓ 1064.1 | ✓ 1347.1 | ✓ 1096.1 | ✓ 1334.2 | ✓ 1481.2 |  |
| 2026-11-07 12:02 UTC (06:02 CST) | 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | gfs_seamless | ✓ 1577.8 | ✓ 1569.7 | ✓ 1642.0 | ✓ 1332.2 | ✓ 1601.9 |  |
| 2026-11-07 06:02 UTC (00:02 CST) | 2026-11-07 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 1216.6 | ✓ 1343.7 | ✓ 1334.2 | ✓ 1188.9 | ✓ 1643.0 |  |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_114 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 119 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-11-08 06:03 UTC (00:03 CST) | 2026-11-08 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 2596.2 | ✓ 2776.0 | ✓ 2752.8 | ✓ 2192.2 | ✓ 3373.7 |  |
| 2026-11-08 00:02 UTC (2026-11-07 18:02 CST) | 2026-11-08 12:00 UTC (06:00 CST) | gfs_seamless | ✓ 1947.9 | ✓ 2497.1 | ✓ 2091.7 | ✓ 3283.9 | ✓ 2971.6 |  |
| 2026-11-07 18:02 UTC (12:02 CST) | 2026-11-08 06:00 UTC (00:00 CST) | gfs_seamless | ✓ 2128.1 | ✓ 2694.2 | ✓ 2192.2 | ✓ 2668.3 | ✓ 2962.4 |  |
| 2026-11-07 12:02 UTC (06:02 CST) | 2026-11-08 00:00 UTC (2026-11-07 18:00 CST) | gfs_seamless | ✓ 3155.5 | ✓ 3139.5 | ✓ 3283.9 | ✓ 2664.4 | ✓ 3203.9 |  |
| 2026-11-07 06:02 UTC (00:02 CST) | 2026-11-07 18:00 UTC (12:00 CST) | gfs_seamless | ✓ 2433.2 | ✓ 2687.4 | ✓ 2668.3 | ✓ 2377.7 | ✓ 3286.0 |  |


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

