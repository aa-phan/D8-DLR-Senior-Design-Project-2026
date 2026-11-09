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

- **Format and transport:** a Postgres table, `public.city_rating`, read through Supabase REST (Phase 6), contract [`rest-api.md`](../../integration/rest-api.md), readable when the owner applies Phase 6's migration. A Python 3.7+ standard-library example is `docs/integration/examples/read_ratings.py`.
- **Interpreter question (D-11):** the example assumes Python 3.7 or newer with TLS 1.2. Power Systems is asked to print `sys.version` and `ssl.OPENSSL_VERSION` inside PSS/E's Python and to run the example once; the question is sent along with the example. A Python 2.7 answer becomes a follow-up, not a blocker.
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

## Day-ahead forecast (2026-11)

A second, separate value is now stored for each city: a 24-hour-ahead forecast for each 00, 06, 12 and 18 UTC hour, with a 5-95% band, labelled `day-ahead-24h; engineering-selection; not-validated`. It is information only: not validated, no safety role, and it never sets or checks the hourly rating or the 60-minute forecast above. How to read it is in [`rest-api.md`](../../integration/rest-api.md) and the columns, the issue rule and the band rule are in [`day_ahead_forecast_v1.md`](../schema/day_ahead_forecast_v1.md); both become readable when the owner applies the day-ahead expose migration.

### Which target hour to use

Each city has four targets a day, at 00, 06, 12 and 18 UTC. For a next-day study, pick the target closest to the study hour, among the targets that are already published. A value appears only about 18 hours before its target, so at any moment each city has at most three upcoming targets and a study hour further away than that has no value yet. There is no interpolation by Data Science: no value is published for an hour in between, so interpolating is the study's own choice and should be stated as such. The Central times of the four targets:

| Target | Central, November to March (CST, UTC-6) | Central, March to November (CDT, UTC-5) |
|---|---|---|
| 00:00 UTC | 18:00 (previous day) | 19:00 (previous day) |
| 06:00 UTC | 00:00 | 01:00 |
| 12:00 UTC | 06:00 | 07:00 |
| 18:00 UTC | 12:00 | 13:00 |

US clocks went back on 1 November 2026, so the CST column applies until March. El Paso keeps Mountain time, one hour earlier than these Central times. A study that needs one hour for all four cities should state the hour in UTC.

### Read the band, not only the point

Take `forecast_ci_lower_amps` and `forecast_ci_upper_amps` as well as `forecast_amps`: the band is the 5-95% empirical band of how far the forecast was off on past data, and a study should know how far off the point value can be. The lower edge is the cautious choice for a screening study. `band_source` says how the band was measured (`test-split` at launch, `live-rolling` once enough live pairs exist) and `band_n` how many past cases it rests on; the width can change when `band_source` changes.

### What it is not

The value has no safety role and is not validated. It is an engineering selection by the owner, labelled `day-ahead-24h; engineering-selection; not-validated` on every row. It is not the live rating: it never sets or checks the hourly rating or the 60-minute forecast, and a study that needs a rating it can rely on uses the live rating and the static rating, not this.

### Empty or late targets

A target the pipeline could not compute stays empty: no substitute value is published. A target more than 18 hours away is not late, it is only not yet due: it is simply absent until about 18 hours before, and `day_ahead_status` will not flag it. If a target within 18 hours is not in the list, read `day_ahead_status`: `is_late` is true when a target due within the next 12 hours has no value, and `missing_targets` names them. Wait for the next hourly run or ask the Data Science owner; never borrow the value of another city or another hour. A target that has passed is never filled afterwards.

### Running the example and converting to megawatts

`python read_ratings.py` (with `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` set as in the example's header) prints the live ratings first; its third part prints the upcoming day-ahead targets for every city, with the band and the lead in minutes, and one status line per city. The columns and the rules are in [`rest-api.md`](../../integration/rest-api.md). The values are in amperes only: for megawatts use MW = sqrt(3) x kV x A x power factor / 1000, with the line voltage and power factor of the rating rows, as described in [`day_ahead_forecast_v1.md`](../schema/day_ahead_forecast_v1.md).

---
*Captured: 2026-09-24, during Track 2 (ML Model Development) Phase 1 discussion — not itself part
of that phase's scope, recorded as a standalone note per the user's request.*
