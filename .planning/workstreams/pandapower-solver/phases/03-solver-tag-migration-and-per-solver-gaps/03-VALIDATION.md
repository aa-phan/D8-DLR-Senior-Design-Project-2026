---
phase: "03"
slug: "solver-tag-migration-and-per-solver-gaps"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-18"
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 03-RESEARCH.md, Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (repo `pytest.ini`) |
| **Config file** | `pytest.ini` at the repo root |
| **Quick run command** | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_solver_tag_test.py backend/tests/psse_gaps_solver_test.py backend/tests/solver_tag_migration_test.py backend/tests/psse_run_record_test.py backend/tests/psse_contract_test.py backend/tests/pandapower_import_gate_test.py backend/tests/psse_phase4_validation_test.py` |
| **Full suite command** | quick command plus `psse_laptop_modes_test.py psse_setup_doc_test.py psse_schema_doc_test.py grid_study_expose_test.py psse_results_migration_test.py psse_gaps_pg_test.py pandapower_study_job_test.py pandapower_solver_tag_test.py` (all under `backend/tests/`) |
| **Database tier (owner's Mac / CI)** | `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs` over the database-bearing files; must report 0 skipped (read the skipped count: some helpers ignore `PSSE_REQUIRE_PG`) |
| **Estimated runtime** | ~15 seconds without Postgres |

Baseline before Phase 3 (14 relevant files): 2 failed, 136 passed, 95 skipped, 1 error. The failures and the error are environmental and pre-existing (CRLF byte-hash pins; `matplotlib` missing). All 95 skips are database tests.

---

## Sampling Rate

- **After every task commit:** run the quick command
- **After every plan wave:** run the full suite command (pure tier), then the database tier on the Mac
- **Before `/gsd-verify-work`:** pure tier green here; database tier green on the Mac with 0 skipped, or the SUMMARY states plainly that it was only skipped
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

Filled by the planner once plans exist. Requirement-to-test map is in 03-RESEARCH.md (DB-01 to DB-03).

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | DB-01 | unit (text) | `pytest backend/tests/solver_tag_migration_test.py -k text` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/solver_tag_migration_test.py` — DB-01 text tier (runs here) and database tier (skips here)
- [ ] `backend/tests/psse_solver_tag_test.py` — DB-02 writer, record and run loop against a recording connection
- [ ] `backend/tests/psse_gaps_solver_test.py` — DB-03 per-solver gaps against a fake connection and the oracle
- [ ] `backend/tests/pandapower_solver_tag_test.py` — vocabulary parity and the tagged rehearsal
- [ ] `backend/tests/psse_local_pg.py` — add `apply_solver_schema` (leave `apply_schema` untouched)
- [ ] Edit `psse_results_migration_test.py:96`, `day_ahead_expose_test.py:127-135`, `grid_study_expose_test.py:236-251` in the same plan as the migration
- [ ] Extend `pandapower_study_job_test.py` with the `solver` and `solver_version` assertions

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration applies and constraints refuse mismatches on a real database | DB-01 | No Postgres on the build machine | On the Mac run the database-tier command above; expect 0 skipped |
| Existing live runs read `psse` and nothing else changed | DB-01 (criterion 4) | Needs the live project; owner applies the migration | After `supabase db push`, run the read-only `supabase/ops/verify_solver_tag.sql` |
| Public view guard `where solver = 'psse'` is accepted | D-03 | Touches a live, public-facing view | Owner reviews and confirms before applying the migration |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
