---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 07
subsystem: evaluation-headline-port
tags: [confirmation-protocol, protocol-rounds, veto-record, ship-rule-v4, headline-port, live-system-check, python, pytest, tdd]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-05 forecast_shadow_decision_v4 (apply_ship_rule_v4, combined_summary_v4); plan 07-06 ProtocolRound registry, armed round-aware guard, round_evidence_root, scorer --round
provides:
  - backend/forecast_shadow_confirm.py on signed v4 rounds (--round, --vetoes, load_vetoes, validate_veto_record, truth_stats, v4 headline or descriptive decision, round-aware fetch window and dry run)
  - a FRESH decision read that cannot start without a sha256-verified ABLATION and TEST veto record and a signed status (SEL-03)
  - backend/forecast_shadow_score.py with the v4 rule as the live-system label (truth_stats, pick always None, round named from the guard)
  - eval_core.render_decision v4 branch (bars, levels, consistency, vetoes with source, pick or no-pick statement)
  - confirm, score and dev-fixture validation suites on the v4 decision structure and combined_summary_v4
affects: [07-09, 07-10, 07-11, 07-12, 07-15]

actuals:
  tokens: 16500
  tasks: 2
  commits: 2
plan_head_before: a995bb224afc1ebcbe906c6670554b311885fa94
plan_head_after: 47bd95733151394ce4d70553c0f477dddcb9abf4

tech-stack:
  added: []
  patterns:
    - "A FRESH decision read is refused for a missing veto record inside run_confirmation before check_guard and before any directory exists, because a crash after the guard would spend the one-shot run"
    - "Veto record carries the sha256 of both source reports; the loader recomputes them from disk and the run records the record's path and hash in config, run_started.json and report"
    - "Evidence goes to <evidence-root>/<round>, so the one-shot rule is per round for the headline port as well"

key-files:
  created: []
  modified:
    - backend/forecast_shadow_confirm.py
    - backend/forecast_shadow_eval_core.py
    - backend/forecast_shadow_score.py
    - backend/tests/forecast_shadow_confirm_test.py
    - backend/tests/forecast_shadow_score_test.py
    - backend/tests/forecast_shadow_eval_validation_test.py

key-decisions:
  - "Deciding rounds (v4-read1, v4-read2) refuse at the CLI unless --vetoes loads and --protocol-status is signed, both checked before run_confirmation; the descriptive round needs neither; run_confirmation independently refuses a FRESH decision scope with no record before its guard (T-07-15, SEL-03)"
  - "load_vetoes returns the parsed record plus a 'file' entry {path, sha256}; a relative report path is resolved against the repository root (base_dir override); vetoed flags must be real bools; the record must name all three real candidates in both sections (stricter than the plan's 'every key is a candidate', so an edited file cannot un-veto by omission)"
  - "run_confirmation and score() take round_name defaulting to the guard's round and refuse a name that disagrees with the guard, so a read-2 guard can never produce a decision labelled read 1"
  - "Headline label for a deciding round, descriptive label for v4-late-descriptive, live label for the shadow-log scorer; require_vetoes is true only for a FRESH headline run, so development rehearsals still run without a record and carry the exploratory statement"
  - "Mean truth per city is the unrounded float mean of the prepared rows' truth_amps (port) or of raw_forecast's truth over scored rows (scorer); a city that fails or has no rows has no truth_stats entry, no bar, and cannot count toward the 3-city consistency need"
  - "The retired --decision-margin-amps flag stays registered (a non-default value is still refused in a FRESH run, PD-15) but its help text says the v4 rule does not use it"

patterns-established:
  - "FRESH-calendar test runs always carry a synthetic no-veto record; tests that exercise the guard on a FRESH scope pass it so the guard, not the record check, is what refuses"

requirements-completed: [SEL-04, SEL-03]

