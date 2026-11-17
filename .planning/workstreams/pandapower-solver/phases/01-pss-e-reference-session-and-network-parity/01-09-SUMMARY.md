---
phase: 01-pss-e-reference-session-and-network-parity
plan: 09
subsystem: testing
tags: [pandapower, ingest, zip-safety, private-path-guard, cli, net-02, net-03, pse-04, leak-guard]
status: complete

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: the session zip layout and bundle reader (01-02 to 01-04); parity, convert and D-06 evidence (01-07); settings_from_session, scale_city, inject_snapshot, run_load_flow, compare_city, load_registry and net03_verdict (01-08)
provides:
  - backend/pandapower_job/private.py, a guard that refuses any write outside an ignored data/private/ (outside root, not ignored, not a checkout, symlink escape, existing file)
  - backend/pandapower_job/ingest.py, allow-listed, capped and hash-verified extraction of the incoming zip, plus verify_session_dir and check_mapping
  - backend/pandapower_job/cli.py and backend/pandapower_net_check.py, the owner's ingest and check commands with a vocabulary-checked counts-only renderer
  - backend/tests/pandapower_ingest_test.py (29 tests) and backend/tests/pandapower_cli_test.py (9 tests)
affects: [01-10, 01-11]

plan_head_before: 149dc8f94a5ee0782483aa45d68c9482b9abece2
plan_head_after: 855481f79109b1753a7eba6ebcb3384815adb9f0
actuals:
  tokens: 23000
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "One printer accepts only lines matching CLI_LINE_PATTERNS; a line outside the vocabulary stops the command with a generic error line, so no value can be printed by accident"
    - "Every private write goes through require_private (resolved path inside data/private, git check-ignore as the judge, no symlink escape), exclusive and 0600 by default"
    - "All checks on a zip's directory are made before one byte is extracted; extraction goes to <dest>.partial, is hash-verified per member and renamed into place; any exit removes the partial folder"
    - "An incomplete comparison (scaling refused or undetermined, no convergence, missing reference) is a stand-in net with converged False, so the comparator reports it incomplete rather than the CLI inventing a verdict"
    - "Marker keys are taken from the modules (cli.REPORT_MARKER, convert.CONVERTED_MARKER), never typed in tests, so the leak guard does not flag the sources"

key-files:
  created:
    - backend/pandapower_job/private.py
    - backend/pandapower_job/ingest.py
    - backend/pandapower_job/cli.py
    - backend/pandapower_net_check.py
    - backend/tests/pandapower_ingest_test.py
    - backend/tests/pandapower_cli_test.py
  modified: []

key-decisions:
  - "require_private asks git itself (git check-ignore with GIT_CEILING_DIRECTORIES set to the repository's parent) instead of copying the ignore rule, so the rule the repository really has is the judge and a non-checkout cannot borrow an enclosing repository's rules"
  - "verify_session_dir accepts the check_<stamp> folders and explained_differences.json beside the manifest's members and refuses any other extra file, so a second check on the same session works and a planted file does not"
  - "check_mapping hashes the mapping bytes and compares with the manifest before parsing; an unreadable or invalid mapping (or a placeholder without --allow-placeholder) prints mapping_invalid, a hash difference prints mapping_mismatch; both exit 2"
  - "When var limits are inconclusive both settings run (labels algorithm:enforce_q_lims_off and _on) and both must pass; the injected diagnostic uses the first of them (off)"
  - "A city's printed algorithm word is incomplete if any of its algorithm verdicts is incomplete, else pass or fail; the overall net03 line says incomplete when any city is incomplete or undecided, else fail"
  - "report.json, d06_evidence.json and scaling_details.json carry the report marker, converted_network.json carries its own, so every output matches the leak guard's pandapower_marker shape"

requirements-completed: [NET-02, NET-03, PSE-04]

