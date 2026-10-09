# C2 — Pipeline Data Contract

**Phase:** 1 (Foundation) · **Effort:** S · **Status:** Implemented and integrated.

**Responsibility:** Be the single authoritative definition of every column that flows through the DS pipeline — its name, unit, and valid range — and provide the validation functions other components should call at their boundaries. This is what turns the pipeline's current implicit CSV-column coupling (see `ROADMAP.md` §1) into an explicit, enforced contract.

## Current Implementation

`backend/units_def.py` — fully implemented, unit-tested (`backend/tests/units_def_test.py`), and **now integrated** at the pipeline's real output boundary:

- `backend/dlr_pipeline.py::validate_pipeline_output(df, max_examples=10) -> int` — new helper, called automatically as the last step of `run_pipeline` before it returns. Validates every row via `validate_pipeline_row(row, strict=False)`, never mutates or filters `df`, and logs a summary (`INFO` if clean, `WARNING` with a deduped top-N violation breakdown otherwise). Returns the count of rows with at least one violation.

- `PIPELINE_SCHEMA: Dict[str, Dict]` (`backend/units_def.py:347`) — the canonical schema. Per column: `unit`, `range` (lo, hi), `required`. Currently defines: `air_temp` (degC), `wind_speed` (m/s), `wind_direction` (deg), `wind_perp_ms` (m/s), `solar_radiation` (W/m²), `relative_humidity` (%), `dlr_amps` (A), `dlr_capacity_mw` (MW), `static_capacity_mw` (MW), `ercot_west_load_mw` (MW), plus the forecast and provenance columns added later: `forecast_horizon_min`, `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, `anomaly_score`, `wind_source`, `temp_source`, `humidity_source`, `solar_source`.
- `Q(value, unit, label="")` — dataclass wrapping a value with a unit; validates against `UNIT_DIMENSIONS` at construction.
- `Q.to(target_unit, **kwargs) -> Q` — same-dimension conversion via a canonical base unit; current↔power cross-dimension conversion requires `voltage_kv` kwarg (`P = sqrt(3) * V * I * pf`).
- `Q.assert_unit`, `Q.assert_dimension`, `Q.assert_range` — chainable assertions, raise `UnitError`.
- `validate_pipeline_row(row: dict, strict: bool = True) -> list[str]` (`backend/units_def.py:454`) — validates a plain dict against `PIPELINE_SCHEMA`. Strict mode raises on first failure; non-strict collects and returns all violations.
- `@check_units(**expected_units)` — decorator enforcing `Q`-typed, specific-unit function arguments.

`backend/dlr_pipeline.py` imports and calls `validate_pipeline_row` (via `validate_pipeline_output`). Outside that one output boundary, inter-module data (e.g. `DLRSafetyMonitor.py`, `ercot_dlr_merger.py`) still moves as plain floats/DataFrame columns with no enforcement.

## Interface & Data Contract

`PIPELINE_SCHEMA` (`backend/units_def.py:347`) **is** the data contract. Do not restate it in any other spec or doc — reference this file. Any new column added by any component (e.g. C8's per-point ampacity, C9's forecast columns) must be added here first.

## Blocked by

**C1** — needs to know config-derived value shapes (e.g. is `static_capacity_mw` fixed or per-location?) before finalizing ranges for those columns, though the core weather-observation columns have no such dependency and can be locked immediately.

## Blocks

- **C3** — export/plot code should validate rows against this schema before writing output. (C6 and the Software sub-team's dashboard are transitively blocked via C3, not directly by C2 — see C3's spec.)
- Software sub-team's dashboard (external) — needs the schema this component defines, delivered via C3, to know what to expect from the DS output feed. This is the fastest path to unblocking a different sub-team; see `ROADMAP.md` Finding 2.

**Related, not blocking:** C7's range gates (G3, hand-coded bounds in `backend/DLRSafetyMonitor.py`) duplicate ranges already defined here and should eventually read from `PIPELINE_SCHEMA` instead of maintaining a second copy — a cleanup opportunity, not a hard dependency, since C7 is gated on C5, not C2.

## Parallel-safe with

C1, C3 (all Phase 1). C2 and C3 will move fastest if done together by the same person/pair, since C3's export format should be validated against C2's schema directly.

## Known Issues

- ~~Fully unused...~~ **Fixed** — `run_pipeline` now validates every output row automatically.
- `backend/DLRSafetyMonitor.py`'s own range bounds (`WIND_BOUNDS`, `TEMP_BOUNDS`, `SOLAR_BOUNDS`) are still a second, independently-maintained copy of ranges that mostly overlap `PIPELINE_SCHEMA`'s (e.g. wind 0–50 m/s in both) — this pass did not touch `DLRSafetyMonitor.py` (that's C7, Phase 3, gated on C5 not C2), so this duplication remains, per the spec's own "Related, not blocking" note above.

## Acceptance Criteria

- ✅ 100% detection rate on a suite of intentionally injected unit errors — `backend/tests/units_def_test.py` (11 tests in that file pass as of 2026-10-08).
- ✅ A real pipeline boundary (`backend/dlr_pipeline.py::run_pipeline`'s output row, before `export_results`) calls `validate_pipeline_row` (via the new `validate_pipeline_output` helper) and the pipeline visibly logs on a schema violation rather than exporting bad data silently. Verified with a synthetic out-of-range row (`air_temp = 200.0`): correctly caught and logged at `WARNING` level, zero false positives on clean data.

## Open Questions

- Should `DLRSafetyMonitor`'s range gates be replaced with calls into `PIPELINE_SCHEMA`, or kept separate because the monitor's bounds are deliberately different (operational safety margins vs. general validity)? Needs a team decision, not assumed here.
- Non-strict vs. strict validation at each boundary — where should the pipeline fail loudly (raise) vs. log and continue?
