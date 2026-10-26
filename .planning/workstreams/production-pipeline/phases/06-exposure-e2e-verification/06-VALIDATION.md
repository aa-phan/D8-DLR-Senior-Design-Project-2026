---
phase: "06"
slug: "exposure-e2e-verification"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-25"
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `06-RESEARCH.md` § Validation Architecture (refreshed 2026-10-25).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (repo `.venv`, Python 3.12); live checks are stdlib scripts and SQL run by the owner |
| **Config file** | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| **Quick run command** | `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/e2e_readonly_test.py backend/tests/e2e_soak_report_test.py backend/tests/example_read_ratings_test.py backend/tests/secret_scan_test.py` |
| **Local-Postgres run** | `DLR_TEST_PG_AUTOSTART=1 /Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/expose_migration_test.py backend/tests/soak_log_migration_test.py` |
| **Full suite command** | `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider` |
| **Estimated runtime** | ~60 seconds offline; local-PG adds ~30 seconds |

Offline tests run with no network and no keys. Live checks read `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (and `SUPABASE_DB_URL` for owner SQL) from the environment, never from `.env` inside tests, and never print them.

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command plus the local-Postgres run
- **Before `/gsd-verify-work`:** Full suite green; live read, hidden-table and write checks, example smoke and trace table recorded; dry-soak report reviewed; 72 h soak report with zero unexplained breaches; alarm drill done; permission re-check on or after 2026-10-31 recorded
- **Max feedback latency:** 90 seconds

---

## Per-Requirement Verification Map

The planner fills task IDs; this map seeds them from research.

| Requirement | Behavior (plain English) | Test Type | Automated Command | File Exists | Status |
|-------------|--------------------------|-----------|-------------------|-------------|--------|
| API-01 | The 34 view columns equal the documented list, in order (drift guard vs `LATEST_COLUMNS`) | offline text | `pytest backend/tests/expose_migration_test.py -k columns` | ❌ W0 | ⬜ pending |
| API-01 | The public key sees exactly one newest row per city; the view is security_invoker; dropping the read policy gives 0 rows | local PG | local-Postgres run | ❌ W0 | ⬜ pending |
| API-01 | `is_provisional` is true for the real `config.RATING_BASIS` + `config.RATING_CONFIG_VERSION` and a backfill label; false for a lifted pair (D-03 as revised) | local PG | local-Postgres run | ❌ W0 | ⬜ pending |
| API-01 | `is_stale` equals `age_minutes > 90` and matches `assert_fresh` at the 90-minute boundary | local PG | local-Postgres run | ❌ W0 | ⬜ pending |
| API-01 | `verify_exposure.sql` all true; SELECT-only on two objects; writes 42501; other tables, `pipeline_run` and `ops` unreadable | local PG + live SQL | local-Postgres run; owner pastes live result | ❌ W0 | ⬜ pending |
| API-02 | Each example lists four cities and pages 2,500 rows; Python example parses PostgREST timestamps, is stdlib-only, parses as 3.7 syntax, runs on 3.9.6 and 3.12 | offline (fake HTTP server) | `pytest backend/tests/example_read_ratings_test.py` | ❌ W0 | ⬜ pending |
| API-02 / D-10 | No project URL, pooler user or publishable key anywhere in the repo; examples read both env vars | offline | `pytest backend/tests/secret_scan_test.py` | ✅ extend | ⬜ pending |
| API-02 | Examples run as written against the real project | live smoke (owner) | the three example commands with env set | ❌ W0 | ⬜ pending |
| E2E-01 | Trace joins cron-job.org execution → run → rows → REST on stored columns; a mismatch is detected | unit + live | `pytest -k trace_compare`; live `python backend/e2e_trace.py --run-id <id>` | ❌ W0 | ⬜ pending |
| E2E-02 | Dry soak: write lag, peak age (from `first_written_at`), slot verdicts, exit codes | unit | `pytest backend/tests/e2e_soak_report_test.py -k dry` | ❌ W0 | ⬜ pending |
| E2E-02 | Soak report: probe gaps, breaches, derived deploy annotations, unexplained breach → non-zero exit | unit | `pytest backend/tests/e2e_soak_report_test.py -k soak` | ❌ W0 | ⬜ pending |
| E2E-02 | `log_freshness` breach equals `age_seconds > 5400`; a missing city logs a breach | local PG | local-Postgres run | ❌ W0 | ⬜ pending |
| E2E-03 | Public-key INSERT/UPSERT/PATCH/DELETE refused, data unchanged; any 2xx write fails the check | unit + live | `pytest backend/tests/e2e_readonly_test.py`; live `python backend/e2e_verify_readonly.py --check-writes` | ❌ W0 | ⬜ pending |
| D-09 | Post-10-30 re-check covers read, hidden, write, `verify_exposure.sql` and the `consumers_cannot_write` smoke | doc + live (owner) | runbook step list; smoke workflow run | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/expose_migration_test.py`, `backend/tests/local_pg.py` — 34-column contract, real-label `is_provisional`, boundary, grants
- [ ] `backend/tests/e2e_readonly_test.py`, `backend/tests/fake_postgrest.py`, `backend/supabase_rest.py` (with URL/key redaction)
- [ ] `backend/tests/e2e_soak_report_test.py` — dry and soak modes
- [ ] `backend/tests/example_read_ratings_test.py` — fake server, paging, syntax and Python-version checks
- [ ] Extend `backend/tests/secret_scan_test.py` — project host, pooler user, publishable key; env-gated owner test

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Migration applied to the live project | API-01 | Live action, owner checkpoint after 05-08 | Owner applies, then pastes `verify_exposure.sql` output |
| Probe smoke check before the 72 h clock | E2E-02 | Needs live pg_cron and cron-job.org | ≥ 3 successful pg_cron probes, ≥ 2 alarm runs with HTTP 200, drill failure and recovery emails |
| Dry-soak review | E2E-02 | Owner judgement gate (D-07) | Owner reviews the dry report before the clock starts |
| 72 h soak sign-off | E2E-02 | Needs 72 h of live time | Export, explain every breach, owner signs off |
| Alarm emails | E2E-02 / D-14 | External service | Drill job on `assert_fresh?max_age_minutes=0` |
| Permission re-check on or after 2026-10-31 | E2E-03 / D-09 | Depends on Supabase's 10-30 change | Run the runbook list and the smoke workflow |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
