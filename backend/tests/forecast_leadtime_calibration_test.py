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

    def fake_single(lat, lon, run):
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

    def fake_single(lat, lon, run):
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

    def fake_single(lat, lon, run):
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


# ──────────────────────────────────────────────────────────────────────────
# Import-time no-side-effects
# ──────────────────────────────────────────────────────────────────────────


def test_module_import_has_no_side_effects():
    import importlib

    importlib.reload(cal)
