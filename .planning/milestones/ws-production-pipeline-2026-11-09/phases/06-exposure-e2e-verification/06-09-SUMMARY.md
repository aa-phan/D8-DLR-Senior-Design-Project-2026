---
phase: 06-exposure-e2e-verification
plan: 09
subsystem: infra
tags: [supabase, postgrest, rls, live-push, e2e, sha256-pin, owner-run]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "expose_latest_rating migration and verify_exposure.sql (06-01); e2e_verify_readonly.py with --check-read/--check-hidden/--check-writes (06-04); soak_freshness_log migration and verify_monitoring.sql (06-05); secret scan (06-02)"
  - phase: 05-hourly-live-run
    provides: "05-08 owner sign-off (approve-push), the D-06 gate for every live step"
provides:
  - "Live: public.latest_rating (34 columns, security_invoker), public.assert_fresh, ops.freshness_log and ops.log_freshness() applied to the Supabase project; the publishable key reads exactly one current row per city"
  - "06-09-live-checks.json: committed live evidence (20 checks, exit_code 0, no URL, no key)"
  - "SHA-256 pins of both applied Phase 6 migrations in the default suite"
affects: [06-10, 06-11, 06-12, 06-13]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 4000
  tasks: 3
  commits: 2
plan_head_before: e00b5eccbf4dd410cf74012a97c129c46d7f3f07
plan_head_after: 17729c4223bc6e5617c54a450980c043d2ca27e3

tech-stack:
  added: []
  patterns:
    - "Applied-migration pin: a dict of file name to SHA-256 in the test module, checked against the raw bytes (Phase 4's _ORIGINAL_MIGRATION_SHA256 pattern, extended to two files)"
    - "Owner-run live step with executor-side evidence parsing: the executor never contacts the project; the owner's JSON is parsed, scanned for secrets and pinned"

key-files:
  created:
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-09-PREFLIGHT.md
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-09-live-checks.json
  modified:
    - backend/tests/expose_migration_test.py

key-decisions:
  - "Owner replied \"publish\" to the contract decision: the 34-column latest_rating contract went live as built (D-01, D-02, D-03); renaming or dropping a column now needs a coordinated change with both consuming teams"
  - "A write against the latest_rating VIEW is refused with HTTP 500 (SQLSTATE 55000), not 401/403; the checker counts that as refused and the snapshot was unchanged, so the view stays read-only in practice. Only the table writes carry 401 + 42501"

patterns-established:
  - "Pin every migration the moment it is live, in the same commit as the evidence"

requirements-completed: [API-01, E2E-03]

coverage:
  - id: D1
    description: "The two Phase 6 migrations were applied to the live project: the first dry run listed exactly the two files, the push applied both, the second dry run reports nothing pending"
    requirement: API-01
    verification:
      - kind: manual
        ref: "owner terminal output relayed 2026-10-26 (dry run, push, second dry run: 'Remote database is up to date')"
        status: pass
    human_judgment: false
  - id: D2
    description: "verify_exposure.sql (17 checks) and verify_monitoring.sql (7 checks) returned ok = true on the live database"
    requirement: API-01
    verification:
      - kind: manual
        ref: "owner-started read-only psycopg run of both files, ALL OK (24 of 24)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Live read with the publishable key: four rows (one per city), 34 columns in the published order, count=exact 4, flags agree with age_minutes and the labels, keyless request refused 401, assert_fresh 200, pipeline_run and ops.freshness_log unreadable"
    requirement: API-01
    verification:
      - kind: e2e
        ref: "06-09-live-checks.json (latest_rating_*, city_rating_readable, keyless_request_refused, assert_fresh_answers, hidden:*)"
        status: pass
    human_judgment: false
  - id: D4
    description: "Write protection on the live project: table insert, upsert, patch and delete refused by privilege (HTTP 401, 42501); view insert, patch and delete refused (HTTP 500, 55000); snapshot of 2212 rows sha256 ea66a80f7b53 identical before and after"
    requirement: E2E-03
    verification:
      - kind: e2e
        ref: "06-09-live-checks.json (write:*, snapshot_before, snapshot_unchanged)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Both applied migration files are pinned by SHA-256, and the committed evidence passes the secret scan"
    requirement: E2E-03
    verification:
      - kind: unit
        ref: "backend/tests/expose_migration_test.py#test_phase6_migrations_are_unchanged_after_apply"
        status: pass
      - kind: unit
        ref: "backend/tests/secret_scan_test.py (5 passed, 1 skipped: the env-gated exact-value scan)"
        status: pass
    human_judgment: false

