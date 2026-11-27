---
phase: "02"
slug: "pandapowerapi-and-study-engine"
status: planned
nyquist_compliant: true
wave_0_complete: false
created: "2026-11-18"
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 02-RESEARCH.md, Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| **Quick run command** | `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_api_test.py backend/tests/pandapower_engine_test.py backend/tests/psse_study_solver_test.py backend/tests/pandapower_import_gate_test.py` (venv from `requirements-pandapower.txt`) |
| **Full suite command** | quick files plus PSS/E regression (`psse_study_test.py psse_contingency_test.py psse_margin_test.py psse_api_test.py psse_contract_test.py psse_dispatch_test.py psse_scaling_test.py`) and Phase 1 `pandapower_network_test.py pandapower_compare_test.py pandapower_raw_test.py` |
| **Estimated runtime** | ~120 seconds (PSS/E set 16.5 s, Phase 1 set 42 s, study end-to-end ~36 s) |

---

## Sampling Rate

- **After every task commit:** run the quick command for the file touched
- **After every plan wave:** run the full suite command
- **Before `/gsd-verify-work`:** full suite green and the staged leak scan exits 0
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

Filled by the planner on 2026-11-18 from plans 02-01 to 02-07. Requirement-to-test map is in 02-RESEARCH.md (ENG-01 to ENG-06).

Every command below runs from the checkout root and is shown without its common prefix. The full commands are in each plan's `<verify>`. The prefix is `PY=.venv/Scripts/python.exe; [ -x "$PY" ] || PY=.venv/bin/python;`, then `PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -q -p no:cacheprovider -rs`. Rows marked "pp" also start with `"$PY" -c "import pandapower; assert pandapower.__version__ == '3.5.6'" &&`, so a missing pandapower fails the command instead of passing on skipped tests. pandapower is not in this Windows checkout's `.venv` at planning time. The phase installs nothing; each pandapower task's precondition halts until the owner installs the approved pin.

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | ENG-01 | integration (tracer, fake psspy) | `backend/tests/psse_study_solver_test.py -k tracer` | ❌ W0 (created by the task) | ⬜ pending |
| 02-01-02 | 01 | 1 | ENG-01 | unit / import gate / PSS/E regression | `backend/tests/psse_study_solver_test.py backend/tests/pandapower_import_gate_test.py` plus the eleven PSS/E files (349 passed at HEAD) | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | ENG-01, ENG-02 | integration (tracer, real solver), pp | `backend/tests/pandapower_api_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | ENG-03, ENG-04 | unit (real solver), pp | `backend/tests/pandapower_api_test.py` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 1 | ENG-02 | unit (real solver), pp | `backend/tests/pandapower_api_test.py backend/tests/pandapower_network_test.py backend/tests/pandapower_raw_test.py backend/tests/pandapower_parity_test.py` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | ENG-01 | integration (tracer, one city through the registry), pp | `backend/tests/pandapower_api_contract_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | ENG-04 | unit (scaling semantics), pp | `backend/tests/pandapower_api_contract_test.py backend/tests/pandapower_api_test.py backend/tests/pandapower_compare_test.py` | ❌ W0 | ⬜ pending |
| 02-03-03 | 03 | 2 | ENG-01 | contract (signature pin, study-call pin, PsseApi parity), pp | `backend/tests/pandapower_api_contract_test.py backend/tests/pandapower_api_test.py backend/tests/psse_study_solver_test.py backend/tests/pandapower_import_gate_test.py backend/tests/psse_api_test.py backend/tests/psse_contract_test.py` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 | 3 | ENG-06 | integration in memory (tracer, four cities, sockets blocked), pp | `backend/tests/pandapower_engine_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-04-02 | 04 | 3 | ENG-02 | unit (preflight refusals), pp | `backend/tests/pandapower_engine_test.py -k "preflight or unreadable or needs_a_pandapower"` | ❌ W0 | ⬜ pending |
| 02-04-03 | 04 | 3 | ENG-05 | unit (records, placeholders, no hard-wiring), pp | `backend/tests/pandapower_engine_test.py backend/tests/pandapower_engine_recorded_test.py` (two owner-local skips here); plus `! env -u DLR_PANDAPOWER_CHECK_DIR DLR_PANDAPOWER_REQUIRE_RECORDS=1 ... backend/tests/pandapower_engine_recorded_test.py` | ❌ W0 | ⬜ pending |
| 02-05-01 | 05 | 3 | ENG-03 | integration (tracer, island through contingency.screen), pp | `backend/tests/pandapower_study_behaviour_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-05-02 | 05 | 3 | ENG-04 | integration (order, failed solve, call recording, master, two runs), pp | `backend/tests/pandapower_study_behaviour_test.py` | ❌ W0 | ⬜ pending |
| 02-06-01 | 06 | 4 | ENG-06 | integration database (tracer), pp | `backend/tests/pandapower_study_job_test.py` (1 passed, database tests SKIPPED here); plus `! env -u DLR_TEST_PG_AUTOSTART -u DLR_TEST_DATABASE_URL PSSE_REQUIRE_PG=1 ... -k tracer` | ❌ W0 | ⬜ pending |
| 02-06-02 | 06 | 4 | ENG-06 | integration database (refusals, island row, leaks), pp | `backend/tests/pandapower_study_job_test.py` (4 SKIPPED here; green only where Postgres exists, see Manual-Only) | ❌ W0 | ⬜ pending |
| 02-07-01 | 07 | 4 | ENG-05 | owner-local (real recorded PSE-02 output), pp | `DLR_PANDAPOWER_REQUIRE_RECORDS=1 ... backend/tests/pandapower_engine_recorded_test.py` | ✅ (from 02-04-03) | ⬜ pending (gated on plan 01-10) |
| 02-07-02 | 07 | 4 | ENG-05 | checkpoint:decision | none (owner reply) | n/a | ⬜ pending |

