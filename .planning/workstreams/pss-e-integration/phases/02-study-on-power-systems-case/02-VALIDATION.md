---
phase: "2"
slug: "study-on-power-systems-case"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-28"
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Derived from the `## Validation Architecture` section of `02-RESEARCH.md`; the planner fills the per-task map.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3, plain asserts, no classes (repo house style) |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| **Quick run command** | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/psse_contract_test.py backend/tests/psse_mapping_test.py backend/tests/psse_api_test.py backend/tests/psse_study_test.py backend/tests/psse_contingency_test.py backend/tests/psse_margin_test.py backend/tests/psse_dispatch_test.py backend/tests/psse_probe_test.py backend/tests/psse_study_doc_test.py` (no database; list only the files that exist at the current plan) |
| **Full suite command** | `PATH="/c/Users/tejas/Downloads/postgresql-18.6-5-windows-x64-binaries/pgsql/bin:$PATH" PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_*_test.py backend/tests/secret_scan_test.py` (Postgres 18.6 `bin` on PATH for the command only; a skipped database proof is a failure) |
| **Estimated runtime** | quick: ~30 seconds; full: ~2.5 minutes (Phase 1 baseline 243 passed in about 109 s, plus one more local-Postgres module) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (no database).
- **After every plan wave:** Run the full suite command; any skip counts as a failure.
- **Before `/gsd-verify-work`:** Full suite green, plus a mutation check (see below).
- **Max feedback latency:** 120 seconds.

---

## Per-Task Verification Map

Task IDs are `<plan>-T<n>` from the PLAN files (filled by the planner 2026-10-28). Every command is `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs <args>` from the repository root; `PG` abbreviates the prefix `PATH="/c/Users/tejas/Downloads/postgresql-18.6-5-windows-x64-binaries/pgsql/bin:$PATH" PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1`. SC1 to SC4 are the ROADMAP Phase 2 success criteria.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-T1 | 02-01 | 1 | IN-02 / SC1 | T-02-03, T-02-04 | The committed placeholder mapping loads with default settings and its own sha256; a placeholder is refused without the flag; psse_local/, *.sav and *.raw are git-ignored | unit | `backend/tests/psse_mapping_test.py -k "tracer or private"` | ❌ W0 | ⬜ pending |
| 02-01-T2 | 02-01 | 1 | IN-02 / SC1 | T-02-01, T-02-02, T-02-05 | 42 malformed mappings refused with every problem named; size capped before parsing; hash of the parsed bytes; error names the file's base name only | unit | `backend/tests/psse_mapping_test.py -k rule` | ❌ W0 | ⬜ pending |
| 02-01-T3 | 02-01 | 1 | IN-02 (defaults as configuration) | T-02-02 | 21 settings defaults pinned; 34 bad overrides refused with dotted paths; errors surface as mapping errors | unit | `backend/tests/psse_mapping_test.py -k settings` | ❌ W0 | ⬜ pending |
| 02-02-T1 | 02-02 | 1 | STU-01 / SC2, TST-01 / SC4 | T-02-09 | Adapter over the injected fake loads the placeholder, strips padded ids, returns a classified converged solve; SURFACE has 19 rows, branch_chng_3 UNVERIFIED | unit (fake) | `backend/tests/psse_api_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-02-T2 | 02-02 | 1 | IN-03 / SC2, TST-01 / SC4 | T-02-06, T-02-08, T-02-10 | Ratings only as positive finite MVA in the rate set's slot, read back; save onto the case path refused (CaseProtected); every psspy failure a named PsseCallError; radial-solver base values pinned | unit (fake) | `backend/tests/psse_api_test.py -k io` | ❌ W0 | ⬜ pending |
| 02-02-T3 | 02-02 | 1 | STU-01 / SC2, TST-01 / SC4 | T-02-07, T-02-09 | Only fnsl 0 and solved() 0 converge (19 cases, stale solved() after a failed fnsl included); fake names and signatures equal SURFACE; recorded calls stay inside it | unit | `backend/tests/psse_api_test.py -k "solve or surface"` | ❌ W0 | ⬜ pending |
| 02-03-T1 | 02-03 | 2 | IN-02, IN-03, STU-01 | T-02-14 | Placeholder base: mapping checked, four DLR ratings written in MVA and read back, base solved, saved to a private temp file that is removed; `tempfile` added to the Phase 1 allow-list on purpose | unit (fake) | `backend/tests/psse_study_test.py -k tracer` and `backend/tests/psse_contract_test.py` | ❌ W0 | ⬜ pending |
| 02-03-T2 | 02-03 | 2 | IN-02 / SC1, IN-03 / SC2, TST-01 static fallback | T-02-11, T-02-12 | Missing, out-of-service, transformer, mixed-kV, sink and extra-outage problems fail at mapping with no write, solve or save; MVA at the case's kV (345 and 138), per parallel circuit, every rate set, read-back enforced; static vs fresh selection applied exactly | unit (fake) | `backend/tests/psse_study_test.py -k "check or units or static"` | ❌ W0 | ⬜ pending |
| 02-03-T3 | 02-03 | 2 | STU-01 / SC2 | T-02-13, T-02-14, T-02-15, T-02-16 | Non-converged, high-mismatch or collapsed base fails at load_flow; study area by hops; temp-file discipline and cleanup; run-time budget | unit (fake) | `backend/tests/psse_study_test.py -k "load_flow or base"` | ❌ W0 | ⬜ pending |
| 02-04-T1 | 02-04 | 3 | STU-02 / SC3 | T-02-17 | Placeholder N-1: 16 outages, 10 rows over 7 contingencies (thermal and voltage, element, limit, exceeded_by), accepted by validate_results | unit (fake) | `backend/tests/psse_contingency_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-04-T2 | 02-04 | 3 | STU-02 / SC3 | T-02-21 | Pure violation rules: limits, signs, units, skips, exact-limit no row, in_base_case, case limits, JSON-safe details | unit | `backend/tests/psse_contingency_test.py -k violation` | ❌ W0 | ⬜ pending |
| 02-04-T3 | 02-04 | 3 | STU-02 / SC3 | T-02-17, T-02-18, T-02-19, T-02-20 | Scope, extra and all; zero, contingency.max, row cap and budget fail the stage (never truncate); non_convergence and collapsed rows; reload before every outage | unit (fake) | `backend/tests/psse_contingency_test.py -k outage` | ❌ W0 | ⬜ pending |
| 02-05-T1 | 02-05 | 3 | STU-03, STU-04 / SC3 | T-02-23 | AUSTIN margin bounded by the voltage criterion and its voltage_stability dispatch row, accepted by validate_results | unit (fake) | `backend/tests/psse_margin_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-05-T2 | 02-05 | 3 | STU-03 / SC3 | T-02-22, T-02-24, T-02-26 | Analytic two-bus limit within tolerance below the independently found nose and V = 0.90 point; every bounded_by; flat transfer and loadless sink fail; reload and subsystem per evaluation | unit (fake, analytic) | `backend/tests/psse_margin_test.py -k "search or city"` | ❌ W0 | ⬜ pending |
| 02-05-T3 | 02-05 | 3 | STU-04 / SC3 | T-02-23, T-02-25 | Lower of applied rating and voltage limit in MVA, amps and MW; tie to dlr_rating; link rule; POWER_FACTOR_DEFAULT equals config.POWER_FACTOR | unit | `backend/tests/psse_dispatch_test.py` and `backend/tests/psse_contract_test.py -k power_factor` | ❌ W0 | ⬜ pending |
| 02-06-T1 | 02-06 | 4 | TST-01 / SC4, SC3 | T-02-27, T-02-28 | prepare_run with the fake through run_once and the real writer: 1 + 4 + 4 + 10 rows, hashes and versions recorded, every completeness check ok, case unchanged | local PG | PG `backend/tests/psse_study_job_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-06-T2 | 02-06 | 4 | IN-02 / SC1, STU-01 / SC2, TST-01 / SC4 | T-02-27, T-02-29, T-02-30 | Missing mapped branch, non-converging load flow, refused placeholder, unreadable mapping, unloadable case, over-cap N-1 and flat transfer each one failed row and no results (exit 1); static, fresh, read-failed and zero-violation runs complete | local PG | PG `backend/tests/psse_study_job_test.py -k "recorded or written"` | ❌ W0 | ⬜ pending |
| 02-06-T3 | 02-06 | 4 | TST-01 / SC4 | T-02-30, T-02-31 | Whole study calls only SURFACE, matches the golden call surface, never saves or changes the case, new adapter per run, temp cleanup, JSON-safe details, dispatch stage | unit (fake) | `backend/tests/psse_study_test.py -k "full or call_surface or prepare_run or json_safe"` | ❌ W0 | ⬜ pending |
| 02-07-T1 | 02-07 | 5 | TST-01 (Phase 3 drift path) | T-02-33 | Probe against the fake passes every check, never saves, restores the probed rating; `inspect` added to the Phase 1 allow-list on purpose | unit (fake) | `backend/tests/psse_probe_test.py -k tracer` | ❌ W0 | ⬜ pending |
| 02-07-T2 | 02-07 | 5 | TST-01 | T-02-32, T-02-36 | Probe flags renamed, missing and uninspectable functions, misaligned columns, an unread-back rating, a non-converging case and mapping problems; the default report holds no identifier | unit (fake) | `backend/tests/psse_probe_test.py -k "detects or report"` | ❌ W0 | ⬜ pending |
| 02-07-T3 | 02-07 | 5 | IN-03 (stated), STU-03 | T-02-34, T-02-35 | Study-definitions note equals the code (settings and defaults, conversion numbers, stages), holds the questions section, no identifiers, honest scope | doc-drift | `backend/tests/psse_study_doc_test.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Mutation checks at the phase gate (each plant must turn a test red): skip the rating read-back; treat `solved() == 1` as converged; trust `solved()` after a failed `fnsl`; write ratings before the mapping check; `save` onto the case path; truncate N-1 silently; accept a flat transfer; give a tie to `voltage_stability`.

