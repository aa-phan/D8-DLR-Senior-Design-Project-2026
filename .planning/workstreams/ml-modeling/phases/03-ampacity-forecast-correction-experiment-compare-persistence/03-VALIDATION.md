---
phase: "03"
slug: "ampacity-forecast-correction-experiment-compare-persistence"
status: complete
nyquist_compliant: true
wave_0_complete: true
created: "2026-09-29"
updated: "2026-09-30"
revision: "D-04 replan — Waves 2-5 remapped to Plans 03-03..03-07; Wave 1 rows corrected to the plan numbering actually executed; all waves closed out at phase completion"
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

- **After every task commit:** `.venv/bin/python3 -m pytest -q backend/tests/<touched>_test.py`
- **After every plan wave:** `.venv/bin/python3 -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite green, **plus** both live-network verification runs (the
  legacy 1-hour calibration gate and the 24-hour offset-lead cross-check) and the single seven-arm
  held-out test run, each hand-transcribed into the tracked decision record — mirroring this
  workstream's existing precedent (`forecast_training.py --bakeoff` is run by hand and
  `forecasting_model.md` hand-transcribes it).
- **Max feedback latency:** 60 seconds (unit suite only; live-network steps are explicitly
  out-of-band and not gated on this latency).
- **Known baseline:** the full suite carries 23 pre-existing `corridor_discretization_test.py`
  failures, reproducible on Plan 03-02's own base commit and logged in `.planning/WINDOWS.md`. Every
  full-suite gate in Plans 03-03 through 03-07 is written against that baseline rather than against
  zero, so a plan neither inherits blame for them nor is allowed to hide a new failure behind them.

---

## Per-Task Verification Map

> **Plan-numbering correction (2026-09-29).** The rows below were originally written against a
> pre-execution plan numbering that no longer matches what ran: the old `03-01-*` rows described
> work that landed in Plan **03-02** (thermal-model extraction, weakest-link), and the old
> `03-02-*` rows described work that landed in Plan **03-01** (the provider adapter). They are
> corrected here to the plans actually executed. Plans 03-03 through 03-07 are the D-04 replan
> (Waves 2-5) and their rows are new — the superseded 03-03 through 03-06 rows for the abandoned
> 1-hour-primary design have been replaced, not merely appended to.

**Wave 1 — executed (corrected numbering)**

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 01 | 1 | D-01 | Caller-URL SSRF | Provider base URLs are fixed module constants; `models` pinned in every outgoing request | unit (recorder) | `.venv/bin/python3 -m pytest -q backend/tests/open_meteo_forecast_provider_test.py` | ✅ | ✅ green |
| 03-01-T2 | 01 | 1 | D-01 | V5 input validation | An all-null or partially-null variable array raises, never forward-filled (Pitfall 3); malformed-`run` 400 distinguished from unavailable-`run` 400 (Pitfall 4) | unit | same | ✅ | ✅ green |
| 03-01-T3 | 01 | 1 | D-01, D-02 | Silent-null / fail-safe | Calibration gate fails on the unfiltered series and passes only on `hour % 6 == 1`; anchored-pair anchor gap is exactly 1 h; arms 0 and 2 share one index | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_leadtime_calibration_test.py backend/tests/experiment_splits_test.py backend/tests/forecast_experiment_test.py` | ✅ | ✅ green |
| 03-02-T1 | 02 | 1 | D-02 | — | `from_uv(*to_uv(s, d))` round-trips, and `perpendicular_wind` agrees across the full direction circle | unit | `.venv/bin/python3 -m pytest -q backend/tests/wind_vector_test.py` | ✅ | ✅ green |
| 03-02-T2 | 02 | 1 | D-03 | V4 (path traversal) | `ieee738_ampacity` output bit-identical after extraction (`np.array_equal`, not a tolerance); `q_conv_override=None` is a true no-op | unit | `.venv/bin/python3 -m pytest -q backend/tests/thermal_model_test.py` | ✅ | ✅ green |
| 03-02-T3 | 02 | 1 | D-03 | — | `corridor_weakest_link` reproduces `corridor_training_frame`'s pre-refactor output exactly, including the tie-break | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py` | ✅ | ✅ green |

