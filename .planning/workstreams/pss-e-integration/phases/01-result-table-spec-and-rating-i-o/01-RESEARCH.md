# Phase 1: Result-Table Spec and Rating I/O - Research

**Researched:** 2026-10-27
**Domain:** Postgres/Supabase table and grant design, REST read of `latest_rating`, atomic write-back, amps-to-MVA unit handling (no `psspy` in this phase)
**Confidence:** HIGH on repo facts, unit arithmetic and the Phase 6 conflicts (all read this session); MEDIUM on Supabase platform behaviour (pooler, custom roles); LOW on PSS/E-side conventions (forum sources only)

<user_constraints>
## User Constraints

No CONTEXT.md exists for this phase (the user chose to continue without one). The constraints below come from the spawn prompt, REQUIREMENTS.md and STATE.md. There are no locked decisions beyond them, so everything else is Claude's discretion and is given as a recommendation.

### Locked (from REQUIREMENTS.md / STATE.md / spawn prompt)
- No standalone migration in this workstream. The four result tables and the PSS/E write grant ship in production-pipeline Phase 6's migration; this phase hands Phase 6 a spec (DBX-01).
- Dashboard / F7 is out of scope. Power Systems owns the case and the branch mapping. `psspy` API choices belong to the implementer.
- Static rating is the fallback when a `city_rating` row is missing, older than 90 minutes, or provisional (IN-01).
- Outcome vocabulary is exactly `ok`, `fallback`, `failed` (WB-01).
- The job reads ratings only through Phase 6's access and writes only to the PSS/E result tables; its credential cannot change `city_rating` (DBX-02, enforced in Phase 3 but the design is settled here).
- Git: agents must not run any git write operation and must not commit. Write only the RESEARCH.md.

### Claude's Discretion
Table and column design, key design, atomicity mechanism, source/reason vocabulary, code location, validation strategy.

### Deferred / Out of Scope
Dashboard views of results (F7); always-on host; `psspy` calls, branch mapping, load flow, N-1 and voltage-margin computation (Phase 2); scheduling, credential scoping proof and the setup guide (Phase 3).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DBX-01 | Written spec of the four PSS/E result tables handed to Phase 6 so tables and grant ship in its migration | "Recommended table spec", "Handoff to Phase 6", "Conflicts with Phase 6's existing plans" |
| IN-01 | Newest `city_rating` row per city; static when missing/older than 90 min/provisional; recorded as such | "Rating selection (IN-01)" and the unit section (which fields to read) |
| WB-01 | One run record per run (start/end, case id, per-city rating + source, outcome, error), also on study failure | `psse_run` columns, "Run record and failed-run behaviour" |
| WB-02 | Results all written or run marked failed; no partial set looks complete | "Atomic write (WB-02)": one transaction + composite FK + verification query |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

No `CLAUDE.md` or `.claude/` directory exists in the repo [VERIFIED: `ls CLAUDE.md .claude` returned "No such file"]. Conventions come from `.planning/codebase/CONVENTIONS.md` and `TESTING.md` instead (treat as binding house style):
- Modules `snake_case`, feature prefix allowed; Google-style docstrings with a module docstring; plain `assert`s, no test classes; tests live in `backend/tests/` as `<module>_test.py`; `pytest.ini` has `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` [VERIFIED: pytest.ini].
- Phase 4/6 house rules that apply here: migrations are additive and never edited once applied (sha256-pinned); tools never print the DB URL, host or project reference; commit with explicit paths; every live action is an owner checkpoint (executor builds and tests offline, never applies migrations).
- User rule for this session: no git write commands by agents.

## Summary

Phase 1 produces three things: (1) a schema spec plus a reference DDL for four tables that Phase 6 will copy into a migration, (2) a rating-selection function that applies IN-01 to the Phase 6 `latest_rating` view, and (3) a run-record builder and an atomic writer. None of it needs `psspy`. The decisive design findings are:

**Phase 6 has no PSS/E work in it today.** All 13 Phase 6 plans and `06-CONTEXT.md` were read. They contain no PSS/E result tables, no PSS/E role and no write grant; `06-CONTEXT.md` lists "dashboard or PSS/E-side code" as not in scope, and production-pipeline `REQUIREMENTS.md` lists "PSS/E results back into the database (F7)" as out of scope. Phase 6 has not started (STATE.md: "Not started", 0 of 13 plans done, no `*-SUMMARY.md` and no expose migration on disk). So the handoff is not "tweak a plan in progress": it needs one new Phase 6 plan (suggested `06-14`) plus a wording fix in `06-09` (which asserts the push lists "exactly the two Phase 6 files"). Phase 6's access design (anon + `authenticated` get SELECT on exactly `city_rating` and `latest_rating`, `verify_exposure.sql` fails on any other anon/authenticated grant) means the PSS/E write credential must be a separate Postgres role, not `anon`/`authenticated`.

**Unit pitfall is real and large.** `city_rating.rating_amps` and `static_rating_amps` are per conductor, and `rating_mw` is computed from the per-conductor amps with power factor 0.95; it is neither per circuit nor an apparent power. For AUSTIN the stored `rating_mw` for the static rating is 1036.0 MW, while the per-circuit apparent power PSS/E should receive is 2181.1 MVA (2.1x higher). The job must read `rating_amps` (never `rating_mw`) and compute `sqrt(3) x kV x (amps x subconductors) / 1000` MVA with no power factor.

**Atomicity is easiest through a direct Postgres transaction** (same pooler pattern as the existing `dlr_writer`), with `psse_run` written in the same transaction as the result rows and a composite foreign key that makes it impossible for a result row to reference a `failed` run. The catch is interpreter support: `psycopg==3.3.6` (the repo pin) needs Python >= 3.10, while PSS/E's Python is unconfirmed (3.7 to 3.9 is possible) and Phase 6 D-11 targets 3.7+. The write code must therefore use only the psycopg 3.x API common to 3.1 to 3.3 and the Phase 3 setup guide must pin psycopg per interpreter. Reads stay on stdlib REST with the publishable key (Phase 6's access), which also satisfies DBX-02's "reads only through Phase 6's access".

