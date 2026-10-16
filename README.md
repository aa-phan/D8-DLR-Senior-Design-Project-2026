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
| AUSTIN | 2026-10-16 10:38 UTC (05:38 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1542.9 | ✓ 1501.7 | ✓ 1570.2 | unavailable | ✓ 1576.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T10:38:46.239636+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-16 10:40 UTC (05:40 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1522.1 | ✓ 1476.0 | ✓ 1519.8 | unavailable | ✓ 1252.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T10:40:13.918768+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-16 10:42 UTC (05:42 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1537.6 | ✓ 1136.7 | ✓ 1539.0 | unavailable | ✓ 1673.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T10:42:52.517261+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-16 10:41 UTC (05:41 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1845.0 | ✓ 1814.0 | ✓ 1868.6 | unavailable | ✓ 1795.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T10:41:26.336146+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

20 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 20 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:38 UTC (05:38 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1542.9 | ✓ 1501.7 | ✓ 1570.2 | unavailable | ✓ 1576.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T10:38:46.239636+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 05:00 UTC (00:00 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1537.8 | ✓ 1562.3 | ✓ 1589.8 | unavailable | ✓ 1292.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T05:00:51.260405+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 03:00 UTC (2026-10-15 22:00 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1547.0 | ✓ 1500.5 | ✓ 1589.8 | unavailable | ✓ 1267.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:00:43.193947+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 00:30 UTC (2026-10-15 19:30 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1409.8 | ✓ 1393.5 | ✓ 1463.9 | unavailable | ✓ 1297.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T00:30:42.196606+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 20:54 UTC (15:54 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1376.5 | ✓ 1352.2 | ✓ 1463.9 | unavailable | ✓ 1073.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T20:54:42.967738+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_15 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 20 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:38 UTC (05:38 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 3085.8 | ✓ 3003.5 | ✓ 3140.4 | unavailable | ✓ 3153.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 05:00 UTC (00:00 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3075.6 | ✓ 3124.5 | ✓ 3179.5 | unavailable | ✓ 2584.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 03:00 UTC (2026-10-15 22:00 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3094.0 | ✓ 3001.0 | ✓ 3179.5 | unavailable | ✓ 2535.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 00:30 UTC (2026-10-15 19:30 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2819.6 | ✓ 2787.1 | ✓ 2927.8 | unavailable | ✓ 2595.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 20:54 UTC (15:54 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2752.9 | ✓ 2704.3 | ✓ 2927.8 | unavailable | ✓ 2147.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

20 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 20 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:40 UTC (05:40 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1522.1 | ✓ 1476.0 | ✓ 1519.8 | unavailable | ✓ 1252.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T10:40:13.918768+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 05:01 UTC (00:01 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1475.5 | ✓ 1376.4 | ✓ 1495.9 | unavailable | ✓ 1314.1 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T05:01:15.914035+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 03:01 UTC (2026-10-15 22:01 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1474.6 | ✓ 1376.4 | ✓ 1495.9 | unavailable | ✓ 1385.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:01:05.158031+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 00:31 UTC (2026-10-15 19:31 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1041.7 | ✓ 1187.3 | ✓ 1075.1 | unavailable | ✓ 1572.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T00:31:14.668668+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 20:55 UTC (15:55 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1162.7 | ✓ 1263.4 | ✓ 1075.1 | unavailable | ✓ 1458.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T20:55:04.507153+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_15 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 20 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:40 UTC (05:40 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 3044.1 | ✓ 2952.1 | ✓ 3039.6 | unavailable | ✓ 2504.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 05:01 UTC (00:01 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2951.0 | ✓ 2752.7 | ✓ 2991.8 | unavailable | ✓ 2628.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 03:01 UTC (2026-10-15 22:01 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2949.3 | ✓ 2752.7 | ✓ 2991.8 | unavailable | ✓ 2770.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 00:31 UTC (2026-10-15 19:31 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2083.5 | ✓ 2374.6 | ✓ 2150.2 | unavailable | ✓ 3145.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 20:55 UTC (15:55 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2325.3 | ✓ 2526.8 | ✓ 2150.2 | unavailable | ✓ 2917.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

20 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 20 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:42 UTC (05:42 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1537.6 | ✓ 1136.7 | ✓ 1539.0 | unavailable | ✓ 1673.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T10:42:52.517261+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 05:03 UTC (00:03 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1569.8 | ✓ 1589.8 | ✓ 1617.2 | unavailable | ✓ 1504.4 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T05:03:51.881844+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 03:03 UTC (2026-10-15 22:03 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1577.4 | ✓ 1589.8 | ✓ 1617.2 | unavailable | ✓ 1530.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:03:42.286056+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1616.3 | ✓ 1465.1 | ✓ 1717.5 | unavailable | ✓ 1498.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T00:32:44.987536+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 20:56 UTC (15:56 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1608.6 | ✓ 1490.2 | ✓ 1717.5 | unavailable | ✓ 1279.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T20:56:50.311286+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_15 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 20 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:42 UTC (05:42 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1537.6 | ✓ 1136.7 | ✓ 1539.0 | unavailable | ✓ 1673.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 05:03 UTC (00:03 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1569.8 | ✓ 1589.8 | ✓ 1617.2 | unavailable | ✓ 1504.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 03:03 UTC (2026-10-15 22:03 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1577.4 | ✓ 1589.8 | ✓ 1617.2 | unavailable | ✓ 1530.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1616.3 | ✓ 1465.1 | ✓ 1717.5 | unavailable | ✓ 1498.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 20:56 UTC (15:56 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1608.6 | ✓ 1490.2 | ✓ 1717.5 | unavailable | ✓ 1279.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

20 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 20 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:41 UTC (05:41 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 1845.0 | ✓ 1814.0 | ✓ 1868.6 | unavailable | ✓ 1795.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T10:41:26.336146+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 05:02 UTC (00:02 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2070.6 | ✓ 2105.3 | ✓ 2109.3 | unavailable | ✓ 1797.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T05:02:40.597801+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 03:02 UTC (2026-10-15 22:02 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2074.4 | ✓ 2105.3 | ✓ 2109.3 | unavailable | ✓ 1708.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:02:29.914194+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2023.9 | ✓ 2092.2 | ✓ 2072.1 | unavailable | ✓ 1685.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T00:32:24.835508+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 20:56 UTC (15:56 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2028.0 | ✓ 2092.2 | ✓ 2072.1 | unavailable | ✓ 1564.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T20:56:29.185921+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_15 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 20 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 10:41 UTC (05:41 CDT) | 2026-10-17 00:00 UTC (2026-10-16 19:00 CDT) | gfs_seamless | ✓ 3689.9 | ✓ 3628.1 | ✓ 3737.2 | unavailable | ✓ 3591.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 05:02 UTC (00:02 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 4141.3 | ✓ 4210.7 | ✓ 4218.7 | unavailable | ✓ 3595.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 03:02 UTC (2026-10-15 22:02 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 4148.7 | ✓ 4210.7 | ✓ 4218.7 | unavailable | ✓ 3415.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 4047.8 | ✓ 4184.3 | ✓ 4144.1 | unavailable | ✓ 3369.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 20:56 UTC (15:56 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 4056.1 | ✓ 4184.3 | ✓ 4144.1 | unavailable | ✓ 3128.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

