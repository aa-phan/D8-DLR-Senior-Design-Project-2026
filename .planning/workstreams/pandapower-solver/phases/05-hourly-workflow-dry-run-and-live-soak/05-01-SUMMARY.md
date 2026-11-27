---
phase: 05-hourly-workflow-dry-run-and-live-soak
plan: 01
subsystem: ops
tags: [github-actions, base64-secrets, closed-vocabulary-printer, dry-run, pandapower, leak-guard]

requires:
  - phase: 02-study-engine
    provides: engine.prepare_run, engine.load_recorded_backend, engine.is_placeholder, engine.SOLVER
  - phase: 03-solver-tag-migration-and-per-solver-gaps
    provides: job.run_once(..., solver=) and the tagged writer
  - phase: 04-replay-and-agreement-check
    provides: the replay_cli printer and error-handling pattern copied here
provides:
  - "backend/pandapower_job/hourly.py: the hourly runner (closed printer, OutputSink, mode gate, secret materialisation, dry and live paths, main)"
  - "backend/pandapower_hourly.py: the entry script the workflow runs with python -I -B"
  - "backend/tests/pandapower_hourly_fixture.py and pandapower_hourly_test.py: public-fixture environment helper and 78 pure-tier tests"
affects: [05-02, 05-03, 05-04, 05-05, workflow, owner-bundle-command, soak]

actuals:
  tokens: 12400
  tasks: 3
  commits: 3
plan_head_before: e24366a029078131298fd1dce0f7523497e4bf82
plan_head_after: 90f08a0bc18d93b0edab31448cd20e92bce59c76

tech-stack:
  added: []
  patterns:
    - "one printer that accepts only compiled vocabulary patterns ending \\Z; no pattern starts with a colon"
    - "OutputSink: descriptors 1 and 2, sys streams, logging and warnings to the null device, restored on exit"
    - "dry path with no connect parameter; writer-side modules imported only inside live_run"
    - "secrets decoded only into mkdtemp under RUNNER_TEMP, removed in finally"

key-files:
  created:
    - backend/pandapower_job/hourly.py
    - backend/pandapower_hourly.py
    - backend/tests/pandapower_hourly_fixture.py
    - backend/tests/pandapower_hourly_test.py
  modified: []

key-decisions:
  - "A decoded secret exactly at its cap is accepted, one byte over is too_large (cap compared with >)"
  - "Surrounding ASCII whitespace of a secret is stripped before strict base64 decoding; inner whitespace is bad_base64"
  - "Usage lines go through the same printer on stdout; stderr stays empty"
  - "The fresh-interpreter proof compares psycopg with a pandapower-only baseline and blocks psycopg.connect, because pandapower itself imports psycopg"

requirements-completed: [OPS-02, OPS-03]

coverage:
  - id: D1
    description: "run command: four base64 secrets to a dry four-city pandapower run on the public fixture, printed as counts only, temporary folder removed"
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_tracer_dry_run_end_to_end_prints_counts_and_writes_nothing"
        status: pass
    human_judgment: false
  - id: D2
    description: "live only for the exact text true; placeholder refused before fetch, prepare or connect; live call tagged pandapower; every input refusal"
    requirement: OPS-03
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_mode_is_live_only_for_the_exact_text_true"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_live_with_a_placeholder_backend_is_refused_before_any_connect_or_study"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_live_run_calls_run_once_with_the_pandapower_tag"
        status: pass
    human_judgment: false
  - id: D3
    description: "public-log routes closed: descriptors, logging, warnings and tracebacks cannot reach the output; dry run loads no writer-side module"
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_sinks_keep_descriptors_logging_and_warnings_out_of_the_output"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_without_the_sink_the_planted_noise_escapes"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_test.py#test_a_fresh_interpreter_dry_run_loads_no_writer_side_module"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-11-26
status: complete
---

# Phase 5 Plan 1: Hourly Runner `run` Command Summary

**A dry-by-default hourly runner: four base64 secrets become private files in a removed temporary folder, the real four-city pandapower study runs, and only closed-vocabulary count lines reach the public log, with live mode gated on the exact text `true` and refused on a placeholder.**

## Performance

- **Duration:** about 45 min (estimated; no start timestamp was captured)
- **Completed:** 2026-11-26
- **Tasks:** 3 of 3
- **Files modified:** 4 created, none changed

