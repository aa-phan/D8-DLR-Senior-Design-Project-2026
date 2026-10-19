---
phase: 03-ampacity-forecast-correction-experiment-compare-persistence
plan: 06
subsystem: ml-modeling
tags: [forecast-experiment, leakage-probe, wind-correction, cooling-correction, mlp-regressor, no-peeking-lock, paired-bootstrap, held-out-test-set, checkpoint-decision]

# Dependency graph
requires:
  - phase: 03 (plans 03, 04, 05)
    provides: "The lead_hours-generalized anchored-pair-frame contract and NON_FITTED_ARMS registry (03-03/03-04), and the wind/cooling correction families plus build_training_matrix's horizon_minutes seam (03-05) this plan wires together and scores once on held-out test rows."
provides:
  - "docs/data-science/decisions/forecast_correction_experiment.md: the Expectation section (committed in an isolated two-file commit predating every test read) PLUS the Measured results section, transcribed verbatim from the single held-out test-set run -- both corridors' full candidate tables (MAE/RMSE/margin vs. persistence/paired-bootstrap 95% CI/exclusion), the oracle's ceiling, and the 24-hour-lead/strong-baseline qualifiers. Verdict/Limitations/Open Questions remain explicit Plan 03-07 placeholders."
  - "backend/forecast_experiment.py: ALL_ARMS (the seven-arm registry), fit_fitted_arms, leakage_probe (Tasks 1-2, unchanged this session), PLUS Task 3's paired_bootstrap_margin, score_arms'/corridor_experiment_report's additive baseline_name parameter, _resolve_verdict, and the corridor-level split==\"test\" path (_score_fitted_arms_at_corridor_level) that fits arms 3/4/5 once on train+val and scores all seven ALL_ARMS entries on one byte-identical held-out test row index."
affects: ["03-07"]

# Actuals (#2632)
actuals:
  tokens: 10896
  tasks: 1
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Paired bootstrap on the DIFFERENCE series, not two independently resampled series: paired_bootstrap_margin resamples |errors_baseline| - |errors_arm| as a single statistic via scipy.stats.bootstrap(BCa), preserving the real pairing an identical scored row index provides rather than discarding it and widening every interval for no reason."
    - "A degenerate-data fast path ahead of a library call known to misbehave on it: paired_bootstrap_margin short-circuits a zero-variance difference series (baseline scored against itself, or any two bit-identical arms) to a zero-width interval at the point value, since scipy.stats.bootstrap's default BCa method empirically returns NaN bounds on constant data (confirmed by direct measurement in this session, not assumed) rather than the mathematically correct degenerate answer."
    - "Additive, default-None parameters threaded through two existing functions (score_arms's baseline_name, corridor_experiment_report's baseline_name) to add margin/verdict reporting without changing either function's byte-identical behavior for any pre-existing caller -- the same discipline forecast_training.build_training_matrix's horizon_minutes parameter (Plan 03-05) established for this phase."
    - "A CORRIDOR-LEVEL prediction column injected into an already-corridor-reduced frame, rather than re-deriving corridor_anchored_pair_frame's per-arm reduction a second time: _score_fitted_arms_at_corridor_level computes arms 3/4's per-city corrected ampacity independently, reduces it through the SAME forecast_training.corridor_weakest_link helper the four non-fitted arms already use, and merges the result onto scored_frame by explicit datetime_utc reindex (never positional concatenation) -- so _corridor_arm_reader can read all seven ALL_ARMS entries uniformly and score_arms's identical-index assertion holds by construction."
    - "Arm 5's SCORING features are rebuilt from the FULL train+val+test window (never just train+val), while its FITTED ESTIMATOR came from train+val only: a fresh build_training_matrix pass over the whole window is needed so lag features exist at the test split's own anchor times, and this is not a leak because every scored row's own features are built from truth values strictly before that row's own valid time, and the estimator's learned weights never saw an excluded row during fitting."
    - "A split-conditional code path inside one function, not two duplicated functions: _run_corridor's split==\"test\" branch is the ONLY place fit_fitted_arms/_score_fitted_arms_at_corridor_level are invoked; split==\"val\" is byte-identical to Plan 03-04's original four-non-fitted-arm path (no margin_vs_persistence, no verdict, unchanged report filename) -- preserving the exact path Plans 03-04/03-05's own validation-split numbers were produced by, verified by re-running the pre-existing test that asserts 3 candidates on that path."

