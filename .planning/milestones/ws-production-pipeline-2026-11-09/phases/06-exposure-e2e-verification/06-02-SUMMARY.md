---
phase: 06-exposure-e2e-verification
plan: 02
subsystem: testing
tags: [secret-scan, pytest, supabase, public-repo, d-10]

requires:
  - phase: 04-supabase-store-writer
    provides: "backend/tests/secret_scan_test.py (DB-04 credential scan over every tracked file)"
provides:
  - "Default-suite patterns that fail on a Supabase project host, a pooler user carrying a project reference and a publishable key in any tracked file"
  - "Owner-local, environment-gated exact-value scan (full URL, host, reference, key, pooler reference and host) that skips when nothing is exported"
affects: [06-03, 06-04, 06-05, 06-06, 06-09, 06-10, 06-11, 06-12, 06-13]

actuals:
  tokens: 2500
  tasks: 2
  commits: 2
plan_head_before: 2ad224354756291dad30c7edd3997064496e9e99
plan_head_after: 9054a813a1e1015aa2042443b77d8a430703f16d

tech-stack:
  added: []
  patterns:
    - "Detection patterns and test plants assembled from pieces so a scanner file never matches itself"
    - "Report carries path, line and pattern name only; tests assert no planted value appears in any finding"
    - "Owner-local check reads only exported variables (never a dotenv file) and skips when none is set"

key-files:
  created: []
  modified:
    - backend/tests/secret_scan_test.py

key-decisions:
  - "Project reference is treated as exactly 20 lowercase letters or digits (assumption A19 of 06-RESEARCH); the old 16-character dummy reference in Phase 4 plants stays a non-match"
  - "The exact-value scan drops values shorter than 8 characters and de-duplicates the rest"

patterns-established:
  - "Shape scan in CI plus an exact-value scan the owner runs in a shell before any push"

requirements-completed: [API-02]

coverage:
  - id: D1
    description: "Default suite flags a project host, a pooler user with a 20-character reference and a publishable key, each with exactly one finding on its planted line"
    requirement: API-02
    verification:
      - kind: unit
        ref: "backend/tests/secret_scan_test.py#test_the_scanner_flags_planted_credentials_and_ignores_placeholders"
        status: pass
    human_judgment: false
  - id: D2
    description: "Placeholders (project-ref, [ref], ${SUPABASE_URL}, 16-character dummy reference, bare prefix with dots, <publishable-key>, generic pooler host) never trip the scan, and no finding contains a planted value"
    requirement: API-02
    verification:
      - kind: unit
        ref: "backend/tests/secret_scan_test.py#test_the_scanner_flags_planted_credentials_and_ignores_placeholders"
        status: pass
    human_judgment: false
  - id: D3
    description: "The whole tracked tree is clean under the new patterns"
    requirement: API-02
    verification:
      - kind: unit
        ref: "backend/tests/secret_scan_test.py#test_tracked_files_hold_no_credentials"
        status: pass
    human_judgment: false
  - id: D4
    description: "Exact-value helpers derive the right values from exported variables and report path and line only; the env-gated test skips when nothing is exported"
    requirement: API-02
    verification:
      - kind: unit
        ref: "backend/tests/secret_scan_test.py#test_exact_values_come_from_the_exported_variables_only"
        status: pass
      - kind: unit
        ref: "backend/tests/secret_scan_test.py#test_exact_value_scan_finds_a_planted_reference_without_printing_it"
        status: pass
    human_judgment: false
  - id: D5
    description: "The real project values (URL, reference, key) appear in no tracked file"
    requirement: API-02
    verification: []
    human_judgment: true
    rationale: "Only the owner holds the real values; the executor never exports or reads them. The owner runs the env-gated test in a shell before any push"

duration: 5min
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 02: Secret scan for the project address and key Summary

**The repository-wide secret scan now also fails on a Supabase project host, a pooler user carrying a 20-character project reference and a publishable key, plus an owner-local exact-value test that checks every tracked file against the real URL, reference and key exported in a shell; nothing pushed.**

Plain English: no project address or public key can be saved anywhere in this public repository without the test suite failing.

## Performance

- **Duration:** 5 min
- **Started:** 2026-10-26T20:09:00Z
- **Completed:** 2026-10-26T20:15:00Z
- **Tasks:** 2 (1 tracer, 1 auto/tdd)
- **Files modified:** 1

## Accomplishments

