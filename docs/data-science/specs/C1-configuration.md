# C1 — Configuration & Parameterization

**Phase:** 1 (Foundation) · **Effort:** S · **Status:** Implemented (`backend/config.py`)

**Responsibility:** Provide a single, non-code source for values currently hardcoded and duplicated across modules — station source file, analysis date window, static ratings (per-location), and conductor properties — so every component reads the same values instead of drifting independently.

## Current Implementation

Implemented as `backend/config.py`, a plain Python constants module (no new dependencies — matches the "flat `backend/`" convention). Exposes:

- `STATIC_RATINGS: dict[str, float]` — per-city static ratings for 5 Texas cities (`HOUSTON`, `AUSTIN`, `DALLAS`, `FORT_WORTH`, `SAN_ANTONIO`). Sourced via two rounds of research: `SAN_ANTONIO` (1,761 A) has a real citation — ERCOT Board Item 11.2 (Aug 2023), existing single-circuit 345kV J.K. Spruce–Pawnee path, 1,051 MVA normal capacity. The other four have no source differentiating a per-city rating (confirmed across ERCOT, utility, PUCT, and FERC filings) and use an honestly-labeled uniform 900 A baseline (nominal rating for single 795 kcmil Drake ACSR at 138kV, matching this project's own `ConductorConfig` defaults) — see the in-file comments for full sourcing detail and why a real Dallas/Fort Worth number (Oncor Wilmer HTLS-rebuild target spec) was deliberately excluded as unrepresentative.
- `DEFAULT_STATIC_RATING = 900.0` — fallback for any location not in `STATIC_RATINGS`.
- `DEFAULT_CONDUCTOR_CONFIG_KWARGS` — the `ConductorConfig` kwargs previously hardcoded in `dlr_pipeline.py`'s `__main__`.
- `DEFAULT_STATION_SOURCE`, `DEFAULT_START`, `DEFAULT_END` — moved unchanged from `dlr_pipeline.py`'s `__main__`.
- `LINE_VOLTAGE_KV = 345.0`, `POWER_FACTOR = 0.95` — moved from `ercot_dlr_merger.py`'s module-level constants.

`backend/dlr_pipeline.py`'s `__main__` and `backend/ercot_dlr_merger.py` both import from `config.py` now instead of holding independent literals — this directly fixes the "two independent `900.0` A literals" known issue below. Runtime values are unchanged from before this component landed; only their source changed.

Not yet done: nothing selects a specific city's `STATIC_RATINGS` entry per pipeline run — `run_pipeline`/`plot_dlr_summary` still receive `config.DEFAULT_STATIC_RATING` unconditionally. Per-location selection (matching a run to one of the 5 cities) is future wiring, not part of this component's scope.

## Interface & Data Contract

`backend/config.py`, importable as `import config` from any script co-located in `backend/` (or via `pythonpath = backend` in `pytest.ini` for tests). Importing it has no side effects (no file I/O, no network calls).

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

- ~~The two independent `900.0` A literals...~~ **Fixed** — both files now import `config.DEFAULT_STATIC_RATING`.
- `STATIC_RATINGS` exists but nothing selects a per-city entry per run yet (see Current Implementation) — every run still effectively uses `DEFAULT_STATIC_RATING` regardless of which of the 5 cities it's analyzing. The lookup table is built; the wiring to actually use it per-location is still open.
- `backend/ercot_data_retriever.py`'s own hardcoded date window (`"2025-07-01"` to `"2025-07-05"` in its `__main__`) was NOT moved into `config.py` — it's a separate, still-hardcoded literal that can still drift from `config.DEFAULT_START`/`DEFAULT_END`. Out of scope for this implementation pass; flagged for a future pass.

## Acceptance Criteria

- ✅ A single change to a static rating (per location) is reflected in every module that computes headroom or fallback — no literal duplicated elsewhere. (True for the two fixed literals; `ercot_data_retriever.py`'s date window is the one remaining exception, see Known Issues.)
- ⚠️ `backend/dlr_pipeline.py` and `backend/ercot_data_retriever.py` read the same date window from the same source when run together for the same analysis. **Not yet met** — see Known Issues above.
- ✅ Config values are loadable without importing `backend/dlr_pipeline.py`'s `__main__` block (i.e., no side effects from importing the config). Verified: `config.py` has zero side effects at import time.

## Open Questions

- Config format/location — no strong constraint from the existing code, team's call.
- Should conductor properties be per-line (multiple conductor types across different corridors) or a single global default as today?
