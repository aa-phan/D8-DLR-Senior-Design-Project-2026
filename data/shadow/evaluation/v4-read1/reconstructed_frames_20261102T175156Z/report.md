# Per-city shadow evaluation - row source: reconstructed frames (headline source)

Truth: reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated
Basis: FRESH
Protocol status: signed
Round: v4-read1
Evaluation instant: 2026-11-01T00:00:00+00:00
Valid-time cutoff (strict, valid_time < cutoff): 2026-10-25T00:00:00+00:00
Now evaluated: 2026-11-02T17:51:56.189045+00:00
Override: none
Non-default pre-registered values: none
Git SHA: e092d129978e0744e7565fdbb258a4b1f7ce8eef (dirty: True)
Freeze check: all artifact commits are before the 2026-11-01 freeze

## Sample size (read this first)

Precision targets: about 590 rows for tail-rate precision and about 1575 rows for a 5 A minimum detectable difference.
- Pooled NOMINAL n (max over candidates) = 400. This sums rows from cities that share weather and rows six hours apart that are correlated, so it is NOT an effective sample size and is never judged against the ~590 / ~1575 targets here; the targets are judged on effective n in the pair table below.
- AUSTIN: n scored per candidate: ml_wind_corrected=100, ml_cooling_corrected=100, raw_forecast=100, persistence_24h=100, reference_ml_refit_24h=100. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- CORPUS_CHRISTI: n scored per candidate: ml_wind_corrected=100, ml_cooling_corrected=100, raw_forecast=100, persistence_24h=100, reference_ml_refit_24h=100. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- MIDLAND: n scored per candidate: ml_wind_corrected=100, ml_cooling_corrected=100, raw_forecast=100, persistence_24h=100, reference_ml_refit_24h=100. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- EL_PASO: n scored per candidate: ml_wind_corrected=100, ml_cooling_corrected=100, raw_forecast=100, persistence_24h=100, reference_ml_refit_24h=100. Nominal count is below ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).

| pair (A vs B) | n paired (pooled) | n_eff (bootstrap) | n_eff (ACF, per city) | MDD (amps) | rows needed for 5 A | ~590 (judged on effective n) | ~1,575 (judged on effective n) |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 400 | 126.4 | AUSTIN:78.0, CORPUS_CHRISTI:95.9, MIDLAND:90.6, EL_PASO:77.3 | 26.77 | 11468 | not met | not met |
| ml_wind_corrected vs reference_ml_refit_24h | 400 | 35.4 | AUSTIN:48.0, CORPUS_CHRISTI:67.6, MIDLAND:67.6, EL_PASO:59.6 | 86.72 | 120323 | not met | not met |
| ml_cooling_corrected vs reference_ml_refit_24h | 400 | 29.5 | AUSTIN:44.7, CORPUS_CHRISTI:81.6, MIDLAND:56.9, EL_PASO:84.9 | 72.78 | 84762 | not met | not met |
| ml_wind_corrected vs raw_forecast | 400 | 133.2 | AUSTIN:98.5, CORPUS_CHRISTI:76.3, MIDLAND:100.0, EL_PASO:81.5 | 26.72 | 11426 | not met | not met |
| ml_cooling_corrected vs raw_forecast | 400 | 118.4 | AUSTIN:93.6, CORPUS_CHRISTI:74.1, MIDLAND:78.7, EL_PASO:75.3 | 24.38 | 9512 | not met | not met |
| reference_ml_refit_24h vs raw_forecast | 400 | 32.7 | AUSTIN:75.7, CORPUS_CHRISTI:68.4, MIDLAND:61.0, EL_PASO:57.6 | 93.56 | 140044 | not met | not met |
| ml_wind_corrected vs persistence_24h | 400 | 39.2 | AUSTIN:57.6, CORPUS_CHRISTI:48.7, MIDLAND:64.9, EL_PASO:81.1 | 104.06 | 173270 | not met | not met |
| ml_cooling_corrected vs persistence_24h | 400 | 39.8 | AUSTIN:100.0, CORPUS_CHRISTI:66.2, MIDLAND:61.7, EL_PASO:100.0 | 90.49 | 131004 | not met | not met |
| reference_ml_refit_24h vs persistence_24h | 400 | 184.2 | AUSTIN:95.6, CORPUS_CHRISTI:60.0, MIDLAND:53.4, EL_PASO:100.0 | 36.02 | 20759 | not met | not met |

