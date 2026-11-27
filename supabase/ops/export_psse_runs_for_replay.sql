-- supabase/ops/export_psse_runs_for_replay.sql
--
-- The project owner's export of the recorded PSS/E runs, for the replay of those runs through
-- pandapower (the pandapower workstream, phase 4, plan 04-01, owner decision D-01).
--
-- What this file is. One SELECT. It is read-only and changes nothing: no table, row, setting or role
-- is touched. It is never applied by the Supabase CLI (this directory holds no migration). It reads
-- the four private PSS/E result tables, which only the project owner and the writer role can read,
-- and returns ONE row with five columns: counts, runs, dispatch, margins, contingencies. The first
-- column holds how many rows each of the other four holds, so the importer can refuse a file that
-- was cut short.
--
-- Who runs it, and how:
--   1. Open the project's SQL editor in the Supabase dashboard (the project owner's login).
--   2. Paste the whole file and run it. One row comes back. If the editor shows an error, send only
--      the error text.
--   3. Download the result with the result panel's CSV download button (or copy it as JSON if the
--      panel offers that). The importer reads either form.
--   4. Send the downloaded file by the private channel the reference-session zip used. Do not paste
--      the result into a chat, an issue, a pull request or the repository: it holds the recorded
--      run ids, the hashes of the case and the mapping, and every dispatched and contingency value.
--   5. The person who receives it saves it under data/private/pandapower/incoming/ (a folder that git
--      ignores) and runs the importer there. Nothing connects to the database again after this
--      step.
--
-- The first export should be narrow. Change the run-id pattern 'psse-%' in the first common table
-- expression below to a date prefix that covers the days the recorded runs exist, such as
-- 'psse-202611%' (a run id is psse-, then the UTC date and time of its start, then 8 hex digits).
-- Widen the prefix only if more runs are needed. If a file comes back cut short, or the importer says
-- it is too large, narrow the pattern again and rerun; that is safe, because the importer refuses a
-- file whose own counts do not match its rows.
--
-- What it selects, and what it leaves out. Only the columns the replay reads (they are pinned in
-- backend/pandapower_job/recorded.py, and a text test holds the two in step). The error text, the
-- ratings read error and the case label are never selected. Result rows are read only for runs whose
-- outcome is ok or fallback; a failed run has none. It filters runs on the run-id prefix and names
-- no column that a later migration adds, because that migration may not be applied to the live
-- project yet (research Pitfall 6): the same file works before and after it.
--
-- The local proofs of this file are backend/tests/pandapower_recorded_test.py (its text: one
-- statement, no write word, the pinned columns) and backend/tests/pandapower_replay_pg_test.py (it
-- runs on a throwaway Postgres in a read-only session, and the four tables are unchanged).

with
runs as (
    select run_id, slot_time, outcome, failed_stage, case_sha256, mapping_sha256, rate_set,
           ratings_used, n_contingencies, n_contingencies_with_results, job_version
      from public.psse_run
     where run_id like 'psse-%'
),
usable as (
    select run_id
      from runs
     where outcome in ('ok', 'fallback')
),
dispatch as (
    select run_id, city, rating_source, fallback_reason, applied_amps_per_conductor,
           subconductors_per_phase, applied_amps_circuit, line_voltage_kv, applied_mva,
           voltage_limit_mva, dispatched_mva, limiting_factor, details
      from public.psse_dispatched_capacity
     where run_id in (select run_id from usable)
),
margins as (
    select run_id, city, method, base_transfer_mw, limit_transfer_mw, margin_mw,
           voltage_limit_mva, critical_bus, min_voltage_pu, details
      from public.psse_voltage_margin
     where run_id in (select run_id from usable)
),
contingencies as (
    select run_id, contingency_id, violation_kind, element_type, element_id, city,
           limit_value, observed_value, exceeded_by, unit
      from public.psse_contingency_result
     where run_id in (select run_id from usable)
)
select
    jsonb_build_object(
        'runs', (select count(*) from runs),
        'usable_runs', (select count(*) from usable),
        'dispatch', (select count(*) from dispatch),
        'margins', (select count(*) from margins),
        'contingencies', (select count(*) from contingencies)
    ) as counts,
    (select coalesce(
        jsonb_agg(to_jsonb(r) order by r.slot_time, r.run_id),
        '[]'::jsonb)
       from runs r) as runs,
    (select coalesce(
        jsonb_agg(to_jsonb(d) order by d.run_id, d.city),
        '[]'::jsonb)
       from dispatch d) as dispatch,
    (select coalesce(
        jsonb_agg(to_jsonb(m) order by m.run_id, m.city),
        '[]'::jsonb)
       from margins m) as margins,
    (select coalesce(
        jsonb_agg(to_jsonb(c) order by c.run_id, c.contingency_id, c.violation_kind, c.element_id),
        '[]'::jsonb)
       from contingencies c) as contingencies;
