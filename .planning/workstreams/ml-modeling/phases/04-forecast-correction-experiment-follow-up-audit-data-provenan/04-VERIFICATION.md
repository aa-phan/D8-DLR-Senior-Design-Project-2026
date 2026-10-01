---
phase: 04-forecast-correction-experiment-follow-up-audit-data-provenan
verified: 2026-10-01T00:00:00Z
status: passed
score: 7/7 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 4: Forecast Correction Follow-up Audit Verification Report

**Phase Goal:** An adversarial, independent follow-up audit of Phase 3's frozen decision record
answers whether `ml_cooling_corrected` or the refit `reference_ml_refit_24h` model actually warrants
production integration — auditing data provenance/leakage, strengthening the statistical comparison
beyond "beats persistence," quantifying conservative-rating/overrating behavior, correcting any
overstated language in the original record, and producing a concrete integration-readiness plan. The
phase must NOT replace the production model and must NOT re-run or re-score the original held-out
test set.

**Verified:** 2026-10-01
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth (D-01 through D-05, CONTEXT.md locked scope) | Status | Evidence |
|---|---|---|---|
| 1 | D-01: Data provenance and leakage are independently re-audited against code, not the report's self-description | ✓ VERIFIED | `backend/forecast_experiment_audit.py` exports `truth_provenance_finding`, `decision_time_availability_finding`, `frame_time_reference_groups`, `leakage_probe_coverage_report`, `arm5_label_timing_finding`, `split_boundary_audit`, `arm5_lag_offset_finding`, `d01_findings_table` — all 9 findings are measured (not asserted) with `file:line` citations. Audit record's `## Data provenance re-audit (D-01)` section (lines 78-459) carries a 5-row dispositions table closing all five CONTEXT.md D-01 bullets. 105/105 audit tests pass, exercising each finding. |
| 2 | D-02: Comparison strengthened — block-bootstrap with block-length sensitivity, direct pairwise comparison (not just vs. persistence), MAE+RMSE at both corridors, multiple-comparisons acknowledgment, fresh-period reservation | ✓ VERIFIED | `paired_block_bootstrap_margin`/`block_length_sensitivity` proven to reduce to i.i.d. at block length 1 (test-verified); `ablation_basis_report`'s `pairwise` dict computes every candidate against persistence/raw_forecast/ml_wind_corrected/reference_ml_refit_24h directly (confirmed in published `## Strengthened comparison (D-02)` section, lines 460-608, with a direct-pairwise table at line 523+). A fresh chronological period is formally reserved (starts 2026-09-30, min 56 rows/14 days) and measured at 0 rows — honestly reported, not fabricated. |
| 3 | D-03: Conservative-rating analysis — overrating frequency/magnitude/duration by regime (incl. low-wind), calibrated lower quantiles with disjoint calibration/eval periods, matched-overrating-rate retained capacity, reanalysis-scope limitation stated | ✓ VERIFIED | `overrating_profile`, `convection_crossover_wind_speed`, `overrating_by_regime`, `quantile_period_boundaries`, `fit_lower_quantile_model`, `quantile_calibration_report`, `retained_capacity_at_matched_overrating` all present and test-covered. Published `## Conservative-rating analysis (D-03)` section (609-824) opens with the reanalysis-scope limitation before any number, states three chronologically disjoint fit/calibrate/evaluate periods, and reports a matched-5%-rate retained-capacity headline table. |
| 4 | D-04: Overstated conclusions corrected — lowest-observed-MAE framing (not established/unique winner), 30A/CI-lower-bound honesty, oracle-as-diagnostic, headroom vs. raw_forecast not persistence, 1-hour exclusion reaffirmed, low-wind-sensitivity-vs-instability distinguished | ✓ VERIFIED | Frozen record `forecast_correction_experiment.md` carries one append-only, byte-identity-gated `## Follow-up Audit Amendment (Phase 4, D-04)` section (246 added lines, 0 deleted; `## Expectation` and `## Measured results` sections independently confirmed byte-identical pre/post). `low_wind_sensitivity_sweep`/`sensitivity_vs_instability_finding`/`reverify_convective_seam_bit_identity` measure (not assert) that the low-wind response is a physics floor, independently re-verified against the committed golden fixture. No "established winner"/"universal ceiling" language found in the audit record (grepped). |
| 5 | D-05: Integration-readiness plan — both candidates kept live with ablation investigating the refit MLP, minimum data contract named field-by-field, now-vs-later split, packaging/fallback/monitoring/rollback outlined (not built), 60-min-vs-24h product question left explicitly open | ✓ VERIFIED | `lag_vs_covariate_ablation`/`cooling_rediscovery_hypothesis` present and tested; published `## Integration readiness plan (D-05)` section (1046-1326) names a 19-field data contract with 3 distinct timestamps, a now-vs-blocked split of 12 recommendations, a 7-part packaging/fetch/fallback/shadow-eval/monitoring/rollback outline, and leaves the 60-min-vs-24h question explicitly open and assigned to product scope. |
| 6 | Zero diff on every frozen production module and Phase 3 planning artifact (additive-only discipline) | ✓ VERIFIED | `git diff --stat 04a679b -- <13 frozen modules + corridor_discretization.py + Phase 3 planning dir>` returns only a harmless pre-existing `.gitkeep` placeholder added by a planning-setup commit (215b2df, "docs(phase-4): add validation strategy") inside the Phase 3 directory — no content of any frozen module or Phase 3 artifact changed. |
| 7 | Audit tests pass; full suite shows only the known pre-existing 23 `corridor_discretization_test.py` failures, no new failures | ✓ VERIFIED | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_audit_test.py` → 105 passed, 0 failed. `.venv/bin/python3 -m pytest -q` (full suite) → 746 passed, 23 failed, all 23 failures confined to `backend/tests/corridor_discretization_test.py` (matches the documented Phase 3 baseline in `WINDOWS.md` id 1 and `03-.../deferred-items.md`). |

**Score:** 7/7 truths verified (0 present-but-behavior-unverified)

### Most Important Substantive Finding (explicitly requested for this report)

Plan 04-03's real-data, out-of-sample (ABLATION-basis) block-bootstrap replication of Phase 3's
candidate comparison **does not replicate** the frozen record's stated winner at
MIDLAND_EL_PASO: `ml_wind_corrected` now has the lowest point MAE (127.129 vs. cooling's 132.239
and the refit model's 135.547), and `ml_cooling_corrected`'s margin over `reference_ml_refit_24h`
(3.308 A, 95% CI [-2.667, 9.055]) is statistically indistinguishable from zero — where the frozen
record reported a distinguishable edge at this exact pair. A related margin
(`ml_wind_corrected` vs. `reference_ml_refit_24h`) excludes zero only at block length 1 and flips to
not-excluding-zero at block lengths 4/8/28, demonstrating the frozen record's own BCa interval for
this margin (CI low 0.036) was already fragile before accounting for serial correlation.
AUSTIN_CORPUS_CHRISTI, by contrast, cleanly replicates the frozen record's candidate ordering and is
stable across every block length tried.

Plan 04-05 then amended the frozen record accordingly: the Midland finding is cited in the
appended, byte-identity-gated `## Follow-up Audit Amendment (Phase 4, D-04)` section (item 2, the
30A/CI-lower-bound item), and the audit record's own `## Corrected verdict` states the recommendation
explicitly conditions on this disagreement — keep both candidates live at low-to-moderate confidence,
rather than endorsing `ml_cooling_corrected` as settled, specifically because Midland's real-data
replication contradicts rather than corroborates the frozen record's ordering. This is the correct,
honest handling of a genuinely adverse finding: it was not softened, buried, or excluded — it is
named as "the phase's single most important finding" in the audit record's own prose (line 486) and
drives the corrected verdict's confidence level.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/forecast_experiment_audit.py` | Standalone, additive audit module with ~26 exported analysis functions | ✓ VERIFIED | 4,708 lines; all claimed symbols present except `pairwise_margin_table` by that exact name (see note below); no TODO/FIXME/XXX/placeholder markers found. |
| `backend/tests/forecast_experiment_audit_test.py` | Network-free unit tests covering every function | ✓ VERIFIED | 2,025 lines, 105 passing tests, no network imports or fetch monkeypatches found. |
| `docs/data-science/decisions/forecast_correction_followup_audit.md` | 10-section audit record, no remaining placeholders | ✓ VERIFIED | 1,400 lines, all 10 section headings present (`What was audited` through `References`), zero placeholder/TODO/TBD/FIXME markers found via grep. |
| `docs/data-science/decisions/forecast_correction_experiment.md` (frozen record amendment) | Append-only, Expectation/Measured-results byte-identical | ✓ VERIFIED | 246 lines added, 0 removed; both locked sections independently verified byte-for-byte identical to the pre-phase commit. |
| `.planning/workstreams/ml-modeling/ROADMAP.md` Phase 4 entry | 5 success criteria each with an honest disposition | ✓ VERIFIED | 4 criteria MET, 1 (fresh-holdout confirmation) honestly marked MET IN PART with the exact gap named (FRESH row count = 0, reservation not an executed confirmation). |
| `.planning/WINDOWS.md` | 4 open items, characterized as planning-doc defects, not implementation bugs | ✓ VERIFIED | See dedicated section below. |

