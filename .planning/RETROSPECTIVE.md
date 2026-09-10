# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — MVP

**Shipped:** 2026-09-10
**Phases:** 5 (3 GSD-tracked: Phase 3, 4, 5) | **Plans:** 7

### What Was Built
- A safety monitor (`DLRSafetyMonitor`) unified with the real IEEE 738 thermal model, with all five fail-safe gates (G1-G5) resolving toward the static rating instead of a stale or optimistic guess.
- Corridor spatial discretization: two D-01 corridors (Austin↔Corpus Christi, Midland↔El Paso) each split into 5 geodesic points, rated as the minimum ampacity across points, with broadened station discovery and graceful exhaustion fallback.
- Ampacity forecasting (`ampacity_forecast.forecast_ampacity`) with a true out-of-sample walk-forward backtested confidence band, published through an additive `PIPELINE_SCHEMA` v2 extension.
- Learned anomaly detection (`AnomalyDetector`, rolling-baseline cold start, per-corridor control limits) wired as an additive G6 gate into the same fallback path Phase 3 shipped.
- Per-location static-rating comparison (DS-F5) fully wired into the flat pipeline (`dlr_pipeline.py`, `ercot_dlr_merger.py`), closing the one gap a mid-milestone audit surfaced.

### What Worked
- Running a milestone audit *before* declaring v1.0 done caught a real gap (DS-F5 not actually wired end-to-end, despite being checked off) that a plain requirements-checklist review would have missed — `config.STATIC_RATINGS` existed and was correctly read by one consumer (`corridor_discretization.py`) but silently ignored by two others.
- Inserting a small, tightly-scoped Phase 5 to close exactly that one gap (rather than reopening Phase 2) kept the fix auditable and independently verifiable (11/11 must-haves re-derived from a live checkout).
- Fail-safe-by-default as a standing constraint (not a per-phase requirement) made every new gate (G6) and every new consumer (Phase 5's city resolution) default to the conservative choice without needing to re-litigate the principle each time.

### What Was Inefficient
- The original Phase 2 implementation (pre-GSD) shipped DS-F5 as "Complete" without full end-to-end verification, and that status went unchallenged until the first milestone audit — a VERIFICATION.md at Phase 2's original completion would have caught this months earlier.
- The Phase 3+4 forecasting/anomaly-detection loop (`forecast_ampacity`, `AnomalyDetector`) is fully built and tested but has no production caller, because `api/`/`frontend/` are owned by another sub-team and remain not-started placeholders — this is scoped correctly for v1, but means real end-to-end confidence in that loop still rests on tests alone.

### Patterns Established
- Silent-and-conservative fallback on unrecognized/omitted input (e.g. an unknown `city` resolving to `DEFAULT_STATIC_RATING`, which is strictly lower than every configured city rating) is the preferred shape for new optional parameters, over raising — provided the fallback can't cause an optimistic overstatement.
- Every VERIFICATION.md independently re-derives evidence against a live checkout rather than trusting SUMMARY.md's claims — this caught the DS-F5 gap and should stay the norm for future phases.

### Key Lessons
1. A milestone-level audit that cross-references REQUIREMENTS.md, VERIFICATION.md, and actual code (not just checkboxes) is worth running even when every individual phase reports "passed" — pre-GSD phases in particular can carry unverified claims forward silently.
2. When a gap is found late, a narrowly-scoped closure phase (not a reopened prior phase) keeps the fix's blast radius small and independently auditable.

### Cost Observations
- Sessions: not tracked per-session in this repo's GSD history.
- Notable: the DS-F5 closure phase (05) was the smallest phase in the milestone (1 plan, 2 files touched) and delivered the highest-leverage fix — the one requirement standing between "gaps_found" and "passed" at milestone close.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | N/A | 5 | First GSD-tracked milestone on this repo; Phases 1-2 adopted from pre-GSD implementation, Phases 3-5 fully GSD-tracked with VERIFICATION.md gates |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | 155 passing | Not measured | 0 (Phase 4 explicitly deferred Tier 2 modelling to avoid adding a dependency; Phase 5 added none) |

### Top Lessons (Verified Across Milestones)

1. Audit before closing a milestone, even when every phase individually reports "passed" — cross-referencing requirements against actual code found a gap phase-level review missed.
