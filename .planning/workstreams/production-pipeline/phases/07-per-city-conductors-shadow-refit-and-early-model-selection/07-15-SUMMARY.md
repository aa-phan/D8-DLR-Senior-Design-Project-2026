---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 15
subsystem: early-model-selection-read2
tags: [confirmation-protocol, v4-read2, fresh-read, one-shot, conditional-retest, shadow-evaluation]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-12 read 1 evidence and the recorded no-pick (D-08 trigger); plan 07-11 vetoes.json; plan 07-07 guard
provides:
  - read2_preflight.json (dry run, equality checks against read 1, count-only; no truth or outcome)
  - v4 read 2 headline evidence (reconstructed frames) and live-system evidence (shadow logs), run once each
affects: [07-16]

requirements-completed: []

actuals:
  tokens: 6000
  tasks: 2
  commits: 2
plan_head_before: b6e910fb572ad44e088bf7aa62974ef7b89d5ba3
plan_head_after: e5bfb9fb3dd6f78745986ec5b88d42fb279b3772

tech-stack:
  added: []
  patterns:
    - "One-shot FRESH read: each evidence root written once by the command that produced it, committed by explicit path"

key-files:
  created:
    - docs/data-science/decisions/v4_selection/read2_preflight.json
    - data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/
    - data/shadow/evaluation/v4-read2/shadow_logs_20261108T012122Z/
  modified: []

key-decisions:
  - "Owner said go at 2026-11-08T01:20Z (UTC); read 2 ran once per row source immediately after, from the main checkout (configuration unchanged since read 1, so no worktree), no flag beyond those the plan lists and no override text"
  - "Read 2 also names no winner under signed v4 (pick null); per the report, there is no day-ahead pick and the interim G6 method keeps running (owner item O3)"

patterns-established: []

coverage:
  - id: D1
    description: "Owner's go recorded after an automated preflight (all 11 checks PASS, read2_preflight.json committed in f9be67a with no truth, metrics, family or decision key)"
    requirement: SEL-04
    verification:
      - kind: command
        ref: "read2_preflight.json: would_refuse false, expected_slots_per_city 128, rating_config_version equal to read 1's, vetoes sha256 equal, worktree_at_read1_commit_needed false"
        status: pass
    human_judgment: true
  - id: D2
    description: "Read 2 ran exactly once per row source under the signed protocol, headline and live-system; evidence committed"
    requirement: SEL-04
    verification:
      - kind: command
        ref: "python3 headline report.json -> 'v4-read2 FRESH signed'; live report.json round v4-read2, basis FRESH, protocol_status signed, label 'live-system check, never decides'; git ls-files --error-unmatch on both report.json exits 0"
        status: pass
    human_judgment: false

duration: 3min (this continuation: precondition check to evidence commit)
completed: 2026-11-08
status: complete
---

# Phase 7 Plan 15: v4 Read 2 Summary

**Read 2 (the one pre-registered re-test) ran once per row source after the owner's go and also names no winner: no candidate qualifies under signed v4 (pick: none), so no shadow model replaces ml and the interim G6 method keeps running.**

## Performance