**Waves 2-5 — the D-04 replan**

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-03-T1 | 03 | 2 | D-04 | T-03-03-01/02/04 | Previous-Runs fetch under its own pin (never the legacy model, which live-returns all-null here); suffix-stripped unit-echo check still fires; NO leading-null carve-out | unit (recorder) + live | `.venv/bin/python3 -m pytest -q backend/tests/open_meteo_forecast_provider_test.py` | ✅ extend | ✅ green |
| 03-03-T2 | 03 | 2 | D-04 | T-03-03-05 | The 24-hour offset gate fails on the unfiltered 24-29 h span and passes only on `hour % 6 == 0`; legacy 1-hour gate untouched | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_leadtime_calibration_test.py` | ✅ extend | ✅ green |
| 03-03-T3 | 03 | 2 | D-02, D-04 | T-03-03-06/07 | Anchor gap exactly equals the claimed lead at both leads; cache key includes the lead; test split mechanically locked; live raw-forecast MAE is non-zero | unit + live | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_test.py` | ✅ extend | ✅ green |
| 03-04-T1 | 04 | 3 | D-02, D-04 | T-03-04-01 | Arm 0 equals the truth ampacity at exactly `T-24h`; no one-row-lag production helper in the module | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_test.py` | ✅ extend | ✅ green |
| 03-04-T2 | 04 | 3 | D-02 | T-03-04-02/03/04 | Corridor reduction uses the one extracted weakest-link helper, per column group at its own time; oracle structurally outside `candidates` | unit + live | same | ✅ extend | ✅ green |
| 03-04-T3 | 04 | 3 | D-02 | T-03-04-05 | Identical row index enforced by exception; split ordering asserted on the filtered frame; no-peeking lock self-describing | unit | same | ✅ extend | ✅ green |
| 03-05-T1 | 05 | 3 | D-03 | T-03-05-04/05 | `build_training_matrix`'s default path bit-identical to a pre-edit golden capture; 24-hour target shift asserted from returned index values; no global mutation | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_training_test.py` | ✅ extend | ✅ green |
| 03-05-T2 | 05 | 3 | D-02 | T-03-05-02/03 | Wind correction fitted and recomposed in u/v space; correct across the 0/360 wrap; selector cannot see a test frame | unit | `.venv/bin/python3 -m pytest -q backend/tests/forecast_correction_models_test.py` | ✅ (Wave 0 file landed by Plan 03-05) | ✅ green |
| 03-05-T3 | 05 | 3 | D-02 | T-03-05-01/06 | Cooling correction goes through `q_conv_override`; a non-positive convective term raises rather than being clamped; no second heat-balance implementation | unit | same | ✅ (Wave 0 file landed by Plan 03-05) | ✅ green |
| 03-06-T1 | 06 | 4 | D-02 | T-03-06-01 | The Expectation lands in an isolated two-file commit with the lock flip and no scoring run — auditable from `git log` | doc + git gate | `.venv/bin/python3 -m pytest -q backend/tests/forecast_experiment_test.py` | ✅ extend | ✅ green |
| 03-06-T2 | 06 | 4 | D-02 | T-03-06-02/03 | Leakage probe with demonstrated power: only the oracle responds to a sabotaged truth column, and a known-leaking arm is detected; arm 5 never reaches the persisted artifact or the process-global cache | unit (monkeypatch to raise) | same | ✅ extend | ✅ green |
| 03-06-T3 | 06 | 4 | D-02 | T-03-06-04/06/07 | Seven arms on one held-out index; every margin carries a paired bootstrap interval bracketing its point estimate; oracle outside `candidates` | unit + live (one run) | same | ✅ extend | ✅ green |
| 03-07-T1 | 07 | 5 | D-01, D-02, D-04 | T-03-07-01/02/03 | Expectation byte-identical to its first commit; legacy 1-hour arm labelled non-primary with its bit-identity caveat preceding any score; Limitations covers the diurnal baseline, the oracle ceiling and the filter cost | doc gate | `.venv/bin/python3 -m pytest -q` | ✅ | ✅ green |
| 03-07-T2 | 07 | 5 | — | T-03-07-05/06 | Phase records describe what was executed; zero backend diff from a documentation plan | doc gate | same | ✅ | ✅ green |

*Status: ✅ green · ❌ red · ⚠️ flaky (all task rows above are green; the phase closed with zero pending rows)*

---

## Wave 0 Requirements

**Wave 1 — all closed by Plans 03-01 and 03-02:**

- [x] `backend/tests/open_meteo_forecast_provider_test.py` — created (24 tests), cloning `open_meteo_provider_test.py`'s `_FakeResponse`/`_mock_get` scaffolding
- [x] `backend/tests/wind_vector_test.py` — created (9 tests)
- [x] `backend/tests/experiment_splits_test.py` — created (9 tests)
- [x] `backend/tests/forecast_leadtime_calibration_test.py` — created (10 tests)
- [x] `backend/tests/forecast_experiment_test.py` — created (15 tests)
- [x] `backend/tests/thermal_model_test.py` extended with the exact-equality extraction gate (`np.array_equal`)
- [x] `backend/tests/forecast_training_test.py` extended with the `corridor_weakest_link` equality gate
- [x] Subprocess-isolated no-network-import idiom established (Plan 03-02 corrected the naive in-process form, which failed on shared state during a full-suite run)
- [x] Framework install: **none needed** — pytest 9.0.3 already present and pinned

