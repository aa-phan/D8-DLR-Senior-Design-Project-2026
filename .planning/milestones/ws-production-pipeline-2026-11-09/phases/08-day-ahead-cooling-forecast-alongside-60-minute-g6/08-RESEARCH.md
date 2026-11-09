# Phase 8: Day-Ahead Cooling Forecast Alongside 60-Minute G6 - Research

**Researched:** 2026-11-07
**Domain:** Wiring an existing, frozen shadow forecast method into the hourly live job as a separate, non-gating output (Python runner, Supabase Postgres/PostgREST, GitHub Actions)
**Confidence:** HIGH for in-repo facts (every discrete value below was read in the source file this session); MEDIUM for the recommended numbers (band switch-over, stage timeouts), which are tagged `[ASSUMED]`.

## In plain English (read this first)

**What gets built.** Four times a day (06:05, 12:05, 18:05 and 00:05 UTC, which is 12:05 AM, 6:05 AM, 12:05 PM and 6:05 PM Central standard time) the hourly live job, after it has finished rating all four cities, works out one new day-ahead ampacity number per city. Each number is for a target hour of 00, 06, 12 or 18 UTC about 18 hours later. The weather behind it is the Open-Meteo forecast that started exactly 24 hours before the target hour. The number comes from `ml_cooling_corrected`, using the shadow code's own functions, untouched. It is saved with a 5%-95% uncertainty band and the label `day-ahead-24h; engineering-selection; not-validated` in a new table. Consumers read it through a new read-only view. The existing live rating, the 60-minute G6 forecast, `city_rating` and the 34-column `latest_rating` are not changed.

**What I found that the planner must know.**

1. The shadow code can be called as is. Only two of its steps care about the conductor: the perpendicular-wind projection (it needs the line bearing) and the final heat balance. Both take a `geometry` argument, so passing `production_city_point(city)` is enough. I ran the whole chain offline with the real, hash-verified model files and it works for all four cities. For CORPUS_CHRISTI, MIDLAND and EL_PASO the production point is numerically identical to the Drake point, so those three will match the shadow log exactly. Only AUSTIN differs (Drake at 100 °C).
2. No guard test forbids this. The golden test freezes 15 named files and the folder `data/shadow/models`. The AST caller-split test forbids only 11 named shadow modules from naming `production_city_point`. A new production module is in neither list.
3. Three real traps are not in CONTEXT.md. (a) The model pre-flight step is a hard gate for the whole job. If the new cooling or band entries failed it, live ratings would stop, which contradicts D-15. (b) The new `pipeline_run` column must exist in the database before the runner code that writes it is deployed, or every rating-stage run-row write fails and the job turns red. (c) `verify_exposure.sql` and several pinned tests hard-code "two public objects", so exposing the new view makes them fail until they are updated on purpose.
4. The band was calibrated on a slightly different setup than live. TEST used the station-like "now" reading taken exactly 24 hours before the target. The shadow reads "now" about 12 hours before the target. This phase, issuing as soon as the run is available, reads it about 18 hours before. TEST also grades against reanalysis weather, while the live band later grades against the station-composed live rating. Both facts belong in the contract text. The live rolling band (D-05) is what corrects them over time.
5. The first run after go-live will issue every target that is already due, up to 3 per city (12 rows), not 4. D-17's "first live issue slot writes 4 rows" should be worded to match (see Open Questions).

**Primary recommendation:** Add one child-process stage per city to `dlr_live_run.run_live`, after the exit code has already been fixed from the ratings. The stage reads the new table to find missing targets, calls the shadow functions unchanged under the production point, attaches a band from a hashed TEST artifact (switching to the live rolling band per band when enough pairs exist), and inserts rows first-write-wins. Ship it in two migrations ("write first, expose later"). Keep every new pinned-test change additive.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### When and how it runs
- **D-01:** **Four target hours a day, as tested.** One value per city for each 00/06/12/18 UTC target hour, computed from the Open-Meteo run initialised exactly 24 h before the target. This
  is the only setup TEST and reads 1-2 measured. No hourly issuance at 25-29 h leads.
- **D-02:** **Runs inside the hourly live job** (`dlr_live.yml` / `dlr_live_run.py`) as a separate
  stage after all live ratings are written, and only does work when a target is due (its 24 h-old
  run is published; the code assumes about 6 h publication lag). It must never delay, block or
  change the live ratings. No new workflow and no new cron-job.org job.
- **D-03:** **Match the shadow exactly.** Production computes the value through the shadow code's
  own functions: the same forecast fetch (`fetch_live_forecast_for_valid_time`), the same "now"
  anchor reading (`fetch_live_anchor_observation`, wind and air temperature), the same feature
  build and `CoolingCorrectionShadowMethod.predict`. It calls them unchanged, under the production
  conductor geometry for the city (D-14). A parity test shows production and the shadow path give
  the same number for the same inputs. It does not reuse the live run's composed observation.
  *Planner note:* the shadow collector itself runs on Drake (COND-02). Parity is "same functions,
  same inputs", with the production conductor point. AUSTIN's value therefore legitimately differs
  from the shadow log's Drake-75 value.
- **D-04:** **Catch-up on a missed slot.** If the run that should issue a target fails or is
  skipped, a later hourly run issues it from the same 24 h-old weather run, provided the target
  hour is still in the future. Every row records its actual issue time, so late values are
  visible. Once the target hour has passed, the slot stays empty.

### Uncertainty band
- **D-05:** **Band source: TEST to start, then live.** At launch each band comes from TEST-split
  residuals of `ml_cooling_corrected` (valid times 2026-03-18 to before 2026-09-30, production
  conductor basis). It is computed once and saved as a hashed artifact verified before use, like
  the models. Once enough live pairs exist, the band switches to the forecast's own recent misses
  against the live outcome, in the same out-of-sample residual-quantile way as the 60-minute band
  (`ampacity_forecast.backtest_residuals` / `FORECAST_BACKTEST_QUANTILES`). Every row records which
  source its band used (e.g. `band_source` = test-split / live-rolling) and its sample size.
- **D-06:** **One band per city × target hour** (16 bands: 4 cities × 00/06/12/18), about 196
  TEST residuals each. TEST showed the day-ahead error depends strongly on the target hour
  (cooling minus ml60 gap +13.5 A at 00 UTC to +30.8 A at 12 UTC). The live rolling band keeps the
  same split.
- **D-07:** **Width 5-95%**, the same quantiles as the 60-minute band, so consumers read both
  bands the same way. Use an empirical residual quantile band, never mean ± k·std (house rule in
  `ampacity_forecast`).
- **D-08:** **"Actual" for live grading = the weather-computed rating at the target hour.** Hours
  that fell back to static (any gate) or have no computed value are excluded. This measures
  forecast skill rather than fallback policy, and matches how fallback rows are excluded from
  60-minute history (Phase 2 rule).

### Storage and what consumers see
- **D-09:** **New table plus new view; existing contract untouched.** A new `day_ahead_forecast`
  table (name at planner's discretion), unique on (`city`, target hour). It holds at least: issue
  time, target hour, horizon, amps, band lower/upper, band source and n, forecast method
  (`ml_cooling_corrected`), cooling model sha256, band artifact sha256 (or live-band identity),
  `config_fingerprint` / `config_version`, run id and the label (D-11). It is added by a new
  additive migration. `city_rating`, `latest_rating` and its 34-column contract are not changed.
  Same privilege model as Phase 6: `dlr_writer` writes, anon/authenticated get SELECT only, writes
  are revoked explicitly, and RLS is on. — **Reversibility:** one-way — once published, the table
  and view columns become a consumer contract (`rest-api.md`); changing them later needs a
  migration and a contract revision.
- **D-10:** **The view returns all upcoming targets.** Every future target hour that has a value,
  about 3 per city (up to about 12 rows), ordered by city then target. Past values stay readable
  in the table (OD-6: full history public).
- **D-11:** **Label wording.** Every row carries the short, stable label
  `day-ahead-24h; engineering-selection; not-validated`. The contract doc gets a plain-English
  paragraph (wording approved by the owner):
  > A 24-hour-ahead estimate from ml_cooling_corrected. It has more error than the 60-minute
  > forecast because it looks further ahead. On past data (TEST window, Mar-Sep 2026) its typical
  > error was about 23 A (~1.7% of rating) larger. It is the owner's engineering choice, not picked
  > by the signed selection rule, and it never sets or checks the live rating.

  The TEST figures are cited as exploratory (horizon comparison report).
- **D-12:** **Stall detection: a flag in the view plus the existing alarm.** The view (or a
  companion check) exposes a missing/late flag, e.g. no value for a target due within the next
  12 h (the exact rule is planner's discretion, stated in the contract). The permanent freshness
  alarm (runbook §14) also checks it, so a stalled feed produces the same failure email. No new
  cron job.

### Model files and failure policy
- **D-13:** **Use the cooling files in place and add them to the live manifest.** AUSTIN uses
  `data/models/conductor_refit/v3-powersystems-2026-11-02/ml_cooling_corrected_AUSTIN.joblib`;
  CORPUS_CHRISTI, MIDLAND and EL_PASO use the frozen
  `data/shadow/models/ml_cooling_corrected_<CITY>.joblib`. Files are not copied or modified. Their
  paths and sha256 go into `data/models/LIVE_ARTIFACT_HASHES.sha256`, and `dlr_live_check_models.py`
  verifies them before any `joblib.load`. The band artifact (D-05) is verified the same way. If
  Power Systems answers for another city later, that city's refit replaces its entry through the
  normal promotion step (regenerate the manifest, ask before pushing).
- **D-14:** Serving uses each city's **production conductor geometry**
  (`city_point.production_city_point`), consistent with the model each city serves (D-13). Reuse
  Phase 7's `forecast_conductor_refit.make_headline_loader` (hash-verified, refit cities =
  AUSTIN) rather than the bare `load_correction_model`.
- **D-15:** **Day-ahead failures never turn the run red.** The hourly job's exit code reflects
  only the live ratings, as today. Day-ahead outcomes are recorded per city in `pipeline_run`
  (separate fields from the rating outcome, added additively). The catch-up rule (D-04) retries,
  and the view flag plus alarm (D-12) catch a lasting stall.
- **D-16:** **No substitute method.** If cooling cannot produce a value (missing anchor reading,
  missing forecast run, failed load or hash check), nothing is published for that target and the
  reason is logged. The shadow's fallback to `raw_forecast` is not used in production. Every
  published value is `ml_cooling_corrected`.
- **D-17:** **Go-live: push, verify, then expose.** Ask before pushing (standing rule). After the
  owner-approved push: confirm that the first live issue slot writes 4 rows with the correct
  label, band source and hashes, and that the parity test (D-03) passed. Only then grant SELECT on
  the view and table and publish the contract doc. No multi-day soak.

### Claude's Discretion
- Table, view and column names; the exact missing/late rule (D-12); how the band artifact is
  stored and hashed.
- The live-band switch-over threshold (minimum live pairs per city × target hour before D-05
  switches), and whether the switch is per band or all at once. State it in the contract doc.
- How the day-ahead stage is isolated inside the live job (in-process after ratings vs its own
  child process with a timeout). It must fit the job's existing time budget (4 × 300 s per city +
  10 min inside 30 min) without delaying ratings.
- Exactly when within the hour a target counts as due, given the publication lag
  (`_DEFAULT_PUBLICATION_LAG_HOURS` = 6), and how catch-up detects missing targets (read the table).
- Whether live pairs and residuals are computed on the fly from the two tables or stored.

### Deferred Ideas (OUT OF SCOPE)
- Hourly day-ahead issuance (24-29 h leads), only once there is evidence for those leads.
- Any statistical validation or rule-based re-selection of the day-ahead method: this needs a new
  signed protocol (v4 O3) and is a separate phase.
- Day-ahead coverage reporting beyond what the band switch-over needs (e.g. a periodic calibration
  report): possible follow-up.
</user_constraints>

<phase_requirements>
## Phase Requirements

