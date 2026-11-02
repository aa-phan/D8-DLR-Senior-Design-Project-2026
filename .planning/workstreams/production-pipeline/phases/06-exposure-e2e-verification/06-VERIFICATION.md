---
phase: 06-exposure-e2e-verification
verified: 2026-11-01T00:00:00Z
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
  - docs/integration/examples/curl.sh
  - docs/integration/examples/read_ratings.py
  - docs/integration/examples/supabase_js.mjs
  - docs/integration/rest-api.md
  - supabase/migrations/20261026195124_expose_latest_rating.sql
  - supabase/migrations/20261026204258_soak_freshness_log.sql
  - supabase/ops/verify_exposure.sql
  - supabase/ops/verify_monitoring.sql
covered_digest: "v3:sha256:08feb6077f9e1a54a6716c044c902fcd124326545319df4466f26de69c95fc05"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 6: Exposure & E2E Verification - Verification Report

**Phase Goal:** Consumers can read current ratings for every city at any time through a documented, read-only REST interface.
**Verified:** 2026-11-01
**Status:** passed (with 6 open review warnings, none undermining a must-have; see "Review warnings")
**Re-verification:** No, initial verification

## Method and evidence limits

I did not contact the live project and did not read `.env`. Evidence is (a) the code, migrations, docs and tests in the repository, (b) the committed redacted owner-run JSON (`06-09/12/13-live-checks.json`, `06-13-smoke.json`, `06-e2e-trace.json`) and (c) the committed raw soak export (`soak-data/final/`), which I re-analysed myself instead of trusting `06-SOAK-REPORT.md`. The live steps are owner-run and relayed; the raw output of `verify_exposure.sql` and `verify_monitoring.sql` (17/17 and 7/7) is relayed in the SUMMARYs and is not committed as a file. That is accepted evidence per the caller's instruction, but it is the weakest link in the chain.

## Goal Achievement

### Observable Truths (ROADMAP success criteria, the contract)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `GET /rest/v1/latest_rating` with the anon key returns exactly four rows (one per city) with units documented | VERIFIED | Migration `20261026195124_expose_latest_rating.sql` creates `public.latest_rating` as `distinct on (city)` with 31 stored plus 3 computed = 34 columns; every column has a unit-first `comment on column`; `rest-api.md` has a column/type/unit table. Live: `latest_rating_readable` "HTTP 200, 4 rows", `latest_rating_four_cities`, `latest_rating_columns` "34 columns in the published order", `count=exact reports 4` in all three of 06-09, 06-12 and 06-13 JSONs, with a publishable key and a keyless request refused with 401. 46 local-Postgres tests pass (`DLR_TEST_PG_AUTOSTART=1`, I ran them). |
| 2 | The curl, supabase-js and stdlib-urllib examples run as written and return data | VERIFIED | Examples exist and are substantive (`curl.sh`, `read_ratings.py`, `supabase_js.mjs`; env-var driven, GET/HEAD only, paging past the 1000-row cap). Owner ran all three live on 2026-10-27 (06-11-SUMMARY: curl exit 0; Python 3.9.6 and 3.12.13 exit 0; supabase-js 2.117.3 on Node 26 exit 0; 4 cities and paged AUSTIN history), and the PSS/E team ran `read_ratings.py` under PSS/E Python 3.14.0, exit 0. `git diff dd9fa40..HEAD` over `docs/integration`, the client and `supabase/` is empty, so the code that ran live is the code on disk. Offline example tests run against the in-process fake (192 phase tests pass). Relayed, not independently reproducible by me. |
| 3 | A trace cron-job.org trigger -> Actions run -> database rows -> REST response matches values for all four cities | VERIFIED | `06-e2e-trace.json`: `ok: true`, 8 of 8 links; execution 2026-10-27T04:05:02Z HTTP 204, run 40447756754 created 04:05:05Z, `workflow_dispatch`, `success`, workflow "DLR Live Ratings"; all four cities `match: true`, `mismatches: []`, `currency: current`. Cross-check I ran: `soak-data/final/writes.csv` independently lists exactly those four rows for run 40447756754 at 04:00:00Z (AUSTIN fallback, other three ok), consistent with the trace. The cron-job.org execution timestamp is owner-supplied (the tool cannot read cron-job.org), but it is corroborated by the run creation 3 s later and by 72 of 72 hourly `workflow_dispatch` slot verdicts `ok`. |
| 4 | A 72 h soak shows every city's latest `valid_time` within cadence plus grace (OD-4) at every probe; breaches listed with causes | VERIFIED | I re-analysed `soak-data/final/probes.csv` directly: 3456 rows = 864 distinct probe times x 4 cities; first 2026-10-27T03:35:00Z, last 03:30:00Z, span 71.99998 h + one 5 min interval = 72 h; no empty ages; recomputed each `age_seconds` from `probed_at - latest_valid_time` (all agree); maximum age AUSTIN/CORPUS_CHRISTI 65.0 min, EL_PASO/MIDLAND 70.0 min; 0 probes above 90 min; 0 rows flagged `breach`; largest probe spacing 5.005 min (limit 11). Breach list is empty ("No breaches"), so "every breach explained" holds vacuously. 72/72 slot verdicts `ok`. Matches `06-SOAK-REPORT.md` and `report.json` (`verdict: pass`, `breaches: []`). WR-05 does not matter here because there were no breaches to excuse. |
| 5 | Insert, update and delete attempts with the anon key are all rejected | VERIFIED | Behavioral, live, three times (06-09 on 2026-10-26, 06-12 end of soak on 2026-10-30, 06-13 after the platform default-grant change on 2026-11-01), identical each time: table POST, upsert, PATCH (`rating_amps`), DELETE on `city_rating` all `401 / 42501 permission denied` (rejected by privilege, not the RLS "200 []" failure mode); the same three verbs on `latest_rating` rejected `500 / 55000`; `snapshot_before` equals `snapshot_unchanged` (2212, 2520, 2779 rows, sha256 identical before and after each). Corroborated structurally: the migration `revoke all ... from anon, authenticated` then grants SELECT on two objects only, the read policy is the sole policy for these roles, and `06-13-smoke.json` (`supabase_smoke/1`, 14 of 14, `consumers_cannot_write: true`, `delete_denied: true`, role `dlr_writer`) closes T-04-22. Local-Postgres tests prove write denial on a throwaway cluster. Judged on its merits, E2E-03 is met. |