coverage:
  - id: D1
    description: "A synthetic session zip made with the real bundle writer ingests and checks to exit 0: parity pass, four city passes, net03 pass, the four private outputs under <session>/check_<stamp>/ and nothing created outside data/private/"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_tracer_ingest_and_check_a_synthetic_session_to_a_pass"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_entry_script_without_arguments_is_a_usage_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each unsafe archive (not a zip, bad name, no or bad manifest, unlisted or missing member, four bad member names, duplicate, symlink, encrypted, four caps, changed member) is refused with exactly its reason, leaves no partial or destination folder, and echoes no content; an existing destination is left alone"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_ingest_test.py#test_ingest_refuses_each_unsafe_archive"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_ingest_test.py#test_refusals_leave_no_partial_or_destination_folder"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_ingest_test.py#test_an_existing_destination_is_refused_and_left_alone"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_ingest_test.py#test_zip_slip_writes_nothing_outside_the_session_folder"
        status: pass
    human_judgment: false
  - id: D3
    description: "An extracted folder re-verifies by hash, flags an edit, a missing, extra or symlinked member and a missing manifest; a mapping whose bytes differ by one character is refused by reason only and the CLI exits 2"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_ingest_test.py#test_verify_session_dir_detects_an_edit"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_ingest_test.py#test_mapping_mismatch_is_refused_by_reason_only"
        status: pass
    human_judgment: false
  - id: D4
    description: "The private guard refuses a path outside data/private, one in a repository without the ignore rule, one in a folder that is not a checkout, a symlink leading out, and an existing file under exclusive creation"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_ingest_test.py#test_private_guard_refuses_unsafe_paths"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_ingest_test.py#test_private_writers_add_the_marker_and_keep_the_file_private"
        status: pass
    human_judgment: false
  - id: D5
    description: "The zip written by the real session code against the fake psspy ingests and its members are read by the Mac side; the fake's own network is refused by the builder by reason; the fake's numbers give a fail, never a pass"
    requirement: "NET-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_seam_fake_session_zip_flows_through_ingest_and_check"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_seam_fake_network_is_refused_by_the_builder_by_reason_only"
        status: pass
    human_judgment: false
  - id: D6
    description: "A reference voltage moved by 0.011 pu fails exactly that city (and a registry entry for exactly that element and size turns it into a pass); a missing city reference or unavailable transformer flows is incomplete; a three-winding network is refused by reason with only report.json written"
    requirement: "NET-03"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_deliberate_mismatch_fails_check"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_missing_or_partial_reference_is_incomplete"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_network_refusal_is_reported_by_reason_only"
        status: pass
    human_judgment: false
  - id: D7
    description: "Everything printed matches the command vocabulary (no bus number, no value with five decimals, no path) for pass, fail and seam runs; the renderer refuses a line that would carry a value; the outputs are git-ignored, 0600 and flagged by the leak guard's marker shape"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_check_output_is_counts_only"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_cli_test.py#test_private_outputs_are_ignored_and_flagged_by_the_leak_guard"
        status: pass
    human_judgment: false
  - id: D8
    description: "That the commands work on the real session zip (real RAW structure, real references, real settings and scaling evidence) and what NET-03 says about real PSS/E numbers"
    requirement: "NET-03"
    verification:
      - kind: manual_procedural
        ref: "plan 01-10: the owner runs ingest and check on the teammate's zip"
        status: unknown
    human_judgment: true
    rationale: "Only synthetic and fake-session data exist here; whether the network builds from the real export and whether pandapower agrees with PSS/E within D-13 can only be learned on the real zip."

duration: "not captured (no start time was recorded at the beginning of this run)"
completed: 2026-11-17
---

# Phase 1 Plan 09: Ingest and check commands Summary

**The owner's two commands, `ingest` and `check`: a session zip from another machine is extracted only after an allow-list, size caps and per-member sha256 pass, every output is forced into an ignored data/private/ through one guard, and everything printed is a counts-only line from a fixed vocabulary.**

## Performance

- **Completed:** 2026-11-17
- **Tasks:** 3 (one tracer, two auto with tdd)
- **Files created:** 6 (3 production modules, 1 entry script, 2 test files; 2,222 lines)

## Accomplishments

