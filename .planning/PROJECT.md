# Dynamic Line Rating (DLR) System

## What This Is

The Data Science subsystem of a senior-design Dynamic Line Rating project: it turns raw weather
and grid telemetry into a trustworthy, physically-grounded ampacity rating for transmission lines
(IEEE Standard 738), compares that rating against conservative static ratings, and guarantees a
fail-safe fallback to the static rating whenever inputs can't be trusted. It is one of three
sub-teams' worth of scope (Data Science / Power Systems (PSS/E) / Software (UI)); this project
covers the Data Science subsystem only — grid simulation, N-1 contingency screening, and the UI
dashboard are owned elsewhere and consumed, not built, here.

## Core Value

The end-to-end pipeline produces valid ampacity forecasts — weather ingestion through thermal
model through export — and runs without manual intervention, while never letting an unreliable
input silently overstate what a line can safely carry (fail-safe to static rating is the standing
ethical commitment, not a nice-to-have).

## Requirements

### Validated

<!-- Inferred from existing code (brownfield onboarding) + confirmed by PRD.md's own "Status" column, reviewed against repo state 2026-08-24. -->

- ✓ Weather station discovery near defined corridors (`backend/station_explorer.py`) — Phase 2 (pre-GSD, commit `9680772`/`ffbea4f`)
- ✓ Provider-agnostic weather observation fetch (`backend/weather_provider.py`) — Phase 2
- ✓ Perpendicular wind component + steady-state IEEE 738 ampacity (`backend/thermal_model.py`) — Phase 2, validated against the published IEEE Std 738-2023 worked example (a real π-factor bug causing a ~69% overestimate was found and fixed during this validation)
- ✓ Unit/dimensional validation across every pipeline row (`backend/units_def.py::PIPELINE_SCHEMA`) — Phase 1
- ✓ ERCOT West-zone grid load merge + Amps→MW conversion (`backend/ercot_dlr_merger.py`) — Phase 2
- ✓ CSV export + 4-panel summary plots per station (`backend/dlr_pipeline.py`) — Phase 1

### Active

<!-- Current scope. Building toward these. -->

- [ ] DS-F5: Wire static-vs-DLR comparison to select the correct per-run location (currently uses a uniform fallback rating) — blocked on the open geographic scope decision below
- [ ] DS-F7: Unify the safety monitor's ampacity check with the real IEEE 738 thermal model (currently a disagreeing placeholder formula)
- [ ] DS-F10: Corridor spatial discretization — discretize a corridor into points, take the minimum ampacity as the corridor-level rating
- [ ] DS-F11: Ampacity forecasting ahead of real time (regression/ML)
- [ ] DS-F12: Learned anomaly detection trained on historical baselines, additive to the C7 fallback path

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- PSS/E grid simulation and load-flow integration — owned by the Power Systems sub-team; this subsystem only supplies ampacity/MW values as input
- N-1 contingency screening, reactive power / voltage stability analysis — PRD §1 explicitly scopes this to other sub-teams
- UI dashboard implementation — owned by the Software sub-team (`docs/frontend/`, `frontend/`, `api/` are placeholders); this subsystem only needs to publish a stable output schema (C3)
- Implementing a second weather provider (NOAA/NSRDB) right now — the provider choice is a genuinely open decision (see below); building NOAA integration today would prematurely resolve it. `weather_provider.py`'s adapter boundary exists specifically so this can be added later without touching downstream modules

## Context

- **Program:** Senior design capstone (ECE 464), team of six (Ben Huynh, Tejaswini Kalikiri,
  Agustin Wilde, Benjamin Meunier, Allie Cao, Aaron Phan). This repo's `docs/data-science/`
  (PRD.md, ROADMAP.md, `specs/C1`–`C10`) is the internal engineering reference for the DS
  subsystem specifically; `Project Definition.md`, `System Design Report.md`, and
  `Prior Art Report.md` are separate course deliverables and are not always in sync with actual
  repo state (see Documentation Discrepancies below).
- **Existing 4-phase structure already in use:** `docs/data-science/ROADMAP.md` and `PRD.md` §4
  already define this project's phase order (Foundation → Core Consolidation → Safety & Spatial →
  Predictive), driven by a real dependency graph (C1 blocks C4/C5/C6; C4+C5 block C7/C8/C9; C7
  blocks C10). This project's ROADMAP.md adopts that structure directly rather than inventing a
  new one — it already fits this project's own delivery boundaries.
