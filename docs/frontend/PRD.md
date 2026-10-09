<!-- generated-by: gsd-doc-writer -->
# Software Subsystem (Dashboard + API) — Product Requirements

**Status:** Internal engineering reference. Not a course deliverable — does not replace or get submitted alongside `Project Definition.md`, `Prior Art Report.md`, or `System Design Report.md`. Written to define what the Software sub-team's subsystem (`frontend/` React dashboard and `api/` Flask backend-for-frontend) must do, grounded in those course documents and in what the Data Science (DS) subsystem actually produces today. **Nothing described here has been built** — `frontend/` and `api/` each contain only a placeholder README.

**Last reviewed against repo state:** 2026-10-08

---

## 1. Purpose & Scope

The Software subsystem turns the DS pipeline's output into an operator-facing dashboard: a grid operator selects a location, sees the current dynamic thermal limit next to the static limit, sees the weather driving it, sees a forecast and how long the limit should be trusted, and is told clearly when the data cannot be trusted and the system has fallen back to the static rating. This corresponds to WBS §4.0 (Software Development Sub-Team) in the System Design Report (Appendix B, tasks 4.1–4.3).

**In scope:**
- A React dashboard (`frontend/`) — the "UI dashboard" deliverable of `Project Definition.md` ("Project Deliverables → UI Specifications") and `System Design Report.md` §3.1 (Output Layer)
- A Flask backend-for-frontend (`api/`) that serves the dashboard from DS pipeline output (currently flat files — see `docs/data-science/specs/C3-export-visualization.md`)
- Location selection, current-limit and weather display, DLR-vs-static capacity visualization, forecast / trusted-duration display, anomaly and fallback status indicators (WBS 4.1.1–4.1.5)
- Connecting DS outputs to the dashboard feed (WBS 4.2.1) and, when its contract exists, PSS/E outputs (WBS 4.2.2)
- End-to-end integration testing and the ISO 9241 usability review (WBS 4.2.3, 4.3.4)

**Explicitly out of scope** (owned elsewhere, referenced only as producers):
- Computing ratings, forecasts, anomaly decisions, or fallback decisions — owned by DS (C5, C9, C7/C10). The Software subsystem **displays** them and must not recompute them (see SW-NF4).
- PSS/E simulation, N-1 contingency, and voltage-stability analysis — Power Systems sub-team
- The economic/reliability research paper
- The optional hardware observation device (`Project Definition.md`: "if time permits")

Note: WBS 4.3.1–4.3.3 (known-value validation, synthetic stress testing, dimensional-analysis validation) sit under the Software sub-team heading in Appendix B/C but are verification of the DS pipeline's numerical behavior; this PRD treats them as owned by DS's own test suites and only covers the dashboard-facing parts (F8).

## 2. Problem Statement

Static Line Ratings hide the 30–50% of extra capacity that exists most of the time (`Project Definition.md`, "Background Information"). The DS pipeline can compute that capacity, but a rating that only exists in CSV files is not usable by an operator, and a dynamic rating is only safe to act on when the operator can tell, at a glance, (a) what the number is, (b) how long it can be trusted, and (c) whether the system has already fallen back to the static rating because inputs became unreliable. The dashboard's job is to make the capacity visible **without ever making an untrustworthy dynamic rating look trustworthy** — the same fail-safe commitment as `Project Definition.md` "Ethical Considerations" ("If the data cuts out, the system must default back to the conservative static rating immediately").

## 3. Users & Consumers

| Consumer | Needs from the Software subsystem |
|---|---|
| Grid operator (primary user, per `Project Definition.md` UI Specifications and ISO 9241 entry in Appendix A) | Correctly interpret dynamic ratings and system alerts "without additional guidance" (`System Design Report.md` §3.3, UI Dashboard) |
| Faculty / TA / course graders | A working prototype demonstrating DLR vs. SLR, forecasting, and anomaly/fallback indication (course deliverable) |
| Power Systems sub-team | Eventually, a view of PSS/E-derived outputs (WBS 4.2.2); contract undefined — see §7 OD-9 |
| Data Science sub-team | A consumer that exercises their exported schema early and reports contract gaps — see §8 |

