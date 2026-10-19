"""
Tests for backend/forecast_leadtime_calibration.py (D-01's hard gate).

Every test is network-free: monkeypatch the two fetch functions on the
calibration module's imported `provider` object, following the convention
`anomaly_training_test.py`/`forecast_training_test.py` use for mocking a
fetch one layer up. Module-level plain-assert functions, no test classes.

Written from the plan's <behavior> block; confirmed to fail before the
module existed (RED), per this module's tdd="true" task.
"""

import numpy as np
import pandas as pd
import pytest

import config
import open_meteo_forecast_provider as provider
import forecast_leadtime_calibration as cal


MOD = config.FORECAST_EXPERIMENT_LEAD_FILTER_MODULUS
REM = config.FORECAST_EXPERIMENT_LEAD_FILTER_REMAINDER


def _healthy_alignment():
    """
    A synthetic alignment reproducing the measured shape: match at leads 0
    through modulus-1, mismatch at modulus through modulus+3.
    """
    per_lead = {h: {"matched": 40, "compared": 40, "mad": 0.0} for h in range(MOD)}
    per_lead.update(
        {h: {"matched": 0, "compared": 40, "mad": 0.31} for h in range(MOD, MOD + 4)}
    )
    return {
        "model": "ecmwf_ifs",
        "sampled_dates": ["2025-07-01"],
        "per_lead": per_lead,
        "boundary_skips": 0,
        "lead_rule": cal.LEAD_RULE_DESCRIPTION,
    }


# ──────────────────────────────────────────────────────────────────────────
# assert_supports_horizon -- both directions of the gate
# ──────────────────────────────────────────────────────────────────────────


def test_gate_fails_on_unfiltered_healthy_alignment():
    alignment = _healthy_alignment()

    with pytest.raises(ValueError) as excinfo:
        cal.assert_supports_horizon(alignment, horizon_min=60.0)

    assert "60" in str(excinfo.value)


def test_gate_passes_on_exact_lead_filtered_healthy_alignment():
    alignment = _healthy_alignment()
    hour_filter = [h for h in range(24) if h % MOD == REM]

    result = cal.assert_supports_horizon(alignment, horizon_min=60.0, hour_filter=hour_filter)

    assert result["lead_min_hours"] == 1.0
    assert result["lead_p05_hours"] == 1.0
    assert result["lead_max_hours"] == 1.0


def test_gate_raises_when_lead_below_floor_matches_poorly_even_filtered():
    alignment = _healthy_alignment()
    alignment["per_lead"][REM] = {"matched": 2, "compared": 40, "mad": 1.2}
    hour_filter = [h for h in range(24) if h % MOD == REM]

    with pytest.raises(ValueError) as excinfo:
        cal.assert_supports_horizon(alignment, horizon_min=60.0, hour_filter=hour_filter)

    assert f"lead {REM}" in str(excinfo.value)


def test_gate_raises_naming_offending_lead_on_unfiltered_unhealthy_alignment():
    alignment = _healthy_alignment()
    alignment["per_lead"][3] = {"matched": 1, "compared": 40, "mad": 1.5}

    with pytest.raises(ValueError) as excinfo:
        cal.assert_supports_horizon(alignment, horizon_min=60.0)

    assert "lead 3" in str(excinfo.value)


# ──────────────────────────────────────────────────────────────────────────
# measure_lead_alignment -- boundary skips, malformed runs
# ──────────────────────────────────────────────────────────────────────────


def _bulk_frame(date: str, n_hours: int = 24):
    idx = pd.date_range(f"{date}T00:00:00Z", periods=n_hours, freq="h")
    return pd.DataFrame({"datetime_utc": idx, "wind_speed": [5.0 + (i % 6) for i in range(n_hours)]})


def _single_run_frame(run_ts, n_hours: int = 6, values=None):
    idx = pd.date_range(run_ts, periods=n_hours, freq="h")
    if values is None:
        values = [5.0 + (i % 6) for i in range(n_hours)]
    return pd.DataFrame({"datetime_utc": idx, "wind_speed": values})


