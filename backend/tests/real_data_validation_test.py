"""
Tests for backend/real_data_validation.py -- the offline analysis of a real
backfill run (completeness, manifest, and the VAL-01 report).

Every test builds its own synthetic archive, trace and log under `tmp_path`; no
test reads or writes the real backfill files and none touches the network.
Follows backend/tests/backfill_archive_test.py's conventions (module-level
imports, plain asserts, no test classes).
"""

import json
import os

import numpy as np
import pandas as pd
import pytest

import city_point
import config
import data_cleaning
import historical_archive
import real_data_validation
from DLRSafetyMonitor import DLRSafetyMonitor

_DAY = "2025-06-01"


def _step(hour):
    return f"{_DAY}T{hour:02d}:00:00Z"


def _write_archive(path, city, hours):
    for hour in hours:
        observation = {"temp": 30.0, "wind": 1.0, "solar": 500.0}
        check = {"rating": 1500.0, "status": "OK", "fallback": False}
        row = historical_archive.build_archive_row(
            city, pd.Timestamp(_step(hour)), observation, check, 1500.0)
        historical_archive.append_observation(row, path=str(path))


def _trace_line(city, hour):
    return json.dumps({
        "schema": real_data_validation.TRACE_SCHEMA, "run_end_utc": _step(hour), "city": city,
        "forecast_method": "naive", "error": None, "station_id": "T1", "rating_a": 1500.0,
        "static_rating_a": 1500.0, "status": "OK", "fallback": False, "exhausted": False,
        "archived": True, "fallback_gates": [], "alerts": [], "observation": None,
        "observation_hour": None, "sources": None, "pipeline": None}, sort_keys=True)


def _write_log(path, city, hours):
    lines = ["run_end_utc,city,rating_a,fallback,exhausted,archived,gates,error"]
    lines += [f"{_step(h)},{city},1500.0,False,False,True,," for h in hours]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_completeness_counts_archive_rows_without_trace_as_no_trace(tmp_path):
    archive, trace, log = tmp_path / "a.csv", tmp_path / "t.jsonl", tmp_path / "l.csv"
    _write_archive(archive, "AUSTIN", [10, 11, 12])  # three archived steps
    trace.write_text(_trace_line("AUSTIN", 10) + "\n", encoding="utf-8")  # one traced
    _write_log(log, "AUSTIN", [10, 11, 12])
    out = tmp_path / "completeness.csv"

    code = real_data_validation.main([
        "completeness", "--archive", str(archive), "--trace", str(trace), "--log", str(log),
        "--start", _step(10), "--end", _step(13), "--cities", "AUSTIN", "--out", str(out)])

    assert code == 0
    row = pd.read_csv(out).iloc[0]
    assert {k: int(row[k]) for k in ("expected_steps", "trace_records", "archive_rows",
                                     "log_rows", "no_trace", "missing")} == {
        "expected_steps": 4, "trace_records": 1, "archive_rows": 3, "log_rows": 3,
        "no_trace": 2, "missing": 1}


