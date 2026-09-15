---
phase: 10-fallback-wiring-documentation-ratification
plan: 03
subsystem: data-science
tags: [documentation, ratification, weather-provider, tceq, nsrdb, synoptic, checkpoint]

# Dependency graph
requires:
  - phase: 10-fallback-wiring-documentation-ratification
    provides: "Plan 10-01's TCEQ-to-Synoptic fallback tracer and Plan 10-02's full-surface WX-06 fallback (grid path, four cities, exhaustion, schema integration) -- the implementation this plan records as ratified"
provides:
  - "docs/data-science/PRD.md §7.1 -- the ratified per-variable weather-provider composition, replacing the open three-way decision, naming all five shipped providers, their roles, modules, and provenance values, plus the fallback policy and its three deliberate non-triggers"
  - "docs/data-science/PRD.md §10 -- the NOAA-plus-NSRDB and solar-irradiance discrepancy rows corrected in the document's existing RESOLVED style"
  - "docs/data-science/decisions/data_provider.md -- ratified status line, an 'Adopted Composition' section (retitled from 'synthesis, not a final decision') naming the Synoptic fallback and its exclusions, a closing record of what was decided and which phase implemented each provider, and three corrected NREL developer-portal hostname occurrences"
  - "docs/data-science/specs/C4-weather-ingestion.md -- a Phase 10 additions (WX-06) paragraph, an updated five-provider-plus-fallback Status line, two new acceptance-criteria bullets, and a resolved Open Questions weather-provider entry"
affects: []

# Actuals (#2632)
actuals:
  tokens: 6800
  tasks: 1
  commits: 1

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "RESOLVED-row convention reused: PRD.md §10's pre-existing strikethrough-plus-RESOLVED-marker style for a corrected discrepancy row was reused for both stale rows this plan closed, rather than inventing a new convention or deleting the historical claim."
    - "Hostname-correction-without-repetition: when a verify gate asserts a stale literal string's count is zero, a corrective parenthetical must reference the old value descriptively (e.g. \"the previous developer-portal hostname\") rather than quoting the exact stale string, or the same grep that flags the uncorrected file also flags the correction's own explanatory text."

key-files:
  created: []
  modified:
    - docs/data-science/PRD.md
    - docs/data-science/decisions/data_provider.md
    - docs/data-science/specs/C4-weather-ingestion.md
    - ACKNOWLEDGEMENTS.md

key-decisions:
  - "Task 1's ratification decision was resolved in a prior session (human approved the composition and fallback policy exactly as documented in the plan's <interface_context>/<decision> text, \"approve, proceed exactly as stated\") -- this session did not re-present that decision, per explicit instruction from the coordinating orchestrator."
  - "Task 3's live-endpoint confirmation was NOT attempted: this isolated worktree's shell environment has neither SYNOPTIC_TOKEN nor the NREL credential pair set, and the sandbox denies direct access to the repository's .env file from a worktree-isolated agent. Per the task's own <how-to-verify> step 1 (\"If it is absent, stop and record the blocker rather than reporting a failed fallback\"), this is a recorded blocker, not a failed check or a self-approved checkpoint."
  - "SUMMARY status recorded as halted, not complete: Task 2 is fully committed and verified against every <verify> command in the plan. Task 3's own gate=\"blocking-human\" checkpoint requires a human (or a session with live-credential access) to perform the live confirmation and give explicit sign-off -- this project's own checkpoint convention excludes gate=\"blocking-human\" checkpoints from auto-approval in every execution mode, including when an instruction asks the executor to \"proceed through\" a task."

requirements-completed: [WX-08]

