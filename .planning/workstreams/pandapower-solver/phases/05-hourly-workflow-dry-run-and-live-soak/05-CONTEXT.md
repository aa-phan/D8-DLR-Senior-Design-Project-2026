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
- **D-01:** Keep every result row; no pruning in this phase. **Corrected 2026-11-25 after research:** the first version of this decision said "a few hundred rows a day", which was wrong. Only violations are written, and the 19 recorded runs hold about 214 rows each (about 205 contingency rows, capped at 5,000 per run, plus about 8 dispatch and margin rows), so 24 runs a day is about 5,100 rows a day. The user re-approved keeping every row on the corrected figure. The writer role `dlr_psse_writer` has no DELETE, so pruning would need the owner's admin login anyway. The written decision (a short document in the phase directory, before the first live write) states the true rate and replaces the 100,000-row review trigger (reached in about 20 days) with a database size check: revisit when the result tables' size, read by the owner, nears a limit the owner names. — **Reversibility:** easy — a later decision can add pruning or archiving; keeping rows loses nothing.

### Dry run to live switch (OPS-03)
- **D-02:** The workflow runs as a dry run (no writes) unless a GitHub repository variable, working name `PANDAPOWER_LIVE`, is set to `true`. The owner (Aaron owns the repo secrets and variables, the user believes) sets it only after NET-03 and AGR-02 have passed; a dated line in the repo records who decided and when (the recorded owner decision in roadmap success criterion 3). Default when the variable is absent or anything but `true` is dry run.
- **D-03:** Independently of the variable, the job refuses a live write when `engine.is_placeholder(backend)` is true, so a mistaken flip cannot store figures from the placeholder mapping. A dry run records that it wrote nothing; a test asserts the four result tables are unchanged after one. — **Reversibility:** easy — the variable can be turned off at any time; rows written while live stay (see D-01).

### The 24 hour soak (OPS-05)
- **D-04:** Pass means 24 consecutive hourly slots, each with a pandapower result, as shown by the per-solver gap check. Any missed hour restarts the clock. The workflow calls `gaps.run_by_solver(...)` with `expected=(engine.SOLVER,)` so an absent pandapower solver is reported, and passes `solver=engine.SOLVER` to `job.run_once` (a run started with the default tag is stored as a failed `psse` run with no figures; see `03-VERIFICATION.md` F-2, F-5). The strict rule matches the roadmap's word "consecutive" and is the simplest to state in the report.

### Public log leak guard (OPS-02)
- **D-05:** Two layers. The job prints only counts and statuses, never a secret, bus number or study value (GitHub's own secret masking is an extra layer, not the plan). A test runs the job with planted fake identifiers and scans the captured log for them, the same pattern as the Phase 4 replay leak test (`04-04`). The private mapping is written only to the runner's temporary folder.

### Workflow shape (fixed by the roadmap and the existing pattern; not re-discussed)
- **D-06:** Follow `.github/workflows/dlr_live.yml`: `workflow_dispatch` poked by cron-job.org (no GitHub scheduler), at :20 UTC, `production` environment, main-only `if`, its own concurrency group, timeout under 30 minutes (the roadmap says under one hour; the existing workflow uses 30). The private network comes from a GitHub secret (earlier decision D-06 of the pandapower workstream: 25,191 bytes against the 48 KB limit). The writer connection and ratings read settings are GitHub secrets.

### Decisions added after research (2026-11-25; the user approved the researcher's recommendations as written)
Source: `05-RESEARCH.md`, open questions 1 to 8.
- **D-07 (merge):** The user will NOT merge anything to `main`. Aaron will pull the branch into `main` when everything is finished. Consequence: GitHub only dispatches a workflow file that is on the default branch and the job is main-only, so nothing can run on GitHub, not even a dry run, until Aaron merges. This phase builds and tests everything locally (workflow file, runner, dry path, leak guard, soak function, retention document, owner `bundle` command, runbook). Every step that needs GitHub or the owner (merge, secrets, the `PANDAPOWER_LIVE` variable, the cron-job.org job, first manual dispatch, dry-run hours, the flip, the 24 hour soak) is written as an owner checkpoint with the exact commands, and the phase verifies as `human_needed` the same way Phase 3 did. Create the cron-job.org job only after one manual dispatch succeeds (cron-job.org disables a job after 25 straight failures). — **Reversibility:** easy.
- **D-08 (recorded settings):** The runner needs a fifth private input, the recorded PSE-02 settings, but the check folder's `report.json` also holds NET-03 detail that Phase 1 D-08 forbids in CI. An owner `bundle` command prints counts only and produces four single-line base64 files (network, mapping, settings keys, scaling detail), stored as base64 secrets in the `production` environment. Plain base64 of the 25,191 byte network is 33,588 characters, under the 48 KB limit.
- **D-09 (gap step):** The hourly gap step reports but does not fail the run, except for the serious exit code 6. The 24 slot soak is a new pure function (trailing count of consecutive slots, tested against an independent oracle), checked once by the owner at the end with `since=<first live slot>`; it first reports on the 25th run.
- **D-10 (credential in dry run):** A dry run never holds the writer credential in the study step: no connect parameter, no writer import. A separate read-only step always gets the credential (it also proves the credential before the flip).
- **D-11 (before the flip):** At least 3 green dry runs, one real downloaded Actions log scanned with `private_leak_scan`, and a comparison of the Linux runner's counts with the owner machine's.
- **D-12 (fallback):** Fallback runs count toward the soak; the soak line prints the count of fallback slots.
- **D-13 (variable level):** `PANDAPOWER_LIVE` is a repository variable only, not per environment. `workflow_dispatch` has no inputs, so a dispatcher cannot flip live mode.
- **D-14 (log discipline):** The runner redirects file descriptors 1 and 2, disables logging and warnings, and prints only through a closed-vocabulary printer (as `replay_cli._Printer` does). No printed line starts with `::`, and the run id is not printed. Reason: `job.run_once` logs stored error text and a mapping error can carry a bus key.

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
