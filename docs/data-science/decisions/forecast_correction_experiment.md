# Ampacity Forecast Correction Experiment — 24-Hour Primary Comparison

**Status:** In progress — this record is committed with only the sections that can honestly be
written before the held-out test set is read. The Expectation below is written and frozen at this
commit; Measured results, Verdict, Limitations, and Open Questions are filled in by Plan 03-06's
own Task 3 (Measured results) and Plan 03-07 (Verdict, Limitations, Open Questions) after the
single test-set run.

**Purpose:** This document discharges D-02 (build and run the full seven-approach comparison,
explicitly reporting a null result if nothing beats persistence) and D-04 (the 24-hour
realizable-lead pivot) for Phase 3 of the ml-modeling workstream. It follows the same 9-section,
working-log shape as `forecasting_model.md` in this directory, and records this workstream's
no-peeking discipline mechanically: the commit that lands this file's Expectation section is the
SAME commit that unlocks `backend/forecast_experiment.py`'s held-out test split, so `git log` — not
a date typed into this document — is the audit trail proving the Expectation predates every
test-set read (ROADMAP Success Criterion 5).

## What was built

An offline experiment harness (`backend/forecast_experiment.py`, built across Plans 03-01 through
03-06) that compares seven approaches to ampacity forecasting at a verified 24-hour lead, against
naive persistence, for both of this project's corridors (`AUSTIN_CORPUS_CHRISTI`,
`MIDLAND_EL_PASO`). This phase exists because Phase 1's `forecasting_model.md` found the
production `"ml"` method lost to naive persistence at a 60-minute horizon on both corridors; this
phase asks the same question at a 24-hour horizon, using a genuinely different forecast data
source and a materially larger set of candidate approaches.

**The seven arms:**

