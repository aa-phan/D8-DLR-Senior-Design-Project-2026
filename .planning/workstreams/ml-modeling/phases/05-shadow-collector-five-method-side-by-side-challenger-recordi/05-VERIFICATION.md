---
phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
verified: 2026-10-08T00:40:34Z
status: passed
score: 11/11 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 5: Shadow Collector — Five-Method Side-by-Side Challenger Recording Verification Report

**Phase Goal:** Extend the existing, inert shadow collector to record all five of Phase 3/4's real
(non-oracle) 24-hour-lead candidates side by side every cycle — `ml_wind_corrected`,
`ml_cooling_corrected`, `reference_ml_refit_24h`, `raw_forecast`, `persistence_24h` — from the same
shared inputs, keeping `ml_wind_corrected` as the provisional production default and declaring no
winner. Production (`dlr_pipeline.py`) remains unchanged.

**Verified:** 2026-10-08
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (D-01 through D-11, 05-CONTEXT.md locked scope)

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | D-01: All five real candidates attempted every cycle from one shared input set; `ml_wind_corrected` stays provisional default; no winner declared | ✓ VERIFIED | `backend/forecast_shadow_demo.py::run_once_all_methods` (lines 192-335) attempts all five names in `shadow.CANDIDATE_METHOD_NAMES`; `log_cycle_predictions`'s mirror hardcodes `"method": "ml_wind_corrected"` (pipeline.py:1577); no comparative/winner language found in code or docs for this phase. |
| 2 | D-02: One shared-input fetch per cycle; aligned timing/horizon/endpoints across all five | ✓ VERIFIED | `fetch_shared_corridor_inputs` (pipeline.py:590-639) fetches each endpoint city's forecast+anchor exactly once; `run_once_all_methods` calls it exactly once per invocation and reuses `shared[c]` for every per-city-reduced candidate; a candidate whose alignment can't be guaranteed is marked unavailable, never computed from a different snapshot. |
| 3 | D-03: `reference_ml_refit_24h` uses the 24h refit MLP, never `ampacity_forecast`'s 60-min production artifact/cache | ✓ VERIFIED | `backend/forecast_shadow_fit_reference_refit.py` calls `forecast_experiment._arm5_truth_frame` → `forecast_training.build_training_matrix(horizon_minutes=1440)` → `fit_corridor_model`; never calls `forecast_training.persist_corridor_model` or `ampacity_forecast._load_corridor_model`; two real artifacts committed (see Required Artifacts). |
| 4 | D-04: Per-candidate feature validation; unavailable is honest and never silently substituted | ✓ VERIFIED | `run_once_all_methods` checks `shared[c].forecast_frame is None` / `.anchor is None` per candidate before computing, records `status="unavailable"` with a named reason, and `continue`s independently per candidate — no candidate's name is ever attached to another's computed value. |
| 5 | D-05: `persistence_24h` reads a decision-time-available prior entry, matched on `valid_time`, never the positionally-last line, never hindsight-reconstructed | ✓ VERIFIED | `Persistence24hShadowMethod.compute` (pipeline.py:1046-1126) scans the corridor's own JSONL, computing `abs(entry_valid_time - decision_ts)` and keeping the minimum within a 90-minute tolerance — not `readlines()[-1]`. Cold start (no match) returns `status="unavailable"` honestly, never backfilled. |
| 6 | D-06: Every existing field preserved per candidate, independently; provider-fallback vs. method-fallback distinction stays per-candidate | ✓ VERIFIED | `log_cycle_predictions` (pipeline.py:1528-1587) writes `schema_version:2` with all five `CANDIDATE_METHOD_NAMES` each carrying its own 7-key record (`status`, `ampacity_amps`, `fallback_used`, `fallback_reason`, `model_version`, `input_provenance`, `reason`) plus the exact 05-01-approved six-field top-level mirror of `candidates["ml_wind_corrected"]` — confirmed byte-for-byte against the approved schema in 05-01-SUMMARY.md. |
| 7 | D-07: One candidate's real failure never blocks the other four; append-only storage preserved | ✓ VERIFIED | `run_once_all_methods` uses five SEPARATE try/except blocks (one per `PER_CITY_REDUCED_METHOD_NAMES` iteration, plus two standalone blocks for `persistence_24h`/`reference_ml_refit_24h`) — no shared block around a loop. `log_cycle_predictions`/`log_prediction` both open with mode `"a"` (append), never `"w"`. |
| 8 | D-08: Runbook documents when five-method collection started and its relationship to the Nov 1/Nov 24 protocol | ✓ VERIFIED | `docs/data-science/decisions/shadow_collection_runbook.md` lines 11-38: dated "2026-10-07," names all five candidates, quotes `forecast_correction_followup_audit.md`'s mechanical-health-check carve-out verbatim, states this data is independent/not a substitute for the Nov 1/Nov 24 protocol. |
| 9 | D-09: No silent protocol changes; no outcome inspection of any FRESH row before 2026-11-24T00:00:00 UTC | ✓ VERIFIED | `git diff --stat 1d3f0e4 -- docs/data-science/decisions/forecast_correction_followup_audit.md` empty (zero diff). Grep of all new shadow-module code for `fresh`/`reanalysis`/`truth_col`/`ground_truth` finds only docstring/comment mentions of the reanalysis-basis *caveat* and the module's own non-"fresh"-row health-check discipline — no code path reads a reanalysis/truth column to score a prediction. |
| 10 | D-10: Targeted tests + one live cycle + confirmation that the next SCHEDULED (cron) run persists the five-candidate shape | ✓ VERIFIED | 100/100 targeted tests pass (see Probe Execution). Live cycles for both corridors confirmed in 05-02/05-03/05-04 SUMMARYs. **Independently re-confirmed by this verification** (beyond what 05-05-SUMMARY.md could claim at its own write time): `gh run list` shows a `schedule`-event run (databaseId `37696861670`, completed success, created `2026-10-07T22:32:46Z`) *after* the manual-dispatch run 05-05 cited; `git fetch origin shadow-collection-data` shows commit `243acf8` (`2026-10-07T22:33:49+00:00`) whose `AUSTIN_CORPUS_CHRISTI.jsonl` last line is `schema_version:2` with all five candidate names present. The next-scheduled-run confirmation D-10 required has now genuinely happened, not merely been scheduled to happen. |
| 11 | D-11: Report operational completeness only, never accuracy/reliability/comparative claims; production unchanged | ✓ VERIFIED | All five SUMMARY.md files frame results strictly as "ran end to end / physically plausible / honest unavailable reason," explicitly deferring any accuracy comparison to the Nov 1/Nov 24 protocol. `dlr_pipeline.py` carries zero diff and zero reference to any shadow module (see Key Link Verification). |