def test_manifest_is_deterministic_and_flags_missing_models(tmp_path, monkeypatch, capsys):
    forecast_dir, anomaly_dir = tmp_path / "forecast_models", tmp_path / "anomaly_models"
    forecast_dir.mkdir()
    anomaly_dir.mkdir()
    monkeypatch.setattr(config, "FORECAST_ML_MODEL_DIR", str(forecast_dir))
    monkeypatch.setattr(config, "ANOMALY_ML_MODEL_DIR", str(anomaly_dir))
    # Models for AUSTIN only: MIDLAND's two model files are missing.
    (forecast_dir / config.FORECAST_ML_MODEL_FILENAME_TEMPLATE.format(city="AUSTIN")).write_bytes(b"f")
    (anomaly_dir / config.ANOMALY_ML_MODEL_FILENAME_TEMPLATE.format(city="AUSTIN")).write_bytes(b"a")

    archive, trace, log = tmp_path / "a.csv", tmp_path / "t.jsonl", tmp_path / "l.csv"
    _write_archive(archive, "AUSTIN", [10, 11])
    trace.write_text(_trace_line("AUSTIN", 10) + "\n" + _trace_line("AUSTIN", 11) + "\n",
                     encoding="utf-8")
    _write_log(log, "AUSTIN", [10, 11])
    argv = ["--start", _step(10), "--end", _step(11), "--cities", "AUSTIN", "MIDLAND"]
    base = ["manifest", "--archive", str(archive), "--trace", str(trace), "--log", str(log),
            "--start", _step(10), "--end", _step(11), "--cities", "AUSTIN", "MIDLAND",
            "--forecast-method", "naive"]

    first, second = tmp_path / "m1.json", tmp_path / "m2.json"
    code1 = real_data_validation.main(base + ["--out", str(first), "--"] + argv)
    code2 = real_data_validation.main(base + ["--out", str(second), "--"] + argv)

    assert code1 == 1 and code2 == 1  # MIDLAND has no model files
    assert first.read_bytes() == second.read_bytes()
    manifest = json.loads(first.read_text(encoding="utf-8"))
    assert manifest["schema"] == "real_data_validation_manifest/1"
    assert manifest["window"] == {
        "start": _step(10), "end": _step(11), "step_hours": 1.0, "steps_per_city": 2,
        "warmup_hours": 168.0, "scored_start": "2025-06-08T10:00:00Z"}
    assert manifest["cities"] == ["AUSTIN", "MIDLAND"]
    assert manifest["backfill_argv"] == argv
    assert repr(argv) in manifest["command"]
    assert manifest["command"] == real_data_validation.OWNER_COMMAND_TEMPLATE.replace(
        "{argv}", repr(argv))
    assert manifest["archive_rows_by_city"] == {"AUSTIN": 2, "MIDLAND": 0}
    assert set(manifest["files"]) == {"archive", "trace", "log"}
    assert manifest["files"]["archive"]["bytes"] == archive.stat().st_size
    assert len(manifest["files"]["archive"]["sha256"]) == 64
    models = manifest["models"]
    present = [name for name, digest in models.items() if digest is not None]
    assert len(present) == 2 and all("AUSTIN" in name for name in present)
    assert any(digest is None for digest in models.values())
    assert len(manifest["git"]["head"]) == 40 and isinstance(manifest["git"]["backend_dirty"], bool)
    assert "PROVISIONAL" in manifest["label"]
    assert "model file missing" in capsys.readouterr().err


# ──────────────────────────────────────────────────────────────────────────────
# VAL-01: helpers
# ──────────────────────────────────────────────────────────────────────────────

_START = "2025-06-01T00:00:00Z"
_WARMUP_H = 2.0  # short warm-up so a seven-step window has warm-up and scored steps
_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
# Inside every city's plausibility bounds (1614.9 A) / below AUSTIN's lower bound
# (483 A) / above AUSTIN's upper bound (2506 A).
_OK_OBS = dict(temp=15.0, wind=3.0, solar=300.0)
_LOW_OBS = dict(temp=45.0, wind=0.0, solar=1000.0)
_HIGH_OBS = dict(temp=0.0, wind=10.0, solar=100.0)


def _ts(hour):
    return (pd.Timestamp(_START) + pd.Timedelta(hours=hour)).strftime(_TS_FMT)


def _record(city, hour, temp=15.0, wind=3.0, solar=300.0, wind_raw=4.0, **overrides):
    """
    A trace record shaped like the Task 1 writer's, built by running the real
    safety monitor the way `rate_city` does (G5 off, the city's own bounds), so
    the rating, fallback flag and gate come from the production gates.
    """
    point = city_point.city_point(city)
    monitor = DLRSafetyMonitor(
        static_rating=point.static_rating, conductor=point.conductor,
        rating_bounds=point.rating_bounds, delta_fraction=float("inf"), logger=lambda msg: None)
    check = monitor.run_check(
        {"sensor_status": "ok", "link_status": "ok", "temp": temp, "wind": wind, "solar": solar})
    record = {
        "schema": real_data_validation.TRACE_SCHEMA, "run_end_utc": _ts(hour), "city": city,
        "forecast_method": "naive", "error": None, "station_id": "T1",
        "rating_a": check["rating"], "static_rating_a": point.static_rating,
        "status": check["status"], "fallback": check["fallback"], "exhausted": False,
        "archived": True,
        "fallback_gates": sorted({a.split()[0] for a in check["alerts"]}),
        "alerts": check["alerts"],
        "observation": {"temp": temp, "wind": wind, "wind_raw": wind_raw,
                        "wind_direction": 100.0, "solar": solar},
        "observation_hour": _ts(hour),
        "sources": {"air_temp": "synoptic", "wind_speed": "tceq", "solar_radiation": "nsrdb"},
        "pipeline": {"history_rows": 10, "usable_history_rows": 9, "forecast_method": "naive",
                     "forecast_used_by_g6": True, "forecast": None, "detector_signal": None,
                     "detector_model": None},
    }
    record.update(overrides)
    return record


