---
phase: 03-real-data-validation
verified: 2026-10-21T08:00:00Z
status: passed
score: 6/6 must-haves verified
covered_files:
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-01-PLAN.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-01-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-02-PLAN.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-02-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-03-PLAN.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-03-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-04-PLAN.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-04-SUMMARY.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-05-PLAN.md
  - .planning/workstreams/production-pipeline/phases/03-real-data-validation/03-05-SUMMARY.md
  - backend/backfill_archive.py
  - backend/real_data_validation.py
  - docs/data-science/decisions/real_data_validation.md
  - docs/data-science/decisions/real_data_validation/manifest.json
  - docs/data-science/decisions/real_data_validation/tables.md
covered_digest: "v3:sha256:51857b46806d8bd9ef5afcc883ea6bb7de2b0afd597fb1a77d828febd028d406"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Owner confirms the Decision section of docs/data-science/decisions/real_data_validation.md (NO-GO, blocking on B1, B2, B4, B5, signed Aaron Phan 2026-10-21) is what they decided"
    expected: "The owner agrees the recorded choice, the blockquote of their words and the signature are theirs, and that the labelled 'Context, not the owner's words' sentence under B1 is acceptable"
    why_human: "Two judgment-tier prohibitions on plan 03-05 (do not choose/sign for the owner; do not paraphrase or drop the owner's words) cannot be proved by code; unverified-prohibition, human review recommended"
---

# Phase 3: Real-Data Validation Verification Report

**Phase Goal:** Evidence that the pipeline's ratings and statistical methods are fit for production, and a recorded go/no-go.
**Verified:** 2026-10-21
**Status:** human_needed (one flagged judgment-tier prohibition item; no gaps)
**Re-verification:** No, initial verification

The goal is to produce evidence and a recorded decision, not to produce a GO. The recorded decision is NO-GO, so Phase 4 is correctly blocked. That is a valid outcome and is not a gap.

## Goal Achievement

### Observable Truths (ROADMAP success criteria, plus 03-05 plan truths)

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | SC1: A backfill over a stated real window (at least 14 days, all four cities) ran through the cleaned pipeline, with window and command recorded | VERIFIED | `manifest.json` records window 2026-09-08..09-28 (504 steps/city, 168 h warm-up, 14 scored days) and the exact command. I recomputed sha256 of archive, trace, log and console from `data/historical/`: all four match the manifest. The archive has 504 rows per city and 0 duplicate (city, datetime) slots. `run_completeness.csv` shows 0 missing, 0 exhausted, 0 errors, 0 no_trace. All 8 model hashes in the manifest match `data/models/`. |
| 2 | SC2: A validation doc reports per city the rating distribution against static rating and bounds, fallback rate per gate, forecast-band empirical coverage, and detector flag rate, with explanations for outliers | VERIFIED | The doc has VAL-01 sections for rating distribution, outcomes by gate, fallback direction and overstatement, outliers and drivers. VAL-02 has band coverage with a bootstrap CI, coverage by residual count, and detector trip rate by voting branch. It has an Explanations section per city. All 278 table rows in `tables.md` appear verbatim in the doc. I re-ran the `report` subcommand offline into a temp directory; all 11 output files are byte-identical to the committed ones. I also recomputed from the archive alone: scored-window fallback share 68.15% / 11.01% / 20.83% / 0.30% and published mean 1638.5 / 1339.7 / 1610.9 / 1179.0 A, matching the doc. Replay fidelity is 2016 compared, 0 mismatches. |
| 3 | SC3: A go/no-go is written and signed by the owner; on no-go the blocking fixes are listed and Phase 4 does not start | VERIFIED | The doc's `## Decision` section has `**Decision:** NO-GO`, the owner's words as a blockquote, blocking fixes B1, B2, B4 and B5, the sentence "Phase 4 does not start until these are resolved and the validation is repeated.", and `**Signed by:** Aaron Phan, 2026-10-21`. The executor is named only as recorder. STATE.md has the dated VAL-03 line (line 138) and a Phase 4 blocker (line 153). The doc's go/no-go section (a)-(c) cites the VAL-01/02 results, and the decision was committed in 614e395. |
| 4 | 03-05: the decision rests on the owner's choice and words, not the executor's (prohibitions: no choosing/signing for the owner; no paraphrasing) | VERIFIED (non-authoritative LLM-judge) | 03-04 left the Decision as "Pending owner decision" (STATE.md line 137), and the 03-05 checkpoint recorded the owner's reply verbatim. The only added text is a sentence explicitly labelled "Context, not the owner's words". The owner's later B6 decision is recorded separately (45a8be1) and stated not to change the NO-GO. Flagged `unverified-prohibition, human review recommended`, so status is human_needed. |
| 5 | 03-05: STATE.md carries the VAL-03 line citing the doc path, and the Phase 4 blocker | VERIFIED | Lines 138 and 153 of STATE.md cite `docs/data-science/decisions/real_data_validation.md`. |
| 6 | The evidence is reproducible and not mutated by the analysis (nothing in rating/model/policy changed) | VERIFIED | `git status` shows no modified `backend/` or `docs/` files. The report is deterministic (re-run is byte-identical). The 3 relevant test modules pass (41 passed). The orchestrator's full-suite run (1397 passed, 0 failed) is taken from the caller. |

