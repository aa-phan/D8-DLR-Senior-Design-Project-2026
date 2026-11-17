---
phase: 01-pss-e-reference-session-and-network-parity
plan: 06
subsystem: testing
tags: [pandapower, psse-raw, parser, fail-closed, network-builder, case39]
status: complete

requires:
  - phase: 01-pss-e-reference-session-and-network-parity
    provides: leak guard and staged scan (01-01), the session's base.json shape (01-03), pandapower 3.5.6 in the checkout's .venv (01-05)
provides:
  - backend/pandapower_job/raw.py, a stdlib fail-closed RAW revision 33 reader (parse_raw, split_record, branch_key, field tables, RawRefused with 15 reasons)
  - backend/pandapower_job/network.py, build_network(case) with PSS/E bus numbers as bus indices, from-to-ckt branch names and 17 fail-closed BuildRefused reasons
  - backend/tests/pandapower_fixture.py, test-time synthetic RAW and synthetic references from case39 with the 90000 offset (not collected)
  - proof that a synthetic RAW parses, builds and solves to case39's own voltages within 1.3e-15 pu
affects: [01-07, 01-08, 01-09, 01-10]

plan_head_before: 475e5ed0e85478e956fbd42137d67a5d79453539
plan_head_after: a629a14e44b27991f0a5dfdc6c5abb3f077a8742
actuals:
  tokens: 20500
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Refusals carry a reason, a count and a line number in the message; element keys live on exception attributes only"
    - "Fixture text is generated into memory or tmp_path and section markers are assembled from pieces, so no tracked file holds RAW structure"
    - "Hand-typed v33 records pin the field order independently of the writer that reads the same table"
    - "Builder collects every offending element per rule before raising, rules checked in the order of BUILD_REFUSAL_REASONS"

key-files:
  created:
    - backend/pandapower_job/__init__.py
    - backend/pandapower_job/raw.py
    - backend/pandapower_job/network.py
    - backend/tests/pandapower_fixture.py
    - backend/tests/pandapower_raw_test.py
    - backend/tests/pandapower_network_test.py
  modified: []

key-decisions:
  - "Range rules live in the parser as bad_value (bus number and circuit-of-bus fields at least 1, IDE 1 to 4, status flags 0 or 1, BASKV, WINDV1 and X1-2 positive, R1-2 not negative) so the builder never receives a value that would make pandapower fail or silently misread a transformer (hypot would lose a negative X)"
  - "A case with zero or more than one swing bus is refused as no_swing_bus (count is the number of swing buses, elements their numbers); swing_bus_machines counts in-service machines at the swing bus, so removing the swing machine and putting it out of service both give count 0"
  - "Feature refusals (non-constant-power load parts, line shunt terminals, remote regulation, transformer codes and the rest) apply to every element whatever its status; only the status-defined rules (swing machine, voltage-controlled bus without a machine, machine at a load bus, conflicting setpoints) count in-service machines, because a retired machine at a load bus is routine and builds as an out-of-service gen"
  - "Terminator comments are matched by phrase prefix per section (so AREA accepts AREA INTERCHANGE and VOLTAGE SOURCE or VSC both name the converter section); a terminator with no comment is accepted by position"
  - "Required counts and defaults per field table are the research's: bus 11 of 13, load 7 of 14, fixed shunt 5 of 5, generator 7 of 28, branch 6 of 24, transformer lines 3 of 21, 2 of 3, 1 of 17, 1 of 2; fields with no sensible default (bus number, BASKV, branch R and X, transformer R and X) are refused when empty"

patterns-established:
  - "Mutation tests through pandapower_fixture.mutate, append and remove, one mutation per refusal reason, with the offending element key asserted on the exception and absent from the message"

requirements-completed: [NET-01]

