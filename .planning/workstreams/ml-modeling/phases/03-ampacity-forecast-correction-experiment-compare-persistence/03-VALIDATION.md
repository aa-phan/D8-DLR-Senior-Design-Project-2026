---
phase: "03"
slug: "ampacity-forecast-correction-experiment-compare-persistence"
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-09-29"
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| **Quick run command** | `.venv/bin/python -m pytest backend/tests/<touched>_test.py -x -q` |
| **Full suite command** | `.venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~30-60 seconds (no network in the unit suite; live-network runs — the calibration gate, the actual experiment fetch — are separate manually-invoked steps, not part of the automated suite) |

---

## Sampling Rate

- **After every task commit:** `.venv/bin/python -m pytest backend/tests/<touched>_test.py -x -q`
- **After every plan wave:** `.venv/bin/python -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite green, **plus** one live-network calibration run
  (`forecast_leadtime_calibration.py`) whose output is transcribed into the tracked decision
  record — mirrors this workstream's existing precedent (`forecast_training.py --bakeoff` is run
  by hand and `forecasting_model.md` hand-transcribes it).
- **Max feedback latency:** 60 seconds (unit suite only; live-network steps are explicitly
  out-of-band and not gated on this latency).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 01 | 1 | D-03 | V4 (path traversal) | `thermal_model.ieee738_ampacity` output exactly unchanged after extraction (`np.array_equal`, not `allclose` — see Pitfall 1) | unit | `.venv/bin/python -m pytest backend/tests/thermal_model_test.py -x -q` | ✅ extend existing | ⬜ pending |
| 03-01-T2 | 01 | 1 | D-03 | — | `q_conv_override=None` is a true no-op; a passed override changes the result | unit | same | ❌ W0 | ⬜ pending |
| 03-01-T3 | 01 | 1 | D-03 | — | `corridor_weakest_link` reproduces `corridor_training_frame`'s pre-refactor `dlr_amps`/`bottleneck_index` exactly | unit | `.venv/bin/python -m pytest backend/tests/forecast_training_test.py -x -q` | ✅ extend existing | ⬜ pending |
| 03-02-T1 | 02 | 1 | D-01 | Caller-URL SSRF | New provider's base URLs are fixed module constants; `models=ecmwf_ifs` always present in outgoing params | unit (recorder) | `.venv/bin/python -m pytest backend/tests/open_meteo_forecast_provider_test.py -x -q` | ❌ W0 | ⬜ pending |
| 03-02-T2 | 02 | 1 | D-01 | V5 input validation | An all-null / partially-null variable array raises, never forward-filled (Pitfall 3) | unit | same | ❌ W0 | ⬜ pending |
| 03-02-T3 | 02 | 1 | D-01 | — | Single-Runs `run=` formatted `%Y-%m-%dT%H:%M`; malformed-`run` 400 vs. unavailable-`run` 400 distinguished (Pitfall 4) | unit | same | ❌ W0 | ⬜ pending |
| 03-03-T1 | 03 | 2 | D-01 | — | `assert_supports_horizon` fails on the unfiltered series and passes on `hour % 6 == 1` | unit | `.venv/bin/python -m pytest backend/tests/forecast_leadtime_calibration_test.py -x -q` | ❌ W0 | ⬜ pending |
| 03-04-T1 | 04 | 2 | D-02 | — | Every train timestamp < every val timestamp < every test timestamp; split is pure; empty side raises | unit | `.venv/bin/python -m pytest backend/tests/experiment_splits_test.py -x -q` | ❌ W0 | ⬜ pending |
| 03-04-T2 | 04 | 2 | D-02 | — | `calendar_split` agrees with `anomaly_training.chronological_split` at equivalent boundaries | unit | same | ❌ W0 | ⬜ pending |
| 03-05-T1 | 05 | 3 | D-02 | Silent-null / fail-safe | All seven arms scored on a byte-identical test-timestamp index | unit | `.venv/bin/python -m pytest backend/tests/forecast_experiment_test.py -x -q` | ❌ W0 | ⬜ pending |
| 03-05-T2 | 05 | 3 | D-02 | Standing ethical commitment (REQUIREMENTS.md Out of Scope) | Experiment never calls `ampacity_forecast._load_corridor_model`; approach 5 refits from train+val only | unit (monkeypatch to raise) | same | ❌ W0 | ⬜ pending |
| 03-05-T3 | 05 | 3 | D-02 | — | Oracle arm lives in a separate report key, absent from any winner-selection input | unit | same | ❌ W0 | ⬜ pending |
| 03-06-T1 | 06 | 1 | D-02 | — | `from_uv(*to_uv(s, d)) == (s, d)` for all integer `d` in 0..359, `s > 0` | unit | `.venv/bin/python -m pytest backend/tests/wind_vector_test.py -x -q` | ❌ W0 | ⬜ pending |
| 03-06-T2 | 06 | 1 | D-02 | — | `perpendicular_wind(*from_uv(*to_uv(s, d)), az) == perpendicular_wind(s, d, az)` | unit | same | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/open_meteo_forecast_provider_test.py` — new; clone `open_meteo_provider_test.py`'s `_FakeResponse`/`_mock_get` scaffolding
- [ ] `backend/tests/wind_vector_test.py` — new
- [ ] `backend/tests/experiment_splits_test.py` — new
- [ ] `backend/tests/forecast_leadtime_calibration_test.py` — new
- [ ] `backend/tests/forecast_experiment_test.py` — new
- [ ] Extend `backend/tests/thermal_model_test.py` with the exact-equality extraction gate (`np.array_equal`)
- [ ] Extend `backend/tests/forecast_training_test.py` with the `corridor_weakest_link` equality gate
- [ ] `backend/tests/` importability idiom for new modules (no network/file I/O on import) — pattern exists at `thermal_model_test.py:249`
- [ ] Framework install: **none needed** — pytest 9.0.3 already present and pinned

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Lead-time calibration gate's live measurement against Single-Runs API | D-01 | Requires live network access to two external APIs; the unit suite tests the gate's *logic* with mocked responses, not the real measurement | Run `.venv/bin/python backend/forecast_leadtime_calibration.py` by hand, inspect the JSON + histogram output, confirm `assert_supports_horizon` behaves as the research predicts (fails unfiltered, passes on `hour % 6 == 1`) before proceeding |
| Full seven-arm experiment run producing the decision record's numbers | D-02 | Requires live network fetch of ~340 requests across three Open-Meteo endpoints, plus model fitting; not something to run automatically on every commit | Run `.venv/bin/python backend/forecast_experiment.py` by hand once data assembly/splits/refactors are all in place; transcribe results into `docs/data-science/decisions/forecast_correction_experiment.md` per this workstream's existing hand-transcription precedent |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
