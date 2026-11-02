---
status: complete
phase: 06-exposure-e2e-verification
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md, 06-03-SUMMARY.md, 06-04-SUMMARY.md, 06-05-SUMMARY.md, 06-06-SUMMARY.md, 06-07-SUMMARY.md, 06-08-SUMMARY.md, 06-09-SUMMARY.md, 06-10-SUMMARY.md, 06-11-SUMMARY.md, 06-12-SUMMARY.md, 06-13-SUMMARY.md, 06-REVIEW-FIX.md]
started: 2026-11-02T01:54:07Z
updated: 2026-11-02T03:27:20.081Z
---

<!-- Human checkpoints group the coverage entries marked present (human_judgment / validation_failed) by the live action that settles them; each test lists the entries it covers. Coverage blocks in 06-09, 06-11, 06-12, 06-13 use a verification kind the classifier rejects (invalid_kind); those entries are kept as human checks, none dropped. SUMMARYs carry plan_head_before/after but no commits: field (legacy warning, not a mismatch). -->

## Current Test

[testing complete]

## Tests

### 1. Real project values are in no tracked file
expected: In a shell (not from a file), export SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY and SUPABASE_DB_URL, then run `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/secret_scan_test.py` from the repo root. The exact-value test runs (not skipped) and passes: no tracked file, including the new code-review fix commits, holds the real URL, key or database URL.
covers: 06-02/D5, 06-11/D4, 06-12/D5, 06-13/D4
result: pass

### 2. Live public-key check still all ok with the fixed checker
expected: With SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY exported, `.venv/bin/python backend/e2e_verify_readonly.py --check-read --check-hidden --check-writes` exits 0 and prints E2E READONLY OK. All checks are ok, including the new key sanity read and the hidden-table checks (each refusal now names its reason), and the seven write attempts are refused as in 06-13 (table writes 401/42501, view writes 500/55000).
covers: 06-04/D6, 06-01/D10, code review WR-02, WR-06
result: pass

### 3. verify_exposure.sql shows 18 of 18 on the live database
expected: Running `supabase/ops/verify_exposure.sql` in the Supabase SQL editor returns 18 rows, all ok = true, including the new `anon_authenticated_hold_no_write_or_column_privilege_in_public`. `verify_monitoring.sql` is still 7 of 7.
covers: 06-09/D1, 06-09/D2, 06-05/D9, code review WR-01
result: pass
evidence: run by Claude at the owner's request on 2026-11-01 with the read-only runner (connection read_only, URL loaded in-process, never printed): verify_exposure.sql 18 of 18 ok, verify_monitoring.sql 7 of 7 ok, ALL OK

### 4. Live trace still works with the read-only transaction change
expected: Pick the most recent hh:05 cron-job.org execution (time in UTC with Z, and its HTTP status). Run `.venv/bin/python backend/e2e_trace.py --execution-time <time>Z --execution-status <status>`. It prints E2E TRACE OK, one candidate run, all four cities match. (The code-review fix WR-04 changed how the trace opens its read-only database session; only a live run exercises that.)
covers: 06-08/D6, code review WR-04
result: pass
evidence: run by Claude at the owner's request on 2026-11-02 for the 09:05 PM CST execution (2026-11-02T03:05:00Z, HTTP 204): E2E TRACE OK, run 41381103142, 8 of 8 links pass, 4 cities match and current
observation: An attempt at 2026-11-01T09:05Z (time misread) found two workflow_dispatch runs at 09:05Z (41287336869, 41291536750) and none at 08:05Z, the morning DST ended; whether the 08:00Z slot was written is unchecked (live DB query not permitted)

### 5. Consumer examples ran live as recorded
expected: 06-11 records that curl.sh, read_ratings.py (Python 3.9.6 and 3.12.13) and supabase_js.mjs (supabase-js 2.117.3) each ran against the live project and exited 0, and that you approved supabase-js 2.117.3 before installing it outside the repo with install scripts off. That matches what you ran and approved.
covers: 06-06/D8, 06-11/D1
result: pass

### 6. Soak result and the window's events are complete
expected: I re-ran the 72 h soak report and the dry soak on the committed data with the fixed code: both are byte-identical PASS (864 of 864 probes, no breach; dry worst age 73.3 min). Nothing happened in the window that the data cannot show: no cron-job.org edits, pauses or incidents between 2026-10-27T03:35Z and 2026-10-30T03:35Z.
covers: 06-03/D6, 06-07/D7, 06-12/D2, code review WR-05
result: pass

