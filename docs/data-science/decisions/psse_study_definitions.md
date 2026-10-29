# PSS/E study definitions

**Date:** 2026-10-28
**From:** pss-e-integration Phase 2 (IN-03, STU-01 to STU-04, TST-01)
**To:** Power Systems (the definitions), the project owner (the defaults), Phase 3 (the laptop checks)
**Status:** what the code implements today; every default below is an assumption, not a decision of Power Systems

## Scope and where the code lives

This note states each definition the PSS/E study uses, so an engineer can review it without reading the code. It also says what the tests prove and what they cannot. A test file, `backend/tests/psse_study_doc_test.py`, keeps the settings table and the worked numbers equal to the code.

The study runs on the licensed laptop, where `psspy` can be imported. The study code never imports `psspy` itself: the launcher (Phase 3) imports it and hands the module to the code. The launcher's call is:

```python
prepared = study.prepare_run(psspy, case_path, mapping_path)
job.run_once(fetch, prepared.study, connect, prepared.case_id,
             prepared.case_sha256, prepared.mapping_sha256)
```

`prepare_run` reads and checks the mapping file, hashes the case and the mapping, and returns the study to run. `run_once` selects the ratings, runs the study once, checks the result and writes it in one transaction.

Two clocks exist and they are different. The `clock` argument of `prepare_run` and `make_study` is the run-time budget's monotonic clock (default `time.monotonic`). The `clock` argument of `run_once` returns an aware datetime and sets the run's start time. Do not pass one where the other is wanted.

| Module (`backend/psse_job/`) | What it does |
|---|---|
| `mapping.py`, `settings.py` | Read and validate the mapping file and the `study` settings; hash the file |
| `psse_api.py` | The only code that names `psspy` functions; one row per function in the `SURFACE` table |
| `ratings.py` | Chooses each city's rating (the `city_rating` row or the static fallback) |
| `study.py` | `prepare_run`, `make_study`, `prepare_base`: checks the mapping against the case, writes the ratings, solves and saves the base |
| `contingency.py`, `violations.py` | The N-1 branch-outage screen and its violation rows |
| `margin.py` | The voltage-stability margin search |
| `dispatch.py` | The dispatched-capacity row |
| `probe.py` | The one-off laptop probe that compares the fake with the real `psspy` |
| `job.py`, `writer.py`, `run_record.py` | Phase 1: one run, the record and the database write |

## Rating conversion (IN-03)

The job reads the city's rating in amperes per conductor and writes a rating in MVA per circuit to PSS/E:

    circuit MVA = sqrt(3) x kV x amps per conductor x subconductors / 1000

- There is no power factor in the conversion. PSS/E branch ratings are apparent power.
- kV is the base kV of the mapped branch's from bus, read from the case. Both ends of a mapped line must have the same base kV, or the mapping fails.
- All mapped branches of one city must share one base kV, because the result tables store one `line_voltage_kv` per city. A city with mixed base kV fails the run at stage `mapping`.
- Every parallel circuit of a city receives the same per-circuit value. The value is not divided between circuits.
- The value goes to every rate set listed in `rate_sets`. The first listed set is the limit for every thermal check.
- After each write the job reads the rating back. A difference above 1e-6 of the value (relative) fails the run at stage `apply_ratings`.
- A rating of zero means "no limit" in PSS/E, so the job never writes zero, a negative number or a number that is not finite.
- The rating the case already had on the first listed rate set is kept as `rate_before_mva` in the dispatch row's details, so Power Systems can see what was replaced.

Worked numbers at a nominal 345 kV (the static ratings). The job uses the case's own base kV, not 345.

| City | A per conductor | Subconductors | A per circuit | MVA per circuit at 345 kV |
|---|---|---|---|---|
| AUSTIN | 1825.0 | 2 | 3650.0 | 2181.1 |
| CORPUS_CHRISTI | 1500.0 | 2 | 3000.0 | 1792.7 |
| MIDLAND | 1875.0 | 2 | 3750.0 | 2240.8 |
| EL_PASO | 1320.0 | 1 | 1320.0 | 788.8 |

`backend/tests/psse_study_doc_test.py` recomputes these four values with `units.circuit_mva`. The values on the real network depend on the base kV in the case; that is why Phase 3 reads one branch with a known flow (see "Phase 3 confirmations").

