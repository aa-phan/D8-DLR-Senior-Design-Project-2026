---
phase: 03-real-data-validation
plan: 04
subsystem: testing
tags: [validation, real-data, report, naive-replay, go-no-go, val-01, val-02, offline-analysis]

requires:
  - phase: 03-real-data-validation
    provides: "03-02: complete 21-day four-city ml backfill, manifest.json (archive sha256), run_completeness.csv"
  - phase: 03-real-data-validation
    provides: "03-03: replay subcommand with fidelity check, VAL-02 tables in report"
provides:
  - "12 committed tables and records under docs/data-science/decisions/real_data_validation/ (VAL-01 x5, VAL-02 x4 with ml and naive_replay rows, replay_fidelity.json, report_meta.json, tables.md), byte-reproducible"
  - "docs/data-science/decisions/real_data_validation.md: per-city results, outlier explanations, ten findings with options, limits, go/no-go questions with measured answers, candidate blocking fixes and three options, Decision section pending"
affects: [03-05 go/no-go decision, 04 DB-03 archive load, 05 live runs]

actuals:
  tokens: 35968
  tasks: 2
  commits: 2

plan_head_before: 9e3ca26949048dcdac1a4f681c16f168623857ac
plan_head_after: 431c7ec4957368a4f0b99020f8e883091d38dbd3

tech-stack:
  added: []
  patterns:
    - "Doc tables are copied verbatim from tables.md by a helper that expands placeholders, then checked row by row (every '|' line of tables.md appears in the doc)"
    - "Analysis runs only after the archive sha256 is recomputed and matched to manifest.json; a second report run into a scratch directory must diff empty"

key-files:
  created:
    - docs/data-science/decisions/real_data_validation/val01_ratings_by_city.csv
    - docs/data-science/decisions/real_data_validation/val01_outcomes_by_city.csv
    - docs/data-science/decisions/real_data_validation/val01_fallback_direction_by_city.csv
    - docs/data-science/decisions/real_data_validation/val01_outliers.csv
    - docs/data-science/decisions/real_data_validation/val01_drivers_by_city.csv
    - docs/data-science/decisions/real_data_validation/val02_forecast_by_city.csv
    - docs/data-science/decisions/real_data_validation/val02_coverage_by_residuals.csv
    - docs/data-science/decisions/real_data_validation/val02_detector_by_city.csv
    - docs/data-science/decisions/real_data_validation/val02_g6_trips.csv
    - docs/data-science/decisions/real_data_validation/replay_fidelity.json
    - docs/data-science/decisions/real_data_validation/report_meta.json
    - docs/data-science/decisions/real_data_validation/tables.md
    - docs/data-science/decisions/real_data_validation.md
  modified: []

key-decisions:
  - "The doc presents measurements, findings and options only; its Decision section holds the single line 'Pending owner decision.' for plan 03-05"
  - "No rating bound, static rating, bearing, conductor model, fallback policy or forecast method was changed; every issue became a finding with options"
  - "VAL-03 is not claimed as completed by this plan: it supplies the input, the owner's decision is taken in 03-05"

requirements-completed: [VAL-01, VAL-02]

coverage:
  - id: D1
    description: "VAL-01/VAL-02 summary tables for the live ml run and the naive replay reference, from the hashed archive, self-checks all zero, replay fidelity 2016 compared and 0 mismatches, byte-identical on a second run"
    requirement: "VAL-01"
    verification:
      - kind: other
        ref: "plan Task 1 verify command: TABLES_OK; diff -r of a second report run empty; secrets grep clean"
        status: pass
    human_judgment: false
  - id: D2
    description: "Validation doc: per-city results, explanations, findings with options, limits, go/no-go section, Decision pending"
    requirement: "VAL-02"
    verification:
      - kind: other
        ref: "plan Task 2 verify command: DOC_OK (headings, every tables.md row copied, archive sha256, provisional label, one pending line); no decision or signature line"
        status: pass
    human_judgment: true
    rationale: "Whether the explanations are credible, the findings and options complete and nothing unfavourable softened is the owner's judgement before the 03-05 decision"
  - id: D3
    description: "Offline naive replay reproduces the real run's G1-G5 outcomes, computed ratings and G6 reach on all 2016 city-steps"
    requirement: "VAL-02"
    verification:
      - kind: other
        ref: "replay exit 0: replay fidelity compared=2016, excluded=0, mismatches=0; replay_fidelity.json identical to the file report wrote"
        status: pass
    human_judgment: false

