---
phase: 01-pss-e-reference-session-and-network-parity
plan: 08
subsystem: testing
tags: [pandapower, net-03, comparator, d-13, scaling, load-flow, pse-02, injected-snapshot]
status: complete

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: RAW parser, network builder and synthetic fixtures (01-06); the session's base.json, settings.json, fingerprint and experiments.json shapes (01-03, 01-04)
provides:
  - backend/pandapower_job/scaling.py, scale_city, inject_snapshot and analyse_scaling_details with named thresholds
  - backend/pandapower_job/solve.py, run_load_flow with the convergence rule, classify_var_limits and settings_from_session
  - backend/pandapower_job/compare.py, the D-13 rule stated once, compare_city, the explained-differences registry and net03_verdict
  - backend/tests/pandapower_compare_test.py, 22 tests of NET-03 and the PSE-02 analyser on synthetic data
affects: [01-09, 01-10, 01-11]

plan_head_before: f9839d1a849a3458b67664ca71ec33d4b6b7c1a7
plan_head_after: e175a0cef9f3f16cdcc8cbd47d7af9008d9bd38d
actuals:
  tokens: 27400
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Tolerances written once as four module constants in compare.py; an AST test proves the numbers appear nowhere else"
    - "Incomplete is never a pass: complete is False for a missing reference, unsolved net, unavailable transformer flows, a one-sided element or a missing reference value"
    - "Registry entries explain exact (element, quantity) pairs up to a measured size and never move a tolerance; the registry is data handed in"
    - "Defaults for unread settings are read from pandapower's runpp signature, never copied into this repo"
    - "Verdicts hold element keys for private reports; render_counts holds counts and pass or fail only"

key-files:
  created:
    - backend/pandapower_job/scaling.py
    - backend/pandapower_job/solve.py
    - backend/pandapower_job/compare.py
    - backend/tests/pandapower_compare_test.py
  modified: []

key-decisions:
  - "Both tolerance bounds carry COMPARISON_EPSILON (1e-12) so exactly 0.01 pu and exactly 2 percent pass; a test fails if the epsilon is removed"
  - "A run label 'algorithm' or 'algorithm:<label>' counts toward NET-03; an inconclusive var-limit classification is run both ways under labels such as algorithm:enforce_q_lims_on and every one must pass; the injected run never counts for or against"
  - "Q is gated only when the reference has it; with transformer flows unavailable only lines are compared (P and larger-end flow) and the verdict is incomplete"
  - "For clamping, a mixture (some candidate machines at the limit, some above) is inconclusive, and a candidate machine is one the factor pushes past its P maximum by more than MW_TOLERANCE; one decisive clamp experiment stands when the other has no evidence or failed, opposite answers are inconclusive"
  - "scale_city skips the generation read-back when clamping held a machine, because the total falls short of the target by design"
  - "classify_var_limits judges a point only from default vs immediate vs ignore; decisive points that disagree raise ValueError naming the conflict and settings_from_session lets it propagate (a D-14 human decision)"

requirements-completed: [NET-03, PSE-02]

coverage:
  - id: D1
    description: "A city's scaled copy is made from its targets, solved under settings copied from the session and compared under D-13: a self-consistent synthetic reference passes complete with every bus and flow compared, a bus raised by 0.011 pu fails"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_tracer_scaled_city_solve_and_compare_on_synthetic_data"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-13 boundaries (0.01 pu, 2 percent, 2 MVA floor), zero and out-of-service flows, order independence, and tolerances defined once"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_d13_boundaries"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_zero_and_out_of_service_reference_flows"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_shuffled_reference_gives_an_equal_verdict"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_tolerances_are_defined_once"
        status: pass
    human_judgment: false
  - id: D3
    description: "An incomplete comparison is never a pass, and NET-03 needs four complete passing cities (one incomplete city gives cities_complete 3)"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_incomplete_comparisons_never_pass"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_net03_verdict_needs_four_complete_passing_cities"
        status: pass
    human_judgment: false
  - id: D4
    description: "No tuning: the registry explains only exact listed entries with a cause and a size, refuses bad entries, and the comparator leaves every table of the net unchanged"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_registry_explains_only_exact_listed_entries"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_registry_refuses_bad_entries"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_compare_reads_the_net_only"
        status: pass
    human_judgment: false
  - id: D5
    description: "Solve settings are copied (D-14) with recorded deviations, var limits classified on, off or inconclusive with boundaries, and the convergence rule rejects NaN and collapsed voltages"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_settings_are_copied_with_recorded_deviations"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_var_limit_classification_boundaries"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_convergence_rule_nan_and_collapse"
        status: pass
    human_judgment: false
  - id: D6
    description: "The three scaling details are classified from the session's experiments with every threshold tested at, inside and outside, print rounding equal, and failed experiments inconclusive"
    requirement: "PSE-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_swing_in_total_classification"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_clamping_classification"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_q_with_p_classification"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_print_rounding_classifies_as_equal"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_failed_experiment_is_inconclusive"
        status: pass
    human_judgment: false
  - id: D7
    description: "A wrong swing flag fails the algorithm run while the injected PSS/E-values run passes; scaling refusals and clamping behave as stated"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_injected_run_localises_a_wrong_scaling_flag"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_compare_test.py#test_scale_city_refusals_and_clamping"
        status: pass
    human_judgment: false

