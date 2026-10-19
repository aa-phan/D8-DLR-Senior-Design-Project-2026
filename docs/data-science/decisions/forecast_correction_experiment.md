> **Frozen corridor-era record.** This document records the completed corridor-based forecast-correction experiment (corridor-era, retired 2026-10-12 as an operating model). It is frozen and is not rewritten for the per-city model; the code that reproduces it uses `backend/legacy_corridor.py` and `config.LEGACY_CORRIDOR_ENDPOINTS`. See [`point_scope.md`](point_scope.md).

# Ampacity Forecast Correction Experiment — 24-Hour Primary Comparison

**Status:** Complete — all nine sections below are finalized. The Expectation section was written
and frozen before the held-out test set was read; `git log` on this file, not a self-reported date,
is the audit trail proving that (see the isolated two-file commit, `4d964cf`, that landed the
Expectation and unlocked the test split in the same commit). Measured results, Verdict,
Limitations, and Open Questions were all written only after that commit, per this workstream's
no-peeking discipline.

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

Transcribed verbatim from the SINGLE held-out test-set invocation (`PYTHONPATH=backend
.venv/bin/python3 backend/forecast_experiment.py --lead-hours 24 --split test`), run once, both
corridors, after the Expectation above was committed (`4d964cf`) and the leakage probe had
demonstrated power (`2ad9971`). No arm, feature, hyperparameter, or filter was adjusted after
seeing this output — the plan's checkpoint was approved by explicit human authorization, and this
is the record's one honest read of the test split. Every margin below is `mean(|persistence_24h's
error|) - mean(|arm's error|)` on the byte-identical 786-row test index; positive means the arm's
mean absolute error is lower than persistence's. The 95% interval is a paired bootstrap on the
per-row absolute-error difference series (`scipy.stats.bootstrap`, `BCa`, 10,000 resamples, fixed
seed `config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE`) — "excludes zero" means the ENTIRE
interval favors the arm, i.e. the margin is statistically distinguishable from noise at this
sample size, which is a distinct claim from the amperes-scale practical-significance threshold the
Expectation above committed to before this number was seen.

**AUSTIN_CORPUS_CHRISTI** (23,592 assembled rows; 786 rows scored; window 2024-01-20 →
2026-09-29; test split starts 2026-03-17)

| Candidate | MAE (A) | RMSE (A) | Rows | Margin vs. persistence (A) | 95% CI (paired bootstrap) | Excludes zero favorably? |
|---|---|---|---|---|---|---|
| persistence_24h (baseline) | 108.665 | 144.295 | 786 | — (reference) | — | — |
| nwp_wind_delta | 120.269 | 164.937 | 786 | -11.604 | [-18.906, -4.408] | No — worse than persistence, and distinguishably so |
| raw_forecast | 98.856 | 135.293 | 786 | 9.809 | [1.923, 17.500] | Yes |
| ml_wind_corrected | 94.024 | 127.544 | 786 | 14.641 | [7.696, 21.420] | Yes |
| **ml_cooling_corrected** | **83.803** | **114.164** | 786 | **24.862** | **[18.771, 30.776]** | **Yes — largest margin** |
| reference_ml_refit_24h | 90.847 | 118.608 | 786 | 17.818 | [11.905, 23.614] | Yes |

Resolved verdict field (machine-computed from the intervals above, not this record's own Verdict
section below): *"multiple candidates beat persistence (ml_cooling_corrected (24.862),
reference_ml_refit_24h (17.818), ml_wind_corrected (14.641), raw_forecast (9.809)); resolved to
'ml_cooling_corrected' by largest point margin (24.862)"*.

Truth-group corridor bottleneck: AUSTIN 629 rows / CORPUS_CHRISTI 157 rows. Arm 1's
(`nwp_wind_delta`) physical zero-floor clamp hit 37 of 786 rows.

> **oracle_observed_future_wind — NON-FORECAST DIAGNOSTIC, never a candidate.** MAE 16.035, RMSE
> 24.395, rows 786, margin vs. persistence 92.630 A (95% CI [86.235, 99.283], excludes zero). This
> substitutes OBSERVED FUTURE wind into the forecast's thermal inputs — no real forecast could ever
> have had this input. It bounds the maximum benefit any wind correction could ever achieve; it is
> never compared against persistence or any candidate as though it were an achievable method.

**MIDLAND_EL_PASO** (23,592 assembled rows; 786 rows scored; window 2024-01-20 → 2026-09-29;
test split starts 2026-03-17)

| Candidate | MAE (A) | RMSE (A) | Rows | Margin vs. persistence (A) | 95% CI (paired bootstrap) | Excludes zero favorably? |
|---|---|---|---|---|---|---|
| persistence_24h (baseline) | 163.535 | 206.285 | 786 | — (reference) | — | — |
| nwp_wind_delta | 188.613 | 237.038 | 786 | -25.078 | [-36.364, -13.861] | No — worse than persistence, and distinguishably so |
| raw_forecast | 163.125 | 211.820 | 786 | 0.410 | [-11.058, 11.834] | No — statistically indistinguishable from zero |
| ml_wind_corrected | 142.207 | 184.719 | 786 | 21.328 | [10.898, 31.466] | Yes |
| **ml_cooling_corrected** | **132.865** | **170.869** | 786 | **30.671** | **[22.347, 39.107]** | **Yes — largest margin** |
| reference_ml_refit_24h | 133.525 | 166.668 | 786 | 30.010 | [22.343, 37.984] | Yes |