duration: 14min
completed: 2026-10-21
status: complete
---

# Phase 3 Plan 04: Real-data validation report and go/no-go options Summary

**The real 21-day run was analysed offline (naive replay 2016/2016 faithful, all self-checks zero, report byte-reproducible) and written up per city with the headline that AUSTIN published a value above its computed rating at 68.15% of scored steps (median +780 A), CORPUS_CHRISTI's learned-model detector trips at 11.01%, and the ml band covers 81% to 90% against a 90% nominal, leaving the go/no-go decision to the owner.**

## Performance

- **Duration:** 14 min of executor time
- **Started:** 2026-10-21T05:06Z
- **Completed:** 2026-10-21T05:21Z
- **Tasks:** 2
- **Files modified:** 13 committed (12 tables/records, 1 doc)

## Accomplishments

- Hash gate and analysis: archive sha256 recomputed (`18f999aa...25cf`) and equal to `manifest.json`; naive replay ran in 48 s with exit 0; report exit 0; self-checks all 0; a second report run into a scratch directory gave an empty `diff -r`.
- Tables (`TABLES_OK`): every outcome table sums to 336 scored and 168 warm-up steps per city; labels `ml` and `naive_replay` present in all three per-city VAL-02 tables.
- Validation doc (887 lines): per-city readings, outlier and fallback explanations, ten findings each with options, limits, six measured go/no-go questions, six candidate blocking fixes, three neutral options, `Decision` section with only the pending line, exact reproduce commands.
- Measured headline numbers (scored window, 336 steps per city): upward fallback AUSTIN 229 (68.15%), MIDLAND 70 (20.83%), CORPUS_CHRISTI 32 (9.52%), EL_PASO 0; ml 90% band coverage 0.8108 / 0.8958 / 0.8134 / 0.8839 (AUSTIN / CORPUS_CHRISTI / MIDLAND / EL_PASO; AUSTIN and MIDLAND intervals exclude 0.90); G6 trip rate 0.036 / 0.1101 / 0.0075 / 0.003 (CORPUS_CHRISTI, all learned-model votes, above the 0.05 reference); no exhausted step, error, silent forecast failure or detector error.

### Replay, report and determinism record

- Replay: `replay fidelity: compared=2016, excluded=0, mismatches=0, mismatch_outcome=0, mismatch_computed=0, mismatch_g6_reach=0`, exit 0.
- Report: exit 0; `report_meta.json` self-check counts all 0 (computed vs reported, archive vs trace, duplicate slots, rows dropped, outside window, trace duplicates, out of window, replay fidelity).
- `diff -r -x manifest.json -x run_completeness.csv` between the committed output directory and a fresh scratch run: empty (exit 0).

## Task Commits

1. **Task 1: Naive replay, full report, determinism proof, commit tables** - `0ef5e91` (docs)
2. **Task 2: Validation doc with findings, options and go/no-go section** - `431c7ec` (docs)

**Plan metadata:** the SUMMARY commit and the state/roadmap commit follow this file.

## Files Created/Modified

- `docs/data-science/decisions/real_data_validation/val01_*.csv` (5) - VAL-01 ratings, outcomes (all twelve), fallback direction, outliers, drivers
- `docs/data-science/decisions/real_data_validation/val02_*.csv` (4) - VAL-02 forecast, coverage by residuals, detector, capped G6 trips (ml and naive_replay rows)
- `docs/data-science/decisions/real_data_validation/{replay_fidelity,report_meta}.json`, `tables.md` - records and Markdown rendering
- `docs/data-science/decisions/real_data_validation.md` - the validation doc

## Decisions Made

- Findings stay findings: nothing in rating policy, models or code was touched (`git log 9e3ca26..HEAD -- backend` lists 0 commits).
- The Decision section is the single pending line; no recommendation is written (the only use of "recommend" is the sentence saying the section does not recommend).
- VAL-03 is left open: this plan is its input, the owner decides in 03-05.

