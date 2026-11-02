# Per-city shadow evaluation - row source: shadow logs (live-system check)

Truth: reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated
Basis: FRESH
Protocol status: signed
Round: v4-read1
Evaluation instant: 2026-11-01T00:00:00+00:00
Valid-time cutoff (strict, valid_time < cutoff): 2026-10-25T00:00:00+00:00
Now evaluated: 2026-11-02T17:52:10.105818+00:00
Override: none
Non-default pre-registered values: none
Git SHA: e092d129978e0744e7565fdbb258a4b1f7ce8eef (dirty: True)
Freeze check: all artifact commits are before the 2026-11-01 freeze

## Sample size (read this first)

Precision targets: about 590 rows for tail-rate precision and about 1575 rows for a 5 A minimum detectable difference.
- Pooled NOMINAL n (max over candidates) = 175. This sums rows from cities that share weather and rows six hours apart that are correlated, so it is NOT an effective sample size and is never judged against the ~590 / ~1575 targets here; the targets are judged on effective n in the pair table below.
- AUSTIN: n scored per candidate: ml_wind_corrected=42, ml_cooling_corrected=42, raw_forecast=44, persistence_24h=9, reference_ml_refit_24h=40. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- CORPUS_CHRISTI: n scored per candidate: ml_wind_corrected=43, ml_cooling_corrected=43, raw_forecast=44, persistence_24h=9, reference_ml_refit_24h=41. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- MIDLAND: n scored per candidate: ml_wind_corrected=44, ml_cooling_corrected=43, raw_forecast=44, persistence_24h=9, reference_ml_refit_24h=42. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- EL_PASO: n scored per candidate: ml_wind_corrected=43, ml_cooling_corrected=43, raw_forecast=43, persistence_24h=9, reference_ml_refit_24h=43. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).

| pair (A vs B) | n paired (pooled) | n_eff (bootstrap) | n_eff (ACF, per city) | MDD (amps) | rows needed for 5 A | ~590 (judged on effective n) | ~1,575 (judged on effective n) |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 171 | 108.6 | AUSTIN:20.5, CORPUS_CHRISTI:16.6, MIDLAND:43.0, EL_PASO:40.4 | 30.13 | 6211 | not met | not met |
| ml_wind_corrected vs reference_ml_refit_24h | 165 | 46.8 | AUSTIN:24.2, CORPUS_CHRISTI:14.3, MIDLAND:28.2, EL_PASO:30.9 | 83.07 | 45550 | not met | not met |
| ml_cooling_corrected vs reference_ml_refit_24h | 165 | 50.6 | AUSTIN:40.0, CORPUS_CHRISTI:32.8, MIDLAND:29.2, EL_PASO:42.0 | 82.03 | 44407 | not met | not met |
| ml_wind_corrected vs raw_forecast | 172 | 85.0 | AUSTIN:36.0, CORPUS_CHRISTI:32.2, MIDLAND:40.1, EL_PASO:43.0 | 37.01 | 9424 | not met | not met |
| ml_cooling_corrected vs raw_forecast | 171 | 135.6 | AUSTIN:42.0, CORPUS_CHRISTI:31.3, MIDLAND:43.0, EL_PASO:29.1 | 26.70 | 4876 | not met | not met |
| reference_ml_refit_24h vs raw_forecast | 165 | 50.8 | AUSTIN:40.0, CORPUS_CHRISTI:17.2, MIDLAND:28.2, EL_PASO:42.0 | 87.32 | 50322 | not met | not met |
| ml_wind_corrected vs persistence_24h | 35 | 11.4 | AUSTIN:4.4, CORPUS_CHRISTI:9.0, MIDLAND:5.8, EL_PASO:9.0 | 214.43 | 64373 | not met | not met |
| ml_cooling_corrected vs persistence_24h | 35 | 14.1 | AUSTIN:8.0, CORPUS_CHRISTI:9.0, MIDLAND:5.7, EL_PASO:5.6 | 155.19 | 33718 | not met | not met |
| reference_ml_refit_24h vs persistence_24h | 30 | 15.9 | AUSTIN:7.0, CORPUS_CHRISTI:7.0, MIDLAND:6.2, EL_PASO:8.0 | 195.44 | 45837 | not met | not met |

## Headline family: 9 tests, pooled, city-clustered, Holm at 0.05

Margin = mean|e_B| - mean|e_A| in amps, so a positive margin means A has the lower MAE. Reanalysis-derived, never sensor-validated.

| A vs B | n | margin (A) | rel. MAE reduction | cities favouring A | headline p | Holm-adj. p | outcome | flags |
|---|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 171 | 6.45 | 0.057 | 3 of 4 | 0.4306 | 1.0000 | inconclusive | V1_live_anchor, V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs reference_ml_refit_24h | 165 | 59.16 | 0.358 | 4 of 4 | 0.0030 | 0.0270 | favors_A | V1_live_anchor, V2_reference_target_hour, V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs reference_ml_refit_24h | 165 | 50.94 | 0.308 | 4 of 4 | 0.0070 | 0.0560 | inconclusive | V1_live_anchor, V2_reference_target_hour, V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs raw_forecast | 172 | 10.65 | 0.087 | 3 of 4 | 0.2992 | 1.0000 | inconclusive | V1_live_anchor, V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs raw_forecast | 171 | 4.33 | 0.037 | 3 of 4 | 0.5291 | 1.0000 | inconclusive | V1_live_anchor, V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs raw_forecast | 165 | -44.87 | -0.373 | 1 of 4 | 0.0490 | 0.3430 | inconclusive | V2_reference_target_hour, V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs persistence_24h | 35 | 67.03 | 0.348 | 3 of 4 | 0.2406 | 1.0000 | inconclusive | V1_live_anchor, V3_live_persistence_definition, V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs persistence_24h | 35 | 60.40 | 0.314 | 3 of 4 | 0.1136 | 0.6815 | inconclusive | V1_live_anchor, V3_live_persistence_definition, V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs persistence_24h | 30 | 33.70 | 0.173 | 3 of 4 | 0.5375 | 1.0000 | inconclusive | V2_reference_target_hour, V3_live_persistence_definition, V4_reanalysis_truth_shared_weather |

Headline intervals (widest 95% and widest Bonferroni (1 - 0.05/9) over both pooled schemes and every runnable block length):

- ml_wind_corrected vs ml_cooling_corrected: 95% [-11.16, 24.94]; Bonferroni [-20.09, 32.34]; block lengths run [1, 4, 8], skipped [28]
- ml_wind_corrected vs reference_ml_refit_24h: 95% [19.13, 114.02]; Bonferroni [3.98, 135.08]; block lengths run [1, 4, 8], skipped [28]
- ml_cooling_corrected vs reference_ml_refit_24h: 95% [11.21, 103.77]; Bonferroni [-1.49, 125.86]; block lengths run [1, 4, 8], skipped [28]
- ml_wind_corrected vs raw_forecast: 95% [-9.61, 32.54]; Bonferroni [-19.47, 39.71]; block lengths run [1, 4, 8], skipped [28]
- ml_cooling_corrected vs raw_forecast: 95% [-9.60, 20.00]; Bonferroni [-16.20, 25.83]; block lengths run [1, 4, 8], skipped [28]
- reference_ml_refit_24h vs raw_forecast: 95% [-97.10, -0.42]; Bonferroni [-120.30, 14.12]; block lengths run [1, 4, 8], skipped [28]
- ml_wind_corrected vs persistence_24h: 95% [-38.16, 193.00]; Bonferroni [-70.22, 237.55]; block lengths run [1, 4], skipped [8, 28]
- ml_cooling_corrected vs persistence_24h: 95% [-11.69, 154.69]; Bonferroni [-34.93, 190.79]; block lengths run [1, 4], skipped [8, 28]
- reference_ml_refit_24h vs persistence_24h: 95% [-65.28, 147.35]; Bonferroni [-96.26, 196.81]; block lengths run [1, 4], skipped [8, 28]