coverage:
  - id: D1
    description: "PRD.md §7.1 records the ratified per-variable provider composition (TCEQ, ASOS, NSRDB, Open-Meteo, Synoptic) with a resolution date, replacing the open three-way decision"
    requirement: "WX-08"
    verification:
      - kind: other
        ref: "grep -c 'unresolved'/'Decision needed'/'not actually settled' docs/data-science/PRD.md == 0; grep -ci for all five provider names >= 1 each"
        status: pass
    human_judgment: false
  - id: D2
    description: "PRD.md §10's NOAA-plus-NSRDB and solar-irradiance discrepancy rows are corrected in the existing RESOLVED style; corridor-discretization and ML-anomaly rows are untouched"
    requirement: "WX-08"
    verification:
      - kind: other
        ref: "grep -c 'No NOAA or NSRDB integration exists'/'Solar irradiance comes from Synoptic' docs/data-science/PRD.md == 0; manual diff review confirms the other two §10 rows are byte-identical"
        status: pass
    human_judgment: false
  - id: D3
    description: "data_provider.md's status line records a ratified decision; its closing section records what was decided and which phase implemented each provider; all three stale NREL developer-portal hostname occurrences are corrected"
    requirement: "WX-08"
    verification:
      - kind: other
        ref: "grep -c 'vetting in progress'/'Explicitly not decided here'/'developer\\.nrel\\.gov' docs/data-science/decisions/data_provider.md == 0; grep -c 'developer\\.nlr\\.gov' >= 3"
        status: pass
    human_judgment: false
  - id: D4
    description: "C4-weather-ingestion.md documents the Phase 10 fallback (SYNOPTIC_FALLBACK_STATIONS, fallback keyword, _as_grid_shaped, EnvironmentError split, null-solar guarantee) where a maintainer would look for it, with the Status line and Open Questions updated"
    requirement: "WX-06"
    verification:
      - kind: other
        ref: "grep -c 'SYNOPTIC_FALLBACK_STATIONS'/'Phase 10'/'WX-06' docs/data-science/specs/C4-weather-ingestion.md all non-zero"
        status: pass
    human_judgment: false
  - id: D5
    description: "This was a documentation-only pass: no file under backend/ was modified and the full repository test suite still reports 0 failed"
    requirement: "WX-08"
    verification:
      - kind: other
        ref: "git diff --name-only -- backend/ (empty); .venv/bin/python -m pytest -q"
        status: pass
    human_judgment: false
  - id: D6
    description: "A human confirms, against the live Synoptic endpoint, that the fallback retrieves real data for all four configured stations and attributes it honestly (Task 3)"
    requirement: "WX-06"
    verification: []
    human_judgment: true
    rationale: "Task 3 is an explicit checkpoint:human-verify with gate=\"blocking-human\", and this session could not even run its own automation: SYNOPTIC_TOKEN and the NREL credential pair are not set in this isolated worktree's environment, and reading the repository's .env file is denied by the execution sandbox. Per the task's own <how-to-verify> step 1, this is a recorded blocker, not a completed or failed check -- a human (or a session with live-credential access) must perform the live confirmation this task requires."

duration: ~20min (Task 2 only; Task 3 blocked before any automation could run)
completed: 2026-09-15
status: halted
---

# Phase 10 Plan 3: PRD.md/data_provider.md Ratification and C4 Fallback Documentation Summary

**`PRD.md` §7.1 and `data_provider.md` now record the ratified per-variable weather-provider composition Phases 6-10 actually built (TCEQ+ASOS wind/temp, NSRDB solar, Open-Meteo historical backfill, Synoptic automatic fallback), and `C4-weather-ingestion.md` documents Phase 10's fallback wiring — with Task 3's live-endpoint confirmation blocked by a genuine credential-access gap in this isolated worktree, not by any finding about the fallback itself.**

## Performance

- **Duration:** ~20 min (Task 2 only)
- **Tasks:** 1 of 2 remaining tasks completed (Task 2); Task 3's checkpoint could not begin its own automation
- **Files modified:** 4

## Accomplishments

- Retitled `PRD.md` §7.1 from "unresolved" to "ratified" and rewrote its body from a three-way open decision into a resolved record: option (c), a provider-agnostic interface sourcing each variable family from its strongest provider, with a table naming all five shipped providers, their roles, implementing modules, and provenance values, plus the fallback policy and its three deliberate non-triggers (caller-shaped errors, `open_meteo`, `EnvironmentError`).
- Corrected `PRD.md` §10's NOAA-plus-NSRDB and solar-irradiance discrepancy rows in the document's own existing strikethrough-plus-RESOLVED style, noting the SDR's NSRDB claim is now substantially correct for the solar half while wind/temperature come from TCEQ CAMS, not NOAA. Extended §5's DS-F2 status text and §6's secrets bullet (added the NREL credential pair) without otherwise touching either section.
- Rewrote `data_provider.md`'s status line, retitled "Recommended Composition (synthesis, not a final decision)" to "Adopted Composition (ratified 2026-09-15)" and appended the Synoptic-fallback element, and rewrote the closing "Explicitly not decided here" paragraph into a record of what was decided and which phase implemented each provider. Corrected all three stale NREL developer-portal hostname occurrences, describing the old hostname by reference (not by repeating the literal stale string) so the plan's own zero-occurrence verify grep holds. Left the TCEQ solar finding (confirmed only for Austin/Corpus Christi) unweakened, pointing at v2 requirement WX-09.
- Added a "Phase 10 additions (WX-06)" paragraph to `C4-weather-ingestion.md` naming `config.SYNOPTIC_FALLBACK_STATIONS`, the `fallback` keyword, `FALLBACK_ELIGIBLE_PRIMARIES`, `_fallback_city_for_request`, `_as_grid_shaped`, the `EnvironmentError`/`ValueError` split, the fallback WARNING log, the credential-free chained both-providers-failed error, and the null-solar guarantee; updated the Status line; added two acceptance-criteria bullets; resolved the Open Questions weather-provider entry.
- Confirmed no file under `backend/` was touched and the full repository suite still reports 388 passed, 0 failed.
- Attempted Task 3's live-endpoint confirmation and found it blocked before any automation step could run: `SYNOPTIC_TOKEN`/NREL credentials are not set in this worktree's shell environment, and this project's execution sandbox denies reading the repository's `.env` file from a worktree-isolated agent. Recorded as a blocker per the task's own instruction, not attempted around.