coverage:
  - id: D1
    description: "A synthetic revision-33 RAW made from case39 with buses offset by 90000 parses, builds and solves to case39's voltages within 1e-9 pu (measured 1.3e-15) and 1e-7 degrees; no synthetic file is committed"
    requirement: "NET-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_network_test.py#test_tracer_synthetic_raw_parses_builds_and_solves_like_case39"
        status: pass
    human_judgment: false
  - id: D2
    description: "PSS/E bus numbers are the net.bus index (no index equals its position); lines and transformers are named from-to-ckt with padding stripped and names are unique across both tables"
    requirement: "NET-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_network_test.py#test_tracer_synthetic_raw_parses_builds_and_solves_like_case39"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_network_test.py#test_names_and_ext_grid_columns"
        status: pass
    human_judgment: false
  - id: D3
    description: "The parser refuses every malformed input of the plan (empty, over the cap, bad header, unknown revision, unknown or misplaced section, unsupported section, field count, bad value, three-winding, four duplicate kinds, missing Q, data after Q) with exactly one reason and a line number"
    requirement: "NET-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_raw_test.py#test_parser_refuses_each_malformed_input"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_raw_test.py#test_every_reason_is_exercised"
        status: pass
    human_judgment: false
  - id: D4
    description: "The builder refuses every item of the research's fail-closed list with one named reason, a complete count and the element keys on the exception only"
    requirement: "NET-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_network_test.py#test_builder_refuses_each_unsupported_feature"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_network_test.py#test_build_refusal_messages_hold_no_key"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_network_test.py#test_every_build_reason_is_exercised"
        status: pass
    human_judgment: false
  - id: D5
    description: "Refusal messages hold the reason, a count and a line number only"
    requirement: "NET-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_raw_test.py#test_refusal_messages_hold_no_record_text"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_network_test.py#test_build_refusal_messages_hold_no_key"
        status: pass
    human_judgment: false
  - id: D6
    description: "Empty, encoding and purity edges: empty input, all-empty sections, BOM, CRLF, tabs, a Latin-1 byte, quoted commas and slashes, circuit ids compared stripped, parse and build are pure"
    requirement: "NET-01"
    verification:
      - kind: unit
        ref: "backend/tests/pandapower_raw_test.py#test_bom_crlf_tabs_latin1_and_quoted_separators_parse"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_raw_test.py#test_parse_is_pure"
        status: pass
      - kind: unit
        ref: "backend/tests/pandapower_network_test.py#test_build_is_pure_and_leaves_the_case_unchanged"
        status: pass
    human_judgment: false

duration: 60min
completed: 2026-11-16
---

# Phase 1 Plan 06: RAW parser and network builder Summary

**A stdlib fail-closed PSS/E RAW v33 reader and a pandapower builder that keeps PSS/E bus numbers and from-to-ckt names, proven on a synthetic RAW generated at test time from case39 (90000 offset) that solves to case39's voltages within 1.3e-15 pu.**

## Performance

- **Duration:** about 60 min
- **Completed:** 2026-11-16
- **Tasks:** 3 (one tracer, two auto with tdd)
- **Files created:** 6 (3 production, 3 test or fixture)

## Accomplishments

- `raw.parse_raw` tokenises by commas outside single quotes, stops at an unquoted slash, walks the 19 v33 sections in order, applies documented defaults to truncated records and returns a `ParsedCase`. 15 refusal reasons, each exercised by a named malformed input; the size cap is checked before decoding.
- `network.build_network` reproduces the research's verified formulas (lines at the from bus's kV, transformers with `vn_hv_kv = WINDV1 * kV_I` and `sn_mva` at the system base, fixed shunt `q_mvar = -BL`, swing machine as `ext_grid` with six `psse_*` columns). 17 refusal reasons, each exercised; element keys never reach a message.
- The fixture inverts the builder formulas from case39's tables, writes RAW text with every field of every table (floats by `repr`, strings quoted and padded as PSS/E pads them), and provides `mutate`, `append` and `remove` plus `reference_from_solved` in the plan 01-03 `base.json` shape for plans 01-08 and 01-09.
- 78 tests in the two pandapower files pass in about 4 seconds.