## Decision (live-system check)

Label: live-system check, never decides. Round: v4-read1. Rule: v4. Protocol status: signed.

Bars: 2% of each city's mean truth ampacity over its scored rows (amps):
- Bar AUSTIN: 23.68 A
- Bar CORPUS_CHRISTI: 28.60 A
- Bar MIDLAND: 32.42 A
- Bar EL_PASO: 25.66 A

Each candidate against raw_forecast (pooled benefit against the pooled bar):
- ml_wind_corrected vs raw_forecast: **not shown** (benefit 10.65 A, pooled bar 27.64 A, Holm-adjusted p 1.0000; favoured in 3 of 4 cities, consistent; not vetoed; veto records consulted: no veto record applied (development basis))
- ml_cooling_corrected vs raw_forecast: **not shown** (benefit 4.33 A, pooled bar 27.61 A, Holm-adjusted p 1.0000; favoured in 3 of 4 cities, consistent; not vetoed; veto records consulted: no veto record applied (development basis))
- reference_ml_refit_24h vs raw_forecast: **not shown** (benefit -44.87 A, pooled bar 27.63 A, Holm-adjusted p 0.3430; favoured in 1 of 4 cities, not consistent; not vetoed; veto records consulted: no veto record applied (development basis))

- ml_cooling_corrected vs ml_wind_corrected: pooled margin -6.45 A against a pooled bar of 27.61 A, favoured in 1 of 4 cities, consistently better: False
- reference_ml_refit_24h vs ml_wind_corrected: pooled margin -59.16 A against a pooled bar of 27.63 A, favoured in 0 of 4 cities, consistently better: False

Reported pick: None (live-system check, never decides). Would-be outcome under the v4 rule: no candidate qualifies.

- Sample size: pooled paired rows per headline test range from 30 to 172 (nominal, not effective; effective sample sizes are smaller because six-hourly rows and the four cities share weather); both precision targets (about 590 rows for the tail rate, about 1,575 rows for a 5 A minimum detectable difference) were not met for any headline test.
- This is the live-system check, never decides: its pick is always None. Under the v4 rule its would-be outcome is no candidate qualifies.
- no ABLATION/TEST veto record was applied (development basis)
- Per-city results are descriptive and uncorrected; the headline is the pooled, city-clustered 9-test family with Holm correction at 0.05.
- Calibrated overrating risk (the overrating rate at the nominal 5% target) and retained capacity were not measured. No 8% ceiling was applied. Candidates are ranked on point error only, which is a weaker standard than v1.
- reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated.
- exploratory: thresholds not pre-registered in a signed protocol

## Per-city descriptive metrics (reanalysis-derived, never sensor-validated)

bias = prediction - truth (positive means capacity overstated). Over-prediction rate and overshoot are descriptive; not the calibrated 5%-target rate; not compared with 8%.

### AUSTIN
Rows in scope: 44; excluded by reason: {'missing_forecast_model': 5, 'at_or_after_cutoff': 37, 'duplicate_valid_time': 10}

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 42 | -25.94 | 107.97 | 133.65 | 83.25 | 0.476 | 86.12 / 195.93 / 223.48 |
| ml_cooling_corrected | 42 | 45.07 | 112.40 | 142.69 | 105.73 | 0.643 | 122.48 / 310.56 / 368.27 |
| raw_forecast | 44 | 53.02 | 111.54 | 148.83 | 93.12 | 0.636 | 129.30 / 334.78 / 383.33 |
| persistence_24h | 9 | 35.74 | 154.64 | 190.95 | 202.68 | 0.444 | 214.18 / 333.29 / 353.10 |
| reference_ml_refit_24h | 40 | 117.77 | 184.56 | 213.18 | 175.97 | 0.725 | 208.50 / 366.76 / 385.46 |
| reference_ml_refit_24h (logged valid_time reading; flagged V2_logged_hour_reading_compares_a_different_hour) | 40 | 112.00 | 173.97 | 207.88 | 176.63 | 0.700 | 204.26 / 380.28 / 467.99 |

Candidate-level exclusions: ml_wind_corrected: {'candidate_unavailable': 2}; ml_cooling_corrected: {'candidate_unavailable': 2}; persistence_24h: {'candidate_unavailable': 35}; reference_ml_refit_24h: {'candidate_unavailable': 4}

### CORPUS_CHRISTI
Rows in scope: 44; excluded by reason: {'missing_forecast_model': 5, 'at_or_after_cutoff': 37, 'duplicate_valid_time': 10}

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 43 | -4.22 | 78.07 | 102.74 | 47.22 | 0.512 | 72.17 / 201.03 / 221.29 |
| ml_cooling_corrected | 43 | -4.60 | 99.65 | 126.87 | 88.57 | 0.465 | 102.18 / 296.61 / 362.65 |
| raw_forecast | 44 | 4.92 | 114.96 | 156.46 | 76.68 | 0.545 | 109.89 / 246.55 / 270.08 |
| persistence_24h | 9 | 0.63 | 273.45 | 363.46 | 201.77 | 0.667 | 205.56 / 497.43 / 554.99 |
| reference_ml_refit_24h | 41 | -17.40 | 110.76 | 146.45 | 71.06 | 0.439 | 106.33 / 268.38 / 275.76 |
| reference_ml_refit_24h (logged valid_time reading; flagged V2_logged_hour_reading_compares_a_different_hour) | 41 | -32.96 | 162.73 | 190.81 | 143.42 | 0.463 | 140.02 / 236.91 / 251.40 |

Candidate-level exclusions: ml_wind_corrected: {'candidate_unavailable': 1}; ml_cooling_corrected: {'candidate_unavailable': 1}; persistence_24h: {'candidate_unavailable': 35}; reference_ml_refit_24h: {'candidate_unavailable': 3}

### MIDLAND
Rows in scope: 44; excluded by reason: {'missing_forecast_model': 5, 'at_or_after_cutoff': 37, 'duplicate_valid_time': 10}

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 44 | 3.37 | 128.90 | 200.33 | 78.30 | 0.364 | 181.87 / 644.85 / 793.50 |
| ml_cooling_corrected | 43 | -13.71 | 119.31 | 166.52 | 86.67 | 0.326 | 162.16 / 411.48 / 578.17 |
| raw_forecast | 44 | -18.56 | 139.05 | 203.96 | 79.48 | 0.364 | 165.68 / 577.18 / 781.71 |
| persistence_24h | 9 | -173.27 | 189.52 | 234.97 | 212.91 | 0.222 | 36.57 / 67.45 / 70.88 |
| reference_ml_refit_24h | 42 | -101.77 | 222.85 | 285.14 | 171.75 | 0.286 | 211.89 / 678.57 / 874.21 |
| reference_ml_refit_24h (logged valid_time reading; flagged V2_logged_hour_reading_compares_a_different_hour) | 42 | -61.26 | 207.68 | 269.56 | 140.83 | 0.357 | 204.99 / 535.75 / 619.14 |

