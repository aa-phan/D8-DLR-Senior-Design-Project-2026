---
phase: 06-exposure-e2e-verification
verified: 2026-11-01T22:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files:
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-01-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-01-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-02-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-02-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-03-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-03-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-04-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-04-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-05-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-05-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-06-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-06-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-07-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-07-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-08-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-08-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-09-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-09-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-10-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-10-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-11-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-11-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-12-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-12-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-13-PLAN.md
  - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-13-SUMMARY.md
  - backend/e2e_soak_report.py
  - backend/e2e_trace.py
  - backend/e2e_verify_readonly.py
  - backend/latest_rating_contract.py
  - backend/supabase_rest.py
  - backend/supabase_store.py
  - docs/integration/examples/curl.sh
  - docs/integration/examples/read_ratings.py
  - docs/integration/examples/supabase_js.mjs
  - docs/integration/rest-api.md
  - supabase/migrations/20261026195124_expose_latest_rating.sql
  - supabase/migrations/20261026204258_soak_freshness_log.sql
  - supabase/ops/verify_exposure.sql
  - supabase/ops/verify_monitoring.sql
covered_digest: "v3:sha256:6d7fc1f9e50ee34340803f8c9308c81fa4c6ae4b88360c496ab7df7073c4ae85"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  gaps_closed: []
  gaps_remaining: []
  regressions: []
---

# Phase 6: Exposure & E2E Verification - Verification Report

**Phase Goal:** Consumers can read current ratings for every city at any time through a documented, read-only REST interface.
**Verified:** 2026-11-01
**Status:** passed (4 open round-3 review items and the earlier open advisory items; none undermines a must-have, see "Review items")
**Re-verification:** Yes. This regenerates the report committed at ac86651, which went stale when three commits changed covered files: efca90c (WR-02, `_classify_view_write` needs a named cause), 6d2dafc (WR-01, `_safe_alert` keeps the fallback-rating suffix) and 4e9b2d0 (docstring only). The previous status was `passed` with no `gaps:`. Every truth was re-checked against the current tree and the three commits' diff (`git diff ac86651..HEAD -- backend/`, four files, +102/-14). Nothing regressed.

## Method and evidence limits

I did not contact the live project, did not read `.env`, did not push and did not commit. Evidence is: (a) the three commits' full diff, which I read; (b) tests and direct function calls I ran from the repo root; (c) the committed redacted owner-run JSON (`06-09/12/13-live-checks.json`, `06-13-smoke.json`, `06-e2e-trace.json`), the committed raw soak export and `06-UAT.md`, `06-SECURITY.md`, `06-REVIEW.md` (round 3), `06-REVIEW-DISPOSITION.md`.

The live steps remain owner-run and relayed: raw `verify_exposure.sql` (18 of 18), `verify_monitoring.sql` (7 of 7) and the 2026-11-02 trace are recorded as evidence text in `06-UAT.md`, not as output files. This is unchanged since the last report and remains the weakest link. The three commits since the last report touch only the offline checker and the alert text writer; no live step needs repeating for them, because the committed live answers are replayed by a test (below).

## What the three commits touched, and the re-check

| Commit | Files | Re-check result |
|--------|-------|-----------------|
| efca90c, 4e9b2d0 WR-02 | `e2e_verify_readonly.py`, `e2e_readonly_test.py` | `_classify_view_write` now passes a view write only on a named cause: `55000` on any status of 400 or above (live: HTTP 500), `42501` on 401/403/5xx, `PGRST117`/`42809` on a 4xx. Any 2xx fails as "write accepted"; a bare 401/403, 400, 404, 408/429 or uncoded 5xx is "inconclusive" (not ok). I called the function directly: 500/55000 passes; 201 fails; bare 401 "Invalid API key" and 400/PGRST102 are inconclusive. Strictly tighter than the old "any 4xx passes", which closes round-2 WR-02. |
| 6d2dafc WR-01 | `supabase_store.py`, `supabase_store_test.py` | `_safe_alert` redacts first without a cap, then shortens to 300 characters, cutting the middle and keeping the `- fallback rating N A` suffix. I ran it on a G6-style alert with a connection URL and `password=hunter2` near the cut: output is 300 characters, ends `... - fallback rating 1825 A`, no `hunter2`. A suffix-less 400-character alert is cut to exactly 300. `rest-api.md` still says "redacted and cut to 300 characters", which stays accurate; `git diff ac86651..HEAD` over docs, migrations, examples, `supabase_rest.py`, `e2e_trace.py` and `e2e_soak_report.py` is empty. Closes round-2 WR-01. |

