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
| **Full suite command** | `DLR_TEST_PG_AUTOSTART=1 python -m pytest -q -p no:cacheprovider -rs` (Mac venv interpreter) |
| **Estimated runtime** | quick: ~10 seconds; full (local Postgres): ~60 seconds |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (no database).
- **After every plan wave:** Run the full suite command with `DLR_TEST_PG_AUTOSTART=1`; any skip counts as a failure.
- **Before `/gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

Task IDs are filled in by the planner; rows below are keyed to requirement and success criterion (SC).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | DBX-01 / SC1 | — | Spec lists four tables, every column with unit, keys and links; doc columns equal the reference DDL; DDL applies cleanly to a fresh local Postgres after the Phase 4 migrations | doc-drift + local PG | `pytest backend/tests/psse_schema_doc_test.py` and `pytest backend/tests/psse_writer_test.py -k ddl` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | DBX-01 / SC1 | T-1 privilege | `dlr_psse_writer` can INSERT/SELECT the four tables only; no UPDATE/DELETE; no privilege on `city_rating`, `pipeline_run` or `latest_rating`; anon/authenticated have no grant on the result tables | local PG | `pytest backend/tests/psse_writer_test.py -k privileges` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IN-01 / SC2 | — | Matrix: missing, stale at 90 vs 91 min, server `is_stale`, provisional, invalid (non-finite, missing flags, wrong types), read_failed, fresh non-provisional (uses row), fresh fallback-status row; today's real labels make all four cities static with reason `provisional` | unit | `pytest backend/tests/psse_ratings_test.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | IN-01 / SC2 | — | Unit trap: chosen amps are per conductor, `rating_mw` is never read, circuit MVA numbers equal the spec table | unit | `pytest backend/tests/psse_ratings_test.py -k units` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | WB-01 / SC3 | — | Run record has every required field for `ok`, `fallback` and `failed`; `ratings_used` has all four cities; a failed study still writes a record | unit + local PG | `pytest backend/tests/psse_run_record_test.py backend/tests/psse_writer_test.py -k record` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | WB-02 / SC4 | — | Failure injected on the Nth child insert leaves zero rows in all four tables for that `run_id`, then a `failed` record exists; success path writes 1 + 4 + 4 + N rows; a child insert referencing a failed run is rejected (23503); the same `run_id` written twice leaves one set | local PG | `pytest backend/tests/psse_writer_test.py -k "atomic or idempotent or failed"` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | WB-02 | — | Verification SQL returns zero offending runs on good data and flags a hand-made partial run | local PG | `pytest backend/tests/psse_writer_test.py -k verification` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | Hygiene | T-2 secrets | No secret in any error or log; `redact` parity with `supabase_store.redact` on shared cases; Python 3.7 syntax gate | unit | `pytest backend/tests/psse_run_record_test.py -k redact` and `pytest backend/tests/psse_contract_test.py -k syntax` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/psse_contract_test.py`, `psse_ratings_test.py`, `psse_run_record_test.py`, `psse_writer_test.py`, `psse_schema_doc_test.py` — stubs for DBX-01, IN-01, WB-01, WB-02
- [ ] A local-Postgres fixture: reuse Phase 6's `backend/tests/local_pg.py` if it exists by then, else copy the `supabase_live_test.py:82-124` pattern into a helper (names must not collide with Phase 6's file)
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
