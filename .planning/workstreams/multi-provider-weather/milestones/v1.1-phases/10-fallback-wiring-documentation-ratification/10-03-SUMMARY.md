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
  tasks: 2
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
  - "Task 3's live-endpoint confirmation was completed in a follow-up session run by the human directly against their local checkout, where SYNOPTIC_TOKEN and the NREL credential pair (loaded from the repository's untracked .env) are genuinely available -- the isolated worktree that produced Task 2's commit had neither, per the blocker recorded below. The human ran the automation themselves (per-city fetches, a real TCEQ >31-day-window failure to force the station-path fallback, a real NSRDB HTTP 400 on an unpublished data year to force the grid-path fallback, and an EnvironmentError check with NREL_API_KEY unset) and reported the full evidence back for review."
  - "SUMMARY status updated to complete: Task 2's ratification and Task 3's live-endpoint confirmation are both done. The human reviewed the gathered evidence (see Checkpoint Resolution) and approved it explicitly -- gate=\"blocking-human\" was never auto-approved."

requirements-completed: [WX-06, WX-08]

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
    verification:
      - kind: other
        ref: "Live per-city fetch: AUSTIN/KAUS 2,682 rows, CORPUS_CHRISTI/KCRP 5,209 rows, MIDLAND/KMAF 5,542 rows, EL_PASO/KELP 1,257 rows -- all four non-null for air_temp/wind_speed/wind_direction (all four stations readable under this project's token, improving on the C4 spec's prior 'only KAUS confirmed' note)"
        status: pass
      - kind: other
        ref: "Real station-path fallback: TCEQ AUSTIN request over a 74-day window (> TCEQ_MAX_DAYS_PER_FETCH=31) raised a genuine ValueError; fallback fired to Synoptic KAUS (87,226 rows); wind_source/temp_source read 'synoptic'/'asos', never 'tceq'"
        status: pass
      - kind: other
        ref: "Real grid-path fallback: NSRDB AUSTIN request for year 2026 (not yet published) raised a genuine HTTP 400 ValueError; fallback fired to Synoptic KAUS (5,316 rows); solar_source correctly null (KAUS carries no solar sensor -- matches the documented no-fabrication guarantee) and no *_source cell read 'nsrdb'"
        status: pass
      - kind: other
        ref: "EnvironmentError branch: NSRDB request with NREL_API_KEY unset raised EnvironmentError and did NOT fall back, as required"
        status: pass
    human_judgment: true
    rationale: "Task 3 is an explicit checkpoint:human-verify with gate=\"blocking-human\". The isolated worktree that produced Task 2's commit had no SYNOPTIC_TOKEN/NREL credentials and could not run this task's automation (recorded as a blocker, not a failure). The human then ran the four checks above directly against their local checkout (where the credentials are genuinely available) and reviewed the full evidence, approving it explicitly rather than the checkpoint being auto-approved."

duration: ~20min (Task 2, prior session) + live-endpoint confirmation run and approved by the human in a follow-up session
completed: 2026-09-15
status: complete
---

# Phase 10 Plan 3: PRD.md/data_provider.md Ratification and C4 Fallback Documentation Summary

**`PRD.md` §7.1 and `data_provider.md` now record the ratified per-variable weather-provider composition Phases 6-10 actually built (TCEQ+ASOS wind/temp, NSRDB solar, Open-Meteo historical backfill, Synoptic automatic fallback), `C4-weather-ingestion.md` documents Phase 10's fallback wiring, and the fallback has now been confirmed against the live Synoptic and NSRDB endpoints — all four `SYNOPTIC_FALLBACK_STATIONS` return real data, and both the station-path and grid-path fallbacks were exercised end-to-end against genuine provider failures with correct provenance.**

## Performance

