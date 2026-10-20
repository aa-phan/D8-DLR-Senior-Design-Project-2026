"""
Tests for backend/historical_archive.py -- shared C9/C10 support (D-07's
locked 10-column row schema, one row per city per run, D-09's
append-only CSV storage).

Every test writes under `tmp_path` so no test ever touches
`config.HISTORICAL_ARCHIVE_PATH`. Follows
backend/tests/city_rating_test.py's conventions (module-level
imports, plain asserts, no classes, no network).
"""

import logging

import pandas as pd
import pytest

import historical_archive as ha
import units_def


def _row(air_temp=25.0, city="AUSTIN", dlr_amps=1200.0,
         datetime_utc="2026-01-01T00:00:00"):
    return {
        "datetime_utc": datetime_utc,
        "city": city,
        "air_temp": air_temp,
        "wind_speed": 5.0,
        "solar_radiation": 500.0,
        "dlr_amps": dlr_amps,
        "static_rating": 1200.0,
        "status": "ok",
        "fallback": False,
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


def test_read_history_filters_by_city(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    assert ha.append_observation(
        _row(city="AUSTIN", datetime_utc="2026-01-01T00:00:00"),
        path=str(path),
    ) is True
    assert ha.append_observation(
        _row(city="MIDLAND", datetime_utc="2026-01-01T01:00:00"),
        path=str(path),
    ) is True

    df = ha.read_history(path=str(path), city="AUSTIN")

    assert len(df) == 1
    assert df.iloc[0]["city"] == "AUSTIN"


# ──────────────────────────────────────────────────────────────────────────────
# build_archive_row -- shape, schema version, float discipline
# ──────────────────────────────────────────────────────────────────────────────

def test_build_archive_row_validates_for_normal_and_fallback_readings():
    observation = {"temp": 25.0, "wind": 5.0, "solar": 500.0}
    normal_result = {"status": "ok", "rating": 1200.0, "fallback": False, "alerts": []}
    fallback_result = {"status": "fallback", "rating": 1200.0, "fallback": True, "alerts": ["G6 FAIL"]}

    for check_result in (normal_result, fallback_result):
        row = ha.build_archive_row(
            city="AUSTIN",
            datetime_utc="2026-01-01T00:00:00",
            observation=observation,
            check_result=check_result,
            static_rating=1200.0,
        )
        errors = units_def.validate_pipeline_row(ha._validation_row(row), strict=False)
        assert errors == []


def test_build_archive_row_keys_and_schema_version():
    row = ha.build_archive_row(
        city="AUSTIN",
        datetime_utc="2026-01-01T00:00:00",
        observation={"temp": 25.0, "wind": 5.0, "solar": 500.0},
        check_result={"status": "ok", "rating": 1200.0, "fallback": False, "alerts": []},
        static_rating=1200.0,
    )

    assert sorted(row.keys()) == sorted(ha.ARCHIVE_COLUMNS)
    assert row["schema_version"] == ha.ARCHIVE_SCHEMA_VERSION


def test_build_archive_row_numeric_values_are_python_floats():
    row = ha.build_archive_row(
        city="AUSTIN",
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


# ──────────────────────────────────────────────────────────────────────────────
# Corridor-era archive compatibility
# ──────────────────────────────────────────────────────────────────────────────

def _legacy_row(**kw):
    row = _row(**kw)
    row["corridor"] = row.pop("city")
    return row


def test_read_history_exposes_legacy_corridor_column_as_city(tmp_path):
    path = tmp_path / "legacy.csv"
    legacy_columns = [c if c != "city" else "corridor" for c in ha.ARCHIVE_COLUMNS]
    pd.DataFrame([_legacy_row(city="AUSTIN_CORPUS_CHRISTI")], columns=legacy_columns).to_csv(
        path, index=False
    )

    df = ha.read_history(path=str(path))

    assert "corridor" not in df.columns
    assert df.iloc[0]["city"] == "AUSTIN_CORPUS_CHRISTI"
    # A per-city filter never matches a legacy corridor row.
    assert ha.read_history(path=str(path), city="AUSTIN").empty


def test_append_to_legacy_file_keeps_columns_aligned(tmp_path):
    path = tmp_path / "legacy.csv"
    legacy_columns = [c if c != "city" else "corridor" for c in ha.ARCHIVE_COLUMNS]
    pd.DataFrame([_legacy_row(city="MIDLAND_EL_PASO")], columns=legacy_columns).to_csv(
        path, index=False
    )

    assert ha.append_observation(
        _row(city="AUSTIN", datetime_utc="2026-01-02T00:00:00"), path=str(path)
    ) is True

    df = ha.read_history(path=str(path))
    assert len(df) == 2
    assert ha.read_history(path=str(path), city="AUSTIN").iloc[0]["dlr_amps"] == 1200.0


def test_append_observation_accepts_corridor_keyed_row(tmp_path):
    path = tmp_path / "a.csv"
    assert ha.append_observation(_legacy_row(city="AUSTIN"), path=str(path)) is True
    assert ha.read_history(path=str(path)).iloc[0]["city"] == "AUSTIN"


def test_append_and_read_file_with_legacy_bottleneck_index_column(tmp_path):
    path = tmp_path / "old.csv"
    old_columns = [c for c in ha.ARCHIVE_COLUMNS]
    old_columns.insert(old_columns.index("schema_version"), "bottleneck_index")
    old_row = dict(_row(city="AUSTIN"), bottleneck_index=0)
    pd.DataFrame([old_row], columns=old_columns).to_csv(path, index=False)

    assert ha.append_observation(
        _row(city="AUSTIN", datetime_utc="2026-01-02T00:00:00"), path=str(path)
    ) is True

    df = ha.read_history(path=str(path))
    assert len(df) == 2
    assert list(df.columns) == old_columns
    assert pd.isna(df.iloc[1]["bottleneck_index"])
    assert df.iloc[1]["dlr_amps"] == 1200.0


# ──────────────────────────────────────────────────────────────────────────────
# One row per slot (CLEAN-03, production-pipeline Phase 2)
#
# The CSV keeps the first row written for a (city, UTC instant) and refuses
# every later one. This is a CSV-only rule: the Postgres writer (Phase 4)
# follows OD-7 (hour-truncated run slot, same-slot retry overwrites).
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param("2026-01-01T00:00:00Z", id="z"),
        pytest.param("2026-01-01T00:00:00", id="naive"),
        pytest.param("2026-01-01 00:00:00+00:00", id="plus_zero"),
        pytest.param("2026-01-01T06:00:00+06:00", id="plus_six"),
    ],
)
def test_append_refuses_a_second_row_for_the_same_city_and_instant_in_any_iso_spelling(
    tmp_path, spelling
):
    path = tmp_path / "ampacity_history.csv"
    first = _row(dlr_amps=1200.0, datetime_utc="2026-01-01T00:00:00Z")
    second = _row(dlr_amps=1300.0, datetime_utc=spelling)

    assert ha.append_observation(first, path=str(path)) is True
    assert ha.append_observation(second, path=str(path)) is False

    df = ha.read_history(path=str(path), validate=False)
    assert len(df) == 1
    assert df.iloc[0]["dlr_amps"] == 1200.0


def test_append_accepts_another_city_or_another_instant(tmp_path):
    path = tmp_path / "ampacity_history.csv"

    assert ha.append_observation(
        _row(city="AUSTIN", datetime_utc="2026-01-01T00:00:00Z"), path=str(path)
    ) is True
    assert ha.append_observation(
        _row(city="MIDLAND", datetime_utc="2026-01-01T00:00:00Z"), path=str(path)
    ) is True
    assert ha.append_observation(
        _row(city="AUSTIN", datetime_utc="2026-01-01T01:00:00Z"), path=str(path)
    ) is True

    assert len(ha.read_history(path=str(path), validate=False)) == 3


def test_a_refused_slot_logs_one_info_line_and_no_warning(tmp_path, caplog):
    path = tmp_path / "ampacity_history.csv"
    assert ha.append_observation(_row(), path=str(path)) is True

    with caplog.at_level(logging.INFO, logger="historical_archive"):
        assert ha.append_observation(_row(dlr_amps=1300.0), path=str(path)) is False

    records = [r for r in caplog.records if r.name == "historical_archive"]
    assert [r.levelno for r in records] == [logging.INFO]
    assert "already archived" in records[0].getMessage()
    assert not [r for r in records if r.levelno >= logging.WARNING]


def test_slot_guard_matches_the_corridor_column_of_a_corridor_era_file(tmp_path):
    path = tmp_path / "legacy.csv"
    legacy_columns = [c if c != "city" else "corridor" for c in ha.ARCHIVE_COLUMNS]
    pd.DataFrame(
        [_legacy_row(city="AUSTIN", datetime_utc="2026-01-01T00:00:00")],
        columns=legacy_columns,
    ).to_csv(path, index=False)

    assert ha.append_observation(
        _row(city="AUSTIN", datetime_utc="2026-01-01T00:00:00Z"), path=str(path)
    ) is False
    assert ha.append_observation(
        _row(city="AUSTIN", datetime_utc="2026-01-01T01:00:00Z"), path=str(path)
    ) is True

    raw = pd.read_csv(path)
    assert "corridor" in raw.columns
    assert "city" not in raw.columns
    assert len(raw) == 2


def test_unparseable_timestamps_match_only_the_identical_string(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    _write_rows_directly(path, [_row(datetime_utc="not-a-time")])

    # An unparseable timestamp already in the file never blocks a valid instant.
    assert ha.append_observation(
        _row(datetime_utc="2026-01-01T00:00:00Z"), path=str(path)
    ) is True
    # A new unparseable timestamp is refused only on an identical string.
    assert ha.append_observation(_row(datetime_utc="not-a-time"), path=str(path)) is False
    assert ha.append_observation(_row(datetime_utc="also-not-a-time"), path=str(path)) is True


def test_a_file_that_already_holds_duplicates_still_refuses_a_third(tmp_path):
    path = tmp_path / "ampacity_history.csv"
    _write_rows_directly(
        path,
        [
            _row(dlr_amps=1200.0, datetime_utc="2026-01-01T00:00:00"),
            _row(dlr_amps=1250.0, datetime_utc="2026-01-01T00:00:00"),
        ],
    )

    assert ha.append_observation(
        _row(dlr_amps=1300.0, datetime_utc="2026-01-01T00:00:00"), path=str(path)
    ) is False
    assert len(ha.read_history(path=str(path), validate=False)) == 2


@pytest.mark.parametrize("state", ["missing", "zero_bytes"])
def test_first_append_to_a_missing_or_empty_file_writes_one_header(tmp_path, state):
    path = tmp_path / "ampacity_history.csv"
    if state == "zero_bytes":
        path.write_bytes(b"")

    assert ha.append_observation(_row(), path=str(path)) is True

    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert lines[0] == ",".join(ha.ARCHIVE_COLUMNS)


def test_unreadable_slot_check_is_not_archived_and_does_not_raise(tmp_path, caplog):
    path = tmp_path / "ampacity_history.csv"
    path.write_text("a,b\n1,2\n")

    with caplog.at_level(logging.INFO, logger="historical_archive"):
        assert ha.append_observation(_row(), path=str(path)) is False

    warnings = [
        r for r in caplog.records
        if r.name == "historical_archive" and r.levelno >= logging.WARNING
    ]
    assert len(warnings) == 1
    assert "append failed (non-fatal)" in warnings[0].getMessage()
    assert path.read_text() == "a,b\n1,2\n"
