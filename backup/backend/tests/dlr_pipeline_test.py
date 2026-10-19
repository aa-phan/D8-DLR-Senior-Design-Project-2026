"""
Tests for DS-F5 — backend/dlr_pipeline.py.

Covers per-location static rating resolution in run_pipeline() and
plot_dlr_summary(): both functions gain a `city` parameter, resolved
internally through config.STATIC_RATINGS.get(city,
config.DEFAULT_STATIC_RATING), replacing the removed `static_rating`
parameter that previously hardcoded config.DEFAULT_STATIC_RATING at both
call sites in this file's __main__ block. Neither function had test
coverage before this phase.
"""
import inspect
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
import thermal_model
import dlr_pipeline


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────
def _synthetic_observations() -> pd.DataFrame:
    """Builds a synthetic observation frame in exactly the shape
    fetch_timeseries() returns."""
    times = pd.date_range("2025-07-01T00:00:00Z", periods=6, freq="5min")
    df = pd.DataFrame(
        {
            "stid": ["TEST1"] * 6,
            "datetime_utc": times,
            "air_temp": [35.0] * 6,
            "wind_speed": [3.0] * 6,
            "wind_direction": [0.0] * 6,
            "wind_gust": [4.0] * 6,
            "solar_radiation": [1000.0] * 6,
            "relative_humidity": [20.0] * 6,
        }
    )
    return df.set_index(["stid", "datetime_utc"]).sort_index()


def _run(monkeypatch, **city_kwargs) -> pd.DataFrame:
    """Monkeypatches fetch_timeseries and runs the pipeline with the
    synthetic weather above. This weather yields dlr_amps ~= 1252.99 A,
    which sits strictly between the 900 A fallback and Austin's 1825 A
    rating — that is what makes the uplift flag flip between the two
    cases below."""
    monkeypatch.setattr(dlr_pipeline, "fetch_timeseries", lambda *a, **k: _synthetic_observations())
    conductor = thermal_model.ConductorConfig(**config.DEFAULT_CONDUCTOR_CONFIG_KWARGS)
    return dlr_pipeline.run_pipeline(
        stids=["TEST1"],
        start="2025-07-01T00:00:00Z",
        end="2025-07-01T00:25:00Z",
        conductor=conductor,
        solar_alt_deg=72.0,
        **city_kwargs,
    )


# ──────────────────────────────────────────────────────────────────────────
# Signature contract (D-01)
# ──────────────────────────────────────────────────────────────────────────
def test_public_signatures_take_city_and_not_a_rating():
    for fn in (dlr_pipeline.run_pipeline, dlr_pipeline.plot_dlr_summary):
        params = inspect.signature(fn).parameters
        assert "city" in params
        assert params["city"].default is None
        assert "static_rating" not in params


# ──────────────────────────────────────────────────────────────────────────
# run_pipeline: per-location rating resolution (D-01, D-02, D-04)
# ──────────────────────────────────────────────────────────────────────────
def test_run_pipeline_austin_compares_against_austin_rating(monkeypatch):
    df = _run(monkeypatch, city="AUSTIN")
    austin_rating = config.STATIC_RATINGS["AUSTIN"]
    expected_headroom = (df["dlr_amps"] - austin_rating) / austin_rating * 100
    assert df["dlr_headroom_pct"].to_numpy() == pytest.approx(expected_headroom.to_numpy())
    assert (df["dlr_uplift_flag"] == False).all()


def test_run_pipeline_without_city_uses_the_fallback_rating(monkeypatch):
    df = _run(monkeypatch)
    default_rating = config.DEFAULT_STATIC_RATING
    expected_headroom = (df["dlr_amps"] - default_rating) / default_rating * 100
    assert df["dlr_headroom_pct"].to_numpy() == pytest.approx(expected_headroom.to_numpy())
    assert (df["dlr_uplift_flag"] == True).all()


def test_city_choice_flips_the_uplift_flag(monkeypatch):
    df_austin = _run(monkeypatch, city="AUSTIN")
    df_default = _run(monkeypatch)

    assert df_austin["dlr_amps"].to_numpy() == pytest.approx(df_default["dlr_amps"].to_numpy())
    assert (df_austin["dlr_uplift_flag"] == False).all()
    assert (df_default["dlr_uplift_flag"] == True).all()
    assert (df_austin["dlr_headroom_pct"] < 0).all()
    assert (df_default["dlr_headroom_pct"] > 0).all()


def test_unknown_city_falls_back_silently(monkeypatch):
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        df_unknown = _run(monkeypatch, city="NOT_A_CITY")
    df_default = _run(monkeypatch)
    assert df_unknown["dlr_headroom_pct"].to_numpy() == pytest.approx(df_default["dlr_headroom_pct"].to_numpy())


# ──────────────────────────────────────────────────────────────────────────
# plot_dlr_summary: reference-line label reflects the resolved city (D-01)
# ──────────────────────────────────────────────────────────────────────────
def test_plot_labels_the_resolved_city_rating(monkeypatch, tmp_path):
    df = _run(monkeypatch, city="AUSTIN")
    real_close = dlr_pipeline.plt.close
    monkeypatch.setattr(dlr_pipeline.plt, "close", lambda *a, **k: None)
    try:
        dlr_pipeline.plot_dlr_summary(df, city="AUSTIN", output_dir=str(tmp_path), file_prefix="t")
        assert (tmp_path / "t_TEST1.png").exists()
        labels = [line.get_label() for line in dlr_pipeline.plt.gcf().axes[0].get_lines()]
        assert "Static Rating (1825 A)" in labels
    finally:
        real_close("all")


def test_plot_without_city_labels_the_fallback_rating(monkeypatch, tmp_path):
    df = _run(monkeypatch)
    real_close = dlr_pipeline.plt.close
    monkeypatch.setattr(dlr_pipeline.plt, "close", lambda *a, **k: None)
    try:
        dlr_pipeline.plot_dlr_summary(df, output_dir=str(tmp_path), file_prefix="t")
        assert (tmp_path / "t_TEST1.png").exists()
        labels = [line.get_label() for line in dlr_pipeline.plt.gcf().axes[0].get_lines()]
        assert "Static Rating (900 A)" in labels
    finally:
        real_close("all")
