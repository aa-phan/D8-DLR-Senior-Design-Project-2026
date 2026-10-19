---
workstream: production-pipeline
created: 2026-10-18
milestone_name: Production Pipeline (Supabase + live ratings)
status: in_progress
---

# Project State

## Project Reference

See: this workstream's REQUIREMENTS.md and ROADMAP.md (both 2026-10-18).

**Core value:** Every city's dynamic rating is computed on a schedule, stored in Supabase Postgres,
and readable by the other teams at any time through a read-only REST interface.

**Scope note (owner, 2026-10-18):** this workstream strings the system together end to end. It
does not analyze the ratings themselves. Observations about output values are recorded below for
whoever owns that analysis; they are not work items here.

## Current Position

**Status:** Phase 1 (Land PR #7) mostly complete; LAND-03 open
**Current Phase:** 1
**Last Activity:** 2026-10-19
**Last Activity Description:** PR #7 restructure pushed to main (5efe97d); live run verified

## Phase 1 Progress

| Req | Status | Evidence |
|-----|--------|----------|
| LAND-01 | Done | 151aac2: files at `backend/` / `docs/` paths, LF, root `dlr_pipeline.py` dropped. 5efe97d removed the `backup/` upload |
| LAND-02 | Done | b1e1d7b (19 `city_rating_test` fixtures get `wind_direction`), e330570 (cron test now checks the cron-job.org dispatch). Suite: 1236 passed, 0 failed |
| LAND-03 | **Open** | No tests yet for `observation_composer`, `city_pipeline`, `dlr_orchestrator`, `backfill_archive` |
| LAND-04 | Done | Amendments in `docs/data-science/PRD.md` §7.1 and `decisions/data_provider.md` |
| PIPE-01 | Done (live) | 2026-10-19 ~04:25Z `dlr_orchestrator --no-archive`, run by the owner: all 4 cities rated through composed weather → projection → G1-G6 |

**History note:** PR #7 was merged on GitHub at 35939cc (root-level uploads plus `backup/`) before
the restructured branch was pushed. Main was then fast-forwarded to 5efe97d, whose tree equals the
restructured branch (e330570) and contains no `backup/`. PR #8 (an accidental auto-revert of #7)
was closed and its branch deleted.

## Integration Items Found in the Live Run (2026-10-19)

These block or affect stringing the system together and belong to the phases named.

1. **Anomaly models are not available outside the main checkout** (Phase 4/5). `data/models/` is
   git-ignored, so the worktree run logged "no trained anomaly model" for all 4 cities, and a
   GitHub Actions runner will hit the same thing. The live workflow needs a way to provision
   `data/models/anomaly_{CITY}.joblib`: commit them, download a release/artifact, or train in CI.
2. **`dlr_orchestrator` does not load `.env`** (Phase 1 follow-up or Phase 5). Local CLI runs need
   the variables exported. `.env` uses `KEY = value` spacing that `source` rejects, so loading it
   through python-dotenv works. Actions will pass secrets as env vars, so this only affects local
   runs. Option: call `load_dotenv()` in `main()` as `forecast_shadow_pipeline.py` does.
3. **NSRDB fails 3 times per run for current windows** (Phase 5). It has no 2026 data (HTTP 400),
   so each live run spends 3 calls before the circuit breaker skips it. Option: skip NSRDB when
   the window is past its coverage.
4. **Stray `print` output** (Phase 5, log hygiene): `SUMMARY:`, `Returned stations`, `OBS keys`
   (Synoptic helpers) and `G4 FAIL ...` (`DLRSafetyMonitor`) go to stdout alongside logging.
   Backfill already redirects stdout to count gate failures, so a change here must keep that
   working.
5. **Cold start** (Phase 4, DB-03): 0 history rows for every city, so no forecast. Expected without
   an archive. The backfill load covers it.

## Output Observations (recorded only; not analyzed in this workstream)

- AUSTIN: computed 1080 A was below its lower bound (`config.RATING_BOUNDS_BY_LOCATION` 1150 A),
  so G4 fell back to the static 1825 A, a higher value than computed. MIDLAND's lower bound
  (1250 A) has the same exposure. Flagged for the owner of rating bounds and fallback policy.
- Other cities: CORPUS_CHRISTI 1259 A (static 1500), MIDLAND 1912 A (1875), EL_PASO 1048 A (1320).

## Decisions

- 2026-10-18: Supabase Postgres as the store, Supabase REST as the read interface, cron-job.org →
  `workflow_dispatch` as the trigger. The DS team holds decision authority on integration
  architecture.
- 2026-10-18: Supersedes the corridor-era `pipeline-integration` workstream.
- 2026-10-18: The workstream's job is to string the system together, not to analyze output values.

## Open Decisions

OD-1 to OD-5 decided 2026-10-19 (REQUIREMENTS.md "Owner decisions"): hourly, composed, ml forecast,
30-min grace, labelled provisional.

## Session Continuity

**Stopped At:** Phase 1, after the push to main; LAND-03 next
**Resume File:** None
