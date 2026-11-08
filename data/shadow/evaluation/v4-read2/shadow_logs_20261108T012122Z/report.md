# Per-city shadow evaluation - row source: shadow logs (live-system check)

Truth: reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated
Basis: FRESH
Protocol status: signed
Round: v4-read2
Evaluation instant: 2026-11-08T00:00:00+00:00
Valid-time cutoff (strict, valid_time < cutoff): 2026-11-01T00:00:00+00:00
Now evaluated: 2026-11-08T01:21:22.061585+00:00
Override: none
Non-default pre-registered values: none
Git SHA: f9be67aa1dee290bcb161a4abe0cb2e99286848f (dirty: True)
Freeze check: all artifact commits are before the 2026-11-01 freeze

## Sample size (read this first)

Precision targets: about 590 rows for tail-rate precision and about 1575 rows for a 5 A minimum detectable difference.
- Pooled NOMINAL n (max over candidates) = 287. This sums rows from cities that share weather and rows six hours apart that are correlated, so it is NOT an effective sample size and is never judged against the ~590 / ~1575 targets here; the targets are judged on effective n in the pair table below.
- AUSTIN: n scored per candidate: ml_wind_corrected=67, ml_cooling_corrected=67, raw_forecast=72, persistence_24h=37, reference_ml_refit_24h=63. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- CORPUS_CHRISTI: n scored per candidate: ml_wind_corrected=71, ml_cooling_corrected=71, raw_forecast=72, persistence_24h=37, reference_ml_refit_24h=67. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- MIDLAND: n scored per candidate: ml_wind_corrected=72, ml_cooling_corrected=71, raw_forecast=72, persistence_24h=37, reference_ml_refit_24h=68. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- EL_PASO: n scored per candidate: ml_wind_corrected=70, ml_cooling_corrected=70, raw_forecast=71, persistence_24h=37, reference_ml_refit_24h=68. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).

| pair (A vs B) | n paired (pooled) | n_eff (bootstrap) | n_eff (ACF, per city) | MDD (amps) | rows needed for 5 A | ~590 (judged on effective n) | ~1,575 (judged on effective n) |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 279 | 144.6 | AUSTIN:45.4, CORPUS_CHRISTI:39.9, MIDLAND:71.0, EL_PASO:62.8 | 26.91 | 8085 | not met | not met |
| ml_wind_corrected vs reference_ml_refit_24h | 265 | 57.8 | AUSTIN:26.7, CORPUS_CHRISTI:36.1, MIDLAND:46.8, EL_PASO:48.2 | 76.20 | 61552 | not met | not met |
| ml_cooling_corrected vs reference_ml_refit_24h | 265 | 58.2 | AUSTIN:24.0, CORPUS_CHRISTI:61.1, MIDLAND:47.5, EL_PASO:67.0 | 73.10 | 56636 | not met | not met |
| ml_wind_corrected vs raw_forecast | 280 | 100.3 | AUSTIN:53.7, CORPUS_CHRISTI:65.2, MIDLAND:72.0, EL_PASO:67.8 | 35.32 | 13976 | not met | not met |
| ml_cooling_corrected vs raw_forecast | 279 | 195.3 | AUSTIN:67.0, CORPUS_CHRISTI:52.8, MIDLAND:71.0, EL_PASO:48.7 | 23.04 | 5923 | not met | not met |
| reference_ml_refit_24h vs raw_forecast | 265 | 74.8 | AUSTIN:62.1, CORPUS_CHRISTI:37.3, MIDLAND:47.9, EL_PASO:67.0 | 70.09 | 52067 | not met | not met |
| ml_wind_corrected vs persistence_24h | 143 | 44.6 | AUSTIN:33.0, CORPUS_CHRISTI:37.0, MIDLAND:31.4, EL_PASO:27.8 | 96.46 | 53227 | not met | not met |
| ml_cooling_corrected vs persistence_24h | 143 | 56.6 | AUSTIN:33.0, CORPUS_CHRISTI:37.0, MIDLAND:34.1, EL_PASO:30.5 | 74.19 | 31486 | not met | not met |
| reference_ml_refit_24h vs persistence_24h | 130 | 45.3 | AUSTIN:25.9, CORPUS_CHRISTI:33.0, MIDLAND:17.7, EL_PASO:33.0 | 98.48 | 50428 | not met | not met |

## Headline family: 9 tests, pooled, city-clustered, Holm at 0.05

Margin = mean|e_B| - mean|e_A| in amps, so a positive margin means A has the lower MAE. Reanalysis-derived, never sensor-validated.

