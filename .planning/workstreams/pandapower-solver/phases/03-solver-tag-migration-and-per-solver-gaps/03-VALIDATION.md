---
phase: "03"
slug: "solver-tag-migration-and-per-solver-gaps"
status: draft
nyquist_compliant: true
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
| **Full suite command** | quick command plus `psse_laptop_modes_test.py psse_setup_doc_test.py psse_schema_doc_test.py grid_study_expose_test.py psse_results_migration_test.py psse_gaps_pg_test.py pandapower_study_job_test.py pandapower_solver_tag_test.py solver_tag_owner_check_test.py pandapower_engine_test.py` (all under `backend/tests/`; the pandapower files take about three minutes) |
| **Database tier (owner's Mac / CI)** | `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/solver_tag_migration_test.py backend/tests/solver_tag_owner_check_test.py backend/tests/psse_gaps_solver_test.py backend/tests/pandapower_solver_tag_test.py backend/tests/pandapower_study_job_test.py backend/tests/psse_results_migration_test.py backend/tests/grid_study_expose_test.py backend/tests/expose_migration_test.py backend/tests/psse_gaps_pg_test.py backend/tests/psse_writer_test.py backend/tests/psse_study_job_test.py backend/tests/psse_schema_pg_test.py`; must report 0 skipped (read the skipped count: `local_pg.require_local_pg`, used by `grid_study_expose_test.py`, `psse_results_migration_test.py` and `expose_migration_test.py`, ignores `PSSE_REQUIRE_PG`) |
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

Filled by the planner on 2026-11-18. Requirement-to-test map is in 03-RESEARCH.md (DB-01 to DB-03). Every command runs from the repository root as `PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider -rs ...` with `PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python`. "Skips here" means the test is a database proof: it is SKIPPED on this Windows checkout (no Postgres) and counts as proven only when the Mac or CI run reports 0 skipped. Each database task also has a `PSSE_REQUIRE_PG=1` command that must turn the skips into failures here.

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | DB-01 | tracer: text (runs here) + database (skips here) | `backend/tests/solver_tag_migration_test.py -k tracer` | ❌ created by this task | ⬜ pending |
| 03-01-02 | 01 | 1 | DB-01 | unit (text) | `backend/tests/solver_tag_migration_test.py -k text` | ❌ created in 03-01-01 | ⬜ pending |
| 03-01-03 | 01 | 1 | DB-01 | database (skips here) | `backend/tests/solver_tag_migration_test.py`; negative: `PSSE_REQUIRE_PG=1 ... -k db` must report 7 failed or errors | ❌ created in 03-01-01 | ⬜ pending |
| 03-02-01 | 02 | 1 | DB-02 | tracer: unit (recording connection) | `backend/tests/psse_solver_tag_test.py::test_tracer_tagged_run_is_written_with_the_tagged_insert backend/tests/pandapower_import_gate_test.py backend/tests/psse_contract_test.py` | ❌ created by this task | ⬜ pending |
| 03-02-02 | 02 | 1 | DB-02 | unit (writer refusals, all-or-nothing) | `backend/tests/psse_solver_tag_test.py backend/tests/psse_writer_test.py backend/tests/psse_phase4_validation_test.py backend/tests/psse_run_record_test.py backend/tests/pandapower_import_gate_test.py backend/tests/psse_contract_test.py` | ✅ (new file from 03-02-01) | ⬜ pending |
| 03-02-03 | 02 | 1 | DB-02 | unit + PSS/E regression (122 passed, 43 skipped at HEAD) | `backend/tests/psse_solver_tag_test.py` plus the ten-file PSS/E regression set (03-02 context) | ✅ | ⬜ pending |
| 03-03-01 | 03 | 2 | DB-03 | tracer: unit (fake read-only connection) | `backend/tests/psse_gaps_solver_test.py -k tracer` | ❌ created by this task | ⬜ pending |
| 03-03-02 | 03 | 2 | DB-03 | unit (per-solver oracle, seeded histories) | `backend/tests/psse_gaps_solver_test.py` | ✅ (from 03-03-01) | ⬜ pending |
| 03-03-03 | 03 | 2 | DB-03 | unit + one database test (skips here) + legacy unchanged | `backend/tests/psse_gaps_solver_test.py backend/tests/psse_gaps_pg_test.py backend/tests/psse_laptop_modes_test.py backend/tests/psse_setup_doc_test.py backend/tests/psse_contract_test.py backend/tests/pandapower_import_gate_test.py` | ✅ | ⬜ pending |
| 03-04-01 | 04 | 2 | DB-02 | tracer: unit with the real engine (pandapower) | `backend/tests/pandapower_solver_tag_test.py::test_tracer_engine_run_is_written_tagged backend/tests/pandapower_engine_test.py::test_tracer_four_cities_in_memory backend/tests/pandapower_import_gate_test.py` | ❌ created by this task | ⬜ pending |
| 03-04-02 | 04 | 2 | DB-02 (parity with DB-01's check) | unit (vocabulary parity, refusals) | `backend/tests/pandapower_solver_tag_test.py -k "tracer or parity or refused"` | ✅ (from 03-04-01) | ⬜ pending |
| 03-04-03 | 04 | 2 | DB-02 | database rehearsal (skips here) | `backend/tests/pandapower_solver_tag_test.py backend/tests/pandapower_study_job_test.py`; negative: `PSSE_REQUIRE_PG=1 ... pandapower_solver_tag_test.py -k db` must report 3 failed or errors | ✅ | ⬜ pending |
| 03-05-01 | 05 | 2 | DB-01 (criterion 4) | tracer: text (runs here) + database all-ok and per-check negatives (skip here) | `backend/tests/solver_tag_owner_check_test.py`; negative: `PSSE_REQUIRE_PG=1 ... -k db` must report 7 failed or errors | ❌ created by this task | ⬜ pending |
| 03-05-02 | 05 | 2 | DB-01 (D-03) | checkpoint:decision, gate blocking-human | none: the owner answers "guard" or "leave" | n/a | ⬜ pending |
| 03-05-03 | 05 | 2 | DB-01 (D-03 guard) | text (runs here) + database (skips here) | `backend/tests/solver_tag_owner_check_test.py backend/tests/solver_tag_migration_test.py backend/tests/grid_study_expose_test.py` | ✅ | ⬜ pending |

Migration text subset (plans 01 and 05; baseline 3 failed, 52 passed, 97 skipped, the 3 failures being the pre-existing CRLF hash tests): `backend/tests/psse_results_migration_test.py backend/tests/day_ahead_expose_test.py backend/tests/grid_study_expose_test.py backend/tests/expose_migration_test.py backend/tests/psse_schema_doc_test.py backend/tests/soak_log_migration_test.py backend/tests/supabase_schema_doc_test.py`. After each plan the FAILED lines must still be exactly those three.

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Each test file is created by the tracer task of the plan that needs it (no separate Wave 0 plan; no task references a test file that does not exist when it runs).

- [ ] `backend/tests/solver_tag_migration_test.py` — DB-01 text tier (runs here) and database tier (skips here); created by 03-01-01
- [ ] `backend/tests/psse_solver_tag_test.py` — DB-02 writer, record and run loop against a recording connection; created by 03-02-01
- [ ] `backend/tests/psse_gaps_solver_test.py` — DB-03 per-solver gaps against a fake connection and the oracle, plus one database test; created by 03-03-01
- [ ] `backend/tests/pandapower_solver_tag_test.py` — tracer, vocabulary parity, refusals and the tagged rehearsal; created by 03-04-01
- [ ] `backend/tests/solver_tag_owner_check_test.py` — the owner's read-only check `supabase/ops/verify_solver_tag.sql` and the D-03 view-guard proofs; created by 03-05-01
- [ ] `backend/tests/psse_local_pg.py` — add `SOLVER_TAG_MIGRATION`, `apply_solver_tag_migration`, `apply_solver_schema`, `make_run_id(prefix=)` (leave `apply_schema` untouched); 03-01-01
- [ ] Edit `psse_results_migration_test.py:96` and `day_ahead_expose_test.py:127-135` in the same plan and task as the migration (03-01-01); edit `grid_study_expose_test.py:236-251` in the task that adds the view guard (03-05-03, only if the owner chooses the guard)
- [ ] Edit `pandapower_engine_test.py:94-97` (03-04-01, forced by the run-loop cross-check) and extend `pandapower_study_job_test.py` with the `solver` and `solver_version` assertions (03-04-01 and 03-04-03)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration applies and constraints refuse mismatches on a real database | DB-01 | No Postgres on the build machine | On the Mac run the database-tier command above; expect 0 skipped |
| Existing live runs read `psse` and nothing else changed | DB-01 (criterion 4) | Needs the live project; owner applies the migration | After `supabase db push`, run the read-only `supabase/ops/verify_solver_tag.sql` |
| Public view guard `where solver = 'psse'` is accepted | D-03 | Touches a live, public-facing view | Owner answers the checkpoint:decision of plan 03-05 Task 2 ("guard" or "leave") before the guard is written; the answer is recorded in 03-05-SUMMARY.md |
| Laptop `gaps` command stays pooled across solvers | DB-03 (assumption A6) | Owner preference, not testable | Owner confirms, or asks for the laptop command to change in a later phase (would also change `launcher.py`, `psse_setup_doc_test.py` and the guide) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the one exception is the decision checkpoint 03-05-02, which gates no code)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (each new test file is created by its plan's tracer task)
- [x] No watch-mode flags
- [ ] Feedback latency < 30s (pure-Python plans yes; the pandapower tasks of 03-04 take one to three minutes because they run the four-city study)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
