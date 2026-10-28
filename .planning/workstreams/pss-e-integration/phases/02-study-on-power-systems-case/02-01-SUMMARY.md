---
phase: 02-study-on-power-systems-case
plan: 01
subsystem: psse-job-configuration
tags: [pss-e, mapping, configuration, validation, json, stdlib, python37]
requires:
  - phase: 01
    provides: "psse_job.constants.CITIES, run_record.file_sha256 and case_label, the 3.7 syntax and import gate"
provides:
  - "psse_job.settings: BranchRef, Settings (22 fields), DEFAULT_SETTINGS, SettingsError, parse_settings, check_bus, check_ckt, rate_set_label"
  - "psse_job.mapping: Mapping, CityMapping, MappingError, parse_mapping, load_mapping (IN-02, D-08)"
  - "docs/data-science/schema/psse_mapping_example.json: the only committed mapping, a marked placeholder with fake 9xxxx buses"
  - ".gitignore rules for /psse_local/, *.sav, *.raw"
affects: [02-02, 02-03, 02-05, 02-06]
tech-stack:
  added: []
  patterns:
    - "json-only parsing of untrusted config with duplicate-key and NaN/Infinity refusal"
    - "all problems collected and raised once (MappingError.problems, SettingsError.problems)"
    - "hash of exactly the parsed bytes"
key-files:
  created:
    - backend/psse_job/settings.py
    - backend/psse_job/mapping.py
    - docs/data-science/schema/psse_mapping_example.json
    - backend/tests/psse_mapping_test.py
  modified:
    - .gitignore
key-decisions:
  - "SettingsError problems name the dotted path (study.thermal.colour); MappingError always prefixes them 'study: ' as the plan requires, so a nested message reads 'study: study.thermal.colour: unknown key'"
  - "Cross-field settings rules (band order, collapse below the voltage criterion, tolerance below step, max at least step) are judged on effective values, so overriding step_mw alone to 1 or less demands tolerance_mw be set too (the 1 MW default would not be below it)"
  - "Untrusted key text in messages is cut to 40 characters"
requirements-completed: [IN-02]
duration: 1h
completed: 2026-10-28
status: complete
commits: 3
plan_head_before: 7a5dc6709236a572d5e0b4f85e66ecc278400ee9
plan_head_after: ba80ef9e60002101902b532626c21b6cfed1f6b4
actuals:
  tokens: 13400
  tasks: 3
  commits: 3
---

# Phase 2 Plan 01: City-to-branch mapping and study settings Summary

**Validated JSON mapping (`load_mapping`) with a 22-field `study` section of stated defaults, sha256 of the parsed bytes, a placeholder guard, and git-ignore rules that keep the real mapping and case out of the public repository.**

## Accomplishments
- `load_mapping(path, allow_placeholder=False)` returns the four cities in `constants.CITIES` order (branches, sink buses defaulting to the first branch's to-bus, optional per-city transfer cap), the study settings, and `sha256` of exactly the bytes parsed (verified equal to `run_record.file_sha256` of the same file, and distinct for a CRLF copy).
- A malformed file raises `MappingError` naming up to 20 problems at once (42 malformed inputs covered; unknown keys at every level, duplicate keys, NaN/Infinity, bad buses, bad circuit ids including `&` multisection ids, branches repeated in either orientation or across cities, size over 64 KiB refused before any parse).
- Placeholder files are refused unless `allow_placeholder=True`; the committed example is a placeholder with buses 90001-90032 only.
- Every study parameter has a stated default (A8, A9, A11 of the research log) and a validated override path; 36 invalid overrides are covered.

## Task Commits
1. Task 1 (tracer): `fe89093` feat(02-01): tracer - load the placeholder city-to-branch mapping with default settings
2. Task 2: `f51f60e` test(02-01): every mapping rule refused with all problems named at once
3. Task 3: `ba80ef9` feat(02-01): study settings with stated defaults and validated overrides

## Verification
- `psse_mapping_test.py`: 101 tests (4 tracer/private, 52 rule, 45 settings); with `psse_contract_test.py` and `secret_scan_test.py`: 114 passed.
- Tracer gate run before expansion: 4 passed, contract gate 13 passed (tracer + contract + secret scan).
- Acceptance checks: `git check-ignore -q` exits 0 for `psse_local/city_branch_mapping.json`, `psse_local/case.sav`, `cases/ercot_2026.sav`; `python -I` example check prints `True ['AUSTIN', 'CORPUS_CHRISTI', 'EL_PASO', 'MIDLAND']`; the settings one-liner prints `22 RATEA`; the own-changes gate over protected paths exits 0.
- Mutation checks (each turned the named test red; files restored byte-for-byte, `git diff` empty): dropped duplicate-key hook, placeholder accepted without the flag, size check removed, `check_ckt` accepting `&1`, default `contingency_hops` 3.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Research assumption labels in settings.py comments**
- **Found during:** Task 3
- **Issue:** Task 1's default comments cited A8 for the rate set and A9 for voltage bands; the research log has A8 = voltage bands, A9 = rate set, A11 = numeric tuning values.
- **Fix:** Comments corrected in the Task 3 commit (`ba80ef9`).
- **Files modified:** backend/psse_job/settings.py

### Process deviations (no behaviour change)

- **Red-first not strictly observed for Task 2.** While writing Task 1 I wrote the full rule set into `mapping.py` rather than only the happy path, so the Task 2 tests passed on first run. Their strength was instead shown by the plan's mutation checks (all five red).
- **Task 1 commit carries two small hardening edits** (untrusted-key truncation in messages, always-prefix `study: `) that I applied before staging; the Task 2 commit message mentions `mapping.py` changes that are in fact in Task 1's commit. No code is missing or duplicated.
- Tests beyond the plan's named list were added (case-count guards, 20-problem cap, file exactly at the cap parses, BOM accepted, partial override keeps defaults, BranchRef key/orientation, NaN/Infinity settings, all-at-once settings); counts exceed the plan's minimums (rule 52 vs 48, settings 45 vs 40).

## Issues Encountered
- Bash heredocs failed in this shell (`unexpected EOF`), so test code and edits were applied with the Edit tool; nothing was lost.
- `.gitignore` uses CRLF and had no trailing newline; the new block was appended with CRLF, so the diff shows the final `.claude` line as changed (line ending only).

## Known Stubs
None.

## Threat Flags
None: no new network, auth or file-access surface beyond the plan's threat model (T-02-01 to T-02-05 mitigated and tested).

## Self-Check: PASSED
- Files exist: backend/psse_job/settings.py, backend/psse_job/mapping.py, backend/tests/psse_mapping_test.py, docs/data-science/schema/psse_mapping_example.json, .gitignore.
- Commits `fe89093`, `f51f60e`, `ba80ef9` are ancestors of HEAD; measured `git rev-list --count` from the ledger base is 3.