- Three new patterns (`_SB_HOST`, `_POOLER_REF`, `_SB_PUBLISHABLE`) producing the finding names `supabase_project_host`, `pooler_project_reference` and `supabase_publishable_key`, assembled from pieces so the file never matches itself.
- The planted-control test gained four plant lines (project URL in a curl line, an environment-style `SUPABASE_URL=` line, a pooler user line, a publishable key line), each with exactly one finding, and twelve placeholder lines that produce nothing. The existing 16-character pooler user plants still produce only their original finding.
- Tracked tree scanned with the new patterns: zero hits, so no file needed a placeholder replacement (hit list: none).
- Owner-local scan: `_exact_values(env)`, `_scan_exact(paths, values)` and `test_tracked_files_hold_no_real_project_values_from_env`. It skips with a message naming the three variables when none is exported; the module docstring carries the owner command.
- Verified with synthetic exported values (not real ones): the env-gated test runs and passes; unset, it is skipped and every other test passes.

## Task Commits

1. **Task 1 (tracer): project host, pooler-reference and publishable-key patterns in the repository-wide scan** - `646e352` (test)
2. **Task 2: owner-local exact-value scan from exported environment variables** - `9054a81` (test)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

The tracer gate: `type="tracer"`, not `blocking-human`, automated-only `<verify>`; the verify was re-run end to end (3 passed) and expansion continued without a checkpoint.

## Files Created/Modified

- `backend/tests/secret_scan_test.py` - new patterns, extended controls, exact-value helpers and tests (+163/-1 lines)

## Decisions Made

- Followed the plan. Reference length is exactly 20 (A19); the pattern is lowercase-only as specified.
- The exact-value scan skips values under 8 characters so a short stray string cannot flag every file.

## Deviations from Plan

### Auto-fixed Issues

**1. Attribution line.** The plan asked for `Co-Authored-By: Claude Opus 5.5`; the commits carry the session's attribution lines (`Claude Sonnet 5.5` plus the session link) per the executor instructions.

**Total deviations:** 0 code deviations, 1 attribution wording note.
**Impact on plan:** none.

### TDD note (Task 2)

Tests were written first and failed with `NameError` for the three missing helpers (3 failed, 3 passed), then the helpers turned all green.

## Discrepancies

- **Pooler host in the exact-value scan.** Per the plan, a pooler host from an exported `SUPABASE_DB_URL` is searched for in tracked files. That host is a region name (for example the generic pooler host used as a placeholder in Phase 4 planning docs), not a project secret, so if the owner's real region matches a placeholder already in docs the owner-local test will report those lines. If that happens, drop the host from `_exact_values` rather than editing docs; the project reference alone is what must stay out.
- Full backend run: `backend/tests` gives 1758 passed, 60 skipped (local-Postgres tests without the autostart flag), 0 failed. Running pytest over all of `backend` aborts at collection because `backend/smoke_test.py` needs `SYNOPTIC_TOKEN` at import; this is pre-existing and out of scope.

## Issues Encountered

None. Pre-existing working-tree changes (.DS_Store files, `.planning/config.json`, untracked `.obsidian/`, `graphify-out/`, etc.) were left unstaged.

## Known Stubs

None.

## Threat Flags

None. T-06-07 and T-06-08 are mitigated as planned; T-06-SC accepted (no package installed).

## User Setup Required

None for CI. Before any push the owner may export `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` and `SUPABASE_DB_URL` in a shell and run `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/secret_scan_test.py`. Nothing touched the live Supabase project.

## Next Phase Readiness

- D-10 enforcement exists before any Phase 6 doc, example or evidence file is written: later plans (docs, examples, evidence JSON) must use placeholders such as `<project-ref>` and read `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` from the environment, or the default suite fails.
- API-02 stays open in REQUIREMENTS.md on purpose: later plans in this phase also declare it.

## Self-Check: PASSED

- File present: `backend/tests/secret_scan_test.py` (FOUND).
- Commits `646e352` and `9054a81` are ancestors of HEAD; `git rev-list --count 2ad2243..HEAD` measured 2 at SUMMARY time.
- Acceptance criteria re-run: the three finding names each appear 2 or more times; `"publishable_"` appears 3 times; exactly one `def test_tracked_files_hold_no_real_project_values_from_env`; zero occurrences of the dotenv loader name; verify command exits 0 with the exact-value test listed as skipped by `-rs`.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-26*