ROADMAP lists "Requirements: TBD". Proposed IDs for the planner to add to REQUIREMENTS.md (a new "Day-ahead cooling forecast (Phase 8)" section and traceability rows) and to ROADMAP.md. They are proposals for the owner's confirmation, not yet decided.

| ID | Description | Research Support |
|----|-------------|------------------|
| DAY-01 | For each city, one `ml_cooling_corrected` value per 00/06/12/18 UTC target hour, from the Open-Meteo run initialised exactly 24 h before the target, issued by a separate stage of the hourly live job after the ratings. A target missing at its first chance is issued by a later hourly run while the target hour is still in the future; the row records its actual issue time. Nothing is published once the target has passed. (D-01, D-02, D-04) | "Due-time and catch-up" below; `fetch_live_forecast_for_valid_time` strict lookup; table-as-state catch-up |
| DAY-02 | The value is computed through the shadow functions unchanged (`fetch_live_forecast_for_valid_time`, `fetch_live_anchor_observation`, `_enrich_city_frame_for_correction`, `CoolingCorrectionShadowMethod.predict`) under `city_point.production_city_point`, with models loaded through hash-verified `make_headline_loader`. A parity test shows production equals the shadow path for the same inputs. No substitute method: no value means no row. (D-03, D-13 loading, D-14, D-16) | "Calling the frozen shadow path"; verified offline end-to-end chain |
| DAY-03 | Each value carries a 5-95% empirical residual-quantile band, one per city x target hour (16). At launch the band comes from a hashed TEST-split artifact verified before use; per band it switches to the live rolling residual band when enough live pairs exist. Each row records `band_source` and its sample size. (D-05, D-06, D-07, D-08) | "Uncertainty band" below |
| DAY-04 | Isolation: the stage never delays, blocks or changes live ratings, G6 stays `ml`, and the runner's exit code is fixed from the ratings before the stage starts. Day-ahead outcomes are stored per city in `pipeline_run` through an additive column. The stage fits inside the existing 30-minute envelope. (D-02, D-15) | "Live job integration" below |
| DAY-05 | A new additive migration creates the day-ahead table (unique on city and target hour) with identity columns (cooling model sha256, band identity, `config_fingerprint`, `config_version`, run id, pipeline version) and the label; `dlr_writer` writes, anon/authenticated get no privilege until the expose step, RLS is on, writes are revoked explicitly. `city_rating`, `latest_rating` and the 34-column contract are unchanged. (D-09, D-11) | "Supabase" below; Phase 4 and Phase 6 migration patterns |
| DAY-06 | A second additive migration exposes a read-only view of upcoming targets (all future targets with a value, ordered by city then target) plus a missing/late flag, grants SELECT only, and the contract doc (`rest-api.md`, new schema doc, `pss_e_handoff.md` pointer) states the label, the band rule and the late rule. The doc's column table is guarded by a parse test against a Python contract module. (D-10, D-11, D-12) | "Supabase"; `rest_api_doc_test` pattern |
| DAY-07 | The permanent freshness alarm also fails for a stalled day-ahead feed (no value for a target due within the next 12 h), through the existing `rpc/assert_fresh` URL, with no new cron job and no unarmed-before-go-live false alarm. (D-12) | "Freshness alarm" below |
| DAY-08 | Go-live is owner-gated: schema apply, then code push, then verification of the first issue slot (label, band source, hashes, parity test passed), then the expose migration and the published contract doc. (D-17) | "Go-live sequence"; Open Question 2 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

No `./CLAUDE.md` exists in the repo, and no project skills. The user's global `~/.claude-edu/CLAUDE.md` only defines the graphify trigger. Directives that apply, from the phase prompt, memory and repo history:

- Run tests with `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider <files>`; run scripts with `PYTHONPATH=backend`. Local-Postgres tests need `DLR_TEST_PG_AUTOSTART=1`.
- Ask before any `git push`. Schema applies and pushes are owner-gated `[BLOCKING]` steps. The repo is public: no project host, pooler reference or key in any committed file (secret scan covers all tracked files).
- Frozen, do not edit: the 15 files and `data/shadow/models` listed in `backend/tests/golden_shadow_capture.py:65-83`, `shadow_collect.yml`, the 12 frozen Drake artifacts, the shadow logs.
- Applied migrations are pinned by sha256 and never edited; changes go in new additive migrations.
- Anti-peeking: never read shadow-log outcomes with `valid_time` after 2026-09-29; never open `data/experiment/anchored_pair_frame_*_2026-09-30_*`.
- Owner-facing checkpoints open with a short plain-English summary (memory: explain-decisions-plainly). Static-rating fallback is safe; the day-ahead value has no safety role (memory: static-rating-fallback-is-safe).
- Times the owner gives are Central 12-hour; convert to UTC explicitly (memory: user-times-are-central-12h). Central is UTC-6 since 2026-11-01.

## Summary

The phase is integration work on proven parts, not new modelling. Every function the value needs already exists in the frozen shadow module and works under any `CityPoint`. The refit, loader, manifest, store, runner and exposure patterns each have a Phase 4 to 7 precedent with tests. The risk is therefore concentrated in four places: (1) keeping the hourly job's red/green rule and time budget untouched; (2) the order in which schema, code and exposure go live; (3) the many tests and ops SQL files that pin "exactly these two public objects / 12 run-log columns / 8 model files / 30-minute arithmetic"; and (4) being honest in the contract about how the TEST band differs from live conditions.

Mechanically, a target hour `T` (UTC hour divisible by 6) becomes issuable at `T - 24 h + 6 h = T - 18 h` and stays issuable while `T` is in the future. The hourly run at minute 05 therefore issues one new target per city every 6 hours (the 06:05, 12:05, 18:05 and 00:05 UTC runs), and any missing earlier target as catch-up. The table itself is the state: a target is missing if its (city, valid_time) key has no row.

**Primary recommendation:** one child process per city for the day-ahead stage (isolation from the hung-HTTP failure mode seen on GitHub runners), launched from `dlr_live_run.run_live` after `state["exit_code"]` is computed from the ratings, with the stage default OFF in `run_live` and ON from `main`, so the 23 existing runner tests stay offline and unchanged.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Compute one `ml_cooling_corrected` value (fetch run, read anchor, features, predict) | API / Backend (runner child process on GitHub Actions) | — | Needs provider secrets and the committed model files; only the runner has both (D-02) |
| Decide which targets are due or missing (catch-up) | Database / Storage (the table is the state) | API / Backend (reads it, computes the grid) | A target is missing iff its key has no row; no extra state file survives on ephemeral runners |
| Band: launch band | CDN / Static -> repo artifact (hashed JSON in git) | API / Backend (verifies hash, applies offsets) | Reproducible, reviewable, no database dependence at launch (D-05) |
| Band: live rolling band | Database / Storage (join of two tables) | API / Backend (quantile, same rule as `forecast_ampacity`) | Pairs already live in `day_ahead_forecast` and `city_rating`; computing on the fly avoids a third store |
| Hash verification before any `joblib.load` | API / Backend | Pre-flight step (non-secret) | A joblib file is a pickle; verify bytes first (Phase 5 T-05-16/17) |
| Label, identity, unit documentation | Database / Storage (columns + comments) | Docs | Consumers see identity in data, never by code reading (DB-06) |
| Read access and write protection | Database / Storage (grants, RLS, security-invoker view) | — | Privilege is the lock, RLS the second lock (OD-6, 06-RESEARCH) |
| Stall detection | Database / Storage (`assert_fresh` function and view flag) | External (cron-job.org alarm, unchanged) | The alarm only calls one URL; extending the function behind it needs no new job (D-12) |
| Run outcome record | Database / Storage (`pipeline_run`, private) | API / Backend (runner is the only writer) | Keeps redacted error text out of the public table (OD-6) |

## Standard Stack

### Core

No new external package is needed. Everything below is already pinned in `requirements.txt` and installed in `.venv`.

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 | Frames, UTC timestamps | Already the shadow path's frame type [VERIFIED: `.venv/bin/python -m pip list`] |
| numpy | 2.4.3 | `np.quantile` for the band | Same call `ampacity_forecast.forecast_ampacity` uses [VERIFIED: pip list; backend/ampacity_forecast.py:522-523] |
| scikit-learn / joblib | 1.9.1 / 1.6.0 | The cooling model (a `CoolingCorrectionModel`) | Version pinned to the one the artifacts were written with; the golden test fails on a library drift [VERIFIED: pip list; backend/tests/cond02_shadow_golden_test.py:98-106] |
| psycopg | 3.3.6 | Writer connection to Postgres | The store already uses it [VERIFIED: pip list; requirements.txt] |
| pytest | 9.0.3 | Tests | Repo standard [VERIFIED: pip list] |

### Supporting (in-repo modules to reuse, not new packages)

| Module | Purpose | When to Use |
|--------|---------|-------------|
| `forecast_shadow_pipeline` | The five shadow functions (D-03) | Unchanged calls from the new module and its child |
| `forecast_conductor_refit.make_headline_loader` | Hash-verified model loading, records `served` (path, sha256, source) | D-14; also supplies the `cooling_model_sha256` value |
| `dlr_live_check_models` | `sha256_file`, `read_manifest`, `check`, `write_manifest` | D-13 manifest growth |
| `supabase_store` | `connect`, `run_context`, `rating_config_fingerprint`, `file_sha256`, `finite`, `redact`, `slot_of` | Row building and identity |
| `dlr_live_run` | `run_city` pattern, `redact`, `child_argv` pattern | Day-ahead child runner |
| `tests/local_pg.py` | Throwaway local Postgres harness | Migration and privilege tests |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| One child per city | One in-process loop after ratings | In-process cannot interrupt a hung HTTP call; the shadow collector adopted per-city children for exactly this (forecast_shadow_collect.py module docstring, "Process model (2026-10-13)"). Use children |
| Replace `assert_fresh` behind the existing alarm URL | A second RPC plus a second cron-job.org job | D-12 forbids a new cron job; extending the function is the only way to keep one URL |
| JSON band artifact | A `.joblib` band object | JSON is not a pickle, so no code runs on load; still hash-verified like the models |

**Installation:** none. `pip install` is not part of this phase.

**Version verification:** versions above were read from `.venv/bin/python -m pip list` on 2026-11-07 and match `requirements.txt` (pandas==2.3.3, numpy==2.4.3, scikit-learn==1.9.1, psycopg==3.3.6, pytest==9.0.3). [VERIFIED: requirements.txt; pip list]

## Package Legitimacy Audit

No external packages are installed by this phase, so the audit is empty by construction.

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| (none) | — | — | — | — | — | — |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 cron-job.org (hourly, minute 05) --workflow_dispatch--> GitHub Actions: dlr_live.yml (timeout 30 min)
   step: pre-flight  dlr_live_check_models.py  (hash-check 8 live files; day-ahead files = NON-FATAL tier, see Pitfall 1)
   step: dlr_live_run.py  (main)
     |
     v
   run_live: for each city -> dlr_orchestrator child (300 s kill)  --> city_rating row / pipeline_run row
     |
     v   state["finished_at"] set; exit_code computed from ratings ONLY; run row saved   <- D-15 frozen here
     v
   day-ahead stage (in main only; try/except everything; remaining-budget gate)
     for each city (sequential, own child process, cwd = repo root, child_env incl. secrets):
       dlr_day_ahead child:
         connect(writer) -> read existing valid_time keys for the city (table = state)
         now = utc now;  due = grid T in (now, now+18h]  minus existing keys     (none due -> exit 0, "none_due")
         verify band artifact sha256 vs manifest -> parse; make_headline_loader(version, refit_cities) verifies model sha256
         anchor = shadow.fetch_live_anchor_observation(city, now)                 (once per city per run)
         for each due T (earliest first):
           row,_ = shadow.fetch_live_forecast_for_valid_time(city, T, 1440, lat, lon, decision_time=now)
           frame = shadow.validate_and_prepare_shadow_row(row, city=city)
           frame = shadow._enrich_city_frame_for_correction(frame, anchor=anchor, city=city, valid_time=T, geometry=point)
           amps  = shadow.CoolingCorrectionShadowMethod(model).predict(frame, point)
           band  = live-rolling if n_pairs >= N_MIN else TEST artifact offsets      (point + offset, clamp guard)
           INSERT ... ON CONFLICT (city, valid_time) DO NOTHING                     (first write wins, issued_at kept)
         write --output JSON {issued, skipped, reasons(redacted), band_source, durations}
     runner classifies each child -> state["day_ahead"] -> upsert pipeline_run subset (best effort, never changes exit code)
     |
     v
   Postgres:  day_ahead_forecast (public, RLS, writer insert/select)    pipeline_run.day_ahead (private jsonb)
              [migration 1: write side]  ...owner verifies first slot...  [migration 2: view + anon SELECT + assert_fresh clause]
     |
     v
   consumers (anon key): GET day_ahead view / status;   cron-job.org alarm: GET rpc/assert_fresh (same URL, extended body)
