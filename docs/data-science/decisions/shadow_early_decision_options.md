# Choosing a forecast method before 2026-11-24, and what a conductor change (B1) does to that choice

**Status:** analysis for the owner, written 2026-10-21. Nothing here is decided, signed or applied. No code,
config, model, workflow or log was changed to write it.

**Anti-peeking statement.** No predicted-versus-truth figure was computed, read or printed for any row with
`valid_time` after 2026-09-29. From the shadow logs only row counts, `valid_time`, `schema_version`,
`forecast_model`, candidate `status` and the `reason` string of `persistence_24h` were read (the v2/v3
mechanical-health-check carve-out, `confirmation_protocol_v3_per_city.md:178-179`). The only new numbers below
come from (1) that health check and (2) a physics-only calculation with the repo's IEEE 738 code at
hand-picked weather values, which uses no observation, forecast or log.

Labels: **UNVERIFIED** = I could not confirm it from the repo or a run; **inference** = my reasoning, not a
recorded finding.

---

## Answer in one paragraph

Yes, production can go live in early November without waiting for 2026-11-24, and no anti-peeking rule has to
be broken. The blocking link is narrower than the 2026-10-21 STATE note implies. **The shadow evaluation is
meant to choose `ml`'s replacement** (Phase 3's stated purpose, `.planning/workstreams/ml-modeling/phases/03-*/03-CONTEXT.md:10-15`;
the owner's 24-hour pivot, `:101-126`; `.planning/workstreams/ml-modeling/STATE.md:33-35`; corrected 2026-10-21
after owner review). But the winner cannot be served by production on go-live day: no shadow candidate is
wired into `ampacity_forecast.FORECAST_METHODS`. G6 also needs an hourly forecast with a band, while the shadow
candidates are point forecasts at four valid hours a day. So until the winner is built in, G6 needs an interim
60-minute method. **If that interim method is naive, B2 disappears**, and nothing about the interim choice
touches the shadow protocol, because C9 is outside v3's scope (`confirmation_protocol_v3_per_city.md:159-164`). **B1 collides with the
shadow evaluation only because production and shadow read the same conductor through `city_point.city_point`**
(`backend/city_point.py:59-60`, `backend/config.py:140-161`). Give production its own conductor resolver, keep
the shadow path byte-identical on Drake, and B1 can land now. My recommendation is option D below: decouple,
choose the 60-minute G6 method now from non-FRESH evidence, and leave the 2026-11-24 run exactly as signed. On
your conductor concern: it is right about level, but it does not make the comparison unfair. Truth and every
candidate use the same Drake model, so the ranking is internally consistent for a Drake-75 °C line. Whether
that ranking carries over to the real conductor is a separate, open question. Near-ties (wind versus cooling)
can flip, and two of the three fitted candidates (`ml_cooling_corrected`, `reference_ml_refit_24h`) would need
refitting under a new conductor. Both points can be tested now on the ABLATION split, which the protocol allows.

---

## 1. The candidates, exactly as the protocol names them

| Name (as in v3) | What it is | Fitted artifact | Source |
|---|---|---|---|
| `ml_wind_corrected` | GFS forecast wind corrected in u/v space, then IEEE 738. **Provisional default** | yes, per city | v3 `:159-160`, `:47`; audit `:1912-1931` |
| `ml_cooling_corrected` | GFS forecast's convective term corrected (`log_ratio` target), pushed through `q_conv_override` | yes, per city | experiment `:45-47`; runbook `:107-110` |
| `reference_ml_refit_24h` | MLP on lagged ampacity plus weather covariates, 24 h target shift | yes, per city | experiment `:48-52`; runbook `:84-85` |
| `raw_forecast` (baseline) | GFS forecast weather through IEEE 738, uncorrected | none | experiment `:41-42` |
| `persistence_24h` (baseline) | live: previous cycle's `raw_forecast` nearest the decision time; dev record: truth 24 h earlier | none | v3 `:390-398` (V3) |

