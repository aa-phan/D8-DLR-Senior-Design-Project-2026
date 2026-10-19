"""
Lead-Time Calibration Gate (D-01's legacy 1h hard gate + D-04's PRIMARY
24h offset-lead verification, Phase 3 experiment)
===================================================================
This module VERIFIES TWO DETERMINISTIC STITCHING RULES -- neither is ever
believed on the vendor's or D-04's own say-so, both are measured. Never an
estimation of a fuzzy distribution.

**Legacy 1-hour rule (D-01, now a demoted non-primary curiosity arm).**
With `models=ecmwf_ifs` pinned on both Open-Meteo endpoints, the bulk
Historical Forecast product's value at valid time `T` is expected to equal
the `run = T.floor('6h')` single run's value at lead `T.hour % 6`, because
the bulk product stitches exactly the first six hours of each six-hourly
ECMWF IFS run (03-RESEARCH.md Pattern 2, live-measured bit-identical at
leads 0-5, divergent at lead >= 6, across three cities and three seasons).
This gate is EXPECTED TO FAIL when applied to the unfiltered series: the
bulk product's lead distribution over all hours is uniform on {0,1,2,3,4,5},
so its fifth-percentile lead is 0 h, which cannot support a 60-minute claim.
That failure is the correct measured outcome, not a defect -- the gate must
NEVER be relaxed, widened, or otherwise tuned until it passes on the
unfiltered series. It passes only on the `hour % 6 == 1` subset, where the
lead is exactly 1 h on every row. See `measure_lead_alignment`/
`assert_supports_horizon`/`LEAD_RULE_DESCRIPTION`.

**PRIMARY 24-hour offset rule (D-04, this refresh's central finding).** With
`models=gfs_seamless` pinned on the Previous Runs / Single-Runs pair, the
Previous-Runs product's `previous_day1` value at valid time `T` equals the
`run = (T - 24h).floor('6h')` single run's value at offset `T - run` hours,
which works out to `24 + (T.hour % 6)` hours -- exactly 24.0h ONLY when
`T.hour % 6 == 0`. Open-Meteo's own docs, and D-04's own text in
`03-CONTEXT.md`, both describe `previous_day1` as a flat, exact-by
-construction 24-hour lead; both are wrong for 5 of every 6 hours
(live-verified this session, 96 hour-cells across 2 cities, 2 dates, 2
variables and all 4 daily cycles, zero exceptions). The SAME "never trust
the product's stated lead time" discipline that motivated this module's
original 1-hour gate applies here, just re-pointed at a different pair of
endpoints with the remainder changed from 1 to 0. See
`measure_previous_runs_alignment`/`assert_exact_offset_lead`/
`PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION`.

This is disposable offline tooling, following the same standalone
-entry-point convention `forecast_training.py` and `anomaly_training.py`
follow: it imports `open_meteo_forecast_provider`; nothing imports it.
Never part of the runtime pipeline.
"""

import argparse
import json
import logging
import os

import numpy as np
import pandas as pd

import config
import open_meteo_forecast_provider as provider

logger = logging.getLogger(__name__)

# A one-sentence plain-language statement of the rule under test, emitted
# into the JSON report so the report is self-describing.
LEAD_RULE_DESCRIPTION: str = (
    "With models=ecmwf_ifs pinned, the bulk Historical Forecast product's "
    "value at valid time T equals the run=T.floor('6h') single run's value "
    "at lead T.hour % 6 -- verified, not estimated -- because the bulk "
    "product stitches exactly the first six hours of each six-hourly run."
)

# The sibling rule-description constant for D-04's PRIMARY 24-hour offset
# rule -- a DISTINCT string from LEAD_RULE_DESCRIPTION above, so a future
# edit cannot collapse the two rules into one.
#
# Measured, not vendor-trusted: Open-Meteo's own docs describe
# `previous_day1` as a flat, exact-by-construction 24-hour lead
# ("the value that was predicted 24 hours before valid time"), and D-04's
# own text in `03-CONTEXT.md` repeats that characterization ("gives an
# exact, unambiguous lead by construction... no calibration gate needed at
# all"). Both are contradicted by direct measurement this session: 96
# hour-cells across 2 cities, 2 dates, 2 variables and all 4 daily GFS
# cycles, zero exceptions -- `previous_day1` is stitched from the SAME
# "first six hours of each six-hourly run" mechanism the legacy rule above
# already established, just offset by +24h instead of +0h.
#
# Assumption B2's limitation (03-RESEARCH.md): the Single-Runs archive for
# `models=gfs_seamless` reaches back only a few months (live-verified
# reachable to roughly 2026-06-01; a probe to 2025-12-01 returned HTTP
# 400), so this rule's cross-check cannot be run against 2024-2025 dates
# directly -- its applicability to those years rests on the mechanism being
# general (the same six-hourly-cycle stitching every GFS run family uses),
# not on a direct historical cross-check against those specific years.
PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION: str = (
    "With models=gfs_seamless pinned, the Previous Runs product's "
    "previous_day1 value at valid time T equals the "
    "run=(T-24h).floor('6h') single run's value at offset T-run hours, "
    "which is 24 + (T.hour % 6) hours -- exactly 24.0h ONLY when "
    "T.hour % 6 == 0 -- verified, not estimated (Open-Meteo's docs and "
    "D-04's own text both describe this as a flat 24h lead; both are "
    "incomplete). The stitching mechanism is identical in kind to the "
    "legacy 1-hour rule, offset by +24h."
)

