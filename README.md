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
| AUSTIN | 2026-10-19 11:00 UTC (06:00 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1031.2 | ✓ 1131.9 | ✓ 1007.2 | unavailable | ✓ 1345.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T11:00:46.217315+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-19 11:02 UTC (06:02 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1655.1 | ✓ 1582.1 | ✓ 1790.6 | unavailable | ✓ 1275.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T11:02:13.080831+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-19 11:05 UTC (06:05 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1052.2 | ✓ 1377.4 | ✓ 1445.3 | unavailable | ✓ 1237.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T11:05:55.750943+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-19 11:03 UTC (06:03 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1552.2 | ✓ 1554.3 | ✓ 1528.7 | unavailable | ✓ 1569.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T11:03:39.317586+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

39 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 39 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 11:00 UTC (06:00 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1031.2 | ✓ 1131.9 | ✓ 1007.2 | unavailable | ✓ 1345.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T11:00:46.217315+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-19 05:00 UTC (00:00 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1066.0 | ✓ 1147.8 | ✓ 1285.1 | unavailable | ✓ 1294.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T05:00:47.979286+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 23:00 UTC (18:00 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1072.4 | ✓ 1230.6 | ✓ 1150.5 | unavailable | ✓ 1288.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T23:00:49.483469+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 17:00 UTC (12:00 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1090.2 | ✓ 1295.0 | ✓ 1180.8 | unavailable | ✓ 1302.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:00:42.286281+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 11:00 UTC (06:00 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1202.0 | ✓ 1230.9 | ✓ 1321.5 | unavailable | ✓ 1376.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T11:00:48.570978+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_34 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 39 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 11:00 UTC (06:00 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 2062.4 | ✓ 2263.8 | ✓ 2014.5 | unavailable | ✓ 2691.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-19 05:00 UTC (00:00 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2132.1 | ✓ 2295.6 | ✓ 2570.2 | unavailable | ✓ 2588.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 23:00 UTC (18:00 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2144.8 | ✓ 2461.1 | ✓ 2300.9 | unavailable | ✓ 2577.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 17:00 UTC (12:00 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2180.5 | ✓ 2590.1 | ✓ 2361.5 | unavailable | ✓ 2604.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 11:00 UTC (06:00 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 2404.1 | ✓ 2461.8 | ✓ 2643.0 | unavailable | ✓ 2751.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

39 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 39 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 11:02 UTC (06:02 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1655.1 | ✓ 1582.1 | ✓ 1790.6 | unavailable | ✓ 1275.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T11:02:13.080831+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-19 05:01 UTC (00:01 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1383.1 | ✓ 1418.4 | ✓ 1552.3 | unavailable | ✓ 1369.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T05:01:09.644015+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 23:01 UTC (18:01 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1549.3 | ✓ 1525.8 | ✓ 1663.3 | unavailable | ✓ 1501.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T23:01:10.806339+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 17:01 UTC (12:01 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1492.7 | ✓ 1564.5 | ✓ 1518.3 | unavailable | ✓ 1380.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:01:03.215607+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 11:02 UTC (06:02 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1188.9 | ✓ 1257.1 | ✓ 1126.5 | unavailable | ✓ 1357.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T11:02:15.852504+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_34 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 39 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 11:02 UTC (06:02 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 3310.2 | ✓ 3164.3 | ✓ 3581.1 | unavailable | ✓ 2550.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-19 05:01 UTC (00:01 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2766.1 | ✓ 2836.7 | ✓ 3104.7 | unavailable | ✓ 2739.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 23:01 UTC (18:01 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3098.5 | ✓ 3051.7 | ✓ 3326.5 | unavailable | ✓ 3003.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 17:01 UTC (12:01 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2985.4 | ✓ 3129.1 | ✓ 3036.6 | unavailable | ✓ 2759.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 11:02 UTC (06:02 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 2377.8 | ✓ 2514.1 | ✓ 2253.1 | unavailable | ✓ 2715.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

39 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 39 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 11:05 UTC (06:05 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1052.2 | ✓ 1377.4 | ✓ 1445.3 | unavailable | ✓ 1237.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T11:05:55.750943+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-19 05:03 UTC (00:03 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1084.3 | ✓ 1112.7 | ✓ 1101.7 | unavailable | ✓ 1248.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T05:03:45.246342+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 23:03 UTC (18:03 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1237.6 | ✓ 1123.3 | ✓ 1170.2 | unavailable | ✓ 1168.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T23:03:45.690853+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 17:03 UTC (12:03 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1125.0 | ✓ 1252.0 | ✓ 1155.2 | unavailable | ✓ 1245.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:03:37.507613+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 11:05 UTC (06:05 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1030.2 | ✓ 1221.3 | ✓ 1193.8 | unavailable | ✓ 1224.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T11:05:46.574898+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_34 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 39 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 11:05 UTC (06:05 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1052.2 | ✓ 1377.4 | ✓ 1445.3 | unavailable | ✓ 1237.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-19 05:03 UTC (00:03 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1084.3 | ✓ 1112.7 | ✓ 1101.7 | unavailable | ✓ 1248.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 23:03 UTC (18:03 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1237.6 | ✓ 1123.3 | ✓ 1170.2 | unavailable | ✓ 1168.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 17:03 UTC (12:03 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1125.0 | ✓ 1252.0 | ✓ 1155.2 | unavailable | ✓ 1245.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 11:05 UTC (06:05 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1030.2 | ✓ 1221.3 | ✓ 1193.8 | unavailable | ✓ 1224.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

39 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 39 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 11:03 UTC (06:03 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 1552.2 | ✓ 1554.3 | ✓ 1528.7 | unavailable | ✓ 1569.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T11:03:39.317586+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-19 05:02 UTC (00:02 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1547.9 | ✓ 1558.2 | ✓ 1535.3 | unavailable | ✓ 1616.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-19T05:02:34.092396+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 23:02 UTC (18:02 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1592.1 | ✓ 1575.6 | ✓ 1525.3 | unavailable | ✓ 1524.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T23:02:34.590447+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 17:02 UTC (12:02 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1733.7 | ✓ 1754.9 | ✓ 1718.9 | unavailable | ✓ 1602.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T17:02:26.844551+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-18 11:04 UTC (06:04 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 1570.5 | ✓ 1570.6 | ✓ 1546.8 | unavailable | ✓ 1564.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-18T11:04:32.511684+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_34 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 39 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 11:03 UTC (06:03 CDT) | 2026-10-20 00:00 UTC (2026-10-19 19:00 CDT) | gfs_seamless | ✓ 3104.3 | ✓ 3108.5 | ✓ 3057.5 | unavailable | ✓ 3138.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-19 05:02 UTC (00:02 CDT) | 2026-10-19 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3095.9 | ✓ 3116.4 | ✓ 3070.5 | unavailable | ✓ 3233.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 23:02 UTC (18:02 CDT) | 2026-10-19 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 3184.1 | ✓ 3151.3 | ✓ 3050.6 | unavailable | ✓ 3048.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 17:02 UTC (12:02 CDT) | 2026-10-19 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 3467.3 | ✓ 3509.8 | ✓ 3437.8 | unavailable | ✓ 3205.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-18 11:04 UTC (06:04 CDT) | 2026-10-19 00:00 UTC (2026-10-18 19:00 CDT) | gfs_seamless | ✓ 3141.0 | ✓ 3141.1 | ✓ 3093.6 | unavailable | ✓ 3129.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

