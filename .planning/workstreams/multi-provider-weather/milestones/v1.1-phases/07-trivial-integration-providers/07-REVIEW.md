---
phase: 07-trivial-integration-providers
reviewed: 2026-09-12T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - ACKNOWLEDGEMENTS.md
  - backend/asos_provider.py
  - backend/config.py
  - backend/open_meteo_provider.py
  - backend/tests/asos_provider_test.py
  - backend/tests/open_meteo_provider_test.py
  - backend/tests/weather_provider_test.py
  - backend/units_def.py
  - backend/weather_provider.py
  - docs/data-science/specs/C4-weather-ingestion.md
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-09-12T00:00:00Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

This phase adds two new unauthenticated weather-provider adapters (`asos_provider.py`, `open_meteo_provider.py`), wires them into `weather_provider.py`'s station-supplement and grid paths, adds `config.ASOS_STATIONS`, and fixes a genuine pre-existing NaN-handling bug in `units_def.validate_pipeline_row`. The diff scope was confirmed against `git diff 37a695d..HEAD` rather than assumed from the full file contents, so findings below are scoped to what this phase actually touched (both provider modules are 100% new; `weather_provider.py`, `units_def.py`, and `config.py` received targeted additions).

The implementation is generally careful — explicit fail-loud behavior on malformed provider responses, a dedicated range-check gate reusing `PIPELINE_SCHEMA`, a source-level "no secrets" test, and consistent provenance bookkeeping. However, two of the three date/timestamp-parsing helpers this phase introduces (and reuses the same pattern for) do not actually honor their own documented error contract for a class of inputs (`None`/empty string), and the phase's new ASOS-supplement feature leans on a pre-existing city-resolution helper that has no distance bound — a latent robustness gap now exercised with materially higher consequence (blending in a real station's observations, not just a label) than when it was used only for merge-keying.

No hardcoded secrets, dangerous functions (`eval`/`exec`/`os.system`), or bare `except:` blocks were found in the new/changed source files (verified via `test_new_providers_read_no_secret` and independent grep).

## Warnings

### WR-01: `_to_asos_timestamp` / `_to_archive_date` violate their own documented error contract for `None`/empty-string input

**File:** `backend/asos_provider.py:34-54`, `backend/open_meteo_provider.py:74-95`

**Issue:** Both helpers wrap only the `pd.Timestamp(value)` constructor call in `try/except (ValueError, TypeError)`, then unconditionally call `.tz_localize()`/`.tz_convert()`/`.strftime()` on the result outside that guard. For `value in (None, "", "NaT")` (or any other pandas-recognized "no timestamp" spelling), `pd.Timestamp(value)` does **not** raise — it silently returns `pd.NaT`. Execution then falls through the `try/except`, and the later `.strftime(...)` call raises an *unrelated*, unhandled `ValueError: NaTType does not support strftime` that never mentions the offending value. This contradicts each function's own docstring: "Raises: ValueError: naming the offending value, when it cannot be parsed by `pd.Timestamp`." No existing test exercises this path (all tests pass well-formed date strings), so this is currently undetected. Reproduced directly:
```
>>> asos_provider._to_asos_timestamp(None)
ValueError: NaTType does not support strftime
>>> open_meteo_provider._to_archive_date(None)
ValueError: NaTType does not support strftime
```
Both `fetch_asos_1min(station, start, end)` and `fetch_open_meteo(lat, lon, start, end)` are public entry points whose docstrings make the same "raises ValueError naming the offending value" promise, so this is a real, if narrow, contract violation reachable from outside these modules.

**Fix:**
```python
try:
    ts = pd.Timestamp(value)
except (ValueError, TypeError) as exc:
    raise ValueError(f"...cannot parse timestamp {value!r}: {exc}") from exc

if pd.isna(ts):
    raise ValueError(f"...cannot parse timestamp {value!r}: got NaT")

if ts.tzinfo is None:
    ...
```
Apply the same `pd.isna(ts)` guard in both `_to_asos_timestamp` and `_to_archive_date`.

### WR-02: `resolve_station_city` has no maximum-distance guard, and Phase 7 now uses it to decide which real station's data gets blended in

**File:** `backend/weather_provider.py:110-138`

**Issue:** `resolve_station_city` always returns the *nearest* of the four hardcoded `config.CITY_COORDINATES` entries, with no upper bound on distance — a station 300 km from any of the four documented corridors still resolves to "the nearest one." This function's own docstring claims the opposite intent ("Never falls back to a default or nearest-guess-regardless-of-validity city — an unresolved coordinate must not be silently attributed to the wrong corridor's static rating"), but the implementation *is* exactly a nearest-guess-regardless-of-validity fallback for any station outside the four corridors.

