# C5 — Thermal Model (IEEE 738)

**Phase:** 2 (Core Consolidation) · **Effort:** M · **Status:** Implemented as an independently importable module (`backend/thermal_model.py`) and validated against IEEE 738's own published worked example. **A real correctness bug was found and fixed during that validation — see below.** Not merely "correct in structure" as previously believed; it was actually wrong until this pass.

**Responsibility:** Compute steady-state IEEE 738 conductor ampacity from weather inputs and conductor properties. This is the physics core every other component (C7, C8, C9) should call rather than reimplement — `backend/DLRSafetyMonitor.py` (C7) now calls `thermal_model.ieee738_ampacity` rather than reimplementing it.

## Current Implementation

All extracted into `backend/thermal_model.py` (previously entangled in `backend/dlr_pipeline.py`; `dlr_pipeline.py` now `import thermal_model` and calls `thermal_model.X` at every call site):

- `ConductorConfig` — physical conductor parameters. Defaults model 795 kcmil Drake ACSR: diameter 0.02814 m, AC resistance 0.0726 Ω/km @ 25°C, resistance temp coefficient 0.00404/°C, emissivity/absorptivity 0.8, max temp 75°C, line azimuth 90°, elevation 300 m.
- `perpendicular_wind(wind_speed_ms, wind_dir_deg, line_azimuth_deg) -> np.ndarray` — projects wind onto the line-perpendicular axis; below 20° incidence, floors at `ws * sin(20°)` to avoid instability in the natural-convection regime.
- `ieee738_ampacity(T_amb_c, wind_perp_ms, ghi_wm2, conductor, solar_altitude_deg=45.0) -> np.ndarray` — the heat balance: `I = sqrt((Q_conv + Q_rad - Q_solar) / R(T_c))`, with forced/natural convection as `max(Q_cf, Q_cn)` (Reynolds-number-dependent forced convection, natural convection floor) and radiative loss via linearized Stefan-Boltzmann. **See "Critical Bug Fixed" below — the forced-convection term was wrong until this pass.**
- Helper functions `_air_density`, `_dynamic_viscosity`, `_thermal_conductivity`.

## Interface & Data Contract

Inputs: `T_amb_c` (degC), `wind_perp_ms` (m/s), `ghi_wm2` (W/m²), a `ConductorConfig`, `solar_altitude_deg` (deg). Output: ampacity in Amperes, matching `PIPELINE_SCHEMA`'s `dlr_amps` (range 100–4000 A).

`thermal_model.py` has no ingestion dependencies and no `__main__` side effects — importable and callable without a `SYNOPTIC_TOKEN` env var or any file I/O. `backend/dlr_pipeline.py::run_pipeline` is a caller of this module, not its owner.

## Critical Bug Fixed: erroneous π factor in forced convection

