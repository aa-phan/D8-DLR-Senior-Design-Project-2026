# Phase 4: Predictive - Research

**Researched:** 2026-09-08
**Domain:** Time-series forecasting + statistical/learned anomaly detection layered on an existing physics-based (IEEE 738) ampacity pipeline with a hard fail-safe contract (Python/pandas/numpy)
**Confidence:** MEDIUM — codebase facts and installed-environment facts are HIGH (read directly this session); forecasting-horizon and C9↔C10 coupling design choices are ASSUMED because the project's own C9/C10 specs explicitly leave them as open questions and no CONTEXT.md exists yet for this phase.

## Summary

Phase 3 delivered a physics-correct, fail-safe `DLRSafetyMonitor` (C7) with a fixed `{status, rating, fallback, alerts}` result contract and five deterministic gates (G1–G5), plus a corridor-discretization layer (C8) that already reuses that exact contract for its own per-point fallback. Phase 4 must add two *learned* layers on top — ampacity forecasting (C9, DS-F11) and learned anomaly detection (C10, DS-F12) — without redefining that contract or `PIPELINE_SCHEMA`.

The most consequential finding from this session's direct codebase read: **the background historical weather/ampacity archive job the Roadmap explicitly recommended starting during Phase 3 was never built.** A repo-wide grep for `archive`/`historical`/`schema_version` found no matching implementation in `backend/`, and the only persisted data on disk is `outputs/station_data/*.csv` (93–385 rows per station, a single ~4-day July 2025 window, overwritten/appended manually per run — not a running accumulation job) plus a 20-row `data/fixtures/sample_pipeline_output.csv`. This means Phase 4 begins at effectively zero accumulated historical volume — exactly the "idling on data volume" scenario the Roadmap's own note warned about. This research treats starting that archive job as a Phase 4 Wave 0 task, not an assumed-already-done precondition, and designs C9/C10 to be honest about starting from near-zero data rather than presuming a mature dataset.

The installed Python environment (`.venv`) confirms `numpy 2.4.3`, `pandas 2.3.3`, `scipy 1.17.1`, `matplotlib`, `pytest 9.0.3` are already present; **no ML library (`scikit-learn`, `statsmodels`, etc.) is installed**, and no `requirements.txt`/`pyproject.toml` exists anywhere in the repo — dependencies are only documented as a `pip install ...` line in `README.md` and a docstring in `dlr_pipeline.py`. Given the tiny expected data volume for a while yet, this research recommends a two-tier approach: a **Tier 1 baseline (no new dependency)** using `pandas`' own rolling/EWM tools for a naive/exponential-smoothing forecast with an empirical-residual confidence band, upgradeable to a **Tier 2 model (`scikit-learn` quantile-loss gradient boosting)** once historical volume clears a documented floor. Anomaly detection (C10) is recommended as a residual/statistical-control-limit check (forecast vs. actual, or rolling mean ± k·std) — explainable, cheap, and consistent with the codebase's existing human-tunable-threshold convention (`config.DELTA_FRACTION`) — rather than a black-box model like Isolation Forest.

**Primary recommendation:** Build the historical archive job first (Wave 0), ship a Tier 1 naive/EWM forecast with an empirical-quantile confidence band for C9, and a residual/statistical-control-limit anomaly signal for C10 that plugs into `DLRSafetyMonitor` as a new gate (or equivalent injectable check) reusing the existing `_fallback` helper and result contract — never a second, parallel fallback mechanism. Extend `PIPELINE_SCHEMA` additively with a new `PIPELINE_SCHEMA_VERSION` constant, adding only new optional columns, never redefining existing ones.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DS-F11 | Forecast ampacity ahead of real time (regression/ML) — owned by C9 | Standard Stack (Tier 1/Tier 2 forecasting), Architecture Patterns (Pattern 1/3), Common Pitfalls, Validation Architecture |
| DS-F12 | Anomaly detection via a model trained on historical baselines, additive to (not a replacement of) C7's fallback path — owned by C10 | Architecture Patterns (Pattern 2), Don't Hand-Roll, Common Pitfalls, Security Domain, Validation Architecture |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Historical weather/ampacity archival | Database / Storage | API/Backend (the pipeline call site that writes it) | Needs an append-only, time-indexed persisted store, distinct from the current per-run `outputs/*.csv` dumps, which are not designed as an accumulating time series |
| Ampacity forecasting (C9) | API / Backend | Database/Storage (reads the archive) | Pure Python model logic; no client/UI or API-server tier exists yet in this repo (`frontend/`, `api/` are explicit placeholders per `REQUIREMENTS.md` Out of Scope) |
| Forecast confidence/uncertainty band | API / Backend | — | Computed in the same process as the point forecast |
| Learned anomaly detection (C10) | API / Backend | — | Must plug into `DLRSafetyMonitor.run_check` (C7), same tier as the existing gate chain |
| `PIPELINE_SCHEMA` extension | API / Backend (`backend/units_def.py`) | — | In-process schema, not a database schema; enforced by `validate_pipeline_row` at export/return time |
| Fallback trigger integration | API / Backend | — | Must reuse `DLRSafetyMonitor._fallback` / the `{status, rating, fallback, alerts}` contract, not introduce a second one |

