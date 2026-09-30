# Phase 2: Anomaly Detection Model - Pattern Map

**Mapped:** 2026-09-24
**Files analyzed:** 8 (4 modified existing, 3 new, 1 doc correction)
**Analogs found:** 8 / 8

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/anomaly_detector.py` (extended: `model` param, `_check_against_model`) | service (decision module) | request-response | `backend/ampacity_forecast.py` (`"ml"` branch of `_point_forecast`) + itself (existing `_check_against_forecast`/`_check_against_rolling_baseline`) | exact (self-extension) + role-match (ml branch discipline) |
| `backend/config.py` (extended: `ANOMALY_ML_*` block) | config | CRUD (constants) | `backend/config.py` lines 229-276 (`FORECAST_ML_*` block) | exact |
| `backend/anomaly_training.py` (new) | service (offline training/CLI) | batch | `backend/forecast_training.py` (whole module) | exact |
| `backend/tests/anomaly_training_test.py` (new) | test | batch | `backend/tests/forecast_training_test.py` | exact |
| `backend/tests/anomaly_detector_test.py` (extended: new test functions) | test | request-response | itself (existing file, established `test_*` convention) | exact |
| `docs/data-science/decisions/anomaly_detection_model.md` (new) | config/doc (ADR) | batch (report) | `docs/data-science/decisions/forecasting_model.md` | exact |
| `docs/data-science/specs/C10-anomaly-detection.md` (corrected, stale status) | config/doc (spec) | — | itself + `docs/data-science/specs/C9-*` correction precedent (not read this session; Phase 1 D-07 precedent referenced in RESEARCH.md) | role-match |
| `data/models/anomaly_{corridor}.joblib` (generated artifact, git-ignored) | model artifact | file-I/O | `data/models/forecast_{corridor}.joblib` (same dir, sibling template) | exact |

## Pattern Assignments

### `backend/anomaly_detector.py` (service, request-response) — extend, don't replace

**Analog:** itself (`backend/anomaly_detector.py`, full file already read) + `backend/ampacity_forecast.py:282-339` (`"ml"` branch discipline)

**Constructor pattern to extend** (lines 38-52, current):
```python
def __init__(self, forecast=None, history=None, k=None, location_key=None, logger=None):
    self.forecast = forecast
    self.history = history
    self.location_key = location_key
    self.k = float(
        k if k is not None
        else config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION.get(
            location_key, config.DEFAULT_ANOMALY_CONTROL_LIMIT_K
        )
    )
    self.logger = logger or print
    self.signal = "not_yet_evaluated"
```
Add `model=None` parameter, store as `self.model = model`. `for_corridor` (lines 54-99) should gain the analogous model-loading step (lazy `_load_corridor_model`-style, see Pattern below) — do not eagerly load in `__init__` unless `for_corridor` is the only construction path used at runtime (check call sites before deciding).

**Core dispatch pattern to change** (lines 101-140, `check()`): currently a pure `if self.forecast is not None: ... elif self.history ...: ... else: cold_start` chain that returns immediately from inside each branch. D-06 requires OR-combination with the new model branch, so this must change from early-`return` per branch to an accumulate-then-OR shape. RESEARCH.md's Pattern 1 (lines 274-310) gives the literal sketch to follow — copy that vote-accumulation structure, keeping `self.signal` assignment inside each existing branch method unchanged (each private method already sets `self.signal` on its own line: `_check_against_forecast` line 152, `_check_against_rolling_baseline` line 182). The new `_check_against_model` method must set `self.signal` the same way (e.g. `"model_trip"` / `"model_clean"`).

**Error-handling pattern to copy** (from `backend/ampacity_forecast.py:319-339`, the `"ml"` branch of `_point_forecast`):
```python
if method == "ml":
    if history is None:
        raise ValueError(
            "_point_forecast: method='ml' requires the `history` frame"
        )
    if model is None:
        raise ValueError(
            "_point_forecast: method='ml' requires an already-fitted `model`"
        )
    features = build_ml_features(history)
    # ... raises ValueError naming the offending column if any value is null