While building the known-value validation below (against IEEE Std 738-2023's own published worked example), the forced-convection term was found to have an extraneous `* np.pi` factor:

```python
# BEFORE (wrong — no basis in the standard):
Q_cf = np.where(N_Re < 1000,
    k_f * (1.01 + 1.347 * N_Re**0.52) * np.pi * (T_c - T_a),
    k_f * 0.754 * N_Re**0.6 * np.pi * (T_c - T_a))

# AFTER (matches IEEE Std 738-2023 Eq. 9 / Eq. 10 — no π term in either):
Q_cf = np.where(N_Re < 1000,
    k_f * (1.01 + 1.347 * N_Re**0.52) * (T_c - T_a),
    k_f * 0.754 * N_Re**0.6 * (T_c - T_a))
```

For the standard's own worked-example inputs, the buggy version computed **~1728 A**; the standard's published answer is **1025 A** — a **~69% overestimate**. Fixed version now computes **1034.78 A** (0.95% from published, within a derived-not-guessed tolerance — see the acceptance criteria below and `backend/tests/thermal_model_test.py`'s inline derivation). Flagged prominently in `PRD.md` §9 given the severity — this bug meant the pipeline was overstating dynamic line capacity by roughly two-thirds under at least some conditions, the exact failure mode the project's own ethics section warns against.

## Modeling Assumptions Worth Documenting Explicitly

- **Steady-state only** — no transient/thermal-inertia modeling. This matches IEEE 738's own steady-state formulation, but means rapid weather swings (e.g. wind dying suddenly) aren't captured as a time-dependent temperature ramp — this is the specific "thermal runaway" risk flagged in the Project Definition's ethical considerations, and worth a comment at the call site once C7 depends on it.
- `solar_altitude_deg` is a single fixed value per run, not computed from time-of-day/date/location — a full-day run at a midday-appropriate altitude overstates solar gain for morning/evening observations in the same window.
- **Newly documented (found while validating against the published worked example):** `solar_altitude_deg`'s name is misleading. The function computes `sin(solar_altitude_deg)` as a stand-in for IEEE 738's `sin(θ)`, where θ is the *angle of incidence* of solar rays on the conductor — a quantity depending on both solar position AND the line's azimuth relative to the sun, not the raw solar altitude `Hc`. In the published worked example these differ (`Hc = 74.9°` vs. `θ = 76.2°`). The function does not independently compute incidence angle from line azimuth vs. solar azimuth; it trusts the caller to supply the effective angle. See the function's own docstring in `thermal_model.py` for the full explanation. Not fixed this pass — a known modeling simplification, not the same category of issue as the π bug (this one is a documented approximation the caller needs to be aware of; the π bug was silently wrong with no way for a caller to know).
- `T_c` is fixed at `conductor.T_max` (the limit temperature), not solved iteratively — correct for "what current reaches the limit," but means the function returns ampacity *at* the thermal limit, not at some other operating temperature.

## Blocked by

**C1** — needs conductor config values.

## Blocks

- **C7** — the safety monitor's plausibility gate (G4) should be checking a rating computed by *this* function, not its own placeholder formula.
- **C8** — corridor discretization needs to call this per corridor point.
- **C9** — forecasting needs this as its physical baseline/feature generator.

## Parallel-safe with

C4, C6 (all Phase 2) — the extraction work here touches only `backend/dlr_pipeline.py`'s internals, not the ingestion or ERCOT-merge code paths.

## Known Issues

- ~~Entangled with ingestion...~~ **Fixed** — `thermal_model.py` is now a standalone module with zero ingestion dependencies.
- ~~No reference/regression test exists...~~ **Fixed, and it caught a real bug** — see "Critical Bug Fixed" above and `backend/tests/thermal_model_test.py`.
- ~~`backend/DLRSafetyMonitor.py` (C7) has its own placeholder ampacity formula.~~ **Fixed** — `DLRSafetyMonitor._compute_ampacity` calls `thermal_model.ieee738_ampacity` (`DLRSafetyMonitor.py:105`).

## Acceptance Criteria

- ✅ Ampacity output for a published IEEE 738 worked example falls within an agreed margin of the reference value. Per System Design Report §3.3 ("Known-value validation"). Reference: IEEE Std 738-2023 §4.6.1 (795 kcmil Drake ACSR) — expected 1025 A, this implementation now gives 1034.78 A (0.95% deviation). Tolerance (2%) is derived from a quantified resistance-model difference plus an observed residual, not guessed — full derivation in `backend/tests/thermal_model_test.py`.
- ✅ `ieee738_ampacity` and `perpendicular_wind` are importable and callable without a `SYNOPTIC_TOKEN` set and without triggering any file I/O. Verified.
- ✅ `DLRSafetyMonitor` (C7) and `thermal_model` return the same ampacity for the same inputs, because C7 delegates to `thermal_model.ieee738_ampacity`.

## Open Questions

- Should `solar_altitude_deg` be computed from timestamp + location (proper solar position, distinguishing true altitude from angle-of-incidence) rather than passed as a fixed run-level parameter? Flagged as a modeling assumption above, not decided here.
- ~~Where does the extracted module live~~ — decided: `backend/thermal_model.py`, alongside `dlr_pipeline.py` rather than a full pipeline/thermal split.
- Should the resistance-vs-temperature model be upgraded from the current single-coefficient linear extrapolation to the standard's own two-point interpolation method (using real R(25°C)/R(75°C) reference points per conductor)? The current model's ~1% discrepancy against the standard's method is small but real and quantified in `backend/tests/thermal_model_test.py`.
