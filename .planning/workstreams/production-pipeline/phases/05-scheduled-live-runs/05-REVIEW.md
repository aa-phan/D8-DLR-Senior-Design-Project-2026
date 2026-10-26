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
  warning: 3
  info: 9
  total: 12
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-10-26
**Depth:** standard
**Files Reviewed:** 27
**Status:** issues_found

## Summary

Reviewed the Phase 5 diff (`fde51cd..HEAD`) of the live runner, run log, model pre-flight,
window check, workflow and the supporting edits (composer NSRDB skip, safety-monitor logger,
backfill gate capture, orchestrator summary fields). The 12 relevant test modules pass
(139 passed, 5 skipped). The eight committed model hashes match
`data/models/LIVE_ARTIFACT_HASHES.sha256`.

No security vulnerability and no data-loss defect was found. The workflow never lets an input reach
a `run:` script, the secret-holding job is main-only and in `production`, the pre-flight hashes
before it unpickles and gets no secrets, and every SQL value is a bound parameter. The decided
items in the review brief were not re-reported.

Three warnings concern operator-facing correctness: the Actions step summary hides the crash reason
for any uncaught child failure (reproduced), the window check can pass a slot that was never
scheduled because a red fault-drill run stands in for it (reproduced), and the runner re-emits the
children's raw streams outside `redact()`. The info items are small robustness and duplication
points.

## Warnings

### WR-01: Step-summary error cell shows the head of a crash traceback and drops the exception

**File:** `backend/dlr_live_run.py:417-420` (and `:444`; the tail is taken at `:201-202`, `:235`)
**Issue:** For a child that dies with an uncaught exception, `classify` stores
`_tail(stderr_text)` (the last 20 lines of the traceback). `write_step_summary` then passes it
through `_cell`, which flattens it to one line and keeps the FIRST 120 characters. The reason
sits on the last line of a traceback, so it is the part that gets cut. Reproduced with the real
orchestrator and a blank `SYNOPTIC_TOKEN` (exactly the SCHED-01 fault drill): the error cell
reads `Traceback (most recent call last): File "/Users/.../dlr_orchestrator.py", line 411, in <module>`
and never shows `OSError: Set SYNOPTIC_TOKEN ...`. The step summary is the only operator-facing
surface for the drill and for any station-discovery crash, so the failure shows as red with no cause.
(`pipeline_run.error` is not affected: `redact()` keeps the last 1000 characters there.)
**Fix:** Make the summary cell keep the tail, or store the exception line first. For example:
```python
def _cell(text, limit=_SUMMARY_ERROR_CHARS) -> str:
    flat = " ".join(str(text).split())
    if len(flat) > limit:
        flat = "..." + flat[-(limit - 3):]
    return flat.replace("|", "\\|")
```
or, in `classify`, build the stderr-based error as `last_line + " | " + tail`.

### WR-02: A red fault-drill (or any red manual run) satisfies "visible failed run" for a slot that was never scheduled

**File:** `backend/dlr_live_window_check.py:189-191` (verdict), `:148-156` (placement)
**Issue:** The SCHED-01 drill always ends red. `evaluate_window` places every run of the workflow
in a slot by `window_end`/start time and gives the slot `failed-visible` when any run in it is red.
`failed-visible` does not fail the window. If cron-job.org missed a dispatch (the exact fault
SCHED-02 is meant to detect) in an hour in which the owner also ran a drill, or any red manual
dispatch, that slot passes. Reproduced: one `conclusion: failure` run in the slot returns
`failed-visible`, `passed: True`. `event` is fetched in `GH_RUN_FIELDS` but never used, and
cron-job.org dispatches are `workflow_dispatch` too, so the event cannot tell drill from schedule;
the run row can: `cities_failed[<city>]["fault_injected"]` is stored for every drilled city.
**Fix:** Exclude a run whose pipeline_run row has any `fault_injected: true` city from the slot's
evidence (list it in the note instead), so a drill neither completes nor masks a slot:
```python
def _is_drill(row):
    failed = (row or {}).get("cities_failed") or {}
    return any(isinstance(v, dict) and v.get("fault_injected") for v in failed.values())
```
Skip those runs when filling `placed` (or keep them but never count them toward `failed-visible`),
and add a test with a drill run in an otherwise empty slot expecting `missing`.

### WR-03: Child stdout and stderr are re-emitted to the Actions log outside `redact()`

**File:** `backend/dlr_live_run.py:265-277` (called at `:315`)
**Issue:** The module contract (header, "Secrets") is that every error text entering a record or
the step summary goes through `redact()`, and the logs the runner writes itself do. `_emit` writes
the child's captured stdout and stderr verbatim. The repo is public, so these logs are public.
Actions masks only the exact secret values it holds. It does not mask the password component of
`SUPABASE_DB_URL`, the host or project reference, or a URL-encoded form of a credential, all of which
`redact()` or Phase 4's `redact()` handle. Today the child's own log lines are redacted, but an
uncaught traceback (a `requests` error text carries the request URL, for instance) is not, and the
traceback is exactly what the failing-child path emits.
**Fix:** Pass both streams through the runner's redaction line by line, without the 1000-character
cut (add a `limit=None` parameter to `redact`):
```python
def _emit(city, stdout_text, stderr_text, env):
    ...
    if stdout_text:
        sys.stdout.write(redact(stdout_text, env, limit=None))
    if stderr_text:
        sys.stderr.write(redact(stderr_text, env, limit=None))
```

