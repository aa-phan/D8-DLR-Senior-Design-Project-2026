# 04-06 Laptop record (Phase 4 session)

Versions, positions, outcomes and counts only. No path, host, user name, case or file name, bus number, connection string, key or city figure.

## Laptop facts

| Item | Value |
|------|-------|
| PSS/E | 36.4.0, free Xplore edition ("50 BUS POWER SYSTEM SIMULATOR", Python 3.14 bindings) |
| Python | 3.14, 64-bit |
| Dates | documentation read 2026-11-10; probe runs and the four-city dry run 2026-11-11 |
| Code under test | branch feature/pss-e-integration; first probe run before the fix, second and the dry run at commit 5a30c63 |
| Case | the public 39-bus example, unconverted, a private copy; the placeholder mapping at schema version 2 with placeholder targets (round fractions of the case's own totals) |

## Scaling layout

Read from the installed API documentation of `scal_2` (the function's own help text) on 2026-11-10. Positions and meanings only.

| Position | Meaning on PSS/E 36.4 | SCALE_LAYOUT value | Same, different or not stated |
|----------|----------------------|--------------------|-------------------------------|
| STATUS 1 | interruptible-load option; 0 scales both kinds | left at the no-input default | same |
| STATUS 2 | method for active power; 1 = new total powers | 1 | same |
| STATUS 3 | enforce machine power limits; 0 = ignore | 0 | same |
| STATUS 4 | reactive-power rule; 1 = constant P/Q ratio | 1 | same |
| STATUS 5 | bus-type flag; 0 = all buses | 0 | same |
| SCALVAL 1 | load MW total (or percent or increment) | the load target | same |
| SCALVAL 2 | generation MW total (or percent or increment) | the generation target | same |
| SCALVAL 3 to 7 | other quantities and the reactive parameter | left at the no-input default | same |
| TOTALS 2 | load MW total (1-based) | index 1 (0-based) | same |
| TOTALS 3 | generation MW total (1-based) | index 2 (0-based) | same |
| APIOPT 0 | initialise for scaling, then run it | scale | same |
| APIOPT 1 | initialise only; returns the totals | read the totals | same |
| APIOPT 2 | run the scaling and finish | close a read (added 2026-11-11) | different: the layout lacked the close, see the finding |

SCAL_4: yes, it exists. `scal_2` is marked obsolete in 36.4 and is implemented by a call to `scal_4`; the job still calls `scal_2`.

Load-type answer (CD-9): STATUS 1 = 0 scales both interruptible and non-interruptible loads; STATUS 4 = 1 keeps a constant P/Q ratio, so each load keeps its power factor. This is the documentation's statement; no load's P and Q was read before and after a scaling.

## Decision

The positions match on every field. One thing the documentation does not state turned up in the probe, below, and was fixed on the Mac (commit 5a30c63).

## Step results

Step 3 (read-only probe): not re-run this session; it passed on 2026-11-09.

Step 4 (probe with the write check, placeholder mapping allowed):
- First run, before the fix: 30 PASS, 1 FAIL, 0 SKIP, exit 6. The failing row was `scale_to_target`: `PsseCallError (psspy.scal_2, ierr 5)`. Every other row passed, including `mapping` (0 problems, all four cities at the same voltage), `rating_write`, `scale_load` and `signature:scal_2` (5 parameters present, 1 extra).
- Second run, after the fix: 0 FAIL, exit 0, `scale_to_target` PASS. The full row text was not pasted.

Step 5 (four-city dry run, placeholder mapping allowed): exit 0. `psse_run=1`, `psse_dispatched_capacity=4`, `psse_voltage_margin=4`, `psse_contingency_result=85`; `contingencies: screened=32 with_results=28`; `ratings: city_rating=4 static=0`; `outcome: ok`; `rate_set: RATEA`; `psse_version: 36.4.0`; `study_seconds: 2.0`; `validation: ok`. Nothing was written to the database.

## Finding from step 4 (2026-11-11)

A totals read (`APIOPT` 1) only opens scaling. It stays open, even across a case load, until an `APIOPT` 2 call closes it. A second `APIOPT` 1 while one is open fails with ierr 5. Reloading the case does not clear it; a failed `APIOPT` 1 leaves nothing open; `APIOPT` 2 with nothing open also returns ierr 5; `APIOPT` 0 returned 0 in every sequence tried.

Three diagnostic scripts, kept outside the repository, tried single calls and then sequences on a fresh copy of the example case, in memory only and never saved. Every call of the sequences that closed each read returned 0 (read and close, scale, read and close). The probe's own order (read, scale, read, reload, read) leaves a read open at the last step, which is why `scale_to_target` failed, and the study's per-city loop would have failed the same way. PSS/E does not document ierr 5 for this call; the rule is inferred from those experiments.

Fix: `read_totals` closes every read at once with an `APIOPT` 2 call that scales nothing. The fake psspy now models the open-read state, so a missing close fails on the Mac (18 tests fail with the close removed). The second probe run and the dry run above passed on the fixed code.

## Claims cleared

- U35 the whole-case scaling layout works on PSS/E 36.4: the positions match the documentation and `scale_to_target` PASS after the close was added (step 4).
- U36 reloading the case undoes a whole-case scaling: the `scale_to_target` row restores the totals by reloading and passed (step 4).
- U38 a four-city dry run on the example case completes within the 1500 s budget: 2.0 s, exit 0, four dispatch rows, `validation: ok` (step 5). This is the 39-bus example's time only.
- U37 the scaling mode keeps each load's power factor: cleared on the documentation only (STATUS 4 = 1 is a constant P/Q ratio). Not measured, see below.

## Claims still UNVERIFIED

- U37 as a measurement: no load's P and Q was read before and after a scaling, so the power-factor behaviour rests on the documentation's wording.
- The meaning of ierr 5 as a rule: inferred from three experiments and one probe pass; PSS/E does not list the code for this call.
- Timing and behaviour on the real case Power Systems supplies. The placeholder targets are fractions of the example case's own totals, not any city's figures, and the real case may be larger than the 39-bus example.
- That `scal_2` stays available: it is marked obsolete and implemented by `scal_4`.

## Open questions

- Whether the same mapped lines can serve every city's copy (Power Systems to confirm; the code allows it).
- El Paso's basis: average load from the sales table, to be confirmed with Power Systems.
- Whether keeping each load's base power factor (no separate reactive target) is what Power Systems intends.
- Why 4 of the 32 screened outages produced no result rows in the dry run (`with_results=28`): not investigated; it may be expected on the 39-bus example.
