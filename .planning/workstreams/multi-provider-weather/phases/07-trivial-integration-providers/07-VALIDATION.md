---
phase: "07"
slug: "trivial-integration-providers"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-11"
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| **Quick run command** | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -x` |
| **Full suite command** | `.venv/bin/python -m pytest` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -x`
- **After every plan wave:** Run `.venv/bin/python -m pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | WX-02 | V5 Input Validation | Malformed/mistyped-station ASOS response raises rather than silently accepted | unit | `.venv/bin/python -m pytest backend/tests/asos_provider_test.py -x` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | WX-02 | V5 Input Validation | ASOS-supplemented fetch produces union-of-timestamps rows with correct unit conversion (knots→m/s, °F→°C) and provenance | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k asos -x` | ❌ W0 | ⬜ pending |
| 07-02-01 | 02 | 1 | WX-04 | V5 Input Validation | Open-Meteo grid fetch returns all 5 `PIPELINE_SCHEMA` weather columns from one request, correctly mapped/unit-converted | unit | `.venv/bin/python -m pytest backend/tests/open_meteo_provider_test.py -x` | ❌ W0 | ⬜ pending |
| 07-02-02 | 02 | 1 | WX-04 | — | Open-Meteo path reachable only via `provider="open_meteo"` on grid shape; station path unaffected | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k open_meteo -x` | ❌ W0 | ⬜ pending |
| 07-03-01 | 03 | 2 | WX-02, WX-04 | — | Both providers' rows carry correct provenance value in Phase 6 provenance columns | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k provenance -x` | ✅ existing pattern (`test_merge_provenance_names_the_actual_supplier_per_field`) — extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/asos_provider_test.py` — new file, covers WX-02 (mocked `requests.get`, `_FakeResponse` convention)
- [ ] `backend/tests/open_meteo_provider_test.py` — new file, covers WX-04 (mocked `requests.get`)
- [ ] Extend `backend/tests/weather_provider_test.py` — add ASOS-supplement and `provider="open_meteo"` dispatch test cases
- No framework install needed — pytest already configured project-wide (`pytest.ini`)

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
