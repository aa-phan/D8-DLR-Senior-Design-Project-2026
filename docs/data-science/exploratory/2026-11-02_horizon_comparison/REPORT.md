# Day-ahead shadow methods vs the live 60-minute `ml`: horizon comparison on TEST

**Exploratory, not pre-registered; does not change signed protocol v4 or read 1.** Run 2026-11-02 on the non-FRESH TEST split only: valid times from 2026-03-18T00Z up to, not including, 2026-09-30T00Z, 784 six-hourly slots per city. No file of read 1 was opened. `PLAN.md` was written before any result was computed and was not changed. One post-hoc descriptive addition is labelled as such (`context_posthoc.md`).

## In plain English

**Setup.** Every number compares a forecast against the same "truth": Open-Meteo reanalysis weather at the valid time, turned into an ampacity with IEEE 738 under each city's production conductor (AUSTIN is Drake at 100 °C). This truth comes from a weather model, not from line sensors. Error is mean absolute error (MAE) in amps. A paired test scores both forecasts on the same city and hour and tests the average difference of their errors. Confidence intervals come from a block bootstrap, which resamples runs of consecutive slots so that weather lasting several days is not counted as independent evidence. Holm corrects for running several tests at once. With 10,000 resamples, p cannot go below 0.0002.

**(A) At the same 24-hour lead, do the weather-correction methods beat the live-ml design re-aimed 24 h ahead (`reference_ml_refit_24h`)?**

- **`ml_cooling_corrected`: yes, clearly.** It beats the reference by 26.3 A pooled (95% CI 13.1 to 49.0 A, Holm p 0.001) and wins in every city (AUSTIN +16.2, CORPUS_CHRISTI +15.6, MIDLAND +58.3, EL_PASO +15.1 A; all four city intervals exclude zero). It also beats `raw_forecast` (+25.8 A pooled) and `persistence_24h` (+49.3 A pooled) in all four cities. The direction matches read 1; this is a different, already-seen window, so it adds support but confirms nothing.
- **`ml_wind_corrected`: only weakly.** It beats the reference by 18.9 A pooled, only just significant (Holm p 0.041; conservative city-clustered interval 0.5 to 44.8 A). The result rests mostly on MIDLAND (+55.2 A); in AUSTIN the reference is slightly better (−3.5 A, not significant); under the frozen-Drake sensitivity it is not significant (p 0.09). It beats `raw_forecast` (+18.5 A) and `persistence_24h` (+41.9 A) pooled, but only marginally beats raw in AUSTIN (+7.2 A, p 0.09 after Holm within the city).
- The reference is no better than the plain forecast pooled (135.9 vs 135.5 A) and much worse in MIDLAND (178.2 vs 129.1 A), as in 07-11.

**(B) How much accuracy is lost by forecasting 24 hours ahead instead of 60 minutes?** As expected, the 60-minute ml forecast wins everywhere; the question is the size of the gap.

| city | live ml at 60 min | best 24 h (`ml_cooling_corrected`) | extra error at 24 h | as % of mean rating | 24 h MAE ÷ 60 min MAE | `raw_forecast` at 24 h |
|---|---|---|---|---|---|---|
| AUSTIN | 85.0 A | 106.5 A | +21.5 A [15.3, 27.6] | 1.5% | 1.25 | 133.3 A (+48.3, ×1.57) |
| CORPUS_CHRISTI | 67.7 A | 85.8 A | +18.1 A [12.1, 24.0] | 1.4% | 1.27 | 110.8 A (+43.1, ×1.64) |
| MIDLAND | 91.5 A | 119.9 A | +28.4 A [18.8, 36.4] | 1.9% | 1.31 | 129.1 A (+37.6, ×1.41) |
| EL_PASO | 102.0 A | 126.3 A | +24.4 A [16.8, 31.6] | 2.1% | 1.24 | 168.6 A (+66.7, ×1.65) |
| **pooled** | **86.5 A** | **109.6 A** | **+23.1 A [18.0, 28.3]** | **1.7%** | **1.27** | **135.5 A (+48.9, ×1.57)** |

Brackets are 95% CIs; all gaps have Holm p ≤ 0.0014. Mean truth ratings: AUSTIN 1433, CORPUS_CHRISTI 1330, MIDLAND 1512, EL_PASO 1145, pooled 1355 A.

