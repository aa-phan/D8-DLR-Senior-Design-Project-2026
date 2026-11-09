---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 02
subsystem: evaluation-protocol
tags: [confirmation-protocol, pre-registration, owner-signature, selection-rule, conductor, python, pytest]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: plan 07-01 per-city production conductor table (the O4 choice is applied to it in a later plan)
provides:
  - Confirmation protocol v4 draft in plain English with 11 owner items and a machine-checked registry
  - Signed record of v4 (signing copy), signed 2026-11-02 by aaphan, sign-with-changes on owner item O4
  - backend/tests/protocol_v4_registry.py parser (parse_registry, as_timestamp, as_list, signature, is_signed) and protocol_v4_doc_test.py (33 checks)
  - ml-modeling and production-pipeline STATE records of the signed amendment
affects: [07-03, 07-05, 07-06, 07-09, 07-10, 07-11, 07-12, 07-15]

actuals:
  tokens: 26000
  tasks: 3
  commits: 3
plan_head_before: d70cb085ae47cb244d1d6317d841419ffb5443b1
plan_head_after: fbe3948604353e741d07982fd1018e75ed154f38

tech-stack:
  added: []
  patterns:
    - "Two-column backticked registry table parsed by a helper; later plans compare code constants to the signing copy's registry"
    - "Signing copy generated from the final draft text so body and registry cannot drift (a test compares them)"

key-files:
  created:
    - docs/data-science/decisions/confirmation_protocol_v4_early_selection.md
    - docs/data-science/decisions/confirmation_protocol_v4_early_selection_SIGNING_COPY.md
    - backend/tests/protocol_v4_registry.py
    - backend/tests/protocol_v4_doc_test.py
  modified:
    - .planning/workstreams/ml-modeling/STATE.md
    - .planning/workstreams/production-pipeline/STATE.md

key-decisions:
  - "Owner signed v4 on 2026-11-02 as `aaphan` (sign-with-changes: 04=switch austin based on given answers); O1-O3 and O5-O11 are the drafter's recommendation (A)"
  - "O4 custom choice: AUSTIN switches to 795 Drake ACSR at 100 C maximum operating temperature (elevation 900 m and azimuth 173.15 stay at model defaults); CORPUS_CHRISTI, MIDLAND, EL_PASO stay on Drake 75 C"
  - "O4 consequence accepted by the owner: AUSTIN FRESH headline under Drake 100 C; AUSTIN cooling and reference refit on rows before 2026-03-17; TEST veto re-scored under the production conductors before read 1 is run; no registered date moves"
  - "Registry encodes O4: power_systems.partial_answers=custom_switch_austin_drake_100c, power_systems.switch_cities=AUSTIN, power_systems.austin_config, refit.cities=AUSTIN, test.rescore_gate=before_read1_run"

patterns-established:
  - "Pre-registered values live in one parsed table; the draft is the reviewed text and the signing copy is the signed record (v3 convention)"

requirements-completed: [SEL-01]

coverage:
  - id: D1
    description: "v4 draft: plain-English first section, 11 owner items with options, recommendation and default, anti-peeking statement, retirement of 2026-11-24, read 1 and conditional read 2 pins, selection rule with worked example, ABLATION and TEST veto criteria"
    requirement: SEL-01
    verification:
      - kind: unit
        ref: "backend/tests/protocol_v4_doc_test.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Signing copy is signed (name, signature, UTC date), its registry equals the draft's, every sign-off row has a chosen option, O4 records the custom AUSTIN choice"
    requirement: SEL-01
    verification:
      - kind: unit
        ref: "backend/tests/protocol_v4_doc_test.py#test_signing_copy_registry_equals_the_drafts"
        status: pass
      - kind: unit
        ref: "backend/tests/protocol_v4_doc_test.py#test_every_signing_copy_sign_off_row_has_a_chosen_option"
        status: pass
    human_judgment: false
  - id: D3
    description: "The owner's signature and O4 choice (human decision, not machine-derivable)"
    requirement: SEL-01
    verification:
      - kind: manual_procedural
        ref: "owner reply `sign-with-changes: 04=switch austin based on given answers;aaphan`, recorded verbatim in the signing copy"
        status: pass
    human_judgment: true

status: complete
---

# Phase 7 Plan 02: Confirmation Protocol v4 Summary

