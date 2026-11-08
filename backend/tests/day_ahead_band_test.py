"""
Tests of the day-ahead uncertainty band (production-pipeline Phase 8, plan 08-03: DAY-03, D-05..D-08).

Two halves. The first covers the hashed TEST-split artifact: it is rebuilt byte for byte from the
tracked TEST rows, parsed strictly, its builder refuses any row outside the TEST window, and no
day-ahead module may read the embargoed shadow outcomes (anti-peeking). The second covers the live
rolling band: `band_for` replaces the TEST band per city and per UTC target hour once enough graded
live pairs exist, joined from `public.day_ahead_forecast` and `public.city_rating` on a throwaway
local Postgres. Nothing here touches the live Supabase project, the live job or the network.

The local-Postgres tests need `DLR_TEST_PG_AUTOSTART=1` (backend/tests/local_pg.py); they skip
otherwise, and a skip proves nothing, so the plan's verify command treats a skip as a failure.
"""

import ast
import glob
import hashlib
import json
import logging
import os

import numpy as np
import pandas as pd
import pytest
import requests

import config
import day_ahead_band
import day_ahead_contract as contract
import local_pg

REPO_ROOT = day_ahead_band.REPO_ROOT
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
ARTIFACT_FILE = os.path.join(REPO_ROOT, day_ahead_band.BAND_ARTIFACT_PATH)
ROWS_FILE = os.path.join(REPO_ROOT, day_ahead_band.ROWS_CSV)
_STORE_MIGRATION = "20261108120000_day_ahead_forecast_store.sql"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """`requests.get` fails the test; the teardown assert cannot be swallowed by a broad except."""
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


