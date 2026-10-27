---
phase: 06-exposure-e2e-verification
plan: 11
subsystem: api
tags: [examples, supabase-js, postgrest, e2e-trace, cron-job-org, github-actions, owner-run]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "docs/integration/examples (curl.sh, read_ratings.py, supabase_js.mjs) from 06-06; backend/e2e_trace.py from 06-08; live REST exposure confirmed in 06-09"
  - phase: 05-hourly-live-run
    provides: "hourly cron-job.org dispatch of dlr_live.yml at minute 05 and the live city_rating rows"
provides:
  - "06-E2E-TRACE.md and 06-e2e-trace.json: one hh:05 cron-job.org execution traced to Actions run 40447756754, four city_rating rows and the identical REST rows (E2E-01)"
  - "Live proof that curl.sh, read_ratings.py (Python 3.9.6 and 3.12.13) and supabase_js.mjs (supabase-js 2.117.3) each ran as written and exited 0 (API-02)"
  - "06-11-PREFLIGHT.md owner command sheet with the approved supabase-js version pinned"
affects: [06-12, 06-13, 07-reval]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 36000
  tasks: 3
  commits: 6
plan_head_before: 45ea9e39d441d2d6afee1efbcc1b24de3bb2d8a3
plan_head_after: dd9fa40de956a7f80f17ecf15ad205647f830f27

tech-stack:
  added: []
  patterns:
    - "Owner-run live step with executor-side evidence checks: the executor never contacts the project; the owner's relayed output is recorded without URL, reference or key"
    - "Package legitimacy checkpoint before install: exact version approved by the owner, installed only in a scratch folder outside the repository with --ignore-scripts, integrity hash compared"

key-files:
  created:
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-11-PREFLIGHT.md
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-E2E-TRACE.md
    - .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-e2e-trace.json
  modified: []

key-decisions:
  - "supabase-js approved at exactly 2.117.3 (not the 2.118.0 named in the research): the owner's registry check recorded it, and the command sheet pins it so neither @2 nor latest is typed"
  - "The PSS/E interpreter question is non-blocking (D-11): at plan close the owner has not confirmed sending it, so it is recorded as an open owner follow-up with the date TBD"

patterns-established:
  - "Trace by an unchanged production trigger: the trace used the hh:05 cron-job.org execution as it was (04:05:02Z, HTTP 204); the dispatch job was not modified"

requirements-completed: [API-02, E2E-01]

coverage:
  - id: D1
    description: "supabase-js was approved by the owner at a blocking checkpoint before any install and installed only in a scratch folder outside the repository with install scripts disabled; version and integrity hash match"
    requirement: API-02
    verification:
      - kind: manual_procedural
        ref: "owner reply 'approved 2.117.3'; owner terminal: 9 packages added, 0 vulnerabilities, lockfile version 2.117.3, integrity matches (relayed 2026-10-27)"
        status: pass
    human_judgment: true
    rationale: "Package legitimacy is a blocking owner decision (gate blocking-human); only the owner can approve an install"
  - id: D2
    description: "curl.sh, read_ratings.py on /usr/bin/python3 3.9.6 and on .venv Python 3.12.13, and supabase_js.mjs each exited 0 on the live project, printed four cities and paged one city's history"
    requirement: API-02
    verification:
      - kind: manual_procedural
        ref: "owner terminal output relayed 2026-10-27 (all exit 0; AUSTIN history 52 rows from 2026-10-25T00:00Z)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Trace: one scheduled execution (2026-10-27T04:05:02Z, HTTP 204) to one successful Actions run (40447756754), four rows in SQL and REST, 31 stored columns equal per city, is_provisional word rule holds"
    requirement: E2E-01
    verification:
      - kind: other
        ref: "backend/e2e_trace.py exit 0, 06-e2e-trace.json (ok true, 8 of 8 links), 06-E2E-TRACE.md ('E2E TRACE OK')"
        status: pass
    human_judgment: false
  - id: D4
    description: "No committed evidence holds the project URL, reference, key or database URL; no package.json or node_modules in the repository"
    requirement: API-02
    verification:
      - kind: test
        ref: "backend/tests/secret_scan_test.py with both trace files staged: 5 passed, 1 skipped (owner-local live check); test ! -e package.json and node_modules; grep of both trace files for URL, host, key patterns: no matches"
        status: pass
    human_judgment: false
  - id: D5
    description: "PSS/E interpreter question (sys.version and ssl.OPENSSL_VERSION inside PSS/E's Python) sent to the Power Systems team"
    requirement: API-02
    verification: []
    human_judgment: true
    rationale: "A message only the owner can send; the owner has not confirmed sending it. Non-blocking by D-11; tracked as an open follow-up, not met as written"

duration: 1 session (pre-flight 2026-10-27 about 01:25Z; owner live run about 03:43Z to 04:10Z)
completed: 2026-10-27
status: complete
---