The per-city set in v3 is these five × four cities, with 12 frozen artifacts (3 fitted methods × 4 cities), hashed
in `confirmation_protocol_v3_per_city.md:868-885`. The legacy 1-hour arm and the oracle are not candidates
(experiment `:53-56`, `:356-387`).

**What production can serve today:** none of the five. `ampacity_forecast.FORECAST_METHODS` is `("naive",
"ewm", "ml")` (`backend/ampacity_forecast.py:58`). The shadow pipeline is never called from `dlr_pipeline.py`
(audit `:2102-2108`; a grep of `backend/*.py` for `forecast_shadow` outside the shadow modules and tests finds
no production caller). `raw_forecast` and `persistence_24h` need no artifact, but they still need a runtime
forecast fetch and its fallback, which the audit lists as unbuilt (audit `:1274-1279`, `:1442-1499`). The
production-pipeline workstream also scopes re-evaluating shadow candidates out (`.planning/workstreams/production-pipeline/REQUIREMENTS.md:152`).

## 2. What is already known without touching FRESH data

The three data bases are defined in `forecast_correction_followup_audit.md:45-49`. **ABLATION** is rows before
2026-03-17: train up to 2025-09-01T18Z, validation 2025-09-02 to 2026-03-16 (runbook `:96-100`). **TEST** is
2026-03-17 to 2026-09-29, the frozen held-out split, read once in Phase 3. **FRESH** is rows after 2026-09-29.

**Corridor-era held-out test (read once; train-only corridor fits; corridor = min of two cities).**
`ml_cooling_corrected` had the lowest MAE at both corridors. Its margin over persistence was +24.9 A
[18.8, 30.8] at AUSTIN_CORPUS_CHRISTI and +30.7 A [22.3, 39.1] at MIDLAND_EL_PASO (experiment `:206-246`,
`:285-287`). Those numbers come with three qualifiers:
- Against `raw_forecast`, which is the axis that isolates the correction, the margin is 15.1 A and 30.3 A (experiment `:614-636`).
- It is "lowest observed MAE, not an established winner". Against `reference_ml_refit_24h` at Midland the margin is 3.3 A [-2.7, 9.1] (experiment `:517-525`).
- The intervals are i.i.d. and optimistic at Midland under block bootstrap (experiment `:544-566`).

**ABLATION replication (train-only fits, 781 rows/corridor, decision-time-clean).** This is the development
evidence the owner's provisional choice rests on (audit `:1938-1964`):
- Austin corridor MAE: raw 111.44, wind 112.57, cooling 107.04, reference 128.20, persistence 156.34 A.
- Midland corridor MAE: raw 152.57, wind 126.52, cooling 132.24, reference 135.55, persistence 161.09 A.
- Wind minus cooling: +5.53 A [-1.60, 12.60] (Austin) and -5.72 A [-12.76, 1.31] (Midland). **Neither is distinguishable from zero** (audit `:1843-1853`).
- Calibrated retained capacity is mixed by corridor, with no interval on the difference (audit `:1072-1103`).
- The owner chose `ml_wind_corrected` on 2026-10-05 as an engineering tie-break, "never a claim of statistical superiority" (audit `:1912-1921`).

**Per-city results.** There are **no per-city accuracy results for any shadow candidate**:
- The 12 per-city artifacts are fit on train + validation, so the validation split is in-sample for them. "Nothing in this repository scores them on the test split" (runbook `:123-129`; v3 `:229-231`, `:806`).
- The scorer's validation on test-split dates used stub models, not the artifacts (`.planning/workstreams/ml-modeling/quick/261013-285-plan-the-per-city-shadow-log-scorer/261013-285-SUMMARY.md:238-246`).
- The 2026-10-13 per-city retrain results are for the separate 60-minute C9 forecaster: all four cities NOT MET against naive (`docs/data-science/PROJECT-STATUS.md:53-57`).

