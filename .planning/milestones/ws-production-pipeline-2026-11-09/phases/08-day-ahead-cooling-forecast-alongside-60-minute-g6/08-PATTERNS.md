# Phase 8: Day-Ahead Cooling Forecast - Pattern Map

**Mapped:** 2026-11-08
**Files analyzed:** 22 new or modified
**Analogs found:** 22 / 22 (all analogs are git-tracked source; no `.gsd` mirror paths)

Line numbers are from files read this session. Paths are relative to `/Users/aphan/Senior_Design`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match |
|---|---|---|---|---|
| `backend/day_ahead_forecast.py` (constants, `due_targets`, artifact resolver, `compute_value`, `build_row`) | service | transform / request-response | `backend/forecast_conductor_refit.py` (loader use) + RESEARCH "Pattern 1/2" snippets | role-match |
| `backend/day_ahead_band.py` (build offline, `load_verified`, live rolling, `apply_band`) | utility | batch / transform | `backend/ampacity_forecast.py:505-536` (band) + `docs/.../2026-11-02_horizon_comparison/build_rows.py` (builder) | role-match |
| `backend/dlr_day_ahead.py` (per-city child CLI, `--output` JSON, only DB opener) | service / CLI | request-response + CRUD insert | `backend/dlr_orchestrator.py` child contract used by `dlr_live_run.run_city` | role-match |
| `backend/day_ahead_contract.py` (Python twin of view columns) | config / contract | n/a | `backend/latest_rating_contract.py` | exact |
| `backend/dlr_live_run.py` (MODIFY: stage after exit code, default off in `run_live`) | orchestrator | event-driven / subprocess | itself, `run_city` 312-337 and `run_live` 353-431 | exact |
| `backend/dlr_live_check_models.py` (MODIFY: day-ahead list, non-fatal tier) | utility | file-I/O | itself, 64-74, 107-187, 190-220 | exact |
| `backend/live_run_log.py` + `backend/supabase_store.py` (MODIFY: optional `day_ahead` run-row key) | model / store | CRUD | `supabase_store.py:76-90, 762-806` | exact |
| `data/models/LIVE_ARTIFACT_HASHES.sha256` (MODIFY: +4 cooling +1 band) | config | file-I/O | itself (sha256sum format) | exact |
| `data/day_ahead/day_ahead_bands_v1.json` (NEW artifact) | config | batch | `data/models/conductor_refit/v3-powersystems-2026-11-02/ARTIFACT_HASHES.sha256` for hash convention; JSON schema from RESEARCH Pattern 5 | partial |
| `supabase/migrations/<ts>_day_ahead_forecast_store.sql` (migration 1, write side) | migration | CRUD | `supabase/migrations/20261019000000_create_city_rating.sql` | exact |
| `supabase/migrations/<ts>_expose_day_ahead_forecast.sql` (migration 2, view, grants, `assert_fresh`) | migration | request-response | `supabase/migrations/20261026195124_expose_latest_rating.sql` | exact |
| `supabase/ops/verify_exposure.sql` (MODIFY: generalise "two objects") | config / ops SQL | request-response | itself, lines 62-73, 123 per RESEARCH Pitfall 6 | exact |
| `docs/integration/rest-api.md`, `docs/data-science/schema/day_ahead_forecast_v1.md`, `pss_e_handoff.md` | docs | n/a | existing `rest-api.md` column table parsed by `rest_api_doc_test.py` | exact |
| `backend/tests/day_ahead_forecast_test.py` | test | unit/integration | `backend/tests/dlr_live_run_test.py`, `forecast_shadow_demo_test.py` fixtures | role-match |
| `backend/tests/day_ahead_band_test.py` | test | unit | `backend/tests/dlr_live_check_models_test.py` (tmp manifest style) | role-match |
| `backend/tests/day_ahead_migration_test.py` | test | local PG | `backend/tests/expose_migration_test.py` + `tests/local_pg.py` | exact |
| `backend/tests/dlr_live_day_ahead_stage_test.py` | test | unit (fake children) | `backend/tests/dlr_live_run_test.py` | exact |
| `backend/tests/dlr_live_check_models_test.py` (MODIFY: "all 8", `len(lines)==8` at 76-92, 183-194) | test | unit | itself | exact |
| `backend/tests/production_conductor_test.py` (MODIFY: add module to `PRODUCTION_CALLERS`, line 209-211) | test | AST | itself | exact |
| `backend/tests/rest_api_doc_test.py` (MODIFY: second parsed table) | test | text | itself, `_column_rows` 30, `test_doc_column_table_matches_the_contract` 57 | exact |
| `backend/tests/supabase_run_log_test.py`, `live_run_log_test.py`, `expose_migration_test.py` (MODIFY, additive) | test | pinned counts | themselves, see Pitfall 3 in RESEARCH | exact |
| `backend/day_ahead_verify.py` (read-only D-17 verify script) | utility | request-response | `backend/e2e_verify_readonly.py` | role-match |

