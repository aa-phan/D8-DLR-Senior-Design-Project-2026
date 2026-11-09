# Plan 06-12 Pre-flight: closing the 72 h soak

Written 2026-10-30 by the executor. Nothing in this note or in the rehearsal touched the live Supabase project: no `.env` read, no network call to the project, nothing scheduled or unscheduled, nothing pushed. It holds no project URL, host, reference or key.

## 1. Gate and rehearsal

**Gate.** `06-10-SUMMARY.md` records the owner decision **"go"** (reply 2026-10-27T03:34:58Z) and the window start **G = 2026-10-27T03:35:00Z**, which is at or after the reply and after the dry-soak export's `--until` (2026-10-27T02:00:00Z), so the window never overlaps the dry-soak data. The orchestrator's clock read 2026-10-30T03:41:11Z, which is at least G + 72 h, so the window can be exported now.

**Local rehearsal.** Run on a throwaway local Postgres, offline:

```
DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs \
  backend/tests/e2e_soak_report_test.py backend/tests/soak_log_migration_test.py
```

Result: **80 passed, 0 skipped, 0 failed, 0 errors.** In plain English: the soak export refuses to write anything to the database and never puts a URL or key in a file; the 72 h report finds each period in which a city's rating was older than 90 minutes from the rows themselves, derives a cause for each from Phase 5's run records, lists deploys from the data, prints owner annotations verbatim and exits 0 only when the window is at least 72 h and every breach and gap is explained; the five-minute log and its owner scripts (schedule once, unschedule to zero jobs) behave as built.

## 2. Window facts (D-09)

| Item | Value |
|---|---|
| G (from 06-10-SUMMARY.md) | **2026-10-27T03:35:00Z** |
| Window length | exactly 72 h |
| Earliest export time, G + 72 h = the export `--until` | **2026-10-30T03:35:00Z** |
| Ends before 2026-10-30T00:00Z? | **No.** It ends 3 h 35 min after that time. |

D-09 wanted the clock started by 2026-10-27T00:00Z so the window would end before Supabase's default-permission change on **2026-10-30**; that start was missed (06-10 records why). The window is **not lengthened and not shortened** to fix that: the last 3 h 35 min of the soak run on the far side of 2026-10-30, and the soak still counts as a normal 72 h window. The change affects only the default permissions of new tables; ours are written out explicitly (06-09: `verify_exposure.sql` 17 of 17 ok). If the change did affect us it would show up as a breach, an alarm email or a failed live check. The separate permission re-check (plan 06-13, runbook section 16) runs **on or after 2026-10-31**, after this window and after this plan.

## 3. What to record during and after the window (D-08)

- **Deploys are found by the report itself**, from the data: any slot where a city's pipeline version, config fingerprint, model hashes, forecast method or config version differs from its previous row, classified as model, config, workflow, code or no runtime change. Nobody has to write these down. If a deploy commit is not in my local clone the report says so; I run `git fetch origin` (read only) and report again.
- **Things the data cannot show** go into `soak-data/final/annotations.json` under `"events"` at Task 3, each with a time, what happened and your name: a cron-job.org edit, a pause of the hourly dispatch, a GitHub Actions or Supabase incident, a phone call that changed something. Task 2 asks you to list them when you reply; write down what you remember with its time.
- **Never pause or restart the soak for a deploy.** A breach that a deploy caused still counts and is explained like any other.
- **Alarm emails.** Task 2 also asks you to list every freshness-alarm email received during the window (failure or recovery) with its time, from your mailbox and the cron-job.org history of "DLR freshness alarm".
- I never write an annotation for you and never edit the exported data (T-06-41).

## 4. Task 2 command sheet (owner), G filled in

