"""
Tests for backend/historical_archive.py -- shared C9/C10 support (D-07's
locked 11-column row schema, D-08's per-corridor granularity, D-09's
append-only CSV storage).

Every test writes under `tmp_path` so no test ever touches
`config.HISTORICAL_ARCHIVE_PATH`. Follows
backend/tests/corridor_discretization_test.py's conventions (module-level
imports, plain asserts, no classes, no network).
"""

import logging

import pandas as pd
import pytest

import historical_archive as ha
import units_def


def _row(air_temp=25.0, corridor="AUSTIN_CORPUS_CHRISTI", dlr_amps=1200.0,
         datetime_utc="2026-01-01T00:00:00"):
    return {
        "datetime_utc": datetime_utc,
        "corridor": corridor,
        "air_temp": air_temp,
        "wind_speed": 5.0,
        "solar_radiation": 500.0,
        "dlr_amps": dlr_amps,
        "static_rating": 1200.0,
        "status": "ok",
        "fallback": False,
        "bottleneck_index": 0,
        "schema_version": ha.ARCHIVE_SCHEMA_VERSION,
    }


def _write_rows_directly(path, rows):
    """
    Write rows straight to CSV, bypassing `append_observation`'s own
    validation -- used only to get a poisoned row onto disk for
    `read_history`'s validate-before-training tests, since
    `append_observation` would (correctly) refuse to persist it in the
    first place.
    """
    pd.DataFrame(rows, columns=ha.ARCHIVE_COLUMNS).to_csv(path, index=False)


# ──────────────────────────────────────────────────────────────────────────────
# read_history validate=True (T-04-07 -- validate before training)
# ──────────────────────────────────────────────────────────────────────────────

def test_read_history_drops_row_failing_validation_and_keeps_the_rest(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    rows = [
        _row(air_temp=25.0, datetime_utc="2026-01-01T00:00:00"),
        _row(air_temp=999.0, datetime_utc="2026-01-01T01:00:00"),  # poisoned
        _row(air_temp=26.0, datetime_utc="2026-01-01T02:00:00"),
    ]
    _write_rows_directly(path, rows)

    df = ha.read_history(path=str(path))

    assert len(df) == 2
    assert 999.0 not in df["air_temp"].tolist()


def test_read_history_logs_drop_count_once(tmp_path, caplog):
    path = tmp_path / "ampacity_history.csv"
    rows = [
        _row(air_temp=25.0, datetime_utc="2026-01-01T00:00:00"),
        _row(air_temp=999.0, datetime_utc="2026-01-01T01:00:00"),
    ]
    _write_rows_directly(path, rows)

    with caplog.at_level(logging.WARNING, logger="historical_archive"):
        ha.read_history(path=str(path))

    warnings = [r for r in caplog.records if r.name == "historical_archive"]
    assert len(warnings) == 1
    assert "1" in warnings[0].message


def test_read_history_does_not_log_when_nothing_dropped(tmp_path, caplog):
    path = tmp_path / "ampacity_history.csv"
    rows = [
        _row(air_temp=25.0, datetime_utc="2026-01-01T00:00:00"),
        _row(air_temp=26.0, datetime_utc="2026-01-01T01:00:00"),
    ]
    _write_rows_directly(path, rows)

    with caplog.at_level(logging.WARNING, logger="historical_archive"):
        ha.read_history(path=str(path))

    warnings = [r for r in caplog.records if r.name == "historical_archive"]
    assert warnings == []


def test_read_history_validate_false_returns_every_row(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    rows = [
        _row(air_temp=25.0, datetime_utc="2026-01-01T00:00:00"),
        _row(air_temp=999.0, datetime_utc="2026-01-01T01:00:00"),
    ]
    _write_rows_directly(path, rows)

    df = ha.read_history(path=str(path), validate=False)

    assert len(df) == 2


def test_read_history_filters_by_corridor(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    assert ha.append_observation(
        _row(corridor="AUSTIN_CORPUS_CHRISTI", datetime_utc="2026-01-01T00:00:00"),
        path=str(path),
    ) is True
    assert ha.append_observation(
        _row(corridor="MIDLAND_EL_PASO", datetime_utc="2026-01-01T01:00:00"),
        path=str(path),
    ) is True

    df = ha.read_history(path=str(path), corridor="AUSTIN_CORPUS_CHRISTI")

    assert len(df) == 1
    assert df.iloc[0]["corridor"] == "AUSTIN_CORPUS_CHRISTI"


# ──────────────────────────────────────────────────────────────────────────────
# build_archive_row -- shape, schema version, float discipline
# ──────────────────────────────────────────────────────────────────────────────

def test_build_archive_row_validates_for_normal_and_fallback_readings():
    observation = {"temp": 25.0, "wind": 5.0, "solar": 500.0}
    normal_result = {"status": "ok", "rating": 1200.0, "fallback": False, "alerts": []}
    fallback_result = {"status": "fallback", "rating": 1200.0, "fallback": True, "alerts": ["G6 FAIL"]}

    for check_result in (normal_result, fallback_result):
        row = ha.build_archive_row(
            corridor="AUSTIN_CORPUS_CHRISTI",
            datetime_utc="2026-01-01T00:00:00",
            observation=observation,
            check_result=check_result,
            static_rating=1200.0,
            bottleneck_index=0,
        )
        errors = units_def.validate_pipeline_row(ha._validation_row(row), strict=False)
        assert errors == []


def test_build_archive_row_keys_and_schema_version():
    row = ha.build_archive_row(
        corridor="AUSTIN_CORPUS_CHRISTI",
        datetime_utc="2026-01-01T00:00:00",
        observation={"temp": 25.0, "wind": 5.0, "solar": 500.0},
        check_result={"status": "ok", "rating": 1200.0, "fallback": False, "alerts": []},
        static_rating=1200.0,
    )

    assert sorted(row.keys()) == sorted(ha.ARCHIVE_COLUMNS)
    assert row["schema_version"] == ha.ARCHIVE_SCHEMA_VERSION


def test_build_archive_row_numeric_values_are_python_floats():
    row = ha.build_archive_row(
        corridor="AUSTIN_CORPUS_CHRISTI",
        datetime_utc="2026-01-01T00:00:00",
        observation={"temp": 25.0, "wind": 5.0, "solar": 500.0},
        check_result={"status": "ok", "rating": 1200.0, "fallback": False, "alerts": []},
        static_rating=1200.0,
    )

    for key in ("air_temp", "wind_speed", "solar_radiation", "dlr_amps", "static_rating"):
        assert type(row[key]) is float


# ──────────────────────────────────────────────────────────────────────────────
# Round-trip precision
# ──────────────────────────────────────────────────────────────────────────────

def test_append_then_read_round_trips_dlr_amps_at_full_float_precision(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    precise_value = 1234.56789
    row = _row(dlr_amps=precise_value)

    assert ha.append_observation(row, path=str(path)) is True

    df = ha.read_history(path=str(path))

    assert df.iloc[0]["dlr_amps"] == precise_value
