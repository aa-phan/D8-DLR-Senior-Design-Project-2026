# C7 — Safety Monitor & Fallback

**Phase:** 3 (Safety & Spatial) · **Effort:** M · **Status:** Implemented — gates G1–G6 are complete and tested (24 tests passing in `backend/tests/SafetyMonitor_TestSuite.py`), and ampacity is computed by C5's `thermal_model.ieee738_ampacity`.

**Responsibility:** Gate each measurement cycle through a sequence of checks and decide whether to trust a computed rating or fall back to the static rating — the concrete implementation of the project's core ethical commitment (fail-safe by default, per `Project Definition.md`'s ethical considerations and `PRD.md` §6 non-functional requirements).

## Current Implementation

`backend/DLRSafetyMonitor.py`, single class:

- `DLRSafetyMonitor(static_rating, conductor=None, solar_altitude_deg=45.0, rating_bounds=None, delta_fraction=None, anomaly_detector=None, logger=None)` — `logger` defaults to `print`; `last_good_rating` initializes to `static_rating`; `rating_bounds` and `delta_fraction` default to `config.DEFAULT_RATING_BOUNDS` (400–1800 A) and `config.DELTA_FRACTION` (0.15); `anomaly_detector=None` leaves G6 disabled.
- `run_check(raw_data: dict) -> dict` — returns `{"status", "rating", "fallback", "alerts"}`. Expects keys: `sensor_status`, `link_status`, `wind`, `temp`, `solar`.

**Gates, in order:**

| Gate | Check | Bounds | On failure |
|---|---|---|---|
| G1 | Sensor availability | `sensor_status == "ok"` and wind/temp/solar all non-null | fallback, `rating = static_rating` |
| G2 | Communication link | `link_status == "ok"` | fallback, `rating = static_rating` |
| G3 | Range validation | wind ∈ [0, 50] m/s, temp ∈ [-20, 60] °C, solar ∈ [0, 1400] W/m² | fallback, `rating = static_rating` |
| G4 | Ampacity plausibility | computed rating within `rating_bounds` (default [400, 1800] A) | fallback, `rating = static_rating` |
| G5 | Delta check | \|rating − last_good_rating\| ≤ `delta_fraction × static_rating` (default 0.15 × static) | fallback, `rating = min(computed, static_rating)`; `last_good_rating` is first updated to the computed value so a genuine sustained change resolves in one cycle instead of latching |
| G6 | Learned anomaly (C10), only if a detector is injected | `anomaly_detector.check(raw_data, rating)` returns not anomalous; a detector exception also fails safe | fallback, `rating = static_rating` |

Every failure goes through `_fallback()`, which sets `status = "fallback"`, `fallback = True`, and a single alert string. No gate falls back to `last_good_rating`. On success, `last_good_rating` updates to the newly computed rating and `status = "ok"`.

`_compute_ampacity(self, d)` calls `thermal_model.ieee738_ampacity(T_amb_c, wind_perp_ms, ghi_wm2, conductor, solar_altitude_deg)` — the same function the pipeline uses (C5).

## Interface & Data Contract

Input `raw_data` dict keys map loosely to `PIPELINE_SCHEMA` fields (`wind` ≈ `wind_perp_ms`, `temp` ≈ `air_temp`, `solar` ≈ `solar_radiation`) but aren't currently validated against it — see Known Issues.

## Blocked by

**C5** — satisfied: the monitor now computes ampacity with C5's `ieee738_ampacity`, which is what makes G4/G5 plausibility gating meaningful.

## Blocks

- **C10** — learned anomaly detection is built as a replacement/augmentation of this component's deterministic gates; it needs the gating framework (and, ideally, a correct ampacity function) to exist first.

## Parallel-safe with

**C8** — independent dependency chains (C7 ← C5; C8 ← C4 + C5), no shared files. (C8's per-city rating constructs one `DLRSafetyMonitor` per city and calls `run_check` on it; it does not modify this module.)

## Known Issues

- **Range gates duplicate `PIPELINE_SCHEMA`.** `WIND_BOUNDS`, `TEMP_BOUNDS`, `SOLAR_BOUNDS` are a second, independently-maintained copy of ranges C2 already owns — see C2's Known Issues for the same finding from the other side.
- **Resolved (2026-10-08):** earlier versions of this spec recorded (a) a placeholder linear `_compute_ampacity`, (b) G1/G2 falling back to `last_good_rating` while G3/G4 used `static_rating`, (c) G5 as alert-only, and (d) `test_gate_2_fails_when_link_status_not_ok` asserting `status == "ok"` alongside `fallback is True`. None hold in the current code: ampacity uses C5, every gate falls back to `static_rating` (G5 to `min(computed, static_rating)`), G5 is a fallback, and the gate-2 test asserts `status == "fallback"` (`test_gate_2_fallback_uses_static_rating_not_last_good` also pins the static-rating target).

## Acceptance Criteria

- All injected anomalies (out-of-range, implausible rating, large delta) correctly flagged; zero false positives on clean data; fallback to static rating confirmed on every anomaly case. Per System Design Report §3.3. `backend/tests/SafetyMonitor_TestSuite.py` covers this.
- ✅ `DLRSafetyMonitor`'s computed rating comes from `thermal_model.ieee738_ampacity`, the same function `dlr_pipeline` uses.

## Open Questions

- Where does the monitor get a `ConductorConfig` for each check cycle — one global default, or per-location like C1's open question on conductor properties? **Partly answered**: for per-city ratings, C8's `city_point.city_point(city)` supplies a `ConductorConfig` carrying that city's line bearing (`config.CITY_LINE_BEARING_DEG`, an assumed value carried over from the retired corridor bearings), along with the city's own `static_rating` and `rating_bounds`. Other conductor properties remain a single global default.
