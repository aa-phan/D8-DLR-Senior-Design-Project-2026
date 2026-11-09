# Phase 4: Supabase Store & Writer - Research

**Researched:** 2026-10-19
**Domain:** Supabase-hosted Postgres as the system of record for a Python (pandas) pipeline run from GitHub-hosted runners: migrations, pooler connectivity, psycopg 3 upsert/read, schema, secrets, free-tier limits, offline testing
**Confidence:** HIGH on schema/SQL/upsert/RLS/migration-tool behavior (all exercised this session against local PostgreSQL 16.14, psycopg 3.3.6, Supabase CLI 2.121.0); MEDIUM on Supabase-platform specifics (official docs read, no Supabase project exists yet so the pooler path was not exercised live); LOW on anything marked `[ASSUMED]`

<user_constraints>
## User Constraints (from REQUIREMENTS.md; no CONTEXT.md exists for this phase)

### Locked Decisions
From REQUIREMENTS.md "Decided architecture":
- "**Store:** hosted Postgres on Supabase. It replaces the CSV historical archive as the system of record for live ratings, because GitHub Actions runners are ephemeral and cannot keep a CSV between runs."
- "**Read interface:** Supabase's built-in REST API (PostgREST), read-only for consumers via Row Level Security. No custom API server in this workstream."
- "**Writer:** the integrated per-city pipeline from PR #7 (`dlr_orchestrator.run_dlr_pipeline`), run in a GitHub Actions workflow."
- "**Trigger:** cron-job.org calling GitHub's `workflow_dispatch` ... No GitHub `schedule:` trigger."

From REQUIREMENTS.md "Owner decisions (fixed 2026-10-19)":
- "OD-1 | Live cadence | **Hourly.**"
- "OD-2 | Production weather provider mode | **`composed`.**"
- "OD-3 | Forecast method on the live path | **`ml`.** Consequence: the per-city forecast models (`data/models/forecast_{CITY}.joblib`, git-ignored) must be available to the live runner alongside the anomaly models (`data/models/anomaly_{CITY}.joblib`). Provisioning them is in scope for Phases 4-5. `city_pipeline` catches a forecast failure and continues without a forecast, so a missing model degrades silently. The live run must detect that case and record it"
- "OD-4 | Freshness grace period for E2E-02 | **30 min** past one cadence interval (a city's latest `valid_time` no older than 90 min at hourly cadence)"
- "OD-5 | Labelling of values based on provisional static ratings / assumed bearings | **Labelled provisional** in the schema doc and per row (e.g. a `rating_basis` / `config_version` column)"

Scope guards from the invoker: never read `.env`; never write to `data/shadow/predictions`; research only (no code changes).

### Claude's Discretion
Migration tooling, Python client, exact schema/column set and types, secret layout and writer role, test strategy, smoke test, where new modules/docs live, and the evaluation of Supabase Storage as a model-provisioning option (Phase 5 decides).

### Deferred Ideas (OUT OF SCOPE)
Custom FastAPI/Flask server; `frontend/` dashboard; PSS/E-side ingestion; PSS/E results back into the DB; changes to `shadow_collect.yml`, shadow logs or frozen evaluation modules; re-evaluating the ML shadow candidates. (Consumer exposure through REST, the `latest_rating` view and anon grants are Phase 6; the scheduled workflow is Phase 5.)
</user_constraints>

## Project Constraints (from CLAUDE.md)

No project `./CLAUDE.md` or `./.claude/CLAUDE.md` rules exist and no `.agents/` skills directory (`.claude/` holds only `jobs`, `scheduled_tasks.lock`, `settings.local.json`, `worktrees`). The user's global CLAUDE.md only defines the `/graphify` trigger (not applicable). Binding workstream rules from ROADMAP.md that apply here: do not modify `shadow_collect.yml`, shadow logs or frozen evaluation modules before 2026-11-24; "Commit with explicit paths; ask before pushing anything that changes live CI" (so any new workflow file, including a smoke workflow, needs a `checkpoint:human-verify` before it is pushed); anti-peeking (nothing scores shadow predictions). Repo conventions that apply: offline tests (`pytest.ini`: `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`), `requirements.txt` pins every dependency (DS-NF2), `.env` is git-ignored (`.gitignore` line 26).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DB-01 | Versioned SQL migration creates schema (rating table keyed uniquely on (`city`,`valid_time`) with the listed columns; units in names) | "Schema design" column table + tested migration skeleton; `supabase db push --db-url` verified with no Docker, tracks history, second push is a no-op |
| DB-02 | Pipeline reads forecast/detector history from Postgres and upserts its result; CSV path stays usable offline; idempotent upsert on the unique key | "Store seam" pattern; `INSERT ... ON CONFLICT (city, valid_time) DO UPDATE` verified (2 upserts -> 1 row); history reader returns the `ARCHIVE_COLUMNS` DataFrame shape; the table MUST store the observation inputs (`air_temp_c`, `wind_perp_ms`, `solar_radiation_wm2`) because the forecast and detector need them |
| DB-03 | Validated Phase 3 backfill loaded; per-city counts match the Phase 3 archive | "Backfill loader" pattern: `ON CONFLICT DO NOTHING`, executemany, dedup-then-count parity check |
| DB-04 | Secrets only as Actions secrets; connection works from GitHub-hosted runners via pooler | Session-mode pooler (port 5432), dedicated least-privilege `dlr_writer` role, one secret `SUPABASE_DB_URL`; masking caveats; secret-scan test; live smoke command |
| DB-05 | Consumer schema contract doc replacing open items in `api-contract.md` and `pss_e_handoff.md` | Doc outline, location (`docs/data-science/schema/city_rating_v1.md`), exact open items to close, fallback/provisional semantics to document |
</phase_requirements>

## Summary

Use Postgres as the store through a plain SQL connection, not through the REST client. The writer is a new `backend/supabase_store.py` using **psycopg 3.3.6** (`psycopg[binary]`) connecting to the **Supavisor session-mode pooler (port 5432)** as a dedicated **`dlr_writer`** login role that has only SELECT/INSERT/UPDATE on two tables (plus a policy, because RLS is on). Schema changes are SQL files in `supabase/migrations/` applied with **`supabase db push --db-url <admin session-pooler URL>`**, which I verified against a plain Postgres with no Docker present: it records history in `supabase_migrations.schema_migrations`, shows a dry run, and a second push reports "Remote database is up to date." The migration is also written idempotently (`IF NOT EXISTS`, `DO` blocks, `DROP POLICY IF EXISTS`) and applies twice cleanly with `psql -v ON_ERROR_STOP=1 -1`, so either path satisfies roadmap criterion 1.

Five findings change what a naive plan would do. (1) **The table must store the weather inputs**, not only the rating: `forecast_ampacity` (`ml` method requires `air_temp`, `wind_speed`, `solar_radiation`) and `AnomalyDetector.for_city` read them from the history DataFrame, and the CSV archive's `wind_speed` is the line-perpendicular projected wind. DB-01's list omits them; add them (nullable, because exhausted cities have no observation). (2) **`valid_time` must be defined as the UTC hour of the run window end (hour-truncated)**: today `rate_city` archives `datetime_utc=end` where `end` is "now floored to 5 minutes", so an hourly cron at 14:07 and a re-run at 14:12 would be different keys and idempotency would silently fail; a `CHECK (valid_time = date_trunc('hour', valid_time))` enforces it. The composer's aligned weather hour (up to 3 h older) goes in a separate `observation_time`. This matches Phase 6's assumption A3. (3) **With RLS on, a role without a policy sees zero rows and gets no error** (verified), so a missing policy turns into a silent forecast cold start; the smoke test must assert the policy works. (4) The seam needs small changes in existing code (store injection in `city_pipeline`, per-city provenance lookup, a forecast-status signal for OD-3, `archive=False` on the DB path). (5) `typing`: NaN is accepted by `double precision`, so a CHECK constraint plus writer-side NaN-to-NULL mapping are needed (verified).

