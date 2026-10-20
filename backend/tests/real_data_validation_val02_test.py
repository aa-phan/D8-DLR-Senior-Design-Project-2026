"""
Tests for the VAL-02 part of backend/real_data_validation.py: how well the live
forecast band covers the ratings it predicts, how often the anomaly detector
(gate G6) trips and which branch voted, and the offline naive replay.

Every test builds its own synthetic steps, trace and archive under `tmp_path`;
none reads or writes the real backfill files and none touches the network.
Follows backend/tests/real_data_validation_test.py's conventions (module-level
imports, plain asserts, no test classes). The G6 vote-marker test runs the
REAL AnomalyDetector branches behind the REAL DLRSafetyMonitor, so a reworded
detector message fails here instead of silently emptying a table.
"""

import json
import os

import numpy as np
import pandas as pd
import pytest
import requests

import anomaly_detector
import ampacity_forecast
import backfill_archive
import city_point
import config
import historical_archive
import observation_composer as oc
import real_data_validation as rdv
from DLRSafetyMonitor import DLRSafetyMonitor


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """
    Replace `requests.get` for every test. The composer and `rate_city` catch
    every provider exception, so raising alone could be swallowed; the teardown
    assert on the recorded attempts cannot be.
    """
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    # Another test module loads `.env` into the process at import time.
    for name in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "default_archive.csv"))
    # Trained models are git-ignored, so a test must not depend on whether this
    # checkout has them.
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


_CITY = "AUSTIN"
_T0 = pd.Timestamp("2025-06-02T00:00:00Z")
_BAND = (1500.0, 1450.0, 1560.0)  # forecast center, nominal lower, nominal upper


# ──────────────────────────────────────────────────────────────────────────────
# Helpers: a classified-steps frame shaped like `classify_steps` output
# ──────────────────────────────────────────────────────────────────────────────

def _row(hour=0, city=_CITY, period="scored", outcome="ok", computed=1500.0, fc=_BAND,
         n_obs=100, used=True, usable=100, history=100, signal="forecast_residual",
         model="data/models/anomaly_AUSTIN.joblib", alerts=""):
    amps, lo, hi = fc if fc is not None else (None, None, None)
    return {
        "city": city, "run_end_utc": _T0 + pd.Timedelta(hours=hour), "period": period,
        "outcome": outcome, "reported_a": computed, "computed_a": computed,
        "fc_amps": amps, "fc_ci_lower": lo, "fc_ci_upper": hi,
        "fc_n_observations": n_obs if fc is not None else None,
        "forecast_used_by_g6": used, "history_rows": history, "usable_history_rows": usable,
        "detector_signal": signal, "detector_model": model, "alerts": alerts}


def _steps(rows, with_usable=True):
    frame = pd.DataFrame(rows)
    if not with_usable:
        frame = frame.drop(columns=["usable_history_rows"])
    return frame


def _forecast_row(frame, city=_CITY):
    table = rdv.forecast_table(frame, "ml", [city])
    assert list(table["city"]) == [city]
    return table.iloc[0]


# ──────────────────────────────────────────────────────────────────────────────
# Pure helpers: band hit, widened band, bootstrap
# ──────────────────────────────────────────────────────────────────────────────

def test_band_hit_is_inclusive_at_both_edges():
    assert rdv.band_hit(1450.0, 1450.0, 1560.0)
    assert rdv.band_hit(1560.0, 1450.0, 1560.0)
    assert not rdv.band_hit(1449.99, 1450.0, 1560.0)
    assert not rdv.band_hit(1560.01, 1450.0, 1560.0)
    values = np.array([1449.99, 1450.0, 1500.0, 1560.0, 1560.01])
    hits = rdv.band_hit(values, 1450.0, 1560.0)
    assert list(hits) == [False, True, True, True, False]


def test_widened_band_agrees_with_the_detector():
    forecast = ampacity_forecast.ForecastResult(
        horizon_min=60.0, amps=1500.0, ci_lower_amps=1450.0, ci_upper_amps=1560.0,
        n_observations=100, method="naive", n_residuals=88)
    assert rdv.k_for(_CITY) == config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION[_CITY] == 4.0
    lower, upper = rdv.widened_band(1500.0, 1450.0, 1560.0, 4.0)
    assert (lower, upper) == (1300.0, 1740.0)

    detector = anomaly_detector.AnomalyDetector(forecast=forecast, k=4.0, logger=lambda m: None)
    for rating, anomalous in ((1300.0, False), (1740.0, False), (1299.99, True), (1740.01, True)):
        flagged, _ = detector.check({}, rating)
        assert flagged is anomalous
        assert bool(rdv.band_hit(rating, lower, upper)) is (not anomalous)


