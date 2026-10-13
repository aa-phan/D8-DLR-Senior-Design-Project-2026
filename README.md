# Shadow Collection — Live Predictions

**Experimental/shadow prototype. Not field-validated operational safety data.** Every number here is a reanalysis-derived development comparison per this phase's own basis caveat -- see `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record.

> Static ratings are this project's own unverified placeholder (the midpoint of a *range* given in `Project Definition.md`'s I/O spec table) -- explicitly flagged by the data-science team's own `C1-configuration.md` spec as "derived-from-spec rather than independently sourced," and never confirmed by the Power Systems sub-team. Do not treat a predicted ampacity below this number as a safety violation without that context.

**What the five candidates actually do.** All five answer the exact same question -- what will this city's ampacity be at the SAME future target time -- but differ in who does the forward-in-time extrapolation, and on what:

- **External-forecast-plus-local-physics** (`ml_wind_corrected`, `ml_cooling_corrected`, `raw_forecast`): the extrapolation of future WEATHER is done entirely by Open-Meteo's own independent NWP model. This project only transforms that already-future weather through IEEE 738 thermal physics (`raw_forecast`), or through that same physics plus a learned correction layer trained to reduce IEEE 738's own known bias (`ml_wind_corrected`/`ml_cooling_corrected`). This project does none of the weather extrapolation itself.
- **Self-contained statistical extrapolation** (`reference_ml_refit_24h`): no external forecast consulted at all. A model learns directly in ampacity-space, from this city's own recent lagged ampacity history plus the MOST RECENTLY OBSERVED (not forecast) weather, to extrapolate the next value. This project does 100% of the forward-looking work itself, with no outside NWP input.
- **No extrapolation at all** (`persistence_24h`): makes no new claim about how conditions evolve. It reuses -- unmodified -- this SAME collector's own `raw_forecast` prediction from ~24 hours ago for the matching target hour, betting only that today looks like yesterday at this same hour. What it reuses is itself a past FORECAST, never a sensor-measured observation -- this project has no sensor-measured ground truth anywhere in this pipeline.