key-files:
  created: []
  modified:
    - docs/data-science/decisions/forecast_correction_experiment.md
    - backend/forecast_experiment.py
    - backend/tests/forecast_experiment_test.py

key-decisions:
  - "CHECKPOINT RESOLVED: proceed. The orchestrator and the user independently confirmed, before spawning this continuation, that all three of the checkpoint's preconditions held -- the Expectation commit (4d964cf) is isolated and predates every test read, the leakage probe (2ad9971) has demonstrated power against a deliberately sabotaged arm, and arms 3/4's configurations are Plan 03-05's validation-selected values passed in as fixed arguments, never re-selected with the test answer visible. The user then explicitly authorized crossing into the held-out test set. This session did not re-litigate that decision -- it executed Task 3 as specified."
  - "score_arms/corridor_experiment_report's margin/verdict machinery is threaded through an ADDITIVE, default-None baseline_name parameter rather than a new sibling function, so every pre-existing caller (the val-split path, the --city tracer path, every Task 1/2 test) is byte-identical to before this session -- verified by re-running the full pre-existing 70-test file unchanged plus a new guard test (test_main_at_val_split_still_scores_only_non_fitted_arms_unchanged) that explicitly asserts the val path still produces exactly 3 candidates with no margin/verdict keys."
  - "The corridor-level TEST-split wiring (fit_fitted_arms + arms 3/4/5's corridor-level scoring) is gated behind `if split == \"test\"` inside _run_corridor, rather than made unconditional for both splits. Plans 03-04/03-05's own validation-split MAE numbers, already cited in this record's Configuration measured section, were produced by the ORIGINAL four-non-fitted-arm val path -- making the wiring unconditional would have silently changed that historical reproduction path's report shape and row scope. Reusing the identical wiring for val-split diagnostics is deferred, not needed by this plan's own scope."
  - "paired_bootstrap_margin reuses config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE (this phase's one existing fixed seed) rather than introducing a second bootstrap-specific seed constant, since this task's own <read_first> instructed reading config.py's bootstrap settings without editing that module, and no bootstrap-specific seed constant already exists there."
  - "The test-split JSON report is written to a SPLIT-SUFFIXED filename (experiment_report_{corridor}_test.json), distinct from the val-split's pre-existing bare filename (experiment_report_{corridor}.json) -- so a test-set run can never silently overwrite, or be mistaken for, the validation-split report the decision record's Configuration measured section already cites."
  - "Test set scored EXACTLY ONCE. The single invocation (both corridors, primary 24-hour lead) produced finite, physically plausible numbers on the first attempt -- no exception, no empty split, no negative ampacity -- so no defect-fix re-run was needed, and no arm/feature/hyperparameter/filter was adjusted after seeing the output. This is documented explicitly in the decision record's Measured results section, per the plan's own prohibition against re-running test-set scoring while tuning."

patterns-established:
  - "A record's headline finding stated plainly even when it contradicts the record's own pre-registered Expectation: the Expectation predicted raw_forecast would win with a small margin and that the refit reference arm would underperform persistence; the measured result was that ml_cooling_corrected had the largest statistically-distinguishable margin at both corridors, and the refit reference arm BEAT persistence distinguishably at both corridors too -- transcribed as measured, with zero editorializing in the Measured results section (interpretation is explicitly deferred to Plan 03-07's Verdict)."

requirements-completed: [D-02, D-03, D-04]