def test_day_block_bootstrap_is_seeded_and_needs_two_days():
    days = np.repeat(np.array(["2025-06-01", "2025-06-02", "2025-06-03"]), 10)
    hits = np.array([True] * 8 + [False] * 2 + [True] * 9 + [False] + [True] * 10)
    point = hits.mean()

    first = rdv.day_block_bootstrap_ci(hits, days)
    second = rdv.day_block_bootstrap_ci(hits, days)
    assert first == second
    assert first[0] <= point <= first[1]
    assert 0.0 <= first[0] < first[1] <= 1.0

    # Whole days are resampled, not rows: one all-hit day and one all-miss day
    # can only give pooled rates 0, 0.5 or 1, so the 95% interval spans 0 to 1.
    two_days = np.repeat(np.array(["2025-06-01", "2025-06-02"]), 10)
    two_hits = np.array([True] * 10 + [False] * 10)
    assert rdv.day_block_bootstrap_ci(two_hits, two_days) == (0.0, 1.0)

    one_day = rdv.day_block_bootstrap_ci(hits[:10], days[:10])
    assert np.isnan(one_day[0]) and np.isnan(one_day[1])
    nothing = rdv.day_block_bootstrap_ci(np.array([], dtype=bool), np.array([]))
    assert np.isnan(nothing[0]) and np.isnan(nothing[1])
    assert rdv.BOOTSTRAP_SEED == 20261019 and rdv.BOOTSTRAP_RESAMPLES == 2000


def test_residual_bucket_edges():
    assert rdv.RESIDUAL_BUCKETS == ("0", "1-47", "48-167", "168+")
    assert rdv.residual_bucket(12) == "0" and rdv.residual_bucket(5) == "0"
    assert rdv.residual_bucket(13) == "1-47" and rdv.residual_bucket(59) == "1-47"
    assert rdv.residual_bucket(60) == "48-167" and rdv.residual_bucket(179) == "48-167"
    assert rdv.residual_bucket(180) == "168+"
    assert rdv.residual_bucket(None) is None


# ──────────────────────────────────────────────────────────────────────────────
# Forecast-band coverage table
# ──────────────────────────────────────────────────────────────────────────────

def test_coverage_population_excludes_cold_degenerate_and_non_g6_steps():
    frame = _steps([
        _row(0, computed=1500.0),                                       # A: hit, widened hit
        _row(1, outcome="G6", computed=1600.0),                         # B: nominal miss, widened hit
        _row(2, computed=1450.0),                                       # C: exactly on the lower edge
        _row(3, period="warmup"),                                       # D: warm-up, left out
        _row(4, outcome="G4_high", computed=3000.0),                    # E: never reached G6
        _row(5, fc=None, usable=5, history=5),                          # F: cold start
        _row(6, fc=(1500.0, 1500.0, 1500.0), used=False),               # G: zero-width band
        _row(7, used=False, computed=1500.0),                           # H: withheld across a gap
        _row(8, outcome="G1", computed=float("nan"), fc=None, usable=100),  # I: G1, no rating
        _row(9, computed=float("nan")),                                 # J: no computed rating
    ])

    row = _forecast_row(frame)

    assert row["method"] == "ml"
    assert row["n_warmup"] == 1
    assert row["n_scored"] == 9
    assert row["n_not_g6"] == 2                 # E and I
    assert row["n_g6_evaluated"] == 7           # A B C F G H J
    assert row["n_with_forecast"] == 6          # all but F
    assert row["n_cold_start"] == 1             # F
    assert row["n_silent_forecast_failure"] == 0
    assert row["n_cleaning_failure_suspect"] == 0
    assert row["n_degenerate_band"] == 1        # G
    assert row["n_no_computed"] == 1            # J
    assert row["n_band"] == 4                   # A B C H
    assert row["n_withheld_gap"] == 1           # H, still in the nominal population
    assert row["n_used_by_g6"] == 3             # A B C
    assert row["n_band"] == row["n_used_by_g6"] + row["n_withheld_gap"]
    assert row["coverage_nominal"] == pytest.approx(3 / 4)       # B misses, C is on the edge
    assert row["nominal_target"] == pytest.approx(0.90)
    assert row["coverage_widened"] == pytest.approx(1.0)         # A B C, H left out
    assert row["width_mean_a"] == pytest.approx(110.0)
    assert row["width_median_a"] == pytest.approx(110.0)
    assert row["mae_a"] == pytest.approx((0 + 100 + 50 + 0) / 4)
    assert row["bias_a"] == pytest.approx((0 + 100 - 50 + 0) / 4)
    assert row["n_all_computed"] == 5           # A B C H and the G4 fallback E
    assert row["coverage_all_computed"] == pytest.approx(3 / 5)  # A C H hit, B and E miss
    # one UTC day only: no bootstrap interval, not a made-up number
    assert np.isnan(row["coverage_ci_lo"]) and np.isnan(row["coverage_ci_hi"])


