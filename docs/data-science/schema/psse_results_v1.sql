-- docs/data-science/schema/psse_results_v1.sql
--
-- Reference DDL for the PSS/E result tables (pss-e-integration Phase 1, DBX-01).
-- NOT a migration: production-pipeline Phase 6 copies the region between the BEGIN and END
-- marker lines, verbatim, into its own migration. Nothing in this workstream applies it to
-- a live database; the local-Postgres tests (backend/tests/psse_schema_pg_test.py) apply it
-- to a throwaway cluster only.
--
-- Creates:
--   public.psse_run                 one row per PSS/E job run (immutable): when it ran, which
--                                   case, which rating each city used, how it ended
--   public.psse_dispatched_capacity four rows per non-failed run (one per city): the rating
--                                   applied, the voltage-stability limit, the capacity dispatched
--   public.psse_voltage_margin      four rows per non-failed run (one per city)
--   public.psse_contingency_result  violations only (zero or more rows per non-failed run)
--   role dlr_psse_writer            the PSS/E job's database role: INSERT and SELECT on these
--                                   four tables only
--
-- Idempotent: tables and the index use if not exists, every policy is dropped before it is
-- created, the role is created inside a guard, grants and comments simply repeat.
--
-- The role is created WITHOUT a credential: the owner sets it once, out of band, and it is
-- never stored in this file, in code or in any committed file.
--
-- Private by design (D-03): anon and authenticated receive nothing. The explicit revoke
-- below also undoes Supabase's legacy auto-grants on new public tables. The role has no
-- privilege on city_rating, pipeline_run or latest_rating, so the PSS/E credential can
-- never change the ratings. Records are immutable: there is no UPDATE, DELETE or TRUNCATE
-- grant, so a retry cannot overwrite a stored run.
--
-- A result row can never belong to a failed run: each child table carries run_outcome
-- (checked to be ok or fallback) and a composite foreign key (run_id, run_outcome) to
-- psse_run (run_id, outcome). The read-only psse_results_v1_checks.sql names any run whose
-- result set is incomplete.
--
-- No function, view or sequence is created here (Supabase auto-grants EXECUTE on functions
-- to the API roles; every key is natural, so no sequence is needed).

-- BEGIN psse_results_v1

create table if not exists public.psse_run (
    run_id text not null constraint psse_run_run_id_ck check (run_id ~ '^psse-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}$'),
    slot_time timestamptz not null constraint psse_run_slot_time_hour_ck check ((slot_time at time zone 'UTC') = date_trunc('hour', slot_time at time zone 'UTC')),
    started_at timestamptz not null,
    finished_at timestamptz not null,
    outcome text not null constraint psse_run_outcome_ck check (outcome in ('ok', 'fallback', 'failed')),
    failed_stage text constraint psse_run_failed_stage_ck check (failed_stage in ('load_case', 'mapping', 'apply_ratings', 'load_flow', 'contingency', 'voltage_margin', 'dispatch', 'validate_results', 'write', 'internal')),
    error text constraint psse_run_error_ck check (length(error) between 1 and 1000),
    ratings_read_error text constraint psse_run_ratings_read_error_ck check (length(ratings_read_error) between 1 and 1000),
    case_id text not null constraint psse_run_case_id_ck check (length(case_id) between 1 and 200 and strpos(case_id, '/') = 0 and strpos(case_id, chr(92)) = 0),
    case_sha256 text constraint psse_run_case_sha256_ck check (case_sha256 ~ '^[0-9a-f]{64}$'),
    mapping_sha256 text constraint psse_run_mapping_sha256_ck check (mapping_sha256 ~ '^[0-9a-f]{64}$'),
    rate_set text,
    ratings_used jsonb not null constraint psse_run_ratings_used_ck check (jsonb_typeof(ratings_used) = 'object' and ratings_used ?& array['AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO']),
    n_contingencies integer constraint psse_run_n_contingencies_ck check (n_contingencies >= 0),
    n_contingencies_with_results integer constraint psse_run_n_contingencies_with_results_ck check (n_contingencies_with_results >= 0),
    job_version text not null,
    psse_version text,
    schema_version integer not null default 1,
    created_at timestamptz not null default date_trunc('second', now()),
    constraint psse_run_pk primary key (run_id),
    constraint psse_run_finished_ck check (finished_at >= started_at),
    constraint psse_run_slot_matches_start_ck check (slot_time = date_trunc('hour', started_at at time zone 'UTC') at time zone 'UTC'),
    constraint psse_run_failed_fields_ck check ((outcome = 'failed') = (error is not null) and (outcome = 'failed') = (failed_stage is not null)),
    constraint psse_run_counts_present_ck check (outcome = 'failed' or (n_contingencies is not null and n_contingencies_with_results is not null)),
    constraint psse_run_counts_order_ck check (n_contingencies_with_results is null or n_contingencies is null or n_contingencies_with_results <= n_contingencies),
    constraint psse_run_run_outcome_uq unique (run_id, outcome)
);