- **Tasks:** 2 (Task 1 the blocking-human go, Task 2 the one-shot read)
- **Completed:** 2026-11-08
- **Commits:** 2 (measured: `git rev-list --count b6e910f..HEAD`; the plan ledger was started after the preflight commit, so the base is the preflight commit's parent)

## Accomplishments

- **Task 1 (earlier, `f9be67a`).** Automated preflight (all 11 checks PASS) committed as `read2_preflight.json`. The owner replied `go` (verbatim) at 2026-11-08T01:20Z (UTC).
- **Task 2 precondition.** Re-checked immediately before the headline command: reply `go`; UTC clock 2026-11-08T01:21:05Z, `>= 2026-11-08T00:00:00Z` printed True; the read-scope clean-tree check printed nothing; `origin/shadow-collection-data` fetched and still at `e7863106bc7f305534031c818092887ddd207eeb` (commit date 2026-11-08T00:02:46Z), the same commit the preflight counted; the live-system logs were exported from that commit (118 lines per city).
- **Headline (reconstructed frames), run once, exit 0.** `forecast_shadow_confirm.py --round v4-read2 --protocol-status signed --vetoes docs/data-science/decisions/v4_selection/vetoes.json --evidence-root data/shadow/evaluation` wrote `data/shadow/evaluation/v4-read2/reconstructed_frames_20261108T012106Z/`. Round `v4-read2`, basis `FRESH`, protocol status `signed`, label `headline decision`, config `v3-powersystems-2026-11-02` (equal to read 1's), conductor-basis differing city: AUSTIN. Scored window 2026-09-30T00:00:00Z to 2026-11-01T00:00:00Z. No failed city, no exclusions; 128 slots per city (pooled nominal n = 512). No override text (`override_reason` null, `prior_fresh_runs` empty for this round).
- **Live-system check (shadow logs), run once, exit 0.** `forecast_shadow_score.py --round v4-read2 --protocol-status signed --predictions-dir <export> --source-commit e7863106... --evidence-root data/shadow/evaluation` wrote `.../shadow_logs_20261108T012122Z/`. Label `live-system check, never decides`; pick is always none.
- Run from the main checkout (no worktree): the preflight found the rating configuration unchanged since read 1. `git worktree list` shows only the main checkout.

## Outcome (copied from the report, not interpreted; 07-16 writes the results for the owner)

**Headline**

- **Pick:** none. "No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07). Read 2 (v4-read2) also names no winner: there is no day-ahead pick and the interim G6 method keeps running; 2026-11-24 stays retired and any later evaluation needs a new signed protocol (owner item O3)."
- No candidate vetoed (ablation and test both false for all three).
- Evidence level for every candidate: `not shown`; Holm rejected: none. Holm-adjusted p: ml_wind_corrected 0.764, ml_cooling_corrected 0.293, reference_ml_refit_24h 0.764.
- Pooled bar 28.01 A (pooled paired, n = 512 each). Benefit vs raw_forecast (amps): ml_wind_corrected 3.97, ml_cooling_corrected 12.12, reference_ml_refit_24h -24.19.
- Margin vs the default ml_wind_corrected: ml_cooling_corrected +8.14 A (below the 28.01 A bar), reference_ml_refit_24h -28.16 A. Neither is consistently better.
- Per-city consistency (need 3 of 4): ml_wind_corrected 3, ml_cooling_corrected 3, reference_ml_refit_24h 1. Per-city bars: AUSTIN 28.84, CORPUS_CHRISTI 27.85, EL_PASO 24.22, MIDLAND 31.12 A.
- Sample size: effective n (bootstrap, ml_wind_corrected vs ml_cooling_corrected) 203.6, vs reference_ml_refit_24h 57.4; both precision targets (about 590 rows tail rate, about 1,575 rows for 5 A) not met for any headline test.

**Secondary (frozen Drake artifacts, AUSTIN differs):** pick none, "never decides"; Holm-adjusted p: ml_wind_corrected 0.509, ml_cooling_corrected 0.226, reference_ml_refit_24h 0.380; margin vs ml_wind_corrected +8.22 A (cooling, bar 26.82 A) and -30.95 A (refit).

**Live-system check (shadow logs, 72 of the logged rows per city in scope):** pick none (always none; would-be outcome: no candidate qualifies). Paired n per comparison 265 to 280. Benefit vs raw (amps): ml_wind_corrected 0.85, ml_cooling_corrected -0.01, reference_ml_refit_24h -36.72; Holm-adjusted p 1.0, 1.0, 0.223. Cities favouring: ml_wind_corrected 2, ml_cooling_corrected 2, reference_ml_refit_24h 0 (need 3).

## Task Commits

1. **Task 1: owner's go after preflight** - `f9be67a` (docs)
2. **Task 2: read 2 evidence (headline and live-system)** - `e5bfb9f` (docs)

## Deviations from Plan

None - plan executed exactly as written. Each FRESH command ran once, with exactly the flags in the plan.

## Issues Encountered

None. No fetch failed; no city excluded. Task 2's commit was made on `main`, which the project config explicitly allows (`git.allow_default_branch_commits: true`), matching earlier Phase 7 plans.

## Known Stubs

None.

## Threat Flags

None. Evidence holds public Open-Meteo responses only; no credential used.

## Notes for Later Plans

- 07-16 writes the plain-English results and records the owner's decision. Both reads name no winner, so per the report no shadow model replaces ml, the interim G6 method keeps running, and any later evaluation needs a new signed protocol.
- SEL-04 is NOT marked complete here: 07-16 still declares it (see state update).

## Self-Check: PASSED

- Files found: `read2_preflight.json`, both evidence directories (report.json, report.md, run_started.json, http/, frames/), tracked via `git ls-files`.
- Commits found in history: `f9be67a`, `e5bfb9f`.