def test_silent_forecast_failure_is_counted():
    frame = _steps([
        _row(0, fc=None, usable=40, history=40),    # enough history, no forecast: silent failure
        _row(1, fc=None, usable=5, history=5),      # genuine cold start
        _row(2, fc=None, usable=0, history=30),     # cleaning dropped everything: suspect
        _row(3, outcome="G6", fc=None, usable=12, history=12, signal="model_trip"),  # 12 is enough
        _row(4, fc=_BAND),
    ])

    row = _forecast_row(frame)

    assert row["n_g6_evaluated"] == 5 and row["n_with_forecast"] == 1
    assert row["n_silent_forecast_failure"] == 2   # steps 0 and 3
    assert row["n_cold_start"] == 2                # steps 1 and 2
    assert row["n_cleaning_failure_suspect"] == 1  # step 2 (also a cold start by usable rows)

    # An older trace without usable_history_rows: the split cannot be made.
    unknown = _forecast_row(frame.drop(columns=["usable_history_rows"]))
    assert pd.isna(unknown["n_silent_forecast_failure"])
    assert pd.isna(unknown["n_cold_start"])
    assert pd.isna(unknown["n_cleaning_failure_suspect"])
    assert unknown["n_with_forecast"] == 1 and unknown["n_g6_evaluated"] == 5


def test_coverage_by_residuals_lists_every_bucket_for_both_periods():
    frame = _steps([
        _row(0, n_obs=20),                                   # 8 residuals -> 1-47, hit
        _row(1, n_obs=20, computed=1700.0),                  # 1-47, miss
        _row(2, n_obs=100),                                  # 88 residuals -> 48-167, hit
        _row(3, n_obs=400, period="warmup"),                 # 388 -> 168+, warm-up
        _row(4, n_obs=12, fc=(1500.0, 1500.0, 1500.0), used=False),  # 0 residuals, zero width
    ])

    table = rdv.coverage_by_residuals_table(frame, "ml", [_CITY])

    assert list(table.columns)[:6] == ["city", "method", "period", "bucket", "n", "coverage_nominal"]
    assert len(table) == 2 * len(rdv.RESIDUAL_BUCKETS)
    cell = {(r.period, r.bucket): r for r in table.itertuples()}
    assert cell[("scored", "1-47")].n == 2 and cell[("scored", "1-47")].coverage_nominal == 0.5
    assert cell[("scored", "48-167")].n == 1 and cell[("scored", "48-167")].coverage_nominal == 1.0
    assert cell[("scored", "168+")].n == 0 and np.isnan(cell[("scored", "168+")].coverage_nominal)
    assert cell[("warmup", "168+")].n == 1
    assert cell[("scored", "0")].n == 0          # a zero-width band is not in the population
    assert cell[("scored", "0")].n_zero_width == 1


# ──────────────────────────────────────────────────────────────────────────────
# G6 vote parsing against the real detector
# ──────────────────────────────────────────────────────────────────────────────

_RAW = {"sensor_status": "ok", "link_status": "ok", "temp": 15.0, "wind": 3.0, "solar": 300.0}


class _StubModel:
    """An estimator that calls every reading an outlier."""

    def predict(self, rows):
        return np.array([-1])

    def decision_function(self, rows):
        return np.array([-0.2])


class _RaisingDetector:
    def check(self, raw_data, rating):
        raise RuntimeError("boom")


def _monitor(detector=None):
    point = city_point.city_point(_CITY)
    return DLRSafetyMonitor(
        static_rating=point.static_rating, conductor=point.conductor,
        rating_bounds=point.rating_bounds, delta_fraction=float("inf"),
        anomaly_detector=detector, logger=lambda msg: None)


def _forecast_far_from(rating):
    centre = rating + 400.0
    return ampacity_forecast.ForecastResult(
        horizon_min=60.0, amps=centre, ci_lower_amps=centre - 10.0, ci_upper_amps=centre + 10.0,
        n_observations=100, method="naive", n_residuals=88)


def test_g6_vote_markers_match_real_detector_reasons():
    rating = _monitor().run_check(dict(_RAW))["rating"]
    history = pd.DataFrame({"dlr_amps": [rating + 300.0 + (i % 3) * 5.0 for i in range(30)]})

    def alerts_of(detector):
        result = _monitor(detector).run_check(dict(_RAW))
        return result["alerts"]

    forecast = anomaly_detector.AnomalyDetector.for_city(
        _CITY, forecast=_forecast_far_from(rating), load_model=False)
    rolling = anomaly_detector.AnomalyDetector.for_city(_CITY, history=history, load_model=False)
    model = anomaly_detector.AnomalyDetector.for_city(_CITY, model=_StubModel())
    both = anomaly_detector.AnomalyDetector.for_city(
        _CITY, forecast=_forecast_far_from(rating), model=_StubModel())
    clean = anomaly_detector.AnomalyDetector.for_city(
        _CITY, forecast=ampacity_forecast.ForecastResult(60.0, rating, rating - 10, rating + 10,
                                                         100, "naive", 88), load_model=False)

    assert rdv.g6_votes(alerts_of(forecast)) == {"forecast"}
    assert rdv.g6_votes(alerts_of(rolling)) == {"rolling"}
    assert rdv.g6_votes(alerts_of(model)) == {"model"}
    assert rdv.g6_votes(alerts_of(both)) == {"forecast", "model"}
    assert rdv.g6_votes(alerts_of(_RaisingDetector())) == {"error"}
    assert rdv.g6_votes(alerts_of(clean)) == set()
    assert rdv.g6_votes([]) == set()

    # A joined text (how classify_steps stores alerts) parses like the list.
    listed = alerts_of(forecast)
    assert rdv.g6_votes(" | ".join(listed)) == {"forecast"}
    # Another gate's text is never read as a vote, even when it quotes a marker.
    assert rdv.g6_votes(["G4 FAIL (implausible) from forecast center"]) == set()
    assert set(rdv.G6_VOTE_MARKERS) == {"forecast", "rolling", "model", "error"}


