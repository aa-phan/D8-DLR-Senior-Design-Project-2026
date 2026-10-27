# Plan 06-10 Pre-flight: monitoring on, alarm drill, dry soak

Written 2026-10-27 by the executor. Nothing in this note or in the rehearsal touched the live Supabase project: no job scheduled, no `.env` read, no network call to the project, nothing pushed. It holds no project URL, host, reference or key.

## 1. Gate and rehearsal

**Gate.** `06-09-SUMMARY.md` records both Phase 6 migrations applied live, `verify_exposure.sql` 17 of 17 ok and `verify_monitoring.sql` 7 of 7 ok (so `ops.freshness_log` and `ops.log_freshness()` exist on the live project and the public key cannot read them). Nothing is scheduled yet: `soak_freshness_log` only creates the function, scheduling is Step 2 below.

**Local rehearsal.** Run on a throwaway local Postgres, offline:

```
DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs \
  backend/tests/soak_log_migration_test.py backend/tests/e2e_soak_report_test.py \
  backend/tests/monitoring_runbook_test.py
```

Result: **87 passed, 0 skipped, 0 failed.** In plain English:

- `soak_log_migration_test.py`: the five-minute log writes four rows per probe (one per city) with the same 90-minute rule consumers see; `soak_probe_smoke.sql` returns ok for a healthy log (run against a stand-in for pg_cron) and each of its four checks can fail; the owner scripts schedule once, re-running changes nothing, and unscheduling leaves zero jobs.
- `e2e_soak_report_test.py`: the export (read-only session, nothing written on failure, no URL or key in any file) and the dry report (write lag from `first_written_at`, peak age, slot verdicts, exit codes 0, 1, 2) behave correctly through a fake connection.
- `monitoring_runbook_test.py`: runbook sections 14 and 15 state the alarm settings and the soak commands as built.

The two small runner commands used below (one read-only, one that writes) were also tried against a throwaway local database: the read-only one refused a `create table`, the other one ran it, and a failed connection printed only the error class, never the address.

## 2. What you are about to do, in plain English

| Step | What it proves | Changes the live project? |
|---|---|---|
| Schedule the five-minute log | the database starts writing down every five minutes how old each city's current rating is | **Yes**: creates one pg_cron job `dlr-soak-freshness` |
| Create the permanent alarm on cron-job.org | if a rating goes stale you get an email within about two hours, and another when it recovers | No change to the project; adds a job in your cron-job.org account (calls a read-only check) |
| Drill the alarm | the email path really works (failure email, then recovery email), then the drill job is deleted | No change to the project; a temporary cron-job.org job |
| Smoke check (about 20 minutes after Step 2) | the five-minute log is running and writing four rows each time | No (read only) |
| Dry-soak export | the hours already recorded show how late each hourly rating lands and the worst age the "current" rating reached | No (read only) |

Never touch the hourly dispatch job or the Shadow Collection job on cron-job.org. Never put the secret key or any database URL into cron-job.org (only the project URL and the publishable key go there).

## 3. Timeline (D-09) and what it means for you

D-09 wanted the 72 h clock to start by **2026-10-27T00:00Z** so the window would end before Supabase's default-permission change on **2026-10-30**. That time has passed: 06-09's live check ran at about 01:18Z on 2026-10-27, and this pre-flight is written after 01:20Z.

What follows from that:

- The soak window runs exactly 72 hours from G, so it **ends at G + 72 h, which is later than 2026-10-30T00:00Z**. It ends later by exactly the amount G is after 2026-10-27T00:00Z. The best case is G of roughly 02:30 to 03:00Z on 2026-10-27, which is an end of about 02:30 to 03:00Z on 2026-10-30, two and a half to three hours into the new regime. Every further hour you take before saying "go" moves the end one hour later.
- The window is **never lengthened to cover 2026-10-30** and never shortened below 72 h (D-09). So the last few hours of the soak run on the far side of the change, and the soak still counts as a normal 72 h window.
- The change should not matter to us: our permissions are written out explicitly (06-09 verified 17 of 17), and the change only affects the default permissions of new tables. If it did affect us, it would show up as a breach in the soak or an alarm email.
- The permission re-check (section 16 of the runbook, plan 06-13) is a separate step run **on or after 2026-10-31**, after the window. It is what proves the change did nothing to us.
- Do not skip the 20-minute smoke wait or the dry-soak review to shave an hour: an unproven probe found at hour 40 would force a full restart, which costs far more than the few hours at stake.