# Match-rate floor below which a lead cell is considered NOT to exhibit the
# rule -- distinct from horizon_min, this catches a gate that would
# otherwise pass on data the rule does not actually hold for.
_MATCH_RATE_FLOOR: float = 0.9

# A small numeric tolerance (m/s) applied when comparing a single-run
# value against the corresponding bulk value.
#
# Live evidence, gathered during Plan 03-01's window re-verification
# (2026-09-29): comparing the two products' `wind_speed` values with exact
# float equality on the CORRECTED, empirically-verified window
# (`config.FORECAST_EXPERIMENT_WINDOW_START` onward) still reports a
# meaningful fraction of "mismatches" per lead cell (roughly 5-15%), but
# their magnitude is overwhelmingly tiny: a targeted inspection of 38
# exact-mismatches sampled across AUSTIN found the great majority
# clustered at 0.01-0.06 m/s -- exactly the two-decimal-place quantization
# noise expected when the SAME underlying value is independently rounded
# and re-serialized by two different API endpoints -- with a small number
# of genuinely larger differences (0.2-0.79 m/s, isolated to one anomalous
# run on one date) clearly separable from the rounding cluster. This
# matches the qualitative distinction 03-01-BOUNDARY-INVESTIGATION.md
# already drew between "two-decimal rounding at the margin" (small,
# scattered MAD) and "a different lead" (uniform, large MAD, 0.1-2.4 m/s
# in the genuinely-failing pre-boundary period). `_MATCH_TOLERANCE_MS` is
# set well above the observed rounding-noise ceiling (~0.06 m/s, a 1.6x
# margin) and well below the smallest genuinely-different value observed
# (~0.2 m/s, a 2x margin), so it absorbs representation noise without
# masking a real divergence. This does NOT touch `_MATCH_RATE_FLOOR` or
# `assert_supports_horizon`'s p05-lead logic -- it corrects how two floats
# sourced from independently-rounded JSON responses are determined to
# represent "the same value," which is a measurement-fidelity fix, not a
# relaxation of what the gate requires to pass.
_MATCH_TOLERANCE_MS: float = 0.1


