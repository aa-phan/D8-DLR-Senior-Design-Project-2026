---
phase: 06-exposure-e2e-verification
plan: 04
subsystem: testing
tags: [postgrest, supabase, rest, urllib, stdlib, redaction, e2e, rls, grants]

requires:
  - phase: 06-exposure-e2e-verification
    provides: "latest_rating_contract (LATEST_COLUMNS, STALE_AFTER_MINUTES, is_provisional, age_minutes, is_stale) and the public.latest_rating / assert_fresh migration (06-01)"
provides:
  - "backend/supabase_rest.py: standard-library PostgREST client (config_from_env, redact_rest, request, get_all, count_exact, parse_ts)"
  - "backend/e2e_verify_readonly.py: --check-read, --check-hidden, --check-writes operator checks with --json-out evidence"
  - "backend/tests/fake_postgrest.py: in-process PostgREST fake (1000-row cap, revoked / rls_only / open write modes, hooks) for 06-06 and 06-08"
  - "backend/tests/e2e_readonly_test.py: 30 test functions (57 cases), all offline"
affects: [06-05, 06-06, 06-08, 06-09, 06-12, 06-13]

# Actuals (#2632): same estimateTokens scale (chars/4 over the realized diff)
actuals:
  tokens: 24000
  tasks: 2
  commits: 2
plan_head_before: 29abd53fc9505ff7b3d1985abdbe57a7f2b61c68
plan_head_after: 489b0a89cbd906295f231546d0f6c103428747c4

tech-stack:
  added: []
  patterns:
    - "Redact every printed line, error and evidence value against the environment-held URL, host, project reference and key (REST twin of supabase_store.redact)"
    - "Pass only on the privilege-layer error (401/403 + 42501 + permission denied) AND an identical before/after SHA-256 snapshot; never on a status code alone"
    - "In-process HTTP fake of PostgREST with request recording, so client and checks are proven against real sockets, no network"
    - "Network failures raised outside the except block so no exception context carries the URL"

key-files:
  created:
    - backend/supabase_rest.py
    - backend/e2e_verify_readonly.py
    - backend/tests/fake_postgrest.py
    - backend/tests/e2e_readonly_test.py
  modified: []

key-decisions:
  - "A table write passes only on HTTP 401 or 403 with code 42501 and 'permission denied'; 42501 with 'row-level security' is its own failure (a write grant is still present); every 2xx fails, including 200 with an empty list and 204"
  - "The snapshot covers every city_rating row older than the current UTC hour minus one hour, so the live hourly upsert (OD-7, current-hour slot) cannot move it; the only benign writers are a backfill load and a manual past-slot re-run, which the failure text names"
  - "View PATCH and DELETE name the old target row (city and valid_time), not just the city, so even a view that became updatable could not change a current rating"
  - "check_writes is off unless --check-writes is given; --check-read and --check-hidden are the defaults"

patterns-established:
  - "Uniform check signature fn(cfg, opener=None, now=None, lines=None, attempts=None) -> list[CheckResult]; main prints lines before the verdicts (RECOVERY after them) and writes redacted JSON evidence"
  - "Test plants (URL, host, 20-character reference, keys, JWTs) built from pieces at runtime so secret_scan_test.py never matches the test file"

requirements-completed: [API-01, E2E-03]

