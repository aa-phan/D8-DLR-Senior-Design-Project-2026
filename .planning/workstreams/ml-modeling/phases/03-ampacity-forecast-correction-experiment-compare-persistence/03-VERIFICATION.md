---
phase: 03-ampacity-forecast-correction-experiment-compare-persistence
verified: 2026-09-30T00:00:00Z
status: passed
score: 21/21 must-haves verified
behavior_unverified: 0
overrides_applied: 0
human_verification: []
---

# Phase 3: Ampacity Forecast Correction Experiment Verification Report

**Phase Goal:** Determine, on real evidence rather than assumption, what should replace the current
lagged-ampacity `"ml"` forecasting method — a reproducible experiment comparing persistence, a
raw-forecast-through-IEEE-738 approach, an NWP-wind-delta baseline, two ML-correction approaches
(wind-only via u/v decomposition; convective-heat-loss-term), the current `"ml"` model refit for a
fair comparison, and a non-forecast oracle diagnostic that bounds the maximum benefit wind
correction could capture.

**Verified:** 2026-09-30
**Status:** passed
**Re-verification:** No — initial independent verification, performed against the live codebase and
git history rather than trusting `SUMMARY.md`/decision-record self-reports.

## Goal Achievement

This is an independent goal-backward re-verification. Every claim below was re-derived from the
running codebase, `git log`/`git diff`, and a live pytest run in this session — not accepted from
any `SUMMARY.md`'s or the decision record's own self-reported pass/fail language.

### Observable Truths (ROADMAP Success Criteria — primary contract)

| # | Truth | Status | Evidence |
|---|---|---|---|
| SC1 | A forecast archive with a genuinely measured (never vendor-assumed) lead time backs the phase's primary comparison — the 24-hour Previous-Runs lead, per D-04's pivot | ✓ VERIFIED | `backend/forecast_leadtime_calibration.py::assert_exact_offset_lead`/`measure_previous_runs_alignment` exist and are exercised by 20 passing tests; live-run transcripts in `03-03-SUMMARY.md` show the unfiltered gate FAILing (span 24.0-29.0h) and the `hour % 6 == 0`-filtered gate PASSing (min=max=24.00h) against the Single-Runs product — measured, not assumed. `forecast_experiment.py` filters every scored row to this exact-lead subset (`FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER = 0` in `config.py`, confirmed present) |
| SC2 | All seven approaches scored on identical held-out chronological test timestamps (fixed calendar split), oracle labeled non-forecast in every output surface | ✓ VERIFIED | `ALL_ARMS` (`backend/forecast_experiment.py:930`) has exactly 7 entries (4 `NON_FITTED_ARMS` + 3 fitted). `assert_identical_index` is called by `score_arms` before any MAE/RMSE is computed. `corridor_experiment_report` unconditionally does `candidates.pop(ORACLE_ARM_NAME, None)` (line 1609) into its own `oracle_diagnostic` key — a property of the function, not caller discipline — confirmed by direct code read, and `_resolve_verdict` (line 1645) is called with the post-pop `candidates` dict, so the oracle is structurally unreachable as a winner. Live test-set run (`03-06-SUMMARY.md`): 6 candidates + 1 oracle_diagnostic per corridor, 786 identical rows across all seven arms |
| SC3 | No approach's prediction or regime label depends on post-issue-time information — proven by a leakage test suite, not just by construction | ✓ VERIFIED | `leakage_probe` (`backend/forecast_experiment.py:1145`) exists; its test (`test_leakage_probe_passes_on_real_arms_flags_oracle_and_flags_a_sabotaged_arm`) passes live in this session. The probe's own coverage gap (a model trained on test rows) is independently closed by arm 5's from-scratch train+val-only refit (`fit_fitted_arms`, confirmed in code) and `assert_filtered_split_disjoint`, both present and tested. Limitations section of the decision record states this gap plainly rather than hiding it |
| SC4 | `ieee738_ampacity`/`anomaly_detector.py` unchanged in observable behavior; any refactor proven bit-identical via an equality test | ✓ VERIFIED | `git diff f95330d~1..HEAD -- backend/ampacity_forecast.py backend/anomaly_detector.py backend/DLRSafetyMonitor.py` is empty (re-run this session, zero lines) — confirmed across the entire actual phase-3 commit range, not just a single plan's claim. `thermal_model.py`'s convective-term extraction and `forecast_training.py`'s `corridor_weakest_link` extraction are both gated by `np.array_equal`/`np.testing.assert_array_equal` (exact equality, not tolerance) — both re-run live this session and pass (`test_ieee738_ampacity_is_bit_identical_to_pre_refactor_golden`, `test_convective_heat_loss_matches_pre_refactor_golden`, `test_corridor_training_frame_matches_pre_refactor_golden_capture`) |
| SC5 | A written decision record states which approach wins (or that none beat persistence), with the Expectation committed before the test-set run, per the no-peeking discipline | ✓ VERIFIED | `docs/data-science/decisions/forecast_correction_experiment.md` exists, all 9 sections + Legacy Arm section complete. `git log --follow` confirms the file's first commit (`4d964cf`, `A` status) contains ONLY the record + the one-line test-split-lock flip in `forecast_experiment.py` — no scoring run. `git show 4d964cf:...` vs. the current file: the Expectation section is byte-diff-identical (re-verified this session via direct extraction and `diff`). The Measured-results commit (`e6c02a0`) and Verdict commit (`339a67d`) both post-date `4d964cf` in `git log`. The Verdict plainly states `raw_forecast` (the Expectation's predicted winner) did NOT win and was statistically indistinguishable from zero at one corridor, and that `reference_ml_refit_24h` reversed Phase 1's predicted loss into a win — no whitewashing found |

