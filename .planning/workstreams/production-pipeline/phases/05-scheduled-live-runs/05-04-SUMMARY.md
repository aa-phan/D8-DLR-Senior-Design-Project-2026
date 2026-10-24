---
phase: 05-scheduled-live-runs
plan: 04
subsystem: infra
tags: [github-actions, joblib, sha256, gitignore, model-artifacts, preflight, pytest]

requires:
  - phase: 05-scheduled-live-runs
    provides: "05-01: .github/workflows/dlr_live.yml with the install step and 'Run live pipeline' step, and dlr_live_workflow_test.py (3 text checks)"
  - phase: 04-supabase-store-writer
    provides: "config.FORECAST_ML_MODEL_DIR / ANOMALY_ML_MODEL_DIR and the production model path resolvers and strict loaders in ampacity_forecast and anomaly_detector"
provides:
  - "backend/dlr_live_check_models.py: live model pre-flight (presence, SHA-256 against a tracked manifest, then strict load) and --write-manifest"
  - "OD-10: the eight per-city live models tracked in git at the paths config reads, through a /data/models/* gitignore carve-out with nine explicit ! lines"
  - "data/models/LIVE_ARTIFACT_HASHES.sha256: sha256sum-format manifest of the eight artifacts (repo-relative paths)"
  - "Workflow step 'Pre-flight - live model artifacts present and verified' between install and the live run, handed no secrets"
affects: [05-05, 05-06, 05-07, 05-08, phase-06, phase-07]

actuals:
  tokens: 5397
  tasks: 3
  commits: 4

tech-stack:
  added: []
  patterns:
    - "Hash every required artifact against a tracked manifest before any joblib.load (pickle) so unvalidated bytes are never deserialized in a process holding secrets"
    - "Required artifact paths come from the production resolvers (ampacity_forecast._model_path_for, anomaly_detector._model_path_for), never a re-typed filename template"
    - "A gitignore carve-out for a directory uses /dir/* plus explicit ! lines, because git cannot re-include a file inside an excluded directory"
    - "Pre-flight tests build stand-ins with joblib.dump under tmp_path and write manifests with hashlib, independent of the module's own writer"

key-files:
  created:
    - backend/dlr_live_check_models.py
    - backend/tests/dlr_live_check_models_test.py
    - data/models/LIVE_ARTIFACT_HASHES.sha256
    - data/models/forecast_AUSTIN.joblib
    - data/models/forecast_CORPUS_CHRISTI.joblib
    - data/models/forecast_MIDLAND.joblib
    - data/models/forecast_EL_PASO.joblib
    - data/models/anomaly_AUSTIN.joblib
    - data/models/anomaly_CORPUS_CHRISTI.joblib
    - data/models/anomaly_MIDLAND.joblib
    - data/models/anomaly_EL_PASO.joblib
  modified:
    - .gitignore
    - .github/workflows/dlr_live.yml
    - backend/tests/dlr_live_workflow_test.py

key-decisions:
  - "check() reports every problem (missing manifest or entry, missing file, hash mismatch, unreadable file) before any load, and runs the strict loaders only when that list is empty and load is true"
  - "The manifest is parsed strictly: a line that is not '<64 hex>  <path>', or a path listed twice with different hashes, is a reported problem, not skipped"
  - "write_manifest() returns the missing paths as problems and writes nothing when any of the eight is missing; manifest lines are sorted by path"
  - "The pre-flight step carries no env block and no secrets, because it unpickles model files"

patterns-established:
  - "Promotion of a retrained model = regenerate LIVE_ARTIFACT_HASHES.sha256 with --write-manifest and commit it with the artifacts; without it the job fails before rating"

requirements-completed: [PIPE-02]

