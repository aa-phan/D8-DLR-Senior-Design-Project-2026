---
phase: 05-shadow-collector-five-method-side-by-side-challenger-recordi
plan: 01
subsystem: data-contract
tags: [jsonl, schema-migration, shadow-collector, checkpoint-decision]

# Dependency graph
requires: []
provides:
  - "The approved, verbatim nested-per-candidate JSONL schema (schema_version 2) for the shadow collector's five-candidate recording"
  - "The approved historical-data strategy: no migration of already-committed flat-shape rows"
  - "The approved six-field legacy mirror rule for `ml_wind_corrected`, confirmed against `forecast_shadow_healthcheck.py`'s actual top-level field reads"
affects: [05-02, 05-03, 05-04, 05-05]

# Actuals (#2632)
actuals:
  tokens: 1800
  tasks: 1
  commits: 1

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "schema_version-keyed JSONL coexistence: new-shape rows accrue alongside old-shape rows in the same append-only .jsonl files forever; readers branch on `entry.get('schema_version', 1) >= 2`"
    - "Exact-mirror backward compatibility: a legacy top-level field set is byte-for-byte copied from one named nested candidate's own fields (including its null/failed state), never silently substituted from a different candidate"

key-files:
  created:
    - ".planning/workstreams/ml-modeling/phases/05-shadow-collector-five-method-side-by-side-challenger-recordi/05-01-SUMMARY.md"
  modified: []

key-decisions:
  - "Approved as-written: the nested `candidates` JSONL schema (schema_version 2) and the no-migration historical-data strategy, with zero changes requested by the human reviewer."

patterns-established:
  - "One-way-door schema decisions get their own checkpoint-only plan, separate from the plan that implements them (this plan vs. 05-02)."

requirements-completed: [D-06, D-07]

coverage:
  - id: D1
    description: "Human explicitly approved the new nested-per-candidate JSONL shape (schema_version 2) before any implementing code was written"
    requirement: "D-06"
    verification:
      - kind: manual_procedural
        ref: "Coordinator relayed the human's verbatim approval: 'approved the proposed schema_version:2 shape and the \"no migration of old rows\" strategy exactly as written — no changes requested.'"
        status: pass
    human_judgment: true
    rationale: "This is a one-way-door schema decision; only a human can authorize it, and automation cannot substitute for that sign-off."
  - id: D2
    description: "Human explicitly approved the historical-data strategy (no migration of already-committed flat-shape rows) for data already on `shadow-collection-data`"
    requirement: "D-07"
    verification:
      - kind: manual_procedural
        ref: "Same coordinator-relayed approval message as D1"
        status: pass
    human_judgment: true
    rationale: "Whether to migrate/rewrite historical rows is itself a one-way, data-loss-adjacent decision given the append-only discipline fixed by commit 417dc54 — requires explicit human sign-off, not an automated default."

duration: N/A (checkpoint plan — execution paused across two invocations awaiting human sign-off)
completed: 2026-10-07
status: complete
---

# Phase 5 Plan 1: Approve the Nested JSONL Schema and Historical-Data Strategy Summary

**Human approved, as-written, the schema_version-2 nested-per-candidate JSONL shape and the no-migration historical-data strategy that 05-02 through 05-05 now implement without re-deriving.**

## Performance

