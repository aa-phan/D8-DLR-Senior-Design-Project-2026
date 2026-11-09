# Per-city shadow evaluation - row source: reconstructed frames (headline source)

Truth: reanalysis-derived (Open-Meteo Archive reanalysis through IEEE 738), never sensor-validated
Basis: development

**DEVELOPMENT DATA - not a confirmation result**

Protocol status: signed
Round: v4-read1
Evaluation instant: 2026-11-01T00:00:00+00:00
Valid-time cutoff (strict, valid_time < cutoff): 2026-10-25T00:00:00+00:00
Now evaluated: 2026-11-02T08:51:08.295243+00:00
Override: none
Non-default pre-registered values: none
Git SHA: 6e12778ec38f19821ff7eace23cd62ebae59dbf8 (dirty: True)
Freeze check: all artifact commits are before the 2026-11-01 freeze

## Sample size (read this first)

Precision targets: about 590 rows for tail-rate precision and about 1575 rows for a 5 A minimum detectable difference.
- Pooled NOMINAL n (max over candidates) = 3136. This sums rows from cities that share weather and rows six hours apart that are correlated, so it is NOT an effective sample size and is never judged against the ~590 / ~1575 targets here; the targets are judged on effective n in the pair table below.
- AUSTIN: n scored per candidate: ml_wind_corrected=784, ml_cooling_corrected=784, raw_forecast=784, persistence_24h=784, reference_ml_refit_24h=784. Nominal count is at or above ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- CORPUS_CHRISTI: n scored per candidate: ml_wind_corrected=784, ml_cooling_corrected=784, raw_forecast=784, persistence_24h=784, reference_ml_refit_24h=784. Nominal count is at or above ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- MIDLAND: n scored per candidate: ml_wind_corrected=784, ml_cooling_corrected=784, raw_forecast=784, persistence_24h=784, reference_ml_refit_24h=784. Nominal count is at or above ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).
- EL_PASO: n scored per candidate: ml_wind_corrected=784, ml_cooling_corrected=784, raw_forecast=784, persistence_24h=784, reference_ml_refit_24h=784. Nominal count is at or above ~590 and below ~1575 (nominal only: six-hourly rows are autocorrelated, so the effective n is lower).

| pair (A vs B) | n paired (pooled) | n_eff (bootstrap) | n_eff (ACF, per city) | MDD (amps) | rows needed for 5 A | ~590 (judged on effective n) | ~1,575 (judged on effective n) |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 3136 | 484.7 | AUSTIN:784.0, CORPUS_CHRISTI:784.0, MIDLAND:656.8, EL_PASO:784.0 | 12.67 | 20151 | not met | not met |
| ml_wind_corrected vs reference_ml_refit_24h | 3136 | 105.9 | AUSTIN:784.0, CORPUS_CHRISTI:739.9, MIDLAND:393.4, EL_PASO:703.7 | 44.01 | 242913 | not met | not met |
| ml_cooling_corrected vs reference_ml_refit_24h | 3136 | 89.4 | AUSTIN:784.0, CORPUS_CHRISTI:613.5, MIDLAND:537.2, EL_PASO:753.8 | 37.24 | 173922 | not met | not met |
| ml_wind_corrected vs raw_forecast | 3136 | 185.8 | AUSTIN:765.8, CORPUS_CHRISTI:784.0, MIDLAND:734.9, EL_PASO:575.7 | 24.80 | 77123 | not met | not met |
| ml_cooling_corrected vs raw_forecast | 3136 | 188.1 | AUSTIN:724.6, CORPUS_CHRISTI:784.0, MIDLAND:773.6, EL_PASO:610.3 | 21.80 | 59630 | not met | not met |
| reference_ml_refit_24h vs raw_forecast | 3136 | 84.9 | AUSTIN:737.0, CORPUS_CHRISTI:784.0, MIDLAND:370.1, EL_PASO:605.7 | 55.25 | 382883 | not met | not met |
| ml_wind_corrected vs persistence_24h | 3136 | 121.2 | AUSTIN:758.2, CORPUS_CHRISTI:565.3, MIDLAND:330.6, EL_PASO:714.7 | 49.28 | 304620 | not met | not met |
| ml_cooling_corrected vs persistence_24h | 3136 | 117.2 | AUSTIN:729.3, CORPUS_CHRISTI:506.3, MIDLAND:309.3, EL_PASO:707.5 | 42.63 | 227967 | not met | not met |
| reference_ml_refit_24h vs persistence_24h | 3136 | 1007.2 | AUSTIN:663.3, CORPUS_CHRISTI:477.0, MIDLAND:518.0, EL_PASO:724.4 | 13.53 | 22959 | met | not met |

