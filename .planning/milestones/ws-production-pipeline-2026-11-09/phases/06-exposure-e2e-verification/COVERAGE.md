# API Coverage — Supabase Data API (PostgREST), supabase-js, pg_cron, cron-job.org, GitHub Actions

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Scope: Phase 6 exposes ratings through Supabase's built-in REST API (decided architecture) and verifies the
> live pipeline with read-only tooling. Plans: 06-01 .. 06-13 (replanned 2026-10-25 for CONTEXT D-01..D-15).
> The freshness alarm is permanent (D-13), runs every 15 min, notifies after 2 failures, on recovery and
> on job disable, owner-only (D-14, D-15). Every example pages past the 1000-row cap (D-12).

| capability | decision | reason |
|---|---|---|
| postgrest.read_table (GET /rest/v1/city_rating) | INTEGRATE | |
| postgrest.read_view (GET /rest/v1/latest_rating, 34-column contract) | INTEGRATE | |
| postgrest.select_columns (select=) | INTEGRATE | |
| postgrest.filters (eq, in, gte, lt, repeated filters on one column) | INTEGRATE | |
| postgrest.ordering (order=) | INTEGRATE | |
| postgrest.pagination (limit/offset, Range; past the 1000-row cap) | INTEGRATE | |
| postgrest.exact_count (Prefer: count=exact) | INTEGRATE | |
| postgrest.singular_object (Accept: application/vnd.pgrst.object+json) | INTEGRATE | |
| postgrest.rpc (GET /rest/v1/rpc/assert_fresh, 200/503) | INTEGRATE | |
| postgrest.insert (POST) | OPT-OUT | explicitly out of scope: read-only for consumers by decision OD-6; exercised only to prove rejection (E2E-03) |
| postgrest.upsert (POST on_conflict) | OPT-OUT | explicitly out of scope: read-only by OD-6; exercised only to prove rejection (E2E-03) |
| postgrest.update (PATCH) | OPT-OUT | explicitly out of scope: read-only by OD-6; exercised only to prove rejection (E2E-03) |
| postgrest.delete (DELETE) | OPT-OUT | explicitly out of scope: read-only by OD-6; exercised only to prove rejection (E2E-03) |
| postgrest.resource_embedding (joins) | OPT-OUT | not needed: one table and one view, no foreign-key relationships to embed |
| postgrest.openapi_spec (GET /rest/v1/) | OPT-OUT | not available to the publishable key since April 2026; the committed docs/integration/rest-api.md is the contract |
| postgrest.custom_schema_profiles (Accept-Profile) | OPT-OUT | explicitly out of scope: public schema with explicit grants; the ops schema stays unexposed and is only probed to prove it is unreachable |
| postgrest.alternate_formats (CSV, GeoJSON) | OPT-OUT | not needed yet: JSON covers both consumers |
| postgrest.aggregates_in_select | OPT-OUT | not needed: consumers read rows, latest_rating already reduces to one row per city |
| supabase.auth (user sign-up, user JWTs) | OPT-OUT | explicitly out of scope: no user accounts; the publishable key maps to the read-only anon role |
| supabase.realtime (subscriptions) | OPT-OUT | not needed yet: data changes hourly; polling every 60 s or more is documented |
| supabase.storage | OPT-OUT | explicitly out of scope: OD-10 keeps the model artifacts in git |
| supabase.graphql (pg_graphql) | OPT-OUT | explicitly out of scope: the decided read interface is REST |
| supabase.edge_functions | OPT-OUT | explicitly out of scope: no custom API server in this workstream |
| supabase.pg_cron (5-minute soak log: schedule, unschedule, run details) | INTEGRATE | |
| supabase.management_api | OPT-OUT | not needed: the owner uses the dashboard, SQL editor and Phase 4's CLI procedure |
| supabase_js.create_client | INTEGRATE | |
| supabase_js.select_filters_order_limit_single_count | INTEGRATE | |
| supabase_js.range_pagination (.range past the 1000-row cap) | INTEGRATE | |
| supabase_js.writes (insert, update, upsert, delete) | OPT-OUT | explicitly out of scope: the frontend example is read-only (OD-6) |
| supabase_js.auth_realtime_storage_functions_modules | OPT-OUT | not needed: consumers only read ratings |
| cron_job_org.http_job_with_header_and_notifications (permanent alarm) | INTEGRATE | |
| cron_job_org.execution_history (console) | INTEGRATE | |
| cron_job_org.rest_api (api.cron-job.org) | OPT-OUT | not needed: the owner reads the console and creates the alarm there; avoids adding another credential |
| cron_job_org.save_responses | OPT-OUT | not needed: the E2E trace correlates by execution time; turning it on would change Phase 5's production dispatch job (runbook section 2) |
| github.actions_runs_read (gh run list, gh run view) | INTEGRATE | |
| github.workflow_dispatch (gh workflow run supabase_smoke.yml, optional) | INTEGRATE | |
| github.workflow_dispatch_return_run_details | OPT-OUT | not needed: Phase 5's dispatch body {"ref":"main"} stays unchanged; the trace accepts an explicit run id that must agree with the correlated run |