coverage:
  - id: D1
    description: "Headline port --round and --vetoes: deciding rounds refuse without a verified record or without a signed status before anything runs; the run goes to the round subroot with the round's guard; descriptive round needs no record"
    requirement: SEL-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_deciding_round_without_a_veto_record_is_refused_before_anything_runs"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_deciding_round_with_an_unsigned_status_is_refused_even_with_a_valid_veto_record"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_valid_veto_record_and_a_signed_status_reach_run_confirmation_in_the_round_subroot"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_fresh_run_without_a_veto_record_raises_before_the_guard_and_leaves_the_root_empty"
        status: pass
    human_judgment: false
  - id: D2
    description: "load_vetoes verifies both source-report sha256 values on disk, the structure, exact candidate names and bool flags; the veto file and its hash are recorded in config, run_started.json and report"
    requirement: SEL-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_load_vetoes_refuses_a_broken_record"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_tampered_source_report_refuses_the_run_at_the_cli"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_report_and_config_record_the_round_and_the_veto_file_with_its_hash"
        status: pass
    human_judgment: false
  - id: D3
    description: "Both evaluators compute per-city mean truth and apply apply_ship_rule_v4 (headline for the port's deciding rounds, descriptive for the late round, live for the scorer); a vetoed candidate is never picked; the live check never picks"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_fresh_run_decides_and_a_vetoed_candidate_is_never_picked"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_truth_stats_are_the_unrounded_mean_of_the_independent_truth_ampacity"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_score_test.py#test_a_large_model_benefit_gives_a_would_be_outcome_but_the_reported_pick_stays_none"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_validation_test.py#test_log_truth_stats_equal_the_oracle_mean_truth_and_feed_the_live_decision"
        status: pass
    human_judgment: false
  - id: D4
    description: "Empty edge: a failed city is named with its stage, never retried, has no truth rows, and the decision is computed on the rest (fewer than 3 cities gives no pick). Encoding edge: exact candidate strings, tz-aware UTC instants"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_city_whose_fetch_fails_has_no_truth_stats_and_the_decision_uses_the_other_three"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_two_failed_cities_leave_fewer_than_three_and_no_pick_is_made"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_instants_are_compared_as_utc_moments_never_as_text"
        status: pass
    human_judgment: false
  - id: D5
    description: "report.md renders the v4 decision in plain form (label, bar per city, level with bar and consistency, veto with source, single Pick or the no-pick statement); development-basis family and per-city metrics unchanged"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_report_renders_the_v4_decision_in_plain_form"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_v4_decision_block_of_a_development_run_leaves_family_and_metrics_alone"
        status: pass
      - kind: unit
        ref: "backend/tests/cond02_shadow_golden_test.py (COND-02 family section, unchanged)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Dry run for a round lists that round's requests and slot count (read 2: end 2026-10-31, 128 slots; read 1: end 2026-10-24, 100 slots)"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_dry_run_for_read_2_lists_requests_ending_2026_10_31_and_128_slots"
        status: pass
      - kind: command
        ref: "PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py --dry-run --round v4-read1 --out /tmp/p7_r1.json (prints v4-read1 100 2026-10-24)"
        status: pass
    human_judgment: false
  - id: D7
    description: "Dev-fixture validation suite and side-by-side summary on the v4 decision and combined_summary_v4 (mixed, swapped, duplicated sources refused); no test deleted; full suite green"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_validation_test.py#test_combined_summary_keeps_the_two_sources_apart_and_never_adds_their_counts"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_validation_test.py#test_apply_ship_rule_v4_refuses_a_family_that_mixes_row_sources"
        status: pass
      - kind: integration
        ref: "pytest backend/tests (full suite, 2335 passed, 82 skipped)"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 07: Headline Port and Scorer on Signed v4 Summary

**The headline port now runs only signed rounds (`--round`), refuses a decision read unless `--vetoes` names an ABLATION and TEST record whose two source-report sha256 values match disk and the status is signed, and decides with the v4 rule; the shadow-log scorer applies the same rule as a live-system label that never picks. No real FRESH row was read.**

## Performance

- **Duration:** 22 min (including one 6 min 23 s full-suite run)
- **Started:** 2026-11-02T07:26:55Z
- **Completed:** 2026-11-02T07:48Z
- **Tasks:** 2
- **Files modified:** 6 (three modules, three test files)

## Accomplishments

- `forecast_shadow_confirm.py`: `--round {v4-late-descriptive,v4-read1,v4-read2}` (default v4-read1) and `--vetoes PATH`. The round's guard comes from the round-aware `score_mod._guard_from_args`, evidence goes to `<evidence-root>/<round>`, and the production provider, dry run, config record and fetch window all follow the round (read 2: 2026-09-28..2026-10-31, 128 slots). Dry run JSON gains `round`, `fetch_window` and the round's `expected_slots_per_city`.
- Veto record (SEL-03, T-07-15): `load_vetoes` recomputes the sha256 of the ABLATION and TEST source reports and compares them with the recorded values, checks the structure (both sections, exact candidate names, real-bool `vetoed`), and returns the record with its own path and sha256. A deciding round refuses at the CLI (exit 2, `refused:`) without a loadable record or without `--protocol-status signed`, before `run_confirmation`. `run_confirmation` itself raises `ValueError` for a FRESH decision scope with no record before `check_guard` and before any directory exists. The record's path and hashes are in `config`, `run_started.json` and `report["vetoes"]`.
- Decision: `report["truth_stats"]` (per-city unrounded mean truth and row count; absent for a failed or empty city) feeds `apply_ship_rule_v4`: headline label for a deciding round, descriptive label for the late descriptive round, `require_vetoes` only for a FRESH headline run, fraction and consistency threshold from the registered params. The v3 import is gone from both modules.
- `forecast_shadow_score.py`: `truth_stats` from `raw_forecast`'s truth over scored rows; the decision is the v4 rule with the live label (pick always `None`, would-be outcome in `rule_outcome`); `score()` names its round from the guard and refuses a disagreeing `round_name`.
- `eval_core.render_decision` (v4 branch only): label and round line, one bar line per city (two decimals), each candidate's level with benefit, pooled bar, Holm-adjusted p, consistency counts and veto text, the alternatives against wind, then `Pick: <name>` or the no-pick statement and the statements. The v3 rendering is unchanged.
- Test counts: confirm 52 -> 100, score 45 -> 51, validation 43 -> 45 collected. Full suite 2335 passed, 82 skipped (was 2279 passed).

