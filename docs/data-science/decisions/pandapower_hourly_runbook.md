# pandapower Hourly Job Runbook

**Status: prepared for the hand-off (pandapower-solver Phase 5). Nothing described here runs on GitHub
until the repository owner has merged the branch into `main`. The job is a dry run until the owner
switches it live.**

This is the operating reference for `.github/workflows/pandapower_hourly.yml` and the cron-job.org job
that starts it: what one run does, the order of the owner's steps after the merge, how the dry run is
observed, how the job goes live, how it is paused, and what to do when it fails. It is deliberately
commands and settings, not rationale; the rationale is in the Phase 5 context and plans. Nothing here
holds a secret value: secrets, tokens and keys live in GitHub's `production` environment and in
cron-job.org, never in this repository. The same layout as `dlr_live_runbook.md` is used on purpose.

Last updated 2026-11-26 (plan 05-06).

## 1. Purpose and scope

Every hour at minute 20 UTC the workflow runs the study of the four-city case with the latest stored
ratings, using the pandapower solver, and then runs a read-only gap and soak check. One run is:

1. `python -I -B backend/pandapower_hourly.py run`: reads the latest ratings, runs the study and prints
   counts only.
2. `python -I -B backend/pandapower_hourly.py soak`: reports, per solver, whether any hour is missing
   and how many consecutive hours pandapower has recorded (the soak count, of 24).
3. A last step removes the private files from the runner's temporary folder.

**Dry unless the repository variable is exactly `true`.** With `PANDAPOWER_LIVE` unset, empty or any
other text, the run reads, computes, prints counts and writes nothing to the database. With the exact
text `true` it stores one run (one run row, four dispatch rows, four margin rows and the contingency
rows) tagged with the solver `pandapower`. The workflow has no inputs, so a person who dispatches it
cannot choose live mode.

Decisions this runbook follows, by number (`05-CONTEXT.md`):

| Decision | What it fixes here |
|---|---|
| D-02 | Dry unless `PANDAPOWER_LIVE` is `true`; the go-live decision is dated in `pandapower_live_write_decision.md` |
| D-03 | A live run is refused while the recorded settings are a placeholder |
| D-07 | Nothing runs on GitHub until the owner merges at the end |
| D-08 | The private inputs travel as four base64 secrets made by the `bundle` command |
| D-09 | The gap step reports and does not fail the run, except when the check cannot run |
| D-10 | A dry run never holds the writer credential in its study step |
| D-11 | The conditions before the flip: 3 green dry runs, one scanned log, the local count comparison |
| D-12 | Fallback runs count toward the soak and are shown |
| D-13 | `PANDAPOWER_LIVE` is a repository variable only, never per environment |
| D-14 | Everything printed is a closed vocabulary of counts and words; nothing private reaches the log |

## 2. Order of first-time setup

Nothing runs on GitHub before the repository owner merges the branch to `main` (D-07). The workflow
file is read from `main` only, and the study job refuses any other branch. After the merge, do these
sections in this order:

1. Section 3: the holder of `data/private/pandapower/` makes the bundle; the repository owner creates the
   seven secrets in the `production` environment.
2. Section 4: one manual dispatch from `main`, and one from another branch to see the branch check.
3. Section 5: the cron-job.org job, only after a manual dispatch from `main` was green.
4. Section 7: observe at least 3 consecutive green scheduled dry runs, scan one real log and run the local
   count comparison.
5. Section 8: record the go-live decision, then set the repository variable.
6. Section 9: the soak, then the closing check.

Sections 6, 10, 11, 12 and 13 are reference for the rest of the time.

## 3. Secrets

Seven secrets are required. All seven live in the `production` environment (Settings, Environments,
`production`), which has a deployment-branch rule that allows `main` only. Only the repository owner can
create them: the account used for the build has push rights but not admin rights, so it can dispatch the
workflow, list runs and download logs, and cannot create a secret, a variable or an environment rule.

