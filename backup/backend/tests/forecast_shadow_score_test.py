"""
Tests for `backend/forecast_shadow_score.py`, the per-city shadow-log scorer
(quick task 261013-285). Synthetic v3 records only, mocked HTTP only; every
file lives under `tmp_path`. No test reads `data/experiment` or any real log.
"""

from __future__ import annotations

import builtins
import json
import os

import numpy as np
import pandas as pd
import pytest
import requests

import city_point
import config
import forecast_shadow_eval_core as core
import forecast_shadow_pipeline
import forecast_shadow_score as score_mod
import thermal_model

SENTINEL = 4321.987
INSTANT = core.EVALUATION_INSTANT_DEFAULT
CUTOFF = core.VALID_TIME_CUTOFF_DEFAULT
ABSENT = object()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload=None, status=200, raw=None):
        self.status_code = status
        self.content = raw if raw is not None else json.dumps(payload).encode("utf-8")
        self.headers = {"Date": "Tue, 24 Nov 2026 00:00:01 GMT", "Content-Type": "application/json"}

    def json(self):
        return json.loads(self.content.decode("utf-8"))

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


def _weather_at(ts: pd.Timestamp) -> dict:
    h = ts.hour + 24 * ts.dayofyear
    return {
        "temperature_2m": 18.0 + 9.0 * np.sin(2 * np.pi * ts.hour / 24) + (h % 3),
        "wind_speed_10m": 1.5 + (h % 7) * 0.6,
        "wind_direction_10m": float((h * 37) % 360),
        "shortwave_radiation": float(max(0.0, 700.0 * np.sin(np.pi * (ts.hour - 6) / 12))) if 6 <= ts.hour <= 18 else 0.0,
        "relative_humidity_2m": 50.0 + (h % 11),
    }


