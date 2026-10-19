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
| 03-01-T1 | 03-01 | 1 | DS-F7 | — | `_compute_ampacity` matches `thermal_model.ieee738_ampacity` for identical inputs | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py -k wired -x` | ✅ exists | ✅ green |
| 03-01-T3 | 03-01 | 1 | DS-F7 | — | Gate-2 test no longer contradicts itself | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py::test_gate_2_fails_when_link_status_not_ok -x` | ✅ exists | ✅ green |
| 03-01-T3 | 03-01 | 1 | DS-NF5 | — | G1-G4 fallback correctly targets the resolved value (static or last-good) | unit | `pytest backend/tests/SafetyMonitor_TestSuite.py -k fallback -x` | ✅ exists | ✅ green |
| 03-02-T2 | 03-02 | 2 | DS-F10 | — | Corridor discretized into 5 points; per-point ampacity computed; corridor rating = min() | unit + integration | `pytest backend/tests/corridor_discretization_test.py -x` | ✅ exists | ✅ green |
| 03-03-T3 | 03-03 | 3 | DS-F10 | — | Artificially "cooled" point correctly identified as the bottleneck (min-reduction correctness) | unit | `pytest backend/tests/corridor_discretization_test.py -k bottleneck -x` | ✅ exists | ✅ green |
| 03-03-T1 | 03-03 | 3 | DS-NF5 | T-03-02 | Candidate probe (nearest-5-then-10) logging carries only station id/lat/lon/distance/outcome — never a Synoptic token or request-parameter mapping | unit | `pytest backend/tests/corridor_discretization_test.py -k probe -x` | ✅ exists | ✅ green |
| 03-03-T2 | 03-03 | 3 | DS-NF5 | T-03-01 | An exhausted point resolves to the corridor static rating, is kept in the `min()` reduction, and is never dropped or interpolated from a neighbour | unit | `pytest backend/tests/corridor_discretization_test.py -k exhaust -x` | ✅ exists | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky.*

---

## Wave 0 Requirements

- [x] `backend/tests/corridor_discretization_test.py` — new file, no existing coverage of `station_explorer.py`, corridor logic, or any C8 behavior (created in 03-02, extended through 03-03)
- [x] A new equivalence test in `SafetyMonitor_TestSuite.py` asserting `DLRSafetyMonitor`'s computed rating matches a direct `thermal_model.ieee738_ampacity` call for identical inputs (C7 spec's own stated Acceptance Criterion — no such test exists yet)
- [x] If the G1/G2 fallback-target change is adopted: update `test_gate_1_fallback_uses_last_good_rating_after_prior_success` and `test_gate_2_fallback_uses_last_good_rating_after_prior_success` (`backend/tests/SafetyMonitor_TestSuite.py:189-215`) to assert `static_rating` instead of the previously-good dynamic rating

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