**Primary recommendation:** Hand Phase 6 one reference DDL (`psse_run`, `psse_contingency_result`, `psse_dispatched_capacity`, `psse_voltage_margin`, role `dlr_psse_writer` with INSERT + SELECT on those four tables only, no grant on `city_rating`, no API-role access), proven by Phase 1's own local-Postgres writer tests; build the job as a stdlib-first package `backend/psse_job/` that reads `latest_rating` over REST, trusts the server's `is_stale`/`is_provisional` flags OR-ed with a client age check, falls back to `config.STATIC_RATINGS` on any doubt, and writes run + results in one transaction (run record alone, outcome `failed`, when the study fails).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Rating selection + static fallback (IN-01) | Job (laptop process) | Database (view flags) | The decision must be made where the study runs; the view supplies one shared definition of stale/provisional |
| Amps-to-MVA conversion | Job | — | PSS/E branch rating units are a study-side concern; DB stores only the result and the factors used |
| Staleness / provisional definition | Database (`latest_rating` columns, Phase 6) | Job (conservative re-check) | One definition shared with the dashboard and the freshness alarm |
| Result persistence and all-or-nothing (WB-02) | Database (transaction, FK, grants) | Job (builds the whole result in memory first) | Atomicity belongs to the DB; the job must not write incrementally |
| Run record (WB-01) | Database (`psse_run`) | Job | Written by the job, immutable afterwards (INSERT-only grant) |
| Credential scoping (DBX-02) | Database (role grants) | Job (separate env vars for read vs write) | Least privilege is a grant property, not code |
| Gap visibility (SCH-02, Phase 3) | Database (query over `psse_run.slot_time`) | Scheduler | Spec must include `slot_time` and an index so the query is possible |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib (`urllib`, `json`, `datetime`, `re`, `os`, `hashlib`) | 3.7+ syntax target | REST read of `latest_rating`, record building | Phase 6 D-11 targets PSS/E Python 3.7+ with no third-party packages for the read path [VERIFIED: 06-CONTEXT.md D-11] |
| `psycopg` (+ `psycopg-binary`) | repo pin 3.3.6; 3.1.20 (>=3.7) and 3.2.13 (>=3.8) exist | Atomic transactional write (`conn.transaction()`) | Already the project's Postgres driver, owner-approved at plan 04-01 [VERIFIED: requirements.txt comment]; `requires_python` per version [VERIFIED: pypi.org JSON: 3.3.6 ">=3.10", 3.2.13 ">=3.8", 3.1.20 ">=3.7"] |
| `backend/config.py` | in repo | `STATIC_RATINGS`, `SUBCONDUCTORS_PER_PHASE`, `LOCATIONS`, `LINE_VOLTAGE_KV` | No imports at all, so importable on the laptop without pandas [VERIFIED: grep of `import` in config.py found none] |
| pytest | 9.0.3 (repo pin) | Tests | Existing framework [VERIFIED: requirements.txt] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Phase 6 `backend/supabase_rest.py` (planned 06-04) | not yet built | Stdlib PostgREST client: `config_from_env`, `redact_rest`, `request`, `get_all`, `parse_ts` | Reuse once 06-04 lands; until then the job carries a tiny equivalent behind an injectable `fetch` callable |
| Phase 6 `backend/tests/local_pg.py` (planned 06-01) and `fake_postgrest.py` (06-04) | not yet built | Throwaway local Postgres harness; fake REST server | Reuse if present; otherwise copy the fixture pattern from `backend/tests/supabase_live_test.py:82-124` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct Postgres write as role `dlr_psse_writer` | PostgREST write with a self-minted JWT carrying `role: dlr_psse_writer` | Works over stdlib `urllib` on any Python 3.7+, but needs `grant dlr_psse_writer to authenticator` and a JWT signed with the project's JWT secret or an imported signing key; Supabase's legacy-secret to signing-keys transition and a July 2025 Data API validation change broke some custom JWTs [CITED: supabase.com/docs/guides/auth/signing-keys; supabase.com/changelog/38771]. Use only if the laptop interpreter cannot run any psycopg 3.x |
| `dlr_psse_writer` role | Supabase `service_role` / secret key | Bypasses RLS and could change `city_rating`; violates DBX-02. Rejected |
| `dlr_psse_writer` role | `authenticated` role via a dedicated Supabase Auth user | Would put grants on `authenticated`, which Phase 6's `verify_exposure.sql` check `anon_authenticated_grants_are_select_on_two_objects_only` forbids, and any signed-in user would inherit them. Rejected |
| One transaction | Status-flagged rows written over several REST calls (`running` then PATCH to final) | Needs UPDATE grant, a fourth outcome value (`running`) and readers that must remember to filter; a crash leaves `running` rows. Only a fallback if only REST is possible |

**Installation:** no new package for this phase. The existing pin stays in `requirements.txt`. For the laptop, Phase 3's guide must pick the psycopg version for PSS/E's interpreter (3.1.20 for 3.7, 3.2.13 for 3.8/3.9, 3.3.6 for >= 3.10).

**Version verification:**
```
pypi.org/pypi/psycopg/3.3.6/json   -> requires_python ">=3.10", uploaded 2026-09-18
pypi.org/pypi/psycopg/3.2.13/json  -> requires_python ">=3.8"
pypi.org/pypi/psycopg/3.1.20/json  -> requires_python ">=3.7"
```
`psycopg`'s `requires_python` is a present, bounded constraint, so it earns VERIFIED.

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| psycopg | PyPI | long-established (3.3.6 published 2026-09-18) | unknown to the seam | psycopg.org | SUS (`unknown-downloads` only; seam cannot read PyPI download counts) | Already in `requirements.txt` with owner-confirmed legitimacy at plan 04-01 Task 1 (2026-10-21). No new install in Phase 1. Planner adds a `checkpoint:human-verify` only if Phase 3 installs a different version on the laptop |
| psycopg-binary | PyPI | same | unknown | psycopg.org | SUS (same reason) | Same disposition; must equal the psycopg version |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** psycopg, psycopg-binary (signal is unknown download counts, not age or scripts; both already owner-approved). Evidence: `gsd-tools query package-legitimacy check --ecosystem pypi psycopg psycopg-binary` run this session.
Phase 1 adds no other package: stdlib plus pytest only.

## Architecture Patterns

### System Architecture Diagram

```
 Task Scheduler (Phase 3)          Supabase (hosted)
        |                      +----------------------------------+
        v                      |  public.latest_rating (Phase 6)  |
  python -m psse_job           |  anon: SELECT only               |
        |                      +----------------+-----------------+
        | 1. start: run_id, started_at          ^ HTTPS GET, publishable key (SUPABASE_URL,
        v                                       | SUPABASE_PUBLISHABLE_KEY), select= only needed cols
  ratings.select_ratings(fetch, now) ----------+
        |   per city: row ok?  --yes--> source city_rating
        |             missing/stale/provisional/read_failed/invalid --> source static_fallback
        |             (static = config.STATIC_RATINGS x SUBCONDUCTORS_PER_PHASE)
        v
  study (Phase 2, psspy)  --exception / mapping miss / no convergence--> failed result
        |
        v
  run_record.build(...)  outcome: failed | fallback (any static) | ok (all city_rating)
        |
        v   one connection, role dlr_psse_writer (SUPABASE_PSSE_DB_URL, session pooler)
  writer.write_run(conn, record, results):
        BEGIN
          insert psse_run ... on conflict (run_id) do nothing returning run_id
          (no row returned => already written => stop, success)
          insert psse_dispatched_capacity x4, psse_voltage_margin x4, psse_contingency_result xN
        COMMIT   (any error => ROLLBACK, then a NEW transaction writes psse_run outcome=failed)
        |
        v
  exit code 0 (ok/fallback) or non-zero (failed / could not record)  --> Task Scheduler result
```

### Recommended Project Structure
```
backend/
  psse_job/                       # stdlib + (optional) psycopg only; imports config, nothing else of backend
    __init__.py
    contract.py                   # column tuples, enums (OUTCOMES, SOURCES, REASONS, VIOLATION_KINDS) = mirror of the DDL
    ratings.py                    # IN-01: select_ratings(fetch, now, static=...) -> {city: RatingChoice}
    rest_read.py                  # fetch_latest_rating(...) over urllib; replaced by supabase_rest once 06-04 lands
    run_record.py                 # build_run_record(...), outcome rule, redact(), ratings_used json
    writer.py                     # write_run(conn, record, results) atomic; record_failure(conn, record)
  tests/
    psse_contract_test.py         # DDL <-> contract drift, 3.7 syntax gate
    psse_ratings_test.py          # IN-01 matrix, no network
    psse_run_record_test.py       # outcome rule, redaction, failed-run record
    psse_writer_test.py           # local-Postgres atomicity/idempotency/privilege proofs (skips without autostart)
    psse_schema_doc_test.py       # spec doc <-> DDL drift (mirrors supabase_schema_doc_test.py)
docs/data-science/schema/
  psse_results_v1.md              # THE SPEC (handed to Phase 6)
  psse_results_v1.sql             # reference DDL (NOT a migration; Phase 6 copies it)
```
Why a sub-package and not flat `backend/psse_*.py`: the backend is flat by convention, but this job runs on a different machine with a different interpreter; a package makes the laptop boundary explicit ("needs `backend/config.py` and `backend/psse_job/` only"). `pythonpath = backend` makes `import psse_job` work in tests with no config change [VERIFIED: pytest.ini]. The module name must not import `supabase_store` (it imports pandas at module top, `supabase_store.py:50`), so `redact` is re-implemented small and tested for equal behaviour on the shared cases.

### Pattern 1: Select with conservative fallback (IN-01)
**What:** One pure function decides per city; every doubt maps to static. **When:** every run, before the case is touched.
```python
# Source: derived from backend/config.py (STATIC_RATINGS, SUBCONDUCTORS_PER_PHASE) and the Phase 6 latest_rating contract
SOURCE_ROW, SOURCE_STATIC = "city_rating", "static_fallback"
STALE_AFTER_MINUTES = 90

def choose(city, row, now, static_amps):
    """row: dict from latest_rating or None. Returns (source, reason, amps_per_conductor, row_or_None)."""
    if row is None:
        return SOURCE_STATIC, "missing", static_amps, None
    try:
        amps = float(row["rating_amps"])
        valid = parse_ts(row["valid_time"])
        server_stale = row["is_stale"]
        server_prov = row["is_provisional"]
    except (KeyError, TypeError, ValueError):
        return SOURCE_STATIC, "invalid", static_amps, None        # contract drift is never trusted
    if not (amps > 0 and amps < float("inf")) or not isinstance(server_stale, bool) or not isinstance(server_prov, bool):
        return SOURCE_STATIC, "invalid", static_amps, None
    client_age_min = (now - valid).total_seconds() / 60.0
    if server_stale or client_age_min > STALE_AFTER_MINUTES:       # OR: either side saying "old" wins
        return SOURCE_STATIC, "stale", static_amps, row
    if server_prov:
        return SOURCE_STATIC, "provisional", static_amps, row
    return SOURCE_ROW, None, amps, row
```
Reason precedence when several apply: `missing`, `invalid`, `stale`, `provisional` (so `provisional` is recorded only for a fresh row, which makes the real reason visible once rows become fresh). `read_failed` is assigned to all four cities when the HTTP read raises or returns a non-2xx status; the redacted error goes to the run record.

