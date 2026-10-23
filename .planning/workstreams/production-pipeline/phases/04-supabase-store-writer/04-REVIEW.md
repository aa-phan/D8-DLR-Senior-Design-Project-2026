---
phase: 04-supabase-store-writer
reviewed: 2026-10-23T23:30:00Z
depth: standard
files_reviewed: 20
files_reviewed_list:
  - .github/workflows/supabase_smoke.yml
  - backend/city_pipeline.py
  - backend/dlr_orchestrator.py
  - backend/rating_identity.py
  - backend/supabase_load_backfill.py
  - backend/supabase_smoke.py
  - backend/supabase_store.py
  - backend/tests/city_pipeline_test.py
  - backend/tests/rating_identity_test.py
  - backend/tests/supabase_live_test.py
  - backend/tests/supabase_load_backfill_test.py
  - backend/tests/supabase_migration_test.py
  - backend/tests/supabase_orchestrator_test.py
  - backend/tests/supabase_run_log_test.py
  - backend/tests/supabase_smoke_test.py
  - backend/tests/supabase_store_test.py
  - docs/data-science/decisions/supabase_store/smoke_actions_review_fixes.json
  - docs/data-science/decisions/supabase_store/smoke_review_fixes.json
  - docs/data-science/schema/city_rating_v1.md
  - supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql
findings:
  critical: 0
  warning: 1
  info: 4
  total: 5
status: issues_found
---

# Phase 4: Code Review Report (re-review after gap-closure plans 04-07..04-11)

**Reviewed:** 2026-10-23
**Depth:** standard
**Files Reviewed:** 20
**Status:** issues_found

## Summary

Re-review of the Supabase store, backfill loader, smoke test, workflow, migration and the orchestrator / pipeline changes after the twelve prior findings were fixed. All twelve are resolved in the current source (see the table below). The related test set passes locally (148 passed, 48 skipped; the skips are the live-Postgres tests that need `DLR_TEST_PG_AUTOSTART=1`). The two workflow action pins resolve to the commits their comments name (`git ls-remote`: `actions/checkout` v4.4.0 -> `11d5960a...`, `actions/setup-python` v5.6.0 -> `a26af69b...`). The committed evidence JSON holds no host, URL, project reference or credential.

No new critical issue. The reconnect logic (`_with_reconnect`), the child-process fingerprint isolation, the UTC hour CHECK and its smoke probe, and the backfill de-duplication rank all trace correctly, including the failure and retry edges. One new warning: the per-city exception text is redacted for the log line and the run row but printed and written to `--output` raw. Four info items concern run-log completeness and hardening.

## Prior Findings Verification

