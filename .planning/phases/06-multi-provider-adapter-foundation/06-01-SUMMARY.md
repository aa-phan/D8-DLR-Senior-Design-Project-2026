---
phase: 06-multi-provider-adapter-foundation
plan: 01
subsystem: data-contract
tags: [pandas, pytest, pipeline-schema, tdd]

# Dependency graph
requires:
  - phase: 04-predictive
    provides: PIPELINE_SCHEMA v2 (forecast/anomaly columns), the additive-only extension pattern this plan reuses for v3
provides:
  - "PIPELINE_SCHEMA v3: four categorical per-field provenance columns (wind_source, temp_source, humidity_source, solar_source)"
  - "units_def.KNOWN_PROVIDER_NAMES registry — the one place Phases 7-10 register a new provider name"
  - "validate_pipeline_row categorical branch — validates a string-valued column by membership instead of numeric range"
  - "weather_provider.attach_provenance — tags a weather frame with its supplying provider, never inferring or defaulting"
affects: [07-trivial-providers, 08-nsrdb, 09-tceq, 10-synoptic-fallback]

# Actuals (#2632)
actuals:
  tokens: 4494
  tasks: 3
  commits: 4

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Categorical schema entries: {\"unit\": \"categorical\", \"range\": None, \"allowed_values\": frozenset} validated by membership, not by numeric range"
    - "TDD RED/GREEN as two separate git commits: implementation temporarily reverted (git checkout -- <files> after saving a patch), tests run and confirmed failing, committed, then the saved patch reapplied and tests re-run to confirm passing before the GREEN commit"

key-files:
  created:
    - backend/tests/weather_provider_test.py
  modified:
    - backend/units_def.py
    - backend/weather_provider.py
    - backend/tests/units_def_test.py

key-decisions:
  - "Task 1 checkpoint:decision resolved as Option A (categorical schema shape with allowed_values) via orchestrator continuation context, with the four column names and initial KNOWN_PROVIDER_NAMES membership exactly as originally proposed."
  - "Bumping PIPELINE_SCHEMA_VERSION broke two pre-existing Phase 4 tests (hardcoded version==2, and a v2-key-diff that started including the new v3 keys); fixed both minimally in Task 2 rather than deferring to Task 3, since Task 2's own <verify> block requires units_def_test.py to pass with zero failures."

patterns-established:
  - "PROVENANCE_FIELD_MAP: dict mapping a provenance column name to the tuple of underlying data columns it tracks — the single seam a future provider wires through without touching validate_pipeline_row."

requirements-completed: [WX-05, WX-07]

coverage:
  - id: D1
    description: "PIPELINE_SCHEMA bumped to v3 with four new required=False categorical provenance columns; all 15 pre-existing entries byte-identical"
    requirement: "WX-07"
    verification:
      - kind: unit
        ref: "backend/tests/units_def_test.py#test_schema_version_bumped_to_v3_and_v2_columns_are_byte_identical"
        status: pass
      - kind: unit
        ref: "backend/tests/units_def_test.py#test_v3_columns_are_all_optional"
        status: pass
    human_judgment: false
  - id: D2
    description: "validate_pipeline_row validates a categorical (string-valued) provenance column by membership check instead of crashing on the numeric range path; an unregistered value produces exactly one error naming the column"
    requirement: "WX-07"
    verification:
      - kind: unit
        ref: "backend/tests/units_def_test.py#test_row_with_valid_provenance_columns_validates"
        status: pass
      - kind: unit
        ref: "backend/tests/units_def_test.py#test_unknown_provenance_value_produces_one_error_naming_the_column"
        status: pass
      - kind: unit
        ref: "backend/tests/units_def_test.py#test_pre_phase6_row_still_validates"
        status: pass
    human_judgment: false
  - id: D3
    description: "fetch_weather's station path returns rows tagged with their supplying provider in all four provenance columns, with an absent/null source left None rather than inferred or defaulted"
    requirement: "WX-05"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_station_fetch_end_to_end_row_carries_provenance_and_validates"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_provenance_is_none_where_the_underlying_field_is_absent"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_provenance_is_none_where_the_underlying_value_is_null"
        status: pass
    human_judgment: false
  - id: D4
    description: "attach_provenance never mutates its argument, rejects an unregistered provider name with a ValueError naming it, and importing weather_provider has no side effects"
    verification:
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_attach_provenance_does_not_mutate_its_argument"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_attach_provenance_rejects_an_unregistered_provider_name"
        status: pass
      - kind: unit
        ref: "backend/tests/weather_provider_test.py#test_module_import_has_no_side_effects"
        status: pass
    human_judgment: false

duration: 35min
completed: 2026-09-10
status: complete
---

# Phase 6 Plan 01: Provenance Schema Foundation Summary

**PIPELINE_SCHEMA v3 adds four categorical per-field provenance columns (wind_source, temp_source, humidity_source, solar_source), validated by allowed_values membership, and `weather_provider.attach_provenance` tags synoptic station fetches with their source end-to-end.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3 (1 decision checkpoint resolved via continuation, 2 executed)
- **Files modified:** 4 (1 created, 3 modified)

## Decision

**Task 1 — checkpoint:decision, resolved.** Per the orchestrator's continuation context, the user selected **Option A**: categorical schema entries carrying `"unit": "categorical"`, `"range": None`, `"allowed_values": KNOWN_PROVIDER_NAMES`; `validate_pipeline_row` branches on `spec.get("unit") == "categorical"` and checks membership instead of running the numeric `float(np.mean(value))` range check on that column.

- **Column names:** `wind_source`, `temp_source`, `humidity_source`, `solar_source` — exactly as proposed, no change requested.
- **Initial `KNOWN_PROVIDER_NAMES` membership:** `"synoptic"`, `"tceq"`, `"asos"`, `"nsrdb"`, `"open_meteo"` — exactly as proposed, no change requested.

This choice was one-way per `PIPELINE_SCHEMA`'s additive-only rule (units_def.py's own comment block) — once written, these four column names and the categorical spec shape become a contract every downstream consumer and every Phase 7-10 provider reads.

