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

import pandas as pd

import config
import historical_archive
import real_data_validation

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
