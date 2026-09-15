# Dynamic Line Rating (DLR) System

## Current State (as of v1.1)

**Shipped 2026-09-15.** The Data Science subsystem's weather ingestion is now a ratified,
five-provider composition behind one adapter (`backend/weather_provider.py::fetch_weather`):
TCEQ CAMS + ASOS 1-minute (wind/temp/RH, station path), NREL NSRDB PSM v4 (solar, grid path),
Open-Meteo (historical bulk backfill, grid path, standalone), and Synoptic retained as the
automatic fallback behind TCEQ/NSRDB only — never an additional/parallel source, and never
triggered by a caller-shaped error or a missing-credential `EnvironmentError`. Every row carries
per-field provenance (`wind_source`, `temp_source`, `humidity_source`, `solar_source`) so exports
and plots can show which provider actually supplied each value. `PRD.md` §7.1 and
`data_provider.md` now record this as the team's ratified decision, closing the project's
longest-standing open engineering item and the System Design Report's self-flagged NOAA/NSRDB
discrepancy (see `docs/data-science/PRD.md` §10, corrected in this milestone). See
`.planning/workstreams/multi-provider-weather/milestones/v1.1-ROADMAP.md` and
`v1.1-REQUIREMENTS.md` for the full archived record, and `.planning/milestones/v1.0-ROADMAP.md`/
`v1.0-REQUIREMENTS.md` for v1.0.

**What's still a gap going into the next milestone:** `ampacity_forecast.forecast_ampacity` and
`anomaly_detector.AnomalyDetector` are implemented and tested but have no production caller —
`api/` and `frontend/` remain documented, not-started placeholders owned by the Software
sub-team. Whoever builds that serving/scheduler layer needs to wire the Phase 3+4 loop
(`rate_corridor` with a real, history-backed `AnomalyDetector`, periodic archive→forecast refit)
live; today it's proven only by tests. Separately, TCEQ solar-radiation instrumentation remains
confirmed only for Austin/Corpus Christi CAMS sites (tracked as v2 requirement WX-09 if TCEQ solar
is ever pursued — TCEQ is wired for wind/temp/RH only in v1.1).

## Current Milestone

No milestone is currently active. Run `/gsd-new-milestone` to scope v1.2.

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
- ✓ DS-F7: Safety monitor unified with the real IEEE 738 thermal model (`DLRSafetyMonitor._compute_ampacity` calls `thermal_model.ieee738_ampacity` directly); every gate (G1-G5) resolves toward the static rating, never an optimistic guess — Phase 3
- ✓ DS-F10: Corridor spatial discretization — `corridor_discretization.py` discretizes each corridor into 5 great-circle points and takes the minimum per-point ampacity as the corridor-level rating, with the bottleneck point identified — Phase 3
- ✓ DS-NF5: Fail-safe by default, extended to corridors — a candidate-probe exhaustion (no usable station data for a point) resolves to the corridor's static rating rather than dropping the point, raising, or interpolating — Phase 3
- ✓ DS-F5: Per-location static-rating comparison — `config.STATIC_RATINGS.get(city, config.DEFAULT_STATIC_RATING)` wired into `dlr_pipeline.py::run_pipeline`/`plot_dlr_summary` and `ercot_dlr_merger.py::process_dlr_to_hourly` (already wired into `corridor_discretization.py` since Phase 3) — v1.0 (Phase 5)
- ✓ DS-F11: Ampacity forecasting ahead of real time — `ampacity_forecast.forecast_ampacity`, out-of-sample expanding-window walk-forward backtested confidence band, published through `PIPELINE_SCHEMA` v2's additive columns — v1.0 (Phase 4)
- ✓ DS-F12: Learned anomaly detection, additive to the fallback path — `anomaly_detector.AnomalyDetector` (forecast-residual + rolling-baseline cold start) wired as gate G6 into `DLRSafetyMonitor._fallback` — v1.0 (Phase 4)
- ✓ WX-01/WX-02: TCEQ CAMS (primary) + ASOS 1-minute (temporal-density supplement) for wind speed, wind direction, temperature, and RH across all four cities — v1.1 (Phases 7, 9)
- ✓ WX-03: NREL NSRDB PSM v4 as the primary solar-irradiance source, live-confirmed against the real API — v1.1 (Phase 8)
- ✓ WX-04: Open-Meteo Archive API as the historical bulk-backfill source for C9/C10 training data — v1.1 (Phase 7)
- ✓ WX-05: `weather_provider.py::fetch_weather` combines station-based (TCEQ/ASOS) and grid-based (NSRDB/Open-Meteo) providers into one row per timestamp via a type-dispatched `location` parameter, with zero changes required of existing callers — v1.1 (Phase 6)
- ✓ WX-06: Synoptic retained as the automatic fallback behind TCEQ/NSRDB only (never an additional source, never triggered by a caller-shaped error or missing-credential `EnvironmentError`), confirmed end-to-end against the live Synoptic and NSRDB endpoints — v1.1 (Phase 10)
- ✓ WX-07: `PIPELINE_SCHEMA` v3 extended with per-field provenance columns (`wind_source`, `temp_source`, `humidity_source`, `solar_source`) — v1.1 (Phase 6)
- ✓ WX-08: `PRD.md` §7.1 and `data_provider.md` ratified to record the shipped per-variable composition, resolving the "Pending" status and the System Design Report's self-flagged discrepancy — v1.1 (Phase 10)

