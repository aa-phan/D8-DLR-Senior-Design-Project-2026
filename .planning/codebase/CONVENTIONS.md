# Coding Conventions

**Analysis Date:** 2026-09-02

## Naming Patterns

**Files:**
- Modules use `snake_case` with descriptive names: `dlr_pipeline.py`, `thermal_model.py`, `ercot_data_retriever.py`
- Modules related to a feature may use descriptive prefixes: `ercot_dlr_merger.py`, `units_def.py`
- Some class-focused files use PascalCase for prominent classes: `DLRSafetyMonitor.py` (defines `DLRSafetyMonitor` class)

**Functions:**
- All functions use `snake_case`: `perpendicular_wind()`, `fetch_timeseries()`, `get_wtm_stations()`, `_air_density()`
- Private/internal functions prefixed with single underscore: `_air_density()`, `_dynamic_viscosity()`, `_gate_sensor()`

**Variables:**
- Local variables use `snake_case`: `stid`, `wind_perp_ms`, `conductor`, `hourly_data`
- Module-level constants use `UPPERCASE`: `WIND_BOUNDS`, `TEMP_BOUNDS`, `RATING_BOUNDS`, `STATIC_RATINGS`, `DEFAULT_STATIC_RATING`
- Type-converted values: `ws = np.asarray(wind_speed_ms, dtype=float)` — shortened variable names for array operations

**Classes:**
- All classes use `PascalCase`: `ConductorConfig`, `DLRSafetyMonitor`, `Q` (Quantity)
- Instance attributes in `snake_case`: `self.static_rating`, `self.last_good_rating`, `self.T_max`
- Class constants in `UPPERCASE`: `WIND_BOUNDS`, `TEMP_BOUNDS`, `SOLAR_BOUNDS`

## Code Style

**Formatting:**
- No explicit formatter configured (no `.prettierrc`, no `black` config detected)
- Follow standard Python conventions: PEP 8 style
- Indentation: 4 spaces (observed throughout codebase)
- Line length: No enforced limit detected; files vary from 70–100+ characters

**Linting:**
- No linting configuration detected (no `.pylintrc`, `.flake8`, or `pyproject.toml`)
- Code is written to follow standard Python conventions without automated checking

**Comments and Sections:**
- Section dividers use extended dashes: `# ──────────────────────────────────────────────────────────────────────────────`
- Sections group related functionality with clear headings: `# SYNOPTIC API HELPERS`, `# PERPENDICULAR WIND COMPONENT`
- Inline comments explain WHY, not WHAT: see `backend/config.py` lines 22–41 explaining why 900A was chosen rather than just stating the value

## Import Organization

**Order:**
1. Standard library imports (`os`, `math`, `json`, `logging`, `requests`, `datetime`, `warnings`, etc.)
2. Type hints from `typing` (e.g., `from typing import Optional, Union, Dict, Callable`)
3. Third-party imports (`numpy`, `pandas`, `matplotlib`, `scipy`, etc.)
4. Future imports at the very top if used (e.g., `from __future__ import annotations`)
5. Local/project imports (relative imports and module imports): `from units_def import ...`, `import thermal_model`, `import config`

**Import Style:**
- Mix of `import module` and `from module import function` depending on usage
- Local imports typically use absolute imports from backend: `import thermal_model`, `from units_def import ...`
- Test files use sys.path manipulation when needed: `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`

**No path aliases detected** — all imports are standard Python paths relative to pythonpath (set to `backend` in `pytest.ini`)

## Type Hints

**Usage:**
- Type hints used consistently in function signatures
- Mix of built-in types and typing module: `Union[float, np.ndarray]`, `Optional[tuple]`, `dict[str, float]`, `list[str]`
- NumPy type hints: `np.ndarray`, and operations return typed arrays
- Dataclasses use type hints: `@dataclass` with annotated fields

**Pattern:**
```python
def perpendicular_wind(
    wind_speed_ms: Union[float, np.ndarray],
    wind_dir_deg: Union[float, np.ndarray],
    line_azimuth_deg: float,
) -> np.ndarray:
```

## Docstrings

**Format:** Google-style docstrings (triple-quoted strings with Args, Returns sections)

**Module-level:**
- Every module starts with a comprehensive docstring explaining purpose and relationship to specs
- Example from `backend/thermal_model.py`:
  ```python
  """
  Thermal Model / IEEE 738 (C5)
  ==================================================
  Pure physics core: steady-state IEEE 738 conductor ampacity from weather
  inputs and conductor properties. No ingestion, no orchestration, no
  `__main__` side effects — importable and callable without a SYNOPTIC_TOKEN
  env var or any file I/O.
  
  Every other component (C7, C8, C9) that needs an IEEE 738 rating should
  import and call this module rather than reimplementing the formula.
  """
  ```