Resolved verdict field: *"multiple candidates beat persistence (ml_cooling_corrected (30.671),
reference_ml_refit_24h (30.010), ml_wind_corrected (21.328)); resolved to 'ml_cooling_corrected' by
largest point margin (30.671)"*.

Truth-group corridor bottleneck: MIDLAND 91 rows / EL_PASO 695 rows. Arm 1's (`nwp_wind_delta`)
physical zero-floor clamp hit 93 of 786 rows.

> **oracle_observed_future_wind — NON-FORECAST DIAGNOSTIC, never a candidate.** MAE 17.700, RMSE
> 25.661, rows 786, margin vs. persistence 145.835 A (95% CI [137.270, 154.905], excludes zero).
> This substitutes OBSERVED FUTURE wind into the forecast's thermal inputs — no real forecast could
> ever have had this input. It bounds the maximum benefit any wind correction could ever achieve;
> it is never compared against persistence or any candidate as though it were an achievable method.

**24-HOUR LEAD AND STRONG-BASELINE QUALIFIERS (apply to every table above, per
`PRIMARY_24H_LEAD_CAVEAT`, emitted verbatim on this run's report and printed summary):**

> PRIMARY 24-HOUR LEAD (D-04): this lead is exactly 24.0 hours ONLY because the scored rows are
> filtered to the six-hourly cycle hours (hour % 6 == 0) — verified against the Single-Runs product
> (`forecast_leadtime_calibration.assert_exact_offset_lead`), NOT taken from Open-Meteo's or D-04's
> own "exact by construction, no calibration gate needed" framing, which is contradicted by direct
> measurement for the other 5 of every 6 hours (25-29h lead). A 24-hour persistence baseline is
> DIURNALLY SELF-ALIGNED and is therefore a genuinely STRONG day-ago-same-hour baseline, not the
> weak one a "longer horizon is easier to beat" intuition would suggest (03-RESEARCH.md Pattern 4)
> — do not expect the correction arms to beat it as easily as that intuition implies. This is the
> phase's PRIMARY comparison (D-04); the 1-hour arm is a labelled non-primary curiosity whose
> raw-forecast score is an artifact of a bit-identical data source, never a competing candidate
> against this arm's result.

**Test set scored once.** No re-run was necessary: the single invocation above produced finite,
physically plausible numbers for both corridors on the first attempt (no exception, no empty
split, no negative ampacity), so no defect fix was required and the "same-run" rule (a second run
is permitted only to reproduce an identical number after a non-scoring code change) was never
invoked.

## Verdict

> **Phase 4 follow-up note.** Every claim in this section is qualified by the appended
> "Follow-up Audit Amendment (Phase 4, D-04)" section near the end of this document, and by the
> corrected verdict in `docs/data-science/decisions/forecast_correction_followup_audit.md`
> (Plan 04-05) — read both before treating any sentence below as the final word.

**`ml_cooling_corrected` wins on the held-out test set at both corridors** — it carries the largest
statistically-distinguishable margin over `persistence_24h` of any candidate, at AUSTIN_CORPUS_CHRISTI
(+24.862 A, 95% CI [18.771, 30.776]) and at MIDLAND_EL_PASO (+30.671 A, 95% CI [22.347, 39.107]).
This is not the answer the Expectation predicted, and this record says so plainly rather than
reframing the prediction after the fact.

**Where the Expectation was wrong, and why.** The Expectation named `raw_forecast` as the predicted
winner, reasoning that the full forecast trajectory already beat every cheaper non-fitted baseline
on the validation split and that a wind-only correction (arms 3/4, each touching only one input
channel) would therefore add little on top of it. The measurement falsifies that specific
prediction: `raw_forecast`'s own margin over persistence was small at AUSTIN_CORPUS_CHRISTI
(+9.809 A) and, at MIDLAND_EL_PASO, statistically indistinguishable from zero (+0.410 A, 95% CI
[-11.058, 11.834]) — not a winner at either corridor. Both fitted correction arms beat
`raw_forecast`'s own margin by a wide amount instead of landing close to it: `ml_wind_corrected`
added roughly 5–21 amps of margin beyond `raw_forecast`'s own edge over persistence at the two
corridors, and `ml_cooling_corrected` added roughly 15–30 amps beyond it. The reasoning error was
assuming that because the full forecast trajectory already outperformed a wind-only *cheap,
non-fitted* baseline (`nwp_wind_delta`) on the validation split, a *fitted* correction of a single
channel would add little on top of it — that validation-split evidence about a non-fitted baseline
did not generalize to what a fitted correction, trained specifically to reduce residual error,
could recover on held-out rows.

**Where the Expectation was also wrong, more decisively: arm 5.** The Expectation predicted
`reference_ml_refit_24h` would underperform persistence by a margin at least as large,
proportionally, as Phase 1's 60-minute loss to naive persistence (`forecasting_model.md`), reasoning
that the same lag features (1, 2, 3, and 6 hours back) are far staler predictors of a target 24
hours out than of a target 60 minutes out. Instead, `reference_ml_refit_24h` beat persistence
distinguishably at both corridors (+17.818 A AUSTIN_CORPUS_CHRISTI, +30.010 A MIDLAND_EL_PASO) — a
reversal of the reasoning, not just the number. The most likely explanation, though this phase's
design does not isolate it directly and a future ablation would be needed to confirm it: at 24
hours, the model's non-lag weather covariates (air temperature, wind speed, solar radiation,
hour-of-day) carry meaningful predictive signal over a genuinely different physical horizon than the
single last-observed value alone can access, even though the lag features specifically are far
staler at this horizon than at 60 minutes. Persistence's own diurnal strength (see Limitations) does
not eliminate that signal; it only raises the bar the model has to clear, which here it did.

