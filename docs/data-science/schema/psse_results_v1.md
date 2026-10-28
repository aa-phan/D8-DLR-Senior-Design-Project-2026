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
- The link columns are filled only when `rating_source` is `city_rating` and are NULL otherwise; the database enforces this. A city that fell back as `stale` or `provisional` therefore has NULL link columns in `psse_dispatched_capacity`; the row that was read but not used is recorded only in `psse_run.ratings_used`.
- `psse_run` is append-only, a deliberate contrast with `city_rating`'s same-hour overwrite. Two runs in one slot are both kept; the reading rules say which one counts.

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

Columns are listed in DDL order. Four rows per non-failed run, one per city. Primary key `(run_id, city)`.

| Column | Type | Unit | NULL when | Meaning |
|---|---|---|---|---|
| `run_id` | `text` | none (identifier) | never | The run these rows belong to; part of the primary key and of the composite foreign key to `psse_run`. |
| `run_outcome` | `text` | none (category) | never | `ok` or `fallback`, copied from `psse_run.outcome`; with `run_id` it is the composite foreign key, so a row can never point at a failed run. |
| `city` | `text` | none (identifier) | never | City key, one of `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`. |
| `rating_source` | `text` | none (category) | never | `city_rating` when the city used a `city_rating` row; `static_fallback` when it used the static rating. |
| `fallback_reason` | `text` | none (category) | `rating_source` is `city_rating` | Why the static rating was used: `missing`, `invalid`, `stale`, `provisional` or `read_failed`. |
| `city_rating_valid_time` | `timestamptz` | UTC instant | `rating_source` is not `city_rating` (also for a stale or provisional fallback, whose link lives only in `ratings_used`) | Soft link to `city_rating (city, valid_time)`; not a foreign key. |
| `city_rating_computed_at` | `timestamptz` | UTC instant | `rating_source` is not `city_rating` | `city_rating.computed_at` of the row used; identifies the exact row version. |
| `applied_amps_per_conductor` | `double precision` | A, per conductor | never | The rating applied to the case, per conductor; comparable with `city_rating.rating_amps`. |
| `subconductors_per_phase` | `integer` | count | never | Subconductors per phase used to turn per-conductor amperes into per-circuit amperes. |
| `applied_amps_circuit` | `double precision` | A, per circuit | never | `applied_amps_per_conductor` times `subconductors_per_phase`; what the case effectively received. |
| `line_voltage_kv` | `double precision` | kV | never | Base kV of the mapped branch's from-bus in the case, used for the MVA conversion. |
| `applied_mva` | `double precision` | MVA, per circuit | never | `sqrt(3)` times `line_voltage_kv` times `applied_amps_circuit` divided by 1000, no power factor; the value written to the branch rating. |
| `voltage_limit_mva` | `double precision` | MVA, per circuit | never | The voltage-stability limit in the same unit as `applied_mva`. |
| `dispatched_mva` | `double precision` | MVA, per circuit | never | The smaller of `applied_mva` and `voltage_limit_mva`. |
| `dispatched_amps_circuit` | `double precision` | A, per circuit | never | `dispatched_mva` times 1000 divided by (`sqrt(3)` times `line_voltage_kv`). |
| `dispatched_amps_per_conductor` | `double precision` | A, per conductor | never | `dispatched_amps_circuit` divided by `subconductors_per_phase`. |
| `power_factor` | `double precision` | dimensionless | never | Power factor used for `dispatched_mw` only; it is never part of `applied_mva`. |
| `dispatched_mw` | `double precision` | MW, per circuit | never | `dispatched_mva` times `power_factor`. |
| `limiting_factor` | `text` | none (category) | never | `dlr_rating` when `applied_mva` is at or below `voltage_limit_mva` (a tie goes to the DLR rating); `voltage_stability` otherwise. |
| `details` | `jsonb` | none (json) | there are no extra facts | Optional extra facts about the dispatch. |
| `schema_version` | `integer` | none (version) | never | Row schema version; 1. |
| `created_at` | `timestamptz` | UTC instant | never | When the row became visible; set by the database. |

`dispatched_mw` is per circuit and is not comparable with `city_rating.rating_mw`, which is per conductor. To compare with the rating pipeline, use `applied_amps_per_conductor` against `city_rating.rating_amps`.

## Columns: public.psse_voltage_margin

Columns are listed in DDL order. Four rows per non-failed run, one per city. Primary key `(run_id, city)`.