- `private.require_private` resolves a path through symlinks, requires it inside `<repo>/data/private/`, asks `git check-ignore` whether it is ignored and refuses with one of five reason words. `write_private_bytes` and `write_private_json` create files exclusively, mode 0600, without following a link at the last name; the JSON writer adds the marker key and refuses NaN.
- `ingest.ingest_zip` checks the zip's directory first (entry count, declared sizes, total, compression ratio, name shape, duplicates, symlink and encryption bits, manifest validity, exact member set), then extracts into `<dest>.partial` while re-checking sizes and each sha256, and renames into place. Any exit, including an interrupt, removes the partial folder; an existing destination is never touched.
- `verify_session_dir` and `check_mapping` re-verify an extracted folder and refuse a mapping whose sha256 differs from the manifest's before parsing it.
- `cli.main` runs the Mac side in order and prints, per run: session and mapping verified, network built or refused by reason, parity pass or fail with per-category counts, the converted copy's size, D-06 evidence written, the settings it copied and their deviation count, the three scaling details, per city an algorithm word, counts and injected word, the NET-03 line and the report line. Private files go to `<session>/check_<stamp>/`: `report.json` (every verdict in full with element keys, settings and sources, scaling evidence, parity differences, versions), `converted_network.json`, `d06_evidence.json`, `scaling_details.json`.
- Exit codes follow the plan: 0 pass, 1 the check ran and parity or NET-03 failed or was incomplete or the network was refused, 2 usage, ingest or mapping or registry refusal, private-path refusal and unexpected errors.

## Task Commits

1. Task 1 (tracer): `206c854` feat(01-09): tracer - ingest and check a synthetic session to a pass with private-only outputs
2. Task 2: `ab79067` test(01-09): unsafe archives and unsafe output paths are refused
3. Task 3: `855481f` test(01-09): session-to-Mac seam, deliberate mismatch and counts-only output

Tracer feedback gate: after `206c854` the tracer `<verify>` was re-run end to end (2 passed, nothing skipped; the entry script with no arguments printed the two usage lines on stderr and exited 2) before Task 2 expanded.

