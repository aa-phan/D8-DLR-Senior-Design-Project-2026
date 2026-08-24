# C2 — Pipeline Data Contract

**Phase:** 1 (Foundation) · **Effort:** S · **Status:** Partial — `src/units_def.py` is fully built and tested but not called anywhere in the actual pipeline.

**Responsibility:** Be the single authoritative definition of every column that flows through the DS pipeline — its name, unit, and valid range — and provide the validation functions other components should call at their boundaries. This is what turns the pipeline's current implicit CSV-column coupling (see `ROADMAP.md` §1) into an explicit, enforced contract.

## Current Implementation

`src/units_def.py` — fully implemented, unit-tested (`tests/units_def_test.py`), and **not integrated**:

- `PIPELINE_SCHEMA: Dict[str, Dict]` (`src/units_def.py:324`) — the canonical schema. Per column: `unit`, `range` (lo, hi), `required`. Currently defines: `air_temp` (degC), `wind_speed` (m/s), `wind_direction` (deg), `wind_perp_ms` (m/s), `solar_radiation` (W/m²), `relative_humidity` (%), `dlr_amps` (A), `dlr_capacity_mw` (MW), `static_capacity_mw` (MW), `ercot_west_load_mw` (MW).
- `Q(value, unit, label="")` — dataclass wrapping a value with a unit; validates against `UNIT_DIMENSIONS` at construction.
- `Q.to(target_unit, **kwargs) -> Q` — same-dimension conversion via a canonical base unit; current↔power cross-dimension conversion requires `voltage_kv` kwarg (`P = sqrt(3) * V * I * pf`).
- `Q.assert_unit`, `Q.assert_dimension`, `Q.assert_range` — chainable assertions, raise `UnitError`.
- `validate_pipeline_row(row: dict, strict: bool = True) -> list[str]` (`src/units_def.py:378`) — validates a plain dict against `PIPELINE_SCHEMA`. Strict mode raises on first failure; non-strict collects and returns all violations.
- `@check_units(**expected_units)` — decorator enforcing `Q`-typed, specific-unit function arguments.

**Nothing in `src/dlr_pipeline.py`, `src/DLRSafetyMonitor.py`, or `src/ercot_dlr_merger.py` imports or calls any of this.** All inter-module data currently moves as plain floats/DataFrame columns with no enforcement.

## Interface & Data Contract

`PIPELINE_SCHEMA` (`src/units_def.py:324`) **is** the data contract. Do not restate it in any other spec or doc — reference this file. Any new column added by any component (e.g. C8's per-point ampacity, C9's forecast columns) must be added here first.

## Blocked by

**C1** — needs to know config-derived value shapes (e.g. is `static_capacity_mw` fixed or per-location?) before finalizing ranges for those columns, though the core weather-observation columns have no such dependency and can be locked immediately.

## Blocks

- **C3** — export/plot code should validate rows against this schema before writing output. (C6 and the Software sub-team's dashboard are transitively blocked via C3, not directly by C2 — see C3's spec.)
- Software sub-team's dashboard (external) — needs the schema this component defines, delivered via C3, to know what to expect from the DS output feed. This is the fastest path to unblocking a different sub-team; see `ROADMAP.md` Finding 2.

**Related, not blocking:** C7's range gates (G3, hand-coded bounds in `src/DLRSafetyMonitor.py`) duplicate ranges already defined here and should eventually read from `PIPELINE_SCHEMA` instead of maintaining a second copy — a cleanup opportunity, not a hard dependency, since C7 is gated on C5, not C2.

## Parallel-safe with

C1, C3 (all Phase 1). C2 and C3 will move fastest if done together by the same person/pair, since C3's export format should be validated against C2's schema directly.

## Known Issues

- Fully unused. `DS-F6` is "Implemented" only in the sense that a correct, tested library exists — it enforces nothing in practice today.
- `src/DLRSafetyMonitor.py`'s own range bounds (`WIND_BOUNDS`, `TEMP_BOUNDS`, `SOLAR_BOUNDS`) are a second, independently-maintained copy of ranges that mostly overlap `PIPELINE_SCHEMA`'s (e.g. wind 0–50 m/s in both) — a second source of truth that can silently diverge from the first.

## Acceptance Criteria

- 100% detection rate on a suite of intentionally injected unit errors (e.g. a value passed in kW where MW is expected) — per System Design Report §3.3. `tests/units_def_test.py` already covers this for the standalone module.
- At least one real pipeline boundary (recommend: `src/dlr_pipeline.py::run_pipeline`'s output row, before `export_results`) calls `validate_pipeline_row` and the pipeline visibly fails/logs on a schema violation rather than exporting bad data silently.

## Open Questions

- Should `DLRSafetyMonitor`'s range gates be replaced with calls into `PIPELINE_SCHEMA`, or kept separate because the monitor's bounds are deliberately different (operational safety margins vs. general validity)? Needs a team decision, not assumed here.
- Non-strict vs. strict validation at each boundary — where should the pipeline fail loudly (raise) vs. log and continue?