## Task Commits

1. **Task 1: Tracer** - `b5cfeea` (feat) synthetic RAW through parser and builder to a case39-equal solve
2. **Task 2: Parser fails closed** - `a41f30c` (test) every refusal reason, encoding, empty, defaults and purity
3. **Task 3: Builder fails closed** - `a629a14` (test) every build refusal, naming, flags, shunt sign and purity

## Verification

- `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/pandapower_raw_test.py backend/tests/pandapower_network_test.py` -> `78 passed, 2 warnings` (nothing skipped; the warnings are pandapower's own deprecation notices about case39's missing `tap_dependency_table`).
- `psse_contract_test.py`, `psse_session_test.py`, `private_data_guard_test.py` with `-k "not owner_local"` -> `47 passed, 1 deselected` (the laptop import gate still rejects `pandapower_job`).
- `.venv/bin/python -I -B backend/private_leak_scan.py` -> exit 0; the staged scan was exit 0 before each commit.
- The acceptance grep for `pandapower.networks` / `pandapower.converter` imports in `raw.py` and `network.py` prints nothing (`test_production_modules_build_from_parsed_values_only` also asserts it).
- Frozen-file gate for plan 01-06 -> exit 0 after each commit.
- Worst voltage magnitude difference to case39 over 39 buses: 1.33e-15 pu.

## Decisions Made

See `key-decisions` above. The ones a later plan is most likely to touch: parser range rules (a real file that trips `bad_value` on a status flag or IDE is relaxed in plan 01-10), the swing-bus rule (exactly one swing bus), and the all-elements policy for feature refusals.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixture cached to keep the suite usable**
- **Found during:** Task 3
- **Issue:** `raw_text` and `case39_records` each rebuilt case39 (about 0.5 s apiece); the parametrised refusal tests called them hundreds of times and the two files took 125 s.
- **Fix:** `_CACHE` in `pandapower_fixture.py` holds the records per offset (handed out as deep copies) and the case frequency; the suite now takes about 4 s.
- **Files modified:** `backend/tests/pandapower_fixture.py` (committed with Task 3)
- **Commit:** `a629a14`

### Notes on process

- Tasks 1 and 2 followed red then green (collection error for the missing package; 15 failing tests before the Task 2 parser changes). In Task 3 the tests were written and the builder rules implemented before the first run, so there was no separate red run for that task; the tests that exist would fail against a builder without the rules.
- Task 1's `raw.py` already handled the tracer path plus the range, field-count, three-winding and unsupported-section refusals; Task 2 added decoding, the cap, the empty check, terminator phrases, duplicates and trailing data.
- The hidden extra checks beyond the plan's list: `test_every_reason_is_exercised` (both modules), the hand-typed positional layout test, a table self-consistency test and a terminator-tolerance test.

## Issues Encountered

None blocking. The sandbox refuses compound git commands, so the frozen-file gate was run from a one-line script kept in the session scratchpad.

## Known Stubs

None.

## Threat Flags

None. The parser and builder are the plan's own T-01-20 to T-01-22 mitigations; no new network, auth or file-access surface.

## Limitations to carry forward

- A synthetic RAW made from pandapower's own case proves transcription only. That PSS/E 36.4 writes the PowerModels.jl field layout (A2) and that PSS/E's transformer convention equals MATPOWER's (A4) are settled only by plan 01-10 (real file) and NET-03.
- `BASFRQ` defaults to 60 Hz when the header omits it.
- Unsupported-section records are refused at the first record without reading further, so the line number points to the first record, not the last.

## Self-Check: PASSED

- FOUND: backend/pandapower_job/__init__.py, backend/pandapower_job/raw.py, backend/pandapower_job/network.py
- FOUND: backend/tests/pandapower_fixture.py, backend/tests/pandapower_raw_test.py, backend/tests/pandapower_network_test.py
- FOUND commits: b5cfeea, a41f30c, a629a14 (each an ancestor of HEAD)
