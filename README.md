# Shadow Collection — Live Predictions

**Experimental/shadow prototype. Not field-validated operational safety data.** Every number here is a reanalysis-derived development comparison per this phase's own basis caveat -- see `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record.

> Static ratings are this project's own unverified placeholder (the midpoint of a *range* given in `Project Definition.md`'s I/O spec table) -- explicitly flagged by the data-science team's own `C1-configuration.md` spec as "derived-from-spec rather than independently sourced," and never confirmed by the Power Systems sub-team. Do not treat a predicted ampacity below this number as a safety violation without that context.

Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.

## AUSTIN_CORPUS_CHRISTI

11 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 2`), most recent 7 of 7 shown:

| Decision time (UTC) | Valid time (UTC) | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08T06:42:02.642573+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 960.5 (AUSTIN) | ✓ 1057.1 (AUSTIN) | ✓ 946.7 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T06:42:02.642573+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T06:09:25.640554+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 960.5 (AUSTIN) | ✓ 1057.1 (AUSTIN) | ✓ 946.7 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T06:09:25.640554+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T05:48:44.358914+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 965.5 (AUSTIN) | ✓ 1057.1 (AUSTIN) | ✓ 946.7 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T05:48:44.358914+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T01:31:14.392105+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 945.4 (AUSTIN) | ✓ 1064.0 (AUSTIN) | ✓ 946.7 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T01:31:14.392105+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T00:45:36.848499+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1046.1 (AUSTIN) | ✓ 1186.7 (AUSTIN) | ✓ 1086.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T00:45:36.848499+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:33:21.729464+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1069.3 (AUSTIN) | ✓ 1190.6 (AUSTIN) | ✓ 1086.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:33:21.729464+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:05:58.463378+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1091.2 (AUSTIN) | ✓ 1226.8 (AUSTIN) | ✓ 1086.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:05:58.463378+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 7 of 7 shown:

| Decision time (UTC) | Valid time (UTC) | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08T06:42:02.642573+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1921.1 (AUSTIN) | ✓ 2114.1 (AUSTIN) | ✓ 1893.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08T06:09:25.640554+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1921.1 (AUSTIN) | ✓ 2114.1 (AUSTIN) | ✓ 1893.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08T05:48:44.358914+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1931.0 (AUSTIN) | ✓ 2114.1 (AUSTIN) | ✓ 1893.5 (AUSTIN) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08T01:31:14.392105+00:00 | 2026-10-08T18:00:00+00:00 | — | — | — | — | — |  |
| 2026-10-08T00:45:36.848499+00:00 | 2026-10-08T12:00:00+00:00 | — | — | — | — | — |  |
| 2026-10-07T22:33:21.729464+00:00 | 2026-10-08T12:00:00+00:00 | — | — | — | — | — |  |
| 2026-10-07T22:05:58.463378+00:00 | 2026-10-08T12:00:00+00:00 | — | — | — | — | — |  |

_4 pre-cutover (single-method) entries exist in this corridor's raw history and are not rendered here -- see `data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl` on this branch for the full single-candidate record._


## MIDLAND_EL_PASO

11 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 2`), most recent 7 of 7 shown:

| Decision time (UTC) | Valid time (UTC) | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08T06:43:26.859456+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 974.3 (MIDLAND) | ✓ 928.5 (MIDLAND) | ✓ 853.0 (MIDLAND) | unavailable | ✓ 1180.5 | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T06:43:26.859456+00:00 (cold start, or a gap in this corridor's collection history) |
| 2026-10-08T06:10:50.438069+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1020.0 (MIDLAND) | ✓ 1043.1 (MIDLAND) | ✓ 853.0 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T06:10:50.438069+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T05:50:06.859095+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1020.0 (MIDLAND) | ✓ 1041.0 (EL_PASO) | ✓ 853.0 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T05:50:06.859095+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T01:31:35.791102+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 990.4 (MIDLAND) | ✓ 1000.5 (MIDLAND) | ✓ 853.0 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T01:31:35.791102+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T00:45:57.638423+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1200.8 (EL_PASO) | ✓ 1160.7 (MIDLAND) | ✓ 1082.8 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T00:45:57.638423+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:33:43.192350+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1166.5 (EL_PASO) | ✓ 1174.3 (MIDLAND) | ✓ 1082.8 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:33:43.192350+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:06:20.222166+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1207.3 (EL_PASO) | ✓ 1169.6 (EL_PASO) | ✓ 1082.8 (MIDLAND) | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:06:20.222166+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |

> Conductor-based bundle thermal estimate (equal-current-sharing assumption across subconductors) -- NOT a verified equipment-limited circuit rating. Subconductor-per-phase counts are the Power Systems sub-team's provisional, regional assumption, not yet confirmed for any specific line segment.

Bundle-level (subconductors-per-phase) ampacity, same cycles as above, most recent 7 of 7 shown:

| Decision time (UTC) | Valid time (UTC) | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08T06:43:26.859456+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1138.6 (EL_PASO) | ✓ 1043.9 (EL_PASO) | ✓ 1117.9 (EL_PASO) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08T06:10:50.438069+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1138.6 (EL_PASO) | ✓ 1043.9 (EL_PASO) | ✓ 1117.9 (EL_PASO) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08T05:50:06.859095+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1138.6 (EL_PASO) | ✓ 1041.0 (EL_PASO) | ✓ 1117.9 (EL_PASO) | unavailable | unavailable | persistence_24h: no matched prior entry this cycle (see the candidate's own reason); reference_ml_refit_24h: reference_ml_refit_24h produces only a corridor-level prediction (see per_city_not_applicab… |
| 2026-10-08T01:31:35.791102+00:00 | 2026-10-08T18:00:00+00:00 | — | — | — | — | — |  |
| 2026-10-08T00:45:57.638423+00:00 | 2026-10-08T12:00:00+00:00 | — | — | — | — | — |  |
| 2026-10-07T22:33:43.192350+00:00 | 2026-10-08T12:00:00+00:00 | — | — | — | — | — |  |
| 2026-10-07T22:06:20.222166+00:00 | 2026-10-08T12:00:00+00:00 | — | — | — | — | — |  |

_4 pre-cutover (single-method) entries exist in this corridor's raw history and are not rendered here -- see `data/shadow/predictions/MIDLAND_EL_PASO.jsonl` on this branch for the full single-candidate record._


