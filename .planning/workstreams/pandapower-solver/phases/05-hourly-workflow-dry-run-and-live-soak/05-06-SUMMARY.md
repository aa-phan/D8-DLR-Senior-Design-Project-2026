---
phase: 05-hourly-workflow-dry-run-and-live-soak
plan: 06
subsystem: ops
tags: [rehearsal, runbook, decision-record, fresh-interpreter, loopback, owner-hand-off]
status: complete

requires:
  - phase: 05-hourly-workflow-dry-run-and-live-soak
    provides: "05-01 the runner and the entry script; 05-03 the workflow; 05-04 the soak command; 05-05 the bundle and scan-log commands and the private-tree fixture"
provides:
  - "backend/tests/pandapower_hourly_rehearsal_test.py: the workflow's exact two commands run in a fresh interpreter on secrets written by bundle"
  - "docs/data-science/decisions/pandapower_hourly_runbook.md: the owner's 14-section procedure for everything after the merge"
  - "backend/tests/pandapower_hourly_runbook_test.py: six text checks that keep the runbook, the workflow and the runner in agreement"
  - "docs/data-science/decisions/pandapower_live_write_decision.md: the OPS-03 decision record, Status Proposed, with the gate and its evidence"
affects: [05-07, 05-08, owner-hand-off]

actuals:
  tokens: 15500
  tasks: 3
  commits: 3
plan_head_before: fdaffbb30df5c713e4b2d1d7ced7f1aa9d8a1f89
plan_head_after: 8985eb88c92751024eed155076e6ed138b32d6fb

tech-stack:
  added: []
  patterns:
    - "rehearse the workflow, not the library: subprocess.run([sys.executable, '-I', '-B', entry script, 'run']) with a stripped environment, so the output sink works on real descriptors outside pytest's capture"
    - "a text test compares names across three owners (runbook, workflow, runner constants) instead of pinning any of them, and carries teeth for its own credential-shape regexes"

key-files:
  created:
    - backend/tests/pandapower_hourly_rehearsal_test.py
    - backend/tests/pandapower_hourly_runbook_test.py
    - docs/data-science/decisions/pandapower_hourly_runbook.md
    - docs/data-science/decisions/pandapower_live_write_decision.md
  modified: []

key-decisions:
  - "The runbook gives the local count comparison without naming an operating system as a requirement: the runner is Linux and the owner's machine is Windows, so the comparison is the very check for an operating-system difference; the plan's wording 'Linux comparison' is kept in the decision record's gate"
  - "The runbook's section 6 line table is checked against HOURLY_LINE_PATTERNS with sample lines, so a renamed vocabulary line fails the text test"

requirements-completed: []

coverage:
  - id: D1
    description: "the exact command the workflow runs, in a fresh interpreter with GITHUB_ACTIONS true, RUNNER_TEMP set and the four secrets read from the files bundle wrote, reads the ratings from a loopback stand-in of the view, completes a dry run with exit 0, prints only vocabulary lines, writes nothing on stderr, leaves RUNNER_TEMP empty, sends one request carrying the key, and its stdout scans clean against the throwaway tree's needles and the bundled values"
    requirement: OPS-02
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_rehearsal_test.py#test_tracer_entry_script_dry_run_in_a_fresh_interpreter"
        status: pass
    human_judgment: false
  - id: D2
    description: "PANDAPOWER_LIVE set to the wrong-case text True still prints mode: dry"
    requirement: OPS-03
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_rehearsal_test.py#test_wrong_case_variable_stays_dry"
        status: pass
    human_judgment: false
  - id: D3
    description: "the soak command, run as the writer role against a throwaway Postgres, prints counts-only gap and soak lines and exits 0 with nothing on stderr"
    requirement: OPS-03
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_rehearsal_test.py#test_entry_script_soak_against_a_throwaway_postgres"
        status: pass
    human_judgment: false
  - id: D4
    description: "the runbook, the workflow and the runner agree on the four bundle secret names, the three Supabase settings, the live variable, every command and flag, the temporary-folder prefix, the cron settings and the six exit codes, and the runbook holds no credential-shaped text"
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_runbook_test.py#test_runbook_names_every_secret_the_workflow_and_runner_use"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_runbook_test.py#test_runbook_commands_and_flags_match_the_runner"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_runbook_test.py#test_workflow_run_lines_and_removal_step_match_the_runner"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_runbook_test.py#test_runbook_cron_settings"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_runbook_test.py#test_runbook_exit_codes_match_the_runner"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_runbook_test.py#test_runbook_holds_no_credential_shaped_value"
        status: pass
    human_judgment: false
  - id: D5
    description: "a decision record for the live switch exists with Status Proposed, the seven-item gate with evidence paths, three sections awaiting the owner and the undo procedure"
    requirement: OPS-03
    verification:
      - kind: other
        ref: "docs/data-science/decisions/pandapower_live_write_decision.md (task verify: grep checks, exit 0; 64-hex count 0)"
        status: pass
    human_judgment: false
  - id: D6
    description: "the runbook's steps work on GitHub as written (secret creation, dispatch, branch check, cron-job.org job, log download and scan, flip)"
    requirement: OPS-01
    verification: []
    human_judgment: true
    rationale: "GitHub's runner, its secret store and the cron-job.org account are not reachable from here; plan 05-07 has the owner follow the runbook and record the result"