coverage:
  - id: D1
    description: "The pre-flight verifies presence and SHA-256 of all eight live artifacts against the manifest, and loads nothing until every hash matched; a missing artifact, tampered artifact, missing/empty/incomplete/garbled manifest each fail with the path (and manifest) named"
    requirement: PIPE-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_test.py#test_tampered_artifact_fails_before_any_load"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_test.py#test_missing_artifact_fails_and_names_the_path"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_test.py#test_missing_or_incomplete_manifest_fails"
        status: pass
    human_judgment: false
  - id: D2
    description: "A hash-matching artifact that will not deserialize fails as 'load failed: <city> <kind>', the clean path exits 0 with the OK line, and the manifest writer round-trips and refuses when a file is missing"
    requirement: PIPE-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_test.py#test_unloadable_artifact_fails_after_hashes_match"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_test.py#test_all_present_and_matching_passes"
        status: pass
      - kind: unit
        ref: "backend/tests/dlr_live_check_models_test.py#test_write_manifest_round_trip_and_refuses_missing_files"
        status: pass
    human_judgment: false
  - id: D3
    description: "The eight live models and LIVE_ARTIFACT_HASHES.sha256 are tracked at the paths config reads; every other file under data/models stays ignored; the real artifacts match the manifest and load under the pinned scikit-learn"
    requirement: PIPE-02
    verification:
      - kind: other
        ref: "git ls-files data/models (9 lines); git check-ignore -q on training_frame_AUSTIN.csv, anomaly_AUSTIN_CORPUS_CHRISTI.joblib, bakeoff_report.json"
        status: pass
      - kind: other
        ref: "shasum -a 256 -c data/models/LIVE_ARTIFACT_HASHES.sha256 (8 x OK); PYTHONPATH=backend .venv/bin/python backend/dlr_live_check_models.py exit 0"
        status: pass
    human_judgment: false
  - id: D4
    description: "dlr_live.yml runs the pre-flight after the dependency install and before the live run, with no secrets in the step"
    requirement: PIPE-02
    verification:
      - kind: unit
        ref: "backend/tests/dlr_live_workflow_test.py#test_models_are_verified_before_the_run"
        status: pass
    human_judgment: false
  - id: D5
    description: "On a real GitHub-hosted runner the pre-flight passes against the checked-out models (same Python 3.12 and scikit-learn 1.9.1 as the owner's venv) and fails the job when an artifact is altered"
    requirement: PIPE-02
    verification: []
    human_judgment: true
    rationale: "Nothing has been pushed; only a dispatched run on the runner proves the checkout, the pinned requirements and the pre-flight together. Backstopped by plan 05-06 Task 2's first dispatch."

duration: 10 min
completed: 2026-10-24
status: complete
plan_head_before: da8f6b294d8f87632d117aa15fd38cc565e37ff4
plan_head_after: 1d5eab565553f8f1806c7e679ecff0ad0c463cd7
commits: 4
---

# Phase 5 Plan 04: Live model artifacts and pre-flight Summary

**The eight per-city forecast and anomaly joblib models are now tracked in git through a `/data/models/*` carve-out with a SHA-256 manifest, and `dlr_live_check_models.py` fails the live job before any rating when one is missing, altered or unloadable (hashes are checked before anything is unpickled).**

## Performance

- **Duration:** 10 min
- **Started:** 2026-10-24T08:44:44Z
- **Completed:** 2026-10-24T08:54:08Z
- **Tasks:** 3 (4 commits: TDD RED test, TDD GREEN feat, chore for the artifacts, feat for the workflow)
- **Files modified:** 14 (3 existing files edited, 11 new, 8 of them binary models)

## Accomplishments

- `backend/dlr_live_check_models.py`: `required_artifacts()` (resolvers from `ampacity_forecast` and `anomaly_detector`), `sha256_file`, a strict `read_manifest`, `check(manifest_path, load=True)` that lists every problem and calls the production strict loaders per city only when none is open, `write_manifest()` and `main(argv)` (`--write-manifest`; exit 0 with the OK line, exit 1 with every problem on stderr). Six offline tests against `joblib.dump` stand-ins, including a spy that proves the loaders are never called when an artifact is tampered with.
- OD-10 carve-out: `/data/models/` became `/data/models/*` followed by nine explicit `!` lines (eight artifacts and the manifest), with a comment that mirrors the shadow carve-out and states the promotion procedure. Training frames, observation CSVs, reports, retrain logs, `legacy_corridor_era/` and the corridor-era joblibs (`anomaly_AUSTIN_CORPUS_CHRISTI.joblib`, `anomaly_MIDLAND_EL_PASO.joblib`) stay ignored.
- The eight artifacts were committed byte-for-byte from the main checkout with `LIVE_ARTIFACT_HASHES.sha256`. The real pre-flight (`PYTHONPATH=backend .venv/bin/python backend/dlr_live_check_models.py`) exits 0, which also proves all eight load under scikit-learn 1.9.1 on Python 3.12.
- `dlr_live.yml` runs "Pre-flight - live model artifacts present and verified" after the install step and before "Run live pipeline"; the step has no `env` block.

