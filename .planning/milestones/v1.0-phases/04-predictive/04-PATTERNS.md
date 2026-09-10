# Phase 4: Predictive - Pattern Map

**Mapped:** 2026-09-08
**Files analyzed:** 9 (3 new modules, 3 new test files, 3 modified files) + `requirements.txt`
**Analogs found:** 9 / 9 (all direct in-repo matches; no external-only patterns needed)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `backend/historical_archive.py` (new) | utility / storage | file-I/O (append) | `backend/dlr_pipeline.py::export_results` | role-match (CSV persistence convention) |
| `backend/ampacity_forecast.py` (new, C9) | service | transform (batch/CRUD-read) | `backend/DLRSafetyMonitor.py` (computation module, no I/O) | role-match |
| `backend/anomaly_detector.py` (new, C10) | service | transform / event-driven (gate check) | `backend/DLRSafetyMonitor.py::_gate_*` methods | exact (gate-shaped check contract) |
| `backend/DLRSafetyMonitor.py` (modify, add G6) | controller / gate-chain | request-response | itself — existing G1-G5 pattern | exact |
| `backend/units_def.py` (modify, add v2 schema) | model / schema | CRUD (validation) | itself — existing `PIPELINE_SCHEMA` | exact |
| `backend/config.py` (modify, add constants) | config | CRUD (static lookup) | itself — `RATING_BOUNDS_BY_LOCATION`/`DELTA_FRACTION` | exact |
| `backend/tests/historical_archive_test.py` (new) | test | file-I/O | `backend/tests/SafetyMonitor_TestSuite.py` | role-match |
| `backend/tests/ampacity_forecast_test.py` (new) | test | transform | `backend/tests/SafetyMonitor_TestSuite.py` | role-match |
| `backend/tests/anomaly_detector_test.py` (new) | test | event-driven (gate) | `backend/tests/SafetyMonitor_TestSuite.py` | exact (gate-failure test shape) |
| `requirements.txt` (new) | config | — | `README.md:33` prose `pip install` line | no analog (new convention) |

## Pattern Assignments

### `backend/historical_archive.py` (new — utility/storage, file-I/O)

**Analog:** `backend/dlr_pipeline.py::export_results` (lines 392-413)

**Core CSV-write pattern to copy** (`backend/dlr_pipeline.py:392-413`):
```python
def export_results(df: pd.DataFrame, output_path: str = ".", file_prefix: str="."):
    """Export pipeline output to CSV."""
    cols = [
        "stid", "datetime_utc",
        "air_temp", "wind_speed", "wind_direction", "wind_perp_ms",
        "solar_radiation", "relative_humidity",
        "dlr_amps", "dlr_headroom_pct", "dlr_uplift_flag",
    ]
    out = df[[c for c in cols if c in df.columns]]
    stations = out["stid"].unique()

    for stid in stations:
        sub = out[out["stid"] == stid]
        filename = f"{file_prefix}_{stid}.csv"
        filepath = os.path.join(output_path, filename)
        sub.to_csv(filepath, index=False)
        log.info(f"  Results exported → {filepath}  ({len(sub):,} rows)")
```
**What to adapt:** `historical_archive.py::append_observation(row: dict)` is a single-row **append** (not a full-DataFrame overwrite like `export_results`) — use `pd.DataFrame([row]).to_csv(path, mode="a", header=not os.path.exists(path), index=False)` or equivalent. Keep the same "one call site" discipline referenced in RESEARCH.md Pattern 3. Validate `row` via `units_def.validate_pipeline_row(row, strict=False)` before writing (per Security Domain V5 — archive poisoning mitigation), matching `dlr_pipeline.py`'s own non-strict `validate_pipeline_output` convention (see `backend/dlr_pipeline.py` around `run_pipeline`/`validate_pipeline_output` — grep confirms this call exists near line 182+).

**Fail-safe wrap (Pitfall 6 — never block the rating path):**
```python
def append_observation(row: dict, path: str = "data/historical/ampacity_history.csv") -> bool:
    try:
        # validate + append
        ...
        return True
    except Exception as exc:
        logging.getLogger(__name__).warning(f"historical_archive append failed (non-fatal): {exc}")
        return False
```
This mirrors `DLRSafetyMonitor._fallback`'s "never let a subsystem error propagate to a crash" philosophy (DS-NF5), applied to I/O instead of a gate.

**Module docstring convention to copy** (see `backend/corridor_discretization.py:1-24` for the "what this module is, what spec it implements, what it composes/does not do" docstring shape — apply the same shape: state this is a new support module for C9/C10, not a spec component itself, and that it has one call site per corridor per run per D-08).

