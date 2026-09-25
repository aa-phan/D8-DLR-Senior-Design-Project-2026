# Phase 2: Anomaly Detection Model - Context

**Gathered:** 2026-09-24
**Status:** Ready for planning

<domain>
## Phase Boundary

`anomaly_detector.AnomalyDetector.check(raw_data, rating)` gains a new, actual trained-model
decision path — trained on historical per-variable weather baselines (wind, temp, solar; load
used at training time only, see D-02) — added alongside the two existing heuristic paths
(`_check_against_forecast`, `_check_against_rolling_baseline`), dropped in behind the exact same
`(is_anomalous: bool, reason: str)` return shape so `DLRSafetyMonitor`'s G6 call site and its
`except Exception -> _fallback` fail-safe wiring need zero changes (ANOM-01, ANOM-02).

Out of scope: forecasting model changes (Phase 1, already complete), pipeline orchestration/
scheduling (Track 1), corridor geometry (Track 3), any change to the fail-safe contract (a
model failure must still resolve to the static rating via existing G6 exception handling), and
any change to `raw_data`'s live shape (wiring ERCOT load into the live pipeline input is Track
1's territory, not this phase's — see D-02).

</domain>

<decisions>
## Implementation Decisions

### What the model looks at
- **D-01:** The trained model watches **raw per-variable readings** (wind, temp, solar — the
  same fields already in `raw_data` per `_gate_sensor`), not the derived `dlr_amps` rating the
  two existing paths already judge. This is the literal ANOM-01 scope ("per-variable
  baselines") and catches a bad/anomalous sensor reading before it ever reaches the physics
  formula, rather than only judging the number that comes out the other end.
- **D-02:** ANOM-01 names "load" as a per-variable baseline, but `raw_data` does not carry
  ERCOT load at inference time and wiring it in would touch Track 1's pipeline scope
  (explicitly out-of-scope per REQUIREMENTS.md). **Resolution: training-only.** Historical
  ERCOT load (`ercot_data_retriever.pull_ercot_data`) is used during training/characterization
  only — e.g. to help validate that a per-variable weather envelope looks sane against
  known load-driven demand patterns — but the live `check()` call only ever receives
  wind/temp/solar, matching what `raw_data` actually carries today. Zero Track 1 changes
  required. — **Reversibility:** reversible — if live load is wired into `raw_data` later by
  Track 1, this model can be retrained to consume it without any interface change (the
  `AnomalyDetector.check(raw_data, rating)` signature is unaffected either way).

### Model technique
- **D-03:** Starting candidate is **`IsolationForest`** (ships in `scikit-learn`, already an
  approved/installed dependency from Phase 1 — no new dependency needed). The user is open to
  the researcher/planner trying additional scikit-learn candidates (e.g. `EllipticEnvelope`,
  `OneClassSVM`) and picking whichever measures best on real per-corridor weather data — same
  bake-off spirit as Phase 1's D-01, not a hardcoded single choice. — **Reversibility:**
  reversible — candidate set lives behind a swappable factory/loader, same pattern Phase 1
  established with `CANDIDATE_ESTIMATORS`.
- **D-04:** Despite Phase 1's finding that the fancier model lost to the simple naive baseline,
  the user's appetite here is **open to more power if it measurably helps** (not a mandate to
  stay maximally simple) — evaluate on real measured false-positive/negative rates, per D-06's
  validation bar, rather than defaulting to the simplest option out of caution.

### Integration into check()
- **D-05:** The trained model becomes a **new, additive third branch** in `check()`, alongside
  the existing `_check_against_forecast` and `_check_against_rolling_baseline` paths — neither
  existing path is modified or removed. Satisfies ROADMAP SC2's "at least one path" literally,
  and mirrors Phase 1's own additive precedent (a new `"ml"` method alongside `naive`/`ewm`,
  nothing removed). — **Reversibility:** reversible — the new branch can be disabled/removed
  without touching the two proven existing paths.
