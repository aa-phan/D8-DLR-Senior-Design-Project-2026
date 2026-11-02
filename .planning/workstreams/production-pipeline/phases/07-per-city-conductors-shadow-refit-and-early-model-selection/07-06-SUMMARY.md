---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 06
subsystem: evaluation-guard
tags: [confirmation-protocol, protocol-rounds, anti-peeking-guard, one-shot, python, pytest, tdd]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-02 signed protocol v4 (signing copy, protocol_v4_registry parser); plan 07-05 forecast_shadow_decision_v4 (RELATIVE_MARGIN_FRACTION)
provides:
  - backend/forecast_shadow_eval_core.py as the signed v4 round registry (ProtocolRound, V4_READ1, V4_READ2, V4_LATE_DESCRIPTIVE, PROTOCOL_ROUNDS, DEFAULT_ROUND, round_named, round_evidence_root, guard_for_round, V3_RETIRED_INSTANT, V4_SIGNING_COPY, v4_signed, GuardConfig.round_name, PD-18, relative_margin_fraction 0.02)
  - an armed, round-aware check_guard: no override path for a FRESH run, retired v3 instant refused, unsigned v4 refused, before-instant and one-shot refusals always on
  - backend/forecast_shadow_score.py --round (live-system check by round, evidence under the round's subroot)
  - the four evaluation test suites moved to the v4-read1 values (189 -> 227 collected tests)
affects: [07-07, 07-09, 07-10, 07-12, 07-15]

actuals:
  tokens: 27000
  tasks: 2
  commits: 2
plan_head_before: 0a1025959c42619d5029864701d6d1acc9009191
plan_head_after: 6e4474cd7fe03d85d5c2a97a5fcc6e0950ceef19

tech-stack:
  added: []
  patterns:
    - "A named, frozen protocol round selected by name replaces the override text; the guard compares dates with the selected round, so it never needs to be switched off"
    - "Round constants pinned to the signed registry by test_rounds_match_the_signed_registry (code never imports from tests)"
    - "FRESH refusals ordered: override text, retired instant, unsigned v4, non-default dates and parameters, before-instant, one-shot; every one fires before any network call or FRESH file read"

key-files:
  created: []
  modified:
    - backend/forecast_shadow_eval_core.py
    - backend/tests/forecast_shadow_eval_core_test.py
    - backend/forecast_shadow_score.py
    - backend/tests/forecast_shadow_score_test.py
    - backend/tests/forecast_shadow_confirm_test.py
    - backend/tests/forecast_shadow_eval_validation_test.py

key-decisions:
  - "Signed rounds as data, not flags: v4-read1 (2026-11-01T00:00:00Z, cutoff 2026-10-25T00:00:00Z, fetch 2026-09-28..2026-10-24, 100 slots), v4-read2 (2026-11-08, 2026-11-01, 2026-09-28..2026-10-31, 128 slots) and v4-late-descriptive (read 1's dates, descriptive only); module defaults are v4-read1; every value equals the signing copy registry (parity test)"
  - "A FRESH run takes no override at all (T-07-12, SEL-04): any non-blank override text raises EvaluationGuardError, so the before-instant and one-shot refusals can no longer be skipped; development runs keep the recorded override for non-default dates"
  - "The retired 2026-11-24 instant raises ValueError for any FRESH run, and v4_signed() False raises EvaluationGuardError before any network call (T-07-13, T-07-14); both are checked inside check_guard, which every evaluator already calls first"
  - "relative_margin_fraction 0.02 is a pre-registered parameter (PD-10 names it), so a non-default value in a FRESH run is refused like any other; decision_margin_amps 5.0 stays registered because the v3 ship-rule call in forecast_shadow_score is left for 07-07"
  - "forecast_shadow_confirm.py is untouched here (its --round and veto record are 07-07); it picks up the v4-read1 dates through the module defaults"

patterns-established:
  - "Evidence subroot per round (data/shadow/evaluation/<round>) so the one-shot rule applies per round and row source; created at run time only"

requirements-completed: [SEL-01, SEL-04]

coverage:
  - id: D1
    description: "Frozen ProtocolRound registry (three signed rounds) with module defaults at v4-read1, equal to the signing copy's registered values"
    requirement: SEL-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_rounds_match_the_signed_registry"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_slot_counts_follow_from_the_signed_windows"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_constants_are_pinned"
        status: pass
    human_judgment: false
  - id: D2
    description: "Round-aware armed guard: refusal one second before each round's instant, run at the instant with no override and no non-default dates, cutoff equal to the instant is a ValueError, 2026-10-25T00:00:00Z is the first unscored slot"
    requirement: SEL-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_a_round_is_refused_one_second_before_its_instant_and_runs_at_it_with_no_override"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_the_read1_boundary_edge"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_each_signed_round_has_its_registered_slot_count_and_window"
        status: pass
    human_judgment: false
  - id: D3
    description: "A FRESH run is refused whatever override text is given, at the retired v3 instant, and while v4 is unsigned; development runs are unaffected; a non-default relative margin is refused"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_a_fresh_run_is_refused_whatever_override_text_is_given"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_the_retired_v3_instant_is_refused_for_a_fresh_run"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_a_fresh_run_is_refused_while_v4_is_unsigned_and_a_development_run_is_not"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_a_non_default_relative_margin_refuses_a_fresh_run_and_override_text_cannot_help"
        status: pass
    human_judgment: false
  - id: D4
    description: "One-shot rule per round evidence subroot and row source (a read-2 marker does not refuse read 1)"
    requirement: SEL-01
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_eval_core_test.py#test_one_shot_applies_per_round_subroot"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_score_test.py#test_round_read_2_scores_into_the_read_2_subroot_with_read_2_dates"
        status: pass
    human_judgment: false
  - id: D5
    description: "forecast_shadow_score.py --round with the registry's names, guard of the selected round, evidence under the round's subroot, count-only unchanged"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_score_test.py#test_cli_lists_the_signed_rounds_and_defaults_to_read_1"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_score_test.py#test_guard_from_args_builds_the_selected_rounds_guard"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_score_test.py#test_count_only_ignores_the_round_and_never_needs_one"
        status: pass
    human_judgment: false
  - id: D6
    description: "Confirm, score, eval-core and dev-fixture validation suites pass with date literals at v4-read1 and the old override-path tests asserting the refusal; no test deleted"
    requirement: SEL-01
    verification:
      - kind: integration
        ref: "pytest backend/tests/forecast_shadow_score_test.py backend/tests/forecast_shadow_confirm_test.py backend/tests/forecast_shadow_eval_validation_test.py backend/tests/forecast_shadow_eval_core_test.py backend/tests/cond02_shadow_golden_test.py (239 passed)"
        status: pass
      - kind: integration
        ref: "pytest backend/tests (full suite, 2279 passed, 82 skipped)"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 06: Signed v4 Rounds and an Armed Guard Summary

**The frozen evaluation core now holds the three signed v4 rounds as named, frozen values, with one anti-peeking guard that stays armed for every round: a FRESH run takes no override, the retired 2026-11-24 instant and an unsigned v4 are refused, and the live-system scorer selects a round with `--round`.**

## Performance

- **Duration:** 22 min
- **Started:** 2026-11-02T07:02:19Z
- **Completed:** 2026-11-02T07:24Z
- **Tasks:** 2
- **Files modified:** 6 (two modules, four test files)

## Accomplishments

- `ProtocolRound` registry in `forecast_shadow_eval_core.py`: `v4-read1`, `v4-read2`, `v4-late-descriptive`, each equal to the signing copy's registry (a parity test parses the signed copy). The module defaults (`EVALUATION_INSTANT_DEFAULT`, `VALID_TIME_CUTOFF_DEFAULT`, `RECON_FETCH_START`, `RECON_FETCH_END`) are v4-read1's; `MODEL_FREEZE` and `FRESH_BASIS_START` are unchanged.
- `check_guard` measures non-default dates against the selected round, so selecting a round never needs an override. For a FRESH basis it now refuses: any override text, the retired v3 instant, an unsigned v4 (`v4_signed()` reads the signature line), non-default dates or parameters, a read before the instant and a second read into the same subroot. The old `override is None` conditions on the before-instant and one-shot refusals are gone (`grep -c "if now_ts < instant and override is None"` prints 0).
- `relative_margin_fraction` 0.02 is pre-registered (PD-10), PD-15 says signed rounds take no override, PD-18 names the protocol round, `OWNER_PENDING` points at the signing copy, and the report header gains a `Round:` line.
- `forecast_shadow_score.py --round {v4-late-descriptive,v4-read1,v4-read2}` (default v4-read1): the guard starts from the selected round, an explicit `--evaluation-instant` or `--valid-time-cutoff` goes on top (and is then non-default), scoring runs write into `<evidence-root>/<round>`, and `--count-only` is unchanged. The docstring's operator commands use `--round` and mark 2026-11-24 retired.
- Evaluation suites moved to the v4-read1 values (instant 2026-11-01T00:00:00Z, just-before 2026-10-31T23:59:59Z, cutoff 2026-10-25T00:00:00Z, fetch end 2026-10-24, 100 rows per city). Collected tests across the four suites: **189 before (40 score, 50 confirm, 43 validation, 56 eval-core), 227 after (45, 52, 43, 87)**. Full suite: 2279 passed, 82 skipped.

## Task Commits

1. **Task 1: Signed round registry and the armed, round-aware guard in the evaluation core** - `15504d5` (feat)
2. **Task 2: --round for the live-system check and the date literals across the three evaluation test suites** - `6e4474c` (feat)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Evidence (Task 1, `tdd="true"`)

- **RED:** `pytest backend/tests/forecast_shadow_eval_core_test.py -x` failed on the target test `test_constants_are_pinned`, on the planned assertion `core.EVALUATION_INSTANT_DEFAULT == 2026-11-01T00:00:00Z` (actual 2026-11-24T00:00:00Z); the test ran and asserted, it was not an import or collection failure. Semantic assessment: valid RED, intended reason.
- **GREEN:** after the registry and guard changes the same file passed (87 passed).
- The plan prescribes one `feat(07-06)` commit holding both files (plan type is `execute`, not `tdd`), so there is no separate `test(07-06)` commit and no TDD Gate Compliance section applies.

## Files Created/Modified

- `backend/forecast_shadow_eval_core.py` - round registry, `v4_signed`, round-aware armed `check_guard`, PD updates, header line, docstring for v4 rounds
- `backend/tests/forecast_shadow_eval_core_test.py` - constants moved to v4-read1, old override-path tests assert the refusal, 31 new tests (registry parity, boundary edge, per-round one-shot, unsigned, retired, relative margin)
- `backend/forecast_shadow_score.py` - `--round`, round-aware `_guard_from_args`, round evidence subroot, docstring
- `backend/tests/forecast_shadow_score_test.py` - cutoff literals moved, `--round` tests added
- `backend/tests/forecast_shadow_confirm_test.py` - window and slot counts moved to 100, refusal tests, per-round window test
- `backend/tests/forecast_shadow_eval_validation_test.py` - fixture mapping `PROD_SLOTS = SLOTS[:100]`, FRESH-calendar log runs re-expressed for the 2026-10-25 cutoff, refusal tests

## Decisions Made

See `key-decisions` above. Notable: the guard check order puts "override text" first, then the retired instant, then "unsigned", so each refusal names its own cause; a retired-instant FRESH run with override text reports the override refusal.

## Premises rewritten for v4-read1 (no test deleted)

Tests whose premise only existed for the retired window were rewritten, keeping their intent:

- `test_default_window_is_the_192_slot_fresh_window` became `test_default_window_is_the_100_slot_fresh_window_of_read_1` (and `test_scored_rows_are_exact_lead_fresh_and_at_most_192` became `..._at_most_100`).
- Tests that ran a FRESH read early or twice through an override reason (`test_override_passes_and_is_recorded`, the "owner-approved rerun" branches, the `*_override_is_recorded_in_json_and_markdown` pair) now assert the refusal; a development-basis test keeps the recorded override.
- The validation suite's FRESH-calendar log tests (`FRESH_LOG_SHIFT_DAYS = 200`) now see 28 in-scope rows per city and 216 at or after the 2026-10-25 cutoff (was 120 and 124); the cutoff-fault test uses fixture indices 20..29, and its persistence count is 7 because every 10th fixture row has no persistence.
- Later-dated fixture literals in the confirm tests (truth perturbation cut, null hour) moved inside the 09-28..10-24 window.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Real-clock FRESH CLI test would have attempted a live FRESH read**
- **Found during:** Task 2 (`test_cli_guard_refusal_exits_2_with_message_and_no_network`, `test_cli_nondefault_parameter_in_a_fresh_run_is_refused`)
- **Issue:** the tests relied on the real clock being before the old 2026-11-24 instant. With v4-read1's instant at 2026-11-01 the real clock (2026-11-02) is already past it, so the CLI no longer refuses on the clock and the test would have gone on to the network step.
- **Fix:** pinned `core.utcnow` before or at the round's instant in those tests (the CLI exposes no clock), and added a refusal-with-override case.
- **Files modified:** backend/tests/forecast_shadow_score_test.py, backend/tests/forecast_shadow_confirm_test.py, backend/tests/forecast_shadow_eval_validation_test.py
- **Committed in:** 6e4474c

**2. [Rule 2 - Missing critical] The `--round` test for the live-system check pins the clock too**
- **Found during:** Task 2
- **Issue:** the new `--round v4-read2` tests call `main()`, which reads the real clock; unpinned they would pass or fail depending on the day they run.
- **Fix:** every new CLI test pins `core.utcnow`.
- **Committed in:** 6e4474c

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical). **Impact on plan:** both are test hygiene needed because the real clock passed the read-1 instant on 2026-11-01; no scope creep. No FRESH data was read or computed at any point: every FRESH-calendar run in the tests uses synthetic fixture data, a stubbed network and an injected clock.

