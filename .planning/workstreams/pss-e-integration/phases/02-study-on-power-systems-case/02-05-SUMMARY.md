---
phase: 02-study-on-power-systems-case
plan: 05
subsystem: psse-job-margin-dispatch
tags: [pss-e, voltage-stability, transfer-search, bisection, dispatch, power-factor, stdlib, python37]
requires:
  - phase: 01
    provides: "units.circuit_amps, circuit_mva and mva_to_circuit_amps; run_record.finite and validate_results; contract.StudyFailed and the column tuples; the 3.7 syntax and import gate"
  - phase: 02
    provides: "plan 02-02 PsseApi (load_case, define_subsystem, scale_load, solve, bus_table, branch_loading) and the fake psspy; plan 02-03 BaseCase, CityBase, Budget, prepare_base and cleanup_base"
provides:
  - "psse_job.margin: SINK_SID, Point, Limit, MarginResult, NoTransferBound, find_transfer_limit (pure), city_margin"
  - "psse_job.dispatch: POWER_FACTOR_DEFAULT (copy of config.POWER_FACTOR), BOUNDS, build_dispatch_row, dispatch_details"
  - "backend/tests/psse_margin_test.py: 22 tests (STU-03); backend/tests/psse_dispatch_test.py: 10 tests (STU-04 and the power-factor drift guard)"
affects: [02-06, 02-07]
tech-stack:
  added: []
  patterns:
    - "the transfer cap is only a starting cap: the walk continues in the same step for transfer.extra_steps more steps and ends at the applied rating or a real bound, else the stage fails"
    - "reload base.saved_path and redefine the sink subsystem before every evaluation (process-global PSS/E state)"
    - "a copy of a config constant lives in the new job module and a test (which may import config) pins it, so no Phase 1 file changes"
key-files:
  created:
    - backend/psse_job/margin.py
    - backend/psse_job/dispatch.py
    - backend/tests/psse_margin_test.py
    - backend/tests/psse_dispatch_test.py
  modified: []
key-decisions:
  - "The reason of a search that ends on a bad point is that of the bad point nearest the limit (the last bad point of the bisection), not the first bad walk step, because the nearer point is the one that actually bounds the good point"
  - "The cap in steps is floor(max_mw / step_mw) (the plan's 'while d + step <= max'); the extra steps are counted from there, so for a cap that is not a multiple of the step the walk takes at most floor(max/step) + extra_steps steps (never more than the plan's ceil-based bound)"
  - "The flat-transfer guard also runs when the search finds no bound, so a flat transfer is reported as 'does not load the mapped branches' and not as 'no bound found'"
  - "build_dispatch_row refuses an unknown bounded_by (BOUNDS) so a misspelt 'dlr_rating' cannot slip past the tripwire"
requirements-completed: [STU-03, STU-04]
duration: 1h 30m
completed: 2026-10-28
status: complete
commits: 3
plan_head_before: e4331b04286519edf79cfa195f6531c38fe72e35
plan_head_after: 7f0d4d1e280c43ec65f0f34833d7e24fa732bcd0
actuals:
  tokens: 12400
  tasks: 3
  commits: 3
---

# Phase 2 Plan 05: Voltage-stability margin and dispatched capacity Summary

**`city_margin` finds each city's transfer limit with a walk-and-bisection search on plain load flows (the 1000 MW cap is only a starting cap, so a fresh EL_PASO rating is dispatched in full as `dlr_rating` instead of an understated `voltage_stability` figure), and `build_dispatch_row` turns that limit and the applied rating into the dispatched capacity in MVA, amps and MW with the tie going to the DLR rating.**

