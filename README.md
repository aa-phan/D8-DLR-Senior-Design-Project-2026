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
| AUSTIN | 2026-10-15 03:03 UTC (2026-10-14 22:03 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 994.2 | ✓ 1062.6 | ✓ 1035.3 | unavailable | ✓ 1362.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T03:03:57.473325+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-15 03:04 UTC (2026-10-14 22:04 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1377.1 | ✓ 1383.0 | ✓ 1370.1 | unavailable | ✓ 1406.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T03:04:19.396854+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-15 03:05 UTC (2026-10-14 22:05 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1100.6 | ✓ 1490.2 | ✓ 1505.1 | unavailable | ✓ 1310.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T03:05:02.366298+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-15 03:04 UTC (2026-10-14 22:04 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1465.9 | ✓ 1354.5 | ✓ 1343.3 | unavailable | ✓ 1571.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T03:04:40.964391+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

13 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 13 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-15 03:03 UTC (2026-10-14 22:03 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 994.2 | ✓ 1062.6 | ✓ 1035.3 | unavailable | ✓ 1362.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T03:03:57.473325+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 21:16 UTC (16:16 CDT) | 2026-10-15 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1162.6 | ✓ 1206.0 | ✓ 1144.5 | unavailable | ✓ 1182.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T21:16:18.052503+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 16:28 UTC (11:28 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1165.7 | ✓ 1186.3 | ✓ 1137.9 | unavailable | ✓ 1276.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T16:28:32.809253+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 11:07 UTC (06:07 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | ✓ 1263.7 | ✓ 1341.8 | ✓ 1471.1 | unavailable | ✓ 1178.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T11:07:37.201239+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1115.7 | ✓ 1145.4 | ✓ 1122.9 | unavailable | ✓ 1365.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:25:21.448975+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_8 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 13 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-15 03:03 UTC (2026-10-14 22:03 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1988.4 | ✓ 2125.2 | ✓ 2070.7 | unavailable | ✓ 2723.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 21:16 UTC (16:16 CDT) | 2026-10-15 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2325.3 | ✓ 2412.1 | ✓ 2289.1 | unavailable | ✓ 2365.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 16:28 UTC (11:28 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2331.4 | ✓ 2372.5 | ✓ 2275.8 | unavailable | ✓ 2552.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 11:07 UTC (06:07 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | ✓ 2527.4 | ✓ 2683.5 | ✓ 2942.1 | unavailable | ✓ 2357.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2231.4 | ✓ 2290.9 | ✓ 2245.7 | unavailable | ✓ 2730.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

13 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 13 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-15 03:04 UTC (2026-10-14 22:04 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1377.1 | ✓ 1383.0 | ✓ 1370.1 | unavailable | ✓ 1406.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T03:04:19.396854+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 21:16 UTC (16:16 CDT) | 2026-10-15 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1368.9 | ✓ 1277.8 | ✓ 1265.9 | unavailable | ✓ 1457.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T21:16:39.707887+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 16:28 UTC (11:28 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1422.8 | ✓ 1412.4 | ✓ 1367.9 | unavailable | ✓ 1404.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T16:28:54.276100+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 11:09 UTC (06:09 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | ✓ 1475.2 | ✓ 1449.6 | ✓ 1447.7 | unavailable | ✓ 1210.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T11:09:04.349989+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1277.8 | ✓ 1262.9 | ✓ 1206.3 | unavailable | ✓ 1441.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:25:42.902228+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_8 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 13 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-15 03:04 UTC (2026-10-14 22:04 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2754.1 | ✓ 2766.0 | ✓ 2740.3 | unavailable | ✓ 2812.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 21:16 UTC (16:16 CDT) | 2026-10-15 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2737.7 | ✓ 2555.6 | ✓ 2531.7 | unavailable | ✓ 2915.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 16:28 UTC (11:28 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2845.7 | ✓ 2824.8 | ✓ 2735.7 | unavailable | ✓ 2808.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 11:09 UTC (06:09 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | ✓ 2950.3 | ✓ 2899.1 | ✓ 2895.4 | unavailable | ✓ 2421.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 03:25 UTC (2026-10-13 22:25 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2555.6 | ✓ 2525.7 | ✓ 2412.7 | unavailable | ✓ 2883.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

13 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 13 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-15 03:05 UTC (2026-10-14 22:05 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1100.6 | ✓ 1490.2 | ✓ 1505.1 | unavailable | ✓ 1310.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T03:05:02.366298+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 21:19 UTC (16:19 CDT) | 2026-10-15 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1400.4 | ✓ 1354.3 | ✓ 1474.8 | unavailable | ✓ 1218.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T21:19:14.840475+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 16:31 UTC (11:31 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1178.4 | ✓ 1234.6 | ✓ 1356.0 | unavailable | ✓ 1221.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T16:31:32.881189+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 11:13 UTC (06:13 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | ✓ 1151.7 | ✓ 1150.4 | ✓ 1228.8 | unavailable | ✓ 1195.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T11:13:37.110749+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 03:28 UTC (2026-10-13 22:28 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1178.0 | ✓ 1157.8 | ✓ 1262.5 | unavailable | ✓ 1270.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:28:18.005271+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_8 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 13 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-15 03:05 UTC (2026-10-14 22:05 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1100.6 | ✓ 1490.2 | ✓ 1505.1 | unavailable | ✓ 1310.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 21:19 UTC (16:19 CDT) | 2026-10-15 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1400.4 | ✓ 1354.3 | ✓ 1474.8 | unavailable | ✓ 1218.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 16:31 UTC (11:31 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1178.4 | ✓ 1234.6 | ✓ 1356.0 | unavailable | ✓ 1221.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 11:13 UTC (06:13 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | ✓ 1151.7 | ✓ 1150.4 | ✓ 1228.8 | unavailable | ✓ 1195.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 03:28 UTC (2026-10-13 22:28 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1178.0 | ✓ 1157.8 | ✓ 1262.5 | unavailable | ✓ 1270.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

13 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 13 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-15 03:04 UTC (2026-10-14 22:04 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1465.9 | ✓ 1354.5 | ✓ 1343.3 | unavailable | ✓ 1571.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T03:04:40.964391+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 21:18 UTC (16:18 CDT) | 2026-10-15 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1805.3 | failed | ✓ 1793.5 | unavailable | unavailable | ml_cooling_corrected: Input X contains NaN. GradientBoostingRegressor does not accept missing values encoded as NaN natively. For supervised learning, you might want to consider sklearn.ensemble.HistG… |
| 2026-10-14 16:30 UTC (11:30 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1806.4 | ✓ 1809.3 | ✓ 1798.6 | unavailable | ✓ 1468.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T16:30:18.257530+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 11:11 UTC (06:11 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | ✓ 1853.1 | ✓ 1755.7 | ✓ 1860.4 | unavailable | ✓ 1484.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T11:11:20.695516+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-14 03:27 UTC (2026-10-13 22:27 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1668.7 | ✓ 1634.0 | ✓ 1630.8 | unavailable | ✓ 1524.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-14T03:27:07.171289+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_8 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 13 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-15 03:04 UTC (2026-10-14 22:04 CDT) | 2026-10-15 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2931.8 | ✓ 2709.0 | ✓ 2686.7 | unavailable | ✓ 3142.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 21:18 UTC (16:18 CDT) | 2026-10-15 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3610.6 | unavailable | ✓ 3587.0 | unavailable | unavailable | ml_cooling_corrected: Input X contains NaN. GradientBoostingRegressor does not accept missing values encoded as NaN natively. For supervised learning, you might want to consider sklearn.ensemble.HistG… |
| 2026-10-14 16:30 UTC (11:30 CDT) | 2026-10-15 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3612.8 | ✓ 3618.5 | ✓ 3597.1 | unavailable | ✓ 2936.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 11:11 UTC (06:11 CDT) | 2026-10-15 00:00 UTC (2026-10-14 19:00 CDT) | gfs_seamless | ✓ 3706.2 | ✓ 3511.4 | ✓ 3720.9 | unavailable | ✓ 2969.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-14 03:27 UTC (2026-10-13 22:27 CDT) | 2026-10-14 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3337.4 | ✓ 3267.9 | ✓ 3261.7 | unavailable | ✓ 3048.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