**Limits that carry over to every number above:**
- The numbers are corridor `min()` values, not per-city values.
- Truth is ERA5 reanalysis, "never sensor-validated" (audit `:1227-1233`).
- There is one NWP model (`gfs_seamless`) and **one conductor (795 Drake ACSR)**. "Nothing in this record generalizes to … a different conductor" (experiment `:423-431`; audit `:1239-1245`).
- About 781–786 rows per corridor. Resolving a 5 A margin needs about 1,575 rows (audit `:1870-1881`).

**Production's own 60-minute evidence (non-FRESH window 2026-09-15 to 09-28).** Naive had lower MAE than `ml` in
all four cities: 62.3/62.9/80.3/117.3 A against 104.1/86.4/94.2/126.7 A. The `ml` band shows a positive bias of
+42 to +88 A, consistent with B2 but not proven to come from it (`real_data_validation.md:410-415`, `:667-695`).

## 3. Options for deciding by about 2026-11-01

| Option | Dates | Protocol impact (rules kept / broken) | Evidence used | Main risks |
|---|---|---|---|---|
| **(a) Choose the day-ahead method now from dev/test evidence; 11-24 stays the confirmation** | choice now; freeze 11-01; run 11-24 as signed | Keeps everything. Nothing is amended, because v3 already names `ml_wind_corrected` the default unless 11-24 says otherwise (v3 `:47`). | ABLATION + corridor test (sec. 2) | The choice is a tie-break, not a win (audit `:1918-1921`). **Unblocks nothing by itself**: the shadow still shares the conductor, and production cannot serve a day-ahead method anyway |
| **(b) Signed amendment v4: earlier evaluation** | e.g. freeze at signing (~10-23); cutoff **2026-10-25T00Z**; instant **2026-11-01T00Z** | Changes decision 5 (v3 `:595-611`). Keeps anti-peeking and one-shot **only if v4 is signed before anyone looks at a FRESH outcome**. The reason must be stated as schedule, not results. Requires changing a frozen evaluation module: the reconstruction fetch window is hard-pinned to 2026-09-28..11-16 and any other window is refused (`backend/forecast_shadow_confirm.py:186-191`; `backend/forecast_shadow_eval_core.py:65-71`). The instant and cutoff can already be passed with `--override-reason` (`forecast_shadow_confirm.py:784-786`). | FRESH (reduced) | **Rows:** headline frames 2026-09-30T00Z..10-24T18Z = 25 days × 4 = **100/city, against 192** (v3 `:295`). Live logs about **44/city, against ~130**. **Power:** interval half-widths about 1.39× wider (√(192/100)). Rough per-city paired-MAE half-width ~20 A (×1.3 dependence: ~26 A; with the 9-test Holm z: ~36 A), against ~14/18/26 A at 192 rows, scaled as in v3 `:302-310`. Almost every comparison would read "indicated, not resolved". Code change to frozen tooling under deadline. Fetching to 11-16 on 11-01 likely fails (**UNVERIFIED**) |
| (b′) v4 with a verified shorter truth-revision margin | cutoff 10-29T00Z, instant 10-31T00Z, only if a truth-vs-truth re-fetch-and-diff shows archive values stable after 2 days | As (b). v2 already allows a verified figure to replace the 1-week margin (audit `:2042-2048`) | FRESH truth only, for the diff | 116 rows/city (29 × 4). The diff must touch truth only, never predictions |
| **(c) Ship current `ml` with B2 fixed as provisional, switch later** | retrain now; go live early Nov | **No protocol impact**: C9 is outside v3 (v3 `:159-164`). Training years 2023-2025 are non-FRESH (`real_data_validation.md:121-124`) | C9 held-out results; Sept window | Ships the method the evidence ranks below naive in all 4 cities (sec. 2). The retrain depends on the conductor: `dlr_amps` is computed through `city_point` (`backend/forecast_training.py:200-226`), so a B2 retrain under Drake has to be redone after B1 |
| **(d) Decouple production from the shadow evaluation** *(recommended; detail in sec. 6)* | B1/B2 now; shadow untouched to 11-24 | **Keeps every rule, no amendment needed.** Production gets its own conductor resolver, and the shadow path stays byte-identical on Drake. Record it in the v3 change log as "no change to what is measured". The 60-minute G6 method is chosen from non-FRESH evidence: naive (an OD-3 reversal) or `ml` with B2 fixed | Sept validation; C9 results | Must prove shadow outputs bit-identical (golden test). Production go-live publishes ratings for FRESH-window dates (sec. 6, step 4) |
| (e) Score the 12 frozen per-city artifacts on the TEST split now | anytime before 11-01 | **Not FRESH, so no v3 anti-peeking rule is broken.** But it departs from "unscored by design" (v3 `:806`; runbook `:127-129`). Phase 4 called re-scoring the test set "a second selection-on-test-set decision" (`.planning/workstreams/ml-modeling/phases/04-*/04-CONTEXT.md:13-15`). Needs a written owner decision **before** it runs; it cannot be a confirmation | ~788 exact-lead rows/city, out of sample for the artifacts (fit < 2026-03-17, runbook `:116-119`) | The team already saw the corridor test result, so this is partly "already seen". Best non-FRESH per-city evidence available, but the tooling would need a development-window provider (exists for tests, `261013-285-SUMMARY.md:246`) |
| (f) Pre-register a conductor follow-up now | addendum signed before 11-24 | Keeps one-shot. Without pre-registration, a post-11-24 re-score of FRESH under a new conductor would be a "re-parameterised" second read (v3 `:173-175`). v3 already anticipates a labelled, separate descriptive follow-up (v3 `:607-608`) | FRESH, after the instant only | None if labelled descriptive and never used to overturn the headline |