Every plan also has a frozen-file gate (in its context section) that runs after each commit, and a staged leak scan (`"$PY" -I -B backend/private_leak_scan.py --staged`) that runs before each commit.

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/pandapower_api_test.py` — ENG-01, ENG-02, ENG-04
- [ ] `backend/tests/pandapower_engine_test.py` — ENG-02 preflight, ENG-03, ENG-04, ENG-05, ENG-06 in memory
- [ ] `backend/tests/pandapower_study_job_test.py` — ENG-06 database tier (skips without Postgres)
- [ ] `backend/tests/pandapower_import_gate_test.py`, `backend/tests/psse_study_solver_test.py` — the solver seam
- [ ] `backend/tests/pandapower_study_fixture.py` — case39 RAW with `PT` raised, placeholder mapping, placeholder backend

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Final solve settings wired to recorded PSE-02 values | ENG-05 | Needs the laptop session (plan 01-10) and the owner's private check output | Plan 02-07: `DLR_PANDAPOWER_REQUIRE_RECORDS=1` run of `backend/tests/pandapower_engine_recorded_test.py` (loads the newest `data/private/pandapower/sessions/*/check_*` through `engine.load_recorded_backend`, asserts `is_placeholder` is False and the recorded settings land in every dispatch row), then the owner's decision checkpoint |
| Database tier green | ENG-06 | Postgres (`initdb`, `pg_ctl`) is not installed on this Windows checkout | On a machine with Postgres (the owner's Mac or CI): `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_study_job_test.py` passes with nothing skipped |
| pandapower available on the executing checkout | all pandapower rows | The phase installs nothing. pandapower 3.5.6 is the owner-approved pin of plan 01-05, and this Windows checkout's `.venv` lacks it at planning time | `"$PY" -c "import pandapower; assert pandapower.__version__ == '3.5.6'"` exits 0. If it does not, the owner installs `requirements-pandapower.txt` with the hash-checked procedure in 01-05-SUMMARY.md |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the one exception is the 02-07-02 decision checkpoint; every new test file is created by the task that first verifies against it)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 120s (the slowest file runs the four-city study once or twice, about 36 s per run, using a module-scoped fixture)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