**Function-level:**
- Functions include Args and Returns sections
- Example from `backend/thermal_model.py`:
  ```python
  def perpendicular_wind(
      wind_speed_ms: Union[float, np.ndarray],
      wind_dir_deg: Union[float, np.ndarray],
      line_azimuth_deg: float,
  ) -> np.ndarray:
      """
      Compute the wind speed component perpendicular to the transmission line.
      
      IEEE 738 uses effective cooling wind; the perpendicular component is
      what drives forced convection. For angles < 20° use minimum value
      to avoid instability in natural convection regime.
      
      Args:
          wind_speed_ms:   Measured wind speed (m/s)
          wind_dir_deg:    Meteorological wind direction (degrees from North)
          line_azimuth_deg: Compass bearing of the transmission line (0–360°)
      
      Returns:
          Effective perpendicular wind component (m/s), shape matching inputs
      """
  ```

**Class-level:**
- Classes have docstrings explaining their purpose
- Example: `backend/DLRSafetyMonitor.py`
  ```python
  class DLRSafetyMonitor:
      """
      Encapsulates all 5 pipeline safety gates for DLR data validation.
      Call run_check() each measurement cycle; it returns a SafetyResult.
      """
  ```

## Error Handling

**Patterns:**
- Custom exception classes for domain-specific errors: `UnitError` in `backend/units_def.py`
- Standard exceptions for common cases: `EnvironmentError` for missing configuration
- HTTP errors use `.raise_for_status()` on requests: `r.raise_for_status()`
- Early return pattern in validation/gate methods: if condition fails, return error immediately

**Example from `backend/DLRSafetyMonitor.py`:**
```python
def run_check(self, raw_data: dict) -> dict:
    result = {"status": "unknown", "rating": None, "fallback": False, "alerts": []}
    
    # G1 — Sensor availability
    if not self._gate_sensor(raw_data):
        return self._fallback(result, "G1", "sensor timeout", self.last_good_rating)
    
    # G2 — Communication link
    if not self._gate_link(raw_data):
        return self._fallback(result, "G2", "link lost", self.last_good_rating)
```

**Error Messages:**
- Clear, actionable error messages with context
- Example: `"Set SYNOPTIC_TOKEN env var. Free research tokens: https://synopticdata.com/"`

## Logging

**Framework:** Python's built-in `logging` module

**Setup Pattern:**
```python
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger(__name__)
```

**Usage:**
- `log.info()` for informational messages: `log.info("Fetching WTM station metadata …")`
- Consistent logging points at entry and completion of major operations

**Custom Logging:**
- Some classes accept logger parameter: `DLRSafetyMonitor` constructor takes optional `logger` parameter, defaulting to `print`
- This allows injection of custom logging functions for testing

## Comments

**When to Comment:**
- Explain WHY the code does something, not WHAT it does
- Document non-obvious assumptions, especially for physics/mathematical code
- Explain workarounds and known limitations

**Example from `backend/config.py` (lines 28–41):**
```python
# Note on Dallas/Fort Worth specifically: a real sourced number DOES exist
# (the Oncor Wilmer 345/138kV project, per an ERCOT filing), but it describes
# a modern-rebuild TARGET spec using 3200A/5000A-class HTLS conductor — not
# representative of this project's typical-existing-conductor assumption — so
# it was deliberately excluded here rather than used.
```

**JSDoc/TSDoc:**
- Not applicable (Python codebase with no TypeScript)
- Python docstrings follow Google style

## Function Design

**Size:** Functions are typically 10–50 lines, with clear single responsibilities

**Parameters:**
- Use type hints for all parameters
- Use named parameters with defaults where appropriate
- Example: `def get_wtm_stations(bbox: Optional[tuple] = None) -> pd.DataFrame:`

**Return Values:**
- Always include type hints for return values
- Functions that fail return early with error result or raise exception
- DataFrame operations return shaped data consistently

## Class Design

**Exports:**
- Public methods/attributes: no leading underscore
- Private/internal methods: prefixed with single underscore `_method_name()`
- Class constants in UPPERCASE

**Class Structure Pattern:**
```python
class ConductorConfig:
    """Docstring explaining purpose."""
    
    def __init__(self, param1: float = default1, param2: float = default2):
        # Store parameters as instance attributes
        self.attr1 = param1
        self.attr2 = param2
```

**Pattern Usage:**
- Classes used for configuration/data holders: `ConductorConfig`, `Q` (Quantity)
- Classes used for stateful validators: `DLRSafetyMonitor` (tracks `last_good_rating`)

---

*Convention analysis: 2026-09-02*
