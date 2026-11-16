# 03-08 Handover record (live session)

Statuses, counts, outcomes, exit codes and dates only. No path, host, user name, case or file name, connection string, key or numeric study result. Who acted is named by role: the owner (project owner), the teammate (the laptop's user).

**Deployment position.** The job is built to run on an always-on licensed Windows machine with PSS/E. The laptop session below was the trial of that deployment: one proof write, then the real hourly task enabled and observed for most of a day, then disabled as decision 2 said. On 2026-11-16 the laptop was cleaned and the writer password was changed, so no machine runs the job now. The job is paused until an always-on host is set up (see "Open questions"). The code, the guide and the runbook are the ones that host uses.

## Live credential proof

Runbook step 8, 2026-11-09, run by the teammate: `credcheck` 16 PASS 0 FAIL 0 SKIP, exit 0 (the writer role connects through the session pooler in the `ROLE.PROJECT-REF` form; the publishable key reads the ratings view and is refused on a write). `credcheck --write-proof` 18 PASS 0 FAIL 0 SKIP, exit 0 (one synthetic run inserted inside a transaction and rolled back; nothing kept). The owner's own grant checker passed 7 of 7. DBX-02 closes.

## Real case review

Runbook step 7: deferred in its planned form. Power Systems' own case and city-to-branch mapping did not arrive. Under the decision recorded in the roadmap (per-city scaled copies of the public IEEE 39-bus case replace waiting for Power Systems' branch mapping, Phase 4), the real runs used the public 39-bus example case with the private per-city mapping (schema version 2, the real city targets, kept off git). The four-city dry run on that case completed within the 1500 second budget (Phase 4 laptop record, 2026-11-11). A Power Systems engineer has not reviewed the numbers, and the hand-check of one rating and one percent-of-rating value has not been done: U21 stays open.

## The proof write

Runbook step 9, 2026-11-11, decision 1 answered by the owner as write-one: one real run written, exit 0, outcome `ok`, read back through the writer role: 1 run row, 4 dispatched capacity rows, 4 voltage margin rows, the contingency rows, 32 of 32 outages with results. Write delay (created_at minus finished_at) under one second. TST-02 closes, on the 39-bus case per the decision above.

## Hourly task and gap check

Runbook step 10, decision 2 answered by the owner on 2026-11-11 as enable-observe.

