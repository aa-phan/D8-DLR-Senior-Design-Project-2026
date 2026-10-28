---
phase: 01-result-table-spec-and-rating-i-o
plan: 02
subsystem: testing
tags: [stdlib, urllib, postgrest, rating-selection, redaction, units, python37, pytest]

requires:
  - phase: production-pipeline Phase 6 (other workstream, planned not built)
    provides: the latest_rating view contract (34 columns, server is_stale and is_provisional flags), read through the publishable key
  - phase: 01-01
    provides: the reference DDL whose CHECK vocabularies and link rule the job-side constants mirror
provides:
  - backend/psse_job package (stdlib only, Python 3.7 syntax) with copied constants, the IN-01 rating chooser, a REST reader for latest_rating, shared redaction and the amps-to-MVA helper
  - ratings_used(selection), the per-city record for psse_run.ratings_used
  - Loopback FakeLatestRatingServer test helper and 96 offline tests (83 ratings, 10 contract, 3 secret scan run alongside)
affects: [01-03, 01-04, 01-05, pss-e-integration Phase 2, pss-e-integration Phase 3]

actuals:
  tokens: 19600
  tasks: 3
  commits: 3
plan_head_before: 3ffef48a593d1f9c9a622d22d72a2a3da59d7ab7
plan_head_after: 390896a1c36fda7890778bcb3b795485cfc56d95

tech-stack:
  added: []
  patterns:
    - "Every doubt maps to static: choose() never raises for bad row content and takes static amps and subconductor counts from constants, never from the row"
    - "A failed read is a value, not an exception: select_ratings turns ReadFailed (or any fetch error) into all-static read_failed with a redacted read_error (D-02)"
    - "Gates are written over (source, filename) so a planted violation proves each one fires; they glob psse_job/*.py, so later modules are covered automatically"
    - "ReadFailed is raised outside the except block, so no original exception text is chained"

key-files:
  created:
    - backend/psse_job/__init__.py
    - backend/psse_job/constants.py
    - backend/psse_job/ratings.py
    - backend/psse_job/redaction.py
    - backend/psse_job/units.py
    - backend/tests/psse_fakes.py
    - backend/tests/psse_ratings_test.py
    - backend/tests/psse_contract_test.py
  modified: []

key-decisions:
  - "Followed D-02, D-05, D-06 as locked: failed read continues as read_failed static, config.py untouched with copied constants plus a drift test, rating_amps read per conductor and converted with sqrt(3) x kV, no power factor"
  - "choices and ratings_used entries are plain dicts (ordered on 3.7+), not OrderedDict, so the record serializes and compares as ordinary JSON"
  - "The redaction parity test executes supabase_store.redact's own source (extracted with ast) instead of importing the module, because the module imports pandas and pandas is not installed here"

patterns-established:
  - "Static choices keep the row link for stale and provisional rows (row_valid_time, row_computed_at, run_id, status, fingerprint, age, server flags) so the record shows which row was read and why it was not used; missing and invalid choices carry none"
  - "A planted-violation test next to every AST gate"

requirements-completed: [IN-01]