## Task Commits

Each completed unit of work was committed atomically:

1. **Task 2 — ratify PRD.md §7.1 and data_provider.md, document the fallback in the C4 spec** — `b761540` (docs; includes the `ACKNOWLEDGEMENTS.md` session entry)

**Plan metadata:** pending (this commit, per worktree convention — `.planning/workstreams/multi-provider-weather/STATE.md` and `ROADMAP.md` are excluded, owned by the orchestrator)

_Task 1 (`checkpoint:decision`) was resolved in a prior session and is not re-committed here. Task 3 (`checkpoint:human-verify`, `gate="blocking-human"`) is blocked; see "Issues Encountered" below._

## Files Created/Modified

- `docs/data-science/PRD.md` — §7.1 retitled and rewritten as a ratified record; §10's two stale discrepancy rows corrected; §5 DS-F2 and §6 secrets bullet extended
- `docs/data-science/decisions/data_provider.md` — status line, "Adopted Composition" section, closing decision record rewritten; three stale NREL hostname occurrences corrected
- `docs/data-science/specs/C4-weather-ingestion.md` — Phase 10 additions paragraph, updated Status line, two new acceptance-criteria bullets, resolved Open Questions entry
- `ACKNOWLEDGEMENTS.md` — Phase 10 Plan 10-03 session entry (ECE 464 AI-use disclosure)

## Decisions Made

- **Task 1 not re-presented:** the human's prior "approve, proceed exactly as stated" resolution was treated as final for the ratification wording, per explicit instruction from the coordinating orchestrator — see key-decisions above.
- **Task 3 not attempted past its own precondition check:** the task's own `<how-to-verify>` step 1 requires stopping and recording a blocker when `SYNOPTIC_TOKEN` is absent, rather than reporting a failed fallback. This environment has no `SYNOPTIC_TOKEN` or NREL credentials set, and reading the repo's `.env` file is denied by the sandbox — so this session recorded the blocker rather than fabricating evidence or bypassing the sandbox's access control.
- **`gate="blocking-human"` honored literally, even under an instruction to "proceed through" the task:** this project's checkpoint convention (and the executor's own protocol) excludes `gate="blocking-human"` checkpoints from auto-approval in every execution mode. Because this session could not even gather the automation evidence Task 3 requires (no credentials), there was nothing to present for approval regardless — the checkpoint remains open pending either a human/session with live-credential access performing the check, or an explicit decision to defer it.
- **SUMMARY `status: halted`, not `complete`:** Task 2 is fully committed and verified. Task 3's automation could not run at all in this session (credential gap), and its checkpoint's human sign-off has not occurred — `halted` is the template's documented status for "an intentional, designed stop," which this is.

## Deviations from Plan

None — plan executed as written through Task 2. Task 3 was not skipped by choice; it hit its own documented precondition-failure path (absent `SYNOPTIC_TOKEN`), which the plan's own `<how-to-verify>` step 1 explicitly designed for.

## Issues Encountered

