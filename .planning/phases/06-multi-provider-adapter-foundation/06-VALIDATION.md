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
| 06-01-T2 | 06-01 | 1 | WX-07 / SC3 | T-06-01 | Station-path rows carry per-field provenance; an unknown source stays `None` rather than being guessed | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py backend/tests/units_def_test.py -q` | ❌ W0 | ⬜ pending |
| 06-01-T3 | 06-01 | 1 | WX-07 / SC3 | T-06-02 | `PIPELINE_SCHEMA_VERSION` bumped to 3, all 15 v2 columns byte-identical, new v3 keys all `required: False` | unit | `.venv/bin/python -m pytest backend/tests/units_def_test.py -q -k "v3 or pre_phase6 or provenance"` | ❌ W0 | ⬜ pending |
| 06-01-T3 | 06-01 | 1 | WX-07 / SC4 | T-06-02 | A pre-existing v2-era row (no provenance keys) still validates; an unregistered provider name produces one error naming the column | unit | `.venv/bin/python -m pytest backend/tests/units_def_test.py -q` | ❌ W0 | ⬜ pending |
| 06-02-T1 | 06-02 | 2 | WX-05 | T-06-05 (V5 Input Validation) | `location` dispatches on shape; a malformed shape raises `ValueError` rather than silently misrouting | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -q -k dispatch` | ❌ W0 | ⬜ pending |
| 06-02-T1 | 06-02 | 2 | WX-05 / SC2 | — | Existing `corridor_discretization` call sites still pass with the renamed parameter | regression | `.venv/bin/python -m pytest backend/tests/corridor_discretization_test.py -q` | ✅ existing | ⬜ pending |
| 06-02-T2 | 06-02 | 2 | WX-05 | T-06-06 | Station-based call resolves city internally to a literal `CITY_COORDINATES` key, and returns `None` rather than defaulting when coordinates are unresolvable | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -q -k city_resolution` | ❌ W0 | ⬜ pending |
| 06-03-T1 | 06-03 | 3 | WX-05 / SC1 | T-06-10, T-06-12 | Station row + grid row merge into one row per `(city, datetime_utc)`; empty/single-row/null-city inputs behave as specified; output order stable | unit | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -q -k "merge or attach_city"` | ❌ W0 | ⬜ pending |
| 06-03-T2 | 06-03 | 3 | WX-05 / SC1 | T-06-11, T-06-14 | End-to-end station + mock grid produces one `PIPELINE_SCHEMA`-valid row with correct per-field provenance; the mock never reaches production dispatch | unit (D-07 mock) | `.venv/bin/python -m pytest backend/tests/weather_provider_test.py -q -k "end_to_end or mock_grid or provenance_matches"` | ❌ W0 | ⬜ pending |
| 06-03-T3 | 06-03 | 3 | SC5 | T-06-15 | Full suite passes with the complete adapter in place; PRD/data_provider docs untouched (Phase 10 scope) | regression (gate) | `.venv/bin/python -m pytest -q` | ✅ existing | ⬜ pending |

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
