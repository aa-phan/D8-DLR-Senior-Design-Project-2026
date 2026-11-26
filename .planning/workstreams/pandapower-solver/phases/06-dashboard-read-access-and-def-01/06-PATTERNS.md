# Phase 6: Dashboard Read Access and DEF-01 - Pattern Map

**Mapped:** 2026-11-26
**Files analyzed:** 13 (2 new SQL/test/doc creations plus 11 edits; see table)
**Analogs found:** 13 / 13 (all analogs are git-tracked; verified with `git ls-files`)

Privacy: nothing under `data/private/` was opened. No secret or connection string is quoted.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `supabase/migrations/20261126200000_latest_grid_study_per_solver.sql` (new) | migration (view replace) | request-response (read) | `supabase/migrations/20261118200000_psse_run_solver_tag.sql` lines 1-45 header, 82-140 view | exact |
| `supabase/ops/verify_exposure.sql` (edit, 36 to 37) | ops check | batch read-only | itself, marker regions lines 127-146 and 325-364 | exact |
| `supabase/ops/verify_solver_tag.sql` (edit, retire ord 7) | ops check | batch read-only | itself, lines 125-148 | exact |
| `backend/grid_study_contract.py` (edit) | utility (contract twin) | transform | itself | exact |
| `backend/tests/grid_study_per_solver_test.py` (new) or extension of `grid_study_expose_test.py` | test (text + DB tier) | request-response | `backend/tests/grid_study_expose_test.py` and `backend/tests/solver_tag_owner_check_test.py` | exact |
| `backend/tests/solver_tag_owner_check_test.py` (edit) | test | request-response | itself, lines 44-52, 272-288, 325-349 | exact |
| `backend/tests/expose_migration_test.py` (edit) | test | batch | itself, `_VERIFY_CHECKS` line 310 | exact |
| `backend/tests/psse_results_migration_test.py` (edit) | test | batch | itself, lines 38, 91-98 | exact |
| `backend/tests/day_ahead_expose_test.py` (edit) | test | batch | itself, lines 127-137 | exact |
| `backend/tests/grid_study_expose_test.py` (docstring edit only) | test | request-response | itself | exact |
| `docs/integration/rest-api.md` (prose edit) | doc | n/a | itself (keep `##` headings; `rest_api_doc_test.py` pins them) | exact |
| `docs/data-science/decisions/<tracked name, e.g. 06_def01_replacement.md>` (new, D-08) | doc / hand-over text | n/a | `docs/data-science/decisions/pandapower_live_write_decision.md` and `pandapower_hourly_runbook.md` (tracked decision docs that Phase 5 text tests read) | role-match |
| `.planning/.../06-DEF01-REPLACEMENT.md` (new, one-line pointer) | doc | n/a | none needed | n/a |

## Pattern Assignments

### `supabase/migrations/20261126200000_latest_grid_study_per_solver.sql` (migration, read view)

**Analog:** `supabase/migrations/20261118200000_psse_run_solver_tag.sql` (never edit it; it stays byte-identical).

**Header pattern** (analog lines 1-45): comment-only `--` lines first, no `password`, `postgres://`, `postgresql://`, `create role`, `alter role`. State what is replaced, grants unchanged, why `security_invoker = false`, additive, idempotent, apply order. New header must warn that re-applying only `20261118200000_psse_run_solver_tag.sql` afterwards restores the PSS/E-only view, and that the owner applies it only after the Phase 5 soak with `supabase db push --db-url ...` then runs the three read-only checks (counts 6, 7, 37).

**Statement to copy** (analog lines 82-117 changed as in RESEARCH Pattern 1, probe-verified). The delta from the analog is exactly:
```sql
-- analog lines 83-90 (old)
with newest_run as (
    select r.run_id, r.slot_time, r.finished_at, r.outcome
      from public.psse_run r
     where r.outcome in ('ok', 'fallback')
       and r.solver = 'psse'
     order by r.slot_time desc, r.finished_at desc, r.run_id desc
     limit 1
)
-- new
with newest_run as (
    select distinct on (r.solver) r.solver, r.run_id, r.slot_time, r.finished_at, r.outcome
      from public.psse_run r
     where r.outcome in ('ok', 'fallback')
     order by r.solver, r.slot_time desc, r.finished_at desc, r.run_id desc
)
```
Then `n.solver,` replaces `'psse'::text as solver,` (analog line 92); the other 19 select items (lines 93-111) are copied word for word; `from newest_run n join public.psse_dispatched_capacity d on d.run_id = n.run_id and d.run_outcome = n.outcome` stays (lines 112-113); `order by d.city, n.solver;`.

