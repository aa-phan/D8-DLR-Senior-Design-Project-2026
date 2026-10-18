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
| AUSTIN | 2026-10-18 17:00 UTC (12:00 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1090.2 | ✓ 1295.0 | ✓ 1180.8 | unavailable | ✓ 1302.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:00:42.286281+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-18 17:01 UTC (12:01 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1492.7 | ✓ 1564.5 | ✓ 1518.3 | unavailable | ✓ 1380.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:01:03.215607+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-18 17:03 UTC (12:03 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1125.0 | ✓ 1252.0 | ✓ 1155.2 | unavailable | ✓ 1245.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:03:37.507613+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-18 17:02 UTC (12:02 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1733.7 | ✓ 1754.9 | ✓ 1718.9 | unavailable | ✓ 1602.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:02:26.844551+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

36 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 36 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 17:00 UTC (12:00 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1090.2 | ✓ 1295.0 | ✓ 1180.8 | unavailable | ✓ 1302.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:00:42.286281+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 11:00 UTC (06:00 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1202.0 | ✓ 1230.9 | ✓ 1321.5 | unavailable | ✓ 1376.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T11:00:48.570978+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 05:00 UTC (00:00 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1088.4 | ✓ 1243.5 | ✓ 1258.2 | unavailable | ✓ 1327.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T05:00:50.429313+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 23:00 UTC (18:00 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1134.4 | ✓ 1276.4 | ✓ 1263.4 | unavailable | ✓ 1268.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:00:49.371281+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 20:03 UTC (15:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1216.2 | ✓ 1276.4 | ✓ 1263.4 | unavailable | ✓ 1281.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T20:03:54.925565+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_31 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 36 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 17:00 UTC (12:00 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2180.5 | ✓ 2590.1 | ✓ 2361.5 | unavailable | ✓ 2604.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 11:00 UTC (06:00 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 2404.1 | ✓ 2461.8 | ✓ 2643.0 | unavailable | ✓ 2751.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 05:00 UTC (00:00 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2176.8 | ✓ 2487.0 | ✓ 2516.3 | unavailable | ✓ 2655.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 23:00 UTC (18:00 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2268.7 | ✓ 2552.8 | ✓ 2526.8 | unavailable | ✓ 2537.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 20:03 UTC (15:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2432.4 | ✓ 2552.8 | ✓ 2526.8 | unavailable | ✓ 2563.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

36 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 36 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 17:01 UTC (12:01 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1492.7 | ✓ 1564.5 | ✓ 1518.3 | unavailable | ✓ 1380.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:01:03.215607+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 11:02 UTC (06:02 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1188.9 | ✓ 1257.1 | ✓ 1126.5 | unavailable | ✓ 1357.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T11:02:15.852504+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 05:01 UTC (00:01 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1199.1 | ✓ 1289.6 | ✓ 1268.2 | unavailable | ✓ 1376.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T05:01:12.590751+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 23:01 UTC (18:01 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1268.7 | ✓ 1251.9 | ✓ 1266.7 | unavailable | ✓ 1409.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:01:10.797917+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 20:04 UTC (15:04 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1283.7 | ✓ 1249.8 | ✓ 1266.7 | unavailable | ✓ 1436.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T20:04:16.107128+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_31 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 36 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 17:01 UTC (12:01 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2985.4 | ✓ 3129.1 | ✓ 3036.6 | unavailable | ✓ 2759.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 11:02 UTC (06:02 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 2377.8 | ✓ 2514.1 | ✓ 2253.1 | unavailable | ✓ 2715.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 05:01 UTC (00:01 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2398.2 | ✓ 2579.2 | ✓ 2536.4 | unavailable | ✓ 2753.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 23:01 UTC (18:01 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2537.5 | ✓ 2503.7 | ✓ 2533.4 | unavailable | ✓ 2818.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 20:04 UTC (15:04 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2567.4 | ✓ 2499.5 | ✓ 2533.4 | unavailable | ✓ 2872.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

36 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 36 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 17:03 UTC (12:03 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1125.0 | ✓ 1252.0 | ✓ 1155.2 | unavailable | ✓ 1245.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:03:37.507613+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 11:05 UTC (06:05 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1030.2 | ✓ 1221.3 | ✓ 1193.8 | unavailable | ✓ 1224.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T11:05:46.574898+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 05:03 UTC (00:03 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1131.6 | ✓ 1202.8 | ✓ 1268.2 | unavailable | ✓ 1261.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T05:03:48.438458+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 23:03 UTC (18:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1287.3 | ✓ 1273.7 | ✓ 1240.8 | unavailable | ✓ 1329.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:03:45.637351+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 20:06 UTC (15:06 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1341.3 | ✓ 1278.8 | ✓ 1240.8 | unavailable | ✓ 1333.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T20:06:50.445905+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_31 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 36 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 17:03 UTC (12:03 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1125.0 | ✓ 1252.0 | ✓ 1155.2 | unavailable | ✓ 1245.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 11:05 UTC (06:05 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1030.2 | ✓ 1221.3 | ✓ 1193.8 | unavailable | ✓ 1224.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 05:03 UTC (00:03 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1131.6 | ✓ 1202.8 | ✓ 1268.2 | unavailable | ✓ 1261.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 23:03 UTC (18:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1287.3 | ✓ 1273.7 | ✓ 1240.8 | unavailable | ✓ 1329.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 20:06 UTC (15:06 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1341.3 | ✓ 1278.8 | ✓ 1240.8 | unavailable | ✓ 1333.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

36 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 36 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 17:02 UTC (12:02 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1733.7 | ✓ 1754.9 | ✓ 1718.9 | unavailable | ✓ 1602.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:02:26.844551+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 11:04 UTC (06:04 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1570.5 | ✓ 1570.6 | ✓ 1546.8 | unavailable | ✓ 1564.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T11:04:32.511684+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 05:02 UTC (00:02 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1651.5 | ✓ 1648.0 | ✓ 1658.5 | unavailable | ✓ 1655.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T05:02:37.088700+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 23:02 UTC (18:02 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1575.8 | ✓ 1515.3 | ✓ 1549.9 | unavailable | ✓ 1543.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:02:34.751378+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 20:05 UTC (15:05 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1585.0 | ✓ 1567.1 | ✓ 1549.9 | unavailable | ✓ 1572.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T20:05:39.737589+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_31 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 36 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-18 17:02 UTC (12:02 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3467.3 | ✓ 3509.8 | ✓ 3437.8 | unavailable | ✓ 3205.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 11:04 UTC (06:04 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 3141.0 | ✓ 3141.1 | ✓ 3093.6 | unavailable | ✓ 3129.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 05:02 UTC (00:02 CDT) | 2026-10-18 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3302.9 | ✓ 3296.0 | ✓ 3317.0 | unavailable | ✓ 3311.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 23:02 UTC (18:02 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3151.7 | ✓ 3030.6 | ✓ 3099.7 | unavailable | ✓ 3086.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 20:05 UTC (15:05 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3170.1 | ✓ 3134.1 | ✓ 3099.7 | unavailable | ✓ 3144.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

