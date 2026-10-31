# Plan 06-13 Pre-flight: permission re-check after Supabase's 2026-10-30 change

Written 2026-10-31 by the executor. Nothing in this note or in the rehearsal touched the live Supabase project: no `.env` read, no network call to the project, no grant changed, nothing pushed. It holds no project URL, host, reference or key.

## 1. Date rule (D-09)

The re-check runs only when **both** hold:

| Condition | Evidence |
|---|---|
| The UTC time is on or after **2026-10-31T00:00Z** (after Supabase's 2026-10-30 default-permission change has had a day to reach existing projects) | the orchestrator's clock read 2026-10-31T00:07:13Z; mine read 2026-10-31T00:07:56Z |
| The 72 h soak window has ended | 06-12-SUMMARY.md records the window as 2026-10-27T03:35:00Z to **2026-10-30T03:35:00Z**; the soak job was removed at sign-off (0 remaining) |

Both hold now, so Task 2 can start. The platform change rolls out gradually, so a pass today proves today's state; if the owner wants extra assurance later the same five checks can simply be run again.

## 2. Local rehearsal

Run on a throwaway local Postgres, offline:

```
DLR_TEST_PG_AUTOSTART=1 .venv/bin/python -m pytest -q -p no:cacheprovider -rs \
  backend/tests/e2e_readonly_test.py backend/tests/supabase_smoke_test.py backend/tests/secret_scan_test.py
```

Result: **71 passed, 1 skipped, 0 failed, 0 errors.** The one skip is the secret-scan's owner-local live check (it needs the public key and database address in a shell). Without the local Postgres switch the plan's own verify command gives 61 passed, 5 skipped (the five skipped are the smoke tests that need a local database), also exit 0.

In plain English: the read-only verifier reads and checks the rating rows, confirms the private tables are hidden, tries every kind of write and fails the run if any write is accepted or the data changed; the smoke check proves, against a stand-in database, that it catches a public role holding a write permission, that every write it makes is rolled back, and that it never prints an address or key; the secret scan passes over the repository.

## 3. The five checks in plain English

| # | Check | What it means for you | Pass looks like |
|---|---|---|---|
| 1 | Read | Anyone with the public key can still read the current rating for all four cities, with the 34 documented columns | `latest_rating_*` rows PASS |
| 2 | Hidden tables | The private run log (`pipeline_run`) and the soak log (`ops.freshness_log`) still cannot be read with the public key | `hidden:*` rows PASS |
| 3 | Writes | Trying to add, change or delete data with the public key is still refused, and the data afterwards is identical to before | `write:*` rows PASS and `snapshot_unchanged` PASS |
| 4 | `verify_exposure.sql` | The database's own permission list still shows read-only access on exactly two objects (the ratings table and the view) | every `ok` true (17 of 17 in 06-09 and 06-12) |
| 5 | `consumers_cannot_write` (Phase 4's carried item T-04-22) | The platform change did not hand the public roles (`anon`, `authenticated`) any write permission on the two tables | `check consumers_cannot_write: ok` and `SMOKE OK` |

## 4. What the previous runs showed (what "identical" means)

Seven write attempts, same in 06-09 and 06-12:

| Attempt | Verdict | HTTP status | Error code |
|---|---|---|---|
| table_insert | pass | 401 | 42501 |
| table_upsert | pass | 401 | 42501 |
| table_patch | pass | 401 | 42501 |
| table_delete | pass | 401 | 42501 |
| view_insert | pass | 500 | 55000 |
| view_patch | pass | 500 | 55000 |
| view_delete | pass | 500 | 55000 |

Any change in a verdict, a status or a code, a read that breaks, or a new grant is a **discrepancy**: I report it to you, E2E-03 stays open and I do not fix it. A fix would be a new additive migration that you apply. The row counts in the snapshot will differ from before (more history exists); that is expected and is reported, not hidden.

## 5. Task 2 command sheet (owner)

All commands run from `/Users/aphan/Senior_Design`. In Claude Code prefix each with `! `. Commands that need the database load the address from your git-ignored `.env` inside the process; nothing prints it. `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` are not in `.env`: export them in **your own terminal only** (Terminal.app), never in chat; paste back redacted output.

**No backfill load and no manual re-run of a past slot may run during step 2.** The hourly run is harmless (it writes only the current slot).

### Step 1. Database permission list (read only)

Paste `supabase/ops/verify_exposure.sql` into the SQL editor, or run the read-only runner from 06-09 and 06-12 (it refuses any write and runs `verify_exposure.sql` and `verify_monitoring.sql`):

```
.venv/bin/python /Users/aphan/.claude-edu/jobs/36058868/tmp/run_verify.py
```

Every `ok` must be true. Copy the result table. Expected: 17 of 17 for `verify_exposure.sql` (and 7 of 7 for `verify_monitoring.sql`), with details as in 06-09.

### Step 2. Live public-key check (your own terminal)

```
export SUPABASE_URL=<paste from dashboard>   SUPABASE_PUBLISHABLE_KEY=<paste from dashboard>
cd /Users/aphan/Senior_Design
PYTHONPATH=backend .venv/bin/python backend/e2e_verify_readonly.py --check-read --check-hidden --check-writes --json-out .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-13-live-checks.json
echo "exit code: $?"
```

Expect the last line `E2E READONLY OK` and exit code 0. The JSON file is redacted by the script (no URL, no key). Paste back the printed PASS/FAIL lines and the exit code. (The plan's `.venv/bin/python backend/e2e_verify_readonly.py ...` form without `PYTHONPATH=backend` is the same; the `PYTHONPATH` form is the one that worked in 06-09 and 06-12.)

### Step 3. Writer smoke, T-04-22 (WRITES, then rolls back)

This connects as the CI writer role using `SUPABASE_DB_URL` from `.env` and writes sentinel rows inside one transaction that is **always rolled back**, so it leaves nothing behind. It is the only step that writes at all, and nothing it writes persists.

```
PYTHONPATH=backend .venv/bin/python -c "from dotenv import load_dotenv; load_dotenv('.env'); import sys, supabase_smoke; sys.exit(supabase_smoke.main(['--report', '.planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-13-smoke.json']))"
echo "exit code: $?"
```

Expect `check consumers_cannot_write: ok`, `SMOKE OK` and exit code 0. If it prints `SUPABASE_DB_URL is not set` (exit 2) the writer address is missing from `.env`; tell me and do not paste any address. The report holds only booleans, counts, the role name, the server version and UTC times.

Optional: `gh workflow run supabase_smoke.yml --ref main` runs the same smoke from GitHub with the repository secret; note the run's conclusion. It is not required.

## 6. What I do after you reply "re-checked" (Task 2 verification)

1. Parse `06-13-live-checks.json` (every check ok, exit_code 0) and `06-13-smoke.json` (`all_passed` true, `consumers_cannot_write` true, `info.anon_can_select` true as expected after Phase 6).
2. Build the three-way per-attempt comparison (06-13 against 06-09 and 06-12: attempt, verdict, status, code). Any difference is a discrepancy for you; E2E-03 is then not marked closed.
3. Run the secret scan with both JSON files staged, commit with explicit paths, no push. Record the `verify_exposure.sql` table you paste, the comparison and "T-04-22: closed" (or open with the reason) in the SUMMARY.

## 7. Evidence checklist for the Task 2 commit

- `06-13-live-checks.json` has no failing check and `exit_code` 0.
- `06-13-smoke.json` has schema `supabase_smoke/1`, `all_passed` true and `checks.consumers_cannot_write` true.
- `backend/tests/secret_scan_test.py` passes with the evidence staged; no URL, host, project reference, key or database URL anywhere in it.
