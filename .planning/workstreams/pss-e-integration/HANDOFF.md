# PSS/E integration handoff (written 2026-11-11)

Branch: `feature/pss-e-integration` (pushed). Read `STATE.md`, `ROADMAP.md`, then `docs/data-science/decisions/psse_laptop_runbook.md`.

## What it does
Hourly job: read the model's ratings from the Supabase `city_rating` view, scale the public IEEE 39-bus case per city, run the load flow and the outage cases in PSS/E, and write the results to the `psse_*` tables as the `dlr_psse_writer` role (INSERT only, so rows are permanent). Ratings older than 90 minutes or provisional fall back to static ratings, and the reason is recorded. Writing results back is required for grading.

## State at handoff
- Phases 1 to 4 built and verified. One real run was written by hand (exit 0, outcome ok, 32 of 32 outages with results).
- Phase 3, plan 03-08, step 10 (hourly task) is IN PROGRESS, not recorded in the repo yet.
- Task `DLR-PSSE-Hourly` is registered on the PSS/E laptop (user account, runs at :15:15). Runs at 3:15, 4:15 and 5:15 PM Central on 11-11 all returned 0, 0 missed. Gap check: 4 runs recorded, 13 gaps all 08:00Z to 20:00Z on 11-11, which are before the task existed and are expected.
- One-time task `DLR-PSSE-Stop` disables the hourly task at 11-12 10:00 AM local. The laptop must stay plugged in, signed in, awake and on wifi until then.

## Laptop facts (PSS/E laptop)
- Repo: `C:\Ben_Meunier Laptop\Senior Design\repo`. Config and working files: `C:\Ben_Meunier Laptop\dlr-psse\` (`config.txt`, `work\`, `task_real.xml`, private `mapping_real.json`). The Windows profile folder is `Ben_ Meunier Laptop` (with a space); the repo is NOT under it.
- Interpreter: `C:\Users\Ben_ Meunier Laptop\AppData\Local\Programs\Python\Python314\python.exe`.
- No admin rights: the Windows Time service cannot be started. The clock matched a web Date header to the second on 11-11. Recheck with `(Invoke-WebRequest -UseBasicParsing -Method Head https://www.microsoft.com).Headers.Date` against `(Get-Date).ToUniversalTime().ToString("R")`.
- Times: gap output is UTC; the laptop is Central (UTC-6 in November).
- When pasting PowerShell, keep to one dollar sign per line.
- `config.txt` holds the writer connection string and Supabase keys. They are not in git. `mapping_real.json` (real city targets) is not in git and cannot be recovered from it; copy it somewhere private before the laptop is wiped.

## Next steps, in order
1. After 11-12 10:00 AM local: run `python -X utf8 backend\psse_run_hourly.py gaps --config <config.txt>` on the laptop. Expect only the 13 old gaps and every hour from 21:00Z on 11-11 recorded. A new gap means a missed run (sleep or lost wifi).
2. Check `Get-ScheduledTask -TaskName "DLR-PSSE-Hourly"` says Disabled. If not, run `Disable-ScheduledTask -TaskName "DLR-PSSE-Hourly"`. Optionally `Unregister-ScheduledTask` for both tasks.
3. Scrub secrets from `config.txt`, its backups and `task_real.xml` before the laptop is returned.
4. Write the step 10 outcome into `03-07-LAPTOP-RECORD.md` (and the runbook), including the clock note (aligned, w32time not running, no admin), then finish plan 03-08, and update `STATE.md`, `ROADMAP.md` and `REQUIREMENTS.md`. Commit and push.
5. Add a short README section for grading: what it reads, what it does, how to run it, evidence of runs.
6. Consider rotating the `dlr_psse_writer` password afterward; the credential sat on a borrowed laptop. That is the owner's call.

## Open items, not blocking
- Production-pipeline Phase 6 has not adopted the `psse_*` tables.
- A stray `SUPABASE_DB_URL` (not the PSS/E writer role) was removed from the laptop config earlier; rotation is the owner's call if it was ever shared.
- Do not write another manual run without an explicit yes: rows are permanent (no DELETE).

## Decisions already made (do not reopen)
- Per-city scaled copies of the 39-bus case replace waiting for Power Systems' branch mapping.
- Plan 03-08 decision 2: enable the hourly task and observe, then disable.
- No more verification layers; keep replies and records short.
