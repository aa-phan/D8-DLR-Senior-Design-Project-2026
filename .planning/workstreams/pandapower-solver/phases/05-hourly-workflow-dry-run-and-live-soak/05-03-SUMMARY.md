---
phase: 05-hourly-workflow-dry-run-and-live-soak
plan: 03
subsystem: ops
tags: [github-actions, workflow, secrets, dry-run, text-test]
status: complete

requires:
  - phase: 05-hourly-workflow-dry-run-and-live-soak
    provides: "plan 05-01 runner env names and the pandapower_hourly_ temp-folder prefix; entry script backend/pandapower_hourly.py with commands run and soak"
provides:
  - ".github/workflows/pandapower_hourly.yml: dispatch-only, main-only hourly workflow, dry unless the repository variable PANDAPOWER_LIVE is exactly true"
  - "backend/tests/pandapower_hourly_workflow_test.py: eleven regex checks of the workflow (no PyYAML), with _workflow, _step, _env, _code_lines and _run_bodies helpers"
affects: [05-06, 05-07, 05-08, cron-job, go-live-decision]

actuals:
  tokens: 3850   # chars/4 over the two files changed (15,376 chars)
  tasks: 2
  commits: 2
plan_head_before: b62b646c1fa4e384c5f3b3deb4d56fb631b34f8d
plan_head_after: ebf7cb18fad2f2e31ec40814909a37a8e3b5e320

tech-stack:
  added: []
  patterns:
    - "workflow tests read the file as text with re and match command lines, not comments"
    - "per-step credentials: every secret enters through env on the one step that needs it"

key-files:
  created:
    - .github/workflows/pandapower_hourly.yml
    - backend/tests/pandapower_hourly_workflow_test.py
  modified: []

key-decisions:
  - "The live switch is only vars.PANDAPOWER_LIVE; the study step receives the writer secret only through a conditional on that variable, so a dry run's study step never holds it"
  - "The soak step holds the writer secret unconditionally (read-only session), so it also proves the credential and the live migration from the runner before the flip"
  - "Env-line comments sit on their own lines, not trailing, so the text tests count code lines exactly"

requirements-completed: []  # OPS-01 and OPS-02 stay Pending until the owner steps and the live soak are done (orchestrator instruction)

coverage:
  - id: D1
    description: "workflow_dispatch is the only trigger, no inputs anywhere, own group pandapower-hourly with cancel-in-progress false, read-only token"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_tracer_workflow_is_dispatch_only_with_its_own_group"
        status: pass
    human_judgment: false
  - id: D2
    description: "the study job runs only on main in the production environment with a 30-minute timeout below the 60-minute cadence; install, study, soak and removal steps run in order"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_job_runs_only_on_main_in_the_production_environment"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_timeout_is_30_minutes_and_below_the_cadence"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_steps_run_the_entry_script_in_order"
        status: pass
    human_judgment: false
  - id: D3
    description: "install line matches the requirements.txt psycopg pins; setup step caches on requirements-pandapower.txt"
    requirement: OPS-01
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_install_line_and_pins_match_requirements"
        status: pass
    human_judgment: false
  - id: D4
    description: "the study step receives exactly eight env names; the writer value only when the variable is true; the soak step only the writer value; no other step any env or expression"
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_study_step_receives_the_secrets_and_the_switch"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_writer_value_reaches_the_study_step_only_when_live"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_soak_step_receives_only_the_writer_value"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_no_other_step_receives_anything"
        status: pass
    human_judgment: false
  - id: D5
    description: "no expression inside a run body, no secret in an if, no set -x, printenv, cat or echo, only the two first-party actions"
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_no_expression_inside_a_run_body_and_no_secret_in_an_if"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_workflow_test.py#test_no_debug_or_echo_and_only_first_party_actions"
        status: pass
    human_judgment: false
  - id: D6
    description: "branch dispatch does not run the job and the production environment is main-only; the cron job fires at :20 UTC (live checks, not text checks)"
    requirement: OPS-01
    verification:
      - kind: manual
        ref: "plan 05-07 owner checkpoints"
        status: pending
    human_judgment: true