## Standard Stack

### Core (already installed — verified this session via `.venv/bin/python -m pip list`)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|---------------|
| pandas | 2.3.3 [VERIFIED: `.venv` pip list, this session] | Time-indexed dataframes; `.rolling()`/`.ewm()` for Tier 1 forecasting and control-limit anomaly detection | Already the pipeline's dataframe backbone (`dlr_pipeline.py`, `corridor_discretization.py`); no new dependency needed for a naive/exponential-smoothing baseline |
| numpy | 2.4.3 [VERIFIED: `.venv` pip list, this session] | Numeric ops, array math | Already used throughout `thermal_model.py` |
| scipy | 1.17.1 [VERIFIED: `.venv` pip list, this session] | `scipy.stats` for empirical-quantile / normal-quantile band math if needed | Already installed; avoids adding a stats-only dependency |
| pytest | 9.0.3 [VERIFIED: `.venv` pip list, this session] | Test runner | Existing convention (`pytest.ini`, `backend/tests/`) |

### Supporting (new dependency — only for Tier 2, once historical volume justifies it)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scikit-learn [ASSUMED: package name from training knowledge, cross-checked against PyPI registry this session — see Package Legitimacy Audit] | 1.9.0 latest [VERIFIED: `.venv/bin/pip index versions scikit-learn`, this session] | `GradientBoostingRegressor(loss="quantile")` for horizon forecasting + prediction intervals | Once a location/corridor has accumulated enough historical rows (see Pitfall 1 / Assumption A3) — official docs explicitly caution against deep trees on datasets under "a few hundred samples" [CITED: scikit-learn "Prediction Intervals for Gradient Boosting Regression" docs] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pandas `.ewm()`/`.rolling()` naive baseline (Tier 1) | scikit-learn `GradientBoostingRegressor` (Tier 2) directly from day one | GBT on a few hundred rows or fewer risks overfitting and a falsely confident interval; the official docs' own small-dataset guidance is to shrink `max_depth` — safer to defer until volume exists |
| pandas `.ewm()` exponential smoothing | `statsmodels` `ExponentialSmoothing`/Holt-Winters | `statsmodels` adds a second new ML-adjacent dependency for functionality `pandas` already partially covers (single/double exponential smoothing); only worth adding later if seasonal (Holt-Winters triple) smoothing is actually needed |
| Residual / statistical-control-limit anomaly detection | scikit-learn `IsolationForest` | Isolation Forest is a black box relative to a rolling-mean ± k·std or MAD-based control limit; harder to explain/audit in a safety-adjacent system and harder to unit-test deterministically with synthetic data — the C10 spec's own framing ("model trained on historical baselines per variable") and the instruction to favor simplicity/explainability both point at the control-limit approach as primary |
| CSV-append historical archive | SQLite / Parquet time-series store | Simpler now (matches the existing `export_results` CSV convention), but should be revisited once monthly row counts grow past what a single flat CSV comfortably supports (see Assumption A5) |

**Installation (only when Tier 2 is actually implemented):**
```bash
.venv/bin/pip install scikit-learn
```
No `requirements.txt`/`pyproject.toml` currently exists in this repo [VERIFIED: `find` for `*.txt`/`*.toml` at repo root this session returned nothing] — dependencies are only documented as a prose `pip install ...` line in `README.md:33` and `backend/dlr_pipeline.py:8`. Recommend creating a `requirements.txt` as part of this phase rather than continuing the prose-only convention, since DS-NF2 (reproducibility) is already a locked non-functional requirement and an unpinned, undeclared dependency set works against it.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|--------------|---------|-------------|
| scikit-learn | pypi | Deep version history: 0.9 → 1.9.0 across dozens of releases [VERIFIED: `pip index versions scikit-learn`, this session] | null — legitimacy seam could not resolve download-count metadata for this package | not returned by legitimacy seam | **SUS** (`unknown-downloads`, `no-repository`) [VERIFIED: `gsd_run query package-legitimacy check --ecosystem pypi scikit-learn`, this session] | Flagged — planner must add a `checkpoint:human-verify` task before installing, per protocol. Note: the SUS verdict traces to metadata the legitimacy seam couldn't fetch (downloads, repo URL), not to any real red flag — a 0.9→1.9.0, multi-year release history is itself strong counter-evidence against slopsquatting, but per this protocol that counter-evidence does not override the required checkpoint. |
| statsmodels | pypi | Deep version history: 0.4 → 0.15.0 across dozens of releases [VERIFIED: `pip index versions statsmodels`, this session] | null | not returned | **SUS** (`too-new`, `unknown-downloads`, `no-repository`) [VERIFIED: `gsd_run query package-legitimacy check --ecosystem pypi statsmodels`, this session] | Not recommended for this phase (see Alternatives Considered — `pandas.ewm()` covers the Tier 1 need without it). If the planner still wants it later for seasonal Holt-Winters smoothing, the same `checkpoint:human-verify` gate applies. |

**Packages removed due to [SLOP] verdict:** none.
**Packages flagged as suspicious [SUS]:** `scikit-learn`, `statsmodels` — planner inserts `checkpoint:human-verify` before each install per protocol.

