---
phase: "1"
slug: "result-table-spec-and-rating-i-o"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-28"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (repo pin), plain asserts, no classes |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| **Quick run command** | `python -m pytest -q -p no:cacheprovider backend/tests/psse_contract_test.py backend/tests/psse_ratings_test.py backend/tests/psse_run_record_test.py backend/tests/psse_schema_doc_test.py` |
| **Full suite command** | `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 python -m pytest -q -p no:cacheprovider -rs` (project venv, Python 3.10+, initdb/pg_ctl on PATH; PSSE_REQUIRE_PG=1 turns a skipped PSS/E database proof into a failure) |
| **Estimated runtime** | quick: ~10 seconds; full (local Postgres): ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (no database).
- **After every plan wave:** Run the full suite command with `DLR_TEST_PG_AUTOSTART=1`; any skip counts as a failure.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

Task IDs are `<plan>-T<n>` from the PLAN files (filled by the planner 2026-10-28). `PG` below abbreviates the prefix `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1` (with PSSE_REQUIRE_PG=1 a missing Postgres fails instead of skipping); every command is `python -m pytest -q -p no:cacheprovider -rs <args>`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-T1 | 01-01 | 1 | DBX-01 / SC1 | T-01-03 | Reference DDL applies after both Phase 4 migrations on a fresh local Postgres with Supabase's legacy default grants; dlr_psse_writer writes and reads back 1 + 4 + 4 + 2 rows in one transaction | local PG | PG `backend/tests/psse_schema_pg_test.py -k round_trip` | ❌ W0 | ⬜ pending |
| 01-01-T2 | 01-01 | 1 | DBX-01 / SC1, WB-02 / SC4 | T-01-01, T-01-02, T-01-04 to T-01-08 | dlr_psse_writer holds exactly INSERT and SELECT on the four tables; UPDATE/DELETE/TRUNCATE and any access to city_rating, pipeline_run, latest_rating fail 42501; anon/authenticated have nothing; failed-run children rejected (23514/23503); UTC slot check at +05:30; MVA identity rejects the power-factor trap; checks SQL flags a partial run | local PG | PG `backend/tests/psse_schema_pg_test.py` (filters `-k privileges`, `-k integrity`, `-k checks`) | ❌ W0 | ⬜ pending |
| 01-02-T1 | 01-02 | 1 | IN-01 / SC2 | T-01-12 | Today's labels read over loopback HTTP select static_fallback/provisional for all four cities; key only in the apikey header | unit (loopback HTTP) | `backend/tests/psse_ratings_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 01-02-T2 | 01-02 | 1 | IN-01 / SC2 | T-01-09, T-01-10, T-01-11, T-01-13, T-01-14 | Matrix: missing, invalid (types, NaN/inf, naive time, string flags, future time, duplicates), stale at exactly 90 vs 90 min + 1 s, server is_stale, provisional, fresh row used, fresh fallback-status row; read_failed (D-02); unit trap (no MW column read, circuit MVA equals the spec table); redaction parity | unit | `backend/tests/psse_ratings_test.py` (filters `-k units`, `-k redact`) | ❌ W0 | ⬜ pending |
| 01-02-T3 | 01-02 | 1 | Hygiene (D-05) | T-01-15 | Copied constants equal backend/config.py; every psse_job module parses with feature_version (3, 7); no heavy or config import | unit | `backend/tests/psse_contract_test.py` (filter `-k syntax`) | ❌ W0 | ⬜ pending |
| 01-03-T1 | 01-03 | 2 | DBX-01 / SC1 | T-01-16 | Spec has the 16 sections; psse_run doc rows equal the DDL; no connection details | doc-drift | `backend/tests/psse_schema_doc_test.py` | ❌ W0 | ⬜ pending |
| 01-03-T2 | 01-03 | 2 | DBX-01 / SC1 | T-01-18, T-01-19 | All four tables documented in DDL order; ratings_used keys; units table recomputed from config; CHECK vocabularies equal psse_job.constants; DDL text grants exactly the D-03 grants, no credential or function | doc-drift | `backend/tests/psse_schema_doc_test.py` | ❌ W0 | ⬜ pending |
| 01-03-T3 | 01-03 | 2 | DBX-01 / SC1 | T-01-17 | Hand-off note names what Phase 6 must add and the 06-09 impact; pinned sha256 equals the DDL's marked region | doc-drift | `backend/tests/psse_schema_doc_test.py -k handoff` | ❌ W0 | ⬜ pending |
| 01-04-T1 | 01-04 | 2 | WB-01 / SC3, WB-02 / SC4 | T-01-21 | One write_run call commits the run row and 4 + 4 + 2 result rows together; checks SQL all ok | local PG | PG `backend/tests/psse_writer_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 01-04-T2 | 01-04 | 2 | WB-02 / SC4 | T-01-20, T-01-22, T-01-23, T-01-24 | Failure injected at statements 1, 2, 6 and last (and a real duplicate key) leaves zero result rows and a failed record with stage write; same run_id twice leaves one set; closed connection raises RecordFailed with no row; connect errors carry no URL or identity | local PG | PG `backend/tests/psse_writer_test.py -k "atomic or idempotent or failed"` and `-k redact` | ❌ W0 | ⬜ pending |
| 01-04-T3 | 01-04 | 2 | WB-01 / SC3 | T-01-20, T-01-25, T-01-26 | Run record has every required field for ok, fallback and failed; slot floor, empty-message and deterministic ratings_used edges; study results validated against the selection; contract columns equal the DDL | unit | `backend/tests/psse_run_record_test.py` (filters `-k redact`, `-k contract`) | ❌ W0 | ⬜ pending |
| 01-05-T1 | 01-05 | 3 | IN-01 / SC2, WB-01 / SC3 | T-01-29 | Whole run from an HTTP read through a fake study records a complete fallback run with four static cities | local PG + loopback HTTP | PG `backend/tests/psse_job_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 01-05-T2 | 01-05 | 3 | WB-01 / SC3, WB-02 / SC4 | T-01-27, T-01-28, T-01-29, T-01-30 | Every study stage failure, invalid results, write failure and unreachable database end in one honest record (exit 1) or exit 3; a failed read is a fallback run (D-02); nothing is written before the study ends (D-04); logs carry no secrets | local PG | PG `backend/tests/psse_job_test.py -k record` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/psse_contract_test.py`, `psse_ratings_test.py`, `psse_run_record_test.py`, `psse_writer_test.py`, `psse_schema_doc_test.py`, `psse_schema_pg_test.py`, `psse_job_test.py` — each created by the tracer task of its plan (see the map above) for DBX-01, IN-01, WB-01, WB-02
- [ ] A local-Postgres fixture: `backend/tests/psse_local_pg.py` (plan 01-01 Task 1), copied from the `supabase_live_test.py:82-124` pattern; named so it never collides with Phase 6's planned `backend/tests/local_pg.py`; fake helpers in `backend/tests/psse_fakes.py` (plans 01-02 and 01-04)
- [ ] `docs/data-science/schema/psse_results_v1.md` and `.sql`, and the `backend/psse_job/` package skeleton
- [ ] Postgres binaries (`initdb`, `pg_ctl`) on the Mac executor's PATH; a skipped atomicity or privilege proof is a failed gate

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| The spec file and reference DDL are what gets handed to production-pipeline Phase 6 | DBX-01 | The hand-off is a human step: the owner of Phase 6 decides whether to add the tables | A reviewer confirms the spec and DDL are complete, and that the hand-off note names what Phase 6 must add (migration, `dlr_psse_writer` role, verify script). Phase 6 owns the later test that its migration SQL equals the reference DDL. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
