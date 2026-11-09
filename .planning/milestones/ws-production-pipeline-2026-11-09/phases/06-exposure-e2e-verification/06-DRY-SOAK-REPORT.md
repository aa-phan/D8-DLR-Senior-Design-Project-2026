# Dry soak report (E2E-02, D-07)

## Context

- **What this is (D-07):** the dry soak is computed from the live city_rating rows already written since 2026-10-25T00:00Z (the Phase 5 window start), exported read-only on 2026-10-27T02:56:53Z with `--since 2026-10-25T00:00:00Z --until 2026-10-27T02:00:00Z` (a 50 hour span; 204 live rows and 53 pipeline runs exported). The report was run with `--min-hours 12`.
- **How lag is measured:** write lag is measured from `first_written_at` (when the rating first landed). The `computed_at` last-write lag is shown in the first table for information only.
- **OD-4 is fixed:** a breach is a current rating strictly older than 90 minutes. The limit is not relaxed anywhere in this report.
- **Soak log schedule (owner, Task 2):** the job `dlr-soak-freshness` runs `select ops.log_freshness()` every 5 minutes. First run 2026-10-27T02:55:00Z succeeded (T0 about 02:50 to 02:55Z).
- **Smoke check (re-run after the log had three probes; all ok):**

| check | result | detail |
|---|---|---|
| last_three_probes_wrote_four_rows | ok | 3 of 3 probes found; 4, 4, 4 rows per probe |
| last_three_runs_succeeded | ok | 3 of 3 runs found; all succeeded (1 row each) |
| no_breach_in_the_last_three_probes | ok | 0, 0, 0 breach rows per probe |
| soak_job_active_every_5_minutes | ok | 1 job named dlr-soak-freshness; active; schedule every 5 minutes; command select ops.log_freshness() |

  The first smoke run, made before three probes existed, returned false for the probe and run checks (0 of 3) and true for the job check. It was re-run once three probes had been written and passed. That was an expected early result, not a fault.
- **Permanent alarm (D-08, D-14, D-15):** "DLR freshness alarm", every 15 minutes, `GET` on the freshness assertion function with the publishable key only. First two executions: 200, 200.
- **Failure drill (max_age_minutes = 0, every minute):** runs returned 503; the failure email arrived at 10:24 PM CDT (2026-10-27T03:24Z). Failure alerting is proven.
- **Deviation: recovery email never arrived.** The same failing drill job was flipped to a 90 minute limit and its runs returned 200, but the "success after failure" email did not arrive (owner checked). Earlier, a separate always-succeeding job produced no recovery email either, which is expected because a job that never failed cannot recover. Recovery notification is therefore unproven. This is non-blocking for the soak: the alarm's purpose (warn when the rating goes stale) is proven by the failure email. Recommendation: the owner checks the permanent alarm's "notify on success after failure" setting. The owner deletes the drill jobs.

## Dry soak result

Window: 2026-10-25T00:00:00Z to 2026-10-27T02:00:00Z (50 hourly slots). A breach is a current rating strictly older than 90 min.

**PASS: all 50 hourly slots landed; the current rating was never older than 73.3 min (limit 90 min); a rating usually landed 7.0 min after its hour and at worst 13.3 min after.**

## Write lag (first_written_at minus valid_time, minutes)

| city | writes | median | p95 | max | last-write lag max (informational) |
|---|---|---|---|---|---|
| AUSTIN | 50 | 5.9 | 6.3 | 9.9 | 23.6 |
| CORPUS_CHRISTI | 50 | 6.1 | 8.0 | 11.1 | 23.7 |
| MIDLAND | 50 | 7.4 | 10.1 | 12.2 | 12.2 |
| EL_PASO | 50 | 8.2 | 12.2 | 13.3 | 23.8 |
| overall | 200 | 7.0 | 9.7 | 13.3 | |

## Peak age (age of the previous rating just before the next one landed, minutes)

| city | peak max | above 75 | above 90 | age at end of window |
|---|---|---|---|---|
| AUSTIN | 69.9 | 0 | 0 | 60.0 |
| CORPUS_CHRISTI | 71.0 | 0 | 0 | 60.0 |
| MIDLAND | 72.2 | 0 | 0 | 60.0 |
| EL_PASO | 73.3 | 0 | 0 | 60.0 |
| overall | 73.3 | 0 | 0 | |

## Fallback share (informational: a fallback row is a fresh row, not a breach)

| city | rows | fallback | share |
|---|---|---|---|
| AUSTIN | 50 | 25 | 50.0 % |
| CORPUS_CHRISTI | 50 | 0 | 0.0 % |
| MIDLAND | 50 | 4 | 8.0 % |
| EL_PASO | 50 | 0 | 0.0 % |

## Late fills (an older slot first written inside the window; informational, never a breach)

No late fills.

## Slot verdicts (dlr_live_window_check.evaluate_window)

