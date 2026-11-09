# Soak report (E2E-02)

## Context

- **Window (D-09):** G = 2026-10-27T03:35:00Z (the owner's "go" reply at 2026-10-27T03:34:58Z rounded up to the next 5-minute boundary, recorded in 06-10-SUMMARY.md) to 2026-10-30T03:35:00Z, exactly 72 h. It starts after the dry soak's export end (2026-10-27T02:00:00Z), so the two never overlap. The export was run by the owner at 2026-10-30T06:09:19Z with `--mode soak --since 2026-10-27T03:35:00Z --until 2026-10-30T03:35:00Z` and holds 384 live rows, 74 pipeline runs, 77 GitHub run records and 3456 probe rows. `export_meta.json` records `git_head` 3fa8baa.
- **D-09 timeline status:** D-09 wanted the clock started by 2026-10-27T00:00Z so the window would end before Supabase's default-permission change on 2026-10-30. That start was missed (06-10 records why), and the window was neither lengthened nor shortened to fix it: its last 3 h 35 min ran on the far side of 2026-10-30T00:00Z. The change only affects the default permissions of new tables; ours are written out explicitly, and the end-of-soak checks below (taken at about 06:10Z on 2026-10-30, after the change date) still pass. The separate permission re-check (plan 06-13) runs on or after 2026-10-31.
- **OD-1 and OD-4 are unchanged:** hourly cadence, and a breach is a current rating strictly older than 90 minutes (exactly 90 is fresh). The probe-gap limit is 11 minutes for a 5-minute probe. Nothing was relaxed.
- **Not paused or restarted:** the soak ran continuously. No pause, no restart and no manual re-run of a past slot is recorded in the data or by the owner.
- **Alarm emails (reported by the owner):** none. The owner reported no freshness-alarm email, failure or recovery, between 2026-10-27T03:35Z and 2026-10-30T03:35Z.
- **Owner events:** none reported. No annotation was written by the executor; `annotations.json` does not exist because there is nothing to annotate (T-06-41).
- **Independent check of the probe log:** from `probes.csv` directly, 864 distinct probe times (first 2026-10-27T03:35:00Z, last 2026-10-30T03:30:00Z), 864 rows per city, 0 rows flagged as breach, 0 rows without an age, and the largest spacing between consecutive probes 5.005 min. The oldest rating any probe saw was 70.0 min (EL_PASO and MIDLAND) and 65.0 min (AUSTIN and CORPUS_CHRISTI). The report's write-based peak (72.3 min) is higher because it also catches the instant just before a new rating lands, between probes. Both are below 90.
- **Deploys:** the report finds three pipeline-version changes from the rows (82c0332 to acbfe3a at the 2026-10-28T22:00Z slot, acbfe3a to aad82c2 at 2026-10-29T19:00Z, aad82c2 to e970549 at 2026-10-29T21:00Z). After a read-only `git fetch origin` all three commits were classifiable, and all three are **no runtime change** (only files under `.planning/workstreams/input-provenance/` changed). No model, config, workflow or code deploy happened in the window, and no breach existed for a deploy to explain.

## Lag statistics compared with the dry soak (06-DRY-SOAK-REPORT.md)

Write lag is `first_written_at` minus `valid_time`, in minutes. Peak age is the age of the previous rating just before the next one landed.

| measure | dry soak (50 slots, 200 writes) | 72 h soak (72 slots, 288 writes) |
|---|---|---|
| write lag median | 7.0 | 7.1 |
| write lag p95 | 9.7 | 9.4 |
| write lag max | 13.3 | 12.3 |
| peak age max (overall) | 73.3 | 72.3 |
| peak age above 75 / above 90 | 0 / 0 | 0 / 0 |
| age at end of window | 60.0 per city | 35.0 per city |

| city | dry soak lag median / p95 / max | 72 h soak lag median / p95 / max | dry soak peak max | 72 h soak peak max |
|---|---|---|---|---|
| AUSTIN | 5.9 / 6.3 / 9.9 | 5.9 / 6.1 / 7.5 | 69.9 | 67.5 |
| CORPUS_CHRISTI | 6.1 / 8.0 / 11.1 | 6.1 / 7.2 / 8.7 | 71.0 | 68.7 |
| MIDLAND | 7.4 / 10.1 / 12.2 | 7.9 / 8.5 / 10.2 | 72.2 | 70.2 |
| EL_PASO | 8.2 / 12.2 / 13.3 | 8.3 / 9.5 / 12.3 | 73.3 | 72.3 |

In plain English: the 72 h soak behaved like the dry soak, with a rating landing about 7 minutes after its hour and at worst about 12 minutes. The slowest city is still EL_PASO. The fallback share (informational, a fallback row is a fresh row and never a breach) moved for AUSTIN from 50.0 % in the dry soak to 65.3 % here (47 of 72 rows); CORPUS_CHRISTI rose from 0.0 % to 1.4 %, MIDLAND from 8.0 % to 6.9 %, EL_PASO stayed at 0.0 %.

Window: 2026-10-27T03:35:00Z to 2026-10-30T03:35:00Z (72 h; at least 72 h required). A breach is a current rating strictly older than 90 min (OD-4: exactly 90 min is fresh), or a gap in the probe log longer than 11 min.

**PASS: over 72 h each city's current rating was never more than 90 min old unless explained (no breach at all); 864 of 864 expected probes were logged with no gap longer than 11 min.**

## Breaches

No breaches.

## Deploys and events during the window

Deploys are derived from the rows (a change of pipeline_version, config_fingerprint, model hashes, forecast_method or config_version from a city's previous row). A deploy is context for a breach; it never excuses one (D-08). Events are the owner's own entries.

No deploys and no owner events in the window.

Commits with no runtime change (listed, not deploys):

- 82c0332 to acbfe3a first written 2026-10-28T22:05:55Z
- acbfe3a to aad82c2 first written 2026-10-29T19:05:54Z
- aad82c2 to e970549 first written 2026-10-29T21:05:54Z

## Probe coverage

864 of 864 expected probes (one every 5 min) were logged; a gap longer than 11 min fails the soak unless annotated.

Gaps:

No probe gaps.

Incomplete probes (a city missing from the probe; listed, not a failure):

No incomplete probes.

Age of the newest rating at the end of the window (minutes):

| city | age |
|---|---|
| AUSTIN | 35.0 |
| CORPUS_CHRISTI | 35.0 |
| MIDLAND | 35.0 |
| EL_PASO | 35.0 |

## Write lag (first_written_at minus valid_time, minutes)

| city | writes | median | p95 | max | last-write lag max (informational) |
|---|---|---|---|---|---|
| AUSTIN | 72 | 5.9 | 6.1 | 7.5 | 7.5 |
| CORPUS_CHRISTI | 72 | 6.1 | 7.2 | 8.7 | 8.7 |
| MIDLAND | 72 | 7.9 | 8.5 | 10.2 | 10.2 |
| EL_PASO | 72 | 8.3 | 9.5 | 12.3 | 12.3 |
| overall | 288 | 7.1 | 9.4 | 12.3 | |

## Peak age (age of the previous rating just before the next one landed, minutes)

| city | peak max | above 75 | above 90 | age at end of window |
|---|---|---|---|---|
| AUSTIN | 67.5 | 0 | 0 | 35.0 |
| CORPUS_CHRISTI | 68.7 | 0 | 0 | 35.0 |
| MIDLAND | 70.2 | 0 | 0 | 35.0 |
| EL_PASO | 72.3 | 0 | 0 | 35.0 |
| overall | 72.3 | 0 | 0 | |

## Fallback share (informational: a fallback row is a fresh row, not a breach)

| city | rows | fallback | share |
|---|---|---|---|
| AUSTIN | 72 | 47 | 65.3 % |
| CORPUS_CHRISTI | 72 | 1 | 1.4 % |
| MIDLAND | 72 | 5 | 6.9 % |
| EL_PASO | 72 | 0 | 0.0 % |

## Late fills (an older slot first written inside the window; informational, never a breach)

No late fills.

## Slot verdicts (dlr_live_window_check.evaluate_window)

| slot (UTC) | verdict | runs | note |
|---|---|---|---|
| 2026-10-27T03:00:00Z | ok | 40442160217 (success) |  |
| 2026-10-27T04:00:00Z | ok | 40447756754 (success) |  |
| 2026-10-27T05:00:00Z | ok | 40453291297 (success) |  |
| 2026-10-27T06:00:00Z | ok | 40458990024 (success) |  |
| 2026-10-27T07:00:00Z | ok | 40464966849 (success) |  |
| 2026-10-27T08:00:00Z | ok | 40471095170 (success) |  |
| 2026-10-27T09:00:00Z | ok | 40478107847 (success) |  |
| 2026-10-27T10:00:00Z | ok | 40485728321 (success) |  |
| 2026-10-27T11:00:00Z | ok | 40493449636 (success) |  |
| 2026-10-27T12:00:00Z | ok | 40500999011 (success) |  |
| 2026-10-27T13:00:00Z | ok | 40508957021 (success) |  |
| 2026-10-27T14:00:00Z | ok | 40517753455 (success) |  |
| 2026-10-27T15:00:00Z | ok | 40527446355 (success) |  |
| 2026-10-27T16:00:00Z | ok | 40537392670 (success) |  |
| 2026-10-27T17:00:00Z | ok | 40547195829 (success) |  |
| 2026-10-27T18:00:00Z | ok | 40556619831 (success) |  |
| 2026-10-27T19:00:00Z | ok | 40565869309 (success) |  |
| 2026-10-27T20:00:00Z | ok | 40574850244 (success) |  |
| 2026-10-27T21:00:00Z | ok | 40583722489 (success) |  |
| 2026-10-27T22:00:00Z | ok | 40592005716 (success) |  |
| 2026-10-27T23:00:00Z | ok | 40599594458 (success) |  |
| 2026-10-28T00:00:00Z | ok | 40606443085 (success) |  |
| 2026-10-28T01:00:00Z | ok | 40612857406 (success) |  |
| 2026-10-28T02:00:00Z | ok | 40618828391 (success) |  |
| 2026-10-28T03:00:00Z | ok | 40624639741 (success) |  |
| 2026-10-28T04:00:00Z | ok | 40630294376 (success) |  |
| 2026-10-28T05:00:00Z | ok | 40635911999 (success) |  |
| 2026-10-28T06:00:00Z | ok | 40641712785 (success) |  |
| 2026-10-28T07:00:00Z | ok | 40647803508 (success) |  |
| 2026-10-28T08:00:00Z | ok | 40654283467 (success) |  |
| 2026-10-28T09:00:00Z | ok | 40661492162 (success) |  |
| 2026-10-28T10:00:00Z | ok | 40669281353 (success) |  |
| 2026-10-28T11:00:00Z | ok | 40677175510 (success) |  |
| 2026-10-28T12:00:00Z | ok | 40684945125 (success) |  |
| 2026-10-28T13:00:00Z | ok | 40693236075 (success) |  |
| 2026-10-28T14:00:00Z | ok | 40702466512 (success) |  |
| 2026-10-28T15:00:00Z | ok | 40712350187 (success) |  |
| 2026-10-28T16:00:00Z | ok | 40722441280 (success) |  |
| 2026-10-28T17:00:00Z | ok | 40732274004 (success) |  |
| 2026-10-28T18:00:00Z | ok | 40741784886 (success) |  |
| 2026-10-28T19:00:00Z | ok | 40751065594 (success) |  |
| 2026-10-28T20:00:00Z | ok | 40760071875 (success) |  |
| 2026-10-28T21:00:00Z | ok | 40768929726 (success) |  |
| 2026-10-28T22:00:00Z | ok | 40777173554 (success) |  |
| 2026-10-28T23:00:00Z | ok | 40784780656 (success) |  |
| 2026-10-29T00:00:00Z | ok | 40791686524 (success) |  |
| 2026-10-29T01:00:00Z | ok | 40798208608 (success) |  |
| 2026-10-29T02:00:00Z | ok | 40804242867 (success) |  |
| 2026-10-29T03:00:00Z | ok | 40810102786 (success) |  |
| 2026-10-29T04:00:00Z | ok | 40815725336 (success) |  |
| 2026-10-29T05:00:00Z | ok | 40821328816 (success) |  |
| 2026-10-29T06:00:00Z | ok | 40827086747 (success) |  |
| 2026-10-29T07:00:00Z | ok | 40833156546 (success) |  |
| 2026-10-29T08:00:00Z | ok | 40839622787 (success) |  |
| 2026-10-29T09:00:00Z | ok | 40846856657 (success) |  |
| 2026-10-29T10:00:00Z | ok | 40854699312 (success) |  |
| 2026-10-29T11:00:00Z | ok | 40862612290 (success) |  |
| 2026-10-29T12:00:00Z | ok | 40870384715 (success) |  |
| 2026-10-29T13:00:00Z | ok | 40878716877 (success) |  |
| 2026-10-29T14:00:00Z | ok | 40887977717 (success) |  |
| 2026-10-29T15:00:00Z | ok | 40897941579 (success) |  |
| 2026-10-29T16:00:00Z | ok | 40908035241 (success) |  |
| 2026-10-29T17:00:00Z | ok | 40917882827 (success) |  |
| 2026-10-29T18:00:00Z | ok | 40927432583 (success) |  |
| 2026-10-29T19:00:00Z | ok | 40936821547 (success) |  |
| 2026-10-29T20:00:00Z | ok | 40945836669 (success) |  |
| 2026-10-29T21:00:00Z | ok | 40954690880 (success) |  |
| 2026-10-29T22:00:00Z | ok | 40963064502 (success) |  |
| 2026-10-29T23:00:00Z | ok | 40970621607 (success) |  |
| 2026-10-30T00:00:00Z | ok | 40977388973 (success) |  |
| 2026-10-30T01:00:00Z | ok | 40983680776 (success) |  |
| 2026-10-30T02:00:00Z | ok | 40989598730 (success) |  |

verdicts: ok 72
billed minutes: 72 runs, median 4.0, max 8; projected 2880 min per 30 days at 24 runs/day
window: PASSED

## Ten largest peak ages

| city | valid_time | first written | peak age | write lag |
|---|---|---|---|---|
| EL_PASO | 2026-10-29T16:00:00Z | 2026-10-29T16:12:16Z | 72.3 | 12.3 |
| EL_PASO | 2026-10-27T14:00:00Z | 2026-10-27T14:10:54Z | 70.9 | 10.9 |
| EL_PASO | 2026-10-27T11:00:00Z | 2026-10-27T11:10:10Z | 70.2 | 10.2 |
| MIDLAND | 2026-10-29T16:00:00Z | 2026-10-29T16:10:10Z | 70.2 | 10.2 |
| MIDLAND | 2026-10-27T14:00:00Z | 2026-10-27T14:09:46Z | 69.8 | 9.8 |
| EL_PASO | 2026-10-27T19:00:00Z | 2026-10-27T19:09:28Z | 69.5 | 9.5 |
| EL_PASO | 2026-10-29T12:00:00Z | 2026-10-29T12:09:32Z | 69.5 | 9.5 |
| EL_PASO | 2026-10-27T17:00:00Z | 2026-10-27T17:09:24Z | 69.4 | 9.4 |
| EL_PASO | 2026-10-27T18:00:00Z | 2026-10-27T18:09:26Z | 69.4 | 9.4 |
| EL_PASO | 2026-10-27T21:00:00Z | 2026-10-27T21:09:24Z | 69.4 | 9.4 |

## End-of-soak checks

Run by the owner at the end of the soak (about 06:10Z on 2026-10-30), read-only, on the live project. The check names come from the two SQL files; the pass result and the details in the last column are as the owner relayed them ("17/17 ok" and "7/7 ok", "identical details to 06-09"). The executor did not connect to the live project.

### verify_exposure.sql: 17 of 17 ok

| Check | Result | Relayed detail |
|---|---|---|
| anon_authenticated_grants_are_select_on_two_objects_only | ok | extra grants: none; select grants on the two objects: 4 of 4 |
| anon_can_select_city_rating | ok | |
| anon_can_select_latest_rating | ok | |
| anon_executable_public_functions_are_assert_fresh_only | ok | the only function anon may execute is assert_fresh |
| city_rating_rls_enabled | ok | |
| index_city_rating_city_valid_desc_present | ok | |
| is_provisional_matches_the_labels | ok | |
| is_stale_matches_age_minutes | ok | |
| latest_rating_columns_all_commented | ok | |
| latest_rating_ends_with_the_computed_columns | ok | |
| latest_rating_has_34_columns | ok | 34 columns |
| latest_rating_has_the_four_cities | ok | four cities |
| latest_rating_is_security_invoker | ok | security_invoker=true |
| latest_rating_one_row_per_city | ok | |
| no_write_policy_for_anon_or_authenticated | ok | |
| pipeline_run_not_readable_by_anon | ok | pipeline_run hidden |
| read_policy_city_rating_public_read | ok | city_rating_public_read SELECT, dlr_writer_all ALL |

### verify_monitoring.sql: 7 of 7 ok

| Check | Result | Relayed detail |
|---|---|---|
| assert_fresh_executable_by_anon | ok | |
| dlr_writer_can_read_freshness_log | ok | freshness_log acl {postgres=arwdDxtm/postgres, dlr_writer=r/postgres} |
| freshness_log_not_readable_by_anon_or_authenticated | ok | same acl as above (no anon or authenticated entry) |
| freshness_log_present | ok | |
| log_freshness_not_executable_by_anon_or_authenticated | ok | log_freshness acl {postgres=X/postgres} |
| log_freshness_present | ok | |
| ops_schema_not_usable_by_anon_or_authenticated | ok | ops schema acl {postgres=UC/postgres, dlr_writer=U/postgres} |

### Second live public-key check (06-12-live-checks.json): 20 of 20 ok, exit code 0, "E2E READONLY OK"

Run by the owner in their own terminal at about 06:11Z on 2026-10-30 (`--check-read --check-hidden --check-writes`). Four rows at valid_time 2026-10-30T06:00Z, age_minutes 11, all fresh, is_provisional true; AUSTIN fallback 1825 A. The JSON holds no project URL and no key.

Per-attempt comparison with `06-09-live-checks.json` (E2E-03: any difference is a discrepancy, never treated as equivalent):

| Attempt | Target | 06-09 verdict and status | 06-12 verdict and status | Same? |
|---|---|---|---|---|
| table_insert | city_rating (POST) | pass, 401 42501 | pass, 401 42501 | yes |
| table_upsert | city_rating (POST) | pass, 401 42501 | pass, 401 42501 | yes |
| table_patch | city_rating (PATCH) | pass, 401 42501 | pass, 401 42501 | yes |
| table_delete | city_rating (DELETE) | pass, 401 42501 | pass, 401 42501 | yes |
| view_insert | latest_rating (POST) | pass, 500 55000 | pass, 500 55000 | yes |
| view_patch | latest_rating (PATCH) | pass, 500 55000 | pass, 500 55000 | yes |
| view_delete | latest_rating (DELETE) | pass, 500 55000 | pass, 500 55000 | yes |

All seven attempts are identical in verdict, HTTP status and error code. The 11 read and hidden checks are identical in name, ok flag and detail too (read, four cities, 34 columns, values, flags, count, keyless 401, assert_fresh 200, pipeline_run 401, ops.freshness_log 406).

Discrepancies: **none in any write verdict.** The only two differences between the files are the snapshot checks (`snapshot_before`, `snapshot_unchanged`): 06-09 saw 2212 rows older than its cutoff (sha256 ea66a80f7b53) and 06-12 saw 2520 rows (sha256 ab03ca91fd63). That is expected, not equivalent-by-assumption: the cutoff moves forward and about three more days of history exist now. What matters is that each run found its snapshot identical before and after its own write attempts (2212 rows, then 2520 rows), so the attempted writes changed nothing.

## For the owner

No unexplained breaches and no unexplained probe gaps. There is nothing to annotate. The only item for the owner in Task 3 is the sign-off ("accept" or "re-soak") and removing the 5-minute `dlr-soak-freshness` pg_cron job; the permanent cron-job.org alarm stays on.

## Sign-off

- **Owner decision:** accept. The owner signalled it by running the accept-only teardown `supabase/ops/soak_cron_unschedule.sql`; they did not type the word "accept" separately. The relayed decision is recorded as "accept, signalled by the owner running the accept-only teardown".
- **Date:** 2026-10-30 (about 06:2xZ, after the final export and end-of-soak checks).
- **Annotated run:** no breach and no probe gap exists, so there is nothing to annotate and no `annotations.json` was written (T-06-41: the executor writes no explanation). The report re-run without `--annotations` exits 0 with verdict pass and a `report.json` byte-identical to the committed one.
- **Unschedule result:** the job `dlr-soak-freshness` was removed. The owner's output was `['unschedule'] (True,)` then `['remaining_jobs'] (0,)`, so 0 jobs remain.
- **Kept on purpose (D-13):** `ops.freshness_log` keeps its rows as the frozen record with no new probes, and the permanent cron-job.org "DLR freshness alarm" was not touched. **The freshness alarm stays on permanently (D-13).**
