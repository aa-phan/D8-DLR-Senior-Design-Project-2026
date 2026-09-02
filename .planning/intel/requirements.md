# Requirements (from PRD-classified documents)

Source PRD: `docs/data-science/PRD.md` ("Data Science Subsystem — Product Requirements"). This is the only PRD-classified document in this ingest batch — no competing-variant PRDs exist for these requirements.

Scope note from source: DS subsystem turns raw weather/grid telemetry into a trustworthy Dynamic Line Rating (DLR), with guaranteed fail-safe fallback to Static Line Rating (SLR). Explicitly out of scope (owned by other sub-teams, referenced only as consumers): PSS/E grid simulation and load-flow integration, N-1 contingency screening / reactive power / voltage stability analysis, UI dashboard implementation.

Acceptance-criteria note: the PRD itself states "[each requirement] maps to the component that owns it — see that component's spec for interface detail." The PRD does not restate acceptance criteria inline; full testable acceptance criteria live in the owning component's SPEC entry in `constraints.md`. Where noted below, `acceptance` points to that owning entry rather than fabricating criteria not present in the PRD.

---

## REQ-weather-station-discovery
- source: docs/data-science/PRD.md (§5, DS-F1)
- description: Discover weather stations near defined transmission corridors.
- acceptance: Status — Implemented. Full acceptance criteria owned by C4 (see constraints.md).
- scope: weather ingestion, station discovery

## REQ-weather-observation-fetch
- source: docs/data-science/PRD.md (§5, DS-F2)
- description: Fetch time-series weather observations (temp, wind speed/direction, solar, humidity) for target stations.
- acceptance: Status — Implemented, now behind a provider-agnostic adapter (`backend/weather_provider.py`). Full acceptance criteria owned by C4.
- scope: weather ingestion, provider adapter

## REQ-perpendicular-wind-component
- source: docs/data-science/PRD.md (§5, DS-F3)
- description: Compute wind component perpendicular to the line for forced-convection cooling.
- acceptance: Status — Implemented, extracted to `backend/thermal_model.py`. Full acceptance criteria owned by C5.
- scope: thermal model, IEEE 738

## REQ-ieee738-ampacity-computation
- source: docs/data-science/PRD.md (§5, DS-F4; also §9)
- description: Compute steady-state IEEE 738 ampacity from weather + conductor properties.
- acceptance: Status — Implemented and validated against a published reference (see §9: a real bug — erroneous π factor, ~69% overestimate — was found and fixed during that validation). Full acceptance criteria owned by C5.
- scope: thermal model, IEEE 738, ampacity

## REQ-dlr-vs-static-comparison
- source: docs/data-science/PRD.md (§5, DS-F5)
- description: Compare DLR against a static rating and flag uplift/headroom.
- acceptance: Status — Implemented, per-location lookup (`backend/config.py::STATIC_RATINGS`, 5 TX cities) with a uniform fallback; not yet wired to select a location per run. Owning components C1, C5.
- scope: static rating comparison, headroom, uplift flag

## REQ-pipeline-unit-validation
- source: docs/data-science/PRD.md (§5, DS-F6)
- description: Validate units and physical ranges across pipeline data.
- acceptance: Status — Implemented and enforced: `run_pipeline` validates every output row against `PIPELINE_SCHEMA` before returning (non-strict, logged). Full acceptance criteria owned by C2.
- scope: unit validation, PIPELINE_SCHEMA

## REQ-anomaly-fallback-detection
- source: docs/data-science/PRD.md (§5, DS-F7)
- description: Detect unreliable/anomalous inputs and fall back to SLR.
- acceptance: Status — Partial. Deterministic threshold gates only; the gated ampacity value disagrees with the real thermal model (C5 not yet wired into C7). Full acceptance criteria owned by C7.
- scope: safety monitor, fail-safe fallback

## REQ-ercot-grid-load-merge
- source: docs/data-science/PRD.md (§5, DS-F8)
- description: Merge DLR output with real ERCOT grid load for a holistic capacity-vs-demand view.
- acceptance: Status — Implemented. Full acceptance criteria owned by C6.
- scope: ERCOT integration, grid load

## REQ-csv-export-and-plots
- source: docs/data-science/PRD.md (§5, DS-F9)
- description: Export results to CSV and produce summary plots.
- acceptance: Status — Implemented. Full acceptance criteria owned by C3.
- scope: export, visualization

## REQ-corridor-spatial-discretization
- source: docs/data-science/PRD.md (§5, DS-F10; also §8)
- description: Discretize a transmission corridor into multiple geographic points and take the minimum ampacity as the corridor-level rating.
- acceptance: Status — Not started. Full acceptance criteria owned by C8.
- scope: corridor discretization, spatial pipeline

## REQ-ampacity-forecasting
- source: docs/data-science/PRD.md (§5, DS-F11; also §8)
- description: Forecast ampacity ahead of real time (regression/ML).
- acceptance: Status — Not started. Full acceptance criteria owned by C9.
- scope: ampacity forecasting

## REQ-learned-anomaly-detection
- source: docs/data-science/PRD.md (§5, DS-F12; also §8)
- description: Anomaly detection via a trained model on historical baselines.
- acceptance: Status — Not started. Full acceptance criteria owned by C10.
- scope: anomaly detection, learned model

---

## Non-Functional Requirements (PRD §6)

## REQ-nfr-fail-safe-default
- source: docs/data-science/PRD.md (§6)
- description: Any missing sensor data, broken communication link, out-of-range reading, implausible computed rating, or large rating swing must resolve toward the static rating, never toward an optimistic guess. Core ethical commitment made in `Project Definition.md`; must hold as anomaly-detection logic (C7, C10) gets more sophisticated.
- acceptance: absent (non-functional requirement stated as a standing commitment, not a single testable criterion)
- scope: fail-safe behavior, safety monitor

## REQ-nfr-unit-correctness
- source: docs/data-science/PRD.md (§6)
- description: Any value crossing a module boundary (API response → pipeline row, pipeline row → safety monitor, ampacity → MW) must be validated against a known unit/dimension (C2). A kW-for-MW-style mistake should be caught, not silently propagated.
- acceptance: absent
- scope: unit correctness, module boundaries

## REQ-nfr-reproducibility
- source: docs/data-science/PRD.md (§6)
- description: Given the same station IDs, time window, and conductor config, the pipeline should produce the same output. No wall-clock-dependent or non-deterministic logic in the ampacity math.
- acceptance: absent
- scope: reproducibility

## REQ-nfr-no-secrets-committed
- source: docs/data-science/PRD.md (§6)
- description: API tokens (`SYNOPTIC_TOKEN`) live in `.env` / environment variables only. `.env` is gitignored.
- acceptance: absent
- scope: secrets management

## REQ-nfr-modularity
- source: docs/data-science/PRD.md (§6)
- description: Components should remain independently workable — no component's implementation should require another dev's in-progress, uncommitted changes to compile or run. See `ROADMAP.md` "Parallel-safe" fields per component.
- acceptance: absent
- scope: modularity, parallel development