| A vs B | n | margin (A) | rel. MAE reduction | cities favouring A | headline p | Holm-adj. p | outcome | flags |
|---|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 279 | 0.90 | 0.007 | 2 of 4 | 0.8633 | 1.0000 | inconclusive | V1_live_anchor, V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs reference_ml_refit_24h | 265 | 39.52 | 0.243 | 3 of 4 | 0.0318 | 0.2226 | inconclusive | V1_live_anchor, V2_reference_target_hour, V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs reference_ml_refit_24h | 265 | 36.08 | 0.222 | 4 of 4 | 0.0380 | 0.2226 | inconclusive | V1_live_anchor, V2_reference_target_hour, V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs raw_forecast | 280 | 0.85 | 0.007 | 2 of 4 | 0.9215 | 1.0000 | inconclusive | V1_live_anchor, V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs raw_forecast | 279 | -0.01 | -0.000 | 2 of 4 | 0.9905 | 1.0000 | inconclusive | V1_live_anchor, V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs raw_forecast | 265 | -36.72 | -0.292 | 0 of 4 | 0.0368 | 0.2226 | inconclusive | V2_reference_target_hour, V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs persistence_24h | 143 | 59.79 | 0.288 | 4 of 4 | 0.0108 | 0.0864 | inconclusive | V1_live_anchor, V3_live_persistence_definition, V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs persistence_24h | 143 | 64.12 | 0.309 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V1_live_anchor, V3_live_persistence_definition, V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs persistence_24h | 130 | 44.83 | 0.221 | 3 of 4 | 0.1092 | 0.4368 | inconclusive | V2_reference_target_hour, V3_live_persistence_definition, V4_reanalysis_truth_shared_weather |

Headline intervals (widest 95% and widest Bonferroni (1 - 0.05/9) over both pooled schemes and every runnable block length):

- ml_wind_corrected vs ml_cooling_corrected: 95% [-13.05, 17.95]; Bonferroni [-18.65, 24.40]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs reference_ml_refit_24h: 95% [3.61, 86.28]; Bonferroni [-8.89, 104.03]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs reference_ml_refit_24h: 95% [1.38, 79.75]; Bonferroni [-7.06, 98.26]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs raw_forecast: 95% [-15.85, 22.82]; Bonferroni [-22.97, 27.10]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs raw_forecast: 95% [-14.18, 11.58]; Bonferroni [-18.55, 16.02]; block lengths run [1, 4, 8, 28], skipped []
- reference_ml_refit_24h vs raw_forecast: 95% [-80.16, -1.49]; Bonferroni [-97.08, 8.16]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs persistence_24h: 95% [9.41, 115.13]; Bonferroni [-2.42, 138.73]; block lengths run [1, 4, 8], skipped [28]
- ml_cooling_corrected vs persistence_24h: 95% [27.06, 106.87]; Bonferroni [15.02, 125.93]; block lengths run [1, 4, 8], skipped [28]
- reference_ml_refit_24h vs persistence_24h: 95% [-12.31, 96.91]; Bonferroni [-43.06, 114.62]; block lengths run [1, 4, 8], skipped [28]

## Decision (live-system check)

Label: live-system check, never decides. Round: v4-read2. Rule: v4. Protocol status: signed.

Bars: 2% of each city's mean truth ampacity over its scored rows (amps):
- Bar AUSTIN: 24.33 A
- Bar CORPUS_CHRISTI: 28.93 A
- Bar MIDLAND: 32.27 A
- Bar EL_PASO: 24.44 A

Each candidate against raw_forecast (pooled benefit against the pooled bar):
- ml_wind_corrected vs raw_forecast: **not shown** (benefit 0.85 A, pooled bar 27.57 A, Holm-adjusted p 1.0000; favoured in 2 of 4 cities, not consistent; not vetoed; veto records consulted: no veto record applied (development basis))
- ml_cooling_corrected vs raw_forecast: **not shown** (benefit -0.01 A, pooled bar 27.55 A, Holm-adjusted p 1.0000; favoured in 2 of 4 cities, not consistent; not vetoed; veto records consulted: no veto record applied (development basis))
- reference_ml_refit_24h vs raw_forecast: **not shown** (benefit -36.72 A, pooled bar 27.56 A, Holm-adjusted p 0.2226; favoured in 0 of 4 cities, not consistent; not vetoed; veto records consulted: no veto record applied (development basis))

- ml_cooling_corrected vs ml_wind_corrected: pooled margin -0.90 A against a pooled bar of 27.55 A, favoured in 2 of 4 cities, consistently better: False
- reference_ml_refit_24h vs ml_wind_corrected: pooled margin -39.52 A against a pooled bar of 27.56 A, favoured in 1 of 4 cities, consistently better: False

Reported pick: None (live-system check, never decides). Would-be outcome under the v4 rule: no candidate qualifies.

