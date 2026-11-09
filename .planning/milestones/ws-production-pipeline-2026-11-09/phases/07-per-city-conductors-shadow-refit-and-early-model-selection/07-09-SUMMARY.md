---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 09
subsystem: evaluation-headline-port
tags: [confirmation-protocol, production-conductor, refit-artifacts, scored-artifacts, late-descriptive-gate, headline-port, python, pytest, tdd]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-07 run_confirmation(round_name, vetoes), truth_stats, the secondary label and combined_summary_v4; plan 07-03 forecast_conductor_refit (arm5_frame_for_point, production_differs, make_headline_loader, manifests); plan 07-01 production_city_point and the COND-02 golden; plan 07-19 RATING_CONFIG_VERSION v2-provisional-2026-11-02
provides:
  - an opt-in point= seam on prepare_city_frame, _arm5_from_weather, candidate_predictions and leakage_probe (None keeps the frozen Drake path)
  - run_confirmation(point_resolver=, secondary=, conductor_basis=) with report["secondary"], report["scored_artifacts"], report["conductor_basis"] and report["rating_config_version"]
  - conductor_basis() (which cities differ, refit and frozen artifact hash status, never deserialized) and late_descriptive_status() (D-03 gate)
  - a CLI that picks its conductor basis, refuses a half-prepared refit before any network call, and reports the basis in --dry-run
affects: [07-10, 07-11, 07-12, 07-15]

actuals:
  tokens: 24000
  tasks: 2
  commits: 2
plan_head_before: 2c113145bd67ff546c26740431f87ed9a1103122
plan_head_after: 148f59c7ca337007442baf675bfeda1f9242cf7f

tech-stack:
  added: []
  patterns:
    - "Geometry seam: a keyword-only point=None; None calls city_point.city_point and weather_to_arm5_frame exactly as before, an explicit point goes through forecast_conductor_refit.arm5_frame_for_point (spy-tested both ways)"
    - "The labelled secondary is scored on the headline's own fetched frame and archive weather in the same read, with its own family and decision (label secondary, pick None), never pooled; a secondary city failure never removes the headline's city"
    - "Provenance by wrapping the loader: _recording_loader reads loader.served for refit-capable loaders, else hashes the frozen file; records are tagged headline or secondary"
    - "Pre-checks hash files and compare to manifests but never joblib.load; run_confirmation is reached only after they pass, so a bad artifact cannot spend the one-shot read"

key-files:
  created: []
  modified:
    - backend/forecast_shadow_confirm.py
    - backend/tests/forecast_shadow_confirm_test.py

key-decisions:
  - "The CLI's secondary loader is make_headline_loader(version, no refit cities), not forecast_shadow_pipeline.load_correction_model: it serves the same frozen Drake artifacts but checks each file's sha256 against the frozen manifest before it is deserialized (T-07-19 asks for verification again before joblib.load)"
  - "Frozen artifacts are pre-verified together with the refit ones when a city differs: a hash mismatch, an unlisted file or an unreadable manifest refuses the run before any network call; an absent frozen file stays candidate_unavailable, as in the default path"
  - "The secondary is not a separate stub at parity: report['secondary'] is None and report['conductor_basis']['secondary'] carries the statement 'identical to the headline by construction; not computed separately'"
  - "v4-late-descriptive is refused (exit 2, 'nothing to re-score descriptively (D-03)') when no v4-read1 report.json exists, it cannot be read, it records no rating_config_version, or the version equals the current one; the newest report directory name wins; only that one key is read"
  - "run_confirmation records rating_config_version and conductor_basis in config (so run_started.json), report and report.json; dry run records both and, for the late round, the gate status without refusing"
  - "A missing production-table entry for a city asked for is converted to a refusal (exit 2) around conductor_basis only, so a KeyError deep inside a post-guard run is never relabelled as a clean refusal"

patterns-established:
  - "Plan-prescribed single feat commit per task for execute-type plans with tdd=true: RED shown by running the new tests before implementation, recorded in this summary"

