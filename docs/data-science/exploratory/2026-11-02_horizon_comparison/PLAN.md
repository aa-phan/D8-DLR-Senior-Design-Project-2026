# Horizon comparison: day-ahead (24 h) shadow methods vs the live 60-minute `ml` — analysis plan

**Exploratory, not pre-registered; does not change signed protocol v4 or read 1.**
Written 2026-11-02 before any result of this analysis was computed. The only results already seen are the
published 07-11 TEST reports (`data/shadow/evaluation/v4-test/report_20261102T085108Z` frozen-drake,
`report_20261102T173449Z` production), which hold per-city MAEs but no per-row data.

## Questions

- **(A) Same 24 h horizon, different method.** Do `ml_cooling_corrected` and `ml_wind_corrected` have a lower
  MAE than `reference_ml_refit_24h` (the live-`ml` design re-targeted 24 h ahead), than `raw_forecast` and than
  `persistence_24h`?
- **(B) Cost of lead time.** On the same valid times and the same truth, how much larger is the error of the 24 h
  forecasts than that of the live 60-minute `ml` forecast? A 60-minute forecast is expected to win; the question
  is the size of the gap.

## Window and rows

- Valid times `2026-03-18T00:00Z <= v < 2026-09-30T00:00Z`, the six-hourly exact-24 h-lead slots of the TEST
  split (784 per city, 4 cities). Every timestamp read or computed is asserted `< 2026-09-30T00:00Z`.
- Data: only the cached `anchored_pair_frame_<CITY>_2024-01-20_2026-09-29_lead24_previous_runs.csv` frames, read
  through `forecast_test_split_score.cached_test_provider` (no network). If a needed hour is absent the row is
  excluded and counted; nothing is imputed. No Open-Meteo request is planned.
- The 24 h predictions are reproduced in memory with the scorer's own building blocks
  (`forecast_shadow_confirm._score_city` with the scorer's loader and point resolver), no evidence directory,
  nothing written under `data/`. Sanity check: per-city MAEs must match the 07-11 reports.

## Conductor basis and truth

- **Primary: production basis** (`city_point.production_city_point`; AUSTIN Drake 100 °C with the refit
  cooling/reference artifacts under `data/models/conductor_refit/v3-powersystems-2026-11-02/`; other cities
  identical to Drake). **Sensitivity: frozen-drake** (all cities Drake 75 °C, the 12 frozen artifacts).
- Truth = Open-Meteo Archive reanalysis weather at the valid time through IEEE 738 under the basis's point (the
  scorer's `truth_amps`). Reanalysis-derived, never sensor-validated.

## The 60-minute arms (B)

- `ml_60min`: the live model `data/models/forecast_<CITY>.joblib`, issued at `t = v − 60 min`. Its inputs are
  exactly `ampacity_forecast.build_ml_features` evaluated on the row at `t` of an hourly frame built like
  `forecast_training.city_training_frame`: `dlr_amps` = IEEE 738 ampacity under the production point from
  reanalysis weather; `wind_speed` = line-perpendicular wind (B2); `air_temp`, `solar_radiation` as observed.
  So the features are `dlr_amps` at t−1, t−2, t−3, t−6 h, the mean of t−6..t−1 h, reanalysis weather at t, and
  the UTC hour of t. The hourly frame is the cached frame's truth weather reindexed to a complete hourly grid (a
  feature window touching a missing hour excludes the row). The cached frame's truth columns come from the same
  `open_meteo_provider.fetch_open_meteo` archive call the training frame used; this is checked numerically on the
  overlapping 2024-01-20..2025-12-31 hours against `data/models/training_frame_<CITY>.csv`.
- Under the frozen-drake sensitivity, `ml_60min` features stay on the production point (that is what the model
  was trained on) while truth is Drake 75 °C; for AUSTIN this is a mismatch and AUSTIN's (B) results under
  frozen-drake are reported as not comparable. The other three cities have identical points in both bases.
- Context arms: `naive_60min` = truth ampacity at `v − 1 h` (the last observed rating); `persistence_24h` (as in
  the scorer).

## Metric and pairing

- Absolute error |prediction − truth| in amps; MAE. Paired, complete-case per pair on (city, valid time). For an
  ordered pair (A, B) the paired series is `d = |e_B| − |e_A|`; a positive mean margin means A has the lower MAE.
- Descriptive extras per arm (not tested): bias, RMSE, 95th percentile |e|, over-prediction rate (forecast >
  truth), MAE as % of mean truth.

## Inference (reusing `forecast_shadow_score_stats`, not modified)

- Per city: 1-D moving-block bootstrap of the mean of `d` (`moving_block_bootstrap_means`) at block lengths
  1, 4, 8, 28 six-hourly rows, 10 000 resamples, seed 20260929. Reported CI = the widest 95 % percentile
  interval over block lengths; p = the largest two-sided bootstrap p over block lengths
  (`bootstrap_p_two_sided`).
- Pooled: `pooled_comparison` (joint time-block and city-clustered two-stage, same block lengths); headline p =
  max over both schemes and all block lengths (PD-04 convention); CI = widest 95 % over all. Both schemes
  reported; the city-clustered one is the conservative one with 4 cities.
- Multiplicity: Holm at α = 0.05 within each family on the pooled headline p. Per-city p values are also
  Holm-adjusted within (family × city) sets as a secondary, labelled descriptive.
- **Family A (6 tests):** (cooling, reference), (wind, reference), (cooling, raw_forecast), (wind, raw_forecast),
  (cooling, persistence_24h), (wind, persistence_24h).
- **Family B (7 tests):** (ml_60min, X) for X in {ml_cooling_corrected, ml_wind_corrected,
  reference_ml_refit_24h, raw_forecast, persistence_24h}; (ml_60min, naive_60min); (naive_60min,
  ml_cooling_corrected).
- "Best 24 h forecast" is fixed in advance as `ml_cooling_corrected`: it has the lowest TEST MAE in every city in
  the already-published 07-11 production report. The other 24 h arms are in family B anyway.
- Effect sizes reported in amps and as % of the city's mean truth ampacity, and as the ratio MAE_24h / MAE_60min.

## Caveats planned to be stated

- TEST is partly already seen (07-11) and is not FRESH; this does not confirm anything under protocol v4.
- `ml_60min` is fed reanalysis at issue time, i.e. idealised "observed" weather from the same source as the
  truth; the live system uses real-time weather, so the real 60-min error is likely somewhat larger. The 24 h
  arms use archived GFS previous-runs forecasts (real forecast error). Shared-weather truth flag (V4) applies.
- Same-source truth favours methods whose inputs are the truth weather at nearby times (naive/ml 60 min).