| Producer | What the Software subsystem needs from it |
|---|---|
| DS pipeline (via C3 export, `docs/data-science/schema/pipeline_output_v1.md`) | Per-location DLR value, headroom, weather inputs; **also** forecast, trusted-duration, and fallback/alert status — most of which the v1 export does not yet carry (§8) |
| DS fixture (`data/fixtures/sample_pipeline_output.csv`) | The only dashboard-development data guaranteed to exist on a fresh clone — `outputs/` is gitignored (`.gitignore: /outputs`) |

## 4. How This PRD Relates to the Roadmap

This document defines **what** the subsystem must do (requirements) and **why** (problem/users). `ROADMAP.md` defines **in what order** to build it and **what blocks what**. `specs/F1`–`F8` define **how** each piece works. Read in that order: PRD → ROADMAP → specs. This mirrors the convention in `docs/data-science/`.

Work is organized into eight components (`specs/README.md` has the full index), grouped into four phases ordered least→most complex / most-externally-dependent:

| Phase | Components | Theme |
|---|---|---|
| 1 — Foundation | F1 Data Access & API Layer, F2 Dashboard Shell & Location Selection | Fix the data contract the UI reads and the frame every panel sits in |
| 2 — Core Views | F3 Line Status & Current Conditions, F4 DLR vs. Static Capacity Chart | The views fully supportable by the v1 export today |
| 3 — Predictive & Safety Views | F5 Forecast & Trusted Duration, F6 Anomaly & Fallback Status | Views whose data the v1 export does not yet carry — externally blocked on DS |
| 4 — Integration & Validation | F7 PSS/E Output Integration, F8 Integration, E2E & Usability Validation | Cross-team wiring and the course test plan |

## 5. Functional Requirements

Status reflects what exists in the repo: **all Not started**. "Source" cites the document that creates the requirement, so nothing here is invented. Each maps to the component that owns it — see that component's spec for interface detail.

| ID | Requirement | Source | Status | Owning Component |
|---|---|---|---|---|
| SW-F1 | Operator can select a location from a preset list of locations in the project's data (not free-form entry) | `Project Definition.md` UI Specifications ("users to only be able to select from a preset amount of locations") | Not started | F2 |
| SW-F2 | Display the current dynamic thermal limit (A) for the selected location alongside its static limit | `Project Definition.md` (mock-up: "calculate a new dynamic thermal limit"); I/O table outputs | Not started | F3 |
| SW-F3 | Display current weather conditions driving the rating: ambient temperature, wind speed, solar irradiance | `Project Definition.md` (mock-up: "current weather condition"); I/O table inputs | Not started | F3 |
| SW-F4 | Display the current sag of the line | `Project Definition.md` (mock-up: "current sag of the line") | Not started — **no data producer exists** (OD-4) | F3 |
| SW-F5 | Display the trusted duration of the current dynamic limit | `Project Definition.md` (mock-up and I/O table "Trusted Duration of New Limit"); `System Design Report.md` §3.3 (refresh window) | Not started — **definition unresolved** (OD-3) | F5 |
| SW-F6 | Visualize dynamic vs. static capacity over time | WBS 4.1.3; `Project Definition.md` ("visualizing dynamic capacity") | Not started | F4 |
| SW-F7 | Display forecast future ratings | WBS 4.1.4; `Project Definition.md` ("forecast future ratings based on environmental inputs") | Not started — forecast columns not in v1 export (§8, G3) | F5 |
| SW-F8 | Display anomaly and fallback status indicators, and operator alerts | WBS 4.1.5; `System Design Report.md` §3.2 Data Integrity ("Alerts are also generated for operators") | Not started — status not in v1 export (§8, G2) | F6 |
| SW-F9 | Read DS pipeline outputs through an API the dashboard calls (the "dashboard data feed") | WBS 4.2.1; `api/README.md` | Not started | F1 |
| SW-F10 | Show PSS/E simulation outputs on the dashboard | WBS 4.2.2 | Not started — **contract undefined** (OD-9) | F7 |
| SW-F11 | Define operator workflow and display requirements per ISO 9241; produce dashboard layout / alert wireframes | WBS 4.1.1, 4.1.2 | Not started | F2 |
| SW-F12 | Verify end to end: a weather-input change propagates to an updated rating on the dashboard within the trusted-duration refresh window; run the ISO 9241 usability review | WBS 4.2.3, 4.3.4; `System Design Report.md` §3.3 (UI Dashboard, Full System Integration) | Not started | F8 |