## Headline family: 9 tests, pooled, city-clustered, Holm at 0.05

Margin = mean|e_B| - mean|e_A| in amps, so a positive margin means A has the lower MAE. Reanalysis-derived, never sensor-validated.

| A vs B | n | margin (A) | rel. MAE reduction | cities favouring A | headline p | Holm-adj. p | outcome | flags |
|---|---|---|---|---|---|---|---|---|
| ml_wind_corrected vs ml_cooling_corrected | 3136 | -6.94 | -0.066 | 0 of 4 | 0.0070 | 0.0210 | favors_B | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs reference_ml_refit_24h | 3136 | 17.90 | 0.137 | 3 of 4 | 0.0900 | 0.1800 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs reference_ml_refit_24h | 3136 | 24.84 | 0.190 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs raw_forecast | 3136 | 17.96 | 0.137 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs raw_forecast | 3136 | 24.90 | 0.190 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs raw_forecast | 3136 | 0.06 | 0.000 | 3 of 4 | 0.9985 | 0.9985 | inconclusive | V4_reanalysis_truth_shared_weather |
| ml_wind_corrected vs persistence_24h | 3136 | 41.57 | 0.269 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| ml_cooling_corrected vs persistence_24h | 3136 | 48.51 | 0.314 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |
| reference_ml_refit_24h vs persistence_24h | 3136 | 23.67 | 0.153 | 4 of 4 | 0.0002 | 0.0018 | favors_A | V4_reanalysis_truth_shared_weather |

Headline intervals (widest 95% and widest Bonferroni (1 - 0.05/9) over both pooled schemes and every runnable block length):

- ml_wind_corrected vs ml_cooling_corrected: 95% [-14.57, -1.15]; Bonferroni [-18.29, 0.11]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs reference_ml_refit_24h: 95% [-2.11, 44.60]; Bonferroni [-8.10, 55.63]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs reference_ml_refit_24h: 95% [10.66, 48.40]; Bonferroni [8.62, 58.06]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs raw_forecast: 95% [5.34, 32.27]; Bonferroni [3.39, 37.88]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs raw_forecast: 95% [12.98, 37.08]; Bonferroni [9.18, 41.76]; block lengths run [1, 4, 8, 28], skipped []
- reference_ml_refit_24h vs raw_forecast: 95% [-34.64, 23.17]; Bonferroni [-48.75, 27.57]; block lengths run [1, 4, 8, 28], skipped []
- ml_wind_corrected vs persistence_24h: 95% [18.23, 70.99]; Bonferroni [11.60, 82.76]; block lengths run [1, 4, 8, 28], skipped []
- ml_cooling_corrected vs persistence_24h: 95% [30.14, 74.35]; Bonferroni [27.02, 84.65]; block lengths run [1, 4, 8, 28], skipped []
- reference_ml_refit_24h vs persistence_24h: 95% [16.43, 31.12]; Bonferroni [14.09, 34.23]; block lengths run [1, 4, 8, 28], skipped []

## Decision (headline decision)

(not computed)

## Per-city descriptive metrics (reanalysis-derived, never sensor-validated)

bias = prediction - truth (positive means capacity overstated). Over-prediction rate and overshoot are descriptive; not the calibrated 5%-target rate; not compared with 8%.

### AUSTIN
Rows in scope: 784; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 784 | -50.64 | 109.24 | 151.89 | 70.93 | 0.403 | 72.70 / 235.83 / 394.63 |
| ml_cooling_corrected | 784 | 1.17 | 91.29 | 125.90 | 59.72 | 0.494 | 93.66 / 266.94 / 462.27 |
| raw_forecast | 784 | 1.24 | 114.46 | 157.24 | 80.77 | 0.529 | 109.29 / 325.98 / 666.99 |
| persistence_24h | 784 | 0.46 | 121.41 | 167.62 | 89.78 | 0.486 | 125.39 / 398.06 / 923.33 |
| reference_ml_refit_24h | 784 | 18.21 | 101.73 | 135.12 | 77.54 | 0.577 | 104.02 / 274.53 / 396.33 |

