# Phase 6: Exposure & E2E Verification - Context

**Gathered:** 2026-10-25
**Status:** Ready for planning (replan: the 7 plans of 2026-10-19 predate these decisions)

<domain>
## Phase Boundary

Consumers (Software team's dashboard, Power Systems' PSS/E scripts) can read current ratings for
every city at any time through a documented, read-only Supabase REST interface. The phase delivers:
the `latest_rating` view and SELECT-only anon exposure (API-01), the REST contract doc with three
working examples (API-02), an end-to-end trace from cron-job.org trigger to REST response (E2E-01),
a >= 72 h freshness soak with every breach explained (E2E-02), and proof that anon writes are
rejected (E2E-03).

Not in scope: changing the cadence, the grace period or the breach rule (OD-1, OD-4 fixed); a
custom API server; dashboard or PSS/E-side code; analysing rating values.

</domain>

<decisions>
## Implementation Decisions

### What changed since the 2026-10-19 plans (replan inputs)
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

### latest_rating contract
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
- **D-03:** The view adds an `is_provisional` boolean, true when the word "provisional"
  (case-insensitive) appears in `rating_basis` OR `config_version` (both NOT NULL), so consumers
  branch on a boolean and Phase 7's GO (REVAL-01) turns it false for new rows without a contract
  change. Revised 2026-10-25 after research: only backfill rows start with `PROVISIONAL (OD-5)`;
  live rows store `config.RATING_BASIS` ("Per-conductor amperes ... Values are provisional ...")
  and `config.RATING_CONFIG_VERSION` (`v1-provisional-2026-10-13`), so a prefix test would read
  every live row as final. A drift-guard test feeds the real `config.RATING_BASIS` and
  `config.RATING_CONFIG_VERSION` through the view and expects true. Phase 7's GO must remove the
  word from both strings. — **Reversibility:** one-way — part of the published column contract.
- **D-04:** `latest_rating` returns the newest row per city by `valid_time`, fallback rows
  included. The fallback is the value the system published and is safe by the owner's rule;
  consumers see `status = 'fallback'` and `fallback_gates` on it. Never skip to an older computed
  row.
- **D-05:** The column-comment rules, units, security_invoker view, revoke sweep plus SELECT-only
  grants and the LATEST_COLUMNS drift-guard test from 06-01 stay. The column list grows per
  D-01..D-03, and the docs table and LATEST_COLUMNS follow it.

### Soak timing and sequencing
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

### Public repo and examples
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

### Monitoring after the soak
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and decisions
- `.planning/workstreams/production-pipeline/ROADMAP.md` — Phase 6 goal and success criteria 1-4; cross-phase constraints (frozen shadow path, anti-peeking, explicit-path commits)
- `.planning/workstreams/production-pipeline/REQUIREMENTS.md` — API-01, API-02, E2E-01..03; owner decisions OD-1..OD-10 (OD-4 grace, OD-6 public history with explicit revokes, OD-9 failed city = run log only)
- `.planning/workstreams/production-pipeline/STATE.md` — Phase 4/5 decisions, carried items (T-04-22, IN-11), open AUSTIN fallback issue

### Existing Phase 6 work (to be revised, not discarded)
- `.planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-RESEARCH.md` — invoker view pattern, revoke/grant layout, Pitfalls 1-10 (RLS-only write blocking returns 200, 10-30 grant change, Python < 3.11 timestamps, 1000-row cap, 90-min budget)
- `.planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-0[1-7]-PLAN.md` — prior plans; their structure is reusable, but column list, dry soak, teardown, alarm and examples change per D-01..D-15
- `.planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/COVERAGE.md` — API capability integrate/opt-out decisions

