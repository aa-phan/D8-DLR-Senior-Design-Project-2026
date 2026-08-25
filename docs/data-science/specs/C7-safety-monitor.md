# C7 — Safety Monitor & Fallback

**Phase:** 3 (Safety & Spatial) · **Effort:** M · **Status:** Partial — the gating logic is complete and tested, but the ampacity it gates is a placeholder, not the real thermal model.

**Responsibility:** Gate each measurement cycle through a sequence of checks and decide whether to trust a computed rating or fall back to the static rating — the concrete implementation of the project's core ethical commitment (fail-safe by default, per `Project Definition.md`'s ethical considerations and `PRD.md` §6 non-functional requirements).

## Current Implementation

`backend/DLRSafetyMonitor.py`, single class:

- `DLRSafetyMonitor(static_rating, logger=None)` — `logger` defaults to `print`; `last_good_rating` initializes to `static_rating`.
- `run_check(raw_data: dict) -> dict` — returns `{"status", "rating", "fallback", "alerts"}`. Expects keys: `sensor_status`, `link_status`, `wind`, `temp`, `solar`.

**Gates, in order:**

| Gate | Check | Bounds | On failure |
|---|---|---|---|
| G1 | Sensor availability | `sensor_status == "ok"` and wind/temp/solar all non-null | fallback, `rating = last_good_rating` |
| G2 | Communication link | `link_status == "ok"` | fallback, `rating = last_good_rating` |
| G3 | Range validation | wind ∈ [0, 50] m/s, temp ∈ [-20, 60] °C, solar ∈ [0, 1400] W/m² | fallback, `rating = static_rating` |
| G4 | Ampacity plausibility | computed rating ∈ [400, 1800] A | fallback, `rating = static_rating` |
| G5 | Delta check | \|rating − last_good_rating\| ≤ 150 A | not a fallback — appends an alert, rating still accepted |

On success, `last_good_rating` updates to the newly computed rating.

`_compute_ampacity(self, d)` (line 62): `900 + wind*30 - (temp-20)*4 - solar*0.05` — explicitly commented `# Simplified IEEE 738 — replace with your full thermal model`. **Does not call C5's `ieee738_ampacity`.**

## Interface & Data Contract

Input `raw_data` dict keys map loosely to `PIPELINE_SCHEMA` fields (`wind` ≈ `wind_perp_ms`, `temp` ≈ `air_temp`, `solar` ≈ `solar_radiation`) but aren't currently validated against it — see Known Issues.

## Blocked by

**C5** — this is the component's core dependency. The whole point of G4/G5 plausibility gating is comparing a computed rating against expectations, and that only means something if the computed rating comes from the actual physical model.

## Blocks

- **C10** — learned anomaly detection is built as a replacement/augmentation of this component's deterministic gates; it needs the gating framework (and, ideally, a correct ampacity function) to exist first.

## Parallel-safe with

**C8** — independent dependency chains (C7 ← C5; C8 ← C4 + C5), no shared files. Per `ROADMAP.md` Finding 4, whoever's assigned C7 shouldn't sit idle waiting on C5 — C6 or early C8 scaffolding is available in the meantime, since C7's actual code change (once C5 lands) is small.

## Known Issues

- **`_compute_ampacity` doesn't call the real thermal model.** Until unified with C5's `ieee738_ampacity`, the safety monitor and the pipeline can disagree on what rating a given weather observation implies — undermining the point of G4/G5.
- **G1/G2 vs. G3/G4 fall back to different values.** G1 and G2 fall back to `last_good_rating` (the last trusted *dynamic* value); G3 and G4 fall back all the way to `static_rating`. This is a real, possibly-intentional design distinction (sensor/link loss ≠ implausible reading), but it's undocumented anywhere and should be explicitly confirmed as intended, not assumed.
- **Range gates duplicate `PIPELINE_SCHEMA`.** `WIND_BOUNDS`, `TEMP_BOUNDS`, `SOLAR_BOUNDS` are a second, independently-maintained copy of ranges C2 already owns — see C2's Known Issues for the same finding from the other side.
- **`backend/tests/SafetyMonitor_TestSuite.py::test_gate_2_fails_when_link_status_not_ok` (line 62) contradicts itself.** It asserts `result["status"] == "ok"` while also asserting `result["fallback"] is True`. `_fallback()` unconditionally sets `status` to `"fallback"`, so `status` can never be `"ok"` when `fallback` is `True`. **Verified failing** via `pytest backend/tests/SafetyMonitor_TestSuite.py backend/tests/units_def_test.py` on 2026-08-24: `1 failed, 17 passed`. Not fixed per team decision to document rather than fix in this pass — needs a decision on intended semantics (is `status` supposed to reflect gate-2-specifically, requiring a richer result shape? or is the test simply a copy-paste error from a passing-case test?) before it's touched.

## Acceptance Criteria

- All injected anomalies (out-of-range, implausible rating, large delta) correctly flagged; zero false positives on clean data; fallback to static rating confirmed on every anomaly case. Per System Design Report §3.3. `backend/tests/SafetyMonitor_TestSuite.py` covers this except for the gate-2 contradiction above.
- Once wired to C5: for identical weather inputs, `DLRSafetyMonitor`'s computed rating matches `dlr_pipeline`'s `ieee738_ampacity` output exactly (or within floating-point tolerance).
- The gate-2 test contradiction is resolved (fixed or the semantics it was probing are formally redefined) before this component is considered done.

## Open Questions

- Confirm G1/G2 vs. G3/G4 fallback-target distinction is intentional (see Known Issues).
- Where does the monitor get a `ConductorConfig` for each check cycle — one global default, or per-location like C1's open question on conductor properties?
- Resolve the gate-2 test contradiction's intended semantics.
