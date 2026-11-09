---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 05
subsystem: evaluation-selection-rule
tags: [confirmation-protocol, selection-rule, relative-margin, vetoes, no-pick, python, pytest, tdd]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-02 signed protocol v4 (signing copy and protocol_v4_registry parser)
provides:
  - backend/forecast_shadow_decision_v4.py, the signed v4 ship rule as a pure module (bars, levels, consistency, vetoes, pick or no pick, labels, side-by-side summary)
  - backend/tests/forecast_shadow_decision_v4_test.py, 73 synthetic-family tests plus registry parity
affects: [07-07, 07-09, 07-10, 07-12, 07-15]

actuals:
  tokens: 13200
  tasks: 2
  commits: 4
plan_head_before: 4a11ad013e9980c28e49ca0115b63bb50bff4ea5
plan_head_after: 0ee7d69a0b92531c5b5c29f9f26e9c27aff28331

tech-stack:
  added: []
  patterns:
    - "Decision constants pinned to the signed registry by a parity test (T-07-11); code never imports from tests"
    - "One family report in, one decision out; non-headline labels compute the would-be result but always report pick None"

key-files:
  created:
    - backend/forecast_shadow_decision_v4.py
    - backend/tests/forecast_shadow_decision_v4_test.py
  modified: []

key-decisions:
  - "v4 rule implemented exactly as signed: bar = 2% of mean truth, pooled paired-row-weighted (O1=A); alternatives displace wind only by that same relative bar in >= 3 cities (O10=A); read 2 uses the same rules (O2=A, READ2_REQUIRES_SUPPORTED False); no-winner-after-read-2 outcome is the signed O3=A text"
  - "Bars are computed at run time from the round's truth_stats, so AUSTIN's Drake-100 mean truth (O4) feeds in with no code change; the Drake-75 ABLATION means (1257.8 / 1375.8 / 1525.4 / 1236.8 A) appear only as the signing copy's worked example in tests"
  - "A supplied veto record is always applied, even when require_vetoes is False; require_vetoes=False with vetoes=None is the development-basis path (nothing vetoed, statement and exploratory label added)"
  - "A headline decision is refused for any row source other than reconstructed_frames (the live-system check never decides)"

requirements-completed: [SEL-01, SEL-04]

coverage:
  - id: D1
    description: "Relative bars (2% of mean truth, 25.156 / 27.516 / 30.508 / 24.736 A; pooled equal-rows bar 26.979 A), unrounded float64, paired-row weighting"
    requirement: SEL-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_equal_rows_pooled_bar_matches_the_signing_copy_worked_example"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_pooled_bar_is_weighted_by_paired_rows"
        status: pass
    human_judgment: false
  - id: D2
    description: "Evidence levels and 3-of-4 consistency with the adjacency, empty and precision edges (benefit == bar meets it; 2 cities with data cannot be consistent)"
    requirement: SEL-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_benefit_exactly_equal_to_the_bar_meets_it"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_two_cities_with_data_cannot_be_consistent_and_the_reason_names_the_count"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pick or no pick: wind default, alternatives displace it by the bar in >= 3 cities, larger margin wins, fixed tie order independent of dict order, ABLATION/TEST vetoes, D-07 no-pick statements per round, headline needs the veto record (SEL-03)"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_an_exact_tie_between_alternatives_follows_the_fixed_order_not_dict_order"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_best_candidate_vetoed_by_ablation_is_never_picked_and_wind_stays"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_headline_needs_the_veto_record_when_required"
        status: pass
    human_judgment: false
  - id: D4
    description: "Secondary, live and descriptive labels never pick; mixed row sources refused; side-by-side summary refuses swapped or duplicated sources; constants equal the signed registry; v3 decision module and tests byte-identical"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_constants_match_the_signed_registry"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_decision_v4_test.py#test_combined_summary_v4_refuses_swapped_or_duplicated_sources"
        status: pass
      - kind: command
        ref: "git diff --quiet d71c501 -- backend/forecast_shadow_decision.py backend/tests/forecast_shadow_decision_test.py"
        status: pass
    human_judgment: false

status: complete
---

# Phase 7 Plan 05: v4 Ship Rule Summary

**The signed protocol-v4 selection rule is now executable as a new pure module: 2%-of-mean-truth pooled bars, supported / indicated / not-shown levels, 3-of-4 consistency, ABLATION and TEST vetoes, a fixed tie order and an explicit "no pick" outcome, pinned to the signing copy's registry by a parity test; the v3 decision module is untouched.**

## Performance

- **Started:** 2026-11-02T06:55Z, **finished:** 2026-11-02T07:01Z (about 6 minutes)
- **Tasks:** 2 of 2 (each a RED then GREEN commit), 2 files created, 0 modified
- **Tests:** 73 in `forecast_shadow_decision_v4_test.py`; with the v3 decision tests, the COND-02 golden and the protocol doc test, 141 pass

## Accomplishments

