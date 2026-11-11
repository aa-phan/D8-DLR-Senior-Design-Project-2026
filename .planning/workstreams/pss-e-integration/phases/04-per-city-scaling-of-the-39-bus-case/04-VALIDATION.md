---
phase: "04"
slug: "per-city-scaling-of-the-39-bus-case"
status: validated
nyquist_compliant: true
wave_0_complete: true
created: "2026-11-09"
audited: "2026-11-11"
---

# Phase 04 - Validation Strategy

> Per-phase validation contract. SCL-01 to SCL-05 are covered by automated tests against the fake psspy; SCL-06 is Manual-Only (laptop record). No city figure or case total appears in this file.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest, repo `.venv` |
| **Config file** | none (plain pytest from the repository root) |
| **Quick run command** | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/psse_api_test.py backend/tests/psse_probe_test.py backend/tests/psse_study_test.py backend/tests/psse_scaling_test.py backend/tests/psse_mapping_test.py backend/tests/psse_contingency_test.py backend/tests/psse_margin_test.py backend/tests/psse_study_doc_test.py backend/tests/psse_contract_test.py backend/tests/psse_phase4_validation_test.py` |
| **Full suite command** | the quick command plus `psse_study_job_test.py psse_launcher_test.py psse_rehearsal_test.py psse_laptop_modes_test.py psse_setup_doc_test.py`, prefixed with `PATH="<local postgres bin>:$PATH" PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1` |
| **Estimated runtime** | quick about 30 seconds; Postgres-backed about 3 minutes |

Last audit run (2026-11-11): quick set plus `psse_launcher_test.py` without Postgres, 360 passed, 11 skipped (the skips are the Postgres-backed tests; the orchestrator ran those separately). The one known failure, `psse_results_migration_test.py` (CRLF rewrite on this machine, predates the phase), is not counted.

---

## Sampling Rate

- **After every task commit:** quick run command
- **After every plan wave:** full suite command
- **Before verify-work:** full suite green
- **Max feedback latency:** about 30 seconds (quick set)

---

## Per-Requirement Verification Map

| Requirement | Behaviour | Test Type | Automated Command (file::test) | Status |
|-------------|-----------|-----------|--------------------------------|--------|
| SCL-01 | Schema v2 scaling block (load_mw, gen_mw, basis average or peak); missing, mistyped, zero, negative, bool, unknown-basis, extra-key or v1 files are refused, all problems reported together, with no value echoed, before any psspy call | unit | `psse_mapping_test.py` (parametrized refusal table, `test_scaling_problems_reported_together`, `test_scaling_refusal_never_echoes_a_value`, `test_scaling_block_refused_before_any_psspy_call`, `test_tracer_v2_scaling_block_reaches_the_study`, `test_sha256_follows_every_target`) | COVERED, green |
| SCL-02 | Fresh case load per city, whole-case `scal_2` to that city's targets, totals read back before the solve, read-back miss fails the city; never runs a script | unit / integration | `psse_scaling_test.py::test_tracer_four_cities_each_on_its_own_scaled_copy`, `::test_readback_miss_fails_city_at_apply_ratings`, `::test_scale_error_fails_city_at_apply_ratings`; `psse_api_test.py::test_tracer_scale_case_sets_and_reads_back_whole_case_totals`, `::test_scale_layout_matches_the_fake`, `::test_read_totals_closes_every_read_so_reads_can_follow_each_other`, `::test_surface_cannot_run_a_script`; `psse_probe_test.py::test_scale_to_target_*` | COVERED, green |
| SCL-03 | Each city's load flow, N-1, margin and dispatch run on its own copy; no cross-city effect from scaling or ratings | integration | `psse_scaling_test.py::test_independent_each_solve_sees_only_its_own_city`, `::test_apply_ratings_one_city_view`, `::test_scaled_case_not_converging_is_load_flow`, `::test_basis_label_reaches_details`; `psse_study_test.py` | COVERED, green |
| SCL-04 | A failing city: all four attempted, one failed run naming every city, no result rows for any city | integration | `psse_scaling_test.py::test_failure_several_cities_first_stage_wins`, `::test_failure_long_messages_keep_every_city`, `::test_budget_spent_between_cities_marks_the_rest_not_attempted`; `psse_study_job_test.py::test_tracer_one_city_fails_all_attempted_one_failed_record` (Postgres, counts `[1,0,0,0]`); NEW `psse_phase4_validation_test.py::test_one_refused_city_writes_no_result_row_for_any_city` (no database) | COVERED, green |
| SCL-05 | Rows unique and attributable per city with no schema change; no city figure in rows, log lines, error text or dry-run output | integration | `psse_scaling_test.py::test_rows_same_line_in_two_cities_unique_and_attributable`, `::test_rows_and_record_hold_no_target_figure`, `::test_combined_failure_text_never_holds_a_figure`; `psse_launcher_test.py::test_dry_run_success_prints_no_figure`, `::test_dry_run_city_failure_names_each_city_without_figures`; `psse_study_job_test.py` (failure-path log and error text); NEW `psse_phase4_validation_test.py::test_converged_run_logs_and_stores_no_scaling_figure` (success-path log lines and every database parameter) | COVERED, green |
| SCL-06 | Scale step, probe row and four-city dry run on the laptop's 39-bus case | manual | none (see Manual-Only) | Manual-Only, evidence recorded |

*Status: green = ran and passed in this audit (Postgres-backed ones as reported by the orchestrator's run).*

### Gap analysis

Two partial areas were found and filled by `backend/tests/psse_phase4_validation_test.py`:

1. SCL-04 "no result rows for any city" was proven only in the Postgres-backed test; it now also has a database-free test through the real study, `job.run_once` and the real writer.
2. SCL-05 "no figure in a log line" was asserted only on the failure path; the success path (the common one, with the most log and row output) had no log-capture check. Both new tests ran green (2 passed). Neither was weakened to pass; the success test also asserts rows really were written, so it cannot pass vacuously.

No implementation bug was found.

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements (pytest, `psse_fake_psspy.py`, `psse_fakes.py`, local Postgres helper).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Evidence / Instructions |
|----------|-------------|------------|--------------------------|
| The `scal_2` scaling layout, the `scale_to_target` probe row and a four-city dry run on the real 39-bus case | SCL-06 | PSS/E 36.4 and its licence exist only on the laptop | `04-06-LAPTOP-RECORD.md`: layout positions matched the installed help; first probe 30 PASS 1 FAIL (ierr 5, open totals read), fixed in commit 5a30c63; second probe 0 FAIL exit 0 with `scale_to_target` PASS; four-city dry run exit 0, 4 dispatch rows, 4 margin rows, `validation: ok`, nothing written. To repeat: runbook steps 4 and 5. |

Honest limits (not gaps): the real case and real targets are unproven; the power-factor-kept behaviour and the meaning of ierr 5 are documented or inferred, not measured.

---

## Validation Sign-Off

- [x] Every requirement has an automated test or a recorded Manual-Only with evidence
- [x] Sampling continuity: every plan has automated verification
- [x] Wave 0 covers all MISSING references (none)
- [x] No watch-mode flags
- [x] Feedback latency about 30 seconds
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-11-11
