---
phase: 02-anomaly-detection-model
verified: 2026-09-26T23:59:00Z
status: gaps_found
score: 17/18 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "A single machine-readable report at config.ANOMALY_ML_VALIDATION_REPORT_NAME holds every number Plan 02-04's validation record transcribes, keyed by corridor, candidate and contamination... so a shortened run is visible in the evidence rather than hidden behind a score (02-02-PLAN.md must_haves)"
    status: failed
    reason: >
      Confirmed by live reproduction: `_run_validate` and `_run_bakeoff` in
      backend/anomaly_training.py both initialize `reports = {}` as a fresh, empty dict scoped
      only to the corridors passed to that invocation, then unconditionally `json.dump` it over
      `data/models/anomaly_validation_report.json` with no read-merge step first. Running
      `backend/anomaly_training.py --bakeoff --years 1` (both corridors, 2 keys in the report)
      followed by `backend/anomaly_training.py --bakeoff --years 1 --corridor MIDLAND_EL_PASO`
      (single corridor) leaves the report file containing ONLY `MIDLAND_EL_PASO` --
      `AUSTIN_CORPUS_CHRISTI`'s entire measurement history (all candidate x contamination
      numbers, selected winner, ceiling-met flag) is silently deleted, with no warning and no
      diff visible to the operator beyond the file shrinking. This is the opposite of "a
      shortened run is visible in the evidence" -- it is a shortened run *replacing* the evidence
      silently. It also directly contradicts the phase's own threat register entry T-02-09, whose
      stated mitigation is exactly this visibility guarantee. `docs/data-science/decisions/
      anomaly_detection_model.md` is a direct transcription of this JSON file, so any future
      single-corridor retrain-and-refresh workflow (e.g. after a data update) performed between
      validation-record updates would corrupt the source-of-truth evidence without any error
      surfacing. This was independently confirmed during this verification pass (not merely
      trusted from 02-REVIEW.md's CR-01 finding) and the report was restored to its full
      two-corridor state afterward so no residual repository state was altered.
    artifacts:
      - path: "backend/anomaly_training.py"
        issue: "_run_validate (~line 591) and _run_bakeoff (~line 878) build `reports = {}` fresh and never load the existing report file before overwriting it, so any corridor absent from the current invocation's corridor list is silently dropped from the persisted report"
    missing:
      - "Load the existing anomaly_validation_report.json (if present) before populating `reports`, merge only the corridors actually processed in this invocation into it, then write -- mirroring the fix already proposed in 02-REVIEW.md's CR-01"
      - "Apply the identical fix to any other report-writing entry point in anomaly_training.py that scopes to a corridor subset (--validate)"
human_verification: []
---

# Phase 2: Anomaly Detection Model Verification Report

**Phase Goal:** The G6 safety gate can be backed by an actual model trained on historical
per-variable baselines (wind, temp, solar, load) instead of only the rolling mean±k·std /
forecast-residual heuristics, with the fail-safe contract intact, and that model's
false-positive/false-negative behavior is proven against real historical data.

**Verified:** 2026-09-26
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria — primary contract)

| # | Truth | Status | Evidence |
|---|---|---|---|
| SC1 | `AnomalyDetector.check(raw_data, rating)` — any construction path — still returns the same `(bool, str)` tuple shape; `DLRSafetyMonitor` requires zero changes | ✓ VERIFIED | `inspect.signature(AnomalyDetector.check)` confirms params `['self','raw_data','rating']` unchanged; `git diff HEAD~30 -- backend/DLRSafetyMonitor.py` is empty; `git status --porcelain backend docs` clean at verification time |
| SC2 | At least one decision path is backed by an actual model trained on historical per-variable baselines (wind, temp, solar, load) | ✓ VERIFIED | Live re-run of `backend/anomaly_training.py --corridor AUSTIN_CORPUS_CHRISTI --years 1` against the real Open-Meteo Archive API produced a real fitted `OneClassSVM`; `AnomalyDetector.for_corridor(...)` loaded it (`model is not None`, `model_source` matches the persisted path) and `check()` returned a real `(False, "model judged reading ... within the learned per-variable envelope ...")` verdict with `signal == "model_clean"` on a real historical row. Load (the fourth named variable) is discharged via `characterize_load` at training time only (see SC4/D-02 below) |
| SC3 | A trained-model failure still resolves to the corridor's static rating via G6's existing `_fallback` handling | ✓ VERIFIED | Ran the named tests directly: `test_model_failure_resolves_to_static_rating` and `test_model_exception_propagates_out_of_check` both pass (`14 passed` for the full fail-safe/OR-combination named-test set). Confirmed no exception handler exists anywhere in `anomaly_detector.py` (`grep -nE '^[[:space:]]*(try:|except )'` finds nothing) so a raising model has no local catch to short-circuit G6 |
| SC4 | The trained model is evaluated against real historical data (Open-Meteo backfill + real ERCOT load), not synthetic fixtures, for FP/FN trip rate vs. the existing baseline on the same data | ✓ VERIFIED | Live re-run of `--bakeoff --years 1` (both corridors, real Open-Meteo data) and `--characterize-load` (real ERCOT `gridstatus` client) reproduced the exact same winners/contaminations/correlations already recorded in 02-02/02-03-SUMMARY.md and the validation record — genuine reproducibility confirmed, not merely trusted. The rolling baseline is scored through the real `_check_against_rolling_baseline` branch (`load_model=False`), not a re-implementation |
| SC5 | A written validation record documents the FP/FN measurement and states whether the model met expectations | ✓ VERIFIED | `docs/data-science/decisions/anomaly_detection_model.md` exists, tracked, `## Expectation` (line 164) precedes `## Verdict` (line 270); an independent transcription check (re-run, not trusted from SUMMARY) confirms every selected-winner rate and every measured candidate name appears verbatim in the doc, matching the freshly-regenerated `anomaly_validation_report.json` |

