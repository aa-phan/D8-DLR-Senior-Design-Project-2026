---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 10
subsystem: evaluation-test-split
tags: [confirmation-protocol, test-split, veto, registry-parity, conductor-basis, python, pytest, tdd]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-09 run_confirmation(point_resolver=, conductor_basis=), conductor_basis() and the production headline loader; plan 07-07 load_vetoes (strict, both sections); plan 07-03 ablation and refit modules; plan 07-02 protocol_v4_registry parser and the signed copy
provides:
  - forecast_test_split_score.py - TEST-split scorer (cached-frame provider, run_test_split, evaluate_test_vetoes, write_test_report, CLI) for the frozen-drake and production conductor bases
  - protocol_v4_registry_test.py - every key of the signed registry pinned to a code constant, a state-aware O4 check or an explicit DOC_ONLY list
affects: [07-11, 07-12, 07-15]

actuals:
  tokens: 18300
  tasks: 2
  commits: 2
plan_head_before: 7f0b3d8d7ad39904bf56a4642d783a985fe5840a
plan_head_after: 2fac5038ad1c1094dc18af5fa9febcce834d911c

tech-stack:
  added: []
  patterns:
    - "TEST is scored through run_confirmation on a development basis with an injected provider and an explicit loader; the window is validated to lie inside [2026-03-18, 2026-09-30) before anything runs, so the guard can never see a FRESH row"
    - "A veto is computed from the family's (candidate, raw_forecast) comparison and refuses a report that lacks one, so a veto cannot be skipped by omission"
    - "Parity tests with a third group: code-mapped keys, state-aware keys (production table, tightens itself when RATING_CONFIG_VERSION leaves v2-provisional) and explicit DOC_ONLY keys; any unmapped or stale key fails"

key-files:
  created:
    - backend/forecast_test_split_score.py
    - backend/tests/forecast_test_split_score_test.py
    - backend/tests/protocol_v4_registry_test.py
  modified: []

key-decisions:
  - "TEST never picks: after run_confirmation the report's decision is set to None (with a decision_note) and report.json / report.md are rewritten, because a development-basis headline decision on TEST rows could otherwise read as a pick"
  - "The frozen-drake basis loads artifacts through make_headline_loader(version, no refit cities), which sha256-checks each file against the frozen manifest before joblib.load, instead of the bare load_correction_model the plan names (same choice as 07-09)"
  - "run_test_split refuses any window outside the TEST window and checks every city's cache exists before an evidence directory is created; a city that failed (missing slots) breaks the 784-slot assertion by name rather than being scored short"
  - "evaluate_test_vetoes returns cities_losing_to_raw as a sorted list of city names (07-11 wants the cities named in vetoes.json) and per_city_mae as {city: (candidate MAE, raw MAE)}"
  - "O4 rows (power_systems.switch_cities, refit.cities, power_systems.austin_config) are checked against the production conductor table, not config-edited here: while RATING_CONFIG_VERSION starts with v2-provisional the table must be at parity and AUSTIN at 75 C; once it moves on, exactly the signed cities must differ, AUSTIN must be at the signed 100 C and the refit artifacts must verify"

patterns-established:
  - "Plan-prescribed single feat commit per task for execute-type plans with tdd=true: RED shown by running the tests before the module exists, recorded in this summary"

requirements-completed: [SEL-01]