Both migrations are unchanged: sha256 `7e2d5f01...ea0cb` (expose) and `246da223...8552` (soak log) match the pins. Examples, contract and SQL ops files are unchanged since they ran live.

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /rest/v1/latest_rating` with the anon key returns exactly four rows (one per city) with units documented | VERIFIED | Migration creates `public.latest_rating` as `distinct on (city)`, 34 columns with unit-first comments; `rest-api.md` carries the column/type/unit table (`rest_api_doc_test.py` passes). Live committed JSON (06-09, 06-12, 06-13): HTTP 200, 4 rows, 34 columns in the published order, keyless request 401. `verify_exposure.sql` 18 of 18 live (UAT 3). 47 Postgres-backed tests pass in my run. The new commits do not touch the view, the migration or the doc. |
| 2 | The curl, supabase-js and stdlib-urllib examples run as written and return data | VERIFIED | Examples unchanged since they ran live (06-11, relayed). `example_read_ratings_test.py` passes. The urllib example does not use `supabase_rest.py`. Relayed live evidence, not reproduced by me. |
| 3 | A trace cron-job.org trigger -> Actions run -> database rows -> REST response matches values for all four cities | VERIFIED | `06-e2e-trace.json` (run 40447756754): `ok: true`, 8 of 8 links, four cities `match: true`, `mismatches: []`; second post-fix trace live on 2026-11-02 (run 41381103142, UAT 4). `e2e_trace.py` unchanged by the three commits; `e2e_trace_test.py` passes. |
| 4 | A 72 h soak shows every city's latest `valid_time` within cadence plus grace (OD-4) at every probe; breaches listed with causes | VERIFIED | Committed `soak-data/final/` and `report.json` (864 of 864 probes, no breach, max age 70.0 min), previously re-run by me with the post-WR-05 code and byte-identical. `e2e_soak_report.py` unchanged by the three commits; `e2e_soak_report_test.py` passes. Behavior-dependent truth backed by probe-by-probe data, not symbol presence. |
| 5 | Insert, update and delete attempts with the anon key are all rejected | VERIFIED | Key check requested for this run. I read the three committed live-check JSONs: in each, `table_insert/upsert/patch/delete` answered `401` code `42501` and `view_insert/patch/delete` answered `500` code `55000`. The test `test_committed_live_view_answers_are_still_classified_as_refused` replays all three files through the new `_classify_view_write`; it ran (not skipped) in my run: 3 parametrized cases pass, and with `test_view_write_verdicts` 20 tests pass. Direct call confirms `(500, 55000)` returns ok. So the stricter rule still classifies the real live answers as refused. Snapshots before and after were identical in all three runs; `06-13-smoke.json` 14 of 14, `consumers_cannot_write: true`; structural lock (`revoke all`, SELECT-only grants on two objects, no write policy) unchanged, now also checked at column and inheritance level (18th SQL check, 18 of 18 live). |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261026195124_expose_latest_rating.sql` | view (34 cols, `security_invoker`), index, `assert_fresh`, revokes, read policy | VERIFIED | Unchanged; sha256 pin matches. |
| `supabase/migrations/20261026204258_soak_freshness_log.sql` | `ops.freshness_log`, `ops.log_freshness()` | VERIFIED | Unchanged; sha256 pin matches. |
| `backend/latest_rating_contract.py` | Python twin of the 34 columns | VERIFIED | Unchanged; drift test passes. |
| `backend/supabase_rest.py`, `e2e_verify_readonly.py`, `e2e_trace.py`, `e2e_soak_report.py`, `supabase_store.py` | live-check, trace, soak and store tooling | VERIFIED | Substantive; the two changed files read in full diff; offline suites pass. |
| `docs/integration/rest-api.md` + 3 examples | consumer contract and runnable examples | VERIFIED | Unchanged; drift guard passes; the 300-character statement is still true. |
| `supabase/ops/verify_exposure.sql` (18 checks), `verify_monitoring.sql` (7) | owner permission checks | VERIFIED | Unchanged; run live (18/18, 7/7). |
| Committed evidence JSON and `soak-data/` | redacted evidence | VERIFIED | Present, parseable, used by a passing replay test; secret scan passes. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `latest_rating` view | `city_rating` RLS read policy | `security_invoker = true` | WIRED | Migration unchanged. |
| anon role | write protection | `revoke all` + SELECT-only grants + no write policy | WIRED | Live 42501 on table, 55000 on view; replayed through the stricter classifier. |
| `ops.log_freshness()` | `latest_rating.is_stale` | pg_cron every 5 min | WIRED | 864 probes, no gap above 5.005 min. |
| cron-job.org | `dlr_live.yml` | `workflow_dispatch` | WIRED | Unchanged. |
| Actions run | `city_rating` rows | `run_id` | WIRED | `writes.csv` and both traces. |
| `city_rating` | REST response | PostgREST | WIRED | SQL equals REST for four cities, both traces. |
| `build_rating_row` | public `alerts` column | `_safe_alert` (redact, then cut, suffix kept) | WIRED | Call site at the alerts line in `build_rating_row` uses `_safe_alert`; `fallback_gates` still derived from the preserved head. |
| e2e checker | `_classify_view_write` | `write:view_*` attempts | WIRED | Stricter verdict function is the one the runner calls; tests cover it. |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| `latest_rating` | all 34 columns | `public.city_rating` (hourly writer upserts) | Yes: SQL-to-REST equality for 4 cities in both traces | FLOWING |
| Examples | rows printed | REST `latest_rating` / `city_rating` | Yes: live output | FLOWING |
| `alerts` column | stored alert text | `DLRSafetyMonitor` via `_safe_alert` | Yes, redacted, at most 300 characters, rating suffix kept | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 6 suites incl. Postgres-backed | `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/{expose_migration,soak_log_migration,e2e_readonly,e2e_soak_report,e2e_trace,supabase_store,secret_scan,rest_api_doc}_test.py` (repo root) | 268 passed, 1 skipped (owner-local exact-value secret scan) | PASS |
| View-write classifier and live-answer replay | `pytest -q -p no:cacheprovider backend/tests/e2e_readonly_test.py -k "committed_live or view_write_verdicts" -rs` | 20 passed, none skipped | PASS |
| `_classify_view_write` direct | called with 500/55000, 403/42501 (RLS message), 401 bare, 400/PGRST102, 201 | ok, ok, inconclusive, inconclusive, "write accepted" | PASS (confirms round-3 WR-01, see below) |
| `_safe_alert` direct | G6 alert with URL and password near the cut, plus 400-char suffix-less alert | 300 chars with suffix kept and no secret; 300 chars | PASS |
| Migration pins | `shasum -a 256` of both migrations | match pins | PASS |
| Full backend suite (caller-supplied, repo root, `DLR_TEST_PG_AUTOSTART=1`) | n/a | 2046 passed, 0 failed | PASS (relayed by orchestrator, not re-run by me) |