def measure_lead_alignment(lat, lon, days, model=None) -> dict:
    """
    For each of `days` sampled dates, fetch the bulk series once, then fetch
    each of that day's four six-hourly runs (00Z/06Z/12Z/18Z). For every
    overlapping (run, lead) pair, compare the single-run value at that lead
    against the bulk value at the corresponding valid time on `wind_speed`
    -- the variable every correction arm in this phase depends on and the
    one 03-RESEARCH.md measured -- and accumulate per-lead exact-match
    counts, total-compared counts, and mean absolute difference.

    A `SingleRunUnavailable` (an archive-boundary condition -- a well
    -formed run the archive does not reach) increments `boundary_skips` and
    the sampling continues to the next run. Every other exception
    propagates -- it is a bug, not a boundary.

    Returns:
        A mapping with keys: `model`, `sampled_dates`, `per_lead` (a dict
        keyed by integer lead hour, each value `{"matched", "compared",
        "mad"}`), `boundary_skips`, and `lead_rule` (`LEAD_RULE_DESCRIPTION`).
    """
    if model is None:
        model = provider.FORECAST_MODEL_ID

    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    sampled_dates = _stratified_sample_days(days)

    per_lead: dict[int, dict[str, float]] = {
        h: {"matched": 0, "compared": 0, "mad_sum": 0.0} for h in range(modulus * 2)
    }
    boundary_skips = 0

    for date in sampled_dates:
        bulk = provider.fetch_historical_forecast(lat, lon, date, date)
        bulk = bulk.set_index("datetime_utc")["wind_speed"]

        for run_hour in range(0, 24, modulus):
            run_ts = pd.Timestamp(date, tz="UTC") + pd.Timedelta(hours=run_hour)
            try:
                # Request wind_speed only (03-RESEARCH.md: "compare on
                # wind_speed -- it is the variable every correction arm in
                # this phase depends on"), and truncate to 1 day
                # (forecast_days=1, live-confirmed null-free) -- this gate
                # never looks past lead modulus*2-1, so there is no reason
                # to pull the full 168-hour response and risk tripping the
                # null-completeness gate on out-of-horizon tail padding
                # this module was never going to use (Pitfall 3's
                # out-of-horizon-null behavior, live-observed here even on
                # wind_speed: 23/168 null past the model's real depth).
                single = provider.fetch_single_run(
                    lat, lon, run_ts,
                    hourly_vars=("wind_speed_10m",), forecast_days=1,
                )
            except provider.SingleRunUnavailable:
                boundary_skips += 1
                continue

            single = single.set_index("datetime_utc")["wind_speed"]

            for lead, valid_time in enumerate(single.index):
                if valid_time not in bulk.index:
                    continue
                bulk_value = bulk.loc[valid_time]
                single_value = single.loc[valid_time]
                if lead not in per_lead:
                    per_lead[lead] = {"matched": 0, "compared": 0, "mad_sum": 0.0}
                per_lead[lead]["compared"] += 1
                diff = abs(float(single_value) - float(bulk_value))
                per_lead[lead]["mad_sum"] += diff
                # Compared within `_MATCH_TOLERANCE_MS`, not exact equality
                # -- see that constant's docstring for the live evidence
                # distinguishing two-decimal rounding noise (~0.01-0.06 m/s)
                # from a genuinely different value (>=0.2 m/s).
                if diff <= _MATCH_TOLERANCE_MS:
                    per_lead[lead]["matched"] += 1

    per_lead_out = {}
    for lead, counts in sorted(per_lead.items()):
        compared = counts["compared"]
        mad = counts["mad_sum"] / compared if compared else 0.0
        per_lead_out[lead] = {
            "matched": counts["matched"],
            "compared": compared,
            "mad": mad,
        }

    return {
        "model": model,
        "sampled_dates": [str(d) for d in sampled_dates],
        "per_lead": per_lead_out,
        "boundary_skips": boundary_skips,
        "lead_rule": LEAD_RULE_DESCRIPTION,
    }


def _stratified_sample_days(days: int) -> list:
    """
    Sample `days` calendar dates stratified across the four astronomical
    seasons, bounded below by `config.FORECAST_EXPERIMENT_WINDOW_START` and
    above by "yesterday" (the bulk archive needs the day to be fully past).

    Bounded by `FORECAST_EXPERIMENT_WINDOW_START`, NOT
    `FORECAST_EXPERIMENT_VERIFIED_WINDOW_START` (03-01-BOUNDARY
    -INVESTIGATION.md, correcting this module's original assumption): the
    latter only marks where the Single-Runs archive becomes REACHABLE
    (2024-03-14), not where the bulk/single-run bit-identical rule this
    gate measures actually starts holding (2024-11-13). A live
    daily-resolution sweep found the rule fails uniformly for every date in
    that eight-month gap -- sampling there does not manufacture boundary
    skips (those are already counted and excluded separately via
    `SingleRunUnavailable`); it manufactures real, measured mismatches, and
    the gate correctly reports them as a failure that has nothing to do
    with a code defect. `FORECAST_EXPERIMENT_WINDOW_START` was corrected to
    the empirically-verified boundary for exactly this reason, so bounding
    the calibration sample by it keeps this gate's live measurement
    reproducing the same window the rest of the phase now scores against.
    """
    start = pd.Timestamp(config.FORECAST_EXPERIMENT_WINDOW_START, tz="UTC")
    end = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=2)
    if end <= start:
        end = start + pd.Timedelta(days=days)

    all_days = pd.date_range(start, end, freq="D")
    if len(all_days) <= days:
        return [d.date() for d in all_days]

    # Deterministic stratified pick: evenly spaced indices across the range.
    idx = np.linspace(0, len(all_days) - 1, num=days, dtype=int)
    return [all_days[i].date() for i in sorted(set(idx))]


