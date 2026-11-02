---
phase: 06-exposure-e2e-verification
reviewed: 2026-11-01T00:00:00Z
depth: standard
files_reviewed: 33
files_reviewed_list:
  - backend/e2e_soak_report.py
  - backend/e2e_trace.py
  - backend/e2e_verify_readonly.py
  - backend/latest_rating_contract.py
  - backend/supabase_rest.py
  - backend/tests/e2e_readonly_test.py
  - backend/tests/e2e_soak_report_test.py
  - backend/tests/e2e_trace_test.py
  - backend/tests/example_read_ratings_test.py
  - backend/tests/expose_migration_test.py
  - backend/tests/fake_postgrest.py
  - backend/tests/local_pg.py
  - backend/tests/monitoring_runbook_test.py
  - backend/tests/rest_api_doc_test.py
  - backend/tests/secret_scan_test.py
  - backend/tests/soak_log_migration_test.py
  - backend/tests/supabase_smoke_test.py
  - docs/data-science/decisions/dlr_live_runbook.md
  - docs/data-science/decisions/pss_e_handoff.md
  - docs/data-science/schema/city_rating_v1.md
  - docs/frontend/specs/api-contract.md
  - docs/frontend/specs/F1-data-access-api.md
  - docs/integration/examples/curl.sh
  - docs/integration/examples/read_ratings.py
  - docs/integration/examples/supabase_js.mjs
  - docs/integration/rest-api.md
  - supabase/migrations/20261026195124_expose_latest_rating.sql
  - supabase/migrations/20261026204258_soak_freshness_log.sql
  - supabase/ops/soak_cron_schedule.sql
  - supabase/ops/soak_cron_unschedule.sql
  - supabase/ops/soak_probe_smoke.sql
  - supabase/ops/verify_exposure.sql
  - supabase/ops/verify_monitoring.sql
findings:
  critical: 0
  warning: 6
  info: 6
  total: 12
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-11-01
**Depth:** standard
**Files Reviewed:** 33
**Status:** issues_found

## Summary

Reviewed the exposure migration, the soak-log migration, the owner ops SQL, the REST client, the three E2E tools, the consumer examples, the docs and the Phase 6 tests. The offline suite passes (192 passed, 39 skipped), and the Postgres-backed tests pass too when run with `DLR_TEST_PG_AUTOSTART=1` (55 passed).

I found no write path reachable by `anon`. The migrations take every privilege from `anon` and `authenticated` and then grant `SELECT` on two objects. The view is `security_invoker`, there is one read policy and no write policy, and `ops` is closed to the API roles. A tracked-file grep for keys, JWTs, project hosts and database URLs found nothing. Redaction in the REST client and the trace tool is thorough.

Six warnings remain. They are verification blind spots, one published-text claim that the code contradicts, a read-only guard that overstates what it does, a soak verdict that excuses its own breach condition, and a cleartext-key path. None is an exploitable hole today.

**Migration constraint.** Both Phase 6 migrations are applied and pinned by SHA-256. Nothing below asks for an edit to either file. Any fix that touches the database goes in a NEW additive migration. The ops SQL files under `supabase/ops/` are not pinned or applied by the CLI and can be edited in place.

## Warnings

### WR-01: `verify_exposure.sql` cannot see column-level grants or inherited privileges

**File:** `supabase/ops/verify_exposure.sql:36-50, 105-110, 112-124`
**Issue:** This is the file the owner runs in 06-09, 06-12 and 06-13 to prove "the public roles can read these two objects and nothing else". It builds its grant list only from `pg_class.relacl`. Column-level privileges are stored in `pg_attribute.attacl`, so they never appear.

I reproduced this on a throwaway cluster with the real migrations applied. I ran `grant update (rating_amps) on public.city_rating to anon` and `grant insert (city) on public.city_rating to authenticated`. Every check in `verify_exposure.sql` still returned `ok = true`, and `anon` could then issue `UPDATE ... SET rating_amps` past the privilege layer.

Row-level security would still block the update, because there is no write policy. But the check is documented as the independent proof that privilege is the first lock, and it cannot detect this. It also cannot see a privilege inherited through role membership: the `grants` CTE reads direct ACL entries, and the write-privilege check is only applied to `pipeline_run`.