duration: owner-gated (executor time about 15 min across the three runs)
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 09: Live exposure and write-rejection evidence Summary

**Both Phase 6 migrations are live: the publishable key reads one current rating per city through `latest_rating` (34 columns), the private run log is hidden, and every anon write was refused with the data provably unchanged.**

## What was done

1. Task 1 (tracer): the local rehearsal of the exact pending migration set and the live check chain passed, and `06-09-PREFLIGHT.md` was committed (`4d0467d`).
2. Task 2: the owner confirmed the contract.
3. Task 3: the owner applied the migrations and ran the live checks; the executor parsed the evidence, pinned both migrations, ran the secret scan and committed (`17729c4`).

## Gate status (D-06)

`05-08-SUMMARY.md` records the owner's sign-off **approve-push**, so the live steps were allowed. The executor never contacted the project, read `.env`, applied a migration or pushed; the owner ran every live command.

## Owner decision (Task 2), verbatim

> publish

## Schema push (file names only)

First dry run: would push exactly `20261026195124_expose_latest_rating.sql` and `20261026204258_soak_freshness_log.sql`. Push applied the same two files in that order. A third file or a different pending set would have stopped the run; neither happened.

## verify_exposure.sql on the live database (17 checks, all ok)

| Check | Result |
|---|---|
| anon_authenticated_grants_are_select_on_two_objects_only | ok (extra grants: none; select grants on the two objects: 4 of 4) |
| anon_can_select_city_rating | ok |
| anon_can_select_latest_rating | ok |
| anon_executable_public_functions_are_assert_fresh_only | ok (other functions anon may execute: none) |
| city_rating_rls_enabled | ok (relrowsecurity=true) |
| index_city_rating_city_valid_desc_present | ok |
| is_provisional_matches_the_labels | ok (rows checked=4) |
| is_stale_matches_age_minutes | ok (rows checked=4) |
| latest_rating_columns_all_commented | ok (columns without a comment: none) |
| latest_rating_ends_with_the_computed_columns | ok (columns 32-34: age_minutes, is_stale, is_provisional) |
| latest_rating_has_34_columns | ok (columns=34) |
| latest_rating_has_the_four_cities | ok (AUSTIN, CORPUS_CHRISTI, EL_PASO, MIDLAND) |
| latest_rating_is_security_invoker | ok (reloptions={security_invoker=true}) |
| latest_rating_one_row_per_city | ok (rows=4) |
| no_write_policy_for_anon_or_authenticated | ok (write policies reaching the public roles: none) |
| pipeline_run_not_readable_by_anon | ok (anon select=false, authenticated select=false) |
| read_policy_city_rating_public_read | ok (city_rating_public_read SELECT, dlr_writer_all ALL) |

## verify_monitoring.sql on the live database (7 checks, all ok)

| Check | Result |
|---|---|
| assert_fresh_executable_by_anon | ok |
| dlr_writer_can_read_freshness_log | ok (schema usage=true, select=true, write=false) |
| freshness_log_not_readable_by_anon_or_authenticated | ok (acl: postgres full, dlr_writer read) |
| freshness_log_present | ok (ops.freshness_log) |
| log_freshness_not_executable_by_anon_or_authenticated | ok (acl: postgres only) |
| log_freshness_present | ok (ops.log_freshness()) |
| ops_schema_not_usable_by_anon_or_authenticated | ok (usage: postgres and dlr_writer only) |

