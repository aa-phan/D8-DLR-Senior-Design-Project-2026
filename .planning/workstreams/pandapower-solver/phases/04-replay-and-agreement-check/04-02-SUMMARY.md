---
phase: 04-replay-and-agreement-check
plan: 02
subsystem: agreement-rules
tags: [pandapower, agreement, gate, tolerances, margin-floor, counts-only-summary, pure-module]

requires:
  - phase: 01 (pandapower-solver)
    provides: pandapower_job.compare tolerances (VOLTAGE_TOLERANCE_PU, FLOW_RELATIVE_TOLERANCE, COMPARISON_EPSILON, within_voltage, within_flow, flow_allowance)
  - phase: pss-e-integration
    provides: psse_job.constants vocabularies, contract.StudyResults and the stored row shapes
provides:
  - backend/pandapower_job/agree.py - Side, Finding, Deviation, RunComparison, Summary, Detail, Gate; side_from_recorded, side_from_results, compare_run, replay_failed, gate, tolerance_header, margin_allowance; the closed vocabularies
  - the D-02 margin rule (one function, margin_allowance) and the D-04 gate rule (one function, gate)
affects: [04-03 replay and CLI (uses compare_run, replay_failed, gate; prints only Summary), 04-04 private report (uses Detail and tolerance_header)]

actuals:
  tokens: 15547
  tasks: 3
  commits: 3
plan_head_before: ea75e954cd9f9f178b11bea7a0a13f8591058abe
plan_head_after: d22bf957897ed48204769a4fc1401c74d988fc18

tech-stack:
  added: []
  patterns:
    - "Tolerances imported by name from compare.py; an AST test (with planted-literal checks) proves agree.py writes none"
    - "Summary is a namedtuple whose constructor rejects anything but integers and closed-vocabulary words; every value, element and run id lives in Detail"
    - "A matrix of (name, mutation of a synthetic run, expected class, expected check) with the value just inside and just outside each tolerance"

key-files:
  created:
    - backend/pandapower_job/agree.py
    - backend/tests/pandapower_agree_test.py
  modified: []

key-decisions:
  - "Base-case margins (bounded_by base_case) are compared like voltage-bound ones (floor is the stored tolerance, min_voltage_pu and voltage_limit_mva compared), because the base point (transfer 0) is not quantised; the plan named only the rating and voltage classes."
  - "limit_transfer_mw is judged against margin_allowance of its own recorded value (the plan said margin_mw and limit_transfer_mw 'within it'); a larger value gets a larger 2 percent."
  - "A missing stored detail equals a missing stored detail (both None or both absent is the same input); present against missing is a data failure."
  - "Unknown exclusion reason raises ValueError so an exclusion is never silently miscounted."

requirements-completed: [AGR-02]

duration: 30min
completed: 2026-11-20
status: complete
---

# Phase 4 Plan 02: Agreement Rules and Gate Summary

**`agree.py` is the pure comparison of one recorded PSS/E run against one replayed run (sets, values, margins with the D-02 resolution floor, dispatch, borderline limits) and the D-04 gate that can say pass, fail or incomplete and returns a summary that cannot hold a figure.**

## Accomplishments

- `compare_run(recorded, replayed)` compares per outage the overload, voltage-violation and non-convergence sets and their values (`within_flow` for thermal, `within_voltage` for the two voltage kinds), then per city the input data, the margins and the dispatch. Findings are `failure` or `borderline`, each with a closed check word; `where` and `detail` are private.
- D-02: `margin_allowance(ref, resolution)` is `max(FLOW_RELATIVE_TOLERANCE * abs(ref), resolution)` with the recorded step for a rating-bound search and the recorded tolerance otherwise; the comparison is inclusive with `COMPARISON_EPSILON`. Rating-bound runs do not compare `min_voltage_pu` and `voltage_limit_mva` (counted as `margin_quantised`).
- Borderline: a one-sided thermal or voltage row within `flow_allowance(limit)` or `VOLTAGE_TOLERANCE_PU` of its limit, and a limiting-factor change whose applied rating sits within the flow band of the voltage limit on either side. Everything else, any one-sided non-convergence row, a different margin class, different search settings or different input data is a failure.
- D-04: `gate(compared, exclusions, runs_in_snapshot, configurations)` returns pass only with a replayed run, a non-empty set comparison and no failure; a failure beats incomplete, incomplete beats pass. `Summary` holds counts and fixed words (including `not_exercised`, a count per exclusion reason, `failed_stages`, `data_differences`, `runs_disagreeing`); `Detail` holds the largest deviation (also on a pass), the worst per quantity, the largest borderline excess against its band, every finding, the exclusions and the summed notes.
- `replay_failed(stage)` is a failed run (stage outside `constants.FAILED_STAGES` is stored as `internal`); `tolerance_header()` returns the four compare constants, the margin and borderline rules as text and the data identity tolerance.

## Built vocabularies