**Confirmation protocol v4 is drafted in plain English with a machine-checked registry and signed by the owner (`aaphan`, 2026-11-02, sign-with-changes on O4: AUSTIN switches to Drake ACSR at 100 C), retiring the 2026-11-24 run in favor of read 1 at 2026-11-01T00:00:00Z and a conditional read 2 at 2026-11-08T00:00:00Z.**

## Performance

- **Tasks:** 3 of 3 (Task 1 draft, Task 2 owner decision, Task 3 record the signature)
- **Task 1** was completed in an earlier session (commit 8d12f17); Task 2 was the owner's reply; this session ran Task 3.

## Accomplishments

- Draft v4 (commit 8d12f17): 19 required sections, 11 owner items, 54-row registry (58 after signing), parser and doc test.
- Owner reply recorded verbatim (`sign-with-changes: 04=switch austin based on given answers;aaphan`); signer name exactly as typed, signature date 2026-11-02 (UTC date of the reply, from `date -u`).
- Signing copy created from the final draft text with the Sign-off table filled (each of O1..O11 with its option and "(selected 2026-11-02)"); the draft carries a signed banner pointing to it and a change-log row.
- O4 written as a custom choice in the draft, the signing copy and the registry; `power_systems.partial_answers` changed from `complete_cities_only` to `custom_switch_austin_drake_100c`; rows added for `power_systems.switch_cities`, `power_systems.austin_config`, `refit.cities`, `test.rescore_gate`. The TEST re-score wording "before the instant" is replaced by "before read 1 is run" as the owner accepted.
- Doc test extended from 23 to 33 checks (signing copy exists and is signed, registry equals the draft's, every sign-off row has a chosen option, O4 row and registry rows agree with the Drake-100 ablation variant, TEST wording).
- ml-modeling STATE: pending-amendment note replaced by the signed record (also a dated Decisions line; "Current focus" no longer names 2026-11-24 as the open evaluation). Production STATE: Phase 7 external-gate blocker updated to "v4 signed 2026-11-02" and a Decisions line recorded.

## Task Commits

1. Task 1: `8d12f17` docs(07-02): draft confirmation protocol v4 for owner signature
2. Task 2: owner decision (no commit)
3. Task 3: `fbe3948` docs(07-02): record the owner's signature on confirmation protocol v4

Note on `commits: 3`: the measured range `plan_head_before..plan_head_after` also contains `858ea22` (plan 07-03's failing-tests commit, made by a concurrent executor on main); plan 07-02's own task commits are the two above.

## Deviations from Plan

None - plan executed as written. The O4 registry rows beyond `power_systems.partial_answers` were added at the orchestrator's direction ("update any registry row(s) that O4's choice affects") so the choice is machine-readable; the draft's own signature block was left blank by design (v3 convention, enforced by an existing test).

ROADMAP Phase 7 SC 1/3/5 and REQUIREMENTS SEL-01/02/04 do not restate "every city stays on Drake" or the no-refit default (SC 3 already says "every city whose Power Systems values arrive by 2026-10-31T00:00Z" are refit, which covers AUSTIN, whose answer arrived 2026-10-27), so no wording was aligned and both files are untouched apart from the plan-progress update.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. No network endpoint, auth path or schema was added; no scorer was run and no predicted-versus-truth outcome was computed or read for any `valid_time` on or after 2026-09-30 (`git status --porcelain data/shadow` is empty).

## Notes for later plans

- The actual config change (`backend/config.py` AUSTIN `max_temp_c` 75.0 to 100.0, a config-version bump, AUSTIN refit and the TEST re-score before read 1 is run) is plan 07-11's apply-answers path. This plan did not edit `backend/config.py`.
- The sign-off acknowledgement text ("I confirm that I have not read any FRESH-basis outcome ...") is part of the block the owner signed; the owner's reply did not restate it separately. Worth a one-line owner confirmation before read 1.
- `03-05-conductor_sensitivity.py` and the two research/options documents were already tracked; nothing was added or changed.

## Self-Check: PASSED

- FOUND: docs/data-science/decisions/confirmation_protocol_v4_early_selection.md
- FOUND: docs/data-science/decisions/confirmation_protocol_v4_early_selection_SIGNING_COPY.md
- FOUND: backend/tests/protocol_v4_registry.py, backend/tests/protocol_v4_doc_test.py (33 passed)
- FOUND commits 8d12f17 and fbe3948 (ancestors of HEAD)
- `is_signed` True, signature date 2026-11-02, name `aaphan`
