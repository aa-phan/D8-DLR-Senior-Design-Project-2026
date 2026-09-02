# Data Science Subsystem — Product Requirements

**Status:** Internal engineering reference. Not a course deliverable — does not replace or get submitted alongside `Project Definition.md`, `Prior Art Report.md`, or `System Design Report.md`. Written to describe the Data Science (DS) subsystem of the DLR project as it actually exists in this repository, and to define the requirements the phased implementation in `ROADMAP.md` builds toward.

**Last reviewed against repo state:** 2026-08-24

---

## 1. Purpose & Scope

The DS subsystem is responsible for turning raw weather and grid telemetry into a trustworthy Dynamic Line Rating (DLR), and for guaranteeing that when the inputs can't be trusted, the system falls back to the conservative Static Line Rating (SLR). This corresponds to WBS §2.0 (Data Science Sub-Team) in the System Design Report.

**In scope:**
- Weather data ingestion for target stations/corridors
- IEEE 738 thermal ampacity modeling
- Dimensional analysis / unit validation across the pipeline
- Anomaly detection and fail-safe fallback to SLR
- Merging DLR output with ERCOT grid load for economic/reliability analysis
- Export and visualization of pipeline results

**Explicitly out of scope** (owned by other sub-teams, referenced only as consumers):
- PSS/E grid simulation and load-flow integration
- N-1 contingency screening, reactive power / voltage stability analysis
- UI dashboard implementation

## 2. Problem Statement

Static Line Ratings are set from worst-case weather assumptions (high ambient temp, full solar radiation, low wind) that hold less than 5% of the time. For the remaining ~95%, transmission lines can typically carry 30–50% more current without exceeding thermal limits, but that capacity is invisible to grid operators using SLR. The DS subsystem's job is to make that capacity visible — computing a live, physically-grounded ampacity from IEEE Standard 738 — while never letting an unreliable input silently overstate what the line can actually carry.

## 3. Users & Consumers

| Consumer | Needs from DS subsystem |
|---|---|
| Software sub-team (UI dashboard) | A per-location DLR value, a trusted-duration window, and a fallback/alert status, refreshed on a predictable cadence. Needs the output **schema** early — see `ROADMAP.md` Finding 2. |
| Power Systems sub-team (PSS/E) | Ampacity values (and their MW equivalent) to inject into load-flow and N-1 contingency screening |
| Research paper (economic/reliability analysis) | Historical DLR vs. SLR series merged with ERCOT load, to quantify curtailment recovered and congestion avoided |

## 4. How This PRD Relates to the Roadmap

This document defines **what** the subsystem must do (requirements) and **why** (problem/users). `ROADMAP.md` defines **in what order** to build it and **what blocks what**. `specs/C1`–`C10` define **how** each piece works. Read in that order: PRD → ROADMAP → specs.

Work is organized into ten components (`specs/README.md` has the full index), grouped into four phases ordered least→most complex:

| Phase | Components | Theme |
|---|---|---|
| 1 — Foundation | C1 Configuration, C2 Data Contract, C3 Export & Visualization | Make the implicit file-based contract explicit; remove hardcoded values |
| 2 — Core Consolidation | C4 Weather Ingestion, C5 Thermal Model, C6 Grid Load Integration | Package the existing working logic into importable, provider-agnostic modules |
| 3 — Safety & Spatial | C7 Safety Monitor, C8 Corridor Discretization | Unify the safety monitor with the real thermal model; build the not-yet-started spatial pipeline |
| 4 — Predictive | C9 Ampacity Forecasting, C10 Learned Anomaly Detection | Highest complexity, most dependencies — deliberately last |

Full dependency graph, phase rationale, and blocker analysis live in `ROADMAP.md`.

## 5. Functional Requirements

Status reflects what's actually implemented in this repo, not what's planned. Each maps to the component that owns it — see that component's spec for interface detail.