# Phase 6 Plan 11: Live examples and the end-to-end trace Summary

**All three consumer examples ran as written on the live project (curl.sh, read_ratings.py on Python 3.9.6 and 3.12.13, supabase_js.mjs on supabase-js 2.117.3), and one scheduled hh:05 trigger was traced through Actions run 40447756754 to four SQL rows and the identical four REST rows (31 columns each, E2E TRACE OK).**

## Performance

- **Duration:** one session; pre-flight about 01:25Z, owner live steps 03:43Z to about 04:10Z on 2026-10-27
- **Tasks:** 3 (1 tracer, 1 package-legitimacy checkpoint, 1 owner live run) plus the evidence commit
- **Files created:** 3 (pre-flight sheet, trace table, trace JSON)

## Package check (Task 2, API-02)

| Item | Value |
|---|---|
| Package | `@supabase/supabase-js` |
| Owner reply (verbatim) | "approved 2.117.3" |
| Version installed | **2.117.3**, exact (`--save-exact`), not `@2` or `latest` |
| Registry facts recorded at the checkpoint | published 2026-10-07, maintainer `@supabase.io`, GitHub Actions trusted publishing, no install scripts, Node 22 or newer |
| Install | scratch folder outside the repository, `--ignore-scripts`; 9 packages added, 0 vulnerabilities |
| Integrity (lockfile) | version `2.117.3`, `sha512-K+f8PimXDunPWQ63CKRXaF5pbVPJxmfw5ryAnh0s9S9PkwcuqBjiSpIaqpF7KLDljeYwXIL85ST8QxaO0+XuvA==`, matches the sheet |
| Node | v26.9.0 |

The research had named 2.118.0 (published 2026-10-15, flagged only for release recency). The owner chose the older 2.117.3 at the checkpoint; the command sheet was updated in `33479a8` before any install.

## Example results (Task 3, API-02)

All run by the owner in their own terminal with only `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` set. Relayed output; the executor never contacted the project.

| Example | Interpreter or runtime | Exit | First lines or result |
|---|---|---|---|
| `curl.sh` | bash | 0 | `latest_rating` 4 rows, valid_time 2026-10-27T03:00Z, age 43 min, all `is_stale` false, `is_provisional` true; AUSTIN fallback G4 1825 A. AUSTIN history 2026-10-25 to 2026-11-01: total 52 rows, one page |
| `read_ratings.py` (defaults) | `/usr/bin/python3` **3.9.6**, `-I` | 0 | 4 city lines; "AUSTIN rows from 2026-10-20T03:00:00Z to 2026-10-27T04:00:00Z: 53"; first row 2026-10-24T23:00:00Z, last 2026-10-27T03:00:00Z |
| `read_ratings.py --city AUSTIN --start 2026-10-25T00:00:00Z` | `.venv/bin/python` **3.12.13**, `-I` | 0 | 4 city lines; 52 rows; first 2026-10-25T00:00:00Z, last 2026-10-27T03:00:00Z |
| `supabase_js.mjs` | Node v26.9.0, supabase-js 2.117.3 | 0 | 4-row table; "AUSTIN rows from 2026-10-25T00:00:00Z to 2026-11-01T00:00:00Z: 52" |

- **Assumption A22 holds.** Two filters on the one `valid_time` column (a start and an end) were accepted by the hosted PostgREST, so the date-window history query works as written.
- **Python 3.9 grammar** is confirmed live (D-11: older than 3.11 on purpose); the example is also written to parse as 3.7.
- The 53 versus 52 rows between the two Python runs is the extra 2026-10-24T23:00Z row that the earlier default start (2026-10-20) includes and the explicit 2026-10-25 start excludes.

## Trace result (Task 3, E2E-01)

`backend/e2e_trace.py` exit 0, "E2E TRACE OK". The JSON confirms: `ok` true, 8 of 8 links pass, one candidate run, conclusion `success`, all four cities `match` true and `currency` current, and the `is_provisional` check passed.

| Link | Result |
|---|---|
| cron-job.org execution | 2026-10-27T04:05:02Z, HTTP 204 (scheduled hh:05 dispatch, unchanged job) |
| Actions run | 40447756754, created 2026-10-27T04:05:05Z (3 s later), workflow "DLR Live Ratings", event `workflow_dispatch`, completed, success, head `82c0332` |
| SQL rows | 4 rows for the run, one per city |
| pipeline_run | `cities_ok` lists all 4 cities, `window_end` 2026-10-27T04:05:00Z |
| REST rows | 4 rows for the run |
| SQL equals REST | 31 stored columns equal for each of the 4 cities |
| is_provisional | equals the word rule on `rating_basis` and `config_version` for all 4 cities |

Four-way table (all `valid_time` 2026-10-27T04:00:00Z, all `match` yes, all current):

