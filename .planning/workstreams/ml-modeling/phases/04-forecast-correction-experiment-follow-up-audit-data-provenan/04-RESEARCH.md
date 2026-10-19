# Phase 4: Forecast Correction Follow-up Audit - Research

**Researched:** 2026-09-30
**Domain:** Adversarial statistical/data-provenance audit of a frozen ML experiment record (no new
libraries; the domain is auditing existing `backend/forecast_experiment.py` code and
`docs/data-science/decisions/forecast_correction_experiment.md` against ground truth)
**Confidence:** HIGH for code-grounded findings (all claims below cite file:line and were read
directly this session); LOW/ASSUMED only where noted (external methodology best-practice claims)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01 — Audit data provenance and leakage** (independently re-verify, do not trust the report):
identify the exact Archive API truth source and confirm no local observational validation exists;
verify forecast availability at decision time vs. merely init-to-valid lead; check every feature
against decision time; check preprocessing/interpolation/shifted-target/split-boundary code
directly; verify hourly lag features retain intended offsets after the six-hourly filter.

**D-02 — Strengthen the comparison**: where saved predictions exist, compute paired block-bootstrap
CIs with block-length sensitivity (in place of or alongside the i.i.d. bootstrap); if predictions
were not persisted, document that explicitly rather than inventing data. Directly compare
`ml_cooling_corrected` against `raw_forecast`, `ml_wind_corrected`, and `reference_ml_refit_24h`
pairwise, not only each candidate's margin over persistence. Report MAE and RMSE at both corridors
for every candidate, explicitly noting Midland's tiny (~0.66A) cooling-vs-refit MAE gap against a
worse RMSE. Acknowledge the multiple-comparisons/selection-on-test-set problem and reserve a fresh
chronological period (non-overlapping with Phase 3's test split) to confirm any revised method.
State that Plan 03-05's synthetic-data configuration selection doesn't invalidate the real-data test
but doesn't establish optimality either.

**D-03 — Evaluate conservative ratings** (genuinely new analysis): measure overrating
frequency/magnitude/duration by weather regime including low-wind; develop and evaluate lower
ampacity quantiles via pinball loss with a calibration period chronologically separate from the
evaluation period; compare candidates at matched overrating rates, reporting retained capacity as
the headline metric; explicitly scope any reliability claim to the reanalysis-derived verification
data used, not conductor-level physical safety.

**D-04 — Correct overstated conclusions**: describe cooling correction as the
lowest-observed-24-hour-MAE candidate, not an established/unique winner; state plainly that neither
cooling nor the refit MLP establishes the *true* improvement exceeds 30A at Midland (only the point
estimate does — the CI lower bound matters); treat the future-wind oracle as a diagnostic bounding
one intervention, never a universal ceiling; measure "forecast correction" headroom relative to
raw_forecast, not persistence; keep the invalid 1-hour experiment excluded from primary claims and
reaffirm a 24-hour result doesn't establish a 60-minute production replacement; distinguish low-wind
sensitivity (real physics) from numerical instability (code defect), re-verifying
`thermal_model.py`'s natural-convection floor directly against the code.

**D-05 — Define the next integration phase** (a plan, not an implementation): keep both
`ml_cooling_corrected` and `reference_ml_refit_24h` as live candidates; use ablations to investigate
why the refit MLP performs well; specify the minimum data contract needed from the pipeline team
(archived forecasts with issue/init timestamps, availability/valid timestamps, local observations
with their own availability timestamps and quality flags, units, sensor location/height,
conductor/span metadata); split recommendations into "ML track can do now" vs. "needs that data
contract"; outline (not build) packaging/runtime-fetch/fallback/shadow-eval/monitoring/rollback;
explicitly name the 60-minute-vs-24-hour-vs-both product question as unresolved.

### Claude's Discretion

- Whether this phase produces a sibling decision-record document or an amendment to the existing
  `forecast_correction_experiment.md` (both use the same 9-section ADR format either way).
- The specific block length(s) tested for block-bootstrap sensitivity.
- The specific low-ampacity quantile level(s) chosen for D-03 (e.g., 5th/10th percentile).
- Exact boundaries of any fresh chronological holdout, provided non-overlap with Phase 3's
  train/val/test split is verified and stated explicitly.

### Deferred Ideas (OUT OF SCOPE)

- Re-running or re-scoring Phase 3's frozen held-out test set for any purpose.
- Replacing the production forecasting model or wiring any winner into `ampacity_forecast.py`.
- Editing Phase 3's frozen artifacts (03-01 through 03-07 PLAN/SUMMARY, 03-VERIFICATION.md, the
  decision record's Expectation/Measured-results sections) except appending corrected language
  where D-04 requires it.
- Building the D-05 integration plan's packaging/runtime-fetch/monitoring work — only outlining it.
</user_constraints>

<phase_requirements>
## Phase Requirements

No requirement IDs apply to this phase — it is methodology/audit investigation of Phase 3's already
satisfied FCST-01/FCST-02, mirroring Phase 3's own no-new-requirement-ID reasoning
(`.planning/workstreams/ml-modeling/REQUIREMENTS.md` shows FCST-01/FCST-02 already marked Complete
against Phase 1, not this phase). This phase produces an audit record and an integration-readiness
plan, not new production capability.
</phase_requirements>

## Summary

This is a code-audit phase, not a build phase: the "stack" is the same `pandas`/`numpy`/`scipy`/
`scikit-learn` already installed in `.venv` (scipy 1.17.1, numpy 2.4.3, sklearn 1.9.1, pandas
2.3.3 — verified via `import`), and no new package is required for any of D-01 through D-05. The
single most important finding, gating nearly everything in D-02 and D-03, is that **Phase 3
persisted only aggregate scores, never per-row predictions or residuals, and the fitted
wind/cooling/arm-5 models were never saved to disk** — confirmed by reading
`forecast_experiment.py`'s only two disk-write call sites (`merged.to_csv` for the *input* weather
cache, `json.dump(report, ...)` for the aggregate MAE/RMSE/margin report) and its own docstring
stating `fit_fitted_arms` "never calls `persist_corridor_model`." The `data/experiment/` cache
directory that would hold any of this is git-ignored and **does not currently exist on disk** at
all. Block-bootstrap CI analysis and any per-row overrating/quantile analysis on Phase 3's frozen
arms is therefore **not reconstructable from anything already written down** — it requires either
fresh real data or synthetic/ablation data, exactly the two options CONTEXT.md's Domain section
already anticipates, never a re-score of the frozen test rows.

