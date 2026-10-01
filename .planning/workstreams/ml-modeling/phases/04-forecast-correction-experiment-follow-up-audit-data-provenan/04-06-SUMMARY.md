---
phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan
plan: 06
subsystem: ml-audit
tags: [sklearn, mlp, scipy, pearson, spearman, forecast-experiment-audit, roadmap, acknowledgements]

requires:
  - phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan (plan 03)
    provides: "Persisted per-row residuals and the real ABLATION-basis out-of-sample comparison (audit_ablation_report_<CORRIDOR>.json)"
  - phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan (plan 05)
    provides: "Corrected verdict recommending both ml_cooling_corrected and reference_ml_refit_24h stay live"
provides:
  - "lag_vs_covariate_ablation(corridor) -- a three-variant (all/lags-only/covariates-only) out-of-sample feature ablation for the refit reference estimator, answering the frozen record's own Open Question about its 60-minute-to-24-hour reversal"
  - "cooling_rediscovery_hypothesis(corridor) -- Pearson/Spearman prediction and residual correlations between each ablation variant and the cooling correction, reconstructed from Plan 04-03's persisted residuals without re-scoring that arm"
  - "The Integration readiness plan (D-05) section: a 19-field data contract with three distinct timestamps, a now-versus-blocked split of every audit recommendation, a seven-part packaging/fetch/fallback/shadow-eval/monitoring/rollback outline, and the horizon product question named and left open"
  - "Phase 4's ROADMAP entry closed with a disposition per success criterion (four MET, one MET IN PART) and marked complete (6/6 plans)"
  - "One consolidated Phase 4 AI-use disclosure entry in ACKNOWLEDGEMENTS.md covering all six plans"
affects: []

actuals:
  tokens: 25300
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Compose two D-05 sub-questions (the feature ablation and the cooling-rediscovery hypothesis) into ONE combined git-ignored report, computed once -- cooling_rediscovery_hypothesis is a thin, idempotent wrapper around lag_vs_covariate_ablation's own already-computed variant predictions, never a second, parallel fit of the same three variants."
    - "Lag-feature enumeration from the config constant, never pattern-matched: the ablation's column partition is {f'dlr_amps_lag_{h}h' for h in config.FORECAST_ML_LAG_HOURS} versus everything else in ampacity_forecast.ML_FEATURE_COLUMNS, asserted disjoint/non-empty/union-complete against the REAL column names before any fit."

key-files:
  created: []
  modified:
    - backend/forecast_experiment_audit.py
    - backend/tests/forecast_experiment_audit_test.py
    - docs/data-science/decisions/forecast_correction_followup_audit.md
    - .planning/workstreams/ml-modeling/ROADMAP.md
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "The rolling-mean history feature (dlr_amps_roll_mean_6h) is NOT one of the enumerated lag columns -- the plan's own read_first instruction says the lag set is 'enumerated from the lag-hours config constant rather than pattern-matched', and FORECAST_ML_LAG_HOURS only names the four dlr_amps_lag_{h}h columns. The rolling mean falls into the covariate bucket alongside the weather columns and time encodings, a precise reading of the plan's own instruction rather than a physically-motivated regrouping."
  - "cooling_rediscovery_hypothesis(corridor) is a thin wrapper that re-runs lag_vs_covariate_ablation and returns its embedded cooling_rediscovery key, rather than an independent computation -- both the plan's own <action> text ('Compose both results into one git-ignored JSON report per corridor') and the shared verify script (which reads both 'variants' and 'cooling_rediscovery' from the SAME audit_ablation_features_<CORRIDOR>.json file) require one combined report, and a second independent fit of the same three MLP variants would only risk silent divergence for no benefit (the fit is already deterministic under the phase's one fixed seed)."
  - "The ROADMAP's second success criterion (the strengthened comparison) is marked 'MET IN PART', not 'MET' -- the fresh-chronological-holdout reservation is a reservation (period defined, enforced disjoint from Phase 3's splits) but not an executed confirmation (the measured FRESH row count is 0 as of this audit's run date). Marking it fully MET would have been the exact 'a criterion marked met that was only half met' failure mode T-04-06-09 in this plan's own threat model warns against."

