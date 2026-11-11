---
phase: 04-per-city-scaling-of-the-39-bus-case
plan: 01
subsystem: psse-mapping
tags: [pss-e, mapping, json-schema, validation, scaling, python]

requires:
  - phase: 02-real-pss-e-study
    provides: "psse_job.mapping (schema version 1), study.prepare_run, the fake psspy and the placeholder case"
provides:
  - "mapping schema version 2: a required per-city scaling block (load_mw, gen_mw, basis) parsed into CityMapping.scaling"
  - "mapping.Scaling, mapping.SCALING_BASES and the refusal of any missing or invalid block before any psspy call"
  - "a per-city duplicate-branch rule, so one line may serve every city's copy"
  - "the committed placeholder mapping as version 2 with synthetic targets"
affects: [04-02, 04-03, 04-04, 04-05, 04-06, per-city-scaling, study]

actuals:
  tokens: 4365
  tasks: 3
  commits: 3
plan_head_before: 197a68989b35de117ce8c7a7d459a4ecd82206ce
plan_head_after: c34d0e971d7e8618fa7577f4ba9cb4174162f2dc

tech-stack:
  added: []
  patterns:
    - "problem-list validation: every problem named at once, capped at MAX_PROBLEMS, no submitted value echoed"
    - "mutation check: plant the fault, see the named test go red, restore the file byte for byte"

key-files:
  created:
    - .planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/deferred-items.md
  modified:
    - backend/psse_job/mapping.py
    - backend/tests/psse_mapping_test.py
    - docs/data-science/schema/psse_mapping_example.json

key-decisions:
  - "Scaling targets are two numbers and one label per city; unknown keys (a load_mvar or a script key included) are refused, so the file cannot name a script or an .idv (CD-2, CD-9)"
  - "Refusal messages name the field and never the submitted value (PD-2, T-04-03)"
  - "The duplicate-branch memory is per city, so one line may be listed under several cities; a repeat inside one city, in either orientation, is still refused (CD-6, PD-4)"
  - "A number too large for a float (a 400-digit integer) is refused by the scaling check instead of raising OverflowError"

requirements-completed: [SCL-01]

coverage:
  - id: D1
    description: "Mapping schema version 2 requires a per-city scaling block and parses it into CityMapping.scaling; version 1 is refused with the version-2 message"
    requirement: SCL-01
    verification:
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_tracer_v2_scaling_block_reaches_the_study"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_rule_rejects_bad_input[schema_one]"
        status: pass
    human_judgment: false
  - id: D2
    description: "Every invalid scaling block (missing, wrong type, unknown key, bad number, infinity, huge integer, bad basis) is refused with all problems named at once and no submitted value in the text"
    requirement: SCL-01
    verification:
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_rule_rejects_bad_input (15 scaling_* rows)"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_scaling_infinity_is_refused"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_scaling_problems_reported_together"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_scaling_refusal_never_echoes_a_value"
        status: pass
    human_judgment: false
  - id: D3
    description: "A mapping refused for its scaling block fails the study at stage mapping with no psspy call"
    requirement: SCL-01
    verification:
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_scaling_block_refused_before_any_psspy_call"
        status: pass
    human_judgment: false
  - id: D4
    description: "The same branch may be listed under several cities, twice in one city is refused in either orientation, and mapping_sha256 moves with every target"
    verification:
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_same_branch_allowed_in_several_cities"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_same_branch_twice_in_one_city_refused"
        status: pass
      - kind: unit
        ref: "backend/tests/psse_mapping_test.py#test_sha256_follows_every_target"
        status: pass
    human_judgment: false
  - id: D5
    description: "Whether CD-6 (the same lines in every city's copy) matches Power Systems' real mapping is not something a test can establish"
    verification: []
    human_judgment: true
    rationale: "CD-6 is still to be confirmed by Power Systems; only they can say whether the real mapping shares lines across cities"

duration: 33min
completed: 2026-11-10
status: complete
---

# Phase 4 Plan 01: Mapping schema version 2 with per-city scaling Summary

**Mapping schema version 2 requires a per-city scaling block (target load MW, target generation MW, average or peak basis), refuses any bad block before a single psspy call without echoing a number, and lets one line serve every city's copy.**

## Performance

- **Duration:** 33 min (about 16 of them waiting for the Postgres-backed gate)
- **Started:** 2026-11-11T02:53Z (20:53 local)
- **Completed:** 2026-11-11T03:26Z (21:26 local)
- **Tasks:** 3
- **Files modified:** 3 source files plus this summary and a deferred-items note