- **The best day-ahead method costs about 23 A of typical error** (about 1.7% of the rating, 27% more MAE) compared with the live 60-minute forecast; similar in every city (18 to 28 A).
- **The correction methods recover about half the cost of lead time.** 60-minute ml → plain 24-hour forecast costs 49 A; → `ml_cooling_corrected` costs 23 A.
- **The live ml is only slightly better than last hour's rating** (`naive_60min`): 86.5 vs 92.0 A, a gap of 5.5 A [2.9, 8.2]. The best 24-hour forecast is 17.6 A [11.9, 22.5] worse than that naive value. Most of the 60-minute advantage comes from knowing the current rating, not from the model.
- **Tails:** pooled 95th-percentile absolute error is 260 A at 60 min, 316 A for cooling at 24 h and 397 A for raw; RMSE 126, 151 and 187 A.
- **Both horizons over-predict about half the time** (60 min 52%, cooling 50%). Neither point forecast is a safe rating without a band; that question is not addressed here.

**How much to trust this.**

- **(B): direction certain; size believable but probably somewhat too large.** The 60-minute ml here is given reanalysis weather at issue time, the same source as the truth. Live, it gets real-time weather, so its real error is probably larger and the real gap smaller. The 24-hour methods use real archived forecasts, so their errors are realistic.
- **(A) for cooling is solid within this window** (all four cities, both conductor bases, pooled interval excludes zero under the conservative city-clustered bootstrap).
- **(A) for wind is fragile** (p at the threshold, rests on one city, changes under the sensitivity basis).
- Window caveats: TEST was already looked at in 07-11 and is not FRESH; truth is reanalysis, never sensor-validated; only 00/06/12/18 UTC; four cities, so city-clustered intervals are wide. None of this changes protocol v4, the TEST vetoes or read 1.

## Tables (production conductor basis, primary)

Full per-city tables, both bootstrap schemes and the frozen-Drake sensitivity: `tables_production.md`, `tables_frozen-drake.md`. Margin = MAE_B − MAE_A (positive: A better). Pooled CI is the widest 95% interval over the joint-time and city-clustered schemes at block lengths 1/4/8/28; pooled p is the largest over the same runs; Holm across each family's pooled tests. Per-city: 1-D moving-block bootstrap, widest CI and largest p over block lengths; "(city)" = Holm within family × city, descriptive only.

### MAE per arm (A; n = 784 per city, 3136 pooled; % of mean truth rating)

| arm | AUSTIN | CORPUS_CHRISTI | MIDLAND | EL_PASO | POOLED |
|---|---|---|---|---|---|
| ml_60min (live ml) | 85.0 (5.9%) | 67.7 (5.1%) | 91.5 (6.0%) | 102.0 (8.9%) | 86.5 (6.4%) |
| naive_60min | 89.8 (6.3%) | 72.6 (5.5%) | 100.3 (6.6%) | 105.4 (9.2%) | 92.0 (6.8%) |
| ml_cooling_corrected | 106.5 (7.4%) | 85.8 (6.4%) | 119.9 (7.9%) | 126.3 (11.0%) | 109.6 (8.1%) |
| ml_wind_corrected | 126.1 (8.8%) | 88.1 (6.6%) | 123.0 (8.1%) | 130.8 (11.4%) | 117.0 (8.6%) |
| reference_ml_refit_24h | 122.6 (8.6%) | 101.3 (7.6%) | 178.2 (11.8%) | 141.4 (12.3%) | 135.9 (10.0%) |
| raw_forecast | 133.3 (9.3%) | 110.8 (8.3%) | 129.1 (8.5%) | 168.6 (14.7%) | 135.5 (10.0%) |
| persistence_24h | 139.6 (9.7%) | 118.4 (8.9%) | 205.7 (13.6%) | 171.9 (15.0%) | 158.9 (11.7%) |

The five 24 h MAEs reproduce the 07-11 production TEST report (`report_20261102T173449Z`) exactly.

### Other pooled metrics

| arm | bias | RMSE | p95 abs error | over-prediction rate |
|---|---|---|---|---|
| ml_60min | +9.0 | 125.6 | 260.5 | 0.521 |
| naive_60min | +2.3 | 136.6 | 296.6 | 0.516 |
| cooling | +4.5 | 151.1 | 315.5 | 0.496 |
| wind | −24.3 | 164.9 | 353.7 | 0.448 |
| reference | +16.5 | 177.2 | 365.9 | 0.536 |
| raw | +7.7 | 187.2 | 396.7 | 0.501 |
| persistence_24h | +0.8 | 216.1 | 463.4 | 0.484 |

### Family A (24 h vs 24 h; 6 tests)

