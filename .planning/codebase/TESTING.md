# Testing Patterns

**Analysis Date:** 2026-09-02

## Test Framework

**Runner:**
- `pytest` (no version pinned; assumed latest compatible)
- Config: `pytest.ini` at project root

**Assertion Library:**
- Built-in `assert` statements
- `pytest.approx()` for floating-point comparisons
- `pytest.mark.parametrize` for parameterized testing

**Run Commands:**
```bash
pytest                              # Run all tests (pythonpath: backend, testpaths: backend/tests)
pytest -v                           # Verbose output
pytest backend/tests/test_file.py   # Run specific test file
pytest -k test_name                 # Run tests matching pattern
```

**pytest Configuration** (`backend/pytest.ini`):
```ini
[pytest]
pythonpath = backend               # Backend root is added to sys.path
testpaths = backend/tests          # Only scan tests/ directory
python_files = test_*.py *_test.py *_TestSuite.py  # Multiple naming patterns supported
```

## Test File Organization

**Location:**
- Tests co-located in `backend/tests/` directory (parallel to source in `backend/`)
- Not inline with source files; separate dedicated directory

**Naming Conventions:**
- Primary pattern: `test_<module>.py` (e.g., `thermal_model_test.py`, `ercot_dlr_merger_test.py`, `units_def_test.py`)
- Alternative pattern: `<module>_test.py` (supported by pytest.ini)
- Suite pattern: `<module>_TestSuite.py` (e.g., `SafetyMonitor_TestSuite.py`)

**Directory Structure:**
```
backend/
├── config.py
├── thermal_model.py
├── DLRSafetyMonitor.py
├── tests/
│   ├── __pycache__/
│   ├── thermal_model_test.py
│   ├── ercot_dlr_merger_test.py
│   ├── units_def_test.py
│   └── SafetyMonitor_TestSuite.py
```

## Test Structure

**Suite Organization Pattern (using pytest):**
```python
"""
Module docstring explaining what is being tested.

Covers specific acceptance criteria or requirements.
"""

import pytest
[other imports]

# Optional: pytest fixtures for setup
@pytest.fixture
def monitor():
    return DLRSafetyMonitor(static_rating=1000, logger=lambda msg: None)

@pytest.fixture
def valid_data():
    return {
        "sensor_status": "ok",
        "link_status": "ok",
        "wind": 5.0,
        "temp": 25.0,
        "solar": 500.0,
    }

# Test functions
def test_run_check_success_returns_ok(monitor, valid_data):
    # Arrange
    result = monitor.run_check(valid_data)
    expected_rating = 900 + 5.0 * 30 - (25.0 - 20) * 4 - 500.0 * 0.05
    
    # Act & Assert
    assert result["status"] == "ok"
    assert result["rating"] == expected_rating
```

**Patterns Observed:**

1. **Comprehensive module docstrings:**
   - Explain what is being tested
   - List acceptance criteria being verified
   - Document any known issues or complexities

2. **Descriptive test names:**
   - `test_ieee738_worked_example_795kcmil_drake_acsr()` — very descriptive
   - `test_gate_1_fails_when_sensor_status_not_ok()` — describes condition and expected behavior
   - `test_hourly_resample_uses_min_not_mean()` — documents the specific implementation detail

3. **Fixtures for common setup:**
   - `monitor` fixture: Creates a DLRSafetyMonitor instance with known static_rating
   - `valid_data` fixture: Provides baseline valid test data
   - Fixtures reused across multiple tests

4. **Arrange-Act-Assert implicit pattern:**
   - Comment-driven sections sometimes present (e.g., `# Conductor, matching the STANDARD's worked example`)
   - Most tests follow: setup, execute, assert inline

## Mocking

**Framework:**
- No explicit mocking framework detected (no `unittest.mock` or `pytest-mock` seen in tests)
- Mocking done manually through fixtures and lambda functions when needed

**Patterns:**

