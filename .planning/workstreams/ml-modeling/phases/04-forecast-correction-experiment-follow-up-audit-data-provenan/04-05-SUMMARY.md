---
phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan
plan: 05
subsystem: ml-audit
tags: [numpy, thermal-model, markdown-audit-trail, forecast-experiment-audit]

requires:
  - phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan (plan 03)
    provides: "Block-bootstrap pairwise comparison, ABLATION-basis replication (Austin clean, Midland contradicted), fresh-period reservation"
  - phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan (plan 04)
    provides: "Overrating profile, measured convection crossover, three-period quantile calibration, matched-overrating-rate retained capacity"
provides:
  - "low_wind_sensitivity_sweep / sensitivity_vs_instability_finding -- measured, not asserted, that the low-wind ampacity response is a physics floor (exactly flat below the crossover, monotone, continuous) rather than a numerical instability, for both corridors"
  - "reverify_convective_seam_bit_identity -- Phase 3's Success-Criterion-4 convective-seam bit-identity claim reproduced from an independent code path against the committed golden fixture, with the override proven non-trivial"
  - "The sub-floor routing question answered by attempting it: a positive, below-the-natural-convection-floor corrected convective term IS permitted to reach the physics through the q_conv_override seam -- predict_cooling_correction's guard rejects only a non-positive term"
  - "The frozen record (forecast_correction_experiment.md) carries one appended, byte-identity-gated, append-only six-item D-04 amendment -- the Expectation and Measured-results sections remain byte-identical, every committed line still appears in order"
  - "The audit record (forecast_correction_followup_audit.md) carries a corrected-language table, an actionable corrected verdict (keep both ml_cooling_corrected and reference_ml_refit_24h live, low-to-moderate confidence), a 16-line completed-findings list across all five decisions, a confidence statement naming each claim's basis, and eight Limitations items"
affects: [04-06]

actuals:
  tokens: 20424
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Measure before asserting: low_wind_sensitivity_sweep's own docstring works out the predicted flat-below-crossover response from the code first, then the sweep confirms it by measurement -- the same discipline convection_crossover_wind_speed (Plan 04-04) established, applied to a sensitivity-vs-instability question instead of a regime-boundary one."
    - "Attempt, don't read: the sub-floor routing question (can a corrected convective term below the natural-convection floor reach the physics) is answered by constructing a deliberately sub-floor correction and routing it through the real predict_cooling_correction/apply_cooling_correction call path, not by reading the guard code and reasoning about it."
    - "Bold lead-in text instead of markdown headings inside a section parsed by a naive '##+ ' section-boundary split -- avoids the same self-contradicting-regex defect class already logged in WINDOWS.md (ids 2-3) without needing a corrected-regex workaround, by simply not emitting the heading level the verify script's own regex over-matches."

key-files:
  created: []
  modified:
    - backend/forecast_experiment_audit.py
    - backend/tests/forecast_experiment_audit_test.py
    - docs/data-science/decisions/forecast_correction_experiment.md
    - docs/data-science/decisions/forecast_correction_followup_audit.md
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "The sub-floor cooling-correction attempt uses the default thermal_model.ConductorConfig() (matching the golden-fixture bit-identity checks' own conductor), not a corridor-specific one -- the question is about the q_conv_override seam's own behavior, which is conductor-config-independent in kind, not about any particular corridor's measured crossover."
  - "Item 6 of the frozen-record amendment (low-wind sensitivity) quotes Arm 4's own description sentence as the 'original wording' rather than an overstated claim, and is explicit that this item is an addition closing a silence, not a correction of an overstatement -- the frozen record never actually makes a claim about low-wind sensitivity vs. instability for this amendment to correct."
  - "Task 3's 'Completed audit findings' and 'Confidence statement' subsections are written as bold lead-in text, not markdown headings, specifically so the section's own '##+ ' naive section-boundary verify-script split does not truncate the section at the first subsection -- a structural accommodation of the verify script as literally written, not a corrected-regex workaround."

patterns-established: []

requirements-completed: [D-04]

