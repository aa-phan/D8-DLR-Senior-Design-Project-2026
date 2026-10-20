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
    # Hour 4 follows hour 1 with hours 2 and 3 excluded, so it is marked after_gap.
    assert [flags[1000.0 + h] for h in range(5)] == [
        "fallback", "", "fallback", "fallback", "after_gap"]
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
    assert report["flag_counts"] == {
        **{name: 0 for name in data_cleaning.FLAG_ORDER},
        "bad_timestamp": 1, "duplicate": 1, "fallback": 1,
    }
    assert (report["rows_in"], report["rows_usable"], report["rows_excluded"]) == (4, 1, 3)
    assert all(type(v) is int for v in report["flag_counts"].values())
    assert report["as_of"] == f"{_DAY}T12:00:00Z"
    again = data_cleaning.clean_history(history, as_of=f"{_DAY}T12:00:00+00:00")
    assert again.report["as_of"] == f"{_DAY}T12:00:00Z"
    assert data_cleaning.clean_history(history).report["as_of"] is None


def test_offset_and_naive_spellings_in_one_frame_are_parsed_independently():
    # pandas 2.3 applies an earlier value's explicit offset to a later naive or
    # date-only value in one mixed parse; each value must read as its own instant.
    history = _rows(
        (f"{_DAY}T16:00:00+06:00", 1001.0, False),   # 10:00Z
        (f"{_DAY}T11:00:00", 1002.0, False),         # naive, reads as 11:00Z
        (f"{_DAY}T10:00:00", 1003.0, False),         # naive, same instant as the first row
        (_DAY, 1004.0, False),                       # date only, reads as 00:00Z
    )

    cleaned = data_cleaning.clean_history(history)

    assert list(cleaned.frame["dlr_amps"]) == [1004.0, 1001.0, 1003.0, 1002.0]
    assert _flags_by_amps(cleaned) == {
        1004.0: "", 1001.0: "after_gap", 1003.0: "duplicate", 1002.0: "",
    }
    assert list(cleaned.usable["dlr_amps"]) == [1004.0, 1001.0, 1002.0]


# ──────────────────────────────────────────────────────────────────────────────
# Hourly slots: rows at or after the run, several rows in one hour, gaps (CLEAN-02)
# ──────────────────────────────────────────────────────────────────────────────

def _at(hour, minute=0):
    return f"{_DAY}T{hour:02d}:{minute:02d}:00Z"


def _hourly(hours, **kw):
    """Computed hourly rows at `hours`; dlr_amps is 1000 + the hour."""
    return _rows(*[(_at(h), 1000.0 + h, False) for h in hours], **kw)


def test_rows_at_or_after_the_rated_slot_are_excluded():
    history = _rows(
        (_at(10), 1001.0, False),
        (_at(11), 1002.0, False),
        (_at(12), 1003.0, False),
        (_at(12, 10), 1004.0, False),
        (_at(13), 1005.0, False),
    )

    cleaned = data_cleaning.clean_history(history, as_of=_at(12, 25))

    assert _flags_by_amps(cleaned) == {
        1001.0: "", 1002.0: "", 1003.0: "at_or_after_run",
        1004.0: "at_or_after_run", 1005.0: "at_or_after_run",
    }
    assert list(cleaned.usable["dlr_amps"]) == [1001.0, 1002.0]
    assert cleaned.report["flag_counts"]["at_or_after_run"] == 3


def test_without_as_of_no_row_is_excluded_for_its_time():
    history = _hourly([10, 11, 12, 23])

    cleaned = data_cleaning.clean_history(history)

    assert cleaned.report["flag_counts"]["at_or_after_run"] == 0
    assert len(cleaned.usable) == 4


def test_a_rerun_does_not_learn_from_its_own_slot():
    history = _hourly([10, 11, 12])

    cleaned = data_cleaning.clean_history(history, as_of=_at(12))

    assert _flags_by_amps(cleaned)[1012.0] == "at_or_after_run"
    assert list(cleaned.usable["dlr_amps"]) == [1010.0, 1011.0]
    # One minute before the slot boundary the 12:00 row is still in the future.
    assert len(data_cleaning.clean_history(history, as_of=_at(11, 59)).usable) == 1
    # The last hour before the run is usable.
    assert len(data_cleaning.clean_history(history, as_of=_at(13)).usable) == 3