duration: about 50 min (the rehearsal file runs 179 s)
completed: 2026-11-26
---

# Phase 5 Plan 06: Hand-off rehearsal, runbook and decision record Summary

**The workflow's exact `python -I -B backend/pandapower_hourly.py run` and `soak` commands are rehearsed in fresh interpreters on secrets written by `bundle` (loopback ratings view, throwaway Postgres), the owner has a 14-section runbook for every step after the merge with a text test that pins it to the workflow and the runner, and the live switch has a Proposed decision record with its seven-item gate.**

## Performance

- **Tasks:** 3 of 3
- **Files:** 4 created, none modified
- **Tests:** rehearsal file 3 passed in 179 s (`PSSE_REQUIRE_PG=1`, Postgres 17 autostart, nothing skipped); runbook file and the existing workflow file together 17 passed in 11 s; `pandapower_import_gate_test.py` 4 passed; whole-checkout `private_leak_scan.py` exit 0.

## Accomplishments

- **Tracer (Task 1).** `_bundle_env(repo)` runs `hourly.bundle` in-process on a synthetic private tree in a throwaway repository and reads the four values back from the files. `_child_env(**values)` is the parent environment minus every `SUPABASE_*`, `PANDAPOWER_*` and `GITHUB_*` name. The child runs `[sys.executable, "-I", "-B", "backend/pandapower_hourly.py", "run"]` from the repository root with `GITHUB_ACTIONS=true`, an empty `RUNNER_TEMP` and the loopback `FakeLatestRatingServer` as `SUPABASE_URL`. It exits 0, prints vocabulary lines only (first `mode: dry`, `ratings: city_rating=4 static=0`, last `dry run: nothing was written to the database`), prints nothing on stderr, leaves `RUNNER_TEMP` empty, and the server saw exactly one request, to `/rest/v1/latest_rating`, carrying the key. The captured stdout, written outside the private tree, scans clean against the tree's derived needles and against the four values, their long tokens and the two source-file hashes; a planted copy of a bundled value is found, so the scan can fail. A second child with `PANDAPOWER_LIVE=True` still prints `mode: dry`. The database-tier test seeds three pandapower runs in the three hours before the database's current hour and runs the child `soak` as `dlr_psse_writer`: exit 0, `gap check: solver pandapower runs=3 gaps=0`, `soak: consecutive_slots=3 of 24 fallback_slots=3`, `soak: not yet`, nothing on stderr.
- **Runbook (Task 2).** `pandapower_hourly_runbook.md`, sections 1 to 14 in the layout of `dlr_live_runbook.md`: purpose, order of setup (nothing runs before the owner's merge, D-07), the seven secrets of the `production` environment with who creates each (the repository owner; the build account has push but not admin rights), how the holder runs `bundle` and hands over the four files, `gh secret set NAME --env production < FILE`, the first dispatch and the branch check, the cron-job.org table (`20 * * * *`, the dispatch URL, `{"ref":"main"}`, a new fine-grained token, the 25-failure note), the printed lines and exit codes 0, 1, 2, 3, 5, 6, dry-run observation (3 green runs, `scan-log` on one real log, the local count comparison, the laptop task), go-live, soak, pause and resume, failure modes, rotation, retention, references. It names the capital-T `True` quirk (GitHub's case-insensitive comparison hands over the writer value; the runner stays dry) and the stale `SUPABASE_DB_URL` row of the other runbook. It holds names, commands and placeholders only.
- **Runbook test (Task 2).** Six text tests: secret names equal across runbook, workflow and `hourly.SECRET_ENV`; `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_PSSE_DB_URL` and `PANDAPOWER_LIVE` in both documents; every `pandapower_hourly.py WORD` of the runbook a key of `COMMAND_FLAGS` with its flags belonging to that command and every command present; the workflow's two run lines and its removal step against `COMMAND_FLAGS` and `TEMP_PREFIX`; the cron settings; the exit-code table equal to the `EXIT_*` constants (with sample lines of the vocabulary table checked against `HOURLY_LINE_PATTERNS`); and six credential shapes, each with a tooth assembled from pieces.
- **Decision record (Task 3).** `pandapower_live_write_decision.md`: Status Proposed, drafted 2026-11-25, the decision, the seven-item gate with evidence paths (NET-03, AGR-02 with the two unexercised kinds stated, the live migration, the retention decision, the local evidence, the dry-run conditions, the placeholder backstop), the three sections each holding "Not recorded yet." for plans 05-07 and 05-08, the undo procedure, consequences and references.

