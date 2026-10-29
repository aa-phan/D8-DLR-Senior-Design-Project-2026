# Ampacity Sensitivity Findings (Phase 2, PROV-05)

**Run:** 2026-10-29, `phase2/ieee_sensitivity.py` (output in `phase2/out/` ). **Status:** This note reports measurements. It does not record the freeze decision and does not yet say whether any model artifact must be
refit (see "What this does not settle").

## 1. What was measured

All ratings are per-conductor ampacity from `thermal_model.ieee738_ampacity` (one 795 kcmil Drake ACSR conductor, the
per-city config from `config.conductor_kwargs_for`, solar altitude 45° as `DLRSafetyMonitor` uses). No repo file was edited.

| Sweep | Input varied | Weather used | Output |
|---|---|---|---|
| Temperature | Conductor limit 75 / 90 / 100 °C (75 normal, 100 emergency, both confirmed by Power Systems per the owner; 90 is an intermediate point) | 100 sample hours (4 cities × 5 cases × 5 hours) | `sensitivity_temperature.csv` |
| Bearing | Line azimuth 0–175° in 5° steps, against the assigned placeholder (`CITY_LINE_BEARING_DEG`: Austin and Corpus Christi 173.15°, Midland and El Paso 267.54°), at 75 °C | Same 100 hours | `sensitivity_bearing_75C.csv` |
| Bounds and static ratings | Current G4 bounds vs the old Project Definition ranges vs subconductor count ±1, at 75 and 100 °C | Full 2025 year, 8,760 hours per city | `sensitivity_bounds_2025.csv` |

**Data.** Open-Meteo archive hourly values for 2025 at each city's coordinates (`phase2/fetch_dev_weather.py`). Sample hours were chosen by
`phase2/pick_samples.py` into five cases (hot calm, median day, breezy cool, perpendicular wind, parallel wind), five hours
per case per city, at least 14 days apart, listed in `phase2/samples_5_per_case.csv`.

**Check.** Before computing, the script reproduced the IEEE 738 worked example at 1034.8 A (published 1025 A, 0.95%
deviation, the figure `C5-thermal-model.md` already documents).

## 2. Findings

### 2.1 Conductor temperature (75 → 100 °C)

Mean ampacity over the five sample hours of each case, in amperes:

| City | Case | 75 °C | 90 °C | 100 °C | Change 75→100 |
|---|---|---|---|---|---|
| Austin | hot calm | 784 | 944 | 1035 | +251 A (+31.9%) |
| Austin | median day | 1190 | 1365 | 1466 | +276 A (+23.3%) |
| Austin | breezy cool | 1657 | 1803 | 1891 | +234 A (+14.1%) |
| Corpus Christi | hot calm | 905 | 1063 | 1155 | +250 A (+27.5%) |
| Corpus Christi | median day | 1461 | 1664 | 1781 | +320 A (+21.9%) |
| Corpus Christi | breezy cool | 1765 | 1928 | 2024 | +259 A (+14.7%) |
| Midland | hot calm | 843 | 1010 | 1104 | +261 A (+30.9%) |
| Midland | median day | 1543 | 1748 | 1868 | +325 A (+21.1%) |
| Midland | breezy cool | 2086 | 2256 | 2358 | +272 A (+13.0%) |
| El Paso | hot calm | 730 | 889 | 980 | +250 A (+34.3%) |
| El Paso | median day | 1142 | 1301 | 1395 | +253 A (+22.1%) |
| El Paso | breezy cool | 1643 | 1785 | 1871 | +228 A (+13.9%) |

The perpendicular-wind cases add +343 to +360 A (+20% to +25%) and the parallel-wind cases +266 to +282 A (+19% to +23%)
across the four cities; the full table is in `sensitivity_temperature.csv`.

- Across all 20 city-and-case groups the 75→100 °C gain is **13–34%, or 228–360 A**.
- The gain is **proportionally largest when conditions are hot and calm** (27–34%) because less heat leaves the conductor by
  convection, so the allowed temperature rise counts for more. It is smallest in breezy-cool hours (13–15%).
- 90 °C captures roughly 60–65% of the gap, so the effect is close to proportional to the temperature limit.

**Computed rating against the static rating** (100 °C column of the table above, as % of `STATIC_RATINGS`):

- Hot calm: 57% (Austin), 77% (Corpus Christi), 59% (Midland), 74% (El Paso) of static, even at the emergency temperature.
- Windy cases: above static in most cities, up to 144% of static (Corpus Christi, perpendicular wind) and 142% (El Paso,
  breezy cool).

### 2.2 Line bearing

