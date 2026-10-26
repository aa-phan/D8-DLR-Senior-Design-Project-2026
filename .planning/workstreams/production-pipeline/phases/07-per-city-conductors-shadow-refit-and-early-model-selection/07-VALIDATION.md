---
phase: "07"
slug: "per-city-conductors-shadow-refit-and-early-model-selection"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-25"
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| **Quick run command** | `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/<file>` |
| **Full suite command** | `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider` (DB tests: prefix `DLR_TEST_PG_AUTOSTART=1`, add `-rs`) |
| **Estimated runtime** | ~165 seconds (full suite); quick runs a few seconds |

---

## Sampling Rate

- **After every task commit:** Run the test file(s) named for that task, plus `backend/tests/cond02_shadow_golden_test.py` once it exists
- **After every plan wave:** Run the full suite command, and the DB tests with `DLR_TEST_PG_AUTOSTART=1 ... -rs`
- **Before `/gsd-verify-work`:** Full suite green, golden test green, `shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256` clean, no change under `data/shadow/predictions`
- **Max feedback latency:** 165 seconds

---

## Per-Task Verification Map

Filled in from the PLAN.md files. Requirement-to-test map from research:

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| COND-01 | Per-city table complete, every value sourced, resolver builds `ConductorConfig`, unknown city raises | unit | `pytest backend/tests/production_conductor_test.py` | ❌ W0 | ⬜ pending |
| COND-01 | Field change alters only that city's fingerprint; source-only edit does not | unit | `pytest backend/tests/rating_identity_test.py` | ✅ extend | ⬜ pending |
| COND-02 | Shadow path byte-identical to HEAD baseline (geometry, arrays, fits, report, 12 artifact hashes) | golden | `pytest backend/tests/cond02_shadow_golden_test.py` | ❌ W0 (capture first) | ⬜ pending |
| COND-02 | Production callers use production resolver; shadow callers do not | AST/import | `pytest backend/tests/production_conductor_test.py::test_caller_split` | ❌ W0 | ⬜ pending |
| SEL-01 | v4 round registry, pre-instant and one-shot refusals armed without override | unit | `pytest backend/tests/forecast_shadow_eval_core_test.py backend/tests/forecast_shadow_confirm_test.py` | ✅ update | ⬜ pending |
| SEL-01 | v4 decision rule: relative margin, no-pick outcome | unit | `pytest backend/tests/forecast_shadow_decision_v4_test.py` | ❌ W0 | ⬜ pending |
| SEL-02 | Refit uses only rows < 2026-03-17, new hashed location, never overwrites frozen models | unit | `pytest backend/tests/forecast_conductor_refit_test.py` | ❌ W0 | ⬜ pending |
| SEL-03 | ABLATION invariance (fit train, score validation); TEST window starts 2026-03-18 | unit | `pytest backend/tests/forecast_conductor_ablation_test.py backend/tests/forecast_test_split_score_test.py` | ❌ W0 | ⬜ pending |
| SEL-04 | Dry-run reads no FRESH file, no network call | unit | `pytest backend/tests/forecast_shadow_confirm_test.py -k dry_run` | ✅ update | ⬜ pending |
| REVAL-01 (B2) | `city_training_frame` uses projected wind; shadow reference unchanged | unit + golden | `pytest backend/tests/forecast_training_test.py backend/tests/cond02_shadow_golden_test.py` | ✅ extend | ⬜ pending |
| REVAL-01 (B5) | Lookback-withheld ml falls back to naive band; `g6_forecast_method` trace key | unit | `pytest backend/tests/city_pipeline_test.py backend/tests/data_cleaning_test.py` | ✅ extend | ⬜ pending |
| REVAL-01 | Offline replay control reproduces fidelity for unchanged config | unit | `pytest backend/tests/real_data_validation_test.py backend/tests/backfill_trace_test.py` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/fixtures/golden_shadow_baseline_<sha>.json` + generator — captured before any production edit
- [ ] `backend/tests/cond02_shadow_golden_test.py`
- [ ] `backend/tests/production_conductor_test.py`
- [ ] `backend/tests/forecast_shadow_decision_v4_test.py`
- [ ] `backend/tests/forecast_conductor_refit_test.py`
- [ ] `backend/tests/forecast_conductor_ablation_test.py`
- [ ] `backend/tests/forecast_test_split_score_test.py`
- [ ] Date-literal updates in existing shadow tests (~57 lines)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| v4 protocol signed by owner before any FRESH outcome | SEL-01 | Owner signature | Confirm signed v4 commit precedes any FRESH-capable merge in `git log` |
| Owner decision recorded after FRESH read | SEL-04 | Owner judgement | Decision record names shadow pick (or none) and interim G6 method |
| New go/no-go signed | REVAL-01 | Owner signature | Signed go/no-go doc committed after re-run |
| Provisional label lift on stored rows | REVAL-01 | Owner-approved DB write | Run only after GO; verify via read-only REST query |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 165s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
