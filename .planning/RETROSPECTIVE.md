# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

> Note (2026-10-13): the corridor model described in this milestone was retired on 2026-10-12 and replaced by one independent rating point per city (`docs/data-science/decisions/point_scope.md`). The retrospective below is history and is not rewritten.

## Milestone: v1.0 — MVP

**Shipped:** 2026-09-10
**Phases:** 5 (3 GSD-tracked: Phase 3, 4, 5) | **Plans:** 7

### What Was Built
- A safety monitor (`DLRSafetyMonitor`) unified with the real IEEE 738 thermal model, with all five fail-safe gates (G1-G5) resolving toward the static rating instead of a stale or optimistic guess.
- Corridor spatial discretization: two D-01 corridors (Austin↔Corpus Christi, Midland↔El Paso) each split into 5 geodesic points, rated as the minimum ampacity across points, with broadened station discovery and graceful exhaustion fallback.
- Ampacity forecasting (`ampacity_forecast.forecast_ampacity`) with a true out-of-sample walk-forward backtested confidence band, published through an additive `PIPELINE_SCHEMA` v2 extension.
- Learned anomaly detection (`AnomalyDetector`, rolling-baseline cold start, per-corridor control limits) wired as an additive G6 gate into the same fallback path Phase 3 shipped.
- Per-location static-rating comparison (DS-F5) fully wired into the flat pipeline (`dlr_pipeline.py`, `ercot_dlr_merger.py`), closing the one gap a mid-milestone audit surfaced.