**Grants** (analog 116-117, copy verbatim):
```sql
revoke all on public.latest_grid_study from public, anon, authenticated;
grant select on public.latest_grid_study to anon, authenticated;
```

**Comments** (analog 119-140): reissue `comment on view` and all 20 `comment on column`. Only two texts change (D-06): the view comment (change "one row per city" to per solver, up to 8 rows, filter on solver; delete the closing "Until the per-solver view replaces it..." sentence) and the `solver` column comment (analog line 121, drop "pandapower rows arrive in a later release"). Lines 122-140 (19 comments) stay word for word.

No `alter`, `drop`, data change, role or credential. No SHA-256 pin of this file until applied live.

---

### `supabase/ops/verify_exposure.sql` (ops check, 36 to 37)

**Analog:** itself. Put the new CTE strictly inside `-- BEGIN grid_study_ctes` ... `-- END grid_study_ctes` (lines 127-146) and the new check inside `-- BEGIN grid_study_checks` ... `-- END grid_study_checks` (lines 325-364). `psse_results_migration_test._exposure_checker_without_grid_study` asserts each region occurs once and replaces four exact fragments (`",\n           ('latest_grid_study')\n"`, `"(select count(*) from select_grants) = 12,"`, `"' of 12'"`, `"the six published objects: "`), so do not reformat those.

**CTE shape to follow** (lines 136-145; comma-led, region ends without trailing comma):
```sql
psse_readable as (
    select t.relation, r.rolname
      from psse_tables t
     cross join (values ('anon'), ('authenticated')) as r(rolname)
     where to_regclass('public.' || t.relation) is not null
       and has_table_privilege(r.rolname, to_regclass('public.' || t.relation), 'select')
)
-- END grid_study_ctes
```
Add `,\nnewest_complete_run as (...)` after `psse_readable )` and before the END marker (RESEARCH Pattern 3 has the probe-verified SQL).

**Check shape to follow** (lines 356-363, `union all` + `select 'name', coalesce(..., false), 'counts-only detail'`):
```sql
    union all
    select 'latest_grid_study_one_row_per_city_per_solver',
           coalesce((select count(*) = count(distinct (solver, city)) from public.latest_grid_study), false),
           'rows=' || coalesce((select count(*) from public.latest_grid_study)::text, 'view missing')
```
Insert the new check `latest_grid_study_has_each_solvers_newest_complete_run` (RESEARCH Pattern 3) before `-- END grid_study_checks`. Detail holds counts only. The existing `..._one_row_per_city_per_solver` check stays true and unchanged. Result order is `order by check_name`.

---

### `supabase/ops/verify_solver_tag.sql` (retire check 7)

**Analog:** itself, lines 125-148. Delete the `union all select 7, 'latest_grid_study_reads_psse_runs_only', ...` block (lines 138-146) so the `(select 6, ...)` block ends the union before `) as checks order by ord;`. Also delete the header paragraph about check 7 (RESEARCH says header lines 35-38). Pattern of the check being removed:
```sql
    select 7,
           'latest_grid_study_reads_psse_runs_only',
           coalesce(position('solver = ''psse''' in pg_get_viewdef(to_regclass('public.latest_grid_study'))) > 0, false),
```
Reason: definition-text match goes false by design.

---

### New tests for the per-solver view (DB tier)

**Analog:** `backend/tests/solver_tag_owner_check_test.py` (fixtures `pg`, `clean_pg` lines 183-187; helpers `_complete_run`, `_insert_complete`, `_view_rows`) plus `backend/tests/grid_study_expose_test.py` (`_session`, whitelist and table-refusal tests).

**Seeding helper** (solver_tag_owner_check_test lines 190-198):
```python
def _complete_run(n, prefix="psse", started=STARTED, **run_changes):
    run_id = psse_local_pg.make_run_id(n, started, prefix=prefix)
    rows = psse_local_pg.valid_run_rows(run_id, started)
    rows["psse_run"] = [dict(rows["psse_run"][0], **run_changes)]
    return run_id, rows

def _insert_complete(conn, rows):
    for table in psse_local_pg.RESULT_TABLES:
        psse_local_pg.insert_rows(conn, table, rows[table])
```
A pandapower run needs `prefix="pp", solver="pandapower", solver_version="3.5.6"` (the `psse_run_solver_run_id_ck` tie).

