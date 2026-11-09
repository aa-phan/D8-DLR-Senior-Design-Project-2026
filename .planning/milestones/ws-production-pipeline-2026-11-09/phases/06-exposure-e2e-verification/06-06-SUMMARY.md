---
phase: 06-exposure-e2e-verification
plan: 06
subsystem: api
tags: [postgrest, supabase, rest, curl, supabase-js, urllib, stdlib, python37, consumer-contract, provisional]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "latest_rating_contract (LATEST_COLUMNS, 34 columns, is_provisional word rule) and the public.latest_rating / assert_fresh migration (06-01)"
  - phase: 06-exposure-e2e-verification
    provides: "backend/tests/secret_scan_test.py _scan_line with the project host, pooler reference and publishable key patterns (06-02)"
  - phase: 06-exposure-e2e-verification
    provides: "backend/supabase_rest.parse_ts and backend/tests/fake_postgrest.FakePostgrest (1000-row cap, recorded requests) (06-04)"
provides:
  - "docs/integration/rest-api.md: the committed consumer REST contract (34-row column table with units, freshness, fallback rows, provisional word rule and Phase 7 hand-off, status codes, write protection, polling, PSS/E interpreter question)"
  - "docs/integration/examples/{read_ratings.py,curl.sh,supabase_js.mjs}: three read-only examples, each showing the current row per city and one city's paged history"
  - "backend/tests/example_read_ratings_test.py (15 tests): the examples run as written against the in-process fake PostgREST, Python on 3.9.6 and 3.12"
  - "backend/tests/rest_api_doc_test.py (10 tests): the doc column table equals LATEST_COLUMNS; doc, pointer and heading guards"
  - "pointers from api-contract.md, F1-data-access-api.md, pss_e_handoff.md and city_rating_v1.md to rest-api.md"
affects: [06-07, 06-08, 06-09, 06-11, 06-13, 07]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 19900
  tasks: 3
  commits: 3
plan_head_before: 5988b29a57081a7b434e623109c9465ffaab21dd
plan_head_after: 1efa7ba37e7b6acbaa3cdbdbf4bae6453381eb8b

tech-stack:
  added: []
  patterns:
    - "Consumer examples read SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY from the environment only; the key travels in the apikey header and nothing else"
    - "Page with a unique order (valid_time ascending within one city) and stop on an EMPTY page, never on a short one"
    - "Examples are tested by running them as subprocesses (fixed argv, no shell) against an in-process fake PostgREST, so the documented commands are the tested commands"
    - "Doc drift guard: the doc column table is parsed and compared with the contract module, so the two cannot diverge"

key-files:
  created:
    - docs/integration/rest-api.md
    - docs/integration/examples/read_ratings.py
    - docs/integration/examples/curl.sh
    - docs/integration/examples/supabase_js.mjs
    - backend/tests/example_read_ratings_test.py
    - backend/tests/rest_api_doc_test.py
  modified:
    - docs/frontend/specs/api-contract.md
    - docs/frontend/specs/F1-data-access-api.md
    - docs/data-science/decisions/pss_e_handoff.md
    - docs/data-science/schema/city_rating_v1.md

key-decisions:
  - "The Python example fails fast: if latest_rating does not return all four cities it exits 1 naming the missing city and does not run the history part, so a consumer never acts on a partial picture"
  - "The doc forbids the word bearer outright and says the key goes in apikey only, never in an Authorization header, so no line can be read as a bearer-token instruction (T-06-20)"
  - "The doc says the DS owner checks write rejection against the live project (E2E-03) rather than naming internal plan codes, since consumers read it"

patterns-established:
  - "Doc tests parse the markdown table under a fixed heading and compare names with the Python contract module"
  - "Existing-doc edits are guarded by heading lists copied from git HEAD into the test before the edit, so no heading can be lost or renamed"

requirements-completed: [API-02, API-01]