Candidate-level exclusions: ml_cooling_corrected: {'candidate_failed': 1}; persistence_24h: {'candidate_unavailable': 35}; reference_ml_refit_24h: {'candidate_unavailable': 2}

### EL_PASO
Rows in scope: 44; excluded by reason: {'missing_forecast_model': 5, 'at_or_after_cutoff': 37, 'duplicate_valid_time': 10}

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 43 | -51.71 | 130.92 | 172.25 | 106.16 | 0.395 | 100.18 / 249.86 / 413.44 |
| ml_cooling_corrected | 43 | -24.84 | 124.78 | 168.11 | 85.63 | 0.419 | 119.38 / 361.13 / 367.31 |
| raw_forecast | 43 | 41.20 | 126.51 | 164.59 | 109.68 | 0.605 | 138.68 / 386.86 / 487.77 |
| persistence_24h | 9 | -85.82 | 154.99 | 200.83 | 87.21 | 0.444 | 77.82 / 147.58 / 163.68 |
| reference_ml_refit_24h | 43 | -1.19 | 142.47 | 174.96 | 135.46 | 0.558 | 126.56 / 286.15 / 298.05 |
| reference_ml_refit_24h (logged valid_time reading; flagged V2_logged_hour_reading_compares_a_different_hour) | 43 | 29.44 | 132.84 | 159.65 | 118.39 | 0.581 | 139.56 / 296.58 / 311.80 |

Candidate-level exclusions: ml_wind_corrected: {'candidate_unavailable': 1}; ml_cooling_corrected: {'candidate_unavailable': 1}; raw_forecast: {'candidate_unavailable': 1}; persistence_24h: {'candidate_unavailable': 35}; reference_ml_refit_24h: {'candidate_unavailable': 1}


## Per-city comparisons (descriptive, uncorrected)

- ml_wind_corrected vs ml_cooling_corrected:
  - AUSTIN: n=42 margin=4.43 outcome=inconclusive (crosses_zero) L=1: [-24.54, 32.73]; L=4: [-27.82, 42.10]; L=8: [-28.42, 46.60] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=43 margin=21.58 outcome=inconclusive (block_length_sensitive) L=1: [4.91, 39.09]; L=4: [-1.09, 41.45]; L=8: [-4.59, 41.62] - descriptive, uncorrected
  - MIDLAND: n=43 margin=5.86 outcome=inconclusive (crosses_zero) L=1: [-9.27, 20.63]; L=4: [-6.28, 19.29]; L=8: [-5.89, 15.75] - descriptive, uncorrected
  - EL_PASO: n=43 margin=-6.14 outcome=inconclusive (crosses_zero) L=1: [-41.92, 30.91]; L=4: [-34.21, 36.44]; L=8: [-31.75, 40.97] - descriptive, uncorrected
- ml_wind_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=40 margin=80.17 outcome=favors_A L=1: [43.82, 116.04]; L=4: [41.96, 123.83]; L=8: [57.37, 126.67] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=41 margin=33.29 outcome=inconclusive (crosses_zero) L=1: [-3.97, 72.17]; L=4: [-13.20, 82.68]; L=8: [-17.42, 96.76] - descriptive, uncorrected
  - MIDLAND: n=42 margin=108.64 outcome=favors_A L=1: [49.42, 172.87]; L=4: [46.07, 184.65]; L=8: [44.10, 193.85] - descriptive, uncorrected
  - EL_PASO: n=42 margin=14.95 outcome=inconclusive (crosses_zero) L=1: [-27.50, 58.08]; L=4: [-19.85, 65.97]; L=8: [-13.35, 65.94] - descriptive, uncorrected
- ml_cooling_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=40 margin=68.55 outcome=favors_A L=1: [27.92, 108.88]; L=4: [32.25, 109.99]; L=8: [41.77, 119.31] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=41 margin=17.35 outcome=inconclusive (crosses_zero) L=1: [-18.23, 53.42]; L=4: [-20.03, 56.75]; L=8: [-16.35, 60.89] - descriptive, uncorrected
  - MIDLAND: n=42 margin=102.80 outcome=favors_A L=1: [43.92, 167.78]; L=4: [41.97, 178.13]; L=8: [41.89, 187.98] - descriptive, uncorrected
  - EL_PASO: n=42 margin=15.12 outcome=inconclusive (crosses_zero) L=1: [-29.68, 59.83]; L=4: [-19.96, 59.92]; L=8: [-15.89, 50.77] - descriptive, uncorrected
- ml_wind_corrected vs raw_forecast:
  - AUSTIN: n=42 margin=2.50 outcome=inconclusive (crosses_zero) L=1: [-28.95, 33.62]; L=4: [-27.44, 36.75]; L=8: [-24.41, 40.74] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=43 margin=34.18 outcome=favors_A L=1: [12.54, 58.33]; L=4: [15.04, 58.80]; L=8: [16.22, 52.63] - descriptive, uncorrected
  - MIDLAND: n=44 margin=10.15 outcome=inconclusive (block_length_sensitive) L=1: [-4.14, 25.92]; L=4: [-1.21, 27.71]; L=8: [1.32, 31.58] - descriptive, uncorrected
  - EL_PASO: n=43 margin=-4.42 outcome=inconclusive (crosses_zero) L=1: [-41.19, 31.82]; L=4: [-37.44, 33.62]; L=8: [-36.33, 39.46] - descriptive, uncorrected
- ml_cooling_corrected vs raw_forecast:
  - AUSTIN: n=42 margin=-1.94 outcome=inconclusive (crosses_zero) L=1: [-26.67, 23.30]; L=4: [-23.69, 19.89]; L=8: [-20.94, 18.07] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=43 margin=12.60 outcome=inconclusive (crosses_zero) L=1: [-15.03, 40.80]; L=4: [-13.72, 44.04]; L=8: [-14.06, 44.37] - descriptive, uncorrected
  - MIDLAND: n=43 margin=4.79 outcome=inconclusive (crosses_zero) L=1: [-12.51, 23.10]; L=4: [-8.40, 21.97]; L=8: [-5.27, 26.11] - descriptive, uncorrected
  - EL_PASO: n=43 margin=1.72 outcome=inconclusive (crosses_zero) L=1: [-30.35, 30.01]; L=4: [-34.53, 27.57]; L=8: [-36.55, 21.17] - descriptive, uncorrected
- reference_ml_refit_24h vs raw_forecast:
  - AUSTIN: n=40 margin=-70.33 outcome=favors_B L=1: [-114.24, -24.67]; L=4: [-106.84, -39.37]; L=8: [-112.80, -48.43] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=41 margin=2.23 outcome=inconclusive (crosses_zero) L=1: [-44.64, 49.00]; L=4: [-54.29, 58.62]; L=8: [-70.61, 57.88] - descriptive, uncorrected
  - MIDLAND: n=42 margin=-97.56 outcome=favors_B L=1: [-162.86, -37.35]; L=4: [-173.35, -30.26]; L=8: [-184.32, -19.42] - descriptive, uncorrected
  - EL_PASO: n=42 margin=-13.92 outcome=inconclusive (crosses_zero) L=1: [-59.16, 31.94]; L=4: [-53.77, 9.59]; L=8: [-46.97, 0.71] - descriptive, uncorrected
