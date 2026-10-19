# Phase 2: Anomaly Detection Model - Research

**Researched:** 2026-09-25
**Domain:** Multivariate unsupervised anomaly detection (scikit-learn) over per-variable weather
baselines (wind/temp/solar), integrated as an additive G6 branch in an existing fail-safe gate
framework.
**Confidence:** HIGH (interface/integration/data-source facts — all read from source this
session); MEDIUM (scikit-learn estimator choice/hyperparameters — official docs, no
project-specific benchmark yet); LOW (nothing in this research is uncorroborated web opinion —
see Assumptions Log for the few forward-looking judgment calls that remain open)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** The trained model watches **raw per-variable readings** (wind, temp, solar — the
  same fields already in `raw_data` per `_gate_sensor`), not the derived `dlr_amps` rating the
  two existing paths already judge.
- **D-02:** ANOM-01 names "load" as a per-variable baseline, but `raw_data` does not carry
  ERCOT load at inference time and wiring it in would touch Track 1's pipeline scope
  (explicitly out-of-scope per REQUIREMENTS.md). **Resolution: training-only.** Historical
  ERCOT load (`ercot_data_retriever.pull_ercot_data`) is used during training/characterization
  only; the live `check()` call only ever receives wind/temp/solar. — **Reversibility:**
  reversible — if live load is wired into `raw_data` later by Track 1, this model can be
  retrained to consume it without any interface change.
- **D-03:** Starting candidate is **`IsolationForest`** (ships in `scikit-learn`, already
  approved/installed). The user is open to the researcher/planner trying additional
  scikit-learn candidates (e.g. `EllipticEnvelope`, `OneClassSVM`) and picking whichever
  measures best on real per-corridor weather data — same bake-off spirit as Phase 1's D-01, not
  a hardcoded single choice. — **Reversibility:** reversible — candidate set lives behind a
  swappable factory/loader.
- **D-04:** Despite Phase 1's finding that the fancier model lost to the simple naive baseline,
  the user's appetite here is **open to more power if it measurably helps** — evaluate on real
  measured false-positive/negative rates, per D-06's validation bar, rather than defaulting to
  the simplest option out of caution.
- **D-05:** The trained model becomes a **new, additive third branch** in `check()`, alongside
  the existing `_check_against_forecast` and `_check_against_rolling_baseline` paths — neither
  existing path is modified or removed. — **Reversibility:** reversible.
- **D-06 (precedence):** When the new trained-model path runs alongside an existing path and
  they disagree, **anomalous if ANY path flags it** — the most conservative combination rule.
  The new model can only ever add caution on top of what already exists; it can never suppress
  an existing path's trip.
- **D-07:** Per the honesty precedent FCST-02 established in Phase 1, the Phase 2 validation
  record must **measure and report the trained model's false-positive/negative rate against the
  mean±k·std baseline honestly, whichever way it comes out** — a "not met" result does not
  block shipping the additive path (per D-05/D-06), but it must be stated plainly, not softened
  or omitted.

### Claude's Discretion
- Exact `IsolationForest` hyperparameters (contamination rate, `n_estimators`, etc.) and
  whether to actually run a multi-candidate bake-off (D-03) or ship `IsolationForest` alone if
  research time is limited.
- Exact per-location granularity for the trained model (per-city vs. per-corridor) and how it's
  keyed/loaded — follow the established pattern already in this codebase
  (`ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` per-city, `AnomalyDetector.for_corridor` takes `max()`
  of the two endpoint cities' `k`) rather than inventing a new scheme.
- Exact feature engineering for the per-variable model (e.g. whether to include time-of-day/
  seasonal features alongside raw wind/temp/solar, similar to Phase 1's `hour_sin`/`hour_cos`).
- Exact filename/structure of the Phase 2 validation record (matching the
  `docs/data-science/decisions/` ADR convention Phase 1 established).
- Whether historical ERCOT load characterization (D-02) is a lightweight sanity check or a more
  thorough correlation analysis — left to the researcher's judgment.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within Phase 2 scope. Wiring live ERCOT load into `raw_data` (which
would let the model consume load at inference time, not just during training) was explicitly
considered and deferred to Track 1's own scope (D-02), not adopted as a Phase 2 idea to revisit
internally.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-------------------|
| ANOM-01 | A trained model — trained on historical per-variable baselines (wind, temp, solar, load), per PRD §8's original C10 scope — replaces or augments the `mean ± k·std` threshold in `anomaly_detector.py`, dropped in behind the existing `AnomalyDetector` interface so it plugs into `DLRSafetyMonitor`'s G6 gate unchanged. | Architecture Patterns 1-3 (additive branch, per-corridor train/persist/load, per-location model selection); Code Examples (feature-row construction, `IsolationForest` fit pattern); Standard Stack (zero-new-dependency confirmation) |
| ANOM-02 | The anomaly-detection model's false-positive/false-negative behavior is validated against real historical data and the results are documented. | Summary (unlabeled-classification framing); Common Pitfalls 1-3 (synthetic-injection FN measurement, `gridstatus` single-year/zone-filter constraints); Validation Architecture (Phase Requirements → Test Map, Wave 0 Gaps) |
</phase_requirements>

## Summary

This phase adds a third, additive decision branch to `AnomalyDetector.check()` — a genuine fitted
scikit-learn outlier-detection model that judges the **raw** `wind`/`temp`/`solar` fields in
`raw_data` (not the derived `rating`, per D-01) against a learned per-variable envelope. It
follows the exact same offline-train / atomic-persist / lazy-load architecture Phase 1 already
established for `ampacity_forecast.py`'s `"ml"` method (`forecast_training.py` →
`_model_path_for`/`_load_corridor_model`/`joblib` + `os.replace`), and it combines with the two
existing paths via OR (D-06): a model trip can only add caution, never suppress an existing trip.
No new third-party dependency is required — `scikit-learn` (1.9.1, verified installed) already
ships `IsolationForest`, `EllipticEnvelope`, and `OneClassSVM`, and `gridstatus` (0.35.0, verified
installed) is already the project's approved ERCOT-load client (`backend/ercot_data_retriever.py`
already exists and already uses it) — so the Package Legitimacy Audit for this phase is empty by
construction: this is a zero-new-dependency phase.