**Score:** 11/11 truths verified (0 present-but-behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/forecast_shadow_demo.py::run_once_all_methods` | Computes/attempts all five candidates per cycle, five separate try/except | ✓ VERIFIED | Read directly (lines 192-335); confirmed five-name loop + two standalone candidate blocks, each independently caught. |
| `backend/forecast_shadow_collect.py::collect_once` | Calls `run_once_all_methods` for every corridor | ✓ VERIFIED | Line 103: `forecast_shadow_demo.run_once_all_methods(corridor)` inside the `for i, corridor in enumerate(config.CORRIDOR_ENDPOINTS)` loop; the old `run_once(corridor, "ml_wind_corrected")` literal is gone (grep confirms absence). |
| `backend/forecast_shadow_pipeline.py::log_cycle_predictions` | Writes approved `schema_version:2` nested shape + six-field legacy mirror | ✓ VERIFIED | Lines 1528-1587, matches 05-01-SUMMARY.md's approved shape exactly, including the mirror being computed from `candidate_records["ml_wind_corrected"]`, not re-derived. |
| `Persistence24hShadowMethod` | Matches on `valid_time`, never the last line | ✓ VERIFIED | Lines 1025-1126; iterates every line, computes a timestamp delta, keeps the closest within tolerance — no `[-1]` indexing anywhere in the class. |
| `ReferenceRefit24hShadowMethod` + persisted artifacts | Real artifact for both corridors, real predict path | ✓ VERIFIED | `data/shadow/models/reference_ml_refit_24h_AUSTIN_CORPUS_CHRISTI.joblib` (44,097 bytes) and `..._MIDLAND_EL_PASO.joblib` (41,489 bytes) exist, are git-tracked (`git ls-files` confirms both), and `ReferenceRefit24hShadowMethod.compute` (pipeline.py:1346-1393) loads + predicts from `fetch_live_truth_proxy_series`'s live window — no `fit`/`train` call anywhere in `compute`. |
| `backend/forecast_shadow_render_table.py` | Handles both old flat shape and new nested shape without crashing | ✓ VERIFIED | `render_markdown` branches per-line on `entry.get("schema_version", 1) >= 2` (line 191); `_render_legacy_row` for old shape, `_render_new_shape_block` for new shape; both paths read directly, no crash-prone assumptions (missing keys default via `.get(...) or {}`/`"—"`). |
| `docs/data-science/decisions/shadow_collection_runbook.md` | Documents D-08 start date and Nov 1/Nov 24 relationship | ✓ VERIFIED | Lines 11-38, see Truth 8 above. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `forecast_shadow_collect.py::collect_once` | `forecast_shadow_demo.py::run_once_all_methods` | direct call inside per-corridor loop | ✓ WIRED | Confirmed by direct read; all 5 collect-test monkeypatches now target `run_once_all_methods`. |
| `forecast_shadow_demo.py::run_once_all_methods` | `forecast_shadow_pipeline.py::log_cycle_predictions` | one call per cycle with all five results | ✓ WIRED | Line 328: `shadow.log_cycle_predictions(corridor, results, timestamps)`, called exactly once after all five candidates are computed. |
| `backend/dlr_pipeline.py` | any shadow module | (must be absent) | ✓ CONFIRMED ABSENT | `grep -i shadow backend/dlr_pipeline.py` returns zero matches; `git diff --stat 1d3f0e4 -- backend/dlr_pipeline.py` is empty. Production remains genuinely unwired from this phase's work. |
| `ReferenceRefit24hShadowMethod` | `fetch_live_truth_proxy_series` | decision-time-available live truth-proxy window, never reanalysis/archive | ✓ WIRED | `compute` calls `fetch_live_truth_proxy_series(corridor, anchor_time)` (line 1357), which itself fetches live `weather_provider.fetch_weather(..., provider="tceq")` windows — no Archive API call anywhere in this path. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `candidates.ml_wind_corrected/.ml_cooling_corrected/.raw_forecast` | `dlr_amps` from `_corridor_reduce_per_city` | live Open-Meteo forecast + live TCEQ/Synoptic anchor, through `thermal_model.ieee738_ampacity` | Yes | ✓ FLOWING (confirmed against real logged values: e.g. `ml_wind_corrected=1069.34A` in the latest `shadow-collection-data` commit) |
| `candidates.persistence_24h` | `raw_candidate.get("ampacity_amps")` | this collector's own prior `raw_forecast` entry, matched on `valid_time` | Yes (or honest `unavailable`) | ✓ FLOWING (currently `unavailable` — cold start, expected; the code path is real, not a static stub) |
| `candidates.reference_ml_refit_24h` | `estimator.predict(last_row)` | persisted MLP artifact + live truth-proxy series | Yes (or honest `unavailable`) | ✓ FLOWING (currently `unavailable` in the latest real cycle due to a live TCEQ `solar_radiation` gap — an honestly-reported live-data limitation, not a stub) |

### Behavioral Spot-Checks / Probe Execution

| Probe | Command | Result | Status |
|---|---|---|---|
| Targeted phase test suite | `.venv/bin/python3 -m pytest -q backend/tests/forecast_shadow_pipeline_test.py backend/tests/forecast_shadow_demo_test.py backend/tests/forecast_shadow_collect_test.py backend/tests/forecast_shadow_fit_reference_refit_test.py backend/tests/forecast_shadow_render_table_test.py backend/tests/forecast_shadow_healthcheck_test.py` | `100 passed in 4.23s` | ✓ PASS |
| Next-scheduled-run confirmation (D-10's own remaining item) | `gh run list --workflow="Shadow Collection" ...` + `git fetch origin shadow-collection-data` + direct JSONL parse | `schedule` event run `37696861670` succeeded 2026-10-07T22:32:46Z; commit `243acf8` on `shadow-collection-data` carries `schema_version:2` with all five candidates | ✓ PASS |
| Frozen-module zero-diff | `git diff --stat 1d3f0e4 -- backend/forecast_experiment.py backend/forecast_correction_models.py backend/forecast_training.py backend/thermal_model.py backend/ampacity_forecast.py backend/anomaly_detector.py backend/DLRSafetyMonitor.py backend/dlr_pipeline.py docs/data-science/decisions/forecast_correction_followup_audit.md docs/data-science/decisions/forecast_correction_experiment.md` | empty output (no changes) | ✓ PASS |

### Requirements Coverage

This phase declares no formal requirement IDs (mirrors Phase 3/4's own convention). The eleven
locked decisions D-01 through D-11 substitute for requirement IDs — all eleven are SATISFIED per
the Observable Truths table above. No orphaned requirements found.

### Anti-Patterns Found

No blocker-level anti-patterns found in files modified by this phase.

- `grep -n -E "TBD|FIXME|XXX|TODO|HACK|PLACEHOLDER"` on all six modified/created shadow-module
  source files: zero matches.
- No empty-return stubs (`return None`/`return {}`/`return []`) found masquerading as real
  implementations — every "unavailable"/"failed" path explicitly constructs a `ShadowPrediction`
  with a named `reason`, never a bare empty value.
- The 23 pre-existing `corridor_discretization_test.py` failures (logged in `deferred-items.md`)
  match the already-documented Phase 3/4 baseline exactly — not a regression introduced by this
  phase, confirmed by `git log -- backend/corridor_discretization.py` showing no phase-5 commit
  touching that file.

### Human Verification Required

None. Every must-have in this phase resolves to code-grounded, test-verified, or directly
re-executed (git/gh) evidence — no visual, UX, or subjective judgment call remains open.

### Gaps Summary

No gaps found. All eleven locked decisions (D-01 through D-11) are genuinely delivered:

- All five candidates are computed from one shared per-cycle fetch, each independently validated,
  isolated on failure, and logged in the approved `schema_version:2` nested shape with the exact
  six-field legacy mirror.
- `persistence_24h` and `reference_ml_refit_24h` are both real, decision-time-available
  implementations — not stubs — and both correctly report honest `unavailable` reasons on the
  actual live data gaps encountered (cold start; a TCEQ CAMS `solar_radiation` gap), which is
  expected behavior per the plans' own stated preconditions, not a defect.
- Every frozen Phase 3/4 production module, `dlr_pipeline.py`, and both frozen decision docs carry
  zero diff against the pre-phase baseline (`1d3f0e4`); `dlr_pipeline.py` has zero textual
  reference to any shadow module.
- D-10's own hardest remaining item — confirmation that the *next scheduled* (cron-triggered, not
  manual) GitHub Actions run persists the five-candidate shape — had NOT happened as of
  05-05-SUMMARY.md's own writing (it said so honestly). This verification, run later, independently
  confirms it has since happened for real: a `schedule`-event workflow run completed successfully
  and its commit to `shadow-collection-data` carries the full five-candidate `schema_version:2`
  shape. This closes what was the phase's only outstanding, honestly-flagged item — not a gap to
  report, but worth recording that it closed between 05-05's completion and this verification pass.
- No code anywhere in the new shadow-module surface reads a reanalysis/truth column to score a
  prediction against ground truth (D-09); the Nov 1/Nov 24 protocol's own frozen files are
  untouched.

---

_Verified: 2026-10-08_
_Verifier: Claude (gsd-verifier)_