## 6. Non-Functional Requirements

- **SW-NF1 Fail-safe display.** When a row carries a fallback/anomaly indication, or when the data feed is missing or stale, the dashboard must resolve toward the static rating and say so — never present a stale or suspect dynamic value as the current limit. Basis: `Project Definition.md` Ethical Considerations ("Data Integrity" — default to static "immediately"). The DS side owns *deciding* fallback; the Software side owns never *hiding* it and never *masking its own feed loss*. Caveat: DS's own C7 falls back to `last_good_rating` (a dynamic value), not the static rating, for gates G1/G2 (sensor/link loss) — see OD-6.
- **SW-NF2 Units and labels.** Every number rendered carries its unit (A, MW, m/s, degC, W/m², %, min/s), taken from `PIPELINE_SCHEMA` (`backend/units_def.py`). Any unit conversion the UI performs must be documented; A→MW conversion is DS's (C6, `amps_to_mw`) and is not reimplemented here without a decision (OD-8). Basis: DS PRD §6 "Unit correctness at every boundary".
- **SW-NF3 Human-centred design (ISO 9241).** Clear, consistent, readable; alerts prioritized so an operator can respond in a time-sensitive situation. Acceptance is the usability review in SW-F12: operators can interpret ratings and alerts without additional guidance (`System Design Report.md` §3.3, UI Dashboard).
- **SW-NF4 No UI-side rating math.** The dashboard displays DS-produced values and DS-produced derived values (`dlr_headroom_pct`, `dlr_uplift_flag`); it does not recompute ampacity, headroom, forecasts, or anomaly decisions. This is what makes "dashboard outputs consistent with pipeline calculations" (`System Design Report.md` §3.3, Full System Integration) testable. Presentation-only arithmetic (formatting, unit labelling, axis scaling) is allowed.
- **SW-NF5 Contract fidelity and tolerance.** Build against the published schema (`pipeline_output_v1.md`) and fixture. Tolerate additive columns (`PIPELINE_SCHEMA` v2/v3 are additive-only by rule, `backend/units_def.py`) and missing/null optional values (e.g. `relative_humidity` is entirely empty in two committed-station outputs — §9) without crashing or fabricating zeros. A breaking change is a new `pipeline_output_v2.md` per that document's own rule.
- **SW-NF6 No secrets in the browser or repo.** DS credentials (`SYNOPTIC_TOKEN`, `NREL_API_KEY`, `NREL_API_EMAIL`) never reach `frontend/`; the BFF should not need them if it only reads DS output. Basis: DS PRD §6 "No secrets committed".
- **SW-NF7 Timestamps are unambiguous.** Every displayed time states its timezone. DS emits UTC (`datetime_utc`) and, in the merged file only, a US/Central `datetime_local`. Which is the default display is undecided (OD-7), but an unlabelled time is never acceptable.
- **SW-NF8 Modularity and fixture-first development.** Each component is independently workable against the fixture without another developer's uncommitted changes (mirrors DS PRD §6 "Modularity"). `ROADMAP.md` "Parallel-safe" fields govern.
- **SW-NF9 Open-source, zero-cost stack.** Bill of Materials (`System Design Report.md` Appendix E) lists "Front-end web development libraries (React, Flask)" at $0 (open-source).

## 7. Open Decisions

None of these is decided by the source documents. Each is listed with the component it blocks and what a decision must cover. Do not resolve them by assumption in code.

