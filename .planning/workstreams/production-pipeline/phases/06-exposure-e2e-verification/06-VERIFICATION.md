---
phase: 06-exposure-e2e-verification
verified: 2026-11-02T03:33:00Z
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
covered_digest: "v3:sha256:eb7ec780ed58e5528dfbb2faa3191c7bc65ea661412f2d525841a8fb30419923"
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
**Verified:** 2026-11-02
**Status:** passed (5 open round-2 review items, all advisory, none undermining a must-have; see "Review items")
**Re-verification:** Yes. This regenerates the 2026-11-01 report, which was made stale by six code-review fix commits (d5bddba, 99674cd, 29aa85c, e8ab256, f65062c, efe3fbd). The previous status was `passed` with no `gaps:`, so every truth was re-checked against the post-fix tree. Nothing regressed.

## Method and evidence limits

I did not contact the live project, did not read `.env`, did not push and did not commit. Evidence is: (a) the code, migrations, docs and tests in the repository after the six fix commits (I read the combined diff `d5bddba^..efe3fbd` for the covered files); (b) tests I ran from the repo root; (c) the committed redacted owner-run JSON (`06-09/12/13-live-checks.json`, `06-13-smoke.json`, `06-e2e-trace.json`) and the committed raw soak export (`soak-data/final/`), which I re-ran the report over myself; (d) the new committed evidence `06-UAT.md`, `06-SECURITY.md`, `06-REVIEW-FIX.md`, `06-REVIEW.md` (round 2) and `06-REVIEW-DISPOSITION.md`.

The live steps remain owner-run and relayed. The raw output of `verify_exposure.sql` (now 18 of 18) and `verify_monitoring.sql` (7 of 7) on 2026-11-01 and the live trace on 2026-11-02 (run 41381103142) are recorded as evidence text in `06-UAT.md`, not as committed output files. That is still the weakest link in the chain, and unchanged from the first report.

## What the fix commits touched, and the re-check

| Commit | Files | Re-check result |
|--------|-------|-----------------|
| d5bddba WR-01 | `verify_exposure.sql` (new CTE `public_role_privileges`, new check `anon_authenticated_hold_no_write_or_column_privilege_in_public`), `expose_migration_test.py` | Read the SQL: still one read-only SELECT; 18 `union all` branches' worth of checks. The new check uses `has_table_privilege` / `has_any_column_privilege`, so column-level and inherited privileges are now visible. Local-Postgres tests (47 passed) plant column-level and inherited grants and see exactly the new check go false. Live: 18 of 18 ok on 2026-11-01 (UAT 3). Strengthens truth 5. |
| 99674cd WR-02 | `e2e_verify_readonly.py`, `e2e_readonly_test.py` | Hidden-table checks now need a named cause (401/403 with 42501, or 404/406 with PGRST205/106/202), preceded by a `key_sanity` read. View-write 5xx pass only with 55000/42501. Live: `--check-read --check-hidden --check-writes` ok on 2026-11-01 (UAT 2). Residual weakness: round-2 WR-02 (any 4xx on a view write still passes). |
| 29aa85c WR-03 | `supabase_store.py` (`redact(str(a))` on stored alerts), `supabase_store_test.py`, `rest-api.md`, `city_rating_v1.md` | I executed `redact()` on a G6-style alert: credentials and URLs are removed, text is capped at 300, but a file path inside a detector exception survives. The published doc no longer claims "no error text" and now tells consumers to treat `alerts` as diagnostic text, so the contradiction I flagged last time (doc false vs code) is closed. A residual information-disclosure exposure of short exception text on a public column remains by owner decision OD-6 and is documented. Round-2 WR-01 (below) confirmed. |
| e8ab256 WR-04 | `e2e_trace.py`, `e2e_soak_report.py`, `supabase_store.py` (`begin_read_only`), tests | Trace and export now run reads in one read-only transaction (psycopg 3.3.6 `read_only` property on a non-autocommit connection) and roll back afterwards. Live trace passed on 2026-11-02 after this change (UAT 4). Residual: round-2 IN-01 (no committed real-Postgres proof the guard bites). |
| f65062c WR-05 | `e2e_soak_report.py`, `e2e_soak_report_test.py`, runbook | A "late run" cause no longer excuses a breach (`_needs_annotation`). I re-ran `report --mode soak --min-hours 72` over the committed `soak-data/final/` with the fixed code: exit 0, verdict `pass`, `breaches: []`, and `report.json` byte-identical to the committed file. |
| efe3fbd WR-06 | `supabase_rest.py`, `e2e_readonly_test.py` | Plain `http://` accepted only for loopback; `_SameHostRedirects` stops `apikey` following a cross-host redirect. Live key checks unaffected (UAT 2). Residual: round-2 IN-03 (opener built at import, ignores a `.env` proxy). |