| A vs B | scope | MAE A | MAE B | margin | 95% CI | p | Holm p |
|---|---|---|---|---|---|---|---|
| **cooling vs reference** | **pooled** | 109.6 | 135.9 | **+26.3** | [13.1, 49.0] | 0.0002 | **0.0012** |
| | AUSTIN | 106.5 | 122.6 | +16.2 | [8.2, 22.5] | 0.0002 | 0.0012 (city) |
| | CORPUS_CHRISTI | 85.8 | 101.3 | +15.6 | [9.4, 21.8] | 0.0002 | 0.0012 (city) |
| | MIDLAND | 119.9 | 178.2 | +58.3 | [46.8, 73.3] | 0.0002 | 0.0012 (city) |
| | EL_PASO | 126.3 | 141.4 | +15.1 | [9.7, 20.7] | 0.0002 | 0.0012 (city) |
| **wind vs reference** | **pooled** | 117.0 | 135.9 | **+18.9** | [0.5, 44.8] | 0.041 | **0.041** |
| | AUSTIN | 126.1 | 122.6 | −3.5 | [−13.3, 6.8] | 0.51 | 0.51 (city) |
| | CORPUS_CHRISTI | 88.1 | 101.3 | +13.3 | [6.0, 20.3] | 0.0004 | 0.0012 (city) |
| | MIDLAND | 123.0 | 178.2 | +55.2 | [42.5, 72.8] | 0.0002 | 0.0012 (city) |
| | EL_PASO | 130.8 | 141.4 | +10.6 | [2.2, 19.4] | 0.012 | 0.012 (city) |
| **cooling vs raw** | **pooled** | 109.6 | 135.5 | **+25.8** | [13.7, 37.8] | 0.0002 | **0.0012** |
| | AUS / CC / MID / EP | | | +26.9 / +25.0 / +9.2 / +42.3 | all exclude 0 | ≤ 0.0002 | ≤ 0.0012 |
| **wind vs raw** | **pooled** | 117.0 | 135.5 | **+18.5** | [6.2, 32.4] | 0.0002 | **0.0012** |
| | AUS / CC / MID / EP | | | +7.2 / +22.7 / +6.1 / +37.8 | AUSTIN [0.1, 17.1] | AUSTIN 0.046; others ≤ 0.0034 | AUSTIN 0.092; others ≤ 0.0034 |
| **cooling vs persistence_24h** | **pooled** | 109.6 | 158.9 | **+49.3** | [31.6, 74.8] | 0.0002 | **0.0012** |
| **wind vs persistence_24h** | **pooled** | 117.0 | 158.9 | **+41.9** | [19.1, 71.0] | 0.0002 | **0.0012** |

### Family B (cost of lead time; 7 tests)

| A vs B | MAE A | MAE B | margin | 95% CI | % of mean rating | MAE ratio B/A | Holm p | per city (AUS / CC / MID / EP) |
|---|---|---|---|---|---|---|---|---|
| ml60 vs cooling | 86.5 | 109.6 | **+23.1** | [18.0, 28.3] | 1.7% | 1.27 | 0.0014 | +21.5 / +18.1 / +28.4 / +24.4 |
| ml60 vs wind | 86.5 | 117.0 | +30.5 | [21.8, 38.8] | 2.2% | 1.35 | 0.0014 | +41.1 / +20.4 / +31.5 / +28.9 |
| ml60 vs reference | 86.5 | 135.9 | +49.4 | [33.2, 74.6] | 3.6% | 1.57 | 0.0014 | +37.6 / +33.7 / +86.7 / +39.5 |
| ml60 vs raw | 86.5 | 135.5 | **+48.9** | [37.2, 61.2] | 3.6% | 1.57 | 0.0014 | +48.3 / +43.1 / +37.6 / +66.7 |
| ml60 vs persistence_24h | 86.5 | 158.9 | +72.4 | [50.7, 100.6] | 5.3% | 1.84 | 0.0014 | +54.7 / +50.7 / +114.2 / +70.0 |
| ml60 vs naive60 | 86.5 | 92.0 | +5.5 | [2.9, 8.2] | 0.4% | 1.06 | 0.0014 | +4.8 / +5.0 / +8.8 / +3.5 (EP CI [−0.6, 7.5]) |
| naive60 vs cooling | 92.0 | 109.6 | +17.6 | [11.9, 22.5] | 1.3% | 1.19 | 0.0014 | +16.7 / +13.1 / +19.6 / +20.9 |

Every per-city interval in family B excludes zero except ml60 vs naive60 in EL_PASO.

### Sensitivity: frozen-Drake basis (all cities Drake 75 °C, the 12 frozen artifacts)

