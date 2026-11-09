# Per-city shadow evaluation - row source: reconstructed frames (headline source)

Truth: reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated
Basis: FRESH
Protocol status: signed
Round: v4-read2
Evaluation instant: 2026-11-08T00:00:00+00:00
Valid-time cutoff (strict, valid_time < cutoff): 2026-11-01T00:00:00+00:00
Now evaluated: 2026-11-08T01:21:06.342299+00:00
Override: none
Non-default pre-registered values: none
Git SHA: f9be67aa1dee290bcb161a4abe0cb2e99286848f (dirty: True)
Freeze check: all artifact commits are before the 2026-11-01 freeze

## Sample size (read this first)

Precision targets: about 590 rows for tail-rate precision and about 1575 rows for a 5 A minimum detectable difference.
- Pooled NOMINAL n (max over candidates) = 512. This sums rows from cities that share weather and rows six hours apart that are correlated, so it is NOT an effective sample size and is never judged against the ~590 / ~1575 targets here; the targets are judged on effective n in the pair table below.
- AUSTIN: n scored per candidate: ml_wind_corrected=128, ml_cooling_corrected=128, raw_forecast=128, persistence_24h=128, reference_ml_refit_24h=128. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- CORPUS_CHRISTI: n scored per candidate: ml_wind_corrected=128, ml_cooling_corrected=128, raw_forecast=128, persistence_24h=128, reference_ml_refit_24h=128. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- MIDLAND: n scored per candidate: ml_wind_corrected=128, ml_cooling_corrected=128, raw_forecast=128, persistence_24h=128, reference_ml_refit_24h=128. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- EL_PASO: n scored per candidate: ml_wind_corrected=128, ml_cooling_corrected=128, raw_forecast=128, persistence_24h=128, reference_ml_refit_24h=128. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).

| pair (A vs B) | n paired (pooled) | n_eff (bootstrap) | n_eff (ACF, per city) | MDD (amps) | rows needed for 5 A | ~590 (judged on effective n) | ~1,575 (judged on effective n) |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 512 | 203.6 | AUSTIN:92.3, CORPUS_CHRISTI:108.3, MIDLAND:113.3, EL_PASO:96.3 | 22.13 | 10030 | not met | not met |
| ml_wind_corrected vs reference_ml_refit_24h | 512 | 57.4 | AUSTIN:77.0, CORPUS_CHRISTI:87.0, MIDLAND:59.0, EL_PASO:82.6 | 69.62 | 99254 | not met | not met |
| ml_cooling_corrected vs reference_ml_refit_24h | 512 | 46.7 | AUSTIN:58.8, CORPUS_CHRISTI:96.8, MIDLAND:64.6, EL_PASO:108.7 | 58.63 | 70401 | not met | not met |
| ml_wind_corrected vs raw_forecast | 512 | 218.3 | AUSTIN:97.0, CORPUS_CHRISTI:104.3, MIDLAND:128.0, EL_PASO:110.2 | 21.69 | 9635 | not met | not met |
| ml_cooling_corrected vs raw_forecast | 512 | 152.0 | AUSTIN:120.0, CORPUS_CHRISTI:111.3, MIDLAND:105.2, EL_PASO:106.8 | 22.51 | 10381 | not met | not met |
| reference_ml_refit_24h vs raw_forecast | 512 | 51.4 | AUSTIN:92.7, CORPUS_CHRISTI:85.7, MIDLAND:70.6, EL_PASO:83.4 | 75.34 | 116255 | not met | not met |
| ml_wind_corrected vs persistence_24h | 512 | 66.1 | AUSTIN:73.6, CORPUS_CHRISTI:60.9, MIDLAND:79.4, EL_PASO:102.3 | 77.26 | 122248 | not met | not met |
| ml_cooling_corrected vs persistence_24h | 512 | 70.7 | AUSTIN:128.0, CORPUS_CHRISTI:84.9, MIDLAND:76.6, EL_PASO:128.0 | 64.68 | 85672 | not met | not met |
| reference_ml_refit_24h vs persistence_24h | 512 | 258.1 | AUSTIN:62.8, CORPUS_CHRISTI:92.9, MIDLAND:52.7, EL_PASO:127.8 | 30.68 | 19278 | not met | not met |

## Headline family: 9 tests, pooled, city-clustered, Holm at 0.05

Margin = mean|e_B| - mean|e_A| in amps, so a positive margin means A has the lower MAE. Reanalysis-derived, never sensor-validated.