coverage:
  - id: D1
    description: "Low-wind sensitivity is measured, not asserted, to be a physics floor (finite, monotone, continuous, flat below the crossover) rather than numerical instability, for both corridors"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py::test_low_wind_sensitivity_sweep_finite_and_monotone_both_corridors, ::test_low_wind_sensitivity_sweep_below_crossover_flat_above_crossover_rises, ::test_sensitivity_vs_instability_finding_states_physics_with_three_citations"
        status: pass
      - kind: other
        ref: "inline verify: LOW_WIND_SENSITIVITY_OK (both corridors)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The convective-seam bit-identity claim is independently re-verified against the committed golden fixture, with the override proven non-trivial and the sub-floor routing question answered by attempting it"
    requirement: "D-04"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py::test_reverify_convective_seam_bit_identity_three_equalities_hold, ::test_reverify_convective_seam_bit_identity_perturbed_override_is_non_trivial, ::test_reverify_convective_seam_bit_identity_sub_floor_attempt_is_permitted_with_citation"
        status: pass
      - kind: other
        ref: "inline verify: SEAM_BIT_IDENTITY_OK permitted"
        status: pass
    human_judgment: false
  - id: D3
    description: "The frozen record carries an appended six-item D-04 amendment; the Expectation and Measured-results sections are proven byte-identical to their committed versions; every committed line still appears in order"
    requirement: "D-04"
    verification:
      - kind: other
        ref: "inline verify: EXPECTATION_AND_MEASURED_BYTE_IDENTICAL_OK, FROZEN_RECORD_APPEND_ONLY_OK (246 lines added), D04_AMENDMENT_OK (6 subsections, 30 figures, 2710 words)"
        status: pass
    human_judgment: false
  - id: D4
    description: "The audit record carries an actionable corrected verdict, a corrected-language table, a completed-findings list across all five decisions, a confidence statement, and a Limitations section -- with no overstated 'established/unique/proven winner' or 'universal ceiling' language"
    requirement: "D-04"
    verification:
      - kind: other
        ref: "inline verify: CORRECTED_VERDICT_OK (6 correction rows, 1367 verdict words, 16 findings, 8 limitations), FROZEN_RECORD_SETTLED_OK, DOC_ONLY_TASK_OK"
        status: pass
    human_judgment: true
    rationale: "Whether the corrected verdict's recommendation is actually actionable and well-calibrated, and whether the amendment's prose honestly represents the strength of the corrected claims, is a judgment call about honesty and framing quality that the automated word/table/regex checks prove the required structure and figures are present for, not that the narrative judgment itself is sound."

duration: 70min
completed: 2026-09-30
status: complete
---

# Phase 04, Plan 05: D-04 Low-Wind Sensitivity Measurement and Frozen-Record Amendment Summary

**Measured (not asserted) that the low-wind ampacity response is a physics floor rather than a numerical instability, independently re-verified Phase 3's convective-seam bit-identity claim and found the override seam permits a sub-floor corrected term, then appended a byte-identity-gated six-item amendment to the frozen record and published the audit's own corrected verdict recommending both `ml_cooling_corrected` and `reference_ml_refit_24h` stay live at low-to-moderate confidence.**

## Performance

- **Duration:** 70 min
- **Started:** 2026-09-30
- **Completed:** 2026-09-30
- **Tasks:** 3
- **Files modified:** 5 (`backend/forecast_experiment_audit.py`, `backend/tests/forecast_experiment_audit_test.py`, `docs/data-science/decisions/forecast_correction_experiment.md`, `docs/data-science/decisions/forecast_correction_followup_audit.md`, `ACKNOWLEDGEMENTS.md`)

## Accomplishments

**Task 1 — Low-wind sensitivity measurement and independent seam bit-identity re-verification:**
- `low_wind_sensitivity_sweep(corridor, *, air_temp_c=None, wind_grid=None, ghi_wm2=None)` sweeps ampacity across a wind grid bracketing the measured convection crossover, returning finiteness/non-negativity (including at exactly zero wind), monotonicity, a continuity measurement (vanishing-step gap across the crossover), the crossover's own index, and the maximum first difference with the wind speed where it occurs.
- `sensitivity_vs_instability_finding(corridor)` turns the sweep into a publishable finding: verdict `"physics"` for both corridors, the three checked properties (finiteness/monotonicity/continuity) each with measured evidence, the peak sensitivity located well above the crossover (not at zero wind), and `file:line` citations.
- `reverify_convective_seam_bit_identity()` loads the committed golden fixture directly (never invoking `thermal_model_test.py` itself) and reproduces exact array equality for the ampacity, the convective term, and the explicit-override-vs-default comparison; proves the override is non-trivial via a perturbed-term check; and answers D-04's sub-floor routing question by attempting it — a positive, below-the-natural-convection-floor corrected term reaches the physics unobstructed through the `q_conv_override` seam, outcome `"permitted"`, because `predict_cooling_correction`'s own guard (`backend/forecast_correction_models.py:547`) rejects only a non-positive term and `ieee738_ampacity`'s override branch (`backend/thermal_model.py:236-239`) bypasses the natural-convection floor entirely when an override is supplied.
- 12 new tests, network-free (97 → 107 total audit tests). `backend/thermal_model.py`, `backend/forecast_correction_models.py`, and `backend/tests/thermal_model_test.py` carry zero diff.

