# Shadow Collection — Live Predictions

**Experimental/shadow prototype. Not field-validated operational safety data.** Every number here is a reanalysis-derived development comparison per this phase's own basis caveat -- see `docs/data-science/decisions/forecast_correction_followup_audit.md` on `main` for the full technical record.

> Static ratings are this project's own unverified placeholder (the midpoint of a *range* given in `Project Definition.md`'s I/O spec table) -- explicitly flagged by the data-science team's own `C1-configuration.md` spec as "derived-from-spec rather than independently sourced," and never confirmed by the Power Systems sub-team. Do not treat a predicted ampacity below this number as a safety violation without that context.

Regenerated automatically after every `shadow_collect.yml` run — do not hand-edit.

## AUSTIN_CORPUS_CHRISTI

7 logged prediction(s), most recent first.

### Cycle — decision time 2026-10-08T00:45:36.848499+00:00 (valid time 2026-10-08T12:00:00+00:00)

All five candidates recorded this cycle (`schema_version: 2`):

| Candidate | Status | Ampacity (A) | Fallback? | Model version | Notes |
|---|---|---|---|---|---|
| ml_wind_corrected | ok | 1046.1 | No | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-08T00:45:12.573507+00:00 |  |
| ml_cooling_corrected | ok | 1186.7 | No | ml_cooling_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-08T00:45:12.573048+00:00 |  |
| raw_forecast | ok | 1086.5 | No | — |  |
| persistence_24h | unavailable | — | No | — | no prior entry within tolerance of decision_time 2026-10-08T00:45:36.848499+00:00 (cold start, or a … |
| reference_ml_refit_24h | unavailable | — | No | — | fetch_live_truth_proxy_series: corridor 'AUSTIN_CORPUS_CHRISTI' city 'AUSTIN': null 'solar_radiation… |

### Cycle — decision time 2026-10-07T22:33:21.729464+00:00 (valid time 2026-10-08T12:00:00+00:00)

All five candidates recorded this cycle (`schema_version: 2`):

| Candidate | Status | Ampacity (A) | Fallback? | Model version | Notes |
|---|---|---|---|---|---|
| ml_wind_corrected | ok | 1069.3 | No | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T22:32:53.893639+00:00 |  |
| ml_cooling_corrected | ok | 1190.6 | No | ml_cooling_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T22:32:53.892999+00:00 |  |
| raw_forecast | ok | 1086.5 | No | — |  |
| persistence_24h | unavailable | — | No | — | no prior entry within tolerance of decision_time 2026-10-07T22:33:21.729464+00:00 (cold start, or a … |
| reference_ml_refit_24h | unavailable | — | No | — | fetch_live_truth_proxy_series: corridor 'AUSTIN_CORPUS_CHRISTI' city 'AUSTIN': no usable station row… |

### Cycle — decision time 2026-10-07T22:05:58.463378+00:00 (valid time 2026-10-08T12:00:00+00:00)

All five candidates recorded this cycle (`schema_version: 2`):

| Candidate | Status | Ampacity (A) | Fallback? | Model version | Notes |
|---|---|---|---|---|---|
| ml_wind_corrected | ok | 1091.2 | No | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T22:05:30.593605+00:00 |  |
| ml_cooling_corrected | ok | 1226.8 | No | ml_cooling_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T22:05:30.592957+00:00 |  |
| raw_forecast | ok | 1086.5 | No | — |  |
| persistence_24h | unavailable | — | No | — | no prior entry within tolerance of decision_time 2026-10-07T22:05:58.463378+00:00 (cold start, or a … |
| reference_ml_refit_24h | unavailable | — | No | — | fetch_live_truth_proxy_series: corridor 'AUSTIN_CORPUS_CHRISTI' city 'AUSTIN': no usable station row… |

| Decision time (UTC) | Valid time (UTC) | Method | Fallback? | Ampacity (A) | Model version | Notes |
|---|---|---|---|---|---|---|
| 2026-10-07T12:30:34.069561+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1062.1 | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T12:30:03.087442+00:00 |  |
| 2026-10-07T07:43:54.603303+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1062.1 | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T07:43:27.653869+00:00 |  |
| 2026-10-07T07:20:47.671132+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1062.1 | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T07:20:12.340155+00:00 |  |
| 2026-10-07T06:52:09.595877+00:00 | 2026-10-07T18:00:00+00:00 | ml_wind_corrected | No | 1004.1 | ml_wind_corrected_AUSTIN_CORPUS_CHRISTI@2026-10-07T06:51:38.496517+00:00 |  |

## MIDLAND_EL_PASO

7 logged prediction(s), most recent first.

### Cycle — decision time 2026-10-08T00:45:57.638423+00:00 (valid time 2026-10-08T12:00:00+00:00)

All five candidates recorded this cycle (`schema_version: 2`):

| Candidate | Status | Ampacity (A) | Fallback? | Model version | Notes |
|---|---|---|---|---|---|
| ml_wind_corrected | ok | 1200.8 | No | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-08T00:45:12.573507+00:00 |  |
| ml_cooling_corrected | ok | 1160.7 | No | ml_cooling_corrected_MIDLAND_EL_PASO@2026-10-08T00:45:12.573507+00:00 |  |
| raw_forecast | ok | 1082.8 | No | — |  |
| persistence_24h | unavailable | — | No | — | no prior entry within tolerance of decision_time 2026-10-08T00:45:57.638423+00:00 (cold start, or a … |
| reference_ml_refit_24h | unavailable | — | No | — | fetch_live_truth_proxy_series: corridor 'MIDLAND_EL_PASO' city 'MIDLAND': null 'solar_radiation' at … |

### Cycle — decision time 2026-10-07T22:33:43.192350+00:00 (valid time 2026-10-08T12:00:00+00:00)

All five candidates recorded this cycle (`schema_version: 2`):

| Candidate | Status | Ampacity (A) | Fallback? | Model version | Notes |
|---|---|---|---|---|---|
| ml_wind_corrected | ok | 1166.5 | No | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T22:32:53.893639+00:00 |  |
| ml_cooling_corrected | ok | 1174.3 | No | ml_cooling_corrected_MIDLAND_EL_PASO@2026-10-07T22:32:53.893639+00:00 |  |
| raw_forecast | ok | 1082.8 | No | — |  |
| persistence_24h | unavailable | — | No | — | no prior entry within tolerance of decision_time 2026-10-07T22:33:43.192350+00:00 (cold start, or a … |
| reference_ml_refit_24h | unavailable | — | No | — | fetch_live_truth_proxy_series: corridor 'MIDLAND_EL_PASO' city 'MIDLAND': no usable station row with… |

### Cycle — decision time 2026-10-07T22:06:20.222166+00:00 (valid time 2026-10-08T12:00:00+00:00)

All five candidates recorded this cycle (`schema_version: 2`):

| Candidate | Status | Ampacity (A) | Fallback? | Model version | Notes |
|---|---|---|---|---|---|
| ml_wind_corrected | ok | 1207.3 | No | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T22:05:30.593605+00:00 |  |
| ml_cooling_corrected | ok | 1169.6 | No | ml_cooling_corrected_MIDLAND_EL_PASO@2026-10-07T22:05:30.593605+00:00 |  |
| raw_forecast | ok | 1082.8 | No | — |  |
| persistence_24h | unavailable | — | No | — | no prior entry within tolerance of decision_time 2026-10-07T22:06:20.222166+00:00 (cold start, or a … |
| reference_ml_refit_24h | unavailable | — | No | — | fetch_live_truth_proxy_series: corridor 'MIDLAND_EL_PASO' city 'MIDLAND': no usable station row with… |

| Decision time (UTC) | Valid time (UTC) | Method | Fallback? | Ampacity (A) | Model version | Notes |
|---|---|---|---|---|---|---|
| 2026-10-07T12:30:55.011306+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1009.6 | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T12:30:03.087442+00:00 |  |
| 2026-10-07T07:44:18.225802+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 1002.7 | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T07:43:27.653869+00:00 |  |
| 2026-10-07T07:22:08.071659+00:00 | 2026-10-08T00:00:00+00:00 | ml_wind_corrected | No | 990.5 | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T07:20:12.340155+00:00 |  |
| 2026-10-07T06:52:32.830592+00:00 | 2026-10-07T18:00:00+00:00 | ml_wind_corrected | No | 944.7 | ml_wind_corrected_MIDLAND_EL_PASO@2026-10-07T06:51:38.496517+00:00 |  |