A second load-bearing finding compounds the first: Phase 3's frozen test split runs through
`2026-09-29` (from the decision record's own stated window), and "today" in this research session
is `2026-09-30`. Because every Open-Meteo endpoint this project uses requires the requested day to
be fully past, **a genuinely fresh, non-overlapping calendar period for the three fitted arms
(`ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`) contains at most ~0-1 usable
days of real data right now** — and the validation split cannot substitute, because it was part of
the frame those three arms were fit on (`train_val_stacked = concat(stacked_train, stacked_val)`),
making it in-sample, not held-out, for exactly the three candidates this audit most needs to
re-examine. The plan should treat this as a hard, load-bearing scoping fact, not an incidental
caveat: D-02's "strengthened comparison" and D-03's "genuinely new analysis" will, as of this
research date, have to rely primarily on (a) a synthetic/ablation validation of the new
block-bootstrap and quantile-calibration *code* (testable today, zero real-data dependency), and
(b) an explicitly-scoped, explicitly-small (or explicitly-deferred) real fresh-data confirmation
pass whose calendar boundaries are defined now and whose row count grows only as real time passes.

On the positive side, several of CONTEXT.md's suspected gaps turn out, on direct code inspection, to
be either non-issues or already-documented: the six-hourly scoring filter does **not** corrupt arm
5's lag-feature offsets (the lag features are built from the full unfiltered hourly truth series
*before* the filter is ever applied — the filter only reindexes into an already-correct feature
table); `thermal_model.py`'s natural-convection floor (`np.maximum(Q_cf, Q_cn)`) and the
`q_conv_override` seam's default path are provably bit-identical to the pre-refactor formula via an
existing golden-array regression test; and the Archive API's ERA5/ERA5-Land reanalysis provenance
claim is accurate as read directly from `open_meteo_provider.py`'s docstring. But the decision
record genuinely never states, anywhere in its Data provenance or Limitations sections, that the
"truth" side of the whole experiment is itself a physics/data-assimilation model output with no
independent sensor-measured validation — this is a real, confirmed gap for D-01 to correct. And the
lead-time calibration gate (`forecast_leadtime_calibration.py`) genuinely proves only a
value-matching / stitching-rule claim between two archival products, not that a real downstream
consumer had the forecast disseminated to it at the claimed decision time — also a real, confirmed
gap, and already partially acknowledged in the decision record's own Limitations section
(Assumption B2) but not stated as bluntly as the D-01 audit brief wants.

**Primary recommendation:** Scope D-02/D-03's new empirical work as two explicit tracks — a
synthetic/ablation-validated methodology track (deliverable now, proves the block-bootstrap and
quantile-calibration code is correct) and a real fresh-holdout confirmation track (deliverable only
as calendar time accrues past 2026-09-29, with boundaries defined but the row count left honestly
small or zero today) — and write the corrected decision record so that every claim distinguishes
which track it comes from.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Data provenance re-audit (D-01) | Offline ML/analysis (`backend/*.py`, read-only) | — | Pure code/doc inspection; no runtime tier involved |
| Block-bootstrap / pairwise comparison (D-02) | Offline ML/analysis, new module or extension of `forecast_experiment.py` | — | Statistical post-processing of scored arms; never touches `ampacity_forecast.py` |
| Overrating / quantile analysis (D-03) | Offline ML/analysis, new module | — | New estimator (quantile GBR) + new metric (pinball loss); offline harness only |
| Decision-record correction (D-04) | Documentation (`docs/data-science/decisions/`) | — | Prose amendment, no code change |
| Integration-readiness plan (D-05) | Documentation / planning artifact | Backend (future phase) | This phase only plans; a future phase would touch `ampacity_forecast.py`, the runtime pipeline, and API/monitoring tiers |

No capability in this phase touches the browser, frontend server, CDN, or production database
tiers — everything is either read-only code audit or offline analysis scripts mirroring
`forecast_training.py`/`forecast_experiment.py`'s own "standalone, not imported by the runtime
pipeline" convention.

## Standard Stack

### Core