def _exhausted_record(city, hour):
    point = city_point.city_point(city)
    record = _record(city, hour, observation=None, observation_hour=None, sources=None,
                     rating_a=point.static_rating, status="fallback", fallback=True,
                     exhausted=True, archived=False, fallback_gates=["EXHAUSTED"],
                     alerts=["EXHAUSTED FAIL (no station)"])
    return record


def _error_record(city, hour):
    record = {key: None for key in _record(city, hour)}
    record.update(schema=real_data_validation.TRACE_SCHEMA, run_end_utc=_ts(hour), city=city,
                  forecast_method="naive", error="boom")
    return record


def _archive_row_from(record):
    obs = record["observation"]
    row = historical_archive.build_archive_row(
        record["city"], pd.Timestamp(record["run_end_utc"]),
        {"temp": obs["temp"], "wind": obs["wind"], "solar": obs["solar"]},
        {"rating": record["rating_a"], "status": record["status"], "fallback": record["fallback"]},
        record["static_rating_a"])
    return row


def _write_run(tmp_path, records, untraced=()):
    """
    Write `records` as a trace and (for the ones that archived) as archive rows.
    `untraced` records get an archive row but no trace line.
    """
    trace = tmp_path / "trace.jsonl"
    archive = tmp_path / "archive.csv"
    lines = [json.dumps(r, sort_keys=True) for r in records]
    trace.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    for record in list(records) + list(untraced):
        if record.get("archived") and record.get("observation"):
            historical_archive.append_observation(_archive_row_from(record), path=str(archive))
    if not archive.exists():
        archive.write_text("", encoding="utf-8")
    log = tmp_path / "log.csv"
    log.write_text("run_end_utc,city,rating_a,fallback,exhausted,archived,gates,error\n",
                   encoding="utf-8")
    return archive, trace, log


def _classify(tmp_path, records, cities=("AUSTIN",), untraced=(), hours=7):
    archive, trace, _ = _write_run(tmp_path, records, untraced)
    steps = real_data_validation.expected_steps(_START, _ts(hours - 1))
    return real_data_validation.classify_steps(
        real_data_validation.load_trace(trace),
        historical_archive.read_history(path=str(archive)) if archive.stat().st_size else
        pd.DataFrame(columns=historical_archive.ARCHIVE_COLUMNS),
        list(cities), steps, pd.Timestamp(_START), _WARMUP_H)


def _report(tmp_path, records, cities, untraced=(), hours=7, out_name="report", extra=()):
    archive, trace, _ = _write_run(tmp_path, records, untraced)
    out_dir = tmp_path / out_name
    code = real_data_validation.main([
        "report", "--archive", str(archive), "--trace", str(trace), "--start", _START,
        "--end", _ts(hours - 1), "--warmup-hours", str(_WARMUP_H), "--cities", *cities,
        "--out-dir", str(out_dir), *extra])
    return code, out_dir


# ──────────────────────────────────────────────────────────────────────────────
# VAL-01: classification, recompute and edge tests
# ──────────────────────────────────────────────────────────────────────────────

def test_bound_class_is_inclusive_at_both_bounds():
    assert real_data_validation.bound_class(1150.0, 1150.0, 2500.0) == "within"
    assert real_data_validation.bound_class(2500.0, 1150.0, 2500.0) == "within"
    assert real_data_validation.bound_class(1149.999, 1150.0, 2500.0) == "below"
    assert real_data_validation.bound_class(2500.001, 1150.0, 2500.0) == "above"


