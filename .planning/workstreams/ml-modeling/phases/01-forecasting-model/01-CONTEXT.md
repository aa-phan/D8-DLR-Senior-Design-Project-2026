# Phase 1: Forecasting Model - Context

**Gathered:** 2026-09-23
**Status:** Ready for planning

<domain>
## Phase Boundary

`ampacity_forecast.forecast_ampacity` gains a new, actual trained-model forecasting method
(regression or neural network) alongside the existing `"naive"` and `"ewm"` Tier-1 methods,
dropped in behind the exact same function signature and `PIPELINE_SCHEMA` output columns so no
caller (Track 1's pipeline wiring, `DLRSafetyMonitor`) needs to change. The model is trained and
evaluated against real historical data — not synthetic fixtures — and a written record documents
its measured accuracy against the naive/EWM baselines (FCST-01, FCST-02).

Out of scope: anomaly detection (Phase 2 of this workstream), pipeline orchestration/scheduling
(Track 1), corridor geometry (Track 3), any change to the fail-safe contract or the
`forecast_ampacity`/`ForecastResult` public signature.

</domain>

<decisions>
## Implementation Decisions

### Model approach
- **D-01:** Regression vs. neural network is fully open — the researcher/planner decides based
  on measured out-of-sample backtested accuracy on the actual assembled real-data training
  series, with **no default lean toward either approach**. Do not treat "regression" as a safer
  default; make the call on evidence once real data is assembled.

### New dependency
- **D-02:** A new ML dependency is **pre-approved** — the package-legitimacy review this
  project's `09-RESEARCH.md` precedent would otherwise require as a human checkpoint is not
  needed as a blocking gate here. — **Reversibility:** reversible — approval of a class of
  dependency, not a specific pin; a specific chosen library can still be swapped before it's
  used anywhere else.
- **D-03:** The approval is **not scoped to scikit-learn specifically** — the researcher/planner
  has latitude to pick whichever well-established scientific-Python ML library best fits the
  chosen model approach (e.g. scikit-learn, statsmodels, xgboost), still subject to this
  project's standard package-legitimacy verification pass (registry/typosquat check) before the
  first import lands — that verification step itself is not skipped, only the human
  re-approval checkpoint on top of it.

### Feature scope
- **D-04:** Model inputs are **multivariate**, not autoregressive-only: feed the real weather
  variables already flowing through the pipeline (wind speed, temperature, solar irradiance —
  the same Open-Meteo-backfill-derived series used to compute the training `dlr_amps` target)
  alongside lagged `dlr_amps`, not just past ampacity values the way naive/EWM do.
- **D-05:** Train **per-location models** (per corridor, or per city — researcher's call on
  exact granularity), not one shared model across all four cities/both corridors. This matches
  the existing per-location pattern already established in this codebase
  (`config.STATIC_RATINGS`, `config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`,
  `config.RATING_BOUNDS_BY_LOCATION`) and avoids one corridor's climate signal (Austin↔Corpus
  Christi's coastal/humid pattern vs. Midland↔El Paso's arid West Texas pattern) diluting the
  other's. The exact mechanism for selecting/loading the right location's fitted model inside
  `forecast_ampacity` (which today takes only a `history` frame, no explicit location parameter)
  is left to research/planning to design — it must not require a signature change per the
  locked interface contract in ROADMAP.md.

### Validation record
- **D-06:** FCST-02's written validation record is a **new file under
  `docs/data-science/decisions/`** (matching this project's existing ADR-style convention —
  `data_provider.md`, `geographic_scope.md`), not a spec update and not only the plan's own
  `SUMMARY.md`. Name it descriptively for the model built (e.g.
  `docs/data-science/decisions/forecasting_model.md`) — exact filename is the planner's call.
- **D-07:** This phase also **corrects the stale `docs/data-science/specs/C9-ampacity-forecasting.md`**
  spec file alongside writing the new decision doc: its "Current Implementation" section and
  Status line still say "None. No model code... exists anywhere in the repo," which has been
  false since v1.0 Phase 4 shipped the naive/EWM methods and becomes even more false once this
  phase lands a trained model. Update it to reflect what naive/EWM already are and what this
  phase adds — same kind of documentation-debt correction as v1.1's `PRD.md` §7.1 ratification.

### Claude's Discretion
- Exact model class within "regression or neural network" (e.g. which specific
  scikit-learn/statsmodels/xgboost estimator).
- Exact per-location granularity (per-city vs. per-corridor) and the mechanism for selecting the
  right location's fitted model inside `forecast_ampacity` without a signature change.
- Exact feature engineering details: lag window size, which weather variables beyond
  wind/temp/solar (if any), how missing/null weather values are handled going into the model.
- Exact filename and structure of the new `docs/data-science/decisions/` validation record.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Interface contracts (locked, from ROADMAP.md — do not renegotiate)
- `.planning/workstreams/ml-modeling/ROADMAP.md` — Phase 1 success criteria and the two
  non-renegotiable interface contracts (`FORECAST_METHODS` extension, `ForecastResult`/
  `PIPELINE_SCHEMA` columns, `backtest_residuals` reuse).