## Headline family: 9 tests, pooled, city-clustered, Holm at 0.05

Margin = mean|e_B| - mean|e_A| in amps, so a positive margin means A has the lower MAE. Reanalysis-derived, never sensor-validated.

| A vs B | n | margin (A) | rel. MAE reduction | cities favouring A | headline p | Holm-adj. p | outcome | flags |
|---|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 400 | -5.54 | -0.052 | 1 of 4 | 0.4990 | 0.9569 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs reference_ml_refit_24h | 400 | 35.95 | 0.244 | 4 of 4 | 0.0500 | 0.2500 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs reference_ml_refit_24h | 400 | 41.48 | 0.281 | 4 of 4 | 0.0006 | 0.0042 | favors_A | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs raw_forecast | 400 | 6.35 | 0.054 | 3 of 4 | 0.3922 | 0.9569 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs raw_forecast | 400 | 11.89 | 0.101 | 3 of 4 | 0.0906 | 0.3624 | inconclusive | V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs raw_forecast | 400 | -29.59 | -0.251 | 1 of 4 | 0.3190 | 0.9569 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs persistence_24h | 400 | 58.23 | 0.343 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs persistence_24h | 400 | 63.77 | 0.375 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs persistence_24h | 400 | 22.28 | 0.131 | 4 of 4 | 0.0062 | 0.0372 | favors_A | V4_reanalysis_truth_shared_weather |

Headline intervals (widest 95% and widest Bonferroni (1 - 0.05/9) over both pooled schemes and every runnable block length):

- ml_wind_corrected vs ml_cooling_corrected: 95% [-21.04, 8.14]; Bonferroni [-28.32, 12.24]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs reference_ml_refit_24h: 95% [0.04, 90.08]; Bonferroni [-5.83, 113.99]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs reference_ml_refit_24h: 95% [10.85, 86.77]; Bonferroni [5.16, 105.95]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs raw_forecast: 95% [-8.53, 20.64]; Bonferroni [-15.13, 25.50]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs raw_forecast: 95% [-1.84, 25.38]; Bonferroni [-7.52, 29.25]; block lengths run [1, 4, 8, 28], skipped []
- reference_ml_refit_24h vs raw_forecast: 95% [-87.63, 11.98]; Bonferroni [-112.16, 20.75]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs persistence_24h: 95% [17.18, 122.59]; Bonferroni [9.98, 152.04]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs persistence_24h: 95% [27.94, 119.67]; Bonferroni [22.07, 145.93]; block lengths run [1, 4, 8, 28], skipped []
- reference_ml_refit_24h vs persistence_24h: 95% [6.56, 47.20]; Bonferroni [-0.03, 59.32]; block lengths run [1, 4, 8, 28], skipped []

## Decision (headline decision)

Label: headline decision. Round: v4-read1. Rule: v4. Protocol status: signed.

Bars: 2% of each city's mean truth ampacity over its scored rows (amps):
- Bar AUSTIN: 28.48 A
- Bar CORPUS_CHRISTI: 27.40 A
- Bar MIDLAND: 30.87 A
- Bar EL_PASO: 24.69 A

Each candidate against raw_forecast (pooled benefit against the pooled bar):
- ml_wind_corrected vs raw_forecast: **not shown** (benefit 6.35 A, pooled bar 27.86 A, Holm-adjusted p 0.9569; favoured in 3 of 4 cities, consistent; not vetoed; veto records consulted: ablation+test)
- ml_cooling_corrected vs raw_forecast: **not shown** (benefit 11.89 A, pooled bar 27.86 A, Holm-adjusted p 0.3624; favoured in 3 of 4 cities, consistent; not vetoed; veto records consulted: ablation+test)
- reference_ml_refit_24h vs raw_forecast: **not shown** (benefit -29.59 A, pooled bar 27.86 A, Holm-adjusted p 0.9569; favoured in 1 of 4 cities, not consistent; not vetoed; veto records consulted: ablation+test)