See `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record this summary is drawn from.

Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.

## Latest cycle per city

| City | Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|---|
| AUSTIN | 2026-10-13 03:02 UTC (2026-10-12 22:02 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1128.5 | ✓ 1177.5 | ✓ 1154.8 | unavailable | ✓ 1316.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:02:31.704446+00:00 (cold start, or a gap in this city's collection history) |
| CORPUS_CHRISTI | 2026-10-13 03:02 UTC (2026-10-12 22:02 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1347.5 | ✓ 1312.2 | ✓ 1262.7 | unavailable | ✓ 1399.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:02:53.399440+00:00 (cold start, or a gap in this city's collection history) |
| EL_PASO | 2026-10-13 03:05 UTC (2026-10-12 22:05 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1026.1 | ✓ 1118.3 | ✓ 1083.6 | unavailable | ✓ 1247.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:05:28.905181+00:00 (cold start, or a gap in this city's collection history) |
| MIDLAND | 2026-10-13 03:04 UTC (2026-10-12 22:04 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1776.6 | ✓ 1716.0 | ✓ 1750.0 | unavailable | ✓ 1622.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:04:17.630354+00:00 (cold start, or a gap in this city's collection history) |

## AUSTIN

3 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 3 of 3 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-13 03:02 UTC (2026-10-12 22:02 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1128.5 | ✓ 1177.5 | ✓ 1154.8 | unavailable | ✓ 1316.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:02:31.704446+00:00 (cold start, or a gap in this city's collection history) |
| 2026-10-13 02:50 UTC (2026-10-12 21:50 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1123.6 | ✓ 1188.0 | ✓ 1154.8 | unavailable | ✓ 1288.7 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T02:50:06.357445+00:00 (cold start, or a gap in this city's collection history) |
| 2026-10-13 02:36 UTC (2026-10-12 21:36 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1123.8 | ✓ 1181.3 | ✓ 1154.8 | unavailable | ✓ 1303.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T02:36:41.306867+00:00 (cold start, or a gap in this city's collection history) |

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 3 of 3 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-13 03:02 UTC (2026-10-12 22:02 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 2257.0 | ✓ 2354.9 | ✓ 2309.6 | unavailable | ✓ 2633.1 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 02:50 UTC (2026-10-12 21:50 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 2247.3 | ✓ 2376.0 | ✓ 2309.6 | unavailable | ✓ 2577.3 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 02:36 UTC (2026-10-12 21:36 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 2247.6 | ✓ 2362.6 | ✓ 2309.6 | unavailable | ✓ 2606.6 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## CORPUS_CHRISTI

3 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 3 of 3 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-13 03:02 UTC (2026-10-12 22:02 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1347.5 | ✓ 1312.2 | ✓ 1262.7 | unavailable | ✓ 1399.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:02:53.399440+00:00 (cold start, or a gap in this city's collection history) |
| 2026-10-13 02:50 UTC (2026-10-12 21:50 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1353.4 | ✓ 1316.4 | ✓ 1262.7 | unavailable | ✓ 1441.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T02:50:27.854410+00:00 (cold start, or a gap in this city's collection history) |
| 2026-10-13 02:37 UTC (2026-10-12 21:37 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1353.4 | ✓ 1316.4 | ✓ 1262.7 | unavailable | ✓ 1469.3 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T02:37:01.794712+00:00 (cold start, or a gap in this city's collection history) |

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 3 of 3 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-13 03:02 UTC (2026-10-12 22:02 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 2694.9 | ✓ 2624.5 | ✓ 2525.3 | unavailable | ✓ 2798.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 02:50 UTC (2026-10-12 21:50 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 2706.8 | ✓ 2632.8 | ✓ 2525.3 | unavailable | ✓ 2882.9 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 02:37 UTC (2026-10-12 21:37 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 2706.8 | ✓ 2632.8 | ✓ 2525.3 | unavailable | ✓ 2938.5 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |


## EL_PASO

3 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 3 of 3 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-13 03:05 UTC (2026-10-12 22:05 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1026.1 | ✓ 1118.3 | ✓ 1083.6 | unavailable | ✓ 1247.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:05:28.905181+00:00 (cold start, or a gap in this city's collection history) |
| 2026-10-13 02:53 UTC (2026-10-12 21:53 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | unavailable | unavailable | unavailable | unavailable | ✓ 1227.7 | ml_wind_corrected: forecast unavailable for EL_PASO: fetch_live_forecast_for_valid_time: retrieval failed for city 'EL_PASO', run 2026-10-12 18:00:00+00:00: HTTPSConnectionPool(host='single-runs-api.o… |
| 2026-10-13 02:39 UTC (2026-10-12 21:39 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | unavailable | unavailable | unavailable | unavailable | ✓ 1287.5 | ml_wind_corrected: forecast unavailable for EL_PASO: fetch_live_forecast_for_valid_time: retrieval failed for city 'EL_PASO', run 2026-10-12 18:00:00+00:00: HTTPSConnectionPool(host='single-runs-api.o… |

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 3 of 3 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-13 03:05 UTC (2026-10-12 22:05 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1026.1 | ✓ 1118.3 | ✓ 1083.6 | unavailable | ✓ 1247.2 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 02:53 UTC (2026-10-12 21:53 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | unavailable | unavailable | unavailable | unavailable | ✓ 1227.7 | ml_wind_corrected: forecast unavailable for EL_PASO: fetch_live_forecast_for_valid_time: retrieval failed for city 'EL_PASO', run 2026-10-12 18:00:00+00:00: HTTPSConnectionPool(host='single-runs-api.o… |
| 2026-10-13 02:39 UTC (2026-10-12 21:39 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | unavailable | unavailable | unavailable | unavailable | ✓ 1287.5 | ml_wind_corrected: forecast unavailable for EL_PASO: fetch_live_forecast_for_valid_time: retrieval failed for city 'EL_PASO', run 2026-10-12 18:00:00+00:00: HTTPSConnectionPool(host='single-runs-api.o… |


## MIDLAND

3 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 3`), most recent 3 of 3 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-13 03:04 UTC (2026-10-12 22:04 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 1776.6 | ✓ 1716.0 | ✓ 1750.0 | unavailable | ✓ 1622.2 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-13T03:04:17.630354+00:00 (cold start, or a gap in this city's collection history) |
| 2026-10-13 02:51 UTC (2026-10-12 21:51 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | unavailable | unavailable | unavailable | unavailable | ✓ 1585.5 | ml_wind_corrected: forecast unavailable for MIDLAND: fetch_live_forecast_for_valid_time: retrieval failed for city 'MIDLAND', run 2026-10-12 18:00:00+00:00: HTTPSConnectionPool(host='single-runs-api.o… |
| 2026-10-13 02:38 UTC (2026-10-12 21:38 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | unavailable | unavailable | unavailable | unavailable | ✓ 1605.0 | ml_wind_corrected: forecast unavailable for MIDLAND: fetch_live_forecast_for_valid_time: retrieval failed for city 'MIDLAND', run 2026-10-12 18:00:00+00:00: HTTPSConnectionPool(host='single-runs-api.o… |

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 3 of 3 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-13 03:04 UTC (2026-10-12 22:04 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | ✓ 3553.1 | ✓ 3432.0 | ✓ 3500.0 | unavailable | ✓ 3244.4 | persistence_24h: no matched prior entry this cycle (see the candidate's own reason) |
| 2026-10-13 02:51 UTC (2026-10-12 21:51 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | unavailable | unavailable | unavailable | unavailable | ✓ 3171.0 | ml_wind_corrected: forecast unavailable for MIDLAND: fetch_live_forecast_for_valid_time: retrieval failed for city 'MIDLAND', run 2026-10-12 18:00:00+00:00: HTTPSConnectionPool(host='single-runs-api.o… |
| 2026-10-13 02:38 UTC (2026-10-12 21:38 CDT) | 2026-10-13 18:00 UTC (13:00 CDT) | unavailable | unavailable | unavailable | unavailable | ✓ 3210.1 | ml_wind_corrected: forecast unavailable for MIDLAND: fetch_live_forecast_for_valid_time: retrieval failed for city 'MIDLAND', run 2026-10-12 18:00:00+00:00: HTTPSConnectionPool(host='single-runs-api.o… |


_Legacy corridor-era logs are not rendered (different schema, never mixed with the per-city tables): `AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`._