Run read-only through psycopg from an owner-started process, which is equivalent to pasting the files into the SQL editor.

## Live checks with the publishable key (exit 0, "E2E READONLY OK")

`06-09-live-checks.json`: 20 checks, every `ok` true, `exit_code` 0. Four rows at valid_time 2026-10-27T01:00:00+00:00, age_minutes 18, is_stale false, is_provisional true:

| City | status | rating_amps |
|---|---|---|
| AUSTIN | fallback | 1825 |
| CORPUS_CHRISTI | ok | 1696.2587 |
| EL_PASO | ok | 1262.0601 |
| MIDLAND | ok | 1585.0178 |

Read: HTTP 200 with 4 rows, 34 columns in published order, count=exact 4, rating_amps above 0 and a whole-hour valid_time on every row, flags agree with age_minutes and the labels, a keyless request refused with 401, `assert_fresh` answered 200. Hidden: `public.pipeline_run` HTTP 401, `ops.freshness_log` HTTP 406.

Observed write status (E2E-03):

| Attempt | Target | Status | Code |
|---|---|---|---|
| insert, upsert, patch, delete | `city_rating` table | 401 | 42501 permission denied |
| insert, patch, delete | `latest_rating` view | 500 | 55000 |

Snapshot before and after: 2212 rows older than the cutoff, sha256 ea66a80f7b53, identical.

## Second dry run

`{"upToDate":true,"dryRun":true,"migrations":[],...,"message":"Remote database is up to date."}`

## Secret scan and pins

The JSON was parsed and contains no URL, host, project reference or key (grep for `http`, `supabase.co`, JWT and key prefixes found nothing). With the evidence staged, `backend/tests/secret_scan_test.py` gave 5 passed, 1 skipped (the env-gated exact-value scan, which only runs in the owner's shell). `test_phase6_migrations_are_unchanged_after_apply` pins:

- `20261026195124_expose_latest_rating.sql` = 7e2d5f0192e4eab126f66a703ac31d69504c463885e34f764ff78eb465dea0cb
- `20261026204258_soak_freshness_log.sql` = 246da223294c58809e03743abb62f6fa0107015488af631b0cf64fbffa8c8552

`backend/tests/expose_migration_test.py` runs 22 passed.

## Deviations from Plan

None - the executor-side steps ran exactly as written.

## Discrepancies

1. **View writes return HTTP 500, not 401/403.** The plan expected every anon write to be 401 or 403 with 42501. Table writes were (401, 42501). Writes against the `latest_rating` view were refused with HTTP 500 and code 55000 (SQLSTATE 55000 is Postgres's "object not in prerequisite state", which it raises for a write against a non-updatable view; cause inferred from the code, not separately verified). The checker counts any refusal as passed and the snapshot was unchanged, so the protection holds; the status code just differs from the plan's wording. Nothing to fix; a future reader should not expect 401 on view writes.
2. **AUSTIN's current row was a fallback** (static rating, 1825 A, status fallback) at check time. Informational: the newest-row-wins rule (06-01) correctly shows the fallback, and the static-rating fallback is the safe side.
3. **The D-09 soak start target has passed.** The target for starting the 72 h soak clock was 2026-10-27T00:00Z; the live check ran about 01:18Z that day. Recorded for 06-10 to plan the soak timeline from the actual start.
4. **Verify SQL ran via psycopg, not the SQL editor.** Same read-only statements, owner-started process.

## Known Stubs

None.

## Threat Flags

None. The plan's register (T-06-30 through T-06-33) was mitigated as designed: dry run listed exactly the expected files, both verify files were all ok, the second dry run showed nothing pending, the evidence passed the secret scan, and the write check left the snapshot unchanged.

## Self-Check: PASSED

- 06-09-PREFLIGHT.md, 06-09-live-checks.json, expose_migration_test.py exist; commits `4d0467d` and `17729c4` are on main.
