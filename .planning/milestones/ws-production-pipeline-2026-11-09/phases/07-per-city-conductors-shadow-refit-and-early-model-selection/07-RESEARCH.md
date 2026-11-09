# Phase 7: Per-City Conductors, Shadow Refit and Early Model Selection - Research

**Researched:** 2026-10-25 (session date; the machine clock read 2026-10-26T04:14Z, i.e. 23:14 local, when this was written)
**Domain:** Python/pandas/scikit-learn rating pipeline; pre-registered statistical evaluation protocol; Supabase-backed live rating rows
**Confidence:** HIGH on code seams and constraints (all read this session); MEDIUM on v4 drafting choices (owner decisions); LOW on how many candidates will clear a 2% bar (no FRESH evidence may be read)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**FRESH read: conductor and evidence weight (SEL-01, SEL-03, SEL-04)**
- **D-01:** The FRESH headline scores the candidates under the **production per-city conductor configs**: reconstructed frames recompute truth, `raw_forecast` and persistence under that config, and `ml_cooling_corrected` / `reference_ml_refit_24h` use models fit under it. `ml_wind_corrected` is conductor-independent and is reused. The frozen Drake artifacts are scored in the same read as a **labelled secondary**. The live shadow logs (Drake, as collected) remain the live-system check and are never pooled with the headline. Because of D-09, the production config is Drake unless Power Systems answers by the D-11 deadline, so in the default case the headline and the frozen Drake setup coincide.
- **D-02:** **FRESH decides; ABLATION and TEST only veto.** Only the FRESH read can name a winner. The ABLATION conductor-invariance re-score and the per-city TEST-split scoring are pre-registered gates that disqualify a candidate whatever FRESH says. Example vetoes: a candidate whose point order against the default flips under the bracketing conductor set, or one that loses to `raw_forecast` on TEST in at least 3 of 4 cities. The exact veto criteria are drafted in v4 for owner signature.
- **D-03:** **Late Power Systems answers (after the FRESH read):** the decision stands if the ABLATION test showed the ranking is invariant across the bracketing set. Cooling and reference are then refit under the real values for serving, with no FRESH re-read. If ABLATION did not show invariance, the decision is labelled **conductor-conditional**, and v4 pre-registers a descriptive re-score under the confirmed conductor that can flag a problem but cannot overturn the decision. — **Reversibility:** one-way — fixed in signed v4 before outcomes; changing it afterwards would be a post-hoc protocol change.
- **D-04:** **One method for all four cities**, keeping v3 decision 8's structure: "consistent" means the point estimate favours it in at least 3 of 4 cities. No per-city winners.

**v4 dates, threshold and no-winner rule (SEL-01)**
- **D-05:** **Dates:** the same 1-week truth-revision margin as v3. `valid_time` cutoff **strictly before 2026-10-25T00:00Z**, instant **2026-11-01T00:00Z**, about 100 headline rows per city (25 days × 4 cycles). The fetch window pinned in the frozen evaluation modules (`backend/forecast_shadow_confirm.py:186-191`, `backend/forecast_shadow_eval_core.py:65-71`) is re-pinned only as v4 explicitly allows. — **Reversibility:** one-way — signed protocol dates.
- **D-06:** **Relative win threshold:** v3's X = 5 A becomes **2% of the city's mean truth ampacity** (MAE reduction), so the bar doesn't move with the conductor. The owner chose 2% because it is roughly what about 100 rows per city can resolve. v3's three evidence levels ("supported" / "indicated, not resolved" / "not shown") and the 9-test city-clustered Holm family (v3 decision 2) carry over unchanged (Claude default; the owner may revisit at signing). — **Reversibility:** one-way — fixed before outcomes.
- **D-07:** **If no candidate qualifies, there is no pick.** v3's fallback rules (keep `ml_wind_corrected` / fall back to `raw_forecast`) are replaced by a pre-registered re-test. No shadow model replaces `ml` at 11-01.
- **D-08:** **Conditional re-test**, pre-registered in v4: instant **2026-11-08T00:00Z**, cutoff **2026-11-01T00:00Z** (same 1-week margin), about 130 rows per city. It grades **all** rows, including the first read's, and uses the same rules. It runs only if the 11-01 read names no winner. This replaces "the single FRESH read" in ROADMAP SC 5 / SEL-04: the planner must update that wording and REQUIREMENTS SEL-04 and record the change in the ml-modeling STATE.md. **Open for the v4 draft:** what happens if the re-test also names no winner. Claude's suggested default for the owner to confirm at signing: no day-ahead pick, and the interim G6 method continues. — **Reversibility:** one-way — pre-registered.

**Provisional conductors (COND-01, COND-02, B1)**
- **D-09:** **Every city stays on Drake 795 ACSR at 75 °C, 900 m, current bearings** (`config.DEFAULT_CONDUCTOR_CONFIG_KWARGS`, `CITY_LINE_BEARING_DEG`) until Power Systems answers. The owner explicitly declined the researched AUSTIN alternatives (Drake @100 °C, Suwannee ACSS/TW @200 °C) and the measured-elevation fix (Austin 163 m). The per-city config structure is still built now: per-city type, diameter, AC resistance, MOT, elevation and azimuth, each with a recorded source (for now "current model default, provisional; Power Systems pending"), plus a config-version bump path. Power Systems' values then drop in with no code change. The production-only resolver, the shadow path left on `city_point.city_point` / `config.conductor_kwargs_for`, and the byte-identical golden test are all still built (COND-02).
- **D-10:** Consequence of D-09: SEL-02's refit under the production config is **conditional**. If no Power Systems values arrive by D-11, the production config equals the frozen Drake configuration, so the 12 frozen artifacts serve as the production-conductor models for the headline and no duplicate refit is produced. If values arrive (for any city), cooling and reference are refit for those cities on rows before 2026-03-17 only (asserted), saved as new hashed artifacts, never overwriting the frozen ones. The ABLATION refits under the bracketing set (SEL-03) happen regardless. The planner should reflect this in the SEL-02 / ROADMAP SC 3 wording.
- **D-11:** **Power Systems deadline for the 11-01 test: end of 2026-10-30, recorded as 2026-10-31T00:00Z.** Values received by then are used in the 11-01 headline. Production switches to them via a config-version bump, cooling and reference are refit, and the TEST-split veto is re-scored under them before the instant. Values arriving later fall under D-03 and go into production but not into the 11-01 headline. — **Reversibility:** one-way — written into signed v4.
- **D-12:** **B1 fallback-policy half: keep the current policy** (Finding 1 option A). The owner's standing rule is that a low-side G4 fallback to the documented static rating is safe and only above-band ratings are unsafe (`memory: static-rating-fallback-is-safe`). Static ratings and G4 bounds are unchanged.
- **D-13:** **A GO is allowed while still on the Drake assumption.** The GO lifts the provisional label for the other closed blockers, but each row stays labelled with its conductor basis (already carried by `config_fingerprint` / `config_version` / `rating_basis`, OD-5, DB-06). B1's conductor question stays open until Power Systems answers.

**Interim G6 method, B2/B4/B5, go/no-go (REVAL-01)**
- **D-14:** **B2: keep `ml` (OD-3 stands) and retrain the four per-city forecast models with the projected (line-perpendicular) wind speed as the feature** (Finding 2 option B), under the current production config. The new artifacts get new hashes, the live manifest is regenerated (`dlr_live_check_models.py --write-manifest`), and they are committed per OD-10. Ask before pushing anything that changes live CI. If Power Systems' values are adopted, the retrain is redone under them.
- **D-15:** **If the retrained `ml` still has higher error than naive in the September re-run, the owner decides at the go/no-go.** There is no pre-set rule; report the comparison clearly.
- **D-16:** **B4: accept CORPUS_CHRISTI's 11.01% detector trip rate as safe** (a trip falls back to the safe static rating; D-12). Re-measure it in the re-run. Log a follow-up to refit the CORPUS_CHRISTI anomaly detector on station-measured inputs together with the conductor-driven detector retrain when Power Systems' values arrive (or by a fallback date the plan proposes if they never answer), then re-check it with a replay on the September window.
- **D-17:** **B5: when the `ml` forecast is withheld from G6 because of a gap** (`data_cleaning.ML_LOOKBACK_ROWS` = 7 consecutive usable rows not met), **G6 uses the naive band instead**, which needs only 1 recent usable slot (`MAX_TRAILING_GAP_SLOTS` = 1). `ml` stays primary. Fallback rows stay excluded from history (the Phase 2 rule is unchanged). Rationale: this restores the high-side band check, the owner's one unsafe direction, at AUSTIN, where `ml` was withheld 96 of 111 evaluated steps against naive's 28. Which method gated each step should be visible in the trace and report.
- **D-18:** **GO requires a checklist, then the owner's signature:** B1, B2, B4 and B5 each closed with a recorded decision; the re-run complete on 2026-09-08..09-28 with 0 replay-fidelity mismatches; the share of hours in which the band check ran reported per city, AUSTIN in particular. The owner then signs GO or NO-GO on the report. There are no hard numeric bars (no ≤5% trip-rate requirement).

