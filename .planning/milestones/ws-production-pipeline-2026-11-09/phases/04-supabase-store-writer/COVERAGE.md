# API Coverage — Supabase (Phase 4: Supabase Store & Writer)

> Full coverage by default. Opt-outs are explicit, reasoned decisions. Phase 4 uses Supabase as a
> hosted Postgres reached over the session pooler; consumer-facing surfaces belong to Phase 6.

| capability | decision | reason |
|---|---|---|
| postgres-session-pooler (Supavisor, port 5432) | INTEGRATE | |
| custom-postgres-role (dlr_writer through the pooler) | INTEGRATE | |
| row-level-security and explicit grants | INTEGRATE | |
| migrations via CLI (`supabase db push --db-url`, migration history) | INTEGRATE | |
| postgres-transaction-pooler (port 6543) | OPT-OUT | not needed: one short-lived writer per run, and transaction mode forbids prepared statements and session state (04-RESEARCH.md) |
| postgres-direct-connection (db.<ref>.supabase.co) | OPT-OUT | not usable: IPv6-only on the Free plan and GitHub-hosted runners are IPv4-only |
| data-api-rest (PostgREST) | OPT-OUT | explicitly out of scope for Phase 4: consumer REST exposure, anon grants and the latest_rating view are Phase 6 (API-01) |
| graphql (pg_graphql) | OPT-OUT | not needed: the decided read interface is REST (REQUIREMENTS.md "Decided architecture") |
| api-keys (publishable / secret) | OPT-OUT | not needed in Phase 4: the writer uses a database URL; the secret key would bypass RLS; the publishable key is Phase 6 |
| supabase-py / postgrest-py client | OPT-OUT | rejected in research: only write credential bypasses RLS, default 1000-row cap truncates history reads, packages flagged SUS |
| auth (GoTrue users) | OPT-OUT | not needed: no end users; access is by database role and, in Phase 6, the anon key |
| storage (buckets) | OPT-OUT | explicitly out of scope: OD-10 commits the model files to git (Phase 5) |
| realtime | OPT-OUT | not needed: consumers poll hourly data |
| edge-functions | OPT-OUT | explicitly out of scope: no custom API server in this workstream |
| pg_cron | OPT-OUT | not needed yet: Phase 6 uses it for the soak freshness log |
| management API / `supabase link` with access token | OPT-OUT | not needed: `db push --db-url` needs no access token or project link |
| backups / point-in-time recovery | OPT-OUT | not needed yet: Free plan daily backups only; revisit if the store must survive operator error beyond that |

DB-06 (row identity: `config_version`, `config_fingerprint`, `forecast_model_sha256`,
`anomaly_model_sha256`) needs no further Supabase capability: they are plain columns of
`public.city_rating` with CHECK constraints, written through the same session-pooler role.

## Requirement coverage (revised 2026-10-21)

Sequencing: the VAL-03 NO-GO does not gate any plan of this phase (owner re-sequencing
2026-10-21, ROADMAP Phase 4 "Depends on"); rows are written and loaded labelled provisional until
Phase 7's go (REVAL-01).

| requirement | plans |
|---|---|
| DB-01 | 04-01 (migration, tests), 04-05 (applied to the real project) |
| DB-02 | 04-01 (store), 04-02 (pipeline seam, run row) |
| DB-03 | 04-03 (loader, provisional labels), 04-06 (load and parity on the real project) |
| DB-04 | 04-01 (hygiene), 04-03 (smoke, secret scan, workflow), 04-05, 04-06 (live checks) |
| DB-05 | 04-04 (consumer contract and pointers) |
| DB-06 | 04-01 (columns, per-city fingerprint, model hashes, drift guard), 04-02 (proven through the orchestrator), 04-03 (Phase 3 identity for backfill rows), 04-04 (consumer meaning), 04-06 (backfill identity checked against the manifest) |