| A vs B | n | margin (A) | rel. MAE reduction | cities favouring A | headline p | Holm-adj. p | outcome | flags |
|---|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 512 | -8.14 | -0.073 | 1 of 4 | 0.2756 | 0.7643 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs reference_ml_refit_24h | 512 | 28.16 | 0.190 | 4 of 4 | 0.0786 | 0.3144 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs reference_ml_refit_24h | 512 | 36.31 | 0.245 | 4 of 4 | 0.0004 | 0.0028 | favors_A | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs raw_forecast | 512 | 3.97 | 0.032 | 3 of 4 | 0.4996 | 0.7643 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs raw_forecast | 512 | 12.12 | 0.098 | 3 of 4 | 0.0586 | 0.2930 | inconclusive | V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs raw_forecast | 512 | -24.19 | -0.195 | 1 of 4 | 0.2548 | 0.7643 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs persistence_24h | 512 | 54.35 | 0.311 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs persistence_24h | 512 | 62.50 | 0.358 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs persistence_24h | 512 | 26.19 | 0.150 | 4 of 4 | 0.0050 | 0.0300 | favors_A | V4_reanalysis_truth_shared_weather |

Headline intervals (widest 95% and widest Bonferroni (1 - 0.05/9) over both pooled schemes and every runnable block length):

- ml_wind_corrected vs ml_cooling_corrected: 95% [-19.95, 3.81]; Bonferroni [-25.39, 8.49]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs reference_ml_refit_24h: 95% [-1.81, 75.07]; Bonferroni [-8.52, 93.74]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs reference_ml_refit_24h: 95% [13.43, 74.96]; Bonferroni [9.09, 91.88]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs raw_forecast: 95% [-7.67, 18.93]; Bonferroni [-13.14, 23.84]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs raw_forecast: 95% [-0.44, 23.75]; Bonferroni [-6.14, 27.32]; block lengths run [1, 4, 8, 28], skipped []
- reference_ml_refit_24h vs raw_forecast: 95% [-72.67, 8.08]; Bonferroni [-94.22, 14.55]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs persistence_24h: 95% [21.43, 100.92]; Bonferroni [14.49, 122.80]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs persistence_24h: 95% [33.31, 100.22]; Bonferroni [27.55, 121.09]; block lengths run [1, 4, 8, 28], skipped []
- reference_ml_refit_24h vs persistence_24h: 95% [7.07, 41.04]; Bonferroni [0.38, 49.62]; block lengths run [1, 4, 8, 28], skipped []

## Decision (headline decision)

Label: headline decision. Round: v4-read2. Rule: v4. Protocol status: signed.

Bars: 2% of each city's mean truth ampacity over its scored rows (amps):
- Bar AUSTIN: 28.84 A
- Bar CORPUS_CHRISTI: 27.85 A
- Bar MIDLAND: 31.12 A
- Bar EL_PASO: 24.22 A

Each candidate against raw_forecast (pooled benefit against the pooled bar):
- ml_wind_corrected vs raw_forecast: **not shown** (benefit 3.97 A, pooled bar 28.01 A, Holm-adjusted p 0.7643; favoured in 3 of 4 cities, consistent; not vetoed; veto records consulted: ablation+test)
- ml_cooling_corrected vs raw_forecast: **not shown** (benefit 12.12 A, pooled bar 28.01 A, Holm-adjusted p 0.2930; favoured in 3 of 4 cities, consistent; not vetoed; veto records consulted: ablation+test)
- reference_ml_refit_24h vs raw_forecast: **not shown** (benefit -24.19 A, pooled bar 28.01 A, Holm-adjusted p 0.7643; favoured in 1 of 4 cities, not consistent; not vetoed; veto records consulted: ablation+test)

- ml_cooling_corrected vs ml_wind_corrected: pooled margin 8.14 A against a pooled bar of 28.01 A, favoured in 3 of 4 cities, consistently better: False
- reference_ml_refit_24h vs ml_wind_corrected: pooled margin -28.16 A against a pooled bar of 28.01 A, favoured in 0 of 4 cities, consistently better: False

No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07). Read 2 (v4-read2) also names no winner: there is no day-ahead pick and the interim G6 method keeps running; 2026-11-24 stays retired and any later evaluation needs a new signed protocol (owner item O3).

- Sample size: pooled paired rows per headline test range from 512 to 512 (nominal, not effective; effective sample sizes are smaller because six-hourly rows and the four cities share weather); both precision targets (about 590 rows for the tail rate, about 1,575 rows for a 5 A minimum detectable difference) were not met for any headline test.
- No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07).
- Read 2 (v4-read2) also names no winner: there is no day-ahead pick and the interim G6 method keeps running; 2026-11-24 stays retired and any later evaluation needs a new signed protocol (owner item O3).
- Per-city results are descriptive and uncorrected; the headline is the pooled, city-clustered 9-test family with Holm correction at 0.05.
- Calibrated overrating risk (the overrating rate at the nominal 5% target) and retained capacity were not measured. No 8% ceiling was applied. Candidates are ranked on point error only, which is a weaker standard than v1.
- reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated.

## Per-city descriptive metrics (reanalysis-derived, never sensor-validated)