| Secret | What it is for | Who creates it | Where its value comes from |
|---|---|---|---|
| `PANDAPOWER_NETWORK_B64` | The converted 39-bus network, base64 | the repository owner | the newest bundle folder, file `PANDAPOWER_NETWORK_B64.txt` |
| `PANDAPOWER_MAPPING_B64` | The per-city mapping, base64 | the repository owner | the same folder, file `PANDAPOWER_MAPPING_B64.txt` |
| `PANDAPOWER_SETTINGS_B64` | The recorded solve settings (six keys), base64 | the repository owner | the same folder, file `PANDAPOWER_SETTINGS_B64.txt` |
| `PANDAPOWER_SCALING_B64` | The three scaling details, base64 | the repository owner | the same folder, file `PANDAPOWER_SCALING_B64.txt` |
| `SUPABASE_URL` | The project's API address, for reading the ratings view | the repository owner | the Supabase project's API settings |
| `SUPABASE_PUBLISHABLE_KEY` | The publishable key, for reading the ratings view | the repository owner | the same page; the publishable key only, never a secret key |
| `SUPABASE_PSSE_DB_URL` | The writer connection of the `dlr_psse_writer` role | the repository owner | the session pooler address (port 5432) of that role; the user name has the form `dlr_psse_writer.<project-ref>` |

The three Supabase secrets are not repository secrets: put them in the `production` environment next to
the four bundle secrets. The writer value is handed to the study step only when the variable is exactly
`true`; the gap and soak step always gets it, read-only, which proves the credential and the live
migration from the runner before the flip.

**Making the bundle.** The holder of `data/private/pandapower/` runs, from the repository root:

```bash
.venv/bin/python -I -B backend/pandapower_hourly.py bundle
```

On Windows the interpreter is `.venv/Scripts/python.exe`. The command prints four size lines
(`bundle: network bytes=N base64=N fits` and the same for the other three), `bundle: verified` and
`bundle: written`, and nothing else. It writes a new folder
`data/private/pandapower/secrets/secrets_STAMP/` holding the four files named
`<SECRET NAME>.txt`, one base64 line each. It reads the newest check folder and the default mapping; to
name them, use `--check-dir DIR` and `--mapping PATH`:

```bash
.venv/bin/python -I -B backend/pandapower_hourly.py bundle --check-dir DIR --mapping PATH
```

The command refuses when it runs on GitHub, when a source is missing or a placeholder, or when a value
does not fit a secret's size limit; a refusal writes nothing. The settings and scaling files are rebuilt
from the validated settings, so the session hashes, the NET-03 verdicts and the parity detail of the
check report never reach a secret.

**Handing the four files over.** The holder gives the four files to the repository owner over the same
private channel as the session zip. Never in a chat message, an issue, a pull request or the repository.

**Creating the secrets.** The repository owner, from any clone with `gh` signed in:

```bash
gh secret set PANDAPOWER_NETWORK_B64 --env production < PANDAPOWER_NETWORK_B64.txt
gh secret set PANDAPOWER_MAPPING_B64 --env production < PANDAPOWER_MAPPING_B64.txt
gh secret set PANDAPOWER_SETTINGS_B64 --env production < PANDAPOWER_SETTINGS_B64.txt
gh secret set PANDAPOWER_SCALING_B64 --env production < PANDAPOWER_SCALING_B64.txt
gh secret set SUPABASE_URL --env production
gh secret set SUPABASE_PUBLISHABLE_KEY --env production
gh secret set SUPABASE_PSSE_DB_URL --env production
```

The last three read the value from a prompt. `gh secret list --env production` shows names only; check
that all seven names are there. Delete the four bundle files from wherever they were handed over once the
secrets exist; the originals stay in the private folder.

**No required reviewers on the environment.** An approval wait would stall every hourly run. The
protection is the main-only deployment-branch rule and the `if` guard in the workflow.

**A correction.** Section 3 of `dlr_live_runbook.md` calls `SUPABASE_DB_URL` a repository secret. It is
out of date: the value is held in the `production` environment, and it belongs to a different role
(`dlr_writer`). This job never uses it.

## 4. First dispatch and the branch check

After the secrets exist and the branch is on `main`, dispatch the workflow by hand. Push rights are
enough for this:

```bash
gh workflow run pandapower_hourly.yml --ref main
gh run list --workflow pandapower_hourly.yml --limit 5
gh run watch
```

`gh run watch` asks which run to follow. The first run is a dry run (the variable does not exist yet).
Expect the three steps to be green and the log to hold only the lines of section 6, with
`mode: dry` first and `dry run: nothing was written to the database` last. The gap and soak step prints
`gap check:` lines; before the flip pandapower has no runs, so `gap check: solver pandapower no runs
recorded` is the expected line.

**The branch check.** Dispatch once from a branch that is not `main` (for example the feature branch
while it exists, or any other branch):

```bash
gh workflow run pandapower_hourly.yml --ref BRANCH
gh run list --workflow pandapower_hourly.yml --limit 5
```