### Pattern 2: Atomic write, then failure record in a fresh transaction
```python
# Source: same API pattern as backend/supabase_store.py upsert_run (conn.transaction()), psycopg 3.1-3.3 common subset
def write_run(conn, record, results):
    try:
        with conn.transaction():                       # BEGIN ... COMMIT, ROLLBACK on any exception
            row = conn.execute(INSERT_RUN_SQL, record_params).fetchone()   # ... on conflict (run_id) do nothing returning run_id
            if row is None:
                return "already_recorded"              # a retry after a lost commit acknowledgement
            for sql, rows in ((INSERT_DISPATCH, results.dispatch), (INSERT_MARGIN, results.margins), (INSERT_CONTINGENCY, results.contingencies)):
                for params in rows:
                    conn.execute(sql, params)
        return "written"
    except Exception as exc:
        failure = redact(str(exc))
    record_failure(conn, record, stage="write", error="result write failed: " + failure)   # new transaction: psse_run only, outcome 'failed'
    raise WriteFailed(failure)
```

### Anti-Patterns to Avoid
- **Reading `rating_mw`:** it is per conductor and includes power factor; it understates the per-circuit MVA by about 2.1x for the three bundled cities (table below).
- **Writing children before knowing the outcome / writing progressively:** a crash would leave a result set with no run record. Build everything in memory, then one transaction.
- **Deriving "complete" from row counts alone:** use the composite FK plus the verification query.
- **A second definition of stale/provisional in the job:** trust the view's flags; the client age check may only make the decision more conservative.
- **Importing `supabase_store` on the laptop:** pulls pandas, `ampacity_forecast`, `city_point` and more.
- **Using the pre-fix hour CHECK form** `valid_time = date_trunc('hour', valid_time)` on `slot_time`: Phase 4's own review (IN-06) found it evaluates in the session time zone; use the UTC form from day one.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Stale and provisional definition | A client-side word match on `rating_basis` or own age rules | `latest_rating.is_stale` / `is_provisional` (Phase 6 D-02, D-03) | One shared definition; Phase 7's go flips `is_provisional` without a contract change |
| All-or-nothing across four tables | Multi-request REST orchestration or app-level compensation | One Postgres transaction (`conn.transaction()`) | Native ACID; psycopg rolls back on any exception |
| Preventing a result row under a failed run | Triggers or app checks only | Composite FK `(run_id, run_outcome) -> psse_run(run_id, outcome)` with `run_outcome in ('ok','fallback')` | Declarative, testable with one failing insert (23503) |
| Secret/URL redaction | New regexes | Port the small `redact` behaviour from `supabase_store.redact` (URL regex, `key=value` regex, known-secret replacement, cut after redaction) | Existing rules are already reviewed (DB-04) |
| Timestamp parsing for PostgREST | `datetime.fromisoformat` on raw strings | The tested `parse_ts` from 06-RESEARCH (Python < 3.11 rejects `Z` and odd fractions) | Phase 6 Pitfall 3 |
| Paging past the 1000-row cap | Single GET | Not needed for `latest_rating` (4 rows); if history is ever read, use Phase 6 `get_all` | — |

**Key insight:** the hard parts (freshness semantics, secret hygiene, local-Postgres harness, REST client) are already being built by Phase 6; this phase's value is a correct table spec and a conservative decision function, so reuse beats rewriting and the job should keep its own code small.

## Runtime State Inventory