1. **Fixture-based dependency injection:**
   ```python
   @pytest.fixture
   def monitor():
       # Pass a no-op logger function instead of real logger
       return DLRSafetyMonitor(static_rating=1000, logger=lambda msg: None)
   ```

2. **Lambda for simple mocks:**
   ```python
   # From SafetyMonitor_TestSuite.py
   monitor._compute_ampacity = lambda d: 300  # Mock method for testing gate
   ```

3. **Direct data substitution:**
   ```python
   valid_data["sensor_status"] = "fail"  # Modify fixture to test failure case
   ```

**What to Mock:**
- External API calls (fetch functions) — typically tested via fixtures or temporary files
- Logger/output functions — use lambda or no-op functions
- Internal methods that are hard to set up (e.g., `_compute_ampacity`)

**What NOT to Mock:**
- Core physics calculations — test with real thermal model
- Data validation functions — test actual behavior
- DataFrame operations — test actual pandas behavior

## Fixtures and Factories

**Test Data Patterns:**

1. **Fixture-based setup** (pytest fixtures):
   ```python
   @pytest.fixture
   def valid_data():
       return {
           "sensor_status": "ok",
           "link_status": "ok",
           "wind": 5.0,
           "temp": 25.0,
           "solar": 500.0,
       }
   ```

2. **Inline data construction** (especially for DataFrames):
   ```python
   timestamps = pd.date_range("2025-07-01T00:00:00Z", periods=12, freq="5min")
   amps = [800.0] * 12
   dip_idxs = [4, 5, 6]
   for i in dip_idxs:
       amps[i] = 250.0
   df = pd.DataFrame({"datetime_utc": timestamps, "dlr_amps": amps, ...})
   ```

3. **Temporary file fixture** (pytest built-in `tmp_path`):
   ```python
   def test_hourly_resample_uses_min_not_mean(tmp_path):
       df = pd.DataFrame({...})
       csv_path = tmp_path / "dlr_synthetic.csv"
       df.to_csv(csv_path, index=False)
       hourly = process_dlr_to_hourly(str(csv_path))
   ```

**Location:**
- Fixtures defined in test files themselves (no `conftest.py` detected)
- Each test file imports from its corresponding module and sets up fixtures as needed

## Coverage

**Requirements:**
- No coverage enforcement detected (no pytest-cov config)
- No minimum coverage percentage enforced

**View Coverage:**
```bash
pytest --cov=backend --cov-report=html  # If pytest-cov installed
pytest --cov=backend --cov-report=term
```

## Test Types

**Unit Tests:**
- **Scope:** Individual functions and classes in isolation
- **Approach:** Test single function/method at a time with controlled inputs
- **Examples:**
  - `test_perpendicular_wind()` — tests wind calculation function
  - `test_valid_units()` — tests Quantity construction
  - `test_gate_1_fails_when_sensor_status_not_ok()` — tests single gate method
- **Location:** `backend/tests/thermal_model_test.py`, `backend/tests/SafetyMonitor_TestSuite.py`, `backend/tests/units_def_test.py`

**Integration Tests:**
- **Scope:** Multiple components working together
- **Approach:** Test full pipeline or significant subsystems
- **Examples:**
  - `test_inner_join_keeps_only_overlap_no_duplicates()` — tests merging of two data sources
  - `test_ieee738_worked_example_795kcmil_drake_acsr()` — tests full thermal model against published standard
- **Location:** `backend/tests/ercot_dlr_merger_test.py` (tests data integration), `backend/tests/thermal_model_test.py` (tests complete formula)

**E2E Tests:**
- **Framework:** Not detected/Not implemented
- **Note:** Current tests are focused on unit and integration; no full end-to-end pipeline test observed

## Common Patterns

**Floating-Point Comparisons:**
```python
# Using pytest.approx
result = amps_to_mw(1000.0, 100.0, 1.0)
assert result == pytest.approx(173.20508075688772, rel=1e-9)

# Or manual tolerance check
assert abs(q.value - 10.0) < 1e-6, f"Expected 10.0 m/s, got {q.value}"

# Or approximate absolute tolerance
assert hourly.loc[0, "dlr_amps"] == pytest.approx(expected_min)
```

