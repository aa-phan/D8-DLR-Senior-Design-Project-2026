# Phase 6: Dashboard Read Access and DEF-01 - Research

**Researched:** 2026-11-26
**Domain:** PostgreSQL view replacement on Supabase (owner-rights view, public-role grants), exposure checks, and a hand-off text for another team's branch
**Confidence:** HIGH (every in-repo claim was read this session; the SQL and the new check were run on a throwaway local PostgreSQL 17.12)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Replace `public.latest_grid_study` in place; do not add a second view. A new additive migration, dated after `20261118200000_psse_run_solver_tag.sql`, replaces the view with `create or replace`. It keeps the name, the 20 columns and their order (the contract the owner approved on 2026-11-16, `solver` already first, a column is only appended), `with (security_invoker = false)`, the revoke and grant, the column comments, and the 90 minute stale rule (`is_stale` when `slot_time` is more than 90 minutes old). It keeps the "complete run" rule (outcome `ok` or `fallback`). It drops the `r.solver = 'psse'` filter that Phase 3 (D-03) added and the constant `'psse'` label, and instead takes the newest complete run per solver, so the view returns one row per city per solver (at most 8 rows). The Phase 3 view comment said the per-solver view would replace it; this is that replacement. — **Reversibility:** costly — it edits an exposed, owner-applied view. It is idempotent and a later migration can restore the PSS/E-only filter.
- **D-02:** The migration is applied to the live project only after the Phase 5 soak passes (roadmap: until agreement and the soak pass, no unverified figure may be readable). Aaron applies it, then runs the read-only exposure checks. Until then the phase builds and tests it on a throwaway local database only, and the verification stays `human_needed` for the live apply, the same way Phase 3 was.
- **D-03:** A whitelist test compares the view's column list to the 20 approved columns (no run id, hash, bus number or detail field). With the dashboard's key, reading any of the four result tables is refused. `supabase/ops/verify_exposure.sql` and its tests are updated for the per-solver view; the Phase 3 tests and checks that pin the PSS/E-only behaviour (the view guard tests in `grid_study_expose_test.py` and `solver_tag_owner_check_test.py`, and any `verify_solver_tag.sql` check that names it) must be found and updated rather than left failing. The committed `verify_exposure.sql` has 36 checks today (owner's live run: 36 of 36, 2026-11-25); the planner states the new count.
- **D-04:** The DEF-01 section is not on this branch. It lives in `.planning/workstreams/software-dashboard/REQUIREMENTS.md` (and a STATE.md line of 2026-11-16) on branch `origin/feature/dashboard`, the software-dashboard workstream whose author is Aaron Phan. This phase does not edit that branch. It produces the exact replacement DEF-01 text as a file in this phase directory for the dashboard owner to commit there. The text must say: the blockers are cleared; the view is `latest_grid_study`; its columns by name; it returns one row per city per solver, so a reader must filter on `solver`; values are preliminary (public 39-bus case scaled per city, not a utility network); a PSS/E row is stale while that job is paused (90 minute rule). VIEW-03 is complete only when the dashboard owner has committed it.

### Claude's Discretion

Migration file name and time-of-day suffix, how the per-solver "newest run" is expressed in SQL, test layout and fixtures, and how the replacement DEF-01 text file is named, as long as the decisions above hold.

### Deferred Ideas (OUT OF SCOPE)

- Pruning or archiving old result rows (Phase 5 D-01 review trigger).
- A per-solver freshness alarm (OPS-06, v2).
- Dashboard-side work to read the view (the software-dashboard workstream owns it).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| VIEW-01 | A read-only view returns, per city and per solver, the newest complete result (dispatched capacity, limiting factor, solver, study time, age, stale flag) and exposes no run ids, hashes, bus numbers or detail fields | "Pattern 1" gives a probe-verified `distinct on (r.solver)` statement that keeps the 20 columns, owner rights, grants and the 90 minute rule; "Impact inventory" lists what pins the old behaviour |
| VIEW-02 | The dashboard's key reads that view and nothing else of the four result tables; the exposure checks (`verify_exposure.sql` and its test) are updated to match | "How the existing proofs are built" (anon and authenticated, `set role`, `InsufficientPrivilege`), a probe-verified new check (36 to 37), and the exact constants that change |
| VIEW-03 | The dashboard requirements' DEF-01 section is updated to say the blockers are cleared, naming the view and its columns | "DEF-01" section: verbatim current wording in three places on `origin/feature/dashboard`, and the structure of the hand-over file |
</phase_requirements>

## Summary

The change is small in SQL and wide in what pins the old behaviour. The view statement becomes one `select distinct on (r.solver) ... order by r.solver, r.slot_time desc, r.finished_at desc, r.run_id desc` over complete runs, joined to `psse_dispatched_capacity` exactly as today. I applied it on a throwaway PostgreSQL 17.12 after the full migration chain: `create or replace view` accepted it (the first column stays `text`), the 20 columns and their order, the ACL (`anon=r/postgres,authenticated=r/postgres`) and `security_invoker=false` were unchanged, and the view returned 0 rows (no runs), 4 rows (PSS/E only), 8 rows (both solvers, the older PSS/E run and the newer pandapower run each shown), 8 rows after a newer failed pandapower run (skipped), and 4 pandapower rows when only pandapower runs exist [VERIFIED: probe on local PostgreSQL 17.12, this session]. The result tables carry no `solver` column, so the join must take the solver from `psse_run` (done in the statement).

Eight places in the repository assert the PSS/E-only behaviour, the 36 count, or the migration ordering and will fail or go stale: two database tests and one sabotage case in `solver_tag_owner_check_test.py`, check 7 of `verify_solver_tag.sql`, two migration-ordering tests (`psse_results_migration_test.py`, `day_ahead_expose_test.py`), the `36` constants in `expose_migration_test.py` and `psse_results_migration_test.py`, and the prose in `docs/integration/rest-api.md` (up to four rows, "Every row today is psse"). The existing `latest_grid_study_one_row_per_city_per_solver` check in `verify_exposure.sql` already tolerates two solvers and stays true, so the exposure checker needs a new behavioural check rather than a repair: I drafted `latest_grid_study_has_each_solvers_newest_complete_run`, ran it inside a copy of `verify_exposure.sql` (37 rows), and it is true on an empty database, with PSS/E only, and with both solvers, and false for the old PSS/E-only view and for a view that hides one city [VERIFIED: probe].

DEF-01 is on `origin/feature/dashboard` in three places, not two: the Deferred bullet in `REQUIREMENTS.md`, the 2026-11-16 line in `STATE.md`, and chapter 10 of `docs/DASHBOARD-REQUIREMENTS.md`, which says "Where this checklist and that document disagree, that document wins" and already tells readers "up to one row per city per solver" but also "pandapower will add hourly rows later". The dashboard code on that branch does not read `latest_grid_study` today.

**Primary recommendation:** One new migration (`20261126200000_latest_grid_study_per_solver.sql`) with the probe-verified statement; retire `verify_solver_tag.sql` check 7 and add one behavioural check to `verify_exposure.sql` (36 to 37); rewrite the two Phase 3 database proofs to assert per-solver rows; update the two ordering tests and the two count constants; update `rest-api.md`; write one hand-over file with three replacement blocks for the dashboard owner.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Choose the newest complete run per solver | Database / Storage (view) | — | One statement over `psse_run`; the dashboard must never see run ids, so selection cannot live in a client |
| Keep the four result tables private | Database / Storage (grants, RLS, view owner rights) | — | `security_invoker = false` is what lets the public roles read the view while holding nothing on the tables |
| Stale flag and age | Database / Storage (view columns) | Browser / Client (FRESH-02 keeps ageing between polls) | The 90 minute rule is in the view; the dashboard only displays it |
| Filter by solver | Browser / Client or Frontend Server (the future reader) | Database (publishes the `solver` column) | The view returns all solvers; the reader must filter, so DEF-01 text must say so |
| Exposure verification | Owner's SQL editor (`verify_exposure.sql`) | Local throwaway PostgreSQL tests | Read-only checks run live by the owner; the same file is proved locally |
| DEF-01 wording | Software-dashboard workstream (Aaron Phan, other branch) | This phase (produces the text) | This phase may not edit that branch |

## Standard Stack

No new library and no new package. Everything runs on what the repository already uses.

### Core
| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| PostgreSQL (local throwaway) | 17.12 [VERIFIED: `postgres --version`] | Proves the migration and the checks | The harness (`local_pg.py`, `psse_local_pg.py`) builds a private cluster and refuses non-local hosts |
| psycopg | 3.3.6 [VERIFIED: `.venv` import] | Database tier of the tests | Already pinned (`requirements.txt`) |
| pytest | 9.0.3 [VERIFIED: `.venv` import] | Test runner | `pytest.ini` puts `backend` on the path |
| Python | 3.12.10 [VERIFIED: `.venv`] | Tests | Project venv |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `select distinct on (...)` | Newest row per group | Already used by `public.latest_rating` (`select distinct on (city)`), so it is a house pattern [VERIFIED: `backend/tests/expose_migration_test.py:112`] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `distinct on (r.solver)` | `row_number() over (partition by solver order by ...) = 1` | Same result, longer, no house precedent; use `distinct on` |
| Retiring `verify_solver_tag.sql` check 7 | Rewriting it as a text match on `pg_get_viewdef` | A definition-text match is fragile (it broke exactly this way, see Pitfall 1); a behavioural check in `verify_exposure.sql` is stronger |
| Adding an index on `psse_run (solver, slot_time desc)` | none | Not needed: about 24 runs a day per solver; Phase 3 deliberately added no index (its migration header: "No index is added: at 24 runs a day the existing slot_time index is enough"). Do not add one |

**Installation:** none.

**Version verification:** `postgres --version` and the venv imports above. No registry lookups apply.

## Package Legitimacy Audit

No external package is installed by this phase.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 psse_job (PSS/E laptop, paused)  --writes--+
                                            v
 pandapower hourly workflow (:20 UTC) ---> psse_run (solver text: 'psse' | 'pandapower', outcome, slot_time, finished_at, run_id)
        (Phase 5, live after soak)              |  1 row per run
                                                |  psse_dispatched_capacity (run_id, run_outcome, city; PK (run_id, city); no solver column)
                                                v
        newest_run CTE:  complete runs only (outcome in ok|fallback)
                         distinct on (solver)  ordered by solver, slot_time desc, finished_at desc, run_id desc
                                                |
                                                v  join on run_id AND run_outcome
        public.latest_grid_study  (owner rights, security_invoker = false)
           20 columns, solver first; <= 4 city rows per solver => <= 8 rows
           age_minutes, is_stale (> 90 min) computed at request time
                                                |
          anon / authenticated  (SELECT on the view only; the four psse_* tables refuse them)
                                                |
                         dashboard reader: filter on solver, show label "Preliminary ..."

 Owner after the live apply:  verify_exposure.sql (37 checks), verify_psse_results.sql (7), verify_solver_tag.sql (6)
 DEF-01 hand-over file  --(Aaron commits)-->  origin/feature/dashboard (REQUIREMENTS.md, STATE.md, docs/DASHBOARD-REQUIREMENTS.md ch. 10)
```

### Recommended Project Structure
```
supabase/migrations/20261126200000_latest_grid_study_per_solver.sql   # new, additive, idempotent
supabase/ops/verify_exposure.sql           # edit: header lines 50-58, new CTE and new check inside the two marked grid_study regions
supabase/ops/verify_solver_tag.sql         # edit: retire check 7 (ord 7), header lines 35-38
backend/grid_study_contract.py             # edit: docstring; optionally SOLVERS = ("psse", "pandapower") and MAX_ROWS = 8
backend/tests/grid_study_per_solver_test.py   # new: text tier + database tier for the new migration (or extend grid_study_expose_test.py)
backend/tests/solver_tag_owner_check_test.py  # edit: CHECK_NAMES, _SABOTAGE, rewrite test_db_a_newer_pandapower_run_never_changes_the_view
backend/tests/expose_migration_test.py        # edit: _VERIFY_CHECKS (+1), comment lines 308-309, sabotage cases for the new check
backend/tests/psse_results_migration_test.py  # edit: _EXPOSURE_CHECKS 36 -> 37, ordering list line 98
backend/tests/day_ahead_expose_test.py        # edit: ordering allow-list lines 133-137
docs/integration/rest-api.md                  # edit: view prose and the solver column row
.planning/workstreams/pandapower-solver/phases/06-dashboard-read-access-and-def-01/06-DEF01-REPLACEMENT.md   # new hand-over file
```

The migration name must sort after `20261118200000_psse_run_solver_tag.sql` and should not collide with any allow-list suffix. `origin/main` and `origin/feature/dashboard` hold no migration later than `20261116200000_expose_latest_grid_study.sql`, and this branch's last is `20261118200000_psse_run_solver_tag.sql`, so a `20261126...` stamp cannot land "before the last migration on the remote" for `supabase db push` [VERIFIED: `git ls-tree` of five remote branches, this session]. The time-of-day suffix is Claude's discretion.

### Pattern 1: The replacement statement (probe-verified)

**What:** newest complete run per solver, then the same join and the same 20 select items.
**When to use:** the whole migration; this is the only view statement.

Current statement, verbatim, lines 82-114 of `supabase/migrations/20261118200000_psse_run_solver_tag.sql`: a `newest_run` CTE with `where r.outcome in ('ok', 'fallback') and r.solver = 'psse' order by r.slot_time desc, r.finished_at desc, r.run_id desc limit 1`, then `select 'psse'::text as solver, d.city, n.slot_time, n.finished_at as study_finished_at, n.outcome as run_outcome, ...` `from newest_run n join public.psse_dispatched_capacity d on d.run_id = n.run_id and d.run_outcome = n.outcome order by d.city;` [VERIFIED: Read, lines 82-114].

Replacement (applied and exercised on PostgreSQL 17.12 this session):

```sql
create or replace view public.latest_grid_study with (security_invoker = false) as
with newest_run as (
    select distinct on (r.solver) r.solver, r.run_id, r.slot_time, r.finished_at, r.outcome
      from public.psse_run r
     where r.outcome in ('ok', 'fallback')
     order by r.solver, r.slot_time desc, r.finished_at desc, r.run_id desc
)
select
    n.solver,
    d.city,
    n.slot_time,
    n.finished_at as study_finished_at,
    n.outcome as run_outcome,
    d.rating_source,
    d.fallback_reason,
    d.city_rating_valid_time,
    d.applied_amps_per_conductor,
    d.dispatched_amps_per_conductor,
    d.subconductors_per_phase,
    d.line_voltage_kv,
    d.applied_mva,
    d.voltage_limit_mva,
    d.dispatched_mva,
    d.dispatched_mw,
    d.dispatched_mva / d.applied_mva * 100 as usable_pct,
    d.limiting_factor,
    ceil(extract(epoch from (now() - n.slot_time)) / 60)::integer as age_minutes,
    (n.slot_time < now() - interval '90 minutes') as is_stale
from newest_run n
join public.psse_dispatched_capacity d on d.run_id = n.run_id and d.run_outcome = n.outcome
order by d.city, n.solver;

revoke all on public.latest_grid_study from public, anon, authenticated;
grant select on public.latest_grid_study to anon, authenticated;
```

Facts the probe established [VERIFIED: probe on PostgreSQL 17.12 after the full chain]:
- `create or replace` is accepted: the first column was `text` before (`'psse'::text`) and is `text` now (`psse_run.solver text`). A type change would have been refused.
- 20 columns, first column `solver`; ACL `{postgres=arwdDxtm/postgres,service_role=arwdDxtm/postgres,anon=r/postgres,authenticated=r/postgres}`, `security_invoker=false`, owner `postgres`: identical before and after.
- `pg_get_viewdef` no longer contains `solver = 'psse'` (so check 7 of `verify_solver_tag.sql` becomes false) and does contain `DISTINCT ON (r.solver)`.
- Behaviour: no runs gives 0 rows; PSS/E run only gives 4 rows, solver `psse`; PSS/E at hour-2 plus pandapower at hour-1 gives 8 rows, one slot_time per solver; adding a newer failed pandapower run (no result rows) still gives the same 8 rows; only pandapower runs gives 4 rows read as `authenticated`.
- When one solver has no complete run the view returns only the other solver's rows (at most 4); it never returns a placeholder row.
- At most 8 rows: `psse_dispatched_capacity` has `constraint psse_dispatched_capacity_pk primary key (run_id, city)` and `city ... check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO'))`, so one run has at most four rows, times two solvers [VERIFIED: `supabase/migrations/20261109233541_psse_results.sql:69,89`]. A complete run having all four is the writer's all-or-nothing behaviour, not a constraint.

**Does `psse_dispatched_capacity` carry `solver`?** No. The solver-tag migration adds `solver` and `solver_version` only to `public.psse_run` (header: "column public.psse_run.solver ..."), and the dispatched-capacity DDL has no such column [VERIFIED: Read both files]. The join through `newest_run` (which takes `r.solver`) is therefore the only route; the three other result tables are not read by the view.

**Comments to carry over.** The 20 column comments and the revoke/grant are reissued as in lines 116-140 of the solver-tag migration. Two texts become false and must change: the `solver` column comment ("psse (Siemens PSS/E). pandapower rows arrive in a later release.") and the view comment (one row per city; the closing sentence "Until the per-solver view replaces it, only PSS/E runs (solver psse) are shown."). Proposed:

- view comment: the 2026-11-18 text with "The newest complete grid-study run (outcome ok or fallback), one row per city" replaced by "The newest complete grid-study run (outcome ok or fallback) of each solver, one row per city per solver (at most 8 rows: AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO for psse and for pandapower); filter on solver", the sentence "Until the per-solver view replaces it ..." deleted, everything else kept (PRELIMINARY wording, 90 minutes, owner's rights, read-only).
- `solver` comment: `'none (identifier): the power-flow program that produced the row; psse (Siemens PSS/E) or pandapower (open-source solver). The view returns one row per city per solver, so filter on this column.'`

This edits one of the "column comments" that D-01 says are kept; see Open Question 2.

### Pattern 2: The idempotent migration (house pattern)

The migration repeats the house conventions [VERIFIED: Read `20261116200000_expose_latest_grid_study.sql` and `20261118200000_psse_run_solver_tag.sql`]:
- A comment-only header first (the solver-tag test asserts the file starts with `--` lines before the first statement and contains none of `password`, `postgres://`, `postgresql://`, `create role`, `alter role`). State: what it creates, that grants are unchanged, why `security_invoker = false` (lint 0010 accepted for this view only; do not switch it), that it never edits an applied migration, that it is idempotent, that it must sort and be applied after `20261118200000_psse_run_solver_tag.sql` (applying the solver-tag file alone afterwards would restore the PSS/E-only view), and that the owner applies it only after the Phase 5 soak with `supabase db push --db-url ...`, then runs the three read-only checks.
- `create or replace view ... with (security_invoker = false)`; `revoke all ... from public, anon, authenticated;` then `grant select ... to anon, authenticated;`; `comment on view` and 20 `comment on column` statements, all re-runnable.
- No `alter table`, no `drop`, no data change, no grant on any `psse_*` table, no role, no credential.
- Re-apply proof: the two existing chain re-apply tests (`grid_study_expose_test.test_the_migration_reapplies_cleanly` re-applies every file from the grid-study migration onward, in name order, twice and compares `pg_get_viewdef` and `relacl`; `expose_migration_test.test_expose_migration_reapplies_cleanly` does the same from the expose file) pick up a new last file automatically and keep passing, because the chain ends with the new view each time [VERIFIED: Read both tests].

### Pattern 3: The new exposure check (probe-verified draft)

`verify_exposure.sql` is one `with ... select ... union all ...` ordered by `check_name`. Its grid-study parts sit between marker lines so a test can strip them (`-- BEGIN grid_study_ctes` ... `-- END grid_study_ctes` and `-- BEGIN grid_study_checks` ... `-- END grid_study_checks`). Put the new CTE and check inside those regions.

```sql
-- inside the grid_study_ctes region, after psse_readable:
,
newest_complete_run as (
    select distinct on (r.solver) r.solver, r.run_id, r.slot_time
      from public.psse_run r
     where r.outcome in ('ok', 'fallback')
     order by r.solver, r.slot_time desc, r.finished_at desc, r.run_id desc
)

-- inside the grid_study_checks region:
    union all
    select 'latest_grid_study_has_each_solvers_newest_complete_run',
           coalesce(
               not exists (select 1 from newest_complete_run n
                            where (select count(*) from public.latest_grid_study v
                                    where v.solver = n.solver and v.slot_time = n.slot_time)
                                  <> (select count(*) from public.psse_dispatched_capacity d where d.run_id = n.run_id))
               and (select count(*) from public.latest_grid_study)
                   = (select count(*) from public.psse_dispatched_capacity d join newest_complete_run n on n.run_id = d.run_id),
               false),
           'view rows=' || coalesce((select count(*) from public.latest_grid_study)::text, 'view missing') ||
               ', solvers with a complete run=' || (select count(*) from newest_complete_run)::text
```

Results inside a copy of the real file, with ratings seeded so the other checks are green [VERIFIED: probe, 37 rows each time]: no runs, new view: true (`view rows=0, solvers with a complete run=0`); PSS/E run only: true (4, 1); PSS/E plus pandapower: true (8, 2); the Phase 3 PSS/E-only view with both solvers present: false (4, 2); a view that hides EL_PASO: false (6, 2). No other check changed. The detail holds counts only.

The new check compares the view with the tables, which the owner can read in the SQL editor. It needs no `pg_get_viewdef` text match. It is true on an empty `psse_run`, which matters because `expose_migration_test`'s module database has no runs.

### Anti-Patterns to Avoid
- **Editing an applied migration.** `20261109233541_psse_results.sql`, `20261116200000_expose_latest_grid_study.sql`, `20261118200000_psse_run_solver_tag.sql` stay byte-identical. Several existing tests (`test_text_the_guarded_view_is_the_old_view_plus_one_predicate`, the sabotage `_sabotage_unguarded_view`) read the old files and must keep passing unchanged.
- **Matching `pg_get_viewdef` text in a live check.** It broke check 7 of `verify_solver_tag.sql` the moment the view changed.
- **Adding `solver` to the other three result tables or a new index.** Out of scope and not needed.
- **Applying `20261118200000_psse_run_solver_tag.sql` alone after this migration is live.** It would put the PSS/E-only view back. The new header must say so (the grid-study header gave the same warning for its successor).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Newest row per group | A loop or a Python-side reduction | `distinct on (r.solver)` with a full tie-break order | House pattern; the full order (`slot_time`, `finished_at`, `run_id`) is deterministic when two runs share an hour |
| A throwaway database | A new fixture | `local_pg.cluster` / `psse_local_pg.cluster` and `local_pg.apply_migrations(url)` | Already refuses non-local hosts and stops the cluster; models `anon`, `authenticated`, `service_role` with the legacy default grants |
| Complete-run row sets | Hand-written INSERTs | `psse_local_pg.valid_run_rows(run_id, started_at, outcome=...)`, `make_run_id(n, when, prefix="pp")`, `failed_run_row`, `insert_rows` | Rows that satisfy every identity constraint; override `solver` and `solver_version` on the `psse_run` row as `solver_tag_owner_check_test._complete_run` does |
| Running a one-SELECT check file | A custom runner | `local_pg.run_select_file(conn, path)` | Returns dict rows; used by every existing checker test |
| The role under test | A real key | `set role anon` / `set role authenticated` after `set timezone = 'UTC'` | The dashboard's publishable key maps to `anon`; the harness models both public roles |

**Key insight:** every fixture, helper and check-runner already exists; this phase adds one SQL file, one CTE and one check, and rewrites assertions.

## Impact inventory: what pins the old behaviour, the old counts or the old ordering

All items below were read this session. "Stays" means it keeps passing unchanged and needs no edit.

| # | File and place | What it pins | What it must become |
|---|----------------|--------------|---------------------|
| 1 | `backend/tests/solver_tag_owner_check_test.py` `CHECK_NAMES` (lines 44-52), last name `latest_grid_study_reads_psse_runs_only` | The seven check names of `verify_solver_tag.sql`, in order, text and database tiers | Drop the last name (6 names) if check 7 is retired (recommended) |
| 2 | same file, `_sabotage_unguarded_view` and the `_SABOTAGE` entry (lines 272-288) and the parametrized `test_db_each_check_can_fail` | Check 7 can be made to fail by re-applying the Phase 3 view statement from the grid-study file | Delete with check 7; the same "can fail" proof moves to the new `verify_exposure` check (re-apply the Phase 3 PSS/E-only statement with both solvers present, expect the new check false) |
| 3 | same file, `test_db_tracer_every_check_is_ok_after_the_chain` (lines 212-240) | After the full chain, every `verify_solver_tag` check ok, and `verify_psse_results` and `verify_exposure` all ok with a PSS/E and a pandapower run present | Fails today only through check 7; after the check change it passes unchanged and now also exercises the new exposure check with both solvers. Seeding already inserts one `psse` and one `pandapower` run |
| 4 | same file, `test_db_a_newer_pandapower_run_never_changes_the_view` (lines 325-349) | A newer pandapower run is invisible; with only pandapower runs the view is empty | Rewrite as per-solver: with PSS/E at hour-2 and pandapower at hour-1 the view returns 8 rows, one slot_time per solver; with only pandapower runs it returns 4 rows, solver `pandapower`; a newer failed pandapower run changes nothing. Rename (the name states the removed behaviour) |
| 5 | same file, `test_db_the_guard_keeps_columns_comments_and_privileges` (lines 383-397) and `test_text_the_guarded_view_*` (lines 113-168) | Properties of the Phase 3 migration read in isolation (sibling database stops at the Phase 3 file via `apply_solver_tag_migration`; file-versus-file text diff) | Stays: they test an applied file that is not edited. Update only the module docstring (lines 1-17) and the comment on line 43 ("The last name is the view guard") |
| 6 | `supabase/ops/verify_solver_tag.sql`: ord 7 (lines 139-146) and header lines 35-38 | `position('solver = ''psse''' in pg_get_viewdef(...)) > 0` | Retire ord 7 and its header paragraph (the guard is gone by design); the file then has 6 checks. The comment on lines 7-14 about "all three all ok" stays true |
| 7 | `backend/tests/expose_migration_test.py` `_VERIFY_CHECKS` (lines 310-347) and the comment on lines 308-309 | 36 check names, sorted, equal to the checker's rows | Add `latest_grid_study_has_each_solvers_newest_complete_run`; 37 in all; update the comment ("the seven grid-study view checks: 36 in all" becomes eight and 37) |
| 8 | `backend/tests/psse_results_migration_test.py`: `_EXPOSURE_CHECKS = 36` (line 38) | Row count of the checker on the full chain | 37. `_EXPOSURE_CHECKS_WITHOUT_GRID_STUDY = 29` stays 29 because the new CTE and check sit inside the stripped regions. `_exposure_checker_without_grid_study` (lines 229-246) asserts each marker region is found exactly once and four exact replacement strings occur once each, so do not reformat those lines in `verify_exposure.sql` |
| 9 | same file, line 98: `names[names.index(name) + 1:] == [_GRID_STUDY_EXPOSE_MIGRATION, _SOLVER_TAG_MIGRATION]` and the test name (line 91) | The only migrations after `psse_results` | Append the new file name; fails the moment the file exists |
| 10 | `backend/tests/day_ahead_expose_test.py` lines 127-137 | After the day-ahead expose file, only names ending `_psse_results.sql`, `_expose_latest_grid_study.sql`, `_psse_run_solver_tag.sql`, and `assert len(after) <= 3` | Add the new suffix (`_latest_grid_study_per_solver.sql`) to the tuple and raise the bound to 4; fails the moment the file exists |
| 11 | `backend/tests/grid_study_expose_test.py` | Text tier reads the 2026-11-16 file; database tier asserts `{r["solver"] for r in rows} == {"psse"}` where every inserted run is PSS/E; columns equal `contract.COLUMNS`; both public roles read the view and not the four tables; write refusals; chain re-apply | All stay passing unchanged (every run it inserts is `psse`; the 20 columns and grants are unchanged). Edit only the docstring. Add the new tests here or in a new file (see Validation Architecture) |
| 12 | `backend/tests/solver_tag_migration_test.py` | `names.index(_MIGRATION_NAME) == names.index(_GRID_STUDY_MIGRATION) + 1`; `_ALLOWED_STARTS` statement inventory of the Phase 3 file | Stays (the new file sorts after both; the inventory reads the Phase 3 file only). Its database tier uses `apply_solver_schema`, which never applies the new file |
| 13 | `backend/grid_study_contract.py` | `COLUMNS` (20 names), `FORBIDDEN` (10 names), `STALE_AFTER_MINUTES = 90`; docstring names the 2026-11-16 migration | `COLUMNS` unchanged (the whitelist). Docstring: name the replacing migration. Optionally add `SOLVERS = ("psse", "pandapower")` and `MAX_ROWS = 8` for the new tests |
| 14 | `docs/integration/rest-api.md` lines 29, 246 and the "Grid-study results (preliminary)" bullets "Where the numbers come from", "How often", "Solvers", and the `solver` row of the columns table | "up to four rows, one per city", "Every row today is `psse`", "A later release adds ... pandapower", "`psse` today; `pandapower` in a later release" | Rewrite: up to eight rows, one per city per solver, filter on `solver`, PSS/E rows stale while its job is paused, pandapower hourly at :20 UTC (Phase 5) once the owner applies the migration. Headings are pinned by `rest_api_doc_test.py`; the grid-study section text is not, so keep every `##` heading and change prose only. Line 137 ("the tables are not readable ... `latest_grid_study` is the only way in") stays true |
| 15 | `docs/data-science/decisions/dlr_live_runbook.md:673` says "29 rows, all ok" | Pre-existing drift from before the grid-study view (live is 36) | Not this phase's; mention to the owner only |

[VERIFIED: Read of each file and line cited, this session; `grep` of `latest_grid_study`, `verify_exposure`, `verify_solver_tag`, `_psse_run_solver_tag` and `migration_files()` across `backend/`, `docs/`, `supabase/`, `.github/`.] No code under `backend/psse_job/`, `backend/pandapower_job/` or `backend/psse_session/` mentions the view, and `frontend/` on this branch does not read it.

Why check 7 is retired rather than rewritten: a definition-text match on the new statement (for example `DISTINCT ON (r.solver)`) would be as fragile as the check it replaces, and the new `verify_exposure` check proves the behaviour. If the owner wants the owner-run trio to keep seven in `verify_solver_tag.sql`, the alternative is to move the new check there instead; the count then reads 7 / 7 / 36. Recommended counts after this phase: `verify_solver_tag.sql` 6, `verify_psse_results.sql` 7, `verify_exposure.sql` 37.

## How the existing proofs are built

- **Roles modelled.** `local_pg.SUPABASE_ROLES_SQL` creates `anon`, `authenticated`, `service_role` if missing and `alter default privileges in schema public grant all on tables to anon, authenticated, service_role` (Supabase's legacy auto-grants, the worst case). The dashboard's publishable key is `anon`; `authenticated` is tested alongside [VERIFIED: `backend/tests/local_pg.py:39-55`].
- **Reading as the key.** Tests open `psycopg.connect(url)`, `set timezone = 'UTC'`, then ``set role "anon"`` (via `sql.Identifier`), query, and `rollback()` in `finally`; fixtures give an admin URL and a `clean_pg` that truncates the four result tables (`psse_local_pg.reset`) [VERIFIED: `grid_study_expose_test._session`, `solver_tag_owner_check_test._view_rows`].
- **Whitelist of columns.** `test_the_view_columns_equal_the_contract` reads `pg_attribute` for `public.latest_grid_study` in `attnum` order and asserts `tuple(names) == contract.COLUMNS` and `not set(names) & set(contract.FORBIDDEN)`. The 20 names, verbatim from `backend/grid_study_contract.py:11-32`: `solver`, `city`, `slot_time`, `study_finished_at`, `run_outcome`, `rating_source`, `fallback_reason`, `city_rating_valid_time`, `applied_amps_per_conductor`, `dispatched_amps_per_conductor`, `subconductors_per_phase`, `line_voltage_kv`, `applied_mva`, `voltage_limit_mva`, `dispatched_mva`, `dispatched_mw`, `usable_pct`, `limiting_factor`, `age_minutes`, `is_stale`. `FORBIDDEN` (lines 35-38): `run_id`, `case_id`, `case_sha256`, `mapping_sha256`, `ratings_used`, `error`, `ratings_read_error`, `details`, `critical_bus`, `job_version`. Success criterion 3's whitelist test already exists and keeps passing; the new tests should re-run it with both solvers' rows present and also assert the selected row dicts carry none of `FORBIDDEN`.
- **Tables refused.** `test_the_public_roles_read_the_view_but_not_the_tables` (parametrized over `anon` and `authenticated`): for each of `psse_run`, `psse_dispatched_capacity`, `psse_voltage_margin`, `psse_contingency_result`, `set role` then `select 1 from public.<table> limit 1` must raise `errors.InsufficientPrivilege`; then `select * from public.latest_grid_study` must succeed. The live-side twin is the check `psse_tables_not_readable_by_public_roles` in `verify_exposure.sql`. The new database tests must read the view as the public role while rows of both solvers exist, so the proof covers the owner-rights path that returns data the role cannot reach directly.
- **Write refusal.** `test_the_public_roles_cannot_write_through_the_view` accepts `InsufficientPrivilege` or `ObjectNotInPrerequisiteState` and asserts `has_table_privilege('anon', 'public.latest_grid_study', 'insert, update, delete')` is false. Unchanged by the new statement (a `distinct on` view is not auto-updatable either).
- **Stale flag.** `test_usable_pct_limiting_factor_age_and_stale` shows a run started in the current hour is not stale and a run two hours earlier is (`age_minutes > contract.STALE_AFTER_MINUTES`). The new per-solver test should seed a fresh pandapower run and an old PSS/E run and assert `is_stale` is false for the pandapower rows and true for the PSS/E rows in the same response.
- **Exposure checker tests.** `expose_migration_test.test_verify_exposure_sql_reports_every_check_ok` asserts `[r["check_name"] for r in rows] == sorted(_VERIFY_CHECKS)` and no failing row; the sabotage style is a rolled-back transaction as superuser, then `bad = {names with ok is not True}` compared to an expected set. Follow `_DAY_AHEAD_SABOTAGE` for new cases.

## Common Pitfalls

### Pitfall 1: The retired guard check keeps failing the owner's live run
**What goes wrong:** After the live apply, `verify_solver_tag.sql` check 7 reads the view definition for `solver = 'psse'`, which is now absent, so it reports false and the owner thinks the apply broke something.
**Why it happens:** The check was written to prove the Phase 3 guard; this phase removes the guard by design.
**How to avoid:** Retire check 7 in the same change; the runbook step for the owner must name the three files and their new counts (6, 7, 37). The Phase 3 live run used the old file; the owner must use the committed new one.
**Warning signs:** `test_db_tracer_every_check_is_ok_after_the_chain` failing on `latest_grid_study_reads_psse_runs_only` after the migration file exists.

### Pitfall 2: Two ordering tests fail the instant the migration file exists
**What goes wrong:** `psse_results_migration_test` (exact list after `psse_results`) and `day_ahead_expose_test` (suffix allow-list and `len(after) <= 3`) fail on a clean checkout.
**Why it happens:** Both enumerate migrations by name; Phase 3 had to edit the same two for its file.
**How to avoid:** Edit both in the same plan that adds the migration. Add the suffix `_latest_grid_study_per_solver.sql` (or whatever name is chosen) to the allow-list and bound the length at 4.

### Pitfall 3: A timestamp-sensitive test
**What goes wrong:** Runs inserted "now" can sit on either side of the 90 minute boundary, or on the hour boundary.
**Why it happens:** `slot_time` is the hour of `started_at` (constraint `psse_run_slot_matches_start_ck`), and the view uses `now()`.
**How to avoid:** Build runs relative to `local_pg.current_utc_hour()` as the existing tests do (`hour - timedelta(hours=2) + timedelta(minutes=7)`). Pin staleness only by hours-ago values well away from 90 minutes, or by the transaction-fixed `now()` trick used in `test_exactly_90_minutes_is_fresh_and_one_microsecond_more_is_stale`.

### Pitfall 4: A run id that disagrees with its solver
**What goes wrong:** An insert with `solver = 'pandapower'` and a `psse-` id fails `psse_run_solver_run_id_ck`.
**Why it happens:** The tie constraint from Phase 3.
**How to avoid:** Use `make_run_id(n, when, prefix="pp")` together with `solver="pandapower"` and `solver_version="3.5.6"` on the `psse_run` row, as `solver_tag_owner_check_test._complete_run` does. The older `grid_study_expose_test._insert_run` writes only `psse-` ids with the default solver; extend it with a `solver` argument or use the `psse_local_pg` helpers in the new file.

### Pitfall 5: The replacement DEF-01 text claims pandapower rows that are not live yet
**What goes wrong:** The text says the view carries pandapower rows while the live apply and the soak have not happened (the Phase 5 soak has not run).
**Why it happens:** This phase is built before D-02's live apply.
**How to avoid:** The hand-over file is written now but marked "hand over after the owner applies the migration"; dates and the "pandapower rows are live" sentence carry an explicit placeholder for the apply date. The text may say what the view does once the migration is applied, and must not state a date that has not happened.

### Pitfall 6: Windows-only failures read as regressions
**What goes wrong:** Four tests in the files this phase edits fail on this Windows machine before any change.
**Why it happens:** Three byte-hash tests meet CRLF checkouts; `test_is_provisional_reads_the_real_labels` is the known Windows failure.
**How to avoid:** Compare against the baseline in Validation Architecture. Do not add a SHA-256 pin for the new migration until it has been applied live (the convention pins applied files), and expect the same CRLF failure on Windows if it is added later.

### Pitfall 7: Breaking the marker regions of `verify_exposure.sql`
**What goes wrong:** `_exposure_checker_without_grid_study` fails with an assertion on the region count or a replacement string.
**Why it happens:** It strips `-- BEGIN grid_study_ctes` / `-- END grid_study_ctes` and `-- BEGIN grid_study_checks` / `-- END grid_study_checks` by line-anchored regex and replaces four exact text fragments (`",\n           ('latest_grid_study')\n"`, `"(select count(*) from select_grants) = 12,"`, `"' of 12'"`, `"the six published objects: "`).
**How to avoid:** Put the new CTE and check strictly inside the existing regions; leave those four fragments byte-identical. The 12 select grants (six objects times two roles) do not change.

## Code Examples

### Reading the view as the dashboard's key in a new test (existing helper shape)
```python
# Source: backend/tests/solver_tag_owner_check_test.py:308-322 (_view_rows), verified by reading
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

### Seeding one run per solver (existing helpers)
```python
# Source: backend/tests/solver_tag_owner_check_test.py:190-195 and 325-333, psse_local_pg.py:286-300
hour = local_pg.current_utc_hour()
psse_started = hour - timedelta(hours=2) + timedelta(minutes=7)   # more than 90 minutes old: stale
pp_started = hour + timedelta(seconds=1)                          # fresh at any minute of the hour
run_id = psse_local_pg.make_run_id(21, pp_started, prefix="pp")
rows = psse_local_pg.valid_run_rows(run_id, pp_started)
rows["psse_run"] = [dict(rows["psse_run"][0], solver="pandapower", solver_version="3.5.6")]
```
The fresh seed `hour + timedelta(seconds=1)` is the one `test_usable_pct_limiting_factor_age_and_stale` uses; a run started at `hour - 1h + 7min` is stale in the second half of the following hour, so do not use it for a "fresh" assertion.

### Asserting the per-solver result
```python
rows = _view_rows(clean_pg)
assert len(rows) == 8
by_solver = {}
for row in rows:
    by_solver.setdefault(row["solver"], []).append(row)
assert sorted(by_solver) == ["pandapower", "psse"]
assert all(sorted(r["city"] for r in group) == sorted(psse_local_pg.CITIES) for group in by_solver.values())
assert all(r["is_stale"] is True for r in by_solver["psse"])
assert not set(rows[0]) & set(contract.FORBIDDEN)
```

## DEF-01: what is on `origin/feature/dashboard`, and the hand-over file

`origin/feature/dashboard` at commit `1f531f80854c8ea20feb72eb7b420749766091ac`, 2026-11-25 19:00:56 -0600, author Aaron Phan. A `git fetch --dry-run` this session listed `shadow-collection-data` as the only changed remote ref, so the local `origin/feature/dashboard` is current [VERIFIED: `git log -1`, `git fetch --dry-run`].

Current wording, verbatim, in the three places that state it [VERIFIED: `git show "origin/feature/dashboard:<path>"` with `MSYS_NO_PATHCONV=1`]:

1. `.planning/workstreams/software-dashboard/REQUIREMENTS.md` lines 98-102 (section `## Deferred`):
   ```
   ## Deferred

   - **DEF-01**: Grid-study results (usable share of the rating and its limiting factor) per city.
     Unblocked 2026-11-16: read `latest_grid_study` with the dashboard's key; preliminary values,
     stale while the PSS/E job is paused (ch. 10).
   ```
2. `.planning/workstreams/software-dashboard/STATE.md` line 45 (under `### Decisions`):
   `- 2026-11-16: DEF-01 unblocked. The Data Science owner exposed the view `latest_grid_study` to the dashboard's key (the result tables stay private) and 19 real PSS/E runs exist. Still deferred from the first release; values are preliminary.`
   Line 44 is the earlier decision `- 2026-11-11: Grid-study (PSS/E) results are a deferred requirement, DEF-01 (Data Science owner).`
3. `.planning/workstreams/software-dashboard/docs/DASHBOARD-REQUIREMENTS.md` chapter 10, lines 441 and 443: "**Unblocked on 2026-11-16.** Both blockers are cleared. First, the Data Science owner opened read access: the view `latest_grid_study` (migration `20261116200000_expose_latest_grid_study.sql`) is readable with the dashboard's key, while the four result tables stay private. Second, the study job has run on real PSS/E: 19 runs were written on 2026-11-11 and 2026-11-12, on the public IEEE 39-bus test case scaled per city." and "What to read: `GET /rest/v1/latest_grid_study`, up to one row per city per solver from the newest complete run, with `usable_pct`, `limiting_factor`, `dispatched_amps_per_conductor`, `applied_amps_per_conductor`, `slot_time`, `age_minutes` and `is_stale` among its 20 columns. ... Three things to design for: every value is preliminary ..., the PSS/E job is paused so every row is stale today ..., and an open-source solver (pandapower) will add hourly rows later, told apart by the `solver` column. Nothing is built for it in the first release, and the layout does not reserve space for it; the Software team decides when to take it up."

Observations:
- The REQUIREMENTS.md bullet already says "Unblocked 2026-11-16" for the PSS/E-only view, so VIEW-03's replacement must add what is new: the blockers named, all 20 columns by name, one row per city per solver (so filter on `solver`), pandapower rows, and the stale rule per solver. `REQUIREMENTS.md` states "Where this checklist and that document disagree, that document wins" (line 19-20), and chapter 10 has the future-tense "pandapower will add hourly rows later" and "so every row is stale today" that becomes wrong once the migration is applied and the soak runs. The hand-over file therefore needs a third block for chapter 10, beyond the two places D-04 names. (Open Question 3.)
- `ROADMAP.md` of that workstream says "DEF-01 (grid-study results) stays deferred and is in neither workstream" (line 18), and `grounding/coverage.md:80` says "`latest_grid_study` unused; deferred by design". Neither needs editing; the text must keep saying "deferred from the first release" while saying "blockers cleared".
- The dashboard code on that branch does not read the view: `git grep -n -i "latest_grid_study\|grid_study" origin/feature/dashboard -- . ':!.planning' ':!docs'` returns only the Data Science files `backend/grid_study_contract.py` and three `backend/tests/*` files, nothing under `frontend/` [VERIFIED: git grep]. One row per city per solver breaks no current consumer; the future reader must filter on `solver`.

### Structure of the hand-over file

File: `.planning/workstreams/pandapower-solver/phases/06-dashboard-read-access-and-def-01/06-DEF01-REPLACEMENT.md` (name is discretionary). Sections, in order:

1. **Header and instructions to the dashboard owner:** from the Data Science owner to Aaron Phan; commit on branch `feature/dashboard`; do it after the owner applies the migration (state the migration name); three blocks, each "replace this exact text with that text"; nothing else changes. State that VIEW-03 is closed only by that commit and say how to confirm (the three `git grep` commands below).
2. **Block A, `REQUIREMENTS.md` `## Deferred`:** the current bullet (lines 100-102 above) quoted verbatim, then the replacement bullet.
3. **Block B, `STATE.md` Decisions:** keep the 2026-11-16 line, add one dated line (placeholder for the apply date).
4. **Block C, `docs/DASHBOARD-REQUIREMENTS.md` chapter 10:** replace the two paragraphs (lines 441 and 443).
5. **Confirmation commands** the Data Science owner can run later: `MSYS_NO_PATHCONV=1 git show "origin/feature/dashboard:.planning/workstreams/software-dashboard/REQUIREMENTS.md" | grep -n "solver"`, and the same for `STATE.md` and `docs/DASHBOARD-REQUIREMENTS.md`.

Draft of the Block A replacement bullet (the planner finalises wording; every fact is from this research or from D-04):

```
- **DEF-01**: Grid-study results (usable share of the rating and its limiting factor) per city.
  Blockers cleared: the dashboard's key can read the view `latest_grid_study` (and nothing else of
  the result tables, which stay private), and the study runs hourly on pandapower as well as on
  PSS/E. The view returns one row per city per solver (at most 8 rows), so a reader must filter on
  `solver` (`psse` or `pandapower`) rather than assume one row per city. Its 20 columns, in order:
  `solver`, `city`, `slot_time`, `study_finished_at`, `run_outcome`, `rating_source`,
  `fallback_reason`, `city_rating_valid_time`, `applied_amps_per_conductor`,
  `dispatched_amps_per_conductor`, `subconductors_per_phase`, `line_voltage_kv`, `applied_mva`,
  `voltage_limit_mva`, `dispatched_mva`, `dispatched_mw`, `usable_pct`, `limiting_factor`,
  `age_minutes`, `is_stale`. Values are preliminary: the public IEEE 39-bus case scaled per city,
  not a utility network, not reviewed by Power Systems. A result is stale when its hour is more than
  90 minutes old; a PSS/E row is stale while that job is paused. Still deferred from the first
  release (ch. 10).
```

A text test in this repository can pin the file: it names `latest_grid_study`, every name in `contract.COLUMNS` (so the file cannot drift from the whitelist), the words `solver`, `preliminary`, `90 minutes`, and "stale while ... paused", and quotes the current bullet verbatim. Risk: the file lives under `.planning/`, which no existing test reads (the Phase 5 text tests read `docs/data-science/decisions/`), and `.planning` commits are filtered out of a clean PR branch. If that matters to the user, also place a copy under `docs/data-science/decisions/` and test that copy; otherwise test the phase-directory file and accept that. (Open Question 5.)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| View returns the single newest run, label constant `'psse'` | Newest complete run per solver, label from `psse_run.solver` | 2026-11-16 original; 2026-11-18 PSS/E-only guard (Phase 3 D-03); this phase | Up to 8 rows; readers must filter on `solver` |
| `verify_solver_tag.sql` check 7 guards PSS/E-only | Behavioural per-solver check in `verify_exposure.sql` | this phase | Counts become 6, 7, 37 |

**Deprecated/outdated:**
- The Phase 3 guard and its proofs: replaced by D-01; the Phase 3 migration file stays as history.
- `docs/integration/rest-api.md` sentences "up to four rows", "Every row today is `psse`": replaced.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Rewriting the `solver` column comment and the view comment (two texts that become false) is acceptable under D-01's "keeps ... the column comments" | Pattern 1 | Low: the alternative leaves a comment stating "pandapower rows arrive in a later release" on a live view; needs a yes from the user (Open Question 2) |
| A2 | Retiring `verify_solver_tag.sql` check 7 (6 checks) and adding one `verify_exposure.sql` check (37) is the right split of the counts | Impact inventory | Low: the owner may prefer to keep seven checks in `verify_solver_tag.sql`; the check SQL moves unchanged |
| A3 | The migration file name `20261126200000_latest_grid_study_per_solver.sql` | Recommended Project Structure | None: discretionary; only the ordering and the allow-list suffix depend on it |
| A4 | Aaron Phan will commit the hand-over blocks, and the apply date can be filled in after the live apply | DEF-01 | VIEW-03 stays open until he does; D-04 already says so |
| A5 | Supabase's production PostgreSQL accepts `select distinct on` in a view CTE and `create or replace view` with an unchanged first-column type | Pattern 1 | Very low: `latest_rating` already runs live with `distinct on`, and the Phase 3 `create or replace` of this same view applied live on 2026-11-25; the exact new statement was proved only on local PostgreSQL 17.12 |

## Open Questions (RESOLVED)

All five were settled on 2026-11-26 as defaults recorded in `06-CONTEXT.md` D-05 to D-08 (applied by the orchestrator from the recommendations below; the user can change them).

1. **Retire check 7 or keep seven checks in `verify_solver_tag.sql`?**
   - What we know: check 7 matches `solver = 'psse'` in the view definition and is false after the new migration; D-03 says to update any check that names it.
   - What's unclear: whether the owner wants the new behavioural check in `verify_exposure.sql` (recommended, 37) or in `verify_solver_tag.sql` (7 / 7 / 36).
   - Recommendation: retire check 7, add the check to `verify_exposure.sql`, state 6 / 7 / 37 in the plan and in the owner's step.
   - **RESOLVED (2026-11-26):** D-05 (retire check 7; new check in `verify_exposure.sql`; counts 6 / 7 / 37).

2. **May the two comments that would become false be edited?**
   - What we know: D-01 lists "the column comments" among things kept; the `solver` comment says "pandapower rows arrive in a later release", the view comment says "one row per city" and "only PSS/E runs ... are shown".
   - Recommendation: edit exactly those two (view comment and `solver` column comment); pin the other 19 column comments word for word against the Phase 3 file, as `test_text_the_guarded_view_is_the_old_view_plus_one_predicate` does for 20.
   - **RESOLVED (2026-11-26):** D-06 (edit only the view comment and the `solver` column comment).

3. **Include chapter 10 of `docs/DASHBOARD-REQUIREMENTS.md` in the hand-over?**
   - What we know: D-04 names REQUIREMENTS.md and STATE.md; chapter 10 is stated to win on disagreement and holds the "pandapower will add rows later" and "every row is stale today" sentences.
   - Recommendation: include it as Block C; without it the dashboard's own requirements contradict each other after the apply.
   - **RESOLVED (2026-11-26):** D-07 (chapter 10 is Block C of the hand-over).

4. **Which date goes in the replacement text?**
   - What we know: the live apply and the soak have not happened.
   - Recommendation: placeholder for the apply date in the file; the owner (or Aaron) fills it in at hand-over.
   - **RESOLVED (2026-11-26):** D-08 (apply date stays a placeholder until the live apply).

5. **Where should the text test read the DEF-01 file from?**
   - What we know: the file lives in the phase directory (D-04); no existing test reads `.planning/`.
   - Recommendation: test the phase-directory file; add a copy under `docs/data-science/decisions/` only if the user wants the test to survive a `.planning`-filtered PR branch.
   - **RESOLVED (2026-11-26):** D-08 (the tracked copy lives under `docs/data-science/decisions/`; the phase directory holds a pointer).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL server binaries (`initdb`, `pg_ctl`) | Database tier of every test here | yes | 17.12 at `/c/Program Files/PostgreSQL/17/bin` | none; tests fail under `PSSE_REQUIRE_PG=1` rather than skip |
| `.venv/Scripts/python.exe` with psycopg, pytest | Tests | yes | Python 3.12.10, psycopg 3.3.6, pytest 9.0.3 | none |
| `git` and `origin/feature/dashboard` ref | DEF-01 verbatim text | yes | ref current as of 2026-11-26 | none |
| Live Supabase project | Live apply and live checks | not used | — | The owner's step (D-02); this phase never connects |

**Missing dependencies with no fallback:** none for the build and the local proofs.

## Validation Architecture

`.planning/config.json` holds no `workflow.nyquist_validation` key, so this section is included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 on Python 3.12.10 [VERIFIED] |
| Config file | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Quick run command (text tier, no database; database tests skip) | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -p no:cacheprovider -q backend/tests/<file>` |
| Database tier prefix (Git Bash) | `PATH="/c/Program Files/PostgreSQL/17/bin:$PATH" DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1` |
| Full phase set | the prefix above, then `.venv/Scripts/python.exe -m pytest -p no:cacheprovider -q backend/tests/grid_study_expose_test.py backend/tests/solver_tag_owner_check_test.py backend/tests/expose_migration_test.py backend/tests/psse_results_migration_test.py backend/tests/day_ahead_expose_test.py backend/tests/solver_tag_migration_test.py <new test file>` |

Measured baselines before any change [VERIFIED: runs this session]: `grid_study_expose_test.py` plus `solver_tag_owner_check_test.py`: 27 passed in 58.7 s. `expose_migration_test.py`, `psse_results_migration_test.py`, `day_ahead_expose_test.py`, `solver_tag_migration_test.py`: 99 passed, 4 failed in 128.3 s. Whole set about 3.5 minutes, each file builds its own throwaway cluster.

Known Windows-only failures in these files today (all four also named by the orchestrator, none caused by this phase): `expose_migration_test.py::test_phase6_migrations_are_unchanged_after_apply`, `psse_results_migration_test.py::test_psse_migration_is_unchanged_after_apply`, `day_ahead_expose_test.py::test_expose_migration_is_unchanged_after_apply` (CRLF byte-hash), and `expose_migration_test.py::test_is_provisional_reads_the_real_labels`. `pandapower_cli_test` and `pandapower_ingest_test` also fail on Windows and are outside this phase's files. The phase gate is "no failure beyond these".

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| VIEW-01 | View returns the newest complete run per solver: 8 rows with both, 4 with one, 0 with none; a newer failed run is skipped; a tie in one hour goes to the later finish | database | `pytest backend/tests/grid_study_per_solver_test.py -x` (prefix above) | no, Wave 0 |
| VIEW-01 | 20 columns equal `contract.COLUMNS`, none in `FORBIDDEN`, order, ACL, `security_invoker=false`, owner, the 19 unchanged comments word for word, new `solver` and view comments | text + database | same | no, Wave 0 |
| VIEW-01 | Stale flag per solver: fresh pandapower rows false, old PSS/E rows true in one response; 90 minute boundary unchanged | database | same | no, Wave 0 |
| VIEW-01 | New migration text: only `create or replace view`, revoke, grant, comments; no `alter`, `drop`, `insert`, `update`, `delete`; no grant on a `psse_` table; no `r.solver = 'psse'`; no constant `'psse'::text`; re-apply twice leaves the same definition and ACL | text + database | same | no, Wave 0 |
| VIEW-02 | As `anon` and `authenticated` with both solvers' rows present: the view reads, the four tables raise `InsufficientPrivilege`, writes through the view are refused | database | same (or the existing `grid_study_expose_test.py`, extended) | partly (existing test needs both solvers seeded) |
| VIEW-02 | `verify_exposure.sql` returns 37 rows, all ok, on the full chain with and without runs; new check false for the Phase 3 PSS/E-only view with both solvers present, and for a view that hides a city | database | `pytest backend/tests/expose_migration_test.py backend/tests/psse_results_migration_test.py` | exists; constants and sabotage cases to edit |
| VIEW-02 | `verify_solver_tag.sql` returns 6 pinned names, all ok after the chain; each can fail once | text + database | `pytest backend/tests/solver_tag_owner_check_test.py` | exists; edits listed in the Impact inventory |
| VIEW-02 | Migration ordering allow-lists include the new file | text | `pytest backend/tests/psse_results_migration_test.py backend/tests/day_ahead_expose_test.py -k "sort or only"` | exists; edits listed |
| VIEW-03 | Hand-over file names `latest_grid_study`, every `contract.COLUMNS` name, `solver`, `preliminary`, `90 minutes`, "paused", and quotes the current DEF-01 text verbatim | text | `pytest backend/tests/grid_study_def01_text_test.py -x` | no, Wave 0 |
| VIEW-03 | The dashboard owner has committed the text on `origin/feature/dashboard` | manual, `human_needed` | `MSYS_NO_PATHCONV=1 git fetch origin feature/dashboard`, then `git show "origin/feature/dashboard:.planning/workstreams/software-dashboard/REQUIREMENTS.md" \| grep -n solver` | n/a |
| D-02 | Live apply and the owner's three read-only checks (6, 7, 37 ok) | manual, `human_needed` | owner runs the three files in the Supabase SQL editor after `supabase db push --db-url ...` | n/a |

### Sampling Rate
- **Per task commit:** the test file or files the task edits, with the database prefix when the task touches SQL (about 30 to 60 s per file).
- **Per wave merge:** the full phase set above (about 3.5 minutes).
- **Phase gate:** full phase set with only the four named Windows failures, plus `pandapower_hourly_runbook_test.py` and `rest_api_doc_test.py` text tests green (the doc edit), before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/grid_study_per_solver_test.py` (or extend `grid_study_expose_test.py`) — VIEW-01, VIEW-02 database and text proofs for the new migration
- [ ] `backend/tests/grid_study_def01_text_test.py` — VIEW-03 text pin of the hand-over file
- [ ] A seeding helper for one run per solver (reuse `solver_tag_owner_check_test._complete_run` shape; do not import across test modules, copy the six lines)
- Framework install: none.

## Security Domain

`security_enforcement` is not set in `.planning/config.json`, so it is treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | The dashboard uses the publishable key; no credential is added or changed (the migration header forbids one) |
| V3 Session Management | no | Stateless REST reads |
| V4 Access Control | yes | The public roles hold SELECT on the view only; the four `psse_*` tables keep their revoke and RLS; `security_invoker = false` is the deliberate owner-rights design (Supabase lint 0010 accepted for this view only); verified by `psse_tables_not_readable_by_public_roles` and the database tests |
| V5 Input Validation | no | The view takes no input; it is not auto-updatable and writes are refused by privilege |
| V6 Cryptography | no | None |
| V8 Data Protection | yes | A fixed column whitelist (`contract.COLUMNS`, 20 names) with a forbidden list (`contract.FORBIDDEN`): no run id, hash, case, bus, error text or details field |
| V14 Configuration | yes | Additive idempotent migration, never editing an applied one; live apply gated on the Phase 5 soak (D-02) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| An unverified pandapower figure readable by the dashboard before the soak passes | Information disclosure (integrity of meaning) | D-02: live apply only after the soak; the repository change is inert until the owner pushes it |
| A pandapower result labelled as PSS/E | Spoofing / Tampering | The label is the stored `psse_run.solver`, tied to the run-id prefix by `psse_run_solver_run_id_ck`; the constant `'psse'` is removed |
| The owner-rights view returns more than intended | Information disclosure | Whitelist test on the column list, a `FORBIDDEN` assertion on returned rows, and the live `latest_grid_study_matches_the_contract` check (20 columns, last two `age_minutes`, `is_stale`) |
| Write through the view | Tampering | Privilege: only SELECT is granted; `has_table_privilege('anon', ..., 'insert, update, delete')` asserted false; checker `anon_authenticated_hold_no_write_or_column_privilege_in_public` |
| Replacing the view drops the revoke/grant or switches it to invoker rights | Elevation / Denial | The migration reissues revoke and grant and states `with (security_invoker = false)`; tests assert ACL, `reloptions` and owner before and after |
| Re-applying the Phase 3 file alone restores the PSS/E-only view | Tampering (regression) | Header warning; the chain re-apply tests re-apply in name order |
| Secrets or private data in the new files | Information disclosure | Header-only comments, no connection string; nothing under `data/private/` was read or is referenced |

## Sources

### Primary (HIGH confidence)
- `supabase/migrations/20261118200000_psse_run_solver_tag.sql` (Read in full): current view statement, comments, header conventions
- `supabase/migrations/20261116200000_expose_latest_grid_study.sql` (Read in full): original view and owner-rights rationale
- `supabase/migrations/20261109233541_psse_results.sql` lines 30-100 (Read): `psse_run`, `psse_dispatched_capacity` DDL, keys, foreign key
- `supabase/ops/verify_exposure.sql`, `supabase/ops/verify_solver_tag.sql` (Read in full)
- `backend/grid_study_contract.py`, `backend/tests/grid_study_expose_test.py`, `solver_tag_owner_check_test.py`, `expose_migration_test.py`, `psse_results_migration_test.py` (lines 1-290), `day_ahead_expose_test.py` (lines 100-180), `solver_tag_migration_test.py` (parts), `local_pg.py`, `psse_local_pg.py` (Read)
- `docs/integration/rest-api.md` lines 20-35, 130-140, 236-330 (Read)
- `git show "origin/feature/dashboard:<path>"` for `REQUIREMENTS.md`, `STATE.md`, and grep of `docs/DASHBOARD-REQUIREMENTS.md`, `COLUMN-GUIDE.md`, `ROADMAP.md`, `grounding/*`; `git grep` of the branch for `latest_grid_study`
- Probes on a throwaway local PostgreSQL 17.12 (scripts kept in the session scratchpad, not in the repository): the replacement view, and the new check inside a copy of `verify_exposure.sql`
- Test runs this session: baselines quoted in Validation Architecture

### Secondary (MEDIUM confidence)
- `.planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-VERIFICATION.md` and `03-RESEARCH.md` (live check of 2026-11-25: 36 of 36, view unchanged)

### Tertiary (LOW confidence)
- none

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, nothing new; versions read from the environment
- Architecture (the view statement): HIGH, applied and exercised on PostgreSQL 17.12; production Supabase behaviour is the Phase 3 precedent (same `create or replace` applied live)
- Impact inventory: HIGH for the files read; the repository-wide greps cover `backend/`, `docs/`, `supabase/`, `.github/`
- DEF-01: HIGH for the current wording (read from the branch ref); the replacement wording is a draft
- Pitfalls: HIGH

**Research date:** 2026-11-26
**Valid until:** 2026-12-26 for repository facts; re-read `origin/feature/dashboard` before the hand-over because Aaron may edit those files meanwhile