**Note on `pairwise_margin_table`:** 04-RESEARCH.md's Architecture Patterns section anticipated this
as a standalone function name; the actual implementation folds direct-pairwise computation into
`ablation_basis_report`'s own `pairwise` dict (built via the `_margin_entry` helper), which is what
the published `## Strengthened comparison (D-02)` section's "Direct pairwise comparison" table
(line 523) is sourced from. This is a research-stage naming difference, not a missing capability —
the functional requirement (direct pairwise comparison, not just vs. persistence) is delivered and
verified present in the published document.

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `forecast_experiment_audit.py` | `forecast_experiment.py` | imports assembly/scoring helpers, never invokes `_run_corridor`/`_run_city_tracer`/`main` | ✓ WIRED | Confirmed by reading module docstring and grepping for runner-entry-point calls — none found; SUMMARY.md's for 04-01/04-02 document the explicit avoidance and the workaround for `calendar_split`'s min-rows floor. |
| `forecast_experiment_audit.py` | `experiment_splits.py` | all new calendar boundaries use `SplitBoundaries`/`calendar_split` | ✓ WIRED | `quantile_period_boundaries`, `build_basis_manifest`'s ABLATION/FRESH assembly, and `rederive_frozen_split_boundaries` all documented and tested as using this module. |
| `forecast_experiment_audit.py` measured numbers | `forecast_correction_followup_audit.md` prose | hand-transcription from git-ignored JSON reports into cited tables | ✓ WIRED | Numbers appearing in the published document (e.g. Midland's 127.129/132.239/135.547 MAE figures) match the specific values described in 04-03-SUMMARY.md's own accomplishments section — consistent across the independent sources. |
| Frozen-test-window guard | Every ABLATION/FRESH basis assembly | `assert_basis_excludes_frozen_test_rows` called before any fit/score | ✓ WIRED | Guard function unit-tested (raises on frozen-window row, raises on FRESH basis with pre-window row, returns zero-row summary on empty frame) — all three behaviors independently confirmed passing in the 105-test run. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Frozen-window guard raises on a row inside the frozen test window | `PYTHONPATH=backend python3 -c "..."` style check embedded in 04-01-PLAN's own verify script, re-run via the committed test suite | `test_frozen_window_guard*` tests pass | ✓ PASS (via test suite, not re-run standalone — see Probe Execution below for the actual commands run this session) |
| Full suite isolates new failures from the known Phase 3 baseline | `.venv/bin/python3 -m pytest -q` | 746 passed, 23 failed (all in `corridor_discretization_test.py`) | ✓ PASS |
| Audit-only test file is fully green | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_audit_test.py` | 105 passed, 0 failed | ✓ PASS |

### Probe Execution

No dedicated `scripts/*/tests/probe-*.sh` convention applies to this phase (it is a backend/pytest
phase, not a migration/CLI-tooling phase). The phase's own verification mechanism is its pytest
suite, run directly above (not simulated, not narrated from SUMMARY.md):

| Probe | Command | Result | Status |
|---|---|---|---|
| Audit test file | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_audit_test.py` | `105 passed in 22.20s` | PASS |
| Full backend suite | `.venv/bin/python3 -m pytest -q` | `23 failed, 746 passed, 67 warnings in 61.63s` (all 23 failures in `corridor_discretization_test.py`) | PASS (matches documented baseline) |
| Frozen-module zero-diff | `git diff --stat 04a679b -- backend/thermal_model.py backend/forecast_experiment.py backend/forecast_correction_models.py backend/forecast_training.py backend/ampacity_forecast.py backend/anomaly_detector.py backend/DLRSafetyMonitor.py backend/open_meteo_provider.py backend/open_meteo_forecast_provider.py backend/forecast_leadtime_calibration.py backend/experiment_splits.py backend/corridor_discretization.py .planning/workstreams/ml-modeling/phases/03-ampacity-forecast-correction-experiment-compare-persistence/` | 1 file changed (`.gitkeep`, 1 insertion — a planning-setup placeholder, not Phase 3 content) | PASS |
| Frozen record append-only | `git diff 04a679b -- docs/data-science/decisions/forecast_correction_experiment.md` + a byte-identity script comparing the `## Expectation` and `## Measured results` sections pre/post | 246 insertions, 0 deletions; both locked sections byte-identical | PASS |

### Requirements Coverage

This phase declares no formal requirement IDs (mirroring Phase 3's own convention — FCST-01/02 and
ANOM-01/02 are already Complete against Phases 1/2). The five locked decisions D-01 through D-05
substitute for requirement IDs.

| Decision | Description | Status | Evidence |
|---|---|---|---|
| D-01 | Data provenance and leakage independently re-audited | ✓ SATISFIED | 9 cited findings, 5-row dispositions table, 105 passing tests |
| D-02 | Comparison strengthened (block bootstrap, direct pairwise, MAE+RMSE, fresh-period reservation) | ✓ SATISFIED (with honest partial disposition on fresh-confirmation execution) | Published section + ROADMAP's own "MET IN PART" disposition for the fresh-confirmation half |
| D-03 | Conservative-rating/overrating analysis, calibrated quantiles, matched-rate retained capacity | ✓ SATISFIED | Published section, 3-period chronological disjointness tested |
| D-04 | Overstated conclusions corrected via append-only amendment | ✓ SATISFIED | Byte-identity-gated amendment, banned-phrase grep clean |
| D-05 | Integration-readiness plan (data contract, now-vs-later, outline, open product question) | ✓ SATISFIED | Published section, 19-field contract, horizon question explicitly open |

No orphaned requirements found (no requirement IDs map to this phase beyond the five D-0N decisions,
all of which are covered).

### Anti-Patterns Found

No blocker-level anti-patterns found in files modified by this phase.

- `grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER|not yet implemented"` on `backend/forecast_experiment_audit.py`: zero matches.
- `grep -ni "placeholder|TBD|TODO|FIXME|coming soon|not yet implemented"` on `docs/data-science/decisions/forecast_correction_followup_audit.md`: zero matches — all 10 sections are substantively filled, no leftover filler text from the skeleton Plan 04-01 created.
- `backend/tests/forecast_experiment_audit_test.py` contains no network import or fetch monkeypatch, consistent with its own stated network-free guarantee.

### `.planning/WINDOWS.md` Open Items (4 total) — Characterization Check

The task asked me to confirm that all 4 open WINDOWS.md items are documented planning-doc defects in
embedded `<verify>` literals, not implementation bugs. Independently reviewed each entry:

| id | Phase | Description | Characterization confirmed? |
|---|---|---|---|
| 1 | 03 | 23 pre-existing `corridor_discretization_test.py` failures, reproducible in isolation on the Phase 3 base commit, unrelated to any file Phase 3 or Phase 4 touches | Confirmed — this is Phase 3's pre-existing baseline, not a Phase 4 defect at all; independently reproduced this session (full suite shows exactly 23 failures, all in this one file). |
| 2 | 04 | Plan 04-02's own Task 1-3 doc-verify scripts use a self-contradicting section-boundary regex (`r'^##+ '` also matches the required `r'^###+ '` subsection markers) | Confirmed — this is a defect in the PLAN.md's embedded `<verify>` literal regex, not in `forecast_experiment_audit.py` or the audit record itself. SUMMARY.md documents the corrected regex (`r'^## '` / `r'##(?!#) '`) was used to independently re-verify substantive intent, and all checks passed under the corrected regex. |
| 3 | 04 | Plan 04-04 Task 1's own `<verify>` literal for `overrating_profile` hand-computes an incorrect expected result (count==6 vs. the mathematically correct 7) | Confirmed — this is an arithmetic error in the PLAN.md's embedded verify literal, not in the implementation. The actual implementation matches the mathematically correct value (7), proven by the executor's own `test_overrating_profile_matches_hand_computation`, part of the passing 86-test suite at that point. Same root-cause family as id 2 (embedded verify-literal defects), though this specific instance is a hand-computation error rather than a regex defect. |
| 4 | 04 | Plan 04-06 Task 2's own `D05_SECTION_OK` doc-verify script uses the same self-contradicting regex already logged as ids 2-3 | Confirmed — same regex-boundary defect class as id 2, in a different plan's embedded verify literal. Corrected-boundary re-verification (3,971 words, 12 subsections, 33 table rows) passed. |

**Verdict on the WINDOWS.md characterization:** Holds. All 4 items are either (a) Phase 3's own
pre-existing, out-of-scope test baseline (id 1), or (b) defects in the planning documents' own
embedded `<verify>` shell-script literals (ids 2-4: a recurring self-contradicting regex, plus one
arithmetic slip in a hand-computed expected value) — never defects in the executed implementation
code. In every one of ids 2-4, the executor independently re-derived the correct check and confirmed
the substantive requirement was actually met; no implementation code was changed or excused because
of these items. These remain open (not fixed, not waived) per the ledger's own convention, and are
correctly non-blocking for this phase's goal achievement — they are accounted for here as requested,
not silently dropped.

### Human Verification Required

None outstanding. The phase's own coverage tables (04-01 D3/D5, 04-03 D3, 04-04 D5, 04-05 D4, 04-06
D3/D4) flag six prose-framing judgment calls (e.g. Midland "contradicted" vs. a softer alternative,
the corrected verdict's "low-to-moderate confidence," the matched-rate headline framing, the data
contract's practical implementability) as items that needed human judgment rather than automated
word/regex/table checks alone. Each of these was already resolved by an explicit human checkpoint at
execution time (Plan 04-01's Task 3 checkpoint, Plan 04-03's Task 2.5 checkpoint, and the
`human_judgment: true` / `rationale: ... approved` entries in the respective SUMMARY.md files). This
verification independently re-read the underlying numbers each framing claim rests on (e.g. Midland's
127.129/132.239/135.547 MAE figures and the 3.308 A, CI [-2.667, 9.055] margin backing the
"contradicted" framing) and confirms the language used does not overstate what the measured numbers
support. No further human sign-off is required for this verification pass.

### Gaps Summary

No gaps found. All 5 locked decisions (D-01 through D-05) are genuinely delivered with code-grounded,
test-verified, or measurement-backed evidence — not report-paraphrasing. The one partial disposition
(D-02's fresh-chronological-holdout confirmation, ROADMAP's own "MET IN PART") is an honest,
correctly-labeled limitation driven by calendar time (today's date equals the frozen window's end),
not a quality defect in the phase's own work — the reservation mechanism is built, tested, and
enforced disjoint from Phase 3's splits; only the confirmation run itself awaits ~2 more weeks of
calendar time to accrue a meaningful row count, and the phase correctly refuses to claim that
confirmation prematurely. The phase's single most important substantive finding — Midland-El Paso's
candidate ordering is contradicted, not corroborated, by real out-of-sample data — was surfaced
prominently rather than buried, and the frozen record was correctly amended (append-only,
byte-identity-gated) to reflect it. Zero diff confirmed on every frozen production module and every
Phase 3 planning artifact. The full test suite shows no regression beyond the pre-existing,
well-documented 23-failure Phase 3 baseline.

---

_Verified: 2026-10-01_
_Verifier: Claude (gsd-verifier)_