---

# Phase 5 Plan 3: Hourly workflow and its text test Summary

**Dispatch-only, main-only hourly pandapower workflow that is dry unless the repository variable `PANDAPOWER_LIVE` is exactly `true`, with each secret entering only the step that needs it, pinned by eleven regex tests.**

## Performance

- Duration: about 15 minutes
- Tasks: 2 of 2
- Commits: 2 (`edc132a`, `ebf7cb1`)

## What was built

**Task 1 (tracer), `edc132a`.** `.github/workflows/pandapower_hourly.yml` in the shape of `dlr_live.yml`: `workflow_dispatch` with no inputs, `permissions: contents: read`, concurrency group `pandapower-hourly` with `cancel-in-progress: false`, one job `study` guarded by `github.ref == 'refs/heads/main'`, in the `production` environment, 30-minute timeout. Steps in order: "Checkout code (main)" (with `persist-credentials: false`), "Set up Python 3.12" (cache on `requirements-pandapower.txt`), "Install dependencies" (the pandapower pins plus the two `requirements.txt` psycopg pins), "Run study" (`python -I -B backend/pandapower_hourly.py run`), "Gap and soak check" (`if: success() || failure()`, `... soak`), "Remove private files" (`if: always()`). Five tests written first and seen failing, then passing.

**Task 2, `ebf7cb1`.** The env blocks. "Run study" maps eight names: the switch (`vars.PANDAPOWER_LIVE`), `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, the four base64 secrets, and `SUPABASE_PSSE_DB_URL` through the `vars.PANDAPOWER_LIVE == 'true' && secrets... || ''` conditional. "Gap and soak check" maps only the plain writer secret. No other step has an `env:` block or a `${{`. Six more tests, four of them failing before the env lines existed.

## Verification

- `pytest backend/tests/pandapower_hourly_workflow_test.py backend/tests/dlr_live_workflow_test.py`: 16 passed (11 new, 5 existing), nothing skipped.
- Non-comment lines: `vars.PANDAPOWER_LIVE` 2, `secrets.SUPABASE_PSSE_DB_URL` 2, `group: pandapower-hourly` 1.
- `git diff --stat HEAD -- .github/workflows/dlr_live.yml .github/workflows/shadow_collect.yml` prints nothing.
- File-scope gate (PLAN=05-03) exits 0; staged leak scan exited 0 before both commits.

## Deviations from Plan

None. The plan was executed as written. One test regex was loosened during Task 1 (the `cache-dependency-path` line may carry a trailing comment, as the other command-line regexes allow); this was a test-authoring fix before the first commit, not a change to the plan.

## Authentication gates

None.

## Known Stubs

None.

## Threat Flags

None. The workflow adds the surface the plan's threat model already lists (T-05-10 to T-05-14, T-05-SC); no new package, endpoint or schema.

## Open items for later plans

- Plan 05-07 (owner): the live checks this plan cannot make, namely that a branch dispatch skips the job, that the `production` environment's branch policy is main only, and that cron-job.org fires at :20 UTC. The workflow file is inert until the owner merges it to main (GitHub dispatches only a workflow whose file is on the default branch) and creates the four base64 secrets, `SUPABASE_PSSE_DB_URL` and the cron job.
- Plan 05-06's runbook test should cross-check the env names in this workflow against the runner.
- OPS-01 and OPS-02 are deliberately left Pending in REQUIREMENTS.md.

## Self-Check: PASSED

- FOUND: `.github/workflows/pandapower_hourly.yml`
- FOUND: `backend/tests/pandapower_hourly_workflow_test.py`
- FOUND: commits `edc132a` and `ebf7cb1` (ancestors of HEAD)