**Option (b) in plain terms:** v4 halves the sample of the headline. It requires editing frozen evaluation code
under deadline, and it answers a question (which day-ahead method) that production go-live does not need
answered. It is legitimate only if signed now, before any FRESH outcome is seen. That is still possible: the
record shows no FRESH outcome has been read (v3 `:24-28`; `PROJECT-STATUS.md:68`).

## 4. Mechanical health check of the per-city shadow logs (2026-10-21)

Source: `origin/shadow-collection-data` at `35c7e03` (2026-10-21T17:05Z). Counts only.

| City | v3 rows | `gfs_seamless` rows | distinct `valid_time` | first / last `valid_time` |
|---|---|---|---|---|
| AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO (each) | 48 | 43 | 34 | 2026-10-14T00Z / 2026-10-22T06Z |

Candidate status in the 43 post-fix rows per city:
- `raw_forecast`, `ml_wind_corrected`, `ml_cooling_corrected`, `reference_ml_refit_24h`: 41–43 `ok`, with 0–2 `unavailable` and one `failed` (MIDLAND cooling).
- **`persistence_24h`: `unavailable` in 43 of 43 rows in every city**, reason "no prior entry within tolerance … (cold start, or a gap …)".

**Likely cause (inference from reading the workflow; not reproduced).** The job checks out `main`
(`.github/workflows/shadow_collect.yml:43`), which tracks no prediction logs (`git ls-files
data/shadow/predictions` is empty). It appends to the data branch only after collecting (`:84-136`).
`Persistence24hShadowMethod` looks for a prior entry in the runner's local log (`backend/forecast_shadow_pipeline.py:1183`,
90-minute tolerance at `:1072`), so every run is a cold start.

**Effect.** The live-log check's three persistence tests in the 9-test family (decision 2) will have no rows.
The headline port recomputes persistence from reconstructed frames (`backend/forecast_shadow_confirm.py:27-32`),
so the headline is unaffected. This is a collection fault for the ml-modeling owners to decide on. The
production workstream treats `shadow_collect.yml` as frozen (`.planning/workstreams/production-pipeline/ROADMAP.md:26-27`).

## 5. Question 2: conductor change (B1) and the model choice

### 5.1 Is the concern right?