create index if not exists psse_run_slot_time_idx on public.psse_run (slot_time desc);

create table if not exists public.psse_dispatched_capacity (
    run_id text not null,
    run_outcome text not null constraint psse_dispatched_capacity_run_outcome_ck check (run_outcome in ('ok', 'fallback')),
    city text not null constraint psse_dispatched_capacity_city_ck check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO')),
    rating_source text not null constraint psse_dispatched_capacity_rating_source_ck check (rating_source in ('city_rating', 'static_fallback')),
    fallback_reason text constraint psse_dispatched_capacity_fallback_reason_ck check (fallback_reason in ('missing', 'invalid', 'stale', 'provisional', 'read_failed')),
    city_rating_valid_time timestamptz,
    city_rating_computed_at timestamptz,
    applied_amps_per_conductor double precision not null constraint psse_dispatched_capacity_applied_amps_per_conductor_ck check (applied_amps_per_conductor > 0 and applied_amps_per_conductor < 'Infinity'::float8),
    subconductors_per_phase integer not null constraint psse_dispatched_capacity_subconductors_per_phase_ck check (subconductors_per_phase >= 1),
    applied_amps_circuit double precision not null constraint psse_dispatched_capacity_applied_amps_circuit_ck check (applied_amps_circuit > 0 and applied_amps_circuit < 'Infinity'::float8),
    line_voltage_kv double precision not null constraint psse_dispatched_capacity_line_voltage_kv_ck check (line_voltage_kv > 0 and line_voltage_kv < 'Infinity'::float8),
    applied_mva double precision not null constraint psse_dispatched_capacity_applied_mva_ck check (applied_mva > 0 and applied_mva < 'Infinity'::float8),
    voltage_limit_mva double precision not null constraint psse_dispatched_capacity_voltage_limit_mva_ck check (voltage_limit_mva > 0 and voltage_limit_mva < 'Infinity'::float8),
    dispatched_mva double precision not null constraint psse_dispatched_capacity_dispatched_mva_ck check (dispatched_mva > 0 and dispatched_mva < 'Infinity'::float8),
    dispatched_amps_circuit double precision not null constraint psse_dispatched_capacity_dispatched_amps_circuit_ck check (dispatched_amps_circuit > 0 and dispatched_amps_circuit < 'Infinity'::float8),
    dispatched_amps_per_conductor double precision not null constraint psse_dispatched_capacity_dispatched_amps_per_conductor_ck check (dispatched_amps_per_conductor > 0 and dispatched_amps_per_conductor < 'Infinity'::float8),
    power_factor double precision not null constraint psse_dispatched_capacity_power_factor_ck check (power_factor > 0 and power_factor <= 1),
    dispatched_mw double precision not null constraint psse_dispatched_capacity_dispatched_mw_ck check (dispatched_mw > 0 and dispatched_mw < 'Infinity'::float8),
    limiting_factor text not null constraint psse_dispatched_capacity_limiting_factor_ck check (limiting_factor in ('dlr_rating', 'voltage_stability')),
    details jsonb constraint psse_dispatched_capacity_details_ck check (jsonb_typeof(details) = 'object'),
    schema_version integer not null default 1,
    created_at timestamptz not null default date_trunc('second', now()),
    constraint psse_dispatched_capacity_pk primary key (run_id, city),
    constraint psse_dispatched_capacity_run_fk foreign key (run_id, run_outcome) references public.psse_run (run_id, outcome),
    constraint psse_dispatched_capacity_source_reason_rule_ck check ((rating_source = 'city_rating') = (fallback_reason is null)),
    constraint psse_dispatched_capacity_link_rule_ck check ((rating_source = 'city_rating') = (city_rating_valid_time is not null and city_rating_computed_at is not null)),
    constraint psse_dispatched_capacity_circuit_amps_identity_ck check (abs(applied_amps_circuit - applied_amps_per_conductor * subconductors_per_phase) <= 1e-6 * applied_amps_circuit),
    constraint psse_dispatched_capacity_applied_mva_identity_ck check (abs(applied_mva - sqrt(3.0::float8) * line_voltage_kv * applied_amps_circuit / 1000) <= 1e-6 * applied_mva),
    constraint psse_dispatched_capacity_dispatched_mva_rule_ck check (abs(dispatched_mva - least(applied_mva, voltage_limit_mva)) <= 1e-6 * dispatched_mva),
    constraint psse_dispatched_capacity_limiting_factor_rule_ck check ((limiting_factor = 'dlr_rating') = (applied_mva <= voltage_limit_mva)),
    constraint psse_dispatched_capacity_dispatched_amps_identity_ck check (abs(dispatched_amps_circuit - dispatched_mva * 1000 / (sqrt(3.0::float8) * line_voltage_kv)) <= 1e-6 * dispatched_amps_circuit and abs(dispatched_amps_per_conductor * subconductors_per_phase - dispatched_amps_circuit) <= 1e-6 * dispatched_amps_circuit),
    constraint psse_dispatched_capacity_dispatched_mw_identity_ck check (abs(dispatched_mw - dispatched_mva * power_factor) <= 1e-6 * dispatched_mw)
);

