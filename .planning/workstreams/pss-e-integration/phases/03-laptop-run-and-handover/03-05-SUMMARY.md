---
phase: 03-laptop-run-and-handover
plan: 05
subsystem: infra
tags: [task-scheduler, xml-template, renderer, sch-01, quoting, mutation-tested]

requires:
  - phase: 03-laptop-run-and-handover
    provides: plan 03-01 launcher parser (run --config, --dry-run, --allow-placeholder), 03-04 entry script backend/psse_run_hourly.py
provides:
  - docs/data-science/ops/psse_hourly_task.xml, the Task Scheduler template (placeholders PYTHON_EXE, ARGUMENTS, WORK_DIR, START_BOUNDARY)
  - backend/psse_job/taskxml.py (PLACEHOLDERS, TaskXmlError, build_arguments, next_start_boundary, render)
  - backend/psse_render_task.py, the install-time command
  - backend/tests/psse_task_xml_test.py (12 tests)
affects: [03-06 guide (render and register commands, the three questions), 03-07 laptop session runbook step 6, 03-08]

actuals:
  tokens: 12900
  tasks: 3
  commits: 3
plan_head_before: 40721fb56ca7415cb73eeac9c523283d9156dd3b
plan_head_after: 1af96adaac4a71ded95e61952225139a2bae977b

tech-stack:
  added: []
  patterns:
    - "policy checks as functions over text (_text_problems, _settings_problems, _problems) so planted variants prove each gate fires"
    - "refusal messages name the argument, never the value; TaskXmlError.argument lets the command map it to an option"
    - "re.sub with a function replacement so a backslash in a path is copied literally"
    - "output opened with mode x unless --force"

key-files:
  created:
    - docs/data-science/ops/psse_hourly_task.xml
    - backend/psse_job/taskxml.py
    - backend/psse_render_task.py
    - backend/tests/psse_task_xml_test.py
  modified: []

key-decisions:
  - "D-01 to D-06 of the plan implemented as written; the template's Settings hold the ten entries of the research template (the plan text says twelve; D-02 names ten distinct ones)"
  - "taskxml.py needs no allow-list change (os, re, datetime only; no xml import, no fromisoformat)"
  - "render normalises the template's CRLF to LF so a Windows checkout renders the same text; the tests read the template the same way"

patterns-established:
  - "Mutation harness outside the repository (scratchpad mutate_0305.py): exact-text replace, named tests, sha256 and git diff --quiet restore check"

requirements-completed: [SCH-01]

duration: not captured at spawn (single session, three tasks)
completed: 2026-10-29
status: complete
---

# Phase 3 Plan 05: Task Scheduler template and renderer Summary

**A committed Task Scheduler XML (one hourly time trigger with no end, IgnoreNew, PT45M, battery flags off, no catch-up, WakeToRun, interactive token with least privilege, placeholders only), a renderer that fills it from absolute existing paths with XML escaping, double quoting and refusal of anything unquotable or URL-shaped, and 12 tests that hold the template to its policy and prove its Arguments parse with the launcher's own parser. Nothing was registered with Windows.**

## Commits

| Commit | Subject |
|--------|---------|
| 5011766 | feat(03-05): tracer - the task template is rendered from tmp paths and its arguments are accepted by the launcher's parser |
| ad252c7 | test(03-05): every Task Scheduler setting and ban is pinned and each planted violation is named |
| 1af96ad | test(03-05): the renderer refuses unsafe values, escapes and quotes paths and writes UTF-8 without a byte-order mark |

`commits: 3` is measured (`git rev-list --count 40721fb..1af96ad`); the docs commit of this SUMMARY is not counted.

## Accomplishments