**Score:** 5/5 ROADMAP success criteria verified.

### Plan-Level Must-Haves (selected, representing the phase's own stated risk surface)

| # | Truth (paraphrased) | Status | Evidence |
|---|---|---|---|
| P1 | Model branch judges raw wind/temp/solar, never derived rating; feature/raw-key tuples contain no `hour`/`load`/`dlr_amps`/`rating` | ✓ VERIFIED | `config.ANOMALY_ML_FEATURE_COLUMNS == ('air_temp','wind_speed','solar_radiation')`, `ANOMALY_ML_RAW_DATA_KEYS == ('temp','wind','solar')`, both length 3, no forbidden substrings — confirmed live |
| P2 | Additive OR-combination; model can only add a trip, never suppress one | ✓ VERIFIED | `test_model_cannot_suppress_existing_trip` / `test_model_can_trip_on_its_own` pass |
| P3 | No exception handler, no imputation call, no `DLRSafetyMonitor` import anywhere in `anomaly_detector.py`; `import anomaly_detector` pulls in neither `sklearn` nor `joblib` | ✓ VERIFIED | All four grep/import guards re-run live, all pass |
| P4 | Model artifact path built only from closed `CORRIDOR_ENDPOINTS` set, atomic persistence (tempfile + `os.replace`) | ✓ VERIFIED | Code inspected; `persist_corridor_model` uses tempfile+`os.replace`; `_model_path_for` validates against `CORRIDOR_ENDPOINTS` before any path join |
| P5 | Both corridors trained/scored/persisted independently; both artifacts loadable | ✓ VERIFIED | Live `--bakeoff --years 1` produced both `.joblib` files; both load with non-`None` model via `for_corridor` |
| P6 | D-03: all three candidates (IsolationForest, EllipticEnvelope, OneClassSVM) measured across the same contamination grid; losers' numbers retained, never dropped | ✓ VERIFIED | Live regenerated report has 15 measurements per corridor (3×5), losers (`EllipticEnvelope`, low-contamination `IsolationForest`) present alongside the winner |
| P7 | Winner selected by single deterministic rule, never architecture preference; `select_winner` refuses on missing/non-finite measurement | ✓ VERIFIED (via test) | `test_select_winner_*` suite (7 named tests) passes, covering the eligible-pick, fallback, tie-break, and refusal paths |
| P8 | A single machine-readable validation report holds every number, "so a shortened run is visible in the evidence rather than hidden behind a score" | ✗ **FAILED** | See Gaps — CR-01, confirmed by live reproduction: a corridor-scoped re-run silently deletes other corridors' evidence instead of making the scope change visible |
| P9 | Injection never mutates the real assembled frame; clean/injected denominators disjoint | ✓ VERIFIED (via test) | `test_inject_anomalies_*` non-mutation and disjoint-denominator tests pass |
| P10 | `backend/anomaly_detector.py` unchanged by Plans 02-02/02-03/02-04 (measurement/docs plans touch no runtime code) | ✓ VERIFIED | `git diff HEAD -- backend/anomaly_detector.py` empty at verification time; each plan's own `DETECTOR_UNTOUCHED`/`NO_CODE_CHANGED` gates independently re-run and pass |
| P11 | D-02: load characterized at training time only; `anomaly_detector.py` never imports `ercot_data_retriever`/`gridstatus`; no `load` name in either feature tuple; `check()` still works on wind/temp/solar-only `raw_data` | ✓ VERIFIED | `test_load_is_training_time_only_and_never_reaches_check` passes; `grep` confirms no import; live `characterize_load` run produced distinct zone matches per corridor (`South`/`South Central` vs. `Far West`/`West`) |
| P12 | Validation record states Expectation before Verdict; reports both FP-rate and recall as separate numbers; never presents `out_of_range` recall as evidence of unique model value | ✓ VERIFIED | Section order confirmed; doc explicitly labels `out_of_range` as "redundant with G3" and points to `in_range_implausible` as the real evidence |
| P13 | C10 spec no longer claims the component doesn't exist; sections describe what shipped; acceptance criteria annotated with evidence, including an honest "not fully met" on the literal zero-false-positive wording | ✓ VERIFIED | All four stale strings absent; spec names `anomaly_detector.py`, `anomaly_training.py`, `anomaly_detection_model.md`; "zero false positives" criterion explicitly marked **Not fully met** rather than whitewashed |