create table if not exists public.psse_voltage_margin (
    run_id text not null,
    run_outcome text not null constraint psse_voltage_margin_run_outcome_ck check (run_outcome in ('ok', 'fallback')),
    city text not null constraint psse_voltage_margin_city_ck check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO')),
    method text not null constraint psse_voltage_margin_method_ck check (length(method) between 1 and 100),
    base_transfer_mw double precision constraint psse_voltage_margin_base_transfer_mw_ck check (base_transfer_mw > '-Infinity'::float8 and base_transfer_mw < 'Infinity'::float8),
    limit_transfer_mw double precision constraint psse_voltage_margin_limit_transfer_mw_ck check (limit_transfer_mw > '-Infinity'::float8 and limit_transfer_mw < 'Infinity'::float8),
    margin_mw double precision not null constraint psse_voltage_margin_margin_mw_ck check (margin_mw > '-Infinity'::float8 and margin_mw < 'Infinity'::float8),
    margin_pct double precision constraint psse_voltage_margin_margin_pct_ck check (margin_pct > '-Infinity'::float8 and margin_pct < 'Infinity'::float8),
    voltage_limit_mva double precision not null constraint psse_voltage_margin_voltage_limit_mva_ck check (voltage_limit_mva > 0 and voltage_limit_mva < 'Infinity'::float8),
    critical_bus text,
    min_voltage_pu double precision constraint psse_voltage_margin_min_voltage_pu_ck check (min_voltage_pu > 0 and min_voltage_pu < 'Infinity'::float8),
    details jsonb constraint psse_voltage_margin_details_ck check (jsonb_typeof(details) = 'object'),
    schema_version integer not null default 1,
    created_at timestamptz not null default date_trunc('second', now()),
    constraint psse_voltage_margin_pk primary key (run_id, city),
    constraint psse_voltage_margin_run_fk foreign key (run_id, run_outcome) references public.psse_run (run_id, outcome)
);