- `CHECK_WORDS` (20): n_contingencies, city_rows, duplicate_key, rating_data, branches, rate_before, sink_buses, search_settings, rate_set, limit_value, element_fields, set_one_sided, convergence_one_sided, value_thermal, value_voltage, margin_bound_class, margin_value, dispatch_value, limiting_factor, replay_failed.
- `DATA_CHECK_WORDS` (8): rating_data, search_settings, branches, rate_before, sink_buses, rate_set, limit_value, element_fields.
- `COMPARE_COUNT_KEYS` (11): outages_thermal_overload, outages_voltage_low, outages_voltage_high, outages_non_convergence, pairs_compared, agreeing_keys, borderline, margin_comparisons, margin_quantised, dispatch_comparisons, dispatch_informative.
- `EXCLUSION_REASONS` (7), `NOTE_WORDS` (bound_member_differs, critical_bus_differs), `QUANTITIES` (8), `VERDICT_WORDS` (pass, fail, incomplete), `DATA_RELATIVE_TOLERANCE` 1e-6, `LIMIT_RELATIVE_TOLERANCE` 1e-9 (identity tolerances of inputs, not study tolerances).
- `Summary` fields: word, runs_in_snapshot, runs_replayed, runs_passed, runs_failed, excluded, configurations, nonempty, not_exercised, pairs_compared, margin_comparisons, dispatch_comparisons, borderline, failed_stages, data_differences, runs_disagreeing; `Summary.as_dict()` gives an ordered dict for printing.

## Where a stored detail was missing

- `details` that is not an object is read as empty. Both sides missing `branches`, `rate_before_mva` or `sink_buses` count as the same; present on one side only is a `branches`, `rate_before` or `sink_buses` failure.
- A missing, non-finite or non-positive `step_mw` or `tolerance_mw` (either side), or a non-finite `criterion_pu`, is `search_settings`; the margin values of that city are then not compared (the floor cannot be derived), but the failure stands.
- A missing or unknown `bounded_by` is `margin_bound_class`. A missing or unknown `limiting_factor` is `limiting_factor`. A non-finite value in a compared pair is the failure of that quantity (never raises).

## Task Commits

1. **Task 1 (tracer): identical rows pass, one 3 percent change fails, through compare_run and gate** - `c886a3e` (feat)
2. **Task 2: full rule set, data reconciliation, D-02 margin floor, dispatch, borderline** - `0ba33de` (feat)
3. **Task 3: gate, counts-only summary, private detail, replay_failed, tolerance_header, purity and no-stray-tolerance proofs** - `d22bf95` (feat)

## Verification

- `pandapower_agree_test.py`: **112 passed, 0 skipped** (matrix of 98 rule cases plus 14 other tests; the first task's tracer is one of them).
- Plan verification set (`pandapower_agree_test.py`, `pandapower_compare_test.py`, `pandapower_import_gate_test.py`): **139 passed, 0 skipped, 0 failed**.
- `grep -c "compare\." backend/pandapower_job/agree.py` prints 22 (plan asked for 5 or more); `agree.py` is 636 lines and the test file 741.
- File-scope gate (PLAN=04-02) exits 0; staged leak scan exited 0 before each commit; full `private_leak_scan.py` exits 0.
- The no-stray-tolerance test is shown to fire by planting `0.01`, `0.02`, `2.0`, `1e-12` and `2` in a copy of the source.
- Tests were written together with the implementation in each task (the rule matrix was written before the Task 2 code was run, and all cases passed on first run); no mutation run against the shipped module beyond the planted-literal check.

## Deviations from Plan

### Auto-fixed Issues

None - no bug, missing-critical or blocking issue was found.

### Notes

**1. Plan assumption: base_case margin class.** The plan named only the rating and voltage classes for the value rules and gave `base_case` as "the base class" with no rule. The module treats it like the voltage class (floor is the stored tolerance; `min_voltage_pu` and `voltage_limit_mva` are compared) because the base point is not quantised. One place to change: `_compare_margin`.

**2. Plan wording: limit_transfer_mw allowance.** Each of `margin_mw` and `limit_transfer_mw` uses `margin_allowance` on its own recorded value. `base_transfer_mw` uses `compare.flow_allowance`.

**3. Commit ledger and commit count.** `.git/gsd-plan-head-before-04-02` held a stale base (`4faab3a`, not an ancestor of this branch), the collision seen in earlier plans, and plan 04-01 committed on the same branch in between. `commits` is therefore measured by `git rev-list --count --grep="(04-02)" ea75e95..HEAD` (3; the range holds 4 commits, one of them plan 04-01's), and `plan_head_before` is `ea75e95`, the commit under both plans' first commits.

**4. AGR-03 is half done here.** The rules half (gate, counts, not-exercised kinds, exclusions, largest deviation kept for the private report) is built; the report itself and the CLI printing are plans 04-03 and 04-04, so only AGR-02 is listed in `requirements-completed`.

## Known Stubs

None.

## Threat Flags

None. T-04-06 (vacuous pass) is covered by the gate tests; T-04-07 (widened tolerance) by the AST test, the absence of any tolerance parameter or flag and the margin floor read only from the recorded run; T-04-08 (disclosure) by the `Summary` constructor check, the leaf-walk test and the assertion that run ids, elements and values are absent from the summary text; T-04-09 (quantisation or permissive band) by the matrix edges and the test that data and class findings are never borderline; T-04-SC met (nothing installed).

## Self-Check: PASSED

- FOUND: backend/pandapower_job/agree.py, backend/tests/pandapower_agree_test.py, this summary
- FOUND commits c886a3e, 0ba33de, d22bf95 (ancestors of HEAD)