## Accomplishments
- `margin.find_transfer_limit` (pure): base point, a walk by `transfer.step_mw` to the starting cap and then up to `transfer.extra_steps` further steps, bisection to `transfer.tolerance_mw` after a bad point. It returns `Limit(base, good, bounded_by, evaluations, first_bad_mw, extended)` with `bounded_by` one of `base_case`, `dlr_rating` (on the walk or during the bisection), `non_convergence`, `voltage_criterion`; there is no `max_transfer`. A walk with no bound and the flow below the rating raises `NoTransferBound(steps, last_increment_mw, last_flow_mva)`.
- `margin.city_margin(base, city)`: per evaluation `budget.check`, reload `base.saved_path`, `define_subsystem(SINK_SID, sink_buses)`, `scale_load` when the increment is above 0, strict solve; non-convergence or a monitored bus below `collapse_voltage_pu` is `non_convergence`, a minimum monitored voltage below `contingency_low_pu` is `voltage_criterion`. The row is keyed by `MARGIN_COLUMNS` (method `pv_curve`, base and limit transfer as summed absolute P of the mapped branches, `margin_pct` null below 0.1 MW of base, `voltage_limit_mva` the largest mapped MAXMVA at the last good point, details with the 12 plan keys, every float through `run_record.finite`). Failures are `StudyFailed("voltage_margin", "<city>: ...")`: no bound within cap plus extra steps (message names `transfer.max_mw` and `transfer.extra_steps` and the settings to raise), a flat transfer, no flow at the limit, a budget overrun, any `PsseCallError` (for example `scal_2` ierr).
- `dispatch.build_dispatch_row(choice, line_voltage_kv, voltage_limit_mva, power_factor=None, details=None, bounded_by=None)`: dispatched MVA is `min(applied, voltage limit)`, amps through `units`, MW = MVA x 0.95 (`POWER_FACTOR_DEFAULT = 0.95`, a copy pinned to `config.POWER_FACTOR` by `test_dispatch_power_factor_copy_matches_config`), `limiting_factor` `dlr_rating` on a tie, the city_rating link only for a city_rating source, and a `ValueError` tripwire for `bounded_by="dlr_rating"` with a voltage limit below the applied MVA.
- Placeholder numbers reproduce the plan exactly: AUSTIN `voltage_criterion`, base transfer 310 MW, limit 474 to 475 MW, `voltage_limit_mva` 499 to 500, critical bus 90002, dispatch `voltage_stability` at about 500 MVA (836.74 A per circuit, 418.37 A per conductor, 475 MW). EL_PASO with today's static rating: `dlr_rating` at the 900 MW step, `extended_past_cap` false, limit 800.0. EL_PASO with a fresh 1.1 x static row (867.65 MVA): passes the 1000 MW cap (852.63 MVA, 0.957 pu), stops at 1050 MW with limit 878.95, `extended_past_cap` true, dispatch 867.65 MVA `dlr_rating`; with `extra_steps` 0 the stage fails naming the settings.

## Task Commits
1. Task 1 (tracer): `019a373` feat(02-05): tracer - AUSTIN voltage margin on the placeholder case and its dispatch row, both accepted by validate_results
2. Task 2: `fd52e0c` feat(02-05): margin search against an analytic two-bus model, every stopping reason, the cap that never stops a search and the flat-transfer guard
3. Task 3: `7f0d4d1` feat(02-05): dispatched capacity rows pinned edge by edge and the power-factor copy pinned to config

## Verification
- `psse_margin_test.py -k tracer`: 1 passed. `-k "search or city"`: 21 passed (plan minimum 20; the evaluation-bound test has two parametrized caps, 400 and 410). `-k "fresh_rating_extends or not_bounded"`: 3 passed. `-k two_bus`: 2 passed. Whole module: 22 passed.
- `psse_dispatch_test.py`: 10 passed (plan minimum 10); `-k "power_factor_copy or rating_bound"`: 2 passed.
- `psse_contract_test.py psse_margin_test.py psse_dispatch_test.py psse_study_test.py`: 78 passed. Wider psse suite (`+ psse_mapping_test psse_api_test psse_contingency_test psse_job_test psse_ratings_test psse_writer_test psse_run_record_test`): 383 passed, 28 skipped (Postgres-backed; no Postgres needed by this plan, none started).
- The own-changes gate over `study.py`, the fake psspy, `constants.py`, `psse_contract_test.py`, `config.py`, `supabase/migrations`, the production-pipeline plans and the DDL file and its doc exits 0 for all three plan commits (the four files this plan touches are all new).
- Red first: Task 1's tracer failed at import (`cannot import name 'dispatch'`) before any code existed; in Task 2 the two flat-transfer tests were red (message was "no voltage, convergence or rating bound") before the guard and the other 20 passed; in Task 3 `test_dispatch_details_shape` was red against the first-version `dispatch_details` and the other 9 passed.
- Mutation checks (each turned the named test red; both modules restored byte-for-byte, verified by byte comparison and an empty `git diff` on `backend/` afterwards; a control run of the 32 tests was green before and after): accept a flat transfer (test_city_flat_transfer_fails); give a tie to voltage_stability (test_dispatch_tie_goes_to_dlr_rating); skip bisection (test_search_two_bus_nose_within_tolerance); skip the reload before an evaluation (test_city_reloads_base_and_redefines_subsystem_each_evaluation); apply the power factor to dispatched_mva (test_dispatch_voltage_limited_amps_and_mw); stop the walk at transfer_max_mw and report the last good point (test_city_el_paso_fresh_rating_extends_past_cap_to_dlr_rating and test_search_bounded_by_variants[dlr_rating_after_cap], 2 failed, the other 4 variants still passed). Harness: `scratchpad/mutate_0205.py`, run with `-B`, environment unstripped, so no stray directory appeared.

