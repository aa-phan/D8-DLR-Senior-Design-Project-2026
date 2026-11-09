# Phase 6: Exposure & E2E Verification - Research

**Researched:** 2026-10-19; **refreshed 2026-10-25** (CONTEXT.md decisions D-01..D-15 of 2026-10-25, Phase 4 identity columns, Phase 5 live since 2026-10-25T00:05Z, public repository)
**Domain:** Supabase Data API (PostgREST) exposure of a Postgres view under RLS; consumer examples; end-to-end and soak verification of a cron-job.org -> GitHub Actions -> Postgres pipeline
**Confidence:** HIGH on PostgREST/RLS/grant behavior, the view SQL and the example code (exercised locally in the 2026-10-19 and 2026-10-25 sessions); MEDIUM on Supabase-platform and cron-job.org specifics (official docs, not exercised against a real project or account); LOW on PSS/E's bundled Python/TLS (conflicting sources)

<user_constraints>
## User Constraints (from CONTEXT.md)

Copied verbatim from `06-CONTEXT.md` (gathered 2026-10-25). The REQUIREMENTS.md constraints that still bind follow after it.

### Locked Decisions

#### What changed since the 2026-10-19 plans (replan inputs)
- Phase 5 is live: hourly cron-job.org dispatch of `dlr_live.yml` at minute 05 since run
  40145300072 (2026-10-25T00:05:05Z). 05-08 (24 h evidence and owner sign-off) is still open.
- The repository is public (05-06). Actions minutes are no longer the constraint; anything
  committed is world-readable.
- Phase 4 shipped DB-06 identity columns (`config_fingerprint`, `forecast_model_sha256`,
  `anomaly_model_sha256`) and `solar_source` (B6). The 06-01 27-column list omits them.
- AUSTIN publishes its static fallback (1825 A) in about 72% of hours (open, accepted issue in
  STATE.md, waits on Phase 7's conductor data).
- Phase 7 may push new conductor configs or model artifacts around 2026-11-01, possibly inside the
  soak window.

#### latest_rating contract
- **D-01:** The view publishes the planned 27 columns (06-01 LATEST_COLUMNS, same order) plus
  `config_fingerprint`, `forecast_model_sha256`, `anomaly_model_sha256` and `solar_source`, so
  consumers can see a conductor or model change through the view, as DB-06 requires. Pure
  diagnostics (`probe_trail`, `candidates_probed`, `history_rows`, `usable_history_rows`,
  per-field weather values, `first_written_at`, `schema_version`, `run_attempt`) stay readable in
  `city_rating` only. — **Reversibility:** one-way — the column names become the published contract
  for the React dashboard and PSS/E; renaming or dropping one needs a coordinated change with both
  teams (adding later is cheap).
- **D-02:** The view adds two computed columns: `age_minutes` (minutes from `valid_time` to
  `now()`) and `is_stale` (true when strictly older than 90 min, per OD-4; exactly 90 is fresh,
  the same rule as `assert_fresh` and the soak log). This covers OD-9: a city that fails keeps
  showing its last good row, and these columns tell consumers it is old. `rpc/assert_fresh` stays
  as planned for the alarm. — **Reversibility:** one-way — part of the published column contract.
- **D-03:** The view adds an `is_provisional` boolean derived from `rating_basis` (live rows start
  with `PROVISIONAL (OD-5)`, see `docs/data-science/schema/city_rating_v1.md`), so consumers
  branch on a boolean and Phase 7's GO (REVAL-01) turns it false for new rows without a contract
  change. — **Reversibility:** one-way — part of the published column contract.
- **D-04:** `latest_rating` returns the newest row per city by `valid_time`, fallback rows
  included. The fallback is the value the system published and is safe by the owner's rule;
  consumers see `status = 'fallback'` and `fallback_gates` on it. Never skip to an older computed
  row.
- **D-05:** The column-comment rules, units, security_invoker view, revoke sweep plus SELECT-only
  grants and the LATEST_COLUMNS drift-guard test from 06-01 stay. The column list grows per
  D-01..D-03, and the docs table and LATEST_COLUMNS follow it.

#### Soak timing and sequencing
- **D-06:** Offline build starts now, before 05-08 closes: the migration, local-Postgres tests,
  REST client, contract doc, examples and soak tooling (06-01, 06-03, 06-04 shapes). Anything that
  touches the live project (applying the migration, scheduling pg_cron, creating the alarm,
  starting the soak) waits for Phase 5's 05-08 sign-off.
- **D-07:** The 12-24 h dry soak (06-RESEARCH Pitfall 9) is computed from live `city_rating` rows
  already written since 2026-10-25T00:05Z (write lag and peak age from `computed_at` vs
  `valid_time`), alongside Phase 5's 24 h window check, instead of waiting a fresh 12-24 h after
  monitoring is switched on. The owner reviews that report, then the 72 h clock starts. The rule
  that the 72 h window starts only after the owner's review, and never overlaps the dry-soak data,
  stays. The 5-minute probe log starts when monitoring is switched on; the planner decides whether
  a short probe smoke check (a few probes) is needed before the clock starts.
- **D-08:** Phase 7 deploys may go live during the 72 h soak. Each deploy (time, commit, what
  changed: config, model or workflow) is recorded in the soak annotations. A breach a deploy causes
  still counts and is explained like any other; the soak is not paused or restarted.
- **D-09:** The soak starts as soon as the dry-soak review allows; it is not stretched past
  2026-10-30. A separate permission re-check (read, hidden tables, write rejection,
  `verify_exposure.sql`) runs after Supabase's 2026-10-30 default-grant change. Phase 4's carried
  item T-04-22 (re-run the `consumers_cannot_write` smoke after 10-30) is folded into this check.

#### Public repo and examples
- **D-10:** Neither the Supabase project URL nor the publishable key is committed anywhere: not
  in docs, examples or evidence files. The docs and all three examples read `SUPABASE_URL` and
  `SUPABASE_PUBLISHABLE_KEY` from the environment; the owner gives the values to the two teams
  directly. The existing redaction rules (tools never print the URL or key) stay. The repo
  secret-scan should also catch the project URL/reference.
- **D-11:** The PSS/E stdlib-`urllib` example supports Python 3.7+ (not 2.7). It includes the
  timestamp-parsing helper (Python < 3.11 cannot parse PostgREST timestamps with `fromisoformat`)
  and avoids syntax newer than 3.7. It is tested on the oldest Python 3 available locally plus the
  repo's 3.12. The interpreter question to Power Systems is still sent; a "2.7" answer becomes a
  follow-up, not a blocker.
- **D-12:** Each example (curl, supabase-js, Python urllib) shows (1) the current row per city
  from `latest_rating` and (2) one city's rows over a date range from `city_rating`, paging past
  the 1000-row cap. An `assert_fresh` example is not required in the examples; the contract doc
  still documents the RPC and its 200/503 behaviour.

#### Monitoring after the soak
- **D-13:** After the 72 h soak passes, the cron-job.org freshness alarm (GET `rpc/assert_fresh`)
  stays on permanently. The 5-minute pg_cron log job is unscheduled at soak end (as 06-07 plans).
  The full soak record is already exported to the repo. The runbook records that the alarm is
  permanent and how to pause it.
- **D-14:** Alarm rule: cron-job.org calls the check every 15 min, emails after 2 consecutive
  failures, and sends a recovery email. During the soak the planner may run the alarm at this same
  rule; the pg_cron log, not the alarm, is the soak's record.
- **D-15:** Alarm emails go to the owner's cron-job.org account only. The runbook says what to
  do when it fires (check `pipeline_run`, the Actions history and `latest_rating.is_stale`).

### Claude's Discretion
- Exact SQL expression for `is_provisional` and `age_minutes` (type, rounding), as long as the
  90-min rule matches `assert_fresh` exactly.
- Where the three new derived columns sit in the column order (append after the 27 + 4 is the
  default).
- How the dry-soak report from existing rows is produced (a mode of `e2e_soak_report.py` or a
  one-off SQL export), and whether a short probe smoke check is needed before the 72 h clock.
- How deploy annotations are captured (manual entries in `annotations.json` or derived from
  `config_fingerprint`/model-hash changes in `city_rating`).

### Deferred Ideas (OUT OF SCOPE)
- Python 2.7 support for the PSS/E example, only if Power Systems report a 2.7 interpreter.
- A team or shared alert address for the freshness alarm (owner-only for now).
- A permanent freshness history (5-minute log with a retention rule), not kept now.

### Still-binding constraints from REQUIREMENTS.md
From "Decided architecture": "**Read interface:** Supabase's built-in REST API (PostgREST), read-only for consumers via Row Level Security. No custom API server in this workstream"; trigger is cron-job.org calling `workflow_dispatch` (no GitHub `schedule:`); store is hosted Postgres on Supabase. From "Owner decisions": OD-1 hourly cadence; OD-4 "**30 min** past one cadence interval (a city's latest `valid_time` no older than 90 min at hourly cadence)"; OD-5 values labelled provisional; OD-6 public history with explicit revokes; OD-9 a failed city writes no row (run log only). Out of scope: custom FastAPI/Flask server; `frontend/` dashboard build; PSS/E-side ingestion; changes to `shadow_collect.yml`, shadow logs or frozen evaluation modules.

**Scope guards for this research:** never contact the live Supabase project, never read `.env`, never push.
</user_constraints>

## Project Constraints (from CLAUDE.md)

No `./CLAUDE.md` exists in the repository (confirmed by the invoker for this refresh); the only global directive (`~/.claude-edu/CLAUDE.md`) is the graphify skill trigger, which does not apply. Established project patterns that act as constraints, all taken from CONTEXT.md `<code_context>` and ROADMAP.md:
- Migrations are additive and sha256-pinned; an applied migration is never edited. Phase 6 adds new files that sort after every Phase 4/5 migration (the latest today is `20261023000000_...`).
- Every live action is an owner checkpoint (apply a migration, schedule pg_cron, create the alarm, start the soak). The executor builds and tests offline and never applies, reads `.env` or pushes without approval.
- Tools never print a URL, host, project reference or credential; evidence JSON carries none.
- Commit with explicit paths; ask before pushing anything that changes live CI; never modify `shadow_collect.yml`, the shadow logs or `data/shadow/predictions`; never modify the cron-job.org dispatch or shadow jobs.
- `load_dotenv()` only under `__main__`, so tests never read the owner's `.env`.
- Owner preference (memory): plain-English explanations of what each verification proves, no unexplained jargon.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| API-01 | Consumer tables/views exposed via REST, read-only for anon under RLS; `latest_rating` returns one current row per city | "Pattern 1" (34-column invoker view), "Pattern 2" (revoke/grant layout), Pitfalls 1, 2, 11, 12; the draft view SQL was run on the real Phase 4 migrations locally (anon reads one row per city, `reloptions = {security_invoker=true}`) |
| API-02 | Working documented examples: curl, supabase-js, Python stdlib urllib | "Code Examples": each shows `latest_rating` per city and one city's range with paging past 1000 rows; env-only credentials (D-10); the Python example ran on CPython 3.9.6, 3.10.21 and 3.12.13 against an in-process fake PostgREST |
| E2E-01 | cron-job.org trigger -> workflow run -> rows -> REST response with matching values, 4 cities | "E2E trace method" (unchanged; compare stored columns only, not the time-varying `age_minutes`/`is_stale`) |
| E2E-02 | >=72 h soak: every city's latest `valid_time` <= cadence + grace at every probe; breaches explained | "Soak design": dry soak from existing rows, exact write-based peak age (now from `first_written_at`), 5-min `pg_cron` log, deploy annotations, alarm |
| E2E-03 | anon insert/update/delete rejected | "Write protection" + Pitfall 1 (REVOKE is mandatory; RLS alone returns 200 with zero rows) + the post-2026-10-30 re-check (Pitfall 17) |
</phase_requirements>

## Summary

Supabase's built-in PostgREST is still sufficient and needs almost no code: the Phase 6 deliverable is one small SQL migration (a 34-column invoker view, grants, comments, an index, `assert_fresh`), a consumer doc with three tested examples, and verification tooling (anon-write-rejection check, trace script, soak log and report). The 2026-10-19 findings stand: an anon `UPDATE`/`DELETE` blocked only by RLS returns HTTP 200 with zero rows, so the migration must `REVOKE` write privileges; Supabase removed OpenAPI access for the anon key, so a committed doc is the interface; and Supabase's default-grant change reaches existing projects on 2026-10-30, so every grant stays explicit.

**What this refresh changed (read first):**
1. **D-03's premise is wrong for live rows.** `config.RATING_BASIS` (what the live runner writes) starts with "Per-conductor amperes from the IEEE 738 thermal model..." and does **not** start with `PROVISIONAL (OD-5)`; only the one-time backfill label does (`supabase_load_backfill.backfill_rating_basis`). A view test of `rating_basis` for the prefix `PROVISIONAL (OD-5)` returns `false` on every live row, so `is_provisional` would silently tell consumers that provisional values are final. Recommended fix inside the owner's discretion (D-03 intent unchanged): derive `is_provisional` from the word "provisional" in `rating_basis` or `config_version`, and add a drift-guard test that feeds the real `config.RATING_BASIS`, `config.RATING_CONFIG_VERSION` and a real backfill label through the view. Surface this to the owner: CONTEXT.md D-03 names the wrong prefix.
2. **`age_minutes` should be `ceil(...)::integer`.** With rounding down, a row 90 min 59 s old shows `age_minutes = 90` but `is_stale = true`; with `ceil`, `age_minutes > 90` is exactly equivalent to `is_stale` (checked on microsecond boundaries, local PG 16.14). `is_stale` itself must be a direct timestamp comparison, never derived from a rounded value.
3. **The soak's exact peak age must use `first_written_at`, not `computed_at`.** The Phase 4 table now has an immutable `first_written_at`; `computed_at` is rewritten by an OD-7 same-hour retry, which would inflate a gap. (The 2026-10-19 text assumed `computed_at` was the insert time; D-07's "from `computed_at` vs `valid_time`" should be read as the first write.)
4. **The dry soak needs a new SQL read**, not just `dlr_live_window_check.py`: that module's queries select only `city, valid_time, run_id` and the `pipeline_run` columns, so they carry no write times. Reuse `evaluate_window` for slot verdicts and add one query for write lag and peak age.
5. **The cron-job.org alarm has a trap:** cron-job.org disables a job that "subsequently fails more than 25 times" (FAQ). At a 15-minute interval a stale data outage of about 6.5 h disables the permanent alarm itself, and no recovery email follows. Turn on the "job disabled" email, and make "pause the pipeline" also mean "pause the alarm" in the runbook.
6. **T-04-22's date is "on or after 2026-10-31"** (STATE.md), not 10-30. Supabase's rollout is gradual; the re-check should run on or after 2026-10-31 and cover read, hidden tables, write rejection, `verify_exposure.sql` and the existing `consumers_cannot_write` smoke.
7. **Public repo:** nothing in the tracked tree or git history carries a project reference today (checked). The scan extension is a pattern for 20-character ref-shaped `*.supabase.co` hosts plus `sb_publishable_` keys, plus an owner-local env-gated test. `supabase_store.redact` does not know the REST URL or the publishable key; the new REST tool needs its own redaction.
8. **Timeline fits.** Earliest sign-off 2026-10-26T01:05Z (25 h after the window start) leaves room for a 72 h soak that ends before 2026-10-30 only if the clock starts by 2026-10-27T00:00Z.

