---
phase: 04-supabase-store-writer
plan: 09
subsystem: database
tags: [postgres, supabase, migration, check-constraint, github-actions, supply-chain, gap-closure]

requires:
  - phase: 04-supabase-store-writer
    provides: "applied migration 20261019000000_create_city_rating.sql, supabase_smoke.py, supabase_smoke.yml, city_rating_v1.md"
provides:
  - "additive migration 20261023000000 replacing the hour CHECK with a UTC-evaluated form (IN-06) and correcting the two run-log column comments (IN-03)"
  - "smoke checks session_timezone_utc and utc_hour_check_zone_independent (Asia/Kolkata accept/refuse pair)"
  - "supabase_smoke.yml pinned by commit SHA, credential-free checkout, main-only job (IN-05)"
affects: [04-12-owner-push, 05-scheduled-live-runs, 06-exposure-e2e]

actuals:
  tokens: 5500
  tasks: 3
  commits: 6

plan_head_before: e60f0693f7a0b132b7ba9c33ce6addef7a843cff
plan_head_after: 79b84764d9f9c8838e2a3af7e7dc52729afe5021
commits: 6

tech-stack:
  added: []
  patterns:
    - "Applied migrations are immutable (sha256 pinned by a test); fixes ship as new additive, re-appliable migrations"
    - "Live smoke tests apply the whole migration chain in name order, as production does"
    - "Actions pinned as owner/repo@<40-hex> # vX.Y.Z, resolved read-only from the official actions/* repositories"

key-files:
  created:
    - supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql
  modified:
    - backend/supabase_smoke.py
    - backend/tests/supabase_migration_test.py
    - backend/tests/supabase_smoke_test.py
    - .github/workflows/supabase_smoke.yml

key-decisions:
  - "IN-06: new additive migration (drop constraint if exists, then add) instead of editing the applied one; original pinned by sha256"
  - "IN-06: the smoke zone probe runs in a nested rolled-back savepoint with set local timezone, and uses the raw UPSERT_RATING_SQL for the refused insert because upsert_rating re-raises a redacted StoreError that hides the CheckViolation"
  - "IN-05: pin the commits the v4 and v5 tags pointed to on 2026-10-23, so workflow behavior is unchanged; the server-side control (protected environment with a main-only deployment-branch rule) is documented, not configured"

patterns-established:
  - "Effective column comments are computed over every migration in name order, later wins, and compared to the schema doc"

requirements-completed: [DB-01, DB-04, DB-05]

coverage:
  - id: D1
    description: "The hour CHECK is evaluated in UTC: in an Asia/Kolkata (UTC+05:30) writer session a whole UTC hour is accepted and 01:30Z is refused on city_rating_valid_time_hour_ck, once the new migration is applied"
    requirement: DB-01
    verification:
      - kind: unit
        ref: "backend/tests/supabase_smoke_test.py#test_hour_check_accepts_utc_hours_in_a_half_hour_offset_session"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_migration_test.py#test_review_fix_migration_makes_the_hour_check_zone_independent"
        status: pass
    human_judgment: false
  - id: D2
    description: "The original migration is byte-identical to its applied version, and the new migration only alters that one CHECK and two comments (no column, grant, policy, role or credential) and re-applies cleanly"
    requirement: DB-01
    verification:
      - kind: unit
        ref: "backend/tests/supabase_migration_test.py#test_original_migration_is_unchanged"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_migration_test.py#test_review_fix_migration_is_reapply_safe_and_grants_nothing"
        status: pass
    human_judgment: false
  - id: D3
    description: "supabase_smoke.py checks session_timezone_utc and utc_hour_check_zone_independent; against the original constraint the second check fails and the smoke exits 1 with every other check true"
    requirement: DB-04
    verification:
      - kind: unit
        ref: "backend/tests/supabase_smoke_test.py#test_smoke_passes_on_a_fresh_migration_and_leaves_no_rows"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_smoke_test.py#test_zone_check_fails_against_the_original_constraint"
        status: pass
    human_judgment: false
  - id: D4
    description: "The effective pipeline_run.cities_ok and cities_failed comments match the code and city_rating_v1.md (healthily; outcome error or degraded, written, forecast_status, detector_model_loaded, redacted error text)"
    requirement: DB-05
    verification:
      - kind: unit
        ref: "backend/tests/supabase_migration_test.py#test_run_log_comments_match_the_schema_doc"
        status: pass
    human_judgment: false
  - id: D5
    description: "The smoke workflow pins both actions by 40-hex SHA with a version comment, checks out with persist-credentials false, and its job runs only on refs/heads/main; trigger, permissions and secret mapping unchanged"
    requirement: DB-04
    verification:
      - kind: unit
        ref: "backend/tests/supabase_smoke_test.py#test_smoke_workflow_pins_actions_by_sha_and_runs_only_on_main"
        status: pass
      - kind: unit
        ref: "backend/tests/supabase_smoke_test.py#test_smoke_workflow_is_dispatch_only_and_passes_the_secret_by_env"
        status: pass
    human_judgment: false
  - id: D6
    description: "The migration and the workflow take effect on the live project and in CI only after the owner pushes them (plan 04-12); a live smoke against the real project then confirms the zone checks"
    requirement: DB-01
    verification: []
    human_judgment: true
    rationale: "Nothing is applied to or pushed at a real database or repository in this plan; the live effect is the owner's step in 04-12"