- ml_cooling_corrected vs ml_wind_corrected: pooled margin 5.54 A against a pooled bar of 27.86 A, favoured in 3 of 4 cities, consistently better: False
- reference_ml_refit_24h vs ml_wind_corrected: pooled margin -35.95 A against a pooled bar of 27.86 A, favoured in 0 of 4 cities, consistently better: False

No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07). Read 1 names no winner, so the pre-registered re-test v4-read2 runs at or after 2026-11-08T00:00:00Z under the same rules.

- Sample size: pooled paired rows per headline test range from 400 to 400 (nominal, not effective; effective sample sizes are smaller because six-hourly rows and the four cities share weather); both precision targets (about 590 rows for the tail rate, about 1,575 rows for a 5 A minimum detectable difference) were not met for any headline test.
- No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07).
- Read 1 names no winner, so the pre-registered re-test v4-read2 runs at or after 2026-11-08T00:00:00Z under the same rules.
- Per-city results are descriptive and uncorrected; the headline is the pooled, city-clustered 9-test family with Holm correction at 0.05.
- Calibrated overrating risk (the overrating rate at the nominal 5% target) and retained capacity were not measured. No 8% ceiling was applied. Candidates are ranked on point error only, which is a weaker standard than v1.
- reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated.

## Per-city descriptive metrics (reanalysis-derived, never sensor-validated)

bias = prediction - truth (positive means capacity overstated). Over-prediction rate and overshoot are descriptive; not the calibrated 5%-target rate; not compared with 8%.

### AUSTIN
Rows in scope: 100; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 100 | -37.97 | 113.17 | 150.82 | 81.21 | 0.390 | 96.41 / 291.95 / 410.71 |
| ml_cooling_corrected | 100 | 33.04 | 110.56 | 145.12 | 89.31 | 0.590 | 121.70 / 319.21 / 446.48 |
| raw_forecast | 100 | 32.13 | 125.14 | 165.14 | 103.76 | 0.640 | 122.87 / 344.44 / 441.45 |
| persistence_24h | 100 | 4.36 | 143.23 | 189.41 | 101.06 | 0.540 | 136.65 / 406.52 / 514.24 |
| reference_ml_refit_24h | 100 | 47.37 | 125.63 | 156.52 | 114.75 | 0.640 | 135.16 / 303.04 / 416.01 |

Candidate-level exclusions: 

### CORPUS_CHRISTI
Rows in scope: 100; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 100 | -13.64 | 92.63 | 119.81 | 72.54 | 0.420 | 94.04 / 272.17 / 297.49 |
| ml_cooling_corrected | 100 | 6.21 | 89.81 | 115.05 | 73.24 | 0.530 | 90.58 / 226.15 / 294.15 |
| raw_forecast | 100 | 4.94 | 115.03 | 148.78 | 78.61 | 0.510 | 117.61 / 258.85 / 339.60 |
| persistence_24h | 100 | -4.16 | 120.85 | 152.55 | 91.87 | 0.480 | 121.55 / 296.43 / 335.75 |
| reference_ml_refit_24h | 100 | -7.38 | 102.87 | 129.71 | 89.79 | 0.470 | 101.59 / 214.60 / 244.89 |

Candidate-level exclusions: 