def assert_supports_horizon(alignment: dict, horizon_min=None, hour_filter=None) -> dict:
    """
    The gate. Derives the lead in hours for each valid time under
    consideration as `hour % FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS`,
    restricted to `hour_filter` when one is supplied (`hour_filter` is a
    collection of the 0-23 UTC hours to include; here it selects which of
    `alignment["per_lead"]`'s keys are considered "leads under the modulus"
    versus "leads at or beyond it").

    Two independent failure modes are checked:

    1. The measured fifth-percentile lead over the considered rows is below
       `horizon_min`. Raises `ValueError` naming the measured p05 lead, the
       claimed horizon, and the hour set considered, with a remark that the
       caller most likely needs to pass the exact-lead hour filter rather
       than widen this gate.
    2. Any lead cell BELOW the stitching depth (`FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS`)
       shows a match rate below `_MATCH_RATE_FLOOR` -- a gate that passes on
       an alignment the rule does not actually hold for is worse than no
       gate. Raises `ValueError` naming the offending leads.

    On success, returns a mapping with `lead_min_hours`, `lead_p05_hours`,
    `lead_max_hours`, `rows_considered`, and `hour_filter`.
    """
    if horizon_min is None:
        horizon_min = config.FORECAST_HORIZON_MINUTES
    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS

    per_lead = alignment["per_lead"]

    # Failure mode 2: leads below the stitching depth must show a healthy
    # match rate, regardless of which hour_filter is applied -- a gate that
    # passes on unhealthy data is worse than no gate.
    unhealthy_leads = []
    for lead in range(modulus):
        counts = per_lead.get(lead, {"matched": 0, "compared": 0})
        compared = counts["compared"]
        matched = counts["matched"]
        if compared == 0:
            continue
        rate = matched / compared
        if rate < _MATCH_RATE_FLOOR:
            unhealthy_leads.append((lead, rate))
    if unhealthy_leads:
        offending = ", ".join(f"lead {lead} (match rate {rate:.2%})" for lead, rate in unhealthy_leads)
        raise ValueError(
            f"forecast_leadtime_calibration: the measured alignment does not "
            f"exhibit the deterministic rule at: {offending}. A gate that "
            f"passes on data the rule does not hold for is worse than no "
            f"gate -- investigate the alignment before proceeding."
        )

    # Build the per-row lead sample implied by the alignment's counts.
    #
    # Only raw leads BELOW the stitching depth (lead < modulus) are genuine
    # per-valid-time bulk-product leads: for a run initialized at run_hour
    # (always a multiple of modulus), a comparison at raw offset L gives
    # valid_time.hour == (run_hour + L) % 24, whose value modulo modulus is
    # simply L (since run_hour % modulus == 0 and L < modulus). A raw offset
    # AT OR BEYOND modulus is a comparison against a DIFFERENT, incorrect
    # run for that valid_time (the correct run under floor('6h') is a later
    # one) -- those entries exist only to prove the stitching-depth cutoff
    # (the unhealthy_leads check above) and must never be counted as if they
    # were the bulk product's own measured lead at that valid time.
    #
    # `hour_filter` is expressed as valid_time.hour values 0-23. Since a
    # genuine lead L (L < modulus) satisfies valid_time.hour % modulus == L,
    # restricting by hour_filter reduces to selecting L in
    # {h % modulus for h in hour_filter}.
    considered_leads = []
    for lead, counts in per_lead.items():
        if lead >= modulus:
            continue
        if hour_filter is not None:
            if lead not in {h % modulus for h in hour_filter}:
                continue
        considered_leads.append((lead, counts))

    # Expand into a per-row lead sample using the compared count as weight.
    lead_samples = []
    for lead, counts in considered_leads:
        lead_samples.extend([float(lead)] * counts["compared"])

    if not lead_samples:
        raise ValueError(
            "forecast_leadtime_calibration: no rows were compared under the "
            f"given hour_filter={hour_filter!r} -- cannot assert a horizon "
            "over an empty sample."
        )

    lead_array = np.array(lead_samples, dtype=float)
    lead_min = float(lead_array.min())
    lead_p05 = float(np.percentile(lead_array, 5))
    lead_max = float(lead_array.max())

    lead_p05_minutes = lead_p05 * 60.0
    if lead_p05_minutes < horizon_min:
        raise ValueError(
            f"forecast_leadtime_calibration: measured fifth-percentile lead "
            f"is {lead_p05:.2f} h ({lead_p05_minutes:.1f} min), which does "
            f"not support the claimed {horizon_min:.1f}-minute horizon, over "
            f"hour_filter={hour_filter!r}. The bulk product's lead "
            f"distribution genuinely spans multiple hours over the "
            f"unfiltered series -- the caller most likely needs to pass the "
            f"exact-lead hour filter (hour % {modulus} == "
            f"{config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER}) rather "
            f"than widen this gate."
        )

    return {
        "lead_min_hours": lead_min,
        "lead_p05_hours": lead_p05,
        "lead_max_hours": lead_max,
        "rows_considered": len(lead_samples),
        "hour_filter": list(hour_filter) if hour_filter is not None else None,
    }


# ──────────────────────────────────────────────────────────────────────────
# D-04's PRIMARY 24-hour offset-lead verification (Plan 03-03 Task 2)
# ──────────────────────────────────────────────────────────────────────────