| ID | Requirement | Status | Owning Component |
|---|---|---|---|
| DS-F1 | Discover weather stations near defined transmission corridors | Implemented | C4 |
| DS-F2 | Fetch time-series weather observations (temp, wind speed/direction, solar, humidity) for target stations | Implemented — now behind a provider-agnostic adapter (`backend/weather_provider.py`) | C4 |
| DS-F3 | Compute wind component perpendicular to the line for forced-convection cooling | Implemented — extracted to `backend/thermal_model.py` | C5 |
| DS-F4 | Compute steady-state IEEE 738 ampacity from weather + conductor properties | Implemented and now validated against a published reference — see §9 below for a real bug found and fixed during that validation | C5 |
| DS-F5 | Compare DLR against a static rating and flag uplift/headroom | Implemented — per-location lookup (`backend/config.py::STATIC_RATINGS`, 5 TX cities) with a uniform fallback; not yet wired to select a location per run | C1, C5 |
| DS-F6 | Validate units and physical ranges across pipeline data | Implemented and enforced — `run_pipeline` validates every output row against `PIPELINE_SCHEMA` before returning (non-strict, logged) | C2 |
| DS-F7 | Detect unreliable/anomalous inputs and fall back to SLR | Partial — deterministic threshold gates only, disagrees with the real thermal model | C7 |
| DS-F8 | Merge DLR output with real ERCOT grid load for a holistic capacity-vs-demand view | Implemented | C6 |
| DS-F9 | Export results to CSV and produce summary plots | Implemented | C3 |
| DS-F10 | Discretize a transmission corridor into multiple geographic points and take the minimum ampacity as the corridor-level rating | Not started | C8 |
| DS-F11 | Forecast ampacity ahead of real time (regression/ML) | Not started | C9 |
| DS-F12 | Anomaly detection via a trained model on historical baselines | Not started | C10 |

## 6. Non-Functional Requirements

- **Fail-safe by default.** Any missing sensor data, broken communication link, out-of-range reading, implausible computed rating, or large rating swing must resolve toward the static rating, never toward an optimistic guess. This is the core ethical commitment made in the Project Definition and must hold even as the anomaly-detection logic gets more sophisticated (C7, C10).
- **Unit correctness at every boundary.** Any value crossing a module boundary (API response → pipeline row, pipeline row → safety monitor, ampacity → MW) must be validated against a known unit/dimension (C2). A kW-for-MW-style mistake should be caught, not silently propagated.
- **Reproducibility.** Given the same station IDs, time window, and conductor config, the pipeline should produce the same output. No wall-clock-dependent or non-deterministic logic in the ampacity math.
- **No secrets committed.** API tokens (`SYNOPTIC_TOKEN`) live in `.env` / environment variables only. `.env` is gitignored.
- **Modularity.** Components should remain independently workable — no component's implementation should require another dev's in-progress, uncommitted changes to compile or run. See `ROADMAP.md` "Parallel-safe" fields per component.

## 7. Open Decisions

### 7.1 Weather data provider — unresolved

This is the most consequential open item and is deliberately **not** decided here.

- The System Design Report (§3.1) states the team evaluated NOAA + NSRDB against Synoptic and selected NOAA + NSRDB "because of their superior data accessibility and the lack of restrictive privacy limitations."
- In practice, every working ingestion path in this repo uses the Synoptic Data API against the West Texas Mesonet (WTM) network.
- During prototyping, the team found it difficult to identify a source with consistent, station-dense coverage. Synoptic was what got the pipeline working end-to-end, but the free research tier has real access limits (rate limits, station/network restrictions) that constrain how far this can scale.
- NOAA is a plausible path to remove that constraint but has not been validated against this pipeline — no code has been written against a NOAA API, and NSRDB (solar) integration doesn't exist at all; solar currently comes from Synoptic's `solar_radiation` field.