Today every `city_rating` row is provisional, so the rating written is the static rating with fallback reason `provisional`. The rule is in the Phase 1 specification, [psse_results_v1.md](../schema/psse_results_v1.md).

## Convergence (STU-01)

- A load flow counts as converged only when `fnsl` returns 0 and `solved()` then returns 0. Every other value is not converged.
- After a failed `fnsl`, `solved()` describes an older attempt, so it is never trusted.
- The `solved()` codes are taken from the PSS/E 33.5 manual: 0 met the tolerance, 1 iteration limit, 2 blown up, 3 terminated by the non-divergent option, 4 console interrupt, 5 singular Jacobian or zero voltage, 6 inertial dispatch error, 7 OPF met tolerance (not accepted here), 9 not attempted. Only 0 is success.
- The base case also fails (stage `load_flow`) when the system mismatch exceeds `max_mismatch_mva`, or when any in-service bus is below `collapse_voltage_pu` (a collapsed solution).
- In an outage or a transfer step, a solve that does not converge, or converges with a monitored bus below `collapse_voltage_pu`, is data: a `non_convergence` row or the stopping point of the search.
- `fnsl` error 2 means the saved case has converted generators. The failure text says so, because the remedy is an unconverted case from Power Systems, not a change to the job.
- Known wart: when `fnsl` returns a non-zero error, the failure message still prints `solved=<number>`. That number is stale and is not used for anything. The text that follows it says `solved() is not trusted after a failed fnsl`. The wording is pinned by tests in plan 02-03, so it was left as written.

## N-1 screening (STU-02)

The screen trips one branch at a time. It is a loop of ordinary load flows, not PSS/E's ACCC module.

**Outage set.** Each mapped branch, plus every in-service line (not transformer) within `contingency.hops` branches (default 2) of a mapped branch's end buses, plus the lines listed in `contingency.extra`. With `contingency.scope` set to `all`, every in-service line. The set is sorted and has no duplicates. Zero outages, or more than `contingency.max` (default 200), fails the run at stage `contingency`; the screen is never cut short silently.

**Monitored set.** The lines of the same neighbourhood, and the buses of the neighbourhood that are in service and at or above `voltage.min_monitor_kv` (default 100), plus each city's sink buses at any voltage.

**Per outage.** Reload the saved solved base, set the branch out of service, solve under the convergence rule above, read the buses and the line loadings, evaluate. The saved base is reloaded before every outage and once at the end. An outage is never undone and re-solved, so a blown-up solution cannot affect the next outage.

**Thermal check.** Basis `current` by default: the larger-end percent of the current rating, read from PSS/E, on the first listed rate set. The limit is the rating times `thermal.limit_pct` (default 100) divided by 100. The observed value is the percent times the rating divided by 100, so it is current expressed in MVA of the rating. A line exactly at the limit is not a violation. A rating of zero, a line out of service and the outaged line itself are skipped. Basis `mva` uses the MVA percent instead.

**Voltage check.** Buses must be inside 0.90 to 1.05 pu after an outage (`voltage.contingency_low_pu`, `voltage.contingency_high_pu`) and 0.95 to 1.05 pu before it (`voltage.base_low_pu`, `voltage.base_high_pu`). With `voltage.source` set to `case`, the bus's own limits in the case are used when they are usable (two positive numbers, low below high), otherwise the configured pair. Isolated buses are skipped.

**Rows.** One row per violation: `thermal_overload` (branch, MVA), `voltage_low` or `voltage_high` (bus, pu), each with the limit, the observed value and `exceeded_by`. An outage that does not converge, or collapses, gives one `non_convergence` row with no values. A violation that already exists in the solved base case is still written, with `in_base_case` true and `base_value` in the row's details. A row names a city only when the element is one of that city's mapped branches, or a bus used by that city alone. `psse_run.n_contingencies` counts the outages screened. More than 5000 rows, a call failure during an outage, or an exhausted run-time budget fails the run at stage `contingency`.

**What is not done.** Transformer outages, generator outages, outages of several elements at once, and a screen of the whole system are not done. The result should not be called a full N-1 study until Power Systems agrees the scope.

## Voltage-stability margin (STU-03)

**Definition.** The margin is a load-transfer search made of ordinary load flows. For a transfer of d MW, for one city: reload the saved base, define subsystem 9 as the city's sink buses, raise their load by d MW at constant P and Q with one `scal_2` call, solve, and measure. Generation is untouched, so the swing bus supplies the increase. A city's transfer is the sum of the absolute active power at the from end of its mapped branches (assumption A18).