def measure_previous_runs_alignment(lat, lon, dates, previous_day=None, model=None) -> dict:
    """
    For each of the EXPLICIT `dates` given, fetch the Previous-Runs series
    for that single day once, then fetch each of the FOUR six-hourly runs
    issued on the PRECEDING day (00Z/06Z/12Z/18Z) from the Single-Runs
    endpoint under the SAME pinned model.

    `dates` is an explicit list, never a day count -- unlike
    `_stratified_sample_days`, which is bounded by
    `config.FORECAST_EXPERIMENT_WINDOW_START` (2025-10-01, a window this
    model's Single-Runs archive comfortably covers), this model's
    Single-Runs archive is SHALLOW (reachable to roughly 2026-06-01 only --
    03-RESEARCH.md Environment Availability), so a caller must pick dates
    known to be reachable rather than relying on a day-count sampler that
    would assume 2024-depth and manufacture boundary skips.

    Why the PRECEDING day's runs: `previous_day1`'s value at a valid time
    `T` on `date` is stitched from the run issued at `(T - 24h).floor('6h')`
    -- since subtracting exactly 24h preserves `T`'s hour-of-day, that run
    was issued on `date`'s PRECEDING calendar day, at one of the same four
    six-hourly cycle hours.

    Each Single-Runs fetch requests wind_speed only (the variable every
    correction arm in this phase depends on, matching the legacy gate's own
    convention) and truncates to `forecast_days=2` so the completeness gate
    never has to reject out-of-horizon tail padding this function does not
    read, while still reaching offset ~29 (the top of the stitched band)
    for every one of the four issue hours.

    For every valid time present in BOTH series, the offset (the whole
    number of hours between the run's issue time and the valid time) is
    computed and the (bulk, single) pair is compared within
    `_MATCH_TOLERANCE_MS` (the SAME tolerance the legacy gate uses, for the
    SAME independently-rounded-JSON reason), accumulating per-offset
    matched/compared counts and mean absolute difference. A single run's
    response naturally straddles offsets well outside the genuine
    24-29h stitched band for a GIVEN valid time (e.g. the run issued at
    00Z also reaches offsets up to 47h) -- these "wrong-run" comparisons are
    intentionally retained (mirroring the legacy gate's own accumulate
    -across-all-runs-per-offset design) because they are what proves the
    24-29h band is the ONLY reliable one, exactly as the legacy gate's
    leads 6+ prove the cutoff at lead 6.

    A `SingleRunUnavailable` (an archive-boundary condition) increments
    `boundary_skips` and the sampling continues to the next run. Every
    other exception propagates -- it is a bug, not a boundary.

    Returns:
        A mapping with keys: `model`, `sampled_dates`, `per_offset` (a dict
        keyed by integer offset hour, each value `{"matched", "compared",
        "mad"}`), `boundary_skips`, and `lead_rule`
        (`PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION`).
    """
    if previous_day is None:
        previous_day = config.FORECAST_EXPERIMENT_PREVIOUS_DAY
    if model is None:
        model = provider.PREVIOUS_RUNS_MODEL_ID

    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    sampled_dates = [pd.Timestamp(d).date() for d in dates]

    per_offset: dict[int, dict[str, float]] = {}
    boundary_skips = 0

    for date in sampled_dates:
        bulk = provider.fetch_previous_runs(
            lat, lon, str(date), str(date), previous_day=previous_day,
        )
        bulk = bulk.set_index("datetime_utc")["wind_speed"]

        preceding_date = pd.Timestamp(date, tz="UTC") - pd.Timedelta(days=1)

        for run_hour in range(0, 24, modulus):
            run_ts = preceding_date + pd.Timedelta(hours=run_hour)
            try:
                # forecast_days=2 (03-RESEARCH.md: truncate so the
                # completeness gate never rejects out-of-horizon tail
                # padding this function was never going to read) still
                # reaches offset ~47, comfortably past the 24-29h stitched
                # band this function needs from every one of the four
                # issue hours.
                single = provider.fetch_single_run(
                    lat, lon, run_ts,
                    hourly_vars=("wind_speed_10m",), forecast_days=2,
                    model=model,
                )
            except provider.SingleRunUnavailable:
                boundary_skips += 1
                continue

            single = single.set_index("datetime_utc")["wind_speed"]

            for valid_time in single.index:
                if valid_time not in bulk.index:
                    continue
                offset = int((valid_time - run_ts) / pd.Timedelta(hours=1))
                bulk_value = bulk.loc[valid_time]
                single_value = single.loc[valid_time]
                if offset not in per_offset:
                    per_offset[offset] = {"matched": 0, "compared": 0, "mad_sum": 0.0}
                per_offset[offset]["compared"] += 1
                diff = abs(float(single_value) - float(bulk_value))
                per_offset[offset]["mad_sum"] += diff
                if diff <= _MATCH_TOLERANCE_MS:
                    per_offset[offset]["matched"] += 1

    per_offset_out = {}
    for offset, counts in sorted(per_offset.items()):
        compared = counts["compared"]
        mad = counts["mad_sum"] / compared if compared else 0.0
        per_offset_out[offset] = {
            "matched": counts["matched"],
            "compared": compared,
            "mad": mad,
        }

    return {
        "model": model,
        "sampled_dates": [str(d) for d in sampled_dates],
        "per_offset": per_offset_out,
        "boundary_skips": boundary_skips,
        "lead_rule": PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION,
    }


