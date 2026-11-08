# API Coverage — Open-Meteo Single Runs, TCEQ / Synoptic stations, Supabase (Postgres writer and Data API), cron-job.org alarm

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Scope: Phase 8 serves `ml_cooling_corrected` as a labelled day-ahead forecast alongside the 60-minute G6
> forecast (plans 08-01 .. 08-12). Every external call for the value goes through the frozen shadow
> functions unchanged (D-03); this phase adds no new provider client. Supabase surfaces extend the
> Phase 4 writer and the Phase 6 read-only REST exposure. No new cron job (D-12).

| capability | decision | reason |
|---|---|---|
| open_meteo.single_run_exact_24h_init | INTEGRATE | |
| open_meteo.single_run_unavailable_handling | INTEGRATE | |
| open_meteo.single_run_other_leads | OPT-OUT | explicitly out of scope: deferred idea in 08-CONTEXT (hourly issuance at 25-29 h leads needs evidence first) |
| open_meteo.forecast_api_latest_run | OPT-OUT | explicitly out of scope: D-01 fixes the exact 24 h-old run that TEST and reads 1-2 measured |
| open_meteo.archive_reanalysis | OPT-OUT | not needed: the launch band is built from the tracked TEST rows CSV; the live band grades against stored ratings |
| open_meteo.other_models_and_ensembles | OPT-OUT | explicitly out of scope: the served method and its band were measured on gfs_seamless only |
| station_anchor.tceq_with_synoptic_fallback | INTEGRATE | |
| station_anchor.asos_supplement_and_bulk_history | OPT-OUT | not needed: one most-recent reading per run, as the frozen anchor function already decides |
| supabase_postgres.writer_insert_first_write_wins | INTEGRATE | |
| supabase_postgres.writer_select_existing_targets | INTEGRATE | |
| supabase_postgres.writer_update_delete | OPT-OUT | explicitly out of scope: insert-only writer so an issued value is never rewritten (owner-confirmed in 08-07) |
| supabase_postgres.pipeline_run_day_ahead_upsert | INTEGRATE | |
| supabase_postgres.read_only_verification | INTEGRATE | |
| supabase_postgres.additive_schema_migrations | INTEGRATE | |
| postgrest.read_view_day_ahead_upcoming | INTEGRATE | |
| postgrest.read_view_day_ahead_status | INTEGRATE | |
| postgrest.read_table_day_ahead_forecast | INTEGRATE | |
| postgrest.select_filters_order_pagination | INTEGRATE | |
| postgrest.rpc_assert_fresh_day_ahead_clause | INTEGRATE | |
| postgrest.insert_upsert_update_delete | OPT-OUT | explicitly out of scope: read-only for consumers (OD-6, D-09); exercised only to prove refusal (--check-rest) |
| postgrest.second_rpc_or_overload | OPT-OUT | explicitly out of scope: an overload would make the alarm URL answer HTTP 300; D-12 keeps one URL |
| supabase.realtime_storage_edge_graphql_auth | OPT-OUT | explicitly out of scope: same decisions as Phase 6 (REST is the decided read interface; models stay in git, OD-10) |
| cron_job_org.existing_alarm_job | INTEGRATE | |
| cron_job_org.new_job | OPT-OUT | explicitly out of scope: D-12 forbids a new cron job; the existing alarm covers the feed |
| github_actions.existing_hourly_workflow | INTEGRATE | |
| github_actions.new_workflow_or_workflow_edit | OPT-OUT | explicitly out of scope: D-02 (no new workflow); the pinned workflow file is not edited |

Notes on the INTEGRATE rows:
- `open_meteo.single_run_exact_24h_init`: `forecast_shadow_pipeline.fetch_live_forecast_for_valid_time`, the run initialised exactly 24 h before the target, model `gfs_seamless`, called unchanged (08-01).
- `open_meteo.single_run_unavailable_handling`: the frozen retry policy; `StaleOrMissingDataError` means no row and a logged reason (D-16), retried by the next hourly run (D-04).
- `station_anchor.tceq_with_synoptic_fallback`: `forecast_shadow_pipeline.fetch_live_anchor_observation`, once per city per run (08-04).
- `supabase_postgres.*`: `public.day_ahead_forecast` insert with on conflict do nothing and select of existing keys and live band pairs (08-01, 08-03, 08-04); `pipeline_run.day_ahead` upsert of `{run_id, day_ahead}` (08-02); read-only checks `day_ahead_verify.py --check-store` and `verify_day_ahead_store.sql` (08-04, 08-06); two owner-applied migrations (08-07, 08-11).
- `postgrest.*`: `GET /rest/v1/day_ahead_upcoming`, `/day_ahead_status`, `/day_ahead_forecast`, and `GET /rest/v1/rpc/assert_fresh` with the same signature (08-09, 08-10, 08-11); the two views are also read by the three consumer examples (curl, supabase-js, stdlib Python), extended in 08-12 and run live in 08-11 (D-18).
- `cron_job_org.existing_alarm_job` and `github_actions.existing_hourly_workflow`: unchanged URL, key and workflow file; the stage runs inside `dlr_live_run.py` (08-02).
