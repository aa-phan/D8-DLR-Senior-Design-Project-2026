# Input Provenance Ledger (Phase 1, draft)

**Opened:** 2026-10-28. **Covers:** PROV-01 (this pass), plus the source trail for PROV-02, PROV-03 and PROV-04.
**Method:** every claim cites a file and line, or a git commit (`git show <hash>`). Line numbers are from
branch `claude/prov-01-task-plan-dcac75` at `82c0332`. Anything with no recoverable source is marked **NO SOURCE FOUND**
rather than inferred.

**Status key:** CONFIRMED = a named party confirmed it for the real lines. PROVISIONAL = supplied by a named party, stated
as an assumption. UNKNOWN = no basis recoverable from the repo.

---

## 1. `max_temp_c` (PROV-01)

### 1.1 Basis (reported by the owner 2026-10-28; supersedes the two earlier same-day drafts)

| Limit | Conductor temperature | Rating type | Status |
|---|---|---|---|
| Normal rating | **75 °C** | Normal | CONFIRMED by Power Systems, as reported by the owner |
| Emergency rating | **100 °C** | Emergency | CONFIRMED by Power Systems, as reported by the owner |

**Evidence caveat (read before citing).** The confirmation is recorded on the owner's statement of 2026-10-28. The repo holds
no written confirmation, no named Power Systems counterpart, and no date for when Power Systems confirmed it. Until one
is attached, cite this as "confirmed by Power Systems per the project owner, 2026-10-28", not as a document. Section 5 asks
for the missing counterpart, date and medium so PROV-01's "documented source" can point at something retrievable.

Whether the two limits apply to every city's line, or only generally, was not stated; the ledger treats them as applying to
all four cities.

### 1.2 What the code does today

| Item | Value |
|---|---|
| Value in code | **75.0 °C** (`backend/config.py:145`, `backend/thermal_model.py:74`) = the **normal** limit |
| Role | Fixed conductor temperature `T_c = conductor.T_max` in `ieee738_ampacity` (`thermal_model.py:120,161,234`); returns the current that *reaches* this temperature, not a solved operating temperature (`specs/C5-thermal-model.md:45`) |
| So the live rating is | A **normal-rating** (75 °C) ampacity. No code path computes an emergency (100 °C) rating |
| First appears | 2026-08-24, commit `9680772` (Aaron Phan), as the `max_temp_c: float = 75.0` default in `dlr_pipeline.py`; carried into `thermal_model.py` by `ffbea4f` (2026-08-31). Neither commit message records a reason for 75 °C |
| Written source at the time | None in the repo (commit messages, `citations.md`, C5 spec, `ACKNOWLEDGEMENTS.md`, course reports). The Power Systems confirmation in 1.1 is the first source |
| Status | CONFIRMED (normal limit) per 1.1; the repo's labeling of it is still missing |

Result: **75 °C in code matches the confirmed normal limit, so no value change is needed for `max_temp_c`.** The gap is
labeling, plus the design question in 1.6.

### 1.3 Every occurrence of a conductor-temperature value

| Location | Says | Meaning against 1.1 |
|---|---|---|
| `backend/config.py:145` | `"max_temp_c": 75.0` | Correct value (normal); no label says "normal" |
| `backend/thermal_model.py:74` | `max_temp_c: float = 75.0  # maximum allowable conductor temp (°C)` | Correct value; "maximum allowable" is misleading, since 75 °C is the normal limit and 100 °C is the higher emergency limit |
| `docs/data-science/specs/C5-thermal-model.md:11` | "max temp 75°C" | Correct value; needs "normal rating limit". Its elevation (300 m) differs from the config default (900 m) |
| `README.md:103` | "ERCOT emergency rating limit (often 75–100°C for ACSR)" | **Wrong label.** The value in use (75 °C) is the normal limit, and the sentence gives a range and names no document. Needs rewriting |
| `docs/data-science/decisions/real_data_validation.md:11, 819` | "Drake ACSR conductor model with `max_temp_c` 75" | Correct value; add "normal limit" |
| `docs/data-science/decisions/real_data_validation.md:786-797` | Option B asks Power Systems for "the maximum conductor temperature (PROV-01)" | Now answered (75 normal / 100 emergency) |
| `docs/data-science/PRD.md:160` | "40°C ambient, 0.61 m/s perpendicular wind, 100°C conductor limit" | IEEE 738 §4.6.1 worked example. It coincides with the emergency limit but is a separate fact; keep the two distinct |
| `backend/tests/thermal_model_test.py:58, 61, 162` | `max_temp_c=100.0`; comment at :58 says the example's limit is 100 °C, not the default | Worked-example validation. The comment stays true; add that 100 °C is also the confirmed emergency limit |
| `docs/data-science/citations.md:47` | Worked example is IEEE Std 738-2023 §4.6.1, 795 kcmil 26/7 Drake ACSR, expected 1025 A | Source of the worked example |
| `backend/tests/supabase_load_backfill_test.py:552-553` | Asserts `"max_temp_c": 75.0,` is in `config.py`, then rewrites it to 100.0 | Config-fingerprint drift test; unaffected, since 75 stays |
| `backend/tests/rating_identity_test.py:144, 158` | Uses 80.0 | Arbitrary test value |
| `docs/data-science/DEVELOPMENT-TRACKS.md:146`, `PROJECT-STATUS.md:128` | "no documented source; project reports state 100 °C" | **Outdated.** Restate as 75 °C normal / 100 °C emergency, confirmed by Power Systems. The course reports (`Project Definition.md`, `System Design Report.md`, `Prior Art Report.md`) themselves state no conductor limit; the 100 °C in `PRD.md:160` is the worked example |