coverage:
  - id: D1
    description: "TEST window and slots: constants equal the signed registry; the window has 784 slots from 2026-03-18T00Z to 2026-09-29T18Z; 2026-03-18T00Z is scored, 2026-03-17T18Z is not (the port refuses its fit-window anchor) and 2026-09-30T00Z is never in scope"
    requirement: SEL-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_the_test_window_has_784_slots_from_march_18_to_the_last_slot_before_fresh"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_boundary_edge_first_and_last_slot_in_scope_and_nothing_outside_it"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_boundary_edge_the_port_scores_march_18_and_refuses_the_slot_whose_anchor_is_in_the_fit_window"
        status: pass
      - kind: command
        ref: "PYTHONPATH=backend .venv/bin/python -c ... prints 784 2026-03-18T00:00:00+00:00 2026-09-29T18:00:00+00:00"
        status: pass
    human_judgment: false
  - id: D2
    description: "The cached-frame provider reads only the _2024-01-20_2026-09-29_ cache (cache hit, no network), refuses a missing cache naming the path, refuses a FRESH-dated cache name without opening it, refuses a frame holding a row on or after 2026-09-30T00Z, and builds archive weather from the frame's own truth columns; a window outside the TEST window and an unsigned protocol are refused before any provider call"
    requirement: SEL-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_a_cache_name_carrying_the_fresh_dates_is_refused_and_never_opened"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_a_frame_holding_a_row_on_or_after_the_fresh_start_is_refused"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_a_missing_cache_is_refused_naming_the_path_with_no_network_call_and_nothing_created"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_a_window_outside_the_test_window_is_refused_before_any_provider_call"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_unsigned_protocol_is_refused_before_any_provider_call_or_directory"
        status: pass
    human_judgment: false
  - id: D3
    description: "run_test_split scores a dev fixture per city through run_confirmation, builds the 9-test family, names no pick, records the conductor basis, asserts the slot count per city and supports the production basis (production points and refit artifacts for the differing city; refused when no city differs or an artifact is unsound)"
    requirement: SEL-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_the_dev_fixture_run_scores_every_city_and_builds_the_family_without_naming_a_pick"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_expected_slots_is_asserted_per_city_and_a_mismatch_names_the_city_and_both_counts"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_production_basis_scores_the_differing_city_under_its_production_conductor"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_production_basis_with_every_city_at_parity_is_refused_with_no_city_differs"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_cli_with_production_at_parity_exits_2_with_no_city_differs"
        status: pass
    human_judgment: false
  - id: D4
    description: "The signed TEST veto: strictly higher per-city MAE than raw_forecast in at least 3 cities with data; 3 of 4 vetoes, 2 does not, a tie is not losing, a city without data is not counted; the report files carry a plain-English summary first"
    requirement: SEL-03
    verification:
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_a_candidate_losing_to_raw_in_three_of_four_cities_is_vetoed"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_a_tie_is_not_losing"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_a_city_without_data_is_not_counted"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_the_veto_of_a_real_run_agrees_with_an_independent_per_city_mae_computation"
        status: pass
      - kind: unit
        ref: "backend/tests/forecast_test_split_score_test.py#test_write_test_report_writes_json_and_a_plain_english_markdown_first"
        status: pass
    human_judgment: false
  - id: D5
    description: "Registry parity: all 58 signed registry keys are mapped (47 to code constants, 3 state-aware O4 checks, 8 DOC_ONLY); an unmapped or stale key or a drifting constant fails; no ABLATION or refit constant differed from the signed copy"
    requirement: SEL-01
    verification:
      - kind: unit
        ref: "backend/tests/protocol_v4_registry_test.py#test_every_registry_key_is_mapped"
        status: pass
      - kind: unit
        ref: "backend/tests/protocol_v4_registry_test.py#test_code_constant_equals_the_signed_value (47 parametrized cases)"
        status: pass
      - kind: unit
        ref: "backend/tests/protocol_v4_registry_test.py#test_production_table_row_matches_the_signed_o4_choice (3 parametrized cases)"
        status: pass
      - kind: integration
        ref: "pytest backend/tests (full suite, 2566 passed, 82 skipped)"
        status: pass
    human_judgment: false

duration: 13min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 10: TEST-Split Scorer, Signed TEST Veto and Registry Parity Summary

**The per-city TEST-split scorer is built and tested on synthetic frames only: it reads just the cached `_2024-01-20_2026-09-29_` frames, refuses to run unless v4 is signed, scores under either the frozen-Drake or the production (AUSTIN at Drake 100 C) conductor basis, applies the signed "strictly worse than raw_forecast in at least 3 cities" veto and never names a pick; a registry test now pins all 58 signed v4 keys to the code, and no constant needed correcting. The real TEST run was not made (that is 07-11).**

## Performance