Candidate-level exclusions: 

### CORPUS_CHRISTI
Rows in scope: 784; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 784 | -0.33 | 88.06 | 128.84 | 59.13 | 0.497 | 88.19 / 281.74 / 606.74 |
| ml_cooling_corrected | 784 | 0.46 | 85.78 | 122.35 | 60.72 | 0.497 | 86.69 / 297.53 / 601.67 |
| raw_forecast | 784 | -16.09 | 110.76 | 152.63 | 80.18 | 0.395 | 119.71 / 384.31 / 687.01 |
| persistence_24h | 784 | 1.44 | 118.38 | 165.86 | 84.25 | 0.474 | 126.26 / 368.27 / 680.99 |
| reference_ml_refit_24h | 784 | 17.88 | 101.34 | 137.36 | 73.16 | 0.550 | 108.43 / 313.99 / 572.76 |

Candidate-level exclusions: 

### MIDLAND
Rows in scope: 784; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 784 | -10.62 | 122.96 | 179.66 | 81.46 | 0.455 | 123.35 / 429.05 / 801.23 |
| ml_cooling_corrected | 784 | -7.80 | 119.92 | 167.73 | 85.16 | 0.420 | 133.60 / 403.10 / 790.72 |
| raw_forecast | 784 | -26.66 | 129.09 | 183.61 | 83.00 | 0.411 | 124.70 / 419.41 / 797.27 |
| persistence_24h | 784 | 1.14 | 205.65 | 272.79 | 151.64 | 0.495 | 208.92 / 556.77 / 1062.68 |
| reference_ml_refit_24h | 784 | -25.58 | 178.20 | 222.70 | 151.90 | 0.408 | 186.96 / 489.16 / 802.29 |

Candidate-level exclusions: 

### EL_PASO
Rows in scope: 784; excluded by reason: none

| candidate | n | bias | MAE | RMSE | median AE | over-pred. rate | overshoot mean / p95 / max |
|---|---|---|---|---|---|---|---|
| ml_wind_corrected | 784 | -29.31 | 130.84 | 170.89 | 102.84 | 0.438 | 116.04 / 296.10 / 435.51 |
| ml_cooling_corrected | 784 | 25.25 | 126.33 | 163.78 | 97.47 | 0.559 | 135.67 / 336.53 / 528.25 |
| raw_forecast | 784 | 70.23 | 168.63 | 222.77 | 124.41 | 0.667 | 179.03 / 466.98 / 820.94 |
| persistence_24h | 784 | 0.56 | 171.93 | 218.54 | 139.99 | 0.496 | 173.82 / 468.37 / 792.50 |
| reference_ml_refit_24h | 784 | 50.18 | 141.42 | 177.30 | 117.17 | 0.611 | 156.80 / 374.45 / 542.87 |

Candidate-level exclusions: 


## Per-city comparisons (descriptive, uncorrected)

- ml_wind_corrected vs ml_cooling_corrected:
  - AUSTIN: n=784 margin=-17.95 outcome=favors_B L=1: [-23.72, -12.18]; L=4: [-23.50, -12.21]; L=8: [-23.62, -11.76]; L=28: [-23.59, -11.00] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=-2.28 outcome=inconclusive (crosses_zero) L=1: [-6.23, 1.73]; L=4: [-6.46, 1.79]; L=8: [-6.39, 1.71]; L=28: [-6.21, 1.19] - descriptive, uncorrected
  - MIDLAND: n=784 margin=-3.03 outcome=inconclusive (crosses_zero) L=1: [-7.42, 1.34]; L=4: [-7.95, 1.40]; L=8: [-7.73, 1.19]; L=28: [-6.85, 1.50] - descriptive, uncorrected
  - EL_PASO: n=784 margin=-4.51 outcome=inconclusive (crosses_zero) L=1: [-11.33, 2.24]; L=4: [-11.25, 2.48]; L=8: [-10.96, 2.58]; L=28: [-10.84, 2.74] - descriptive, uncorrected
