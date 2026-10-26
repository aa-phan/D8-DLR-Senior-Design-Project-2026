---
phase: 06-exposure-e2e-verification
plan: 07
subsystem: testing
tags: [soak, freshness, probe-log, breach-causes, deploy-annotations, runbook, cron-job-org, e2e-02, e2e-03, d-08, d-13, d-14, d-15, d-09]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "06-03: e2e_soak_report.py dry mode (export, load_inputs, evaluate_dry, render); 06-05: ops.freshness_log, job dlr-soak-freshness and the owner SQL files; 06-04: e2e_verify_readonly.py flags; 06-01: verify_exposure.sql and latest_rating_contract.STALE_AFTER_MINUTES"
  - phase: 05-scheduled-live-runs
    provides: "dlr_live_window_check.evaluate_window slot verdicts and pipeline_run cities_failed shape, used for breach causes"
provides:
  - "e2e_soak_report.py soak mode: export --mode soak (adds probes.csv) and report --mode soak (72 h breach list with causes, probe coverage, derived deploys, owner annotations)"
  - "Runbook sections 14 (permanent freshness alarm), 15 (soak monitoring), 16 (permission re-check on or after 2026-10-31), plus the section 6 pause rule and the section 11 pointer"
  - "backend/tests/monitoring_runbook_test.py pinning the runbook to the scripts' real flags, the job name and the thresholds"
affects: [06-09, 06-10, 06-12, 06-13]

actuals:
  tokens: 25917
  tasks: 3
  commits: 3
plan_head_before: 9333aaf82f6a42b9e80ae5e1f8c25a8879c7c36e
plan_head_after: bf17f1648894f92e67121c8b26b04ad7a967b624

tech-stack:
  added: []
  patterns:
    - "Exact write-based breach intervals: running maximum valid_time over first_written_at, seeded from the newest live row first written before G; a breach starts when the age reaches 90 min and exists only if the interval ends strictly after it (exact timedelta)"
    - "Probe log as coverage evidence: distinct probe times against the expected count, gaps longer than 2 x interval + 1 min including both window edges, incomplete probes listed"
    - "A breach is explained only by a rule-derived cause (Phase 5 slot verdicts, pipeline_run, late-run rule) or an owner annotation; a deploy is context and never an excuse"
    - "git called with an argv list only for versions that are 7-40 lowercase hex; anything else is flagged, never guessed"
    - "Runbook pinned to the tools: flags parsed from each script's own --help, job name and cron read from the owner SQL"

key-files:
  created:
    - backend/tests/monitoring_runbook_test.py
  modified:
    - backend/e2e_soak_report.py
    - backend/tests/e2e_soak_report_test.py
    - docs/data-science/decisions/dlr_live_runbook.md

key-decisions:
  - "A breach interval starts at the instant the age reaches the limit and is a breach only when it ends strictly after it, so exactly 90 minutes is fresh in the write measure, the probe log and the report"
  - "A deploy is context (two hours before a breach, up to its end) and never explains a breach; only a rule-derived cause or an owner annotation does"
  - "Unrecognised changed paths classify as 'other', not as harmless: nothing is guessed"

patterns-established:
  - "Soak report CLI: export --mode soak; report --mode soak [--min-hours 72] [--probe-interval-min 5] [--annotations FILE]; exit 0/1/2"

requirements-completed: [E2E-02, E2E-03]