**Primary recommendation:** Ship `latest_rating` as a `security_invoker = true` view over the RLS-protected `city_rating` table with the 34-column contract (explicit list, three computed columns appended), `ceil` integer age, a direct-comparison `is_stale`, and an `is_provisional` that matches the live label; `REVOKE ALL` from anon then `GRANT SELECT` only; document with a committed doc whose examples read `SUPABASE_URL`/`SUPABASE_PUBLISHABLE_KEY` from the environment; run the dry soak from existing rows (write lag and peak age from `first_written_at`), then the 72 h soak as a `pg_cron` freshness log plus the exact write-based query, with deploys derived from `pipeline_version`/identity-column changes and supplemented by manual annotations.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| "One current row per city" (`latest_rating`) | Database / Storage (view) | — | A view keeps the rule in one place for every consumer; no API code (custom server is out of scope) |
| Staleness flag (`age_minutes`, `is_stale`) and provisional flag (`is_provisional`) | Database / Storage (view expressions) | — | One definition shared by the dashboard, PSS/E, `assert_fresh` and the soak log; consumers branch on a boolean instead of re-implementing the 90-minute rule |
| Read-only enforcement for anon | Database / Storage (GRANT + RLS) | API gateway (key -> role mapping) | Privilege is decided by Postgres role; the gateway only maps the key to `anon`. Do not rely on client discipline |
| Writer credentials (pooler secret) | API / Backend (GitHub Actions job) | Database (`dlr_writer` role) | Secrets only in Actions secrets (DB-04); never reach a consumer |
| REST serving, filtering, ordering, paging | API (Supabase PostgREST) | — | Built-in; consumers use query params; 1000-row cap |
| Interface documentation | Docs (repo) | — | OpenAPI via anon is no longer served, so the repo doc is the source of truth; credentials are handed over out of band (D-10) |
| Freshness measurement (soak) | Database / Storage (`pg_cron` + `ops` log table) | cron-job.org (REST-path alarm) | Always on, no Actions minutes, same DB as the view |
| Freshness alarm (permanent) | cron-job.org (GET `rpc/assert_fresh`, email) | Database (`assert_fresh` raises PT503) | The existing external scheduler; independent of GitHub Actions and of the DB-internal `pg_cron` |
| Dry soak and write-lag statistics | Operator tooling (SQL via `supabase_store.connect()` + `gh`) | Database (`city_rating.first_written_at`) | Runs before the migration is applied (the table is still private), so it needs the owner's writer connection, read-only |
| Deploy annotations | Operator tooling (SQL change points + `git diff --name-only`) | Manual `annotations.json` | The data already records `pipeline_version` and the identity columns per row |
| Cause attribution for breaches | Operator tooling (script/`gh`) | Database (`pipeline_run`, `run_id`) | Joins DB facts with Actions history and the cron-job.org console |
| Consumer clients (React dashboard, PSS/E Python) | Browser / Client; Power Systems workstation | — | Consume only; publishable key is safe in client code but is not committed |

## Standard Stack

### Core
| Library / Service | Version | Purpose | Why Standard |
|-------------------|---------|---------|--------------|
| Supabase Data API (PostgREST) | PostgREST 16.4 used for local verification on 2026-10-19 (released 2026-09-24); hosted version not observed | REST read interface | Decided architecture. `[VERIFIED: gh api repos/PostgREST/postgrest/releases/latest -> v16.4, 2026-09-24]` for the local build; hosted version `[ASSUMED]` to behave the same for the features used. Not re-run this session (no local PostgREST binary remains); this session re-verified only the SQL side on PostgreSQL 16.14 |
| PostgreSQL | views with `security_invoker` need >= 15; local 16.14 | Store + view + RLS | `[CITED: supabase.com/docs/guides/database/postgres/row-level-security]` "In Postgres 15 and above ... `security_invoker = true`"; the migration check `server_version_ge_15` already exists in `backend/supabase_smoke.py` |
| `pg_cron` (Supabase extension) | seconds schedules need Postgres 15.1.1.61+ | Soak freshness log | `[CITED: supabase.com/docs/guides/cron/quickstart]` |
| `@supabase/supabase-js` | 2.118.0 (npm `time.modified` 2026-10-22; last version published 2026-10-15; `engines.node >=22.0.0`) | Frontend example | Official client. `[VERIFIED: npm view @supabase/supabase-js version engines.node, 2026-10-25]`; legitimacy gate still SUS only for `too-new` (see audit) |
| Python stdlib `urllib.request`, `json`, `re`, `datetime`, `os` | CPython 3.7+ target; run on 3.9.6, 3.10.21, 3.12.13 | PSS/E example, E2E scripts | Project requirement: no third-party packages for PSS/E (D-11) |
| `curl` | 8.7.1 here | Any-consumer example | Universal |
| `gh` CLI | present | Run lookup/correlation, deploy classification | Used by the repo already (`dlr_live_window_check.fetch_runs`) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| cron-job.org (console; REST API not used) | n/a | Freshness alarm job; execution history in the console | Alarm and trace; COVERAGE.md opts out of its REST API and `saveResponses` so the dispatch job stays untouched |
| `pg_net` (Supabase extension) | n/a | Optional DB-side HTTP GET | Not needed; the alarm lives in cron-job.org |
| `psycopg` via `backend/supabase_store.connect()` | already pinned | Read-only SQL for the dry soak, soak export and independent trace read | Owner-run, `SUPABASE_DB_URL`, never printed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `DISTINCT ON` view | window function (`row_number()`) | Same plan cost; `DISTINCT ON` is shorter. At ~35k rows/year it is fine with the descending index |
| `security_invoker` view | default (definer) view | Definer bypasses RLS (the pattern Supabase warns about). Choose invoker |
| Public schema | custom `api` schema + "Exposed schemas" setting | Cleaner, but needs dashboard config and `Accept-Profile` in every client. For one table and one view, `public` with explicit grants is simpler |
| `is_provisional` from the word "provisional" | a stored boolean column on `city_rating` | A column is the cleanest signal but needs a Phase 4 table change and a writer change; the text rule needs neither and flips with Phase 7's label change. Keep the text rule and the drift-guard test |
| Derive deploys from data | manual `annotations.json` only | Manual alone forgets deploys; derived alone cannot see non-data events (cron-job.org edits, GitHub incidents). Use both |
| `pg_cron` log | separate GitHub workflow probe | Dies with the Actions incidents it should detect. Reject |

**Installation:** nothing to install for the Python/curl paths. For the supabase-js example: `npm install @supabase/supabase-js@2` (Node >= 22; browsers need only native `fetch`).

**Version verification (2026-10-25):**
```
npm view @supabase/supabase-js version engines.node time.modified -> 2.118.0, >=22.0.0, 2026-10-22T12:03:47Z
gsd package-legitimacy check --ecosystem npm @supabase/supabase-js -> SUS (too-new); publishedAt 2026-10-15; 21,473,502 weekly downloads; repo github.com/supabase/supabase-js; postinstall null
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `@supabase/supabase-js` | npm | many years (v2 line); latest release 2.118.0 is 10 days old | ~21.5M/wk | github.com/supabase/supabase-js | SUS (reason: `too-new`; no postinstall; not deprecated) | Flagged: `[WARNING: flagged as suspicious — verify before using.]` The flag reflects release recency, not package identity (name taken from Supabase's official install page `[CITED: supabase.com/docs/reference/javascript/installing]`). The planner still adds a `checkpoint:human-verify` before any `npm install`; docs pin the major (`@2`); run installs with `--ignore-scripts` in an isolated directory |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** `@supabase/supabase-js` (see above).
No Python third-party packages are used by the examples (stdlib only); the repo's own tooling uses already-pinned `psycopg`, `python-dotenv` and `pytest`.

## Architecture Patterns

### System Architecture Diagram

```
 cron-job.org dispatch job (existing, never modified)          cron-job.org ALARM job (new, permanent)
   |  POST .../dlr_live.yml/dispatches  at hh:05 UTC             |  GET /rest/v1/rpc/assert_fresh  every 15 min (apikey header)
   v                                                             |  200 ok | 503 PT503 stale/missing
 GitHub Actions run --GITHUB_RUN_ID--> run_id, GITHUB_SHA[:7] --> pipeline_version
   |  SUPABASE_DB_URL (Actions secret)                           |  email after 2 failures; recovery email; "job disabled" email
   v                                                             v
 +----------------------- Supabase Postgres ---------------------------------------------------+        +----------------------+
 |  public.city_rating (PK city,valid_time; RLS on; anon SELECT policy)                         |        | Supabase Data API    |
 |     ^ upsert by dlr_writer (first_written_at fixed; computed_at rewritten by same-hour retry)| <------| PostgREST            |
 |  public.latest_rating  VIEW security_invoker  (34 columns; age_minutes / is_stale /          |  SQL   | key -> role anon     |
 |        is_provisional computed from now() per request)                                        |        +----------+-----------+
 |  public.assert_fresh(int) RPC (PT503 when any of 4 cities missing or stale)                   |                   |
 |  public.pipeline_run (private run log)                                                        |                   | HTTPS + apikey
 |  ops.freshness_log <-- pg_cron every 5 min -- ops.log_freshness()   (ops not exposed)         |                   v
 +----------------------------------------------------------------------------------------------+   React dashboard / PSS/E Python / curl
                                                                                                         (SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY from env)
 Operator tooling (owner machine, read-only):
   DRY SOAK (before monitoring): city_rating rows since 2026-10-25T00:00Z -> write lag + peak age (first_written_at) + dlr_live_window_check slot verdicts -> report -> owner review -> 72 h clock
   E2E-01 trace:   cron-job.org console execution -> gh run -> pipeline_run -> city_rating(run_id) -> REST rows -> compare stored columns
   E2E-03:         anon INSERT/UPSERT/PATCH/DELETE -> 401/403 + unchanged row snapshot
   72 h SOAK:      ops.freshness_log export + exact write-based peak age + derived deploy annotations + manual annotations -> breach table with causes
   10-31 RE-CHECK: read + hidden + writes + verify_exposure.sql + supabase_smoke consumers_cannot_write
```

### Recommended Project Structure
```
supabase/migrations/
├── <ts>_expose_latest_rating.sql      # view (34 cols), comments, index, assert_fresh, revoke sweep + SELECT grants, read policy
└── <ts>_soak_freshness_log.sql        # ops schema + log table/function (no cron.schedule inside the migration; owner schedules)
supabase/ops/
├── verify_exposure.sql                # single read-only SELECT (check_name, ok, detail); local test and owner's live runs
└── soak_pg_cron.sql                   # owner-run: cron.schedule / cron.unschedule for the 5-minute log
docs/integration/
├── rest-api.md                        # contract: endpoints, 34 columns+units, 200/503, paging, no URL/key
└── examples/
    ├── curl.sh
    ├── supabase_js.mjs
    └── read_ratings.py                # stdlib only, Python 3.7+
