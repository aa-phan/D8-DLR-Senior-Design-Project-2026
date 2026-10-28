---
phase: 01-result-table-spec-and-rating-i-o
plan: 03
subsystem: database
tags: [spec, ddl, drift-test, handoff, sha256, psse, pytest]

requires:
  - phase: 01-01
    provides: the reference DDL (psse_results_v1.sql with BEGIN/END markers) and the completeness checks file
  - phase: 01-02
    provides: psse_job.constants vocabularies, RATINGS_USED_KEYS and psse_job.units.circuit_mva
provides:
  - docs/data-science/schema/psse_results_v1.md, the 16-section human spec of the four PSS/E result tables handed to production-pipeline Phase 6
  - docs/data-science/decisions/psse_results_phase6_handoff.md, the hand-off note (what Phase 6 adds, 06-09 and 06-01 impact, both resolutions, the DDL region sha256 pin)
  - backend/tests/psse_schema_doc_test.py, 20 offline tests that pin the spec, the DDL text and the hand-off note to each other and to psse_job and backend/config.py
affects: [01-04, 01-05, production-pipeline Phase 6, pss-e-integration Phase 3]

actuals:
  tokens: 13000
  tasks: 3
  commits: 3
plan_head_before: cfee668b0f3f7634ce09e525b3501dafa069f038
plan_head_after: bdfd2b501597bec57333f1aa45d9a99f9c0e4bcf

tech-stack:
  added: []
  patterns:
    - "Doc-to-DDL drift test: parse each create-table block and compare column names, order and types with the doc table; the units table is recomputed from backend/config.py and psse_job.units, never hard-coded"
    - "Line-ending-proof sha256 pin: hash the marked DDL region read in text mode with one LF per line, so a CRLF Windows checkout and an LF checkout agree"
    - "Offline DDL text contract (grants, revoke, policies, no credential, function, view or sequence, unit-first comments) over a statement splitter that blanks comment bodies and splits on semicolons outside dollar quotes"

key-files:
  created:
    - docs/data-science/schema/psse_results_v1.md
    - docs/data-science/decisions/psse_results_phase6_handoff.md
    - backend/tests/psse_schema_doc_test.py
  modified: []

key-decisions:
  - "Followed D-01 to D-06 as locked: spec and hand-off note only, no migration, no production-pipeline edit, results private, per-conductor amps converted without a power factor"
  - "Spec says service_role (Supabase's service key bypasses RLS) and the database owner sit outside the 'only dlr_psse_writer' access claim"
  - "Spec states that stale and provisional fallback cities have NULL city_rating link columns in psse_dispatched_capacity (the DDL link rule); the row read but not used lives only in psse_run.ratings_used"
  - "Added a doc test that no sentence in the spec or the note describes a grant to anon or authenticated (the plan's D-03 prohibition was marked judgment-verified)"

requirements-completed: [DBX-01]

coverage:
  - id: D1
    description: "The spec lists every column of the four tables in DDL order with type, unit, NULL-when and meaning, and fails the test if a column is added, renamed or retyped on one side only"
    requirement: "DBX-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_schema_doc_test.py#test_doc_lists_every_column_of_the_four_tables"
        status: pass
    human_judgment: false
  - id: D2
    description: "ratings_used keys equal psse_job RATINGS_USED_KEYS in order; the units table (2181.1, 1792.7, 2240.8, 788.8 MVA against 1036.0, 851.5, 1064.4, 749.3 MW, ratios 2.105, 2.105, 2.105, 1.053) is recomputed from backend/config.py; every DDL CHECK vocabulary equals the psse_job tuple"
    requirement: "DBX-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_schema_doc_test.py -k 'ratings_used or units_table or vocabularies'"
        status: pass
    human_judgment: false
  - id: D3
    description: "The DDL text holds exactly the D-03 grants and revoke, eight writer-only policies, no credential, function, view or sequence, and a unit-first comment on every table and column"
    requirement: "DBX-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_schema_doc_test.py -k ddl (5 tests); 9 planted DDL mutations all caught"
        status: pass
    human_judgment: false
  - id: D4
    description: "The hand-off note names every Phase 6 item, the 06-09 and 06-01 impact with both resolutions, resolves its links, contains no connection details, and pins the LF-normalised sha256 of the DDL's marked region, which the test recomputes"
    requirement: "DBX-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_schema_doc_test.py -k handoff (6 tests)"
        status: pass
    human_judgment: false
  - id: D5
    description: "A reviewer reads the spec and the hand-off note and confirms they are complete and tell Phase 6's owner what to add (ROADMAP Phase 1 criterion 1)"
    requirement: "DBX-01"
    verification: []
    human_judgment: true
    rationale: "Completeness and clarity for a human reader is a review call (VALIDATION.md manual-only item, done at /gsd-verify-work); the tests prove consistency, not readability"