Catching tests (planned): read-back `test_units_read_back_enforced` (02-03); `solved() == 1` `test_solve_classification` (02-02); stale `solved()` `test_solve_stale_solved_after_failed_fnsl` (02-02); write before check `test_check_missing_branch_fails_before_any_write` (02-03); save onto the case `test_io_save_refuses_the_case_path` (02-02) and `test_full_study_never_saves_or_changes_the_case` (02-06); silent truncation `test_outage_row_cap_fails_never_truncates` (02-04); flat transfer `test_city_flat_transfer_fails` (02-05) and `test_recorded_flat_transfer` (02-06); tie `test_dispatch_tie_goes_to_dlr_rating` (02-05).

---

## Wave 0 Requirements

- [ ] Each test file is created by the tracer task of its plan: `psse_mapping_test.py` (02-01-T1), `psse_api_test.py` and the helper `psse_fake_psspy.py` (02-02-T1), `psse_study_test.py` (02-03-T1), `psse_contingency_test.py` (02-04-T1), `psse_margin_test.py` (02-05-T1), `psse_dispatch_test.py` (02-05-T3), `psse_study_job_test.py` (02-06-T1), `psse_probe_test.py` (02-07-T1), `psse_study_doc_test.py` (02-07-T3); `backend/tests/data/psse_call_surface.json` (02-06-T3)
- [ ] `psse_contract_test.py`, deliberate edits with the reason in each commit: `tempfile` in `_STDLIB_ALLOWED` (02-03-T1), new `test_power_factor_copy_matches_config` (02-05-T3), `inspect` in `_STDLIB_ALLOWED` (02-07-T1). No `argparse`: the probe has no command line inside the package (the Phase 3 launcher imports psspy and calls it)
- [ ] `backend/psse_job/constants.py`: `POWER_FACTOR_DEFAULT` (02-05-T1). `RATE_SETS` and every settings default live in `backend/psse_job/settings.py` (02-01), not in constants.py
- [ ] `docs/data-science/schema/psse_mapping_example.json` (marked placeholder) and the `.gitignore` block (02-01-T1); `docs/data-science/decisions/psse_study_definitions.md` (02-07-T3)
- [ ] No framework install needed (pytest, psycopg and Postgres already present)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fake `psspy` matches the real PSS/E signatures and option strings | STU-01..03 | PSS/E is not installed here; the fake can only be checked against documentation | Phase 3: the launcher calls `psse_job.probe.run_probe(psspy, case_path, mapping, write_check=True)` once on the licensed laptop with `show_identifiers` left False, and pastes `format_report` into the Phase 3 verification |
| Units, N-1 scope, rate set and transfer sink make engineering sense on Power Systems' network | IN-03, STU-02, STU-03 | Depends on Power Systems' case and conventions | A Power Systems reviewer confirms the study definitions note |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