- Template: XML declaration UTF-8; Task 1.2 in the task namespace; one TimeTrigger (StartBoundary placeholder, Enabled, Repetition with Interval PT1H only); Principal Author with InteractiveToken and LeastPrivilege and no UserId or Password; Settings IgnoreNew, DisallowStartIfOnBatteries false, StopIfGoingOnBatteries false, AllowHardTerminate true, StartWhenAvailable false, RunOnlyIfNetworkAvailable false, WakeToRun true, Enabled true, Hidden false, ExecutionTimeLimit PT45M; one Exec (Command, Arguments, WorkingDirectory as placeholders). Comments say what each setting is for and label every real-scheduler behaviour UNVERIFIED until runbook step 6.
- `taskxml.render`: fills the four placeholders (Command double-quoted when it holds a space; Arguments `-X utf8 "ENTRY" run --config "CONFIG"` plus `--dry-run` and, with it, `--allow-placeholder`), XML-escapes ampersand, angle brackets and quotation marks, refuses a template that does not hold exactly the four tokens. `build_arguments` checks the form of both paths and the flag pair. `next_start_boundary` gives the next :MM strictly after now (default 15).
- Refused (TaskXmlError naming only the argument): empty or non-text, a line break or other control character, double quote, angle bracket, percent sign, an at-sign pair, `://`, a trailing backslash on a quoted file, a relative path, a missing file or folder (unless `check_exists=False`), a start boundary that is not a real YYYY-MM-DDTHH:MM:SS, `--allow-placeholder` without `--dry-run`, a minute outside 0 to 59.
- `psse_render_task.py`: exit 0 and `wrote PATH`; exit 2 with one stderr line naming the option (`refused --config: config_file must be an absolute path`) for a refusal, an unreadable template or an unwritable output; an existing output is not overwritten without `--force` (opened with mode x); UTF-8, LF, no byte-order mark. Defaults: `sys.executable`, `backend/psse_run_hourly.py` beside the script, the committed template, minute 15. `--start` and `--minute` exclude each other (argparse).

## Test results

| Command | Result |
|---------|--------|
| `psse_task_xml_test.py -k tracer` | 1 passed, 0 skipped (before the module existed: collection ImportError) |
| `psse_task_xml_test.py` after Task 2 | 6 passed, 0 skipped; `-k planted` 1 passed |
| `psse_task_xml_test.py` after Task 3 | 12 passed, 0 skipped |
| `psse_contract_test.py` | 10 passed after Task 1 (Python 3.7 and allow-list gates over taskxml.py) |
| `psse_contract_test.py` + `secret_scan_test.py` (files staged first) | 13 passed |
| Acceptance grep for the whole `IgnoreNew` element | prints 1 |
| Own-changes gate (PLAN=03-05) | exit 0 after each of the three commits |

No Postgres was needed or started (tasklist count 0). The full wave-end gate is the orchestrator's, as the plan says, and was not run here.

Red first, actually run: Task 1 failed at collection (no `taskxml`). Task 3: 4 of 12 failed against the Task 1 renderer (refusals, deterministic/token test, minute rule, install command), the ampersand and dry-run tests were already green because the Task 1 renderer escapes and quotes. Task 2's tests pin an artifact that already existed from Task 1, so they were green on first run; the template mutations below are their red evidence.

## Mutation results (plant, see the named test go red, restore; sha256 identical and `git diff --quiet` rc 0 each time)

| # | Fault planted | Red tests |
|---|---------------|-----------|
| 1 | IgnoreNew changed to Parallel | test_template_settings_are_the_researched_ones |
| 2 | PT45M changed to PT0S | test_template_settings_are_the_researched_ones |
| 3 | StartWhenAvailable true | test_template_settings_are_the_researched_ones |
| 4 | a user path in the Description | test_template_holds_only_known_placeholders_no_secret_no_path |
| 5 | XML escaping dropped | test_render_escapes_xml_and_quotes_paths_with_spaces_and_ampersand |
| 6 | double quotes dropped around the config path | the tracer and the ampersand test |
| 7 | a percent sign allowed | test_render_refuses_unsafe_or_unquotable_values |
| 8 | `--allow-placeholder` let through without `--dry-run` | test_render_refuses_unsafe_or_unquotable_values and test_render_script_writes_utf8_and_refuses_overwrite |
| 9 | CRLF normalisation dropped | test_render_leaves_no_placeholder_and_is_deterministic |
| 10 | absolute-path rule dropped | test_render_refuses_unsafe_or_unquotable_values |
| 11 | existence rule dropped | test_render_refuses_unsafe_or_unquotable_values |
| 12 | start boundary check dropped | test_render_refuses_unsafe_or_unquotable_values |
| 13 | URL rule dropped | test_render_refuses_unsafe_or_unquotable_values |
| 14 | the command overwrites without `--force` | test_render_script_writes_utf8_and_refuses_overwrite |
| 15 | the command writes a byte-order mark | test_render_script_writes_utf8_and_refuses_overwrite |
| 16 | the minute rule dropped | test_next_start_boundary_is_the_next_quarter_past |
| 17 | "strictly after now" loosened | test_next_start_boundary_is_the_next_quarter_past |

Mutations 1 to 8 are the plan's list; 9 to 17 are extras. The harness is outside the repository (scratchpad `mutate_0305.py`). The 35 planted variants of the template in test_template_gate_flags_planted_violations each assert a named problem, so the Task 2 gates are also mutation-tested by construction.