patterns-established: []

requirements-completed: [D-05]

coverage:
  - id: D1
    description: "A real, out-of-sample feature ablation (all features / lags only / covariates only) for the refit reference estimator, with provably disjoint, dropped-not-zeroed column subsets, answering the frozen record's own Open Question about its 60-minute-to-24-hour reversal"
    requirement: "D-05"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py::test_lag_vs_covariate_ablation_runs_and_returns_documented_shape"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py::test_feature_column_partition_disjoint_nonempty_union_complete_against_real_columns"
        status: pass
      - kind: other
        ref: "data/experiment/audit_ablation_features_AUSTIN_CORPUS_CHRISTI.json, ..._MIDLAND_EL_PASO.json (git-ignored evidence; live run via ABLATION_FEATURES_RUN_OK/ABLATION_FEATURES_SHAPE_OK)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The cooling-rediscovery hypothesis is tested by prediction AND residual correlation for all three variants against the cooling correction, with an interpretation distinguishing the two"
    requirement: "D-05"
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_audit_test.py::test_correlate_aligned_raises_on_mismatched_index, ::test_cooling_rediscovery_from_predictions_raises_on_length_mismatch, ::test_cooling_rediscovery_hypothesis_matches_lag_vs_covariate_ablation_embedded_result"
        status: pass
    human_judgment: false
  - id: D3
    description: "The Integration readiness plan (D-05) section: both candidates named live, the 19-field data contract with three distinct timestamps, the now-versus-blocked split, the seven-part outline, and the horizon question named and left open"
    requirement: "D-05"
    verification:
      - kind: other
        ref: "D05_SECTION_OK / AUDIT_RECORD_COMPLETE_OK / DOC_ONLY_TASK_OK inline verify scripts in 04-06-PLAN.md Task 2 (D05_SECTION_OK re-run under the corrected ##(?!#) boundary regex -- see Deviations)"
        status: pass
    human_judgment: true
    rationale: "Whether the data contract is genuinely implementable, the fallback ladder honestly mirrors the standing fail-safe commitment, and the now-versus-blocked split is well-scoped are judgment calls about specification quality the automated word/table/regex checks prove the required structure and figures are present for, not that the professional judgment embedded in them is sound."
  - id: D4
    description: "Phase 4's ROADMAP entry closed with a disposition per success criterion and every other entry proven byte-identical; one consolidated Phase 4 disclosure entry filed in ACKNOWLEDGEMENTS.md"
    verification:
      - kind: other
        ref: "ROADMAP_SCOPED_EDIT_OK / ACKNOWLEDGEMENTS_OK inline verify scripts in 04-06-PLAN.md Task 3"
        status: pass
    human_judgment: true
    rationale: "Whether the 'MET IN PART' framing for the second success criterion is the honest disposition, and whether the consolidated disclosure entry's depth genuinely matches the two preceding entries' own standard, are judgment calls about honesty and completeness that the automated checks prove structure and keyword presence for, not narrative soundness."

duration: 95min
completed: 2026-10-01
status: complete
---

# Phase 4 Plan 06: Integration Readiness Plan (D-05) — Ablation, Data Contract, and Phase Closure Summary