**Score:** 6/6 truths verified (0 present, behavior-unverified).

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `backend/backfill_archive.py` | `--trace-path` validation trace | VERIFIED | Trace of 2016 records exists and is consumed by the analysis (0 archive-vs-trace mismatches). |
| `backend/real_data_validation.py` | completeness, manifest, report, replay CLI | VERIFIED | Ran `report`; exit 0, outputs identical to committed. |
| `docs/data-science/decisions/real_data_validation.md` | validation doc with signed decision | VERIFIED | Substantive (917 lines), contains `**Signed by:**`. |
| `docs/data-science/decisions/real_data_validation/*` (12 files) | committed tables and manifest | VERIFIED | Present; manifest hashes match the git-ignored raw data. |
| STATE.md | VAL-03 line and blocker | VERIFIED | See truth 5. |

### Key Link Verification

| From | To | Via | Status |
| --- | --- | --- | --- |
| STATE.md | `real_data_validation.md` | VAL-03 decision line cites doc path | WIRED |
| manifest.json | `data/historical/*` | sha256 and byte counts | WIRED (recomputed, all four match) |
| tables.md | doc | verbatim copy | WIRED (278/278 rows) |
| report | trace/archive/replay | offline analysis | WIRED (re-run reproduces) |

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| VAL-01 | 03-01, 03-02, 03-04 | Ratings vs static rating and bounds, fallback rate per gate and city, outliers explained | SATISFIED | Truths 1 and 2. |
| VAL-02 | 03-02, 03-03, 03-04 | Forecast band coverage and detector flag rate measured and documented | SATISFIED | Truth 2: coverage with CI, trip rates by branch, naive replay reference. |
| VAL-03 | 03-04, 03-05 | Written go/no-go citing VAL-01/02; Phase 4 does not start on a no-go | SATISFIED | Truth 3: NO-GO signed, Phase 4 blocked in doc and STATE.md. |

All three IDs map to REQUIREMENTS.md and are marked complete there. No orphaned Phase 3 requirements.

### Anti-Patterns Found

No TBD, FIXME or XXX markers were examined as blockers in the deliverable doc. No stubs; the doc and tables are populated with real data. Small bookkeeping staleness (warning, not goal-blocking): STATE.md "Current Position" still reads "Ready to execute 03-05" and the ROADMAP Phase 3 checkbox is unchecked. The SUMMARY notes the orchestrator finalizes these.

### Code Review (03-REVIEW.md) Assessment

All 11 findings are `open`. None undermines the goal.

- **CR-01 (redaction gaps):** This is a defense-in-depth gap in `_redact`, not a leak in this evidence. I grepped the committed-hash trace, log and console for `token=`, `api_key`, `bearer` and `email=` and found 0 hits. It does not affect any number in the validation doc. It should be fixed before the trace and log are shared more widely or before the backfill is re-run for the post-NO-GO re-validation, because the re-validation will reuse this code. Warning-level for the next cycle, not a Phase 3 blocker.
- **WR-01 (log is unredacted):** same class as CR-01. The log was grepped clean.
- **WR-02, WR-03, WR-04:** robustness on interrupted or resumed runs. The real run was uninterrupted (0 resumed, 0 no_trace, 2016/2016 traced), so the evidence is not affected.
- **WR-05, WR-06, IN-01 to IN-04:** manifest determinism, a missing-git crash and hygiene. These do not alter the recorded numbers. The manifest hashes were independently recomputed and match.

The reviewer also found "no correctness defect in the VAL-01/VAL-02 tables themselves", which my independent recompute and byte-identical re-run support. The evidence is reliable.

### Human Verification Required

#### 1. Owner confirms the recorded decision

**Test:** Read the `## Decision` section of `docs/data-science/decisions/real_data_validation.md`.
**Expected:** The choice (NO-GO), the blockquote, the blocking list (B1, B2, B4, B5) and the signature match what you said and signed. The "Context, not the owner's words" sentence under B1 is acceptable.
**Why human:** The two judgment-tier prohibitions on plan 03-05 (no auto-chosen decision or forged signature; no paraphrase) are unverifiable by code. I found no evidence of a violation, but this is flagged rather than passed silently.

### Gaps Summary

No gaps. The phase goal is achieved: the evidence is real, reproducible and hash-pinned, all three requirements are satisfied, and a NO-GO decision is recorded and signed. Phase 4 is correctly blocked on B1, B2, B4 and B5. The one human item is the owner's confirmation of the judgment-tier prohibition. Recommended next steps are to triage the 11 review findings (CR-01 first) before the re-validation run, and to refresh STATE.md "Current Position" and the ROADMAP checkbox.

---

_Verified: 2026-10-21_
_Verifier: Claude (gsd-verifier)_
