---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 11
subsystem: evaluation-veto-and-conductor-gate
tags: [confirmation-protocol, ablation, test-split, veto, power-systems-gate, conductor-refit, config-version, python, pytest]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-10 TEST-split scorer and registry parity test; plan 07-03 ablation and refit modules; plan 07-07 load_vetoes; plan 07-09 production headline loader and conductor_basis; plan 07-19 production conductor table
provides:
  - ABLATION and TEST evidence (frozen-drake and production basis), vetoes.json accepted by load_vetoes, plain-English report
  - power_systems_gate.md recording the owner's apply-answers decision for AUSTIN (signed v4 O4)
  - PRODUCTION_CONDUCTORS["AUSTIN"] at Drake 100 C, RATING_CONFIG_VERSION v3-powersystems-2026-11-02
  - AUSTIN refit cooling and reference artifacts with a verified manifest (data/models/conductor_refit/v3-powersystems-2026-11-02/)
affects: [07-12, 07-14, 07-15, 07-17]

requirements-completed: [SEL-03, SEL-02, COND-01]

actuals:
  tokens: 11700
  tasks: 3
  commits: 5
plan_head_before: 6e12778ec38f19821ff7eace23cd62ebae59dbf8
plan_head_after: e7d1b21834aff064c7fb8e4cb0a970751a8cb012

tech-stack:
  added: []
  patterns:
    - "A Power Systems value enters through config.PRODUCTION_CONDUCTORS plus a RATING_CONFIG_VERSION bump with a per-value source string; no code change (COND-01)"
    - "Tests of the no-differing-city path pin the pre-switch table with a drake_parity_table fixture instead of relying on the live table"
    - "vetoes.json keeps the superseded frozen-drake TEST record under test.frozen_drake_record"

key-files:
  created:
    - docs/data-science/decisions/v4_selection/power_systems_gate.md
    - data/models/conductor_refit/v3-powersystems-2026-11-02/ (ARTIFACT_HASHES.sha256, ml_cooling_corrected_AUSTIN.joblib, reference_ml_refit_24h_AUSTIN.joblib)
    - data/shadow/evaluation/v4-test/report_20261102T173449Z/ and reconstructed_frames_20261102T173449Z/
  modified:
    - backend/config.py
    - backend/tests/production_conductor_test.py
    - backend/tests/protocol_v4_registry_test.py
    - docs/data-science/schema/city_rating_v1.md
    - docs/data-science/decisions/v4_selection/vetoes.json
    - docs/data-science/decisions/v4_selection/ablation_and_test_report.md
    - six parity-assuming test files (see Deviations)

key-decisions:
  - "Task 3's precondition (clock before 2026-11-01T00:00:00Z, otherwise D-03) is superseded by signed v4 O4: test.rescore_gate = before_read1_run. The switch was applied before read 1 was run; read 1 has not been run."
  - "AUSTIN's diameter and AC resistance keep the Drake catalogue values (unchanged); elevation 900 m and azimuth 173.15 keep model defaults, with their provisional sources; only conductor_type and max_temp_c carry the owner's citation"
  - "The version label v3-powersystems-2026-11-02 drops the word provisional, but RATING_BASIS still carries it, so latest_rating.is_provisional stays true until the 07-17 go"

patterns-established:
  - "Owner-answer gate: gate record, config bump, refit, TEST re-score and registry/dry-run proof as four separately committed steps"

