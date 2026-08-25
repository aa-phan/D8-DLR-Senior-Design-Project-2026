# C5 — Thermal Model (IEEE 738)

**Phase:** 2 (Core Consolidation) · **Effort:** M · **Status:** Implemented and correct in structure; not packaged as an independently importable module (currently entangled with `backend/dlr_pipeline.py`'s ingestion/orchestration code and `__main__` side effects).

**Responsibility:** Compute steady-state IEEE 738 conductor ampacity from weather inputs and conductor properties. This is the physics core every other component (C7, C8, C9) should call rather than reimplement — the current biggest structural problem in the repo is that `backend/DLRSafetyMonitor.py` reimplements a *different, wrong* version of this instead of calling it.

## Current Implementation

All in `backend/dlr_pipeline.py`:

- `ConductorConfig` (lines 210–233) — physical conductor parameters. Defaults model 795 kcmil Drake ACSR: diameter 0.02814 m, AC resistance 0.0726 Ω/km @ 25°C, resistance temp coefficient 0.00404/°C, emissivity/absorptivity 0.8, max temp 75°C, line azimuth 90°, elevation 300 m.
- `perpendicular_wind(wind_speed_ms, wind_dir_deg, line_azimuth_deg) -> np.ndarray` (line 170) — projects wind onto the line-perpendicular axis; below 20° incidence, floors at `ws * sin(20°)` to avoid instability in the natural-convection regime.
- `ieee738_ampacity(T_amb_c, wind_perp_ms, ghi_wm2, conductor, solar_altitude_deg=45.0) -> np.ndarray` (line 252) — the heat balance: `I = sqrt((Q_conv + Q_rad - Q_solar) / R(T_c))`, with forced/natural convection as `max(Q_cf, Q_cn)` (Reynolds-number-dependent forced convection, natural convection floor) and radiative loss via linearized Stefan-Boltzmann.
- Helper functions `_air_density`, `_dynamic_viscosity`, `_thermal_conductivity` (lines 236–249).

## Interface & Data Contract

Inputs: `T_amb_c` (degC), `wind_perp_ms` (m/s), `ghi_wm2` (W/m²), a `ConductorConfig`, `solar_altitude_deg` (deg). Output: ampacity in Amperes, matching `PIPELINE_SCHEMA`'s `dlr_amps` (range 100–4000 A).

**Target design:** extract `ConductorConfig`, `perpendicular_wind`, `ieee738_ampacity`, and the three `_air_*`/`_thermal_*` helpers into a module with no ingestion dependencies and no `__main__` side effects, so `import` alone doesn't require a Synoptic token or trigger a pipeline run. `backend/dlr_pipeline.py::run_pipeline` becomes a caller of this module rather than the module itself.

## Modeling Assumptions Worth Documenting Explicitly

- **Steady-state only** — no transient/thermal-inertia modeling. This matches IEEE 738's own steady-state formulation, but means rapid weather swings (e.g. wind dying suddenly) aren't captured as a time-dependent temperature ramp — this is the specific "thermal runaway" risk flagged in the Project Definition's ethical considerations, and worth a comment at the call site once C7 depends on it.
- `solar_altitude_deg` is a single fixed value per run, not computed from time-of-day/date/location — a full-day run at a midday-appropriate altitude overstates solar gain for morning/evening observations in the same window.
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

- Entangled with ingestion: currently, calling `ieee738_ampacity` in isolation is fine (it's a pure function), but the module it lives in (`backend/dlr_pipeline.py`) has a `__main__` block with real side effects, so "just import the thermal model" pulls in an entire file whose top-level structure assumes it's being run as a script.
- No reference/regression test exists comparing `ieee738_ampacity`'s output against a known historical or published ampacity value — the acceptance criterion below is not yet met.

## Acceptance Criteria

- Ampacity output for a known historical weather/rating pair (or a published IEEE 738 worked example) falls within an agreed margin of the reference value. Per System Design Report §3.3 ("Known-value validation"). No fixture exists yet — needed before this can be marked done.
- `ieee738_ampacity` and `perpendicular_wind` are importable and callable without a `SYNOPTIC_TOKEN` set and without triggering any file I/O.
- `DLRSafetyMonitor` (C7) and `dlr_pipeline` (this component) return the same ampacity for the same weather inputs and conductor config — the current biggest cross-component inconsistency in the repo.

## Open Questions

- Should `solar_altitude_deg` be computed from timestamp + location (proper solar position) rather than passed as a fixed run-level parameter? Flagged as a modeling assumption above, not decided here.
- Where does the extracted module live — a new `thermal_model.py`, or does `backend/dlr_pipeline.py` get split into `thermal_model.py` + `pipeline.py`?