bias = prediction - truth (positive means capacity overstated). Over-prediction rate and overshoot are descriptive; not the calibrated 5%-target rate; not compared with 8%.

### AUSTIN
Rows in scope: 128; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 128 | -61.46 | 129.81 | 172.31 | 99.01 | 0.352 | 97.21 / 276.44 / 410.71 |
| ml_cooling_corrected | 128 | 22.78 | 117.76 | 152.09 | 105.52 | 0.555 | 126.68 / 328.44 / 446.48 |
| raw_forecast | 128 | 13.88 | 132.38 | 175.99 | 105.53 | 0.594 | 123.16 / 353.29 / 441.45 |
| persistence_24h | 128 | 4.66 | 158.91 | 204.22 | 127.93 | 0.516 | 158.61 / 473.62 / 606.78 |
| reference_ml_refit_24h | 128 | 30.41 | 132.95 | 166.30 | 119.21 | 0.602 | 135.78 / 312.02 / 481.05 |

Candidate-level exclusions: 

### CORPUS_CHRISTI
Rows in scope: 128; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 128 | -12.05 | 99.92 | 128.25 | 78.98 | 0.445 | 98.66 / 274.22 / 301.05 |
| ml_cooling_corrected | 128 | 5.83 | 93.54 | 120.17 | 75.38 | 0.531 | 93.53 / 227.12 / 302.65 |
| raw_forecast | 128 | 9.94 | 118.34 | 151.93 | 90.09 | 0.539 | 118.98 / 261.09 / 376.40 |
| persistence_24h | 128 | -1.56 | 134.62 | 169.86 | 95.28 | 0.492 | 135.18 / 311.39 / 475.23 |
| reference_ml_refit_24h | 128 | -18.79 | 113.86 | 142.87 | 103.11 | 0.445 | 106.74 / 227.35 / 399.48 |

Candidate-level exclusions: 

### MIDLAND
Rows in scope: 128; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 128 | -8.81 | 127.21 | 180.67 | 85.51 | 0.430 | 137.77 / 397.59 / 796.90 |
| ml_cooling_corrected | 128 | 13.71 | 131.34 | 174.37 | 94.29 | 0.438 | 165.77 / 400.27 / 775.81 |
| raw_forecast | 128 | -12.96 | 127.97 | 176.60 | 96.37 | 0.438 | 131.44 / 361.35 / 781.71 |
| persistence_24h | 128 | 9.30 | 247.65 | 334.43 | 196.54 | 0.508 | 253.00 / 772.08 / 1032.09 |
| reference_ml_refit_24h | 128 | -25.69 | 217.57 | 267.82 | 181.45 | 0.445 | 215.45 / 586.07 / 683.76 |

Candidate-level exclusions: 

### EL_PASO
Rows in scope: 128; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 128 | -39.07 | 124.20 | 164.17 | 102.61 | 0.461 | 92.34 / 296.91 / 411.80 |
| ml_cooling_corrected | 128 | 4.18 | 105.93 | 136.29 | 88.16 | 0.516 | 106.78 / 286.28 / 458.58 |
| raw_forecast | 128 | 44.39 | 118.36 | 160.26 | 92.99 | 0.609 | 133.54 / 405.27 / 609.18 |
| persistence_24h | 128 | -4.47 | 157.37 | 199.25 | 130.47 | 0.516 | 148.26 / 343.35 / 428.20 |
| reference_ml_refit_24h | 128 | 16.50 | 129.42 | 158.81 | 109.99 | 0.602 | 121.28 / 282.10 / 343.86 |

Candidate-level exclusions: 


## Per-city comparisons (descriptive, uncorrected)

- ml_wind_corrected vs ml_cooling_corrected:
  - AUSTIN: n=128 margin=-12.05 outcome=inconclusive (crosses_zero) L=1: [-30.57, 6.02]; L=4: [-34.62, 7.93]; L=8: [-33.57, 7.55]; L=28: [-27.61, 15.24] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=-6.38 outcome=inconclusive (crosses_zero) L=1: [-16.69, 3.71]; L=4: [-13.91, 5.64]; L=8: [-12.20, 5.69]; L=28: [-7.64, 4.45] - descriptive, uncorrected
  - MIDLAND: n=128 margin=4.13 outcome=inconclusive (crosses_zero) L=1: [-9.96, 17.79]; L=4: [-9.83, 19.39]; L=8: [-7.56, 14.78]; L=28: [-3.83, 9.86] - descriptive, uncorrected
  - EL_PASO: n=128 margin=-18.26 outcome=favors_B L=1: [-35.34, -1.76]; L=4: [-37.13, -0.94]; L=8: [-35.36, -0.20]; L=28: [-29.68, -3.64] - descriptive, uncorrected
