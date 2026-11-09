---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
reviewed: 2026-11-07T00:00:00Z
depth: standard
files_reviewed: 48
files_reviewed_list:
  - backend/anomaly_training.py
  - backend/city_pipeline.py
  - backend/city_point.py
  - backend/city_rating.py
  - backend/config.py
  - backend/data_cleaning.py
  - backend/dlr_live_run.py
  - backend/forecast_conductor_ablation.py
  - backend/forecast_conductor_refit.py
  - backend/forecast_shadow_confirm.py
  - backend/forecast_shadow_decision_v4.py
  - backend/forecast_shadow_eval_core.py
  - backend/forecast_shadow_score.py
  - backend/forecast_test_split_score.py
  - backend/forecast_training.py
  - backend/rating_identity.py
  - backend/real_data_validation.py
  - backend/tests/city_pipeline_test.py
  - backend/tests/city_rating_test.py
  - backend/tests/city_rating_wind_projection_test.py
  - backend/tests/cleaning_pipeline_test.py
  - backend/tests/cond02_shadow_golden_test.py
  - backend/tests/data_cleaning_test.py
  - backend/tests/dlr_live_run_test.py
  - backend/tests/e2e_readonly_test.py
  - backend/tests/e2e_trace_test.py
  - backend/tests/example_read_ratings_test.py
  - backend/tests/expose_migration_test.py
  - backend/tests/fake_postgrest.py
  - backend/tests/forecast_conductor_ablation_test.py
  - backend/tests/forecast_conductor_refit_test.py
  - backend/tests/forecast_shadow_confirm_test.py
  - backend/tests/forecast_shadow_decision_v4_test.py
  - backend/tests/forecast_shadow_eval_core_test.py
  - backend/tests/forecast_shadow_eval_validation_test.py
  - backend/tests/forecast_shadow_score_test.py
  - backend/tests/forecast_test_split_score_test.py
  - backend/tests/forecast_training_test.py
  - backend/tests/golden_shadow_capture.py
  - backend/tests/production_conductor_test.py
  - backend/tests/protocol_v4_doc_test.py
  - backend/tests/protocol_v4_registry_test.py
  - backend/tests/protocol_v4_registry.py
  - backend/tests/rating_identity_test.py
  - backend/tests/real_data_validation_test.py
  - backend/tests/real_data_validation_val02_test.py
  - backend/tests/rest_api_doc_test.py
findings:
  critical: 1
  warning: 10
  info: 4
  total: 15
status: issues_found
---

# Phase 7: Code Review Report

**Reviewed:** 2026-11-07
**Depth:** standard
**Files Reviewed:** 48 (source files read in full or by phase diff; test files sampled for assertion quality and run)
**Status:** issues_found

## Summary

All listed test files pass locally (317 tests in the first batch, 761 in the second). I read the phase diff for the
production-rating files and the new evaluation modules in full, and probed the guard and redaction behaviour directly.

The safety-relevant rating path is mostly sound. `production_city_point` and `production_conductor_kwargs_for` fail closed
on an unknown city, a missing field, an unknown key, a bool or NaN. The G4 bounds are unchanged and AUSTIN at 100 C stays
inside them. The B5 naive fallback in `city_pipeline` only engages for the lookback gap and never for a trailing gap.
The B2 training fix (`city_training_frame` stores the projected wind) matches `city_rating._project_wind`. I found no
proven overstated-ampacity bug. I did find a real hole in the one-shot guard (CR-01), several protocol-enforcement gaps,
a redaction regression in the public-log path, and resolver ranges too loose to catch the unit slips they claim to catch.

## Critical Issues

### CR-01: One-shot FRESH guard is defeated by `--evidence-root`

