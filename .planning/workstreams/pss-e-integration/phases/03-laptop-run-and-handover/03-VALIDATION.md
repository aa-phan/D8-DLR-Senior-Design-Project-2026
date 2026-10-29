---
phase: "3"
slug: "laptop-run-and-handover"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-28"
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from the `## Validation Architecture` section of `03-RESEARCH.md`; the planner filled the per-task map on 2026-10-28.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3, plain asserts, no classes (repo house style) |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| **Quick run command** | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/psse_contract_test.py backend/tests/psse_task_xml_test.py backend/tests/psse_entry_test.py backend/tests/psse_laptop_modes_test.py backend/tests/psse_setup_doc_test.py` (no database for most tests; the Postgres-backed tests in those files skip without the PG prefix; list only the files that exist at the current plan) |
| **Full suite command** | `PYTHONDONTWRITEBYTECODE=1 PATH="/c/Users/tejas/Downloads/postgresql-18.6-5-windows-x64-binaries/pgsql/bin:$PATH" PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_*_test.py backend/tests/secret_scan_test.py` (Postgres 18.6 `bin` on PATH for the command only; a skipped database proof is a failure) |
| **Estimated runtime** | quick: about 30 seconds; full: about 4 minutes (Phase 2 baseline 521 passed in about 2.5 minutes, plus six Postgres-backed modules and several real-subprocess tests) |

"Mac-proven" in these plans means proven on the development machine with the fake `psspy`, a loopback stand-in and a local Postgres. That machine is Windows 11 with Python 3.12, so the Windows byte lock (`msvcrt`) is exercised for real there (a second handle, a second process and a killed holder were probed during planning), and the `fcntl` branch is exercised through a fake module; on a Mac the roles of the two branches swap. It is still not the laptop: its Python (3.7 to 3.11), its filesystem and its Task Scheduler are UNVERIFIED until runbook step 6.

---

## Sampling Rate

- **After every task commit:** Run the task's own command from the map below (the new test files; Postgres where the map says PG).
- **After every plan wave:** Run the full suite command; any skip counts as a failure.
- **Before `/gsd-verify-work`:** Full suite green, plus the mutation checks below.
- **Max feedback latency:** 240 seconds.

---

## Per-Task Verification Map

Task IDs are `<plan>-T<n>` from the PLAN files (filled by the planner 2026-10-28). Every command is `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs <args>` from the repository root; `PG` abbreviates the prefix `PYTHONDONTWRITEBYTECODE=1 PATH="/c/Users/tejas/Downloads/postgresql-18.6-5-windows-x64-binaries/pgsql/bin:$PATH" PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1`. SC1 to SC4 are the ROADMAP Phase 3 success criteria. Plans 03-07 and 03-08 are human checkpoint plans: their tasks have no automated command except the record checks and the full gate, and are listed under Manual-Only Verifications as well.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-T1 | 03-01 | 1 | SCH-01 / SC3 (lock), TST-02 / SC1 (Mac part) | T-03-01, T-03-03, T-03-04 | A config file alone drives one complete fallback run into local Postgres; the environment is not configuration; a real second process is refused while the lock is held; `argparse`, `fcntl`, `msvcrt` added to the Phase 1 allow-list on purpose | integration (local PG, real 2nd process) | PG `backend/tests/psse_lock_test.py backend/tests/psse_launcher_test.py -k tracer` and `backend/tests/psse_contract_test.py` | ❌ W0 | ⬜ pending |
| 03-01-T2 | 03-01 | 1 | SCH-01 / SC3, TST-02 / SC1 | T-03-01, T-03-02, T-03-03, T-03-06, T-03-08 | Exit 2 for every config problem with no value echoed, sslmode rule, exit 3 before PSS/E starts, exit 4 with nothing recorded, PsseUnavailable is one recorded `load_case` failure with no path, exit 7, no secret in output or log, lock held from before PSS/E to after the write | integration (local PG) + unit | PG `backend/tests/psse_lock_test.py backend/tests/psse_launcher_test.py` (at least 26 passed) | ❌ W0 | ⬜ pending |
| 03-01-T3 | 03-01 | 1 | TST-02 / SC1 | T-03-05, T-03-07 | Dry-run equals a real run up to the connect and never connects; `--allow-placeholder` only with `--dry-run`; search folders appended, never prepended | integration (local PG) + unit | PG `backend/tests/psse_lock_test.py backend/tests/psse_launcher_test.py` (at least 31 passed) and the full gate | ❌ W0 | ⬜ pending |
| 03-02-T1 | 03-02 | 1 | SCH-02 / SC3 | T-03-09 | The gap statement lists the missing hours of a seeded history (no_run, failed_only; duplicates, failed-plus-complete and the current hour are not gaps) | integration (local PG) | PG `backend/tests/psse_gaps_pg_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 03-02-T2 | 03-02 | 1 | SCH-02 / SC3 | T-03-09 | The SQL equals an independent pure-Python reference over 30 seeded random histories; empty table, current-hour-only, single slot, since and until, exit codes | integration (local PG) | PG `backend/tests/psse_gaps_pg_test.py` (at least 7 passed) | ❌ W0 | ⬜ pending |
| 03-02-T3 | 03-02 | 1 | SCH-02 / SC3 | T-03-10, T-03-11, T-03-12 | One SELECT statement on a read-only session; same rows as the writer role and the superuser; no secret or identifier in the output; connection failure redacted | integration (local PG) | PG `backend/tests/psse_gaps_pg_test.py` (at least 13 passed) and the full gate | ❌ W0 | ⬜ pending |
| 03-03-T1 | 03-03 | 1 | DBX-02 / SC2 | T-03-13, T-03-18 | Role leg: 13 checks pass as `dlr_psse_writer` (catalog derived, seven where-false statements refused with 42501) and the superuser fails the privilege checks; nothing changed | integration (local PG) | PG `backend/tests/psse_credcheck_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 03-03-T2 | 03-03 | 1 | DBX-02 / SC2 | T-03-13, T-03-14, T-03-17, T-03-18 | Eight planted privileges each a named FAIL with unrelated checks still PASS; REST leg refuses PATCH and DELETE with 401 or 403, fails on 2xx or inconclusive, sends nothing after a failed read or with a secret key | integration (local PG + loopback stand-in) | PG `backend/tests/psse_credcheck_test.py` (at least 15 passed) | ❌ W0 | ⬜ pending |
| 03-03-T3 | 03-03 | 1 | DBX-02 / SC2 | T-03-15, T-03-16, T-03-19 | Opt-in write proof inserts a complete synthetic run in a forced rollback and nothing survives; off by default; run exit codes; no secret in output | integration (local PG) | PG `backend/tests/psse_credcheck_test.py` (at least 22 passed) and the full gate | ❌ W0 | ⬜ pending |
| 03-04-T1 | 03-04 | 2 | TST-02 / SC1 (Mac part) | T-03-42 | The entry script's selftest finds a stub psspy in the configured folder under `-I`, starts it, prints the version and five launch rows; psspy imported only inside `load_psspy` | subprocess + unit (fake) | PG `backend/tests/psse_laptop_modes_test.py backend/tests/psse_entry_test.py` (at least 5 passed) | ❌ W0 | ⬜ pending |
| 03-04-T2 | 03-04 | 2 | TST-02 / SC1, SCH-01 / SC3 (tool) | T-03-42, T-03-43, T-03-44, T-03-45 | selftest failures exit 6 path-free; probe default report identifier-free, write check never saves; hold-lock capped and held; entry failure modes; an overlapping start exits 4 through two real entry processes | subprocess + unit (fake) | PG `backend/tests/psse_laptop_modes_test.py backend/tests/psse_entry_test.py` (at least 15 passed) | ❌ W0 | ⬜ pending |
| 03-04-T3 | 03-04 | 2 | SCH-02 / SC3, DBX-02 / SC2 (reachability) | T-03-42 | gaps and credcheck reach the real modules through the launcher with parsed arguments; since and until need an offset; required keys per mode; no lock for them | integration (local PG) | PG `backend/tests/psse_laptop_modes_test.py backend/tests/psse_entry_test.py` (at least 21 passed) and the full gate | ❌ W0 | ⬜ pending |
| 03-05-T1 | 03-05 | 2 | SCH-01 / SC3 (Mac part) | T-03-20, T-03-23 | The template renders from tmp paths to well-formed XML whose arguments the launcher's own parser accepts | unit | `backend/tests/psse_task_xml_test.py -k tracer` and `backend/tests/psse_contract_test.py` | ❌ W0 | ⬜ pending |
| 03-05-T2 | 03-05 | 2 | SCH-01 / SC3 | T-03-20, T-03-21, T-03-22 | Every setting pinned (IgnoreNew, PT45M, battery flags, no catch-up, wake, interactive token, least privilege, hourly repetition without duration) and each planted violation named; clean under the secret scan; UTF-8 without BOM | unit | `backend/tests/psse_task_xml_test.py` (at least 6 passed) | ❌ W0 | ⬜ pending |
| 03-05-T3 | 03-05 | 2 | SCH-01 / SC3 | T-03-23, T-03-24 | The renderer escapes ampersands, quotes paths with spaces, refuses relative, missing, unquotable and URL-shaped values and `--allow-placeholder` without `--dry-run`; the install command writes UTF-8 and refuses to overwrite | unit + subprocess | `backend/tests/psse_task_xml_test.py` (at least 12 passed) and the full gate | ❌ W0 | ⬜ pending |
| 03-06-T1 | 03-06 | 3 | TST-02 / SC1, DOC-01 / SC4 | T-03-25, T-03-27 | Every runbook launcher command is executed on the fake psspy, the loopback stand-in and local Postgres (selftest, probe, dry-runs, real run, gaps, credcheck, hold-lock, render) | integration (local PG, subprocess) | PG `backend/tests/psse_rehearsal_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 03-06-T2 | 03-06 | 3 | DOC-01 / SC4 | T-03-25, T-03-26, T-03-27, T-03-28 | The guide's 14 sections; key, exit-code, XML-setting and psycopg tables equal the code, the template and `requirements.txt`; prohibitions stated; no secret, host, user path or stray integer; twelve questions | doc-drift | `backend/tests/psse_setup_doc_test.py` (at least 9 passed) and `backend/tests/psse_study_doc_test.py backend/tests/psse_schema_doc_test.py` | ❌ W0 | ⬜ pending |
| 03-06-T3 | 03-06 | 3 | DOC-01 / SC4, TST-02 / SC1, SCH-02 / SC3 | T-03-26, T-03-27 | UNVERIFIED tags name existing runbook steps and have register rows; every sql block runs on local Postgres; every command block parses with the real parser; the steps table closes each requirement; links resolve; an induced missing hour exits 5 through the documented command | doc-drift + integration (local PG) | PG `backend/tests/psse_setup_doc_test.py backend/tests/psse_rehearsal_test.py` (at least 16 passed) and the full gate | ❌ W0 | ⬜ pending |
| 03-07-T1 | 03-07 | 4 | DOC-01 / SC4 | T-03-30 | Ask-list answered at the laptop; no host, path or user name | manual (checkpoint) | none (resume signal) | n/a | ⬜ pending |
| 03-07-T2 | 03-07 | 4 | DOC-01 / SC4 | T-03-29, T-03-30 | Record file has its six sections and no drive path or connection string | record check | `.venv/Scripts/python.exe -I -c ...` over `03-07-LAPTOP-RECORD.md` (the command in the plan) | ❌ W0 | ⬜ pending |
| 03-07-T3 | 03-07 | 4 | TST-02 / SC1 | T-03-SC | Five PyPI packages and wheel hashes verified by a human before any install | manual (blocking-human) | none (resume signal) | n/a | ⬜ pending |
| 03-07-T4 | 03-07 | 4 | TST-02 / SC1 | T-03-30, T-03-31, T-03-32 | psycopg from the wheelhouse, ACL on the config file, selftest, probe read only and with the write check on a copy, dry-run on an example case with a throwaway mapping outside git | manual (laptop) | none (resume signal; evidence recorded by 03-07-T6) | n/a | ⬜ pending |
| 03-07-T5 | 03-07 | 4 | SCH-01 / SC3 | T-03-33, T-03-34 | Three hourly scheduled dry-runs at :15 with LastTaskResult 0, a held-lock start exits 4, the smoke task unregistered | manual (laptop, about 3 hours) | none (resume signal; evidence recorded by 03-07-T6) | n/a | ⬜ pending |
| 03-07-T6 | 03-07 | 4 | SCH-01, TST-02, DOC-01 | T-03-30 | Record complete without identifiers; only evidence-backed tags cleared; guide and gates green | record check + full gate | the record check of the plan and the full gate | ❌ W0 | ⬜ pending |
| 03-08-T1 | 03-08 | 5 | DBX-02 / SC2 | T-03-35, T-03-38 | Live credential proof: every role-leg and REST-leg row PASS, REST leg not skipped | manual (live, Phase 6) | none (resume signal) | n/a | ⬜ pending |
| 03-08-T2 | 03-08 | 5 | TST-02 / SC1 | T-03-37, T-03-40 | Real case and mapping: probe read only (mapping row clean), dry-run under budget, engineer review and hand-check | manual (real inputs) | none (resume signal) | n/a | ⬜ pending |
| 03-08-T3 | 03-08 | 5 | TST-02 / SC1 | T-03-36 | Explicit blocking-human decision to allow exactly one real write | decision (blocking-human) | none (resume signal) | n/a | ⬜ pending |
| 03-08-T4 | 03-08 | 5 | TST-02 / SC1 | T-03-36, T-03-40 | The one real write read back: exit 0, counts equal the dry-run's, completeness checks all ok, newest set per the reading rules | manual (live, one-way) | none (resume signal) | n/a | ⬜ pending |
| 03-08-T5 | 03-08 | 5 | SCH-02 / SC3, SCH-01 / SC3 | T-03-39, T-03-41 | Real task registered and left on; next-day gap check; one induced gap shows as no_run; other gaps explained | manual (live, next day) | none (resume signal) | n/a | ⬜ pending |
| 03-08-T6 | 03-08 | 5 | DOC-01 / SC4 | T-03-37 | Final guide and runbook; handover record without identifiers or numeric results; gates green | record check + full gate | the record check of the plan and the full gate | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Mutation checks at the phase gate (each plant must turn a test red; the plans list the full set, this is the headline list): second process not refused (lock always acquired); lock released before the write; preflight skipped; configuration problem echoing a value; redacting filter dropped; environment read as configuration; path scrub dropped; dry-run connecting; search folder prepended; sslmode rule removed; placeholder on a real run; gap SQL including the current hour; failed-only treated as complete; duplicate slot counted; series started at a fixed date; gap check not read-only; any exception counted as a credential refusal; write proof without the forced rollback; PATCH sent before the ratings read; psspy imported at module level; probe printing identifiers by default; `Parallel` instead of `IgnoreNew`; `PT0S`; `StartWhenAvailable` true; unescaped ampersand; a flag renamed in a runbook command; a table value changed in the guide; a tag naming a missing step.

