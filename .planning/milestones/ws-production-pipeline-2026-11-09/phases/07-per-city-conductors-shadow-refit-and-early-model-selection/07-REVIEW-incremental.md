---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
reviewed: 2026-11-07T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - backend/forecast_conductor_ablation.py
  - backend/tests/forecast_conductor_ablation_test.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 07: Code Review Report (incremental, commit 3aa7bf4)

**Reviewed:** 2026-11-07
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Scope was `git diff a1fcb02 HEAD` for the two files: a `core.v4_signed()` refusal added to `main()` (exit 2, stderr message, nothing written) and one test. The guard is correct for the CLI path. It runs after `parse_args`, so `--help` and argument errors still work. It runs before `_default_out_dir()` and `run_ablation()`, so no directory is created and no frames are loaded. `v4_signed()` fails closed on a missing or blank signing copy (checked in `forecast_shadow_eval_core.py:329`). The new test patches `core.v4_signed`, which is the attribute `main()` reads through `core.`, so the patch takes effect. No blockers. The findings below cover guard placement and test coupling.

## Warnings

### WR-01: Gate lives only in the CLI `main()`, not in the `run_ablation` / `write_report` library entry points

**File:** `backend/forecast_conductor_ablation.py:614` (compare `backend/forecast_test_split_score.py:198`)
**Issue:** The TEST-split sibling puts its `v4_signed()` check inside `run_test_split`, the library function. Any caller of the module is therefore refused, and the CLI is covered as a consequence. Here the check sits only in `main()`. `run_ablation()` (line 359) and `write_report()` (around line 575) can still be called programmatically while v4 is unsigned, for example from a notebook, another script or a future driver. Both will compute and write the ABLATION report. The T-07-23 mitigation therefore covers one invocation path, not the behaviour it names. The commit says it mirrors the TEST-split CLI, but the real enforcement point there is the library function. The asymmetry is also untested: the new test patches `run_ablation` to fail, so it never checks that `run_ablation` is unguarded.
**Fix:** Raise at the top of `run_ablation()` (or `write_report()`), and let `main()` translate the error to exit 2:
```python
if not core.v4_signed():
    raise core.EvaluationGuardError("protocol v4 is not signed; the ABLATION re-score runs only after the signed v4 (T-07-23)")
```
In `main()`, catch `core.EvaluationGuardError` for this case, print the message to stderr and return 2. Alternatively, record in the plan or threat register that the gate is intentionally CLI-only.

### WR-02: Existing success-path CLI test now depends on the repository's real signing copy

**File:** `backend/tests/forecast_conductor_ablation_test.py:597` (`test_main_runs_the_ablation_and_prints_the_veto_summary`)
**Issue:** Before this commit, `main()` never read the signing copy. Now `test_main_runs_the_ablation...` calls `main()` without patching `core.v4_signed`, so it silently depends on the checked-in signing copy being signed. The repo's own test `forecast_shadow_eval_core_test.py:632` asserts that today. The test fails with rc 2 instead of exercising the pipeline if the signing copy is reverted, edited, or absent (shallow or sparse checkout, a packaged copy, a rebase onto an earlier state). The failure would then look like an ablation regression instead of a gate. The unsigned case is pinned by the new test, but the signed case should be pinned the same way.
**Fix:** Patch the signed state in the success-path test:
```python
monkeypatch.setattr(core, "v4_signed", lambda repo_root=None: True)
```

## Info

### IN-01: Module docstring does not mention the new refusal

**File:** `backend/forecast_conductor_ablation.py:1-42`
**Issue:** The "Run by a human offline" paragraph (line 38) and the "checked against the signed registry in plan 07-10" sentence (line 11) do not say the CLI now exits 2 until the v4 signing copy carries a signature. A reader running the documented command on an unsigned tree sees only the error. The stderr message also does not name the signing copy path (`core.V4_SIGNING_COPY`).
**Fix:** Add one sentence to the docstring, and optionally append the path to the stderr message. The message embeds the internal threat ID "T-07-23", which means little to an operator. Say "protocol v4 signing copy has no signature".

### IN-02: New test is weak on the "nothing written" claim

**File:** `backend/tests/forecast_conductor_ablation_test.py:611-618`
**Issue:** `assert not os.path.exists(out)` is true even if a guard-bypassing regression created and removed a parent directory, or wrote to the default evidence root (`core.EVIDENCE_ROOT_DEFAULT`). Here `--out-dir` is given, so `_default_out_dir()` is never exercised. The test also does not assert that stdout is empty (no "ABLATION report written" line).
**Fix:** Also assert `not (tmp_path / "v4-ablation").exists()`, and `capsys.readouterr().out == ""`. Optionally add a variant without `--out-dir`, with `core.EVIDENCE_ROOT_DEFAULT` monkeypatched to a temp path, and assert it stays empty.

---

_Reviewed: 2026-11-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