**Statistical distinguishability is not the same claim as practical significance.** The Expectation
committed, before any test row was read, to a roughly 30–50 ampere threshold for a margin to be
practically meaningful for a dynamic line rating decision — a distinct claim from a confidence
interval merely excluding zero on a rating in the thousands of amps. Measured against that
threshold: `ml_cooling_corrected`'s margin clears it at MIDLAND_EL_PASO (30.671 A, at the bottom
edge of the stated range) but falls short at AUSTIN_CORPUS_CHRISTI (24.862 A, below the 30 A floor).
`reference_ml_refit_24h` clears it at MIDLAND_EL_PASO (30.010 A) but not at AUSTIN_CORPUS_CHRISTI
(17.818 A). `ml_wind_corrected` clears it nowhere (14.641 A / 21.328 A). `raw_forecast` clears it
nowhere and is not even statistically distinguishable from zero at one corridor. In amperes-scale
terms: every candidate reported above with an excluding confidence interval has won a measurement,
but only `ml_cooling_corrected` has won anything resembling the practical argument the Expectation
set out to require, and only at one of the two corridors.

**The oracle's margin is a bound, not an achieved result, and real headroom remains unclaimed.** The
oracle — which substitutes observed future wind no real forecast can supply — beat persistence by
92.630 A at AUSTIN_CORPUS_CHRISTI and 145.835 A at MIDLAND_EL_PASO. `ml_cooling_corrected`, the
winning real candidate, recovered only about 26.8% of that headroom at AUSTIN_CORPUS_CHRISTI
(24.862 / 92.630) and about 21.0% at MIDLAND_EL_PASO (30.671 / 145.835). The gap between what a
real, forecast-input-only correction achieved and what a perfect wind correction could achieve is
large at both corridors — this is a modelling gap, not evidence that the ceiling itself is too small
to matter. Substantial room remains for a better wind (or joint wind-plus-thermal) correction to
close, and nothing in this measurement suggests that room is unreachable in principle.

**Recommendation for `ampacity_forecast`'s shipped method.** `ml_cooling_corrected` is the
strongest evidence-based candidate to replace the current `"ml"` method's underlying approach for a
24-hour-ahead correction, given the largest and most consistent margin of the four fitted/raw arms
across both corridors — but the margin's modest size relative to the Expectation's own practical
threshold, its failure to clear that threshold at one of two corridors, and the still-unexplained
mechanism behind arm 5's reversal from Phase 1's result all argue for further evaluation, not an
immediate swap. Implementing any of this phase's candidates into
`ampacity_forecast.FORECAST_METHODS` is explicitly out of scope for this phase (`03-CONTEXT.md`
Phase Boundary) and belongs to a future phase that must also decide runtime forecast-fetch fallback
behavior — what `ampacity_forecast` does when the forecast provider it would newly depend on is
unavailable, a question this experiment's offline harness never had to answer.

## Legacy 1-Hour Arm — A Non-Primary Curiosity, Not a Competing Candidate

This section reports Wave 1's original, idealized-lead result honestly, but it is **not part of the
primary verdict above** and must never be quoted without the finding immediately below travelling
with it: the bulk forecast product this arm depends on was found to be **bit-identical to the
reanalysis truth archive** for every hour tested, across three cities and nine-plus dates —
confirmed independently via raw, wrapper-free HTTP requests that bypass every line of this
repository's own code, ruling out a code-level bug in either provider adapter (full evidence in
`03-01-SUMMARY.md`'s Critical Finding). A forecast that is empirically identical to the eventual
observation cannot be scored for forecast skill; any near-zero error it produces demonstrates a
property of that data source at that lead, not predictive accuracy.

**What Wave 1 built and measured.** Plan 03-01 built a real, working, tested pipeline around
Open-Meteo's Historical Forecast bulk API (`models=ecmwf_ifs`), gated by an empirical lead-time
calibration step (`forecast_leadtime_calibration.py`) that measured — rather than assumed — the
bulk product's effective lead and filtered to the subset (`hour % 6 == 1`) carrying an exact,
verified 1-hour lead. Scored against persistence for AUSTIN over 145 held-out test rows (window
2025-10-01 through 2026-03-31), the result was: persistence 54.985 MAE, and `raw_forecast` an exact
**0.000 MAE / 0.000 RMSE**. This is the number the bit-identity caveat above exists to precede — it
is not evidence of a genuinely skillful 1-hour-lead forecast; it is the signature of a forecast
source that, at this lead and for the necessarily-recent window the calibration gate required, is
not distinguishable from the truth it is meant to predict.

**Disposition.** D-04 (`03-CONTEXT.md`) explicitly retains this arm's code rather than deleting it,
because it is working, fully tested (the calibration gate, the anchored-pair-frame contract, and the
tracer scoring itself all remain green in the current test suite), and documents a real, reusable
negative finding about this specific data source at this specific lead that a future reader building
on Open-Meteo's Historical Forecast bulk API would otherwise have to rediscover through the same
live-network investigation this phase already did. It is excluded from this record's primary verdict
for exactly the reason stated above, and it must remain excluded from any future comparison unless a
genuinely independent forecast/truth pair can be established at a 1-hour lead for this data source —
which, per `03-CONTEXT.md`'s own resolution, may not exist.

## Limitations

