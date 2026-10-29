---
phase: 03-laptop-run-and-handover
plan: 06
subsystem: docs
tags: [runbook, setup-guide, doc-drift, rehearsal, unverified-register, dbx-02, sch-01, sch-02, tst-02, doc-01]

requires:
  - phase: 03-laptop-run-and-handover
    provides: plans 03-01 to 03-05 (launcher, gaps, credcheck, entry script and modes, task XML and renderer)
provides:
  - docs/data-science/decisions/psse_laptop_runbook.md (eleven steps, the UNVERIFIED register of 32 claims, stop rules)
  - docs/data-science/decisions/psse_laptop_setup.md (fourteen sections, twelve questions)
  - backend/tests/psse_rehearsal_test.py (every cmd-tagged runbook command executed on fakes and local Postgres; induced-gap rehearsal)
  - backend/tests/psse_setup_doc_test.py (15 drift and cross-document gates)
affects: [03-07 laptop session (steps 0 to 6), 03-08 live session (steps 7 to 10, final guide edit)]

actuals:
  tokens: 32700
  tasks: 3
  commits: 4
plan_head_before: c28aa1c3465a49a2f5b8fd61cc492c4103943e5f
plan_head_after: 3e2da3a404101e91cfcb06b73518b1333cff5928

tech-stack:
  added: []
  patterns:
    - "command blocks marked by a comment line directly above the fence, tokenised like Windows, executed by the test that reads the document"
    - "claim ids (U01 to U32) after each tag, so a tag, its sentence and its register row are tied by a test"
    - "doc tables compared with code: CONFIG_KEYS, EXIT_CODES, the XML template, requirements.txt"

key-files:
  created:
    - docs/data-science/decisions/psse_laptop_runbook.md
    - docs/data-science/decisions/psse_laptop_setup.md
    - backend/tests/psse_rehearsal_test.py
    - backend/tests/psse_setup_doc_test.py
  modified: []

key-decisions:
  - "D-01 to D-07 of the plan implemented as written; no code file of plans 03-01 to 03-05 changed (no fix-forward was needed)"
  - "The tag format stays `[UNVERIFIED until step N]`; a claim id in parentheses follows it so that each tag can be tied to one register row"
  - "The register has 32 rows, five more than the plan's floor of 27 (see Deviations)"

patterns-established:
  - "Mutation harness outside the repository (scratchpad mutate_0306.py): exact-text replace, named tests, sha256 compared after restore"

requirements-completed: []

duration: not captured at spawn (single session, three tasks)
completed: 2026-10-29
status: complete
---

# Phase 3 Plan 06: Setup guide, runbook, doc-drift gates and rehearsal Summary

**A fourteen-section setup guide and an eleven-step runbook whose tables are equal to `launcher.CONFIG_KEYS`, `launcher.EXIT_CODES`, the Task Scheduler XML and `requirements.txt`, whose every launcher command is executed on the fake psspy and local Postgres, whose every SQL block runs as the writer role, and whose every claim about the laptop carries a tag naming a runbook step and a register row.**

DOC-01 and TST-02 are drafted and Mac-rehearsed here. Neither is closed: DOC-01 closes when someone other than the author follows the guide through step 10 (plans 03-07 and 03-08), and TST-02 when the proof write of step 9 is read back. REQUIREMENTS statuses stay Pending (not edited here).

## Commits

| Commit | Subject |
|--------|---------|
| 11d82c2 | docs(03-06): tracer - the laptop runbook and a rehearsal that runs every documented launcher command on fakes and local Postgres |
| 9386a97 | docs(03-06): the laptop setup guide and drift gates tying its tables and prohibitions to the launcher, the other modes and the XML template |
| 6616228 | test(03-06): cross-document gates for the UNVERIFIED tags, the SQL and command blocks, the steps table and the links, and the induced-gap rehearsal |
| 3e2da3a | docs(03-06): the guide states the gap check's exit 5 on an empty table and its exit 6 when it cannot connect |

`commits: 4` is measured (`git rev-list --count c28aa1c..3e2da3a`); the docs commit of this SUMMARY is not counted. See Deviations for how the base was recorded.

## Accomplishments