- ml_wind_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=784 margin=-7.51 outcome=inconclusive (block_length_sensitive) L=1: [-15.10, -0.22]; L=4: [-14.73, -0.07]; L=8: [-14.91, 0.32]; L=28: [-14.94, 0.10] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=13.28 outcome=favors_A L=1: [6.53, 19.95]; L=4: [6.27, 20.07]; L=8: [6.47, 20.29]; L=28: [6.02, 19.75] - descriptive, uncorrected
  - MIDLAND: n=784 margin=55.25 outcome=favors_A L=1: [43.98, 66.36]; L=4: [43.36, 67.58]; L=8: [42.52, 68.11]; L=28: [42.47, 72.77] - descriptive, uncorrected
  - EL_PASO: n=784 margin=10.58 outcome=favors_A L=1: [2.21, 18.83]; L=4: [2.55, 19.44]; L=8: [2.72, 19.44]; L=28: [2.89, 19.35] - descriptive, uncorrected
- ml_cooling_corrected vs reference_ml_refit_24h:
  - AUSTIN: n=784 margin=10.44 outcome=favors_A L=1: [5.54, 15.14]; L=4: [5.53, 15.36]; L=8: [5.09, 15.60]; L=28: [4.30, 15.04] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=15.56 outcome=favors_A L=1: [9.85, 21.09]; L=4: [9.63, 21.50]; L=8: [9.53, 21.81]; L=28: [9.35, 21.25] - descriptive, uncorrected
  - MIDLAND: n=784 margin=58.28 outcome=favors_A L=1: [48.49, 67.83]; L=4: [47.92, 69.15]; L=8: [47.02, 69.81]; L=28: [46.83, 73.31] - descriptive, uncorrected
  - EL_PASO: n=784 margin=15.09 outcome=favors_A L=1: [9.89, 20.48]; L=4: [9.90, 20.75]; L=8: [9.68, 20.54]; L=28: [10.02, 20.18] - descriptive, uncorrected
- ml_wind_corrected vs raw_forecast:
  - AUSTIN: n=784 margin=5.21 outcome=inconclusive (crosses_zero) L=1: [-0.95, 11.39]; L=4: [-0.57, 11.38]; L=8: [-0.61, 11.86]; L=28: [-0.47, 13.67] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=22.70 outcome=favors_A L=1: [18.19, 27.06]; L=4: [18.66, 27.13]; L=8: [18.61, 27.29]; L=28: [19.09, 26.84] - descriptive, uncorrected
  - MIDLAND: n=784 margin=6.14 outcome=favors_A L=1: [2.58, 9.59]; L=4: [2.47, 9.67]; L=8: [2.25, 9.81]; L=28: [2.37, 9.89] - descriptive, uncorrected
  - EL_PASO: n=784 margin=37.79 outcome=favors_A L=1: [27.90, 48.00]; L=4: [27.68, 47.99]; L=8: [27.00, 48.39]; L=28: [26.06, 49.47] - descriptive, uncorrected
- ml_cooling_corrected vs raw_forecast:
  - AUSTIN: n=784 margin=23.17 outcome=favors_A L=1: [18.08, 28.37]; L=4: [18.19, 28.42]; L=8: [18.26, 28.54]; L=28: [18.08, 29.46] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=24.98 outcome=favors_A L=1: [20.01, 29.94]; L=4: [20.65, 29.80]; L=8: [20.40, 30.03]; L=28: [21.17, 29.92] - descriptive, uncorrected
  - MIDLAND: n=784 margin=9.17 outcome=favors_A L=1: [5.04, 13.23]; L=4: [5.19, 13.43]; L=8: [4.90, 13.42]; L=28: [4.53, 12.77] - descriptive, uncorrected
  - EL_PASO: n=784 margin=42.30 outcome=favors_A L=1: [34.33, 50.29]; L=4: [33.69, 50.59]; L=8: [33.07, 50.74]; L=28: [32.82, 50.72] - descriptive, uncorrected