- **Arm 0 — `persistence_24h`.** The naive "same time yesterday" baseline: the corridor's own
  truth ampacity computed exactly 24 hours before the valid time. Built as a direct shift of the
  full unfiltered truth series, never through `ampacity_forecast`'s one-row-lag production helper
  (which would silently score a 1-hour-old baseline at this project's hourly cadence).
- **Arm 1 — `nwp_wind_delta`.** A cheap non-fitted baseline: the observed wind 24 hours ago,
  adjusted by the forecast's own predicted change in wind over the lead, with every other input
  held at its latest-observed value. Physically clamped at zero wind speed, with the clamp-hit
  rate reported rather than silently applied.
- **Arm 2 — `raw_forecast`.** The Open-Meteo Previous-Runs forecast's own weather, run through the
  same IEEE 738 physics core every other DLR component uses, with no correction of any kind.
- **Arm 3 — `ml_wind_corrected`.** A `scikit-learn` estimator, fit in wind u/v vector space (never
  on a wrapping compass direction), that corrects the forecast's wind before the physics runs.
- **Arm 4 — `ml_cooling_corrected`.** A `scikit-learn` estimator that corrects the physics'
  convective heat-loss term directly, substituted back through `thermal_model.ieee738_ampacity`'s
  `q_conv_override` seam.
- **Arm 5 — `reference_ml_refit_24h`.** The production `"ml"` method's own estimator family
  (`MLPRegressor`, matching `forecasting_model.md`'s persisted winner), refit from scratch on
  train-plus-validation rows at an explicit 24-hour target shift — never the persisted production
  artifact, and never touching the runtime module's per-corridor model cache, since that artifact
  was trained on years overlapping this experiment's test range.
- **Arm 6 — `oracle_observed_future_wind`.** A non-forecast diagnostic: observed future wind
  substituted into the forecast's thermal inputs, bounding the maximum benefit any wind correction
  could ever achieve. Structurally isolated from the candidate mapping in every report this module
  emits — it can never be selected as a winner and its margin is never presented as achievable.

**D-04's pivot.** This phase originally scored a 1-hour idealized lead (Plan 03-01), but that
data source's "forecast" turned out to be empirically bit-identical to "truth" for the
necessarily-recent window the calibration gate required — confirmed by raw HTTP requests bypassing
this project's own code, across three cities. Rather than continue chasing a window where a
genuinely independent forecast and a compliant lead-time claim could hold simultaneously at 1 hour
(which may not exist for this data source), Plan 03-03 promoted a 24-hour lead via Open-Meteo's
Previous Runs API to this phase's PRIMARY comparison. The legacy 1-hour arm is retained in the
codebase as a documented, labelled, non-primary curiosity — its raw-forecast score is an artifact
of the bit-identical data source, never a competing candidate against this record's primary
verdict.

## Data provenance

**Forecast source.** Open-Meteo's Previous Runs API, pinned to `models=gfs_seamless` (a distinct
model pin from the legacy arm's `ecmwf_ifs`, since `ecmwf_ifs`'s Previous-Runs archive is null for
the overwhelming majority of this phase's window). `previous_day1`'s effective lead is measured,
not assumed, to be `24 + (valid_hour % 6)` hours — exactly 24.0 hours only when
`valid_hour % 6 == 0` — live-verified in-repo against the Single-Runs product
(`forecast_leadtime_calibration.assert_exact_offset_lead`) before any arm was scored. Scored rows
are filtered to this exact-24h-lead subset; the phase never scores the broader 24–29-hour smear as
though it were a single lead.

**Truth source.** Open-Meteo's Archive API (`open_meteo_provider.fetch_open_meteo`), the same
reanalysis source every other component of this project's weather ingestion already uses.

**Physics.** Both corridors' endpoint cities' weather is run through `thermal_model.
perpendicular_wind` (projected onto the corridor's own bearing) and `thermal_model.
ieee738_ampacity`, using that corridor's `ConductorConfig` — the same IEEE 738 core every other DLR
component calls. The corridor-level value at each timestamp is the elementwise minimum of the two
endpoint cities' computed ampacities (this codebase's established weakest-link convention),
reduced independently for the truth group, the anchor (T-24h) group, and each arm's own prediction,
since the bottleneck city at one time is not necessarily the bottleneck 24 hours later.

**Window.** `2024-01-20` (the live-bisected Previous-Runs archive start for `gfs_seamless`, common
to all four project cities) through "yesterday" (UTC) at run time. The full assembled window
carries 23,592 hourly rows per city before any filter; after the exact-24h-lead filter and the
three-way calendar train/validation/test split, Plan 03-04's validation-split live run scored 786
rows per corridor (window `2024-01-20` → `2026-09-29`) — the test split's own row count is reported
in Measured results below, read for the first time only after this section is committed.

**Split.** A fixed calendar train/validation/test split (`experiment_splits.calendar_split`),
never shuffled and never re-derived per arm — genuinely new infrastructure for this codebase, since
every pre-existing evaluation mechanism here (`backtest_residuals`, `TimeSeriesSplit`) is
walk-forward-only, not a true held-out split. The split boundaries are computed once, from the
corridor's full assembled window, and are identical across every arm and every corridor.

## Configuration measured

| Parameter | Value | Source |
|---|---|---|
| Primary lead | 24 hours | `config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS` |
| Exact-lead filter | `valid_hour % 6 == 0` | `config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER` |
| Previous-Runs model pin | `gfs_seamless` | `open_meteo_forecast_provider.PREVIOUS_RUNS_MODEL_ID` |
| Window start | 2024-01-20 | `config.FORECAST_EXPERIMENT_PREVIOUS_RUNS_WINDOW_START` |
| Correction estimator random state | 20260929 | `config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE` |
| Bootstrap resamples | 10,000 | `config.FORECAST_EXPERIMENT_BOOTSTRAP_RESAMPLES` |
| Bootstrap confidence level | 0.95 | `config.FORECAST_EXPERIMENT_BOOTSTRAP_CONFIDENCE` |
| Arm 3 (wind correction) pooling / estimator | pooled (both endpoint cities, one model with an endpoint indicator) / `LinearRegression` | Plan 03-05's validation selector, illustrative synthetic-data run: `LinearRegression+pooled` MAE 22.60 vs. `LinearRegression+per_city` 23.52, `GradientBoostingRegressor+pooled` 30.33, `GradientBoostingRegressor+per_city` 33.29 |
| Arm 4 (cooling correction) target / estimator | log-ratio (scale-free) / `GradientBoostingRegressor` | Plan 03-05's validation selector, illustrative synthetic-data run: `GradientBoostingRegressor+log_ratio` MAE 34.54 vs. `LinearRegression+level` 36.01, `LinearRegression+log_ratio` 37.18, `GradientBoostingRegressor+level` 38.31 |
| Arm 5 estimator | `MLPRegressor` (matching `forecasting_model.md`'s persisted production winner) | `forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]`, refit at `horizon_minutes=1440` |
| Non-fitted-arm validation MAE, AUSTIN_CORPUS_CHRISTI (Plan 03-04 live run) | persistence_24h 156.466, nwp_wind_delta 143.539, raw_forecast 111.075, oracle 12.875 | `03-04-SUMMARY.md` |
| Non-fitted-arm validation MAE, MIDLAND_EL_PASO (Plan 03-04 live run) | persistence_24h 161.162, nwp_wind_delta 161.303, raw_forecast 159.802, oracle 12.256 | `03-04-SUMMARY.md` |

Plan 03-05's pooling/target selections above were measured on representative synthetic data (that
plan's own harness does not fetch real corridor data); per this plan's explicit instruction, those
selections — not a fresh re-selection against real data — are the configurations Plan 03-06 fits
arms 3 and 4 with, since re-selecting after the test split is unlocked would itself be a
configuration decision made with more information available than the no-peeking discipline
permits.

## Expectation

Written before any held-out test row is read, and frozen at this commit — the commit that lands
this section is the same commit that unlocks `backend/forecast_experiment.py`'s test split, and
this section is never edited after that unlock (a revised Expectation records nothing).

**Predicted winner: `raw_forecast` (arm 2), with no arm's margin over persistence expected to be
large.** The clearest evidence already in hand, from Plan 03-04's live validation-split run, is
that the full, uncorrected forecast already beats every cheaper non-fitted baseline at
AUSTIN_CORPUS_CHRISTI (raw_forecast MAE 111.075, beating persistence_24h's 156.466 by roughly 45
amps and beating the wind-only correction nwp_wind_delta's 143.539 too) and is roughly tied with
persistence at MIDLAND_EL_PASO (159.802 vs. 161.162, a gap of under 2 amps that is very unlikely to
be distinguishable from zero once a confidence interval is attached). This pattern — the FULL
forecast trajectory beating a wind-only adjustment at both corridors — suggests that whatever skill
this forecast source has at 24 hours comes from its joint temperature/wind/solar picture, not from
wind alone, which lowers my expectation for how much arms 3 and 4 (both of which correct only one
input channel before or after the physics) can add on top of arm 2. I expect arm 3 (wind-corrected)
to land close to arm 2, plausibly a small improvement at AUSTIN_CORPUS_CHRISTI and a small,
possibly negative change at MIDLAND_EL_PASO, and I expect arm 4 (cooling-corrected) to behave
similarly, since it too only touches the convective term.

**The oracle ceiling bounds how much this can matter.** The oracle's measured validation margin
over `raw_forecast` is large in relative terms — about 98 amps at AUSTIN_CORPUS_CHRISTI (88% of
`raw_forecast`'s own error) and about 147 amps at MIDLAND_EL_PASO (92%) — which says a perfect wind
correction has substantial theoretical headroom to close. But the oracle substitutes OBSERVED
FUTURE wind, which no real forecast can supply; the real question is how much of that headroom a
learned correction, working only from the SAME imperfect forecast inputs arm 2 already has, can
actually recover. Given that even the observed-wind-only, non-fitted `nwp_wind_delta` baseline did
not close this gap (it scored worse than `raw_forecast` at both corridors), I do not expect either
fitted correction arm to close more than a modest fraction of the oracle's headroom — my prior is
that a real, learned correction recovers on the order of 10–20 amps at AUSTIN_CORPUS_CHRISTI, not
the 98 amps the oracle bounds.

**Practical significance, stated in amperes.** These corridors' static ratings run from about 1450 A
(EL_PASO) to about 3000 A (CORPUS_CHRISTI, per `config.STATIC_RATINGS`), and Phase 1's own bake-off
treated a margin as substantive only when it beat BOTH statistical baselines outright, not by a
token amount. I judge a margin against persistence as practically meaningful for a dynamic line
rating decision only if it exceeds roughly 30–50 amperes — an order that could plausibly move a
corridor's DLR-vs-static-rating decision in a way an operator would notice — and distinct from
statistical significance: a 10-amp margin could have a confidence interval that excludes zero at
this sample size (roughly 780 validation rows/corridor) without being large enough, on a rating in
the thousands of amps, to justify replacing persistence in production.

**Expectation for arm 5, the refit reference model.** Phase 1 found the production `"ml"` method
(the same `MLPRegressor` family, at a 60-minute horizon) lost to naive persistence on both
corridors. At 24 hours, arm 5's lag features (1, 2, 3, and 6 hours back) are considerably weaker
predictors of a target 24 hours out than they were of a target 60 minutes out — the same
information that helped at 60 minutes is far more stale by the time it needs to predict a full day
ahead. I expect arm 5 to underperform `persistence_24h` by a margin at least as large, proportionally,
as the 60-minute method's loss to naive in Phase 1 (there, the losing gap was roughly 10–15 amps on
corridors with MAE in the 70–90 amp range; at 24 hours, with persistence's own MAE around 150–160
amps, I would not be surprised by a substantially larger absolute gap).

**Commitment to reporting a null result.** If no arm's confidence interval excludes zero in the
beneficial direction — including `raw_forecast`, my predicted winner — this record will say
plainly that nothing beat persistence at the 24-hour lead, per D-02's explicit commitment, rather
than reframing a small or statistically indistinguishable margin as a win. Given 24-hour
persistence's diurnal self-alignment (03-RESEARCH.md Pattern 4) makes it a genuinely strong
baseline rather than the weak one a "longer horizon is easier to beat" intuition would suggest,
I consider this a live possibility, not a formality: I would be more surprised by a large, clearly
distinguishable margin than by a small or null one.

## Measured results

*Plan 03-06's Task 3 pastes the single test-set run's results here, verbatim, after the Expectation
above has been committed and the leakage probe has demonstrated power. Not yet run as of this
commit.*

## Verdict

*Written by Plan 03-07, reading the Measured results above against the Expectation above. Not yet
written.*

## Limitations

*Written by Plan 03-07. Not yet written.*

## Open Questions

*Written by Plan 03-07. Not yet written.*

## References

- `.planning/workstreams/ml-modeling/ROADMAP.md` — Phase 3's entry and its five success criteria.
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-CONTEXT.md`
  — D-01 through D-04, including D-04's full pivot narrative.
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-RESEARCH.md`
  — the live-verified Previous-Runs stitching mechanism (Pattern 2) and the diurnal-persistence-strength
  argument (Pattern 4) this Expectation is built on.
- `docs/data-science/decisions/forecasting_model.md` — Phase 1's 60-minute bake-off, the reason this
  phase exists, and the 9-section record format this document mirrors.
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-01-SUMMARY.md`
  through `03-05-SUMMARY.md` — Waves 1 through 3's build record, including the bit-identity finding
  that forced D-04's pivot and the live validation-split scores this Expectation cites.
- `backend/forecast_experiment.py` — the harness itself: `ALL_ARMS`, `fit_fitted_arms`,
  `leakage_probe`, `paired_bootstrap_margin`, `corridor_experiment_report`.
- `backend/forecast_correction_models.py` — the wind and cooling correction families arms 3 and 4
  consume.
- `backend/forecast_training.py` — `build_training_matrix`'s `horizon_minutes` parameter, arm 5's
  refit seam.
