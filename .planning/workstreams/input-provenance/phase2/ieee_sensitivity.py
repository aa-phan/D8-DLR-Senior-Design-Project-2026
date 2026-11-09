"""Phase 2 (PROV-05) ampacity sensitivity to the unresolved rating inputs.

DRAFT FOR REVIEW -- not yet run. Read-only with respect to the repo: it imports `backend/config.py` and
`backend/thermal_model.py`, never edits them, and writes only CSVs under `--out-dir`.

Usage (repo root, needs numpy):
    py -I .planning/workstreams/input-provenance/phase2/ieee_sensitivity.py --dry-run
    py -I .planning/workstreams/input-provenance/phase2/ieee_sensitivity.py [--section all|temperature|bearing|bounds]

What it measures, each against the live code path (`thermal_model.ieee738_ampacity`, one Drake ACSR conductor,
per-city defaults from `config.conductor_kwargs_for`, `solar_altitude_deg` 45 as `DLRSafetyMonitor` uses):

  temperature  The 75 / 90 / 100 C conductor limit (75 = confirmed normal, 100 = confirmed emergency; 90 is an
               intermediate point) on the sample hours in `samples_5_per_case.csv`.
  bearing      The line azimuth swept 0-175 deg (a line axis has no direction) on the same sample hours; the
               assigned `config.CITY_LINE_BEARING_DEG` is an unconfirmed placeholder (PROV-03).
  bounds       On the full 2025 development year (`dev_weather_2025_<CITY>.json`, real wind direction): how often
               the computed rating falls outside the G4 plausibility bounds (-> static-rating fallback) under the
               current and alternative static ratings / bounds / subconductor counts, at 75 and 100 C.

Inputs are development data only (2025; before the 2026-09-29 anti-peeking cutoff). No FRESH outcome data is read.

Limits to keep in mind when reading the output:
  * Weather is Open-Meteo reanalysis (10 m wind, horizontal shortwave), not the station wind the live pipeline uses.
  * `bounds` counts only the G4 band. The real monitor has other gates (G1-G6), so this is the G4 share of fallbacks,
    not the total fallback rate.
  * Subconductor-count alternatives rescale the per-conductor static rating and bounds only; the computed
    per-conductor rating does not depend on the count.
"""
import argparse
import csv
import json
import pathlib
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[3]  # phase2 -> input-provenance -> workstreams -> .planning -> repo root
sys.path.insert(0, str(REPO / "backend"))

import config  # noqa: E402
import thermal_model as tm  # noqa: E402

SAMPLES_CSV = HERE / "samples_5_per_case.csv"
DEFAULT_OUT_DIR = HERE / "out"

TEMPERATURES_C = (75.0, 90.0, 100.0)
AZIMUTHS_DEG = tuple(range(0, 180, 5))
SOLAR_ALTITUDE_DEG = 45.0  # DLRSafetyMonitor default; the pipeline passes no per-hour value

# Power Systems 345 kV bundle ranges (A) behind STATIC_RATINGS / RATING_BOUNDS_BY_LOCATION.
# Source: comments in backend/config.py (commits cd4c365, a5004e5, 2026-10-13); basis and temperature unconfirmed.
BUNDLE_RANGES_A = {
    "AUSTIN": (2300.0, 5000.0),
    "CORPUS_CHRISTI": (1600.0, 4400.0),
    "MIDLAND": (2500.0, 5000.0),
    "EL_PASO": (640.0, 2000.0),
}

# Per-conductor ranges used before 2026-10-13: "Worst Case Static Limit" in docs/Project Definition.md lines 79-84.
OLD_PROJECT_DEFINITION_RANGES_A = {
    "AUSTIN": (800.0, 3000.0),
    "CORPUS_CHRISTI": (1000.0, 5000.0),
    "MIDLAND": (600.0, 3000.0),
    "EL_PASO": (600.0, 2300.0),
}

# IEEE Std 738-2023 4.6.1 worked example, as reproduced in backend/tests/thermal_model_test.py.
WORKED_EXAMPLE_EXPECTED_A = 1025.0
WORKED_EXAMPLE_TOLERANCE = 0.02