- **Duration:** ~20 min (Task 2) + a follow-up session for Task 3's live-endpoint confirmation
- **Tasks:** 2 of 2 completed (Task 2 and Task 3; Task 1's decision was resolved in an earlier session)
- **Files modified:** 4

## Accomplishments

- Retitled `PRD.md` §7.1 from "unresolved" to "ratified" and rewrote its body from a three-way open decision into a resolved record: option (c), a provider-agnostic interface sourcing each variable family from its strongest provider, with a table naming all five shipped providers, their roles, implementing modules, and provenance values, plus the fallback policy and its three deliberate non-triggers (caller-shaped errors, `open_meteo`, `EnvironmentError`).
- Corrected `PRD.md` §10's NOAA-plus-NSRDB and solar-irradiance discrepancy rows in the document's own existing strikethrough-plus-RESOLVED style, noting the SDR's NSRDB claim is now substantially correct for the solar half while wind/temperature come from TCEQ CAMS, not NOAA. Extended §5's DS-F2 status text and §6's secrets bullet (added the NREL credential pair) without otherwise touching either section.
- Rewrote `data_provider.md`'s status line, retitled "Recommended Composition (synthesis, not a final decision)" to "Adopted Composition (ratified 2026-09-15)" and appended the Synoptic-fallback element, and rewrote the closing "Explicitly not decided here" paragraph into a record of what was decided and which phase implemented each provider. Corrected all three stale NREL developer-portal hostname occurrences, describing the old hostname by reference (not by repeating the literal stale string) so the plan's own zero-occurrence verify grep holds. Left the TCEQ solar finding (confirmed only for Austin/Corpus Christi) unweakened, pointing at v2 requirement WX-09.
- Added a "Phase 10 additions (WX-06)" paragraph to `C4-weather-ingestion.md` naming `config.SYNOPTIC_FALLBACK_STATIONS`, the `fallback` keyword, `FALLBACK_ELIGIBLE_PRIMARIES`, `_fallback_city_for_request`, `_as_grid_shaped`, the `EnvironmentError`/`ValueError` split, the fallback WARNING log, the credential-free chained both-providers-failed error, and the null-solar guarantee; updated the Status line; added two acceptance-criteria bullets; resolved the Open Questions weather-provider entry.
- Confirmed no file under `backend/` was touched and the full repository suite still reports 388 passed, 0 failed.
- Completed Task 3's live-endpoint confirmation in a follow-up session run directly against the human's local checkout (real `SYNOPTIC_TOKEN`/NREL credentials, no mocking): all four `SYNOPTIC_FALLBACK_STATIONS` (`KAUS`, `KCRP`, `KMAF`, `KELP`) returned real, non-null observation data; a real TCEQ failure (a >31-day window exceeding `TCEQ_MAX_DAYS_PER_FETCH`) forced a genuine station-path fallback to Synoptic with correct `synoptic`/`asos` provenance; a real NSRDB failure (HTTP 400 for an unpublished 2026 data year) forced a genuine grid-path fallback to Synoptic with a correctly-null `solar_source` (KAUS has no solar sensor); and the `EnvironmentError` branch (NREL credential unset) correctly raised without falling back.

## Task Commits

Each completed unit of work was committed atomically:

1. **Task 2 — ratify PRD.md §7.1 and data_provider.md, document the fallback in the C4 spec** — `b761540` (docs; includes the `ACKNOWLEDGEMENTS.md` session entry)

**Plan metadata:** owned by the orchestrator (`.planning/workstreams/multi-provider-weather/STATE.md` and `ROADMAP.md` are updated centrally, not per-worktree).

_Task 1 (`checkpoint:decision`) was resolved in a prior session and is not re-committed here. Task 3 (`checkpoint:human-verify`, `gate="blocking-human"`) produces no code/doc commit of its own — it is a live-evidence-gathering and human-approval gate, and its evidence is recorded in coverage item D6 and "Checkpoint Resolution" below._

## Files Created/Modified

- `docs/data-science/PRD.md` — §7.1 retitled and rewritten as a ratified record; §10's two stale discrepancy rows corrected; §5 DS-F2 and §6 secrets bullet extended
- `docs/data-science/decisions/data_provider.md` — status line, "Adopted Composition" section, closing decision record rewritten; three stale NREL hostname occurrences corrected
- `docs/data-science/specs/C4-weather-ingestion.md` — Phase 10 additions paragraph, updated Status line, two new acceptance-criteria bullets, resolved Open Questions entry
- `ACKNOWLEDGEMENTS.md` — Phase 10 Plan 10-03 session entry (ECE 464 AI-use disclosure)

## Decisions Made

- **Task 1 not re-presented:** the human's prior "approve, proceed exactly as stated" resolution was treated as final for the ratification wording, per explicit instruction from the coordinating orchestrator — see key-decisions above.
- **Task 3 initially blocked, then completed in a follow-up session:** the task's own `<how-to-verify>` step 1 requires stopping and recording a blocker when `SYNOPTIC_TOKEN` is absent, rather than reporting a failed fallback. The isolated worktree that produced Task 2's commit had no `SYNOPTIC_TOKEN`/NREL credentials, so that session recorded the blocker per instruction. A follow-up session then ran Task 3's automation directly against the human's local checkout (real credentials present) and reported the results back for review.
- **`gate="blocking-human"` honored literally throughout:** this project's checkpoint convention excludes `gate="blocking-human"` checkpoints from auto-approval in every execution mode. The evidence in coverage item D6 was gathered by the automation and then explicitly reviewed and approved by the human — it was never self-approved by an executor.
- **SUMMARY `status: complete`:** Task 2 is fully committed and verified; Task 3's live-endpoint evidence has been gathered and explicitly approved by the human. Both tasks in this plan are now done.

## Deviations from Plan

An invalid CAMS ID (as a literal example) does not exercise the fallback the way Task 3 intends: `tceq_provider.fetch_tceq` rejects an unrecognized site ID with a `ValueError` before any network call (`no fixed UTC offset registered`), and `weather_provider._fallback_city_for_request` correctly treats an unrecognized CAMS ID as unresolvable and re-raises rather than falling back — this is the caller-shaped-error exclusion working exactly as designed, not a bug. Task 3's live check instead forced the station-path fallback with a *valid* CAMS ID (`config.TCEQ_STATIONS["AUSTIN"]`) over a 74-day window exceeding `TCEQ_MAX_DAYS_PER_FETCH=31`, and the grid-path fallback with a real NSRDB request for an as-yet-unpublished data year (2026) rather than a future date (a future date also causes the Synoptic fallback itself to have no data available, which would have produced a correct-but-uninformative both-providers-failed result instead of demonstrating a successful fallback).

## Issues Encountered

- **Task 3 initially blocked: no live Synoptic/NREL credentials accessible from the isolated worktree that ran Task 2.** `SYNOPTIC_TOKEN`/`NREL_API_KEY` were absent from that worktree's shell environment, and the execution sandbox denied reading the repository's `.env` file directly from within it. This was resolved by running Task 3's automation in a follow-up session against the human's own local checkout, where `.env` is genuinely loaded (via `source .env` with `set -a`, since this codebase reads plain `os.getenv`/`os.environ` — there is no `.env` auto-loading in `backend/`).
- **Resolved — no further action needed.** All four `SYNOPTIC_FALLBACK_STATIONS` entries returned real data (`KCRP`/`KMAF`/`KELP` had been genuinely unconfirmed prior to this check; all three are now confirmed alongside `KAUS`), so no station ID needs replacement, contrary to what "Issues Encountered" originally anticipated.

## Next Phase Readiness

- **Both tasks are complete.** `PRD.md` §7.1, `data_provider.md`, and `C4-weather-ingestion.md` record the ratified composition and the Phase 10 fallback (WX-08), and the fallback has been confirmed against the live Synoptic and NSRDB endpoints with correct provenance in both directions (WX-06).
- **The v1.1 milestone goal is met by this plan's completion.** Phase 10 (and with it, the v1.1 milestone's `PRD.md` §7.1 resolution) can be marked complete pending the orchestrator's roadmap/state update and phase-goal verification.
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
- Plan-level `<verification>` re-run: all grep-based checks pass (see coverage D1-D5 above); Task 3's live-endpoint confirmation (D6) gathered and human-approved in a follow-up session