- **Task 3 blocked: no live Synoptic/NREL credentials accessible from this isolated worktree.** `env | grep -iE 'synoptic|nrel|nsrdb'` returned nothing in this worktree's shell, and a direct attempt to check the repository's `.env` file (a read-only `grep -c` count, not printing any secret value) was denied by the execution sandbox's own classifier. `backend/config.py`'s credential-reading functions (`dlr_pipeline._token()`, `nsrdb_provider`'s `NREL_API_KEY`/`NREL_API_EMAIL` lookups) read only `os.getenv`/`os.environ` — no `.env` auto-loading exists in this codebase — so the absence of these env vars in this session's shell is a genuine, verified absence, not an artifact of not having looked hard enough. Per Task 3's own `<how-to-verify>` step 1, this is a recorded blocker, not a finding about the four `SYNOPTIC_FALLBACK_STATIONS` station IDs (`KAUS` confirmed elsewhere; `KCRP`/`KMAF`/`KELP` remain genuinely unconfirmed). Contrast with Phase 9 Plan 09-03's Task 2 (TCEQ live check), which succeeded in an isolated worktree because TCEQ's `daily_summary.pl` endpoint is public and unauthenticated — Synoptic and NREL both require a credential this environment does not expose.
- **Resolution path:** either (a) run Task 3's `<how-to-verify>` steps in a session/environment where `SYNOPTIC_TOKEN` and the NREL credential pair are genuinely available (e.g. the main checkout, not this worktree), or (b) the human explicitly defers Task 3 the way Task 1's own `<options>` describes deferring ratification — though deferring Task 3 specifically (rather than declining the whole ratification) is not one of Task 1's three named options, since Task 1 and Task 3 gate different things (publication wording vs. live-fallback confirmation).

## User Setup Required

**External credentials required to complete this plan's Task 3.** `SYNOPTIC_TOKEN` and the `NREL_API_KEY`/`NREL_API_EMAIL` pair must be available in the environment that runs Task 3's live confirmation — see "Issues Encountered" above. No new account or dashboard configuration is needed beyond what Phases 8-10 already required; this is an environment-access gap for this specific isolated worktree, not a missing external service.

## Next Phase Readiness

- **Task 2 is complete and committed.** `PRD.md` §7.1, `data_provider.md`, and `C4-weather-ingestion.md` now record the ratified composition and the Phase 10 fallback, matching what Phases 6-10 actually implemented. WX-08 is satisfied.
- **Task 3 remains open, blocked on credential access in this session — not failed, not skipped by choice.** Re-run this plan's Task 3 (or dispatch a fresh executor with `SYNOPTIC_TOKEN`/NREL credentials genuinely available) to perform the live per-city fetches, the two forced end-to-end fallbacks (station path via an invalid CAMS ID, grid path via unset NSRDB credentials), and gather the evidence Task 3's `<how-to-verify>` names. Once gathered, a human must still review and approve it — `gate="blocking-human"` is never auto-approved.
- **The v1.1 milestone goal is not yet fully met.** WX-08 (documentation ratification) is done; WX-06's live-endpoint confirmation (this plan's own contribution beyond what 10-01/10-02 already tested against mocks) is the one remaining item before Phase 10 — and the v1.1 milestone — can be marked complete.
- No architectural (Rule 4) escalations occurred this session.

---
*Phase: 10-fallback-wiring-documentation-ratification*
*Completed: 2026-09-15*

## Self-Check: PASSED

- FOUND: `docs/data-science/PRD.md` (modified, on disk)
- FOUND: `docs/data-science/decisions/data_provider.md` (modified, on disk)
- FOUND: `docs/data-science/specs/C4-weather-ingestion.md` (modified, on disk)
- FOUND: `ACKNOWLEDGEMENTS.md` (modified, on disk)
- FOUND: commit `b761540` in `git log --oneline --all`
- Full repository suite: 388 passed, 0 failed (unchanged from the Plan 10-02 baseline — a documentation-only pass)
- `git diff --name-only -- backend/`: empty
- Plan-level `<verification>` re-run: all grep-based checks pass (see coverage D1-D5 above); Task 3's live-endpoint confirmation (D6) not run — recorded blocker, human_judgment: true

## Checkpoint Resolution

Task 3's `blocking-human` checkpoint (live Synoptic-fallback confirmation across all four `SYNOPTIC_FALLBACK_STATIONS` entries) is **still open**. This session could not gather the required live evidence: no `SYNOPTIC_TOKEN` or NREL credential is available in this isolated worktree's environment, and the execution sandbox denies reading the repository's `.env` file directly. No automation was run, no evidence was fabricated, and the checkpoint was not self-approved. A follow-up session with genuine access to `SYNOPTIC_TOKEN` and the NREL credential pair must perform Task 3's `<how-to-verify>` steps before a human can review and approve.
