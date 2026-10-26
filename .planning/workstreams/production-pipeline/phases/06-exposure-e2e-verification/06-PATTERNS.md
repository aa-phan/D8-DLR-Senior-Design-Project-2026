# Phase 6: Exposure & E2E Verification - Pattern Map

**Mapped:** 2026-10-25
**Files analyzed:** 22 new/modified
**Analogs found:** 20 / 22 (all cited paths verified git-tracked with `git ls-files`)

Sources: 06-CONTEXT.md (D-01..D-15), 06-RESEARCH.md (Wave 0 Gaps, Pattern 1-6, Code Examples). RESEARCH.md lines 444-989 (Don't Hand-Roll, Pitfalls detail, Code Examples bodies) were not re-read here; the planner should take SQL/example bodies from RESEARCH.md "Code Examples" and use this file for the repo conventions to wrap them in.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `supabase/migrations/<ts>_expose_latest_rating.sql` (ts > 20261023000000) | migration | CRUD (DDL/grants) | `supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql` + `20261019000000_create_city_rating.sql` | exact |
| `supabase/migrations/<ts>_soak_freshness_log.sql` | migration | batch (log table + fn) | same two migrations | role-match |
| `supabase/ops/verify_exposure.sql` | utility (read-only SQL) | request-response | `backend/supabase_smoke.py` checks (privilege probes) | partial |
| `supabase/ops/soak_pg_cron.sql` | config (owner-run SQL) | batch | none in repo (see No Analog) | none |
| `backend/tests/local_pg.py` | test helper | file-I/O (throwaway cluster) | fixtures in `backend/tests/supabase_live_test.py:82-156` | exact (extract) |
| `backend/tests/expose_migration_test.py` | test | CRUD vs local PG | `supabase_live_test.py` (live PG) + `supabase_migration_test.py` (text contract) | exact |
| `backend/supabase_rest.py` | service (stdlib REST client) | request-response | `backend/supabase_store.py` (`redact`, `StoreError`, `connect`) | role-match |
| `backend/e2e_verify_readonly.py` | CLI tool | request-response | `backend/supabase_smoke.py` | exact |
| `backend/e2e_trace.py` | CLI tool | request-response | `backend/dlr_live_window_check.py` | role-match |
| `backend/e2e_soak_report.py` (`--mode dry|soak`) | CLI tool | transform/batch | `backend/dlr_live_window_check.py` | exact |
| `backend/tests/fake_postgrest.py` | test helper | request-response | none (see No Analog) | none |
| `backend/tests/e2e_readonly_test.py`, `e2e_soak_report_test.py` | test | transform | `backend/tests/dlr_live_window_check_test.py` | exact |
| `backend/tests/example_read_ratings_test.py` | test | request-response | `backend/tests/dlr_live_runbook_test.py` (doc/code drift) | role-match |
| `backend/tests/secret_scan_test.py` (modify) | test | batch scan | itself, lines 22-26, 63-127 | exact |
| `docs/integration/rest-api.md` | doc | n/a | `docs/data-science/schema/city_rating_v1.md` | exact |
| `docs/integration/examples/{curl.sh,supabase_js.mjs,read_ratings.py}` | example | request-response | none (RESEARCH.md Code Examples) | none |
| `docs/data-science/decisions/dlr_live_runbook.md` (modify: alarm, monitoring, 10-31 re-check) | doc | n/a | itself, sections 6, 11, 13 | exact |
| `docs/data-science/schema/city_rating_v1.md` (modify: view + provisional line) | doc | n/a | itself | exact |
| `docs/frontend/specs/api-contract.md`, `F1-data-access-api.md`, `docs/data-science/decisions/pss_e_handoff.md` (modify: pointers) | doc | n/a | existing files | exact |
| `backend/tests/supabase_schema_doc_test.py` (modify, if it pins doc columns) | test | doc drift | itself | exact |

## Pattern Assignments

### New migration `<ts>_expose_latest_rating.sql` (migration)

**Analog:** `supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql` (header and idempotency style) and `20261019000000_create_city_rating.sql:93-116` (RLS / revoke / grant / policy).

**Header style** (analog lines 1-10): file-name comment, phase and requirement IDs, "Additive follow-up ... already applied ... never edited", "Idempotent: ... re-applies cleanly", and who applies it (owner, `supabase db push --db-url`). State "adds no credential".

**Revoke/grant/policy style to extend** (create_city_rating.sql:93-116):
```sql
alter table public.city_rating enable row level security;
revoke all on public.city_rating, public.pipeline_run from anon, authenticated;
grant select, insert, update on public.city_rating, public.pipeline_run to dlr_writer;
drop policy if exists dlr_writer_all on public.city_rating;
create policy dlr_writer_all on public.city_rating for all to dlr_writer using (true) with check (true);
```
Phase 6 copies the `drop policy if exists` then `create policy` idiom for `city_rating_public_read` and uses the RESEARCH.md Pattern 1 / Pattern 2 SQL (34-column `security_invoker` view, `ceil(...)::integer`, direct `valid_time < now() - interval '90 minutes'`, "provisional" position test on `rating_basis` OR `config_version`, revoke sweep, `grant select ... to anon, authenticated`, `alter default privileges for role postgres`). Keep `pipeline_run` private (no anon grant). One `comment on column public.latest_rating.<col>` per column (all 34), in the Phase 4 unit-first style (see column comments in create_city_rating.sql; "none (flag): ..." form seen in the analog lines 33-34).

**Constraints:** never edit the two applied migrations (sha256-pinned in `supabase_migration_test.py:35` `_ORIGINAL_MIGRATION_SHA256`); the new file must sort after `20261023000000`.

---

### `backend/tests/local_pg.py` and `backend/tests/expose_migration_test.py` (test, CRUD)

**Analog:** `backend/tests/supabase_live_test.py`. Extract its module-scoped fixture into `local_pg.py` (not collected: no `_test` suffix) and import it in the new test.

**Autostart fixture** (lines 82-124):
```python
@pytest.fixture(scope="module")
def _pg_admin_url(tmp_path_factory):
    explicit = os.environ.get("DLR_TEST_DATABASE_URL")
    if explicit:
        host = urlsplit(explicit).hostname
        if host not in _LOCAL_HOSTS:
            pytest.fail("DLR_TEST_DATABASE_URL must name a local database (127.0.0.1, localhost or ::1)")
        yield explicit
        return
    if os.environ.get("DLR_TEST_PG_AUTOSTART") != "1":
        pytest.skip("set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the live Postgres tests")
    psycopg = pytest.importorskip("psycopg")
    if shutil.which("initdb") is None or shutil.which("pg_ctl") is None:
        pytest.skip("initdb / pg_ctl not on PATH")
    ...
    subprocess.run(["initdb", "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"], check=True, capture_output=True)
    options = (f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories='' -c fsync=off -c synchronous_commit=off")
    ...
    finally:
        subprocess.run(["pg_ctl", "-D", data, "-m", "immediate", "stop"], capture_output=True)
```
**Roles and migration application** (lines 127-151): `_ROLE_SQL` creates `anon` and `authenticated` as `nologin` roles when missing; `_apply_migration` applies the committed SQL as superuser. Phase 6 must apply, in order, all of `supabase/migrations/*.sql` (sorted) and then check as `anon` with `set role anon` (or a trust-auth URL as `anon`). The autouse `_no_network` fixture (lines 47-62) should be copied too.

**Test style** (supabase_migration_test.py:1-17): module docstring stating what is and is not touched, plain asserts, no test classes, module-level imports, `import config` / `import supabase_store`.

**Tests to write** (from RESEARCH Validation): 34-column order drift guard (LATEST_COLUMNS list in the test, as `_CITY_RATING_COLUMNS` is in supabase_migration_test.py:30-80); `is_provisional` fed the real `config.RATING_BASIS` and `config.RATING_CONFIG_VERSION` and a real `supabase_load_backfill.backfill_rating_basis` label (true) and a synthetic lifted pair (false); boundary test inside one transaction (`age_minutes = a`, `assert_fresh(a)` ok, `assert_fresh(a-1)` raises PT503); `reloptions = {security_invoker=true}`; anon has SELECT only, no INSERT/UPDATE/DELETE/TRUNCATE; re-apply the file twice; every view column has a comment.

---

### `backend/e2e_verify_readonly.py` (CLI, request-response)

**Analog:** `backend/supabase_smoke.py` (docstring contract, check runner, exit codes).

**Docstring contract** (lines 14-42): one line per named check, then "output holds only booleans, counts, ... never a URL, host, project reference or credential", then "Exit codes: 0 every check passed, 1 a check failed or the connection failed, 2 ... missing (no connection is attempted)", then an owner-run command line using `PYTHONPATH=backend .venv/bin/python -c "from dotenv import load_dotenv; ..."`.

**Check-runner shape** (lines 271-292): `checks.run("name", fn)` with named checks; writes performed against the live DB go inside `with conn.transaction(force_rollback=True):`. For E2E-03 the writes are REST calls as anon (no transaction); assert HTTP 401/403 AND an unchanged before/after row snapshot (RLS-only blocking returns 200 with zero rows, Pitfall 1).

**Fold-in:** the 10-31 re-check must also re-run the existing `consumers_cannot_write` smoke (lines 271-280). Its info line "Informational only: Phase 6 grants anon SELECT" is already forward-looking; no change needed in supabase_smoke.py unless a check pins "no anon SELECT".

---

### `backend/e2e_soak_report.py` (`--mode dry|soak`) and `backend/e2e_trace.py` (CLI, transform / request-response)

**Analog:** `backend/dlr_live_window_check.py`.

**Imports and constants** (lines 35-44, 61-72): `argparse, json, math, os, statistics, subprocess, sys, datetime/timedelta/timezone`, `import config`; SQL as module-level strings with bound params `%(start)s` / `%(end)s`; never format values into SQL.
```python
PIPELINE_RUN_SQL = (
    "select run_id, run_attempt, window_end, cities_ok, cities_failed, finished_at "
    "from public.pipeline_run "
    "where window_end >= %(start)s and window_end < %(end)s "
    "order by window_end, run_id"
)
```
**DB read with redacted errors** (lines 261-301): `_rows(conn, sql, params)` returns `list[dict]`; `fetch_rows` imports `supabase_store` lazily, opens `supabase_store.connect()` only if no `conn` was passed (closing only its own), re-raises `supabase_store.StoreError` unchanged, and wraps any other exception as `StoreError(f"... {supabase_store.redact(str(exc))}")` after the `finally`. Copy this exact structure for the new queries (write-time peak-age query from RESEARCH Pattern 5; deploy change-point query from Pattern 6).

**Pure evaluator + thin fetcher + `main(argv=None) -> int`** (lines 132, 213, 314-339): `evaluate_*` pure and fixture-testable, `format_report`, `main` with `argparse`, `_hour_arg` validator (`--start` on the hour, lines 304-311), `--json PATH`, exit 0 pass / 1 fail. Reuse `evaluate_window`, `fetch_runs`, `fetch_rows` directly by import for slot verdicts (do not re-implement).

**Entry point** (lines 335-339), required by the "`load_dotenv()` only under `__main__`" rule:
```python
if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
```
**Data caveat:** exclude `origin = 'backfill'`; use `first_written_at`, not `computed_at` (RESEARCH Pitfall 14). Evidence JSON must carry no URL/key/host.

---

### `backend/supabase_rest.py` (service, request-response)

**Analog:** `backend/supabase_store.py` for conventions only (it is Postgres, not REST).

**Redaction pattern** (lines 274-294): `redact(text, secrets=None, limit=...)` defaults secrets from env vars, replaces longest first, truncates after redaction. Write a REST twin whose default secret set is `SUPABASE_URL` (full value, host, project reference label) and `SUPABASE_PUBLISHABLE_KEY` (Pitfall 15: `supabase_store.redact` does not know them). Raise a module-level error type like `StoreError`; do not chain the original exception (connect, lines 296-310: "original exception is not chained, so no part of the URL reaches a traceback"); strip env values (a pasted trailing newline, line 308-310).

**Env-missing behavior** (line 304-307): `raise StoreError("SUPABASE_DB_URL is not set")` naming the variable, before any network call. Mirror for `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY`.

**Constraints:** stdlib only (urllib); paging loop stops on an empty page, not `len(page) < 1000` (Pitfall 6); `parse_ts` helper for Python < 3.11 (shared design with `read_ratings.py`).

---

### `backend/tests/e2e_soak_report_test.py`, `e2e_readonly_test.py` (test, transform)

**Analog:** `backend/tests/dlr_live_window_check_test.py` (same module style; fixtures feed pure evaluators). Use `fake_postgrest.py` (in-process HTTP server) for REST tests; no network, no `.env`.

---

### `backend/tests/example_read_ratings_test.py` (test, doc/code drift)

**Analog:** `backend/tests/dlr_live_runbook_test.py:95-119` (docs pinned against code and workflow with regex, plain asserts) and `:144` `test_phase5_files_contain_no_secret_values`. Pattern: read the doc/example text and assert it names the real constants (env var names `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, the 34 `LATEST_COLUMNS`, the 90-minute rule, 200/503), and assert no URL/key literal. Run the example against `fake_postgrest.py` on the interpreters available (oldest local Python 3, plus 3.12, per D-11).

---

### `backend/tests/secret_scan_test.py` (modify, D-10)

**Analog:** itself. Add patterns the way existing ones are built: assembled from pieces so the file never matches itself (lines 22-26).
```python
_SCHEME = "postgres" + "(?:ql)?://"
_SB_KEY = re.compile("sb_" + "secret_" + r"[A-Za-z0-9_-]{16,}")
```
Add (a) `_SB_PUBLISHABLE = re.compile("sb_" + "publishable_" + r"[A-Za-z0-9_-]{16,}")`, (b) a 20-char ref-shaped `*.supabase.co` host pattern; extend `_scan_line` (lines 50-63), add entries to the `plants` list and to `placeholders` (placeholder text like `<project-ref>` must not fire) in `test_the_scanner_flags_planted_credentials_and_ignores_placeholders` (lines 99-134), preserving the check that reports hold no matched text. Add an env-gated owner-local test comparing tracked files against the real `SUPABASE_URL` / ref only when set (skip otherwise, never read `.env`).

---

### `docs/integration/rest-api.md` (doc)

**Analog:** `docs/data-science/schema/city_rating_v1.md`: header block (Schema version / Date / Status / Scope), bold "Read this first" provisional warning, "Where the data lives", time-semantics table, per-column table with units. Copy the "No connection details ... The owner hands them to the teams that need them" sentence (D-10). Add the 34-column table (order = LATEST_COLUMNS), computed-column rules (`age_minutes` ceil; `is_stale` strictly > 90 min; `is_provisional`), 200/503 for `rpc/assert_fresh`, paging past 1000 rows, status = 'fallback' meaning (D-04). A drift test should pin the doc's column list to the migration (see `supabase_schema_doc_test.py`).

---

### Runbook additions (modify `dlr_live_runbook.md`)

**Analog:** the runbook's own numbered-section convention (`## 6. Pause and resume`, `## 11. Failure modes and alerting`, `## 13. Checking a window`). Add sections after 13 (alarm: permanent, every 15 min, email after 2 failures, recovery and "job disabled" email, how to pause, what to do when it fires: check `pipeline_run`, Actions history, `latest_rating.is_stale`; monitoring; 10-31 re-check). Section 13 shows the command-block + verdict-table style for tools. Update section 6 so "pause the pipeline" also means "pause the alarm" (Pitfall 13). If constants or tool names are pinned by `dlr_live_runbook_test.py`, add the new tool names there.

## Shared Patterns

### Environment and secrets
**Source:** `backend/supabase_store.py:296-310`, `backend/dlr_live_window_check.py:335-339`
**Apply to:** every new CLI (`e2e_*`, `supabase_rest`), examples, tests. `load_dotenv()` only under `__main__`; tests never read `.env`; tools never print URL, host, project reference or key; evidence JSON carries none.

### Redacted error wrapping
**Source:** `backend/dlr_live_window_check.py:261-301` (and `supabase_store.redact`, lines 274-294)
**Apply to:** `e2e_soak_report.py`, `e2e_trace.py`, `e2e_verify_readonly.py`.
```python
except supabase_store.StoreError:
    raise
except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
    failure = supabase_store.redact(str(exc))
...
raise supabase_store.StoreError(f"could not read the window: {failure}")
```

### Local-Postgres test gating
**Source:** `backend/tests/supabase_live_test.py:82-124`
**Apply to:** `expose_migration_test.py` and any test needing real PG. Skipped unless `DLR_TEST_PG_AUTOSTART=1` or `DLR_TEST_DATABASE_URL` (local hosts only); the fixture always stops the cluster; nothing touches Supabase.

### Test conventions
**Source:** `backend/tests/supabase_migration_test.py:1-17`
**Apply to:** all new tests: module docstring naming what is and is not touched, module-level imports, plain asserts, no test classes, no network.

### Migration discipline
**Source:** `supabase/migrations/20261023000000_*.sql:1-10`; sha256 pin test `supabase_migration_test.py:363` (`test_original_migration_is_unchanged`)
**Apply to:** both new migrations: additive, idempotent (`if exists`, `create or replace`, `drop policy if exists`), new timestamp after `20261023000000`, no credential, never edit applied files. Consider pinning the new migrations' sha256 once applied (owner checkpoint).

### Tracked-source and live-action rules
**Apply to:** all plans: executor builds and tests offline; applying the migration, scheduling pg_cron, creating the alarm and starting the soak are owner checkpoints gated on 05-08 sign-off (D-06); commit with explicit paths; do not touch `shadow_collect.yml`, shadow logs, or the cron-job.org dispatch/shadow jobs.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/tests/fake_postgrest.py` | test helper | request-response | No in-process HTTP fake exists; use stdlib `http.server` + RESEARCH.md Code Examples |
| `docs/integration/examples/*` | example | request-response | No consumer examples exist; use RESEARCH.md "Code Examples" (curl, supabase-js, Python 3.7+ stdlib) |
| `supabase/ops/soak_pg_cron.sql`, `ops.log_freshness` | config / function | batch | No pg_cron or `ops` schema in repo; use RESEARCH.md "ops.log_freshness" block |
| `assert_fresh` RPC | function | request-response | No SQL function precedent in migrations; use RESEARCH.md "assert_fresh" block (PT503, `make_interval(mins => ...)`) |

## Metadata

**Analog search scope:** `supabase/`, `backend/` (CLIs and `backend/tests/`), `docs/data-science/`, `docs/frontend/specs/`, `.github/workflows/`
**Files read:** 06-CONTEXT.md, 06-RESEARCH.md (lines 1-443 and the Wave 0 Gaps / heading index), the two migrations (partial), `supabase_store.py` (redact/connect/finite/file_sha256), `supabase_smoke.py` (checks), `dlr_live_window_check.py`, `secret_scan_test.py`, `supabase_live_test.py` (fixtures), `supabase_migration_test.py` (header), runbook (sections 6, 13)
**Pattern extraction date:** 2026-10-25