G is not chosen by the executor or by you after seeing later data: it is your "go" reply time rounded up to the next 5-minute boundary (UTC), and it must be after the dry-soak export's `--until` and after the smoke check. The window therefore never overlaps the dry-soak data.

## 4. Owner steps, in order

All commands run from `/Users/aphan/Senior_Design`. In Claude Code you can prefix each with `! `. They load the database address from your git-ignored `.env` inside the process; nothing prints it. `.env` has no `SUPABASE_URL` or `SUPABASE_PUBLISHABLE_KEY`: you read those from the Supabase dashboard (Project Settings, Data API / API keys) and type them into cron-job.org only, never into chat.

### Step 1. Enable Cron (changes the live project)

Supabase Dashboard, Integrations, Cron: enable it.

### Step 2. Schedule the five-minute log (changes the live project)

Option A, SQL editor (simplest): open `supabase/ops/soak_cron_schedule.sql`, paste it into the SQL editor and run it.

Option B, from your terminal (this one **writes** to the live project; the file contains exactly one `cron.schedule` call and one `select`):

```
.venv/bin/python -c "import sys,psycopg;from dotenv import dotenv_values as d;sys.excepthook=lambda t,v,b:print('FAILED:',t.__name__,getattr(getattr(v,'diag',None),'message_primary',None) or '(no server message)');c=psycopg.connect(d('.env')['SUPABASE_ADMIN_DB_URL'],autocommit=True,prepare_threshold=None,connect_timeout=15);k=c.execute(open(sys.argv[1]).read());exec('while 1:\n if k.description:print([x.name for x in k.description]);[print(r) for r in k.fetchall()]\n if not k.nextset():break')" supabase/ops/soak_cron_schedule.sql
```

Expected: one `cron.job` row with `jobname` = `dlr-soak-freshness`, `schedule` = `*/5 * * * *`, `command` = `select ops.log_freshness()`, `active` = true. Running it twice is safe (same job, no copy). **Note the time you ran it (call it T0, UTC).**

### Step 3. Create the permanent alarm on cron-job.org

Create a NEW job. Settings (from runbook section 14; D-14, D-15):

| Setting | Value |
|---|---|
| Title | `DLR freshness alarm` |
| URL | `<project URL>/rest/v1/rpc/assert_fresh` |
| Method | GET |
| Request header | `apikey: <publishable key>` (the publishable key only, never the secret key) |
| Schedule | every 15 minutes, time zone UTC |
| Timeout | default (30 s) |
| Notify on failure | after 2 failures |
| Notify on success after a failure | on (recovery email) |
| Notify when the job is disabled | on |
| Emails go to | your own cron-job.org account only |

Leave the hourly dispatch job and the Shadow Collection job untouched. Expect HTTP 200 on every execution (503 means a city is missing or stale).

### Step 4. Drill the alarm (temporary job, then delete it)

1. Create a temporary job `DLR freshness alarm drill`: same URL with `?max_age_minutes=0` on the end (that always answers 503), same `apikey` header, same three notification settings, every minute.
2. Wait for the **failure email** (it arrives after the second failure, a few minutes in). Note its time.
3. Edit the drill job's URL to end `?max_age_minutes=90` (always 200). Wait for the **recovery email**. Note its time.
4. Delete the drill job. The permanent alarm from Step 3 stays.

### Step 5. Export the dry soak (read only; do this while you wait for the smoke check)

Pick `--until` as the top of the current UTC hour (for example `2026-10-27T02:00:00Z` if it is between 02:00 and 03:00Z now). It must be in the past and at least 12 h after `--since`; the export starts at the Phase 5 window start:

```
.venv/bin/python -c "import os,sys;from dotenv import dotenv_values as d;e=d('.env');os.environ.setdefault('SUPABASE_DB_URL',e.get('SUPABASE_DB_URL') or e['SUPABASE_ADMIN_DB_URL']);sys.path.insert(0,'backend');import e2e_soak_report as m;sys.exit(m.main(sys.argv[1:]))" export --mode dry --since 2026-10-25T00:00:00Z --until <the current UTC hour, e.g. 2026-10-27T02:00:00Z> --out-dir .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/soak-data/dry
```

This is the same as `.venv/bin/python backend/e2e_soak_report.py export ...` from the runbook; the wrapper only lets it use `SUPABASE_ADMIN_DB_URL` when `.env` has no `SUPABASE_DB_URL`. The export opens a read-only session before its first query, and `gh` must be signed in (it is). Expect a line like `exported N live rows, M pipeline runs to ...` and four files in `soak-data/dry/`: `writes.csv`, `runs.csv`, `gh_runs.json`, `export_meta.json`. Do not commit them; the executor does that after the secret scan.

### Step 6. Smoke check (at least 20 minutes after T0; read only)

Option A: paste `supabase/ops/soak_probe_smoke.sql` into the SQL editor.

Option B, read-only from your terminal (refuses any write):

```
.venv/bin/python -c "import sys,psycopg;from dotenv import dotenv_values as d;sys.excepthook=lambda t,v,b:print('FAILED:',t.__name__,getattr(getattr(v,'diag',None),'message_primary',None) or '(no server message)');c=psycopg.connect(d('.env')['SUPABASE_ADMIN_DB_URL'],autocommit=True,prepare_threshold=None,connect_timeout=15);c.execute('set default_transaction_read_only = on');k=c.execute(open(sys.argv[1]).read());exec('while 1:\n if k.description:print([x.name for x in k.description]);[print(r) for r in k.fetchall()]\n if not k.nextset():break')" supabase/ops/soak_probe_smoke.sql
```

Pass criteria: four rows, every `ok` true:

| check_name | what ok = true means |
|---|---|
| `soak_job_active_every_5_minutes` | the job exists once, is on, every five minutes, calls the log |
| `last_three_runs_succeeded` | the database's own job history shows the last three runs succeeded |
| `last_three_probes_wrote_four_rows` | each of the last three probes wrote one row per city (4) |
| `no_breach_in_the_last_three_probes` | no city older than 90 minutes or missing in those probes |

If any row is false: stop, send me the table, do not start the clock. (Likely causes: the job runs as a role that cannot read `latest_rating` or write `ops.freshness_log`, or Cron is not enabled.)

### Step 7. Check the alarm history

In cron-job.org, open "DLR freshness alarm" history: at least **two executions with HTTP 200** (15 minutes apart, so about 30 minutes after you created it).

### Reply

Reply **"monitoring on"** with: the `cron.job` row from Step 2, the smoke-check table, the alarm's first statuses, the two drill email times (failure, recovery) and the export's `--until`. If anything failed, describe what failed instead.

What happens next: the executor checks the export, computes `06-DRY-SOAK-REPORT.md` with `--min-hours 12`, runs the secret scan and commits the evidence. You then review the report and answer **"go"** or **"no-go: <what must change>"** (plan 06-10, Task 3). Only that reply starts the 72 h clock.

## 5. Evidence checklist for the commit

- `soak-data/dry/` holds `writes.csv`, `runs.csv`, `gh_runs.json`, `export_meta.json` (export) and `report.json` (report); `export_meta.json` shows `since` 2026-10-25T00:00:00Z and a span of at least 12 h.
- `06-DRY-SOAK-REPORT.md` has a Context section (D-07 dry soak from existing rows, since and until, write lag measured from `first_written_at` with `computed_at` shown for information, the smoke table, the alarm's first executions, the drill email times, OD-4 fixed at 90 minutes) and a lag-statistics section.
- `backend/tests/secret_scan_test.py` passes with the evidence staged; no URL, host, project reference, key or database URL anywhere in it.