def archive_payload(start: str, end: str, *, null_hours=()) -> dict:
    times = pd.date_range(pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(hours=23), freq="h")
    hourly = {"time": [t.strftime("%Y-%m-%dT%H:%M") for t in times]}
    for key in ("temperature_2m", "wind_speed_10m", "wind_direction_10m", "shortwave_radiation", "relative_humidity_2m"):
        hourly[key] = [_weather_at(t.tz_localize("UTC"))[key] for t in times]
    for ts in null_hours:
        hourly["wind_speed_10m"][hourly["time"].index(pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M"))] = None
    return {"hourly": hourly, "hourly_units": {"temperature_2m": "°C", "wind_speed_10m": "m/s", "wind_direction_10m": "°",
                                               "shortwave_radiation": "W/m²", "relative_humidity_2m": "%"}}


def truth_at(city: str, ts) -> float:
    """Independent truth ampacity for one hour (thermal_model + city_point)."""
    ts = pd.Timestamp(ts)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    w = _weather_at(ts)
    point = city_point.city_point(city)
    perp = thermal_model.perpendicular_wind(np.array([w["wind_speed_10m"]]), np.array([w["wind_direction_10m"]]), point.bearing_deg)
    return float(np.asarray(thermal_model.ieee738_ampacity(
        np.array([w["temperature_2m"]]), perp, np.array([w["shortwave_radiation"]]), point.conductor))[0])


def install_archive(monkeypatch, *, fail_cities=(), null_hours=()):
    calls = []

    def fake_get(url, params=None, **kwargs):
        calls.append((url, dict(params), kwargs))
        lat = params["latitude"]
        city = next(c for c, (la, _) in config.CITY_COORDINATES.items() if la == lat)
        if city in fail_cities:
            return _FakeResponse(raw=b"service unavailable", status=503)
        return _FakeResponse(archive_payload(params["start_date"], params["end_date"], null_hours=null_hours))
    monkeypatch.setattr(requests, "get", fake_get)
    return calls


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("requests.get must not be called in this test")
    monkeypatch.setattr(requests, "get", boom)


def make_candidate(amps, *, status="ok", fallback=False, anchor=None, window_end=None, reason=None):
    cand = {"status": status, "ampacity_amps": amps, "fallback_used": fallback, "fallback_reason": None,
            "model_version": "x@stamp", "input_provenance": None, "reason": reason,
            "bundle": {"status": "ok", "bundle_ampacity_amps": 2 * (amps or 0)}}
    if anchor is not None:
        cand["input_provenance"] = {"anchor_provenance": anchor}
    if window_end is not None:
        cand["input_provenance"] = {"truth_proxy_window_start": (pd.Timestamp(window_end) - pd.Timedelta(hours=6)).isoformat(),
                                    "truth_proxy_window_end": pd.Timestamp(window_end).isoformat()}
    return cand


def make_row(city, valid, *, decision=None, model="gfs_seamless", logged_at=None, amps=None, horizon=1440, init=None,
             overrides=None, anchor_source="synoptic", anchor_age_h=1.0, schema=3):
    valid = pd.Timestamp(valid)
    valid = valid.tz_localize("UTC") if valid.tzinfo is None else valid
    decision = pd.Timestamp(decision) if decision is not None else valid - pd.Timedelta(hours=14, minutes=3)
    decision = decision.tz_localize("UTC") if decision.tzinfo is None else decision
    amps = amps or {}
    anchor = {"anchor_source": anchor_source, "anchor_station": "KAUS",
              "anchor_observation_time": (decision - pd.Timedelta(hours=anchor_age_h)).isoformat()}
    cands = {
        "ml_wind_corrected": make_candidate(amps.get("ml_wind_corrected", SENTINEL), anchor=anchor),
        "ml_cooling_corrected": make_candidate(amps.get("ml_cooling_corrected", SENTINEL), anchor=anchor),
        "raw_forecast": make_candidate(amps.get("raw_forecast", SENTINEL)),
        "persistence_24h": make_candidate(amps.get("persistence_24h", SENTINEL)),
        "reference_ml_refit_24h": make_candidate(amps.get("reference_ml_refit_24h", SENTINEL), window_end=decision),
    }
    for name, value in (overrides or {}).items():
        cands[name] = value
    row = {"schema_version": schema, "city": city,
           "initialization_time": (valid - pd.Timedelta(hours=24) if init is None else pd.Timestamp(init)).isoformat(),
           "availability_time": (valid - pd.Timedelta(hours=18)).isoformat(),
           "decision_time": decision.isoformat(), "valid_time": valid.isoformat(), "horizon_minutes": horizon,
           "logged_at": (logged_at or decision + pd.Timedelta(minutes=1)).isoformat() if not isinstance(logged_at, str) else logged_at,
           "basis_caveat": "x", "candidates": cands}
    if model is not ABSENT:
        row["forecast_model"] = model
    return row


def write_log(path, rows, extra_lines=()):
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
        for line in extra_lines:
            fh.write(line + "\n")


def guard_cfg(**kw):
    return core.GuardConfig(**kw)


# --------------------------------------------------------------------------
# Reader
# --------------------------------------------------------------------------

def test_reader_accepts_exactly_what_read_city_log_entries_accepts(tmp_path, monkeypatch):
    good1 = make_row("AUSTIN", "2026-10-20T00:00:00Z")
    good2 = make_row("AUSTIN", "2026-10-20T06:00:00Z", model=ABSENT)
    lines = [
        json.dumps(good1), "", "   ", "{not json", json.dumps([1, 2]), json.dumps("str"),
        json.dumps({"schema_version": True, "city": "AUSTIN"}),
        json.dumps({"schema_version": "3", "city": "AUSTIN"}),
        json.dumps({"city": "AUSTIN", "candidates": {}}),                              # v1 flat
        json.dumps({"schema_version": 1, "city": "AUSTIN"}),                           # v1 flat
        json.dumps({"schema_version": 2, "corridor": "AUSTIN_CORPUS_CHRISTI", "candidates": {}}),  # v2
        json.dumps({"schema_version": 3, "corridor": "AUSTIN_CORPUS_CHRISTI"}),        # corridor-only
        json.dumps(make_row("MIDLAND", "2026-10-20T00:00:00Z")),                       # other city
        json.dumps(good2),
    ]
    path = tmp_path / "AUSTIN.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    monkeypatch.setattr(forecast_shadow_pipeline, "SHADOW_PREDICTIONS_DIR", str(tmp_path))
    expected = forecast_shadow_pipeline.read_city_log_entries("AUSTIN")
    entries, counters = score_mod.read_scorable_log(str(path), "AUSTIN")
    assert [e for _, e in entries] == expected and len(expected) == 2
    assert [n for n, _ in entries] == [1, 14]
    assert counters["blank"] == 2
    assert counters["malformed"] == 5            # bad json, list, str, bool version, str version
    assert counters["legacy_v1_flat"] == 2
    assert counters["legacy_v2_corridor"] == 2
    assert counters["other_city_or_schema"] == 1
    assert counters["accepted_rows"] == 2 and counters["lines_total"] == len(lines)
    assert (counters["lines_total"] == counters["blank"] + counters["malformed"] + counters["legacy_v1_flat"]
            + counters["legacy_v2_corridor"] + counters["other_city_or_schema"] + counters["accepted_rows"])


def test_reader_missing_file_is_empty(tmp_path):
    entries, counters = score_mod.read_scorable_log(str(tmp_path / "none.jsonl"), "AUSTIN")
    assert entries == [] and counters["accepted_rows"] == 0 and counters["file_missing"] is True


# --------------------------------------------------------------------------
# Row selection
# --------------------------------------------------------------------------

def _select(rows, city="AUSTIN", cfg=None):
    entries = [(i + 1, r) for i, r in enumerate(rows)]
    return score_mod.select_rows(entries, city, cfg or guard_cfg())


def test_v6_row_logged_first_is_excluded_and_the_later_gfs_row_is_kept():
    v = "2026-10-20T00:00:00Z"
    v6 = make_row("AUSTIN", v, model=ABSENT, logged_at=pd.Timestamp("2026-10-19T09:00:00Z"))
    gfs = make_row("AUSTIN", v, model="gfs_seamless", logged_at=pd.Timestamp("2026-10-19T10:00:00Z"))
    frame, counters, dups = _select([v6, gfs])
    assert counters["missing_forecast_model"] == 1 and counters["duplicate_valid_time"] == 0
    assert list(frame["line_no"]) == [2] and dups == []
    assert counters["forecast_model_counts"] == {"<missing>": 1, "gfs_seamless": 1}


def test_empty_and_null_forecast_model_count_as_missing_not_ecmwf():
    rows = [make_row("AUSTIN", "2026-10-20T00:00:00Z", model=None), make_row("AUSTIN", "2026-10-20T06:00:00Z", model=""),
            make_row("AUSTIN", "2026-10-20T12:00:00Z", model=7)]
    _, counters, _ = _select(rows)
    assert counters["missing_forecast_model"] == 3 and counters["other_forecast_model"] == 0


def test_explicit_other_model_is_excluded_with_a_per_model_count():
    rows = [make_row("AUSTIN", "2026-10-20T00:00:00Z", model="ecmwf_ifs"), make_row("AUSTIN", "2026-10-20T06:00:00Z", model="ecmwf_ifs"),
            make_row("AUSTIN", "2026-10-20T12:00:00Z", model="icon_seamless"), make_row("AUSTIN", "2026-10-20T18:00:00Z")]
    frame, counters, _ = _select(rows)
    assert counters["other_forecast_model"] == 3
    assert counters["other_forecast_model_by_model"] == {"ecmwf_ifs": 2, "icon_seamless": 1}
    assert len(frame) == 1


@pytest.mark.parametrize("kwargs,detail", [
    ({"horizon": 60}, "horizon_not_1440"),
    ({"horizon": True}, "horizon_not_1440"),
    ({"init": "2026-10-19T01:00:00+00:00"}, "init_not_valid_minus_24h"),
    ({"decision": "2026-10-19T06:00:00+00:00"}, "decision_gap_outside_11_17h"),        # gap 18 h
    ({"decision": "2026-10-19T13:00:00+00:00"}, "decision_gap_outside_11_17h"),        # gap exactly 11 h: excluded
    ({"decision": "2026-10-19T08:00:00+00:00"}, None),                                  # gap exactly 16 h: kept
    ({"decision": "2026-10-19T07:00:00+00:00"}, None),                                  # gap exactly 17 h: kept
    ({"decision": "2026-10-19T12:59:00+00:00"}, None),                                  # gap 11 h 1 min: kept
    ({"decision": "2026-10-20T01:00:00+00:00"}, "decision_gap_outside_11_17h"),        # decision after valid
])
def test_lead_structure_boundaries(kwargs, detail):
    row = make_row("AUSTIN", "2026-10-20T00:00:00Z", **kwargs)
    frame, counters, _ = _select([row])
    if detail is None:
        assert len(frame) == 1 and counters["lead_structure_mismatch"] == 0
    else:
        assert len(frame) == 0 and counters["lead_structure_mismatch"] == 1
        assert counters["lead_structure_detail"][detail] >= 1


def test_valid_time_off_the_six_hour_grid_is_a_lead_mismatch():
    row = make_row("AUSTIN", "2026-10-20T05:00:00Z")
    _, counters, _ = _select([row])
    assert counters["lead_structure_mismatch"] == 1 and "valid_time_off_6h_grid" in counters["lead_structure_detail"]
    row = make_row("AUSTIN", "2026-10-20T06:30:00Z")
    _, counters, _ = _select([row])
    assert counters["lead_structure_mismatch"] == 1


def test_cutoff_is_strict():
    at = make_row("AUSTIN", "2026-11-17T00:00:00Z")
    before = make_row("AUSTIN", "2026-11-16T18:00:00Z")
    after = make_row("AUSTIN", "2026-11-17T06:00:00Z")
    frame, counters, _ = _select([at, before, after])
    assert counters["at_or_after_cutoff"] == 2
    assert list(frame["valid_time"]) == [pd.Timestamp("2026-11-16T18:00:00Z")]


def test_first_logged_duplicate_wins_and_duplicates_are_listed_with_inversions():
    v = "2026-10-20T00:00:00Z"
    first = make_row("AUSTIN", v, decision="2026-10-19T09:30:00+00:00", logged_at=pd.Timestamp("2026-10-19T09:31:00Z"))
    later = make_row("AUSTIN", v, decision="2026-10-19T08:30:00+00:00", logged_at=pd.Timestamp("2026-10-19T08:31:00Z"))  # earlier logged_at, later in file
    third = make_row("AUSTIN", v, decision="2026-10-19T10:30:00+00:00", logged_at=pd.Timestamp("2026-10-19T10:31:00Z"))
    frame, counters, dups = _select([first, later, third])
    assert list(frame["line_no"]) == [1] and counters["duplicate_valid_time"] == 2
    assert [d["line_no"] for d in dups] == [2, 3] and all(d["kept_line_no"] == 1 for d in dups)
    assert dups[0]["decision_time"] == "2026-10-19T08:30:00+00:00" and dups[0]["logged_at"].startswith("2026-10-19T08:31")
    assert counters["logged_at_inversions"] == 1


def test_bad_timestamps_are_counted_before_everything_else():
    row = make_row("AUSTIN", "2026-10-20T00:00:00Z", model=ABSENT)
    row["valid_time"] = "not a time"
    r2 = make_row("AUSTIN", "2026-10-20T06:00:00Z")
    r2.pop("decision_time")
    _, counters, _ = _select([row, r2])
    assert counters["bad_timestamps"] == 2 and counters["missing_forecast_model"] == 0


def test_row_level_accounting_identity():
    rows = [
        make_row("AUSTIN", "2026-10-20T00:00:00Z", model=ABSENT),                      # V6
        make_row("AUSTIN", "2026-10-20T06:00:00Z", model="ecmwf_ifs"),                  # other
        make_row("AUSTIN", "2026-10-20T12:00:00Z", horizon=60),                         # lead
        make_row("AUSTIN", "2026-11-18T00:00:00Z"),                                     # cutoff
        make_row("AUSTIN", "2026-10-21T00:00:00Z"), make_row("AUSTIN", "2026-10-21T00:00:00Z"),  # dup
        make_row("AUSTIN", "2026-10-21T06:00:00Z"),
    ]
    frame, counters, dups = _select(rows)
    excl = sum(counters[k] for k in score_mod.ROW_EXCLUSION_KEYS)
    assert len(rows) == excl + counters["in_scope_rows"] == excl + len(frame)
    assert excl == 5 and len(frame) == 2 and len(dups) == 1


def test_candidate_level_classification():
    overrides = {
        "ml_wind_corrected": make_candidate(None, status="unavailable", reason="no anchor"),
        "ml_cooling_corrected": make_candidate(None, status="failed", reason="boom"),
        "raw_forecast": make_candidate(1000.0, fallback=True),
        "persistence_24h": make_candidate(float("nan")),
        "reference_ml_refit_24h": make_candidate(True),
    }
    row = make_row("AUSTIN", "2026-10-20T00:00:00Z", overrides=overrides)
    row["candidates"].pop("raw_forecast")
    frame, counters, _ = _select([row])
    r = frame.iloc[0]
    assert r["ml_wind_corrected__excl"] == "candidate_unavailable" and r["ml_wind_corrected__status"] == "unavailable"
    assert r["ml_cooling_corrected__excl"] == "candidate_failed"
    assert r["raw_forecast__excl"] == "candidate_missing" and r["raw_forecast__status"] == "missing"
    assert r["persistence_24h__excl"] == "candidate_null_or_nonfinite_value"
    assert r["reference_ml_refit_24h__excl"] == "candidate_null_or_nonfinite_value"      # bool is not a number
    assert all(np.isnan(r[f"{n}__pred"]) for n in core.CANDIDATES)
    # a fallback candidate is distinct from provider fallback (anchor source)
    row2 = make_row("AUSTIN", "2026-10-20T06:00:00Z", overrides={"raw_forecast": make_candidate(1000.0, fallback=True)}, anchor_source="tceq")
    frame2, _, _ = _select([row2])
    assert frame2.iloc[0]["raw_forecast__excl"] == "candidate_fallback_used"
    assert frame2.iloc[0]["ml_wind_corrected__excl"] is None and frame2.iloc[0]["ml_wind_corrected__anchor_source"] == "tceq"
    cx = counters["candidate_exclusions_in_scope"]
    assert cx["ml_wind_corrected"]["candidate_unavailable"] == 1 and cx["raw_forecast"]["candidate_missing"] == 1


# --------------------------------------------------------------------------
# Reference own target hour and anchor breakdown
# --------------------------------------------------------------------------

def test_reference_target_hours_rounding_and_window_end_discrepancy():
    rows = [
        make_row("AUSTIN", "2026-10-20T00:00:00Z", decision="2026-10-19T09:29:59+00:00"),
        make_row("AUSTIN", "2026-10-20T06:00:00Z", decision="2026-10-19T15:30:00+00:00"),
        make_row("AUSTIN", "2026-10-20T12:00:00Z", decision="2026-10-19T21:00:00+00:00"),
    ]
    frame, _, _ = _select(rows)
    t = score_mod.reference_target_hours(frame)
    assert list(t["target"]) == [pd.Timestamp("2026-10-20T09:00:00Z"), pd.Timestamp("2026-10-20T16:00:00Z"), pd.Timestamp("2026-10-20T21:00:00Z")]
    assert list(t["rounding_offset_s"]) == [-(29 * 60 + 59), 1800.0, 0.0]
    # the window end equals the decision time in make_row, so both offsets agree
    for (_, r), (_, tr) in zip(frame.iterrows(), t.iterrows()):
        assert tr["rounding_offset_s"] == (tr["target"] - (r["decision_time"] + pd.Timedelta(hours=24))).total_seconds()
        assert tr["window_end_discrepancy_s"] == (tr["target"] - (r["decision_time"] + pd.Timedelta(hours=24))).total_seconds()
    assert float(t["rounding_offset_s"].abs().max()) <= 1800.0


def test_reference_window_end_missing_gives_nan_discrepancy():
    row = make_row("AUSTIN", "2026-10-20T00:00:00Z", overrides={"reference_ml_refit_24h": make_candidate(1000.0)})
    frame, _, _ = _select([row])
    assert np.isnan(score_mod.reference_target_hours(frame)["window_end_discrepancy_s"].iloc[0])


def test_anchor_breakdown_by_source_and_age():
    rows = [
        make_row("AUSTIN", "2026-10-20T00:00:00Z", anchor_source="tceq", anchor_age_h=1.0),
        make_row("AUSTIN", "2026-10-20T06:00:00Z", anchor_source="tceq", anchor_age_h=3.0),
        make_row("AUSTIN", "2026-10-20T12:00:00Z", anchor_source="synoptic", anchor_age_h=2.0),
    ]
    frame, _, _ = _select(rows)
    errors = {"ml_wind_corrected": pd.Series([10.0, -20.0, 5.0], index=frame["valid_time"]),
              "ml_cooling_corrected": pd.Series([1.0, 1.0, 1.0], index=frame["valid_time"])}
    out = score_mod.anchor_breakdown(frame, errors)
    assert "exploratory" in out["label"]
    wind = out["candidates"]["ml_wind_corrected"]["by_source"]
    assert set(wind) == {"tceq", "synoptic"}
    assert wind["tceq"]["n_rows"] == 2 and wind["tceq"]["anchor_age_h"]["min"] == pytest.approx(1.0)
    assert wind["tceq"]["anchor_age_h"]["max"] == pytest.approx(3.0) and wind["tceq"]["anchor_age_h"]["median"] == pytest.approx(2.0)
    # anchor_to_valid = valid - observation = (14 h 3 min) + age
    assert wind["tceq"]["anchor_to_valid_h"]["min"] == pytest.approx(14.05 + 1.0)
    assert wind["tceq"]["scored"] == {"n": 2, "bias": pytest.approx(-5.0), "mae": pytest.approx(15.0)}
    assert wind["synoptic"]["scored"]["mae"] == pytest.approx(5.0)
    assert wind["tceq"]["stations"] == {"KAUS": 2}


def test_anchor_breakdown_unknown_source_when_provenance_is_absent():
    row = make_row("AUSTIN", "2026-10-20T00:00:00Z", overrides={"ml_wind_corrected": make_candidate(1000.0)})
    frame, _, _ = _select([row])
    out = score_mod.anchor_breakdown(frame, {})
    assert list(out["candidates"]["ml_wind_corrected"]["by_source"]) == ["unknown"]
    assert out["candidates"]["ml_wind_corrected"]["by_source"]["unknown"]["anchor_age_h"]["n"] == 0


# --------------------------------------------------------------------------
# Count-only
# --------------------------------------------------------------------------

def _count_fixture(tmp_path):
    """FRESH-dated rows whose ampacities are all the sentinel, plus legacy corridor files."""
    d = tmp_path / "logs"
    d.mkdir()
    base = pd.Timestamp("2026-10-20T00:00:00Z")
    for city in config.LOCATIONS:
        rows = []
        for k in range(4):
            rows.append(make_row(city, base + pd.Timedelta(hours=6 * k)))
        rows.append(make_row(city, base + pd.Timedelta(hours=6), model=ABSENT))
        rows.append(make_row(city, base + pd.Timedelta(hours=30), model="ecmwf_ifs"))
        rows.append(make_row(city, base + pd.Timedelta(hours=36), overrides={"persistence_24h": make_candidate(None, status="unavailable")}))
        write_log(d / f"{city}.jsonl", rows)
    (d / "AUSTIN_CORPUS_CHRISTI.jsonl").write_text(json.dumps({"corridor": "AUSTIN_CORPUS_CHRISTI", "ampacity_amps": SENTINEL}) + "\n")
    (d / "MIDLAND_EL_PASO.jsonl").write_text("{}\n")
    return d


def test_count_only_is_status_only_and_never_reads_corridor_files(tmp_path, monkeypatch):
    d = _count_fixture(tmp_path)
    opened = []
    real_open = builtins.open

    def spy_open(file, *a, **k):
        opened.append(str(file))
        return real_open(file, *a, **k)
    monkeypatch.setattr(builtins, "open", spy_open)
    # before the evaluation instant, on FRESH-dated rows, with requests.get raising (autouse)
    report = score_mod.count_only_report(str(d), list(config.LOCATIONS), guard_cfg())
    monkeypatch.setattr(builtins, "open", real_open)
    assert not any("CORPUS_CHRISTI.jsonl" in p and "AUSTIN_CORPUS" in p for p in opened)
    assert not any("MIDLAND_EL_PASO" in p for p in opened)
    assert report["not_read_files"] == ["AUSTIN_CORPUS_CHRISTI.jsonl", "MIDLAND_EL_PASO.jsonl"]
    assert set(report["cities"]) == set(config.LOCATIONS)
    text = core.dumps(report)
    assert "4321" not in text and "987" not in text
    block = report["cities"]["AUSTIN"]
    for key in score_mod.READER_COUNTER_KEYS + score_mod.ROW_EXCLUSION_KEYS:
        assert key in block["counters"]
    assert block["counters"]["missing_forecast_model"] == 1 and block["counters"]["other_forecast_model"] == 1
    assert block["counters"]["accepted_rows"] == 7 and block["counters"]["in_scope_rows"] == 5
    assert block["forecast_model_counts"] == {"gfs_seamless": 5, "<missing>": 1, "ecmwf_ifs": 1}
    assert block["valid_hour_histogram"] == {"00": 1, "06": 1, "12": 2, "18": 1}
    gap = block["decision_to_valid_gap_hours"]
    assert gap["min"] == gap["median"] == gap["max"] == pytest.approx(14.05)
    assert block["candidate_status_counts"]["persistence_24h"]["unavailable"] == 1
    assert block["candidate_status_counts"]["ml_wind_corrected"]["ok"] == 5
    assert block["progress"]["tail_rate_target"] == {"rows": 590, "fraction": pytest.approx(5 / 590)}
    assert block["progress"]["mdd_target"]["rows"] == 1575
    assert report["pooled_nominal"]["label"] == "nominal, not effective"
    assert report["pooled_nominal"]["in_scope_rows"] == 20
    assert report["mode"] == "count_only" and report["row_source"] == "shadow_logs"


def test_count_only_cli_succeeds_before_the_instant_and_creates_no_evidence(tmp_path, capsys):
    d = _count_fixture(tmp_path)
    out = tmp_path / "counts.json"
    rc = score_mod.main(["--count-only", "--predictions-dir", str(d), "--out", str(out), "--evidence-root", str(tmp_path / "ev")])
    assert rc == 0
    data = json.loads(out.read_text())
    assert set(data["cities"]) == set(config.LOCATIONS) and "4321" not in out.read_text()
    assert not (tmp_path / "ev").exists()
    assert "missing_forecast_model" in capsys.readouterr().err


def test_count_only_counts_a_missing_city_file_without_failing(tmp_path):
    report = score_mod.count_only_report(str(tmp_path), ["AUSTIN"], guard_cfg())
    assert report["cities"]["AUSTIN"]["counters"]["in_scope_rows"] == 0
    assert report["cities"]["AUSTIN"]["counters"]["file_missing"] is True


# --------------------------------------------------------------------------
# score(): guard, evidence, truth, metrics
# --------------------------------------------------------------------------

DELTAS = {"ml_wind_corrected": 10.0, "ml_cooling_corrected": -5.0, "raw_forecast": 20.0, "persistence_24h": 30.0}
REF_DELTA = 7.0


def _dev_rows(city, n=10, start="2026-04-10T00:00:00Z", jitter=True):
    """Development-dated rows whose predictions are truth + a constant per candidate
    (reference: truth at ITS target hour + 7)."""
    rows = []
    for k in range(n):
        valid = pd.Timestamp(start) + pd.Timedelta(hours=6 * k)
        decision = valid - pd.Timedelta(hours=14, minutes=3 + (k % 5) * 7 if jitter else 3)
        target = core.round_half_up_to_hour(decision + pd.Timedelta(hours=24))
        amps = {n_: truth_at(city, valid) + d for n_, d in DELTAS.items()}
        amps["reference_ml_refit_24h"] = truth_at(city, target) + REF_DELTA
        rows.append(make_row(city, valid, decision=decision, amps=amps, anchor_source="tceq" if k % 2 else "synoptic", anchor_age_h=1.0 + k))
    return rows


def _write_dev_logs(d, cities, n=10, **kw):
    d.mkdir(exist_ok=True)
    for c in cities:
        write_log(d / f"{c}.jsonl", _dev_rows(c, n, **kw))


def test_score_development_run_reproduces_independent_numbers(tmp_path, monkeypatch):
    cities = ["AUSTIN", "MIDLAND"]
    d = tmp_path / "logs"
    _write_dev_logs(d, cities)
    (d / "AUSTIN_CORPUS_CHRISTI.jsonl").write_text("{}\n")
    calls = install_archive(monkeypatch)
    opened = []
    real_open = builtins.open
    monkeypatch.setattr(builtins, "open", lambda f, *a, **k: (opened.append(str(f)), real_open(f, *a, **k))[1])
    now = pd.Timestamp("2026-10-13T12:00:00Z")
    report = score_mod.score(str(d), cities=cities, guard_cfg=guard_cfg(), evidence_root=str(tmp_path / "ev"),
                             protocol_status="unsigned", now=now, source_commit="f" * 40)
    monkeypatch.setattr(builtins, "open", real_open)
    assert not any("AUSTIN_CORPUS_CHRISTI" in p for p in opened)
    assert len(calls) == 2                                       # one archive request per city, no retry
    assert report["row_source"] == "shadow_logs" and report["basis"] == "development"
    assert report["guard"]["defaults_used"] is True and report["guard"]["now_evaluated"] == now.isoformat()
    for c in cities:
        pc = report["per_city"][c]
        assert pc["n_in_scope"] == 10 and pc["n_with_truth"] == 10
        for cand, delta in DELTAS.items():
            m = pc["metrics"][cand]
            assert m["n"] == 10 and m["bias"] == pytest.approx(delta, abs=1e-9)
            assert m["mae"] == pytest.approx(abs(delta), abs=1e-9) and m["rmse"] == pytest.approx(abs(delta), abs=1e-9)
        ref = pc["metrics"]["reference_ml_refit_24h"]            # headline: own target hour
        assert ref["n"] == 10 and ref["bias"] == pytest.approx(REF_DELTA, abs=1e-9)
        logged = pc["reference_logged_hour_reading"]              # alongside, flagged, a different hour
        assert logged["flag"] == core.FLAG_V2_LOGGED and logged["n"] == 10
        expect = np.mean([truth_at(c, core.round_half_up_to_hour(pd.Timestamp(r["decision_time"]) + pd.Timedelta(hours=24)))
                          + REF_DELTA - truth_at(c, r["valid_time"]) for r in _dev_rows(c)])
        assert logged["bias"] == pytest.approx(expect, abs=1e-9)
        assert abs(logged["bias"] - ref["bias"]) > 1e-6
        acc = report["exclusions"][c]["accounting"]
        assert acc["lines_accepted_equals_exclusions_plus_in_scope"] and acc["in_scope_equals_truth_exclusions_plus_with_truth"]
        assert all(acc["per_candidate_with_truth_equals_scored_plus_exclusions"].values())
        diag = report["diagnostics"][c]
        assert diag["truth_fetch"]["error"] is None and diag["reference_target_hour"]["rounding_offset_s_max_abs"] <= 1800.0
        ab = diag["anchor_breakdown"]["candidates"]["ml_wind_corrected"]["by_source"]
        assert set(ab) == {"tceq", "synoptic"} and ab["tceq"]["scored"]["bias"] == pytest.approx(10.0)
    # evidence on disk
    ev_dir = report["evidence_dir"]
    assert os.path.basename(ev_dir).startswith("shadow_logs_20261013T120000Z")
    names = sorted(os.listdir(ev_dir))
    assert names == ["http", "report.json", "report.md", "run_started.json"]
    assert len(report["evidence"]) == 2 and all(len(e["sha256"]) == 64 for e in report["evidence"])
    saved = json.loads(open(os.path.join(ev_dir, "report.json")).read())
    for key in ("row_source", "basis", "protocol_status", "guard", "config", "provenance", "sample_size", "family", "decision",
                "per_city", "exclusions", "validity_flags", "diagnostics", "not_measured", "planner_defaults",
                "owner_pending", "evidence"):
        assert key in saved
    assert saved["provenance"]["logs_source_commit"] == "f" * 40
    assert saved["sample_size"]["pooled_nominal"]["n_scored"]["raw_forecast"] == 20
    md = open(os.path.join(ev_dir, "report.md")).read()
    assert md.index("## Sample size") < md.index("## Per-city descriptive metrics") and core.NOT_MEASURED_STATEMENT in md


def test_score_fetch_window_and_requests_cover_scope_but_stay_before_the_cutoff_day(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    _write_dev_logs(d, ["AUSTIN"], n=8, start="2026-04-10T00:00:00Z")
    calls = install_archive(monkeypatch)
    score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(), evidence_root=str(tmp_path / "ev"),
                    now=pd.Timestamp("2026-10-13T12:00:00Z"))
    (url, params, kwargs), = calls
    assert params["start_date"] == "2026-04-10" and params["end_date"] == "2026-04-12"
    assert kwargs == {"timeout": 60} and params["wind_speed_unit"] == "ms"


def test_reference_target_at_or_after_the_cutoff_is_a_candidate_level_exclusion(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    d.mkdir()
    rows = _dev_rows("AUSTIN", n=4, start="2026-04-11T00:00:00Z", jitter=False)    # valid 04-11T00..18
    write_log(d / "AUSTIN.jsonl", rows)
    calls = install_archive(monkeypatch)
    cutoff = pd.Timestamp("2026-04-12T00:00:00Z")
    report = score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(valid_time_cutoff=cutoff, override_reason="test cutoff"),
                             evidence_root=str(tmp_path / "ev"), now=pd.Timestamp("2026-10-13T12:00:00Z"))
    pc = report["per_city"]["AUSTIN"]
    # decisions 04-10T09:57, 15:57, 21:57 and 04-11T03:57: targets 04-11T10, 16, 22 are before the cutoff; the last (04-12T04) is not
    assert pc["n_in_scope"] == 4 and pc["n_with_truth"] == 4
    assert pc["candidate_exclusions"]["reference_ml_refit_24h"] == {"reference_target_at_or_after_cutoff": 1}
    assert pc["metrics"]["reference_ml_refit_24h"]["n"] == 3 and pc["metrics"]["raw_forecast"]["n"] == 4
    assert calls[0][1]["end_date"] == "2026-04-11"
    assert report["guard"]["override_reason"] == "test cutoff" and report["guard"]["defaults_used"] is False
    assert all(report["exclusions"]["AUSTIN"]["accounting"]["per_candidate_with_truth_equals_scored_plus_exclusions"].values())


def test_truth_fetch_failure_is_per_city_and_never_retried(tmp_path, monkeypatch):
    cities = ["AUSTIN", "MIDLAND"]
    d = tmp_path / "logs"
    _write_dev_logs(d, cities, n=6)
    calls = install_archive(monkeypatch, fail_cities=("MIDLAND",))
    report = score_mod.score(str(d), cities=cities, guard_cfg=guard_cfg(), evidence_root=str(tmp_path / "ev"),
                             now=pd.Timestamp("2026-10-13T12:00:00Z"))
    assert len(calls) == 2
    assert report["per_city"]["AUSTIN"]["n_scored"]["raw_forecast"] == 6
    assert report["per_city"]["MIDLAND"]["n_scored"]["raw_forecast"] == 0
    assert report["per_city"]["MIDLAND"]["excluded_by_reason"] == {"truth_fetch_failed": 6}
    assert "HTTPError" in report["diagnostics"]["MIDLAND"]["truth_fetch"]["error"]
    assert report["exclusions"]["MIDLAND"]["accounting"]["in_scope_equals_truth_exclusions_plus_with_truth"]
    assert any(e["status_code"] == 503 for e in report["evidence"])


def test_null_truth_hour_is_truth_missing_and_never_imputed(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    _write_dev_logs(d, ["AUSTIN"], n=6)
    victim = pd.Timestamp("2026-04-10T12:00:00Z")            # the valid hour of row k=2
    install_archive(monkeypatch, null_hours=[victim])
    report = score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(), evidence_root=str(tmp_path / "ev"),
                             now=pd.Timestamp("2026-10-13T12:00:00Z"))
    pc = report["per_city"]["AUSTIN"]
    assert pc["excluded_by_reason"].get("truth_missing", 0) >= 1
    assert pc["n_with_truth"] == pc["n_in_scope"] - pc["excluded_by_reason"]["truth_missing"]
    assert report["diagnostics"]["AUSTIN"]["truth_dropped_null_hours"] == [victim.isoformat()]
    # the reference row whose own TARGET hour is the null hour is a reference-only exclusion
    cx = pc["candidate_exclusions"]["reference_ml_refit_24h"]
    assert set(cx) <= {"reference_target_truth_missing"}


def test_empty_selection_scores_nothing_and_fetches_nothing(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    write_log(d / "AUSTIN.jsonl", [make_row("AUSTIN", "2026-10-20T00:00:00Z", model=ABSENT)])
    report = score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(), evidence_root=str(tmp_path / "ev"),
                             now=pd.Timestamp("2026-10-13T12:00:00Z"))
    assert report["per_city"]["AUSTIN"]["n_in_scope"] == 0
    assert report["per_city"]["AUSTIN"]["excluded_by_reason"] == {"missing_forecast_model": 1}
    assert report["evidence"] == []


def test_guard_blocks_fresh_scoring_before_the_instant_with_no_network_and_no_directory(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    write_log(d / "AUSTIN.jsonl", [make_row("AUSTIN", "2026-10-20T00:00:00Z", amps={"raw_forecast": SENTINEL})])
    with pytest.raises(core.EvaluationGuardError):
        score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(), evidence_root=str(tmp_path / "ev"),
                        now=INSTANT - pd.Timedelta(seconds=1))
    assert not (tmp_path / "ev").exists()


def test_fresh_run_at_the_instant_then_second_run_is_refused(tmp_path, monkeypatch):
    d = tmp_path / "logs"
    d.mkdir()
    rows = [make_row("AUSTIN", pd.Timestamp("2026-10-20T00:00:00Z") + pd.Timedelta(hours=6 * k)) for k in range(4)]
    write_log(d / "AUSTIN.jsonl", rows)
    install_archive(monkeypatch)
    ev = str(tmp_path / "ev")
    report = score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(), evidence_root=ev, now=INSTANT)
    assert report["basis"] == "FRESH" and "DEVELOPMENT DATA" not in open(report["report_paths"]["report_md"]).read()
    with pytest.raises(core.EvaluationGuardError):
        score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(), evidence_root=ev, now=INSTANT + pd.Timedelta(hours=2))
    again = score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(override_reason="rerun"), evidence_root=ev,
                            now=INSTANT + pd.Timedelta(hours=2))
    assert again["guard"]["override_reason"] == "rerun" and len(again["guard"]["prior_fresh_runs"]) == 1


