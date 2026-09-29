"""
Three-Way Calendar Train/Val/Test Split (D-02, Phase 3 experiment)
=====================================================================
This module generalizes `anomaly_training.chronological_split`, which
already solved the sort-by-`datetime_utc`, the `reset_index(drop=True)` on
every returned side, the purity guarantee ("called twice on the same frame
returns identical slices"), the empty-side `ValueError` naming all row
counts, and the minimum-rows floor for the TWO-way, ROW-FRACTION case
(`backend/anomaly_training.py:394-438`). This module extends that same
shape to THREE ways and to CALENDAR DATES, because D-02 asks for a fixed
calendar train/val/test split rather than a row-fraction holdout.

`03-CONTEXT.md`'s claim, under its "Facts confirmed by direct code/API
investigation (do not re-derive)" heading, that "no fixed train/val/test
split exists anywhere in this repo" is INCORRECT -- `chronological_split`
is exactly that, just two-way and row-fraction-based. This module's tests
assert `calendar_split` and `chronological_split` agree at equivalent
boundaries precisely so a future reader does not re-derive the same guard
conditions a third time, and so the two splitters cannot silently drift
apart (03-RESEARCH.md Pitfall 5).

Standalone module -- imported by `forecast_experiment.py`; imports nothing
from this repo itself. Importing this module performs no network call, no
file I/O and no environment variable read.
"""

import pandas as pd


def _to_utc_timestamp(value) -> pd.Timestamp:
    """
    Coerce a bare-date string, an ISO-8601 string, or a `pd.Timestamp` into
    a tz-aware UTC `pd.Timestamp` -- a naive-vs-aware comparison against a
    `datetime_utc` column (always tz-aware UTC in this repo) raises
    `TypeError` rather than silently doing the wrong thing, so this
    coercion happens once, here, rather than being left to the caller.
    """
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


class SplitBoundaries:
    """
    A small value object carrying the two calendar boundary dates that
    partition a frame into (train, val, test):

    - `train`: strictly before `val_start`.
    - `val`: at or after `val_start`, strictly before `test_start`.
    - `test`: at or after `test_start`.

    Raises `ValueError` naming both boundaries when `val_start` is not
    strictly before `test_start` -- an inverted or equal pair of boundaries
    can never produce a non-empty val side.
    """

    def __init__(self, val_start, test_start):
        val_start = _to_utc_timestamp(val_start)
        test_start = _to_utc_timestamp(test_start)
        if not val_start < test_start:
            raise ValueError(
                f"SplitBoundaries: val_start ({val_start}) must be "
                f"strictly before test_start ({test_start})"
            )
        self.val_start = val_start
        self.test_start = test_start

    def __repr__(self):
        return (
            f"SplitBoundaries(val_start={self.val_start!r}, "
            f"test_start={self.test_start!r})"
        )


def calendar_split(
    frame: pd.DataFrame, boundaries: SplitBoundaries, min_rows_per_side: int = 1,
) -> tuple:
    """
    Split `frame` (any `datetime_utc`-bearing frame) into a strictly
    time-ordered (train, val, test) triple on the two calendar dates in
    `boundaries`.

    Sorts by `datetime_utc`, partitions on the two calendar boundaries
    (train strictly before `boundaries.val_start`; val at or after
    `boundaries.val_start` and strictly before `boundaries.test_start`;
    test at or after `boundaries.test_start`), and resets every side's
    index -- carrying over `chronological_split`'s exact discipline for
    each of these steps. Pure: the same input returns the same slices
    (asserted by test, not merely stated).

    Raises `ValueError` naming all three row counts and both boundaries
    when any side would be empty or below `min_rows_per_side` -- carrying
    over `chronological_split`'s empty-side guard, generalized to three
    sides.
    """
    sorted_frame = frame.sort_values("datetime_utc").reset_index(drop=True)
    dt = sorted_frame["datetime_utc"]

    train_mask = dt < boundaries.val_start
    val_mask = (dt >= boundaries.val_start) & (dt < boundaries.test_start)
    test_mask = dt >= boundaries.test_start

    train = sorted_frame[train_mask].reset_index(drop=True)
    val = sorted_frame[val_mask].reset_index(drop=True)
    test = sorted_frame[test_mask].reset_index(drop=True)

    if len(train) < min_rows_per_side or len(val) < min_rows_per_side or len(test) < min_rows_per_side:
        raise ValueError(
            f"calendar_split: split produced a side below the "
            f"min_rows_per_side={min_rows_per_side} floor "
            f"(train={len(train)}, val={len(val)}, test={len(test)}) at "
            f"boundaries={boundaries!r}, from {len(sorted_frame)} total "
            f"row(s)"
        )

    return train, val, test
