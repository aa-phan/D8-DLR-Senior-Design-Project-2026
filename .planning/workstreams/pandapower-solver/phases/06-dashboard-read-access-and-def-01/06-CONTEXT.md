# Phase 6: Dashboard Read Access and DEF-01 - Context

**Gathered:** 2026-11-26
**Status:** Ready for planning

<domain>
## Phase Boundary

The dashboard's key reads the newest complete result for each city and each solver through one read-only view and nothing else, the four result tables stay private, the exposure checks match, and the dashboard requirements' DEF-01 section says the blockers are cleared. Requirements VIEW-01, VIEW-02, VIEW-03. Depends on Phase 3 (the solver column, applied live and checked 2026-11-25) and Phase 5 (verified, live results). Built and tested on a throwaway local database here; the live apply is the owner's step (D-02).

</domain>

<decisions>
## Implementation Decisions

Gathered 2026-11-26. The user had no view of their own and asked for recommendations; both choices below were put to them with a recommendation and approved as recommended.

### The view (VIEW-01, VIEW-02)
- **D-01:** Replace `public.latest_grid_study` in place; do not add a second view. A new additive migration, dated after `20261118200000_psse_run_solver_tag.sql`, replaces the view with `create or replace`. It keeps the name, the 20 columns and their order (the contract the owner approved on 2026-11-16, `solver` already first, a column is only appended), `with (security_invoker = false)`, the revoke and grant, the column comments, and the 90 minute stale rule (`is_stale` when `slot_time` is more than 90 minutes old). It keeps the "complete run" rule (outcome `ok` or `fallback`). It drops the `r.solver = 'psse'` filter that Phase 3 (D-03) added and the constant `'psse'` label, and instead takes the newest complete run per solver, so the view returns one row per city per solver (at most 8 rows). The Phase 3 view comment said the per-solver view would replace it; this is that replacement. — **Reversibility:** costly — it edits an exposed, owner-applied view. It is idempotent and a later migration can restore the PSS/E-only filter.
- **D-02:** The migration is applied to the live project only after the Phase 5 soak passes (roadmap: until agreement and the soak pass, no unverified figure may be readable). Aaron applies it, then runs the read-only exposure checks. Until then the phase builds and tests it on a throwaway local database only, and the verification stays `human_needed` for the live apply, the same way Phase 3 was.
- **D-03:** A whitelist test compares the view's column list to the 20 approved columns (no run id, hash, bus number or detail field). With the dashboard's key, reading any of the four result tables is refused. `supabase/ops/verify_exposure.sql` and its tests are updated for the per-solver view; the Phase 3 tests and checks that pin the PSS/E-only behaviour (the view guard tests in `grid_study_expose_test.py` and `solver_tag_owner_check_test.py`, and any `verify_solver_tag.sql` check that names it) must be found and updated rather than left failing. The committed `verify_exposure.sql` has 36 checks today (owner's live run: 36 of 36, 2026-11-25); the planner states the new count.

### DEF-01 (VIEW-03)
- **D-04:** The DEF-01 section is not on this branch. It lives in `.planning/workstreams/software-dashboard/REQUIREMENTS.md` (and a STATE.md line of 2026-11-16) on branch `origin/feature/dashboard`, the software-dashboard workstream whose author is Aaron Phan. This phase does not edit that branch. It produces the exact replacement DEF-01 text as a file in this phase directory for the dashboard owner to commit there. The text must say: the blockers are cleared; the view is `latest_grid_study`; its columns by name; it returns one row per city per solver, so a reader must filter on `solver`; values are preliminary (public 39-bus case scaled per city, not a utility network); a PSS/E row is stale while that job is paused (90 minute rule). VIEW-03 is complete only when the dashboard owner has committed it.

### Claude's Discretion
Migration file name and time-of-day suffix, how the per-solver "newest run" is expressed in SQL, test layout and fixtures, and how the replacement DEF-01 text file is named, as long as the decisions above hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/workstreams/pandapower-solver/ROADMAP.md` — Phase 6 goal and success criteria
- `.planning/workstreams/pandapower-solver/REQUIREMENTS.md` — VIEW-01 to VIEW-03
- `supabase/migrations/20261118200000_psse_run_solver_tag.sql` — the current view statement (psse-only filter), column list and comments, `psse_dispatched_capacity` join
- `supabase/migrations/20261116200000_expose_latest_grid_study.sql` — the original view and its owner approval (never edit an applied migration)
- `supabase/ops/verify_exposure.sql`, `supabase/ops/verify_solver_tag.sql`, `supabase/ops/verify_psse_results.sql`
- `backend/grid_study_contract.py` — Python twin of the view's column list
- `backend/tests/grid_study_expose_test.py`, `backend/tests/solver_tag_owner_check_test.py`, `backend/tests/expose_migration_test.py` — tests that pin the view and the exposure checks
- `backend/tests/psse_local_pg.py`, `backend/tests/local_pg.py` — the throwaway-Postgres harness (Git Bash: `PATH="/c/Program Files/PostgreSQL/17/bin:$PATH" DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1`)
- `.planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-VERIFICATION.md` — how the view guard was proved and the owner's live check of 2026-11-25
- `origin/feature/dashboard`, `.planning/workstreams/software-dashboard/REQUIREMENTS.md` (DEF-01) and `STATE.md` — read with `git show "origin/feature/dashboard:<path>"` (set `MSYS_NO_PATHCONV=1` in Git Bash)

</canonical_refs>

<specifics>
## Open Facts To Check At Planning

- Whether `psse_dispatched_capacity` and the other result views carry `solver`, or the join must go through `psse_run.solver`.
- The dashboard does not read `latest_grid_study` yet (DEF-01 is deferred in its roadmap), so one row per city per solver breaks no current consumer; the replacement DEF-01 text is what tells the future reader to filter.
- The Phase 3 PSS/E-only view proofs (`test_db_a_newer_pandapower_run_never_changes_the_view` and the "with only pandapower runs the view is empty" case) assert the behaviour this phase removes; they change to assert per-solver rows.

</specifics>

<deferred>
## Deferred Ideas

- Pruning or archiving old result rows (Phase 5 D-01 review trigger).
- A per-solver freshness alarm (OPS-06, v2).
- Dashboard-side work to read the view (the software-dashboard workstream owns it).

</deferred>