def assert_exact_offset_lead(alignment: dict, lead_hours=None, hour_filter=None) -> dict:
    """
    The PRIMARY gate for D-04's 24-hour offset rule. Two independent
    failure modes, mirroring `assert_supports_horizon`'s structure:

    1. Any offset cell in the STITCHED BAND -- `[lead_hours, lead_hours +
       modulus - 1]`, i.e. 24 through 29 for the default 24-hour lead --
       whose match rate falls below `_MATCH_RATE_FLOOR` raises, naming the
       offending offsets. A gate that passes on data the rule does not hold
       for is worse than no gate. Checked regardless of `hour_filter`.
    2. The measured lead over the considered rows is not UNIFORMLY
       `lead_hours`. The per-row lead sample is built from the offsets in
       the stitched band, restricted by `hour_filter` when supplied, where
       a valid hour `h` maps to offset `lead_hours + (h % modulus)`. Raises
       when the sample's minimum and maximum are not BOTH exactly
       `lead_hours`, naming the observed span, the claimed lead, and the
       hour set considered, with the same remark
       `assert_supports_horizon` carries: the caller most likely needs the
       exact-lead hour filter rather than a widened gate.

    Unlike `assert_supports_horizon`, this gate does NOT accept a
    fifth-percentile softening: this rule is exactly-or-not (a
    stitched-run offset either IS the claimed lead or it is a different,
    wrong-run offset), and a percentile would let a minority of 25
    -to-29-hour rows through unnoticed -- exactly the silent lead-smear
    RESEARCH Pitfall 1 exists to prevent.

    On success, returns a mapping with `lead_min_hours`, `lead_max_hours`,
    `rows_considered`, and `hour_filter`.
    """
    if lead_hours is None:
        lead_hours = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS
    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS

    per_offset = alignment["per_offset"]
    stitched_band = range(lead_hours, lead_hours + modulus)

    # Failure mode 1: every offset in the stitched band must show a healthy
    # match rate, regardless of hour_filter -- a gate that passes on
    # unhealthy data is worse than no gate.
    unhealthy_offsets = []
    for offset in stitched_band:
        counts = per_offset.get(offset, {"matched": 0, "compared": 0})
        compared = counts["compared"]
        matched = counts["matched"]
        if compared == 0:
            continue
        rate = matched / compared
        if rate < _MATCH_RATE_FLOOR:
            unhealthy_offsets.append((offset, rate))
    if unhealthy_offsets:
        offending = ", ".join(
            f"offset {offset} (match rate {rate:.2%})" for offset, rate in unhealthy_offsets
        )
        raise ValueError(
            f"forecast_leadtime_calibration: the measured 24-hour-offset "
            f"alignment does not exhibit the deterministic rule at: "
            f"{offending}. A gate that passes on data the rule does not "
            f"hold for is worse than no gate -- investigate the alignment "
            f"before proceeding."
        )

    # Failure mode 2: the per-row lead sample, restricted to the stitched
    # band and (when given) hour_filter, must be UNIFORMLY lead_hours.
    considered_offsets = []
    for offset in stitched_band:
        counts = per_offset.get(offset)
        if counts is None:
            continue
        if hour_filter is not None:
            allowed_offsets = {lead_hours + (h % modulus) for h in hour_filter}
            if offset not in allowed_offsets:
                continue
        considered_offsets.append((offset, counts))

    lead_samples = []
    for offset, counts in considered_offsets:
        lead_samples.extend([float(offset)] * counts["compared"])

    if not lead_samples:
        raise ValueError(
            "forecast_leadtime_calibration: no rows were compared under the "
            f"given hour_filter={hour_filter!r} -- cannot assert a 24-hour "
            "offset lead over an empty sample."
        )

    lead_array = np.array(lead_samples, dtype=float)
    lead_min = float(lead_array.min())
    lead_max = float(lead_array.max())

    if lead_min != float(lead_hours) or lead_max != float(lead_hours):
        remainder = config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER
        raise ValueError(
            f"forecast_leadtime_calibration: measured lead spans "
            f"{lead_min:.1f}h-{lead_max:.1f}h over hour_filter={hour_filter!r}, "
            f"not uniformly the claimed {float(lead_hours):.1f}h lead. The "
            f"Previous-Runs product's lead distribution genuinely spans "
            f"multiple hours over the unfiltered series -- the caller most "
            f"likely needs to pass the exact-lead hour filter (hour % "
            f"{modulus} == {remainder}) rather than widen this gate."
        )

    return {
        "lead_min_hours": lead_min,
        "lead_max_hours": lead_max,
        "rows_considered": len(lead_samples),
        "hour_filter": list(hour_filter) if hour_filter is not None else None,
    }


