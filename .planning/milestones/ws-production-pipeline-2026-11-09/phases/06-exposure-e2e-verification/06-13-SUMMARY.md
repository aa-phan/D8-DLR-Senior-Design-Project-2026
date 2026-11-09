---
phase: 06-exposure-e2e-verification
plan: 13
subsystem: testing
tags: [permissions, exposure, supabase, grants, t-04-22, owner-run]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "06-09 and 06-12 live checks to compare against; verifier and smoke tooling from 06-01, 06-04 and Phase 4"
provides:
  - "06-13-live-checks.json: third live public-key check, 20 of 20 ok, after the 2026-10-30 platform change (E2E-03, API-01)"
  - "06-13-smoke.json: T-04-22 writer smoke, 14 of 14 ok including consumers_cannot_write"
  - "06-13-PREFLIGHT.md: date rule and owner command sheet"
affects: [07-reval]

actuals:
  tokens: 24000
  tasks: 2
  commits: 2
plan_head_before: 2e0b730575466cc7b6a6efba3a65356a96b81e27
plan_head_after: 367c5aa399a770d2811ce13f914dd652681222e6

tech-stack:
  added: []
  patterns:
    - "Owner-run live steps with executor-side evidence checks; no URL, reference or key in committed evidence"

key-files:
  created:
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-13-PREFLIGHT.md
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-13-live-checks.json
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-13-smoke.json
  modified: []

key-decisions:
  - "Write verdicts after the 2026-10-30 platform change are identical to 06-09 and 06-12, so E2E-03 is treated as holding; the snapshot count and digest differences are expected history growth, reported rather than assumed"

patterns-established: []

requirements-completed: [E2E-03, API-01]

coverage:
  - id: D1
    description: "After the 2026-10-30 default-grant change, the public key still reads four cities with 34 columns, cannot read the run log or soak log, and every write is refused with the snapshot unchanged"
    requirement: E2E-03
    verification:
      - kind: other
        ref: "06-13-live-checks.json: exit 0, 20 of 20 ok; seven attempts identical in verdict, HTTP status and code to 06-09 and 06-12 (programmatic comparison)"
        status: pass
    human_judgment: false
  - id: D2
    description: "verify_exposure.sql and verify_monitoring.sql report every check ok on the live project after the change"
    requirement: E2E-03
    verification:
      - kind: other
        ref: "read-only SQL runner output 17 of 17 and 7 of 7, details identical to 06-09 and 06-12 (run by the orchestrator at the owner's explicit request)"
        status: pass
    human_judgment: false
  - id: D3
    description: "T-04-22: consumers_cannot_write passes on the live project after the change"
    requirement: API-01
    verification:
      - kind: other
        ref: "06-13-smoke.json: schema supabase_smoke/1, all_passed true, checks.consumers_cannot_write true, 14 of 14 checks true, info.anon_can_select true (expected after Phase 6)"
        status: pass
    human_judgment: false
  - id: D4
    description: "No committed evidence contains the project URL, reference, key or database URL"
    requirement: E2E-03
    verification:
      - kind: test
        ref: "backend/tests/secret_scan_test.py with both JSONs staged: 5 passed, 1 skipped (owner-local live check); grep for URL, host, key and connection-string patterns over both files: no hits"
        status: pass
    human_judgment: false

duration: 1 session across the pre-flight (2026-10-30) and one owner checkpoint (2026-11-01)
completed: 2026-11-01
status: complete
---

# Phase 6 Plan 13: Post-2026-10-30 permission re-check Summary

**After Supabase's 2026-10-30 default-grant change the public key still reads all four cities, still cannot read the private logs, and every write attempt is refused exactly as in 06-09 and 06-12; the writer smoke confirms the public roles have no write permission, closing T-04-22.**

## Performance

- **Run date:** 2026-10-31 and 2026-11-01 (after 2026-10-31T00:00Z and after the 72 h window ended on 2026-10-30T03:35Z, so the precondition holds)
- **Tasks:** 2 (tracer pre-flight, owner re-check and smoke)
- **Task commits:** `fa88aa3` (pre-flight), `367c5aa` (evidence)

## Who ran what

- **Step 1, permission lists (verify_exposure.sql, verify_monitoring.sql):** run by the orchestrator at the owner's explicit request, through a read-only SQL runner. The database URL was loaded in-process and never printed. This differs from the plan, which has the owner paste the SQL editor output.
- **Step 2, public-key live checks:** run by the owner in their terminal (about 2026-11-01T22:58Z). The executor read the evidence file only.
- **Step 3, writer smoke (T-04-22):** run by the owner from Claude Code with `!`, exit code 0, report checked at 2026-11-01T23:59:01Z.
- The executor never contacted the live project, read `.env`, changed a grant or pushed.

## verify_exposure.sql table (17 of 17 ok)

The runner prints the check names and results as text. Details are identical to 06-09 and 06-12.

| Check | Result |
|---|---|
| Extra grants on public roles beyond select | none (ok) |
| Select grants on `city_rating` and `latest_rating` | 4 of 4 (ok) |
| Anonymous-executable public functions | none besides `assert_fresh` (ok) |
| Row-level security on `city_rating` | on (ok) |
| Latest-lookup index | present (ok) |
| `latest_rating` columns | 34, ending `age_minutes`, `is_stale`, `is_provisional` (ok) |
| Cities in `latest_rating` | four, one row per city (ok) |
| View `security_invoker` | true (ok) |
| Write policy for public roles | none (ok) |
| `pipeline_run` hidden from public roles | yes (ok) |
| Policies | `city_rating_public_read` SELECT, `dlr_writer_all` ALL (ok) |