## Accomplishments

- `PIPELINE_SCHEMA_VERSION` bumped 2 → 3; four new `required: False` categorical columns added, all 15 pre-existing entries byte-identical.
- `units_def.KNOWN_PROVIDER_NAMES` frozenset registry — the single place a future provider (Phases 7-10) is registered.
- `validate_pipeline_row` gained a categorical branch: a typo'd provider name is reported as one error naming the column; a numeric value wrongly written into a provenance column is reported instead of crashing on `lo, hi = None`.
- `weather_provider.attach_provenance(frame, provider, *, field_map=PROVENANCE_FIELD_MAP)` — copies the frame, tags each provenance column with the supplying provider only where the mapped source column(s) are present and non-null for that row, never inferred/defaulted/carried across rows. Wired into `fetch_weather`'s existing `"synoptic"` branch.
- `backend/tests/weather_provider_test.py` (new, 6 tests) proves the whole vertical slice end to end: a `fetch_weather(["KAUS"], ...)` call (with `dlr_pipeline.fetch_timeseries` monkeypatched) returns rows that validate cleanly against `PIPELINE_SCHEMA` v3.
- `backend/tests/units_def_test.py` gained a new Task 3 pytest section: a hand-transcribed `_V2_SCHEMA_SNAPSHOT` (15 entries) and 6 tests freezing the v3 version bump, the four-new-optional-columns guarantee, a v2-era row still validating, a fully-provenanced row validating, an unregistered provenance value producing one error, and the four v3 entries declaring `allowed_values` rather than a range.
- Full suite: **167 passed, 0 failed** (up from a 155-passed pre-phase baseline).

## Task Commits

Each task was committed atomically. Task 2 (TDD tracer) produced two commits (RED, then GREEN) rather than one, since the plan required proving RED with a real test run before implementing:

1. **Task 1: Confirm the v3 provenance schema shape** — no code changes; decision recorded above (resolved via continuation context, not a new commit).
2. **Task 2 (RED): failing tests for provenance schema and adapter** — `d3d5be6` (test)
3. **Task 2 (GREEN): PIPELINE_SCHEMA v3 + attach_provenance implementation** — `45721f2` (feat)
4. **Task 3: freeze v2 schema, pin v3 additive-only guarantees** — `247145d` (test)

**Plan metadata:** committed separately per the parallel-execution contract (SUMMARY.md + ACKNOWLEDGEMENTS.md).