**Read as the dashboard key** (lines 308-322):
```python
def _view_rows(url, role="anon"):
    import psycopg
    from psycopg import sql
    conn = psycopg.connect(url)
    try:
        conn.execute("set timezone = 'UTC'")
        conn.execute(sql.SQL("set role {}").format(sql.Identifier(role)))
        cur = conn.execute("select * from public.latest_grid_study")
        names = [d.name for d in cur.description]
        return [dict(zip(names, row)) for row in cur.fetchall()]
    finally:
        conn.rollback()
        conn.close()
```

**Whitelist test to re-run with both solvers present** (`grid_study_expose_test.py` 144-150):
```python
assert tuple(names) == contract.COLUMNS
assert not set(names) & set(contract.FORBIDDEN)
```
Also assert the selected row dicts carry none of `contract.FORBIDDEN`.

**Table refusal** (`grid_study_expose_test.py` 207-216), parametrized `anon`, `authenticated`; do it while rows of both solvers exist:
```python
for table in ("psse_run", "psse_dispatched_capacity", "psse_voltage_margin", "psse_contingency_result"):
    with _session(pg_url, role) as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute("select 1 from public.%s limit 1" % table)
```

**Time seeds** (timestamp pitfall): stale PSS/E `hour - timedelta(hours=2) + timedelta(minutes=7)`; fresh pandapower `hour + timedelta(seconds=1)` (`grid_study_expose_test.py` line 188 uses the same fresh seed). Use `local_pg.current_utc_hour()`.

**Re-apply pattern** (`test_the_migration_reapplies_cleanly`, lines 236-249): chain from the grid-study file onward in name order, twice, compares viewdef and `relacl`; picks up the new last file automatically.

---

### `backend/tests/solver_tag_owner_check_test.py` (edit)

**Analog:** itself.
- `CHECK_NAMES` (lines 44-52): drop `latest_grid_study_reads_psse_runs_only` (6 names); update the comment on line 43 and docstring lines 1-17.
- Delete `_sabotage_unguarded_view` and its `_SABOTAGE` entry (lines 272-275, 287). The "can fail" proof moves to the new `verify_exposure` check: re-apply the Phase 3 statement (`_only(_statements(_GRID_STUDY_MIGRATION), _VIEW)` style, line 274) or the Phase 3 PSS/E-only statement with both solvers present, expect the new check false.
- Rewrite `test_db_a_newer_pandapower_run_never_changes_the_view` (lines 325-349) and rename it. New assertions: PSS/E at hour-2 plus pandapower at hour-1 gives 8 rows, one `slot_time` per solver; only pandapower runs gives 4 rows with solver `pandapower`; a newer failed pandapower run changes nothing.
- `test_db_tracer_every_check_is_ok_after_the_chain` (lines 212-240) passes unchanged afterwards.
- `test_text_the_guarded_view_*` and `test_db_the_guard_keeps_columns_comments_and_privileges` stay (they test the applied Phase 3 file).

---

### `backend/tests/expose_migration_test.py` (edit)

**Analog:** itself. `_VERIFY_CHECKS` (line 310, 36 names, sorted) gains `latest_grid_study_has_each_solvers_newest_complete_run` (37); update the comment at lines 308-309. Sabotage cases follow `_DAY_AHEAD_SABOTAGE` style (rolled-back transaction as superuser, `bad = {names with ok is not True}` compared to an expected set). Test: `[r["check_name"] for r in rows] == sorted(_VERIFY_CHECKS)`.

### `backend/tests/psse_results_migration_test.py` (edit)

**Analog:** itself. Line 38 `_EXPOSURE_CHECKS = 36` to 37; `_EXPOSURE_CHECKS_WITHOUT_GRID_STUDY = 29` stays. Ordering test (lines 91-98):
```python
names = sorted(n for n in os.listdir(_MIGRATIONS_DIR) if n.endswith(".sql"))
assert name > _EXPOSE_MIGRATION
assert names[names.index(name) + 1:] == [_GRID_STUDY_EXPOSE_MIGRATION, _SOLVER_TAG_MIGRATION]
```
Append a constant for the new file name to that list and update the test name.

### `backend/tests/day_ahead_expose_test.py` (edit)

**Analog:** itself, lines 132-137:
```python
after = names[names.index(_EXPOSE_MIGRATION) + 1:]
assert after == [
    name for name in after
    if name.endswith(("_psse_results.sql", "_expose_latest_grid_study.sql", "_psse_run_solver_tag.sql"))
], after
assert len(after) <= 3
```
Add `"_latest_grid_study_per_solver.sql"` to the tuple, bound to 4, update the comment on lines 130-131.