### MIDLAND
Rows in scope: 100; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 100 | -22.18 | 118.79 | 172.48 | 80.65 | 0.380 | 127.11 / 390.87 / 796.90 |
| ml_cooling_corrected | 100 | 5.58 | 126.33 | 169.74 | 89.13 | 0.420 | 157.04 / 328.20 / 775.81 |
| raw_forecast | 100 | -21.15 | 120.13 | 168.95 | 89.48 | 0.410 | 120.72 / 299.49 / 781.71 |
| persistence_24h | 100 | -9.93 | 270.02 | 359.75 | 205.03 | 0.490 | 265.39 / 838.77 / 1032.09 |
| reference_ml_refit_24h | 100 | -21.75 | 234.22 | 285.45 | 195.10 | 0.440 | 241.45 / 595.50 / 683.76 |

Candidate-level exclusions: 

### EL_PASO
Rows in scope: 100; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 100 | -51.04 | 121.77 | 161.26 | 101.98 | 0.440 | 80.38 / 180.49 / 333.74 |
| ml_cooling_corrected | 100 | -11.47 | 97.51 | 125.63 | 79.51 | 0.490 | 87.80 / 245.79 / 318.06 |
| raw_forecast | 100 | 34.31 | 111.47 | 146.97 | 87.34 | 0.610 | 119.49 / 333.95 / 487.77 |
| persistence_24h | 100 | -13.95 | 145.18 | 186.67 | 126.59 | 0.520 | 126.18 / 309.71 / 321.58 |
| reference_ml_refit_24h | 100 | -3.28 | 127.42 | 156.80 | 107.72 | 0.570 | 108.89 / 256.77 / 299.16 |

Candidate-level exclusions: 


## Per-city comparisons (descriptive, uncorrected)

- ml_wind_corrected vs ml_cooling_corrected:
  - AUSTIN: n=100 margin=-2.61 outcome=inconclusive (crosses_zero) L=1: [-19.81, 13.81]; L=4: [-19.78, 18.35]; L=8: [-21.07, 19.99]; L=28: [-22.38, 19.67] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=-2.82 outcome=inconclusive (crosses_zero) L=1: [-13.41, 8.28]; L=4: [-13.61, 7.67]; L=8: [-12.94, 7.52]; L=28: [-9.21, 5.92] - descriptive, uncorrected
  - MIDLAND: n=100 margin=7.55 outcome=inconclusive (crosses_zero) L=1: [-9.13, 23.77]; L=4: [-10.27, 23.99]; L=8: [-7.27, 18.15]; L=28: [-5.12, 11.90] - descriptive, uncorrected
  - EL_PASO: n=100 margin=-24.27 outcome=favors_B L=1: [-43.57, -5.27]; L=4: [-45.78, -4.25]; L=8: [-44.35, -3.10]; L=28: [-34.39, -3.79] - descriptive, uncorrected
- ml_wind_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=100 margin=12.46 outcome=inconclusive (crosses_zero) L=1: [-11.04, 35.27]; L=4: [-14.14, 41.29]; L=8: [-15.78, 45.66]; L=28: [-14.57, 50.66] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=10.24 outcome=inconclusive (crosses_zero) L=1: [-9.34, 30.11]; L=4: [-12.34, 32.18]; L=8: [-10.93, 33.04]; L=28: [-13.63, 32.22] - descriptive, uncorrected
  - MIDLAND: n=100 margin=115.44 outcome=favors_A L=1: [77.88, 153.26]; L=4: [68.92, 155.07]; L=8: [64.94, 148.84]; L=28: [76.42, 137.52] - descriptive, uncorrected
  - EL_PASO: n=100 margin=5.64 outcome=inconclusive (crosses_zero) L=1: [-15.45, 27.51]; L=4: [-19.46, 31.45]; L=8: [-18.58, 31.14]; L=28: [-10.24, 33.40] - descriptive, uncorrected