- ml_wind_corrected vs persistence_24h:
  - AUSTIN: n=8 margin=6.12 outcome=inconclusive (crosses_zero) L=1: [-74.38, 99.64]; L=4: [-95.89, 89.07] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=9 margin=202.18 outcome=favors_A L=1: [56.67, 360.49]; L=4: [88.85, 319.84] - descriptive, uncorrected
  - MIDLAND: n=9 margin=100.63 outcome=inconclusive (block_length_sensitive) L=1: [4.33, 197.34]; L=4: [-5.66, 229.11] - descriptive, uncorrected
  - EL_PASO: n=9 margin=-47.58 outcome=inconclusive (block_length_sensitive) L=1: [-155.36, 50.54]; L=4: [-126.15, -9.16] - descriptive, uncorrected
- ml_cooling_corrected vs persistence_24h:
  - AUSTIN: n=8 margin=-24.39 outcome=inconclusive (crosses_zero) L=1: [-93.07, 49.21]; L=4: [-88.11, 29.76] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=9 margin=144.28 outcome=favors_A L=1: [14.02, 291.89]; L=4: [55.86, 256.62] - descriptive, uncorrected
  - MIDLAND: n=9 margin=85.78 outcome=inconclusive (crosses_zero) L=1: [-8.56, 179.29]; L=4: [-18.74, 207.04] - descriptive, uncorrected
  - EL_PASO: n=9 margin=26.50 outcome=inconclusive (crosses_zero) L=1: [-15.83, 79.35]; L=4: [-23.37, 57.04] - descriptive, uncorrected
- reference_ml_refit_24h vs persistence_24h:
  - AUSTIN: n=7 margin=6.29 outcome=insufficient_data (fewer_than_min_paired_rows)  - descriptive, uncorrected
  - CORPUS_CHRISTI: n=7 margin=152.36 outcome=insufficient_data (fewer_than_min_paired_rows)  - descriptive, uncorrected
  - MIDLAND: n=8 margin=-72.81 outcome=inconclusive (crosses_zero) L=1: [-178.27, 50.79]; L=4: [-160.10, 52.45] - descriptive, uncorrected
  - EL_PASO: n=8 margin=60.37 outcome=inconclusive (crosses_zero) L=1: [-57.01, 184.39]; L=4: [-50.96, 70.28] - descriptive, uncorrected

## Validity flags and source-specific diagnostics

- V1 (applies): The live correction anchor is a station observation (TCEQ, falling back to Synoptic) taken 11 to 23 h before valid time; the models were trained with an archive anchor at exactly valid - 24 h.
- V2 (applies): reference_ml_refit_24h predicts about decision time + 24 h, which is 7 to 13 h after the logged valid time. Its headline is scored at its own target hour; the logged-valid_time reading is reported alongside and flagged.
- V3 (applies): The logged persistence_24h is the previous same-model cycle's raw_forecast (an hour about 11 to 17 h before the scored valid time), not the 24 h persistence of the development record. It is unavailable on a cold start.
- V4 (applies): Truth is reanalysis shared with the training data, and the four cities share weather, so a pooled comparison has far fewer effective samples than rows.
- V5 (applies): The live underlying weather model must match the one the corrections were trained on (gfs_seamless). Only rows tagged forecast_model == gfs_seamless are scored.
- V6 (applies): Rows without a forecast_model field were logged before the 2026-10-13 fix and predict the hour before the scored hour; they are excluded and never pooled.