```
Mirror this discipline exactly for `_check_against_model(self, raw_data)`: raise `ValueError` naming the missing/null field(s) (`wind`/`temp`/`solar`) rather than defaulting — RESEARCH.md Pitfall 5 and the module's own docstring ("must never swallow an exception; `DLRSafetyMonitor`'s `except Exception -> _fallback` is the single, already-correct mitigation boundary") both require this to propagate uncaught. Do NOT add a `try/except` inside `AnomalyDetector` for the model branch.

**Module docstring convention** (lines 1-19): update to add the third branch to the module-level description, matching the existing "Per D-04, the primary anomaly signal is..." paragraph style — name the new model branch, its D-01 raw-variable scope, and the D-06 OR-combination rule in prose, same register as the existing docstring.

---

### `backend/config.py` (config) — extend `ANOMALY_ML_*` block

**Analog:** `backend/config.py:229-276` (`FORECAST_ML_*` block, literal source, already read in full)

**Pattern to copy (structure, new names):**
```python
FORECAST_ML_MODEL_DIR: str = "data/models"
FORECAST_ML_MODEL_FILENAME_TEMPLATE: str = "forecast_{corridor}.joblib"
FORECAST_ML_TRAINING_FRAME_TEMPLATE: str = "training_frame_{corridor}.csv"
FORECAST_ML_FEATURE_WEATHER_COLUMNS: tuple[str, ...] = (
    "air_temp", "wind_speed", "solar_radiation",
)
FORECAST_ML_TRAINING_YEARS: int = 3
FORECAST_ML_BAKEOFF_SPLITS: int = 5
FORECAST_ML_BAKEOFF_REPORT_NAME: str = "bakeoff_report.json"
```
New equivalents (per RESEARCH.md's Recommended Project Structure and Pattern 2): `ANOMALY_ML_MODEL_DIR` (can reuse `FORECAST_ML_MODEL_DIR = "data/models"` — same directory, different filename template — RESEARCH.md explicitly allows sharing the dir), `ANOMALY_ML_MODEL_FILENAME_TEMPLATE = "anomaly_{corridor}.joblib"`, an `ANOMALY_ML_TRAINING_FRAME_TEMPLATE`, a `contamination` tunable (no forecast analog — new), and whatever bake-off/report filename constants the training script needs. Place immediately after the existing `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` / `DEFAULT_ANOMALY_CONTROL_LIMIT_K` block (config.py:290-300, already read) so all C10-related config stays contiguous, mirroring how `FORECAST_ML_*` is contiguous with the rest of the forecast block.

**Comment convention to copy** (config.py:278-289, the `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` preamble comment) — this codebase writes a multi-line rationale comment above every per-location config dict explaining *why* the values are what they are and citing the decision letter (D-06). Do the same for any new `ANOMALY_ML_*` per-location dict, citing D-03/D-04.

---

### `backend/anomaly_training.py` (new, service/offline-training, batch)

**Analog:** `backend/forecast_training.py` (full file, 615 lines, already read in full — this is the structural template, not just inspiration, per RESEARCH.md's "Key insight")

**Imports pattern** (forecast_training.py lines 22-40):
```python
import argparse
import json
import logging
import math
import os
import tempfile

import numpy as np
import pandas as pd

import ampacity_forecast
import config
import corridor_discretization
import historical_archive
import open_meteo_provider
import thermal_model
import units_def

logger = logging.getLogger(__name__)
```
Anomaly equivalent: swap `ampacity_forecast`/`corridor_discretization`/`historical_archive`/`thermal_model`/`units_def` for `anomaly_detector` (to reuse `_MODEL_CACHE`/`_model_path_for`-equivalent helpers once added there) and `ercot_data_retriever` (for D-02's training-only load characterization). Keep `open_meteo_provider` (same real weather source).

**Candidate-factory pattern** (forecast_training.py lines 43-86, `CANDIDATE_ESTIMATORS` dict of zero-arg factories):
```python
def _make_regression_candidate():
    from sklearn.ensemble import HistGradientBoostingRegressor
    return HistGradientBoostingRegressor(random_state=20260924)

