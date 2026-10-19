# Phase 6: Exposure & E2E Verification - Research

**Researched:** 2026-10-19
**Domain:** Supabase Data API (PostgREST) exposure of a Postgres view under RLS; consumer examples; end-to-end and soak verification of a cron-job.org -> GitHub Actions -> Postgres pipeline
**Confidence:** HIGH on PostgREST/RLS/grant behavior and the example code (all exercised locally this session); MEDIUM on Supabase-platform specifics (read from official docs, not exercised against a real project, because no Supabase project exists yet); LOW on PSS/E's bundled Python/TLS (conflicting sources)

## User Constraints (from CONTEXT.md)

No CONTEXT.md exists for this phase (confirmed: `phases/06-exposure-e2e-verification/` was empty). The binding constraints come from REQUIREMENTS.md and are copied verbatim.

### Locked Decisions
From REQUIREMENTS.md "Decided architecture" (line 24-29):
- "**Read interface:** Supabase's built-in REST API (PostgREST), read-only for consumers via Row Level Security. No custom API server in this workstream (a FastAPI layer is out of scope; see below)."
- "**Trigger:** cron-job.org calling GitHub's `workflow_dispatch`, the same pattern as `.github/workflows/shadow_collect.yml` since commit 2ec2bfd. No GitHub `schedule:` trigger."
- "**Store:** hosted Postgres on Supabase."

From REQUIREMENTS.md "Owner decisions (fixed 2026-10-19)":
- "OD-1 | Live cadence | Phase 5 | **Hourly.** Actions minutes must be checked against the plan's quota alongside the 4/day shadow runs (SCHED-02)"
- "OD-4 | Freshness grace period for E2E-02 | Phase 6 | **30 min** past one cadence interval (a city's latest `valid_time` no older than 90 min at hourly cadence)"
- "OD-5 | Labelling of values based on provisional static ratings / assumed bearings | Phase 4 | **Labelled provisional** in the schema doc and per row (e.g. a `rating_basis` / `config_version` column)"

Scope guards given by the invoker: never read `.env`; never write to `data/shadow/predictions`; research only, no code changes.

### Claude's Discretion
- Soak-test tooling for E2E-02 (the invoker listed three options and asked for a trade-off and recommendation).
- Which Postgres schema the view lives in, the view's SQL form, and the exact RLS/GRANT layout.
- Where example files and verification scripts live in the repo.

### Deferred Ideas (OUT OF SCOPE)
From REQUIREMENTS.md "Out of Scope": custom FastAPI/Flask server; `frontend/` dashboard build; PSS/E-side ingestion and N-1 analysis; PSS/E results back into the database (F7); changes to `shadow_collect.yml`, the shadow logs or the frozen evaluation modules; re-evaluating the ML shadow candidates.

## Project Constraints (from CLAUDE.md)

No project-level `./CLAUDE.md` or `./.claude/CLAUDE.md` rules exist (`.claude/` holds only `jobs`, `scheduled_tasks.lock`, `settings.local.json`, `worktrees`; no `.agents/`). The only global directive is the graphify skill trigger (`/graphify`), which does not apply here. Cross-phase constraints from ROADMAP.md that DO apply: do not modify `shadow_collect.yml` or shadow logs before 2026-11-24; "Commit with explicit paths; ask before pushing anything that changes live CI"; anti-peeking (nothing scores shadow predictions).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | Consumer tables/views exposed via REST, read-only for anon under RLS; `latest_rating` view returns one current row per city | Sections "Exposing `latest_rating`", Pattern 1-2; verified: `security_invoker` view + table RLS + SELECT-only grants returns 4 rows to anon; anon writes are rejected |
| API-02 | Working documented examples: curl, supabase-js, Python stdlib urllib | "Code Examples": supabase-js 2.118.0 and Python 3.9.6 stdlib examples were run against an emulated PostgREST; curl forms verified |
| E2E-01 | cron-job.org trigger -> workflow run -> new rows -> REST response with matching values, 4 cities | "E2E trace method": `saveResponses` + `return_run_details` capture the Actions run id; `run_id` column in DB; compare REST vs SQL |
| E2E-02 | >=72 h soak: every city's latest `valid_time` <= cadence + grace at every probe; breaches explained | "Soak design": pg_cron freshness log (5-min) + exact peak-age query over `city_rating` + optional REST-path probe via `rpc/assert_fresh` (503 on stale) |
| E2E-03 | anon insert/update/delete rejected | "Write protection": verified HTTP 401 + `42501` for INSERT/PATCH/DELETE when anon has no write grants; verified silent zero-row 200 for PATCH/DELETE when grants exist without policies (so REVOKE is mandatory) |
</phase_requirements>

## Summary

Supabase's built-in PostgREST is sufficient and needs almost no code: the Phase 6 deliverable is one small SQL migration (view, grants, comments, an index, an optional `assert_fresh` RPC), a consumer doc with three tested examples, and verification tooling (an anon-write-rejection script, a trace script, a soak log). Everything that can fail silently was exercised this session against a local PostgreSQL 16.14 + PostgREST 16.4 stack configured like Supabase (roles `anon`/`authenticated`/`service_role`/`authenticator`). Three findings change what a naive plan would do: (1) an anon `UPDATE`/`DELETE` that is blocked only by RLS returns **HTTP 200 with zero rows changed**, not an error, so E2E-03 is only meaningful if the migration `REVOKE`s write privileges from `anon` (then PostgREST returns 401/`42501`); (2) Supabase **removed OpenAPI spec access for the anon key** (all existing projects from 8 April 2026), so "PostgREST OpenAPI as the interface doc" no longer works for consumers and a committed doc is the interface; (3) Supabase is changing default grants on `public` so new tables are not exposed unless explicitly granted (existing projects: 30 October 2026, which is 11 days from now), so the migration must grant `SELECT` to `anon` explicitly and never rely on defaults.

The soak should not depend on GitHub Actions minutes or the owner's laptop. Recommended: a `pg_cron` job inside Supabase writes a per-city freshness log every 5 minutes (free, always on, authoritative), plus an exact "peak age before each write" SQL over `city_rating` (`computed_at - lag(valid_time)`), which is independent of probe sampling. Layer on an optional cron-job.org GET to a tiny `rpc/assert_fresh` function that raises `PT503` when any city is stale or missing (verified locally: PostgREST returns HTTP 503), which turns cron-job.org's own failure notification into a freshness alarm and exercises the real REST path. cron-job.org keeps only the last 50 executions and 2 days of bodies, so it cannot be the 72 h record.

Hourly cadence is at the edge of the Actions free quota (see Pitfall 8), which is another reason to keep the probe off Actions.

**Primary recommendation:** Ship `latest_rating` as a `security_invoker = true` view over the RLS-protected `city_rating` table, expose `public`, `REVOKE ALL` from `anon` then `GRANT SELECT` only, document with a committed interface doc (not OpenAPI), and run the 72 h soak as a `pg_cron` freshness log plus the exact peak-age query, with causes attributed from the Phase 5 run log, `gh run list`, and cron-job.org history.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| "One current row per city" (`latest_rating`) | Database / Storage (view) | — | A view keeps the rule in one place for every consumer; no API code (custom server is out of scope) |
| Read-only enforcement for anon | Database / Storage (GRANT + RLS) | API gateway (key -> role mapping) | Privilege is decided by Postgres role; the gateway only maps the key to `anon`. Do not rely on client discipline |
| Writer credentials (service role / pooler) | API / Backend (GitHub Actions job) | Database (`bypassrls` role) | Secrets only in Actions secrets (DB-04); never reach a consumer |
| REST serving, filtering, ordering | API (Supabase PostgREST) | — | Built-in; consumers use query params |
| Interface documentation | Docs (repo) | — | OpenAPI via anon is no longer served, so the repo doc is the source of truth |
| Freshness measurement (soak) | Database / Storage (`pg_cron` + log table) | cron-job.org (REST-path probe) | Always on, no Actions minutes, same DB as the view |
| Cause attribution for breaches | Operator tooling (script/`gh`) | Database (Phase 5 run log, `run_id`) | Joins DB facts with Actions history and cron-job.org history |
| Consumer clients (React dashboard, PSS/E Python) | Browser / Client; Power Systems workstation | — | Consume only; publishable key is safe in client code |