**Parametrized Testing:**
```python
@pytest.mark.parametrize(
    "amps,voltage_kv,pf,expected_mw",
    [
        (1000.0, 100.0, 1.0, 173.20508075688772),
        (900.0, 345.0, 0.95, 510.91168696262963),
        (500.0, 138.0, 0.9, 107.56035515002728),
    ],
)
def test_amps_to_mw_matches_hand_calculation(amps, voltage_kv, pf, expected_mw):
    result = amps_to_mw(amps, voltage_kv, pf)
    assert result == pytest.approx(expected_mw, rel=1e-9)
```

**Testing Both Success and Failure Cases:**
```python
def test_run_check_success_returns_ok(monitor, valid_data):
    result = monitor.run_check(valid_data)
    assert result["status"] == "ok"

def test_gate_1_fails_when_sensor_status_not_ok(monitor, valid_data):
    valid_data["sensor_status"] = "fail"
    result = monitor.run_check(valid_data)
    assert result["status"] == "fallback"
    assert "G1 FAIL" in result["alerts"][0]
```

**Custom Error Expectations:**
```python
def _expect_unit_error(fn: Callable, hint: str = "") -> None:
    """Assert that fn() raises UnitError (otherwise the test itself fails)."""
    try:
        fn()
        raise AssertionError(f"Expected UnitError but none was raised. {hint}")
    except UnitError:
        pass   # correct — the module caught it

# Usage in test
def test_unknown_unit():
    _expect_unit_error(lambda: Q(5.2, "furlongs/fortnight"), "Unknown unit should raise.")
```

**Detailed Test Docstrings:**
```python
def test_ieee738_worked_example_795kcmil_drake_acsr():
    """
    Reproduces the IEEE Std 738-2023 published worked example for a 795 kcmil
    "Drake" ACSR conductor and checks `ieee738_ampacity` against its
    published answer of 1025 A (steady-state rating, §4.6.1).
    
    Every input below is chosen to map this project's `ieee738_ampacity`
    parameters onto the standard's worked-example inputs as closely as this
    function's actual formula allows — see inline comments for each one.
    """
    # Extensive inline comments explaining test setup
    # ... test implementation
```

**Assertion Messages:**
```python
assert rel_error <= rel_tol, (
    f"ieee738_ampacity({ampacity:.2f} A) deviates from the IEEE Std "
    f"738-2023 worked-example answer ({expected} A) by "
    f"{rel_error * 100:.3f}%, exceeding the {rel_tol * 100:.1f}% "
    f"tolerance justified above."
)
```

## Test Data & Constants

**Test constants** are defined inline or in fixtures:
```python
# From SafetyMonitor_TestSuite.py — bounds match class constants
valid_data = {
    "sensor_status": "ok",
    "link_status": "ok",
    "wind": 5.0,        # Within WIND_BOUNDS (0, 50)
    "temp": 25.0,       # Within TEMP_BOUNDS (-20, 60)
    "solar": 500.0,     # Within SOLAR_BOUNDS (0, 1400)
}
```

**Synthetic data construction:**
```python
# From ercot_dlr_merger_test.py — create DataFrame for testing
timestamps = pd.date_range("2025-07-01T00:00:00Z", periods=12, freq="5min")
amps = [800.0] * 12
dip_idxs = [4, 5, 6]
for i in dip_idxs:
    amps[i] = 250.0
df = pd.DataFrame({
    "datetime_utc": timestamps,
    "dlr_amps": amps,
    "wind_speed": [5.0] * 12,
    "air_temp": [30.0] * 12,
})
```

## Import Pattern in Tests

**Standard pattern:**
```python
import pytest
import math
import numpy as np
import pandas as pd
from pathlib import Path

# Local module under test
import thermal_model as tm
# or
from units_def import Q, UnitError
# or with sys.path manipulation for parent directory
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ercot_dlr_merger import amps_to_mw, process_dlr_to_hourly
```

---

*Testing analysis: 2026-09-02*
