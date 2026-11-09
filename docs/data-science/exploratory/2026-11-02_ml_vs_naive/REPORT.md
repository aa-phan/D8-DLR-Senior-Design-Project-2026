# ml vs naive at 60 minutes: is the improvement significant?

Exploratory, not pre-registered; does not change signed protocol v4 or read 1. Plan written before any result: `PLAN.md`.

## In plain English

- **What was compared:** the live `ml` and `naive` 60-minute ampacity forecasts on the same hours, asking whether ml's average miss is smaller by more than luck and hour-to-hour correlation explain.
- **September replay (Sep 15–28, recorded observations, 07-14 re-run): no.** On hours where ml really fed G6, ml led by +1.9 A pooled (p = 0.47); EL_PASO +5.4 A (p = 0.087, Holm 0.35), CORPUS_CHRISTI +0.7 A, AUSTIN and MIDLAND about 0. "As deployed" (including the B5 naive-fallback hours) is the same picture diluted: +1.6 A, p = 0.47. The window is too short: the smallest reliably detectable difference is 7–13 A per city, about 5–6 A pooled.
- **2026-01-01 to 2026-09-29 (out of sample, reanalysis weather): yes, in every city.** AUSTIN +3.9, CORPUS_CHRISTI +4.7, MIDLAND +3.3, EL_PASO +3.8 A; pooled +3.9 A (95% CI 3.1 to 4.7), MAE 75.6 naive vs 71.7 ml. All p at the bootstrap floor (0.0002), Holm 0.0008, at every block length and both pooled schemes.
- **How much to trust it:** the direction is solid. The size is small, about 0.3% of mean ampacity: below the project's 5 A bar and far below the v4 bar of 2% of mean truth (about 24–31 A). The 9-month truth is reanalysis through IEEE 738, the same kind of data ml was trained on; on recorded observations the edge was smaller (see caveats).

## Tables

d = naive |error| minus ml |error| (positive = ml better). CI from a 24 h moving-block bootstrap (B = 10000, seed 20260929). Headline p is the largest over 6/24/72 h blocks; Holm across the 4 cities. MDD = minimal detectable difference at 80% power (per city at α = 0.05/4, pooled at 0.05).

### Part 1a: Sep replay, hours where ml fed G6

| City | n | MAE naive / ml (A) | d (A) | 95% CI | p (6/24/72 h) | Holm p | n_eff (ACF / boot) | MDD (A) |
|---|---|---|---|---|---|---|---|---|
| AUSTIN | 261 | 81.2 / 81.2 | +0.03 | −7.0, 6.4 | .97/.86/.73 | 1.00 | 166 / 116 | 12.7 |
| CORPUS_CHRISTI | 233 | 62.4 / 61.7 | +0.74 | −3.9, 3.9 | .90/.94/.73 | 1.00 | 200 / 262 | 7.3 |
| MIDLAND | 169 | 66.4 / 66.6 | −0.18 | −4.9, 5.1 | .99/.98/.98 | 1.00 | 139 / 154 | 12.4 |
| EL_PASO | 330 | 116.9 / 111.5 | +5.36 | −0.2, 11.8 | .046/.058/.087 | 0.35 | 330 / 308 | 10.6 |
| POOLED (city-clustered) | 993 | 86.1 / 84.2 | +1.93 | −2.4, 6.0 | 0.47 | – | boot 472 | 5.9 |

### Part 1b: Sep replay, as deployed (fallback hours in brackets)

| City | n (fallback) | d (A) | 95% CI | p | Holm p | MDD (A) |
|---|---|---|---|---|---|---|
| AUSTIN | 317 (56) | +0.03 | −5.8, 5.0 | 0.97 | 1.00 | 10.0 |
| CORPUS_CHRISTI | 316 (83) | +0.54 | −2.6, 3.1 | 0.89 | 1.00 | 5.5 |
| MIDLAND | 251 (82) | −0.12 | −3.0, 3.2 | 0.99 | 1.00 | 8.2 |
| EL_PASO | 336 (6) | +5.26 | −0.2, 11.5 | 0.087 | 0.35 | 10.2 |
| POOLED | 1220 | +1.57 | −1.9, 5.3 | 0.47 | – | 5.1 |

In fallback hours both sides hand G6 the identical naive centre, so d = 0 there. A third population reproduces the p7 README MAEs exactly (84.6/87.6, 61.3/62.9, 80.2/80.3, 112.6/117.3), which checks the pipeline: pooled +2.5 A, p = 0.18.

### Part 2: 2026-01-01T00Z to 2026-09-29T23Z (6528 hours per city)