**Score (plan-level detail):** 12/13 verified, 1 failed (P8 / CR-01).

### Combined Score

17/18 must-haves verified (5 ROADMAP SC + 12 of 13 sampled plan-level truths); 1 failed.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `backend/anomaly_detector.py` | Additive third branch, unchanged contract | ✓ VERIFIED | 460 lines, `_check_against_model` present ×5 refs, no handler/imputation/monitor-import |
| `backend/anomaly_training.py` | Offline trainer/bake-off/measurement/load-characterization | ✓ VERIFIED (with CR-01 defect) | 1219 lines, all exported functions present and exercised; report-merge defect confirmed (see Gaps) |
| `backend/config.py` | `ANOMALY_ML_*` tunables | ✓ VERIFIED | All named constants present with expected shapes |
| `backend/ercot_data_retriever.py` | Additive return value, zone selection, per-year loop | ✓ VERIFIED | `pull_ercot_data` returns frame; per-corridor zone substrings confirmed distinct in live run (WR-02 date-boundary truncation noted as pre-existing, non-blocking, see Anti-Patterns) |
| `backend/tests/anomaly_detector_test.py` | Model-branch + fail-safe + OR-combination tests | ✓ VERIFIED | 32 tests, all pass |
| `backend/tests/anomaly_training_test.py` | Offline assembly + measurement + bake-off + D-02 boundary invariants | ✓ VERIFIED | Present, all pass |
| `backend/tests/ercot_data_retriever_test.py` | Offline retriever tests | ✓ VERIFIED | 254 lines, present, all pass, no network |
| `docs/data-science/decisions/anomaly_detection_model.md` | ANOM-02 validation record | ✓ VERIFIED | 406 lines, all required sections present, transcription re-confirmed against a freshly-regenerated report |
| `docs/data-science/specs/C10-anomaly-detection.md` | Corrected spec | ✓ VERIFIED | 141 lines, stale claims removed, evidence-annotated |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `anomaly_detector.py` | `config.py` | Path built only from `ANOMALY_ML_MODEL_DIR`+`ANOMALY_ML_MODEL_FILENAME_TEMPLATE` | ✓ WIRED | `_model_path_for` validates corridor before path assembly |
| `anomaly_detector.py` | `data/models/anomaly_<corridor>.joblib` | `_load_corridor_model`/`_load_corridor_model_or_none` | ✓ WIRED | Live-loaded both corridors' artifacts successfully |
| `anomaly_detector.py` | `DLRSafetyMonitor.py` | Raises rather than handles; G6 is the sole fail-safe boundary | ✓ WIRED | Confirmed via passing `model_failure_resolves_to_static_rating` test and zero diff on `DLRSafetyMonitor.py` |
| `anomaly_training.py` | `backend/open_meteo_provider.py` (via `forecast_training.fetch_city_weather`) | Real historical weather source, reused | ✓ WIRED | Live E2E run pulled 17,520 real hourly rows per corridor |
| `anomaly_training.py` | `anomaly_detector.py` | `persist_corridor_model` writes onto `anomaly_detector._model_path_for(corridor)` | ✓ WIRED | Path convention shared and confirmed via successful load-after-persist |
| `anomaly_training.py` | `backend/ercot_data_retriever.py` | `characterize_load` calls `pull_ercot_data` with corridor-specific zones | ✓ WIRED | Live run confirmed distinct zone matches per corridor |
| `anomaly_detector.py` | `backend/ercot_data_retriever.py` | NO link — asserted absent (D-02 boundary) | ✓ VERIFIED ABSENT | `test_load_is_training_time_only_and_never_reaches_check` passes; grep confirms no import |
| `anomaly_training.py` | `data/models/anomaly_validation_report.json` | `corridor_report`/`--bakeoff` write path | ⚠️ **WIRED BUT DEFECTIVE** | Writes correctly for a full-corridor-set run; silently destructive for a corridor-scoped run (CR-01) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full test suite | `.venv/bin/python3 -m pytest -q` | `467 passed, 0 failed` | ✓ PASS |
| Fail-safe/OR-combination named tests | `pytest -k "model_failure_resolves_to_static_rating or ... non_finite_rating_still_skips_model_branch"` | `14 passed` | ✓ PASS |
| Live E2E tracer | `anomaly_training.py --corridor AUSTIN_CORPUS_CHRISTI --years 1` + manual `check()` call | Real `(bool,str)` verdict, `signal='model_clean'`, `model_source` matches | ✓ PASS |
| Live D-03 bake-off, both corridors | `anomaly_training.py --bakeoff --years 1` | Both corridors reproduced identical winners/contaminations to the SUMMARY | ✓ PASS |
| Live D-02 load characterization | `anomaly_training.py --characterize-load` | Reproduced identical zone matches/correlations to the SUMMARY | ✓ PASS |
| Validation-record transcription | Independent re-run of the plan's own `TRANSCRIPTION_OK` script against a freshly-regenerated report | `TRANSCRIPTION_OK` | ✓ PASS |
| Report-merge integrity (CR-01 reproduction) | `--bakeoff --years 1` (both) then `--bakeoff --years 1 --corridor MIDLAND_EL_PASO` | Report shrank from 2 keys to 1 key — `AUSTIN_CORPUS_CHRISTI` silently dropped | ✗ **FAIL** — confirms 02-REVIEW.md CR-01 |
| Non-numeric raw value error message | `check({'wind':'bad',...})` | `ValueError: could not convert string to float: 'bad'` (does not name the field per docstring contract) | ⚠️ Confirms 02-REVIEW.md WR-04 (does not gate; ValueError still propagates uncaught) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| ANOM-01 | 02-01, 02-02, 02-03 | Trained model on wind/temp/solar/load baselines replaces/augments the heuristic, dropped in behind the existing interface | ✓ SATISFIED | Model branch shipped, both corridors trained and persisted, load characterized at training time (D-02) with an enforced boundary test |
| ANOM-02 | 02-02, 02-04 | Model's FP/FN behavior validated against real historical data, results documented | ✓ SATISFIED | Bake-off measurement + validation record, both independently reproduced during this verification |