## Architecture Patterns

### System Architecture Diagram

```
Synoptic Weather API (C4)                 IEEE 738 Thermal Model (C5)
        |                                          |
        v                                          v
weather_provider.fetch_weather()  --->  thermal_model.ieee738_ampacity()
        |                                          |
        +--------------------+---------------------+
                             v
              [NEW] Historical Archive append
              (one row per run: timestamp, location/corridor,
               weather features, dlr_amps, static_rating, status)
                             |
                             v
              data/historical/ampacity_history.csv (append-only)
                             |
              +--------------+---------------------+
              v                                     v
   [NEW] C9 Forecast Model                [NEW] C10 Anomaly Detector
   (reads archive, produces                (reads archive baseline +
    horizon-ahead point forecast            current reading, optionally
    + confidence band)                      C9's forecast, for a residual
              |                              check)
              v                                     v
   PIPELINE_SCHEMA-extended row      anomaly signal --> DLRSafetyMonitor
   (forecast_horizon_min,            (C7) new gate, same
    forecast_amps,                   {status, rating, fallback,
    forecast_ci_lower_amps,          alerts} contract as G1-G5
    forecast_ci_upper_amps)                  |
              |                              v
              +------------> export_results() / plot_dlr_summary()
                              (existing C3, unchanged)
```

A reader can trace the primary use case: weather → physics ampacity → archived alongside every run → forecast model reads the archive to project ahead → anomaly detector reads the same archive plus the live reading (and optionally the forecast) to decide whether to trip the *same* fallback path C7 already uses → everything still flows through the one existing export/visualization stage.

### Recommended Project Structure
```
backend/
├── historical_archive.py       # NEW — append-only persistence job (C9/C10 shared support)
├── ampacity_forecast.py        # NEW (C9) — Tier 1 naive/EWM forecast + empirical band; Tier 2 GBT hook
├── anomaly_detector.py         # NEW (C10) — residual/control-limit anomaly signal
├── DLRSafetyMonitor.py         # MODIFY — optional injectable anomaly-detector hook, new gate
├── units_def.py                # MODIFY — PIPELINE_SCHEMA additive extension + PIPELINE_SCHEMA_VERSION
├── config.py                   # MODIFY — forecast horizon, anomaly control-limit constants (k, window)
data/
├── historical/                 # NEW — archived weather+ampacity time series (git-ignored, like outputs/)
backend/tests/
├── historical_archive_test.py  # NEW
├── ampacity_forecast_test.py   # NEW
├── anomaly_detector_test.py    # NEW
```

### Pattern 1: Additive `PIPELINE_SCHEMA` versioning

