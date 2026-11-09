---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 18
subsystem: live-promotion
tags: [reval-01, promotion, fast-forward-push, dlr-live, label-lift, owner-approval]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: 07-17 owner GO (go-forward-only), new RATING_BASIS, retrained models with manifest, per-city conductor table and v3 config
provides:
  - Phase 7's production changes on origin/main (e970549..682801d), pushed as a fast-forward with the owner's approval
  - one verified live run (41543992876) writing four rows with v3-powersystems-2026-11-02, new fingerprints, retrained model hashes and the new label
  - real_data_validation_p7.md "## Promotion" record
affects: [phase-8-day-ahead-cooling-forecast, shadow-collection, live-monitoring]

plan_head_before: 972a0e6ddd68c365b5375f663bd52658ac087a0a
plan_head_after: 2705bea2a694d3def833d030241a0916002ee6a8

actuals:
  tokens: 2500
  tasks: 3
  commits: 7

tech-stack:
  added: []
  patterns:
    - "merge-first promotion: when origin/main moved by teammate docs-only commits, merge it (no-ff, clean), re-run the pre-push checks, then fast-forward push"
    - "post-push verification through a session-scratch read-only script (counts and values only) plus the anon read path for is_provisional, because the writer role has no privilege on the latest_rating view"

key-files:
  created: []
  modified:
    - docs/data-science/decisions/real_data_validation_p7.md

key-decisions:
  - "Owner reply 'push' (2026-11-02T23:13Z) was treated as approving the merge-first step as well, as the owner was told beforehand"
  - "Task 3 (stored-row relabel) not applicable: 07-17 chose go-forward-only, so supabase/ops/lift_provisional_label.sql was not written"

requirements-completed: [REVAL-01]

coverage:
  - id: D1
    description: "Phase 7's reviewed commits reach origin/main as a fast-forward with the owner's approval, never forced"
    requirement: REVAL-01
    verification:
      - kind: other
        ref: "git merge-base --is-ancestor origin/main main (exit 0) before the push; git push origin main e970549..682801d"
        status: pass
    human_judgment: false
  - id: D2
    description: "First live run on the new code is green and its four rows carry the expected config_version, config_fingerprint, retrained model hashes and the new label; pipeline_run lists four cities_ok"
    requirement: REVAL-01
    verification:
      - kind: other
        ref: "gh run view 41543992876 (success); read-only scratch query of city_rating and pipeline_run for run 41543992876; backend/e2e_verify_readonly.py --check-read (E2E READONLY OK, is_provisional false on all four)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Promotion record committed in real_data_validation_p7.md"
    requirement: REVAL-01
    verification:
      - kind: other
        ref: "grep -c '^## Promotion' docs/data-science/decisions/real_data_validation_p7.md; grep -ciE 'postgres(ql)?://|pooler\\.supabase' (prints 0)"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 18: Promotion of Phase 7 to the live system Summary

**Phase 7's per-city conductors, retrained ml models, B5 fix and the label without the word "provisional" are live on origin/main, and the first live run (41543992876) wrote four verified rows with `is_provisional` false.**

## Performance

- **Duration:** about 15 min for this continuation (owner approval 23:13Z, push and dispatch 23:15Z, run finished about 23:18Z)
- **Tasks:** 3 (task 1 approved at the checkpoint, task 2 executed, task 3 not applicable)
- **Files modified:** 1 (`docs/data-science/decisions/real_data_validation_p7.md`)

## Accomplishments