For each sample hour the rating was recomputed for every azimuth from 0° to 175°. The table gives, averaged over the five
hours of a case, how far the *worst* and the *best* azimuth sit from the assigned bearing (worst = lower rating, best = higher).

| City | Case | Rating at assigned bearing (A) | Worst azimuth is lower by | Best azimuth is higher by |
|---|---|---|---|---|
| Austin | hot calm | 784 | 8.8% | 7.3% |
| Austin | median day | 1189 | 8.4% | 21.7% |
| Austin | breezy cool | 1657 | 1.9% | 30.9% |
| Corpus Christi | hot calm | 905 | 5.7% | 19.9% |
| Corpus Christi | median day | 1461 | 18.8% | 8.1% |
| Corpus Christi | breezy cool | 1765 | 2.7% | 30.1% |
| Midland | hot calm | 843 | 9.5% | 12.9% |
| Midland | median day | 1543 | 22.5% | 3.4% |
| Midland | breezy cool | 2086 | 16.7% | 11.2% |
| El Paso | hot calm | 730 | 6.9% | 10.5% |
| El Paso | median day | 1142 | 6.0% | 24.4% |
| El Paso | breezy cool | 1643 | 0.1% | 33.3% |

- Across wind-driven hours, the rating changes by **up to about 20–35% either way** depending on orientation. Hot-calm hours
  vary less (about 6–20%) because there is little wind to cool the line.
- **Selection effect.** The perpendicular-wind and parallel-wind cases were picked against the assigned bearing, so the
  assigned bearing is at the best (perpendicular) or worst (parallel) point by construction (about 0–0.3% from the extreme).
  Their values (25% down, 33–34% up) show the *range* of the physics, not how wrong the assigned bearing is. The median-day
  and breezy-cool rows are the fairer read of how far the assigned placeholder is from the best or worst case.
- **Pattern.** In Austin and Corpus Christi (assigned 173°, roughly north-south), the cool-season hours are
  dominated by northerly wind, which runs along that axis; in those breezy-cool hours the best azimuth would give
  **30–31% more** than the assigned one. In Midland (assigned 267.5°, roughly east-west) the assigned bearing is
  17% above the worst azimuth and 11% below the best in the breezy-cool hours.

### 2.3 G4 bounds, static ratings and subconductor count (2025)