### `backend/grid_study_contract.py` (edit)
`COLUMNS` (20), `FORBIDDEN` (10), `STALE_AFTER_MINUTES = 90` unchanged. Edit the docstring to name the replacing migration; optionally add `SOLVERS = ("psse", "pandapower")` and `MAX_ROWS = 8`. (File lines 11-38 hold the lists; not re-read here beyond RESEARCH's citation.)

### `docs/integration/rest-api.md` (edit)
Prose only: lines ~29 and ~246 and the "Grid-study results (preliminary)" bullets (Where the numbers come from, How often, Solvers, `solver` row of the columns table). Keep every `##` heading. Line ~137 stays true.

### DEF-01 hand-over file (D-04, D-07, D-08)
**Analog:** decision docs under `docs/data-science/decisions/` (for example `pandapower_live_write_decision.md`), which Phase 5 text tests read; a text test can read the tracked copy. Content from RESEARCH "Structure of the hand-over file": header to Aaron Phan, Block A (`REQUIREMENTS.md` `## Deferred` bullet, current text quoted verbatim, then the replacement), Block B (`STATE.md` new dated line, apply-date placeholder), Block C (`docs/DASHBOARD-REQUIREMENTS.md` ch. 10 lines 441 and 443), confirmation `git grep` commands (`MSYS_NO_PATHCONV=1 git show "origin/feature/dashboard:<path>"`). Do not claim pandapower rows are live. Text test: names `latest_grid_study`, every name in `contract.COLUMNS`, `solver`, `preliminary`, `90 minutes`, "stale while ... paused", and quotes the current bullet verbatim. The phase-directory file is a one-line pointer.

## Shared Patterns

### Throwaway-Postgres harness
**Source:** `backend/tests/local_pg.py` (`cluster`, `apply_migrations`, `run_select_file`, `current_utc_hour`, `migration_files`, `SUPABASE_ROLES_SQL` lines 39-55), `backend/tests/psse_local_pg.py` (`valid_run_rows`, `make_run_id`, `insert_rows`, `reset`, `RESULT_TABLES`, `CITIES`).
**Apply to:** all new DB tests.
```python
@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        local_pg.apply_migrations(url)
        yield url
```
Run: Git Bash `PATH="/c/Program Files/PostgreSQL/17/bin:$PATH" DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1`.

### Run a check file and assert all ok
**Source:** `solver_tag_owner_check_test.py` lines 203-209, 226-231.
```python
def _check_rows(conn, path=_VERIFY_SOLVER_TAG):
    return local_pg.run_select_file(conn, path)
...
failing = [(row["check_name"], row["detail"]) for row in rows if row["ok"] is not True]
assert failing == []
```
The exposure checker needs one fresh rating per city seeded (lines 220-224) or four checks report false.

### Sabotage proof (each check can fail)
**Source:** `solver_tag_owner_check_test.py` lines 291-301.
```python
with psycopg.connect(clean_pg, autocommit=True) as conn:
    with conn.transaction(force_rollback=True):
        assert _ok(conn, name) is True
        _SABOTAGE[name](conn)
        assert _ok(conn, name) is False
    assert _ok(conn, name) is True
```

### Counts-only check detail
**Apply to:** the new check. No run id, hash, prefix or version in `detail` (test lines 232-235 assert this).

### Do-not-edit list
`20261109233541_psse_results.sql`, `20261116200000_expose_latest_grid_study.sql`, `20261118200000_psse_run_solver_tag.sql` stay byte-identical. `solver_tag_migration_test.py` and `grid_study_expose_test.py` keep passing unchanged (docstring edit only).

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| (none) | | | Every file has an in-repo analog. The DEF-01 hand-over text has only a role-match (decision docs); its content comes from RESEARCH. |

## Metadata

**Analog search scope:** `supabase/migrations`, `supabase/ops`, `backend/tests`, `backend/grid_study_contract.py`, `docs/data-science/decisions`, `docs/integration`.
**Files read this pass:** 5 targeted reads plus the two phase documents; `git ls-files` confirmed the analogs are tracked.
**Open items for the planner:** state final counts 6 / 7 / 37; the tracked DEF-01 file name under `docs/data-science/decisions/`; `docs/data-science/decisions/dlr_live_runbook.md:673` "29 rows" drift is pre-existing and not this phase's (mention to the owner only). Baseline Windows failures (three CRLF byte-hash tests, `test_is_provisional_reads_the_real_labels`) are not regressions.
**Pattern extraction date:** 2026-11-26