- ml_wind_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=128 margin=3.14 outcome=inconclusive (crosses_zero) L=1: [-20.33, 26.51]; L=4: [-25.09, 28.30]; L=8: [-25.42, 30.93]; L=28: [-17.30, 41.62] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=13.93 outcome=inconclusive (crosses_zero) L=1: [-4.39, 32.28]; L=4: [-4.63, 37.09]; L=8: [-1.96, 38.06]; L=28: [-4.27, 38.49] - descriptive, uncorrected
  - MIDLAND: n=128 margin=90.36 outcome=favors_A L=1: [56.10, 125.07]; L=4: [46.50, 131.56]; L=8: [45.06, 132.75]; L=28: [63.84, 126.46] - descriptive, uncorrected
  - EL_PASO: n=128 margin=5.22 outcome=inconclusive (crosses_zero) L=1: [-14.40, 24.60]; L=4: [-16.05, 28.67]; L=8: [-12.80, 28.56]; L=28: [-7.14, 27.50] - descriptive, uncorrected
- ml_cooling_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=128 margin=15.19 outcome=inconclusive (block_length_sensitive) L=1: [2.97, 27.86]; L=4: [0.48, 30.39]; L=8: [-1.24, 32.33]; L=28: [6.01, 32.56] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=20.32 outcome=inconclusive (block_length_sensitive) L=1: [3.85, 36.62]; L=4: [3.51, 37.27]; L=8: [4.49, 37.23]; L=28: [-1.15, 38.10] - descriptive, uncorrected
  - MIDLAND: n=128 margin=86.24 outcome=favors_A L=1: [58.61, 114.12]; L=4: [47.82, 121.13]; L=8: [47.38, 124.74]; L=28: [64.13, 120.14] - descriptive, uncorrected
  - EL_PASO: n=128 margin=23.49 outcome=favors_A L=1: [10.63, 36.55]; L=4: [10.65, 38.19]; L=8: [12.04, 38.71]; L=28: [14.51, 38.33] - descriptive, uncorrected
- ml_wind_corrected vs raw_forecast:
  - AUSTIN: n=128 margin=2.56 outcome=inconclusive (crosses_zero) L=1: [-13.84, 18.66]; L=4: [-15.65, 18.96]; L=8: [-14.85, 20.20]; L=28: [-7.79, 21.13] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=18.41 outcome=favors_A L=1: [6.54, 30.02]; L=4: [8.29, 31.28]; L=8: [8.88, 32.08]; L=28: [15.01, 31.40] - descriptive, uncorrected
  - MIDLAND: n=128 margin=0.76 outcome=inconclusive (crosses_zero) L=1: [-9.20, 10.82]; L=4: [-7.92, 8.91]; L=8: [-8.59, 8.13]; L=28: [-6.89, 8.95] - descriptive, uncorrected
  - EL_PASO: n=128 margin=-5.84 outcome=inconclusive (crosses_zero) L=1: [-26.72, 14.95]; L=4: [-25.45, 15.23]; L=8: [-23.27, 16.66]; L=28: [-15.43, 9.20] - descriptive, uncorrected
- ml_cooling_corrected vs raw_forecast:
  - AUSTIN: n=128 margin=14.62 outcome=inconclusive (block_length_sensitive) L=1: [-0.44, 29.84]; L=4: [0.89, 30.09]; L=8: [2.91, 30.46]; L=28: [-0.05, 29.34] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=24.80 outcome=favors_A L=1: [13.18, 36.25]; L=4: [11.55, 35.67]; L=8: [12.15, 35.35]; L=28: [16.33, 31.67] - descriptive, uncorrected
  - MIDLAND: n=128 margin=-3.37 outcome=inconclusive (crosses_zero) L=1: [-15.40, 8.93]; L=4: [-16.70, 7.56]; L=8: [-14.65, 6.29]; L=28: [-10.74, 6.07] - descriptive, uncorrected
  - EL_PASO: n=128 margin=12.42 outcome=inconclusive (block_length_sensitive) L=1: [-0.71, 25.89]; L=4: [0.15, 27.62]; L=8: [0.57, 27.91]; L=28: [0.94, 23.54] - descriptive, uncorrected
- reference_ml_refit_24h vs raw_forecast:
  - AUSTIN: n=128 margin=-0.58 outcome=inconclusive (crosses_zero) L=1: [-22.19, 21.14]; L=4: [-22.93, 24.59]; L=8: [-23.00, 27.72]; L=28: [-26.07, 19.46] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=4.48 outcome=inconclusive (crosses_zero) L=1: [-18.34, 27.48]; L=4: [-21.88, 28.01]; L=8: [-21.56, 25.13]; L=28: [-14.97, 25.68] - descriptive, uncorrected
  - MIDLAND: n=128 margin=-89.61 outcome=favors_B L=1: [-122.64, -56.57]; L=4: [-131.06, -46.67]; L=8: [-133.19, -46.19]; L=28: [-127.25, -62.43] - descriptive, uncorrected
  - EL_PASO: n=128 margin=-11.06 outcome=inconclusive (crosses_zero) L=1: [-31.22, 9.48]; L=4: [-33.98, 13.31]; L=8: [-33.56, 11.24]; L=28: [-29.75, 2.56] - descriptive, uncorrected
