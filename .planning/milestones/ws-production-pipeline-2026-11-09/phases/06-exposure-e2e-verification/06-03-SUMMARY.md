---
phase: 06-exposure-e2e-verification
plan: 03
subsystem: testing
tags: [soak, freshness, dry-soak, psycopg, read-only, e2e-02, d-07]

requires:
  - phase: 05-scheduling-and-live-runs
    provides: "backend/dlr_live_window_check.py (evaluate_window, fetch_runs, format_report) and the live rows written since 2026-10-25"
  - phase: 04-supabase-store-writer
    provides: "supabase_store.connect(), StoreError and redact()"
provides:
  - "backend/e2e_soak_report.py: `export --mode dry` (owner, read-only) and `report --mode dry` (offline) for the D-07 dry soak"
  - "Pure evaluators (load_inputs, advance_events, evaluate_dry, render_markdown, render_json) that the 72 h soak mode in 06-07 reuses"
affects: [06-07, 06-10]

actuals:
  tokens: 13300
  tasks: 2
  commits: 2
plan_head_before: 736ae4e4c35c8470221c3f3140922a92b22c8a5e
plan_head_after: a85a3e729c62bf121c341afabf75fdb5f75899e2

tech-stack:
  added: []
  patterns:
    - "Exact peak age: running per-city maximum valid_time over rows in first_written_at order, seeded from the newest row first written before --since"
    - "Breach decided on the exact timedelta (strictly over 90 min), never on the one-decimal display value"
    - "Read-only export: set default_transaction_read_only = on before the first query, bound parameters only, failure printed as exception type plus redact()"
    - "Report output carries no wall-clock time, so the same inputs give byte-identical markdown and JSON"

key-files:
  created:
    - backend/e2e_soak_report.py
    - backend/tests/e2e_soak_report_test.py
  modified: []

key-decisions:
  - "Lag and peak age use first_written_at (immutable first insert), not computed_at, so an OD-7 retry cannot inflate them; last-write lag (computed_at minus valid_time) is shown as an informational column"
  - "A late-filled older slot never advances the running maximum, so it is never a breach; it is counted and listed in its own informational section instead of being dropped"
  - "The age of the newest rating at --until is also held to the 90 min limit (stricter than the plan's verdict rule)"

patterns-established:
  - "Report inputs are four files (writes.csv, runs.csv, gh_runs.json, export_meta.json); since and until come from export_meta.json so the report cannot be run against a different window than was exported"

requirements-completed: [E2E-02]

coverage:
  - id: D1
    description: "export reads the live window read-only (read-only setting first, SELECT-only SQL with bound parameters) and writes the four files without any URL, host or credential"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_export_is_read_only_and_bound"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_export_never_leaks_the_url"
        status: pass
    human_judgment: false
  - id: D2
    description: "export then report end to end gives write lag 8 min, peak age 68 min, every slot ok and a PASS verdict on fixtures"
    requirement: E2E-02
    verification:
      - kind: integration
        ref: "backend/tests/e2e_soak_report_test.py#test_tracer_export_then_dry_report"
        status: pass
    human_judgment: false
  - id: D3
    description: "Retries, backfill rows, late fills and fallback rows do not distort lag or peak age; a missing slot is a 128.0 min breach and exit 1"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_retry_rewrite_does_not_inflate_lag"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_backfill_rows_are_ignored"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_late_fill_of_an_old_slot_is_not_a_breach"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_missing_slot_is_a_128_minute_breach"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_fallback_share_is_informational"
        status: pass
    human_judgment: false
  - id: D4
    description: "The 90 minute boundary holds on the exact timedelta: 90.0 passes, 90.1 and a value that displays as 90.0 but is 2 s over both breach; above 75 warns"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_exactly_90_minutes_is_within_budget"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_peak_over_75_warns_but_passes"
        status: pass
    human_judgment: false
  - id: D5
    description: "Short or empty windows exit 1, bad input exits 2 naming the file or column, and output is ordered by config.LOCATIONS and byte-identical on rerun"
    requirement: E2E-02
    verification:
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_short_or_empty_window_fails"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_bad_input_exits_2"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_soak_report_test.py#test_output_order_and_byte_identical_reports"
        status: pass
    human_judgment: false
  - id: D6
    description: "Whether the real live rows since 2026-10-25 land within the 90 minute budget (the actual dry-soak result) is not known until the owner runs export in 06-10"
    requirement: E2E-02
    verification: []
    human_judgment: true
    rationale: "This plan builds the instrument and proves it on fixtures; the live export is owner-run (D-06) and the owner reviews the numbers before the 72 h clock starts"