```

### Recommended Project Structure

```
backend/
├── day_ahead_forecast.py     # constants (label, refit version, lag, grid), due_targets(), artifact resolver, compute_value(), build_row()
├── day_ahead_band.py         # build (offline) / load_verified / live_rolling_offsets / apply (point + offset, clamp)
├── dlr_day_ahead.py          # child CLI: one city; --output JSON; the only file that opens a DB connection for this stage
├── day_ahead_contract.py     # Python twin of the view columns (like latest_rating_contract.py); guarded by a doc-parse test
├── dlr_live_run.py           # + stage (default off in run_live, on in main); + step-summary lines when state has day_ahead
├── dlr_live_check_models.py  # + day-ahead artifact list, lazy imports (cycle!), non-fatal tier
├── live_run_log.py / supabase_store.py   # + optional `day_ahead` run-row key
data/day_ahead/day_ahead_bands_v1.json    # band artifact (text; no .gitignore change needed)
supabase/migrations/<ts>_day_ahead_forecast_store.sql     # migration 1 (write side)
supabase/migrations/<ts>_expose_day_ahead_forecast.sql    # migration 2 (view, grants, policy, assert_fresh)
supabase/ops/verify_exposure.sql                           # generalised published-object list
docs/data-science/schema/day_ahead_forecast_v1.md          # own doc (see Pitfall 7)
docs/integration/rest-api.md                               # new section + column table (parsed by test)
backend/tests/day_ahead_*_test.py                          # see Validation Architecture
```

### Pattern 1: Calling the frozen shadow path under the production point

**What:** Resolve the production point once, pass it as the `geometry` argument. Nothing in the shadow module is edited.

**Evidence (all read this session):**
- `fetch_live_forecast_for_valid_time(city, valid_time, horizon_minutes, *, lat, lon, decision_time=None)` returns `(row, ShadowTimestamps)` [VERIFIED: backend/forecast_shadow_pipeline.py:228-231]. It derives the run as `valid_time - horizon`, rejects a `decision_time` earlier than `init + lag`, retries transport failures, raises `StaleOrMissingDataError` on an unavailable run, and does a STRICT lookup of exactly `valid_time` (lines 264-337).
- `fetch_live_anchor_observation(city, decision_time, *, lookback_hours=_ANCHOR_LOOKBACK_HOURS_DEFAULT)` returns a Series with `anchor_wind_speed`, `anchor_wind_direction`, `anchor_air_temp`, `anchor_observation_time`, `anchor_source`, `anchor_station` [VERIFIED: forecast_shadow_pipeline.py:376-378, 554-561]. `_ANCHOR_LOOKBACK_HOURS_DEFAULT = 6.0` [VERIFIED: forecast_shadow_pipeline.py:373].
- `fetch_shared_city_inputs(city, *, valid_time, decision_time, horizon_minutes)` does both fetches and never raises for a fetch failure [VERIFIED: forecast_shadow_pipeline.py:699-739].
- `_enrich_city_frame_for_correction(forecast_frame, *, anchor, city, valid_time, geometry)` is a pure, no-fetch enrichment that uses `geometry.bearing_deg` for the two perpendicular-wind columns [VERIFIED: forecast_shadow_pipeline.py:742-799].
- `CoolingCorrectionShadowMethod.predict(self, frame, geometry)` calls `predict_cooling_correction` then `apply_cooling_correction(frame, prediction.q_conv, geometry)` [VERIFIED: forecast_shadow_pipeline.py:987-990]. The model recomputes its own convective term from `model.conductor` (fixed at fit time), and only the final heat balance uses `geometry.conductor` [VERIFIED: backend/forecast_correction_models.py:553-563, 598-604].
- The shadow collector passes `geometry = city_point.city_point(city)` (Drake) explicitly to `_enrich_city_frame_for_correction` and to `method.predict` [VERIFIED: backend/forecast_shadow_demo.py:216, 280-283, 290]. Nothing reads module-level Drake config on the way: `validate_and_prepare_shadow_row` calls `city_point.city_point(city)` only as a closed-set city check and to set `frame.attrs["geometry"]` [VERIFIED: forecast_shadow_pipeline.py:656, 677].
- `production_city_point(city)` [VERIFIED: backend/city_point.py:77] returns a `CityPoint` with the same attributes `predict` reads (`bearing_deg`, `conductor`).

**Offline end-to-end proof (run this session, real hash-verified artifacts, synthetic weather):**

```
refit cities: {'AUSTIN'}   RATING_CONFIG_VERSION v3-powersystems-2026-11-02
AUSTIN          model T_max 100.0  prod T_max 100.0  drake T_max 75.0  amps prod 1726.683  amps drake 1736.747
CORPUS_CHRISTI  model T_max 75.0   prod T_max 75.0   drake T_max 75.0  amps prod 1485.586  amps drake 1485.586
MIDLAND         model T_max 75.0   prod T_max 75.0   drake T_max 75.0  amps prod 1279.586  amps drake 1279.586
EL_PASO         model T_max 75.0   prod T_max 75.0   drake T_max 75.0  amps prod 1154.19   amps drake 1154.19
served: AUSTIN refit 31fe8d9b..., CORPUS_CHRISTI frozen 8f50c799..., MIDLAND frozen cdd0a2c9..., EL_PASO frozen f64f9872...
```

So production equals the shadow value exactly for three cities and differs for AUSTIN only through the heat balance (D-03 planner note holds). [VERIFIED: ad hoc run this session, `PYTHONPATH=backend .venv/bin/python`]

**Example:**
```python
# Source: composed from the verified signatures above; ran offline this session
import city_point, forecast_conductor_refit as fcr, forecast_shadow_pipeline as shadow

DAY_AHEAD_REFIT_VERSION = "v3-powersystems-2026-11-02"   # pinned constant, NOT config.RATING_CONFIG_VERSION (Pitfall 9)
refit = {c for c in config.LOCATIONS if fcr.production_differs(c)}          # {'AUSTIN'} today
loader = fcr.make_headline_loader(DAY_AHEAD_REFIT_VERSION, refit, root=fcr.REFIT_ROOT,
                                  frozen_manifest=fcr.FROZEN_MANIFEST)
