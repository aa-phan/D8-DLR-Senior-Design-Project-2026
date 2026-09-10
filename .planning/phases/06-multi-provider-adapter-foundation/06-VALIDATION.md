---
phase: "6"
slug: "multi-provider-adapter-foundation"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-10"
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| **Quick run command** | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py backend/tests/units_def_test.py backend/tests/corridor_discretization_test.py -q` |
| **Full suite command** | `.venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest backend/tests/weather_provider_test.py backend/tests/units_def_test.py backend/tests/corridor_discretization_test.py -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-TBD | TBD | 0 | WX-05 | V5 Input Validation | Malformed `location` argument raises `ValueError` rather than silently misrouting | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k dispatch -q` | ❌ W0 | ⬜ pending |
| 06-01-TBD | TBD | 0 | WX-05 | — | Station-based call resolves city internally, no call-site change | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k city_resolution -q` | ❌ W0 | ⬜ pending |
| 06-01-TBD | TBD | 0 | WX-05 | — | Station row + mock grid row merge into one row per timestamp with correct provenance | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -k merge -q` | ❌ W0 | ⬜ pending |
| 06-01-TBD | TBD | 0 | WX-05 | — | Existing corridor_discretization call sites still pass with new signature | regression | `.venv/bin/python -m pytest backend/tests/corridor_discretization_test.py -q` | ✅ existing | ⬜ pending |
| 06-01-TBD | TBD | 0 | WX-07 | — | `PIPELINE_SCHEMA_VERSION` bumped, v2 columns byte-identical | unit | `.venv/bin/python -m pytest backend/tests/units_def_test.py -k schema_version -q` | ❌ W0 | ⬜ pending |
| 06-01-TBD | TBD | 0 | WX-07 | — | New v3 columns are exactly the 4 named, all `required: False` | unit | `.venv/bin/python -m pytest backend/tests/units_def_test.py -k v3_columns -q` | ❌ W0 | ⬜ pending |
| 06-01-TBD | TBD | 0 | WX-07 / SC4 | V5 Input Validation | Provenance columns never default to a guessed source; a pre-existing v2-era row (no provenance) still validates | unit | `.venv/bin/python -m pytest backend/tests/units_def_test.py -k pre_v3_row -q` | ❌ W0 | ⬜ pending |
| 06-01-TBD | TBD | final | SC5 | — | Full suite passes after the interface change | regression (gate) | `.venv/bin/python -m pytest -q` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/weather_provider_test.py` — new file; covers WX-05's dispatch, city-resolution, and merge behaviors, plus a mock grid-provider fixture (D-07).
- [ ] New `test_*` functions appended to `backend/tests/units_def_test.py` — covers WX-07's schema version bump, v3-columns-optional, and pre-existing-row-still-validates assertions (mirrors the Phase 4 v1→v2 pattern at `units_def_test.py:441-464`).
- [ ] No new fixture/conftest infrastructure needed — `backend/tests/corridor_discretization_test.py`'s existing `fake_fetch(stids, start, end)` closures already demonstrate the injection pattern new tests should follow.

---

## Manual-Only Verifications

*None — all phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