---

### `backend/ampacity_forecast.py` (new, C9 — service, transform)

**Analog:** `backend/DLRSafetyMonitor.py` (pure-computation class shape, no I/O) + `backend/thermal_model.py` (float-wrap convention)

**Float-wrap pitfall to copy** (`backend/DLRSafetyMonitor.py:84-91`):
```python
def _compute_ampacity(self, d):
    return float(thermal_model.ieee738_ampacity(
        T_amb_c=d["temp"],
        wind_perp_ms=d["wind"],
        ghi_wm2=d["solar"],
        conductor=self.conductor,
        solar_altitude_deg=self.solar_altitude_deg,
    ))
```
Any new code in `ampacity_forecast.py` that reads a computed/archived `dlr_amps` value and does arithmetic on it (EWM, residuals, quantiles) must apply the same `float(...)` wrap at the boundary where it leaves pandas/numpy and is compared/returned (RESEARCH.md Pitfall 2). `pandas.Series.ewm().mean()` returns a Series/float-like already, but any `.iloc[-1]` scalar extraction should still be explicitly `float(...)`-wrapped defensively at the API boundary (the return of the public forecast function), matching this codebase's existing convention rather than trusting pandas' dtype.

**Class/constructor shape to mirror** (`backend/DLRSafetyMonitor.py:15-24`, constructor-injection convention):
```python
def __init__(self, static_rating: float, conductor=None, solar_altitude_deg: float = 45.0,
             rating_bounds=None, delta_fraction=None, logger=None):
    self.static_rating   = static_rating
    self.conductor        = conductor if conductor is not None else thermal_model.ConductorConfig(
        **config.DEFAULT_CONDUCTOR_CONFIG_KWARGS)
    ...
```
Apply the same "constructor takes explicit args with `config.py`-sourced defaults when `None`" shape for any forecast-horizon/window constants (`config.FORECAST_HORIZON_MINUTES` etc., D-01).

---

### `backend/anomaly_detector.py` (new, C10 — service, event-driven gate check)

**Analog:** `backend/DLRSafetyMonitor.py::_gate_plausible` / `_gate_delta` (lines 75-82) — the existing gate-check method shape C10 must mirror in its own `.check(...)` method, and the constructor-injection + `_fallback` resolution shape from Pattern 2 (RESEARCH.md).

**Gate-check method shape to copy** (`backend/DLRSafetyMonitor.py:78-82`):
```python
def _gate_delta(self, rating) -> bool:
    # Inclusive boundary, matching _gate_plausible/_gate_range's
    # inclusive convention: a delta exactly equal to the threshold is
    # not a swing.
    return abs(rating - self.last_good_rating) <= self.delta_fraction * self.static_rating
```
`anomaly_detector.py`'s public method (e.g. `check(raw_data, rating) -> (bool, str)`) should return the same "boolean + reason string" shape `_gate_*` implies, so `DLRSafetyMonitor`'s new G6 branch can consume it directly (per D-05/Pattern 2 sketch below).

**G6 integration point — exact insertion in `backend/DLRSafetyMonitor.py`, after line 62 (`return result` of the existing `run_check`)**, per RESEARCH.md Pattern 2 and CONTEXT.md D-05:
```python
def __init__(self, ..., anomaly_detector=None, logger=None):
    ...
    self.anomaly_detector = anomaly_detector  # None = C10 disabled, G1-G5 unchanged

def run_check(self, raw_data: dict) -> dict:
    ...  # G1-G5 unchanged, ending at:
    self.last_good_rating = rating
    result["status"] = "ok"
    result["rating"] = rating

    # G6 — learned anomaly signal (C10), additive: never runs if no detector injected
    if self.anomaly_detector is not None:
        try:
            is_anomalous, reason = self.anomaly_detector.check(raw_data, rating)
        except Exception as exc:
            return self._fallback(result, "G6", f"detector error ({exc})", self.static_rating)
        if is_anomalous:
            return self._fallback(result, "G6", reason, self.static_rating)

    return result
```
**Resolves through the existing, unmodified `_fallback` helper** (`backend/DLRSafetyMonitor.py:93-98`) — do not add a second result shape:
```python
def _fallback(self, result, gate, reason, rating):
    msg = f"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"
    self.logger(msg)
    result.update({"status": "fallback", "rating": rating, "fallback": True,
                    "alerts": [msg]})
    return result
```

---

### `backend/config.py` (modify — add D-06/D-01 constants)