| ID | Decision | Why it is open (evidence) | Blocks |
|---|---|---|---|
| OD-1 | **Unit of selection.** Is a "location" a city (Austin, Corpus Christi, Midland, El Paso — the four in the I/O table), a corridor (`config.CORRIDOR_ENDPOINTS`: two corridors), or a weather station (`stid`, the only identifier in the v1 export)? | `Project Definition.md` says "preset locations ... in our database" and tabulates four cities; the v1 export and fixture are keyed by `stid` only, with no city/corridor column; `docs/data-science/decisions/geographic_scope.md` leaves city→corridor mapping open. No "database" exists in the repo — only flat files. | F1 route shape, F2 selector |
| OD-2 | **Data-feed mechanism.** Thin file-serving layer, live-polling service, or one that also proxies PSS/E? Push (WebSocket/SSE) or poll? Refresh cadence? | `api/README.md`: "Not yet decided". `System Design Report.md` §3.3 says the dashboard must update "in real time" and "within the trusted duration refresh window", but nothing produces live data today — the pipeline writes batch CSVs. | F1, F5, F8 |
| OD-3 | **Meaning and units of "trusted duration".** | `Project Definition.md` I/O table gives 10 or 20 **seconds** ("window ... before the system requires a data refresh"), yet DS data cadence is 5-minute (schema) to hourly (committed outputs) and DS's forecast horizon is 60 minutes (`C9`, `config.FORECAST_HORIZON_MINUTES`). `C9` Open Questions: "What forecast horizon matters for the dashboard's 'trusted duration' feature — minutes, hours? Still genuinely open; no dashboard requirement has been specified yet." No column named for it exists. | F5 (SW-F5), F8 |
| OD-4 | **Source and owner of line sag.** | The mock-up shows "current sag of the line"; the ethical section cites sag as the safety risk. No sag computation exists anywhere in `backend/` (searched), no WBS task (Appendix B 4.1.x) names a sag display, and IEEE 738 ampacity does not output sag. | F3 (SW-F4) |
| OD-5 | **What "operating limit" the headline number is when DLR < SLR.** | Committed outputs show `dlr_amps` below the static rating for part of the window in three of six stations (negative `dlr_headroom_pct`, `dlr_uplift_flag = False`; §9). The source docs describe only the DLR>SLR benefit case and the fallback-to-static case. Whether the dashboard headlines the lower DLR, the static value, or `min(DLR, SLR)` is not stated. Showing the lower value is the conservative direction, but this is a team/DS decision. | F3, F4 |
| OD-6 | **How a fallback is presented given DS's two fallback targets.** | DS C7: gates G1/G2 fall back to `last_good_rating` (a previously trusted *dynamic* value); G3/G4 fall back to `static_rating`. `Project Definition.md` says "default back to the conservative static rating". DS C7 lists this as unconfirmed. The UI must say which basis is in effect, but cannot until DS confirms and exports it. | F6 |
| OD-7 | **Default display timezone and whether to expose both UTC and local.** | DS exports UTC; merged file adds `datetime_local` (US/Central). Operators/graders' expectation unspecified. | F2, F4 |
| OD-8 | **Does the dashboard show MW capacity and ERCOT load, or amperes only?** | I/O table and mock-up speak only in amperes. MW columns (`dlr_capacity_mw`, `static_capacity_mw`, `ercot_west_load_mw`) exist only after DS's C6 merge, hourly, for one station (`merged_ercot_dlr_AN489.csv`). C6 states the "stress %" metric must not be read as a utilization number. DS C3 Open Question already asks whether MW should be exported directly. | F4 |
| OD-9 | **PSS/E → dashboard interface** (format, cadence, fields, granularity). | `docs/data-science/decisions/pss_e_handoff.md`: the DS→PSS/E handoff is "informal", never confirmed; there is no document describing PSS/E → dashboard at all. WBS 4.2.2 exists, with Power Systems and others as support. | F7 |
| OD-10 | **Which standards constrain the UI beyond ISO 9241**, and how. | `Project Definition.md` says the UI should align with IEEE 2030.2 (energy storage interoperability), IEEE 1815 (DNP3, "between the dashboard and telemetry devices"), and IEEE C37.118 (synchrophasors). `System Design Report.md` Appendix A keeps 1815 and C37.118 but drops 2030.2, and no telemetry device or synchrophasor feed exists in the repo. | F2, F8 |
| OD-11 | **Front-end stack beyond "React" and "Flask".** Language (JS/TS), build tool, charting library, state/data-fetching approach, test frameworks, styling approach; Flask dependency management (Flask is not in `requirements.txt`; no `package.json` exists). | `System Design Report.md` Appendix E names only React and Flask. | F1, F2 (decide first) |
| OD-12 | **Whether the dashboard also consumes DS's shadow-forecast stream.** | Not in this PRD's grounding set, but `data/shadow/predictions/*.jsonl` is a separate DS output (fields include `corridor`, `method`, `ampacity_amps`, `fallback_used`, `fallback_reason`, `valid_time`, `horizon_minutes`) with its own status owned by DS. Whether it is a dashboard input or a DS-internal experiment is a DS call. | F5, F6 |
| OD-13 | **Authentication / access control for an operator tool.** | Nothing in the source documents mentions operator login or roles. Likely out of scope for a course prototype, but unstated. | F1 |