### Claude's Discretion
- Drafting the full v4 text: the exact ABLATION invariance criteria (start from `shadow_early_decision_options.md` §5.4: set Drake-75 control, Drake-100, Falcon-90, Suwannee-150, Suwannee-200, plus a 163 m Austin variant), the exact TEST veto criteria, and the precise "qualifies" definition combining D-04 and D-06. The owner signs it.
- **Partial Power Systems answers by D-11:** default to switching only the cities with a complete answer, leaving the rest on Drake. This is flagged for the owner to confirm in v4.
- The fallback date for the CORPUS_CHRISTI detector refit if Power Systems never answers (D-16).
- Whether the TEST-split scoring needs a development-window provider (`shadow_early_decision_options.md` option (e) notes one exists for tests).

### Deferred Ideas (OUT OF SCOPE)
- Refit the CORPUS_CHRISTI anomaly detector on station-measured inputs, bundled with the conductor-driven detector retrain (D-16 follow-up).
- Real per-city elevations (Austin 163 m etc.) and the researched AUSTIN conductor alternatives: deferred to Power Systems' answer by owner choice (D-09).
- Wiring the selected shadow model into the live path (already out of scope; follow-on phase).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| COND-01 | Per-city conductor config (type, diameter, AC resistance, MOT, elevation, azimuth) in config with a recorded source per value; replacing values is a config change plus version bump | Pattern 1 (per-city table + sources), Pattern 2 (identity/fingerprint compatibility), Pitfalls 1, 2, 3, 12 |
| COND-02 | Production rating, training and validation use per-city configs; shadow collector, 12 frozen artifacts and frozen evaluation modules keep Drake; golden test proves byte-identical | Pattern 1 (resolver in `city_point.py`), Pattern 3 (golden design), caller inventory, shadow transitive-import list |
| SEL-01 | Protocol v4 signed before any FRESH outcome is computed or read; contents listed | Pattern 4 (round constants, guard), v4 drafting checklist, schedule section, Pitfalls 4, 5, 6 |
| SEL-02 | `ml_cooling_corrected` and `reference_ml_refit_24h` refit per city under production configs on rows < 2026-03-17 (asserted), new hashed artifacts, wind reused | Pattern 5 (refit driver, new location, hash manifest), measured fit time 3.5 s per city, Pitfall 7 |
| SEL-03 | ABLATION conductor-invariance re-score and per-city TEST scoring, criteria pre-registered in v4 | Pattern 6 (cached-frame provider, TEST window start 2026-03-18), bracketing set values, Pitfalls 8, 9 |
| SEL-04 | The FRESH read runs under v4; recorded owner decision names the model (if any) and interim G6 method | Pattern 4, `apply_ship_rule` v4 variant, D-07/D-08 re-test, Pitfalls 4, 10, 11 |
| REVAL-01 | B1, B2, B4, B5 closed; Phase 3 validation re-run on 2026-09-08..09-28; new go/no-go signed; GO lifts provisional label | Pattern 7 (B2 retrain), Pattern 8 (B5), Pattern 9 (offline replay re-run), Pitfalls 13, 14, 15 |
</phase_requirements>

## Summary

Almost nothing in this phase needs new libraries or external services. It is a set of seams in code that already exists, plus governance work. All four `ml`-side items (B2 retrain, B5 band fallback, conductor table, replay re-run) are small, offline and testable on committed fixtures. The ABLATION and TEST analyses are computationally trivial: one full per-city fit of the three shadow candidates took **3.5 s** in this session (`fit_from_frame`, AUSTIN, 18,864 hourly rows, no artifact written). **Compute is not the bottleneck. The bottlenecks are (1) the owner's signature on v4, (2) the Power Systems deadline of 2026-10-31T00Z, and (3) a one-day window between that deadline and the 2026-11-01T00Z instant.**

The riskiest engineering hazard is the golden-test promise (COND-02). The shadow side imports `ampacity_forecast`, `forecast_training`, `thermal_model`, `weather_provider`, `wind_vector`, `config` and `city_point` from the production side [VERIFIED: import scan of `backend/forecast_shadow_*.py`, `forecast_experiment*.py`]. So the B2 retrain fix and every per-city-config edit sit next to code the frozen shadow path executes. The golden fixtures must be captured from the untouched tree at current HEAD (`d71c501`) **before the first production edit**, and B2 must be confined to `city_training_frame` (not `build_training_matrix` or `build_ml_features`, which the reference candidate uses).

The second hazard is the anti-peeking guard. v4's dates are not the constants in `forecast_shadow_eval_core.py`. Passing them as non-default values forces `--override-reason`, and **an override silently disables both the "before the instant" refusal and the one-shot refusal** [VERIFIED: `forecast_shadow_eval_core.py:397-424`]. Re-pin the constants as a signed-v4 round instead, so the single guard stays armed.

**Primary recommendation:** Capture golden baselines first and draft v4 in parallel (day 0). Merge the v4-authorised edits to frozen modules only after the owner signs. Build the resolver, B2, B5 and the ABLATION/TEST drivers on a branch while waiting. After signing, run ABLATION and TEST (minutes), hold the 2026-10-31T00Z gate for Power Systems, then run the single FRESH read once at or after 2026-11-01T00:00Z.

## Schedule Implications (read first)

Today is 2026-10-25. The instant is 2026-11-01T00:00Z, so there are about 5 days 20 hours left (the clock read 2026-10-26T04:14Z).

| Order | Item | Blocks | Can run in parallel with |
|---|---|---|---|
| 1 (first commit, before any edit) | Golden baseline capture at HEAD `d71c501` (COND-02) | Every code change that touches production or shared modules | v4 drafting |
| 1 | Draft v4 in plain English, owner reviews and signs | ABLATION and TEST runs (their criteria must be pre-registered, and TEST needs a written owner decision), any merge to frozen modules, the FRESH read | Golden capture, all code on branches |
| 2 | Per-city config + resolver + caller repoint + identity + doc (COND-01/02) | Phase 7 refits if Power Systems answers; REVAL-01 re-run | v4 signing, selection tooling, B2/B5 code |
| 2 | Selection tooling edits to frozen modules (rounds, geometry seam, provenance, relative-margin decision) | Merge only after v4 signature; the FRESH read | Everything else |
| 2 | ABLATION and TEST driver code (new modules) tested on the committed dev fixture | Running them for real needs signed v4 | Everything else |
| 2 | B2 retrain code, B5 code, B4 follow-up log | REVAL-01 | Everything else |
| 3 (after signature) | Run ABLATION, TEST; report against pre-registered criteria | The FRESH read (SEL-03 says "before the FRESH read") | Power Systems wait |
| 4 (2026-10-31T00Z gate) | If Power Systems values arrived: config version bump, refit cooling/reference for those cities, re-score TEST veto, hash manifest | The FRESH read | Nothing; this is the one-day crunch. Pre-build it as one command |
| 5 (>= 2026-11-01T00:00Z) | Single FRESH read, then owner decision record (SEL-04) | REVAL-01 closure, ml-modeling STATE update | Dry-run rehearsal beforehand (no network, no FRESH read) |
| 6 | Conditional second read at >= 2026-11-08T00:00Z if no winner | A pick | REVAL-01 re-run |
| 7 | REVAL-01: B2 promote (ask before push), replay re-run, closure decisions, GO/NO-GO | The GO | Can start before the FRESH read (none of it touches FRESH data), but ROADMAP says closure comes after SEL-04 |

Nothing in B2/B5/REVAL touches FRESH rows: the re-run window 2026-09-08..09-28 ends before `FRESH_BASIS_START` (2026-09-30T00Z).

## Architectural Responsibility Map

This phase is a Python backend and offline-evaluation phase (no browser or SSR tier). Tiers are adapted accordingly.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Per-city conductor values and sources | Config (`backend/config.py`) | Docs (`city_rating_v1.md`) | Values change by config edit plus version bump, not code (COND-01) |
| Production conductor resolution | Backend library (`city_point.py`) | Rating identity | One resolver; the shadow path keeps `city_point.city_point` |
| Rating identity (fingerprint, config version) | Backend library (`rating_identity.py`) | Supabase rows | Must stay importable by the Phase 3 backfill child |
| Byte-identical shadow proof | Test tier (committed fixtures) | Git (`git diff` on frozen files, artifact hashes) | The promise is about outputs, not just source text |
| Protocol v4 text, signature, decision records | Governance docs (`docs/data-science/decisions/`) | ml-modeling STATE.md | Must be signed before any FRESH outcome |
| FRESH headline scoring, guard, evidence | Offline evaluation tooling (`forecast_shadow_confirm/eval_core/decision`) | Open-Meteo APIs | Frozen except as v4 allows |
| ABLATION and TEST scoring, refit under alternative conductors | New offline modules reusing frozen helpers | Cached frames in `data/experiment` | Never touches `data/shadow/models` |
| Forecast retrain (B2), band fallback (B5) | Backend library (`forecast_training.py`, `city_pipeline.py`) | Live runner (GitHub Actions), `LIVE_ARTIFACT_HASHES.sha256` | Promotion changes live CI behaviour |
| REVAL re-run and report | Offline validation (`real_data_validation.py replay/report`) | Docs | Offline replay over the stored trace |
| Provisional-label lift on stored rows | Supabase (`city_rating.rating_basis`) | Schema doc | Needs an owner-run data change (Open Question 2) |

## Standard Stack

