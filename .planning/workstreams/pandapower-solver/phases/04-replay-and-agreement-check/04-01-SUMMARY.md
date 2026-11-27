---
phase: 04-replay-and-agreement-check
plan: 01
subsystem: replay-data-route
tags: [pandapower, replay, owner-run-export, private-snapshot, strict-validation, read-only-sql, counts-only]
status: complete

requires:
  - phase: 01 (pandapower-solver)
    provides: pandapower_job.private (the private-path guard) and the report marker the leak scanner flags
  - phase: 03 (pandapower-solver)
    provides: psse_local_pg.apply_solver_schema, the schema after the solver-tag migration (the export is proven on both schemas)
provides:
  - backend/pandapower_job/recorded.py - read_export, validate, ingest_export, load_snapshot, by_run, complete, profile, profile_lines, ExportRefused and the closed vocabularies (REPORT_MARKER, SNAPSHOT_KIND, SNAPSHOT_VERSION, MAX_EXPORT_BYTES, MAX_SNAPSHOT_BYTES, EXPORT_COLUMNS, RUN_COLUMNS, DISPATCH_COLUMNS, MARGIN_COLUMNS, CONTINGENCY_COLUMNS, COUNT_KEYS, EXPORT_REFUSAL_REASONS, EXPORT_REFUSAL_HINTS, PROFILE_LINE_PATTERNS)
  - supabase/ops/export_psse_runs_for_replay.sql - the owner's read-only export of the recorded PSS/E runs (D-01)
  - backend/tests/pandapower_replay_fixture.py - shared uncollected helper (make_repo, HEX_A, HEX_B, run_bundle, export_document, write_export_json, write_export_csv)
  - backend/tests/pandapower_recorded_test.py (runs here) and backend/tests/pandapower_replay_pg_test.py (database tier, skips here)