coverage:
  - id: D1
    description: "Python 3.7+ standard-library example: parse_ts helper, default TLS verification, current row per city and one city's 2,500 rows paged past the 1000-row cap, run as written on /usr/bin/python3 (3.9.6) and the repository's 3.12"
    requirement: API-02
    verification:
      - kind: integration
        ref: "backend/tests/example_read_ratings_test.py#test_tracer_read_ratings_runs_against_the_fake"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_read_ratings_is_stdlib_only_and_parses_as_python_37"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_parse_ts_matches_the_backend_helper"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_read_ratings_keeps_certificate_verification"
        status: pass
    human_judgment: false
  - id: D2
    description: "curl example: set -euo pipefail, count=exact HEAD then GETs at offsets 0, 1000 and 2000, curl -f on every call, GET and HEAD only"
    requirement: API-02
    verification:
      - kind: integration
        ref: "backend/tests/example_read_ratings_test.py#test_curl_example_pages_past_the_cap"
        status: pass
      - kind: integration
        ref: "backend/tests/example_read_ratings_test.py#test_curl_example_fails_on_an_http_error"
        status: pass
    human_judgment: false
  - id: D3
    description: "supabase-js example passes node --check, reads both variables, queries latest_rating and city_rating, orders valid_time ascending, pages with .range and breaks on an empty page; nothing installed"
    requirement: API-02
    verification:
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_supabase_js_example_syntax_and_contract"
        status: pass
    human_judgment: false
  - id: D4
    description: "All three examples are read-only, send one credential header (apikey) and write no local file; none carries a project URL, reference or key (06-02 scan line check)"
    requirement: API-02
    verification:
      - kind: integration
        ref: "backend/tests/example_read_ratings_test.py#test_examples_are_read_only_and_send_one_credential_header"
        status: pass
      - kind: unit
        ref: "backend/tests/example_read_ratings_test.py#test_examples_carry_no_url_or_key"
        status: pass
    human_judgment: false
  - id: D5
    description: "docs/integration/rest-api.md column table lists exactly LATEST_COLUMNS in order with type, unit and meaning; every *_amps and *_mw row says PROVISIONAL; identity columns explained as the way a change shows; age_minutes, is_stale and is_provisional state their exact rules"
    requirement: API-01
    verification:
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_doc_column_table_matches_the_contract"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_doc_rating_columns_are_labelled_provisional"
        status: pass
    human_judgment: false
  - id: D6
    description: "The doc states the freshness contract and its decisions, fallback rows as safe published values, rpc/assert_fresh 200/503, the 1000-row cap, write rejection and public history, 60-second polling, the PSS/E interpreter question, and the Phase 7 hand-off (REVAL-01 must remove the word provisional from both strings); no connection detail, no bearer instruction, all links resolve"
    requirement: API-02
    verification:
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_doc_states_the_contract_terms"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_doc_states_the_provisional_hand_off"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_doc_contains_no_connection_details"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_doc_links_resolve"
        status: pass
    human_judgment: false
  - id: D7
    description: "The four existing consumer docs link to rest-api.md, keep every heading and every statement Phase 4's schema-doc test pins, and the schema doc carries the is_provisional word rule and the Phase 7 hand-off"
    requirement: API-02
    verification:
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_consumer_docs_link_to_the_rest_contract"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_consumer_docs_keep_their_headings"
        status: pass
      - kind: unit
        ref: "backend/tests/rest_api_doc_test.py#test_city_rating_doc_states_the_view_and_the_word_rule"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_schema_doc_test.py"
        status: pass
    human_judgment: false
  - id: D8
    description: "The examples work against the hosted service: the publishable key through the real gateway, two filters on one column (valid_time gte and lt), and the supabase-js paging loop"
    requirement: API-02
    verification: []
    human_judgment: true
    rationale: "Per D-06 this plan is offline against a fake. Only the live run in 06-11 (after the supabase-js legitimacy checkpoint) shows how the hosted PostgREST answers (06-RESEARCH assumptions A21, A22)"

# Metrics
duration: 11min
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 06: Consumer REST contract and three examples Summary

**A committed REST contract (`docs/integration/rest-api.md`, 34-column table pinned to the contract module) and three read-only examples (curl, supabase-js, Python 3.7+ standard library) that run as written against an in-process fake PostgREST, with the four existing consumer docs now pointing at it. Nothing contacted the live project and nothing was installed.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-10-26T21:37:06Z
- **Completed:** 2026-10-26T21:48:00Z
- **Tasks:** 3 (1 tracer, 2 auto/tdd)
- **Files modified:** 10 (6 created, 4 edited)

