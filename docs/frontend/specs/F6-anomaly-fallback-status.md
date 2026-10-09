<!-- generated-by: gsd-doc-writer -->
# F6 — Anomaly & Fallback Status Indicators

**Phase:** 3 (Predictive & Safety Views) · **Effort:** M · **Status:** Not started — externally blocked on DS exporting fallback/anomaly status.

**Responsibility:** Make it unmistakable to the operator when the system has detected unreliable data and is no longer relying on the dynamic rating — status indicators, operator alerts, and the reason (WBS 4.1.5 "Implement anomaly and fallback status indicators"; SW-F8; `System Design Report.md` §3.2 Data Integrity: "Alerts are also generated for operators so maintenance or sensor troubleshooting can be performed promptly"). This is the dashboard's expression of the project's ethical core — fail-safe to the static rating — and the most safety-critical view.

## Current Implementation

None. DS's producers exist but only in memory, not in any exported file:

- `backend/DLRSafetyMonitor.py::DLRSafetyMonitor.run_check(raw_data)` (DS C7) returns `{"status", "rating", "fallback", "alerts"}`. Gates G1 (sensor availability), G2 (communication link), G3 (range), G4 (ampacity plausibility) and G5 (delta check) all cause a fallback (G5 reports `min(computed, static_rating)`); G6 is the learned anomaly check (`backend/anomaly_detector.py::AnomalyDetector.check(raw_data, rating) -> (is_anomalous, reason)`, DS C10).
- `anomaly_score` (unit `pu`, range 0–1000) is defined in `PIPELINE_SCHEMA` v2 but is not in the v1 export.
- `PIPELINE_SCHEMA` v3's `wind_source`, `temp_source`, `humidity_source`, `solar_source` record per-field provider provenance, including `synoptic` as automatic fallback; also not in the v1 export.

## Interface & Data Contract

Inputs the view needs — **none are in the v1 export today** (PRD §8, G2, G7):

| Display | Needed from DS | Current state |
|---|---|---|
| Fallback active? | a boolean per row (analogue of `fallback`) | In-memory only |
| Reason | which gate/branch tripped and a human-readable message (analogue of `alerts`, `reason`) | In-memory only |
| Rating basis in effect | `static_rating` vs. `min(computed, static_rating)` for G5 (OD-6) | In-memory only |
| Anomaly score | `anomaly_score` | In `PIPELINE_SCHEMA` v2, not exported |
| Data provenance (optional) | `*_source` | In `PIPELINE_SCHEMA` v3, not exported |

Behavior rules:

- **Status is never hidden.** Fallback and anomaly states appear in a persistent location in the shell (F2's status-banner slot), visible regardless of which panel is focused, and F3's headline limit reflects the basis (SW-NF1).
- **Three states are distinct, not one:** *normal*, *warning (alert without fallback, e.g. G5 delta)*, and *fallback active*; plus *data unavailable/stale* (F1) which is a UI-detected condition rather than a DS-detected one. Wording and color convention is the one defined in F2 and shared with F3.
- **State the basis honestly.** For G5 the reported rating is `min(computed, static_rating)`, so the UI must not always say "static rating in effect"; wording depends on OD-6 and what DS exports.
- **Reason and time:** show when the status began and the DS-provided reason so the operator can start sensor troubleshooting.
- **Alert history** (a list of recent events) is useful but not stated in the source documents; treat as optional until the team decides (Open Questions).
- The UI never infers fallback from a drop in `dlr_amps`, and never *suppresses* a DS fallback. It displays what DS exports (SW-NF4).

## Blocked by

**F1** and **F2** (internal: the limit-basis view-model and the status-banner slot). **External:** DS exports fallback/anomaly fields (G2) and confirms the rating basis semantics (OD-6). Can be built against a **mock** fixture extension with agreed column names meanwhile.

## Blocks

**F8** — the end-to-end and usability tests require this view; `System Design Report.md` §3.3 requires "anomaly flags, and fallback status indicators update correctly".

## Parallel-safe with

**F3**, **F4**, **F5** (after F1 and F2). F3 reads the same F1 limit-basis field, so there is no file collision, but agree the status vocabulary in F2.

## Known Issues

- **Status is not in any exported file** — the single biggest gap (PRD §8, G2).
- **Fallback targets** (verified in `DLRSafetyMonitor.py`): G1–G4 and G6 → `static_rating`; G5 → `min(computed, static_rating)`. DS C7's Known Issues claims G1/G2 use `last_good_rating`, which the code does not do (stale spec — confirm with DS). The course documents say "default back to … static" without distinction (OD-6).
- **DS test contradiction (not confirmed):** DS C7 Known Issues says `test_gate_2_fails_when_link_status_not_ok` asserts `status == "ok"` while fallback is True. The test actually asserts `status == "fallback"`, so no such contradiction exists in the code; `_fallback()` sets `status` to `"fallback"`.
- **False positives are nonzero in the learned detector** (DS C10: 3.77% and 0.53% on clean held-out data) — so the UI will occasionally show an anomaly on good data; wording should not overclaim a sensor fault.
- **Learned-model artifacts are gitignored**; without them the model branch is absent and heuristics carry G6 alone (DS C10) — an "anomaly detector degraded" condition DS does not export either.
- **Shadow stream** (`data/shadow/predictions/*.jsonl`) carries `fallback_used` / `fallback_reason` for forecasts — a different meaning from C7's gate fallback (OD-12).

## Acceptance Criteria

- Against a mock extension of the fixture, a row with fallback active shows the fallback indicator, the reason text, and the rating basis; a row with an alert but no fallback shows a distinct warning state; a normal row shows neither.
- The status indicator is visible from every panel (persistent), and F3's headline limit changes basis with it.
- Following `System Design Report.md` §3.3: for each of the injected-anomaly cases DS tests (out-of-range, implausible rating, large delta, sensor/link loss), the dashboard shows the matching state when fed the corresponding mock rows, and **no** case leaves a normal-looking dynamic limit on screen.
- The UI shows fallback for every fallback row and never shows fallback for a normal row (no UI-side inference), checked against a mock with a known mix.
- Missing fallback/anomaly columns (v1 export) result in an explicit "status not provided" state, not a silent "normal" — until DS exports status, the dashboard must not imply that normal is verified.
- Colour is not the only carrier of status (text/icon redundancy) — consistent with ISO 9241 readability; verified in F8's usability review.

## Open Questions

- OD-6 (basis wording), OD-12 (shadow stream), OD-10 (standards).
- Alert history/log and acknowledgment — required? Not stated; "operator response time to flagged conditions" is a usability review focus (`System Design Report.md` §3.3) but acknowledgement workflow is unspecified.
- Should provenance (`*_source`) be shown, e.g. "wind from fallback provider"? Optional; not in the source requirements.