## Verification

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_cli_test.py backend/tests/pandapower_ingest_test.py`: `38 passed in 65.59s`, nothing skipped (9 cli tests, 29 ingest tests).
- The phase's quick set plus the existing job (`private_data_guard`, `psse_session`, `psse_session_reference`, `psse_session_settings`, `pandapower_raw`, `pandapower_network`, `pandapower_parity`, `pandapower_compare`, `secret_scan`, `psse_contract`, `psse_api`, `psse_study`, `psse_entry`, with `-k "not owner_local and not real_project_values"`): `350 passed, 2 deselected, 2 warnings in 130.47s`, no failed, error or skipped.
- `.venv/bin/python -I -B backend/pandapower_net_check.py` exits 2 with no traceback. `git status --porcelain -- data` is empty. The staged leak scan exited 0 before each of the three commits and the full scan exits 0. The frozen-file gate (PLAN=01-09) exits 0 after each commit.
- Mutation spot checks, each reverted: dropping the symlink refusal and dropping the git-ignore check each failed their tests (`symlink_member` case; `test_private_guard_refuses_unsafe_paths`); making `check` always exit 0 and treating an incomplete verdict as complete failed the mismatch and incomplete tests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Plan assumption wrong] The fake session's network is refused by the builder**
- **Found during:** Task 1 (exploring the fake session's zip before writing the seam test)
- **Issue:** The plan says the fake's RAW "parses and builds, parity passes". It parses, but `network.build_network` refuses it with `machine_at_load_bus` (4 elements): the fake's placeholder case puts its machines at buses typed as load buses. The frozen fake and session cannot be edited.
- **Fix:** Two seam tests. `test_seam_fake_network_is_refused_by_the_builder_by_reason_only` runs the unchanged fake and proves `network: refused (machine_at_load_bus)`, exit 1 and a report holding the reason and element keys privately. `test_seam_fake_session_zip_flows_through_ingest_and_check` registers the same placeholder case with its machine buses retyped to voltage-controlled (a change to the case object the test registers, not to the fake, the session or any frozen file), runs the real `session.main` with all four sections, and then ingest and check: parity passes (all categories compared, nothing differing) and every city gets its NET-03 lines.
- **Files modified:** backend/tests/pandapower_cli_test.py
- **Commit:** 855481f

**2. [Rule 3 - Blocking] Frozen fixture reads transformer results with line column names**
- **Found during:** Task 1 (building the synthetic references; the 39-bus case has transformers)
- **Issue:** `pandapower_fixture.reference_from_solved` raises on any net with a transformer (the issue plan 01-08 recorded). The fixture is frozen for this plan.
- **Fix:** the test helper `_reference` aliases `res_trafo`'s hv and lv columns to the line names on a copy before calling the fixture, as plan 01-08's test helper does. The fixture is untouched. Nothing in production code calls it, so no further follow-up remains for plan 01-10 unless a later test calls it on a transformer net.
- **Files modified:** backend/tests/pandapower_cli_test.py
- **Commit:** 206c854

### Interpretation choices (the plan text was silent or contradictory)

- **Seam verdict.** The plan says the seam's verdict is a fail. On the fake data the algorithm run cannot start: `swing_in_total` classifies inconclusive (the fake's swing machine has zero output, so both totals agree) and `clamped_at_limits` is inconclusive, so `scale_city` raises `ScalingUndetermined` and each city's algorithm word is `incomplete` (`net03: incomplete (0 of 4 cities)`, exit 1). The injected run, which needs no scaling rule, is complete and fails on all four cities (9 buses and 48 flows compared each), which is what the seam test asserts. This is still "never a pass" and proves the members are read.
- **destination_exists.** The plan says every refusal leaves no destination folder; for an existing destination that cannot hold, so the test asserts the existing folder and its file are left untouched and no `.partial` appears.
- **Session folder contents.** `verify_session_dir` tolerates `check_<stamp>` folders and `explained_differences.json` next to the manifest's members (the check's own outputs and the owner's registry), and refuses any other extra entry as `unlisted_member`.
- **Extra vocabulary and helpers.** `mapping_invalid` (unreadable, invalid or placeholder mapping without the flag), `private.make_private_dir`, `ingest.REGISTRY_FILE_NAME` and the `registry: ...` lines are additions beyond the plan's lists; the interfaces only grew.
- **Marker.** `d06_evidence.json` and `scaling_details.json` carry `cli.REPORT_MARKER` (the plan names a marker for report.json only), so all four outputs match the leak guard's `pandapower_marker`.
- **Encrypted-entry test.** `zipfile` resets the flag bits on write, so the test forges the encryption bit in the finished file's central directory.

### Process notes

- **Tests were not observed failing first.** The three modules were written before their tests in Task 1 and the tests passed on the first run (Task 2 had one test-helper fix for the forged flag bit). The tests' ability to fail was checked afterwards with the mutations listed under Verification.
- **Branch allow-list and ledger.** The `agent-*` allow-list was not applied (sequential run on `feature/pandapower-solver` as dispatched); the supplied-root pin and the leak scan ran before every commit. The plan commit ledger is the scratchpad file `gsd-plan-head-before-01-09` (base `149dc8f`); `commits: 3` was measured with `git rev-list --count`. The sandbox refused compound shell forms (heredocs, `;`-joined git commands), so those were redone as plain commands and scratchpad scripts.
- STATE.md and ROADMAP.md were not touched, as instructed.

**Total deviations:** 1 Rule 1, 1 Rule 3, 6 interpretation choices, 3 process notes. **Impact:** none on the plan's outputs.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: subprocess | backend/pandapower_job/private.py | runs `git check-ignore` with a fixed argument list (no shell, `--` before the path, 30 s timeout) to judge whether a path is ignored; the path is relative to the resolved repository and the result is only the exit code |

The plan's threat register is otherwise covered: T-01-31 and T-01-32 by `test_ingest_refuses_each_unsafe_archive`, T-01-33 by `test_mapping_mismatch_is_refused_by_reason_only`, T-01-34 by `test_check_output_is_counts_only`, T-01-35 by `test_private_outputs_are_ignored_and_flagged_by_the_leak_guard`; nothing was installed (T-01-SC).

## Issues Encountered

- Each pandapower import prints a numba notice and takes about 5 s, so the cli and ingest test files take about a minute (the notice is a warning, not a failure).
- A second `check` in the same second as the first is refused as `private path: refused (exists)` (exit 2), because the check folder is named by the second; the test asserts this.

## Next Phase Readiness

Plan 01-10 can run `pandapower_net_check.py ingest --zip <zip>` and `check --session <dir> --mapping <file>` on the real export. Open points that only the real data can settle: whether the real RAW builds (the builder refuses what it cannot reproduce, by reason), whether the three scaling details classify decisively (an inconclusive `swing_in_total` makes every algorithm run incomplete, as the fake showed), what the var-limit fingerprints say, and whether any difference needs an explained-differences registry entry (`<session>/explained_differences.json`, loaded automatically).

## Self-Check: PASSED

- FOUND: backend/pandapower_job/private.py, ingest.py, cli.py, backend/pandapower_net_check.py, backend/tests/pandapower_ingest_test.py, backend/tests/pandapower_cli_test.py
- FOUND commits 206c854, ab79067 and 855481f, all ancestors of HEAD