def test_cli_guard_refusal_exits_2_with_message_and_no_network(tmp_path, capsys):
    d = tmp_path / "logs"
    d.mkdir()
    write_log(d / "AUSTIN.jsonl", [make_row("AUSTIN", "2026-10-20T00:00:00Z")])
    rc = score_mod.main(["--predictions-dir", str(d), "--cities", "AUSTIN", "--evidence-root", str(tmp_path / "ev")])
    assert rc == 2 and "refused" in capsys.readouterr().err
    assert not (tmp_path / "ev").exists()
    rc = score_mod.main(["--predictions-dir", str(d), "--cities", "AUSTIN", "--evidence-root", str(tmp_path / "ev"),
                         "--evaluation-instant", "2026-12-01T00:00:00Z"])
    assert rc == 2 and "override" in capsys.readouterr().err


def test_cli_rejects_unknown_city_and_exposes_no_clock(capsys):
    assert score_mod.main(["--count-only", "--cities", "ATLANTIS"]) == 2
    parser = score_mod.build_parser()
    assert "--now" not in parser.format_help()
    assert parser.parse_args([]).protocol_status == "unsigned"
    with pytest.raises(SystemExit):
        parser.parse_args(["--protocol-status", "maybe"])


# --------------------------------------------------------------------------
# Task 2 wiring: the 9-test family, the sample-size block and the ship rule
# --------------------------------------------------------------------------