## Accomplishments

- **Python example** `docs/integration/examples/read_ratings.py` (standard library only, no f-strings, walrus or other post-3.7 syntax; `ast.parse(feature_version=(3, 7))` passes and the same gate rejects a walrus). It carries `parse_ts` (equal to the backend helper for 0 to 6 fractional digits and `Z`, `+00`, `+0000`, `+00:00`, `-05:00`), default TLS verification, a unique `valid_time.asc` order and an empty-page stop. It ran as written on `/usr/bin/python3` (3.9.6) and on the repository's 3.12: four city lines in `config.LOCATIONS` order, `AUSTIN rows from S to E: 2500`, and the fake saw `city_rating` requests at offsets 0, 1000, 2000 and 2500 (the last an empty page). With the fake capped at 400 rows it still returns 2,500 rows.
- **curl example** `curl.sh`: `set -euo pipefail`, `curl -fsS` on every call, one HEAD request with `Prefer: count=exact` reading the total after the slash of `Content-Range`, then three GETs at offsets 0, 1000 and 2000; a missing total stops the script. Works on macOS bash 3.2.
- **supabase-js example** `supabase_js.mjs`: `node --check` passes; reads both variables, exits 2 when one is missing, queries `latest_rating` and `city_rating`, `.order('valid_time', { ascending: true })`, `.range(from, from + PAGE - 1)`, breaks on an empty page. No `package.json` or `node_modules` anywhere.
- **Contract doc** `docs/integration/rest-api.md`: Connecting, Endpoints, the 34-row `latest_rating` column table, Freshness (OD-1 hourly, OD-7 slot semantics with the 14:07/14:12 example, OD-4 90 minutes, OD-9 a failed city keeps its last good row which reads `is_stale` true, `age_minutes` rounded up), Fallback rows (D-04: the newest row even when it is a fallback, a safe published value, not an error), Provisional values, What produced each row, Timestamps, Status codes, Write protection and visibility (OD-6), Limits and polling (no faster than every 60 seconds), Examples, PSS/E environment, OpenAPI, Compatibility, Monitoring.
- **What the tests prove, in plain English:** the three code samples work as written when the two environment values are supplied; they only read, send the key in one header, write no file and name no project; and the doc's column list cannot drift from the code's column list.
- **Mutation spot-check** (example or doc mutated, suite re-run, file restored; 14 mutations): killed at once were stopping paging on a short page, replacing `parse_ts` with `fromisoformat`, echoing the key in an error, a wrong curl page step, dropping the missing-city check, dropping a column row, removing PROVISIONAL from `rating_mw`, a bearer instruction, a changed hand-off sentence, a broken link, a wrong column type, a dropped OD-9 mention, a dropped heading. Two survived and were closed: dropping `curl -f` (now a test that every `curl` invocation uses `-fsS` plus a wrong-key run that must fail) and "exactly 90 minutes is stale" inside the Freshness section (the section's needles now include the exact rule).

## Task Commits

1. **Task 1 (tracer): three read-only examples, run as subprocesses against the in-process fake PostgREST** - `095ef01` (feat)
2. **Task 2: the REST interface contract `docs/integration/rest-api.md`, pinned to the contract module** - `60126da` (docs)
3. **Task 3: pointers from the four existing consumer docs, keeping Phase 4's pinned statements** - `1efa7ba` (docs)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

Tracer gate: `type="tracer"` without `gate="blocking-human"` and an automated-only `<verify>`, so the tracer verify was re-run end to end (15 passed, no skip, the 3.9 case ran) and expansion continued with no checkpoint.

## Files Created/Modified

- `docs/integration/rest-api.md` - consumer REST contract (API-01 units, API-02)
- `docs/integration/examples/read_ratings.py` - Python 3.7+ standard-library example (PSS/E)
- `docs/integration/examples/curl.sh` - curl example for any consumer
- `docs/integration/examples/supabase_js.mjs` - supabase-js example for the dashboard
- `backend/tests/example_read_ratings_test.py` - 15 tests running the examples against the fake
- `backend/tests/rest_api_doc_test.py` - 10 tests: column table, terms, hand-off, no connection details, links, pointers, headings
- `docs/frontend/specs/api-contract.md` - Authentication bullet, `public.latest_rating` data-sources row, open decisions 4 and 8 note
- `docs/frontend/specs/F1-data-access-api.md` - one bullet: live ratings resolved through `latest_rating`
- `docs/data-science/decisions/pss_e_handoff.md` - fixes section points to rest-api.md and the Python 3.7+ example; interpreter question
- `docs/data-science/schema/city_rating_v1.md` - three bullets inside existing sections (no new heading)

## Decisions Made

- The Python example fails fast when `latest_rating` does not return all four cities (exit 1 naming the missing city, history part not run).
- The doc contains no occurrence of the word "bearer" and says the key goes in `apikey` only, never in an `Authorization` header; the test enforces both.
- The doc says the DS owner checks write rejection live (E2E-03) instead of naming a plan code, because consumers read it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Extra tests beyond the plan's lists (15 and 10 functions instead of 10 and 9)**
- **Added:** `test_default_window_is_seven_days_back_to_one_hour_ahead`, `test_read_ratings_survives_a_server_cap_below_the_page_size`, `test_curl_example_stops_when_the_row_count_cannot_be_read`, `test_curl_example_fails_on_an_http_error` (the last because dropping `curl -f` survived the mutation check), and `test_consumer_docs_state_the_live_interface`.
- **Committed in:** 095ef01, 1efa7ba

**2. [Rule 2 - Missing critical] `--start` and `--end` are validated with `parse_ts`**
- **Issue:** an unparseable timestamp would otherwise travel into the URL and come back as an opaque server error.
- **Fix:** argparse rejects it with exit 2 before any request. A URL the interpreter cannot open is reported as "SUPABASE_URL is not a usable URL", never echoing the value.
- **Committed in:** 095ef01

**3. Attribution line.** The plan asked for `Co-Authored-By: Claude Opus 5.5`; the commits carry the session's attribution lines (`Claude Sonnet 5.5` plus the session link) per the executor instructions, as in 06-01 and 06-04.

### TDD note (Tasks 2 and 3)

Task 1: tests written first, run, 9 failed and 4 errored because the example files did not exist, then the examples made all green. Task 2: the doc was drafted before its test file, so the RED run was produced by moving the doc aside (6 of 6 tests failed with `FileNotFoundError`), then restoring it; the real check of the tests' strength is the 8-mutation run above, which found one gap (the 90-minute rule inside the Freshness section) that was closed. Task 3: the three new tests were written first and failed for the intended reasons (no link in any of the four docs, no view or word-rule text); the heading test passed from the start by design (it guards what must not change), and a one-heading mutation confirms it fails when a heading is lost. As in 06-01 and 06-04, the plan asks for one commit per task, so there is no separate RED commit.

---

**Total deviations:** 2 auto-added (Rule 2), 1 attribution wording note.
**Impact on plan:** no scope creep; every truth in `must_haves` is covered by a named test.

## Discrepancies

- **Part 1 city order.** The plan says the Python example prints "four city lines in config.LOCATIONS order". It asks the service for `order=city` (alphabetical, as the doc and curl do) and then re-sorts client-side by `CITIES`, so the printed order is AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO. curl and supabase-js print in the service's alphabetical order, as the plan specifies for them.
- **curl.sh avoids `tr -d` and `awk -F`.** The read-only test forbids the short curl write flags (`-d`, `-F`) as case-sensitive tokens, and those spellings also occur in `tr -d '\r'` and `awk -F/`. The script strips nothing and uses `awk 'BEGIN {FS = "/"} ...'`, which also removes the need to delete a carriage return (awk's whitespace strip handles it).
- **Runbook link has no anchor.** rest-api.md's Monitoring section names "section 14 of the live runbook". Section 14 is added by 06-07, so the link targets the runbook file (which exists) and the section is named in text; either plan order leaves a correct result (the plan's `coupling_justified`).
- **Hosted behaviour is still two assumptions, now stated in the doc's own words only where safe.** (A21) Python 3.7 itself cannot be run here; D-11 rests on the `feature_version=(3, 7)` syntax gate, the standard-library-only check, and runs on 3.9.6 and 3.12. (A22) The examples filter `valid_time` twice (`gte` and `lt`) as the fake does; if the live run in 06-11 rejects two filters on one column, the examples switch to the `and=(...)` form. Neither was run against the hosted service.
- **supabase-js was not run.** Only `node --check` was possible without installing the package; the install and the live run wait for 06-11's legitimacy checkpoint.
- **Phase 7 hand-off.** Phase 7's REVAL-01 go must remove the word `provisional` from both `rating_basis` and `config_version` for `is_provisional` to turn false; a phrase such as "no longer provisional" would still read as provisional. Recorded in `rest-api.md` ("Provisional values") and `city_rating_v1.md` ("Provisional label (OD-5)").

## Issues Encountered

None blocking. The full default suite (`.venv/bin/python -m pytest -q -p no:cacheprovider`) reported 1858 passed, 81 skipped, 0 failed (the skips are env-gated and local-Postgres tests; none come from this plan's files, which ran with `-rs` and reported no skip). `secret_scan_test.py` was re-run after the commits, when the new files were tracked, and passes (the owner-local exact-value test stays env-gated). Pre-existing working-tree changes (.DS_Store files, `.planning/config.json`, untracked `.obsidian/`, `graphify-out/`, `docs/data-science/decisions/shadow_early_decision_options.md`, etc.) were left unstaged.

## Known Stubs

None. No placeholder text, empty-value-to-UI paths or unwired data in the files this plan created. The `<value from the DS owner>` markers in the examples and the doc are deliberate instructions, not stubs.

## Threat Flags

None. The surface (public docs and examples, consumer authentication, TLS) is exactly the plan's threat model: T-06-19 (no project value; scan-line check in both test files plus the repository-wide scan), T-06-20 (apikey only, one credential header asserted from the recorded requests, no bearer word), T-06-21 (PROVISIONAL on every amps and MW row, `is_provisional` rule and hand-off, fallback documented as valid), T-06-22 (default certificate verification, no unverified context). T-06-SC stays accepted (nothing installed; the `@2` install line is documentation).

## User Setup Required

None - no external service configuration required. To run an example against the live project the owner supplies `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` in a shell (never a committed file); that is 06-11. Nothing was pushed and nothing contacted the Supabase project.

## Next Phase Readiness

- Ready for 06-07 (runbook section 14 that the doc's Monitoring section names) and 06-08 onward. `fake_postgrest.py` and the examples' subprocess pattern are reusable.
- API-01 and API-02 stay open in REQUIREMENTS.md on purpose: later plans (06-09, 06-11 and others) also declare them, and their live halves are the owner's runs.
- Before the teams are told about the interface: the owner applies 06-01's migration (06-09), then 06-11 runs each example once against the live project (after the supabase-js legitimacy check) and resolves the two hosted-behaviour assumptions above.

## Self-Check: PASSED

- Files present: `docs/integration/rest-api.md`, `docs/integration/examples/read_ratings.py`, `docs/integration/examples/curl.sh`, `docs/integration/examples/supabase_js.mjs`, `backend/tests/example_read_ratings_test.py`, `backend/tests/rest_api_doc_test.py` (all FOUND).
- Commits `095ef01`, `60126da` and `1efa7ba` are ancestors of HEAD; `git rev-list --count 5988b29..HEAD` measured 3 at SUMMARY time.
- Acceptance criteria re-run: `bash -n curl.sh` exits 0; `/usr/bin/python3 -I` parses `read_ratings.py`; no `package.json` or `node_modules` at the root or in the examples directory; 15 test functions in the example test (at least 10) and 10 in the doc test (at least 9); `grep -c PROVISIONAL rest-api.md` prints 11 (at least 10); `SUPABASE_PUBLISHABLE_KEY` appears in rest-api.md 3 times; the columns heading appears once; each of the four consumer docs links to `integration/rest-api.md`; `tail -n 1 pss_e_handoff.md` ends with "recorded as a standalone note per the user's request.*".
- Verify commands: `example_read_ratings_test.py` 15 passed (no skip); `rest_api_doc_test.py` plus `secret_scan_test.py` and `supabase_schema_doc_test.py` pass; full suite 1858 passed, 81 skipped, 0 failed.
- `git status --porcelain -- data/shadow .github/workflows/shadow_collect.yml` prints nothing; nothing pushed; nothing contacted the live project.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-26*