## Checkpoint Resolution

Task 3's `blocking-human` checkpoint (live Synoptic-fallback confirmation across all four `SYNOPTIC_FALLBACK_STATIONS` entries) is **resolved and approved**. The isolated worktree that ran Task 2 could not gather live evidence (no credentials available there); a follow-up session ran the required checks directly against the human's local checkout, where `SYNOPTIC_TOKEN` and the NREL credential pair are genuinely available:

- **Per-city live fetch** (all four `SYNOPTIC_FALLBACK_STATIONS`): `AUSTIN`/`KAUS` 2,682 rows, `CORPUS_CHRISTI`/`KCRP` 5,209 rows, `MIDLAND`/`KMAF` 5,542 rows, `EL_PASO`/`KELP` 1,257 rows — all four non-null for `air_temp`, `wind_speed`, `wind_direction`. No station is unreadable; no replacement ID is needed.
- **Station-path fallback**, forced with a real TCEQ failure (a 74-day request window exceeding `TCEQ_MAX_DAYS_PER_FETCH=31`): fired to Synoptic `KAUS`, returned 87,226 rows, `wind_source`/`temp_source` correctly read `synoptic`/`asos` and never `tceq`.
- **Grid-path fallback**, forced with a real NSRDB failure (HTTP 400 for the as-yet-unpublished 2026 data year): fired to Synoptic `KAUS`, returned 5,316 rows, and `solar_source` was correctly null (this Synoptic station carries no solar sensor, so the null-rather-than-fabricated guarantee held) with no `*_source` cell reading `nsrdb`.
- **`EnvironmentError` branch** (NREL credential unset): raised `EnvironmentError` and did not fall back, as required.

The human reviewed this evidence in full and explicitly approved it. No secret value (token, request URL, response header) was ever printed or recorded — only station IDs, row counts, timestamps, and null-ness, per the plan's own information-disclosure mitigation (T-10-15).