## Accomplishments

- `mapping.SCHEMA_VERSION` is 2; `load_mapping` accepts only version 2 and refuses version 1 with `schema_version: must be the integer 2 (version 2 adds the per-city scaling block)`.
- `mapping.Scaling(load_mw, gen_mw, basis)`, `SCALING_BASES == ("average", "peak")` and `CityMapping.scaling` (the last field). `_parse_scaling` refuses a missing block, a non-object, a missing key, any unknown key (`load_mvar` and a script key included), a zero, negative, text, boolean, null, infinite or over-large number, and an unknown basis, all at once.
- No refusal text repeats a submitted value; the study turns a refused block into a `mapping` stage failure with `fake.fake_calls == []`.
- The committed example is version 2, `placeholder: true`, with the plan's synthetic targets on the same fake 9xxxx buses; the whole study (prepare_run, four dispatch and four margin rows, `validate_results`) still runs on it unchanged.
- The duplicate-branch memory moved inside `_parse_city`; the same line can be listed under several cities, a repeat in one city is refused (`branch <key> is listed twice in this city`).

## Task Commits

1. **Task 1: Tracer, version 2 mapping with scaling reaches CityMapping.scaling and the study** - `d1dbccd` (feat)
2. **Task 2: Every invalid scaling block refused at once, no value echoed, no psspy call** - `98a916d` (test)
3. **Task 3: Same line may serve several cities, twice in one city refused, hash follows every target** - `c34d0e9` (feat)

**Plan metadata:** the commit holding this summary (docs: complete plan).

## TDD evidence

- **Task 1 RED:** the new `test_tracer_v2_scaling_block_reaches_the_study` and the flipped version pins failed on their planned assertions: `assert 1 == 2` on `loaded.schema_version` (6 failed, 96 passed in `psse_mapping_test.py`). The target failed on the assertion for the planned behavior, not on an import or syntax fault. GREEN: the same file, 101 passed.
- **Task 3 RED:** `test_same_branch_allowed_in_several_cities` failed with `MappingError ... is already listed under AUSTIN` and `test_same_branch_twice_in_one_city_refused` with the old message text; `test_sha256_follows_every_target` was already green because the hash is the hash of the bytes (a characterization test, kept). GREEN: 193 passed across mapping, study, probe and contract tests.
- **Task 2 had no separate RED run:** the strict `_parse_scaling` was written in Task 1, so every Task 2 test was green on its first run. The mutation checks below stand in for it: each planted fault turns the named test red.
- The RED evidence was not run through `gsd_run check tdd-red-evidence`: the plan is `type: execute` and `workflow.tdd_mode` is not enabled.

## Mutation checks (plant, see red, restore byte for byte; `git diff --quiet` on mapping.py passed after each)

| Planted fault | Test that went red |
|---|---|
| accept version 1 | `test_rule_rejects_bad_input[schema_one]` |
| let a missing block through | `test_rule_rejects_bad_input[scaling_missing]` and `test_scaling_block_refused_before_any_psspy_call` |
| accept a `load_mvar` key | `test_rule_rejects_bad_input[scaling_key_load_mvar]` |
| put the value into the finite-number message | `test_scaling_refusal_never_echoes_a_value` |
| restore a shared cross-city `seen` | `test_same_branch_allowed_in_several_cities` |

## Message text

Every message matches PD-2 and PD-4 exactly; none differs. Added beyond them: none.

## Files Created/Modified

- `backend/psse_job/mapping.py` - version 2, `Scaling`, `SCALING_BASES`, `_SCALING_KEYS`, `_positive_finite`, `_parse_scaling`, the scaling field, the per-city duplicate rule, updated docstring
- `backend/tests/psse_mapping_test.py` - version pins flipped, tracer, 15 scaling rows, infinity, huge integer, together, no-echo, before-psspy, several-cities, twice-in-one-city and hash tests; row count test now 57
- `docs/data-science/schema/psse_mapping_example.json` - version 2 placeholder with the synthetic scaling blocks and a note of under 200 characters
- `.planning/workstreams/pss-e-integration/phases/04-per-city-scaling-of-the-39-bus-case/deferred-items.md` - the one out-of-scope finding

## Decisions Made