```json
{
 "AUSTIN": {
  "anchor_breakdown": {
   "candidates": {
    "ml_cooling_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.3815234913888889,
        "mean": 0.15985851683201058,
        "median": 0.13158230152777778,
        "min": 0.08994184361111111,
        "n": 42
       },
       "anchor_to_valid_h": {
        "max": 17.0,
        "mean": 13.773015873015874,
        "median": 13.116666666666667,
        "min": 11.333333333333334,
        "n": 42
       },
       "n_rows": 42,
       "scored": {
        "bias": 45.06978218024546,
        "mae": 112.3986847867712,
        "n": 42
       },
       "stations": {
        "KAUS": 42
       }
      },
      "unknown": {
       "anchor_age_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "anchor_to_valid_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "n_rows": 2,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 2
       }
      }
     }
    },
    "ml_wind_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.3815234913888889,
        "mean": 0.15985851683201058,
        "median": 0.13158230152777778,
        "min": 0.08994184361111111,
        "n": 42
       },
       "anchor_to_valid_h": {
        "max": 17.0,
        "mean": 13.773015873015874,
        "median": 13.116666666666667,
        "min": 11.333333333333334,
        "n": 42
       },
       "n_rows": 42,
       "scored": {
        "bias": -25.94232038589137,
        "mae": 107.96564821707675,
        "n": 42
       },
       "stations": {
        "KAUS": 42
       }
      },
      "unknown": {
       "anchor_age_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "anchor_to_valid_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "n_rows": 2,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 2
       }
      }
     }
    }
   },
   "label": "exploratory; descriptive only; not a hypothesis test; no adjustment or reweighting"
  },
  "decision_to_valid_gap_hours": {
   "max": 16.783626738333332,
   "mean": 13.584601427190655,
   "median": 12.98691713875,
   "min": 11.157189704444445,
   "n": 44
  },
  "forecast_model_counts": {
   "<missing>": 5,
   "gfs_seamless": 91
  },
  "logged_at_inversions": 0,
  "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
  "reference_target_hour": {
   "rounding_offset_s_max_abs": 1727.492334,
   "window_end_discrepancy_s": {
    "max": 1273.760364,
    "mean": -177.47984985,
    "median": -50.9399155,
    "min": -1727.492334,
    "n": 40
   }
  },
  "truth_dropped_null_hours": [],
  "truth_fetch": {
   "end_date": "2026-10-24",
   "error": null,
   "n_hours": 264,
   "params": {
    "end_date": "2026-10-24",
    "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m,shortwave_radiation,relative_humidity_2m",
    "latitude": 30.2711,
    "longitude": -97.7437,
    "start_date": "2026-10-14",
    "timezone": "UTC",
    "wind_speed_unit": "ms"
   },
   "start_date": "2026-10-14",
   "url": "https://archive-api.open-meteo.com/v1/archive"
  },
  "valid_hour_histogram": {
   "00": 11,
   "06": 11,
   "12": 11,
   "18": 11
  }
 },
 "CORPUS_CHRISTI": {
  "anchor_breakdown": {
   "candidates": {
    "ml_cooling_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.25386632444444446,
        "mean": 0.18236512122739018,
        "median": 0.1709154336111111,
        "min": 0.11102996861111111,
        "n": 43
       },
       "anchor_to_valid_h": {
        "max": 17.0,
        "mean": 13.752325581395349,
        "median": 13.15,
        "min": 11.333333333333334,
        "n": 43
       },
       "n_rows": 43,
       "scored": {
        "bias": -4.602363108071887,
        "mae": 99.6506837842567,
        "n": 43
       },
       "stations": {
        "KCRP": 43
       }
      },
      "unknown": {
       "anchor_age_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "anchor_to_valid_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "n_rows": 1,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 1
       }
      }
     }
    },
    "ml_wind_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.25386632444444446,
        "mean": 0.18236512122739018,
        "median": 0.1709154336111111,
        "min": 0.11102996861111111,
        "n": 43
       },
       "anchor_to_valid_h": {
        "max": 17.0,
        "mean": 13.752325581395349,
        "median": 13.15,
        "min": 11.333333333333334,
        "n": 43
       },
       "n_rows": 43,
       "scored": {
        "bias": -4.21589076894224,
        "mae": 78.06750264141253,
        "n": 43
       },
       "stations": {
        "KCRP": 43
       }
      },
      "unknown": {
       "anchor_age_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "anchor_to_valid_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "n_rows": 1,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 1
       }
      }
     }
    }
   },
   "label": "exploratory; descriptive only; not a hypothesis test; no adjustment or reweighting"
  },
  "decision_to_valid_gap_hours": {
   "max": 16.75900703611111,
   "mean": 13.573584558402779,
   "median": 12.980214445416667,
   "min": 11.132944785277777,
   "n": 44
  },
  "forecast_model_counts": {
   "<missing>": 5,
   "gfs_seamless": 91
  },
  "logged_at_inversions": 0,
  "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
  "reference_target_hour": {
   "rounding_offset_s_max_abs": 1748.877612,
   "window_end_discrepancy_s": {
    "max": 1186.081232,
    "mean": -215.61110999999997,
    "median": -75.817854,
    "min": -1748.877612,
    "n": 41
   }
  },
  "truth_dropped_null_hours": [],
  "truth_fetch": {
   "end_date": "2026-10-24",
   "error": null,
   "n_hours": 264,
   "params": {
    "end_date": "2026-10-24",
    "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m,shortwave_radiation,relative_humidity_2m",
    "latitude": 27.7635,
    "longitude": -97.4033,
    "start_date": "2026-10-14",
    "timezone": "UTC",
    "wind_speed_unit": "ms"
   },
   "start_date": "2026-10-14",
   "url": "https://archive-api.open-meteo.com/v1/archive"
  },
  "valid_hour_histogram": {
   "00": 11,
   "06": 11,
   "12": 11,
   "18": 11
  }
 },
 "EL_PASO": {
  "anchor_breakdown": {
   "candidates": {
    "ml_cooling_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.3207890208333333,
        "mean": 0.20067258371273713,
        "median": 0.21174612666666667,
        "min": 0.07932849472222223,
        "n": 41
       },
       "anchor_to_valid_h": {
        "max": 16.833333333333332,
        "mean": 13.673983739837398,
        "median": 13.15,
        "min": 11.15,
        "n": 41
       },
       "n_rows": 41,
       "scored": {
        "bias": -22.570429834492636,
        "mae": 127.38849874959607,
        "n": 41
       },
       "stations": {
        "41": 1,
        "KELP": 40
       }
      },
      "tceq": {
       "anchor_age_h": {
        "max": 0.9561883369444445,
        "mean": 0.95174851375,
        "median": 0.95174851375,
        "min": 0.9473086905555556,
        "n": 2
       },
       "anchor_to_valid_h": {
        "max": 16.0,
        "mean": 16.0,
        "median": 16.0,
        "min": 16.0,
        "n": 2
       },
       "n_rows": 2,
       "scored": {
        "bias": -71.35902362990203,
        "mae": 71.35902362990203,
        "n": 2
       },
       "stations": {
        "41": 2
       }
      },
      "unknown": {
       "anchor_age_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "anchor_to_valid_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "n_rows": 1,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 1
       }
      }
     }
    },
    "ml_wind_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.3207890208333333,
        "mean": 0.20067258371273713,
        "median": 0.21174612666666667,
        "min": 0.07932849472222223,
        "n": 41
       },
       "anchor_to_valid_h": {
        "max": 16.833333333333332,
        "mean": 13.673983739837398,
        "median": 13.15,
        "min": 11.15,
        "n": 41
       },
       "n_rows": 41,
       "scored": {
        "bias": -53.10250753301965,
        "mae": 133.023062273731,
        "n": 41
       },
       "stations": {
        "41": 1,
        "KELP": 40
       }
      },
      "tceq": {
       "anchor_age_h": {
        "max": 0.9561883369444445,
        "mean": 0.95174851375,
        "median": 0.95174851375,
        "min": 0.9473086905555556,
        "n": 2
       },
       "anchor_to_valid_h": {
        "max": 16.0,
        "mean": 16.0,
        "median": 16.0,
        "min": 16.0,
        "n": 2
       },
       "n_rows": 2,
       "scored": {
        "bias": -23.17738366068488,
        "mae": 87.82222455362717,
        "n": 2
       },
       "stations": {
        "41": 2
       }
      },
      "unknown": {
       "anchor_age_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "anchor_to_valid_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "n_rows": 1,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 1
       }
      }
     }
    }
   },
   "label": "exploratory; descriptive only; not a hypothesis test; no adjustment or reweighting"
  },
  "decision_to_valid_gap_hours": {
   "max": 16.714653104444444,
   "mean": 13.532371707487375,
   "median": 12.937897232916667,
   "min": 11.070671505277778,
   "n": 44
  },
  "forecast_model_counts": {
   "<missing>": 5,
   "gfs_seamless": 91
  },
  "logged_at_inversions": 0,
  "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
  "reference_target_hour": {
   "rounding_offset_s_max_abs": 1744.485205,
   "window_end_discrepancy_s": {
    "max": 1744.485205,
    "mean": -212.62398281395346,
    "median": -230.906791,
    "min": -1698.005271,
    "n": 43
   }
  },
  "truth_dropped_null_hours": [],
  "truth_fetch": {
   "end_date": "2026-10-24",
   "error": null,
   "n_hours": 264,
   "params": {
    "end_date": "2026-10-24",
    "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m,shortwave_radiation,relative_humidity_2m",
    "latitude": 31.7601,
    "longitude": -106.487,
    "start_date": "2026-10-14",
    "timezone": "UTC",
    "wind_speed_unit": "ms"
   },
   "start_date": "2026-10-14",
   "url": "https://archive-api.open-meteo.com/v1/archive"
  },
  "valid_hour_histogram": {
   "00": 11,
   "06": 11,
   "12": 11,
   "18": 11
  }
 },
 "MIDLAND": {
  "anchor_breakdown": {
   "candidates": {
    "ml_cooling_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.27398226277777776,
        "mean": 0.16510685138888886,
        "median": 0.16056222666666667,
        "min": 0.053350824444444445,
        "n": 42
       },
       "anchor_to_valid_h": {
        "max": 16.833333333333332,
        "mean": 13.653174603174605,
        "median": 13.116666666666667,
        "min": 11.25,
        "n": 42
       },
       "n_rows": 42,
       "scored": {
        "bias": -21.192025127186753,
        "mae": 114.99859399238873,
        "n": 42
       },
       "stations": {
        "KMAF": 42
       }
      },
      "tceq": {
       "anchor_age_h": {
        "max": 0.9137620880555556,
        "mean": 0.9137620880555556,
        "median": 0.9137620880555556,
        "min": 0.9137620880555556,
        "n": 1
       },
       "anchor_to_valid_h": {
        "max": 16.0,
        "mean": 16.0,
        "median": 16.0,
        "min": 16.0,
        "n": 1
       },
       "n_rows": 1,
       "scored": {
        "bias": 300.363147873916,
        "mae": 300.363147873916,
        "n": 1
       },
       "stations": {
        "1095": 1
       }
      },
      "unknown": {
       "anchor_age_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "anchor_to_valid_h": {
        "max": null,
        "mean": null,
        "median": null,
        "min": null,
        "n": 0
       },
       "n_rows": 1,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 1
       }
      }
     }
    },
    "ml_wind_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.30116057944444447,
        "mean": 0.16827089157622738,
        "median": 0.16082203666666667,
        "min": 0.053350824444444445,
        "n": 43
       },
       "anchor_to_valid_h": {
        "max": 16.833333333333332,
        "mean": 13.684496124031007,
        "median": 13.116666666666667,
        "min": 11.25,
        "n": 43
       },
       "n_rows": 43,
       "scored": {
        "bias": -2.4621177109035965,
        "mae": 125.9949443366459,
        "n": 43
       },
       "stations": {
        "KMAF": 43
       }
      },
      "tceq": {
       "anchor_age_h": {
        "max": 0.9137620880555556,
        "mean": 0.9137620880555556,
        "median": 0.9137620880555556,
        "min": 0.9137620880555556,
        "n": 1
       },
       "anchor_to_valid_h": {
        "max": 16.0,
        "mean": 16.0,
        "median": 16.0,
        "min": 16.0,
        "n": 1
       },
       "n_rows": 1,
       "scored": {
        "bias": 254.01607031060712,
        "mae": 254.01607031060712,
        "n": 1
       },
       "stations": {
        "1095": 1
       }
      }
     }
    }
   },
   "label": "exploratory; descriptive only; not a hypothesis test; no adjustment or reweighting"
  },
  "decision_to_valid_gap_hours": {
   "max": 16.721041982777777,
   "mean": 13.551907338806815,
   "median": 12.958006022777777,
   "min": 11.094957064444445,
   "n": 44
  },
  "forecast_model_counts": {
   "<missing>": 5,
   "gfs_seamless": 91
  },
  "logged_at_inversions": 0,
  "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
  "reference_target_hour": {
   "rounding_offset_s_max_abs": 1781.74247,
   "window_end_discrepancy_s": {
    "max": 1781.74247,
    "mean": -119.07162635714286,
    "median": -158.994911,
    "min": -1627.171289,
    "n": 42
   }
  },
  "truth_dropped_null_hours": [],
  "truth_fetch": {
   "end_date": "2026-10-24",
   "error": null,
   "n_hours": 264,
   "params": {
    "end_date": "2026-10-24",
    "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m,shortwave_radiation,relative_humidity_2m",
    "latitude": 31.9974,
    "longitude": -102.0779,
    "start_date": "2026-10-14",
    "timezone": "UTC",
    "wind_speed_unit": "ms"
   },
   "start_date": "2026-10-14",
   "url": "https://archive-api.open-meteo.com/v1/archive"
  },
  "valid_hour_histogram": {
   "00": 11,
   "06": 11,
   "12": 11,
   "18": 11
  }
 }
}
```