def test_period_starts_exactly_at_start_plus_warmup():
    start = pd.Timestamp(_START)
    assert real_data_validation.period_of(start + pd.Timedelta(hours=168), start, 168) == "scored"
    assert real_data_validation.period_of(start + pd.Timedelta(hours=167), start, 168) == "warmup"
    assert real_data_validation.period_of(start, start, 0) == "scored"


@pytest.mark.parametrize("city", list(config.LOCATIONS))
def test_computed_amps_matches_the_safety_monitor(city):
    record = _record(city, 0)
    assert record["status"] == "ok"  # the observation passes every gate for every city
    computed = real_data_validation.computed_amps(city, 15.0, 3.0, 300.0)
    assert abs(float(computed) - record["rating_a"]) < 1e-6


def test_classify_steps_counts_every_expected_step_once(tmp_path):
    records = [
        _record("AUSTIN", 0),                                  # ok, warm-up
        _record("AUSTIN", 1, **_LOW_OBS),                      # G4 below the lower bound
        _record("AUSTIN", 2, **_HIGH_OBS),                     # G4 above the upper bound
        _exhausted_record("AUSTIN", 3),
        _error_record("AUSTIN", 4),
    ]
    frame = _classify(tmp_path, records, untraced=[_record("AUSTIN", 5)])  # hour 6 has nothing

    assert len(frame) == 7
    assert list(frame["run_end_utc"]) == list(real_data_validation.expected_steps(_START, _ts(6)))
    assert list(frame["outcome"]) == [
        "ok", "G4_low", "G4_high", "EXHAUSTED", "ERROR", "NO_TRACE", "MISSING"]
    assert list(frame["period"]) == ["warmup", "warmup", "scored", "scored", "scored", "scored",
                                     "scored"]
    assert set(frame["outcome"]) <= set(real_data_validation.OUTCOMES)
    assert frame.duplicated(["city", "run_end_utc"]).sum() == 0
    low = frame.iloc[1]
    assert low["bound_class"] == "below" and frame.iloc[2]["bound_class"] == "above"
    assert np.isnan(frame.iloc[3]["computed_a"]) and np.isnan(frame.iloc[6]["reported_a"])


def test_upward_fallback_counts_static_above_computed(tmp_path):
    # AUSTIN at 45 C, still air, 1000 W/m2 computes 483 A: G4 falls back to the 1825 A static rating.
    records = [_record("AUSTIN", 3, **_LOW_OBS), _record("AUSTIN", 4, **_HIGH_OBS),
               _record("AUSTIN", 5, **_OK_OBS)]
    frame = _classify(tmp_path, records)
    low = frame[frame["outcome"] == "G4_low"].iloc[0]
    assert low["computed_a"] < 1150.0 < low["static_a"]
    assert low["direction"] == "upward"
    assert low["overstatement_a"] == pytest.approx(low["static_a"] - low["computed_a"])
    high = frame[frame["outcome"] == "G4_high"].iloc[0]
    assert high["direction"] == "downward" and np.isnan(high["overstatement_a"])
    assert set(frame[frame["outcome"] == "ok"]["direction"]) == {"none"}
    assert set(frame[frame["outcome"] == "MISSING"]["direction"]) == {"unknown"}

    code, out_dir = _report(tmp_path, records, ["AUSTIN"])
    table = pd.read_csv(out_dir / "val01_fallback_direction_by_city.csv")
    row = table[(table["city"] == "AUSTIN") & (table["gate"] == "G4_low")].iloc[0]
    assert (row["fallback_steps"], row["upward"], row["downward"], row["unknown"]) == (1, 1, 0, 0)
    assert row["overstatement_median"] == pytest.approx(round(low["overstatement_a"], 1))


