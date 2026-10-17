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
| AUSTIN | 2026-10-17 23:00 UTC (18:00 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1134.4 | ✓ 1276.4 | ✓ 1263.4 | unavailable | ✓ 1268.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:00:49.371281+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-17 23:01 UTC (18:01 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1268.7 | ✓ 1251.9 | ✓ 1266.7 | unavailable | ✓ 1409.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:01:10.797917+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-17 23:03 UTC (18:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1287.3 | ✓ 1273.7 | ✓ 1240.8 | unavailable | ✓ 1329.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:03:45.637351+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-17 23:02 UTC (18:02 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1575.8 | ✓ 1515.3 | ✓ 1549.9 | unavailable | ✓ 1543.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:02:34.751378+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

33 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 33 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 23:00 UTC (18:00 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1134.4 | ✓ 1276.4 | ✓ 1263.4 | unavailable | ✓ 1268.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:00:49.371281+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 20:03 UTC (15:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1216.2 | ✓ 1276.4 | ✓ 1263.4 | unavailable | ✓ 1281.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T20:03:54.925565+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 17:00 UTC (12:00 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1156.6 | ✓ 1283.6 | ✓ 1184.8 | unavailable | ✓ 1310.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T17:00:43.440042+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 14:54 UTC (09:54 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1201.0 | ✓ 1306.6 | ✓ 1184.8 | unavailable | ✓ 1391.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T14:54:27.930987+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 11:00 UTC (06:00 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1349.7 | ✓ 1351.4 | ✓ 1413.5 | unavailable | ✓ 1399.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:00:44.365463+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_28 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 33 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 23:00 UTC (18:00 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2268.7 | ✓ 2552.8 | ✓ 2526.8 | unavailable | ✓ 2537.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 20:03 UTC (15:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2432.4 | ✓ 2552.8 | ✓ 2526.8 | unavailable | ✓ 2563.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 17:00 UTC (12:00 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2313.2 | ✓ 2567.3 | ✓ 2369.7 | unavailable | ✓ 2620.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 14:54 UTC (09:54 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2402.0 | ✓ 2613.2 | ✓ 2369.7 | unavailable | ✓ 2783.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 11:00 UTC (06:00 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2699.3 | ✓ 2702.8 | ✓ 2827.0 | unavailable | ✓ 2798.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

33 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 33 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 23:01 UTC (18:01 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1268.7 | ✓ 1251.9 | ✓ 1266.7 | unavailable | ✓ 1409.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:01:10.797917+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 20:04 UTC (15:04 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1283.7 | ✓ 1249.8 | ✓ 1266.7 | unavailable | ✓ 1436.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T20:04:16.107128+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 17:01 UTC (12:01 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1335.3 | ✓ 1357.9 | ✓ 1349.5 | unavailable | ✓ 1411.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T17:01:04.383086+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 14:54 UTC (09:54 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1309.8 | ✓ 1359.2 | ✓ 1349.5 | unavailable | ✓ 1437.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T14:54:48.584625+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 11:01 UTC (06:01 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1287.0 | ✓ 1365.2 | ✓ 1282.0 | unavailable | ✓ 1527.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:01:07.424429+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_28 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 33 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 23:01 UTC (18:01 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2537.5 | ✓ 2503.7 | ✓ 2533.4 | unavailable | ✓ 2818.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 20:04 UTC (15:04 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2567.4 | ✓ 2499.5 | ✓ 2533.4 | unavailable | ✓ 2872.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 17:01 UTC (12:01 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2670.7 | ✓ 2715.9 | ✓ 2698.9 | unavailable | ✓ 2822.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 14:54 UTC (09:54 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2619.7 | ✓ 2718.5 | ✓ 2698.9 | unavailable | ✓ 2875.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 11:01 UTC (06:01 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2574.0 | ✓ 2730.4 | ✓ 2563.9 | unavailable | ✓ 3054.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

33 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 33 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 23:03 UTC (18:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1287.3 | ✓ 1273.7 | ✓ 1240.8 | unavailable | ✓ 1329.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:03:45.637351+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 20:06 UTC (15:06 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1341.3 | ✓ 1278.8 | ✓ 1240.8 | unavailable | ✓ 1333.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T20:06:50.445905+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 17:02 UTC (12:02 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1312.1 | ✓ 1260.4 | ✓ 1272.3 | unavailable | ✓ 1307.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T17:02:49.197379+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 14:57 UTC (09:57 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1238.4 | ✓ 1260.4 | ✓ 1272.3 | unavailable | ✓ 1275.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T14:57:22.278013+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 11:03 UTC (06:03 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1248.2 | ✓ 1325.0 | ✓ 1538.2 | unavailable | ✓ 1285.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:03:45.029036+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_28 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 33 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 23:03 UTC (18:03 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1287.3 | ✓ 1273.7 | ✓ 1240.8 | unavailable | ✓ 1329.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 20:06 UTC (15:06 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1341.3 | ✓ 1278.8 | ✓ 1240.8 | unavailable | ✓ 1333.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 17:02 UTC (12:02 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1312.1 | ✓ 1260.4 | ✓ 1272.3 | unavailable | ✓ 1307.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 14:57 UTC (09:57 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1238.4 | ✓ 1260.4 | ✓ 1272.3 | unavailable | ✓ 1275.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 11:03 UTC (06:03 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1248.2 | ✓ 1325.0 | ✓ 1538.2 | unavailable | ✓ 1285.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

33 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 33 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 23:02 UTC (18:02 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1575.8 | ✓ 1515.3 | ✓ 1549.9 | unavailable | ✓ 1543.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T23:02:34.751378+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 20:05 UTC (15:05 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1585.0 | ✓ 1567.1 | ✓ 1549.9 | unavailable | ✓ 1572.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T20:05:39.737589+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 17:01 UTC (12:01 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1213.0 | ✓ 1357.1 | ✓ 1204.6 | unavailable | ✓ 1552.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T17:01:25.956397+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 14:56 UTC (09:56 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1183.8 | ✓ 1377.0 | ✓ 1204.6 | unavailable | ✓ 1579.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T14:56:12.062968+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-17 11:02 UTC (06:02 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 1129.0 | ✓ 1289.5 | ✓ 1150.4 | unavailable | ✓ 1580.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-17T11:02:32.688466+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_28 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 33 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-17 23:02 UTC (18:02 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3151.7 | ✓ 3030.6 | ✓ 3099.7 | unavailable | ✓ 3086.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 20:05 UTC (15:05 CDT) | 2026-10-18 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3170.1 | ✓ 3134.1 | ✓ 3099.7 | unavailable | ✓ 3144.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 17:01 UTC (12:01 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2426.0 | ✓ 2714.3 | ✓ 2409.2 | unavailable | ✓ 3105.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 14:56 UTC (09:56 CDT) | 2026-10-18 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2367.6 | ✓ 2753.9 | ✓ 2409.2 | unavailable | ✓ 3158.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-17 11:02 UTC (06:02 CDT) | 2026-10-18 00:00 UTC (2026-10-17 19:00 CDT) | gfs_seamless | ✓ 2257.9 | ✓ 2579.0 | ✓ 2300.7 | unavailable | ✓ 3160.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