- **The exact-lead filter's cost.** The full assembled Previous-Runs window carries 23,592 hourly
  rows per city before any filter. Filtering to the exact-24-hour-lead subset (`hour % 6 == 0`)
  leaves roughly 3,932 scored rows per city over the full window — after the three-way calendar
  split, 786 rows per corridor in the held-out test set scored above. The unfiltered series would
  have offered roughly six times the row volume, but at the cost of silently blending five distinct
  lead times (24 through 29 hours) into one number (`03-RESEARCH.md` Pattern 2, Pitfall 1) — no
  honest point claim of "the 24-hour lead" could be made from that blend. The filter was chosen
  anyway, trading statistical power for a claim this record can actually defend.
- **The stitching verification's reach is bounded, and the gap is not directly closed.** The
  cross-check proving the `24 + (hour % 6)` stitching rule against the exact Single-Runs product
  could only be run over a handful of recent dates, because the Single-Runs archive for the pinned
  `gfs_seamless` model reaches back only to roughly mid-2026 — it cannot reach the bulk of this
  experiment's own window, which starts 2024-01-20. The rule's applicability to 2024 and 2025 dates
  therefore rests on the stitching mechanism being general to any six-hourly NWP product's
  bulk/previous-runs construction, not on a direct historical cross-check against those years
  (`03-RESEARCH.md` Assumption B2). This is an open exposure, not a verified fact, and it is recorded
  here rather than folded into the confident "measured, not assumed" framing the rest of this record
  uses.
- **24-hour persistence is a strong baseline, not a weak one — do not read the margins above with
  the opposite intuition.** Twenty-four hours is exactly one full diurnal cycle, so
  `persistence_24h` is a genuine day-ago-same-hour ("seasonal-naive") baseline, similar in kind to
  time-series practice's own strong baseline for diurnally-cyclic series, not the weak baseline a
  "longer horizon is easier to beat" intuition would suggest (`03-RESEARCH.md` Pattern 4). Every
  margin reported in the Verdict above was measured against that strong baseline, not a weak one —
  the modest size of even the winning margin is consistent with, not contradictory to, that framing.
- **The oracle bounds the ceiling; it does not certify that the ceiling is reachable.** The oracle's
  margin over persistence (92.630 A AUSTIN_CORPUS_CHRISTI, 145.835 A MIDLAND_EL_PASO) is the maximum
  any wind correction could ever recover, because it substitutes observed future wind no real
  forecast can supply. No real candidate came close to it (the best, `ml_cooling_corrected`,
  recovered roughly a quarter of it at each corridor) — this bounds the size of the opportunity but
  says nothing about whether a better model, more data, or a different correction target could
  actually close more of that gap; this record does not claim it could.
- **Two endpoint cities per corridor, two corridors, one conductor configuration, one NWP model.** As
  in Phase 1's own bottleneck proxy (`forecasting_model.md` Limitations), the corridor-level target
  and every arm's own prediction reduce two endpoint cities' computed ampacity via the weakest-link
  convention — a proxy for the true multi-point bottleneck a richer corridor-discretization dataset
  would eventually measure. Both corridors share an identical `ConductorConfig` (795 kcmil Drake
  ACSR) except for bearing, and both share an identical elevation (900.0 m, no per-corridor split
  implemented). Every forecast arm in the primary comparison is built from exactly one pinned NWP
  model (`gfs_seamless`); nothing in this record generalizes to a different model, a different
  conductor, or a third corridor.
- **The leakage probe's coverage is partial by design.** `leakage_probe` detects a direct read of a
  truth-column value at or after the valid time being predicted — it does not, and was never
  designed to, detect a leak through a model that was trained on rows inside the test window. That
  second failure mode is covered instead by arm 5's from-scratch refit on train-plus-validation rows
  only (never the persisted production artifact, never touching its process-global cache) and by the
  explicit split-disjointness assertion on the filtered frame actually scored. A reader relying on
  the leakage probe alone to certify the absence of test-set contamination would be trusting it for a
  guarantee it does not provide.
- **The test set was scored exactly once, with no defect-forced re-run.** Plan 03-06's own transcript
  confirms the single invocation (`--lead-hours 24 --split test`, both corridors) produced finite,
  physically plausible numbers on the first attempt — no exception, no empty split, no negative
  ampacity — so the "same-run" exception (a second run permitted only to reproduce an identical
  number after a non-scoring code change) was never invoked, and no arm, feature, hyperparameter, or
  filter was adjusted after seeing this record's Measured results.

## Open Questions

- **Probabilistic and quantile evaluation of the winning correction.** This record scores mean
  absolute error alone; it says nothing about calibrated confidence bounds around a corrected
  forecast. Worth doing if `ml_cooling_corrected` (or any correction arm) is ever considered for
  production wiring, since a dynamic line rating decision needs a defensible uncertainty band, not
  just a point estimate — deferred here per `03-CONTEXT.md`'s Phase Boundary.
- **Regime-specific correction models.** `raw_forecast`'s own margin was real at
  AUSTIN_CORPUS_CHRISTI but statistically indistinguishable from zero at MIDLAND_EL_PASO, and the
  winning correction's margin similarly varies by corridor. Worth investigating whether that
  variation tracks a specific weather regime (frontal passage, wind regime, season) rather than a
  corridor-level property, since a regime-conditional correction could plausibly recover more of the
  oracle's headroom than a single corridor-wide model — deferred here as originally scoped.
- **Multi-source NWP fusion.** Every arm in the primary comparison depends on exactly one pinned
  model (`gfs_seamless`). Worth doing if a second independent NWP source becomes available, since
  this record cannot distinguish "this correction generalizes to real forecast error" from "this
  correction is tuned to `gfs_seamless`'s particular error signature" — deferred here as originally
  scoped.