- `city_bars`, `pooled_bar`: bar_c = 0.02 x mean truth (None for a city with no truth rows); pooled bar is the paired-row-weighted mean using each comparison's own per-city `n_paired`. With the non-FRESH means the bars are 25.156 / 27.516 / 30.508 / 24.736 A and the equal-rows pooled bar is 26.979 A.
- `evidence_level_v4`, `consistency`: the four levels by the signed rule (benefit == bar meets it; "supported" needs `p_holm_adjusted <= alpha` and benefit > 0); 3-of-4 consistency, impossible below 3 cities with data (reason names the count). All arithmetic unrounded; two-decimal rounding appears only in rendered text.
- `apply_ship_rule_v4`: refuses mixed row sources and a headline with `require_vetoes=True` and no veto record (ValueError naming SEL-03); picks wind unless a qualifying alternative is consistently better by the pooled bar in >= 3 cities (larger margin wins); with wind not qualifying, the qualifying alternative with the larger benefit over raw wins; exact ties follow `TIE_ORDER` regardless of dict or list order; a vetoed candidate never qualifies; nothing qualifying gives pick None with `NO_PICK_STATEMENT` plus the read-2 schedule (round v4-read1) or the signed O3 outcome (round v4-read2).
- Secondary, live and descriptive labels compute levels and the would-be `rule_outcome` but always report `pick: None`.
- `combined_summary_v4`: headline, live-system and optional secondary blocks, a bars line per city, no number computed across row sources; swapped, duplicated or mislabelled reports are refused.
- Constants (`RELATIVE_MARGIN_FRACTION`, `BAR_SCOPE`, `CONSISTENCY_MIN_CITIES`, `FAMILY_ALPHA_BY_ROUND`, `TIE_ORDER`, `READ2_REQUIRES_SUPPORTED`) are asserted equal to the signed registry and the O2 sign-off, mitigating T-07-11.

## Task Commits

1. Task 1 RED: `8ed2833` test(07-05): add failing tests for v4 bars, evidence levels and consistency
2. Task 1 GREEN: `3c064a3` feat(07-05): v4 bars, evidence levels and consistency under the relative threshold
3. Task 2 RED: `1e3e36d` test(07-05): add failing tests for v4 vetoes, pick or no pick, labels and summary
4. Task 2 GREEN: `0ee7d69` feat(07-05): v4 vetoes, pick or no pick, labels and side-by-side summary

## TDD Gate Compliance

- **RED (both tasks):** `test(07-05)` commits precede each `feat(07-05)` commit. RED evidence came from `pytest --junitxml` runs; `gsd_run check tdd-red-evidence` returned `RED_EVIDENCE_OK` (reason `target_test_failed`) for both: Task 1 26 of 26 tests failing (target `test_city_bars_are_two_percent_of_mean_truth`), Task 2 47 of 47 new tests failing (target `test_alternative_consistently_better_than_wind_is_picked`). Semantic assessment: the target tests executed and failed with `AttributeError` because the planned functions did not exist yet, which is the intended reason; no import, collection or fixture fault. The evidence records sit untracked under `.planning/tmp/07-05-red/`.
- **GREEN:** both feature commits pass their test files (26, then 96 with the v3 decision tests).
- **REFACTOR:** none needed.
- To make RED fail at test time rather than at import, the Task 1 RED commit includes a docstring-only placeholder `backend/forecast_shadow_decision_v4.py` (no functions, no constants).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test used a mean truth whose 2% bar is exactly representable after rounding**
- **Found during:** Task 1 GREEN
- **Issue:** `test_city_bars_are_unrounded_float64` asserted that 0.02 x 1257.8 differs from its 3-decimal rounding, but it equals 25.156 exactly in float64, so the test failed on the correct implementation.
- **Fix:** the test now uses mean truth 1257.837 (bar 25.15674), which is not equal to its rounded value.
- **Files modified:** backend/tests/forecast_shadow_decision_v4_test.py
- **Commit:** 3c064a3

### Judgement calls within the plan's wording (no behavior outside the signed rule)

- A veto record that is supplied is always applied, even when `require_vetoes=False`; `require_vetoes=False` with `vetoes=None` is the development-basis path (nothing vetoed, "no ABLATION/TEST veto record was applied (development basis)" and the exploratory statement added). Ignoring a supplied veto would be the unsafe reading.
- `apply_ship_rule_v4` refuses `label="headline"` for a row source other than `reconstructed_frames` ("the live-system check never decides"), consistent with v3 decision 9 and D-02.
- Unknown round names and unknown labels raise ValueError; `consistency()` takes a keyword-only `scope` (default `BAR_SCOPE`) so a per-city scope (O1 option B) would need no new code.

**Total deviations:** 1 auto-fixed (test bug). **Impact:** none on the delivered rule.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. The module is pure (no I/O, no network, no file access). No scorer was run and no predicted-versus-truth figure for a `valid_time` on or after 2026-09-30 was computed or read; the only accuracy-related numbers used are the non-FRESH ABLATION means printed in the signing copy.

## Notes for later plans (07-07 wiring)

- Input shapes: `truth_stats = {city: {"mean_truth_amps", "n_truth_rows"}}` for the round's scored rows (AUSTIN's will be under Drake 100 C per O4); `vetoes = {"ablation": {candidate: {"vetoed": bool}}, "test": {...}}`; `combined_summary_v4` reads each report's `["decision"]` (the dict `apply_ship_rule_v4` returns) and its `["row_source"]`.
- The headline path should call with `require_vetoes=True`; development-basis callers pass `require_vetoes=False`.
- `FAMILY_ALPHA_BY_ROUND` and `READ2_REQUIRES_SUPPORTED` are module constants read at call time; the registry parity test fails if the signed values ever change.

## Self-Check: PASSED

- FOUND: backend/forecast_shadow_decision_v4.py, backend/tests/forecast_shadow_decision_v4_test.py
- FOUND commits 8ed2833, 3c064a3, 1e3e36d, 0ee7d69 (ancestors of HEAD; 4 commits measured from the ledger base 4a11ad0)
- Acceptance: `city_bars` prints 25.156; `grep -c` of the two function defs prints 2; `git diff --quiet d71c501` exits 0 for the v3 module and the v3 test file
- Plan verification: forecast_shadow_decision_v4_test, cond02_shadow_golden_test, forecast_shadow_decision_test and protocol_v4_doc_test, 141 passed