create table if not exists public.psse_contingency_result (
    run_id text not null,
    run_outcome text not null constraint psse_contingency_result_run_outcome_ck check (run_outcome in ('ok', 'fallback')),
    contingency_id text not null constraint psse_contingency_result_contingency_id_ck check (length(contingency_id) between 1 and 200),
    violation_kind text not null constraint psse_contingency_result_violation_kind_ck check (violation_kind in ('thermal_overload', 'voltage_low', 'voltage_high', 'non_convergence')),
    element_type text not null constraint psse_contingency_result_element_type_ck check (element_type in ('branch', 'bus', 'contingency')),
    element_id text not null constraint psse_contingency_result_element_id_ck check (length(element_id) between 1 and 200),
    city text constraint psse_contingency_result_city_ck check (city in ('AUSTIN', 'CORPUS_CHRISTI', 'MIDLAND', 'EL_PASO')),
    limit_value double precision,
    observed_value double precision,
    exceeded_by double precision,
    unit text constraint psse_contingency_result_unit_ck check (unit in ('MVA', 'pu')),
    details jsonb constraint psse_contingency_result_details_ck check (jsonb_typeof(details) = 'object'),
    schema_version integer not null default 1,
    created_at timestamptz not null default date_trunc('second', now()),
    constraint psse_contingency_result_pk primary key (run_id, contingency_id, violation_kind, element_id),
    constraint psse_contingency_result_run_fk foreign key (run_id, run_outcome) references public.psse_run (run_id, outcome),
    constraint psse_contingency_result_kind_shape_rule_ck check (
        (violation_kind = 'thermal_overload' and element_type = 'branch' and unit is not distinct from 'MVA')
        or (violation_kind in ('voltage_low', 'voltage_high') and element_type = 'bus' and unit is not distinct from 'pu')
        or (violation_kind = 'non_convergence' and element_type = 'contingency' and element_id = contingency_id
            and unit is null and limit_value is null and observed_value is null and exceeded_by is null)
    ),
    constraint psse_contingency_result_values_rule_ck check (
        violation_kind = 'non_convergence'
        or (limit_value is not null and observed_value is not null and exceeded_by is not null
            and limit_value > 0 and limit_value < 'Infinity'::float8
            and observed_value >= 0 and observed_value < 'Infinity'::float8
            and exceeded_by > 0 and exceeded_by < 'Infinity'::float8)
    ),
    constraint psse_contingency_result_exceeded_rule_ck check (
        violation_kind = 'non_convergence'
        or abs(exceeded_by - case when violation_kind = 'voltage_low' then limit_value - observed_value else observed_value - limit_value end) <= 1e-6 * greatest(abs(limit_value), 1)
    )
);

-- Access (D-03). Row-level security is on and the only policies belong to dlr_psse_writer;
-- a role without a policy sees zero rows and gets no error, so each table has one insert
-- policy and one select policy instead of a policy for all.
alter table public.psse_run enable row level security;
alter table public.psse_dispatched_capacity enable row level security;
alter table public.psse_voltage_margin enable row level security;
alter table public.psse_contingency_result enable row level security;

revoke all on public.psse_run, public.psse_dispatched_capacity, public.psse_voltage_margin, public.psse_contingency_result from public, anon, authenticated;

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'dlr_psse_writer') then
        create role dlr_psse_writer login;
    end if;
end
$$;

grant usage on schema public to dlr_psse_writer;
grant select, insert on public.psse_run, public.psse_dispatched_capacity, public.psse_voltage_margin, public.psse_contingency_result to dlr_psse_writer;

drop policy if exists dlr_psse_writer_insert on public.psse_run;
create policy dlr_psse_writer_insert on public.psse_run for insert to dlr_psse_writer with check (true);
drop policy if exists dlr_psse_writer_select on public.psse_run;
create policy dlr_psse_writer_select on public.psse_run for select to dlr_psse_writer using (true);

drop policy if exists dlr_psse_writer_insert on public.psse_dispatched_capacity;
create policy dlr_psse_writer_insert on public.psse_dispatched_capacity for insert to dlr_psse_writer with check (true);
drop policy if exists dlr_psse_writer_select on public.psse_dispatched_capacity;
create policy dlr_psse_writer_select on public.psse_dispatched_capacity for select to dlr_psse_writer using (true);

