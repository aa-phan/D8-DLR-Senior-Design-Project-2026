"""
Tests for backend/tceq_provider.py (C4, Phase 9 / WX-01).

Follows backend/tests/asos_provider_test.py's `_FakeResponse` +
`monkeypatch.setattr(module.requests, "get", ...)` convention to avoid a
live network call. Module-level plain-assert functions, no test classes --
matches every existing test file's convention in this project.

Fixtures are small hand-built HTML strings matching `daily_summary.pl`'s
confirmed table shape (one `<h1><a ...CAMS=id>`, one `<table border='1'>`,
a header row of four-digit hour labels, and one `<tr>` per parameter with a
`<strong>` label cell and hourly `<td>` cells) -- built by `_report_html`,
which takes the hour count as an argument so Plan 09-02 can reuse it.

This is Plan 09-01 Task 3's tracer group: one city (Corpus Christi, CAMS
83), one calendar day, proving the vertical slice end to end. RH-absent
sites and multi-day windows are Plan 09-02's expansion.
"""

import pandas as pd
import pytest

import tceq_provider
from units_def import Q

_CAMS_83 = "83"
_START = "2026-07-01T00:00:00Z"
_END = "2026-07-01T23:59:59Z"
_JAN_START = "2026-01-15T00:00:00Z"
_JAN_END = "2026-01-15T23:59:59Z"

_HOUR_LABELS = ["0000", "0100", "0200", "0300"]


class _FakeResponse:
    def __init__(self, text):
        self._text = text

    def raise_for_status(self):
        pass

    @property
    def text(self):
        return self._text


def _mock_get(monkeypatch, text):
    monkeypatch.setattr(tceq_provider.requests, "get", lambda *a, **k: _FakeResponse(text))


def _report_html(
    cams_id: str,
    hour_labels: list,
    rows: dict,
    site_name: str = "Corpus Christi C83",
) -> str:
    """
    Build a minimal daily_summary.pl-shaped report: one <h1><a> carrying
    CAMS=<cams_id>, one <table border='1'> with a header row of hour
    labels and one <tr> per (label -> values) entry in `rows`. Each data
    row's first cell holds <a><strong>label</strong></a>, followed by one
    <td> per hourly value, a repeated-label cell, and a POC cell -- the
    live-confirmed shape `_extract_row_values` slices against.
    """
    header_cells = "".join(f"<td>{h}</td>" for h in hour_labels)
    header_row = f"<tr><td>&nbsp;</td>{header_cells}<td>Parameter Measured</td><td>POC</td></tr>"

    row_htmls = []
    for label, values in rows.items():
        value_cells = "".join(f"<td>{v}</td>" for v in values)
        row_htmls.append(
            f"<tr><td><a href='#'><strong>{label}</strong></a></td>"
            f"{value_cells}<td>{label}</td><td>1</td></tr>"
        )

    table = f"<table border='1'>{header_row}{''.join(row_htmls)}</table>"
    return (
        "<html><body>"
        f"<h1><a href='daily_summary.pl?CAMS={cams_id}&region=14'>{site_name}</a></h1>"
        f"{table}"
        "</body></html>"
    )


# The tracer's primary fixture: all four target rows plus a
# "Resultant Wind Direction" row and a "Std. Dev. Wind Direction" row (both
# contain the substring "Wind Direction"), so the label-exactness test has
# something to collide with (09-RESEARCH.md Pattern 2).
_WIND_SPEED_MPH = [5.0, 10.0, 15.0, 20.0]
_WIND_DIRECTION_DEG = [180.0, 190.0, 200.0, 210.0]
_RESULTANT_WIND_DIRECTION_DEG = [90.0, 91.0, 92.0, 93.0]
_STD_DEV_WIND_DIRECTION_DEG = [5.0, 6.0, 7.0, 8.0]
_OUTDOOR_TEMP_DEGF = [75.0, 76.0, 77.0, 78.0]
_RELATIVE_HUMIDITY_PCT = [55.0, 56.0, 57.0, 58.0]

_PRIMARY_ROWS = {
    "Wind Speed": _WIND_SPEED_MPH,
    "Wind Direction": _WIND_DIRECTION_DEG,
    "Resultant Wind Direction": _RESULTANT_WIND_DIRECTION_DEG,
    "Std. Dev. Wind Direction": _STD_DEV_WIND_DIRECTION_DEG,
    "Outdoor Temperature": _OUTDOOR_TEMP_DEGF,
    "Relative Humidity": _RELATIVE_HUMIDITY_PCT,
}