**Analog:** itself — `RATING_BOUNDS_BY_LOCATION` (lines 63-68) is the exact per-location dict shape to copy for the new anomaly control-limit constant (D-06 explicitly requires this shape, citing the historical `RATING_BOUNDS` global-vs-per-location bug documented in `03-PATTERNS.md`).

**Pattern to copy** (`backend/config.py:63-68`):
```python
RATING_BOUNDS_BY_LOCATION: dict[str, tuple[float, float]] = {
    "AUSTIN": (800.0, 3000.0),
    "CORPUS_CHRISTI": (1000.0, 5000.0),
    "MIDLAND": (600.0, 3000.0),
    "EL_PASO": (600.0, 2300.0),
}
```
New constant should follow this exact shape, e.g. `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION: dict[str, float]` (a per-city multiplier `k` for mean ± k·std), plus a single flat `FORECAST_HORIZON_MINUTES = 60` constant (D-01, reversible — "a config-level horizon constant") following the simpler flat-value convention already used by `DELTA_FRACTION: float = 0.15` (`backend/config.py:83`). Include a comment block matching the file's existing section-header convention (`# ──── ... ────`) and cite D-06/03-PATTERNS.md the way `RATING_BOUNDS_BY_LOCATION`'s own comment cites the historical bug it fixes (lines 56-62).

---

### `backend/units_def.py` (modify — additive `PIPELINE_SCHEMA` v2)

**Analog:** itself — `PIPELINE_SCHEMA` (lines 324-375, confirmed at this session's read).

**Exact existing shape to extend, never redefine:**
```python
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
**Additive extension to append** (new keys only, `"required": False`, plus a new module-level `PIPELINE_SCHEMA_VERSION` constant placed immediately above the dict per RESEARCH.md Pattern 1):
```python
PIPELINE_SCHEMA_VERSION = 2  # bumped from 1 (Phase 1-3 baseline) — Phase 4 (C9/C10) additions

PIPELINE_SCHEMA: Dict[str, Dict] = {
    # ... existing v1 columns, UNCHANGED ...

    # --- v2 additions (Phase 4 / C9, C10) ---
    "forecast_horizon_min": {"unit": "min", "range": (0.0, 1440.0), "required": False},
    "forecast_amps":        {"unit": "A",   "range": (100.0, 4000.0), "required": False},
    "forecast_ci_lower_amps": {"unit": "A", "range": (0.0, 4000.0), "required": False},
    "forecast_ci_upper_amps": {"unit": "A", "range": (0.0, 8000.0), "required": False},
    "anomaly_score": {"unit": "pu", "range": (0.0, None), "required": False},
}
```
`validate_pipeline_row` (lines ~377+) already iterates `PIPELINE_SCHEMA.items()` generically — no change needed there for additive keys to be picked up automatically.

---

### `backend/tests/historical_archive_test.py`, `ampacity_forecast_test.py`, `anomaly_detector_test.py` (new — test)

**Analog:** `backend/tests/SafetyMonitor_TestSuite.py` (read in full)

**Fixture pattern to copy** (`backend/tests/SafetyMonitor_TestSuite.py:1-27`):
```python
import pytest

import config
import thermal_model
from DLRSafetyMonitor import DLRSafetyMonitor


@pytest.fixture
def monitor():
    return DLRSafetyMonitor(
        static_rating=1690.0,
        conductor=thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS),
        logger=lambda msg: None,
    )


@pytest.fixture
def valid_data():
    return {
        "sensor_status": "ok", "link_status": "ok",
        "wind": 5.0, "temp": 25.0, "solar": 500.0,
    }
```

**Direct-override injection pattern for deterministic synthetic-anomaly tests** (`backend/tests/SafetyMonitor_TestSuite.py:122-123`, cited directly in RESEARCH.md's Wave 0 Gaps):
```python
def test_gate_4_fails_when_rating_is_implausibly_low(monitor, valid_data):
    monitor._compute_ampacity = lambda d: 300
    result = monitor.run_check(valid_data)
    assert result["status"] == "fallback"
