---
phase: 05-hourly-workflow-dry-run-and-live-soak
plan: 05
subsystem: ops
tags: [bundle, scan-log, base64-secrets, leak-test, counts-only, owner-commands, throwaway-tree]
status: complete

requires:
  - phase: 05-hourly-workflow-dry-run-and-live-soak
    provides: "05-01 hourly.main, materialize, SECRET_ENV, the closed vocabulary and the fixture; 05-04 the soak command"
  - phase: 04-replay-and-agreement-check
    provides: "the replay output test pattern (needle sets, teeth) and replay_cli._newest_check and _default_mapping"
provides:
  - "backend/pandapower_job/hourly.py: the bundle and scan-log owner commands, their constants and seven vocabulary patterns"
  - "backend/tests/pandapower_hourly_fixture.py: private_tree, PLANTED, read_env and the planted writer and Supabase URLs"
  - "backend/tests/pandapower_hourly_owner_test.py: 16 tests of both owner commands on a throwaway private tree"
  - "backend/tests/pandapower_hourly_leak_test.py: the planted-identifier leak test over 22 output cases, with five teeth"
affects: [05-06, 05-07, 05-08, runbook, owner-hand-off]

actuals:
  tokens: 16800
  tasks: 3
  commits: 3
plan_head_before: b2ca6d71c6199d6d3443646d339ad50f090baa8a
plan_head_after: d6f1564106a0bcfd198cbd6b803c772288634377

tech-stack:
  added: []
  patterns:
    - "the bundle rebuilds both recorded-settings documents from the validated backend instead of filtering the check report, so a key that is not rebuilt cannot pass"
    - "verify before write: the four values are decoded into a temporary folder, loaded back, preflighted and hashed against the source files, and only then is the exclusive private folder made"
    - "scan-log refuses every input on which the scanner would silently scan nothing (empty needle set, log in the private folder, log over the size limit, log that is not text)"
    - "leak test collects every case's output first and builds scan set B afterwards, so run ids and figures seen by the recording study are in the set"

key-files:
  created:
    - backend/tests/pandapower_hourly_owner_test.py
    - backend/tests/pandapower_hourly_leak_test.py
  modified:
    - backend/pandapower_job/hourly.py
    - backend/tests/pandapower_hourly_fixture.py

key-decisions:
  - "The bundle's equality check on load-back compares the settings and the three scaling details, not the scaling evidence: the evidence is deliberately not in the secret (T-05-19), and nothing at run time reads it"
  - "scan-log gets an eighth refusal word, log_binary, for a log the scanner reports as binary (a NUL byte or a binary suffix); the scanner skips such a file silently, which would read as a clean log"
  - "bundle takes an optional say callable so the lines come out in true order (sizes, verified, written) and a refusal after the size lines does not lose them"

requirements-completed: []