_PRIMARY_HTML = _report_html(_CAMS_83, _HOUR_LABELS, _PRIMARY_ROWS)


def test_fetch_tceq_parses_into_pipeline_columns(monkeypatch):
    _mock_get(monkeypatch, _PRIMARY_HTML)

    result = tceq_provider.fetch_tceq(_CAMS_83, _START, _END)

    assert list(result.columns) == [
        "datetime_utc",
        "air_temp",
        "wind_speed",
        "wind_direction",
        "relative_humidity",
    ]
    assert len(result) == len(_HOUR_LABELS)


def test_fetch_tceq_converts_units(monkeypatch):
    _mock_get(monkeypatch, _PRIMARY_HTML)

    result = tceq_provider.fetch_tceq(_CAMS_83, _START, _END)

    expected_temp = [Q(v, "degF").to("degC").value for v in _OUTDOOR_TEMP_DEGF]
    expected_wind = [Q(v, "mph").to("m/s").value for v in _WIND_SPEED_MPH]

    assert list(result["air_temp"]) == pytest.approx(expected_temp)
    assert list(result["wind_speed"]) == pytest.approx(expected_wind)
    assert list(result["wind_direction"]) == _WIND_DIRECTION_DEG
    assert list(result["relative_humidity"]) == _RELATIVE_HUMIDITY_PCT


def test_fetch_tceq_request_carries_select_date_user(monkeypatch):
    recorded = {}

    def _recorder(url, params=None, timeout=None):
        recorded["params"] = params
        return _FakeResponse(_PRIMARY_HTML)

    monkeypatch.setattr(tceq_provider.requests, "get", _recorder)

    tceq_provider.fetch_tceq(_CAMS_83, _START, _END)

    params = recorded["params"]
    assert params["select_date"] == "user"
    assert params["time_format"] == "24hr"
    assert params["cams"] == _CAMS_83
    assert params["user_month"] == 6  # July -> 0-indexed 6, never 7
    assert params["user_day"] == 1
    assert params["user_year"] == 2026


def test_fetch_tceq_single_day_window_issues_exactly_one_request(monkeypatch):
    counter = {"count": 0}

    def _counting_recorder(*a, **k):
        counter["count"] += 1
        return _FakeResponse(_PRIMARY_HTML)

    monkeypatch.setattr(tceq_provider.requests, "get", _counting_recorder)

    tceq_provider.fetch_tceq(_CAMS_83, _START, _END)

    assert counter["count"] == 1


def test_fetch_tceq_applies_fixed_utc_offset_not_dst(monkeypatch):
    _mock_get(monkeypatch, _PRIMARY_HTML)

    july_result = tceq_provider.fetch_tceq(_CAMS_83, _START, _END)
    january_result = tceq_provider.fetch_tceq(_CAMS_83, _JAN_START, _JAN_END)

    # CAMS 83's fixed offset is -6 (CST, never DST-adjusted) in both months.
    # Real local clock time in July is CDT, but the report is never
    # DST-adjusted -- hour 0000 must still convert with the same -6 offset.
    assert july_result["datetime_utc"].iloc[0] == pd.Timestamp("2026-07-01T06:00:00Z")
    assert january_result["datetime_utc"].iloc[0] == pd.Timestamp("2026-01-15T06:00:00Z")


def test_fetch_tceq_matches_row_labels_exactly(monkeypatch):
    _mock_get(monkeypatch, _PRIMARY_HTML)

    result = tceq_provider.fetch_tceq(_CAMS_83, _START, _END)

    # Must hold the "Wind Direction" row's values, not "Resultant Wind
    # Direction"'s or "Std. Dev. Wind Direction"'s -- a substring match
    # would silently grab one of the other two rows instead.
    assert list(result["wind_direction"]) == _WIND_DIRECTION_DEG
    assert list(result["wind_direction"]) != _RESULTANT_WIND_DIRECTION_DEG
    assert list(result["wind_direction"]) != _STD_DEV_WIND_DIRECTION_DEG