Neither applied migration changed: sha256 `7e2d5f01...ea0cb` (expose) and `246da223...8552` (soak log) match the pins; `git diff dd9fa40..HEAD` over `supabase/migrations`, `docs/integration/examples` and `backend/latest_rating_contract.py` is empty. The code that ran live for the examples is therefore still the code on disk.

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /rest/v1/latest_rating` with the anon key returns exactly four rows (one per city) with units documented | VERIFIED | Migration creates `public.latest_rating` as `distinct on (city)` with 34 columns (31 stored, 3 computed), each with a unit-first column comment; `rest-api.md` has the column/type/unit table (the fix commits only changed one bullet in the visibility section, and `rest_api_doc_test.py` passes). Live (committed JSON): HTTP 200, 4 rows, 34 columns in the published order, `count=exact` 4, keyless request 401, in 06-09, 06-12 and 06-13. Post-fix: `verify_exposure.sql` 18 of 18 on 2026-11-01 and the live read-only check on 2026-11-02 includes a 200 `latest_rating` key-sanity read. 47 Postgres-backed tests pass. |
| 2 | The curl, supabase-js and stdlib-urllib examples run as written and return data | VERIFIED | Examples unchanged since they ran live (06-11: curl exit 0; Python 3.9.6, 3.12.13, and PSS/E 3.14.0 exit 0; supabase-js 2.117.3 exit 0). Diff over `docs/integration/examples` is empty. `example_read_ratings_test.py` passes in my run. The urllib example does not use `supabase_rest.py`, so WR-06 does not touch it. Relayed live evidence, not reproduced by me. |
| 3 | A trace cron-job.org trigger -> Actions run -> database rows -> REST response matches values for all four cities | VERIFIED | `06-e2e-trace.json` (2026-10-27 run 40447756754): `ok: true`, 8 of 8 links, four cities `match: true`, `mismatches: []`; corroborated by `soak-data/final/writes.csv`. New since the first report: the post-fix trace tool (read-only transaction) was run live on the 2026-11-02T03:05:00Z execution (HTTP 204), run 41381103142, `E2E TRACE OK`, 8 of 8 links, four cities match and current (UAT 4). `e2e_trace_test.py` passes. |
| 4 | A 72 h soak shows every city's latest `valid_time` within cadence plus grace (OD-4) at every probe; breaches listed with causes | VERIFIED | I re-ran `e2e_soak_report.py report --mode soak --min-hours 72` over the committed `soak-data/final/` with the post-WR-05 code: exit 0, verdict pass, no breach, 864 of 864 probes, `report.json` byte-identical to the committed one. My earlier independent re-analysis of `probes.csv` stands (864 distinct probe times x 4 cities, max age 70.0 min, 0 probes above 90 min, largest spacing 5.005 min). WR-05's fix changes how a late run is judged but there were no breaches, so the verdict could not change and does not. |
| 5 | Insert, update and delete attempts with the anon key are all rejected | VERIFIED | Live, behavioral, three times in committed JSON (06-09, 06-12, 06-13): table POST/upsert/PATCH/DELETE `401 / 42501`, same verbs on the view `500 / 55000`, snapshot before equals after (sha256 identical). Plus `06-13-smoke.json` (14 of 14, `consumers_cannot_write: true`). New since the first report: the strengthened checker passed live on 2026-11-01/02 (UAT 2, seven write attempts refused as in 06-13), and the strengthened `verify_exposure.sql` (column-level and inherited privilege check) is 18 of 18 on the live database (UAT 3), which closes the blind spot I flagged as WR-01. Structural lock unchanged: `revoke all` then SELECT-only grants on two objects, no write policy. |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified)

Behavior-dependent truths (4 and 5) are backed by behavioral evidence (probe-by-probe ages; live write attempts with before/after snapshot), not by symbol presence.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261026195124_expose_latest_rating.sql` | view (34 cols, `security_invoker`), index, `assert_fresh`, revokes, read policy | VERIFIED | Unchanged; sha256 pin matches. |
| `supabase/migrations/20261026204258_soak_freshness_log.sql` | `ops.freshness_log`, `ops.log_freshness()` | VERIFIED | Unchanged; sha256 pin matches. |
| `backend/latest_rating_contract.py` | Python twin of the 34 columns | VERIFIED | Unchanged; drift test passes. |
| `backend/supabase_rest.py`, `e2e_verify_readonly.py`, `e2e_trace.py`, `e2e_soak_report.py`, `supabase_store.py` | live-check, trace, soak and store tooling | VERIFIED | Substantive; fix changes read in full diff; all offline tests pass; exercised live after the fixes (UAT 2, 4). |
| `docs/integration/rest-api.md` + 3 examples | consumer contract and runnable examples | VERIFIED | Drift guard passes; the one changed sentence is now accurate about `alerts`. |
| `supabase/ops/verify_exposure.sql` (18 checks), `verify_monitoring.sql` (7) | owner permission checks | VERIFIED | Run by local tests and live (18 of 18, 7 of 7); sequences not covered by the new check (round-2 IN-02). |
| Committed evidence JSON and `soak-data/` | redacted evidence | VERIFIED | Present, parseable, unchanged; secret scan passes (below). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `latest_rating` view | `city_rating` RLS read policy | `security_invoker = true` | WIRED | Migration unchanged. |
| anon role | write protection | `revoke all` + SELECT-only grants + no write policy | WIRED | Live 42501; now also checked at the column and inheritance level by the 18th check. |
| `ops.log_freshness()` | `latest_rating.is_stale` | pg_cron every 5 min | WIRED | 864 probes, no gap above 5.005 min. |
| cron-job.org | `dlr_live.yml` | `workflow_dispatch` | WIRED | Trace plus 72 of 72 slots; second trace on 2026-11-02. |
| Actions run | `city_rating` rows | `run_id` | WIRED | `writes.csv` and both traces. |
| `city_rating` | REST response | PostgREST | WIRED | SQL equals REST for four cities, both traces. |
| `build_rating_row` | public `alerts` column | `redact(str(a))` | WIRED | New in 29aa85c; redaction confirmed by direct execution, cap is lossy (round-2 WR-01). |
| trace / soak export | read-only database transaction | `supabase_store.begin_read_only` | WIRED | Both call it before the first query and `rollback()` after; works live. Not proven by a real-Postgres test (round-2 IN-01). |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| `latest_rating` | all 34 columns | `public.city_rating` (hourly writer upserts) | Yes: SQL-to-REST equality for 4 cities in both traces; rows advance hourly | FLOWING |
| Examples | rows printed | REST `latest_rating` / `city_rating` | Yes: live output | FLOWING |
| `alerts` column | stored alert text | `DLRSafetyMonitor` via `redact` | Yes, redacted and capped | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 6 suites incl. Postgres-backed (view, grants, RLS, labels, soak log, readonly, trace, soak, store, doc drift, secret scan) | `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/{expose_migration,soak_log_migration,e2e_readonly,e2e_soak_report,e2e_trace,supabase_store,secret_scan,rest_api_doc}_test.py` (repo root) | 254 passed, 1 skipped (owner-local exact-value secret scan) | PASS |
| Postgres-only proofs | `expose_migration_test.py soak_log_migration_test.py` with autostart | 47 passed | PASS |
| Adjacent suites | `example_read_ratings, monitoring_runbook, dlr_live_runbook, supabase_schema_doc, supabase_smoke, supabase_migration, dlr_live_workflow, dlr_live_window_check` | 80 passed | PASS |
| Soak verdict with post-fix code | `e2e_soak_report.py report --mode soak --min-hours 72 --in-dir soak-data/final` | exit 0, verdict pass, `breaches: []`, `report.json` byte-identical | PASS |
| Migration pins | `shasum -a 256` of both migrations | match test constants | PASS |
| Alert redaction | `supabase_store.redact()` on a crafted G6 alert | secrets removed, capped at 300, suffix cut, file path survives | confirms round-2 WR-01 and the residual noted above |
| Full suite | n/a | not re-run by me this round (caller-supplied 1932 passed on 2026-11-01, before the fix commits) | not re-verified |