# ──────────────────────────────────────────────────────────────────────────────
# Detector table and G6 trip list
# ──────────────────────────────────────────────────────────────────────────────

def _trip_alert(votes_text, rating=1500.0):
    return f"G6 FAIL (rating 1700.0 A deviates +200.0 A {votes_text}) — fallback rating {rating:.0f} A"


def test_detector_table_counts_trips_by_branch_and_missing_models():
    forecast_trip = _trip_alert("from forecast center 1500.0 A, outside widened band [1300.0, 1740.0] A")
    model_text = "model flagged reading (temp=15.00) as outside the learned per-variable envelope"
    frame = _steps([
        _row(0, signal="forecast_residual"),
        _row(1, outcome="G6", computed=1700.0, alerts=forecast_trip, signal="forecast_residual"),
        _row(2, outcome="G6", computed=1700.0, signal="forecast_residual+model_trip",
             alerts=_trip_alert("from forecast center 1500.0 A, outside widened band [1300.0, 1740.0] A; "
                                + model_text)),
        _row(3, signal="rolling_baseline", fc=None),
        _row(4, signal="cold_start", fc=None, usable=3, history=3),
        _row(5, outcome="G6", alerts="G6 FAIL (detector error (boom)) — fallback rating 1500 A",
             signal="forecast_residual"),
        _row(6, signal="forecast_residual+model_clean", model=None),
        _row(7, outcome="G4_low", signal=None),            # never reached G6
        _row(8, period="warmup", outcome="G6", alerts=forecast_trip),
    ])

    table = rdv.detector_table(frame, "ml", [_CITY])

    row = table.iloc[0]
    assert row["method"] == "ml"
    assert row["n_g6_evaluated"] == 7 and row["n_g6_trips"] == 3
    assert row["trip_rate"] == pytest.approx(3 / 7)
    assert row["forecast_runs"] == 5   # steps 0, 1, 2, 5, 6
    assert row["rolling_runs"] == 1
    assert row["model_runs"] == 2      # step 2 (model_trip) and step 6 (model_clean)
    assert row["cold_start_runs"] == 1
    assert row["forecast_votes"] == 2 and row["model_votes"] == 1
    assert row["rolling_votes"] == 0 and row["detector_errors"] == 1
    assert row["n_g6_trips_unattributed"] == 0
    assert row["model_trip_rate"] == pytest.approx(1 / 2)
    assert row["n_detector_model_missing"] == 1
    assert row["anomaly_ml_max_false_positive_rate"] == config.ANOMALY_ML_MAX_FALSE_POSITIVE_RATE
    assert np.isnan(row["trip_rate_ci_lo"])  # a single UTC day


def test_g6_trips_are_ordered_by_deviation_and_capped_per_city():
    rows = [_row(h, outcome="G6", computed=1500.0 + h, alerts=_trip_alert("from forecast center"))
            for h in range(1, 61)]
    rows.append(_row(70, outcome="G6", fc=None, computed=1500.0, usable=3, history=3,
                     alerts=_trip_alert("from rolling baseline mean 1400.0 A")))
    rows.append(_row(71, outcome="G6", period="warmup", computed=2500.0,
                     alerts=_trip_alert("from forecast center")))

    table = rdv.g6_trips_table(_steps(rows), "ml", [_CITY], per_city=50)

    assert len(table) == 50                     # capped; the warm-up trip is not listed
    assert (table["city"] == _CITY).all() and (table["method"] == "ml").all()
    deviation = (table["computed_a"] - table["fc_amps"]).abs()
    assert list(deviation) == sorted(deviation, reverse=True)
    assert table.iloc[0]["computed_a"] == 1560.0   # largest deviation from the 1500 centre
    assert list(table.columns) == [
        "city", "method", "run_end_utc", "votes", "computed_a", "fc_amps",
        "widened_lower_a", "widened_upper_a", "reason"]
    assert table.iloc[0]["votes"] == "forecast"
    assert table.iloc[0]["widened_lower_a"] == 1300.0 and table.iloc[0]["widened_upper_a"] == 1740.0

    # The trip with no forecast sorts after every trip that has one.
    full = rdv.g6_trips_table(_steps(rows), "ml", [_CITY], per_city=100)
    assert len(full) == 61
    assert pd.isna(full.iloc[-1]["fc_amps"]) and full.iloc[-1]["votes"] == "rolling"


# ──────────────────────────────────────────────────────────────────────────────
# report: VAL-02 files, deterministic
# ──────────────────────────────────────────────────────────────────────────────

