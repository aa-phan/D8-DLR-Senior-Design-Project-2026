# Line bearing check (2026-10-13)

**Status:** research note; no value changed. Owner instruction (2026-10-13): check whether
`config.CITY_LINE_BEARING_DEG` is realistic; substitute estimates and refit everything only if it is not.

## What was measured
HIFLD transmission-line layer (public, mirrored at `gis.elpasotexas.gov/.../source_HIFLD_Open/MapServer/7`),
filter `VOLTAGE = 345`, line segments whose midpoint lies within 15 / 30 / 60 km of each city point
(`config.CITY_COORDINATES`). Each segment's axial bearing (0-180 deg, a line has no direction) was weighted by length.
`R` is the concentration of the weighted bearings (1 = all parallel, 0 = evenly spread). Run once on 2026-10-13.

| City | Current bearing (axis, deg) | 345 kV km within 30 km | Dominant axis within 30 km | R | Within 60 km |
|---|---|---|---|---|---|
| AUSTIN | 173.15 (axis 173) | 221 | 30 | 0.46 | 47, R 0.25 |
| CORPUS_CHRISTI | 173.15 (axis 173) | 76 (none within 15) | 16 | 0.21 | 22, R 0.36 |
| MIDLAND | 267.54 (axis 88) | 277 | 75 | 0.63 | 69, R 0.47 |
| EL_PASO | 267.54 (axis 88) | 96 | 147 | 0.33 | 141, R 0.31 |

## Reading
- **Midland:** most 345 kV length (207 of 277 km) lies in the 67.5-90 deg sector; the current axis (88) is in that
  sector, about 13-17 deg from the dominant axis. Realistic as an approximation.
- **Austin, Corpus Christi, El Paso:** the lines near each city run in several directions (R 0.21-0.46); no single
  axis represents them. The current value is one of several plausible orientations, not demonstrably wrong, and no
  replacement estimate is better supported than the placeholder. A point rating has no single line, so a per-city
  bearing is an assumption by construction.
- El Paso's 345 kV network is El Paso Electric (WECC), not ERCOT; the same limit applies.

## Decision
No substitution: no data-backed estimate is more defensible than the carried-over value, so substituting would add
false precision and force a post-signature refit of all 12 shadow artifacts (hash manifest) and the per-city models.
The bearings stay a documented assumption (`point_scope.md`, Open Questions). To resolve properly, obtain the actual
line azimuth from Power Systems for the segment each city represents.

## Limits
HIFLD geometry is approximate and may be outdated; `UNKNOWN` substations appear; segments within the radius are not
necessarily the lines whose rating the project means.

Reproduce: `.venv/bin/python -I docs/data-science/decisions/line_bearing_check.py` from the repo root (network; read-only).