## Pattern Assignments

### `backend/dlr_live_run.py` (MODIFY, orchestrator, subprocess)

**Analog:** itself.

**Imports to reuse** (lines 53-66): `argparse, json, logging, os, re, subprocess, sys, tempfile, time`, `from datetime import datetime, timezone`, `import config`, `import live_run_log`.

**Per-child pattern to copy** (`child_argv` 143-155, `run_city` 312-337): sequential child, `cwd=REPO_ROOT`, kill timeout, partial output kept, `_emit`, `classify`-style record with timing.
```python
def child_argv(city, end, output_path):
    return [os.path.abspath(sys.executable), ORCHESTRATOR, "--cities", city, ..., "--output", output_path]
...
try:
    proc = subprocess.run(child_argv(city, end, output_path), cwd=REPO_ROOT, env=env,
                          capture_output=True, text=True, timeout=timeout_s)
except subprocess.TimeoutExpired as exc:
    timed_out = True
    returncode, stdout_text, stderr_text = None, _as_text(exc.stdout), _as_text(exc.stderr)
...
record.update(started_at=_stamp(started), finished_at=_stamp(datetime.now(timezone.utc)),
              duration_s=round(duration, 1))
```
A day-ahead child gets its own `day_ahead_child_argv(city, output_path)` (same abspath-executable rule, `PYTHONPATH=backend`, `cwd=REPO_ROOT`; RESEARCH Pitfall 14).

**Stage placement** (lines 426-431). Exit code is computed first; stage goes after, inside try/except; new run-row save is counted outside `run_log["failed"]`:
```python
state["finished_at"] = _stamp(datetime.now(timezone.utc))
save_run_row()
state["exit_code"] = 0 if all(live_run_log.is_healthy(r) for r in records) and run_log["failed"] == 0 else 1
state["run_log"] = run_log if record_run else None
# NEW, after the three lines above:
# if day_ahead:
#     try: state["day_ahead"] = run_day_ahead_stage(...); save_day_ahead_row()   # separate counter
#     except Exception as exc: log.error("day-ahead stage failed (%s): %s", type(exc).__name__, redact(exc, env))
```
`run_live(...)` signature at 353-354 gains `day_ahead=False`; `main` (502) turns it on and adds `--no-day-ahead`. Keep `CITY_TIMEOUT_S = 300` (line 75) and the "run:" line pinned by `dlr_live_workflow_test.py`.

**Error/redaction:** `redact(exc, env)` (158-190) on every logged or recorded reason; `save_run_row` wrapper at 396-405 is the model for a best-effort write ("must never stop the cities").

---

### `backend/dlr_live_check_models.py` (MODIFY, utility, file-I/O)

**Analog:** itself.

**Keep** `required_artifacts()` (64-74) returning the original 8, so the existing "all 8" assertions stay valid. Add a sibling, lazy imports only (circular import: `forecast_conductor_refit` imports this module at its top):
```python
def required_day_ahead_artifacts():
    import day_ahead_forecast, forecast_conductor_refit as fcr      # lazy: cycle
    ...  # (kind "day_ahead_cooling", city, path) via fcr.production_differs(city) + pinned refit version; plus ("day_ahead_band", "", band_path)
```
**Copy the verify loop** (128-144): presence, then `entries.get(_key(path))`, then `sha256_file`, never loading while a problem is open. Iterate it over a second list and return day-ahead problems separately (non-fatal tier, D-13a).
**Main change** (209-220): live-8 problems still `return 1`; day-ahead problems print `::warning::` lines and exit 0.
```python
problems = check(MANIFEST_PATH)
if problems:
    print(f"ERROR: {len(problems)} live model problem(s); ...", file=sys.stderr)
    ...
    return 1
```
`write_manifest` (163-187) hashes `required_artifacts()` only; extend it to include the day-ahead list (sorted by `_key(path)`, same `<hex>  <path>` format, header line 178-181). Strict load for cooling must be `make_headline_loader(...)(city, "ml_cooling_corrected")`, not a bare `joblib.load`.

---

### `backend/day_ahead_forecast.py` (NEW, service, transform)

**Analog:** `backend/forecast_conductor_refit.py` (loader, 347-396) and the verified chain in RESEARCH Pattern 1 (ran offline).