CANDIDATE_ESTIMATORS: dict = {
    "HistGradientBoostingRegressor": _make_regression_candidate,
    "MLPRegressor": _make_neural_network_candidate,
}
```
Copy this exact shape for D-03's candidate set: lazy `sklearn` import inside each factory (keeps `import anomaly_training` free of a hard `sklearn` dependency, matching this module's stated convention), one factory per candidate (`IsolationForest` primary; `EllipticEnvelope`/`OneClassSVM` optional per D-04), same `random_state=20260924` fixed-seed convention for reproducibility.

**Atomic persistence pattern to copy verbatim** (forecast_training.py lines 444-471, `persist_corridor_model` — this is the literal function RESEARCH.md Pattern 2 names as the reference):
```python
def persist_corridor_model(model, corridor: str) -> str:
    import joblib
    os.makedirs(config.FORECAST_ML_MODEL_DIR, exist_ok=True)
    final_path = ampacity_forecast._model_path_for(corridor)
    fd, tmp_path = tempfile.mkstemp(
        dir=config.FORECAST_ML_MODEL_DIR, suffix=".joblib.tmp"
    )
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
Anomaly equivalent calls an `anomaly_detector._model_path_for(corridor)`-equivalent (new function to add to `anomaly_detector.py`, mirroring `ampacity_forecast._model_path_for` lines 235-244) and `config.ANOMALY_ML_MODEL_DIR`.

**CLI entry-point pattern to copy** (forecast_training.py lines 474-538, `main()` + `argparse.ArgumentParser`): same `--corridor` (choices from `config.CORRIDOR_ENDPOINTS`), `--years` flag shape; add a `--validate` flag per RESEARCH.md's Test Map (`anomaly_training.py --validate` entry point) instead of/alongside `--bakeoff`, to run the FP/FN measurement (Pitfall 1) and print/report it.