def test_city_with_no_records_still_has_a_row(tmp_path):
    records = [_record("AUSTIN", h) for h in range(7)]
    code, out_dir = _report(tmp_path, records, ["AUSTIN", "MIDLAND"])

    assert code == 0
    ratings = pd.read_csv(out_dir / "val01_ratings_by_city.csv")
    assert list(ratings["city"]) == ["AUSTIN", "MIDLAND"]
    empty = ratings[ratings["city"] == "MIDLAND"].iloc[0]
    assert empty["static_a"] == config.STATIC_RATINGS["MIDLAND"]
    assert empty["reported_n"] == 0 and pd.isna(empty["reported_p50"]) and pd.isna(empty["computed_p50"])
    outcomes = pd.read_csv(out_dir / "val01_outcomes_by_city.csv")
    midland = outcomes[outcomes["city"] == "MIDLAND"]
    assert len(midland) == 2 * len(real_data_validation.OUTCOMES)
    missing = midland[midland["outcome"] == "MISSING"].set_index("period")["count"]
    assert missing.to_dict() == {"warmup": 2, "scored": 5}
    assert (midland[midland["outcome"] != "MISSING"]["count"] == 0).all()
    for name in ("val01_fallback_direction_by_city.csv", "val01_outliers.csv",
                 "val01_drivers_by_city.csv"):
        assert "MIDLAND" in set(pd.read_csv(out_dir / name)["city"]), name


def test_report_is_byte_identical_across_runs_and_ordered_by_locations(tmp_path):
    records = []
    for city in ("EL_PASO", "AUSTIN"):  # written in reverse of config.LOCATIONS order
        records += [_record(city, h) for h in range(5)] + [_record(city, 5, **_LOW_OBS)]
    code1, first = _report(tmp_path, records, ["EL_PASO", "AUSTIN"], out_name="one")
    code2, second = _report(tmp_path, records, ["EL_PASO", "AUSTIN"], out_name="two")

    assert code1 == 0 and code2 == 0
    names = sorted(p.name for p in first.iterdir())
    assert names == sorted([
        "report_meta.json", "tables.md", "val01_drivers_by_city.csv",
        "val01_fallback_direction_by_city.csv", "val01_outcomes_by_city.csv",
        "val01_outliers.csv", "val01_ratings_by_city.csv",
        # added by plan 03-03 (VAL-02)
        "val02_coverage_by_residuals.csv", "val02_detector_by_city.csv",
        "val02_forecast_by_city.csv", "val02_g6_trips.csv"])
    for name in names:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name
    cities = list(pd.read_csv(first / "val01_ratings_by_city.csv")["city"])
    assert cities == ["AUSTIN", "EL_PASO"]  # config.LOCATIONS order, not the order given
    outcomes = pd.read_csv(first / "val01_outcomes_by_city.csv")
    assert list(outcomes[(outcomes["city"] == "AUSTIN") & (outcomes["period"] == "scored")]["outcome"]) \
        == list(real_data_validation.OUTCOMES)
    markdown = (first / "tables.md").read_text(encoding="utf-8")
    assert markdown.index("val01_ratings_by_city") < markdown.index("val01_outcomes_by_city") \
        < markdown.index("Cleaning activity")


def test_report_exits_one_on_archive_trace_mismatch(tmp_path):
    records = [_record("AUSTIN", h) for h in range(7)]
    archive, trace, _ = _write_run(tmp_path, records)
    table = pd.read_csv(archive)
    table.loc[3, "dlr_amps"] = table.loc[3, "dlr_amps"] + 5.0  # edited outside the pipeline
    table.to_csv(archive, index=False, lineterminator="\n")
    out_dir = tmp_path / "report"

    code = real_data_validation.main([
        "report", "--archive", str(archive), "--trace", str(trace), "--start", _START,
        "--end", _ts(6), "--warmup-hours", str(_WARMUP_H), "--cities", "AUSTIN",
        "--out-dir", str(out_dir)])

    assert code == 1
    meta = json.loads((out_dir / "report_meta.json").read_text(encoding="utf-8"))  # written first
    assert meta["archive_vs_trace_mismatches"] == 1
    assert meta["computed_vs_reported_mismatches"] == 0
    assert meta["archive_duplicate_slot_mismatches"] == 0


def test_report_exits_one_when_a_reported_rating_disagrees_with_physics(tmp_path):
    records = [_record("AUSTIN", h) for h in range(7)]
    records[4] = dict(records[4], rating_a=records[4]["rating_a"] + 0.01)
    code, out_dir = _report(tmp_path, records, ["AUSTIN"])
    meta = json.loads((out_dir / "report_meta.json").read_text(encoding="utf-8"))
    assert code == 1 and meta["computed_vs_reported_mismatches"] == 1