## Task Commits

1. **Task 1: Headline port on signed rounds with a required veto record and the v4 decision** - `79b5857` (feat)
2. **Task 2: v4 rule as the live-system label in the shadow-log scorer; dev-fixture suite on v4** - `47bd957` (feat)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Evidence (both tasks `tdd="true"`)

- **Task 1 RED:** after the tests were written and before any implementation, `pytest backend/tests/forecast_shadow_confirm_test.py -x` failed on `test_guard_refuses_before_any_side_effect` with `TypeError: run_confirmation() got an unexpected keyword argument 'vetoes'`, and the full file run failed in every new test and every test using the `run()` helper (the planned API did not exist). Semantic assessment: the target tests ran and failed on the planned behavior (missing `vetoes`, `round_name`, `load_vetoes`, `--round`), not on a syntax or collection fault. **GREEN:** the same file then passed (100 tests), with the eval-core, decision-v4 and COND-02 golden suites.
- **Task 2 RED:** `pytest backend/tests/forecast_shadow_score_test.py` failed 8 tests (the updated decision assertions, the new truth-stats, live-label, round and import tests) and the validation suite failed 4 (`test_log_family_margins_equal_the_complete_case_oracle`, `test_log_truth_stats_equal_the_oracle_mean_truth_and_feed_the_live_decision`, `test_apply_ship_rule_v4_refuses_a_family_that_mixes_row_sources`, `test_combined_summary_keeps_the_two_sources_apart_and_never_adds_their_counts`), each on the v3 label or a missing `truth_stats`, which is the intended reason. **GREEN:** after the scorer change all four evaluation suites passed.
- The plan type is `execute` and prescribes one `feat(07-07)` commit per task, so there is no separate `test(07-07)` commit and no TDD Gate Compliance section applies.

## Files Created/Modified

- `backend/forecast_shadow_confirm.py` - `--round`, `--vetoes`, `load_vetoes`, `validate_veto_record`, `truth_stats`, v4 decision, round-aware provider, dry run and config; docstring updated for v4 (100 and 128 rows, operator commands, veto record)
- `backend/forecast_shadow_eval_core.py` - `render_decision` v4 branch (`_render_decision_v4`); nothing else touched
- `backend/forecast_shadow_score.py` - `truth_stats`, v4 live label, `round_name`, docstring and help text
- `backend/tests/forecast_shadow_confirm_test.py` - veto-file helper, 48 new tests and the `run()` helper default record
- `backend/tests/forecast_shadow_score_test.py` - decision assertions on v4, 6 new tests
- `backend/tests/forecast_shadow_eval_validation_test.py` - synthetic no-veto record on every FRESH-calendar run, v4 decision and `combined_summary_v4` tests, truth-stats oracle checks

## Decisions Made

See `key-decisions` above. The ordering matters for the one-shot read: CLI veto and signed checks, then `run_confirmation`'s own veto check, then `check_guard` (override text, retired instant, unsigned v4, dates, parameters, before-instant, one-shot), then the evidence directory.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] The veto record must name all three candidates in both sections**
- **Found during:** Task 1 (`load_vetoes`)
- **Issue:** the plan checks only that every candidate key is in `core.REAL_CANDIDATES`. A record missing a candidate key would be read by `apply_ship_rule_v4` as "not vetoed" for it, so a truncated or hand-edited file could un-veto a candidate (T-07-15).
- **Fix:** `validate_veto_record` also requires every real candidate in each section and refuses unknown keys and non-bool flags (0, 1 and strings). Work for 07-11: its writer must emit all three candidates in both sections (the interface shape already does).
- **Files modified:** backend/forecast_shadow_confirm.py, backend/tests/forecast_shadow_confirm_test.py
- **Committed in:** 79b5857