def test_fetch_tceq_range_check_rejects_an_unconverted_value(monkeypatch):
    # 150 mph converts to ~67 m/s, outside PIPELINE_SCHEMA's wind_speed
    # range [0.0, 50.0] -- proving the range-check backstop catches a
    # genuinely out-of-range value even after a correct conversion.
    rows = dict(_PRIMARY_ROWS)
    rows["Wind Speed"] = [150.0, 10.0, 15.0, 20.0]
    html = _report_html(_CAMS_83, _HOUR_LABELS, rows)
    _mock_get(monkeypatch, html)

    with pytest.raises(ValueError) as excinfo:
        tceq_provider.fetch_tceq(_CAMS_83, _START, _END)

    message = str(excinfo.value)
    assert "wind_speed" in message
    assert "0.0" in message
    assert "50.0" in message


def test_tceq_provider_import_has_no_side_effects(monkeypatch):
    """
    Guards the module docstring's no-side-effects-on-import contract:
    importing tceq_provider must never issue a network call (mirrors
    weather_provider_test.py::test_module_import_has_no_side_effects).
    """
    counter = {"count": 0}

    def _counting_recorder(*a, **k):
        counter["count"] += 1
        return _FakeResponse(_PRIMARY_HTML)

    monkeypatch.setattr(tceq_provider.requests, "get", _counting_recorder)

    import importlib

    importlib.reload(tceq_provider)

    assert counter["count"] == 0


# ──────────────────────────────────────────────────────────────────────────
# Plan 09-02 Task 1: multi-day window decomposition, deterministic ordering,
# and the two window-level raises (D-09).
# ──────────────────────────────────────────────────────────────────────────

_FULL_HOUR_LABELS = [f"{h:02d}00" for h in range(24)]


def _full_day_rows(seed: float = 0.0) -> dict:
    """
    Build a full 24-hour set of the four primary target rows, with values
    offset by `seed` so two different fixtures are distinguishable (used by
    the dedup test to prove which call's data survived).
    """
    return {
        "Wind Speed": [5.0 + seed + h * 0.1 for h in range(24)],
        "Wind Direction": [180.0 + (seed % 90) + h for h in range(24)],
        "Outdoor Temperature": [70.0 + seed + h * 0.1 for h in range(24)],
        "Relative Humidity": [50.0 + (seed % 40) + h * 0.1 for h in range(24)],
    }


def _full_day_html(cams_id: str, seed: float = 0.0) -> str:
    return _report_html(cams_id, _FULL_HOUR_LABELS, _full_day_rows(seed))


# A 3-local-calendar-day window for CAMS 83 (fixed offset -6): local midnight
# of 2026-07-01 is 2026-07-01T06:00:00Z, and local 23:59:59 of 2026-07-03 is
# 2026-07-04T05:59:59Z -- chosen so the window boundaries land exactly on
# local calendar-day edges, giving exactly 3 spanned days (07-01, 07-02,
# 07-03), not 2 or 4.
_MULTI_DAY_START = "2026-07-01T06:00:00Z"
_MULTI_DAY_END = "2026-07-04T05:59:59Z"


def test_fetch_tceq_multi_day_window_issues_one_request_per_day(monkeypatch):
    recorded = []

    def _recorder(url, params=None, timeout=None):
        recorded.append(params)
        return _FakeResponse(_full_day_html(_CAMS_83))

    monkeypatch.setattr(tceq_provider.requests, "get", _recorder)

    tceq_provider.fetch_tceq(_CAMS_83, _MULTI_DAY_START, _MULTI_DAY_END)

    assert len(recorded) == 3
    triples = [(p["user_year"], p["user_month"], p["user_day"]) for p in recorded]
    # Distinctness is the actual assertion that matters: three identical
    # triples is precisely the silent-mis-dating failure a bare count check
    # would miss (09-RESEARCH.md Pitfall 1's warning sign).
    assert len(set(triples)) == 3, triples
    assert triples == sorted(triples)
    for p in recorded:
        assert p["select_date"] == "user"


def test_fetch_tceq_concatenates_days_in_order(monkeypatch):
    _mock_get(monkeypatch, _full_day_html(_CAMS_83))

    result = tceq_provider.fetch_tceq(_CAMS_83, _MULTI_DAY_START, _MULTI_DAY_END)

    assert result["datetime_utc"].is_monotonic_increasing
    assert not result["datetime_utc"].duplicated().any()