- **Duration:** N/A — this plan's single task is a `checkpoint:decision` with `gate="blocking-human"`; execution halted after presenting the decision and resumed in a second invocation once the human's answer was relayed by the coordinator.
- **Completed:** 2026-10-07
- **Tasks:** 1/1 completed
- **Files modified:** 0 (this SUMMARY.md is the only artifact; no implementation code was written, per this plan's explicit no-implementation scope)

## Accomplishments

- Presented the one-way-door JSONL schema restructuring decision (D-06) to a human before any code implemented it, exactly as this plan's objective required.
- Obtained and recorded explicit human approval, verbatim, with no changes requested — `approve-as-written` was selected.
- Unblocks 05-02 Task 1 (`log_cycle_predictions`), which is directed to implement exactly this shape and this strategy, cited by name.

## Decision Record (verbatim, as approved)

### The approved nested-per-candidate JSONL schema (schema_version 2)

One JSON object per corridor per cycle:

```json
{
  "schema_version": 2, "corridor": "...",
  "initialization_time": "...", "availability_time": "...",
  "decision_time": "...", "valid_time": "...", "horizon_minutes": 1440,
  "logged_at": "...", "basis_caveat": "(unchanged string, same as today)",
  "candidates": {
    "ml_wind_corrected":      { "status": "ok|unavailable|failed", "ampacity_amps": "float|null",
                                 "fallback_used": "bool", "fallback_reason": "string|null",
                                 "model_version": "string|null", "input_provenance": "dict|null",
                                 "reason": "string|null" },
    "ml_cooling_corrected":   "...same seven keys...",
    "raw_forecast":           "...same seven keys...",
    "persistence_24h":        "...same seven keys...",
    "reference_ml_refit_24h": "...same seven keys..."
  },
  "method": "ml_wind_corrected",
  "ampacity_amps": "candidates.ml_wind_corrected.ampacity_amps, verbatim",
  "fallback_used": "candidates.ml_wind_corrected.fallback_used, verbatim",
  "fallback_reason": "candidates.ml_wind_corrected.fallback_reason, verbatim",
  "model_version": "candidates.ml_wind_corrected.model_version, verbatim",
  "input_provenance": "candidates.ml_wind_corrected.input_provenance, verbatim"
}
```

Each of the five `candidates` entries carries exactly these seven keys: `status`, `ampacity_amps`,
`fallback_used`, `fallback_reason`, `model_version`, `input_provenance`, `reason`.

### The approved six-field legacy mirror rule

The six top-level mirror fields (`method`, `ampacity_amps`, `fallback_used`, `fallback_reason`,
`model_version`, `input_provenance`) are an **exact, byte-for-byte copy** of
`candidates["ml_wind_corrected"]`'s own fields — including when `ml_wind_corrected` itself is
`"unavailable"` or `"failed"` that cycle, in which case `method` stays the literal string
`"ml_wind_corrected"` and `ampacity_amps` is `null`. This is D-01 read literally: a legacy
single-method reader (`forecast_shadow_healthcheck.py`) sees exactly what it saw before — an honest
null on a bad cycle, never a different candidate's value silently promoted into that slot.

Confirmed directly against the actual code (not re-derived by 05-02): `forecast_shadow_healthcheck.py`
lines 44-77 (`_last_entry`, `check`) reads only `entry.get('fallback_used')` and `entry['logged_at']`
at the top level — this mirror requires **zero code change** in that file.

### The approved historical-data strategy

Leave every already-committed flat-shape row on `shadow-collection-data` exactly as it is — **no
migration, no backfill, no rewrite** — following directly from the append-only discipline commit
`417dc54` established. A reader (05-05 Task 1's `forecast_shadow_render_table.py` update)
distinguishes old rows from new rows per-line via `entry.get("schema_version", 1) >= 2`, rendering
old rows as a single-method row (as today) and new rows with all five candidates.

### Other confirmed, approved details

- The `candidates` object roughly quintuples each line's byte size — accepted as no operational cost
  (git diffs on text; nothing parses this at volume).
- The new `reason` field (D-04/D-07 — why NO value exists this cycle) is deliberately kept distinct
  from the existing `fallback_reason` field (D-06 — a method-internal fallback that still produced a
  genuine value).
- `.github/workflows/shadow_collect.yml`'s append step (`cat "$f" >> ...`) is format-agnostic to the
  JSON shape inside each line — this decision requires no workflow-file change.

## Human Decision Record

**Decision requested:** Approve the new nested-per-candidate JSONL schema (schema_version 2) and
the historical-data strategy for rows already committed to `shadow-collection-data` in the old flat
shape.

**Options presented:**
1. `approve-as-written` — approve the schema and historical-data strategy exactly as written above.
2. `approve-with-changes` — approve the general approach but name specific changes.

**Human response (relayed by the coordinator, verbatim):** "The human approved the proposed
schema_version:2 shape and the 'no migration of old rows' strategy exactly as written — no changes
requested."

**Selected:** `approve-as-written`. No amendments were made to the schema, the mirror rule, or the
historical-data strategy as recorded above.

## Deviations from Plan

None — plan executed exactly as written. No implementation code was written in this plan, per its
explicit scope; only the checkpoint was presented and the human's decision recorded.

## Task Commits

1. **Task 1: Checkpoint — approve the new nested JSONL schema and the historical-data strategy** - presented as a `checkpoint:decision` (`gate="blocking-human"`); no commit at presentation time since no files changed. The human's answer is recorded in this SUMMARY.md, committed below.

**Plan metadata:** (recorded in the closing docs commit, see final commit for this plan)

## Self-Check: PASSED

- This SUMMARY.md file exists at its documented path (verified by the Write tool's successful write, no prior read-then-edit failure).
- No commit hashes are claimed in this summary prior to the closing commit, so there is nothing stale to verify here.