- Registered on 2026-11-11 for the teammate's account; first scheduled start 3:15 PM Central (21:00 UTC slot). A one-time task disabled it at 10:00 AM Central on 2026-11-12, as planned; its own result was 0.
- Starts were at :15:15. `LastTaskResult` was 0 at every reading (11-11 afternoon, and the final reading on 2026-11-15 after the last start at 9:15 AM on 11-12). No result 1, 3 or 4 was seen.
- Database read-back on 2026-11-16 (read-only, counts only): 19 runs in total (the proof write and 18 scheduled), every one outcome `ok`, no failed stage, no ratings read error, every run with results for all its outages. Every logged run read all four cities from `city_rating`; none fell back to the static rating. Run times 1 to 3 seconds; the largest write delay about 1 second. No two runs overlapped.
- Gap check over 2026-11-11 to 2026-11-12 (run from the owner's machine on 2026-11-15; the check only reads the database): 19 runs recorded, and these `no_run` hours, each explained:
  - 11-11 08:00 to 20:00 UTC (13 hours): before the task existed. Expected.
  - 11-12 12:00 and 14:00 UTC: the laptop was in Modern Standby (connected standby) from 5:50 to 7:30 AM and from 7:43 to 9:10 AM Central, from the System event log. `WakeToRun` did not wake it, so the 6:15, 7:15 and 8:15 starts did not happen on time. Windows ran a held start on each resume (7:31 and 9:10 AM). The gap check files a run under the hour it started, so the 7:31 run filled the 13:00 UTC slot and the 9:10 run shares the 15:00 UTC slot with the 9:15 start. Explained; a gap, not a failure, as the runbook says.
  - 11-12 16:00 UTC onward: after the one-time task disabled the hourly task. Expected; it also shows that hours with the task disabled appear as `no_run`.
- The deliberate two-hour induced gap was not run. The disabled hours after the stop, and the standby hours, show the same thing: an hour with no run is a visible `no_run` row. SCH-02 closes on that evidence.
- Clock: 1 second from a web Date header on 2026-11-15; the write delays above agree. The Windows Time service was not running and was not started.
- Stop and cleanup, 2026-11-16, by the teammate with the scripts `docs/data-science/ops/psse_laptop_status.ps1` (read-only) and `docs/data-science/ops/psse_laptop_cleanup.ps1` (preview, then `-Apply`): both scheduled tasks disabled and removed; the three secret values blanked in the configuration file and its two backups; one PowerShell history line holding a secret removed; no other file under the job's folder or the repository's untracked files matches a secret pattern (two compiled Python files match only the redaction module's own pattern text). The private mapping was copied off the laptop by the teammate. The owner's side changed the `dlr_psse_writer` password the same day, and the new login was checked read-only.
- SCH-01 is confirmed on the real task: hourly starts at :15 with no overlap for the whole observed window (about 18 hours, 11-11 3:15 PM to 11-12 9:15 AM Central).

## Write counts

Proof writes (task 4, after decision 1): 1
Scheduled runs written (task 6, after decision 2): 18
Decision 1: write-one.
Decision 2: enable-observe.

## Guide edits

- The guide's status, "Purpose and scope" and hand-over record now state what steps 7 to 10 showed: live ratings were read (outcome `ok`, not `fallback`), the result sets are runs on the public 39-bus case and not a full N-1 study, 19 permanent row sets exist (the two counts above), and the deployment target is an always-on licensed machine.
- The runbook's step 10 gains the standby finding and the two laptop scripts; the register rows U16, U19, U20, U27, U28, U29 and U32 record what the session showed or did not show.
- No command was found wrong in steps 8 to 10.

## Claims cleared

- U16 answered: `WakeToRun` did not wake this Modern Standby laptop (two standby periods on 2026-11-12, starts held until resume). The hour is a gap, as the register allows. An always-on host must not sleep.
- U19: the laptop clock agreed with the database (write delays about 1 second) and with a web clock (1 second), though the Windows Time service was not running.
- U23, U24, U25 (cleared in 03-07, step 8) hold on the live project.
- U27 in part: the repetition ran for about 18 hours with `NextRunTime` still set when it was disabled. A full day was not observed.

## Claims still UNVERIFIED

- U20 (`IgnoreNew`): no start came while an instance ran in step 10, and the Task Scheduler operational log was not enabled, so it holds no history. The run lock itself refused a second instance in step 6 on 2026-11-09 (result 4, the 03-07 session), so U13 is covered there.
- U21 (units and percent-of-rating values reviewed by an engineer) and U22 on Power Systems' own case: open.
- U27 for a full day and more, U28 (a hard kill at 45 minutes: no run came close, the longest took 3 seconds), U29 (no daylight-saving change in the window), U32 (no signed-out period observed): open.
- U07, U08, U12, U15 (from 03-07): not isolated; the account had administrator rights.

## Open questions

- Which always-on licensed Windows machine hosts the job from now on (the owner). It must stay on, awake, signed in and on the network: the PSS/E licence terms read so far tie it to one physical PC and rule out a virtual machine, so a cloud server or container is not a substitute. Setting it up is runbook steps 1 to 6 and 10 with the new writer password delivered privately and the private mapping copied back.
- Whether a Power Systems engineer reviews the 39-bus results and answers the eight questions of the study-definitions note (Power Systems).
- Whether the main pipeline's writer login, which once sat in the laptop configuration and was removed, should be changed as well (the owner).
- Production-pipeline Phase 6 has not adopted the `psse_*` tables in its own records (the owner).
- An open-source solver for continuous runs without a licensed machine is planned as a separate workstream; it does not change this record.