- Family A, pooled: cooling vs reference +24.8 [10.7, 48.4], Holm p 0.001; **wind vs reference +17.9 [−2.1, 44.6], Holm p 0.090 (not significant)**; cooling vs raw +24.9, wind vs raw +18.0, cooling vs persistence +48.5, wind vs persistence +41.6, all Holm p 0.001. CORPUS_CHRISTI, MIDLAND and EL_PASO identical to production; AUSTIN: cooling 91.3, wind 109.2, reference 101.7, raw 114.5 A.
- Family B: AUSTIN is not comparable (the live ml is trained on AUSTIN's Drake 100 °C; against 75 °C truth its MAE is 262 A, measuring the conductor change, not forecasting), so four-city pooled B is not interpreted. On the three cities with identical points: ml60 vs cooling +23.6 [17.1, 29.9], vs raw +49.1 [34.4, 65.7], vs naive60 +5.8 [2.5, 9.2], all Holm p 0.0014, matching production.

### Post-hoc descriptive context (not planned, no tests; `context_posthoc.md`)

- Over every hour of the window the live ml's 60-minute MAE is lower than at the slot hours (AUSTIN 74.0, CORPUS_CHRISTI 51.7, MIDLAND 77.8, EL_PASO 86.0 A vs 85.0, 67.7, 91.5, 102.0 at the slots), so the 00/06/12/18 UTC slots are harder than average for a 1-hour forecast and the all-hours gap to 24 h would likely be somewhat larger (not testable: 24 h methods exist only at the slots).
- Cooling minus ml60 gap by slot hour (pooled): +13.5 A at 00 UTC, +22.1 at 06, +30.8 at 12, +26.0 at 18.

## Method

- **24 h methods**, rebuilt in memory with the TEST scorer's own functions: `forecast_test_split_score.cached_test_provider` (reads only the `_2024-01-20_2026-09-29_` cache) and `forecast_shadow_confirm._score_city` with `make_headline_loader`, under `production_city_point` (production) or the Drake point (frozen). No evidence directory created; nothing written under `data/` (file-timestamp check). Leakage probe passed in every city; the scorer's truth equals the hourly truth used here at every valid time (max difference 0.0).
- **Live 60-minute ml**: `data/models/forecast_<CITY>.joblib` (B2 retrain), issued at valid time − 60 min with `ampacity_forecast.build_ml_features` at the issue hour. Features: rating 1, 2, 3 and 6 h before issue; mean of those 6 h; air temperature, line-perpendicular wind and solar at issue time; UTC hour. The rating at issue time is not a feature. Hourly series: the cached frame's truth weather on a complete hourly grid, production point, perpendicular wind as in `forecast_training.city_training_frame`.
- **Same basis as training**: on 17,064 shared hours (2024-01-21..2025-12-31) the rebuilt inputs equal `data/models/training_frame_<CITY>.csv` to within 5e-13 in every city; `forecast_ampacity(method="ml")` reproduces the vectorised prediction exactly at 5 spot times per city.
- **`naive_60min`** = truth rating 1 hour before the valid time. 784 of 784 rows per city for every arm.
- **Statistics**: `forecast_shadow_score_stats` unmodified (`per_city_comparison`, `moving_block_bootstrap_means`, `bootstrap_p_two_sided`, `pooled_comparison` joint time-block and two-stage city-cluster, `holm`). Block lengths 1/4/8/28 six-hourly rows, 10,000 resamples, seed 20260929.

## Caveats

1. Exploratory, not pre-registered; TEST partly already seen (07-11), not FRESH; nothing here bears on the signed v4 decision.
2. The 60-minute ml gets idealised inputs (reanalysis weather at issue time, same source as the truth); live, its error is probably larger, so the (B) gap is probably overstated; not measurable from the cached data.
3. Truth is reanalysis through IEEE 738, never sensor-validated; forecasts whose inputs are close in time to the truth weather (naive and ml at 60 min) benefit most.
4. Only four cities; city-clustered intervals are wide; a pooled result can rest on one city (wind vs reference rests on MIDLAND).
5. The 24 h methods exist only at 00/06/12/18 UTC, so (B) is measured at those hours only.
6. p values are limited by the resample count (floor about 0.0002); Holm p 0.0012 and 0.0014 are that limit.

## Files

`PLAN.md` (plan, written before results); `build_rows.py` → `rows_production.csv`, `rows_frozen-drake.csv`, `checks.json`; `stats.py` → `results_*.json`, `descriptive_*.csv`; `tables.py` → `tables_production.md`, `tables_frozen-drake.md`; `context_posthoc.py` → `context_posthoc.md` (post-hoc, descriptive); `REPORT.md`. Reproduce from the repo root, in order: `PYTHONPATH=backend .venv/bin/python docs/data-science/exploratory/2026-11-02_horizon_comparison/build_rows.py`, then `stats.py`, `tables.py`, `context_posthoc.py`.