**2. [Rule 2 - Missing critical] `round_name` defaults to the guard's round, and a disagreement is refused**
- **Found during:** Tasks 1 and 2
- **Issue:** the plan's default of `core.DEFAULT_ROUND.name` would label a read-2 decision "v4-read1" whenever a caller built a read-2 guard but did not repeat the round name.
- **Fix:** `run_confirmation` and `score` take `round_name=None`, use the guard's round, and raise `ValueError` if the two differ. For default guards the behavior is the plan's.
- **Committed in:** 79b5857, 47bd957

**3. [Rule 1 - Bug] Tests that relied on the guard being first for a FRESH CLI run now meet the veto check**
- **Found during:** Task 1
- **Issue:** `test_cli_refuses_before_the_instant_with_exit_2` and `test_cli_nondefault_parameter_in_a_fresh_run_is_refused` (and the validation suite's block-length CLI test) run `main` on a FRESH scope with no `--vetoes`; they are now refused for the missing record before the guard they were written to exercise.
- **Fix:** they pass a valid veto file and `--protocol-status signed`, so the guard is again what refuses; intent unchanged, no test deleted. The same applies to the four direct FRESH-calendar `run_confirmation` calls in the validation suite (they carry a synthetic no-veto record, as the plan prescribes).
- **Committed in:** 79b5857, 47bd957

**4. [Rule 3 - Blocking] The plan's non-dry-run acceptance command was run behind tripwires**
- **Found during:** Task 1 acceptance
- **Issue:** the acceptance criterion invokes `forecast_shadow_confirm.py --round v4-read1 --evidence-root <tmp>` for real. The real clock (2026-11-02) is past the read-1 instant and v4 is signed, so a defect in the new refusal would have spent the one-shot read.
- **Fix:** the same `main([...])` call was made in-process with `requests.get` and `run_confirmation` replaced by tripwires. It printed `refused: a deciding round (v4-read1) cannot start: --vetoes must name the ABLATION and TEST veto record (SEL-03: ...); --protocol-status signed is required`, exited 2 and created no directory. The dry-run acceptance command was run as written (`v4-read1 100 2026-10-24`).

---

**Total deviations:** 4 (2 missing critical, 1 bug in test premises, 1 blocking safety substitution). **Impact on plan:** items 1 and 2 only tighten the plan's own refusals; items 3 and 4 are test and verification hygiene. No scope creep. No real confirm or scoring run was executed, and no predicted-versus-truth figure for a valid time on or after 2026-09-30 was computed or read: every FRESH-calendar run in the tests uses synthetic data, a stubbed network and an injected clock.

## Issues Encountered

None beyond the deviations above.

## Notes for later plans

- 07-09 (production-conductor geometry seam, frozen-Drake secondary): `run_confirmation(round_name=, vetoes=)`, `report["truth_stats"]` and `apply_ship_rule_v4`'s `secondary` label are the hooks; `combined_summary_v4(headline, live, secondary)` already refuses a duplicated or wrong-source secondary (tested).
- 07-11 (veto writer): write `{"protocol": "v4", "ablation": {"report", "sha256", "vetoes": {all three candidates}}, "test": {...}}`; a relative `report` path is resolved against the repository root (`load_vetoes(base_dir=)` overrides it). Hash the reports after they are final: any later edit makes the read refuse.
- The live-system label's statement list carries "no ABLATION/TEST veto record was applied (development basis)" (from `apply_ship_rule_v4` with `vetoes=None`), which reads oddly for a live check in a FRESH run; the wording lives in `forecast_shadow_decision_v4.py`, outside this plan's files.
- `--decision-margin-amps` is now an inert, still-registered parameter in both CLIs.

## Known Stubs

None.

## Threat Flags

None. The new file-access surface (reading the operator-named veto file and the two reports it names) is exactly the trust boundary the plan's T-07-15 mitigates; no endpoint, auth path or schema was added.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The tooling for the one-shot read is complete for the headline port and the live check; the read itself is blocked until the TEST and ABLATION vetoes exist (07-11) and the AUSTIN Drake-100 geometry is applied (07-09/07-11, owner item O4).

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*

## Self-Check: PASSED

- FOUND: backend/forecast_shadow_confirm.py, backend/forecast_shadow_eval_core.py, backend/forecast_shadow_score.py, the three test files, this summary
- FOUND commits: 79b5857, 47bd957 (both ancestors of HEAD; 2 commits measured from the ledger base a995bb2)
- Acceptance criteria re-run: `grep -c apply_ship_rule_v4` prints 1 (score) and 2 (confirm); `git diff --quiet d71c501 -- backend/forecast_shadow_decision.py backend/forecast_shadow_score_stats.py` exits 0; dry run prints `v4-read1 100 2026-10-24`; the guarded non-dry-run stand-in exits 2 with `refused:`
- Plan verification: full suite 2335 passed, 82 skipped; `git status --porcelain data/shadow` prints nothing