**Loader and chain (D-03, D-14):**
```python
DAY_AHEAD_REFIT_VERSION = "v3-powersystems-2026-11-02"      # pinned, NOT config.RATING_CONFIG_VERSION
refit = {c for c in config.LOCATIONS if fcr.production_differs(c)}   # forecast_conductor_refit.py:396
loader = fcr.make_headline_loader(DAY_AHEAD_REFIT_VERSION, refit, root=fcr.REFIT_ROOT, frozen_manifest=fcr.FROZEN_MANIFEST)
model  = loader(city, "ml_cooling_corrected")          # loader.served[...]["sha256"/"source"] -> row identity
point  = city_point.production_city_point(city)
anchor = shadow.fetch_live_anchor_observation(city, now)
row, ts = shadow.fetch_live_forecast_for_valid_time(city, T, 1440, lat=lat, lon=lon, decision_time=now)
frame = shadow.validate_and_prepare_shadow_row(row, city=city)
frame = shadow._enrich_city_frame_for_correction(frame, anchor=anchor, city=city, valid_time=T, geometry=point)
amps  = float(shadow.CoolingCorrectionShadowMethod(model).predict(frame, point))
```
**Due targets:** copy the `due_targets(now)` pure function from RESEARCH "Code Examples" (grid `T.hour % 6 == 0`, `now < T <= now + 18 h`); missing = due minus existing `(city, valid_time)` keys. Read the lag from `forecast_shadow_pipeline._DEFAULT_PUBLICATION_LAG_HOURS` (line 189), do not copy it.
**Error handling:** `StaleOrMissingDataError`, hash `ArtifactIntegrityError`, load errors each mean no row plus a redacted reason (D-16). Never fall back to `raw_forecast`. Never read or branch on `frame.attrs["geometry"]` (it is Drake; RESEARCH Pitfall 10).
**AST rule:** module must name `production_city_point` and never `city_point.city_point(...)`; add to `PRODUCTION_CALLERS` in `backend/tests/production_conductor_test.py:209-211`.

---

### `backend/day_ahead_band.py` (NEW, utility, batch/transform)

**Analog:** `backend/ampacity_forecast.py` lines 516-536 (empirical band, clamp) and `docs/data-science/exploratory/2026-11-02_horizon_comparison/build_rows.py` (provenance of the TEST rows).

**Band convention to copy exactly:**
```python
q_lo, q_hi = quantiles                      # config.FORECAST_BACKTEST_QUANTILES = (0.05, 0.95), config.py:506
ci_lower = point_forecast + float(np.quantile(residuals, q_lo))
ci_upper = point_forecast + float(np.quantile(residuals, q_hi))
if ci_lower > point_forecast or ci_upper < point_forecast:     # band excludes its centre: clamp + log warning
    ci_lower = point_forecast; ci_upper = point_forecast
```
Residual sign: `truth - forecast`. Store offsets (not absolute edges) per city x UTC hour in a deterministic JSON (`json.dumps(obj, sort_keys=True, indent=2) + "\n"`). Build from the tracked `docs/data-science/exploratory/2026-11-02_horizon_comparison/rows_production.csv` (3136 rows, 196 per group); record the CSV sha256 inside the artifact. Guard: `valid_time.min() >= 2026-03-18T00:00Z` and `.max() < 2026-09-30T00:00Z` (constants at `forecast_test_split_score.py:59-60`). Verify the artifact hash against the manifest (via `dlr_live_check_models.sha256_file` / `read_manifest`) before parse.
**Live rolling band:** SQL join `day_ahead_forecast d` to `city_rating c` on `(city, valid_time)`, `c.status='ok' and not c.fallback and not c.exhausted and c.origin='live'`, equal `config_fingerprint`; residual `c.rating_amps - d.amps`; band per `extract(hour ...)`. Switch-over threshold is an `[ASSUMED]` 60 pairs / 120 window / must straddle 0 (owner discretion, state in contract).
**Anti-peeking:** do not import `read_city_log_entries` or touch `data/shadow/predictions` or `anchored_pair_frame_*_2026-09-30_*`.

---

### `backend/dlr_day_ahead.py` (NEW, per-city child CLI)

**Analog:** the orchestrator-child contract used by `run_city` (`--output` JSON file read by `_load_output`, `dlr_live_run.py:297-302`; secrets via env only; exit 0 on none-due). Use `supabase_store.connect()` (317) and `run_context()` (408), `rating_config_fingerprint(city)`, `file_sha256` (500), `finite` (443). Insert pattern (bound params only, first write wins):
```sql
insert into public.day_ahead_forecast (city, valid_time, issued_at, ...)
values (%(city)s, %(valid_time)s, %(issued_at)s, ...)
on conflict (city, valid_time) do nothing
```
(contrast `supabase_store._build_upsert_sql`, 149-170, which is `do update`; the day-ahead table must not rewrite `issued_at`.) Reasons go only to the `--output` JSON (redacted) and then `pipeline_run.day_ahead`, never into the public table.

