# Phase 2: Anomaly Detection Model - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-24
**Phase:** 2-Anomaly Detection Model
**Areas discussed:** What the model looks at, Model technique, How it plugs into check(), Validation bar

---

## What the model looks at

| Option | Description | Selected |
|--------|-------------|----------|
| Raw per-variable readings | Check wind/temp/solar in raw_data directly against learned per-variable historical baselines — catches a bad sensor reading before it reaches the physics formula; literal ANOM-01 scope; no Track 1 changes needed | ✓ |
| The derived rating only | Keep judging computed dlr_amps with a trained model instead of mean±k·std | |
| Both, as one added path | One trained model consumes wind/temp/solar plus the derived rating together | |

**User's choice:** Raw per-variable readings.
**Notes:** None.

| Option | Description | Selected |
|--------|-------------|----------|
| Training-only, not live | Use historical ERCOT load only during training/characterization; live check() only sees wind/temp/solar as it does today — zero Track 1 changes | ✓ |
| Drop load entirely | Scope ANOM-01's "load" mention out for this phase, note the gap in the validation record | |
| Flag as a real blocker | Treat missing live load as a genuine scope conflict requiring a Track 1 coordination ask before continuing | |

**User's choice:** Training-only, not live.
**Notes:** Resolves the tension between ANOM-01's literal wording ("wind, temp, solar, load") and REQUIREMENTS.md's Track 1 out-of-scope boundary without blocking on cross-track coordination.

---

## Model technique

| Option | Description | Selected |
|--------|-------------|----------|
| IsolationForest | Ships in scikit-learn (already installed); designed for exactly this use case; interpretable anomaly score | ✓ |
| EllipticEnvelope (robust covariance) | Also in scikit-learn; simpler/more interpretable but assumes roughly Gaussian features | |
| OneClassSVM | Also in scikit-learn; more flexible boundary, slower to tune, less interpretable | |
| You decide (Claude's discretion) | Let researcher/planner pick based on measured performance | |

**User's choice:** IsolationForest, as a starting candidate.
**Notes:** Not locked exclusively — see next question.

| Option | Description | Selected |
|--------|-------------|----------|
| Stay simple/interpretable | Prefer a technique whose decisions are easy to explain in an alert message | |
| Open to more power if it measurably helps | Let the researcher try a couple of candidates and pick whichever wins on real measured false-positive/negative rates | ✓ |

**User's choice:** Open to more power if it measurably helps.
**Notes:** Despite Phase 1's finding that the fancier model lost to naive, the user does not want Phase 2 to default to the simplest option out of caution — evaluate on real evidence (D-04 in CONTEXT.md). Combined with the IsolationForest answer above, this reads as: start with IsolationForest, but a bake-off against other scikit-learn candidates is legitimate if time allows (Claude's discretion on whether to actually run one).

---

## How it plugs into check()

| Option | Description | Selected |
|--------|-------------|----------|
| New third branch | Additive: existing paths untouched, trained model is a new signal | ✓ |
| Replace rolling_baseline (cold-start path) | Upgrade only the weakest existing path | |
| Replace forecast_residual (primary path) | Replace the main signal outright — higher risk | |

**User's choice:** New third branch.
**Notes:** Mirrors Phase 1's own additive precedent (new "ml" method alongside naive/ewm, nothing removed).

| Option | Description | Selected |
|--------|-------------|----------|
| Anomalous if ANY path flags it | Most conservative — trip G6 if either the heuristic or the trained model flags it | ✓ |
| Trained model takes precedence when available | Trust the model's verdict over the heuristic once it has enough data | |
| Existing heuristic stays primary, model is informational only | Model's verdict is logged for the validation record but doesn't trip G6 itself yet | |

**User's choice:** Anomalous if ANY path flags it.
**Notes:** Consistent with this project's fail-safe-first ethos — the new model can only ever add caution, never suppress an existing path's trip.

---

## Validation bar

| Option | Description | Selected |
|--------|-------------|----------|
| Must beat the baseline to ship as-is | Model's trip rate must beat mean±k·std's trip rate on real data, or don't ship it live yet | |
| Measure and report honestly either way | State the expectation before the result, write an explicit met/not-met verdict, ship the additive path regardless (it can only add caution, per the OR-combination) | ✓ |

**User's choice:** Measure and report honestly either way.
**Notes:** Matches FCST-02's precedent exactly — the same honesty-first pattern this project already established in Phase 1's validation record when the ML forecast lost to naive.

---

## Claude's Discretion

- Exact `IsolationForest` hyperparameters, and whether to actually run a multi-candidate bake-off or ship `IsolationForest` alone.
- Exact per-location granularity mechanism (follow `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`/`for_corridor`'s existing pattern).
- Exact feature engineering for the per-variable model (e.g. time-of-day/seasonal features).
- Exact filename/structure of the Phase 2 validation record.
- Depth of the training-time ERCOT load characterization (lightweight sanity check vs. thorough correlation analysis).

## Deferred Ideas

None — discussion stayed within Phase 2 scope. Wiring live ERCOT load into `raw_data` for live inference was considered and explicitly deferred to Track 1's own scope, not queued as a Phase 2 backlog idea.