**Label.** The method label `pv_curve` is the DDL's conventional name for this load-transfer search on ordinary load flows. It is not a PSS/E PV-curve analysis. The PSS/E PV and QV engines need a licensed module and distribution-factor inputs, and are not used (question 6).

**Stopping rule.** A point is good when the load flow converged, no monitored bus collapsed and the lowest monitored voltage is at or above `voltage.contingency_low_pu`. The search steps up by `transfer.step_mw` (default 25). After a bad step it bisects to `transfer.tolerance_mw` (default 1). It stops at the first of these:

| `bounded_by` | Meaning |
|---|---|
| `base_case` | The base case already fails the criterion. The margin is 0. |
| `dlr_rating` | The largest per-circuit flow on the mapped branches reached the applied rating |
| `non_convergence` | The nearest bad point did not converge or collapsed |
| `voltage_criterion` | The nearest bad point had a monitored bus below the contingency low voltage |

**The cap.** `transfer.max_mw` (default 1000, or `transfer_max_mw` per city in the mapping file) is a starting cap, never a limit. If the walk reaches it with no bound found and the flow still below the rating, the walk continues with the same step for at most `transfer.extra_steps` more steps (default 80). If it still finds no bound, the run fails at stage `voltage_margin` and the message names the two settings. There is no "cap reached" outcome, because it could understate a voltage limit. This replaces the `max_transfer` outcome of the research. A capacity is reported as voltage-stability-limited only when a `non_convergence` or `voltage_criterion` bound was actually found. The row's details record `extended_past_cap`.

**Lower-bound semantics.** When the bound is `dlr_rating`, the search stopped because the rating binds, so the margin is "at least this much", not the voltage-stability nose. `details.lower_bound` is true then. That is what dispatch needs, because the dispatched capacity is the lower of the rating and the voltage limit.

**Quantities.** `base_transfer_mw` is the summed absolute from-end P at the base. `limit_transfer_mw` is the same at the last good point. `margin_mw` is the difference. `margin_pct` is empty when the base is below 0.1 MW. `critical_bus` and `min_voltage_pu` come from the last good point. `voltage_limit_mva` is the largest per-circuit apparent flow (`MAXMVA`) over the mapped branches at the last good point, in the same unit as `applied_mva`. The margin row and the dispatch row carry the same value.

**Flat-transfer guard.** If the mapped branches' power does not rise by at least `transfer.min_rise_fraction` (default 0.01) of the increment at the first good step, the transfer is not loading them (wrong sink, no scalable load, a parallel path takes it all). The run fails at stage `voltage_margin`; a flat flow is never reported as a limit.

## Dispatched capacity (STU-04)

Per city, per circuit:

- `applied_mva` is the rating written (the conversion above).
- `dispatched_mva` = the lower of `applied_mva` and `voltage_limit_mva`.
- `dispatched_amps_circuit` = `dispatched_mva` x 1000 / (sqrt(3) x kV); per conductor it is that divided by the subconductor count.
- `dispatched_mw` = `dispatched_mva` x power factor, with the power factor 0.95. The 0.95 is the project's convention, the same as the stored per-conductor `rating_mw`; it is stored in the row.
- `limiting_factor` is `dlr_rating` when `applied_mva` is at most `voltage_limit_mva` (a tie goes to the rating) and `voltage_stability` otherwise.

A margin that stopped on the rating (`dlr_rating`) cannot hold a voltage limit below the applied rating. The code refuses that combination rather than report an understated figure.

## Failure stages

Every failure of the study is one failed run record with no result rows. The stages the study uses:

| Stage | Condition |
|---|---|
| `load_case` | The case cannot be loaded, or its branch and bus tables cannot be read. The message holds the case file's base name only. |
| `mapping` | The mapping file cannot be read or is invalid, or is marked placeholder and refused. A mapped branch is missing, a transformer, out of service, or has ends or a city with different base kV. A sink bus is missing or isolated. An extra outage is not a line. Checked before anything is written to the case. |
| `apply_ratings` | The rating cannot be converted, a write call fails, or the read-back differs by more than 1e-6 relative |
| `load_flow` | The base load flow did not converge, or the mismatch is too large, or a bus collapsed, or the solved base cannot be read |
| `contingency` | No outage was selected, too many outages or rows, a call failed during an outage, the run-time budget was exhausted in the screen, or the solved base cannot be saved to the temporary file or reloaded |
| `voltage_margin` | No bound found within the cap plus the extra steps, a flat transfer, no flow at the limit, a call failure (for example `scal_2`), no monitored bus in service, or the run-time budget exhausted in the search |
| `dispatch` | The dispatch row cannot be built (for example a voltage limit that is not above 0) |