requirements-completed: [COND-02]

coverage:
  - id: D1
    description: "The geometry seam: with no point the four functions call city_point.city_point and weather_to_arm5_frame exactly as before; with a point they use arm5_frame_for_point and never ask city_point; an explicit Drake point reproduces the default numbers exactly; the COND-02 golden stays green"
    requirement: COND-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_without_a_point_the_default_path_uses_city_point_and_weather_to_arm5_frame"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_with_a_point_the_geometry_comes_from_the_point_and_city_point_is_not_asked"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_an_explicit_drake_point_gives_exactly_the_default_numbers"
        status: pass
      - kind: command
        ref: "PYTHONPATH=backend .venv/bin/python backend/tests/golden_shadow_capture.py --check (golden matches all six sections)"
        status: pass
    human_judgment: false
  - id: D2
    description: "A production point_resolver recomputes truth, raw_forecast and persistence under each city's production conductor (AUSTIN at 100 C rises, the other three are unchanged) and the leakage probe still passes and still catches a leaky arm"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_production_point_raises_austin_truth_and_raw_and_persistence"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_production_resolver_changes_only_the_differing_citys_truth"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_leakage_probe_passes_under_a_production_point_and_still_catches_a_leaky_arm"
        status: pass
    human_judgment: false
  - id: D3
    description: "The frozen-Drake secondary on the same read: its family equals a separate Drake-only run on the same inputs, carries the label 'secondary: frozen Drake artifacts, never decides' with pick None, is accepted by combined_summary_v4 (a duplicate is still refused), is validated before the guard, and a city failure in it is recorded without removing the headline's city"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_secondary_equals_a_drake_only_run_on_the_same_inputs_and_never_decides"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_secondary_report_is_accepted_by_the_combined_summary_with_its_own_label"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_bad_secondary_spec_is_refused_before_the_guard_and_leaves_the_root_empty"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_secondary_failure_in_one_city_is_recorded_and_the_headline_keeps_that_city"
        status: pass
    human_judgment: false
  - id: D4
    description: "report['scored_artifacts'] lists every artifact the headline and the secondary loaded with city, method, path, sha256, source (refit, frozen or injected) and role, matching what the headline loader itself served"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_scored_artifacts_lists_every_headline_and_secondary_artifact_with_hash_and_source"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_recording_loader_returns_the_model_and_records_each_served_artifact_once"
        status: pass
    human_judgment: false
  - id: D5
    description: "The CLI selects its conductor basis: parity runs the default path with no secondary; a differing city builds the production resolver, the headline loader and a frozen secondary; a missing, tampered or unlisted refit artifact, a missing refit manifest or a tampered frozen artifact exits 2 before run_confirmation (requests.get is a bomb in these tests)"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_main_with_a_differing_city_builds_the_production_resolver_the_headline_loader_and_a_secondary"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_main_refuses_with_exit_2_before_any_request_when_the_refit_or_frozen_artifacts_are_not_sound"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_main_at_parity_runs_the_default_path_with_no_secondary_and_records_the_statement"
        status: pass
    human_judgment: false
  - id: D6
    description: "Every report, config record and run_started.json carries rating_config_version and conductor_basis"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_every_report_and_its_run_started_marker_record_the_rating_config_version"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_a_given_conductor_basis_is_recorded_in_the_report_and_the_config"
        status: pass
    human_judgment: false
  - id: D7
    description: "D-03 gate: v4-late-descriptive is refused with 'nothing to re-score descriptively (D-03)' without a read-1 report, with an unchanged or missing version, uses the newest report, and still meets the instant and one-shot guards after the gate"
    requirement: SEL-04
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_late_descriptive_round_is_refused_without_any_read_1_report"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_the_late_descriptive_round_proceeds_when_the_version_differs_and_uses_the_newest_read_1_report"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_after_the_gate_the_late_round_still_meets_the_instant_and_one_shot_guards"
        status: pass
    human_judgment: false
  - id: D8
    description: "--dry-run reports the conductor basis (differing cities, refit artifacts and hash status, rating_config_version, late-gate status) with no network call, no joblib.load and no directory created; at parity it prints [] v2-"
    requirement: SEL-02
    verification:
      - kind: unit
        ref: "backend/tests/forecast_shadow_confirm_test.py#test_dry_run_with_a_differing_city_lists_the_refit_artifacts_and_their_hash_status_without_network_or_load"
        status: pass
      - kind: command
        ref: "PYTHONPATH=backend .venv/bin/python backend/forecast_shadow_confirm.py --dry-run --round v4-read1 --out /tmp/p7_basis.json (prints [] v2-)"
        status: pass
      - kind: integration
        ref: "pytest backend/tests (full suite, 2457 passed, 82 skipped)"
        status: pass
    human_judgment: false