drop policy if exists dlr_psse_writer_insert on public.psse_voltage_margin;
create policy dlr_psse_writer_insert on public.psse_voltage_margin for insert to dlr_psse_writer with check (true);
drop policy if exists dlr_psse_writer_select on public.psse_voltage_margin;
create policy dlr_psse_writer_select on public.psse_voltage_margin for select to dlr_psse_writer using (true);

drop policy if exists dlr_psse_writer_insert on public.psse_contingency_result;
create policy dlr_psse_writer_insert on public.psse_contingency_result for insert to dlr_psse_writer with check (true);
drop policy if exists dlr_psse_writer_select on public.psse_contingency_result;
create policy dlr_psse_writer_select on public.psse_contingency_result for select to dlr_psse_writer using (true);

comment on table public.psse_run is 'One row per PSS/E job run, immutable (INSERT and SELECT only). Written once at the end of the run, also when the study failed; a mid-run crash leaves a gap, not a row. Private: no consumer role has any privilege.';
comment on table public.psse_dispatched_capacity is 'Four rows per non-failed run, one per city: the rating applied to the case, the voltage-stability limit and the capacity dispatched. Per circuit, so not comparable with city_rating.rating_mw, which is per conductor.';
comment on table public.psse_voltage_margin is 'Four rows per non-failed run, one per city: the voltage-stability margin of the city transfer.';
comment on table public.psse_contingency_result is 'Contingency violations of a non-failed run. Only violations are stored; a clean contingency has no row (psse_run.n_contingencies_with_results counts the contingencies that do).';

comment on column public.psse_run.run_id is 'none (identifier): psse-<UTC yyyymmddThhmmssZ>-<8 hex>, generated once at job start, reused on retry (idempotency key).';
comment on column public.psse_run.slot_time is 'UTC instant: hour floor of started_at in UTC; SCH-02 gap queries read it.';
comment on column public.psse_run.started_at is 'UTC instant: when the job process started.';
comment on column public.psse_run.finished_at is 'UTC instant: end of the study, just before the write; never before started_at.';
comment on column public.psse_run.outcome is 'none (category): ok: every city used a city_rating row; fallback: completed with at least one city on the static rating (including a failed ratings read, D-02); failed: no result rows exist for this run.';
comment on column public.psse_run.failed_stage is 'none (category): the stage that failed (load_case, mapping, apply_ratings, load_flow, contingency, voltage_margin, dispatch, validate_results, write or internal); NULL unless outcome is failed.';
comment on column public.psse_run.error is 'none (text): redacted, cut to 1000 characters after redaction; NULL unless outcome is failed.';
comment on column public.psse_run.ratings_read_error is 'none (text): redacted, cut to 1000 characters after redaction; why the ratings read failed (D-02); NULL when the read succeeded.';
comment on column public.psse_run.case_id is 'none (label): label of the PSS/E case, never a path; known from configuration, so present even when the load fails.';
comment on column public.psse_run.case_sha256 is 'none (identifier): lowercase hex sha256 of the case file bytes; NULL when the case could not be read.';
comment on column public.psse_run.mapping_sha256 is 'none (identifier): lowercase hex sha256 of the city-to-branch mapping file; NULL when it was not loaded.';
comment on column public.psse_run.rate_set is 'none (label): the PSS/E rate set that received the dynamic rating (for example RATEA); NULL when the study was not reached.';
comment on column public.psse_run.ratings_used is 'none (json): per-city rating used, its source and the link to the newest city_rating row read; see psse_results_v1.md. An object with exactly the four city keys, written for every outcome including failed.';
comment on column public.psse_run.n_contingencies is 'count: contingencies screened (the completeness reference); NULL when the run failed before screening.';
comment on column public.psse_run.n_contingencies_with_results is 'count: distinct contingencies with at least one psse_contingency_result row; NULL when the run failed before screening.';
comment on column public.psse_run.job_version is 'none (identifier): short git commit of the job; unknown when it cannot be read.';
comment on column public.psse_run.psse_version is 'none (label): PSS/E version string reported by the API; NULL when the study was not reached.';
comment on column public.psse_run.schema_version is 'none (version): psse_run row schema version.';
comment on column public.psse_run.created_at is 'UTC instant: when the record became visible; set by the database.';