Catching tests (planned): lock `test_exit4_second_instance_skipped_writes_nothing` and `test_tracer_lock_second_process_refused_then_acquires_after_release` (03-01); lock held `test_exit4_lock_held_during_start_and_write` (03-01); preflight `test_exit3_unreachable_database_never_starts_psspy` (03-01); value echo `test_exit2_malformed_lines_name_no_value` (03-01); filter `test_hygiene_secrets_never_reach_output_or_log` (03-01); environment `test_tracer_environment_is_not_configuration` (03-01); path scrub `test_failure_psse_unavailable_recorded_as_load_case` (03-01); dry-run connect `test_dry_run_never_connects_and_prints_counts_only` (03-01); search order `test_paths_dirs_appended_never_prepended` (03-01); sslmode `test_exit2_sslmode_rule` (03-01); placeholder `test_exit2_allow_placeholder_needs_dry_run` (03-01); current hour and failed-only and duplicates `test_gap_sql_matches_independent_reference_over_random_histories`, `test_gap_only_current_hour_has_no_gaps`, `test_gap_single_closed_slot_complete_and_failed_only`, `test_gap_duplicates_and_failed_plus_complete_are_not_gaps` (03-02); read-only `test_gap_safe_session_is_read_only` (03-02); refusal rule `test_fault_*` and the superuser tracer (03-03); forced rollback `test_write_proof_inserts_a_complete_run_and_nothing_survives` (03-03); PATCH ordering `test_rest_read_failure_skips_the_write_attempts` and `test_rest_secret_key_refused_and_nothing_sent` (03-03); module-level psspy import `test_entry_imports_psspy_only_in_load_psspy` (03-04); probe identifiers `test_probe_mode_hides_identifiers_by_default` (03-04); template settings `test_template_settings_are_the_researched_ones` and `test_template_gate_flags_planted_violations` (03-05); escaping `test_render_escapes_xml_and_quotes_paths_with_spaces_and_ampersand` (03-05); runbook flag `test_tracer_rehearsal_runs_the_runbook_commands_against_fakes_and_local_postgres` and `test_every_command_block_parses_with_the_real_parser` (03-06); table drift `test_guide_*_equals_*` (03-06); tag steps `test_unverified_tags_cite_existing_runbook_steps` (03-06).