| Column | Type | Unit | NULL when | Meaning |
|---|---|---|---|---|
| `run_id` | `text` | none (identifier) | never | The run these rows belong to; part of the primary key and of the composite foreign key to `psse_run`. |
| `run_outcome` | `text` | none (category) | never | `ok` or `fallback`, copied from `psse_run.outcome`; with `run_id` it is the composite foreign key. |
| `city` | `text` | none (identifier) | never | City key, one of `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND`, `EL_PASO`. |
| `method` | `text` | none (label) | never | How the margin was computed, for example `pv_curve`. |
| `base_transfer_mw` | `double precision` | MW | the method does not report it | Base-case transfer of the city. |
| `limit_transfer_mw` | `double precision` | MW | the method does not report it | Transfer at the voltage-stability limit. |
| `margin_mw` | `double precision` | MW | never | `limit_transfer_mw` minus `base_transfer_mw`; negative means the base case is already past the limit. |
| `margin_pct` | `double precision` | percent | the method does not report it | `margin_mw` as a percentage of the base transfer. |
| `voltage_limit_mva` | `double precision` | MVA, per circuit | never | The voltage-stability limit; the value `psse_dispatched_capacity` copies. |
| `critical_bus` | `text` | none (identifier) | not reported | The bus that limits the transfer. |
| `min_voltage_pu` | `double precision` | per unit (pu) | not reported | Lowest bus voltage at the limit. |
| `details` | `jsonb` | none (json) | there are no extra facts | Optional extra facts about the margin. |
| `schema_version` | `integer` | none (version) | never | Row schema version; 1. |
| `created_at` | `timestamptz` | UTC instant | never | When the row became visible; set by the database. |

## Columns: public.psse_contingency_result

Columns are listed in DDL order. Primary key `(run_id, contingency_id, violation_kind, element_id)`.

| Column | Type | Unit | NULL when | Meaning |
|---|---|---|---|---|
| `run_id` | `text` | none (identifier) | never | The run this violation belongs to; part of the primary key and of the composite foreign key to `psse_run`. |
| `run_outcome` | `text` | none (category) | never | `ok` or `fallback`, copied from `psse_run.outcome`; with `run_id` it is the composite foreign key. |
| `contingency_id` | `text` | none (identifier) | never | Label of the outage, for example the tripped branch as from-to-circuit. |
| `violation_kind` | `text` | none (category) | never | `thermal_overload`, `voltage_low`, `voltage_high` or `non_convergence`. |
| `element_type` | `text` | none (category) | never | `branch`, `bus` or `contingency` (for `non_convergence`). |
| `element_id` | `text` | none (identifier) | never | Branch as from-to-circuit or bus number; the contingency id for `non_convergence`. |
| `city` | `text` | none (identifier) | the element is not a city's mapped branch | The city whose mapped branch this is. |
| `limit_value` | `double precision` | MVA for `thermal_overload`, per unit (pu) for voltage kinds | `violation_kind` is `non_convergence` | The limit used. |
| `observed_value` | `double precision` | MVA for `thermal_overload`, per unit (pu) for voltage kinds | `violation_kind` is `non_convergence` | The post-contingency value. |
| `exceeded_by` | `double precision` | MVA for `thermal_overload`, per unit (pu) for voltage kinds | `violation_kind` is `non_convergence` | Observed minus limit (`voltage_low`: limit minus observed); always positive. |
| `unit` | `text` | none (category) | `violation_kind` is `non_convergence` | `MVA` for `thermal_overload`, `pu` for the voltage kinds. |
| `details` | `jsonb` | none (json) | there are no extra facts | Optional extra facts about the violation. |
| `schema_version` | `integer` | none (version) | never | Row schema version; 1. |
| `created_at` | `timestamptz` | UTC instant | never | When the row became visible; set by the database. |

Only violations are written: a contingency with no violation has no row, and `psse_run.n_contingencies_with_results` counts the contingencies that do. A contingency whose post-contingency solution does not converge is a `non_convergence` row, while a base-case load flow that does not converge fails the whole run (STU-01).

## ratings_used: the per-city rating record

`psse_run.ratings_used` is a JSON object with exactly the four city keys, written for every outcome including `failed`; each city's value is an object with these keys, in this order:

| Key | JSON type | Unit | NULL when | Meaning |
|---|---|---|---|---|
| `source` | string | none (category) | never | `city_rating` when the newest row was used, `static_fallback` when the static rating was used. |
| `fallback_reason` | string | none (category) | `source` is `city_rating` | `missing`, `invalid`, `stale`, `provisional` or `read_failed`. |
| `rating_amps_per_conductor` | number | A, per conductor | never | The rating applied: the row's `rating_amps` when used, otherwise the static value. |
| `subconductors_per_phase` | integer | count | never | Subconductors per phase the job used. |
| `rating_amps_circuit` | number | A, per circuit | never | `rating_amps_per_conductor` times `subconductors_per_phase`. |
| `static_rating_amps_per_conductor` | number | A, per conductor | never | The static rating from `backend/config.py`, never the row's `static_rating_amps`. |
| `line_voltage_kv` | number | kV | the study did not reach the dispatched-capacity rows | Base kV the study used, filled from the study's dispatched-capacity rows (Phase 2). |
| `rating_mva` | number | MVA, per circuit | the study did not reach the dispatched-capacity rows | `applied_mva` of the study, filled from the dispatched-capacity rows (Phase 2). |
| `city_rating_valid_time` | string (UTC instant) | UTC instant | no usable row was read (`missing`, `invalid`, `read_failed`) | `valid_time` of the newest row read, whether or not it was used. |
| `city_rating_computed_at` | string (UTC instant) | UTC instant | no usable row was read | `computed_at` of the newest row read; identifies its exact version. |
| `city_rating_run_id` | string | none (identifier) | no usable row was read, or the row had no `run_id` | The pipeline run that wrote that row. |
| `city_rating_status` | string | none (category) | no usable row was read | The row's `status` (`ok` or `fallback`); a fresh non-provisional `fallback` row is still used as `city_rating`. |
| `config_fingerprint` | string | none (identifier) | no usable row was read | The row's `config_fingerprint`. |
| `age_minutes` | number | minutes | no usable row was read | Age of the row at the job's clock, to two decimals. |
| `server_is_stale` | boolean | none (flag) | no usable row was read | The server's `is_stale` flag for the row. |
| `server_is_provisional` | boolean | none (flag) | no usable row was read | The server's `is_provisional` flag for the row. |

The link fields (`city_rating_valid_time` through `server_is_provisional`) describe the newest row that was read, whether or not it was used; `source` says whether it was used. `line_voltage_kv` and `rating_mva` are filled from the study's dispatched-capacity rows (Phase 2) and are null when the study did not reach them.

## Rating selection and static fallback (IN-01)

The job reads the newest `latest_rating` row per city once, at start, and takes its clock once for all four cities.

- A city uses its row as `city_rating` unless a reason below applies; then it uses the static rating and records the reason. Reason precedence for one row: `missing`, `invalid`, `stale`, `provisional`.
- `missing`: the read succeeded but no row exists for the city.
- `invalid`: the row cannot be trusted: it is not an object for that city, `rating_amps` is not a finite number above zero, a timestamp does not parse, a server flag is not true or false, `valid_time` is more than 5 minutes ahead of the job's clock, or two rows came back for one city.
- `stale`: the row is older than 90 minutes at the job's clock; exactly 90 minutes is fresh. The server's `is_stale` flag and the job's own age check are OR-ed, so clock skew can only move a city toward static.
- `provisional`: the row's server flag `is_provisional` is true.
- `read_failed`: the read itself failed. All four cities then use the static rating with this reason, `psse_run.ratings_read_error` records the redacted cause, and the run continues with outcome `fallback`, never `failed` (D-02).
- The static rating is the per-conductor value from `backend/config.py` (the job keeps a copy that a test pins to it) times the city's subconductor count. It is never the row's `static_rating_amps`: a missing row has none, and two sources could differ after a configuration change.
- Today every `city_rating` row is provisional, so all four cities use the static rating with reason `provisional` until Phase 7's go (REVAL-01).
- Note for Phase 3: the live pipeline writes the hour's row a few minutes after the hour, so a job started after about HH:30 with the current slot's row not yet written finds the previous slot's row older than 90 minutes and goes all-static with reason `stale`. The recorded `age_minutes` shows it.

## Units: amps per conductor to MVA per circuit

The job reads `rating_amps` (per conductor) and converts it; it never reads `rating_mw`.

- Amps per circuit = amps per conductor times subconductors per phase.
- MVA per circuit = sqrt(3) times kV times amps per circuit divided by 1000. There is no power factor: PSS/E branch ratings are apparent power.
- kV is the base kV of the mapped branch's bus in Power Systems' case, applied by Phase 2 (IN-03). The nominal 345 kV below is only for the worked table.

| City | A per conductor | Subconductors | A per circuit | Stored static rating_mw (MW, per conductor, pf 0.95) | MVA per circuit at 345 kV | Ratio |
|---|---|---|---|---|---|---|
| AUSTIN | 1825.0 | 2 | 3650.0 | 1036.0 | 2181.1 | 2.105 |
| CORPUS_CHRISTI | 1500.0 | 2 | 3000.0 | 851.5 | 1792.7 | 2.105 |
| MIDLAND | 1875.0 | 2 | 3750.0 | 1064.4 | 2240.8 | 2.105 |
| EL_PASO | 1320.0 | 1 | 1320.0 | 749.3 | 788.8 | 1.053 |