---

### `backend/supabase_store.py` / `backend/live_run_log.py` (MODIFY, store, CRUD)

**Analog:** `supabase_store.py:76-90` and `upsert_run` 762-806.
```python
PIPELINE_RUN_COLUMNS = ("run_id", ..., "sources")         # append "day_ahead" LAST
PIPELINE_RUN_JSONB = ("cities_failed", "provider_errors", "sources")   # append "day_ahead"
```
`upsert_run` accepts any subset containing `run_id`, so the stage can send `{run_id, day_ahead}` alone. `live_run_log.build_run_row` must emit `day_ahead` only when `state` carries it (RESEARCH Pitfall 4: code deployed before the column exists must not break rating-stage writes). Additive guards to update: `supabase_store.build_run_row` check `tuple(row) != PIPELINE_RUN_COLUMNS` (~757), `supabase_run_log_test.py:112-113`, `live_run_log_test.py:195`.

---

### `backend/day_ahead_contract.py` (NEW, contract twin)

**Analog:** `backend/latest_rating_contract.py` (exact).
```python
STORED_COLUMNS: tuple[str, ...] = ("city", "valid_time", ...)      # lines 36-68
COMPUTED_COLUMNS: tuple[str, ...] = ("age_minutes", "is_stale", "is_provisional")   # 71
LATEST_COLUMNS = STORED_COLUMNS + COMPUTED_COLUMNS                 # 73
```
Docstring states the one-way rule (rename/drop never, append only). Add `DAY_AHEAD_LABEL = "day-ahead-24h; engineering-selection; not-validated"`, `UPCOMING_COLUMNS`, `STATUS_COLUMNS`, stdlib only. Test twin: `rest_api_doc_test.py` (`_column_rows` 30, `test_doc_column_table_matches_the_contract` 57) gets a second parsed table; also a migration-vs-contract column test like `expose_migration_test.py`.

---

### `supabase/migrations/<ts>_day_ahead_forecast_store.sql` (migration 1)

**Analog:** `supabase/migrations/20261019000000_create_city_rating.sql` (exact).

Copy: header comment block (what it creates, idempotent, owner applies with `supabase db push --db-url ...`, no credential); `create table if not exists public.<t> (... constraint <t>_city_ck check (city in ('AUSTIN','CORPUS_CHRISTI','MIDLAND','EL_PASO')) ...)`; named checks `... check (x > 0 and x < 'Infinity'::float8)` and `... ~ '^[0-9a-f]{64}$'`; `first_written_at timestamptz not null default date_trunc('second', now())`; `constraint <t>_pk primary key (city, valid_time)`; then:
```sql
alter table public.<t> enable row level security;
revoke all on public.<t> from anon, authenticated;
grant usage on schema public to dlr_writer;
grant select, insert on public.<t> to dlr_writer;      -- insert only (A4), not "select, insert, update"
drop policy if exists dlr_writer_all on public.<t>;
create policy dlr_writer_all on public.<t> for all to dlr_writer using (true) with check (true);
```
Plus a grid CHECK `valid_time = date_trunc('hour', valid_time) and extract(hour from valid_time at time zone 'UTC')::int % 6 = 0`, `horizon_minutes = 1440`, `forecast_method = 'ml_cooling_corrected'`, `band_source in ('test-split','live-rolling')`, and `alter table public.pipeline_run add column if not exists day_ahead jsonb;`. Every column gets `comment on column ... is '<unit or none (kind)>: ...'` unit first. Never edit the three applied migrations (sha256-pinned). Grant nothing to anon here. Re-apply safe.

---

### `supabase/migrations/<ts>_expose_day_ahead_forecast.sql` (migration 2)

**Analog:** `supabase/migrations/20261026195124_expose_latest_rating.sql` (exact).