**Fix:** Edit the ops file. It is not applied by the CLI, so no migration is needed. Add a check that asks the privilege functions directly, which covers columns and membership:
```sql
union all
select 'anon_authenticated_hold_no_write_or_column_privilege_in_public',
       not exists (
           select 1
             from pg_class c
             join pg_namespace n on n.oid = c.relnamespace
            cross join (values ('anon'), ('authenticated')) as r(role)
            where n.nspname = 'public' and c.relkind in ('r', 'p', 'v', 'm', 'f')
              and (has_table_privilege(r.role, c.oid, 'insert, update, delete, truncate, references, trigger')
                   or (c.relname not in ('city_rating', 'latest_rating')
                       and has_any_column_privilege(r.role, c.oid, 'select, insert, update, references'))
                   or has_any_column_privilege(r.role, c.oid, 'insert, update, references'))),
       'write, trigger or column-level privileges held by anon or authenticated (directly or inherited)'
```
Also add a test that plants a column-level grant, as the review reproduction did.

---

### WR-02: Refusal checks can pass for the wrong reason (invalid key, missing table, 5xx)

**File:** `backend/e2e_verify_readonly.py:322-328, 389-395` (constants at 93)
**Issue:** `check_hidden` passes on any of 401, 403, 404 or 406 without looking at the error code.
- Run with an invalid, rotated or revoked key, the Supabase gateway answers 401 `Invalid API key` for every request. Both `hidden:public.pipeline_run` and `hidden:ops.freshness_log` then report `PASS ... not readable`. The same happens if `pipeline_run` is dropped or renamed (404).
- `--check-hidden` alone is the 06-13 re-check path that reports "the private tables cannot be read with the public key". It can return a green result that proves nothing.

`_classify_view_write` treats every non-2xx as "refused", including 500, 502 and 504. A gateway timeout after a committed write would be recorded as a pass.

The table-write classifier is correct, because it requires `42501` plus "permission denied". The view writes and the hidden checks are the weak ones. The test file locks this behaviour in: `e2e_readonly_test.py:502` asserts that status 500 passes a view write.

**Fix:**
```python
# check_hidden: a 401/403 must be a privilege refusal, 404/406 must name the schema or table cache miss
body = _body_of(response) or {}
code = body.get("code")
if response.status in (401, 403) and code == "42501":
    ok = True
elif response.status in (404, 406) and code in ("PGRST205", "PGRST106", "PGRST202"):
    ok = True
else:
    inconclusive  # includes a bare 401 "Invalid API key"

# _classify_view_write: only a 4xx refuses; a 5xx is inconclusive (fail)
if 400 <= status < 500:
    return True, "refused (HTTP %d)" % status, code
return False, "inconclusive: HTTP %d" % status, code
```
Better still, run one cheap authenticated read (the `latest_rating` limit-1 call) at the start of `--check-hidden` and `--check-writes`, so an invalid key fails loudly before any refusal is trusted.

---

### WR-03: Detector exception text is published to `anon`, and the docs say none is stored

**File:** `docs/integration/rest-api.md:131`, `docs/data-science/schema/city_rating_v1.md:15`, with the source at `backend/DLRSafetyMonitor.py:84` and `backend/supabase_store.py:551` (both outside the listed scope but they decide whether the claim is true)
**Issue:** Both docs state that nothing sensitive is stored in the publicly readable history: "no file path, no credential, no error text". But `DLRSafetyMonitor` builds the alert as `f"detector error ({exc})"` from a raw exception. `supabase_store.build_city_row` stores `alerts = [str(a) for a in result["alerts"]]` with no redaction and no length cap. That text lands in `public.city_rating.alerts` and in `latest_rating.alerts`, both readable with the publishable key.

The exception comes from the anomaly detector. Depending on the failure it can carry a file path, a model name or library internals. Every other error path in this codebase (`pipeline_run.cities_failed`) goes through `supabase_store.redact` and a length cap. This one does not, and the published contract promises it.

**Fix:** Fix the writer, not the migration. In `build_city_row`, redact and cap each alert (`supabase_store.redact(str(a), limit=300)`), and have the G6 branch report the exception type only (`f"detector error ({type(exc).__name__})"`). Rows already stored may hold raw text. Check them with a one-off query on `alerts like 'G6%detector error%'`, and correct them with an owner UPDATE. No change to the applied migrations is needed. Until both are done, soften the two doc sentences.

---