**File:** `backend/forecast_shadow_eval_core.py:460-478,554-567`, `backend/forecast_shadow_confirm.py:1323,1352`, `backend/forecast_shadow_score.py:838`
**Issue:** The one-shot rule is "a prior `run_started.json` exists under the evidence subroot". The subroot is
`<--evidence-root>/<round>`, and `--evidence-root` is a free CLI option on both `forecast_shadow_confirm.py` and
`forecast_shadow_score.py`. A FRESH run with `--evidence-root /tmp/anything` sees no prior marker and is allowed.
I confirmed this against the real tree with a read-only `check_guard` call:
`data/shadow/evaluation/v4-read1` is refused ("second FRESH run"), while a fresh temp directory with the same round,
valid times and `now` returns `ALLOWED FRESH []`. The module docstring claims "signed v4 rounds take no override" and
that the one guard stays armed, but a plain flag the guard does not see is an override. Two concurrent invocations also
both pass `check_guard` before either writes its marker (no exclusive reservation), so they can both run.
**Fix:** Make the FRESH one-shot location non-overridable. Refuse any FRESH run whose evidence root is not exactly
`core.EVIDENCE_ROOT_DEFAULT` (resolved with `realpath`), or keep the one-shot ledger in a fixed repo-relative path
independent of the CLI. Reserve the slot atomically in `new_evidence_dir`/`check_guard`:
```python
# in check_guard, FRESH branch, after computing the fixed ledger directory
os.makedirs(ledger_dir, exist_ok=True)
try:
    fd = os.open(os.path.join(ledger_dir, f"{rnd.name}__{row_source}.lock"), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
except FileExistsError:
    raise EvaluationGuardError("round already spent ...")
os.close(fd)
```
Add a test that a FRESH `main(["--evidence-root", tmp_path, ...])` is refused. Exposure is low now (reads 1 and 2 are
spent, `v4-late-descriptive` is gated), but the guard's stated invariant does not hold.

## Warnings

### WR-01: `v4-read2` precondition ("only if read 1 names no winner") is not enforced in code

**File:** `backend/forecast_shadow_confirm.py:1342-1386`, `backend/forecast_shadow_eval_core.py:520-536`
**Issue:** D-08 and the signed registry (`read2.runs_only_if`) say the 11-08 re-test runs only if the 11-01 read names
no winner. Only the late-descriptive round has a gate (`late_descriptive_status`). For `v4-read2` the guard checks the
instant, the signature and the one-shot subroot, nothing else. I called `check_guard` for `v4-read2` with no read-1
outcome anywhere and it returned FRESH/allowed. If read 1 had named a winner, read 2 could still have been run and
scored. No test covers this.
**Fix:** In `main()` (and ideally `check_guard`), for `v4-read2` read the newest `v4-read1` headline `report.json`
(as `late_descriptive_status` already does) and refuse unless `decision.pick is None`. Add a test for both branches.

### WR-02: Veto record flags are not bound to the source reports they cite