Share of 2025 hours in which the computed rating falls outside the G4 band and would be replaced by the static rating
(G4 only; the monitor's other gates are not counted). Assigned bearing, real wind direction.

| City | Alternative | Static (A) | Band (A) | Fallback at 75 °C | Fallback at 100 °C |
|---|---|---|---|---|---|
| Austin | current | 1825 | 1150–2500 | **31.99%** | 4.05% |
| Austin | old Project Definition ranges | 1900 | 800–3000 | 0.58% | 0.00% |
| Austin | count +1 (3) | 1217 | 767–1667 | 1.78% | 16.24% |
| Corpus Christi | current | 1500 | 800–2200 | 0.07% | 0.29% |
| Corpus Christi | old Project Definition ranges | 3000 | 1000–5000 | 3.09% | 0.05% |
| Corpus Christi | count +1 (3) | 1000 | 533–1467 | 27.13% | 77.44% |
| Midland | current | 1875 | 1250–2500 | **17.48%** | 4.05% |
| Midland | old Project Definition ranges | 1800 | 600–3000 | 0.00% | 0.00% |
| Midland | count +1 (3) | 1250 | 833–1667 | 32.60% | 67.65% |
| El Paso | current | 1320 | 640–2000 | 0.08% | 0.53% |
| El Paso | old Project Definition ranges | 1450 | 600–2300 | 0.02% | 0.01% |
| El Paso | count +1 (2) | 660 | 320–1000 | 86.85% | 99.45% |

- With **count −1** (Austin, Corpus Christi, Midland: a single conductor carries the whole bundle) the static rating doubles
  and almost every hour falls below the lower bound (92–100% at 75 °C; 45–99.9% at 100 °C). El Paso has no −1 case
  (its count is already 1).
- In the current configuration, Austin (32%) and Midland (17%) already fall back in a large share of hours at 75 °C. These
  are almost all hours with a computed rating *below the lower bound*; raising the limit to 100 °C cuts that to about 4%.
- The current Corpus Christi and El Paso fallback rates are small (0.07–0.53%).

## 3. Why the variances matter

1. **Safety direction.** The commitment in `PROJECT.md` is never to overstate what a line can carry. A higher
   conductor limit or a favourable bearing raises the computed rating; if either is wrong the computed rating is too high
   by that amount. Today the pipeline uses the **normal** limit (75 °C), which is the conservative one. Switching
   any published number to 100 °C moves it up 13–34% and makes it an **emergency-basis** number that must be labelled as such.
2. **Temperature is no longer an unknown; basis is.** The 75/100 °C limits are confirmed by Power Systems (per the owner).
   What the sweep shows is the cost of getting the *basis* wrong: a downstream consumer that expects the normal rating and
   receives an emergency one (or the reverse) is off by about 230–360 A.
3. **Bearing is the largest unconfirmed physical input.** The 173.15° and 267.54° values are corridor-to-corridor angles
   between city centres, not line azimuths (`PROVENANCE-LEDGER.md` §3). The sweep shows the rating can move by
   tens of percent in wind-driven hours, in either direction, and it is plausibly near its *worst* case in the cool-season
   northerlies for Austin and Corpus Christi. `line_bearing_check.md` found no better-supported replacement from public
   data, so only Power Systems can close this.
4. **Static ratings and bounds decide how often the pipeline falls back.** The bundle ranges (basis and temperature
   unconfirmed) and the subconductor counts (provisional) set both the static rating and the G4 band, so they control
   how much of the dynamic rating ever reaches a user. A ±1 count error moves fallback from under 1% to anywhere up to
   99%. This matches finding 9 in `real_data_validation.md` (static ratings, bounds and the computed rating rest on different
   assumptions).
5. **Consistency check on the static values.** In hot, calm hours even the emergency (100 °C) computed rating is only
   57–77% of the static rating. A static rating normally represents worst-case weather, so it should not exceed what the same
   conductor can carry in worst-case weather. That is consistent with the bundle ranges assuming a different conductor, count
   or basis than the single Drake conductor modelled here. This does not prove that, and the sample hours are about 31–35 °C
   rather than the standard's 40 °C worst case, but it is a reason to ask Power Systems what conductor and temperature
   the ranges assume.

## 4. Potential takeaways

1. **Keep `max_temp_c` at 75 °C** (the confirmed normal limit) and label it as such. No value change is needed; the work is
   labelling (see `PROVENANCE-LEDGER.md` §6).
2. **Add a rating-basis field** (normal 75 °C / emergency 100 °C) to the PSS/E contract (PSSE-01/PSSE-02), so a consumer cannot
   mistake one for the other. The 13–34% gap is the size of the mistake it prevents.
3. **Ask Power Systems for the real line azimuth per city first.** It is the input with the largest physical effect that the repo
   cannot resolve from public data. Ask for the subconductor counts and for the conductor and temperature behind each bundle range
   in the same message.
4. **Treat the static ratings and G4 bounds as the biggest driver of fallback behaviour**, and keep them labelled provisional wherever
   they appear until the counts are confirmed.
5. **Add elevation to the list of inputs to confirm.** `elevation_m` is 900 m for every city, but the station metadata
   implies roughly 80–140 m for Austin and near sea level for Corpus Christi. It was not swept here, but it affects air density.

## 5. What this does not settle

- **Refit decision (PROV-05 criterion 3 and 4).** I have not yet traced which of the 12 shadow artifacts and the per-city
  "ml" models depend on temperature or bearing in their training targets. Until that is done, this note cannot say whether
  a changed input would force a refit. The model freeze is **2026-11-01**; the owner's decision (refit, freeze as-is with the
  assumption documented, or defer) is not recorded here.
- **Sample-based figures.** The temperature and bearing results come from 100 chosen hours, not the whole year.
  Only the G4 bounds table uses the full year.
- **Weather source.** Open-Meteo reanalysis (10 m wind, horizontal shortwave), not the TCEQ/ASOS station wind the live pipeline
  uses; absolute amperes will differ from live ratings, but the relative effects should hold.
- **G4 only.** Fallback percentages count the plausibility band only, not gates G1–G6 together.
- **Elevation, emissivity/absorptivity and conductor type** were not varied.

## 6. Reproducing

From the repo root, with numpy installed:

```
py -I .planning/workstreams/input-provenance/phase2/fetch_dev_weather.py
py -I .planning/workstreams/input-provenance/phase2/pick_samples.py
py -I .planning/workstreams/input-provenance/phase2/ieee_sensitivity.py
```

Related: `PROVENANCE-LEDGER.md` (input sources), `docs/data-science/decisions/line_bearing_check.md`,
`docs/data-science/decisions/real_data_validation.md` (finding 9), `docs/data-science/decisions/confirmation_protocol_v3_per_city.md`
(anti-peeking rules and the 2026-11-01 freeze).
