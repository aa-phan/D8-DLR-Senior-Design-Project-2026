---
phase: "06"
slug: "dashboard-read-access-and-def-01"
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-11-26"
planned: "2026-11-26"
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 06-RESEARCH.md, Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 on Python 3.12.10 (repo `pytest.ini`: `pythonpath = backend`, `testpaths = backend/tests`) |
| **Config file** | `pytest.ini` at the repo root |
| **Quick run command** (text tier, no database) | `PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python; DEF01_REQUIRE_BRANCH=1 PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider -rs backend/tests/grid_study_def01_text_test.py backend/tests/rest_api_doc_test.py` |
| **Database tier prefix (Git Bash)** | `PATH="/c/Program Files/PostgreSQL/17/bin:$PATH" DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1` |
| **Full suite command** | the prefix, then `"$PY" -m pytest -q -p no:cacheprovider -rs` over `grid_study_per_solver_test.py grid_study_expose_test.py solver_tag_owner_check_test.py expose_migration_test.py psse_results_migration_test.py day_ahead_expose_test.py solver_tag_migration_test.py grid_study_def01_text_test.py rest_api_doc_test.py` with the four Windows deselects (exact command in 06-04-PLAN.md Task 1) |
| **Expected at the phase gate** | 173 passed, 4 deselected, 0 skipped |
| **Estimated runtime** | text tier about 2 s; one database file 30 to 60 s; full suite about 4 to 5 minutes (each file builds its own cluster) |

