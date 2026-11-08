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


# --------------------------------------------------------------------------------------------------
# The live rolling band (local Postgres)
# --------------------------------------------------------------------------------------------------

_FINGERPRINT = "ab" * 32  # local_pg.rating_row's default config_fingerprint
_OTHER_FINGERPRINT = "ef" * 32
_MODEL_SHA = "cd" * 32
_OTHER_MODEL_SHA = "12" * 32
_START = pd.Timestamp("2027-01-01T00:00:00Z")
_DECISION = pd.Timestamp("2028-01-01T00:05:00Z")
_POINT = 1700.0
_CITY = "AUSTIN"
_HOUR = 12


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        paths = [p for p in local_pg.migration_files() if os.path.basename(p) <= _STORE_MIGRATION]
        assert os.path.basename(paths[-1]) == _STORE_MIGRATION, [os.path.basename(p) for p in paths]
        local_pg.apply_migrations(url, paths=paths)
        yield url


@pytest.fixture
def admin(pg_url):
    """An administrator connection with both tables emptied, for seeding."""
    import psycopg

    with psycopg.connect(pg_url, autocommit=True) as conn:
        conn.execute("truncate public.city_rating, public.day_ahead_forecast")
        yield conn


@pytest.fixture
def writer(pg_url, admin):
    """The runner's own connection: role dlr_writer, UTC session."""
    import psycopg

    conn = psycopg.connect(pg_url, autocommit=True)
    conn.execute("set timezone = 'UTC'")
    conn.execute("set role dlr_writer")
    yield conn
    conn.close()


def _valid_time(hour, index):
    """The index-th daily target at `hour` UTC, counted from _START."""
    return _START + pd.Timedelta(days=index, hours=hour)


def _forecast_row(city, valid_time, forecast_amps, **overrides):
    issued = valid_time - pd.Timedelta(hours=12)
    row = {
        "city": city, "valid_time": valid_time.to_pydatetime(), "issued_at": issued.to_pydatetime(),
        "forecast_run_init_time": (valid_time - pd.Timedelta(hours=24)).to_pydatetime(),
        "horizon_minutes": 1440, "forecast_amps": forecast_amps,
        "forecast_ci_lower_amps": forecast_amps - 200.0, "forecast_ci_upper_amps": forecast_amps + 250.0,
        "band_source": "test-split", "band_n": 196, "band_pairs_through": None,
        "band_artifact_sha256": "ab" * 32, "forecast_method": contract.FORECAST_METHOD,
        "cooling_model_sha256": _MODEL_SHA, "cooling_model_source": "refit",
        "anchor_observation_time": (issued - pd.Timedelta(minutes=5)).to_pydatetime(),
        "anchor_source": "tceq", "label": contract.DAY_AHEAD_LABEL,
        "config_version": config.RATING_CONFIG_VERSION, "config_fingerprint": _FINGERPRINT,
        "run_id": "test-run", "run_attempt": 1, "pipeline_version": "test000", "schema_version": 1,
    }
    row.update(overrides)
    return row


def _insert_forecast(conn, row):
    columns = list(contract.INSERT_COLUMNS)
    assert sorted(row) == sorted(columns)
    conn.execute(
        f"insert into {contract.TABLE} ({', '.join(columns)}) values ({', '.join(['%s'] * len(columns))})",
        [row[c] for c in columns],
    )


def _seed(admin, residuals, *, city=_CITY, hour=_HOUR, first_index=0, rating_overrides=None,
          forecast_overrides=None):
    """
    One graded pair per residual, at consecutive daily targets: the forecast is _POINT and the weather
    computed rating is _POINT + residual, so the pair's residual (rating minus forecast) is exactly it.
    """
    for offset, residual in enumerate(residuals):
        valid_time = _valid_time(hour, first_index + offset)
        local_pg.insert_rows(admin, [local_pg.rating_row(
            city, valid_time.to_pydatetime(), rating_amps=_POINT + float(residual),
            **(rating_overrides or {}),
        )])
        _insert_forecast(admin, _forecast_row(city, valid_time, _POINT, **(forecast_overrides or {})))


def _band(conn, *, city=_CITY, hour=_HOUR, decision_time=_DECISION, fingerprint=_FINGERPRINT,
          model_sha=_MODEL_SHA, point=_POINT, conn_override="use"):
    artifact = _committed_artifact()
    return day_ahead_band.band_for(
        conn if conn_override == "use" else conn_override, city, _valid_time(hour, 400), point, artifact,
        "a" * 64, config_fingerprint=fingerprint, cooling_model_sha256=model_sha,
        decision_time=decision_time,
    )