**What:** Add a module-level `PIPELINE_SCHEMA_VERSION` constant next to `PIPELINE_SCHEMA`, and only ever add new keys with `"required": False` — never remove, rename, or change the `unit`/`range` of an existing key.
**When to use:** Any time C9/C10 needs to add forecast/anomaly columns to pipeline output.
**Basis (verbatim, existing code read this session — `backend/units_def.py:324-375`):**
```python
PIPELINE_SCHEMA: Dict[str, Dict] = {
    "air_temp": {
        "unit":      "degC",
        "range":     (-20.0, 60.0),
        "required":  True,
    },
    ...
    "ercot_west_load_mw": {
        "unit":      "MW",
        "range":     (0.0, 30_000.0),
        "required":  False,
    },
}
```
No `SCHEMA_VERSION` or similar marker exists in the codebase today [VERIFIED: grep for `schema_version`/`SCHEMA_VERSION` across `backend/` and `docs/` this session returned no implementation match]. Recommended additive pattern (standard practice for backward-compatible schema evolution — additive columns, explicit version bump, never mutate existing entries) [ASSUMED — general software-engineering practice, not something this specific repo has precedent for yet]:
```python
PIPELINE_SCHEMA_VERSION = 2  # bumped from 1 (Phase 1-3 baseline) when C9/C10 columns were added

PIPELINE_SCHEMA: Dict[str, Dict] = {
    # ... existing v1 columns, UNCHANGED ...

    # --- v2 additions (Phase 4 / C9, C10) ---
    "forecast_horizon_min": {
        "unit": "min", "range": (0.0, 1440.0), "required": False,
    },
    "forecast_amps": {
        "unit": "A", "range": (100.0, 4000.0), "required": False,
    },
    "forecast_ci_lower_amps": {
        "unit": "A", "range": (0.0, 4000.0), "required": False,
    },
    "forecast_ci_upper_amps": {
        "unit": "A", "range": (0.0, 8000.0), "required": False,
    },
    "anomaly_score": {
        "unit": "pu", "range": (0.0, None), "required": False,  # dimensionless
    },
}
```
(Exact ranges/columns are the planner's decision at plan time — this sketch demonstrates the additive mechanism, not final values.)

### Pattern 2: Plugging C10 into `DLRSafetyMonitor` without a second fallback path

**What:** Extend `DLRSafetyMonitor` with an *injectable* anomaly-detector dependency (mirroring how `conductor`/`rating_bounds` are already injected per `backend/DLRSafetyMonitor.py:15-24`), evaluated as a new gate after G5, reusing the existing `_fallback` helper so the result is indistinguishable in shape from any other gate failure.
**When to use:** Wiring C10's learned signal into C7's existing chain.
**Basis (verbatim, existing gate + fallback contract read this session — `backend/DLRSafetyMonitor.py:26-98`):**
```python
def run_check(self, raw_data: dict) -> dict:
    result = {"status": "unknown", "rating": None, "fallback": False, "alerts": []}
    ...
    self.last_good_rating  = rating
    result["status"]       = "ok"
    result["rating"]       = rating
    return result

def _fallback(self, result, gate, reason, rating):
    msg = f"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"
    self.logger(msg)
    result.update({"status": "fallback", "rating": rating, "fallback": True,
                    "alerts": [msg]})
    return result
```
Recommended extension shape (sketch, not existing code):
```python
def __init__(self, ..., anomaly_detector=None, logger=None):
    ...
    self.anomaly_detector = anomaly_detector  # None = C10 disabled, G1-G5 unchanged

def run_check(self, raw_data: dict) -> dict:
    ...
    # existing G1-G5 unchanged ...
    self.last_good_rating = rating
    result["status"] = "ok"
    result["rating"] = rating

    # G6 — learned anomaly signal (C10), additive: never runs if no detector injected
    if self.anomaly_detector is not None:
        try:
            is_anomalous, reason = self.anomaly_detector.check(raw_data, rating)
        except Exception as exc:
            # fail-safe-by-default (DS-NF5): a detector error must fall back,
            # never silently pass through as "ok"
            return self._fallback(result, "G6", f"detector error ({exc})", self.static_rating)
        if is_anomalous:
            return self._fallback(result, "G6", reason, self.static_rating)

    return result
```
This keeps `corridor_discretization.py::rate_corridor`'s existing call site (`monitor.run_check(observation)`) completely unchanged — the anomaly detector is injected once at construction, matching how `geometry.conductor`/`geometry.rating_bounds` are already passed into `DLRSafetyMonitor(...)` at `backend/corridor_discretization.py:535-539`.

### Pattern 3: Historical archive as a single, injectable append call

**What:** One small module (`historical_archive.py`) with an `append_observation(row: dict)` function, called once per pipeline run from `run_pipeline`/`rate_corridor`, matching the codebase's existing "one call site" discipline (e.g. `config.conductor_kwargs_for`'s own stated rationale: "so this decision has exactly one call site").
**When to use:** Every time a weather+ampacity reading is produced, whether it results in `"ok"` or `"fallback"` status — both are equally valuable training signal for C9/C10.
**Anti-pattern to avoid:** Writing archive rows directly inline in multiple call sites (`dlr_pipeline.run_pipeline`, `corridor_discretization.rate_corridor`) — duplicated write logic is exactly the kind of drift `config.py`'s own docstring calls out as the reason it exists ("two independent 900.0 A literals... could silently drift out of agreement").

### Anti-Patterns to Avoid
- **Retraining a heavy model per request:** Tier 2 GBT training should happen offline/periodically (e.g. a scheduled retrain script), never inline in the hot request path.
- **A second, competing fallback shape:** C10 must never emit its own `{"anomaly": true, ...}` result — it must resolve through `DLRSafetyMonitor._fallback`'s existing `{status, rating, fallback, alerts}` contract (DS-F12 success criterion 3 is explicit about this).
- **Ad hoc schema columns:** Adding forecast/anomaly fields as a parallel dict or DataFrame outside `PIPELINE_SCHEMA` violates DS-F11 success criterion 2 directly.
- **Blocking the safety-critical path on archive I/O:** A disk-full or permission error writing to the historical archive must never prevent `run_check`/`rate_corridor` from returning a rating — archival should be best-effort, wrapped so its failure degrades to "not archived this cycle," never to "pipeline failed."
- **Shuffled random train/test split on time-series data:** Leaks future values into training, producing a falsely optimistic backtest.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|--------------|-----|
| Prediction interval / uncertainty band | Custom bootstrap resampling around a hand-rolled trend line | `pandas`-derived empirical residual quantiles from a walk-forward backtest (Tier 1); `sklearn.ensemble.GradientBoostingRegressor(loss="quantile")` (Tier 2) | Quantile loss is a documented, tested scikit-learn feature [CITED: scikit-learn "Prediction Intervals for Gradient Boosting Regression" docs]; a hand-rolled bootstrap CI is easy to get statistically wrong (biased or too narrow), which is dangerous for a rating that must never overstate capacity |
| Time-series train/validation split | Random/shuffled `train_test_split` | Walk-forward / expanding-window split (manual loop, or `sklearn.model_selection.TimeSeriesSplit` if scikit-learn is already a dependency) | Random splitting on a time series leaks future information into the training fold |
| Great-circle / corridor geo math | Reimplementing haversine/bearing formulas | Existing `corridor_discretization.py::haversine_km`/`initial_bearing_deg`/`interpolate_great_circle` (already built in Phase 3) | Already solved and tested; no reason to reintroduce a geo library or duplicate math |
| Statistical process control thresholds | Ad hoc "looks weird" heuristics scattered per-caller | Rolling mean ± k·rolling-std (Shewhart-style control limits) or MAD-based robust z-score, centralized as named constants in `config.py` | Matches the codebase's own existing convention (`config.DELTA_FRACTION`, `config.RATING_BOUNDS_BY_LOCATION`) of one human-tunable, documented, centralized threshold rather than magic numbers per module |