## Deviations from Plan

### Auto-fixed Issues
None.

### Notes (choices inside the plan's latitude, not deviations of behaviour)
- **Extra validation in `build_dispatch_row`:** an unknown `bounded_by` raises `ValueError` (the plan names only the `dlr_rating` tripwire). The vocabulary is `dispatch.BOUNDS`, equal to `margin.Limit.bounded_by`'s four values.
- **Guard also on the no-bound path.** The plan places the flat-transfer guard "after the search". A flat transfer never finds a bound, so without this the required message ("does not load the mapped branches") could never appear for a solver that ignores the sink load; the guard now runs before the no-bound message too. Cost: a flat transfer spends cap plus extra steps of solves (about 120 with defaults) before failing, bounded by the budget; an early abort on the first positive step was not added.
- **Bound reason from the nearest bad point.** The research code reported the first bad walk step's reason; the search reports the reason of the last bad point of the bisection, the one adjacent to the limit.
- **Extra tests beyond the plan's list:** none by name; `test_search_evaluations_bounded` runs for two caps (400 and 410) so one is not a multiple of the step.
- **Bash:** one empty python heredoc was run by mistake (it started an interactive interpreter that read nothing and wrote nothing). All file content went through Write/Edit. STATE.md, ROADMAP.md and REQUIREMENTS.md were not updated, per the user's rules; `.planning/config.json`, `milestone.lock` and `state.json` remain uncommitted.

## Known Stubs
None.

## Threat Flags
None. The modules add no filesystem, network or auth surface; they read and change the working case only through `base.api` and reload the private temp file of plan 02-03. T-02-22 to T-02-26 and T-02-37 are mitigated, each with its named test; T-02-25 through `test_dispatch_power_factor_copy_matches_config`.

## Hand-off notes for later plans
- `city_margin(base, city)` returns `MarginResult(row, voltage_limit_mva, bounded_by)`; the row has no `run_id` or `run_outcome`. It leaves the working case reloaded to the saved base. The caller owns `study.cleanup_base(base)`.
- For the dispatch row call `dispatch.build_dispatch_row(selection.choices[city], base.cities[city].line_voltage_kv, result.voltage_limit_mva, details=dispatch.dispatch_details(base.cities[city], base.settings.rate_sets, result.bounded_by), bounded_by=result.bounded_by)`. Always pass `bounded_by`; without it the tripwire is off. A `ValueError` from it is a code bug or an inconsistent search and belongs to stage `dispatch` (`StudyFailed("dispatch", ...)`), not a crash.
- The margin and dispatch rows of a city carry the same `voltage_limit_mva` by construction (`result.voltage_limit_mva` is the row's value).
- `NoTransferBound` never escapes `city_margin`: it becomes `StudyFailed("voltage_margin", ...)`. A flat or loadless sink fails at the same stage, as does a margin with no flow at its limit.
- With the defaults a city's search costs at most 1 + 40 + 80 walk evaluations plus about 5 bisection evaluations, each a reload and a solve; `base.budget` is checked before every one.
- The sink and source of the transfer (research open question 4) remain the researched default (the mapping's `sink_buses`, the swing bus absorbing); the real search is not exercised against real PSS/E until the laptop probe (plan 02-07).

## Self-Check: PASSED
- FOUND: backend/psse_job/margin.py, backend/psse_job/dispatch.py, backend/tests/psse_margin_test.py, backend/tests/psse_dispatch_test.py
- FOUND commits: 019a373, fd52e0c, 7f0d4d1 (each an ancestor of HEAD); measured `git rev-list --count` from the ledger base is 3
