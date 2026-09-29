"""
Lead-Time Calibration Gate (D-01's hard gate, Phase 3 experiment)
===================================================================
This module is a **verification of a deterministic rule**, not an
estimation of a fuzzy distribution. With `models=ecmwf_ifs` pinned on both
Open-Meteo endpoints, the bulk Historical Forecast product's value at valid
time `T` is expected to equal the `run = T.floor('6h')` single run's value
at lead `T.hour % 6`, because the bulk product stitches exactly the first
six hours of each six-hourly ECMWF IFS run (03-RESEARCH.md Pattern 2, live
-measured bit-identical at leads 0-5, divergent at lead >= 6, across three
cities and three seasons).

This gate is EXPECTED TO FAIL when applied to the unfiltered series: the
bulk product's lead distribution over all hours is uniform on {0,1,2,3,4,5},
so its fifth-percentile lead is 0 h, which cannot support a 60-minute claim.
That failure is the correct measured outcome, not a defect -- the gate must
NEVER be relaxed, widened, or otherwise tuned until it passes on the
unfiltered series. It passes only on the `hour % 6 == 1` subset, where the
lead is exactly 1 h on every row.

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

# Match-rate floor below which a lead cell is considered NOT to exhibit the
# rule -- distinct from horizon_min, this catches a gate that would
# otherwise pass on data the rule does not actually hold for.
_MATCH_RATE_FLOOR: float = 0.9


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
                single = provider.fetch_single_run(lat, lon, run_ts)
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
                per_lead[lead]["mad_sum"] += abs(float(single_value) - float(bulk_value))
                if float(single_value) == float(bulk_value):
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
    seasons, bounded below by `config.FORECAST_EXPERIMENT_VERIFIED_WINDOW_START`
    (the archive does not reach earlier for this model, so sampling earlier
    only manufactures boundary skips) and above by "yesterday" (the bulk
    archive needs the day to be fully past).
    """
    start = pd.Timestamp(config.FORECAST_EXPERIMENT_VERIFIED_WINDOW_START, tz="UTC")
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="D-01's hard gate: measure the bulk forecast product's "
        "lead time against exact single runs and assert whether the "
        "measured lead supports the claimed horizon."
    )
    parser.add_argument(
        "--city", choices=sorted(config.CITY_COORDINATES), default=None,
        help="City to calibrate. Default: every city.",
    )
    parser.add_argument(
        "--days", type=int, default=config.FORECAST_EXPERIMENT_CALIBRATION_SAMPLE_DAYS,
        help="Number of stratified days to sample.",
    )
    args = parser.parse_args(argv)

    cities = [args.city] if args.city else sorted(config.CITY_COORDINATES)
    modulus = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
    remainder = config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER
    exact_lead_hour_filter = [h for h in range(24) if h % modulus == remainder]

    report = {}
    summary_lines = []

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

        report[city] = {
            "alignment": alignment,
            "unfiltered_verdict": unfiltered_verdict,
            "filtered_verdict": filtered_verdict,
            "filtered_result": filtered_result,
        }
        summary_lines.append(
            f"SUMMARY: {city} sampled_days={len(alignment['sampled_dates'])} "
            f"boundary_skips={alignment['boundary_skips']} "
            f"unfiltered={unfiltered_verdict} filtered={filtered_verdict}"
        )

    os.makedirs(config.FORECAST_EXPERIMENT_CACHE_DIR, exist_ok=True)
    report_path = os.path.join(
        config.FORECAST_EXPERIMENT_CACHE_DIR, "leadtime_calibration_report.json"
    )
    with open(report_path, "w") as fh:
        json.dump(report, fh, indent=2, default=str)
    print(f"\ncalibration report written to {report_path}")

    print()
    for line in summary_lines:
        print(line)


if __name__ == "__main__":
    main()