**Decision needed:** whether to (a) stay on Synoptic and budget for a paid tier, (b) migrate to NOAA (+ a separate solar source, since NOAA doesn't provide GHI), or (c) support both via a provider-agnostic ingestion interface. **This must not block Phase 2/3 work** — C4 defines a provider adapter boundary specifically so C8 (corridor discretization) and later components can build against the existing Synoptic provider (or a mock) without waiting for this decision. See `ROADMAP.md` Finding 3.

## 8. Future Scope (brief)

These appear in the System Design Report's risk-reduction section as work in progress but have no corresponding code today. Full component specs exist for them (`specs/C8`, `specs/C9`, `specs/C10`) since they're part of the phased roadmap, but they are intentionally last — see PRD §4 and `ROADMAP.md` Phase 4.

- **Corridor spatial discretization** (C8) — break a transmission corridor into multiple points along its real geometry, compute ampacity at each, and take the minimum as the corridor-level bottleneck rating.
- **ML-based ampacity forecasting** (C9) — regression or neural-network model to forecast ahead of real time, per IEEE Trans. Smart Grid prior art (`Prior Art Report.md`).
- **Trained anomaly detection** (C10) — replace/augment `DLRSafetyMonitor`'s deterministic gates with a model trained on historical baselines per variable (wind, temp, solar, load).

## 9. Critical Bug Found and Fixed: IEEE 738 Forced-Convection Formula

While validating `ieee738_ampacity` (C5) against the published IEEE Std 738-2023 worked example (§4.6.1, 795 kcmil Drake ACSR — the exact conductor this project defaults to), the forced-convection term was found to have an erroneous extra `* np.pi` factor with no basis in the standard. Neither of the standard's actual equations (Eq. 9: `qc1 = Kangle × [1.01 + 1.35 × NRe^0.52] × kf × (Ts − Ta)`; Eq. 10: `qc2 = Kangle × 0.754 × NRe^0.6 × kf × (Ts − Ta)`) contains a π term.

**Impact of the bug (now fixed):** for the standard's own worked-example inputs (40°C ambient, 0.61 m/s perpendicular wind, 100°C conductor limit), the buggy formula computed **~1728 A** against a published correct answer of **1025 A** — a **~69% overestimate** of line capacity. Since ampacity scales with `sqrt(heat_balance)`, this error did not cancel out anywhere downstream. This is the precise failure mode the project's own ethical-considerations section (`Project Definition.md`) warns against: a DLR system silently overstating how much current a line can safely carry.

**Status:** fixed in `backend/thermal_model.py::ieee738_ampacity` (see C5's spec and the module's own inline comments for the fix). The corrected formula now reproduces the published worked example within 0.95% (see `backend/tests/thermal_model_test.py` for the full derivation of that tolerance — it is not an arbitrarily loose bound). This is why the C5 acceptance criterion "no known-value validation exists" mattered enough to be treated as a real gap rather than a formality — it caught a real, previously-undetected defect in the pipeline's core safety-relevant calculation.

No prior documentation (course deliverables or the DS specs) claimed this bug didn't exist — this wasn't a discrepancy between docs and code, it was undetected because no reference-value validation had been done until this pass. Flagged here at the PRD level, not just in C5's spec, because of its severity.

## 10. Documentation Discrepancies

Places where `System Design Report.md` (or, for the row below, `Project Definition.md`) describes DS subsystem work or scope that does not match what's in this repository. Flagged so the team can correct the record in the next course submission rather than let the gap compound.

| Course Deliverable Claim | Location | Actual Repo State |
|---|---|---|
| Team evaluated and selected NOAA + NSRDB over Synoptic for weather ingestion | SDR §3.1 Design Concept | All working ingestion code uses Synoptic/WTM, now behind a provider-agnostic adapter (`backend/weather_provider.py`). No NOAA or NSRDB integration exists. See Open Decisions §7.1 — this was not actually settled. |
| A spatial pipeline discretizes transmission corridors into multiple points, computes ampacity at each, and takes the corridor-level minimum as the true bottleneck | SDR §3.2 Risk Reduction ("Weather Data and Transmission Corridor Mapping") | No such pipeline exists yet — this is C8, Phase 3, not started. `backend/station_explorer.py::CORRIDORS` is five hardcoded lat/lon pairs used to rank station proximity, not to discretize a line for per-point ampacity. |
| An ML anomaly-detection model is "currently being trained and tuned on historical ambient weather and operating datasets" | SDR §3.2 Risk Reduction ("Data Integrity") | No model, training script, or training dataset exists anywhere in the repo — this is C10, Phase 4, not started. `backend/DLRSafetyMonitor.py` is entirely deterministic threshold/range gating (G1–G5), not a trained model. |
| Solar irradiance sourced from NSRDB | SDR §3.2 Risk Reduction | Solar irradiance comes from Synoptic's `solar_radiation` field. |
| ~~The system targets **four** specific cities — Austin, Corpus Christi, Midland, El Paso — each with its own documented input-range and static-rating bounds~~ **RESOLVED** | Project Definition.md §"Input/Output Specifications" (lines 79-86) | Previously, no code implemented this four-city list, and three different, mutually inconsistent location sets existed instead (`config.py`'s old 5-city table, `station_explorer.py`'s 5 West-Texas corridors, and a dead-code stub in `dlr_pipeline.py`). Resolved per `docs/data-science/decisions/geographic_scope.md`: `config.py::STATIC_RATINGS` is now re-keyed to the real four-city scope (Austin, Corpus Christi, Midland, El Paso), and the dead-code stub was deleted. `station_explorer.py::CORRIDORS`' West-Texas corridors remain unchanged — the open question of how these four cities map to actual corridor endpoints for C8 is tracked separately in `geographic_scope.md`'s Open Questions, not yet resolved. |

## 11. References

- `ROADMAP.md` (this directory) — phase order, dependency graph, blocker analysis
- `specs/` (this directory) — per-component technical specs
- `citations.md` (this directory) — full bibliography for AI-assisted research used in this subsystem (static line ratings, IEEE 738 worked-example validation), with per-source used/excluded status and a verification checklist
- `System Design Report.md` §2.0–3.3 (design concept, risk reduction, test plan)
- `Project Definition.md` (I/O specification table, ethical fail-safe commitment)
- IEEE Std 738-2023 — Calculating the Current-Temperature Relationship of Bare Overhead Conductors (see `citations.md` §2 for the specific clause used in C5's validation)