def test_rows_sharing_an_hour_keep_the_latest():
    history = _rows(
        (_at(10), 1001.0, False),
        (_at(10, 5), 1002.0, False),
        (_at(10, 55), 1003.0, False),
        (_at(11), 1004.0, False),
    )

    cleaned = data_cleaning.clean_history(history)

    assert _flags_by_amps(cleaned) == {
        1001.0: "same_hour", 1002.0: "same_hour", 1003.0: "", 1004.0: "",
    }
    assert list(cleaned.usable["dlr_amps"]) == [1003.0, 1004.0]
    assert cleaned.report["flag_counts"]["same_hour"] == 2


def test_a_fallback_row_does_not_displace_a_computed_row_in_its_hour():
    history = _rows(
        (_at(11, 5), 1001.0, False),
        (_at(11, 30), 1825.0, True),
    )

    cleaned = data_cleaning.clean_history(history)

    assert _flags_by_amps(cleaned) == {1001.0: "", 1825.0: "fallback"}
    assert list(cleaned.usable["dlr_amps"]) == [1001.0]


def test_skipped_cycle_leaves_one_missing_slot_marked_on_the_next_row():
    history = _hourly([0, 1, 2, 3, 4, 6, 7, 8, 9])      # 05:00 never ran

    cleaned = data_cleaning.clean_history(history, as_of=_at(10))

    assert _flags_by_amps(cleaned)[1006.0] == "after_gap"
    gap_by_amps = dict(zip(cleaned.frame["dlr_amps"], cleaned.frame["gap_slots"]))
    assert gap_by_amps[1006.0] == 1
    assert sum(gap_by_amps.values()) == 1
    # after_gap marks the row, it does not exclude it.
    assert len(cleaned.usable) == 9
    assert not cleaned.frame["clean_excluded"].any()
    assert cleaned.report["missing_slots"] == 1
    assert cleaned.report["trailing_gap_slots"] == 0
    assert cleaned.report["flag_counts"]["after_gap"] == 1
    # No row is invented for the missing hour.
    assert len(cleaned.frame) == 9


def test_gap_slots_count_missing_hours_between_usable_rows():
    history = _hourly([0, 1, 2, 4, 5, 8])

    cleaned = data_cleaning.clean_history(history)

    assert list(cleaned.frame["gap_slots"]) == [0, 0, 0, 1, 0, 2]
    assert [bool(f) for f in cleaned.frame["clean_flags"] == "after_gap"] == [
        False, False, False, True, False, True]
    assert cleaned.report["missing_slots"] == 3
    assert cleaned.report["contiguous_tail_rows"] == 1
    assert pd.api.types.is_integer_dtype(cleaned.frame["gap_slots"])


def test_an_excluded_row_leaves_its_hour_missing():
    history = _rows(
        (_at(0), 1001.0, False),
        (_at(1), 1825.0, True),
        (_at(2), 1003.0, False),
    )

    cleaned = data_cleaning.clean_history(history)

    gap_by_amps = dict(zip(cleaned.frame["dlr_amps"], cleaned.frame["gap_slots"]))
    assert gap_by_amps == {1001.0: 0, 1825.0: 0, 1003.0: 1}
    assert _flags_by_amps(cleaned)[1003.0] == "after_gap"
    assert _flags_by_amps(cleaned)[1825.0] == "fallback"


def test_trailing_gap_is_measured_against_as_of():
    history = _hourly(range(0, 9))

    assert data_cleaning.clean_history(history, as_of=_at(9)).report["trailing_gap_slots"] == 0
    assert data_cleaning.clean_history(history, as_of=_at(10)).report["trailing_gap_slots"] == 1
    assert data_cleaning.clean_history(history, as_of=_at(11, 30)).report["trailing_gap_slots"] == 2
    assert data_cleaning.clean_history(history).report["trailing_gap_slots"] is None
    assert all(type(data_cleaning.clean_history(history, as_of=_at(10)).report[key]) is int
               for key in ("missing_slots", "trailing_gap_slots", "contiguous_tail_rows"))

    # Nothing usable: no trailing gap to measure and no unbroken tail.
    all_fallback = _rows((_at(0), 1825.0, True), (_at(1), 1825.0, True))
    report = data_cleaning.clean_history(all_fallback, as_of=_at(10)).report
    assert report["trailing_gap_slots"] is None
    assert report["contiguous_tail_rows"] == 0
    assert report["missing_slots"] == 0