**Score:** 5/5 truths verified (0 present-but-behavior-unverified)

Behavior-dependent truths (5 and 4) are backed by behavioral evidence (live write attempts with before/after snapshot; probe-by-probe ages), not by symbol presence alone.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `supabase/migrations/20261026195124_expose_latest_rating.sql` | view (34 cols, `security_invoker`), index, `assert_fresh`, revokes, read policy | VERIFIED | Read in full. Substantive; sha256 `7e2d5f01...ea0cb` pinned by `expose_migration_test.py`; unchanged. |
| `supabase/migrations/20261026204258_soak_freshness_log.sql` | `ops.freshness_log`, `ops.log_freshness()` | VERIFIED | sha256 `246da223...8552` pinned; 06-05 tests pass. |
| `backend/latest_rating_contract.py` | Python twin of the 34 columns | VERIFIED | Drift test against the migration passes. |
| `backend/supabase_rest.py`, `e2e_verify_readonly.py`, `e2e_trace.py`, `e2e_soak_report.py` | live-check, trace and soak tooling | VERIFIED | Substantive; wired to the live evidence JSONs; offline tests pass (see WR-02, WR-04, WR-05, WR-06 for weaknesses). |
| `docs/integration/rest-api.md` + 3 examples | consumer contract and runnable examples | VERIFIED | Drift guard `rest_api_doc_test.py` passes; examples ran live. |
| `supabase/ops/verify_exposure.sql`, `verify_monitoring.sql` | owner permission checks | VERIFIED (limited) | Run locally by tests and live by owner; blind to column-level grants (WR-01). |
| `06-09/12/13-live-checks.json`, `06-13-smoke.json`, `06-e2e-trace.json`, `soak-data/` | committed redacted evidence | VERIFIED | All present, parseable, internally consistent; no URL, host, ref or key (secret_scan_test: 5 passed, 1 skipped owner-local; grep of the phase directory finds only prose mentions in SUMMARY/REVIEW text). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `latest_rating` view | `city_rating` RLS read policy | `security_invoker = true` | WIRED | Policy `city_rating_public_read` is the only one for anon/authenticated; `assert_fresh` also invoker with empty `search_path`. |
| anon role | write protection | `revoke all` + SELECT-only grants + no write policy | WIRED | Live 42501 on table writes. |
| `ops.log_freshness()` | `latest_rating.is_stale` | pg_cron every 5 min | WIRED | Probe log has 864 distinct times, no gap above 5.005 min. Reads as owner (IN-01), see below. |
| cron-job.org | `dlr_live.yml` | `workflow_dispatch` | WIRED | Trace plus 72/72 slots. |
| Actions run | `city_rating` rows | run_id | WIRED | `writes.csv` rows carry `run_id`, equal to trace. |
| `city_rating` | REST response | PostgREST | WIRED | `SQL equals REST`: 31 columns x 4 cities. |

### Data-Flow Trace (Level 4)

