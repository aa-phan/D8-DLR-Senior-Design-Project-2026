---
phase: "02"
slug: "pandapowerapi-and-study-engine"
status: draft
nyquist_compliant: false
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

Filled by the planner once plans exist. Requirement-to-test map is in 02-RESEARCH.md (ENG-01 to ENG-06).

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | ENG-01 | unit/gate | `pytest backend/tests/psse_study_solver_test.py backend/tests/pandapower_import_gate_test.py -x` | ❌ W0 | ⬜ pending |

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
| Final solve settings wired to recorded PSE-02 values | ENG-05 | Needs the laptop session (plan 01-10) | After 01-10, run the engine with `backend_from_records` on the private report and confirm `is_placeholder` is false |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
