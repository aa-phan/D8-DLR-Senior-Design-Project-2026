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
| AUSTIN | 2026-10-16 03:00 UTC (2026-10-15 22:00 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1547.0 | ✓ 1500.5 | ✓ 1589.8 | unavailable | ✓ 1267.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:00:43.193947+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-16 03:01 UTC (2026-10-15 22:01 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1474.6 | ✓ 1376.4 | ✓ 1495.9 | unavailable | ✓ 1385.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:01:05.158031+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-16 03:03 UTC (2026-10-15 22:03 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1577.4 | ✓ 1589.8 | ✓ 1617.2 | unavailable | ✓ 1530.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:03:42.286056+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-16 03:02 UTC (2026-10-15 22:02 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2074.4 | ✓ 2105.3 | ✓ 2109.3 | unavailable | ✓ 1708.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:02:29.914194+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

## AUSTIN

18 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 18 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 03:00 UTC (2026-10-15 22:00 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1547.0 | ✓ 1500.5 | ✓ 1589.8 | unavailable | ✓ 1267.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:00:43.193947+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 00:30 UTC (2026-10-15 19:30 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1409.8 | ✓ 1393.5 | ✓ 1463.9 | unavailable | ✓ 1297.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T00:30:42.196606+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 20:54 UTC (15:54 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1376.5 | ✓ 1352.2 | ✓ 1463.9 | unavailable | ✓ 1073.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T20:54:42.967738+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 16:15 UTC (11:15 CDT) | 2026-10-16 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 977.5 | ✓ 1186.3 | ✓ 1199.8 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T16:15:53.484569+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history); r… |
| 2026-10-15 10:49 UTC (05:49 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | ✓ 1180.5 | ✓ 1155.9 | ✓ 1293.8 | unavailable | ✓ 1192.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T10:49:11.230486+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_13 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 18 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 03:00 UTC (2026-10-15 22:00 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 3094.0 | ✓ 3001.0 | ✓ 3179.5 | unavailable | ✓ 2535.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 00:30 UTC (2026-10-15 19:30 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2819.6 | ✓ 2787.1 | ✓ 2927.8 | unavailable | ✓ 2595.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 20:54 UTC (15:54 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2752.9 | ✓ 2704.3 | ✓ 2927.8 | unavailable | ✓ 2147.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 16:15 UTC (11:15 CDT) | 2026-10-16 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1955.0 | ✓ 2372.7 | ✓ 2399.6 | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: no ampacity available for this candidate |
| 2026-10-15 10:49 UTC (05:49 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | ✓ 2361.0 | ✓ 2311.8 | ✓ 2587.6 | unavailable | ✓ 2385.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

18 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 18 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 03:01 UTC (2026-10-15 22:01 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1474.6 | ✓ 1376.4 | ✓ 1495.9 | unavailable | ✓ 1385.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:01:05.158031+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 00:31 UTC (2026-10-15 19:31 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1041.7 | ✓ 1187.3 | ✓ 1075.1 | unavailable | ✓ 1572.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T00:31:14.668668+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 20:55 UTC (15:55 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1162.7 | ✓ 1263.4 | ✓ 1075.1 | unavailable | ✓ 1458.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T20:55:04.507153+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 16:16 UTC (11:16 CDT) | 2026-10-16 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 1487.2 | unavailable | unavailable | ml_wind_corrected: anchor unavailable for CORPUS_CHRISTI: fetch_live_anchor_observation: no usable wind observation for 'CORPUS_CHRISTI' at/before decision_time 2026-10-15 16:16:14.085183+00:00 within… |
| 2026-10-15 10:49 UTC (05:49 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | ✓ 1478.3 | ✓ 1410.2 | ✓ 1520.3 | unavailable | ✓ 1228.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T10:49:32.898282+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_13 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 18 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 03:01 UTC (2026-10-15 22:01 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2949.3 | ✓ 2752.7 | ✓ 2991.8 | unavailable | ✓ 2770.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 00:31 UTC (2026-10-15 19:31 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2083.5 | ✓ 2374.6 | ✓ 2150.2 | unavailable | ✓ 3145.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 20:55 UTC (15:55 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2325.3 | ✓ 2526.8 | ✓ 2150.2 | unavailable | ✓ 2917.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 16:16 UTC (11:16 CDT) | 2026-10-16 06:00 UTC (01:00 CDT) | gfs_seamless | unavailable | unavailable | ✓ 2974.4 | unavailable | unavailable | ml_wind_corrected: anchor unavailable for CORPUS_CHRISTI: fetch_live_anchor_observation: no usable wind observation for 'CORPUS_CHRISTI' at/before decision_time 2026-10-15 16:16:14.085183+00:00 within… |
| 2026-10-15 10:49 UTC (05:49 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | ✓ 2956.5 | ✓ 2820.3 | ✓ 3040.5 | unavailable | ✓ 2457.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

18 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 18 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 03:03 UTC (2026-10-15 22:03 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1577.4 | ✓ 1589.8 | ✓ 1617.2 | unavailable | ✓ 1530.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:03:42.286056+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1616.3 | ✓ 1465.1 | ✓ 1717.5 | unavailable | ✓ 1498.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T00:32:44.987536+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 20:56 UTC (15:56 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1608.6 | ✓ 1490.2 | ✓ 1717.5 | unavailable | ✓ 1279.8 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T20:56:50.311286+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 16:16 UTC (11:16 CDT) | 2026-10-16 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1551.3 | ✓ 1216.3 | ✓ 1721.9 | unavailable | ✓ 1483.9 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T16:16:54.356087+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 10:53 UTC (05:53 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | ✓ 1163.4 | ✓ 1017.4 | ✓ 1415.3 | unavailable | ✓ 1380.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T10:53:14.602639+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_13 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 18 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 03:03 UTC (2026-10-15 22:03 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 1577.4 | ✓ 1589.8 | ✓ 1617.2 | unavailable | ✓ 1530.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1616.3 | ✓ 1465.1 | ✓ 1717.5 | unavailable | ✓ 1498.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 20:56 UTC (15:56 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 1608.6 | ✓ 1490.2 | ✓ 1717.5 | unavailable | ✓ 1279.8 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 16:16 UTC (11:16 CDT) | 2026-10-16 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 1551.3 | ✓ 1216.3 | ✓ 1721.9 | unavailable | ✓ 1483.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 10:53 UTC (05:53 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | ✓ 1163.4 | ✓ 1017.4 | ✓ 1415.3 | unavailable | ✓ 1380.7 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## MIDLAND

18 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 5 of 18 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 03:02 UTC (2026-10-15 22:02 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 2074.4 | ✓ 2105.3 | ✓ 2109.3 | unavailable | ✓ 1708.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T03:02:29.914194+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2023.9 | ✓ 2092.2 | ✓ 2072.1 | unavailable | ✓ 1685.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-16T00:32:24.835508+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 20:56 UTC (15:56 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 2028.0 | ✓ 2092.2 | ✓ 2072.1 | unavailable | ✓ 1564.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T20:56:29.185921+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 16:16 UTC (11:16 CDT) | 2026-10-16 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 2028.6 | ✓ 2056.5 | ✓ 2055.9 | unavailable | ✓ 1601.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T16:16:33.967227+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |
| 2026-10-15 10:50 UTC (05:50 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | ✓ 1817.7 | ✓ 1818.2 | ✓ 1884.5 | unavailable | ✓ 1442.0 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-15T10:50:57.512483+00:00 produced by forecast model 'gfs_seamless' (cold start, or a gap in this city's collection history) |

_Rows in this city's log come from more than one NWP model (ecmwf_ifs, gfs_seamless); rows without a `forecast_model` field are `ecmwf_ifs` (before 2026-10-13). They are different series and must not be pooled when scoring._

_13 older cycle(s) omitted from this render -- still present, unpruned, in the raw `data/shadow/predictions/<CITY>.jsonl` file._

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 5 of 18 shown:

| Decision time | Valid time | NWP model | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| 2026-10-16 03:02 UTC (2026-10-15 22:02 CDT) | 2026-10-16 18:00 UTC (13:00 CDT) | gfs_seamless | ✓ 4148.7 | ✓ 4210.7 | ✓ 4218.7 | unavailable | ✓ 3415.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-16 00:32 UTC (2026-10-15 19:32 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 4047.8 | ✓ 4184.3 | ✓ 4144.1 | unavailable | ✓ 3369.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 20:56 UTC (15:56 CDT) | 2026-10-16 12:00 UTC (07:00 CDT) | gfs_seamless | ✓ 4056.1 | ✓ 4184.3 | ✓ 4144.1 | unavailable | ✓ 3128.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 16:16 UTC (11:16 CDT) | 2026-10-16 06:00 UTC (01:00 CDT) | gfs_seamless | ✓ 4057.2 | ✓ 4113.0 | ✓ 4111.8 | unavailable | ✓ 3203.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-15 10:50 UTC (05:50 CDT) | 2026-10-16 00:00 UTC (2026-10-15 19:00 CDT) | gfs_seamless | ✓ 3635.4 | ✓ 3636.5 | ✓ 3769.0 | unavailable | ✓ 2884.0 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