- **Task 1 (owner approval):** reply "push" at 2026-11-02T23:13Z (UTC), after the owner was told that a merge of `origin/main` into `main` was needed first and that "push" approved that step.
- **Merge:** `origin/main` was still exactly the reviewed state (tip `e970549`, five teammate documentation-only commits from PRs #11 and #12 under `.planning/workstreams/input-provenance/`). `git merge --no-ff origin/main` was clean (`682801d`); main went from 147 ahead and 5 behind to 148 ahead and 0 behind.
- **Pre-push re-checks after the merge:** `dlr_live_check_models.py` OK for all 8 artifacts; `golden_shadow_capture.py --check` matched; `.github` unchanged against `origin/main`; `git merge-base --is-ancestor origin/main main` exit 0; `origin/main` re-fetched and unmoved right before the push.
- **Push:** `git push origin main` fast-forwarded `e970549..682801d` (no force).
- **Dispatch:** exactly one `gh workflow run dlr_live.yml --ref main` at 23:15:25Z, run id **41543992876**, head `682801d`. Result: success in 3 minutes; the step "Pre-flight - live model artifacts present and verified" passed with the new manifest.
- **Which run wrote the verified rows:** only run 41543992876. The hourly cron-job.org run of 23:05Z (id 41542570586) executed on the old head `e970549`, before the push; it wrote the same hourly slot (valid_time 23:00Z), and this run's upsert replaced those four rows, so every row for that slot now carries run id 41543992876. No second dispatch was made; the next scheduled run (00:05Z) will be the first hourly run on the new code.
- **Verification (read-only, counts and values only):** four rows (`origin = live`, valid_time 2026-11-02T23:00Z), all with `config_version` `v3-powersystems-2026-11-02`, `forecast_model_sha256` equal to the new manifest entry, `rating_basis` equal to `config.RATING_BASIS` (no "provisional" in it or in the version). Four distinct fingerprints (first 12): AUSTIN `c68d35482144`, CORPUS_CHRISTI `ac6981de3a7b`, EL_PASO `0a92b915d653`, MIDLAND `ea30ca4e48d0`. `pipeline_run` for the run lists all four cities in `cities_ok` (4), `cities_failed` empty. `latest_rating.is_provisional` is false for all four, read through the public path (`e2e_verify_readonly.py --check-read`: E2E READONLY OK, all rows fresh).
- **Task 3 (stored-row relabel):** not applicable. 07-17 chose `go-forward-only`; no stored row was relabelled, no backfill row was touched, and `supabase/ops/lift_provisional_label.sql` was not written.
- **Promotion record:** `## Promotion` section added to `real_data_validation_p7.md` (commit `2705bea`).

## Task Commits

1. **Task 1:** checkpoint (no commit); owner approval recorded above.
2. **Task 2:** merge commit `682801d` (merge of `origin/main`), then `2705bea` `docs(07-18): promotion record`.
3. **Task 3:** not applicable.

**Measured commits:** `git rev-list --count 972a0e6..2705bea` = 7 (this plan's own: the merge `682801d` and `2705bea`; the other five are the teammates' commits that arrived through the merge). The summary/state commit comes after this count.

## Deviations from Plan

### Auto-fixed Issues

None. One departure from the plan's wording, recorded as normal flow: the plan assumed local main was a pure fast-forward of origin/main; `origin/main` had moved by five teammate documentation-only commits, so a clean merge commit was made first (the owner approved this with "push" after being told). The push itself was still a fast-forward of `origin/main`.

**Total deviations:** 0 auto-fixed. **Impact:** none on the plan's goal.

## Auth gates

None. The workflow dispatch used the existing `gh` login.

## Issues Encountered

- The writer role cannot select from `public.latest_rating` (`InsufficientPrivilege`, expected: the view is for the public key). `is_provisional` was read through `e2e_verify_readonly.py --check-read` instead. A follow-up query in the same scratch script was aborted by that failed statement inside the read-only transaction; the rows needed were already printed, so it was not repeated.
- GitHub annotations on the run (Node.js 20 deprecation, ubuntu-latest label migration on 2026-10-19) are unrelated to this plan.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema change; the scratch verification script lived outside the repository and printed no connection string, host, user or project reference (the record greps clean).

## Next Phase Readiness

REVAL-01 is complete. Phase 7's remaining open item is the B4 follow-up (2026-11-30). The next hourly run (00:05Z) is the first unattended run on the new code; watching it stay green is the natural check.

## Self-Check: PASSED

- `docs/data-science/decisions/real_data_validation_p7.md` contains `## Promotion`: FOUND
- Commits `682801d` and `2705bea` are ancestors of HEAD and `682801d` is on origin/main: FOUND
- Run 41543992876 conclusion success: FOUND
