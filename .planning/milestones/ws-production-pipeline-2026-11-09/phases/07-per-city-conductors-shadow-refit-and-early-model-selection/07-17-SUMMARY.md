---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
plan: 17
subsystem: validation-go-no-go
tags: [reval-01, go-no-go, rating-basis, label-lift, owner-decision, g6]

requires:
  - phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
    provides: 07-14 offline re-run of 2026-09-08..09-28 (tables, fidelity files, B2 retrain), 07-13 SEL-04 read-1 decision
provides:
  - real_data_validation_p7.md, the REVAL-01 report with the D-18 checklist and the owner's signed GO
  - config.RATING_BASIS and the schema doc label section changed together (new text, no word "provisional")
  - consumer docs reworded so they are correct for new-label rows and for older provisional rows
  - STATE entries: decision, B1/B2/B4/B5 closed, B4 follow-up dated 2026-11-30T00:00:00Z, Phase 5 AUSTIN note updated
affects: [07-18 promotion push (owner approval, any stored-row action), Phase 8]

actuals:
  tokens: 14000
  tasks: 3
  commits: 3
plan_head_before: 46bd2f6
plan_head_after: bbbe6a0

tech-stack:
  added: []
  patterns:
    - "A label lift is a text change in config plus the pinned schema-doc section, with tests that pin both the new label (is_provisional false) and the older label (true)"

key-files:
  created:
    - docs/data-science/decisions/real_data_validation_p7.md
  modified:
    - backend/config.py
    - docs/data-science/schema/city_rating_v1.md
    - docs/integration/rest-api.md
    - docs/data-science/decisions/real_data_validation.md
    - .planning/workstreams/production-pipeline/STATE.md
    - backend/tests/expose_migration_test.py
    - backend/tests/rest_api_doc_test.py
    - backend/tests/e2e_trace_test.py
    - backend/tests/e2e_readonly_test.py
    - backend/tests/example_read_ratings_test.py
    - backend/tests/fake_postgrest.py

key-decisions:
  - "GO, label mode go-forward-only: no stored live row and no backfill row is relabelled (owner, aaphan, 2026-11-02 UTC)"
  - "D-15: ml stays the interim G6 method; dlr_live_run.FORECAST_METHOD untouched"
  - "B4 follow-up date 2026-11-30T00:00:00Z accepted"
  - "The proposed RATING_BASIS text was accepted unedited; it keeps the conductor basis per row (D-13) and has no occurrence of the word provisional"

requirements-completed: []

# REVAL-01 is declared again by 07-18, so it is not marked complete here (requirements.ready-ids gate).
---

# Phase 7 Plan 17: Re-validation report and signed go/no-go Summary

**Owner signed GO on 2026-11-02 for the new label going forward only: `RATING_BASIS` now states the per-city conductor basis without the word "provisional", ml stays the interim G6 method, and nothing is pushed or applied to the live database.**

## What was done

- **Task 1 (c028af2, earlier session):** wrote `docs/data-science/decisions/real_data_validation_p7.md` with the plain-English section, the D-18 checklist, the ml-versus-naive table, SEL-04 status, label-lift options and a pending decision.
- **Task 2 (checkpoint):** the owner replied at 2026-11-02T20:43Z: "go-forward-only, D-15: ml; 2026-11-30 ok; aaphan", and added that the Power Systems answers were mainly to clear the assumptions that made Austin fall back to static over half the time, with the other results accepted as stated. Both lines are recorded verbatim in the Decision block.
- **Task 3 (4fdf774, bbbe6a0):**
  - Decision block written (decision, label mode, D-15, B4 date, verbatim words, `**Signed by:** aaphan, 2026-11-02 (UTC)`, recorded-by line). One pointer line added under the title of `real_data_validation.md` (2 lines added, 0 removed).
  - `config.RATING_BASIS` set to the proposed text, and the schema doc's "Provisional label (OD-5)" section updated with the same text and a "which rows carry it" paragraph. `RATING_CONFIG_VERSION` is unchanged (`v3-powersystems-2026-11-02`, which has no such word).
  - The `forecast_used_by_g6` sentence added to "Forecast fields" (naive band may feed G6 when ml is held back; the flag describes the stored forecast, the trace says which band was used).
  - STATE.md: dated Decisions line, B1/B2/B4/B5 closed in Blockers, the B4 follow-up logged with 2026-11-30T00:00:00Z, the Phase 5 AUSTIN static-fallback note updated with the conductor outcome and the B5 band share (317 of 321 G6-evaluated hours with a band, 0.9875; low-side fallbacks 15 of 336, down from 225).