## Accomplishments

- `python -I -B backend/pandapower_hourly.py run` decodes `PANDAPOWER_NETWORK_B64`, `PANDAPOWER_MAPPING_B64`, `PANDAPOWER_SETTINGS_B64` and `PANDAPOWER_SCALING_B64` into a fresh folder (under `RUNNER_TEMP` when set), loads the recorded settings, runs the study and prints at most eight lines. The tracer test runs the real solver on the public 39-bus fixture (about 16 s).
- Live mode is on only for `PANDAPOWER_LIVE` equal to `true`. Absent, empty, `True`, `TRUE`, `1`, `yes`, `false`, ` true`, `true ` and `true` plus a newline are all dry. A live run on a placeholder backend prints `placeholder: refused` and exits 2 with the recording stand-ins for fetch, connect and prepare never called. A live run without `SUPABASE_PSSE_DB_URL` is `missing_secret` before any folder exists.
- The live call is `job.run_once(..., env=environ, solver=engine.SOLVER)`; the test checks the tag, the environment identity, the neutral case id `network.json`, and that the runner never calls `connect` itself.
- `OutputSink` closes the public-log routes. A planted token (`NOISE-` plus a branch key) written by `print`, `sys.stderr`, `os.write` on descriptors 1 and 2, `warnings.warn`, the `pandapower` logger and the `psse_job.job` logger never reaches `capfd` or `caplog`; with `sink=False` the same run lets it escape, so the test has teeth. Logging, warnings, streams and descriptors are verified restored afterwards.

## Final vocabulary (`HOURLY_LINE_PATTERNS`, each ends `\Z`)

```
mode: (dry|live)
inputs: ok
inputs: refused (missing_secret|bad_base64|too_large|unwritable)
records: refused (the eleven engine.RECORD_REFUSAL_REASONS)
placeholder: refused
ratings: city_rating=N static=N
study: ok
study: failed at stage (the ten constants.FAILED_STAGES)
outcome: (ok|fallback|failed)
rows: run=N dispatch=N margin=N contingency=N
dry run: nothing was written to the database
run status: (written|already_recorded|failure_recorded|not_recorded)
usage: pandapower_hourly.py {run,soak,bundle,scan-log} ...
usage error: (bad or missing arguments|unknown command)
error: unexpected (ClassName)        # [A-Z][A-Za-z]{0,39}
```

N is `[0-9]{1,9}`, so no printed line carries a decimal number.

## Seams of `main`

`main(argv, out=None, environ=None, repo_root=None, fetch=None, connect=None, clock=None, prepare=None, backend_loader=None, sink=True)` never raises. `out` (printer stream, default a duplicate of the real stdout), `environ` (default a copy of `os.environ`), `fetch` (ratings read, default `ratings.fetch_latest_rating(environ)`), `connect` (live writer connection, default `writer.connect` bound to the environment), `clock`, `prepare` (default `engine.prepare_run`), `backend_loader` (default `engine.load_recorded_backend`) and `sink=False` (no redirects) are the test seams. `repo_root` is accepted for the later commands and unused by `run`. Other public names: `decide_mode`, `materialize`, `dry_run`, `live_run`, `OutputSink`, `InputsRefused`, `DryOutcome`, `LiveOutcome`, `SECRET_ENV`, `READ_ENV`, `COMMAND_FLAGS`, `USAGE_LINE` and the exit constants.

## Task Commits

1. **Task 1: Tracer, four base64 secrets to a dry four-city run** - `2c90707` (feat)
2. **Task 2: Live switch, input refusals, placeholder refusal, tagged live call** - `937f1a8` (feat)
3. **Task 3: Close the public-log routes (OutputSink, vocabulary proofs, writer-free dry run)** - `90f08a0` (feat)

**Plan metadata:** the docs commit that follows this file.

## Files Created/Modified

- `backend/pandapower_job/hourly.py` - the runner
- `backend/pandapower_hourly.py` - entry script (`sys.exit(hourly.main(sys.argv[1:]))`)
- `backend/tests/pandapower_hourly_fixture.py` - `FIXED_NOW`, `secret_files`, `hourly_env`, `fake_fetch_for`, `fake_pandapower_study`, `fast_prepare`
- `backend/tests/pandapower_hourly_test.py` - 78 tests (529 lines)