_START = "2025-06-01T20:00:00Z"   # eight steps crossing a UTC midnight
_WARMUP_H = 2.0
_HOURS = 8


def _ts(hour):
    return (pd.Timestamp(_START) + pd.Timedelta(hours=hour)).strftime(rdv._TS_FMT)


def _trace_record(hour, temp=15.0, g6_trip=False):
    point = city_point.city_point(_CITY)
    wind, solar = 3.0, 300.0
    computed = float(rdv.computed_amps(_CITY, temp, wind, solar))
    centre = computed + (50.0 if hour == 4 else 20.0 * (hour % 3 - 1))  # hour 4 misses the +-30 band
    record = {
        "schema": rdv.TRACE_SCHEMA, "run_end_utc": _ts(hour), "city": _CITY,
        "forecast_method": "ml", "error": None, "station_id": "T1",
        "rating_a": point.static_rating if g6_trip else computed,
        "static_rating_a": point.static_rating,
        "status": "fallback" if g6_trip else "OK", "fallback": g6_trip, "exhausted": False,
        "archived": True, "fallback_gates": ["G6"] if g6_trip else [],
        "alerts": [_trip_alert("from forecast center 1500.0 A, outside widened band "
                               "[1300.0, 1740.0] A")] if g6_trip else [],
        "observation": {"temp": temp, "wind": wind, "wind_raw": 4.0,
                        "wind_direction": 100.0, "solar": solar},
        "observation_hour": _ts(hour),
        "sources": {"air_temp": "synoptic", "wind_speed": "tceq", "solar_radiation": "nsrdb"},
        "pipeline": {
            "history_rows": 100, "usable_history_rows": 99, "forecast_method": "ml",
            "forecast_used_by_g6": True,
            "forecast": {"amps": centre, "ci_lower_amps": centre - 30.0,
                         "ci_upper_amps": centre + 30.0, "n_observations": 100,
                         "horizon_min": 60.0},
            "detector_signal": "forecast_residual", "detector_model": "m.joblib"}}
    return record


def _write_run(tmp_path, records):
    trace, archive = tmp_path / "trace.jsonl", tmp_path / "archive.csv"
    trace.write_text("\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n",
                     encoding="utf-8")
    for record in records:
        obs = record["observation"]
        row = historical_archive.build_archive_row(
            record["city"], pd.Timestamp(record["run_end_utc"]),
            {"temp": obs["temp"], "wind": obs["wind"], "solar": obs["solar"]},
            {"rating": record["rating_a"], "status": record["status"], "fallback": record["fallback"]},
            record["static_rating_a"])
        historical_archive.append_observation(row, path=str(archive))
    return archive, trace


def _report(tmp_path, records, out_name):
    archive, trace = _write_run(tmp_path, records) if not (tmp_path / "trace.jsonl").exists() \
        else (tmp_path / "archive.csv", tmp_path / "trace.jsonl")
    out_dir = tmp_path / out_name
    code = rdv.main([
        "report", "--archive", str(archive), "--trace", str(trace), "--start", _START,
        "--end", _ts(_HOURS - 1), "--warmup-hours", str(_WARMUP_H), "--cities", _CITY,
        "--out-dir", str(out_dir)])
    return code, out_dir


def test_report_writes_val02_tables_deterministically(tmp_path):
    records = [_trace_record(h, temp=10.0 + 2.0 * h, g6_trip=(h == 5)) for h in range(_HOURS)]

    code1, first = _report(tmp_path, records, "run1")
    code2, second = _report(tmp_path, records, "run2")

    assert code1 == 0 and code2 == 0
    names = ["val02_forecast_by_city.csv", "val02_coverage_by_residuals.csv",
             "val02_detector_by_city.csv", "val02_g6_trips.csv", "report_meta.json", "tables.md"]
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
        assert b"\r" not in (first / name).read_bytes()

    forecast = pd.read_csv(first / "val02_forecast_by_city.csv")
    assert list(forecast["city"]) == [_CITY] and list(forecast["method"]) == ["ml"]
    row = forecast.iloc[0]
    assert row["n_scored"] == _HOURS - 2          # two warm-up steps
    assert row["n_g6_evaluated"] == 6             # the G6 trip also reached G6
    assert row["n_band"] == 6 and row["n_used_by_g6"] == 6
    assert row["nominal_target"] == pytest.approx(0.9)
    assert row["coverage_nominal"] == pytest.approx(5 / 6, abs=1e-4)   # hour 4 is outside its band
    assert row["coverage_widened"] == 1.0                              # the widened band holds all six
    assert row["coverage_ci_lo"] <= row["coverage_nominal"] <= row["coverage_ci_hi"]  # two UTC days
    assert len(str(row["coverage_nominal"]).split(".")[-1]) <= 4

    detector = pd.read_csv(first / "val02_detector_by_city.csv").iloc[0]
    assert detector["n_g6_trips"] == 1 and detector["forecast_votes"] == 1
    trips = pd.read_csv(first / "val02_g6_trips.csv")
    assert len(trips) == 1 and trips.iloc[0]["votes"] == "forecast"
    assert pd.read_csv(first / "val02_coverage_by_residuals.csv")["bucket"].nunique() == 4

    meta = json.loads((first / "report_meta.json").read_text(encoding="utf-8"))
    assert meta["nominal_coverage_target"] == pytest.approx(0.9)
    assert meta["bootstrap"] == {"n_resamples": 2000, "seed": 20261019, "conf": 0.95,
                                 "block": "UTC day"}
    assert "usable_history_rows" not in " ".join(meta.get("val02_notes", []))
    tables = (first / "tables.md").read_text(encoding="utf-8")
    assert tables.index("# VAL-01 tables") < tables.index("# VAL-02 tables")
    assert "val02_g6_trips.csv" in tables