- ml_cooling_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=100 margin=15.07 outcome=inconclusive (block_length_sensitive) L=1: [1.36, 29.05]; L=4: [-0.98, 32.34]; L=8: [-2.09, 35.97]; L=28: [4.82, 37.94] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=13.06 outcome=inconclusive (crosses_zero) L=1: [-3.64, 30.04]; L=4: [-5.85, 30.18]; L=8: [-4.64, 30.38]; L=28: [-8.41, 29.16] - descriptive, uncorrected
  - MIDLAND: n=100 margin=107.89 outcome=favors_A L=1: [78.61, 138.50]; L=4: [69.61, 142.57]; L=8: [65.55, 139.41]; L=28: [76.95, 130.60] - descriptive, uncorrected
  - EL_PASO: n=100 margin=29.91 outcome=favors_A L=1: [15.42, 44.46]; L=4: [14.81, 45.13]; L=8: [15.34, 44.40]; L=28: [18.43, 42.73] - descriptive, uncorrected
- ml_wind_corrected vs raw_forecast:
  - AUSTIN: n=100 margin=11.97 outcome=inconclusive (block_length_sensitive) L=1: [-4.65, 28.15]; L=4: [0.13, 27.59]; L=8: [1.47, 28.04]; L=28: [7.89, 24.43] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=22.39 outcome=favors_A L=1: [10.95, 34.51]; L=4: [9.83, 35.56]; L=8: [9.48, 35.80]; L=28: [13.11, 31.11] - descriptive, uncorrected
  - MIDLAND: n=100 margin=1.35 outcome=inconclusive (crosses_zero) L=1: [-9.38, 12.27]; L=4: [-8.21, 11.20]; L=8: [-8.87, 11.02]; L=28: [-8.87, 6.53] - descriptive, uncorrected
  - EL_PASO: n=100 margin=-10.31 outcome=inconclusive (crosses_zero) L=1: [-34.43, 13.02]; L=4: [-33.98, 15.87]; L=8: [-29.78, 18.13]; L=28: [-15.00, 13.25] - descriptive, uncorrected
- ml_cooling_corrected vs raw_forecast:
  - AUSTIN: n=100 margin=14.58 outcome=inconclusive (block_length_sensitive) L=1: [-0.60, 29.94]; L=4: [0.41, 29.44]; L=8: [1.03, 29.38]; L=28: [2.77, 33.35] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=25.22 outcome=favors_A L=1: [12.97, 37.36]; L=4: [12.02, 38.72]; L=8: [11.61, 38.90]; L=28: [14.00, 29.66] - descriptive, uncorrected
  - MIDLAND: n=100 margin=-6.20 outcome=inconclusive (crosses_zero) L=1: [-19.84, 7.54]; L=4: [-20.45, 8.76]; L=8: [-17.16, 8.46]; L=28: [-13.69, 4.17] - descriptive, uncorrected
  - EL_PASO: n=100 margin=13.96 outcome=inconclusive (block_length_sensitive) L=1: [-0.99, 29.34]; L=4: [0.00, 31.83]; L=8: [2.44, 33.26]; L=28: [5.25, 27.84] - descriptive, uncorrected
- reference_ml_refit_24h vs raw_forecast:
  - AUSTIN: n=100 margin=-0.49 outcome=inconclusive (crosses_zero) L=1: [-22.57, 22.00]; L=4: [-23.43, 23.98]; L=8: [-26.05, 25.16]; L=28: [-29.91, 25.93] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=12.16 outcome=inconclusive (crosses_zero) L=1: [-11.69, 36.12]; L=4: [-14.89, 39.63]; L=8: [-15.61, 36.75]; L=28: [-8.82, 32.76] - descriptive, uncorrected
  - MIDLAND: n=100 margin=-114.09 outcome=favors_B L=1: [-151.70, -77.26]; L=4: [-154.74, -66.95]; L=8: [-149.66, -62.12]; L=28: [-139.67, -76.31] - descriptive, uncorrected
  - EL_PASO: n=100 margin=-15.95 outcome=inconclusive (crosses_zero) L=1: [-38.70, 7.05]; L=4: [-39.76, 11.92]; L=8: [-37.80, 13.63]; L=28: [-34.36, 6.83] - descriptive, uncorrected