### 1.4 Where each number appears externally

- **100 °C:** IEEE Std 738-2023 §4.6.1 worked example (Drake 795 kcmil 26/7 ACSR, 40 °C ambient, 0.61 m/s wind; published
  answer 1025 A; `citations.md:47`, `thermal_model_test.py:58`). It is also the confirmed emergency limit (1.1).
- **75 °C:** no external document in the repo; confirmed as the normal limit per 1.1.
- Neither temperature is tied to the bundle ranges in section 2 (see 1.6).

### 1.5 Consequences

- Computed ampacity scales with the square root of the heat balance, so an emergency (100 °C) ampacity is higher than the
  normal (75 °C) one. Size measured in Phase 2 (PROV-05).
- Because the live rating is the normal one, the current DLR output is the more conservative of the two limits. Switching
  any output to 100 °C would present an emergency-basis number and must be labeled that way.
- `DEFAULT_CONDUCTOR_CONFIG_KWARGS` is fingerprinted (`backend/rating_identity.py`, `FINGERPRINTED_CONFIG_NAMES`). Adding a
  key or changing a value in that dict changes the stored config identity of every rating row; a comment-only edit does not.

### 1.6 Decisions and gaps this leaves

1. **Which basis do the static ratings and bounds use?** Section 2's bundle ranges still have no stated normal/emergency
   basis or conductor temperature. The confirmation in 1.1 covers the 75/100 limits only; it does not say whether the
   bundle ranges are normal or emergency ratings. Left UNKNOWN until Power Systems answers.
2. **Which basis does the pipeline publish?** Today only the normal (75 °C) rating is computed. If the PSS/E hand-off needs
   an emergency (100 °C) value, that is new work for PSSE-01/PSSE-02 (a rating-basis field), not a documentation change.
3. **Written confirmation.** Counterpart name, date, and medium for the 75/100 confirmation are not recorded (section 5).

### 1.7 Labeling to use until Phase 3

"75 °C: normal conductor temperature limit; 100 °C: emergency limit; confirmed by Power Systems (per project owner,
2026-10-28; written confirmation to be attached)." The code's `max_temp_c` is the normal limit.

---

## 2. `STATIC_RATINGS` and `RATING_BOUNDS_BY_LOCATION` (PROV-02 source trail)

### 2.1 Arithmetic (verified)

Per-conductor value = bundle value ÷ `SUBCONDUCTORS_PER_PHASE`. Static rating = bundle range average ÷ count.

| City | Bundle range (A) | Count | Bundle average | `STATIC_RATINGS` (A) | `RATING_BOUNDS_BY_LOCATION` (A) |
|---|---|---|---|---|---|
| AUSTIN | 2300-5000 | 2 | 3650 | 1825 | 1150-2500 |
| CORPUS_CHRISTI | 1600-4400 | 2 | 3000 | 1500 | 800-2200 |
| MIDLAND | 2500-5000 | 2 | 3750 | 1875 | 1250-2500 |
| EL_PASO | 640-2000 | 1 | 1320 | 1320 | 640-2000 |