coverage:
  - id: D1
    description: "ABLATION (all four cities, six signed variants, 2,360 train / 784 validation rows per city) and TEST (frozen artifacts, 784 slots per city) run on the real cached frames against the signed criteria; no veto, ranking_invariant true"
    requirement: SEL-03
    verification:
      - kind: command
        ref: "PYTHONPATH=backend .venv/bin/python -c load_vetoes(vetoes.json) prints the three real candidates for ablation and test, ranking_invariant True"
        status: pass
    human_judgment: false
  - id: D2
    description: "Owner's gate outcome recorded: apply-answers for AUSTIN only (type 795 kcmil ACSR Drake, 100 C), other cities unchanged, with UTC reply time, values, sources, new version, artifact hashes and the TEST re-score"
    requirement: COND-01
    verification:
      - kind: unit
        ref: "backend/tests/production_conductor_test.py#test_documented_divergence"
        status: pass
      - kind: unit
        ref: "backend/tests/protocol_v4_registry_test.py#test_production_table_row_matches_the_signed_o4_choice (3 parametrized cases)"
        status: pass
      - kind: unit
        ref: "backend/tests/cond02_shadow_golden_test.py (COND-02 golden, shadow Drake path unchanged)"
        status: pass
    human_judgment: false
  - id: D3
    description: "AUSTIN cooling and reference refit on rows before 2026-03-17 into the new-version directory with a manifest; frozen manifest still verifies and data/shadow/models is untouched"
    requirement: SEL-02
    verification:
      - kind: command
        ref: "shasum -a 256 -c data/models/conductor_refit/v3-powersystems-2026-11-02/ARTIFACT_HASHES.sha256 (2 OK); shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256 (all OK)"
        status: pass
      - kind: unit
        ref: "backend/tests/protocol_v4_registry_test.py#test_production_table_row_matches_the_signed_o4_choice[refit.cities]"
        status: pass
    human_judgment: false
  - id: D4
    description: "TEST re-scored under the production conductors; vetoes.json test section updated, frozen-drake record kept; read-1 dry run lists AUSTIN as the one differing city with both refit artifacts verified"
    requirement: SEL-03
    verification:
      - kind: command
        ref: "forecast_shadow_confirm.py --dry-run --round v4-read1 --out /tmp/p7_gate_dry.json: differing [AUSTIN], problems [], refit_verified true"
        status: pass
      - kind: integration
        ref: "pytest backend/tests (full suite, 2570 passed, 82 skipped)"
        status: pass
    human_judgment: false