coverage:
  - id: D1
    description: "The Expectation section of the decision record is committed in an isolated two-file commit (the record plus the test-split lock flip) containing no scoring run and no arm implementation -- git log is the audit trail, not a document's self-reported date (Task 1, unchanged this session)"
    requirement: D-02
    verification:
      - kind: other
        ref: "git log -1 --name-only on commit 4d964cf: exactly docs/data-science/decisions/forecast_correction_experiment.md and backend/forecast_experiment.py (EXPECTATION_COMMIT_OK)"
        status: pass
      - kind: unit
        ref: "PYTHONPATH=backend .venv/bin/python3 -c \"import forecast_experiment as fe; fe._require_test_split_unlocked()\" (TEST_SPLIT_UNLOCKED_OK)"
        status: pass
    human_judgment: false
  - id: D2
    description: "ALL_ARMS is a seven-entry registry containing the oracle; the candidate mapping derived from it (excluding the oracle) has six entries; the leakage probe has demonstrated power against a deliberately sabotaged arm (Task 2, unchanged this session)"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_all_arms_has_exactly_seven_entries_and_contains_oracle, test_leakage_probe_passes_on_real_arms_flags_oracle_and_flags_a_sabotaged_arm"
        status: pass
    human_judgment: false
  - id: D3
    description: "paired_bootstrap_margin computes a paired bootstrap CI on the per-row absolute-error difference series, brackets its own point estimate, correctly reports non-exclusion for a difference series centered on zero, and handles the degenerate baseline-vs-itself case without NaN bounds"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_paired_bootstrap_margin_bounds_bracket_the_point_and_favor_the_better_arm, test_paired_bootstrap_margin_reports_non_exclusion_for_difference_centered_on_zero, test_paired_bootstrap_margin_degenerate_self_comparison_is_zero_width_at_zero, test_paired_bootstrap_margin_raises_on_shape_mismatch"
        status: pass
    human_judgment: false
  - id: D4
    description: "score_arms's additive baseline_name parameter attaches margin_vs_persistence to every candidate including the baseline's own trivial entry, without changing any pre-existing caller's output when omitted; corridor_experiment_report's additive baseline_name parameter attaches a three-valued verdict field (single winner / no-candidate-beat-persistence / multiple-candidates-resolved-by-largest-margin)"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_score_arms_with_baseline_name_attaches_margin_to_every_candidate_including_baseline, test_score_arms_raises_when_baseline_name_not_among_arms, test_score_arms_without_baseline_name_omits_margin_key_unchanged_from_before, test_resolve_verdict_reports_no_candidate_beat_persistence_when_all_straddle_zero, test_resolve_verdict_names_the_single_winner, test_resolve_verdict_names_multiple_and_resolves_by_largest_margin, test_corridor_experiment_report_attaches_verdict_when_baseline_name_given, test_corridor_experiment_report_omits_verdict_when_baseline_name_not_given"
        status: pass
    human_judgment: false
  - id: D5
    description: "The corridor-level split==\"test\" path fits arms 3/4/5 once on the stacked train+val frame (never on test rows) and scores all seven ALL_ARMS entries on one byte-identical row index with every candidate carrying a bracketing margin_vs_persistence interval and the report carrying a non-empty verdict; the split==\"val\" path is unchanged (three non-fitted candidates, no margin/verdict keys)"
    requirement: D-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_experiment_test.py::test_main_at_test_split_wires_all_seven_arms_with_margins_and_verdict, test_main_at_val_split_still_scores_only_non_fitted_arms_unchanged"
        status: pass
    human_judgment: false
  - id: D6
    description: "All seven arms scored ONCE on held-out test rows for both corridors on a byte-identical index at the verified 24-hour lead -- the phase's one irreversible step, executed after explicit checkpoint authorization"
    requirement: D-02
    verification:
      - kind: other
        ref: "PYTHONPATH=backend .venv/bin/python3 backend/forecast_experiment.py --lead-hours 24 --split test (live run, both corridors) -> TEST_SET_RUN_OK (6 candidates, oracle excluded, identical row counts, every margin bracketed, non-empty verdict, measured_lead_hours==24, split=='test')"
        status: pass
    human_judgment: false
  - id: D7
    description: "The Measured results section of the decision record contains both corridors' transcribed tables with the oracle, the 24-hour lead stated, and the caveat/qualifier beneath them; Verdict/Limitations/Open Questions remain explicit Plan 03-07 placeholders; the decision record's first commit is still the isolated Expectation-plus-unlock commit"
    requirement: D-02
    verification:
      - kind: other
        ref: "MEASURED_TRANSCRIBED_OK and NO_PEEKING_AUDIT_OK verify scripts from 03-06-PLAN.md Task 3, both pass against the committed record"
        status: pass
    human_judgment: false
  - id: D8
    description: "No observable behavior of any existing runtime module changed (D-03); zero diff on backend/ampacity_forecast.py, backend/anomaly_detector.py, backend/DLRSafetyMonitor.py, backend/config.py from this plan's base commit"
    requirement: D-03
    verification:
      - kind: other
        ref: "git diff --name-only c043c17 -- backend/ampacity_forecast.py backend/anomaly_detector.py backend/DLRSafetyMonitor.py backend/config.py -> empty"
        status: pass
    human_judgment: false

duration: ~35min (Task 3 only -- code, live run, transcription)
completed: 2026-09-30
status: complete
---

# Phase 3 Plan 6: Expectation Commit, Fitted-Arm Wiring, Power-Tested Leakage Probe, and the Single Held-Out Test-Set Run Summary