def test_report_notes_a_trace_without_usable_history_rows(tmp_path):
    records = [_trace_record(h, temp=10.0 + 2.0 * h) for h in range(_HOURS)]
    for record in records:
        del record["pipeline"]["usable_history_rows"]

    code, out_dir = _report(tmp_path, records, "run")

    assert code == 0
    meta = json.loads((out_dir / "report_meta.json").read_text(encoding="utf-8"))
    assert any("usable_history_rows" in note for note in meta["val02_notes"])
    forecast = pd.read_csv(out_dir / "val02_forecast_by_city.csv").iloc[0]
    assert pd.isna(forecast["n_silent_forecast_failure"])
    assert forecast["n_band"] == 6


# ──────────────────────────────────────────────────────────────────────────────
# Offline naive replay through the real pipeline
# ──────────────────────────────────────────────────────────────────────────────
#
# The original run is the whole offline stack (stub providers) over sixteen hourly
# AUSTIN steps with forecast method naive: enough history for the last steps to
# carry a forecast. The replay then feeds the same observations back through the
# real pipeline. Anomaly models are patched out (git-ignored artifacts), so the
# replay is called with require_models=False unless a test is about that refusal.

_DAY = "2025-06-01"
_R_START, _R_END = f"{_DAY}T00:00:00Z", f"{_DAY}T15:00:00Z"
_R_STEPS = 16


def _station_at(city):
    lat, lon = config.CITY_COORDINATES[city]
    return pd.DataFrame([{"stid": "T1", "name": "t", "lat": lat, "lon": lon}])


def _hourly(values):
    """One row per hour of _DAY; `values(h)` gives that hour's column values."""
    return pd.DataFrame([{"datetime_utc": pd.Timestamp(f"{_DAY}T{h:02d}:00:00Z"), **values(h)}
                         for h in range(24)])


def _install_providers(monkeypatch):
    """Stub the four providers the composer calls; values vary by hour so history has spread."""
    def synoptic(stids, start, end, provider=None, fallback=None):
        return _hourly(lambda h: dict(stid=stids[0], air_temp=18.0 + 0.9 * h + (h % 3),
                                      wind_speed=2.0, wind_direction=10.0, solar_radiation=100.0))

    def tceq(cams_id, start, end):
        return _hourly(lambda h: dict(air_temp=19.0, wind_speed=3.0 + 0.4 * (h % 5),
                                      wind_direction=100.0 + 7.0 * (h % 6)))

    def nsrdb(lat, lon, start, end):
        return _hourly(lambda h: dict(solar_radiation=40.0 + 50.0 * h))

    monkeypatch.setattr(oc.weather_provider, "fetch_weather", synoptic)
    monkeypatch.setattr(oc.tceq_provider, "fetch_tceq", tceq)
    monkeypatch.setattr(oc.nsrdb_provider, "fetch_nsrdb", nsrdb)
    monkeypatch.setattr(oc.open_meteo_provider, "fetch_open_meteo", lambda lat, lon, start, end: pd.DataFrame())


def _original_run(tmp_path, monkeypatch):
    _install_providers(monkeypatch)
    paths = {"archive": tmp_path / "orig_archive.csv", "log": tmp_path / "orig_log.csv",
             "trace": tmp_path / "orig_trace.jsonl"}
    backfill_archive.backfill(
        _R_START, _R_END, archive_path=str(paths["archive"]), log_path=str(paths["log"]),
        cities=[_CITY], forecast_method="naive", stations=_station_at(_CITY), out=lambda *_: None,
        trace_path=str(paths["trace"]))
    return paths


def _out_paths(tmp_path, tag="rep"):
    return {"archive": tmp_path / f"{tag}_archive.csv", "trace": tmp_path / f"{tag}_trace.jsonl",
            "log": tmp_path / f"{tag}_log.csv", "fidelity": tmp_path / f"{tag}_fidelity.json"}


def _replay(orig, outs, method="naive", **kwargs):
    kwargs.setdefault("require_models", False)
    kwargs.setdefault("out", lambda *_: None)
    return rdv.replay(str(orig["trace"]), _R_START, _R_END, 1.0, [_CITY], method,
                      str(outs["archive"]), str(outs["trace"]), str(outs["log"]), **kwargs)


