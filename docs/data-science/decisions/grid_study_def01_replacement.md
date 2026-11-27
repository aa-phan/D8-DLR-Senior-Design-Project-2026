# DEF-01 replacement text: grid-study results per city and solver

| | |
|---|---|
| **Status** | Not handed over yet |
| **Applied live** | {{APPLY_DATE}} |
| **From** | the Data Science owner, pandapower-solver workstream (phase 6, VIEW-03) |
| **To** | the dashboard owner (Aaron Phan), software-dashboard workstream, branch `feature/dashboard` |
| **Hand over after** | the owner applies `supabase/migrations/20261126200000_latest_grid_study_per_solver.sql` to the live project after the Phase 5 soak and the three read-only checks return 6, 7 and 37, all ok; then `{{APPLY_DATE}}` is replaced by that date (UTC) |
| **Written against** | `origin/feature/dashboard` at commit 1f531f8 (2026-11-25) |

Scope: three statements about DEF-01 (grid-study results) in the software-dashboard workstream that go out of date when the per-solver view is applied. Nothing else in those files changes. The view itself, its columns and its checks are recorded in the migration header and in `docs/integration/rest-api.md`.

## How to apply

1. Re-read the three files on `feature/dashboard` first. The blocks below were written against the commit named in the header table; if a file has changed since, match the current text by meaning and tell the Data Science owner.
2. In each of Blocks A and C, replace the exact text under "Current text" with the text under "Replacement text". In Block B, keep the 2026-11-16 line and add the new line directly after it.
3. Do this only after the Status row above reads `Ready to hand over` and `{{APPLY_DATE}}` no longer appears in this document. Until then the replacement texts would claim figures that are not readable yet.
4. Commit on `feature/dashboard` with your usual message. VIEW-03 of the pandapower-solver workstream closes only when that commit is on the branch.

This repository never edits `feature/dashboard`: it only reads the branch to check the quoted texts (see "Confirmation").

## Block A: `.planning/workstreams/software-dashboard/REQUIREMENTS.md`, section `## Deferred`

**Current text:**

```text
- **DEF-01**: Grid-study results (usable share of the rating and its limiting factor) per city.
  Unblocked 2026-11-16: read `latest_grid_study` with the dashboard's key; preliminary values,
  stale while the PSS/E job is paused (ch. 10).
```

**Replacement text:**

```text
- **DEF-01**: Grid-study results (usable share of the rating and its limiting factor) per city.
  Blockers cleared on {{APPLY_DATE}}: the dashboard's key can read the view `latest_grid_study`
  (migration `20261126200000_latest_grid_study_per_solver.sql`) and nothing else of the result
  tables, which stay private; since then the study also runs hourly on pandapower, next to PSS/E.
  The view returns one row per city per solver (at most 8 rows), so a reader must filter on
  `solver` (`psse` or `pandapower`) rather than assume one row per city. Its 20 columns, in order:
  `solver`, `city`, `slot_time`, `study_finished_at`, `run_outcome`, `rating_source`,
  `fallback_reason`, `city_rating_valid_time`, `applied_amps_per_conductor`,
  `dispatched_amps_per_conductor`, `subconductors_per_phase`, `line_voltage_kv`, `applied_mva`,
  `voltage_limit_mva`, `dispatched_mva`, `dispatched_mw`, `usable_pct`, `limiting_factor`,
  `age_minutes`, `is_stale`. Values are preliminary: the public IEEE 39-bus case scaled per city,
  not a utility network, not reviewed by Power Systems. A result is stale when its hour is more than
  90 minutes old; a PSS/E row is stale while that job is paused. Still deferred from the first
  release (ch. 10).
```

## Block B: `.planning/workstreams/software-dashboard/STATE.md`, section `### Decisions`

**Current text (keep it):**

```text
- 2026-11-16: DEF-01 unblocked. The Data Science owner exposed the view `latest_grid_study` to the dashboard's key (the result tables stay private) and 19 real PSS/E runs exist. Still deferred from the first release; values are preliminary.
```

**Add this line directly after it:**

```text
- {{APPLY_DATE}}: DEF-01 blockers cleared for both solvers. The Data Science owner replaced the view `latest_grid_study` (migration `20261126200000_latest_grid_study_per_solver.sql`); it returns the newest complete result per city per solver (`psse` and `pandapower`, at most 8 rows), so a reader filters on `solver`. pandapower rows refresh hourly; PSS/E rows are stale while that job is paused. Still deferred from the first release; values are preliminary.
```

## Block C: `.planning/workstreams/software-dashboard/docs/DASHBOARD-REQUIREMENTS.md`, chapter 10

Chapter 10 states that it wins where the requirements checklist disagrees, so it must change with Block A. The two paragraphs below are consecutive, with one blank line between them; the bullet `**DEF-01**` above them stays.

**Current text:**