def test_fetch_tceq_day_boundary_rows_are_distinct_and_adjacent(monkeypatch):
    _mock_get(monkeypatch, _full_day_html(_CAMS_83))

    result = tceq_provider.fetch_tceq(_CAMS_83, _MULTI_DAY_START, _MULTI_DAY_END)

    times = list(result["datetime_utc"])
    diffs = [times[i + 1] - times[i] for i in range(len(times) - 1)]
    assert all(d == pd.Timedelta(hours=1) for d in diffs)
    assert len(times) == len(set(times))  # no timestamp duplicated


def test_fetch_tceq_drops_duplicate_timestamps_keeping_first(monkeypatch):
    # Force the day-decomposition to request the SAME calendar day twice --
    # a defensive scenario the real decomposition must never itself produce,
    # but the concat/sort/dedupe sequence must still resolve correctly if it
    # ever did (e.g. a live report changing between two fetches of the same
    # day). The recorder returns a DIFFERENT fixture on each call; the
    # earlier call's values must be the ones that survive.
    day = pd.Timestamp("2026-07-01", tz="UTC").date()
    monkeypatch.setattr(tceq_provider, "_days_spanned", lambda *a, **k: [day, day])

    responses = [_full_day_html(_CAMS_83, seed=0.0), _full_day_html(_CAMS_83, seed=1000.0)]
    calls = {"n": 0}

    def _recorder(url, params=None, timeout=None):
        html = responses[calls["n"]]
        calls["n"] += 1
        return _FakeResponse(html)

    monkeypatch.setattr(tceq_provider.requests, "get", _recorder)

    result = tceq_provider.fetch_tceq(_CAMS_83, _START, _END)

    assert not result["datetime_utc"].duplicated().any()
    assert result["wind_speed"].iloc[0] == pytest.approx(Q(5.0, "mph").to("m/s").value)


def test_fetch_tceq_is_reproducible_for_the_same_window(monkeypatch):
    _mock_get(monkeypatch, _full_day_html(_CAMS_83))

    first = tceq_provider.fetch_tceq(_CAMS_83, _MULTI_DAY_START, _MULTI_DAY_END)
    second = tceq_provider.fetch_tceq(_CAMS_83, _MULTI_DAY_START, _MULTI_DAY_END)

    pd.testing.assert_frame_equal(first, second)


def test_fetch_tceq_raises_when_the_window_selects_zero_rows(monkeypatch):
    # A report with a header row but zero hour-label columns contributes no
    # rows at all -- the window-level empty check is what must catch this,
    # since a single day yielding nothing is not itself a raise condition.
    empty_hour_html = _report_html(_CAMS_83, [], {})
    _mock_get(monkeypatch, empty_hour_html)

    with pytest.raises(ValueError) as excinfo:
        tceq_provider.fetch_tceq(_CAMS_83, _START, _END)

    message = str(excinfo.value)
    assert "2026-07-01" in message


_FORTY_DAY_START = "2026-01-01T06:00:00Z"
_FORTY_DAY_END = str(pd.Timestamp(_FORTY_DAY_START) + pd.Timedelta(days=40) - pd.Timedelta(seconds=1))


def test_fetch_tceq_raises_when_the_window_exceeds_the_day_cap(monkeypatch):
    counter = {"count": 0}

    def _recorder(*a, **k):
        counter["count"] += 1
        return _FakeResponse(_full_day_html(_CAMS_83))

    monkeypatch.setattr(tceq_provider.requests, "get", _recorder)

    with pytest.raises(ValueError) as excinfo:
        tceq_provider.fetch_tceq(_CAMS_83, _FORTY_DAY_START, _FORTY_DAY_END)

    message = str(excinfo.value)
    assert "40" in message
    assert "31" in message
    assert counter["count"] == 0


def test_fetch_tceq_accepts_iso_and_bare_date_windows(monkeypatch):
    _mock_get(monkeypatch, _full_day_html(_CAMS_83))

    iso_result = tceq_provider.fetch_tceq(_CAMS_83, "2026-07-01T00:00Z", "2026-07-01T23:59:59Z")
    bare_result = tceq_provider.fetch_tceq(_CAMS_83, "2026-07-01", "2026-07-01")

    assert not iso_result.empty
    assert not bare_result.empty