## Issues Encountered

None beyond the deviations above.

## Operator note for the owner (not a deviation)

`forecast_shadow_confirm.py` is deliberately untouched here (`--round`, `--vetoes` and the veto-record requirement are 07-07). Until 07-07 lands, the real clock (2026-11-02) is already past the read-1 instant and v4 is signed, so a real `forecast_shadow_confirm.py` run (not `--dry-run`) would pass the guard and spend the one-shot read without the veto check. Do not run it before 07-07 and the TEST/ABLATION vetoes exist. The plan's `--dry-run` was run and exits 0 with requests ending 2026-10-24 and 100 expected slots per city; it reads no FRESH file and makes no network call.

## Known Stubs

None.

## Threat Flags

None. The change removes an unsafe path (T-07-12 override, T-07-13 retired instant, T-07-14 unsigned FRESH) and adds no endpoint, auth path or file access beyond reading the committed signing copy's signature line.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 07-07 can take `core.PROTOCOL_ROUNDS`, `round_named`, `round_evidence_root` and `guard_for_round` (round-aware `score_mod._guard_from_args` is already in place) and wire `--round`, `--vetoes` and the v4 decision into `forecast_shadow_confirm.py`.
- `forecast_shadow_confirm.py` still passes `args.evidence_root` unchanged to the one-shot check; 07-07 must switch it to the round subroot so the one-shot rule is per round there as well.
- The v3 `apply_ship_rule` call in `forecast_shadow_score._attach_family_and_decision` and the `decision_margin_amps` parameter are left for 07-07.

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*

## Self-Check: PASSED

- FOUND: backend/forecast_shadow_eval_core.py, backend/forecast_shadow_score.py, the four test files, this summary
- FOUND commits: 15504d5, 6e4474c (both ancestors of HEAD)
- Acceptance criteria re-run: `PROTOCOL_ROUNDS`/default/fetch end print `['v4-late-descriptive', 'v4-read1', 'v4-read2'] 2026-11-01T00:00:00+00:00 2026-10-24`; `grep -c "if now_ts < instant and override is None"` is 0; `grep -n "2026-11-24"` over the three test files prints nothing; `--help` lists `--round {v4-late-descriptive,v4-read1,v4-read2}`; collected tests 189 -> 227
- Plan verification: full suite 2279 passed, 82 skipped; dry-run exit 0
