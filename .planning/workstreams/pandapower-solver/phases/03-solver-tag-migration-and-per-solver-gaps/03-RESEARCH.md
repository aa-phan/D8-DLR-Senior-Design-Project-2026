# Phase 3: Solver Tag, Migration and Per-Solver Gaps - Research

**Researched:** 2026-11-18
**Domain:** one additive Postgres migration (Supabase), the stdlib-only Python 3.7-safe `psse_job` package (run record, atomic writer, run loop, gap check), and the tests that pin all of them
**Confidence:** HIGH for the schema and the test-pin inventory (every file below was opened this session); MEDIUM for the Python design (a recommendation, not yet built); the database behaviour is unproven on this machine (no Postgres here)

## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** One new migration file dated after `20261116200000_expose_latest_grid_study.sql`. It adds `solver text not null default 'psse'` (check: `psse` or `pandapower`) and `solver_version text` (nullable) to `public.psse_run`, and replaces the run-id check so a `pp-` id is accepted only with `solver = 'pandapower'` and a `psse-` id only with `solver = 'psse'`. The applied v1 migration (`20261109233541_psse_results.sql`) is never edited; the run-id check is dropped and re-added by the new file. Existing runs stay valid and read as `psse`. Reversibility: one-way once applied live.
- **D-02:** Idempotent, like earlier migrations in this repo, and it adds no role or credential. The writer role `dlr_psse_writer` keeps its existing privileges; check whether its INSERT grant needs the new columns.
- **D-03:** The new migration also replaces `public.latest_grid_study` so it reads only `solver = 'psse'` runs (same 20 columns, same order, column list stays one-way). This stops a pandapower row from being shown to the dashboard as PSS/E before Phase 6 replaces the view with a per-solver one. Reversibility: costly (edits an exposed, owner-applied view). **Owner to confirm.**
- **D-04:** The run record gains a `solver` field (default `psse`, so the PSS/E job and its tests are unchanged) and `solver_version`. The all-or-nothing writer stamps both. A pandapower run can never be stored as `psse`: the writer and the database constraint both refuse a mismatch. This phase edits the files Phase 2 deliberately left alone (`contract.py`, `run_record.py`, `job.py`, `constants.py`, `gaps.py`, `writer.py` as needed); `psse_job` stays stdlib-only and Python 3.7-safe, and the import-boundary tests must keep passing.
- **D-05:** The pandapower engine's `psse_version=None` plus `solver_version` hand-off from Phase 2 research is used; the closing rehearsal writes a tagged four-city pandapower study through the real writer into a throwaway database.
- **D-06:** Gaps are computed per solver: a PSS/E run in an hour never hides a missing pandapower hour. PSS/E gaps while its machine is offline are listed separately from pandapower gaps. Pure Python, covered by tests that run without a database.
- **D-07:** No Postgres is installed on this machine, so the database proofs (success criterion 1 and the writer's refusal against the real constraint) are written to run on a throwaway local database and skip cleanly here; the SUMMARY must say plainly that they were only skipped and give the command to run them on the owner's Mac. The pure-Python parts (gap check, run-record and writer logic against a fake connection) run here. Success criterion 4 (read-only check after the owner applies the migration live) is an owner step: the phase prepares a read-only check script and does not touch the live project.

### Claude's Discretion

Migration file name and time-of-day suffix, helper names, and test layout, as long as the decisions above hold.

### Deferred Ideas (OUT OF SCOPE)

- The per-solver `latest_grid_study` replacement, exposure-check updates and the DEF-01 text stay in Phase 6.
- The retention rule for permanent rows (OPS-04) stays in Phase 5.

## Phase Requirements

<phase_requirements>

| ID | Description | Research Support |
|----|-------------|------------------|
| DB-01 | One additive migration adds a `solver` column (`psse` or `pandapower`, default `psse` so the existing 19 runs and the unchanged PSS/E job stay valid) and a `solver_version` column to `psse_run`, and allows a `pp-` run-id prefix tied to `solver = 'pandapower'` by a check constraint. | Migration skeleton, dependency inventory and idempotence rules in "Architecture Patterns" (Pattern 1); pitfalls 1 to 5; text-test plus database-test split in "Validation Architecture". |
| DB-02 | The pandapower job writes through the existing all-or-nothing writer as `dlr_psse_writer`, tagging every run with its solver; a pandapower run can never be stored as `psse`. | Pattern 2 (two column tuples, tagged INSERT, writer refusal, `run_once(solver=...)` and the study-carried tag); "Common Pitfalls" 6 and 7 (the `pandapower` word gate and the pinned 17-column tuple). |
| DB-03 | The gap check reports missing hours per solver, so a PSS/E run in an hour cannot hide a missing pandapower hour, and PSS/E gaps while its machine is offline are listed separately. | Pattern 4 (pure-Python per-solver gap computation over a one-statement read, fake-connection tests, the existing oracle reused); pitfall 8. |

</phase_requirements>

## Summary

The migration is small and safe. Nothing depends on `psse_run_run_id_ck` except the check itself: no foreign key, index, view, policy or grant references the check or the column list (the three child tables reference `psse_run (run_id, outcome)`, which is the primary key plus a unique constraint, and the view names its columns explicitly). Adding two columns is therefore invisible to the writer role's table-level `INSERT, SELECT` grant and to every policy (`with check (true)` / `using (true)`), so D-02's question is answered: **no grant change is needed, and none must be added** (a column-level grant would change `verify_psse_results.sql`'s pinned count of 8 permission-list entries). The only existing object that must be replaced is the view (D-03), and `create or replace view` keeps its owner and privileges.

The real work and the real risk are on the Python side and in the tests, not in the SQL. Four existing pins constrain the design and each one would silently force a wrong design if missed: (1) `psse_job` source may not contain the word `pandapower` anywhere, comments and docstrings included (`pandapower_import_gate_test.py`), so the solver tag must be registered by the solver package, not named in `psse_job`; (2) `PSSE_RUN_COLUMNS` is pinned to the 17 columns of the frozen reference DDL (`psse_run_record_test.py`), and a PSS/E record must keep exactly those 17 keys and execute exactly `contract.INSERT_RUN_SQL` (`psse_phase4_validation_test.py`), so the tag columns need a second tuple and a second INSERT, used only for a non-PSS/E run; (3) the gap logic today is one SQL file whose Python wrapper is pinned by database-only tests, so per-solver gaps must be added as a new pure-Python path and the existing `run` output left byte-identical; (4) three existing text/database tests assert the migration directory ends with exactly the two current files or re-apply the old view migration alone, and they break by design the moment a third file exists, so they must be edited in the same plan as the migration.

Nothing in this environment can prove database behaviour: `initdb`, `pg_ctl`, `psql`, `docker` and the Supabase CLI are all absent, so every database proof skips here. What can be proven here is the migration's text (statements, constraint names, vocabulary parity with Python), all writer and run-loop logic against a recording fake connection, and the whole gap check against a fake connection with an independent oracle. The plan should split the work exactly along that line and state plainly in the SUMMARY that the database tier was only skipped.

**Primary recommendation:** One migration named `20261118200000_psse_run_solver_tag.sql` (three `alter table` statements plus a guarded view replace), a registry-based solver tag in `psse_job.contract` that the pandapower package fills on import, a second 19-column INSERT used only for non-PSS/E runs, a pure-Python per-solver gap path added beside the untouched legacy one, and the three order-sensitive existing tests edited in the same plan.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Solver tag column and run-id/solver tie | Database / Storage | API / Backend (writer refuses first) | The constraint is the last line of defence and survives a buggy or older writer; the writer refusal gives a clear error before a transaction opens. |
| Stamping the tag on a run | API / Backend (`run_record`, `job`, `writer`) | Database (default `psse`) | The run record owns what a row says; the database default only protects a writer that does not know the column. |
| Keeping unverified pandapower figures off the dashboard | Database / Storage (view guard) | — | The dashboard reads only `latest_grid_study`; the guard in the view is the only place that cannot be bypassed by a client. |
| Per-solver gap computation | API / Backend (Python) | Database (one read-only row source) | D-06 demands database-free tests, so the logic lives in Python; SQL only supplies `(slot_time, solver, outcome)` rows. |
| Post-apply live check | Database / Storage (read-only SQL under `supabase/ops/`) | Owner (runs it) | Success criterion 4 is an owner step; the repo ships a script, never touches the live project. |

## Standard Stack

No new package, no new tool. Every item below already exists in the repo.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PostgreSQL SQL (Supabase) | live version not stated in the repo | the additive migration | Same dialect and idempotence style as the eight existing migrations. |
| psycopg | 3.3.6 installed in `.venv` [VERIFIED: `.venv/Scripts/python.exe -c "import psycopg"` printed `psycopg 3.3.6`]; laptop pins `psycopg[binary]==3.1.20` for 3.7 (documented in `psse_setup_doc_test.py:256`) | writer connection, test harness | Already the writer's driver; imported lazily in `writer.connect` only. |
| pytest | repo `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) | all proofs | Existing convention: module-level imports, plain asserts, no classes. |
| Python stdlib (`collections`, `datetime`, `re`, `json`, `os`, `sys`) | `psse_job` must stay Python 3.7 syntax | contract, run record, writer, gaps | The allow-list in `psse_contract_test.py:40-44` already contains everything the design needs. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `collections.namedtuple(..., defaults=...)` | added in Python 3.7 [CITED: docs.python.org/3.7/library/collections.html: "Changed in version 3.7: Added the defaults parameter and the _field_defaults attribute."] | give `RunContext` and `StudyResults` new trailing fields with defaults so every existing 6-field construction still works | `RunContext` (job, launcher, credcheck, tests construct it with the 6 original fields). |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Registry (`contract.register_solver_tag`) filled by the solver package | `run_once(solver=..., run_id_prefix=...)` kwargs only | Kwargs make every caller (Phase 5) remember two strings and let a forgotten argument tag a pandapower study as `psse`; the registry mirrors `study.register_solver`, which Phase 2 already uses for the same reason. |
| Second 19-column INSERT used only for non-PSS/E runs | Always write 19 columns | Always-19 breaks the pinned 17-key record test and `psse_phase4_validation_test` (which compares the executed SQL to `contract.INSERT_RUN_SQL`) and would make a PSS/E insert fail on a database that has not had the migration applied yet (the laptop job is paused but not retired). |
| New pure-Python per-solver gap path | Edit `psse_run_gaps.sql` and `fetch_gaps` | Editing makes the SQL reference `solver`, so the existing database-only gap tests, which run against the reference DDL without the migration, would fail unless their fixture changes, and the printed report format they pin would change. |
| Two constraints (`psse_run_run_id_ck` widened, plus a separate tie) | One combined constraint | One constraint satisfies D-01 literally, but two give different violation names, so a test can say whether the pattern or the tie refused an insert. Equivalent in effect. |

**Installation:** none (`# nothing to install`).

**Version verification:** psycopg and pandapower versions above were read from the project venv this session. No package is added, so no registry lookup applies.

## Package Legitimacy Audit

This phase installs no external package. Audit table: not applicable. **Packages removed due to SLOP verdict:** none. **Packages flagged SUS:** none. `[ASSUMED]` installs: none.

## Architecture Patterns

### System Architecture Diagram

```
 PSS/E job (laptop, Py 3.7)              pandapower engine (CI, Py 3.12)
 launcher/job.run_once(solver default)    engine.prepare_run -> PreparedRun
        |                                         |   (imports pandapower_job.api, which
        |                                         |    registers factory AND solver tag "pp")
        v                                         v
   job.run_once(solver="psse" | solver=<tag>) ----------------------------+
        |  new_run_id(started_at, solver)  -> "psse-..." or "pp-..."        |
        |  study(selection, context) -> StudyResults(.., solver, solver_version)
        |  validate_results ; cross-check results.solver == run solver      |
        v                                                                   |
   run_record.build_run_record                                              |
        |  psse: 17 keys (unchanged)    non-psse: 17 + solver + solver_version
        v
   writer._check_tag(record)   <- refuses before any statement (ValueError, nothing written)
        |  17 keys -> contract.INSERT_RUN_SQL ; 19 keys -> contract.INSERT_RUN_TAGGED_SQL
        v
   Postgres (public.psse_run + 3 child tables)
        |  psse_run_solver_ck, psse_run_run_id_ck (widened), psse_run_solver_run_id_ck (tie)
        |
        +--> public.latest_grid_study  (guard: r.solver = 'psse')  --> dashboard (anon key)
        |
        +--> gaps: one read-only statement (slot_time, solver, outcome) + DB clock hour
                 -> pure-Python compute per solver -> sections "psse" and "<other>"
```

### Recommended Project Structure

```
supabase/migrations/20261118200000_psse_run_solver_tag.sql   # new, additive
supabase/ops/verify_solver_tag.sql                           # new, read-only owner check (criterion 4)
backend/psse_job/contract.py        # + tag registry, TAGGED columns, tagged INSERT, 2 defaulted fields
backend/psse_job/run_record.py      # + new_run_id(solver), tag keys for non-psse, cross-checks
backend/psse_job/job.py             # + run_once(solver=...)
backend/psse_job/writer.py          # + _check_tag, SQL choice
backend/psse_job/gaps.py            # + per-solver path; legacy path byte-identical
backend/psse_job/constants.py       # + SOLVER_PSSE = "psse" (no other solver named)
backend/pandapower_job/api.py       # + one line: register the tag next to study.register_solver
backend/pandapower_job/engine.py    # _recording_study: solver, solver_version=results.psse_version, psse_version=None
backend/tests/psse_local_pg.py      # + apply_solver_schema helper (apply_schema unchanged)
backend/tests/solver_tag_migration_test.py   # new: text tests (always run) + database tests (skip here)
backend/tests/psse_solver_tag_test.py        # new: pure-Python writer / run_once / record tests
backend/tests/psse_gaps_solver_test.py       # new: pure-Python per-solver gap tests
backend/tests/pandapower_solver_tag_test.py  # new: vocabulary parity + rehearsal (importorskip pandapower)
```

### Pattern 1: The migration (what depends on what, and what it must drop and re-add)

**Dependency inventory** (everything below read from `supabase/migrations/20261109233541_psse_results.sql` and the view file this session):

| Object | Depends on `psse_run_run_id_ck` or the column list? | Evidence (verbatim) | Consequence |
|--------|-----|-----|-----|
| The check itself | is the thing replaced | line 36: `run_id text not null constraint psse_run_run_id_ck check (run_id ~ '^psse-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$'),` | drop and re-add under the same name |
| Primary key | no | line 55: `constraint psse_run_pk primary key (run_id),` | untouched |
| Unique (FK target) | no | line 61: `constraint psse_run_run_outcome_uq unique (run_id, outcome)` | untouched |
| Three child foreign keys | reference `(run_id, outcome)` only | line 90: `constraint psse_dispatched_capacity_run_fk foreign key (run_id, run_outcome) references public.psse_run (run_id, outcome),` (same shape at lines 117 and 136) | untouched; adding a check on the parent does not lock or revalidate children |
| Index | `slot_time` only | line 64: `create index if not exists psse_run_slot_time_idx on public.psse_run (slot_time desc);` | untouched (no new index needed at 24 rows a day) |
| RLS and policies | `with check (true)` / `using (true)`, no column reference | line 178: `create policy dlr_psse_writer_insert on public.psse_run for insert to dlr_psse_writer with check (true);` | unaffected by new columns |
| Grants | table level | line 175: `grant select, insert on public.psse_run, public.psse_dispatched_capacity, public.psse_voltage_margin, public.psse_contingency_result to dlr_psse_writer;` | covers the new columns; **no grant needed** |
| Public view | names columns explicitly, reads `run_id, slot_time, finished_at, outcome` | view lines 37-38: `select r.run_id, r.slot_time, r.finished_at, r.outcome` / `from public.psse_run r` | unaffected by new columns; replaced for the guard (D-03) |
| `verify_psse_results.sql` check 4 | pins entry counts | `and (select count(*) from writer_acl) = 8` | a column-level grant would break it; do not add one |

**Constraints to add** (names new, except the widened one which keeps its name so existing documentation and the reference test text stay true):

| Name | Expression |
|------|------------|
| `psse_run_solver_ck` | `solver in ('psse', 'pandapower')` |
| `psse_run_solver_version_ck` | `length(solver_version) between 1 and 100` (null passes, same style as the existing `psse_run_error_ck`) |
| `psse_run_run_id_ck` (replaced) | `run_id ~ '^(psse\|pp)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$'` |
| `psse_run_solver_run_id_ck` | `(solver = 'psse' and left(run_id, 5) = 'psse-') or (solver = 'pandapower' and left(run_id, 3) = 'pp-')` |

`solver` and `run_id` are both `not null`, so the tie expression is never null. An insert that omits `solver` (an older writer) gets `'psse'`; with a `pp-` id it fails `psse_run_solver_run_id_ck`, which is exactly the "default is also the danger" case.

**Skeleton** (statement order matters: the columns must exist before a constraint names them; separate `alter table` statements keep each step obvious and re-runnable):

```sql
-- supabase/migrations/20261118200000_psse_run_solver_tag.sql  (comment header, no credential)

alter table public.psse_run
    add column if not exists solver text not null default 'psse',
    add column if not exists solver_version text;

alter table public.psse_run
    drop constraint if exists psse_run_solver_ck,
    drop constraint if exists psse_run_solver_version_ck,
    drop constraint if exists psse_run_solver_run_id_ck,
    drop constraint if exists psse_run_run_id_ck;

alter table public.psse_run
    add constraint psse_run_solver_ck check (solver in ('psse', 'pandapower')),
    add constraint psse_run_solver_version_ck check (length(solver_version) between 1 and 100),
    add constraint psse_run_run_id_ck check (run_id ~ '^(psse|pp)-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$'),
    add constraint psse_run_solver_run_id_ck check ((solver = 'psse' and left(run_id, 5) = 'psse-') or (solver = 'pandapower' and left(run_id, 3) = 'pp-'));

-- D-03: the view body is the existing one with one added predicate in newest_run.
create or replace view public.latest_grid_study with (security_invoker = false) as
with newest_run as (
    select r.run_id, r.slot_time, r.finished_at, r.outcome
      from public.psse_run r
     where r.outcome in ('ok', 'fallback')
       and r.solver = 'psse'
     order by r.slot_time desc, r.finished_at desc, r.run_id desc
     limit 1
)
select 'psse'::text as solver, d.city, ... /* the other 19 expressions copied verbatim, same order */
from newest_run n
join public.psse_dispatched_capacity d on d.run_id = n.run_id and d.run_outcome = n.outcome
order by d.city;

revoke all on public.latest_grid_study from public, anon, authenticated;
grant select on public.latest_grid_study to anon, authenticated;
-- plus comment on column public.psse_run.solver / solver_version (unit-first style), and the
-- changed comment on view public.latest_grid_study.
```

Rules the PostgreSQL documentation gives that this relies on:
- A constant default on `ADD COLUMN` is stored in metadata and no rewrite happens [CITED: postgresql.org/docs/current/sql-altertable.html: "In neither case is a rewrite of the table required."]. So the existing rows read `psse` with no `UPDATE` (the writer role has none, and the owner needs none).
- Adding a check constraint scans the table and takes an `ACCESS EXCLUSIVE` lock [CITED: same page: "Normally, this form will cause a scan of the table to verify that all existing rows in the table satisfy the new constraint"; "Although most forms of ADD table_constraint require an ACCESS EXCLUSIVE lock"]. At about 19 rows and a paused laptop writer, that is instantaneous; `NOT VALID` is not needed.
- `create or replace view` needs the same column names, order and types, and keeps ownership and privileges [CITED: postgresql.org/docs/current/sql-createview.html: "the same column names in the same order and with the same data types"; "Other view properties, including ownership, permissions, and non-SELECT rules, remain unchanged."]. The view keeps `'psse'::text as solver`, so the type is unchanged.

**Idempotence:** run twice, the first statement adds nothing (a notice), the drop-then-add re-creates the same four constraints and re-validates. The view replace, `revoke` then `grant` are the same pattern as `20261116200000`. Statement order inside one file also gives atomicity under the local harness (`conn.execute(whole file)` inside `with psycopg.connect(...)` commits once).

**Timestamp and name:** `20261118200000_psse_run_solver_tag.sql` sorts after `20261116200000_expose_latest_grid_study.sql`, and no other branch (`main`, `origin/feature/pandapower-solver`, `origin/main`, `feature/pss-e-integration`) carries a later migration [VERIFIED: `git ls-tree` of every local and remote branch this session; the newest on main is `20261116200000_expose_latest_grid_study.sql`]. The name must not end in `_psse_results.sql`, `_expose_latest_rating.sql`, `_soak_freshness_log.sql` or `_expose_day_ahead_forecast.sql`: existing tests glob those suffixes and assert exactly one match (`psse_results_migration_test.py:64-70`, `day_ahead_expose_test.py:135`).

### Pattern 2: Contract, run record, writer and run loop (design that satisfies every pin)

**The pins this design must respect** (all read this session):

- `backend/tests/psse_run_record_test.py:82-83`: `columns = list(contract.PSSE_RUN_COLUMNS)` then `assert len(columns) == 17`; a default `build_run_record` must return exactly those 17 keys (`assert list(ok) == columns`).
- `backend/tests/psse_run_record_test.py:503`: `assert list(columns) + list(contract.DB_DEFAULT_COLUMNS) == ddl, table` for every entry of `contract.TABLE_COLUMNS`, where `ddl` is parsed from `docs/data-science/schema/psse_results_v1.sql` (frozen: its marked region is sha-pinned). **Do not change `PSSE_RUN_COLUMNS` or `TABLE_COLUMNS[PSSE_RUN_TABLE]`.**
- `backend/tests/psse_phase4_validation_test.py:109`: `run_inserts = [call for call in conn.calls if call[0] == contract.INSERT_RUN_SQL]` with `assert len(run_inserts) == 1`: a PSS/E run must execute exactly `contract.INSERT_RUN_SQL`.
- `backend/tests/psse_run_record_test.py:522`: `assert contract.INSERT_RUN_SQL.endswith("on conflict (run_id) do nothing returning run_id")`.
- `backend/tests/pandapower_import_gate_test.py:44-46`: `count = lowered.count(_SOLVER_WORD)` over every `psse_job/*.py` with `_SOLVER_WORD = "pandapower"`: the word may not appear at all, in any letter case, in code, comment or docstring. **Write "the second solver" in comments.**
- `backend/tests/psse_contract_test.py:196`: every `psse_job` module must parse with `feature_version=(3, 7)`; no `X | Y` annotations, no builtin generics, no walrus; import allow-list at lines 40-44.
- `backend/tests/psse_laptop_modes_test.py:586`: `env, since, until, fail_on_gaps, stream = args` (the launcher calls `gaps.run` with exactly five positional arguments).

**Design:**

1. `contract.py`:
   - `SOLVER_RUN_COLUMNS = ("solver", "solver_version")`, `TAGGED_RUN_COLUMNS = PSSE_RUN_COLUMNS + SOLVER_RUN_COLUMNS`.
   - `insert_sql(table, suffix="", columns=None)` (an optional argument; default behaviour identical) and `INSERT_RUN_TAGGED_SQL = insert_sql(PSSE_RUN_TABLE, "on conflict (run_id) do nothing returning run_id", TAGGED_RUN_COLUMNS)`. `INSERT_RUN_SQL` stays byte-identical.
   - `SOLVER_PSSE = "psse"`, `RUN_ID_PREFIXES = {"psse": "psse"}` and `register_solver_tag(name, prefix)`: refuse an empty value, refuse re-registering a name with a different prefix, refuse a prefix that equals or begins another's prefix plus `-`, no-op for an identical call. Same shape as `study.register_solver` (read at `study.py:335-348`).
   - `RunContext` gains `solver` (default `"psse"`); `StudyResults` gains `solver` (default `"psse"`) and `solver_version` (default `None`). Use `collections.namedtuple(..., defaults=(...))` (3.7+, cited above). Existing 6-field constructions (`job.py:91`, `launcher.py:613`, `credcheck.py:433/438`, `study.py:653` and the tests) keep working because the new fields are trailing and defaulted.
2. `run_record.py`:
   - `new_run_id(started_at, solver="psse")` uses `contract.RUN_ID_PREFIXES[solver]` (unknown solver: `ValueError`). The existing call `new_run_id(NOW)` is unchanged.
   - `build_run_record`: for `context.solver == "psse"` return today's 17 keys; for any other solver return the 17 keys plus `solver` and `solver_version` (`results.solver_version` or `None`, a label cut to 100 characters). `as_failed` copies the dict so it keeps the tag. `result_rows` is unaffected (it reads only `run_id` and `outcome`).
   - Refuse a run whose study results self-identify as a different solver than the run (`results.solver != context.solver`): raise `ResultsInvalid`/`ValueError` so `run_once` records a `validate_results` failure instead of writing rows. This is what stops a pandapower study run with the default `solver="psse"` from being stored as a PSS/E result, which neither the writer nor the database can detect (everything would be consistently `psse`).
3. `job.py`: `run_once(..., solver="psse")` (new trailing keyword), `run_id = run_record.new_run_id(started_at, solver)`, context carries it. Nothing else changes, so every existing call and test is unaffected.
4. `writer.py`: a private `_check_tag(record)` called first in `write_run`, `record_failure` and `_insert_run`, before any statement or transaction:
   - tag = `record.get("solver", "psse")`; refuse (`ValueError`, fixed text, no value) if the tag is not in `contract.RUN_ID_PREFIXES`, if `run_id` does not start with that tag's prefix followed by `-`, if a record has one tag key but not the other, or if a `psse` record carries a `solver_version`.
   - A record with 17 keys uses `INSERT_RUN_SQL`; one with 19 uses `INSERT_RUN_TAGGED_SQL`. A `pp-` id with no tag keys is refused here (it would otherwise be stored as `psse` by the database default and then refused by the constraint, a worse failure).
   - Existing behaviour is unchanged: the failure record path still goes through `record_failure`, so a refused or failed pandapower write is stored with its tag.
5. `pandapower_job/api.py`: next to `study.register_solver(SOLVER_NAME, factory)` add `contract.register_solver_tag(SOLVER_NAME, "pp")`. `pandapower_job/engine.py` `_recording_study`: return `results._replace(dispatch=dispatch, psse_version=None, solver=SOLVER, solver_version=results.psse_version)` (today it returns `results._replace(dispatch=dispatch, psse_version=None)`, read at `engine.py:134`). Phase 5's runner passes `solver=engine.SOLVER` to `run_once`.

**Why a registry and not the literal in `psse_job`:** the gate forbids the word, and the Phase 2 research already settled the same problem for the adapter by having the solver package register itself on import (`API_FACTORIES = {"psse": _psse_factory}`, `study.py:332`). A fourth check keeps it honest: importing `psse_job` alone registers only `psse` (extend the existing `test_importing_study_registers_only_psse` style).

### Pattern 3: The view guard and its twins

- `backend/grid_study_contract.py` (the Python twin) lists the 20 published columns. The guard changes no column, so the twin, `grid_study_expose_test.test_the_view_columns_equal_the_contract` and the exposure checks `latest_grid_study_matches_the_contract`, `latest_grid_study_columns_all_commented`, `latest_grid_study_one_row_per_city_per_solver` and `latest_grid_study_is_stale_matches_age_minutes` (all in `supabase/ops/verify_exposure.sql`) are unaffected. Grants are preserved by `create or replace`, and the new migration repeats `revoke` then `grant`, so the `anon_authenticated_grants_are_select_on_published_objects_only` count of 12 holds.
- `verify_exposure.sql` and its test need no edit in this phase (Phase 6 owns them). The **must-keep-passing** list is: `grid_study_expose_test.py`, `psse_results_migration_test.py` (after the ordering edit below), `expose_migration_test.py` (its `test_expose_migration_reapplies_cleanly` re-applies the chain from the latest-rating migration onward, which will now end with the new file; that is idempotence-safe because every statement in the new file is re-runnable and the chain re-applies the old unguarded view first and the guarded one last).
- The view's `solver` comment says "pandapower rows arrive in a later release"; with the guard it stays true. Re-issue `comment on view` to say the view shows PSS/E runs only until the per-solver view replaces it. Whether comments on view columns survive `create or replace view` is not stated on the CREATE VIEW page `[ASSUMED]`; they are attached to the view's object id, which that statement keeps, and the existing `latest_grid_study_columns_all_commented` check over the full chain will prove it on the Mac.

### Pattern 4: Per-solver gap check, pure Python

**What exists** (read this session): `psse_job/gaps.py` runs `docs/data-science/schema/psse_run_gaps.sql` (one `with ... select`, no solver anywhere) plus `SUMMARY_SQL = "select count(*), min(slot_time), max(slot_time) from public.psse_run"`, exposes `GapRow = collections.namedtuple("GapRow", ["slot_time", "gap_kind", "runs", "failed_runs"])` and `run(env, since, until, fail_on_gaps, out, connect)`. Every test of it is database-only (`psse_gaps_pg_test.py`), and pins: the report line shapes (`psse_gaps_pg_test.py:485-491`, each output line must match one of five patterns), two statements per run (`:380`), one SELECT statement in the SQL file with no forbidden word (`:314-330`), and `assert "generate_series" not in source` for `gaps.py` (`:329`). The launcher passes five positional arguments (`psse_laptop_modes_test.py:586`).

**Consequence:** the legacy path (`run`, `fetch_gaps`, `format_report`, the SQL file) must stay byte-identical, or the whole database gap suite and the laptop doc tests change. It is also **pooled across solvers**: once pandapower rows exist, a pandapower row fills a PSS/E hour and the reverse. That is the exact hiding problem DB-03 names, so the new per-solver path is the one Phase 5 uses; the legacy command stays as the PSS/E laptop's, and the plan should add one honest sentence about that wherever the gap check is described (not by editing `psse_laptop_setup.md`, whose SQL blocks and headings are pinned by `psse_setup_doc_test.py`).

**Design:**

```python
# backend/psse_job/gaps.py  (additions only; no second solver named)
RUNS_SQL = "select slot_time, solver, outcome from public.psse_run"
CURRENT_HOUR_SQL = "select (date_trunc('hour', now() at time zone 'UTC') at time zone 'UTC')"

def compute_gaps(runs, current_slot):
    """runs: iterable of (slot_time, solver, outcome); current_slot: aware UTC hour (excluded).
    Returns {solver: [GapRow, ...]}, oldest first, one list per solver present in runs.
    Rules per solver (the legacy five, applied to that solver's own rows):
      1. several rows in an hour are not a gap; only an hour with no ok/fallback row is listed
      2. an hour whose rows are all failed is failed_only, never hidden
      3. the current hour is excluded
      4. hours before THAT SOLVER's first recorded slot are not its gaps
      5. a solver with no rows has no list (reported as 'no runs recorded' for it)
    """
```
Rule 4 per solver is the essential choice: with a global first slot, every PSS/E-only hour before the first pandapower run would be flagged as a pandapower gap forever. With the per-solver first slot, "a PSS/E run in an hour and no pandapower run in that hour" is reported as a pandapower gap only after pandapower has started, which is what success criterion 3 means.

- **DB-free proof:** `run_by_solver(env, since, until, fail_on_gaps, out, connect, ...)` reuses `writer.connect`, the read-only handling (`conn.autocommit = False; conn.read_only = True`), `_in_window`, `_iso` and the redacted one-line failure of the legacy `run`; its connection seam accepts a fake with `execute(sql)` returning an object with `fetchall()`/`fetchone()`, plus settable `autocommit` and `read_only` attributes and `close()`. The current hour comes from `CURRENT_HOUR_SQL` on the same read-only connection (so the CI runner's clock and the database's clock can never disagree), and a fake returns a fixed hour.
- **Oracle:** `reference_gaps` at `psse_gaps_pg_test.py:155-176` is already an independent plain-loop oracle over `(slot, outcome)`; copy it per solver into the new pure test and drive `compute_gaps` with the same seeded random histories (`random.Random(20261103)` style), now with a solver per row.
- **Output** holds only times, the solver tag, kinds and counts (no run id, no case label), with a pinned-line-shape test like `test_gap_safe_report_holds_only_times_kinds_and_counts`. The PSS/E section is printed separately from the other solver's; the solver tags in the output come from the data, so `gaps.py` never has to name the second solver.
- **Exit code** (recommendation, owner may change): reuse `EXIT_OK/EXIT_GAPS/EXIT_CHECK_FAILED`; with `fail_on_gaps`, exit 5 when any solver other than PSS/E has a gap in the window, or when the table is empty; PSS/E gaps are listed but do not fail the check by default, because "PSS/E machine offline" is the known state. Make the set of failing solvers an argument.

### Pattern 5: The owner's read-only live check (success criterion 4)

Write `supabase/ops/verify_solver_tag.sql` in the style of `verify_psse_results.sql` (one `with ... select check_name, ok, detail`, no write keyword, check names pinned in a test, a negative per check on the local database). Checks: the two columns exist with the right type, null and default; every `psse-` run reads `psse` (`not exists (select 1 from public.psse_run where left(run_id, 5) = 'psse-' and solver <> 'psse')`); the four constraint names exist; the view definition contains the guard (`pg_get_viewdef('public.latest_grid_study'::regclass)` contains `solver = 'psse'`); the count of `psse_run` rows equals the count of `psse`-tagged rows until the first pandapower run. The script's header says: also run `verify_psse_results.sql` and `verify_exposure.sql`, all `ok`, to show "nothing else changed". The phase does not run it against the live project.

### Anti-Patterns to Avoid

- **Editing the applied migration or the frozen reference DDL.** `psse_results.sql` is hash-pinned, and the reference DDL's marked region is pinned in `psse_schema_doc_test.py:160-170` and the hand-off note. New columns live only in the new migration.
- **Adding the tag keys to `PSSE_RUN_COLUMNS`.** It breaks the DDL-contract test and every 17-key assertion, and makes a PSS/E insert depend on the migration having been applied.
- **Naming the second solver in `psse_job` text.** Fails `test_psse_job_source_never_names_the_other_solver`.
- **A column-level grant on the new columns.** Changes the entry count `verify_psse_results.sql` pins.
- **A unique `(solver, slot_time)` index.** Two runs in one hour are legitimate (a retry, a manual re-run) and the primary key is `run_id` with `on conflict (run_id) do nothing`.
- **Hashing the working-tree bytes of the new file in an "unchanged after apply" test.** See pitfall 9.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Refusing a mismatched tag at the database | a trigger or function | `check` constraints in the migration | A trigger adds a function (a new executable object for the exposure checks to account for); a check is what the repo already uses for every other rule. |
| Solver-to-prefix mapping | a hard-coded `if solver == ...` in `psse_job` | `contract.register_solver_tag`, filled by the solver package | The text gate forbids the name; the registry matches `study.register_solver`. |
| Gap oracle | a new reference algorithm | the existing `reference_gaps` in `psse_gaps_pg_test.py:155-176`, run per solver | Already the independent oracle for the legacy check. |
| Throwaway database harness | a new cluster launcher | `psse_local_pg.cluster` + `apply_schema`, plus one additive helper | Skip rules (`PSSE_REQUIRE_PG`) and Windows quirks are already handled. |
| Fake connection | a new mock library | the recording connection in `psse_phase4_validation_test.py:46-63` (`calls`, `transaction()` as `contextlib.nullcontext()`, `execute`, `fetchone`, `close`) | Already proves "no row written" paths without a database. |
| Run-id format | a second generator | extend `new_run_id` with a prefix argument | One format, one regex, one place. |

**Key insight:** the writer, validator, run loop and gap oracle already exist and are solver-neutral; every piece of this phase is a defaulted addition to one of them, and the cost of getting it wrong is almost entirely in the tests that pin the old shapes.

## Common Pitfalls

### Pitfall 1: Three existing tests fail by design as soon as a third migration exists
**What goes wrong:** `psse_results_migration_test.py:96` asserts `names[names.index(name) + 1:] == [_GRID_STUDY_EXPOSE_MIGRATION]`; `day_ahead_expose_test.py:133-134` asserts the files after the day-ahead migration all end with `_psse_results.sql` or `_expose_latest_grid_study.sql` and `len(after) <= 2`; `grid_study_expose_test.py:236-251` re-applies only the old grid-study file twice and asserts the view definition is unchanged, which would now replace the guarded view with the unguarded one.
**Why it happens:** each test froze the directory at the moment it was written.
**How to avoid:** edit all three in the same plan as the migration: the first to `== [_GRID_STUDY_EXPOSE_MIGRATION, _SOLVER_MIGRATION]`, the second to allow the new suffix and `<= 3`, the third to re-apply the whole chain from the old grid-study file onward (as `expose_migration_test.py:629-649` already does) and compare snapshots.
**Warning signs:** a failure in any of those three files on the first full run.

### Pitfall 2: The migration must not be named or written so a glob or a text parser mis-reads it
**What goes wrong:** a name ending in `_psse_results.sql` makes `_psse_path()` assert `len(paths) == 1` fail; `dlr_live_runbook_test.py:288` fails on any revoke from `dlr_writer`.
**How to avoid:** use `..._psse_run_solver_tag.sql`; the migration touches only `dlr_psse_writer`-neutral objects and revokes only from `public, anon, authenticated` (as the existing view file does). `dlr_psse_writer` never matches `\bdlr_writer\b`.

### Pitfall 3: Ordering on the live project
**What goes wrong:** Supabase refuses or reorders a migration dated before the newest remote one `[ASSUMED]`.
**How to avoid:** the timestamp `20261118200000` is later than every migration on every branch, and the owner applies it last with `supabase db push --db-url ...`, as for earlier files. Do not re-date it earlier than `20261116200000` for any reason.

### Pitfall 4: The default is also the danger
**What goes wrong:** an older or buggy writer omits `solver`, the default stores `psse`, and a pandapower run masquerades as the reference.
**How to avoid:** the `pp-` id plus the tie constraint make that insert fail loudly at the database; the writer refuses a `pp-` id without tag keys before any statement; `run_once` fails a run whose study results name a different solver than the run (Pattern 2). Three layers, each testable.

### Pitfall 5: Making the check replacement safe on a populated table
**What goes wrong:** re-adding a check on a table with rows can fail if any row violates it, or lock the table.
**How to avoid:** add the columns first (so every existing row is `psse` by default), then drop and re-add the constraints; every existing row has a `psse-` id (the old check guaranteed it), so validation passes. At 19 rows the `ACCESS EXCLUSIVE` lock is momentary and the writer is paused. Do not use `NOT VALID`; it would leave an unvalidated constraint behind. The live count of 19 is owner-reported (`STATE.md`), not observed here `[ASSUMED]`; the migration does not depend on it.

### Pitfall 6: Python 3.7 and the import boundary
**What goes wrong:** `str | None` annotations, `defaults=` misuse, walrus, `removeprefix`, a new import outside the allow-list, or the word `pandapower` in a docstring fail `psse_contract_test.py` or `pandapower_import_gate_test.py`.
**How to avoid:** only constructs already in the file are used; the new code needs `collections`, `re`, `datetime` (all allowed). Run both gate files after each edit; they glob `psse_job/*.py` so new code is covered automatically.

### Pitfall 7: Hidden second source of truth for the column list
**What goes wrong:** `psse_local_pg.apply_schema` applies only the two Phase 4 migrations and the reference DDL (`psse_local_pg.py:38-46` says a glob is avoided on purpose), so every existing writer and job test runs against a table without `solver`; a writer that always sends 19 columns would fail all of them.
**How to avoid:** PSS/E stays on the 17-column path; add `apply_solver_schema(admin_url)` (= `apply_schema` then the new migration by explicit path) and use it only in the new database tests. Leave `apply_schema` unchanged. A harness change here is the right place; note that applying the new migration after the reference DDL creates `latest_grid_study` fresh (the grid-study migration is not part of that harness), which is fine.

### Pitfall 8: Per-solver "first slot"
**What goes wrong:** using one first slot for all solvers flags every PSS/E-only historical hour as a pandapower gap forever; using none lets a missing pandapower hour hide behind a PSS/E row.
**How to avoid:** per-solver first slot (Pattern 4), plus a test that has PSS/E rows before the first pandapower row and expects no pandapower gap before that row.

### Pitfall 9: Windows line endings break byte-hash pins (observed)
**What goes wrong:** this checkout has `core.autocrlf=true`; the working copy of `20261109233541_psse_results.sql` hashes to `e2bf9319...` while the pinned value and the committed blob hash to `08e7e103...` [VERIFIED: `sha256sum` of the working file versus `git show HEAD:... | sha256sum`]. Baseline run this session: `psse_results_migration_test.py::test_psse_migration_is_unchanged_after_apply` and `day_ahead_expose_test.py::test_expose_migration_is_unchanged_after_apply` already fail here for that reason, and `day_ahead_migration_test.py` fails to collect (no `matplotlib`).
**How to avoid:** do not add a byte-hash "unchanged after apply" pin for the new file in this phase (it is not yet applied); if one is wanted later, hash after normalising CRLF to LF. Report the two baseline failures in the SUMMARY as pre-existing and environmental, not as regressions.

### Pitfall 10: `solver_version` for a failed run
**What goes wrong:** a pandapower run that fails before the study returns has no results, so no version.
**How to avoid:** the column is nullable; store `None` and say so in the column comment ("NULL when the study was not reached", the same sentence `psse_version` uses). The tag itself is known from the start and is always stamped.

## Code Examples

### Writer refusal, no database (pure Python)
```python
# Source: design for this phase; modelled on writer.write_run's existing ValueError for outcome
def _check_tag(record):
    tagged = "solver" in record
    if tagged != ("solver_version" in record):
        raise ValueError("a run record carries both solver keys or neither")
    solver = record["solver"] if tagged else contract.SOLVER_PSSE
    prefix = contract.RUN_ID_PREFIXES.get(solver)
    if prefix is None:
        raise ValueError("the solver of this run is not registered")
    if not str(record.get("run_id", "")).startswith(prefix + "-"):
        raise ValueError("the run id does not belong to the solver of this run")
    if solver == contract.SOLVER_PSSE and record.get("solver_version") is not None:
        raise ValueError("a PSS/E run has no solver_version")
```

### Run-loop test with the recording connection (pure Python)
```python
# Source: backend/tests/psse_phase4_validation_test.py:46-63 (the recording connection, reused)
conn = _RecordingConnection()
outcome = job.run_once(fetch=..., study=prepared_study, connect=lambda: conn,
                       case_id="CASE", clock=..., env={"PSSE_JOB_VERSION": "t"}, solver=TAG)
run_inserts = [c for c in conn.calls if c[0] == contract.INSERT_RUN_TAGGED_SQL]
assert len(run_inserts) == 1
assert run_inserts[0][1]["solver"] == TAG and run_inserts[0][1]["run_id"].startswith("pp-")
# and for the default: the unchanged statement
assert [c for c in conn.calls if c[0] == contract.INSERT_RUN_SQL]  # psse run
```

### Database refusal as the writer role (skips here)
```python
# Source: pattern of backend/tests/psse_schema_pg_test.py:275 (_rejected(..., "CheckViolation", name))
row = dict(pg_helper.valid_run_rows(run_id_pp, STARTED)["psse_run"][0], solver="psse")  # pp- id, psse tag
_rejected(admin_or_writer_url, "psse_run", row, "CheckViolation", "psse_run_solver_run_id_ck")
row = dict(valid_row, run_id=psse_id, solver="pandapower")
_rejected(..., "CheckViolation", "psse_run_solver_run_id_ck")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| One gap result for all rows | per-solver gap lists from `(slot_time, solver, outcome)` | this phase | A row from one solver can no longer fill another solver's hour. |
| Run id prefix `psse-` only | `psse-` or `pp-`, tied to `solver` by a check | this phase | The prefix names the program; the database refuses a mismatch. |

**Deprecated/outdated:** the milestone research sketch (`research/ARCHITECTURE.md` lines 201-218) uses `check ((solver = 'psse') = (left(run_id, 5) = 'psse-'))` and an index on `(solver, slot_time desc)`; this research keeps the same effect with a more literal constraint and leaves the index out (24 rows a day; the existing `slot_time` index suffices; Phase 6 can add it if its view needs it).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | View column comments survive `create or replace view` (the PostgreSQL page does not state it) | Pattern 3 | A comment would be lost; the existing exposure check `latest_grid_study_columns_all_commented` would fail on the Mac. Mitigation: re-issue the comments in the new file at no cost. |
| A2 | `supabase db push` refuses or reorders a migration older than the newest remote one | Pitfall 3 | None for this plan: the chosen timestamp is later than everything. |
| A3 | The live project's Postgres major version stores a constant default in metadata (the docs state the behaviour; the live major version is not in the repo) | Pattern 1 | At 19 rows a rewrite would also be instantaneous; no failure either way. |
| A4 | The live table holds 19 runs, all `psse-` ids (owner-reported in `STATE.md`) | Pitfall 5 | Constraint validation could fail if some row had an unexpected id; impossible under the old check. |
| A5 | Two constraints, not one, is acceptable (D-01 describes the effect, not the shape) | Pattern 1 | Cosmetic; the owner can ask for one combined constraint. |
| A6 | The legacy launcher `gaps` command may stay pooled across solvers, with the per-solver path used by Phase 5 and the owner | Pattern 4, Open Questions | If the owner wants the laptop command per-solver, `launcher.py`, `psse_setup_doc_test.py` and the guide change too. |
| A7 | `solver_version` stores the bare version string the adapter reports (for example `3.5.6`), not `pandapower 3.5.6`, because `solver` already names the program | Pattern 2 | Cosmetic. |
| A8 | Skipping the optional `(solver, slot_time desc)` index is acceptable | State of the Art | None at current volume. |

## Open Questions

1. **Should the laptop `gaps` command become per-solver?**
   - What we know: `launcher.py` dispatches to `gaps.run` with five positional arguments, the doc test pins the command blocks, and the legacy output is pooled once two solvers write.
   - What is unclear: whether the owner wants the laptop command changed now or only the Phase 5 path.
   - Recommendation: keep legacy untouched in this phase (smallest blast radius), add the per-solver path, and add the one-sentence caveat where the plan describes the check. Ask at the checkpoint with D-03.
2. **D-03 owner confirmation.** The guard edits a live, public view. Nothing technical blocks it; the plan should keep the existing "Owner to confirm" gate and make the migration's header say the view guard is the one part that touches the dashboard-facing surface.
3. **Should the migration also constrain `psse_version` to NULL for pandapower rows?** Not requested; Python already stores `None`. Recommendation: no extra constraint (it would be a further one-way schema rule the owner did not ask for).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (`.venv`) | all tests | yes | 3.12.10 | none needed |
| psycopg | database tests, `writer.connect` | yes (module only) | 3.3.6 | none needed |
| pandapower | rehearsal, vocabulary parity | yes | 3.5.6 | tests use `pytest.importorskip` |
| `initdb`, `pg_ctl`, `psql`, `postgres` | every database proof | **no** | none | database tests skip with the harness reason; run on the owner's Mac |
| Docker | alternative database | no | none | same |
| Supabase CLI | live apply | no | none | owner step, not this phase |
| `matplotlib`, `requests` | some unrelated tests collect them | no | none | those modules fail to collect here (pre-existing) |

**Missing dependencies with no fallback:** none that block the pure-Python tier.
**Missing dependencies with fallback:** Postgres (database tier skips here; owner runs it).

## Validation Architecture

Nyquist validation is enabled: `.planning/config.json` has no `nyquist_validation` key (absent means enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (repo `pytest.ini`) |
| Config file | `pytest.ini` at the repo root |
| Quick run command | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_solver_tag_test.py backend/tests/psse_gaps_solver_test.py backend/tests/solver_tag_migration_test.py backend/tests/psse_run_record_test.py backend/tests/psse_contract_test.py backend/tests/pandapower_import_gate_test.py backend/tests/psse_phase4_validation_test.py` |
| Full suite command | the quick command plus `backend/tests/psse_laptop_modes_test.py backend/tests/psse_setup_doc_test.py backend/tests/psse_schema_doc_test.py backend/tests/grid_study_expose_test.py backend/tests/psse_results_migration_test.py backend/tests/psse_gaps_pg_test.py backend/tests/pandapower_study_job_test.py backend/tests/pandapower_solver_tag_test.py` |
| Database tier (owner's Mac / CI) | `DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs` over the database-bearing files above; must report 0 skipped. Note `local_pg.require_local_pg` (used by `grid_study_expose_test.py`, `psse_results_migration_test.py`, `expose_migration_test.py`) ignores `PSSE_REQUIRE_PG`, so read the skipped count, do not rely on the exit code. |

**Baseline measured this session** (14 relevant files, `--continue-on-collection-errors`): `2 failed, 136 passed, 95 skipped, 1 error`. The 2 failures and the 1 collection error are pre-existing and environmental (CRLF byte-hash pins on `psse_results.sql` and the day-ahead expose file; `matplotlib` missing for `day_ahead_migration_test.py`). Every one of the 95 skips is a database test.

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DB-01 | Migration text: adds exactly `solver text not null default 'psse'` and `solver_version text`; four constraints with the pinned names and expressions; vocabulary in the constraint equals `contract.RUN_ID_PREFIXES` after the solver package registers itself; run-id regexes accept and reject a matrix of ids as the SQL says (Python `re` mirror, text-level only); no `grant`, no `create role`, no `dlr_` credential text; header is comments; sorts after `20261116200000`; touches `psse_run` and the view only | unit (text) | `pytest backend/tests/solver_tag_migration_test.py -k text` | no, Wave 0 |
| DB-01 | On a throwaway database with every migration applied: existing rows read `psse`; default applies; `pp-` id with `solver='psse'` and `psse-` id with `solver='pandapower'` refused with `CheckViolation` naming `psse_run_solver_run_id_ck`; bad pattern refused by `psse_run_run_id_ck`; unknown tag refused by `psse_run_solver_ck`; migration re-applies twice leaving constraints, view definition and ACL unchanged; `verify_psse_results.sql` still all ok (writer ACL count 8); `verify_exposure.sql` still all ok | database | `DLR_TEST_PG_AUTOSTART=1 ... pytest backend/tests/solver_tag_migration_test.py backend/tests/psse_results_migration_test.py backend/tests/grid_study_expose_test.py` | no, Wave 0 (skips here) |
| DB-01 (guard) | Text: the guarded view body equals the old body plus `and r.solver = 'psse'`, same 20 select expressions in order, no forbidden field selected. Database: a newer `pandapower` run never changes `latest_grid_study`; with only `pandapower` rows the view is empty | text + database | as above | no, Wave 0 |
| DB-02 | Writer refuses before any statement: unknown solver, prefix mismatch (`pp-` id with no tag keys, `psse-` id with another tag, one tag key only, a `psse` record with a version); `_ForbiddenConnection` proves nothing executed | unit | `pytest backend/tests/psse_solver_tag_test.py -k writer` | no, Wave 0 |
| DB-02 | `run_once(solver=TAG)` with the recording connection: one tagged insert, `pp-` id, `solver` and `solver_version` params, result rows follow, failed and refused runs are stored tagged; default run executes exactly `contract.INSERT_RUN_SQL` with 17 keys; a study whose results name another solver becomes a `validate_results` failure; `psse_version` is `None` | unit | `pytest backend/tests/psse_solver_tag_test.py` | no, Wave 0 |
| DB-02 | PSS/E regression: the 17-key record, `new_run_id`, DDL contract, SQL-never-updates, Python 3.7 parse, import allow-list, no `pandapower` word, importing `psse_job` registers only `psse` | unit | quick command, existing files unchanged | yes |
| DB-02 (rehearsal) | A tagged four-city pandapower study through the real `engine.prepare_run`, `job.run_once(solver=engine.SOLVER)` and the real writer on a throwaway database; stored `solver` is `pandapower`, `solver_version` equals the adapter's pandapower version, `psse_version` null, run id starts `pp-`; no-database variant with the recording connection runs here | database + unit | `pytest backend/tests/pandapower_solver_tag_test.py` | no, Wave 0 (database part skips here) |
| DB-03 | `compute_gaps` against the plain-loop oracle over seeded random per-solver histories, with PSS/E rows before the first pandapower row, a PSS/E-only hour missing for pandapower, a pandapower-only hour missing for PSS/E, failed-only hours, empty table, only-current-hour, window filter; report lines hold only times, solver tag, kinds and counts; exit codes; one redacted line on failure; read-only handling on the fake | unit | `pytest backend/tests/psse_gaps_solver_test.py` | no, Wave 0 |
| DB-03 | Legacy `run` output and SQL file unchanged | database (existing) | `psse_gaps_pg_test.py` | yes (skips here) |
| Criterion 4 | `supabase/ops/verify_solver_tag.sql`: single read-only select, pinned check names in order, a negative per check on the local database; text part runs here | unit (text) + database | `pytest backend/tests/solver_tag_migration_test.py -k verify` | no, Wave 0 |

### Sampling Rate
- **Per task commit:** the quick command above (about 5 to 15 seconds without Postgres; the gate files glob `psse_job`, so they re-check every edit).
- **Per wave merge:** the full suite command here, then the database tier on the Mac.
- **Phase gate:** pure tier green here; database tier green on the Mac with 0 skipped, or the SUMMARY states plainly that it was only skipped and quotes the command. Do not mark DB-01's database half, DB-02's constraint half or the guard as proven from a skip.

### Wave 0 Gaps
- [ ] `backend/tests/solver_tag_migration_test.py` - DB-01 text tier (always runs) and database tier (skips here)
- [ ] `backend/tests/psse_solver_tag_test.py` - DB-02 writer, record and run-loop logic with a recording connection
- [ ] `backend/tests/psse_gaps_solver_test.py` - DB-03 with a fake connection and the oracle
- [ ] `backend/tests/pandapower_solver_tag_test.py` - vocabulary parity and the rehearsal (importorskip pandapower)
- [ ] `backend/tests/psse_local_pg.py` - add `apply_solver_schema` (leave `apply_schema` untouched)
- [ ] Edit `psse_results_migration_test.py:96`, `day_ahead_expose_test.py:127-135` and `grid_study_expose_test.py:236-251` (Pitfall 1), in the same plan as the migration
- [ ] Extend `pandapower_study_job_test.py` with the `solver` and `solver_version` assertions its header says Phase 3 will add

## Security Domain

`security_enforcement` is not set to false anywhere (`.planning/config.json` has only `workflow` and `graphify` keys), so it is treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no new credential or role; D-02) | `dlr_psse_writer` unchanged |
| V3 Session Management | no | none |
| V4 Access Control | yes | table-level `INSERT, SELECT` and per-table insert/select policies unchanged; view privileges preserved; `anon` and `authenticated` still hold nothing on the four tables (`verify_psse_results.sql`, `verify_exposure.sql` stay green) |
| V5 Input Validation | yes | writer `_check_tag` (fixed-text refusals) plus database `check` constraints; all values stay bound parameters |
| V6 Cryptography | no | none |
| V8 Data Protection | yes | the view guard stops unverified pandapower figures reaching the dashboard before Phase 6 |
| V14 Configuration | yes | idempotent migration, no credential in any file, header comment-only |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| A pandapower result stored as, or shown as, PSS/E (the default-stamp trap) | Spoofing / Repudiation | `pp-` id tied to `solver` by constraint; writer refusal; run-loop cross-check of the study's own solver; view guard |
| Insert with a mismatched tag from a buggy or older writer | Tampering | database check constraint refuses it; the failure is recorded as a failed run |
| Unverified figures exposed to the dashboard | Information Disclosure | `where solver = 'psse'` in the view (D-03) |
| Migration widening privileges by accident | Elevation of Privilege | no grant statement on the psse tables; text test asserts none; `verify_psse_results.sql` entry count stays 8 |
| Table lock during check re-add | Denial of Service | about 19 rows, paused writer; momentary `ACCESS EXCLUSIVE` |
| Run id, case label or connection detail in gap output | Information Disclosure | new output holds only times, solver tag, kinds, counts; pinned-line-shape test; one redacted failure line |
| Secret in a stored error | Information Disclosure | all writer messages stay fixed text or pass through `redact` as today |

## Sources

### Primary (HIGH confidence)
- Repository files opened this session: `supabase/migrations/20261109233541_psse_results.sql` (all 276 lines), `supabase/migrations/20261116200000_expose_latest_grid_study.sql` (all), `supabase/ops/verify_exposure.sql` (all), `supabase/ops/verify_psse_results.sql` (all), `backend/psse_job/{contract,run_record,writer,job,gaps,constants}.py` (all), parts of `launcher.py` and `study.py`, `backend/grid_study_contract.py`, `backend/pandapower_job/engine.py`, `docs/data-science/schema/psse_run_gaps.sql`, `backend/tests/{local_pg,psse_local_pg,psse_results_migration_test,psse_run_record_test,psse_writer_test,psse_gaps_pg_test,psse_contract_test,pandapower_import_gate_test,psse_phase4_validation_test,grid_study_expose_test,pandapower_study_job_test}.py`, parts of `psse_job_test.py`, `psse_laptop_modes_test.py`, `psse_setup_doc_test.py`, `psse_schema_pg_test.py`, `day_ahead_expose_test.py`, `day_ahead_migration_test.py`, `expose_migration_test.py`, `supabase_migration_test.py`, `dlr_live_runbook_test.py`, `supabase_smoke_test.py`; workstream `CONTEXT.md`, `REQUIREMENTS.md`, `STATE.md`, `ROADMAP.md`, `02-04-SUMMARY.md`, `02-06-SUMMARY.md`, `research/ARCHITECTURE.md` (lines 190-250).
- Commands run this session: baseline pytest over 14 files, environment probes (`initdb`, `pg_ctl`, `psql`, `docker`, `supabase` absent; psycopg 3.3.6 and pandapower 3.5.6 present), `sha256sum` versus `git show HEAD:` for the CRLF finding, `git ls-tree` over every local and remote branch for migration names.
- postgresql.org/docs/current/sql-altertable.html and sql-createview.html (quotes above).
- docs.python.org/3.7/library/collections.html (`defaults` added in 3.7).

### Secondary (MEDIUM confidence)
- `.planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-RESEARCH.md` (hand-off lines on `solver_version`, `psse_version=None`, details record).

### Tertiary (LOW confidence)
- Supabase `db push` ordering behaviour (A2), live Postgres major version (A3), live row count (A4): training knowledge or owner report, nothing observed.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, nothing new is introduced and every piece was read.
- Architecture: HIGH for the schema and the pin inventory; MEDIUM for the Python design, which is a recommendation consistent with every pin read but not yet built or run.
- Pitfalls: HIGH; pitfalls 1, 7 and 9 were found by reading and measuring, not by inference.

**Research date:** 2026-11-18
**Valid until:** about 30 days, or until Phase 2's engine or Phase 5's runner changes the `run_once` call shape.