- Sample size: pooled paired rows per headline test range from 130 to 280 (nominal, not effective; effective sample sizes are smaller because six-hourly rows and the four cities share weather); both precision targets (about 590 rows for the tail rate, about 1,575 rows for a 5 A minimum detectable difference) were not met for any headline test.
- This is the live-system check, never decides: its pick is always None. Under the v4 rule its would-be outcome is no candidate qualifies.
- no ABLATION/TEST veto record was applied (development basis)
- Per-city results are descriptive and uncorrected; the headline is the pooled, city-clustered 9-test family with Holm correction at 0.05.
- Calibrated overrating risk (the overrating rate at the nominal 5% target) and retained capacity were not measured. No 8% ceiling was applied. Candidates are ranked on point error only, which is a weaker standard than v1.
- reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated.
- exploratory: thresholds not pre-registered in a signed protocol

## Per-city descriptive metrics (reanalysis-derived, never sensor-validated)

bias = prediction - truth (positive means capacity overstated). Over-prediction rate and overshoot are descriptive; not the calibrated 5%-target rate; not compared with 8%.

### AUSTIN
Rows in scope: 72; excluded by reason: {'missing_forecast_model': 5, 'at_or_after_cutoff': 31, 'duplicate_valid_time': 10}

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 67 | -58.73 | 126.06 | 159.69 | 108.85 | 0.388 | 86.75 / 186.25 / 223.48 |
| ml_cooling_corrected | 67 | 12.85 | 127.15 | 159.90 | 112.12 | 0.552 | 126.76 / 346.14 / 368.27 |
| raw_forecast | 72 | 14.07 | 122.32 | 164.41 | 86.62 | 0.542 | 125.90 / 324.96 / 383.33 |
| persistence_24h | 37 | -33.34 | 184.82 | 236.25 | 149.64 | 0.378 | 200.17 / 467.86 / 563.82 |
| reference_ml_refit_24h | 63 | 100.51 | 169.55 | 198.04 | 159.33 | 0.714 | 189.04 / 346.06 / 385.46 |
| reference_ml_refit_24h (logged valid_time reading; flagged V2_logged_hour_reading_compares_a_different_hour) | 63 | 72.29 | 167.26 | 202.63 | 168.25 | 0.667 | 179.66 / 342.03 / 467.99 |

Candidate-level exclusions: ml_wind_corrected: {'candidate_unavailable': 5}; ml_cooling_corrected: {'candidate_unavailable': 5}; persistence_24h: {'candidate_unavailable': 35}; reference_ml_refit_24h: {'candidate_unavailable': 8, 'reference_target_at_or_after_cutoff': 1}

### CORPUS_CHRISTI
Rows in scope: 72; excluded by reason: {'missing_forecast_model': 5, 'at_or_after_cutoff': 31, 'duplicate_valid_time': 10}

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 71 | 3.64 | 105.62 | 139.74 | 68.07 | 0.507 | 107.74 / 310.05 / 362.72 |
| ml_cooling_corrected | 71 | -1.95 | 119.39 | 146.92 | 107.60 | 0.479 | 122.62 / 317.47 / 386.26 |
| raw_forecast | 72 | 13.82 | 120.87 | 158.90 | 91.61 | 0.583 | 115.45 / 246.80 / 376.40 |
| persistence_24h | 37 | 36.26 | 258.09 | 319.86 | 201.77 | 0.622 | 236.76 / 549.69 / 597.78 |
| reference_ml_refit_24h | 67 | -20.03 | 133.53 | 169.92 | 113.01 | 0.418 | 135.79 / 272.72 / 406.20 |
| reference_ml_refit_24h (logged valid_time reading; flagged V2_logged_hour_reading_compares_a_different_hour) | 67 | -42.26 | 198.98 | 236.53 | 176.71 | 0.433 | 181.04 / 424.29 / 460.95 |

Candidate-level exclusions: ml_wind_corrected: {'candidate_unavailable': 1}; ml_cooling_corrected: {'candidate_unavailable': 1}; persistence_24h: {'candidate_unavailable': 35}; reference_ml_refit_24h: {'candidate_unavailable': 4, 'reference_target_at_or_after_cutoff': 1}