### Core (no new packages)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python (project venv) | 3.12.13 | Runtime | `/Users/aphan/Senior_Design/.venv/bin/python` [VERIFIED: `python --version`] |
| pandas | 2.3.3 | Frames, time handling | Pinned in `requirements.txt` [VERIFIED: `requirements.txt`, import probe] |
| numpy | 2.4.3 | Physics arrays | Pinned [VERIFIED] |
| scikit-learn | 1.9.1 | LinearRegression, GradientBoostingRegressor, MLPRegressor, HistGradientBoosting | Pinned; same versions the frozen artifacts used [VERIFIED] |
| joblib | 1.6.0 | Artifact persistence | Arrives with scikit-learn [VERIFIED import probe] |
| scipy | 1.17.1 | Bootstrap/test statistics in `forecast_shadow_score_stats` | Pinned [VERIFIED] |
| pytest | 9.0.3 | Tests | Convention from prior phases [VERIFIED] |
| psycopg | 3.3.6 | DB tests only | Installed [VERIFIED import probe] |

### Supporting (existing project modules to reuse, not rebuild)

| Module | Use in Phase 7 |
|--------|----------------|
| `forecast_shadow_fit_models` (`fit_from_frame`, `assert_no_test_leak`, `restrict_to_train_val`, `WIND_CONFIGURATION`, `COOLING_CONFIGURATION`, `train_val_window_end`) | Recipe for refits; call the lower-level pieces with an explicit point |
| `forecast_experiment` (`_add_correction_columns(frame, geometry)`, `_city_ampacity`, `_wind_corrected_ampacity(model, frame, geometry)`, `_cooling_corrected_ampacity`, `filter_to_exact_lead`) | Duck-typed `geometry` (needs `bearing_deg` and `conductor`), so any production `CityPoint` works without editing |
| `forecast_shadow_confirm` (`prepare_city_frame`, `candidate_predictions`, `leakage_probe`, `run_confirmation(frame_provider=, model_loader=, window=)`) | FRESH read and TEST scoring |
| `forecast_shadow_score_stats` (`build_family_report`, `per_city_comparison`, `moving_block_bootstrap_means`) | ABLATION pairwise intervals and the 9-test Holm family |
| `real_data_validation` (`replay`, `report`, `replay_fidelity`) | REVAL-01 re-run |
| `dlr_live_check_models` (`--write-manifest`) | B2 promotion manifest |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Re-pin v4 constants as a signed round in `forecast_shadow_eval_core` | Pass v4 dates with `--override-reason` | Override disables the pre-instant and one-shot refusals. Rejected |
| New `forecast_conductor_ablation.py` / TEST driver modules | Add optional point parameters to frozen `forecast_shadow_fit_models` | New modules keep frozen files at zero diff. Preferred; the geometry seam in confirm is only needed if Power Systems answers |
| Golden JSON captured at HEAD | Materialize pre-change modules from git in a child process (the `phase3_config_fingerprints` pattern) | The child approach is stronger but heavier. Use committed JSON plus the artifact hash check; add the child approach only if cheap |

**Installation:** none. `requirements.txt` is unchanged by this phase.

**Version verification:** `pip freeze` equivalents were read from `requirements.txt` and import probes this session. No registry lookups were needed because no package is added.

## Package Legitimacy Audit