### WR-04: The read-only session guard does not hold on a transaction-pooler URL

**File:** `backend/e2e_trace.py:82, 303`, `backend/e2e_soak_report.py:130, 246`
**Issue:** Both tools run `set default_transaction_read_only = on` as a session setting, and the comments say "this session can no longer write". `supabase_store.connect()` opens the connection with `autocommit=True` and explicitly supports a pasted transaction-pooler URL (port 6543).
- On a direct or session-mode URL the guard works.
- Through a transaction pooler, session-level `SET` is not tied to the client connection. The next statement may run on a different backend that never saw the `SET`, so the guard silently does nothing.
- The reverse is a hazard too. The setting can stay on a pooled backend and make a later writer transaction fail with "cannot execute INSERT in a read-only transaction". The existing `set statement_timeout` and `set timezone` in `connect()` share the first problem.

Today every statement is a literal parameter-bound `SELECT`, so nothing is at risk now. The comment overstates the protection, and a later edit that adds a write would not be stopped.

**Fix:** Make read-only a per-transaction property, so it survives pooling:
```python
conn.autocommit = False
conn.read_only = True            # psycopg 3: BEGIN READ ONLY for every transaction
rows = _query(conn, CITY_RATING_SQL, params)   # all reads inside the one transaction
conn.rollback()
```
Alternatively, wrap each read in `with conn.transaction(): conn.execute("set local transaction_read_only = on")`. Reword the comments to say "read-only transaction".

---

### WR-05: The soak "late run" rule explains exactly the breach it detects

**File:** `backend/e2e_soak_report.py:817, 908-912` (rule), `1147` (pass condition)
**Issue:** A write breach exists only when the next advancing row lands more than 90 minutes after the previous slot began. With an hourly cadence that is the same as "written more than 30 minutes after its own slot" (`W - S > 30 min`). `LATE_RUN_MIN` is 30, and the late-run test is `written - slot_time > 30 min`, so the two conditions are identical.

Whenever the breach comes from the next slot's row arriving late, the rule marks it as "explained". The verdict passes when every breach has a cause, so a chronically slow pipeline passes the 72 h soak as long as the late rows keep arriving.

This is the exact failure the dry-soak tool was built to catch (06-RESEARCH Pitfall 9: "the real write lag does not fit the 90-minute freshness budget"). 06-07-SUMMARY records that the 90 min + 2 s cases now exit 0 as "late run". The PASS line is honest ("unless explained"), but the exit code and the 06-12 sign-off read as a pass.

**Fix:** Keep the cause text but do not let it satisfy the pass condition. Count `late run` breaches separately and fail on them unless the owner annotates them, or fail above a stated count or duration:
```python
LATE_ONLY = "late run:"
unexplained = [b for b in breaches
               if not b["explanation"] and (not b["cause"] or b["cause"].startswith(LATE_ONLY))]
```
If the owner deliberately accepts late-run causes as sufficient, say so in the PASS line and the runbook ("N breaches explained only by lateness"). Today the line reads as if they were exceptional.

---

### WR-06: `http://` accepted for any host, the error message says https, and `apikey` follows redirects

**File:** `backend/supabase_rest.py:114-115, 237-245`
**Issue:** `config_from_env` accepts `^https?://`, but the error text says "must start with https://". A mistyped `http://<project>.supabase.co` therefore passes validation and sends the key in clear text.

`urllib.request` follows redirects and copies the request headers to the new location, including `apikey`. A redirect from the service to another host would carry the key along. The key is a publishable key, which lowers the impact, but the tool's own contract is that the key goes only to the project.

**Fix:**
```python
parts = urllib.parse.urlsplit(base_url)
local = parts.hostname in ("127.0.0.1", "localhost", "::1")   # the tests' fake server
if parts.scheme != "https" and not (parts.scheme == "http" and local):
    raise ConfigError("%s must start with https://" % ENV_URL)
```
Also install a redirect handler that refuses redirects (`urllib.request.HTTPRedirectHandler.redirect_request` returning None) when the target host differs.

## Info

### IN-01: The `ops.log_freshness()` comment claims it reads the view "as the calling role"

