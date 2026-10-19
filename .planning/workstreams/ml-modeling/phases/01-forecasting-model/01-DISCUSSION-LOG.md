# Phase 1: Forecasting Model - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-23
**Phase:** 1-Forecasting Model
**Areas discussed:** Model approach, New dependency stance, Feature scope, Validation record format

---

## Model approach

| Option | Description | Selected |
|--------|-------------|----------|
| Regression (Recommended) | Simpler, faster to validate, no GPU/deep-learning dependency needed. | |
| Neural network | More capacity for nonlinear interactions, but needs a much heavier dependency and more data/tuning. | |
| You decide | Let the researcher/planner make the call based on what the actual backtested data volume supports. | ✓ |

**User's choice:** You decide.

Follow-up: Lean regression by default (Recommended) vs. Fully open, no default lean.

| Option | Description | Selected |
|--------|-------------|----------|
| Lean regression by default (Recommended) | Only pick NN if research finds strong evidence it's clearly warranted. | |
| Fully open, no default lean | Researcher picks purely on backtested accuracy, zero bias toward either approach. | ✓ |

**User's choice:** Fully open, no default lean.
**Notes:** Regression-vs-NN is fully delegated to research/planning, decided on measured backtested accuracy against real data, with no built-in preference either way.

---

## New dependency stance

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-roll with numpy/scipy first (Recommended) | Try a numpy/scipy-only regression before reaching for a new dependency; avoids the legitimacy review entirely if good enough. | |
| Just approve scikit-learn now | Skip the hand-rolled attempt; approve scikit-learn upfront. | ✓ |
| You decide | Let the researcher/planner weigh it once they see what the model needs. | |

**User's choice:** Just approve scikit-learn now.

Follow-up: scope of approval.

| Option | Description | Selected |
|--------|-------------|----------|
| scikit-learn specifically (Recommended) | Covers the vast majority of regression approaches in one well-known package. | |
| Any well-established scientific-Python ML library | Latitude to pick xgboost/statsmodels/etc. if a better fit, still subject to legitimacy verification. | ✓ |

**User's choice:** Any well-established scientific-Python ML library.
**Notes:** A new ML dependency is pre-approved as a class (not pinned to one specific library), still subject to the standard package-legitimacy verification pass (registry/typosquat check per the `09-RESEARCH.md` precedent) before the first import — the human re-approval checkpoint itself is what's pre-cleared, not the technical verification step.

---

## Feature scope

| Option | Description | Selected |
|--------|-------------|----------|
| Multivariate: weather + past ampacity (Recommended) | Feeds wind/temp/solar alongside lagged dlr_amps. | ✓ |
| Autoregressive only (past dlr_amps) | Mirrors naive/EWM's own inputs. | |
| You decide | Let the researcher/planner pick based on what the backtest shows. | |

**User's choice:** Multivariate: weather + past ampacity (Recommended).

Follow-up: per-location vs. shared model.

| Option | Description | Selected |
|--------|-------------|----------|
| Per-location models (Recommended) | Mirrors existing per-city pattern (STATIC_RATINGS, ANOMALY_CONTROL_LIMIT_K_BY_LOCATION). | ✓ |
| One shared model across all locations | Simpler to build once; city as a categorical feature instead. | |
| You decide | Let the researcher/planner pick based on how much data each location's backfill yields. | |

**User's choice:** Per-location models (Recommended).
**Notes:** Model inputs are multivariate (real weather + lagged ampacity), trained per-location following this codebase's existing per-city config pattern. Exact lag window and per-location model-selection mechanism left to research/planning.

---

## Validation record format

| Option | Description | Selected |
|--------|-------------|----------|
| New docs/data-science/decisions/ doc (Recommended) | Matches the project's existing ADR-style convention. | ✓ |
| New spec update (C9-ampacity-forecasting.md) | Would fix C9's staleness but conflates "what C9 is" with "how this model was validated." | |
| Just the plan's SUMMARY.md | Lowest overhead, lives in .planning/ only. | |

**User's choice:** New docs/data-science/decisions/ doc (Recommended).

Follow-up: also correct the stale C9 spec?

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, correct C9 spec too (Recommended) | Same kind of documentation-debt correction as v1.1's PRD.md §7.1 ratification. | ✓ |
| No, leave C9 spec as-is for now | Keep this phase strictly scoped to the new decision doc. | |

**User's choice:** Yes, correct C9 spec too (Recommended).
**Notes:** New ADR-style doc under docs/data-science/decisions/ for the validation record, plus in-place correction of C9-ampacity-forecasting.md's stale "no model code exists" claim.

---

## Claude's Discretion

- Exact model class within "regression or neural network."
- Exact per-location granularity (per-city vs. per-corridor) and the model-selection mechanism inside `forecast_ampacity`.
- Exact feature-engineering details (lag window, additional variables, missing-value handling).
- Exact filename/structure of the new validation decision doc.

## Deferred Ideas

None — discussion stayed within Phase 1 scope.