### MIDLAND
Rows in scope: 72; excluded by reason: {'missing_forecast_model': 5, 'at_or_after_cutoff': 31, 'duplicate_valid_time': 10}

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 72 | 16.92 | 140.99 | 205.00 | 82.64 | 0.444 | 177.65 / 494.13 / 793.50 |
| ml_cooling_corrected | 71 | 6.89 | 130.73 | 175.37 | 90.74 | 0.408 | 168.47 / 414.06 / 578.17 |
| raw_forecast | 72 | -5.01 | 145.62 | 203.03 | 96.57 | 0.431 | 163.29 / 457.16 / 781.71 |
| persistence_24h | 37 | 7.04 | 204.65 | 248.39 | 212.72 | 0.514 | 206.13 / 436.45 / 485.55 |
| reference_ml_refit_24h | 68 | -77.78 | 212.99 | 267.14 | 179.58 | 0.294 | 229.86 / 536.28 / 874.21 |
| reference_ml_refit_24h (logged valid_time reading; flagged V2_logged_hour_reading_compares_a_different_hour) | 68 | -58.33 | 183.48 | 237.65 | 140.83 | 0.397 | 157.59 / 494.59 / 619.14 |

Candidate-level exclusions: ml_cooling_corrected: {'candidate_failed': 1}; persistence_24h: {'candidate_unavailable': 35}; reference_ml_refit_24h: {'candidate_unavailable': 3, 'reference_target_at_or_after_cutoff': 1}

### EL_PASO
Rows in scope: 72; excluded by reason: {'missing_forecast_model': 5, 'at_or_after_cutoff': 31, 'duplicate_valid_time': 10}

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 70 | -24.77 | 140.01 | 177.53 | 117.14 | 0.471 | 122.22 / 344.64 / 425.15 |
| ml_cooling_corrected | 70 | 14.71 | 129.68 | 170.20 | 94.95 | 0.500 | 144.40 / 362.22 / 545.04 |
| raw_forecast | 71 | 56.66 | 133.00 | 179.68 | 103.22 | 0.606 | 156.58 / 459.90 / 609.18 |
| persistence_24h | 37 | 49.09 | 178.03 | 216.04 | 157.48 | 0.595 | 190.98 / 365.41 / 452.14 |
| reference_ml_refit_24h | 68 | 19.68 | 133.47 | 160.02 | 125.04 | 0.618 | 123.97 / 263.03 / 298.05 |
| reference_ml_refit_24h (logged valid_time reading; flagged V2_logged_hour_reading_compares_a_different_hour) | 68 | 57.57 | 143.93 | 176.31 | 123.80 | 0.632 | 159.32 / 345.33 / 467.35 |

Candidate-level exclusions: ml_wind_corrected: {'candidate_unavailable': 2}; ml_cooling_corrected: {'candidate_unavailable': 2}; raw_forecast: {'candidate_unavailable': 1}; persistence_24h: {'candidate_unavailable': 35}; reference_ml_refit_24h: {'candidate_unavailable': 3, 'reference_target_at_or_after_cutoff': 1}


## Per-city comparisons (descriptive, uncorrected)

- ml_wind_corrected vs ml_cooling_corrected:
  - AUSTIN: n=67 margin=1.09 outcome=inconclusive (crosses_zero) L=1: [-22.82, 24.86]; L=4: [-28.53, 26.45]; L=8: [-25.96, 25.88]; L=28: [-12.97, 23.02] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=71 margin=13.77 outcome=inconclusive (block_length_sensitive) L=1: [-2.80, 29.38]; L=4: [0.92, 34.41]; L=8: [3.52, 36.64]; L=28: [12.02, 28.09] - descriptive, uncorrected
  - MIDLAND: n=71 margin=-1.07 outcome=inconclusive (crosses_zero) L=1: [-15.85, 12.11]; L=4: [-12.71, 12.69]; L=8: [-11.94, 11.56]; L=28: [-4.25, 10.55] - descriptive, uncorrected
  - EL_PASO: n=70 margin=-10.33 outcome=inconclusive (crosses_zero) L=1: [-37.28, 17.21]; L=4: [-36.30, 19.38]; L=8: [-31.94, 22.85]; L=28: [-33.72, 18.44] - descriptive, uncorrected
- ml_wind_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=63 margin=46.52 outcome=inconclusive (block_length_sensitive) L=1: [8.74, 81.90]; L=4: [-7.87, 87.88]; L=8: [-13.03, 92.12]; L=28: [-4.71, 101.11] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=67 margin=29.59 outcome=inconclusive (block_length_sensitive) L=1: [-2.92, 61.38]; L=4: [0.08, 72.30]; L=8: [-0.39, 77.15]; L=28: [5.06, 55.83] - descriptive, uncorrected
  - MIDLAND: n=68 margin=84.96 outcome=favors_A L=1: [38.96, 134.29]; L=4: [36.63, 142.88]; L=8: [36.53, 155.34]; L=28: [68.05, 125.60] - descriptive, uncorrected
  - EL_PASO: n=67 margin=-3.23 outcome=inconclusive (crosses_zero) L=1: [-35.17, 29.22]; L=4: [-35.04, 33.13]; L=8: [-36.31, 33.38]; L=28: [-37.61, 40.04] - descriptive, uncorrected