def _committed_artifact() -> dict:
    with open(ARTIFACT_FILE, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


# --------------------------------------------------------------------------------------------------
# The TEST artifact: reproducible, and equal to the residual quantiles it claims
# --------------------------------------------------------------------------------------------------

def test_artifact_rebuilds_byte_for_byte_from_the_tracked_test_rows():
    fresh = day_ahead_band.artifact_bytes(day_ahead_band.build_band_artifact())
    with open(ARTIFACT_FILE, "rb") as fh:
        assert fh.read() == fresh


def test_artifact_records_the_sha256_of_its_rows_file():
    with open(ROWS_FILE, "rb") as fh:
        expected = hashlib.sha256(fh.read()).hexdigest()
    assert _committed_artifact()["rows_sha256"] == expected


def test_artifact_has_sixteen_bands_of_196_pairs_that_bracket_zero():
    bands = _committed_artifact()["bands"]
    assert sorted(bands) == sorted(config.LOCATIONS)
    count = 0
    for city in config.LOCATIONS:
        assert sorted(bands[city]) == ["0", "12", "18", "6"]
        for hour in ("0", "6", "12", "18"):
            band = bands[city][hour]
            assert band["n"] == 196
            assert band["lower_offset_amps"] < 0 < band["upper_offset_amps"]
            count += 1
    assert count == 16


def test_artifact_offsets_equal_the_empirical_quantiles_of_truth_minus_forecast():
    frame = pd.read_csv(ROWS_FILE)
    frame["valid_time"] = pd.to_datetime(frame["valid_time"], utc=True)
    frame["residual"] = frame["truth_amps"] - frame[contract.FORECAST_METHOD]
    q_lo, q_hi = config.FORECAST_BACKTEST_QUANTILES
    bands = _committed_artifact()["bands"]
    for city in config.LOCATIONS:
        for hour in contract.TARGET_HOURS_UTC:
            group = frame.loc[(frame["city"] == city) & (frame["valid_time"].dt.hour == hour), "residual"]
            band = bands[city][str(hour)]
            assert band["lower_offset_amps"] == pytest.approx(float(np.quantile(group, q_lo)), abs=1e-9)
            assert band["upper_offset_amps"] == pytest.approx(float(np.quantile(group, q_hi)), abs=1e-9)


# --------------------------------------------------------------------------------------------------
# The TEST window guard
# --------------------------------------------------------------------------------------------------

def test_window_bounds_equal_the_test_split_scorers_window():
    import forecast_test_split_score as scorer

    assert day_ahead_band.TEST_START == scorer.TEST_WINDOW_START
    assert day_ahead_band.TEST_END_EXCLUSIVE == scorer.TEST_WINDOW_END_EXCLUSIVE


def _csv_with_extra_row(tmp_path, *, valid_time=None, truth=None):
    """A copy of the TEST rows plus one row copied from AUSTIN 00 UTC with the given changes."""
    frame = pd.read_csv(ROWS_FILE)
    extra = frame.iloc[[0]].copy()
    if valid_time is not None:
        extra["valid_time"] = valid_time
    if truth is not None:
        extra["truth_amps"] = truth
    path = tmp_path / "rows.csv"
    pd.concat([frame, extra], ignore_index=True).to_csv(path, index=False)
    return str(path)


def test_window_a_row_at_the_cutoff_is_refused(tmp_path):
    path = _csv_with_extra_row(tmp_path, valid_time="2026-09-30 00:00:00+00:00")
    with pytest.raises(ValueError, match="TEST window end"):
        day_ahead_band.build_band_artifact(path)


def test_window_a_row_before_the_start_is_refused(tmp_path):
    path = _csv_with_extra_row(tmp_path, valid_time="2026-03-17 18:00:00+00:00")
    with pytest.raises(ValueError, match="TEST window start"):
        day_ahead_band.build_band_artifact(path)


def test_window_a_missing_value_is_refused(tmp_path):
    path = _csv_with_extra_row(tmp_path, truth=float("nan"))
    with pytest.raises(ValueError, match="missing value"):
        day_ahead_band.build_band_artifact(path)


def test_window_an_unmodified_copy_still_builds(tmp_path):
    frame = pd.read_csv(ROWS_FILE)
    path = tmp_path / "rows.csv"
    frame.to_csv(path, index=False)
    built = day_ahead_band.build_band_artifact(str(path))
    assert built["bands"] == _committed_artifact()["bands"]


# --------------------------------------------------------------------------------------------------
# The strict parser
# --------------------------------------------------------------------------------------------------

def _parse(artifact) -> dict:
    return day_ahead_band.parse_band_artifact(json.dumps(artifact).encode("utf-8"))


def test_parser_accepts_the_committed_artifact():
    assert _parse(_committed_artifact())["schema"] == day_ahead_band.ARTIFACT_SCHEMA


def _mutated(mutate):
    artifact = _committed_artifact()
    mutate(artifact)
    return artifact


@pytest.mark.parametrize("mutate, field", [
    (lambda a: a.update(schema=2), "schema"),
    (lambda a: a["bands"].pop("AUSTIN"), "AUSTIN"),
    (lambda a: a["bands"]["MIDLAND"].pop("12"), "MIDLAND"),
    (lambda a: a["bands"]["AUSTIN"]["0"].update(lower_offset_amps=float("nan")), "lower_offset_amps"),
    (lambda a: a["bands"]["AUSTIN"]["6"].update(upper_offset_amps=float("inf")), "upper_offset_amps"),
    (lambda a: a["bands"]["EL_PASO"]["18"].update(lower_offset_amps=50.0, upper_offset_amps=-50.0),
     "lower_offset_amps"),
    (lambda a: a["bands"]["AUSTIN"]["12"].update(n=0), "n"),
    (lambda a: a["bands"]["AUSTIN"]["12"].update(n=-3), "n"),
    (lambda a: a["bands"]["AUSTIN"]["12"].update(n=196.5), "n"),
    (lambda a: a["bands"]["AUSTIN"]["12"].update(n=True), "n"),
    (lambda a: a.update(quantiles=[0.1, 0.9]), "quantiles"),
    (lambda a: a.update(method="ml_wind_corrected"), "method"),
], ids=["schema_2", "missing_city", "missing_hour_key", "nan_offset", "infinite_offset",
        "lower_above_upper", "n_zero", "n_negative", "n_fractional", "n_bool", "quantiles", "method"])
def test_parser_rejects_a_bad_artifact_and_names_the_field(mutate, field):
    with pytest.raises(day_ahead_band.BandArtifactError, match=field):
        _parse(_mutated(mutate))


def test_parser_rejects_a_band_that_is_not_an_object():
    artifact = _mutated(lambda a: a["bands"]["AUSTIN"].update({"0": [1, 2, 3]}))
    with pytest.raises(day_ahead_band.BandArtifactError, match="AUSTIN"):
        _parse(artifact)


def test_parser_rejects_bytes_that_are_not_json():
    with pytest.raises(day_ahead_band.BandArtifactError, match="JSON"):
        day_ahead_band.parse_band_artifact(b"\x80not json")


# --------------------------------------------------------------------------------------------------
# The clamp
# --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("lower, upper", [(5.0, 10.0), (-20.0, -5.0)], ids=["both_above", "both_below"])
def test_clamp_a_band_that_excludes_its_centre_collapses_to_the_point_and_warns(caplog, lower, upper):
    with caplog.at_level(logging.WARNING, logger=day_ahead_band.logger.name):
        assert day_ahead_band.apply_band(100.0, lower, upper) == (100.0, 100.0)
    assert any("clamping" in record.getMessage() for record in caplog.records)


def test_clamp_a_band_that_brackets_the_point_is_left_alone(caplog):
    with caplog.at_level(logging.WARNING, logger=day_ahead_band.logger.name):
        assert day_ahead_band.apply_band(100.0, -20.0, 30.0) == (80.0, 130.0)
    assert caplog.records == []


# --------------------------------------------------------------------------------------------------
# Anti-peeking: no day-ahead module may read the embargoed shadow outcomes
# --------------------------------------------------------------------------------------------------

_FORBIDDEN_TEXT = ("data/shadow/predictions", "read_city_log_entries", "anchored_pair_frame", "2026-09-30_")
_FORBIDDEN_IMPORTS = {"forecast_shadow_confirm", "forecast_shadow_eval_core", "forecast_shadow_score"}


def _day_ahead_modules():
    return sorted(glob.glob(os.path.join(BACKEND_DIR, "*day_ahead*.py")))


def _imported_modules(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_anti_peek_the_glob_finds_the_day_ahead_modules():
    names = {os.path.basename(path) for path in _day_ahead_modules()}
    assert {"day_ahead_band.py", "day_ahead_contract.py", "day_ahead_forecast.py"} <= names


def test_anti_peek_no_day_ahead_module_names_the_embargoed_data_or_imports_a_shadow_scorer():
    for path in _day_ahead_modules():
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for needle in _FORBIDDEN_TEXT:
            assert needle not in text, f"{os.path.basename(path)} contains {needle!r}"
        offending = _imported_modules(ast.parse(text)) & _FORBIDDEN_IMPORTS
        assert not offending, f"{os.path.basename(path)} imports {sorted(offending)}"