**Ran the phase's one irreversible step -- scoring all seven arms once on held-out test rows for both corridors at the verified 24-hour lead, with paired bootstrap confidence intervals on every margin against persistence -- after the checkpoint's three preconditions were independently verified and the user explicitly authorized proceeding; the measured result contradicts the pre-registered Expectation (`ml_cooling_corrected` wins distinguishably at both corridors, and the refit reference arm beats persistence rather than losing to it as Phase 1's 60-minute result predicted), and is transcribed into the decision record exactly as measured.**

## Performance

- **Duration:** ~35 min (Task 3 only: `paired_bootstrap_margin`/verdict-resolution/corridor-level test-split wiring, 14 new tests, the one live network run, and transcription -- Tasks 1-2 were completed and committed in a prior session, see below)
- **Completed:** 2026-09-30
- **Tasks:** 3 of 3 (all tasks and the checkpoint now resolved)
- **Files modified:** 3 (0 created, 3 modified this session; the decision record was created in the prior session's Task 1)

## Accomplishments

- **Tasks 1-2 (prior session, unchanged this session).** The Expectation section of `docs/data-science/decisions/forecast_correction_experiment.md` was committed in the same isolated two-file commit (`4d964cf`) that unlocked the held-out test split; arms 3 (`ml_wind_corrected`), 4 (`ml_cooling_corrected`) and 5 (`reference_ml_refit_24h`) were wired into a seven-entry `ALL_ARMS` registry (`2ad9971`); a leakage probe was built and power-tested against a deliberately sabotaged arm. This session verified all of that work is intact (`git log --oneline` shows all four prior commits; the full pre-existing 70-test file still passes unchanged) before proceeding.
- **Checkpoint resolved: proceed.** The orchestrator and the user independently re-verified the checkpoint's three preconditions (Expectation commit isolated and prior, leakage probe demonstrably powerful, arm configurations fixed from Plan 03-05's validation selection) and explicitly authorized crossing into the test set. This session executed Task 3 without re-litigating that decision.
- **`paired_bootstrap_margin`.** A paired bootstrap confidence interval (`scipy.stats.bootstrap`, `BCa`, 10,000 resamples, `config.FORECAST_EXPERIMENT_BOOTSTRAP_CONFIDENCE`=0.95, fixed seed `config.FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE`) on the per-row absolute-error difference between an arm and a baseline, resampling the paired DIFFERENCE series rather than two independent series. Includes a degenerate-data fast path (a zero-variance difference, e.g. the baseline scored against itself) that returns a zero-width interval at the point value directly, since `scipy`'s `BCa` method was empirically confirmed (this session) to return `NaN` bounds on constant data.
- **`score_arms`/`corridor_experiment_report` extended, additively.** Both functions gained a `baseline_name` parameter, default `None`, byte-identical behavior to before this parameter existed when omitted. When given, `score_arms` attaches `margin_vs_persistence` to every candidate (including the baseline's own trivial entry), and `corridor_experiment_report` attaches a `verdict` field via the new `_resolve_verdict` (one of: `NO_CANDIDATE_BEAT_PERSISTENCE_VERDICT`, a single winner's bare name, or an explicit multiple-candidates string resolved by largest point margin with ties recorded).
- **Corridor-level test-split wiring.** `_run_corridor`'s `split == "test"` branch fits arms 3/4/5 once on the stacked train+val frame (`fit_fitted_arms`, never on test rows) and attaches their corridor-level predictions to the scored frame via the new `_score_fitted_arms_at_corridor_level` (arms 3/4 corrected per-city and weakest-link-reduced through `forecast_training.corridor_weakest_link`; arm 5 scored directly, already corridor-level, from its own from-scratch corridor-reduced-truth feature table rebuilt over the FULL train+val+test window so lag features exist at the test split's own anchor times). The `split == "val"` path is byte-identical to Plan 03-04's original -- verified by a new guard test.
- **The held-out test set, scored once.** `PYTHONPATH=backend .venv/bin/python3 backend/forecast_experiment.py --lead-hours 24 --split test` ran against the live Open-Meteo APIs (no cache existed; the plan's precondition text anticipating a warm cache did not hold in this worktree, so this was a genuine live fetch, not a re-read of a prior run). Both corridors scored 786 test rows (window 2024-01-20 -> 2026-09-29, test split starting 2026-03-17) on a byte-identical index across all six candidates. No exception, no empty split, no negative ampacity -- no re-run was needed, and no arm/feature/hyperparameter/filter was adjusted after seeing the output.
- **Headline finding (measured, not interpreted -- Plan 03-07 writes the Verdict).** `ml_cooling_corrected` had the largest statistically-distinguishable margin at both corridors (+24.86 A AUSTIN_CORPUS_CHRISTI, 95% CI [18.77, 30.78]; +30.67 A MIDLAND_EL_PASO, 95% CI [22.35, 39.11]) -- contradicting the Expectation's prediction that `raw_forecast` would win with only a small margin. The refit reference arm (`reference_ml_refit_24h`) BEAT persistence distinguishably at both corridors (+17.82 A and +30.01 A respectively) -- contradicting the Expectation's prediction, drawn from Phase 1's 60-minute result, that it would underperform. `raw_forecast`'s own margin was small and, at MIDLAND_EL_PASO, not statistically distinguishable from zero (0.41 A, 95% CI [-11.06, 11.83]). The oracle's ceiling was 92.63 A (AUSTIN_CORPUS_CHRISTI) and 145.84 A (MIDLAND_EL_PASO) over persistence -- both far larger than any real candidate's margin, confirming substantial unclaimed headroom remains.
- **Transcribed into the decision record.** Both corridors' full candidate tables (MAE, RMSE, rows, margin vs. persistence, 95% CI, exclusion), each corridor's bottleneck distribution and arm-1 clamp count, and the oracle's ceiling (clearly separated, annotated as a non-forecast diagnostic) are now in the Measured results section, beneath the 24-hour-lead and strong-diurnal-baseline qualifiers. Verdict, Limitations, and Open Questions remain explicit Plan 03-07 placeholders -- this plan pastes the measurement, it does not interpret it.

## Task Commits

Prior session (Tasks 1-2, unchanged, verified intact):
1. **Task 1: Commit the Expectation and unlock the test split** - `4d964cf` (docs)
2. **Fix: re-scope the no-peeking lock tests** (Rule 1, fallout from Task 1) - `045d0ea` (fix)
3. **Task 2 RED: failing tests for ALL_ARMS/fit_fitted_arms/leakage_probe** - `bf5d92b` (test)
4. **Task 2 GREEN: wire arms 3/4/5 and land the leakage probe** - `2ad9971` (feat)
5. **Docs: record Tasks 1-2 completion and the checkpoint halt** - `7bbe334` (docs, this worktree's base)

This session (Task 3, checkpoint resolved):
6. **Task 3 code: paired bootstrap margins, verdict resolution, arm 3/4/5 corridor-level test-set scoring** - `112fd8b` (feat)
7. **Task 3 transcription: the single held-out test-set run into the decision record** - `e6c02a0` (docs)

_Note: this SUMMARY.md itself is committed separately, per this session's explicit instruction that the orchestrator owns STATE.md/ROADMAP.md updates for this wave._

## Files Created/Modified

- `docs/data-science/decisions/forecast_correction_experiment.md` — Measured results section added (both corridors' tables, oracle ceiling, qualifiers); Verdict/Limitations/Open Questions remain Plan 03-07 placeholders.
- `backend/forecast_experiment.py` — `paired_bootstrap_margin`, `NO_CANDIDATE_BEAT_PERSISTENCE_VERDICT`, `_resolve_verdict`, `score_arms`'s/`corridor_experiment_report`'s additive `baseline_name` parameter, `_fitted_arm_city_frame`, `_merge_prediction_to_scored_index`, `_score_fitted_arms_at_corridor_level`, and `_run_corridor`'s `split == "test"` wiring added.
- `backend/tests/forecast_experiment_test.py` — 14 new tests for Task 3's bootstrap margin, verdict resolution, and corridor-level test-split (all seven arms) vs. val-split (unchanged) report shapes.

## Decisions Made

See `key-decisions` in frontmatter for full detail. Summary:
1. Checkpoint resolved as **proceed** — all three preconditions independently re-verified, user explicitly authorized; this session did not re-litigate the decision.
2. `baseline_name` threaded as an additive, default-`None` parameter through `score_arms`/`corridor_experiment_report` — every pre-existing caller's behavior is byte-identical to before this session.
3. The fitted-arm corridor-level wiring is gated to `split == "test"` only, preserving Plans 03-04/03-05's original val-split reproduction path unconditionally unchanged.
4. `paired_bootstrap_margin` reuses the phase's one existing fixed seed (`FORECAST_EXPERIMENT_CORRECTION_RANDOM_STATE`) rather than introducing a new config constant, per this task's own instruction to read, not edit, `config.py`.
5. Test-split reports write to a split-suffixed filename, never colliding with the val-split's pre-existing bare filename.
6. Test set scored exactly once — no defect, no re-run, no post-hoc tuning.

## Deviations from Plan

None — plan executed exactly as written. The one departure from the plan's own precondition text (which anticipated a warmed experiment cache so "this run does not re-issue the full fetch") was not a deviation requiring a rule: no cache existed in this worktree, so the run issued genuine live HTTP requests to the Open-Meteo APIs and completed successfully on the first attempt. This is documented here for transparency, not as an auto-fix, since nothing was broken or missing that required correction — the harness's live-fetch path is exactly what Plan 03-01 built and every prior wave's own live runs already exercised.

## Issues Encountered

None.

## Known Stubs

None — every function this session added is fully implemented and tested (14 new tests, all passing) and exercised against real live data in the Task 3 run itself, not only synthetic fixtures.

## User Setup Required

None — no external service configuration required. The live Open-Meteo API calls used no credentials (public, unauthenticated endpoints, as established throughout this phase).

## Next Phase Readiness

- **Ready for Plan 03-07.** The Measured results section is committed, transcribed verbatim from the single test-set run, with the Verdict/Limitations/Open Questions sections left as explicit Plan 03-07 placeholders per this plan's own prohibition against writing them here.
- **No blockers.** The full suite carries exactly the same 23 pre-existing `corridor_discretization_test.py` failures recorded in `.planning/WINDOWS.md` (641 passed / 23 failed after this session's commits, up from 627/23 at session start) — no regression introduced. Zero diff on `backend/ampacity_forecast.py`, `backend/anomaly_detector.py`, `backend/DLRSafetyMonitor.py`, `backend/config.py` from this plan's base commit (`c043c17`).
- **Headline finding for Plan 03-07 to interpret:** the measured result contradicts the Expectation on two specific, falsifiable predictions (predicted winner, and the refit reference arm's predicted underperformance) — both contradictions are stated plainly in the Measured results section rather than smoothed over, exactly as D-02 and this plan's own Expectation-writing discipline intended.
- **The generated JSON reports** (`data/experiment/experiment_report_{corridor}_test.json`) stay git-ignored evidence per this workstream's established precedent (`.gitignore:13:/data/experiment/`) — the decision record is the artifact of record, not the JSON file.
- **This SUMMARY.md is committed by this session; STATE.md, ROADMAP.md, and REQUIREMENTS.md are intentionally left untouched**, per this session's explicit instruction that the orchestrator owns those writes after this wave completes.
- **ACKNOWLEDGEMENTS.md intentionally not touched**, per this phase's established precedent (Plans 03-03/03-04/03-05 also did not touch it) — Plan 03-07 owns the consolidated Waves 2-5 AI-use disclosure entry.

## Self-Check: PASSED

- `docs/data-science/decisions/forecast_correction_experiment.md` (Measured results section present, both corridors' tables, oracle referenced, "24" stated; Verdict/Limitations/Open Questions each name "03-07") — FOUND (`MEASURED_TRANSCRIBED_OK`)
- `backend/forecast_experiment.py` (contains `paired_bootstrap_margin`, `_resolve_verdict`, `NO_CANDIDATE_BEAT_PERSISTENCE_VERDICT`, `_score_fitted_arms_at_corridor_level`) — FOUND
- `backend/tests/forecast_experiment_test.py` — FOUND (84 tests, verified passing)
- Commit `112fd8b` — FOUND in `git log --oneline --all`
- Commit `e6c02a0` — FOUND
- The decision record's FIRST commit is still `4d964cf` (isolated Expectation-plus-unlock, exactly 2 files) — CONFIRMED (`NO_PEEKING_AUDIT_OK`)
- `backend/ampacity_forecast.py`, `backend/anomaly_detector.py`, `backend/DLRSafetyMonitor.py`, `backend/config.py` carry zero diff from this plan's base (`c043c17`) — CONFIRMED
- Full suite: 641 passed, 23 failed (unchanged pre-existing `corridor_discretization_test.py` baseline per `.planning/WINDOWS.md`) — CONFIRMED
- Live test-set run: `TEST_SET_RUN_OK` (6 candidates per corridor, oracle excluded, identical row counts, every margin bracketed, non-empty verdict, `measured_lead_hours==24`, `split=='test'`) — CONFIRMED

---
*Phase: 03-ampacity-forecast-correction-experiment-compare-persistence*
*Plan: 06 (COMPLETE — all three tasks and the checkpoint resolved)*
*Completed: 2026-09-30*