def test_score_attaches_the_nine_test_family_and_the_live_system_decision(tmp_path, monkeypatch):
    cities = list(config.LOCATIONS)
    d = tmp_path / "logs"
    _write_dev_logs(d, cities, n=10)
    install_archive(monkeypatch)
    report = score_mod.score(str(d), cities=cities, guard_cfg=guard_cfg(), evidence_root=str(tmp_path / "ev"),
                             protocol_status="unsigned", now=pd.Timestamp("2026-10-13T12:00:00Z"),
                             params={"n_resamples": 300})
    fam = report["family"]
    assert len(fam["comparisons"]) == 9 and fam["family_size"] == 9 and fam["row_source"] == "shadow_logs"
    assert [(c["a"], c["b"]) for c in fam["comparisons"]] == list(core.HEADLINE_FAMILY)
    by = {(c["a"], c["b"]): c for c in fam["comparisons"]}
    # constant offsets: wind vs raw margin = 20 - 10; reference (own target hour) vs raw = 20 - 7
    assert by[("ml_wind_corrected", "raw_forecast")]["point_margin"] == pytest.approx(10.0, abs=1e-9)
    assert by[("reference_ml_refit_24h", "raw_forecast")]["point_margin"] == pytest.approx(13.0, abs=1e-9)
    assert by[("ml_cooling_corrected", "reference_ml_refit_24h")]["point_margin"] == pytest.approx(7.0 - 5.0, abs=1e-9)
    assert by[("ml_wind_corrected", "raw_forecast")]["n_paired"] == 40 and by[("ml_wind_corrected", "raw_forecast")]["cities_with_data"] == 4
    assert core.FLAG_V2 in by[("reference_ml_refit_24h", "raw_forecast")]["flags"]
    assert core.FLAG_V3 in by[("ml_wind_corrected", "persistence_24h")]["flags"]
    dec = report["decision"]
    assert dec["row_source"] == "shadow_logs" and dec["label"] == "live-system check" and dec["protocol_status"] == "unsigned"
    assert dec["levels"]["ml_wind_corrected"]["benefit_amps"] == pytest.approx(10.0, abs=1e-9)
    assert dec["working_choice"] in core.CANDIDATES and core.NOT_MEASURED_STATEMENT in dec["statements"]
    ss = report["sample_size"]
    assert len(ss["pairs"]) == 9 and ss["pooled_nominal"]["label"] == "nominal, not effective"
    assert all(not p["targets"]["tail_rate_target_met"] and not p["targets"]["mdd_target_met"] for p in ss["pairs"])
    assert report["planner_defaults"]["PD-09"]["non_default"] is True
    saved = json.loads(open(os.path.join(report["evidence_dir"], "report.json")).read())
    assert len(saved["family"]["comparisons"]) == 9 and saved["decision"]["row_source"] == "shadow_logs"
    md = open(os.path.join(report["evidence_dir"], "report.md")).read()
    assert (md.index("## Sample size") < md.index("## Headline family") < md.index("## Decision (live-system check)")
            < md.index("## Per-city descriptive metrics"))
    assert "descriptive, uncorrected" in md and core.FLAG_V2 in md and "NON-DEFAULT" in md