The run must show the job as skipped and never reach a step that holds a secret. A dispatch from another
branch that runs the steps is a defect: stop and tell the owner.

## 5. Trigger (cron-job.org)

The workflow has no GitHub `schedule:` trigger; GitHub's own scheduler started the other hourly workflows
hours late. A cron-job.org job calls the workflow's `dispatches` endpoint, the same mechanism the other
hourly workflows use. Create the job only after one manual dispatch from `main` (section 4) was green:
cron-job.org disables a job that fails 25 times in a row, and a misconfigured job fails every hour.

Job settings in cron-job.org:

| Setting | Value |
|---|---|
| Title | pandapower hourly |
| URL | `https://api.github.com/repos/aa-phan/D8-DLR-Senior-Design-Project-2026/actions/workflows/pandapower_hourly.yml/dispatches` |
| Method | POST |
| Header `Accept` | `application/vnd.github+json` |
| Header `Authorization` | `Bearer <the fine-grained token, entered in cron-job.org only>` |
| Header `X-GitHub-Api-Version` | `2022-11-28` |
| Body | `{"ref":"main"}` |
| Expected result | HTTP 204 with an empty body (GitHub accepted the dispatch) |
| Schedule | `20 * * * *`, time zone set to UTC |
| Notifications | failure notifications on |

The body never carries `inputs`; the workflow has none.

**Why minute 20.** The rating job runs at minute 05 and the PSS/E laptop task `DLR-PSSE-Hourly` at
minute 15 when it is enabled, so the latest ratings are in place when this job reads them. The workflow's
own concurrency group is `pandapower-hourly`, so it never blocks, and is never blocked by, the other
workflows.

**The token.** A new fine-grained personal access token, made for this job only:

- Resource owner: the repository owner; "Only select repositories": this repository only.
- Repository permission "Actions": read and write. Nothing else.
- An expiry date, with a calendar reminder set before it. An expired token makes every dispatch fail and
  nothing in the repository reports it.
- Separate from the tokens of the other jobs, so any one can be revoked alone.
- Stored only in cron-job.org. Never written in this repository, in a workflow, in a `.env` or in a
  message.

**What is recorded here and what is not.** Recorded: the URL, method, header names, body, expected status,
schedule and token scope above. Not recorded, by design: the token, its expiry date and the account details.

**A disabled job.** cron-job.org disables a job after 25 failures in a row. A "job disabled" email is the
only sign. To recover, fix the cause, re-enable the job and check that its next execution answers 204.

## 6. What one run prints and the exit codes

Every printed line is one of a closed set of counts and words (D-14). A run id, a hash, a path, a bus
number, a figure or error text cannot appear. No line starts with two colons.

| Line | Meaning |
|---|---|
| `mode: dry` or `mode: live` | Which mode this run is in |
| `inputs: ok` | The four private inputs decoded |
| `ratings: city_rating=N static=N` | How many of the four cities used a stored rating and how many used the static one |
| `study: ok` or `study: failed at stage WORD` | The study result and, when it failed, the stage |
| `outcome: ok`, `fallback` or `failed` | The run's outcome |
| `rows: run=N dispatch=N margin=N contingency=N` | The row counts of the result set |
| `dry run: nothing was written to the database` | The last line of a dry run |
| `run status: WORD` | The live run's status: `written`, `already_recorded`, `failure_recorded` or `not_recorded` |
| `gap check: solver NAME runs=N gaps=N` | Per solver, runs recorded and missing hours |
| `soak: consecutive_slots=N of 24 fallback_slots=N` | The trailing count of consecutive hours and how many were fallback |
| `soak: pass` or `soak: not yet` | The count is at least 24, or it is not |

Exit codes of `backend/pandapower_hourly.py`:

| Code | Meaning | What to check |
|---|---|---|
| 0 | The run is ok; a dry run passed; or the soak command found nothing to report | Nothing |
| 1 | The study failed, or a failure row was recorded (for the `scan-log` command: the log has findings) | The `study: failed at stage` line names the stage; the run turns red and GitHub's failure email is the alert |
| 2 | Usage error, a refusal (missing or unusable input, a placeholder in live mode) or an unexpected error | The refusal line (section 11) |
| 3 | A live run could not be recorded | The database connection and the writer secret (section 11) |
| 5 | `soak --since`: a gap in the window, or fewer than 24 consecutive slots | The `gap check` and `soak` lines |
| 6 | The gap and soak check could not run (`gap check: could not run`) | The writer secret, the project's pause state and the live migration |