- **Duration:** 13 min (one 3 min 46 s full-suite run)
- **Started:** 2026-11-02T08:34Z
- **Completed:** 2026-11-02T08:47Z
- **Tasks:** 2
- **Files modified:** 3 created (`backend/forecast_test_split_score.py`, `backend/tests/forecast_test_split_score_test.py`, `backend/tests/protocol_v4_registry_test.py`)

## Accomplishments

- **Provider (T-07-21).** `cached_test_provider(city, *, evidence_dir)` builds the cache path from `FROZEN_WINDOW_START/END`, calls `assert_not_fresh_experiment_cache` on it, refuses a missing file with a message naming the path (`FrameFetchError`, no network, nothing written), reads it through `anchored_pair_frame` as a cache hit, refuses a frame holding any row on or after 2026-09-30T00Z, builds archive weather from the frame's own truth columns and returns the path and sha256 in the meta. Tests redirect the cache to a tmp directory and an autouse spy fails any open of the real `data/experiment`.
- **Scorer.** `run_test_split` refuses unless `core.v4_signed()`, validates the conductor basis and that the window lies inside `[2026-03-18, 2026-09-30)`, then calls `run_confirmation` with the injected provider, a development basis and an explicit loader. `frozen-drake` passes no point resolver; `production` passes `city_point.production_city_point` and the hash-verified headline loader for the differing cities and is refused when no city differs or an artifact is unsound. Per city, `n_in_scope` and `n_with_truth` must equal the expected 784, naming the city and both counts otherwise.
- **Veto.** `evaluate_test_vetoes` reads each (candidate, raw_forecast) comparison; a city loses when its margin is below 0, a tie or an empty city does not count, and a candidate is vetoed at 3 or more losing cities. It returns the losing cities, per-city (candidate MAE, raw MAE) pairs and reasons, and refuses a report with no such comparison.
- **Report.** `write_test_report` writes `test_split.json` and `test_split.md` into a new directory (refused if it exists or lies inside the frozen model directory); the markdown opens with a plain-English section saying, per candidate, where it beats raw_forecast and whether it would be vetoed. CLI: `--conductor-basis`, `--cities`, `--evidence-root` (default `data/shadow/evaluation/v4-test`), `--out-dir` (default `<evidence-root>/report_<UTC stamp>`); any refusal exits 2.
- **Registry parity (T-07-22).** `CODE_MAP` maps 47 keys (rounds, rule, ABLATION including each of the six variant rows, TEST, refit) to constants; `STATE_CHECKS` covers the three O4 rows against the production table; `DOC_ONLY_KEYS` lists eight rows with their reason. Mutating a constant (train rows, a naive timestamp, a variant temperature, refit methods, veto min cities, block lengths) makes its case fail.
- Test counts: TEST scorer 45 tests; registry parity 64 tests (50 parametrized key cases). Full suite 2566 passed, 82 skipped (was 2457 passed).

## Task Commits

1. **Task 1: TEST-split scorer with the cached-frame provider and the signed veto** - `11461da` (feat)
2. **Task 2: Registry parity test pinning every signed value to the code** - `2fac503` (test)

**Plan metadata:** recorded in the docs commit that follows this summary.

## TDD Evidence

- **Task 1 RED:** the 45 tests were written first; running them before the module existed failed at collection with `ModuleNotFoundError: No module named 'forecast_test_split_score'` (a missing-module RED, recorded as such; the plan type is `execute` and prescribes one `feat(07-10)` commit, so there is no separate `test(07-10)` commit and no TDD Gate Compliance section applies). **GREEN:** 45 passed after two test-side fixes (a `KeyError` on `seen["secondary"]` in one spy test); then the TEST suite with the COND-02 golden and the confirm suite (198 passed).
- **Task 2:** the registry test passed on first run with no constant changed. Because that proves nothing by itself, constants were mutated in a throwaway interpreter (`TRAIN_ROWS_PER_CITY` 2361, a tz-naive `VALIDATION_START`, Drake-100 at 101 C, one refit method dropped, `VETO_MIN_CITIES` 2, block lengths `(1,4,8)`) and each case failed as it should; three added tests drive the state-aware O4 checks through the adopted state.

## Files Created/Modified