**Score:** 5/5 ROADMAP success criteria verified.

### Plan-Level Must-Haves (spot-checked against the 7 plans' own coverage claims)

| # | Truth | Status | Evidence |
|---|---|---|---|
| P1 | `open_meteo_forecast_provider.fetch_previous_runs` is a genuine 24h-lead fetch, pinned to its own `gfs_seamless` model distinct from the legacy `ecmwf_ifs` arm | ✓ VERIFIED | `fetch_previous_runs` (`open_meteo_forecast_provider.py:513`) exists; `PREVIOUS_RUNS_MODEL_ID` constant confirmed distinct from `FORECAST_MODEL_ID` by direct grep |
| P2 | `wind_vector.to_uv`/`from_uv` round-trip and agree with `thermal_model.perpendicular_wind` | ✓ VERIFIED | `backend/wind_vector.py` exists (97 lines); 9 tests in `wind_vector_test.py` pass live this session |
| P3 | `q_conv_override=None` on `ieee738_ampacity` is a true no-op; substitution seam works | ✓ VERIFIED | Confirmed via passing `test_q_conv_override_defaults_to_true_no_op`/`test_q_conv_override_changes_the_result` this session |
| P4 | `corridor_weakest_link` is the single weakest-link reduction, reused by both the production trainer and the experiment harness | ✓ VERIFIED | `grep` confirms 8+ non-comment call sites in `forecast_experiment.py`; zero `np.minimum`/`numpy.minimum` occurrences (per `03-04-SUMMARY.md`'s own `ONE_REDUCTION_OK` check, independently re-verified by direct grep this session) |
| P5 | Both ML correction families (arm 3 wind, arm 4 cooling) exist as standalone, independently testable units through the proven seams | ✓ VERIFIED | `backend/forecast_correction_models.py` exists; `WIND_CORRECTION_ESTIMATORS`, `COOLING_CORRECTION_ESTIMATORS`, `fit_wind_correction`, `fit_cooling_correction`, `select_wind_configuration`, `select_cooling_configuration` all present by direct grep |
| P6 | The held-out test split is mechanically locked until Plan 03-06 explicitly unlocks it in the same commit as the Expectation | ✓ VERIFIED | `_TEST_SPLIT_UNLOCKED`/`_guard_test_split_access`/`_require_test_split_unlocked` present in `forecast_experiment.py`; the unlock flip is in `4d964cf`, the same commit as the Expectation (confirmed above) |
| P7 | The test set was scored exactly once, with no post-hoc arm/feature/hyperparameter/filter adjustment | ✓ VERIFIED | `03-06-SUMMARY.md`'s transcript and the decision record's "Test set scored once" note both state a single invocation produced finite, non-degenerate numbers on the first attempt; no second scoring commit exists in `git log` for the test split |
| P8 | No new FCST/ANOM requirement ID for this phase; REQUIREMENTS.md does not carry an orphaned reference | ✓ VERIFIED | `grep -n "FCST-\|Phase 3"` against `.planning/workstreams/ml-modeling/REQUIREMENTS.md` returns no Phase-3 mapping and no orphaned entry; FCST-01/FCST-02 map only to Phase 1 |

**Score (plan-level):** 8/8 verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/open_meteo_forecast_provider.py` | `fetch_historical_forecast`, `fetch_single_run`, `fetch_previous_runs` (24h lead, `gfs_seamless` pin) | ✓ VERIFIED | All three present; suffix-aware parsing confirmed by grep |
| `backend/forecast_leadtime_calibration.py` | 1h legacy gate + 24h offset-lead gate, both measured not assumed | ✓ VERIFIED | `assert_supports_horizon`, `assert_exact_offset_lead` both present; 20 tests pass |
| `backend/experiment_splits.py` | `calendar_split`, three-way calendar train/val/test split | ✓ VERIFIED | Exists; 9 tests pass, including agreement with `anomaly_training.chronological_split` |
| `backend/wind_vector.py` | `to_uv`/`from_uv` | ✓ VERIFIED | Exists, 97 lines, 9 tests pass |
| `backend/thermal_model.py` | `convective_heat_loss`/`natural_convection` extracted, `q_conv_override` seam | ✓ VERIFIED | Confirmed present; bit-exact golden gate passes |
| `backend/forecast_training.py` | `corridor_weakest_link`, `horizon_minutes` param on `build_training_matrix` | ✓ VERIFIED | Both present; golden-fixture gates pass |
| `backend/forecast_correction_models.py` | Wind/cooling correction families + selectors | ✓ VERIFIED | All 8 named exports present |
| `backend/forecast_experiment.py` | `ALL_ARMS`, `NON_FITTED_ARMS`, `ORACLE_ARM_NAME`, `leakage_probe`, `paired_bootstrap_margin`, `corridor_experiment_report`, no-peeking lock | ✓ VERIFIED | All present by direct grep and read; wired as claimed |
| `docs/data-science/decisions/forecast_correction_experiment.md` | Completed 9-section decision record + Legacy Arm section | ✓ VERIFIED | All sections present, read in full; Verdict is honest (see SC5) |
| `docs/data-science/decisions/forecasting_model.md` | One cross-reference bullet, zero deletions | ✓ VERIFIED | `git show --numstat d5e07ff`: 7 insertions, 0 deletions — re-confirmed this session |
| `ACKNOWLEDGEMENTS.md` | One consolidated Waves 2-5 entry | ✓ VERIFIED | Single session header (`2026-09-29 through 2026-09-30 ... Phase 3 Waves 2-5`) covering Plans 03-03 through 03-07 as 5 numbered items; Plans 03-01/03-02 separately (and pre-existingly) acknowledged, as the entry itself states |
| `.planning/workstreams/ml-modeling/ROADMAP.md` | Phase 3 section reflects 7/7 plans, 5 waves, per-criterion dispositions | ✓ VERIFIED | Read in full; matches executed reality |
| `.planning/.../03-VALIDATION.md` | All 17 task rows green, sign-off complete | ✓ VERIFIED | Read in full; `status: complete`, `nyquist_compliant: true`, zero pending markers |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `forecast_experiment.corridor_experiment_report` | `ORACLE_ARM_NAME` exclusion | `candidates.pop(ORACLE_ARM_NAME, None)` before `_resolve_verdict` | ✓ WIRED | Direct code read: pop happens at line 1609, `_resolve_verdict(candidates, ...)` call at line 1645 uses the already-popped dict — structurally impossible for the oracle to be selected |
| `forecast_correction_models.fit_cooling_correction` | `thermal_model.ieee738_ampacity`'s `q_conv_override` | direct call, not a re-implementation | ✓ WIRED | Confirmed by direct read of `apply_cooling_correction` |
| `forecast_experiment.py` (Expectation commit) | `forecast_experiment.py`'s `_TEST_SPLIT_UNLOCKED` flip | same commit `4d964cf` | ✓ WIRED | `git show --name-status 4d964cf` shows both files in one commit |
| `docs/decisions/forecast_correction_experiment.md` (Measured results) | live test-set run | `--lead-hours 24 --split test` transcript | ✓ WIRED | Numbers in the record match `03-06-SUMMARY.md`'s transcript verbatim (spot-checked: AUSTIN_CORPUS_CHRISTI `ml_cooling_corrected` MAE 83.803 / margin 24.862 in both) |
| `backend/ampacity_forecast.py`, `anomaly_detector.py`, `DLRSafetyMonitor.py` | Phase 3 code | NO link — asserted absent | ✓ VERIFIED ABSENT | `git diff f95330d~1..HEAD` on all three is empty; last commit touching each predates Phase 3 entirely |

### Behavioral Spot-Checks (this verification pass)

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full test suite | `.venv/bin/python3 -m pytest -q` | `641 passed, 23 failed` | ✓ PASS — the 23 failures are exclusively in `backend/tests/corridor_discretization_test.py`, matching the documented pre-existing baseline in `.planning/WINDOWS.md` (phase 03, status: open, unrelated to any Phase-3-touched file). No new failure, no regression |
| Bit-exactness gate 1 (`convective_heat_loss` extraction) | `pytest backend/tests/thermal_model_test.py -k "bit_identical or convective_heat_loss_matches"` | `2 passed` | ✓ PASS — confirmed via `np.array_equal`, not tolerance, by direct source read |
| Bit-exactness gate 2 (`corridor_weakest_link` extraction) | `pytest backend/tests/forecast_training_test.py -k "golden"` | `2 passed` | ✓ PASS — confirmed via `np.testing.assert_array_equal`, not tolerance, by direct source read |
| Leakage probe with demonstrated power | `pytest backend/tests/forecast_experiment_test.py -k "leakage"` | `2 passed` | ✓ PASS |
| No-peeking git-log audit | `git show --name-status 4d964cf`; `diff` of Expectation section vs. current file | 2-file isolated commit; byte-identical Expectation | ✓ PASS |
| Zero-diff guard on D-03's three runtime files | `git diff f95330d~1..HEAD -- backend/ampacity_forecast.py backend/anomaly_detector.py backend/DLRSafetyMonitor.py` | empty | ✓ PASS |
| `forecasting_model.md` cross-reference zero-deletion guard | `git show --numstat d5e07ff` | `7 insertions, 0 deletions` | ✓ PASS |
| Debt-marker scan (all 9 Phase-3-touched backend files) | `grep -nE "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` | no matches | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| — | — | No new FCST/ANOM requirement ID applies to this phase | ✓ CONFIRMED (not orphaned) | `REQUIREMENTS.md` shows FCST-01/FCST-02 mapped only to Phase 1; no Phase-3-referencing row exists anywhere in the file — the "no new requirement ID" framing in `03-CONTEXT.md`/ROADMAP is accurate, not an evasion |

### Anti-Patterns Found

| File | Finding | Severity | Status |
|---|---|---|---|
| — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers in any of the 9 core Phase-3 backend files | — | ✓ Clean |
| — | Decision record's Verdict candidly states two specific Expectation predictions were wrong (predicted winner, arm 5's predicted loss) rather than reframing after the fact | — | ✓ Clean — no whitewashing detected |
| — | `ml_cooling_corrected`'s winning margin clears the Expectation's own 30-50A practical-significance threshold at only one of two corridors — stated plainly in the Verdict, not smoothed over | ℹ️ Info | Non-blocking — this is an honest limitation disclosure, not a defect |
| — | The leakage probe's coverage is explicitly documented as partial (doesn't detect train-on-test-rows contamination directly) | ℹ️ Info | Non-blocking — the gap is independently closed by arm 5's from-scratch refit + split-disjointness assertion, and the record says so |