### 7. Owner decisions are recorded correctly
expected: 06-10 records your "go" at 03:34:58Z, so the window start G = 2026-10-27T03:35:00Z. 06-12 records your sign-off as accept, shown by running soak_cron_unschedule.sql (output: unschedule True, remaining_jobs 0), with the permanent "DLR freshness alarm" left on. Both match what you decided and did.
covers: 06-10/D5, 06-12/D4
result: pass

### 8. Alarm recovery email arrives
expected: When the freshness alarm goes from failing back to ok, cron-job.org sends you a recovery email. (06-10 recorded that this email never arrived in the drill: failure emails work, recovery is unproven.)
covers: 06-10/D3
result: pass

### 9. PSS/E team answered the interpreter question
expected: The Power Systems team answered the PSS/E Python question (06-11 records: Python 3.14.0, OpenSSL 3.0.18, read_ratings.py exit 0 on 2026-10-27).
covers: 06-11/D5
result: pass

### 10. No raw detector error text in stored public rows
expected: In the SQL editor, `select count(*) from public.city_rating where alerts::text ilike '%detector error%';` returns 0, or every match holds no file path or internals. (The WR-03 fix redacts new rows only. Note: the detector still puts the raw error message into the alert, and redaction does not remove file paths. If you want only the error type stored, report that here.)
covers: code review WR-03
result: pass

### 11. Cold Start Smoke Test
expected: Starting from an empty Postgres, every migration applies cleanly and latest_rating answers a query with live-shaped rows.
result: pass
source: automated
evidence: DLR_TEST_PG_AUTOSTART=1 local Postgres tests (expose_migration_test, soak_log_migration_test) apply all migrations to a fresh database and query the view; 46 passed on 2026-11-01 after the code-review fixes

### 12. latest_rating invoker view with the 34-column contract in order, equal to latest_rating_co
expected: latest_rating invoker view with the 34-column contract in order, equal to latest_rating_contract.LATEST_COLUMNS, with the three computed columns last
result: pass
source: automated
coverage_id: 06-01/D1

### 13. Newest row per city wins even when it is a fallback row (D-04)
expected: Newest row per city wins even when it is a fallback row (D-04)
result: pass
source: automated
coverage_id: 06-01/D2

### 14. 90-minute rule agrees between age_minutes, is_stale and assert_fresh, including the exact
expected: 90-minute rule agrees between age_minutes, is_stale and assert_fresh, including the exact boundary
result: pass
source: automated
coverage_id: 06-01/D3

### 15. is_provisional is true for the real live label, the real backfill label and a word only in
expected: is_provisional is true for the real live label, the real backfill label and a word only in config_version; false for a lifted pair; drift guard in the default suite
result: pass
source: automated
coverage_id: 06-01/D4

### 16. anon and authenticated are refused INSERT, UPDATE, DELETE, TRUNCATE by privilege (42501) a
expected: anon and authenticated are refused INSERT, UPDATE, DELETE, TRUNCATE by privilege (42501) and cannot read pipeline_run, starting from every legacy default grant
result: pass
source: automated
coverage_id: 06-01/D5

### 17. The view applies the caller's RLS; with the read policy dropped anon sees zero rows
expected: The view applies the caller's RLS; with the read policy dropped anon sees zero rows
result: pass
source: automated
coverage_id: 06-01/D6

### 18. assert_fresh contract (200 JSON, PT503 naming cities, 22023 out of range, invoker, stable,
expected: assert_fresh contract (200 JSON, PT503 naming cities, 22023 out of range, invoker, stable, empty search_path, anon-executable, no PUBLIC execute); city list equals config.LOCATIONS
result: pass
source: automated
coverage_id: 06-01/D7

### 19. Concurrency edge: same-key re-upsert by the Phase 4 writer leaves one row per city; re-app
expected: Concurrency edge: same-key re-upsert by the Phase 4 writer leaves one row per city; re-applying the migration is idempotent
result: pass
source: automated
coverage_id: 06-01/D8