**File:** `backend/forecast_shadow_confirm.py:855-896`
**Issue:** `load_vetoes` verifies that each cited ABLATION/TEST report exists and matches its sha256, but the
`vetoed` booleans in the record are taken from the record itself and never cross-checked against the report content
(`ablation.json["veto"]`, `test_split.json["vetoes"]`). Anyone editing the record can set every `vetoed` to false and the
loader passes, so a vetoed candidate can qualify. The T-07-15 comment ("the report changed after the record was
written") only covers the reverse edit. The record's own sha256 is merely recorded in the output, not compared to
anything.
**Fix:** After the hash check, parse each report and require equality of the veto flags:
```python
report_json = json.loads(open(full, "rb").read())
src = report_json["veto"]["vetoes"] if basis == "ablation" else report_json["vetoes"]
for cand, entry in section["vetoes"].items():
    if bool(src[cand]["vetoed"]) != entry["vetoed"]:
        raise ValueError(f"load_vetoes: {basis!r} {cand!r} vetoed flag disagrees with its source report")
```

### WR-03: Three different "is v4 signed" predicates; the one guarding FRESH reads is the weakest

**File:** `backend/forecast_shadow_eval_core.py:326-344`, `backend/tests/protocol_v4_registry.py:182-188`, `backend/tests/cond02_shadow_golden_test.py:143-145`
**Issue:** `v4_signed()` passes if the first line matching `^- Signature:` has any character other than `_`, space,
tab or CR. It does not require the owner name or the date, does not anchor to the sign-off block (a template or
instruction line such as `- Signature: (to be filled)` earlier in the file would count), and does not bind the signed
text to the registry the code constants are tested against. `protocol_v4_registry.is_signed` requires name, signature and
date. The golden test uses a third variant. The guard that decides whether a FRESH outcome may be computed should be the
strictest, not the loosest.
**Fix:** Make `v4_signed()` reuse one implementation that requires name, signature and date from the sign-off block
(move the parser out of `tests/`), and add a test that a signature line with placeholder text is not accepted.

### WR-04: Frozen artifacts are deserialized without a hash check on the Drake-parity path

**File:** `backend/forecast_shadow_confirm.py:1113-1119,1387-1403`
**Issue:** When any city's production conductor differs from Drake (today: AUSTIN), `main()` builds
`make_headline_loader`, which hash-checks every frozen and refit artifact before `joblib.load`. When no city differs,
`run_kwargs` is empty and `run_confirmation` falls back to `forecast_shadow_pipeline.load_correction_model` directly:
pickles are loaded with no manifest check and the freeze check in `core.provenance` only flags afterwards (PD-16). A
joblib file runs code on load, so the integrity guarantee depends on a config state, not on the loader. Even on the
verified path the frozen hash is checked and the file is then re-opened by path (`:377-383`), which the module
documents as an accepted TOCTOU.
**Fix:** Always use `make_headline_loader(..., frozenset())` for the headline in a FRESH run, and for frozen artifacts
read the bytes once, hash them, and `joblib.load(io.BytesIO(data))` the same bytes (as `_load_verified_refit` already
does).

### WR-05: `write_manifest` re-blesses every `.joblib` in the directory, including tampered ones

**File:** `backend/forecast_conductor_refit.py:129-155,314`
**Issue:** After each `write_refit`, `write_manifest` rehashes all `*.joblib` currently in the directory and overwrites the
manifest. If an earlier artifact was replaced between two refits (the exact case the manifest exists to catch), the next
refit silently makes the swapped file "verified". The manifest becomes trust-on-last-write.
**Fix:** Before rewriting, load the existing manifest and verify every listed file against it; only add entries for
files not yet listed, and refuse on any mismatch.

### WR-06: Credential redaction regressed for key-like names in the public Actions log path

**File:** `backend/dlr_live_run.py:96-100,155-190`
**Issue:** The new `_CREDENTIAL_PARAM_RE` left boundary fixed the `cache_key=` over-masking but dropped masking of any
`..._key=` name that is not `api_key`. Probed with `redact(..., env={})`: `SUPABASE_SERVICE_ROLE_KEY=abc123`,
`access_key=abc`, `private_key=abc`, `aws_secret_access_key=abc` and `sb_publishable_key=abc` all pass through
unmasked; the old pattern masked them via the trailing `key=`. The logs are public (the code says so), and only the four
`REQUIRED_ENV` values are removed by exact match first, so any other secret that a traceback or request URL prints is now
exposed. `jwt=` and `secret=` were never covered.
**Fix:** Mask any name ending in `key`, `token`, `secret` or `password`, keeping the left boundary:
```python
r"(?i)(?<![A-Za-z0-9])([A-Za-z0-9_]*(?:key|token|secret|password)|email)=[^&\s]+"
```
and accept that `cache_key=` is masked (over-masking is the safe direction), or maintain an explicit allow-list. Add
tests for the five names above.

### WR-07: Production conductor ranges are too wide to catch the unit slips they exist for (overstated-ampacity direction)

**File:** `backend/config.py:340-349`
**Issue:** The comment says the ranges guard "a typo or a unit slip". `resistance_ac` accepts 0.005 to 1.0 ohm/km, a
200x window around Drake's 0.0726. The classic slip (ohm/mile entered as ohm/km, factor 1.6) passes, and a too-low
resistance raises computed ampacity, the dangerous direction. `absorptivity` and `emissivity` accept 0.0 (zero solar heating
or zero radiative term), `diameter_m` accepts 0.005 to 0.1 m, `max_temp_c` accepts up to 250 C for a conductor
labelled ACSR. G4 (upper bound 2500 A for AUSTIN) backs this up, but it is a bound on the result, not on the inputs.
**Fix:** Tighten to physically plausible transmission-conductor windows (for example resistance 0.02 to 0.2 ohm/km,
emissivity and absorptivity 0.2 to 1.0, diameter 0.015 to 0.05 m) and add a coherence check between `conductor_type`,
`max_temp_c` and `resistance_ac` (an ACSR entry above about 120 C should be rejected, ACSS above 200 C flagged). Add tests
that 0.1166 (ohm/mile) is rejected for a Drake entry.

### WR-08: B5 fallback is skipped when the ml band is degenerate AND the lookback gap applies; untested

**File:** `backend/city_pipeline.py:136-172`, `backend/tests/city_pipeline_test.py:627-639`
**Issue:** The branch order is `if forecast_degenerate: ... elif gap_reason:`. If the ml forecast is withheld by the lookback
rule and its band also has zero width, the naive fallback never runs and G6 loses the high-side band check, which is exactly
what D-17 is meant to restore. The existing test pins only the unbroken-history case ("a zero-width ml band on an unbroken
history stays withheld"); the combined case is not exercised. A zero-width ml band is irrelevant when ml is withheld for the
gap anyway.
**Fix:** Evaluate the lookback-gap branch first (or make the degenerate check apply only to the band that would be used):
```python
if gap_reason and gap_kind == data_cleaning.GAP_KIND_ML_LOOKBACK and forecast_method == "ml":
    ... naive fallback ...
elif forecast_degenerate: ...
elif gap_reason: ...
```
and add a test with a degenerate ml band on a gapped history.

### WR-09: Live DB rows cannot show whether the naive band gated G6

**File:** `backend/city_pipeline.py:203-219`, `backend/supabase_store.py:635`
**Issue:** `forecast_used_by_g6` now means "the primary forecast fed G6" and is False when the naive band gated. That value is
persisted to `city_rating`. `g6_forecast_method` and `g6_forecast` go only into the in-memory `pipeline` dict and the backfill
trace, so for a live row `forecast_used_by_g6=False` is indistinguishable from "no band checked at all". D-17 asks that the
gating method be visible in the trace and report, and the owner's one unsafe direction is the missing high-side band check;
production monitoring cannot tell the two apart. Downstream `real_data_validation` also counts naive-gated rows as
`n_withheld_gap`.
**Fix:** Persist `g6_forecast_method` (nullable text) with the row, or at minimum into the run log, and have the monitoring
runbook read it; document the new meaning of `forecast_used_by_g6` in the schema doc.

### WR-10: Nothing ties served ml artifacts to the conductor table they were trained under

**File:** `backend/config.py:235-238,457-473`, `backend/dlr_live_check_models.py` (manifest), `backend/forecast_training.py:204-230`
**Issue:** The table comment says a Power Systems answer is "an edit here plus a RATING_CONFIG_VERSION bump, never a code
change". But the `ml` forecast artifacts (and the history lags they consume) are trained under the production conductor
(`forecast_training.city_training_frame` now uses `production_city_point`, and AUSTIN's artifact was retrained at 100 C on
2026-11-02). A later table edit leaves the hashed live artifact trained on the old basis with no check, no metadata and no
warning; the live manifest only hashes files. The effect is mostly availability (more G6 trips to the safe static rating),
but the "no code change" claim hides a required retrain (D-14). Mixed-basis history also straddles a switch (the 30-day
history carries no fingerprint filter).
**Fix:** Store the `config_fingerprint` (or the production-table hash) in a sidecar of each live artifact, have
`dlr_live_check_models.py` fail when it differs from the current resolver output, and correct the comment to name the
retrain step.

## Info

### IN-01: `forecast_gap_kind` duplicates `forecast_gap_reason`'s conditions

**File:** `backend/data_cleaning.py:445-494`
**Issue:** The two functions repeat the same three conditions and rely on a docstring promise that they stay in sync.
**Fix:** Have `forecast_gap_reason` call `forecast_gap_kind` and only format the text.

### IN-02: Stale "provisional" comments and labels after the signed GO

**File:** `backend/config.py:437-451`, `backend/real_data_validation.py:294-295`
**Issue:** The `RATING_CONFIG_VERSION` comment still says the `rating_basis` provisional caveat "is unchanged until a signed
GO in 07-17" although `RATING_BASIS` was rewritten in the same file. `real_data_validation._LABEL` still opens with
"PROVISIONAL (OD-5)". The `v3-powersystems-...` version name also describes values that the source strings attribute to
an Austin Energy teammate relayed by the owner.
**Fix:** Update the comments, and decide whether the validation label and the version name should change.

### IN-03: COND-02 golden test depends on git state and exact library versions

**File:** `backend/tests/cond02_shadow_golden_test.py:98-145`
**Issue:** `test_frozen_sources_are_unchanged_since_baseline` shells out to git (needs commit `d71c501` present, fails on any
untracked file under `data/shadow/models`, including a stray `.DS_Store`), and `test_versions_match_the_capture` fails on any
Python patch release. Both are deliberate ("fails, never skips") but no CI workflow runs pytest, so the protection only
exists on developer machines and breaks there for unrelated reasons.
**Fix:** Run this file in CI with `fetch-depth: 0`, ignore `.DS_Store`, and compare Python major.minor only.

### IN-04: CLI reports post-guard `ValueError` as a clean "refused"; global config mutation in the frame provider

**File:** `backend/forecast_shadow_confirm.py:229-250,1409-1411`
**Issue:** `main()` maps any `ValueError` (including one raised after `new_evidence_dir` has spent the one-shot, for example
from `core.provenance`) to `refused: ...` exit 2, which reads as "nothing happened". `production_frame_provider` also swaps
the process-global `config.FORECAST_EXPERIMENT_CACHE_DIR` and restores it in `finally`, which is not safe if two providers
ever run in one process.
**Fix:** Distinguish pre-guard refusals from post-guard failures in the message (state that the one-shot is spent), and pass
the cache directory explicitly instead of mutating config.

---

_Reviewed: 2026-11-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