**Traceability note (non-blocking, documentation currency gap):** `.planning/workstreams/ml-modeling/REQUIREMENTS.md` still lists both `ANOM-01` and `ANOM-02` as unchecked (`- [ ]`) and its traceability table (lines 57-58) still reads "Pending" for both, despite both being fully discharged by this phase's evidence. This is a stale traceability document, not a missing implementation — recommend updating the checkboxes/table to "Complete" as part of phase close-out, but it does not itself block the phase goal.

### Anti-Patterns Found

Re-confirmed 02-REVIEW.md's findings by direct reproduction/inspection rather than trusting the review document:

| File | Finding | Severity | Impact | Independently confirmed? |
|---|---|---|---|---|
| `backend/anomaly_training.py` (`_run_validate`, `_run_bakeoff`) | Report overwrite silently drops corridors not in the current invocation (CR-01) | 🛑 Blocker (for evidentiary integrity, not runtime safety) | Undermines the phase's own T-02-09 mitigation; promoted to a **gap** in this report | ✓ Yes — live repro performed and reversed |
| `backend/anomaly_training.py:249-293` (`chronological_split`) | Untested disjointness guarantee for real two-rows-per-timestamp pooled shape (WR-01) | ⚠️ Warning | Could mildly understate FP rate for corridors where the split boundary lands mid-timestamp; not proven to have actually occurred in the current persisted report | Not independently reproduced (requires a specific row-count parity); accepted from review on code-reading grounds |
| `backend/ercot_data_retriever.py:85` | Inclusive end-of-day mask truncates the final ~23 hours of any requested window (WR-02) | ⚠️ Warning | Pre-existing bug (not introduced this phase); confirmed live — both corridors' load windows end at `Dec 31T00:00:00` instead of `Dec 31T23:00:00` | ✓ Yes — reproduced in live `--characterize-load` run |
| `backend/anomaly_training.py:531-538` (`validate_candidate`) | Duplicated RNG seed makes both injection categories sample identical row positions (WR-03) | ⚠️ Warning | Weakens (does not invalidate) the "pooled recall" figure's independence; both corridors' recall numbers themselves are unaffected in direction (100% vs 0%) | ✓ Yes — confirmed by code inspection (`seed_rng`/`seed_rng_2` both constructed from the identical `config.ANOMALY_ML_RANDOM_SEED`) |
| `backend/anomaly_detector.py:426-434` (`_check_against_model`) | Non-numeric (non-float-castable) raw value raises `ValueError` before the intended field-naming guard runs, so message doesn't name the field (WR-04) | ⚠️ Warning | Still fails safe (ValueError propagates uncaught to G6); only the diagnostic message quality is degraded; untested edge case | ✓ Yes — reproduced live |
| `backend/anomaly_detector.py` (`_MODEL_CACHE`) | Cache never invalidated after `persist_corridor_model` writes a new artifact (WR-05) | ⚠️ Warning | Not exercised in the intended train/serve-as-separate-processes deployment shape; a footgun for any future same-process retrain | Not independently reproduced; accepted from review on code-reading grounds (bake-off's own verify script has to call `_MODEL_CACHE.clear()` manually, corroborating) |
| `backend/anomaly_training.py` | `select_winner` undocumented secondary tie-break on contamination (IN-01); CLI flags not mutually exclusive (IN-02); JSON `NaN` serialization (IN-03); string-based `datetime_utc` groupby before conversion (IN-04) | ℹ️ Info | Minor robustness/documentation gaps, no safety or correctness impact | Accepted from review; none independently re-verified as immaterial to the phase goal |
| — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in any phase-modified file | — | — | ✓ Confirmed via direct grep of all 6 modified/created files |

### Human Verification Required

None. Every must-have and every review finding was independently checked against the running codebase (test execution, live network re-runs of the training/bake-off/characterization scripts, direct code/grep inspection) rather than accepted from SUMMARY.md or 02-REVIEW.md prose alone.

### Gaps Summary

The phase goal's core claim — the G6 safety gate backed by a real trained model, fail-safe
contract intact, and false-positive/false-negative behavior measured against real historical
data — **is genuinely achieved**. All five ROADMAP success criteria were independently
re-verified against the running codebase, not merely trusted from the SUMMARY documents: the
model branch is real and additive, the fail-safe contract holds under a live-tested model
failure, both corridors are trained and measured against real Open-Meteo/ERCOT data, and the
validation record honestly transcribes that measurement (including an honest "not fully met" on
the literal zero-false-positive wording, and a load characterization correctly scoped to
training-time only with an enforced boundary test).

One genuine, independently-reproduced defect (CR-01) sits in the *offline evidence-recording*
machinery, not the runtime safety path: `--bakeoff`/`--validate` overwrite
`anomaly_validation_report.json` with a corridor-scoped subset whenever invoked with `--corridor`,
silently destroying the other corridor's previously-recorded evidence with no warning. This
directly contradicts a must-have this phase's own Plan 02-02 explicitly wrote in its frontmatter
("so a shortened run is visible in the evidence rather than hidden behind a score") and the
threat register's own T-02-09 mitigation claim. It does not affect the currently-persisted report
or the currently-published validation record — both were generated by a full, unscoped run and
this verification independently reproduced identical numbers — but it is a real, live,
un-mitigated risk for any future maintenance workflow that retrains one corridor at a time. This
is why the phase is marked `gaps_found` rather than `passed`: a must-have was proven false by
direct reproduction, not merely inferred from static review.

Four additional Warning-level findings from 02-REVIEW.md were independently corroborated
(WR-02 through WR-05) and are recorded above for completeness; none of them contradicts an
explicit must-have and none touches the live `check()` safety path, so none is elevated to a gap.
A stale REQUIREMENTS.md traceability entry (still reading "Pending" for both requirements) is
noted as a non-blocking documentation-currency item.

**Recommended next step:** a small follow-up plan/commit applying the fix 02-REVIEW.md already
specifies for CR-01 (load-merge-write instead of build-fresh-and-overwrite) before this workstream
relies further on `anomaly_validation_report.json` as a durable evidence trail. WR-01 through
WR-05 and IN-01 through IN-04 can be triaged at the team's discretion — none blocks this phase's
goal.

---

_Verified: 2026-09-26_
_Verifier: Claude (gsd-verifier)_
