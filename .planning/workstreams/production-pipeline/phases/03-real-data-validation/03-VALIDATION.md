---
phase: "03"
slug: "real-data-validation"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-10-21"
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Reconstructed from artifacts after execution (state B).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pytest.ini` (`testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| **Quick run command** | `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/backfill_trace_test.py backend/tests/real_data_validation_test.py backend/tests/real_data_validation_val02_test.py` |
| **Full suite command** | `.venv/bin/python -m pytest -q -p no:cacheprovider` |
| **Estimated runtime** | ~5 seconds quick (41 tests); ~175 seconds full (1397 tests) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 180 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | VAL-01 | T-03-05 | Backfill tests make no network call; credentials removed from env | integration (tracer) | `pytest backend/tests/backfill_trace_test.py backend/tests/backfill_archive_test.py` | ✅ | ✅ green |
| 03-01-02 | 01 | 1 | VAL-01 | T-03-01, T-03-02 | Credential-shaped pairs redacted in trace; manifest pins hashes | unit (TDD) | `pytest backend/tests/backfill_trace_test.py backend/tests/real_data_validation_test.py backend/tests/backfill_archive_test.py` | ✅ | ✅ green |
| 03-01-03 | 01 | 1 | VAL-01 | T-03-02, T-03-03 | Self-checks make `report` exit 1 on disagreement; no shadow/experiment reads | unit (TDD) | `pytest backend/tests/real_data_validation_test.py backend/tests/backfill_trace_test.py` | ✅ | ✅ green |
| 03-02-01 | 02 | 2 | VAL-01, VAL-02 | T-03-06, T-03-09 | Clean backend tree recorded; `.env` never read by the executor | artifact check | Plan 03-02 Task 1 `<automated>` preflight (prints `PREFLIGHT_OK`) | ✅ | ✅ green (2026-10-20 run, HEAD 175b32b) |
| 03-02-02 | 02 | 2 | VAL-01, VAL-02 | T-03-06 | Only the owner loads credentials | manual | — (see Manual-Only) | — | ✅ done by owner |
| 03-02-03 | 02 | 2 | VAL-01, VAL-02 | T-03-07, T-03-08 | Only derived files committed; hashes pinned | artifact check | Plan 03-02 Task 3 `<automated>` (prints `COMPLETE_OK`, `MANIFEST_OK`) | ✅ | ✅ green (re-run 2026-10-21) |
| 03-03-01 | 03 | 2 | VAL-02 | T-03-14 | VAL-02 uses only the city_pipeline trace | unit (TDD) | `pytest backend/tests/real_data_validation_val02_test.py backend/tests/real_data_validation_test.py` | ✅ | ✅ green |
| 03-03-02 | 03 | 2 | VAL-02 | T-03-11, T-03-12, T-03-13, T-03-15 | Replay refuses without models or over existing outputs; zero network; `naive_replay` label | unit (TDD) | `pytest backend/tests/real_data_validation_val02_test.py backend/tests/real_data_validation_test.py backend/tests/backfill_trace_test.py` | ✅ | ✅ green |
| 03-04-01 | 04 | 3 | VAL-01, VAL-02 | T-03-16, T-03-18 | Archive hash checked before analysis; deterministic, aggregate-only outputs | artifact check | Plan 03-04 Task 1 `<automated>` (prints `TABLES_OK`) | ✅ | ✅ green (re-run 2026-10-21) |
| 03-04-02 | 04 | 3 | VAL-01, VAL-02, VAL-03 | T-03-17, T-03-19 | Tables copied verbatim; decision left to the owner | artifact check | Plan 03-04 Task 2 `<automated>` (prints `DOC_OK`) | ✅ | ✅ green (re-run 2026-10-21 without the `Pending owner decision.` clause, which 03-05 superseded by design) |
| 03-05-01 | 05 | 4 | VAL-03 | T-03-20 | Decision taken only by the owner | manual | — (see Manual-Only) | — | ✅ done by owner |
| 03-05-02 | 05 | 4 | VAL-03 | T-03-20, T-03-21, T-03-22 | Verbatim owner words; owner signature; Phase 4 blocked on NO-GO | artifact check | Plan 03-05 Task 2 `<automated>` (prints `DECISION_RECORDED`) | ✅ | ✅ green (re-run 2026-10-21) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real backfill over 2026-09-08..09-28 (smoke, then full) | VAL-01, VAL-02 | Needs the owner's credentials in `.env`, which the executor may not read (T-03-06) | Run the two commands in 03-02-PLAN Task 2; then 03-02 Task 3's check must print `COMPLETE_OK` and `MANIFEST_OK` |
| Production go/no-go and signature | VAL-03 | A decision only the owner can make (blocking-human gate) | Owner reads the doc's Go/no-go section and replies; confirmed at 03-UAT test 1 (pass) |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (the two manual tasks are owner actions by design)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none missing)
- [x] No watch-mode flags
- [x] Feedback latency < 180s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-10-21
