# Phase 4: Predictive - Context

**Gathered:** 2026-09-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 4 delivers two learned layers on top of Phase 3's safety-validated, physics-based pipeline, per ROADMAP.md's Success Criteria:

1. **Ampacity forecasting (C9, DS-F11):** given historical weather and computed ampacity, produce a forecasted ampacity at a defined horizon ahead of real time, with a confidence/uncertainty band, extending `PIPELINE_SCHEMA` additively.
2. **Learned anomaly detection (C10, DS-F12):** a learned signal that augments — never replaces — C7's fallback path, triggering the same `{status, rating, fallback, alerts}` result shape when conditions look anomalous, and falling back to the static rating under synthetic/injected anomalous conditions.

Both must be built on a historical archive that, per direct codebase verification this session, does not yet exist — building it is now confirmed as Phase 4 Wave 0 scope, not an assumed precondition.

</domain>

<decisions>
## Implementation Decisions

### Forecast horizon & target (C9)
- **D-01:** Forecast horizon is **1 hour ahead**, matching the pipeline's existing hourly/sub-hourly cadence and keeping validation tractable against a near-zero starting historical archive. — **Reversibility:** reversible — a config-level horizon constant.
- **D-02:** C9 forecasts **ampacity directly** (naive/EWM trend on the historical `dlr_amps` series), not the underlying weather variables re-run through IEEE 738. Simpler, fewer moving parts, and the confidence band applies directly to the value that matters. — **Reversibility:** reversible — an internal modeling choice behind the same forecast output columns.
- **D-03:** The confidence/uncertainty band is computed via **empirical residual quantiles** from a walk-forward backtest of the naive/EWM forecast (e.g. 5th/95th percentile of residuals), not a normal-distribution (mean ± k·std) band. No new dependency; matches research's Tier 1 recommendation. — **Reversibility:** reversible.