### Probe Execution

Step 7c: SKIPPED. No `probe-*.sh` files are declared or exist for this phase.

### Requirements Coverage

All five IDs (API-01, API-02, E2E-01, E2E-02, E2E-03) appear in plan frontmatter, and `REQUIREMENTS.md` maps no other ID to Phase 6, so there are no orphans.

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| API-01 | 06-01, 06-04, 06-06, 06-09, 06-13 | Consumer tables/views exposed read-only to anon under RLS; `latest_rating` one row per city | SATISFIED | Truths 1 and 5. |
| API-02 | 06-02, 06-06, 06-11 | Documented curl, supabase-js and stdlib urllib examples work as written | SATISFIED | Truth 2. |
| E2E-01 | 06-08, 06-11 | cron-job.org -> workflow -> rows -> REST, four cities match | SATISFIED | Truth 3 (two live traces). |
| E2E-02 | 06-03, 06-05, 06-07, 06-10, 06-12 | 72 h soak, freshness within 90 min, breaches explained | SATISFIED | Truth 4. |
| E2E-03 | 06-04, 06-07, 06-09, 06-12, 06-13 | anon insert/update/delete rejected | SATISFIED | Truth 5. |

Bookkeeping: the first report flagged `REQUIREMENTS.md` E2E-03 and the ROADMAP Phase 6 line as still unticked. Both are now ticked (`[x]` API-01..E2E-03, traceability table "Complete", ROADMAP "completed 2026-11-01"). No bookkeeping gap remains.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (phase code, docs, SQL, ops files) | n/a | `TBD`/`FIXME`/`XXX` grep over `backend/e2e_*.py`, `supabase_rest.py`, `docs/integration`, `supabase/ops` | none | No debt markers. |
| `backend/e2e_verify_readonly.py` | 426-428 | any 4xx on a view write counts as refused | Warning (round-2 WR-02) | Weakens only the view-write half of the proof; live answer is the specific 500/55000 and the table writes are strict 42501. |
| `backend/supabase_store.py` | 563-566 | `redact()` 300-char cap cuts the `— fallback rating N A` suffix on a long G6 alert | Warning (round-2 WR-01) | Lossy but safe: head of the alert survives, `fallback_gates` is derived from the head, the rating is a separate column. |