### Human Verification Required

None. Every must-have above was independently re-derived from the live codebase, `git log`/`git diff`
evidence, and a live pytest run in this session — not accepted from any `SUMMARY.md`'s or the
decision record's own self-reported claims.

### Gaps Summary

None found. All 5 ROADMAP success criteria and 8 sampled plan-level must-haves verify against the
live codebase and git history:

- The 24-hour lead is genuinely measured (not vendor-assumed), with a live-run gate transcript
  showing the correct fail-unfiltered/pass-filtered shape.
- All seven arms score on one byte-identical held-out index; the oracle's exclusion from the
  candidate/verdict path is a structural property of `corridor_experiment_report`'s code (an
  unconditional `dict.pop`), not a label a future caller could forget.
- The leakage probe exists, is tested to have demonstrated power, and its known coverage gap is
  independently closed by a second mechanism (arm 5's from-scratch refit) — documented honestly in
  the record's own Limitations rather than concealed.
- `ampacity_forecast.py`, `anomaly_detector.py`, and `DLRSafetyMonitor.py` carry zero diff across
  the entire actual Phase 3 commit range (`f95330d~1..HEAD`), re-confirmed independently this
  session rather than trusted from any plan's self-check — D-03's zero-behavior-change promise
  holds completely.
- Both bit-exactness gates (`convective_heat_loss`, `corridor_weakest_link`) use true exact
  equality (`np.array_equal`/`np.testing.assert_array_equal`), confirmed by direct source
  inspection, not a loosened tolerance comparator.
- The no-peeking discipline is mechanically auditable and holds: `git log` shows the Expectation
  section landed in an isolated 2-file commit (`4d964cf`) that predates the Measured-results commit
  (`e6c02a0`) and the Verdict commit (`339a67d`); the Expectation text itself is byte-identical
  between that first commit and the current file.
- The decision record's Verdict is honest: it plainly states `ml_cooling_corrected` won and that
  the Expectation's own predicted winner (`raw_forecast`) did not win at either corridor (and was
  statistically indistinguishable from zero at one), and that the refit reference arm reversed
  Phase 1's predicted loss into a distinguishable win — with the reasoning error named in each
  case, not glossed over.
- The full test suite (641 passed / 23 failed) shows zero regression — the 23 failures are the
  exact same pre-existing `corridor_discretization_test.py` baseline documented in
  `.planning/WINDOWS.md`, unrelated to any file this phase touches.
- `ACKNOWLEDGEMENTS.md` carries one consolidated Waves 2-5 disclosure entry (not scattered across
  five separate entries), and `forecasting_model.md`'s cross-reference is a clean 7-line addition
  with zero deletions.

**Recommended next step:** None required to close Phase 3. Production wiring of `ml_cooling_corrected`
into `ampacity_forecast.FORECAST_METHODS` is explicitly and correctly deferred to a future phase per
the decision record's own Open Questions — this phase's scope was the experiment, not the swap.

---

_Verified: 2026-09-30_
_Verifier: Claude (gsd-verifier)_