Free tier is not a constraint: measured 29 MB per year for 4 cities hourly at a representative row width (limit 500 MB), hourly writes count as database activity that prevents the 7-day pause, and the writer holds one connection (Nano: 60 direct, 200 pooler clients). Supabase Storage is a poor fit for the models: they total ~0.76 MB (well under the 50 MB free file limit) but a private-bucket download needs the secret key (full RLS bypass on the runner) and `.joblib` files are pickles; committing them with a `.gitignore` carve-out (the repo's own `data/shadow/models` precedent) is safer. Phase 5 decides.

**Primary recommendation:** psycopg 3 + session-pooler + least-privilege `dlr_writer` role; one idempotent migration applied with `supabase db push --db-url`; `valid_time` = hour-truncated run end with `observation_time`, `first_written_at`, `computed_at`, `run_id`, `rating_basis`, `config_version` columns; store injected behind a small seam so the CSV path stays the offline default.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Computing the rating, forecast, detector signal | API / Backend (Python pipeline on the Actions runner) | — | Existing `run_dlr_pipeline`; DB only stores results |
| Idempotent persistence (upsert on (city, valid_time)) | Database / Storage (unique key + `ON CONFLICT`) | API / Backend (writer issues the statement) | The key is enforced in Postgres, so CLEAN-03 holds at the DB level regardless of client bugs |
| History for forecast/detector | Database / Storage (table) | API / Backend (reader builds the DataFrame) | Replaces the CSV that ephemeral runners cannot keep |
| MW conversion | API / Backend (`ercot_dlr_merger.amps_to_mw` with `config.LINE_VOLTAGE_KV`, `config.POWER_FACTOR`) | — | DB-01 mandates this function; the DB stores kV and PF used so MW is reproducible. Do not use a SQL generated column (would duplicate constants) |
| Least-privilege write access | Database / Storage (role `dlr_writer`, GRANT, RLS policy) | — | Privilege is a Postgres property; the pooler only authenticates |
| Schema versioning | Database / Storage (`supabase_migrations.schema_migrations` via CLI) | Repo (`supabase/migrations/*.sql`) | History table prevents re-running one-shot objects (e.g., Phase 6's removable soak cron) |
| Secret custody | CI (GitHub Actions secrets) | Owner machine (admin URL, never in repo) | DB-04 |
| Model artifact provisioning (OD-3) | CI / repo (git carve-out) or Storage | Phase 5 decision | Noted here, decided in Phase 5 |
| Consumer contract (DB-05) | Docs | — | Repo doc replaces open items; REST exposure itself is Phase 6 |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `psycopg[binary]` (psycopg 3) | 3.3.6 (released 2026-09-18; `requires_python >=3.10`) `[VERIFIED: PyPI JSON api, this session]` | Postgres driver for upserts, history reads, backfill load, smoke test | Maintained successor to psycopg2; pure `psycopg` + `psycopg-binary` wheels exist for cp312 on manylinux x86_64 (Actions) and macOS arm64 (dev) `[VERIFIED: PyPI file list]`; no numpy/pandas dependency, `pip check` clean with pandas 2.3.3, numpy 2.4.3, python-dotenv 1.2.4 on Python 3.12.13 `[VERIFIED: scratch venv]` |
| `psycopg-binary` | 3.3.6 (must equal `psycopg`) | Prebuilt libpq so the runner and Windows/macOS students need no compiler or libpq | Pinned alongside `psycopg` (DS-NF2) |
| Supabase CLI (npm `supabase`) | 2.121.0 (published 2026-10-14) | `supabase db push --db-url ...` migration apply and history | Official; `[VERIFIED: ran it]`: `--dry-run` lists pending, push applies, second push "up to date", works with only `supabase/migrations/` present (no `config.toml`), no Docker on this machine |
| PostgreSQL features | Supabase hosted Postgres (>= 15; verified locally on 16.14) | `ON CONFLICT`, RLS, CHECK, `timestamptz`, `text[]`, `jsonb` | The store |

Not added to `requirements.txt`: the Supabase CLI (dev/ops tool; install with `npm install --ignore-scripts supabase@2.121.0` in a scratch dir, `brew`, or `scoop`), `psycopg-pool` (one short-lived connection per run; no pool needed), SQLAlchemy (pandas works with plain cursor results; `pd.read_sql` on a raw psycopg connection emits "pandas only supports SQLAlchemy connectable ..." UserWarning `[VERIFIED: pandas 2.3.3 run]`, so build the DataFrame from `cursor.fetchall()`).

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-dotenv` | 1.2.4 (already pinned) | Owner loads `SUPABASE_*` from the git-ignored `.env` for local runs | Local only; Actions passes secrets as env vars (STATE item 2: `dlr_orchestrator` does not call `load_dotenv()`) |
| `pytest` | 9.0.3 (already pinned) | Offline writer/migration/secret-scan tests | Always |
| `psql` (PostgreSQL client) | 16.14 present here (`/opt/homebrew/bin/psql`) | Optional local integration test, fallback to apply SQL (`psql -v ON_ERROR_STOP=1 -1 -f`) | Optional |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| psycopg 3 over SQL | `supabase-py` / PostgREST over HTTPS with a secret key | HTTPS avoids the pooler/IPv6 issue, but: the only write credential is the secret key which maps to `service_role` and bypasses RLS on every table (no least privilege) `[CITED: supabase.com/docs/guides/api/api-keys]`; the API caps results at "Max rows" (default 1000, `[CITED]` MEDIUM) which silently truncates history reads; `computed_at = now()`/conditional update logic must come from the client; `supabase` and `postgrest` PyPI packages returned SUS (`too-new`, `no-repository`) and drag in httpx and others; legacy keys are being deprecated by end of 2026. Reject |
| psycopg 3 | psycopg2-binary 2.9.13 | Works and is ubiquitous, but psycopg2 is legacy API (no native `Jsonb`, no pipeline `executemany`), and SUS only for the same "unknown downloads" reason. No upside here |
| Session pooler (5432) | Transaction pooler (6543) | Supavisor transaction mode forbids prepared statements, session state (`SET`, temp tables, advisory locks), and pipelining `[CITED: supabase.com/docs/guides/database/connecting-to-postgres]`. The writer is one short-lived client, so session mode costs nothing. If 6543 is ever used set `prepare_threshold=None` (psycopg default is 5 `[VERIFIED: Connection.prepare_threshold == 5]`) |
| Session pooler | Direct host `db.<ref>.supabase.co:5432` | Direct is IPv6-only on Free; GitHub Actions is on Supabase's IPv4-only list `[CITED: supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility-cHe3BP]`. The IPv4 add-on is ~$4/month and Pro+ only. Many home networks also lack IPv6, so use the pooler for the owner's migration pushes too |
| Supabase CLI `db push` | Plain `psql -f` per file | `psql` works with zero installs on CI and gives atomic `-1` apply, but has no history table: re-applying every file each time would re-create one-shot objects (Phase 6 plans a removable `cron.schedule` soak job). Use `psql` only as the fallback |
| Supabase CLI | hand-written Python migration runner | Reinvents history tracking (see Don't Hand-Roll). Reject |
| Dedicated `dlr_writer` role | `postgres` role in the connection string | `postgres` can drop tables and read everything; leaking it from CI is far worse. A role-per-service is Supabase's own recommendation `[CITED: supabase.com/docs/guides/database/postgres/roles]` |

**Installation (`requirements.txt` additions; pin both, exact versions):**
```
psycopg==3.3.6
psycopg-binary==3.3.6
```
(Comment block in the file says versions are verified in `.venv`; install into `.venv` and run `.venv/bin/python -m pip check` before committing the pins. `typing_extensions` 4.15.0, required by psycopg on Python < 3.13, is already in `.venv`.)

**Version verification:**
```
PyPI JSON: psycopg 3.3.6 (upload 2026-09-18), psycopg-binary 3.3.6, psycopg-pool 3.3.3, psycopg2-binary 2.9.13
pypistats recent: psycopg 42.0M/week, psycopg-binary 41.2M/week (2026-10-19)
npm view supabase version -> 2.121.0 (repo github.com/supabase/cli, 3.6M/week)
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `psycopg` | PyPI | first upload 2021-08-30 (63 releases) | 42.0M/wk (pypistats) | github.com/psycopg/psycopg | SUS (seam reason: `unknown-downloads`; the seam cannot read PyPI download counts) | `psycopg` [WARNING: flagged as suspicious — verify before using.] The flag is an artifact of missing download data; my own checks (pypistats, PyPI project URLs, 4+ years of releases) support legitimacy. Planner still adds a `checkpoint:human-verify` before the first `pip install` and pins the exact version |
| `psycopg-binary` | PyPI | first upload 2021-10-12 | 41.2M/wk | github.com/psycopg/psycopg | SUS (`unknown-downloads`) | Same as above; installed as the `binary` extra of psycopg (`psycopg[binary]`), version must equal `psycopg` |
| `supabase` (npm CLI) | npm | many years; 2.121.0 is 5 days old | 3.6M/wk | github.com/supabase/cli | SUS (`too-new`: latest release 2026-10-14; `postinstall: null`) | Dev/ops tool, not in `requirements.txt`. Flag stands: planner adds `checkpoint:human-verify` before the owner installs it; install with `--ignore-scripts` (I ran it that way and it worked); pin `2.121.0`. The flag reflects release recency, not identity |
| `psycopg2-binary` | PyPI | 2018 | 50.8M/wk | github.com/psycopg/psycopg2 | SUS (`unknown-downloads`) | Not recommended (alternative only) |
| `supabase` (PyPI), `postgrest` (PyPI) | PyPI | latest release 2026-10-15 | unknown | none (`repoUrl: null`) | SUS (`too-new`, `no-repository`) | Not recommended; not used |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `psycopg`, `psycopg-binary` (both required, flag is data-gap), npm `supabase` CLI (tooling). Package names for psycopg came from the official docs (psycopg.org, linked from PyPI project URLs and Supabase's docs for Postgres drivers), not from search results alone, but the seam did not return `OK`, so they are not tagged `[VERIFIED: npm registry]`; treat as flagged-with-evidence per the table.

## Architecture Patterns

### System Architecture Diagram

```
 cron-job.org (hourly, Phase 5) --workflow_dispatch--> GitHub Actions run (ubuntu-latest, IPv4 only)
                                                         |  env: SUPABASE_DB_URL (Actions secret), SYNOPTIC_TOKEN, NREL_*  (OD-2)
                                                         v
   dlr_orchestrator.run_dlr_pipeline(store=SupabaseStore)         [per city, failures isolated]
     |
     |  1. store.read_history(city, before=slot)  ------------------------------+
     |         SELECT ... FROM city_rating WHERE city=%s AND valid_time < slot    |   (Phase 2 cleaning step
     |         -> DataFrame in ARCHIVE_COLUMNS shape                              |    sits right after this)
     v                                                                            |
   city_pipeline: drop fallback rows -> forecast_ampacity(method="ml")            |
        -> AnomalyDetector.for_city(city, forecast, history) -> rate_city(archive=False)
     |  result dict + result["pipeline"] + composer provenance for the resolved station
     v
   build_rating_row(result, run_ctx) -> python-native types, NaN->None, MW via amps_to_mw
     |
     |  2. store.upsert_rating(row)  INSERT ... ON CONFLICT (city, valid_time) DO UPDATE
     v                                                                            
   Supavisor SESSION pooler  aws-N-<region>.pooler.supabase.com:5432  (user dlr_writer.<ref>, sslmode=require)
     v
   Supabase Postgres: public.city_rating (PK city,valid_time; RLS on; policy only for dlr_writer)
                      public.pipeline_run (one row per workflow run; used by Phase 5 for SCHED-01)

 Owner-only paths (never in CI):
   supabase db push --db-url $SUPABASE_ADMIN_DB_URL   (postgres role via session pooler)  -> migrations
   python backend/supabase_load_backfill.py --csv data/historical/provisional_backfill.csv -> ON CONFLICT DO NOTHING
   python backend/supabase_smoke.py                                                         -> live check, rolls back
```

### Recommended Project Structure
```
supabase/migrations/
└── 20261019000000_create_city_rating.sql   # DB-01 (CLI naming: <timestamp>_<name>.sql). Phase 6 appends later files
backend/
├── supabase_store.py          # connect(), read_history(), build_rating_row(), upsert_rating(), upsert_run(), SupabaseStore
├── supabase_load_backfill.py  # DB-03 CSV -> city_rating (ON CONFLICT DO NOTHING), prints per-city parity
├── supabase_smoke.py          # one-command live check (rolls back, leaves no rows)
└── tests/
    ├── supabase_store_test.py        # stub-connection tests of row shaping + SQL
    ├── supabase_migration_test.py    # parses the .sql: columns, constraints, no secrets, idempotent markers
    ├── supabase_live_test.py         # skipped unless DLR_TEST_DATABASE_URL is set (local Postgres)
    └── secret_scan_test.py           # git-tracked files contain no keys/URLs with passwords
docs/data-science/schema/city_rating_v1.md   # DB-05 (next to pipeline_output_v1.md, same convention)
```
Locations are recommendations; names follow the repo's flat-module `backend/` layout and `*_test.py` collection.

### Pattern 1: Store seam (keeps the CSV path the offline default)
**What:** A tiny object with two methods injected into `run_dlr_pipeline`/`run_city_pipeline`: `read_history(city, before) -> DataFrame` and `write_result(result, ctx) -> bool`. The default (`None`) keeps today's behavior: `historical_archive.read_history` and `rate_city(archive=True)`. The DB store passes `archive=False` to `rate_city` (so no CSV is written on the runner) and calls the writer after each city's result.
**Why:** DB-02 says the CSV path "stays usable offline for tests and backfill"; Phase 2 adds its cleaning step between the read and `forecast_ampacity`, so the reader must return the same DataFrame shape as `historical_archive.read_history` and the cleaner stays storage-agnostic. Phases 2 and 4 both edit `city_pipeline.py`; they are sequential (Phase 4 depends on 3 which depends on 2), so no concurrent-edit conflict, but Phase 4 plans must start from the Phase 2 result.
**Changes needed in existing code (planner tasks):**
1. `city_pipeline.run_city_pipeline(..., history_reader=None, ...)`: use it instead of `historical_archive.read_history(path=..., city=...)` when given. `[VERIFIED: backend/city_pipeline.py:41]` the line is `history = historical_archive.read_history(path=archive_path, city=city)`.
2. Expose why the forecast is missing (OD-3). Today `forecast = None` for both cold start and a caught failure (`city_pipeline.py:54-61`). Add `result["pipeline"]["forecast_status"]` = `"ok"|"cold_start"|"failed"` (set `"failed"` in the `except` branch). The DB column `forecast_status` records it; Phase 5's live run can fail/alert when `ml` was requested and status is `"failed"`.
3. `result["pipeline"]["detector_model"]` is a filesystem path (`getattr(detector, "model_source", None)`); store only `detector_model_loaded boolean` (do not publish paths; the base table will be anon-readable in Phase 6).
4. Per-field provenance: `observation_composer.make_composed_fetcher` returns a callable with `.provenance` (list of dicts `{"stid", "hour", "air_temp", "wind_speed", "solar_radiation"}` holding the source name per field) `[VERIFIED: backend/observation_composer.py:290-298 rec = {"stid": stid, "hour": ..., f: src}]`. In `run_dlr_pipeline`, record `n0 = len(fetcher.provenance)` before each city and, after, take the last record whose `stid == result["station_id"]` in `fetcher.provenance[n0:]`; its `hour` is `observation_time`, and `air_temp/wind_speed/solar_radiation` map to `temp_source/wind_source/solar_source`. (`out["sources"]` is only a cross-city count summary, not usable per row.) Non-composed providers have no provenance: store NULL.
5. Share the archive's validator: factor the validation block of `historical_archive.read_history` (lines 231-245) into a helper (e.g., `validate_history_frame(df)`) and apply it to the DB frame so the DB path keeps the T-04-07 archive-poisoning protection.
6. `config`: add `RATING_BASIS` (text) and `RATING_CONFIG_VERSION` constants for OD-5 (see Schema). Existing constants `BUNDLE_CONFIG_VERSION = "v1-provisional-2026-10-08"` `[VERIFIED: backend/config.py:74]` and `BUNDLE_RATING_BASIS` cover the shadow bundle values, not these per-conductor ratings; reuse their style, do not repurpose them.

### Pattern 2: Idempotent upsert on (city, valid_time)
**What:** One parameterized statement, executed per city in one transaction; `first_written_at` and `origin='backfill'` semantics protect history.
```python
# Source: statement shape verified against local PostgreSQL 16.14 + psycopg 3.3.6, 2026-10-19
UPSERT_SQL = """
insert into public.city_rating (
  city, valid_time, observation_time, rating_amps, rating_mw, static_rating_amps, static_rating_mw,
  line_voltage_kv, power_factor, status, fallback, fallback_gates, alerts, exhausted, station_id,
  candidates_probed, probe_trail, air_temp_c, wind_perp_ms, wind_speed_ms, wind_direction_deg,
  solar_radiation_wm2, temp_source, wind_source, solar_source, forecast_method, forecast_status,
  forecast_amps, forecast_ci_lower_amps, forecast_ci_upper_amps, forecast_horizon_min,
  forecast_n_observations, forecast_used_by_g6, detector_signal, detector_model_loaded,
  history_rows, usable_history_rows, rating_basis, config_version, origin, run_id, run_attempt,
  pipeline_version)
values (%(city)s, %(valid_time)s, ... same names ..., 'live', %(run_id)s, %(run_attempt)s, %(pipeline_version)s)
on conflict (city, valid_time) do update set
  observation_time = excluded.observation_time, rating_amps = excluded.rating_amps, ...every column except
  city, valid_time and first_written_at ...,
  origin = 'live',
  computed_at = date_trunc('second', now())
"""
# first_written_at is deliberately NOT in the SET list: it keeps the original insert time (Phase 6 peak-age query).
```
Verified behavior: two upserts of the same key left `count = 1` with the second run's values; `first_written_at` unchanged `[VERIFIED: local, t.py]`. (`now()` is the transaction start time, so all four cities written in one transaction share one `computed_at`; fine.)

### Pattern 3: History reader returning the archive's DataFrame shape
```python
# Source: verified locally (dtypes: datetime_utc object/ISO string, floats float64, fallback bool)
HISTORY_SQL = """
select to_char(valid_time at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as datetime_utc,
       city, air_temp_c as air_temp, wind_perp_ms as wind_speed, solar_radiation_wm2 as solar_radiation,
       rating_amps as dlr_amps, static_rating_amps as static_rating, status, fallback, schema_version
from public.city_rating
where city = %s and valid_time < %s and valid_time >= %s
order by valid_time
"""
cols = [d.name for d in cur.description]
df = pd.DataFrame(cur.fetchall(), columns=cols)          # not pd.read_sql (UserWarning on raw psycopg connections)
```
Notes: return `datetime_utc` as the same `YYYY-MM-DDTHH:MM:SSZ` strings the CSV archive uses so CSV and DB frames are interchangeable in tests (a parity test: same rows through both readers give identical `forecast_ampacity` results). `before=` (strictly `<` the slot being computed) makes a same-hour re-run reproducible: otherwise the re-run would see its own earlier row as history and produce a different forecast (DS-NF2). Bound the window (`>= slot - N days`, N is a planning choice; the ML method needs >= `FORECAST_MIN_HISTORY_ROWS` = 12 hourly rows per `config.py` comment at lines 314-316; the Phase 3 backfill is >= 14 days = 336 rows per city) so the read stays small.

### Pattern 4: Backfill loader (DB-03)
Read the Phase 3 archive CSV with `historical_archive.read_history(path, validate=False)`, parse `datetime_utc` to UTC, **drop duplicate (city, slot) keeping the last**, floor to the hour (assert it already is), then `executemany` of an `INSERT ... ON CONFLICT (city, valid_time) DO NOTHING` with `origin='backfill'`, the archive columns mapped to `rating_amps`, `static_rating_amps`, `air_temp_c`, `wind_perp_ms` (the archive's `wind_speed` is the projected wind), `solar_radiation_wm2`, `status`, `fallback`, and the NOT NULL labels (`rating_basis`, `config_version`, MW via `amps_to_mw`). Forecast, alert, source and station columns stay NULL (the archive never stored them), which is why they are nullable. `DO NOTHING` (not `DO UPDATE`) so re-running a backfill can never overwrite richer live rows. `executemany` with a few thousand rows is fine over the pooler; `COPY` cannot do `ON CONFLICT` so skip it `[CITED: psycopg.org/psycopg3/docs/basic/copy.html — page does not mention ON CONFLICT]`. Parity check = per-city `count(*)` from the DB equals per-city count of the de-duplicated CSV (print both and any dropped duplicates; Phase 2 should already have removed them).

### Pattern 5: Roles, grants and RLS (tested)
RLS is enabled on both tables; the only policies are for `dlr_writer`; `anon`/`authenticated` get `REVOKE ALL` now and `GRANT SELECT` + a read policy in Phase 6.
- Verified locally: with RLS enabled and the policy, `dlr_writer` can INSERT/UPSERT/SELECT; DELETE -> `InsufficientPrivilege permission denied for table city_rating`; DDL -> `permission denied for schema public`; `anon` SELECT -> permission denied; **with the policy dropped, SELECT returns 0 rows with no error and INSERT fails with "new row violates row-level security policy"** `[VERIFIED: local]`.
- The migration creates the role without a password (`create role dlr_writer login;`). The owner sets it once, out of band: `alter role dlr_writer with password '<generated>';` (SQL editor or psql as admin). A password in a committed migration would violate DB-04.
- Through the shared pooler the username is `[ROLE].[PROJECT-REF]`, i.e. `dlr_writer.<ref>` `[CITED: supabase.com/docs/guides/database/connecting-to-postgres, "Custom roles"]`. Percent-encode special characters in the password inside the URL `[CITED: supabase.com/docs/guides/database/postgres/roles]`.
- Table owner: tables created by `supabase db push` as `postgres`. Supabase's new default (new projects since 2026-05-30, all existing projects from **2026-10-30**) stops auto-granting `anon`/`authenticated`/`service_role` on new `public` tables; direct Postgres connections are unaffected `[CITED: supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically]`. The migration states its grants explicitly and revokes from `anon, authenticated` so behavior is identical before and after that date.

### Pattern 6: Live smoke test (one command, leaves no rows)
`python backend/supabase_smoke.py` (reads `SUPABASE_DB_URL` from env, optionally via python-dotenv locally). In one transaction that is always rolled back: connect with `connect_timeout=10`; print `current_user`, whether `conn.pgconn.ssl_in_use` is true, and server version; assert both tables exist; assert the writer can `INSERT` the same sentinel key twice with `ON CONFLICT DO UPDATE` and `count(*) = 1`; assert `DELETE` is denied inside a savepoint; assert `select count(*)` of existing rows returns without error (and print the per-city counts so a silent RLS zero is visible after the backfill is loaded: fail if the table is known to be loaded but the writer sees 0). Print only booleans/counts, never the URL. The same script run in a `workflow_dispatch` workflow on `ubuntu-latest` is the falsification probe for "runner reaches the pooler over IPv4" (success criterion 4); that new workflow file needs a human checkpoint before it is pushed.

### Anti-Patterns to Avoid
- **Writing `valid_time = end` (5-minute floor) as the key:** an hourly job at 14:07 and a retry at 14:12 would create two rows. Floor to the hour in the writer and enforce with the CHECK.
- **Using `pd.read_sql` on a psycopg connection:** emits a UserWarning (verified); build the DataFrame from the cursor.
- **Storing only the rating:** the forecast and detector cannot be rebuilt from history without the weather columns.
- **Granting `dlr_writer` `DELETE`/`TRUNCATE`/DDL or using the `postgres` role in CI.**
- **Using `BYPASSRLS` for the writer** when a one-line policy does the job (Supabase: never share credentials of a bypass role) `[CITED: RLS docs]`. (Phase 6's diagram says the writer "bypassrls"; in this design it is policy-based. Both are fine for Phase 6 as long as Phase 6 adds its own anon policy; policies are OR-combined.)
- **Printing or logging the connection URL or its parts.** Use `str(exc)` only (the repo convention, T-03-02); GitHub masks the whole secret but not substrings/derived values `[CITED: docs.github.com using-secrets-in-github-actions, `::add-mask::` for derived values]`.

## Schema Design (DB-01) — recommended columns

All timestamps are `timestamptz` (stored UTC; the client sees the session time zone, Supabase default UTC `[ASSUMED]`). Units are in column names. NOT NULL only where a value always exists. The skeleton below was applied twice with `psql -v ON_ERROR_STOP=1 -1` and the upsert/RLS/privilege behavior was exercised on it `[VERIFIED: local PG 16.14]`; align Phase 6's column names to it.

| Group | Columns (type) | Source |
|-------|----------------|--------|
| Key | `city text` (CHECK in the four `config.LOCATIONS` keys), `valid_time timestamptz` (CHECK hour-truncated), PK (`city`,`valid_time`) | `result["city"]`; hour of `end` |
| Timing | `observation_time timestamptz null` (composer's aligned weather hour), `first_written_at timestamptz not null` (never updated), `computed_at timestamptz not null` (updated on every upsert), both `date_trunc('second', now())` (Phase 6 pitfall 3: avoids odd fractional digits) | composer `provenance[..]["hour"]`; DB clock |
| Rating | `rating_amps`, `rating_mw`, `static_rating_amps`, `static_rating_mw` (double precision, > 0 and finite CHECK on the first two), `line_voltage_kv`, `power_factor` (the constants used for MW) | `result["rating"]`; `amps_to_mw(rating, config.LINE_VOLTAGE_KV, config.POWER_FACTOR)`; `city_point.static_rating` |
| Status | `status text` ('ok'/'fallback'), `fallback boolean`, `fallback_gates text[]`, `alerts text[]`, `exhausted boolean`, `station_id text null`, `candidates_probed int`, `probe_trail jsonb` | `rate_city` keys; `summarize()["fallback_gates"]` |
| Observation inputs | `air_temp_c`, `wind_perp_ms` (projected, what the archive calls `wind_speed`), `wind_speed_ms` (raw measured, `wind_raw`), `wind_direction_deg`, `solar_radiation_wm2` (all nullable) | `result["observation"]` |
| Provenance | `temp_source`, `wind_source`, `solar_source` text | composer provenance |
| Forecast | `forecast_method`, `forecast_status` ('ok'/'cold_start'/'failed'), `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, `forecast_horizon_min`, `forecast_n_observations`, `forecast_used_by_g6` | `result["pipeline"]` |
| Detector | `detector_signal text`, `detector_model_loaded boolean`, `history_rows`, `usable_history_rows` | `result["pipeline"]` |
| Labels (OD-5) | `rating_basis text not null`, `config_version text not null`, `origin text` ('live'/'backfill'), `schema_version int` | new `config` constants; loader |
| Run | `run_id text` (= `GITHUB_RUN_ID`), `run_attempt int` (= `GITHUB_RUN_ATTEMPT`), `pipeline_version text` (= `GITHUB_SHA`[:7], else `git rev-parse --short HEAD`, else `"unknown"`) | env `[CITED: docs.github.com default variables: GITHUB_RUN_ID stays the same on re-run, GITHUB_RUN_ATTEMPT increments, GITHUB_SHA]` |

Value provenance for the sources of these columns (read this session):
- Archive columns, `[VERIFIED: backend/historical_archive.py:46-57]`: `ARCHIVE_COLUMNS: list[str] = ["datetime_utc","city","air_temp","wind_speed","solar_radiation","dlr_amps","static_rating","status","fallback","schema_version"]`.
- `rate_city` return keys, `[VERIFIED: backend/city_rating.py:437-450]`: `"city"`, `"point"`, `"station_id"`, `"candidates_probed"`, `"probe_trail"`, `"rating"`, `"status"`, `"fallback"`, `"alerts"`, `"observation"`, `"exhausted"`, `"archived"`. `status` values per the archive docs: `ok` or `fallback` (`docs/frontend/specs/api-contract.md` section 3 table, read this session).
- Pipeline dict, `[VERIFIED: backend/city_pipeline.py:87-103]`: keys `history_rows`, `usable_history_rows`, `forecast_method`, `forecast_used_by_g6`, `forecast` (`amps`, `ci_lower_amps`, `ci_upper_amps`, `n_observations`, `horizon_min`), `detector_signal`, `detector_model`.
- `summarize()` fallback gates, `[VERIFIED: backend/dlr_orchestrator.py:73-74]`: `gates = [a.split(" ")[0] for a in result["alerts"]]` and `"fallback_gates": sorted(set(gates))` (tokens like `G4`, `EXHAUSTED`).
- Cities, `[VERIFIED: backend/config.py:194-207]`: `CITY_COORDINATES` keys `"AUSTIN"`, `"CORPUS_CHRISTI"`, `"MIDLAND"`, `"EL_PASO"`; `LOCATIONS: tuple[str, ...] = tuple(CITY_COORDINATES)`.
- MW constants, `[VERIFIED: backend/config.py:247-248]`: `LINE_VOLTAGE_KV: float = 345.0`, `POWER_FACTOR: float = 0.95`. Golden value: `amps_to_mw(1825.0, 345.0, 0.95)` = 1036.0153652297765 MW (computed this session; `amps_to_mw` is `(np.sqrt(3) * voltage_kv * amps * pf) / 1000.0`, `backend/ercot_dlr_merger.py:15-20`). Use as a unit-test golden.
- Static ratings (per-conductor A), `[VERIFIED: backend/config.py:47-50]`: AUSTIN 1825.0, CORPUS_CHRISTI 1500.0, MIDLAND 1875.0, EL_PASO 1320.0 — explicitly "Unverified for any specific line segment" and "provisional", which is what OD-5's labelling is about.
- Detector signal values appear as strings: `"not_yet_evaluated"`, `"cold_start"`, `"forecast_residual"`, `"rolling_baseline"`, `"model_trip"`, `"model_clean"`, `"non_finite_guard"`, or `"+"`-joined combinations (`backend/anomaly_detector.py` lines 173, 271, 298, 304, 324, 354, 427; grep-confirmed), so store as free `text`, not an enum.

**Recommended `rating_basis` / `config_version` values (planner picks the final strings; add both as `config.py` constants):** `rating_basis` text stating "per-conductor amperes; static ratings are provisional (owner-supplied bundle averages divided by an assumed subconductor count); line bearings are assumed, not measured; not a verified equipment-limited circuit rating"; `config_version` a string like `"v1-provisional-2026-10-13"` that is bumped whenever `STATIC_RATINGS`, `RATING_BOUNDS_BY_LOCATION`, `CITY_LINE_BEARING_DEG` or `SUBCONDUCTORS_PER_PHASE` change (the repo already does this for `BUNDLE_CONFIG_VERSION`).

### Migration skeleton (tested; no secrets; idempotent)
```sql
-- supabase/migrations/20261019000000_create_city_rating.sql
create table if not exists public.city_rating (
    city text not null constraint city_rating_city_ck check (city in ('AUSTIN','CORPUS_CHRISTI','MIDLAND','EL_PASO')),
    valid_time timestamptz not null constraint city_rating_valid_time_hour_ck check (valid_time = date_trunc('hour', valid_time)),
    observation_time timestamptz,
    rating_amps double precision not null constraint city_rating_rating_amps_ck check (rating_amps > 0 and rating_amps < 'Infinity'::float8),
    rating_mw   double precision not null constraint city_rating_rating_mw_ck   check (rating_mw   > 0 and rating_mw   < 'Infinity'::float8),
    static_rating_amps double precision not null, static_rating_mw double precision not null,
    line_voltage_kv double precision not null, power_factor double precision not null,
    status text not null constraint city_rating_status_ck check (status in ('ok','fallback')),
    fallback boolean not null, fallback_gates text[] not null default '{}', alerts text[] not null default '{}',
    exhausted boolean not null default false, station_id text, candidates_probed integer, probe_trail jsonb,
    air_temp_c double precision, wind_perp_ms double precision, wind_speed_ms double precision,
    wind_direction_deg double precision, solar_radiation_wm2 double precision,
    temp_source text, wind_source text, solar_source text,
    forecast_method text,
    forecast_status text constraint city_rating_forecast_status_ck check (forecast_status in ('ok','cold_start','failed')),
    forecast_amps double precision, forecast_ci_lower_amps double precision, forecast_ci_upper_amps double precision,
    forecast_horizon_min double precision, forecast_n_observations integer, forecast_used_by_g6 boolean,
    detector_signal text, detector_model_loaded boolean, history_rows integer, usable_history_rows integer,
    rating_basis text not null, config_version text not null,
    origin text not null default 'live' constraint city_rating_origin_ck check (origin in ('live','backfill')),
    run_id text, run_attempt integer, pipeline_version text, schema_version integer not null default 1,
    first_written_at timestamptz not null default date_trunc('second', now()),
    computed_at      timestamptz not null default date_trunc('second', now()),
    constraint city_rating_pk primary key (city, valid_time)
);
create table if not exists public.pipeline_run (          -- SCHED-01 run log; Phase 5 fills it
    run_id text primary key, run_attempt integer,
    started_at timestamptz not null default date_trunc('second', now()), finished_at timestamptz,
    window_end timestamptz, provider text, forecast_method text, pipeline_version text,
    cities_ok text[] not null default '{}', cities_failed jsonb not null default '{}'::jsonb,
    provider_errors jsonb, sources jsonb
);
alter table public.city_rating  enable row level security;
alter table public.pipeline_run enable row level security;
revoke all on public.city_rating, public.pipeline_run from anon, authenticated;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'dlr_writer') then
    create role dlr_writer login;            -- password set out of band, never in a migration
  end if;
end $$;
grant usage on schema public to dlr_writer;
grant select, insert, update on public.city_rating, public.pipeline_run to dlr_writer;
drop policy if exists dlr_writer_all on public.city_rating;
create policy dlr_writer_all on public.city_rating  for all to dlr_writer using (true) with check (true);
drop policy if exists dlr_writer_all on public.pipeline_run;
create policy dlr_writer_all on public.pipeline_run for all to dlr_writer using (true) with check (true);
-- add COMMENT ON TABLE / COLUMN for every column with unit text (units also live in the names)
```
Applied twice in a row: second apply only emitted "already exists, skipping" notices; the file is one transaction under `-1`, so a failure leaves nothing half-created (a failed first attempt in this session rolled back cleanly). The `anon`/`authenticated` roles exist on Supabase; a plain local Postgres needs them created first (`create role anon nologin; ...`) — note this for the optional local integration test.

Index decision: none beyond the PK. "Latest per city" with `ORDER BY valid_time DESC LIMIT 1` per city uses the PK as a backward index scan (0.054 ms on 35k rows, `EXPLAIN ANALYZE` `Index Scan Backward using city_rating_pk`); `DISTINCT ON` over the whole table took ~22 ms. Phase 6 plans a `(city, valid_time desc)` index for its `DISTINCT ON` view; that is harmless and it is Phase 6's migration. Size: 35,040 rows (one year, 4 cities hourly) at representative width = **29 MB** total including PK `[VERIFIED: pg_total_relation_size]` vs the 500 MB Free limit.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Migration history/ordering | A Python migration runner with a tracking table | `supabase db push --db-url` | Verified: tracks `supabase_migrations.schema_migrations`, dry run, "up to date" no-op; Phase 6 adds a removable soak-cron migration that a re-apply-everything script would resurrect |
| Idempotency | Check-then-insert in Python | `INSERT ... ON CONFLICT (city, valid_time) DO UPDATE` | Race-free; satisfies CLEAN-03 at the DB level |
| Hour-slot dedupe | Python set logic against the table | PK + `CHECK (valid_time = date_trunc('hour', valid_time))` | The database refuses off-slot rows (verified `CheckViolation`) |
| SQL value escaping | f-string SQL | psycopg parameters (`%(name)s`) | Injection-safe; `Jsonb()` wrapper for dict/list JSON |
| Connection URL parsing/masking | Regex over the URL | `psycopg.connect(url)`; log `conn.info.dsn` (verified: omits the password) | Library handles percent-encoding; `OperationalError` text had host/port but no password `[VERIFIED: local]` |
| Pooling | `psycopg-pool` | One connection per run | One writer, 4 short transactions |
| MW conversion | A SQL generated column | `ercot_dlr_merger.amps_to_mw` (DB-01 says so) | One definition; kV and PF stored for reproducibility |
| Secret scanning | A bespoke scanner | A small pytest regex over `git ls-files` (tests) and, optionally, gitleaks on the owner's machine | Success criterion 4 needs a repeatable check |

**Key insight:** every hard part (idempotency, privilege, RLS, history) is a Postgres feature; the code is parameter shaping and type hygiene.

## Common Pitfalls

### Pitfall 1: `valid_time` not stable across retries
**What goes wrong:** `rate_city` archives `datetime_utc=end`, and `_default_window` floors "now" to 5 minutes (`dlr_orchestrator.py:43-54`), so two runs in the same hour make different keys; duplicates appear and "idempotent" is false.
**How to avoid:** writer computes `valid_time = pd.Timestamp(end).floor("h")` (UTC); the CHECK constraint backs it. The backfill already steps on whole hours. Keep `observation_time` for the aligned weather hour. **Warning sign:** more than 24 rows per city per day.

### Pitfall 2: RLS makes a mis-configured writer see an empty table
**What goes wrong:** without `dlr_writer_all` the reader returns 0 rows silently -> cold start -> no forecast, no error `[VERIFIED: local]`. **How to avoid:** the smoke test and the migration test assert the policy exists; the reader logs a warning when it returns 0 rows for a city that has `history_rows` elsewhere (or simply when `usable_history_rows == 0` after the backfill is loaded).

### Pitfall 3: Re-run changes the forecast
**What goes wrong:** a same-hour retry reads its own earlier row as history. **How to avoid:** read `valid_time < slot`.

### Pitfall 4: Type adaptation and NaN
**What goes wrong:** `double precision` stores NaN and Infinity (verified) which then poison charts; arrays/dicts need correct adaptation. `np.bool_`/`np.float64` happened to adapt in psycopg 3.3.6 (`np.float64` subclasses `float`; `np.bool_` was accepted in my run) `[VERIFIED: local]`, but do not rely on it. **How to avoid:** `build_rating_row` casts to `float/int/bool/str`, maps non-finite floats to `None`, wraps `probe_trail` in `psycopg.types.json.Jsonb([...])` after converting numpy scalars; CHECK constraints (`rating_amps > 0 and < 'Infinity'`) are the backstop.

### Pitfall 5: Direct host from a runner or an IPv4-only laptop
**What goes wrong:** `db.<ref>.supabase.co` is IPv6-only on Free; GitHub Actions is IPv4-only -> "Network is unreachable"/`ENETUNREACH`. **How to avoid:** both the writer URL and the owner's admin URL use the session pooler host copied from the dashboard Connect dialog (`aws-<INDEX>-<region>.pooler.supabase.com`, the `[INDEX]` cannot be derived from the region `[CITED]`). Wrong/short username (missing `.<ref>`) fails at the pooler with a tenant/user error `[ASSUMED: error wording]`.

### Pitfall 6: Transaction-mode surprises
**What goes wrong:** URL pasted with port 6543 -> prepared-statement errors after 5 executions of one statement (psycopg auto-prepares at the 6th). **How to avoid:** use 5432; additionally pass `prepare_threshold=None` to `psycopg.connect` so a port change cannot break it.

### Pitfall 7: `sslmode=require` encrypts but does not verify
Docs: many drivers default to `prefer`; `require` encrypts without verifying the server; `verify-full` needs the downloaded root cert `[CITED]`. Use `sslmode=require` in the URL and assert `conn.pgconn.ssl_in_use` in the smoke test; `verify-full` is optional hardening (local Postgres reported `ssl_in_use False`, as expected without TLS).

### Pitfall 8: Secret leakage
Masking covers the registered secret string, not substrings (password alone, host with ref) or transformations. **How to avoid:** never print the URL or `os.environ`; log `str(exc)` only; no `set -x` in workflow steps that use the secret; pass the secret via `env:` (not on a command line); secrets are not available to workflows from forks `[CITED: docs.github.com]`. Keep the admin (postgres) URL off GitHub entirely (owner's `.env`/shell only).

### Pitfall 9: Free-tier pause stops the whole pipeline
Free projects with low activity over 7 days are paused (restorable up to 1 year); "a few user requests to the database each day" is typically enough `[CITED: supabase.com/docs/guides/platform/free-project-pausing]`; a staff forum reply says actual queries/writes count, an idle connection does not `[CITED: GitHub discussion via search, MEDIUM]`. Hourly upserts are real writes, so the pipeline itself keeps the project active; the risk is if cron-job.org is paused or the runs fail for more than a week. The runbook (Phase 5) should say: after a long pause, restore the project from the dashboard; the writer will fail with a connection error until then.

### Pitfall 10: Backfill semantics
Archive `wind_speed` is the projected perpendicular wind, not the measured speed (`city_rating._project_wind` replaces `wind` and keeps `wind_raw`); load it into `wind_perp_ms`, leave `wind_speed_ms` NULL. Backfill rows are a documented PLACEHOLDER ("regenerate it once any of those change", `backfill_archive.py` docstring), so `origin='backfill'` and the provisional `rating_basis` must be set; a live upsert may overwrite a backfill row, never the reverse.

### Pitfall 11: Phase 6 and Phase 4 contracts drifting
See "Cross-phase contract" below.

## Cross-phase contract (aligned with 06-RESEARCH.md)

I read Phase 6's research (Assumptions Log A1-A13, schema assumptions). This phase commits to:
- A1 names: `public.city_rating` with `city`, `valid_time`, `rating_amps`, `rating_mw`, `status`, `run_id`, `computed_at`, `rating_basis`; PK (`city`,`valid_time`). **Confirmed.** Extra columns exist (list above); Phase 6's `latest_rating` should use an explicit column list rather than `*` if it wants to hide `probe_trail`/`alerts`/`station_id` from the contract (everything in the base table will be anon-readable once Phase 6 adds the read policy, so nothing sensitive may be stored: no paths, no error text, no tokens; `detector_model_loaded` is a boolean for this reason).
- A2: `run_id` = `$GITHUB_RUN_ID` as text (plus `run_attempt` because `GITHUB_RUN_ID` is unchanged on re-run). **Confirmed.** `computed_at` is *updated* on re-upsert, so I added **`first_written_at`, which is immutable**: Phase 6's exact peak-age query must use `first_written_at - lag(valid_time)` instead of `computed_at - lag(valid_time)`.
- A3: `valid_time` is the hour-truncated UTC rating time, DB-enforced. **Confirmed**; weather lag lives in `observation_time`.
- Pitfall 3 (fractional-second timestamps): `computed_at`/`first_written_at` are truncated to whole seconds; `valid_time` is a whole hour.
- Writer privilege: `dlr_writer` is policy-based (no `BYPASSRLS`), not "service role". Phase 6's anon read policy coexists (permissive policies are OR-ed).
- Re-apply safety: Phase 6 migrations should also be idempotent (`create policy` has no `IF NOT EXISTS`: use `drop policy if exists` first, as above) and use the CLI so one-shot objects (soak `cron.schedule`) are not re-created. Phase 6's pg_cron statements will not run on a plain local Postgres; keep Phase 4's local integration test pointed at the Phase 4 file only.
- Grants: Phase 4 leaves `anon`/`authenticated` with no privileges (REVOKE ALL). Phase 6 adds `GRANT SELECT` and the read policy.
- Phase 6 open question 5 (pausing, rate limits): answered in Pitfall 9 and "Free-tier constraints".

## Model artifact provisioning (OD-3) — Supabase Storage as an option

| Fact | Evidence |
|------|----------|
| Artifacts are tiny: `forecast_*.joblib` = 268,512 + 44,641 + 380,744 + 48,241 B (AUSTIN, CORPUS_CHRISTI, EL_PASO, MIDLAND) ~0.74 MB; `anomaly_*.joblib` = 6,577 + 4,897 + 4,193 + 4,289 B ~0.02 MB | `ls -la data/models` this session (main checkout; the worktree lacks them, STATE item 1) |
| Free-plan Storage global file size limit is 50 MB (cannot be raised on Free); total Storage 1 GB | `[CITED: supabase.com/docs/guides/storage/uploads/file-limits; billing page]` |
| A private bucket file is fetched with `GET https://<ref>.supabase.co/storage/v1/object/authenticated/<bucket>/<path>` plus an Authorization header, or via a signed URL | `[CITED: supabase.com/docs/guides/storage/serving/downloads]` |
| The runner would need a Storage-capable credential. A secret key bypasses RLS on everything, so adding it to the runner widens the blast radius beyond the `dlr_writer` URL; alternatively a signed URL stored as a secret expires | reasoning from `[CITED: api-keys docs]`; `[ASSUMED]` that no Storage-only key type exists |
| `.joblib` is pickle: loading an attacker-writable object executes code on the runner | general knowledge `[ASSUMED]`; relevant because a bucket has a separate write path from code review |
| Precedent: `data/shadow/models/` is deliberately NOT git-ignored so the runner gets artifacts via `actions/checkout` (`.gitignore` lines 16-23) | `[VERIFIED: .gitignore:16-23]` |

**Recommendation for Phase 5 to decide:** commit the 8 small `.joblib` files via a `.gitignore` carve-out (e.g., `!/data/models/forecast_*.joblib`, `!/data/models/anomaly_*.joblib` alongside the existing `/data/models/` ignore, using an `/data/models/*` + exceptions form so negation works), reviewed in a PR, no extra secret. Choose Storage only if the team wants to retrain and publish without a commit. Whichever is chosen, add a pre-flight step like `forecast_shadow_check_models.py` that fails the run when a required `forecast_{CITY}.joblib` or `anomaly_{CITY}.joblib` is missing, and record `forecast_status`/`detector_model_loaded` per row (OD-3 requires the degradation be detected and recorded).

## Free-tier constraints

| Item | Value | Source |
|------|-------|--------|
| Database size | 500 MB per project; measured ~29 MB/year here | `[CITED: supabase.com/docs/guides/platform/billing-on-supabase]`; `[VERIFIED: local measurement]` |
| Pausing | Low activity over 7 days; restorable up to 1 year; hourly upserts count as activity | `[CITED: free-project-pausing]`; staff reply MEDIUM |
| Connections | Nano (Free): 60 direct, 200 pooler clients; writer uses 1 | `[CITED: supabase.com/docs/guides/platform/compute-and-disk]` ("Nano compute resources on the Free plan are subject to change") |
| Free projects per account | 2 | `[CITED: billing page]` |
| Egress | 5 GB (REST reads are Phase 6) | `[CITED: billing page]` |
| IPv4 | Direct host IPv6-only; IPv4 add-on is Pro+ ($0.0055/h) and *replaces* the AAAA record; shared pooler is IPv4 on all plans | `[CITED: connecting-to-postgres page; troubleshooting page]` |

## Code Examples

### Connect (no secrets in logs)
```python
# Source: psycopg 3.3.6 behavior verified locally; URL comes from env (GitHub secret) only
import os, psycopg

def connect(url: str | None = None) -> psycopg.Connection:
    url = url or os.environ["SUPABASE_DB_URL"]          # KeyError message names the variable, not a value
    return psycopg.connect(url, connect_timeout=10, prepare_threshold=None,
                           options="-c statement_timeout=30000")
# sslmode=require lives in the URL; log conn.info.dsn (password omitted) or nothing at all, never the URL.
```

### Row shaping (stub-testable pure function)
```python
import math, pandas as pd
from psycopg.types.json import Jsonb
from ercot_dlr_merger import amps_to_mw          # DB-01
import config

def _f(x):  # python float or None; NaN/inf -> None
    if x is None: return None
    x = float(x)
    return x if math.isfinite(x) else None

def build_rating_row(result: dict, end: str, ctx: dict, prov: dict | None) -> dict:
    slot = pd.Timestamp(end).tz_convert("UTC") if pd.Timestamp(end).tzinfo else pd.Timestamp(end, tz="UTC")
    slot = slot.floor("h")
    pipe, fc, obs = result.get("pipeline", {}), (result.get("pipeline") or {}).get("forecast"), result.get("observation") or {}
    static = config.STATIC_RATINGS[result["city"]]          # or city_point.city_point(city).static_rating
    return {
        "city": result["city"], "valid_time": slot.to_pydatetime(),
        "rating_amps": float(result["rating"]),
        "rating_mw": float(amps_to_mw(result["rating"], config.LINE_VOLTAGE_KV, config.POWER_FACTOR)),
        "static_rating_amps": float(static),
        "static_rating_mw": float(amps_to_mw(static, config.LINE_VOLTAGE_KV, config.POWER_FACTOR)),
        "line_voltage_kv": config.LINE_VOLTAGE_KV, "power_factor": config.POWER_FACTOR,
        "status": str(result["status"]), "fallback": bool(result["fallback"]),
        "fallback_gates": sorted({a.split(" ")[0] for a in result["alerts"]}),
        "alerts": [str(a) for a in result["alerts"]], "exhausted": bool(result["exhausted"]),
        "air_temp_c": _f(obs.get("temp")), "wind_perp_ms": _f(obs.get("wind")),
        "wind_speed_ms": _f(obs.get("wind_raw")), "wind_direction_deg": _f(obs.get("wind_direction")),
        "solar_radiation_wm2": _f(obs.get("solar")),
        "probe_trail": Jsonb([{k: (v if isinstance(v, (str, int)) else _f(v)) for k, v in e.items()}
                              for e in result["probe_trail"]]),
        # ... station_id, candidates_probed, forecast_*, detector_*, sources from prov, labels, run ctx
    }
```
Observation keys: `_OBSERVATION_FIELD_MAP` maps `air_temp`->`temp`, `wind_speed`->`wind`, `solar_radiation`->`solar` and `_project_wind` adds `wind_raw` `[VERIFIED: backend/city_rating.py:59-63, 102-108]`.

### Offline stub connection (no DB)
```python
class FakeCursor:
    def __init__(self, log): self.log = log
    def execute(self, sql, params=None): self.log.append((" ".join(sql.split()), params)); return self
    def executemany(self, sql, seq): self.log.append((" ".join(sql.split()), list(seq)))
    def fetchall(self): return []
class FakeConn:
    def __init__(self): self.log = []
    def cursor(self): return FakeCursor(self.log)
    def transaction(self): ...   # context manager no-op
# assert: "on conflict (city, valid_time) do update" in SQL; first_written_at not in the SET list;
# column list of the INSERT is a subset of the columns parsed from the migration file; params are python natives.
```

### Apply migrations (owner, once; re-runnable)
```bash
# SUPABASE_ADMIN_DB_URL = session-pooler URL for role postgres.<ref>, in the owner's shell/.env only
npx supabase@2.121.0 db push --db-url "$SUPABASE_ADMIN_DB_URL" --dry-run   # shows pending files
npx supabase@2.121.0 db push --db-url "$SUPABASE_ADMIN_DB_URL"             # applies; second run: "Remote database is up to date."
# fallback with no Node: psql "$SUPABASE_ADMIN_DB_URL" -v ON_ERROR_STOP=1 -1 -f supabase/migrations/20261019000000_create_city_rating.sql
# once: psql "$SUPABASE_ADMIN_DB_URL" -c "alter role dlr_writer with password '<generated>'"   then build SUPABASE_DB_URL
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| New `public` tables auto-granted to `anon`/`authenticated`/`service_role` | Explicit grants required; direct Postgres connections unaffected | New projects 2026-05-30; all existing projects 2026-10-30 | Migration states grants explicitly (revoke from anon/authenticated); Phase 6 must grant SELECT itself |
| Legacy `anon`/`service_role` JWT keys | `sb_publishable_...` / `sb_secret_...`; legacy deprecated "by the end of 2026" | 2026 | The writer avoids API keys entirely; only the DB URL is a secret here |
| IPv6-only direct connection + IPv4 add-on | Shared pooler (Supavisor) is IPv4 on all plans; session 5432 / transaction 6543 | — | Use the session pooler for CI and owner pushes |
| psycopg2 | psycopg 3 (3.3.6) | — | `Jsonb`, pipeline `executemany`, `prepare_threshold` control |
| Event-trigger "auto-RLS" as the safety net | Explicit `enable row level security` in the migration (the guide's event trigger only affects tables created after it is installed) | — | Do it in the migration; optionally add the trigger as defense in depth |

**Deprecated/outdated:** relying on default grants; `Authorization: Bearer <anon>` examples (Phase 6); `pd.read_sql` with a raw DBAPI connection.

## Runtime State Inventory

Not applicable: this phase adds new objects (tables, role, secrets); it renames/refactors nothing. One related runtime-state item the planner must track: the Supabase project, the `dlr_writer` password and the GitHub secret are external state created by the owner (see Environment Availability).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `valid_time` should be the hour-truncated UTC of the run window end (not the weather observation time) | Schema, Pitfall 1 | If the owner wants observation-time semantics, E2E-02 freshness (OD-4's 90 min) is unreachable when providers lag up to 3 h; change CHECK and writer together |
| A2 | Supabase default DB session time zone is UTC | Schema | Timestamps come back with another offset; parsers must read the offset (Phase 6 helper does) |
| A3 | Wrong pooler username (missing `.<ref>`) yields a "tenant or user not found"-style error | Pitfall 5 | Only affects diagnosis text |
| A4 | No Storage-only credential type exists, so a runner would need a secret key or a signed URL secret | Model provisioning | If a scoped Storage key exists, Storage's blast-radius argument weakens |
| A5 | `.joblib` loading executes pickle code (security argument for git over Storage) | Model provisioning | Low; a general fact, but the recommendation also stands on "no extra secret" |
| A6 | Hosted Supabase Postgres is >= 15 and accepts `create role ... login` from `postgres`/`supabase db push` | Roles | Phase 6 assumes >= 15 too (A12 there). The docs show `create role "role_name" with login password ...` for the dashboard SQL |
| A7 | The pooler accepts custom roles over session mode at `dlr_writer.<ref>` | Pattern 5 | Documented (connecting page, "Custom roles"), but not exercised without a project; first live smoke test decides. Fallback: connect as `postgres.<ref>` (loses least privilege) |
| A8 | GitHub-hosted runners still lack outbound IPv6 | Pitfall 5 | Supabase's page lists GitHub Actions as IPv4-only (page date unknown, third-party sources agree); the Actions smoke run is the falsification probe |
| A9 | Supabase hourly writes keep a Free project active | Pitfall 9 | If project pauses anyway, the pipeline stops; the smoke/health checks and Phase 6 soak would show it |
| A10 | The window length for the history read (N days) and `before=slot` semantics are planning choices | Pattern 3 | None of the facts depend on N beyond >= 12 rows for `ml` |
| A11 | The `supabase` CLI works the same against the real pooler URL as against plain Postgres (verified only the latter) | Migrations | Fallback `psql -1 -f` works with the same URL |
| A12 | Phase 2's cleaning markers are in-memory only (storage-agnostic); if it later persists a "cleaned" flag, it needs an additive migration | Schema | Adds one `alter table ... add column if not exists` migration |

## Open Questions

1. **Confirm `valid_time` = hour-truncated run time (A1).** What we know: Phase 6 already assumes it; OD-4's 90 min only works with it. What is unclear: whether the owner prefers the aligned observation hour. Recommendation: lock the run-slot definition and keep `observation_time` separately; state it in the DB-05 doc.
2. **Who creates the Supabase project, sets the `dlr_writer` password and adds `SUPABASE_DB_URL`?** Owner-only steps (no project exists yet). Recommendation: the plan has a `checkpoint:human-action` with an exact checklist (create project, copy session-pooler host, run `db push`, set the role password, build the URL with `?sslmode=require`, add the repository secret, run the smoke test locally, then in Actions).
3. **History window and what counts as usable history.** Recommend the reader excludes nothing in SQL (fallback filtering stays in `city_pipeline`), bounded to the last N days with N >= the Phase 3 backfill length; the planner picks N.
4. **Failed city: write nothing or a fallback row?** Today an exception inside a city leaves no row (isolated in `run_dlr_pipeline`); a "no observation" city writes a fallback row at the static rating (`exhausted=true`). Recommendation: keep both behaviors, record failures in `pipeline_run.cities_failed` (Phase 5), and let the soak (Phase 6) show the stale city.
5. **Models (OD-3):** git carve-out vs Storage (above); Phase 5 decides, Phase 4 only provides the `forecast_status`/`detector_model_loaded` columns.
6. **Is it acceptable that the whole base table will be world-readable via the publishable key in Phase 6?** Phase 6 raised it; here it constrains what columns may contain. Recommendation: nothing sensitive in any column (already designed so).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 venv (`.venv`) | all code | ✓ | 3.12.13 | — (Actions uses 3.12, `shadow_collect.yml`; system `python3` is 3.9.6, below psycopg's >=3.10) |
| psycopg / psycopg-binary | writer | ✗ not in `.venv` (verified in a scratch venv) | 3.3.6 | none; add pins |
| PostgreSQL client `psql` | optional local integration test, fallback apply | ✓ | 16.14 (Homebrew) | Supabase SQL editor |
| Local Postgres server (`initdb`, `pg_ctl`, `postgres`) | optional local integration test | ✓ | 16.14 (Homebrew) | skip the live test (it is env-gated) |
| Docker | n/a | ✗ | — | Not needed: `db push --db-url` ran without it |
| Supabase CLI | migration apply | ✗ globally; ✓ via npm in a scratch dir | 2.121.0 | `psql -1 -f` |
| Node / npm | CLI install | ✓ | Node 26.9.0, npm 11.19.1 (per Phase 6 research on the same machine; `npm` ran here) | brew/scoop binary |
| Supabase project, `dlr_writer` password, `SUPABASE_DB_URL` secret | DB-01..04 live steps | ✗ (not created) | — | blocks live verification only; all offline work proceeds |
| GitHub Actions runner reaching the pooler | DB-04 | unverified | — | owner's local run proves credentials; an Actions smoke run proves the runner |

**Missing dependencies with no fallback:** a Supabase project (owner action) for the live parts of DB-01/03/04.
**Missing dependencies with fallback:** psycopg (install and pin), Supabase CLI (psql fallback).

## Validation Architecture

`workflow.nyquist_validation` is not set in `.planning/config.json` (the file only has `workflow._auto_chain_active` and `graphify.enabled`; absent = enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (`.venv/bin/python -m pytest -q -p no:cacheprovider`) |
| Config file | `/Users/aphan/Senior_Design/pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Quick run command | `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/supabase_store_test.py backend/tests/supabase_migration_test.py backend/tests/secret_scan_test.py` |
| Full suite command | `.venv/bin/python -m pytest -q -p no:cacheprovider` (last recorded green: 1236 passed, STATE.md) |
| Live (env-gated) | `DLR_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:<port>/<db> .venv/bin/python -m pytest -q backend/tests/supabase_live_test.py` against a throwaway local Postgres; skipped when unset |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-01 | Migration defines every required column group, PK (city, valid_time), CHECKs, RLS enabled, role without password, no secret-looking text | unit (parse SQL text) | `pytest backend/tests/supabase_migration_test.py` | ❌ Wave 0 |
| DB-01 | Migration applies twice without error and enforces PK/CHECKs/privileges | live-local | `pytest backend/tests/supabase_live_test.py` (env-gated) | ❌ Wave 0 |
| DB-01 | Units present in column names or `COMMENT ON` | unit | `::test_every_value_column_has_unit_or_comment` | ❌ Wave 0 |
| DB-02 | `build_rating_row` shape: python-native types, NaN->None, hour-floored `valid_time`, MW equals `amps_to_mw` golden (1825 A -> 1036.0153652297765 MW) | unit | `pytest backend/tests/supabase_store_test.py::test_build_rating_row_*` | ❌ Wave 0 |
| DB-02 | Upsert SQL: `on conflict (city, valid_time) do update`, `first_written_at` not updated, INSERT column list ⊆ migration columns (drift guard) | unit (stub conn) | `::test_upsert_sql_matches_migration` | ❌ Wave 0 |
| DB-02 | Same row twice -> row count unchanged; re-run with different values updates | live-local | `supabase_live_test.py::test_upsert_idempotent` | ❌ Wave 0 |
| DB-02 | History reader returns `ARCHIVE_COLUMNS` shape; CSV vs DB frames give identical `forecast_ampacity` | unit (fake cursor rows) | `::test_history_frame_parity_with_csv` | ❌ Wave 0 |
| DB-02 | Reader uses `valid_time < slot` (re-run reproducibility) | unit | `::test_reader_excludes_current_slot` | ❌ Wave 0 |
| DB-02 | Orchestrator with a fake store: reads via store, writes one row per city, a failing city does not stop the others, CSV default path unchanged | unit | `pytest backend/tests/supabase_store_test.py::test_orchestrator_with_fake_store` (+ existing suite stays green) | ❌ Wave 0 |
| DB-02 | `forecast_status == "failed"` when `forecast_ampacity` raises (OD-3 detection) | unit | `backend/tests/city_pipeline_test.py` additions | ❌ Wave 0 (file arrives with LAND-03) |
| DB-03 | Loader de-duplicates, floors, maps columns, uses `ON CONFLICT DO NOTHING`, reports per-city counts equal to the source CSV | unit + live-local | `::test_backfill_loader_*`, `supabase_live_test.py::test_backfill_counts` | ❌ Wave 0 |
| DB-03 | Live: per-city DB counts equal Phase 3 archive counts | live (owner) | `python backend/supabase_load_backfill.py --csv <phase3 archive> --verify` | ❌ Wave 0 |
| DB-04 | No secret in tracked files (URLs with passwords, `sb_secret_`, JWT-like `eyJ...`, `SUPABASE_DB_URL=` with a value) | unit | `pytest backend/tests/secret_scan_test.py` | ❌ Wave 0 |
| DB-04 | Error/log paths never include the URL/password (inject a URL with a marker password, force failure, assert marker absent from `str(exc)` handling) | unit | `::test_connection_failure_does_not_leak_password` | ❌ Wave 0 |
| DB-04 | Owner's laptop reaches the session pooler as `dlr_writer`, TLS in use, upsert+rollback works, DELETE denied | live (owner) | `python backend/supabase_smoke.py` | ❌ Wave 0 |
| DB-04 | GitHub-hosted runner reaches the pooler using only repo secrets | live (CI, human-gated) | `gh workflow run <smoke workflow>` then `gh run view --log` shows smoke OK, URL absent | ❌ Wave 0 (new workflow: needs human approval before push) |
| DB-05 | Doc lists every column with unit/type/meaning, fallback semantics, provisional label, freshness expectation; `api-contract.md` / `pss_e_handoff.md` link to it | doc check (grep test) | `pytest backend/tests/supabase_migration_test.py::test_schema_doc_covers_every_column` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the quick run command (offline, < 30 s).
- **Per wave merge:** full suite.
- **Phase gate:** full suite green; live smoke from the owner's machine and from an Actions run; backfill parity printed and recorded; secret scan green; before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/supabase_store_test.py`, `supabase_migration_test.py`, `secret_scan_test.py`, `supabase_live_test.py`
- [ ] `backend/supabase_store.py`, `supabase_load_backfill.py`, `supabase_smoke.py`
- [ ] `supabase/migrations/20261019000000_create_city_rating.sql`
- [ ] `requirements.txt`: `psycopg==3.3.6`, `psycopg-binary==3.3.6` (install in `.venv`, `pip check`)
- [ ] `docs/data-science/schema/city_rating_v1.md` and link edits in `docs/frontend/specs/api-contract.md` and `docs/data-science/decisions/pss_e_handoff.md`
- [ ] Owner checklist for the Supabase project, role password and repository secret (human-action checkpoint)

## Security Domain

`security_enforcement` is not set to `false` in `.planning/config.json` (absent = enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (DB credential) | Dedicated `dlr_writer` login with generated password; credential only in an Actions secret; TLS `sslmode=require` |
| V3 Session Management | no | Short-lived connection per run |
| V4 Access Control | yes | GRANT SELECT/INSERT/UPDATE only; RLS on with an explicit writer policy; no DELETE/DDL; `anon`/`authenticated` revoked (Phase 6 grants read) |
| V5 Input Validation | yes | psycopg parameters; CHECK constraints (city set, status set, finite positive rating, hour-aligned `valid_time`); reuse `units_def.validate_pipeline_row` on history frames |
| V6 Cryptography | yes | TLS to the pooler (`require`; `verify-full` optional); no custom crypto; password generated, never committed |
| V7/V8 Error handling & logging | yes | `str(exc)` only; log `conn.info.dsn`; never print URL/env |
| V14 Configuration | yes | Secrets only in Actions secrets / owner `.env` (git-ignored); admin URL never on GitHub; secret-scan test |

### Known Threat Patterns for Supabase Postgres + GitHub Actions

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via city/alert text | Tampering | Parameterized queries only; city CHECK; `Jsonb` for structured data |
| Leaked writer URL in logs | Information disclosure | Env-var injection, no echo/`set -x`, `str(exc)` only, `::add-mask::` for any derived value; rotate password if exposed (`alter role ... with password`) |
| Over-privileged CI credential | Elevation of privilege | `dlr_writer` not `postgres`/service role; no DELETE/DDL; a leak cannot read other schemas or drop tables |
| Silent loss of history from RLS misconfiguration | Denial of service / integrity | Smoke test asserts policy; reader warns on empty history |
| Poisoned rows (NaN, out-of-range) | Tampering | CHECK constraints + writer finite-mapping + read-side `validate_pipeline_row` |
| Forked-PR workflow exfiltrating secrets | Information disclosure | Secrets not passed to fork-triggered workflows; workflow uses `workflow_dispatch` only |
| Backfill overwriting live data | Tampering | `ON CONFLICT DO NOTHING` for loader, `origin` column |
| Unpinned/new dependency (supply chain) | Tampering | Exact pins, legitimacy audit above, `checkpoint:human-verify` before install |

## Sources

### Primary (HIGH confidence)
- Local verification this session: PostgreSQL 16.14 (Homebrew) with roles emulating Supabase, psycopg 3.3.6 in a scratch venv with pandas 2.3.3 / numpy 2.4.3 / python-dotenv 1.2.4 on Python 3.12.13: migration applied twice, upsert idempotence, `first_written_at` immutability, CHECK violations (NaN, Infinity, negative, off-hour `valid_time`, bad status), DELETE/DDL denied, RLS zero-row behavior, `anon` denied, `DISTINCT ON` vs backward PK scan plans, size measurement, `pd.read_sql` warning, `conn.info.dsn` password omission, `ssl_in_use`, `Connection.prepare_threshold == 5`; Supabase CLI 2.121.0 `db push --dry-run`/push/second push with no Docker and no `config.toml`.
- https://supabase.com/docs/guides/database/connecting-to-postgres — connection methods table, ports, IPv6/IPv4, transaction-mode limits, SSL
- https://supabase.com/docs/guides/deployment/database-migrations — `supabase db push`, `schema_migrations`, `migration list`, `migration repair`
- https://supabase.com/docs/reference/cli/supabase-db-push — `--db-url`, `--dry-run`, `--include-all`, `--linked`
- https://supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility-cHe3BP — GitHub Actions on the IPv4-only list; add-on price
- https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically — default-grants timeline (2026-04-28 / 05-30 / 10-30), direct connections unaffected, explicit grants
- https://supabase.com/docs/guides/database/postgres/row-level-security — RLS, `service_role` bypass, grants+RLS in the same migration, no policy = no rows via API
- https://supabase.com/docs/guides/database/postgres/roles — create role with login, role per service, percent-encode passwords
- https://supabase.com/docs/guides/api/api-keys — publishable/secret keys, secret key = `service_role` bypassrls, legacy deprecation by end of 2026
- https://supabase.com/docs/guides/platform/free-project-pausing — 7-day low-activity pause, 1-year restore
- https://supabase.com/docs/guides/platform/billing-on-supabase and /compute-and-disk — 500 MB, 2 free projects, 5 GB egress, Nano 60/200 connections
- https://supabase.com/docs/guides/storage/uploads/file-limits (50 MB Free), /storage/serving/downloads (private bucket download)
- https://www.psycopg.org/psycopg3/docs/advanced/prepare.html — `prepare_threshold`, PgBouncer note; /basic/copy.html — `COPY` bulk load; /basic/usage.html — connection context manager commit/rollback
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/using-secrets-in-github-actions — masking, `::add-mask::`, forks, env var passing; https://docs.github.com/en/actions/reference/workflows-and-actions/variables — `GITHUB_RUN_ID`, `GITHUB_RUN_ATTEMPT`, `GITHUB_SHA`
- PyPI JSON API and pypistats (psycopg, psycopg-binary, psycopg-pool, psycopg2-binary); `npm view supabase`
- Repo files read this session (paths with line ranges cited inline): `backend/city_pipeline.py`, `historical_archive.py`, `dlr_orchestrator.py`, `city_rating.py`, `observation_composer.py`, `backfill_archive.py`, `config.py` (41-52, 74, 170-207, 245-248, 284-301, 558-566), `ercot_dlr_merger.py:15-20`, `ampacity_forecast.py` (74-123, 162-252), `anomaly_detector.py` (signal assignments), `requirements.txt`, `.gitignore`, `pytest.ini`, `.github/workflows/shadow_collect.yml`, `docs/frontend/specs/api-contract.md`, `docs/data-science/decisions/pss_e_handoff.md`, `docs/data-science/schema/` listing, `.planning/workstreams/production-pipeline/{REQUIREMENTS,STATE,ROADMAP}.md`, `phases/06-exposure-e2e-verification/06-RESEARCH.md`

### Secondary (MEDIUM confidence)
- Supabase staff forum reply (via search) that real queries/writes, not idle connections, count as activity
- Supabase "Max rows" default 1000 (via Phase 6 research and search summary)

### Tertiary (LOW confidence)
- Third-party confirmation that hosted runners lack IPv6 (blog posts, GitHub community thread); error-message wording for a bad pooler username

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for psycopg/pins/compatibility (installed and `pip check`ed) and CLI behavior (ran it); MEDIUM for hosted pooler behavior (docs only)
- Architecture: HIGH for schema, upsert, RLS, privileges, sizing (all exercised); MEDIUM for the seam changes (derived from reading the code, not yet implemented) and for Phase 5/6 interplay
- Pitfalls: HIGH for 1-4, 7, 10 (verified or read in code); MEDIUM for 5, 6, 8, 9 (documented)

**Research date:** 2026-10-19
**Valid until:** 2026-10-30 for grant/default-privilege behavior (platform change lands that day; re-check after); otherwise ~30 days. Supabase key and connection docs have changed repeatedly in 2026; re-verify the pooler hostname format and the Connect dialog before the owner's first live step.
