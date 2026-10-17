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
| AUSTIN | 2026-10-17 11:00 UTC (06:00 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1349.7 | ✓ 1351.4 | ✓ 1413.5 | unavailable | ✓ 1399.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:00:44.365463+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-17 11:01 UTC (06:01 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1287.0 | ✓ 1365.2 | ✓ 1282.0 | unavailable | ✓ 1527.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:01:07.424429+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-17 11:03 UTC (06:03 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1248.2 | ✓ 1325.0 | ✓ 1538.2 | unavailable | ✓ 1285.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:03:45.029036+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-17 11:02 UTC (06:02 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1129.0 | ✓ 1289.5 | ✓ 1150.4 | unavailable | ✓ 1580.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:02:32.688466+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

29 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 29 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 11:00 UTC (06:00 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1349.7 | ✓ 1351.4 | ✓ 1413.5 | unavailable | ✓ 1399.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:00:44.365463+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 10:06 UTC (05:06 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1362.5 | ✓ 1318.9 | ✓ 1413.5 | unavailable | ✓ 1397.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T10:06:47.770867+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 05:00 UTC (00:00 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1284.5 | ✓ 1347.4 | ✓ 1422.2 | unavailable | ✓ 1423.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T05:00:48.819070+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 02:53 UTC (2026-10-16 21:53 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1350.9 | ✓ 1362.4 | ✓ 1422.2 | unavailable | ✓ 1487.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T02:53:04.266664+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 23:00 UTC (18:00 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1436.8 | ✓ 1384.0 | ✓ 1414.2 | unavailable | ✓ 1428.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T23:00:46.265030+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_24 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 29 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 11:00 UTC (06:00 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2699.3 | ✓ 2702.8 | ✓ 2827.0 | unavailable | ✓ 2798.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 10:06 UTC (05:06 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2725.0 | ✓ 2637.7 | ✓ 2827.0 | unavailable | ✓ 2794.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 05:00 UTC (00:00 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2569.1 | ✓ 2694.9 | ✓ 2844.3 | unavailable | ✓ 2847.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 02:53 UTC (2026-10-16 21:53 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2701.8 | ✓ 2724.8 | ✓ 2844.3 | unavailable | ✓ 2974.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 23:00 UTC (18:00 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2873.7 | ✓ 2768.0 | ✓ 2828.4 | unavailable | ✓ 2857.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

29 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 29 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 11:01 UTC (06:01 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1287.0 | ✓ 1365.2 | ✓ 1282.0 | unavailable | ✓ 1527.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:01:07.424429+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 10:07 UTC (05:07 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1283.5 | ✓ 1365.2 | ✓ 1282.0 | unavailable | ✓ 1485.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T10:07:09.956051+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 05:02 UTC (00:02 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1378.8 | ✓ 1427.5 | ✓ 1396.9 | unavailable | ✓ 1491.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T05:02:18.184535+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 02:53 UTC (2026-10-16 21:53 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1383.8 | ✓ 1460.0 | ✓ 1396.9 | unavailable | ✓ 1513.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T02:53:25.547630+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 23:01 UTC (18:01 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1540.9 | ✓ 1417.8 | ✓ 1527.1 | unavailable | ✓ 1520.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T23:01:07.171705+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_24 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 29 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 11:01 UTC (06:01 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2574.0 | ✓ 2730.4 | ✓ 2563.9 | unavailable | ✓ 3054.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 10:07 UTC (05:07 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2567.0 | ✓ 2730.4 | ✓ 2563.9 | unavailable | ✓ 2971.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 05:02 UTC (00:02 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2757.5 | ✓ 2854.9 | ✓ 2793.8 | unavailable | ✓ 2983.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 02:53 UTC (2026-10-16 21:53 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2767.5 | ✓ 2920.0 | ✓ 2793.8 | unavailable | ✓ 3027.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 23:01 UTC (18:01 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3081.8 | ✓ 2835.6 | ✓ 3054.1 | unavailable | ✓ 3041.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

29 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 29 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 11:03 UTC (06:03 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1248.2 | ✓ 1325.0 | ✓ 1538.2 | unavailable | ✓ 1285.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:03:45.029036+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 10:08 UTC (05:08 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1251.2 | ✓ 1349.0 | ✓ 1538.2 | unavailable | ✓ 1320.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T10:08:58.514030+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 05:04 UTC (00:04 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1402.3 | ✓ 1334.8 | ✓ 1526.2 | unavailable | ✓ 1326.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T05:04:53.024389+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 02:56 UTC (2026-10-16 21:56 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1415.1 | ✓ 1357.8 | ✓ 1526.2 | unavailable | ✓ 1324.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T02:56:00.132504+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 23:03 UTC (18:03 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1529.5 | ✓ 1388.1 | ✓ 1531.7 | unavailable | ✓ 1411.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T23:03:42.382498+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_24 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 29 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 11:03 UTC (06:03 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1248.2 | ✓ 1325.0 | ✓ 1538.2 | unavailable | ✓ 1285.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 10:08 UTC (05:08 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1251.2 | ✓ 1349.0 | ✓ 1538.2 | unavailable | ✓ 1320.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 05:04 UTC (00:04 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1402.3 | ✓ 1334.8 | ✓ 1526.2 | unavailable | ✓ 1326.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 02:56 UTC (2026-10-16 21:56 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1415.1 | ✓ 1357.8 | ✓ 1526.2 | unavailable | ✓ 1324.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 23:03 UTC (18:03 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1529.5 | ✓ 1388.1 | ✓ 1531.7 | unavailable | ✓ 1411.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

29 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 29 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 11:02 UTC (06:02 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1129.0 | ✓ 1289.5 | ✓ 1150.4 | unavailable | ✓ 1580.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:02:32.688466+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 10:07 UTC (05:07 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1128.9 | ✓ 1278.5 | ✓ 1150.4 | unavailable | ✓ 1577.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T10:07:33.686937+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 05:03 UTC (00:03 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1353.0 | ✓ 1391.3 | ✓ 1352.7 | unavailable | ✓ 1600.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T05:03:29.082513+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 02:54 UTC (2026-10-16 21:54 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1343.0 | ✓ 1389.3 | ✓ 1352.7 | unavailable | ✓ 1588.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T02:54:49.543517+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 23:02 UTC (18:02 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1551.0 | ✓ 1627.7 | ✓ 1610.4 | unavailable | ✓ 1694.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T23:02:31.396795+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_24 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 29 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 11:02 UTC (06:02 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2257.9 | ✓ 2579.0 | ✓ 2300.7 | unavailable | ✓ 3160.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 10:07 UTC (05:07 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2257.7 | ✓ 2557.1 | ✓ 2300.7 | unavailable | ✓ 3155.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 05:03 UTC (00:03 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2705.9 | ✓ 2782.7 | ✓ 2705.4 | unavailable | ✓ 3200.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 02:54 UTC (2026-10-16 21:54 CDT) | 2026-10-17 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2685.9 | ✓ 2778.6 | ✓ 2705.4 | unavailable | ✓ 3177.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 23:02 UTC (18:02 CDT) | 2026-10-17 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3102.1 | ✓ 3255.5 | ✓ 3220.8 | unavailable | ✓ 3389.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