Own-changes gates: every Mac plan carries a gate over its staged files and its own commits after the Phase 3 research commit `57209f1` (messages carrying "(03-0N)"), so uncommitted work by other sessions, for example production-pipeline Phase 6, cannot fail it. The protected set is the Phase 1 and Phase 2 modules and test helpers, the pinned spec and DDL, `backend/config.py`, `supabase/migrations/`, the production-pipeline plans and the Phase 2 study-definitions note; `backend/tests/psse_contract_test.py` is protected except in plan 03-01, which changes it only by the three allow-list names.

---

## Wave 0 Requirements

- [ ] Each test file is created by the tracer task of its plan: `psse_lock_test.py` and `psse_launcher_test.py` (03-01-T1), `psse_gaps_pg_test.py` (03-02-T1), `psse_credcheck_test.py` (03-03-T1), `psse_entry_test.py` and `psse_laptop_modes_test.py` with the helper `psse_fake_launch.py` (03-04-T1), `psse_task_xml_test.py` (03-05-T1), `psse_rehearsal_test.py` (03-06-T1), `psse_setup_doc_test.py` (03-06-T2)
- [ ] Phase 1 files change only by the allow-list edit of 03-01-T1: `argparse`, `fcntl` and `msvcrt` in `psse_contract_test.py`'s `_STDLIB_ALLOWED`, each with a comment and the reason in the commit. No other allow-list change is planned (`inspect`, `socket`, `subprocess`, `time`, `os`, `sys`, `re`, `datetime`, `json`, `hashlib`, `logging` and `urllib` are already allowed)
- [ ] No Phase 2 file changes: the fake psspy is extended by the subclass in `psse_fake_launch.py`, the launch signatures are checked by launcher code instead of editing `probe.py`, and the study-definitions note's planned environment names are checked read only
- [ ] Reference files: `docs/data-science/schema/psse_run_gaps.sql` (03-02-T1), `docs/data-science/ops/psse_hourly_task.xml` (03-05-T1), `docs/data-science/decisions/psse_laptop_runbook.md` (03-06-T1), `docs/data-science/decisions/psse_laptop_setup.md` (03-06-T2); no file under `supabase/migrations/`
- [ ] No framework install needed (pytest, psycopg and Postgres already present); no package is installed on the Mac. The psycopg wheelhouse is installed on the laptop only, behind a blocking-human legitimacy checkpoint (03-07-T3)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real `psspy` starts, matches the adapter's signatures (`branch_chng_3` and the combined `scal_2` are UNVERIFIED), and the study runs in dry-run on a PSS/E example case | TST-02 | PSS/E and its licence exist only on the teammate's laptop | Runbook steps 2 to 5 through plan 03-07 task 4; `selftest`, `probe` (read only, then the write check on a copy), `run --dry-run --allow-placeholder`; a FAIL stops the session and goes to a gap-closure plan |
| Windows Task Scheduler runs the job hourly at :15 with no overlap, accepts the XML, passes the exit code, lets a standard user register | SCH-01 | The real scheduler, the laptop's rights and the passage of three hours | Runbook step 6 through plan 03-07 task 5, including the `hold-lock` overlap (exit 4) |
| The job's real credential reads ratings and writes the result tables, and cannot change `city_rating` | DBX-02 | Needs production-pipeline Phase 6 applied, the owner's role password and the live key | Runbook step 8 through plan 03-08 task 1: `credcheck` with both legs |
| One real end-to-end run on Power Systems' case written and read back | TST-02 | Needs Phase 6, the real case and mapping, and an explicit human decision (the row set is permanent) | Runbook steps 7 and 9 through plan 03-08 tasks 2 to 4 |
| An hour with no run is visible as a gap on the live table, including one induced gap | SCH-02 | Needs the unattended task running for a day on the real laptop | Runbook step 10 through plan 03-08 task 5: `gaps`, two hours of disabled task, a next-day check |
| Someone other than the author follows the guide to a running hourly job | DOC-01 | A human follows it | Plans 03-07 and 03-08; the final guide edit in 03-08 task 6 |
| Units, N-1 scope, rate set and transfer sink make engineering sense on the real network | TST-02, (Phase 2 human items) | Power Systems' judgement | Plan 03-08 task 2: engineer review of the study-definitions note, its eight questions, and the hand-check of one rating and one percent-of-rating value |