- **D-06 (precedence):** When the new trained-model path runs alongside an existing path and
  they disagree, **anomalous if ANY path flags it** — the most conservative combination rule,
  consistent with this project's fail-safe-first ethos (never resolve optimistically when a
  signal is uncertain). This means the new model can only ever add caution on top of what
  already exists; it can never suppress an existing path's trip.

### Validation bar
- **D-07:** Per the honesty precedent FCST-02 established in Phase 1 (state the expectation
  before the result; write the real number either way), the Phase 2 validation record must
  **measure and report the trained model's false-positive/negative rate against the
  mean±k·std baseline honestly, whichever way it comes out** — a "not met" result does not
  block shipping the additive path (per D-05/D-06, it's OR-combined, so a weak model only adds
  extra caution, it never removes existing protection), but it must be stated plainly, not
  softened or omitted, exactly as `docs/data-science/decisions/forecasting_model.md` did for
  Phase 1's negative result.

### Claude's Discretion
- Exact `IsolationForest` hyperparameters (contamination rate, `n_estimators`, etc.) and
  whether to actually run a multi-candidate bake-off (D-03) or ship `IsolationForest` alone if
  research time is limited — the user's instruction is "open to trying more if it helps," not
  "must run a full bake-off."
- Exact per-location granularity for the trained model (per-city vs. per-corridor) and how it's
  keyed/loaded — follow the established pattern already in this codebase
  (`ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` per-city, `AnomalyDetector.for_corridor` takes
  `max()` of the two endpoint cities' `k`) rather than inventing a new scheme.
- Exact feature engineering for the per-variable model (e.g. whether to include time-of-day/
  seasonal features alongside raw wind/temp/solar, similar to Phase 1's `hour_sin`/`hour_cos`).
- Exact filename/structure of the Phase 2 validation record (matching the
  `docs/data-science/decisions/` ADR convention Phase 1 established).
- Whether historical ERCOT load characterization (D-02) is a lightweight sanity check or a
  more thorough correlation analysis — left to the researcher's judgment on what's actually
  useful given the real data.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Interface contracts (locked, from ROADMAP.md — do not renegotiate)
- `.planning/workstreams/ml-modeling/ROADMAP.md` — Phase 2 success criteria (SC1-SC5) and the
  two non-renegotiable interface contracts (`AnomalyDetector.check` return shape;
  `DLRSafetyMonitor`'s G6 fail-safe wiring via `except Exception`).
- `.planning/workstreams/ml-modeling/REQUIREMENTS.md` — ANOM-01, ANOM-02 full text and the Out
  of Scope table (Track boundaries this phase must respect).

### Existing anomaly-detection module and safety monitor
- `backend/anomaly_detector.py` — the module this phase extends. Read in full: `AnomalyDetector`
  constructor, `for_corridor`, `check`, `_check_against_forecast`, `_check_against_rolling_baseline`,
  `ROLLING_BASELINE_MIN_ROWS`. The new path must return the same `(bool, str)` shape and set
  `self.signal` like the existing branches do.
- `backend/DLRSafetyMonitor.py` — G6's call site (`run_check`), the `except Exception ->
  _fallback` fail-safe wrapper the new path's failure mode must keep triggering correctly.
- `docs/data-science/specs/C10-anomaly-detection.md` — the spec this phase should keep
  current (check for staleness the way Phase 1's D-07 corrected C9; not yet confirmed stale,
  but worth checking during research).

### Real-data sourcing (mirrors Phase 1's precedent, not re-litigated here)
- `.planning/workstreams/ml-modeling/ROADMAP.md` Overview — the same "real data is less scarce
  than the live archive suggests" section Phase 1 used: Open-Meteo Archive API backfill for
  weather, `ercot_data_retriever.pull_ercot_data` for historical ERCOT load (training-only
  per D-02).
- `backend/open_meteo_provider.py` — real historical weather source (already shipped, WX-04).
- `backend/ercot_data_retriever.py::pull_ercot_data` — real historical ERCOT load archive, used
  per D-02 for training-time characterization only.
- `backend/config.py` — `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`, `DEFAULT_ANOMALY_CONTROL_LIMIT_K`,
  `CORRIDOR_ENDPOINTS` — the existing per-location keying pattern to follow (see Claude's
  Discretion).

### Phase 1 precedent (established patterns and honesty standard to match)
- `.planning/workstreams/ml-modeling/phases/01-forecasting-model/01-CONTEXT.md` — D-01
  (bake-off, no default lean), D-02/D-03 (dependency approval precedent — already exercised,
  `scikit-learn` is installed), D-05 (per-location pattern), D-06/D-07 (validation record
  convention).
- `docs/data-science/decisions/forecasting_model.md` — the honesty-first validation record
  template and precedent D-07 (this phase) must match: state the expectation before the
  verdict, report a "not met" result plainly if that's what the numbers show.
- `.planning/workstreams/ml-modeling/phases/01-forecasting-model/01-VERIFICATION.md` — how a
  "the model didn't win" phase still passed verification because the engineering/honesty
  deliverable, not a guaranteed accuracy win, is what's actually required.
- `backend/forecast_training.py` — reference implementation of an offline
  assemble/bake-off/persist pattern (`CANDIDATE_ESTIMATORS`, `bakeoff_corridor`,
  `select_winner`) this phase's equivalent training script can follow structurally.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/anomaly_detector.py::AnomalyDetector.for_corridor` — the per-corridor construction
  pattern (resolves `k` per endpoint city, takes `max()`) to mirror for the new model's
  per-location artifact selection.
- `backend/forecast_training.py` — Phase 1's offline training/bake-off script is a structural
  template: real-data assembly, `CANDIDATE_ESTIMATORS` factory mapping, `TimeSeriesSplit`-style
  measured comparison, atomic `joblib` persistence via `os.replace`.
- `backend/open_meteo_provider.py` + `backend/ercot_data_retriever.py` — both already-shipped
  real historical data sources this phase needs, no new integration work to reach them.

### Established Patterns
- Per-location dicts keyed by city (`config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`,
  `config.STATIC_RATINGS`, `config.RATING_BOUNDS_BY_LOCATION`) — the new model's per-location
  selection should follow this same convention.
- `self.signal` attribute set before every `check()` return — lets a caller/test see which
  branch decided; the new path must participate in this same introspection contract.
- `except Exception -> _fallback` in `DLRSafetyMonitor.run_check` — the fail-safe contract the
  new path's failure mode is already covered by; no new exception-handling code needed at the
  `DLRSafetyMonitor` layer.
- Additive-only extension (Phase 1: new method value in an existing tuple; here: new branch in
  an existing dispatch) — the established way this codebase evolves both C9 and C10 signal sets
  without touching what's already proven.

### Integration Points
- `AnomalyDetector.check(raw_data, rating)` — the model's new branch reads `raw_data`'s
  wind/temp/solar fields directly (D-01); it does not need a new parameter on `check` or the
  constructor beyond however the trained model artifact itself is loaded/selected (mirroring
  `_load_corridor_model`'s per-corridor loader pattern from Phase 1's `ampacity_forecast.py`).
- Combination rule (D-06) lives inside `check()`'s existing dispatch logic — the new branch does
  not replace the `if self.forecast is not None: ... elif self.history is not None: ...`
  structure, it runs as an additional check whose "anomalous" result ORs with whichever existing
  branch also ran.

</code_context>

<specifics>
## Specific Ideas

No specific implementation examples given beyond the six decisions above (D-01 through D-07) —
exact hyperparameters, per-location granularity mechanism, feature engineering details, and
validation record filename are explicitly left to research/planning (see "Claude's Discretion").

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 2 scope. Wiring live ERCOT load into `raw_data` (which
would let the model consume load at inference time, not just during training) was explicitly
considered and deferred to Track 1's own scope (D-02), not adopted as a Phase 2 idea to revisit
internally.

</deferred>

---

*Phase: 2-Anomaly Detection Model*
*Context gathered: 2026-09-24*