coverage:
  - id: D1
    description: "export --mode soak also writes probes.csv from ops.freshness_log in the same read-only session with bound parameters"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/e2e_soak_report_test.py#test_tracer_soak_export_then_report"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_soak_export_reads_probes_read_only_and_bound"
        status: pass
    human_judgment: false
  - id: D2
    description: "Exact write-based breach intervals with the strict 90 minute rule (exactly 90 is fresh, 90 min 2 s is a breach even though it displays 90.0), no-prior-row cities, late fills and backfill ignored, deterministic order and byte-identical reports"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_soak_exactly_90_minutes_is_not_a_breach"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_city_without_a_prior_row_breaches_from_window_start"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_soak_late_fill_and_backfill_are_ignored"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_soak_order_and_byte_identical_reports"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_report_rule_matches_the_contract"
        status: pass
    human_judgment: false
  - id: D3
    description: "Probe coverage: gaps (edges included), zero probes, short windows fail; probe breaches merge into write breaches or stand alone; incomplete probes are listed"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_probe_gaps_and_empty_or_short_windows_fail"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_probe_breaches_merge_into_write_breaches"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_incomplete_probe_is_listed"
        status: pass
    human_judgment: false
  - id: D4
    description: "Every breach has a rule-derived cause or needs an owner annotation (printed verbatim with author and date); malformed annotations exit 2; unknown ids warn"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_causes_follow_the_slot_verdicts"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_unexplained_breach_fails_without_annotation"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_annotation_explains_an_unexplained_breach"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_unknown_or_malformed_annotations"
        status: pass
    human_judgment: false
  - id: D5
    description: "Deploys are derived from the rows, classified through git with validated versions, listed beside the owner's events, and shown as breach context without excusing it (D-08)"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_derive_deploys_classifies_version_changes"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_unknown_pipeline_version_is_flagged"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_deploy_is_context_not_an_excuse"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_manual_events_are_listed_in_time_order"
        status: pass
    human_judgment: false
  - id: D6
    description: "Runbook sections 14, 15, 16 exist, state the alarm rule and the response, the soak commands and teardown, and the five-check re-check; flags, job name and thresholds match the scripts; no secret-shaped line"
    requirement: E2E-03
    verification:
      - kind: unit
        ref: "backend/tests/monitoring_runbook_test.py#test_runbook_names_match_the_tools"
        status: pass
      - kind: unit
        ref: "backend/tests/monitoring_runbook_test.py#test_alarm_section_states_the_rule_and_the_response"
        status: pass
      - kind: unit
        ref: "backend/tests/monitoring_runbook_test.py#test_runbook_has_no_secret_shaped_lines"
        status: pass
    human_judgment: false
  - id: D7
    description: "Whether the runbook's alarm setup, soak and 10-31 re-check procedures work against the live cron-job.org account and Supabase project is not known until the owner runs them (06-09, 06-10, 06-12, 06-13)"
    requirement: E2E-02
    verification: []
    human_judgment: true
    rationale: "This plan builds the instrument and the instructions and proves them on fixtures; every live step is an owner checkpoint (D-06) and the report has never run on real soak data"

duration: 13min
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 07: Soak report and operator runbook Summary

**72 h soak mode for e2e_soak_report.py (exact write-based breaches, probe coverage, rule-derived causes, deploys derived from the rows and classified through git, owner annotations) plus runbook sections 14 to 16 for the permanent cron-job.org freshness alarm, soak monitoring and the post-2026-10-30 permission re-check, with a test pinning the runbook to the tools**

## Performance

- **Duration:** 13 min
- **Started:** 2026-10-26T21:54:00Z
- **Completed:** 2026-10-26T22:06:48Z
- **Tasks:** 3
- **Files modified:** 4 (1 new test, 3 edited)

## Accomplishments

- In plain English the soak report now says: "for three days the current rating of each city was never more than 90 minutes old, or each exception has a stated cause; every deploy in that time is listed." Anything it cannot explain fails the run, so nobody has to trust the instrument.
- Breaches come from the writes themselves, not from sampling: a rating is a breach only if the interval in which it was the newest is strictly longer than 90 minutes on the exact timedelta. The five-minute probe log is cross-checked (probe counts per breach), and a probe breach no write explains, a gap in the log, a late-starting or early-ending log, zero probes or a window under 72 h all fail the report.
- Causes are derived from Phase 5's records (no run for the slot, a red run, the city in `cities_failed` with its redacted error, a row written more than 30 minutes after its slot). A deploy within two hours before a breach appears as context; it never explains it.
- The runbook now tells an operator how to run, read, pause and answer the alarm, how to run and tear down the soak, and how to run the 10-31 re-check. `monitoring_runbook_test.py` fails if a flag, the job name or a threshold the runbook quotes drifts from the code.

## Soak-mode CLI as built

```
python backend/e2e_soak_report.py export --mode soak --since ISO --until ISO --out-dir DIR
python backend/e2e_soak_report.py report --mode soak --in-dir DIR [--min-hours 72] [--probe-interval-min 5]
       [--max-age-min 90] [--annotations FILE] --out FILE.md [--json-out FILE]
```

