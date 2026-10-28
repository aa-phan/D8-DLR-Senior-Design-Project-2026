---
phase: 02-study-on-power-systems-case
plan: 07
subsystem: psse-job-probe-and-study-definitions
tags: [pss-e, probe, drift-guard, study-definitions, honest-scope, open-questions, stdlib, python37]
requires:
  - phase: 01
    provides: "run_record.case_label and file_sha256, units.circuit_mva, constants.CITIES, FAILED_STAGES, the Phase 1 import allow-list in psse_contract_test.py"
  - phase: 02
    provides: "plan 02-01 mapping and settings; 02-02 psse_api.SURFACE, PsseApi and the fake psspy; 02-03 study.check_mapping; 02-04 to 02-06 the N-1 screen, the margin, dispatch and prepare_run"
provides:
  - "psse_job.probe: ProbeRow, check_signatures, run_probe, format_report, probe_ok (the laptop drift guard for Phase 3)"
  - "docs/data-science/decisions/psse_study_definitions.md: every study definition, the honest scope, Phase 3 confirmations, assumptions A1 to A18, representability notes and the eight questions"
  - "backend/tests/psse_probe_test.py (11 tests) and backend/tests/psse_study_doc_test.py (7 tests)"
affects: [phase-03]
tech-stack:
  added: []
  patterns:
    - "probe: each check in its own try block, a failure is a FAIL row and never an exception, details carry no identifiers unless show_identifiers is True"
    - "doc drift test: the note's settings table, worked numbers, stage table and headings are compared with the code"
key-files:
  created:
    - backend/psse_job/probe.py
    - backend/tests/psse_probe_test.py
    - docs/data-science/decisions/psse_study_definitions.md
    - backend/tests/psse_study_doc_test.py
  modified:
    - backend/tests/psse_contract_test.py
key-decisions:
  - "The probe reaches the case only through PsseApi(protected_path=case_path), never saves, and undoes its opt-in writes by loading the case from disk again; a write check reloads in a finally block so an error mid-check still leaves the working case as found"
  - "A failing adapter call shows as its function name and ierr (PsseCallError.function and .ierr, which hold no argument or path), never as exception text, unless show_identifiers is True"
  - "The note states every default as an assumption with the question that would change it; no default was resolved"
requirements-completed: [IN-03, STU-03, TST-01]
duration: not timed
completed: 2026-10-28
status: complete
commits: 4
plan_head_before: a1e9470cd14d9227eef42121adac1eac0948a48e
plan_head_after: 15812ed04835ea37ada90b4b4f87f24fb3a16a1b
actuals:
  tokens: 14900
  tasks: 3
  commits: 4
---

# Phase 2 Plan 07: Laptop probe and study-definitions note Summary

**`probe.run_probe(psspy, case_path, mapping=None, write_check=False, show_identifiers=False)` compares all 19 `SURFACE` rows with the real `psspy` and exercises the adapter on a case without ever saving it, and one note, `psse_study_definitions.md`, states every definition the study implements, what the fake does not prove, the assumptions behind each default and eight questions for the user and Power Systems, with a drift test keeping its settings table and worked numbers equal to the code.**