**File:** `supabase/migrations/20261026204258_soak_freshness_log.sql:38-39, 84`
**Issue:** The function is security invoker and pg_cron runs it as `postgres`, the table owner, which bypasses RLS. I confirmed this on a scratch cluster: after dropping the read policy, `anon` saw 0 rows in `latest_rating`, while `ops.log_freshness()` run as the owner still logged 4 rows with times. So the log shows what the owner sees, not what a consumer sees. The two agree today. A future policy change would make the log disagree with consumers while the breach flag still looks the same.
**Fix:** Do not edit the applied file. Either add a new additive migration with `comment on function ops.log_freshness()` that states the real behaviour, or note it in the runbook. If the log must follow consumer visibility, the probe would need `set local role anon`, which is a new migration.

### IN-02: A malformed `fallback` cell is silently read as false

**File:** `backend/e2e_soak_report.py:371` (strict parser exists at 343-349)
**Issue:** `writes.csv` rows get `row["fallback"] = str(raw["fallback"]).strip().lower() in ("true", "t", "1")`. A corrupt cell such as `ture` becomes false with no error, while the probe `breach` column uses the strict `_bool_cell`. The value is informational (fallback share), but the report's exit code 2 promise for malformed input is not kept here.
**Fix:** `row["fallback"] = _parse(WRITES_FILE, number, "fallback", raw["fallback"], _bool_cell)`.

### IN-03: Report CLI edge cases fail with a traceback or a silent default

**File:** `backend/e2e_soak_report.py:1453-1457, 704-705, 732, 1088`
**Issue:**
- `--out` or `--json-out` in a missing directory raises an uncaught `FileNotFoundError`, after the whole evaluation has run. The tool uses exit 2 for bad input everywhere else.
- `--probe-interval-min 0` gives `ZeroDivisionError` in `probe_findings` (`(until - since) // interval`).
- An annotation `time` without an offset is read as UTC without comment (`_ts` default). That is the same ambiguity the trace tool refuses for `--execution-time`.

**Fix:** Create the output directory (`os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)`), reject a non-positive interval in argparse, and require an offset in annotation times.

### IN-04: `_slot_window` does not match its docstring

**File:** `backend/e2e_soak_report.py:209-213`
**Issue:** The docstring says the slots whose `valid_time` lies in `[since, until)`. The code starts at the hour containing `since`, so a slot before `since` is included. It also floors the count, so a final partial hour (a slot at 14:00 when `until` is 14:30) is dropped. For the aligned windows actually used (`G` on a 5-minute boundary, 72 h) the effect is one extra lead-in slot in the dry verdict list. The statement is still wrong.
**Fix:** Correct the docstring, or compute `hours` from `ceil`/the true slot count.

### IN-05: Consumer examples have small robustness and hygiene gaps

**File:** `docs/integration/examples/read_ratings.py:95-96, 120-125`, `docs/integration/examples/curl.sh:29, 36`, `docs/integration/examples/supabase_js.mjs:50`
**Issue:**
- `read_ratings.py` catches `HTTPError` and `URLError` around `urlopen` but not read-time failures (`ConnectionResetError`, `http.client.IncompleteRead`, a read `socket.timeout`). These end in a traceback, although the header promises a clean exit 1 for "could not be reached". `get_all` has no page cap, unlike `supabase_rest.get_all`, so a service that ignores `offset` loops forever.
- `curl.sh` passes the key as a command-line `-H` argument, which is visible in `ps` to other local users. `CITY`, `START` and `END` are interpolated into the URL with no encoding. A `+00:00` offset in `START` becomes a space and returns a 400.
- `supabase_js.mjs` only compares the row count to 4 and does not check each city's `is_stale`, which the docs tell consumers to do.

**Fix:** Catch `(urllib.error.URLError, OSError, http.client.HTTPException)` around the whole read, and cap pages at a large constant. In `curl.sh`, feed the header with `-H @-` from a here-string or a `--config` file, and URL-encode the values. In the JS example, print or fail on `is_stale`.

### IN-06: Two statements in `api-contract.md` are stale after Phase 6

**File:** `docs/frontend/specs/api-contract.md:256, 271`
**Issue:** Line 256 says history read access "arrives through Supabase REST in Phase 6", and line 271 says "Only the shadow collector is scheduled". Phase 6 has delivered the read interface, and the hourly live pipeline is scheduled (runbook section 2). A reader sizing the Software team's work gets the wrong picture.
**Fix:** Change both to point at `rest-api.md` as delivered, and drop the "nothing schedules it" wording.

---

_Reviewed: 2026-11-01_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
