---
phase: 01-result-table-spec-and-rating-i-o
verified: 2026-10-28T00:00:00Z
status: human_needed
score: 4/4 must-haves verified
covered_files:
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-01-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-01-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-02-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-02-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-03-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-03-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-04-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-04-SUMMARY.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-05-PLAN.md"
  - ".planning/workstreams/pss-e-integration/phases/01-result-table-spec-and-rating-i-o/01-05-SUMMARY.md"
  - "backend/psse_job/__init__.py"
  - "backend/psse_job/constants.py"
  - "backend/psse_job/contract.py"
  - "backend/psse_job/job.py"
  - "backend/psse_job/ratings.py"
  - "backend/psse_job/redaction.py"
  - "backend/psse_job/run_record.py"
  - "backend/psse_job/units.py"
  - "backend/psse_job/writer.py"
  - "docs/data-science/decisions/psse_results_phase6_handoff.md"
  - "docs/data-science/schema/psse_results_v1.md"
  - "docs/data-science/schema/psse_results_v1.sql"
  - "docs/data-science/schema/psse_results_v1_checks.sql"
covered_digest: "v3:sha256:cdec6252eafcd90d47dd66f23fe28321f961df62215b8ba0a3ff0d81384d4087"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Phase 6's owner reviews docs/data-science/schema/psse_results_v1.md, psse_results_v1.sql and the hand-off note, and decides how Phase 6 takes the tables (amend 06-09, or a separate later plan such as 06-14)."
    expected: "Phase 6's plans take the four tables and the dlr_psse_writer grant from the spec (ROADMAP success criterion 1, last clause). Today no production-pipeline plan references psse_results; the hand-off is a proposal by design (D-01)."
    why_human: "The consumer of the spec is another owner's phase. This workstream may not edit production-pipeline files, so whether Phase 6 adopts the spec cannot be checked from this phase's code."
  - test: "Confirm which Python PSS/E bundles on the laptop and pin a psycopg version for it (Phase 3)."
    expected: "A psycopg release that supports that interpreter; writer.py uses only the psycopg 3.x API common to 3.1 to 3.3."
    why_human: "psycopg 3.3.6 (repo pin) needs Python 3.10+, and the PSS/E interpreter version is unknown. Only the laptop can answer it."
  - test: "Run psse_job under the interpreter PSS/E actually bundles."
    expected: "Imports and a fake-study run succeed."
    why_human: "psse_job is only syntax-checked against feature_version (3, 7) by psse_contract_test.py. No real 3.7 to 3.9 interpreter ran it."
---

# Phase 1: Result-Table Spec and Rating I/O Verification Report

**Phase Goal:** Phase 6 has what it needs to build the PSS/E result tables and write grant, and the job can choose each city's rating and record every run.
**Verified:** 2026-10-28
**Status:** human_needed (all four roadmap criteria verified in code; three items need a person)
**Re-verification:** No, initial verification

## Goal Achievement

### Observable Truths

