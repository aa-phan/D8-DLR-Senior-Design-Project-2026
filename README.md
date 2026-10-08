# Shadow Collection — Live Predictions

**Experimental/shadow prototype. Not field-validated operational safety data.** Every number here is a reanalysis-derived development comparison per this phase's own basis caveat -- see `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record.

> Static ratings are this project's own unverified placeholder (the midpoint of a *range* given in `Project Definition.md`'s I/O spec table) -- explicitly flagged by the data-science team's own `C1-configuration.md` spec as "derived-from-spec rather than independently sourced," and never confirmed by the Power Systems sub-team. Do not treat a predicted ampacity below this number as a safety violation without that context.

Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.

## AUSTIN_CORPUS_CHRISTI

8 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 2`), most recent 4 of 4 shown:

| Decision time (UTC) | Valid time (UTC) | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08T01:31:14.392105+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 945.4 | ✓ 1064.0 | ✓ 946.7 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T01:31:14.392105+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T00:45:36.848499+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1046.1 | ✓ 1186.7 | ✓ 1086.5 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T00:45:36.848499+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:33:21.729464+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1069.3 | ✓ 1190.6 | ✓ 1086.5 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:33:21.729464+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:05:58.463378+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1091.2 | ✓ 1226.8 | ✓ 1086.5 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:05:58.463378+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |

| Decision time (UTC) | Valid time (UTC) | Method | Fallback? | Ampacity (A) | Model version | Notes |
|---|---|---|---|---|---|---|
| 2026-10-07T12:30:34.069561+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1062.1 | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T12:30:03.087442+00:00 |  |
| 2026-10-07T07:43:54.603303+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1062.1 | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T07:43:27.653869+00:00 |  |
| 2026-10-07T07:20:47.671132+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1062.1 | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T07:20:12.340155+00:00 |  |
| 2026-10-07T06:52:09.595877+00:00 | 2026-10-07T18:00:00+00:00 | ml_wind_corrected | No | 1004.1 | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T06:51:38.496517+00:00 |  |

## MIDLAND_EL_PASO

8 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 2`), most recent 4 of 4 shown:

| Decision time (UTC) | Valid time (UTC) | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08T01:31:35.791102+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 990.4 | ✓ 1000.5 | ✓ 853.0 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T01:31:35.791102+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T00:45:57.638423+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1200.8 | ✓ 1160.7 | ✓ 1082.8 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T00:45:57.638423+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:33:43.192350+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1166.5 | ✓ 1174.3 | ✓ 1082.8 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:33:43.192350+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:06:20.222166+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1207.3 | ✓ 1169.6 | ✓ 1082.8 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:06:20.222166+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |

| Decision time (UTC) | Valid time (UTC) | Method | Fallback? | Ampacity (A) | Model version | Notes |
|---|---|---|---|---|---|---|
| 2026-10-07T12:30:55.011306+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1009.6 | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T12:30:03.087442+00:00 |  |
| 2026-10-07T07:44:18.225802+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1002.7 | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T07:43:27.653869+00:00 |  |
| 2026-10-07T07:22:08.071659+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 990.5 | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T07:20:12.340155+00:00 |  |
| 2026-10-07T06:52:32.830592+00:00 | 2026-10-07T18:00:00+00:00 | ml_wind_corrected | No | 944.7 | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T06:51:38.496517+00:00 |  |