### Probe Execution

Step 7c: SKIPPED. No `probe-*.sh` files are declared or exist for this phase.

### Requirements Coverage

Every ID in the phase's plan `requirements:` frontmatter (API-01, API-02, E2E-01, E2E-02, E2E-03) is defined in `REQUIREMENTS.md` (lines 120-130, all `[x]`) and in the traceability table (lines 225-229, all "Phase 6 / Complete"). `REQUIREMENTS.md` maps no other ID to Phase 6, so there are no orphans.

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| API-01 | 06-01, 06-04, 06-06, 06-09, 06-13 | Consumer tables/views exposed read-only to anon under RLS; `latest_rating` one row per city | SATISFIED | Truths 1 and 5. |
| API-02 | 06-02, 06-06, 06-11 | Documented curl, supabase-js and stdlib urllib examples work as written | SATISFIED | Truth 2. |
| E2E-01 | 06-08, 06-11 | cron-job.org -> workflow -> rows -> REST, four cities match | SATISFIED | Truth 3. |
| E2E-02 | 06-03, 06-05, 06-07, 06-10, 06-12 | 72 h soak, freshness within 90 min, breaches explained | SATISFIED | Truth 4. |
| E2E-03 | 06-04, 06-07, 06-09, 06-12, 06-13 | anon insert/update/delete rejected | SATISFIED | Truth 5. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (phase code, docs, SQL, ops files) | n/a | `TBD`/`FIXME`/`XXX` grep over `backend/e2e_*.py`, `supabase_rest.py`, `supabase_store.py`, `docs/integration`, `supabase/ops` | none | No debt markers. |
| `backend/e2e_verify_readonly.py` | ~439-441 | `42501` on 401/403/5xx passes without checking the message (round-3 WR-01) | Warning (advisory) | An RLS-only 42501 ("new row violates row-level security policy") on a view write would be recorded as refused, unlike the table classifier. I confirmed by direct call (403/42501 with that message returns ok). The live answer is 500/55000, so no current verdict is affected, and the SQL privilege check (18 of 18) plus the strict table checks cover the grant. |
| `backend/tests/e2e_readonly_test.py` | ~600-626 | live-answer replay test skips if `.planning` evidence is absent (round-3 WR-02) | Warning (advisory) | The guard exists and ran for me; it would silently vanish on a PR branch without `.planning/`. Recommend a fixture under `backend/tests/`. |
| `backend/e2e_verify_readonly.py` | ~435 | `55000` accepted on code alone (round-3 IN-01) | Info | `snapshot_unchanged` is the backstop. |
| `backend/supabase_store.py` | ~314 | shortened alert can leave unbalanced parentheses (round-3 IN-02) | Info | Cosmetic. |