## 7. Dry-run observation

Go live only after the dry run has shown, from GitHub's runner, that the job works (D-11). Record the
evidence in `pandapower_live_write_decision.md`, section "Dry-run evidence".

1. **Three green scheduled runs.** At least 3 consecutive scheduled dry runs, each with all three steps
   green. The soak step's `gap check` lines prove the writer credential and the live migration from the
   runner: a run on which they read `gap check: could not run` is not green for this purpose.

   ```bash
   gh run list --workflow pandapower_hourly.yml --limit 10
   ```

2. **One real log, scanned.** Download one log, outside the working tree and on the same drive, and scan
   it against the private folder and the bundled secrets:

   ```bash
   gh run view RUN_ID --log > "$HOME/pandapower_hourly_run.log"
   .venv/bin/python -I -B backend/pandapower_hourly.py scan-log --log "$HOME/pandapower_hourly_run.log"
   ```

   Expect `scan-log: lines=N findings=0` and exit 0. A finding prints its line number and kind, never the
   text; exit 1 means findings (treat as a leak: rotate the affected secrets, section 12), exit 2 a refusal
   (`scan-log: refused (WORD)`; the log was not scanned). Delete the downloaded log afterwards.

3. **The local count comparison.** The runner is Linux and the study also runs on the owner's machine; this
   compares the two. Within the same hour as a scheduled run, run the same `run` command locally in dry
   mode, with the four values exported from the bundle files and the two read values set in the shell:

   ```bash
   BUNDLE=data/private/pandapower/secrets/secrets_STAMP
   for NAME in PANDAPOWER_NETWORK_B64 PANDAPOWER_MAPPING_B64 PANDAPOWER_SETTINGS_B64 PANDAPOWER_SCALING_B64; do
     export "$NAME=$(< "$BUNDLE/$NAME.txt")"
   done
   export SUPABASE_URL=<SUPABASE_URL> SUPABASE_PUBLISHABLE_KEY=<SUPABASE_PUBLISHABLE_KEY>
   .venv/bin/python -I -B backend/pandapower_hourly.py run
   ```

   Compare the printed lines with the same hour's run log. Identical lines pass. The ratings must be the
   same hour's: if the rating job ran late, the two runs read different ratings, so repeat in a later hour.
   The two values go in the shell only, never in a file.

4. **The laptop task.** Record the state of the `DLR-PSSE-Hourly` task (enabled or disabled) with
   `docs/data-science/ops/psse_laptop_status.ps1` or `Get-ScheduledTask -TaskName "DLR-PSSE-Hourly"` on
   the laptop. It runs at minute 15, so it does not conflict with minute 20. Its `psse` rows never fill a
   pandapower hour in the per-solver check.

## 8. Go-live

The switch is one repository variable. Before it:

- `pandapower_live_write_decision.md` must say `Accepted` with a dated line, "Decided: go live, by NAME,
  on YYYY-MM-DD (UTC)".
- `05-RETENTION-DECISION.md` must hold the owner's review limit and the size read with
  `supabase/ops/psse_result_size.sql` in the Supabase SQL editor before the flip.
- Section 7 must be complete.

Then the repository owner sets the variable at repository level, and only there:

```bash
gh variable set PANDAPOWER_LIVE --body true
```

Never set it per environment (D-13). The next scheduled run is the first live run. A live run is also
refused in code while the recorded settings are a placeholder (D-03).

**A known, harmless quirk.** GitHub compares strings without regard to case, so a capital-T `True` in
`PANDAPOWER_LIVE` makes the workflow hand the writer value to the study step. The runner treats only the
exact lowercase `true` as live, so that run is still a dry run and prints `mode: dry`. Nothing is written.
Set the variable to exactly `true`.

## 9. Soak

The soak is 24 consecutive hourly slots with a pandapower run recorded (OPS-05).

- Note the first live run's slot (the UTC hour of its start).
- Avoid manual dispatches during the soak. Each adds a permanent row set and, in the same hour as a
  scheduled run, an extra set.
- The 25th live run's `soak:` lines are the first to show the count; each run shows
  `soak: consecutive_slots=N of 24 fallback_slots=N`.
