# PSS/E Result Tables: Schema v1 (psse_results_v1)

**Schema version:** v1
**Date:** 2026-10-28
**Status:** specification handed to production-pipeline Phase 6 (DBX-01); not applied to any database by this workstream
**Scope:** four private tables, `public.psse_run`, `public.psse_dispatched_capacity`, `public.psse_voltage_margin` and `public.psse_contingency_result`, and the role `dlr_psse_writer` that writes them. The reference DDL is `docs/data-science/schema/psse_results_v1.sql`; the read-only completeness checks are `docs/data-science/schema/psse_results_v1_checks.sql`. The DDL is proven on a throwaway local Postgres by `backend/tests/psse_schema_pg_test.py`; it is not a migration.

**Read this first.** The tables are private (D-03): no consumer role has any access. Every study in this milestone runs on the static ratings until Phase 7's go (REVAL-01), because every `city_rating` row is provisional. Nothing in this document says Phase 6 is live, and nothing here has been applied to a database.

## Phase 6 intake

Production-pipeline Phase 6 must do these five things to take the tables and the PSS/E write grant from this specification (D-01: this document and the reference DDL are the whole deliverable; this workstream adds no migration):

1. Add one migration `supabase/migrations/<UTC ts>_psse_results.sql` whose body is the region of `psse_results_v1.sql` from the `-- BEGIN psse_results_v1` line to the `-- END psse_results_v1` line, verbatim, sorting after Phase 6's expose and soak-log migrations.
2. The role `dlr_psse_writer` is created by that migration without a credential. The owner sets its password out of band, and the laptop stores the session-pooler connection string as `SUPABASE_PSSE_DB_URL` (never committed).
3. Add `supabase/ops/verify_psse_results.sql` (read-only, `check_name, ok, detail`): the four tables exist with row-level security on; `anon` and `authenticated` hold nothing on them; `dlr_psse_writer` holds exactly INSERT and SELECT on them and nothing on `city_rating`, `pipeline_run` or `latest_rating`; and the role is not superuser, createrole, createdb or bypassrls.
4. Pin the migration with the sha256 of the marked region given in the hand-off note.
5. Record the scope change in Phase 6: its CONTEXT lists PSS/E-side code as not in scope.