### 20. verify_exposure.sql is one read-only SELECT of 17 checks, all true on the seeded local dat
expected: verify_exposure.sql is one read-only SELECT of 17 checks, all true on the seeded local database, and each check can fail
result: pass
source: automated
coverage_id: 06-01/D9

### 21. Default suite flags a project host, a pooler user with a 20-character reference and a publ
expected: Default suite flags a project host, a pooler user with a 20-character reference and a publishable key, each with exactly one finding on its planted line
result: pass
source: automated
coverage_id: 06-02/D1

### 22. Placeholders (project-ref, [ref], ${SUPABASE_URL}, 16-character dummy reference, bare pref
expected: Placeholders (project-ref, [ref], ${SUPABASE_URL}, 16-character dummy reference, bare prefix with dots, <publishable-key>, generic pooler host) never trip the scan, and no finding contains a planted value
result: pass
source: automated
coverage_id: 06-02/D2

### 23. The whole tracked tree is clean under the new patterns
expected: The whole tracked tree is clean under the new patterns
result: pass
source: automated
coverage_id: 06-02/D3

### 24. Exact-value helpers derive the right values from exported variables and report path and li
expected: Exact-value helpers derive the right values from exported variables and report path and line only; the env-gated test skips when nothing is exported
result: pass
source: automated
coverage_id: 06-02/D4

### 25. export reads the live window read-only (read-only setting first, SELECT-only SQL with boun
expected: export reads the live window read-only (read-only setting first, SELECT-only SQL with bound parameters) and writes the four files without any URL, host or credential
result: pass
source: automated
coverage_id: 06-03/D1

### 26. export then report end to end gives write lag 8 min, peak age 68 min, every slot ok and a
expected: export then report end to end gives write lag 8 min, peak age 68 min, every slot ok and a PASS verdict on fixtures
result: pass
source: automated
coverage_id: 06-03/D2

### 27. Retries, backfill rows, late fills and fallback rows do not distort lag or peak age; a mis
expected: Retries, backfill rows, late fills and fallback rows do not distort lag or peak age; a missing slot is a 128.0 min breach and exit 1
result: pass
source: automated
coverage_id: 06-03/D3

### 28. The 90 minute boundary holds on the exact timedelta: 90.0 passes, 90.1 and a value that di
expected: The 90 minute boundary holds on the exact timedelta: 90.0 passes, 90.1 and a value that displays as 90.0 but is 2 s over both breach; above 75 warns
result: pass
source: automated
coverage_id: 06-03/D4

### 29. Short or empty windows exit 1, bad input exits 2 naming the file or column, and output is
expected: Short or empty windows exit 1, bad input exits 2 naming the file or column, and output is ordered by config.LOCATIONS and byte-identical on rerun
result: pass
source: automated
coverage_id: 06-03/D5

### 30. Standard-library REST client: env-only config refusing secret keys and service_role tokens
expected: Standard-library REST client: env-only config refusing secret keys and service_role tokens before any request, apikey-only header, error statuses as values, paging that stops only on an empty page, count=exact, Python 3.7+ timestamp parsing
result: pass
source: automated
coverage_id: 06-04/D1

### 31. --check-read proves one current rating per city with the 34 documented columns, whole-hour
expected: --check-read proves one current rating per city with the 34 documented columns, whole-hour valid_time, is_stale / is_provisional consistent, count=exact 4, keyless refused, assert_fresh 200/503, through main() against the fake
result: pass
source: automated
coverage_id: 06-04/D2

### 32. --check-hidden: pipeline_run and ops.freshness_log must answer 401/403/404/406; any 2xx, e
expected: --check-hidden: pipeline_run and ops.freshness_log must answer 401/403/404/406; any 2xx, even an empty list, fails
result: pass
source: automated
coverage_id: 06-04/D3

### 33. --check-writes (E2E-03): seven public-key write attempts pass only on privilege-layer refu
expected: --check-writes (E2E-03): seven public-key write attempts pass only on privilege-layer refusal, plus an identical before/after snapshot; RLS-only, accepted, inconclusive and data-changing cases fail; RECOVERY printed, never executed
result: pass
source: automated
coverage_id: 06-04/D4

### 34. No output line, exception message or --json-out file holds the project URL, host, project
expected: No output line, exception message or --json-out file holds the project URL, host, project reference or key, including when a network error or an HTTP error body echoes them
result: pass
source: automated
coverage_id: 06-04/D5