# ──────────────────────────────────────────────────────────────────────────────
# Rating helper
# ──────────────────────────────────────────────────────────────────────────────
def conductor(city, **overrides):
    """ConductorConfig for `city` exactly as `city_point` builds it, with optional overrides."""
    kwargs = config.conductor_kwargs_for(config.CITY_LINE_BEARING_DEG[city])
    kwargs.update(overrides)
    return tm.ConductorConfig(**kwargs)


def rate(city, temp_c, wind_ms, wdir_deg, ghi_wm2, **overrides):
    """Per-conductor ampacity (A). Arrays or scalars. `overrides` go to ConductorConfig
    (max_temp_c, line_azimuth, elevation_m, ...); the perpendicular wind uses the overridden azimuth."""
    cond = conductor(city, **overrides)
    perp = tm.perpendicular_wind(wind_ms, wdir_deg, cond.line_az)
    return tm.ieee738_ampacity(temp_c, perp, ghi_wm2, cond, solar_altitude_deg=SOLAR_ALTITUDE_DEG)


def self_check():
    """Guard: the helper's underlying model must still reproduce the published worked example."""
    cond = tm.ConductorConfig(diameter_m=0.02814, resistance_ac=0.07283, emissivity=0.8, absorptivity=0.8,
                              max_temp_c=100.0, line_azimuth=90.0, elevation_m=0.0)
    amps = float(tm.ieee738_ampacity(40.0, 0.61, 1027.0, cond, solar_altitude_deg=76.2))
    err = abs(amps - WORKED_EXAMPLE_EXPECTED_A) / WORKED_EXAMPLE_EXPECTED_A
    if err > WORKED_EXAMPLE_TOLERANCE:
        raise SystemExit(f"self-check failed: worked example gave {amps:.1f} A (expected "
                         f"{WORKED_EXAMPLE_EXPECTED_A:.0f} A +/- {WORKED_EXAMPLE_TOLERANCE:.0%})")
    print(f"self-check ok: IEEE 738 worked example = {amps:.1f} A (expected {WORKED_EXAMPLE_EXPECTED_A:.0f} A)")


# ──────────────────────────────────────────────────────────────────────────────
# Inputs
# ──────────────────────────────────────────────────────────────────────────────
def load_samples(path):
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("air_temp_c", "wind_ms", "wind_dir_deg", "ghi_wm2", "line_azimuth_deg"):
            r[k] = float(r[k])
        if r["city"] not in config.CITY_LINE_BEARING_DEG:
            raise SystemExit(f"unknown city in samples: {r['city']!r}")
        if abs(r["line_azimuth_deg"] - config.CITY_LINE_BEARING_DEG[r["city"]]) > 1e-6:
            raise SystemExit(f"{r['city']}: samples were picked against bearing {r['line_azimuth_deg']}, "
                             f"config now has {config.CITY_LINE_BEARING_DEG[r['city']]}; re-run pick_samples.py")
    return rows


def load_year(city):
    path = HERE / f"dev_weather_2025_{city}.json"
    hourly = json.loads(path.read_text())["response"]["hourly"]
    cols = ("temperature_2m", "wind_speed_10m", "wind_direction_10m", "shortwave_radiation")
    keep = [i for i in range(len(hourly["time"])) if all(hourly[c][i] is not None for c in cols)]
    return {
        "time": [hourly["time"][i] for i in keep],
        "temp": np.array([hourly["temperature_2m"][i] for i in keep], dtype=float),
        "wind": np.array([hourly["wind_speed_10m"][i] for i in keep], dtype=float),
        "wdir": np.array([hourly["wind_direction_10m"][i] for i in keep], dtype=float),
        "ghi": np.array([hourly["shortwave_radiation"][i] for i in keep], dtype=float),
    }


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {path} ({len(rows)} rows)")