coverage:
  - id: D1
    description: "Standard-library REST client: env-only config refusing secret keys and service_role tokens before any request, apikey-only header, error statuses as values, paging that stops only on an empty page, count=exact, Python 3.7+ timestamp parsing"
    requirement: API-01
    verification:
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_secret_or_service_role_key_is_refused_before_any_request"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_get_all_pages_until_an_empty_page"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_parse_ts_fractions_and_offsets"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_requests_carry_the_key_only_in_the_apikey_header"
        status: pass
    human_judgment: false
  - id: D2
    description: "--check-read proves one current rating per city with the 34 documented columns, whole-hour valid_time, is_stale / is_provisional consistent, count=exact 4, keyless refused, assert_fresh 200/503, through main() against the fake"
    requirement: API-01
    verification:
      - kind: integration
        ref: "backend/tests/e2e_readonly_test.py#test_tracer_check_read_end_to_end"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_check_read_failures"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_stale_flag_boundary_is_strictly_more_than_90"
        status: pass
    human_judgment: false
  - id: D3
    description: "--check-hidden: pipeline_run and ops.freshness_log must answer 401/403/404/406; any 2xx, even an empty list, fails"
    requirement: API-01
    verification:
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_check_hidden_verdicts"
        status: pass
    human_judgment: false
  - id: D4
    description: "--check-writes (E2E-03): seven public-key write attempts pass only on privilege-layer refusal, plus an identical before/after snapshot; RLS-only, accepted, inconclusive and data-changing cases fail; RECOVERY printed, never executed"
    requirement: E2E-03
    verification:
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_check_writes_passes_when_writes_are_refused_by_privilege"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_rls_only_rejection_fails"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_accepted_writes_fail_and_print_recovery"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_change_before_the_cutoff_fails"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_snapshot_pages_and_cross_checks_the_count"
        status: pass
    human_judgment: false
  - id: D5
    description: "No output line, exception message or --json-out file holds the project URL, host, project reference or key, including when a network error or an HTTP error body echoes them"
    requirement: API-01
    verification:
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_errors_and_json_out_never_leak_url_or_key"
        status: pass
      - kind: unit
        ref: "backend/tests/e2e_readonly_test.py#test_writes_json_out_has_no_url_or_key"
        status: pass
    human_judgment: false
  - id: D6
    description: "The live runs (hosted gateway maps the publishable key to anon, hosted status codes for privilege errors) are NOT done here; they are 06-09, 06-12 and 06-13"
    requirement: E2E-03
    verification: []
    human_judgment: true
    rationale: "Per D-06 this plan is offline; only the owner's live run shows how the hosted gateway answers (401 vs 403 for a privilege error is an open assumption)"

# Metrics
duration: 10min
completed: 2026-10-26
status: complete
---

# Phase 6 Plan 04: Consumer-side REST checks Summary

**Standard-library PostgREST client, an in-process fake of PostgREST, and `e2e_verify_readonly.py` with read, hidden-table and write-rejection checks: a write passes only on a privilege-layer refusal AND a byte-identical before/after snapshot, and no URL, host, reference or key is ever printed. Nothing contacted the live project.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-10-26T20:30:56Z
- **Completed:** 2026-10-26T20:41:00Z
- **Tasks:** 2 (1 tracer, 1 auto/tdd)
- **Files modified:** 4 (4 created)

## Accomplishments