## Committed artifacts (sizes and dates)

All eight were dated 2026-10-13 (01:05 to 01:07 local) before commit, so none is a Phase 2-3 retrain after the 2026-10-13 snapshot the plan records. Sizes match the plan's table exactly (total 762,094 bytes).

| Path | Bytes | Modified | SHA-256 |
|------|------:|----------|---------|
| `data/models/forecast_AUSTIN.joblib` | 268,512 | 2026-10-13 01:05 | `dd6d540d0ccd8403f6b857001919ffa1505e0dc25a0c4f9e3789a3699804cc7c` |
| `data/models/forecast_CORPUS_CHRISTI.joblib` | 44,641 | 2026-10-13 01:05 | `d4527fefb591301e54d5cf536bfd86ff44cc70f434e62402a45fd9d8b10e535e` |
| `data/models/forecast_MIDLAND.joblib` | 48,241 | 2026-10-13 01:07 | `0a62d94ed4402bfa294619969aedd4f4ab51b64c9736f89c4241abe776e81606` |
| `data/models/forecast_EL_PASO.joblib` | 380,744 | 2026-10-13 01:06 | `3cd066e0c3fd31f5a786323282a75ec9ca806d10b190ac83fb1ff1fa285731c3` |
| `data/models/anomaly_AUSTIN.joblib` | 6,577 | 2026-10-13 01:06 | `2ecaead8d2be2fb7bcc179bef82958b536f73f34b6959b9b63a22f0faa83f6a4` |
| `data/models/anomaly_CORPUS_CHRISTI.joblib` | 4,897 | 2026-10-13 01:06 | `9fbc26ab8907a033e013b4e67881b4bc0d399de74f912ba7ee9423fa920c8cc0` |
| `data/models/anomaly_MIDLAND.joblib` | 4,289 | 2026-10-13 01:06 | `d1b2ac321a79ec77a6d16314c3a2b8cfc6cd370e38a526b4370cc758b03c4f9b` |
| `data/models/anomaly_EL_PASO.joblib` | 4,193 | 2026-10-13 01:06 | `d4431d56fabd8514df228b585ccc5c156a2c12b7653f57363236c9c79a7aaf37` |

Artifact commit: `c7c9e44` (`git show --stat` lists only `.gitignore`, the manifest and the eight joblib paths). The manifest's first line is a comment dated 2026-10-24.

## Task Commits

1. **Task 1 RED: failing tests for the live model pre-flight** - `c8e71e3` (test)
2. **Task 1 GREEN: live model pre-flight with a SHA-256 manifest** - `fdda342` (feat)
3. **Task 2: track the eight live models (OD-10) with a SHA-256 manifest** - `c7c9e44` (chore; one-way: binaries now live in git history)
4. **Task 3: run the live model pre-flight before rating** - `1d5eab5` (feat)

**Plan metadata:** recorded in the docs commits that follow this file (SUMMARY, then STATE/ROADMAP/REQUIREMENTS). Nothing was pushed.

## TDD Gate Compliance (Task 1, `tdd="true"`)

