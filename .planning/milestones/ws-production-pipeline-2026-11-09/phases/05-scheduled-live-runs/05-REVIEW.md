---
phase: 05-scheduled-live-runs
reviewed: 2026-10-26T00:00:00Z
depth: standard
files_reviewed: 27
files_reviewed_list:
  - .github/workflows/dlr_live.yml
  - .github/workflows/supabase_smoke.yml
  - .gitignore
  - backend/backfill_archive.py
  - backend/city_pipeline.py
  - backend/dlr_live_check_models.py
  - backend/dlr_live_run.py
  - backend/dlr_live_window_check.py
  - backend/dlr_orchestrator.py
  - backend/dlr_pipeline.py
  - backend/DLRSafetyMonitor.py
  - backend/live_run_log.py
  - backend/observation_composer.py
  - backend/tests/backfill_archive_test.py
  - backend/tests/city_pipeline_test.py
  - backend/tests/dlr_live_check_models_test.py
  - backend/tests/dlr_live_run_test.py
  - backend/tests/dlr_live_runbook_test.py
  - backend/tests/dlr_live_window_check_test.py
  - backend/tests/dlr_live_workflow_test.py
  - backend/tests/dlr_orchestrator_test.py
  - backend/tests/live_log_hygiene_test.py
  - backend/tests/live_run_log_test.py
  - backend/tests/observation_composer_test.py
  - backend/tests/supabase_smoke_test.py
  - data/models/LIVE_ARTIFACT_HASHES.sha256
  - docs/data-science/schema/city_rating_v1.md
findings:
  critical: 0
  warning: 0
  info: 11
  total: 11
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-10-26
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Original review covered the Phase 5 diff (`fde51cd..HEAD`) of the live runner, run log, model
pre-flight, window check, workflow and supporting edits. This pass is an incremental re-review of the
four files changed by the fix commits e7cddb4 (WR-01), 9b38480 (WR-03) and c47686d (WR-02):
`dlr_live_run.py`, `dlr_live_window_check.py` and their two test modules (38 tests pass).

All three warnings are confirmed fixed and are removed:

- WR-01: `_cell` now keeps the last 120 characters behind a `...` marker. Redaction runs before the
  cut, so a secret cannot be half-cut into view, and the test confirms the exception line of a
  traceback ends the cell.
- WR-02: `_is_drill` reads the `fault_injected` flag that `live_run_log.build_run_row` stores per
  failed city. Drill runs are routed to a separate list, so they neither complete a slot nor produce
  `failed-visible`; their rating rows still count toward OD-7 overwrite tolerance and their minutes are
  still billed. A drill alone in an hour gives `missing`, a drill beside a good run leaves it `ok`,
  and a red non-drill run still gives `failed-visible` (all covered by new tests). `pipeline_run` is
  keyed by `run_id` alone, so a re-run attempt replaces the row and `rows_by_id` is unambiguous.
- WR-03: `_emit` redacts both child streams with `limit=None`; the cut is skipped only there, and every
  other caller keeps the 1000-character tail. No regression found in `redact`'s secret ordering.

No critical issue and no new warning was found. Two new info items cover a side effect of the WR-03
fix and two small gaps around the WR-02 drill detection. IN-01 to IN-09 were spot-checked against the
current source and all still apply; line references in the in-scope files were updated for the
shifted code.

## Info

### IN-01: A child that fails after its row was written is recorded as "no rating row"

**File:** `backend/dlr_live_run.py:235-236`, `:233-234`
**Issue:** `classify` treats any non-zero exit or timeout as `written: False`, and the schema doc
says `error`/`timeout` mean "no row was written". The child writes its rating inside the per-city loop
and exits non-zero afterwards for unrelated reasons (`summarize` raising after `write_rating`, which
is recorded as an error with the row already stored; `_print_report` or the `--output` dump failing;
`store.close()` hanging into the timeout). The run log then states a falsehood for the city, and it is
the only record. The slot still shows red, so no gap is hidden.
**Fix:** Word the field as "no confirmed row" in the doc and runbook, or have the child write the
`--output` file before the report print so `classify` can recover `archived` from it on a non-zero exit.

### IN-02: Provider errors and sources of a failed city are dropped

**File:** `backend/dlr_live_run.py:235-243` vs `:252-253`
**Issue:** `provider_errors` and `sources` are filled only in the `ok` branch. A failed child that
exited 1 still wrote `--output` with both. The city's `error` text is kept, but the per-provider counts
(for example 3 NSRDB failures before the breaker opened, as in the 2026-10-19 run) never reach
`pipeline_run`, though that row is the failed city's only record (OD-9).
**Fix:** Read `output.get("provider_errors")` and `output.get("sources")` whenever `output` is a dict,
before the failure branches, and apply `_redact_counts`.

### IN-03: The health predicate and run constants are duplicated across modules

**File:** `backend/dlr_live_run.py:46-47,258-263`, `backend/live_run_log.py:43-44,82-86`
**Issue:** `_healthy` (runner, drives the exit code) and `live_run_log._is_healthy` (drives
`cities_ok`/`cities_failed`) are two copies of one rule, and `supabase_store` holds a third. `PROVIDER`
and `FORECAST_METHOD` are also defined in both modules: the runner's copy builds `child_argv`, the
other fills the run row. If either drifts, the exit code and the run log disagree.
**Fix:** Make `live_run_log.is_healthy` public and call it from the runner; import `PROVIDER` and
`FORECAST_METHOD` from one place.

### IN-04: `--end` accepts a future slot, and `--timeout-s` is unchecked