- **Client** `backend/supabase_rest.py` (standard library only; the import check prints `[]`): `config_from_env` reads `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (D-10), strips whitespace and a trailing slash, names a missing variable and never its value, and refuses a key starting `sb_` + `secret_` or a JWT whose role is `service_role` before any request. `request` sends the key in `apikey` only and returns HTTP error statuses as values; a URLError or timeout becomes a redacted `RestError` with no chained exception. `get_all` advances the offset by the rows received and stops only on an empty page, so it still returns 2500 rows from a server capped at 400. `parse_ts` accepts `Z`, `+00`, `+0000`, `+00:00`, `-05:00` and 0 to 6 fractional digits.
- **Fake** `backend/tests/fake_postgrest.py`: `FakePostgrest` on 127.0.0.1 (context manager, `url`, recorded `requests`), a 1000-row cap, `latest_rating` computed with the real contract, `city_rating` filters / order / paging / `count=exact`, `assert_fresh` 200 or 503 PT503, hidden tables, and three write modes: `revoked` (401 42501 permission denied), `rls_only` (INSERT 401 row-level security, PATCH and DELETE 200 `[]`) and `open` (writes applied). Overrides and a `before_request` hook let a test change rows between two calls. `make_rating_rows` builds 31-column rows with the real config labels.
- **Verifier** `backend/e2e_verify_readonly.py`: `--check-read` (nine named checks), `--check-hidden` (public.pipeline_run, ops.freshness_log via Accept-Profile), `--check-writes` (off by default) and `--json-out`. Exit codes 0 / 1 / 2. `LATEST_COLUMNS` is imported from `latest_rating_contract`; an AST test proves no local copy exists.
- **What each check proves, in plain English:** read, "a person with only the public key sees exactly one current rating per city, with the documented columns"; hidden, "the private run log and the soak log cannot be read with the public key"; writes, "trying to add, change or delete data with the public key is refused, and the data afterwards is identical".
- **Mutation spot-check** (source mutated, suite re-run, file restored): 13 mutations. Twelve killed at once (accepting any 2xx as a refusal, skipping the second snapshot comparison, dropping the RLS-only verdict, stopping paging on a short page, always sending the key, allowing secret and service_role keys, passing a keyless 2xx, dropping host redaction, dropping config-derived redaction, skipping the empty-table guard). One survived, the stale-flag boundary (`age > 90` mutated to `age >= 90`); it is now killed by `test_stale_flag_boundary_is_strictly_more_than_90` (exactly 90 is fresh, 91 is stale).

## Task Commits

1. **Task 1 (tracer): stdlib REST client, in-process fake PostgREST, and the read and hidden-table checks run end to end through main()** - `df5c9f7` (feat)
2. **Task 2: anon write-rejection check with an unchanged-snapshot proof (E2E-03)** - `489b0a8` (feat)

**Plan metadata:** committed with this SUMMARY (docs: complete plan).

Tracer gate: `type="tracer"` without `gate="blocking-human"` and an automated-only `<verify>`, so the tracer verify was re-run end to end (35 passed) and expansion continued with no checkpoint.

## Files Created/Modified

- `backend/supabase_rest.py` - stdlib PostgREST client, redaction, timestamp parsing
- `backend/e2e_verify_readonly.py` - the three checks and the CLI
- `backend/tests/fake_postgrest.py` - in-process PostgREST fake and row factory
- `backend/tests/e2e_readonly_test.py` - 30 test functions, 57 cases

## Interfaces as built

**`supabase_rest`**: constants `ENV_URL`, `ENV_KEY`, `PAGE_SIZE=1000`, `USER_AGENT="dlr-e2e-verify/1.0"`, `SECRET_KEY_PREFIX`, `PUBLISHABLE_KEY_PREFIX`; `ConfigError`, `RestError`; `RestConfig(base_url, key)`; `Response(status, headers, text).json()`; `config_from_env(env=None)`; `redact_rest(text, cfg=None, env=None, limit=300)` (`limit=None` keeps the whole text); `request(cfg, method, path, params=None, headers=None, body=None, profile=None, timeout=30, opener=None, send_key=True)`; `brief(response, cfg=None, limit=160)`; `get_all(cfg, path, params, order, page_size=1000, opener=None, profile=None)`; `count_exact(cfg, path, params, opener=None, profile=None)`; `parse_ts(s)`.

**`e2e_verify_readonly`**: `CheckResult(name, ok, detail)`, `EXPECTED_CITIES`, `HIDDEN_TARGETS`, `SENTINEL_CITY="AUSTIN"`, `SENTINEL_VALID_TIME="2000-01-01T00:00:00Z"`, `SENTINEL_RUN_ID="e2e-03-sentinel"`, `WRITE_PREFER="return=representation"`, `Snapshot(count, digest, target)`, `SnapshotError`, `snapshot(cfg, cutoff, opener=None)`, `check_read`, `check_hidden`, `check_writes`, `CHECKS` (`read`, `hidden`, `writes`), `main(argv=None, opener=None, now=None)`. CLI: `--check-read`, `--check-hidden` (both on when no check flag is given), `--check-writes` (only when given), `--json-out PATH` writing `{"checks": [{name, ok, detail}], "attempts": [{name, method, path, status, code, verdict}], "exit_code": n}`. Check names: `latest_rating_readable`, `latest_rating_four_cities`, `latest_rating_columns`, `latest_rating_values`, `latest_rating_flags`, `latest_rating_count_exact`, `city_rating_readable`, `keyless_request_refused`, `assert_fresh_answers`, `hidden:public.pipeline_run`, `hidden:ops.freshness_log`, `snapshot_before`, `write:table_insert|table_upsert|table_patch|table_delete|view_insert|view_patch|view_delete`, `snapshot_unchanged`.

**`fake_postgrest`**: `FakePostgrest(rows, key, max_rows=1000, now, fresh=True, write_mode="revoked", rpc_available=True, require_key=True, latest_override, route_overrides, table_write_response, view_write_response, count_override, before_request)`, `.latest_view_rows()`, `make_rating_rows(slots, cities=config.LOCATIONS, newest=None, **overrides)`.

## Decisions Made

- Followed the plan's verdict rules exactly (see key-decisions). The view PATCH and DELETE additionally name the old target row's `valid_time` (Rule 2 safety refinement, see Deviations).
- Output order: city lines, then verdicts, then (for `--check-writes` only) the RECOVERY block, so the owner reads the verdict before the repair steps.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] View PATCH and DELETE also filter on the target's valid_time**
- **Found during:** Task 2 design (threat T-06-13, "never damage production on a misconfigured project")
- **Issue:** the plan filters the view writes by city only. If a project ever made `latest_rating` updatable, a city-only PATCH would change that city's CURRENT rating by +1 A, the very row consumers read.
- **Fix:** the view PATCH and DELETE name the same old row as the table attempts (`city` and the target's `valid_time`). The view never shows that row, so even an updatable view could not alter a current rating; the verdict is unchanged (any 2xx fails).
- **Files modified:** backend/e2e_verify_readonly.py, backend/tests/e2e_readonly_test.py (asserts the city filter)
- **Committed in:** 489b0a8

**2. [Rule 2 - Missing critical] Extra tests beyond the plan's list (30 functions instead of 23)**
- **Added:** `test_a_clean_fake_passes_every_read_check`, `test_an_anon_jwt_and_a_publishable_key_are_accepted`, `test_config_from_env_strips_the_value_and_a_trailing_slash`, `test_check_hidden_default_fake_hides_both_tables`, `test_count_exact_reads_the_total_after_the_slash`, `test_redact_rest_removes_url_host_reference_and_both_key_kinds`, and `test_stale_flag_boundary_is_strictly_more_than_90` (the last one because the `>` to `>=` mutation survived).
- **Committed in:** df5c9f7, 489b0a8

**3. Attribution line.** The plan asked for `Co-Authored-By: Claude Opus 5.5`; the commits carry the session's attribution lines (`Claude Sonnet 5.5` plus the session link) per the executor instructions, as in 06-01.

### TDD note (Task 2)

Tests were written before the implementation and run: 18 of the new tests failed for the intended reason (`check_writes`, `snapshot`, `SnapshotError` and the `--check-writes` flag did not exist; the fake had only the `revoked` mode), and the 35 Task 1 tests still passed. The implementation then turned all green (53), and the boundary test took it to 57. As in 06-01, the plan asks for one commit per task, so there is no separate RED commit. Task 1 was written test-first as well (collection failed with `ModuleNotFoundError` for the two new modules).

---

**Total deviations:** 2 auto-added (Rule 2), 1 attribution wording note.
**Impact on plan:** no scope creep; every truth in `must_haves` is covered by a named test.

## Discrepancies

- **Signatures widened, never narrowed.** `request()` gained a trailing `send_key=True` (the keyless-refusal check needs a request with no `apikey`). `main()` gained `opener=None, now=None`. Every check function takes the same `(cfg, opener=None, now=None, lines=None, attempts=None)`; `check_read` and `check_hidden` ignore `now` and `attempts`. `get_all` and `count_exact` gained an optional `profile`. `redact_rest(limit=None)` keeps the whole text (needed for JSON evidence and the RECOVERY block).
- **`snapshot()` returns `Snapshot(count, digest, target)`**, not the row list: only the first row is needed, and keeping every row would grow with the table.
- **Hosted behaviour is still an assumption.** The plan's flagged assumption (hosted PostgREST may answer a privilege rejection with 401 or 403) is accepted in both forms. Whether the hosted gateway maps the publishable key to the `anon` role exactly as the local role test does is proven only by 06-09's live `--check-read`. Local PostgREST itself was not run in this plan (the fake follows the 06-RESEARCH status map).
- **The secret-scan pattern for the project host** matches a 20-character reference. `redact_rest` matches the same shape plus the host and reference taken from the environment, so a reference of any length that is in `SUPABASE_URL` is also removed.

None other.

## Issues Encountered

None blocking. The full default suite (`.venv/bin/python -m pytest -q -p no:cacheprovider`) reported 1830 passed, 60 skipped (the skips are the local-Postgres tests without the autostart flag), 0 failed. Pre-existing working-tree changes (.DS_Store files, `.planning/config.json`, untracked `.obsidian/`, `graphify-out/`, etc.) were left unstaged. The `__main__` entry point of `e2e_verify_readonly.py` was not executed here because it calls `load_dotenv`, which would read the owner's `.env`; `main()` is covered through the tests instead.

## Known Stubs

None. No placeholder text, empty-value-to-UI paths or unwired data in the files this plan created.

## Threat Flags

None. The tool's write attempts, the sentinel key, the printed recovery statements and the redaction are exactly the surface in the plan's threat model (T-06-12 to T-06-15); T-06-SC stays accepted (standard library only, no install).

## User Setup Required

None - no external service configuration required. The live runs (`--check-read --check-hidden` in 06-09, `--check-writes` with no backfill or past-slot re-run in progress, and the post-2026-10-30 re-check) are the owner's steps in later plans. Nothing was pushed and nothing contacted the Supabase project.

## Next Phase Readiness

- Ready for 06-05 onward. `fake_postgrest.py` is ready for 06-06 (examples) and 06-08 (E2E trace); `supabase_rest.py` is the client for them.
- API-01 and E2E-03 stay open in REQUIREMENTS.md on purpose: later plans (06-06, 06-09, 06-12, 06-13) also declare them and their live halves are the owner's runs.
- For the live run: the owner needs `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` exported in the shell (never a committed file), and must not run a backfill load or a manual past-slot re-run while `--check-writes` runs.

## Self-Check: PASSED

- Files present: `backend/supabase_rest.py`, `backend/e2e_verify_readonly.py`, `backend/tests/fake_postgrest.py`, `backend/tests/e2e_readonly_test.py` (all FOUND).
- Commits `df5c9f7` and `489b0a8` are ancestors of HEAD; `git rev-list --count 29abd53..HEAD` measured 2 at SUMMARY time.
- Acceptance criteria re-run: `supabase_rest.py` imports only standard-library modules (`[]`, exit 0); `load_dotenv()` appears once, inside the `__main__` block; `latest_rating_contract` appears 5 times in the verifier; `def check_writes(` 1, `2000-01-01T00:00:00Z` 2 times, `rls_only` 4 times in the fake; 30 test functions (at least 23).
- Verify commands: `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/e2e_readonly_test.py` 57 passed; full suite 1830 passed, 60 skipped, 0 failed.
- `git status --porcelain -- data/shadow .github/workflows/shadow_collect.yml` prints nothing; nothing pushed; nothing contacted the live project.

---
*Phase: 06-exposure-e2e-verification*
*Completed: 2026-10-26*