- **Production wiring, and the runtime forecast-fetch fallback decision it requires.** Explicitly out
  of scope for this phase. Worth pursuing given that a real, distinguishable (if modest) margin now
  exists at one corridor for at least two candidates — but any such phase must also decide what
  `ampacity_forecast` does when the forecast provider it would newly depend on is unavailable, a
  question this offline experiment harness never had to answer.
- **Why did the reference `"ml"` model reverse from a loss at 60 minutes (Phase 1) to a win at 24
  hours?** Newly raised by this measurement, not anticipated by the Expectation. The Verdict above
  offers a plausible but unconfirmed explanation (non-lag weather covariates carrying more signal
  over a longer, physically distinct horizon); a feature-ablation study isolating the lag features
  from the weather covariates would be needed to confirm it, and would inform whether the same
  architecture is worth retrying at other horizons.
- **Would accepting the broader, unfiltered 24–29-hour lead range (trading a point claim for roughly
  six times the row volume, with an explicit range caveat per `03-RESEARCH.md` Pitfall 1) change
  which margins are statistically distinguishable?** Not attempted in this phase, since the
  Expectation and this record's own no-peeking discipline committed to the exact-lead filter before
  any test row was read. A future sensitivity pass could re-run the same seven arms against the wider
  window to see whether the added statistical power changes any of this record's borderline calls
  (`ml_wind_corrected`'s and `reference_ml_refit_24h`'s margins at AUSTIN_CORPUS_CHRISTI, both
  currently below the practical threshold).

## Follow-up Audit Amendment (Phase 4, D-04) — Additive, Six Corrections

This section is a Phase 4 follow-up amendment: it is purely additive, and every sentence above it
in this document is unedited. The `## Expectation` and `## Measured results` sections remain
byte-identical to their committed versions, proven by `EXPECTATION_AND_MEASURED_BYTE_IDENTICAL_OK`
(extracting both sections from the committed file and comparing them byte-for-byte), and every line
of the committed file still appears, in order, below — proven by `FROZEN_RECORD_APPEND_ONLY_OK`. The
six subsections below correct or qualify the Verdict's own language, one per D-04 item
(`04-CONTEXT.md`), each quoting the sentence it qualifies before stating the correction.

### 1. Lowest observed MAE, not an established winner

**Original wording, quoted from the Verdict above:** "**`ml_cooling_corrected` wins on the
held-out test set at both corridors** — it carries the largest statistically-distinguishable margin
over `persistence_24h` of any candidate, at AUSTIN_CORPUS_CHRISTI (+24.862 A, 95% CI
[18.771, 30.776]) and at MIDLAND_EL_PASO (+30.671 A, 95% CI [22.347, 39.107])."