# ──────────────────────────────────────────────────────────────────────────────
# Temperature sweep
# ──────────────────────────────────────────────────────────────────────────────
def temperature_sweep(samples, out_dir):
    rows = []
    for s in samples:
        static = config.STATIC_RATINGS[s["city"]]
        base = None
        for t in TEMPERATURES_C:
            amps = float(rate(s["city"], s["air_temp_c"], s["wind_ms"], s["wind_dir_deg"], s["ghi_wm2"],
                              max_temp_c=t))
            base = amps if t == TEMPERATURES_C[0] else base
            rows.append({"city": s["city"], "case": s["case"], "time_utc": s["time_utc"], "max_temp_c": t,
                         "amps": round(amps, 1), "static_a": static,
                         "pct_of_static": round(100 * amps / static, 1),
                         "delta_vs_75_a": round(amps - base, 1),
                         "delta_vs_75_pct": round(100 * (amps - base) / base, 1) if base else ""})
    write_csv(out_dir / "sensitivity_temperature.csv", rows)

    print("\nTemperature sweep: mean ampacity (A) and 75->100 C change, by city and case")
    print(f"{'city':15s} {'case':19s} {'75C':>7s} {'90C':>7s} {'100C':>7s} {'75->100 %':>10s} {'100C %static':>13s}")
    for city in config.CITY_LINE_BEARING_DEG:
        for case in dict.fromkeys(r["case"] for r in rows):
            sel = [r for r in rows if r["city"] == city and r["case"] == case]
            mean = {t: np.mean([r["amps"] for r in sel if r["max_temp_c"] == t]) for t in TEMPERATURES_C}
            print(f"{city:15s} {case:19s} {mean[75.0]:7.0f} {mean[90.0]:7.0f} {mean[100.0]:7.0f} "
                  f"{100 * (mean[100.0] - mean[75.0]) / mean[75.0]:9.1f}% "
                  f"{100 * mean[100.0] / config.STATIC_RATINGS[city]:12.1f}%")


# ──────────────────────────────────────────────────────────────────────────────
# Bearing sweep
# ──────────────────────────────────────────────────────────────────────────────
def bearing_sweep(samples, out_dir, temp_c):
    rows = []
    summary = {}
    for s in samples:
        city = s["city"]
        assigned = float(rate(city, s["air_temp_c"], s["wind_ms"], s["wind_dir_deg"], s["ghi_wm2"],
                              max_temp_c=temp_c))
        by_az = {}
        for az in AZIMUTHS_DEG:
            by_az[az] = float(rate(city, s["air_temp_c"], s["wind_ms"], s["wind_dir_deg"], s["ghi_wm2"],
                                   max_temp_c=temp_c, line_azimuth=float(az)))
            rows.append({"city": city, "case": s["case"], "time_utc": s["time_utc"], "max_temp_c": temp_c,
                         "azimuth_deg": az, "amps": round(by_az[az], 1),
                         "assigned_azimuth_deg": s["line_azimuth_deg"], "assigned_amps": round(assigned, 1)})
        lo, hi = min(by_az.values()), max(by_az.values())
        summary.setdefault((city, s["case"]), []).append(
            (assigned, lo, hi, 100 * (assigned - lo) / assigned, 100 * (hi - assigned) / assigned))
    write_csv(out_dir / f"sensitivity_bearing_{int(temp_c)}C.csv", rows)

    print(f"\nBearing sweep at {temp_c:.0f} C: mean over samples of the assigned-bearing rating and its range "
          f"over azimuths 0-175 deg")
    print(f"{'city':15s} {'case':19s} {'assigned':>9s} {'min':>7s} {'max':>7s} {'-vs assigned':>13s} {'+vs assigned':>13s}")
    for (city, case), vals in summary.items():
        a = np.array(vals)
        print(f"{city:15s} {case:19s} {a[:, 0].mean():9.0f} {a[:, 1].mean():7.0f} {a[:, 2].mean():7.0f} "
              f"{a[:, 3].mean():12.1f}% {a[:, 4].mean():12.1f}%")


# ──────────────────────────────────────────────────────────────────────────────
# G4 bounds / static-rating alternatives, full 2025 year
# ──────────────────────────────────────────────────────────────────────────────
def alternative_sets(city):
    """(label, static_a, lo_a, hi_a) per-conductor alternatives for `city`."""
    out = [("current", config.STATIC_RATINGS[city], *config.RATING_BOUNDS_BY_LOCATION[city])]
    lo, hi = OLD_PROJECT_DEFINITION_RANGES_A[city]
    out.append(("old_project_definition", (lo + hi) / 2, lo, hi))
    blo, bhi = BUNDLE_RANGES_A[city]
    n = config.SUBCONDUCTORS_PER_PHASE[city]
    for label, n_alt in (("count_minus_1", n - 1), ("count_plus_1", n + 1)):
        if n_alt >= 1:
            out.append((label, (blo + bhi) / 2 / n_alt, blo / n_alt, bhi / n_alt))
    return out


