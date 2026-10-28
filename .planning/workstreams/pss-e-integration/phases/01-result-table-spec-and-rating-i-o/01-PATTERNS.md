# Phase 1: Result-Table Spec and Rating I/O - Pattern Map

**Mapped:** 2026-10-28
**Files analyzed:** 14 (new; nothing existing is modified)
**Analogs found:** 12 / 14 (2 are partial/no analog)

Note on the tracked-source gate: the working directory is not a git repository (no `git ls-files` possible). Every analog below is a hand-written source file under `backend/`, `supabase/migrations/` or `docs/`; none is a `.gsd/capabilities` mirror or install copy.

## File Classification

| New File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `docs/data-science/schema/psse_results_v1.md` | spec doc | transform (doc) | `docs/data-science/schema/city_rating_v1.md` | exact |
| `docs/data-science/schema/psse_results_v1.sql` | reference DDL (not a migration) | CRUD schema | `supabase/migrations/20261019000000_create_city_rating.sql` (+ `20261023...utc_hour...sql`) | exact |
| `backend/psse_job/__init__.py` | package marker | n/a | none (backend is flat) | no analog |
| `backend/psse_job/contract.py` | config/constants | transform | `PIPELINE_RUN_COLUMNS` and friends in `backend/supabase_store.py` (~lines 60-150) | role-match |
| `backend/psse_job/ratings.py` | service (pure decision) | transform | `supabase_store.finite` / `build_rating_row` (value hygiene) | partial |
| `backend/psse_job/rest_read.py` | service | request-response | none in repo (Phase 6 `supabase_rest.py` not built) | no analog |
| `backend/psse_job/run_record.py` | service | transform | `supabase_store.run_context` + `build_run_row` + `redact` | role-match |
| `backend/psse_job/writer.py` | service | CRUD (transaction) | `supabase_store.upsert_run` / `connect` | exact |
| `backend/tests/psse_contract_test.py` | test | transform | `backend/tests/supabase_schema_doc_test.py` (`_migration_columns`) | role-match |
| `backend/tests/psse_ratings_test.py` | test | transform | `backend/tests/city_rating_test.py` conventions | role-match |
| `backend/tests/psse_run_record_test.py` | test | transform | `backend/tests/supabase_run_log_test.py` | role-match |
| `backend/tests/psse_writer_test.py` | test | CRUD (live local PG) | `backend/tests/supabase_live_test.py` lines 1-173 | exact |
| `backend/tests/psse_schema_doc_test.py` | test | transform | `backend/tests/supabase_schema_doc_test.py` | exact |

## Pattern Assignments

### `docs/data-science/schema/psse_results_v1.sql` (reference DDL)

**Analog:** `supabase/migrations/20261019000000_create_city_rating.sql`

**Header / idempotency** (lines 1-23): file-path comment line, purpose, "Idempotent: tables use if not exists, each policy is dropped before it is created, the role is created inside a guard", "role is created WITHOUT a credential". For the new file the header must say "NOT a migration; production-pipeline Phase 6 copies it".