- ml_wind_corrected vs persistence_24h:
  - AUSTIN: n=128 margin=29.10 outcome=inconclusive (block_length_sensitive) L=1: [4.70, 53.58]; L=4: [-0.41, 55.32]; L=8: [-0.91, 54.81]; L=28: [7.20, 47.94] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=34.70 outcome=favors_A L=1: [16.20, 53.45]; L=4: [14.08, 59.12]; L=8: [12.90, 61.84]; L=28: [14.58, 58.38] - descriptive, uncorrected
  - MIDLAND: n=128 margin=120.44 outcome=favors_A L=1: [77.69, 164.40]; L=4: [69.82, 173.52]; L=8: [67.54, 179.10]; L=28: [65.69, 167.32] - descriptive, uncorrected
  - EL_PASO: n=128 margin=33.17 outcome=favors_A L=1: [9.50, 56.99]; L=4: [6.07, 54.21]; L=8: [9.24, 52.93]; L=28: [13.79, 48.82] - descriptive, uncorrected
- ml_cooling_corrected vs persistence_24h:
  - AUSTIN: n=128 margin=41.15 outcome=favors_A L=1: [21.78, 60.97]; L=4: [19.83, 60.98]; L=8: [16.44, 60.59]; L=28: [16.83, 51.54] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=41.08 outcome=favors_A L=1: [24.70, 58.03]; L=4: [20.91, 59.37]; L=8: [20.63, 61.08]; L=28: [20.30, 56.16] - descriptive, uncorrected
  - MIDLAND: n=128 margin=116.31 outcome=favors_A L=1: [77.30, 156.19]; L=4: [69.39, 163.53]; L=8: [67.54, 171.37]; L=28: [66.13, 160.66] - descriptive, uncorrected
  - EL_PASO: n=128 margin=51.43 outcome=favors_A L=1: [33.51, 69.80]; L=4: [33.12, 64.23]; L=8: [34.14, 62.82]; L=28: [34.39, 58.90] - descriptive, uncorrected
- reference_ml_refit_24h vs persistence_24h:
  - AUSTIN: n=128 margin=25.96 outcome=inconclusive (block_length_sensitive) L=1: [5.63, 47.04]; L=4: [3.95, 48.40]; L=8: [-1.21, 49.37]; L=28: [-3.94, 36.27] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=128 margin=20.76 outcome=favors_A L=1: [5.20, 36.24]; L=4: [2.32, 36.25]; L=8: [2.76, 35.08]; L=28: [3.34, 37.49] - descriptive, uncorrected
  - MIDLAND: n=128 margin=30.08 outcome=inconclusive (crosses_zero) L=1: [-4.23, 65.32]; L=4: [-12.18, 75.14]; L=8: [-17.57, 79.32]; L=28: [-14.59, 62.38] - descriptive, uncorrected
  - EL_PASO: n=128 margin=27.95 outcome=favors_A L=1: [9.84, 46.32]; L=4: [7.09, 40.62]; L=8: [7.41, 38.60]; L=28: [2.94, 36.73] - descriptive, uncorrected

## Validity flags and source-specific diagnostics

- V1 (does not apply to this source): The reconstructed frames use the archive anchor at valid - 24 h, which is the development configuration.
- V2 (does not apply to this source): In the reconstructed frames the reference features sit at the anchor (valid - 24 h), so its target is the valid time by construction.
- V3 (does not apply to this source): The port uses the development persistence: archive truth weather 24 h earlier, run through IEEE 738.
- V4 (applies): Truth is reanalysis shared with the training data, and the four cities share weather, so a pooled comparison has far fewer effective samples than rows.
- V5 (does not apply to this source): The reconstructed frames use GFS Previous-Runs forecasts, the training source.
- V6 (does not apply to this source): The reconstructed frames contain no logged rows.

