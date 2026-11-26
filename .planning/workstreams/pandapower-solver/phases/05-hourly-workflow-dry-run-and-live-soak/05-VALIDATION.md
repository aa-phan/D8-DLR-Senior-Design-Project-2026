---
phase: "05"
slug: "hourly-workflow-dry-run-and-live-soak"
status: planned
nyquist_compliant: true
wave_0_complete: false
created: "2026-11-25"
planned: "2026-11-25"
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Source: 05-RESEARCH.md, Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (repo `pytest.ini`: `pythonpath = backend`, `testpaths = backend/tests`) |
| **Config file** | `pytest.ini` at the repo root |
| **Quick run command** | `PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/pandapower_hourly_workflow_test.py backend/tests/pandapower_soak_test.py backend/tests/pandapower_hourly_test.py` |
| **Full suite command** | quick command plus `backend/tests/pandapower_hourly_leak_test.py`, then the database tier, then the regression set |
| **Database tier (Git Bash)** | `PATH="/c/Program Files/PostgreSQL/17/bin:$PATH" DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1 PYTHONDONTWRITEBYTECODE=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider backend/tests/pandapower_hourly_pg_test.py` |
| **Regression set (must stay green)** | `dlr_live_workflow_test.py`, `psse_gaps_solver_test.py`, `pandapower_import_gate_test.py` (psse_job must not name or import the second solver), `pandapower_replay_output_test.py`, `pandapower_study_job_test.py`, `pandapower_solver_tag_test.py`, `psse_writer_test.py` |
| **Estimated runtime** | quick set about 1 s to a few seconds; leak test about 12 s setup plus 10 to 14 s per test; database tier minutes |

Known Windows-only failures, not phase defects: three CRLF byte-hash tests (`test_psse_migration_is_unchanged_after_apply`, `test_phase6_migrations_are_unchanged_after_apply`, `test_expose_migration_is_unchanged_after_apply`), `test_is_provisional_reads_the_real_labels` (no `matplotlib`), and a Phase 1 CLI test on the `0o600` file mode. Do not assert file mode bits and do not pin file bytes.

---

## Sampling Rate

- **After every task commit:** run the quick command
- **After every plan wave:** quick set plus leak test plus database tier plus the regression set
- **Before `/gsd-verify-work`:** everything green locally, then the owner sequence (see D-07 in `05-CONTEXT.md`): merge by Aaron, secrets, variable, first manual dispatch, cron job, at least 3 green dry runs, real-log scan, recorded decision, flip, 24 hour soak
- **Max feedback latency:** 30 seconds for the quick set

---

## Per-Task Verification Map

Filled by the planner. Requirement-to-test map from research:

| Req | Behavior | Test type | Test file | Status |
|-----|----------|-----------|-----------|--------|
| OPS-01 | Dispatch-only, no schedule/push/pull_request, no inputs, own group with `cancel-in-progress: false`, main-only `if`, `environment: production`, timeout under 60 (30), `contents: read`, entry script | text (regex) | `pandapower_hourly_workflow_test.py` | ⬜ pending |
| OPS-01 | A branch dispatch does not execute the job | text (`if` guard) plus owner check on Actions | same, owner step | ⬜ pending |
| OPS-02 | Every secret through `env:` only; no `${{` inside any `run:`; no `secrets.` in an `if` | text | `pandapower_hourly_workflow_test.py` | ⬜ pending |
| OPS-02 | Private files only in the temp folder, removed on success, failure and exception | unit | `pandapower_hourly_test.py -k temp` | ⬜ pending |
| OPS-02 | No planted secret, bus key, target or base64 fragment in printer output, file descriptors or logging records, with teeth | leak test (04-04 pattern) | `pandapower_hourly_leak_test.py` | ⬜ pending |
| OPS-02 | Real Actions log scanned with real needles | owner check | owner step | ⬜ pending |
| OPS-03 | Absent, empty, `True`, `1`, `false` all give dry; only `true` gives live | unit | `pandapower_hourly_test.py -k mode` | ⬜ pending |
| OPS-03 | Live plus `engine.is_placeholder` refuses before any connect or study | unit | `-k placeholder` | ⬜ pending |
| OPS-03 | Dry run leaves the four tables unchanged, no connect called; positive control: live changes them by one set; live run stored `solver = pandapower`, `pp-` id | database tier | `pandapower_hourly_pg_test.py` | ⬜ pending |
| OPS-03 | Recorded owner decision with date, NET-03 and AGR-02 evidence, variable state | document check plus owner step | manual | ⬜ pending |
| OPS-04 | Retention document in the phase directory states the true daily row rate, the no-pruning decision and the size review trigger, before the first live write | document check | grep in a verification step | ⬜ pending |
| OPS-05 | Soak function matches an independent oracle on 300 seeded histories; hand cases | unit | `pandapower_soak_test.py` | ⬜ pending |
| OPS-05 | `run_by_solver` called with `expected=(engine.SOLVER,)`; output reaches the log only as vocabulary lines | unit | `pandapower_hourly_test.py -k gap` | ⬜ pending |
| OPS-05 | 24 consecutive slots on the live project | owner check, counts-only `05-SOAK-RECORD.md` | owner step | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