def test_fresh_run_with_a_nondefault_parameter_needs_an_override_and_creates_nothing(tmp_path):
    d = tmp_path / "logs"
    d.mkdir()
    write_log(d / "AUSTIN.jsonl", [make_row("AUSTIN", "2026-10-20T00:00:00Z")])
    with pytest.raises(ValueError, match="override"):
        score_mod.score(str(d), cities=["AUSTIN"], guard_cfg=guard_cfg(), evidence_root=str(tmp_path / "ev"), now=INSTANT,
                        params={"decision_margin_amps": 7.0})
    assert not (tmp_path / "ev").exists()


def test_cli_exposes_the_preregistered_parameters_and_no_row_gate_or_family_size(tmp_path, monkeypatch):
    parser = score_mod.build_parser()
    for flag in ("--row-gate", "--family-size"):
        with pytest.raises(SystemExit):
            parser.parse_args([flag, "5"])
    help_text = parser.format_help()
    assert "--row-gate" not in help_text and "--family-size" not in help_text
    args = parser.parse_args(["--block-lengths", "1", "4", "--n-resamples", "500", "--decision-margin-amps", "6",
                              "--consistency-min-cities", "2", "--min-paired-rows", "5", "--power", "0.9", "--seed", "7"])
    assert score_mod._params_from_args(args) == {"block_lengths": (1, 4), "n_resamples": 500, "decision_margin_amps": 6.0,
                                                 "consistency_min_cities": 2, "min_paired_rows": 5, "power": 0.9, "seed": 7}
    assert score_mod._params_from_args(parser.parse_args([])) is None
    # end to end on development data: a non-default parameter is recorded, not refused
    cities = ["AUSTIN", "MIDLAND"]
    d = tmp_path / "logs"
    _write_dev_logs(d, cities, n=10)
    install_archive(monkeypatch)
    rc = score_mod.main(["--predictions-dir", str(d), "--cities", *cities, "--evidence-root", str(tmp_path / "ev"),
                         "--n-resamples", "300"])
    assert rc == 0
    (run,) = os.listdir(tmp_path / "ev")
    saved = json.loads(open(tmp_path / "ev" / run / "report.json").read())
    assert saved["config"]["params"]["n_resamples"] == 300 and saved["guard"]["nondefault_params"] == {"n_resamples": 300}