def test_measure_lead_alignment_counts_boundary_skip_and_continues(monkeypatch):
    date = "2025-07-01"

    def fake_bulk(lat, lon, start, end):
        return _bulk_frame(date)

    calls = {"n": 0}

    def fake_single(lat, lon, run, hourly_vars=None, forecast_days=None):
        calls["n"] += 1
        run_ts = pd.Timestamp(run)
        if run_ts.hour == 6:
            raise provider.SingleRunUnavailable("not available")
        return _single_run_frame(run_ts)

    monkeypatch.setattr(cal.provider, "fetch_historical_forecast", fake_bulk)
    monkeypatch.setattr(cal.provider, "fetch_single_run", fake_single)
    monkeypatch.setattr(
        cal, "_stratified_sample_days", lambda days: [pd.Timestamp(date).date()]
    )

    alignment = cal.measure_lead_alignment(30.27, -97.74, days=1)

    assert alignment["boundary_skips"] == 1
    assert calls["n"] == 4  # 4 runs sampled that day, one skipped
    assert alignment["lead_rule"] == cal.LEAD_RULE_DESCRIPTION


def test_measure_lead_alignment_propagates_malformed_run_error(monkeypatch):
    date = "2025-07-01"

    def fake_bulk(lat, lon, start, end):
        return _bulk_frame(date)

    def fake_single(lat, lon, run, hourly_vars=None, forecast_days=None):
        raise ValueError("cannot parse run timestamp")

    monkeypatch.setattr(cal.provider, "fetch_historical_forecast", fake_bulk)
    monkeypatch.setattr(cal.provider, "fetch_single_run", fake_single)
    monkeypatch.setattr(
        cal, "_stratified_sample_days", lambda days: [pd.Timestamp(date).date()]
    )

    with pytest.raises(ValueError, match="cannot parse run timestamp"):
        cal.measure_lead_alignment(30.27, -97.74, days=1)


def test_measure_lead_alignment_reports_per_lead_match_and_compared_counts(monkeypatch):
    date = "2025-07-01"
    bulk = _bulk_frame(date)

    def fake_bulk(lat, lon, start, end):
        return bulk.copy()

    def fake_single(lat, lon, run, hourly_vars=None, forecast_days=None):
        run_ts = pd.Timestamp(run)
        # matches bulk exactly for the first MOD hours, diverges after
        idx = pd.date_range(run_ts, periods=MOD + 2, freq="h")
        vals = []
        for i, ts in enumerate(idx):
            if ts in set(bulk["datetime_utc"]) and i < MOD:
                vals.append(float(bulk.set_index("datetime_utc").loc[ts, "wind_speed"]))
            else:
                vals.append(999.0)
        return pd.DataFrame({"datetime_utc": idx, "wind_speed": vals})

    monkeypatch.setattr(cal.provider, "fetch_historical_forecast", fake_bulk)
    monkeypatch.setattr(cal.provider, "fetch_single_run", fake_single)
    monkeypatch.setattr(
        cal, "_stratified_sample_days", lambda days: [pd.Timestamp(date).date()]
    )

    alignment = cal.measure_lead_alignment(30.27, -97.74, days=1)

    for lead in range(MOD):
        assert alignment["per_lead"][lead]["matched"] == alignment["per_lead"][lead]["compared"]
    assert alignment["per_lead"][MOD]["matched"] == 0


def test_measure_lead_alignment_tolerates_rounding_noise_within_tolerance(monkeypatch):
    """
    A value within `_MATCH_TOLERANCE_MS` of the bulk value counts as
    matched -- live evidence (Plan 03-01 window re-verification) found
    two-decimal rounding noise of ~0.01-0.06 m/s between the two
    independently-serialized API responses even for values that are, for
    the phase's purposes, the same underlying model output.
    """
    date = "2025-07-01"
    bulk = _bulk_frame(date)

    def fake_bulk(lat, lon, start, end):
        return bulk.copy()

    def fake_single(lat, lon, run, hourly_vars=None, forecast_days=None):
        run_ts = pd.Timestamp(run)
        idx = pd.date_range(run_ts, periods=MOD, freq="h")
        vals = []
        for ts in idx:
            base = float(bulk.set_index("datetime_utc").loc[ts, "wind_speed"])
            vals.append(base + 0.05)  # within tolerance (0.1)
        return pd.DataFrame({"datetime_utc": idx, "wind_speed": vals})

    monkeypatch.setattr(cal.provider, "fetch_historical_forecast", fake_bulk)
    monkeypatch.setattr(cal.provider, "fetch_single_run", fake_single)
    monkeypatch.setattr(
        cal, "_stratified_sample_days", lambda days: [pd.Timestamp(date).date()]
    )

    alignment = cal.measure_lead_alignment(30.27, -97.74, days=1)

    for lead in range(MOD):
        assert alignment["per_lead"][lead]["matched"] == alignment["per_lead"][lead]["compared"]


