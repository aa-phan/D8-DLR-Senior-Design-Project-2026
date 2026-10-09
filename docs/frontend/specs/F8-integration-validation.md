<!-- generated-by: gsd-doc-writer -->
# F8 — Integration, E2E & Usability Validation

**Phase:** 4 (Integration & Validation) · **Effort:** M · **Status:** Not started.

**Responsibility:** Prove the dashboard works as the course test plan says it must: end-to-end integration (WBS 4.2.3), the UI-dashboard test and the ISO 9241 usability review (WBS 4.3.4), and consistency of every displayed value with pipeline output (SW-F12, SW-NF3, SW-NF4). This is the final component; it creates no features, it verifies the others.

## Current Implementation

None. Existing DS test suites are under `backend/tests/` (e.g. `units_def_test.py`, `SafetyMonitor_TestSuite.py`, `ampacity_forecast_test.py`, `anomaly_detector_test.py`, `ercot_dlr_merger_test.py`) and cover the DS pipeline only. No frontend or API tests exist. `System Design Report.md` Appendix B 4.3.1–4.3.3 (known-value, synthetic stress, dimensional-analysis validation) are DS-side verification and are treated as DS-owned here (PRD §1 note).

## Interface & Data Contract

Test targets, from `System Design Report.md` §3.3:

**UI Dashboard test.** "Feeding it live pipeline outputs and confirming that DLR values, anomaly flags, and fallback status indicators update correctly in real time." Pass: "operators can correctly interpret dynamic ratings and system alerts without additional guidance, and all pipeline outputs are accurately reflected in real time."

**Usability review (ISO 9241).** "Clarity of alerts and operator response time to flagged conditions." Reviewed by the whole team (LRC 4.3.4: one primary, five review).

**Full System Integration.** "A change in weather input propagates correctly through IEEE 738 calculation, updates the corridor ampacity, triggers appropriate contingency checks, and displays the updated rating on the dashboard within the trusted duration refresh window." Pass: "data flows end-to-end with no unit errors, no undetected anomalies, and dashboard outputs consistent with pipeline calculations."

What this component adds:

- **API/UI contract tests** against the fixture, plus the mock extension for forecast and fallback fields (F5/F6) so they are covered before DS exports real data.
- **A pipeline-to-screen consistency check:** for a given pipeline run, every value the UI renders (limits, headroom, weather, forecast, status) equals the CSV value, with unit and timezone labels correct.
- **A scripted fault-injection set** driven through the feed (stale file, missing file, null columns, fallback rows, out-of-range rows) confirming SW-NF1: nothing leaves a normal-looking dynamic limit when data is untrustworthy.
- **A usability-review protocol:** tasks an operator-role tester performs without help (read the current limit; tell whether it can be trusted; identify an active fallback and its reason; read the forecast), with success/time recorded.

## Blocked by

**F1, F2, F3, F4, F5, F6** (hard — every view must exist and be fed). **F7** (soft — only the PSS/E leg). Plus the external DS contract extension for the non-mock paths (PRD §8) and OD-2/OD-3 for what "real time" and "within the trusted duration refresh window" mean.

## Blocks

Nothing — final component.

## Parallel-safe with

Test-harness and fixture-extension scaffolding can start alongside Phase 2/3 work; execution of the full plan cannot start until its blockers land. The usability-review protocol can be written any time after F2.

## Known Issues

- **"Real time" is untestable until a live feed exists.** The pipeline produces batch CSVs (PRD OD-2); the integration test's "within the trusted duration refresh window" criterion needs OD-2 and OD-3 resolved or reinterpreted (e.g. refresh-on-new-file).
- **The test plan assumes the integrated pipeline** (corridor discretization → anomaly check → forecast) exists; DS Track 1 (`docs/data-science/DEVELOPMENT-TRACKS.md`) is the work that wires those into `run_pipeline`, and it is not yet executed at time of writing, so end-to-end runs through the real pipeline may be limited.
- **Operator availability:** the review criterion is about operators; no source document names who the test operators are (real operators vs. proxies is undecided).
- **Standards criteria are not testable as written:** IEEE 2030.2 / 1815 / C37.118 alignment (PRD OD-10) has no pass/fail definition.
- **No frontend/API test framework chosen** (OD-11).

## Acceptance Criteria

- Contract tests pass against the committed fixture from a fresh clone (no network, no tokens).
- For a pipeline run, a script compares each displayed value to its source CSV cell and reports zero mismatches in value, unit label and timezone label (consistency criterion, `System Design Report.md` §3.3).
- Every fault in the injection set results in the documented fail-safe display (static-rating/unavailable/fallback state per F1/F6) and none shows a stale dynamic value as current.
- A weather-input change fed through the pipeline appears on the dashboard within the agreed refresh window (once OD-2/OD-3 define it) — recorded with timestamps.
- The ISO 9241 usability review is run to its protocol and recorded; criterion: tested operators correctly interpret ratings and alerts without additional guidance (`System Design Report.md` §3.3). Findings are filed against the relevant component.
- The PSS/E leg is either executed with F7's contract, or explicitly recorded as not applicable.

## Open Questions

- OD-2, OD-3, OD-9, OD-10 (see PRD §7).
- What is the numeric bar for "operator response time to flagged conditions"? Not stated.
- Who plays the operator in the review, and how many testers? Not stated; LRC assigns the whole team as Review.