## Scope and exclusions

Scored unit: one (city, valid_time) pair; single-conductor ampacity_amps only (bundle not scored, PD-14). Corridor-era rows are never counted. Nothing is imputed, retried or backfilled.

```json
{
 "AUSTIN": {
  "accounting": {
   "in_scope_equals_truth_exclusions_plus_with_truth": true,
   "lines_accepted_equals_exclusions_plus_in_scope": true,
   "per_candidate_with_truth_equals_scored_plus_exclusions": {
    "ml_cooling_corrected": true,
    "ml_wind_corrected": true,
    "persistence_24h": true,
    "raw_forecast": true,
    "reference_ml_refit_24h": true
   }
  },
  "candidate_level": {
   "ml_cooling_corrected": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 2
   },
   "ml_wind_corrected": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 2
   },
   "persistence_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 35
   },
   "raw_forecast": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 0
   },
   "reference_ml_refit_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 4,
    "reference_target_at_or_after_cutoff": 0,
    "reference_target_truth_missing": 0
   }
  },
  "duplicates_excluded": [
   {
    "decision_time": "2026-10-16T00:30:42.196606+00:00",
    "kept_line_no": 16,
    "line_no": 17,
    "logged_at": "2026-10-16T00:30:58.897755+00:00",
    "valid_time": "2026-10-16T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T05:00:51.260405+00:00",
    "kept_line_no": 18,
    "line_no": 19,
    "logged_at": "2026-10-16T05:00:59.936522+00:00",
    "valid_time": "2026-10-16T18:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T11:00:49.273147+00:00",
    "kept_line_no": 20,
    "line_no": 21,
    "logged_at": "2026-10-16T11:02:01.167542+00:00",
    "valid_time": "2026-10-17T00:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T17:00:49.379276+00:00",
    "kept_line_no": 22,
    "line_no": 23,
    "logged_at": "2026-10-16T17:02:00.509533+00:00",
    "valid_time": "2026-10-17T06:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T23:00:46.265030+00:00",
    "kept_line_no": 24,
    "line_no": 25,
    "logged_at": "2026-10-16T23:00:51.277184+00:00",
    "valid_time": "2026-10-17T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T05:00:48.819070+00:00",
    "kept_line_no": 26,
    "line_no": 27,
    "logged_at": "2026-10-17T05:02:02.232523+00:00",
    "valid_time": "2026-10-17T18:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T11:00:44.365463+00:00",
    "kept_line_no": 28,
    "line_no": 29,
    "logged_at": "2026-10-17T11:00:51.593054+00:00",
    "valid_time": "2026-10-18T00:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T17:00:43.440042+00:00",
    "kept_line_no": 30,
    "line_no": 31,
    "logged_at": "2026-10-17T17:00:48.529412+00:00",
    "valid_time": "2026-10-18T06:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T23:00:49.371281+00:00",
    "kept_line_no": 32,
    "line_no": 33,
    "logged_at": "2026-10-17T23:00:54.807956+00:00",
    "valid_time": "2026-10-18T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-21T23:00:56.204885+00:00",
    "kept_line_no": 49,
    "line_no": 50,
    "logged_at": "2026-10-21T23:01:01.601752+00:00",
    "valid_time": "2026-10-22T12:00:00+00:00"
   }
  ],
  "lead_structure_detail": {},
  "other_forecast_model_by_model": {},
  "reader": {
   "accepted_rows": 96,
   "blank": 0,
   "legacy_v1_flat": 0,
   "legacy_v2_corridor": 0,
   "lines_total": 96,
   "malformed": 0,
   "other_city_or_schema": 0
  },
  "row_level": {
   "at_or_after_cutoff": 37,
   "bad_timestamps": 0,
   "duplicate_valid_time": 10,
   "lead_structure_mismatch": 0,
   "missing_forecast_model": 5,
   "other_forecast_model": 0
  },
  "truth": {
   "truth_fetch_failed": 0,
   "truth_missing": 0
  }
 },
 "CORPUS_CHRISTI": {
  "accounting": {
   "in_scope_equals_truth_exclusions_plus_with_truth": true,
   "lines_accepted_equals_exclusions_plus_in_scope": true,
   "per_candidate_with_truth_equals_scored_plus_exclusions": {
    "ml_cooling_corrected": true,
    "ml_wind_corrected": true,
    "persistence_24h": true,
    "raw_forecast": true,
    "reference_ml_refit_24h": true
   }
  },
  "candidate_level": {
   "ml_cooling_corrected": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 1
   },
   "ml_wind_corrected": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 1
   },
   "persistence_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 35
   },
   "raw_forecast": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 0
   },
   "reference_ml_refit_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 3,
    "reference_target_at_or_after_cutoff": 0,
    "reference_target_truth_missing": 0
   }
  },
  "duplicates_excluded": [
   {
    "decision_time": "2026-10-16T00:31:14.668668+00:00",
    "kept_line_no": 16,
    "line_no": 17,
    "logged_at": "2026-10-16T00:32:09.026230+00:00",
    "valid_time": "2026-10-16T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T05:01:15.914035+00:00",
    "kept_line_no": 18,
    "line_no": 19,
    "logged_at": "2026-10-16T05:02:24.596555+00:00",
    "valid_time": "2026-10-16T18:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T11:02:17.162517+00:00",
    "kept_line_no": 20,
    "line_no": 21,
    "logged_at": "2026-10-16T11:04:17.295539+00:00",
    "valid_time": "2026-10-17T00:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T17:02:16.525222+00:00",
    "kept_line_no": 22,
    "line_no": 23,
    "logged_at": "2026-10-16T17:03:11.716064+00:00",
    "valid_time": "2026-10-17T06:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T23:01:07.171705+00:00",
    "kept_line_no": 24,
    "line_no": 25,
    "logged_at": "2026-10-16T23:02:15.508906+00:00",
    "valid_time": "2026-10-17T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T05:02:18.184535+00:00",
    "kept_line_no": 26,
    "line_no": 27,
    "logged_at": "2026-10-17T05:03:13.143863+00:00",
    "valid_time": "2026-10-17T18:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T11:01:07.424429+00:00",
    "kept_line_no": 28,
    "line_no": 29,
    "logged_at": "2026-10-17T11:02:16.811584+00:00",
    "valid_time": "2026-10-18T00:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T17:01:04.383086+00:00",
    "kept_line_no": 30,
    "line_no": 31,
    "logged_at": "2026-10-17T17:01:10.165534+00:00",
    "valid_time": "2026-10-18T06:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T23:01:10.797917+00:00",
    "kept_line_no": 32,
    "line_no": 33,
    "logged_at": "2026-10-17T23:02:18.760513+00:00",
    "valid_time": "2026-10-18T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-21T23:01:17.436066+00:00",
    "kept_line_no": 49,
    "line_no": 50,
    "logged_at": "2026-10-21T23:02:25.247942+00:00",
    "valid_time": "2026-10-22T12:00:00+00:00"
   }
  ],
  "lead_structure_detail": {},
  "other_forecast_model_by_model": {},
  "reader": {
   "accepted_rows": 96,
   "blank": 0,
   "legacy_v1_flat": 0,
   "legacy_v2_corridor": 0,
   "lines_total": 96,
   "malformed": 0,
   "other_city_or_schema": 0
  },
  "row_level": {
   "at_or_after_cutoff": 37,
   "bad_timestamps": 0,
   "duplicate_valid_time": 10,
   "lead_structure_mismatch": 0,
   "missing_forecast_model": 5,
   "other_forecast_model": 0
  },
  "truth": {
   "truth_fetch_failed": 0,
   "truth_missing": 0
  }
 },
 "EL_PASO": {
  "accounting": {
   "in_scope_equals_truth_exclusions_plus_with_truth": true,
   "lines_accepted_equals_exclusions_plus_in_scope": true,
   "per_candidate_with_truth_equals_scored_plus_exclusions": {
    "ml_cooling_corrected": true,
    "ml_wind_corrected": true,
    "persistence_24h": true,
    "raw_forecast": true,
    "reference_ml_refit_24h": true
   }
  },
  "candidate_level": {
   "ml_cooling_corrected": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 1
   },
   "ml_wind_corrected": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 1
   },
   "persistence_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 35
   },
   "raw_forecast": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 1
   },
   "reference_ml_refit_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 1,
    "reference_target_at_or_after_cutoff": 0,
    "reference_target_truth_missing": 0
   }
  },
  "duplicates_excluded": [
   {
    "decision_time": "2026-10-16T00:32:44.987536+00:00",
    "kept_line_no": 16,
    "line_no": 17,
    "logged_at": "2026-10-16T00:33:52.373292+00:00",
    "valid_time": "2026-10-16T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T05:03:51.881844+00:00",
    "kept_line_no": 18,
    "line_no": 19,
    "logged_at": "2026-10-16T05:03:57.406287+00:00",
    "valid_time": "2026-10-16T18:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T11:06:49.658552+00:00",
    "kept_line_no": 20,
    "line_no": 21,
    "logged_at": "2026-10-16T11:08:50.186014+00:00",
    "valid_time": "2026-10-17T00:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T17:04:51.799845+00:00",
    "kept_line_no": 22,
    "line_no": 23,
    "logged_at": "2026-10-16T17:05:46.783043+00:00",
    "valid_time": "2026-10-17T06:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T23:03:42.382498+00:00",
    "kept_line_no": 24,
    "line_no": 25,
    "logged_at": "2026-10-16T23:04:50.182549+00:00",
    "valid_time": "2026-10-17T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T05:04:53.024389+00:00",
    "kept_line_no": 26,
    "line_no": 27,
    "logged_at": "2026-10-17T05:05:48.181820+00:00",
    "valid_time": "2026-10-17T18:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T11:03:45.029036+00:00",
    "kept_line_no": 28,
    "line_no": 29,
    "logged_at": "2026-10-17T11:04:54.442086+00:00",
    "valid_time": "2026-10-18T00:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T17:02:49.197379+00:00",
    "kept_line_no": 30,
    "line_no": 31,
    "logged_at": "2026-10-17T17:03:45.772528+00:00",
    "valid_time": "2026-10-18T06:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T23:03:45.637351+00:00",
    "kept_line_no": 32,
    "line_no": 33,
    "logged_at": "2026-10-17T23:04:53.652992+00:00",
    "valid_time": "2026-10-18T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-21T23:03:51.455564+00:00",
    "kept_line_no": 49,
    "line_no": 50,
    "logged_at": "2026-10-21T23:04:59.481974+00:00",
    "valid_time": "2026-10-22T12:00:00+00:00"
   }
  ],
  "lead_structure_detail": {},
  "other_forecast_model_by_model": {},
  "reader": {
   "accepted_rows": 96,
   "blank": 0,
   "legacy_v1_flat": 0,
   "legacy_v2_corridor": 0,
   "lines_total": 96,
   "malformed": 0,
   "other_city_or_schema": 0
  },
  "row_level": {
   "at_or_after_cutoff": 37,
   "bad_timestamps": 0,
   "duplicate_valid_time": 10,
   "lead_structure_mismatch": 0,
   "missing_forecast_model": 5,
   "other_forecast_model": 0
  },
  "truth": {
   "truth_fetch_failed": 0,
   "truth_missing": 0
  }
 },
 "MIDLAND": {
  "accounting": {
   "in_scope_equals_truth_exclusions_plus_with_truth": true,
   "lines_accepted_equals_exclusions_plus_in_scope": true,
   "per_candidate_with_truth_equals_scored_plus_exclusions": {
    "ml_cooling_corrected": true,
    "ml_wind_corrected": true,
    "persistence_24h": true,
    "raw_forecast": true,
    "reference_ml_refit_24h": true
   }
  },
  "candidate_level": {
   "ml_cooling_corrected": {
    "candidate_failed": 1,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 0
   },
   "ml_wind_corrected": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 0
   },
   "persistence_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 35
   },
   "raw_forecast": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 0
   },
   "reference_ml_refit_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 2,
    "reference_target_at_or_after_cutoff": 0,
    "reference_target_truth_missing": 0
   }
  },
  "duplicates_excluded": [
   {
    "decision_time": "2026-10-16T00:32:24.835508+00:00",
    "kept_line_no": 16,
    "line_no": 17,
    "logged_at": "2026-10-16T00:32:29.192956+00:00",
    "valid_time": "2026-10-16T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T05:02:40.597801+00:00",
    "kept_line_no": 18,
    "line_no": 19,
    "logged_at": "2026-10-16T05:03:35.893950+00:00",
    "valid_time": "2026-10-16T18:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T11:04:33.299659+00:00",
    "kept_line_no": 20,
    "line_no": 21,
    "logged_at": "2026-10-16T11:06:33.560095+00:00",
    "valid_time": "2026-10-17T00:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T17:03:27.800543+00:00",
    "kept_line_no": 22,
    "line_no": 23,
    "logged_at": "2026-10-16T17:04:35.741667+00:00",
    "valid_time": "2026-10-17T06:00:00+00:00"
   },
   {
    "decision_time": "2026-10-16T23:02:31.396795+00:00",
    "kept_line_no": 24,
    "line_no": 25,
    "logged_at": "2026-10-16T23:03:26.441796+00:00",
    "valid_time": "2026-10-17T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T05:03:29.082513+00:00",
    "kept_line_no": 26,
    "line_no": 27,
    "logged_at": "2026-10-17T05:04:37.024551+00:00",
    "valid_time": "2026-10-17T18:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T11:02:32.688466+00:00",
    "kept_line_no": 28,
    "line_no": 29,
    "logged_at": "2026-10-17T11:03:29.174690+00:00",
    "valid_time": "2026-10-18T00:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T17:01:25.956397+00:00",
    "kept_line_no": 30,
    "line_no": 31,
    "logged_at": "2026-10-17T17:02:33.354880+00:00",
    "valid_time": "2026-10-18T06:00:00+00:00"
   },
   {
    "decision_time": "2026-10-17T23:02:34.751378+00:00",
    "kept_line_no": 32,
    "line_no": 33,
    "logged_at": "2026-10-17T23:03:29.646036+00:00",
    "valid_time": "2026-10-18T12:00:00+00:00"
   },
   {
    "decision_time": "2026-10-21T23:02:41.058873+00:00",
    "kept_line_no": 49,
    "line_no": 50,
    "logged_at": "2026-10-21T23:03:35.692625+00:00",
    "valid_time": "2026-10-22T12:00:00+00:00"
   }
  ],
  "lead_structure_detail": {},
  "other_forecast_model_by_model": {},
  "reader": {
   "accepted_rows": 96,
   "blank": 0,
   "legacy_v1_flat": 0,
   "legacy_v2_corridor": 0,
   "lines_total": 96,
   "malformed": 0,
   "other_city_or_schema": 0
  },
  "row_level": {
   "at_or_after_cutoff": 37,
   "bad_timestamps": 0,
   "duplicate_valid_time": 10,
   "lead_structure_mismatch": 0,
   "missing_forecast_model": 5,
   "other_forecast_model": 0
  },
  "truth": {
   "truth_fetch_failed": 0,
   "truth_missing": 0
  }
 }
}
```