**Task 2 — Six-item D-04 amendment appended to the frozen record, under byte-identity and append-only gates:**
- Appended one new section, `## Follow-up Audit Amendment (Phase 4, D-04)`, immediately before `## References`, with six numbered subsections (one per D-04 item): lowest-observed-MAE framing (not an established winner, with the Midland cooling-vs-refit indistinguishable-from-zero pairwise margin brought in from D-02), the interval's lower bound vs. the 30A threshold (with the block-length-sensitivity flip reported as "the strongest sentence in this amendment"), the oracle as a diagnostic not a ceiling, correction headroom measured against `raw_forecast` not persistence (with side-by-side figures at both corridors), the legacy-arm/60-minute reaffirmation, and the low-wind-sensitivity-is-physics finding (crossover 0.1428 m/s, finite/monotone/continuous, sub-floor outcome permitted with citations).
- Added exactly one forward-pointer line at the head of `## Verdict` (added, nothing existing touched), naming the amendment and the audit record.
- Verified, before committing, that `## Expectation` and `## Measured results` remain byte-identical to the committed versions (extracted and compared byte-for-byte) and that every line of the committed file still appears, in order, in the amended one (246 lines added, zero deleted or reworded).

**Task 3 — Corrected verdict, corrected-language table, and Limitations published in the audit record:**
- `## Corrected language in the frozen record (D-04)`: a six-row table (D-04 bullet → frozen wording → audit's revision → amendment subsection), the two structural guarantees (byte-identical sections, append-only discipline) with their gates named, and this phase's own physics findings reported in full.
- `## Corrected verdict`: one actionable paragraph recommending both `ml_cooling_corrected` and `reference_ml_refit_24h` stay live as integration candidates at low-to-moderate confidence, naming what would strengthen (a FRESH-basis confirmation reproducing Austin's replication at Midland) or weaken (a FRESH-basis run reproducing Midland's contradiction) that recommendation. Grounded in the ABLATION-basis replication (Austin clean, Midland contradicted), the block-length-sensitivity flip, and the matched-rate retained-capacity finding; states plainly where it differs from the frozen record's own "wins ... at both corridors" claim and why (Plan 04-03's direct pairwise comparison, never computed in the frozen record). A 16-line completed-findings list covering all five decisions (D-01 through D-05), and a confidence statement naming each claim's basis (SYNTHETIC/ABLATION/FRESH) with the measured fresh-basis row count (0) and an explicit refusal to call any ABLATION-basis finding a fresh-period confirmation.
- `## Limitations`: eight items, each marked permanent or removable by calendar time or Plan 04-06's data contract — the fresh-basis row count, the reanalysis-derived truth with no sensor validation, the already-seen ABLATION basis, the single-model/single-conductor/weakest-link proxy (carried forward unchanged from the frozen record), the non-row-comparable refit arms, the leakage probe's un-retroactive re-run, this audit's own uncorrected multiple pairwise comparisons, and the single-ambient-temperature scope of the low-wind sweep.
- No "established winner" or "universal ceiling" language anywhere in the new sections (verified by an automated banned-phrase grep). No backend changes; the frozen record carries no further diff beyond Task 2's committed amendment.

## Task Commits