| Library | Version (verified in `.venv`) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `scipy` | 1.17.1 `[VERIFIED: .venv/bin/python3 -c "import scipy; print(scipy.__version__)"]` | Existing i.i.d. bootstrap (`scipy.stats.bootstrap`), general numerics | Already the project's bootstrap tool (`forecast_experiment.paired_bootstrap_margin`) |
| `numpy` | 2.4.3 `[VERIFIED: same command]` | Hand-rolled block-bootstrap resampling, array ops | Only tool needed for a moving/circular block bootstrap — no dependency gap |
| `pandas` | 2.3.3 `[VERIFIED: same command]` | Frame assembly, chronological boundary logic | Already every module in this phase's dependency chain uses it |
| `scikit-learn` | 1.9.1 `[VERIFIED: same command]` | `GradientBoostingRegressor(loss="quantile", alpha=...)`, `sklearn.metrics.mean_pinball_loss` | Both already exist in the installed version — confirmed via `inspect.signature` this session; `GradientBoostingRegressor` is already this project's Arm 4 estimator family |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| none | — | — | This phase needs no new library. `scipy.stats.bootstrap` has **no** block-length parameter (`[VERIFIED: .venv/bin/python3 -c "import inspect,scipy.stats; print(inspect.signature(scipy.stats.bootstrap))"` — signature has `n_resamples, batch, vectorized, paired, axis, confidence_level, alternative, method, bootstrap_result, rng, random_state`, no `block_size`]), so the block-bootstrap must be hand-rolled with `numpy`, not imported. |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled moving/circular block bootstrap (numpy) | `arch` package's `arch.bootstrap.MovingBlockBootstrap`/`CircularBlockBootstrap` | `arch` is a real, legitimate PyPI package (financial econometrics), but it is a **new** dependency this project's stack does not have (`STATE.md`'s own Blockers/Concerns note new ML dependencies require a legitimacy checkpoint). A ~20-30 line hand-rolled block bootstrap (resample fixed-length contiguous blocks with replacement, concatenate to length n, repeat) is well-understood, easy to unit-test against a known-variance synthetic series, and avoids the dependency-review overhead for a single well-defined statistical routine. Recommend hand-rolling. |
| `sklearn.ensemble.GradientBoostingRegressor(loss="quantile")` for D-03's lower quantile | `sklearn.linear_model.QuantileRegressor` | `QuantileRegressor` is linear-only; `GradientBoostingRegressor` matches this project's ALREADY-CHOSEN cooling-correction estimator family (Arm 4), so reusing it for the quantile variant keeps the estimator family consistent across the phase rather than introducing a second modeling paradigm. |

**Installation:** None required — every tool above is already present in `.venv`.

**Version verification:** Verified directly against the installed `.venv` (not training-data
versions) via `import` + `__version__` checks this session, and against `inspect.signature` for the
two sklearn/scipy APIs this phase's new code will call.

## Package Legitimacy Audit

No external packages are installed or proposed by this phase — every dependency (`scipy`, `numpy`,
`pandas`, `scikit-learn`) is already present in the project's `.venv` and was verified by direct
`import` in this research session, not merely proposed. This section is included per the RESEARCH.md
template but has no rows because the Package Legitimacy Gate protocol applies only when a phase
installs new packages.

**Packages removed due to [SLOP] verdict:** none — no new packages considered.
**Packages flagged as suspicious [SUS]:** none — no new packages considered.

## Architecture Patterns

### System Architecture Diagram

```
Phase 3 frozen artifacts                    Phase 4 audit (this phase)
──────────────────────────                  ──────────────────────────
docs/.../forecast_correction_       ┌──►  D-01 Provenance re-audit
  experiment.md (frozen prose)      │      reads: open_meteo_provider.py,
                                    │      open_meteo_forecast_provider.py,
backend/forecast_experiment.py     │      forecast_leadtime_calibration.py,
  (unmodified except additive      │      forecast_experiment.leakage_probe,
   new functions, never edited     │      _arm5_truth_frame / build_training_matrix
   in place)                       │      → writes: audit findings section
                                    │
data/experiment/*.json (aggregate  │  D-02 Strengthened comparison
  MAE/RMSE per arm — the ONLY      ├──►  reads: whatever aggregate JSON exists
  persisted output; per-row        │      (none currently on disk)
  predictions were NEVER saved)    │      NEW: block-bootstrap fn (numpy, hand-
                                    │      rolled) + pairwise-vs-cooling calls to
  (does not currently exist        │      score_arms(..., baseline_name="ml_
   on disk — git-ignored,          │      cooling_corrected") — run ONLY on a
   regenerated per invocation,     │      fresh chronological period or
   never committed)                │      synthetic data, NEVER on frozen test
                                    │      rows
                                    │
                                    ├──►  D-03 Conservative-rating analysis
                                    │      NEW: overrating-rate calculator,
                                    │      GradientBoostingRegressor(loss=
                                    │      "quantile") fit on a calibration
                                    │      sub-period, scored via mean_pinball_
                                    │      loss on a disjoint evaluation
                                    │      sub-period — both fresh/synthetic
                                    │
                                    ├──►  D-04 Corrected language
                                    │      writes: amendment section appended to
                                    │      forecast_correction_experiment.md
                                    │      (or a sibling audit document)
                                    │
                                    └──►  D-05 Integration-readiness plan
                                           writes: candidate ablation scope,
                                           minimum data contract, now-vs-later
                                           split, packaging/fallback/monitoring
                                           outline — a planning document, no code
```

A reader can trace the primary flow: Phase 3's frozen artifacts are read-only inputs; every new
computation this phase performs branches off either "read Phase 3's aggregate JSON/prose" (D-01,
D-04) or "compute fresh statistics on non-frozen data" (D-02, D-03); D-05 consumes the findings of
all four and produces a planning document, never code.

### Recommended Project Structure

```
backend/
├── forecast_experiment.py           # UNCHANGED except possibly new, additive
│                                     #   functions (never edit existing scoring
│                                     #   logic — Phase 3's frozen invariant)
├── forecast_experiment_audit.py     # NEW, Plan 03-06-mirroring standalone module:
│                                     #   block-bootstrap, pairwise comparisons,
│                                     #   overrating-rate calc, quantile calibration
├── tests/
│   └── forecast_experiment_audit_test.py  # NEW — synthetic-data unit tests for
│                                     #   block-bootstrap block-length sensitivity
│                                     #   and pinball-loss calibration correctness
docs/data-science/decisions/
├── forecast_correction_experiment.md   # frozen, amended only per D-04's specific
│                                        #   corrected-language items
└── forecast_correction_followup_audit.md  # NEW sibling document (Claude's
                                            #   discretion whether sibling or
                                            #   amendment — recommend sibling,
                                            #   since this phase's own findings
                                            #   (provenance re-audit, block-
                                            #   bootstrap methodology, overrating
                                            #   analysis) are new content, not a
                                            #   rewrite of Phase 3's existing
                                            #   Expectation/Measured/Verdict)
```

### Pattern 1: Additive-only audit code, mirroring Plan 03-06's own discipline