**Table + named constraints** (lines 25-35, 72-75): one column per line (the doc test parses this), constraints named `<table>_<col>_ck` / `<table>_pk`:
```sql
create table if not exists public.city_rating (
    city text not null constraint city_rating_city_ck check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO')),
    rating_amps double precision not null constraint city_rating_rating_amps_ck check (rating_amps > 0 and rating_amps < 'Infinity'::float8),
    config_fingerprint text not null constraint city_rating_config_fingerprint_ck check (config_fingerprint ~ '^[0-9a-f]{64}$'),
    schema_version integer not null default 1,
    computed_at timestamptz not null default date_trunc('second', now()),
    constraint city_rating_pk primary key (city, valid_time)
);
```
**UTC hour CHECK (use this form, not line 27's original)** from `20261023000000_...sql` line 20:
```sql
check ((valid_time at time zone 'UTC') = date_trunc('hour', valid_time at time zone 'UTC'))
```
**Grants / role / RLS / policies** (lines 93-116):
```sql
alter table public.city_rating enable row level security;
revoke all on public.city_rating, public.pipeline_run from anon, authenticated;
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'dlr_writer') then
        create role dlr_writer login;
    end if;
end
$$;
grant usage on schema public to dlr_writer;
grant select, insert, update on public.city_rating, public.pipeline_run to dlr_writer;
drop policy if exists dlr_writer_all on public.city_rating;
create policy dlr_writer_all on public.city_rating for all to dlr_writer using (true) with check (true);
```
Adaptation (locked decision: private tables): revoke from `public, anon, authenticated`; role `dlr_psse_writer`; grant only `select, insert` (no update/delete); two policies per table (`for insert ... with check (true)`, `for select ... using (true)`) instead of `for all`. No grant on `city_rating`, `pipeline_run`, `latest_rating`.

**Comments** (lines 118-182): `comment on column public.<t>.<c> is '<unit-first>: ...'` with units written as `'none (identifier): ...'`, `'amperes (A), per conductor: ...'`, `'UTC instant: ...'`, `'count: ...'`, `'none (flag): ...'`. Every column needs one; the spec doc test should assert it.

**Composite FK / new constructs with no analog:** `unique (run_id, outcome)`, `foreign key (run_id, run_outcome) references psse_run (run_id, outcome)`, `?&` jsonb key check. Take them from RESEARCH.md "Recommended Table Spec"; the repo has no precedent.

---

### `docs/data-science/schema/psse_results_v1.md` (spec doc)

**Analog:** `docs/data-science/schema/city_rating_v1.md`. Structure is enforced by `backend/tests/supabase_schema_doc_test.py`: exact ordered `## ` heading list (`REQUIRED_HEADINGS`, lines 30-43), and per-column table rows `| Column | Type | Unit | NULL when | Meaning |` (5 cells; type cell is the backticked SQL type; unit cell never empty, write `none`; NULL-when never empty, write `never`). Run-log style secondary tables use 3 cells (`Column | Type | Meaning`). Needed content per RESEARCH: "Phase 6 intake" section first, per-table columns, grants/role block, verification SQL, unit conversion table (amps per conductor x subconductors, sqrt(3) x kV x I / 1000, no power factor), the "no `rating_mw`" warning, env var name `SUPABASE_PSSE_DB_URL`, no connection details.

---

### `backend/psse_job/writer.py` (service, CRUD transaction)

**Analog:** `backend/supabase_store.py` (`upsert_run` lines 727-771, `connect` lines 296-343, `StoreError` line 192)

**Lazy driver import + connect settings** (lines 319-327):
```python
import psycopg  # imported here so importing this module needs no driver
conn = psycopg.connect(url, connect_timeout=10, prepare_threshold=None, autocommit=True)
conn.execute("set statement_timeout = '30s'")
conn.execute("set timezone = 'UTC'")
```
Copy these as-is but read `SUPABASE_PSSE_DB_URL`; keep `autocommit=True` so `with conn.transaction():` is the explicit BEGIN/COMMIT. Do not use `conn.execute(...).fetchone()` assumptions beyond the 3.1-3.3 common API.

**Transaction + redacted re-raise outside the except block** (lines 764-771):
```python
failure = None
try:
    with conn.transaction():
        conn.execute(sql, params)
except Exception as exc:  # noqa: BLE001 - re-raised below as a redacted StoreError
    failure = redact(str(exc))
if failure is not None:
    raise StoreError(f"could not write the pipeline_run row: {failure}")
```
Raising outside the `except` avoids chaining the original message. Use the same shape for `WriteFailed`, and call `record_failure` (new transaction) between capture and raise, as RESEARCH Pattern 2 shows.

**jsonb binding** (lines 743-761): `%(col)s::jsonb` placeholders with `json.dumps(value, allow_nan=False, default=str)`; column names only from a fixed tuple (unknown key -> `ValueError`). Copy for `ratings_used` and `details`. Difference to apply: `on conflict (run_id) do nothing returning run_id` instead of `do update` (insert-only role).

**Connection failure redaction** (lines 329-341): `_RESOLVED_ADDRESS_RE.sub("(REDACTED)", redact(str(exc), secrets + _connection_identifiers(url)))`. Re-implement the small versions in `psse_job` (do not import `supabase_store`: line 50 imports pandas at module top, line 52-55 pull `ampacity_forecast`, `city_point`, `historical_archive`).

---

### `backend/psse_job/run_record.py` (service, transform)

**Analog:** `backend/supabase_store.py`

**run_id generation** (`run_context`, lines 383-385; adapt prefix to `psse-`):
```python
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
run_id = f"local-{stamp}-{uuid.uuid4().hex[:8]}"
```
**Version as label, never a reason to fail** (lines 390-402): `GITHUB_SHA[:7]` else `git rev-parse --short HEAD` in a try/except with `"unknown"` default, `# noqa: BLE001 - version is a label, never a reason to fail a run`.

**redact** (lines 200-205, 274-293): port `_URL_RE`, `_KEY_VALUE_RE`, longest-first secret replacement, `text[:limit]` AFTER redaction. Add `SUPABASE_PSSE_DB_URL` (and `SUPABASE_PUBLISHABLE_KEY`) to the env names; limit 1000 (`_RUN_ERROR_MAX_CHARS`, line 92) for `psse_run.error`.

**finite()** (lines 410-426): copy semantics (None for NaN/inf/non-number) for every double column before writing. Slot floor: `slot_of` (lines 359-368) floors to the UTC hour; reimplement with stdlib `datetime.replace(minute=0, second=0, microsecond=0)` (no pandas).

---

### `backend/psse_job/contract.py` (constants mirroring DDL)

**Analog:** `PIPELINE_RUN_COLUMNS` / `PIPELINE_RUN_JSONB` / `PIPELINE_RUN_KEY` / `PIPELINE_RUN_TABLE` in `backend/supabase_store.py` (used at lines 736-761): tuples of column names plus a jsonb subset, validated against the DDL by a test. Mirror: `PSSE_RUN_COLUMNS`, `PSSE_RUN_JSONB`, `OUTCOMES = ("ok","fallback","failed")`, `SOURCES`, `REASONS`, `VIOLATION_KINDS`, `CITIES` (must equal `config.LOCATIONS`; add a test).

---

### `backend/psse_job/ratings.py` (pure decision, transform)

No exact analog. Use RESEARCH Pattern 1 (`choose`). From the repo take only: `config.STATIC_RATINGS` (backend/config.py:41, per conductor: AUSTIN 1825.0, CORPUS_CHRISTI 1500.0 ...), `config.SUBCONDUCTORS_PER_PHASE` (config.py:76-81: 2, 2, 2, 1), `config.LINE_VOLTAGE_KV` (247), `config.POWER_FACTOR` (248), and `finite()` semantics. Imports pattern: `import config` (tests put `backend` on `sys.path`, see test header below).

**WARNING (Python version claim):** `backend/config.py:41` and `:76` annotate with `dict[str, float]` / `dict[str, int]` at module level and the file has no `from __future__ import annotations`. That evaluates at import and raises `TypeError` on Python 3.7/3.8 (works on 3.9+). RESEARCH asserts "config.py has no imports so it is importable on the laptop"; true for imports, false for 3.7/3.8. The planner must either (a) set the PSS/E-interpreter floor to 3.9 for `psse_job`, or (b) have `psse_job` avoid importing `config` (copy constants plus a drift test), or (c) add a `from __future__ import annotations` line to config.py (a modification to an existing file, so it needs an owner call). Also check other module-level annotations in config.py before choosing (only the two above were grepped).

---

### `backend/psse_job/rest_read.py` (service, request-response)

**No analog in the repo** (grep: the repo reads Supabase only via psycopg; Phase 6's `supabase_rest.py` is unbuilt). Use RESEARCH "Code Examples: Reading latest_rating with stdlib" and pass an injectable `fetch` callable into `ratings.select_ratings` so tests stay offline. Reuse the "refuse a secret/service_role key before any request" truth from Phase 6 plan 06-04.

---

### `backend/tests/psse_writer_test.py` (test, live local Postgres)

**Analog:** `backend/tests/supabase_live_test.py`

**Skip/guard + local-only host rule** (lines 82-123): module-scoped `_pg_admin_url` fixture, `DLR_TEST_DATABASE_URL` must be `127.0.0.1|localhost|::1` else `pytest.fail`; `DLR_TEST_PG_AUTOSTART=1` runs `initdb`/`pg_ctl` in `tmp_path_factory`, always stops in `finally`; `pytest.importorskip("psycopg")`; skip if `initdb`/`pg_ctl` missing. Copy verbatim (or import if Phase 6's `local_pg.py` exists by then).

**Roles + apply** (lines 125-165):
```python
_ROLE_SQL = """do $$ begin if not exists (select 1 from pg_roles where rolname = 'anon') then create role anon nologin; end if; ... end $$;"""
def _apply_migration(admin_url):
    with open(_MIGRATION, encoding="utf-8") as handle: sql = handle.read()
    with psycopg.connect(admin_url) as conn:
        conn.execute(_ROLE_SQL); conn.execute(sql)
def _writer_url(admin_url):
    parts = urlsplit(admin_url)
    return parts._replace(netloc=f"dlr_writer@{parts.hostname}:{parts.port}").geturl()
```
Adapt: apply `docs/data-science/schema/psse_results_v1.sql` (the reference DDL) instead of a migration, and connect as `dlr_psse_writer`. Also apply `20261019000000_create_city_rating.sql` first so the "no privilege on `city_rating`" proof has a table to deny. `_reset` truncates as superuser; `_admin_rows` uses `dict_row` (lines 159-173).

**Privilege proofs to add** (no analog; use `psycopg.errors.InsufficientPrivilege` / `ForeignKeyViolation` 23503): update/delete denied, `city_rating` select denied, anon/authenticated denied, child insert under a `failed` run denied by the composite FK, rollback leaves zero rows on a mid-write error, same `run_id` twice returns `already_recorded`, `set time zone '+05:30'` slot check (RESEARCH pitfall 7).

**Header convention** (lines 1-14): docstring stating skip conditions, "never touch Supabase", "plain asserts, no test classes, no network".

---

### `backend/tests/psse_schema_doc_test.py` and `psse_contract_test.py` (test, transform)

**Analog:** `backend/tests/supabase_schema_doc_test.py`

**Path bootstrap + helpers** (lines 13-27, 49-95):
```python
_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
_ROOT = os.path.abspath(os.path.join(_BACKEND, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
import config  # noqa: E402
_SQL_TYPES = r"(text\[\]|double precision|timestamptz|integer|boolean|jsonb|text)"
_COLUMN_LINE = re.compile(r"^\s+([a-z_0-9]+)\s+" + _SQL_TYPES + r"(?=[\s,]|$)")
```
Reuse `_migration_columns(table)` (parse `create table if not exists public.<t> (` block until `);`), `_section`, `_table_rows`, `_squash`. Note: `_COLUMN_LINE` matches only column lines whose type is on the allow-list and that start with whitespace; table-level `constraint ...` lines are skipped, which is why the DDL must keep one column per line. Point `MIGRATION_PATH` at `psse_results_v1.sql`.

**Assertions to copy:** doc column names/order equal DDL (lines 98-121), `REQUIRED_HEADINGS` exact equality plus `count == 1` (124-137), no connection details (151-158):
```python
assert not re.search(r"postgres(?:ql)?://", doc, re.IGNORECASE)
assert "pooler." + "supabase.com" not in doc
assert not re.search("sb_" + r"[a-z]+_[A-Za-z0-9_-]{8,}", doc)
assert not re.search(r"eyJ[A-Za-z0-9_-]{7,}", doc)
```
Unit table (RESEARCH): recompute amps x subconductors x sqrt(3) x 345 / 1000 from `config` instead of hard-coding (e.g. AUSTIN 2181.1 MVA).

**3.7 syntax gate:** no repo analog; `ast.parse(source, feature_version=(3, 7))` over each `psse_job/*.py` (best-effort).

---

### `backend/tests/psse_ratings_test.py`, `psse_run_record_test.py` (test, transform)

**Analog:** conventions of `backend/tests/city_rating_test.py` / `supabase_run_log_test.py` (module-level imports, plain asserts, no classes, no network). The bootstrap block above applies. Parametrize the IN-01 matrix (missing, invalid, stale by server flag, stale by client age at exactly 90 vs 91 minutes, provisional, read_failed, fresh ok, fresh `status=fallback` still `city_rating`). Include a redaction parity test against `supabase_store.redact` on shared cases (importing `supabase_store` in a TEST is fine; only the job must not).

## Shared Patterns

### Secret hygiene
**Source:** `backend/supabase_store.py` lines 200-293 (`redact`), 329-341 (connect failure).
**Apply to:** `writer.py`, `run_record.py`, `rest_read.py`, every error string stored in `psse_run.error`.
Cut after redaction; never print URL/host/project ref; raise outside the `except` block.

### Value hygiene for numerics and jsonb
**Source:** `supabase_store.finite` (410-426), `json.dumps(..., allow_nan=False, default=str)` (758).
**Apply to:** all double columns and jsonb values built by `ratings.py` / `run_record.py` / `writer.py`.

### DDL conventions
**Source:** `supabase/migrations/20261019000000_create_city_rating.sql` and `20261023...sql` (UTC hour CHECK).
**Apply to:** `psse_results_v1.sql`. Named constraints, unit-first comments, `schema_version integer not null default 1`, DB-set `date_trunc('second', now())` timestamps, explicit revokes, role guard without credential, RLS on with explicit policies.

### Test file conventions
**Source:** `supabase_schema_doc_test.py` lines 1-27 and `supabase_live_test.py` lines 1-14.
**Apply to:** all five new tests. Names `<module>_test.py` in `backend/tests/` (pytest.ini picks up `*_test.py`, `pythonpath = backend`); docstring with phase/requirement IDs and skip conditions.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `backend/psse_job/__init__.py` | package | n/a | `backend/` is a flat module layout; no sub-package exists |
| `backend/psse_job/rest_read.py` | service | request-response | repo reads Supabase only via psycopg; Phase 6 REST client unbuilt; use RESEARCH stdlib example |
| `backend/psse_job/ratings.py` | service | transform | no staleness/fallback chooser exists; use RESEARCH Pattern 1 |
| Composite FK / `?&` jsonb checks in DDL | schema | CRUD | no precedent in existing migrations; use RESEARCH DDL |

## Metadata

**Analog search scope:** `backend/*.py`, `backend/tests/`, `supabase/migrations/`, `docs/data-science/schema/`
**Files read:** supabase_store.py (192-431, 727-772), both migrations, supabase_schema_doc_test.py, supabase_live_test.py (1-190), config.py (selected)
**Pattern extraction date:** 2026-10-28