- reference_ml_refit_24h vs raw_forecast:
  - AUSTIN: n=784 margin=12.73 outcome=favors_A L=1: [5.02, 20.70]; L=4: [4.80, 20.97]; L=8: [4.67, 21.42]; L=28: [4.97, 23.24] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=9.42 outcome=favors_A L=1: [1.40, 17.37]; L=4: [1.93, 17.53]; L=8: [1.66, 17.56]; L=28: [2.69, 17.71] - descriptive, uncorrected
  - MIDLAND: n=784 margin=-49.11 outcome=favors_B L=1: [-60.57, -37.77]; L=4: [-61.67, -36.86]; L=8: [-62.66, -35.87]; L=28: [-67.48, -35.42] - descriptive, uncorrected
  - EL_PASO: n=784 margin=27.21 outcome=favors_A L=1: [16.88, 37.51]; L=4: [15.72, 37.88]; L=8: [14.87, 38.28]; L=28: [15.11, 38.18] - descriptive, uncorrected
- ml_wind_corrected vs persistence_24h:
  - AUSTIN: n=784 margin=12.17 outcome=favors_A L=1: [3.74, 20.90]; L=4: [3.95, 20.80]; L=8: [3.85, 21.17]; L=28: [3.88, 22.12] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=30.32 outcome=favors_A L=1: [22.26, 38.33]; L=4: [21.27, 38.90]; L=8: [20.98, 38.96]; L=28: [20.70, 38.68] - descriptive, uncorrected
  - MIDLAND: n=784 margin=82.69 outcome=favors_A L=1: [69.27, 96.34]; L=4: [67.72, 98.43]; L=8: [65.76, 99.04]; L=28: [64.67, 104.28] - descriptive, uncorrected
  - EL_PASO: n=784 margin=41.09 outcome=favors_A L=1: [31.05, 51.40]; L=4: [31.25, 51.84]; L=8: [31.32, 52.75]; L=28: [32.00, 53.87] - descriptive, uncorrected
- ml_cooling_corrected vs persistence_24h:
  - AUSTIN: n=784 margin=30.12 outcome=favors_A L=1: [23.67, 37.18]; L=4: [23.42, 37.07]; L=8: [23.30, 37.10]; L=28: [22.48, 38.16] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=32.60 outcome=favors_A L=1: [25.54, 39.53]; L=4: [24.50, 40.43]; L=8: [24.03, 40.46]; L=28: [22.83, 41.78] - descriptive, uncorrected
  - MIDLAND: n=784 margin=85.73 outcome=favors_A L=1: [73.59, 97.99]; L=4: [71.78, 100.09]; L=8: [70.06, 101.06]; L=28: [68.71, 105.29] - descriptive, uncorrected
  - EL_PASO: n=784 margin=45.60 outcome=favors_A L=1: [37.53, 53.82]; L=4: [37.57, 54.18]; L=8: [37.66, 54.65]; L=28: [38.72, 54.59] - descriptive, uncorrected