## Accomplishments
- `check_signatures`: one `signature:<name>` row per `SURFACE` function. A missing function is FAIL "missing"; a signature `inspect` cannot read is SKIP (assumption A6), never PASS; a missing parameter name is FAIL naming it; extra parameters are counted.
- `run_probe` rows after the signatures: version, load_case, branch_table, bus_table, column_alignment (bulk RATEA against single-branch `brndat`, first three in-service lines), circuit_id_padding (one raw `abrnchar` read), option_strings (current and mva percent items), load_flow, and with a mapping the mapping check (problem count and each city's base kV). With `write_check` also rating_write (RATEA moved by 1 MVA on the first mapped circuit, read back, then the case is loaded from disk again and the original value confirmed) and scale_load (subsystem 9 and a 1 MW `scal_2`, then a reload). `format_report` ends with `<n> PASS, <m> FAIL, <k> SKIP`; `probe_ok` is true when no row is FAIL.
- Never raises for a probe failure (a module whose every function raises, `object()` and `None` all return rows). The default report holds no bus number, circuit id, case path, file name or exception text.
- The note has the 14 required sections in order: conversion with the formula and the four worked values at 345 kV (2181.1, 1792.7, 2240.8, 788.8), convergence, N-1 scope and limits (not to be called a full N-1 study until Power Systems agrees), the margin definition with the four `bounded_by` values, `transfer.max_mw` as a starting cap that is never a limit and the 80 extra steps, lower-bound semantics, the `pv_curve` label (not a PSS/E PV-curve analysis), dispatched capacity, the seven study failure stages, the 22-row settings table, private inputs, honest scope, the Phase 3 confirmations, assumptions A1 to A18 and the three representability notes (no DDL change).
- The hand-off items from plan 02-06 are in the note: the launcher call, the two different `clock` arguments, the gap between hashing and loading the case, the stale `solved=` number in a failed-fnsl message, the golden file pinning function order and keyword names only, and the `bounded_by` mutation that no test can see.

## Task Commits
1. Allow-list step (the one Phase 1 change): `e5482ab` test(02-07): allow inspect in the Phase 1 import allow-list
2. Task 1 (tracer): `e9b0fbe` feat(02-07): tracer - the laptop probe against the fake psspy passes every check and leaves the case untouched
3. Task 2: `b470427` test(02-07): the probe catches each kind of drift and keeps identifiers out of its default report
4. Task 3: `15812ed` docs(02-07): study definitions note with honest scope, assumptions and the open questions, guarded by a doc drift test

## Verification
- `psse_probe_test.py`: 11 passed (tracer, 7 `test_detects_`, 3 `test_report_`); `-k "detects or report"` over probe, contract and api tests: 10 passed. `psse_study_doc_test.py`: 7 passed. With the contract, API, schema-doc and secret-scan tests: all green.
- Full phase gate (local Postgres 18.6, `PSSE_REQUIRE_PG=1`, `DLR_TEST_PG_AUTOSTART=1`): `backend/tests/psse_*_test.py` and `secret_scan_test.py`: 521 passed, no skip; no Postgres process left running.
- Mutation checks, each restored byte for byte (`git diff` empty): probe saves the case after the write check, tracer red (`test_tracer_probe_against_fake_all_pass`); a missing parameter treated as PASS, `test_detects_renamed_parameter` red; branch key included in the default mapping detail, `test_detects_mapping_problems` and `test_report_hides_identifiers_by_default` red; `contingency_hops` default changed to 3 in `settings.py` without the note, `test_doc_configuration_table_lists_every_setting_with_its_default` red.
- Own-changes gate (no touch of `backend/config.py`, `supabase/migrations`, production-pipeline plans or the pinned schema files) passes. `grep -c '"inspect"'` in `psse_contract_test.py`: 1.
- The phase-gate mutation list of 02-VALIDATION.md was not re-run: no earlier Phase 2 module changed in this plan (`probe.py` is new; the only edit to an earlier file is the one allow-list entry).

## Deviations from Plan

### Auto-fixed Issues
None.

### Notes (choices inside the plan's latitude, not deviations of behaviour)
- **The allow-list entry is its own commit** (`e5482ab`), before any probe code, with the reason in the message body, as the plan asks. Only `"inspect"` and one comment line were added.
- **Task 1 was run red first** (ImportError: no `probe` module). **Task 2's tests were first run green**, because the Task 1 implementation already covered the cases (the dependent-check SKIP rule, the identifier-free details); the mutation checks above are the evidence they can fail. Task 3's tests were run red (the note did not exist), then green.
- **Small additions to the probe beyond the plan text:** a check that cannot run because the adapter could not be built or the case did not load is a SKIP "not run: ..." (the failing row comes first, so `probe_ok` is still false); a function that takes any keyword (a `**kwargs` signature) with names missing is SKIP, because the names cannot be confirmed; a failing adapter call shows its function name and ierr, which carry no argument or path, as well as the exception class.
- **Test count:** `psse_probe_test.py` has 11 tests (the plan names 11); `psse_study_doc_test.py` has the 7 named tests.
- **Bash.** One empty heredoc was run by mistake twice (an interactive Python start that read nothing, and `cat >> file` with no body that appended nothing). All file content went through Write and Edit. STATE.md, ROADMAP.md and REQUIREMENTS.md were not updated, per the user's rules; `.planning/config.json`, `milestone.lock` and `state.json` remain uncommitted.

## Known Stubs
None.

## Threat Flags
None. The probe adds no network, auth or filesystem surface: it reads the case, may write the working case in memory (opt-in) and reloads it, and never saves. T-02-32 (identifiers out of the report: `test_report_hides_identifiers_by_default`, `test_detects_mapping_problems`), T-02-33 (case untouched: `test_tracer_probe_against_fake_all_pass`, `test_report_write_check_off_by_default`), T-02-34 (`test_doc_links_placeholder_and_has_no_identifiers`, `secret_scan_test.py`), T-02-35 (`test_doc_states_honest_scope`) and T-02-36 (`test_detects_renamed_parameter`, `test_detects_missing_function`, `test_detects_uninspectable_signature_as_skip`) are mitigated with the named tests.

## Hand-off notes for Phase 3
- Run the probe once on the laptop through the launcher, which imports `psspy` and calls `probe.run_probe`. Use the default `show_identifiers=False` for anything pasted into the repository.
- Against the fake the probe proves its own logic only. The real signatures (`branch_chng_3` and the combined `scal_2` form are UNVERIFIED), units, margins, N-1 scope and run time on Power Systems' network are proven only by that run and a reviewed study run.
- The extended margin walk can add about 80 load flows per city; measure the whole study's run time.
- The interpreter version and the `psycopg` pin are deferred to Phase 3 (`psycopg` 3.3.6 needs Python 3.10 or later; PSS/E's bundled Python is not known).

## Self-Check: PASSED
- FOUND: backend/psse_job/probe.py, backend/tests/psse_probe_test.py, backend/tests/psse_study_doc_test.py, docs/data-science/decisions/psse_study_definitions.md
- FOUND commits: e5482ab, e9b0fbe, b470427, 15812ed (each an ancestor of HEAD); measured `git rev-list --count` from the ledger base is 4

## Questions for the user / Power Systems

1. Mapping (Power Systems): for each city, which line or lines carry its rating in your case (from bus, to bus, circuit id), and are all of a city's lines at one base kV? Today the job runs on a placeholder with fake 9xxxx buses; a city with mixed base kV fails the run at stage mapping.
2. Rate set (Power Systems): should the DLR value go into RATEA only, or also RATEB (and RATEC), and should N-1 overloads be judged against RATEB rather than RATEA? Default: write RATEA and judge every check against RATEA (`study.rate_sets` in the mapping file changes it).
3. Static overwrite (user and Power Systems): when no trusted DLR row exists, should the project's static rating replace your case's own rating on the mapped lines, or should the case rating stay? Default: the static rating is written, as IN-01 requires; the case's previous value is kept in the dispatch row's details as rate_before_mva.
4. Voltage-margin transfer (Power Systems): for each city, which buses should take the extra load in the margin search, what should supply it, and how far may the search go? Defaults: the far end of the first mapped line takes the load and the swing bus supplies it (`sink_buses` per city in the mapping file); the search steps 25 MW at a time to a 1000 MW starting cap (`transfer.max_mw`, or `transfer_max_mw` per city) and, if no voltage, convergence or rating limit has been found by then, at most 80 more steps (`transfer.extra_steps`); if it still finds none, the run fails at stage voltage_margin rather than report the cap as a limit.
5. Base-case violations (Power Systems): should violations that already exist before any outage stay in the N-1 table, flagged in_base_case, or be left out? Default: kept and flagged.
6. Licensed modules (laptop owner): does the laptop's PSS/E have the PV/QV or ACCC modules licensed, and should the job use them instead of its own load-flow loops? Default: not used.
7. Case size and run time (Power Systems): about how many buses and branches does the case have, and is screening the lines within 2 branches of the mapped lines (at most 200 outages, 25 minutes per run) acceptable every hour? Defaults: contingency.hops 2, contingency.max 200, max_runtime_seconds 1500.
8. Limits (Power Systems): are the voltage bands 0.95 to 1.05 pu before and 0.90 to 1.05 pu after an outage (buses at or above 100 kV) and a current-based thermal check at 100 % of the rating right for your case? Defaults as stated, all in the mapping file's study section.
