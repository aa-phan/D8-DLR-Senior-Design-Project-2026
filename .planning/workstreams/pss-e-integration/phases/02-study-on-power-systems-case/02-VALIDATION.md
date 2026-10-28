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
| **Quick run command** | `.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/psse_contract_test.py backend/tests/psse_mapping_test.py backend/tests/psse_api_test.py backend/tests/psse_study_test.py` (no database) |
| **Full suite command** | `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_*_test.py backend/tests/secret_scan_test.py` (Postgres 18.6 `bin` on PATH for the command only; a skipped database proof is a failure) |
| **Estimated runtime** | quick: ~15 seconds; full: ~2 minutes (Phase 1 baseline 243 passed, about 109 s) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (no database).
- **After every plan wave:** Run the full suite command; any skip counts as a failure.
- **Before `/gsd-verify-work`:** Full suite green, plus a mutation check (see below).
- **Max feedback latency:** 120 seconds.

---

## Per-Task Verification Map

Filled by the planner (task IDs `<plan>-T<n>`); requirement to test coverage from research:

| Requirement | Behavior | Test Type | Automated Command | Status |
|-------------|----------|-----------|-------------------|--------|
| IN-02 | Mapping loads and validates; a missing, out-of-service, transformer or mixed-kV branch fails at stage `mapping` before any rating write; through `run_once` one failed row and zero result rows | unit (fake), integration (PG) | `psse_mapping_test.py`, `psse_study_test.py -k mapping`, `psse_study_job_test.py -k mapping` | ⬜ pending |
| IN-03 | Written MVA equals `units.circuit_mva(amps, count, case base kV)`; read-back enforced; static fallback applies static amps | unit (fake) | `psse_study_test.py -k "units or static"` | ⬜ pending |
| STU-01 | Only `fnsl` ierr 0 and `solved() == 0` counts as converged; a non-converging base case is a recorded failed run at `load_flow` | unit (fake), integration (PG) | `psse_api_test.py -k solve`, `psse_study_test.py -k load_flow`, `psse_study_job_test.py -k non_converg` | ⬜ pending |
| STU-02 | Scripted outages produce thermal and voltage rows (element, limit, amount exceeded); non-converged outage row; every row passes `validate_results` | unit (fake) | `psse_study_test.py -k "contingency or violation"` | ⬜ pending |
| STU-03 | Analytic two-bus fake: reported limit within tolerance of an independently bisected nose and below it; flat-flow guard | unit (fake, analytic) | `psse_study_test.py -k margin` | ⬜ pending |
| STU-04 | Dispatched capacity is the lower of rating and voltage limit in amps and MW and says which set it; a tie goes to `dlr_rating` | unit | `psse_study_test.py -k dispatch` | ⬜ pending |
| TST-01 | Static fallback, mapping check, non-converging load flow and a failed-run write-back through `run_once` with the real writer and the fake `psspy` | integration (PG) | `psse_study_job_test.py` | ⬜ pending |
| Drift | Fake method and parameter names equal the adapter `SURFACE` table; recorded calls stay inside it | unit | `psse_api_test.py -k surface` | ⬜ pending |
| Hygiene | New modules pass the Python 3.7 syntax gate and import boundary (deliberately extended allow-list); no `psspy` import; no `rating_mw` constant; power-factor constant equals `config.POWER_FACTOR` | unit | `psse_contract_test.py` | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

Mutation checks at the phase gate (each plant must turn a test red): skip the rating read-back; treat `solved() == 1` as converged; trust `solved()` after a failed `fnsl`; write ratings before the mapping check; `save` onto the case path; truncate N-1 silently; accept a flat transfer; give a tie to `voltage_stability`.

---

## Wave 0 Requirements

- [ ] `backend/tests/psse_fake_psspy.py` (helper), `psse_mapping_test.py`, `psse_api_test.py`, `psse_study_test.py`, `psse_study_job_test.py`, `backend/tests/data/psse_call_surface.json`
- [ ] `psse_contract_test.py`: deliberate edit to add `tempfile` (and `inspect`, `argparse` if the probe lives in the package) to `_STDLIB_ALLOWED`; add the power-factor drift assertion
- [ ] `backend/psse_job/constants.py`: power-factor default, `RATE_SETS`, settings defaults
- [ ] `docs/data-science/schema/psse_mapping_example.json` (marked placeholder), `.gitignore` rule for a local PSS/E directory, `docs/data-science/decisions/psse_study_definitions.md`
- [ ] No framework install needed (pytest, psycopg and Postgres already present)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fake `psspy` matches the real PSS/E signatures and option strings | STU-01..03 | PSS/E is not installed here; the fake can only be checked against documentation | Phase 3: run the probe module once on the licensed laptop and compare its output to the `SURFACE` table |
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