coverage:
  - id: D1
    description: "With today's labels (every row provisional) all four cities select static_fallback with reason provisional and the per-conductor static rating (AUSTIN 1825, CORPUS_CHRISTI 1500, MIDLAND 1875, EL_PASO 1320 A); one GET with the exact select list, order=city.asc and the key in apikey only"
    requirement: "IN-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_ratings_test.py#test_tracer_today_labels_select_static_for_all_four_cities"
        status: pass
    human_judgment: false
  - id: D2
    description: "Reason precedence missing, invalid, stale, provisional; exactly 90 minutes is fresh, 90 minutes plus one second and a server is_stale flag are stale; a valid_time more than 5 minutes ahead is invalid; fresh non-provisional rows (including status 'fallback') are used as city_rating"
    requirement: "IN-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_ratings_test.py#test_choose_matrix (23 ids) and test_choose_exact_90_minutes_is_fresh_and_keeps_the_row_link"
        status: pass
    human_judgment: false
  - id: D3
    description: "Selection over a response: empty gives all missing, a failed read gives all read_failed with a redacted error and never raises (D-02), fixed city order, exact case-sensitive keys, duplicate rows make a city invalid, aware now required"
    requirement: "IN-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_ratings_test.py -k select (7 tests) and test_ratings_used_has_four_cities_and_fixed_keys"
        status: pass
    human_judgment: false
  - id: D4
    description: "The reader refuses a secret key, a service_role JWT and plain http to a remote host before any request; HTTP errors, non-list bodies and transport errors are ReadFailed with no URL, host or key in the text"
    requirement: "IN-01"
    verification:
      - kind: integration
        ref: "backend/tests/psse_ratings_test.py -k fetch (loopback fake server and closed port)"
        status: pass
    human_judgment: false
  - id: D5
    description: "Per-circuit MVA = amps x subconductors x sqrt(3) x kV / 1000 with no power factor (AUSTIN 2181.1, ratio 2.105 to the per-conductor pf 0.95 MW figure); choose() and the select list never touch rating_mw (D-06)"
    requirement: "IN-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_ratings_test.py -k units (19 tests)"
        status: pass
    human_judgment: false
  - id: D6
    description: "Redaction removes the URL, host, project reference, password (raw and decoded), publishable key, sb_ tokens, JWTs, key=value pairs and resolved addresses, cuts after redaction, and equals supabase_store.redact on the shared cases"
    requirement: "IN-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_ratings_test.py -k redact (4 tests)"
        status: pass
    human_judgment: false
  - id: D7
    description: "psse_job's constants equal backend/config.py's; every module parses with ast feature_version (3, 7), has no builtin-generic or X | Y annotations, no 3.9+ calls or modules, imports only the standard library (psycopg lazily), loads no heavy module in a subprocess, and names no bare MW column"
    requirement: "IN-01"
    verification:
      - kind: unit
        ref: "backend/tests/psse_contract_test.py (10 tests)"
        status: pass
    human_judgment: false
  - id: D8
    description: "psse_job runs on the actual PSS/E interpreter (its Python version is unconfirmed; Phase 6 targets 3.7+)"
    verification: []
    human_judgment: true
    rationale: "ast feature_version is a best-effort syntax gate on Python 3.12; only running on the laptop's interpreter proves it (Phase 3 setup guide)"

duration: 9min
completed: 2026-10-28
status: complete
---

# Phase 1 Plan 02: Rating I/O for the PSS/E Job Summary

**A stdlib-only `psse_job` package that reads `latest_rating` over REST with the publishable key, picks per city between the newest `city_rating` row and the static rating with a recorded reason (all four static today, `read_failed` on any read error), converts per-conductor amps to per-circuit MVA with no power factor, and is pinned by tests to parse as Python 3.7 and stay off config, pandas and psycopg at import time.**

## Performance

- **Duration:** about 9 min
- **Started:** about 2026-10-28T10:33Z
- **Completed:** 2026-10-28T10:42Z
- **Tasks:** 3
- **Files modified:** 8 (all created)

## Accomplishments

- `fetch_latest_rating` does one GET (`select` = the 12 columns of `LATEST_RATING_SELECT`, `order=city.asc`) with `apikey` only and no Authorization header. It refuses a secret-prefixed key, a `service_role` JWT, and plain http to a non-loopback host before any request, and raises a redacted `ReadFailed` for HTTP errors, non-list bodies and transport errors.
- `select_ratings` calls the reader once and returns the four cities in fixed order. Reason precedence is missing, invalid, stale, provisional, and a failed read gives `read_failed` for all four (D-02). Server `is_stale` is OR-ed with a client age check, so clock skew only moves a city toward static.
- `ratings_used(selection)` builds the `psse_run.ratings_used` object (four cities, exactly the 16 `RATINGS_USED_KEYS`, JSON-safe with `allow_nan=False`); `line_voltage_kv` and `rating_mva` stay None for Phase 2 to fill.
- `units` converts amps to circuit amps and MVA and back; none of its functions takes a power factor. The select list contains no MW column and `choose()` is proven not to read one.
- `redaction` ports `supabase_store.redact` with extra key, JWT and resolved-address rules; `env_secrets` knows the three environment variable names the job uses.
- `psse_contract_test.py` pins the copied constants to `backend/config.py` and gates every `psse_job/*.py` for Python 3.7 syntax, import boundary, heavy-module imports and the MW column name; each AST gate has a planted-violation test.

## Task Commits