### Active

<!-- Current scope. No milestone is active — run /gsd-new-milestone to scope v1.2. -->

(None — awaiting v1.2 requirements definition.)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- PSS/E grid simulation and load-flow integration — owned by the Power Systems sub-team; this subsystem only supplies ampacity/MW values as input
- N-1 contingency screening, reactive power / voltage stability analysis — PRD §1 explicitly scopes this to other sub-teams
- UI dashboard implementation — owned by the Software sub-team (`docs/frontend/`, `frontend/`, `api/` are placeholders); this subsystem only needs to publish a stable output schema (C3)

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
- **Documentation discrepancies (self-flagged in `PRD.md` §10, updated after v1.1):** as of v1.0
  the System Design Report claimed NOAA+NSRDB was selected for weather data, that a corridor
  spatial pipeline exists, and that an ML anomaly-detection model is "currently being trained" —
  none of that matched the repo state at the time. C8/C10 shipped in v1.0 (Phases 3-4), closing
  those two rows. The NOAA+NSRDB row is now substantially correct for the solar half after v1.1:
  NSRDB is the real solar primary (TCEQ CAMS, not NOAA, supplies wind/temperature) — `PRD.md` §10
  records this correction in its existing RESOLVED-row style; the exact wording should be restated
  precisely in the next System Design Report submission.
- **Known safety-relevant bug (fixed):** `thermal_model.py`'s forced-convection term had an
  erroneous `* np.pi` factor with no basis in IEEE Std 738-2023 — it overstated ampacity by ~69%
  for the standard's own worked example before being caught during reference validation. This is
  the exact failure mode the fail-safe commitment exists to prevent; it's why known-value
  validation is treated as load-bearing, not a formality, going forward.
- **AI-use disclosure requirement:** ECE 464 requires disclosing AI assistance in
  `ACKNOWLEDGEMENTS.md`; update it before any significant AI-assisted commit.