duration: 8min
completed: 2026-10-28
status: complete
---

# Phase 1 Plan 03: PSS/E Result-Table Spec and Phase 6 Hand-off Summary

**A 16-section spec of the four private PSS/E result tables, a hand-off note for production-pipeline Phase 6 that pins the reference DDL's marked region by an LF-normalised sha256, and 20 offline tests that stop the spec, the DDL, psse_job and backend/config.py from drifting apart.**

## Performance

- **Duration:** about 8 min (the start time was not captured; estimated from the previous plan's completion at 10:42Z)
- **Completed:** 2026-10-28T10:50Z
- **Tasks:** 3
- **Files modified:** 3 (all created)

## Accomplishments

- `psse_results_v1.md` has the Phase 6 intake (five items), where the data lives, keys and links (`(run_id, run_outcome)` composite link, soft `city_rating` link, link columns NULL unless `rating_source` is `city_rating`), 19 + 22 + 14 + 14 column rows in DDL order, the 16-key `ratings_used` table, IN-01 selection (five reasons, 90-minute rule, HH:30 note), the amps-to-MVA units table with the 2.1 times trap warning, write semantics, the five completeness checks, access (INSERT and SELECT only, `service_role` outside the claim), reading rules, open questions and versioning.
- `psse_results_phase6_handoff.md` lists what Phase 6 must add, quotes the three 06-09 statements a third migration breaks and gives both resolutions (amend 06-09, or a separate later step), notes that 06-01's two-object `verify_exposure.sql` rule stays true and acts as a regression net, and carries `Marked-region sha256: 955f349d2df66394dbec4378ddcc2d9eb61f7e37bd4eda8de4b70de16c3a6643` (cross-checked against the committed LF blob with `sed | sha256sum`).
- `psse_schema_doc_test.py` has 20 tests. The pin is proven the same for a CRLF and an LF copy, different when the region changes, and unchanged by an edit outside the region.

## Task Commits

1. **Task 1: Tracer, spec skeleton with every section, the Phase 6 intake and the psse_run table** - `0df9e4b` (docs)
2. **Task 2: Complete the spec and the offline DDL text contract** - `e2ce100` (docs)
3. **Task 3: Hand-off note with the sha256 pin of the marked region** - `bdfd2b5` (docs)

**Plan metadata:** the docs(01-03) commit that holds this file, STATE.md and ROADMAP.md (see git log).

_RED was observed for Task 1 (3 failed: spec file absent) and Task 3 (7 failed: note absent) before the documents existed. Task 2's tests were written against the finished spec; their first run failed once (`test_doc_has_no_unfilled_section`, a one-line Versioning section), which was fixed in the spec. To prove the DDL tests bite, nine planted mutations (renamed and retyped column, an `anon` grant, vocabulary drift, a password, a function, a missing comment, a non-unit-first comment, a second BEGIN marker) were run against temporary copies outside the repository; all nine were caught. The reference DDL itself was never touched._

## Files Created/Modified

- `docs/data-science/schema/psse_results_v1.md` - the spec (16 sections)
- `docs/data-science/decisions/psse_results_phase6_handoff.md` - the Phase 6 hand-off note (7 sections)
- `backend/tests/psse_schema_doc_test.py` - spec, DDL-text and hand-off drift tests

## Decisions Made

- Followed D-01 to D-06 as written. `docs/data-science/schema/psse_results_v1.sql`, `supabase/migrations`, `backend/config.py` and the production-pipeline workstream are untouched.
- Spec states the carry-over facts from the earlier plans: `service_role` bypasses RLS and is outside "only `dlr_psse_writer`"; stale and provisional fallbacks carry no `city_rating` link in `psse_dispatched_capacity`; the five fallback reasons; the DDL-region hash normalises CRLF to LF.
- The Open Questions item "should results ever be public" is worded as a new owner decision plus a new schema version, so the spec leaves no room for a consumer grant.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `_statements` and `_code` bound the DDL path as a default argument**
- **Found during:** Task 2 (mutation check, two of nine planted mutations were not caught)
- **Issue:** `def _statements(path=DDL_PATH)` evaluates the path at definition time, so a test that redirects `DDL_PATH` (as the mutation harness does) never reached the statement-based tests. The tests themselves were correct for the real file but could not be proven to bite.
- **Fix:** both helpers take `path=None` and resolve `DDL_PATH` at call time.
- **Files modified:** `backend/tests/psse_schema_doc_test.py`
- **Verification:** all nine mutations are now caught; 13 passed in Task 2.
- **Commit:** `e2ce100`

### Additions beyond the plan (no behavior change to the plan's scope)

- Extra test `test_docs_describe_no_anon_or_authenticated_grant` (plan marked the D-03 prohibition as judgment-verified); extra needles `service_role` (Access) and "only in `psse_run.ratings_used`" (Keys).
- Total tests: 20 (plan minimums were 13 for Task 2 and 6 handoff tests).

**Total deviations:** 1 auto-fixed (bug in the test helper). **Impact:** none on scope; no file outside the plan's three was touched.

## Notes for the next plans

- **01-04 and 01-05:** the spec now documents the writer's rules: one transaction for a successful study; a failed study writes `psse_run` alone; a failed write rolls back and records `failed_stage` `write`; `insert ... on conflict (run_id) do nothing`; the `psse_dispatched_capacity` link columns come only from a choice whose source is `city_rating`. Plan 01-04's tests should keep matching the spec's section on these.
- **Changing the DDL:** any edit between the BEGIN and END markers of `psse_results_v1.sql` fails `test_handoff_pins_the_marked_region_sha256` until the pin in the hand-off note is updated, and Phase 6's owner must be told, because their migration must carry the same region.
- **Open for the owner:** the 06-09 vehicle choice (option a or b) and the scope note in Phase 6 are theirs; nothing in this workstream edits Phase 6.

## Authentication Gates

None.

## Known Stubs

None. The spec text carries no placeholder, and `test_doc_has_no_unfilled_section` fails on a one-line section.

## Threat Flags

None. The two documents add no endpoint, auth path or file access; T-01-16 to T-01-19 are each covered by a named test.

## Verification Results

Environment: Windows 11 Git Bash, Python 3.12 venv (`.venv/Scripts/python.exe`), pytest 9.0.3. No database or Postgres process was needed or started.

- `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_schema_doc_test.py` - 20 passed, 0 skipped (3 after Task 1, 13 after Task 2)
- `... -k "unfilled or vocabularies or units_table"` - 3 passed; `... -k handoff` - 6 passed
- `... backend/tests/psse_schema_doc_test.py backend/tests/supabase_schema_doc_test.py backend/tests/secret_scan_test.py` - 30 passed (re-run after the files were tracked)
- Whole offline phase set (`psse_contract_test`, `psse_ratings_test`, `psse_schema_doc_test`, `supabase_schema_doc_test`, `secret_scan_test`) - 123 passed, 0 skipped
- Acceptance greps: `grep -c "^## "` on the spec prints 16; `_psse_results.sql` 2; `SUPABASE_PSSE_DB_URL` 1; the AUSTIN units row 1; `started_at desc, run_id desc` 1; the hand-off `Marked-region sha256:` line 1; `exactly the two Phase 6 files` 1
- `git diff --quiet -- docs/data-science/schema/psse_results_v1.sql` exits 0; `git status --porcelain -- supabase/migrations .planning/workstreams/production-pipeline docs/data-science/decisions/pss_e_handoff.md docs/data-science/schema/psse_results_v1.sql` prints nothing
- Manual item (VALIDATION.md): a reviewer reads the spec and the note; left for `/gsd-verify-work` (coverage D5)

## Self-Check: PASSED

- FOUND: docs/data-science/schema/psse_results_v1.md, docs/data-science/decisions/psse_results_phase6_handoff.md, backend/tests/psse_schema_doc_test.py
- FOUND commits 0df9e4b, e2ce100, bdfd2b5 (ancestors of HEAD); `git rev-list --count cfee668..HEAD` was 3 before this SUMMARY commit