- The closing check is run by the holder of the writer value, with that value in the shell and the first
  live slot as `--since`:

  ```bash
  export SUPABASE_PSSE_DB_URL=<SUPABASE_PSSE_DB_URL>
  .venv/bin/python -I -B backend/pandapower_hourly.py soak --since YYYY-MM-DDTHH:00:00Z
  ```

  Exit 0 means the soak passed: no pandapower gap in the window and at least 24 consecutive slots. Exit 5
  means a gap or a short count; exit 6 means the check could not run. The time must be a whole UTC hour
  written exactly as shown.
- Fallback slots (a run that used a static rating) count and are shown, D-12.
- Any missed hour restarts the count.
- Record counts only in `05-SOAK-RECORD.md`: the slots, the fallback count and the exit code. No run id,
  no connection detail.

## 10. Pause and resume

**Pause.** Disable the cron-job.org job. That stops new runs at the source; a run in flight finishes. To
return a live job to a dry run without stopping it:

```bash
gh variable set PANDAPOWER_LIVE --body false
gh variable delete PANDAPOWER_LIVE
```

Either command works (the second removes the variable); the next run is dry. To also block manual
dispatches, open the Actions tab, "pandapower hourly", the "..." menu and choose Disable workflow. If the
workflow is disabled while the cron-job.org job is enabled, cron-job.org receives errors and may disable
its own job; check its state after resuming.

**What stays.** Rows written while the job was live stay (D-01). The writer role cannot delete, and
nothing here removes rows.

**Resume.** Re-enable the workflow if it was disabled and re-enable the cron-job.org job; set the variable
back to exactly `true` only if the job should be live again. Missed slots are not back-filled and restart
the soak count (section 9).

## 11. Failure modes

| What you see | Meaning | What to do |
|---|---|---|
| `inputs: refused (missing_secret)` | One of the four bundle secrets or the two read secrets is missing, or empty | `gh secret list --env production`; create the missing one (section 3) |
| `inputs: refused (bad_base64)` | A bundle secret is not plain single-line base64 | Make a new bundle (section 12) and set the four secrets again |
| `inputs: refused (too_large)` | A decoded secret is over its size cap | Run `bundle`; its size lines show which value does not fit |
| `records: refused (WORD)` | The recorded settings were refused by the engine's checks | Make a new bundle from the approved check folder (section 12) |
| `placeholder: refused` | A live run found placeholder settings (D-03) | Make a new bundle from the approved check folder, never from a placeholder; the variable can stay |
| `gap check: could not run` | The soak step could not read the database (exit 6) | The `SUPABASE_PSSE_DB_URL` secret (format and role), the Supabase project's pause state, the live migration |
| red run, exit 1 | The study failed, or a failure row was recorded | The `study: failed at stage` line; one red run is a visible, recorded failure and does not stop the next hour |
| red run, exit 3 | A live run's outcome could not be recorded | The writer secret and the database; rerun nothing until the cause is known, a rerun in the same hour adds a second row set |
| `error: unexpected (NAME)` | An unexpected error; only its class name is printed | Run the section 7 local comparison to reproduce, with the owner's machine's full output |
| A dispatch answered with an error in cron-job.org | The token expired or lacks Actions write | A new fine-grained token (section 5) |

## 12. Rotating the private inputs

When the mapping or the network changes, or a log scan found a leak:

1. The holder runs `bundle` again (section 3): a new `secrets_STAMP` folder; the older folders are kept.
2. The repository owner replaces the four `PANDAPOWER_*_B64` secrets with `gh secret set` as in section 3.
3. The stored mapping hash then changes: a run with the new inputs records the new hashes, so rows of
   the old and the new inputs are told apart in the database.
4. For a suspected leak also rotate the three Supabase secrets and the dispatch token.

## 13. Retention

Every row is kept; nothing is pruned in this phase. The decision, the owner's review limit and the size
read before the first live write are in
`.planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/05-RETENTION-DECISION.md`.
The size query is `supabase/ops/psse_result_size.sql`, run in the Supabase SQL editor.

## 14. References

- `.github/workflows/pandapower_hourly.yml`: the workflow
- `backend/pandapower_hourly.py` and `backend/pandapower_job/hourly.py`: the runner and the owner commands
- `docs/data-science/decisions/pandapower_live_write_decision.md`: the go-live decision record
- `docs/data-science/decisions/pandapower_network_data_decision.md`: why the network is private
- `docs/data-science/decisions/dlr_live_runbook.md`: the runbook of the other hourly workflow
- `.planning/workstreams/pandapower-solver/phases/05-hourly-workflow-dry-run-and-live-soak/05-CONTEXT.md`: decisions D-01 to D-14