- **Runbook** (six `##` sections, eleven `### Step N:` sections): each step has Needs, command blocks, Should show and Stop if. Output lines, exit codes, row counts and flag names come from the built code and the plan 03-01 to 03-05 summaries, and the quoted output was produced by running the modes on the fakes. Step 5 says how the four lines of the throwaway mapping are chosen from PSS/E's own listing (counts only from the probe). Steps 9 and 10 each begin with the human decision of plan 03-08 (decision 1: exactly one proof write; decision 2: the unattended task, with Disable-ScheduledTask then Unregister-ScheduledTask as the stop). The newest-per-slot statement, the per-run counts, the dispatch listing and the clock comparison are `sql` blocks; the completeness check is a link.
- **Guide** (fourteen `##` sections): the 13-key table with required modes, secret flag and default; the exit-code table plus a "look first at" table; the Task Scheduler settings table (13 rows, covering all ten `Settings` entries); the psycopg decision table (3.7: 3.1.20, 3.8 and 3.9: 3.2.13, 3.10 to 3.12: the repository pin, 32-bit: not supported); wheelhouse commands; the package-legitimacy note; file protection with `icacls` and what it does not protect against; troubleshooting (13 symptoms); credential hygiene; uninstall; a hand-over record; twelve questions, each with who answers and the default assumed meanwhile. It says the Phase 2 note's environment-variable sentence is superseded by the configuration file, that libpq's PG* variables are not isolated, that `verify-full` is recommended where a CA certificate exists, and that the 5 second preflight bounds the TCP connect only.
- **Rehearsal** (`psse_rehearsal_test.py`): the tracer extracts every `<!-- cmd: NAME -->` block, tokenises lines the Windows way, substitutes placeholders and runs: `selftest` (six PASS rows, exit 0), `probe` with and without a mapping and `probe_write_check` (no FAIL, no five-digit number, no path), `dry_run_smoke` and `dry_run_real` (counts, `validation: ok`, all four tables empty), `real_run` (exit 0, one run of 1 + 4 + 4 + 10 rows, every completeness check ok), `gaps` (exit 0, `1 runs recorded`), `credcheck` (16 PASS) and `credcheck_write_proof` (18 PASS, tables unchanged), `hold_lock` in a real second process (a concurrent real run exits 4, nothing new written, the holder exits 0), and both renderer commands through a `python -I -B` process (UTF-8 XML without a byte-order mark, Arguments parsed by the launcher's parser). An unknown cmd name fails; each name must also parse to its own shape (a real run never carries `--allow-placeholder`).
- **Induced gap**: the documented `gaps` lines run through `launcher.main` on a seeded history with one missing hour: the plain command exits 0 with one `no_run` line for that hour, the `--fail-on-gaps` command exits 5; with no missing hour both exit 0 and print `no gaps`. A history is accepted only if the database's hour did not roll while reading it.
- **Cross-document gates**: every tag names an existing step and a register claim at the same step, every register row is cited, the guide has at least 12 tags; every `sql` block is a read and runs as `dlr_psse_writer`; the read-back statement is run unchanged on a seeded history (below); every command block parses; the steps table closes SCH-01 on 6, DBX-02 on 8, TST-02 on 9, SCH-02 on 10; every relative link resolves.

## Test results

| Command | Result |
|---------|--------|
| PG command over `psse_setup_doc_test.py` and `psse_rehearsal_test.py` | 17 passed, 0 skipped (15 doc tests, 2 rehearsal tests) |
| PG command, `psse_rehearsal_test.py -k tracer` (Task 1 gate) | 1 passed, 0 skipped |
| `psse_setup_doc_test.py` without Postgres, Task 2 gate | 9 passed, 0 skipped |
| `psse_contract_test.py` + `secret_scan_test.py` (files staged first) | 13 passed |
| `psse_study_doc_test.py`, `psse_schema_doc_test.py`, `psse_task_xml_test.py` (neighbouring gates, informational) | 39 passed |
| Acceptance greps | `grep -c "^### Step "` prints 11; `grep -c '<!-- cmd: '` prints 25 (floor 12); guide tag lines 27 (floor 12); questions heading 1 |
| Own-changes gate (PLAN=03-06) | exit 0 after each commit |
| Postgres processes left running | 0 (`tasklist` count after the last run) |

The full `psse_*_test.py` wave-end gate is the orchestrator's and was not run here.

Red first, actually run: Task 1: the tracer failed with `FileNotFoundError` for the runbook, then passed once it existed. Task 2: all 9 tests failed with `FileNotFoundError` for the guide. Task 3: on the first run one of the seven new tests was red (`test_unverified_tags_cite_existing_runbook_steps`, because the documents write a tag in backticks and the test's pattern did not allow the closing backtick before the claim id; the pattern was corrected, the documents were right). The other six were green on first run, because the documents were written against the same rules; their red evidence is the mutation table below.

## Mutation results (plant, see the named test go red, restore; sha256 equal and `git status` clean for the documents each time)

The plan's list:

| Planted fault | Red test |
|---------------|----------|
| flag renamed in a runbook command (`--write-check` to `--write-chek`) | the rehearsal tracer |
| flag renamed in a runbook command (`--fail-on-gaps` to `--fail-on-gap`) | `test_every_command_block_parses_with_the_real_parser` |
| a key row dropped from the guide's key table | `test_guide_config_key_table_equals_launcher_config_keys` |
| a code changed in the guide's exit table (5 to 9) | `test_guide_exit_code_table_equals_launcher_exit_codes` |
| a value changed in the settings table (`PT45M` to `PT50M`) | `test_guide_xml_settings_table_equals_template_values` |
| a pin changed in the guide (3.1.20 to 3.1.19) | `test_guide_psycopg_matrix_pins` |
| a tag naming step 11 | `test_unverified_tags_cite_existing_runbook_steps` |
| a user-profile path in the guide | `test_docs_hold_no_secret_identifier_or_real_path` |
| a broken sql block (`psse_run` to `psse_runs`) | `test_every_sql_block_runs_on_local_postgres` (and the read-back test) |
| the sslmode sentence deleted | `test_guide_states_prohibitions` |

Extras: a cmd name misspelt (`dry_run_smok`) and a real run given `--dry-run --allow-placeholder` (rehearsal tracer); `setx` advised instead of forbidden, the Phase 2 sentence not called superseded, a question number broken (the three matching tests); a tag without a claim id, and a tag with the wrong step for its claim; the read-back statement ordered by run id ascending, ordered with `outcome` first, and with the `outcome in ('ok', 'fallback')` filter removed (read-back test); the `--fail-on-gaps` line of the runbook changed (induced-gap rehearsal); a Closes cell emptied (steps table test); a broken link; a step heading renamed.

## The read-back seed (research assumption A16)

On local Postgres as the writer role, with `psse_run` rows in three slots, the runbook's newest-per-slot statement is run unchanged. Slot A (10:00): a failed run started latest (10:50), an ok run started at :40 and a fallback run started at :10, so the ok run started later and is the newest complete run. Slot B (09:00): two complete runs with equal `started_at` (09:15), different run ids; the fallback run holds the larger id, so the tie-break is the run id and not the outcome. Slot C (08:00): one failed run only. Result: A's ok run, then B's larger id, newest slot first, no row for C, and the failed runs and the older fallback run of slot A never returned. A16 is therefore shown on local Postgres 18.6 (the live table is a separate matter).

## Deviations from Plan

**1. [Plan addition] Claim ids after each tag, and a register of 32 rows.**
- The plan asks that each distinct claim have a register row whose Tag step column holds the same N, but a sentence cannot otherwise be tied to its row by a test. The tag format stays `[UNVERIFIED until step N]` exactly; a short id in parentheses follows it (`(U05)`), the register's Claim column starts with the same id, and the test checks id, step and that every register row is cited at least once.
- The plan's list gives 28 claims, which are U01 to U29 except U20 (the quoted Command and the UTF-8 import are one row). U20 (IgnoreNew drops a start made while an instance runs, step 6) comes from plan 03-05's summary and is registered apart from U13 (the byte lock); the observed no-overlap guarantee stays the lock. Three more were added because the guide and runbook state them: U30 (a licence is not available to a signed-out or non-interactive session, step 0), U31 (the job's code runs on the laptop's older Python, step 2), U32 (an interactive-token task runs only while its user is signed in, step 6). Total 32.
- A12 is tagged to step 8 (U26, first `writer.connect`) and A7 to step 10 (U27, a day-long observation), as handed over.

**2. [Process] The plan commit ledger (protocol 0c) was not created before the first commit.** `plan_head_before` is `c28aa1c`, the HEAD recorded at the start of the session (confirmed by `git log` before any edit), and `commits: 4` is measured from it. Nothing else depends on the ledger file.

**3. [Process] Two scratch-file shell heredocs.** One appended a line to a scratch script in the scratchpad (outside the repository) and one was a no-op `cat > /dev/null`; both ran without trouble. Every repository file was written with Write or Edit. A `pin.sh` source attempted from the scratchpad folder failed (not a git checkout) and was repeated from the repository root before any write; no write happened in between.

**4. [Test design] Shared helpers live in the rehearsal module.** `psse_setup_doc_test.py` imports `command_blocks`, `launcher_arguments`, `render_arguments`, `SHAPES` and `RENDER_SHAPES` from `psse_rehearsal_test.py`, and the rehearsal imports `RestStandIn` from `psse_credcheck_test.py` and the Windows splitter from `psse_task_xml_test.py`, so the extraction and tokenising exist once.

**5. [Wording] Settings count.** The guide's settings table lists the ten entries of the template's `Settings` plus `Interval`, `LogonType` and `RunLevel` (13 rows), and a test pins that the template's `Settings` has exactly ten children, as plan 03-05 recorded.

No fix-forward was made to any file of plans 03-01 to 03-05; the rehearsal and the drift tests found no defect in them. No Phase 1 or 2 file, the DDL, `backend/config.py`, `supabase/migrations/` or production-pipeline plan was touched (own-changes gate exit 0). No package was installed; no scheduled task was registered or changed; nothing contacted a network service beyond loopback.

## Authentication gates

None.

## Known Stubs

None. The guide's hand-over record rows read `pending` on purpose; plans 03-07 and 03-08 fill them.

## Threat Flags

None beyond the plan's register: T-03-25 (secret scan, user-path, host-shape, URL and hash gates, an allowed-integers gate), T-03-26 (the tag, claim-id and register tests), T-03-27 (the table-to-code tests and the rehearsal), T-03-28 (the prohibitions test, which also scans every command block for `setx`, `service_role` and a placeholder flag on a real run). T-03-SC: no package was installed.

## Honest scope: what is and is not proved

Proved on the Mac: that the documents' tables equal the code, that each documented command parses and, on the fake psspy and local Postgres, prints what the runbook says, that the documented SQL runs as the job's role, and that an induced missing hour gives exit 5 through the documented command. Not proved, and tagged: everything about real PSS/E, the licence, the laptop's Python, Windows Task Scheduler (accepting the XML, registration rights, wake, the exit code reaching `LastTaskResult`, `IgnoreNew`, indefinite repetition), the Windows byte lock on that machine, the live database and pooler, the older psycopg lines running `writer.py`, and clock agreement. Nobody other than the author has read the guide as an installer.

## Self-Check: PASSED

- Files found: docs/data-science/decisions/psse_laptop_runbook.md, docs/data-science/decisions/psse_laptop_setup.md, backend/tests/psse_rehearsal_test.py, backend/tests/psse_setup_doc_test.py.
- Commits found as ancestors of HEAD: 11d82c2, 9386a97, 6616228, 3e2da3a.
- No postgres process left running; `git status` shows only `.planning/config.json` (modified) and the two untracked workstream files, all to stay uncommitted.

## Questions for the user, the teammate and the owner (the guide's twelve, none answered)

1. Teammate: PSS/E version and edition (full, free or university), licence type (local, dongle or network, and whether a VPN is needed), Python interpreter path and bitness, the `psspy` folder, administrator rights.
2. Teammate: can you register a scheduled task for your own account, does wake work (`powercfg /a`), is the laptop plugged in and awake at :15.
3. The user and Power Systems: is the real case the IEEE 39-bus New England system, when do the case and the mapping arrive, and does Power Systems supply a PSS/E saved case (.sav) or a raw file.
4. The owner: does production-pipeline Phase 6 take the migration, when, who sets the `dlr_psse_writer` password and how is the connection string delivered privately, and does the session pooler accept the role in the form `ROLE.PROJECT-REF`.
5. The user: smoke runs are dry-runs only; is one permanent live row set acceptable for the single proof write, may the case file's base name be stored as `case_id` (rename the file first if not), and, once the unattended real task is enabled (a second decision, after the proof write), is it acceptable that each hourly start appends a permanent row set (the writer has no DELETE) until someone disables the task.
6. The teammate and the owner: is a PSS/E licence available to a signed-out or non-interactive session (default: assume not, interactive token only).
7. The user: is a :15 start with no catch-up run after wake acceptable.
8. The user and the owner: may `credcheck --write-proof` run on the live database.
9. Power Systems: the eight open questions of `psse_study_definitions.md` (mapping, rate set, static overwrite, margin transfer, base-case violations, licensed modules, case size and run time, limits) remain open and are answered in that note's own section.
10. The owner: is unattended gap monitoring wanted later (exit code 5 exists for it).
11. The teammate: is BitLocker on, and will antivirus or application control block a new script folder.
12. The user: where should the repository copy live on the laptop, and who owns the install.
