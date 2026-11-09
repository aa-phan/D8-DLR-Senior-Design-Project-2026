---
phase: 04-supabase-store-writer
plan: 06
subsystem: database
tags: [supabase, github-actions, smoke-test, backfill, parity, evidence]

requires:
  - phase: 04-supabase-store-writer
    provides: "04-03: loader, smoke test, dispatch-only workflow; 04-05: live schema, dlr_writer credential, smoke_local.json"
  - phase: 03-real-data-validation
    provides: "the backfill archive and its manifest (sha256, row counts, model hashes, git head 175b32b)"
provides:
  - "GitHub secret SUPABASE_DB_URL (the only database secret on GitHub)"
  - "Phase 3 backfill in public.city_rating: 4 x 504 rows, newest 2026-09-28T23:00:00Z, labelled provisional, Phase 3 identity"
  - "docs/data-science/decisions/supabase_store/{smoke_local,smoke_actions,backfill_parity,smoke_after_backfill}.json"
affects: [05 scheduled runs (05-06 go-live needs the Actions smoke recorded here), 06 read view, 07 per-city conductors]

actuals:
  tasks: 3
  commits: 1
plan_head_before: 74946e6
plan_head_after: 0b0fa08

key-files:
  created:
    - docs/data-science/decisions/supabase_store/smoke_local.json
    - docs/data-science/decisions/supabase_store/smoke_actions.json
    - docs/data-science/decisions/supabase_store/backfill_parity.json
    - docs/data-science/decisions/supabase_store/smoke_after_backfill.json
  modified: []

key-decisions:
  - "Backfill loaded despite Phase 3's NO-GO, per the owner's 2026-10-21 re-sequencing; every row stays provisional until Phase 7's go (REVAL-01)"

requirements-completed: [DB-03, DB-04, DB-06]
---

# 04-06 Summary: live evidence on the real project

A GitHub-hosted runner reached the live database with only the repository secret (SC4), the Phase 3 backfill is in Postgres with per-city parity and the Phase 3 configuration and model identity (SC3, SC6), the writer sees the rows, and the four evidence files are committed.

## Task outcomes

1. **Secret, push, Actions smoke (owner).** Runner-wheel precondition passed before the checkpoint (`psycopg-3.3.6-py3-none-any.whl`, `psycopg_binary-3.3.6-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl`). Owner set `SUPABASE_DB_URL`, pushed `main` (8 commits, `origin/main` = `74946e6`) and dispatched "Supabase Smoke". Run `40010766903`: `success`, `workflow_dispatch`, head `74946e6`, created 2026-10-23T19:21:27Z. Read-only checks: secret list is `NREL_API_EMAIL`, `NREL_API_KEY`, `SUPABASE_DB_URL`, `SYNOPTIC_TOKEN` (no `SUPABASE_ADMIN*`); the log has "SMOKE OK", every check `ok`, the secret only as `***`, and none of `postgresql://`, `postgres://`, `pooler.supabase.com`, `supabase.co`, `SUPABASE_ADMIN`. The log was written to a temp file outside the repository and deleted.
2. **Backfill load (owner).** Loader output:
   ```
   Phase 3 identity: code 175b32b, config_version v1-provisional-2026-10-13, forecast_method ml
   city             manifest    csv  dups     db  inserted  skipped  match
   AUSTIN                504    504     0    504       504        0  yes
   CORPUS_CHRISTI        504    504     0    504       504        0  yes
   MIDLAND               504    504     0    504       504        0  yes
   EL_PASO               504    504     0    504       504        0  yes
   rows read: 2016, dropped by validation: 0
   parity: every city matches
   ```
   Smoke with `--expect-rows`: 12 checks ok plus `rows_visible`; each city 504 rows, newest 2026-09-28T23:00:00Z; "SMOKE OK".
3. **Verify and commit (executor).** The plan's verify command printed `EVIDENCE_OK` (parity, archive sha256 equal to the manifest, per-city rows equal to `archive_rows_by_city`, identity commit and `config_version`, model hashes equal to the manifest, both owner smoke reports, Actions report, no connection details in any file). The four config fingerprints in `backfill_parity.json` equal 04-03's precomputed table exactly. Secret scan and schema-doc tests: 10 passed with the files staged. Commit `0b0fa08`, not pushed.

## Task Commits

1. **Task 3: live evidence** - `0b0fa08` (docs)

## Deviations from Plan

- The plan expected the push to also carry the two psycopg pins in `requirements.txt`. They have been on `origin/main` since 04-01 (`a036c0d`), so the push carried only the new dispatch-only workflow plus docs and tests. Shadow Collection had already been installing psycopg; its last three runs before the push succeeded.
- `smoke_actions.json` was written when the owner reported the run finished (before Task 2) rather than inside Task 3; content and checks are as the plan specifies.
- The dry run in Task 2 step 1 was not pasted; the owner reported the load directly. The load's own manifest and identity checks passed (it refuses on an archive or identity mismatch before inserting).
- No executor subagent was spawned: Tasks 1 and 2 are owner checkpoints and Task 3 is a short verification the orchestrator ran directly.

## Discrepancies

None beyond the deviations above.

## Issues Encountered

None.

## User Setup Required

- Re-run the local smoke test after 2026-10-30 and keep the newer `smoke_local.json` (from 04-05).
- Glance at the next scheduled Shadow Collection run to confirm it still succeeds after the push.

## Known Stubs

None.

## Threat Flags

None. Only `SUPABASE_DB_URL` (the writer) is on GitHub; the admin URL stays in `.env`.

## Next Phase Readiness

- Phase 5's go-live plan (05-06) can cite run `40010766903` as the successful database smoke test from a GitHub-hosted runner.
- The live table holds the provisional backfill; the forecast and detector cold-start from live hours after go-live (backfill ends 2026-09-28, read window 30 days).

## Self-Check: PASSED

- FOUND (tracked): the four evidence files under docs/data-science/decisions/supabase_store/
- FOUND commit: 0b0fa08 (in `origin/main..HEAD`, not pushed)
- `EVIDENCE_OK`; secret scan and schema-doc tests 10 passed
- `gh secret list` has SUPABASE_DB_URL and no SUPABASE_ADMIN