def bounds_fullyear(out_dir):
    rows = []
    for city in config.CITY_LINE_BEARING_DEG:
        w = load_year(city)
        n = len(w["time"])
        for t in (75.0, 100.0):
            amps = np.asarray(rate(city, w["temp"], w["wind"], w["wdir"], w["ghi"], max_temp_c=t))
            for label, static, lo, hi in alternative_sets(city):
                below, above = int(np.sum(amps < lo)), int(np.sum(amps > hi))
                in_band = (amps >= lo) & (amps <= hi)
                rows.append({"city": city, "max_temp_c": t, "alternative": label, "hours": n,
                             "static_a": round(static, 1), "lo_a": round(lo, 1), "hi_a": round(hi, 1),
                             "pct_below_lo": round(100 * below / n, 2), "pct_above_hi": round(100 * above / n, 2),
                             "pct_g4_fallback": round(100 * (below + above) / n, 2),
                             "pct_in_band_above_static": round(100 * float(np.sum(in_band & (amps > static))) / n, 2),
                             "median_amps": round(float(np.median(amps)), 1),
                             "p5_amps": round(float(np.percentile(amps, 5)), 1),
                             "p95_amps": round(float(np.percentile(amps, 95)), 1)})
    write_csv(out_dir / "sensitivity_bounds_2025.csv", rows)

    print("\nG4 bounds on 2025 (assigned bearing): % of hours falling back, by city, limit and alternative")
    print(f"{'city':15s} {'T':>4s} {'alternative':23s} {'static':>7s} {'band':>13s} {'<lo %':>7s} {'>hi %':>7s} {'fallback %':>11s}")
    for r in rows:
        print(f"{r['city']:15s} {r['max_temp_c']:4.0f} {r['alternative']:23s} {r['static_a']:7.0f} "
              f"{r['lo_a']:6.0f}-{r['hi_a']:<6.0f} {r['pct_below_lo']:7.2f} {r['pct_above_hi']:7.2f} "
              f"{r['pct_g4_fallback']:11.2f}")


# ──────────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--section", choices=("all", "temperature", "bearing", "bounds"), default="all")
    ap.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    ap.add_argument("--bearing-temp", type=float, default=75.0,
                    help="conductor temperature (C) for the bearing sweep (default 75)")
    ap.add_argument("--dry-run", action="store_true",
                    help="run the self-check and load the inputs, print what would be computed; compute and write nothing")
    args = ap.parse_args()

    self_check()
    samples = load_samples(SAMPLES_CSV)
    print(f"samples: {len(samples)} rows from {SAMPLES_CSV.name} "
          f"({len({r['city'] for r in samples})} cities, {len({r['case'] for r in samples})} cases)")
    do = lambda name: args.section in ("all", name)  # noqa: E731

    if args.dry_run:
        years = {c: len(load_year(c)["time"]) for c in config.CITY_LINE_BEARING_DEG}
        print(f"2025 hours per city: {years}")
        if do("temperature"):
            print(f"would run: temperature sweep {TEMPERATURES_C} -> {len(samples) * len(TEMPERATURES_C)} rows")
        if do("bearing"):
            print(f"would run: bearing sweep {AZIMUTHS_DEG[0]}-{AZIMUTHS_DEG[-1]} step 5 at {args.bearing_temp:.0f} C "
                  f"-> {len(samples) * len(AZIMUTHS_DEG)} rows")
        if do("bounds"):
            print("would run: G4 bounds on full 2025 at 75/100 C with alternatives "
                  f"{[a[0] for a in alternative_sets('AUSTIN')]}")
        print(f"output directory: {args.out_dir}")
        return

    if do("temperature"):
        temperature_sweep(samples, args.out_dir)
    if do("bearing"):
        bearing_sweep(samples, args.out_dir, args.bearing_temp)
    if do("bounds"):
        bounds_fullyear(args.out_dir)


if __name__ == "__main__":
    main()