coverage:
  - id: D1
    description: "bundle turns a throwaway private tree into four single-line base64 files named after the four secrets in a new exclusive folder, prints only byte counts, base64 lengths and fits words, and an environment made of exactly those four files runs a dry run on the real engine with exit 0 and the source files' case and mapping hashes"
    requirement: OPS-02
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_owner_test.py#test_tracer_bundle_secrets_drive_a_dry_run_end_to_end"
        status: pass
    human_judgment: false
  - id: D2
    description: "the settings bundle holds only the settings key and the marker with the six settings keys, the scaling bundle only the three details and the marker; no planted session hash, NET-03, parity or evidence value is in any decoded or encoded file; the network and mapping travel byte for byte"
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_owner_test.py#test_bundle_keeps_only_the_settings_and_detail_keys"
        status: pass
    human_judgment: false
  - id: D3
    description: "every bundle refusal writes nothing (in_ci, records_missing, mapping_missing, mapping_refused, a placeholder source, preflight_refused, network_refused, private_path, exists); a value exactly at the secret limit fits and one character over refuses the whole bundle as too_large"
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_owner_test.py#test_bundle_refusals_write_nothing"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_owner_test.py#test_bundle_second_run_in_the_same_second_is_refused_as_existing"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_owner_test.py#test_bundle_secret_limit_boundary"
        status: pass
    human_judgment: false
  - id: D4
    description: "scan-log prints counts only on a clean log, fires on a planted mapping key, scaling target and bundled-secret fragment without printing any of them, and refuses a log inside the private folder, a missing file, an empty needle set, a log over the size limit or not text, a malformed allow list, another drive and GitHub Actions"
    requirement: OPS-02
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_hourly_owner_test.py#test_scan_log_clean_log_prints_counts_only"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_owner_test.py#test_scan_log_finds_planted_values_without_printing_them"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_hourly_owner_test.py#test_scan_log_refusals"
        status: pass
    human_judgment: false
  - id: D5
    description: "every output of 13 runner paths and 9 owner-command paths is vocabulary lines only, no line starts with two colons, nothing reaches standard error or the log, the scratch temporary folder is empty, and two needle sets (private-tree derived, and planted secrets, base64 values and fragments, hashes, run ids, branch keys and figures) find nothing in it; five teeth show the scans fire on a planted password, branch key, scaling target, base64 fragment and run id"
    requirement: OPS-02
    verification:
      - kind: integration
        ref: "backend/tests/pandapower_hourly_leak_test.py#test_tracer_every_run_path_output_is_vocabulary_and_scans_clean"
        status: pass
      - kind: integration
        ref: "backend/tests/pandapower_hourly_leak_test.py#test_soak_and_owner_command_output_scans_clean"
        status: pass
      - kind: integration
        ref: "backend/tests/pandapower_hourly_leak_test.py#test_scan_teeth_fire_on_planted_values"
        status: pass
    human_judgment: false
  - id: D6
    description: "the bundle and scan-log commands run correctly on the owner's real private folder and a real downloaded Actions log (the tests rehearse them on a synthetic tree only)"
    requirement: OPS-02
    verification: []
    human_judgment: true
    rationale: "Plan 05-07 has the owner run both commands on the real private tree and a real log; no test here, and no run by this plan, opens the real private folder"

duration: about 1h 10min (estimated; the owner file runs about 100 s, the leak file about 40 s)
completed: 2026-11-26
---

# Phase 5 Plan 05: Owner commands bundle and scan-log, and the leak test Summary

**`pandapower_hourly.py bundle` writes four verified single-line base64 secret files from the private tree (settings and scaling documents rebuilt from the validated backend, so no NET-03 or parity detail travels), `scan-log` scans a downloaded Actions log against the private needles and the bundled secrets and prints only counts, line numbers and kinds, and a planted-identifier leak test over 22 output paths, with five teeth, finds nothing in anything the runner or the owner commands print.**

## Performance

- **Tasks:** 3 of 3
- **Files:** 2 created, 2 modified
- **Tests:** owner file 16 passed (about 100 s, the tracer runs the real four-city study once); leak file 3 passed (about 40 s, the real study once); quick set (`pandapower_hourly_test.py`, `pandapower_hourly_workflow_test.py`, `pandapower_soak_test.py`, `pandapower_replay_output_test.py`, `pandapower_import_gate_test.py`) 109 passed in 109 s. Nothing skipped.

## Accomplishments