comment on column public.psse_dispatched_capacity.run_id is 'none (identifier): the run these rows belong to; part of the primary key and of the composite foreign key to psse_run.';
comment on column public.psse_dispatched_capacity.run_outcome is 'none (category): ok or fallback, copied from psse_run.outcome; with run_id it forms the composite foreign key, so a row can never point at a failed run.';
comment on column public.psse_dispatched_capacity.city is 'none (identifier): upper-case project city key, one of AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO.';
comment on column public.psse_dispatched_capacity.rating_source is 'none (category): city_rating when the city used a city_rating row, static_fallback when it used the static rating.';
comment on column public.psse_dispatched_capacity.fallback_reason is 'none (category): why the static rating was used (missing, invalid, stale, provisional or read_failed); NULL when rating_source is city_rating.';
comment on column public.psse_dispatched_capacity.city_rating_valid_time is 'UTC instant: soft link to public.city_rating (city, valid_time); not a foreign key. NULL when the static rating was used.';
comment on column public.psse_dispatched_capacity.city_rating_computed_at is 'UTC instant: city_rating.computed_at of the row used; identifies the exact row version. NULL when the static rating was used.';
comment on column public.psse_dispatched_capacity.applied_amps_per_conductor is 'amperes (A), per conductor: comparable to city_rating.rating_amps.';
comment on column public.psse_dispatched_capacity.subconductors_per_phase is 'count: subconductors per phase the job used to turn per-conductor amps into per-circuit amps.';
comment on column public.psse_dispatched_capacity.applied_amps_circuit is 'amperes (A), per circuit: applied_amps_per_conductor x subconductors_per_phase; what the case effectively received.';
comment on column public.psse_dispatched_capacity.line_voltage_kv is 'kilovolts (kV): base kV of the branch from-bus in the case, used for the MVA conversion.';
comment on column public.psse_dispatched_capacity.applied_mva is 'megavolt-amperes (MVA), per circuit: sqrt(3) x line_voltage_kv x applied_amps_circuit / 1000, no power factor; the value written to the branch rating.';
comment on column public.psse_dispatched_capacity.voltage_limit_mva is 'megavolt-amperes (MVA), per circuit: the voltage-stability limit in the same unit as applied_mva.';
comment on column public.psse_dispatched_capacity.dispatched_mva is 'megavolt-amperes (MVA), per circuit: least(applied_mva, voltage_limit_mva).';
comment on column public.psse_dispatched_capacity.dispatched_amps_circuit is 'amperes (A), per circuit: dispatched_mva x 1000 / (sqrt(3) x line_voltage_kv).';
comment on column public.psse_dispatched_capacity.dispatched_amps_per_conductor is 'amperes (A), per conductor: dispatched_amps_circuit / subconductors_per_phase.';
comment on column public.psse_dispatched_capacity.power_factor is 'dimensionless: power factor used for dispatched_mw only; it is never part of applied_mva.';
comment on column public.psse_dispatched_capacity.dispatched_mw is 'megawatts (MW), per circuit: dispatched_mva x power_factor; per circuit, so not comparable with city_rating.rating_mw, which is per conductor.';
comment on column public.psse_dispatched_capacity.limiting_factor is 'none (category): dlr_rating when applied_mva is at or below voltage_limit_mva (a tie goes to the DLR rating), voltage_stability otherwise.';
comment on column public.psse_dispatched_capacity.details is 'none (json): optional extra facts about the dispatch; NULL when there are none.';
comment on column public.psse_dispatched_capacity.schema_version is 'none (version): psse_dispatched_capacity row schema version.';
comment on column public.psse_dispatched_capacity.created_at is 'UTC instant: when the row became visible; set by the database.';