- Followed the plan's locked decisions (CD-1 to CD-10, PD-1 to PD-4) as written.
- Kept one commit per task as the plan's commit lines specify, so a TDD task's test and code land together rather than as a separate `test(...)` then `feat(...)` pair.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] An over-large integer must not crash the parser**
- **Found during:** Task 1 (writing `_parse_scaling`)
- **Issue:** `math.isfinite(10**400)` raises `OverflowError`, which would escape `parse_mapping` as a non-`MappingError` and could stop the launcher without a `mapping` stage failure. The plan said to reuse the `transfer_max_mw` test, which has this flaw.
- **Fix:** a small `_positive_finite` helper that returns False on `OverflowError`, used by the scaling targets only; `test_scaling_huge_integer_is_refused_not_a_crash` pins it.
- **Files modified:** `backend/psse_job/mapping.py`, `backend/tests/psse_mapping_test.py`
- **Committed in:** `d1dbccd` (code), `98a916d` (test)

**2. [Rule 3 - Blocking] Existing test rows adjusted for the new version**
- **Found during:** Task 1 and 2
- **Issue:** the duplicate-key row replaced bytes of `"schema_version": 1`, and the count test pinned 42 rows.
- **Fix:** the byte replace now targets version 2; `schema_two` became `schema_one` with the full PD-2 message; the text-version row now uses `"2"`; the count test is now `test_rule_case_count_is_57`.
- **Files modified:** `backend/tests/psse_mapping_test.py`
- **Committed in:** `d1dbccd`, `98a916d`

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking)
**Impact on plan:** no scope creep; the over-large-integer guard is one helper and one test.

## Issues Encountered

- **Wave-end gate not clean (environmental, not from this plan).** `psse_*_test.py` plus `secret_scan_test.py` with the plan's PATH and flags gave `2 failed, 685 passed, 1 skipped, 19 errors`, run twice with the same result. Every failure and error is in `backend/tests/psse_results_migration_test.py` (a file this plan must not touch, with no reference to the mapping): its Postgres fixture could not start, and the server log shows `FATAL: could not create lock file "''/.s.PGSQL.<port>.lock": No such file or directory`, from the `unix_socket_directories=''` option on Windows. The Postgres-backed study, job and writer tests ran and passed (`psse_study_job_test.py` runs `prepare_run` on the new example under a real database). The one skip is the owner-local `secret_scan_test.py` check that needs Supabase environment variables. The gate as the plan words it ("exits 0 with no skipped test") therefore does not pass on this laptop; the cause predates the plan and was not investigated further.
- The `-k` selectors in the plan's acceptance criteria are satisfied: `tracer_v2` 1 passed, the four Task 2 names 4 passed, the three Task 3 names 3 passed.

## Pre-existing finding (not fixed)

`transfer_max_mw` still raises `OverflowError` for an over-large integer; logged in `deferred-items.md`.

## State files not updated (plan rule C-4)

The plan forbids editing STATE.md, ROADMAP.md and REQUIREMENTS.md, and says to leave `.planning/config.json` and `milestone.lock` uncommitted. This executor therefore did not run `state.advance-plan`, `roadmap.update-plan-progress` or `requirements.mark-complete` (SCL-01 is still to be marked by the orchestrator). The existing uncommitted STATE.md and state.json edits are not mine and were left as found.

## User Setup Required

None - no external service configuration required.

## Known Stubs

None.

## Threat Flags

None - no new network, auth, file-access or schema surface beyond the plan's threat model (T-04-01 to T-04-03 mitigated: only synthetic targets committed, hostile blocks refused, no value echoed).

## Next Phase Readiness

- Plans 04-02 to 04-05 can read `CityMapping.scaling` and the synthetic target table; the study itself does not read the block until plan 04-03.
- Real targets must be added to the private mapping on the laptop as version 2 before the next real run; the old version 1 private file is now refused by design.
- CD-6 (the same lines in every city's copy) still needs Power Systems' confirmation.

## Self-Check: PASSED

- Files exist: `backend/psse_job/mapping.py`, `backend/tests/psse_mapping_test.py`, `docs/data-science/schema/psse_mapping_example.json`, `deferred-items.md`.
- Commits `d1dbccd`, `98a916d`, `c34d0e9` are ancestors of HEAD; `git rev-list --count 197a689..HEAD` was 3 before this summary's commit.
- Own-changes gate (PLAN=04-01) exited 0 after each commit.
- Plan-level verification: 244 passed across mapping, study, api, probe, study_doc and contract tests.

---
*Phase: 04-per-city-scaling-of-the-39-bus-case*
*Completed: 2026-11-10*
