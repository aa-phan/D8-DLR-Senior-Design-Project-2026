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
| AUSTIN | 2026-10-21 05:00 UTC (00:00 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1150.8 | ✓ 1165.0 | ✓ 1337.8 | unavailable | ✓ 1311.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T05:00:49.695286+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-21 05:01 UTC (00:01 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1316.9 | ✓ 1416.2 | ✓ 1359.2 | unavailable | ✓ 1432.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T05:01:11.649654+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-21 05:03 UTC (00:03 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1075.7 | ✓ 1236.8 | ✓ 1258.7 | unavailable | ✓ 1359.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T05:03:47.998453+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-21 05:02 UTC (00:02 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1501.8 | ✓ 1492.6 | ✓ 1484.9 | unavailable | ✓ 1603.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T05:02:36.694120+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

46 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 46 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 05:00 UTC (00:00 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1150.8 | ✓ 1165.0 | ✓ 1337.8 | unavailable | ✓ 1311.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T05:00:49.695286+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 23:00 UTC (18:00 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1145.1 | ✓ 1270.1 | ✓ 1173.3 | unavailable | ✓ 1288.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T23:00:51.029567+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 17:00 UTC (12:00 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 1151.6 | unavailable | unavailable | ml_wind_corrected: anchor unavailable for AUSTIN: fetch_live_anchor_observation: no usable wind observation for 'AUSTIN' at/before decision_time 2026-10-20 17:00:56.097770+00:00 within the 6.0h lookba… |
| 2026-10-20 11:00 UTC (06:00 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | ✓ 1151.4 | ✓ 1294.1 | ✓ 1331.1 | unavailable | ✓ 1323.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T11:00:48.064469+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 05:00 UTC (00:00 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1125.7 | ✓ 1168.8 | ✓ 1326.9 | unavailable | ✓ 1360.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T05:00:48.927776+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_41 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 46 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 05:00 UTC (00:00 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2301.6 | ✓ 2330.1 | ✓ 2675.6 | unavailable | ✓ 2622.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 23:00 UTC (18:00 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2290.1 | ✓ 2540.2 | ✓ 2346.6 | unavailable | ✓ 2577.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 17:00 UTC (12:00 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 2303.3 | unavailable | unavailable | ml_wind_corrected: anchor unavailable for AUSTIN: fetch_live_anchor_observation: no usable wind observation for 'AUSTIN' at/before decision_time 2026-10-20 17:00:56.097770+00:00 within the 6.0h lookba… |
| 2026-10-20 11:00 UTC (06:00 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | ✓ 2302.7 | ✓ 2588.2 | ✓ 2662.3 | unavailable | ✓ 2647.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 05:00 UTC (00:00 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2251.3 | ✓ 2337.7 | ✓ 2653.7 | unavailable | ✓ 2721.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

46 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 46 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 05:01 UTC (00:01 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1316.9 | ✓ 1416.2 | ✓ 1359.2 | unavailable | ✓ 1432.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T05:01:11.649654+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 23:01 UTC (18:01 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1397.9 | ✓ 1358.5 | ✓ 1302.8 | unavailable | ✓ 1559.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T23:01:12.646843+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 17:01 UTC (12:01 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1572.7 | ✓ 1588.6 | ✓ 1630.2 | unavailable | ✓ 1440.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T17:01:17.304979+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 11:02 UTC (06:02 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | ✓ 1552.6 | ✓ 1520.3 | ✓ 1633.1 | unavailable | ✓ 1292.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T11:02:15.113773+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 05:01 UTC (00:01 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1305.9 | ✓ 1406.4 | ✓ 1346.0 | unavailable | ✓ 1401.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T05:01:14.004954+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_41 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 46 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 05:01 UTC (00:01 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2633.7 | ✓ 2832.4 | ✓ 2718.4 | unavailable | ✓ 2865.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 23:01 UTC (18:01 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2795.7 | ✓ 2717.0 | ✓ 2605.5 | unavailable | ✓ 3119.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 17:01 UTC (12:01 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3145.5 | ✓ 3177.1 | ✓ 3260.3 | unavailable | ✓ 2881.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 11:02 UTC (06:02 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | ✓ 3105.3 | ✓ 3040.6 | ✓ 3266.2 | unavailable | ✓ 2585.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 05:01 UTC (00:01 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2611.8 | ✓ 2812.8 | ✓ 2691.9 | unavailable | ✓ 2803.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

46 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 46 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 05:03 UTC (00:03 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1075.7 | ✓ 1236.8 | ✓ 1258.7 | unavailable | ✓ 1359.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T05:03:47.998453+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 23:03 UTC (18:03 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1197.8 | ✓ 1230.2 | ✓ 1183.2 | unavailable | ✓ 1320.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T23:03:48.247144+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 17:03 UTC (12:03 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1204.4 | ✓ 1286.0 | ✓ 1246.7 | unavailable | ✓ 1360.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T17:03:02.764700+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 11:04 UTC (06:04 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | unavailable | unavailable | unavailable | unavailable | ✓ 1350.2 | ml_wind_corrected: forecast unavailable for EL_PASO: fetch_live_forecast_for_valid_time: retrieval failed for city 'EL_PASO', run 2026-10-20 00:00:00+00:00 after 3 attempt(s): HTTPSConnectionPool(host… |
| 2026-10-20 05:03 UTC (00:03 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1069.0 | ✓ 1073.3 | ✓ 1104.9 | unavailable | ✓ 1341.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T05:03:50.418867+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_41 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 46 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 05:03 UTC (00:03 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1075.7 | ✓ 1236.8 | ✓ 1258.7 | unavailable | ✓ 1359.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 23:03 UTC (18:03 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1197.8 | ✓ 1230.2 | ✓ 1183.2 | unavailable | ✓ 1320.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 17:03 UTC (12:03 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1204.4 | ✓ 1286.0 | ✓ 1246.7 | unavailable | ✓ 1360.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 11:04 UTC (06:04 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | unavailable | unavailable | unavailable | unavailable | ✓ 1350.2 | ml_wind_corrected: forecast unavailable for EL_PASO: fetch_live_forecast_for_valid_time: retrieval failed for city 'EL_PASO', run 2026-10-20 00:00:00+00:00 after 3 attempt(s): HTTPSConnectionPool(host… |
| 2026-10-20 05:03 UTC (00:03 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1069.0 | ✓ 1073.3 | ✓ 1104.9 | unavailable | ✓ 1341.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

46 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 46 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 05:02 UTC (00:02 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1501.8 | ✓ 1492.6 | ✓ 1484.9 | unavailable | ✓ 1603.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T05:02:36.694120+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 23:02 UTC (18:02 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1432.1 | ✓ 1424.0 | ✓ 1283.5 | unavailable | ✓ 1480.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T23:02:36.918102+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 17:01 UTC (12:01 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1551.1 | ✓ 1543.2 | ✓ 1509.7 | unavailable | ✓ 1585.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T17:01:38.195637+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 11:03 UTC (06:03 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | ✓ 1578.1 | ✓ 1494.3 | ✓ 1562.8 | unavailable | ✓ 1576.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T11:03:27.844812+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-20 05:02 UTC (00:02 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1606.7 | ✓ 1616.1 | ✓ 1605.1 | unavailable | ✓ 1603.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-20T05:02:38.959332+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_41 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 46 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-21 05:02 UTC (00:02 CDT) | 2026-10-21 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3003.6 | ✓ 2985.1 | ✓ 2969.7 | unavailable | ✓ 3206.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 23:02 UTC (18:02 CDT) | 2026-10-21 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2864.3 | ✓ 2848.0 | ✓ 2567.0 | unavailable | ✓ 2959.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 17:01 UTC (12:01 CDT) | 2026-10-21 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3102.1 | ✓ 3086.4 | ✓ 3019.4 | unavailable | ✓ 3171.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 11:03 UTC (06:03 CDT) | 2026-10-21 00:00 UTC (2026-10-20 19:00 CDT) | gfs_seamless | ✓ 3156.2 | ✓ 2988.5 | ✓ 3125.6 | unavailable | ✓ 3153.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-20 05:02 UTC (00:02 CDT) | 2026-10-20 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3213.4 | ✓ 3232.2 | ✓ 3210.3 | unavailable | ✓ 3205.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