```
For `anomaly_detector_test.py::test_synthetic_anomaly_triggers_fallback`, mirror this exact style: inject `monitor.anomaly_detector = FakeDetector(is_anomalous=True, reason="synthetic spike")` (a stub with a `.check()` method), then assert `result["status"] == "fallback"`, `result["fallback"] is True`, and `"G6 FAIL" in result["alerts"][0]` — the same assertion shape as every existing `test_gate_*` test (`assert result["status"] == "fallback"`, `assert result["fallback"] is True`, `assert "G{n} FAIL" in result["alerts"][0]`, seen repeatedly at lines 100-118+ of `SafetyMonitor_TestSuite.py`).

Naming convention note: existing test files use two different suffix styles in this repo — `SafetyMonitor_TestSuite.py` (PascalCase+`_TestSuite`) vs. `corridor_discretization_test.py`/`units_def_test.py`/`thermal_model_test.py`/`ercot_dlr_merger_test.py` (snake_case+`_test`). RESEARCH.md's own Wave 0 Gaps section and `pytest.ini`'s `python_files = test_*.py *_test.py *_TestSuite.py` both confirm `*_test.py` is the dominant/matched convention — use `historical_archive_test.py`, `ampacity_forecast_test.py`, `anomaly_detector_test.py` (already the names RESEARCH.md specifies), matching the majority snake_case convention, not the one-off `SafetyMonitor_TestSuite.py` style.

---

### `requirements.txt` (new, D-11)

**No in-repo analog** (first file of its kind — `README.md:33` and `backend/dlr_pipeline.py:8` only have prose `pip install ...` lines). Pin the exact versions verified this session in RESEARCH.md's Environment Availability table:
```
pandas==2.3.3
numpy==2.4.3
scipy==1.17.1
pytest==9.0.3
```
Do not add `scikit-learn`/`statsmodels` — Tier 2 is explicitly out of scope this phase (D-10) and both packages are flagged SUS pending a `checkpoint:human-verify` gate per RESEARCH.md's Package Legitimacy Audit.

## Shared Patterns

### Fail-safe-by-default / single fallback contract (DS-NF5)
**Source:** `backend/DLRSafetyMonitor.py::_fallback` (lines 93-98) + `run_check` (lines 26-62)
**Apply to:** `anomaly_detector.py` (must resolve exclusively through this helper, never its own result shape — Pitfall 4), `historical_archive.py` (archive-write failure must degrade to "not archived," never propagate — Pitfall 6, same philosophy applied to I/O instead of a gate)
```python
def _fallback(self, result, gate, reason, rating):
    msg = f"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"
    self.logger(msg)
    result.update({"status": "fallback", "rating": rating, "fallback": True,
                    "alerts": [msg]})
    return result
```

### Centralized config, one call site (C1 discipline)
**Source:** `backend/config.py` (whole-file convention: `STATIC_RATINGS`, `RATING_BOUNDS_BY_LOCATION`, `DELTA_FRACTION`, `DEFAULT_CONDUCTOR_CONFIG_KWARGS`)
**Apply to:** All new tunable constants — `FORECAST_HORIZON_MINUTES` (D-01), `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` (D-06) — must live in `config.py`, never as a literal inside `ampacity_forecast.py`/`anomaly_detector.py`.

### Additive schema versioning
**Source:** `backend/units_def.py::PIPELINE_SCHEMA` (lines 324-375)
**Apply to:** Any new forecast/anomaly output column — append-only, `"required": False`, bump `PIPELINE_SCHEMA_VERSION`, never mutate an existing key's `unit`/`range`.

### `float(...)` boundary wrap for computed ampacity
**Source:** `backend/DLRSafetyMonitor.py::_compute_ampacity` (lines 84-91)
**Apply to:** Any new code (`ampacity_forecast.py`, `anomaly_detector.py`) that reads `thermal_model.ieee738_ampacity` output or an archived `dlr_amps` value and does arithmetic/comparison on it.

### Constructor-injection over global state
**Source:** `backend/DLRSafetyMonitor.py.__init__` (lines 15-24), call site `backend/corridor_discretization.py::rate_corridor` (lines ~535-539)
**Apply to:** `DLRSafetyMonitor.__init__`'s new `anomaly_detector=None` param (D-05); `rate_corridor`'s monitor-construction call site is the natural place to wire an actual detector instance in later once one exists, but is unaffected (`None` default) until then.
```python
monitor = DLRSafetyMonitor(
    static_rating=geometry.static_rating,
    conductor=geometry.conductor,
    rating_bounds=geometry.rating_bounds,
)
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `requirements.txt` | config | — | First dependency-pinning file in the repo; no prior convention beyond prose `pip install` lines (`README.md:33`, `backend/dlr_pipeline.py:8`) |

## Metadata

**Analog search scope:** `backend/` (all `.py` modules and `backend/tests/`), `backend/config.py`, `backend/units_def.py`, `README.md`
**Files scanned:** `DLRSafetyMonitor.py`, `config.py`, `units_def.py`, `corridor_discretization.py`, `dlr_pipeline.py`, `SafetyMonitor_TestSuite.py`, `thermal_model.py` (referenced), test directory listing
**Pattern extraction date:** 2026-09-08
</content>