**Waves 2-5 — closed, all delivered by the D-04 replan:**

- [x] `backend/tests/forecast_correction_models_test.py` — created (Plan 03-05, 21 tests); module-level plain-assert functions, network-free, with the subprocess-isolated import check
- [x] `backend/tests/forecast_training_pre_horizon_param_golden.npz` — golden capture (Plan 03-05), committed in its own commit strictly BEFORE the source edit it gates
- [x] Extended `backend/tests/open_meteo_forecast_provider_test.py` with the Previous-Runs path (Plan 03-03) — 10 new tests (34 total)
- [x] Extended `backend/tests/forecast_leadtime_calibration_test.py` with a clearly separated 24-hour-primary section (Plan 03-03) — 10 new tests (20 total)
- [x] Extended `backend/tests/forecast_experiment_test.py` across Plans 03-03, 03-04 and 03-06 — 14 + 30 + 14 new tests (84 total by phase end)
- [x] Framework install: **none needed** — `scipy` 1.17.1 supplied the paired bootstrap and was already pinned; used live in Plan 03-06's `paired_bootstrap_margin`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Legacy 1-hour lead-time calibration gate's live measurement against the Single-Runs API | D-01 | Requires live network access to two external APIs; the unit suite tests the gate's *logic* with mocked responses, not the real measurement | Run `.venv/bin/python3 backend/forecast_leadtime_calibration.py --days 30` by hand, inspect the per-lead table, confirm the gate fails unfiltered and passes on `hour % 6 == 1`. **Executed in Plan 03-01; transcript in `03-01-SUMMARY.md`.** |
| 24-hour offset-lead stitching cross-check against exact single runs | D-04 | Requires live network access, and the Single-Runs archive for the pinned Previous-Runs model reaches back only a few months — so this is a bounded, hand-run check over recent dates, not a wide historical sampler. Assumption B2's limitation (no direct check possible for 2024-2025) must be recorded in the decision record alongside it. | Run `.venv/bin/python3 backend/forecast_leadtime_calibration.py --previous-runs` by hand (Plan 03-03 Task 2); confirm near-total match rates at offsets 24-29, an unfiltered verdict of FAIL and a filtered verdict of PASS; transcribe into `03-03-SUMMARY.md` |
| Full seven-arm experiment run producing the decision record's numbers | D-02 | Requires a live multi-endpoint fetch plus model fitting, and — critically — the held-out test run is scored **exactly once**, after the Expectation is committed. It is not something to run automatically on any commit. | Run `.venv/bin/python3 backend/forecast_experiment.py --lead-hours 24 --split test` by hand once (Plan 03-06 Task 3), only after the Expectation commit and the leakage probe pass; transcribe results into `docs/data-science/decisions/forecast_correction_experiment.md` per this workstream's hand-transcription precedent. **Executed in Plan 03-06; both corridors scored once, 786 test rows each, no re-run needed; transcript in `03-06-SUMMARY.md` and the decision record's Measured results section.** |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies — every row in both Per-Task
  Verification Map tables above carries an automated command; the two Plan 03-05 rows that were
  `❌ W0` at planning time are now closed by that plan's own `forecast_correction_models_test.py`
  creation.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify — every task row across
  both tables (17 total) carries its own automated command; zero gaps.
- [x] Wave 0 covers all MISSING references — both Wave 0 checklists (Wave 1 and Waves 2-5) are fully
  checked, and no `❌ W0` markers remain in either Per-Task Verification Map table.
- [x] No watch-mode flags — every automated command above is a single, terminating invocation
  (`pytest -q`, or a one-shot `python3` script); none use `--watch` or an equivalent long-running mode.
- [x] Feedback latency < 60s — the unit suite (the latency-gated portion per Sampling Rate above)
  completed within the stated ~30-60 second estimate throughout the phase; live-network steps are
  explicitly out-of-band per this section's own carve-out.
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved — all 17 task rows green, both Wave 0 checklists closed, all three
Manual-Only Verifications executed and transcribed (see `03-01-SUMMARY.md`, `03-03-SUMMARY.md`,
`03-06-SUMMARY.md`), and the full suite's failed count (23, pre-existing `corridor_discretization_test.py`
failures per `.planning/WINDOWS.md`) is unchanged from this phase's own base commit.