**What is wrong with it.** "Wins" and a bare statement of the largest margin over persistence reads
as an established, unique statistical victory. It is not: six candidates were scored once on one
held-out chronological split, at one verified 24-hour lead, under one pinned weather model
(`gfs_seamless`), and a winner was picked by largest point margin over persistence — a single read
used for both discovery and confirmation, the exact conflation Plan 04-03's `## Strengthened
comparison (D-02)` section names as a multiple-comparisons problem. Beating persistence is also not
the same claim as beating the other real candidates: the frozen record above never computes a
direct pairwise margin between `ml_cooling_corrected` and `reference_ml_refit_24h` — only each
candidate's own margin over persistence (24.862 vs. 30.010 at the two corridors). Plan 04-05's own
D-02 replication computed that pairwise margin directly, on a real (ABLATION-basis) out-of-sample
split: at MIDLAND_EL_PASO, cooling's margin over the refit model is 3.308 A, 95% CI
[-2.667, 9.055] — not distinguishable from zero. A candidate whose margin over its closest real
competitor is statistically indistinguishable from zero at one of two corridors is not an
established winner over that competitor, whatever its margin over persistence says.

**Corrected wording.** `ml_cooling_corrected` had the lowest-observed-24-hour-MAE candidate among
the six scored in this one test, on one held-out chronological split, at one verified lead, under
one pinned weather model, selected by largest point margin over persistence from six candidates
scored once. It is not an established, unique, or proven statistical winner over the other real
candidates: its own margin over `reference_ml_refit_24h` — never computed directly in this record's
own Measured results above — was found, in Plan 04-05's direct pairwise replication, to be
statistically indistinguishable from zero at MIDLAND_EL_PASO (3.308 A, 95% CI [-2.667, 9.055]), the
corridor where this record's practical-significance claim for cooling is also weakest (see item 2
below).

### 2. The practical threshold is a claim about the interval's lower bound

**Original wording, quoted from the Verdict above:** "Measured against that threshold:
`ml_cooling_corrected`'s margin clears it at MIDLAND_EL_PASO (30.671 A, at the bottom edge of the
stated range) but falls short at AUSTIN_CORPUS_CHRISTI (24.862 A, below the 30 A floor).
`reference_ml_refit_24h` clears it at MIDLAND_EL_PASO (30.010 A) but not at AUSTIN_CORPUS_CHRISTI
(17.818 A)."

**What is wrong with it.** "Clears it" states a point estimate crossing 30 A as though that settled
the practical-significance question the Expectation committed to before the test split was read.
It did not: at MIDLAND_EL_PASO, `ml_cooling_corrected`'s own 95% CI is [22.347, 39.107] and
`reference_ml_refit_24h`'s own 95% CI is [22.343, 37.984] — both intervals' lower bounds (22.347 and
22.343) sit well below the 30 A threshold, roughly 8 amperes short of it. The point estimate
clearing the threshold proves only that the point estimate clears it; the interval's lower bound is
the claim that would matter if this number were ever used to justify a production change, and
neither candidate's lower bound clears 30 A at this corridor.

Plan 04-05's own block-length-sensitivity sweep (D-02) measured what this frozen record could not:
whether a block bootstrap, which accounts for the temporal dependence the original i.i.d. paired
bootstrap assumes away, is wider, and whether any margin's favourable exclusion flips under it. One
does: the MIDLAND_EL_PASO `ml_wind_corrected`-vs-`reference_ml_refit_24h` margin excludes zero at
block length 1 (95% CI [0.254, 16.641], the length at which this audit's block bootstrap reduces
exactly to the i.i.d. method) but stops excluding zero at block lengths 4, 8, and 28 (e.g., block
length 28: [-0.675, 18.007]) — and the frozen harness's own original BCa method, applied to this
same margin on the same real data, was already only barely excluding zero before any
autocorrelation correction (CI lower bound 0.036). **This is the strongest sentence in this
amendment:** a margin that would read as a confident, distinguishable win under this record's own
original interval method does not survive a block-length sweep that accounts for serial correlation
in the hourly series it was measured on — the frozen record's intervals are optimistic at
MIDLAND_EL_PASO, not merely imprecise.

**Corrected wording.** Both `ml_cooling_corrected` and `reference_ml_refit_24h`'s point margins sit
at or just above the 30 A practical-significance threshold at MIDLAND_EL_PASO, while both
candidates' 95% confidence intervals' lower bounds (22.347 A and 22.343 A respectively) sit well
below it. Neither result establishes that the true improvement exceeds the threshold — only that
the point estimate does. A related margin at the same corridor (`ml_wind_corrected` vs.
`reference_ml_refit_24h`) that excludes zero under the i.i.d.-equivalent block length no longer
excludes zero once temporal dependence is accounted for at longer block lengths — a caution that
applies with at least equal force to every interval reported in this record's own Measured results
above, none of which has been re-examined under a block bootstrap.

### 3. The oracle is a diagnostic, not a ceiling

**Original wording, quoted from the Verdict above:** "`ml_cooling_corrected`, the winning real
candidate, recovered only about 26.8% of that headroom at AUSTIN_CORPUS_CHRISTI (24.862 / 92.630)
and about 21.0% at MIDLAND_EL_PASO (30.671 / 145.835). The gap between what a real,
forecast-input-only correction achieved and what a perfect wind correction could achieve is large at
both corridors — this is a modelling gap, not evidence that the ceiling itself is too small to
matter. Substantial room remains for a better wind (or joint wind-plus-thermal) correction to close,
and nothing in this measurement suggests that room is unreachable in principle."

**What is wrong with it.** The "recovered-fraction" framing — a candidate recovering 26.8% or 21.0%
of the oracle's margin — invites a reader to treat the oracle's 92.630 A (AUSTIN_CORPUS_CHRISTI) and
145.835 A (MIDLAND_EL_PASO) margins over persistence as a universal performance ceiling that a
sufficiently good model could eventually close in full, and the unrecovered 73–79% as "headroom"
waiting to be claimed by any real model. It is not a ceiling in that sense: the oracle substitutes
OBSERVED FUTURE wind directly into the forecast's thermal inputs, an input no real forecast can ever
supply at decision time. It is a diagnostic that bounds the maximum benefit one specific
intervention — wind correction — could achieve under an unrealizable input; it says nothing about
whether any of that bound is reachable by a real model working only from the same imperfect forecast
inputs every real candidate in this record actually has.

**Corrected wording.** The oracle is a diagnostic, not a universal performance ceiling: it bounds
the maximum benefit any wind correction could ever achieve under an input (observed future wind)
that no real forecast can supply, and it should never be read as proof that the measured headroom —
73.2% at AUSTIN_CORPUS_CHRISTI, 79.0% at MIDLAND_EL_PASO, by the recovered-fraction framing above —
is actually learnable by any real model working from real forecast inputs. The gap between what
`ml_cooling_corrected` achieved (24.862 A / 30.671 A) and what the oracle bounds (92.630 A /
145.835 A) measures the size of one unrealized intervention's theoretical ceiling, not a quantity of
unclaimed, achievable performance.

### 4. Correction headroom is measured against the raw forecast

**Original wording, quoted from the Verdict above:** "Both fitted correction arms beat
`raw_forecast`'s own margin by a wide amount instead of landing close to it: `ml_wind_corrected`
added roughly 5–21 amps of margin beyond `raw_forecast`'s own edge over persistence at the two
corridors, and `ml_cooling_corrected` added roughly 15–30 amps beyond it."

**What is wrong with it.** Every margin this record's Verdict reports (+24.862 A, +30.671 A, and
every other arm's own figure) is measured against `persistence_24h` — temporal extrapolation, the
ampacity 24 hours ago. Persistence is a different comparison axis from `raw_forecast`: persistence
extrapolates the past, while `raw_forecast` and the two correction arms are all members of the same
forecast-plus-physics family, differing only in whether and how the forecast's own weather inputs
are corrected before the physics runs. Measuring correction headroom against persistence (as every
figure in this record's Measured results above does) does not isolate what correction itself
contributed on top of the uncorrected forecast already in hand.

The headroom attributable to correction specifically is the margin against `raw_forecast`, not
against persistence. Computed directly from this record's own Measured results table:
`ml_cooling_corrected`'s margin over `raw_forecast` is 98.856 − 83.803 = 15.053 A at
AUSTIN_CORPUS_CHRISTI and 163.125 − 132.865 = 30.260 A at MIDLAND_EL_PASO — both smaller than the
corresponding persistence-relative margins (24.862 A and 30.671 A). The two axes are not only
conceptually different but numerically different: at MIDLAND_EL_PASO, `raw_forecast`'s own margin
over persistence was itself statistically indistinguishable from zero (+0.410 A, 95% CI
[-11.058, 11.834]), so a reader comparing cooling's persistence-relative margin to raw_forecast's
near-zero persistence-relative margin and inferring "correction added roughly 30 A over the raw
forecast" at that corridor would be wrong by more than double — the correction-relative margin there
is 30.260 A, close by coincidence to the persistence-relative figure of 30.671 A only because
`raw_forecast` itself barely beat persistence at that corridor.

**Corrected wording.** The margin attributable to forecast correction specifically is
`ml_cooling_corrected`'s advantage over `raw_forecast` (the uncorrected member of the same
forecast-plus-physics family), not its advantage over `persistence_24h` (a different comparison
axis — temporal extrapolation, not a physics-informed forecast). Side by side at both corridors:
AUSTIN_CORPUS_CHRISTI — margin vs. persistence +24.862 A, margin vs. raw_forecast +15.053 A;
MIDLAND_EL_PASO — margin vs. persistence +30.671 A, margin vs. raw_forecast +30.260 A. These two
axes are numerically distinct, not merely conceptually distinct: at MIDLAND_EL_PASO,
`raw_forecast`'s own margin over persistence was not statistically distinguishable from zero
(+0.410 A, 95% CI [-11.058, 11.834]), so any gain attributed to "forecast correction" at that
corridor must be read against `raw_forecast`, never against persistence.

### 5. The legacy arm stays excluded, and a 24-hour result is not a sixty-minute replacement

**Original wording, quoted from the "Legacy 1-Hour Arm" section above:** "It is excluded from this
record's primary verdict for exactly the reason stated above, and it must remain excluded from any
future comparison unless a genuinely independent forecast/truth pair can be established at a 1-hour
lead for this data source — which, per `03-CONTEXT.md`'s own resolution, may not exist." And, from
"What was built": "The legacy 1-hour arm is retained in the codebase as a documented, labelled,
non-primary curiosity — its raw-forecast score is an artifact of the bit-identical data source,
never a competing candidate against this record's primary verdict."

**What is wrong with it.** Nothing in the legacy-arm disposition itself is incorrect — it is
reaffirmed, not corrected, below. What this record does not currently say plainly is the converse
claim a reader might otherwise infer: that because the 24-hour correction arms carry a real,
distinguishable (if modest) margin while the legacy 1-hour arm's near-zero MAE is a known artifact
of a bit-identical data source, a 24-hour-lead result somehow supersedes or replaces the production
60-minute method (`ampacity_forecast.py`'s `"ml"` method). It does not: a 24-hour lead and a
60-minute lead are different horizons that may serve different product needs, and this record never
measured the 60-minute horizon with this phase's candidates or data source at all.

**Corrected wording.** The legacy one-hour arm's near-zero score remains excluded from this record's
primary verdict: it is an artifact of a forecast/truth pair that was found empirically bit-identical
for the necessarily-recent window its own calibration gate required, never a competing candidate,
and it must stay excluded from any future comparison unless a genuinely independent 1-hour-lead
forecast/truth pair is established for this data source. Separately and additionally: a 24-hour-lead
result does not, by itself, establish a replacement for the production 60-minute method. These are
different horizons that may serve different product needs, and the question of which horizon (or
both) the product actually requires is named as unresolved in the audit record's own integration
plan (`docs/data-science/decisions/forecast_correction_followup_audit.md`, Plan 04-06).

### 6. Low-wind sensitivity is physics, not numerical instability

**Original wording, quoted from the "What was built" section above (Arm 4's description):** "A
`scikit-learn` estimator that corrects the physics' convective heat-loss term directly, substituted
back through `thermal_model.ieee738_ampacity`'s `q_conv_override` seam."

**What is wrong with it.** Nothing in this sentence is factually incorrect — this item is not a
language overstatement to correct, unlike items 1 through 5 above. This record is simply SILENT on
two questions Plan 04-04's own measurement later raised: whether the sharp concentration of
overrating in the lowest-wind regime (100% of rows below the measured natural-vs-forced convection
crossover, both corridors, per the audit record's `## Conservative-rating analysis (D-03)` section)
is a real physical property of the model or a numerical defect, and whether the `q_conv_override`
seam this sentence names could ever push a corrected convective term below the physical
natural-convection floor. Plan 04-05's Task 1 closes both silences by measurement, from an
independent code path — never by citing this record's or Phase 3's own equality-gate claim for the
seam's bit-identity.

