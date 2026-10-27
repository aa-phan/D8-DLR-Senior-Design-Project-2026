# Plan 06-11 Pre-flight: the three live examples, the end-to-end trace, the PSS/E question

Written 2026-10-27 (about 01:25Z) by the executor. Nothing in this note or in the rehearsal touched the live Supabase project: no network call to the project, no `.env` read, no package installed, nothing pushed. It holds no project URL, host, reference or key.

## 1. Gate and rehearsal

**Gate.** `06-09-SUMMARY.md` records the live read check as passed: four rows (one per city), 34 columns in the published order, `count=exact` 4, a keyless request refused with 401, and the private run log unreadable with the publishable key (evidence: `06-09-live-checks.json`, 20 checks, exit code 0). So the examples have something live to read. Phase 5's hourly cron-job.org job is stated as running.

**Local rehearsal** (offline, against fake servers):

```
.venv/bin/python -m pytest -q -p no:cacheprovider -rs \
  backend/tests/example_read_ratings_test.py backend/tests/e2e_trace_test.py
```

Result: **40 passed, 0 skipped, 0 failed.** In plain English:

- `example_read_ratings_test.py` (15 tests): `read_ratings.py` ran as a subprocess against a fake server on **both** interpreters, the repository's Python 3.12.13 and the oldest local one, `/usr/bin/python3` 3.9.6 (that case did not skip); it parses as Python 3.7, uses only the standard library, keeps certificate checking, fails on three cities or an HTTP error, exits 2 without the two environment values, and survives a server cap below 1000. `curl.sh` ran against the fake: it paged past the cap, stopped when the row count could not be read, failed on an HTTP error. The `.mjs` example passes the syntax check (also run by hand: `node --check` printed nothing and exited 0). No example holds a URL or key, and all are read-only with one credential header.
- `e2e_trace_test.py` (25 tests): the trace correlates exactly one run to the execution time, fails loudly on zero or several candidates, compares the 31 stored columns per city, reports superseded rows as failures, checks the `is_provisional` word rule, redacts every line and file, and exits 0, 1 or 2 as documented.

**Versions on this machine:** `node --version` is v26.9.0; `/usr/bin/python3 --version` is Python 3.9.6; `.venv/bin/python --version` is Python 3.12.13. `package.json` and `node_modules` do not exist in the repository (and must not).

**One extra rehearsal (the trace wrapper in Step 6).** The trace needs a database connection in `SUPABASE_DB_URL`. Your `.env` is documented as holding `SUPABASE_ADMIN_DB_URL`; the executor cannot read `.env` to see whether it also holds `SUPABASE_DB_URL`. So Step 6 has a plain command and a fallback that borrows the admin connection (the trace only reads: it sets its session read-only before the first statement and uses bound parameters). The fallback was tried against a throwaway file with a fake address and no environment values: it imported the trace and stopped with `SUPABASE_URL is not set` and exit 2 before any connection, which is the intended first failure.

## 2. What you are about to do, in plain English

| Step | What it proves | Changes anything? |
|---|---|---|
| 1 | Both values the examples need are in your own terminal | No |
| 2 `curl.sh` | any language can read all four cities and page one city's history | No (GET and HEAD only) |
| 3 `read_ratings.py` on 3.9.6 and 3.12 | the PSS/E-style Python example works on an old and a new interpreter | No (GET only) |
| 4 supabase-js in a scratch folder | the dashboard's client library reads the same data | Installs one npm package into a scratch folder **outside** the repository, with install scripts disabled, only after you approve the version at the checkpoint |
| 5 find the cron-job.org execution | the single fact the trace needs from the console | No |
| 6 the trace | one scheduled trigger produced one run, the run wrote one row per city, and the public interface returns exactly those values | No (read only) |
| 7 the PSS/E question | the Power Systems team can run the Python example | Sends one message |

Do not change the hourly dispatch job on cron-job.org to make the trace easier (plan prohibition): the trace uses the execution history as it is. Do not touch the 06-10 jobs (alarm, soak) either.

## 3. Owner steps, in order

All commands run from `/Users/aphan/Senior_Design`, in your own terminal (in Claude Code you can prefix each with `! ` for a command that needs no value typed in; Step 1 must be typed in your own terminal). The two values below are never pasted into chat, a file or a commit. `.env` does not hold `SUPABASE_URL` or `SUPABASE_PUBLISHABLE_KEY`; read them from the Supabase dashboard (Project Settings, Data API / API keys). Use the **publishable** key, never the secret key.

### Step 1. Export the two values (your own terminal only)

```
export SUPABASE_URL="<project URL from the dashboard>"
export SUPABASE_PUBLISHABLE_KEY="<publishable key from the dashboard>"
```

Keep the same terminal window for Steps 2 to 6 (the values live only in that window). `read_ratings.py` and the trace refuse to run if either is missing (exit 2).

### Step 2. curl

```
bash docs/integration/examples/curl.sh
```

Expect exit 0: four city rows, a `total rows: N` line, then one or more `-- rows <offset> and after --` pages. To choose the city and window explicitly:

```
CITY=MIDLAND START=2026-10-25T00:00:00Z END=2026-11-01T00:00:00Z bash docs/integration/examples/curl.sh
```

Check the exit code with `echo $?` right after.

### Step 3. Python on the old and the new interpreter