Known Windows-only failures, deselected, not phase defects (they pass on the owner's Mac): `expose_migration_test.py::test_phase6_migrations_are_unchanged_after_apply`, `expose_migration_test.py::test_is_provisional_reads_the_real_labels`, `psse_results_migration_test.py::test_psse_migration_is_unchanged_after_apply`, `day_ahead_expose_test.py::test_expose_migration_is_unchanged_after_apply` (CRLF byte hashes, matplotlib). The inertness diff (`git diff --quiet bce1c3b -- backend/psse_job backend/pandapower_job <three applied migrations> requirements*.txt`) covers the same risk. No SHA-256 pin of the new migration until it is applied live.

---

## Sampling Rate

- **After every task commit:** the test files the task's `<verify>` names (database prefix when the task touches SQL)
- **After every plan wave:** the plan's `<verification>` command (wave 1: 105 passed; wave 2: 118 passed for 06-02 plus 25 for 06-03)
- **Before `/gsd-verify-work`:** the full suite green (173 passed), then the owner steps: live apply and checks (06-04 Task 2), dashboard commit (06-05 Task 2)
- **Max feedback latency:** about 60 s per database file; 2 s for the text tier

---

## Per-Task Verification Map

`PY` is `.venv/Scripts/python.exe` (fallback `.venv/bin/python`); "PG" means the database tier prefix above. Every auto task creates or extends the test file its verify runs inside the same task, so no verify depends on a later wave.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 (tracer) | 01 | 1 | VIEW-01 | T-06-01, T-06-02 | anon reads 8 rows (one per city per solver), no forbidden key | text + database | PG `pytest backend/tests/grid_study_per_solver_test.py` (2) | ❌ W0, created in task | ⬜ pending |
| 06-01-02 | 01 | 1 | VIEW-02 | T-06-05 | check 7 retired; 6 owner checks each able to fail; ordering pins accept the new file | database + text | PG `pytest solver_tag_owner_check_test.py psse_results_migration_test.py day_ahead_expose_test.py` with 2 deselects (59) | ✅ | ⬜ pending |
| 06-01-03 | 01 | 1 | VIEW-01, VIEW-02 | T-06-01, T-06-03, T-06-04 | 0/4/8 rows, failed run skipped, tie to later finish, ACL and owner rights kept, tables refused with both solvers, re-apply | text + database | PG `pytest grid_study_per_solver_test.py grid_study_expose_test.py` (30) | ✅ after 06-01-01 | ⬜ pending |
| 06-02-01 (tracer) | 02 | 2 | VIEW-02 | T-06-06, T-06-08 | checker returns 37 checks all ok; stripped checker still 29 | database | PG `pytest expose_migration_test.py psse_results_migration_test.py solver_tag_owner_check_test.py` with 3 deselects (72) | ✅ | ⬜ pending |
| 06-02-02 | 02 | 2 | VIEW-02 | T-06-06, T-06-07 | owner trio 6/7/37 ok with both solvers; new check false alone three ways; counts-only detail | database | PG `pytest grid_study_per_solver_test.py` (23) | ✅ | ⬜ pending |
| 06-03-01 (tracer) | 03 | 2 | VIEW-03 | T-06-11, T-06-12 | hand-over names view, 20 columns in order, rules; quoted text matches the branch | text + git ref | `DEF01_REQUIRE_BRANCH=1 DEF01_EXPECT=current pytest grid_study_def01_text_test.py` (2) | ❌ W0, created in task | ⬜ pending |
| 06-03-02 | 03 | 2 | VIEW-03, VIEW-01 | T-06-09, T-06-10 | placeholder lifecycle, no premature date, no credential shape; REST doc per solver | text | `DEF01_REQUIRE_BRANCH=1 DEF01_EXPECT=current pytest grid_study_def01_text_test.py rest_api_doc_test.py` (25) | ✅ | ⬜ pending |
| 06-04-01 (tracer) | 04 | 3 | VIEW-01, VIEW-02 | T-06-05, T-06-13 | full set green, leak scan clean, inertness diff clean, counts-only record | database + text + git | PG full suite (173) then inertness diff and record grep | ✅ | ⬜ pending |
| 06-04-02 | 04 | 3 | VIEW-01, VIEW-02 | T-06-13, T-06-14, T-06-15 | live apply only after `Soak verdict: pass`; dry run lists one file; 6/7/37 ok; key reads view, refused on table | manual (owner) | none: `checkpoint:human-action`, precondition grep of `05-SOAK-RECORD.md` | n/a | ⬜ pending |
| 06-04-03 | 04 | 3 | VIEW-01, VIEW-02 | T-06-16 | date filled only after matching counts; record counts only | text | `DEF01_REQUIRE_BRANCH=1 DEF01_EXPECT=current pytest grid_study_def01_text_test.py` (6) plus placeholder and record greps | ✅ | ⬜ pending |
| 06-05-01 (tracer) | 05 | 4 | VIEW-03 | T-06-19 | fresh fetch; quoted text still current on the branch | text + git ref | `git fetch origin feature/dashboard && DEF01_REQUIRE_BRANCH=1 DEF01_EXPECT=current pytest grid_study_def01_text_test.py` (6) | ✅ | ⬜ pending |
| 06-05-02 | 05 | 4 | VIEW-03 | T-06-18 | the dashboard owner commits the three blocks; this checkout never writes the branch | manual (dashboard owner) | none: `checkpoint:human-action` | n/a | ⬜ pending |
| 06-05-03 | 05 | 4 | VIEW-03 | T-06-17 | branch check in state committed; three files name the migration | text + git ref | `git fetch ... && DEF01_REQUIRE_BRANCH=1 DEF01_EXPECT=committed pytest grid_study_def01_text_test.py` (6) plus three `git show` greps | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Sampling continuity: the two manual tasks (06-04-02, 06-05-02) are separated by two automated tasks (06-04-03, 06-05-01); no run of three tasks lacks an automated verify.

### Requirement-to-test map (from research)

| Req | Behavior | Test | Plan |
|-----|----------|------|------|
| VIEW-01 | Newest complete run per solver: 8 rows with both, 4 with one, 0 with none; newer failed run skipped; same-hour tie to the later finish | `grid_study_per_solver_test.py` | 06-01 |
| VIEW-01 | 20 columns equal `contract.COLUMNS`, none in `FORBIDDEN`, types, ACL, `security_invoker=false`, owner, 19 comments word for word, two rewritten | `grid_study_per_solver_test.py` (sibling database, text) | 06-01 |
| VIEW-01 | Stale flag per solver in one response; 90 minute rule unchanged | `grid_study_per_solver_test.py` tracer | 06-01 |
| VIEW-01 | Migration text: only view, revoke, grant, comments; no PSS/E-only predicate or constant label; re-apply twice; Phase 3 file then new file | `grid_study_per_solver_test.py` | 06-01 |
| VIEW-02 | anon and authenticated with both solvers: view reads, four tables raise `InsufficientPrivilege`; writes refused (existing `grid_study_expose_test.py` on the full chain) | `grid_study_per_solver_test.py`, `grid_study_expose_test.py` | 06-01 |
| VIEW-02 | `verify_exposure.sql` 37 rows all ok with none, one or both solvers; new check false for the Phase 3 view, a hidden city and an older run | `expose_migration_test.py`, `psse_results_migration_test.py`, `grid_study_per_solver_test.py` | 06-02 |
| VIEW-02 | `verify_solver_tag.sql` 6 pinned names all ok; each can fail | `solver_tag_owner_check_test.py` | 06-01 |
| VIEW-02 | Live: 6/7/37 ok; key reads view, refused on a table | owner step, recorded in `06-APPLY-RECORD.md` | 06-04 |
| VIEW-03 | Hand-over names `latest_grid_study`, every column, `solver`, preliminary, 90 minutes, paused, the migration; quoted text matches the branch | `grid_study_def01_text_test.py` | 06-03 |
| VIEW-03 | The dashboard owner committed the text on `origin/feature/dashboard` | `grid_study_def01_text_test.py` with `DEF01_EXPECT=committed`, three `git show` greps | 06-05 |

### Spec-less probe record (no SPEC.md for this phase)

The edge probe over VIEW-01 to VIEW-03 returned three rows, all `unclassified` (status `unresolved`); none was auto-resolved or dismissed. They stay flagged assumptions, reviewed by hand, and the edge classes were written as explicit must-have truths instead: VIEW-01 empty (0 rows, a solver with no complete run is absent), boundary (90 minute rule unchanged, stale and fresh in one response), ordering and adjacency (newer failed run skipped, same-hour tie to the later finish), interruption (re-apply order) in 06-01; VIEW-02 negative proofs (three sabotages, table refusal for both roles) in 06-01 and 06-02; VIEW-03 empty and ordering (placeholder lifecycle, no premature date, drift check before hand-over) in 06-03 and 06-05. Prohibitions recalled and kept, descriptor-less and unverified (`status: unresolved`): no row labelled with another solver and no placeholder row (06-01); no pandapower claim or apply date before the apply, preliminary label kept (06-03); no live apply before `Soak verdict: pass` (06-04); no commit or push to `feature/dashboard` from this checkout (06-05). Canon-referral drop: "public roles must not read the result tables" is canon access control and is covered as an explicit truth, not minted as a prohibition.

---

## Wave 0 Requirements

- [ ] `backend/tests/grid_study_per_solver_test.py` — VIEW-01 and VIEW-02 proofs of the new migration (created by 06-01 Task 1, extended by 06-01 Task 3 and 06-02 Task 2)
- [ ] `backend/tests/grid_study_def01_text_test.py` — VIEW-03 pins of the tracked hand-over text and the branch check (created by 06-03 Task 1)
- [ ] Seeding helpers for one run per solver: copied into the new test file from `solver_tag_owner_check_test.py` (`_complete_run`, `_insert_complete`, `_view_rows`), not imported across modules

No framework install needed (pytest and psycopg are already in `.venv`). No package is added.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live apply of `20261126200000_latest_grid_study_per_solver.sql` | VIEW-01, VIEW-02 | Only the owner holds the live project's credentials; D-02 gates it on the Phase 5 soak | 06-04 Task 2: `migration list`, `db push --dry-run` (one file), `db push`, then the three files in the SQL editor: 6, 7, 37 all ok |
| The dashboard's key reads the view and is refused on a table, live | VIEW-01, VIEW-02 | Needs the live project and the publishable key | 06-04 Task 2 steps 7 and 8 (counts only; HTTP 401 or 403) |
| DEF-01 committed on `feature/dashboard` | VIEW-03 | D-04: only the dashboard owner commits there | 06-05 Task 2; then 06-05 Task 3 reads it back |

The phase verifies `human_needed` until both owner steps are recorded, as Phase 3 did.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the two owner checkpoints are manual by nature: 06-04-02, 06-05-02)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no verify uses the MISSING sentinel; each new test file is created by the task whose verify runs it)
- [x] No watch-mode flags
- [ ] Feedback latency < 60 s per database file (to be measured at execution)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