The plan-level impact on Phase 6 (06-09's "exactly the two Phase 6 files" and its tracked-migration count) and the sha256 are in [the hand-off note](../decisions/psse_results_phase6_handoff.md).

## Where the data lives

- A Supabase-hosted Postgres database, four tables in schema `public`. One PSS/E job run writes its rows once, at the end of the run, through the role `dlr_psse_writer`, from the licensed laptop that runs PSS/E.
- The tables are private (D-03): `anon` and `authenticated` have no access, because the rows carry grid element identifiers from Power Systems' case while this repository and the `city_rating` history are public (OD-6).
- No connection details (host, project reference, key, URL) are published in this repository. The owner hands them to the people who need them.

## Keys, links and time semantics

- `run_id` has the form `psse-<UTC yyyymmddThhmmssZ>-<8 hex>`. The job fixes it once at start and reuses it on retry, so it is the idempotency key.
- `slot_time` is the UTC hour floor of `started_at`: a start at 14:00:00Z and a start at 14:59:59Z both give 14:00:00Z. `started_at` is when the job process began, `finished_at` is the end of the study just before the write, `created_at` is set by the database when the record became visible.
- Each result row links to its run through `(run_id, run_outcome)` -> `psse_run (run_id, outcome)`. `run_outcome` is checked to be `ok` or `fallback`, so no result row can sit under a failed run.
- `psse_dispatched_capacity` links to the `city_rating` row it used through `(city, city_rating_valid_time)`, plus `city_rating_computed_at` for the exact version. This is a soft link and not a foreign key: the PSS/E role has no privilege on `city_rating`, an OD-7 retry may rewrite that row, and a static choice has no row.
- `psse_run` is append-only, a deliberate contrast with `city_rating`'s same-hour overwrite. Two runs in one slot are both kept; the reading rule below says which one counts.

## Columns: public.psse_run

Columns are listed in DDL order. "NULL when" says when the column is empty; "never" means the table forbids NULL.

| Column | Type | Unit | NULL when | Meaning |
|---|---|---|---|---|
| `run_id` | `text` | none (identifier) | never | The run's key, `psse-<UTC yyyymmddThhmmssZ>-<8 hex>`, generated once at job start and reused on retry. Primary key. |
| `slot_time` | `timestamptz` | UTC instant | never | The hour floor of `started_at` in UTC; the table rejects anything that is not a whole UTC hour or does not match `started_at`. SCH-02 gap queries read it. |
| `started_at` | `timestamptz` | UTC instant | never | When the job process started. |
| `finished_at` | `timestamptz` | UTC instant | never | End of the study, just before the write; never before `started_at`. |
| `outcome` | `text` | none (category) | never | `ok`: every city used a `city_rating` row. `fallback`: completed with at least one city on the static rating, including a failed ratings read (D-02). `failed`: no result rows exist for this run. |
| `failed_stage` | `text` | none (category) | outcome is not `failed` | The stage that failed: `load_case`, `mapping`, `apply_ratings`, `load_flow`, `contingency`, `voltage_margin`, `dispatch`, `validate_results`, `write` or `internal`. |
| `error` | `text` | none (text) | outcome is not `failed` | Redacted error text, cut to 1000 characters after redaction. |
| `ratings_read_error` | `text` | none (text) | the ratings read succeeded | Redacted text of why the `latest_rating` read failed (D-02), cut to 1000 characters. |
| `case_id` | `text` | none (label) | never | Label of the PSS/E case, never a path; known from configuration, so present even when the case fails to load. |
| `case_sha256` | `text` | none (identifier) | the case could not be read | Lowercase hex sha256 of the case file bytes. |
| `mapping_sha256` | `text` | none (identifier) | the mapping was not loaded | Lowercase hex sha256 of the city-to-branch mapping file. |
| `rate_set` | `text` | none (label) | the study was not reached | The PSS/E rate set that received the dynamic rating, for example `RATEA`. |
| `ratings_used` | `jsonb` | none (json) | never | Per-city rating used, its source and the link to the newest `city_rating` row read; an object with exactly the four city keys, written for every outcome including `failed`. See "ratings_used: the per-city rating record". |
| `n_contingencies` | `integer` | count | the run failed before screening | Contingencies screened; the completeness reference. |
| `n_contingencies_with_results` | `integer` | count | the run failed before screening | Distinct contingencies with at least one `psse_contingency_result` row. |
| `job_version` | `text` | none (identifier) | never | Short git commit of the job; `unknown` when it cannot be read. |
| `psse_version` | `text` | none (label) | the study was not reached | PSS/E version string reported by the API. |
| `schema_version` | `integer` | none (version) | never | Row schema version; 1. |
| `created_at` | `timestamptz` | UTC instant | never | When the record became visible; set by the database. |

## Columns: public.psse_dispatched_capacity

One row per city for each non-failed run; the full column table is added with the rest of this specification.

## Columns: public.psse_voltage_margin

One row per city for each non-failed run; the full column table is added with the rest of this specification.

## Columns: public.psse_contingency_result

One row per contingency violation of a non-failed run; the full column table is added with the rest of this specification.

## ratings_used: the per-city rating record

The per-city record inside `psse_run.ratings_used`; the key table is added with the rest of this specification.

## Rating selection and static fallback (IN-01)

How each city chooses between its `city_rating` row and the static rating; added with the rest of this specification.

## Units: amps per conductor to MVA per circuit

How per-conductor amperes become per-circuit MVA; added with the rest of this specification.

## All-or-nothing write and failed runs (WB-02)

How one run is written, and what a failed run leaves behind; added with the rest of this specification.

## Completeness checks

The read-only checks that name a partial run; added with the rest of this specification.

## Access: role dlr_psse_writer and grants

Who may read and write the tables; added with the rest of this specification.

## Reading rules

How a reader picks one result set for an hour; added with the rest of this specification.

## Open questions for Power Systems and Phase 6

Questions that this specification leaves open; added with the rest of this specification.

## Versioning

How the schema changes after Phase 6 applies it; added with the rest of this specification.