def test_duplicate_archive_slot_counts_as_a_mismatch(tmp_path):
    records = [_record("AUSTIN", h) for h in range(7)]
    archive, trace, _ = _write_run(tmp_path, records)
    lines = archive.read_text(encoding="utf-8").splitlines()
    archive.write_text("\n".join(lines + [lines[2]]) + "\n", encoding="utf-8")  # a second row, slot 2
    out_dir = tmp_path / "report"

    code = real_data_validation.main([
        "report", "--archive", str(archive), "--trace", str(trace), "--start", _START,
        "--end", _ts(6), "--warmup-hours", str(_WARMUP_H), "--cities", "AUSTIN",
        "--out-dir", str(out_dir)])

    meta = json.loads((out_dir / "report_meta.json").read_text(encoding="utf-8"))
    assert code == 1 and meta["archive_duplicate_slot_mismatches"] == 1


def test_missing_input_exits_two_naming_the_path(tmp_path, capsys):
    code = real_data_validation.main([
        "report", "--archive", str(tmp_path / "nope.csv"), "--trace", str(tmp_path / "nope.jsonl"),
        "--start", _START, "--end", _ts(6), "--out-dir", str(tmp_path / "out")])
    assert code == 2
    assert str(tmp_path / "nope.csv") in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


def test_amps_round_to_one_decimal_and_rates_to_four(tmp_path):
    # Three scored steps (hours 2-4): two ok (1614.9 A, below the 1825 A static) and one G4
    # fallback that reports exactly the static rating.
    records = [_record("AUSTIN", 0), _record("AUSTIN", 1), _record("AUSTIN", 2),
               _record("AUSTIN", 3, **_LOW_OBS), _record("AUSTIN", 4)]
    code, out_dir = _report(tmp_path, records, ["AUSTIN"], hours=5)

    assert code == 0
    ratings = pd.read_csv(out_dir / "val01_ratings_by_city.csv", dtype=str).iloc[0]
    assert ratings["reported_p50"] == "1614.9"
    assert ratings["reported_max"] == "1825.0"
    assert ratings["frac_reported_equal_static"] == "0.3333"
    assert ratings["frac_reported_below_static"] == "0.6667"
    assert ratings["frac_reported_above_static"] == "0.0"
    outcomes = pd.read_csv(out_dir / "val01_outcomes_by_city.csv")
    scored = outcomes[(outcomes["city"] == "AUSTIN") & (outcomes["period"] == "scored")]
    assert scored["count"].sum() == 3 and scored["count"].dtype.kind == "i"
    assert scored.set_index("outcome").loc["ok", "rate"] == pytest.approx(0.6667)


def test_cleaning_summary_calls_clean_history_once_per_city(tmp_path, monkeypatch):
    records = [_record(city, h) for city in ("AUSTIN", "MIDLAND") for h in range(7)]
    real_clean = data_cleaning.clean_history
    calls = []

    def counting_clean(history, as_of=None, **kwargs):
        calls.append((sorted(history["city"].unique()), as_of))
        return real_clean(history, as_of=as_of, **kwargs)

    monkeypatch.setattr(data_cleaning, "clean_history", counting_clean)
    code, out_dir = _report(tmp_path, records, ["AUSTIN", "MIDLAND"])

    assert code == 0
    assert calls == [(["AUSTIN"], None), (["MIDLAND"], None)]
    meta = json.loads((out_dir / "report_meta.json").read_text(encoding="utf-8"))
    assert list(meta["cleaning"]) == ["AUSTIN", "MIDLAND"]
    for city in ("AUSTIN", "MIDLAND"):
        block = meta["cleaning"][city]
        assert set(block["flag_counts"]) == set(data_cleaning.FLAG_ORDER)
        assert block["rows_in"] == 7
        assert block["live_excluded_rows_median"] == 1.0 and block["live_excluded_rows_max"] == 1
    assert "Cleaning activity" in (out_dir / "tables.md").read_text(encoding="utf-8")