| City | MAE naive / ml (A) | d (A) | 95% CI | p | Holm p | Diebold-Mariano p (NW lag 24 h) | n_eff (ACF / boot) | MDD (A) |
|---|---|---|---|---|---|---|---|---|
| AUSTIN | 76.9 / 73.0 | +3.86 | 2.6, 5.1 | 0.0002 | 0.0008 | <1e-4 | 6086 / 4639 | 2.2 |
| CORPUS_CHRISTI | 57.7 / 53.0 | +4.69 | 3.8, 5.6 | 0.0002 | 0.0008 | <1e-4 | 5230 / 5091 | 1.7 |
| MIDLAND | 82.5 / 79.3 | +3.26 | 2.1, 4.4 | 0.0002 | 0.0008 | <1e-4 | 5130 / 4930 | 2.1 |
| EL_PASO | 85.2 / 81.4 | +3.79 | 2.5, 5.0 | 0.0002 | 0.0008 | <1e-4 | 6528 / 5198 | 2.4 |
| POOLED | 75.6 / 71.7 | +3.90 | 3.1, 4.7 | 0.0002 | – | – | boot 12678 | 1.1 |

### Part 2 by month (pooled)

| Month | Jan | Feb | Mar | Apr | May | Jun | Jul | Aug | Sep |
|---|---|---|---|---|---|---|---|---|---|
| d (A) | −0.1 | +0.7 | +2.9 | +1.7 | +5.2 | +5.2 | +5.5 | +6.7 | +7.2 |
| p | 0.90 | 0.53 | 0.005 | 0.28 | <0.001 | <0.001 | <0.001 | <0.001 | <0.001 |

With Holm across all 36 city-months, 16 stay below 0.05, all March–September and all favouring ml; no city-month favours naive significantly (`part2_monthly.csv`).

Bands (Part 1, descriptive): ml bands 3–11% narrower than naive at about the same coverage; both slightly under the 90% nominal (MIDLAND lowest, 0.85 ml / 0.86 naive). ml over-forecasts AUSTIN by 20–29 A in this window (`part1_band_coverage.csv`).

Bake-off (`data/models/bakeoff_report.json`): contains a naive baseline on the 2023–2025 training years only, on different rows (ml out-of-fold 21910 vs naive 26292), unpaired and without intervals, so it cannot answer the significance question. Its ml advantage is 1.3–2.6 A, same direction. Persisted models: MLP for AUSTIN, MIDLAND, EL_PASO; HGB for CORPUS_CHRISTI.

## Method

- `mae_a` (real_data_validation) = mean |`computed_a` − `fc_amps`| over `n_band`; `computed_a` is IEEE 738 from the traced observation with the production conductor; `fc_amps` is the stored forecast from history ending one hour earlier, kept even when withheld from G6. `forecast_used_by_g6` is True only when ml fed G6; `g6_forecast_method` records which band gated G6. The two replays' `computed_a` agree on every hour.
- Part 2 frames: one Open-Meteo Archive request per city for 2025-12-25..2026-09-29 (December rows warm-up only), fed into the unmodified `forecast_training.city_training_frame` by swapping `fetch_city_weather` in-process. ml = `.predict` on `build_ml_features` at t−1; naive = `dlr_amps`(t−1); truth = `dlr_amps`(t). Spot-checked against `forecast_ampacity` on 8 random hours per city: max difference 5e-13 A.
- Statistics: primitives imported unchanged from `backend/forecast_shadow_score_stats.py` (joint and city-cluster resamplers, percentile interval, two-sided bootstrap p, ACF effective n, MDD, Holm), on a calendar-hour grid with empty hours kept as empty slots.
- Safety: a timestamp < 2026-09-30 assertion on every load; nothing under `data/shadow` opened; no forbidden script run; no tracked file changed.

## Caveats

- Truth is IEEE 738 on weather inputs, not a sensor; Part 2 scores ml on the same kind of reanalysis-derived series it was trained on.
- Data source may matter (post-hoc): Part 2 restricted to Sep 15–28 gives +5.0 / +7.4 / +5.6 / +6.7 A per city (pooled +6.2, p 0.0002), while on recorded observations over the same hours ml led by only +0.0 / +0.7 / −0.2 / +5.4 A. Part of ml's edge may not carry over to station-based ratings.
- The README's AUSTIN ml gain (3.0 A) comes from hours where ml was withheld from G6 (post-hoc): there the unused ml forecast beat naive by +15.9 A (n 60); on hours where ml fed G6 AUSTIN's gain is 0.0 A.
- Seasonal: no ml advantage in Jan–Feb; 5–7 A from May to September.
- Conclusions unchanged across 6/24/72 h blocks; bootstrap effective n sometimes exceeds n (negative autocorrelation in d).
- AUSTIN at Drake 100 °C, others at 75 °C: amp gaps not like-for-like across cities; the pooled mean weights every row equally.
- Plan deviations: none in the planned analyses; the two post-hoc checks were added after seeing results.

## Files

`PLAN.md`, `stats_lib.py`, `part1_sep_replay.py`, `part2_2026_oos.py`, `part1_paired_tests.csv`, `part1_band_coverage.csv`, `part1_results.json`, `part2_paired_tests.csv`, `part2_monthly.csv`, `part2_meta.json`, `part2_errors_<CITY>.csv`, `posthoc_part2_restricted_to_part1_window.csv`, `cache/open_meteo_<CITY>_2025-12-25_2026-09-29.csv`. Re-run: `PYTHONPATH=backend:docs/data-science/exploratory/2026-11-02_ml_vs_naive .venv/bin/python <script>`.
