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
| AUSTIN | 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1115.7 | ✓ 1145.4 | ✓ 1122.9 | unavailable | ✓ 1365.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:25:21.448975+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1277.8 | ✓ 1262.9 | ✓ 1206.3 | unavailable | ✓ 1441.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:25:42.902228+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-14 03:28 UTC (2026-10-13 22:28 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1178.0 | ✓ 1157.8 | ✓ 1262.5 | unavailable | ✓ 1270.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:28:18.005271+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-14 03:27 UTC (2026-10-13 22:27 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1668.7 | ✓ 1634.0 | ✓ 1630.8 | unavailable | ✓ 1524.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:27:07.171289+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

9 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 9 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1115.7 | ✓ 1145.4 | ✓ 1122.9 | unavailable | ✓ 1365.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:25:21.448975+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 00:24 UTC (2026-10-13 19:24 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1088.4 | ✓ 1153.8 | ✓ 1038.2 | unavailable | ✓ 1315.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T00:24:52.783308+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 18:50 UTC (13:50 CDT) | 2026-10-14 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1299.2 | ✓ 1264.3 | ✓ 1270.5 | unavailable | ✓ 1230.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T18:50:34.117064+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 07:12 UTC (02:12 CDT) | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) | gfs_seamless | ✓ 1180.1 | ✓ 1162.3 | ✓ 1177.8 | unavailable | ✓ 1153.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T07:12:58.943742+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 03:12 UTC (2026-10-12 22:12 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ecmwf_ifs | ✓ 1129.3 | ✓ 1181.3 | ✓ 1154.8 | unavailable | ✓ 1281.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:12:59.309036+00:00 (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_4 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 9 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2231.4 | ✓ 2290.9 | ✓ 2245.7 | unavailable | ✓ 2730.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 00:24 UTC (2026-10-13 19:24 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2176.7 | ✓ 2307.5 | ✓ 2076.4 | unavailable | ✓ 2630.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 18:50 UTC (13:50 CDT) | 2026-10-14 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2598.3 | ✓ 2528.6 | ✓ 2541.0 | unavailable | ✓ 2461.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 07:12 UTC (02:12 CDT) | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) | gfs_seamless | ✓ 2360.3 | ✓ 2324.5 | ✓ 2355.5 | unavailable | ✓ 2306.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 03:12 UTC (2026-10-12 22:12 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ecmwf_ifs | ✓ 2258.6 | ✓ 2362.6 | ✓ 2309.6 | unavailable | ✓ 2561.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

9 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 9 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1277.8 | ✓ 1262.9 | ✓ 1206.3 | unavailable | ✓ 1441.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:25:42.902228+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 00:25 UTC (2026-10-13 19:25 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1153.2 | ✓ 1166.9 | ✓ 1047.8 | unavailable | ✓ 1523.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T00:25:14.044782+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 18:52 UTC (13:52 CDT) | 2026-10-14 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1291.5 | ✓ 1325.4 | ✓ 1211.1 | unavailable | ✓ 1418.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T18:52:01.398773+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 07:14 UTC (02:14 CDT) | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) | gfs_seamless | ✓ 1434.9 | ✓ 1424.7 | ✓ 1419.7 | unavailable | ✓ 1246.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T07:14:27.574670+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 03:13 UTC (2026-10-12 22:13 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ecmwf_ifs | ✓ 1347.5 | ✓ 1316.4 | ✓ 1262.7 | unavailable | ✓ 1361.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:13:21.360037+00:00 (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_4 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 9 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2555.6 | ✓ 2525.7 | ✓ 2412.7 | unavailable | ✓ 2883.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 00:25 UTC (2026-10-13 19:25 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2306.3 | ✓ 2333.7 | ✓ 2095.5 | unavailable | ✓ 3047.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 18:52 UTC (13:52 CDT) | 2026-10-14 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2583.0 | ✓ 2650.7 | ✓ 2422.3 | unavailable | ✓ 2836.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 07:14 UTC (02:14 CDT) | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) | gfs_seamless | ✓ 2869.9 | ✓ 2849.4 | ✓ 2839.4 | unavailable | ✓ 2493.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 03:13 UTC (2026-10-12 22:13 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ecmwf_ifs | ✓ 2694.9 | ✓ 2632.8 | ✓ 2525.3 | unavailable | ✓ 2722.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

9 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 9 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-14 03:28 UTC (2026-10-13 22:28 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1178.0 | ✓ 1157.8 | ✓ 1262.5 | unavailable | ✓ 1270.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:28:18.005271+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 00:27 UTC (2026-10-13 19:27 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1124.4 | ✓ 1149.2 | ✓ 1172.0 | unavailable | ✓ 1302.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T00:27:47.942557+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 18:55 UTC (13:55 CDT) | 2026-10-14 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1287.9 | ✓ 1238.7 | ✓ 1342.4 | unavailable | ✓ 1186.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T18:55:45.582581+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 07:17 UTC (02:17 CDT) | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) | gfs_seamless | ✓ 1027.6 | ✓ 1154.8 | ✓ 1117.2 | unavailable | ✓ 1253.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T07:17:07.248824+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 03:15 UTC (2026-10-12 22:15 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ecmwf_ifs | ✓ 1047.3 | ✓ 1132.8 | ✓ 1083.6 | unavailable | ✓ 1269.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:15:06.870776+00:00 (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_4 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 9 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-14 03:28 UTC (2026-10-13 22:28 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1178.0 | ✓ 1157.8 | ✓ 1262.5 | unavailable | ✓ 1270.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 00:27 UTC (2026-10-13 19:27 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1124.4 | ✓ 1149.2 | ✓ 1172.0 | unavailable | ✓ 1302.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 18:55 UTC (13:55 CDT) | 2026-10-14 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1287.9 | ✓ 1238.7 | ✓ 1342.4 | unavailable | ✓ 1186.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 07:17 UTC (02:17 CDT) | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) | gfs_seamless | ✓ 1027.6 | ✓ 1154.8 | ✓ 1117.2 | unavailable | ✓ 1253.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 03:15 UTC (2026-10-12 22:15 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ecmwf_ifs | ✓ 1047.3 | ✓ 1132.8 | ✓ 1083.6 | unavailable | ✓ 1269.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

9 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 9 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-14 03:27 UTC (2026-10-13 22:27 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1668.7 | ✓ 1634.0 | ✓ 1630.8 | unavailable | ✓ 1524.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:27:07.171289+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 00:26 UTC (2026-10-13 19:26 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1554.2 | ✓ 1537.1 | ✓ 1467.9 | unavailable | ✓ 1440.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T00:26:37.718983+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 18:54 UTC (13:54 CDT) | 2026-10-14 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1748.8 | ✓ 1730.9 | ✓ 1768.6 | unavailable | ✓ 1425.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T18:54:18.154568+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 07:16 UTC (02:16 CDT) | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) | gfs_seamless | ✓ 1632.4 | ✓ 1594.9 | ✓ 1572.7 | unavailable | ✓ 1653.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T07:16:44.248862+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-13 03:14 UTC (2026-10-12 22:14 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ecmwf_ifs | ✓ 1778.0 | ✓ 1716.0 | ✓ 1750.0 | unavailable | ✓ 1624.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:14:45.952230+00:00 (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_4 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 9 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-14 03:27 UTC (2026-10-13 22:27 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3337.4 | ✓ 3267.9 | ✓ 3261.7 | unavailable | ✓ 3048.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 00:26 UTC (2026-10-13 19:26 CDT) | 2026-10-14 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3108.5 | ✓ 3074.2 | ✓ 2935.9 | unavailable | ✓ 2881.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 18:54 UTC (13:54 CDT) | 2026-10-14 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3497.6 | ✓ 3461.7 | ✓ 3537.1 | unavailable | ✓ 2850.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 07:16 UTC (02:16 CDT) | 2026-10-14 00:00 UTC (2026-10-13 19:00 CDT) | gfs_seamless | ✓ 3264.7 | ✓ 3189.9 | ✓ 3145.4 | unavailable | ✓ 3306.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 03:14 UTC (2026-10-12 22:14 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ecmwf_ifs | ✓ 3556.0 | ✓ 3432.0 | ✓ 3500.0 | unavailable | ✓ 3249.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

