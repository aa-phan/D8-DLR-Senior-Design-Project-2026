---
phase: "08"
slug: "day-ahead-cooling-forecast-alongside-60-minute-g6"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-08"
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 08-RESEARCH.md "## Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| **Quick run command** | `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/day_ahead_forecast_test.py backend/tests/day_ahead_band_test.py` |
| **Local-Postgres command** | `DLR_TEST_PG_AUTOSTART=1 /Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/day_ahead_migration_test.py backend/tests/expose_migration_test.py backend/tests/soak_log_migration_test.py` |
| **Full suite command** | `DLR_TEST_PG_AUTOSTART=1 /Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider` |
| **Estimated runtime** | quick ~10 s; full suite several minutes (take a counted baseline before Wave 1) |

---

## Sampling Rate

- **After every task commit:** quick command for the touched module, plus `production_conductor_test.py` and `cond02_shadow_golden_test.py` when anything near the shadow path changes
- **After every plan wave:** full suite with `DLR_TEST_PG_AUTOSTART=1`
- **Before `/gsd-verify-work`:** full suite must be green
- **Max feedback latency:** 30 seconds for the quick command

---

## Per-Task Verification Map

Filled by the planner/executor from the research requirement map (DAY-01..DAY-08):

| Req | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|-----------|-------------------|-------------|--------|
| DAY-01 | due targets, catch-up, first-write-wins | unit / local PG | `pytest ... day_ahead_forecast_test.py -k "due or catchup"` | ❌ W0 | ⬜ pending |
| DAY-02 | shadow parity, no substitute, AST caller split, golden untouched | integration / AST / golden | `pytest ... day_ahead_forecast_test.py -k "parity or no_substitute"`; `production_conductor_test.py`; `cond02_shadow_golden_test.py` | ❌ W0 / exists | ⬜ pending |
| DAY-03 | 16 TEST bands, clamp, live switch, anti-peeking | unit / local PG | `pytest ... day_ahead_band_test.py` | ❌ W0 | ⬜ pending |
| DAY-04 | stage after exit code, failure isolation, budget skip, run row | unit (fake children) | `pytest ... dlr_live_day_ahead_stage_test.py dlr_live_run_test.py dlr_live_workflow_test.py` | ❌ W0 / exists | ⬜ pending |
| DAY-05 | migration 1 (table, RLS, writer insert/select), identity columns | text / local PG | `pytest ... day_ahead_migration_test.py` | ❌ W0 | ⬜ pending |
| DAY-06 | migration 2 (view, anon SELECT, status view), contract doc parity, privilege sweep | local PG / text | `pytest ... day_ahead_migration_test.py expose_migration_test.py rest_api_doc_test.py` | ❌ W0 / exists | ⬜ pending |
| DAY-07 | `assert_fresh` day-ahead clause (same signature, armed on first row), secret scan | local PG / text | `pytest ... expose_migration_test.py day_ahead_migration_test.py secret_scan_test.py -k "assert_fresh or secret"` | exists, extend | ⬜ pending |
| D-13a | non-fatal day-ahead manifest tier; live-8 still fatal; hard offline mismatch test | unit | `pytest ... dlr_live_check_models_test.py` | exists, extend | ⬜ pending |
| DAY-08 | owner-gated apply/push/verify/expose | manual + verify script | `backend/day_ahead_verify.py` offline test | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/day_ahead_forecast_test.py` — DAY-01, DAY-02, DAY-05 identity
- [ ] `backend/tests/day_ahead_band_test.py` — DAY-03
- [ ] `backend/tests/day_ahead_migration_test.py` — DAY-05, DAY-06, DAY-07
- [ ] `backend/tests/dlr_live_day_ahead_stage_test.py` — DAY-04 (separate from the 23 existing runner tests)
- [ ] Shared offline fixtures (`_no_network`, `_no_database`, fake conn, `local_pg`, fake shared-input factory)
- [ ] Read-only first-slot verify script with an offline test (D-17)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration 1 applied to Supabase before code push | DAY-08 | Owner-gated `[BLOCKING]` schema push; Supabase CLI not installed locally | Owner applies migration, runs `supabase/ops` verify SQL |
| Push of live-CI changes | DAY-08 | Standing rule: ask before pushing live CI | Owner approves push |
| First issue slot writes rows with correct label, band source and hashes | DAY-08 (D-17) | Needs live run | Owner runs the read-only verify script after the first due run |
| Migration 2 applied (expose) and contract doc published | DAY-08 (D-17) | Owner-gated | Owner applies, live anon read/write checks |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