**A real out-of-sample lag-versus-covariate ablation (corridor-dependent: supports the frozen record's own explanation at Austin, does not at Midland) plus a cooling-rediscovery correlation test, a 19-field minimum data contract with three distinct timestamps, and the Phase 4 ROADMAP/AI-disclosure closure — all without building any part of the integration itself.**

## Performance

- **Duration:** 95 min
- **Started:** 2026-10-01
- **Completed:** 2026-10-01
- **Tasks:** 3
- **Files modified:** 5 (`backend/forecast_experiment_audit.py`, `backend/tests/forecast_experiment_audit_test.py`, `docs/data-science/decisions/forecast_correction_followup_audit.md`, `.planning/workstreams/ml-modeling/ROADMAP.md`, `ACKNOWLEDGEMENTS.md`)

## Accomplishments

- **Task 1 — the lag-vs-covariate ablation and the cooling-rediscovery hypothesis test.** `lag_vs_covariate_ablation(corridor)` fits three variants of the SAME refit-reference estimator family (`forecast_training.CANDIDATE_ESTIMATORS["MLPRegressor"]`) on the real ABLATION train rows — all features, lag features only (enumerated from `config.FORECAST_ML_LAG_HOURS`, never pattern-matched), weather-covariate-and-time-encoding features only — and scores all three on the real ABLATION validation rows. The result is corridor-dependent: at AUSTIN_CORPUS_CHRISTI the covariates-only variant (MAE 127.759) approaches the full model's own skill (MAE 127.215, gap 0.545 A, statistically indistinguishable) while the lags-only variant (MAE 131.983, gap 4.768 A, excludes zero) does not — SUPPORTING the frozen record's own proposed explanation. At MIDLAND_EL_PASO the opposite holds: lags-only (MAE 131.450) is measurably closer to the full model than covariates-only (MAE 137.636) — DOES NOT SUPPORT the frozen record's explanation at this corridor. `cooling_rediscovery_hypothesis(corridor)` reconstructs `ml_cooling_corrected`'s predictions from Plan 04-03's own persisted residuals (never re-scored) and measures Pearson/Spearman correlation between each variant and the cooling correction: the covariates-only variant's RESIDUAL correlation (0.846 Austin, 0.803 Midland) is comparable to the full-feature variant's and higher than lags-only's, consistent with — but not proof of — an implicitly rediscovered cooling-like correction, with the interpretation explicitly distinguishing prediction correlation (which two models can share merely by tracking the same diurnal signal) from residual correlation (which means the two models fail in the same places). 9 new tests (96 → 105), network-free; every frozen production module and the frozen decision record carried zero diff.
- **Task 2 — the Integration readiness plan (D-05).** Published the complete `## Integration readiness plan (D-05)` section: both `ml_cooling_corrected` and `reference_ml_refit_24h` named live, neither narrowed away; the ablation and rediscovery results transcribed with the corridor-dependent verdict stated plainly; a 19-field data contract (archived forecasts, three distinct timestamps, local observations with quality flags, units, sensor siting including measurement height above ground, and conductor/span metadata), every field traced to a specific audit finding — the `availability_timestamp` field closes D-01 Finding 4's own central gap; two tables splitting all twelve of this audit's own recommendations into six "now" items and six items blocked on a named contract field; a seven-part outline (packaging, runtime fetch, stale/missing data, a four-rung fallback ladder ending at the static rating with no optimistic guess at any rung, shadow evaluation, monitoring naming the overrating rate, rollback); and the 60-minute-vs-24-hour-vs-both product question named, assigned to whoever owns product scope, and left open with no blanket replacement recommended. Completed the `## References` section citing all six plan summaries, the audit module/tests, and every git-ignored report as evidence, not the artifact of record. No backend changes.
- **Task 3 — ROADMAP closure and the AI-use disclosure.** Added a bolded disposition under each of Phase 4's five success criteria, citing the plan and audit-record section that discharges it: four MET, one (the comparison-strengthening criterion) MET IN PART, since the fresh-chronological-holdout reservation is a reservation, not an executed confirmation (measured FRESH row count is 0). Updated the plan-count line to "6/6 plans complete across 6 waves", checked Wave 6's plan line, and updated the `## Phases` checkbox and `## Progress` table row to 6/6 Complete — verified every other phase's ROADMAP section and the Overview/Backlog/Execution-Order sections byte-identical to their committed versions. Appended one consolidated, ~1,967-word Phase 4 session entry to `ACKNOWLEDGEMENTS.md`, walking all six plans at the depth the file's two preceding entries establish, naming the byte-identity guarantee on the frozen record, the two-mode leakage re-run, the measured fresh-basis row count, the replication-not-confirmation discipline, and every deviation classified by rule.

## Task Commits

Each task was committed atomically:

1. **Task 1: Separate the lag features from the weather covariates, and test whether the refit model is rediscovering the cooling correction** - `d496195` (feat)
2. **Task 2: Write the integration-readiness plan** - `ccf8238` (docs)
3. **Task 3: Close the ROADMAP's Phase 4 entry and file the project's AI-use disclosure** - `7fa8f1e` (docs)

## Files Created/Modified

- `backend/forecast_experiment_audit.py` — `_feature_column_partition`, `_margin_entry`, `_correlate_aligned`, `_load_ablation_report`, `_cooling_rediscovery_from_predictions`, `lag_vs_covariate_ablation`, `cooling_rediscovery_hypothesis`
- `backend/tests/forecast_experiment_audit_test.py` — 9 new tests covering the column partition, the correlation-alignment guard, the unknown-corridor raises, the fit-before-score overlap guard, the full report shape, and the two entry points' determinism
- `docs/data-science/decisions/forecast_correction_followup_audit.md` — `## Integration readiness plan (D-05)` section fully written (previously a placeholder); `## References` completed
- `.planning/workstreams/ml-modeling/ROADMAP.md` — Phase 4's entry closed with five dispositions, six checked plans, updated Phases checkbox and Progress row (scoped edits only)
- `ACKNOWLEDGEMENTS.md` — consolidated Phase 4 session entry appended before `## Keeping This Updated`

## Decisions Made

See `key-decisions` in frontmatter above for full detail. Summary:
- The rolling-mean history feature is grouped with the covariates, not the lags, per the plan's own precise "enumerated from the lag-hours config constant" instruction.
- `cooling_rediscovery_hypothesis` is a thin, idempotent wrapper around `lag_vs_covariate_ablation`'s own embedded result — one combined report, one fit, per the plan's own composition instruction.
- The ROADMAP's second success criterion is marked "MET IN PART", naming precisely what remains outstanding (the FRESH-basis confirmation itself) rather than rounding up to a full MET.

## Deviations from Plan

### Auto-fixed Issues

None — no Rule 1/2/3 auto-fixes were required; both prose fixes below were caught during this plan's own first verify attempts, before any commit, rather than discovered as regressions.

### Verify-script defect (documented, no code fix required)

**1. [Same defect class as `.planning/WINDOWS.md` ids 2-3] Task 2's own `D05_SECTION_OK` doc-verify script's `##+ ` section-boundary split also matches `### ` subsection headings**
- **Found during:** Task 2, first attempt at verifying the Integration readiness plan section
- **Issue:** The script computes the section's own body via `sec = re.split(r'^##+\s+', sec, flags=re.M)[0]`, meant to stop at the next TOP-LEVEL `## ` heading — but `r'^##+\s+'` (2-or-more hashes) also matches this section's own `### ` subsection headings, truncating `sec` at the FIRST subsection (confirmed directly: the literal script measured 64 words and 0 subsections for a section that, under the correct boundary, is 3,971 words with 12 subsections). The SAME assertions the script then runs (`words >= 1200`, `len(subs) >= 11`) are therefore mutually unsatisfiable for any document using `### ` subsections, which Task 2's own `<action>` text explicitly asks for ("Seven outline subsections").
- **Fix:** Did not modify PLAN.md (out of this plan's own file scope). Verified the document's actual, substantive correctness using the evidently-intended outer boundary `r'^##(?!#)\s+'` (stops only at a true level-2 heading, never matching `### `), which passed cleanly (3,971 words, 12 subsections, 33 table rows, every required content pattern present). Logged as `.planning/WINDOWS.md` id 4, a new instance of the same recurring defect class already open for ids 2-3.
- **Files modified:** None (diagnosis of the plan's own verify-script text, not a code change).
- **Verification:** Ran both the literal (buggy) script and the corrected one side-by-side; the corrected one's output is reproduced above.
- **Committed in:** Documented in `ccf8238`'s commit message; WINDOWS.md id 4 committed in `ccf8238`.

**2. [Rule 1 - prose, not substance] Two of my own sentences in the Integration readiness plan tripped the section's own banned-phrase/placeholder checks**
- **Found during:** Task 2, live verify
- **Issue:** The opening sentence of "The minimum data contract" originally read `"we need better data" is not a data contract`, which literally contains the forbidden phrase `better data` even though used as a negated example (the same banned-phrase-in-negation trap Plan 04-04 hit for "safety margin"). Separately, a later sentence read `none is a placeholder`, which the document-wide leftover-placeholder scan (`re.findall(r'.*placeholder.*', text, re.I)`) flags regardless of context.
- **Fix:** Reworded both sentences to convey the identical meaning without the literal flagged substrings (`a vague instruction to improve the inputs is not a data contract`; `names a real field, never a stand-in to be named later`).
- **Files modified:** `docs/data-science/decisions/forecast_correction_followup_audit.md`
- **Verification:** Re-ran `D05_SECTION_OK` (corrected regex) and `AUDIT_RECORD_COMPLETE_OK` — both pass.
- **Committed in:** `ccf8238` (Task 2 commit)

---

**Total deviations:** 0 auto-fixed code changes; 1 documented verify-script defect (same recurring class as WINDOWS.md ids 2-3, logged as id 4) and 2 prose rewordings caught before commit, neither changing this plan's own substantive deliverables.
**Impact on plan:** None of this plan's own D-05 content was weakened or narrowed by these fixes — only the literal phrasing was adjusted to match the verify scripts' own patterns, or the verify script's own boundary defect was independently worked around per established project precedent.

## Issues Encountered

- **Worktree was forked before Plans 04-01 through 04-05's own merges landed on `main`.** This worktree's branch was created at `04a679b` (the phase-04 planning commit). Confirmed clean, non-divergent ancestry (merge-base equalled worktree HEAD, clean tree, zero local commits ahead of `main`) and fast-forward-merged `main` (through `a4f7ab7`) before starting Task 1, per this session's explicit instructions and mirroring the documented precedent every prior Phase 4 plan has followed.
- **`.venv` and `data/experiment/` do not exist in a fresh worktree** (both gitignored, per-worktree working-directory state). Symlinked `.venv` to the main checkout's `.venv` (untracked, mirroring every prior Phase 4 plan's own documented precedent) and regenerated `data/experiment/audit_basis_manifest.json` plus both corridors' `audit_ablation_report_<CORRIDOR>.json` via a live network fetch before Task 1 began, per Task 1's own stated precondition ("that path is cached and idempotent") — reproduced the exact same measured ABLATION basis (784 validation rows/corridor, `test_start=2026-03-17` matching for both corridors) every prior Phase 4 plan already measured.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

Phase 4 is complete (6/6 plans). The frozen record's own Open Question about the refit model's reversal is answered with a measurement rather than deferred a second time; the cooling-rediscovery hypothesis is tested with a correlation and a number attached, not asserted; both `ml_cooling_corrected` and `reference_ml_refit_24h` remain live candidates per the Corrected verdict and this plan's own Integration readiness section; and a concrete, field-level integration-readiness plan exists for whoever picks up the next phase, without building any part of the integration itself.

**For a future integration phase:** the data contract's `availability_timestamp` field is the single highest-leverage item — it is the only field that closes D-01 Finding 4's own central gap (archive-to-archive comparison can never evidence real-time dissemination), and every "blocked on contract" recommendation in this plan's now-versus-later split depends on it either directly or via the local-observation fields it parallels. The horizon product question (60-minute vs. 24-hour vs. both) remains genuinely unresolved and is assigned to whoever owns product scope — not to this workstream's own next phase by default.

No blockers for Phase 4's closure. Milestone v1.3 (Phases 1-4, all complete) is ready for `/gsd-complete-milestone` or equivalent next-step routing.

---
*Phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan*
*Completed: 2026-10-01*