1. **Task 1: Low-wind sensitivity sweep and independent convective-seam bit-identity re-verification** — `f9172da` (feat)
2. **Task 2: Append the six-item D-04 amendment to the frozen record** — `eca9422` (docs)
3. **Task 3: Publish the corrected verdict, corrected-language table, and Limitations** — `effe631` (docs)
4. **ACKNOWLEDGEMENTS.md update (per project CLAUDE.md's ECE 464 AI-use disclosure requirement)** — `cf9bbe4` (docs)

## Files Created/Modified

- `backend/forecast_experiment_audit.py` — `low_wind_sensitivity_sweep`, `sensitivity_vs_instability_finding`, `_attempt_sub_floor_cooling_correction`, `reverify_convective_seam_bit_identity`
- `backend/tests/forecast_experiment_audit_test.py` — 12 new tests covering the sweep's finiteness/monotonicity/continuity, the crossover-index-based below/above split, the finding's citations, the three re-verified equalities, the non-trivial-override check, and the sub-floor attempt's measured `"permitted"` outcome
- `docs/data-science/decisions/forecast_correction_experiment.md` — `## Follow-up Audit Amendment (Phase 4, D-04)` section appended before `## References`; one forward-pointer line added at the head of `## Verdict`
- `docs/data-science/decisions/forecast_correction_followup_audit.md` — `## Corrected language in the frozen record (D-04)`, `## Corrected verdict`, and `## Limitations` sections fully written (previously placeholders)
- `ACKNOWLEDGEMENTS.md` — session entry per the project's ECE 464 AI-use disclosure requirement

## Decisions Made

See `key-decisions` in frontmatter above for full detail. Summary:
- The sub-floor cooling-correction attempt uses the default `ConductorConfig()`, matching the golden-fixture checks' own conductor, since the question is about the seam's behavior in kind, not corridor-specific physics.
- Item 6 of the amendment is explicitly framed as an addition closing a silence (the frozen record never makes a claim about low-wind sensitivity to correct), not a correction of an overstatement, while still satisfying the "quoted original wording" structure the other five items use.
- Task 3's two subsections that would otherwise need `###` headings are written as bold lead-in text instead, so the section's own naive `##+`-boundary verify-script split does not truncate it — a structural accommodation of the verify script as written, not a corrected-regex workaround.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, verify-script defect] Task 3's own "Corrected verdict" doc-verify script's `##+ ` section-boundary split also matches `### ` subheadings**
- **Found during:** Task 3, first attempt at writing the completed-findings list and confidence statement as `###` subsections
- **Issue:** The same self-contradicting-regex defect class already logged in `.planning/WINDOWS.md` (phase 04, ids 2 and 3): the verify script's `sec(title)` helper splits on `^##+\s+` to isolate a section's body, which also matches `### ` subheadings — any `###` subsection I wrote inside `## Corrected verdict` would truncate the extracted section at that first subsection, well before the required word count, findings count, and D-01..D-05 mentions were reached. Confirmed by direct measurement: with `### Completed audit findings` as a heading, `len(verdict.split())` measured 448 words (just the opening paragraphs) instead of the full section.
- **Fix:** Rewrote the two subsections ("Completed audit findings, by decision" and "Confidence statement") as bold lead-in text (`**Completed audit findings, by decision.**` / `**Confidence statement.**`) rather than markdown headings — avoiding the heading level the verify script's own regex over-matches, rather than relying on a corrected-regex workaround to prove substantive intent. No PLAN.md edit made (out of this plan's file scope); no new WINDOWS.md entry added, since the defect class is already open there and applies project-wide to this phase's doc-verify scripts, matching the precedent set by Plans 04-02/04-03/04-04.
- **Files modified:** `docs/data-science/decisions/forecast_correction_followup_audit.md`
- **Verification:** Re-ran the literal, unmodified `CORRECTED_VERDICT_OK` verify script after the fix — all checks pass (1367 verdict words, 16 findings, D-01 through D-05 all present).
- **Commit:** `effe631` (Task 3 commit)

