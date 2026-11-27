# Retention of the pandapower result rows: keep every row

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-11-25 (UTC) |
| **Deciders** | Tejaswini Kalikiri (approved D-01 on the corrected figure, 2026-11-25); the repository and Supabase owner (Aaron) may change it and names the review limit |

Scope: the four result tables `public.psse_run`, `public.psse_dispatched_capacity`, `public.psse_voltage_margin` and `public.psse_contingency_result`, and the rows the pandapower hourly job of phase 5 writes into them. The 19 existing PSS/E runs are unchanged by this record.

## Decision

Keep every row. Nothing is pruned, archived or deleted in this phase (D-01).

**Review trigger.** The owner runs `supabase/ops/psse_result_size.sql` in the Supabase SQL editor. It is one read-only query that returns counts and sizes for the four result tables, their sum and the whole database. The decision is revisited when the `all four result tables` total nears the limit the owner names. A reading equal to the limit counts as reached, so the review is meant to happen while the reading is still below it.

Two lines are filled by plan 05-08 Task 1, from the owner's answer at plan 05-07 Task 3, before the first live write:

- Review limit named by the owner: **250 MB** for all four result tables together (owner's answer, 2026-11-27). At the rate of about 5,100 rows a day (about 430 bytes a row on the first reading, so about 2.2 MB a day) that is roughly 3.5 months of live running.
- Size before the first live write, read by the owner with `supabase/ops/psse_result_size.sql` on 2026-11-27 at 05:17 UTC: `psse_run` 19 rows, 112 kB; `psse_dispatched_capacity` 76 rows, 96 kB; `psse_voltage_margin` 76 rows, 104 kB; `psse_contingency_result` 3,895 rows, 1,432 kB; **all four result tables 4,066 rows, 1,744 kB (1,785,856 bytes)**; whole database 22 MB. All of these rows are PSS/E runs; no pandapower row has been written.

## Context

**The true rate.** The 19 recorded runs hold 76 dispatch rows, 76 margin rows and 3,895 contingency rows, which is about 205 contingency rows per run (3,895 divided by 19). One run is therefore 1 run row, 4 dispatch rows, 4 margin rows and about 205 contingency rows, about 214 rows. At 24 runs a day that is about 5,100 rows a day (24 times 214 is 5,136), about 36,000 a week and about 154,000 in 30 days.

**What drives it.** Only violations are written to the contingency table, so the number follows how stressed the grid is. The per-run cap of 5,000 contingency rows (`MAX_CONTINGENCY_ROWS`) bounds the worst case at about 5,009 rows a run, about 120,000 rows a day.

**What changed from the first draft.** The first draft of D-01 said "a few hundred rows a day". That counted only run, dispatch and margin rows (9 per run, 216 a day) and left out the contingency rows, which are about 96 percent of every run. At the corrected rate the earlier trigger of 100,000 rows would be reached in about 20 days, so it is replaced by the size check above.

**Who can delete.** The writer role `dlr_psse_writer` has INSERT and SELECT and no DELETE, so any pruning would need the owner's admin login. That is a second reason to keep every row for now.

## Consequences

**Positive:** nothing is lost, and the decision is cheap to change. The soak and the gap check read every row that was written.

**Negative:** the tables grow by about 5,100 rows a day, and someone must read the size. Until the owner names a limit and reads the size before the first live write, the review has no number to be compared with.

**How to change it:** add a new dated entry that supersedes this one. Pruning or archiving stays a deferred idea until then.

## References

- `.planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/05-CONTEXT.md`, decision D-01
- `.planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/05-RESEARCH.md`, Pitfall 4
- `.planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-REPLAY-RECORD.md` (the row counts of the 19 recorded runs)
- `backend/psse_job/run_record.py` (`MAX_CONTINGENCY_ROWS`)
- `docs/data-science/schema/psse_results_v1.md` (only violations are written)
- `supabase/ops/psse_result_size.sql` (the owner's size query)