## Not measured

Calibrated overrating risk (the overrating rate at the nominal 5% target) and retained capacity were not measured. No 8% ceiling was applied. Candidates are ranked on point error only, which is a weaker standard than v1.

## Planner defaults in force (owner may override)

- PD-01 port model source: the 12 frozen per-city artifacts (not a train-only refit)
- PD-02 port fetch window: 2026-09-28..2026-10-24
- PD-03 block lengths (six-hourly slots): [1, 4, 8, 28]
- PD-04 headline p-value per test: largest two-sided bootstrap p over both pooled schemes and every runnable block length
- PD-05 interval excludes 0 in the ship rule: Holm rejection at family alpha 0.05 with the margin favouring the candidate
- PD-06 pooled statistic: row-weighted
- PD-07 minimum paired rows: 8
- PD-08 MDD power: 0.8
- PD-09 resampling: 10000 resamples, seed 20260929
- PD-10 ship-rule readings: v4 relative margin 2% of the city's mean truth ampacity (pooled, paired-row-weighted), consistency 3 cities
- PD-11 logs: reference own target hour: decision_time + 24 h rounded to the nearest whole UTC hour (half past rounds up)
- PD-12 first-logged: first eligible line in file order
- PD-13 underlying weather model: gfs_seamless
- PD-14 bundle ampacity: not scored
- PD-15 parameter changes: any non-default value in a FRESH run is refused (signed v4 rounds take no override)
- PD-16 freeze check: artifact commits at or after 2026-11-01T00:00Z are flagged, not refused
- PD-17 evidence root: data/shadow/evaluation
- PD-18 protocol round: v4-read1