- **Tracer (Task 1): `bundle`.** `bundle(repo_root, check_dir, mapping_path, now, say)` finds the newest check folder and the mapping, passes each through the private-path guard, loads and validates the recorded backend, checks the network with `convert.case_from_json` and the mapping with `mapping.load_mapping` and runs the engine's preflight. `bundle_documents(backend)` rebuilds the settings document (the `settings` key with the six settings keys, plus the marker) and the scaling document (the three details plus the marker); nothing else of the check report can reach a secret. The four values are base64-encoded, sized against `convert.SECRET_LIMIT_BYTES` (read at call time), decoded into a temporary folder, loaded back as a recorded backend equal to the source, preflighted and prepared with `engine.prepare_run`, and the case and mapping hashes must equal the source files' sha256; only then is `data/private/pandapower/secrets/secrets_STAMP/` made (exclusive) and the four `<SECRET NAME>.txt` files written. On the real engine an environment made of exactly those four files runs a dry `run` with exit 0 and the source files' hashes.
- **`scan-log` (Task 2).** `scan_log(repo_root, log_path)` refuses a log inside `data/private` (resolved and lexical), a missing file, a log over `private_leak_scan.MAX_BYTES`, a log the scanner reads as binary, a malformed allow list, an empty needle set and a log on another drive; it derives the needles from the private folder, adds every token of 20 or more characters of the newest bundle folder's four files as `secret_fragment`, scans with `private_leak_scan.scan_paths`, and prints the line count, the finding count and one `kind` line per finding. Exit 0 with no finding, 1 with findings, 2 for any refusal.
- **Leak test (Task 3).** 13 runner cases (dry on the real engine, dry with a noisy study printing, writing, warning and logging planted values, dry under GitHub Actions, dry and live duplicated-outage refusals, live connect failures carrying the planted writer URL, password and host, live placeholder, missing secret, bad base64, oversized secret, records refused, an exception in prepare naming a branch key, usage) and 9 command cases (soak with gaps, soak with a failing connect, bundle written, exists, in CI and without records, scan-log clean, with a finding and refused). Each runs through the real output sink under `capfd` and `caplog`, in its own scratch folder. Teeth: a planted writer password, a branch key, a scaling target, a base64 fragment and a run id each make the matching scan and token check fire, a `::` line and a bus-key line each fail the vocabulary check, and the clean output rescans clean afterwards.

## Final vocabulary additions (`HOURLY_LINE_PATTERNS`, each ends `\Z`)

```
bundle: (network|mapping|settings|scaling) bytes=N base64=N (fits|does not fit)
bundle: verified
bundle: written
bundle: refused \((in_ci|private_path|records_missing|mapping_missing|network_refused|mapping_refused|preflight_refused|placeholder|too_large|exists)\)
scan-log: lines=N findings=N
scan-log: finding line=N kind=(SCAN_KINDS)
scan-log: refused \((in_ci|log_missing|log_inside_private|log_outside_drive|log_too_large|no_needles|allow_list|log_binary)\)
```

`SCAN_KINDS` is `mapping_key`, `scaling_target`, `file_hash`, `decimal`, `secret_fragment`, `needle`, the five shape names of `private_leak_scan.SHAPE_PATTERNS`, `private_path_in_tree`, `session_artifact_path` and `oversize_unscanned`. `bundle` can also print the existing `records: refused (REASON)` line. Exit codes: `bundle` 0 or 2; `scan-log` 0, 1 (findings) or 2.

Leak test case count: 22 output cases (13 runner, 9 command) plus the teeth test.

## Task Commits

1. **Task 1: Tracer, `bundle` and the owner test file (12 tests)** - `7fb3b2e` (feat)
2. **Task 2: `scan-log` and four more tests** - `dd1a701` (feat)
3. **Task 3: the planted-identifier leak test** - `d6f1564` (test)

**Plan metadata:** the docs commit that follows this file.

## Files Created/Modified

- `backend/pandapower_job/hourly.py` - bundle and scan-log commands, constants, vocabulary, dispatch of `repo_root` to the owner commands
- `backend/tests/pandapower_hourly_fixture.py` - `private_tree`, `PLANTED`, `read_env`, `planted_writer_url`, `planted_supabase_url`
- `backend/tests/pandapower_hourly_owner_test.py` - 16 tests (4 bundle groups with a parametrized refusal test of 8 cases, the same-second `exists` test, 4 scan-log tests)
- `backend/tests/pandapower_hourly_leak_test.py` - 3 tests, 22 cases

## Decisions Made