**What:** Every new function this phase adds (block-bootstrap, pairwise comparison, overrating
calculator, quantile calibration) should be a **new, additive** function/module — never an edit to
`forecast_experiment.py`'s existing `score_arms`, `paired_bootstrap_margin`, `corridor_experiment_
report`, or any of the seven arm factories. Phase 3's own docstrings already establish this
discipline (`paired_bootstrap_margin`, Plan 03-06 Task 3: "additive... every pre-existing caller's
behavior is byte-identical to before this parameter existed").
**When to use:** Any change touching `forecast_experiment.py` in this phase.
**Example:**
```python
# Source: backend/forecast_experiment.py:1377-1445 (score_arms), read directly this session —
# pattern to follow for a NEW sibling function, never an edit to score_arms itself.
def paired_block_bootstrap_margin(
    errors_arm, errors_baseline, *, block_length: int, n_resamples: int, confidence_level: float,
    random_state: int,
) -> dict:
    """
    Moving block bootstrap on the per-row |baseline| - |arm| difference series,
    resampling contiguous blocks of `block_length` rows (with replacement,
    concatenated to length n) instead of i.i.d. rows -- preserves whatever
    temporal autocorrelation is present in hourly ampacity residuals, which
    scipy.stats.bootstrap's i.i.d. resampling (used by paired_bootstrap_margin)
    does not.
    """
    ...