Owner-pending items:

- protocol v4 governs this evaluation: see docs/data-science/decisions/confirmation_protocol_v4_early_selection_SIGNING_COPY.md

## Evidence files

- 01_archive_AUSTIN.body: sha256 b0b0168461037ca5ee658299ad0a1c91401ffaf7a30dd100f2cecf8d7c027e4d, 11118 bytes, status 200, retrieved 2026-11-02T17:52:10.626746+00:00 .. 2026-11-02T17:52:11.207234+00:00
- 02_archive_CORPUS_CHRISTI.body: sha256 06944d44058870c5d472eb5602c3b3800415d90af9324d2f8c2aa3e61584746c, 11101 bytes, status 200, retrieved 2026-11-02T17:52:11.242050+00:00 .. 2026-11-02T17:52:11.818056+00:00
- 03_archive_MIDLAND.body: sha256 31da236cc7883ed67b3efcf43989d1e9f5ed91c8cc3b5e4f734c782d1db93ff9, 11159 bytes, status 200, retrieved 2026-11-02T17:52:11.853593+00:00 .. 2026-11-02T17:52:12.434676+00:00
- 04_archive_EL_PASO.body: sha256 9d6ea4df2cb655dc42cca568ae04b9659a4c7fa22abb67a0ffcce103e1886d20, 11168 bytes, status 200, retrieved 2026-11-02T17:52:12.472546+00:00 .. 2026-11-02T17:52:13.076252+00:00