- The load-back equality in the bundle's own verification compares the settings and the three scaling details only. The scaling evidence is dropped on purpose (it is part of what must not travel), and `engine.settings_record` never reads it.
- `log_binary` was added to the scan-log refusal words: `private_leak_scan.scan_paths` returns no findings for a file it classes as binary, so a log with a NUL byte near the start would read `findings=0` after scanning nothing.
- The imports `private_leak_scan` and `pandapower_job.private` are at module level in `hourly.py` (both standard library only, so a dry run still loads no writer-side module and no driver; the fresh-interpreter test of plan 05-01 still passes); `replay_cli` is imported inside `bundle()` only, so the heavy replay modules stay out of the hourly path.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] A log the scanner skips silently would read as clean**
- **Found during:** Task 2
- **Issue:** the plan's refusal list covers a missing file, a log inside the private folder, an empty needle set and an oversize log, but `scan_paths` also silently skips a file it classes as binary (a NUL byte in the first 8,192 bytes, or a binary suffix). `findings=0` after scanning nothing is exactly the T-05-21 failure the plan names.
- **Fix:** an eighth word, `log_binary`, appended to `SCAN_REFUSAL_REASONS` (the plan's seven words are unchanged and in their order), refused before scanning; a test writes a log with a NUL byte.
- **Files modified:** `backend/pandapower_job/hourly.py`, `backend/tests/pandapower_hourly_owner_test.py`
- **Commit:** `dd1a701`

**2. [Interface extension, no rule] `bundle` takes an optional `say`**
- **Issue:** the plan's signature `bundle(repo_root=None, check_dir=None, mapping_path=None, now=None)` returns a result, but the plan also wants the size lines, `verified` and `written` printed in order, with the size lines kept when a later step refuses.
- **Fix:** a fifth keyword `say=None`; without it `bundle` prints nothing and returns `BundleResult(folder, sizes)`, so the plan's four-argument call works unchanged.
- **Commit:** `7fb3b2e`

**Total deviations:** 1 auto-fixed (Rule 2) plus 1 interface extension. **Impact:** none on the plan's behaviour; both make the commands refuse or print more faithfully.

## Known Stubs

None.

## Threat Flags

None. `bundle` and `scan-log` add no endpoint and no network path; they read and write only under `data/private` (through the private-path guard) and refuse under GitHub Actions. The plan's threat register T-05-19 to T-05-22 is covered by the keys test, the leak test's set B (base64 values and fragments), the scan-log refusals and the closed vocabulary.

## Issues Encountered

None in the code under test. The tests were first run in full after both owner commands existed and passed at the first run. `git` printed LF-to-CRLF warnings on the touched files; no test pins file bytes or asserts file modes. The known Windows-only failures named in the task brief were not touched. No command of this plan was run against the real private folder; the one `ls -d` of the acceptance criteria printed nothing (no bundle folder in this checkout).

## Next Phase Readiness

- Plan 05-06 (workflow and runbook) can name `bundle --check-dir --mapping` and `scan-log --log` as written; the bundle folder is `data/private/pandapower/secrets/secrets_STAMP/` with files `<SECRET NAME>.txt`, one base64 line each.
- Plan 05-07's owner steps: run `bundle` and expect four `fits` lines, `bundle: verified`, `bundle: written`; run `scan-log` on one real downloaded log and expect `findings=0`.
- OPS-02 stays Pending in REQUIREMENTS.md by the orchestrator's instruction until the owner steps and the live soak are done.

## Self-Check: PASSED

- FOUND: backend/pandapower_job/hourly.py (`def bundle(`, `def scan_log(`, `private.write_private_bytes`, `private_leak_scan.scan_paths`)
- FOUND: backend/tests/pandapower_hourly_fixture.py (`private_tree`, `PLANTED`)
- FOUND: backend/tests/pandapower_hourly_owner_test.py (432 lines, 16 tests) and backend/tests/pandapower_hourly_leak_test.py (544 lines, 3 tests)
- FOUND commits: 7fb3b2e, dd1a701, d6f1564
- Owner file 16 passed; leak file 3 passed; quick set 109 passed; file-scope gate exit 0 after each commit; staged leak scan exit 0 before each commit; whole-checkout `private_leak_scan.py` exit 0; no change under backend/psse_job