The relayed output lists these as 17 individual ok lines; the rows above group them by subject. `verify_monitoring.sql` is 7 of 7 ok with identical ACLs: `{postgres=arwdDxtm/postgres,dlr_writer=r/postgres}`, `{postgres=X/postgres}` and `{postgres=UC/postgres,dlr_writer=U/postgres}`. Final line: ALL OK.

## Live checks (06-13-live-checks.json)

Exit code 0, 20 of 20 checks ok. Reads: HTTP 200 with four rows (AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO), 34 columns in the published order, `count=exact` 4, keyless request refused with 401, `assert_fresh` answers 200 with every city fresh, `public.pipeline_run` 401, `ops.freshness_log` 406.

## Three-way per-attempt comparison

Programmatic comparison of the `attempts` arrays (name, method, path, status, code, verdict) gives identical results in all three files.

| Attempt | Method, object | 06-13 | 06-12 | 06-09 |
|---|---|---|---|---|
| table_insert | POST `city_rating` | 401 / 42501 / pass | 401 / 42501 / pass | 401 / 42501 / pass |
| table_upsert | POST `city_rating` | 401 / 42501 / pass | 401 / 42501 / pass | 401 / 42501 / pass |
| table_patch | PATCH `city_rating` | 401 / 42501 / pass | 401 / 42501 / pass | 401 / 42501 / pass |
| table_delete | DELETE `city_rating` | 401 / 42501 / pass | 401 / 42501 / pass | 401 / 42501 / pass |
| view_insert | POST `latest_rating` | 500 / 55000 / pass | 500 / 55000 / pass | 500 / 55000 / pass |
| view_patch | PATCH `latest_rating` | 500 / 55000 / pass | 500 / 55000 / pass | 500 / 55000 / pass |
| view_delete | DELETE `latest_rating` | 500 / 55000 / pass | 500 / 55000 / pass | 500 / 55000 / pass |

All 18 non-snapshot checks have details identical across the three files. The two snapshot checks differ in count and digest only:

| Run | Rows older than cutoff | sha256 (12 hex) | Before equals after |
|---|---|---|---|
| 06-09 | 2212 | ea66a80f7b53 | yes |
| 06-12 | 2520 | ab03ca91fd63 | yes |
| 06-13 | 2779 | 6415993f85b8 | yes |

## Writer smoke (06-13-smoke.json), T-04-22

Schema `supabase_smoke/1`, `all_passed` true. 14 of 14 checks true: connected, role_is_dlr_writer, ssl_in_use, server_version_ge_15, session_timezone_utc, tables_exist, rls_enabled, writer_policies_exist, writer_privileges_exact, **consumers_cannot_write**, rating_upsert_idempotent, run_row_idempotent, delete_denied, utc_hour_check_zone_independent. Role `dlr_writer`, server version 170011, `anon_can_select` true (informational, expected after Phase 6).

**T-04-22: closed.** The platform change did not hand the public roles any write permission on `public.city_rating` or `public.pipeline_run`, as shown by the smoke and by the permission list.

## Task Commits

1. **Task 1 (tracer): pre-flight** - `fa88aa3` (docs)
2. **Task 2: owner re-check and T-04-22 smoke evidence** - `367c5aa` (docs)

**Plan metadata:** the final docs commit (this SUMMARY plus state files).

## Deviations from Plan

1. **Step 1 run by the orchestrator, not pasted from the SQL editor.** At the owner's explicit request the orchestrator ran the read-only SQL runner on 2026-10-31 and 2026-11-01 with the database URL loaded in-process and never printed. The output is the same two verify scripts the plan names.
2. **Optional `gh workflow run supabase_smoke.yml` not run.** The plan marks it optional.
3. **Co-Authored-By line.** The plan text names Claude Opus 5.5; commits carry the runtime's configured attribution lines (Claude Sonnet 5.5 and the session link).

## Discrepancies

- **Write verdicts: none.** All seven attempts match 06-09 and 06-12 in verdict, HTTP status and code. No new grant, no changed status, no broken read.
- **Snapshot count and digest differ (expected).** 2212, 2520 and 2779 rows with different digests, because the cutoff moved forward and history grew. Each run found its own snapshot identical before and after its write attempts.
- **AUSTIN has 696 rows against 697 for the other three cities (informational).** Reported by the smoke over the full table history, newest `2026-11-01T23:00:00Z` for all four. One hour is missing from AUSTIN's history; it is not a permission matter and not a freshness breach. Left for the Phase 7 review.
- **Owner-side facts are relayed.** The SQL runner output, the live-check run and the smoke output come from the orchestrator and owner. The executor verified only the committed files and the repository.

## Issues Encountered

None.

## Self-Check: PASSED

Verified before commit: `06-13-PREFLIGHT.md`, `06-13-live-checks.json` and `06-13-smoke.json` exist; commits `fa88aa3` and `367c5aa` are ancestors of HEAD.