```

### Pattern 2: Reuse `experiment_splits.SplitBoundaries`/`calendar_split` for the fresh holdout

**What:** `backend/experiment_splits.py`'s `SplitBoundaries`/`calendar_split` (already used by
Phase 3) is a generic, reusable two-boundary calendar splitter — it takes any `datetime_utc`-bearing
frame and any two boundary dates, with no dependency on Phase 3's specific corridor data. This
phase's "reserved chronological period" (D-02) and quantile calibration-vs-evaluation split (D-03)
should both be expressed as new `SplitBoundaries` instances with explicit dates, not a hand-rolled
row slice.
**When to use:** Defining any new disjoint calendar period in this phase.
**Example:**
```python
# Source: backend/experiment_splits.py:44-73 (SplitBoundaries), read directly this session.
# This phase's own new boundaries would be constructed the same way, e.g.:
fresh_boundaries = experiment_splits.SplitBoundaries(
    val_start="2026-09-30",   # or later -- whatever "yesterday" resolves to at run time
    test_start="2026-XX-XX",  # a second boundary if D-03 needs calibration-vs-evaluation split
)
```

### Anti-Patterns to Avoid

- **Re-invoking `backend/forecast_experiment.py --split test`:** This reproduces the exact frozen
  numbers deterministically (fixed random state `config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_
  STATE = 20260929`), but CONTEXT.md's Phase Boundary explicitly forbids re-running or re-scoring
  the held-out test set regardless of determinism — do not do this even to "just get the residuals
  that were never saved."
- **Treating the validation split as a legitimate fresh holdout for the fitted arms:** `train_val_
  stacked = concat(stacked_train, stacked_val)` (`forecast_experiment.py:1937-1944`) is exactly what
  `fit_fitted_arms` trains on — scoring `ml_wind_corrected`/`ml_cooling_corrected`/`reference_ml_
  refit_24h` against validation-split rows would be in-sample evaluation, not a holdout, for those
  three arms specifically (the four non-fitted arms were genuinely scored on val in Plan 03-04, but
  that's a different, non-fitted set).
- **Inventing per-row data to "unblock" block-bootstrap or overrating analysis:** CONTEXT.md's own
  execution notes require documenting the absence explicitly rather than fabricating residuals.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Lower ampacity quantile prediction | A custom quantile-loss gradient-descent loop | `sklearn.ensemble.GradientBoostingRegressor(loss="quantile", alpha=<q>)` `[VERIFIED: .venv/bin/python3 -c "from sklearn.ensemble import GradientBoostingRegressor; import inspect; print(inspect.signature(GradientBoostingRegressor.__init__))"` — signature includes `loss='squared_error'` (accepts `'quantile'`) and `alpha=0.9`] | Already the estimator family this project uses for Arm 4; sklearn's quantile loss is a standard, tested implementation |
| Pinball-loss scoring | A custom asymmetric-loss function | `sklearn.metrics.mean_pinball_loss(y_true, y_pred, alpha=...)` `[VERIFIED: .venv/bin/python3 -c "from sklearn.metrics import mean_pinball_loss; import inspect; print(inspect.signature(mean_pinball_loss))"` — signature `(y_true, y_pred, *, sample_weight=None, alpha=0.5, multioutput='uniform_average')`] | Standard scikit-learn metric, exact formula match, avoids an off-by-factor-of-two bug (pinball loss at alpha=0.5 equals half of MAE — easy to get wrong by hand) |
| Chronological/calendar boundary splitting | A hand-rolled date-comparison slice | `experiment_splits.SplitBoundaries`/`calendar_split` (already in-repo) | This project already solved the "strictly time-ordered, empty-side guard, purity" problem twice (`anomaly_training.chronological_split`, `experiment_splits.calendar_split`) — a third hand-rolled version would risk silently drifting from the two existing ones' disjointness guarantees |

**Key insight:** Every genuinely new piece of code this phase needs (block bootstrap, overrating
rate, quantile calibration) is either a thin wrapper over an existing sklearn/scipy primitive or a
~20-30 line numpy routine with no existing library equivalent in this project's stack — there is no
"don't hand-roll" violation risk here except the temptation to reach for a new heavyweight
dependency (`arch`, `statsmodels` — neither installed, `[VERIFIED: .venv/bin/python3 -c "import
statsmodels"` raised `ModuleNotFoundError`]) when the existing stack already suffices.

## Common Pitfalls

### Pitfall 1: Assuming per-row predictions exist somewhere because the aggregate numbers are so precise

**What goes wrong:** The decision record's tables report MAE/RMSE to three decimal places and exact
95% CIs — it is tempting to assume the underlying per-row arrays must be saved somewhere (a cache,
a hidden artifact). They are not.
**Why it happens:** `forecast_experiment.py`'s `score_arms` (line 1377) computes `residuals` and
`candidates` (aggregate MAE/RMSE) in one function body, but only `candidates` is returned and only
`candidates` is ever written to JSON (`corridor_experiment_report`, line 1571, never receives or
persists `residuals`). The residual arrays are garbage-collected the moment `score_arms` returns.
**How to avoid:** Treat "was it persisted" as a question answerable only by reading every
`to_csv`/`json.dump`/`joblib.dump` call site in the module (there are exactly three: the input
weather cache at line 672, and the two JSON report writes at lines 1714 and 1983) — confirmed this
session via `grep -n "to_csv\|joblib\|pickle\|json.dump"`.
**Warning signs:** Any plan task that says "load Phase 3's saved predictions" without first
confirming a specific file path and its contents will fail at execution time.

### Pitfall 2: Treating `.shift(h)` lag features as time-safe on a frame with silent gaps

**What goes wrong:** `ampacity_forecast.build_ml_features` (line 144-145) computes lag features via
`frame["dlr_amps"].shift(h)` — a **positional** row shift, correct only if the frame has an unbroken
hourly cadence. `_arm5_truth_frame` (forecast_experiment.py:1031) builds its input from
`anchored_pair_frame`'s already-`dropna()`'d truth columns (line 658) — and that `dropna()` drops an
entire row if **any** of the truth/anchor/fcst/fcst_anchor column groups has a null, even if the
truth value itself is present. If the forecast source (Previous Runs API) has occasional missing
hours somewhere in the 2024-01-20 → 2026-09-29 window, the truth series feeding arm 5's lag features
would have a gap at exactly that hour, and `.shift(1)` would then be silently "1 row back" = more
than 1 hour back at that point, not the intended 1-hour lag.
**Why it happens:** The row-drop is a project-wide, deliberate design choice ("nothing is ever
padded... an absent value here is a failed fetch, never a null column" —
`open_meteo_forecast_provider.py:54-57`), but it has a side effect on arm 5's lag-feature assumption
that the module's own docstring ("UNFILTERED... needs a genuine hourly cadence for its lag
features," `forecast_experiment.py:1013-1017`) does not fully account for: "unfiltered" (with
respect to the six-hourly scoring filter) is not the same claim as "gap-free."
**How to avoid:** During D-01's audit, empirically check (once a fresh `anchored_pair_frame` cache
is built for any window) whether `len(merged)` before/after the `dropna()` at line 658 differs from
the expected hourly row count for that window — a nonzero drop count means arm 5's lag features
could be affected. This could not be checked in this research pass because `data/experiment/`
currently has no cached frames on disk and building one requires a live network fetch — flagged as
an Open Question below, not resolved.
**Warning signs:** Any large discrepancy between `rows_assembled` (23,592 in the frozen record, one
row per hour over the full window) and what an hour-count over the same span computes to
independently.

### Pitfall 3: Confusing "the calibration gate proves an exact lead" with "the calibration gate proves decision-time availability"

**What goes wrong:** `forecast_leadtime_calibration.py`'s `assert_exact_offset_lead`/`measure_
previous_runs_alignment` (lines 390-624, not fully quoted here) prove that the **value** in the
Previous-Runs bulk product at valid time T matches the **value** in the Single-Runs archive at a
specific measured offset — a pure archival value-matching cross-check between two backward-looking
data products. It says nothing about whether a real-time forecast consumer, at the actual clock
time `T - 24h`, could have received this exact forecast value over the network at that moment.
**Why it happens:** Both products are themselves retrospective archives; the calibration gate can
only compare two archives against each other, never against a genuine real-time dissemination log.
**How to avoid:** State this distinction explicitly in D-01's findings — the gate answers "what lead
does this archived value's construction correspond to," not "was this value actually available for
consumption at that lead in real time." The decision record's own Limitations section already
gestures at a related but narrower point (Assumption B2, the Single-Runs archive's shallow reach
limits historical cross-check coverage) — this is a distinct, additional limitation the audit should
name on its own terms.
**Warning signs:** Any language in the decision record implying "available at decision time" when
the evidence only supports "constructionally corresponds to a T-24h-labeled value."

## Code Examples

### Confirming what Phase 3 persisted (per-row predictions: nothing; aggregates: JSON only)

```python
# Source: backend/forecast_experiment.py, read directly this session.
# score_arms (line 1377) — computes residuals, but only candidates (aggregate) survives:
    residuals = {}
    candidates = {}
    for name, fn in arms.items():
        pred = np.asarray(fn(test_frame), dtype=float)
        residual = actual - pred
        residuals[name] = residual                 # <- exists only in this function's local scope
        candidates[name] = {
            "mae": float(np.mean(np.abs(residual))),
            "rmse": float(np.sqrt(np.mean(residual ** 2))),
            "rows": int(n),
        }
    # ... residuals is used locally for paired_bootstrap_margin, then discarded.
    return {"candidates": candidates, "test_index": list(test_frame.index), **index_info}

# _run_corridor's only disk writes (lines 1971-1983):
    report_path = os.path.join(config.FORECAST_EXPERIMENT_CACHE_DIR, report_filename)
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)   # <- report["candidates"] only: MAE/RMSE/margin
```

### Verifying no fitted model is ever persisted for arms 3/4/5

```python
# Source: backend/forecast_experiment.py:1078-1090, read directly this session (fit_fitted_arms
# docstring, verbatim):
"""
... fit with `forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]` ... via
`forecast_training.fit_corridor_model` -- which only calls
`estimator.fit(...)`, never `persist_corridor_model` and never
anything in `ampacity_forecast`, so arm 5 can never reach the
persisted production artifact ...
"""
```

### Confirming the six-hourly filter does NOT corrupt arm 5's lag offsets

```python
# Source: backend/forecast_experiment.py:1856-1867 and :1031-1060, read directly this session.
# X5_all is built from the FULL unfiltered truth frame (build_training_matrix has no filter
# applied yet); filtering to the exact-24h-lead rows happens AFTER, via reindex onto the
# already-correct anchor timestamps -- not by filtering the raw series before lag computation:
    arm5_truth_frame = _arm5_truth_frame(stacked_full, city_a, city_b)   # full hourly cadence
    X5_all, _ = forecast_training.build_training_matrix(arm5_truth_frame, horizon_minutes=1440)
    anchor_index = pd.DatetimeIndex(pd.to_datetime(scored_frame["anchor_datetime_utc"], utc=True))
    X5_scored = X5_all.reindex(anchor_index)   # <- selection AFTER lag features are already correct