No stubs, hardcoded-empty data paths or console-only handlers in the deliverables.

### Prohibitions (must-NOT checks)

All 13 plans declare judgment-tier prohibitions, each `status: resolved` in the plan. Verdicts below are NON-AUTHORITATIVE LLM judgments; none is unresolved, so none is flagged `unverified-prohibition`.

| Prohibition (condensed) | Judgment | Basis |
|---|---|---|
| No INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER for anon or authenticated, not relying on RLS alone | Held, now stronger | Revoke-then-SELECT-only; live 42501; the new 18th check covers column-level and inherited privileges (live 18 of 18). |
| Nothing but `city_rating` and `latest_rating` readable; run log and `ops` unreachable | Held | Live hidden checks now require a named refusal cause after a key-sanity read; SQL check `pipeline_run_not_readable_by_anon`. |
| `is_provisional` never false on a provisional label; view and `assert_fresh` not owner-rights | Held | Migration unchanged and pinned. |
| No URL, ref or key committed; no `.env` read by tests; no `package.json` or `node_modules` | Held | `secret_scan_test` passes (exact-value test is owner-local; UAT 1 records the owner ran it unskipped, relayed); no `package.json`/`node_modules`. |
| Never bearer-token advice; no 2xx write counted as rejected without snapshot | Held | `apikey` header only; snapshot unchanged in all three runs and the 2026-11-02 check. |
| Do not relabel breaches, shorten window or excuse by deploy; no annotation written for owner | Held, now stronger | Zero breaches; WR-05 fix stops "late run" from excusing a breach; no `annotations.json`. |
| Executor must not contact live project in 06-09; 06-13 any difference is a discrepancy | Held (relayed) | Unchanged. The post-fix live checks in UAT 3 and 4 were run by the orchestrator at the owner's explicit request with a read-only runner; no state changed. |

