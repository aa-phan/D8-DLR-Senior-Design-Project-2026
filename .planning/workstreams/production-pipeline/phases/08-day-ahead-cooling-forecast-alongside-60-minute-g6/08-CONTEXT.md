# Phase 8: Day-Ahead Cooling Forecast Alongside 60-Minute G6 - Context

**Gathered:** 2026-11-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Production publishes, for each of the four cities, a 24-hour-ahead ampacity forecast from
`ml_cooling_corrected`. Each value has its own 5-95% uncertainty band and a label saying it is a
higher-error, engineering-selected, not-validated forecast. It is stored in a new table, exposed
read-only through a new REST view, and checked by the existing freshness alarm.

The 60-minute G6 forecast stays `ml` (B2 retrain) and is the only forecast that gates G6. The
day-ahead value never sets, replaces or checks the live rating. `city_rating`, the 34-column
`latest_rating` contract, `shadow_collect.yml`, the shadow logs, the 12 frozen Drake artifacts and
the frozen evaluation modules are not modified.

Selection status is fixed by Phase 7 (`decision_record.md`): `ml_cooling_corrected` is the
owner's continuing labelled engineering departure. It is not a rule pick and not "validated".
No new FRESH read or signed protocol is part of this phase.

</domain>

<decisions>
## Implementation Decisions

### When and how it runs
- **D-01:** **Four target hours a day, as tested.** One value per city for each 00/06/12/18 UTC
  target hour, computed from the Open-Meteo run initialised exactly 24 h before the target. This
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
- **D-13a (owner, 2026-11-08, after research):** **A day-ahead file mismatch never stops live
  ratings.** The live pre-flight step (`dlr_live_check_models.py`) still verifies the cooling and
  band files, but only as a non-fatal warning tier. The 8 live models stay fatal, as today. The
  day-ahead stage refuses to load any file whose hash does not match, so untrusted bytes are never
  unpickled, and records the reason in `pipeline_run`. An offline test fails hard if the
  day-ahead manifest entries and the files on disk disagree, so a mismatch is caught before any
  push.
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Selection status and evidence
- `docs/data-science/decisions/v4_selection/decision_record.md` — owner's labelled engineering selection of `ml_cooling_corrected` (read 1 and read 2 sections); not a rule pick, not validated
- `docs/data-science/exploratory/2026-11-02_horizon_comparison/REPORT.md` — TEST-window day-ahead errors by city, the +23 A / 1.7% cost of lead time, slot-hour gaps (`context_posthoc.md`); source of the D-11 figures and the D-05 starting residuals
- `docs/data-science/exploratory/2026-11-02_horizon_comparison/build_rows.py` — how the TEST rows were rebuilt with the scorer's own functions under the production conductor (reuse for the D-05 band artifact)
- `docs/data-science/exploratory/2026-11-02_ml_vs_naive/REPORT.md` — 60-minute ml vs naive context
- `docs/data-science/decisions/confirmation_protocol_v4_early_selection_SIGNING_COPY.md` — signed v4; O3 says any later evaluation needs a new signed protocol (this phase does none)

### Shadow method and frozen constraints
- `docs/data-science/decisions/shadow_collection_runbook.md` — shadow method, fit windows, frozen artifacts, issue times
- `.planning/workstreams/production-pipeline/phases/07-per-city-conductors-shadow-refit-and-early-model-selection/07-CONTEXT.md` — COND-02 frozen/production split, D-09..D-11 conductor decisions
- `data/shadow/models/ARTIFACT_HASHES.sha256` and `data/models/conductor_refit/v3-powersystems-2026-11-02/ARTIFACT_HASHES.sha256` — hashes of the files served (D-13)