```json
{
 "AUSTIN": {
  "archive_vs_frame_truth": {
   "archive_null_hours_dropped": [],
   "max_abs_diff_truth_amps": 0.0,
   "max_abs_diff_weather": 0.0,
   "n_hours_compared": 128,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/frames/anchored_pair_frame_AUSTIN_2026-09-28_2026-10-31_lead24_previous_runs.csv",
   "city": "AUSTIN",
   "fetch_window": [
    "2026-09-28",
    "2026-10-31"
   ],
   "http_records": [
    {
     "body_file": "01_AUSTIN.body",
     "byte_length": 33401,
     "error": null,
     "meta_file": "01_AUSTIN.meta.json",
     "retrieval_completed_at_utc": "2026-11-08T01:21:07.510444+00:00",
     "retrieval_started_at_utc": "2026-11-08T01:21:06.838012+00:00",
     "sha256": "8d252673780609407d0a0b3ce32da54a00a744741b6bb749f0349533c014a730",
     "status_code": 200,
     "url": "https://archive-api.open-meteo.com/v1/archive"
    },
    {
     "body_file": "02_AUSTIN.body",
     "byte_length": 33606,
     "error": null,
     "meta_file": "02_AUSTIN.meta.json",
     "retrieval_completed_at_utc": "2026-11-08T01:21:08.252473+00:00",
     "retrieval_started_at_utc": "2026-11-08T01:21:07.532320+00:00",
     "sha256": "0602f1edf81a8b50cf440bbd96c1b9a1dfd5022a8351dd51f9ebbcbd2b77eace",
     "status_code": 200,
     "url": "https://previous-runs-api.open-meteo.com/v1/forecast"
    }
   ]
  },
  "leakage_probe": {
   "arms_checked": [
    "raw_forecast",
    "persistence_24h",
    "ml_wind_corrected",
    "ml_cooling_corrected"
   ],
   "oracle_changed": true,
   "oracle_max_abs_change_amps": 1068.7027462618296,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-09-29T00:00:00+00:00",
   "n_expected_slots": 128,
   "n_frame_rows": 792,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 128,
   "window": [
    "2026-09-30T00:00:00+00:00",
    "2026-11-01T00:00:00+00:00"
   ]
  },
  "reference_feature_gaps": {
   "n_rows": 0,
   "valid_times": []
  },
  "reference_target": "the valid time by construction (features at anchor = valid - 24 h)",
  "unavailable_reasons": {}
 },
 "CORPUS_CHRISTI": {
  "archive_vs_frame_truth": {
   "archive_null_hours_dropped": [],
   "max_abs_diff_truth_amps": 0.0,
   "max_abs_diff_weather": 0.0,
   "n_hours_compared": 128,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/frames/anchored_pair_frame_CORPUS_CHRISTI_2026-09-28_2026-10-31_lead24_previous_runs.csv",
   "city": "CORPUS_CHRISTI",
   "fetch_window": [
    "2026-09-28",
    "2026-10-31"
   ],
   "http_records": [
    {
     "body_file": "03_CORPUS_CHRISTI.body",
     "byte_length": 33360,
     "error": null,
     "meta_file": "03_CORPUS_CHRISTI.meta.json",
     "retrieval_completed_at_utc": "2026-11-08T01:21:09.396338+00:00",
     "retrieval_started_at_utc": "2026-11-08T01:21:08.767861+00:00",
     "sha256": "07dd947644cc58187bbd5925f4167db141a2f4bbced9c19de60bdb7885609798",
     "status_code": 200,
     "url": "https://archive-api.open-meteo.com/v1/archive"
    },
    {
     "body_file": "04_CORPUS_CHRISTI.body",
     "byte_length": 33490,
     "error": null,
     "meta_file": "04_CORPUS_CHRISTI.meta.json",
     "retrieval_completed_at_utc": "2026-11-08T01:21:10.229747+00:00",
     "retrieval_started_at_utc": "2026-11-08T01:21:09.407928+00:00",
     "sha256": "903342cb7a1570f193784a40654cbe3d886bffe01a18f2fadb9e26534003e1bf",
     "status_code": 200,
     "url": "https://previous-runs-api.open-meteo.com/v1/forecast"
    }
   ]
  },
  "leakage_probe": {
   "arms_checked": [
    "raw_forecast",
    "persistence_24h",
    "ml_wind_corrected",
    "ml_cooling_corrected"
   ],
   "oracle_changed": true,
   "oracle_max_abs_change_amps": 856.829104354779,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-09-29T00:00:00+00:00",
   "n_expected_slots": 128,
   "n_frame_rows": 792,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 128,
   "window": [
    "2026-09-30T00:00:00+00:00",
    "2026-11-01T00:00:00+00:00"
   ]
  },
  "reference_feature_gaps": {
   "n_rows": 0,
   "valid_times": []
  },
  "reference_target": "the valid time by construction (features at anchor = valid - 24 h)",
  "unavailable_reasons": {}
 },
 "EL_PASO": {
  "archive_vs_frame_truth": {
   "archive_null_hours_dropped": [],
   "max_abs_diff_truth_amps": 0.0,
   "max_abs_diff_weather": 0.0,
   "n_hours_compared": 128,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/frames/anchored_pair_frame_EL_PASO_2026-09-28_2026-10-31_lead24_previous_runs.csv",
   "city": "EL_PASO",
   "fetch_window": [
    "2026-09-28",
    "2026-10-31"
   ],
   "http_records": [
    {
     "body_file": "07_EL_PASO.body",
     "byte_length": 33563,
     "error": null,
     "meta_file": "07_EL_PASO.meta.json",
     "retrieval_completed_at_utc": "2026-11-08T01:21:12.408829+00:00",
     "retrieval_started_at_utc": "2026-11-08T01:21:11.792921+00:00",
     "sha256": "1e4d703a15046bbe837482227e188919bff807a5c7e7475c819a2f3a6ff00315",
     "status_code": 200,
     "url": "https://archive-api.open-meteo.com/v1/archive"
    },
    {
     "body_file": "08_EL_PASO.body",
     "byte_length": 33590,
     "error": null,
     "meta_file": "08_EL_PASO.meta.json",
     "retrieval_completed_at_utc": "2026-11-08T01:21:13.164759+00:00",
     "retrieval_started_at_utc": "2026-11-08T01:21:12.423291+00:00",
     "sha256": "5adcf669f71a3f89bf20aa3eadb52f5e3365bea0be45e9416abe37aa43167eeb",
     "status_code": 200,
     "url": "https://previous-runs-api.open-meteo.com/v1/forecast"
    }
   ]
  },
  "leakage_probe": {
   "arms_checked": [
    "raw_forecast",
    "persistence_24h",
    "ml_wind_corrected",
    "ml_cooling_corrected"
   ],
   "oracle_changed": true,
   "oracle_max_abs_change_amps": 962.293374924399,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-09-29T00:00:00+00:00",
   "n_expected_slots": 128,
   "n_frame_rows": 792,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 128,
   "window": [
    "2026-09-30T00:00:00+00:00",
    "2026-11-01T00:00:00+00:00"
   ]
  },
  "reference_feature_gaps": {
   "n_rows": 0,
   "valid_times": []
  },
  "reference_target": "the valid time by construction (features at anchor = valid - 24 h)",
  "unavailable_reasons": {}
 },
 "MIDLAND": {
  "archive_vs_frame_truth": {
   "archive_null_hours_dropped": [],
   "max_abs_diff_truth_amps": 0.0,
   "max_abs_diff_weather": 0.0,
   "n_hours_compared": 128,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/frames/anchored_pair_frame_MIDLAND_2026-09-28_2026-10-31_lead24_previous_runs.csv",
   "city": "MIDLAND",
   "fetch_window": [
    "2026-09-28",
    "2026-10-31"
   ],
   "http_records": [
    {
     "body_file": "05_MIDLAND.body",
     "byte_length": 33601,
     "error": null,
     "meta_file": "05_MIDLAND.meta.json",
     "retrieval_completed_at_utc": "2026-11-08T01:21:10.943801+00:00",
     "retrieval_started_at_utc": "2026-11-08T01:21:10.318871+00:00",
     "sha256": "c3024cb461b6f0be5e70d7cbfc118e1430a5104c3784ff4727865a930c60dad5",
     "status_code": 200,
     "url": "https://archive-api.open-meteo.com/v1/archive"
    },
    {
     "body_file": "06_MIDLAND.body",
     "byte_length": 33708,
     "error": null,
     "meta_file": "06_MIDLAND.meta.json",
     "retrieval_completed_at_utc": "2026-11-08T01:21:11.703687+00:00",
     "retrieval_started_at_utc": "2026-11-08T01:21:10.957363+00:00",
     "sha256": "9e8bb90b44023d294d28d3e09bbedd65b2c9c45b336d41cb12dbb5ad4c433e05",
     "status_code": 200,
     "url": "https://previous-runs-api.open-meteo.com/v1/forecast"
    }
   ]
  },
  "leakage_probe": {
   "arms_checked": [
    "raw_forecast",
    "persistence_24h",
    "ml_wind_corrected",
    "ml_cooling_corrected"
   ],
   "oracle_changed": true,
   "oracle_max_abs_change_amps": 956.3085608155095,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-09-29T00:00:00+00:00",
   "n_expected_slots": 128,
   "n_frame_rows": 792,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 128,
   "window": [
    "2026-09-30T00:00:00+00:00",
    "2026-11-01T00:00:00+00:00"
   ]
  },
  "reference_feature_gaps": {
   "n_rows": 0,
   "valid_times": []
  },
  "reference_target": "the valid time by construction (features at anchor = valid - 24 h)",
  "unavailable_reasons": {}
 }
}
```