comment on column public.psse_voltage_margin.run_id is 'none (identifier): the run these rows belong to; part of the primary key and of the composite foreign key to psse_run.';
comment on column public.psse_voltage_margin.run_outcome is 'none (category): ok or fallback, copied from psse_run.outcome; with run_id it forms the composite foreign key, so a row can never point at a failed run.';
comment on column public.psse_voltage_margin.city is 'none (identifier): upper-case project city key, one of AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO.';
comment on column public.psse_voltage_margin.method is 'none (label): how the margin was computed (for example pv_curve).';
comment on column public.psse_voltage_margin.base_transfer_mw is 'megawatts (MW): base-case transfer of the city; NULL when the method does not report it.';
comment on column public.psse_voltage_margin.limit_transfer_mw is 'megawatts (MW): transfer at the voltage-stability limit; NULL when the method does not report it.';
comment on column public.psse_voltage_margin.margin_mw is 'megawatts (MW): limit_transfer_mw minus base_transfer_mw; negative means the base case is already past the limit.';
comment on column public.psse_voltage_margin.margin_pct is 'percent: margin_mw as a percentage of the base transfer; NULL when the method does not report it.';
comment on column public.psse_voltage_margin.voltage_limit_mva is 'megavolt-amperes (MVA), per circuit: the voltage-stability limit; the value psse_dispatched_capacity copies.';
comment on column public.psse_voltage_margin.critical_bus is 'none (identifier): the bus that limits the transfer; NULL when not reported.';
comment on column public.psse_voltage_margin.min_voltage_pu is 'per unit (pu): lowest bus voltage at the limit; NULL when not reported.';
comment on column public.psse_voltage_margin.details is 'none (json): optional extra facts about the margin; NULL when there are none.';
comment on column public.psse_voltage_margin.schema_version is 'none (version): psse_voltage_margin row schema version.';
comment on column public.psse_voltage_margin.created_at is 'UTC instant: when the row became visible; set by the database.';

comment on column public.psse_contingency_result.run_id is 'none (identifier): the run this violation belongs to; part of the primary key and of the composite foreign key to psse_run.';
comment on column public.psse_contingency_result.run_outcome is 'none (category): ok or fallback, copied from psse_run.outcome; with run_id it forms the composite foreign key, so a row can never point at a failed run.';
comment on column public.psse_contingency_result.contingency_id is 'none (identifier): label of the outage, for example the tripped branch from-to-circuit.';
comment on column public.psse_contingency_result.violation_kind is 'none (category): thermal_overload, voltage_low, voltage_high or non_convergence.';
comment on column public.psse_contingency_result.element_type is 'none (category): branch, bus or contingency (for non_convergence).';
comment on column public.psse_contingency_result.element_id is 'none (identifier): branch from-to-circuit or bus number; the contingency id for non_convergence.';
comment on column public.psse_contingency_result.city is 'none (identifier): the city whose mapped branch this is; NULL for other elements.';
comment on column public.psse_contingency_result.limit_value is 'megavolt-amperes (MVA) for thermal_overload, per unit (pu) for voltage kinds: the limit used; NULL for non_convergence.';
comment on column public.psse_contingency_result.observed_value is 'megavolt-amperes (MVA) for thermal_overload, per unit (pu) for voltage kinds: the post-contingency value; NULL for non_convergence.';
comment on column public.psse_contingency_result.exceeded_by is 'megavolt-amperes (MVA) for thermal_overload, per unit (pu) for voltage kinds: observed minus limit (voltage_low: limit minus observed), always positive; NULL for non_convergence.';
comment on column public.psse_contingency_result.unit is 'none (category): MVA for thermal_overload, pu for voltage kinds; NULL for non_convergence.';
comment on column public.psse_contingency_result.details is 'none (json): optional extra facts about the violation; NULL when there are none.';
comment on column public.psse_contingency_result.schema_version is 'none (version): psse_contingency_result row schema version.';
comment on column public.psse_contingency_result.created_at is 'UTC instant: when the row became visible; set by the database.';

-- END psse_results_v1