def test_contiguous_tail_counts_the_newest_unbroken_run():
    assert data_cleaning.clean_history(_hourly(range(10))).report["contiguous_tail_rows"] == 10
    broken = _hourly([0, 1, 2, 3, 5, 6, 7, 8, 9])
    assert data_cleaning.clean_history(broken).report["contiguous_tail_rows"] == 5


def test_a_frame_without_rows_has_an_integer_gap_slots_column_and_zero_gap_report(tmp_path):
    history = historical_archive.read_history(path=str(tmp_path / "missing.csv"))

    cleaned = data_cleaning.clean_history(history, as_of=_at(10))

    assert list(cleaned.frame["gap_slots"]) == []
    assert pd.api.types.is_integer_dtype(cleaned.frame["gap_slots"])
    assert cleaned.report["missing_slots"] == 0
    assert cleaned.report["trailing_gap_slots"] is None
    assert cleaned.report["contiguous_tail_rows"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Stuck-sensor runs and spikes across rows (CLEAN-01)
# ──────────────────────────────────────────────────────────────────────────────

def _with_values(field, values, hours=None, **kw):
    """Hourly rows (hours default 0..n-1) whose `field` column is set to `values`."""
    hours = list(range(len(values))) if hours is None else hours
    history = _hourly(hours, **kw)
    history[field] = list(values)
    return history


def _flag_list(cleaned):
    return list(cleaned.frame["clean_flags"])


def test_six_identical_readings_are_a_stuck_run_and_five_are_not():
    six = data_cleaning.clean_history(_with_values("air_temp", [21.0] * 6))
    assert _flag_list(six) == ["stuck_air_temp"] * 6
    assert len(six.usable) == 0
    assert six.report["flag_counts"]["stuck_air_temp"] == 6

    five = data_cleaning.clean_history(_with_values("air_temp", [21.0] * 5))
    assert _flag_list(five) == [""] * 5
    assert len(five.usable) == 5
    assert data_cleaning.STUCK_MIN_RUN_ROWS == 6


def test_night_time_zero_solar_is_not_a_stuck_run():
    night = data_cleaning.clean_history(_with_values("solar_radiation", [0.0] * 12))
    assert _flag_list(night) == [""] * 12

    daylight = data_cleaning.clean_history(_with_values("solar_radiation", [350.0] * 6))
    assert _flag_list(daylight) == ["stuck_solar_radiation"] * 6


def test_a_stuck_run_spans_rows_already_excluded():
    history = _with_values("wind_speed", [4.0, 4.0, 4.0, 9.0, 4.0, 4.0, 4.0])
    history["fallback"] = [False, False, False, True, False, False, False]
    history["fallback"] = history["fallback"].astype(object)

    cleaned = data_cleaning.clean_history(history)

    assert _flag_list(cleaned) == [
        "stuck_wind_speed", "stuck_wind_speed", "stuck_wind_speed",
        "fallback",
        "stuck_wind_speed", "stuck_wind_speed", "stuck_wind_speed",
    ]
    assert len(cleaned.usable) == 0


def test_missing_values_never_form_a_stuck_run():
    cleaned = data_cleaning.clean_history(_with_values("solar_radiation", [math.nan] * 6))

    assert _flag_list(cleaned) == [""] * 6
    assert len(cleaned.usable) == 6


def test_stuck_min_run_rows_can_be_overridden():
    history = _with_values("air_temp", [21.0] * 3 + [22.5, 23.5])

    assert _flag_list(data_cleaning.clean_history(history)) == [""] * 5
    cleaned = data_cleaning.clean_history(history, stuck_min_run_rows=3)

    assert _flag_list(cleaned) == ["stuck_air_temp"] * 3 + ["", ""]


def test_a_one_hour_excursion_beyond_the_step_is_a_spike():
    # The spike row is excluded and leaves its hour missing, so the row after it is after_gap.
    up = data_cleaning.clean_history(_with_values("air_temp", [20.0, 31.0, 20.0]))
    assert _flag_list(up) == ["", "spike_air_temp", "after_gap"]
    assert list(up.usable["air_temp"]) == [20.0, 20.0]

    down = data_cleaning.clean_history(_with_values("air_temp", [20.0, 9.0, 20.0]))
    assert _flag_list(down) == ["", "spike_air_temp", "after_gap"]


def test_a_difference_equal_to_the_step_is_not_a_spike():
    cleaned = data_cleaning.clean_history(_with_values("air_temp", [20.0, 30.0, 20.0]))

    assert _flag_list(cleaned) == ["", "", ""]


def test_steps_ramps_and_gaps_are_not_spikes():
    step = data_cleaning.clean_history(_with_values("air_temp", [20.0, 31.0, 31.0]))
    assert _flag_list(step) == ["", "", ""]

    ramp = data_cleaning.clean_history(_with_values("air_temp", [20.0, 31.0, 42.0]))
    assert _flag_list(ramp) == ["", "", ""]

    # The next row is two slots away, so the excursion cannot be judged a one-hour spike.
    gap = data_cleaning.clean_history(_with_values("air_temp", [20.0, 31.0, 20.0], hours=[0, 1, 3]))
    assert _flag_list(gap) == ["", "", "after_gap"]


def test_first_and_last_usable_rows_are_never_spikes():
    first = data_cleaning.clean_history(_with_values("air_temp", [31.0, 20.0, 20.0]))
    last = data_cleaning.clean_history(_with_values("air_temp", [20.0, 20.0, 31.0]))

    assert _flag_list(first) == ["", "", ""]
    assert _flag_list(last) == ["", "", ""]


def test_spike_thresholds_per_field():
    wind = data_cleaning.clean_history(_with_values("wind_speed", [2.0, 13.0, 2.0]))
    assert _flag_list(wind) == ["", "spike_wind_speed", "after_gap"]

    solar = data_cleaning.clean_history(_with_values("solar_radiation", [100.0, 900.0, 100.0]))
    assert _flag_list(solar) == ["", "spike_solar_radiation", "after_gap"]

    below = data_cleaning.clean_history(_with_values("solar_radiation", [100.0, 750.0, 100.0]))
    assert _flag_list(below) == ["", "", ""]
    assert data_cleaning.SPIKE_MAX_STEP == {
        "air_temp": 10.0, "wind_speed": 10.0, "solar_radiation": 700.0}


def test_an_oscillating_sensor_flags_every_interior_row():
    cleaned = data_cleaning.clean_history(
        _with_values("air_temp", [20.0, 31.0, 20.0, 31.0, 20.0]))

    assert _flag_list(cleaned) == [
        "", "spike_air_temp", "spike_air_temp", "spike_air_temp", "after_gap"]


def test_spike_max_step_override_replaces_the_table():
    history = _with_values("air_temp", [20.0, 26.0, 20.0])
    history["wind_speed"] = [2.0, 13.0, 2.0]

    default = data_cleaning.clean_history(history)
    assert _flag_list(default) == ["", "spike_wind_speed", "after_gap"]

    cleaned = data_cleaning.clean_history(history, spike_max_step={"air_temp": 5.0})

    # The override replaces the table: air_temp now flags, wind_speed is not checked.
    assert _flag_list(cleaned) == ["", "spike_air_temp", "after_gap"]


def test_a_missing_field_column_skips_its_rules():
    history = _with_values("air_temp", [21.0] * 6).drop(columns=["solar_radiation"])

    cleaned = data_cleaning.clean_history(history)

    assert _flag_list(cleaned) == ["stuck_air_temp"] * 6
    assert cleaned.report["flag_counts"]["stuck_solar_radiation"] == 0
    assert cleaned.report["flag_counts"]["spike_solar_radiation"] == 0
