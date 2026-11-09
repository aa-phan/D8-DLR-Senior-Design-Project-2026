---
phase: "06"
slug: "exposure-e2e-verification"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-01"
---

# Phase 06 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

Register built from the `<threat_model>` blocks of 06-01 through 06-13 (authored at plan time). No SUMMARY raised a new threat flag. Verification depth: ASVS L1 (grep-level evidence in the implementation, plus the offline and local-Postgres test runs and the committed live evidence listed below).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Internet (publishable key holder) -> PostgREST | Key is public by design; every request runs as `anon` | Rating rows (public), write attempts |
| PostgREST -> Postgres roles anon/authenticated | Grants and RLS decide what each request can do | Row access decisions |
| Migration author / owner admin connection -> production schema | Migrations change grants on every public relation | Schema and privilege changes |
| pg_cron (scheduling role) -> ops schema | Privileged scheduled job writes the soak log | Freshness probes (internal) |
| Owner machine (writer URL from .env) -> production database | Soak export and trace open a privileged connection | Database URL (secret), rating and run rows |
| Operator machine -> live REST (anon) | Live checks send reads and write attempts with the publishable key | Project URL, publishable key |
| Owner machine -> GitHub (gh auth) | Trace and soak report read Actions runs | Run metadata |
| cron-job.org -> live REST | Third-party scheduler holds the URL and publishable key for the alarm | Project URL, publishable key |
| npm registry -> owner machine | supabase-js installed to run the dashboard example | Third-party package code |
| Platform defaults -> live grants | Supabase changed default grants on 2026-10-30 | Privilege state |
| Local tree / evidence -> public GitHub repository | Every committed byte is world-readable | Docs, examples, exports, live-check JSON |
| Owner judgement -> committed evidence | Annotations explain breaches | Soak verdict accountability |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation (evidence) | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-06-01 | Tampering | anon writes via lingering default grants | high | mitigate | `supabase/migrations/20261026195124_expose_latest_rating.sql:128-134` revoke sweep + default-privilege revokes + SELECT-only grant; `backend/tests/expose_migration_test.py:529-537` asserts 42501/"permission denied" (passed against local Postgres) | closed |
| T-06-02 | Information disclosure | view bypassing RLS | high | mitigate | `security_invoker = true` at migration `:47`; policy-drop test `expose_migration_test.py:545` | closed |
| T-06-03 | Information disclosure | run log reachable by anon | high | mitigate | Revoke sweep; `supabase/ops/verify_exposure.sql:120-123` `pipeline_run_not_readable_by_anon` + aclexplode `:42`; `HIDDEN_TARGETS` in `backend/e2e_verify_readonly.py:92` | closed |
| T-06-04 | Elevation of privilege | `assert_fresh` RPC | medium | mitigate | `stable`, `security invoker`, `search_path = ''`, 0..10080 bound raising 22023 (migration `:148-162`); EXECUTE revoked from public `:187`, granted to anon/authenticated `:188`; `verify_exposure.sql:126` other-function check | closed |
| T-06-05 | Tampering (meaning) | is_provisional false on provisional rows | high | mitigate | Word rule on rating_basis OR config_version (migration `:83`); offline drift guard `expose_migration_test.py:331` | closed |
| T-06-06 | Information disclosure | full rating history readable by key holder | low | accept | See Accepted Risks (OD-6) | closed |
| T-06-07 | Information disclosure | project URL/ref/key committed | high | mitigate | Shape patterns over tracked files `backend/tests/secret_scan_test.py:43-45` + owner exact-value scan; scan passes on current tree | closed |
| T-06-08 | Information disclosure | scan report echoing a value | medium | mitigate | Reports path/line/pattern only (`secret_scan_test.py:16-22`), planted values assembled from pieces | closed |
| T-06-09 | Information disclosure | export leaking DB URL | high | mitigate | `backend/e2e_soak_report.py:254-255` type + `supabase_store.redact`; marker-password test `backend/tests/e2e_soak_report_test.py:284-285` | closed |
| T-06-10 | Tampering | soak tooling writing to production | medium | mitigate | `READ_ONLY_SQL` `e2e_soak_report.py:130`, asserted first statement `e2e_soak_report_test.py:268,652` | closed |
| T-06-11 | Repudiation | late hours hidden by the measure | medium | mitigate | Running-maximum ages from immutable `first_written_at` (`e2e_soak_report.py:28-50`); retry/late-fill tests | closed |
| T-06-12 | Tampering | E2E-03 false pass | high | mitigate | Pass needs 401/403 + 42501 + "permission denied"; any 2xx fails; SHA-256 snapshot (`backend/e2e_verify_readonly.py:13-43`). View writes return 500/55000 and are counted refused with snapshot unchanged (06-09 decision) | closed |
| T-06-13 | Tampering | check damaging production | medium | mitigate | Sentinel 2000-01-01 key `e2e_verify_readonly.py:96-98`; +1 A changes; recovery printed never executed `:402-403` | closed |
| T-06-14 | Spoofing / Elevation | run with secret/service_role key | medium | mitigate | `backend/supabase_rest.py:97-118` refuses `sb_secret_` and service_role JWTs before any request; key only in `apikey` | closed |
| T-06-15 | Information disclosure | URL/key in output or evidence | high | mitigate | `redact_rest` on every line/error/JSON (`supabase_rest.py:167`, `e2e_verify_readonly.py:109,528,542`); leak test `backend/tests/e2e_readonly_test.py:342` | closed |
| T-06-16 | Information disclosure | ops log/function via Data API | medium | mitigate | `supabase/migrations/20261026204258_soak_freshness_log.sql:24,63-65` revokes; `verify_monitoring.sql`; `check_hidden` on `ops.freshness_log` | closed |
| T-06-17 | Denial of service | soak job left running / resurrected | low | mitigate | No-cron-in-migration test `backend/tests/soak_log_migration_test.py:81`; `soak_cron_unschedule.sql` run at soak end, `remaining_jobs (0,)` (06-12) | closed |
| T-06-18 | Repudiation | soak record disagreeing with consumer view | medium | mitigate | Log stores `latest_rating.is_stale` and exact `age_seconds` (soak migration `:31,50-54`) | closed |
| T-06-19 | Information disclosure | URL/key/ref in docs or examples | high | mitigate | Env vars only in `docs/integration/examples/*`; scan-line checks in `example_read_ratings_test.py` / `rest_api_doc_test.py` plus repo-wide scan | closed |
| T-06-20 | Spoofing / Elevation | consumers using secret key or bearer | medium | mitigate | `docs/integration/rest-api.md:15-16`; single-credential-header assertions `example_read_ratings_test.py:333-358` | closed |
| T-06-21 | Tampering (meaning) | provisional/fallback rows misread | medium | mitigate | PROVISIONAL on every amps/MW row and fallback section in `rest-api.md:5-45` | closed |
| T-06-22 | Info disclosure / Spoofing | Python example disabling TLS | medium | mitigate | Default `urlopen` (`read_ratings.py:95`); unverified-context needles rejected `example_read_ratings_test.py:240-243` | closed |
| T-06-23 | Repudiation | breaches hidden or waved through | medium | mitigate | Unexplained breaches fail; annotations printed verbatim with author/date (`e2e_soak_report.py:58-61,812,1024`) | closed |
| T-06-24 | Tampering / Injection | git invoked with DB strings | medium | mitigate | argv list, `_COMMIT_ID.fullmatch` 7-40 hex before `git diff` (`e2e_soak_report.py:925-962`) | closed |
| T-06-25 | DoS (monitoring) | alarm silently disabled | medium | mitigate | Runbook pause/resume and alarm rule `docs/data-science/decisions/dlr_live_runbook.md:189-198`; job-disabled notification on (06-10) | closed |
| T-06-26 | Information disclosure | URL/key in runbook | medium | mitigate | Placeholders; scan control in `backend/tests/monitoring_runbook_test.py:222-226` | closed |
| T-06-27 | Tampering | trace writing to production | medium | mitigate | `backend/e2e_trace.py:82,303` read-only before first query; test `e2e_trace_test.py:602` | closed |
| T-06-28 | Information disclosure | secrets in trace output | high | mitigate | Redaction + marker leak test `backend/tests/e2e_trace_test.py:618-644` | closed |
| T-06-29 | Spoofing | wrong run attributed | medium | mitigate | Exactly one workflow_dispatch candidate in -60 s..+300 s, conclusion/name checks, superseded detection (`e2e_trace.py:15-38`) | closed |
| T-06-30 | Tampering | migration misapplied | medium | mitigate | 05-08 approve-push precondition; dry run listed exactly two files; second dry run "up to date"; verify files all ok (06-09-SUMMARY) | closed |
| T-06-31 | Tampering | applied migration edited later | medium | mitigate | SHA-256 pins `expose_migration_test.py:37-38,662` (passing) | closed |
| T-06-32 | Information disclosure | secrets in 06-09 evidence | high | mitigate | `--json-out` redaction (06-04 tests); 06-02 scan over staged evidence; scan passes on current tree | closed |
| T-06-33 | Tampering | write check damaging production | medium | mitigate | Same controls as T-06-13; snapshot unchanged in 06-09 | closed |
| T-06-34 | Information disclosure | URL + publishable key in cron-job.org | low | accept | See Accepted Risks (D-15) | closed |
| T-06-35 | Tampering / DoS | hourly dispatch job altered | medium | mitigate | New alarm/drill jobs only; dispatch and shadow jobs untouched (06-10-SUMMARY:134); soak slot verdicts clean | closed |
| T-06-36 | DoS (monitoring) | alarm silently disabled | medium | mitigate | Job-disabled notification on; failure-email drill proven 2026-10-27T03:24Z (06-10-SUMMARY:136-138) | closed |
| T-06-37 | Repudiation | 72 h clock backdated | low | mitigate | G = reply 03:34:58Z rounded up to 03:35:00Z, recorded with reply (06-10-SUMMARY:110-112) | closed |
| T-06-38 | Information disclosure | secrets in committed exports | medium | mitigate | Export never writes them (06-03 tests); scan on staged files in `36c9522` | closed |
| T-06-SC | Tampering | supabase-js npm install (06-11) | high | mitigate | Blocking legitimacy checkpoint; owner approved exactly 2.117.3; installed outside repo with `--ignore-scripts`, integrity matched (06-11-SUMMARY:30,40,54). Other plans: no install (accepted) | closed |
| T-06-39 | Information disclosure | secrets in trace evidence | high | mitigate | e2e_trace redaction (06-08 tests); scan over staged files; scan passes on current tree | closed |
| T-06-40 | Spoofing | wrong run attributed | medium | mitigate | One candidate, conclusion success, 8 of 8 links (06-11-SUMMARY:135) | closed |
| T-06-41 | Repudiation | breaches waved through | medium | mitigate | Zero breaches; no annotations written by the executor (06-12-SUMMARY:152) | closed |
| T-06-42 | Tampering / Elevation | privileges drifting during soak | medium | mitigate | verify_exposure 17/17, verify_monitoring 7/7, second `--check-writes` identical to 06-09 (06-12-SUMMARY:132-157) | closed |
| T-06-43 | Denial of service | soak job left running | low | mitigate | Unschedule run, `remaining_jobs (0,)` (06-SOAK-REPORT:273) | closed |
| T-06-44 | Information disclosure | secrets in soak evidence | medium | mitigate | Tools never write them (06-03/04/07 tests); scan over staged files | closed |
| T-06-45 | Tampering / Elevation | platform change granting writes | high | mitigate | Post-2026-10-30 `--check-writes` identical to 06-09/06-12; `consumers_cannot_write` true in `06-13-smoke.json`; no extra grants | closed |
| T-06-46 | Denial of service | read access lost after change | medium | mitigate | `--check-read` 20/20; select grants 4 of 4 (06-13-SUMMARY:104-105) | closed |
| T-06-47 | Information disclosure | secrets in 06-13 evidence | medium | mitigate | Tools never write them; scan over staged files; scan passes on current tree | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