def _classified(archive, trace):
    steps = rdv.expected_steps(_R_START, _R_END)
    return rdv.classify_steps(
        rdv.load_trace(trace), historical_archive.read_history(path=str(archive), validate=True),
        [_CITY], steps, pd.Timestamp(_R_START), 2.0)


def _comparable(trace_df):
    cols = ["city", "run_end_utc", "rating_a", "fallback", "fc_amps", "fc_ci_lower", "fc_ci_upper",
            "detector_signal", "obs_temp", "obs_wind", "obs_wind_raw", "obs_solar", "temp_source",
            "wind_source", "solar_source", "observation_hour", "history_rows", "usable_history_rows"]
    frame = trace_df.sort_values(["city", "run_end_utc"]).reset_index(drop=True)
    out = frame[cols].copy()
    out["fallback_gates"] = [tuple(g) for g in frame["fallback_gates"]]
    return out


def _model_dir(tmp_path, monkeypatch, with_models):
    path = tmp_path / "anomaly_models"
    path.mkdir(exist_ok=True)
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(path))
    if with_models:
        (path / config.ANOMALY_ML_MODEL_FILENAME_TEMPLATE.format(city=_CITY)).write_bytes(b"x")
    return path


def _cli(orig, outs, *extra):
    return ["replay", "--archive", str(orig["archive"]), "--trace", str(orig["trace"]),
            "--start", _R_START, "--end", _R_END, "--cities", _CITY, "--method", "naive",
            "--archive-out", str(outs["archive"]), "--trace-out", str(outs["trace"]),
            "--log-out", str(outs["log"]), "--fidelity-out", str(outs["fidelity"]),
            "--warmup-hours", "2", *extra]


def test_replay_with_the_same_method_reproduces_the_original_trace(tmp_path, monkeypatch):
    orig = _original_run(tmp_path, monkeypatch)
    outs = _out_paths(tmp_path)
    lines = []

    totals = _replay(orig, outs, out=lines.append)

    assert totals[_CITY]["runs"] == _R_STEPS
    assert len(lines) == 1  # one progress line per simulated UTC day
    original, replayed = rdv.load_trace(orig["trace"]), rdv.load_trace(outs["trace"])
    assert len(original) == len(replayed) == _R_STEPS
    assert original["fc_amps"].notna().sum() >= 2  # the comparison covers real forecasts
    pd.testing.assert_frame_equal(_comparable(original), _comparable(replayed))
    assert set(replayed["station_id"]) == {"REPLAY_" + _CITY}
    fidelity = rdv.replay_fidelity(_classified(orig["archive"], orig["trace"]),
                                   _classified(outs["archive"], outs["trace"]))
    assert fidelity["compared"] == _R_STEPS and fidelity["excluded"] == 0
    assert fidelity["mismatches"] == 0 and fidelity["examples"] == []
    assert (fidelity["mismatch_outcome"], fidelity["mismatch_computed"],
            fidelity["mismatch_g6_reach"]) == (0, 0, 0)


def test_replay_fidelity_flags_a_changed_observation(tmp_path, monkeypatch, capsys):
    orig = _original_run(tmp_path, monkeypatch)
    _model_dir(tmp_path, monkeypatch, with_models=True)
    classified = _classified(orig["archive"], orig["trace"])
    target = classified[classified["outcome"] == "ok"].iloc[3]["run_end_utc"].strftime(rdv._TS_FMT)
    lines = orig["trace"].read_text(encoding="utf-8").splitlines()
    edited = []
    for line in lines:
        record = json.loads(line)
        if record["run_end_utc"] == target:
            record["observation"]["solar"] = 2000.0  # past the G3 range limit; the record still says ok
        edited.append(json.dumps(record, sort_keys=True))
    orig["trace"].write_text("\n".join(edited) + "\n", encoding="utf-8")
    outs = _out_paths(tmp_path)

    code = rdv.main(_cli(orig, outs))

    assert code == 1
    fidelity = json.loads(outs["fidelity"].read_text(encoding="utf-8"))
    assert fidelity["mismatches"] >= 1 and fidelity["mismatch_g6_reach"] >= 1
    assert fidelity["examples"][0]["city"] == _CITY
    assert fidelity["examples"][0]["run_end_utc"] == target
    assert fidelity["examples"][0]["replay_outcome"] == "G3"
    assert "mismatches=" in capsys.readouterr().out

    # An unchanged trace replays clean: exit 0, zero mismatches.
    clean_dir = tmp_path / "clean"
    clean_dir.mkdir()
    clean = _original_run(clean_dir, monkeypatch)
    clean_outs = _out_paths(clean_dir)
    assert rdv.main(_cli(clean, clean_outs)) == 0
    assert json.loads(clean_outs["fidelity"].read_text(encoding="utf-8"))["mismatches"] == 0