```

### Verified sklearn APIs for D-03's quantile work

```python
# Source: local .venv/bin/python3 introspection this session (sklearn 1.9.1).
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_pinball_loss

# GradientBoostingRegressor.__init__ signature includes: loss='squared_error' (accepts 'quantile'),
# alpha=0.9 (the target quantile when loss='quantile')
model = GradientBoostingRegressor(loss="quantile", alpha=0.10, random_state=...)  # lower-tail quantile

# mean_pinball_loss(y_true, y_pred, *, sample_weight=None, alpha=0.5, multioutput='uniform_average')
loss = mean_pinball_loss(y_true, y_pred, alpha=0.10)
```

## State of the Art

| Old Approach (Phase 3) | Current Approach (this phase's audit) | When Changed | Impact |
|--------------------|------------------|--------------|--------|
| i.i.d. paired bootstrap (`scipy.stats.bootstrap`, `BCa`) on the per-row absolute-error difference | Paired **block** bootstrap (hand-rolled, moving or circular blocks) with block-length sensitivity | This phase, D-02 | Accounts for temporal autocorrelation in hourly ampacity residuals that i.i.d. resampling assumes away — CIs from the block method are expected to be wider than Phase 3's i.i.d. CIs for the same nominal confidence level, per general time-series bootstrap literature (Hall et al. 1995's `B ≈ N^0.25` block-length heuristic; Politis & White's block-size-from-ACF estimator) `[CITED: web search this session — "moving block bootstrap... block length selection", multiple sources including arxiv.org/pdf/2304.14236 and blogs.sas.com/content/iml/2021/01/13/moving-block-bootstrap-sas.html; not independently verified against a primary statistics text this session]` |
| Margin only vs. `persistence_24h` baseline | Direct pairwise margins between `ml_cooling_corrected` and each of `raw_forecast`/`ml_wind_corrected`/`reference_ml_refit_24h` | This phase, D-02 | `score_arms`'s existing `baseline_name` parameter already generalizes to any arm as baseline — no new scoring machinery needed, just additional calls with `baseline_name="ml_cooling_corrected"` on non-frozen data |
| Point MAE/RMSE only | Overrating rate/magnitude/duration by regime + calibrated lower quantiles + pinball loss | This phase, D-03 | Genuinely new analysis axis; needs `GradientBoostingRegressor(loss="quantile")` (available, unused until now) |

**Deprecated/outdated:** Nothing in Phase 3's own code is deprecated by this phase — every new
function is additive, per Pattern 1 above.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Block-length sensitivity heuristics (Hall et al. `N^0.25`, Politis-White ACF-based sizing) are appropriate for this project's ~786-row/corridor hourly residual series | State of the Art | If wrong, the chosen block lengths could under- or over-smooth the resampled variance, making the block-bootstrap CIs either too narrow (false confidence) or too wide (uninformative) — mitigated by the D-02 requirement to test more than one block length and report stability, which the plan should retain regardless of which specific lengths are chosen |
| A2 | No genuinely fresh real corridor data exists beyond ~2026-09-29 as of this research date (2026-09-30) | Summary, Architecture Patterns anti-patterns | If a wider window is actually fetchable (e.g., if "yesterday" resolves later at execution time than at research time, or if the archive's `2026-09-29` end date in the frozen record was itself conservative), the fresh-holdout row count could be larger than assumed here — this is a currently-time-bound fact, not a permanent one, and the plan should re-check the actual `yesterday` resolution at execution time rather than hard-coding this research session's finding |
| A3 | `anchored_pair_frame`'s `dropna()` (forecast_experiment.py:658) causes a nonzero, meaningful number of gaps in the hourly truth series feeding arm 5's lag features | Common Pitfalls, Pitfall 2 | This is a structural/logical finding from reading the code, not an empirically-measured gap count — the actual gap frequency could be zero in practice if the Previous-Runs API has never actually returned a null for the pinned `gfs_seamless` model over this window; the plan should verify this empirically (Open Questions) before treating it as a real finding worth reporting in the audit's own findings |

## Open Questions

1. **How many rows, if any, does `anchored_pair_frame`'s `dropna()` actually drop for the frozen
   window, and does that create a lag-feature gap for arm 5 (Pitfall 2)?**
   - What we know: the code path that WOULD create this gap is confirmed by direct read
     (forecast_experiment.py:657-665, :1031-1060).
   - What's unclear: whether it ever fires in practice for this project's actual data — this
     research pass made no live network calls and the cache directory is currently empty.
   - Recommendation: the plan's D-01 audit task should build (or reuse, if already built during
     execution) a fresh `anchored_pair_frame` cache and log the `dropped` count `forecast_
     experiment.py:660-665` already computes and warns about, then cross-check it against an
     independent hourly-row-count expectation for the window.

2. **What is the actual size of the currently-available fresh chronological holdout at execution
   time?**
   - What we know: as of this research session (2026-09-30), the frozen test split runs through
     2026-09-29, leaving ~0-1 usable days.
   - What's unclear: how many days will have accrued by the time this phase is actually planned and
     executed, and whether that's enough for a statistically meaningful block-bootstrap or
     calibration-vs-evaluation quantile split.
   - Recommendation: the plan should have the execution step re-resolve "yesterday" at run time
     (mirroring `forecast_experiment._resolve_window_end`'s own convention) rather than hard-coding
     any date from this research session, and should explicitly branch: if row count is too small
     for a meaningful CI, report that honestly (per CONTEXT.md's own execution notes) rather than
     stretching a tiny sample into a confident claim.

3. **Does a synthetic-data-only validation of the block-bootstrap/quantile-calibration code
   satisfy D-02/D-03's substantive intent, or does the user expect a real-data confirmation pass to
   be attempted regardless of how small?**
   - What we know: CONTEXT.md's Domain section explicitly permits "synthetic/ablation analysis" as
     an acceptable fresh basis, and the Execution Notes explicitly anticipate a fresh holdout "too
     short to be meaningful."
   - What's unclear: whether the user would want a `checkpoint:human-verify` before finalizing the
     decision record with only synthetic-validated methodology and a near-empty real-data
     confirmation.
   - Recommendation: the plan should include a checkpoint after computing whatever real fresh
     holdout size is available at execution time, surfacing the row count to the user before writing
     final language into the audit's own decision record.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `.venv` Python (backend) | All new audit code | ✓ | Python running `.venv/bin/python3` | — |
| `scipy` | Existing bootstrap + numeric base for hand-rolled block bootstrap | ✓ | 1.17.1 | — |
| `numpy` | Block-bootstrap resampling | ✓ | 2.4.3 | — |
| `pandas` | Frame assembly, calendar boundaries | ✓ | 2.3.3 | — |
| `scikit-learn` | Quantile GBR, pinball loss | ✓ | 1.9.1 | — |
| `statsmodels` | Would provide alternative block-bootstrap primitives | ✗ | — | Hand-roll with numpy (see Standard Stack) — no functional loss, since the needed routine is simple |
| `arch` | Would provide `MovingBlockBootstrap`/`CircularBlockBootstrap` classes | ✗ | — | Hand-roll with numpy (see Standard Stack) |
| Network access to `archive-api.open-meteo.com`, `previous-runs-api.open-meteo.com`, `single-runs-api.open-meteo.com` | Fetching any fresh chronological data for D-02/D-03 | Not tested this session (no live calls made in a read-only research pass) | — | If unreachable at execution time, D-02/D-03's real-data track degrades to synthetic-only, which is already an explicitly-permitted fallback per CONTEXT.md |

**Missing dependencies with no fallback:** none — every missing item above has an in-repo fallback.

**Missing dependencies with fallback:**
- `statsmodels`/`arch` — hand-roll block bootstrap with `numpy` (recommended anyway, per Don't
  Hand-Roll discretion above, to avoid new dependency review overhead for one routine).
- Live network access — degrade to synthetic/ablation-only if unreachable at execution time.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` (project-wide; `[VERIFIED: /Users/aphan/Senior_Design/pytest.ini exists]`) |
| Config file | `/Users/aphan/Senior_Design/pytest.ini` |
| Quick run command | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_test.py` (mirrors Phase 3's own targeted-test convention, `03-06-PLAN.md:298`) |
| Full suite command | `.venv/bin/python3 -m pytest -q` (mirrors `03-06-PLAN.md:312`/`:484`) |

**Pre-existing baseline, not a regression this phase introduces:** the full suite currently reports
23 pre-existing failures in `backend/tests/corridor_discretization_test.py`, confirmed unrelated to
Phase 3 (and by extension Phase 4) — documented in Phase 3's own
`.planning/workstreams/ml-modeling/phases/03-.../deferred-items.md`. Any plan for this phase should
state this baseline explicitly (470 passed / 23 failed, or whatever the current count is at
execution time) before making any pass/fail claim about its own new tests.

### Phase Requirements → Test Map

No formal requirement IDs apply to this phase (see `<phase_requirements>` above). The five D-0X
decisions substitute for requirement IDs; a corresponding test map:

| Decision | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| D-01 | Data-provenance/leakage claims are code-grounded, not report-trusting | manual (doc read + `grep`/`Read` audit, not unit-testable) | n/a — audit findings are prose, verified by citation | n/a |
| D-02 | Block-bootstrap CI computed correctly, sensitive to block length in the expected direction | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_audit_test.py::test_block_bootstrap_*` | ❌ Wave 0 — new file |
| D-02 | Pairwise comparison (`score_arms(..., baseline_name="ml_cooling_corrected")`) produces symmetric, sane margins | unit | same file, `::test_pairwise_margin_*` | ❌ Wave 0 |
| D-03 | Overrating-rate calculator correctly counts prediction > truth by regime | unit | same file, `::test_overrating_rate_*` | ❌ Wave 0 |
| D-03 | Pinball loss / quantile calibration split is chronologically disjoint (calibration vs. evaluation) | unit | same file, `::test_quantile_calibration_split_disjoint` | ❌ Wave 0 |
| D-04 | Corrected language changes are additive to the frozen record, never edit the Expectation/Measured-results sections | manual (git diff review) | `git diff docs/data-science/decisions/forecast_correction_experiment.md` shows only permitted sections touched | n/a |
| D-05 | Integration-readiness plan document exists with all five named sub-items | manual (document review checklist) | n/a | ❌ Wave 0 — new document |