## Standard Stack

### Core
| Library / Service | Version | Purpose | Why Standard |
|-------------------|---------|---------|--------------|
| Supabase Data API (PostgREST) | PostgREST 16.4 used for local verification (released 2026-09-24); Supabase's hosted version not observed | REST read interface | Decided architecture. `[VERIFIED: gh api repos/PostgREST/postgrest/releases/latest -> v16.4, 2026-09-24]` for the local build; hosted version `[ASSUMED]` to behave the same for the features used |
| PostgreSQL | views with `security_invoker` need >= 15; local test on 16.14 | Store + view + RLS | `[CITED: supabase.com/docs/guides/database/postgres/row-level-security]` "In Postgres 15 and above ... `security_invoker = true`" |
| `pg_cron` (Supabase extension) | seconds schedules need Postgres 15.1.1.61+ | Soak freshness log | `[CITED: supabase.com/docs/guides/cron/quickstart]` |
| `@supabase/supabase-js` | 2.118.0 (published 2026-10-15, `engines.node >=22`) | Frontend examples | Official client. `[VERIFIED: npm view @supabase/supabase-js version]`; legitimacy gate returned SUS only for "too-new" (see audit) |
| Python stdlib `urllib.request`, `json`, `re`, `datetime` | tested on CPython 3.9.6 | PSS/E example, E2E scripts | Project requirement: no third-party packages for PSS/E |
| `curl` | 8.7.1 here | Any-consumer example | Universal |
| `gh` CLI | present on this machine | Run lookup/correlation | Used by the repo already; supports `return_run_details` default from v2.87.0 `[CITED: github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| cron-job.org REST API (`api.cron-job.org`) | n/a | Pull job history for cause attribution; `saveResponses` for E2E-01 | Soak report and trace |
| `pg_net` (Supabase extension) | n/a | Optional: DB-side HTTP GET of the REST URL from `pg_cron` | Only if a REST-path check must live inside Supabase; adds complexity (responses kept 6 h) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `DISTINCT ON` view | window function (`row_number() over (partition by city order by valid_time desc)`) | Same plan cost (full scan); `DISTINCT ON` is shorter. A `LATERAL`-per-city form is O(4 index probes) (0.5 ms vs 14-110 ms at 210k rows, measured) but needs a hard-coded city list or a `city` dimension table. At ~35k rows/year (4 cities x 8760 h) `DISTINCT ON` is fine; add the descending index |
| `security_invoker` view | default (security-definer) view with no table grant to anon | Definer view bypasses RLS and is the exact pattern Supabase warns about; invoker keeps RLS authoritative and lets consumers also read history. Choose invoker |
| Public schema | custom `api` schema + "Exposed schemas" setting | Custom schema is cleaner (internal tables unexposed) but needs dashboard config + `Accept-Profile`/`db.schema` in every client example. For one table and one view in a project nobody else uses, `public` with explicit grants is simpler; revisit if more tables appear |
| `pg_cron` log | separate GitHub workflow probe | Actions probe at 15 min = 288 runs per 72 h and bills >= 1 min each; also dies with Actions incidents it is supposed to detect. Reject |
| `pg_cron` log | cron-job.org response logging only | Only last 50 executions, bodies 2 days, cannot assert content. Use only as a secondary REST-path signal |

**Installation:** nothing to install for the Python/curl paths. For the supabase-js example: `npm install @supabase/supabase-js@2` (Node >= 22 for 2.118; browsers need only native `fetch`) or the CDN form in Code Examples.

**Version verification:**
```
npm view @supabase/supabase-js version   -> 2.118.0   (time.modified 2026-10-15T12:57:18Z)
gh api repos/PostgREST/postgrest/releases/latest -> v16.4 (2026-09-24)
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `@supabase/supabase-js` | npm | many years (v2 line; release 2.118.0 is 3 days old) | ~19.9M/wk | github.com/supabase/supabase-js | SUS (reason: `too-new`, i.e. the latest release is 3 days old; no postinstall; not deprecated) | Flagged: `[WARNING: flagged as suspicious — verify before using.]` The flag reflects release recency, not package identity; the planner still must add a `checkpoint:human-verify` before any `npm install`, and the docs examples should pin the major (`@2`) as Supabase's own docs do. Examples were run with `--ignore-scripts` in an isolated scratch directory |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `@supabase/supabase-js` (see above). Package name came from the official Supabase install page `[CITED: supabase.com/docs/reference/javascript/installing]`.
No Python third-party packages are used (stdlib only), so there is nothing to audit on PyPI.

## Architecture Patterns

### System Architecture Diagram

```
 cron-job.org (hourly POST)                                   cron-job.org (optional GET, 5-10 min)
   |  POST .../actions/workflows/<dlr_live>.yml/dispatches          |  GET /rest/v1/rpc/assert_fresh   (apikey header)
   |  body {"ref":"main","return_run_details":true}                 |  -> 200 ok | 503 stale/missing  -> failure email
   v  (response saved by cron-job.org: workflow_run_id)             |
 GitHub Actions run (Phase 5)  --GITHUB_RUN_ID--> run_id            |
   |  service role / pooler secret (Actions secrets only)           |
   v                                                                v
 +------------------- Supabase Postgres (Phase 4 schema) --------------------+        +-----------------------+
 |  public.city_rating  (PK city,valid_time; RLS on; anon SELECT policy)     |        | Supabase Data API     |
 |        ^ upsert by writer (bypassrls)                                      | <------| PostgREST             |
 |  public.latest_rating  VIEW security_invoker=true (DISTINCT ON city)       |  SQL   | role from key:        |
 |  public.assert_fresh() RPC (raises PT503 when stale)                       |        |  publishable -> anon  |
 |  ops.freshness_log  <--- pg_cron every 5 min ---- ops.log_freshness()      |        +-----------+-----------+
 |  (ops schema NOT exposed; anon has no privilege)                           |                    |
 +----------------------------------------------------------------------------+                    | HTTPS + apikey
                                                                                                   v
          React dashboard (supabase-js, publishable key)      PSS/E Python (urllib, publishable key)      curl / any

 Verification tooling (operator machine or CI, not required to stay on):
   E2E-01 trace script: cron-job.org history(saveResponses) -> workflow_run_id -> gh run view -> SQL rows(run_id) -> REST rows -> diff
   E2E-03 script:       anon INSERT/PATCH/DELETE/upsert -> expect 401/403 + row checksum unchanged
   E2E-02 report:       ops.freshness_log + peak-age SQL + (gh run list, cron-job.org history, Phase 5 run log) -> breach table with causes
```

### Recommended Project Structure
Paths for migrations belong to Phase 4's decision (Supabase CLI convention is `supabase/migrations/`); Phase 6 only appends files there. `[ASSUMED]` that Phase 4 adopts that layout.
```
supabase/migrations/
└── <ts>_expose_latest_rating.sql     # view, grants, comments, index, assert_fresh RPC
supabase/migrations/
└── <ts>_soak_freshness_log.sql       # ops schema, log table+function, cron.schedule (removable after soak)
docs/integration/                      # location is a suggestion; DB-05 (Phase 4) decides the schema-doc home
├── rest-api.md                        # interface doc: endpoints, columns+units, status codes, examples
└── examples/
    ├── curl.sh
    ├── supabase_js.mjs
    └── read_ratings.py                # stdlib only
backend/                               # existing flat-module layout; tests collected from backend/tests (pytest.ini)
├── e2e_verify_readonly.py             # E2E-03 (stdlib; live)
├── e2e_trace.py                       # E2E-01 (stdlib + gh/curl)
└── e2e_soak_report.py                 # E2E-02 report generator
backend/tests/
└── e2e_verify_test.py                 # offline unit tests with fake HTTP (pytest.ini: python_files includes *_test.py)
```