## Info

### IN-01: A child that fails after its row was written is recorded as "no rating row"

**File:** `backend/dlr_live_run.py:234-235`, `:232-233`
**Issue:** `classify` treats any non-zero exit or timeout as `written: False`, and the schema doc
says `error`/`timeout` mean "no row was written". The child writes its rating inside the per-city loop
and exits non-zero afterwards for unrelated reasons (`summarize` raising after `write_rating`, which
is recorded as an error with the row already stored; `_print_report` or the `--output` dump failing;
`store.close()` hanging into the timeout). The run log then states a falsehood for the city, and it is
the only record. The slot still shows red, so no gap is hidden.
**Fix:** Word the field as "no confirmed row" in the doc and runbook, or have the child write the
`--output` file before the report print so `classify` can recover `archived` from it on a non-zero exit.

### IN-02: Provider errors and sources of a failed city are dropped

**File:** `backend/dlr_live_run.py:234-242` vs `:251-252`
**Issue:** `provider_errors` and `sources` are filled only in the `ok` branch. A failed child that
exited 1 still wrote `--output` with both. The city's `error` text is kept, but the per-provider counts
(for example 3 NSRDB failures before the breaker opened, as in the 2026-10-19 run) never reach
`pipeline_run`, though that row is the failed city's only record (OD-9).
**Fix:** Read `output.get("provider_errors")` and `output.get("sources")` whenever `output` is a dict,
before the failure branches, and apply `_redact_counts`.

### IN-03: The health predicate and run constants are duplicated across modules

**File:** `backend/dlr_live_run.py:46-47,257-262`, `backend/live_run_log.py:43-44,82-86`
**Issue:** `_healthy` (runner, drives the exit code) and `live_run_log._is_healthy` (drives
`cities_ok`/`cities_failed`) are two copies of one rule, and `supabase_store` holds a third. `PROVIDER`
and `FORECAST_METHOD` are also defined in both modules: the runner's copy builds `child_argv`, the
other fills the run row. If either drifts, the exit code and the run log disagree.
**Fix:** Make `live_run_log.is_healthy` public and call it from the runner; import `PROVIDER` and
`FORECAST_METHOD` from one place.

### IN-04: `--end` accepts a future slot, and `--timeout-s` is unchecked

**File:** `backend/dlr_live_run.py:455-460`, `:469-470`
**Issue:** `_end_arg` only checks the format. `--end 2030-01-01T00:00:00Z` would rate a future hour
with no weather, write static-fallback rows with a future `valid_time` into the consumer-readable
`city_rating`, and the CLI offers it for re-running missed slots. `--timeout-s 0` or a negative value
turns every city into an instant `timeout`.
**Fix:** In `_end_arg`, reject an end later than now (UTC); give `--timeout-s` a positive-integer `type`.

### IN-05: `--start ""` in the window check raises AttributeError instead of a usage error

**File:** `backend/dlr_live_window_check.py:304-311`
**Issue:** `_ts("")` returns `None`, then `parsed.minute` raises `AttributeError`, which argparse does
not catch (reproduced). `--start` is the one required argument the owner types for the sign-off.
**Fix:** `if parsed is None: raise argparse.ArgumentTypeError("--start is required, e.g. 2026-10-25T00:00:00Z")`.

### IN-06: Step-summary cell escaping can be defeated, and child stdout can carry workflow commands

**File:** `backend/dlr_live_run.py:417-420`, `:265-277`
**Issue:** `_cell` replaces `|` with `\|` after truncation, so text ending in a backslash before a pipe
(`a\|b`) becomes `a\\|b`, which markdown reads as an escaped backslash plus a real column separator
(reproduced). Separately, `_emit` writes child stdout at line starts, where Actions interprets
`::stop-commands::`, `::add-mask::` and similar. The child prints `ERROR <city>: <message>`, and a
message built from a remote response containing a newline could place such a line there.
**Fix:** Escape backslashes before pipes in `_cell`. In `_emit`, prefix any line that starts with `::`
(or wrap output in a `::stop-commands::<token>` pair).

### IN-07: `RED_CONCLUSIONS` omits `startup_failure`, `action_required` and `stale`

**File:** `backend/dlr_live_window_check.py:55`, `:192-196`
**Issue:** A run that cannot start (broken workflow, a `production` environment that needs approval)
shows as failed in the Actions UI, but is classified `missing` ("nothing shows the slot was
attempted"). This fails the window rather than passing it, so it is the safe direction, but the note
text is wrong and the sign-off would report a missing slot where the run was in fact visible.
**Fix:** Add `startup_failure` (and decide on `action_required`/`stale`) to `RED_CONCLUSIONS`, or word
the `missing` note to name the conclusion.

### IN-08: Skipped runs are counted as billed minutes

**File:** `backend/dlr_live_window_check.py:118-129`
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

---

_Reviewed: 2026-10-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