duration: 22min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 09: Production-Conductor Seam in the Headline Port Summary

**The headline port can now score under each city's production conductor with the hash-verified refit cooling and reference models and, in the same read, report the frozen Drake artifacts as a labelled secondary; the CLI picks the basis itself, refuses a half-prepared refit before any network call, records which artifacts were scored, and gates the D-03 descriptive re-score. While every city is on Drake the whole seam is off and the COND-02 golden proves the default path is unchanged. No real FRESH row was read and no real confirm or score run was made.**

## Performance

- **Duration:** 22 min (one 3 min 44 s full-suite run)
- **Started:** 2026-11-02T08:08:42Z
- **Completed:** 2026-11-02T08:31Z
- **Tasks:** 2
- **Files modified:** 2 (`backend/forecast_shadow_confirm.py`, `backend/tests/forecast_shadow_confirm_test.py`)

## Accomplishments

- **Geometry seam (D-01).** `prepare_city_frame`, `_arm5_from_weather`, `candidate_predictions` and `leakage_probe` take a keyword-only `point=None`. With no point they make the same calls as before (`city_point.city_point`, `forecast_shadow_fit_models.weather_to_arm5_frame`); with a point they use it and `forecast_conductor_refit.arm5_frame_for_point`. Spy tests pin both directions, and an explicit Drake point reproduces the default arrays exactly (`np.array_equal`).
- **Production headline and secondary.** `run_confirmation(point_resolver=, secondary=)`: the per-city work is now `_score_city` (prepare, load, predict, probe) and `_city_blocks`, shared by the headline and the secondary. The secondary reuses the headline's fetched frame and archive weather, builds its own error frames, family and decision (`apply_ship_rule_v4(label="secondary")`, pick always `None`) and its own truth_stats, and is validated before the guard. Under the signed O4 table (AUSTIN at 100 C) AUSTIN's truth, raw forecast and persistence rise and the other three cities' values are identical.
- **Provenance.** `_recording_loader` wraps each loader; `report["scored_artifacts"]` holds city, method, path, sha256, source (`refit`, `frozen` or `injected`) and role (`headline` or `secondary`) for every artifact either loaded. For the refit-capable loader the entries are the loader's own `served` records.
- **Conductor basis.** `conductor_basis(cities)` names the differing cities, the two refit artifacts per differing city and the frozen artifacts, each with `verified`, `missing_file`, `hash_mismatch`, `not_in_manifest` or `manifest_unreadable` status (hashed, never loaded), a `problems` list, and the headline and secondary statements (at parity: "identical to the headline by construction; not computed separately").
- **CLI.** `main` computes the basis, refuses with exit 2 and `refused: conductor basis ...` when `problems` is non-empty (before `run_confirmation`, so before any request), otherwise builds `point_resolver=city_point.production_city_point`, `make_headline_loader(version, differing)` and the frozen secondary; at parity it passes none of these. `rating_config_version` and `conductor_basis` go into config, `run_started.json` and the report.
- **D-03 gate.** `late_descriptive_status` reads the `rating_config_version` of the newest `v4-read1/reconstructed_frames_*/report.json`; `v4-late-descriptive` exits 2 with "nothing to re-score descriptively (D-03)" when none exists, it is unreadable, records no version, or equals the current one. The guard's instant and one-shot rules still apply afterwards (tested).
- **Dry run.** Adds `conductor_basis`, `rating_config_version` and, for the late round, `late_descriptive_gate`; it reports problems and never refuses because of one. Run for real at parity it printed `[] v2-` and created no evidence directory.
- Test counts: confirm 100 -> 141 collected (41 new; one existing test adapted, see below). Full suite 2457 passed, 82 skipped (was 2416 passed).