| Artifact | Data variable | Source | Real data | Status |
|----------|---------------|--------|-----------|--------|
| `latest_rating` | all 34 columns | `public.city_rating` (hourly writer upserts) | Yes: SQL-to-REST equality for 4 cities; rows advance hourly across the 72 h window | FLOWING |
| Examples | rows printed | REST `latest_rating` / `city_rating` | Yes: live output includes 52 to 66 AUSTIN history rows | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase 6 offline suite | `pytest` over the 10 phase test files | 192 passed, 39 skipped (Postgres-gated) | PASS |
| Postgres-backed proofs (view, grants, RLS, boundary, labels, soak log) | `DLR_TEST_PG_AUTOSTART=1 pytest expose_migration_test.py soak_log_migration_test.py` | 46 passed (local throwaway cluster) | PASS |
| Secret scan | `pytest secret_scan_test.py` | 5 passed, 1 skipped (owner-local) | PASS |
| Soak probe re-analysis | own script over `probes.csv` | 0 breaches, max age 70.0 min, max gap 5.005 min, span 72 h | PASS |
| Migration pins | sha256 of both migrations vs test constants | unchanged since apply | PASS |
| Full suite (caller-supplied) | n/a | 1932 passed, 81 skipped, 0 failed (2026-11-01) | not re-run by me |

### Probe Execution

Step 7c: SKIPPED. No `probe-*.sh` files are declared or exist for this phase; verification here is through the Python tools above, not shell probes.

### Requirements Coverage

All five ROADMAP/REQUIREMENTS IDs for Phase 6 appear in plan frontmatter, and no REQUIREMENTS.md ID mapped to Phase 6 is unclaimed (no orphans).

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|--------------|-------------|--------|----------|
| API-01 | 06-01, 06-04, 06-06, 06-09, 06-13 | Consumer tables/views exposed read-only to anon under RLS; `latest_rating` one row per city | SATISFIED | Truth 1 and 5 evidence. |
| API-02 | 06-02, 06-06, 06-11 | Documented curl, supabase-js and stdlib urllib examples work as written | SATISFIED | Truth 2 evidence. |
| E2E-01 | 06-08, 06-11 | cron-job.org -> workflow -> rows -> REST with matching values, four cities | SATISFIED | Truth 3 evidence. |
| E2E-02 | 06-03, 06-05, 06-07, 06-10, 06-12 | 72 h soak, freshness within 90 min, breaches explained | SATISFIED | Truth 4 evidence. |
| E2E-03 | 06-04, 06-07, 06-09, 06-12, 06-13 | anon insert/update/delete rejected | SATISFIED on the evidence | Truth 5 evidence; see bookkeeping note. |

**Bookkeeping discrepancy (not a code gap).** `REQUIREMENTS.md` still shows E2E-03 as `[ ]` / `Pending` (line 130 and line 229), and the ROADMAP Phase 6 line (51) is still `[ ]`. The evidence satisfies E2E-03: three live runs with identical rejection verdicts across the 2026-10-30 platform change, snapshot unchanged each time, plus the T-04-22 smoke. The Pending marker reflects only that `requirements.ready-ids` returned neither ready nor blocked at 06-13 close. Recommend the orchestrator tick E2E-03 and the Phase 6 roadmap entry after this verification is accepted. I did not edit either file.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (phase code, docs, SQL, ops files) | n/a | `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` grep | none | No debt markers found in any phase-modified file. |
| `backend/e2e_verify_readonly.py` | 322-328, 389-395 | refusal classifier accepts bare 401/404/5xx for hidden and view-write checks | Warning (WR-02) | Weakens hidden-table and view-write proof only; table writes are classified strictly on 42501. |

No stubs, hardcoded-empty data paths or console-only handlers found in the deliverables.

### Prohibitions (must-NOT checks)

All 13 plans declare judgment-tier prohibitions, each already `status: resolved` in the plan. My verdicts below are NON-AUTHORITATIVE LLM judgments; none is left unresolved, so none is flagged `unverified-prohibition`, but the owner may want to sample the first two because they carry the most risk.

| Prohibition (condensed) | My judgment | Basis |
|---|---|---|
| No INSERT/UPDATE/DELETE/TRUNCATE/REFERENCES/TRIGGER for anon or authenticated, not relying on RLS alone | Held | Migration revokes then grants SELECT only; live 42501 on table writes. Column-level drift is not covered by the check (WR-01) but the live PATCH on `rating_amps` was refused by privilege. |
| Nothing but `city_rating` and `latest_rating` readable; run log and `ops` unreachable | Held | Live 401 on `pipeline_run`, 406 on `ops.freshness_log`; ACLs relayed. |
| `is_provisional` never false on a provisional label; view and `assert_fresh` not owner-rights | Held | View expression read; `security_invoker`; `assert_fresh` is `security invoker` with `search_path = ''`; local tests. |
| No URL, ref or key committed; no `.env` read by tests; no `package.json` or `node_modules` | Held | secret_scan_test passes; evidence JSON clean; `package.json` and `node_modules` absent; no tracked `.env`. |
| Never bearer-token advice; no 2xx write counted as rejected without snapshot | Held | `rest-api.md` says `apikey` header only; snapshot before/after identical in all three runs. |
| Do not relabel breaches, shorten window or excuse by deploy; no annotation written for owner | Held | Zero breaches; three deploys listed as "no runtime change"; no `annotations.json`. See WR-05 caveat for the rule's weakness. |
| Executor must not contact the live project in 06-09; 06-13 any difference is a discrepancy | Held (relayed) | I cannot independently verify who ran what. 06-13 records that the orchestrator ran the read-only SQL runner at the owner's explicit request, a stated deviation from the plan; nothing was changed. |