## 8. Data Contract Requests to Data Science

The Software subsystem's most important external dependency, following the pattern of `docs/data-science/ROADMAP.md` Finding 2. The v1 export (`outputs/station_data/*.csv`, documented in `docs/data-science/schema/pipeline_output_v1.md`) has 11 columns: `stid, datetime_utc, air_temp, wind_speed, wind_direction, wind_perp_ms, solar_radiation, relative_humidity, dlr_amps, dlr_headroom_pct, dlr_uplift_flag`. Against what SW-F1–F12 need:

| Gap | Need | Current state | Needed by |
|---|---|---|---|
| G1 | A location/corridor identifier (OD-1) | Only `stid`; no `stid`→city/corridor mapping in the export | F1, F2 |
| G2 | Per-row fallback/anomaly status: whether fallback is active, which gate/reason, which rating basis (OD-6), and any alert text | Exists only in memory as `DLRSafetyMonitor.run_check`'s `{status, rating, fallback, alerts}` and `AnomalyDetector.check`'s `(is_anomalous, reason)`; `anomaly_score` is in `PIPELINE_SCHEMA` v2 but **not** in the v1 export | F6, F3 |
| G3 | Forecast columns in the export | `forecast_horizon_min`, `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps` are in `PIPELINE_SCHEMA` v2, but not in the v1 export. Per `C9`, cold start emits no forecast columns at all | F5 |
| G4 | A trusted-duration value or a definition from which the UI can show one (OD-3) | None | F5 |
| G5 | The static rating in effect, as a column | Not exported; only derivable as `dlr_amps / (1 + dlr_headroom_pct/100)` (equals 900 A in the committed outputs and fixture). Deriving it in the UI would be rating math (SW-NF4) | F3, F4 |
| G6 | One timestamp format | Fixture: `2026-07-15T18:00:00Z`. Committed outputs: `2025-07-01 00:00:00+00:00`. Both are UTC; formats differ | F1 |
| G7 | Provenance / data-quality flags the UI can surface | `wind_source`, `temp_source`, `humidity_source`, `solar_source` exist in `PIPELINE_SCHEMA` v3; not in the v1 export. Also see §9 on constant/missing columns | F6 (optional) |
| G8 | Sag (OD-4) | Not produced | F3 |

Until these land, F5 and F6 can be built only against a **mock** extension of the fixture whose column names DS has agreed to (see `ROADMAP.md` Finding 2). Do not invent column names in production code.

## 9. Observed Characteristics of Existing DS Output