### Pattern 1: `latest_rating` as an invoker view over an RLS table
**What:** The view applies the caller's privileges and RLS to the base table, so RLS stays the single source of truth for "who sees what".
**When to use:** Always for this phase; Supabase warns that default (definer) views bypass RLS.
**Evidence:** `[CITED: supabase.com/docs/guides/database/postgres/row-level-security]` — "Views bypass RLS by default because they are usually created with the `postgres` user." and "In Postgres 15 and above, make a view obey the RLS policies of its underlying tables ... when invoked by `anon` and `authenticated` by setting `security_invoker = true`." Exercised locally: anon `GET /latest_rating` returned 4 rows (HTTP 200) `[VERIFIED: local PostgREST 16.4 + PG 16.14, this session]`.
```sql
-- Source: pattern from Supabase RLS docs; behavior verified locally 2026-10-19
create view public.latest_rating with (security_invoker = true) as
  select distinct on (city) *            -- prefer an explicit column list in the real migration
  from public.city_rating
  order by city, valid_time desc;

create index if not exists city_rating_city_valid_desc on public.city_rating (city, valid_time desc);
```
Measured at 210k rows: without the descending index `Execution Time: 110.189 ms` (external merge sort); with it `14.681 ms`. At the project's real size (~35k rows/year) this is not a concern; add the index anyway (cheap). `[VERIFIED: local EXPLAIN ANALYZE]`