## Task Commits

1. **Task 1: Opt-in production-conductor seam, frozen-Drake secondary and scored-artifact provenance** - `f01715d` (feat)
2. **Task 2: CLI conductor-basis selection, refit pre-check, late-descriptive gate and dry-run reporting** - `148f59c` (feat)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Evidence (both tasks `tdd="true"`)

- **Task 1 RED:** the new tests were written first; `pytest backend/tests/forecast_shadow_confirm_test.py` then gave 16 failed, 101 passed. The failures were the target tests, on the planned reasons: `KeyError: 'point'` for the missing keyword in `test_the_geometry_functions_take_an_optional_keyword_only_point`, unexpected-keyword `TypeError`s for `point=`, `point_resolver=` and `secondary=`, and `AttributeError: module has no attribute '_recording_loader'`. The one new test that passed already (`test_without_a_point_the_default_path_...`) pins existing behavior on purpose. **GREEN:** the same file, the validation suite and the COND-02 golden passed (174 tests) and `golden_shadow_capture.py --check` matched all six sections.
- **Task 2 RED:** the new tests were written first; the same file gave 22 failed, 119 passed, each failing on a missing `conductor_basis`, `late_descriptive_status`, `--dry-run` keys or the CLI behavior (`KeyError: 'conductor_basis'`, `KeyError: 'late_descriptive_gate'`, `AttributeError` for the new functions). **GREEN:** 141 passed; then the confirm, validation, golden and refit suites together (255 passed) and the full suite (2457 passed, 82 skipped).
- The plan type is `execute` and prescribes one `feat(07-09)` commit per task, so there is no separate `test(07-09)` commit and no TDD Gate Compliance section applies.

## Files Created/Modified

- `backend/forecast_shadow_confirm.py` - the point seam, `_score_city`, `_city_blocks`, `_sample_size_block`, `_validate_secondary`, `_recording_loader`, `conductor_basis`, `late_descriptive_status`, secondary scoring, `scored_artifacts`, conductor basis and version in config and report, CLI selection and refusals, dry-run additions; module docstring documents the conductor basis
- `backend/tests/forecast_shadow_confirm_test.py` - 41 new tests for the seam, secondary, provenance, basis, CLI refusals, version recording, D-03 gate and dry run; one existing test adapted

## Decisions Made

See `key-decisions` above. The two worth a human glance: the secondary uses the hash-verified frozen loader rather than the bare `load_correction_model` the plan text names, and a missing frozen file is not a refusal (it stays `candidate_unavailable`) while a mismatching or unlisted one is.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Secondary loader verifies hashes before deserializing**
- **Found during:** Task 2 (main wiring), against threat T-07-19 ("manifest verification before any network call and again before joblib.load")
- **Issue:** The plan's action passes `forecast_shadow_pipeline.load_correction_model` as the secondary loader, which unpickles the 12 frozen files with no hash check; the headline loader for non-refit cities already checks them.
- **Fix:** The secondary loader is `forecast_conductor_refit.make_headline_loader(version, frozenset(), ...)`, which serves the same frozen Drake artifacts through the manifest check. `run_confirmation` accepts any loader, so the secondary spec shape is as planned.
- **Files modified:** `backend/forecast_shadow_confirm.py`
- **Verification:** `test_main_with_a_differing_city_...` (secondary `served` records source `frozen`), `test_scored_artifacts_lists_every_headline_and_secondary_artifact_...`
- **Committed in:** `148f59c`