**Per-year weather fetch loop to copy** (forecast_training.py lines 89-109, `fetch_city_weather`) — reuse directly or call through `ampacity_forecast`/shared helper; also apply the same per-year looping discipline to the ERCOT load pull per RESEARCH.md Pitfall 2 (the installed `gridstatus`'s `end` param is a no-op, so a multi-year window needs one call per year, exactly like this function already does for Open-Meteo).

---

### `backend/tests/anomaly_training_test.py` (new, test, batch)

**Analog:** `backend/tests/forecast_training_test.py` (referenced in RESEARCH.md as a 361-line/10-test structure; not re-read in full this session — file confirmed tracked and present, same directory/naming convention as `anomaly_detector_test.py`)

**Pattern:** mirror its test-function organization (one test per pipeline stage: frame assembly, feature matrix, fit, persist round-trip, load-and-predict) rather than one monolithic end-to-end test — this matches `anomaly_detector_test.py`'s own per-behavior `test_*` convention (RESEARCH.md Validation Architecture, Wave 0 Gaps).

---

### `backend/tests/anomaly_detector_test.py` (extend existing)

**Analog:** itself — RESEARCH.md confirms this file already exists (200+ lines read this session), with an established per-behavior `test_*` convention and an existing test named `test_anomaly_resolves_through_existing_fallback_contract` that already exercises the `DLRSafetyMonitor` G6 fail-safe wiring. New tests for the model branch (OR-combination, missing-field `ValueError`, model-exception-propagates-to-fallback) should extend this file in the same style, not create a parallel test file.

---

### `docs/data-science/decisions/anomaly_detection_model.md` (new ADR)

**Analog:** `docs/data-science/decisions/forecasting_model.md` (Phase 1's honesty-first validation record; file tracked, not re-read line-by-line this session but its role/format is fully specified by CONTEXT.md D-07 and RESEARCH.md as the template to match)

**Pattern:** state the expectation before the verdict; report both FP rate (real clean data) and FN/recall rate (synthetic-injected anomalies) explicitly and separately, per RESEARCH.md Pitfall 1 — do not soften a "not met" result, matching Phase 1's own negative-result precedent for the forecasting model.

---

### `docs/data-science/specs/C10-anomaly-detection.md` (correction)

**Analog:** Phase 1's correction of the sibling C9 spec (same convention, not re-read this session — RESEARCH.md confirms C10's "Status: Not started" / "Current Implementation: None" lines are now stale and should be corrected the same way D-07 corrected C9).

## Shared Patterns

### OR-combination / additive-branch dispatch (D-05, D-06)
**Source:** `backend/anomaly_detector.py:101-140` (`check()`, to be restructured) — see RESEARCH.md Architecture Patterns, Pattern 1, lines 266-318, for the concrete accumulate-then-`any()` sketch.
**Apply to:** `anomaly_detector.py` only — this is the single dispatch site all three branches share.

### Fail-safe exception propagation (never catch inside the model layer)
**Source:** `backend/DLRSafetyMonitor.py:66-80` (`run_check`'s G6 block, already read in full):
```python
if self.anomaly_detector is not None:
    try:
        is_anomalous, reason = self.anomaly_detector.check(raw_data, rating)
    except Exception as exc:
        return self._fallback(result, "G6", f"detector error ({exc})", self.static_rating)
    if is_anomalous:
        return self._fallback(result, "G6", reason, self.static_rating)
```
**Apply to:** `_check_against_model`'s own error handling — raise `ValueError` (or let any exception propagate), never catch-and-neutralize inside `anomaly_detector.py`. This existing G6 wrapper is the only fail-safe boundary; zero changes needed here.

### Atomic model persistence (tempfile → joblib.dump → os.replace)
**Source:** `backend/forecast_training.py:444-471` (`persist_corridor_model`, literal source above).
**Apply to:** `anomaly_training.py`'s own persistence function.

### Per-corridor lazy-load + module-level cache
**Source:** `backend/ampacity_forecast.py:247-279` (`_MODEL_CACHE` dict + `_load_corridor_model`, literal source read this session):
```python
_MODEL_CACHE: dict = {}

def _load_corridor_model(corridor: str):
    if corridor in _MODEL_CACHE:
        return _MODEL_CACHE[corridor]
    path = _model_path_for(corridor)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"_load_corridor_model: no trained model for corridor "
            f"{corridor!r} at {path!r}. Train one with: "
            f".venv/bin/python3 backend/forecast_training.py --corridor {corridor}"
        )
    import joblib
    model = joblib.load(path)
    _MODEL_CACHE[corridor] = model
    return model
```
**Apply to:** `anomaly_detector.py` needs its own `_model_path_for`/`_load_corridor_model`/`_MODEL_CACHE` trio (or equivalent private helpers), closed-set corridor validation preserved (`corridor not in config.CORRIDOR_ENDPOINTS` guard, matching `_model_path_for`'s docstring-stated path-traversal mitigation) since `data/models/*.joblib` deserialization via `joblib.load` executes arbitrary pickled objects (RESEARCH.md Security Domain, Known Threat Patterns) — never accept a caller-supplied path.

### Cyclical time-of-day feature encoding
**Source:** `backend/ampacity_forecast.py:124-159` (`build_ml_features`, `hour_sin`/`hour_cos` lines 156-157):
```python
features["hour_sin"] = np.sin(2 * np.pi * hours / 24.0)
features["hour_cos"] = np.cos(2 * np.pi * hours / 24.0)
```
**Apply to:** the anomaly model's feature engineering, if time-of-day features are included (Claude's Discretion item), for consistency with the one existing cyclical-encoding convention in this codebase.

### Per-location config dict + rationale comment
**Source:** `backend/config.py:278-300` (`ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` + preamble comment + `DEFAULT_ANOMALY_CONTROL_LIMIT_K`, literal source already read).
**Apply to:** any new `ANOMALY_ML_*` per-location/per-corridor dict this phase adds.

## No Analog Found

None — every file in scope has at least a role-match analog. The one partial-match item is the C10 spec's "Not started" language correction, whose analog (Phase 1's C9 spec correction) was not re-read verbatim this session but is referenced consistently by both CONTEXT.md and RESEARCH.md as the template to follow; the planner should locate that specific diff via `git log -p -- docs/data-science/specs/C9-*.md` around Phase 1's completion if an exact textual template is needed.

## Metadata

**Analog search scope:** `backend/` (anomaly_detector.py, ampacity_forecast.py, forecast_training.py, config.py, DLRSafetyMonitor.py, tests/), `docs/data-science/` (specs/, decisions/)
**Files scanned/read this session:** `backend/anomaly_detector.py` (full), `backend/forecast_training.py` (full), `backend/ampacity_forecast.py` (lines 210-339, plus grep-located feature/cache/dispatch line numbers), `backend/config.py` (lines 225-305), `backend/DLRSafetyMonitor.py` (lines 55-93, plus grep-located bounds/gate lines) — all cross-referenced against RESEARCH.md's own already-cited line numbers for the remaining sections (module docstrings, `ML_FEATURE_COLUMNS`, `_gate_sensor`) to avoid re-reading ranges RESEARCH.md already quoted verbatim.
**Pattern extraction date:** 2026-09-24