## Files Created/Modified

- `backend/units_def.py` — `KNOWN_PROVIDER_NAMES`, `PIPELINE_SCHEMA_VERSION = 3`, four v3 categorical entries, categorical branch in `validate_pipeline_row`
- `backend/weather_provider.py` — `import units_def`, `PROVENANCE_FIELD_MAP`, `attach_provenance()`, wired into `fetch_weather`'s synoptic branch
- `backend/tests/weather_provider_test.py` — new file; 6 tests, end-to-end provenance tracer plus `attach_provenance` unit tests
- `backend/tests/units_def_test.py` — 2 pre-existing Phase 4 tests updated for the v3 bump (Task 2, deviation below); new Task 3 pytest section with `_V2_SCHEMA_SNAPSHOT` and 6 tests

## Decisions Made

See "Decision" section above for the Task 1 checkpoint resolution. No other architectural decisions were required — Task 2 and Task 3 implemented the plan's `<action>` text directly.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated two pre-existing Phase 4 tests broken by the v3 version bump**
- **Found during:** Task 2 (implementing the schema bump)
- **Issue:** Bumping `PIPELINE_SCHEMA_VERSION` from 2 to 3 broke `test_schema_version_bumped_and_v1_columns_are_byte_identical` (hardcoded `== 2`) and `test_v2_columns_are_all_optional` (its key-diff against `_V1_SCHEMA_SNAPSHOT` started including the four new v3 keys, since nothing excluded them). Task 2's own `<verify>` block runs `units_def_test.py` and requires zero failures, so this was a genuine blocker for finishing Task 2 as specified, not an optional cleanup.
- **Fix:** Updated the version literal to 3 in the first test (the guarantee it pins — v1 columns stay byte-identical across additive bumps — is unaffected by which version number is current); updated the second test to exclude the four known v3 keys from its `v2_keys` diff, so it continues checking specifically the original five v2 (Phase 4) keys. Task 3's own acceptance criteria explicitly permit this ("either updated for the version bump or left passing" — as opposed to deleted).
- **Files modified:** `backend/tests/units_def_test.py`
- **Verification:** `pytest backend/tests/weather_provider_test.py backend/tests/units_def_test.py -q` → 11 passed, 0 failed; full suite 161 passed after Task 2, 167 after Task 3.
- **Committed in:** `45721f2` (Task 2 GREEN commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary for Task 2's own verify gate to pass; no scope creep — both edits are minimal literal/set adjustments to tests the schema bump directly invalidated, and Task 3 supersedes them with the full freeze/snapshot as planned.

## Issues Encountered

**Worktree branch was stale at spawn time.** The assigned worktree's branch (`worktree-agent-ac0ead8b18f032e23`) was based on an older point on `origin/main` that predated the entire Phase 6 planning session — `.planning/phases/06-multi-provider-adapter-foundation/` did not exist in the worktree. Verified the worktree tip was a strict ancestor of the shared repo's local `main` (no unique worktree commits, safe to fast-forward) before running `git merge --ff-only main`. This is the same non-destructive recovery pattern used by prior worktree-executor sessions per `ACKNOWLEDGEMENTS.md`.

**No `.venv` in the worktree.** Python virtualenvs are gitignored and not shared across git worktrees by git itself. Rather than creating a duplicate `.venv`, every `pytest`/`python` invocation in this session used the shared `.venv` at the main checkout's absolute path (`/Users/aphan/Documents/Senior_Design/.venv/bin/python`), consistent with how the plan's own `<verify>` commands are written (`.venv/bin/python ...`).

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `PIPELINE_SCHEMA` v3 and `KNOWN_PROVIDER_NAMES` are the stable contract Plans 06-02 (dispatch/signature redesign) and 06-03 (merge) build on, and the one place Phases 7-10 register a new provider name.
- `attach_provenance`'s `field_map` parameter is the seam a future provider wires through without touching `validate_pipeline_row` or the schema shape again.
- WX-05 is partially delivered (provenance emission on the station path only); dispatch and merge across multiple providers are Plan 06-02/06-03's job.
- No blockers identified for Plan 06-02.

---
*Phase: 06-multi-provider-adapter-foundation*
*Completed: 2026-09-10*