### Sampling Rate

- **Per task commit:** targeted test file (`backend/tests/forecast_experiment_audit_test.py`).
- **Per wave merge:** full suite (`.venv/bin/python3 -m pytest -q`), comparing against the known
  23-failure baseline.
- **Phase gate:** Full suite green (modulo the pre-existing 23-failure baseline) before
  `/gsd-verify-work`.

### Wave 0 Gaps

- [ ] `backend/tests/forecast_experiment_audit_test.py` — new file, covers D-02/D-03's new code
      with synthetic autocorrelated data (does not require network access or any fresh real data)
- [ ] Framework install: none — `pytest` already present

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | This phase has no auth surface — offline analysis scripts, no API/UI |
| V3 Session Management | No | Same reason |
| V4 Access Control | No | Same reason |
| V5 Input Validation | Marginal — yes for any new network fetch code | Reuse `open_meteo_forecast_provider.py`'s existing `_completeness_check` pattern (never pad/impute a null) if any new fetch code is written; otherwise not applicable |
| V6 Cryptography | No | No secrets or crypto touched by this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Silent data leakage across a "fresh" holdout boundary (the phase's central risk, not a classic security threat but structurally analogous to an information-disclosure boundary violation) | Information Disclosure (of future information into a past-only feature) | Reuse `assert_exact_lead`/`assert_filtered_split_disjoint`-style assertions (already in `forecast_experiment.py`) for any new chronological boundary this phase defines, rather than trusting a date string alone |
| Overstating a statistical claim beyond what the evidence supports (D-04's entire purpose) | Repudiation-adjacent (a report that can't be traced back to its actual evidence) | Every new claim in the audit document must cite its specific source data/computation, mirroring the frozen record's own "git log is the audit trail" discipline |

## Sources

### Primary (HIGH confidence — read directly this session)

- `backend/forecast_experiment.py` (full file, 2075 lines) — arm registry, `score_arms`,
  `paired_bootstrap_margin`, `leakage_probe`, `fit_fitted_arms`, `_arm5_truth_frame`,
  `corridor_experiment_report`, `main` — the harness under audit
- `backend/forecast_training.py:288-353` — `build_training_matrix` (horizon shift, lag-feature
  timing)
- `backend/ampacity_forecast.py:124-159` — `build_ml_features` (lag feature construction, confirms
  `.shift(h)` is positional)
- `backend/thermal_model.py` (full file) — `natural_convection`, `convective_heat_loss`,
  `ieee738_ampacity`'s `q_conv_override` seam and its bit-identical-default-path claim
- `backend/open_meteo_provider.py:1-80` — Archive API / ERA5-ERA5-Land reanalysis provenance claim
- `backend/open_meteo_forecast_provider.py:1-120` — three-endpoint forecast adapter, model pinning
  rationale, null-handling discipline
- `backend/forecast_leadtime_calibration.py:1-300` — lead-time calibration gate's actual measured
  claim (value-matching, not dissemination-latency proof)
- `backend/experiment_splits.py` (full file) — `SplitBoundaries`/`calendar_split`
- `backend/anomaly_training.py:394-438` — `chronological_split` (precedent two-way splitter)
- `backend/config.py` (grepped for all `FORECAST_EXPERIMENT_*` constants, `FORECAST_ML_LAG_HOURS`,
  `FORECAST_HORIZON_MINUTES`, `CITY_COORDINATES`, `CORRIDOR_ENDPOINTS`, `STATIC_RATINGS`)
- `docs/data-science/decisions/forecast_correction_experiment.md` (full file) — the frozen record
  under audit
- `docs/data-science/decisions/forecasting_model.md` (headers only) — 9-section ADR format
  precedent
- `.planning/workstreams/ml-modeling/phases/03-.../deferred-items.md` — pre-existing 23-failure test
  baseline
- `.gitignore` — confirms `/data/experiment/` is git-ignored, "not the artifact of record"
- `.venv` direct introspection (`import scipy/numpy/pandas/sklearn`, `inspect.signature` on
  `scipy.stats.bootstrap`, `GradientBoostingRegressor.__init__`, `mean_pinball_loss`) — this session
- Filesystem check: `data/experiment/` does not currently exist (`find` returned "No such file or
  directory")
- `pytest.ini` exists at project root; `backend/tests/forecast_experiment_test.py` and siblings exist

### Secondary (MEDIUM confidence)

- WebSearch: moving/circular block bootstrap block-length heuristics (Hall et al. `N^0.25`, Politis-
  White ACF-based sizing) — cross-referenced across multiple results (arxiv.org/pdf/2304.14236,
  blogs.sas.com, medium.com), not verified against a single primary statistics reference this
  session `[CITED, not VERIFIED]`
- WebSearch: `sklearn.metrics.mean_pinball_loss` / `GradientBoostingRegressor(loss="quantile")`
  semantics — cross-referenced against scikit-learn's own official docs pages appearing in search
  results, AND independently confirmed via local `inspect.signature` against the actually-installed
  1.9.1 (the signature check is the HIGH-confidence part; the semantic description of what "quantile
  loss" does is `[CITED: scikit-learn.org]`)

### Tertiary (LOW confidence)

- None — no findings in this document rest solely on an unverified WebSearch result with no
  cross-check against either the installed environment or an official docs page.

## Metadata

**Confidence breakdown:**
- Data provenance / leakage findings (D-01): HIGH — every claim cites a specific file:line read
  directly this session
- Persisted-artifact scope constraint (D-02/D-03's central finding): HIGH — confirmed by exhaustive
  `grep` for every disk-write call in the relevant modules, plus a direct filesystem check
- Block-bootstrap/quantile methodology recommendations: MEDIUM — the *that these are the standard
  tools* claim is HIGH (verified against installed versions), the *specific block-length heuristics*
  claim is MEDIUM (web-search-sourced, not independently re-derived)
- Fresh-holdout data availability (A2 in Assumptions Log): MEDIUM-HIGH but explicitly time-bound —
  correct as of this research date, must be re-checked at execution time

**Research date:** 2026-09-30
**Valid until:** The code-grounded findings (D-01 audit facts, persisted-artifact scope) do not
expire — they describe frozen Phase 3 code. The fresh-holdout row-count finding (A2) is valid only
as of 2026-09-30 and should be re-resolved at execution time, not reused verbatim.