## Deviations from Plan

**1. [Process] next_start_boundary was written in Task 1, not Task 3**
- The renderer command needs it for its default start, so the Task 1 version already computed the boundary. Task 3 added only the minute validation; its test was red on the minute-rule case (the datetime call raised a plain ValueError, not TaskXmlError) but green on the boundary arithmetic. Mutations 16 and 17 cover both.

**2. [Rule 2 - Missing safety] extra refusals beyond D-04**
- Control characters other than line breaks, an at-sign pair in a value, a trailing backslash on a quoted file (it would escape the closing quote), a template whose tokens are not exactly the four placeholders, non-text or empty values. All name the argument only and are tested.

**3. [Rule 1 - Robustness] CRLF checkouts**
- Git on this machine warns that LF will become CRLF on the next touch. A CRLF template would have put carriage returns into the filled XML and broken the planted-variant string matches. `render` normalises the template to LF; the tests read the template normalised and assert the CRLF rendering equals the LF one (mutation 9).

**4. [Note] Settings count**
- The plan text says "the twelve entries of D-02"; D-02 and the research template name ten distinct settings (Enabled appears in the trigger and in Settings). The template holds those ten. I did not add AllowStartOnDemand or RunOnlyIfIdle to reach twelve: both are defaults and neither was researched.

**5. [Small additions]** `TaskXmlError.argument` (so the command can name the option), and `--start`/`--minute` as a mutually exclusive pair. Both are tested.

## Authentication gates

None.

## Known Stubs

None.

## Threat Flags

None beyond the plan's register: T-03-20 (placeholders only; secret scan and path checks on the template; URL refusal), T-03-21 and T-03-22 (settings and bans pinned, 35 plants), T-03-23 (escaping and refusals), T-03-24 (absolute existing paths; the writable-folder advice is guide text for plan 03-06).

## Honest scope: UNVERIFIED, handed to plan 03-07 (runbook step 6)

Everything here is text-level plus the launcher's parser. Not proved, and labelled so in the template comments, the module docstrings and the test docstring:

- That Task Scheduler accepts this XML (Microsoft's schema was not run against it) and that `Register-ScheduledTask -Xml` with `Get-Content -Raw -Encoding UTF8` imports it.
- That a Repetition with an Interval and no Duration repeats indefinitely (check NextRunTime after registering).
- That a Command double-quoted because it holds a space works, and that the quoted entry script and config inside Arguments reach the launcher as one token each.
- That a percent sign would be expanded by the scheduler (the renderer refuses it as a precaution).
- That a standard user can register the task for their own account (research A8), with the fallback of registering it from the teammate's own session.
- That WakeToRun wakes the laptop (Modern Standby), that the battery flags are honoured, and that the exit code (including 4 for a held lock) reaches LastTaskResult.
- That `IgnoreNew` behaves as documented; the observed no-overlap guarantee is the run lock of plan 03-01.

Questions carried forward for the guide (plan 03-06): (1) start minute, default 15; (2) StartWhenAvailable false versus one catch-up run after wake; (3) whether the teammate can register without administrator rights. A working directory only the user can write, not Downloads, is guide advice (T-03-24).

## Notes for plans 03-06 and 03-07

- Install command: `python -X utf8 backend/psse_render_task.py --config FILE --work-dir DIR --out FILE [--python EXE] [--entry SCRIPT] [--start ISO | --minute N] [--dry-run [--allow-placeholder]] [--template FILE] [--force]`. Use `--dry-run --allow-placeholder` for the smoke task; a real run never takes `--allow-placeholder`.
- Register with typed cmdlets as in the research (`Register-ScheduledTask -TaskName ... -Xml $xml`, `Get-ScheduledTaskInfo`, `Start-ScheduledTask`, `Unregister-ScheduledTask`) or `schtasks /create /tn NAME /xml FILE /f`; neither was run here.
- The renderer's default interpreter is the one that runs it, so render with the interpreter that matches PSS/E's psspy folder.

## Self-Check: PASSED

- Files found: docs/data-science/ops/psse_hourly_task.xml, backend/psse_job/taskxml.py, backend/psse_render_task.py, backend/tests/psse_task_xml_test.py.
- Commits found as ancestors of HEAD: 5011766, ad252c7, 1af96ad.
- No postgres process left running; no stray directory in the repository (`git status` shows only the two untracked workstream files and config.json that are to stay uncommitted).
