# Phase 4: Forecast Correction Follow-up Audit - Context

**Gathered:** 2026-09-30 (via chat discussion following Phase 3's completion — the user reviewed
`docs/data-science/decisions/forecast_correction_experiment.md` and identified specific gaps and
overstated claims; captured here verbatim as the phase's locked scope, not re-derived)
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase is an **adversarial, independent audit** of Phase 3's already-completed and already-
verified decision record. It does **not**:
- Re-run or re-score the original held-out test set (that data is now "already seen" — any new
  analysis on it would be a second selection-on-test-set decision, exactly the failure mode this
  phase exists to check for).
- Replace the production forecasting model or wire any winner into `ampacity_forecast.py`.
- Touch any of Phase 3's frozen artifacts (`03-01` through `03-07` PLAN/SUMMARY files,
  `03-VERIFICATION.md`, the decision record's already-written Expectation/Measured-results sections)
  except to append corrected/clarified language where Section 4 below requires it.

It **does**:
- Independently re-verify data provenance and leakage claims against the actual code (not the
  report's self-description).
- Strengthen the statistical comparison (block-bootstrap accounting for temporal dependence, direct
  pairwise comparisons between fitted candidates, RMSE alongside MAE).
- Add a genuinely new analysis axis Phase 3 did not attempt: conservative-rating/overrating
  frequency and calibrated lower-ampacity quantiles.
- Correct any overstated or imprecise language in the existing decision record.
- Produce a concrete, scoped plan for an eventual integration phase (not build it).

**Any new empirical work in this phase uses a genuinely fresh basis** — a reserved chronological
period not used in Phase 3's train/val/test split, or synthetic/ablation analysis — never the frozen
test rows. Where the plan needs a fresh chronological holdout for calibration/confirmation, it must
define that period's boundaries explicitly and verify no overlap with Phase 3's test split.

</domain>

<decisions>
## Implementation Decisions (user's audit brief, verbatim scope — five sections)

### D-01: Audit data provenance and leakage (independently re-verify, do not trust the report)

- Identify the exact Archive API model/product used for "truth" in Phase 3 (`archive-api.open-meteo.com`,
  ERA5/ERA5-Land reanalysis per `open_meteo_provider.py`'s docstring — confirm this is still accurate
  by reading the actual code, not assuming from memory). Distinguish this reanalysis/analysis-derived
  ampacity from any local observational validation (there is none in Phase 3 — the entire "truth" side
  is itself a physics-model output from reanalysis weather, not sensor-measured; confirm this is
  stated plainly in the decision record, and flag it as a real limitation if it is not).
- Verify forecast availability at **decision time**, not merely initialization-to-valid-time lead.
  Phase 3's calibration gate (`forecast_leadtime_calibration.py`) measured lead time via
  bulk-vs-single-run bit-matching — audit whether this actually proves the forecast was *available*
  at the claimed decision point (T-24h), or only that the *value* matches a run that happens to have
  that nominal lead. Document the limited historical coverage of the stitching-calibration method
  (Single-Runs archive depth, per `03-01-BOUNDARY-INVESTIGATION.md` and `03-RESEARCH.md`) as an
  explicit scope limitation.
- Check **every feature** against decision time — not just truth at/after valid time. The existing
  leakage probe (`forecast_experiment.leakage_probe`, Plan 03-06) sabotages `truth_*` columns and
  checks arms don't read them; audit whether it also catches leakage in the window *between* decision
  time and valid time (e.g., a feature that uses information only available partway through that
  window, not strictly at decision time).
- Check preprocessing, interpolation, shifted targets, and split boundaries. Training labels used to
  fit arms 3/4/5 must be available *before* the evaluated forecast decisions they're being compared
  against — audit `_stacked_pair_frame`, `build_training_matrix`'s `horizon_minutes` shift, and
  `experiment_splits.calendar_split`'s boundary handling directly in code.
- Verify hourly lag features (arm 5's reference-model lags) retain their intended time offsets after
  the six-hourly (`hour % 6`) filtering — audit that a lag computed pre-filter still means what it
  claims to mean post-filter, not a filter-introduced multi-of-6-hour drift.

### D-02: Strengthen the comparison

- Where saved predictions exist (check what Phase 3 actually persisted — the git-ignored JSON reports
  per the established "not the artifact of record" convention, or per-row prediction arrays), compute
  paired **block-bootstrap** confidence intervals that account for temporal autocorrelation in hourly
  ampacity series, rather than (or alongside) the i.i.d. paired bootstrap Phase 3 used. Assess
  sensitivity to block length (try more than one block size, report whether conclusions are stable).
  If predictions were not persisted, this constrains scope — document that explicitly rather than
  inventing data.
- Directly compare `ml_cooling_corrected` against `raw_forecast`, `ml_wind_corrected`, and
  `reference_ml_refit_24h` pairwise — not only each candidate's margin over `persistence_24h`. Beating
  persistence does not establish superiority over the other real candidates.
- Report both MAE **and** RMSE for every candidate at both corridors (Phase 3's table has both, but
  the Verdict text emphasizes MAE only) — explicitly note the Midland case where cooling's MAE
  advantage over the refit MLP is tiny (~0.66 A) while the MLP has better RMSE, and discuss what that
  divergence implies (heavier-tailed error distribution for one candidate vs. the other).
- Acknowledge the multiple-comparisons / selection-on-the-test-set problem: six candidates were
  scored once and a winner picked by largest point margin — note explicitly that this is a single
  test-set read used for both discovery and confirmation, and reserve a **fresh chronological
  period** (post-dating Phase 3's test split, or otherwise non-overlapping) to confirm any revised
  or promoted method before it's treated as settled.
- State plainly that Plan 03-05's synthetic-data configuration selection (pooling mode, target
  parameterization, chosen on validation data during development) does not invalidate the real-data
  test — the test itself ran on real corridor data — but also does not establish that those are the
  *optimal* configurations for real data, since the selection process itself used limited/synthetic
  exploration. Recommend real development data for any future re-tuning.

### D-03: Evaluate conservative ratings (genuinely new analysis, not in Phase 3)

- Measure **overrating frequency, magnitude, and duration** — how often, by how much, and for how
  long would each candidate's predicted rating have exceeded the true safe rating, broken out by
  weather regime (explicitly including low-wind conditions, where IEEE-738's convective term is most
  sensitive).
- Develop and evaluate **lower ampacity quantiles** (not just point predictions) using pinball loss
  and calibration checks, with a separate chronological calibration period from whatever period is
  used to evaluate them (no using the same rows to both fit and check calibration).
- Compare candidates and calibrated-quantile baselines at **matched overrating rates** — i.e., "at
  the same acceptable risk level, how much more usable capacity does each candidate retain compared
  to persistence/the static rating" — reporting retained capacity as the headline comparison metric
  for this section.
- Explicitly scope any reliability claim to the verification data actually used: reanalysis-derived
  "truth" calibration does **not** establish conductor-level physical safety — this section measures
  self-consistency against a physics-model simulation, not field-validated safety margins. State this
  limitation prominently wherever an overrating-rate or calibration number is reported.

### D-04: Correct overstated conclusions in the existing decision record

- Describe `ml_cooling_corrected` as the **lowest-observed-24-hour-MAE candidate** in this specific
  test, not an "established" or "unique" statistical winner — the direct-pairwise-comparison work in
  D-02 should inform exactly how strong a claim the corrected language can honestly make.
- Both `ml_cooling_corrected` and `reference_ml_refit_24h` barely clear the 30A practical-significance
  threshold at Midland — state plainly that neither result establishes the *true* improvement exceeds
  30A (only that the point estimate does); the CI's lower bound matters here, not just the point value.
- Treat the future-wind oracle diagnostic as exactly that — a diagnostic bounding one specific
  intervention (wind correction) under an unrealizable input — never as a rigorous universal
  performance ceiling or proof that the measured headroom is actually learnable by any real model.
- When discussing gains attributable to "forecast correction," measure headroom **relative to
  raw_forecast** (the uncorrected baseline within the same forecast-plus-physics family), not relative
  to persistence — persistence is a different comparison axis (temporal extrapolation vs. physics).
- Keep the invalid, bit-identical 1-hour experiment excluded from any primary claim — it remains a
  labeled non-primary curiosity per Phase 3's own D-04 disposition. Reaffirm explicitly: a 24-hour
  result does not, by itself, establish a replacement for the original 60-minute production method
  (`ampacity_forecast.py`'s `"ml"` method) — these are different horizons serving potentially
  different product needs (see D-05's final bullet).
- Distinguish **low-wind sensitivity** (a real, expected physical property of IEEE-738's convective
  term near the natural/forced convection crossover) from **numerical instability** (a code defect).
  Confirm `thermal_model.py`'s natural-convection floor and physical constraints are preserved and
  were never weakened by Phase 3's additive `q_conv_override` extraction — re-verify this directly
  against the code, not just cite Phase 3's own equality-gate claim.

### D-05: Define the next integration phase (a plan, not an implementation)

- Keep `ml_cooling_corrected` and `reference_ml_refit_24h` both as live candidates (not narrowed to
  one) — use ablations to investigate specifically *why* the refit MLP performs as well as it does
  (does it effectively rediscover a cooling-like correction implicitly, or something else).
- Specify the **minimum data contract** the ML track needs from the pipeline/production team before
  any integration: archived forecasts (with issue/init timestamps), initialization/availability/
  valid timestamps distinctly, local observations with their own availability timestamps and quality
  flags, units, sensor location/height, and conductor/span metadata — name each field explicitly, not
  just "more data."
- Identify what the ML track can complete **now** (with existing data/tools) versus what genuinely
  requires that new data contract to exist first — split the audit's own recommendations into these
  two buckets.
- Outline (not build) model packaging, runtime forecast fetching, stale/missing-data handling,
  fallback behavior (mirroring the existing fail-safe philosophy — a bad forecast fetch must degrade
  to a known-safe path, never an optimistic guess), shadow evaluation before cutover, monitoring, and
  rollback.
- Explicitly name and leave open the product question this audit cannot answer on its own: does the
  intended product need 60-minute forecasting, 24-hour forecasting, or both? Do not recommend
  integration of the 24-hour winner as a blanket replacement for the 60-minute production method
  without this being answered — flag it as a decision for whoever owns that product scope.

</decisions>

<execution_notes>
## Notes for the planner/researcher

- **Inspect the actual implementation and artifacts — do not accept `forecast_correction_experiment.md`'s
  claims at face value anywhere in this phase.** This is the audit's entire premise; a plan that reads
  the report and summarizes it without independently checking code/git history/data has not done the
  job.
- **Complete what's feasible; document what isn't, honestly.** If saved per-row predictions don't
  exist for block-bootstrap analysis, or if a fresh chronological holdout would be too short to be
  meaningful, or if some claim can't be checked without data this project doesn't have — say so
  explicitly rather than inventing evidence or silently skipping the item.
- **This phase's own final deliverable should include:** a concise corrected verdict (does cooling
  correction or the refit MLP warrant integration, with what confidence and caveats), a list of
  completed audit findings/changes, remaining blockers, and a prioritized next-step plan — mirroring
  the structure the user asked for.
- **Reuse Phase 3's established conventions** where they fit: the `docs/data-science/decisions/`
  9-section ADR format (this phase likely produces a sibling or amendment document, planner's call),
  the git-ignored-JSON-not-the-artifact-of-record convention, the no-peeking discipline if any new
  fresh-holdout confirmation step is added.
- **This phase is research-heavy and audit-heavy, not build-heavy** — expect a research pass to
  matter more than usual here (verifying exact data provenance, checking what was/wasn't persisted
  from Phase 3's runs, understanding scipy's block-bootstrap options) before planning tasks.

</execution_notes>

## References

- `docs/data-science/decisions/forecast_correction_experiment.md` — the document under audit (frozen,
  not to be rewritten wholesale — only corrected/amended per D-04)
- `.planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/`
  — all Phase 3 artifacts (03-01 through 03-07 PLAN/SUMMARY, 03-CONTEXT, 03-RESEARCH, 03-VALIDATION,
  03-VERIFICATION, 03-01-BOUNDARY-INVESTIGATION)
- `backend/forecast_experiment.py`, `backend/forecast_leadtime_calibration.py`,
  `backend/forecast_correction_models.py`, `backend/open_meteo_forecast_provider.py`,
  `backend/thermal_model.py`, `backend/forecast_training.py`, `backend/config.py` — the code under audit