### What Worked
- Running a milestone audit *before* declaring v1.0 done caught a real gap (DS-F5 not actually wired end-to-end, despite being checked off) that a plain requirements-checklist review would have missed — `config.STATIC_RATINGS` existed and was correctly read by one consumer (`corridor_discretization.py`) but silently ignored by two others.
- Inserting a small, tightly-scoped Phase 5 to close exactly that one gap (rather than reopening Phase 2) kept the fix auditable and independently verifiable (11/11 must-haves re-derived from a live checkout).
- Fail-safe-by-default as a standing constraint (not a per-phase requirement) made every new gate (G6) and every new consumer (Phase 5's city resolution) default to the conservative choice without needing to re-litigate the principle each time.

### What Was Inefficient
- The original Phase 2 implementation (pre-GSD) shipped DS-F5 as "Complete" without full end-to-end verification, and that status went unchallenged until the first milestone audit — a VERIFICATION.md at Phase 2's original completion would have caught this months earlier.
- The Phase 3+4 forecasting/anomaly-detection loop (`forecast_ampacity`, `AnomalyDetector`) is fully built and tested but has no production caller, because `api/`/`frontend/` are owned by another sub-team and remain not-started placeholders — this is scoped correctly for v1, but means real end-to-end confidence in that loop still rests on tests alone.

### Patterns Established
- Silent-and-conservative fallback on unrecognized/omitted input (e.g. an unknown `city` resolving to `DEFAULT_STATIC_RATING`, which is strictly lower than every configured city rating) is the preferred shape for new optional parameters, over raising — provided the fallback can't cause an optimistic overstatement.
- Every VERIFICATION.md independently re-derives evidence against a live checkout rather than trusting SUMMARY.md's claims — this caught the DS-F5 gap and should stay the norm for future phases.

### Key Lessons
1. A milestone-level audit that cross-references REQUIREMENTS.md, VERIFICATION.md, and actual code (not just checkboxes) is worth running even when every individual phase reports "passed" — pre-GSD phases in particular can carry unverified claims forward silently.
2. When a gap is found late, a narrowly-scoped closure phase (not a reopened prior phase) keeps the fix's blast radius small and independently auditable.

### Cost Observations
- Sessions: not tracked per-session in this repo's GSD history.
- Notable: the DS-F5 closure phase (05) was the smallest phase in the milestone (1 plan, 2 files touched) and delivered the highest-leverage fix — the one requirement standing between "gaps_found" and "passed" at milestone close.

---

## Milestone: v1.1 — Multi-Provider Weather

**Shipped:** 2026-09-15
**Phases:** 5 (Phases 6-10) | **Plans:** 15

### What Was Built
- A redesigned `weather_provider.fetch_weather` adapter with a type-dispatched `location` parameter (station-ID list or lat/lon grid tuple), zero breaking changes to existing callers, and `PIPELINE_SCHEMA` v3's four per-field provenance columns.
- ASOS 1-minute (wind/temp supplement) and Open-Meteo (grid-path historical backfill) wired as the first two trivial no-auth providers, proven end-to-end with a real merged multi-source frame.
- NREL NSRDB PSM v4 as the primary solar-irradiance source for all four cities, with per-year window decomposition and credential-redacted error handling.
- TCEQ CAMS as the primary wind/temp/RH source via HTML-report scraping, with real per-local-calendar-day window decomposition (up to 31 days) across all four cities.
- Synoptic wired as the automatic fallback behind TCEQ/NSRDB (station and grid paths both), with eligibility computed before any provider dispatch so caller-shaped errors and missing-credential `EnvironmentError`s are never masked.
- `PRD.md` §7.1 and `data_provider.md` ratified to record the shipped five-provider composition, closing the project's longest-standing open engineering decision and correcting the System Design Report's self-flagged NOAA/NSRDB discrepancy.

### What Worked
- Sequencing providers from cheapest-to-verify to hardest (trivial no-auth first, then credentialed NSRDB, then the no-REST-API TCEQ scrape, then the fallback that depends on all of them existing) meant each phase's live-check gate only ever had to prove one new surface, not re-verify the whole stack.
- `checkpoint:human-verify` gates with `gate="blocking-human"` for live-endpoint confirmation caught real bugs a mocked test suite structurally cannot reach: Phase 9's TCEQ live check found and fixed two real report-parsing bugs; Phase 10's live check confirmed all four Synoptic fallback stations return real data (three of which had never been fetched under this project's token before).
- Computing fallback eligibility from provider+path alone, before any `try`, rather than from error type, made the "does this caller-shaped error ever fall back" question answerable by reading one boolean expression instead of tracing every raise site.

### What Was Inefficient
- A `gate="blocking-human"` checkpoint that needs live API credentials cannot be completed inside a worktree-isolated executor agent when those credentials only exist in the user's local `.env` — this was discovered mid-phase (Plan 10-03's Task 3) and required a manual hand-off (a runnable script, then inline one-liners) to the user's own shell. Worth flagging *before* dispatch next time a plan's checkpoint needs a real external credential.
- The harness's worktree isolation forks executor agents from `origin/HEAD`, not local `main` — after Plan 10-01 merged locally without a push, Plan 10-02's executor forked from a 3-commit-stale base and had to be re-dispatched. Push to origin after every wave merge when worktree isolation is in play, not just at the end of a phase.
- Choosing an "invalid CAMS ID" as the first attempt to force the TCEQ→Synoptic fallback live actually exercised the *caller-shaped-error* exclusion (correctly re-raising instead of falling back) rather than the fallback path itself — a valid station ID with a request shape a live provider genuinely rejects (an out-of-range window, an unpublished data year) is what actually forces the fallback to fire against reality.

### Patterns Established
- Fallback eligibility as a pre-computed boolean (provider+path, never error type) with `EnvironmentError` always propagating unchanged — the shape any future "provider X falls back to provider Y" feature in this codebase should reuse.
- A `checkpoint:human-verify` task's `<how-to-verify>` step 1 ("if the credential is absent, stop and record the blocker, don't report a failed check") is the correct response to a genuinely unavailable credential — not a reason to fabricate evidence or bypass the sandbox.

### Key Lessons
1. When a phase's live-check gate needs a real external credential, confirm *before* dispatching a worktree-isolated executor whether that credential is actually reachable from an isolated worktree — if not, plan for a human hand-off step rather than discovering the blocker mid-execution.
2. Forcing a fallback path live requires understanding the primary provider's *own* validation order: an error thrown before the point where a "this maps to a real city" check happens will never be fallback-eligible, no matter how invalid the input looks.
3. With worktree-isolated parallel execution, `origin/HEAD` — not local `main` — is the fork base; push after each wave that lands worktree-isolated work, not just at phase end.

### Cost Observations
- Sessions: this milestone's Phase 10 alone spanned two sessions (a `/gsd-execute-phase` run that got Tasks 1-2 of Plan 10-03 done and correctly halted on a credential gap, followed by a `/gsd-complete-milestone` session after the human ran the live check locally).
- Notable: full suite grew from 155 (v1.0) to 388 passing, 0 failed — more than doubling test count while adding four new external providers and a fallback layer, with zero regressions surfaced at any phase boundary.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | N/A | 5 | First GSD-tracked milestone on this repo; Phases 1-2 adopted from pre-GSD implementation, Phases 3-5 fully GSD-tracked with VERIFICATION.md gates |
| v1.1 | 2+ | 5 | First milestone using the multi-workstream layout (`.planning/workstreams/multi-provider-weather/`); first milestone with `gate="blocking-human"` checkpoints requiring live external credentials, surfacing a real gap in worktree-isolated executor credential access |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | 155 passing | Not measured | 0 (Phase 4 explicitly deferred Tier 2 modelling to avoid adding a dependency; Phase 5 added none) |
| v1.1 | 388 passing | Not measured | 0 (all four new providers use `requests`, already a dependency; `beautifulsoup4` pinned for TCEQ's HTML scrape in Phase 9) |

### Top Lessons (Verified Across Milestones)

1. Audit before closing a milestone, even when every phase individually reports "passed" — cross-referencing requirements against actual code found a gap phase-level review missed.
2. A `gate="blocking-human"` checkpoint needing a real external credential cannot always be completed inside a worktree-isolated executor — check credential reachability before dispatch, not after a blocked run.
3. Worktree-isolated parallel execution forks from `origin/HEAD`; push after each wave that lands isolated work to avoid a stale-base re-dispatch.
