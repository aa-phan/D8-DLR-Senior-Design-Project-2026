# Phase 5: Hourly Workflow, Dry Run and Live Soak - Context

**Gathered:** 2026-11-25
**Status:** Ready for planning

<domain>
## Phase Boundary

The pandapower job runs every hour in GitHub Actions with no laptop involved: first as a dry run that writes nothing, then, after the gate has passed, writing live results for 24 consecutive hourly slots without anything private reaching the public log. Requirements OPS-01 to OPS-05. Depends on Phase 2 (engine), Phase 3 (migration and tagged writer; the migration is applied live and checked as of 2026-11-25) and Phase 4 (agreement). The first live write also requires NET-03 (Phase 1) and AGR-02 (Phase 4) to have passed.

</domain>

<decisions>
## Implementation Decisions

Gathered 2026-11-25. The user did not have a view on the four open choices and asked for recommendations; each recommendation below was approved as written ("go with those"). The owner can change any of them.

### Retention (OPS-04)
- **D-01:** Keep every result row; no pruning in this phase. The hourly job adds about 24 run row sets a day (one run row plus its dispatch and margin rows), a few hundred rows a day, small for the Supabase project. The writer role `dlr_psse_writer` has no DELETE, so pruning would need the owner's admin login anyway. The written decision (a short document in the phase directory, before the first live write) states this and names a review trigger: revisit if the result tables pass 100,000 rows or the project nears its size limit. — **Reversibility:** easy — a later decision can add pruning or archiving; keeping rows loses nothing.

### Dry run to live switch (OPS-03)
- **D-02:** The workflow runs as a dry run (no writes) unless a GitHub repository variable, working name `PANDAPOWER_LIVE`, is set to `true`. The owner (Aaron owns the repo secrets and variables, the user believes) sets it only after NET-03 and AGR-02 have passed; a dated line in the repo records who decided and when (the recorded owner decision in roadmap success criterion 3). Default when the variable is absent or anything but `true` is dry run.
- **D-03:** Independently of the variable, the job refuses a live write when `engine.is_placeholder(backend)` is true, so a mistaken flip cannot store figures from the placeholder mapping. A dry run records that it wrote nothing; a test asserts the four result tables are unchanged after one. — **Reversibility:** easy — the variable can be turned off at any time; rows written while live stay (see D-01).

### The 24 hour soak (OPS-05)
- **D-04:** Pass means 24 consecutive hourly slots, each with a pandapower result, as shown by the per-solver gap check. Any missed hour restarts the clock. The workflow calls `gaps.run_by_solver(...)` with `expected=(engine.SOLVER,)` so an absent pandapower solver is reported, and passes `solver=engine.SOLVER` to `job.run_once` (a run started with the default tag is stored as a failed `psse` run with no figures; see `03-VERIFICATION.md` F-2, F-5). The strict rule matches the roadmap's word "consecutive" and is the simplest to state in the report.

### Public log leak guard (OPS-02)
- **D-05:** Two layers. The job prints only counts and statuses, never a secret, bus number or study value (GitHub's own secret masking is an extra layer, not the plan). A test runs the job with planted fake identifiers and scans the captured log for them, the same pattern as the Phase 4 replay leak test (`04-04`). The private mapping is written only to the runner's temporary folder.

### Workflow shape (fixed by the roadmap and the existing pattern; not re-discussed)
- **D-06:** Follow `.github/workflows/dlr_live.yml`: `workflow_dispatch` poked by cron-job.org (no GitHub scheduler), at :20 UTC, `production` environment, main-only `if`, its own concurrency group, timeout under 30 minutes (the roadmap says under one hour; the existing workflow uses 30). The private network comes from a GitHub secret (earlier decision D-06 of the pandapower workstream: 25,191 bytes against the 48 KB limit). The writer connection and ratings read settings are GitHub secrets.

### Claude's Discretion
Workflow file name, the exact variable and group names, log wording (counts only), test layout, and how the retention document is titled, as long as the decisions above hold.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

- `.planning/workstreams/pandapower-solver/ROADMAP.md` — Phase 5 goal and success criteria
- `.planning/workstreams/pandapower-solver/REQUIREMENTS.md` — OPS-01 to OPS-05 (OPS-06 is deferred)
- `.planning/workstreams/pandapower-solver/phases/03-solver-tag-migration-and-per-solver-gaps/03-VERIFICATION.md` — findings F-2, F-3, F-5 (default-tag failed run, `run_by_solver` has no caller, `expected=`) and the live check of 2026-11-25
- `.planning/workstreams/pandapower-solver/phases/04-replay-and-agreement-check/` — the leak test pattern and the AGR-02 result that gates live writes
- `.github/workflows/dlr_live.yml` — the pattern to copy
- `backend/psse_job/` (`job.py`, `gaps.py`, `writer.py`) and `backend/pandapower_job/` (`engine.py`, `api.py`)
- `supabase/ops/verify_solver_tag.sql` — read-only checks, run live on 2026-11-25

</canonical_refs>

<specifics>
## Open Facts To Check At Planning

- The PSS/E laptop hourly task is `DLR-PSSE-Hourly` at :15; the old plan said it was stopped 2026-11-12. Check its state before the soak so the :15 and :20 jobs do not confuse the per-solver gap check.
- Phase 3 live check notes still open with the owner (37 versus 36 exposure checks, `solver_version` counts, dashboard page); none blocks planning.
- NET-03 (Phase 1) and AGR-02 (Phase 4) status is the live-write gate; confirm both are recorded passed before the owner flips `PANDAPOWER_LIVE`.

</specifics>

<deferred>
## Deferred Ideas

- OPS-06, an external freshness alarm if pandapower results stop arriving (v2).
- Pruning or archiving old result rows (revisit under D-01's trigger).
- Per-solver dashboard view: Phase 6.

</deferred>