### Task-level map (filled by the planner, 2026-11-25)

Every auto task creates the test file its verify command runs, inside the same task (tests first), so no verify depends on a file another wave creates later. `PY` is `.venv/Scripts/python.exe` (fallback `.venv/bin/python`); "PG flags" means `PATH="/c/Program Files/PostgreSQL/17/bin:$PATH" DLR_TEST_PG_AUTOSTART=1 PSSE_REQUIRE_PG=1`.

| Task | Wave | Req | Decisions | Automated verify | Status |
|------|------|-----|-----------|------------------|--------|
| 05-01 T1 (tracer) | 1 | OPS-02, OPS-03 | D-05, D-08, D-10 | `pytest backend/tests/pandapower_hourly_test.py -k tracer` | ⬜ pending |
| 05-01 T2 | 1 | OPS-03 | D-02, D-03, D-04, D-13 | `pytest backend/tests/pandapower_hourly_test.py` and `-k "mode or placeholder or temp"` | ⬜ pending |
| 05-01 T3 | 1 | OPS-02 | D-05, D-10, D-14 | `pytest backend/tests/pandapower_hourly_test.py`; `pandapower_import_gate_test.py pandapower_replay_readonly_test.py` | ⬜ pending |
| 05-02 T1 (tracer) | 1 | OPS-05 | D-04, D-09, D-12 | `pytest backend/tests/pandapower_soak_test.py`; `psse_gaps_solver_test.py` | ⬜ pending |
| 05-02 T2 | 1 | OPS-04 | D-01 | grep of `05-RETENTION-DECISION.md`; Python text check of `supabase/ops/psse_result_size.sql` | ⬜ pending |
| 05-03 T1 (tracer) | 1 | OPS-01 | D-06, D-13 | `pytest backend/tests/pandapower_hourly_workflow_test.py backend/tests/dlr_live_workflow_test.py` | ⬜ pending |
| 05-03 T2 | 1 | OPS-02 | D-02, D-08, D-10, D-13 | `pytest backend/tests/pandapower_hourly_workflow_test.py` (11 tests) | ⬜ pending |
| 05-04 T1 (tracer) | 2 | OPS-03 | D-03, D-04, D-10 | PG flags `pytest backend/tests/pandapower_hourly_pg_test.py -k tracer` | ⬜ pending |
| 05-04 T2 | 2 | OPS-05 | D-04, D-09, D-12 | `pytest backend/tests/pandapower_hourly_test.py` and `-k "soak or gap_lines"` (7) | ⬜ pending |
| 05-04 T3 | 2 | OPS-03, OPS-05, OPS-04 | D-01, D-03, D-05, D-09 | PG flags `pytest backend/tests/pandapower_hourly_pg_test.py`; regression database tier | ⬜ pending |
| 05-05 T1 (tracer) | 3 | OPS-02 | D-08 | `pytest backend/tests/pandapower_hourly_owner_test.py` | ⬜ pending |
| 05-05 T2 | 3 | OPS-02 | D-11 | `pytest backend/tests/pandapower_hourly_owner_test.py` (7) | ⬜ pending |
| 05-05 T3 | 3 | OPS-02 | D-05, D-14 | `pytest backend/tests/pandapower_hourly_leak_test.py`; quick set plus `pandapower_replay_output_test.py` | ⬜ pending |
| 05-06 T1 (tracer) | 4 | OPS-02, OPS-03, OPS-05 | D-07, D-10, D-14 | PG flags `pytest backend/tests/pandapower_hourly_rehearsal_test.py` | ⬜ pending |
| 05-06 T2 | 4 | OPS-01, OPS-02 | D-02, D-07, D-09, D-11, D-12, D-13 | `pytest backend/tests/pandapower_hourly_runbook_test.py backend/tests/pandapower_hourly_workflow_test.py` | ⬜ pending |
| 05-06 T3 | 4 | OPS-03 | D-02, D-03, D-11 | grep of `pandapower_live_write_decision.md` (Status Proposed, evidence paths) | ⬜ pending |
| 05-07 T1 (tracer) | 5 | OPS-01, OPS-02, OPS-03 | D-07 | PG flags, all Phase 5 test files; `private_leak_scan.py`; Local evidence grep | ⬜ pending |
| 05-07 T2 | 5 | OPS-01, OPS-02 | D-06, D-07, D-08, D-11 | manual (owner on GitHub, cron-job.org; resume message with printed lines) | ⬜ pending |
| 05-07 T3 | 5 | OPS-03, OPS-04 | D-01, D-02 | manual (owner decision) | ⬜ pending |
| 05-08 T1 (tracer) | 6 | OPS-03, OPS-04 | D-01, D-02 | grep of the dated `Decided:` line, Status, retention lines | ⬜ pending |
| 05-08 T2 | 6 | OPS-05 | D-02, D-04, D-09, D-12 | manual (owner flip and soak; `soak --since` exit 0) | ⬜ pending |
| 05-08 T3 | 6 | OPS-05 | D-04, D-09, D-12 | grep of `05-SOAK-RECORD.md` verdict line | ⬜ pending |