- `.planning/workstreams/ml-modeling/REQUIREMENTS.md` — FCST-01, FCST-02 full text and Out of
  Scope table.

### Existing forecasting module and spec
- `backend/ampacity_forecast.py` — the module this phase extends. Read in full: `FORECAST_METHODS`,
  `ForecastResult`, `_extract_series`, `_point_forecast`, `backtest_residuals`,
  `forecast_ampacity`, `forecast_columns`. The new method must reuse `backtest_residuals`'
  expanding-window walk-forward machinery, not a parallel band implementation.
- `docs/data-science/specs/C9-ampacity-forecasting.md` — currently stale (says no model code
  exists); this phase corrects it per D-07. Its "Open Questions" section already independently
  raised the regression-vs-NN question this discussion resolved as open discretion (D-01).

### Real-data sourcing (already resolved in ROADMAP.md, not re-litigated here)
- `.planning/workstreams/ml-modeling/ROADMAP.md` Overview — "Real training/validation data is
  less scarce than the live archive alone suggests" section: use Open-Meteo Archive API backfill
  (`backend/open_meteo_provider.py`, WX-04) run through `backend/thermal_model.py::ieee738_ampacity`
  to derive a real `dlr_amps` series, NOT the live (currently empty) `historical_archive.py` CSV.
- `backend/historical_archive.py` — `build_archive_row`, `read_history` — the archive frame
  shape `forecast_ampacity` consumes.
- `backend/config.py` — `CITY_COORDINATES`, `CORRIDOR_ENDPOINTS`, `STATIC_RATINGS`,
  `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`, `RATING_BOUNDS_BY_LOCATION` — the existing per-location
  pattern D-05 follows.

### Dependency precedent
- `.planning/workstreams/multi-provider-weather/milestones/v1.1-phases/09-tceq-cams-integration/09-RESEARCH.md` —
  the package-legitimacy review precedent referenced in D-02/D-03 (see its `beautifulsoup4`
  entries for the registry-check format to reuse, even though the human-approval gate itself is
  pre-cleared here).
- `.planning/codebase/STACK.md` — current stack (pandas/numpy/scipy only, no ML library) —
  stale as of 2026-09-02, does not yet reflect `beautifulsoup4` from v1.1 Phase 9; re-verify
  actual installed packages rather than trusting this file's exact version list.

### Prior art
- `docs/Prior Art Report.md` — the IEEE Trans. Smart Grid MILP planning citation referenced by
  both `ROADMAP.md`'s FCST-01 text and the C9 spec's header as the origin of "regression or
  neural network" framing.
- `docs/System Design Report.md` §3.1 — "thermal limit forecasting via regression or neural
  network models" — the graded deliverable's own framing of this component; do not edit this
  file (course deliverable, out of scope), but its wording is why the roadmap phrases the model
  choice as it does.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/ampacity_forecast.py::backtest_residuals` — expanding-window walk-forward backtest
  already implemented and tested; the new method must call this (or an equivalent path reusing
  its exclusivity guarantee), not hand-roll a second backtest.
- `backend/thermal_model.py::ieee738_ampacity` — the only path from weather to `dlr_amps`;
  needed to derive the real training/validation target series from Open-Meteo backfill.
- `backend/open_meteo_provider.py` — already-shipped real historical weather source (WX-04,
  reaches back to 1940), the training data source per ROADMAP.md.
- `backend/ercot_data_retriever.py::pull_ercot_data` — real historical ERCOT load, relevant if
  load ends up being a useful additional feature (not required by D-04, which specifies weather
  + past ampacity, but available if research finds it improves accuracy).

### Established Patterns
- Per-location dicts keyed by city (`config.STATIC_RATINGS`, `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`,
  `RATING_BOUNDS_BY_LOCATION`) — D-05's per-location models should follow this same keying
  convention rather than inventing a new location-identification scheme.
- `ForecastResult`'s float-wrapping-at-assignment discipline and `forecast_columns()`'s
  "only place a ForecastResult becomes pipeline output" rule — the new method must not create a
  second path to `PIPELINE_SCHEMA` columns.
- `docs/data-science/decisions/*.md` ADR-style convention (status line, evidence, ratified/open
  outcome) — follow this shape for D-06's new validation record, per `data_provider.md` and
  `geographic_scope.md`'s existing format.

### Integration Points
- `FORECAST_METHODS` tuple is the single source of valid method names — the new method's name
  is added here; `_point_forecast` and `forecast_ampacity` both validate against it.
- `forecast_ampacity`'s `history: pd.DataFrame` parameter is the only per-call context available
  today — D-05's per-location model selection must work from what's derivable out of `history`
  (or a location identifier the caller already has) without adding a new parameter.

</code_context>

<specifics>
## Specific Ideas

No specific implementation examples given during discussion — the four decisions above (D-01
through D-07) are the vision-level calls; exact estimator class, feature-engineering details,
and per-location model-selection mechanism are explicitly left to research/planning (see
"Claude's Discretion").

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 1 scope. (Phase 2 — Anomaly Detection Model — is a
separate, independent phase in this same workstream; not discussed here.)

</deferred>

---

*Phase: 1-Forecasting Model*
*Context gathered: 2026-09-23*