| city | SQL rating (A) | REST rating (A) | status |
|---|---|---|---|
| AUSTIN | 1825.0 | 1825 | fallback (static, G4) |
| CORPUS_CHRISTI | 1520.0913199525 | 1520.0913199525 | ok |
| MIDLAND | 1465.62365478361 | 1465.62365478361 | ok |
| EL_PASO | 1281.16494535577 | 1281.16494535577 | ok |

The differences between SQL and REST that remain (for example `1825.0` against `1825`, `forecast_horizon_min` 60.0 against 60) are number-formatting differences between the two interfaces; the trace compares values, not text, and reports no mismatches.

## PSS/E interpreter question (D-11)

**Not confirmed sent.** At plan close the owner has not confirmed sending the question (`sys.version` and `ssl.OPENSSL_VERSION` inside PSS/E's Python, plus one run of `read_ratings.py`) to the Power Systems team. Per the plan this is non-blocking: the phase does not wait for the answer. Open owner follow-up, send date TBD. If the answer is Python 2.7, it is recorded as a follow-up (the example targets 3.7+), not a blocker.

## Evidence hygiene

- `backend/tests/secret_scan_test.py` with both trace files staged: 5 passed, 1 skipped (the skip is the owner-local live check that needs the three environment values; it is not a failure).
- `test ! -e package.json && test ! -e node_modules` in the repository: true.
- Grep of both trace files for `http(s)://`, `supabase.co`, JWT-shaped strings, `sb_publishable`, `sb_secret`, `ghp_`, `github_pat`, `apikey`, `Bearer`: no matches.

## Task Commits

1. **Task 1 (tracer): pre-flight and owner command sheet** - `71f2549` (docs)
2. **Task 2: supabase-js approved version pinned in the command sheet** - `33479a8` (docs)
3. **Task 3: owner live run; trace evidence committed** - `dd9fa40` (docs)

**Plan metadata:** the final docs commit (this SUMMARY plus state files).

Note: `actuals.commits: 6` is measured with `git rev-list --count 45ea9e3..dd9fa40`. It includes three 06-10 commits (`36c9522`, `82db455`, `91ac958`) that landed between this plan's commits; 06-11's own task commits are 3.

## Deviations from Plan

1. **PSS/E question not confirmed sent.** The plan's must-have says it "was sent". The owner has not confirmed that at close. The plan marks it non-blocking (D-11), so the plan completes with this open; tracked as an owner follow-up (see Discrepancies). The plan's task 3 done criterion "the PSS/E question as sent" is therefore NOT met as written.
2. **Co-Authored-By line.** The plan text names Claude Opus 5.5; commits in this continuation carry the runtime's configured attribution line instead (Claude Sonnet 5.5), as the environment instructs.

## Discrepancies

- **PSS/E question unsent** (above): plan truth not met as written; owner follow-up, date TBD.
- **MIDLAND `observation_time` is 2026-10-27T02:00:00Z while the other three cities show 03:00:00Z**, all in the same run and all `valid_time` 04:00Z. SQL and REST agree, so the trace is clean; the row is current. This is informational: MIDLAND's newest upstream weather observation was one hour older than the others at that run. Worth a glance if it repeats during the soak (06-12 data).
- **AUSTIN published the static fallback again** (G4: computed 1098 A judged implausible, so 1825 A). Same pattern the dry soak recorded (AUSTIN 50 % fallback). The row is fresh and valid for the trace; the underlying cause is for a later review, not this plan.
- **Owner-side facts** (all example outputs, the registry checks, the npm install result, the cron-job.org execution time) are relayed by the owner. The executor verified only what is in the committed trace files and the repository, and never contacted the live project.
- The curl.sh output shows `valid_time` 03:00Z (run before the 04:05Z trigger), while the trace shows 04:00Z; these are different hours of the same hourly series, not a conflict.

## Issues Encountered

None beyond the deviations above.

## Known Stubs

None. No placeholder values or empty data flows in the files this plan created.

## User Setup Required

Done by the owner during this plan (examples, scratch install, trace). Open owner items:
- Send the PSS/E interpreter question to the Power Systems team and note the date (non-blocking).
- Optionally delete the scratch folder `~/dlr-js-check` (outside the repository) and unset `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` in the terminal used.

## Threat Flags

None. No new network endpoints, auth paths or schema surface; no URL, project reference, key or database URL appears in the committed evidence.

## Next Phase Readiness

- API-02 and E2E-01 evidence is committed. 06-12 (soak close, earliest at 2026-10-30T03:35:00Z) and 06-13 (permission re-check) are unaffected: this plan's reads were GET and HEAD plus one read-only database session and did not touch the soak jobs.
- Open follow-up carried forward: PSS/E interpreter answer.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-27*

## Self-Check: PASSED

- FOUND: 06-11-PREFLIGHT.md, 06-E2E-TRACE.md, 06-e2e-trace.json (phase directory)
- FOUND commits: 71f2549, 33479a8, dd9fa40 (ancestors of HEAD)
