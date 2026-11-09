# Austin conductor maximum operating temperature: Drake ACSR at 100 °C (2026-10-27)

**Status:** decision recorded; no value changed yet. The config change lands in Phase 7 (per-city conductors,
COND-01) after the Phase 6 72 h soak closes (window ends 2026-10-30T03:35:00Z). Changing it now would move ratings
inside the soak window.

**Decision:** AUSTIN's conductor stays 795 kcmil Drake ACSR, and its maximum operating temperature (MOT) becomes
**100 °C** instead of the current 75 °C. This answers Phase 7 D-09 for Austin's MOT ("until Power Systems
answers"). The other three cities stay at 75 °C, labelled provisional, until their utilities' values are known.

## Source

| What | Source | Confidence |
|---|---|---|
| Austin Energy's lines are Drake ACSR with a 100 °C maximum line design temperature | Owner's teammate who works for Austin Energy, relayed by the owner 2026-10-27 (personal communication) | confirmed, direct utility source |
| Austin Energy rated its 345 kV lines (795 ACSR Drake, Lapwing, Condor) at 100 °C, 40 °C ambient, 2 ft/s wind, ε = α = 0.5 | [ERCOT ROS 2005 SPWG comments](https://www.ercot.com/files/docs/2005/02/08/ros02102005_7.doc), found in `.planning/workstreams/production-pipeline/phases/03-real-data-validation/03-05-CONDUCTOR-RESEARCH.md` | confirmed, utility's own filing |

Two independent sources, twenty years apart, give the same value.

## Why 100 °C is possible when many sources say Drake "anneals at 100 °C"

Sources disagree on where annealing starts: some say 75 °C, some 80 °C, some about 93 °C. Annealing is not a
threshold. Each utility chooses its MOT from how much strength loss it accepts over the line's life, so the
utility's own value outranks a generic figure online.

1. **Annealing is cumulative, not a switch.** Hard-drawn aluminum strands lose tensile strength gradually, and the
   rate depends on both temperature and time at that temperature. A line does not lose its strength the moment it
   reaches 100 °C. Strength loss is budgeted over the design life. One worked example: with a 10 % strength-loss
   limit over a 30-year life, about 450 h per year at 100 °C does the same damage as about 9 h per year at 125 °C
   ([IAEI Magazine](https://iaeimagazine.org/?p=8702)).
2. **A line seldom reaches its MOT.** The conductor only reaches 100 °C when it carries its full rated current in
   the worst cooling weather assumed by the rating (hot, sunny, almost no wind). Most hours it runs far cooler, so
   the yearly time spent near 100 °C is small.
3. **"Maximum line design temperature" is mainly a sag and clearance limit.** Conductors sag more as they heat. NESC
   ground clearances are checked at the maximum operating temperature, so a line designed for 100 °C was built
   with enough clearance to run that hot. Austin Energy's design value means the towers and spans were laid out for it.
4. **100 °C is a common continuous ceiling for ACSR.** Typical ACSR can run continuously up to about 100 °C without
   a significant change in its sag-related properties
   ([USPTO patent 7516051](https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7516051)). CIGRE
   publishes a whole guide on running conventional conductors above 100 °C
   ([CIGRE TB 643](https://www.e-cigre.org/publications/detail/643-guide-to-the-operation-of-conventional-conductor-systems-above-100oc.html)).
   Other utilities differ: Oncor rates 1590 ACSR at 90 °C (research note, Q2), and some references limit classic
   ACSR to 80 °C ([Miskolc paper](https://ojs.uni-miskolc.hu/index.php/hmcse/article/download/2715/1881/10663)).
   The variation is a utility choice, which is why Austin's own value governs Austin.

## What it changes in the model

**The math is unchanged.** In `backend/thermal_model.py`'s IEEE 738 heat balance, `max_temp_c` is not an assumed
running temperature. It is the ceiling. The rating is the current that would heat the conductor to exactly that
ceiling in the hour's weather. The real conductor reaches it only if the line is actually loaded to the rating.
"The conductor is not at 100 °C all the time" is therefore already built into how a rating works, and nothing
in the formula needs to change. Only the input value changes.

**The input moves ratings a lot.** Our own model (`ieee738_ampacity`, current Drake kwargs, ε = α = 0.8, run
2026-10-27):

| Weather case | 75 °C | 100 °C | Change |
|---|---|---|---|
| Hot and calm (40 °C, 0.61 m/s, 1000 W/m²) | 777 A | 1066 A | +37 % |
| Typical (25 °C, 2 m/s, 600 W/m²) | 1310 A | 1585 A | +21 % |

**Effect on Austin's fallbacks.** Austin's computed ratings (about 1100–1440 A during the Phase 6 dry soak) keep
landing below its G4 lower plausibility bound of 1150 A (`config.RATING_BOUNDS_BY_LOCATION`). That is why AUSTIN
published the static rating in 25 of 50 dry-soak hours (`06-DRY-SOAK-REPORT.md`). At 100 °C most of those hours
should come out above 1150 A, so the fallback share should fall sharply. Per the owner's rule, a low-side G4
fallback is correct and safe, so this is an accuracy improvement, not a safety fix.

## Caveat: dynamic ratings use more of the annealing budget

A static rating assumes bad cooling weather, so a line loaded to it usually runs well below MOT. A dynamic rating
removes that margin: if operators load the line to the dynamic rating, the conductor spends more hours near
100 °C than it would under a static rating. That spends the annealing budget faster. This is not a reason to keep
75 °C, because the utility's MOT already allows for that wear. It is a reason to tell consumers (dashboard and
PSS/E) that loading to the dynamic rating should come with tracking, or a cap, on hours spent near MOT. That
tracking is the utility's job, not this system's. This system publishes the thermal limit; it does not dispatch.

## Related input: elevation (all four cities, sourced)

The model uses `elevation_m: 900.0` for every city (`config.py`, commented "West Texas Permian Basin avg
elevation"). Measured at each `config.CITY_COORDINATES` point on 2026-10-27:

| City | Point (lat, lon) | USGS 3DEP | Open-Meteo | Current value | Rating effect of the measured value at 100 °C, typical / hot-calm case |
|---|---|---|---|---|---|
| AUSTIN | 30.2711, -97.7437 | 163.1 m | 167 m | 900 m | +2.3 % / -0.1 % |
| CORPUS_CHRISTI | 27.7635, -97.4033 | 9.6 m | 10 m | 900 m | +2.7 % / +0.3 % |
| MIDLAND | 31.9974, -102.0779 | 847.3 m | 851 m | 900 m | +0.2 % / +0.1 % |
| EL_PASO | 31.7601, -106.4870 | 1133.3 m | 1141 m | 900 m | -0.7 % / -0.5 % |

- **Source:** USGS Elevation Point Query Service (3DEP),
  `https://epqs.nationalmap.gov/v1/json?x=<lon>&y=<lat>&wkid=4326&units=Meters`, cross-checked against the
  [Open-Meteo elevation API](https://open-meteo.com/en/docs/elevation-api). The two agree within 8 m everywhere.
  Austin's 163 m matches the 2026-10-21 research note (Q6), which also lists nearby NWS stations (KAUS 148 m,
  KATT 200 m).
- **Reading:** 900 m is right for Midland only by coincidence. It is about 740 m too high for Austin, 890 m too
  high for Corpus Christi, and 230 m too low for El Paso. The rating effect is small (under 3 %), because
  elevation only changes air density in the convection term. Fixing it is cheap and removes an unsourced
  constant, but it is not what drives Austin's fallbacks. MOT does.
- **Caveat:** an elevation at the city point is not the elevation of a specific line. A point rating has no
  single line (`line_bearing_check.md` makes the same point for bearings), so the point's ground elevation is the
  most defensible single value.
- **Status:** proposed, owner to confirm. D-09 recorded the owner declining the elevation fix; these sourced
  values are offered so that decision can be revisited with evidence.

## Out of scope (owner decision, 2026-10-27)

Each city is modelled as a point source, not as a specific line, so no per-line detail is needed. Everything else
in the conductor model stays as it is:

- `config.SUBCONDUCTORS_PER_PHASE`: unchanged.
- Emissivity and absorptivity (ε = α = 0.8): unchanged. The 2005 filing's 0.5 / 0.5 is noted for context only.
- Conductor type: Drake for every city, unchanged.

## When applied (Phase 7)

- Set AUSTIN `max_temp_c` to 100.0 in the per-city conductor table, with this note and both sources recorded as
  the value's source. Bump the config version (D-01 fingerprint columns will show the change in `latest_rating`).
- Refit the forecast and anomaly models on 100 °C ratings (Phase 7 shadow refit), and re-run the real-data
  validation so the G4 fallback share is re-measured.
- The provisional label (`is_provisional`) stays until REVAL-01. This change does not lift it.