**Level: yes.** Everything is Drake 795 at 75 °C and 900 m:
- The shadow collector: `city_point.city_point` builds the conductor from `config.conductor_kwargs_for` (`backend/city_point.py:59-60`; `backend/config.py:140-161`). The collector rates through it (`backend/forecast_shadow_pipeline.py:656`, `:1644`, `:1822`).
- The fits (runbook `:81-85`).
- The headline scorer, which recomputes truth, `raw_forecast` and persistence from weather with `city_point` on the day it runs (`forecast_shadow_confirm.py:27-32`, `:240-253`).

The research note's estimates, at 40 °C and 0.61 m/s, put the plausible real conductors well above Drake-75:
Drake-75 707 A, Drake-100 1008 A, Falcon-90 about 1330–1550 A, Suwannee-200 1858 A (`.planning/workstreams/production-pipeline/phases/03-real-data-validation/03-05-CONDUCTOR-RESEARCH.md:85-90`, `:106-107`).

**Fairness: the comparison is still internally fair.** Truth and predictions use the same physics and the same
conductor, so no candidate is favoured by the wrong conductor. What the ranking describes is a Drake-75 line,
not the real one. Fairness is intact; transfer to the real conductor is open.

**A sharper version of the collision (inference from the code).** Changing the shared config before 11-24
would not just move all candidates together. It would mix conductors inside one evaluation:
- The headline would recompute truth and `raw_forecast` under the new conductor.
- Each `ml_cooling_corrected` artifact carries its fit-time Drake conductor. It computes its features and corrected convective term with that conductor (`backend/forecast_correction_models.py:435-450`, `:553-561`), then pushes the term into the heat balance of whatever conductor the caller passes (`:589-603`).
- `reference_ml_refit_24h` would receive new-conductor ampacity lags into a Drake-trained MLP (`backend/forecast_shadow_pipeline.py:1595-1644`).
- The live logs' `ampacity_amps` were computed at collection time under Drake.

That is why any decoupling must keep the shadow path byte-identical, not merely "close".

### 5.2 What actually changes with the conductor

The heat balance is I = √((Q_conv + Q_rad − Q_solar) / R(T_max)) (`backend/thermal_model.py:253-258`).
- Forced convection scales with (T_max − T_a) and Re = D·V·ρ/μ (`:170`, `:181-189`).
- Natural convection scales with D^0.75 (T_max − T_a)^1.25 (`:124`).
- Radiation scales with D·ε·(T_max⁴ − T_a⁴) (`:244`).
- Solar gain scales with D (`:250`).

The physics-only calculation below uses the repo's own code, the same catalogue diameters and resistances as
`03-05-conductor_sensitivity.py:12`, and the Austin bearing. The script is in my scratchpad and is not committed.
These are **estimates**: the repo's linear resistance model at 150–200 °C is approximate for ACSS (**UNVERIFIED**).

| Conductor | Case (T_a, V⊥, GHI) | I (A) | dI/dV (A per m/s) | dI/dV (% per m/s) | dI/dT_a (% per °C) | Radiation share of cooling |
|---|---|---|---|---|---|---|
| Drake 75 °C (current) | 35 °C, 0.5 m/s, 900 W/m² | 816 | 357 | 43.8 | −1.44 | 0.31 |
| Drake 100 °C | same | 1075 | 413 | 38.4 | −0.77 | 0.34 |
| Falcon 90 °C | same | 1499 | 513 | 34.2 | −0.97 | 0.37 |
| Suwannee 150 °C | same | 1595 | 537 | 33.6 | −0.37 | 0.38 |
| Suwannee 200 °C | same | 1914 | 583 | 30.5 | −0.22 | 0.43 |
| Drake 75 °C (current) | 20 °C, 3 m/s, 600 W/m² | 1531 | 138 | 9.0 | −0.89 | 0.14 |
| Suwannee 200 °C | same | 2824 | 226 | 8.0 | −0.23 | 0.21 |