Code: `STATIC_RATINGS` `backend/config.py:41-51`; `RATING_BOUNDS_BY_LOCATION` `config.py:97-116`.

### 2.2 Sources, in order of authority

| # | Source | What it supports | Date / author |
|---|---|---|---|
| 1 | `backend/config.py:42-46` (comment inside `STATIC_RATINGS`, line 41) | Bundle ranges "owner-supplied 2026-10-13"; averages 3650/3750/3000/1320 A; "unverified for any specific line segment" | Commit `cd4c365`, 2026-10-13, Aaron Phan |
| 2 | `backend/config.py:98-100` (comment) | Same ranges described as "the Power Systems team's 345 kV BUNDLE ranges"; divided by `SUBCONDUCTORS_PER_PHASE` | Commit `a5004e5`, 2026-10-13, Aaron Phan |
| 3 | `docs/data-science/decisions/point_scope.md:12` | Static values changed 2026-10-13 "(owner decision)"; before: 1900, 3000, 1800, 1450 | Commit `cd4c365` |
| 4 | `docs/data-science/decisions/real_data_validation.md:568-569, 786-787` | Restates the derivation as "owner-supplied 345 kV bundle average ... divided by 2 subconductors"; finding 9 notes computed rating rests on different assumptions | 2026-10 |
| 5 | `docs/Project Definition.md:79-84` | **Previous** source: "Worst Case Static Limit (I) [A]" Austin 800-3000, Corpus Christi 1000-5000, Midland 600-3000, El Paso 600-2300 | Course deliverable |
| 6 | `ACKNOWLEDGEMENTS.md:101-105` and `docs/data-science/decisions/geographic_scope.md:45` | Earlier midpoints came from source 5 by mechanical derivation, "not independently researched citations" | Session 2026-09-02 |
| 7 | `config.py:98-100`, source 5 | Bounds before 2026-10-13: 800-3000, 1000-5000, 600-3000, 600-2300 (= source 5) | Diff of `a5004e5` |

### 2.3 Gaps (all UNKNOWN)

- **No primary document.** The bundle ranges exist only as a code comment and commit message. No file in the repo holds
  the original message, spreadsheet, or table from Power Systems. Source 1 says "owner-supplied"; source 2 says
  "Power Systems team's". **Which named person supplied them, in what medium, is not recorded.** Treat the supplier as
  "Power Systems sub-team via the project owner", date 2026-10-13 at the latest.
- **Normal vs. emergency, and the assumed conductor temperature: not recorded anywhere.**
- Whether the ranges are for a specific line or a regional figure: source 1 says "unverified for any specific line segment".
- The 345 kV label comes from `config.py:44,99`; `LINE_VOLTAGE_KV = 345.0` (`config.py:247`) is described there as "ERCOT West
  Texas standard backbone", which is an assumption for the other cities too.
- `docs/data-science/decisions/line_bearing_check.md` notes El Paso's 345 kV network is El Paso Electric (WECC), not ERCOT.

---

## 3. `CITY_LINE_BEARING_DEG` (PROV-03 source trail)

| City | Value (°) | Origin | Source |
|---|---|---|---|
| AUSTIN | 173.15 | Great-circle initial bearing Austin → Corpus Christi, from `CITY_COORDINATES` | below |
| CORPUS_CHRISTI | 173.15 | Same corridor bearing reused | below |
| MIDLAND | 267.54 | Great-circle initial bearing Midland → El Paso | below |
| EL_PASO | 267.54 | Same corridor bearing reused | below |

- **Origin:** The values are the bearings of the corridor between two city-center coordinates, not of any physical line.
  I recomputed them 2026-10-28 from `config.CITY_COORDINATES` (`config.py:194-199`): Austin→Corpus Christi = 173.1471°,
  Midland→El Paso = 267.5399°, matching 173.15 and 267.54 to rounding. `backend/forecast_shadow_confirm.py:29` independently
  records "bearing 173.1471 vs 173.15". The corridor pairing is `LEGACY_CORRIDOR_ENDPOINTS` (`config.py:227`).
- **Why they are in the file:** carried over when corridors were retired 2026-10-12 so wind behavior was unchanged
  (`config.py:209-215`; commit `882bc69`; `decisions/point_scope.md:14,38`).