```
/usr/bin/python3 -I docs/integration/examples/read_ratings.py
echo "exit=$?"
.venv/bin/python -I docs/integration/examples/read_ratings.py --city AUSTIN --start 2026-10-25T00:00:00Z
echo "exit=$?"
```

Expect exit 0 each time: four city lines and a history line (row count, first and last `valid_time`). The script does not print its Python version; the interpreters are 3.9.6 (`/usr/bin/python3`, deliberately older than 3.11, D-11) and 3.12.13 (`.venv/bin/python`), as recorded in section 1.

### Step 4. supabase-js in a scratch folder (only after the Task 2 checkpoint is approved)

Replace `<approved version>` with the exact version you approve at the checkpoint (for example `2.117.0`; do not type `@2` or `latest`).

```
mkdir -p ~/dlr-js-check && cd ~/dlr-js-check && npm init -y && npm install --ignore-scripts @supabase/supabase-js@<approved version>
cp /Users/aphan/Senior_Design/docs/integration/examples/supabase_js.mjs .
node --version
node supabase_js.mjs
echo "exit=$?"
cd /Users/aphan/Senior_Design
```

Expect exit 0: a table of four rows and a history count. The scratch folder is outside the repository on purpose; nothing is added to the repository. The copy of `supabase_js.mjs` is run from the scratch folder so Node finds the package there. If you rejected the package at the checkpoint, skip this step and say "not run: package rejected".

### Step 5. Find the execution's actual time in cron-job.org

1. Wait for the next hh:05 UTC scheduled execution of the dispatch job, then about 20 minutes more so the Actions run has finished.
2. In the cron-job.org console, open the **dispatch job** (the one that POSTs to `dlr_live.yml`), then its **History**.
3. Note that execution's **actual time** (to the second) and **HTTP status** (GitHub answers 204).
4. cron-job.org shows times in the timezone set in your account. Convert to UTC and write it with a trailing `Z`, for example `2026-10-27T02:05:02Z`. A time without `Z` is rejected on purpose (it could be your local time). Pick a scheduled hh:05 execution, not a manual test run.

### Step 6. The trace

Replace `<ISO time>` and `<status>` with the two values from Step 5. Both output files go in this phase directory; they hold run ids, times and values only (every line and file is redacted).

Plain command (works if your `.env` has `SUPABASE_DB_URL`):

```
.venv/bin/python backend/e2e_trace.py --execution-time <ISO time> --execution-status <status> --out .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-E2E-TRACE.md --json-out .planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/06-e2e-trace.json
echo "exit=$?"
```

If it stops with `SUPABASE_DB_URL is not set` (exit 2), use this fallback, which takes the connection from `SUPABASE_ADMIN_DB_URL` in `.env` inside the process (nothing prints it):

```
.venv/bin/python -c "import os,sys; sys.path.insert(0,'backend'); from dotenv import dotenv_values; v=dotenv_values('/Users/aphan/Senior_Design/.env'); os.environ.setdefault('SUPABASE_DB_URL', v.get('SUPABASE_DB_URL') or v['SUPABASE_ADMIN_DB_URL']); import e2e_trace; p='.planning/workstreams/production-pipeline/phases/06-exposure-e2e-verification/'; sys.exit(e2e_trace.main(['--execution-time','<ISO time>','--execution-status','<status>','--out',p+'06-E2E-TRACE.md','--json-out',p+'06-e2e-trace.json']))"
echo "exit=$?"
```

It also needs an authenticated GitHub CLI (`gh auth status` should say you are logged in). Expect exit 0 and PASS lines for each link. If it reports "superseded" or "2 candidates" or "0 candidates", repeat with the **next hour's** execution (Step 5 again); do not edit the job. Exit 1 means a link failed: send me the printed PASS/FAIL lines.

### Step 7. Send the PSS/E question (does not block the phase)

Send the Power Systems team this text (from `docs/integration/rest-api.md`, "PSS/E environment"):

> Please run the following inside PSS/E's Python and send back the two lines it prints:
>
> `import sys, ssl; print(sys.version); print(ssl.OPENSSL_VERSION)`
>
> Please also run `read_ratings.py` once (`python read_ratings.py --city AUSTIN`) with the two environment values I give you directly (the project URL and the publishable key, never by chat history or a file in the repository). The script needs Python 3.7 or newer with TLS 1.2 and SNI, standard library only. Tell me what it prints and its exit status.

The phase does not wait for the reply. If the answer is Python 2.7, that becomes a follow-up (a separate example), not a blocker. Record the date you sent it.

## 4. If an example fails

- If a Python or curl example fails only because the server rejects the two `valid_time` filters on one column, copy the error text and send it to me: a follow-up switches the examples to the `and=(...)` form.
- A `401` or an empty list usually means the wrong key or URL was exported; re-check Step 1 in the same terminal window.
- `exit=2` from `read_ratings.py` means a missing environment value.

## 5. After you reply

Reply "done" with each example's exit code and first lines, the trace's PASS/FAIL lines, and the date the PSS/E question was sent. The executor then checks the trace JSON (exit 0, one candidate run, conclusion success, four cities each with match true, the `is_provisional` check passed), runs the secret scan on the staged trace files, confirms no `package.json` or `node_modules` exists in the repository, commits both trace files, and writes the SUMMARY. Nothing is pushed.