What this shows:
- **Level rises 1.3–2.3×.** Every amp-denominated error and margin, and the fixed X = 5 A ship threshold (v3 `:47`), changes meaning. The same relative skill gives bigger amp margins, so 5 A becomes easier to clear.
- **The error mix shifts toward wind.** Per-degree temperature sensitivity falls about 2× (Drake-100) to about 6× (Suwannee-200), relative to level. Relative wind sensitivity falls only 10–30%. Radiation, which no wind error touches, takes a larger share.
- **The natural/forced crossover moves**, because both terms change with T_max and D. The audit's 0.1428 m/s crossover was for Drake-75 (experiment `:686-687`).

### 5.3 Is the ranking likely to be conductor-invariant? (inference)

| Class | Candidates | Refit under a new conductor? | Likely ranking behaviour |
|---|---|---|---|
| Forecast weather, recompute through physics | `raw_forecast`, `ml_wind_corrected`, `persistence_24h` | **No.** The wind model's features are forecast/anchor u/v, temperature, solar and hour, and it predicts truth u/v (`backend/forecast_correction_models.py:114-162`, `:225-232`). None of that involves the conductor. Only recomputation is needed. | Errors are re-weighted, not re-learned. A wind-only correction keeps most of its edge, because wind becomes relatively more important. Persistence's day-ago temperature/diurnal alignment matters less as temperature sensitivity drops. Large gaps (raw vs persistence at Austin, ~45 A dev) are probably stable. Small gaps are not guaranteed |
| Correction of a physics term | `ml_cooling_corrected` | **Yes.** The artifact embeds the conductor. Its target log(Q_true/Q_fcst) is only partly scale-free: the (T_max − T_a) ratio, the D-dependent Reynolds regime and the natural-convection floor all move (`forecast_correction_models.py:487-515`) | Part of what it learned corrects temperature-driven convection error, which shrinks at high T_max. Its edge over wind could shrink or grow. Its rank relative to wind is **not** expected to be invariant |
| Direct ampacity forecast | `reference_ml_refit_24h` | **Yes.** The target and lag features are conductor-specific ampacity (runbook `:84-85`) | Errors scale roughly with level, but the learned mapping does not transfer. A refit is a new model |

**Bottom line.** The wind-versus-cooling question is already unresolved on Drake (CIs cross zero, audit
`:1843-1846`). A conductor change cannot make it "less resolved". It can flip point orders, though, and
"consistent in 3 of 4 cities" (decision 8) is a point-order rule.

### 5.4 A ranking-invariance test that never touches FRESH data

**Allowed splits:**
- **ABLATION** (before 2026-03-17) is allowed without qualification. It "may support … relative-ordering findings" (audit `:45-49`). Use train (to 2025-09-01T18Z) for fitting and validation (2025-09-02..2026-03-16) for scoring.
- **TEST** (2026-03-17..09-29) is not FRESH, but using it needs a written owner decision first (option (e), Phase 4 boundary).
- **FRESH** (after 2026-09-29) is forbidden before the instant. Never open `data/experiment/anchored_pair_frame_*_2026-09-30_*` (`.planning/NEXT-SESSION-PROMPT.md:14`). The local cached frames `..._2024-01-20_2026-09-29_...` (runbook `:74-76`) contain TEST rows, so filter them in code to before 2026-03-17 and assert it, as `assert_no_test_leak` does (runbook `:116-118`).

**Design** (pre-register the criteria before running):
1. Conductor set K: Drake-75 (control), Drake-100, Falcon-90, Suwannee-150, Suwannee-200. Hold bearing, emissivity and elevation fixed so only the conductor moves. Add one variant at the measured Austin elevation of 163 m (research note `:117-124`).
2. For each city and each K, recompute truth, `raw_forecast` and persistence (truth 24 h earlier) from the same cached weather.
3. Fit `ml_wind_corrected` once on train (it does not depend on the conductor). Refit `ml_cooling_corrected` and `reference_ml_refit_24h` on train under each K, using the frozen configurations (`WIND_CONFIGURATION`, `COOLING_CONFIGURATION`, MLP; runbook `:107-111`). Never write to `data/shadow/models/` and never touch the 12 frozen artifacts.
4. Score on the ~784 validation rows per city. Report:
   - MAE, RMSE and bias per candidate.
   - The same quantities divided by mean truth ampacity.
   - The rank order and its Kendall τ against Drake-75.
   - Paired block-bootstrap differences per pair, at block lengths 1/4/8/28 as in the audit.
   - Each correction's margin over `raw_forecast` in A and in %.