duration: 9min
completed: 2026-10-23
status: complete
---

# Phase 4 Plan 09: Schema and CI Gap Closure (G-04-2, IN-06, IN-03, IN-05) Summary

**A new additive migration makes the `city_rating` hour CHECK evaluate in UTC regardless of session zone (proved live with an Asia/Kolkata session), corrects the two run-log column comments, and the smoke workflow now pins its actions by commit SHA, drops the checkout token and runs only on main.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-10-23T21:49:04Z
- **Completed:** 2026-10-23T21:58:00Z
- **Tasks:** 3 (all TDD, RED then GREEN)
- **Files:** 1 created, 4 modified

## Accomplishments
- IN-06: `valid_time` slots mean the same in Studio, manual corrections and Phase 6 jobs. With only the original constraint, a +05:30 session refused the whole UTC hour 01:00Z; with the new one it is accepted and 01:30Z (a whole hour in Kolkata only) is refused on `city_rating_valid_time_hour_ck`.
- The smoke test now proves the zone pin (`session_timezone_utc`) and the constraint behavior (`utc_hour_check_zone_independent`) on any database it runs against, inside a rolled-back savepoint. It exits 1 against the original constraint.
- IN-03: Studio and `\d+` descriptions of `pipeline_run.cities_ok` and `cities_failed` now match what `build_run_row` stores and what `city_rating_v1.md` says.
- IN-05: the one job holding the production writer secret runs only pinned action code, keeps no git token, and is skipped on any branch but main.
- The applied migration is untouched: `shasum -a 256` prints `7fbf1423e0b8ccf0eee6f79e502036e11c8f3c4c9d54f6badddda0473f76129d`, and a test pins it.

## Task Commits

Each task committed atomically, failing-first:

1. **Task 1 (IN-06): zone-independent hour CHECK and smoke checks**
   - RED `3c24882` (test)
   - GREEN `655646d` (fix)
2. **Task 2 (IN-03): run-log column comments**
   - RED `8dd91be` (test)
   - GREEN `32cd1eb` (fix)
3. **Task 3 (IN-05): pinned, credential-free, main-only workflow**
   - RED `e23a2aa` (test)
   - GREEN `79b8476` (fix)

**Plan metadata:** the docs commit that adds this SUMMARY, then the state and roadmap commit.

## TDD Evidence (failing first)

RED evidence is pytest console output (no adapter for `gsd_run check tdd-red-evidence`), so the classifier was not run. Semantic assessment is by inspection: each new test executed and failed on the planned assertion for the intended reason, nothing failed on setup, import or collection.

**IN-06 (`3c24882`).** Offline: `test_review_fix_migration_makes_the_hour_check_zone_independent` and `test_review_fix_migration_is_reapply_safe_and_grants_nothing` failed with `FileNotFoundError` for the new migration (2 failed, 15 passed, 5 skipped; `test_original_migration_is_unchanged` passed, as expected, because the original is already correct and pinned). Live (`DLR_TEST_PG_AUTOSTART=1`): 3 failed, 5 passed. `test_smoke_passes_on_a_fresh_migration_and_leaves_no_rows` failed with `KeyError: 'session_timezone_utc'`; `test_hour_check_accepts_utc_hours_in_a_half_hour_offset_session` failed because the original constraint refused the whole UTC hour in a Kolkata session (`violates check constraint "city_rating_valid_time_hour_ck"`); `test_zone_check_fails_against_the_original_constraint` failed because the smoke exited 0 (`assert 0 == 1`). After `655646d`: offline 24 passed, 5 skipped; live 8 passed.