## Deviations from Plan

None - plan executed exactly as written (see Discrepancies for acceptance-check wording that cannot hold literally).

## Discrepancies

- **Commit trailer:** both commits end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` (the trailer this environment specifies), not the plan's `Claude Opus 5.5` text (orchestrator-approved, as in 03-01 to 03-03).
- **Task 1 acceptance `! git ls-files | grep '^data/'`:** fails literally because 31 files under `data/` were already tracked by earlier milestones (fixtures, `data/shadow/models`, `data/publication_lag_check`, `data/reanalysis_revision_check`, station CSVs). The intent (no raw or replay data from this phase is committed) holds: `git ls-files data/historical` lists 0 files, the replay outputs and the archive show as ignored, and commit `0ef5e91` lists only the twelve planned files.
- **Task 2 acceptance policy grep:** `git log --format=%s -- backend | grep '(03-04)'` matches three commits of an earlier milestone with the same scope (`0eb453a`, `1618d8a`, `952a0b3`). The intent (this plan changed no backend file) was verified with the range form: `git log 9e3ca26..HEAD -- backend` lists 0 commits, and `git show --name-only` of `431c7ec` lists only the doc.
- **Withheld-forecast expectation (plan Task 2, VAL-02 text):** the plan expected forecasts withheld from G6 "only after exhausted or errored steps". There are no exhausted or errored steps, yet `n_withheld_gap` is 96 / 103 / 99 / 6 (ml). The doc explains the real cause (Finding 8): Phase 2 cleaning excludes fallback rows from the history, each fallback leaves a missing hourly slot, and ml needs 7 consecutive usable hours before it may gate G6. This is a finding for the owner, not a bug fixed here.
- **`replay_fidelity.json`:** `report` writes it into the output directory itself; it is byte-identical to the file the `replay` command wrote (`diff` empty), so there is one fidelity record.
- **Doc assembly:** the tables were expanded into the doc from `tables.md` by a throwaway helper kept outside the repository (placeholders replaced by the section's `|` rows), then verified row by row by the plan's own check. Prose numbers were checked against the tables; a few exact counts (air-temperature source shares, observation lag, local-hour distribution of fallbacks, wind-direction share near the line axis, usable-row and forecast-withholding facts for one Midland sequence) come from a read-only pass over the git-ignored trace and are marked "trace" in the doc.
- **VAL-02 wording:** REQUIREMENTS.md says "naive/EWM forecast band"; per OD-3 this plan measures the live ml band with naive as a replay reference. EWM was not replayed (stated in the doc).
- **Requirements:** `requirements-completed` lists VAL-01 and VAL-02 only; VAL-03 (signed decision) is deliberately not claimed.
- **Baseline:** the full suite is unchanged by this plan: 1397 passed, 0 failed.

## Issues Encountered

None.

## Known Stubs

None. The only placeholder-like content is the intentional `Pending owner decision.` line that plan 03-05 fills.

## Threat Flags

None. No network endpoint, auth path, file-access pattern or schema was added; only derived aggregates were committed (credential-shaped pair grep clean).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 03-05 (blocking-human checkpoint): the owner reads `docs/data-science/decisions/real_data_validation.md`, then states GO, GO WITH CONDITIONS or NO-GO; 03-05 fills the `## Decision` section from that reply.
- Inputs carried to Phase 4: archive sha256 and 504-rows-per-city counts, the OD-7 slot versus observation-hour distinction, the OD-8 window lapse on 2026-10-28 and the need for a contiguous history to go-live (Finding 6), the model sha256 list for OD-10.

## Self-Check: PASSED

- All 13 committed files exist; commits `0ef5e91` and `431c7ec` are ancestors of HEAD and list exactly the planned files (12 and 1).
- `TABLES_OK` and `DOC_OK` printed; doc has the required headings, 887 lines, one `Pending owner decision.` line, no decision or signature line.
- Replay fidelity 0 mismatches of 2016; second report run `diff -r` empty; no `data/historical` file tracked; full suite 1397 passed.

---
*Phase: 03-real-data-validation*
*Completed: 2026-10-21*