```text
**Unblocked on 2026-11-16.** Both blockers are cleared. First, the Data Science owner opened read access: the view `latest_grid_study` (migration `20261116200000_expose_latest_grid_study.sql`) is readable with the dashboard's key, while the four result tables stay private. Second, the study job has run on real PSS/E: 19 runs were written on 2026-11-11 and 2026-11-12, on the public IEEE 39-bus test case scaled per city.

What to read: `GET /rest/v1/latest_grid_study`, up to one row per city per solver from the newest complete run, with `usable_pct`, `limiting_factor`, `dispatched_amps_per_conductor`, `applied_amps_per_conductor`, `slot_time`, `age_minutes` and `is_stale` among its 20 columns. The column table and the display rules are in the "Grid-study results (preliminary)" section of [`rest-api.md`](../../../../docs/integration/rest-api.md). Three things to design for: every value is preliminary (show the label the contract gives), the PSS/E job is paused so every row is stale today (show the study time and a "Study not current" state), and an open-source solver (pandapower) will add hourly rows later, told apart by the `solver` column. Nothing is built for it in the first release, and the layout does not reserve space for it; the Software team decides when to take it up.
```

**Replacement text:**

```text
**Unblocked on 2026-11-16; one row per city per solver since {{APPLY_DATE}}.** Both blockers are cleared. First, the Data Science owner opened read access: the view `latest_grid_study` (migration `20261116200000_expose_latest_grid_study.sql`) is readable with the dashboard's key, while the four result tables stay private. Second, the study job has run on real PSS/E: 19 runs were written on 2026-11-11 and 2026-11-12, on the public IEEE 39-bus test case scaled per city. Since {{APPLY_DATE}}, migration `20261126200000_latest_grid_study_per_solver.sql` has replaced the view so that it returns each solver's newest complete result, and pandapower runs the same study every hour.

What to read: `GET /rest/v1/latest_grid_study`, one row per city per solver (at most 8 rows), each from that solver's newest complete run, with `usable_pct`, `limiting_factor`, `dispatched_amps_per_conductor`, `applied_amps_per_conductor`, `slot_time`, `age_minutes` and `is_stale` among its 20 columns. The column table and the display rules are in the "Grid-study results (preliminary)" section of [`rest-api.md`](../../../../docs/integration/rest-api.md). Three things to design for: every value is preliminary (show the label the contract gives); rows of both solvers are told apart by `solver` (`psse` or `pandapower`), so filter on it rather than assume one row per city; and a row is stale when its hour is more than 90 minutes old, so PSS/E rows stay stale while that job is paused, while pandapower rows refresh hourly (show the study time and a "Study not current" state). Nothing is built for it in the first release, and the layout does not reserve space for it; the Software team decides when to take it up.
```

## Confirmation

The Data Science owner runs these after the hand-over (read-only; they never write to the branch):

```text
git fetch origin feature/dashboard
MSYS_NO_PATHCONV=1 git show "origin/feature/dashboard:.planning/workstreams/software-dashboard/REQUIREMENTS.md" | grep -n "20261126200000_latest_grid_study_per_solver.sql"
MSYS_NO_PATHCONV=1 git show "origin/feature/dashboard:.planning/workstreams/software-dashboard/STATE.md" | grep -n "20261126200000_latest_grid_study_per_solver.sql"
MSYS_NO_PATHCONV=1 git show "origin/feature/dashboard:.planning/workstreams/software-dashboard/docs/DASHBOARD-REQUIREMENTS.md" | grep -n "20261126200000_latest_grid_study_per_solver.sql"
DEF01_REQUIRE_BRANCH=1 DEF01_EXPECT=committed .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/grid_study_def01_text_test.py -k dashboard_branch
```

Each `grep` prints one or more lines: the migration name appears only in the replacements, never in the current texts. The test passes only when the placeholder is gone from this document, Blocks A and C are on the branch and their old texts are not, and Block B shows both the kept line and the added line. Before the hand-over, `DEF01_EXPECT=current` shows the quoted current texts still match the branch.

## Why the text says what it says

- The blockers are cleared, the view is `latest_grid_study`, and its columns are named: decision D-04 of phase 6.
- One row per city per solver, so a reader filters on `solver`: the view definition in `supabase/migrations/20261126200000_latest_grid_study_per_solver.sql` (decision D-01); at most 8 rows is four cities times two solvers (`MAX_ROWS` in `backend/grid_study_contract.py`).
- The 20 columns and their order come from `COLUMNS` in `backend/grid_study_contract.py`; a test checks Block A against that list.
- Values are preliminary, on the public IEEE 39-bus case scaled per city: the label of `docs/integration/rest-api.md`, section "Grid-study results (preliminary)".
- A result is stale when its hour is more than 90 minutes old (`STALE_AFTER_MINUTES` in the same contract file); a PSS/E row stays stale while that job is paused.
- Three blocks, not two: chapter 10 of the dashboard requirements states that it wins on disagreement and would otherwise still say every row is stale and pandapower rows come later (decision D-07).
- The apply-date placeholder and this tracked location: until the owner applies the migration live, the text must not say pandapower rows are readable or give a date; the tracked copy survives a clean branch that filters `.planning` commits (decision D-08).
- The 2026-11-11, 2026-11-12 and 2026-11-16 dates are quoted from the current texts; no other date is written before the apply.
