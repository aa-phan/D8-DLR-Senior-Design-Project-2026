# DS → Power Systems (PSS/E) Handoff — Informal Note

**Status:** Informal working understanding — not yet confirmed with the Power Systems
sub-team, and not a ratified interface contract. Captured here so the understanding survives
between sessions rather than living only in conversation. A formal interface contract
(file format, cadence, exact fields) is explicitly deferred — see "Still open with Power Systems" below.

The storage and handoff format are now fixed by the production pipeline; see [`../schema/city_rating_v1.md`](../schema/city_rating_v1.md).

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

## What the production store fixes (2026-10)

The production pipeline (production-pipeline Phase 4) stores every city's hourly result in one place. The contract is [`city_rating_v1.md`](../schema/city_rating_v1.md). What it settles for the points this note used to list as undefined:

- **Format and transport:** a Postgres table, `public.city_rating`, read through Supabase REST from Phase 6 (a Python stdlib example is planned there). Until Phase 6 delivers the read grant, no consumer has access.
- **Cadence:** hourly (OD-1), once Phase 5's scheduled runner is live; the latest row of a city is expected to be no older than 90 minutes.
- **Amps, MW and the forecast band:** all stored on every row: `rating_amps`, `rating_mw`, `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, `forecast_horizon_min`. The forecast fields are empty while the forecast is in cold start.
- **Granularity:** one independent row per city per hour. Rows of different cities are never combined.
- **Provenance:** `config_version`, `config_fingerprint`, `forecast_model_sha256` and `anomaly_model_sha256` on every row (DB-06). Within one city, a change in these between rows marks a configuration or model change, such as Phase 7's per-city conductors; PSS/E studies should not splice values across it without noting it.

All values are provisional (OD-5) until Phase 7's re-validation go (REVAL-01).

## Still open with Power Systems

This is deliberately not resolved here; it needs a conversation with the Power Systems sub-team, not a unilateral DS-side decision.

- Which of the stored fields PSS/E consumes (point forecast only, or also the band, MW or Amps), and how the injection runs inside PSS/E.
- The per-city conductor values Power Systems is to confirm (Phase 7, COND-01). Today one Drake conductor configuration is used for every city, with assumed subconductor counts and line bearings.
- The provisional caveat: every row stays provisional (OD-5) until Phase 7's go (REVAL-01) lifts the label.

---
*Captured: 2026-09-24, during Track 2 (ML Model Development) Phase 1 discussion — not itself part
of that phase's scope, recorded as a standalone note per the user's request.*