No stubs, hardcoded-empty data paths or console-only handlers in the deliverables.

### Prohibitions (must-NOT checks)

All 13 plans declare judgment-tier prohibitions, each `status: resolved`. Verdicts are NON-AUTHORITATIVE LLM judgments; none is unresolved, so none is flagged `unverified-prohibition`. No test-tier prohibitions were found.

| Prohibition (condensed) | Judgment | Basis |
|---|---|---|
| No INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER for anon or authenticated, not relying on RLS alone | Held | Revoke-then-SELECT-only; live 42501 and 55000; 18th SQL check covers column-level and inherited privileges. Round-3 WR-01 is a weakness in the offline checker only, not in the grants. |
| Nothing but `city_rating` and `latest_rating` readable; run log and `ops` unreachable | Held | Unchanged by the three commits. |
| `is_provisional` never false on a provisional label; view and `assert_fresh` not owner-rights | Held | Migration unchanged and pinned. |
| No URL, ref or key committed; no `.env` read by tests; no `package.json`/`node_modules` | Held | `secret_scan_test` passes; the new `_safe_alert` test builds its connection URL from pieces so it does not trip the scan. |
| Never bearer-token advice; no 2xx write counted as rejected without snapshot | Held | A 2xx still fails in the stricter classifier; the snapshot check is unchanged. |
| Do not relabel breaches, shorten window or excuse by deploy | Held | Zero breaches; soak code untouched by the three commits. |
| Executor must not contact live project in 06-09; any 06-13 difference is a discrepancy | Held (relayed) | Unchanged. I did not contact the live project either. |

### Review items (effect on the must-haves, judgment, nothing changed by me)

Round 2 (2 warnings, 3 info) is addressed for its two warnings: round-2 WR-01 is fixed by 6d2dafc and round-2 WR-02 by efca90c/4e9b2d0, both confirmed by my reading and execution above. Round 3 (`06-REVIEW.md` at 367beaf, review of those fixes) reports 0 critical, 2 warnings, 2 info, all open in `06-REVIEW-DISPOSITION.md`. I confirmed the substance of round-3 WR-01 by execution; WR-02 by reading the test. Neither changes a truth: truth 5 rests on the structural grants, the live 401/42501 and 500/55000 answers with unchanged snapshots, and the 18 of 18 SQL privilege check, and the stricter classifier still passes those answers. Round-2 IN-01 to IN-03 and the carried round-1 info items remain open and advisory. `06-SECURITY.md` reports 48 of 48 threats closed (not re-audited by me).

Recommended follow-ups, none blocking: make the view-write 42501 branch reject an RLS-only message; move the committed live answers into a `backend/tests/` fixture so the replay cannot skip; confirm the live 55000 message text before tightening the 55000 rule.

### Human Verification Required

None required to close Phase 6. The relayed live facts are recorded in `06-UAT.md` (73 of 73 pass) and corroborated by committed evidence and my re-runs; I found no inconsistency.

### Gaps Summary

No gaps. All five ROADMAP success criteria remain verified after efca90c, 6d2dafc and 4e9b2d0. All five requirement IDs are accounted for and satisfied, with no orphans, no debt markers and no stubs. Open items are advisory only.

---

_Verified: 2026-11-01_
_Verifier: Claude (gsd-verifier)_