The core research finding that changes how this phase must be planned relative to Phase 1: **this
is not a regression-accuracy problem, it's an unlabeled binary-classification problem.** Phase 1
could measure "beats naive on held-out MAE" directly from real historical data because the target
(`dlr_amps`) is continuous and observed. Here there is no historical "this reading was anomalous"
label anywhere in the project — real historical weather/load data is, by construction, *clean*
(Open-Meteo backfill and ERCOT settlements are not injected with sensor faults). That means ANOM-02
validation cannot be "trained model's trip rate vs. baseline's trip rate on real data" alone for
the *false-negative* half of the bar — false positive rate is directly measurable on real clean
data (in fact, it should trend toward zero on clean data by construction, mirroring the C10 spec's
own "zero false positives on clean historical data" acceptance criterion), but false-negative rate
requires **injecting synthetic corrupted values into an otherwise-real data stream** (spikes,
out-of-range excursions) and measuring the trip rate on the injected rows — this is also exactly
what the (still-stale) `docs/data-science/specs/C10-anomaly-detection.md` spec's own Acceptance
Criteria already anticipated ("injecting corrupted or out-of-range values... is correctly
identified as anomalous"). Both halves — clean-data FP rate and injected-anomaly FN rate — must be
measured against the same real backbone data and the existing mean±k·std baseline, per ROADMAP
SC4, and both need to be in the D-06/D-07-style validation record.

The second load-bearing finding: `ercot_data_retriever.pull_ercot_data`'s `end` parameter is
currently **ignored** by the installed `gridstatus` 0.35.0 client — `get_hourly_load_post_
settlements` only ever downloads one calendar year (`date.year`), and the existing zone filter
(`"WEST" in c.upper()`) only matches ERCOT's `West`/`Far West` weather zones, which is the right
proxy for `MIDLAND_EL_PASO` but not for `AUSTIN_CORPUS_CHRISTI` (Austin/Corpus Christi sit in
ERCOT's `South`/`South Central` zones). Both are training-time-only concerns per D-02, but the
planner needs to account for them when writing the load-characterization step.

**Primary recommendation:** Ship `IsolationForest` as the primary/only candidate (contamination
tuned from the injected-anomaly validation run, not left at `'auto'`), trained per corridor on the
pooled raw wind/temp/solar readings of both endpoint cities (mirroring `for_corridor`'s per-city
resolution, not a from-scratch scheme), with `hour_sin`/`hour_cos` seasonal features alongside the
three raw variables — run a lightweight EllipticEnvelope/OneClassSVM comparison only if time
allows, since D-04 explicitly permits (but does not require) a bake-off, and the Gaussian
assumption EllipticEnvelope needs is unlikely to hold cleanly across all three variables (solar
irradiance is zero at night, a hard non-Gaussian floor).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-variable raw-reading anomaly scoring | Backend / ML model layer (`anomaly_detector.py`, new branch) | — | `AnomalyDetector.check` is the sole owner of the `(bool, str)` decision; no other tier touches this |
| Model training/persistence | Backend / offline script (new `anomaly_training.py`, mirroring `forecast_training.py`) | Database/Storage (`data/models/*.joblib`, git-ignored) | Offline, standalone entry point — never imported by the runtime pipeline, same as `forecast_training.py` |
| Fail-safe resolution on model failure | Backend / `DLRSafetyMonitor` (G6 `except Exception -> _fallback`) | — | Already implemented, zero changes required (ROADMAP SC1/SC3) |
| Historical weather backfill | External API / Backend adapter (`open_meteo_provider.py`) | — | Already shipped (WX-04); no new integration |
| Historical ERCOT load (training-only) | External API / Backend adapter (`ercot_data_retriever.py`) | — | Already shipped; training-time only per D-02, never reaches `check()` |
| Validation record | Documentation (`docs/data-science/decisions/`) | — | Matches Phase 1's ADR convention (D-06/D-07 precedent) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| scikit-learn | 1.9.1 (verified installed via `.venv/lib/python3.12/site-packages/scikit_learn-1.9.1.dist-info`) | `IsolationForest` (primary candidate), optionally `EllipticEnvelope`/`OneClassSVM` for a bake-off | Already the project's approved ML library from Phase 1 (D-02/D-03 pre-approval); ships all three D-03 candidate estimators, no new install |
| joblib | 1.6.0 (verified installed) | Atomic model persistence (`joblib.dump`/`joblib.load`) | Same persistence mechanism `forecast_training.py`/`ampacity_forecast.py` already use — one persistence pattern project-wide |
| pandas / numpy | Already project-standard (2.3.3 / 2.4.3 per `.planning/codebase/STACK.md`) | Feature frame assembly | No change |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| gridstatus | 0.35.0 (verified installed) | ERCOT historical load pull (`ercot_data_retriever.pull_ercot_data`) | Training-time-only characterization per D-02 — never touches the `check()` call path |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `IsolationForest` | `EllipticEnvelope` | Assumes a Gaussian (elliptical) joint distribution over wind/temp/solar — solar irradiance's hard zero-floor at night and skewed daytime distribution violates this; only reasonable if features are decorrelated/transformed first |
| `IsolationForest` | `OneClassSVM` | scikit-learn's own outlier-detection guide states it "is known to be sensitive to outliers and thus does not perform very well for outlier detection" (as opposed to novelty detection on pre-cleaned data) and requires careful `nu`/kernel tuning — a heavier tuning burden for a phase where D-04 says power is welcome only if it *measurably* helps |
| `IsolationForest` | `LocalOutlierFactor` (novelty=True) | Not named in D-03's candidate list (IsolationForest/EllipticEnvelope/OneClassSVM only) — available if the bake-off is extended, but out of the locked candidate set unless the planner deliberately broadens D-03 |

**Installation:** None — `scikit-learn`, `joblib`, `gridstatus` are all already installed and
already imported elsewhere in this repo. No `pip install` step belongs in this phase's plan.

**Version verification (this session):**
```
$ ls .venv/lib/python3.12/site-packages/ | grep -iE "scikit|joblib|gridstatus"
gridstatus
gridstatus-0.35.0.dist-info
joblib
joblib-1.6.0.dist-info
scikit_learn-1.9.1.dist-info
sklearn
$ .venv/bin/python3 -c "import sklearn; print(sklearn.__version__)"
1.9.1
$ .venv/bin/python3 -c "from sklearn.ensemble import IsolationForest; from sklearn.covariance import EllipticEnvelope; from sklearn.svm import OneClassSVM; print('all import ok')"
all import ok
```

## Package Legitimacy Audit

**No new external packages are introduced by this phase.** `scikit-learn` was pre-approved and
verified in Phase 1 (D-02/D-03); `IsolationForest`, `EllipticEnvelope`, and `OneClassSVM` are all
submodules of that same already-installed package, not separate PyPI packages. `gridstatus` is
already an existing, already-installed dependency of `backend/ercot_data_retriever.py`, documented
in `.planning/codebase/STACK.md` and `.planning/codebase/CONCERNS.md` (with an existing migration
plan noted there in case it becomes unmaintained — pre-existing project risk, not new to this
phase). `joblib` is likewise already installed and already used by `forecast_training.py`/
`ampacity_forecast.py`.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| scikit-learn | PyPI | Mature (>15 yrs) | Very high | github.com/scikit-learn/scikit-learn | OK (pre-approved Phase 1) | Not a new install this phase |
| gridstatus | PyPI | Established (already in STACK.md) | — | github.com/gridstatus/gridstatus | OK (pre-existing) | Not a new install this phase |
| joblib | PyPI | Mature | Very high | github.com/joblib/joblib | OK (pre-existing) | Not a new install this phase |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                     OFFLINE (new: anomaly_training.py, mirrors forecast_training.py)
  ┌────────────────────────────────────────────────────────────────────────────┐
  │  Open-Meteo Archive API            ERCOT settlements archive               │
  │  (open_meteo_provider.py)          (ercot_data_retriever.pull_ercot_data)  │
  │         │  per-city wind/temp/solar        │  training-only sanity check   │
  │         ▼  (both corridor endpoints)        ▼  (D-02, never fed to check())│
  │  pool per-corridor raw readings      correlate/characterize vs weather env │
  │         │                                                                  │
  │         ▼                                                                  │
  │  feature engineering (raw wind/temp/solar (+ hour_sin/hour_cos))           │
  │         │                                                                  │
  │         ▼                                                                  │
  │  fit IsolationForest (or bake-off winner) per corridor                    │
  │         │                                                                  │
  │         ▼                                                                  │
  │  atomic persist: tmp-file → os.replace → data/models/anomaly_{corridor}.joblib
  └────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ loaded lazily, cached, at runtime
                                    ▼
  RUNTIME (existing: anomaly_detector.py -- new branch only)
  ┌────────────────────────────────────────────────────────────────────────────┐
  │  DLRSafetyMonitor.run_check(raw_data)                                      │
  │    G1..G5 (unchanged) → rating computed → last_good_rating updated         │
  │    G6: self.anomaly_detector.check(raw_data, rating)                       │
  │         │                                                                  │
  │         ▼  AnomalyDetector.check()                                        │
  │    ┌─────────────────────────────────────────────────────────┐           │
  │    │ self.forecast is not None?  → _check_against_forecast()  │  (D-04    │
  │    │ elif self.history has >=24 rows? → _check_against_rolling_baseline() │  existing
  │    │ [NEW] self.model is not None? → _check_against_model()   │  (this    │
  │    │   builds feature row from raw_data["wind"/"temp"/"solar"]│   phase)  │
  │    │   model.predict(row) == -1  → anomalous                  │           │
  │    └─────────────────────────────────────────────────────────┘           │
  │         │  D-06: OR-combine — ANY path anomalous → is_anomalous=True      │
  │         ▼                                                                  │
  │    except Exception (model load/predict failure) → G6 FAIL → _fallback    │
  │    → resolves to corridor's static_rating (fail-safe, unchanged)          │
  └────────────────────────────────────────────────────────────────────────────┘
```

A reader can trace the live path: `raw_data` enters `run_check`, physics computes `rating`
(G1-G5, unchanged), then G6 hands both `raw_data` (for the new model branch) and `rating` (for the
two existing branches) to `AnomalyDetector.check`, whose three branches OR-combine, and any
exception anywhere in G6 — old or new — resolves through the one existing `_fallback` path.

### Recommended Project Structure
```
backend/
├── anomaly_detector.py       # extended: new `model` param, `_check_against_model` branch
├── anomaly_training.py       # NEW — offline train/bake-off/persist, mirrors forecast_training.py
├── config.py                 # extended: ANOMALY_ML_* tunables, mirroring FORECAST_ML_* block
data/
└── models/                   # git-ignored, existing dir — anomaly_{corridor}.joblib added here
docs/data-science/
├── decisions/
│   └── anomaly_detection_model.md   # NEW — ANOM-02 validation record (D-06/D-07-style)
└── specs/
    └── C10-anomaly-detection.md     # corrected (stale "Not started"/"no model exists" language)
```

### Pattern 1: Additive third branch, not a replacement (D-05)
**What:** `check()` gains a third `if`/`elif` arm alongside `_check_against_forecast` and
`_check_against_rolling_baseline` — neither existing method's code changes.
**When to use:** Any time an existing dispatch chain must gain a new signal without risking the
two already-proven ones. This is also exactly how Phase 1 added `"ml"` to `FORECAST_METHODS`
without touching `"naive"`/`"ewm"`.
**Example (shape, not literal source — this is the pattern to implement, following the module's
own docstring conventions read this session in `backend/anomaly_detector.py`):**
```python
# Constructor gains `model=None, location_key already exists`.
def __init__(self, forecast=None, history=None, model=None, k=None, location_key=None, logger=None):
    ...
    self.model = model

def check(self, raw_data: dict, rating: float) -> tuple[bool, str]:
    rating = float(rating)
    if not math.isfinite(rating):
        self.signal = "non_finite_guard"
        return False, f"non-finite rating ({rating}) — not a G6 concern, G3/G4 own this"

    anomalous_votes = []   # D-06: OR-combine, never suppress an existing trip
    reasons = []

    if self.forecast is not None:
        is_anom, reason = self._check_against_forecast(rating)
        anomalous_votes.append(is_anom); reasons.append(reason)
    elif self.history is not None and "dlr_amps" in self.history.columns:
        usable = self.history["dlr_amps"].dropna()
        if len(usable) >= ROLLING_BASELINE_MIN_ROWS:
            is_anom, reason = self._check_against_rolling_baseline(rating)
            anomalous_votes.append(is_anom); reasons.append(reason)

    if self.model is not None:
        is_anom, reason = self._check_against_model(raw_data)
        anomalous_votes.append(is_anom); reasons.append(reason)

    if not anomalous_votes:
        self.signal = "cold_start"
        return False, "cold start — no forecast/history/model signal available; G6 defers to G1-G5"

    is_anomalous = any(anomalous_votes)
    # self.signal / reason composition left to planner -- must still name which
    # branch(es) fired so introspection (RESEARCH.md "self.signal" contract) holds.
    return is_anomalous, "; ".join(r for r, v in zip(reasons, anomalous_votes))
```
**Planner note:** the existing `check()` dispatch is `if/elif` (forecast OR rolling-baseline,
never both) — D-06 requires the *new* model branch to run *alongside* whichever of those two
already ran, so the control flow must change from a pure `if/elif` chain to "resolve the
forecast/rolling-baseline signal (still mutually exclusive per D-04's existing cold-start logic),
then separately check the model if present, then OR the results." The sketch above shows one way;
the exact `self.signal` string convention (e.g. `"model_trip"` vs. combining multiple signal names)
is left to the planner, but it must remain inspectable per the existing `self.signal` contract
(`backend/anomaly_detector.py:49-52`, verified read this session).

### Pattern 2: Per-corridor offline train / atomic persist / lazy load (reuse Phase 1's shape)
**What:** A standalone script (`anomaly_training.py`) assembles real per-corridor weather,
fits one estimator per corridor, and atomically persists it; the runtime module lazily loads and
caches it, exactly like `ampacity_forecast.py::_load_corridor_model`.
**When to use:** Any per-location model artifact in this codebase — this is now the second
instance of the pattern (forecast, then anomaly), so treat it as the established convention, not a
one-off.
**Example (verified read this session, `backend/ampacity_forecast.py:235-279` and
`backend/forecast_training.py:444-471`):**
```python
# forecast_training.py::persist_corridor_model — literal source, reuse the shape
def persist_corridor_model(model, corridor: str) -> str:
    import joblib
    os.makedirs(config.FORECAST_ML_MODEL_DIR, exist_ok=True)
    final_path = ampacity_forecast._model_path_for(corridor)
    fd, tmp_path = tempfile.mkstemp(dir=config.FORECAST_ML_MODEL_DIR, suffix=".joblib.tmp")
    os.close(fd)
    try:
        joblib.dump(model, tmp_path)
        os.replace(tmp_path, final_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise
    return final_path
```
The anomaly equivalent needs its own `config.ANOMALY_ML_MODEL_DIR` (or can reuse
`config.FORECAST_ML_MODEL_DIR` if the planner prefers one shared model directory — both artifacts
are already namespaced by filename template) and its own `ANOMALY_ML_MODEL_FILENAME_TEMPLATE`
(e.g. `"anomaly_{corridor}.joblib"`), following `FORECAST_ML_MODEL_FILENAME_TEMPLATE`'s exact
`.format(corridor=corridor)` convention (`backend/config.py:231-234`, verified read this session).

### Pattern 3: Per-location model selection via `for_corridor`'s existing city-key mechanism
**What:** `AnomalyDetector.for_corridor(corridor_name, ...)` already resolves `k` per corridor by
taking `max()` of the two endpoint cities' `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` values
(`backend/anomaly_detector.py:54-99`, verified read this session). The trained model needs an
analogous resolution step, but the *model itself* (not `k`) can't be `max()`-combined — models
aren't numbers. Recommended mechanism: resolve `corridor_name` to a single per-corridor model
artifact path (one model per corridor, not one per city, not a `max()` over two models), trained
on the *pooled* raw wind/temp/solar readings from both endpoint cities. This mirrors
`forecast_training.corridor_training_frame`'s two-endpoint-city assembly, but pools rather than
reduces via `min()`/bottleneck-selection, because an anomaly check judges one city's own raw
reading against a plausible-envelope, not a corridor-level derived ampacity.
**When to use:** Any time this phase's per-location discretion item (Claude's Discretion,
CONTEXT.md) needs a concrete default. This is a **recommendation, not a locked decision** — the
planner may instead choose strict per-city models (four models, one per `config.CITY_COORDINATES`
key) if `for_corridor` is extended to select by whichever endpoint city `raw_data` actually came
from; nothing in `raw_data`'s current shape (`_gate_sensor`: `wind`/`temp`/`solar`/
`sensor_status`/`link_status`, no location field) currently identifies which of the two endpoint
cities produced a given reading, which is the practical argument for pooling at the corridor level
rather than requiring a city-level selector the call site doesn't have.

### Anti-Patterns to Avoid
- **Training the model on `rating`/`dlr_amps` instead of raw wind/temp/solar:** D-01 is explicit —
  the new path watches the *raw* per-variable readings, catching a bad sensor value before it
  reaches the physics formula. A model trained on `dlr_amps` would duplicate
  `_check_against_forecast`/`_check_against_rolling_baseline`'s job, not add a new signal.
- **Wiring live ERCOT load into `raw_data` or the runtime `check()` call:** explicitly out of
  scope per D-02 — load is training-time-only, and doing this would touch Track 1's pipeline-wiring
  scope, which is out of bounds for this workstream (REQUIREMENTS.md Out of Scope table).
  `raw_data`'s live shape is a locked, unchangeable input to this phase.
- **Letting the model branch suppress an existing trip:** D-06 mandates OR-combination. A design
  where the model's `(False, ...)` result overrides an existing forecast/rolling-baseline trip
  would silently weaken protection that already works — the opposite of what an *additive* branch
  is for.
- **A second, parallel exception-handling path inside `AnomalyDetector.check` for the model
  branch:** don't swallow the model's exception inside `check()` and return `(False, ...)` — let it
  propagate. `DLRSafetyMonitor.run_check`'s existing `except Exception -> _fallback` (verified read
  this session, `backend/DLRSafetyMonitor.py:72-80`) is *already* the fail-safe boundary; catching
  and neutralizing the exception one layer lower would mean a broken model fails open (silently
  reports "not anomalous") instead of failing safe (falls back to the static rating) — exactly the
  DS-NF5/T-04-02 violation the existing comment at that call site warns against.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Multivariate outlier scoring | A custom per-variable z-score/threshold combiner | `sklearn.ensemble.IsolationForest` (or the bake-off winner) | The rolling mean±k·std path already exists and is univariate-only (`dlr_amps`); a hand-rolled multivariate combination of three independent z-scores is not the same statistical object as a joint-distribution model and would not satisfy ANOM-01's "trained model" requirement — it's still a heuristic. |
| Atomic model persistence | A raw `joblib.dump(path)` write | `tempfile.mkstemp` + `joblib.dump` + `os.replace` | Exact pattern `forecast_training.persist_corridor_model` already implements and tests cover — a direct write risks a torn file on interruption, the same concurrency hazard Phase 1 already solved once. |
| Per-corridor model caching | A dict keyed by corridor re-loaded every call | Module-level `_MODEL_CACHE` dict, load-once-then-cache | `ampacity_forecast._load_corridor_model`'s exact existing pattern — re-implementing this per-module would fork the caching discipline for no reason. |
| Cyclical time-of-day feature | Raw `hour` integer (0-23) as a feature | `hour_sin`/`hour_cos` via `np.sin(2*pi*hour/24)`/`np.cos(...)` | `ampacity_forecast.build_ml_features` already establishes this exact convention (`backend/ampacity_forecast.py:155-157`, verified read this session) — hour 23 and hour 0 are adjacent in reality but maximally distant as a raw integer; reusing the established cyclical encoding keeps one feature-engineering convention project-wide. |

**Key insight:** Every piece of "training/persist/load/cache" machinery this phase needs already
exists in working, tested form from Phase 1 — the only genuinely new code is (a) the estimator
choice/fit call itself and (b) the `check()` dispatch change to OR-combine a third branch. Treat
`forecast_training.py`/`ampacity_forecast.py` as the reference implementation to structurally
mirror, not just a design inspiration.

## Common Pitfalls

### Pitfall 1: Real historical data has no anomaly labels — FN rate can't be measured on clean data alone
**What goes wrong:** A validation record that only reports "trip rate on real clean historical
data" for both FP and FN would silently under-measure the FN half — clean data has no true
anomalies in it, so a model that never trips would show a 0% "false negative rate" that is
actually just "0 anomalies existed to miss," not "the model catches real anomalies."
**Why it happens:** Unlike Phase 1's regression target (`dlr_amps`, a real observed continuous
value), "is this reading anomalous" has no ground-truth label anywhere in this project's real data
sources — Open-Meteo and ERCOT archives record what actually happened, not sensor faults.
**How to avoid:** Measure FP rate directly on real clean data (mirrors the C10 spec's own "zero
false positives on clean historical data" acceptance criterion), and measure FN/recall by
**injecting synthetic corrupted values** into a copy of the real data stream (spikes, out-of-range
excursions, matching the C10 spec's own "corrupted or out-of-range values" acceptance-criterion
language) and checking the trip rate on those injected rows specifically — report both numbers,
and report them for both the new model and the existing mean±k·std baseline on the identical
injected data, per ROADMAP SC4's "compared against the existing mean±k·std baseline's trip rate on
the same data."
**Warning signs:** A validation record with only one number ("X% trip rate on real data") instead
of two clearly separated numbers (FP rate on clean data, FN/recall rate on injected anomalies).

### Pitfall 2: `gridstatus.Ercot().get_hourly_load_post_settlements`'s `end` parameter is a no-op in the installed version
**What goes wrong:** Calling `pull_ercot_data(start="2023-01-01", end="2025-12-31")` expecting a
3-year pull (to match Phase 1's `FORECAST_ML_TRAINING_YEARS=3` Open-Meteo window) silently returns
only one calendar year's data.
**Why it happens:** Verified by reading the installed source this session
(`.venv/lib/python3.12/site-packages/gridstatus/ercot.py:858-889`): `get_hourly_load_post_
settlements(date, end=None, ...)` parses `end` via `utils._handle_date` but then calls
`self._download_post_settlements_load_file(date.year)` — `end` is never passed to the download
call. The function only ever fetches the single year `date` falls in.
**How to avoid:** If a multi-year load-characterization window is wanted, loop one call per year
(mirroring `forecast_training.fetch_city_weather`'s own per-year `fetch_open_meteo` loop pattern)
rather than trusting a single `(start, end)` call to span years. Given D-02 scopes ERCOT load to
training-time characterization only (not literal model input), a single-year or short-window pull
may be entirely adequate for a "sanity check" — this is a real constraint to design around, not
necessarily a blocker.
**Warning signs:** A characterization step that silently only covers one year when the plan
intended a multi-year window — check the row count / date span of the pulled frame explicitly, the
same way `forecast_training.corridor_training_frame`'s callers already print `start`/`end`.

### Pitfall 3: ERCOT's `"WEST"` zone filter doesn't cover `AUSTIN_CORPUS_CHRISTI`
**What goes wrong:** Reusing `ercot_data_retriever.py`'s existing `zone_cols = [c for c in
summer_df.columns if "WEST" in c.upper()]` filter unmodified for a corridor-level load
characterization would silently produce a meaningless (all-`West`/`Far West`) "load" series for
the `AUSTIN_CORPUS_CHRISTI` corridor, which is nowhere near ERCOT's West/Far West weather zones.
**Why it happens:** Verified by reading the installed `gridstatus` source this session
(`.venv/lib/python3.12/site-packages/gridstatus/ercot.py:933-956`): the actual ERCOT weather-zone
columns are `Coast`, `East`, `Far West`, `North`, `North Central`, `South`, `South Central`,
`West`, `ERCOT` (total). Austin and Corpus Christi fall in `South`/`South Central`, not
`West`/`Far West`; only `MIDLAND_EL_PASO` (West Texas) is well-served by the existing filter.
**How to avoid:** If per-corridor load characterization is implemented, map each corridor to its
appropriate ERCOT zone column(s) explicitly (e.g. `AUSTIN_CORPUS_CHRISTI` → `South`/`South
Central`, `MIDLAND_EL_PASO` → `West`/`Far West`) rather than reusing the existing hardcoded
`"WEST"` substring filter for both corridors. This is training-time-only (D-02) so it does not
block shipping, but a wrong-zone characterization would produce misleading sanity-check evidence.
**Warning signs:** A characterization step that reports the same load series (or an implausible
one) for both corridors.

### Pitfall 4: `contamination='auto'` may not match this project's actual clean-data trip-rate expectations
**What goes wrong:** Shipping `IsolationForest(contamination='auto')` untuned risks either an
overly aggressive model (frequent false trips eroding trust, the exact failure mode D-06's control
limit already tries to avoid for the existing paths) or an overly permissive one (misses real
excursions).
**Why it happens:** `'auto'` (verified via `scikit-learn.org` official docs, fetched this session)
uses the original Isolation Forest paper's offset heuristic, which is a generic default, not tuned
to this project's own weather-envelope data or its documented fail-safe-first, few-false-trips
preference (`config.py`'s `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` comment: "deliberately wide —
favors fewer false trips over higher sensitivity").
**How to avoid:** Treat `contamination` as a value to tune from the FP-rate measurement on real
clean data (Pitfall 1) — pick the smallest contamination that still catches the injected synthetic
anomalies at an acceptable rate, then report that choice's measured FP/FN tradeoff explicitly in
the validation record, the same "state the number, don't hide the tuning" discipline Phase 1's
`forecasting_model.md` already modeled.
**Warning signs:** A validation record that names a `contamination` value with no measured
FP-rate evidence justifying the choice.

### Pitfall 5: Building the feature row from `raw_data` inside `check()` must not silently accept a missing key
**What goes wrong:** `raw_data.get("wind")`/`.get("temp")`/`.get("solar")` returning `None` for a
missing key, then silently coercing to `0.0` or `nan` and feeding that into `model.predict()`,
would produce a meaningless prediction rather than a loud failure.
**Why it happens:** `_gate_sensor` (verified read this session, `backend/DLRSafetyMonitor.py:85`)
already treats a missing `wind`/`temp`/`solar` as a G1 failure *before* G6 ever runs, so in
practice `check()`'s model branch should never see a missing key when called through
`DLRSafetyMonitor.run_check` — but `AnomalyDetector.check()` is also called directly in tests
(`backend/tests/anomaly_detector_test.py` passes `{}` as `raw_data` in several tests, verified
read this session), so the model branch must not assume G1 already ran.
**How to avoid:** Follow `ampacity_forecast._point_forecast`'s existing discipline for the `"ml"`
method (verified read this session, `backend/ampacity_forecast.py:329-336`): raise `ValueError`
naming the missing/null column(s) rather than substituting a default. This exception is exactly
what `DLRSafetyMonitor`'s `except Exception -> _fallback` is designed to catch — a loud failure
here is a *feature*, not a bug, per the fail-safe contract.
**Warning signs:** A test that calls `check({}, rating)` with a model configured and gets a clean
`(False, ...)` result instead of an exception/fallback trip.

## Code Examples

### Building the raw-reading feature row for prediction (pattern, not literal source)
```python
# Mirrors ampacity_forecast._point_forecast's "ml" branch discipline
# (backend/ampacity_forecast.py:319-339, verified read this session):
# raise loudly on a missing/null feature, never substitute a default.
def _check_against_model(self, raw_data: dict) -> tuple[bool, str]:
    self.signal = "model_trip" if ... else "model_clean"  # planner's exact naming
    missing = [k for k in ("wind", "temp", "solar") if raw_data.get(k) is None]
    if missing:
        raise ValueError(
            f"_check_against_model: raw_data is missing required field(s) {missing}"
        )
    # feature order must match training-time ML_FEATURE_COLUMNS-equivalent tuple
    row = np.array([[raw_data["wind"], raw_data["temp"], raw_data["solar"]]], dtype=float)
    prediction = self.model.predict(row)[0]  # -1 == outlier, +1 == inlier (sklearn convention)
    is_anomalous = bool(prediction == -1)
    ...
    return is_anomalous, reason
```

### Fitting IsolationForest with explicit, non-default contamination (official docs pattern)
```python
# Source: https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html
from sklearn.ensemble import IsolationForest

clf = IsolationForest(
    n_estimators=100,          # default; no evidence yet to deviate
    contamination=0.02,        # tune from measured FP-rate on real clean data (Pitfall 4) — 0.02 illustrative only
    random_state=20260924,     # reproducibility, matching forecast_training.py's fixed seed convention
)
clf.fit(X_train)                       # X_train: pooled per-corridor raw wind/temp/solar (+ hour_sin/cos)
predictions = clf.predict(X_new)       # array of -1 (outlier) / +1 (inlier)
scores = clf.decision_function(X_new)  # continuous anomaly score, lower = more abnormal
```

### Outlier-detection vs novelty-detection distinction (official docs, verified this session)
```
# Source: https://scikit-learn.org/stable/modules/outlier_detection.html
# Outlier detection: training data itself is (potentially) contaminated -> use fit_predict()
# Novelty detection: training data is clean -> fit() once, then predict() only on NEW data,
#                     never re-predict on the training rows themselves.
#
# This phase's real historical weather/load data is, by construction, clean (no known sensor
# faults in Open-Meteo/ERCOT archives) -- so this is closer to NOVELTY detection: fit on the
# real historical envelope, then predict() on live raw_data readings never seen during training.
# IsolationForest and EllipticEnvelope both support this workflow without a `novelty=` flag;
# LocalOutlierFactor (not in D-03's candidate set) would require novelty=True explicitly.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Rolling `mean ± k·std` over `dlr_amps` history only (univariate, derived-value) | Additive multivariate `IsolationForest` (or bake-off winner) over raw wind/temp/solar (this phase) | This phase (v1.3 Phase 2) | Catches a bad/implausible-but-in-range sensor combination before it reaches the physics formula, not just an out-of-band derived rating |
| `docs/data-science/specs/C10-anomaly-detection.md` says "Not started... No model, training
script, or training dataset exists anywhere in the repo" | Becomes false once this phase lands, same as Phase 1's D-07 correction of the C9 spec | This phase | Spec correction is in-scope for this phase (not explicitly a lettered decision like D-07, but CONTEXT.md's canonical_refs flags it as "worth checking during research" — confirmed genuinely stale this session, recommend planner treat it as a required correction task mirroring D-07's precedent) |

**Deprecated/outdated:**
- `docs/data-science/specs/C10-anomaly-detection.md`'s "Status: Not started" line and "Current
  Implementation: None" section are stale as of this research session — `backend/anomaly_detector.py`
  already implements two heuristic paths (forecast-residual, rolling-baseline), and this phase adds
  a third, genuinely trained one. The spec's "Open Questions" section ("Model type —
  unspecified... labeled anomalies or a synthetic-injection strategy") is *not* stale — it correctly
  anticipated exactly the injection-based validation strategy this research recommends (Pitfall 1).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Pooling both endpoint cities' raw readings into one per-corridor training set (rather than strict per-city models) is the right default granularity, given `raw_data` carries no location identifier the call site could use to pick a city-level model. | Architecture Patterns, Pattern 3 | If a future phase adds a location field to `raw_data`, per-city models might be measurably tighter (less pooled variance) — this is explicitly left as Claude's Discretion in CONTEXT.md, not a locked call, so being wrong here just means the planner picks the alternative already described. |
| A2 | `IsolationForest` alone (no full three-candidate bake-off) is an acceptable default if research/planning time is limited, per CONTEXT.md's explicit "the user's instruction is 'open to trying more if it helps,' not 'must run a full bake-off.'" | Summary, Standard Stack | If a bake-off would have found `EllipticEnvelope`/`OneClassSVM` measurably better on the real per-corridor data, shipping `IsolationForest` alone leaves that improvement unrealized — reversible per D-03 (swappable factory pattern), not a one-way door. |
| A3 | Synthetic-anomaly injection (spikes/out-of-range values layered onto real historical data) is the correct mechanism to measure false-negative rate, since no labeled real anomalies exist in this project's data sources. | Common Pitfalls, Pitfall 1 | This is directly supported by the (stale-but-not-wrong) C10 spec's own Acceptance Criteria language, so risk is low — but the exact injection methodology (spike magnitude, out-of-range value choice, injection rate) is not specified anywhere and is left to the planner. |

**If this table is empty:** N/A — see above; all three entries are judgment calls explicitly left
open by CONTEXT.md's "Claude's Discretion" section, not claims presented as settled fact.

## Open Questions

1. **Exact per-corridor model training-set composition: pooled-both-cities vs. strict per-city.**
   - What we know: `for_corridor` resolves `k` via `max()` over two cities' scalar values; a model
     artifact can't be `max()`-combined the same way.
   - What's unclear: Whether pooling produces a meaningfully worse (higher-variance) envelope than
     training two separate city models and selecting between them somehow.
   - Recommendation: Start with per-corridor pooling (Pattern 3); if research/execution finds the
     pooled envelope's FP rate on real clean data is uncomfortably high for one city's typical
     conditions, revisit per-city training as a follow-up (same kind of backlog item Phase 1 left
     as `999.1`).

2. **Exact synthetic-anomaly injection methodology for FN-rate measurement.**
   - What we know: The C10 spec's Acceptance Criteria names "sudden temperature spikes, impossible
     wind speeds" as example injected anomalies; `DLRSafetyMonitor.WIND_BOUNDS`/`TEMP_BOUNDS`/
     `SOLAR_BOUNDS` (verified read this session, `backend/DLRSafetyMonitor.py:11-13`) already define
     the plausible physical range each variable must stay inside for G3 to even let a reading
     through to G6.
   - What's unclear: Whether injected anomalies should be near-but-outside these G3 bounds
     (testing whether G6 adds value on top of G3's coarse range check) or plausible-but-unusual
     in-range combinations (testing G6's actual unique value — a value each variable individually
     could pass G3 with, but that's jointly implausible, e.g. high solar irradiance simultaneous
     with near-freezing temperature and near-zero wind at 2am).
   - Recommendation: Include both categories in the validation record, explicitly labeled, since
     they test different things — a model that only catches "already caught by G3" injected values
     would not demonstrate the multivariate value ANOM-01 is asking for.

3. **Whether `docs/data-science/specs/C10-anomaly-detection.md`'s correction is in scope for this
   phase's plan (mirroring Phase 1's D-07) or left to a follow-up.**
   - What we know: CONTEXT.md's canonical_refs flags this file as "worth checking during
     research... not yet confirmed stale." This research confirms it *is* stale (Status: "Not
     started"; Current Implementation: "None").
   - What's unclear: CONTEXT.md's `<decisions>` section does not contain a D-07-equivalent lettered
     decision explicitly requiring this correction (unlike Phase 1, where D-07 was an explicit,
     named decision).
   - Recommendation: Treat this as in-scope by precedent (same documentation-debt discipline Phase
     1 applied to C9) unless the planner has a specific reason to defer it — it's a small,
     low-risk doc edit with a clear template (Phase 1's C9 correction) to follow.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| scikit-learn | Model fit/predict | ✓ | 1.9.1 (verified) | — |
| joblib | Atomic persistence | ✓ | 1.6.0 (verified) | — |
| gridstatus | Training-time ERCOT load pull (D-02) | ✓ | 0.35.0 (verified) | — |
| Network access (Open-Meteo Archive API) | Training data backfill | Not directly probed this session (Phase 1 already exercised this successfully per `forecasting_model.md`) | — | None needed — already proven reachable in Phase 1's own validation record |
| Network access (ercot.com load-history page scrape via `gridstatus`) | Training-time load characterization (D-02) | Not directly probed this session | — | If unreachable/rate-limited, D-02 already scopes this as training-only and non-blocking — the planner can defer/skip the load sanity-check without affecting ANOM-01's interface requirement |

**Missing dependencies with no fallback:** none — every dependency this phase needs is already
installed and already proven working by Phase 1's own precedent.

**Missing dependencies with fallback:** ERCOT load network access (see table) — D-02 already
frames this as training-only and lightweight-by-discretion, so a network hiccup here does not
block ANOM-01/ANOM-02's core deliverable.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (verified via `.planning/codebase/STACK.md`) |
| Config file | `pytest.ini` (pythonpath → `backend/`) |
| Quick run command | `.venv/bin/python3 -m pytest backend/tests/anomaly_detector_test.py -x` |
| Full suite command | `.venv/bin/python3 -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ANOM-01 | New model branch returns `(bool, str)`, participates in `self.signal`, OR-combines with existing branches | unit | `pytest backend/tests/anomaly_detector_test.py -x` | ✅ existing file, needs new test functions (Wave 0 gap: none — file exists and structure is established) |
| ANOM-01 | A trained-model exception still resolves through `DLRSafetyMonitor._fallback` (G6) | unit/integration | `pytest backend/tests/anomaly_detector_test.py backend/tests/SafetyMonitor_TestSuite.py -x` | ✅ both files exist (mirrors `test_anomaly_resolves_through_existing_fallback_contract`, verified read this session) |
| ANOM-01 | Model artifact training/persistence round-trips (fit → save → load → predict) | unit | New test file, e.g. `pytest backend/tests/anomaly_training_test.py -x` | ❌ Wave 0 gap — mirrors `backend/tests/forecast_training_test.py`'s existing 361-line/10-test structure |
| ANOM-02 | Real-data FP rate (clean historical weather) measured and compared to mean±k·std baseline | manual/scripted, feeds the validation record | `.venv/bin/python3 backend/anomaly_training.py --validate` (new script entry point, planner's naming) | ❌ Wave 0 gap — new offline validation script, mirrors `forecast_training.py --bakeoff`'s reporting shape |
| ANOM-02 | Real-data FN rate (synthetic-injected anomalies) measured and compared to baseline | manual/scripted, feeds the validation record | same as above | ❌ Wave 0 gap |

### Sampling Rate
- **Per task commit:** `.venv/bin/python3 -m pytest backend/tests/anomaly_detector_test.py -x`
- **Per wave merge:** `.venv/bin/python3 -m pytest -q` (full suite — 409 passed as of Phase 1's
  verification; expect a new baseline count once this phase's tests land)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/anomaly_training_test.py` — covers new training/persist/load round-trip
  (mirrors `forecast_training_test.py`'s structure)
- [ ] Offline validation/reporting script (`anomaly_training.py`'s bake-off/validate entry point,
  or equivalent) — no existing file computes FP/FN rates against injected synthetic anomalies;
  this is genuinely new machinery, not a gap in existing coverage
- [ ] No new test framework install needed — pytest already configured and green

*(No gap in `backend/tests/anomaly_detector_test.py` itself — it already exists, is substantive
(200+ lines read this session), and follows the exact per-behavior `test_*` convention new tests
should extend.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | This phase has no auth surface — offline training script, in-process model inference only |
| V3 Session Management | No | N/A |
| V4 Access Control | No | N/A |
| V5 Input Validation | Yes | `raw_data`'s `wind`/`temp`/`solar` fields are already validated by G1 (`_gate_sensor`, presence) and G3 (`_gate_range`, physical bounds) *before* G6 runs — the new model branch inherits this upstream validation and must not weaken it (e.g., must not attempt to "correct" or clamp an out-of-range value itself; G3 already owns that). The model's own feature-row construction should raise loudly (`ValueError`) rather than substitute a default on any missing/null field, per Pitfall 5. |
| V6 Cryptography | No | No secrets, tokens, or encrypted data touched by this phase — model artifacts are plain `joblib` files, same trust level as the already-existing forecast model artifacts |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| Deserializing an untrusted/tampered `.joblib` model artifact | Tampering | `joblib.load` executes arbitrary pickled Python objects if the file is attacker-controlled — this is a pre-existing risk from Phase 1's identical pattern (`_load_corridor_model`), not new to this phase, but worth the planner re-confirming `data/models/` stays git-ignored, locally-generated-only, and never accepts a caller-supplied path (`_model_path_for`'s existing closed-set corridor validation, verified read this session, is the mitigation already in place and must be mirrored for the anomaly model's own `_model_path_for`-equivalent). |
| A broken/failing model silently reporting "not anomalous" instead of failing safe | Denial of Service (of the safety guarantee, inverted) | Let exceptions propagate out of the new branch uncaught — `DLRSafetyMonitor`'s existing `except Exception -> _fallback` (G6) is the single, already-correct mitigation boundary; do not add a second, competing try/except inside `AnomalyDetector` itself (see Anti-Patterns above). |

## Sources

### Primary (HIGH confidence — read directly this session)
- `backend/anomaly_detector.py` — full module read; `AnomalyDetector.__init__`, `for_corridor`,
  `check`, `_check_against_forecast`, `_check_against_rolling_baseline`, `ROLLING_BASELINE_MIN_ROWS`
- `backend/DLRSafetyMonitor.py` — full module read; `run_check`, `_gate_sensor`, `_gate_range`,
  `_fallback`, `WIND_BOUNDS`/`TEMP_BOUNDS`/`SOLAR_BOUNDS`
- `backend/config.py` — full module read; `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION`,
  `DEFAULT_ANOMALY_CONTROL_LIMIT_K`, `CORRIDOR_ENDPOINTS`, `FORECAST_ML_*` block (structural
  template for a new `ANOMALY_ML_*` block)
- `backend/forecast_training.py` — full module read; `CANDIDATE_ESTIMATORS`, `bakeoff_corridor`,
  `select_winner`, `persist_corridor_model`, `main`/`_run_bakeoff`
- `backend/ampacity_forecast.py` — full module read; `ML_FEATURE_COLUMNS`, `build_ml_features`,
  `_model_path_for`, `_load_corridor_model`, `_point_forecast`'s `"ml"` branch
- `backend/open_meteo_provider.py` — full module read; `fetch_open_meteo`, `HOURLY_TO_PIPELINE`
- `backend/ercot_data_retriever.py` — full module read; `pull_ercot_data`
- `.venv/lib/python3.12/site-packages/gridstatus/ercot.py:858-975` — read this session;
  `get_hourly_load_post_settlements`'s single-year-only behavior and the real ERCOT zone-column
  names (Pitfalls 2 and 3)
- `docs/data-science/specs/C10-anomaly-detection.md` — full spec read; confirmed stale
- `.planning/workstreams/ml-modeling/ROADMAP.md` — Phase 2 Success Criteria 1-5
- `.planning/workstreams/ml-modeling/REQUIREMENTS.md` — ANOM-01, ANOM-02, Out of Scope table
- `.planning/workstreams/ml-modeling/phases/02-anomaly-detection-model/02-CONTEXT.md` — full
  context read (D-01 through D-07, Claude's Discretion, canonical refs)
- `.planning/workstreams/ml-modeling/phases/01-forecasting-model/01-CONTEXT.md`,
  `docs/data-science/decisions/forecasting_model.md`,
  `.planning/workstreams/ml-modeling/phases/01-forecasting-model/01-VERIFICATION.md` — Phase 1
  precedent read in full
- `backend/tests/anomaly_detector_test.py` — read (first ~200 lines); existing test conventions
- Direct shell verification: `scikit-learn` 1.9.1, `joblib` 1.6.0, `gridstatus` 0.35.0 all
  importable in `.venv`

### Secondary (MEDIUM confidence — official docs fetched this session)
- [scikit-learn IsolationForest API reference](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html) — full parameter list, method signatures, contamination guidance, no-partial_fit confirmation
- [scikit-learn Novelty and Outlier Detection guide](https://scikit-learn.org/stable/modules/outlier_detection.html) — outlier vs. novelty detection distinction, per-estimator guidance (EllipticEnvelope Gaussian assumption, OneClassSVM sensitivity, IsolationForest high-dimensional strength)

### Tertiary (LOW confidence)
- None — all findings in this document are either read directly from project source this session
  (HIGH/CITED) or fetched from official scikit-learn documentation this session (MEDIUM/CITED); no
  claim rests on unverified WebSearch snippets alone.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new dependency; versions verified by direct import in `.venv`
- Architecture/integration: HIGH — every locked interface point (`check` signature, `_fallback`
  wiring, `raw_data` shape, `for_corridor` mechanism, `config.py` conventions) read from source
  this session, not inferred
- Model technique (IsolationForest/EllipticEnvelope/OneClassSVM specifics): MEDIUM — official
  scikit-learn docs, no project-specific benchmark exists yet (that's this phase's job to produce)
- Validation methodology (synthetic injection for FN rate): MEDIUM — derived from the project's
  own (pre-existing, stale-but-correct-on-this-point) C10 spec Acceptance Criteria plus standard
  unsupervised-anomaly-detection practice; not an externally-cited methodology paper

**Research date:** 2026-09-25
**Valid until:** 30 days (stable library APIs; the ERCOT `gridstatus` client behavior documented
in Pitfalls 2/3 should be re-verified if `gridstatus` is upgraded before this phase executes)
