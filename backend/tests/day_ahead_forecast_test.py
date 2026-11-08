"""
Tests of the day-ahead cooling forecast write path (production-pipeline Phase 8, plan 08-01:
DAY-01, DAY-02, DAY-03, DAY-05).

The tracer drives one AUSTIN target the whole way: stubbed weather and anchor leaves, the real
hash-verified refit cooling model, the production conductor point, the hashed TEST band artifact,
and an insert as role `dlr_writer` into a throwaway local Postgres. Nothing here touches the live
Supabase project, the live job or the network.

Follows backend/tests/dlr_live_run_test.py's conventions: module-level imports, an autouse guard
on `requests.get`, plain asserts, no conftest.py, no test classes.

The local-Postgres tests need `DLR_TEST_PG_AUTOSTART=1` (backend/tests/local_pg.py). They skip
otherwise, and a skip proves nothing, so the plan's verify command treats a skip as a failure.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
import requests

import config
import day_ahead_band
import day_ahead_contract as contract
import day_ahead_forecast as daf
import forecast_shadow_pipeline as shadow
import local_pg
import supabase_store

_STORE_MIGRATION = "20261108120000_day_ahead_forecast_store.sql"

# One decision time and the target it can issue: 18:00Z is exactly 18 h after 00:00Z, the earliest
# moment its 24 h-old weather run (init 2026-11-08 18:00Z) plus the 6 h lag is published.
_NOW = pd.Timestamp("2026-11-09T00:05:00Z")
_TARGET = pd.Timestamp("2026-11-09T18:00:00Z")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """`requests.get` fails the test; the teardown assert cannot be swallowed by a broad except."""
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


# --------------------------------------------------------------------------------------------------
# Stubbed leaves: the weather run row and the "now" anchor reading
# --------------------------------------------------------------------------------------------------

def _forecast_row(*, air_temp=31.0, wind_speed=4.5, wind_direction=120.0, solar=620.0):
    """The Series `fetch_live_forecast_for_valid_time` returns: provider columns already renamed to fcst_*."""
    return pd.Series({
        "fcst_air_temp": air_temp, "fcst_wind_speed": wind_speed,
        "fcst_wind_direction": wind_direction, "fcst_solar_radiation": solar,
        "fcst_relative_humidity": 55.0,
    })


def _anchor(decision_time=_NOW, *, wind_speed=3.8, wind_direction=110.0, air_temp=29.5):
    return pd.Series({
        "anchor_wind_speed": wind_speed, "anchor_wind_direction": wind_direction,
        "anchor_air_temp": air_temp, "anchor_observation_time": decision_time - pd.Timedelta(minutes=5),
        "anchor_source": "tceq", "anchor_station": "TEST",
    })


def _stub_forecast_fetch(monkeypatch, row=None, calls=None):
    """Replace the frozen forecast fetch (the network leaf) with a recorder returning `row`."""
    row = _forecast_row() if row is None else row

    def fetch(city, valid_time, horizon_minutes, *, lat, lon, decision_time=None):
        if calls is not None:
            calls.append({"city": city, "valid_time": valid_time, "horizon_minutes": horizon_minutes,
                          "lat": lat, "lon": lon, "decision_time": decision_time})
        valid_ts = pd.Timestamp(valid_time)
        init = valid_ts - pd.Timedelta(minutes=horizon_minutes)
        return row.copy(), shadow.ShadowTimestamps(
            initialization_time=init, availability_time=init + pd.Timedelta(hours=6),
            decision_time=decision_time, valid_time=valid_ts, horizon_minutes=horizon_minutes,
        )

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", fetch)


def _band_manifest(tmp_path, path=day_ahead_band.BAND_ARTIFACT_PATH):
    """A temporary manifest holding the band artifact's sha256 (the live manifest is plan 08-05's)."""
    with open(path, "rb") as fh:
        digest = hashlib.sha256(fh.read()).hexdigest()
    manifest = tmp_path / "bands.sha256"
    manifest.write_text(f"{digest}  {path.replace(os.sep, '/')}\n", encoding="utf-8")
    return str(manifest), digest


# --------------------------------------------------------------------------------------------------
# Local Postgres: the write-side migration only (08-09's expose migration would grant anon SELECT)
# --------------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        paths = [p for p in local_pg.migration_files() if os.path.basename(p) <= _STORE_MIGRATION]
        assert os.path.basename(paths[-1]) == _STORE_MIGRATION, [os.path.basename(p) for p in paths]
        local_pg.apply_migrations(url, paths=paths)
        yield url


def _session(url, role):
    import psycopg

    conn = psycopg.connect(url, autocommit=True)
    conn.execute("set timezone = 'UTC'")
    conn.execute(f"set role {role}")
    return conn


# --------------------------------------------------------------------------------------------------
# Tracer: one AUSTIN target, shadow functions -> TEST band -> row -> local Postgres
# --------------------------------------------------------------------------------------------------

def test_tracer_one_austin_target_reaches_the_table(pg_url, tmp_path, monkeypatch):
    import psycopg

    calls = []
    _stub_forecast_fetch(monkeypatch, calls=calls)
    monkeypatch.setattr(shadow, "fetch_live_anchor_observation", lambda city, decision_time, **kw: _anchor(decision_time))

    # Real, hash-verified AUSTIN refit model through the headline loader (D-14).
    loader = daf.make_model_loader()
    model = loader("AUSTIN", "ml_cooling_corrected")
    entry = daf.served_entry(loader, "AUSTIN")
    assert entry["source"] == "refit"
    assert entry["sha256"].startswith("31fe8d9b")

    anchor = daf.read_anchor("AUSTIN", _NOW)
    amps = daf.compute_value("AUSTIN", _TARGET, decision_time=_NOW, anchor=anchor, model=model)
    assert np.isfinite(amps) and amps > 0
    assert calls == [{"city": "AUSTIN", "valid_time": _TARGET, "horizon_minutes": 1440,
                      "lat": config.CITY_COORDINATES["AUSTIN"][0], "lon": config.CITY_COORDINATES["AUSTIN"][1],
                      "decision_time": _NOW}]

    # The band artifact is verified against a manifest holding its sha256 before it is parsed.
    manifest, band_sha = _band_manifest(tmp_path)
    artifact, sha = day_ahead_band.load_verified_band(day_ahead_band.BAND_ARTIFACT_PATH, manifest)
    assert sha == band_sha
    fingerprint = supabase_store.rating_config_fingerprint("AUSTIN")
    band = day_ahead_band.band_for(
        None, "AUSTIN", _TARGET, amps, artifact, sha,
        config_fingerprint=fingerprint, cooling_model_sha256=entry["sha256"], decision_time=_NOW,
    )
    assert band.source == "test-split" and band.n == 196 and band.pairs_through is None

    run_ctx = {"run_id": "tracer-run", "run_attempt": 1, "pipeline_version": "abc1234"}
    row = daf.build_row("AUSTIN", _TARGET, issued_at=_NOW, amps=amps, band=band, model_entry=entry,
                        anchor=anchor, run_ctx=run_ctx)
    assert tuple(row) == contract.INSERT_COLUMNS

    writer = _session(pg_url, "dlr_writer")
    assert daf.insert_row(writer, row) is True
    stored = writer.execute(
        "select forecast_method, label, band_source, cooling_model_source, forecast_run_init_time, "
        "valid_time, forecast_amps, forecast_ci_lower_amps, forecast_ci_upper_amps, issued_at "
        "from public.day_ahead_forecast where city = 'AUSTIN'"
    ).fetchall()
    assert len(stored) == 1
    (method, label, band_source, model_source, init_time, valid_time,
     stored_amps, lower, upper, issued_at) = stored[0]
    assert method == "ml_cooling_corrected"
    assert label == contract.DAY_AHEAD_LABEL
    assert band_source == "test-split"
    assert model_source == "refit"
    assert init_time == valid_time - timedelta(hours=24)
    assert lower <= stored_amps <= upper
    assert stored_amps == pytest.approx(amps)

    # First write wins (D-04): the same key again changes nothing, issued_at included.
    later = dict(row, issued_at=_NOW + pd.Timedelta(hours=1), forecast_amps=amps + 50.0,
                 forecast_ci_upper_amps=row["forecast_ci_upper_amps"] + 50.0)
    assert daf.insert_row(writer, later) is False
    again = writer.execute(
        "select issued_at, forecast_amps from public.day_ahead_forecast where city = 'AUSTIN'"
    ).fetchall()
    assert again == [(issued_at, stored_amps)]
    writer.close()

    # The table is hidden from anon until the separate expose migration (D-17).
    anon = _session(pg_url, "anon")
    with pytest.raises(psycopg.errors.InsufficientPrivilege) as raised:
        anon.execute("select * from public.day_ahead_forecast").fetchall()
    assert raised.value.sqlstate == "42501"
    anon.close()


def test_a_band_artifact_that_differs_from_the_manifest_is_refused_before_parsing(tmp_path, monkeypatch):
    with open(day_ahead_band.BAND_ARTIFACT_PATH, "rb") as fh:
        genuine = fh.read()
    tampered = tmp_path / "day_ahead_bands_v1.json"
    tampered.write_bytes(b"this is not json and never gets parsed")
    manifest = tmp_path / "bands.sha256"
    manifest.write_text(f"{hashlib.sha256(genuine).hexdigest()}  {str(tampered).replace(os.sep, '/')}\n",
                        encoding="utf-8")

    parsed = []
    monkeypatch.setattr(day_ahead_band, "parse_band_artifact", lambda data: parsed.append(data))
    with pytest.raises(day_ahead_band.BandArtifactError, match="hash mismatch"):
        day_ahead_band.load_verified_band(str(tampered), str(manifest))
    assert parsed == []


# --------------------------------------------------------------------------------------------------
# The write-side migration against the contract
# --------------------------------------------------------------------------------------------------

def _sample_row(city="AUSTIN", valid_time=_TARGET, **overrides):
    """A complete valid row, built directly (no model), for the constraint checks."""
    point = 1700.0
    row = {
        "city": city, "valid_time": valid_time.to_pydatetime(),
        "issued_at": _NOW.to_pydatetime(),
        "forecast_run_init_time": (valid_time - pd.Timedelta(hours=24)).to_pydatetime(),
        "horizon_minutes": 1440, "forecast_amps": point,
        "forecast_ci_lower_amps": point - 200.0, "forecast_ci_upper_amps": point + 250.0,
        "band_source": "test-split", "band_n": 196, "band_pairs_through": None,
        "band_artifact_sha256": "ab" * 32, "forecast_method": "ml_cooling_corrected",
        "cooling_model_sha256": "cd" * 32, "cooling_model_source": "refit",
        "anchor_observation_time": (_NOW - pd.Timedelta(minutes=5)).to_pydatetime(),
        "anchor_source": "tceq", "label": contract.DAY_AHEAD_LABEL,
        "config_version": config.RATING_CONFIG_VERSION, "config_fingerprint": "ef" * 32,
        "run_id": "test-run", "run_attempt": 1, "pipeline_version": "test000", "schema_version": 1,
    }
    row.update(overrides)
    return row


def test_migration_columns_equal_the_contract_and_the_writer_cannot_rewrite(pg_url):
    import psycopg

    admin = psycopg.connect(pg_url, autocommit=True)
    columns = [name for (name,) in admin.execute(
        "select column_name from information_schema.columns where table_schema = 'public' "
        "and table_name = 'day_ahead_forecast' order by ordinal_position"
    ).fetchall()]
    assert tuple(columns) == contract.TABLE_COLUMNS
    assert admin.execute(
        "select 1 from information_schema.columns where table_schema = 'public' "
        "and table_name = 'pipeline_run' and column_name = 'day_ahead' and data_type = 'jsonb'"
    ).fetchone() == (1,)
    # re-applying the whole file is safe (idempotent)
    path = os.path.join(local_pg.MIGRATIONS_DIR, _STORE_MIGRATION)
    with open(path, encoding="utf-8") as handle:
        admin.execute(handle.read())
    admin.close()

    writer = _session(pg_url, "dlr_writer")
    assert daf.insert_row(writer, _sample_row(city="MIDLAND")) is True
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer.execute("update public.day_ahead_forecast set forecast_amps = 1 where city = 'MIDLAND'")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        writer.execute("delete from public.day_ahead_forecast where city = 'MIDLAND'")
    writer.close()


@pytest.mark.parametrize("overrides, constraint", [
    ({"valid_time": pd.Timestamp("2026-11-09T17:00:00Z")}, "day_ahead_forecast_valid_time_grid_ck"),
    ({"valid_time": pd.Timestamp("2026-11-09T18:30:00Z")}, "day_ahead_forecast_valid_time_hour_ck"),
    ({"forecast_run_init_time": pd.Timestamp("2026-11-08T17:00:00Z").to_pydatetime()}, "day_ahead_forecast_run_init_ck"),
    ({"forecast_method": "raw_forecast"}, "day_ahead_forecast_method_ck"),   # D-16: only cooling
    ({"horizon_minutes": 1500}, "day_ahead_forecast_horizon_ck"),
    ({"forecast_amps": float("nan")}, "day_ahead_forecast_amps_ck"),
    ({"forecast_amps": 0.0}, "day_ahead_forecast_amps_ck"),
    ({"forecast_ci_upper_amps": 1000.0}, "day_ahead_forecast_band_contains_point_ck"),
    ({"band_source": "live-rolling"}, "day_ahead_forecast_band_pairs_through_ck"),
    ({"band_pairs_through": pd.Timestamp("2026-11-08T18:00:00Z").to_pydatetime()},
     "day_ahead_forecast_band_pairs_through_ck"),
    ({"issued_at": pd.Timestamp("2026-11-09T18:00:00Z").to_pydatetime()}, "day_ahead_forecast_issued_before_valid_ck"),
    ({"label": ""}, "day_ahead_forecast_label_ck"),
    ({"cooling_model_sha256": "not-hex"}, "day_ahead_forecast_cooling_model_sha256_ck"),
    ({"city": "DALLAS"}, "day_ahead_forecast_city_ck"),
])
def test_the_table_rejects_a_row_that_breaks_a_constraint(pg_url, overrides, constraint):
    import psycopg

    overrides = dict(overrides)
    writer = _session(pg_url, "dlr_writer")
    with pytest.raises(psycopg.errors.CheckViolation) as raised:
        daf.insert_row(writer, _sample_row(city=overrides.pop("city", "EL_PASO"), **overrides))
    assert raised.value.diag.constraint_name == constraint
    writer.close()
