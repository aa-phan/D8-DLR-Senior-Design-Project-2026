# pandapower hourly job: switch from dry run to live writes

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-11-25 (UTC), drafted |
| **Deciders** | the repository and Supabase owner (Aaron) with Tejaswini Kalikiri; the deciding person and date are recorded below when decided |

Scope: the repository variable `PANDAPOWER_LIVE` of the hourly workflow `.github/workflows/pandapower_hourly.yml`, and nothing else. The solver design, the agreement check and the retention of result rows are recorded elsewhere.

## Decision

Set the repository variable `PANDAPOWER_LIVE` to `true`, at repository level only, once every item of the gate below holds. Until then the hourly job stays a dry run: it reads the ratings, runs the study, prints counts and writes nothing to the database. Setting the variable is the owner's act; the owner steps are in `docs/data-science/decisions/pandapower_hourly_runbook.md` (section 8).

## Gate

Each item needs its evidence on record before the variable is set (D-02, D-11).

1. **NET-03 passed.** The base-case comparison of the converted network against the PSS/E answers held for 4 of 4 cities, reproduced, on 2026-11-20 (Phase 1). Evidence: `.planning/workstreams/pandapower-solver/phases/01-pss-e-reference-session-and-network-parity/01-VERIFICATION.md` and `01-SESSION-RECORD.md` in the same folder.
2. **AGR-02 passed.** The replay of recorded PSS/E runs on pandapower agreed on 19 of 19 runs, verdict pass, on 2026-11-21 (Phase 4). The recorded runs did not exercise the kinds `voltage_low` and `non_convergence`, so those two kinds rest on the Phase 1 base-case comparison and the public-fixture tests, not on a recorded replay. Evidence: `.planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/04-REPLAY-RECORD.md`.
3. **The solver-tag migration is applied to the live project and checked.** Applied by the owner and read back with the read-only check on 2026-11-25 (Phase 3). Evidence: `.planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-VERIFICATION.md`, section "Live check, 2026-11-25".
4. **The retention decision is written,** with the owner's review limit and the size of the four result tables before the first live write. Evidence: `.planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/05-RETENTION-DECISION.md`.
5. **The local hand-off evidence is recorded.** The owner commands run on the real private folder: `bundle` and the dry run on the real engine (plan 05-07, Task 1). Recorded under "Local evidence" below.
6. **The dry-run conditions hold.** At least 3 consecutive green scheduled dry runs; one real downloaded Actions log scanned with `scan-log` with 0 findings; and the local count comparison with identical lines (D-11; plan 05-07, Task 2). Recorded under "Dry-run evidence" below.
7. **The code-level backstop.** A live run refuses a placeholder backend before it reads the ratings, runs the study or opens a connection (D-03), so a mistaken flip cannot store figures from the placeholder mapping. This is in the code and its tests, not a step for the owner.

## Local evidence

Run on 2026-11-26 (UTC) at commit `36df6bf` on the branch `feature/pandapower-solver`, from the repository root, with pandapower 3.5.6 and the database-tier flags set. Nothing was skipped in any set.

| Set | Files | Result |
|---|---|---|
| Quick set | `pandapower_hourly_workflow_test.py`, `pandapower_soak_test.py`, `pandapower_hourly_test.py` | 103 passed, 0 skipped |
| Leak and owner set | `pandapower_hourly_leak_test.py`, `pandapower_hourly_owner_test.py`, `pandapower_hourly_runbook_test.py` | 25 passed, 0 skipped |
| Database tier and rehearsal | `pandapower_hourly_pg_test.py`, `pandapower_hourly_rehearsal_test.py` | 9 passed, 0 skipped |
| Regression set | `dlr_live_workflow_test.py`, `psse_gaps_solver_test.py`, `pandapower_import_gate_test.py`, `pandapower_replay_output_test.py`, `pandapower_study_job_test.py`, `pandapower_solver_tag_test.py`, `psse_writer_test.py` | 53 passed, 0 skipped |

Tree leak scan (`backend/private_leak_scan.py`): exit code 0, no finding lines; 36 files were not scanned because they are binary or over 2 MiB.

If the branch gains commits before the owner merges, these commands are run again at the merged commit before the first dispatch.

The owner `bundle` command ran on 2026-11-26 and produced the four files (network 33,588, mapping 1,880, settings 400 and scaling 144 characters). The dry run on the real engine is the local count comparison under "Dry-run evidence" below, which matched the runner.

## Dry-run evidence

Recorded 2026-11-27 (UTC), after the owner merged the branch into `main` and created the seven secrets of the `production` environment.

- **Scheduled dry runs:** 3 consecutive green runs, at 01:20, 02:20 and 03:20 UTC on 2026-11-27, each started by the cron-job.org job. Two manual dispatches from `main` before them were also green. A dispatch from the branch `feature/pandapower-solver` was skipped by the main-only `if`, as intended. Every run printed `mode: dry`.
- **Log scan:** one real downloaded Actions log (the 03:20 UTC run, 306 lines) scanned with `scan-log`: `scan-log: lines=306 findings=0`, exit 0. The downloaded copy was deleted afterwards.
- **Local count comparison:** matched. The owner's Windows machine, in the same hour as the 03:20 UTC run, printed lines identical to the Linux runner's: `mode: dry`, `inputs: ok`, `ratings: city_rating=4 static=0`, `study: ok`, `outcome: ok`, `rows: run=1 dispatch=4 margin=4 contingency=205`, `dry run: nothing was written to the database`. (The network secret is 33,588 characters, above Windows' limit of about 32,700 for one environment variable, so the local run held the four values in memory through a small launcher outside the repository, not in environment variables. The job's own code was unchanged.)
- **`DLR-PSSE-Hourly` laptop task:** state not recorded yet.

## Owner decision

Decided: go live, by Tejaswini Kalikiri, on 2026-11-27 (UTC).

The owner's review limit of 250 MB for the four result tables and the size read before the first live write are in `05-RETENTION-DECISION.md`. The variable `PANDAPOWER_LIVE` is set by the repository owner, at repository level only, to exactly `true`.

## How to undo

Set the variable to anything other than `true`, or delete it, and the next run is a dry run:

```bash
gh variable set PANDAPOWER_LIVE --body false
gh variable delete PANDAPOWER_LIVE
```

Either command is enough. Pausing the cron-job.org job stops runs altogether. Rows written while the job was live stay: the writer role has no DELETE, and nothing in this phase removes rows (D-01).

## Consequences

**Positive:** hourly pandapower results are stored without a licensed machine, tagged with their solver so they are told apart from the PSS/E rows. The switch is one variable that the owner can set or clear at any time, and the default is dry.

**Negative:** the stored rows are permanent. At 24 runs a day the job adds about 5,100 rows a day (retention decision, section "Context"). A switch back to dry stops the growth and does not shrink it. The agreement evidence for two kinds of finding is indirect (gate item 2). A borderline element could come out differently on the Linux runner than on the owner's machine; the local count comparison in gate item 6 is the check for that.

**Neutral:** the PSS/E laptop task, when enabled, writes `psse` rows that never fill a pandapower hour in the per-solver gap check.

## References

- Operating procedure: `docs/data-science/decisions/pandapower_hourly_runbook.md`
- Why the network stays private: `docs/data-science/decisions/pandapower_network_data_decision.md`
- Phase 5 decisions D-01 to D-14: `.planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/05-CONTEXT.md`
