# Shadow Collection — Live Predictions

**Experimental/shadow prototype. Not field-validated operational safety data.** Every number here is a reanalysis-derived development comparison per this phase's own basis caveat -- see `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record.

> Static ratings are this project's own unverified placeholder (the midpoint of a *range* given in `Project Definition.md`'s I/O spec table) -- explicitly flagged by the data-science team's own `C1-configuration.md` spec as "derived-from-spec rather than independently sourced," and never confirmed by the Power Systems sub-team. Do not treat a predicted ampacity below this number as a safety violation without that context.

**What the five candidates actually do.** All five answer the exact same question -- what will this corridor's ampacity be at the SAME future target time -- but differ in who does the forward-in-time extrapolation, and on what:

- **External-forecast-plus-local-physics** (`ml_wind_corrected`, `ml_cooling_corrected`, `raw_forecast`): the extrapolation of future WEATHER is done entirely by Open-Meteo's own independent NWP model. This project only transforms that already-future weather through IEEE 738 thermal physics (`raw_forecast`), or through that same physics plus a learned correction layer trained to reduce IEEE 738's own known bias (`ml_wind_corrected`/`ml_cooling_corrected`). This project does none of the weather extrapolation itself.
- **Self-contained statistical extrapolation** (`reference_ml_refit_24h`): no external forecast consulted at all. A model learns directly in ampacity-space, from this corridor's own recent lagged ampacity history plus the MOST RECENTLY OBSERVED (not forecast) weather, to extrapolate the next value. This project does 100% of the forward-looking work itself, with no outside NWP input -- and because the model was trained on an already corridor-reduced series (weakest-link `min()` applied BEFORE any feature was built), it can only ever produce one corridor-level number, never a per-city breakdown (see `reference_ml_refit_24h`'s own `per_city_not_applicable_reason` field whenever it predicts).
- **No extrapolation at all** (`persistence_24h`): makes no new claim about how conditions evolve. It reuses -- unmodified -- this SAME collector's own `raw_forecast` prediction from ~24 hours ago for the matching target hour, betting only that today looks like yesterday at this same hour. What it reuses is itself a past FORECAST, never a sensor-measured observation -- this project has no sensor-measured ground truth anywhere in this pipeline.