- `export --mode soak` writes everything the dry export writes plus `probes.csv` (probed_at, city, latest_valid_time, age_seconds, breach) from `ops.freshness_log`: one read-only session, bound parameters, no URL in any output. It fetches the Actions runs from two hours before the first slot so causes for a breach at the window start can be attributed. `export_meta.json` carries `mode: soak` and `rows.probes`.
- `report --mode soak` reads the files offline (no wall clock, byte-identical on rerun). `--min-hours` defaults to 12 for dry and 72 for soak. Exit 0 only when the window is at least `--min-hours`, probes are present and every breach and probe gap has a cause or an annotation; 1 otherwise; 2 on missing or malformed input or annotations (stderr names the file or key).
- Breach ids are `<kind>:<city>:<start ISO>`, kinds `write`, `probe`, `probe-gap` (city `ALL`); order is start time, then `config.LOCATIONS` order, then kind. JSON breach fields: id, kind, city, start, end, duration_min, peak_age_min (null with no rating), probe_count, ended_by, cause, context, explanation. Result also carries `probe_coverage` (expected, found, gap_limit_min, gaps, incomplete), `trailing_age`, `deploys`, `events`, `warnings`, `failures`, `verdict`, `lines`.
- Functions: `PROBES_SQL`, `SOAK_MIN_HOURS = 72`, `PROBE_INTERVAL_MIN = 5`, `LATE_RUN_MIN = 30`, `export_window`, `write_breaches`, `probe_findings`, `merge_breaches`, `evaluate_soak`, `attribute_causes`, `derive_deploys`, `load_annotations`. `DEFAULT_MAX_AGE_MIN` is now `latest_rating_contract.STALE_AFTER_MINUTES` (tested equal to 90).

## annotations.json format

```json
{
  "breaches": {"<breach id>": {"explanation": "<text>", "by": "<owner>", "date": "YYYY-MM-DD"}},
  "events": [{"time": "<ISO UTC>", "what": "<text>", "by": "<owner>"}]
}
```

Both keys are optional; an unknown key, a non-object entry, a blank field, a bad date or time, or a file that is not valid JSON exits 2. An id that matches no breach is a warning, not an excuse. Explanations are printed verbatim (own section of the markdown, with author and date); events are sorted by time and listed beside the derived deploys.

## Task Commits

1. **Task 1 (tracer): soak-mode export with probes and the write-based breach list** - `f50900c` (feat)
2. **Task 2: cause attribution, derived deploys and owner annotations (D-08)** - `a08fbb8` (feat)
3. **Task 3: runbook sections 14 to 16 and the runbook test** - `bf17f16` (docs)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

Tracer gate: Task 1's `<verify>` carries only `<automated>`, so it was re-run after the commit (28 passed) and the plan expanded.

## Files Created/Modified

- `backend/e2e_soak_report.py` - soak mode (export, report, breaches, causes, deploys, annotations); dry mode unchanged in behaviour
- `backend/tests/e2e_soak_report_test.py` - 33 test functions (13 from 06-03, 20 new; 56 cases), all offline with fake connection, fake `gh run list`, fake git runner and fixture files
- `docs/data-science/decisions/dlr_live_runbook.md` - sections 14, 15, 16; section 6 pause rule; section 11 and section 6 now point at the alarm instead of "Phase 6's freshness check"
- `backend/tests/monitoring_runbook_test.py` - 7 tests tying the runbook to the tools

## Decisions Made

- The breach threshold is applied to the exact timedelta in all three places (write interval, probe log, report); a boundary test covers 90:00, 90:02 (displays 90.0) and 90:06.
- Deploy classification never guesses: an unknown commit, a version that is not 7 to 40 lowercase hex (never passed to git), an unchanged `pipeline_version` with a changed column, and paths outside the known runtime classes are all flagged.
- Probe visibility is strict in the test fixtures (a probe at the instant of a write has not yet seen it), matching the transaction ordering the real log has.

## Deviations from Plan

None under Rules 1 to 4. The following are choices inside the plan's intent, recorded under Discrepancies.

**Total deviations:** 0 auto-fixed. **Impact on plan:** none.

## Issues Encountered

None. The full suite was run once after Task 3 (1906 passed, 81 skipped); `git status --porcelain -- data/shadow .github` is empty. Nothing was pushed and the live project was never contacted.

## Discrepancies

