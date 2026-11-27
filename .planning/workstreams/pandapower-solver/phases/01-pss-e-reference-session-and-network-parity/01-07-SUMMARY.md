---
phase: 01-pss-e-reference-session-and-network-parity
plan: 07
subsystem: testing
tags: [pandapower, parity, read-back, mutation-tests, canonical-json, case39, d-06]
status: complete

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: raw.ParsedCase, raw.branch_key and network.build_network with PSS/E numbering and names (01-06); the leak guard and its pandapower_marker shape pattern (01-01)
provides:
  - backend/pandapower_job/parity.py, an independent read-back of a built network against the parsed export in 11 categories, with ParityReport (pass only when nothing differs and nothing went uncompared) and a counts-only rendering
  - parity.case39_evidence, counts-only evidence against pandapower's public 39-bus case for the owner's D-06 decision
  - backend/pandapower_job/convert.py, canonical marker-keyed network JSON with a fail-closed reader and a size check against the 48 KB secret limit
  - 46 tests proving the report can fail in every category and that the converted copy builds an equal network
affects: [01-08, 01-09, 01-10, 01-11]

plan_head_before: fde1909cadfb519520079af295d8f03f0767d2a8
plan_head_after: 0940f9d15d2692945904387574ce7c4d6dbdbf78
actuals:
  tokens: 16400
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Read-back functions return the quantities in the export's units (`_read_line`, `_read_transformer`) and the caller chooses the tolerance, so the parity report (1e-9) and the D-06 evidence (1e-6) share one set of formulas"
    - "An unreadable value (missing column, NaN) is a difference with got None, never a skipped comparison"
    - "Reports are namedtuple subclasses, so equal inputs give equal reports and row-order independence is a one-line equality test"
    - "Marker key assembled from pieces in source and in tests so the leak guard flags a stray converted file but not the code"

key-files:
  created:
    - backend/pandapower_job/parity.py
    - backend/pandapower_job/convert.py
    - backend/tests/pandapower_parity_test.py
  modified: []

key-decisions:
  - "Read-back uses the net's own bus kV and frequency and the export's system base: R, X in ohms times length over parallel circuits over kV^2/SBASE; B at the net's f_hz; rating is max_i_ka times df times parallel times root three times the from bus kV; transformer Z and R move from the unit's MVA to the system base and X is sqrt((Z-R)(Z+R)); shunt BL is minus q times step times (rated kV over bus kV) squared"
  - "Net frequency and system MVA are compared with BASFRQ and SBASE as two `impedance` comparisons on the element `system`, so a header mismatch is a difference rather than a silent change to every line"
  - "A branch or machine whose kind differs is reported once under classification and not compared further; a one-sided key is reported under names, with the family total under counts"
  - "`passed` also requires at least one comparison overall, so an empty report is not a pass"
  - "Transformer ratings are not compared: the builder does not carry RATA1 into the network, so the rating category covers lines only (stated in the module docstring)"
  - "case_from_json requires every v33 section name to be present and refuses a record in an unsupported section, so a copy cannot silently drop what the builder would ignore"
  - "The D-06 matching rules: buses by number, branches by unordered bus pair and position, loads, shunts and machines by bus and position; `unmatched_buses` counts export buses the public case lacks"

patterns-established:
  - "One mutation per category through plain pandas edits of the net, each asserting the exact (category, element, quantity) set"

requirements-completed: [NET-02]

