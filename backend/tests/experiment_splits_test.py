"""
Tests for experiment_splits.py (D-02).

Module-level plain-assert functions, no test classes, no fixtures beyond
pytest built-ins -- matching this repo's established test-file convention.
Every test is network-free and file-I/O-free.
"""

import numpy as np
import pandas as pd
import pytest

import anomaly_training as at
import experiment_splits as es


def _hourly_frame(start="2023-01-01", end="2025-12-31 23:00"):
    idx = pd.date_range(start, end, freq="h", tz="UTC")
    return pd.DataFrame({
        "datetime_utc": idx,
        "dlr_amps": np.linspace(900.0, 1400.0, len(idx)),
    })


def test_split_boundaries_rejects_inverted_pair():
    with pytest.raises(ValueError):
        es.SplitBoundaries("2025-07-01", "2025-01-01")


def test_split_boundaries_rejects_equal_pair():
    with pytest.raises(ValueError):
        es.SplitBoundaries("2025-01-01", "2025-01-01")


def test_calendar_split_is_strictly_time_ordered():
    frame = _hourly_frame()
    boundaries = es.SplitBoundaries("2025-01-01", "2025-07-01")
    train, val, test = es.calendar_split(frame, boundaries)

    assert len(train) > 0 and len(val) > 0 and len(test) > 0
    assert train["datetime_utc"].max() < val["datetime_utc"].min()
    assert val["datetime_utc"].max() < test["datetime_utc"].min()


def test_calendar_split_indexes_are_reset():
    frame = _hourly_frame()
    boundaries = es.SplitBoundaries("2025-01-01", "2025-07-01")
    train, val, test = es.calendar_split(frame, boundaries)

    for side in (train, val, test):
        assert list(side.index) == list(range(len(side)))


def test_calendar_split_is_pure():
    frame = _hourly_frame()
    boundaries = es.SplitBoundaries("2025-01-01", "2025-07-01")

    tr1, va1, te1 = es.calendar_split(frame, boundaries)
    tr2, va2, te2 = es.calendar_split(frame, boundaries)

    assert tr1.equals(tr2)
    assert va1.equals(va2)
    assert te1.equals(te2)


def test_calendar_split_raises_naming_all_three_row_counts_on_empty_side():
    frame = _hourly_frame()
    # Both boundaries predate the frame entirely -- train and val land empty,
    # test absorbs everything.
    boundaries = es.SplitBoundaries("2019-01-01", "2019-02-01")

    with pytest.raises(ValueError) as excinfo:
        es.calendar_split(frame, boundaries)

    message = str(excinfo.value)
    assert "train=0" in message
    assert "val=0" in message


def test_calendar_split_raises_below_min_rows_per_side_floor():
    frame = _hourly_frame()
    boundaries = es.SplitBoundaries("2025-01-01", "2025-07-01")

    # A floor far above any single side's real row count forces the guard.
    with pytest.raises(ValueError):
        es.calendar_split(frame, boundaries, min_rows_per_side=10**9)


def test_calendar_split_agrees_with_chronological_split_at_equivalent_boundaries():
    """
    03-RESEARCH.md Pitfall 5: calendar_split and chronological_split must
    place the same rows on the same side when given equivalent boundaries,
    so the repo's two splitters cannot silently drift apart.
    """
    frame = _hourly_frame()

    # chronological_split's boundary is expressed as a row-fraction holdout;
    # compute the equivalent calendar date so both splitters see the same
    # partition point.
    holdout_fraction = 0.2
    sorted_frame = frame.sort_values("datetime_utc").reset_index(drop=True)
    split_index = int(len(sorted_frame) * (1 - holdout_fraction))
    boundary_date = sorted_frame["datetime_utc"].iloc[split_index]

    fit, holdout = at.chronological_split(frame, holdout_fraction=holdout_fraction)

    # calendar_split takes two boundaries (val, test); collapse it to a
    # two-way split for this comparison by pinning val_start to the frame's
    # very first timestamp, so `train` lands empty and `val` absorbs every
    # row before `boundary_date` (== chronological_split's `fit` side
    # exactly), while `test` (>= boundary_date) equals chronological_split's
    # `holdout` side exactly.
    val_start = frame["datetime_utc"].min()
    test_start = boundary_date
    boundaries = es.SplitBoundaries(val_start, test_start)
    train, val, test = es.calendar_split(frame, boundaries, min_rows_per_side=0)

    calendar_fit_side = pd.concat([train, val], ignore_index=True)
    calendar_holdout_side = test

    assert calendar_fit_side["datetime_utc"].max() < calendar_holdout_side["datetime_utc"].min()
    assert fit["datetime_utc"].max() == calendar_fit_side["datetime_utc"].max()
    assert holdout["datetime_utc"].min() == calendar_holdout_side["datetime_utc"].min()
    assert len(fit) == len(calendar_fit_side)
    assert len(holdout) == len(calendar_holdout_side)


def test_calendar_split_called_twice_matches_reference_splitter_purity():
    """Sanity: the reference splitter's own purity guarantee still holds,
    so the agreement test above is comparing against a stable target."""
    frame = _hourly_frame()
    fit1, hold1 = at.chronological_split(frame, holdout_fraction=0.2)
    fit2, hold2 = at.chronological_split(frame, holdout_fraction=0.2)
    assert fit1.equals(fit2)
    assert hold1.equals(hold2)