def _spread(count):
    """Residuals that straddle zero, so a band built from them has lower < 0 < upper."""
    return np.linspace(-80.0, 120.0, count)


def _expected_offsets(residuals):
    q_lo, q_hi = config.FORECAST_BACKTEST_QUANTILES
    return float(np.quantile(residuals, q_lo)), float(np.quantile(residuals, q_hi))


def test_live_59_pairs_keep_the_test_band_and_60_switch(admin, writer):
    _seed(admin, _spread(59))
    choice = _band(writer)
    assert choice.source == "test-split" and choice.n == 196 and choice.pairs_through is None
    admin.execute("truncate public.city_rating, public.day_ahead_forecast")
    _seed(admin, _spread(60))
    assert _band(writer).source == "live-rolling"


def test_live_60_pairs_record_the_size_the_newest_pair_and_np_quantile_offsets(admin, writer):
    residuals = _spread(60)
    _seed(admin, residuals)
    choice = _band(writer)
    lower, upper = _expected_offsets(residuals)
    assert choice.source == "live-rolling" and choice.n == 60
    assert choice.pairs_through == _valid_time(_HOUR, 59)
    assert choice.lower_amps == pytest.approx(_POINT + lower, abs=1e-9)
    assert choice.upper_amps == pytest.approx(_POINT + upper, abs=1e-9)
    assert choice.artifact_sha256 == "a" * 64  # the TEST artifact stays the recorded fallback (D-05)


def test_live_only_the_newest_120_of_150_pairs_are_used(admin, writer):
    residuals = _spread(150)
    _seed(admin, residuals)
    choice = _band(writer)
    lower, upper = _expected_offsets(residuals[30:])
    assert choice.source == "live-rolling" and choice.n == contract.LIVE_BAND_WINDOW == 120
    assert choice.pairs_through == _valid_time(_HOUR, 149)
    assert choice.lower_amps == pytest.approx(_POINT + lower, abs=1e-9)
    assert choice.upper_amps == pytest.approx(_POINT + upper, abs=1e-9)
    all_lower, _ = _expected_offsets(residuals)
    assert lower != pytest.approx(all_lower)  # the oldest 30 pairs really are left out


def test_live_offsets_are_empirical_quantiles_not_a_normal_approximation(admin, writer):
    residuals = np.array([-5.0] * 55 + [500.0] * 5)  # heavily skewed: mean +/- k sigma would differ
    _seed(admin, residuals)
    choice = _band(writer)
    lower, upper = _expected_offsets(residuals)
    assert choice.source == "live-rolling"
    assert choice.lower_amps == pytest.approx(_POINT + lower, abs=1e-9)
    assert choice.upper_amps == pytest.approx(_POINT + upper, abs=1e-9)


def test_per_band_sixty_pairs_do_not_switch_another_hour_or_another_city(admin, writer):
    _seed(admin, _spread(60), city="AUSTIN", hour=12)
    assert _band(writer, city="AUSTIN", hour=12).source == "live-rolling"
    other_hour = _band(writer, city="AUSTIN", hour=18)
    other_city = _band(writer, city="MIDLAND", hour=12)
    assert other_hour.source == "test-split" and other_hour.n == 196
    assert other_city.source == "test-split" and other_city.n == 196


def test_per_band_each_band_counts_only_its_own_pairs(admin, writer):
    _seed(admin, _spread(40), city="AUSTIN", hour=12)
    _seed(admin, _spread(40), city="AUSTIN", hour=18)
    _seed(admin, _spread(40), city="MIDLAND", hour=12)
    for city, hour in (("AUSTIN", 12), ("AUSTIN", 18), ("MIDLAND", 12)):
        assert _band(writer, city=city, hour=hour).source == "test-split"