### Live pipeline, store and contract
- `docs/data-science/decisions/dlr_live_runbook.md` — live job, model promotion and manifest procedure, §14 permanent freshness alarm
- `docs/data-science/schema/city_rating_v1.md` — existing consumer schema and label conventions (unchanged; the new table gets its own section or doc)
- `docs/integration/rest-api.md` — REST contract; new view documented here (its column table is parsed by a test)
- `docs/data-science/decisions/pss_e_handoff.md` — consumer pointer to update
- `supabase/migrations/20261026195124_expose_latest_rating.sql` — privilege and view pattern to follow (D-09)
- `.planning/workstreams/production-pipeline/REQUIREMENTS.md` — OD-1..OD-10; "Out of Scope" row on wiring a shadow model into live (this phase is that follow-on)
- `.planning/workstreams/production-pipeline/STATE.md` — Phase 4-7 decisions on identity, manifest, run log

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `backend/forecast_shadow_pipeline.py`: `fetch_live_forecast_for_valid_time` (exact-24 h-init run, 2 forecast days, retry policy), `fetch_live_anchor_observation`, `fetch_shared_city_inputs`, `_enrich_city_frame_for_correction`, `CoolingCorrectionShadowMethod` (`name = "ml_cooling_corrected"`). Call these unchanged (D-03); the module is frozen.
- `backend/forecast_correction_models.py`: `predict_cooling_correction`, `apply_cooling_correction`.
- `backend/forecast_conductor_refit.py:347` `make_headline_loader`: hash-verified loading of refit plus frozen artifacts (D-14).
- `backend/city_point.py` `production_city_point`: per-city production conductor geometry.
- `backend/ampacity_forecast.py`: empirical residual-quantile band logic (`backtest_residuals`, quantile clamp, band-excludes-centre guard) as the model for the live band (D-05, D-07).
- `backend/dlr_live_check_models.py`: manifest read/write/check; `required_artifacts()` currently lists 8 files and must grow to include the 4 cooling files plus the band artifact (D-13).
- `backend/supabase_store.py`: upsert helpers, `upsert_run`, `rating_config_snapshot` / `config_fingerprint`, redaction; `backend/rating_identity.py` for identity.
- `backend/forecast_test_split_score.py` `cached_test_provider` and `forecast_shadow_confirm._score_city`: rebuild TEST rows for the starting band (as `build_rows.py` does).

### Established Patterns
- Live runner (`backend/dlr_live_run.py`): one orchestrator child per city, 300 s kill, exit 0 only when every city is healthy. Day-ahead must not change this exit rule (D-15).
- Migrations are additive, and applied migrations are pinned by sha256 and never edited (04-09). Schema pushes are owner-gated `[BLOCKING]` steps.
- Contract docs are parsed by tests against code column lists (06-06), so the new view's column table needs the same guard.
- The secret scan covers project host, pooler ref and publishable key; no project values are committed (06-02).
- Anti-peeking: never read shadow-log outcomes with valid_time after 2026-09-29 for any purpose (including band calibration). Never open `data/experiment/anchored_pair_frame_*_2026-09-30_*`. The cached `..._2024-01-20_2026-09-29_...` frame is allowed for TEST rows.

### Integration Points
- `.github/workflows/dlr_live.yml` / `backend/dlr_live_run.py`: the new stage runs after ratings (D-02).
- `pipeline_run`: new additive day-ahead outcome fields (D-15).
- Supabase: new migration (table, view, grants, RLS); the freshness alarm check (`assert_fresh` / runbook §14) gains the day-ahead flag (D-12).
- `data/models/LIVE_ARTIFACT_HASHES.sha256`: cooling and band entries (D-13).

</code_context>

<specifics>
## Specific Ideas

- The owner's framing: day-ahead "has more error because it's in the future (like any future
  forecast would in any domain)". The label and doc should say this plainly, not as a defect.
- The owner wants plain-English explanations before options (`memory: explain-decisions-plainly`).
  Owner-facing checkpoints in plans (schema approval, push, go-live) should open with a short plain
  summary.
- Safety framing (`memory: static-rating-fallback-is-safe`): the day-ahead value has no safety
  role. It never gates anything, so it is an information output and not a safety item.

</specifics>

<deferred>
## Deferred Ideas

- Hourly day-ahead issuance (24-29 h leads), only once there is evidence for those leads.
- Any statistical validation or rule-based re-selection of the day-ahead method: this needs a new
  signed protocol (v4 O3) and is a separate phase.
- Day-ahead coverage reporting beyond what the band switch-over needs (e.g. a periodic calibration
  report): possible follow-up.

</deferred>

---

*Phase: 08-day-ahead-cooling-forecast-alongside-60-minute-g6*
*Context gathered: 2026-11-08*