## Scope and exclusions

Scored unit: one (city, valid_time) pair; single-conductor ampacity_amps only (bundle not scored, PD-14). Corridor-era rows are never counted. Nothing is imputed, retried or backfilled.

```json
{
 "AUSTIN": {
  "accounting": {
   "expected_slots_equals_scored_plus_missing": true,
   "per_candidate_scored_plus_exclusions_equals_rows": {
    "ml_cooling_corrected": true,
    "ml_wind_corrected": true,
    "persistence_24h": true,
    "raw_forecast": true,
    "reference_ml_refit_24h": true
   }
  },
  "candidate_level": {
   "ml_cooling_corrected": {},
   "ml_wind_corrected": {},
   "persistence_24h": {},
   "raw_forecast": {},
   "reference_ml_refit_24h": {}
  },
  "row_level": {
   "missing_from_reconstruction": 0
  },
  "rows_dropped_null_weather": 0
 },
 "CORPUS_CHRISTI": {
  "accounting": {
   "expected_slots_equals_scored_plus_missing": true,
   "per_candidate_scored_plus_exclusions_equals_rows": {
    "ml_cooling_corrected": true,
    "ml_wind_corrected": true,
    "persistence_24h": true,
    "raw_forecast": true,
    "reference_ml_refit_24h": true
   }
  },
  "candidate_level": {
   "ml_cooling_corrected": {},
   "ml_wind_corrected": {},
   "persistence_24h": {},
   "raw_forecast": {},
   "reference_ml_refit_24h": {}
  },
  "row_level": {
   "missing_from_reconstruction": 0
  },
  "rows_dropped_null_weather": 0
 },
 "EL_PASO": {
  "accounting": {
   "expected_slots_equals_scored_plus_missing": true,
   "per_candidate_scored_plus_exclusions_equals_rows": {
    "ml_cooling_corrected": true,
    "ml_wind_corrected": true,
    "persistence_24h": true,
    "raw_forecast": true,
    "reference_ml_refit_24h": true
   }
  },
  "candidate_level": {
   "ml_cooling_corrected": {},
   "ml_wind_corrected": {},
   "persistence_24h": {},
   "raw_forecast": {},
   "reference_ml_refit_24h": {}
  },
  "row_level": {
   "missing_from_reconstruction": 0
  },
  "rows_dropped_null_weather": 0
 },
 "MIDLAND": {
  "accounting": {
   "expected_slots_equals_scored_plus_missing": true,
   "per_candidate_scored_plus_exclusions_equals_rows": {
    "ml_cooling_corrected": true,
    "ml_wind_corrected": true,
    "persistence_24h": true,
    "raw_forecast": true,
    "reference_ml_refit_24h": true
   }
  },
  "candidate_level": {
   "ml_cooling_corrected": {},
   "ml_wind_corrected": {},
   "persistence_24h": {},
   "raw_forecast": {},
   "reference_ml_refit_24h": {}
  },
  "row_level": {
   "missing_from_reconstruction": 0
  },
  "rows_dropped_null_weather": 0
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

- 01_AUSTIN.body: sha256 8d252673780609407d0a0b3ce32da54a00a744741b6bb749f0349533c014a730, 33401 bytes, status 200, retrieved 2026-11-08T01:21:06.838012+00:00 .. 2026-11-08T01:21:07.510444+00:00
- 02_AUSTIN.body: sha256 0602f1edf81a8b50cf440bbd96c1b9a1dfd5022a8351dd51f9ebbcbd2b77eace, 33606 bytes, status 200, retrieved 2026-11-08T01:21:07.532320+00:00 .. 2026-11-08T01:21:08.252473+00:00
- 03_CORPUS_CHRISTI.body: sha256 07dd947644cc58187bbd5925f4167db141a2f4bbced9c19de60bdb7885609798, 33360 bytes, status 200, retrieved 2026-11-08T01:21:08.767861+00:00 .. 2026-11-08T01:21:09.396338+00:00
- 04_CORPUS_CHRISTI.body: sha256 903342cb7a1570f193784a40654cbe3d886bffe01a18f2fadb9e26534003e1bf, 33490 bytes, status 200, retrieved 2026-11-08T01:21:09.407928+00:00 .. 2026-11-08T01:21:10.229747+00:00
- 05_MIDLAND.body: sha256 c3024cb461b6f0be5e70d7cbfc118e1430a5104c3784ff4727865a930c60dad5, 33601 bytes, status 200, retrieved 2026-11-08T01:21:10.318871+00:00 .. 2026-11-08T01:21:10.943801+00:00
- 06_MIDLAND.body: sha256 9e8bb90b44023d294d28d3e09bbedd65b2c9c45b336d41cb12dbb5ad4c433e05, 33708 bytes, status 200, retrieved 2026-11-08T01:21:10.957363+00:00 .. 2026-11-08T01:21:11.703687+00:00
- 07_EL_PASO.body: sha256 1e4d703a15046bbe837482227e188919bff807a5c7e7475c819a2f3a6ff00315, 33563 bytes, status 200, retrieved 2026-11-08T01:21:11.792921+00:00 .. 2026-11-08T01:21:12.408829+00:00
- 08_EL_PASO.body: sha256 5adcf669f71a3f89bf20aa3eadb52f5e3365bea0be45e9416abe37aa43167eeb, 33590 bytes, status 200, retrieved 2026-11-08T01:21:12.423291+00:00 .. 2026-11-08T01:21:13.164759+00:00