Copy: `create or replace view public.<v> with (security_invoker = true) as select ... order by city, valid_time;` (lines ~51-91); a `comment on view` and a `comment on column` per view column (view comments do not inherit); privilege block (~157-170):
```sql
revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
grant select on public.city_rating, public.latest_rating, public.<day_ahead objects> to anon, authenticated;
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
drop policy if exists <t>_public_read on public.<t>;
create policy <t>_public_read on public.<t> for select to anon, authenticated using (true);
```
IMPORTANT: re-state the full grant list (city_rating + latest_rating + new objects) because `revoke all on all tables` precedes the grant. Then `create or replace function public.assert_fresh(max_age_minutes integer default 90)` with the SAME signature (no overload -> HTTP 300), `security invoker`, `stable`, `set search_path = ''`, schema-qualified names, `raise ... using errcode = 'PT503'`, new additive key `day_ahead_late`, clause armed only when `exists (select 1 from public.day_ahead_forecast)`; end with `notify pgrst, 'reload schema';`. Copy the existing function body from lines of that migration beyond 140 (read it in full before writing; I did not excerpt it here).

---

### `backend/tests/day_ahead_migration_test.py`, `dlr_live_day_ahead_stage_test.py` and friends

**Analogs:** `backend/tests/expose_migration_test.py` (privilege sweep, `_VERIFY_CHECKS` 316-335, pinned applied-migration sha256 36-39) with `backend/tests/local_pg.py` (run with `DLR_TEST_PG_AUTOSTART=1`); `backend/tests/dlr_live_run_test.py` (fake orchestrator, `_no_network` and `_no_database` autouse fixtures, `requests.get` guard) for the stage test; `backend/tests/dlr_live_check_models_test.py` (`_write_manifest` 42, `models` fixture, `load_spy`, tamper test ~106-117 asserting `load_spy == []`) for hash-before-load and warning tier; `forecast_shadow_demo_test.py` `_fake_shared_inputs_factory` plus a monkeypatch of `forecast_shadow_demo._resolve_next_valid_time` for the parity test. Each new migration must be applied twice in tests (re-apply safe). Offline test: committed cooling and band files must match the committed manifest (like `test_the_committed_models_match_the_committed_manifest`, line 216) so a mismatch fails before any push (D-13a).

## Shared Patterns

### Hash before unpickle
**Source:** `backend/forecast_conductor_refit.py:347-396` (`make_headline_loader`) and `dlr_live_check_models.py:77-104`.
**Apply to:** `day_ahead_forecast.py`, `dlr_day_ahead.py`, pre-flight. Refit branch hashes bytes then loads the same bytes; frozen branch hashes then calls `load_correction_model`. Band JSON verified the same way (it is not a pickle).

### Secret redaction / public table hygiene
**Source:** `dlr_live_run.redact` (158) and `supabase_store.redact`. **Apply to:** every logged or recorded failure reason, step summary, `pipeline_run.day_ahead`. The public `day_ahead_forecast` table carries no exception text (OD-6). Docs and migrations carry only placeholders like `<SUPABASE_URL>` (secret scan walks all tracked files).

### Privilege model
**Source:** the two migrations above. **Apply to:** migrations 1 and 2, `verify_exposure.sql` (generalise "two objects" list and the `count(*) = 4` select-grant check, per RESEARCH Pitfall 6), `expose_migration_test._VERIFY_CHECKS`.

### Frozen paths
**Apply to:** all new files. Nothing under `backend/forecast_shadow_*.py`, `data/shadow/models`, the 15 files in `backend/tests/golden_shadow_capture.py:65-83`, `shadow_collect.yml`. `dlr_live.yml` and the pinned run lines in `dlr_live_workflow_test.py` stay unchanged. Frozen-path test counts untracked files (`cond02_shadow_golden_test.py`).

### Offline-by-default tests
**Source:** `dlr_live_run_test.py` fixtures. **Apply to:** all new Python tests; real network never touched.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `data/day_ahead/day_ahead_bands_v1.json` | artifact | batch | No existing JSON hashed artifact in the live manifest; format is sha256sum line, schema from RESEARCH Pattern 5. Path is not gitignored (`data/models/*` is). |
| `day_ahead_status` view / missing-target `is_late` flag | view | request-response | `latest_rating` is distinct-on-newest; a missing row cannot be expressed per-row. Use the `values`-list left join pattern already in `assert_fresh` (expose migration, function body). |
| Stage budget gate (`remaining = 1200 - used`, `skipped_budget`) | logic | event-driven | No existing shared-budget logic; arithmetic pinned by `dlr_live_workflow_test.py:55-65` (child_seconds == 1200). |

## Metadata

**Analog search scope:** `backend/`, `supabase/migrations`, `supabase/ops`, `backend/tests`, `docs/data-science/exploratory/2026-11-02_horizon_comparison`.
**Tracked-source gate:** `git ls-files` confirmed `data/models/LIVE_ARTIFACT_HASHES.sha256`, `rows_production.csv`, `build_rows.py`, `tests/local_pg.py`, `tests/dlr_live_run_test.py` are tracked.
**Pattern extraction date:** 2026-11-08