def _default_previous_runs_dates(count: int = 4) -> list:
    """
    `count` dates spaced across the most recent reachable months, computed
    relative to "yesterday" (UTC) so the default set never goes stale.
    Bounded to RECENT dates only -- unlike `_stratified_sample_days`, this
    is NOT a wide historical sampler: the Single-Runs archive for the
    pinned Previous-Runs model (`gfs_seamless`) is SHALLOW (03-RESEARCH.md
    Environment Availability: live-verified reachable to roughly
    2026-06-01; a probe to 2025-12-01 returned HTTP 400), so a `--days 30`
    -style sampler expecting 2024 depth would manufacture boundary skips
    rather than measurements.
    """
    yesterday = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=1)
    offsets_days = (10, 35, 60, 85)[:count]
    return [(yesterday - pd.Timedelta(days=d)).date() for d in offsets_days]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="D-01's legacy 1-hour hard gate, or (via --previous-runs) "
        "D-04's PRIMARY 24-hour offset-lead check: measure a forecast "
        "product's lead time against exact single runs and assert whether "
        "the measured lead supports the claimed horizon."
    )
    parser.add_argument(
        "--city", choices=sorted(config.CITY_COORDINATES), default=None,
        help="City to calibrate. Default: every city.",
    )
    parser.add_argument(
        "--days", type=int, default=config.FORECAST_EXPERIMENT_CALIBRATION_SAMPLE_DAYS,
        help="Number of stratified days to sample (legacy 1-hour gate only).",
    )
    parser.add_argument(
        "--previous-runs", action="store_true",
        help="Run D-04's PRIMARY 24-hour offset-lead verification instead "
        "of the legacy 1-hour gate, over a small explicit list of recent "
        "dates (see _default_previous_runs_dates -- the Single-Runs "
        "archive for the pinned Previous-Runs model is shallow).",
    )
    args = parser.parse_args(argv)

    cities = [args.city] if args.city else sorted(config.CITY_COORDINATES)

    os.makedirs(config.FORECAST_EXPERIMENT_CACHE_DIR, exist_ok=True)
    report_path = os.path.join(
        config.FORECAST_EXPERIMENT_CACHE_DIR, "leadtime_calibration_report.json"
    )
    # Read any existing report so a legacy-gate run and a --previous-runs
    # run, invoked as separate CLI calls against the same report file,
    # never clobber each other's top-level keys.
    report = {}
    if os.path.exists(report_path):
        try:
            with open(report_path) as fh:
                report = json.load(fh)
        except (ValueError, OSError):
            report = {}

    summary_lines = []

    if args.previous_runs:
        modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
        remainder = config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER
        lead_hours = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS
        exact_lead_hour_filter = [h for h in range(24) if h % modulus == remainder]
        dates = [str(d) for d in _default_previous_runs_dates()]

        for city in cities:
            lat, lon = config.CITY_COORDINATES[city]
            print(f"\n{city}: sampling {len(dates)} recent dates {dates} for the 24h offset rule...")
            alignment = measure_previous_runs_alignment(lat, lon, dates)

            print(f"{'offset_h':>8}{'matched':>10}{'compared':>10}{'match_rate':>12}{'mad':>10}")
            for offset in sorted(alignment["per_offset"]):
                counts = alignment["per_offset"][offset]
                compared = counts["compared"]
                rate = counts["matched"] / compared if compared else float("nan")
                print(
                    f"{offset:>8}{counts['matched']:>10}{compared:>10}"
                    f"{rate:>12.2%}{counts['mad']:>10.4f}" if compared
                    else f"{offset:>8}{counts['matched']:>10}{compared:>10}{'--':>12}{'--':>10}"
                )
            print(f"boundary_skips: {alignment['boundary_skips']}")

            unfiltered_verdict = "FAIL"
            unfiltered_detail = ""
            try:
                assert_exact_offset_lead(alignment, lead_hours=lead_hours)
                unfiltered_verdict = "PASS (unexpected -- gate may have been relaxed)"
            except ValueError as exc:
                unfiltered_detail = str(exc)
            print(f"unfiltered gate: {unfiltered_verdict}")
            if unfiltered_detail:
                print(f"  {unfiltered_detail}")

            filtered_verdict = "FAIL"
            filtered_detail = ""
            filtered_result = None
            try:
                filtered_result = assert_exact_offset_lead(
                    alignment, lead_hours=lead_hours,
                    hour_filter=exact_lead_hour_filter,
                )
                filtered_verdict = "PASS"
            except ValueError as exc:
                filtered_detail = str(exc)
            print(f"filtered gate (hour % {modulus} == {remainder}): {filtered_verdict}")
            if filtered_result:
                print(
                    f"  min={filtered_result['lead_min_hours']:.2f}h "
                    f"max={filtered_result['lead_max_hours']:.2f}h "
                    f"rows={filtered_result['rows_considered']}"
                )
            if filtered_detail:
                print(f"  {filtered_detail}")

            report.setdefault(city, {})["previous_runs"] = {
                "alignment": alignment,
                "unfiltered_verdict": unfiltered_verdict,
                "filtered_verdict": filtered_verdict,
                "filtered_result": filtered_result,
            }
            summary_lines.append(
                f"SUMMARY: {city} sampled_dates={len(alignment['sampled_dates'])} "
                f"boundary_skips={alignment['boundary_skips']} "
                f"unfiltered={unfiltered_verdict} filtered={filtered_verdict}"
            )
    else:
        modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
        remainder = config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER
        exact_lead_hour_filter = [h for h in range(24) if h % modulus == remainder]

        for city in cities:
            lat, lon = config.CITY_COORDINATES[city]
            print(f"\n{city}: sampling {args.days} days...")
            alignment = measure_lead_alignment(lat, lon, args.days)

            print(f"{'lead_h':>8}{'matched':>10}{'compared':>10}{'match_rate':>12}{'mad':>10}")
            for lead in sorted(alignment["per_lead"]):
                counts = alignment["per_lead"][lead]
                compared = counts["compared"]
                rate = counts["matched"] / compared if compared else float("nan")
                print(
                    f"{lead:>8}{counts['matched']:>10}{compared:>10}"
                    f"{rate:>12.2%}{counts['mad']:>10.4f}" if compared
                    else f"{lead:>8}{counts['matched']:>10}{compared:>10}{'--':>12}{'--':>10}"
                )
            print(f"boundary_skips: {alignment['boundary_skips']}")

            unfiltered_verdict = "FAIL"
            unfiltered_detail = ""
            try:
                assert_supports_horizon(alignment, horizon_min=config.FORECAST_HORIZON_MINUTES)
                unfiltered_verdict = "PASS (unexpected -- gate may have been relaxed)"
            except ValueError as exc:
                unfiltered_detail = str(exc)
            print(f"unfiltered gate: {unfiltered_verdict}")
            if unfiltered_detail:
                print(f"  {unfiltered_detail}")

            filtered_verdict = "FAIL"
            filtered_detail = ""
            filtered_result = None
            try:
                filtered_result = assert_supports_horizon(
                    alignment, horizon_min=config.FORECAST_HORIZON_MINUTES,
                    hour_filter=exact_lead_hour_filter,
                )
                filtered_verdict = "PASS"
            except ValueError as exc:
                filtered_detail = str(exc)
            print(f"filtered gate (hour % {modulus} == {remainder}): {filtered_verdict}")
            if filtered_result:
                print(
                    f"  min={filtered_result['lead_min_hours']:.2f}h "
                    f"p05={filtered_result['lead_p05_hours']:.2f}h "
                    f"max={filtered_result['lead_max_hours']:.2f}h "
                    f"rows={filtered_result['rows_considered']}"
                )
            if filtered_detail:
                print(f"  {filtered_detail}")

            report.setdefault(city, {})
            report[city]["alignment"] = alignment
            report[city]["unfiltered_verdict"] = unfiltered_verdict
            report[city]["filtered_verdict"] = filtered_verdict
            report[city]["filtered_result"] = filtered_result
            summary_lines.append(
                f"SUMMARY: {city} sampled_days={len(alignment['sampled_dates'])} "
                f"boundary_skips={alignment['boundary_skips']} "
                f"unfiltered={unfiltered_verdict} filtered={filtered_verdict}"
            )

    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"\ncalibration report written to {report_path}")

    print()
    for line in summary_lines:
        print(line)


if __name__ == "__main__":
    main()