**Key insight:** The codebase's existing discipline — one physics source of truth (`thermal_model.py`), one fallback contract (`DLRSafetyMonitor._fallback`), one centralized config module for every tunable number (`config.py`) — already *is* the anti-hand-rolling posture this domain needs. Phase 4 should extend that discipline into the two new models rather than inventing a separate one for "the ML parts."

## Common Pitfalls

### Pitfall 1: Building/training against near-zero historical data
**What goes wrong:** A forecasting or anomaly model trained on ~100-400 rows (the current on-disk maximum, confirmed this session) will overfit or produce a falsely narrow/confident interval.
**Why it happens:** The Roadmap's own recommendation to start a background archive job during Phase 3 was not implemented [VERIFIED: grep for `archive`/`historical` across `backend/` this session found no matching implementation; `wc -l outputs/station_data/*.csv` shows 93-385 rows per station, one ~4-day window].
**How to avoid:** Treat the archive job as Wave 0 of Phase 4. Gate Tier 2 (GBT) behind a minimum-row floor (Assumption A3); default to Tier 1 (naive/EWM + empirical residual band) until that floor is cleared.
**Warning signs:** A prediction interval that never widens even as the forecast horizon grows, or a backtest MAE that looks "too good."

### Pitfall 2: `ieee738_ampacity`'s `np.ndarray`-vs-`float` return-type trap
**What goes wrong:** `thermal_model.ieee738_ampacity` returns `np.ndarray` even for scalar input [per Phase 3's own `03-PATTERNS.md`: "Float-wrap pitfall — `ieee738_ampacity` returns `np.ndarray` even for scalar input... wrap with `float(...)`"]. Any new forecast/anomaly code deriving features from this function's output, or comparing a forecast to a live rating, will silently operate on 0-d/1-element arrays instead of scalars if this isn't repeated.
**Why it happens:** `thermal_model.py` is a vectorized/pure-numpy module by design.
**How to avoid:** Apply the same `float(...)` wrap already used in `DLRSafetyMonitor._compute_ampacity` (`backend/DLRSafetyMonitor.py:84-91`) at every new boundary that reads a computed ampacity value.
**Warning signs:** Equality/threshold comparisons that behave inconsistently, or `assert` failures comparing `np.ndarray` to `float` in new tests.

### Pitfall 3: Redefining `PIPELINE_SCHEMA` ad hoc instead of extending it
**What goes wrong:** A new forecast module introduces its own separate schema dict or bypasses `validate_pipeline_row` entirely, silently violating DS-F11 success criterion 2.
**How to avoid:** Follow Pattern 1 — additive keys only, one `PIPELINE_SCHEMA_VERSION` bump, no new parallel schema object.

### Pitfall 4: C10 introducing a second, competing fallback mechanism
**What goes wrong:** An anomaly detector returns its own ad hoc `{"anomaly": True, "confidence": 0.9}`-shaped result instead of routing through `DLRSafetyMonitor._fallback`, silently violating DS-F12 success criterion 3 and giving downstream callers (C8's `rate_corridor`, future UI) two different failure shapes to handle.
**How to avoid:** Follow Pattern 2 — inject the detector into `DLRSafetyMonitor`, resolve through the existing `_fallback` helper.

### Pitfall 5: A global anomaly threshold instead of per-location bounds
**What goes wrong:** Phase 3 already hit this exact bug once: the original `RATING_BOUNDS = (400, 1800)` global plausibility band was "Incompatible with 3 of 4 `STATIC_RATINGS`" [per `03-PATTERNS.md`, quoting the historical bug directly] and had to be replaced with `config.RATING_BOUNDS_BY_LOCATION`. A new anomaly/control-limit threshold that isn't similarly per-location risks the identical failure mode — e.g. a single global control-limit band that's too wide for El Paso (static rating 1450 A, range up to only 2300 A) and too narrow for Corpus Christi (static rating 3000 A, range up to 5000 A).
**How to avoid:** Any new anomaly threshold constants added to `config.py` should follow the existing `RATING_BOUNDS_BY_LOCATION`-style per-city dict shape, not a single global tuple.

### Pitfall 6: Archive-write failures blocking the safety-critical rating path
**What goes wrong:** If `historical_archive.append_observation(...)` raises (disk full, permissions, bad row), and that exception isn't isolated, it could prevent `run_pipeline`/`rate_corridor` from returning a rating at all — a much worse outcome than simply missing one archive row.
**How to avoid:** Wrap the archive-append call so any failure there logs and continues, never propagates into the rating computation path (matches DS-NF5's "fail-safe by default" spirit, even though archival itself isn't a safety gate).

## Code Examples

### Existing `PIPELINE_SCHEMA` shape to extend
```python
# Source: backend/units_def.py:324-375 (read this session)
PIPELINE_SCHEMA: Dict[str, Dict] = {
    "air_temp": {
        "unit":      "degC",
        "range":     (-20.0, 60.0),
        "required":  True,
    },
    "dlr_amps": {
        "unit":      "A",
        "range":     (100.0, 4000.0),
        "required":  False,
    },
    # ...
}
```

### Existing fail-safe contract to reuse (never redefine)
```python
# Source: backend/DLRSafetyMonitor.py:26-98 (read this session)
def run_check(self, raw_data: dict) -> dict:
    result = {"status": "unknown", "rating": None, "fallback": False, "alerts": []}
    # G1-G5 ...
    self.last_good_rating  = rating
    result["status"]       = "ok"
    result["rating"]       = rating
    return result

def _fallback(self, result, gate, reason, rating):
    msg = f"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"
    self.logger(msg)
    result.update({"status": "fallback", "rating": rating, "fallback": True,
                    "alerts": [msg]})
    return result
```

### Existing injectable-dependency pattern for the safety monitor
```python
# Source: backend/corridor_discretization.py:535-539 (read this session)
monitor = DLRSafetyMonitor(
    static_rating=geometry.static_rating,
    conductor=geometry.conductor,
    rating_bounds=geometry.rating_bounds,
)
```
(C10's `anomaly_detector` should be injected the same way, per Pattern 2.)

### scikit-learn quantile-loss pattern (Tier 2, official docs)
```python
# Source: scikit-learn "Prediction Intervals for Gradient Boosting Regression" docs
# https://scikit-learn.org/stable/auto_examples/ensemble/plot_gradient_boosting_quantile.html
from sklearn.ensemble import GradientBoostingRegressor

common_params = dict(
    learning_rate=0.05, n_estimators=200, max_depth=2,  # shallow trees for small datasets
    min_samples_leaf=9, min_samples_split=9,
)
gbr_lower  = GradientBoostingRegressor(loss="quantile", alpha=0.05, **common_params)
gbr_median = GradientBoostingRegressor(loss="quantile", alpha=0.50, **common_params)
gbr_upper  = GradientBoostingRegressor(loss="quantile", alpha=0.95, **common_params)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Static line rating only | Real-time IEEE 738 dynamic rating with deterministic fail-safe gates (G1-G5) | Phase 2-3 (this project) | Established the safety contract C9/C10 must not disturb |
| Single-station rating | Corridor-level rating via 5-point discretization + weakest-link minimum | Phase 3 (this project) | C9/C10 must decide per-station vs. per-corridor granularity (Open Question) |
| Reactive, current-conditions-only rating | Forward-looking forecast + learned anomaly signal (this phase) | Phase 4 (in progress) | Adds two new model layers that must plug into the existing contract, not replace it |

**Deprecated/outdated:** Nothing in this repo is being deprecated by this phase — it is purely additive.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|----------------|
| A1 | Forecast horizon assumed short-to-medium (e.g. 1-6 hours ahead), matching the pipeline's existing 5-minute-to-hourly cadence, absent a specified value — the C9 spec (`docs/data-science/specs/C9-ampacity-forecasting.md`) itself lists "minutes, hours?" as an open question. | Standard Stack, Validation Architecture | Wrong horizon could require redesigning the feature/target windowing entirely |
| A2 | Assumed C9's forecast/actual residual is C10's primary anomaly signal (with a pure-statistical rolling-baseline fallback path when no forecast is available), rather than two fully independent models — the C10 spec explicitly leaves this open. | Architecture Patterns (Pattern 2), Architectural Responsibility Map | If the user wants fully independent models, the coupling assumed here requires rework |
| A3 | Assumed a "few hundred rows" floor per location/corridor before attempting Tier 2 (GBT), extending scikit-learn's documented small-dataset caution [CITED] into a firm "don't train below this" rule [ASSUMED extension beyond what the docs explicitly state]. | Standard Stack, Common Pitfalls (Pitfall 1) | Too low a floor risks overfit/false-confidence bands; too high delays Tier 2 unnecessarily |
| A4 | Assumed C10 is wired into `DLRSafetyMonitor` as a new gate (G6) via constructor injection, mirroring the existing `conductor`/`rating_bounds` pattern — the C10 spec confirms the *result shape* must be reused but does not specify the injection mechanism. | Architecture Patterns (Pattern 2) | Planner/user may prefer a wrapping/decorator function instead of a sixth gate |
| A5 | Assumed CSV-append is an adequate historical-archive storage format at the current/near-term data volume, with Parquet/SQLite deferred as a later optimization — no existing convention in the repo covers accumulating (as opposed to per-run) storage. | Standard Stack (Alternatives), Architecture Patterns (Pattern 3) | A growing single CSV could eventually become slow to append/read; low risk at hundreds-to-low-thousands of rows/month |
| A6 | Assumed the latest scikit-learn (1.9.0, confirmed via registry this session) is an acceptable version to pin, absent any existing pinned-dependency convention in the repo (no `requirements.txt` exists at all). | Standard Stack | None-pinned reproducibility is already a DS-NF2-relevant gap independent of this phase; planner should consider adding `requirements.txt` as part of this phase's scope |

**If this table is empty:** N/A — see entries above; all are flagged for confirmation before being treated as locked decisions.

## Open Questions (RESOLVED)

1. **Forecast horizon** — see Assumption A1. Recommendation: confirm with user/stakeholder during `/gsd-discuss-phase` before locking feature/target windowing. RESOLVED: see CONTEXT.md D-01.
2. **C9→C10 coupling** — see Assumption A2. Recommendation: confirm whether C10 should be fully independent of C9's forecast. RESOLVED: see CONTEXT.md D-04.
3. **Was the historical archive job started anywhere not found by this session's grep?** A repo-wide search for `archive`/`historical`/`schema_version` across `backend/` and `.planning/phases/03-safety-spatial/` found no implementation. Recommendation: confirm with the user before assuming Phase 4 must build this from scratch as Wave 0 — the Roadmap's phrasing implies it should already exist. RESOLVED: see CONTEXT.md D-07 — built from scratch in Phase 4, Wave 0/04-01.
4. **Per-corridor vs. per-station/point granularity** for C9/C10 — Phase 3 operates `DLRSafetyMonitor` once per corridor (`corridor_discretization.py:535-539`) but resolves per-point observations independently. Neither C9 nor C10's spec states which granularity the learned models should target. Recommendation: default to per-corridor (matches the existing one-monitor-per-corridor instantiation) unless the user specifies otherwise. RESOLVED: see CONTEXT.md D-08.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python 3.12 (`.venv`) | All backend code | ✓ [VERIFIED: `.venv/pyvenv.cfg` present, `.venv/bin/pip` runs this session] | 3.12 | — |
| pandas | Tier 1 forecast, archive, anomaly control limits | ✓ [VERIFIED: `.venv` pip list] | 2.3.3 | — |
| numpy | All numeric code | ✓ [VERIFIED: `.venv` pip list] | 2.4.3 | — |
| scipy | Optional stats helpers | ✓ [VERIFIED: `.venv` pip list] | 1.17.1 | — |
| pytest | Test running | ✓ [VERIFIED: `.venv` pip list, `pytest.ini` present] | 9.0.3 | — |
| scikit-learn | Tier 2 GBT quantile forecast (optional, deferred) | ✗ [VERIFIED: absent from `.venv` pip list this session] | — | Tier 1 (pandas-only naive/EWM + empirical residual band) covers DS-F11 without it; install only when Tier 2 is actually implemented, behind `checkpoint:human-verify` (see Package Legitimacy Audit) |
| `requirements.txt`/`pyproject.toml` | Reproducible dependency pinning | ✗ [VERIFIED: `find` at repo root this session found neither] | — | README prose `pip install` line (existing convention); recommend creating a proper file this phase |

**Missing dependencies with no fallback:** none — Tier 1 needs nothing beyond what's installed.
**Missing dependencies with fallback:** `scikit-learn` (fallback: stay on Tier 1 until data volume justifies Tier 2).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 [VERIFIED: `.venv` pip list] |
| Config file | `pytest.ini` [VERIFIED: read this session — `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`] |
| Quick run command | `.venv/bin/python -m pytest -q backend/tests/<new_test_file>.py` |
| Full suite command | `.venv/bin/python -m pytest -q` (matches Phase 3's own cross-cutting constraint: "reports 0 failed") |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|--------------------|--------------|
| DS-F11 | Given historical weather+ampacity, forecast at a defined horizon | unit | `.venv/bin/python -m pytest -q backend/tests/ampacity_forecast_test.py` | ❌ Wave 0 |
| DS-F11 | Forecast output extends `PIPELINE_SCHEMA` additively (new versioned columns, no redefinition) | unit | `.venv/bin/python -m pytest -q backend/tests/ampacity_forecast_test.py::test_schema_version_bumped_and_additive` | ❌ Wave 0 |
| DS-F12 | Learned anomaly signal augments C7, same result shape | unit | `.venv/bin/python -m pytest -q backend/tests/anomaly_detector_test.py::test_anomaly_resolves_through_existing_fallback_contract` | ❌ Wave 0 |
| DS-F12 | Synthetic/injected anomalous conditions fall back to static rating | unit | `.venv/bin/python -m pytest -q backend/tests/anomaly_detector_test.py::test_synthetic_anomaly_triggers_fallback` | ❌ Wave 0 |
| DS-F12 | Zero false positives on clean historical/fixture data | unit | `.venv/bin/python -m pytest -q backend/tests/anomaly_detector_test.py::test_clean_data_no_false_positive` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** targeted new test file (`.venv/bin/python -m pytest -q backend/tests/<file>.py`)
- **Per wave merge:** `.venv/bin/python -m pytest -q` (full suite)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/historical_archive_test.py` — covers the new archive job (append/read round-trip, best-effort-failure behavior per Pitfall 6)
- [ ] `backend/tests/ampacity_forecast_test.py` — covers DS-F11
- [ ] `backend/tests/anomaly_detector_test.py` — covers DS-F12, follows `SafetyMonitor_TestSuite.py`'s existing fixture/injection style (e.g. `monitor._compute_ampacity = lambda d: 300` direct-override pattern [VERIFIED: `backend/tests/SafetyMonitor_TestSuite.py:122-123`, read this session]) for deterministic synthetic-anomaly injection
- [ ] A larger synthetic fixture for backtesting — `data/fixtures/sample_pipeline_output.csv` currently has only ~20 rows [VERIFIED: read this session], too small for a meaningful walk-forward backtest; recommend generating a synthetic multi-week weather+ampacity series with a known/injectable pattern so tests don't depend on live archive volume
- [ ] Framework install: none needed for Tier 1 (pandas-only); `scikit-learn` only if/when Tier 2 lands, per `checkpoint:human-verify`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | no | No auth layer exists yet in this subsystem (`api/`/`frontend/` are explicit placeholders per `REQUIREMENTS.md` Out of Scope) |
| V3 Session Management | no | Same as above |
| V4 Access Control | no | Same as above |
| V5 Input Validation | yes | `PIPELINE_SCHEMA` + `validate_pipeline_row` (`backend/units_def.py`) — extend to new forecast/anomaly columns per Pattern 1; also validate archived rows before persisting and before training |
| V6 Cryptography | no | No new secrets/crypto surface introduced by this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Historical-archive poisoning (a corrupted or malicious row silently skews future forecasts/anomaly baselines) | Tampering | Validate every row against `PIPELINE_SCHEMA` (`validate_pipeline_row`) both before persisting to the archive and before using it for training — reuse the existing non-strict validation convention already applied to live pipeline output (`dlr_pipeline.validate_pipeline_output`) |
| Anomaly detector fail-open (a detector exception silently treated as "no anomaly") | Tampering / Denial of Service | Wrap detector calls so any exception resolves to a gate failure (fallback), never a silent pass-through — matches Pattern 2's sketch and DS-NF5's fail-safe-by-default principle |
| Unbounded historical-archive growth | Denial of Service | Define a retention/rotation policy (rolling window or periodic compaction) as part of the archive job's design rather than an unbounded append-forever file |

## Sources

### Primary (HIGH confidence)
- `backend/DLRSafetyMonitor.py` (read in full this session) — `run_check`/`_fallback` contract, gate order, injectable-dependency pattern
- `backend/units_def.py:1-80,300-399` (read this session) — `PIPELINE_SCHEMA` shape, `validate_pipeline_row`
- `backend/config.py` (read in full this session) — `STATIC_RATINGS`, `RATING_BOUNDS_BY_LOCATION`, `DELTA_FRACTION`, `CORRIDOR_ENDPOINTS` centralization convention
- `backend/dlr_pipeline.py` (read in full this session) — `run_pipeline`, `validate_pipeline_output`, existing dependency prose (`README.md:33`)
- `backend/corridor_discretization.py` (read in full this session) — `rate_corridor`, `DLRSafetyMonitor` injection call site, min()-reduction pattern
- `backend/thermal_model.py:1-80` (read this session) — `ieee738_ampacity` signature and `np.ndarray`-return behavior
- `backend/tests/SafetyMonitor_TestSuite.py` (read in full this session) — existing pytest fixture/injection conventions
- `.planning/phases/03-safety-spatial/03-PATTERNS.md` (read in full this session) — documents the exact `RATING_BOUNDS`-mismatch historical bug referenced in Pitfall 5
- `docs/data-science/specs/C9-ampacity-forecasting.md`, `docs/data-science/specs/C10-anomaly-detection.md` (read in full this session) — component specs, explicit open questions
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` (read in full this session)
- `pip index versions scikit-learn` / `pip index versions statsmodels` (run this session against the real PyPI registry) — version history confirmation
- scikit-learn official docs — "Prediction Intervals for Gradient Boosting Regression" (`https://scikit-learn.org/stable/auto_examples/ensemble/plot_gradient_boosting_quantile.html`)

### Secondary (MEDIUM confidence)
- WebSearch: residual-based anomaly detection / statistical control limits — cross-checked general concept (forecast-residual control charts, Shewhart-style limits) against multiple independent sources

### Tertiary (LOW confidence)
- `gsd_run query package-legitimacy check` SUS verdicts for `scikit-learn`/`statsmodels` — the seam's metadata gaps (`unknown-downloads`, `no-repository`) appear to be a data-source limitation rather than a genuine risk signal, given the deep registry version history confirmed independently, but per protocol this is not sufficient to clear the SUS flag

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for installed-environment facts (verified via `pip list`/`pip index versions` this session); MEDIUM for the scikit-learn quantile-regression pattern (official docs, not yet exercised in this repo)
- Architecture: HIGH for how it must integrate with existing C7/C8/C2 code (all read directly this session); MEDIUM for the specific new-module boundaries proposed (a design recommendation, not yet built)
- Pitfalls: HIGH — several are direct citations of bugs Phase 3 already hit and documented (`03-PATTERNS.md`), not speculative

**Research date:** 2026-09-08
**Valid until:** ~30 days for library versions (scikit-learn/statsmodels release cadence); architecture/pattern recommendations remain valid as long as `DLRSafetyMonitor`'s contract and `PIPELINE_SCHEMA`'s shape are unchanged