affects: [04-03 replay and ingest command, 04-04 first real replay (waits for the owner's file)]

actuals:
  tokens: 23065
  tasks: 3
  commits: 3
plan_head_before: c886a3e335177d9a9ccfb8cdc6a06f4428f8d040
plan_head_after: 7f67a0b1ba934e258499ea09235f8ee65c5c9280

tech-stack:
  added: []
  patterns:
    - "Untrusted file in, reason word out: a per-column rule table over the closed vocabularies, strict JSON, and an exception raised outside any except block that carries no cell, key, id, hash or path"
    - "Owner-run export plus private snapshot instead of a database connection: no driver exists in the compute path, pinned by an AST walk of every import"
    - "Counts printed only through a closed line vocabulary (PROFILE_LINE_PATTERNS), checked inside profile_lines itself"

key-files:
  created:
    - backend/pandapower_job/recorded.py
    - supabase/ops/export_psse_runs_for_replay.sql
    - backend/tests/pandapower_replay_fixture.py
    - backend/tests/pandapower_recorded_test.py
    - backend/tests/pandapower_replay_pg_test.py
  modified: []

key-decisions:
  - "D-01 implemented as planned: the owner runs one read-only SELECT in the SQL editor, the ingest validates the file and writes a private snapshot, later plans read only the snapshot; no module of this phase imports a driver."
  - "A top-level bare number ('5') is routed to the CSV reader by the plan's first-character rule and refused as not_csv; wrong_shape is raised for '[5]', '[]', '[[1]]' and a two-object list."
  - "A NaN or infinity token in a file is refused as not_json by the strict parser; a value that reaches validate() as a Python float, or a number such as 1e999 that parses to infinity, is refused as bad_value."
  - "The run-id rule is 'psse-' followed by 1 to 100 characters of [0-9A-Za-z._-], not the schema's full pattern: the plan's rule is the prefix, and the database already enforces the full pattern."
  - "Not-null columns of the stored tables (applied_mva and the other required numbers, method, contingency_id, element_id, job_version) are required non-null here too; the nullable ones accept None."

requirements-completed: []
requirements-progress:
  - id: AGR-01
    note: "route half done (export plus validated private snapshot, no database access in the compute path); the read-only replay itself is plan 04-03; the database-tier proofs of the export SQL are skipped here"
  - id: AGR-04
    note: "ingest half done (counts-only profile through a closed vocabulary); the report half is in later plans"

coverage:
  - id: D1
    description: "an export file becomes a git-ignored private snapshot that the leak scan flags by shape, loads back equal, and prints a counts-only profile with no id, hash or row number"
    requirement: "AGR-01, AGR-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_recorded_test.py#test_tracer_export_to_snapshot_to_counts"
        status: pass
    human_judgment: false
  - id: D2
    description: "every malformed, edited, duplicated, orphaned or truncated export is refused by one of 13 reason words, in JSON and CSV form, with no cell, key, id, hash or path in the message and nothing written"
    requirement: "AGR-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_recorded_test.py#test_each_reason_is_raised_by_its_minimal_file_with_a_reason_only_message"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_recorded_test.py#test_a_bad_value_is_refused"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_recorded_test.py#test_a_planted_marker_in_a_cell_never_reaches_the_error"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_recorded_test.py#test_recorded_imports_no_driver_no_network_no_process_and_no_writer_side_module"
        status: pass
    human_judgment: false
  - id: D3
    description: "the export SQL is one read-only SELECT over the four result tables, filters on the psse- prefix, names no solver column and selects exactly the pinned columns"
    requirement: "AGR-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_recorded_test.py#test_text_export_is_one_read_only_select"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_recorded_test.py#test_text_export_selects_exactly_the_pinned_columns"
        status: pass
    human_judgment: false
  - id: D4
    description: "the export SQL runs read-only on a real Postgres, leaves the four tables unchanged, a write in that session is refused (25006), and its output ingests to the seeded runs, on both schemas"
    requirement: "AGR-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_replay_pg_test.py#test_db_export_runs_read_only_and_the_four_tables_are_unchanged"
        status: skipped
      - kind: unit
        ref: "backend/tests/pandapower_replay_pg_test.py#test_db_export_output_ingests_to_the_seeded_runs"
        status: skipped
      - kind: unit
        ref: "backend/tests/pandapower_replay_pg_test.py#test_db_a_write_in_the_read_only_session_is_refused"
        status: skipped
    human_judgment: false
---

# Phase 4 Plan 01: The Recorded-Runs Route (owner-run export, strict ingest, private snapshot) Summary

An owner-run read-only SQL export becomes a validated, private, git-ignored snapshot that later plans read instead of a database: `recorded.py` refuses anything that is not exactly what the export statement produces, with one reason word and no echo of the data, and prints only counts.

## Database tier status

The six database test items of `backend/tests/pandapower_replay_pg_test.py` (three tests, each on the schema before and after the solver-tag migration) were only SKIPPED on this Windows machine, with the harness reason "set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the PSS/E Postgres proofs". None of them passed. **The export SQL has never executed on a real Postgres from this plan**: the file was checked by eye and by text tests only (one statement, four tables, pinned columns, no write word), and no SQL parser or Postgres binary exists here. Those proofs are database-only. Under `PSSE_REQUIRE_PG=1` with no database the same six items all error (checked: "6 errors"), so a skip cannot pass a strict gate.

Postgres host command (the owner's Mac, manual, not claimable from here); it must report 0 skipped:

```
DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_replay_pg_test.py
```

The owner may run the export at any time after this plan: `supabase/ops/export_psse_runs_for_replay.sql` is complete and its header tells the person who runs it what to do (SQL editor, CSV or JSON download, send by the private channel, a narrow date prefix for the first export, save under `data/private/pandapower/incoming/`). If the database proofs are not run first and the statement has a syntax error, the SQL editor will show it; the person should send only the error text back.

## Performance

- **Duration:** about 1 hour (single session)
- **Tasks:** 3 of 3
- **Files:** 5 created, none modified

## Accomplishments

- Tracer (Task 1): export JSON to `ingest_export` to a `snapshot_STAMP.json` inside `data/private/pandapower/snapshots/`, which git ignores, which the leak scan flags as a `pandapower_marker` shape, which `load_snapshot` reads back equal, with `by_run` in slot order and a profile whose every line matches `PROFILE_LINE_PATTERNS` and holds no id, hash or row number.
- Strict validation (Task 2): per-column rule table, JSON and CSV forms (any header order, byte-order mark, CRLF, a cell serialised twice), 13 reason words each raised by a minimal bad file and checked for an exact `export refused: REASON` message, nothing written on a refusal, fixed hints for `too_large` and `counts_mismatch`, `complete()` for the replay's per-run exclusion, an AST import pin that also fails on planted imports.
- Export SQL (Task 3): one SELECT with four common table expressions and one five-column row (`counts`, `runs`, `dispatch`, `margins`, `contingencies`), pinned by four text tests; database-tier proofs written for both schemas.

## Task Commits

1. **Task 1: Tracer** - `93a7c7e` (feat)
2. **Task 2: Strict validation** - `7cef9ed` (feat)
3. **Task 3: Export SQL, text tests and database-tier tests** - `7f67a0b` (feat)

Plan 04-02 ran in parallel on the same branch; its commits sit between these three (`0ba33de`, `d22bf95`, `33092af`) and touch none of this plan's files. The file-scope gate (PLAN=04-01) exits 0.

## Verification results

- `pandapower_recorded_test.py` (131 tests) and `pandapower_replay_pg_test.py` (6 items): **131 passed, 6 skipped, 0 failed**. The 6 skipped are the database tier, each with the harness's Postgres reason.
- With `pandapower_import_gate_test.py` and `private_data_guard_test.py` added: **146 passed, 6 skipped, 0 failed**.
- `PSSE_REQUIRE_PG=1` with no database, `pandapower_replay_pg_test.py` alone: 6 errors (the strict gate trips, as required).
- `grep -c jsonb_agg supabase/ops/export_psse_runs_for_replay.sql` prints 4; the word "solver" appears nowhere in the file.
- `private_leak_scan.py` exits 0 (whole tree) and `--staged` exited 0 before each of the three commits.
- Post-commit deletion check: no deletions in any of the three commits.
- Test-first was observed for Task 2: the new tests failed against the Task 1 module (red) before the rule table, CSV reader, uniqueness and orphan rules were written (green).

## Files Created

- `backend/pandapower_job/recorded.py` (680 lines)
- `supabase/ops/export_psse_runs_for_replay.sql` (98 lines)
- `backend/tests/pandapower_replay_fixture.py` (130 lines)
- `backend/tests/pandapower_recorded_test.py` (1009 lines)
- `backend/tests/pandapower_replay_pg_test.py` (226 lines)

## Decisions Made

See `key-decisions` above. The four substantive ones: a bare top-level number routes to the CSV reader and is refused as `not_csv` (the plan's first-character rule); NaN and infinity tokens in a file are `not_json`, while values that reach `validate` as non-finite floats or parse to infinity are `bad_value`; the run-id rule is the `psse-` prefix plus a bounded safe alphabet; not-null columns of the stored tables are required non-null in the export too.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Stale plan-commit ledger reused by this plan**
- **Found during:** SUMMARY writing (measuring `commits:`)
- **Issue:** `.git/gsd-plan-head-before-04-01` already existed from the earlier pss-e-integration plan that also numbered itself 04-01, so the ledger held an old base (197a689) and `rev-list` counted 158 commits.
- **Fix:** Used the parent of this plan's first commit (`c886a3e`) as `plan_head_before` and overwrote the stale ledger file (inside `.git`, untracked). The measured count of commits carrying `(04-01)` in the range is 3.
- **Files modified:** none tracked
- **Commit:** n/a

### Wording decisions that follow the plan's rules rather than deviate from them

- Task 2's behavior list says "a top-level number" is `wrong_shape`; the plan's own detection rule sends a file whose first non-blank character is not `[` or `{` to the CSV reader, so a bare `5` is `not_csv`, and `wrong_shape` is tested with `[5]`, `[]`, `[[1]]` and a two-object list. Recorded as a decision above.
- The behavior list says NaN or infinity is `bad_value`; a NaN or Infinity token is refused earlier by the strict parser as `not_json` (the plan also demands strict parsing), so both paths are tested: tokens in a file give `not_json`, floats given to `validate` and numbers like `1e999` give `bad_value`.
- `test_the_report_marker_equals_the_one_the_owner_commands_use` reads `cli.REPORT_MARKER` from the source with an AST evaluation instead of importing `pandapower_job.cli`, so this test file needs no pandapower (the plan says "no pandapower").

None of these changed a tolerance or weakened a test.

## Known Stubs

None. `recorded.py` holds no placeholder data; the fixture rows are synthetic public rows by design.

## Issues Encountered

- A pytest parametrised id built from a 200000-character string exceeded the Windows environment-variable limit (`PYTEST_CURRENT_TEST`); the hostile-nesting case became its own test.
- One test expectation was my own arithmetic slip (the number of contingency rows after appending one is 5, not 3); fixed in the test, not in the module.

## Threat Flags

None beyond the plan's register. T-04-01 to T-04-05 are mitigated as the plan says (files only through `private.py`, marker key present, closed-vocabulary profile, no driver import, reason-word refusals with a planted-marker test, size caps and csv limit restored). T-04-02's database half (the read-only session and the 25006 refusal) is the skipped database tier.

## Next Phase Readiness

- Plans 04-03 and 04-04 can import every name in "Artifacts this phase produces" unchanged.
- Plan 04-04 waits for the owner's export file; the owner can run `supabase/ops/export_psse_runs_for_replay.sql` at any time (preferably after the database tier has been run once on a Postgres host, so the statement is proven to execute).
- The orchestrator owns STATE.md, state.json, ROADMAP.md and REQUIREMENTS.md; AGR-01 and AGR-04 are partly done here (route and ingest halves) and should not be marked complete yet.

## Self-Check: PASSED

- Files exist: `backend/pandapower_job/recorded.py`, `supabase/ops/export_psse_runs_for_replay.sql`, `backend/tests/pandapower_replay_fixture.py`, `backend/tests/pandapower_recorded_test.py`, `backend/tests/pandapower_replay_pg_test.py` (all FOUND).
- Commits are ancestors of HEAD: `93a7c7e`, `7cef9ed`, `7f67a0b` (all FOUND).