1. **Task 1: Tracer, fetch latest_rating from a fake PostgREST over HTTP and select static for all four cities** - `b6f7474` (feat)
2. **Task 2: IN-01 decision matrix, read failures, shared redaction and the amps-to-MVA helper** - `6128ec4` (feat)
3. **Task 3: Constants drift test, Python 3.7 syntax gate and the laptop import boundary** - `390896a` (feat)

**Plan metadata:** the docs(01-02) commit that holds this file, STATE.md and ROADMAP.md (see git log).

_RED for Task 1 was observed before the package existed: collection failed with `ImportError: cannot import name 'constants' from 'psse_job'`. The plan puts `choose` and `select_ratings` in Task 1 and the matrix tests in Task 2, so the Task 2 tests were written after the code they exercise and passed on first run. Instead of a RED run, a mutation check was made: changing the stale comparison from `>` to `>=` made exactly the two exact-90-minute tests fail, and the file was restored before commit._

## Files Created/Modified

- `backend/psse_job/__init__.py`, `constants.py` - package docstring; copied constants (no annotations) and every vocabulary shared with the reference DDL
- `backend/psse_job/ratings.py` - `ReadFailed`, `parse_ts`, `fetch_latest_rating`, `RatingChoice`, `Selection`, `choose`, `select_ratings`, `ratings_used`
- `backend/psse_job/redaction.py` - `redact`, `env_secrets`, `connection_identifiers`
- `backend/psse_job/units.py` - `circuit_amps`, `circuit_mva`, `mva_to_circuit_amps`
- `backend/tests/psse_fakes.py` - `FakeLatestRatingServer`, `latest_rows`, `fake_publishable_key` (not collected)
- `backend/tests/psse_ratings_test.py` - 83 tests
- `backend/tests/psse_contract_test.py` - 10 tests, plus constant `PHASE6_PLANNED_LATEST_COLUMNS` (34 names)

## Decisions Made

- Followed D-02, D-05, D-06 as locked. `backend/config.py`, `supabase/migrations` and the production-pipeline workstream are untouched.
- `choices` and each `ratings_used` entry are plain dicts rather than `OrderedDict`; insertion order is guaranteed from Python 3.7.
- Static choices for stale and provisional rows still carry the row link in memory (`row_valid_time`, `row_computed_at`, `row_run_id`, `row_status`, `row_config_fingerprint`, `age_minutes`, server flags). That is what the plan specifies for the run record; see the link-rule note below for the writer.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] The parity test cannot import `supabase_store`**
- **Found during:** Task 2 (checking the environment before writing `test_redact_parity_with_supabase_store`)
- **Issue:** The plan has the test import `backend/supabase_store.py`, which imports pandas at the top. pandas (and numpy) are not installed in the venv and must not be installed without approval, so an import would fail or force a skip, and the plan forbids skipped proofs.
- **Fix:** The test compiles the four top-level names and two functions that make up `supabase_store.redact` (`_URL_RE`, `_KEY_VALUE_RE`, `_ENV_URL_NAMES`, `_MAX_MESSAGE_CHARS`, `_url_secrets`, `redact`) from that file's own source with `ast`, executes them in an empty namespace and compares 12 shared cases. It asserts it found exactly those six nodes, so a rename in `supabase_store.py` fails the test loudly rather than silently skipping it. It runs with or without pandas and never skips.
- **Files modified:** `backend/tests/psse_ratings_test.py`
- **Verification:** `-k redact` 4 passed; the parity test passes with pandas absent.
- **Commit:** `6128ec4`

### Additions beyond the plan (no behavior change to the plan's scope)

- Extra tests: `test_choose_exact_90_minutes_is_fresh_and_keeps_the_row_link`, `test_select_ignores_rows_that_are_not_dicts_and_counts_them`, `test_fetch_accepts_an_anon_role_jwt`, `test_fetch_wrong_key_is_http_401_read_failed`, `test_fetch_returns_the_decoded_rows_and_strips_a_trailing_slash`, `test_redact_env_secrets_skips_unset_and_blank`, `test_units_reject_bad_subconductor_counts`.
- `psse_contract_test.py` adds `test_syntax_gates_flag_planted_violations` and `test_import_gate_flags_planted_violations` so a gate that can no longer fail is caught. Total contract tests: 10 (plan minimum 8).
- Task 1's `fetch_latest_rating` first used a small local scrub for transport errors; Task 2 replaced it with `redaction.redact`, as the plan describes.

