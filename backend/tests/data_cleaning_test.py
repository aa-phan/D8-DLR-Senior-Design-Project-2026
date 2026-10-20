"""
Tests for backend/data_cleaning.py -- the read-time cleaning step that sits
between `historical_archive.read_history` and the forecast / detector
(production-pipeline Phase 2, CLEAN-03 read side and CLEAN-04's marker
invariant).

Pure DataFrame-in / DataFrame-out: no files except `tmp_path`, no network.
Follows backend/tests/city_rating_test.py's conventions (module-level
imports, plain asserts, no test classes).
"""

import math

import pandas as pd
import pytest

import data_cleaning
import historical_archive

_DAY = "2025-06-01"


def _rows(*specs, city="AUSTIN"):
    """
    An ARCHIVE_COLUMNS frame from `(datetime_utc, dlr_amps, fallback)` tuples.
    Weather changes from row to row in small steps, so the stuck-run and spike
    rules plan 02-03 adds never fire on these fixtures. `fallback` is kept as
    an object column so bool and text values both survive.
    """
    records = []
    for i, (datetime_utc, dlr_amps, fallback) in enumerate(specs):
        records.append({
            "datetime_utc": datetime_utc,
            "city": city,
            "air_temp": 25.0 + 0.1 * i,
            "wind_speed": 5.0 + 0.05 * i,
            "solar_radiation": 500.0 + 1.0 * i,
            "dlr_amps": dlr_amps,
            "static_rating": 1825.0,
            "status": "ok",
            "fallback": fallback,
            "schema_version": historical_archive.ARCHIVE_SCHEMA_VERSION,
        })
    frame = pd.DataFrame(records, columns=historical_archive.ARCHIVE_COLUMNS)
    frame["datetime_utc"] = frame["datetime_utc"].astype(object)
    frame["fallback"] = frame["fallback"].astype(object)
    return frame


def _hour(h):
    return f"{_DAY}T{h:02d}:00:00Z"


def _flags_by_amps(cleaned):
    return dict(zip(cleaned.frame["dlr_amps"], cleaned.frame["clean_flags"]))


def test_unparseable_or_missing_timestamps_are_flagged_bad_timestamp_and_excluded():
    history = _rows(
        ("garbage", 1001.0, False),
        ("", 1002.0, False),
        (math.nan, 1003.0, False),
        (_hour(9), 1004.0, False),
    )

    cleaned = data_cleaning.clean_history(history)

    flags = _flags_by_amps(cleaned)
    assert flags == {1001.0: "bad_timestamp", 1002.0: "bad_timestamp",
                     1003.0: "bad_timestamp", 1004.0: ""}
    excluded = dict(zip(cleaned.frame["dlr_amps"], cleaned.frame["clean_excluded"]))
    assert excluded == {1001.0: True, 1002.0: True, 1003.0: True, 1004.0: False}
    assert list(cleaned.usable["dlr_amps"]) == [1004.0]
    # Unparseable rows sort last, in input order.
    assert list(cleaned.frame["dlr_amps"]) == [1004.0, 1001.0, 1002.0, 1003.0]

    # A frame with no datetime_utc column has no parseable timestamp at all.
    no_column = history.drop(columns=["datetime_utc"])
    cleaned = data_cleaning.clean_history(no_column)
    assert set(cleaned.frame["clean_flags"]) == {"bad_timestamp"}
    assert cleaned.frame["clean_excluded"].all()
    assert len(cleaned.usable) == 0


def test_rows_at_one_instant_keep_the_first_in_input_order_and_flag_the_rest_duplicate():
    history = _rows(
        (f"{_DAY}T10:00:00Z", 1001.0, False),
        (f"{_DAY}T10:00:00", 1002.0, False),
        (f"{_DAY}T10:00:00+00:00", 1003.0, False),
        (f"{_DAY}T16:00:00+06:00", 1004.0, False),
        (_hour(11), 1005.0, False),
    )

    cleaned = data_cleaning.clean_history(history)

    assert _flags_by_amps(cleaned) == {
        1001.0: "", 1002.0: "duplicate", 1003.0: "duplicate",
        1004.0: "duplicate", 1005.0: "",
    }
    assert list(cleaned.usable["dlr_amps"]) == [1001.0, 1005.0]
    assert cleaned.report["flag_counts"]["duplicate"] == 3


def test_fallback_is_matched_as_bool_or_any_case_text():
    history = _rows(*[
        (_hour(h), 1000.0 + h, value)
        for h, value in enumerate(["TRUE", "false", True, "True", False])
    ])

    cleaned = data_cleaning.clean_history(history)

    flags = _flags_by_amps(cleaned)
    assert [flags[1000.0 + h] for h in range(5)] == ["fallback", "", "fallback", "fallback", ""]
    assert list(cleaned.usable["dlr_amps"]) == [1001.0, 1004.0]
    assert cleaned.report["flag_counts"]["fallback"] == 3