**2. [Rule 1 - Bug] The confidence statement's "no fresh confirmation" phrasing did not literally match the verify script's own regex**
- **Found during:** Task 3, second verify attempt (after fixing deviation 1 above)
- **Issue:** The verify script requires the literal substring `not a confirmation`, `no confirmation`, or `cannot confirm` somewhere in the Corrected verdict section. The first draft wrote "no claim in this record is a confirmation on a genuinely fresh chronological period" — a negated clause that conveys the same meaning but does not contain any of the three required substrings contiguously.
- **Fix:** Reworded to lead with the literal phrase: "**not a confirmation** — no claim in this record is a confirmation on a genuinely fresh chronological period."
- **Files modified:** `docs/data-science/decisions/forecast_correction_followup_audit.md`
- **Verification:** `CORRECTED_VERDICT_OK` passes.
- **Commit:** `effe631` (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 bugs discovered while running this plan's own verify scripts against the actual written content).
**Impact on plan:** Both fixes were necessary to satisfy the plan's own stated acceptance criteria; neither changed the substance of what was reported — only its literal structure/phrasing to match the verify scripts' own patterns. No scope creep.

## Issues Encountered

- **Worktree was forked before Plans 04-01 through 04-04's own merges landed on `main`.** This worktree's branch was created at `04a679b` (the phase-04 planning commit). Confirmed clean, non-divergent ancestry (merge-base equalled worktree HEAD, clean tree) and fast-forward-merged `main` (through `1f1cf3b`) before starting Task 1, per this session's explicit instructions and mirroring the documented precedent for every prior Phase 4 plan.
- **`.venv` does not exist in a fresh worktree** (gitignored, per-worktree working-directory state). Symlinked `.venv` to the main checkout's `.venv` (untracked), mirroring every prior Phase 4 plan's own documented precedent. No `data/experiment/` regeneration was needed this plan — Tasks 1-3 are pure code transforms and documentation, with no network fetch.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Plan 04-06 can read the following directly from this summary and the audit record's `## Corrected verdict` section, without re-running any measurement:

- **The corrected verdict's single recommendation and what would change it:** keep both `ml_cooling_corrected` and `reference_ml_refit_24h` live as integration candidates, at low-to-moderate confidence. It would strengthen toward preferring `ml_cooling_corrected` if a future FRESH-basis confirmation run reproduces AUSTIN_CORPUS_CHRISTI's clean replication at MIDLAND_EL_PASO too; it would weaken toward narrowing to `ml_wind_corrected` or dropping cooling's "primary candidate" status if a future FRESH-basis run instead reproduces MIDLAND_EL_PASO's contradiction.
- **The measured convection crossover and the sub-floor routing outcome:** 0.1428 m/s at 35.0°C (both corridors, shared conductor configuration); the low-wind response is measured physics (exactly flat below the crossover, monotone, continuous), not numerical instability; a positive corrected convective term below the natural-convection floor IS permitted to reach the physics through the `q_conv_override` seam (`predict_cooling_correction`'s guard only rejects non-positive terms) — a real finding about the seam's exposure that Plan 04-06's integration-readiness plan should weigh when scoping any future hardening of the correction pipeline.
- **Which of the frozen record's claims were corrected, and where:** all six D-04 items, in the frozen record's own appended `## Follow-up Audit Amendment (Phase 4, D-04)` section (one subsection per item) and cross-referenced from the audit record's `## Corrected language in the frozen record (D-04)` table.
- **Remaining blockers the verdict names:** none that block Plan 04-06 specifically — the verdict's own confidence is bounded by the FRESH basis's zero-row count (a calendar-time-removable limitation, not a blocking one) and by the ABLATION basis's already-seen status (a permanent limitation of this calendar range).
- **Specific unresolved questions the integration plan must schedule or leave open:** (1) the 60-minute-vs-24-hour-vs-both product-scope question, named as unresolved in both the frozen amendment (item 5) and this record's own completed-findings list (D-05); (2) whether a future FRESH-basis confirmation run should be scheduled now or deferred until the reserved period accrues its 56-row/14-day minimum (roughly two weeks from this audit's run date); (3) whether the sub-floor seam exposure this plan found warrants a hardening task (an explicit floor-aware guard in `predict_cooling_correction`) before any production integration, named here as a candidate "now" item for Plan 04-06's now-vs-later split.

No blockers for Plan 04-06.

---
*Phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan*
*Completed: 2026-09-30*

## Self-Check: PASSED

- FOUND: `backend/forecast_experiment_audit.py`
- FOUND: `backend/tests/forecast_experiment_audit_test.py`
- FOUND: `docs/data-science/decisions/forecast_correction_experiment.md`
- FOUND: `docs/data-science/decisions/forecast_correction_followup_audit.md`
- FOUND: `ACKNOWLEDGEMENTS.md`
- FOUND commit: `f9172da`
- FOUND commit: `eca9422`
- FOUND commit: `effe631`
- FOUND commit: `cf9bbe4`