5. Pre-stated criterion, for example: "invariant" if no pair whose Drake-75 interval excludes zero changes sign under any K, no pair becomes distinguishable in the opposite direction, and the 3-of-4-cities point order of the default (`ml_wind_corrected`) against each alternative is unchanged.

**What it can and cannot say.** It is a relative-ordering finding on already-seen data, never a confirmation
(audit `:1199-1213`). The configurations were selected on Drake validation data, so their selection optimism
carries over unchanged (runbook `:130-132`).

### 5.5 Timing: choose now and swap the conductor later?

- **The method can be chosen without waiting for the conductor.** Later you refit `ml_cooling_corrected` and `reference_ml_refit_24h`, recompute `raw_forecast`, persistence and `ml_wind_corrected`, and refit nothing for wind. This holds if the ABLATION test in 5.4 shows invariance across the bracketing conductors. That does not need Power Systems' answer, because the set brackets the plausible range.
- **If the test shows non-invariance between the default and an alternative**, the 2026-11-24 Drake result will not transfer by itself. Re-scoring FRESH under the real conductor after 11-24 would be a second, re-parameterised read (v3 `:173-175`) unless it is pre-registered now as a labelled descriptive follow-up (option (f)).
- **Either way**, the 2026-11-24 headline must be scored on the Drake conductor it was frozen with. Under option (d) that happens automatically.

## 6. Recommended sequence (option d), with dates

This is my recommendation; the decision is yours. Item 6 depends on Phases 4–6 of production-pipeline, whose
durations I have not checked (**UNVERIFIED**).

1. **By 2026-10-23, owner decisions:**
   - Pick the interim G6 method (it runs until the 2026-11-24 winner replaces `ml`): naive (OD-3 reversal, supported by `real_data_validation.md:685-695` and `PROJECT-STATUS.md:55-56`) or `ml` with B2 fixed (`real_data_validation.md:679-683`, option B or C).
   - Decide the fallback-policy half of B1 (Finding 1, `real_data_validation.md:649-665`), which does not depend on Power Systems.
2. **By about 2026-10-27, decouple** (ml-modeling owners agree and record it in the v3 change log):
   - Add a production-only conductor resolver and point the production callers at it: `city_rating` (`backend/city_rating.py:377`), `forecast_training` (`:200-226`), `anomaly_training` (`:566`) and `real_data_validation`.
   - Leave `config.DEFAULT_CONDUCTOR_CONFIG_KWARGS`, `city_point.city_point` and every shadow module unchanged.
   - Prove it with a golden test: shadow collector, fit and both scorers give byte-identical outputs before and after, using development fixtures only.