- **Plausibility check:** `docs/data-science/decisions/line_bearing_check.md` (2026-10-13). HIFLD 345 kV segments within
  15/30/60 km of each city; concentration R is 0.21-0.46 for Austin, Corpus Christi and El Paso (no dominant axis) and 0.63
  for Midland, where the dominant axis (75°) is 13-17° from the assigned 88°. Decision: no substitution. Data source:
  HIFLD layer mirrored at `gis.elpasotexas.gov/.../source_HIFLD_Open/MapServer/7`; reproducible with
  `decisions/line_bearing_check.py`. Limits: geometry approximate, may be outdated, not tied to the rated line.
- **Status:** UNKNOWN as a measurement; documented placeholder. Not confirmed by Power Systems. `PROJECT-STATUS.md:135-139`
  and `README.md:102` already describe it as an assumption.
- **Wind direction note:** the azimuth is a line axis; 173.15 and 353.15 are the same line, so only 0-180° matters for
  perpendicular wind. 267.54 ≡ 87.54°.

---

## 4. `SUBCONDUCTORS_PER_PHASE` (PROV-04 source trail)

| City | Count | Status |
|---|---|---|
| AUSTIN | 2 | PROVISIONAL |
| CORPUS_CHRISTI | 2 | PROVISIONAL |
| MIDLAND | 2 | PROVISIONAL |
| EL_PASO | 1 | PROVISIONAL |

- **Source:** "the Power Systems sub-team's PROVISIONAL per-city subconductor-per-phase count ... explicitly a regional
  assumption, not yet confirmed for any specific line segment -- stated that way by the team supplying these numbers"
  (`backend/config.py:61-72`).
- **When and who recorded it:** commit `0de7590`, 2026-10-07, Aaron Phan (message lists Austin 2, Corpus Christi 2, Midland 2,
  El Paso 1); config comment dated 2026-10-08; `BUNDLE_CONFIG_VERSION = "v1-provisional-2026-10-08"` (`config.py:74`).
  Restated in `ACKNOWLEDGEMENTS.md:2063-2090` session notes.
- **Not recorded:** the individual at Power Systems who supplied it, and the medium. Same gap as section 2.
- **Where derived numbers appear (all must carry "provisional"):** `STATIC_RATINGS`, `RATING_BOUNDS_BY_LOCATION`
  (per-conductor values), `BUNDLE_RATING_BASIS` text (`config.py:89-93`) in shadow bundle records, `README.md:103` example
  ("1825 A per conductor"), `point_scope.md:12`, `real_data_validation.md:568`.
- **Dependency:** every per-conductor number in section 2 is a function of these counts. If a count changes, the static rating
  and bounds change with it, and `BUNDLE_CONFIG_VERSION` must be bumped (`config.py:69`).

---

## 5. Open items for the consolidated Power Systems request

1. Written confirmation of the 75 °C normal / 100 °C emergency limits: Power Systems counterpart, date, medium, and whether they apply to every city (section 1.1).
2. For each bundle range: normal / emergency / worst-case static; the conductor temperature it assumes; the named supplier and
   date (section 2).
3. Confirmed subconductor counts per line segment (section 4).
4. Real line azimuth for the segment each city represents (section 3).
5. Interface details for PSSE-01 (separate section in the request).

## 6. Corrections to other project documents (to apply in Phase 3, not edited here)

- `DEVELOPMENT-TRACKS.md:146` and `PROJECT-STATUS.md:128`: replace "no documented source; project reports state 100 °C" with
  "75 °C normal / 100 °C emergency, confirmed by Power Systems (per project owner, 2026-10-28)".
- `README.md:103`: replace "ERCOT emergency rating limit (often 75–100°C for ACSR)" with "conductor temperature limit used
  as `T_max`: 75 °C normal rating (100 °C is the emergency rating, not used by the pipeline)".
- `backend/config.py:145` and `backend/thermal_model.py:74`: keep 75.0; change the comments to "normal rating limit" and cite
  this ledger. Comment edits do not change the config fingerprint; a new key or value does.
- `specs/C5-thermal-model.md:11`: label 75 °C as the normal limit; reconcile elevation 300 m vs the config default 900 m.
- `real_data_validation.md:11, 819`: add "(normal limit)" to the 75 °C basis; no re-run needed because the value is unchanged.
- `thermal_model_test.py:58`: note that 100 °C is also the confirmed emergency limit.
- `BUNDLE_CONFIG_VERSION` is not affected by this item, since no value changes.
