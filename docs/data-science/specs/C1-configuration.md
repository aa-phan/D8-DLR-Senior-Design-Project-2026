# C1 — Configuration & Parameterization

**Phase:** 1 (Foundation) · **Effort:** S · **Status:** Not started

**Responsibility:** Provide a single, non-code source for values currently hardcoded and duplicated across modules — station source file, analysis date window, static ratings (per-location), and conductor properties — so every component reads the same values instead of drifting independently.

## Current Implementation

Not started as a distinct module. The values it should own are currently scattered:

- `src/dlr_pipeline.py` `__main__` (lines 507–540): `ConductorConfig` instance, `OUTPUT_CSV`/`OUTPUT_PLOTS` paths, hardcoded station source file `data/wtm_stations_austin.csv`, hardcoded `START`/`END` date window, `static_rating=900.0`.
- `src/ercot_dlr_merger.py:42`: a **second, independent** hardcoded `900.0` A static rating, used to compute `static_capacity_mw`.
- `src/ercot_data_retriever.py` `__main__` (lines 51–52): a third hardcoded date window (`"2025-07-01"` to `"2025-07-05"`), not guaranteed to match `src/dlr_pipeline.py`'s window.
- `Project Definition.md`'s I/O table specifies per-city static rating *ranges* (Austin 800–3000 A, Corpus Christi 1000–5000 A, Midland 600–3000 A, El Paso 600–2300 A) that no code currently reads.

## Interface & Data Contract

Not yet designed in code. Should provide, at minimum:

- A per-location static rating lookup (location → A), replacing the two independent `900.0` literals.
- Conductor properties (currently `ConductorConfig`'s constructor defaults).
- Analysis window and station source, for repeatable runs across the four cities in the Project Definition's I/O table.

Format (JSON/YAML/`.env`-adjacent/Python constants module) is an implementation choice, not specified here — whatever is chosen, it must be importable by C4, C5, C6, and C7 without those modules needing to know how it's stored.

## Blocked by

None — this is a foundation component.

## Blocks

- **C2** (data contract needs to know the config's shape to validate config-derived fields, e.g. `static_capacity_mw` bounds)
- **C4** (weather ingestion needs the station source + date window)
- **C5** (thermal model needs `ConductorConfig` values)
- **C6** (ERCOT retriever needs the date window; merger needs the static rating)
- Transitively, everything downstream of C4/C5/C6 in Phase 3–4 (including C7, which needs `static_rating` for its fallback value — reached via C5, not directly)

## Parallel-safe with

C2, C3 — all three are Phase 1 and touch different concerns (config values vs. schema vs. export format), though C2 and C3 will want to know what shape C1 lands on before finalizing.

## Known Issues

- The two independent `900.0` A literals (`src/dlr_pipeline.py` `__main__` and `src/ercot_dlr_merger.py:42`) can be edited independently and silently disagree — there is no test or check that would catch this today.
- No per-location rating is wired in despite one being specified in `Project Definition.md`'s I/O table — every run currently uses one static rating regardless of city.

## Acceptance Criteria

- A single change to a static rating (per location) is reflected in every module that computes headroom or fallback — no literal duplicated elsewhere.
- `src/dlr_pipeline.py` and `src/ercot_data_retriever.py` read the same date window from the same source when run together for the same analysis.
- Config values are loadable without importing `src/dlr_pipeline.py`'s `__main__` block (i.e., no side effects from importing the config).

## Open Questions

- Config format/location — no strong constraint from the existing code, team's call.
- Should conductor properties be per-line (multiple conductor types across different corridors) or a single global default as today?