- **RED:** `c8e71e3` carries the six tests plus a behavior-less stub of the module (`check()` returns `['not implemented']`, `required_artifacts()` returns `[]`, `write_manifest()` writes nothing, `main()` returns 1), so the tests import and fail on their assertions instead of on a missing module. 6 of 6 failed. `gsd-tools check tdd-red-evidence` on the pytest JUnit XML for the target `test_tampered_artifact_fails_before_any_load` returned `RED_EVIDENCE_OK` (`target_test_failed`, format `junit`). Semantic assessment: the target failed on `assert 'hash mismatch' in 'not implemented'`, the planned assertion for the planned behavior, not on an import, collection or fixture fault. The other five failed on their own assertions (the writer test on the manifest file not existing after `write_manifest`). Evidence record: `.planning/tmp/05-04-t1-red-evidence.json` (untracked, like the rest of `.planning/tmp`).
- **GREEN:** `fdda342`; 6 of 6 pass. Full `backend/tests`: 1712 passed, 48 skipped (baseline after 05-03: 1699 plus this plan's 6 + 1 new tests and 05-03's own additions; 0 failed).
- **REFACTOR:** none needed.

## Files Created/Modified

- `backend/dlr_live_check_models.py` - pre-flight module (`required_artifacts`, `sha256_file`, `read_manifest`, `check`, `write_manifest`, `main`; `MANIFEST_PATH`)
- `backend/tests/dlr_live_check_models_test.py` - 6 test functions over `tmp_path` stand-ins, with a loader spy
- `.gitignore` - `/data/models/*` plus nine `!` lines and the OD-10 comment
- `data/models/LIVE_ARTIFACT_HASHES.sha256` - 8 entries sorted by path, sha256sum format
- `data/models/{forecast,anomaly}_{AUSTIN,CORPUS_CHRISTI,MIDLAND,EL_PASO}.joblib` - the eight live models, unchanged
- `.github/workflows/dlr_live.yml` - the pre-flight step replaces 05-01's placeholder comment
- `backend/tests/dlr_live_workflow_test.py` - `test_models_are_verified_before_the_run` (now 4 functions)

## Decisions Made

