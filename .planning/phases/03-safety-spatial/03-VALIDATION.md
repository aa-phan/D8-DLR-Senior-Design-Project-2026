---
phase: "3"
slug: "safety-spatial"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-03"
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (config: repo-root `pytest.ini`) |
| **Config file** | `/Users/aphan/Documents/Senior_Design/pytest.ini` |
| **Quick run command** | `pytest backend/tests/SafetyMonitor_TestSuite.py -x` |
| **Full suite command** | `pytest` (uses `pytest.ini`'s `testpaths = backend/tests` automatically) |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest backend/tests/SafetyMonitor_TestSuite.py -x` (or the relevant new C8 test file for corridor-touching tasks)
- **After every plan wave:** Run `pytest` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-TBD | TBD | TBD | DS-F7 | — | `_compute_ampacity` matches `thermal_model.ieee738_ampacity` for identical inputs | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py -k wired -x` | ❌ W0 | ⬜ pending |
| 03-TBD | TBD | TBD | DS-F7 | — | Gate-2 test no longer contradicts itself | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py::test_gate_2_fails_when_link_status_not_ok -x` | ✅ exists (currently failing — documented bug) | ⬜ pending |
| 03-TBD | TBD | TBD | DS-NF5 | — | G1-G4 fallback correctly targets the resolved value (static or last-good) | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py -k fallback -x` | ✅ exists, needs target-assertion updates if fallback-target change adopted | ⬜ pending |
| 03-TBD | TBD | TBD | DS-F10 | — | Corridor discretized into 5 points; per-point ampacity computed; corridor rating = min() | unit + integration | `pytest backend/tests/corridor_discretization_test.py -x` | ❌ W0 (new file) | ⬜ pending |
| 03-TBD | TBD | TBD | DS-F10 | — | Artificially "cooled" point correctly identified as the bottleneck (min-reduction correctness) | unit | `pytest backend/tests/corridor_discretization_test.py -k bottleneck -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky. Task IDs/plan/wave columns are placeholders — the planner fills these once PLAN.md task IDs exist.*

---

## Wave 0 Requirements

- [ ] `backend/tests/corridor_discretization_test.py` — new file, no existing coverage of `station_explorer.py`, corridor logic, or any C8 behavior
- [ ] A new equivalence test in `SafetyMonitor_TestSuite.py` asserting `DLRSafetyMonitor`'s computed rating matches a direct `thermal_model.ieee738_ampacity` call for identical inputs (C7 spec's own stated Acceptance Criterion — no such test exists yet)
- [ ] If the G1/G2 fallback-target change is adopted: update `test_gate_1_fallback_uses_last_good_rating_after_prior_success` and `test_gate_2_fallback_uses_last_good_rating_after_prior_success` (`backend/tests/SafetyMonitor_TestSuite.py:189-215`) to assert `static_rating` instead of the previously-good dynamic rating

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification via pytest.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