**Notes (non-blocking):**
- Live-only evidence (T-06-30, 35-37, 40-46) rests on owner-relayed terminal output recorded in the SUMMARYs; the executor never contacted the live project.
- The alarm's recovery ("success after failure") email was not observed in the 06-10 drill. Failure alerting and job-disabled notification, which T-06-25/T-06-36 depend on, are in place; recovery notification is an open follow-up for the owner, not a register threat.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-06-01 | T-06-06 | Full rating history readable by any publishable-key holder is intended (OD-6). **Caveat (code review WR-03):** the "no error text" premise was false: G6 detector alerts carried raw exception text into the public `alerts` column. Fixed for new rows in `29aa85c` (redact + 300-char cap); credentials/URLs are removed but a file path in an exception message can still pass. Rows already stored need a one-off owner check. Acceptance stands for the history itself; the residual alert-text exposure is low severity and tracked in 06-REVIEW-DISPOSITION (WR-03) | Owner (OD-6), recorded in 06-01-PLAN; caveat added by audit | 2026-10-26 / 2026-11-01 |
| AR-06-02 | T-06-34 | cron-job.org alarm holds only the publishable key (documented by Supabase as safe to expose), in the owner's account; emails go to the owner only (D-15) | Owner (D-15), recorded in 06-10-PLAN | 2026-10-27 |
| AR-06-03 | T-06-SC (all plans except 06-11) | No package installed; psycopg, pytest, python-dotenv already pinned; Supabase CLI vetted in Phase 4 | Plan-time disposition | 2026-10-26 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-01 | 48 | 48 | 0 | /gsd-secure-phase (orchestrator, L1 grep + tests: 188 passed offline, 46 passed with local Postgres) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-01