| ID | Status | Evidence |
|----|--------|----------|
| CR-01 | resolved | `backend/supabase_store.py:328` reads the role from `select current_user`; `:342` logs it after `redact(role, secrets + _project_identifiers(url))`. `conn.info.user` is no longer referenced. Failing-first test `supabase_store_test.py` (`test_tracer_postgres_run_logs_the_server_role_not_the_project_reference`) asserts the project reference is absent from caplog, stdout and stderr. |
| WR-01 | resolved | `backend/dlr_orchestrator.py:372-373` returns 1 for any failed city when `--store postgres`; `:374` keeps the CSV rule. Parametrized test `supabase_orchestrator_test.py` `test_main_with_postgres_exits_one_when_any_city_failed` covers postgres, `--no-run-row`, csv and default. |
| WR-02 | resolved | `backend/city_pipeline.py:62-83` records `cleaning_error`; `:101-102` sets `forecast_status = "failed"` when cleaning failed and `total_rows > 0`; `backend/dlr_orchestrator.py:259` carries it to the run record; `backend/supabase_store.py:694-704` classifies the city `degraded` with the redacted error. Residual case (empty history) is IN-08 below. |
| WR-03 | resolved | `backend/supabase_store.py:813-896`: `from_env` supplies a reconnect factory that goes back through `connect()` (settings re-applied); `_with_reconnect` replaces a flagged-lost connection before the call and retries once after a `StoreError` only when `_lost()` confirms the session is gone; a CHECK failure on a healthy connection is not retried; the run context is kept. |
| WR-04 | resolved | `backend/supabase_load_backfill.py:353-357` ranks computed rows ahead of fallback rows with a stable sort, marks `duplicated(keep="first")` over that ranking and maps the mark back by index (the frame index is unique after `read_history`'s `reset_index`). Four-way parametrized test plus `test_backfill_keeps_the_row_the_cleaning_step_keeps_usable` agree with `data_cleaning.clean_history`. |
| WR-05 | resolved | `backend/supabase_load_backfill.py:189-210`: the child imports only `config, city_point, thermal_model, rating_identity`, proves the first three came from the materialized copies and that no other live backend module loaded; `:275-281` surfaces the whole redacted stderr (head and tail past 4000 characters). `backend/rating_identity.py:19-23` imports only `hashlib`, `json`, `city_point`, `config`. Tests cover a config lacking names live modules read at import. |
| IN-01 | resolved | `backend/supabase_store.py:274` gives `redact` a `limit` parameter (default 300); `:659` and `:703` pass `_RUN_ERROR_MAX_CHARS`; `_redact_keys` (`:646-665`) sums counts of keys equal after redaction. |
| IN-02 | resolved | `backend/supabase_store.py:310` assigns the stripped URL before it is used for redaction and for `psycopg.connect`. |
| IN-03 | resolved | `supabase/migrations/20261023000000_...sql:26-27` replace both comments (additive; the original migration is hash-pinned by `test_original_migration_is_unchanged`). Text matches `docs/data-science/schema/city_rating_v1.md:176-177`. |
| IN-04 | resolved | `backend/supabase_load_backfill.py:341,362,387,515` use `supabase_store.finite` and `supabase_store.file_sha256`; `sha256_file` and `_finite` are gone; an AST test forbids private `supabase_store` access from any backend module. |
| IN-05 | resolved | `.github/workflows/supabase_smoke.yml:41,44` pin by 40-character SHA with the version comment (verified against the upstream tags), `:42-43` sets `persist-credentials: false`, `:37` guards the job with `github.ref == 'refs/heads/main'`. The protected-environment control is documented as not configured (owner decision), which is acceptable. |
| IN-06 | resolved | `supabase/migrations/20261023000000_...sql:19-20` rebuilds the CHECK in UTC; `backend/supabase_store.py:326` pins the session zone; `backend/supabase_smoke.py:160-180` probes a +05:30 session in a nested rolled-back savepoint; `smoke_review_fixes.json` shows `session_timezone_utc` and `utc_hour_check_zone_independent` true on the live project. |

## Warnings

### WR-06: Per-city exception text is redacted for the log and run row but printed and written to `--output` raw

**File:** `backend/dlr_orchestrator.py:273` (consumers at `:318-319` and `:364-366`)
**Issue:** In `_run_cities_with_store` the handler logs `supabase_store.redact(exc)` (line 272) and the run row redacts `record["error"]` in `build_run_row`, but `out["errors"][name] = str(exc)` stores the raw text. `_print_report` prints it (`ERROR {name}: {msg}`, printed into the Actions log of the scheduled runner) and `--output` writes `errors` into the JSON summary. `observation_composer._record_error` states in its own comment that a requests error string "can echo a URL, and Synoptic's carries the token"; an exception of that kind escaping `run_city_pipeline` is therefore redacted in two of the three sinks and raw in the other two. The DB-04 redaction contract for this module is "only redacted text reaches a log, message or stored row", and the same inconsistency exists on the CSV path (`:195`). Database errors are already redacted at the source (`StoreError`), so the exposure is the provider token and any URL embedded in a third-party exception.
**Fix:**
```python
except Exception as exc:
    text = supabase_store.redact(exc)
    log.error("city %s failed: %s", name, text)
    out["errors"][name] = text
    record["written"] = False
    record["error"] = text
```
Apply the same `redact` in the CSV branch at line 194-195 (import `supabase_store` lazily or move `redact` to a small shared module), and add a test that an exception whose text holds `token=abc123` reaches neither stdout nor the `--output` file.

## Info

### IN-07: A failed forecast is recorded as a degraded city with no reason

**File:** `backend/city_pipeline.py:88-97`, `backend/supabase_store.py:698-704`
**Issue:** WR-02 added a reason (`cleaning_error`) for a cleaning failure, but a forecast failure (for example `--forecast-method ml` with a missing or corrupt model artifact) still produces `forecast_status = "failed"` with no error text. `build_run_row` then stores `{"outcome": "degraded", "written": true, "forecast_status": "failed", "error": null}` (reproduced with a direct call). The run log exists to explain why a city is unhealthy, and the only trace is a WARNING line in the log. The job also exits 0 (the row was written), so a run where every city has a failed ML forecast stays green with no stored explanation.
**Fix:** Add a `forecast_error` entry to `pipeline` (the exception text from line 91) and set `record["error"]` from `cleaning_error or forecast_error` in the orchestrator; consider exiting non-zero when every written city is degraded.

### IN-08: A cleaning failure on an empty history is dropped from the run row

**File:** `backend/dlr_orchestrator.py:259`, `backend/supabase_store.py:694-697`
**Issue:** When `clean_history` raises on an empty history (`total_rows == 0`), `forecast_status` stays `cold_start` by design (`city_pipeline.py:101`), so the city lands in `cities_ok` (provided a detector model loaded) and the `error` text is never stored: `build_run_row` records `error` only for cities in `cities_failed`. A deterministic cleaning bug that also fires on empty frames would be invisible on every cold start and would first surface as `failed` once history exists. The test `test_cleaning_failure_on_empty_history_stays_cold_start` pins the status but nothing pins that the error is kept. (Today `clean_history` accepts an empty `ARCHIVE_COLUMNS` frame, so this is latent.)
**Fix:** Either classify any city with a non-empty `cleaning_error` as degraded, or log the error at WARNING from the orchestrator regardless of classification and state the choice in the `build_run_row` docstring.

### IN-09: The manifest commit is passed to `git show` without validation

**File:** `backend/supabase_load_backfill.py:217-225` (and `load_manifest`, `:129-134`)
**Issue:** `_git_show` runs `git show f"{commit}:{path}"` where `commit` is `manifest["git"]["head"]` taken verbatim from the manifest. The archive hash is checked against the manifest, but the manifest itself is not authenticated, and a value beginning with `-` (for example `--output=/some/path`) would be read by git as an option. The argv is fixed-form (no shell), the file is a committed owner-run input, so exposure is low; it is a one-line hardening on a tool that runs with the owner's credentials in the environment.
**Fix:** In `load_manifest`, require `re.fullmatch(r"[0-9a-f]{40}", head)` and raise `ValueError` otherwise (a `--` separator cannot precede a revision argument, so validation is the control).

### IN-10: Schema doc states the CSV archive keeps "the first write for an exact instant"

**File:** `docs/data-science/schema/city_rating_v1.md:35`
**Issue:** The archive rule is first write per slot except that a computed row may follow fallback rows and then owns the slot (`historical_archive._slot_archived`, lines 178-203; the WR-04 fix and the loader docstring rely on it). The consumer-facing sentence omits the exception, so a reader comparing the CSV and Postgres rules draws a wrong conclusion for the fallback-then-computed case.
**Fix:** "The offline CSV archive keeps the first computed write for an instant (a computed row may follow fallback rows and then owns the slot; otherwise the first write wins)."

---

_Reviewed: 2026-10-23_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