All commands run from `/Users/aphan/Senior_Design`. In Claude Code prefix each with `! `. Commands that need the database load the address from your git-ignored `.env` inside the process; nothing prints it. `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are not in `.env`: export them in **your own terminal only** (Terminal.app), never in chat; paste back redacted output.

### Step 1. Export the 72 h window (read only)

```
.venv/bin/python -c "import os,sys;from dotenv import dotenv_values as d;e=d('.env');os.environ.setdefault('SUPABASE_DB_URL',e.get('SUPABASE_DB_URL') or e['SUPABASE_ADMIN_DB_URL']);sys.path.insert(0,'backend');import e2e_soak_report as m;sys.exit(m.main(sys.argv[1:]))" export --mode soak --since 2026-10-27T03:35:00Z --until 2026-10-30T03:35:00Z --out-dir .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/soak-data/final
```

`--since` must be exactly `2026-10-27T03:35:00Z` and `--until` exactly `2026-10-30T03:35:00Z`. This is the same as `.venv/bin/python backend/e2e_soak_report.py export ...` from runbook section 15; the wrapper only lets it use `SUPABASE_ADMIN_DB_URL` when `.env` has no `SUPABASE_DB_URL`. The export opens a read-only session first; `gh` must be signed in. Expect a line like `exported N live rows, M pipeline runs ...` and five files in `soak-data/final/`: `writes.csv`, `runs.csv`, `gh_runs.json`, `probes.csv`, `export_meta.json`. Do not commit them; I do that after the secret scan.

### Step 2. End-of-soak database permission lists (read only)

Run each file with this runner (it refuses any write) or paste the file into the SQL editor:

```
.venv/bin/python -c "import sys,psycopg;from dotenv import dotenv_values as d;sys.excepthook=lambda t,v,b:print('FAILED:',t.__name__,getattr(getattr(v,'diag',None),'message_primary',None) or '(no server message)');c=psycopg.connect(d('.env')['SUPABASE_ADMIN_DB_URL'],autocommit=True,prepare_threshold=None,connect_timeout=15);c.execute('set default_transaction_read_only = on');k=c.execute(open(sys.argv[1]).read());exec('while 1:\n if k.description:print([x.name for x in k.description]);[print(r) for r in k.fetchall()]\n if not k.nextset():break')" supabase/ops/verify_exposure.sql
```

then the same command ending `supabase/ops/verify_monitoring.sql`. Every `ok` must be true. Copy both result tables. Expected: 17 of 17 and 7 of 7, as in 06-09.

### Step 3. Second live public-key check (your own terminal)

No backfill load and no manual re-run of a past slot may run during this step (the hourly run is harmless; it writes only the current slot). In **your own terminal**:

```
export SUPABASE_URL=<paste from dashboard>   SUPABASE_PUBLISHABLE_KEY=<paste from dashboard>
cd /Users/aphan/Senior_Design
PYTHONPATH=backend .venv/bin/python backend/e2e_verify_readonly.py --check-read --check-hidden --check-writes --json-out .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-12-live-checks.json
echo "exit code: $?"
```

Expect the last line `E2E READONLY OK` and exit code 0. The JSON file is redacted by the script (no URL, no key). Paste back the printed PASS/FAIL lines and the exit code.

### Step 4. Alarm emails and events

List every freshness-alarm email from the window (failure or recovery, with times) and any event worth recording (section 3).

### Step 5. Do NOT unschedule the pg_cron job yet

It is removed only after your sign-off in Task 3.

## 5. What I do after you reply "final exported" (Task 2 verification)

1. Check the five files in `soak-data/final/`, that `export_meta.json` has `since` = G exactly and a span of 72 h, and that `06-12-live-checks.json` exists with every check ok.
2. `git fetch origin` (read only), then `report --mode soak --min-hours 72` into `06-SOAK-REPORT.md` and `soak-data/final/report.json`. Exit 0 or 1 are recorded outcomes; exit 2 (bad input) stops me.
3. Add a Context section (G, window, OD-1/OD-4 unchanged, D-09 status, your alarm emails, lag statistics versus the dry soak), an End-of-soak checks section (both SQL tables; a per-attempt table comparing 06-12 with 06-09: attempt, 06-09 verdict and status, 06-12 verdict and status; any difference is a **discrepancy**, never treated as equivalent), and a "For the owner" list for each unexplained breach or gap. I write no annotation.
4. Secret scan, then commit with explicit paths. No push.

## 6. Evidence checklist for the Task 2 commit

- `soak-data/final/` holds `writes.csv`, `runs.csv`, `gh_runs.json`, `probes.csv`, `export_meta.json` and `report.json`; `export_meta.json` shows `since` 2026-10-27T03:35:00Z and a 72 h span.
- `06-12-live-checks.json` has no failing check and `exit_code` 0.
- `06-SOAK-REPORT.md` has Context, End-of-soak checks and lag-statistics sections.
- `backend/tests/secret_scan_test.py` passes with the evidence staged; no URL, host, project reference, key or database URL anywhere in it.