Sampling continuity: the longest run of tasks without an automated verify is two (05-07 T2 and T3); 05-08 T1 between them and 05-08 T2 is automated.

### Spec-less probe record (no SPEC.md for this phase)

The edge probe over OPS-01 to OPS-05 proposed 11 items. Resolved as explicit must-have truths: OPS-01 empty (05-01: absent or wrong-case variable is dry; no inputs), adjacency and ordering (05-03: same-hour dispatches queue, step order); OPS-02 boundary (05-01 size cap, 05-05 secret limit), precision (05-01: integer counts only), interruption (05-01: folder removed on exception and interrupt); OPS-04 empty, ordering and adjacency (05-02). Two rows were unclassified by the probe and stay flagged assumptions, reviewed by hand: OPS-03 (covered by 05-01, 05-04 and 05-08 truths, but the probe's own classification is open) and OPS-05 (covered by 05-02, 05-04 and 05-08 truths, same). Prohibitions recalled and kept, descriptor-less and unverified: no live-mode choice for a dispatcher (05-03), no run id or stored error text printed (05-05), no row deletion and no relaxing of the 24-slot rule (05-02, 05-08).

---

## Wave 0 Requirements

- [ ] `backend/tests/pandapower_hourly_workflow_test.py` — OPS-01 and OPS-02 workflow text (model on `dlr_live_workflow_test.py`)
- [ ] `backend/tests/pandapower_hourly_test.py` — gate, placeholder refusal, temp cleanup, vocabulary
- [ ] `backend/tests/pandapower_hourly_leak_test.py` — OPS-02 planted identifiers
- [ ] `backend/tests/pandapower_hourly_pg_test.py` — OPS-03 tables unchanged and the live tag
- [ ] `backend/tests/pandapower_soak_test.py` — OPS-05 function against an independent oracle
- [ ] A fixture helper that turns the public fixture into the base64 environment the runner reads (the placeholder mapping has `placeholder` true, which `prepare_run(..., allow_placeholder=False)` refuses, so the helper rewrites that field in a temp copy)

No framework install needed (pytest is already in `.venv`).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Workflow dispatches at all | OPS-01 | `workflow_dispatch` only fires for a workflow file on the default branch; Aaron merges to `main` when everything is finished (D-07) | After the merge, dispatch once from the Actions tab; then create the cron-job.org job |
| A branch dispatch does not run the job | OPS-01 | Needs GitHub | Dispatch from a non-`main` ref; the job shows as skipped |
| Secrets, variable and cron job exist | OPS-01, OPS-02 | The user's account has push but not admin rights; owner only | Owner creates the base64 secrets, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_PSSE_DB_URL` in `production`, then the `PANDAPOWER_LIVE` repository variable only at the flip |
| Real public log has no private value | OPS-02 | Needs a real log | Download one Actions log, scan with `private_leak_scan` needles from `data/private` (counts only) |
| Go-live decision | OPS-03 | Owner decision | At least 3 green dry runs, the log scan, a count comparison with the owner machine, then a dated line in the repo |
| 24 consecutive live slots | OPS-05 | Takes 24 hours on live | Owner runs the soak check with `since=<first live slot>`; record counts in `05-SOAK-RECORD.md` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (owner checkpoints are manual by nature: 05-07 T2, T3 and 05-08 T2)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no verify uses the MISSING sentinel; each task creates its own test file first)
- [x] No watch-mode flags
- [ ] Feedback latency < 30s for the quick set (to be measured at execution; the real-engine tracer of 05-01 takes 12 to 36 s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