def test_replay_refuses_without_anomaly_models_or_over_existing_outputs(tmp_path, monkeypatch, capsys):
    orig = _original_run(tmp_path, monkeypatch)
    model_dir = _model_dir(tmp_path, monkeypatch, with_models=False)
    outs = _out_paths(tmp_path)

    code = rdv.main(_cli(orig, outs))

    err = capsys.readouterr().err
    assert code == 2
    assert config.ANOMALY_ML_MODEL_FILENAME_TEMPLATE.format(city=_CITY) in err
    assert not any(path.exists() for path in outs.values())  # nothing was started
    with pytest.raises(rdv.ReplayRefused):
        _replay(orig, outs, require_models=True)

    # With the model present, an existing output file is still refused, untouched.
    (model_dir / config.ANOMALY_ML_MODEL_FILENAME_TEMPLATE.format(city=_CITY)).write_bytes(b"x")
    outs["trace"].write_text("keep", encoding="utf-8")
    code = rdv.main(_cli(orig, outs))
    err = capsys.readouterr().err
    assert code == 2 and str(outs["trace"]) in err
    assert outs["trace"].read_text(encoding="utf-8") == "keep"
    assert not outs["archive"].exists() and not outs["log"].exists() and not outs["fidelity"].exists()

    # A missing original input is also exit 2, naming the path.
    missing = dict(orig, trace=tmp_path / "nope.jsonl")
    assert rdv.main(_cli(missing, _out_paths(tmp_path, "other"))) == 2
    assert str(tmp_path / "nope.jsonl") in capsys.readouterr().err


def test_replay_never_touches_the_network(tmp_path, monkeypatch):
    orig = _original_run(tmp_path, monkeypatch)
    outs = _out_paths(tmp_path)
    attempts = []

    def boom(*args, **kwargs):
        attempts.append(args)
        raise AssertionError("the replay must not call a provider or the network")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(oc.weather_provider, "fetch_weather", boom)
    monkeypatch.setattr(oc.tceq_provider, "fetch_tceq", boom)
    monkeypatch.setattr(oc.nsrdb_provider, "fetch_nsrdb", boom)
    monkeypatch.setattr(oc.open_meteo_provider, "fetch_open_meteo", boom)
    monkeypatch.setattr(oc, "make_composed_fetcher", boom)

    _replay(orig, outs)

    assert attempts == []
    assert len(rdv.load_trace(outs["trace"])) == _R_STEPS
    assert os.path.getsize(outs["archive"]) > 0


def _report_with_replay(orig, outs, out_dir):
    return rdv.main([
        "report", "--archive", str(orig["archive"]), "--trace", str(orig["trace"]),
        "--start", _R_START, "--end", _R_END, "--warmup-hours", "2", "--cities", _CITY,
        "--out-dir", str(out_dir), "--replay-archive", str(outs["archive"]),
        "--replay-trace", str(outs["trace"])])


def test_report_shows_the_naive_replay_beside_the_original_and_fails_on_drift(tmp_path, monkeypatch):
    orig = _original_run(tmp_path, monkeypatch)
    clean = _out_paths(tmp_path, "clean")
    _replay(orig, clean)

    code = _report_with_replay(orig, clean, tmp_path / "report_clean")

    assert code == 0
    out_dir = tmp_path / "report_clean"
    forecast = pd.read_csv(out_dir / "val02_forecast_by_city.csv")
    assert list(forecast["method"]) == ["naive", "naive_replay"]
    detector = pd.read_csv(out_dir / "val02_detector_by_city.csv")
    assert list(detector["method"]) == ["naive", "naive_replay"]
    assert (detector["n_g6_evaluated"] > 0).all()
    fidelity = json.loads((out_dir / "replay_fidelity.json").read_text(encoding="utf-8"))
    assert fidelity["mismatches"] == 0 and fidelity["compared"] == _R_STEPS
    meta = json.loads((out_dir / "report_meta.json").read_text(encoding="utf-8"))
    assert meta["val02_method_labels"] == ["naive", "naive_replay"]
    assert meta["replay"]["reference_only"] is True and meta["replay_fidelity_mismatches"] == 0
    assert "counterfactual reference" in (out_dir / "tables.md").read_text(encoding="utf-8")
    ratings = pd.read_csv(out_dir / "val01_ratings_by_city.csv")
    assert len(ratings) == 1  # VAL-01 stays on the original run only

    # A replay fed a drifted trace no longer matches the original: report exits 1,
    # after writing its files.
    drifted_trace = tmp_path / "drifted_trace.jsonl"
    records = [json.loads(line) for line in orig["trace"].read_text(encoding="utf-8").splitlines()]
    records[5]["observation"]["solar"] = 2000.0
    drifted_trace.write_text("\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n",
                             encoding="utf-8")
    drift = _out_paths(tmp_path, "drift")
    rdv.replay(str(drifted_trace), _R_START, _R_END, 1.0, [_CITY], "naive", str(drift["archive"]),
               str(drift["trace"]), str(drift["log"]), require_models=False, out=lambda *_: None)

    assert _report_with_replay(orig, drift, tmp_path / "report_drift") == 1
    drift_fidelity = json.loads((tmp_path / "report_drift" / "replay_fidelity.json").read_text(encoding="utf-8"))
    assert drift_fidelity["mismatches"] >= 1
    assert (tmp_path / "report_drift" / "tables.md").exists()