backend/
├── supabase_rest.py                   # stdlib REST client: apikey only, paging, parse_ts, redaction of URL/key
├── e2e_verify_readonly.py             # API-01 read + hidden checks, E2E-03 write checks
├── e2e_trace.py                       # E2E-01
└── e2e_soak_report.py                 # --mode dry | soak
backend/tests/
├── local_pg.py, fake_postgrest.py     # helpers (not collected)
└── expose_migration_test.py, e2e_readonly_test.py, e2e_soak_report_test.py, example_read_ratings_test.py, secret_scan_test.py (extended)
```

### Pattern 1: `latest_rating` as an invoker view over an RLS table (34 columns)
**What:** The view applies the caller's privileges and RLS to the base table; RLS stays the single source of truth for "who sees what". `now()` is evaluated per request (PostgREST runs each request in its own transaction), so the computed columns are always current; the view cannot be materialized, which is the point.
**Evidence:** `[CITED: supabase.com/docs/guides/database/postgres/row-level-security]` — "Views bypass RLS by default because they are usually created with the `postgres` user." and "In Postgres 15 and above, make a view obey the RLS policies of its underlying tables ... by setting `security_invoker = true`." Draft run on the real `20261019...` and `20261023...` migrations on local PostgreSQL 16.14: as `anon`, `select city, valid_time, age_minutes, is_stale, is_provisional from public.latest_rating` returned one row per city (`AUSTIN|...|13|f|t`, `MIDLAND|...|13|f|t`) and `reloptions` was `{security_invoker=true}` `[VERIFIED: local PostgreSQL 16.14, 2026-10-25]`.

**Column list.** The 27 original columns (CONTEXT `06-01 LATEST_COLUMNS`) all exist in the Phase 4 table; D-01 appends four identity/source columns, then three computed columns are appended (CONTEXT default). Total **34**, in this order:

```
city, valid_time, observation_time, rating_amps, rating_mw, static_rating_amps, static_rating_mw,
line_voltage_kv, power_factor, status, fallback, fallback_gates, alerts, exhausted,
forecast_method, forecast_status, forecast_amps, forecast_ci_lower_amps, forecast_ci_upper_amps,
forecast_horizon_min, detector_signal, rating_basis, config_version, origin, run_id,
pipeline_version, computed_at,                                    -- 27 (06-01 order)
config_fingerprint, forecast_model_sha256, anomaly_model_sha256, solar_source,   -- D-01 (4)
age_minutes, is_stale, is_provisional                                  -- computed (3)
```
`[VERIFIED: supabase/migrations/20261019000000_create_city_rating.sql:25-76]` each of the 31 stored names appears in `create table if not exists public.city_rating (`, for example line 65 `config_fingerprint text not null constraint city_rating_config_fingerprint_ck check (config_fingerprint ~ '^[0-9a-f]{64}$'),`, line 66 `forecast_model_sha256 text constraint ...`, line 67 `anomaly_model_sha256 text constraint ...`, line 50 `solar_source text,`. Types: `config_fingerprint` text NOT NULL; `forecast_model_sha256` and `anomaly_model_sha256` text, nullable; `solar_source` text, nullable (`[VERIFIED: docs/data-science/schema/city_rating_v1.md:68, 83-85]`).

```sql
-- Source: pattern from Supabase RLS docs; expressions exercised on PostgreSQL 16.14 on 2026-10-25
create or replace view public.latest_rating with (security_invoker = true) as
select distinct on (city)
  city, valid_time, observation_time, rating_amps, rating_mw, static_rating_amps, static_rating_mw,
  line_voltage_kv, power_factor, status, fallback, fallback_gates, alerts, exhausted,
  forecast_method, forecast_status, forecast_amps, forecast_ci_lower_amps, forecast_ci_upper_amps,
  forecast_horizon_min, detector_signal, rating_basis, config_version, origin, run_id,
  pipeline_version, computed_at,
  config_fingerprint, forecast_model_sha256, anomaly_model_sha256, solar_source,
  ceil(extract(epoch from (now() - valid_time)) / 60)::integer            as age_minutes,
  (valid_time < now() - interval '90 minutes')                              as is_stale,
  (position('provisional' in lower(rating_basis)) > 0
     or position('provisional' in lower(config_version)) > 0)               as is_provisional
from public.city_rating
order by city, valid_time desc;

create index if not exists city_rating_city_valid_desc_idx on public.city_rating (city, valid_time desc);
```
Notes the planner must carry:
- **Appending only.** `create or replace view` can add columns only at the end and cannot rename, reorder or drop one; so the column list is a one-way contract in practice as well as by decision. Changing the *expression* of `is_provisional` (for Phase 7's label lift) is allowed because name and type stay `boolean`. `[ASSUMED]` from PostgreSQL's documented `CREATE OR REPLACE VIEW` rules; the 06-01 idempotency test (re-apply the file) covers the same-text case.
- **Comments do not carry over from the table** (Pitfall 4): write `comment on column public.latest_rating.<col>` for all 34, in Phase 4's style (leading unit or `none (category|identifier|flag|label)`). Suggested text for the computed columns: `age_minutes`: "minutes (whole, rounded up): from valid_time to the moment of the request; stale when greater than 90"; `is_stale`: "none (flag): true when valid_time is strictly more than 90 minutes before the request (OD-4); exactly 90 minutes is fresh; a stale row is the city's last good row (OD-9)"; `is_provisional`: "none (flag): true while the row's rating_basis or config_version labels the values provisional (OD-5); false only after Phase 7's re-validation go lifts the label".
- `age_minutes` type: `extract(epoch from interval)` returns `numeric` on PostgreSQL 16 (exact), so `ceil(.../60)::integer` is exact `[VERIFIED: local, pg_typeof -> numeric, integer]`.

### Pattern 1b: why `ceil`, and the 90-minute boundary (D-02)
Checked at the boundary with explicit timestamps (valid_time 10:00; "now" varied):

| now - valid_time | `ceil` age | `floor` age | `valid_time < now() - interval '90 minutes'` | `make_interval(mins => 90)` form | `(now - valid_time) > interval '90 minutes'` |
|---|---|---|---|---|---|
| 89 min 59.999999 s | 90 | 89 | false | false | false |
| exactly 90 min | 90 | 90 | false | false | false |
| 90 min 0.000001 s | 91 | 90 | true | true | true |
| 90 min 59 s | 91 | 90 | true | true | true |

`[VERIFIED: local PostgreSQL 16.14, 2026-10-25]`. All three comparison spellings agree, so `assert_fresh` (which uses `make_interval(mins => max_age_minutes)`) and the view agree at the boundary. With `floor` a row 90 min 59 s old would read `age_minutes = 90` and `is_stale = true`, which a consumer reads as a contradiction. `ceil` makes `age_minutes > 90` identical to `is_stale`. Plain English for the owner and docs: "age_minutes counts a started minute as a minute; a row is stale only once it is more than 90 full minutes old."

**Boundary test without controlling `now()`:** valid_time must be a whole UTC hour (CHECK), so a test cannot seed an exact-90-minute row. Inside one transaction `now()` is constant, so seed a row two hours back, read `age_minutes` (call it a) from the view, then assert `assert_fresh(a)` succeeds and `assert_fresh(a - 1)` raises PT503 in the same transaction. That pins the `ceil`/strict-greater equivalence for any a, including a = 90 when the transaction starts at minute 30.

### Pattern 1c: `is_provisional` must match the live label (corrects D-03's premise)
Facts: the live runner stores `config.RATING_BASIS`; the backfill stores `backfill_rating_basis(manifest)`.
- `[VERIFIED: backend/config.py:256-262]`: `RATING_BASIS: str = ("Per-conductor amperes from the IEEE 738 thermal model at one rating point per city. Static ratings are owner-supplied 345 kV bundle averages divided by an assumed subconductor count; line bearings are assumed, not measured. Not a verified equipment-limited circuit rating. Values are provisional until Phase 7's re-validation go (REVAL-01) lifts this label.")`
- `[VERIFIED: backend/supabase_load_backfill.py:150-157]`: backfill label begins `"PROVISIONAL (OD-5). Phase 3 backfill, window "` and ends `"Provisional until Phase 7's re-validation go (REVAL-01)."`
- `[VERIFIED: backend/config.py:273]`: `RATING_CONFIG_VERSION: str = "v1-provisional-2026-10-13"`
- Run this session: `config.RATING_BASIS.startswith('PROVISIONAL (OD-5)')` -> `False`; `'provisional' in config.RATING_BASIS.lower()` -> `True`; `'provisional' in config.RATING_CONFIG_VERSION.lower()` -> `True`. In SQL, `starts_with(live_label, 'PROVISIONAL (OD-5)')` -> `f` and `position('provisional' in lower(live_label)) > 0` -> `t` `[VERIFIED: local PostgreSQL 16.14]`.
- `docs/data-science/schema/city_rating_v1.md:104-106` says the same thing the code does: the live label is the "Per-conductor amperes ..." text; only backfill rows "start with `PROVISIONAL (OD-5)`" (line 146). CONTEXT D-03's parenthetical ("live rows start with `PROVISIONAL (OD-5)`") conflates the two.

Recommendation (fail toward provisional): the case-insensitive word "provisional" in `rating_basis` **or** in `config_version`. Both columns are NOT NULL, so the result is never NULL. Phase 7's GO must change **both** strings so neither contains the word (or the view's expression is updated by a new `create or replace view` migration); record that as a Phase 7 hand-off item. A label such as "no longer provisional" would still read true: the safe direction, but wrong at GO, so the Phase 7 label text must avoid the word. Add the drift-guard test (Validation Architecture): seed rows with the real `config.RATING_BASIS` + `config.RATING_CONFIG_VERSION`, and a real-shaped backfill label, and assert `is_provisional` is true for both; assert a synthetic "lifted" label pair gives false.

### Pattern 2: Read-only privilege layout (GRANT is the lock, RLS is the second lock)
```sql
alter table public.city_rating enable row level security;
revoke all on all tables in schema public from anon, authenticated;     -- covers TRUNCATE/REFERENCES/TRIGGER too
revoke all on all sequences in schema public from anon, authenticated;
grant select on public.city_rating, public.latest_rating to anon, authenticated;
drop policy if exists city_rating_public_read on public.city_rating;
create policy city_rating_public_read on public.city_rating for select to anon, authenticated using (true);
-- no INSERT/UPDATE/DELETE policy for anon/authenticated; dlr_writer keeps its own policy
alter default privileges for role postgres in schema public revoke all on tables from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
```
Why REVOKE first: until the 2026-10-30 platform change, new `public` tables carry `select, insert, update, delete` for `anon`, `authenticated`, `service_role` `[CITED: github.com/orgs/supabase/discussions/45329]`. The sweep also removes the privileges Supabase's own opt-in SQL leaves behind (commenters report `TRUNCATE`, `REFERENCES`, `TRIGGER` stay granted by that opt-in; maintainers did not confirm) `[CITED: same thread]`. `alter default privileges` is written with an explicit `for role postgres` because default privileges apply per creating role and the migration runs as `postgres` (the form Supabase's own opt-in SQL uses `[CITED: supabase.com/changelog/45329-...]`); objects created by `supabase_admin` have separate defaults that `postgres` cannot change `[CITED: discussion 45329, commenter report]`.
Also: "A policy that reads `to anon using ( true )` grants every unauthenticated visitor read access" `[CITED: supabase.com RLS docs]`; acceptable by OD-6 and recorded in the doc (Open Question 3 is now an owner decision, OD-6).

### Pattern 3: Exact freshness definition and measurement (revised for `first_written_at`)
At hourly cadence the newest row's age sawtooths from about its write lag up to 60 min plus the next write lag, then resets. The exact check uses the writes themselves: the moment a consumer stops seeing the previous row as "latest" is the **first** time the next slot's row was inserted. So the age of the old row at that moment is `first_written_at(new) - valid_time(prev)`; if that is <= 90 min for every consecutive pair, no instant exceeded 90 min. Add the trailing age of the newest row at the end of the window.
- `first_written_at` is `timestamptz not null default date_trunc('second', now())` and "never changes after insert"; `computed_at` is "when the row was last written; updated on every rewrite of the same key" `[VERIFIED: supabase/migrations/20261019000000_create_city_rating.sql:73-74, 168-169]` (`first_written_at timestamptz not null default date_trunc('second', now()),` / `computed_at timestamptz not null default date_trunc('second', now()),`).
- A same-hour retry (OD-7) overwrites values and `computed_at` but not `first_written_at`. Using `computed_at` would inflate the gap whenever a retry or drill rewrote the next row late. Demonstrated locally: a row rewritten 40 min after its first write still showed the correct 8-minute lag and 68-minute peak age with `first_written_at`.
- Exclude `origin = 'backfill'` rows (their `first_written_at` is the load time, not a live arrival).
- Expected numbers (the dry soak replaces these with measurements): the dispatch is at hh:05; the one measured first run took 3 min 6 s of job time (`docs/data-science/decisions/dlr_live_runbook.md:335`, run 40141557468, EL_PASO 126 s), so rows land roughly hh:07 to hh:10 and the peak age is about 67-70 min against the 90 min limit: about 20 min of slack. `[ASSUMED]` from one run; the dry soak measures it.
- One missed city-hour is always a breach: the next row lands about 128 min after the old slot's `valid_time`, above 90. That follows from OD-4 (grace of 30 min below two cadences), not from a defect in the check.

### Pattern 4: The permanent alarm (D-13..D-15)
cron-job.org job: GET `<SUPABASE_URL>/rest/v1/rpc/assert_fresh` (default `max_age_minutes` = 90), header `apikey: <publishable key>`, every 15 minutes, expected HTTP 200. Settings (from the REST API object `JobNotificationSettings`, which mirrors the console):
| Setting | Value | Source |
|---|---|---|
| `onFailure` | true | `[CITED: docs.cron-job.org/rest-api.html]` default false |
| `onFailureCount` | 2 ("How many failures are required before a notification is sent (min 1)") | `[CITED: docs.cron-job.org/rest-api.html]`; the doc does not say the failures must be consecutive: `[ASSUMED]` consecutive, confirm from the console wording at setup |
| `onSuccess` | true ("when the job succeeds after a prior failure": the recovery email) | `[CITED: docs.cron-job.org/rest-api.html]` |
| `onDisable` | true (email when the job is disabled automatically) | `[CITED: docs.cron-job.org/rest-api.html]` |
| Schedule | every 15 minutes, time zone UTC | schedule object has `timezone` default `UTC` `[CITED: docs.cron-job.org/rest-api.html]`; the 2026-11-01 US clock change is irrelevant to an every-15-minutes job |
| Timeout | the default; "If your URL/script does not finish after 30 seconds, it will timeout" | `[CITED: cron-job.org/en/faq/]` |
Latency from a lost city-hour to the email: stale after 90 min from the slot, first failing probe 0-15 min later, second failing probe 15 min after that, so about 105-120 min after the slot started.
**Trap (Pitfall 13):** "when it subsequently fails more than 25 times" cron-job.org disables the job `[CITED: cron-job.org/en/faq/]`. At 15 minutes that is a continuous outage of about 6.5 h. Mitigation: `onDisable` email on, and the runbook says pausing the pipeline also pauses the alarm and resuming re-enables both.
**Drill before relying on it (owner checkpoint):** create a temporary every-minute job on `rpc/assert_fresh?max_age_minutes=0` (always 503, `[VERIFIED: local PostgREST 16.4, 2026-10-19]`), same notification settings; confirm the failure email arrives after the second failure; edit it to `max_age_minutes=90` and confirm the recovery email; delete the drill job. This proves the email path and that a 503 counts as a failure: the docs map failure to `JobStatus` 4 "Failed (HTTP error)" but do not list which HTTP codes count `[ASSUMED]` that 4xx/5xx do.

### Pattern 5: Dry-soak mode of the soak report (D-07)
**What it must prove (plain English):** "Before we start the 72-hour clock, the hours already recorded show how late each hourly rating really lands, and the worst-case age of the 'current' rating stays well inside the 90-minute limit."
**Inputs already available:** live rows since the window start (slot 2026-10-25T00:00Z; the run that dispatched at 00:05:05Z is run 40145300072). Phase 5 live since then; 05-08 reads the same window.
**Why `dlr_live_window_check.py` alone is not enough:** its SQL selects `city, valid_time, run_id` from `city_rating` and `run_id, run_attempt, window_end, cities_ok, cities_failed, finished_at` from `pipeline_run` `[VERIFIED: backend/dlr_live_window_check.py:61-72]`. There is no `first_written_at` or `computed_at`, so no lag can be computed. Reuse its pure `evaluate_window(runs, run_rows, rating_rows, start, hours)` (slot verdicts `ok | incomplete | failed-visible | missing`), `fetch_runs` and `fetch_rows`, and add one SQL for write times.
**Proposed shape:** `python backend/e2e_soak_report.py --mode dry --start 2026-10-25T00:00:00Z --hours N --json PATH` (owner-run; `SUPABASE_DB_URL` through `supabase_store.connect()`; read-only SELECTs with bound parameters). Output (all offline-testable with fixtures through a pure `evaluate_dry(rows, ...)`):
1. Per city and slot: `write_lag_min = first_written_at - valid_time`; summary min / median / p95 / max.
2. Per city, per consecutive pair: `peak_age_min = first_written_at(new) - valid_time(prev)`; max, count above 75, count above 90 (the Pitfall 9 structural threshold and the OD-4 limit); trailing age at report time.
3. The `evaluate_window` slot table for the same window (so one report answers both Phase 5's 24 h check and the dry soak).
4. Fallback share per city, labelled "informational: a fallback row is a fresh row" (AUSTIN about 72 % per STATE.md; not a breach).
5. Verdict lines in plain English; exit 0 when max peak age <= 90 and no slot is missing/incomplete, exit 1 otherwise; peak age above 75 prints a warning ("a single slow hour would breach"). The owner decides; the report never edits a verdict.
**The write SQL** (executed locally on synthetic rows including a missing slot and an OD-7 rewrite; `:start`/`:end` are bound parameters, never formatted in):
```sql
with g as (
  select city, valid_time, first_written_at,
         lag(valid_time) over w as prev_valid_time
  from public.city_rating
  where origin = 'live'
    and valid_time >= %(start)s - interval '3 hours' and valid_time < %(end)s
  window w as (partition by city order by valid_time))
select city, valid_time, prev_valid_time,
       round(extract(epoch from (first_written_at - prev_valid_time)) / 60, 1) as peak_age_min_before_write,
       round(extract(epoch from (first_written_at - valid_time)) / 60, 1)       as write_lag_min,
       (first_written_at - prev_valid_time) > interval '90 minutes'              as breach
from g
where prev_valid_time is not null and valid_time >= %(start)s
order by breach desc, peak_age_min_before_write desc;
```
Synthetic result `[VERIFIED: local PostgreSQL 16.14]`: with slot 03 missing, the 04:00 row shows `peak_age_min = 128.0`, `breach = t`; neighbours `68.0` / `8.0` / `f`.
**No overlap rule:** the dry window ends at the review; the 72 h window starts at G (go reply rounded up to the next 5-minute boundary, per 06-06) and its report filters on `valid_time >= G`. State both windows in the evidence files.

### Pattern 6: Deploy annotations during the soak (D-08): derive, then supplement
`city_rating` already records what produced every row: `pipeline_version` (`GITHUB_SHA[:7]` in Actions, else `git rev-parse --short HEAD`) `[VERIFIED: backend/supabase_store.py:390-403]`, `config_fingerprint`, `forecast_model_sha256`, `anomaly_model_sha256`, `forecast_method`, `config_version`. A deploy shows up as the first slot where any of them differs from the same city's previous row:
```sql
with c as (
  select city, valid_time, first_written_at, pipeline_version, config_fingerprint,
         forecast_model_sha256, anomaly_model_sha256, forecast_method,
         lag(pipeline_version)       over w as pv0, lag(config_fingerprint)     over w as cf0,
         lag(forecast_model_sha256)  over w as fm0, lag(anomaly_model_sha256)   over w as am0,
         lag(forecast_method)        over w as me0, row_number() over w as rn
  from public.city_rating where origin = 'live' window w as (partition by city order by valid_time))
select city, valid_time, first_written_at, pv0, pipeline_version,
       (config_fingerprint is distinct from cf0)        as config_changed,
       (forecast_model_sha256 is distinct from fm0)     as forecast_model_changed,
       (anomaly_model_sha256 is distinct from am0)      as anomaly_model_changed,
       (forecast_method is distinct from me0)           as method_changed
from c
where rn > 1 and (pipeline_version is distinct from pv0 or config_fingerprint is distinct from cf0
   or forecast_model_sha256 is distinct from fm0 or anomaly_model_sha256 is distinct from am0
   or forecast_method is distinct from me0);
```
Verified on synthetic rows: a `aaaaaaa -> bbbbbbb` version change with a fingerprint change at slot 05 returned one row `[VERIFIED: local PostgreSQL 16.14]`. Then classify each `pv0 -> pipeline_version` pair with `git diff --name-only pv0 pipeline_version` (both are commits on `main`): paths under `data/models/` -> model; `backend/config.py`, `backend/city_point.py`, `backend/supabase_store.py` -> config/code; `.github/workflows/dlr_live.yml` -> workflow; other `backend/` -> code; only `docs/`, `.planning/` -> "no runtime change" (listed but not an event). **Why derive:** `pipeline_version` changes on *every* commit to `main` (a docs-only push too), so the raw change points are noisy and the classification is needed; but nothing is forgotten, and the first slot is exact. **Why still allow `annotations.json`:** it records what the data cannot: a cron-job.org edit, an owner pause, a GitHub or Supabase incident, with the explanation text. Annotation keys: breach id -> `{explanation, by, date}` (06-07's shape); deploy events are generated, not typed. Limits: a deploy during a gap appears only when the next row is written; `pipeline_version = 'unknown'` appears when git is unreadable and must be flagged, not classified. A breach caused by a deploy still counts and is explained (D-08).

### Anti-Patterns to Avoid
- **Relying on RLS alone for write protection:** blocked `PATCH`/`DELETE` return 200 with `[]`/204 and no error. Revoke privileges.
- **Deriving `is_stale` from the rounded `age_minutes`** (or `floor`): boundary disagreement (Pitfall 12).
- **Testing `rating_basis` for the prefix `PROVISIONAL (OD-5)`:** false on every live row (Pitfall 11).
- **Measuring peak age from `computed_at`:** inflated by same-hour retries (Pitfall 14).
- **Serving OpenAPI to consumers via `GET /rest/v1/`:** anon gets "Access to schema is forbidden"; commit the doc.
- **Putting the secret/service key, the project URL or the publishable key into any committed file** (D-10).
- **Using `datetime.fromisoformat()` on raw PostgREST timestamps in Python < 3.11** (Pitfall 3).
- **Using cron-job.org history as the soak record** (50 executions, bodies 2 days).
- **Counting a fallback row as "stale":** a fallback rating still has a fresh `valid_time`.
- **Stopping a paging loop when `len(page) < 1000`:** if the project's "Max rows" is ever lowered the loop ends early and silently truncates (Pitfall 6); stop on an empty page.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| REST read API | Flask/FastAPI shim | Supabase PostgREST | Decided; out of scope |
| "Latest per city" and "is it old / provisional" | App-side max() and age maths in each client | `latest_rating` view columns | One definition for React, PSS/E, the alarm and the soak log |
| Write protection | Middleware that rejects verbs | GRANT/REVOKE + RLS | Enforced in Postgres for every path |
| Auth for read | Custom token scheme | Publishable key (`anon` role) | `[CITED: supabase.com/docs/guides/api/api-keys]` "Safe to expose online: web page, mobile or desktop app, GitHub actions, CLIs, source code." (still not committed here, D-10) |
| Scheduler for the soak probe | Self-hosted cron / laptop loop | `pg_cron` in the database | Always on, free |
| Alerting on staleness | Custom mailer | cron-job.org failure + recovery + disabled notifications on `rpc/assert_fresh` | Notification fields exist `[CITED: docs.cron-job.org/rest-api.html]` |
| HTTP status for "stale" | Parsing body in cron-job.org | PostgREST `RAISE SQLSTATE 'PT503'` | `[CITED: docs.postgrest.org/en/stable/references/errors.html]`; verified locally: GET returns HTTP 503 |
| Pagination | Hand-rolled paging with a short-page stop | `limit`/`offset` (or `Range`) until an empty page; supabase-js `.range()` | Default max rows is 1000 |
| Timestamp parsing for PSS/E | `fromisoformat` on raw strings | the tested `parse_ts()` helper | Pitfall 3 |
| Slot verdicts for the dry soak | A second run/slot matcher | `dlr_live_window_check.evaluate_window` | Already handles OD-7 overwrites and late runs |
| Redaction of DB URLs | New regexes | `supabase_store.redact` (DB side); add a small URL/key redaction for the REST side | Pitfall 15 |
| Deploy log | Hand-typed deploy list as the only record | change points in `city_rating` + `git diff --name-only` | Data records `pipeline_version` per row |

**Key insight:** every protection this phase needs already exists as a Postgres, PostgREST or cron-job.org primitive; the risk is in defaults (grants, view security mode, silent zero-row writes, rounding, label text) not in missing features.

## Runtime State Inventory

This phase adds objects; it renames nothing. Items that become runtime state and need an owner teardown/ownership note:
| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | `ops.freshness_log` rows (about 864 probes x 4 cities in 72 h, 3,456 rows); `cron.job_run_details` rows for the soak job (not cleaned automatically and kept after unschedule `[CITED: supabase.com/docs/guides/cron/quickstart]`) | Soak record exported to the repo; at soak end delete the soak job's `cron.job_run_details` rows (or accept the few hundred rows); keep or drop `ops.freshness_log` per owner (a permanent history is deferred) |
| Live service config | pg_cron job `soak-freshness` (5-minute); cron-job.org alarm job (permanent, D-13); optional cron-job.org drill job (temporary) | Unschedule `soak-freshness` at soak end (`select cron.unschedule('soak-freshness')`, deletes it from `cron.job`); alarm stays; delete the drill job. Never modify the dispatch or shadow jobs |
| OS-registered state | None — verified by design: no local scheduler, launchd, Task Scheduler or pm2 is used | None |
| Secrets/env vars | `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` (consumer env vars, never committed); the publishable key and URL are stored once inside the cron-job.org alarm job (header and URL) | Owner hands the two values to the teams out of band; no secret value in the repository |
| Build artifacts | None | None |

## Common Pitfalls

### Pitfall 1: RLS-only write blocking is silent for UPDATE/DELETE
**What goes wrong:** With `GRANT UPDATE, DELETE` still present and no write policy, `PATCH` and `DELETE` return `200` with `[]` (or `204`) and change nothing; `INSERT` returns `401` `42501`. A naive E2E-03 asserting "non-2xx" would fail on PATCH/DELETE, or be "fixed" by loosening the assertion.
**Evidence:** `[VERIFIED: local PostgREST 16.4, 2026-10-19]` INSERT -> `{"code":"42501",...,"message":"new row violates row-level security policy for table \"city_rating\""}` HTTP 401; PATCH -> `[]` HTTP 200; DELETE -> `[]` HTTP 200; table unchanged. Supabase docs agree `[CITED: supabase.com RLS docs]`.
**How to avoid:** revoke all write privileges from `anon` and `authenticated`. With no grant, all three return `401` `{"code":"42501",...,"message":"permission denied for table city_rating"}` `[VERIFIED: local]`. In E2E-03 assert both the status (401 or 403) AND that before/after row count + checksum are identical.
**Warning signs:** the script sees any 2xx on a write.

### Pitfall 2: Default grants on `public` (platform change reaches existing projects 2026-10-30)
**What goes wrong:** Until a project opts in, new `public` tables are reachable by `anon` with all four privileges; from the change on, "tables without explicit grants stop being reachable via the Data API" and PostgREST answers `42501` `[CITED: github.com/orgs/supabase/discussions/45329]`.
**What the change touches (refined 2026-10-25):** Dates: opt-in checkbox 2026-04-28, default for new projects 2026-05-30, **existing projects 2026-10-30**. Maintainers state existing tables keep their grants; only objects created afterwards need explicit grants `[CITED: discussion 45329]`. The Supabase changelog page is thinner and says "verify this in your project before the date" `[CITED: supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically]`. The setting name is "Automatically expose new tables and functions" (tables, and per the docs functions: "New functions are callable by every role" today, with `PUBLIC` execute coming from a Postgres global default that a schema-level revoke cannot remove) `[CITED: supabase.com/docs/guides/api/hardening-data-api]`. A 2026-05-30-or-later project replaying old migrations leaves tables unreachable (commenters) — not our case.
**Consequences for this phase:** (a) The Phase 6 migration (a new view and a new function created before or after 10-30) states every grant explicitly: `grant select ... to anon, authenticated` and `grant execute on function ... to anon, authenticated` after `revoke ... from public, anon, authenticated`, so it behaves the same on either side of the date. (b) The `ops` schema functions are protected by `ops` having no `USAGE` for anon and not being an exposed schema, even though function `EXECUTE` defaults to `PUBLIC`. (c) What can break on 10-30 is not our migration but the assumption that nothing else moves: a grant removed, or a default re-applied by the platform. Hence the separate re-check (Pitfall 17).
**Warning signs:** `information_schema.role_table_grants` shows `anon` with INSERT/UPDATE/DELETE on any exposed object; anon `GET latest_rating` returns 42501 after 10-30.

### Pitfall 3: Python < 3.11 cannot parse PostgREST timestamps reliably
**What goes wrong:** `datetime.fromisoformat()` before 3.11 rejects `Z` and fractions that are not 3 or 6 digits; Postgres drops trailing zeros, so `.1`, `.11297` arrive.
**Evidence:** `[VERIFIED: CPython 3.9.6 and 3.10.21, 2026-10-25]` native `fromisoformat` accepts `2026-10-25T01:00:00+00:00` and fails on `...:00Z`, `...:14.1+00:00`, `...:14.11297+00:00`; on 3.12.13 all four parse. The helper below (regex to date, clock, optional fraction, optional offset; pad or cut the fraction to six digits; normalise `Z`, `+00`, `+0000`) returned the correct UTC instant for seven formats on 3.9.6, 3.10.21 and 3.12.13.
**How to avoid:** the tested `parse_ts()` in the PSS/E example; `valid_time` is whole-hour (CHECK), `first_written_at`/`computed_at` are `date_trunc('second', now())` defaults so fractions are rare but a manual write could carry them; always parse the offset (the Supabase session zone is `[ASSUMED]` UTC; the local psql session used -05).

### Pitfall 4: OpenAPI is not available to the anon key; view comments do not inherit
**What goes wrong:** Plans saying "consumers read the OpenAPI at `/rest/v1/`" fail with "Access to schema is forbidden" `[CITED: supabase.com/changelog/42949-breaking-change-removing-access-to-openapi-spec-via-the-anon-key]` (existing projects from 2026-04-08). `COMMENT ON COLUMN` on the base table does NOT carry over to the view `[VERIFIED: local, 2026-10-19]`; comment all 34 view columns, including the three computed ones.
**How to avoid:** the repo doc `docs/integration/rest-api.md` is the contract; put units in names AND comments.

### Pitfall 5: Key naming and header discipline
**What goes wrong:** old posts use the `anon` JWT plus `Authorization: Bearer`. New keys: `sb_publishable_...` / `sb_secret_...`, "Send publishable and secret keys on the `apikey` header, not on `Authorization: Bearer`" `[CITED: supabase.com/docs/guides/api/api-keys]`; legacy keys deprecated "by the end of 2026". Examples use only the publishable key in `apikey`. The publishable-key path through the real gateway was never exercised (earlier emulation used a JWT): Wave 0 of the live run exercises each example once `[ASSUMED]` until then.

### Pitfall 6: Silent truncation at 1000 rows; paging and its stop condition
**What goes wrong:** results are cut at the project "Max rows" (default 1000) with no error `[CITED: supabase.com/docs/reference/dart/v1/select and /csharp/select, via search; Supabase community GitHub discussion 3765]` and clients are told to use `range()` for larger sets. A stop rule "short page means done" breaks if the cap is ever lowered below the page size.
**How to avoid:** page with an explicit **unique** order key: for one city, `order=valid_time.asc` is unique because the primary key is (`city`, `valid_time`); for several cities use `order=valid_time.asc,city.asc`. Bound the window with `valid_time=gte.<start>` and `valid_time=lt.<end>` so rows appended during paging (later `valid_time`) cannot shift offsets, and a same-hour rewrite keeps its key. Continue until a page is empty, or until `Content-Range` shows the end (`Prefer: count=exact` returns e.g. `0-24/3573458`; "the larger the table the slower this query runs") `[CITED: docs.postgrest.org/en/stable/references/api/pagination_count.html]`. `Range-Unit: items` with `Range: 0-999` is inclusive on both ends; supabase-js `.range(from, to)` is 0-based and inclusive and "respects the query order and if there is no order clause the range could behave unexpectedly" `[CITED: supabase.com/docs/reference/javascript/range]`. The Python example paged 2,500 rows in three requests plus an empty-page stop on 3.9.6, 3.10.21 and 3.12.13 against a fake server with a 1000 cap `[VERIFIED: in-process fake server, 2026-10-25]`; the real PostgREST path is exercised at the live run.

### Pitfall 7: Schema-cache lag after DDL
A new view/function returns `404 PGRST202` until PostgREST reloads its schema cache; locally `NOTIFY pgrst, 'reload schema'` fixed it `[VERIFIED: local, 2026-10-19]`. End the migration with `notify pgrst, 'reload schema';` (harmless). Supabase migrations normally trigger the reload `[ASSUMED]`.

### Pitfall 8: Actions quota (resolved)
Actions minutes are no longer the constraint since the repository went public (runbook section 12: "Actions minutes on GitHub-hosted runners are free for public repositories"). The reason to keep the probe in the database now is independence from Actions incidents, not cost.

### Pitfall 9: 90-minute budget vs real latency (now measurable from existing rows)
**What goes wrong:** the 90 = 60 + 30 bound must absorb dispatch jitter, Actions queue time, the run and the write. If the real peak age is above about 75 min the soak fails structurally. **State today:** `valid_time` is the hour-truncated UTC slot of the run window end `[VERIFIED: migration comment line 122 and city_rating_v1.md:24]`, so the budget is analyzable; the dispatch is hh:05. **How to avoid:** the dry soak (Pattern 5) measures write lag and peak age from the rows since 2026-10-25T00:00Z before the clock starts. If the maximum exceeds 90 it is a Phase 4/5 problem, not OD-4. A manual re-run does not back-fill a missed slot (runbook section 6), so a gap in the dry-soak window stays visible.

### Pitfall 10: "A failed city is missing, not stale-flagged"
A failed city writes no row (OD-9), so its latest row simply ages while the other three stay fresh; a probe that checks only "4 rows returned" passes while a city is 3 h old. Check per-city age (the log does, and the view's `is_stale` per row), and `assert_fresh` counts cities AND stale rows (raises if fewer than 4 or any stale).

### Pitfall 11: `is_provisional` keyed to the wrong label (new)
**What goes wrong:** D-03 as written names the prefix `PROVISIONAL (OD-5)`; live rows start with "Per-conductor amperes ..." so the boolean is false on every live row, telling the dashboard and PSS/E that provisional ratings are final. This is the label-in-the-data being right and the derived flag being wrong, so nothing else would notice.
**Evidence:** Pattern 1c.
**How to avoid:** the word-based rule on `rating_basis` or `config_version`, a drift-guard test that feeds the real `config.RATING_BASIS` and `config.RATING_CONFIG_VERSION` strings, and a Phase 7 hand-off note that lifting the label must change both strings. Tell the owner (plain English): "the flag is derived from the words in the label, not from how the label begins, because live rows and backfill rows begin differently".
**Warning signs:** the E2E trace shows `is_provisional = false` on a row whose `rating_basis` still says "provisional".

### Pitfall 12: Age rounding vs the stale rule (new)
See Pattern 1b: use `ceil`, make `is_stale` a direct comparison, and never compute `is_stale` from the integer. The soak log (`ops.log_freshness`) must use the same direct comparison; recommended: read `is_stale` and the exact `extract(epoch ...)` seconds from the view in the log function, and add a test that `breach` equals `age_seconds > 5400`.

### Pitfall 13: cron-job.org auto-disables a long-failing job (new)
**What goes wrong:** "when it subsequently fails more than 25 times" the job is disabled; at a 15-minute interval about 6.5 h of continuous 503 (a stopped pipeline, an owner pause) disables the permanent alarm and no recovery email follows; the runbook already notes the same behaviour for the dispatch job (`dlr_live_runbook.md:185-189`).
**How to avoid:** `onDisable` email; runbook: pause pipeline => pause alarm, resume => re-enable and check job state. `[ASSUMED]` that the 25 failures are consecutive (the FAQ says "subsequently").

### Pitfall 14: `computed_at` is not the arrival time (new)
See Pattern 3. `computed_at` changes on every rewrite; the exact peak age and the dry-soak lag use `first_written_at`. A soak report that used `computed_at` would blame the pipeline for a retry the owner deliberately ran.

### Pitfall 15: Redaction does not cover the REST side (new)
`supabase_store.redact` removes `postgres(ql)://` URLs, `key=value` secrets (`password, token, api_key, apikey, key, secret`) and the values in `SUPABASE_DB_URL` / `SUPABASE_ADMIN_DB_URL` `[VERIFIED: backend/supabase_store.py:274-293, 204]`. It does not know `SUPABASE_URL` (host and project reference) or the publishable key. The REST client must scrub both from any error text, `repr`, JSON evidence and printed lines (replace the host, the 20-character reference, the key); error paths (`URLError`, `HTTPError`, JSON error bodies that echo a URL) get tests that plant a fake URL and key and assert they never appear in stdout, stderr or `--json-out`. Build the planted values from pieces so `secret_scan_test.py` never matches the test file.

### Pitfall 16: Default privileges apply per creating role (new)
`alter default privileges in schema public revoke ...` without `for role` affects objects created by the **current** role. The migration is applied through Phase 4's recorded `supabase db push --db-url ...` procedure; confirm which role it connects as, and write `for role postgres` explicitly if it is `postgres`, as Supabase's own SQL does. Objects created by `supabase_admin` (dashboard-created) follow separate defaults; the revoke sweep and `verify_exposure.sql`'s aclexplode check, not the default privileges, are the real guarantee.

### Pitfall 17: The post-2026-10-30 permission re-check (new; folds in T-04-22)
**Date:** STATE.md carries T-04-22 as "re-run the local smoke (`consumers_cannot_write`) on or after 2026-10-31" `[VERIFIED: STATE.md:187]`; CONTEXT says "after 10-30"; the rollout is gradual `[CITED: discussion 45329]`. Run it on or after 2026-10-31.
**What it must cover (each with its plain-English meaning):**
| Check | Command | What it proves (plain English) |
|---|---|---|
| Read still works | `e2e_verify_readonly.py --check-read` | "Anyone with the public key can still read the current rating for all four cities." |
| Hidden tables still hidden | `--check-hidden` | "The private run log and the soak log still cannot be read with the public key." |
| Writes still refused | `--check-writes` (insert, upsert, update, delete) with before/after snapshot | "Trying to change data with the public key is still refused, and the data did not change." |
| Privileges still exactly as designed | `supabase/ops/verify_exposure.sql` | "The database's own permission list still shows read-only access on exactly two objects." |
| T-04-22 | `supabase_smoke.py` check `consumers_cannot_write` (Actions workflow `supabase_smoke.yml`, dispatch-only, or the local command in its docstring) | "The platform change did not hand the public roles any write permission on the two tables." |
**Existing smoke limits:** `consumers_cannot_write` loops `TABLES = ("public.city_rating", "public.pipeline_run")` and `WRITE_PRIVILEGES = ("INSERT", "UPDATE", "DELETE", "TRUNCATE")` for roles present among `("anon", "authenticated")` `[VERIFIED: backend/supabase_smoke.py:55, 64-65, 271-280]`; it does not look at `public.latest_rating` or at functions, and records `info["anon_can_select"]` as informational (becomes true after Phase 6). `verify_exposure.sql` covers all public relations and anon-executable functions, so it complements rather than duplicates the smoke. The smoke needs `SUPABASE_DB_URL` and (in Actions) the `production` environment.

### Pitfall 18: A Phase 7 deploy during the soak looks like a pipeline fault
A conductor or model change changes values (and fingerprints) but not freshness; a *broken* deploy turns a run red and costs a city-hour, which is a breach and is explained like any other (D-08). The derived annotations (Pattern 6) put the deploy beside the breach so the explanation takes seconds. Do not pause or restart the soak.

## Code Examples

Local runs this session: SQL on PostgreSQL 16.14 (real migrations applied), the Python example and `parse_ts` on CPython 3.9.6 / 3.10.21 / 3.12.13 against an in-process fake PostgREST, `ast` feature-version gate. The curl and supabase-js examples were last run against the 2026-10-19 emulation (older single-endpoint forms); the new paging forms below are `[ASSUMED]` until run. All credentials come from the environment.

### SQL: expose `latest_rating` and prove it
See Pattern 1 (view, index) and Pattern 2 (revoke sweep, SELECT grants, read policy). Add at the end: the 34 `comment on column` statements, `assert_fresh` (below) and `notify pgrst, 'reload schema';`.

### `assert_fresh` (alarm and REST-path check)
```sql
create or replace function public.assert_fresh(max_age_minutes integer default 90)
returns jsonb language plpgsql stable security invoker set search_path = '' as $$
declare missing text[]; stale text[]; n integer;
begin
  if max_age_minutes is null or max_age_minutes < 0 or max_age_minutes > 10080 then
    raise sqlstate '22023' using message = 'max_age_minutes out of range';
  end if;
  select array_agg(c.city order by c.city) filter (where l.city is null),
         array_agg(c.city order by c.city) filter (where l.valid_time < now() - make_interval(mins => max_age_minutes)),
         count(l.city)
    into missing, stale, n
  from (values ('AUSTIN'), ('CORPUS_CHRISTI'), ('MIDLAND'), ('EL_PASO')) as c(city)
  left join public.latest_rating l on l.city = c.city;
  if missing is not null or stale is not null then
    raise sqlstate 'PT503' using message = 'stale or missing city rating',
      detail = format('missing=%s stale=%s', coalesce(missing::text, '{}'), coalesce(stale::text, '{}'));
  end if;
  return jsonb_build_object('ok', true, 'cities', n, 'max_age_minutes', max_age_minutes);
end $$;
revoke all on function public.assert_fresh(integer) from public, anon, authenticated;
grant execute on function public.assert_fresh(integer) to anon, authenticated;
```
The shape is the 06-01 plan's (same contract: 200 JSON or PT503; 22023 on bad input; city list = `config.LOCATIONS`); this refresh only restates it so the comparison form (`valid_time < now() - make_interval(...)`) is visibly the same as the view's. Earlier locally verified: fresh -> `200 {"ok": true, ...}`; `max_age_minutes=0` -> `503 {"code":"PT503",...}` for POST and plain GET `rpc/assert_fresh?max_age_minutes=0` (the form cron-job.org sends) `[VERIFIED: local PostgREST 16.4, 2026-10-19]`. The function body above was not executed this session: the planner's 06-01 Task 2 tests it.

### curl (any consumer; credentials from the environment)
```bash
# SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY come from the shell; the owner gives them to you directly.
: "${SUPABASE_URL:?set SUPABASE_URL}" "${SUPABASE_PUBLISHABLE_KEY:?set SUPABASE_PUBLISHABLE_KEY}"
H=(-H "apikey: $SUPABASE_PUBLISHABLE_KEY" -H "Accept: application/json")

# (1) current rating per city (4 rows)
curl -sS "$SUPABASE_URL/rest/v1/latest_rating?select=city,valid_time,rating_amps,rating_mw,status,age_minutes,is_stale,is_provisional&order=city" "${H[@]}"

# (2) one city over a date range, paging past the 1000-row cap
Q="city=eq.AUSTIN&select=valid_time,rating_amps&valid_time=gte.2026-10-25T00:00:00Z&valid_time=lt.2026-11-01T00:00:00Z&order=valid_time.asc"
total=$(curl -sSI "$SUPABASE_URL/rest/v1/city_rating?$Q" "${H[@]}" -H "Prefer: count=exact" -H "Range-Unit: items" -H "Range: 0-0" \
        | tr -d '\r' | awk -F/ 'tolower($1) ~ /^content-range/ {print $2}')
for offset in $(seq 0 1000 $((total - 1))); do
  curl -sS "$SUPABASE_URL/rest/v1/city_rating?$Q&limit=1000&offset=$offset" "${H[@]}"
done
```
Single-city and `Prefer: count=exact` HEAD forms were verified locally against `latest_rating` (`Content-Range: 0-3/4`) `[VERIFIED: local PostgREST 16.4, 2026-10-19]`; the two-`valid_time`-filter range and the Range-header HEAD on `city_rating` are `[ASSUMED]` until run (PostgREST allows repeated filters on one column `[ASSUMED]`). Also documented in the contract (not required as an example per D-12): `Accept: application/vnd.pgrst.object+json` for exactly-one-row (HTTP 406 `PGRST116` otherwise); `rpc/assert_fresh` (200 `{"ok":true,...}` / 503 `PT503` with `detail` naming the cities).

### supabase-js (frontend; Node >= 22 for the CLI form)
```javascript
// SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY come from the environment (a bundler passes them to the browser build).
import { createClient } from '@supabase/supabase-js'   // pin the major: @supabase/supabase-js@2

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_PUBLISHABLE_KEY)

// (1) current rating per city
const current = await supabase.from('latest_rating')
  .select('city,valid_time,rating_amps,rating_mw,status,age_minutes,is_stale,is_provisional')
  .order('city')
if (current.error) throw current.error

// (2) one city over a date range, paging past the 1000-row cap (range is 0-based and inclusive)
const PAGE = 1000
const rows = []
for (let from = 0; ; from += PAGE) {
  const { data, error } = await supabase.from('city_rating')
    .select('valid_time,rating_amps').eq('city', 'AUSTIN')
    .gte('valid_time', '2026-10-25T00:00:00Z').lt('valid_time', '2026-11-01T00:00:00Z')
    .order('valid_time', { ascending: true })          // unique per city: no repeated or skipped rows
    .range(from, from + PAGE - 1)
  if (error) throw error
  if (data.length === 0) break
  rows.push(...data)
}
```
`[CITED: supabase.com/docs/reference/javascript/range]` for `.range` semantics; the `latest_rating` select/order forms were run with 2.118.0 under Node 26 on 2026-10-19 `[VERIFIED: local emulation]`; the paging loop is `[ASSUMED]` until run. A browser needs only native `fetch`. Node 20 needs 2.109.0 (2.110+ requires Node >= 22) `[CITED: supabase-js README]`.

### Python stdlib (PSS/E): Python 3.7+, credentials from the environment
```python
"""Read the current DLR rating per city and one city's history from the Supabase REST API.

Standard library only; written for Python 3.7+ (no walrus, no positional-only parameters,
no dict union, no str.removeprefix, no builtin generics).
Environment: SUPABASE_URL (project URL) and SUPABASE_PUBLISHABLE_KEY (publishable key).
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

PAGE = 1000  # the server returns at most 1000 rows per request (project "Max rows")


def parse_ts(s):
    """PostgREST timestamptz -> aware datetime. datetime.fromisoformat() before Python 3.11
    rejects 'Z' and any fraction that is not exactly 3 or 6 digits."""
    s = s.strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.(\d+))?(Z|[+-]\d{2}(?::?\d{2})?)?$", s)
    if not m:
        raise ValueError("unrecognised timestamp: %r" % s)
    day, clock, frac, off = m.groups()
    off = off or "+00:00"
    if off == "Z":
        off = "+00:00"
    if re.match(r"^[+-]\d{2}$", off):
        off += ":00"
    if re.match(r"^[+-]\d{4}$", off):
        off = off[:3] + ":" + off[3:]
    return datetime.fromisoformat("%sT%s.%s%s" % (day, clock, ((frac or "") + "000000")[:6], off))


def get(path, params=None):
    base = os.environ["SUPABASE_URL"].rstrip("/")
    query = ("?" + urllib.parse.urlencode(params, safe=",.()*:")) if params else ""
    req = urllib.request.Request(base + "/rest/v1/" + path + query, headers={
        "apikey": os.environ["SUPABASE_PUBLISHABLE_KEY"], "Accept": "application/json",
        "User-Agent": "dlr-psse-client/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit("HTTP %s from %s" % (e.code, path))
    except urllib.error.URLError as e:
        raise SystemExit("could not reach the service: %s" % e.reason)


def get_all(path, params, order):
    """Every row in pages, ordered by a unique key so no row repeats or is skipped.
    Stops on an empty page, so it still works if the server's row cap is below PAGE."""
    rows, offset = [], 0
    while True:
        page = get(path, dict(params, order=order, limit=PAGE, offset=offset))
        if not page:
            return rows
        rows.extend(page)
        offset += len(page)


def main():
    for r in get("latest_rating", {"select": "city,valid_time,rating_amps,rating_mw,status,age_minutes,is_stale,is_provisional",
                                   "order": "city"}):
        print("%-15s %7.1f A %7.1f MW %-8s age %3d min stale=%s provisional=%s" % (
            r["city"], r["rating_amps"], r["rating_mw"], r["status"], r["age_minutes"], r["is_stale"], r["is_provisional"]))
    rows = get_all("city_rating", {"city": "eq.AUSTIN", "select": "valid_time,rating_amps",
                                   "valid_time": "gte.2026-10-25T00:00:00Z"}, "valid_time.asc")
    print("AUSTIN rows since 2026-10-25T00:00Z:", len(rows))
    if rows:
        print("first", parse_ts(rows[0]["valid_time"]).astimezone(timezone.utc).isoformat())


if __name__ == "__main__":
    main()
```
Run result `[VERIFIED: CPython 3.9.6, 3.10.21, 3.12.13 against an in-process fake PostgREST with a 1000-row cap, 2026-10-25]`: four city lines, `AUSTIN rows since 2026-10-25T00:00Z: 2500`, exit 0 on all three interpreters (the version of the loop that stopped on a short page was the one run; the empty-page stop shown here is the recommended form and was reasoned, not run: the planner's test runs it). `ast.parse(source, feature_version=(3, 7))` parsed the script and rejected a walrus (3.8 syntax) in a control `[VERIFIED: CPython 3.12.13]`; the `feature_version` check is documented best-effort `[ASSUMED]`, so it is a syntax gate only. Not covered locally: Python 3.7 itself (see Environment Availability), so that the example uses only 3.7-available stdlib APIs (`urllib`, `json`, `re`, `os`, `datetime.fromisoformat`) is `[ASSUMED]`. Windows (PSS/E) note for the doc: `set SUPABASE_URL=...` and `set SUPABASE_PUBLISHABLE_KEY=...` in the command shell before running. A second `User-Agent` note: set defensively because some CDN front ends reject `Python-urllib` `[ASSUMED]`.

### Writes must be rejected (E2E-03 matrix)
```bash
# Expect: HTTP 401 (or 403) + JSON code 42501 for each; then re-count rows and compare a checksum to prove nothing changed.
curl -sS -o /dev/stderr -w "%{http_code}\n" -X POST   "$SUPABASE_URL/rest/v1/city_rating" -H "apikey: $SUPABASE_PUBLISHABLE_KEY" -H 'Content-Type: application/json' -d '{"city":"AUSTIN","valid_time":"2031-01-01T00:00:00Z","rating_amps":1,"status":"ok"}'
curl -sS -o /dev/stderr -w "%{http_code}\n" -X POST   "$SUPABASE_URL/rest/v1/city_rating?on_conflict=city,valid_time" -H "apikey: $SUPABASE_PUBLISHABLE_KEY" -H 'Content-Type: application/json' -H 'Prefer: resolution=merge-duplicates' -d '[{"city":"AUSTIN","valid_time":"2031-01-01T00:00:00Z","rating_amps":1,"status":"ok"}]'
curl -sS -o /dev/stderr -w "%{http_code}\n" -X PATCH  "$SUPABASE_URL/rest/v1/city_rating?city=eq.AUSTIN" -H "apikey: $SUPABASE_PUBLISHABLE_KEY" -H 'Content-Type: application/json' -d '{"rating_amps":1}'
curl -sS -o /dev/stderr -w "%{http_code}\n" -X DELETE "$SUPABASE_URL/rest/v1/city_rating?city=eq.AUSTIN" -H "apikey: $SUPABASE_PUBLISHABLE_KEY"
```
Local status map (no write grants): table INSERT/PATCH/DELETE -> `401 {"code":"42501",...,"message":"permission denied for table city_rating"}`. Writes to the `DISTINCT ON` view -> `500 {"code":"55000","details":"Views containing DISTINCT are not automatically updatable."...}` (rejected, but by "not updatable", so a 5xx is not an outage; treat view writes as "any non-2xx") `[VERIFIED: local PostgREST 16.4, 2026-10-19]`. PostgREST maps `42501` to "if authenticated 403, else 401" `[CITED: docs.postgrest.org/en/stable/references/errors.html]`; accept 401 or 403 on the real platform `[ASSUMED]`. Note: the test write payload carries only a 2031 slot and is never accepted; if a write were ever accepted, the snapshot check must fail the run (that row would also violate nothing, so the check, not the database, is the guard).

### `ops.log_freshness` (5-minute soak log; reads the view)
```sql
create schema if not exists ops;
create table if not exists ops.freshness_log (
  id bigint generated always as identity primary key,
  probed_at timestamptz not null default now(),
  city text not null,
  latest_valid_time timestamptz,
  age_seconds integer,
  breach boolean not null
);
create or replace function ops.log_freshness() returns void language sql set search_path = '' as $$
  insert into ops.freshness_log (city, latest_valid_time, age_seconds, breach)
  select c.city, l.valid_time,
         floor(extract(epoch from (now() - l.valid_time)))::integer,
         coalesce(l.is_stale, true)                     -- no row at all counts as a breach
  from (values ('AUSTIN'), ('CORPUS_CHRISTI'), ('MIDLAND'), ('EL_PASO')) as c(city)
  left join public.latest_rating l on l.city = c.city;
$$;
revoke all on schema ops from public, anon, authenticated;
revoke all on all tables in schema ops from public, anon, authenticated;
revoke all on function ops.log_freshness() from public, anon, authenticated;
-- owner-run, not part of the migration:  select cron.schedule('soak-freshness', '*/5 * * * *', $$select ops.log_freshness()$$);
-- teardown:                              select cron.unschedule('soak-freshness');
```
The 2026-10-19 version took a `max_age_minutes` parameter and hard-coded the comparison; reading `is_stale` from the view keeps a single definition (D-02: "the same rule as `assert_fresh` and the soak log"). The job runs as the pg_cron owner (the view then reads with that role's rights); `cron.schedule(name, schedule, command)` and `cron.unschedule(name)` per the Supabase quickstart `[CITED: supabase.com/docs/guides/cron/quickstart]`. `pg_cron` was not run locally. Supabase recommends no more than 8 concurrent jobs and each job under 10 minutes `[CITED: supabase.com/docs/guides/cron]`. A probe is expected every 5 minutes: 864 probes in 72 h; a probe gap is two consecutive `probed_at` values more than 10 minutes apart and is its own breach class ("the check itself did not run").

### Secret scan extension (D-10)
Today's patterns: `postgres(ql)://user:password@`, `sb_secret_...`, a three-part JWT and a role statement that sets a literal password `[VERIFIED: backend/tests/secret_scan_test.py:24-30]`; the report prints path, line number and pattern name only, and plants are built from pieces. Add, in the same style:
```python
_SB_HOST = re.compile(r"\b[a-z0-9]{20}\.supabase\.(?:co|in|red)\b")          # a project host
_POOLER_USER = re.compile(r"\b(?:postgres|dlr_writer|authenticator)\.[a-z0-9]{20}\b")  # pooler user carries the reference
_SB_PUBLISHABLE = re.compile("sb_" + "publishable_" + r"[A-Za-z0-9_-]{16,}")
```
Checked against the tracked tree (`git ls-files`, 2026-10-25): `_SB_HOST` matched one line (a placeholder host in the previous version of this file, removed in this refresh); `_POOLER_USER` and `_SB_PUBLISHABLE` matched nothing; a pattern on the generic `pooler.supabase.com` host matched 14 lines in Phase 4 planning docs (placeholders), so **do not** ban that string repo-wide. Git history: no commit adds a 20-character `*.supabase.co` host or a `pooler.supabase.com` host (`git log -G`, count 0 each) `[VERIFIED: git, 2026-10-25]`, so no history rewrite is indicated by this check (it cannot see a reference that was committed in some other shape). Real project references are 20 lowercase letters `[ASSUMED]` from Supabase's URL form, so the pattern is an allowlist-free shape check; docs use `<ref>`-style placeholders that the pattern does not match.
Owner-local, env-gated test (never reads `.env`; skips when the variable is unset; CI has no `SUPABASE_URL` and the pattern test is the CI guard): derive the reference from `SUPABASE_URL` (the host's first label) or from `SUPABASE_DB_URL` through `supabase_store._connection_identifiers` (user part after the dot, plus host) and assert none of those strings occurs in any tracked file. The owner runs it before a push with the variables exported. The redaction-leak side (Pitfall 15) is separate.

### Soak: exact peak age between writes
See Pattern 5 (SQL); the 72 h report adds a trailing-age line: `select city, now() - max(valid_time) from public.city_rating where origin = 'live' group by city` and the probe-gap check on `ops.freshness_log`.

### E2E-01 trace (cron-job.org -> run -> rows -> REST)
Unchanged in method; COVERAGE.md keeps the dispatch job untouched (no `saveResponses`, no `return_run_details`), so correlation is by time and run id:
1. cron-job.org console: the execution for slot hh:05 (planned time, actual time, jitter, HTTP 204).
2. `gh run list --workflow dlr_live.yml` (as `dlr_live_window_check.fetch_runs`) -> the run whose `createdAt` is within seconds of that execution (`event = workflow_dispatch`).
3. SQL (owner connection): `pipeline_run` row for `run_id`; `city_rating where run_id = '<id>'` -> 4 rows (the key `run_id` is `GITHUB_RUN_ID`).
4. REST: `latest_rating` (or `city_rating?run_id=eq.<id>` if a later slot has replaced it) -> compare **stored** columns exactly (everything except `age_minutes` and `is_stale`, which change with the clock; compare `is_provisional` to its definition from `rating_basis`/`config_version`).
Record the four-way table. A later hourly run replaces `latest_rating`, so do the comparison right after the run, or compare against `city_rating?run_id=eq.<id>`.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `anon` / `service_role` JWT keys, `Authorization: Bearer` | `sb_publishable_...` / `sb_secret_...`, `apikey` header only | legacy keys deprecated "by the end of 2026" | Examples use the new names |
| OpenAPI at `/rest/v1/` with the anon key | Secret key only | existing projects 2026-04-08 | The repo doc is the contract |
| Default `select/insert/update/delete` grants on new `public` tables | Opt-in exposure; explicit grants required | new projects 2026-05-30; existing projects 2026-10-30 (existing tables keep grants) | Migration grants explicitly; re-check on or after 10-31 |
| Views bypass RLS (definer) | `security_invoker = true` (Postgres 15+) | Postgres 15 | Use it |
| supabase-js on Node 18/20 | supabase-js >= 2.110 needs Node >= 22 | Node 20 EOL 2026-04-30 | Local example runner needs Node 22+ |
| Private repository, Actions minutes budget | Public repository, free hosted-runner minutes | 2026-10-24/25 (05-06) | Anything committed is world-readable (D-10); minutes no longer limit probes |

**Deprecated/outdated:** `anon`-key OpenAPI; assuming grants by default; `datetime.fromisoformat` for arbitrary Postgres timestamps on Python < 3.11; the 06-01 27-column list; a soak peak age measured from `computed_at`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | (Resolved 2026-10-25: Phase 4's table names and constraints were read from the migration; no longer assumed.) | — | — |
| A2 | (Resolved: `run_id` is `GITHUB_RUN_ID` and `first_written_at` is immutable per the migration comments and `supabase_store.run_context`.) | — | — |
| A3 | (Resolved: `valid_time` is the hour-truncated UTC slot of the run window end.) | — | — |
| A4 | Supabase default DB time zone is UTC, so timestamps come back as `+00:00` | Pitfall 3 | Parsing handles any offset (helper does) |
| A5 | Hosted PostgREST behaves like local 16.4 for 401 vs 403 on 42501, `PT503` mapping, schema reload, `Prefer`/`Range` | Pitfalls 1, 6, 7, examples | E2E-03 accepts 401 or 403; other differences surface at the first live run |
| A6 | A publishable key through the Supabase gateway maps to `anon` and works with `apikey` alone | Pitfall 5 | Examples fail until adjusted; the live run exercises them |
| A7 | `https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm` works as an ESM import (not used in the refreshed example) | supabase-js | Use the documented UMD tag |
| A8 | `User-Agent` is harmless for Python urllib on Supabase | Python example | None |
| A9 | PSS/E's bundled Python is >= 3.7 with TLS 1.2 + SNI | Python example | Fails on 2.7 (then a follow-up per D-11) |
| A10 | Supabase documents no Data API request-rate limit found; keep polling at >= 30-60 s | Security | Dashboard polling could hit a limit |
| A11 | Supabase migrations trigger a PostgREST schema reload automatically | Pitfall 7 | `notify pgrst, 'reload schema'` covers it |
| A12 | New Supabase projects run Postgres >= 15 | Pattern 1 | View creation errors immediately |
| A13 | (Resolved: the repository is public; Actions minutes are free.) | — | — |
| A14 | The word-based `is_provisional` rule is acceptable to the owner; Phase 7's label lift will change both `rating_basis` and `config_version` so neither contains "provisional" (or the view expression is updated in a new migration) | Pattern 1c, Pitfall 11 | `is_provisional` stays true after GO (safe direction) or a consumer reads a lifted label wrongly |
| A15 | `create or replace view` can append columns but not rename/reorder/drop them | Pattern 1 | Contract evolution needs a drop-and-recreate (breaks readers); documented PostgreSQL behaviour, not run here |
| A16 | cron-job.org counts "failures" for `onFailureCount` as consecutive, and an HTTP 503 counts as a failed execution | Pattern 4 | The email fires on non-consecutive failures, or not at all on a 503; the alarm drill proves both |
| A17 | cron-job.org's "fails more than 25 times" auto-disable counts consecutive failures | Pitfall 13 | Alarm disabled sooner or never; `onDisable` email covers both |
| A18 | Supabase's 2026-10-30 rollout leaves existing tables' grants and the new view/function grants unchanged | Pitfall 2, 17 | Reads break or writes open after 10-30; the re-check on or after 10-31 detects it |
| A19 | Supabase project references are 20 lowercase letters (basis of the secret-scan host pattern) | Secret scan | The pattern misses an unusual reference; the owner-local env test still catches the real one |
| A20 | The `pg_cron` job runs as a role that can read `latest_rating` and write `ops.freshness_log`; `pg_cron` itself not run locally | `ops.log_freshness` | The first scheduled run fails; the short probe smoke check detects it |
| A21 | Python 3.7 itself cannot be run locally; the example's 3.7 compatibility rests on the `feature_version=(3,7)` syntax gate and the stdlib-API review | Python example | An API newer than 3.7 slips in; the oldest real run is 3.9.6 (optionally 3.8 via a downloaded interpreter) |
| A22 | PostgREST accepts a repeated filter on one column (`valid_time=gte.X&valid_time=lt.Y`) in the curl range example | curl | Use `and=(valid_time.gte.X,valid_time.lt.Y)` instead |
| A23 | Peak age is about 67-70 min and write lag about 7-10 min (one measured run) | Pattern 3 | The dry soak replaces it with measurements |

## Open Questions

1. **D-03 names the wrong label prefix.** CONTEXT.md says live rows start with `PROVISIONAL (OD-5)`; the code writes the "Per-conductor amperes ..." text for live rows and the `PROVISIONAL (OD-5)` prefix only for backfill rows.
   - What we know: verified in `config.py`, `supabase_load_backfill.py` and the schema doc; a prefix test is false on live rows.
   - What's unclear: whether the owner accepts the word-based rule (inside "Claude's Discretion" for the exact SQL) or wants a Phase 4 follow-up (a stored boolean).
   - Recommendation: use the word-based rule plus the drift-guard test; tell the owner in plain English; record the Phase 7 hand-off (lift both strings).
2. **Does the owner want the dry soak to double as Phase 5's 24 h check?** `05-08` runs `dlr_live_window_check.py` over 24 h; the dry-soak report reuses its verdicts. Recommendation: produce both from one run of the new mode at/after 05-08.
3. **PSS/E's Python and TLS.** Sources conflict (PSS/E 35 release notes: Python 3.7; blogs: 3.9; nothing for 36) `[CITED: scribd copy of PSS/E release notes, via search; LOW]`. Send the question; a "2.7" answer is a follow-up (D-11).
4. **Supabase tier / project pausing and rate limits** are not confirmed in official pages. Hourly writes keep a Free project active; check the plan before the soak.
5. **Is a snapshot `openapi.json` wanted** for Software-team codegen (owner, secret key)? Optional.
6. **Does cron-job.org's console word "failures" as consecutive?** Confirm at alarm setup (A16); the drill proves the behaviour.
7. **Should `supabase_smoke.py` also check `public.latest_rating`?** Small additive change (`to_regclass` guard) or leave it and rely on `verify_exposure.sql`. Recommendation: leave the smoke unchanged (it is Phase 4's frozen check, T-04-22 names it) and rely on `verify_exposure.sql` for the view.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Supabase project (Phases 4-5) | All live steps | Live (Phase 5 hourly since 2026-10-25T00:05Z) | — | Offline build first (D-06); live steps wait for 05-08 |
| `curl` | Examples, E2E-03 | ✓ | 8.7.1 | — |
| Python 3, oldest local | PSS/E example (D-11) | ✓ | **3.9.6** `/usr/bin/python3` (Xcode CLT; LibreSSL 2.8.3) | — |
| Python 3.10 | Example check | ✓ | 3.10.21 `~/.local/share/uv/python/cpython-3.10-macos-aarch64-none` | — |
| Python 3.12 / 3.14 | Repo test runs | ✓ | 3.12.13 (Homebrew and `.venv`), 3.14.6 (Homebrew) | — |
| Python 3.7 / 3.8 | Strict D-11 check | ✗ | `uv python list --all-versions` offers 3.8.x (e.g. 3.8.20) as download only; no 3.7 build is offered | Syntax gate `ast.parse(feature_version=(3, 7))` + run on 3.9.6; optionally `uv python install 3.8` (a download, so an owner-approved step) |
| Node.js / npm | supabase-js example | ✓ | Node 26.9.0 (supabase-js 2.118.0 needs >= 22) | Browser CDN form |
| `gh` CLI | Run correlation, deploy classification | ✓ | present | REST via `curl` + token |
| `psql` / `initdb` / `pg_ctl` | Local-Postgres tests | ✓ | Homebrew PostgreSQL 16 (16.14) and 18 | Supabase SQL editor for live runs |
| PostgREST binary | Local REST emulation | ✗ (the 2026-10-19 binary is no longer present) | — | Not needed for the plan: tests use `fake_postgrest.py` and local SQL; real PostgREST behaviour is exercised at the live run |
| `pg_cron` / `pg_net` | Soak log | not testable locally | Supabase-provided | Run `ops.log_freshness()` by hand to test the function body |
| cron-job.org account and console | Alarm, E2E-01 | owner-held | — | Owner performs the console steps |
| `uv` | Optional old-interpreter download | ✓ | `/opt/homebrew/bin/uv` | — |

**Missing dependencies with no fallback:** none for the offline build. Live steps need 05-08 sign-off (D-06).
**Missing dependencies with fallback:** Python 3.7 (syntax gate plus 3.9.6), local PostgREST (fake + live run), `pg_cron` locally.

**Timeline check (all UTC).** Window start 2026-10-25T00:05Z. 05-08's precondition is at least 25 h after the window start: earliest 2026-10-26T01:05Z. Then: apply migration + live read/hidden/write checks (06-02), schedule `pg_cron` + create the alarm + short smoke (about 45 min), dry-soak report and review, then the 72 h clock at G. To end by 2026-10-30T00:00Z (D-09) G must be no later than 2026-10-27T00:00Z; the earliest G is roughly 2026-10-26T04:00Z, so the soak would end about 2026-10-29T04:00Z. If 05-08 slips past about 10-27 the 72 h window necessarily ends after 10-30 and the 10-31 re-check should then be run after the soak as well. The 2026-11-01 Phase 7 target and the US clock change (2026-11-01) fall after the soak at the earliest start; neither affects an every-hour or every-15-minute UTC schedule.

## Validation Architecture

`workflow.nyquist_validation` is not set in `.planning/config.json` or the workstream `config.json` (absent = enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (repo default; `.venv/bin/python -m pytest -q -p no:cacheprovider`) for offline tests; live checks are stdlib scripts/SQL run by the owner |
| Config file | `/Users/aphan/Senior_Design/pytest.ini` — `pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py` `[VERIFIED: pytest.ini]` |
| Quick run command | `.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/e2e_readonly_test.py backend/tests/e2e_soak_report_test.py backend/tests/example_read_ratings_test.py backend/tests/secret_scan_test.py` |
| Local-Postgres run | `DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs backend/tests/expose_migration_test.py` (Phase 4's convention; skips otherwise; fails if set but binaries missing) |
| Full suite command | `.venv/bin/python -m pytest -q -p no:cacheprovider` |

Live verification needs `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (and `SUPABASE_DB_URL` for owner-side SQL) as environment variables, never committed, never from `.env` inside tests. Offline tests run with no network and no keys.

### What each check proves (plain English, for the owner)
| Check | In plain English |
|---|---|
| View column drift guard | "The columns the dashboard and PSS/E will code against are exactly the list in the documentation, in order." |
| `is_provisional` with the real labels | "A live row carrying today's real label is flagged provisional, and a row with a lifted label is flagged final." |
| `age_minutes` / `is_stale` boundary | "A rating is called old only when it is more than 90 whole minutes old, and the number shown never contradicts the flag." |
| anon read of `latest_rating` | "A person with only the public key sees exactly one current rating per city." |
| anon cannot write (privilege and snapshot) | "Trying to add, change or delete data with the public key is refused, and the data afterwards is identical." |
| Invoker view drops to 0 rows without the policy | "The view really obeys the table's access rules; it is not a back door." |
| Hidden tables | "The private run log and the soak log cannot be read with the public key." |
| Dry soak | "The hours already recorded show each hourly rating lands within about N minutes, and the oldest the 'current' rating ever got was M minutes, inside the 90-minute limit." |
| 72 h soak | "For three days the current rating for each city was never more than 90 minutes old, or each exception has a stated cause." |
| Alarm drill | "If a rating goes stale, the owner gets an email within about two hours, and another when it recovers." |
| Examples | "The three code samples work as written when the two environment values are supplied." |
| Secret scan | "No project address or public key is saved anywhere in the repository." |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| API-01 | View columns equal the migration's list, 34 in order (drift guard vs `LATEST_COLUMNS`); every stored column exists in `city_rating` | offline text | `pytest backend/tests/expose_migration_test.py -k columns` | ❌ Wave 0 |
| API-01 | anon reads one newest row per city; `reloptions` has `security_invoker`; policy dropped -> 0 rows | local PG | `DLR_TEST_PG_AUTOSTART=1 pytest ... expose_migration_test.py` | ❌ Wave 0 |
| API-01 | `is_provisional` true for the real `config.RATING_BASIS` + `config.RATING_CONFIG_VERSION` and a real-shaped backfill label; false for a synthetic lifted pair | local PG (seed rows with real strings from `config` / `supabase_load_backfill.backfill_rating_basis`) | same | ❌ Wave 0 |
| API-01 | In one transaction, `assert_fresh(age_minutes)` passes and `assert_fresh(age_minutes - 1)` raises PT503; `is_stale` equals `age_minutes > 90` | local PG | same | ❌ Wave 0 |
| API-01 | `verify_exposure.sql` all-true; grants SELECT-only on two objects; writes 42501; other public tables, `pipeline_run` and `ops` unreadable | local PG + live SQL | same; owner pastes the live result | ❌ Wave 0 |
| API-02 | Each example lists four cities and pages 2,500 rows; Python example parses fractional timestamps; stdlib-only (AST import check); syntax parses under `feature_version=(3,7)`; runs on `/usr/bin/python3` (3.9.6) and the venv (3.12) when present | offline (in-process fake HTTP server + subprocess) | `pytest backend/tests/example_read_ratings_test.py` | ❌ Wave 0 |
| API-02 | Examples contain no project URL or key and read both environment variables | offline text + secret scan | `pytest backend/tests/secret_scan_test.py` | ✅ (extend) |
| API-02 | Examples run as written against the real project | live smoke (owner, after 06-02) | `bash docs/integration/examples/curl.sh && node docs/integration/examples/supabase_js.mjs && python3 -I docs/integration/examples/read_ratings.py` | ❌ Wave 0 |
| E2E-01 | trace joins cron-job.org execution -> run -> rows -> REST on stored columns; mismatch detected; computed columns excluded | unit + live | `pytest ...::test_trace_compare_*`; live `python backend/e2e_trace.py --run-id <id>` | ❌ Wave 0 |
| E2E-02 | dry soak: write lag, peak age, slot verdicts, exit codes (fixtures: normal, missing slot, OD-7 rewrite, backfill excluded) | unit | `pytest backend/tests/e2e_soak_report_test.py -k dry` | ❌ Wave 0 |
| E2E-02 | soak report: probe gaps (> 10 min between probes), write-based breaches, trailing age, derived deploy annotations (pipeline_version / fingerprint / model-hash changes; docs-only commits classified "no runtime change"), manual annotations merged, unexplained breach -> non-zero exit | unit | `pytest ...e2e_soak_report_test.py -k soak` | ❌ Wave 0 |
| E2E-02 | `log_freshness`: breach equals `age_seconds > 5400`; missing city logs a breach | local PG | `DLR_TEST_PG_AUTOSTART=1 pytest ... soak_log_migration_test.py` | ❌ Wave 0 |
| E2E-02 | alarm responses: `rpc/assert_fresh` 200 fresh / 503 stale or missing | local PG + live | local: `assert_fresh` tests; live: `curl -s -o /dev/null -w '%{http_code}' ...` | ❌ Wave 0 |
| E2E-03 | anon INSERT/UPSERT/PATCH/DELETE rejected (401/403), data unchanged; any 2xx write fails the check; URL and key never in output | unit + live | `pytest ...e2e_readonly_test.py`; live `python backend/e2e_verify_readonly.py --check-writes` | ❌ Wave 0 |
| D-10 | Secret scan flags a planted project host, pooler user with a 20-character reference and publishable key; ignores `<ref>` placeholders; env-gated owner test skips when unset | offline | `pytest backend/tests/secret_scan_test.py` | ✅ (extend) |
| D-09 | Post-10-30 re-check script/runbook lists read, hidden, write, `verify_exposure.sql`, smoke `consumers_cannot_write`, on or after 2026-10-31 | doc + live (owner) | runbook step list; `gh workflow run supabase_smoke.yml --ref main` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** the quick run command above.
- **Per wave merge:** full suite plus the local-Postgres run.
- **Phase gate:** full suite green; live read/hidden/write checks, example smoke, trace table recorded; dry-soak report reviewed; 72 h soak report with zero unexplained breaches; alarm drill done; re-check on or after 2026-10-31 recorded; before `/gsd-verify-work`.

### Soak flow validation (offline build, then live)
1. Offline (D-06, now): migration + local-PG tests, REST client and checks, soak report in both modes against fixtures, examples tested against the in-process fake, secret-scan extension.
2. After 05-08: owner applies the migration; live read/hidden/write checks; owner schedules the 5-minute log, creates the alarm (and the drill), runs the **short probe smoke check** (recommended: yes) before the clock.
3. Dry-soak report (existing rows) reviewed by the owner.
4. 72 h clock at G; weekly nothing to do; export; breach explanation; owner sign-off; unschedule the soak job; alarm stays.
5. On or after 2026-10-31: the permission re-check.
**Probe smoke check (recommendation: yes, about 30-45 min).** A broken probe discovered at hour 40 would force a restart of the 72 h clock. Pass criteria: `pg_cron` ran the job at least 3 times in a row (`cron.job_run_details` status `succeeded`, `ops.freshness_log` has 4 rows per probe), the alarm executed at least 2 times with HTTP 200 in the console, and the alarm drill produced a failure email and a recovery email. It does not extend the soak window (the 72 h window starts after it).

### Wave 0 Gaps
- [ ] `backend/tests/expose_migration_test.py`, `backend/tests/local_pg.py` (34-column contract, real-label `is_provisional`, boundary test, grants)
- [ ] `backend/tests/e2e_readonly_test.py`, `backend/tests/fake_postgrest.py`, `backend/supabase_rest.py` (with URL/key redaction), `backend/e2e_verify_readonly.py`
- [ ] `backend/e2e_soak_report.py` (`--mode dry|soak`) and `backend/tests/e2e_soak_report_test.py`; `supabase/migrations/<ts>_soak_freshness_log.sql`; `supabase/ops/soak_pg_cron.sql`; `backend/e2e_trace.py`
- [ ] `docs/integration/rest-api.md`, `docs/integration/examples/{curl.sh,supabase_js.mjs,read_ratings.py}`, `backend/tests/example_read_ratings_test.py`
- [ ] Extend `backend/tests/secret_scan_test.py` (host, pooler user, publishable key; env-gated owner test)
- [ ] Runbook sections: alarm (permanent, how to pause, what to do when it fires: check `pipeline_run`, the Actions history and `latest_rating.is_stale`; pause the pipeline => pause the alarm), monitoring, 10-31 re-check
- [ ] Credentials via environment only; first live run of all examples against the real project (publishable-key path unverified)

## Security Domain

`security_enforcement` is not set to `false` in either `.planning/config.json` (absent = enabled).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (API key as the only credential) | Publishable key via `apikey` header; no user auth; secret key never in consumers; the verification tools refuse a secret/service-role key |
| V3 Session Management | no | Stateless REST |
| V4 Access Control | yes | Postgres GRANT/REVOKE + RLS; `anon` SELECT-only; `ops` schema unexposed; `assert_fresh` invoker with explicit EXECUTE |
| V5 Input Validation | yes (limited) | Consumers send query strings; PostgREST parameterizes; RPC takes a bounded integer (22023 otherwise); soak SQL uses bound parameters |
| V6 Cryptography | yes | HTTPS/TLS only; no custom crypto; key rotation per Supabase docs |
| V8/V13 API & data protection | yes | No documented Data API rate limit found; keep polling modest; data deliberately public to key holders (OD-6) |
| V14 Configuration / secrets in source | yes (new, public repo) | D-10: no project URL, reference or publishable key in tracked files; pattern scan in CI plus owner-local env-gated scan; redaction in tools (Pitfall 15) |

### Known Threat Patterns for Supabase PostgREST + RLS

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Anon write via exposed table with default grants | Tampering | Revoke sweep; RLS with no write policies; E2E-03 asserts status and unchanged data; re-check on or after 2026-10-31 |
| View bypasses RLS (definer view) | Information disclosure | `security_invoker = true`; test drops the read policy and expects 0 rows |
| Derived flag wrong (`is_provisional` false on provisional data) | Information disclosure / integrity of meaning | Word-based rule + drift-guard test on the real labels (Pitfall 11) |
| Secret/service key leaks to client or repo | Elevation of privilege | Secret only in Actions secrets; secret keys 401 from browsers; secret scan; rotate if exposed |
| Project URL or publishable key committed to a public repo | Information disclosure (benign key, but invites scraper traffic and ties the project to the repo) | Env-only examples; pattern scan + owner-local scan; tools redact |
| Over-broad `using (true)` select policy | Information disclosure | Accepted by OD-6, recorded in the doc |
| SECURITY DEFINER functions / RPC abuse | Elevation of privilege | `assert_fresh` is security invoker, read-only, EXECUTE granted explicitly to anon/authenticated and revoked from `public`; `ops.log_freshness` has no anon access |
| Schema disclosure via OpenAPI | Information disclosure | Supabase blocks the anon key from the spec endpoint |
| Scraping / abuse of public key (DoS) | Denial of service | `latest_rating` is 4 rows; 1000-row cap; `pgrst.db_pre_request` hook available |
| Soak/ops data exposed | Information disclosure | `ops` unexposed, all privileges revoked; `check_hidden` and `verify_exposure.sql` verify |
| Alarm silently disabled by cron-job.org after >25 failures | Denial of monitoring | `onDisable` email; runbook pause/resume rule (Pitfall 13) |
| Alarm job holds the project URL and key | Information disclosure | They live only in the owner's cron-job.org account; alarm emails go to the owner only (D-15) |

## Sources

### Primary (HIGH confidence)
- Local verification 2026-10-25: PostgreSQL 16.14 with the real Phase 4 migrations applied (view expressions, boundary table, anon invoker read, peak-age and change-point SQL on synthetic rows); CPython 3.9.6, 3.10.21, 3.12.13 (timestamp helper, example against an in-process fake PostgREST with a 1000-row cap, `ast` feature-version gate); `config.RATING_BASIS` read through the repo's own `config` module; `uv python list --all-versions`.
- Local verification 2026-10-19: PostgreSQL 16.14 + PostgREST 16.4 (view + RLS behavior, anon write status codes, zero-row silent writes, `PT503` RPC, singular-object 406, `DISTINCT ON` plans, supabase-js 2.118.0).
- Repo files read this session: `06-CONTEXT.md`, `06-RESEARCH.md` (prior), `06-01-PLAN.md`, `COVERAGE.md`, `supabase/migrations/20261019000000_create_city_rating.sql`, `supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql`, `docs/data-science/schema/city_rating_v1.md`, `backend/config.py` (240-279), `backend/supabase_store.py` (204-336, 374-403), `backend/supabase_load_backfill.py` (140-165), `backend/dlr_live_window_check.py`, `backend/supabase_smoke.py`, `backend/live_run_log.py` (header), `backend/tests/secret_scan_test.py`, `.github/workflows/dlr_live.yml`, `.github/workflows/supabase_smoke.yml`, `docs/data-science/decisions/dlr_live_runbook.md` (sections 2, 6, 12), `docs/data-science/decisions/shadow_early_decision_options.md` (head), `05-08-PLAN.md`, ROADMAP.md Phase 6, STATE.md (T-04-22 line), `pytest.ini`.
- https://supabase.com/docs/guides/database/postgres/row-level-security — views and RLS, `security_invoker`, `to anon using (true)`
- https://supabase.com/docs/guides/api/api-keys — publishable/secret keys, `apikey` header, legacy deprecation
- https://supabase.com/docs/guides/api/securing-your-api and https://supabase.com/docs/guides/api/hardening-data-api — grants, "New functions are callable by every role", `alter default privileges for role postgres revoke execute on functions from public`
- https://github.com/orgs/supabase/discussions/45329 and https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically — default-grant timeline (2026-10-30 for existing projects; existing tables keep grants per maintainers), opt-in SQL, sequences, functions
- https://supabase.com/changelog/42949-breaking-change-removing-access-to-openapi-spec-via-the-anon-key — OpenAPI via anon removed
- https://docs.postgrest.org/en/stable/references/errors.html, /references/api/pagination_count.html — 42501 mapping, `PTxyz`, `limit`/`offset`, `Range` (inclusive), `Prefer: count=exact`
- https://supabase.com/docs/reference/javascript/range — `.range(from, to)` 0-based inclusive
- https://docs.cron-job.org/rest-api.html — `JobNotificationSettings` (`onFailure`, `onFailureCount`, `onSuccess`, `onDisable`), history fields, schedule timezone
- https://cron-job.org/en/faq/ — last 50 executions, bodies kept 2 days, 30 s timeout, once-per-minute minimum, auto-disable "more than 25 times", recovery email
- https://supabase.com/docs/guides/cron/quickstart and /cron — `cron.schedule`, `cron.unschedule`, `cron.job_run_details` not cleaned up automatically
- `npm view @supabase/supabase-js` (2.118.0, engines.node >=22.0.0, modified 2026-10-22) and `gsd package-legitimacy check` (SUS: too-new)

### Secondary (MEDIUM confidence)
- https://supabase.com/docs/guides/database/extensions/pg_net — response retention 6 h (not used by this plan)
- https://raw.githubusercontent.com/supabase/supabase-js/master/README.md — Node support policy
- Web search summaries on the Data API "Max rows" default (Supabase client reference pages for Dart/C#; GitHub discussion 3765)

### Tertiary (LOW confidence)
- PSS/E Python version (Scribd copy of release notes vs blogs); third-party Supabase rate-limit numbers

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH for PostgREST/RLS/grants and the example code (run locally); MEDIUM for hosted-Supabase and cron-job.org specifics (docs only)
- Architecture: HIGH for the view/grant/soak design (SQL exercised on the real migrations); MEDIUM for the alarm (account behaviour unverified until the drill) and `pg_cron` (not run locally)
- Pitfalls: HIGH for 1, 3, 4 (view comments), 7, 11, 12, 14 (verified); MEDIUM for 2, 5, 6, 13, 15-17 (documented or reasoned); 9 is measurable from existing rows

**Research date:** 2026-10-19; refreshed 2026-10-25
**Valid until:** 2026-10-30 for grant/default behavior (platform change lands that day; re-check on or after 2026-10-31); otherwise about 30 days. Supabase key, OpenAPI and cron-job.org policies move; re-verify before executing live steps.