See `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record this summary is drawn from.

Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.

## AUSTIN_CORPUS_CHRISTI

12 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 2`), most recent 8 of 8 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08 12:40 UTC (07:40 CDT) | 2026-10-09 00:00 UTC (2026-10-08 19:00 CDT) | ✓ 963.7 (AUSTIN) | ✓ 1033.4 (AUSTIN) | ✓ 988.1 (AUSTIN) | unavailable | ✓ 1198.6 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T12:40:06.416559+00:00 (cold start, or a gap in this corridor's collection history) |
| 2026-10-08 06:42 UTC (01:42 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 960.5 (AUSTIN) | ✓ 1057.1 (AUSTIN) | ✓ 946.7 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T06:42:02.642573+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08 06:09 UTC (01:09 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 960.5 (AUSTIN) | ✓ 1057.1 (AUSTIN) | ✓ 946.7 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T06:09:25.640554+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08 05:48 UTC (00:48 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 965.5 (AUSTIN) | ✓ 1057.1 (AUSTIN) | ✓ 946.7 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T05:48:44.358914+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08 01:31 UTC (2026-10-07 20:31 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 945.4 (AUSTIN) | ✓ 1064.0 (AUSTIN) | ✓ 946.7 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T01:31:14.392105+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08 00:45 UTC (2026-10-07 19:45 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | ✓ 1046.1 (AUSTIN) | ✓ 1186.7 (AUSTIN) | ✓ 1086.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T00:45:36.848499+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07 22:33 UTC (17:33 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | ✓ 1069.3 (AUSTIN) | ✓ 1190.6 (AUSTIN) | ✓ 1086.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:33:21.729464+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07 22:05 UTC (17:05 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | ✓ 1091.2 (AUSTIN) | ✓ 1226.8 (AUSTIN) | ✓ 1086.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:05:58.463378+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 8 of 8 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08 12:40 UTC (07:40 CDT) | 2026-10-09 00:00 UTC (2026-10-08 19:00 CDT) | ✓ 1927.5 (AUSTIN) | ✓ 2066.7 (AUSTIN) | ✓ 1976.2 (AUSTIN) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08 06:42 UTC (01:42 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 1921.1 (AUSTIN) | ✓ 2114.1 (AUSTIN) | ✓ 1893.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08 06:09 UTC (01:09 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 1921.1 (AUSTIN) | ✓ 2114.1 (AUSTIN) | ✓ 1893.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08 05:48 UTC (00:48 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 1931.0 (AUSTIN) | ✓ 2114.1 (AUSTIN) | ✓ 1893.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08 01:31 UTC (2026-10-07 20:31 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | — | — | — | — | — |  |
| 2026-10-08 00:45 UTC (2026-10-07 19:45 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | — | — | — | — | — |  |
| 2026-10-07 22:33 UTC (17:33 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | — | — | — | — | — |  |
| 2026-10-07 22:05 UTC (17:05 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | — | — | — | — | — |  |

_4 pre-cutover (single-method) entries exist in this corridor's raw history and are not rendered here -- see `data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl` on this branch for the full single-candidate record._


## MIDLAND_EL_PASO

12 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 2`), most recent 8 of 8 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08 12:41 UTC (07:41 CDT) | 2026-10-09 00:00 UTC (2026-10-08 19:00 CDT) | unavailable | unavailable | unavailable | unavailable | unavailable | ml_wind_corrected: forecast unavailable for ['MIDLAND']: MIDLAND: fetch_live_forecast_for_valid_time: retrieval failed for corridor 'MIDLAND_EL_PASO', run 2026-10-08 00:00:00+00:00: HTTPSConnectionPoo… |
| 2026-10-08 06:43 UTC (01:43 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 974.3 (MIDLAND) | ✓ 928.5 (MIDLAND) | ✓ 853.0 (MIDLAND) | unavailable | ✓ 1180.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T06:43:26.859456+00:00 (cold start, or a gap in this corridor's collection history) |
| 2026-10-08 06:10 UTC (01:10 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 1020.0 (MIDLAND) | ✓ 1043.1 (MIDLAND) | ✓ 853.0 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T06:10:50.438069+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08 05:50 UTC (00:50 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 1020.0 (MIDLAND) | ✓ 1041.0 (EL_PASO) | ✓ 853.0 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T05:50:06.859095+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08 01:31 UTC (2026-10-07 20:31 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 990.4 (MIDLAND) | ✓ 1000.5 (MIDLAND) | ✓ 853.0 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T01:31:35.791102+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08 00:45 UTC (2026-10-07 19:45 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | ✓ 1200.8 (EL_PASO) | ✓ 1160.7 (MIDLAND) | ✓ 1082.8 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T00:45:57.638423+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07 22:33 UTC (17:33 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | ✓ 1166.5 (EL_PASO) | ✓ 1174.3 (MIDLAND) | ✓ 1082.8 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:33:43.192350+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07 22:06 UTC (17:06 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | ✓ 1207.3 (EL_PASO) | ✓ 1169.6 (EL_PASO) | ✓ 1082.8 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:06:20.222166+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 8 of 8 shown:

| Decision time | Valid time | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08 12:41 UTC (07:41 CDT) | 2026-10-09 00:00 UTC (2026-10-08 19:00 CDT) | unavailable | unavailable | unavailable | unavailable | unavailable | ml_wind_corrected: forecast unavailable for ['MIDLAND']: MIDLAND: fetch_live_forecast_for_valid_time: retrieval failed for corridor 'MIDLAND_EL_PASO', run 2026-10-08 00:00:00+00:00: HTTPSConnectionPoo… |
| 2026-10-08 06:43 UTC (01:43 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 1138.6 (EL_PASO) | ✓ 1043.9 (EL_PASO) | ✓ 1117.9 (EL_PASO) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08 06:10 UTC (01:10 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 1138.6 (EL_PASO) | ✓ 1043.9 (EL_PASO) | ✓ 1117.9 (EL_PASO) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08 05:50 UTC (00:50 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | ✓ 1138.6 (EL_PASO) | ✓ 1041.0 (EL_PASO) | ✓ 1117.9 (EL_PASO) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08 01:31 UTC (2026-10-07 20:31 CDT) | 2026-10-08 18:00 UTC (13:00 CDT) | — | — | — | — | — |  |
| 2026-10-08 00:45 UTC (2026-10-07 19:45 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | — | — | — | — | — |  |
| 2026-10-07 22:33 UTC (17:33 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | — | — | — | — | — |  |
| 2026-10-07 22:06 UTC (17:06 CDT) | 2026-10-08 12:00 UTC (07:00 CDT) | — | — | — | — | — |  |

_4 pre-cutover (single-method) entries exist in this corridor's raw history and are not rendered here -- see `data/shadow/predictions/MIDLAND_EL_PASO.jsonl` on this branch for the full single-candidate record._