duration: 7min
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 03: Dry-soak export and report Summary

**Read-only `export` of the live city_rating and pipeline_run rows plus an offline `report` that turns them into exact write-lag and peak-age statistics (first_written_at based, 90 minute rule on the exact timedelta) with Phase 5's slot verdicts reused**

## Performance

- **Duration:** 7 min
- **Started:** 2026-10-26T20:16:34Z
- **Completed:** 2026-10-26T20:23:00Z
- **Tasks:** 2
- **Files modified:** 2 (both new)

## Accomplishments

- One owner command exports the existing live window read-only; one offline command computes the dry soak. In plain English the report says: "the hours already recorded show each hourly rating lands within about N minutes, and the oldest the current rating ever got was M minutes, against the 90 minute limit."
- Exact peak age that retries, backfill rows and late fills cannot distort, with a hard 90.0 versus 90.1 boundary decided on the exact timedelta.
- Fallback share reported per city as informational only (a fallback row is a fresh row, so AUSTIN's static-rating hours are not breaches).
- The same report answers Phase 5's 24 h slot check, because it embeds `dlr_live_window_check.evaluate_window`'s table instead of re-implementing it.

## CLI as built

```
python backend/e2e_soak_report.py export --mode dry --since ISO --until ISO --out-dir DIR
python backend/e2e_soak_report.py report --mode dry --in-dir DIR [--min-hours 12] [--max-age-min 90] --out FILE.md [--json-out FILE]
```

- `export` writes `writes.csv` (14 columns of live rows), `runs.csv` (cities_ok and cities_failed as JSON text), `gh_runs.json` and `export_meta.json` (mode, since, until, exported_at, row counts, short git HEAD; no URL). Timestamps are ISO 8601 UTC with Z. It returns 1 on failure and prints the exception type plus `supabase_store.redact(...)` text; nothing is written when a read fails. `main` and `export_dry` take injectable `connect_fn` and `fetch_runs_fn`.
- `report` reads since and until from `export_meta.json`. Exit 0: window at least `--min-hours` (12), no peak age (or age at the end of the window) strictly above `--max-age-min` (90), no slot missing or incomplete, no city without a row. Exit 1 otherwise. Exit 2: missing or malformed input, naming the file or column. A peak age above 75 prints "a single slow hour would breach" (stdout and report).
- `.env` is loaded only inside the `if __name__ == "__main__":` block.

## evaluate_window interface used

`dlr_live_window_check.evaluate_window(runs, run_rows, rating_rows, start, hours)` with `runs` from `gh_runs.json`, `run_rows` from `runs.csv` (window_end parsed), `rating_rows = [{city, valid_time, run_id}]` from live writes first written before `--until`, `start` = `--since` truncated to the hour, `hours` = whole hours from there to `--until`. Its `slots`, `minutes` and `passed` come back unchanged inside the result under `slots`, and `format_report` renders the table. `dlr_live_window_check.fetch_runs(start, hours)` is the default `fetch_runs_fn`.

## Task Commits

1. **Task 1 (tracer): export to files, then the dry report from those files** - `b05201b` (feat)
2. **Task 2: dry-report edge cases** - `a85a3e7` (test)

**Plan metadata:** committed with this SUMMARY (docs: complete plan)

## Files Created/Modified

- `backend/e2e_soak_report.py` - export and report for the dry soak; `DEFAULT_MAX_AGE_MIN`, `WARN_PEAK_MIN`, `DRY_MIN_HOURS`, `WRITES_SQL`, `RUNS_SQL`, `load_inputs`, `advance_events`, `evaluate_dry`, `render_markdown`, `render_json`, `main`
- `backend/tests/e2e_soak_report_test.py` - 13 test functions (15 cases), fully offline: fake connection, fake `gh run list`, fixture files

## Decisions Made

- first_written_at, not computed_at, drives lag and peak age (as the plan and 06-RESEARCH Pitfall 14 require); last-write lag is an informational column.
- Late fills and backfill rows: backfill is excluded everywhere; a late fill is not an advancing write, so it stays out of the lag and peak statistics but is listed in its own section, never hidden.
- Trailing age at `--until` is a failure condition when strictly over 90 (see Discrepancies).
- Slots are the whole hours from `--since` truncated to the hour; a slot is compared against rows first written before `--until`.

## Deviations from Plan

None - plan executed exactly as written, apart from the points under Discrepancies (all within the plan's intent; no Rule 1-4 fix was needed).

## Issues Encountered

None. No live export was run: this plan builds the instrument and proves it on fixtures (D-06); the owner runs `export` in 06-10.

## Discrepancies

- **Commit trailer:** the plan asked for `Co-Authored-By: Claude Opus 5.5`; the session's attribution instruction replaced it, so both commits end with `Co-Authored-By: Claude Sonnet 5.5` and the `Claude-Session` line.
- **Trailing age is part of the verdict:** the plan's exit rule names only the max peak age. If the newest rating is strictly older than 90 min at `--until`, no later write exists to create an event, so the staleness would otherwise go unseen. The report fails in that case and states the age per city. Healthy windows are unaffected.
- **D-07 wording:** CONTEXT D-07 says "write lag and peak age from computed_at"; the plan (and Pitfall 14) use first_written_at. Followed the plan; computed_at appears only as the informational last-write lag.
- **TDD commits:** Task 2 is `tdd="true"` but the plan prescribes one commit per task, so there is no separate RED commit. RED was observed before implementing: 4 of the 10 new tests failed (75 min warning, late-fill count, short and empty window, bad input column). The other 6 (retry, backfill, missing slot, 90 min boundary, fallback share, ordering) already held because Task 1's tracer implemented the core walk exactly; they are regression locks, not newly green behaviour.
- **Missing-slot wording:** with one city's row lost but the run present, `evaluate_window` reports the slot `incomplete`; `missing` appears when the whole slot (run and rows) is absent. The test covers both; exit is 1 either way.
- **report takes no --since/--until:** the window comes from `export_meta.json`, so it cannot differ from what was exported.

## User Setup Required

None - no external service configuration required. Owner step later (06-10): run `export` from the main checkout with `SUPABASE_DB_URL` set and `gh` authenticated.

## Known Stubs

None.

## Threat Flags

None. The only new trust boundary (the owner's privileged connection) is the one in the plan's threat model (T-06-09, T-06-10, T-06-11), each covered by a test.

## Next Phase Readiness

- `evaluate_dry`, `advance_events` and `load_inputs` are ready for 06-07 to extend with the 72 h soak mode (`--mode` currently accepts only `dry`).
- 06-10 can run `export` against the live project and the owner reviews `report` before the 72 h clock starts.
- Verification: new tests 15 passed; full suite 1773 passed, 60 skipped; `git status --porcelain -- data/shadow .github` is empty.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-26*

## Self-Check: PASSED

- backend/e2e_soak_report.py and backend/tests/e2e_soak_report_test.py exist on disk.
- Commits b05201b and a85a3e7 are ancestors of HEAD; `git rev-list --count 736ae4e..HEAD` before this SUMMARY is 2.
- All acceptance criteria re-run: evaluate_dry and advance_events defined once each, 5 references to dlr_live_window_check.evaluate_window/fetch_runs, read-only setting present, load_dotenv() only under `__main__`, 13 test functions, warning text present.