**IN-03 (`8dd91be`).** `test_run_log_comments_match_the_schema_doc` failed on `assert 'healthily' in 'none (labels): cities whose rating row was written.'` (the effective comments were still the originals). After `32cd1eb`: migration, schema-doc and secret-scan tests 25 passed.

**IN-05 (`e23a2aa`).** `test_smoke_workflow_pins_actions_by_sha_and_runs_only_on_main` failed on `- uses: actions/checkout@v4` not matching the SHA-plus-version form. After `79b8476`: smoke and secret-scan tests 7 passed, 5 skipped (live tests, run separately below).

## Resolved Action Pins

Resolved read-only with `gh api` on 2026-10-23 from the official repositories (the commit each currently used tag points to, plus the most specific release tag on that commit):

| Action | Was | Commit SHA | Tag on that commit |
|---|---|---|---|
| `actions/checkout` | `@v4` | `11d5960a326750d5838078e36cf38b85af677262` | `v4.4.0` (also `v4`) |
| `actions/setup-python` | `@v5` | `a26af69be951a213d495a4c3e4e4022e16d87065` | `v5.6.0` (also `v5`) |

## Verification

- `pytest -q backend/tests/supabase_migration_test.py backend/tests/supabase_smoke_test.py backend/tests/supabase_schema_doc_test.py` : passed (live tests skipped without the env gate).
- `DLR_TEST_PG_AUTOSTART=1 pytest -q backend/tests/supabase_smoke_test.py` against a private throwaway local Postgres: 9 passed, 0 skipped.
- Full suite `pytest -q -p no:cacheprovider`: 1532 passed, 48 skipped (the live Postgres modules other than the smoke test are env-gated).
- Acceptance greps: `grep -c "at time zone 'UTC'"` on the new migration prints 2; `grep -c "comment on column public.pipeline_run"` prints 2; `grep -cE "uses: [a-z-]+/[a-z-]+@[0-9a-f]{40} +# v[0-9]"` on the workflow prints 2; `git log origin/main..HEAD` contains three `fix(04-09)` commits (committed locally, not pushed).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] First attempt to resolve the action pins hit a shell quirk, not a network failure**
- **Found during:** Task 3
- **Issue:** The first `gh api` loop failed ("error connecting to api.github.com", then 404) because of a transient connectivity blip followed by zsh not word-splitting `$r`. No SHA was written from either failed attempt.
- **Fix:** Re-ran with an explicit function taking repo and tag as arguments; both SHAs and tags then resolved from the official repositories.
- **Files modified:** none
- **Commit:** n/a

**2. [Rule 1 - Bug] Task 1 acceptance grep counted lines, not occurrences**
- **Found during:** Task 1 acceptance check
- **Issue:** `grep -c "at time zone 'UTC'"` printed 1 because both occurrences are on the single `add constraint` line; the criterion requires 2 or more.
- **Fix:** The migration's explanatory comment now quotes the expression (`valid_time at time zone 'UTC'`), giving two matching lines. This amended the Task 1 GREEN commit before anything else was built on it (local only, never pushed), which is why its hash is `655646d`.
- **Files modified:** supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql
- **Commit:** 655646d

**Total deviations:** 2 auto-fixed (1 Rule 3, 1 Rule 1). **Impact:** none on scope or behavior.

## Authentication Gates

None.

## Issues Encountered

None open. Nothing was applied to or pushed at a real database or repository: the new migration and the hardened workflow are NOT live yet. They take effect when the owner runs `supabase db push --db-url` and pushes the workflow in plan 04-12; the smoke test run against the real project after that push is what confirms `utc_hour_check_zone_independent` there. Until the push, a real-project smoke run would report that check as FAILED (the live constraint is still the original form), which is the intended signal.

## Known Stubs

None.

## Threat Flags

None. The only new surface is a CHECK expression, two comments and tighter CI settings; no endpoint, auth path, file access or grant was added.

## Self-Check: PASSED

- FOUND: supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql
- FOUND: commits 3c24882, 655646d, 8dd91be, 32cd1eb, e23a2aa, 79b8476 (ancestors of HEAD)
- Original migration sha256 matches `7fbf1423e0b8ccf0eee6f79e502036e11c8f3c4c9d54f6badddda0473f76129d`
- `git rev-list --count e60f069..HEAD` measured 6 at SUMMARY write