model = loader(city, "ml_cooling_corrected")             # hash-checked before joblib.load
point = city_point.production_city_point(city)
lat, lon = config.CITY_COORDINATES[city]
anchor = shadow.fetch_live_anchor_observation(city, now)                  # once per city per run
row, ts = shadow.fetch_live_forecast_for_valid_time(city, T, 1440, lat=lat, lon=lon, decision_time=now)
frame = shadow.validate_and_prepare_shadow_row(row, city=city)
frame = shadow._enrich_city_frame_for_correction(frame, anchor=anchor, city=city, valid_time=T, geometry=point)
amps = float(shadow.CoolingCorrectionShadowMethod(model).predict(frame, point))
```

`_enrich_city_frame_for_correction` is underscore-private; D-03 names it, so the call is intended. Pin it with the parity test so a rename in the (frozen) module cannot go unnoticed.

### Pattern 2: Due time and catch-up (D-01, D-02, D-04)

**Constants:**
- Lag: `_DEFAULT_PUBLICATION_LAG_HOURS = 6.0` [VERIFIED: forecast_shadow_pipeline.py:189]. `config.FORECAST_EXPERIMENT_PREVIOUS_RUNS_PUBLICATION_LAG_HOURS` is read with `getattr` and is defined nowhere in `backend/` (grep of all files this session), so the effective lag is 6.0 h.
- Open-Meteo's own statement: a run "is generally accessible from approximately 04-06 UTC onwards" for a 00 UTC run, "typically 4-6 hours for global models (e.g. ECMWF IFS, GFS)". [CITED: https://open-meteo.com/en/docs/single-runs-api] The 6 h constant is the upper end, so the catch-up rule has margin.
- Fetch retry policy: `_FORECAST_FETCH_ATTEMPTS = 3`, `_FORECAST_FETCH_DAYS = 2`, `_FORECAST_FETCH_TIMEOUT_S = 30`, `_FORECAST_FETCH_RETRY_DELAY_S = 20` [VERIFIED: forecast_shadow_pipeline.py:210, 223-225]. Worst case per forecast fetch is 3 x 30 + 2 x 20 = 130 s (comment at lines 198-209).
- `SingleRunUnavailable` (HTTP 400 "not available", or HTTP 200 with every variable null) is converted to `StaleOrMissingDataError` and is NOT retried inside the call [VERIFIED: open_meteo_forecast_provider.py:486-531; forecast_shadow_pipeline.py:293-297]. The next hourly run is the retry.
- Model: `config.SHADOW_LIVE_FORECAST_MODEL: str = "gfs_seamless"` [VERIFIED: backend/config.py:983].

**Rule (recommended):** at decision time `t` (the actual UTC now, not the floored window end), a target `T` on the UTC grid (`T.hour % 6 == 0`, minute 0) is *due* iff `t < T <= t + 18 h`. Equivalently `T - 24 h + 6 h <= t` and `T` still in the future. It is *missing* iff the table has no row for (city, T). The lower bound `t >= T - 18 h` must be checked before the fetch, because the shadow function raises if `decision_time < availability_time` (lines 267-276).

Consequences, hand-checked:
- Steady state: the new target first becomes due at hh:00 for hh in {06, 12, 18, 00}, so the hh:05 runs of those hours issue one new target per city (4 rows per 6 h). Every other hourly run does nothing unless something is missing.
- At any moment about 3 targets per city are due or issued ahead (`T` in `(t, t+18h]`), which matches D-10's "about 3 per city".
- The first run after go-live issues every due target (up to 3 per city, 12 rows), with different issue-to-target leads.
- Targets are at most 18 h ahead of issue time and at least 0: the "24 h" in the label is the age of the weather run, not the lead from the issue time. Say this plainly in the contract (Pitfall 11).

**Where the three setups differ (anchor "now" reading versus target):**

| Setup | Anchor reading time | Evidence |
|-------|--------------------|----------|
| TEST (band source) | exactly `T - 24 h` | `anchor["datetime_utc"] = anchor["anchor_datetime_utc"] + lead_td`, i.e. valid = anchor + 24 h [VERIFIED: backend/forecast_experiment.py:622]; rows_production.csv row 1 has `anchor_time` 2026-03-17 00:00 for `valid_time` 2026-03-18 00:00 |
| Shadow collector (reads 1-2) | about `T - 12 h` (valid time is the next grid hour 11 to 17 h ahead) | `_resolve_next_valid_time`: `candidate = (now + 12h).floor("6h")`, `while candidate <= now + 11h: candidate += 6h` [VERIFIED: backend/forecast_shadow_demo.py:173-176] |
| This phase if issued at first availability | about `T - 18 h`; later for catch-up | derived above |

D-03 fixes the choice ("now" reading, shadow functions). The planner should record `anchor_observation_time` and `issued_at` on every row so the difference is visible, and state it in the contract (Open Question 3).

### Pattern 3: Live job integration (D-02, D-15)

**Facts (all read this session):**
- `run_live` runs one `dlr_orchestrator.py` child per city, each killed at `CITY_TIMEOUT_S = 300` [VERIFIED: backend/dlr_live_run.py:75]; `STORE_ARGS = ("--store", "postgres", "--no-run-row")` [VERIFIED: dlr_live_run.py:81]. The runner is the only `pipeline_run` writer.
- After the loop: `state["finished_at"] = _stamp(...)`, `save_run_row()`, then `state["exit_code"] = 0 if all(live_run_log.is_healthy(r) for r in records) and run_log["failed"] == 0 else 1` [VERIFIED: dlr_live_run.py:426-428].
- Workflow: `timeout-minutes: 30` [VERIFIED: .github/workflows/dlr_live.yml:45]. The comment and `dlr_live_workflow_test.py` pin the arithmetic: `child_seconds == 1200` and `child_seconds <= (timeout - 10) * 60`, so the pinned envelope has zero slack [VERIFIED: backend/tests/dlr_live_workflow_test.py:55-65]. The same file pins `run: PYTHONPATH=backend python backend/dlr_live_run.py` exactly (line 93) and the pre-flight run line (line 103).
- Runbook test pins `` `CITY_TIMEOUT_S` = 300 s ``, `4 cities x 300 s` and `timeout-minutes: 30` [VERIFIED: backend/tests/dlr_live_runbook_test.py:98-107].

**Recommended structure:**
1. Do not touch `dlr_live.yml` (so no workflow pin changes). The stage runs inside `dlr_live_run.main`.
2. Compute `state["exit_code"]` from the ratings first (unchanged expression). Then run the stage inside `try/except Exception`. A later failure can only add a `day_ahead` record; it can never reach the exit code. This makes D-15 structural, not conventional.
3. One child per city, sequential, `cwd=REPO_ROOT` (paths in `REFIT_ROOT` and `SHADOW_MODEL_DIR` are cwd-relative), the same `child_env` (secrets plus `GITHUB_RUN_ID`), a per-child kill timeout and an `--output` JSON, mirroring `run_city`/`classify`.
4. Time budget without editing the pinned envelope: treat 1200 s as the shared child budget. `remaining = 1200 - (seconds the rating children used)`; start a city's day-ahead child only if `remaining >= 60`; give it `min(DAY_AHEAD_CITY_TIMEOUT_S, remaining)`. Recommended `DAY_AHEAD_CITY_TIMEOUT_S = 150` `[ASSUMED]` (healthy runs take seconds; worst single forecast fetch is 130 s). Because the ratings alone can already use all 1200 s, in the worst case the stage is simply skipped and recorded as `skipped_budget`; catch-up covers it. Alternative: raise `timeout-minutes` to 40 and update the two pins, but that needs workflow and runbook edits and an owner decision.
5. Default the stage OFF in `run_live(..., day_ahead=False)` and turn it ON in `main` (with a `--no-day-ahead` switch for local runs). The 23 tests in `dlr_live_run_test.py` call `run_live` directly with a fake orchestrator and a `requests.get` guard; an always-on default would make them spawn real children.
6. Set `state["day_ahead"]` and save the run row once more after the stage. Count that write separately (not in `run_log["failed"]`, whose value feeds the exit code). Show it in the step summary only when present, because `test_step_summary_*` and the `pipeline_run: 3 writes, 0 failed` pin (dlr_live_run_test.py:700) assume today's text.
7. Note the semantic shift: `finished_at` then means "ratings finished". Document it in the runbook; it is the lesser evil compared with leaving `finished_at` null while the stage runs.

**pipeline_run additive field.** `PIPELINE_RUN_COLUMNS` has 12 names, `PIPELINE_RUN_JSONB = ("cities_failed", "provider_errors", "sources")` [VERIFIED: backend/supabase_store.py:76-90]. Add one jsonb column `day_ahead` (per-city objects: `outcome` in `none_due | issued | partial | error | timeout | skipped_budget`, `due`, `issued`, `missing` as ISO times, redacted `reasons`, `band_source`, `duration_s`). Add it last in `PIPELINE_RUN_COLUMNS` and in `PIPELINE_RUN_JSONB`. `upsert_run` already accepts any subset including `run_id` and binds jsonb through a cast (supabase_store.py:762-806), so the stage can send `{run_id, day_ahead}` alone.

### Pattern 4: Model manifest (D-13)

**Facts:**
- `MANIFEST_PATH = os.path.join("data", "models", "LIVE_ARTIFACT_HASHES.sha256")`, `KINDS: tuple[str, ...] = ("forecast", "anomaly")` [VERIFIED: backend/dlr_live_check_models.py:51, 53]. `required_artifacts()` returns `(kind, city, path)` for 8 files; `check()` does presence, then hash against the manifest (never loading while a problem is open), then strict loads only via the two production loaders; `write_manifest()` hashes exactly `required_artifacts()`. Manifest format is sha256sum text, one `<64 hex>  <repo-relative path>` per line with `#` comments (lines 20-27, 80-100, 163-190).
- The live manifest today has 8 lines plus a header [VERIFIED: data/models/LIVE_ARTIFACT_HASHES.sha256]. The refit manifest key format is repo-relative with forward slashes (e.g. `data/models/conductor_refit/v3-powersystems-2026-11-02/ml_cooling_corrected_AUSTIN.joblib`) [VERIFIED: that directory's ARTIFACT_HASHES.sha256]. The four cooling hashes and their paths are already in the two source manifests (refit: AUSTIN `31fe8d9b...`; frozen: CORPUS_CHRISTI `8f50c799...`, MIDLAND `cdd0a2c9...`, EL_PASO `f64f9872...`).
- `make_headline_loader(config_version: str, refit_cities, root: str = REFIT_ROOT, frozen_manifest: str = FROZEN_MANIFEST)` [VERIFIED: forecast_conductor_refit.py:347-348]; constants `REFIT_ROOT = os.path.join("data", "models", "conductor_refit")`, `MANIFEST_NAME = "ARTIFACT_HASHES.sha256"`, `FROZEN_MANIFEST = os.path.join(REPO_ROOT, "data", "shadow", "models", MANIFEST_NAME)` [VERIFIED: forecast_conductor_refit.py:65-69]. The refit branch reads the bytes once, hashes them and loads those same bytes. The frozen branch hashes the path, then calls the path-based `load_correction_model` (a small check-to-load window, stated in the module docstring, lines 22-28).
- `production_differs(city)` is true only for AUSTIN today [VERIFIED: ran this session; backend/forecast_conductor_refit.py:396].

**Recommended extension:**
- Add `required_day_ahead_artifacts()` (kinds `day_ahead_cooling` per city and `day_ahead_band`) and make `check()` and `write_manifest()` iterate over both lists. Keep `required_artifacts()` returning the original 8, so `test_all_present_and_matching_passes` (`len(expected) == 8`) stays valid. The count-sensitive assertions that must change: `dlr_live_check_models_test.py` lines 76-92 (OK message "all 8"), 183-194 (`len(lines) == 8`).
- Resolve the serving file per city with `production_differs(city)` and a pinned refit version constant. Do both imports (`forecast_conductor_refit`, `day_ahead_forecast`) lazily inside functions. `forecast_conductor_refit` imports `dlr_live_check_models` at module top (line 57), so a top-level import in the other direction is a circular import (Pitfall 2).
- The cooling "strict load" in the pre-flight should be the same loader (`make_headline_loader(...)(city, "ml_cooling_corrected")`), which verifies the refit and frozen manifests independently.
- `.gitignore`: the cooling files are already tracked (`!/data/models/conductor_refit/`, `data/shadow/models` is not ignored). Put the band artifact at `data/day_ahead/day_ahead_bands_v1.json`: `git check-ignore -v` returned exit 1 (not ignored) for it and exit 0 (ignored by `/data/models/*`) for `data/models/day_ahead/...` [VERIFIED: ran this session]. No `.gitignore` edit is then needed. Never write under `data/shadow/models` (frozen path, golden test checks `git status --untracked-files=all` there).

### Pattern 5: Uncertainty band (D-05 to D-08)

**Convention:** `ci = point + np.quantile(residuals, q)` with `residual = actual - prediction`, `q` from `FORECAST_BACKTEST_QUANTILES`, lower edge first; if `ci_lower > point or ci_upper < point`, both edges are clamped to the point and a warning is logged [VERIFIED: backend/ampacity_forecast.py:516-536; `residuals[offset] = float(series.iloc[i]) - prediction` at line 436]. `FORECAST_BACKTEST_QUANTILES: tuple[float, float] = (0.05, 0.95)` [VERIFIED: backend/config.py:506]. Never mean +/- k sigma.

**Launch band (reproducible, no network):**
- Source rows: `docs/data-science/exploratory/2026-11-02_horizon_comparison/rows_production.csv`, tracked in git, columns `city, valid_time, anchor_time, truth_amps, ml_wind_corrected, ml_cooling_corrected, ...`. I checked it this session: 3136 rows, `valid_time` 2026-03-18 00:00 to 2026-09-29 18:00 UTC, no nulls, exactly 196 rows in each of the 16 city x hour groups. [VERIFIED: ran pandas against the file]
- Residual: `truth_amps - ml_cooling_corrected`. Per group, offsets `lower = np.quantile(res, 0.05)`, `upper = np.quantile(res, 0.95)`. Sample values this session: AUSTIN 00 UTC (n 196) lower -245.75, upper +274.55; AUSTIN 18 UTC lower -297.93, upper +184.25; EL_PASO 06 UTC lower -340.64, upper +235.06; all 16 groups have lower < 0 < upper. [VERIFIED: ran this session]
- Provenance: `build_rows.py` (same folder) rebuilds the rows in memory with `forecast_test_split_score.cached_test_provider` (reads only the `_2024-01-20_2026-09-29_` cache), `forecast_shadow_confirm._score_city` and `make_headline_loader`, under `production_city_point` [VERIFIED: build_rows.py:76-83 loader_and_resolver, 163-205 main]. The cache files live in gitignored `data/experiment/`; the committed CSV makes the artifact reproducible in CI without them. Record the CSV's sha256 inside the artifact.
- Artifact: `{"schema": 1, "quantiles": [0.05, 0.95], "residual": "truth_amps - ml_cooling_corrected, amperes", "rows_file": <path>, "rows_sha256": <hex>, "valid_time_min": ..., "valid_time_max": ..., "bands": {city: {"0": {"n": 196, "lower_offset_amps": ..., "upper_offset_amps": ...}, "6": ..., "12": ..., "18": ...}}}`, written with `json.dumps(obj, sort_keys=True, indent=2) + "\n"` so the bytes (and hash) are deterministic. Store offsets, not absolute edges, so `band = point + offset` exactly as the 60-minute band does.
- Anti-peeking guards in the builder: assert `valid_time.min() >= 2026-03-18T00:00Z` and `.max() < 2026-09-30T00:00Z` (same constants as `forecast_test_split_score.py:59-60`); read only that CSV; never open `data/experiment/anchored_pair_frame_*_2026-09-30_*` (the repo has `core.assert_not_fresh_experiment_cache` for paths); never import `read_city_log_entries` or touch `data/shadow/predictions`. Enforce with an AST/grep test over the new modules.

**Live rolling band (D-05, D-08):**
- Pairs are computed on the fly from the two tables: for a band (city, target hour h), join `day_ahead_forecast d` to `city_rating c` on `c.city = d.city and c.valid_time = d.valid_time`, with `extract(hour from d.valid_time at time zone 'UTC') = h`, `c.status = 'ok' and c.fallback = false and c.exhausted = false` (computed, non-fallback, has a value), `c.config_fingerprint = d.config_fingerprint` (never pair across a conductor or config change), `c.origin = 'live'`, newest first, limited to a window. Residual = `c.rating_amps - d.amps`. Columns are `status` check in ('ok','fallback'), `fallback boolean`, `exhausted boolean`, `rating_amps` [VERIFIED: supabase/migrations/20261019000000_create_city_rating.sql, columns `status`, `fallback`, `exhausted`, `rating_amps`; `city_rating_status_ck`]. When a row fell back, `rating_amps` holds the static rating (migration comment on `rating_amps`), which is why the filter is on `status`/`fallback`, not on `rating_amps`.
- Slot semantics: `city_rating.valid_time` is the hour-truncated UTC slot of the run window end (OD-7), so the 06:05 run writes the 06:00 row, matching a 06:00 target [VERIFIED: migration column comment on `valid_time`; supabase_store.slot_of at line 392].
- Recommended switch-over `[ASSUMED]`: per band, once `n_live_pairs >= 60`, using the most recent 120 pairs; the live band is used only if `lower < 0 < upper`, otherwise stay on the TEST band. Rationale: each band gets one pair per day, so 30 pairs is a month but puts the 5% quantile on the 1st to 2nd smallest value; 60 pairs (about 2 months) puts it near the 3rd. This is the owner's discretion item; state the chosen numbers in the contract.
- Document the known mismatches between the launch band and live truth: TEST grades against Open-Meteo reanalysis through IEEE 738 (REPORT.md "Setup"), live grades against the composed station-based rating; and TEST anchors sit 24 h before the target (table above). Do not report coverage or skill against live outcomes (deferred, and v4 O3 forbids further evaluation without a new signed protocol).

### Pattern 6: Supabase write side and expose side (D-09, D-10, D-12, D-17)

**Conventions (all read this session):**
- Phase 4 migration: `create table if not exists`, explicit `revoke all ... from anon, authenticated`, RLS enabled, `grant select, insert, update on ... to dlr_writer`, one `dlr_writer_all` policy `for all to dlr_writer using (true) with check (true)`, a `comment on column` for every column with the unit first, no credential in the file [VERIFIED: supabase/migrations/20261019000000_create_city_rating.sql].
- Phase 6 expose migration: index, `create or replace view ... with (security_invoker = true)`, per-column comments, `revoke all on all tables/sequences in schema public from anon, authenticated`, `grant select on public.city_rating, public.latest_rating to anon, authenticated`, `alter default privileges for role postgres ... revoke`, a `create policy city_rating_public_read ... for select to anon, authenticated using (true)` preceded by `drop policy if exists`, `public.assert_fresh(integer)` as security invoker with `set search_path = ''` and schema-qualified names, `notify pgrst, 'reload schema'` [VERIFIED: supabase/migrations/20261026195124_expose_latest_rating.sql]. Note this migration's blanket `revoke all on all tables in schema public` already ran once; a later migration's new table gets no default privilege, but it must still revoke explicitly.
- Applied migrations are pinned: `_ORIGINAL_MIGRATION_SHA256` (supabase_migration_test.py:31) and `_APPLIED_PHASE6_MIGRATION_SHA256` (expose_migration_test.py:36-39). Do not edit the three existing migration files. Add the two new files' hashes to a pin test after they are applied, as Phase 6 did.
- All migrations are applied twice in some tests (`supabase_smoke_test._apply_migration` runs each `_reset`), so each new file must be re-apply safe: `if not exists`, `add column if not exists`, `drop policy if exists` before `create policy`, `create or replace`.

**Recommended two-migration staging ("write first, expose later"):**
1. Migration 1 `..._day_ahead_forecast_store.sql` (applied before the code is pushed): the `public.day_ahead_forecast` table, a CHECK that `valid_time` is on the 6-hour UTC grid, `alter table public.pipeline_run add column if not exists day_ahead jsonb` (+ comment), RLS on, `revoke all ... from anon, authenticated`, `grant select, insert on public.day_ahead_forecast to dlr_writer` (insert only; first-write-wins uses `ON CONFLICT DO NOTHING`; add `update` only if the planner wants re-issue), policy for `dlr_writer`. Grants nothing to anon.
2. Migration 2 `..._expose_day_ahead_forecast.sql` (applied only after the first slot is verified, D-17): the view(s), `grant select` to anon/authenticated, a `for select` read policy, and the extended `public.assert_fresh(integer)`.

**Proposed table (names and columns at planner's discretion; this is a concrete starting point):**

| Column | Type | Note |
|--------|------|------|
| `city` | text | CHECK in the four cities (same list as `city_rating_city_ck`) |
| `valid_time` | timestamptz | target hour, UTC, CHECK `hour % 6 = 0` and minute 0; PK `(city, valid_time)` (D-09) |
| `issued_at` | timestamptz | actual decision time, not `now()` default, so catch-up is visible (D-04) |
| `forecast_run_init_time` | timestamptz | `valid_time - 24 h`, the weather run actually used |
| `horizon_minutes` | integer | always 1440, CHECK = 1440 |
| `forecast_amps` | double precision | CHECK > 0 and finite |
| `ci_lower_amps`, `ci_upper_amps` | double precision | 5% and 95% edges (name them like `forecast_ci_lower_amps`) |
| `band_source` | text | CHECK in ('test-split', 'live-rolling') |
| `band_n` | integer | residual count behind the band |
| `band_artifact_sha256` | text | hex CHECK; the TEST artifact is always the fallback, so always recorded |
| `band_pairs_through` | timestamptz | newest pair used when live-rolling, else NULL |
| `forecast_method` | text | CHECK = 'ml_cooling_corrected' |
| `cooling_model_sha256` | text | hex CHECK; from `loader.served[...]["sha256"]` |
| `cooling_model_source` | text | 'refit' or 'frozen' (also from `loader.served`) |
| `anchor_observation_time`, `anchor_source` | timestamptz, text | provenance of the "now" reading (lead differs by issue time) |
| `config_version`, `config_fingerprint` | text | `config.RATING_CONFIG_VERSION`, `supabase_store.rating_config_fingerprint(city)`, hex CHECK |
| `label` | text | the D-11 string, NOT NULL (pin the value in a Python constant and a test) |
| `run_id`, `run_attempt`, `pipeline_version`, `schema_version` | text, int, text, int | same meaning as `city_rating` |
| `first_written_at` | timestamptz | default `date_trunc('second', now())` |

Do not store exception text or provider error strings in this publicly readable table (OD-6). Reasons go only into the private, redacted `pipeline_run.day_ahead`. Omit MW columns (amps only) to keep the one-way contract small; the doc states how to convert (`rating_mw` and `rating_amps` in `city_rating` use `ercot_dlr_merger.amps_to_mw` with `line_voltage_kv` and `power_factor`).

**View and flag (D-10, D-12).** Recommended: `public.day_ahead_upcoming` (security invoker; rows with `valid_time > now()`, ordered by city then `valid_time`, plus computed `lead_minutes` from `now()`) and a small companion `public.day_ahead_status` that always has four rows (cities from a `values` list left-joined, like `assert_fresh`), with `missing_targets` and `is_late`. Rule recommended: a city is late iff some grid target `T` with `now() < T <= now() + interval '12 hours'` has no row. Why 12 h: such a target became issuable at `T - 18 h`, so it is at least 6 h overdue, six failed hourly attempts. A per-row flag cannot express a missing row, hence the companion.

### Pattern 7: Freshness alarm extension (D-12)

**Facts:** The alarm is a cron-job.org GET of `<SUPABASE_URL>/rest/v1/rpc/assert_fresh`, every 15 minutes, fail-notify after 2 failures, recovery email on; pausing the pipeline also pauses it; cron-job.org disables a job after more than 25 consecutive failures [VERIFIED: docs/data-science/decisions/dlr_live_runbook.md section 14, lines 459-517]. `assert_fresh(max_age_minutes integer default 90)` is `security invoker`, `stable`, `set search_path = ''`, raises SQLSTATE `PT503` with detail `missing=... stale=...`, returns `jsonb` with keys `ok`, `cities`, `max_age_minutes`, `oldest_valid_time` [VERIFIED: expose migration lines 21-66 of the function body quoted in this session].

**Recommendation:**
- Replace the function with `create or replace function public.assert_fresh(max_age_minutes integer default 90)`, the SAME signature. A different signature would create an overload and PostgREST would answer HTTP 300 "could not choose the best candidate function" for the no-argument URL the alarm calls.
- Add the day-ahead clause: for each city, fail with the same `PT503` and an additional `day_ahead_late=...` in the detail when a grid target in `(now, now + 12 h]` has no row. Add `day_ahead_late` to the 200 body as an additive key.
- Arm it only once the table has at least one row (`exists (select 1 from public.day_ahead_forecast)`). Reason: the day-ahead clause must be deployable without a false alarm, and the existing local tests (`test_assert_fresh_contract`, which inserts only `city_rating` rows and expects 200) stay valid unchanged. The cost is that a feed that never started is not alarmed; D-17's manual first-slot check covers that.
- Everything referenced inside the function must be schema-qualified (`public.day_ahead_forecast`), and the anon role needs SELECT on that table plus a read policy because the function runs as the caller. Both come with migration 2, which is why the function change belongs in migration 2, not 1.
- The 503 detail is documented in `rest-api.md` ("Status codes" row for `PT503`); update that row.

### Anti-Patterns to Avoid

- **Importing the shadow logs or any of their readers in the new code** (`read_city_log_entries`, `Persistence24hShadowMethod`, `ReferenceRefit24hShadowMethod`): they read `data/shadow/predictions`, whose rows after 2026-09-29 are off limits.
- **Reading `config.RATING_CONFIG_VERSION` as the refit directory name.** The next conductor change bumps it and the loader then looks for a directory that does not exist. Use a pinned constant (`"v3-powersystems-2026-11-02"`) and bump it together with a new refit, per the promotion step in D-13.
- **Doing the day-ahead work in the runner process.** A hung request cannot be interrupted in-process; use children.
- **Falling back to `raw_forecast` or any other value.** D-16: no value, no row.
- **Writing the band or any new file under `data/shadow/models`, or editing any of the 15 frozen files.**
- **Putting day-ahead columns into `city_rating` or `latest_rating`** (the 34-column contract is pinned by `rest_api_doc_test`, `expose_migration_test`, `verify_exposure.sql`).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Residual quantile band | A new quantile or std-based formula | `np.quantile(residuals, q)` added to the point, with the center-exclusion clamp, as `forecast_ampacity` does | House rule; identical reading for consumers (D-07) |
| File hashing and manifest parsing | Your own sha256 loop or manifest regex | `dlr_live_check_models.sha256_file`, `read_manifest`; `supabase_store.file_sha256` | Strict-format parser with duplicate-path check already exists |
| Hash-verified model load | `joblib.load` on a path | `forecast_conductor_refit.make_headline_loader` (records `served`) | Unpickling runs code; refit bytes verified before load |
| Which cities use the refit | A hard-coded `{"AUSTIN"}` | `forecast_conductor_refit.production_differs(city)` | Tracks the conductor table automatically; D-13 says a later refit replaces a city's entry |
| Config identity on a row | A new hash recipe | `supabase_store.rating_config_fingerprint(city)` and `config.RATING_CONFIG_VERSION` | Same identity the rating rows carry (DB-06); no schema 2 change |
| Per-city child with kill timeout and output file | A new subprocess helper | The `run_city` / `classify` / `child_argv` pattern in `dlr_live_run.py` | Redaction, defanging, timeout handling already tested |
| Secret redaction in logs and run rows | A new regex | `dlr_live_run.redact` / `supabase_store.redact` | Covers DB URL, password, token, key forms |
| UTC slot and run identity | `datetime` string math | `supabase_store.slot_of`, `run_context`, `dlr_live_run.run_identity` | OD-7 semantics already tested |
| Throwaway Postgres for privilege tests | A mock | `backend/tests/local_pg.py` (initdb on 127.0.0.1) | Reproduces Supabase's legacy default grants |
| Doc/contract drift guard | A manual check | A Python contract module plus a parse test, like `latest_rating_contract.py` + `rest_api_doc_test.py` | Contract is one-way; the doc is the only thing consumers get |

**Key insight:** the phase should add almost no new logic. The only genuinely new pieces are the due-target arithmetic, the band artifact builder, and the SQL. Everything else is a call to something with existing tests.

## Runtime State Inventory

Not applicable: this phase adds a feature, it does not rename or migrate anything. For completeness: no existing stored data is renamed, no live service configuration changes (the cron-job.org alarm URL stays the same), no OS-registered state, no new secret names (the stage uses the existing `SYNOPTIC_TOKEN`, `NREL_*`, `SUPABASE_DB_URL`), and build artifacts are unchanged. One deployment-order dependency does exist and is covered in Pitfall 4.

## Common Pitfalls

### Pitfall 1: The model pre-flight is a hard gate, so day-ahead artifact problems would stop live ratings
**What goes wrong:** D-13 asks `dlr_live_check_models.py` to verify the cooling files and band. That step runs before `dlr_live_run.py` and exits 1 on any problem; in GitHub Actions a failed step skips the rest, so a day-ahead hash or load problem would leave every city unrated for the hour. This contradicts D-02 ("never delay, block or change the live ratings") and D-15.
**Why it happens:** the pre-flight was designed (Phase 5, OD-3) so a missing live model can never silently degrade a rating; day-ahead has the opposite requirement.
**How to avoid (recommended):** verify the day-ahead files in a second, non-fatal tier: `check()` returns live-model problems as today (exit 1) and prints day-ahead problems as warnings (exit 0, `::warning::` annotation), while the day-ahead child verifies its own hashes again (the loader does) and refuses to publish, recording the reason in `pipeline_run.day_ahead`. Keep the strong guard offline: a test that the committed cooling and band files match the committed live manifest (like `test_the_committed_models_match_the_committed_manifest`, which runs `check(..., load=False)`). This still satisfies "verified before any `joblib.load`". See Open Question 1; it needs the owner's confirmation because it softens D-13's wording.
**Warning signs:** a pre-flight failure naming a `day_ahead` artifact turning the whole run red.

### Pitfall 2: Circular import between the manifest checker and the refit module
**What goes wrong:** `forecast_conductor_refit` imports `dlr_live_check_models` at module top (line 57). Making the checker import the refit module (to resolve the AUSTIN path or call the loader) at module top creates a cycle and an ImportError at pre-flight.
**How to avoid:** import `forecast_conductor_refit` and the day-ahead module lazily inside the functions that need them. Test with a fresh interpreter: `PYTHONPATH=backend python backend/dlr_live_check_models.py`.

### Pitfall 3: Pinned tests that change on purpose (list them, extend, do not weaken)
Each pins "exactly N" and will fail until updated additively. Known set:
- `supabase_schema_doc_test.py:114` `assert len(run_columns) == 12` and the doc-row equality at lines 113-117, plus `REQUIRED_HEADINGS` (lines 30, 127): do NOT add the `day_ahead` run-log row or a new `##` section to `city_rating_v1.md`; put the new column and table in the new `day_ahead_forecast_v1.md` instead (Pitfall 7).
- `supabase_run_log_test.py:112-113` (`PIPELINE_RUN_COLUMNS == _migration_run_columns()`, `len == 12`): the helper reads only the original `create table` block; extend it to include columns added by additive migrations.
- `live_run_log_test.py:195` (`updated == every non-key PIPELINE_RUN_COLUMNS`): holds only if `live_run_log.build_run_row` emits the same keys; decide emit-always versus omit-unless-present (Pitfall 4) and adjust once.
- `supabase_store.build_run_row` guard `tuple(row) != PIPELINE_RUN_COLUMNS` (supabase_store.py:757).
- `dlr_live_check_models_test.py` "all 8" message and `len(lines) == 8` (lines 76-92, 183-194).
- `expose_migration_test.py` `_VERIFY_CHECKS` (lines 316-335) and `verify_exposure.sql` (Pitfall 6).
- `production_conductor_test.py:209-220`: add the new module to `PRODUCTION_CALLERS` so the production-point rule is pinned for it (extends the list, removes nothing).
- `rest_api_doc_test.py`: add a second parsed column table; the `latest_rating` one stays untouched.
- `dlr_live_runbook_test.py` pins `` `CITY_TIMEOUT_S` = 300 s `` etc.; the runbook may add sections but must keep those strings.

### Pitfall 4: Deploy order, the new run-log column must exist before the runner writes it
**What goes wrong:** if `live_run_log.build_run_row` always includes a `day_ahead` key and the code is pushed before migration 1 is applied, every `save_run_row()` in the rating stage fails with "column does not exist". `run_log["failed"]` then makes `state["exit_code"]` 1 and the live job goes red (supabase_store.py:762-806 shows the statement names exactly the keys given; dlr_live_run.py:428 folds `run_log["failed"]` into the exit code).
**How to avoid:** (a) owner order: apply migration 1, verify, then push code; (b) belt and braces: `build_run_row` adds `day_ahead` only when `state` carries it, so rating-stage saves are identical to today's and only the post-stage save (best effort, not in the exit code) can fail on a missing column.

### Pitfall 5: `assert_fresh` replacement hazards
Overloads break the alarm URL (HTTP 300); an unqualified table name fails under `set search_path = ''`; anon needs SELECT and a read policy on the new table for a security-invoker function to see it; and applying the expose migration before any row exists would make the day-ahead clause fail every 15 minutes, burning toward cron-job.org's 25-failure auto-disable (runbook section 14) unless the clause is armed by the first row. See Pattern 7.

### Pitfall 6: `verify_exposure.sql` and its test hard-code "two public objects"
`verify_exposure.sql` requires `(select count(*) from extra_grants) = 0 and (select count(*) from select_grants) = 4` (line 123), restricts reads to `('city_rating', 'latest_rating')` (lines 62-70) and allows only `assert_fresh` as an anon-executable function (line 73 onward). The check names are pinned by `_VERIFY_CHECKS` (`anon_authenticated_grants_are_select_on_two_objects_only`, `latest_rating_has_34_columns`, ...) and the local-Postgres tests run this very file after applying every migration, so the first run after migration 2 fails. Generalise the published-object list in the SQL (new view, table, status view) and update `_VERIFY_CHECKS`; add new checks for the new objects (column count, comments, security invoker, read policy). Also `e2e_verify_readonly.py` has `HIDDEN_TARGETS = (("public", "pipeline_run"), ("ops", "freshness_log"))` (line 98): `pipeline_run` stays hidden, so it needs no change, and `supabase_smoke.py` `TABLES` (line 55) can optionally gain the new table.

### Pitfall 7: The pinned schema doc cannot take new sections
`supabase_schema_doc_test.py` requires the exact heading list and a run-log table that equals the original 12 columns. Write `docs/data-science/schema/day_ahead_forecast_v1.md` as its own doc (the CONTEXT allows "its own section or doc"), link it from `city_rating_v1.md`'s existing text only if that does not add a heading, and document `pipeline_run.day_ahead` there and in the runbook.

### Pitfall 8: The launch band does not describe live conditions
TEST residuals are against reanalysis truth with anchors exactly 24 h before the target (Pattern 2 table); live residuals are against the station-composed rating, and live anchors are about 18 h (or less, for catch-up). The launch band is therefore an honest starting estimate, not a calibrated live band. Say so in `band_source` semantics and the contract, and let the live rolling band replace it per D-05.

### Pitfall 9: Refit directory name
`make_headline_loader(config_version, ...)` uses `config_version` as a folder name. `RATING_CONFIG_VERSION` equals the folder today (`v3-powersystems-2026-11-02`, config.py:476) by coincidence of the 07-11 refit. Pin the folder name in the day-ahead module.

### Pitfall 10: Stale `frame.attrs["geometry"]`
`validate_and_prepare_shadow_row` sets `frame.attrs["geometry"]` to the Drake point and `_enrich_city_frame_for_correction` copies it (lines 677, 790), even when you pass the production point as `geometry`. `predict` uses only its `geometry` argument, so values are right, but never log or branch on `frame.attrs["geometry"]` (verified this session: `attrs geom is drake: True` for all four cities).

### Pitfall 11: "24 h" is the weather-run age
Rows are issued 0 to 18 h before their target. The contract and label text must not imply a 24 h lead from issue; add `forecast_run_init_time` and `issued_at` so a consumer can compute both.

### Pitfall 12: First run issues up to 12 rows, not 4
D-17 says "the first live issue slot writes 4 rows". With catch-up the first hourly run after go-live issues every due target (up to 3 per city). Either word the check as "every due target gets a row with the right label, band source and hashes" or cap the first run to the newest target per city (Open Question 2).

### Pitfall 13: Position-dependent timeouts on GitHub runners
The shadow collector measured the 3rd and 4th request to the single-runs API timing out inside one process while fresh processes succeeded (forecast_shadow_pipeline.py comment at lines 198-209; forecast_shadow_collect.py INTER_CITY_DELAY_S discussion). A per-city child avoids it. Do not rely on a delay constant; it was measured insufficient at 15 s.

### Pitfall 14: cwd-relative paths
`REFIT_ROOT` and `SHADOW_MODEL_DIR` are relative; the children run with `cwd=REPO_ROOT` (dlr_live_run.py `run_city`). A local run from another directory fails the loader with a manifest or file error. Run the new child with the same `cwd` and `PYTHONPATH=backend`.

### Pitfall 15: Frozen-path test counts untracked files
`test_frozen_sources_are_unchanged_since_baseline` fails on any untracked or modified file under the frozen paths (`git status --porcelain --untracked-files=all`). Keep every new file outside `backend/forecast_shadow_*.py`, `data/shadow/models`, and the other frozen paths in `golden_shadow_capture.py:65-83`.

### Pitfall 16: Public table, public repo
The table is publicly readable by decision (OD-6). No exception text, station provider error or stack trace goes in it. The secret scan walks every tracked file (`secret_scan_test.py:175-185`), so docs and migrations may carry only placeholders like `<SUPABASE_URL>`.

### Pitfall 17: No evaluation against live outcomes
The live band needs residual quantiles, nothing more. Reporting MAE, coverage or "skill" of the day-ahead value against live ratings is the deferred idea and falls under signed v4 O3 (any later evaluation needs a new signed protocol). Keep the new code from emitting such statistics.

## Code Examples

### Due targets and missing targets (pure functions, offline-testable)
```python
# Source: derived rule above; constants verified in forecast_shadow_pipeline.py:189 and the shadow grid at forecast_shadow_demo.py:173-176
import pandas as pd

PUBLICATION_LAG_H = 6          # mirror forecast_shadow_pipeline._DEFAULT_PUBLICATION_LAG_HOURS (read it, do not copy it)
RUN_AGE_H = 24                 # horizon_minutes = 1440
GRID_H = 6

def due_targets(now: pd.Timestamp) -> list[pd.Timestamp]:
    """Grid targets T with now < T <= now + (RUN_AGE_H - PUBLICATION_LAG_H) h."""
    now = pd.Timestamp(now).tz_convert("UTC")
    first = now.ceil(f"{GRID_H}h")
    if first == now:                       # T must be strictly in the future
        first += pd.Timedelta(hours=GRID_H)
    horizon = now + pd.Timedelta(hours=RUN_AGE_H - PUBLICATION_LAG_H)
    out, t = [], first
    while t <= horizon:
        out.append(t)
        t += pd.Timedelta(hours=GRID_H)
    return out
# missing = [T for T in due_targets(now) if T not in existing_keys_for_city]
```

### Band application (same convention as the 60-minute band)
```python
# Source: backend/ampacity_forecast.py:516-536 (convention), applied to stored offsets
def apply_band(point_amps: float, lower_offset: float, upper_offset: float):
    lo, hi = point_amps + lower_offset, point_amps + upper_offset
    if lo > point_amps or hi < point_amps:          # band excludes its own centre: clamp, log
        lo = hi = point_amps
    return lo, hi

# offsets: np.quantile(truth - forecast, 0.05) and (..., 0.95) per (city, UTC hour)
```

### Insert, first write wins
```sql
-- Source: pattern of supabase_store._build_upsert_sql (bound parameters only), with DO NOTHING per D-04
insert into public.day_ahead_forecast (city, valid_time, issued_at, ...)
values (%(city)s, %(valid_time)s, %(issued_at)s, ...)
on conflict (city, valid_time) do nothing
```

### Stage placement in the runner (shape only)
```python
# Source: shape of backend/dlr_live_run.py:426-431, with the new stage after the exit code is fixed
state["finished_at"] = _stamp(datetime.now(timezone.utc))
save_run_row()
state["exit_code"] = 0 if all(live_run_log.is_healthy(r) for r in records) and run_log["failed"] == 0 else 1  # unchanged
if day_ahead:
    try:
        state["day_ahead"] = run_day_ahead_stage(cities, child_env, remaining_budget_s=..., ...)
        save_day_ahead_row()                    # best effort; separate counter; never touches exit_code
    except Exception as exc:                    # noqa: BLE001
        log.error("day-ahead stage failed (%s): %s", type(exc).__name__, redact(exc, env))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Shadow models run only in the shadow collector on Drake | Same functions called from the live job under the production point | This phase | Needs the parity test; AUSTIN legitimately differs from the shadow log |
| One hash manifest per artifact family | Live manifest also lists the shadow-frozen and refit cooling files | This phase (D-13) | Three manifests agree on four hashes; the golden test still pins the frozen one |
| Open-Meteo Single Runs "most models archived from 2nd of April 2026" | Used only for runs at most 24 h old | n/a | No dependency on deep archive; [CITED: https://open-meteo.com/en/docs/single-runs-api] |

**Deprecated/outdated:** none for this phase. The 2026-11-24 FRESH run is retired (signed v4); no new evaluation happens here.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `DAY_AHEAD_CITY_TIMEOUT_S = 150` and "skip a city if less than 60 s of shared budget remain" are the right stage limits | Pattern 3 | Too small drops value on a slow day (catch-up retries it); too large squeezes the 1200 s shared budget. Low impact, owner/planner may retune |
| A2 | Live-band switch-over at 60 pairs per band with a 120-pair window, used only if `lower < 0 < upper` | Pattern 5 | Switching too early gives a noisy 5% quantile; too late keeps a TEST band that does not describe live. It is explicitly the owner's discretion; needs confirmation before it is written into the contract |
| A3 | The missing/late rule "no row for a grid target in `(now, now + 12 h]`" and its arming on the first row | Pattern 6, 7 | A different rule changes when the alarm emails; arm-on-first-row means a feed that never starts is not alarmed |
| A4 | Insert privilege only (no UPDATE) for `dlr_writer` on the new table | Pattern 6 | A later need to correct a bad row needs an owner SQL session or a grant change |
| A5 | Amps only (no MW columns) in the one-way contract | Pattern 6 | Consumers may want MW directly; adding it later is allowed (columns may be appended) |
| A6 | The pre-flight should treat day-ahead artifact problems as warnings, not failures | Pitfall 1 | If the owner wants D-13 literally, a bad day-ahead file will block live ratings; owner decision |
| A7 | A published value that is finite and positive is enough; no check against the city's rating bounds | Open Question 5 | An absurd forecast from a bad anchor could be published; it never gates anything but is public |
| A8 | Proposed requirement IDs DAY-01 to DAY-08 and their grouping | Phase requirements | Purely naming; the planner may regroup |
| A9 | Open-Meteo's "4-6 hours" applies to `gfs_seamless` runs on the single-runs endpoint | Pattern 2 | The page names GFS in its example list but its GFS table did not render in my fetch; the 6 h repo constant and the hourly catch-up cover a slower model |

## Open Questions (RESOLVED)

All six questions below are settled. Each carries one RESOLVED line naming the decision or plan that settles it.

1. **Should day-ahead files be in the fatal part of the model pre-flight?**
   - What we know: the pre-flight runs before ratings and a failure stops the job (Pitfall 1). D-13 says the pre-flight verifies the cooling files and band; D-02 and D-15 say day-ahead must never block ratings.
   - What's unclear: whether the owner intended "verify and fail the run" or "verify and report".
   - Recommendation: warning tier in the pre-flight, hard refusal in the child, hard failure in an offline test. Needs one owner yes/no, phrased plainly: "If a day-ahead model file is damaged, should the hourly job still rate the lines? (Recommended: yes, and say so in the log.)"
   - RESOLVED by the owner as D-13a (2026-11-08, CONTEXT.md): verify and report, never stop the ratings. 08-05 adds the non-fatal warning tier (any exception in that tier is also only a warning) and the offline hard-failure test; 08-04's child refuses a file whose hash does not match and records why.

2. **What exactly does D-17's go-live check count?**
   - What we know: with catch-up the first run issues up to 12 rows (3 targets per city), each with a different lead; steady state is 4 rows every 6 hours.
   - What's unclear: whether the owner wants the first run capped to the newest target per city.
   - Recommendation: do not cap; word the check as "every due target has a row with the correct label, band source and hashes, and the parity test passed", and have a small read-only verify script print them (like `e2e_verify_readonly.py`).
   - RESOLVED as recommended (no cap): DAY-08 in 08-02 words the check as "a row for every due target, up to 3 per city and 12 in all"; 08-06 builds the read-only `day_ahead_verify.py --check-store`; 08-08 runs it after the push as the go-live check.

3. **Anchor-lead honesty.**
   - What we know: TEST anchors are 24 h before the target, the shadow reads about 12 h before, and this phase about 18 h or less. D-03 fixes the method (a "now" reading).
   - What's unclear: whether the owner wants the contract to mention it (recommended) or wants to delay issue to the shadow's 12 h lead (not recommended: it breaks "issue when available" and shrinks the lead consumers get).
   - Recommendation: record `anchor_observation_time` and `issued_at` per row and state the three leads in the contract text.
   - RESOLVED as recommended (no delayed issue): 08-01 stores `issued_at`, `forecast_run_init_time` and `anchor_observation_time` on every row; 08-10's contract docs state that "24 h" is the weather run's age and that values are issued 0-18 h before their target.

4. **Where does the band artifact live and who reviews it?**
   - What we know: `data/day_ahead/day_ahead_bands_v1.json` needs no `.gitignore` change; it is built from the tracked rows CSV.
   - Recommendation: build once offline, commit the JSON, add its hash to the live manifest, and add a test that rebuilds it byte for byte.
   - RESOLVED as recommended: 08-01 builds and commits `data/day_ahead/day_ahead_bands_v1.json`; 08-03 adds the byte-for-byte rebuild test and the strict parser; 08-05 adds its hash to `data/models/LIVE_ARTIFACT_HASHES.sha256`. The owner sees it listed in 08-08's push note before approving the push.

5. **Plausibility of the published value.**
   - What we know: `predict_cooling_correction` already refuses a non-positive convective term; nothing bounds the final amps.
   - Recommendation: DB CHECK `forecast_amps > 0 and < 'Infinity'`, log (do not suppress) a value outside the city's G4 bounds. Ask the owner only if they want out-of-bounds values withheld.
   - RESOLVED as recommended (log, do not suppress; the owner has not asked for out-of-bounds values to be withheld, and D-16 publishes every value cooling produces): 08-01's write-side migration carries the `forecast_amps > 0 and < 'Infinity'` CHECK; 08-01 and 08-04 still insert an out-of-bounds value and list it in the child's `out_of_bounds` output, which 08-02 records in `pipeline_run.day_ahead`.

6. **Supabase CLI is not installed on this machine** (`command -v supabase` returned nothing; `gh` 2.100.0, Node 26.9.0 and local Postgres 16.14 are present). The documented owner command is `supabase db push --db-url ...`. Keep the apply as an owner-gated `[BLOCKING]` step and let the plan name the alternative the owner already uses.
   - RESOLVED as recommended: both applies are owner-gated `[BLOCKING]` human-action steps that use the owner's existing CLI at `~/tools/supabase-cli/node_modules/.bin/supabase` (dry run first, then push): 08-07 Task 3 for the write-side migration and 08-11 Task 3 for the expose migration. No test needs the CLI.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (repo venv) | all tests and scripts | yes | 3.12.13 | — |
| pytest | tests | yes | 9.0.3 | — |
| psycopg | store and PG tests | yes | 3.3.6 | — |
| Local Postgres (`initdb`, `pg_ctl`) | migration and privilege tests with `DLR_TEST_PG_AUTOSTART=1` | yes | 16.14 (Homebrew; 18 also present) | tests skip without it |
| `gh` CLI | read-only run inspection, owner steps | yes | 2.100.0 | — |
| Supabase CLI | owner applies migrations | no | — | owner's existing apply route (documented `supabase db push --db-url`); not needed for tests |
| Network to Open-Meteo / TCEQ / Synoptic | live stage only | not needed for tests | — | all tests offline with the `_no_network` fixture pattern |
| Real model files (4 cooling, committed) | parity test with real artifacts | yes | hashes match their manifests (verified through `make_headline_loader` this session) | stub models, as the golden test does |

**Missing dependencies with no fallback:** none for planning or implementation.
**Missing dependencies with fallback:** Supabase CLI (owner step only).

## Validation Architecture

`workflow.nyquist_validation` is not set to false in `.planning/config.json` or the workstream config (both read this session), so this section is required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `/Users/aphan/Senior_Design/pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Quick run command | `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/day_ahead_forecast_test.py backend/tests/day_ahead_band_test.py` |
| Local-Postgres command | `DLR_TEST_PG_AUTOSTART=1 /Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/day_ahead_migration_test.py backend/tests/expose_migration_test.py backend/tests/soak_log_migration_test.py` |
| Full suite command | `DLR_TEST_PG_AUTOSTART=1 /Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider` |
| Baseline measured | the Phase 5 to 7 suites touched here ran green and fast this session: runner, run log, check-models, conductor tests 99 passed in about 9 s; `expose_migration_test` plus `soak_log_migration_test` with local Postgres 47 passed in about 2.4 s. The full suite (`DLR_TEST_PG_AUTOSTART=1`, `-x`) also finished with exit code 0 on 2026-11-07 (no failure; only warnings), so the starting point is green. The pass count was not captured (the run used `-q -q`); take a counted baseline before Wave 1. |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DAY-01 | `due_targets(now)` for hh:05 in {06,12,18,00} yields the new target at `now + 18 h - 5 min`; other hours only catch-up; a target in the past is never due; `T == now` excluded; missing = due minus table keys; `decision_time < availability` pre-filtered | unit | `pytest -q -p no:cacheprovider backend/tests/day_ahead_forecast_test.py -k due` | Wave 0 |
| DAY-01 | catch-up: a later run issues a missing target from the same 24 h-old run; row `issued_at` is the actual decision time; second run inserts nothing (DO NOTHING) | unit + fake conn / local PG | `pytest ... -k catchup` | Wave 0 |
| DAY-02 | parity: for each city, the production value equals `forecast_shadow_demo.run_once_all_methods` `ml_cooling_corrected` for the same fake inputs and the same `valid_time` (three cities exactly; AUSTIN equals the shadow functions called with the production point and the refit model, and differs from the Drake call) | integration, offline, real hash-verified artifacts | `pytest ... -k parity` | Wave 0 |
| DAY-02 | no substitute: missing anchor, missing run (`StaleOrMissingDataError`), hash mismatch, loader error each produce no row and a reason | unit | `pytest ... -k no_substitute` | Wave 0 |
| DAY-02 | AST pin: new module names `production_city_point`, never `<x>.city_point()`; added to `PRODUCTION_CALLERS` | AST | `pytest -q -p no:cacheprovider backend/tests/production_conductor_test.py -k caller_split` | exists, extend |
| DAY-02 | frozen paths untouched | golden | `pytest -q -p no:cacheprovider backend/tests/cond02_shadow_golden_test.py` | exists, must stay green |
| DAY-03 | band builder: 16 bands x n=196, sign convention `truth - forecast`, offsets equal `np.quantile`, artifact bytes reproducible, `rows_sha256` matches the CSV, refuses a CSV row at or after 2026-09-30 | unit | `pytest -q -p no:cacheprovider backend/tests/day_ahead_band_test.py` | Wave 0 |
| DAY-03 | clamp guard; live-rolling uses only computed non-fallback pairs with equal `config_fingerprint`; switch per band at the threshold; `band_source` and `band_n` recorded; live band rejected if it does not straddle 0 | unit + local PG | `pytest ... day_ahead_band_test.py -k live` | Wave 0 |
| DAY-03 | anti-peeking: new modules reference neither `data/shadow/predictions`, `read_city_log_entries`, nor FRESH-dated cache names | grep/AST | `pytest ... day_ahead_band_test.py -k anti_peek` | Wave 0 |
| DAY-04 | stage runs after `exit_code` is computed; a crashing, hanging or erroring child leaves the exit code and rating `cities_ok`/`cities_failed` unchanged; stage default OFF in `run_live`; skip when budget is short; `finished_at` semantics | unit with fake children (pattern of `dlr_live_run_test.py`) | `pytest -q -p no:cacheprovider backend/tests/dlr_live_day_ahead_stage_test.py` | Wave 0 |
| DAY-04 | run row: `day_ahead` omitted unless present; post-stage write failure counted separately; existing 23 runner tests unchanged | unit | `pytest -q -p no:cacheprovider backend/tests/dlr_live_run_test.py backend/tests/live_run_log_test.py backend/tests/supabase_run_log_test.py` | exist, extend |
| DAY-04 | workflow pins unchanged (`timeout-minutes: 30`, run lines) | text | `pytest -q -p no:cacheprovider backend/tests/dlr_live_workflow_test.py backend/tests/dlr_live_runbook_test.py` | exist, must stay green |
| DAY-05 | migration 1 text: columns and types in order, CHECKs (grid, finite amps, hex hashes, label not null), RLS on, revoke from anon/authenticated, writer grant exactly `select, insert`, no credential, re-apply safe, every column commented unit-first | offline text tests | `pytest -q -p no:cacheprovider backend/tests/day_ahead_migration_test.py` | Wave 0 |
| DAY-05 | local PG: anon cannot read or write the table after migration 1; writer can insert and select; duplicate key is ignored | local PG | `DLR_TEST_PG_AUTOSTART=1 pytest ... day_ahead_migration_test.py -k writer` | Wave 0 |
| DAY-05 | identity: row carries `rating_config_fingerprint(city)`, `RATING_CONFIG_VERSION`, cooling sha256 from `loader.served`, band sha256, label constant | unit | `pytest ... day_ahead_forecast_test.py -k identity` | Wave 0 |
| DAY-06 | migration 2: view is security invoker, anon SELECT on exactly the new objects, read policy, rows only for `valid_time > now()`, order by city then target, status view always 4 rows, `is_late` rule | local PG | `DLR_TEST_PG_AUTOSTART=1 pytest ... day_ahead_migration_test.py -k expose` | Wave 0 |
| DAY-06 | contract: `day_ahead_contract.py` columns equal the migration view columns and the `rest-api.md` table; label text equals the D-11 string; paragraph present | offline text | `pytest -q -p no:cacheprovider backend/tests/rest_api_doc_test.py backend/tests/day_ahead_migration_test.py -k contract` | exist (extend) / Wave 0 |
| DAY-06 | privilege sweep: updated `verify_exposure.sql` all `ok` after both migrations; existing checks still pinned | local PG | `DLR_TEST_PG_AUTOSTART=1 pytest -q -p no:cacheprovider backend/tests/expose_migration_test.py` | exists, extend |
| DAY-07 | `assert_fresh()` still 200 with only `city_rating` rows (not armed); armed once a day-ahead row exists; 503 `PT503` with `day_ahead_late=` when a target in the next 12 h is missing; same signature (no overload); `max_age_minutes` validation unchanged | local PG | `DLR_TEST_PG_AUTOSTART=1 pytest ... expose_migration_test.py day_ahead_migration_test.py -k assert_fresh` | exist, extend |
| DAY-07 | secret scan: no project value in new files | text | `pytest -q -p no:cacheprovider backend/tests/secret_scan_test.py` | exists |
| D-13 | manifest: day-ahead list resolves the four cooling paths via `production_differs`, hashes match the committed manifest, band entry present, `--write-manifest` round trip, non-fatal tier prints warnings and exits 0 while a live-8 problem still exits 1, no circular import | unit | `pytest -q -p no:cacheprovider backend/tests/dlr_live_check_models_test.py` | exists, extend |
| DAY-08 | owner-gated checks are procedural: migration 1 applied, code pushed, first-slot verify script output reviewed, migration 2 applied, doc published | manual, owner | verify script plus `supabase/ops` SQL | Wave 0 (script) |

### Sampling Rate
- **Per task commit:** the quick command for the touched module plus `production_conductor_test.py` and `cond02_shadow_golden_test.py` when anything near the shadow path changes.
- **Per wave merge:** the full suite with `DLR_TEST_PG_AUTOSTART=1`.
- **Phase gate:** full suite green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/day_ahead_forecast_test.py` covers DAY-01, DAY-02, DAY-05 identity
- [ ] `backend/tests/day_ahead_band_test.py` covers DAY-03
- [ ] `backend/tests/day_ahead_migration_test.py` covers DAY-05, DAY-06, DAY-07 (offline text and local PG)
- [ ] `backend/tests/dlr_live_day_ahead_stage_test.py` covers DAY-04 (separate file so the 23 existing runner tests stay untouched)
- [ ] Shared offline fixtures: autouse `_no_network` (records `requests.get`, asserts none) and `_no_database` (refuse `live_run_log.open_connection`), copied from `dlr_live_run_test.py`; a fake connection like `FakeConn` in `supabase_run_log_test.py`; `local_pg` for SQL tests; a fake shared-input factory like `_fake_shared_inputs_factory` in `forecast_shadow_demo_test.py` and a monkeypatch of `forecast_shadow_demo._resolve_next_valid_time` so the shadow reference uses the same `valid_time` (the cooling features include the hour encoding of `valid_time`)
- [ ] A read-only verify script for D-17 (`backend/day_ahead_verify.py` or an `e2e_verify_readonly.py` addition) with its own offline test
- [ ] Framework install: none

## Security Domain

`security_enforcement` is not set to false in either config, so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no (no new auth surface; the writer credential and publishable key are unchanged) | existing `SUPABASE_DB_URL` secret, publishable key for reads |
| V3 Session Management | no | — |
| V4 Access Control | yes | RLS on the new table, explicit `revoke all` from anon/authenticated, security-invoker views, writer insert/select only, privilege sweep in `verify_exposure.sql` |
| V5 Input Validation | yes | closed city set (`config.LOCATIONS` / table CHECK), bound SQL parameters only, strict parse of the band JSON (schema key, 16 bands, finite numbers, offsets ordered), UTC grid CHECK on `valid_time` |
| V6 Cryptography | yes | sha256 only, through existing helpers; never hand-rolled |
| V8 Data Protection | yes | public table carries no error text or secrets; reasons go only into private `pipeline_run.day_ahead`, passed through `redact()` |
| V12 Files and Resources | yes | joblib is a pickle: hash verified before any load (`make_headline_loader`); band artifact is JSON (no code execution) |
| V14 Configuration | yes | no project host, reference or key in any committed file (secret scan); workflow permissions unchanged (`contents: read`) |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unpickling a tampered model in a process that holds the DB URL | Tampering / Elevation | sha256 against the manifest before `joblib.load`; the pre-flight step has no secrets (Phase 5 T-05-16/17) |
| SQL injection through city or time values | Tampering | psycopg bound parameters; closed city set; no string-built SQL for data |
| Anon writes through the new table or view | Tampering | explicit revoke, no write policy for anon/authenticated, local PG test as anon, `verify_exposure.sql` extended |
| View bypassing RLS | Information disclosure | `security_invoker = true` plus a read policy on the table (06-RESEARCH) |
| Credential or error text leaking through the public table, Actions log or step summary | Information disclosure | no error text in the table; `redact()` before any record or log line; the runner already defangs child output |
| Alarm credential exposure when extending the alarm | Information disclosure | no change to the alarm: same URL, same publishable key, still entered only in cron-job.org |
| A deploy-order mistake turning the alarm red repeatedly | Denial of service (alarm auto-disable at 25 failures) | arm the day-ahead clause on the first row; apply the expose migration only after the first slot is verified |
| A broken day-ahead stage blocking live ratings | Denial of service | exit code fixed before the stage; try/except around the whole stage; child isolation; non-fatal pre-flight tier |

## Sources

### Primary (HIGH confidence) - read in full or in the cited ranges this session
- `/Users/aphan/Senior_Design/backend/forecast_shadow_pipeline.py` (lines 1-1065, 1797-1965)
- `/Users/aphan/Senior_Design/backend/forecast_shadow_demo.py` (all), `backend/forecast_shadow_collect.py` (1-180)
- `/Users/aphan/Senior_Design/backend/forecast_correction_models.py` (384-607), `backend/forecast_conductor_refit.py` (all), `backend/city_point.py` (all)
- `/Users/aphan/Senior_Design/backend/dlr_live_run.py`, `backend/live_run_log.py`, `backend/dlr_live_check_models.py`, `backend/rating_identity.py` (all)
- `/Users/aphan/Senior_Design/backend/supabase_store.py` (60-200, 317-382, 400-944), `backend/ampacity_forecast.py` (381-574)
- `/Users/aphan/Senior_Design/backend/forecast_test_split_score.py` (1-246), `backend/forecast_shadow_confirm.py` (684-745), `backend/open_meteo_forecast_provider.py` (374-536)
- `/Users/aphan/Senior_Design/docs/data-science/exploratory/2026-11-02_horizon_comparison/REPORT.md`, `build_rows.py`, `context_posthoc.md`, `rows_production.csv` (analysed with pandas)
- `/Users/aphan/Senior_Design/supabase/migrations/*.sql` (all four), `supabase/ops/verify_exposure.sql`, `supabase/ops/verify_monitoring.sql`
- Tests read: `production_conductor_test.py` (190-329), `cond02_shadow_golden_test.py`, `golden_shadow_capture.py` (52-110), `dlr_live_run_test.py` (1-140), `dlr_live_check_models_test.py`, `dlr_live_workflow_test.py`, `dlr_live_runbook_test.py`, `expose_migration_test.py` (1-120, 296-420, 685-700), `supabase_migration_test.py`, `supabase_run_log_test.py`, `supabase_schema_doc_test.py`, `rest_api_doc_test.py`, `local_pg.py`
- `.github/workflows/dlr_live.yml`, `.github/workflows/shadow_collect.yml`, `requirements.txt`, `.gitignore`
- `docs/data-science/decisions/dlr_live_runbook.md` (sections 4, 5, 9, 14, 15, 16), `shadow_collection_runbook.md` (External trigger), `v4_selection/decision_record.md`, `docs/integration/rest-api.md`, `docs/data-science/schema/city_rating_v1.md` (run-log section)
- `.planning/workstreams/production-pipeline/REQUIREMENTS.md`, `STATE.md`, `ROADMAP.md` (Phase 8), `phases/08-.../08-CONTEXT.md`
- Ad hoc runs this session: offline end-to-end cooling chain for all four cities with hash-verified artifacts; 16-band quantile check on `rows_production.csv`; `git check-ignore` for candidate artifact paths; baseline pytest runs.

### Secondary (MEDIUM confidence)
- https://open-meteo.com/en/docs/single-runs-api (availability "typically 4-6 hours for global models", valid run cycles, "most models are archived from 2nd of April 2026")

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - nothing new; versions read from the venv and `requirements.txt`.
- Architecture: HIGH for the shadow call chain, manifest, run-log and migration mechanics (all read and partly executed); MEDIUM for the stage time limits and band switch-over (recommendations, tagged `[ASSUMED]`).
- Pitfalls: HIGH - each cites the file and line (or test) that pins it.

**Research date:** 2026-11-07
**Valid until:** 2026-12-07 for the code facts, unless a Phase 8 plan or a conductor update (Power Systems answers) lands first; re-check `RATING_CONFIG_VERSION` and `production_differs` if it does.