### Schema and store (Phase 4)
- `supabase/migrations/20261019000000_create_city_rating.sql` — `city_rating` and `pipeline_run` definitions, RLS, existing revokes, `dlr_writer` grants
- `supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql` — UTC hour CHECK; applied migrations are pinned by sha256 and never edited
- `docs/data-science/schema/city_rating_v1.md` — consumer schema doc, units, `rating_basis` provisional label, DB-06 identity columns
- `backend/supabase_store.py` — connection, redaction (`redact`), `finite`, `file_sha256`

### Live pipeline (Phase 5)
- `.github/workflows/dlr_live.yml` — the hourly live workflow
- `backend/dlr_live_run.py`, `backend/dlr_live_window_check.py` — runner and slot verdicts (reuse for breach causes and the dry soak)
- `docs/data-science/decisions/dlr_live_runbook.md` — cron-job.org dispatch job, pause/cadence procedure; Phase 6 adds the alarm and monitoring sections
- `.planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-07-SUMMARY.md` — window start run id and fault-drill evidence
- `.planning/workstreams/production-pipeline/phases/05-scheduled-live-runs/05-08-PLAN.md` — the gate for anything live in Phase 6 (D-06)

### Consumer docs to update
- `docs/frontend/specs/api-contract.md` — dashboard team's API contract (point to the new REST doc)
- `docs/frontend/specs/F1-data-access-api.md` — dashboard data-access spec
- `docs/data-science/decisions/pss_e_handoff.md` — PSS/E hand-off (point to the new REST doc and the Python 3.7+ example)

### Phase 7 interaction
- `docs/data-science/decisions/shadow_early_decision_options.md` — what Phase 7 may deploy around 2026-11-01 (D-08)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/supabase_store.py`: `connect()` (UTC session, pooler), `redact()`, `finite`, `file_sha256`. Reuse for the independent SQL read in the E2E trace and for soak exports.
- `backend/dlr_live_window_check.py`: slot verdicts per run (counts a slot's rows by any run placed in it, so OD-7 overwrites don't fail a slot). Reuse for breach causes and the dry-soak report.
- `backend/supabase_smoke.py` and `.github/workflows/supabase_smoke.yml`: the existing `consumers_cannot_write` smoke, to be re-run after 10-30 (D-09).
- `backend/tests/secret_scan_test.py`: extend so the project URL/reference can never be committed (D-10).

### Established Patterns
- Migrations are additive and never edited once applied (sha256-pinned); Phase 6's exposure is a new migration sorting after all Phase 4/5 files.
- Every live action is an owner checkpoint; the executor builds and tests offline, never applies migrations, reads `.env` or pushes without approval.
- Tools print no URL, host or project reference; evidence JSON carries no credentials.
- Commit with explicit paths; ask before pushing anything that changes live CI.
- `load_dotenv()` only under `__main__`, so tests never read the owner's `.env`.

### Integration Points
- New migration on top of `public.city_rating` (view, index, `assert_fresh`, revoke sweep, SELECT grants, read policy).
- `ops` schema (unexposed) for the soak freshness log; pg_cron job inside Supabase.
- cron-job.org: a new alarm job beside the existing dispatch job (never modify the dispatch or shadow jobs).
- `docs/integration/rest-api.md` (new) as the consumer contract; the docs above point to it.

</code_context>

<specifics>
## Specific Ideas

- The owner wants plain-English explanations of what each verification proves, not internal codes.
- Falling back to the static rating is safe by the owner's rule. AUSTIN's high fallback rate is not a Phase 6 breach: a fallback row is still a fresh row.
- The dashboard and PSS/E code against the view's column names, so the column list is the costly decision. Settle it before the migration goes live.

</specifics>

<deferred>
## Deferred Ideas

- Python 2.7 support for the PSS/E example, only if Power Systems report a 2.7 interpreter.
- A team or shared alert address for the freshness alarm (owner-only for now).
- A permanent freshness history (5-minute log with a retention rule), not kept now.

</deferred>

---

*Phase: 06-exposure-e2e-verification*
*Context gathered: 2026-10-25*