duration: 75min
completed: 2026-11-16
---

# Phase 1 Plan 08: Scaling, solve and comparison Summary

**The NET-03 machinery proven on synthetic data: a city's scaled copy solved under session-copied settings and compared under the D-13 rule held in four constants, with incomplete comparisons failing, explained differences limited to exact written entries, and an injected-snapshot run that tells a wrong scaling rule from a wrong network.**

## Performance

- **Duration:** about 75 min (interrupted once by a rate limit and resumed)
- **Completed:** 2026-11-16
- **Tasks:** 3 (one tracer, two auto with tdd)
- **Files created:** 4 (3 production, 1 test)

## Accomplishments

- `compare.py` states D-12 and D-13 once. Voltage within 0.01 pu, flow within max(2 percent of the reference, 2 MVA), both inclusive with a 1e-12 slack, applied to every in-service bus and, per branch, to signed from-end P, from-end Q when the reference has it and the larger-end apparent flow, joined by bus number and from-to-ckt key.
- `compare_city` returns a `CityVerdict` that is `complete` only for a usable reference, a solved net, transformer flows from the session and identical element sets; `net03_verdict` passes only for four complete passing algorithm-run cities.
- `solve.py` copies `tolerance_mva` and `max_iteration` from the session, takes `enforce_q_lims` from the var-limit fingerprints (None means run both), records every default used as a D-14 deviation and applies a convergence rule that also rejects NaN voltages and voltages below the collapse limit.
- `scaling.py` reproduces the scal_2 rules from the measured details with the factor bounds and read-back tolerance imported from `psse_job.study`, classifies the three details offline, and `inject_snapshot` copies PSS/E's own post-scaling values by name.

## Task Commits

1. Task 1 (tracer): `200e1e5` feat(01-08): tracer - scale, solve and compare one synthetic city under D-13
2. Task 2: `ace2708` test(01-08): comparator edges, registry, verdict and copied settings
3. Task 3: `e175a0c` test(01-08): scaling-detail analyser and the injected-snapshot diagnostic

Verification: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_compare_test.py backend/tests/pandapower_network_test.py backend/tests/pandapower_raw_test.py` gave `100 passed` with nothing skipped (the compare file alone: 22 passed). The staged leak scan exited 0 before every commit and the full scan exits 0. The frozen-file gate exits 0 for all three commits. Mutation spot checks (dropping the comparison epsilon, `<` instead of `<=` in the registry, zero boundary slack) each made a test fail.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Frozen fixture reads transformer results with line column names**
- **Found during:** Task 1
- **Issue:** `pandapower_fixture.reference_from_solved` (plan 01-06, frozen for this plan) reads `p_from_mw` and friends from `net.res_trafo`, which has `p_hv_mw`, `q_hv_mvar`, `p_lv_mw`, `q_lv_mvar`. It raises AttributeError on any net with a transformer; plan 01-06's tests never called it on a solved net.
- **Fix:** the test helper `_reference` aliases the transformer result columns to the line names on a copy before calling the fixture (the same numbers, hv end as the from end). `compare.py` reads the correct transformer columns itself. The fixture is untouched.
- **Files modified:** backend/tests/pandapower_compare_test.py
- **Commit:** 200e1e5
- **Follow-up for the orchestrator:** plan 01-09 or 01-10 should fix `reference_from_solved` if anything else calls it on a net with transformers.

**2. [Rule 1 - Test data] Synthetic tracer needs room under the machines' P maximum**
- **Found during:** Task 1
- **Issue:** several 39-bus machines sit at their P maximum, so any generation factor above one passes a limit and `scale_city` (correctly) refuses when the clamp detail is inconclusive.
- **Fix:** the tests build their network from records with every machine's PT raised to 5000 MW; clamping behaviour has its own tests with a binding limit.
- **Commit:** 200e1e5

### Interpretation choices (plan text was silent or ambiguous)

- Clamping with a mixture of held and above-limit machines is inconclusive rather than "no", so a partial effect never tells Phase 2 to skip clamping.
- Where the plan names `FINGERPRINT_TOLERANCE_PU` beside the scaling thresholds, it lives in `solve.py` as the interface list says; the threshold-value test pins all four.
- Added two tests beyond the named ones: `test_scale_city_refusals_and_clamping` and `test_threshold_values_are_the_plans` (the boundary tests are written against the constants, so a separate test pins the values).

None of these changes scope or architecture.

## Known Stubs

None.

## Threat Flags

None. No new network, auth, file-access or schema surface. The registry is read as parsed data only; file loading is plan 01-09's.

## Issues Encountered

- The sandbox refuses compound shell lines that mention git, so the frozen-file gate and root-pin guard were run from scripts in the scratchpad and commits were made with plain separate commands.

## Next Phase Readiness

Plan 01-09's CLI can call `settings_from_session`, `scale_city`, `run_load_flow`, `compare_city` (algorithm and injected runs), `load_registry` and `net03_verdict`. For an inconclusive var-limit classification, solve and compare twice and label the runs `algorithm:<label>`. Nothing here has met PSS/E's real answers; plan 01-10's data decides whether NET-03 actually passes.

## Self-Check: PASSED

- FOUND: backend/pandapower_job/scaling.py, solve.py, compare.py and backend/tests/pandapower_compare_test.py
- FOUND commits 200e1e5, ace2708 and e175a0c, all ancestors of HEAD