**Total deviations:** 1 auto-fixed (blocking). **Impact:** none on scope; the redaction parity is proven against the real `supabase_store.redact` code.

## Notes for the next plans

- **Link rule (01-04, writer):** `psse_dispatched_capacity_link_rule_ck` (plan 01-01) needs `city_rating_valid_time` and `city_rating_computed_at` NULL unless `rating_source = 'city_rating'`. `RatingChoice.row_valid_time` and `row_computed_at` are non-null for stale and provisional static choices, so the writer must take the link columns from the choice only when `source == "city_rating"`. The read-but-unused row stays in `ratings_used` (the `city_rating_*` keys).
- **Vocabulary parity (01-03):** `constants.OUTCOMES`, `FAILED_STAGES`, `LIMITING_FACTORS`, `VIOLATION_KINDS`, `ELEMENT_TYPES`, `RESULT_UNITS`, `SOURCES`, `FALLBACK_REASONS` and the city list should be tested against the CHECK lists in `docs/data-science/schema/psse_results_v1.sql`. `FALLBACK_REASONS` is `missing, invalid, stale, provisional, read_failed`; the spec must list these five.
- **Gates cover new modules (01-04, 01-05, Phase 2):** `psse_contract_test.py` globs `psse_job/*.py`. Its import allow-list includes `subprocess`, `hashlib`, `uuid`, `socket` and `time` but forbids `psspy` everywhere, so Phase 2's study module will need a deliberate, reviewed change to that gate (or an injected `psspy` object, as the research suggests). `psycopg` is allowed only inside a function body.
- **Reader scope:** `fetch_latest_rating` reads only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY`; the job's write credential is `SUPABASE_PSSE_DB_URL` and `env_secrets` already redacts all three.
- **Scheduling note carried from research:** a row exactly 90 minutes old is fresh, so a job that starts after about HH:30 with the current slot's row missing goes all-stale; Phase 3 should schedule early. The recorded `age_minutes` makes the cause visible.
- **3.7 proof is syntactic:** the gate parses on Python 3.12 with `feature_version=(3, 7)`. Runtime on the PSS/E interpreter is still a Phase 3 check (`coverage` D8).

## Authentication Gates

None. Every test uses a loopback fake server and fake, non-credential-shaped keys.

## Known Stubs

None.

## Threat Flags

None beyond the plan's threat model: the new network client (T-01-11 to T-01-13) and the key handling are each covered by a named test.

## Verification Results

Environment: Windows 11 Git Bash, Python 3.12.7 venv (`.venv/Scripts/python.exe`), pytest 9.0.3. No database or Postgres process was needed or started.

- `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_ratings_test.py -k tracer` - 1 passed
- `... backend/tests/psse_ratings_test.py` - 83 passed, 0 skipped
- `... backend/tests/psse_ratings_test.py -k units` - 19 passed; `-k redact` - 4 passed; `-k "units or redact"` - 23 passed
- `... backend/tests/psse_contract_test.py` - 10 passed, 0 skipped; `-k syntax` - 4 passed
- `... backend/tests/psse_ratings_test.py backend/tests/psse_contract_test.py backend/tests/secret_scan_test.py` - 96 passed, 0 skipped
- `secret_scan_test.py` re-run after all files were tracked - 3 passed
- `.venv/Scripts/python.exe -I -c "... units.circuit_mva(1825.0, 2, 345.0) ..."` prints `2181.1`
- `grep -c "feature_version=(3, 7)" backend/tests/psse_contract_test.py` prints 2; `grep -c "rest/v1/" backend/psse_job/ratings.py` prints 1; `grep -c STATIC_RATINGS_AMPS_PER_CONDUCTOR backend/psse_job/constants.py` prints 1
- `git status --porcelain -- backend/config.py supabase/migrations .planning/workstreams/production-pipeline` prints nothing
- Mutation check on the stale boundary (see above): 2 expected failures, then restored; full suite green

## Self-Check: PASSED

- FOUND: backend/psse_job/__init__.py, constants.py, ratings.py, redaction.py, units.py; backend/tests/psse_fakes.py, psse_ratings_test.py, psse_contract_test.py
- FOUND commits b6f7474, 6128ec4, 390896a (ancestors of HEAD); `git rev-list --count 3ffef48..HEAD` was 3 before this SUMMARY commit
