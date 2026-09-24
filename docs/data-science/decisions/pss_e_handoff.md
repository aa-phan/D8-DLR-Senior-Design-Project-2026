# DS → Power Systems (PSS/E) Handoff — Informal Note

**Status:** Informal working understanding — not yet confirmed with the Power Systems
sub-team, and not a ratified interface contract. Captured here so the understanding survives
between sessions rather than living only in conversation. A formal interface contract
(file format, cadence, exact fields) is explicitly deferred — see "What's still undefined" below.

**Purpose:** Record what the DS subsystem believes it hands off to Power Systems and why, based
on the two places this project's own documents describe the connection
(`docs/data-science/PRD.md` §3, `docs/System Design Report.md` §3.1), cross-checked against what
`backend/ampacity_forecast.py` actually produces today.

## The understanding

The handoff is a **predicted ampacity** value — not just the current, real-time computed
rating. Power Systems takes that prediction and evaluates it against grid conditions (load flow,
N-1 contingency screening) to determine whether the grid can actually operate at that capacity
without violating thermal or voltage limits. The feasibility judgment is entirely Power Systems'
side of the boundary; DS's job stops at producing an honest predicted number with an honest
uncertainty range.

This is stated fairly directly in two existing documents:

- `docs/data-science/PRD.md` §3 (Users & Consumers): *"Power Systems sub-team (PSS/E) —
  Ampacity values (and their MW equivalent) to inject into load-flow and N-1 contingency
  screening."*
- `docs/System Design Report.md` §3.1: *"...allows the data science pipeline to automate the
  injection of **forecasted** ampacity limits directly into the load flow environment to verify
  real-time grid stability."* (emphasis added — this is the line that specifically points at the
  forecast, not just the current rating.)

## What DS actually produces today that would feed this

`backend/ampacity_forecast.py::forecast_ampacity` → `forecast_columns()` produces exactly these
four `PIPELINE_SCHEMA` columns per pipeline row:

| Column | Meaning |
|---|---|
| `forecast_horizon_min` | How far ahead the prediction looks (60 min by default, `config.FORECAST_HORIZON_MINUTES`) |
| `forecast_amps` | The point forecast — predicted ampacity, in Amps |
| `forecast_ci_lower_amps` / `forecast_ci_upper_amps` | An empirical confidence band around the point forecast (from out-of-sample walk-forward backtest residuals) |

**The confidence band likely matters to Power Systems, not just the point value** — a feasibility
check against grid conditions presumably wants to know the uncertainty range PSS/E should assume
margin for, not only a single number. This is worth keeping in mind if/when Track 2's Phase 1
(ML-backed forecasting model, replacing today's naive/EWM methods) or a future interface-contract
discussion narrows down exactly which fields get handed off.

Separately, `backend/ercot_dlr_merger.py::amps_to_mw` already converts an Amps value to the "MW
equivalent" PRD.md's consumer table mentions (`P = √3 × V × I × PF`, using
`config.LINE_VOLTAGE_KV` = 345 kV and `config.POWER_FACTOR` = 0.95) — this conversion exists as
its own step, separate from the forecast itself.

## What's still undefined

No document in this repo — searched across `docs/`, `.planning/`, and `backend/` — specifies
*how* this injection actually happens. Specifically undefined:

- File format / transport (CSV hand-off? PSS/E's Python API pulling from a shared archive?
  something else?) — PSS/E's Python API is cited in the System Design Report as the reason PSS/E
  was chosen over PowerWorld, which makes it the most likely intended mechanism, but this is not
  written down as a decision anywhere.
- Cadence (per pipeline run? per hour? on-demand?).
- Whether Power Systems wants Amps, MW, or both, and whether they want the confidence band or
  just the point forecast.
- Granularity (per-corridor, per-station, or per-city).

**This is deliberately not resolved here.** Defining the actual contract requires a conversation
with the Power Systems sub-team, not a unilateral DS-side decision — flag it again when Track 1
(Pipeline Integration) or an actual cross-team sync on this happens.

---
*Captured: 2026-09-24, during Track 2 (ML Model Development) Phase 1 discussion — not itself part
of that phase's scope, recorded as a standalone note per the user's request.*
