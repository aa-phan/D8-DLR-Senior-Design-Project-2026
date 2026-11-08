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

Filled by the planner from the research requirement map (DAY-01..DAY-08). `pytest ...` means
`/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider`, prefixed with
`DLR_TEST_PG_AUTOSTART=1` for local-Postgres files.

| Req | Plan / Task | Behavior | Test Type | Automated Command | File Exists | Status |
|-----|-------------|----------|-----------|-------------------|-------------|--------|
| DAY-02, DAY-03, DAY-05 | 08-01 T1 (tracer) | one target end to end: shadow functions, TEST band, row, local PG, first write wins, anon denied | integration / local PG | `pytest ... -rs backend/tests/day_ahead_forecast_test.py -k tracer`; `PYTHONPATH=backend .venv/bin/python backend/day_ahead_band.py --check` | ❌ W0 (created by the task) | ⬜ pending |
| DAY-01, DAY-02 | 08-01 T2 | due targets, catch-up arithmetic, shadow parity, no substitute, identity, out-of-bounds, AST caller split, golden untouched | unit / integration / AST / golden | `pytest ... backend/tests/day_ahead_forecast_test.py -k "due or catchup or parity or no_substitute or identity or out_of_bounds"`; `pytest ... backend/tests/production_conductor_test.py backend/tests/cond02_shadow_golden_test.py` | ❌ W0 / exists | ⬜ pending |
| DAY-08 (docs) | 08-02 T1 | DAY IDs in REQUIREMENTS and ROADMAP | text | python one-liner in the plan | n/a | ⬜ pending |
| DAY-04 | 08-02 T2-T3 | optional run-log column; stage after the exit code, isolation, budget skip, run row, redaction, summary; malformed day-ahead record cannot change main()'s return (render_guard) | unit (fake children) | `pytest ... backend/tests/dlr_live_day_ahead_stage_test.py backend/tests/dlr_live_run_test.py backend/tests/live_run_log_test.py backend/tests/supabase_run_log_test.py backend/tests/dlr_live_workflow_test.py backend/tests/dlr_live_runbook_test.py` | ❌ W0 / exists | ⬜ pending |
| DAY-03 | 08-03 T1-T2 | artifact reproducible, strict parser, TEST-window guard, anti-peeking, clamp, live switch per band, D-08 filters | unit / local PG | `pytest ... -rs backend/tests/day_ahead_band_test.py` | ❌ W0 | ⬜ pending |
| DAY-01, DAY-02, DAY-05 | 08-04 T1-T2 | child: contract, none_due, catch-up, idempotent, refusals, redaction, no-store; write-side migration text and privileges; store check SQL | unit / local PG | `pytest ... -rs backend/tests/dlr_day_ahead_test.py backend/tests/day_ahead_migration_test.py backend/tests/expose_migration_test.py` | ❌ W0 / exists | ⬜ pending |
| DAY-02, DAY-04 (D-13, D-13a) | 08-05 T1-T2 | day-ahead warning tier, live 8 still fatal, hash before load, escaping, any exception in the tier is a warning (tier_crash), import order, committed manifest match | unit | `pytest ... backend/tests/dlr_live_check_models_day_ahead_test.py backend/tests/dlr_live_check_models_test.py`; `PYTHONPATH=backend .venv/bin/python backend/dlr_live_check_models.py` | ❌ W0 / exists | ⬜ pending |
| DAY-08, DAY-04 | 08-06 T1-T2 | read-only first-slot check (store mode); runbook section 17 | local PG / text | `pytest ... -rs backend/tests/day_ahead_verify_test.py backend/tests/dlr_live_runbook_test.py` | ❌ W0 / exists | ⬜ pending |
| DAY-05, DAY-08 | 08-07 T1-T3 | full suite rehearsal; owner contract decision; [BLOCKING] write-side apply; sha256 pin | full suite / manual | `pytest ... -rs` (full); `pytest ... backend/tests/day_ahead_migration_test.py -k unchanged_after_apply` | exists | ⬜ pending |
| DAY-08, DAY-01, DAY-04 | 08-08 T1-T3 | rehearsal at the pushed commit incl. parity; owner push; first-slot JSON all ok | full suite / manual + script | `pytest ... -rs` (full); `pytest ... backend/tests/day_ahead_forecast_test.py -k parity`; JSON parse one-liner | exists | ⬜ pending |
| DAY-06, DAY-07 | 08-09 T1-T2 | expose migration: views, grants, status rule, `assert_fresh` same signature and armed clause; privilege sweep (29 checks); Phase 6 reapply test widened to the five published objects (T1 break window limited to three named tests, closed in T2) | local PG / text | `pytest ... -rs backend/tests/day_ahead_expose_test.py backend/tests/expose_migration_test.py backend/tests/soak_log_migration_test.py` | ❌ W0 / exists | ⬜ pending |
| DAY-06, DAY-07 | 08-10 T1-T2 | contract docs parsed against the contract module; REST check (fake PostgREST); runbook section 14; section 16 permission re-check states the post-expose surface (five rows kept) | text / unit | `pytest ... backend/tests/rest_api_doc_test.py backend/tests/day_ahead_verify_test.py backend/tests/dlr_live_runbook_test.py backend/tests/monitoring_runbook_test.py backend/tests/secret_scan_test.py` | exists, extend | ⬜ pending |
| DAY-06, DAY-07, DAY-08 | 08-11 T1-T3 | rehearsal; owner expose decision; [BLOCKING] expose apply; live REST checks; publish push; sha256 pin | full suite / manual + script | `pytest ... -rs` (full); `pytest ... backend/tests/day_ahead_expose_test.py -k unchanged_after_apply`; JSON parse one-liner | exists | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Each test file is created by the task that first needs it (TDD inside the task), not by a separate wave:
- [ ] `backend/tests/day_ahead_forecast_test.py` — 08-01 (DAY-01, DAY-02, DAY-05 identity, tracer)
- [ ] `backend/tests/dlr_live_day_ahead_stage_test.py` — 08-02 (DAY-04; the 23 existing runner tests stay untouched)
- [ ] `backend/tests/day_ahead_band_test.py` — 08-03 (DAY-03)
- [ ] `backend/tests/dlr_day_ahead_test.py`, `backend/tests/day_ahead_migration_test.py` — 08-04 (DAY-01, DAY-02, DAY-05)
- [ ] `backend/tests/dlr_live_check_models_day_ahead_test.py` — 08-05 (D-13, D-13a)
- [ ] `backend/tests/day_ahead_verify_test.py` — 08-06 (store mode), extended in 08-10 (REST mode) (DAY-08)
- [ ] `backend/tests/day_ahead_expose_test.py` — 08-09 (DAY-06, DAY-07)
- [ ] Shared offline fixtures copied per file (`_no_network`, `_no_database`, fake conn, `local_pg`, fake leaf fetches)

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