@pytest.mark.parametrize("rating_overrides, forecast_overrides, decision", [
    ({"status": "fallback"}, {}, _DECISION),
    ({"fallback": True}, {}, _DECISION),
    ({"exhausted": True}, {}, _DECISION),
    ({"origin": "backfill"}, {}, _DECISION),
    ({"config_fingerprint": _OTHER_FINGERPRINT}, {}, _DECISION),
    ({}, {"config_fingerprint": _OTHER_FINGERPRINT}, _DECISION),
    ({}, {"cooling_model_sha256": _OTHER_MODEL_SHA}, _DECISION),
    ({}, {}, _valid_time(_HOUR, 59)),
    ({}, {}, _valid_time(_HOUR, 59) - pd.Timedelta(hours=1)),
], ids=["status_fallback", "fallback_flag", "exhausted", "origin_backfill", "rating_fingerprint",
        "forecast_fingerprint", "model_sha", "target_at_decision_time", "target_after_decision_time"])
def test_filters_an_excluded_pair_is_not_counted(admin, writer, rating_overrides, forecast_overrides, decision):
    """59 good pairs plus one excluded pair is still 59: the TEST band stays."""
    _seed(admin, _spread(59))
    _seed(admin, [10.0], first_index=59, rating_overrides=rating_overrides, forecast_overrides=forecast_overrides)
    assert _band(writer, decision_time=decision).source == "test-split"


def test_filters_the_same_pair_counts_when_nothing_excludes_it(admin, writer):
    """The control for the filter cases: 59 good plus one good pair is 60 and switches."""
    _seed(admin, _spread(59))
    _seed(admin, [10.0], first_index=59)
    assert _band(writer).source == "live-rolling"


def test_filters_a_live_set_uses_only_pairs_of_the_callers_fingerprint_and_model(admin, writer):
    _seed(admin, _spread(60))
    other = _band(writer, fingerprint=_OTHER_FINGERPRINT)
    other_model = _band(writer, model_sha=_OTHER_MODEL_SHA)
    assert other.source == "test-split" and other_model.source == "test-split"


def test_straddle_a_live_set_that_never_brackets_zero_keeps_the_test_band_and_says_why(admin, writer, caplog):
    residuals = np.linspace(10.0, 90.0, 60)  # every actual above the forecast: the 5% offset is positive
    _seed(admin, residuals)
    with caplog.at_level(logging.INFO, logger=day_ahead_band.logger.name):
        choice = _band(writer)
    assert choice.source == "test-split" and choice.n == 196 and choice.pairs_through is None
    assert any("straddle" in record.getMessage() or "bracket" in record.getMessage()
               for record in caplog.records)


def test_straddle_a_live_set_that_is_entirely_below_the_forecast_keeps_the_test_band(admin, writer):
    _seed(admin, np.linspace(-90.0, -10.0, 60))
    assert _band(writer).source == "test-split"


def test_sign_residual_is_rating_minus_forecast_so_a_forecast_50_amps_low_gives_offsets_near_plus_50(
        admin, writer):
    # Every actual rating is about 50 A above the forecast, with enough spread that the live band
    # still brackets zero. The offsets are centred near +50, not -50.
    residuals = 50.0 + np.linspace(-140.0, 140.0, 60)
    _seed(admin, residuals)
    choice = _band(writer)
    lower, upper = _expected_offsets(residuals)
    assert choice.source == "live-rolling"
    assert choice.lower_amps == pytest.approx(_POINT + lower, abs=1e-9)
    assert choice.upper_amps == pytest.approx(_POINT + upper, abs=1e-9)
    assert (lower + upper) / 2.0 == pytest.approx(50.0, abs=1.0)


def test_live_pairs_returns_newest_first_with_the_residual_sign(admin, writer):
    _seed(admin, [50.0, 60.0, 70.0])
    pairs = day_ahead_band.live_pairs(
        writer, _CITY, _HOUR, config_fingerprint=_FINGERPRINT, cooling_model_sha256=_MODEL_SHA,
        decision_time=_DECISION, limit=2,
    )
    assert [residual for _, residual in pairs] == [70.0, 60.0]
    assert [pd.Timestamp(valid_time) for valid_time, _ in pairs] == [_valid_time(_HOUR, 2), _valid_time(_HOUR, 1)]


def test_conn_none_returns_the_test_band_without_a_database():
    choice = _band(None)
    offsets = _committed_artifact()["bands"][_CITY][str(_HOUR)]
    assert choice.source == "test-split" and choice.n == offsets["n"] and choice.pairs_through is None
    assert choice.lower_amps == pytest.approx(_POINT + offsets["lower_offset_amps"])
    assert choice.upper_amps == pytest.approx(_POINT + offsets["upper_offset_amps"])
