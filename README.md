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
| AUSTIN | 2026-10-22 17:00 UTC (12:00 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 1095.1 | ✓ 1275.7 | unavailable | ml_wind_corrected: anchor unavailable for AUSTIN: fetch_live_anchor_observation: no usable wind observation for 'AUSTIN' at/before decision_time 2026-10-22 17:00:52.428418+00:00 within the 6.0h lookba… |
| CORPUS_CHRISTI | 2026-10-22 17:01 UTC (12:01 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1609.4 | ✓ 1614.0 | ✓ 1590.4 | ✓ 1676.0 | ✓ 1403.6 |  |
| EL_PASO | 2026-10-22 17:02 UTC (12:02 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1115.0 | ✓ 1368.9 | ✓ 1401.4 | ✓ 1499.7 | ✓ 1315.3 |  |
| MIDLAND | 2026-10-22 17:01 UTC (12:01 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1603.8 | ✓ 1605.3 | ✓ 1574.0 | ✓ 1398.3 | ✓ 1542.6 |  |

## AUSTIN

53 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 53 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 17:00 UTC (12:00 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 1095.1 | ✓ 1275.7 | unavailable | ml_wind_corrected: anchor unavailable for AUSTIN: fetch_live_anchor_observation: no usable wind observation for 'AUSTIN' at/before decision_time 2026-10-22 17:00:52.428418+00:00 within the 6.0h lookba… |
| 2026-10-22 11:00 UTC (06:00 CDT) | 2026-10-23 00:00 UTC (2026-10-22 19:00 CDT) | gfs_seamless | ✓ 1221.2 | ✓ 1189.4 | ✓ 1333.2 | ✓ 1135.3 | ✓ 1337.1 |  |
| 2026-10-22 05:00 UTC (00:00 CDT) | 2026-10-22 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1025.5 | ✓ 1235.0 | ✓ 1275.7 | ✓ 1102.4 | ✓ 1299.2 |  |
| 2026-10-21 23:00 UTC (18:00 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1096.9 | ✓ 1212.3 | ✓ 1135.3 | ✓ 1247.1 | ✓ 1257.8 |  |
| 2026-10-21 19:58 UTC (14:58 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1098.0 | ✓ 1225.5 | ✓ 1135.3 | unavailable | ✓ 1241.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T19:58:23.790637+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_48 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 53 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 17:00 UTC (12:00 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 2190.3 | ✓ 2551.4 | unavailable | ml_wind_corrected: anchor unavailable for AUSTIN: fetch_live_anchor_observation: no usable wind observation for 'AUSTIN' at/before decision_time 2026-10-22 17:00:52.428418+00:00 within the 6.0h lookba… |
| 2026-10-22 11:00 UTC (06:00 CDT) | 2026-10-23 00:00 UTC (2026-10-22 19:00 CDT) | gfs_seamless | ✓ 2442.4 | ✓ 2378.7 | ✓ 2666.4 | ✓ 2270.5 | ✓ 2674.3 |  |
| 2026-10-22 05:00 UTC (00:00 CDT) | 2026-10-22 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2050.9 | ✓ 2469.9 | ✓ 2551.4 | ✓ 2204.9 | ✓ 2598.4 |  |
| 2026-10-21 23:00 UTC (18:00 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2193.9 | ✓ 2424.5 | ✓ 2270.5 | ✓ 2494.2 | ✓ 2515.7 |  |
| 2026-10-21 19:58 UTC (14:58 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2196.0 | ✓ 2451.0 | ✓ 2270.5 | unavailable | ✓ 2482.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

53 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 53 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 17:01 UTC (12:01 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1609.4 | ✓ 1614.0 | ✓ 1590.4 | ✓ 1676.0 | ✓ 1403.6 |  |
| 2026-10-22 11:01 UTC (06:01 CDT) | 2026-10-23 00:00 UTC (2026-10-22 19:00 CDT) | gfs_seamless | ✓ 1586.6 | ✓ 1537.0 | ✓ 1666.1 | ✓ 1679.9 | ✓ 1269.4 |  |
| 2026-10-22 05:01 UTC (00:01 CDT) | 2026-10-22 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1560.3 | ✓ 1517.7 | ✓ 1676.0 | ✓ 1122.4 | ✓ 1398.2 |  |
| 2026-10-21 23:01 UTC (18:01 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1652.1 | ✓ 1651.6 | ✓ 1679.9 | ✓ 1636.7 | ✓ 1619.9 |  |
| 2026-10-21 19:59 UTC (14:59 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1674.6 | ✓ 1651.6 | ✓ 1679.9 | unavailable | ✓ 1557.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T19:59:51.181649+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_48 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 53 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 17:01 UTC (12:01 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3218.7 | ✓ 3228.1 | ✓ 3180.9 | ✓ 3351.9 | ✓ 2807.3 |  |
| 2026-10-22 11:01 UTC (06:01 CDT) | 2026-10-23 00:00 UTC (2026-10-22 19:00 CDT) | gfs_seamless | ✓ 3173.1 | ✓ 3074.0 | ✓ 3332.1 | ✓ 3359.9 | ✓ 2538.8 |  |
| 2026-10-22 05:01 UTC (00:01 CDT) | 2026-10-22 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3120.6 | ✓ 3035.5 | ✓ 3351.9 | ✓ 2244.7 | ✓ 2796.3 |  |
| 2026-10-21 23:01 UTC (18:01 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3304.2 | ✓ 3303.2 | ✓ 3359.9 | ✓ 3273.4 | ✓ 3239.9 |  |
| 2026-10-21 19:59 UTC (14:59 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3349.1 | ✓ 3303.2 | ✓ 3359.9 | unavailable | ✓ 3114.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

53 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 53 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 17:02 UTC (12:02 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1115.0 | ✓ 1368.9 | ✓ 1401.4 | ✓ 1499.7 | ✓ 1315.3 |  |
| 2026-10-22 11:04 UTC (06:04 CDT) | 2026-10-23 00:00 UTC (2026-10-22 19:00 CDT) | gfs_seamless | ✓ 1173.7 | ✓ 1228.2 | ✓ 1275.8 | ✓ 1139.3 | ✓ 1200.6 |  |
| 2026-10-22 05:03 UTC (00:03 CDT) | 2026-10-22 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1287.3 | ✓ 1339.5 | ✓ 1499.7 | ✓ 1146.1 | ✓ 1272.5 |  |
| 2026-10-21 23:03 UTC (18:03 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1234.0 | ✓ 1201.0 | ✓ 1139.3 | ✓ 1151.9 | ✓ 1220.5 |  |
| 2026-10-21 20:02 UTC (15:02 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1201.9 | ✓ 1184.1 | ✓ 1139.3 | unavailable | ✓ 1172.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T20:02:27.089117+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_48 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 53 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 17:02 UTC (12:02 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1115.0 | ✓ 1368.9 | ✓ 1401.4 | ✓ 1499.7 | ✓ 1315.3 |  |
| 2026-10-22 11:04 UTC (06:04 CDT) | 2026-10-23 00:00 UTC (2026-10-22 19:00 CDT) | gfs_seamless | ✓ 1173.7 | ✓ 1228.2 | ✓ 1275.8 | ✓ 1139.3 | ✓ 1200.6 |  |
| 2026-10-22 05:03 UTC (00:03 CDT) | 2026-10-22 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1287.3 | ✓ 1339.5 | ✓ 1499.7 | ✓ 1146.1 | ✓ 1272.5 |  |
| 2026-10-21 23:03 UTC (18:03 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1234.0 | ✓ 1201.0 | ✓ 1139.3 | ✓ 1151.9 | ✓ 1220.5 |  |
| 2026-10-21 20:02 UTC (15:02 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1201.9 | ✓ 1184.1 | ✓ 1139.3 | unavailable | ✓ 1172.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

53 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 53 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 17:01 UTC (12:01 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1603.8 | ✓ 1605.3 | ✓ 1574.0 | ✓ 1398.3 | ✓ 1542.6 |  |
| 2026-10-22 11:02 UTC (06:02 CDT) | 2026-10-23 00:00 UTC (2026-10-22 19:00 CDT) | gfs_seamless | ✓ 1484.4 | ✓ 1428.7 | ✓ 1454.4 | ✓ 1153.0 | ✓ 1517.6 |  |
| 2026-10-22 05:02 UTC (00:02 CDT) | 2026-10-22 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1410.5 | ✓ 1384.9 | ✓ 1398.3 | ✓ 1594.4 | ✓ 1592.1 |  |
| 2026-10-21 23:02 UTC (18:02 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1347.8 | ✓ 1332.7 | ✓ 1153.0 | ✓ 1241.4 | ✓ 1390.9 |  |
| 2026-10-21 20:01 UTC (15:01 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1333.1 | ✓ 1307.3 | ✓ 1153.0 | unavailable | ✓ 1333.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-21T20:01:02.675771+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_48 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 53 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-22 17:01 UTC (12:01 CDT) | 2026-10-23 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3207.7 | ✓ 3210.5 | ✓ 3148.0 | ✓ 2796.6 | ✓ 3085.2 |  |
| 2026-10-22 11:02 UTC (06:02 CDT) | 2026-10-23 00:00 UTC (2026-10-22 19:00 CDT) | gfs_seamless | ✓ 2968.8 | ✓ 2857.4 | ✓ 2908.8 | ✓ 2306.0 | ✓ 3035.3 |  |
| 2026-10-22 05:02 UTC (00:02 CDT) | 2026-10-22 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2821.0 | ✓ 2769.8 | ✓ 2796.6 | ✓ 3188.7 | ✓ 3184.2 |  |
| 2026-10-21 23:02 UTC (18:02 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2695.7 | ✓ 2665.4 | ✓ 2306.0 | ✓ 2482.7 | ✓ 2781.8 |  |
| 2026-10-21 20:01 UTC (15:01 CDT) | 2026-10-22 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2666.3 | ✓ 2614.6 | ✓ 2306.0 | unavailable | ✓ 2666.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


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