### C9→C10 coupling & wiring (C10)
- **D-04:** C10's primary anomaly signal is **|actual − C9 forecast| compared against C9's own empirical residual band**, with a **rolling-baseline (mean ± k·std) fallback** for cold-start conditions where no forecast is available yet. Not a fully independent detector — reuses the "what's normal" computation already built for C9. — **Reversibility:** reversible — an internal signal-selection choice inside the detector.
- **D-05:** C10 is wired into `DLRSafetyMonitor` as a **new gate G6, evaluated after G5, via constructor injection** (`anomaly_detector=None` by default), mirroring the existing `conductor`/`rating_bounds` injection pattern. It resolves through the existing `_fallback` helper — never a second, competing result shape. `None` = C10 disabled, G1–G5 unchanged. — **Reversibility:** reversible — additive gate behind a None-default constructor parameter; existing call sites (`corridor_discretization.py::rate_corridor`) are unaffected until a detector is actually passed in.
- **D-06:** The anomaly control limit is **conservative — a wide band, favoring fewer false trips** over higher sensitivity. Given the codebase's existing fail-safe philosophy, an anomaly detector that trips too eagerly erodes trust faster than one that occasionally misses a subtle anomaly (C7's deterministic gates G1–G5 already catch the clear-cut failure modes). The exact multiplier is a named, centralized `config.py` constant (matching `config.DELTA_FRACTION`'s convention), **per-location** per research's Pitfall 5 (a single global band already caused a real bug in Phase 3 — `RATING_BOUNDS` vs. `RATING_BOUNDS_BY_LOCATION`). — **Reversibility:** reversible — a tunable constant.

### Historical archive (Wave 0 precondition for C9/C10)
- **D-07:** The Roadmap's recommended background archive job was confirmed absent from the repo (direct grep this session found no `archive`/`historical` implementation). Building it is **Wave 0 of Phase 4's plan**, not an assumed-already-done precondition. — **Reversibility:** one-way once C9/C10 depend on its schema shape — **rationale:** once the forecast/anomaly modules are built against a given archive row schema, changing that schema later requires migrating or discarding accumulated history; get the row shape right in Wave 0.
- **D-08:** The archive persists at **per-corridor granularity** — one row per corridor per run (the corridor's minimum/bottleneck ampacity + its weather), matching where `DLRSafetyMonitor` is already instantiated (`corridor_discretization.py::rate_corridor`, one monitor per corridor) and where the fallback decision actually happens. Not per-station/point. — **Reversibility:** costly — **rationale:** switching granularity later means re-deriving or discarding accumulated per-corridor history; per-point granularity could theoretically be added alongside later without breaking per-corridor consumers, but was explicitly not chosen for this phase.
- **D-09:** Storage is **append-only CSV, unbounded retention for now** — matches the existing `export_results` CSV convention, zero new dependency, adequate at expected near-term volume (hundreds-to-low-thousands rows/month per research). No rolling retention window this phase. — **Reversibility:** reversible — research explicitly flags Parquet/SQLite migration as a later, non-blocking optimization if the flat file becomes slow.

### Tier scope for this phase
- **D-10:** **Tier 1 only this phase** — the pandas-only naive/EWM forecast + empirical residual band (C9), and the rolling-baseline/forecast-residual anomaly detector (C10). Tier 2 (scikit-learn `GradientBoostingRegressor(loss="quantile")`) is explicitly **not attempted** this phase — there is no data yet to justify or validate it against, and it avoids the `checkpoint:human-verify` gate research flagged for scikit-learn/statsmodels (SUS verdict, likely a metadata-gap false positive, but the checkpoint still applies per protocol). No Tier 2 hook/interface is required to be pre-built either — the planner may leave a natural extension point but should not spend scope defining an unused interface. — **Reversibility:** reversible — Tier 2 is purely additive later, nothing about Tier 1 needs to be torn out first.
- **D-11:** Add a **`requirements.txt`** as part of this phase's scope, pinning the already-installed `pandas`/`numpy`/`scipy`/`pytest` versions (verified this session via `.venv` pip list) — supports DS-NF2 (reproducibility), already a locked non-functional requirement, and replaces the current prose-only (`README.md`/docstring) dependency documentation. — **Reversibility:** reversible.

### Claude's Discretion
- Exact `config.py` constant names/values for the anomaly control-limit multiplier (D-06) and forecast horizon (D-01) — standard config-centralization choice, not user-facing.
- Exact archive row schema (column names/order within `historical_archive.py`) beyond the "per-corridor, includes weather + dlr_amps + static_rating + status" shape already described in RESEARCH.md's Pattern 3 — planner/implementer detail.
- Whether `PIPELINE_SCHEMA_VERSION` starts at 2 (per RESEARCH.md's Pattern 1 sketch) — not discussed, left to planner as the natural next version number.
- Exact walk-forward backtest window size for computing D-03's empirical residual quantiles — not discussed, left to planner given real archive volume will be near-zero at first (the backtest can only use what accumulates).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### This phase's own artifacts (mandatory)
- `.planning/phases/04-predictive/04-RESEARCH.md` — full research: architecture patterns (Pattern 1 additive schema, Pattern 2 gate injection, Pattern 3 archive), pitfalls (esp. Pitfall 1 near-zero data, Pitfall 5 per-location thresholds), validation architecture, package legitimacy audit (scikit-learn/statsmodels SUS verdicts)

### Component specs
- `docs/data-science/specs/C9-ampacity-forecasting.md` — C9 spec; D-01/D-02/D-03 directly answer this spec's open questions on horizon and target
- `docs/data-science/specs/C10-anomaly-detection.md` — C10 spec; D-04/D-05/D-06 directly answer this spec's open questions on coupling and wiring mechanism
- `docs/data-science/specs/C7-safety-monitor.md` — safety monitor spec C10's gate injection (D-05) must respect

### Existing code C9/C10 build on (do not replace)
- `backend/DLRSafetyMonitor.py` — `run_check`/`_fallback` contract, existing `conductor`/`rating_bounds` constructor-injection pattern D-05 extends
- `backend/units_def.py` — `PIPELINE_SCHEMA` (lines ~324-375), `validate_pipeline_row`; D-11's additive extension pattern (Pattern 1 in RESEARCH.md) applies here
- `backend/corridor_discretization.py` — `rate_corridor`, existing `DLRSafetyMonitor(...)` injection call site (lines ~535-539) D-08's per-corridor granularity aligns with
- `backend/config.py` — `STATIC_RATINGS`, `RATING_BOUNDS_BY_LOCATION`, `DELTA_FRACTION` centralization convention D-06's per-location control-limit constant should follow
- `backend/thermal_model.py` — `ieee738_ampacity`; note its `np.ndarray`-return-type trap (RESEARCH.md Pitfall 2) applies to any new code deriving features from computed ampacity

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — DS-F11, DS-F12 (this phase's requirements)
- `.planning/ROADMAP.md` — Phase 4 Success Criteria (the 4 criteria this phase must satisfy)
- `.planning/phases/03-safety-spatial/03-PATTERNS.md` — documents the exact `RATING_BOUNDS`-mismatch historical bug D-06 explicitly avoids repeating

### Prior phase context (for continuity, not re-decided)
- `.planning/phases/03-safety-spatial/03-CONTEXT.md` — D-06 there deferred the full multi-provider weather composition (`docs/data-science/decisions/data_provider.md`) as a natural Phase 4 candidate given overlap with C9/C10's historical-backfill needs; not selected for discussion this session — remains deferred (see Deferred Ideas below)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/DLRSafetyMonitor.py::_fallback` — the single fallback helper C10 (G6) must resolve through, never a second result shape
- `backend/corridor_discretization.py::rate_corridor` — existing per-corridor `DLRSafetyMonitor(...)` construction call site; D-05's `anomaly_detector` injection and D-08's per-corridor archive write both hook in here
- `backend/units_def.py::PIPELINE_SCHEMA` / `validate_pipeline_row` — additive extension target for forecast/anomaly output columns (D-11's `requirements.txt` work is separate/orthogonal to this)
- `backend/config.py` — existing per-location constant convention (`RATING_BOUNDS_BY_LOCATION`, `STATIC_RATINGS`) D-06's anomaly threshold constants should follow exactly

### Established Patterns
- Fail-safe-by-default (DS-NF5): every prior gate (G1–G5) resolves toward the static rating on any inability to trust a value — D-05/D-06 extend this same pattern to a learned signal, not a new philosophy
- One call site, centralized config (C1 discipline): `config.py`'s own docstring warns against literals drifting out of agreement across modules — D-06's per-location constants and the archive's single `append_observation` call site (Pattern 3, RESEARCH.md) both follow this

### Integration Points
- `historical_archive.py` (new, D-07) ← written from `corridor_discretization.py::rate_corridor` (per D-08, per-corridor) → read by both the new C9 forecast module and C10 anomaly module
- C9 forecast module → `PIPELINE_SCHEMA`-extended output columns (D-11's schema-version work) → `DLRSafetyMonitor` gate G6 (C10, D-05) reads the forecast + its residual band for its primary signal (D-04)

</code_context>

<specifics>
## Specific Ideas

No particular UI/output-format requests — this phase is backend logic (forecasting + anomaly detection), not user-facing. The user's choices throughout consistently favored the simplest, lowest-dependency, most conservative option at each decision point — this reads as a deliberate risk posture given the near-zero starting data volume and the project's standing fail-safe/safety-adjacent ethical commitment, not indecision.

</specifics>

<deferred>
## Deferred Ideas

- **Tier 2 (scikit-learn quantile-loss GBT) forecasting/anomaly detection** — explicitly deferred (D-10) until historical archive volume clears a floor. Natural candidate for a future phase or a Phase 4 follow-up once the archive (Wave 0) has accumulated meaningful volume.
- **Full multi-provider weather composition** (TCEQ CAMS + NSRDB PSM v4 + ASOS + Open-Meteo), per `docs/data-science/decisions/data_provider.md` — carried forward from Phase 3's own deferral (03-CONTEXT.md D-06); not selected for discussion this session, remains a candidate given its overlap with the historical-backfill needs this phase's archive job creates.
- **Multiple forecast horizons** (e.g. both 1h and 6h) — considered during the Forecast horizon discussion but not chosen; 1-hour-only is this phase's scope. A future phase could add a longer horizon once more history exists to validate against.

### Reviewed Todos (not folded)
None — `todo.match-phase` returned zero matches for Phase 4 this session.

</deferred>

---

*Phase: 4-Predictive*
*Context gathered: 2026-09-08*