No external package is installed or added by this phase. Every dependency above is already pinned in `requirements.txt` and installed in the project venv. `gsd_run query package-legitimacy check` was not run because there is nothing to check.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                      (owner)  v4 text ──sign──► [GATE: v4 signed]
                                                    │ unlocks: ABLATION/TEST runs, frozen-module merges, FRESH read
 config.PRODUCTION_CONDUCTORS (+sources)            │
        │                                           ▼
        ▼                              ┌──────────────────────────────┐
 city_point.production_city_point ───► │ production rating path       │──► city_rating.rate_city ─► Supabase rows
        │                    │         │ (rate, forecast_training,    │       (config_fingerprint, forecast/anomaly hashes)
        │                    │         │  anomaly_training, validation)│
        │                    ▼         └──────────────────────────────┘
        │          rating_identity.rating_config_snapshot (getattr fallback for Phase 3 child)
        ▼
 candidate geometry for K-set (Drake-75 … Suwannee-200, +163 m) ─┐
                                                                 ▼
 cached frames data/experiment/*_2024-01-20_2026-09-29_* ──► filter < 2026-03-17 ──► ABLATION: fit train, score validation (per K)
        │                                                  └► TEST window >= 2026-03-18 ──► score frozen artifacts ──► veto flags
        │
 FRESH frames (network, round-specific fetch window) ──► run_confirmation(v4 round) ──► 9-test family ──► v4 ship rule (2% of mean truth, no-pick)
                                                                                         │
 Shadow path (UNCHANGED): city_point.city_point ─ collector ─ 12 frozen artifacts ─ logs ─┴─► live-system check (never pooled)

 B2: city_training_frame(wind_speed := projected) ─► retrain ─► new joblib ─► --write-manifest ─► commit (ASK before push)
 B5: city_pipeline: ml withheld (lookback) ─► naive band to G6 ─► trace key g6_forecast_method
 REVAL: stored trace (2026-09-08..09-28) ─► replay --method ml (offline) ─► report ─► owner GO/NO-GO ─► label lift
```

### Recommended Project Structure

```
backend/
├── config.py                      # + PRODUCTION_CONDUCTORS, PRODUCTION_CONDUCTOR_SOURCES; RATING_CONFIG_VERSION bump; RATING_BASIS text at GO
├── city_point.py                  # + production_city_point(city); city_point() byte-unchanged
├── rating_identity.py             # snapshot uses production resolver via getattr fallback; imports unchanged
├── city_rating.py, anomaly_training.py, forecast_training.py, real_data_validation.py  # repoint to production resolver
├── city_pipeline.py               # B5: naive band when ml withheld for lookback
├── forecast_training.py           # B2: wind_speed feature := projected, in city_training_frame only
├── forecast_conductor_refit.py    # NEW: refit(city, point, ...) -> hashed artifacts outside data/shadow/models
├── forecast_conductor_ablation.py # NEW: K-set ABLATION re-score + invariance report
├── forecast_test_split_score.py   # NEW: TEST scoring (cached-frame provider) + veto flags
├── forecast_shadow_decision_v4.py # NEW: v4 ship rule (relative margin, no-pick) leaving v3 module intact
└── forecast_shadow_eval_core.py / forecast_shadow_confirm.py  # ONLY v4-authorised edits, merged after signing
backend/tests/fixtures/            # + golden_shadow_baseline_d71c501.json (+ generator script)
data/models/conductor_refit/<config_version>/   # NEW refit artifacts + ARTIFACT_HASHES.sha256 (never data/shadow/models)
docs/data-science/decisions/confirmation_protocol_v4_*.md  # NEW: v4 + signing copy
```

### Pattern 1: Per-city table plus a production-only resolver

**What:** One explicit, per-city table in `config.py` (values and a separate sources table). A new `city_point.production_city_point(city)` builds a `CityPoint` from it. `city_point.city_point` and `config.conductor_kwargs_for` stay byte-identical.

**When to use:** Every production caller (rating, training, validation, identity). Never in shadow modules.

**Verified values the table must start from (D-09):**
`config.py:140-148`:
```python
DEFAULT_CONDUCTOR_CONFIG_KWARGS: dict = {
    "diameter_m": 0.02814,      # 795 kcmil Drake ACSR
    "resistance_ac": 0.0726,    # Ω/km at 25°C
    "emissivity": 0.8,
    "absorptivity": 0.8,
    "max_temp_c": 75.0,
    "line_azimuth": 90.0,       # set to actual line bearing
    "elevation_m": 900.0,       # West Texas Permian Basin avg elevation
}
```
`config.py:216-221`:
```python
CITY_LINE_BEARING_DEG: dict[str, float] = {
    "AUSTIN": 173.15,
    "CORPUS_CHRISTI": 173.15,
    "MIDLAND": 267.54,
    "EL_PASO": 267.54,
}
```
`ConductorConfig` constructor [VERIFIED: `thermal_model.py:62-85`] also has `resist_temp_coef=0.00404`. The table may omit it (the default applies and is fingerprinted via `vars(conductor)`).

**Example (skeleton; names are recommendations):**
```python
# config.py
PRODUCTION_CONDUCTORS: dict[str, dict] = {
    "AUSTIN": {
        "conductor_type": "795 kcmil ACSR Drake (model default)",
        "diameter_m": 0.02814, "resistance_ac": 0.0726,
        "emissivity": 0.8, "absorptivity": 0.8,
        "max_temp_c": 75.0, "elevation_m": 900.0, "line_azimuth": 173.15,
    },
    # CORPUS_CHRISTI (173.15), MIDLAND (267.54), EL_PASO (267.54) likewise
}
PRODUCTION_CONDUCTOR_SOURCES: dict[str, dict[str, str]] = {
    "AUSTIN": {name: "current model default, provisional; Power Systems pending" for name in (...)},
}

def production_conductor_kwargs_for(city: str) -> dict:
    """ConductorConfig kwargs for `city`; KeyError naming valid cities. Drops conductor_type."""
```
```python
# city_point.py (city_point() untouched)
def production_city_point(city: str) -> CityPoint:
    if city not in config.LOCATIONS:
        raise KeyError(f"Unknown city {city!r}. Valid cities: {sorted(config.LOCATIONS)}")
    kwargs = config.production_conductor_kwargs_for(city)
    return CityPoint(name=city, coord=config.CITY_COORDINATES[city],
                     bearing_deg=kwargs["line_azimuth"],
                     conductor=thermal_model.ConductorConfig(**kwargs),
                     static_rating=config.STATIC_RATINGS[city],
                     rating_bounds=config.RATING_BOUNDS_BY_LOCATION[city])
```
**Design points:**
- `bearing_deg` must come from the table's azimuth, because `_project_wind` and `perpendicular_wind` use `point.bearing_deg` [VERIFIED: `city_rating.py:408`, `forecast_training.py:204-209`].
- Strict lookup, plus a completeness test (every `config.LOCATIONS` city has a table entry and a non-empty source for every value). Same pattern as `ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` ("Every key in LOCATIONS must appear here -- a test asserts it", `config.py` near line 697). The `synthetic_city` fixture in `city_rating_test.py:37-44` monkeypatches `LOCATIONS` and several dicts; it must gain a `PRODUCTION_CONDUCTORS` entry.
- Static ratings, bounds and coordinates are shared. `dlr_orchestrator.py:95`, `supabase_store.py:547`, `supabase_smoke.py:74` read only `static_rating` from `city_point.city_point`; leave them (values are identical).
- Add an explicit "provisional parity" test (production table equals Drake default plus `CITY_LINE_BEARING_DEG`) with a docstring saying it is meant to be deleted when Power Systems' values land.

### Pattern 2: Keep the rating identity compatible with the Phase 3 backfill child

`rating_identity.rating_config_snapshot` calls `city_point.city_point(city)` today (`rating_identity.py:122`). The fingerprint must describe the production conductor, so it must switch. Constraints, all verified:
- The backfill loader evaluates the **live** `rating_identity.py` against **Phase 3 copies** of `config.py`, `city_point.py`, `thermal_model.py`, and aborts if any other live backend module was imported (`supabase_load_backfill.py:195-216`).
- A test pins `rating_identity`'s top-level imports to `{"json", "hashlib", "config", "city_point"}` (`supabase_load_backfill_test.py:617-628`).
- So: do not create a new module for the resolver. Put it in `city_point.py` and resolve it defensively: `resolve = getattr(city_point, "production_city_point", city_point.city_point)`. The Phase 3 copy lacks the function and falls back to the Drake path, which is exactly what produced the backfill rows.
- `FINGERPRINTED_CONFIG_NAMES` reads use `getattr(config, name, None)` (`rating_identity.py:136`), so a new name is `None` in the Phase 3 config. Safe.
- The AST guard `test_every_config_name_the_rating_path_reads_is_classified` (`rating_identity_test.py`) fails until `PRODUCTION_CONDUCTORS`, `PRODUCTION_CONDUCTOR_SOURCES` and `production_conductor_kwargs_for` are classified in `FINGERPRINTED_CONFIG_NAMES` or `UNFINGERPRINTED_CONFIG_NAMES` with a reason.
- **Recommendation:** fingerprint `PRODUCTION_CONDUCTORS` (includes `conductor_type`, so DB-06's "type" is covered). List `PRODUCTION_CONDUCTOR_SOURCES` and `production_conductor_kwargs_for` as unfingerprinted with reasons ("provenance text; values are fingerprinted", "a function; its result is fingerprinted as ConductorConfig attributes"), so editing a source note does not change every row's fingerprint. Because the table is new, every fingerprint changes once at introduction. Bump `RATING_CONFIG_VERSION` in the same change and update `docs/data-science/schema/city_rating_v1.md` (`supabase_schema_doc_test.py:143-147` pins both the label and the `RATING_BASIS` text to that doc).
- Existing tests patch `city_point.city_point` to change AUSTIN's conductor (`rating_identity_test.py:_patch_austin_conductor`). They must patch the production resolver instead. Add per-field cases for the new table next to the existing `_CASES`.
- The test at `supabase_load_backfill_test.py:~540-556` replaces the text `"max_temp_c": 75.0,` throughout `config.py`. A new table that also contains that literal still yields different fingerprints, so the test remains valid.

### Pattern 3: Golden test for COND-02 (capture before editing)

Capture fixtures at HEAD `d71c501` (the current `main`, tree untouched) and commit them as the first change. What to pin (all reachable offline from the committed dev fixture `backend/tests/fixtures/shadow_eval_frozen_dev_frames.csv.gz`, sha256 `a397c82d5d541ee0941204a6c64c53782529b4a6593ed9bf83a9d22cdae26250` [VERIFIED: `forecast_shadow_eval_validation_test.py` header]):
1. `city_point.city_point(c)` snapshot for all four cities: `vars(conductor)`, `bearing_deg`, `coord`, static rating, bounds (JSON with `repr` floats).
2. Truth, `raw_forecast`, persistence from `weather_to_arm5_frame` and the `_arms` callables on the fixture for each city.
3. `fit_from_frame(city, fixture_frame)` outputs. Compare coefficient and prediction arrays (`tobytes()` hash) rather than joblib bytes; also assert `shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256` for the 12 frozen artifacts.
4. A development-basis `run_confirmation` on the fixture (injected `frame_provider` and `model_loader`, as the validation suite does): the canonical JSON of `family` and `decision`, with timestamps, paths and git sha removed.
5. Source-level guard: `git diff --exit-code d71c501 -- backend/forecast_shadow_pipeline.py backend/forecast_shadow_fit_models.py backend/forecast_shadow_fit_reference_refit.py backend/forecast_shadow_demo.py backend/forecast_shadow_collect.py backend/legacy_corridor.py .github/workflows/shadow_collect.yml data/shadow/models`, expressed as a test that reads `git diff --name-only` (frozen-eval files are exempt only for the v4-authorised edits, listed explicitly).

Shadow transitive production dependencies the golden test must cover: `ampacity_forecast`, `forecast_training`, `thermal_model`, `weather_provider`, `wind_vector`, `config`, `city_point` [VERIFIED: import scan]. The CI workflows do not run pytest [VERIFIED: `.github/workflows/*.yml` grep], so goldens only need local determinism under the pinned versions; record sklearn/numpy versions in the fixture.

### Pattern 4: v4 as a signed "protocol round", not an override

**Verified current pins** (`forecast_shadow_eval_core.py:65-73`):
```python
EVALUATION_INSTANT_DEFAULT = pd.Timestamp("2026-11-24T00:00:00Z")
VALID_TIME_CUTOFF_DEFAULT = pd.Timestamp("2026-11-17T00:00:00Z")
MODEL_FREEZE = pd.Timestamp("2026-11-01T00:00:00Z")
...
FRESH_BASIS_START = pd.Timestamp("2026-09-30T00:00:00Z")
RECON_FETCH_START = "2026-09-28"
RECON_FETCH_END = "2026-11-16"
```
and the guard (`check_guard`, lines 397-424): non-default instant/cutoff require an override reason; with an override, `now_ts < instant` and the prior-run refusal are skipped (`if now_ts < instant and override is None`, `if prior and override is None`).

What breaks if v4 is just passed on the command line:
- `production_frame_provider` raises unless the window equals `RECON_FETCH_START..RECON_FETCH_END` (`forecast_shadow_confirm.py:186-191`).
- `dry_run` and `run_confirmation` write the pinned fetch window into the plan and the config record (`:640`, `:753-755`).
- `run_confirmation` refuses a non-default window when no `frame_provider` is injected (`:618`).

**Recommendation:** add a small round registry to `forecast_shadow_eval_core` (v4-authorised edit, merged after signing): `v4-read1` (instant 2026-11-01T00Z, cutoff 2026-10-25T00Z, fetch 2026-09-28..2026-10-24) and `v4-read2` (instant 2026-11-08T00Z, cutoff 2026-11-01T00Z, fetch 2026-09-28..2026-10-31). The module defaults become `v4-read1`; the CLI gains `--round`. Non-default detection compares against the selected round, so no override is needed and the instant refusal and one-shot refusal stay armed. Each round gets its own evidence subroot (`data/shadow/evaluation/v4-read1`, `.../v4-read2`), which also lets the one-shot rule work per round. Update the 82 lines that mention these dates or constants (57 in tests, 25 in the three modules; `grep -c` line counts), across `forecast_shadow_confirm_test.py` (22), `forecast_shadow_eval_core_test.py` (12), `forecast_shadow_eval_validation_test.py` (17), `forecast_shadow_score_test.py` (6) and the three modules (13 + 11 + 1) [VERIFIED: grep counts].

Row arithmetic [VERIFIED by arithmetic and the v3 doc's own method]: slots are 6-hourly, `hour % 6 == 0`. 2026-09-30T00Z..2026-10-24T18Z is 25 days x 4 = **100** rows per city. Read 2 covers 2026-09-30T00Z..2026-10-31T18Z = 32 days x 4 = **128** rows per city (CONTEXT says "about 130").

Truth-data availability: Open-Meteo's historical API documents ERA5 as "Daily with 5 days delay" [CITED: open-meteo.com/en/docs/historical-weather-api]. The last scored valid hour is 2026-10-24T18Z, which is about 7.25 days before the instant (2 days of margin). The Previous Runs API page does not state GFS currency or latency [CITED: open-meteo.com/en/docs/previous-runs-api]; a `--dry-run`-style rehearsal of a short recent window on development data cannot test this without reading FRESH, so treat fetch success as a day-of risk (`FrameFetchError` is recorded per city and never retried).

### Pattern 5: Refit driver (new module, new hashed location)

- Reuse the lower-level pieces with an explicit point: `forecast_experiment._add_correction_columns(exact, point)`, `forecast_correction_models.fit_cooling_correction(exact, estimator, target="log_ratio", conductor=point.conductor)`, `forecast_training.build_training_matrix(..., horizon_minutes=1440)` plus `CANDIDATE_ESTIMATORS["MLPRegressor"]()`. Re-implement only the thin `weather_to_arm5_frame` variant that takes the point (the shadow version hardcodes `city_point.city_point`, `forecast_shadow_fit_models.py:98`).
- Use `restrict_to_train_val` and `assert_no_test_leak` on every frame (they check both `datetime_utc` and `anchor_datetime_utc` against `FROZEN_TEST_SPLIT_START = "2026-03-17"`, `forecast_experiment_audit.py:81`).
- Write artifacts to `data/models/conductor_refit/<config_version>/<method>_<CITY>.joblib` and a sha256 manifest beside them. Never call `forecast_shadow_pipeline.save_correction_model` (it targets `SHADOW_MODEL_DIR`, `forecast_shadow_pipeline.py:1021-1027`).
- Verify each artifact against the manifest **before** `joblib.load` (a joblib file is a pickle; same rule as `dlr_live_check_models`).
- The FRESH scorer's `provenance()` records hashes only for `data/shadow/models` (`forecast_shadow_eval_core.py:815-870`). When refit artifacts are scored, the report must record their hashes too (small v4-authorised edit, or a `scored_artifacts` block added by the wrapper).
- Measured cost: all three models for one city in 3.5 s. Rebuild everything in a minute or two.

### Pattern 6: ABLATION and TEST on cached frames

- Cached frames exist locally: `data/experiment/anchored_pair_frame_{CITY}_2024-01-20_2026-09-29_lead24_previous_runs.csv` for the four cities [VERIFIED: `ls data/experiment`]. They are git-ignored, so run in the main checkout, not a worktree. **Never open** the `..._2026-09-30_2026-10-04_...` files that sit next to them.
- ABLATION: filter to rows < 2026-03-17 with `load_city_frame` (which already restricts), assert it, then split train (up to 2025-09-01T18Z) and validation (2025-09-02..2026-03-16). The runbook and audit record 2360 train and 784 validation exact-lead rows per city [CITED: `shadow_collection_runbook.md` Fit-window section; `forecast_correction_followup_audit.md` basis manifest table]. Pin the boundary "2025-09-02" in the driver and assert the 784-row validation count per city.
- TEST: the frozen artifacts were fit on rows < 2026-03-17, so TEST rows are out of sample for them. `prepare_city_frame` raises `ReconstructionError` if the minimum anchor is earlier than 2026-03-17T00Z (`split_start = train_val_window_end + 1 day`). With the 24 h lead, **the first usable TEST valid time is 2026-03-18T00Z**. State that in v4 (the first TEST day is excluded, 4 rows per city).
- A development-window provider exists in tests (`forecast_shadow_eval_validation_test.py`: fixture-backed `frame_provider(city, evidence_dir=...)` returning `(frame, archive_weather, meta)`). For TEST, build `archive_weather` from the cached frame's own truth columns so `candidate_predictions`' exact cross-check passes. `run_confirmation` requires an injected `model_loader` for any non-FRESH basis (`forecast_shadow_confirm.py` "refuse a development-basis run without an injected `model_loader`"); passing `forecast_shadow_pipeline.load_correction_model` explicitly satisfies it without editing the frozen file.
- Bracketing set from the research script `03-05-conductor_sensitivity.py` (catalogue values, Rac at 25 °C in Ω/km, flagged approximate by its own comment): Suwannee 959.6 ACSS/TW `(0.02819 m, 0.0597)`, Drake 795 `(0.02814 m, 0.0726)`, Rail 954 `(0.02959 m, 0.0612)`, Falcon 1590 `(0.03924 m, 0.0371)`. The research note's Falcon OD (1.544 in = 0.03922 m) and Rail OD (1.165 in = 0.02959 m) agree [CITED: `03-05-CONDUCTOR-RESEARCH.md` Q4]. ACSS resistance in the repo's linear model at 150-200 °C is unverified [CITED: `shadow_early_decision_options.md` "Items I could not verify"].

### Pattern 7: B2 retrain (confine the change)

- Verified cause: `city_training_frame` computes `perp` only for `dlr_amps` and stores `"wind_speed": weather["wind_speed"]` as the feature (`forecast_training.py:204-224`); serving reads the archive's projected `wind_speed` (`city_rating._project_wind`). `config.py:340-342`: `FORECAST_ML_FEATURE_WEATHER_COLUMNS: tuple[str, ...] = ("air_temp", "wind_speed", "solar_radiation",)`.
- Fix: `"wind_speed": perp` in `city_training_frame` only. Do not touch `build_training_matrix` or `ampacity_forecast.build_ml_features`; the shadow reference candidate calls both (`forecast_shadow_fit_models.py:113-117`).
- The anomaly detector's features are raw weather (`ANOMALY_ML_FEATURE_COLUMNS = ("air_temp", "wind_speed", "solar_radiation")`, `config.py:604-606`) and `city_rating._RawWindDetector` hands it the measured speed, so B2 does not touch it. The anomaly **training validation** uses the conductor only in `_dlr_amps_for` (`anomaly_training.py:~552-570`) for the rolling-baseline arm. A conductor change therefore does not force an anomaly-model refit; it changes that arm's validation numbers. Record this correction of D-16's phrase "conductor-driven detector retrain" in v4/the follow-up note.
- The trainer overwrites the live location. `forecast_training.main`/`_run_bakeoff` call `persist_model`, which `os.replace`s `data/models/forecast_{CITY}.joblib`, and write `training_frame_{CITY}.csv` and `bakeoff_report.json` (`forecast_training.py:~560-640`). The current files are tracked in git (OD-10), so git holds the old versions, but copy them to `data/models/retrain_logs/` first.
- Training pulls Open-Meteo archive years (`fetch_city_weather`: `last_complete_year = now.year - 1`, three network calls per city) so it needs network; 2023-2025 are non-FRESH.
- Promotion: `PYTHONPATH=backend python backend/dlr_live_check_models.py --write-manifest`, then commit artifacts and `LIVE_ARTIFACT_HASHES.sha256` **in one commit**. The live job fails red if the manifest and files disagree (`dlr_live_check_models.py`). Ask the owner before pushing. If Power Systems values are adopted, the retrain is redone (dlr_amps and the projected wind both depend on the table).

### Pattern 8: B5 band fallback

- Verified logic: `city_pipeline.py` builds `forecast_for_detector = None` when `gap_reason` is set, using `data_cleaning.forecast_gap_reason` (`data_cleaning.py:438-466`). Two reasons exist: trailing gap greater than `MAX_TRAILING_GAP_SLOTS: int = 1`, and (ml only) fewer than `ML_LOOKBACK_ROWS` consecutive rows (`data_cleaning.py:79`, `:87-89`).
- D-17 applies only to the **lookback** reason. When it fires and the trailing-gap rule passes, compute `ampacity_forecast.forecast_ampacity(history, method="naive")` and give that band to `AnomalyDetector.for_city(...)`. A trailing gap greater than 1 slot withholds the naive band too (same rule), so keep that.
- Naive still needs `FORECAST_MIN_HISTORY_ROWS = 12` usable rows (`config.py:297`) and a positive-width band (the degenerate-band guard applies). On sparse AUSTIN history the naive band may still be absent; the report must say how often.
- Add a pipeline key (for example `g6_forecast_method`: `"ml"`, `"naive"`, `None`) and carry it through the backfill trace (`backfill_archive._trace_records`) and `real_data_validation` pass-through names (`_PASS_THROUGH_NAMES`, line 275). Do **not** reuse `forecast_method` or `forecast_used_by_g6` for this: both are `city_rating` columns (`supabase_store.py:593`, `:600`) and would then misdescribe the stored forecast. A new column needs an additive migration and an owner-approved schema push (Open Question 3).

### Pattern 9: REVAL-01 re-run is an offline replay

- `real_data_validation.py replay --method ml` re-runs the real per-city pipeline over the stored trace, offline, into new files; it refuses existing outputs and refuses without the anomaly and (for ml) forecast models (`replay`, lines 1273-1317). Inputs exist locally: archive sha256 `18f999aac44540138cfb2a2d1c7f624688e66d261e391a01b036970b8bfa25cf` matched this session [VERIFIED: `shasum`]; trace and the earlier naive replay files are present.
- The replay exercises B5 automatically (it calls `run_city_pipeline`) and the B2-retrained models (`ampacity_forecast._model_path_for`).
- `real_data_validation.py` recomputes ampacity with `city_point.city_point` (lines 310, 373, 490). Repoint to the production resolver. Under D-09 the numbers are unchanged. If any Power Systems value is adopted, the traced observations are unchanged but ratings change.
- Fidelity: `replay_fidelity` counts a mismatch when a fixed-gate outcome, the computed rating (1e-9 A) or G6 reach differs from the *original* run (`real_data_validation.py:1319-1368`). Under Drake the gate outcomes and computed ratings are identical, so 0 is attainable even with B2/B5. If a conductor changes, mismatches are expected by construction. Run an unchanged-config **control** replay first to prove the harness still reproduces the trace, then report the new-config replay against it (see Pitfall 14).
- The re-run window ends 2026-09-28T23:00Z, before `FRESH_BASIS_START`.

### Anti-Patterns to Avoid
- **Editing `config.DEFAULT_CONDUCTOR_CONFIG_KWARGS` or `conductor_kwargs_for`:** shadow depends on them; the production table must be separate.
- **Giving the resolver a new module:** it would break the Phase 3 identity child.
- **`--override-reason` for v4 dates:** disables the two anti-peeking refusals.
- **Adding optional parameters to frozen shadow modules for convenience:** use new modules; touch frozen files only for v4-authorised edits, merged after signing.
- **Running any scorer in scoring mode on real FRESH data before the instant** (including "just to check"): `--dry-run` and `--count-only` only.
- **Letting a Power Systems answer silently change the shadow path.**

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pairwise intervals, Holm family, ACF effective n | A new bootstrap | `forecast_shadow_score_stats` (`build_family_report`, `per_city_comparison`, `moving_block_bootstrap_means`) | Seeded, tested, already defines the 9-test city-clustered family |
| Frame preparation, anchors, leakage probe | New preprocessing | `forecast_shadow_confirm.prepare_city_frame`, `candidate_predictions`, `leakage_probe` | Enforces exact 24 h lead, archive cross-check, sabotage probe |
| Anti-peeking and one-shot guard | A second guard | `forecast_shadow_eval_core.check_guard` with a round registry | One implementation to trust |
| Calendar splits | `.iloc` slicing | `experiment_splits.calendar_split` / the pinned 2025-09-02 boundary with row-count asserts | Existing purity and empty-side checks |
| Test-leak assertions | Ad-hoc date checks | `forecast_shadow_fit_models.assert_no_test_leak`, `restrict_to_train_val` | Checks both timestamp columns |
| Replay and report | A new validator | `real_data_validation.py replay/report` | Already the Phase 3 method; fidelity is built in |
| Model hash manifest | New format | `sha256sum` format via `dlr_live_check_models` (`--write-manifest`, `read_manifest`) | Same loader, same CI check |
| Config identity | A hand-bumped version as identity | `rating_identity.rating_config_fingerprint` | Automatic and per city |

**Key insight:** every statistical and identity primitive already exists and is tested. The risk in this phase is in seams and ordering, not in missing machinery.

## Runtime State Inventory

This phase changes configuration identity, replaces model files and lifts a label on stored rows. It is not a rename, but these runtime states matter.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | Supabase `city_rating` rows (live hourly since 2026-10-24/25, plus the Phase 3 backfill) carry `rating_basis`, `config_version`, `config_fingerprint`, model hashes. Backfill rows carry `PHASE3_CONFIG_VERSION` and fingerprints computed on the Phase 3 commit | Code edit for new rows. A GO lifting the label on **stored** rows needs an owner-run UPDATE or an accepted "going forward only" rule (Open Question 2). The loader's DO NOTHING means old backfill rows are never rewritten by code |
| Live service config | `dlr_live.yml` runs hourly from `main` in the `production` environment; its pre-flight verifies the 8 models against `data/models/LIVE_ARTIFACT_HASHES.sha256` | Promote B2 models and the manifest in one commit; ask before pushing |
| OS-registered state | cron-job.org hourly job (OD-1); the shadow cron `0 0,6,12,18 * * *` | None. Do not touch `shadow_collect.yml` |
| Secrets and env vars | `SUPABASE_DB_URL` (environment secret), provider tokens | None. Never print URLs or connection details in reports |
| Build artifacts | `data/shadow/models/*.joblib` (12 frozen, hashed in `ARTIFACT_HASHES.sha256`); `data/models/*.joblib` (8 live, git-tracked); `data/models/training_frame_*.csv` (rewritten by the trainer) | Never overwrite the 12 frozen; archive the 8 live before retraining; new refits go to `data/models/conductor_refit/<version>/` |

## Common Pitfalls

### Pitfall 1: Golden baseline captured after the first edit
**What goes wrong:** "before and after" compares against already-modified code, so the proof is vacuous.
**Why:** Shadow imports production modules (`ampacity_forecast`, `forecast_training`, `config`, `city_point`).
**Avoid:** First commit of the phase is the fixtures plus a test that passes on the untouched tree. Record the commit hash in the fixture.
**Warning signs:** The golden commit is not an ancestor of every production-code commit.

### Pitfall 2: A new module for the resolver breaks the Phase 3 identity child
**What goes wrong:** `phase3_config_fingerprints` aborts with "live backend modules were imported" or the import-set test fails.
**Avoid:** Resolver lives in `city_point.py`; identity resolves it with `getattr(..., fallback)`.

### Pitfall 3: Unclassified config names fail the AST guard
**What goes wrong:** `test_every_config_name_the_rating_path_reads_is_classified` fails as soon as `city_point` reads `config.PRODUCTION_*`.
**Avoid:** Classify in `FINGERPRINTED_CONFIG_NAMES` / `UNFINGERPRINTED_CONFIG_NAMES` in the same commit.

### Pitfall 4: Override disables the anti-peeking guard
**What goes wrong:** Using `--override-reason` to pass v4 dates lets a pre-instant FRESH run through, and a second run too.
**Avoid:** Round registry (Pattern 4). Add tests that a v4 run before the instant is refused and a repeat into the same round root is refused.

### Pitfall 5: Frozen modules edited before signature
**What goes wrong:** Violates the roadmap constraint ("except as a signed v4 explicitly allows") and weakens the anti-peeking record.
**Avoid:** Prepare on a branch; merge after the signing copy exists. v4 must list each permitted edit (round constants, geometry seam, provenance, `--round`).

### Pitfall 6: v4 ambiguity in "qualifies" with a relative bar
**What goes wrong:** The existing rule compares a pooled margin in amps with `DECISION_MARGIN_AMPS = 5.0` and counts cities by sign (`forecast_shadow_decision.py`). "2% of the city's mean truth ampacity" needs: which mean (scored rows of that city), whether the pooled test uses a pooled mean or per-city thresholds, and whether the 3-of-4 count is by sign or by clearing 2%. The report does not carry mean truth today (`descriptive_metrics` has no truth mean).
**Avoid:** v4 defines it numerically; a new `forecast_shadow_decision_v4` adds `mean_truth_amps` per city to the report and reproduces the v3 three levels with the relative margin. Pre-register the exact formula with a worked example.

### Pitfall 7: Refit artifacts scored but not recorded
**What goes wrong:** `provenance()` hashes only `data/shadow/models`, so the report cannot show which refit files were scored.
**Avoid:** Record `scored_artifacts` (path, sha256) for whatever the model loader served.

### Pitfall 8: TEST window starts one day too early
**What goes wrong:** Scoring from 2026-03-17T00Z raises `ReconstructionError` (anchor inside the fit window).
**Avoid:** Start at 2026-03-18T00Z; say so in v4.

### Pitfall 9: ABLATION that scores an in-sample model
**What goes wrong:** The 12 frozen artifacts were fit on train + validation; scoring them on validation is in-sample.
**Avoid:** ABLATION fits on train only (wind once; cooling and reference per K), in memory or in a scratch directory. Never write to `data/shadow/models`.

### Pitfall 10: Second read inflates false-pick chance
**What goes wrong:** The ship rule is mostly a point-estimate threshold (Holm only upgrades the label). Two looks at overlapping data give two chances to pass it, and read 2 includes read 1's rows.
**Avoid:** v4 states how read 2's levels are labelled (for example Holm family alpha 0.05 split across the two reads) and says plainly that read 2 is not independent. Owner choice.

### Pitfall 11: Calibration of expectations at 2%
**What goes wrong:** Under Drake, 2% of mean truth is about 25.2 / 27.5 / 30.5 / 24.7 A (AUSTIN / CORPUS_CHRISTI / MIDLAND / EL_PASO), versus the v3 bar of 5 A. These were computed this session from ABLATION rows only (< 2026-03-17, exact-lead, Drake): mean truth 1257.8 / 1375.8 / 1525.4 / 1236.8 A over 3,144 rows per city. The corridor-era development gaps against `raw_forecast` were about 26 A (wind, Midland) and 4.4 A (cooling, Austin) and negative for wind at Austin (raw 111.44 vs wind 112.57) [CITED: `shadow_early_decision_options.md` section 2]. Corridor `min()` values do not transfer to per-city values, but "no candidate qualifies" is a realistic outcome. Say so in the owner summary.

### Pitfall 12: Synthetic-city fixtures
**What goes wrong:** `city_rating_test.py::synthetic_city` adds a city to several dicts but not the new table; a strict resolver raises `KeyError`.
**Avoid:** Add the table entry to that fixture (and any similar fixture) and keep the resolver strict.

### Pitfall 13: Retrainer overwrites live models in place
**What goes wrong:** `forecast_training` writes `data/models/forecast_{CITY}.joblib` directly; an unpromoted retrain fails the live pre-flight on the next hourly run, if it is committed without the manifest.
**Avoid:** Archive first; promote artifacts and manifest atomically; owner approval before pushing.

### Pitfall 14: "0 replay-fidelity mismatches" under a changed conductor
**What goes wrong:** If a city's conductor changes, computed ratings and G4 outcomes legitimately differ from the original run.
**Avoid:** Report an unchanged-config control replay at 0 mismatches, then the new-config replay with its differences explained. Tell the owner in plain words.

### Pitfall 15: Label lift mechanism undefined
**What goes wrong:** The schema doc says every row stays provisional until REVAL-01 "lifts the label", but the label is a per-row column.
**Avoid:** Decide the mechanism at GO (Open Question 2); the doc test pins `RATING_BASIS` to the schema doc, so change both together.

### Pitfall 16: Local vs UTC dates
**What goes wrong:** The session date (2026-10-25 local) and the machine UTC clock (2026-10-26T04:14Z) differ. v4 text with unqualified dates is ambiguous.
**Avoid:** Write every protocol time in UTC.

## Code Examples

### Guard shape to preserve (verified)
```python
# forecast_shadow_eval_core.py:397-424 (excerpt)
if instant != EVALUATION_INSTANT_DEFAULT:
    nd_dates["evaluation_instant"] = instant.isoformat()
...
if basis == "FRESH":
    if now_ts < instant and override is None:
        raise EvaluationGuardError(...)
    if prior and override is None:
        raise EvaluationGuardError(...)
```

### Round registry (recommended shape)
```python
# forecast_shadow_eval_core.py (v4-authorised edit, merged after signing)
@dataclass(frozen=True)
class ProtocolRound:
    name: str
    instant: pd.Timestamp
    cutoff: pd.Timestamp
    fetch_start: str
    fetch_end: str

V4_READ1 = ProtocolRound("v4-read1", pd.Timestamp("2026-11-01T00:00:00Z"),
                         pd.Timestamp("2026-10-25T00:00:00Z"), "2026-09-28", "2026-10-24")
V4_READ2 = ProtocolRound("v4-read2", pd.Timestamp("2026-11-08T00:00:00Z"),
                         pd.Timestamp("2026-11-01T00:00:00Z"), "2026-09-28", "2026-10-31")
```

### B2 fix (one line, confined)
```python
# forecast_training.city_training_frame (after perp is computed)
"wind_speed": np.asarray(perp, dtype=float),   # was weather["wind_speed"].to_numpy(dtype=float)
```

### Offline re-run (commands follow the documented Reproduce block)
```bash
cd /Users/aphan/Senior_Design && P=data/historical/real_data_validation_2026-09-08_2026-09-28 && \
PYTHONPATH=backend .venv/bin/python backend/real_data_validation.py replay --archive $P.csv --trace ${P}_trace.jsonl \
  --start 2026-09-08T00:00:00Z --end 2026-09-28T23:00:00Z --step-hours 1 --method ml --warmup-hours 168 \
  --archive-out ${P}_replay_ml_p7.csv --trace-out ${P}_replay_ml_p7_trace.jsonl \
  --log-out ${P}_replay_ml_p7_log.csv --fidelity-out ${P}_replay_ml_p7_fidelity.json
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v3: single FRESH read 2026-11-24, 5 A bar, fallback to raw/wind if nothing qualifies | v4: read 2026-11-01 (cutoff 2026-10-25), relative 2% bar, no pick if none qualifies, conditional re-test 2026-11-08 | v4, to be signed | Evaluation code pins and about 57 test lines change |
| One shared Drake conductor for production and shadow | Production per-city table; shadow frozen on Drake | Phase 7 | Resolver split, golden test |
| `ml` trained on measured wind, served projected wind | Trained on projected wind | B2 | New artifact hashes, manifest, live promotion |

**Deprecated/outdated:** the 2026-11-24 evaluation run (retired by v4); the STATE.md note that B1/B2 wait for 2026-11-24 (already superseded).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | joblib bytes of refit models need not be byte-reproducible; comparing coefficient/prediction hashes is enough for the golden test | Pattern 3 | If the owner wants literal artifact bytes compared, the golden test needs a deterministic-dump check |
| A2 | Mixed conductors across cities (partial Power Systems answers) remain valid for a pooled, relative-threshold headline | Open Questions | If not, v4 must say partial answers wait or are excluded |
| A3 | Corridor-era development gaps are only a rough guide to per-city outcomes at 2% | Pitfall 11 | Likely no-pick on 2026-11-01 may be more or less likely than implied |
| A4 | Open-Meteo previous-runs GFS data covers up to the last scored hour on the day of the read | Pattern 4 | A `FrameFetchError` on read day; there is no retry by design |
| A5 | The owner prefers a "going forward" label lift unless an UPDATE is approved | Pitfall 15 | Stored rows would stay labelled provisional |
| A6 | Adding azimuth/emissivity variants to the bracketing set is cheap in compute but raises the number of veto chances | Open Questions | Over-broad vetoes could block every candidate |

## Open Questions

1. **What exactly does "qualifies" mean under a relative bar?**
   - Known: D-04 (3 of 4 cities by point estimate) and D-06 (2% of mean truth, MAE reduction) are fixed; v3 levels and the 9-test Holm family carry over.
   - Unclear: pooled versus per-city threshold; whether a candidate must also beat the other candidates or only `raw_forecast`; tie-breaking.
   - Recommendation: draft a numeric definition with a worked example (using non-FRESH mean truth values above) and ask the owner to confirm in plain language.
2. **How is the provisional label lifted on stored rows after a GO?**
   - Known: `rating_basis` is a per-row column; the schema doc and `RATING_BASIS` are test-coupled; D-13 says rows keep their conductor basis.
   - Unclear: a one-time owner-run UPDATE of old rows, or new rows only.
   - Recommendation: new text going forward plus an owner-approved UPDATE as a checkpoint task.
3. **Should the G6 method that gated each step be a database column?**
   - Known: D-17 says visible in the trace and report. DB columns `forecast_method`/`forecast_used_by_g6` cannot express it.
   - Recommendation: trace and report only for Phase 7. If the owner wants a consumer-visible column, treat it as an additive migration with an owner-gated push.
4. **How are two reads handled statistically?** (Pitfall 10) Owner decides the labelling rule; note read 2 is not independent.
5. **Should the bracketing set include azimuth (and emissivity) variants?** Section 5.4 holds bearing and emissivity fixed. Power Systems may change azimuth. Recommendation: include one or two azimuth variants only if the owner accepts a larger veto surface; compute cost is negligible (3.5 s per city-fit).
6. **What is the production-rows ruling?** Live and backfill rating rows for FRESH-window dates are not shadow outcomes provided nothing joins them to shadow predictions (`shadow_early_decision_options.md` section 6 step 4). No recorded ruling was found. Put it in v4.
7. **If the re-test also names no winner:** CONTEXT suggests no day-ahead pick and the interim G6 method continues; owner to confirm in v4.
8. **Fallback date for the CORPUS_CHRISTI detector refit if Power Systems never answers (D-16).** Discretionary; propose a date in the v4/follow-up note.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Project venv Python | Everything | yes | 3.12.13 | none |
| pandas / numpy / scikit-learn / joblib / scipy | Evaluation and refits | yes | 2.3.3 / 2.4.3 / 1.9.1 / 1.6.0 / 1.17.1 | none |
| Cached frames `data/experiment/..._2024-01-20_2026-09-29_lead24_previous_runs.csv` (4 cities) | ABLATION, TEST | yes | local, git-ignored | rebuild with network (`anchored_pair_frame`) |
| Dev fixture `shadow_eval_frozen_dev_frames.csv.gz` | Tests, golden | yes | committed | none |
| Phase 3 archive/trace for 2026-09-08..09-28 | REVAL-01 replay | yes | archive sha256 matches | none |
| Live models in `data/models` | Replay with ml | yes | 8 files | none |
| Open-Meteo archive and previous-runs APIs | FRESH read, B2 retrain | network at run time | not probed (would touch FRESH dates for the former) | none; failures are recorded, not retried |
| Postgres binaries (`pg_ctl`, `postgres`, `initdb`, `psql`) | DB tests | yes | homebrew (postgresql@16, @18) | tests skip without `DLR_TEST_PG_AUTOSTART=1` |
| `gh` CLI | Pushes/Actions checks | yes | present | none |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none. The only external gate is Power Systems' conductor answer (D-09 provisional values in the meantime).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `/Users/aphan/Senior_Design/pytest.ini` (`pythonpath = backend`, `testpaths = backend/tests`, `python_files = test_*.py *_test.py *_TestSuite.py`) |
| Quick run command | `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider backend/tests/<file>` |
| Full suite command | `/Users/aphan/Senior_Design/.venv/bin/python -m pytest -q -p no:cacheprovider` |
| DB tests | prefix `DLR_TEST_PG_AUTOSTART=1`, add `-rs` |

Baseline measured this session at HEAD `d71c501`: full suite in 2 min 42 s with 1730 passing markers, 48 skipped (DB tests without the autostart flag) and no `F`/`E` markers (counted from the progress dots, because `-q -q` hid the summary line).

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COND-01 | Table complete for every `LOCATIONS` city; every value has a non-empty source; resolver builds `ConductorConfig`; unknown city raises `KeyError` naming cities | unit | `pytest backend/tests/production_conductor_test.py` | no, Wave 0 |
| COND-01 | Each table field change alters only that city's fingerprint; source-only edit does not | unit | `pytest backend/tests/rating_identity_test.py` | exists, extend |
| COND-01 | Provisional parity: table equals Drake default + `CITY_LINE_BEARING_DEG` (marked for removal at Power Systems) | unit | `pytest backend/tests/production_conductor_test.py::test_provisional_parity` | no, Wave 0 |
| COND-02 | Golden: shadow geometry, truth/raw/persistence arrays, fit outputs, dev-basis report and 12 artifact hashes identical to HEAD `d71c501` | golden | `pytest backend/tests/cond02_shadow_golden_test.py` | no, Wave 0 (capture first) |
| COND-02 | Frozen files have no diff except the listed v4 edits | source guard | same file | no, Wave 0 |
| COND-02 | Production callers use the production resolver; shadow callers do not | AST/import test | `pytest backend/tests/production_conductor_test.py::test_caller_split` | no, Wave 0 |
| SEL-01 | v4 round constants; default round is v4-read1; pre-instant FRESH refused; second run into same root refused; no override needed | unit | `pytest backend/tests/forecast_shadow_eval_core_test.py backend/tests/forecast_shadow_confirm_test.py` | exists, update literals |
| SEL-01 | v4 decision: relative 2% margin, 3-of-4 rule, no-pick when none qualifies, three levels preserved | unit | `pytest backend/tests/forecast_shadow_decision_v4_test.py` | no, Wave 0 |
| SEL-02 | Refit uses only rows < 2026-03-17 (assert), writes to the new location, never to `data/shadow/models`, manifest matches, hash verified before load | unit | `pytest backend/tests/forecast_conductor_refit_test.py` | no, Wave 0 |
| SEL-03 | ABLATION: train/validation split counts, K-set recompute, invariance criteria on dev fixture; TEST window starts 2026-03-18; veto flags | unit | `pytest backend/tests/forecast_conductor_ablation_test.py backend/tests/forecast_test_split_score_test.py` | no, Wave 0 |
| SEL-04 | Dry-run reads no FRESH file and makes no network call; dry-run lists v4 planned requests (fetch end 2026-10-24) | unit | `pytest backend/tests/forecast_shadow_confirm_test.py -k dry_run` | exists, update |
| REVAL-01 (B2) | `city_training_frame` stores projected wind in `wind_speed`; `build_training_matrix` and shadow reference outputs unchanged | unit + golden | `pytest backend/tests/forecast_training_test.py backend/tests/cond02_shadow_golden_test.py` | exists, extend |
| REVAL-01 (B5) | Lookback-withheld ml uses naive band; trailing gap withholds both; key `g6_forecast_method` in trace; fallback rows stay out of history | unit | `pytest backend/tests/city_pipeline_test.py backend/tests/data_cleaning_test.py` | exists, extend |
| REVAL-01 | Offline replay on a small synthetic trace reproduces fidelity 0 for unchanged config; report builder accepts the new pass-through key | unit | `pytest backend/tests/real_data_validation_test.py backend/tests/backfill_trace_test.py` | exists, extend |
| REVAL-01 | Live manifest consistent with models; schema doc pinned to label and version | unit | `pytest backend/tests/dlr_live_check_models_test.py backend/tests/supabase_schema_doc_test.py` | exists |

### Sampling Rate
- **Per task commit:** the single test file(s) named for that task, plus `cond02_shadow_golden_test.py` once it exists.
- **Per wave merge:** full suite (about 2 min 45 s) and the DB tests with `DLR_TEST_PG_AUTOSTART=1 ... -rs`.
- **Phase gate:** full suite green, golden test green, `shasum -a 256 -c data/shadow/models/ARTIFACT_HASHES.sha256` clean, `git status` showing no change under `data/shadow/predictions`, before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `backend/tests/fixtures/golden_shadow_baseline_d71c501.json` and its generator script: capture before any production edit.
- [ ] `backend/tests/cond02_shadow_golden_test.py`
- [ ] `backend/tests/production_conductor_test.py`
- [ ] `backend/tests/forecast_shadow_decision_v4_test.py`
- [ ] `backend/tests/forecast_conductor_refit_test.py`
- [ ] `backend/tests/forecast_conductor_ablation_test.py`
- [ ] `backend/tests/forecast_test_split_score_test.py`
- [ ] Updates to the date literals in four existing shadow test files (57 matching lines) and to `synthetic_city`, `rating_identity_test` patching.
- [ ] Framework install: none needed.

## Security Domain

`security_enforcement` is not set to false in `.planning/config.json` [VERIFIED: file contents], so this section applies.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Not touched (no new endpoint) |
| V3 Session Management | no | Not touched |
| V4 Access Control | limited | Anon read-only grants unchanged; the label-lift UPDATE must use the `dlr_writer` or an owner-run service path, never anon |
| V5 Input Validation | yes | Strict per-city table lookup, completeness test, numeric range checks on conductor values in the resolver |
| V6 Cryptography | yes | `hashlib.sha256` only; never hand-roll |
| V10 Malicious code / integrity (joblib pickles) | yes | Verify every artifact hash against the manifest **before** `joblib.load` (refit artifacts, live models); new artifacts only from owner-run local fits |
| V8 Data protection | yes | Evidence directories hold public Open-Meteo data only; never print `SUPABASE_DB_URL`, host, user or project reference in reports |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Peeking at FRESH outcomes before signature or instant | Tampering/Repudiation | Armed guard via round registry; dry-run/count-only only; signed v4 committed before any FRESH-capable code merges; `data/experiment/anchored_pair_frame_*_2026-09-30_*` never opened |
| Swapped or unhashed model artifact loaded | Tampering | Manifest check before load; refits to a new hashed location; frozen 12 verified by `shasum -c` |
| Unpromoted retrain pushed to `main` | Denial of service (live runs go red) | Artifacts and manifest in one commit; owner approval before push |
| Post-hoc protocol change after seeing outcomes | Repudiation | Criteria, thresholds, re-test rule and no-winner action fixed in signed v4; D-03 labels "conductor-conditional" results descriptively |
| Secret leakage via reports or error text | Information disclosure | Existing `redact` conventions in `supabase_store`; reports never include connection strings |
| Config table edited to an implausible value | Tampering | Range validation plus fingerprint change visible on every row |

## Sources

### Primary (HIGH confidence, read this session)
- `/Users/aphan/Senior_Design/.planning/workstreams/production-pipeline/phases/07-.../07-CONTEXT.md`, `REQUIREMENTS.md`, `STATE.md`, `ROADMAP.md` (Phase 7 section)
- `backend/config.py:100-290,325-360,596-620`, `backend/city_point.py`, `backend/rating_identity.py`, `backend/city_rating.py:320-470`, `backend/city_pipeline.py`, `backend/data_cleaning.py:60-140,438-466`, `backend/forecast_training.py:90-340,540-640`, `backend/ampacity_forecast.py:100-200,441-530`, `backend/anomaly_training.py:540-620`
- `backend/forecast_shadow_confirm.py`, `forecast_shadow_eval_core.py:1-140,225-460,715-925`, `forecast_shadow_decision.py`, `forecast_shadow_fit_models.py`, `forecast_shadow_score_stats.py:361-440`, `forecast_shadow_pipeline.py:1010-1050`, `real_data_validation.py:290-330,1273-1372`, `supabase_load_backfill.py:180-300`, `dlr_live_check_models.py:1-150`
- `backend/tests/rating_identity_test.py`, `supabase_load_backfill_test.py:535-660`, `city_rating_test.py:34-60`, `forecast_shadow_eval_validation_test.py` header
- `docs/data-science/decisions/shadow_early_decision_options.md`, `confirmation_protocol_v3_per_city.md`, `real_data_validation.md` (findings, go/no-go, reproduce), `shadow_collection_runbook.md` (fit-window), `forecast_correction_followup_audit.md` (bases), `docs/data-science/schema/city_rating_v1.md`
- `.planning/workstreams/production-pipeline/phases/03-real-data-validation/03-05-CONDUCTOR-RESEARCH.md` and `03-05-conductor_sensitivity.py`
- `data/models/LIVE_ARTIFACT_HASHES.sha256`, `requirements.txt`, `pytest.ini`, `.github/workflows/` listing
- In-session runs: full test suite baseline; one-city fit timing (3.5 s); ABLATION-only mean truth per city; archive sha256 check

### Secondary (MEDIUM confidence)
- [CITED: open-meteo.com/en/docs/historical-weather-api] ERA5 and ERA5-Land "Daily with 5 days delay"
- [CITED: open-meteo.com/en/docs/previous-runs-api] most models archived from January 2024; no stated GFS latency

### Tertiary (LOW confidence)
- None used as a basis for a recommendation.

Tool note: the `research-plan` code seam was not used. Every research question was answered from this repository; the only external facts (ERA5 delay, Previous Runs coverage) were fetched directly from Open-Meteo's documentation.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH (no additions; versions read)
- Architecture: HIGH (every seam and constraint read in code or tests)
- Pitfalls: HIGH for code/test coupling; MEDIUM for statistical drafting items that need owner input
- Schedule: HIGH on sequencing; the Power Systems gate is external

**Research date:** 2026-10-25
**Valid until:** 2026-11-01 for the FRESH-read sequencing; the code-seam findings hold until the files named above change (re-check `git log` on `backend/` before planning)