Facts read directly from `data/fixtures/sample_pipeline_output.csv` and the local, untracked `outputs/` files (generated 2025-07-01 to 2025-07-04). The UI must be built to cope with all of these; none is decided to be a bug (that is DS's call), but several look surprising and should be raised to DS.

- **Fixture:** one station (`AP140`), 10 rows, 5-minute cadence, 2026-07-15T18:00:00Z–18:45:00Z; `dlr_amps` 1180–1325 A; `dlr_headroom_pct` 31.1–47.2 (consistent with the 30–50% claim); every row `dlr_uplift_flag = True`. No nulls.
- **Committed outputs are not guaranteed to exist** on a fresh clone (`/outputs` is gitignored); only the fixture is tracked.
- **Cadence varies by station file:** `AN489` 96 rows and `AN490` 92 rows over four days (hourly); `F2876`, `F9683`, `F9684` 384 rows each (about 15-minute); `KSWW` 288 rows (about 20-minute). The schema document states "5-minute intervals". Row gaps exist (e.g. `AN490` has 92 of 96 hourly slots).
- **`solar_radiation` is exactly `1000.0` on every row** in five of the six station files (`F9683` varies, 0–1195). It is within the schema range `[0, 1400]` so it validates; whether it is a placeholder/fill is not explained in any source document.
- **`relative_humidity` is entirely empty** in `AN489` and `AN490`.
- **Headroom is far above the stated 30–50%:** `dlr_headroom_pct` peaks at 209–274% across the six committed stations (against the default 900 A static rating; `dlr_amps` up to 3363 A). The `Project Definition.md` I/O table bounds the new limit at 1.5x the static maximum (e.g. Austin 800–4500 A vs 800–3000 A static).
- **DLR below static occurs:** `F2876`, `F9684`, `KSWW` have negative headroom (down to −32.8%) and `dlr_uplift_flag = False` for 41, 65 and 41 rows respectively.
- **Static line in plots is 900 A** (`DEFAULT_STATIC_RATING`), not the per-city values in `backend/config.py::STATIC_RATINGS` (e.g. Austin 1900 A) — so the existing PNGs and committed CSVs do not use the four-city static ratings.
- **MW file (`merged_ercot_dlr_AN489.csv`)** is hourly, 96 rows, with `datetime_local` (US/Central); `static_capacity_mw` is a constant 510.9 MW (900 A at 345 kV, power factor 0.95). The "stress %" panel in `holistic_view_AN489.png` reaches ~1750% (load ÷ single-line capacity) and is, per DS C6, illustrative only.
- **Existing visualizations the dashboard can take cues from (not copy as spec):** `outputs/station_plots/*.png` — DLR vs. static with shaded headroom, total vs. perpendicular wind, ambient temperature, headroom histogram; `holistic_view_*.png` — MW capacity vs. load.

## 10. Documentation Discrepancies

Places where the course deliverables disagree with each other or with the repo, as they bear on the dashboard. Flagged so the team can correct the record rather than let it compound.

| Course Deliverable Claim | Location | Actual Repo State |
|---|---|---|
| UI should align with IEEE 2030.2, 1815, and C37.118 in addition to ISO 9241 | `Project Definition.md` UI Specifications | `System Design Report.md` Appendix A drops 2030.2; no telemetry device or synchrophasor input exists. See OD-10. |
| Dashboard "will also show the current sag of the line" | `Project Definition.md` UI Specifications | No sag computation in `backend/`; no WBS 4.1.x task for it. See OD-4. |
| Users select from "preset ... locations that are in our database" | `Project Definition.md` UI Specifications | No database; DS output is flat files keyed by station. See OD-1. |
| Trusted duration is 10 s (Austin, Corpus Christi, Midland) or 20 s (El Paso) | `Project Definition.md` I/O table | DS cadence is minutes-to-hours and forecast horizon is 60 minutes; no trusted-duration producer. See OD-3. |
| Dashboard "update[s] correctly in real time"; integration "within the trusted duration refresh window" | `System Design Report.md` §3.3 | The pipeline writes batch CSV files; no live feed or refresh mechanism exists. See OD-2. |
| Dynamic ratings unlock "30–50% more power" | `Project Definition.md`, `System Design Report.md` §2.0 | Committed station outputs peak at 209–274% headroom against the 900 A default (§9). A DS validation matter; the dashboard must display what DS produces without clamping. |
| Software sub-team owns WBS 4.3.1–4.3.3 (known-value, synthetic stress, dimensional-analysis testing) | `System Design Report.md` Appendix B/C | Those tests verify DS pipeline behavior and already live in DS test suites (`backend/tests/`). See §1 note. |

## 11. References

- `ROADMAP.md` (this directory) — phase order, dependency graph, blocker analysis
- `specs/` (this directory) — per-component technical specs; `specs/README.md` is the index and template
- `README.md` (this directory) — documentation index and convention
- `docs/Project Definition.md` — UI Specifications, I/O specification table, Ethical Considerations (fail-safe commitment), ISO 9241 (Appendix A)
- `docs/System Design Report.md` — §3.1 (layers), §3.2 (Data Integrity), §3.3 (Test Plan: UI Dashboard, Full System Integration), Appendix B (WBS 4.0), Appendix C (LRC), Appendix E (BOM)
- `docs/data-science/specs/C3-export-visualization.md` and `docs/data-science/schema/pipeline_output_v1.md` — the DS→dashboard contract
- `docs/data-science/specs/C7-safety-monitor.md`, `C9-ampacity-forecasting.md`, `C10-anomaly-detection.md` — producers of the status, forecast, and anomaly data F5/F6 display
- `docs/data-science/decisions/pss_e_handoff.md`, `geographic_scope.md` — related open DS-side decisions
- `data/fixtures/sample_pipeline_output.csv` — the only guaranteed dev data