- ml_wind_corrected vs persistence_24h:
  - AUSTIN: n=100 margin=30.06 outcome=favors_A L=1: [4.57, 55.49]; L=4: [3.48, 62.37]; L=8: [3.03, 64.91]; L=28: [8.84, 54.77] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=28.22 outcome=favors_A L=1: [6.87, 50.33]; L=4: [2.99, 55.71]; L=8: [1.52, 58.79]; L=28: [6.04, 61.62] - descriptive, uncorrected
  - MIDLAND: n=100 margin=151.23 outcome=favors_A L=1: [98.62, 204.08]; L=4: [93.34, 212.38]; L=8: [90.84, 215.62]; L=28: [91.90, 187.83] - descriptive, uncorrected
  - EL_PASO: n=100 margin=23.40 outcome=inconclusive (block_length_sensitive) L=1: [-2.70, 49.91]; L=4: [-4.35, 46.74]; L=8: [-1.85, 46.08]; L=28: [9.37, 48.87] - descriptive, uncorrected
- ml_cooling_corrected vs persistence_24h:
  - AUSTIN: n=100 margin=32.66 outcome=favors_A L=1: [10.10, 55.34]; L=4: [10.45, 57.35]; L=8: [9.76, 60.08]; L=28: [18.76, 54.02] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=31.04 outcome=favors_A L=1: [13.10, 49.23]; L=4: [10.86, 53.17]; L=8: [10.83, 54.14]; L=28: [14.19, 56.54] - descriptive, uncorrected
  - MIDLAND: n=100 margin=143.68 outcome=favors_A L=1: [96.91, 191.80]; L=4: [90.79, 200.08]; L=8: [89.95, 205.94]; L=28: [93.65, 180.99] - descriptive, uncorrected
  - EL_PASO: n=100 margin=47.67 outcome=favors_A L=1: [27.03, 68.51]; L=4: [28.71, 62.78]; L=8: [28.72, 62.81]; L=28: [32.10, 62.09] - descriptive, uncorrected
