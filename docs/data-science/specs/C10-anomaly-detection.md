# C10 — Learned Anomaly Detection

**Phase:** 4 (Predictive) · **Effort:** L · **Status:** Not started. The System Design Report claims a model is "currently being trained and tuned" (§3.2, "Data Integrity") — this claim is inaccurate; see `PRD.md` §9 Documentation Discrepancies. No model, training script, or training dataset exists anywhere in the repo.

**Responsibility:** Replace or augment `DLRSafetyMonitor`'s (C7) deterministic threshold gates with a model trained on historical baselines per variable (wind, temp, solar, load), so anomaly detection can catch patterns that fixed range/delta thresholds miss — while preserving C7's non-negotiable fail-safe-to-static behavior.

## Current Implementation

None. `backend/DLRSafetyMonitor.py` (C7) is entirely deterministic threshold/range gating (G1–G5) — no learned component anywhere.

## Interface & Data Contract

Not yet designed. Should be additive to C7's `run_check` result shape (`status`, `rating`, `fallback`, `alerts`), not a replacement of its interface — a learned anomaly signal should be able to trigger the same fallback path C7 already implements, not introduce a second, parallel fallback mechanism.

## Blocked by

**C7** — needs the gating framework (and, once fixed, a correct ampacity computation to detect anomalies against) to exist first. This is a hard dependency: a learned model that flags "this rating looks wrong" only makes sense once there's an agreed-correct rating to compare against, which is exactly what C7's dependency on C5 establishes.

Also depends on **accumulated historical data**, same lead-time concern as C9 — see `ROADMAP.md` Finding 5.

## Blocks

Nothing else in this roadmap depends on C10 — it's the last component in the dependency chain.

## Parallel-safe with

**C9** — both Phase 4, distinct models, workable simultaneously by different people once both land.

## Known Issues

Not applicable — no implementation exists yet. (C7's Known Issues — particularly the placeholder ampacity formula — are a prerequisite blocker, not a C10 issue directly, but worth re-reading before starting this component, since training against C7's current placeholder rating instead of C5's real one would bake in the same defect this whole roadmap is trying to remove.)

## Acceptance Criteria

Adapted from System Design Report §3.3's stated (but not yet implemented) validation plan:

- Injecting corrupted or out-of-range values into weather/operating data streams (e.g. sudden temperature spikes, impossible wind speeds) is correctly identified as anomalous.
- Zero false positives on clean historical data.
- Automatic fallback to SLR is confirmed upon every detected anomaly — this must go through C7's existing fallback path, not a separate one.

## Open Questions

- Model type — unspecified in any existing doc.
- Does this run instead of C7's deterministic gates, alongside them (belt-and-suspenders), or only for anomaly types the deterministic gates structurally can't catch (e.g. plausible-but-wrong values within range)?
- Training data provenance — same historical-accumulation question as C9, but specifically needs *labeled* anomalies or a synthetic-injection strategy (per the acceptance criteria above) rather than just raw historical weather.