In Phase 6 this function only affected a `city` label used for merge-keying grid data. Phase 7's new `_supplement_with_asos` (`weather_provider.py:344-432`) raises the stakes: it now uses this same resolution to pick which IEM ASOS station (`config.ASOS_STATIONS[city]`) to fetch *real 1-minute observations* from and merge into the result as if it were local weather for that Synoptic station. If a caller ever passes a Synoptic station ID that isn't actually near one of the four cities (e.g. a station added later, or a bug elsewhere in the pipeline that selects a station outside the two documented corridors), this code will silently attribute a distant airport's live temperature/wind readings to it with no warning — a safety-relevant data-provenance risk given this pipeline's output feeds ampacity gating.

**Fix:** Add a distance threshold (e.g. a new `config.MAX_CITY_RESOLUTION_KM` constant) and return `None` when the nearest city exceeds it:
```python
def resolve_station_city(lat, lon) -> str | None:
    ...
    nearest = min(config.CITY_COORDINATES, key=lambda city: station_explorer.haversine_km(lat, lon, *config.CITY_COORDINATES[city]))
    if station_explorer.haversine_km(lat, lon, *config.CITY_COORDINATES[nearest]) > config.MAX_CITY_RESOLUTION_KM:
        return None
    return nearest
```

### WR-03: Open-Meteo unit cross-check is silently skipped when `hourly_units` is missing or incomplete

**File:** `backend/open_meteo_provider.py:182-194`

**Issue:** The docstring frames `EXPECTED_HOURLY_UNITS` as "the cheapest possible detector for a request parameter that was dropped, renamed, or ignored upstream (RESEARCH.md Pitfall 4)." But the check is entirely skipped when `hourly_units` is absent (`isinstance(hourly_units, dict)` is `False`), and per-key, skipped when a specific mapped key is absent from that dict (`if echoed_unit is None: continue`). A response that dropped the whole `hourly_units` block, or omitted the echo for one variable (e.g. `wind_speed_10m`, the one the docstring specifically calls out — a dropped `wind_speed_unit=ms` override), would pass through this gate undetected, with the unit-mismatch only caught later (if at all) by the coarser numeric range check in `_range_check`, which cannot distinguish "value in wrong units but still in-range" from "genuinely correct." No test exercises the "hourly_units entirely absent" case.

**Fix:** Treat an entirely-missing `hourly_units` block, or a missing echo for a variable this code explicitly requested a unit override for (`wind_speed_10m`), as a hard failure rather than a silent skip:
```python
if not isinstance(hourly_units, dict):
    raise ValueError("open_meteo_provider: response is missing 'hourly_units' -- cannot verify the requested unit overrides were honored.")
for provider_key, expected_unit in EXPECTED_HOURLY_UNITS.items():
    echoed_unit = hourly_units.get(provider_key)
    if echoed_unit is None:
        raise ValueError(f"open_meteo_provider: response's 'hourly_units' did not echo a unit for {provider_key!r}.")
    ...
```

## Info

### IN-01: Redundant import of the same name in `asos_provider.py`

**File:** `backend/asos_provider.py:22-24`
**Issue:** `import units_def` and `from units_def import Q` both import from the same module; `Q` is also reachable as `units_def.Q`. Minor inconsistency versus `open_meteo_provider.py`, which imports only the module and uses `units_def.PIPELINE_SCHEMA` throughout.
**Fix:** Drop `from units_def import Q` and reference `units_def.Q(...)` for consistency with the sibling module, or keep both imports but note the duplication is intentional for readability — either is fine, just pick one convention.

### IN-02: No runtime type validation on `start`/`end` — a non-string silently produces a nonsensical date rather than an error

**File:** `backend/asos_provider.py:34-54`, `backend/open_meteo_provider.py:74-95`
**Issue:** Both helpers are type-hinted to take `str`, but `pd.Timestamp` also accepts an `int`/`float` and interprets it as nanoseconds since the Unix epoch rather than raising. `pd.Timestamp(123)` silently produces `1970-01-01 00:00:00.000000123` instead of an error. If a caller ever passes a non-string (e.g. a Unix-epoch integer by mistake), the request window would silently become "the beginning of 1970" instead of failing loudly — the opposite of this phase's stated fail-loud design philosophy for malformed input.
**Fix:** Add an explicit `isinstance(value, str)` check at the top of `_to_asos_timestamp`/`_to_archive_date` and raise `ValueError` naming the received type, before handing the value to `pd.Timestamp`.

---

_Reviewed: 2026-09-12T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