**File:** `backend/dlr_live_run.py:468-473`, `:482-483`
**Issue:** `_end_arg` only checks the format. `--end 2030-01-01T00:00:00Z` would rate a future hour
with no weather, write static-fallback rows with a future `valid_time` into the consumer-readable
`city_rating`, and the CLI offers it for re-running missed slots. `--timeout-s 0` or a negative value
turns every city into an instant `timeout`.
**Fix:** In `_end_arg`, reject an end later than now (UTC); give `--timeout-s` a positive-integer `type`.

### IN-05: `--start ""` in the window check raises AttributeError instead of a usage error

**File:** `backend/dlr_live_window_check.py:321-328`
**Issue:** `_ts("")` returns `None`, then `parsed.minute` raises `AttributeError`, which argparse does
not catch (reproduced). `--start` is the one required argument the owner types for the sign-off.
**Fix:** `if parsed is None: raise argparse.ArgumentTypeError("--start is required, e.g. 2026-10-25T00:00:00Z")`.

### IN-06: Step-summary cell escaping can be defeated, and child stdout can carry workflow commands

**File:** `backend/dlr_live_run.py:423-432`, `:266-283`
**Issue:** `_cell` replaces `|` with `\|` after truncation, so text ending in a backslash before a pipe
(`a\|b`) becomes `a\\|b`, which markdown reads as an escaped backslash plus a real column separator
(reproduced again after the WR-01 change). Separately, `_emit` writes child stdout at line starts, where
Actions interprets `::stop-commands::`, `::add-mask::` and similar. The child prints
`ERROR <city>: <message>`, and a message built from a remote response containing a newline could place
such a line there.
**Fix:** Escape backslashes before pipes in `_cell`. In `_emit`, prefix any line that starts with `::`
(or wrap output in a `::stop-commands::<token>` pair).

### IN-07: `RED_CONCLUSIONS` omits `startup_failure`, `action_required` and `stale`

**File:** `backend/dlr_live_window_check.py:57`, `:202-207`
**Issue:** A run that cannot start (broken workflow, a `production` environment that needs approval)
shows as failed in the Actions UI, but is classified `missing` ("nothing shows the slot was
attempted"). This fails the window rather than passing it, so it is the safe direction, but the note
text is wrong and the sign-off would report a missing slot where the run was in fact visible.
**Fix:** Add `startup_failure` (and decide on `action_required`/`stale`) to `RED_CONCLUSIONS`, or word
the `missing` note to name the conclusion.

### IN-08: Skipped runs are counted as billed minutes

**File:** `backend/dlr_live_window_check.py:128-139`
**Issue:** `_minutes_summary` takes every placed run with a conclusion, so a `skipped` run (a
non-main dispatch stopped by the `if:` guard) adds a "1 minute" sample. It is not billed, and it
lowers the median that the runbook's 30-day projection uses.
**Fix:** Exclude `conclusion == "skipped"` from the minutes list.

### IN-09: The model manifest has no repo-level guard, and `--write-manifest` drops the header comment

**File:** `backend/dlr_live_check_models.py:162-179`, `backend/tests/dlr_live_check_models_test.py`
**Issue:** Every test builds stand-in artifacts under `tmp_path`; none runs `check(load=False)` on the
committed files. A local retrain overwrites the tracked joblib files (the carve-out in `.gitignore`
tracks them, so the change shows up in `git status`), and a mismatch is first found by a red hourly
run. Also, `write_manifest` writes only the hash lines, so regenerating the manifest silently removes
the `# 2026-10-24 ...` header that tells the next person how it was made.
**Fix:** Add one test that runs `preflight.check(load=False)` against the repo's committed manifest and
files. Have `write_manifest` emit a `# <date> SHA-256 of the models promoted ...` header line.

### IN-10: The WR-03 redaction masks ordinary child log text (`cache_key=`, `monkey=`)

**File:** `backend/dlr_live_run.py:96`, `:277-279`
**Issue:** `_CREDENTIAL_PARAM_RE` has no left boundary, so once it runs over the whole child stdout and
stderr it rewrites any `...key=value`, `...token=value`, `...email=value` or `...password=value` in
ordinary diagnostic lines (reproduced: `monkey=1`, `cache_key=abc` and `max_key=5` become `=***`). The
fixer noted this side effect. It cannot leak anything, but it can hide a non-secret value from the
only log of a failed hourly run. `redact()` for the bounded record fields was always lossy in the same
way; for the raw stream the loss is new.
**Fix:** Accept it and say so in the runbook, or tighten the pattern for the stream path with a left
boundary, for example `(?i)(?<![A-Za-z0-9_])(token|api_key|apikey|key|email|password)=[^&\s]+`, which
keeps `?token=` and `&api_key=` masked and leaves `cache_key=` alone.

### IN-11: Drill detection depends on a saved `cities_failed` entry, and the runbook still describes the old semantics

**File:** `backend/dlr_live_window_check.py:112-117`, `docs/data-science/decisions/dlr_live_runbook.md:427`
**Issue:** `_is_drill` recognises a drill only from a `fault_injected` entry in the run's saved
`cities_failed`. The runner writes the row before the first child with `cities_failed` empty and adds the
drilled city only after its child finishes. A drill that is cancelled or killed by the job timeout
before that city is reached, or one that died before the first row was written, is not recognised and
still counts as `failed-visible`, which is the masking WR-02 closed for the completed case. (Remote and
unlikely: the drill normally finishes in a few minutes.) Separately, the runbook's verdict table
(`failed-visible`: "at least one run is red") does not mention that a fault-drill run is excluded, so
the owner reading it at sign-off will expect the old behavior.
**Fix:** Have the runner record the drill city in the run row from the start (for example a
`fault_city` entry written by the first `save_run_row`) and test that in `_is_drill`; at minimum add the
exclusion sentence to the runbook's `failed-visible` row and the "visible failed run" paragraph.

---

_Reviewed: 2026-10-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