- **Carried-forward blockers (unaffected by v1.1):** `ercot_data_retriever.py::pull_ercot_data`'s
  live path fails with a deterministic `Bad CRC-32` error inside the third-party `gridstatus`
  library, blocking live ERCOT pulls until upstream fixes it.

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
| **RESOLVED — Geographic/corridor scope**: adopted `Project Definition.md`'s 4-city scope (Austin, Corpus Christi, Midland, El Paso) as authoritative for `config.py::STATIC_RATINGS`, replacing the previous mismatched 5-city table. See `docs/data-science/decisions/geographic_scope.md` for full evidence and rationale. | `PRD.md` §10 and `data_provider.md` already implicitly treated the 4-city spec as ground truth; this makes it official. `config.py::STATIC_RATINGS` re-keyed to the 4 cities (midpoint of each city's documented static-limit range); `dlr_pipeline.py`'s redundant dead-code stub deleted. | ✓ Resolved 2026-09-02. Corridor-endpoint mapping (previously open) resolved 2026-09-08 — see next row. |
| **RESOLVED — Corridor endpoints for C8**: `config.CORRIDOR_ENDPOINTS` defines exactly two corridors (Austin↔Corpus Christi, Midland↔El Paso / D-01), each endpoint resolving into `CITY_COORDINATES`/`STATIC_RATINGS`/`RATING_BOUNDS_BY_LOCATION` — one consistent geographic model across station discovery, static ratings, and discretization. Legacy `station_explorer.py::CORRIDORS` left untouched, not read by the new module. | Closed the gap `geographic_scope.md` flagged as still open. City coordinates for Corpus Christi/El Paso needed live re-verification against OpenStreetMap Nominatim (US Census Gazetteer diverged materially due to those cities' irregular incorporated-limits shapes). | ✓ Resolved 2026-09-08 — Phase 3 (03-02) |
| **RESOLVED — Weather data provider**: adopted `data_provider.md`'s per-variable composition (TCEQ+ASOS for wind/temp/RH, NSRDB for solar, Open-Meteo for historical backfill, Synoptic retained as automatic fallback — never an additional/parallel source) to resolve `PRD.md` §7.1 | Synoptic/WTM has real research-tier scaling limits and doesn't match the real four-city spec's coverage; the vetting log in `data_provider.md` already did the candidate research — no single provider is both observation-grade and variable-complete, so per-variable sourcing was the strongest option found | ✓ Resolved 2026-09-15 — Phases 6-10 (v1.1); ratified in `PRD.md` §7.1/`data_provider.md`, confirmed against live Synoptic/NSRDB endpoints |
| TCEQ multi-day fetch capped at 31 calendar days per request (`TCEQ_MAX_DAYS_PER_FETCH`) rather than serving unbounded historical backfill | `daily_summary.pl` is a free, unauthenticated, public government CGI endpoint with no documented rate limit; the project chose not to service long backfills by issuing hundreds of rapid sequential requests against it — Open-Meteo (WX-04) exists for bulk historical backfill instead | ✓ Resolved — Phase 9 (09-02) |
| Fallback eligibility (Synoptic behind TCEQ/NSRDB) computed before any provider dispatch, keyed on provider+path only — never on error type; `EnvironmentError` (missing credential) is never masked by a fallback | A caller-shaped error (unknown provider, wrong path, multiple CAMS IDs, unresolvable coordinates) must never trigger a real network fallback request; a misconfigured machine (missing credential) must stay visibly broken rather than silently served from a fallback that looks like success | ✓ Resolved — Phase 10 (10-01/10-02) |
| NSRDB window requests spanning a calendar-year boundary decomposed into per-year requests and reassembled, rather than raising or truncating | NSRDB's PSM v4 API is year-scoped per request; C9/C10 training windows can legitimately cross a year boundary | ✓ Resolved — Phase 8 (08-02) |
| C7 (`DLRSafetyMonitor`) currently computes ampacity with a placeholder linear formula, not the real IEEE 738 model in C5 | Historical: C7 was written before C5's thermal model was extracted into its own module | ✓ Resolved 2026-09-08 — Phase 3 (03-01) unified `_compute_ampacity` with `thermal_model.ieee738_ampacity` |
| G5 ("large rating swing") large-swing checkpoint: flat vs. relative threshold shape, and whether it should fall back at all | Checkpoint decision required during 03-01 execution — old flat 150A threshold was calibrated against the placeholder formula's output range, not real IEEE 738 magnitudes (~1700-2300A) | ✓ Resolved 2026-09-08 — chose relative threshold (`config.DELTA_FRACTION = 0.15`) with conservative `min(computed, static_rating)` fallback under `status="fallback"`; `last_good_rating` still updates so a genuine sustained weather change resolves in one cycle |
| Anomaly detection (G6) trained on a rolling baseline with per-corridor control limits, additive to (never replacing) the G1-G5 fallback chain | C10 needed a cold-start path since historical archives start empty; wider-of-two-endpoint-cities control limit avoids one city's noisier readings suppressing detection at the other endpoint | ✓ Resolved 2026-09-09 — Phase 4 (04-01/04-03); `AnomalyDetector.for_corridor` resolves per-corridor limits, `rate_corridor` wires it as an optional constructor param, fail-safe on exception |
| Forecast confidence band: in-sample residual vs. true out-of-sample backtest | An in-sample band would understate real forecast error; only an expanding-window walk-forward backtest measures the model against data it hasn't seen | ✓ Resolved 2026-09-09 — Phase 4 (04-02) — replaced the tracer's in-sample band with a true walk-forward backtest; added EWM as a second Tier 1 method behind the same signature |
| DS-F5 wiring scope: silently fall back to `DEFAULT_STATIC_RATING` on unknown/omitted city vs. validate-and-raise (as `corridor_discretization.py` does) | Phase 5 chose the conservative-silent path for the flat-pipeline consumers since `DEFAULT_STATIC_RATING` (900A) is strictly lower than every configured city rating, so an unrecognized city can't cause an optimistic overstatement — deliberately asymmetric with the corridor path, which validates and raises | ✓ Resolved 2026-09-10 — Phase 5 (05-01); flagged as tech debt for future consistency review, not a defect (see `.planning/milestones/v1.0-MILESTONE-AUDIT.md`) |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-09-15 after v1.1 milestone*