## Decisions Made

See `key-decisions`. In short: the cap check is inclusive, outer whitespace of a secret is ignored, usage output uses the one printer on stdout, and the writer-free proof uses a baseline because pandapower itself loads psycopg.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug in the plan's test premise] A fresh interpreter cannot show `psycopg` unloaded**
- **Found during:** Task 3 (fresh-interpreter test)
- **Issue:** the plan asks the child to report that none of `psse_job.writer`, `psse_job.job`, `psse_job.gaps`, `psycopg` is in `sys.modules`. Importing `pandapower` alone loads `psycopg` (its `sql_io` module imports it when installed, here and on the runner), so the literal assertion fails for a reason that has nothing to do with the runner.
- **Fix:** the child now records whether `psycopg` is loaded after `import pandapower` alone, replaces `psycopg.connect` with a stub that counts calls, runs the dry run, and the test asserts that the three writer-side modules are unloaded, that `psycopg` presence is unchanged by the runner, and that the stub was called 0 times. A second test (`test_the_runner_module_never_imports_a_database_driver`) walks the AST of `hourly.py` for any `psycopg` import. The D-10 claim (the dry path loads no writer and opens no connection) is still proven; the weaker claim "psycopg is absent" was never true.
- **Files modified:** `backend/tests/pandapower_hourly_test.py`
- **Verification:** both tests pass.
- **Committed in:** `90f08a0`

**2. [Rule 3 - Blocking, own tooling] A stray `cat` in one of my shell commands hung until killed**
- **Found during:** Task 2
- **Issue:** a leftover `cat > "$TMP/..."` waited on stdin and held the following edit script; killing it released the script, which then applied the one intended edit to `hourly.py`.
- **Fix:** verified the file state by function listing and a diff stat before continuing; no duplicate edit. No effect on the committed result.

---

**Total deviations:** 1 plan correction (test premise), 1 tooling slip with no effect on output
**Impact on plan:** none on scope; the D-10 guarantee is proven more precisely.

## Issues Encountered

- The `materialize` guard for a value that decodes to nothing is unreachable for non-blank input (`====` already raises `binascii.Error`), so `bad_base64` covers it; the guard stays as defence in depth.
- The fixture's `PANDAPOWER_NETWORK_B64` is 34,712 characters (the real network's is 33,588) and still passed through a Windows child-process environment in the fresh-interpreter test, so the size of one base64 value is not a problem for the tests on this machine.

## Known Stubs

None. `COMMAND_FLAGS` holds only `run`; `soak`, `bundle` and `scan-log` are named in the usage line by design and arrive in plans 05-04 and 05-05 (an unknown command prints the usage lines and exits 2).

## Threat Flags

None. No network endpoint, auth path or schema was added; the live path reuses `job.run_once` and `writer.connect` unchanged.

## Verification Results

- `backend/tests/pandapower_hourly_test.py`: 78 passed, 0 skipped (about 48 s).
- `pandapower_import_gate_test.py`, `pandapower_replay_readonly_test.py`, `pandapower_study_job_test.py`: 35 passed, 4 skipped (the study-job Postgres proofs skip without a database, as the plan expects).
- `private_leak_scan.py --staged` exited 0 before each commit; the full scan exited 0.
- `git diff --stat HEAD -- backend/psse_job` is empty; the file-scope gate for 05-01 exits 0.
- The AST check shows no module-level import of `job`, `writer` or `gaps` in `hourly.py`.

## User Setup Required

None in this plan. The four secrets, the repository variable and the workflow arrive in plans 05-03 and 05-05.

## Next Phase Readiness

Plan 05-02 onward can call `hourly.main` and extend `COMMAND_FLAGS`. The database tier (a dry run leaves the four tables unchanged, a live run stores a `pp-` run with solver `pandapower`) is plan 05-04's. Nothing here has run on GitHub: the branch is not on `main` (D-07).

## Self-Check: PASSED

All four files exist; commits `2c90707`, `937f1a8` and `90f08a0` are ancestors of HEAD.

---
*Phase: 05-hourly-workflow-dry-run-and-live-soak*
*Completed: 2026-11-26*