- reference_ml_refit_24h vs persistence_24h:
  - AUSTIN: n=784 margin=19.68 outcome=favors_A L=1: [13.30, 26.53]; L=4: [13.04, 26.44]; L=8: [13.14, 26.09]; L=28: [13.64, 27.16] - descriptive, uncorrected
  - CORPUS_CHRISTI: n=784 margin=17.04 outcome=favors_A L=1: [10.28, 23.92]; L=4: [9.07, 24.71]; L=8: [8.43, 24.95]; L=28: [7.94, 26.64] - descriptive, uncorrected
  - MIDLAND: n=784 margin=27.45 outcome=favors_A L=1: [16.68, 38.40]; L=4: [15.21, 39.81]; L=8: [14.13, 39.69]; L=28: [14.26, 39.51] - descriptive, uncorrected
  - EL_PASO: n=784 margin=30.51 outcome=favors_A L=1: [22.13, 39.27]; L=4: [22.07, 38.97]; L=8: [22.70, 38.96]; L=28: [24.26, 38.23] - descriptive, uncorrected

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
   "n_hours_compared": 784,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/experiment/anchored_pair_frame_AUSTIN_2024-01-20_2026-09-29_lead24_previous_runs.csv",
   "cache_sha256": "dbe2ad2207b933730e45bc960922b8fef4199d73af923e8ed9a2623be0c228c5",
   "city": "AUSTIN",
   "fetch_window": [
    "2024-01-20",
    "2026-09-29"
   ],
   "provider": "cached_test_provider"
  },
  "leakage_probe": {
   "arms_checked": [
    "raw_forecast",
    "persistence_24h",
    "ml_wind_corrected",
    "ml_cooling_corrected"
   ],
   "oracle_changed": true,
   "oracle_max_abs_change_amps": 936.3715933274034,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-03-17T00:00:00+00:00",
   "n_expected_slots": 784,
   "n_frame_rows": 23592,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 784,
   "window": [
    "2026-03-18T00:00:00+00:00",
    "2026-09-30T00:00:00+00:00"
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
   "n_hours_compared": 784,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/experiment/anchored_pair_frame_CORPUS_CHRISTI_2024-01-20_2026-09-29_lead24_previous_runs.csv",
   "cache_sha256": "585bf24623747bf9c21051b4b2e9674c2e5888707f23b267efa6caaddbb78043",
   "city": "CORPUS_CHRISTI",
   "fetch_window": [
    "2024-01-20",
    "2026-09-29"
   ],
   "provider": "cached_test_provider"
  },
  "leakage_probe": {
   "arms_checked": [
    "raw_forecast",
    "persistence_24h",
    "ml_wind_corrected",
    "ml_cooling_corrected"
   ],
   "oracle_changed": true,
   "oracle_max_abs_change_amps": 933.5597144325751,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-03-17T00:00:00+00:00",
   "n_expected_slots": 784,
   "n_frame_rows": 23592,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 784,
   "window": [
    "2026-03-18T00:00:00+00:00",
    "2026-09-30T00:00:00+00:00"
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
   "n_hours_compared": 784,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/experiment/anchored_pair_frame_EL_PASO_2024-01-20_2026-09-29_lead24_previous_runs.csv",
   "cache_sha256": "32ea0bab4dee2d462926b40b831c42d7f44e13adb3e3c8b990fae8f838dc82e4",
   "city": "EL_PASO",
   "fetch_window": [
    "2024-01-20",
    "2026-09-29"
   ],
   "provider": "cached_test_provider"
  },
  "leakage_probe": {
   "arms_checked": [
    "raw_forecast",
    "persistence_24h",
    "ml_wind_corrected",
    "ml_cooling_corrected"
   ],
   "oracle_changed": true,
   "oracle_max_abs_change_amps": 1003.1854075113325,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-03-17T00:00:00+00:00",
   "n_expected_slots": 784,
   "n_frame_rows": 23592,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 784,
   "window": [
    "2026-03-18T00:00:00+00:00",
    "2026-09-30T00:00:00+00:00"
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
   "n_hours_compared": 784,
   "tolerance": 0.0
  },
  "candidate_failed_rows": {
   "ml_cooling_corrected": 0,
   "ml_wind_corrected": 0,
   "persistence_24h": 0,
   "raw_forecast": 0
  },
  "frame_fetch": {
   "cache_path": "data/experiment/anchored_pair_frame_MIDLAND_2024-01-20_2026-09-29_lead24_previous_runs.csv",
   "cache_sha256": "a29edcf31480749b72c1a873157f0c349b34ea10bdf0071610e8fbca7c9b0cef",
   "city": "MIDLAND",
   "fetch_window": [
    "2024-01-20",
    "2026-09-29"
   ],
   "provider": "cached_test_provider"
  },
  "leakage_probe": {
   "arms_checked": [
    "raw_forecast",
    "persistence_24h",
    "ml_wind_corrected",
    "ml_cooling_corrected"
   ],
   "oracle_changed": true,
   "oracle_max_abs_change_amps": 927.6876014986183,
   "passed": true,
   "sabotage": "truth_air_temp +10, truth_wind_speed +5, truth_wind_direction +90 mod 360, truth_solar_radiation +100, every *_dlr_amps column NaN",
   "status": "passed"
  },
  "missing_slots": [],
  "preparation": {
   "anchor_after_fit_end": true,
   "artifact_fit_window_end": "2026-03-16",
   "min_anchor_datetime_utc": "2026-03-17T00:00:00+00:00",
   "n_expected_slots": 784,
   "n_frame_rows": 23592,
   "n_missing_from_reconstruction": 0,
   "n_rows_dropped_null_weather": 0,
   "n_scored_slots": 784,
   "window": [
    "2026-03-18T00:00:00+00:00",
    "2026-09-30T00:00:00+00:00"
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

(no HTTP evidence recorded)