### 35. ops.log_freshness() writes one row per config.LOCATIONS city; breach is latest_rating's is
expected: ops.log_freshness() writes one row per config.LOCATIONS city; breach is latest_rating's is_stale and equals age_seconds > 5400, to the microsecond at the 90-minute boundary
result: pass
source: automated
coverage_id: 06-05/D1

### 36. A city with no rating is logged with null valid time, null age and breach true
expected: A city with no rating is logged with null valid time, null age and breach true
result: pass
source: automated
coverage_id: 06-05/D2

### 37. ops is unreachable for anon, authenticated and PUBLIC (schema, table, sequence, function);
expected: ops is unreachable for anon, authenticated and PUBLIC (schema, table, sequence, function); dlr_writer can read the log and cannot write or call the function
result: pass
source: automated
coverage_id: 06-05/D3

### 38. The migration schedules nothing (no pg_cron reference in code), sorts after the expose mig
expected: The migration schedules nothing (no pg_cron reference in code), sorts after the expose migration, grants only the two dlr_writer read rights, and its city list equals config.LOCATIONS
result: pass
source: automated
coverage_id: 06-05/D4

### 39. verify_monitoring.sql is one read-only SELECT of 7 checks, all true locally, and each chec
expected: verify_monitoring.sql is one read-only SELECT of 7 checks, all true locally, and each check can fail
result: pass
source: automated
coverage_id: 06-05/D5

### 40. Re-applying the soak migration succeeds, changes no grant, definition, comment or logged r
expected: Re-applying the soak migration succeeds, changes no grant, definition, comment or logged row; the expose migration's tests still pass with it present
result: pass
source: automated
coverage_id: 06-05/D6

### 41. The schedule file creates one named job and is repeatable; the unschedule file removes it,
expected: The schedule file creates one named job and is repeatable; the unschedule file removes it, touches no other job and is a no-op when absent (against a stub cron schema)
result: pass
source: automated
coverage_id: 06-05/D7

### 42. soak_probe_smoke.sql passes on healthy probes and flags a failed run, a missing run, a sho
expected: soak_probe_smoke.sql passes on healthy probes and flags a failed run, a missing run, a short probe, a breach, a paused or re-scheduled or re-pointed job, an unscheduled job and an empty log; evidence older than the last three is ignored
result: pass
source: automated
coverage_id: 06-05/D8

### 43. Python 3.7+ standard-library example: parse_ts helper, default TLS verification, current r
expected: Python 3.7+ standard-library example: parse_ts helper, default TLS verification, current row per city and one city's 2,500 rows paged past the 1000-row cap, run as written on /usr/bin/python3 (3.9.6) and the repository's 3.12
result: pass
source: automated
coverage_id: 06-06/D1

### 44. curl example: set -euo pipefail, count=exact HEAD then GETs at offsets 0, 1000 and 2000, c
expected: curl example: set -euo pipefail, count=exact HEAD then GETs at offsets 0, 1000 and 2000, curl -f on every call, GET and HEAD only
result: pass
source: automated
coverage_id: 06-06/D2

### 45. supabase-js example passes node --check, reads both variables, queries latest_rating and c
expected: supabase-js example passes node --check, reads both variables, queries latest_rating and city_rating, orders valid_time ascending, pages with .range and breaks on an empty page; nothing installed
result: pass
source: automated
coverage_id: 06-06/D3

### 46. All three examples are read-only, send one credential header (apikey) and write no local f
expected: All three examples are read-only, send one credential header (apikey) and write no local file; none carries a project URL, reference or key (06-02 scan line check)
result: pass
source: automated
coverage_id: 06-06/D4

### 47. docs/integration/rest-api.md column table lists exactly LATEST_COLUMNS in order with type,
expected: docs/integration/rest-api.md column table lists exactly LATEST_COLUMNS in order with type, unit and meaning; every *_amps and *_mw row says PROVISIONAL; identity columns explained as the way a change shows; age_minutes, is_stale and is_provisional state their exact rules
result: pass
source: automated
coverage_id: 06-06/D5

