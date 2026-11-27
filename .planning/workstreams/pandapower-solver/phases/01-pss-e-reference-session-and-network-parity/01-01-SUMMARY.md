---
phase: 01-pss-e-reference-session-and-network-parity
plan: 01
subsystem: security
tags: [leak-guard, gitignore, stdlib, secret-scan, pss-e, private-data]

requires:
  - phase: none
    provides: first plan of the phase, nothing upstream
provides:
  - ignore rules for /data/private/ and psse_pp_session* (comment-first, before any private file exists)
  - backend/private_leak_scan.py, a standard-library three-layer scanner (path, shape, needle) with working-tree and --staged modes, allow-list and CLI exit codes 0/1/2
  - private_leak_scan.Finding, SHAPE_PATTERNS and the function names later plans import
  - this checkout's own Python 3.12 .venv (used by every later verify command)
affects: [01-02, 01-07, 01-08, 01-09, 01-10, 01-11]

plan_head_before: 5c34c9c1d001110aec9a0e47a694e1daa49c90f7
plan_head_after: f7287b13094204cbc481cd9e82d2d4d4046ea6f8

actuals:
  tokens: 12000
  tasks: 2
  commits: 2

tech-stack:
  added: []
  patterns:
    - "Leak findings are path:line:layer:pattern only; matched text never reaches stdout, stderr, a Finding or a repr (NeedleSet repr is counts-only)"
    - "Scanner patterns and test plants are assembled from string pieces so no tracked file matches itself"
    - "Needles are matched as whole tokens by set membership (linear in line length)"

key-files:
  created:
    - backend/private_leak_scan.py
    - backend/tests/private_data_guard_test.py
  modified:
    - .gitignore
    - backend/tests/secret_scan_test.py

key-decisions:
  - "raw_terminator carries a negative lookahead for the begin phrase, so a terminator line that also names the next section is reported once, as raw_begin"
  - "RAW shape patterns are case-sensitive upper case (PSS/E writes them that way) so lower-case prose never matches"
  - "Path layer also flags any not-ignored working-tree file under data/private/ or with a psse_pp_session path component, and a missing ignore rule is a finding (private_dir_not_ignored)"
  - "A needle's reported pattern name is its kind (mapping_key, scaling_target, file_hash, decimal), carried by a NeedleSet subclass of set"
  - "The repository root for the CLI is the git toplevel of the cwd (so a pre-commit hook judges the repo being committed), falling back to the script's own checkout"

requirements-completed: [PSE-04]

coverage:
  - id: D1
    description: "The ignore rules for data/private/ and the psse_pp_session artefacts are in place and nothing under data/private/ is tracked"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/secret_scan_test.py#test_private_data_folder_is_ignored_and_untracked"
        status: pass
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_tracer_ignore_rule_clean_tree_and_planted_identifier"
        status: pass
    human_judgment: false
  - id: D2
    description: "The scanner passes the clean working tree and flags a planted placeholder identifier by path and line only"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_tracer_ignore_rule_clean_tree_and_planted_identifier"
        status: pass
      - kind: integration
        ref: ".venv/bin/python -I -B backend/private_leak_scan.py (exit 0, empty stdout)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Shape layer: each RAW and marker pattern fires on its plant, the header only on the first non-empty line, prose does not match"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_shape_layer_flags_each_planted_pattern"
        status: pass
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_shape_header_only_on_the_first_line"
        status: pass
    human_judgment: false
  - id: D4
    description: "Needle layer: decimals, scaling-target forms, file hashes and mapping keys, matched as whole tokens"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_needles_decimals_targets_and_hashes"
        status: pass
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_needles_match_whole_tokens_only"
        status: pass
    human_judgment: false
  - id: D5
    description: "Staged mode scans index blobs, fails closed on an oversize staged text file, and the allow-list exempts only an exact path plus sha256"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_staged_mode_scans_the_index_not_the_working_tree"
        status: pass
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_staged_oversize_file_fails_closed"
        status: pass
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_allow_list_exempts_only_an_exact_sha256"
        status: pass
    human_judgment: false
  - id: D6
    description: "No finding, stdout, stderr or repr carries matched text; CLI exit codes 0/1/2"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_findings_never_hold_the_matched_text"
        status: pass
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_cli_exit_codes"
        status: pass
    human_judgment: false
  - id: D7
    description: "The needle layer against the REAL files under data/private/ (decimal false-positive rate on real data, completeness of derived needles)"
    requirement: "PSE-04"
    verification:
      - kind: unit
        ref: "backend/tests/private_data_guard_test.py#test_owner_local_working_tree_has_no_private_values"
        status: unknown
    human_judgment: true
    rationale: "data/private/ does not exist yet (plan 01-10 brings the export onto the owner's machine); the test is skipped here and can only run owner-local once real files exist"

