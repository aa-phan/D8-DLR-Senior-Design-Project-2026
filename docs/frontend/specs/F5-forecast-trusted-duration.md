<!-- generated-by: gsd-doc-writer -->
# F5 — Forecast & Trusted-Duration View

**Phase:** 3 (Predictive & Safety Views) · **Effort:** M · **Status:** Not started — externally blocked on DS contract extension and on the definition of "trusted duration".

**Responsibility:** Show forecast future ratings with their uncertainty (WBS 4.1.4 "Implement forecasting display panel"; SW-F7), and the trusted duration of the current dynamic limit (SW-F5) — how long the operator may rely on the number before it must be refreshed (`Project Definition.md` I/O table; `System Design Report.md` §3.3 "refresh window").

## Current Implementation

None. DS's producer exists but is not wired into the pipeline's export: `backend/ampacity_forecast.py::forecast_ampacity` (DS C9) returns a `ForecastResult` (`horizon_min`, `amps`, `ci_lower_amps`, `ci_upper_amps`, `n_observations`, `method`, `n_residuals`) via methods `naive`, `ewm`, `ml`; `forecast_columns()` maps it onto four `PIPELINE_SCHEMA` v2 columns. Per `docs/data-science/PROJECT-STATUS.md`, forecasting is never called from `run_pipeline` today, so no CSV output contains forecast columns.

## Interface & Data Contract

Inputs the view needs (names are DS's, from `PIPELINE_SCHEMA` v2 and C9; they are **not in the v1 export** — PRD §8, G3):

| Display | Column | Unit |
|---|---|---|
| Forecast horizon | `forecast_horizon_min` | min (default 60, `config.FORECAST_HORIZON_MINUTES`) |
| Forecast point value | `forecast_amps` | A |
| Forecast band | `forecast_ci_lower_amps`, `forecast_ci_upper_amps` | A |
| Trusted duration | **no column** (PRD §8, G4; OD-3) | undefined (s in `Project Definition.md`) |

Behavior rules:

- **Cold start is not a forecast.** DS C9 returns no forecast (and emits no forecast columns) when history is below `min_rows` (default `FORECAST_MIN_HISTORY_ROWS = 12`). The view shows "forecast unavailable", never zeros or a flat line that could be mistaken for one.
- Show the band, not just the point value — the confidence band comes from DS's walk-forward backtest residuals and is what DS's own PSS/E handoff note says consumers will want (`docs/data-science/decisions/pss_e_handoff.md`).
- Label the forecast method and horizon in the UI (`naive`, `ewm`, `ml`) if DS exports them; DS C9's own record states the ML candidate does not beat the naive baseline at the 60-minute horizon, so a forecast should not be presented as more authoritative than it is.
- Trusted duration is shown as a value with an expiry ("valid until …") once defined; when it expires or the feed is stale, the dynamic limit is shown as expired and the static rating is in effect (SW-NF1).
- The forecast shares F2's chart wrapper with F4 for consistent axes, units and null handling. Whether it overlays F4's chart or is a separate panel is a layout choice for F2 (WBS lists them as separate items).
- No forecast math in the UI (SW-NF4).

## Blocked by

**F1** and **F2** (internal). **External:** DS exports the forecast columns (G3) and the team defines trusted duration (OD-3, G4). The panel can be laid out and built against a **mock** fixture extension with agreed column names while waiting.

## Blocks

**F8** — the end-to-end test checks forecast display against pipeline output; the "refresh window" check also needs trusted duration.

## Parallel-safe with

**F3**, **F4**, **F6** (after F1 and F2). F4 shares the chart wrapper (agree it in F2).

## Known Issues

- **Trusted duration is contradictory in the sources.** `Project Definition.md` gives 10 or 20 **seconds**; DS cadence is minutes–hours and forecast horizon 60 minutes; DS C9 says no dashboard requirement for horizon has been specified (OD-3).
- **Forecast columns not exported**, and cold-start omits them entirely (DS C9); the view must handle both "no columns" and "columns present".
- **Model artifacts for `ml` are gitignored** (`/data/models/`); a clean checkout has none and `method="ml"` raises rather than degrading (DS C9). Not the UI's problem to hide, but a source of "forecast unavailable". Model artifacts are per city (`forecast_{city}.joblib`); existing corridor-named artifacts are legacy and not loaded, and the per-city refit has not been run (`point_scope.md`).
- **A separate shadow-forecast stream exists** (`data/shadow/predictions/{CITY}.jsonl`, one file per city, `schema_version: 3`, records carry `city`) with a different shape and fields (e.g. `valid_time`, `horizon_minutes`, `fallback_used`); whether the dashboard reads it is OD-12 and DS's call. The corridor-named files (`AUSTIN_CORPUS_CHRISTI.jsonl`, `MIDLAND_EL_PASO.jsonl`; v1 flat and v2) are legacy and must be tolerated, not mixed into a city's series. Per-city logs start empty, and until the per-city models are refit the ML shadow candidates report `status="unavailable"` with a named reason, so expect sparse or missing candidates (`point_scope.md`).
- **Forecast horizon the dashboard needs is unspecified** (DS C9 Open Questions).

## Acceptance Criteria

- Against a mock fixture extension with the four v2 forecast columns, the panel shows the point forecast, the band, and the horizon with units (A, min); band edges equal the column values.
- Against the unmodified v1 fixture (no forecast columns), the panel shows an explicit "forecast unavailable" state and nothing that resembles a number.
- A row with forecast values and a cold-start row (no forecast columns) are handled in the same series without error.
- Trusted duration is displayed per its agreed definition (OD-3) and is visibly expired when the feed's age exceeds it; the expired state degrades the headline limit via F1's limit-basis.
- The forecast method label is displayed if exported.
- The panel follows `System Design Report.md` §3.3: after F8 wiring, forecast values on screen equal pipeline output, and a weather change propagates within the trusted-duration refresh window.
- No forecast field is computed or smoothed in the browser.

## Open Questions

- OD-3 (trusted duration), OD-12 (shadow-forecast stream), OD-2 (refresh cadence).
- If the v3 shadow stream is shown, the shape of its per-candidate `bundle` and `input_provenance` objects under the per-city model is not stated in the scope contract (the corridor-era `corridor_bundle_ampacity_amps`, `bundle_bottleneck_city` and `per_city_ampacity_amps` are among the things it removes). Do not code against the v2 shapes; wait for DS to document v3.
- The forecast shown is per city. Nothing is reduced across cities.
- What forecast horizon(s) should the panel show — a single horizon (DS default 60 minutes) or a range of lead times?
- Should forecast/actual divergence be shown (C10 uses forecast residuals as an anomaly signal)? Not required by the source documents.