| slot (UTC) | verdict | runs | note |
|---|---|---|---|
| 2026-10-25T00:00:00Z | ok | 40145300072 (success) | fault-drill run 40146481713 not counted |
| 2026-10-25T01:00:00Z | ok | 40149224957 (success) |  |
| 2026-10-25T02:00:00Z | ok | 40153094724 (success) |  |
| 2026-10-25T03:00:00Z | ok | 40156888768 (success) |  |
| 2026-10-25T04:00:00Z | ok | 40160579131 (success) |  |
| 2026-10-25T05:00:00Z | ok | 40164234698 (success) |  |
| 2026-10-25T06:00:00Z | ok | 40167843477 (success) |  |
| 2026-10-25T07:00:00Z | ok | 40171448029 (success) |  |
| 2026-10-25T08:00:00Z | ok | 40175233252 (success) |  |
| 2026-10-25T09:00:00Z | ok | 40179188388 (success) |  |
| 2026-10-25T10:00:00Z | ok | 40183301436 (success) |  |
| 2026-10-25T11:00:00Z | ok | 40187388549 (success) |  |
| 2026-10-25T12:00:00Z | ok | 40191572824 (success) |  |
| 2026-10-25T13:00:00Z | ok | 40195996660 (success) |  |
| 2026-10-25T14:00:00Z | ok | 40200573392 (success) |  |
| 2026-10-25T15:00:00Z | ok | 40205253236 (success) |  |
| 2026-10-25T16:00:00Z | ok | 40209980259 (success) |  |
| 2026-10-25T17:00:00Z | ok | 40214743173 (success) |  |
| 2026-10-25T18:00:00Z | ok | 40219548556 (success) |  |
| 2026-10-25T19:00:00Z | ok | 40224320021 (success) |  |
| 2026-10-25T20:00:00Z | ok | 40229082246 (success) |  |
| 2026-10-25T21:00:00Z | ok | 40233793751 (success) |  |
| 2026-10-25T22:00:00Z | ok | 40238508680 (success) |  |
| 2026-10-25T23:00:00Z | ok | 40243136280 (success) |  |
| 2026-10-26T00:00:00Z | ok | 40247620028 (success) |  |
| 2026-10-26T01:00:00Z | ok | 40252444721 (success) |  |
| 2026-10-26T02:00:00Z | ok | 40257333205 (success) |  |
| 2026-10-26T03:00:00Z | ok | 40262284804 (success) |  |
| 2026-10-26T04:00:00Z | ok | 40267222167 (success) |  |
| 2026-10-26T05:00:00Z | ok | 40272358123 (success) |  |
| 2026-10-26T06:00:00Z | ok | 40277772217 (success) |  |
| 2026-10-26T07:00:00Z | ok | 40283615218 (success) |  |
| 2026-10-26T08:00:00Z | ok | 40289840153 (success) |  |
| 2026-10-26T09:00:00Z | ok | 40296851773 (success) |  |
| 2026-10-26T10:00:00Z | ok | 40304597500 (success) |  |
| 2026-10-26T11:00:00Z | ok | 40312368888 (success) |  |
| 2026-10-26T12:00:00Z | ok | 40319824680 (success) |  |
| 2026-10-26T13:00:00Z | ok | 40327566499 (success) |  |
| 2026-10-26T14:00:00Z | ok | 40336327699 (success) |  |
| 2026-10-26T15:00:00Z | ok | 40345805579 (success) |  |
| 2026-10-26T16:00:00Z | ok | 40355654183 (success) |  |
| 2026-10-26T17:00:00Z | ok | 40365273798 (success) |  |
| 2026-10-26T18:00:00Z | ok | 40374569705 (success) |  |
| 2026-10-26T19:00:00Z | ok | 40383503248 (success) |  |
| 2026-10-26T20:00:00Z | ok | 40392474708 (success) |  |
| 2026-10-26T21:00:00Z | ok | 40401311500 (success) |  |
| 2026-10-26T22:00:00Z | ok | 40409647804 (success) |  |
| 2026-10-26T23:00:00Z | ok | 40417234808 (success) |  |
| 2026-10-27T00:00:00Z | ok | 40424070338 (success) |  |
| 2026-10-27T01:00:00Z | ok | 40430433025 (success) |  |

verdicts: ok 50
billed minutes: 51 runs, median 4, max 9; projected 2880 min per 30 days at 24 runs/day
window: PASSED

## Ten largest peak ages

| city | valid_time | first written | peak age | write lag |
|---|---|---|---|---|
| EL_PASO | 2026-10-26T12:00:00Z | 2026-10-26T12:13:19Z | 73.3 | 13.3 |
| EL_PASO | 2026-10-25T00:00:00Z | 2026-10-25T00:12:13Z | 72.2 | 12.2 |
| EL_PASO | 2026-10-25T16:00:00Z | 2026-10-25T16:12:14Z | 72.2 | 12.2 |
| MIDLAND | 2026-10-26T12:00:00Z | 2026-10-26T12:12:11Z | 72.2 | 12.2 |
| CORPUS_CHRISTI | 2026-10-26T12:00:00Z | 2026-10-26T12:11:03Z | 71.0 | 11.1 |
| EL_PASO | 2026-10-25T22:00:00Z | 2026-10-25T22:10:22Z | 70.4 | 10.4 |
| MIDLAND | 2026-10-25T22:00:00Z | 2026-10-25T22:10:12Z | 70.2 | 10.2 |
| MIDLAND | 2026-10-25T00:00:00Z | 2026-10-25T00:10:08Z | 70.1 | 10.1 |
| MIDLAND | 2026-10-25T16:00:00Z | 2026-10-25T16:10:07Z | 70.1 | 10.1 |
| AUSTIN | 2026-10-26T12:00:00Z | 2026-10-26T12:09:54Z | 69.9 | 9.9 |