3. **When Power Systems answers B1 (target 2026-10-27):** set the production conductor, MOT, elevation and azimuth. If there is no answer, the owner decides whether to go live on a labelled provisional choice (for example Drake at Austin Energy's stated 100 °C, research note `:9`, `:52-57`) or wait.
4. **Before go-live, a written ruling (owner + ml-modeling):** production backfill and live ratings for FRESH-window dates are not shadow outcomes, provided nothing joins them to shadow predictions.
   - This matters because production phase 3 used 2026-09-29 as its own cutoff (`real_data_validation.md:26-27`), and OD-6 makes the history public (`.planning/workstreams/production-pipeline/STATE.md:145`).
   - B3 is not blocking (`real_data_validation.md:884`). Option C, seeding a short history at go-live (`:736-738`), keeps any backfill minimal.
5. **2026-10-28 to 10-31:** retrain the per-city C9 forecast (if `ml` is kept) and the anomaly models under the production conductor, on 2023-2025 history (non-FRESH). Redo B4 on the new anomaly model. Decide B5. Re-run the Phase 3 validation on the same 2026-09-08..09-28 window. New go/no-go about 2026-10-31.
6. **2026-11-01:** shadow freeze as signed, unchanged. **About 2026-11-02 to 11-06:** production Phases 4–6 and go-live. Check the Actions quota first: hourly live runs plus shadow could exhaust minutes and stop Shadow Collection before 11-24 (`.planning/workstreams/production-pipeline/STATE.md:65`).
7. **In parallel, before 2026-11-17:**
   - Run the ABLATION conductor-invariance test (5.4).
   - Sign a short addendum before any FRESH read that pre-registers the conductor follow-up (option (f)). If wanted, restate the ship threshold X in relative terms so it survives a conductor change. Changing X is a protocol change, legitimate only before outcomes.
   - Optionally fix the persistence cold-start fault (sec. 4).
8. **2026-11-24:** the one-shot evaluation as signed, on Drake. Afterwards, if a day-ahead product is wanted, wire the chosen method into production, refit (cooling or reference only) under the production conductor, and run the pre-registered follow-up.

## 7. Open questions

**For you (owner):**
1. Which interim G6 method runs from go-live until the 2026-11-24 winner is built in? The shadow winner is intended to replace `ml` (Phase 3 context `:10-15`), but it needs a runtime forecast fetch, an hourly series and a band before it can feed G6.
2. For G6: naive (reverse OD-3) or `ml` with B2 fixed?
3. Do you accept decoupling (sec. 6, step 2) instead of a v4 date change?
4. Should the ship threshold X = 5 A be restated in relative terms before any outcome?
5. ~~Do you consider v3 fully signed?~~ **Resolved 2026-10-21: the owner confirms v3 is fully signed.** (`PROJECT-STATUS.md:71-72` still says the block is blank and should be updated.)
6. If B1 is not answered by about 10-27: go live on a labelled provisional conductor, or wait?

**For the ml-modeling owners:**
1. Will you record the production-only conductor resolver as a no-measurement-change note in v3, and own the golden test?
2. Do you agree that production backfill and live ratings for FRESH dates are not shadow outcomes (sec. 6, step 4)?
3. The `persistence_24h` permanent cold start (sec. 4): fix before 11-17, or accept zero live persistence rows? Is the workflow-checkout cause right?
4. Option (e) (TEST-split scoring of the frozen artifacts): acceptable as pre-11-24 descriptive evidence, or ruled out by the Phase 4 principle?
5. Will you pre-register the conductor follow-up (option (f)) and the 5.4 invariance criteria?
6. Is the 2026-11-17 cutoff still needed? The truth-vs-truth revision check (NEXT-SESSION-PROMPT `:33`) has not been shown to have run (v3 `:659-661`).

**For Power Systems (from the research note `:135-142`, plus the model's needs):**
1. Which 345 kV line or circuit does each city point represent?
2. For each: conductor type and size, maximum operating temperature (normal and emergency), elevation and true azimuth.
3. Are 2300/3650/5000 A per circuit or per corridor, normal or emergency? Is 3650 A a midpoint?
4. Do the TSPs' static-rating assumptions (ambient, wind, ε/α) match what the model should use?
5. Is terminal equipment (3200 A legacy, 5000 A new) the binding limit on any of these lines?

## Items I could not verify

- Whether `anchored_pair_frame` with a fetch end of 2026-11-16 fails when run on 2026-11-01. Not run; only inferred.
- The cause of the `persistence_24h` cold start. Read from the workflow, not reproduced.
- ACSS resistance at 150–200 °C in the repo's linear model, and therefore the Suwannee rows in sec. 5.2.
- The durations of production-pipeline Phases 4–6 and the real Actions quota.
- That no shadow module imports a production module that would be switched to the new conductor resolver. A grep found no such import; the golden test in step 2 is the real check.