def test_a_row_can_carry_several_flags_in_flag_order():
    history = _rows(
        (_hour(10), 1001.0, False),
        (_hour(10), 1002.0, True),     # later duplicate and a fallback row
        (_hour(11), 1003.0, True),     # fallback only
    )

    cleaned = data_cleaning.clean_history(history)

    assert _flags_by_amps(cleaned) == {
        1001.0: "", 1002.0: "duplicate|fallback", 1003.0: "fallback",
    }
    # The first row written for an instant owns it, even when it is a fallback row.
    reversed_ = data_cleaning.clean_history(_rows(
        (_hour(10), 1001.0, True),
        (_hour(10), 1002.0, False),
    ))
    assert _flags_by_amps(reversed_) == {1001.0: "fallback", 1002.0: "duplicate"}
    assert len(reversed_.usable) == 0
    assert data_cleaning.FLAG_ORDER.index("duplicate") < data_cleaning.FLAG_ORDER.index("fallback")


def test_cleaning_never_changes_a_cell_and_never_mutates_its_input():
    history = _rows(
        (_hour(12), 1001.0, False),
        (f"{_DAY}T10:00:00", 1002.0, "TRUE"),
        ("garbage", 1003.0, False),
        (f"{_DAY}T10:00:00Z", 1004.0, False),   # same instant as the row above
        (f"{_DAY}T16:00:00+06:00", 1005.0, True),
    )
    snapshot = history.copy(deep=True)

    cleaned = data_cleaning.clean_history(history, as_of=f"{_DAY}T13:00:00Z")

    pd.testing.assert_frame_equal(history, snapshot)
    assert list(cleaned.frame.columns) == list(history.columns) + list(data_cleaning.MARKER_COLUMNS)
    parsed = pd.to_datetime(history["datetime_utc"], utc=True, errors="coerce", format="ISO8601")
    order = parsed.sort_values(kind="mergesort", na_position="last").index
    expected = history.loc[order].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        cleaned.frame.drop(columns=list(data_cleaning.MARKER_COLUMNS)), expected)
    assert len(cleaned.frame) == len(history)
    # `usable` is a selection of `frame`: same cells, only the excluded rows gone.
    kept = cleaned.frame[~cleaned.frame["clean_excluded"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(cleaned.usable, kept)
    assert cleaned.frame["clean_excluded"].dtype == bool


def test_empty_history_returns_empty_frames_with_marker_columns(tmp_path):
    history = historical_archive.read_history(path=str(tmp_path / "missing.csv"))
    assert len(history) == 0

    cleaned = data_cleaning.clean_history(history)

    expected_columns = list(historical_archive.ARCHIVE_COLUMNS) + list(data_cleaning.MARKER_COLUMNS)
    assert len(cleaned.frame) == 0
    assert len(cleaned.usable) == 0
    assert list(cleaned.frame.columns) == expected_columns
    assert list(cleaned.usable.columns) == expected_columns
    assert cleaned.report["rows_in"] == 0
    assert cleaned.report["rows_usable"] == 0
    assert cleaned.report["rows_excluded"] == 0
    assert cleaned.report["flag_counts"] == {name: 0 for name in data_cleaning.FLAG_ORDER}


def test_more_than_one_city_or_an_unparseable_as_of_raises_value_error():
    mixed = pd.concat([_rows((_hour(9), 1001.0, False)),
                       _rows((_hour(10), 1002.0, False), city="EL_PASO")],
                      ignore_index=True)
    with pytest.raises(ValueError, match="AUSTIN.*EL_PASO"):
        data_cleaning.clean_history(mixed)

    with pytest.raises(ValueError, match="not-a-time"):
        data_cleaning.clean_history(_rows((_hour(9), 1001.0, False)), as_of="not-a-time")


def test_report_counts_rows_and_names_the_policy_version():
    history = _rows(
        (_hour(9), 1001.0, False),
        (_hour(9), 1002.0, False),
        ("garbage", 1003.0, False),
        (_hour(11), 1004.0, True),
    )

    cleaned = data_cleaning.clean_history(history, as_of=f"{_DAY}T12:00:00")
    report = cleaned.report

    assert report["policy_version"] == data_cleaning.CLEANING_POLICY_VERSION
    assert set(report["flag_counts"]) == set(data_cleaning.FLAG_ORDER)
    assert report["flag_counts"] == {"bad_timestamp": 1, "duplicate": 1, "fallback": 1}
    assert (report["rows_in"], report["rows_usable"], report["rows_excluded"]) == (4, 1, 3)
    assert all(type(v) is int for v in report["flag_counts"].values())
    assert report["as_of"] == f"{_DAY}T12:00:00Z"
    again = data_cleaning.clean_history(history, as_of=f"{_DAY}T12:00:00+00:00")
    assert again.report["as_of"] == f"{_DAY}T12:00:00Z"
    assert data_cleaning.clean_history(history).report["as_of"] is None