---

## Requirement Coverage (explicit)

Statuses in REQUIREMENTS.md stay Pending until the matching human step passes; the orchestrator marks them after each plan's SUMMARY states which criteria are met.

| Requirement | ROADMAP criterion | Mac-proven by (plans 03-01 to 03-06) | Laptop or live proof by (plans 03-07 and 03-08) | After the Mac plans |
|-------------|-------------------|--------------------------------------|--------------------------------------------------|---------------------|
| DBX-02 | SC2 | 03-03 (role leg on local Postgres with planted faults, REST leg on a loopback stand-in, rolled-back write proof), 03-04 (reachable through the launcher) | 03-08 task 1 (live credential proof; the REST leg may not be skipped) | Pending |
| TST-02 | SC1 | 03-01 (config to local Postgres through the fake psspy, dry-run equal to a real run), 03-04 (selftest, probe, entry script), 03-06 (runbook rehearsed command by command) | 03-07 task 4 (real selftest, probe and dry-run on an example case), 03-08 tasks 2 to 4 (real case review, the one real write, read-back) | Pending |
| SCH-01 | SC3 | 03-01 (lock with a real second process), 03-04 (hold-lock and an overlapping start exiting 4 through two real entry processes), 03-05 (XML template with `IgnoreNew` and a bounded run, renderer) | 03-07 task 5 (closes: three hourly runs at :15, a held-lock start exits 4), 03-08 task 5 (confirmed on the real task) | Pending |
| SCH-02 | SC3 | 03-02 (SQL equal to an independent oracle, read-only wrapper, exit codes), 03-04 and 03-06 (reachable and documented through the launcher) | 03-08 task 5 (closes: next-day gap check and one induced gap) | Pending |
| DOC-01 | SC4 | 03-06 (guide and runbook equal to the code, rehearsed, tagged, questions carried) | 03-07 (steps 0 to 6 followed), 03-08 task 6 (closes: final guide edit, steps 7 to 10 followed) | Pending |