- reference_ml_refit_24h vs persistence_24h:
  - AUSTIN: n=100 margin=17.59 outcome=inconclusive (crosses_zero) L=1: [-5.25, 41.52]; L=4: [-5.94, 43.99]; L=8: [-9.11, 47.88]; L=28: [-5.96, 38.74] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=100 margin=17.99 outcome=inconclusive (block_length_sensitive) L=1: [1.89, 34.31]; L=4: [-0.30, 38.19]; L=8: [-0.01, 36.42]; L=28: [9.70, 43.25] - descriptive, uncorrected
  - MIDLAND: n=100 margin=35.79 outcome=inconclusive (crosses_zero) L=1: [-4.19, 75.66]; L=4: [-8.31, 90.54]; L=8: [-6.95, 99.21]; L=28: [-6.09, 79.47] - descriptive, uncorrected
  - EL_PASO: n=100 margin=17.76 outcome=inconclusive (crosses_zero) L=1: [-1.52, 37.30]; L=4: [-2.02, 33.70]; L=8: [-1.27, 30.95]; L=28: [-2.16, 32.33] - descriptive, uncorrected

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
   "n_hours_compared": 100,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/frames/anchored_pair_frame_AUSTIN_2026-09-28_2026-10-24_lead24_previous_runs.csv",
   "city": "AUSTIN",
   "fetch_window": [
    "2026-09-28",
    "2026-10-24"
   ],
   "http_records": [
    {
     "body_file": "01_AUSTIN.body",
     "byte_length": 26624,
     "error": null,
     "meta_file": "01_AUSTIN.meta.json",
     "retrieval_completed_at_utc": "2026-11-02T17:51:57.239951+00:00",
     "retrieval_started_at_utc": "2026-11-02T17:51:56.646586+00:00",
     "sha256": "11362ad0bb2e55911832412f0edcd837a735d65b4205acc20afd47ca86ef9a0a",
     "status_code": 200,
     "url": "https://archive-api.open-meteo.com/v1/archive"
    },
    {
     "body_file": "02_AUSTIN.body",
     "byte_length": 26840,
     "error": null,
     "meta_file": "02_AUSTIN.meta.json",
     "retrieval_completed_at_utc": "2026-11-02T17:51:57.897552+00:00",
     "retrieval_started_at_utc": "2026-11-02T17:51:57.265290+00:00",
     "sha256": "ce732444db1c08a2a9f08bd592d742461f5d59d36dfb0b9f06cea80819f55b98",
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
   "n_expected_slots": 100,
   "n_frame_rows": 624,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 100,
   "window": [
    "2026-09-30T00:00:00+00:00",
    "2026-10-25T00:00:00+00:00"
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
   "n_hours_compared": 100,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/frames/anchored_pair_frame_CORPUS_CHRISTI_2026-09-28_2026-10-24_lead24_previous_runs.csv",
   "city": "CORPUS_CHRISTI",
   "fetch_window": [
    "2026-09-28",
    "2026-10-24"
   ],
   "http_records": [
    {
     "body_file": "03_CORPUS_CHRISTI.body",
     "byte_length": 26594,
     "error": null,
     "meta_file": "03_CORPUS_CHRISTI.meta.json",
     "retrieval_completed_at_utc": "2026-11-02T17:51:58.757286+00:00",
     "retrieval_started_at_utc": "2026-11-02T17:51:58.184199+00:00",
     "sha256": "b4502a78b9ba904704c5abbc9bafffa9b9d6cabbdd7439c2a8b2109f38553070",
     "status_code": 200,
     "url": "https://archive-api.open-meteo.com/v1/archive"
    },
    {
     "body_file": "04_CORPUS_CHRISTI.body",
     "byte_length": 26722,
     "error": null,
     "meta_file": "04_CORPUS_CHRISTI.meta.json",
     "retrieval_completed_at_utc": "2026-11-02T17:51:59.362559+00:00",
     "retrieval_started_at_utc": "2026-11-02T17:51:58.773238+00:00",
     "sha256": "27fb7eb6d5a0adcd71d5bb7016bcd3c30cfafbd37a76215d97b33e48dbdded10",
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
   "n_expected_slots": 100,
   "n_frame_rows": 624,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 100,
   "window": [
    "2026-09-30T00:00:00+00:00",
    "2026-10-25T00:00:00+00:00"
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
   "n_hours_compared": 100,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/frames/anchored_pair_frame_EL_PASO_2026-09-28_2026-10-24_lead24_previous_runs.csv",
   "city": "EL_PASO",
   "fetch_window": [
    "2026-09-28",
    "2026-10-24"
   ],
   "http_records": [
    {
     "body_file": "07_EL_PASO.body",
     "byte_length": 26751,
     "error": null,
     "meta_file": "07_EL_PASO.meta.json",
     "retrieval_completed_at_utc": "2026-11-02T17:52:01.317722+00:00",
     "retrieval_started_at_utc": "2026-11-02T17:52:00.746961+00:00",
     "sha256": "bdeac049fa9e1bf2a2dc9f85e0cc9f841c198d5186e7fceeda3b086fcf3c5404",
     "status_code": 200,
     "url": "https://archive-api.open-meteo.com/v1/archive"
    },
    {
     "body_file": "08_EL_PASO.body",
     "byte_length": 26802,
     "error": null,
     "meta_file": "08_EL_PASO.meta.json",
     "retrieval_completed_at_utc": "2026-11-02T17:52:02.078431+00:00",
     "retrieval_started_at_utc": "2026-11-02T17:52:01.327598+00:00",
     "sha256": "ae2cd1f9fe62e39e1e8299bcb9a64f28ca0705db3521a1c21d388c9373878eaa",
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
   "oracle_max_abs_change_amps": 922.2107276504403,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-09-29T00:00:00+00:00",
   "n_expected_slots": 100,
   "n_frame_rows": 624,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 100,
   "window": [
    "2026-09-30T00:00:00+00:00",
    "2026-10-25T00:00:00+00:00"
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
   "n_hours_compared": 100,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/frames/anchored_pair_frame_MIDLAND_2026-09-28_2026-10-24_lead24_previous_runs.csv",
   "city": "MIDLAND",
   "fetch_window": [
    "2026-09-28",
    "2026-10-24"
   ],
   "http_records": [
    {
     "body_file": "05_MIDLAND.body",
     "byte_length": 26773,
     "error": null,
     "meta_file": "05_MIDLAND.meta.json",
     "retrieval_completed_at_utc": "2026-11-02T17:52:00.028792+00:00",
     "retrieval_started_at_utc": "2026-11-02T17:51:59.445444+00:00",
     "sha256": "5c2d6bb36049308bbefe2a65058cbd02dd3550d2804ffe87a9b352b7100eca79",
     "status_code": 200,
     "url": "https://archive-api.open-meteo.com/v1/archive"
    },
    {
     "body_file": "06_MIDLAND.body",
     "byte_length": 26874,
     "error": null,
     "meta_file": "06_MIDLAND.meta.json",
     "retrieval_completed_at_utc": "2026-11-02T17:52:00.669830+00:00",
     "retrieval_started_at_utc": "2026-11-02T17:52:00.041266+00:00",
     "sha256": "bd31e3a6324d46c66b2247f744409bd07d17d3c3c347d98106ccca628f4fbd37",
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
   "n_expected_slots": 100,
   "n_frame_rows": 624,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 100,
   "window": [
    "2026-09-30T00:00:00+00:00",
    "2026-10-25T00:00:00+00:00"
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

- 01_AUSTIN.body: sha256 11362ad0bb2e55911832412f0edcd837a735d65b4205acc20afd47ca86ef9a0a, 26624 bytes, status 200, retrieved 2026-11-02T17:51:56.646586+00:00 .. 2026-11-02T17:51:57.239951+00:00
- 02_AUSTIN.body: sha256 ce732444db1c08a2a9f08bd592d742461f5d59d36dfb0b9f06cea80819f55b98, 26840 bytes, status 200, retrieved 2026-11-02T17:51:57.265290+00:00 .. 2026-11-02T17:51:57.897552+00:00
- 03_CORPUS_CHRISTI.body: sha256 b4502a78b9ba904704c5abbc9bafffa9b9d6cabbdd7439c2a8b2109f38553070, 26594 bytes, status 200, retrieved 2026-11-02T17:51:58.184199+00:00 .. 2026-11-02T17:51:58.757286+00:00
- 04_CORPUS_CHRISTI.body: sha256 27fb7eb6d5a0adcd71d5bb7016bcd3c30cfafbd37a76215d97b33e48dbdded10, 26722 bytes, status 200, retrieved 2026-11-02T17:51:58.773238+00:00 .. 2026-11-02T17:51:59.362559+00:00
- 05_MIDLAND.body: sha256 5c2d6bb36049308bbefe2a65058cbd02dd3550d2804ffe87a9b352b7100eca79, 26773 bytes, status 200, retrieved 2026-11-02T17:51:59.445444+00:00 .. 2026-11-02T17:52:00.028792+00:00
- 06_MIDLAND.body: sha256 bd31e3a6324d46c66b2247f744409bd07d17d3c3c347d98106ccca628f4fbd37, 26874 bytes, status 200, retrieved 2026-11-02T17:52:00.041266+00:00 .. 2026-11-02T17:52:00.669830+00:00
- 07_EL_PASO.body: sha256 bdeac049fa9e1bf2a2dc9f85e0cc9f841c198d5186e7fceeda3b086fcf3c5404, 26751 bytes, status 200, retrieved 2026-11-02T17:52:00.746961+00:00 .. 2026-11-02T17:52:01.317722+00:00
- 08_EL_PASO.body: sha256 ae2cd1f9fe62e39e1e8299bcb9a64f28ca0705db3521a1c21d388c9373878eaa, 26802 bytes, status 200, retrieved 2026-11-02T17:52:01.327598+00:00 .. 2026-11-02T17:52:02.078431+00:00