Not applicable: this is a greenfield phase (new tables, new package); nothing is renamed or migrated. Stated explicitly: stored data none, live service config none, OS-registered state none (the Task Scheduler entry is Phase 3), secrets/env vars new names only (`SUPABASE_PSSE_DB_URL`; `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are Phase 6's), build artifacts none.

## Recommended Table Spec (the content of `psse_results_v1.md` and the reference DDL)

Conventions followed, each verified in the Phase 4 migrations read this session: `create table if not exists public.<t>`; named constraints `<table>_<col>_ck` and `<table>_pk`; unit-first `comment on column` text (`'none (identifier): ...'`, `'amperes (A), per conductor: ...'`); `schema_version integer not null default 1`; DB-set timestamps `date_trunc('second', now())`; RLS on; explicit `revoke all ... from anon, authenticated`; role created inside a `do $$ ... $$` guard without a credential (the owner sets the password out of band); `first_written_at`-style columns set by the DB, never by the client; additive-only afterwards; the numeric CHECK `x > 0 and x < 'Infinity'::float8` also rejects NaN (Postgres orders NaN above Infinity) [VERIFIED: 20261019000000_create_city_rating.sql:29 `check (rating_amps > 0 and rating_amps < 'Infinity'::float8)`].

City keys are exactly `('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO')` [VERIFIED: 20261019000000_create_city_rating.sql:26, `check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO'))`]. The UTC hour check form is [VERIFIED: 20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql:20] `check ((valid_time at time zone 'UTC') = date_trunc('hour', valid_time at time zone 'UTC'))`.

### 1. `public.psse_run` (run record, WB-01) — one row per run, immutable
| Column | Type | Unit | NULL when | Meaning |
|---|---|---|---|---|
| `run_id` | text PK | none (identifier) | never | `psse-<UTC yyyymmddThhmmssZ>-<8 hex>`, generated once at job start, reused on retry (idempotency key). Same style as `supabase_store.run_context`'s `local-<UTC>-<id>` |
| `slot_time` | timestamptz | UTC instant | never | Hour floor of `started_at` in UTC (mirrors OD-7). Whole-UTC-hour CHECK in the UTC form. Index `psse_run_slot_time_idx (slot_time desc)` supports SCH-02's gap query |
| `started_at` | timestamptz | UTC instant | never | Job process start |
| `finished_at` | timestamptz | UTC instant | never | End of study, just before the write; CHECK `finished_at >= started_at` |
| `outcome` | text | none (category) | never | CHECK in `('ok','fallback','failed')`. `ok`: all four cities used a `city_rating` row. `fallback`: completed, at least one city on static. `failed`: no results exist for this run |
| `failed_stage` | text | none (label) | outcome is not `failed` | One of `read_ratings`, `load_case`, `mapping`, `load_flow`, `contingency`, `voltage_margin`, `write`, `internal`. CHECK ties it to `outcome = 'failed'` |
| `error` | text | none (text) | outcome is not `failed` | Redacted, cut to 1000 characters after redaction (same rule as `pipeline_run` errors, `_RUN_ERROR_MAX_CHARS = 1000`). CHECK `(outcome = 'failed') = (error is not null)` |
| `case_id` | text | none (label) | never | Label of the case (file name without directory, or Power Systems' own id). Never a path. Known from config, so present even when the load fails |
| `case_sha256` | text | none (identifier) | case not readable | Lowercase hex sha256 of the case file bytes; CHECK `~ '^[0-9a-f]{64}$'` (same recipe as the DB-06 identity columns) |
| `mapping_sha256` | text | none (identifier) | not yet loaded | sha256 of the city-to-branch configuration file |
| `rate_set` | text | none (label) | study not reached | Which PSS/E rate set received the DLR value (for example `RATEA`); Power Systems' choice (open question 4) |
| `ratings_used` | jsonb | see below | never | Object with exactly the four city keys (CHECK `ratings_used ?& array['AUSTIN','CORPUS_CHRISTI','MIDLAND','EL_PASO']` and `jsonb_typeof = 'object'`), written for every outcome including `failed` |
| `n_contingencies` | integer | count | outcome `failed` before screening | Contingencies screened (completeness reference) |
| `n_contingencies_with_results` | integer | count | same | Distinct contingencies that have at least one `psse_contingency_result` row |
| `job_version` | text | none (identifier) | not readable | Short git commit of the job (`unknown` when unreadable; same rule as `pipeline_version`) |
| `psse_version` | text | none (label) | not reached | PSS/E version string reported by the API |
| `schema_version` | integer | none (version) | never | default 1 |
| `created_at` | timestamptz | UTC instant | never | DB default `date_trunc('second', now())`; the time the record became visible |
| unique `(run_id, outcome)` | | | | Target of the composite FKs |

`ratings_used.<CITY>` keys (documented in the column comment and the spec, checked by `psse_run_record_test.py`): `source` (`city_rating` | `static_fallback`), `fallback_reason` (null | `missing` | `stale` | `provisional` | `read_failed` | `invalid`), `rating_amps_per_conductor` (A), `subconductors_per_phase`, `rating_amps_circuit` (A, per circuit = per conductor x subconductors), `line_voltage_kv` (kV the study used: the branch's bus base kV, filled by Phase 2; null before the case loads), `rating_mva` (MVA, filled by Phase 2), `static_rating_amps_per_conductor`, and the link to the row used: `city_rating_valid_time`, `city_rating_computed_at`, `city_rating_run_id`, `city_rating_status`, `config_fingerprint`, `is_provisional`, `age_minutes` (all null when no row was read or the row was invalid).

### 2. `public.psse_dispatched_capacity` (STU-04) — PK `(run_id, city)`, four rows per non-failed run
| Column | Type | Unit | Meaning |
|---|---|---|---|
| `run_id` | text | none | FK part |
| `run_outcome` | text | none | CHECK in `('ok','fallback')`; with `run_id` forms the composite FK to `psse_run(run_id, outcome)` so a result row cannot point at a failed run |
| `city` | text | none | the four-city CHECK |
| `rating_source` | text | none | `city_rating` or `static_fallback` (copy of `ratings_used`, typed for querying) |
| `fallback_reason` | text | none | null when `rating_source = 'city_rating'` |
| `city_rating_valid_time` | timestamptz | UTC instant | Soft link to `public.city_rating (city, valid_time)`; null on static. NOT a foreign key: the PSS/E role has no privilege on `city_rating`, the row may be rewritten by an OD-7 retry, and a static run has no row. `city_rating_computed_at` identifies the exact version used |
| `city_rating_computed_at` | timestamptz | UTC instant | as above |
| `applied_amps_per_conductor` | double precision | A, per conductor | Comparable to `city_rating.rating_amps` |
| `applied_amps_circuit` | double precision | A, per circuit | What PSS/E effectively received (x subconductors) |
| `applied_mva` | double precision | MVA, per circuit | Value written to the branch rating |
| `voltage_limit_mva` | double precision | MVA | Voltage-stability limit in the same unit |
| `dispatched_mva` | double precision | MVA | `least(applied_mva, voltage_limit_mva)` |
| `dispatched_amps_circuit` | double precision | A, per circuit | `dispatched_mva x 1000 / (sqrt(3) x line_voltage_kv)` |
| `dispatched_amps_per_conductor` | double precision | A, per conductor | `dispatched_amps_circuit / subconductors_per_phase` |
| `dispatched_mw` | double precision | MW | `dispatched_mva x power_factor` (same convention as `rating_mw`; the factor is stored) |
| `limiting_factor` | text | none | CHECK in `('dlr_rating','voltage_stability')`; tie goes to `dlr_rating` |
| `line_voltage_kv`, `power_factor`, `subconductors_per_phase` | double / double / integer | kV, dimensionless, count | Self-describing, like `city_rating` rows |
| `details` | jsonb | none | Optional extras Phase 2 may need without a schema change |
CHECKs: all numeric > 0 and finite; `dispatched_mva <= applied_mva` and `<= voltage_limit_mva` (tolerance 1e-9); `limiting_factor` consistent with which value equals `dispatched_mva`.

### 3. `public.psse_voltage_margin` (STU-03) — PK `(run_id, city)`
`run_id`, `run_outcome` (composite FK as above), `city`, `method` text (label, for example `pv_curve`), `base_transfer_mw` (MW), `limit_transfer_mw` (MW), `margin_mw` (MW, CHECK >= 0 unless the base case already violates), `margin_pct` (percent of base), `voltage_limit_mva` (MVA; the value `psse_dispatched_capacity` copies), `critical_bus` text (none, identifier), `min_voltage_pu` (per unit, nullable), `details` jsonb. Exact method is Phase 2's; only `margin_mw`, `margin_pct`, `voltage_limit_mva` are required.

### 4. `public.psse_contingency_result` (STU-02) — PK `(run_id, contingency_id, violation_kind, element_id)`
| Column | Type | Unit | Meaning |
|---|---|---|---|
| `run_id`, `run_outcome` | text | none | composite FK to `psse_run(run_id, outcome)` |
| `contingency_id` | text | none (identifier) | Label of the outage, for example the tripped branch `<from>-<to>-<ckt>` |
| `violation_kind` | text | none (category) | CHECK in `('thermal_overload','voltage_low','voltage_high','non_convergence')` |
| `element_type` | text | none | `branch`, `bus` or `contingency` (for `non_convergence`) |
| `element_id` | text | none (identifier) | Branch `<from>-<to>-<ckt>` or bus number; the contingency id for `non_convergence` |
| `city` | text | none | The city whose mapped branch this is; null for other elements |
| `limit_value` | double precision | MVA for thermal, per unit for voltage | The limit used (for a DLR-mapped branch, the applied rating in MVA) |
| `observed_value` | double precision | same | Post-contingency value |
| `exceeded_by` | double precision | same | CHECK > 0: `observed - limit` (thermal, high voltage), `limit - observed` (low voltage); null for `non_convergence` |
| `unit` | text | none | `MVA` or `pu`; CHECK ties it to `violation_kind` |
| `details` | jsonb | none | Optional extras |
Only violations are written (no row for a clean contingency): row volume matters on a hosted free-tier database, and completeness is checked through `psse_run.n_contingencies` and `n_contingencies_with_results` instead. Retention is not defined in this milestone (open question 6).

### Grants and role (copy into the Phase 6 migration; verified shape from Phase 4)
Phase 4's pattern [VERIFIED: 20261019000000_create_city_rating.sql:99-113]: `revoke all on public.city_rating, public.pipeline_run from anon, authenticated;`, role created in a guard (`create role dlr_writer login;`), `grant select, insert, update on ... to dlr_writer;`, policy `dlr_writer_all ... for all to dlr_writer using (true) with check (true)`. The PSS/E equivalent, narrower:
```sql
revoke all on public.psse_run, public.psse_contingency_result, public.psse_dispatched_capacity, public.psse_voltage_margin from public, anon, authenticated;
do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'dlr_psse_writer') then create role dlr_psse_writer login; end if;
end $$;                                           -- no credential here; the owner sets it out of band
grant usage on schema public to dlr_psse_writer;
grant select, insert on public.psse_run, public.psse_contingency_result, public.psse_dispatched_capacity, public.psse_voltage_margin to dlr_psse_writer;
alter table public.<each> enable row level security;
drop policy if exists dlr_psse_writer_insert on public.<each>; create policy dlr_psse_writer_insert on public.<each> for insert to dlr_psse_writer with check (true);
drop policy if exists dlr_psse_writer_select on public.<each>; create policy dlr_psse_writer_select on public.<each> for select to dlr_psse_writer using (true);
```
No UPDATE, DELETE or TRUNCATE (records are immutable; INSERT-only also means a retry cannot overwrite), no grant on `city_rating`, `pipeline_run`, `latest_rating` (reads go through REST), no sequences (all keys are natural), no grant to `anon` or `authenticated`. SELECT is granted because `insert ... returning` and the read-back check need it. Consumer read (anon) is deliberately absent: the results carry real grid element identifiers from Power Systems' case, and the repo and `city_rating` history are public by owner decision OD-6, so publishing PSS/E results is the owner's separate call (Assumption A5). Any function added (for example a verification helper) needs `revoke all on function ... from public, anon, authenticated`, because Supabase auto-grants EXECUTE; Phase 6 relies on that rule for `assert_fresh`.

## Unit Handling (verified against the repo)

Verified claims, each against the file read this session:
- `rating_amps` and `static_rating_amps` are per conductor [VERIFIED: `docs/data-science/schema/city_rating_v1.md:47,49`: "A, per conductor"].
- `rating_mw` is `amps_to_mw(rating, voltage, power_factor)` on the per-conductor value, with no subconductor factor [VERIFIED: `backend/supabase_store.py:572` `"rating_mw": float(amps_to_mw(rating, voltage, power_factor))`; `backend/ercot_dlr_merger.py:15-20` `return (np.sqrt(3) * voltage_kv * amps * pf) / 1000.0`].
- `STATIC_RATINGS` are per conductor: `"AUSTIN": 1825.0` ... `"EL_PASO": 1320.0`; `SUBCONDUCTORS_PER_PHASE`: AUSTIN 2, CORPUS_CHRISTI 2, MIDLAND 2, EL_PASO 1; `LINE_VOLTAGE_KV: float = 345.0`; `POWER_FACTOR: float = 0.95` [VERIFIED: `backend/config.py:41-51, 76-81, 247-248`]. Config says the subconductor counts are the Power Systems team's provisional assumption under equal current sharing [VERIFIED: config.py:61-73, 83-88].
- No disagreement found between the brief, the schema doc and the code on these points. One thing the brief did not say: the view `latest_rating` has no `subconductors_per_phase` column, so the count must come from `config.SUBCONDUCTORS_PER_PHASE` (or Power Systems' mapping config in Phase 2), and the job must record the count it used.

Conversion the spec must state (the study step applies it in Phase 2, IN-03):
`rating_amps_circuit = rating_amps_per_conductor x subconductors_per_phase`; `rating_mva = sqrt(3) x line_voltage_kv x rating_amps_circuit / 1000` with `line_voltage_kv` the base kV of the branch's from-bus in the case, no power factor.

| City | per-conductor A | subcond. | circuit A | `rating_mw` as stored (static, 345 kV, pf 0.95) | per-circuit MVA the job must apply | Ratio |
|---|---|---|---|---|---|---|
| AUSTIN | 1825 | 2 | 3650 | 1036.0 | 2181.1 | 2.105 |
| CORPUS_CHRISTI | 1500 | 2 | 3000 | 851.5 | 1792.7 | 2.105 |
| MIDLAND | 1875 | 2 | 3750 | 1064.4 | 2240.8 | 2.105 |
| EL_PASO | 1320 | 1 | 1320 | 749.3 | 788.8 | 1.053 |
(Computed this session with Python from the repo constants; the doc test should recompute them rather than hard-code them.)

PSS/E side: branch ratings are apparent-power values in MVA, and PSS/E has a program setting for "current expressed as MVA" ratings, where the rating is the nominal current limit times base kV times sqrt(3) `[CITED: psspy.org/psse-help-forum (practitioner answers; no official Siemens manual found)]`. Both readings give the same number to write, `sqrt(3) x kV_base x I_circuit`, with no power factor. Which Program Settings option Power Systems' case uses changes how loading percent is reported, not the value to write; confirm it with them (open question 3). `RATEA = 0` means "no limit" in PSS/E reports, so the job must never write 0 or a missing rating into a branch; an unreadable or non-positive rating is `invalid` and goes to static (this guard belongs to Phase 2's write step but the spec should say it).

`dispatched_mw` and `rating_mw` are not comparable: one is per circuit, one per conductor. The doc must say so next to the table, and `psse_dispatched_capacity` carries `applied_amps_per_conductor` precisely so a reader can compare it with `city_rating.rating_amps`.

## Rating Selection (IN-01) — how to read and what to record

- **Endpoint:** `GET {SUPABASE_URL}/rest/v1/latest_rating?select=city,valid_time,computed_at,rating_amps,static_rating_amps,status,fallback,run_id,config_fingerprint,age_minutes,is_stale,is_provisional&order=city` with header `apikey: <publishable key>`. Select only needed columns so additive changes never break the job, and never select `rating_mw`. All of these are in the Phase 6 34-column list (27 base columns include `computed_at`, `run_id`, `static_rating_amps`, `status`, `fallback`; D-01 adds `config_fingerprint`; D-02/D-03 add the three computed columns) [VERIFIED: 06-01-PLAN.md `<interfaces>` list]. The contract is planned, not live (nothing is applied; migration not on disk).
- **Credential:** the publishable key from env (`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, Phase 6 D-10); never the secret key. Phase 6's client refuses a secret/service_role key before any request [VERIFIED: 06-04-PLAN.md truths]; the job's reader should do the same.
- **Server-side definitions** [VERIFIED: 06-CONTEXT.md D-02, D-03]: `is_stale` is true when `valid_time` is strictly more than 90 minutes old (exactly 90 is fresh); `is_provisional` is true when the word "provisional" appears in `rating_basis` or `config_version`. Today every live and backfill row is provisional (`config.RATING_CONFIG_VERSION = "v1-provisional-2026-10-13"` per D-03), so all four cities select static until Phase 7's go.
- **Newest row semantics:** the view returns the newest row per city by `valid_time`, fallback rows included (D-04). A `status = 'fallback'` row that is fresh and non-provisional is still `city_rating`-sourced (its `rating_amps` equals the static value); record `city_rating_status = 'fallback'` in `ratings_used` so it is distinguishable.
- **Clock use:** the job takes `now` once at start and uses it for all four cities and for `started_at`. The client age check (`(now - valid_time) > 90 min`) is OR-ed with the server flag, so clock skew can only push decisions toward static.
- **What to record as source:** `source` in (`city_rating`, `static_fallback`) plus `fallback_reason` in (`missing`, `stale`, `provisional`, `read_failed`, `invalid`) per city in `ratings_used`, mirrored in `psse_dispatched_capacity`. `read_failed` extends IN-01's three listed reasons: a read that cannot be completed is "missing" operationally, and static is the safe answer by the core value, so the run continues with outcome `fallback` rather than failing. Flagged for confirmation (Assumption A2).
- **Static source:** `config.STATIC_RATINGS[city]` (per conductor) with `config.SUBCONDUCTORS_PER_PHASE[city]`; do not use the stale row's `static_rating_amps`, since a missing row has none and two sources could differ after a config bump.
- **Scheduling interaction (for Phase 3):** the hourly live pipeline is dispatched at minute 05 [VERIFIED: 06-CONTEXT.md "at minute 05"], so the current hour's row exists only after the run completes. A row from the previous slot is exactly 90 minutes old at HH:30:00 and 91 (stale) one minute later. If the PSS/E job starts after about HH:30 and the current slot's row is missing, every city silently becomes `stale`. The Phase 3 schedule should start the job well before HH:30 (or the guide should state the consequence).

## Run Record and Failed-Run Behaviour (WB-01, WB-02)

Decision: **one transaction, run record last in code but first in SQL.** Concretely:
1. Study succeeded: one transaction inserts `psse_run` (outcome `ok` or `fallback`) and all child rows. Commit makes the whole set visible at once (Postgres MVCC: a reader sees all or none).
2. Study failed (mapping miss IN-02, non-convergence STU-01, any exception): write `psse_run` alone with outcome `failed`, `failed_stage`, redacted `error` and `ratings_used` (the selection ran before the study, so it is known). Zero child rows exist, and the composite FK makes it impossible to add any later.
3. The result write itself fails: the transaction rolls back (no partial rows), then a new transaction records `failed` with stage `write`. If that also fails (database unreachable), no record exists; the job exits non-zero and logs locally. That absence is exactly the "gap" SCH-02 detects, and it is the one case a run record cannot cover (a laptop that sleeps mid-run behaves the same). A `running` heartbeat row is deliberately not added: it would introduce a fourth outcome the requirement does not list and needs UPDATE.
4. Idempotency: the key is `run_id`, fixed at start. `insert ... on conflict (run_id) do nothing returning run_id` returning no row means a prior attempt already committed; stop and report success. A rerun in the same hour with a new `run_id` creates a second record in the same `slot_time`; readers take the newest `psse_run` per `slot_time` with `outcome in ('ok','fallback')`. This is append-only on purpose: the job has no UPDATE/DELETE, so a rerun cannot overwrite a good run with a worse one. (The `city_rating` rule, a retry overwriting the same slot, is a deliberate contrast and is documented in the spec.)
5. Redaction: every error string goes through the ported `redact` and is cut to 1000 characters after redaction. Because the table is private (no consumer role), error text is allowed, unlike `city_rating`, whose doc forbids error text because it is public [VERIFIED: city_rating_v1.md "no column holds anything sensitive: no file path, no credential, no error text"].

Verification query the spec ships (and Phase 3 uses for read-back, WB-02): every `psse_run` with `outcome in ('ok','fallback')` has exactly 4 rows in `psse_dispatched_capacity`, exactly 4 in `psse_voltage_margin`, and `count(distinct contingency_id)` in `psse_contingency_result` equals `n_contingencies_with_results`; every `failed` run has zero rows in all three. Expected result: zero offending runs.

## Handoff to Phase 6

**What exists in Phase 6 today** (read this session): 13 plans (`06-01` to `06-13`), `06-CONTEXT.md` decisions D-01 to D-15, nothing built. The migration it plans is one file `supabase/migrations/<UTC ts>_expose_latest_rating.sql` (06-01) plus a soak-log migration (06-05, `ops.freshness_log`); 06-09 is the owner's `[BLOCKING]` push of "both" migrations and pins both by sha256. Its permission design: `revoke all on all tables in schema public from anon, authenticated`, then `grant select on public.city_rating, public.latest_rating to anon, authenticated`, `alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated`, policy `city_rating_public_read`; `dlr_writer` untouched; one anon-executable function, `assert_fresh` [VERIFIED: 06-01-PLAN.md truths and action step 4-5].

**What the spec must contain** (so Phase 6 can plan without re-asking): the four table definitions above as a reference DDL file that already passed Phase 1's local-Postgres tests; the role and grant block; the policy block; the verification SQL; the naming of the credential env var (`SUPABASE_PSSE_DB_URL`, session pooler URL for role `dlr_psse_writer`); the statement that anon/authenticated get nothing; and the order rule below.

**Where it lives:** `docs/data-science/schema/psse_results_v1.md` (human spec, same folder and style as `city_rating_v1.md`) and `docs/data-science/schema/psse_results_v1.sql` (reference DDL, header says "NOT a migration"). Not under `supabase/migrations/` (no standalone migration here), and not under `docs/integration/` (Phase 6 creates that for the read contract). Add a short "Phase 6 intake" section at the top of the spec listing exactly the five things Phase 6 must do.

**Conflicts with Phase 6's existing plans** (each needs a deliberate resolution; this workstream cannot edit Phase 6 files):
1. **Scope.** 06-CONTEXT "Not in scope: ... dashboard or PSS/E-side code" and production-pipeline REQUIREMENTS "PSS/E results back into the database (F7) ... follow-on table" contradict adding these tables. Needs an owner-level note (a new decision, for example D-16) and a requirement home: DBX-01 lives in this workstream, so the new Phase 6 plan cites it cross-workstream.
2. **06-09.** Truths say the dry run "listed exactly the two Phase 6 files" and the pin test covers "both applied Phase 6 migrations". A third file breaks both statements. Two clean options: (a) amend 06-09 to three files and pin all three (preferred if the file is ready before wave 4, since it avoids a second owner push); (b) ship the PSS/E migration as its own later owner step (`06-14`, own dry-run and sha pin) so 06-09 stays untouched. Phase 6's planner chooses.
3. **`verify_exposure.sql` and the harness.** The check that anon/authenticated hold SELECT on exactly two objects will fail if any PSS/E table gets an anon/authenticated grant, which is the regression net we want; no change needed if the spec follows the grants above. The local harness runs `alter default privileges in schema public grant all ... to anon, authenticated, service_role` before the migrations [VERIFIED: 06-01-PLAN.md local_pg.py `SUPABASE_ROLES_SQL` description], so the PSS/E migration must either sort after the expose migration (whose `alter default privileges ... for role postgres ... revoke` cancels that) or carry its own explicit `revoke ... from public, anon, authenticated` (the spec includes it, so either order is safe).
4. **Ordering and name.** The file must sort after `20261023000000_...` and, preferably, after the expose and soak migrations: `<UTC ts>_psse_results.sql`.
5. **New ops SQL.** A `supabase/ops/verify_psse_results.sql` (read-only `check_name, ok, detail`, same shape as `verify_exposure.sql`) so the owner confirms live that the PSS/E tables exist, anon has nothing, the role exists and has no `city_rating` privilege.
6. **`dlr_writer` untouched.** No conflict: the new role is separate, and Phase 6's revoke sweep only names anon and authenticated.

Timing: Phase 6 executes offline waves 1-3 first and applies nothing before 05-08's sign-off (D-06), so there is room to hand over the spec first, but the spec should land before Phase 6's planner is next asked to touch the plans.

## Code Location and Environment Constraints (Point 6)

- **Directory:** `backend/psse_job/` (package) with flat tests `backend/tests/psse_*_test.py`. Entry point `python -m psse_job` run with `PYTHONPATH=backend` (Phase 3 decides the exact launcher). Phase 2 adds `psse_job/study.py` and a `psspy` shim; Phase 1 must not import `psspy`.
- **Fake `psspy` (Phase 2):** a test double module is injected by the caller (`study` takes a `psspy`-like object), so Phase 1's functions take plain dicts and a `conn`, which keeps them testable on the Mac with no PSS/E.
- **Python syntax target 3.7+** for everything the laptop imports (no walrus, no `list[str]`/`X | Y` annotations, no `str.removeprefix`, no dataclass `slots`/`kw_only`); gate with `ast.parse(source, feature_version=(3, 7))` as a syntax-only test (best-effort per CPython docs, see Assumption A6).
- **Env vars:** reads `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (Phase 6); writes `SUPABASE_PSSE_DB_URL`. The job must never print any of them, and `redact` must know the new variable name. Phase 6's secret-scan test (06-02) scans for the project host and key; the new env name needs no extra rule beyond not committing values.
- **Where the DB role is exercised:** local Postgres only in Phase 1; the live role and pooler login are Phase 3 (pooler login as a custom role already works for `dlr_writer`: runbook line "the session pooler URL (port 5432) for the `dlr_writer` role" [VERIFIED: docs/data-science/decisions/dlr_live_runbook.md:93]). Whether the university/laptop network needs the IPv4 session pooler is the same reason runners used it; direct connections need IPv6 or an add-on `[CITED: supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits]`.

## Common Pitfalls

### Pitfall 1: Reading `rating_mw` for PSS/E
**What goes wrong:** the study applies 1036 MVA where 2181 is correct (AUSTIN), or treats per-conductor amps as per-circuit.
**Why:** `rating_mw` is per conductor with pf 0.95. **Avoid:** select `rating_amps`, multiply by subconductors, `sqrt(3) x kV x I`, no pf. **Warning sign:** applied MVA / stored `rating_mw` not near 2.105.

### Pitfall 2: Job starts after HH:30 and silently goes all-static
See "Scheduling interaction". **Avoid:** schedule early; record `age_minutes` per city so the cause is visible.

### Pitfall 3: Partial result sets from incremental writes
**Avoid:** build in memory; one transaction; composite FK; verification query. **Warning sign:** a `psse_run` with fewer than 4 dispatched rows.

### Pitfall 4: psycopg 3.3.6 on an old PSS/E interpreter
**What goes wrong:** `pip install psycopg==3.3.6` refuses on Python < 3.10; the write path cannot run. **Avoid:** write only to the 3.1-3.3 common API; Phase 3 pins per interpreter; if no psycopg works, fall back to the JWT/REST route (open question 1). **Warning sign:** the interpreter answer to Phase 6's PSS/E question (06-11 Task 3).

### Pitfall 5: Grants on `authenticated` or `anon`
Breaks Phase 6's `verify_exposure.sql` and exposes grid element names. **Avoid:** only `dlr_psse_writer`.

### Pitfall 6: EXECUTE on functions defaults to API roles
Any helper function is callable by anon unless `revoke all on function ... from public, anon, authenticated` is explicit.

### Pitfall 7: Hour CHECK in the session time zone
Use the UTC form (Phase 4 IN-06). Test with `set time zone '+05:30'` as `supabase_live_test.py` does for `city_rating`.

### Pitfall 8: Timestamps from PostgREST on Python < 3.11
`fromisoformat` rejects `Z` and odd fractions; use the tested `parse_ts`.

### Pitfall 9: `jsonb` and NaN
`json.dumps(..., allow_nan=False)` for every jsonb value (as `upsert_run` does) and `finite()` semantics for doubles; Postgres CHECKs are the backstop.

### Pitfall 10: Row volume of contingency results
A real case with many contingencies can produce thousands of rows per hour on a hosted database with limited storage `[ASSUMED]` (free-tier size). **Avoid:** violations only, optional `max_result_rows` job cap that marks the run `failed` (stage `contingency`) instead of writing a truncated set, and ask Power Systems for the case size.

## Code Examples

### Reading `latest_rating` with stdlib (Python 3.7+)
```python
# Source: adapted from 06-RESEARCH.md "Python stdlib (PSS/E)" example (Phase 6, planned; verified there against an in-process fake)
import json, os, urllib.error, urllib.parse, urllib.request

COLUMNS = ("city,valid_time,computed_at,rating_amps,static_rating_amps,status,fallback,run_id,"
           "config_fingerprint,age_minutes,is_stale,is_provisional")

def fetch_latest_rating():
    base = os.environ["SUPABASE_URL"].rstrip("/")
    key = os.environ["SUPABASE_PUBLISHABLE_KEY"]
    url = base + "/rest/v1/latest_rating?" + urllib.parse.urlencode({"select": COLUMNS, "order": "city"}, safe=",.()*:")
    req = urllib.request.Request(url, headers={"apikey": key, "Accept": "application/json", "User-Agent": "dlr-psse-client/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:        # raises on HTTP errors: caller maps to read_failed
        rows = json.loads(resp.read().decode("utf-8"))
    return {r["city"]: r for r in rows}                           # missing city => reason "missing"
```

### Reference DDL excerpt (run record), conventions as Phase 4
```sql
create table if not exists public.psse_run (
    run_id text not null constraint psse_run_pk primary key,
    slot_time timestamptz not null constraint psse_run_slot_time_hour_ck check ((slot_time at time zone 'UTC') = date_trunc('hour', slot_time at time zone 'UTC')),
    started_at timestamptz not null,
    finished_at timestamptz not null,
    outcome text not null constraint psse_run_outcome_ck check (outcome in ('ok', 'fallback', 'failed')),
    failed_stage text,
    error text,
    case_id text not null,
    case_sha256 text constraint psse_run_case_sha256_ck check (case_sha256 ~ '^[0-9a-f]{64}$'),
    ratings_used jsonb not null constraint psse_run_ratings_used_ck check (jsonb_typeof(ratings_used) = 'object' and ratings_used ?& array['AUSTIN','CORPUS_CHRISTI','MIDLAND','EL_PASO']),
    schema_version integer not null default 1,
    created_at timestamptz not null default date_trunc('second', now()),
    constraint psse_run_finished_ck check (finished_at >= started_at),
    constraint psse_run_failed_error_ck check ((outcome = 'failed') = (error is not null)),
    constraint psse_run_run_outcome_uq unique (run_id, outcome)
    -- plus n_contingencies, n_contingencies_with_results, mapping_sha256, rate_set, job_version, psse_version (see table above)
);
create index if not exists psse_run_slot_time_idx on public.psse_run (slot_time desc);

create table if not exists public.psse_dispatched_capacity (
    run_id text not null,
    run_outcome text not null constraint psse_dispatched_capacity_run_outcome_ck check (run_outcome in ('ok', 'fallback')),
    city text not null constraint psse_dispatched_capacity_city_ck check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO')),
    -- ... columns from the spec table ...
    constraint psse_dispatched_capacity_pk primary key (run_id, city),
    constraint psse_dispatched_capacity_run_fk foreign key (run_id, run_outcome) references public.psse_run (run_id, outcome)
);
```
(The `?&` operator and `jsonb_typeof` are standard Postgres jsonb features; Phase 1's local tests are what prove the DDL applies, which is why the reference DDL is tested before handover.)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Supabase auto-grants new public tables to API roles | Auto-grant stops; explicit grants required | 2026-10-30 (stated in the Phase 4 migration header) | The migration already states grants explicitly; do the same for the new tables |
| Legacy shared JWT secret | JWT Signing Keys (asymmetric), legacy secret revocable | 2025 `[CITED: supabase.com/docs/guides/auth/signing-keys]` | Another reason to avoid self-minted role JWTs for the write path |
| `psycopg` 3.1/3.2 on Python 3.7/3.8 | 3.3.x requires >= 3.10 | 3.3.6 uploaded 2026-09-18 | Laptop needs a per-interpreter pin |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | PSS/E's bundled Python is somewhere in 3.7 to 3.9 (35) and unconfirmed for 36; Power Systems' answer to the interpreter question (06-11) is still pending | Stack, Pitfall 4 | If < 3.10, psycopg 3.3.6 cannot be used there and the pin differs; if no psycopg works, the write path switches to REST+JWT |
| A2 | Outcome semantics: `fallback` = completed with at least one city on static; `read_failed` runs continue as `fallback`; a failed ratings read is not a failed run | Run record | If the owner wants a failed read to be `failed`, selection changes one branch; confirm before Phase 2 |
| A3 | `psse_run` written once at the end (no `running` row); a crash leaves no record and appears as a gap | Run record | If owners want crash visibility, a fourth outcome and UPDATE grant would be needed |
| A4 | A new Phase 6 plan (06-14) or an amended 06-09 is acceptable; the scope exclusion in production-pipeline REQUIREMENTS can be overridden by the owner | Handoff | If not, the tables cannot ship in Phase 6 and DBX-01 needs a different vehicle |
| A5 | PSS/E result tables must NOT be anon-readable (grid element identifiers, public repo) | Grants | If the owner wants them public like `city_rating`, add an anon SELECT grant and policy later (additive) |
| A6 | `ast.parse(feature_version=(3,7))` is an adequate Python 3.7 syntax gate | Constraints | It is documented best-effort; a real 3.7 run is not available locally |
| A7 | Free-tier storage limits make unbounded contingency rows risky | Pitfall 10 | If plan limits are higher, the cap is just cautious |
| A8 | `dlr_psse_writer` can log in through the shared pooler as `dlr_psse_writer.<project-ref>` like `dlr_writer` | Constraints | Supabase docs fetched did not describe custom roles on the shared pooler; the existing `dlr_writer` smoke evidence suggests it works, Phase 3 must prove it |
| A9 | PSS/E "current expressed as MVA" rating = I x kV_base x sqrt(3) | Units | From forum answers only; the value to write is the same either way, but confirm which setting Power Systems' case uses |
| A10 | The `latest_rating` columns listed will ship as planned in 06-01 (not yet built) | Selection | Column drift would break the select list; a contract test against `LATEST_COLUMNS` once Phase 6 lands |

## Open Questions

1. **Which Python/PSS/E version will the laptop use, and does it run any psycopg 3.x?**
   - Known: psycopg `requires_python` is >=3.7 (3.1.20), >=3.8 (3.2.13), >=3.10 (3.3.6); Phase 6 asks Power Systems for `sys.version` (06-11).
   - Unclear: the answer. Recommendation: write to the common API now, pin in Phase 3; keep the DDL role-agnostic so a REST+JWT route stays possible.
2. **Outcome semantics confirmation (A2, A3).** Recommendation: ship as specified, confirm with the owner when the spec is handed over.
3. **Which PSS/E rate set (RATEA/RATEB/RATEC) gets the DLR value, and which Program Settings rating-units option does the case use?** Needed by Phase 2; `rate_set` is nullable so Phase 1 does not block.
4. **Case size and expected N-1 volume** (row-volume cap, retention). Recommendation: ask Power Systems; add retention only if volume warrants.
5. **Should results ever be public?** Recommendation: not now (A5); revisit with F7.
6. **Which Phase 6 vehicle (06-09 amended vs 06-14 later push)?** The Phase 6 planner decides; both are compatible with the spec.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3 | everything | yes (this research machine) | 3.12.7 and 3.14.7 (`python`, `py`) | — |
| pytest, pandas, psycopg | tests | not installed on this Windows research machine | — | The teammate's Mac `.venv` (Phase 4-6 plans use `/Users/aphan/Senior_Design/.venv/bin/python`); install from `requirements.txt` |
| Postgres server binaries (`initdb`, `pg_ctl`) | local atomicity/privilege tests | not found on this machine | — | Tests skip without `DLR_TEST_PG_AUTOSTART=1` (house convention); the Mac executor must have Postgres binaries on PATH or the DDL/atomicity proofs are not run. Plans must treat a skip as a failed gate (`fails_when` includes "skipped", as in 06-01) |
| Node | not needed | yes | — | — |
| `psspy` / PSS/E | Phase 2 mock, Phase 3 real | not needed in Phase 1 | — | — |
| Supabase project / network | none in Phase 1 | not touched | — | All Phase 1 verification is offline |

**Missing dependencies with no fallback:** none for planning. Execution on the Mac needs Postgres binaries for the PG-backed proofs (cannot be confirmed from here).
**Missing with fallback:** psycopg/pytest on this machine, irrelevant to the executor.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (repo pin), plain asserts, no classes [VERIFIED: requirements.txt, TESTING.md] |
| Config file | `pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`) |
| Quick run command | `python -m pytest -q -p no:cacheprovider backend/tests/psse_contract_test.py backend/tests/psse_ratings_test.py backend/tests/psse_run_record_test.py backend/tests/psse_schema_doc_test.py` |
| Full suite command | `DLR_TEST_PG_AUTOSTART=1 python -m pytest -q -p no:cacheprovider -rs` (Mac venv interpreter) |

### Phase Requirements to Test Map
| Req / criterion | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| DBX-01 / SC1 | Spec doc lists the four tables, every column with unit, keys and links; doc columns equal the reference DDL; the DDL applies cleanly to a fresh local Postgres after the Phase 4 migrations | doc-drift + local PG | `pytest backend/tests/psse_schema_doc_test.py` and `... psse_writer_test.py -k ddl` | Wave 0 |
| DBX-01 / SC1 | Grants: `dlr_psse_writer` can INSERT/SELECT the four tables, cannot touch `city_rating`/`pipeline_run`/`latest_rating`; anon/authenticated have no grant; no UPDATE/DELETE for the role | local PG | `pytest backend/tests/psse_writer_test.py -k privileges` | Wave 0 |
| IN-01 / SC2 | Matrix: missing, stale at exactly 90 vs 91 min, server `is_stale`, provisional, invalid (nonfinite, missing flags, wrong types), read_failed, fresh non-provisional (uses row), fresh fallback-status row, today's real labels: all four cities static with reason `provisional` | unit | `pytest backend/tests/psse_ratings_test.py` | Wave 0 |
| IN-01 / SC2 | The unit trap: chosen amps per conductor, `rating_mw` never read, circuit MVA numbers equal the doc table | unit | `pytest backend/tests/psse_ratings_test.py -k units` | Wave 0 |
| WB-01 / SC3 | Run record has every required field for `ok`, `fallback` and `failed`; `ratings_used` has the four cities; failed study writes a record | unit + local PG | `pytest backend/tests/psse_run_record_test.py backend/tests/psse_writer_test.py -k record` | Wave 0 |
| WB-02 / SC4 | Inject a failure on the Nth child insert: all four tables have zero rows for that `run_id`, then a `failed` record exists; success path has 1 + 4 + 4 + N rows; child insert referencing a failed run is rejected (23503); same `run_id` written twice leaves one set | local PG | `pytest backend/tests/psse_writer_test.py -k "atomic or idempotent or failed"` | Wave 0 |
| WB-02 | Verification SQL returns zero offending runs on good data and flags a hand-made partial run | local PG | `pytest backend/tests/psse_writer_test.py -k verification` | Wave 0 |
| Hygiene | No secret in any error or log; `redact` parity with `supabase_store.redact` on shared cases; 3.7 syntax gate | unit | `pytest backend/tests/psse_run_record_test.py -k redact` and `psse_contract_test.py -k syntax` | Wave 0 |

### Sampling Rate
- **Per task commit:** the quick run command (no database).
- **Per wave merge:** the full command with `DLR_TEST_PG_AUTOSTART=1`; any skip is a failure.
- **Phase gate:** full suite green, plus a reviewer confirms the spec file and DDL are what is handed to Phase 6 (a literal copy test: the SQL in the future migration must equal the reference DDL; Phase 6 owns that test).

### Wave 0 Gaps
- [ ] `backend/tests/psse_contract_test.py`, `psse_ratings_test.py`, `psse_run_record_test.py`, `psse_writer_test.py`, `psse_schema_doc_test.py`
- [ ] A local-Postgres fixture: reuse Phase 6's `backend/tests/local_pg.py` if it exists by then, else copy the `supabase_live_test.py:82-124` pattern into a helper (names must not collide with Phase 6's file)
- [ ] `docs/data-science/schema/psse_results_v1.md` and `.sql`, `backend/psse_job/` package skeleton
- [ ] Postgres binaries on the Mac executor's PATH (cannot confirm from here)

## Security Domain

Security enforcement is not disabled in config (`.planning/config.json` has no `security_enforcement` key), so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (service credential) | Dedicated DB role, password set out of band, never in migration/code/log |
| V3 Session Management | no | Not interactive |
| V4 Access Control | yes | Least-privilege grants (INSERT+SELECT on four tables), RLS on, explicit revokes from API roles, composite FK, immutability by omitting UPDATE/DELETE |
| V5 Input Validation | yes | Parameter-bound SQL only, CHECK constraints (city, enums, finite numbers, hex hashes, jsonb shape), `allow_nan=False` |
| V6 Cryptography | partial | sha256 of case file via `hashlib`; no hand-rolled crypto; TLS to Supabase |
| V7 Error handling / logging | yes | `redact()` on every error string; no URL/host/project ref printed |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Job credential can alter `city_rating` | Tampering / Elevation | No privilege on `city_rating`; test asserts 42501 for UPDATE/INSERT/DELETE as the role (Phase 3 repeats live, DBX-02) |
| Anon reads grid element names | Information disclosure | No anon/authenticated grant; Phase 6 `verify_exposure.sql` aclexplode check plus `verify_psse_results.sql` |
| Secret leakage via error text or logs (public repo) | Information disclosure | Redaction, truncation after redaction, secret-scan extension from 06-02, no committed env values |
| Partial result set trusted as complete | Tampering (integrity of meaning) | One transaction, composite FK to a non-failed run, verification query |
| Trusting a stale or provisional rating | Tampering (integrity of meaning) | Server flags OR client age, any malformed row to static, record reason |
| Self-minted JWT for a role (if REST write is ever used) | Spoofing / Elevation | Avoided in the recommended design; if used, long-lived token scoped to one role, rotation documented |
| Callable helper functions via API roles | Elevation | `revoke all on function ... from public, anon, authenticated` |

## Sources

### Primary (HIGH confidence, read this session)
- `docs/data-science/schema/city_rating_v1.md` (units, key semantics, run-log table, no-error-text rule)
- `supabase/migrations/20261019000000_create_city_rating.sql` and `20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql` (conventions, grants, role, UTC hour check)
- `backend/config.py`, `backend/supabase_store.py`, `backend/ercot_dlr_merger.py`, `requirements.txt`, `pytest.ini`, `backend/tests/supabase_live_test.py`, `supabase_schema_doc_test.py`, `supabase_migration_test.py`
- `.planning/workstreams/production-pipeline/{ROADMAP,STATE,REQUIREMENTS}.md`; Phase 6 `06-CONTEXT.md`, `06-01-PLAN.md`, `06-04-PLAN.md`, `06-09-PLAN.md`, `06-RESEARCH.md` (Python stdlib example), `06-PATTERNS.md`
- `docs/data-science/decisions/pss_e_handoff.md`, `docs/frontend/specs/F7-psse-integration.md`, `docs/data-science/decisions/dlr_live_runbook.md:93`
- pypi.org JSON for psycopg 3.3.6, 3.2.13, 3.1.20 (`requires_python`)
- `gsd-tools query package-legitimacy check --ecosystem pypi psycopg psycopg-binary` (SUS on unknown downloads)

### Secondary (MEDIUM confidence)
- supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits (IPv6 for direct connections; shared pooler IPv4-only; custom-role rule not described)
- supabase.com/docs/guides/auth/signing-keys and supabase.com/changelog/38771 (custom JWT and signing-key transition)
- docs.postgrest.org auth reference (role claim; `grant <role> to authenticator`)

### Tertiary (LOW confidence)
- psspy.org help-forum threads on "current expressed as MVA" and `RATEA = 0` (practitioner answers, no official Siemens manual found); PSS/E bundled Python version (blog and forum only)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for stdlib/psycopg constraints (registry data); MEDIUM for Phase 6 helper reuse (planned, unbuilt)
- Architecture and table spec: HIGH on conventions and Phase 6 conflicts; MEDIUM on column-level choices Phase 2 may refine (hence `details jsonb`, nullable study fields)
- Pitfalls: HIGH for units, grants, scheduling; MEDIUM for platform items (pooler custom role, row volume)

**Research date:** 2026-10-27
**Valid until:** about 7 days for Phase 6 plan state (it is being replanned and executed in parallel; re-read `06-CONTEXT.md` and the plan list before planning); 30 days for the rest.