---

## Source Coverage Audit

Every item of the four source types is covered by a plan, deferred by the roadmap, or recorded as a question. No CONTEXT.md exists; the "context" rows are the locked constraints in the research's `<user_constraints>` and the spawn prompt's facts.

| Source | Item | Covered by |
|--------|------|------------|
| GOAL | The hourly job runs on the licensed laptop against the real case | 03-01, 03-04, 03-05 (Mac); 03-07 (example case), 03-08 (real case) |
| GOAL | Results can be read back from the database | 03-02 (gap statement), 03-06 (read-back statements, tested on local Postgres), 03-08 task 4 |
| GOAL | Someone else can install it | 03-06 (guide), 03-07 and 03-08 (followed, final edit) |
| REQ | DBX-02, TST-02, SCH-01, SCH-02, DOC-01 | See Requirement Coverage |
| RESEARCH | F1 two credentials | 03-03 (role leg and REST leg) |
| RESEARCH | F2 Python and driver matrix; wheelhouse; sha256 | 03-06 (guide table tested against `requirements.txt`), 03-07 tasks 2 to 4 |
| RESEARCH | F3 one fresh process per run, OS-released lock | 03-01 (lock), 03-04 (entry script, one process) |
| RESEARCH | F4 dry-run for smoke runs | 03-01 task 3, 03-07, runbook steps 5 and 6 |
| RESEARCH | F5 Task Scheduler defaults corrected | 03-05 |
| RESEARCH | Patterns 1 to 6 (launcher, config, dry-run, lock, psspy bootstrap, XML) | 03-01 (1, 2, 3, 4), 03-04 (5), 03-05 (6) |
| RESEARCH | Pitfalls 1 and 2 (licence hang, licence release) | 03-05 (time limit), 03-01 and 03-04 (one process), 03-06 (troubleshooting), 03-07 and 03-08 (observed) |
| RESEARCH | Pitfall 3 (non-administrator) | 03-05 (interactive token), 03-06 (guide), 03-07 task 5 (registration) |
| RESEARCH | Pitfalls 4 and 5 (sleep, catch-up) | 03-05 (WakeToRun, StartWhenAvailable false), 03-06 (guide), question 7 |
| RESEARCH | Pitfalls 6 and 7 (clock, 90-minute rule) | 03-02 (UTC statement, documented skew), 03-05 (:15 start), 03-06 (clock check statement) |
| RESEARCH | Pitfalls 8 and 9 (encoding, XML import) | 03-01 (utf-8-sig config), 03-04 (stdout UTF-8), 03-05 (`-X utf8`, UTF-8 without BOM, renderer) |
| RESEARCH | Pitfalls 10 and 11 (pythonw, antivirus) | 03-04 (None stream guard), 03-06 (guide, troubleshooting), question 11 |
| RESEARCH | Pitfall 12 (network) | 03-01 (TCP preflight, exit 3), 03-06 (guide) |
| RESEARCH | Pitfall 13 (REST proof cannot change data) | 03-03 |
| RESEARCH | Package legitimacy gate (five SUS packages) | 03-07 task 3 (`gate="blocking-human"`), `T-03-SC` in every plan |
| RESEARCH | Gap statement, credential proof, runbook, guide contents, smoke case choices | 03-02 (gap statement), 03-03 (credential proof), 03-06 (runbook, guide and smoke case choices) and 03-07 (the example case) |
| RESEARCH | Security domain (V2, V4, V5, V6, V7, V14) | 03-01 (sslmode, redaction, config), 03-03 (role proof), 03-05 (task args carry no secret), threat models in every plan |
| RESEARCH | Open questions 1 to 6 | The guide's questions 1 to 6 (03-06); answered in 03-07 and 03-08 or left open with who answers |
| RESEARCH | Assumptions A1 to A18 | The runbook's UNVERIFIED register (03-06), cleared only by evidence in 03-07 and 03-08; A13, A15 and A16 are proved or corrected on local Postgres in 03-02 and 03-03 |
| CONTEXT | Public repository; no real case, mapping, credential or connection string in git | Hard constraint C-4 or C-3 in every plan, secret-scan tests, identifier gates in 03-06, record checks in 03-07 and 03-08 |
| CONTEXT | Credential is the scoped `dlr_psse_writer` role only; no migration written | 03-03, 03-08 task 1; no plan touches `supabase/migrations/` (own-changes gates) |
| CONTEXT | Smoke runs are dry-run; the live write is exactly one behind an explicit human decision | 03-01 D-09, 03-07 (every run a dry-run), 03-08 tasks 3 and 4 (`checkpoint:decision` with `gate="blocking-human"`, one-way rating) |
| CONTEXT | Requirement statuses stay Pending until the matching human step passes | The Requirement Coverage table; every SUMMARY states criteria met; executors do not edit REQUIREMENTS.md |
| CONTEXT | Plans 03-01 to 03-06 verifiable without the laptop, case, mapping or Phase 6; everything about real psspy, Task Scheduler and PSS/E labelled UNVERIFIED | Every Mac plan has an honest-scope paragraph; the tag format and register of 03-06 |
| CONTEXT | Tracer-first, `python -I` for untrusted data, PG prefix, mutation checks, threat model, trailer, git rules | Each plan's first task is a tracer (human plans excepted), each plan has a mutation list, a `<threat_model>`, the Sonnet 5.5 trailer and the git rules of C-5 or C-4 |
| CONTEXT | Phase 1 and Phase 2 code frozen except named allow-list lines | Own-changes gates; plan 03-01 changes only the three allow-list names |
| Excluded | Always-on host, dashboard views (F7), a standalone migration, choosing the grid case or mapping, PSS/E ACCC and PV/QV engines | REQUIREMENTS "Future Requirements" and "Out of Scope"; not planned |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies (the human tasks of 03-07 and 03-08 are checkpoints with record checks)
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify, except the human checkpoint runs of plan 03-07 (tasks 3 to 5) and plan 03-08 (tasks 1 to 5), which cannot be automated and are closed by the record checks and the full gate of the automatic task that follows them
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 240s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