## Task Commits

1. **Task 1: Tracer, the workflow's exact command line in a fresh interpreter** - `57d4dde` (test)
2. **Task 2: Runbook and the agreement test** - `f024101` (docs)
3. **Task 3: Decision record, Status Proposed** - `8985eb8` (docs)

**Plan metadata:** the docs commit that follows this file.

## Files Created/Modified

- `backend/tests/pandapower_hourly_rehearsal_test.py` - 3 tests, module-scoped bundle on a throwaway repository, child-process helpers
- `docs/data-science/decisions/pandapower_hourly_runbook.md` - the 14-section owner procedure
- `backend/tests/pandapower_hourly_runbook_test.py` - 6 text tests
- `docs/data-science/decisions/pandapower_live_write_decision.md` - the Proposed decision record

## Decisions Made

- The local count comparison is written as "the owner's machine against the runner" and does not require Linux on the owner's side: the plan's "Linux comparison" is the runner side, and the point of the comparison is to catch an operating-system difference, which a Windows run shows as well.
- The runbook's section 6 table is validated against the runner's vocabulary through sample lines, because a renamed line would otherwise leave a stale table (the failure the older runbook already has).

## Deviations from Plan

None - plan executed exactly as written. One scripted edit of the runbook test left a broken string literal at first (an escaping slip in my own edit, caught by the collection error); it was corrected in place before the file was committed.

## Known Stubs

None. The three "Not recorded yet." lines in the decision record are the plan's intended placeholders, filled by plans 05-07 and 05-08.

## Threat Flags

None. The plan adds no endpoint and no code path; the rehearsal uses a loopback server and a throwaway database, and the documents hold names and commands only (T-05-23: credential-shape test, 64-hex count 0 on the decision record, staged leak scan exit 0 before each commit; T-05-24: the agreement test; T-05-25: the runbook requires a new fine-grained, repository-scoped, Actions-only token with an expiry reminder).

## Issues Encountered

None in the code under test. The rehearsal file passed at its first run. `git` printed LF-to-CRLF warnings on the new files; no test pins file bytes or asserts file modes. The known Windows-only failures named in the task brief were not touched. No command of this plan opened `data/private` of this checkout.

## Next Phase Readiness

- Plan 05-07: the owner follows the runbook sections 3, 4 and 7 and records the local and dry-run evidence in the decision record, replacing its "Local evidence" and "Dry-run evidence" lines.
- Plan 05-08: fills the retention limit and size, the dated owner decision and the soak record.
- OPS-01, OPS-02, OPS-03 stay Pending in REQUIREMENTS.md by the orchestrator's instruction until the owner steps and the live soak are done.

## Self-Check: PASSED

- FOUND: backend/tests/pandapower_hourly_rehearsal_test.py, backend/tests/pandapower_hourly_runbook_test.py, docs/data-science/decisions/pandapower_hourly_runbook.md, docs/data-science/decisions/pandapower_live_write_decision.md
- FOUND commits: 57d4dde, f024101, 8985eb8 (3 commits from the ledger base, measured with `git rev-list --count`)
- Rehearsal 3 passed; runbook and workflow tests 17 passed; import gate 4 passed; runbook section count 14; 64-hex count 0 in both documents; file-scope gate exit 0 after each commit; staged leak scan exit 0 before each commit; no change under backend/psse_job