### Review items (effect on the must-haves, judgment, nothing changed by me)

Round 1 produced 6 warnings, all now fixed in the six commits above (see the table at the top; I read each diff, ran the tests, and the live UAT checks exercised WR-01, WR-02, WR-04 and WR-06 after the fix). Round 2 (`06-REVIEW.md`, review of the fix commits) reports 0 critical, 2 warnings, 3 info, all open and advisory in `06-REVIEW-DISPOSITION.md`. I confirmed the substance of both warnings in the code:

- **Round-2 WR-01 (300-char cap drops the fallback suffix): confirmed by execution.** Safe and lossy, not a goal failure. No success criterion depends on the alert tail. Recommend the suffix-preserving shortening the review proposes when convenient.
- **Round-2 WR-02 (any 4xx on a view write passes): confirmed by reading `_classify_view_write`.** The `snapshot_unchanged` backstop does not catch a writable view (writes target the old row), so this is a real weakness in one of the proofs. It does not change truth 5, which rests on the live 500/55000 answer, the structural grants, and the strict table-write checks. Fix before reusing the tool as a regression gate.
- **Round-2 IN-01 to IN-03** (`begin_read_only` unconfirmed, sequences skipped by the new SQL check, renamed-table false pass and import-time proxy opener): none affects a truth; the SQL checks and live runs cover the same ground today.
- **Carried round-1 info items** (IN-01 to IN-06 in the original numbering, including stale sentences in `api-contract.md`) remain open and cosmetic.
- **Security:** `06-SECURITY.md` reports 48 of 48 threats closed, `threats_open: 0`. I did not re-audit each threat; I spot-checked the grants, redirect and key-handling mitigations against the code and found them as described.

Observation from UAT 4 (not a phase-6 criterion): around the 2026-11-01 DST change the owner saw two workflow_dispatch runs at 09:05Z and none at 08:05Z; whether the 08:00Z slot was written is unchecked. It falls after the 72 h soak window (2026-10-27T03:35Z to 2026-10-30T03:35Z), so it does not affect truth 4, but it is worth one owner look at the alarm history.

### Human Verification Required

None required to close Phase 6. The relayed live facts (examples, SQL runner output 18 of 18 and 7 of 7, 2026-11-02 trace, cron-job.org times) are recorded in `06-UAT.md` (73 of 73 pass, 0 issues) and corroborated by the committed evidence and my own re-runs; I found no inconsistency.

### Gaps Summary

No gaps. All five ROADMAP success criteria remain verified after the six fix commits, all five requirement IDs are accounted for and satisfied, no orphans, no debt markers, no stubs, bookkeeping is complete. Open items are advisory only: two round-2 warnings (alert suffix truncation; weak view-write 4xx classifier), three round-2 info items, and the carried round-1 info items.

---

_Verified: 2026-11-02_
_Verifier: Claude (gsd-verifier)_
