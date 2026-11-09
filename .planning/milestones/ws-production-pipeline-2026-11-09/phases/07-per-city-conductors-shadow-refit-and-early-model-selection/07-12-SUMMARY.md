---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 12
subsystem: early-model-selection-read1
tags: [confirmation-protocol, v4-read1, fresh-read, one-shot, shadow-evaluation]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-11 vetoes.json and the Power Systems gate record; plan 07-07 guard and load_vetoes; plan 07-09 production headline loader and conductor_basis
provides:
  - read1_preflight.json (dry run, veto check, counts only; no truth or outcome)
  - v4 read 1 headline evidence (reconstructed frames) and live-system evidence (shadow logs), run once each
affects: [07-13, 07-14]

requirements-completed: []

actuals:
  tokens: 6000
  tasks: 2
  commits: 2
plan_head_before: 16765f08a1288ceba0bc74549327933537055667
plan_head_after: 2115cfdb618cad319762e7fd2c213e2ac0084f3c

tech-stack:
  added: []
  patterns:
    - "One-shot FRESH read: each evidence root written once by the command that produced it, committed by explicit path"

key-files:
  created:
    - docs/data-science/decisions/v4_selection/read1_preflight.json
    - data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/
    - data/shadow/evaluation/v4-read1/shadow_logs_20261102T175210Z/
  modified: []

key-decisions:
  - "Owner said go at 2026-11-02T17:51Z (UTC); read 1 ran once per row source immediately after, no flag beyond those the plan lists and no override text"
  - "No candidate qualifies under signed v4 (pick null); the pre-registered re-test v4-read2 runs at or after 2026-11-08T00:00:00Z"

patterns-established: []

coverage:
  - id: D1
    description: "Owner's go recorded after an automated preflight (all 11 checks PASS, read1_preflight.json committed in e092d12 with no truth, metrics, family or decision key)"
    requirement: SEL-04
    verification:
      - kind: command
        ref: "read1_preflight.json top-level keys: plan, task, round, purpose, generated_at_utc, utc_clock, owner_sign_off_statement, dry_run, vetoes_record, power_systems_gate, read_scope_clean_tree_check, shadow_log_export, owner_go_status, plain_words"
        status: pass
    human_judgment: true
  - id: D2
    description: "Read 1 ran exactly once per row source under the signed protocol, headline and live-system; evidence committed"
    requirement: SEL-04
    verification:
      - kind: command
        ref: "python3 headline report.json -> 'v4-read1 FRESH signed headline decision'; live report.json round v4-read1, basis FRESH, protocol_status signed, label 'live-system check, never decides'; git ls-files --error-unmatch on both report.json exits 0"
        status: pass
    human_judgment: false

duration: 5min (this continuation: precondition check to evidence commit)
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 12: v4 Read 1 Summary

**Read 1 ran once per row source after the owner's go and names no winner: no candidate qualifies under signed v4 (pick: none), so v4-read2 is the next step at or after 2026-11-08T00:00:00Z.**

## Performance

- **Tasks:** 2 (Task 1 the blocking-human go, Task 2 the one-shot read)
- **Completed:** 2026-11-02
- **Commits:** 2 (measured from the plan ledger)

## Accomplishments

- **Task 1 (earlier, `e092d12`).** Automated preflight (all 11 checks PASS) committed as `read1_preflight.json`. The owner replied `go` (verbatim) at 2026-11-02T17:51Z (UTC).
- **Task 2 precondition.** Re-checked immediately before the headline command: reply `go`; UTC clock 2026-11-02T17:51:51Z, `>= 2026-11-01T00:00:00Z` printed True; the read-scope clean-tree check printed nothing; `origin/shadow-collection-data` still at `ec4279c04324c0935e77eccf4b3338f754c852da`, the commit the preflight exported the logs from (export in `/tmp/read1logs.yrTl` reused).
- **Headline (reconstructed frames), run once, exit 0.** `forecast_shadow_confirm.py --round v4-read1 --protocol-status signed --vetoes docs/data-science/decisions/v4_selection/vetoes.json --evidence-root data/shadow/evaluation` wrote `data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/`. Round `v4-read1`, basis `FRESH`, protocol status `signed`, label `headline decision`, config `v3-powersystems-2026-11-02`, conductor basis differing city: AUSTIN. No failed city; 100 slots per city scored for every candidate (pooled nominal n = 400).
- **Live-system check (shadow logs), run once, exit 0.** `forecast_shadow_score.py --round v4-read1 --protocol-status signed --predictions-dir <export> --source-commit ec4279c0... --evidence-root data/shadow/evaluation` wrote `.../shadow_logs_20261102T175210Z/`. Label `live-system check, never decides`; pick is always none; paired n per comparison 165 to 171.

## Outcome (copied from the report, not interpreted; 07-13 writes the results for the owner)

- **Headline pick:** none. "No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07). Read 1 names no winner, so the pre-registered re-test v4-read2 runs at or after 2026-11-08T00:00:00Z under the same rules."
- No candidate vetoed (ablation and test both false for all three).
- Evidence level for every candidate: `not shown`; Holm-adjusted p: ml_wind_corrected 0.957, ml_cooling_corrected 0.362, reference_ml_refit_24h 0.957. Holm rejected: none.
- Pooled bar vs default (ml_wind_corrected): 27.86 A; ml_cooling_corrected margin 5.54 A, reference_ml_refit_24h margin -35.95 A; neither consistently better.
- Per-city consistency (need 3 of 4): ml_wind_corrected 3, ml_cooling_corrected 3, reference_ml_refit_24h 1. Per-city bars: AUSTIN 28.48, CORPUS_CHRISTI 27.40, EL_PASO 24.69, MIDLAND 30.87 A.
- Both precision targets (about 590 rows tail rate, about 1,575 rows 5 A) not met for any headline test.
- Secondary block (frozen Drake artifacts, AUSTIN differs): pick none, "never decides".
- Report header shows `Git SHA e092d129... (dirty: True)`: the working tree held only unrelated files (.DS_Store, .obsidian, graphify-out, .planning/*, docs Test and Evaluation Report.*); the read-scope clean-tree check printed nothing before the run.

## Task Commits

1. **Task 1: owner's go after preflight** - `e092d12` (docs)
2. **Task 2: read 1 evidence (headline and live-system)** - `2115cfd` (docs)

## Deviations from Plan

None - plan executed exactly as written. Each FRESH command ran once, with exactly the flags in the plan.

## Issues Encountered

None. No fetch failed; no city excluded.

## Known Stubs

None.

## Threat Flags

None. Evidence holds public Open-Meteo responses only; no credential used.

## Notes for Later Plans

- 07-13 writes the plain-English results and records the owner's decision; the headline names no winner, so the next read is v4-read2 (at or after 2026-11-08T00:00:00Z).
- SEL-04 is NOT marked complete: `requirements.ready-ids` reports it blocked (the owner decision and the conditional re-test are still open).
- 07-14 (B2 retrain) depends on 07-12 and may now rewrite tracked data/models files.

## Self-Check: PASSED

- Files found: `read1_preflight.json`, both evidence directories (report.json, report.md, run_started.json, http/), tracked via `git ls-files`.
- Commits found in history: `e092d12`, `2115cfd`.