coverage:
  - id: D1
    description: "parity_report reads the built synthetic network back to the export with zero differences, a non-zero comparison count for every category that has elements, and passed True"
    requirement: "NET-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_tracer_parity_is_zero_on_a_clean_synthetic_build"
        status: pass
    human_judgment: false
  - id: D2
    description: "Each of ten single mutations (reactance, rating, setpoint, voltage limit, machine limit, load, shunt, in-service flag, dropped line, line reclassified as a transformer) gives exactly the expected difference set naming exactly that element, and passed is False"
    requirement: "NET-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_each_single_mutation_is_named_exactly"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_a_mutation_leaves_every_other_category_clean"
        status: pass
    human_judgment: false
  - id: D3
    description: "The scope note heads every rendering, and render_counts prints category counts and a verdict only, with no bus number, element key or value, passing or failing"
    requirement: "NET-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_render_counts_holds_no_key_or_value"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_a_category_that_could_not_be_compared_is_not_a_pass"
        status: pass
    human_judgment: false
  - id: D4
    description: "Edges: the tolerance boundary (exact in binary, and half and twice the tolerance on a real line), empty sections on both sides, one-sided elements, sorted differences, shuffled table rows and a read-only net all behave as stated"
    requirement: "NET-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_tolerance_boundary"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_tolerance_boundary_on_a_real_element"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_empty_sections_and_one_sided_elements"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_differences_are_sorted_and_row_order_free"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_report_reads_the_net_only"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_an_unreadable_value_is_a_difference_not_a_skip"
        status: pass
    human_judgment: false
  - id: D5
    description: "The converted copy is canonical (sorted keys, compact, ASCII, no NaN, byte-identical whatever the dict order), round-trips exactly, builds a network whose every table equals the one built from the RAW, and is flagged by the leak guard's marker pattern"
    requirement: "NET-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_converted_round_trip_and_equal_build"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_converted_bytes_are_canonical_and_flagged_by_the_leak_guard"
        status: pass
    human_judgment: false
  - id: D6
    description: "case_from_json fails closed with one named reason and no value in the message for 12 reasons (18 bad documents plus byte-level cases), and every reason is exercised"
    requirement: "NET-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_converted_copy_refuses_a_bad_document"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_converted_copy_refuses_bad_input"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_every_convert_reason_is_exercised"
        status: pass
    human_judgment: false
  - id: D7
    description: "size_report states whether the copy fits the 48 KB secret limit (exactly 49152 bytes fits, one more does not) and case39_evidence gives counts only: 0 unmatched buses and 0 differences at offset 0, 39 unmatched buses at offset 90000, one impedance difference for a 1 percent reactance change, one classification difference for a line exported as a transformer"
    requirement: "NET-02"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_size_report_and_the_secret_limit"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_case39_evidence_counts"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_parity_test.py#test_evidence_render_holds_counts_only_and_decides_nothing"
        status: pass
    human_judgment: false

duration: 55min
completed: 2026-11-16
---

# Phase 1 Plan 07: Parity report and converted network copy Summary

**An independent read-back of the built pandapower network against the parsed export in 11 categories, proven able to fail by ten single mutations that each name exactly the element changed, plus a canonical marker-keyed JSON form of the parsed network (26,025 bytes for the synthetic case, under the 48 KB secret limit) and counts-only evidence against the public 39-bus case.**

## Performance

- **Duration:** about 55 min
- **Completed:** 2026-11-16
- **Tasks:** 3 (one tracer, two auto with tdd)
- **Files created:** 3 (2 production, 1 test)

## Accomplishments

- `parity.parity_report` matches buses by number, branches by key against `net.line.name` and `net.trafo.name` together, loads, shunts and machines by `bus-id`, and the swing machine against the ext_grid row. It reads each pandapower value back to the export's units with formulas written in `parity.py` (no import from `network.py`, checked by grep) and lists every difference as category, element, quantity, expected, got. A clean build shows none and every category with elements made at least one comparison (39 buses x 3 voltage limits, 35 line ratings, 21 loads x 2 quantities, and so on).
- `ParityReport.passed` is true only with no difference, at least one comparison, and a comparison in every category that has elements; `render_counts()` prints the scope note, one count line per category and the verdict, never a key or value.
- `convert.case_to_json` and `case_from_json` give a byte-stable, ASCII, NaN-free form; the network built from the converted copy equals the one built from the RAW in every table, and the parity report passes on it. The reader refuses 12 reasons, none echoing a value.
- `parity.case39_evidence` reports element counts on each side, unmatched buses, classification differences and the count of matched elements differing beyond 1e-6 relative, per category; it decides nothing.

## Task Commits

1. **Task 1: Tracer** - `5b25e25` (feat) parity read-back shows zero differences on a clean build
2. **Task 2: One mutation per category** - `d033c43` (test) ten mutations and the tolerance, empty, ordering and read-only edges
3. **Task 3: Converted copy and D-06 evidence** - `0940f9d` (feat) convert.py, case39_evidence, and the shared read-back split