duration: 15min (this continuation, from the owner's reply at about 17:32Z to 17:47Z; Tasks 1 and 2 ran earlier)
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 11: ABLATION and TEST Results, Power Systems Gate Summary

**ABLATION and TEST found no veto and a conductor-invariant ranking, and the owner's `apply-answers` moved AUSTIN (only) to 795 kcmil ACSR Drake at 100 C: config bumped to `v3-powersystems-2026-11-02`, AUSTIN's cooling and reference models refit (rows before 2026-03-17), and TEST re-scored under the production conductors with the same no-veto outcome (reference_ml_refit_24h still loses to the plain forecast at MIDLAND only). Neither analysis names a winner; read 1 has not been run.**

## Performance

- **Tasks:** 3 (Task 1 automated, Task 2 the blocking-human gate, Task 3 apply-answers)
- **Completed:** 2026-11-02
- **Commits:** 5 (measured from the plan ledger)

## Accomplishments

- **Task 1 (earlier, `2c48f9e`).** ABLATION and TEST (frozen-drake) run on the real cached frames; `vetoes.json` and the plain-English report written; `load_vetoes` accepts the record; no vetoes; `ranking_invariant` true.
- **Task 2 (owner gate).** The owner replied `apply-answers` at about 2026-11-02T17:32Z confirming the proposed payload: AUSTIN `795 kcmil ACSR Drake`, diameter 0.02814 m and AC resistance 0.0726 ohm/km (catalogue, unchanged), `max_temp_c` 100.0 (was 75.0), elevation 900 m and azimuth 173.15 (model defaults, not part of the answer); CORPUS_CHRISTI, MIDLAND, EL_PASO no answer, unchanged.
- **Task 3 step 1 (`a14f088`).** `PRODUCTION_CONDUCTORS["AUSTIN"]` and its sources set; `RATING_CONFIG_VERSION` bumped with a comment; the schema doc's label sentence and conductor-basis paragraph updated; `test_provisional_parity` replaced by `test_documented_divergence` (exactly AUSTIN differs, only in maximum operating temperature).
- **Task 3 step 2 (`a933959`).** `forecast_conductor_refit.py --cities-from-production-diff` refit AUSTIN's `ml_cooling_corrected` (3,144 rows) and `reference_ml_refit_24h` (18,834 rows) into `data/models/conductor_refit/v3-powersystems-2026-11-02/` with a manifest (cooling `31fe8d9b...f20973`, reference `f5dc0ebb...3dc43`); `shasum -c` OK for both, and the frozen manifest still verifies in full.
- **Task 3 step 3 (`87a0760`).** TEST re-scored with `--conductor-basis production` (`report_20261102T173449Z`): no candidate vetoed; AUSTIN MAE vs raw_forecast, wind 126.10 vs 133.33, cooling 106.48 vs 133.33, reference 122.64 vs 133.33 (AUSTIN's raw baseline rises from 114.46 because truth is recomputed at 100 C). `vetoes.json` test section updated with the frozen-drake report kept as `frozen_drake_record`; `load_vetoes` accepts it. `forecast_shadow_confirm.py --dry-run --round v4-read1` lists AUSTIN as the one differing city, both refit artifacts verified, no problems. `power_systems_gate.md` records all of it, including the superseded precondition.
- Full suite: 2570 passed, 82 skipped (last run before this plan's tests: 2566 passed).

## Task Commits

1. **Task 1: ABLATION and TEST against the signed criteria** - `2c48f9e` (docs)
2. **Task 2: Owner's Power Systems gate** - no commit (decision recorded in `power_systems_gate.md`)
3. **Task 3: adopt values / refit / TEST re-score** - `a14f088` (feat), `a933959` (feat), `87a0760` (docs)
4. **Consequential test updates** - `e7d1b21` (test)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Tests that assumed Drake parity or a "v2-provisional" label broke at the switch**
- **Found during:** Task 3 verification (full suite: 13 failures after the config edit and refit)
- **Issue:** Tests written for the pre-switch table failed because AUSTIN is now at 100 C and the version label no longer contains "provisional": `protocol_v4_registry_test` fixtures (assumed the live table was pre-switch), `production_conductor_test` (a 100 C "hotter" comparison), `forecast_conductor_refit_test` (`_drake_point` was the production point; parity CLI and `production_differs` cases), `forecast_shadow_confirm_test` (three parity cases), `forecast_test_split_score_test` (two parity cases), `forecast_shadow_eval_validation_test` (block-length refusal was preceded by the new conductor-basis refusal), `real_data_validation_test` (two cases assumed AUSTIN at 75 C), `expose_migration_test` (asserted the version label alone reads provisional).
- **Fix:** a `drake_parity_table` fixture pins the pre-switch table for the no-differing-city tests; `_drake_point` is now the frozen Drake point; a new test pins that only AUSTIN differs in the live table; the registry-test fixture starts from the pre-switch table explicitly and the "still provisional" case sets the old label; rating tests use 125 C for the "hotter" comparison and pin AUSTIN at 75 C for the rounding test; the `is_provisional` check uses a literal old label. No test was weakened: each keeps its assertion against an explicitly constructed state.
- **Files modified:** the six test files above plus `production_conductor_test.py` and `protocol_v4_registry_test.py` (the latter two in `a14f088`)
- **Commits:** `a14f088`, `e7d1b21`

**2. [Rule 2 - Missing Critical] Plan precondition superseded**
- Task 3 required the clock to be before 2026-11-01T00:00:00Z. The instant had passed when the owner signed; signed v4 O4 (`test.rescore_gate = before_read1_run`) replaces it, and the work was done before read 1 was run. Recorded in `power_systems_gate.md`.

**Total deviations:** 2 (both auto-handled). **Impact:** no scope change; the test edits are fixture and expectation updates caused directly by the intended switch.

## Issues Encountered

- `pytest backend` fails at collection because `backend/smoke_test.py` needs `SYNOPTIC_TOKEN`; the suite is run as `pytest backend/tests` (as in prior plans).
- A shell variable holding several file names was not word-split by zsh on the first test-commit attempt; nothing was committed and the commit was redone with explicit paths.

## Known Stubs

None. Elevation, azimuth and the emissivity, absorptivity and temperature-coefficient values keep their sources marked provisional by design; they are values, not stubs.

## Threat Flags

None. No new endpoint, auth path or trust boundary; the owner-supplied value entered through the existing resolver with range checks (T-07-24) and the refit manifest is verified (T-07-25).

## Notes for Later Plans

- 07-12 (read 1) scores AUSTIN under Drake 100 C with the refit cooling and reference artifacts and every other city on the frozen Drake artifacts; the dry run already shows this.
- 07-14 (B2 retrain) runs under `v3-powersystems-2026-11-02` (D-14). B1's conductor half stays open for CORPUS_CHRISTI, MIDLAND and EL_PASO (D-13).
- Every AUSTIN `config_fingerprint` changes at v3; the other three cities' fingerprints do not (the fingerprint covers the conductor table, not the version label).
- A decision for later: `latest_rating.is_provisional` still reads true only through `rating_basis`; 07-17 must remove the word from the basis text as well as the version when the go lifts the label (the version already lacks it).

## Self-Check: PASSED

- Files found: `power_systems_gate.md`, `vetoes.json`, `ablation_and_test_report.md`, `data/models/conductor_refit/v3-powersystems-2026-11-02/` (manifest and two joblib files), `data/shadow/evaluation/v4-test/report_20261102T173449Z/test_split.json`.
- Commits found in history: `2c48f9e`, `a14f088`, `a933959`, `87a0760`, `e7d1b21`.