| # | Truth (ROADMAP success criterion) | Status | Evidence |
|---|---|---|---|
| 1 | A written spec of the four result tables gives columns, units, keys, links to its run and to the `city_rating` rows used, and is in a form Phase 6 can take the tables and PSS/E grant from | VERIFIED (artifact side); adoption by Phase 6 goes to human review | `psse_results_v1.md` (245 lines) documents all four tables in DDL order with type, unit, "NULL when", meaning. Keys: `run_id` PK; composite FK `(run_id, run_outcome)` to `psse_run (run_id, outcome)`; soft link `(city, city_rating_valid_time)` plus `city_rating_computed_at`, plus the full `ratings_used` jsonb key table. `psse_results_v1.sql` (281 lines) holds the four tables, role `dlr_psse_writer`, INSERT and SELECT grants, RLS and column comments between BEGIN/END markers. The hand-off note lists the five Phase 6 steps and the 06-09 impact. I recomputed the sha256 of the marked region: `955f349d...6643`, equal to the pin in the hand-off note. The 06-09 claims check against `06-09-PLAN.md` ("exactly the two Phase 6 files", "exactly four migrations"). `git diff 82c0332..HEAD` touches no `supabase/`, `backend/config.py` or production-pipeline file (D-01, D-05). |
| 2 | Per city the newest `city_rating` row is used; static, recorded as such, when missing, older than 90 min or provisional | VERIFIED | `ratings.choose` and `select_ratings` (`backend/psse_job/ratings.py`), read over REST from `latest_rating` with `rating_amps` only (D-06). I ran it directly: fresh rows give `city_rating`; provisional rows give `static_fallback/provisional` for all four cities (today's state); a row exactly 90 min old is used; 90 min + 1 s gives `stale`; no rows give `missing`; a failing read gives `read_failed` with a redacted error and the run continues (D-02). Static amps come from `constants.py`, which `psse_contract_test.py` pins to `backend/config.py`. |
| 3 | Every run writes one run record (start/end, case id, per-city rating and source, outcome ok/fallback/failed, error), including a run whose study fails | VERIFIED | `job.run_once` builds the record via `run_record.build_run_record` for ok, fallback and failed, and writes it once, at the end, through `writer`. The DDL `psse_run` has `started_at`, `finished_at`, `case_id`, `ratings_used` (NOT NULL, all four cities, every outcome), `outcome` CHECK, `error`, and `failed_fields_ck` tying `outcome='failed'` to `error` and `failed_stage`. `test_record_failed_study_each_stage`, `test_record_unexpected_exception_is_internal` and `test_tracer_run_once_http_to_postgres` pass against local Postgres. The one case with no record is an unreachable database: `run_once` returns exit 3, and the spec documents that as the SCH-02 gap (D-04, no 'running' row). |
| 4 | A run that fails partway leaves no result set that looks complete: results all written, or the run is marked failed | VERIFIED | `writer.write_run` inserts the run row and all result rows in one `conn.transaction()`; on any failure it rolls back, then a second transaction writes a `failed` row with stage `write`. The DDL composite FK with `run_outcome in ('ok','fallback')` makes a result row under a failed run impossible. `validate_results` rejects incomplete or inconsistent study output before any write. Tests injecting failure at statements 1, 2, 6 and last leave zero result rows and one failed record; a duplicate key rolls back; a re-run with the same `run_id` never overwrites; the completeness checks SQL reports no offender. |

**Score:** 4/4 truths verified (0 present-but-behavior-unverified). The atomicity and rollback truths are behavior-dependent. The named failure-injection tests exercise them and passed.

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `docs/data-science/schema/psse_results_v1.sql` | Reference DDL, idempotent, role and grants | VERIFIED | Substantive. Applied to a throwaway Postgres 18.6 by `psse_schema_pg_test.py`, twice, with Supabase legacy default grants. |
| `docs/data-science/schema/psse_results_v1_checks.sql` | Read-only completeness checks | VERIFIED | Five checks; exercised by the PG tests. |
| `docs/data-science/schema/psse_results_v1.md` | Spec | VERIFIED | Kept equal to the DDL by `psse_schema_doc_test.py`. |
| `docs/data-science/decisions/psse_results_phase6_handoff.md` | Phase 6 hand-off with sha256 pin | VERIFIED | Pin recomputed independently and matches. |
| `backend/psse_job/` (constants, contract, ratings, units, redaction, run_record, writer, job) | Rating I/O, record, atomic writer | VERIFIED | All substantive and wired: `job` to `ratings`, `run_record`, `writer`, `contract`. No `numpy`, `pandas`, `config` or `supabase_store` import. |
| `backend/tests/psse_*_test.py`, `psse_fakes.py`, `psse_local_pg.py` | Tests and fixture | VERIFIED | 243 tests, all passed. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `job.run_once` | `ratings.select_ratings` | one fetch, one clock | WIRED | `job.py` line 97. |
| `job.run_once` | `run_record.validate_results` and `build_run_record` | after the study, before any write | WIRED | Failure becomes stage `validate_results`. |
| `job.run_once` | `writer.write_run` or `record_failure` | `connect()` called only after the study | WIRED | `test_no_write_before_the_study_finishes` passes. |
| `contract.PSSE_RUN_COLUMNS` and the other tuples | DDL columns | drift test | WIRED | `psse_run_record_test.py` contract tests. |
| `constants` vocabularies | DDL CHECK lists | drift test | WIRED | `psse_schema_doc_test.py`. |
| `constants` static ratings and subconductors | `backend/config.py` | drift test | WIRED | `psse_contract_test.py`. |
| Hand-off sha256 | DDL marked region | recomputed in test and by me | WIRED | Equal. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `psse_run.ratings_used` | per-city choice | `select_ratings` over rows read from the REST view (loopback fake server in tests) | Yes | FLOWING |
| `psse_dispatched_capacity` rows | study output | Phase 2's study (injected; not built here) | Fake study in tests only | By design: `job.run_once` takes the study as a parameter, and `contract.py` states the study contract for Phase 2. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| IN-01 matrix (fresh, provisional, 90 min, 90 min + 1 s, missing, read failed) | Own script against `psse_job.ratings` | Outputs as in truth 2 | PASS |
| Hand-off sha256 equals the DDL region | Own recomputation, LF-normalised | `955f349d2df66394dbec4378ddcc2d9eb61f7e37bd4eda8de4b70de16c3a6643` | PASS |
| Whole PSS/E suite on local Postgres | `PSSE_REQUIRE_PG=1 DLR_TEST_PG_AUTOSTART=1 .venv/Scripts/python.exe -m pytest -q -p no:cacheprovider -rs backend/tests/psse_*_test.py backend/tests/secret_scan_test.py` | 243 passed, 0 skipped, 108.8 s | PASS |

### Probe Execution

Step 7c: SKIPPED. The plans declare no `probe-*.sh`, and no `scripts/*/tests/probe-*.sh` is relevant to this phase.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| DBX-01 | 01-01, 01-03 | Spec of four tables handed to Phase 6, no standalone migration | SATISFIED (hand-off made; adoption is Phase 6's step, see human item 1) | Spec, DDL, checks, hand-off exist and agree. No `supabase/migrations` change. |
| IN-01 | 01-02, 01-05 | Newest row, static when missing, older than 90 min or provisional, recorded | SATISFIED | Truth 2. |
| WB-01 | 01-04, 01-05 | One run record per run, also on failure | SATISFIED | Truth 3. |
| WB-02 | 01-01, 01-04, 01-05 | All written or run marked failed | SATISFIED | Truth 4. |

No orphaned requirement: REQUIREMENTS.md maps DBX-01, IN-01, WB-01 and WB-02 to this phase and all four are claimed by plans. DBX-02 belongs to Phase 3.

### Anti-Patterns Found

None. No `TBD`, `FIXME`, `XXX`, `TODO`, `HACK`, "not implemented" or placeholder in any phase file. No credential, URL or key in committed files (the only connection strings are loopback test URLs).

### Human Verification Required

1. **Phase 6 owner reviews the spec and hand-off.** Test: read `psse_results_v1.md`, `psse_results_v1.sql` and the hand-off note, then choose option (a) or (b) for 06-09. Expected: Phase 6's plans take the four tables and the `dlr_psse_writer` grant from the spec. Why human: the consumer is another owner's phase, and no production-pipeline plan references the spec yet (that is by design, D-01).
2. **psycopg against the PSS/E interpreter.** Test: confirm PSS/E's bundled Python on the laptop and pick the psycopg pin. Expected: a supported pairing. Why human: psycopg 3.3.6 needs Python 3.10+, and the PSS/E interpreter is unknown (Phase 3).
3. **`psse_job` under the PSS/E interpreter.** Test: run the fake-study path under that interpreter. Expected: runs without a syntax or import error. Why human: only syntax-checked against 3.7 so far.

### Gaps Summary

No gaps. All four ROADMAP success criteria are met in the code, DDL, docs and tests, not only in the SUMMARY claims.

Notes, none blocking:
- **Environment limit:** the full repo suite cannot be collected in this minimal venv (numpy, pandas, requests, joblib, matplotlib and fcntl are missing). This is pre-existing and not a Phase 1 gap. Only the PSS/E suite and `secret_scan_test.py` were run.
- **Completeness is a check, not a constraint:** the DDL does not force an `ok` run to have four dispatch rows. `psse_results_v1_checks.sql` finds an offender, and the single-transaction writer plus `validate_results` prevent one. A role holding INSERT could still write a run row alone. The spec documents this.
- **Unrecorded runs by design:** with the database unreachable, a run leaves no row (exit 3) and shows as a gap (SCH-02, Phase 3).

---

_Verified: 2026-10-28_
_Verifier: Claude (gsd-verifier)_