- ml_cooling_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=63 margin=42.16 outcome=inconclusive (block_length_sensitive) L=1: [8.02, 75.78]; L=4: [-1.63, 76.41]; L=8: [-9.96, 83.12]; L=28: [-11.92, 88.49] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=67 margin=16.91 outcome=inconclusive (crosses_zero) L=1: [-12.35, 45.24]; L=4: [-9.23, 48.40]; L=8: [-6.57, 48.94]; L=28: [-4.10, 33.12] - descriptive, uncorrected
  - MIDLAND: n=68 margin=84.01 outcome=favors_A L=1: [40.01, 132.38]; L=4: [37.47, 137.88]; L=8: [40.73, 150.45]; L=28: [67.09, 120.05] - descriptive, uncorrected
  - EL_PASO: n=67 margin=0.88 outcome=inconclusive (crosses_zero) L=1: [-32.06, 33.42]; L=4: [-29.62, 30.10]; L=8: [-27.21, 25.81]; L=28: [-21.58, 25.92] - descriptive, uncorrected
- ml_wind_corrected vs raw_forecast:
  - AUSTIN: n=67 margin=-9.04 outcome=inconclusive (crosses_zero) L=1: [-34.11, 16.48]; L=4: [-38.30, 15.66]; L=8: [-39.22, 17.35]; L=28: [-31.51, 18.06] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=71 margin=13.70 outcome=inconclusive (crosses_zero) L=1: [-8.39, 35.64]; L=4: [-4.40, 36.55]; L=8: [-4.57, 35.97]; L=28: [-0.18, 39.69] - descriptive, uncorrected
  - MIDLAND: n=72 margin=4.63 outcome=inconclusive (crosses_zero) L=1: [-8.54, 18.15]; L=4: [-7.42, 17.62]; L=8: [-8.40, 20.17]; L=28: [-4.97, 23.27] - descriptive, uncorrected
  - EL_PASO: n=70 margin=-6.59 outcome=inconclusive (crosses_zero) L=1: [-35.51, 22.04]; L=4: [-35.84, 21.78]; L=8: [-36.95, 22.73]; L=28: [-36.12, 18.66] - descriptive, uncorrected
- ml_cooling_corrected vs raw_forecast:
  - AUSTIN: n=67 margin=-10.14 outcome=inconclusive (crosses_zero) L=1: [-32.52, 12.54]; L=4: [-29.80, 9.30]; L=8: [-28.55, 6.24]; L=28: [-27.44, 7.29] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=71 margin=-0.07 outcome=inconclusive (crosses_zero) L=1: [-21.68, 21.81]; L=4: [-25.44, 21.48]; L=8: [-27.11, 21.06]; L=28: [-24.15, 23.49] - descriptive, uncorrected
  - MIDLAND: n=71 margin=5.93 outcome=inconclusive (crosses_zero) L=1: [-8.73, 21.90]; L=4: [-6.89, 16.47]; L=8: [-5.83, 17.21]; L=28: [-4.08, 18.09] - descriptive, uncorrected
  - EL_PASO: n=70 margin=3.74 outcome=inconclusive (crosses_zero) L=1: [-19.83, 26.85]; L=4: [-20.76, 25.29]; L=8: [-23.13, 17.67]; L=28: [-10.18, 9.62] - descriptive, uncorrected
- reference_ml_refit_24h vs raw_forecast:
  - AUSTIN: n=63 margin=-51.41 outcome=favors_B L=1: [-89.46, -13.20]; L=4: [-83.20, -8.21]; L=8: [-84.42, -8.36]; L=28: [-82.89, -12.07] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=67 margin=-15.08 outcome=inconclusive (crosses_zero) L=1: [-52.31, 22.88]; L=4: [-62.25, 25.74]; L=8: [-65.48, 26.02]; L=28: [-38.02, 26.67] - descriptive, uncorrected
  - MIDLAND: n=68 margin=-78.54 outcome=favors_B L=1: [-127.64, -33.57]; L=4: [-136.00, -32.66]; L=8: [-149.33, -31.74]; L=28: [-114.34, -55.60] - descriptive, uncorrected
  - EL_PASO: n=67 margin=-2.09 outcome=inconclusive (crosses_zero) L=1: [-35.72, 32.39]; L=4: [-28.81, 22.12]; L=8: [-25.73, 18.09]; L=28: [-25.04, 15.65] - descriptive, uncorrected
