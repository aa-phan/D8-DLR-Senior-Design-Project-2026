---
phase: "1"
slug: "forecasting-model"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: true
wave_0_complete: false
created: "2026-09-24"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| **Quick run command** | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py` |
| **Full suite command** | `.venv/bin/python3 -m pytest -q` |
| **Estimated runtime** | ~30 seconds (full suite, per prior-phase baseline of 388 passed) |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted test file(s), e.g. `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py` or `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py`
- **After every plan wave:** Run `.venv/bin/python3 -m pytest -q` (full suite)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01-01 | 1 | FCST-01 | T-01-01/02 | Only load `.joblib` artifacts produced by this repo's own training script under `data/models/`; never accept an external model path | tracer/unit | `.venv/bin/python3 backend/forecast_training.py --corridor AUSTIN_CORPUS_CHRISTI --years 1 && PYTHONPATH=backend .venv/bin/python3 -c "...E2E_OK..."` | ❌ Wave 0 | ⬜ pending |
| 01-01-02 | 01-01 | 1 | FCST-01/02 | T-01-03 | Training-data poisoning check: validate every offline-assembled row against `units_def.validate_pipeline_row` before fitting; no future-weather leakage | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py backend/tests/ampacity_forecast_test.py -k "no_future_leakage or weakest_link_min_matches_convention or invalid_row_dropped_before_fit or ml_method_sensitive_to_weather or corridor_model_selection or missing_artifact_raises_and_never_falls_back or null_weather_raises_rather_than_imputing"` | ❌ Wave 0 | ⬜ pending |
| 01-02-01 | 01-02 | 2 | FCST-01/02 | — | N/A | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py -k "bakeoff or select_winner or baseline or fold"` | ❌ Wave 0 | ⬜ pending |
| 01-02-02 | 01-02 | 2 | FCST-01 | Model-artifact tampering | Per-corridor artifacts are named/isolated so no cross-corridor bleed occurs; `data/models/` stays git-ignored | unit | `.venv/bin/python3 -m pytest -q backend/tests/ampacity_forecast_test.py -k "corridor_isolation or corridor_model_cache or unknown_corridor"` | ❌ Wave 0 | ⬜ pending |
| 01-03-01 | 01-03 | 3 | FCST-02 | Evaluation-integrity | Validation record's MAE/RMSE figures traceable to the actual bake-off report JSON, not hand-typed | integration/manual | `D=docs/data-science/decisions/forecasting_model.md; test -f "$D" && [ "$(wc -l < "$D")" -ge 90 ] && grep -q '^\*\*Status:\*\*' "$D" && ... && echo RECORD_SHAPE_OK` | ❌ Wave 0 | ⬜ pending |
| 01-03-02 | 01-03 | 3 | FCST-02 | — | N/A | doc/unit | `S=docs/data-science/specs/C9-ampacity-forecasting.md; for t in FORECAST_METHODS ForecastResult ...; do grep -q -- "$t" "$S" || exit 1; done; echo SPEC_CONTRACT_OK` | ❌ Wave 0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Full commands are in each PLAN.md's `<verify>` blocks — abbreviated here for width; see 01-01-PLAN.md, 01-02-PLAN.md, 01-03-PLAN.md for the exact executable strings.*

---

## Wave 0 Requirements

- [ ] `backend/tests/ampacity_forecast_test.py` — extend with new tests for the `"ml"` method path (fixture-injected small fitted model; no real joblib I/O or network calls in unit tests, mirroring `open_meteo_provider_test.py`'s mocked-HTTP convention)
- [ ] `backend/tests/forecast_training_test.py` — new file covering feature engineering, the weakest-link `min()` reduction, and the no-future-leakage invariant, using synthetic (not live-network) weather fixtures
- [ ] `.venv/bin/pip install scikit-learn` — framework install (package legitimacy audit run; no blocking checkpoint per D-02, pre-waived)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real Open-Meteo Archive API backfill produces a usable, non-empty training frame across the full multi-year window | FCST-02 | Live network call against a real, rate-limited third-party API; not mockable without losing the "real data" guarantee FCST-02 requires | Run `.venv/bin/python3 backend/forecast_training.py --corridor <corridor> --years <N>` against the real Open-Meteo endpoint and confirm a non-empty `data/models/training_frame_<corridor>.csv` is produced |
| Bake-off winner's measured out-of-sample accuracy is genuinely better than naive/EWM baselines on real data, not just "the tests pass" | FCST-02 | Requires human judgment reading `docs/data-science/decisions/forecasting_model.md`'s narrative comparison, not a boolean assertion | Read the validation record's Verdict section, confirm the stated MAE/RMSE comparison and "met/not met" conclusion are consistent with the underlying bake-off report JSON |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (two new test files + one framework install, listed above)
- [ ] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