- `backend/forecast_test_split_score.py` - constants (`TEST_WINDOW_START`, `TEST_WINDOW_END_EXCLUSIVE`, `TEST_SLOTS_PER_CITY`, `VETO_MIN_CITIES`, `EVIDENCE_SUBDIR`, `CONDUCTOR_BASES`, `RESCORE_GATE`), `cached_test_provider`, `run_test_split`, `evaluate_test_vetoes`, `summary_markdown`, `write_test_report`, CLI; `ScoringScopeError`
- `backend/tests/forecast_test_split_score_test.py` - 45 tests (constants, boundary edge, provider refusals, scorer, production basis, veto, report files, CLI)
- `backend/tests/protocol_v4_registry_test.py` - `CODE_MAP`, `STATE_CHECKS`, `DOC_ONLY_KEYS` and the parity tests

## Decisions Made

See `key-decisions` above. The one worth a human glance: the TEST report never carries a decision. `run_confirmation` computes a headline-labelled v4 decision even on a development basis, which on TEST rows could read as a pick; `run_test_split` replaces it with `None` plus a note and rewrites the report files, so only the veto is a TEST output (D-02).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Frozen basis loads through the hash-verified loader**
- **Found during:** Task 1 (loader choice), against the threat of unpickling an unchecked file
- **Issue:** The plan passes `forecast_shadow_pipeline.load_correction_model` for the frozen-drake basis, which unpickles the 12 frozen files with no hash check (07-09 made the same call for its secondary).
- **Fix:** both bases use `forecast_conductor_refit.make_headline_loader`, which checks each file's sha256 against the frozen manifest before `joblib.load`; the frozen basis passes no refit cities. `scored_artifacts` lists every artifact with its hash and source. One consequence: run_started.json labels the loader `injected`, but `scored_artifacts` records source `frozen` with the hash.
- **Files modified:** `backend/forecast_test_split_score.py`
- **Verification:** `test_the_default_loader_of_the_frozen_basis_checks_hashes_before_deserializing` (tampered file raises `ArtifactIntegrityError`)
- **Committed in:** `11461da`

**2. [Rule 2 - Missing Critical] Window and cache refusals before anything is created; TEST decision neutralised**
- **Found during:** Task 1
- **Issue:** (a) `run_confirmation` treats any window reaching 2026-09-30 as a FRESH run, so a mistaken `window` argument was one step from a FRESH read; (b) a missing cache would only surface after an evidence directory existed; (c) the development-basis report would carry a headline-labelled decision.
- **Fix:** `run_test_split` refuses a window outside `[2026-03-18, 2026-09-30)` and, for the cached provider, a missing cache for any city, both before any directory exists; the decision is replaced by `None` plus a note and report.json / report.md are rewritten.
- **Files modified:** `backend/forecast_test_split_score.py`
- **Verification:** the four window-refusal cases, `test_the_full_window_is_the_default_and_the_preflight_names_a_missing_cache_before_creating_evidence`, the dev-fixture run test (decision `None` on disk)
- **Committed in:** `11461da`

**3. [Rule 2 - Missing Critical] Registry test covers the O4 rows with a third, state-aware group; `RESCORE_GATE` constant**
- **Found during:** Task 2
- **Issue:** the plan's two groups (code constants, DOC_ONLY) cannot express `power_systems.switch_cities`, `refit.cities` and `power_systems.austin_config`: their counterpart is the production table, whose AUSTIN row is still the provisional 75 C until a later plan applies the switch (this plan must not edit `config.py`). `test.rescore_gate` also had no code constant.
- **Fix:** `STATE_CHECKS` (provisional state: table at parity, AUSTIN 75 C, all other austin_config fields equal the table and the ABLATION Drake-100 bracket; adopted state, detected by `RATING_CONFIG_VERSION` no longer starting with `v2-provisional`: exactly the signed cities differ, AUSTIN is 100 C, refit artifacts verify); `RESCORE_GATE = "before_read1_run"` added to the TEST module and mapped.
- **Files modified:** `backend/tests/protocol_v4_registry_test.py`, `backend/forecast_test_split_score.py`
- **Verification:** `test_production_table_row_matches_the_signed_o4_choice`, the three adopted-state tests
- **Committed in:** `2fac503`