- ml_wind_corrected vs persistence_24h:
  - AUSTIN: n=33 margin=31.66 outcome=inconclusive (crosses_zero) L=1: [-20.39, 86.70]; L=4: [-22.02, 62.31]; L=8: [-18.25, 58.64] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=37 margin=128.81 outcome=favors_A L=1: [61.40, 194.76]; L=4: [63.59, 191.85]; L=8: [76.12, 180.84] - descriptive, uncorrected
  - MIDLAND: n=37 margin=61.96 outcome=favors_A L=1: [7.53, 114.98]; L=4: [8.87, 104.21]; L=8: [16.82, 78.52] - descriptive, uncorrected
  - EL_PASO: n=36 margin=12.43 outcome=inconclusive (crosses_zero) L=1: [-36.19, 60.66]; L=4: [-31.25, 60.06]; L=8: [-21.28, 62.23] - descriptive, uncorrected
- ml_cooling_corrected vs persistence_24h:
  - AUSTIN: n=33 margin=27.70 outcome=inconclusive (block_length_sensitive) L=1: [-11.78, 70.08]; L=4: [-7.52, 60.11]; L=8: [1.80, 64.05] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=37 margin=113.39 outcome=favors_A L=1: [49.12, 177.01]; L=4: [45.29, 167.31]; L=8: [59.43, 149.40] - descriptive, uncorrected
  - MIDLAND: n=37 margin=67.21 outcome=favors_A L=1: [18.06, 118.06]; L=4: [17.86, 103.98]; L=8: [23.52, 79.79] - descriptive, uncorrected
  - EL_PASO: n=36 margin=43.69 outcome=favors_A L=1: [9.38, 77.85]; L=4: [13.61, 73.19]; L=8: [16.83, 70.83] - descriptive, uncorrected