- **Commit trailer:** the plan asked for `Co-Authored-By: Claude Opus 5.5`; the session's attribution instruction replaced it, so all three task commits end with `Co-Authored-By: Claude Sonnet 5.5` and the `Claude-Session` line (as in 06-03 to 06-06).
- **`events` name collision:** the plan says the JSON adds `events` (the owner's manual events), but the dry statistics already use `events` for the advancing writes. In soak mode the advancing writes are moved to `advances` and `events` holds the owner's events; dry-mode JSON is unchanged.
- **Cause when a red run also lost a city:** the plan's rules are first-match. A red run whose `pipeline_run` row names the city would then hide the detail, so the cause is "workflow run <id> concluded failure; city failure: <outcome> (<redacted error>)". Each rule alone gives exactly the plan's text.
- **Cause wording for an unfinished run:** a slot verdict `missing` with a run that never finished says "workflow run <ids> did not finish (...)"; "no workflow run for slot <slot> (dispatch missing)" is kept for a slot with no run at all.
- **Cause for a city with no rating before G:** the plan names the first slot after the city's newest rating, which does not exist here. The slot inspected is the one just before the city's first row in the window (or the first window slot when it has none).
- **Deploy classes:** the plan names five classes. Added `other` (a changed path outside every known class is flagged as a deploy, not assumed harmless) and treat `backend/tests/`, `data/shadow/`, `supabase/` and `.github/` (apart from `dlr_live.yml`) as "no runtime change" so test-only and shadow-data commits do not flood the event list. An unchanged `pipeline_version` with a changed column is listed with class "unknown: pipeline_version unchanged, no commits to compare" (nothing to diff).
- **Incomplete probes:** listed in the report and as a warning, not a failure, exactly as the plan says; a probe missing a city is a coverage note, not a breach.
- **Annotations are validated strictly:** unknown keys and extra entry keys exit 2 (a typo such as `breach` would otherwise drop every annotation silently). Task 1 read the annotations file with a minimal loader; Task 2 replaced it with `load_annotations`.
- **Task 1 test updated in Task 2:** once causes exist, the 90 min + 2 s / + 6 s cases are explained as a late run (exit 0, cause starts "late run: written +30"); the test now asserts that. The other Task 1 breach tests use a dropped row with an intact run, which no rule explains.
- **TDD commits:** Tasks 2 and 3 are `tdd="true"` but the plan prescribes one commit per task. RED was observed before implementing both (Task 1: 13 new tests failed; Task 2: 39 failed; Task 3: 7 failed).
- **Runbook shows `--since 2026-10-25T00:00:00Z` for the dry export** (the live window start used by Phase 5's check); the owner substitutes their own times.

## Known Stubs

None. (`<DRY_DIR>`, `<G>`, `<U>`, `<SUPABASE_URL>` and similar are deliberate placeholders in the runbook: D-10 forbids real values.)

## Threat Flags

None. The new surface is the plan's own threat model: the git call with database-derived strings (T-06-24, argv list plus hex validation, tested), annotation trust (T-06-23, printed verbatim, never written by the tool) and runbook secrets (T-06-26, placeholders plus a line scan).

## User Setup Required

None for this plan. Owner steps that use the new instruments: creating the cron-job.org "DLR freshness alarm" (section 14, with the 2-failure email, recovery and job-disabled email), enabling Cron and running the soak SQL (section 15), and the 10-31 re-check (section 16); they belong to 06-09, 06-10, 06-12 and 06-13.

## Next Phase Readiness

- 06-09 and 06-10 can set up the alarm and start the soak from section 14 and 15; 06-12 can run `report --mode soak` and the teardown; 06-13 can run section 16.
- Open assumption carried forward: deploy classification needs both commits in the local clone; a commit pushed from elsewhere is flagged "run git fetch" until fetched.
- The soak report has only been exercised on fixtures; the first real export will be the first check against live rows.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-26*

## Self-Check: PASSED

- backend/e2e_soak_report.py, backend/tests/e2e_soak_report_test.py, backend/tests/monitoring_runbook_test.py and docs/data-science/decisions/dlr_live_runbook.md exist on disk.
- Commits f50900c, a08fbb8 and bf17f16 are ancestors of HEAD; `git rev-list --count 9333aaf..HEAD` before this SUMMARY is 3.
- Acceptance criteria re-run: write_breaches, probe_findings, evaluate_soak, derive_deploys, attribute_causes and load_annotations each defined once; `ops.freshness_log` and `dlr_live_window_check.evaluate_window` referenced; 33 test functions in e2e_soak_report_test.py (at least 30) and 7 in monitoring_runbook_test.py; section headings 14, 15 and 16 each present once; `dlr-soak-freshness` named in the runbook.
- Verification: e2e_soak_report_test, monitoring_runbook_test, dlr_live_runbook_test and secret_scan_test pass; full suite 1906 passed, 81 skipped; `git status --porcelain -- data/shadow .github` is empty.