## Verification

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_parity_test.py` -> `46 passed in 10.10s` (nothing skipped).
- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_parity_test.py backend/tests/pandapower_network_test.py backend/tests/private_data_guard_test.py -k "not owner_local"` -> `97 passed, 1 deselected, 2 warnings in 13.46s` (the warnings are pandapower's own notices about case39's missing `tap_dependency_table`).
- `grep -n "from pandapower_job.network import\|from pandapower_job import network\|import pandapower_job.network" backend/pandapower_job/parity.py` -> nothing.
- The `convert` import check prints `ok`.
- `.venv/bin/python -I -B backend/private_leak_scan.py` -> exit 0; the staged scan was exit 0 before each commit.
- Frozen-file gate for plan 01-07 -> exit 0 after each commit.

## Evidence figures for the owner's D-06 decision (synthetic, counts only)

- The converted copy of the synthetic 39-bus case is 26,025 bytes (2,392 gzipped), under the 49,152-byte limit. The copy writes every field of every record, so it is larger than the research's 15,053-byte estimate. A real network more than about 1.8 times this size would no longer fit as a plain secret; compressing it (a few KB here) would be needed. That is for the owner's decision, not this plan.
- Against `pandapower.networks.case39()`: with the synthetic file at bus offset 0, 0 unmatched buses, 0 classification differences and 0 elements differing beyond 1e-6 (35 lines and 11 transformers on both sides). These numbers describe the synthetic file, which is built from case39, so they prove the evidence code works, not anything about the real network.

## Decisions Made

See `key-decisions` above.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pandapower 3.5.6 has no `drop_lines`**
- **Found during:** Task 2
- **Issue:** the dropped-line and reclassified-line mutations first called `pandapower.drop_lines`, which this version does not have.
- **Fix:** the mutations drop the row with `net.line.drop(index, inplace=True)`.
- **Files modified:** `backend/tests/pandapower_parity_test.py`
- **Commit:** `d033c43`

### Notes on process

- Test-first was not followed for Tasks 1 and 2. In Task 1 `parity.py` was written (the complete read-back, needed for "zero differences" to mean anything) before the two tracer tests, and both passed on the first run. In Task 2 the ten mutation cases and five edge tests passed against that implementation after the one `drop_lines` fix above, so there was no separate red run. Task 3 followed red then green (collection error for the missing `convert` module, then 46 passing). The mutation tests are the evidence that the report can fail: each asserts the exact difference set for its change, so a report that missed the change would fail them (not separately confirmed by deleting a comparison).
- The plan's Task 3 text names `tests/pandapower_parity_test.py#test_converted_copy_refuses_bad_input` as one test; the 18 bad documents are a parametrised companion `test_converted_copy_refuses_a_bad_document` plus the byte-level cases in `test_converted_copy_refuses_bad_input`.
- `case39_evidence` takes `element_counts` as a three-part mapping (`export`, `reference`, `matched`) rather than a flat one so the unmatched elements other than buses can be read off it; `differing_beyond` is a mapping from category to count. The plan fixed the field names, not their inner shape.
- The tolerance-boundary test uses a binary-exact tolerance (2^-10, patched in) for "equal to the tolerance passes", because 1e-9 cannot be hit exactly through the read-back formulas; on a real line it checks half and twice the tolerance.

## Issues Encountered

The sandbox refuses compound shell commands (`cd && ...`, long heredocs), so appends to the test file went through scratchpad files, and the frozen-file gate was run from a one-line script kept in the session scratchpad.

## Known Stubs

None.

## Threat Flags

None. `convert.py` returns bytes and writes nothing; the converted bytes carry the marker the leak guard flags (T-01-25), the report rendering is counts only (T-01-24), and the reader fails closed (T-01-26).

## Limitations to carry forward

- The parity report proves transcription only (`PARITY_SCOPE_NOTE`). A shared misreading of a PSS/E convention (assumptions A2 and A4) passes both builder and read-back; NET-03 in plan 01-08 and the real file in plan 01-10 are the independent checks.
- Transformer ratings (RATA1) are not carried into the network and so not compared; shunt, machine QG for gen rows and RATEB/RATEC are likewise outside the read-back.
- `in_service` differences for a load and a shunt with the same `bus-id` key share the key and the quantity `STATUS`; the family is not on the `Difference`. Only a private report would ever list them.
- The evidence's position-based matching of parallel branches and of several machines at one bus assumes the same ordering on both sides; a real file that orders them differently shows as differences, which is the safe direction.

## Self-Check: PASSED

- FOUND: backend/pandapower_job/parity.py, backend/pandapower_job/convert.py, backend/tests/pandapower_parity_test.py
- FOUND commits: 5b25e25, d033c43, 0940f9d (each an ancestor of HEAD)