### 48. The doc states the freshness contract and its decisions, fallback rows as safe published v
expected: The doc states the freshness contract and its decisions, fallback rows as safe published values, rpc/assert_fresh 200/503, the 1000-row cap, write rejection and public history, 60-second polling, the PSS/E interpreter question, and the Phase 7 hand-off (REVAL-01 must remove the word provisional from both strings); no connection detail, no bearer instruction, all links resolve
result: pass
source: automated
coverage_id: 06-06/D6

### 49. The four existing consumer docs link to rest-api.md, keep every heading and every statemen
expected: The four existing consumer docs link to rest-api.md, keep every heading and every statement Phase 4's schema-doc test pins, and the schema doc carries the is_provisional word rule and the Phase 7 hand-off
result: pass
source: automated
coverage_id: 06-06/D7

### 50. export --mode soak also writes probes.csv from ops.freshness_log in the same read-only ses
expected: export --mode soak also writes probes.csv from ops.freshness_log in the same read-only session with bound parameters
result: pass
source: automated
coverage_id: 06-07/D1

### 51. Exact write-based breach intervals with the strict 90 minute rule (exactly 90 is fresh, 90
expected: Exact write-based breach intervals with the strict 90 minute rule (exactly 90 is fresh, 90 min 2 s is a breach even though it displays 90.0), no-prior-row cities, late fills and backfill ignored, deterministic order and byte-identical reports
result: pass
source: automated
coverage_id: 06-07/D2

### 52. Probe coverage: gaps (edges included), zero probes, short windows fail; probe breaches mer
expected: Probe coverage: gaps (edges included), zero probes, short windows fail; probe breaches merge into write breaches or stand alone; incomplete probes are listed
result: pass
source: automated
coverage_id: 06-07/D3

### 53. Every breach has a rule-derived cause or needs an owner annotation (printed verbatim with
expected: Every breach has a rule-derived cause or needs an owner annotation (printed verbatim with author and date); malformed annotations exit 2; unknown ids warn
result: pass
source: automated
coverage_id: 06-07/D4

### 54. Deploys are derived from the rows, classified through git with validated versions, listed
expected: Deploys are derived from the rows, classified through git with validated versions, listed beside the owner's events, and shown as breach context without excusing it (D-08)
result: pass
source: automated
coverage_id: 06-07/D5

### 55. Runbook sections 14, 15, 16 exist, state the alarm rule and the response, the soak command
expected: Runbook sections 14, 15, 16 exist, state the alarm rule and the response, the soak commands and teardown, and the five-check re-check; flags, job name and thresholds match the scripts; no secret-shaped line
result: pass
source: automated
coverage_id: 06-07/D6

### 56. Happy-path trace: one execution maps to one successful dispatch run, whose four city_ratin
expected: Happy-path trace: one execution maps to one successful dispatch run, whose four city_rating rows (SQL) equal the REST rows for all 31 stored columns, listed in config.LOCATIONS order, exit 0, with a markdown table and JSON evidence
result: pass
source: automated
coverage_id: 06-08/D1

### 57. Comparison rules: Z and +00:00 are the same instant, floats compared exactly (1e-9 is a mi
expected: Comparison rules: Z and +00:00 are the same instant, floats compared exactly (1e-9 is a mismatch naming city and column), arrays element by element, null only with null, booleans never equal numbers
result: pass
source: automated
coverage_id: 06-08/D2

### 58. is_provisional agrees with the word rule on rating_basis and config_version; the current-o
expected: is_provisional agrees with the word rule on rating_basis and config_version; the current-or-superseded column separates 'current', 'superseded by a later slot' (informational) from overwritten rows
result: pass
source: automated
coverage_id: 06-08/D3

### 59. Every failing link is named: candidate window edges (-60 s and +300 s in, 301 s out, zero
expected: Every failing link is named: candidate window edges (-60 s and +300 s in, 301 s out, zero or two candidates), conclusion, event and workflow name, superseded rows naming the newer run, empty or one-sided rows, incomplete pipeline_run, non-2xx execution status, disagreeing --run-id, usage and configuration errors as exit 2
result: pass
source: automated
coverage_id: 06-08/D4

### 60. Read-only and leak-free: the first statement is the read-only setting, run_id is a bound p
expected: Read-only and leak-free: the first statement is the read-only setting, run_id is a bound parameter, REST is GET only, no database URL, project URL, host or key reaches any output, file or exception text, and re-runs give byte-identical evidence
result: pass
source: automated
coverage_id: 06-08/D5