- reference_ml_refit_24h vs persistence_24h:
  - AUSTIN: n=30 margin=34.75 outcome=inconclusive (block_length_sensitive) L=1: [-24.54, 95.69]; L=4: [-16.24, 99.06]; L=8: [8.36, 97.86] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=33 margin=97.59 outcome=favors_A L=1: [24.43, 173.85]; L=4: [25.12, 160.12]; L=8: [46.05, 136.50] - descriptive, uncorrected
  - MIDLAND: n=34 margin=-17.16 outcome=inconclusive (crosses_zero) L=1: [-77.18, 40.98]; L=4: [-101.59, 45.72]; L=8: [-113.94, 45.42] - descriptive, uncorrected
  - EL_PASO: n=33 margin=65.10 outcome=favors_A L=1: [17.83, 111.85]; L=4: [26.49, 107.16]; L=8: [36.85, 106.86] - descriptive, uncorrected

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
        "mean": 0.14868792449834162,
        "median": 0.13079174,
        "min": 0.08994184361111111,
        "n": 67
       },
       "anchor_to_valid_h": {
        "max": 17.0,
        "mean": 13.528109452736322,
        "median": 13.116666666666667,
        "min": 11.333333333333334,
        "n": 67
       },
       "n_rows": 67,
       "scored": {
        "bias": 12.850361887690175,
        "mae": 127.14779618022897,
        "n": 67
       },
       "stations": {
        "KAUS": 67
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
       "n_rows": 5,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 5
       }
      }
     }
    },
    "ml_wind_corrected": {
     "by_source": {
      "synoptic": {
       "anchor_age_h": {
        "max": 0.3815234913888889,
        "mean": 0.14868792449834162,
        "median": 0.13079174,
        "min": 0.08994184361111111,
        "n": 67
       },
       "anchor_to_valid_h": {
        "max": 17.0,
        "mean": 13.528109452736322,
        "median": 13.116666666666667,
        "min": 11.333333333333334,
        "n": 67
       },
       "n_rows": 67,
       "scored": {
        "bias": -58.72994469185339,
        "mae": 126.05721938206828,
        "n": 67
       },
       "stations": {
        "KAUS": 67
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
       "n_rows": 5,
       "scored": {
        "bias": null,
        "mae": null,
        "n": 0
       },
       "stations": {
        "unknown": 5
       }
      }
     }
    }
   },
   "label": "exploratory; descriptive only; not a hypothesis test; no adjustment or reweighting"
  },
  "decision_to_valid_gap_hours": {
   "max": 16.783626738333332,
   "mean": 13.352083095181326,
   "median": 12.986660589583334,
   "min": 11.157189704444445,
   "n": 72
  },
  "forecast_model_counts": {
   "<missing>": 5,
   "gfs_seamless": 113
  },
  "logged_at_inversions": 0,
  "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
  "reference_target_hour": {
   "rounding_offset_s_max_abs": 1727.492334,
   "window_end_discrepancy_s": {
    "max": 1273.760364,
    "mean": -128.994791078125,
    "median": -49.679477500000004,
    "min": -1727.492334,
    "n": 64
   }
  },
  "truth_dropped_null_hours": [],
  "truth_fetch": {
   "end_date": "2026-10-31",
   "error": null,
   "n_hours": 432,
   "params": {
    "end_date": "2026-10-31",
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
   "00": 18,
   "06": 18,
   "12": 18,
   "18": 18
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
        "mean": 0.17924236557511733,
        "median": 0.17052946027777777,
        "min": 0.11102996861111111,
        "n": 71
       },
       "anchor_to_valid_h": {
        "max": 17.0,
        "mean": 13.514788732394367,
        "median": 13.15,
        "min": 11.333333333333334,
        "n": 71
       },
       "n_rows": 71,
       "scored": {
        "bias": -1.948131485439102,
        "mae": 119.3853829996895,
        "n": 71
       },
       "stations": {
        "KCRP": 71
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
        "mean": 0.17924236557511733,
        "median": 0.17052946027777777,
        "min": 0.11102996861111111,
        "n": 71
       },
       "anchor_to_valid_h": {
        "max": 17.0,
        "mean": 13.514788732394367,
        "median": 13.15,
        "min": 11.333333333333334,
        "n": 71
       },
       "n_rows": 71,
       "scored": {
        "bias": 3.6415315535091044,
        "mae": 105.61812061431003,
        "n": 71
       },
       "stations": {
        "KCRP": 71
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
   "mean": 13.341016844814815,
   "median": 12.98009259625,
   "min": 11.132944785277777,
   "n": 72
  },
  "forecast_model_counts": {
   "<missing>": 5,
   "gfs_seamless": 113
  },
  "logged_at_inversions": 0,
  "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
  "reference_target_hour": {
   "rounding_offset_s_max_abs": 1748.877612,
   "window_end_discrepancy_s": {
    "max": 1186.081232,
    "mean": -165.4389491617647,
    "median": -73.67868100000001,
    "min": -1748.877612,
    "n": 68
   }
  },
  "truth_dropped_null_hours": [],
  "truth_fetch": {
   "end_date": "2026-10-31",
   "error": null,
   "n_hours": 432,
   "params": {
    "end_date": "2026-10-31",
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
   "00": 18,
   "06": 18,
   "12": 18,
   "18": 18
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
        "mean": 0.19747957563725493,
        "median": 0.21167052458333335,
        "min": 0.07932849472222223,
        "n": 68
       },
       "anchor_to_valid_h": {
        "max": 16.833333333333332,
        "mean": 13.458088235294117,
        "median": 13.15,
        "min": 11.15,
        "n": 68
       },
       "n_rows": 68,
       "scored": {
        "bias": 17.246442511379033,
        "mae": 131.39972342234148,
        "n": 68
       },
       "stations": {
        "41": 1,
        "KELP": 67
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
        "max": 0.3207890208333333,
        "mean": 0.19747957563725493,
        "median": 0.21167052458333335,
        "min": 0.07932849472222223,
        "n": 68
       },
       "anchor_to_valid_h": {
        "max": 16.833333333333332,
        "mean": 13.458088235294117,
        "median": 13.15,
        "min": 11.15,
        "n": 68
       },
       "n_rows": 68,
       "scored": {
        "bias": -24.82135100088115,
        "mae": 141.54626893846404,
        "n": 68
       },
       "stations": {
        "41": 1,
        "KELP": 67
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
   "max": 16.714653104444444,
   "mean": 13.301507262785494,
   "median": 12.93714277013889,
   "min": 11.070671505277778,
   "n": 72
  },
  "forecast_model_counts": {
   "<missing>": 5,
   "gfs_seamless": 113
  },
  "logged_at_inversions": 0,
  "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
  "reference_target_hour": {
   "rounding_offset_s_max_abs": 1744.485205,
   "window_end_discrepancy_s": {
    "max": 1744.485205,
    "mean": -218.52879423188406,
    "median": -230.097325,
    "min": -1698.005271,
    "n": 69
   }
  },
  "truth_dropped_null_hours": [],
  "truth_fetch": {
   "end_date": "2026-10-31",
   "error": null,
   "n_hours": 432,
   "params": {
    "end_date": "2026-10-31",
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
   "00": 18,
   "06": 18,
   "12": 18,
   "18": 18
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
        "mean": 0.16141468068650794,
        "median": 0.16001749777777777,
        "min": 0.053350824444444445,
        "n": 70
       },
       "anchor_to_valid_h": {
        "max": 16.833333333333332,
        "mean": 13.43714285714286,
        "median": 13.116666666666667,
        "min": 11.25,
        "n": 70
       },
       "n_rows": 70,
       "scored": {
        "bias": 2.6994628502209284,
        "mae": 128.30885917486756,
        "n": 70
       },
       "stations": {
        "KMAF": 70
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
        "mean": 0.16338293278169014,
        "median": 0.16008454194444444,
        "min": 0.053350824444444445,
        "n": 71
       },
       "anchor_to_valid_h": {
        "max": 16.833333333333332,
        "mean": 13.459154929577469,
        "median": 13.116666666666667,
        "min": 11.25,
        "n": 71
       },
       "n_rows": 71,
       "scored": {
        "bias": 13.5829594409727,
        "mae": 139.39872183728366,
        "n": 71
       },
       "stations": {
        "KMAF": 71
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
   "mean": 13.320639578950615,
   "median": 12.957153358749999,
   "min": 11.094957064444445,
   "n": 72
  },
  "forecast_model_counts": {
   "<missing>": 5,
   "gfs_seamless": 113
  },
  "logged_at_inversions": 0,
  "reference_headline": "own target hour (decision_time + 24 h, nearest whole hour)",
  "reference_target_hour": {
   "rounding_offset_s_max_abs": 1781.74247,
   "window_end_discrepancy_s": {
    "max": 1781.74247,
    "mean": -133.6546457826087,
    "median": -156.918102,
    "min": -1627.171289,
    "n": 69
   }
  },
  "truth_dropped_null_hours": [],
  "truth_fetch": {
   "end_date": "2026-10-31",
   "error": null,
   "n_hours": 432,
   "params": {
    "end_date": "2026-10-31",
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
   "00": 18,
   "06": 18,
   "12": 18,
   "18": 18
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
    "candidate_unavailable": 5
   },
   "ml_wind_corrected": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 5
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
    "candidate_unavailable": 8,
    "reference_target_at_or_after_cutoff": 1,
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
   "accepted_rows": 118,
   "blank": 0,
   "legacy_v1_flat": 0,
   "legacy_v2_corridor": 0,
   "lines_total": 118,
   "malformed": 0,
   "other_city_or_schema": 0
  },
  "row_level": {
   "at_or_after_cutoff": 31,
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
    "candidate_unavailable": 4,
    "reference_target_at_or_after_cutoff": 1,
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
   "accepted_rows": 118,
   "blank": 0,
   "legacy_v1_flat": 0,
   "legacy_v2_corridor": 0,
   "lines_total": 118,
   "malformed": 0,
   "other_city_or_schema": 0
  },
  "row_level": {
   "at_or_after_cutoff": 31,
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
    "candidate_unavailable": 1
   },
   "reference_ml_refit_24h": {
    "candidate_failed": 0,
    "candidate_fallback_used": 0,
    "candidate_missing": 0,
    "candidate_null_or_nonfinite_value": 0,
    "candidate_unavailable": 3,
    "reference_target_at_or_after_cutoff": 1,
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
   "accepted_rows": 118,
   "blank": 0,
   "legacy_v1_flat": 0,
   "legacy_v2_corridor": 0,
   "lines_total": 118,
   "malformed": 0,
   "other_city_or_schema": 0
  },
  "row_level": {
   "at_or_after_cutoff": 31,
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
    "candidate_unavailable": 3,
    "reference_target_at_or_after_cutoff": 1,
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
   "accepted_rows": 118,
   "blank": 0,
   "legacy_v1_flat": 0,
   "legacy_v2_corridor": 0,
   "lines_total": 118,
   "malformed": 0,
   "other_city_or_schema": 0
  },
  "row_level": {
   "at_or_after_cutoff": 31,
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

- 01_archive_AUSTIN.body: sha256 8ae1a022f3515c62ed9857742d1d2233ce0c8d1d49e38fd2ab6f5f1e893f9ed6, 17894 bytes, status 200, retrieved 2026-11-08T01:21:22.589691+00:00 .. 2026-11-08T01:21:23.215255+00:00
- 02_archive_CORPUS_CHRISTI.body: sha256 7a44cbcc2c4805211216db43b03e18830af4475d9fb6be83eaa92d7ee884f12c, 17867 bytes, status 200, retrieved 2026-11-08T01:21:23.263133+00:00 .. 2026-11-08T01:21:23.885821+00:00
- 03_archive_MIDLAND.body: sha256 46e1cb13a88a3d4b7badd971ddb243f7271be4ca9aa12c48bd3d5d23fe028781, 17988 bytes, status 200, retrieved 2026-11-08T01:21:23.920435+00:00 .. 2026-11-08T01:21:24.538522+00:00
- 04_archive_EL_PASO.body: sha256 6ed7342a1d31793055aa06b966390e1df1c30ed70767d2cb88c0ae09bcf73968, 17978 bytes, status 200, retrieved 2026-11-08T01:21:24.584977+00:00 .. 2026-11-08T01:21:25.202599+00:00