- The pre-flight reports all problems at once rather than stopping at the first, and when the manifest itself is missing, empty or malformed it names the manifest once instead of repeating a "no entry" line for each file. Missing files are still listed individually in that case.
- Manifest parsing is strict (a garbled line or a path with two different hashes is a failure), because a manifest that silently drops a line would let that artifact skip verification.
- The workflow step has no `env:` block and the test asserts no `${{` expression sits in it: it is the step that unpickles model files, so it is given nothing to leak.
- `write_manifest()` is pure (no header comment); the dated comment line was added by hand per the plan. A regenerated manifest therefore has no comment, which `read_manifest` and `shasum -c` accept.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Manifest lines sorted by hash instead of by path**
- **Found during:** Task 1 (GREEN run)
- **Issue:** the first `write_manifest` sorted the formatted `"<hash>  <path>"` lines, so the order followed the hash digits; the round-trip test (and the plan's "sorted" requirement) expects path order.
- **Fix:** sort the paths, then format.
- **Files modified:** `backend/dlr_live_check_models.py`
- **Verification:** `test_write_manifest_round_trip_and_refuses_missing_files` passes
- **Committed in:** `fdda342`

**2. [Rule 1 - Bug] Workflow test regexes matched the wrong text**
- **Found during:** Task 3
- **Issue:** the first draft of `test_models_are_verified_before_the_run` looked for `requirements.txt` on a `run:` line (the install command is on the next line of a block scalar) and for the substring `secrets.` in the pre-flight step (its own comment says "no secrets.").
- **Fix:** match the `python -m pip install -r requirements.txt` command line and assert no `${{` expression appears in the step.
- **Files modified:** `backend/tests/dlr_live_workflow_test.py`
- **Committed in:** `1d5eab5`

### Plan-vs-instruction differences (not defects)

- **Commit trailer:** the plan says `Co-Authored-By: Claude Opus 5.5`; the commits carry `Claude Sonnet 5.5`, the model that made them, per the attribution instruction for this run.
- **Task 1 commit split:** the plan says one commit for Task 1. The canonical TDD reference for a `tdd="true"` task asks for `test(...)` then `feat(...)`, so there are two (`c8e71e3`, `fdda342`). The RED commit includes a behavior-less stub of the module so RED is a valid assertion failure, not an import error; the `feat` message is the one the plan specifies.
- **Full-suite command:** the plan's verify runs `pytest` with no path; per the run instructions it was run as `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests` (a smoke script elsewhere in `backend/` needs a token).

---

**Total deviations:** 2 auto-fixed (both Rule 1, caught by tests before the commit they belong to)
**Impact on plan:** none on scope; both fixes are inside the planned files.

## Discrepancies

- **The runbook the `.gitignore` comment points at does not exist yet.** The comment cites the promotion procedure in `docs/data-science/decisions/dlr_live_runbook.md`, as the plan instructs. That file is plan 05-05's deliverable; until it lands the reference dangles. 05-05 must document: regenerate with `PYTHONPATH=backend python backend/dlr_live_check_models.py --write-manifest`, then commit the artifacts and the manifest together.
- **GNU `sha256sum -c` warns on the manifest's comment line** ("1 line is improperly formatted") but exits 0 and reports all eight `OK`. macOS `shasum -a 256 -c` is silent. The workflow does not use either tool: the Python pre-flight skips `#` lines.
- **The pre-flight has not run on a runner.** Verified here only through the real artifacts in the main checkout (exit 0) and the offline tests. The Python 3.12 / scikit-learn 1.9.1 match between the owner's venv and the runner is stated in the plan, not re-checked in CI; 05-06's first dispatch is the check.
- **Hash-then-load is not atomic.** A file changed between the hash check and the load would be loaded; the window is within one process on a fresh checkout and is accepted, in line with T-05-16's scope (guards accidental or unpromoted changes, not a collaborator who can edit code).
- Everything else matched the plan: file sizes and dates, the nine-line `git ls-files data/models`, the ignored generated files, and `git diff --quiet origin/main` on `shadow_collect.yml`, `forecast_shadow_check_models.py` and `data/shadow`.

## Issues Encountered

None beyond the items above. The pre-existing untracked and modified files in the working tree (`.DS_Store`, `.obsidian/`, `graphify-out/`, the phase 07 directory, `.planning/config.json`, and so on) were left unstaged; every commit used explicit paths. `data/models/` still holds files the plan does not track (`anomaly_AUSTIN_CORPUS_CHRISTI.joblib`, `anomaly_MIDLAND_EL_PASO.joblib`, CSVs, reports, retrain logs); `git status --porcelain --untracked-files=all data/models` prints nothing.

## Known Stubs

None. The RED-phase stub in `backend/dlr_live_check_models.py` was replaced by the implementation in `fdda342`; no TODO or FIXME text remains.

## Threat Flags

None. The surface added is the one in the plan's threat model (T-05-16 to T-05-20): committed pickles verified by hash before any load (T-05-16, tamper test asserts the loaders are never called), an unpromoted retrain failing the job (T-05-17), a missing model failing before the run step (T-05-18), per-file `!` lines with a ten-path commit stat (T-05-19).

## User Setup Required

None - no external service configuration required. Nothing was pushed; the artifacts reach GitHub when plan 05-06 pushes after the owner approves (binary permanence in history is shown at that push).

## Next Phase Readiness

- Ready for 05-05 (runbook: model promotion procedure, above) and 05-06 (push and first dispatch, which exercises the pre-flight on a runner).
- The first push will carry 762,094 bytes of binaries into git history permanently (T-05-20, accepted).

## Self-Check: PASSED

- FOUND: `backend/dlr_live_check_models.py`, `backend/tests/dlr_live_check_models_test.py`, `data/models/LIVE_ARTIFACT_HASHES.sha256`, the eight `data/models/{forecast,anomaly}_*.joblib`, `.github/workflows/dlr_live.yml`, `backend/tests/dlr_live_workflow_test.py`
- FOUND commits: `c8e71e3`, `fdda342`, `c7c9e44`, `1d5eab5` (`git rev-list --count da8f6b2..HEAD` = 4)
- Acceptance criteria re-run: module greps pass; test counts 6 and 4; `git ls-files data/models` prints 9 lines; ignore checks pass; `shasum -a 256 -c` 8 x OK; pre-flight exit 0; `git show --stat c7c9e44` lists only `.gitignore` and nine `data/models` paths; shadow files unchanged from `origin/main`; targeted tests 31 passed; full `backend/tests` 1712 passed, 48 skipped, 0 failed.

---
*Phase: 05-scheduled-live-runs*
*Completed: 2026-10-24*