Warning: `rating_mw` is per conductor and includes a power factor of 0.95. Reading it as the branch rating would understate the per-circuit rating about 2.1 times for the three bundled cities, so the job reads `rating_amps` only (D-06).

- A PSS/E rating of 0 means "no limit", so a zero or missing rating is never written to a branch; it is `invalid` and goes to the static rating.
- The database itself rejects a dispatched-capacity row whose `applied_mva` breaks the identity above.
- Assumption: all of a city's mapped branches share one base kV. If Power Systems' mapping says otherwise, Phase 2 raises it before Phase 6's push.

## All-or-nothing write and failed runs (WB-02)

- A successful study is written in one transaction that holds the `psse_run` row and every result row, so a reader sees all of a run or none of it.
- A failed study writes `psse_run` alone: outcome `failed`, a `failed_stage`, a redacted `error` of at most 1000 characters, and `ratings_used` still filled (the selection ran before the study).
- A failed result write rolls back, and a new transaction then records the run as failed with `failed_stage` `write`. If even that cannot be written (database unreachable, laptop asleep mid-run), no row exists and the hour shows as a gap (SCH-02, Phase 3).
- There is no "running" row (D-04): one run record is written at the end, and a mid-run crash is a gap.
- Outcomes: `ok` means every city used a `city_rating` row; `fallback` means the study completed with at least one city on the static rating; `failed` means the study did not complete and no result rows exist.
- Idempotency: the insert is `insert ... on conflict (run_id) do nothing`, so a retry after a lost commit acknowledgement writes nothing new.

## Completeness checks

`docs/data-science/schema/psse_results_v1_checks.sql` is one read-only statement returning `check_name, ok, detail`, one row per check. The expected result is every row `ok`. Phase 3's read-back runs it.

- `non_failed_runs_have_four_dispatch_rows`: every `ok` or `fallback` run has one `psse_dispatched_capacity` row per city.
- `non_failed_runs_have_four_margin_rows`: the same for `psse_voltage_margin`.
- `non_failed_runs_contingency_count_matches`: the number of distinct `contingency_id` values among a run's `psse_contingency_result` rows equals `psse_run.n_contingencies_with_results`.
- `failed_runs_have_no_results`: no failed run has a row in any of the three result tables.
- `dispatch_voltage_limit_matches_margin`: for each run and city, `voltage_limit_mva` agrees between `psse_dispatched_capacity` and `psse_voltage_margin`.

## Access: role dlr_psse_writer and grants

- `dlr_psse_writer` holds INSERT and SELECT on the four tables and nothing else. It has no UPDATE, DELETE or TRUNCATE (records are immutable, and a rerun cannot overwrite a good run).
- It holds no privilege on `city_rating`, `pipeline_run` or `latest_rating`; the ratings are read through REST.
- `anon` and `authenticated` receive nothing. The DDL's explicit revoke also undoes Supabase's legacy automatic grants on new tables.
- Row-level security is on, with the policies `dlr_psse_writer_insert` and `dlr_psse_writer_select` on each table.
- "Only `dlr_psse_writer`" describes the roles this schema grants. It does not cover `service_role` (Supabase's service key bypasses row-level security) or the database owner: whoever holds those can read and change these tables, so those keys stay out of the laptop and out of the repository.
- No credential appears in any file. The write credential is `SUPABASE_PSSE_DB_URL`; the ratings read uses Phase 6's `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (DBX-02, proven live in Phase 3).

## Reading rules

- The result set of an hour is the newest `psse_run` for that `slot_time` with outcome in (`ok`, `fallback`), ordered by `started_at desc, run_id desc`. A failed run never has results.
- Check completeness (the checks file) before trusting a set.
- Never combine values across cities: there is no corridor minimum and no bottleneck value.
- `dispatched_mw` is per circuit and `city_rating.rating_mw` is per conductor; compare `applied_amps_per_conductor` with `city_rating.rating_amps` instead.

## Open questions for Power Systems and Phase 6

1. Which rate set (RATEA, RATEB or RATEC) receives the DLR value, and which rating-units program setting does the case use?
2. Case size and expected contingency volume (row volume and retention); no retention is defined in this milestone.
3. Does a city map to branches of different base kV?
4. Should results ever be public? Not now (D-03); that would be a new owner decision and a new schema version.
5. Phase 6's vehicle: amend 06-09 or add a separate push (see the hand-off note).
6. The laptop's PSS/E Python version and the matching psycopg pin (Phase 3).

## Versioning

- `schema_version` is 1. Once Phase 6 applies the tables, changes are additive migrations only; a rename or drop needs a new schema version.
- The sha256 of the marked DDL region is pinned in the hand-off note and re-checked by `backend/tests/psse_schema_doc_test.py`.
