---
phase: 04-supabase-store-writer
plan: 04
subsystem: docs
tags: [supabase, schema-contract, consumer-docs, pss-e, provenance]

requires:
  - phase: 04-supabase-store-writer
    provides: "04-01: the city_rating / pipeline_run migration and config labels; 04-02: the writer path; 04-03: the backfill loader and its provisional labels"
provides:
  - "docs/data-science/schema/city_rating_v1.md: v1 consumer contract for public.city_rating (columns, key and time rules, fallback, provisional label, DB-06 row identity, freshness, backfill, reading rules)"
  - "backend/tests/supabase_schema_doc_test.py: 7 tests keeping the doc in step with the migration, config labels, the no-connection-details rule and the two consumer docs"
  - "api-contract.md and pss_e_handoff.md point at the contract; their storage open items are closed"
affects: [04-05 owner schema approval, 06 read view and REST access, 07 per-city conductors]

actuals:
  tasks: 2
  commits: 2
plan_head_before: d7f680a7e34aa5a6590eee58982e4b22bebfe01e
plan_head_after: accefb0

key-files:
  created:
    - docs/data-science/schema/city_rating_v1.md
    - backend/tests/supabase_schema_doc_test.py
  modified:
    - docs/frontend/specs/api-contract.md
    - docs/data-science/decisions/pss_e_handoff.md

key-decisions:
  - "Open decision 2 in api-contract.md is resolved by the store: each run writes every city to public.city_rating and consumers read it through Supabase REST from Phase 6, so no in-process call or file exporter is needed"
  - "Open decision 10 is resolved for the per-city archive part only; the shadow v3 part is left open as it was"
  - "pss_e_handoff.md now separates what the production store fixes (format/transport, cadence, fields, granularity, provenance) from what stays open with Power Systems (which fields PSS/E consumes, per-city conductor values, the provisional caveat)"

requirements-completed: [DB-05, DB-06]
---

# 04-04 Summary: city_rating v1 consumer contract

The consumer schema contract for `public.city_rating` is published under `docs/`, a test keeps it in step with the migration and config, and the two consumer-facing docs (`api-contract.md`, `pss_e_handoff.md`) now point at it instead of listing storage and handoff as undefined.

## Accomplishments

- `city_rating_v1.md`: 12-section contract covering every column of `city_rating` and `pipeline_run` in migration order, the `(city, valid_time)` key and time rules, fallback behaviour, the provisional label (until REVAL-01), the DB-06 identity columns and how a change in them marks a configuration or model change, freshness (hourly, 90 minutes once Phase 5 runs), backfill and reading rules. It names no host, project reference, key or URL.
- `api-contract.md`: `public.city_rating` row in the data-sources table; the CSV archive is described as the offline store; the `/api/cities/{city}/history` row points at the contract; open decisions 2 and 10 (archive part) are marked resolved with the link.
- `pss_e_handoff.md`: link under the status paragraph; "What's still undefined" replaced by "What the production store fixes (2026-10)" and "Still open with Power Systems".
- Full suite: 1505 passed, 43 skipped, 0 failed.

## Task Commits

1. **Task 1: consumer schema contract and its test** - `f1b8c95` (docs)
2. **Task 2: point api-contract.md and pss_e_handoff.md at the contract** - `accefb0` (docs)

## Deviations from Plan

None in content. The plan was not run end to end by one executor (see Issues Encountered).

## Discrepancies

- Task 1's commit carries `Co-Authored-By: Claude Sonnet 5.5`; the plan asks for Opus 5.5. Task 2's commit carries Opus 5.5.
- `gsd check evaluation-scope --plan 04-04` also returns commits from another workstream's plan 04-04 (Conservative-Rating analysis) because it matches on the subject prefix; only `f1b8c95` and `accefb0` belong to this plan.

## Issues Encountered

- The original run stopped after committing Task 1. Task 2's edits were left complete but uncommitted in the working tree, with no SUMMARY. On `/gsd-execute-phase 4` the safe-resume gate stopped dispatch; the owner chose "close out manually". The uncommitted edits were checked against Task 2's behaviour and acceptance criteria (below), committed with the plan's message and explicit paths, and the full suite was run before this SUMMARY was written.

## User Setup Required

None for this plan. Approving the contract before it reaches the shared project is 04-05 Task 2.

## Known Stubs

None.

## Threat Flags

None. T-04-18 (drift), T-04-19 (connection details) and T-04-28 (provisional rows read as validated) are covered by the tests named in the plan.

## Next Phase Readiness

- Ready for 04-05: the owner can review `docs/data-science/schema/city_rating_v1.md` at its schema-approval checkpoint.
- Nothing was pushed.

## Self-Check: PASSED

- FOUND: docs/data-science/schema/city_rating_v1.md, backend/tests/supabase_schema_doc_test.py
- FOUND commits: f1b8c95, accefb0 (ancestors of HEAD)
- `supabase_schema_doc_test.py`: 7 passed; `grep -c "^def test_"` prints 7
- `grep -c city_rating_v1.md`: api-contract.md 5 (needs ≥3), pss_e_handoff.md 2 (needs ≥1)
- Both `## What the production store fixes (2026-10)` and `## Still open with Power Systems` present; the fixes section names `config_fingerprint`
- Task 2 commit diff stat on the two docs: "2 files changed"
- Full suite: 1505 passed, 43 skipped, 0 failed