### Pattern 2: Read-only privilege layout (belt and braces: GRANT is the lock, RLS is the second lock)
```sql
-- Table (owned by Phase 4; shown here so the E2E-03 expectations are explicit)
alter table public.city_rating enable row level security;
revoke all on public.city_rating from anon, authenticated;               -- strip Supabase default grants
grant select on public.city_rating to anon, authenticated;
create policy city_rating_read on public.city_rating
  for select to anon, authenticated using (true);                         -- public data by design
-- no INSERT/UPDATE/DELETE policy for anon/authenticated; writer uses service_role/pooler (bypasses RLS)

-- View
revoke all on public.latest_rating from anon, authenticated;
grant select on public.latest_rating to anon, authenticated;
```
Why REVOKE first: current Supabase projects grant `select, insert, update, delete` on new `public` tables to `anon`, `authenticated`, `service_role` `[CITED: github.com/orgs/supabase/discussions/45329]`, and the page "securing-your-api" confirms it. If those grants stay, an anon `PATCH`/`DELETE` blocked only by RLS silently affects zero rows (see Pitfall 1).
Also: "A policy that reads `to anon using ( true )` grants every unauthenticated visitor read access" `[CITED: supabase.com RLS docs]`; acceptable here because the ratings are meant for the other teams, but it means **anyone with the publishable key (or who views the dashboard's JS) can read all history**. Record this as an explicit owner-acknowledged decision in the doc (see Open Question 3).

### Pattern 3: Exact freshness definition and measurement
At hourly cadence the latest row's age sawtooths from ~0 up to (60 min + write latency) and resets when the next row lands. A probe every N minutes samples that sawtooth; an exact check uses the writes themselves: at the moment a new row is written, the previous row's age was `computed_at(new) - valid_time(prev)`. If that is <= 90 min for every consecutive pair, no instant between rows exceeded 90 min. Add the trailing age of the newest row at soak end. (SQL in Code Examples; syntax and logic exercised locally with synthetic data.)

### Anti-Patterns to Avoid
- **Relying on RLS alone for write protection:** blocked `PATCH`/`DELETE` return 200 with `[]`/204 and no error. Revoke privileges.
- **Granting `anon` SELECT on the base table "just in case" while the view is definer:** defeats the point; use invoker.
- **Serving OpenAPI to consumers via `GET /rest/v1/`:** anon gets "Access to schema is forbidden"; commit the doc.
- **Putting the secret/service key into any example or the frontend:** secret keys return 401 from browsers and bypass RLS.
- **Using `datetime.fromisoformat()` on raw PostgREST timestamps in Python < 3.11** (Pitfall 3).
- **Using cron-job.org history as the soak record** (50 executions, bodies 2 days).
- **Counting a fallback row as "stale":** a fallback rating still has a fresh `valid_time`; freshness is about row arrival, status is separate.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| REST read API | Flask/FastAPI shim | Supabase PostgREST | Decided; out of scope |
| "Latest per city" | App-side max() logic in each client | `latest_rating` view | One definition for React and PSS/E |
| Write protection | Middleware that rejects verbs | GRANT/REVOKE + RLS | Enforced in Postgres for every path |
| Auth for read | Custom token scheme | Publishable key (`anon` role) | Safe to embed; `[CITED: supabase.com/docs/guides/api/api-keys]` "Safe to expose online: web page, mobile or desktop app, GitHub actions, CLIs, source code." |
| Scheduler for the soak probe | Self-hosted cron / laptop loop | `pg_cron` in the database | Always on, free |
| Alerting on staleness | Custom mailer | cron-job.org failure notification on `rpc/assert_fresh` returning 503 | `onFailure` notifications exist `[CITED: docs.cron-job.org/rest-api.html]` |
| HTTP status for "stale" | Parsing body in cron-job.org | PostgREST `RAISE SQLSTATE 'PT503'` | `[CITED: docs.postgrest.org/en/stable/references/errors.html]` "raise an exception of the `PTxyz` type"; verified: GET returns HTTP 503 |
| Pagination/limits | Hand-rolled paging | `limit`/`Range`/`Prefer: count=exact`; supabase-js `.limit()`/`.range()` | Default max rows is 1000 (Pitfall 6) |
| Timestamp parsing for PSS/E | Hand-written date math without handling fractions | Small `parse_ts()` helper (tested) or truncate fractions in the DB | Pitfall 3 |

**Key insight:** every protection this phase needs already exists as a Postgres or PostgREST primitive; the risk is in defaults (grants, view security mode, silent zero-row writes), not in missing features.

## Common Pitfalls

### Pitfall 1: RLS-only write blocking is silent for UPDATE/DELETE
**What goes wrong:** With `GRANT UPDATE, DELETE` still present and no write policy, `PATCH` and `DELETE` return `200` with `[]` (or `204`) and change nothing; `INSERT` returns `401` `42501 new row violates row-level security policy`. A naive E2E-03 asserting "non-2xx" would fail on PATCH/DELETE, or worse, be "fixed" by loosening the assertion.
**Evidence:** `[VERIFIED: local PostgREST 16.4, this session]` Scenario B output: INSERT -> `{"code":"42501",...,"message":"new row violates row-level security policy for table \"city_rating\""}` HTTP 401; PATCH -> `[]` HTTP 200; DELETE -> `[]` HTTP 200; table unchanged (`count 12, min(rating_amps) 1000`). Supabase docs agree: a filtered write "raises nothing, matches zero rows" `[CITED: supabase.com RLS docs]`.
**How to avoid:** `REVOKE INSERT, UPDATE, DELETE` (revoke all) from `anon` and `authenticated`. With no grant: all three return `401` `{"code":"42501","details":null,"hint":null,"message":"permission denied for table city_rating"}` `[VERIFIED: local]`. In E2E-03 assert both the status (401 or 403) AND that a before/after row count + checksum are identical; also run the check in a second mode with a temporary grant to prove the RLS layer independently (optional).
**Warning signs:** E2E-03 script sees any 2xx on a write.

### Pitfall 2: Default grants on `public` (platform change in flight)
**What goes wrong:** Until a project opts in, new `public` tables are reachable by `anon` with all four privileges. Supabase "is changing the platform default to revoke these automatic grants"; new projects from 2026-05-30, existing projects 2026-10-30 (existing tables keep their grants) `[CITED: github.com/orgs/supabase/discussions/45329]`. Behavior will differ by project creation date and could change under the migration mid-phase.
**How to avoid:** the migration states every grant explicitly (revoke then grant select) and also grants nothing on future objects (`alter default privileges ... revoke` is documented). Apply the same pattern to the `ops` schema (no anon grants, schema not exposed) and the RPC (`grant execute` only where intended; revoke from `public`).
**Warning signs:** `information_schema.role_table_grants` shows `anon` with INSERT/UPDATE/DELETE on any exposed object.

### Pitfall 3: Python < 3.11 cannot parse PostgREST timestamps reliably
**What goes wrong:** `datetime.fromisoformat()` on CPython 3.9.6 rejects `...:14.1+00:00`, `...:14.11297+00:00` and `...:14Z`; it accepts 0 or exactly 6 fractional digits. Postgres drops trailing zeros, so a `computed_at` with microseconds can arrive with 1-6 digits.
**Evidence:** `[VERIFIED: python3 3.9.6 run this session]` -> `2026-10-19T00:00:14.1+00:00 FAIL Invalid isoformat string`; `...11297+00:00 FAIL`; `...14Z FAIL`; `...00:00+00:00` and `.112967+00:00` OK.
**How to avoid:** (a) use the tested `parse_ts()` helper in the PSS/E example; (b) preferably Phase 4 stores `valid_time` hour-aligned and rounds `computed_at` (e.g. `date_trunc('second', now())`), so fractions are rare; (c) PostgREST emits the session time zone offset, Supabase's default is UTC `[ASSUMED]`, so always parse the offset, never assume Z.

### Pitfall 4: OpenAPI is not available to the anon key
**What goes wrong:** Plans that say "consumers read the OpenAPI at `/rest/v1/`" fail with "Access to schema is forbidden" / hint "Accessing the schema via the Data API is only allowed using a secret API key." `[CITED: supabase.com/changelog/42949-breaking-change-removing-access-to-openapi-spec-via-the-anon-key]` (new projects from 11 March 2026; all existing projects from 8 April 2026). Plain local PostgREST still serves it, including SQL `COMMENT` text as `description` `[VERIFIED: local]`, which can mislead local testing.
**How to avoid:** the repo interface doc (`rest-api.md`) is the contract. Put units in column NAMES (e.g. `rating_amps`) AND in `COMMENT ON` (still valuable for anyone using the secret key/Management API to dump the spec). The owner may snapshot the spec with the secret key into the repo as `openapi.json` for the Software team's codegen (optional).
**Related gotcha:** `COMMENT ON COLUMN` on the base table does NOT carry over to the view: in the local test the view column `rating_amps` had no `description`, while the same column on the table did `[VERIFIED: local]`. Comment the view's columns explicitly.

### Pitfall 5: Key naming and header discipline
**What goes wrong:** Examples copied from older blog posts use `anon` JWT plus `Authorization: Bearer`. New keys: publishable `sb_publishable_...` / secret `sb_secret_...`, "not JWTs"; "Send publishable and secret keys on the `apikey` header, not on `Authorization: Bearer`." `[CITED: supabase.com/docs/guides/api/api-keys]`. Supabase says it "is deprecating the `anon` and `service_role` keys by the end of 2026"; legacy keys stay valid until disabled.
**How to avoid:** all docs use the publishable key in the `apikey` header only. supabase-js handles headers itself (`createClient(url, publishableKey)` is the documented form `[CITED: supabase.com/docs/reference/javascript/initializing]`). Do not tell Power Systems to send Bearer. The writer's secret/service key must stay in Actions secrets; a secret key "doesn't work in a browser" (HTTP 401 when the User-Agent indicates a browser).
**Not verifiable locally:** my emulation used a JWT as the key, so the publishable-key path through the Supabase gateway was NOT exercised; Wave 0 of execution must run the examples once against the real project.

### Pitfall 6: Silent truncation at 1000 rows
**What goes wrong:** PostgREST on Supabase truncates results at the project "Max rows" (default 1000) without an error `[CITED: supabase.co/docs/library/get via search summary; MEDIUM]`. `latest_rating` is 4 rows, but history queries (PSS/E often wants a window) will silently cut.
**How to avoid:** examples that read history show `limit`, `order=valid_time.desc`, and a `valid_time=gte.` window; the doc states the 1000-row ceiling and shows `Prefer: count=exact` (`Content-Range: 0-3/4` verified locally) or `Range` paging.

### Pitfall 7: Schema-cache lag after DDL
**What goes wrong:** A new view/function returns `404 PGRST202` until PostgREST reloads its schema cache. Locally I had to run `NOTIFY pgrst, 'reload schema'` `[VERIFIED: local, PGRST202 then success]`. Supabase migrations normally trigger the reload `[ASSUMED]`, but the soak RPC added later via SQL editor may need `notify pgrst, 'reload schema';` appended to the migration (harmless).

### Pitfall 8: Actions quota and probes
**What goes wrong:** An hourly workflow of ~3-5 min is 2,160-3,600 Linux minutes/month before the soak probe or the shadow runs; the repository is private and the plan quota is "**unverified**" (shadow runbook line 297). This is a Phase 5 SCHED-02 problem, but a probe workflow in Phase 6 would worsen it and stop working exactly when quota is exhausted (a cause of stale data you would want to observe).
**How to avoid:** keep the probe in the database; flag the quota number to Phase 5 as the most likely cause of a failed soak.

### Pitfall 9: 90-minute budget vs real latency
**What goes wrong:** The 90-min bound = 60 + 30. The 30 minutes must absorb dispatch jitter, Actions queue time, the run (~5 min or more), and, if `valid_time` is the observation time rather than the hour start, provider observation lag. The shadow runbook records that GitHub's scheduler started runs 3-8 h late, and "timing under the external trigger has not been measured" (api-contract.md section 5). If `valid_time` is the *weather observation* timestamp (not the scheduled hour), age at probe time includes provider lag.
**How to avoid:** before starting the 72 h clock, run a 12-24 h dry soak and read the measured peak-age distribution; if the distribution's max is > ~75 min the soak will fail for structural reasons and Phase 4/5 must be fixed first (not OD-4, which is fixed). Define in Phase 4 that `valid_time` = the hour the rating is for, truncated to the hour, so the budget is analyzable. (Open Question 1.)

### Pitfall 10: "A failed city is missing, not stale-flagged"
**What goes wrong:** If one city's provider fails, that city has no row for the hour, so its `latest_rating` row simply ages; the other three stay fresh. A probe that only checks "4 rows returned" passes while a city is 3 h old.
**How to avoid:** check per-city age (the log does), and `assert_fresh` counts cities AND stale rows (raises if fewer than 4 or any stale).

## Code Examples

All examples below were executed this session against local PostgreSQL 16.14 + PostgREST 16.4 (with a small path-prefix proxy standing in for `/rest/v1`, and a JWT standing in for the key). Replace `<ref>` and the key for the real project. Output shown is from the local run.

### SQL: expose `latest_rating` and prove it
```sql
-- migration: <ts>_expose_latest_rating.sql   (assumes Phase 4's public.city_rating exists)
-- column names below are the Phase 4 ASSUMED names; align to the real schema.
create or replace view public.latest_rating with (security_invoker = true) as
  select distinct on (city) *
  from public.city_rating
  order by city, valid_time desc;

comment on view public.latest_rating is
  'Newest city_rating row per city (one row per city). Ratings are PROVISIONAL (OD-5): static ratings and line bearings are unconfirmed.';
-- repeat COMMENT ON COLUMN for every exposed column: units belong in the text (A = amperes per conductor, MW, UTC)

revoke all on public.latest_rating from anon, authenticated;
grant select on public.latest_rating to anon, authenticated;
create index if not exists city_rating_city_valid_desc on public.city_rating (city, valid_time desc);
notify pgrst, 'reload schema';
```

### curl (any consumer)
```bash
# Source: query syntax verified locally; headers per supabase.com/docs/guides/api/api-keys
export SUPABASE_URL="https://<ref>.supabase.co"
export SUPABASE_KEY="sb_publishable_..."           # publishable key, safe to share; never the secret key

# all four cities, current rating
curl -sS "$SUPABASE_URL/rest/v1/latest_rating?select=city,valid_time,rating_amps,rating_mw,status&order=city" \
  -H "apikey: $SUPABASE_KEY" -H "Accept: application/json"
# one city
curl -sS "$SUPABASE_URL/rest/v1/latest_rating?city=eq.AUSTIN&select=*" -H "apikey: $SUPABASE_KEY"
# last 24 hourly rows for one city
curl -sS "$SUPABASE_URL/rest/v1/city_rating?city=eq.AUSTIN&order=valid_time.desc&limit=24&select=valid_time,rating_amps" -H "apikey: $SUPABASE_KEY"
# exactly-one-row assertion (HTTP 406 PGRST116 if 0 or >1 rows)
curl -sS "$SUPABASE_URL/rest/v1/latest_rating?city=eq.AUSTIN" -H "apikey: $SUPABASE_KEY" -H "Accept: application/vnd.pgrst.object+json"
# count without body
curl -sSI "$SUPABASE_URL/rest/v1/latest_rating?select=city" -H "apikey: $SUPABASE_KEY" -H "Prefer: count=exact" | grep -i content-range   # Content-Range: 0-3/4
```
Local results: `?city=eq.AUSTIN&select=city,valid_time,rating_amps` -> `[{"city":"AUSTIN","valid_time":"2026-10-19T00:00:14.112967-05:00","rating_amps":1000}]`; `in.(AUSTIN,MIDLAND)` works; a missing city with the singular Accept returns `406 PGRST116 "Cannot coerce the result to a single JSON object"`; an unknown column returns `400 42703`. `[VERIFIED: local]`

### supabase-js (frontend)
```javascript
// Source: createClient form per supabase.com/docs/reference/javascript/initializing ("your-publishable-key");
// verified with @supabase/supabase-js 2.118.0 under Node 26 against the local emulation.
import { createClient } from '@supabase/supabase-js'
// Browser quick test without a bundler (jsDelivr's +esm endpoint; the docs' CDN form is the UMD tag
//   <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>  [CITED: supabase.com/docs/reference/javascript/installing]):
// import { createClient } from 'https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm'   // [ASSUMED] not run

const supabase = createClient('https://<ref>.supabase.co', 'sb_publishable_...')

const { data, error } = await supabase
  .from('latest_rating')
  .select('city,valid_time,rating_amps,rating_mw,status')
  .order('city')                                   // -> 4 rows
if (error) throw error

const one = await supabase.from('latest_rating').select('*').eq('city', 'AUSTIN').single()   // error if not exactly 1 row
const hist = await supabase.from('city_rating').select('valid_time,rating_amps')
  .eq('city', 'AUSTIN').order('valid_time', { ascending: false }).limit(24)
const { count } = await supabase.from('latest_rating').select('city', { count: 'exact', head: true })
```
Local results: `ALL null 4 {city:'AUSTIN',...}`, `ONE null AUSTIN 1000`, `HIST null 3`, `COUNT 200 4`. Writes through supabase-js: `INSERT 401 42501 permission denied...`, `UPDATE 401 42501`, `DELETE 401 42501` `[VERIFIED: local]`. Note supabase-js >= 2.110.0 requires Node >= 22 (Node 20 EOL 2026-04-30; use 2.109.0 on Node 20) `[CITED: raw.githubusercontent.com/supabase/supabase-js README]`; browsers only need native `fetch`.

### Python stdlib (PSS/E)
```python
"""Read the current DLR rating per city. Standard library only; tested on CPython 3.9.6."""
import json, re, urllib.error, urllib.parse, urllib.request
from datetime import datetime, timezone

BASE_URL = "https://<ref>.supabase.co"
API_KEY = "sb_publishable_..."      # publishable key; sent in the apikey header only

def parse_ts(s):
    """PostgREST timestamptz -> aware datetime. fromisoformat() on Python < 3.11 rejects 'Z' and
    fractions that are not exactly 6 digits."""
    s = s.replace("Z", "+00:00")
    s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s)
    return datetime.fromisoformat(s)

def get(path, **params):
    q = ("?" + urllib.parse.urlencode(params, safe=",.()")) if params else ""
    req = urllib.request.Request(BASE_URL + "/rest/v1/" + path + q, headers={
        "apikey": API_KEY, "Accept": "application/json", "User-Agent": "dlr-psse-client/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")))

rows = get("latest_rating", select="city,valid_time,rating_amps,rating_mw,status", order="city")
now = datetime.now(timezone.utc)
for r in rows:
    age = (now - parse_ts(r["valid_time"])).total_seconds() / 60
    print("%-15s %7.1f A %7.1f MW %-9s age %.0f min" % (r["city"], r["rating_amps"], r["rating_mw"], r["status"], age))
```
Local run: 4 lines (`AUSTIN 1000.0 A 600.0 MW ok age 4 min` ...) and a filtered `city=eq.AUSTIN` query. Python 3.9.6 here reports `LibreSSL 2.8.3, HAS_SNI True, HAS_TLSv1_3 False` and a plain HTTPS GET to `https://supabase.com` returned 200, so TLS 1.2 + SNI work on a 3.9 interpreter `[VERIFIED: this session]`; the Supabase **project** host could not be tested (no project; `abcdefghijklmnopqrst.supabase.co` does not resolve). `User-Agent` is set defensively because some CDN front ends reject `Python-urllib` `[ASSUMED]`.

### Writes must be rejected (E2E-03 matrix)
```bash
# Expect: HTTP 401 (or 403) + JSON code 42501 for each; then re-count rows to prove nothing changed.
curl -sS -o /dev/stderr -w "%{http_code}\n" -X POST   "$SUPABASE_URL/rest/v1/city_rating" -H "apikey: $SUPABASE_KEY" -H 'Content-Type: application/json' -d '{"city":"AUSTIN","valid_time":"2031-01-01T00:00:00Z","rating_amps":1,"status":"ok"}'
curl -sS -o /dev/stderr -w "%{http_code}\n" -X POST   "$SUPABASE_URL/rest/v1/city_rating?on_conflict=city,valid_time" -H "apikey: $SUPABASE_KEY" -H 'Content-Type: application/json' -H 'Prefer: resolution=merge-duplicates' -d '[{"city":"AUSTIN","valid_time":"2031-01-01T00:00:00Z","rating_amps":1,"status":"ok"}]'
curl -sS -o /dev/stderr -w "%{http_code}\n" -X PATCH  "$SUPABASE_URL/rest/v1/city_rating?city=eq.AUSTIN" -H "apikey: $SUPABASE_KEY" -H 'Content-Type: application/json' -d '{"rating_amps":1}'
curl -sS -o /dev/stderr -w "%{http_code}\n" -X DELETE "$SUPABASE_URL/rest/v1/city_rating?city=eq.AUSTIN" -H "apikey: $SUPABASE_KEY"
```
Local status map (no write grants, JWT role anon, and also no JWT at all): table INSERT/PATCH/DELETE -> `401 {"code":"42501",...,"message":"permission denied for table city_rating"}`. Writes to the `DISTINCT ON` view -> `500 {"code":"55000","details":"Views containing DISTINCT are not automatically updatable."...}` (rejected, but by "not updatable", so a 5xx is not an outage; the E2E-03 script must treat view writes as "any non-2xx" and must not alarm on it) `[VERIFIED: local]`. PostgREST maps `42501` to "if authenticated 403, else 401" `[CITED: docs.postgrest.org/en/stable/references/errors.html]`; the anon role stayed on 401 even with an anon JWT in my emulation, but accept both 401 and 403 on the real platform because the gateway may differ `[ASSUMED]`.

### Optional REST-path freshness alarm (RPC raising PT503)
```sql
create or replace function public.assert_fresh(max_age_minutes int default 90)
returns jsonb language plpgsql stable security invoker as $$
declare n_stale int; n_total int;
begin
  select count(*) filter (where valid_time < now() - make_interval(mins => max_age_minutes)), count(*)
    into n_stale, n_total from public.latest_rating;
  if n_total < 4 or n_stale > 0 then
    raise sqlstate 'PT503' using message = 'stale or missing city rating',
      detail = format('cities=%s stale=%s', n_total, n_stale);
  end if;
  return jsonb_build_object('ok', true, 'cities', n_total);
end $$;
revoke all on function public.assert_fresh(int) from public;
grant execute on function public.assert_fresh(int) to anon, authenticated;
notify pgrst, 'reload schema';
```
Verified locally: fresh -> `200 {"ok": true, "cities": 4}`; `max_age_minutes=0` -> `503 {"code":"PT503","details":"cities=4 stale=4","message":"stale or missing city rating"}` for both POST (JSON body) and plain GET `rpc/assert_fresh?max_age_minutes=0` (the form cron-job.org can send). Hard-coding `4` ties the function to the city count; use a constant or a small `city` list if cities are added. RLS does not apply to functions (the function runs invoker, so it sees only what anon sees), and EXECUTE must be granted deliberately `[CITED: supabase.com/docs/guides/api/securing-your-api]`.

### Soak: `pg_cron` freshness log (E2E-02 record)
```sql
create schema if not exists ops;
create table if not exists ops.freshness_log (
  id bigint generated always as identity primary key,
  probed_at timestamptz not null default now(),
  city text not null,
  latest_valid_time timestamptz,
  age_minutes numeric(8,1),
  max_age_minutes int not null,
  breach boolean not null
);
create or replace function ops.log_freshness(max_age_minutes int default 90) returns void language sql as $$
  insert into ops.freshness_log (city, latest_valid_time, age_minutes, max_age_minutes, breach)
  select c.city, l.valid_time,
         round(extract(epoch from (now() - l.valid_time)) / 60, 1),
         max_age_minutes,
         (l.valid_time is null or l.valid_time < now() - make_interval(mins => max_age_minutes))
  from (values ('AUSTIN'),('CORPUS_CHRISTI'),('MIDLAND'),('EL_PASO')) as c(city)
  left join public.latest_rating l on l.city = c.city;
$$;
revoke all on schema ops from public, anon, authenticated;
revoke all on all tables in schema ops from public, anon, authenticated;
-- needs pg_cron enabled (Dashboard > Integrations > Cron, or: create extension pg_cron):
select cron.schedule('soak-freshness', '*/5 * * * *', $$select ops.log_freshness(90)$$);
-- teardown after the soak: select cron.unschedule('soak-freshness');
```
The function and a missing-city / stale-city case were run locally (the missing/stale city produced `breach = t`, the rest `f`); `cron.schedule(name, '*/5 * * * *', sql)` and `cron.unschedule(name)` follow the Supabase quickstart `[CITED: supabase.com/docs/guides/cron/quickstart]`; `pg_cron` itself was NOT run locally (not installed). Supabase recommends "no more than 8 Jobs run concurrently" and each job "no more than 10 minutes" `[CITED: supabase.com/docs/guides/cron]`.

### Soak: exact peak age between writes
```sql
-- window = soak period; also include one row before the window start so the first gap is measured
with g as (
  select city, valid_time, computed_at,
         lag(valid_time) over (partition by city order by valid_time) as prev_valid_time
  from public.city_rating
  where valid_time >= :soak_start::timestamptz - interval '3 hours'
)
select city, valid_time, computed_at, prev_valid_time,
       round(extract(epoch from (computed_at - prev_valid_time)) / 60, 1) as peak_age_min_before_write,
       (computed_at - prev_valid_time) > interval '90 minutes' as breach
from g
where prev_valid_time is not null and valid_time >= :soak_start::timestamptz
order by breach desc, peak_age_min_before_write desc;
-- plus trailing age at soak end:  select city, now() - max(valid_time) from city_rating group by city;
```
Syntax and output shape verified locally on synthetic rows. It requires `computed_at` to be the true write time (not a copied observation time); a replayed upsert overwriting `computed_at` would hide a gap, so Phase 4 should keep a separate immutable `first_written_at`/insert time or never rewrite `computed_at` on conflict `[ASSUMED]` (Open Question 2).

### E2E-01 trace (cron-job.org -> run -> rows -> REST)
Steps (each is a command/query a script can run; this is the method, not run live because Phases 4-5 do not exist yet):
1. Before the trace, set the cron-job.org dispatch job's `saveResponses` to `true` and its body to `{"ref":"main","return_run_details":true}`. `saveResponses` is a job field ("Whether to save job response header/body or not") `[CITED: docs.cron-job.org/rest-api.html]`; `return_run_details` makes GitHub answer `200` with `workflow_run_id`, `run_url`, `html_url` instead of `204` `[CITED: github.blog changelog 2026-02-19; docs.github.com REST workflow dispatch]`. Stored bodies last "2 days" and the job shows the "last 50 executions" `[CITED: cron-job.org/en/faq/]`, so capture the trace in that window.
2. Fetch the execution: `GET https://api.cron-job.org/jobs/<jobId>/history` -> choose the item; `GET .../history/<identifier>` for `httpStatus`, `date`, `datePlanned`, `jitter`, `body` (-> `workflow_run_id`). The API needs an API key from the console (rate limit 5 req/s; 100 requests/day default) `[CITED: docs.cron-job.org/rest-api.html]`.
3. Confirm the run: `gh run view <workflow_run_id> --json conclusion,event,createdAt,headSha` (event must be `workflow_dispatch`).
4. DB rows: `select city, valid_time, rating_amps, status, run_id, computed_at from city_rating where run_id = '<workflow_run_id>' order by city;` expects 4 rows. This requires Phase 4/5 to write `run_id` = `$GITHUB_RUN_ID` as text (Open Question 2). If it writes something else, fall back to time-window correlation (`computed_at` between run start and end).
5. REST: `GET /rest/v1/latest_rating?select=*` and compare each row's value fields to step 4's rows (exact equality on numeric columns, timestamp equality after parsing). Do the compare immediately after the run finishes so a later run has not replaced `latest_rating`; if it has, query `city_rating?run_id=eq.<id>` instead (the base table is readable by anon by design).
Record the four-way table (cron-job.org execution id / Actions run id / SQL rows / REST rows) in the verification doc.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `anon` / `service_role` JWT keys, `Authorization: Bearer` | `sb_publishable_...` / `sb_secret_...`, `apikey` header only | Supabase deprecating legacy keys "by the end of 2026" | Examples must use the new names; keep a note for legacy-key holders |
| OpenAPI at `/rest/v1/` with the anon key | Secret key only; Management API endpoint (2026-03-23) | New projects 2026-03-11, existing 2026-04-08 | Cannot be the consumer interface doc |
| Default `select/insert/update/delete` grants on new `public` tables | Opt-in exposure; explicit grants required | New projects default 2026-05-30; existing projects 2026-10-30 | Migration must grant explicitly; verify after 10-30 |
| Views bypass RLS (definer) | `security_invoker = true` (Postgres 15+) | Postgres 15 | Use it for `latest_rating` |
| `workflow_dispatch` returns 204 and no run id | `return_run_details` -> 200 + `workflow_run_id` | 2026-02-19 | Exact E2E trace without polling heuristics |
| supabase-js on Node 18/20 | supabase-js >= 2.110 needs Node >= 22 | Node 20 EOL 2026-04-30 | Local example runner needs Node 22+; browsers unaffected |

**Deprecated/outdated:** `anon`-key OpenAPI; assuming grants by default; `datetime.fromisoformat` for arbitrary Postgres timestamps on Python < 3.11.

## Runtime State Inventory

Not applicable: this phase adds objects; it renames/refactors nothing. (No stored data, live service config, OS-registered state, secrets or build artifacts carry a renamed string.) One related note: when the soak ends, `cron.unschedule('soak-freshness')` is required cleanup (a `pg_cron` registration is runtime state).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Phase 4 uses a `public.city_rating` table with columns named like `city`, `valid_time`, `rating_amps`, `rating_mw`, `status`, `run_id`, `computed_at`, `rating_basis`, PK (`city`, `valid_time`) | All SQL, examples | Examples/SQL names must be aligned to the Phase 4 migration before execution; no logic change |
| A2 | Phase 4/5 write `run_id` = `$GITHUB_RUN_ID` and keep `computed_at` as the true insert time | E2E-01 step 4; peak-age SQL | Trace falls back to time correlation; peak-age query can under-report gaps |
| A3 | `valid_time` is the hour the rating is for (hour-aligned UTC), not a raw observation timestamp | Pitfall 9, soak budget | 90 min budget may be structurally unreachable; soak fails for non-bug reasons |
| A4 | Supabase default DB time zone is UTC, so timestamps come back as `+00:00` | Pitfall 3 | Parsing must still handle any offset (helper does) |
| A5 | Hosted PostgREST behaves like local 16.4 for: 401 vs 403 on 42501, `PT503` mapping, schema cache reload, `Prefer`/`Range` | Pitfall 1, 7, examples | E2E-03 must accept 401 or 403 (planned); other differences found at the first live run |
| A6 | A publishable key through the Supabase gateway maps to `anon` and works with `apikey` alone (documented) | Pitfall 5 | Examples fail until adjusted; Wave 0 runs them live |
| A7 | `https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm` works as an ESM import | supabase-js example | Fall back to the documented UMD script tag |
| A8 | `User-Agent` header is not required but harmless for Python urllib on Supabase | Python example | None (header is harmless) |
| A9 | PSS/E's bundled Python is >= 3.7 and its OpenSSL supports TLS 1.2 + SNI | Python example | Example fails on very old interpreters (2.7) |
| A10 | Supabase documents no Data API request-rate limit I could find; third-party figures (500/s free, 1000/s Pro) are unconfirmed | Rate limits | Dashboard polling cadence could hit a limit; keep clients at >= 30-60 s polling |
| A11 | Supabase migrations trigger a PostgREST schema reload automatically | Pitfall 7 | A `notify pgrst, 'reload schema';` line covers it either way |
| A12 | New Supabase projects run Postgres >= 15 (needed for `security_invoker`) | Pattern 1 | View creation errors immediately if not |
| A13 | The repository's Actions plan quota is unverified (private repo) | Pitfall 8 | Phase 5's problem, but it is the likeliest soak breach cause |

## Open Questions

1. **What exactly is `valid_time` in the Phase 4 table, and what is the realistic end-to-end latency?**
   - What we know: OD-4 fixes the grace at 30 min and "no older than 90 min at hourly cadence"; the shadow workflow's dispatch timing under cron-job.org is "not measured".
   - What's unclear: whether `valid_time` is hour-truncated run time or the provider's observation time (which lags).
   - Recommendation: Phase 4 defines `valid_time` as the hour-truncated UTC rating time; Phase 6 begins with a 12-24 h dry soak and reads the peak-age distribution before starting the 72 h clock.
2. **Does Phase 4/5 record `run_id` as the GitHub run id and keep `computed_at` immutable on re-upsert?** E2E-01 and the exact peak-age query depend on it. Ask the Phase 4 researcher/planner to make both explicit.
3. **Is a world-readable history acceptable?** Anyone with the publishable key (embedded in the React app) can read the whole `city_rating` table, not only `latest_rating`. If history should be restricted, make the table non-readable by anon and use a definer view (accepting that it bypasses RLS) or a limited view. Owner/PSS-E team decision; default recommended: readable (consumers need history and the data is not secret).
4. **PSS/E's Python and TLS.** Sources conflict (release notes: PSS/E 35 standardizes on Python 3.7; third-party blogs say 3.9; nothing found for 36). Ask Power Systems to run `import sys, ssl; print(sys.version, ssl.OPENSSL_VERSION)` in PSS/E's interpreter and run `read_ratings.py` once against the live project. `[CITED: scribd copy of PSS/E release notes, via search; LOW]`
5. **Supabase tier / project pausing and rate limits.** Not confirmed in official pages fetched. Check the plan (Free projects may pause on inactivity; hourly writes keep it active) before the soak.
6. **Is a snapshot `openapi.json` wanted** for Software-team codegen (generated by the owner with the secret key)? Optional; not required by API-02.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Supabase project (Phase 4) | Everything live | ✗ (not yet created) | — | Local PostgREST emulation was used for research only; live verification is blocked until Phase 4/5 exist |
| `curl` | Examples, E2E-03 | ✓ | 8.7.1 | — |
| Python 3 | PSS/E example, scripts | ✓ | 3.9.6 (LibreSSL 2.8.3, SNI yes, TLS1.3 no) | — |
| Node.js / npm | supabase-js example | ✓ | Node 26.9.0 / npm 11.19.1 | Browser CDN form |
| `gh` CLI | Run correlation | ✓ | present (used for PostgREST download) | REST via `curl` + token |
| `psql` | Running migrations/queries by hand | ✓ | 16 and 18 (Homebrew) | Supabase SQL editor |
| `pg_cron` / `pg_net` | Soak log | not testable locally | Supabase-provided | Run the freshness query by hand on a schedule from cron-job.org -> RPC (less complete) |
| cron-job.org API key | Trace + soak attribution | unknown (owner holds the account) | — | Read the console history manually (screenshots) |
| Docker | n/a | ✗ | — | Not needed (PostgREST binary + Homebrew Postgres were used) |

**Missing dependencies with no fallback:** a live Supabase project populated by Phases 4-5 (blocks E2E-01/02 and the live run of API-02 examples).
**Missing dependencies with fallback:** `pg_cron` locally (documented behavior used instead).

## Validation Architecture

`workflow.nyquist_validation` is not set in `.planning/config.json` (absent = enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (repo default; `.venv/bin/python -m pytest -q -p no:cacheprovider`) for offline unit tests; live checks are stdlib Python scripts/SQL run against the real project |
| Config file | `/Users/aphan/Senior_Design/pytest.ini` — `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` |
| Quick run command | `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/e2e_verify_test.py` |
| Full suite command | `.venv/bin/python -m pytest -q -p no:cacheprovider` |

Live verification needs `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` as environment variables (never commit; the invoker also forbids reading `.env`). The offline tests must run with no network and no keys (fake `urlopen`).

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | anon `GET latest_rating` returns exactly 4 rows, one per city, with the documented columns | live integration | `python backend/e2e_verify_readonly.py --check-read` (asserts len==4, set(city)==expected, required columns present) | ❌ Wave 0 |
| API-01 | `latest_rating` is `security_invoker` and anon has SELECT only | live SQL | `select reloptions from pg_class where relname='latest_rating'` expects `security_invoker=true`; `select privilege_type from information_schema.role_table_grants where grantee='anon'` expects only `SELECT` for `city_rating`, `latest_rating` | ❌ Wave 0 |
| API-01 | view logic returns newest row per city (SQL logic) | local/unit (pgTAP-style or psql) | psql script against a throwaway Postgres: seed 3 rows x 4 cities, assert max(valid_time) per city | ❌ Wave 0 |
| API-02 | each doc example runs as written and returns data | live smoke | `bash docs/integration/examples/curl.sh && node docs/integration/examples/supabase_js.mjs && python3 -I docs/integration/examples/read_ratings.py` (exit 0, 4 cities printed) | ❌ Wave 0 |
| API-02 | Python example uses only stdlib and parses fractional timestamps | unit | `pytest backend/tests/e2e_verify_test.py::test_read_ratings_stdlib_only` (AST import check) and `::test_parse_ts_variable_fractions` | ❌ Wave 0 |
| E2E-01 | trace joins cron-job.org execution -> run id -> rows -> REST with equal values for 4 cities | live script | `python backend/e2e_trace.py --job-id <id> --run-id <id>` exits 0 and writes the four-way table | ❌ Wave 0 |
| E2E-01 | comparison logic (REST vs DB rows) | unit | `pytest ...::test_trace_compare_detects_mismatch` | ❌ Wave 0 |
| E2E-02 | every probe within 90 min; breaches listed with causes | live SQL + script | `python backend/e2e_soak_report.py --since <ts> --until <ts>` exits non-zero if any unexplained breach; includes peak-age query | ❌ Wave 0 |
| E2E-02 | `assert_fresh` returns 200 when fresh, 503 when a city is missing/stale | live (+ local psql) | `curl -s -o /dev/null -w '%{http_code}' "$SUPABASE_URL/rest/v1/rpc/assert_fresh" -H "apikey: $KEY"` | ❌ Wave 0 |
| E2E-02 | soak report classifies causes (missing run, failed run, city failure, provider lag, quota) | unit | `pytest ...::test_cause_attribution` with fixtures | ❌ Wave 0 |
| E2E-03 | anon INSERT/UPSERT/PATCH/DELETE all rejected (401/403) and data unchanged | live | `python backend/e2e_verify_readonly.py --check-writes` (row count + checksum before/after) | ❌ Wave 0 |
| E2E-03 | silent zero-row guard: script fails if any write returns 2xx | unit | `pytest ...::test_any_2xx_write_is_failure` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/e2e_verify_test.py`
- **Per wave merge:** full suite (`.venv/bin/python -m pytest -q -p no:cacheprovider`) plus the live read-only/read checks once Supabase credentials are exported
- **Phase gate:** full suite green; live `--check-read`, `--check-writes`, example smoke, trace table recorded; 72 h soak report with zero unexplained breaches, before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/e2e_verify_test.py` — offline tests above (fake HTTP)
- [ ] `backend/e2e_verify_readonly.py`, `backend/e2e_trace.py`, `backend/e2e_soak_report.py`
- [ ] `docs/integration/examples/{curl.sh,supabase_js.mjs,read_ratings.py}`
- [ ] Migration SQL files and a throwaway-Postgres script for the view-logic check (psql available locally)
- [ ] Credentials via environment only; first live run of all examples against the real project (publishable-key path is unverified)
- [ ] 12-24 h dry soak before the 72 h clock (Pitfall 9)

## Security Domain

`security_enforcement` is not set to `false` in `.planning/config.json` (absent = enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (API key as the only credential) | Publishable key via `apikey` header; no user auth; secret key never in consumers |
| V3 Session Management | no | Stateless REST, no sessions |
| V4 Access Control | yes | Postgres GRANT/REVOKE + RLS; `anon` SELECT-only; writer uses service role/pooler (bypassrls) from Actions secrets; `ops` schema unexposed |
| V5 Input Validation | yes (limited) | Consumers only send query strings; PostgREST parameterizes; writer-side validation is Phase 4; RPC takes an int |
| V6 Cryptography | yes | HTTPS/TLS only; no custom crypto; key rotation procedure per Supabase docs (create new, replace, confirm, retire) |
| V8/V13 API & data protection | yes | `Cache`/rate: no documented Data API limit found; keep polling modest; data deliberately public to key holders |

### Known Threat Patterns for Supabase PostgREST + RLS

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Anon write via exposed table with default grants | Tampering | `REVOKE` write privileges; RLS with no write policies; E2E-03 asserts both status and unchanged data |
| View bypasses RLS (definer view) | Information disclosure | `security_invoker = true` |
| Secret/service key leaks to client or repo | Elevation of privilege | Secret only in Actions secrets; secret keys 401 from browsers; secret scan (Phase 4 criterion 4); rotate if exposed |
| Over-broad `using (true)` select policy | Information disclosure | Accept only for deliberately public data; record the decision (Open Question 3) |
| SECURITY DEFINER functions / RPC abuse | Elevation of privilege | `assert_fresh` is security invoker, read-only, EXECUTE granted explicitly; no other functions exposed |
| Schema disclosure via OpenAPI | Information disclosure | Supabase blocks the anon key from the spec endpoint (April 2026) |
| Scraping / abuse of public key (DoS) | Denial of service | Small payloads, `latest_rating` is 4 rows; `pgrst.db_pre_request` hook available for limits `[CITED: securing-your-api]`; consider if abuse appears |
| Soak/ops data exposed | Information disclosure | `ops` schema unexposed, all privileges revoked from `anon`/`authenticated`; verify anon cannot read `freshness_log` |
| Publishable key committed in docs | Information disclosure (benign) | Allowed by Supabase ("safe to expose ... source code"), but docs should use placeholders and the real key is shared out of band to avoid scraper traffic |

## Sources

### Primary (HIGH confidence)
- Local verification this session (PostgreSQL 16.14 + PostgREST 16.4, roles emulating Supabase; supabase-js 2.118.0; CPython 3.9.6): view + RLS behavior, anon write status codes, zero-row silent writes, `PT503` RPC, singular-object 406, OpenAPI descriptions, `DISTINCT ON` plans, freshness-log and peak-age SQL, Python timestamp parsing.
- https://supabase.com/docs/guides/database/postgres/row-level-security — views and RLS, `security_invoker`, service_role bypass, `to anon using (true)`, silent zero-row policies
- https://supabase.com/docs/guides/api/api-keys — publishable/secret keys, `apikey` header, browser restriction, rotation, legacy deprecation "by the end of 2026"
- https://supabase.com/docs/guides/api/securing-your-api — grants, RLS on exposed views, `pgrst.db_pre_request`
- https://github.com/orgs/supabase/discussions/45329 — default-grants change (2026-04-28 opt-in, 2026-05-30 new-project default, 2026-10-30 existing projects)
- https://supabase.com/changelog/42949-breaking-change-removing-access-to-openapi-spec-via-the-anon-key — OpenAPI via anon removed (2026-03-11 / 2026-04-08)
- https://docs.postgrest.org/en/stable/references/errors.html — 42501 -> 401/403 mapping, `PTxyz` custom status
- https://docs.postgrest.org/en/stable/references/api/openapi.html — OpenAPI on `/`, comments as descriptions
- https://docs.postgrest.org/en/stable/references/api/tables_views.html — filters, select, order
- https://supabase.com/docs/guides/cron and /cron/quickstart — pg_cron usage and limits
- https://docs.cron-job.org/rest-api.html and https://cron-job.org/en/faq/ — job history, `saveResponses`, notifications, last 50 executions, 2-day body retention, 30 s timeout, 64 KB read, 1-minute minimum
- https://github.blog/changelog/2026-02-19-workflow-dispatch-api-now-returns-run-ids and https://docs.github.com/en/rest/actions/workflows — `return_run_details`, `workflow_run_id`
- https://supabase.com/docs/reference/javascript/initializing, /installing, /select — client usage
- Repo files read this session: `.planning/workstreams/production-pipeline/{REQUIREMENTS,STATE,ROADMAP}.md`, `docs/frontend/specs/api-contract.md`, `docs/data-science/decisions/pss_e_handoff.md`, `docs/data-science/decisions/shadow_collection_runbook.md` (lines 295-316), `.github/workflows/shadow_collect.yml`, `pytest.ini`.

### Secondary (MEDIUM confidence)
- https://supabase.com/docs/guides/database/extensions/pg_net — response retention 6 h (page also contains an internal inconsistency about supported verbs)
- https://raw.githubusercontent.com/supabase/supabase-js/master/README.md — Node support policy (2.110.0 drops Node 20)
- Search summary for Supabase "Max rows" default 1000 (supabase.co/docs/library/get; GitHub discussion 3765)
- https://supabase.com/docs/guides/troubleshooting/database-api-42501-errors — 42501 appears as 401/403 in clients

### Tertiary (LOW confidence)
- PSS/E Python version (Scribd copy of release notes vs blogs); third-party Supabase rate-limit numbers; jsDelivr `+esm` import path (not run)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for PostgREST/RLS/grants and example code (run locally); MEDIUM for hosted-Supabase specifics (docs only)
- Architecture: HIGH for the view/grant/soak design; MEDIUM where it depends on Phase 4/5 columns and semantics (A1-A3)
- Pitfalls: HIGH for 1, 3, 4(view comments), 7 (verified); MEDIUM for 2, 5, 6, 8, 9 (documented or inferred)

**Research date:** 2026-10-19
**Valid until:** 2026-10-30 for grant/default behavior (platform change lands that day, re-check after); otherwise ~30 days. Supabase key/OpenAPI policies are moving through 2026; re-verify before executing.
