# Shadow Collection — Live Predictions

**Experimental/shadow prototype. Not field-validated operational safety data.** Every number here is a reanalysis-derived development comparison per this phase's own basis caveat -- see `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record.

> Static ratings are this project's own unverified placeholder (the midpoint of a *range* given in `Project Definition.md`'s I/O spec table) -- explicitly flagged by the data-science team's own `C1-configuration.md` spec as "derived-from-spec rather than independently sourced," and never confirmed by the Power Systems sub-team. Do not treat a predicted ampacity below this number as a safety violation without that context.

Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.

## AUSTIN_CORPUS_CHRISTI

9 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 2`), most recent 5 of 5 shown:

| Decision time (UTC) | Valid time (UTC) | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08T05:48:44.358914+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 965.5 | ✓ 1057.1 | ✓ 946.7 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T05:48:44.358914+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T01:31:14.392105+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 945.4 | ✓ 1064.0 | ✓ 946.7 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T01:31:14.392105+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T00:45:36.848499+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1046.1 | ✓ 1186.7 | ✓ 1086.5 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T00:45:36.848499+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:33:21.729464+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1069.3 | ✓ 1190.6 | ✓ 1086.5 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:33:21.729464+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:05:58.463378+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1091.2 | ✓ 1226.8 | ✓ 1086.5 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:05:58.463378+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |

_4 pre-cutover (single-method) entries exist in this corridor's raw history and are not rendered here -- see `data/shadow/predictions/AUSTIN_CORPUS_CHRISTI.jsonl` on this branch for the full single-candidate record._


## MIDLAND_EL_PASO

9 logged prediction(s), most recent first.

All five candidates per cycle (`schema_version: 2`), most recent 5 of 5 shown:

| Decision time (UTC) | Valid time (UTC) | ml_wind_corrected | ml_cooling_corrected | raw_forecast | persistence_24h | reference_ml_refit_24h | Notes |
|---|---|---|---|---|---|---|---|
| 2026-10-08T05:50:06.859095+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 1020.0 | ✓ 1041.0 | ✓ 853.0 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T05:50:06.859095+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T01:31:35.791102+00:00 | 2026-10-08T18:00:00+00:00 | ✓ 990.4 | ✓ 1000.5 | ✓ 853.0 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T01:31:35.791102+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-08T00:45:57.638423+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1200.8 | ✓ 1160.7 | ✓ 1082.8 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-08T00:45:57.638423+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:33:43.192350+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1166.5 | ✓ 1174.3 | ✓ 1082.8 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:33:43.192350+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |
| 2026-10-07T22:06:20.222166+00:00 | 2026-10-08T12:00:00+00:00 | ✓ 1207.3 | ✓ 1169.6 | ✓ 1082.8 | unavailable | unavailable | persistence_24h: no prior entry within tolerance of decision_time 2026-10-07T22:06:20.222166+00:00 (cold start, or a gap in this corridor's collection history); reference_ml_refit_24h: fetch_live_trut… |

_4 pre-cutover (single-method) entries exist in this corridor's raw history and are not rendered here -- see `data/shadow/predictions/MIDLAND_EL_PASO.jsonl` on this branch for the full single-candidate record._