duration: 25min
completed: 2026-11-17
status: complete
---

# Phase 1 Plan 01: Leak guard before the data Summary

**A standard-library three-layer leak scanner (path, shape, owner-local exact needles) over the working tree and the git index, plus the `/data/private/` and `psse_pp_session*` ignore rules, in place before any PSS/E export exists.**

## Performance

- **Duration:** about 25 min (start time was not captured at the very start of the run; estimated from the first and last timestamps)
- **Completed:** 2026-11-17T00:20Z (UTC)
- **Tasks:** 2 of 2
- **Files modified:** 4 (2 created, 2 modified)

## Accomplishments

- The ignore rules exist before any private file does: `git check-ignore -q data/private/pandapower/x.json` exits 0, a session zip and a work folder with the `psse_pp_session` prefix are ignored anywhere in the tree, and `git ls-files -- data/private` prints nothing.
- `backend/private_leak_scan.py` exits 0 with empty stdout on the clean tree and exits 1 on a planted 8xxxx mapping key, a planted RAW structure line, or a planted marker key. Output is `path:line:layer:pattern` only.
- `--staged` scans index blobs: a file staged and then deleted or edited clean in the working tree is still flagged, and a staged text file over 2 MiB is a `size` finding (fail closed). Working-tree mode only counts such files, on stderr.
- Needles are derived from `data/private/` only (mapping keys in both orientations from any object at any depth, scaling targets in plain, two-decimal and thousands-comma forms, each file's sha256 in both cases, decimals with five or more fractional digits after trailing zeros are stripped) and matched as whole tokens by set membership. An absent folder skips the layer.
- The allow-list contract is in place for plan 01-11: `backend/private_leak_allow.json` (absent today) exempts a file only when path and sha256 both match; a listed sha256 is not a needle; a malformed list is exit 2.
- This checkout now has its own `.venv` (Python 3.12.13, built from the shared checkout's interpreter without modifying the shared venv; `pip install -r requirements.txt` then `pip check`: "No broken requirements found.").

## Task Commits

1. **Task 1: Tracer - ignore rule and a scanner that flags a planted identifier** - `3c8066b` (feat)
2. **Task 2: Shape layer, full needle set, staged mode and the allow-list** - `f7287b1` (test)

**Plan metadata:** the SUMMARY commit that follows this file (docs).

The tracer gate: re-ran the tracer `<verify>` end to end after the commit (pytest `-k "tracer or private_data_folder or env_file or tracked_files_hold_no_credentials"`: 4 passed; scanner CLI exit 0, empty stdout). Verified, then expanded.

## Verification Results

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/private_data_guard_test.py backend/tests/secret_scan_test.py -k "not owner_local and not real_project_values"`: `16 passed, 2 deselected in 3.43s` (no skips; all ten named tests plus `test_private_data_folder_is_ignored_and_untracked` in the passed set).
- Full run of the same two files without `-k`: `16 passed, 2 skipped` (the two skips are the owner-local needle scan, `data/private/` absent, and the owner-local Supabase value scan, variables not exported).
- `.venv/bin/python -I -B backend/private_leak_scan.py`: exit 0, empty stdout. `... --staged` (with the two Task 2 files staged): exit 0, empty stdout. `... --no-such-flag`: exit 2.
- `.venv/bin/python -c "import sys; print(sys.version_info[:2])"`: `(3, 12)`.
- Frozen-file gate (PLAN=01-01) after each commit: `GATE_OK`.
- Wave-end regression `pytest -q -p no:cacheprovider backend/tests/psse_contract_test.py backend/tests/psse_api_test.py backend/tests/psse_study_test.py`: `126 passed in 1.16s`.
- Post-commit deletion check on both commits: no deletions.

## Files Created/Modified

- `.gitignore` - comment-first block after `*.raw` with `/data/private/` and `psse_pp_session*`
- `backend/private_leak_scan.py` - the scanner (Finding, SHAPE_PATTERNS, NeedleSet, repo_root, working_tree_files, staged_blobs, derive_needles, load_allow_list, scan_paths, scan_blobs, main)
- `backend/tests/private_data_guard_test.py` - PSE-04 proofs (11 tests, one owner-local)
- `backend/tests/secret_scan_test.py` - `test_private_data_folder_is_ignored_and_untracked` after the `.env` guard; nothing else changed

## Decisions Made

See `key-decisions` in the frontmatter. In short: one finding per line for a terminator-plus-begin RAW line; upper-case-only RAW patterns; extra path-layer findings (`private_path_in_tree`, `session_artifact_path`, `private_dir_not_ignored`); needle kind as the reported pattern name; CLI root taken from the cwd's git toplevel so a hook judges the repository being committed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Counts-only repr for NeedleSet**
- **Found during:** Task 2 (first red run)
- **Issue:** pytest's assertion rewriting printed the whole needle set when an `in needles` assertion failed. With real needles that would put private values into a test log, which C-7 and T-01-02 forbid.
- **Fix:** `NeedleSet.__repr__` returns `NeedleSet(<N needles>)`.
- **Files modified:** `backend/private_leak_scan.py`
- **Commit:** `f7287b1`

### Process deviations (no code impact)

**2. Branch allow-list in the pre-commit assertion not applied.** The executor protocol's worktree check requires an `agent-*` branch. The orchestrator dispatched this plan sequentially on the existing feature branch `feature/pandapower-solver` and said to stay on it. Applied: detached-HEAD refusal, protected/default-branch refusal (the branch is not protected), supplied-root pin before every write and commit.

**3. Plan commit ledger kept outside the git directory.** The sandbox refused the compound `git rev-parse --git-dir` redirect, so the base SHA (`5c34c9c1d001110aec9a0e47a694e1daa49c90f7`) was recorded in the session scratchpad instead. `plan_head_before` in the frontmatter is that value; `commits: 2` was measured with `git rev-list --count` against it.

**4. Task 1 includes the `--private-root` flag.** The plan lists both flags under Task 2; `--private-root` was needed by the Task 1 tracer subprocess path and landed in Task 1. `--staged` landed in Task 2 as planned.

**Total deviations:** 1 auto-fixed (Rule 2), 3 process notes. **Impact:** none on the plan's outputs or interfaces.

## Issues Encountered

None blocking. Two transient auto-mode classifier failures on Bash calls were retried once each and succeeded.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or schema; the scanner only reads files and runs read-only git commands.

## Threat Model Coverage

- T-01-01 (leak into git): ignore rules plus path, shape and needle layers over tracked and not-ignored files and over index blobs; `test_tracer_ignore_rule_clean_tree_and_planted_identifier`, `test_staged_mode_scans_the_index_not_the_working_tree`.
- T-01-02 (scanner output): `test_findings_never_hold_the_matched_text` checks stdout, stderr and `repr` of findings for every plant kind.
- T-01-03 (shape false negatives): one plant per pattern and a clean sibling in `test_shape_layer_flags_each_planted_pattern`.
- T-01-04 (untracked tool output): the working-tree scan includes untracked-not-ignored files, so `graphify-out/`, `.planning/graphs/` and `.obsidian/` are in scope (A13 stays unverified; the scan is the backstop).
- T-01-SC: only existing `requirements.txt` pins were installed, no new package.

## Open Items For Later Plans

- The needle layer has not been run against real private data (D7 above). Decimals that are common in public text could raise findings once real files exist; the owner resolves them by location, and a pinned published copy goes through the allow-list (plan 01-11).
- Any later tracked source that writes a marker key as a JSON literal must assemble it from pieces, or it will match its own shape (stated in the module docstring).
- The owner can enable the local pre-commit step by putting `exec .venv/bin/python backend/private_leak_scan.py --staged` in `.git/hooks/pre-commit`.

## Next Phase Readiness

Ready for plan 01-02. The guard is in place and its interface names are final.

## Self-Check: PASSED

- FOUND: `.gitignore`, `backend/private_leak_scan.py`, `backend/tests/private_data_guard_test.py`, `backend/tests/secret_scan_test.py`
- FOUND commits: `3c8066b`, `f7287b1` (both ancestors of HEAD)