### Review warnings: effect on the must-haves (judgment, no code changed)

The phase review (`06-REVIEW.md`) reports 0 critical, 6 warning, 6 info, all open in `06-REVIEW-DISPOSITION.md`. I confirmed the substance of WR-01, WR-03 and WR-05 and checked each against the five truths.

- **WR-03 (detector exception text readable by anon): confirmed, does not undermine a ROADMAP truth, but is the one warning that makes published text false.** `backend/DLRSafetyMonitor.py:84` builds `f"detector error ({exc})"`, `backend/supabase_store.py:551` stores `str(a)` with no redaction or cap, and `rest-api.md:131` and `city_rating_v1.md:16` both promise "no file path, no credential, no error text". No success criterion asserts that, and the committed evidence shows only `G4 ... fallback` alert text and `"alerts": []`, so I have no evidence any such row exists today; I cannot query live data to rule it out. Impact is information disclosure of an exception string on a table the owner made public (OD-6), not a read-only or freshness failure. Recommend before the label is lifted: redact/cap in `build_city_row`, report only the exception type at G6, run one owner query for `alerts like 'G6%detector error%'`, and soften the two doc sentences in the meantime. WARNING, not a BLOCKER.
- **WR-01 (`verify_exposure.sql` blind to column-level grants and inherited privileges): confirmed from the SQL (it builds from `pg_class.relacl` only).** It weakens one of the independent proofs, not the truth itself. Truth 5 rests primarily on the live behavioral write attempts, and the PATCH attempt targets `rating_amps` and was refused by privilege (42501), which directly shows no column-level UPDATE on that column for anon on each of the three dates. `REVOKE ALL ON TABLE` at apply time also clears column grants. RLS has no write policy as a second lock. Residual risk is future drift only. WARNING.
- **WR-02, WR-04, WR-06:** tooling-hardening issues. WR-02 could make `hidden:` checks pass vacuously on a bad key, but the same run's `latest_rating_readable` returned HTTP 200 with the same key, and `verify_exposure.sql` independently reports `pipeline_run_not_readable_by_anon`, so the live hidden-table result is not vacuous. WR-04 has no effect today (bound SELECTs only). WR-06 affects a mistyped `http://` URL only.
- **WR-05 (late-run rule explains its own breach):** real design weakness in the verdict logic, but the 72 h soak had zero breaches (I verified from raw probes), so the E2E-02 verdict is unaffected. Should be fixed before the tool is reused for another soak.
- **IN-01 (`log_freshness` probe reads as the owner):** the probe record shows what the owner sees, not what anon sees. It agrees with anon today because the policy is `using (true)` and the three anon live reads (06-09, 06-12, 06-13) returned four fresh rows, so the soak is a valid proxy. Not flagged as coincidental reliance because the precondition is declared in the migration and checked by `verify_exposure.sql`.
- **IN-02 to IN-06:** cosmetic or documentation staleness (IN-06: two stale sentences in `api-contract.md` lines 256 and 271). None affects a truth.

Net: none of the six warnings turns a must-have into a failure. WR-03 is the only one I would schedule soon, because it is a published claim the code contradicts on a public surface.

### Human Verification Required

None required to close Phase 6. The live-project facts (owner-run examples, SQL-editor/SQL-runner results, cron-job.org execution time) are relayed rather than reproduced by this verifier; the committed JSON and the raw soak export corroborate them and I found no inconsistency. If the owner wants a belt-and-braces step, the single useful one is the WR-03 row query above.

### Gaps Summary

No gaps. All five ROADMAP success criteria are verified, all five requirement IDs are accounted for and satisfied, no orphaned requirements, no debt markers, no stubs. The only outstanding items are bookkeeping (tick E2E-03 in `REQUIREMENTS.md` and Phase 6 in `ROADMAP.md`) and the six open review warnings, led by WR-03.

---

_Verified: 2026-11-01_
_Verifier: Claude (gsd-verifier)_
