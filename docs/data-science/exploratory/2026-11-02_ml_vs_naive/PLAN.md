# Plan: is the live `ml` 60-minute forecast better than `naive`? (exploratory)

**Exploratory, not pre-registered; does not change signed protocol v4 or read 1.**
Written 2026-11-02, before any result below was computed. Nothing here reads or
computes anything at or after 2026-09-30T00:00:00Z (asserted in code).

## Question

Is the absolute error of the live `ml` 60-minute-ahead ampacity point forecast
smaller than that of the `naive` forecast (last value), by more than chance and
serial correlation explain? Per city (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO)
and pooled.

## Metric and pairing (both parts)

For each city and target hour t: e_m(t) = truth(t) - centre_m(t), the forecast
centre made one hour earlier. Paired difference d(t) = |e_naive(t)| - |e_ml(t)|.
**Positive d = ml better.** Point estimate = mean of d (= MAE_naive - MAE_ml).
Complete case: an hour enters only if both centres and the truth exist.

## Test (both parts)

Reuses `backend/forecast_shadow_score_stats.py` primitives (imported, not
modified): percentile interval, `bootstrap_p_two_sided`, `acf_effective_n`,
`minimum_detectable_difference`, `holm`, and the slot-grid resamplers
`_gather_means_joint` / `_gather_means_cluster`, here on an **hourly** grid
(calendar hours, empty hours kept as empty slots, so a block always spans L
real hours even where a population has holes).

- Per city: moving-block bootstrap on the city's hourly grid, B = 10000, seed
  20260929 (`config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE`).
  **Primary block length L = 24 h**; sensitivity L = 6 h and 72 h. Reported:
  n, mean d, 95% percentile CI at L = 24, two-sided bootstrap p at each L, the
  headline p = max over L in {6, 24, 72} (conservative, as the project's PD-04),
  Holm-adjusted headline p across the 4 cities (family = 4, alpha 0.05).
- Pooled: city-clustered two-stage resample (`_gather_means_cluster`) and joint
  time block (`_gather_means_joint`), each at L in {6, 24, 72}; row-weighted
  mean; headline p = max over both schemes and all L; CI = widest 95%. Pooled
  is reported separately, not in the Holm family.
- Effective n: per city `acf_effective_n(d)` and bootstrap n_eff =
  var(d) / var(bootstrap means) at the L giving the largest SE; pooled n_eff
  from the module's same definition.
- Minimal detectable difference (80% power): per city at alpha = 0.05/4
  (Holm's strictest step) using the largest bootstrap SE over L; pooled at
  alpha = 0.05.
- Sensitivity (not headline): Diebold-Mariano test on d with a Newey-West
  (Bartlett) variance, lag 24 h, per city.

## Part 1 windows and populations (offline replays, Sep 2026)

Inputs (read only): `data/historical/real_data_validation_2026-09-08_2026-09-28_replay_{ml,naive}_p7{.csv,_trace.jsonl}`.
Loaded with `real_data_validation.load_trace` + `classify_steps` exactly as the
p7 report did (start 2026-09-08T00Z, end 2026-09-28T23Z, 1 h steps, warm-up
168 h). Scored hours only (2026-09-15T00Z .. 2026-09-28T23Z, 336 per city).
Truth = `computed_a` (IEEE 738 recomputed from the traced observation with the
production conductor), the same truth `mae_a` uses. An hour must be
G6-evaluated (outcome `ok` or `G6`) in both replays.

- (a) **ml actually forecast**: hours whose ml-replay `g6_forecast_method == "ml"`.
  ml centre = ml-replay `fc_amps`; naive centre = naive-replay `fc_amps`.
- (b) **as deployed**: every G6-evaluated hour where each replay handed G6 a
  band (`g6_amps` present). ml side = ml-replay `g6_amps` (ml, or the naive
  B5 fallback); naive side = naive-replay `g6_amps`. Hours where either had no
  band are excluded and counted.
- (c) secondary, for reconciliation with the p7 README `mae_a`: the README
  population (`n_band`: G6-evaluated, forecast band width > 0, computed
  present), ml-replay `fc_amps` vs naive-replay `fc_amps` (ml forecasts withheld
  from G6 included). Same tests; Holm within (c) only.

Descriptive side table for (a) and (b): nominal band coverage (truth inside
[lo, hi]) and mean band width for each method, same hours.

## Part 2 window (longer out-of-sample, reanalysis)

Target hours 2026-01-01T00:00Z .. 2026-09-29T23:00Z (the ml models were trained
on 2023-2025). Per city, build the frame with `forecast_training.city_training_frame`
(production conductor via `city_point.production_city_point`, projected wind,
row validation), with `fetch_city_weather` replaced in-process (no file change)
by one Open-Meteo Archive request for 2025-12-25 .. 2026-09-29 (end date
<= 2026-09-29; the Dec 2025 rows are lag/warm-up inputs only, never scored).
Raw weather is cached under this folder; max timestamp asserted < 2026-09-30.

- ml: features from `ampacity_forecast.build_ml_features` at hour t-1 (the last
  history row, as `forecast_ampacity` uses), model `data/models/forecast_<CITY>.joblib`
  `.predict`, target hour t. Spot-checked against `forecast_ampacity(prefix, method="ml")`.
- naive: centre = dlr_amps(t-1) (`forecast_ampacity(..., method="naive")`).
- truth: dlr_amps(t) from the frame.
- A target hour is excluded (and counted) if any of the 7 hourly rows t-7..t-1
  is missing (the live ml lookback rule would withhold ml) or t itself is missing.
- Same per-city / pooled / Holm / L in {6, 24, 72} tests; plus per-month
  (Jan..Sep) per city and pooled, descriptive, with Holm across the 36
  city-months shown for reference.

Also reported (no new test): what `data/models/bakeoff_report.json` says about
naive on the 2023-2025 time-series CV.

## Will not change after results

If anything above must change, the change and the reason are written in
REPORT.md under "Deviations from plan".