def test_measure_lead_alignment_still_rejects_values_beyond_tolerance(monkeypatch):
    """A value outside `_MATCH_TOLERANCE_MS` still counts as a mismatch --
    the tolerance absorbs rounding noise, it does not widen the rule."""
    date = "2025-07-01"
    bulk = _bulk_frame(date)

    def fake_bulk(lat, lon, start, end):
        return bulk.copy()

    def fake_single(lat, lon, run, hourly_vars=None, forecast_days=None):
        run_ts = pd.Timestamp(run)
        idx = pd.date_range(run_ts, periods=MOD, freq="h")
        vals = []
        for ts in idx:
            base = float(bulk.set_index("datetime_utc").loc[ts, "wind_speed"])
            vals.append(base + 0.2)  # beyond tolerance (0.1)
        return pd.DataFrame({"datetime_utc": idx, "wind_speed": vals})

    monkeypatch.setattr(cal.provider, "fetch_historical_forecast", fake_bulk)
    monkeypatch.setattr(cal.provider, "fetch_single_run", fake_single)
    monkeypatch.setattr(
        cal, "_stratified_sample_days", lambda days: [pd.Timestamp(date).date()]
    )

    alignment = cal.measure_lead_alignment(30.27, -97.74, days=1)

    for lead in range(MOD):
        assert alignment["per_lead"][lead]["matched"] == 0


# ──────────────────────────────────────────────────────────────────────────
# D-04's PRIMARY 24-hour offset-lead verification (Plan 03-03 Task 2)
# ──────────────────────────────────────────────────────────────────────────

PRIMARY_LEAD = config.FORECAST_EXPERIMENT_PRIMARY_LEAD_HOURS
PRIMARY_REM = config.FORECAST_EXPERIMENT_24H_LEAD_FILTER_REMAINDER


def test_previous_runs_and_legacy_rule_descriptions_are_distinct():
    assert cal.PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION != cal.LEAD_RULE_DESCRIPTION
    assert isinstance(cal.PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION, str)
    assert isinstance(cal.LEAD_RULE_DESCRIPTION, str)


def _healthy_offset_alignment():
    """
    A synthetic 24-hour-offset alignment reproducing the measured shape:
    match at every offset in the stitched band [PRIMARY_LEAD, PRIMARY_LEAD
    + MOD - 1] (24-29 for the default lead/modulus).
    """
    per_offset = {
        PRIMARY_LEAD + k: {"matched": 40, "compared": 40, "mad": 0.0} for k in range(MOD)
    }
    return {
        "model": "gfs_seamless",
        "sampled_dates": ["2026-09-20"],
        "per_offset": per_offset,
        "boundary_skips": 0,
        "lead_rule": cal.PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION,
    }


def test_offset_gate_passes_on_exact_lead_filtered_healthy_alignment():
    alignment = _healthy_offset_alignment()
    hour_filter = [h for h in range(24) if h % MOD == PRIMARY_REM]

    result = cal.assert_exact_offset_lead(alignment, hour_filter=hour_filter)

    assert result["lead_min_hours"] == float(PRIMARY_LEAD)
    assert result["lead_max_hours"] == float(PRIMARY_LEAD)


def test_offset_gate_fails_on_unfiltered_healthy_alignment():
    alignment = _healthy_offset_alignment()

    with pytest.raises(ValueError) as excinfo:
        cal.assert_exact_offset_lead(alignment)

    message = str(excinfo.value)
    assert f"{float(PRIMARY_LEAD):.1f}" in message or str(PRIMARY_LEAD) in message
    assert f"{float(PRIMARY_LEAD + MOD - 1):.1f}" in message


def test_offset_gate_raises_when_offset_below_stitching_depth_matches_poorly_even_filtered():
    alignment = _healthy_offset_alignment()
    exact_offset = PRIMARY_LEAD + PRIMARY_REM
    alignment["per_offset"][exact_offset] = {"matched": 2, "compared": 40, "mad": 1.2}
    hour_filter = [h for h in range(24) if h % MOD == PRIMARY_REM]

    with pytest.raises(ValueError) as excinfo:
        cal.assert_exact_offset_lead(alignment, hour_filter=hour_filter)

    assert f"offset {exact_offset}" in str(excinfo.value)


def test_offset_gate_raises_naming_offending_offset_on_unfiltered_unhealthy_alignment():
    alignment = _healthy_offset_alignment()
    bad_offset = PRIMARY_LEAD + 3
    alignment["per_offset"][bad_offset] = {"matched": 1, "compared": 40, "mad": 1.5}

    with pytest.raises(ValueError) as excinfo:
        cal.assert_exact_offset_lead(alignment)

    assert f"offset {bad_offset}" in str(excinfo.value)