### 61. Live read with the publishable key: four rows (one per city), 34 columns in the published
expected: Live read with the publishable key: four rows (one per city), 34 columns in the published order, count=exact 4, flags agree with age_minutes and the labels, keyless request refused 401, assert_fresh 200, pipeline_run and ops.freshness_log unreadable
result: pass
source: automated
coverage_id: 06-09/D3

### 62. Write protection on the live project: table insert, upsert, patch and delete refused by pr
expected: Write protection on the live project: table insert, upsert, patch and delete refused by privilege (HTTP 401, 42501); view insert, patch and delete refused (HTTP 500, 55000); snapshot of 2212 rows sha256 ea66a80f7b53 identical before and after
result: pass
source: automated
coverage_id: 06-09/D4

### 63. Both applied migration files are pinned by SHA-256, and the committed evidence passes the
expected: Both applied migration files are pinned by SHA-256, and the committed evidence passes the secret scan
result: pass
source: automated
coverage_id: 06-09/D5

### 64. pg_cron job dlr-soak-freshness is active every 5 minutes and the probe smoke check returne
expected: pg_cron job dlr-soak-freshness is active every 5 minutes and the probe smoke check returned every check ok with 4 rows per probe and no breach
result: pass
source: automated
coverage_id: 06-10/D1

### 65. Permanent alarm 'DLR freshness alarm' executed at least twice with HTTP 200 and the failur
expected: Permanent alarm 'DLR freshness alarm' executed at least twice with HTTP 200 and the failure-email path was proven by the drill (503 then email at 03:24Z)
result: pass
source: automated
coverage_id: 06-10/D2

### 66. Dry soak over 2026-10-25T00:00Z to 2026-10-27T02:00Z passes: 50 of 50 slots, peak age 73.3
expected: Dry soak over 2026-10-25T00:00Z to 2026-10-27T02:00Z passes: 50 of 50 slots, peak age 73.3 min, no rating older than 90 min
result: pass
source: automated
coverage_id: 06-10/D4

### 67. curl.sh, read_ratings.py on /usr/bin/python3 3.9.6 and on .venv Python 3.12.13, and supaba
expected: curl.sh, read_ratings.py on /usr/bin/python3 3.9.6 and on .venv Python 3.12.13, and supabase_js.mjs each exited 0 on the live project, printed four cities and paged one city's history
result: pass
source: automated
coverage_id: 06-11/D2

### 68. Trace: one scheduled execution (2026-10-27T04:05:02Z, HTTP 204) to one successful Actions
expected: Trace: one scheduled execution (2026-10-27T04:05:02Z, HTTP 204) to one successful Actions run (40447756754), four rows in SQL and REST, 31 stored columns equal per city, is_provisional word rule holds
result: pass
source: automated
coverage_id: 06-11/D3

### 69. Over exactly 72 h from G, each city's current rating was never more than 90 minutes old at
expected: Over exactly 72 h from G, each city's current rating was never more than 90 minutes old at any probe or any write instant; the probe log has no gap longer than 11 minutes
result: pass
source: automated
coverage_id: 06-12/D1

### 70. At soak end verify_exposure.sql (17 of 17) and verify_monitoring.sql (7 of 7) report every
expected: At soak end verify_exposure.sql (17 of 17) and verify_monitoring.sql (7 of 7) report every check ok, and a second --check-read --check-hidden --check-writes run exits 0 with all seven write verdicts identical to 06-09
result: pass
source: automated
coverage_id: 06-12/D3

### 71. After the 2026-10-30 default-grant change, the public key still reads four cities with 34
expected: After the 2026-10-30 default-grant change, the public key still reads four cities with 34 columns, cannot read the run log or soak log, and every write is refused with the snapshot unchanged
result: pass
source: automated
coverage_id: 06-13/D1

### 72. verify_exposure.sql and verify_monitoring.sql report every check ok on the live project af
expected: verify_exposure.sql and verify_monitoring.sql report every check ok on the live project after the change
result: pass
source: automated
coverage_id: 06-13/D2

### 73. T-04-22: consumers_cannot_write passes on the live project after the change
expected: T-04-22: consumers_cannot_write passes on the live project after the change
result: pass
source: automated
coverage_id: 06-13/D3

## Summary

total: 73
passed: 73
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