- **Where things stand today:** Phase 1 (C1 Configuration, C2 Data Contract, C3 Export &
  Visualization) and Phase 2 (C4 Weather Ingestion, C5 Thermal Model, C6 Grid Load Integration)
  are implemented and committed (`9680772`, `ffbea4f`). Phase 3 (C7 Safety Monitor unification, C8
  Corridor Discretization) and Phase 4 (C9 Forecasting, C10 Learned Anomaly Detection) are not
  started. This is the first `.planning/` setup for this repo (GSD wasn't used for Phases 1–2);
  they're recorded here as Complete to reflect reality, not re-planned from scratch.
- **Documentation discrepancies (self-flagged in `PRD.md` §10):** the System Design Report claims
  NOAA+NSRDB was selected for weather data, that a corridor spatial pipeline exists, and that an
  ML anomaly-detection model is "currently being trained" — none of this matches the actual repo
  state. Synoptic/West Texas Mesonet is the only working weather source; C8 and C10 are not
  started. Per default doc precedence (SPEC/PRD > DOC), this PROJECT.md reflects the SPEC/PRD
  state (what's actually built), not the course-deliverable claims.
- **Known safety-relevant bug (fixed):** `thermal_model.py`'s forced-convection term had an
  erroneous `* np.pi` factor with no basis in IEEE Std 738-2023 — it overstated ampacity by ~69%
  for the standard's own worked example before being caught during reference validation. This is
  the exact failure mode the fail-safe commitment exists to prevent; it's why known-value
  validation is treated as load-bearing, not a formality, going forward.
- **AI-use disclosure requirement:** ECE 464 requires disclosing AI assistance in
  `ACKNOWLEDGEMENTS.md`; update it before any significant AI-assisted commit.

## Constraints

- **Tech stack**: Python 3.12 (pandas, numpy, scipy, matplotlib, requests, gridstatus), pytest for
  testing. No build step. `.venv` for isolation. — established stack for the DS pipeline; frontend
  (React) and API (Flask) are separate, not-yet-started subsystems owned elsewhere.
- **Secrets**: `SYNOPTIC_TOKEN` (and any future provider tokens) live in `.env` only, which is
  gitignored — required by the NFR "no secrets committed" and by good practice for a
  student-team-shared repo.
- **Data contract**: `backend/units_def.py::PIPELINE_SCHEMA` is the single canonical schema for
  every pipeline output column (unit, range, required flag) — per its own spec text, "do not
  restate it in any other spec or doc." Any new component that adds output columns (C8, C9, C10)
  must extend this schema, not create a parallel one.
- **Fail-safe ethical commitment**: any missing sensor, broken link, out-of-range reading,
  implausible rating, or large rating swing must resolve toward the static rating, never an
  optimistic guess — this is a standing project commitment (`Project Definition.md`), not scoped
  to any single phase, and must keep holding as C7/C10 get more sophisticated.
- **Execution runtime**: this project's planning/execution workflow targets Claude (Claude Code)
  as the implementer.
- **Course policy**: AI-assisted commits require an `ACKNOWLEDGEMENTS.md` update (ECE 464
  requirement) before the commit.

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Adopt the existing 4-phase structure from `docs/data-science/ROADMAP.md`/`PRD.md` §4 (Foundation → Core Consolidation → Safety & Spatial → Predictive) as this project's ROADMAP.md | Already derived from the real component dependency graph (C1→{C4,C5,C6}→{C7,C8}→{C9,C10}); two of the four phases are already delivered against it | ✓ Good — validated by two completed phases |
| **RESOLVED — Geographic/corridor scope**: adopted `Project Definition.md`'s 4-city scope (Austin, Corpus Christi, Midland, El Paso) as authoritative for `config.py::STATIC_RATINGS`, replacing the previous mismatched 5-city table. See `docs/data-science/decisions/geographic_scope.md` for full evidence and rationale. | `PRD.md` §10 and `data_provider.md` already implicitly treated the 4-city spec as ground truth; this makes it official. `config.py::STATIC_RATINGS` re-keyed to the 4 cities (midpoint of each city's documented static-limit range); `dlr_pipeline.py`'s redundant dead-code stub deleted. | ✓ Resolved 2026-09-02. **Still open** (tracked in `geographic_scope.md`): how the 4 cities map to corridor endpoints for C8 — `station_explorer.py::CORRIDORS`' West-Texas corridors were deliberately left unchanged pending that separate design question. |
| **OPEN — Weather data provider** (Synoptic vs. NOAA vs. hybrid) | Genuinely unresolved per `PRD.md` §7.1; Synoptic/WTM is what works today behind `weather_provider.py`'s adapter, but has real research-tier scaling limits; NOAA has no code written against it yet and doesn't provide solar (would need NSRDB too) | — Pending. Explicitly must not block Phase 2/3 work (`PRD.md` §7.1) |
| C7 (`DLRSafetyMonitor`) currently computes ampacity with a placeholder linear formula, not the real IEEE 738 model in C5 | Historical: C7 was written before C5's thermal model was extracted into its own module | ⚠️ Revisit — scheduled to be fixed by unifying them in Phase 3 |

---
*Last updated: 2026-09-02 after initial project setup (doc-ingest synthesis)*