**Measured, corrected wording (an addition, not a correction of overstated prose).** The low-wind
behaviour both corridors' overrating analysis surfaced is a measured property of the physics, not a
numerical instability. The natural-vs-forced convection crossover for both corridors' shared
conductor configuration, at a representative 35.0°C ambient temperature, is 0.1428 m/s. Sweeping
perpendicular wind across a grid bracketing this crossover (`low_wind_sensitivity_sweep`), the
ampacity response is finite and non-negative everywhere on the grid, including at exactly zero wind;
monotone non-decreasing across the whole grid; and continuous across the crossover (a vanishing step
on either side of the crossover produces a vanishing ampacity gap, not a fixed-size jump — exactly
what an elementwise maximum of two continuous expressions produces). Below the crossover, the
response is measured EXACTLY FLAT, not merely small: `convective_heat_loss` returns
`natural_convection`'s own expression unchanged there, and that expression does not contain the wind
variable at all, so the convective term — and therefore the ampacity — cannot respond to wind in
that regime by construction, not by coincidence. The peak sensitivity to wind is located
above the crossover (at roughly ten times the crossover speed in this sweep, not at zero wind),
confirming that the genuinely wind-sensitive regime is the opposite of where a "numerical
instability near zero wind" intuition would place it.

Independently of this sweep, Phase 3's Success-Criterion-4 convective-seam bit-identity claim was
re-verified from this phase's own code path against the committed golden fixture
(`backend/tests/thermal_model_pre_refactor_golden.npz`), never by invoking the existing equality
test itself: the live ampacity and the live convective term both match the stored golden arrays
exactly, the override seam reproduces the default path exactly when passed the unmodified convective
term, and a perturbed override changes the result — proving the equality above is not the trivial
consequence of an ignored parameter. Finally, the sub-floor routing question Plan 04-04's analysis
raised is answered by attempting it rather than by reading the guard code alone: a corrected
convective term that is positive but below the natural-convection floor IS permitted to reach the
physics through the `q_conv_override` seam. `forecast_correction_models.py`'s own
`predict_cooling_correction` guard rejects only a non-positive corrected term
(`backend/forecast_correction_models.py:547`); a positive sub-floor term is not caught by it, and
`ieee738_ampacity`'s override branch substitutes the override directly for the convective term,
bypassing `convective_heat_loss`'s own natural-convection floor entirely when an override is given
(`backend/thermal_model.py:236-239`). This is a real, measured finding about the seam's exposure,
not a theoretical one — it is reported here as a finding for Plan 04-06's integration-readiness plan
to weigh, not as evidence of any defect in the physics itself, which this sweep's own measurements
show is finite, monotone, and continuous throughout.