**4. [Rule 2 - extra parameter] `run_test_split(model_loader=None)` test hook**
- **Issue:** the plan's signature has no way to inject the stub models its own test cases ("stub loader") need.
- **Fix:** an optional `model_loader` keyword (like `provider`); the CLI passes neither.
- **Committed in:** `11461da`

---

**Total deviations:** 4 auto-fixed (4 missing critical / interface). No ABLATION or refit constant differed from the signed copy, so no module constant was corrected.
**Impact on plan:** all four tighten the plan's own mitigations (T-07-21, T-07-22) or fill a gap it left; nothing outside the planned files changed.

## Issues Encountered

- `confirm.conductor_basis()` only checks the frozen artifacts when a city differs, so at parity a tampered frozen file is caught by the loader at load time (`ArtifactIntegrityError`, CLI exit 1) rather than before the run; for TEST this is harmless (no one-shot rule applies to a development basis).
- `forecast_conductor_refit.REFIT_ROOT` is cwd-relative, so the production basis, like the refit CLI, must be run from the repository root.

## Threat Flags

None beyond the plan's register. The only new file access is the TEST provider's read of the pre-FRESH `_2024-01-20_2026-09-29_` caches, which is the surface T-07-21 mitigates (path check, frozen-window name, row-date assertion; all tested).

## Known Stubs

None.

## Safety Notes

- No real confirm or score run was made and no FRESH figure was read. `forecast_shadow_confirm.py` and `forecast_shadow_score.py` were never run as programs (the TEST module imports `forecast_shadow_confirm` as a library and a test pins that it does not name `forecast_shadow_score`). The TEST scorer was never run on real data: every test uses synthetic frames in a tmp cache, stub models and a tmp evidence root, with `requests.get` a bomb and a spy that fails any open of `data/experiment`.
- The only real-data access was a count of rows in the four real `_2024-01-20_2026-09-29_` frames (header and the `datetime_utc` column only): 23,592 rows per city, last row 2026-09-29T23:00Z, and exactly 784 six-hourly slots per city inside the TEST window, so the signed slot count holds on the real frames. No weather value, prediction or error was read. The one real CLI invocation, `--conductor-basis production`, was refused with exit 2 ("no city differs") before any file was opened.
- `git status --porcelain data` printed nothing after the tests and the full suite. No Supabase write, no deploy, no retraining; `data/shadow/models` untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 07-11 can run `forecast_test_split_score.py --conductor-basis frozen-drake` (then `production` once AUSTIN is switched and its refit artifacts exist for the new version). The report to cite in `vetoes.json` is `<evidence-root>/report_<stamp>/test_split.json`; each candidate's veto has `vetoed`, `reasons` and `cities_losing_to_raw` (a list of city names), and `load_vetoes` still needs both candidates and both sections.
- When 07-11 edits `PRODUCTION_CONDUCTORS` and bumps `RATING_CONFIG_VERSION` to `v3-powersystems-...`, the registry test's state checks switch to the adopted rules by themselves: AUSTIN must be at 100 C, only AUSTIN may differ and the refit artifacts must verify.
- `test.rescore_gate` (re-score TEST under production before read 1 is run) is a process gate recorded as `RESCORE_GATE`; nothing in code enforces it, so the 07-11/07-12 runbook must.
- `SEL-03` stays open (other plans in the phase still declare it); `SEL-01` is marked complete.

## Self-Check: PASSED

- `backend/forecast_test_split_score.py`, `backend/tests/forecast_test_split_score_test.py` and `backend/tests/protocol_v4_registry_test.py` exist; commits `11461da` and `2fac503` are ancestors of HEAD.
- The acceptance command prints `784 2026-03-18T00:00:00+00:00 2026-09-29T18:00:00+00:00`; `git status --porcelain data` prints nothing; the plan's verify run (TEST tests with the COND-02 golden, 198 passed with the confirm suite) and the full suite (2566 passed, 82 skipped) are green.

---
*Phase: 07-per-city-conductors-shadow-refit-and-early-model-selection*
*Completed: 2026-11-02*