def test_offset_gate_raises_on_empty_sample_under_hour_filter():
    alignment = _healthy_offset_alignment()
    # A filter selecting only offsets far outside the stitched band leaves
    # no compared rows.
    with pytest.raises(ValueError):
        cal.assert_exact_offset_lead(alignment, hour_filter=[])


def _previous_runs_bulk_frame(date: str, n_hours: int = 24):
    idx = pd.date_range(f"{date}T00:00:00Z", periods=n_hours, freq="h")
    return pd.DataFrame({"datetime_utc": idx, "wind_speed": [5.0 + (i % 6) for i in range(n_hours)]})


def test_measure_previous_runs_alignment_counts_boundary_skip_and_continues(monkeypatch):
    date = "2026-09-20"
    bulk = _previous_runs_bulk_frame(date)

    def fake_bulk(lat, lon, start, end, previous_day=None):
        return bulk.copy()

    calls = {"n": 0}

    def fake_single(lat, lon, run, hourly_vars=None, forecast_days=None, model=None):
        calls["n"] += 1
        run_ts = pd.Timestamp(run)
        if run_ts.hour == 6:
            raise provider.SingleRunUnavailable("not available")
        idx = pd.date_range(run_ts, periods=48, freq="h")
        return pd.DataFrame({"datetime_utc": idx, "wind_speed": [5.0] * 48})

    monkeypatch.setattr(cal.provider, "fetch_previous_runs", fake_bulk)
    monkeypatch.setattr(cal.provider, "fetch_single_run", fake_single)

    alignment = cal.measure_previous_runs_alignment(30.27, -97.74, dates=[date])

    assert alignment["boundary_skips"] == 1
    assert calls["n"] == 4  # 4 preceding-day runs sampled, one skipped
    assert alignment["lead_rule"] == cal.PREVIOUS_RUNS_LEAD_RULE_DESCRIPTION
    assert alignment["sampled_dates"] == [date]


def test_measure_previous_runs_alignment_propagates_non_boundary_error(monkeypatch):
    date = "2026-09-20"
    bulk = _previous_runs_bulk_frame(date)

    def fake_bulk(lat, lon, start, end, previous_day=None):
        return bulk.copy()

    def fake_single(lat, lon, run, hourly_vars=None, forecast_days=None, model=None):
        raise ValueError("cannot parse run timestamp")

    monkeypatch.setattr(cal.provider, "fetch_previous_runs", fake_bulk)
    monkeypatch.setattr(cal.provider, "fetch_single_run", fake_single)

    with pytest.raises(ValueError, match="cannot parse run timestamp"):
        cal.measure_previous_runs_alignment(30.27, -97.74, dates=[date])


def test_measure_previous_runs_alignment_reports_per_offset_match_and_compared_counts(monkeypatch):
    date = "2026-09-20"
    bulk = _previous_runs_bulk_frame(date)
    bulk_indexed = bulk.set_index("datetime_utc")["wind_speed"]

    def fake_bulk(lat, lon, start, end, previous_day=None):
        return bulk.copy()

    def fake_single(lat, lon, run, hourly_vars=None, forecast_days=None, model=None):
        run_ts = pd.Timestamp(run)
        idx = pd.date_range(run_ts, periods=48, freq="h")
        vals = []
        for ts in idx:
            offset = int((ts - run_ts) / pd.Timedelta(hours=1))
            if ts in bulk_indexed.index and PRIMARY_LEAD <= offset < PRIMARY_LEAD + MOD:
                vals.append(float(bulk_indexed.loc[ts]))
            else:
                vals.append(999.0)
        return pd.DataFrame({"datetime_utc": idx, "wind_speed": vals})

    monkeypatch.setattr(cal.provider, "fetch_previous_runs", fake_bulk)
    monkeypatch.setattr(cal.provider, "fetch_single_run", fake_single)

    alignment = cal.measure_previous_runs_alignment(30.27, -97.74, dates=[date])

    for offset in range(PRIMARY_LEAD, PRIMARY_LEAD + MOD):
        counts = alignment["per_offset"][offset]
        assert counts["compared"] > 0
        assert counts["matched"] == counts["compared"]


def test_measure_previous_runs_alignment_accepts_explicit_dates_not_a_day_count():
    import inspect

    sig = inspect.signature(cal.measure_previous_runs_alignment)
    assert "dates" in sig.parameters
    assert "days" not in sig.parameters


# ──────────────────────────────────────────────────────────────────────────
# Import-time no-side-effects
# ──────────────────────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects():
    import importlib

    importlib.reload(cal)
