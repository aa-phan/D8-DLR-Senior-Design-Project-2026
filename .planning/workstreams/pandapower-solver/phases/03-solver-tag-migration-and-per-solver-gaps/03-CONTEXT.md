# Phase 3: Solver Tag, Migration and Per-Solver Gaps - Context

**Gathered:** 2026-11-18
**Status:** Ready for planning

<domain>
## Phase Boundary

One additive migration makes the four `psse_*` result tables hold PSS/E and pandapower runs side by side, every run carries its solver, the existing writer stamps it, and the gap check reports missing hours per solver. Requirements DB-01, DB-02, DB-03. Runs in parallel with Phase 2; only a closing tagged-write rehearsal with the pandapower engine needs Phase 2 (which is built). Applying the migration to the live project is the owner's step, not this phase's.

</domain>

<decisions>
## Implementation Decisions

Gathered under the owner's instruction on 2026-11-18 to do whatever can be done without the PSS/E laptop; recommendations were applied as defaults, and the owner can change any of them.

### Migration
- **D-01:** One new migration file dated after `20261116200000_expose_latest_grid_study.sql`. It adds `solver text not null default 'psse'` (check: `psse` or `pandapower`) and `solver_version text` (nullable) to `public.psse_run`, and replaces the run-id check so a `pp-` id is accepted only with `solver = 'pandapower'` and a `psse-` id only with `solver = 'psse'`. The applied v1 migration (`20261109233541_psse_results.sql`) is never edited; the run-id check is dropped and re-added by the new file. Existing runs stay valid and read as `psse`. — **Reversibility:** one-way — once the owner applies it live, the column and constraint exist in production; undoing needs a further migration.
- **D-02:** Idempotent, like earlier migrations in this repo, and it adds no role or credential. The writer role `dlr_psse_writer` keeps its existing privileges; check whether its INSERT grant needs the new columns.

### Public view guard
- **D-03:** Because `public.latest_grid_study` selects the newest run with no solver filter and labels it the constant `'psse'`, the new migration also replaces that view so it reads only `solver = 'psse'` runs (same 20 columns, same order, column list stays one-way). This stops a pandapower row from being shown to the dashboard as PSS/E before Phase 6 replaces the view with a per-solver one. — **Reversibility:** costly — it edits an exposed, owner-applied view that the dashboard reads. **Owner to confirm** (this touches a live, public-facing surface the owner approved on 2026-11-16).

### Writer and job
- **D-04:** The run record gains a `solver` field (default `psse`, so the PSS/E job and its tests are unchanged) and `solver_version`. The all-or-nothing writer stamps both. A pandapower run can never be stored as `psse`: the writer and the database constraint both refuse a mismatch. This phase edits the files Phase 2 deliberately left alone (`contract.py`, `run_record.py`, `job.py`, `constants.py`, `gaps.py`, `writer.py` as needed); `psse_job` stays stdlib-only and Python 3.7-safe, and the import-boundary tests must keep passing.
- **D-05:** The pandapower engine's `psse_version=None` plus `solver_version` hand-off from Phase 2 research is used; the closing rehearsal writes a tagged four-city pandapower study through the real writer into a throwaway database.

### Gap check
- **D-06:** Gaps are computed per solver: a PSS/E run in an hour never hides a missing pandapower hour. PSS/E gaps while its machine is offline are listed separately from pandapower gaps. Pure Python, covered by tests that run without a database.

### Verification boundaries
- **D-07:** No Postgres is installed on this machine, so the database proofs (success criteria 1 and the writer's refusal against the real constraint) are written to run on a throwaway local database and skip cleanly here; the SUMMARY must say plainly that they were only skipped and give the command to run them on the owner's Mac. The pure-Python parts (gap check, run-record and writer logic against a fake connection) run here. Success criterion 4 (read-only check after the owner applies the migration live) is an owner step: the phase prepares a read-only check script and does not touch the live project.

### Claude's Discretion
Migration file name and time-of-day suffix, helper names, and test layout, as long as the decisions above hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/workstreams/pandapower-solver/ROADMAP.md` — Phase 3 goal and success criteria
- `.planning/workstreams/pandapower-solver/REQUIREMENTS.md` — DB-01 to DB-03
- `.planning/workstreams/pandapower-solver/STATE.md` — workstream decisions, including the `latest_grid_study` view note
- `.planning/workstreams/pandapower-solver/phases/02-pandapowerapi-and-study-engine/02-RESEARCH.md` and `02-04-SUMMARY.md` — the `solver_version` / `psse_version=None` hand-off and the dispatch-row `details` settings record
- `supabase/migrations/20261109233541_psse_results.sql` — the applied v1 schema (never edit)
- `supabase/migrations/20261116200000_expose_latest_grid_study.sql` — the live public view to guard
- `backend/psse_job/` — `contract.py`, `run_record.py`, `job.py`, `constants.py`, `gaps.py`, `writer.py`
- `backend/grid_study_contract.py` — Python twin of the view's column list
- `backend/tests/local_pg.py` and `backend/tests/psse_study_job_test.py` — the throwaway-Postgres harness and its skip rules
- `docs/data-science/` verify_exposure checks named in VIEW-02 (Phase 6 updates them; this phase must not break them)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/tests/local_pg.py`: autostart throwaway Postgres for tests (skips without `DLR_TEST_PG_AUTOSTART=1`).
- `backend/psse_job/gaps.py`: the existing PSS/E-only gap check to extend per solver.

### Established Patterns
- Additive, idempotent migrations that never edit an applied file; the owner applies them with `supabase db push`.
- Run-id format is `psse-<UTC stamp>-<8 hex>`; the new `pp-` prefix follows the same shape.

### Integration Points
- `run_record` and the writer are the single path into `psse_run`; Phase 5's workflow will call the engine and that writer.

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches.

</specifics>

<deferred>
## Deferred Ideas

- The per-solver `latest_grid_study` replacement, exposure-check updates and the DEF-01 text stay in Phase 6.
- The retention rule for permanent rows (OPS-04) stays in Phase 5.

</deferred>

---

*Phase: 3-Solver Tag, Migration and Per-Solver Gaps*
*Context gathered: 2026-11-18*