`is_provisional` check: the view tests `position('provisional' in lower(rating_basis))` and the same for `config_version` (`supabase/migrations/20261026195124_expose_latest_rating.sql`). The new text and `v3-powersystems-2026-11-02` contain neither, so the flag is false for a row carrying both. Verified offline with `latest_rating_contract.is_provisional` and on a throwaway local Postgres (`DLR_TEST_PG_AUTOSTART=1`, `expose_migration_test.py`, 23 passed, AUSTIN false, older-label and backfill rows true). The live database was not touched.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Consumer docs would have misstated rows after the label change**
- **Found during:** Task 3 (flagged at Task 1)
- **Issue:** `city_rating_v1.md` "Rules for consumers" said every row stays provisional until the go and that the removal must happen in both strings; the "Read this first" and status lines and the backfill bullet said no row has passed a go/no-go; `docs/integration/rest-api.md` "Provisional values" carried the same lines. After a GO these are wrong for new rows, and the older wording must stay true for older and backfill rows.
- **Fix:** reworded those lines so rows with the new label are covered by the re-validation, while backfill rows and live rows written before the change still read provisional and must not be described as having passed a go/no-go. Reworded so `supabase_schema_doc_test`'s "passed a go/no-go" sentence rule still holds.
- **Files modified:** `docs/data-science/schema/city_rating_v1.md`, `docs/integration/rest-api.md`
- **Commit:** 4fdf774

**2. [Rule 1 - Bug] Tests pinned the old label text and its "provisional" reading**
- **Found during:** Task 3 full-suite run (6 failures)
- **Issue:** `expose_migration_test` (offline and local-Postgres cases), `rest_api_doc_test` (hand-off wording needles "both strings", "remove the word"), `e2e_trace_test`, `e2e_readonly_test` and `example_read_ratings_test` assumed every live-label row reads provisional.
- **Fix:** tests now pin both cases: the current label is not provisional, the pre-go label (kept in the test as `_OLD_LIVE_BASIS`) and older versions are. The e2e and example fixtures use a pre-go version label where they need a provisional row. The doc-test needles follow the new wording ("going forward only", "lacks the word", "both lack the word"). `fake_postgrest` docstring corrected.
- **Files modified:** `backend/tests/expose_migration_test.py`, `rest_api_doc_test.py`, `e2e_trace_test.py`, `e2e_readonly_test.py`, `example_read_ratings_test.py`, `fake_postgrest.py`
- **Commit:** 4fdf774

D-15 chose ml, so `backend/dlr_live_run.py` and `dlr_live_run_test.py` were not modified.

## Verification

- Full suite (`.venv/bin/python -m pytest backend/tests`): the run after the test fixes gave 2569 passed, 82 skipped, 1 failed. The failure, `forecast_shadow_demo_test.py::test_run_once_all_methods_ok_with_per_city_artifacts_and_a_complete_truth_proxy_window`, passes when its file is run alone (15 passed). The files this plan touched are all green. The earlier full run (before the test fixes) failed only the six tests fixed above. Treat the demo test as an intermittent, unrelated failure; its cause was not investigated (out of scope).
- Acceptance: `**Signed by:**` appears once; `real_data_validation.md` diff since the report commit is 2 added, 0 removed.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema change. T-07-33 (checklist committed before the checkpoint, signature verbatim and dated) and T-07-34 (conductor basis kept, backfill never relabelled, no stored-row relabel) are met.

## Follow-ups

- B4: refit the CORPUS_CHRISTI anomaly detector on station-measured inputs once Power Systems answers, or by 2026-11-30T00:00:00Z, then replay the September window (logged in STATE.md).
- 07-18: the new label reaches live rows only after the owner-approved push. No stored-row `UPDATE` is planned (go-forward-only).
- REVAL-01 is not marked complete here: 07-18 still declares it.

## Self-Check: PASSED

- FOUND: docs/data-science/decisions/real_data_validation_p7.md, backend/config.py, docs/data-science/schema/city_rating_v1.md
- FOUND commits: c028af2, 4fdf774, bbbe6a0 (all ancestors of HEAD)
