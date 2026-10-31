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
| AUSTIN | 2026-10-31 05:00 UTC (00:00 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 996.1 | ✓ 1194.8 | ✓ 1156.3 | ✓ 1398.4 | ✓ 1340.9 |  |
| CORPUS_CHRISTI | 2026-10-31 05:01 UTC (00:01 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1004.2 | ✓ 1138.5 | ✓ 1021.6 | ✓ 1690.0 | ✓ 1377.1 |  |
| EL_PASO | 2026-10-31 05:03 UTC (00:03 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1018.8 | ✓ 1097.5 | ✓ 1105.6 | ✓ 1214.1 | ✓ 1291.5 |  |
| MIDLAND | 2026-10-31 05:02 UTC (00:02 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1433.9 | ✓ 1351.7 | ✓ 1366.8 | ✓ 1566.4 | ✓ 1636.1 |  |

## AUSTIN

87 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 87 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-31 05:00 UTC (00:00 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 996.1 | ✓ 1194.8 | ✓ 1156.3 | ✓ 1398.4 | ✓ 1340.9 |  |
| 2026-10-30 23:00 UTC (18:00 CDT) | 2026-10-31 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1222.9 | ✓ 1290.2 | ✓ 1262.9 | ✓ 1169.1 | ✓ 1305.7 |  |
| 2026-10-30 17:00 UTC (12:00 CDT) | 2026-10-31 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1341.6 | ✓ 1355.0 | ✓ 1398.4 | ✓ 1389.9 | ✓ 1349.2 |  |
| 2026-10-30 11:00 UTC (06:00 CDT) | 2026-10-31 00:00 UTC (2026-10-30 19:00 CDT) | gfs_seamless | ✓ 1093.3 | ✓ 1142.8 | ✓ 1169.1 | ✓ 1208.3 | ✓ 1326.1 |  |
| 2026-10-30 05:00 UTC (00:00 CDT) | 2026-10-30 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1221.0 | ✓ 1342.6 | ✓ 1389.9 | ✓ 1349.4 | unavailable | reference_ml_refit_24h: fetch_live_truth_proxy_series: city 'AUSTIN': window fetch failed: HTTPSConnectionPool(host='www.tceq.texas.gov', port=443): Max retries exceeded with url: /cgi-bin/compliance/… |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_82 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 87 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-31 05:00 UTC (00:00 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1992.2 | ✓ 2389.6 | ✓ 2312.7 | ✓ 2796.7 | ✓ 2681.8 |  |
| 2026-10-30 23:00 UTC (18:00 CDT) | 2026-10-31 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2445.7 | ✓ 2580.4 | ✓ 2525.7 | ✓ 2338.3 | ✓ 2611.3 |  |
| 2026-10-30 17:00 UTC (12:00 CDT) | 2026-10-31 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2683.3 | ✓ 2710.0 | ✓ 2796.7 | ✓ 2779.9 | ✓ 2698.3 |  |
| 2026-10-30 11:00 UTC (06:00 CDT) | 2026-10-31 00:00 UTC (2026-10-30 19:00 CDT) | gfs_seamless | ✓ 2186.5 | ✓ 2285.5 | ✓ 2338.3 | ✓ 2416.7 | ✓ 2652.3 |  |
| 2026-10-30 05:00 UTC (00:00 CDT) | 2026-10-30 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2442.0 | ✓ 2685.3 | ✓ 2779.9 | ✓ 2698.8 | unavailable | reference_ml_refit_24h: no ampacity available for this candidate |


## CORPUS_CHRISTI

87 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 87 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-31 05:01 UTC (00:01 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1004.2 | ✓ 1138.5 | ✓ 1021.6 | ✓ 1690.0 | ✓ 1377.1 |  |
| 2026-10-30 23:01 UTC (18:01 CDT) | 2026-10-31 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 875.0 | ✓ 1304.0 | ✓ 1277.3 | ✓ 1495.9 | ✓ 1531.7 |  |
| 2026-10-30 17:03 UTC (12:03 CDT) | 2026-10-31 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1551.3 | ✓ 1392.3 | ✓ 1690.0 | ✓ 1625.0 | ✓ 1261.8 |  |
| 2026-10-30 11:01 UTC (06:01 CDT) | 2026-10-31 00:00 UTC (2026-10-30 19:00 CDT) | gfs_seamless | ✓ 1464.9 | ✓ 1448.5 | ✓ 1495.9 | ✓ 1361.1 | ✓ 1347.1 |  |
| 2026-10-30 05:00 UTC (00:00 CDT) | 2026-10-30 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1620.8 | ✓ 1608.8 | ✓ 1625.0 | ✓ 1483.8 | unavailable | reference_ml_refit_24h: fetch_live_truth_proxy_series: city 'CORPUS_CHRISTI': window fetch failed: HTTPSConnectionPool(host='www.tceq.texas.gov', port=443): Max retries exceeded with url: /cgi-bin/com… |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_82 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 87 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-31 05:01 UTC (00:01 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2008.3 | ✓ 2277.0 | ✓ 2043.2 | ✓ 3380.1 | ✓ 2754.1 |  |
| 2026-10-30 23:01 UTC (18:01 CDT) | 2026-10-31 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1750.1 | ✓ 2608.0 | ✓ 2554.6 | ✓ 2991.8 | ✓ 3063.3 |  |
| 2026-10-30 17:03 UTC (12:03 CDT) | 2026-10-31 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3102.6 | ✓ 2784.7 | ✓ 3380.1 | ✓ 3249.9 | ✓ 2523.7 |  |
| 2026-10-30 11:01 UTC (06:01 CDT) | 2026-10-31 00:00 UTC (2026-10-30 19:00 CDT) | gfs_seamless | ✓ 2929.7 | ✓ 2897.0 | ✓ 2991.8 | ✓ 2722.1 | ✓ 2694.2 |  |
| 2026-10-30 05:00 UTC (00:00 CDT) | 2026-10-30 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3241.7 | ✓ 3217.7 | ✓ 3249.9 | ✓ 2967.5 | unavailable | reference_ml_refit_24h: no ampacity available for this candidate |


## EL_PASO

87 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 87 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-31 05:03 UTC (00:03 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1018.8 | ✓ 1097.5 | ✓ 1105.6 | ✓ 1214.1 | ✓ 1291.5 |  |
| 2026-10-30 23:03 UTC (18:03 CDT) | 2026-10-31 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1125.7 | ✓ 1167.6 | ✓ 1163.6 | ✓ 972.7 | ✓ 1238.8 |  |
| 2026-10-30 17:05 UTC (12:05 CDT) | 2026-10-31 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1076.9 | ✓ 1192.9 | ✓ 1214.1 | ✓ 1344.2 | ✓ 1230.1 |  |
| 2026-10-30 11:03 UTC (06:03 CDT) | 2026-10-31 00:00 UTC (2026-10-30 19:00 CDT) | gfs_seamless | ✓ 909.4 | ✓ 1162.1 | ✓ 972.7 | ✓ 1151.1 | ✓ 1318.3 |  |
| 2026-10-30 05:02 UTC (00:02 CDT) | 2026-10-30 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1129.6 | ✓ 1017.5 | ✓ 1344.2 | ✓ 1246.4 | unavailable | reference_ml_refit_24h: fetch_live_truth_proxy_series: city 'EL_PASO': window fetch failed: HTTPSConnectionPool(host='www.tceq.texas.gov', port=443): Max retries exceeded with url: /cgi-bin/compliance… |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_82 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 87 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-31 05:03 UTC (00:03 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1018.8 | ✓ 1097.5 | ✓ 1105.6 | ✓ 1214.1 | ✓ 1291.5 |  |
| 2026-10-30 23:03 UTC (18:03 CDT) | 2026-10-31 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1125.7 | ✓ 1167.6 | ✓ 1163.6 | ✓ 972.7 | ✓ 1238.8 |  |
| 2026-10-30 17:05 UTC (12:05 CDT) | 2026-10-31 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1076.9 | ✓ 1192.9 | ✓ 1214.1 | ✓ 1344.2 | ✓ 1230.1 |  |
| 2026-10-30 11:03 UTC (06:03 CDT) | 2026-10-31 00:00 UTC (2026-10-30 19:00 CDT) | gfs_seamless | ✓ 909.4 | ✓ 1162.1 | ✓ 972.7 | ✓ 1151.1 | ✓ 1318.3 |  |
| 2026-10-30 05:02 UTC (00:02 CDT) | 2026-10-30 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1129.6 | ✓ 1017.5 | ✓ 1344.2 | ✓ 1246.4 | unavailable | reference_ml_refit_24h: no ampacity available for this candidate |


## MIDLAND

87 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 87 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-31 05:02 UTC (00:02 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1433.9 | ✓ 1351.7 | ✓ 1366.8 | ✓ 1566.4 | ✓ 1636.1 |  |
| 2026-10-30 23:02 UTC (18:02 CDT) | 2026-10-31 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1131.5 | ✓ 1229.6 | ✓ 920.6 | ✓ 1729.4 | ✓ 1518.2 |  |
| 2026-10-30 17:04 UTC (12:04 CDT) | 2026-10-31 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1603.3 | ✓ 1601.7 | ✓ 1566.4 | ✓ 1697.8 | ✓ 1513.1 |  |
| 2026-10-30 11:02 UTC (06:02 CDT) | 2026-10-31 00:00 UTC (2026-10-30 19:00 CDT) | gfs_seamless | ✓ 1735.4 | ✓ 1753.9 | ✓ 1729.4 | ✓ 1755.1 | ✓ 1605.1 |  |
| 2026-10-30 05:01 UTC (00:01 CDT) | 2026-10-30 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1714.6 | ✓ 1650.0 | ✓ 1697.8 | ✓ 1755.8 | unavailable | reference_ml_refit_24h: fetch_live_truth_proxy_series: city 'MIDLAND': window fetch failed: HTTPSConnectionPool(host='www.tceq.texas.gov', port=443): Max retries exceeded with url: /cgi-bin/compliance… |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_82 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 87 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-31 05:02 UTC (00:02 CDT) | 2026-10-31 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2867.8 | ✓ 2703.5 | ✓ 2733.7 | ✓ 3132.8 | ✓ 3272.2 |  |
| 2026-10-30 23:02 UTC (18:02 CDT) | 2026-10-31 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2263.0 | ✓ 2459.1 | ✓ 1841.2 | ✓ 3458.8 | ✓ 3036.5 |  |
| 2026-10-30 17:04 UTC (12:04 CDT) | 2026-10-31 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3206.5 | ✓ 3203.4 | ✓ 3132.8 | ✓ 3395.6 | ✓ 3026.2 |  |
| 2026-10-30 11:02 UTC (06:02 CDT) | 2026-10-31 00:00 UTC (2026-10-30 19:00 CDT) | gfs_seamless | ✓ 3470.9 | ✓ 3507.8 | ✓ 3458.8 | ✓ 3510.2 | ✓ 3210.3 |  |
| 2026-10-30 05:01 UTC (00:01 CDT) | 2026-10-30 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3429.1 | ✓ 3300.0 | ✓ 3395.6 | ✓ 3511.7 | unavailable | reference_ml_refit_24h: no ampacity available for this candidate |


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

