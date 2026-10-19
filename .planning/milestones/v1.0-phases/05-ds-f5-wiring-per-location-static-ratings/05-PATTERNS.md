# Phase 5: DS-F5 Wiring: Per-Location Static Ratings - Pattern Map

**Mapped:** 2026-09-09
**Files analyzed:** 2 (modified only, no new files)
**Analogs found:** 2 / 2 (both use the same in-repo analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `backend/dlr_pipeline.py` (`run_pipeline`) | service (pipeline orchestrator) | transform (CRUD-adjacent: compute + return DataFrame) | `backend/corridor_discretization.py` `corridor_geometry` (lines 242-271) | role-match (lookup pattern exact, surrounding shape differs — DLR pipeline transforms a fetched DataFrame vs. corridor_geometry building a geometry struct) |
| `backend/dlr_pipeline.py` (`plot_dlr_summary`) | utility (visualization) | transform | `backend/corridor_discretization.py` `corridor_geometry` (lines 257-260, the rating-lookup lines only) | partial (only the lookup expression is analogous; plotting has no equivalent elsewhere) |
| `backend/dlr_pipeline.py` `__main__` block (lines 420-461) | config/entry-point (demo driver) | request-response (script invocation) | same file, existing call at lines 454/461 (self-analog — only the argument changes) | exact |
| `backend/ercot_dlr_merger.py` (`process_dlr_to_hourly`) | service (data transform) | CRUD/transform | `backend/corridor_discretization.py` `corridor_geometry` (lines 242-260) | role-match (same "explicit city key → STATIC_RATINGS lookup" pattern, different surrounding computation — MW conversion vs. corridor geometry) |
| `backend/ercot_dlr_merger.py` `__main__` block (lines 118-119) | config/entry-point (demo driver) | request-response (script invocation) | same file, existing call at line 128 (self-analog) | exact |

## Pattern Assignments

### `backend/dlr_pipeline.py::run_pipeline` (service, transform)

**Analog:** `backend/corridor_discretization.py::corridor_geometry`, lines 242-260

**Current signature to modify** (lines 182-189):
```python
def run_pipeline(
    stids:          list[str],
    start:          str,
    end:            str,
    conductor:      thermal_model.ConductorConfig,
    static_rating:  float = 900.0,    # A — conventional static rating for comparison
    solar_alt_deg:  float = 45.0,
) -> pd.DataFrame:
```

**Analog's explicit-city-key lookup pattern** (`corridor_discretization.py` lines 248, 257):
```python
city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor_name]
...
static_rating = min(config.STATIC_RATINGS[city_a], config.STATIC_RATINGS[city_b])
```
Note: the analog uses direct bracket indexing (`STATIC_RATINGS[city_a]`) because `corridor_geometry` already validated `corridor_name` against `CORRIDOR_ENDPOINTS` earlier (raises `KeyError` at lines 242-246) — every `city_a`/`city_b` is guaranteed present. **`run_pipeline` must NOT copy the bracket form** — per CONTEXT.md D-02, unknown/`None` cities must silently fall back, so use `.get()`:
```python
def run_pipeline(
    stids:          list[str],
    start:          str,
    end:            str,
    conductor:      thermal_model.ConductorConfig,
    city:           str = None,       # e.g. "AUSTIN" — resolves per-location static rating
    solar_alt_deg:  float = 45.0,
) -> pd.DataFrame:
    ...
    static_rating = config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)
```

**Core usage site to preserve unchanged** (lines 233-234, only the source of `static_rating` changes):
```python
obs["dlr_headroom_pct"] = (obs["dlr_amps"] - static_rating) / static_rating * 100
obs["dlr_uplift_flag"]  = obs["dlr_amps"] > static_rating
```

**Docstring pattern to update** (lines 190-202) — analog has no docstring for this line, but existing `run_pipeline` docstring already documents `static_rating`; replace that Args entry with a `city` entry mirroring the analog's inline comment style (`corridor_discretization.py` line 231-236 block comment explaining the "weakest link" rationale) — here the rationale is simpler: "resolves this station's per-city static rating from `config.STATIC_RATINGS`; unmatched/`None` city falls back to `config.DEFAULT_STATIC_RATING`."

---

### `backend/dlr_pipeline.py::plot_dlr_summary` (utility, transform)

**Analog:** same lookup expression as above.

**Current signature** (line 324):
```python
def plot_dlr_summary(df: pd.DataFrame, static_rating: float = 900.0, output_dir: str=".", file_prefix: str="dlr"):
```

**Target shape:**
```python
def plot_dlr_summary(df: pd.DataFrame, city: str = None, output_dir: str=".", file_prefix: str="dlr"):
    ...
    static_rating = config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)
```

**Usage sites to preserve unchanged** (lines 348-350) — `static_rating` local var is consumed identically once resolved:
```python
ax1.axhline(static_rating, color="red", ls="--", lw=1.5, label=f"Static Rating ({static_rating:.0f} A)")
ax1.fill_between(sub.index, static_rating, sub["dlr_amps"],
                 where=(sub["dlr_amps"] > static_rating),
                 alpha=0.2, color="green", label="Uplift headroom")
```
Note: `dlr_pipeline.py` does not currently `import config` at module top — verify/add the import (check existing imports near top of file; `corridor_discretization.py` and `ercot_dlr_merger.py` both do `import config`, following that same convention).

---

### `backend/dlr_pipeline.py` `__main__` block (entry-point, request-response)

**Analog:** self — existing lines 454, 461, only the passed argument changes (D-06).

**Before** (lines ~454, 461):
```python
        static_rating  = config.DEFAULT_STATIC_RATING,
...
        plot_dlr_summary(results, static_rating=config.DEFAULT_STATIC_RATING, output_dir=OUTPUT_PLOTS, file_prefix=f"{START.split('T')[0]}_{END.split('T')[0]}")
```

**After:**
```python
        city           = "AUSTIN",
...
        plot_dlr_summary(results, city="AUSTIN", output_dir=OUTPUT_PLOTS, file_prefix=f"{START.split('T')[0]}_{END.split('T')[0]}")
```
Rationale: `__main__` already hardcodes `config.DEFAULT_STATION_SOURCE = "data/wtm_stations_austin.csv"` (config.py line 170) — this is unambiguously Austin data (D-06).

---

### `backend/ercot_dlr_merger.py::process_dlr_to_hourly` (service, CRUD/transform)

**Analog:** `backend/corridor_discretization.py::corridor_geometry` explicit-city-key + `.get()` fallback pattern (same as `run_pipeline` above — reuse identically, do not copy the bracket-indexing form since no upstream validation of `city` exists here).

**Current signature and rating usage** (lines 25, 44):
```python
def process_dlr_to_hourly(dlr_csv_path: str) -> pd.DataFrame:
    """Loads 5-min DLR data and resamples to Hourly worst-case."""
    ...
    hourly["static_capacity_mw"] = amps_to_mw(config.DEFAULT_STATIC_RATING, LINE_VOLTAGE_KV, POWER_FACTOR)
    return hourly.reset_index()
```

**Target shape** (per CONTEXT.md D-04, D-05 — one city per call, `city` param added, default `None` preserves existing test behavior):
```python
def process_dlr_to_hourly(dlr_csv_path: str, city: str = None) -> pd.DataFrame:
    """Loads 5-min DLR data and resamples to Hourly worst-case."""
    df = pd.read_csv(dlr_csv_path)
    ...
    static_rating = config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)
    hourly["dlr_capacity_mw"] = amps_to_mw(hourly["dlr_amps"], LINE_VOLTAGE_KV, POWER_FACTOR)
    hourly["static_capacity_mw"] = amps_to_mw(static_rating, LINE_VOLTAGE_KV, POWER_FACTOR)
    return hourly.reset_index()
```
`config` is already imported at module top (line 7) — no import change needed here, unlike `dlr_pipeline.py`.

**Backward-compat constraint (D-04):** `backend/tests/ercot_dlr_merger_test.py::test_hourly_resample_uses_min_not_mean` calls `process_dlr_to_hourly(str(csv_path))` with no `city` — new default `city=None` must resolve to `config.DEFAULT_STATIC_RATING` (900.0 A), identical numeric result to current unconditional `config.DEFAULT_STATIC_RATING` usage. Do not reorder existing positional param (`dlr_csv_path` stays first); append `city` after it.

---

### `backend/ercot_dlr_merger.py` `__main__` block (entry-point, request-response)

**Analog:** self — existing line 128 call, only the argument changes (D-07).

**Before** (line 128):
```python
        dlr_hourly = process_dlr_to_hourly(DLR_FILE)
```

**After:**
```python
        dlr_hourly = process_dlr_to_hourly(DLR_FILE, city="AUSTIN")
```
Rationale: `TARGET_STATION = "AN489"` (line 119) is an Austin-network WTM station (D-07).

---

## Shared Patterns

### Explicit city-key rating resolution with silent fallback
**Source:** `backend/corridor_discretization.py` lines 248-260 (`corridor_geometry`), adapted from bracket-indexing (`STATIC_RATINGS[city]`, which assumes pre-validated keys) to `.get()`-with-default (no validation, silent fallback) per CONTEXT.md D-02.
**Apply to:** `run_pipeline`, `plot_dlr_summary` (`backend/dlr_pipeline.py`), `process_dlr_to_hourly` (`backend/ercot_dlr_merger.py`).
```python
static_rating = config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)
```
Do NOT use `config.STATIC_RATINGS[city]` (KeyError on miss) in any of the three target functions — that form is only safe in `corridor_geometry` because it validates `corridor_name` against `CORRIDOR_ENDPOINTS` first and both cities in `CORRIDOR_ENDPOINTS` are guaranteed to also be `STATIC_RATINGS` keys.

### Config source of truth
**Source:** `backend/config.py` lines 41-51 (`STATIC_RATINGS` dict, `DEFAULT_STATIC_RATING` fallback).
**Apply to:** All three target functions — no new config entries needed, just consult the existing dict/fallback instead of hardcoding `config.DEFAULT_STATIC_RATING` unconditionally.

### `__main__` demo wiring — Austin-only for this phase
**Source:** existing hardcoded `TARGET_STATION = "AN489"` (`ercot_dlr_merger.py` line 119) and `config.DEFAULT_STATION_SOURCE = "data/wtm_stations_austin.csv"` (`config.py` line 170).
**Apply to:** Both `__main__` blocks — pass `city="AUSTIN"` literal; do not build a multi-city loop (explicitly deferred, D-08/D-09).

## No Analog Found

None — all target files/functions have a direct in-repo analog (`corridor_discretization.py::corridor_geometry`) for the core lookup pattern. No files require falling back to external/research-only patterns.

## Metadata

**Analog search scope:** `backend/` (specifically `corridor_discretization.py`, `dlr_pipeline.py`, `ercot_dlr_merger.py`, `config.py`, `tests/ercot_dlr_merger_test.py`)
**Files scanned:** 5
**Pattern extraction date:** 2026-09-09
