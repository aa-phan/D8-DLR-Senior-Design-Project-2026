## Conflict Detection Report

Ingest mode: merge. 20 classified documents synthesized (12 SPEC, 1 PRD, 7 DOC, 0 ADR). Cross-ref graph re-verified acyclic (Tarjan's SCC, no SCC > 1) after orchestrator's manual correction removing a false-positive strongly-connected component (companion-doc back-references and one self-loop). No existing `.planning/PROJECT.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md`, or phase `CONTEXT.md` files were found, so merge-mode existing-locked-decision checks had nothing to compare against.

### BLOCKERS (0)

None. No ADR-classified documents exist in this ingest set, so no LOCKED-vs-LOCKED contradiction is possible. No existing locked decisions were found in `.planning/` to contradict. No UNKNOWN/low-confidence classifications exist. No unresolved cross-ref cycles remain after the orchestrator's correction.

### WARNINGS (1)

[WARNING] Competing city/corridor scope across same-precedence-tier SPECs
  Found: docs/Project Definition.md's Input/Output Specification table scopes the system to four cities — Austin, Corpus Christi, Midland, El Paso — each with its own documented input-range and static-rating bounds.
  Found: docs/data-science/specs/C1-configuration.md's `STATIC_RATINGS` covers a different five cities — Houston, Austin, Dallas, Fort Worth, San Antonio — overlapping the Project Definition list only on Austin.
  Found: docs/data-science/specs/C8-corridor-discretization.md references `backend/station_explorer.py::CORRIDORS` — five West-Texas corridors (Panhandle Export, Permian Basin 345kV, Sweetwater Wind Hub, Big Spring Corridor, West TX to Hill Country) — none of which are Austin, Corpus Christi, Midland, or El Paso.
  Impact: All three are SPEC-tier documents at the same default precedence (no per-doc `precedence` override set on any of them), so this synthesizer cannot auto-pick a winning location scope. Downstream planning (requirements scoping, roadmap city coverage, weather-provider selection in the still-open PRD §7.1 decision) needs one authoritative scope. This exact mismatch is already self-flagged inside docs/data-science/PRD.md §10 ("Documentation Discrepancies") as a repo-vs-course-deliverable gap, but the underlying three-way SPEC contradiction has not been resolved by any document in this set.
  → Pick one authoritative location/corridor scope (or explicitly define a phased scope, e.g. "West Texas corridors now, four-city buildout later") via --manifest precedence override or a new ADR, before routing into ROADMAP.md.

### INFO (5)

[INFO] Auto-resolved: SPEC/PRD > DOC on weather data provider currently in use
  Note: docs/System Design Report.md §3.1 states the team "selected NOAA and NSRDB because of their superior data accessibility," and Appendix B (WBS) item 2.1.1 says "Integrate NOAA real-time weather data streams." docs/Prior Art Report.md's Impact section states the system "ingests external weather data from NOAA and sensors." docs/data-science/specs/C4-weather-ingestion.md (SPEC) and docs/data-science/PRD.md (PRD) both state, and PRD.md §10 self-documents as a discrepancy, that all working ingestion code uses the Synoptic Data API against the West Texas Mesonet network — no NOAA or NSRDB integration exists anywhere in the repo, and the provider choice is an explicitly open decision (PRD §7.1) that must not block Phase 2/3 work. Per default precedence (SPEC/PRD > DOC), C4/PRD's "what is actually implemented" claim wins in synthesized intel; the SDR/Prior-Art-Report claims of an already-made NOAA+NSRDB selection are not carried forward as current state.

[INFO] Auto-resolved: SPEC/PRD > DOC on solar irradiance source
  Note: docs/System Design Report.md §3.2 ("Weather Data and Transmission Corridor Mapping") states solar irradiance is sourced from NSRDB. docs/data-science/specs/C4-weather-ingestion.md (SPEC) states solar irradiance comes from Synoptic's `solar_radiation` field, which is commonly missing on airport/METAR-style stations (confirmed for `KAUS`), falling back to a hardcoded 1000 W/m² constant. PRD.md §10 self-documents this as a discrepancy. SPEC wins per default precedence; synthesized constraints.md/context.md reflect Synoptic as the current solar source.

[INFO] Auto-resolved: SPEC > DOC on corridor spatial discretization existence
  Note: docs/System Design Report.md §3.2 states the team "developed a spatial pipeline that defines transmission line corridors...discretizes the corridor into multiple geographic points" with per-point IEEE 738 ampacity and minimum-ampacity bottleneck logic. docs/data-science/specs/C8-corridor-discretization.md (SPEC) states Status: Not started, and explicitly calls the SDR's claim inaccurate — the only existing artifact (`station_explorer.py::CORRIDORS`) ranks station proximity to five fixed points, with no notion of a line, route, or per-point ampacity reduction. SPEC wins per default precedence; C8 is synthesized as not-started.

[INFO] Auto-resolved: SPEC > DOC on learned anomaly-detection model existence
  Note: docs/System Design Report.md §3.2 ("Data Integrity") states a machine-learning anomaly-detection model "is currently being trained and tuned on historical ambient weather and operating datasets," and Appendix B item 2.3.1 lists "Train Machine Learning model on sensor telemetry data." docs/data-science/specs/C10-anomaly-detection.md (SPEC) states Status: Not started, and explicitly calls the SDR's claim inaccurate — no model, training script, or training dataset exists anywhere in the repo; `DLRSafetyMonitor.py` is entirely deterministic threshold/range gating. SPEC wins per default precedence; C10 is synthesized as not-started.

[INFO] Auto-resolved: PRD > DOC on N-1 contingency screening ownership
  Note: docs/Prior Art Report.md's Impact section states prior-art research "led us to integrate these checks [N-1 contingency] directly into our Python-based data science pipeline." docs/data-science/PRD.md (PRD) §1 explicitly scopes N-1 contingency screening, reactive power, and voltage stability analysis as "Explicitly out of scope (owned by other sub-teams, referenced only as consumers)" for the DS subsystem. PRD wins per default precedence (PRD > DOC); synthesized requirements.md does not include N-1 contingency logic in the DS subsystem's scope.