Three more stages belong to Phase 1 and are not raised by the study: `validate_results`, `write` and `internal`. The study saves the solved base to a private temporary file after the base solve and before the screen; a failure of that save is reported at stage `contingency`. The temporary files are removed on every path, and the case file is never saved over.

## Configuration

The mapping file has a required `cities` section (Power Systems' branch choices) and an optional `study` section (the settings). See [the placeholder example](../schema/psse_mapping_example.json): fake buses only, marked `"placeholder": true`. A refused placeholder fails the run at stage `mapping`. The file is capped at 65536 bytes, and bus numbers are whole numbers from 1 to 999999. One hash of the file is stored with every run, so it covers every number that shaped the result.

Per city: `branches` (from bus, to bus, circuit id; parallel circuits as separate entries), `sink_buses` (default: the to bus of the first branch) and `transfer_max_mw` (optional, the starting cap for that city).

The `study` settings. A key left out keeps its default. The "JSON path" is under `study` in the mapping file.

| JSON path | Settings field | Default | Meaning |
|---|---|---|---|
| `rate_sets` | `rate_sets` | `["RATEA"]` | Rate sets that receive the DLR value; the first is the limit of every check |
| `thermal.basis` | `thermal_basis` | `"current"` | Percent of rating by `current` or by `mva` |
| `thermal.limit_pct` | `thermal_limit_pct` | `100.0` | Overload limit, percent of the rating |
| `voltage.source` | `voltage_source` | `"config"` | Voltage limits from this table (`config`) or from the case (`case`) |
| `voltage.base_low_pu` | `base_low_pu` | `0.95` | Low voltage limit before any outage |
| `voltage.base_high_pu` | `base_high_pu` | `1.05` | High voltage limit before any outage |
| `voltage.contingency_low_pu` | `contingency_low_pu` | `0.9` | Low voltage limit after an outage; also the margin criterion |
| `voltage.contingency_high_pu` | `contingency_high_pu` | `1.05` | High voltage limit after an outage |
| `voltage.min_monitor_kv` | `min_monitor_kv` | `100.0` | Buses below this base kV are not monitored |
| `contingency.scope` | `contingency_scope` | `"neighbourhood"` | Outages near the mapped branches, or `all` lines |
| `contingency.hops` | `contingency_hops` | `2` | How many branches away from a mapped branch an outage may be |
| `contingency.max` | `contingency_max` | `200` | Most outages screened; more fails the run |
| `contingency.extra` | `contingency_extra` | `[]` | Extra lines to trip, as from bus, to bus, circuit id |
| `transfer.step_mw` | `transfer_step_mw` | `25.0` | Margin search step |
| `transfer.max_mw` | `transfer_max_mw` | `1000.0` | Starting cap of the search, never a limit (at most 10000) |
| `transfer.extra_steps` | `transfer_extra_steps` | `80` | Further steps allowed past the cap while no bound is found |
| `transfer.tolerance_mw` | `transfer_tolerance_mw` | `1.0` | Bisection tolerance |
| `transfer.min_rise_fraction` | `transfer_min_rise_fraction` | `0.01` | Flat-transfer guard |
| `solve.options` | `solve_options` | `null` | Eight integers for `fnsl`, or the program settings of the case |
| `solve.max_mismatch_mva` | `max_mismatch_mva` | `1.0` | Largest base-case mismatch accepted |
| `solve.collapse_voltage_pu` | `collapse_voltage_pu` | `0.5` | A bus below this voltage means a collapsed solution |
| `max_runtime_seconds` | `max_runtime_seconds` | `1500.0` | Run-time budget, checked between solves |

The launcher will read the case and mapping paths from the environment variables `PSSE_CASE_PATH` and `PSSE_MAPPING_PATH`. These names are planned for Phase 3 to implement; no Phase 2 code reads them.

The budget cannot interrupt a single `fnsl`. Phase 3 still needs a Task Scheduler time limit and a no-overlap rule.

## Private inputs

The real mapping and the real case carry grid element identifiers from Power Systems. This repository is public, so both stay outside it. A local directory, `psse_local/`, and the extensions `*.sav` and `*.raw` are git-ignored, so a file dropped there cannot be committed. Only the placeholder example is committed, and this note names placeholder buses only as the range 90000-99999.

The probe's report is also safe to paste: by default it holds no bus number, circuit id, path or exception text. Run it with `show_identifiers` left at its default, False, for anything that goes into the repository.

## What the fake proves and what it does not

The tests run the whole study against a fake `psspy`. The fake copies the call shapes of the `SURFACE` table and a small radial network.

**What the fake proves:**

- the arithmetic (the conversion, the dispatched capacity, the margin numbers on the fake network);
- control flow, the order of calls and the reload discipline;
- failure handling: each failure becomes one failed record with no result rows;
- the shape of every row, and that it passes the Phase 1 checks and the database;
- call shapes: every call is a `SURFACE` function with listed parameter names, and the case file is never saved over.

**What the fake does not prove:**

- that real PSS/E accepts these calls. `branch_chng_3` (its parameter list) and the combined `scal_2` form are UNVERIFIED in the `SURFACE` table; the other rows come from a manual, a reference and examples, not from this laptop;
- that units, margins and N-1 scope make engineering sense on Power Systems' network;
- run time on a real case.

All three are shown only by the laptop probe and a reviewed run in Phase 3.

Limits of the checks, stated plainly:

- The golden call-surface file pins the order of the functions and the keyword names, not every argument.
- Dropping the `bounded_by` argument from the `build_dispatch_row` call in `study.make_study` is an equivalent mutation to the end-to-end tests unless it is combined with a margin plant: the fake search never returns a bound that trips the tripwire. A spy test (`test_full_study_passes_the_search_bound_to_the_dispatch_tripwire` in `psse_study_test.py`) pins that the argument is passed, so the tripwire stays wired in.
- The case is hashed first and loaded later, in a separate step. If the file changed between the two, the stored hash would not describe the case that was studied. The gap is small and accepted.

## Phase 3 confirmations

On the licensed laptop, in this order:

1. Run `probe.run_probe` once with `show_identifiers` False, first without `write_check`, then with it on a copy of the case. The probe compares every `SURFACE` row with the real `psspy`, reads the case, checks that the bulk columns line up, tries the option strings, solves once and, if asked, writes a rating and reads it back. It undoes the write by reloading the case from disk and never saves.
2. Confirm the `branch_chng_3` signature and that the rating write reads back.
3. Confirm the percent-of-rating option strings exist in the installed version.
4. Check units on a branch with a known flow: the rating written and one percent-of-rating value.
5. Confirm which rate set Power Systems intends (question 2).
6. Confirm what the sink bus means for each city and what supplies it (question 4); an engineer reviews the margin numbers.
7. Measure the real N-1 run time. The extended walk can add about 80 load flows per city, so measure the whole study, not only the screen.
8. Choose the interpreter and the `psycopg` pin. PSS/E's bundled Python is not known here, and `psycopg` 3.3.6 needs Python 3.10 or later. The `psse_job` code has only been checked against Python 3.7 syntax and never run on that interpreter.
9. Anything that uses a licensed module (PV/QV, ACCC), if Power Systems wants it later.

## Assumptions

These come from the research log (A1 to A17, condensed) and A18. Each is configuration or is checked in Phase 3. None is Power Systems' decision.

| # | Assumption |
|---|---|
| A1 | `branch_chng_3` takes `ibus, jbus, ckt, intgar, realar, ratings, namear`, with 12 ratings and unlisted entries left at the default sentinel |
| A2 | The 33.5 option strings (percent of rating, `MAXMVA`, `P`, `TYPE`, `STATUS`, `ID`, `BASE`, `PU` and the bus limits) exist unchanged in 35 and 36 |
| A3 | The `solved()` codes are unchanged in 35 and 36 (any new non-zero code still fails) |
| A4 | `fnsl()` with no argument uses the program settings of the case |
| A5 | PSS/E 34.7 bundles Python 3.7, 35.x Python 3.9 and 36.1 Python 3.11; the 3.7 floor covers all |
| A6 | The real `psspy` functions expose the manual's parameter names to `inspect.signature`; if not, the probe reports SKIP and relies on the calls |
| A7 | Power Systems supplies a case with non-transformer city lines, one base kV per city and in-service mapped branches |
| A8 | The voltage bands 0.95 to 1.05 pu before and 0.90 to 1.05 pu after an outage, for buses at or above 100 kV, are the right defaults |
| A9 | RATEA is the right rate set for DLR, and N-1 limits use the same set |
| A10 | A constant power factor of 0.95 for `dispatched_mw` |
| A11 | Defaults: `thermal.limit_pct` 100, `transfer.step_mw` 25, `transfer.tolerance_mw` 1, `transfer.max_mw` 1000 as a starting cap, `transfer.extra_steps` 80, `contingency.max` 200, `contingency.hops` 2, `solve.max_mismatch_mva` 1.0, `max_runtime_seconds` 1500 |
| A12 | `psspy` holds process-global state, so the study runs once per process |
| A13 | `scal_2` with the combined form adds only to the subsystem's load at constant P and Q and leaves generation unchanged; the flat-transfer guard catches a no-op |
| A14 | Bulk columns from separate calls with identical selectors are aligned; the probe compares them with single-branch reads |
| A15 | The PV and QV engines need a licensed module and distribution-factor inputs |
| A16 | PSS/E's sample case is installed on the laptop, for a plumbing smoke run |
| A17 | A real N-1 over the neighbourhood (tens of outages) fits an hourly budget |
| A18 | A city's transfer is the summed absolute from-end P of its mapped branches |

## Representability notes (no DDL change)

The result tables are pinned and handed to Phase 6. Three things do not fit them exactly. Nothing was changed.

- There is no column for base-case violations. A violation that exists before any outage is written to the N-1 table with `in_base_case` in `details`.
- There is no "not computed" value for a city's margin or dispatch. One city's failed margin therefore fails the whole run. An additive Phase 6 migration could relax this if the project wants it.
- `psse_run.rate_set` is one text value. Several rate sets are joined with "+", for example `RATEA+RATEB`.

## Questions for the user / Power Systems

1. Mapping (Power Systems): for each city, which line or lines carry its rating in your case (from bus, to bus, circuit id), and are all of a city's lines at one base kV? Today the job runs on a placeholder with fake 9xxxx buses; a city with mixed base kV fails the run at stage mapping.
2. Rate set (Power Systems): should the DLR value go into RATEA only, or also RATEB (and RATEC), and should N-1 overloads be judged against RATEB rather than RATEA? Default: write RATEA and judge every check against RATEA (`study.rate_sets` in the mapping file changes it).
3. Static overwrite (user and Power Systems): when no trusted DLR row exists, should the project's static rating replace your case's own rating on the mapped lines, or should the case rating stay? Default: the static rating is written, as IN-01 requires; the case's previous value is kept in the dispatch row's details as rate_before_mva.
4. Voltage-margin transfer (Power Systems): for each city, which buses should take the extra load in the margin search, what should supply it, and how far may the search go? Defaults: the far end of the first mapped line takes the load and the swing bus supplies it (`sink_buses` per city in the mapping file); the search steps 25 MW at a time to a 1000 MW starting cap (`transfer.max_mw`, or `transfer_max_mw` per city) and, if no voltage, convergence or rating limit has been found by then, at most 80 more steps (`transfer.extra_steps`); if it still finds none, the run fails at stage voltage_margin rather than report the cap as a limit.
5. Base-case violations (Power Systems): should violations that already exist before any outage stay in the N-1 table, flagged in_base_case, or be left out? Default: kept and flagged.
6. Licensed modules (laptop owner): does the laptop's PSS/E have the PV/QV or ACCC modules licensed, and should the job use them instead of its own load-flow loops? Default: not used.
7. Case size and run time (Power Systems): about how many buses and branches does the case have, and is screening the lines within 2 branches of the mapped lines (at most 200 outages, 25 minutes per run) acceptable every hour? Defaults: contingency.hops 2, contingency.max 200, max_runtime_seconds 1500.
8. Limits (Power Systems): are the voltage bands 0.95 to 1.05 pu before and 0.90 to 1.05 pu after an outage (buses at or above 100 kV) and a current-based thermal check at 100 % of the rating right for your case? Defaults as stated, all in the mapping file's study section.