**2. [Rule 2 - Missing Critical] Frozen artifacts pre-verified with the refit ones; late integrity failures handled**
- **Found during:** Task 2
- **Issue:** The plan's pre-check covers only refit artifacts, but both headline and secondary loaders also raise `ArtifactIntegrityError` (a `RuntimeError`) for a bad frozen file, which `run_confirmation` does not catch per city and `main` did not catch at all: that would be raised after the guard and could spend the one-shot read.
- **Fix:** `conductor_basis` also checks the cities' frozen artifacts against the frozen manifest and refuses (before any network call) on a hash mismatch, an unlisted file or an unreadable manifest; `main` now reports a post-pre-check `ArtifactIntegrityError` as `failed:` (exit 1) instead of a traceback.
- **Files modified:** `backend/forecast_shadow_confirm.py`
- **Verification:** `test_main_refuses_with_exit_2_before_any_request_...[frozen_tampered]`, `test_conductor_basis_flags_a_tampered_frozen_artifact_but_not_an_absent_one`
- **Committed in:** `148f59c`

**3. [Rule 1 - Bug, test left stale by the planned behavior change] Descriptive-round CLI test needed a read-1 report**
- **Found during:** Task 2
- **Issue:** `test_the_descriptive_round_needs_no_veto_record_and_still_uses_its_own_subroot` ran `--round v4-late-descriptive` with an empty evidence root; the planned D-03 gate now (correctly) refuses that.
- **Fix:** The test writes a synthetic read-1 report recorded under an older config version first; its assertions are unchanged.
- **Files modified:** `backend/tests/forecast_shadow_confirm_test.py`
- **Committed in:** `148f59c`

---

**Total deviations:** 3 auto-fixed (2 missing critical, 1 stale test)
**Impact on plan:** All three tighten the plan's own threat mitigations or follow from its D-03 gate. No scope creep; nothing outside the two planned files changed.

## Issues Encountered

- `report.md` (written by `forecast_shadow_eval_core.write_report`) renders only the headline; the secondary is in `report.json` under `report["secondary"]`. Rendering it would be an edit to eval_core, which this plan does not list; it is a candidate for the 07-11 or 07-15 runbook step if a human-readable secondary block is wanted.
- `forecast_conductor_refit.REFIT_ROOT` is a path relative to the working directory, so the CLI's refit pre-check, like the refit CLI itself, must be run from the repository root (as the operator commands already are). Tests monkeypatch it to an absolute temp path.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: file_access | backend/forecast_shadow_confirm.py | `late_descriptive_status` opens the newest `v4-read1/reconstructed_frames_*/report.json` (FRESH evidence) and reads only its `rating_config_version` key; no figure is read or computed from it, and the tests use synthetic reports only |

## Known Stubs

None.

## Safety Notes

- No real confirm or score run was made. The only real invocation of the CLI was the plan's acceptance command `forecast_shadow_confirm.py --dry-run --round v4-read1`, which makes no network call, opens no FRESH file and created no evidence directory (`data/shadow/evaluation` still does not exist). All tests pin the clock where it matters, stub the network (`requests.get` raises), load no real frozen artifact for scoring and use synthetic fixtures.
- No Supabase writes, no deploys, no retraining; `data/shadow/models` untouched (the golden `--check` matches).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 07-11 can land the AUSTIN `PRODUCTION_CONDUCTORS` change and refit artifacts: with them present for the current `RATING_CONFIG_VERSION` under `data/models/conductor_refit/<version>/`, the CLI will pick the production basis by itself; with them absent it refuses with exit 2 before any request, naming each problem.
- `SEL-04` and `SEL-02` stay open (other plans in the phase still declare them); `COND-02` is marked complete.

## Self-Check: PASSED

- `backend/forecast_shadow_confirm.py` and `backend/tests/forecast_shadow_confirm_test.py` exist; commits `f01715d` and `148f59c` are ancestors of HEAD.
- `grep -c "point=None" backend/forecast_shadow_confirm.py` prints 4; the golden `--check` exits 0; the dry-run command prints `[] v2-`; the full suite is 2457 passed, 82 skipped.

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*