### 7. Correction to this amendment's own § 4 (append-only — § 4's text above is unedited)

**Dated 2026-10-05, added during a focused fact-check pass on this amendment and on
`forecast_correction_followup_audit.md`.** § 4 above states that a reader inferring "correction added
roughly 30 A over the raw forecast" at MIDLAND_EL_PASO "would be wrong by more than double." That
sentence is itself incorrect, and is corrected here rather than edited in place, per this document's own
append-only discipline.

The two numbers § 4 is comparing are 30.260 A (the correction-relative margin, `raw_forecast` →
`ml_cooling_corrected`) and 30.671 A (the persistence-relative margin for the same arm). These two
numbers differ by 0.411 A — about 1.3% of either value — not by a factor of two. § 4's own very next
clause already says as much: "close by coincidence to the persistence-relative figure of 30.671 A."
A reader who used the persistence-relative figure (30.671 A) as a stand-in for the correction-relative
one (30.260 A) at THIS corridor would be off by under half a percent, not "wrong by more than double."

The "more than double" distortion § 4 is reaching for does occur, but at the OTHER corridor:
AUSTIN_CORPUS_CHRISTI's persistence-relative margin is 24.862 A against a correction-relative margin of
15.053 A — the persistence-relative figure overstates the correction-relative one by a factor of 1.65,
not quite double either, but a much larger distortion than the near-zero one at MIDLAND_EL_PASO. §4's
own general point — that the two axes are numerically distinct, not merely conceptually distinct, and
that a reader must not substitute one for the other — is correct and stands; only the specific "wrong by
more than double" example, and its attachment to MIDLAND_EL_PASO specifically, is withdrawn.

---

For the full measured tables, the block-length sensitivity sweep, the overrating and retained-capacity
analysis, and the integration-readiness plan this amendment's six items feed into, see
`docs/data-science/decisions/forecast_correction_followup_audit.md`.

## References

- `.planning/workstreams/ml-modeling/ROADMAP.md` — Phase 3's entry, its five success criteria, and
  their disposition as executed.
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-CONTEXT.md`
  — D-01 through D-04, including D-04's full pivot narrative and the Phase Boundary/Deferred Ideas
  this record's Open Questions section reads from.
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-RESEARCH.md`
  — the live-verified Previous-Runs stitching mechanism (Pattern 2), the exact-lead filter tradeoff
  (Pitfall 1), the diurnal-persistence-strength argument (Pattern 4), and the stitching-verification
  reach limitation (Assumption B2) this record's Limitations section is built on.
- `docs/data-science/decisions/forecasting_model.md` — Phase 1's 60-minute bake-off (both trained
  candidates lost to naive persistence), the reason this phase exists, and the 9-section record
  format this document mirrors.
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-01-SUMMARY.md`
  through `03-06-SUMMARY.md` — the build record for this phase's plans, including the bit-identity
  finding that forced D-04's pivot (03-01), the in-repo refutation of that finding at a 24-hour lead
  (03-03), the four non-fitted arms and the oracle's isolation (03-04), the two ML correction
  families and the horizon seam (03-05), and the single held-out test-set run this record's Measured
  results and Verdict are built on (03-06).
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/03-01-BOUNDARY-INVESTIGATION.md`
  — the addendum documenting the corrected window-start boundary and the bit-identity finding's
  initial discovery.
- `backend/forecast_experiment.py` — the harness itself: `ALL_ARMS`, `fit_fitted_arms`,
  `leakage_probe`, `paired_bootstrap_margin`, `corridor_experiment_report`.
- `backend/forecast_correction_models.py` — the wind and cooling correction families arms 3 and 4
  consume.
- `backend/forecast_training.py` — `build_training_matrix`'s `horizon_minutes` parameter, arm 5's
  refit seam.
