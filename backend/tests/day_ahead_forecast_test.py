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

import city_point
import config
import day_ahead_band
import day_ahead_contract as contract
import day_ahead_forecast as daf
import forecast_conductor_refit as fcr
import forecast_shadow_demo as demo
import forecast_shadow_pipeline as shadow
import local_pg
import supabase_store
import weather_provider

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


# --------------------------------------------------------------------------------------------------
# due / catchup (D-01, D-02, D-04)
# --------------------------------------------------------------------------------------------------

def _ts(text):
    return pd.Timestamp(text, tz="UTC")


def test_due_at_12_05_lists_the_next_three_grid_targets():
    assert daf.due_targets(_ts("2026-11-09 12:05")) == [
        _ts("2026-11-09 18:00"), _ts("2026-11-10 00:00"), _ts("2026-11-10 06:00"),
    ]


def test_due_at_06_05_ends_with_the_next_midnight_target():
    due = daf.due_targets(_ts("2026-11-09 06:05"))
    assert due[-1] == _ts("2026-11-10 00:00")
    assert due[0] == _ts("2026-11-09 12:00")


def test_due_excludes_a_target_that_is_exactly_now():
    due = daf.due_targets(_ts("2026-11-09 12:00:00"))
    assert _ts("2026-11-09 12:00") not in due
    assert len(due) == 3 and due[0] == _ts("2026-11-09 18:00")


def test_due_yields_exactly_three_targets_every_hour_and_each_is_fetchable():
    lag = pd.Timedelta(hours=shadow._resolve_publication_lag_hours())
    for hour in range(24):
        for minute in (0, 5, 59):
            now = _ts("2026-11-09 00:00") + pd.Timedelta(hours=hour, minutes=minute)
            due = daf.due_targets(now)
            assert len(due) == 3, (now, due)
            for target in due:
                assert target > now
                assert target.hour % contract.GRID_HOURS == 0 and target.minute == 0
                # the frozen fetch raises when decision_time precedes init + lag
                assert now >= target - pd.Timedelta(minutes=contract.HORIZON_MINUTES) + lag


def test_due_is_naive_safe_and_never_lists_a_past_target():
    due = daf.due_targets(pd.Timestamp("2026-11-09 18:30:00"))  # naive timestamps are read as UTC
    assert all(target > _ts("2026-11-09 18:30") for target in due)
    assert _ts("2026-11-09 18:00") not in due


def test_catchup_missing_is_due_minus_existing_and_keeps_due_order():
    due = daf.due_targets(_ts("2026-11-09 12:05"))
    existing = {_ts("2026-11-10 00:00")}
    assert daf.missing_targets(due, existing) == [_ts("2026-11-09 18:00"), _ts("2026-11-10 06:00")]
    assert daf.missing_targets(due, set(due)) == []


def test_catchup_a_missed_target_stays_due_until_its_own_hour():
    # The 18:00Z target first becomes issuable at 00:00Z the same day (T - 24 h + 6 h lag = T - 18 h).
    target = _ts("2026-11-09 18:00")
    for chance in ("2026-11-09 00:05", "2026-11-09 12:05", "2026-11-09 17:55"):
        assert target in daf.due_targets(_ts(chance)), chance
    assert target not in daf.due_targets(_ts("2026-11-08 23:55"))   # not published yet
    assert target not in daf.due_targets(_ts("2026-11-09 18:00:00"))  # D-04: once it has passed, the slot stays empty
    assert target not in daf.due_targets(_ts("2026-11-09 23:05"))


def test_catchup_reads_the_table_for_missing_targets(pg_url):
    writer = _session(pg_url, "dlr_writer")
    now = _ts("2026-11-09 12:05")
    assert daf.existing_targets(writer, "CORPUS_CHRISTI", now) == set()
    stored = _sample_row(city="CORPUS_CHRISTI", valid_time=_ts("2026-11-10 00:00"),
                         issued_at=now.to_pydatetime())
    assert daf.insert_row(writer, stored) is True
    existing = daf.existing_targets(writer, "CORPUS_CHRISTI", now)
    assert existing == {_ts("2026-11-10 00:00")}
    assert daf.missing_targets(daf.due_targets(now), existing) == [
        _ts("2026-11-09 18:00"), _ts("2026-11-10 06:00"),
    ]
    # a stored target that has already passed is not "existing" any more
    assert daf.existing_targets(writer, "CORPUS_CHRISTI", _ts("2026-11-10 00:00")) == set()
    writer.close()


# --------------------------------------------------------------------------------------------------
# parity with the shadow path (D-03)
# --------------------------------------------------------------------------------------------------

def _fake_station_window(location, start, end, provider="synoptic", **kwargs):
    """A complete network-free station window for the shadow methods this test does not care about."""
    end_ts = pd.Timestamp(end)
    if end_ts.tzinfo is None:
        end_ts = end_ts.tz_localize("UTC")
    return pd.DataFrame([{
        "datetime_utc": end_ts - pd.Timedelta(hours=h), "air_temp": 25.0, "wind_speed": 5.0,
        "wind_direction": 100.0, "solar_radiation": 400.0,
    } for h in range(config.FORECAST_ML_ROLLING_WINDOW_HOURS, -1, -1)])


def _shadow_demo_value(monkeypatch, tmp_path, city):
    """What the shadow demo's own entry point computes for `city` on the same stubbed inputs and valid time."""
    monkeypatch.setattr(shadow, "SHADOW_PREDICTIONS_DIR", str(tmp_path / "predictions"))
    monkeypatch.setattr(weather_provider, "fetch_weather", _fake_station_window)

    def not_under_test(self, city_arg, decision_time):
        raise RuntimeError("not under test: only ml_cooling_corrected is compared")

    # The two history-based candidates fetch their own history over the network; they do not touch the
    # cooling value, and the demo records a failure for either without stopping.
    monkeypatch.setattr(shadow.Persistence24hShadowMethod, "compute", not_under_test)
    monkeypatch.setattr(shadow.ReferenceRefit24hShadowMethod, "compute", not_under_test)
    monkeypatch.setattr(demo, "_resolve_next_valid_time", lambda horizon_minutes: _TARGET)
    _stub_forecast_fetch(monkeypatch)
    monkeypatch.setattr(shadow, "fetch_live_anchor_observation",
                        lambda city_arg, decision_time, **kw: _anchor(decision_time))
    results = demo.run_once_all_methods(city)
    prediction = results["ml_cooling_corrected"]
    assert prediction.status == "ok", prediction.reason
    return prediction.ampacity_amps


@pytest.mark.parametrize("city", ["CORPUS_CHRISTI", "MIDLAND", "EL_PASO"])
def test_parity_production_equals_the_shadow_path_where_the_conductor_matches(monkeypatch, tmp_path, city):
    assert not fcr.production_differs(city)
    expected = _shadow_demo_value(monkeypatch, tmp_path, city)
    loader = daf.make_model_loader()
    model, entry = daf.load_model(loader, city)
    assert entry["source"] == "frozen"
    value = daf.compute_value(city, _TARGET, decision_time=_NOW, anchor=_anchor(), model=model)
    assert value == expected


def test_parity_austin_equals_the_same_chain_with_the_refit_model_and_differs_from_drake(monkeypatch, tmp_path):
    assert fcr.production_differs("AUSTIN")
    drake_value = _shadow_demo_value(monkeypatch, tmp_path, "AUSTIN")
    loader = daf.make_model_loader()
    model, entry = daf.load_model(loader, "AUSTIN")
    assert entry["source"] == "refit"
    value = daf.compute_value("AUSTIN", _TARGET, decision_time=_NOW, anchor=_anchor(), model=model)

    point = city_point.production_city_point("AUSTIN")
    frame = shadow.validate_and_prepare_shadow_row(_forecast_row(), city="AUSTIN")
    frame = shadow._enrich_city_frame_for_correction(
        frame, anchor=_anchor(), city="AUSTIN", valid_time=_TARGET, geometry=point)
    assert value == float(shadow.CoolingCorrectionShadowMethod(model).predict(frame, point))
    assert value != drake_value


# --------------------------------------------------------------------------------------------------
# no substitute (D-16)
# --------------------------------------------------------------------------------------------------

def _spy_every_shadow_method(monkeypatch):
    """Record every call to a prediction method of any shadow method class; the real code still runs."""
    called = []
    for name in dir(shadow):
        cls = getattr(shadow, name)
        if not (isinstance(cls, type) and name.endswith("ShadowMethod")):
            continue
        for attr in ("predict", "compute"):
            original = cls.__dict__.get(attr)
            if original is None:
                continue

            def make(label, fn):
                def spy(self, *args, **kwargs):
                    called.append(label)
                    return fn(self, *args, **kwargs)
                return spy

            monkeypatch.setattr(cls, attr, make(f"{name}.{attr}", original))
    return called


@pytest.fixture(scope="module")
def austin_model():
    return daf.load_model(daf.make_model_loader(), "AUSTIN")[0]


def test_no_substitute_only_the_cooling_method_is_ever_called(monkeypatch, austin_model):
    _stub_forecast_fetch(monkeypatch)
    called = _spy_every_shadow_method(monkeypatch)
    daf.compute_value("AUSTIN", _TARGET, decision_time=_NOW, anchor=_anchor(), model=austin_model)
    assert called == ["CoolingCorrectionShadowMethod.predict"]


def test_no_substitute_a_missing_weather_run_is_a_named_reason_and_nothing_else_runs(monkeypatch, austin_model):
    def unavailable(*args, **kwargs):
        raise shadow.StaleOrMissingDataError("run 2026-11-08 18:00 unavailable for city 'AUSTIN'")

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", unavailable)
    called = _spy_every_shadow_method(monkeypatch)
    with pytest.raises(daf.DayAheadNotIssued) as raised:
        daf.compute_value("AUSTIN", _TARGET, decision_time=_NOW, anchor=_anchor(), model=austin_model)
    assert raised.value.reason.startswith("forecast: StaleOrMissingDataError")
    assert called == []


def test_no_substitute_a_missing_anchor_is_a_named_reason(monkeypatch, austin_model):
    _stub_forecast_fetch(monkeypatch)
    with pytest.raises(daf.DayAheadNotIssued) as raised:
        daf.compute_value("AUSTIN", _TARGET, decision_time=_NOW, anchor=None, model=austin_model)
    assert raised.value.reason.startswith("anchor:")

    def failing(city, decision_time, **kwargs):
        raise shadow.StaleOrMissingDataError("no observation within the lookback window")

    monkeypatch.setattr(shadow, "fetch_live_anchor_observation", failing)
    with pytest.raises(daf.DayAheadNotIssued) as raised:
        daf.read_anchor("AUSTIN", _NOW)
    assert raised.value.reason.startswith("anchor: StaleOrMissingDataError")

    monkeypatch.setattr(shadow, "fetch_live_anchor_observation", lambda city, decision_time, **kw: None)
    with pytest.raises(daf.DayAheadNotIssued) as raised:
        daf.read_anchor("AUSTIN", _NOW)
    assert raised.value.reason.startswith("anchor:")


def test_no_substitute_a_hash_refusal_from_the_loader_is_a_named_reason_and_nothing_is_unpickled(
        monkeypatch, tmp_path):
    # A frozen manifest whose EL_PASO entry is wrong: the real loader must refuse before loading.
    frozen_path = shadow._model_path_for("EL_PASO", "ml_cooling_corrected")
    manifest = tmp_path / "ARTIFACT_HASHES.sha256"
    manifest.write_text(f"{'0' * 64}  {fcr._manifest_key(frozen_path)}\n", encoding="utf-8")
    loader = fcr.make_headline_loader(daf.DAY_AHEAD_REFIT_VERSION, daf.refit_cities(), root=fcr.REFIT_ROOT,
                                      frozen_manifest=str(manifest))
    loads = []
    monkeypatch.setattr(shadow, "load_correction_model", lambda *a, **k: loads.append(a))
    with pytest.raises(daf.DayAheadNotIssued) as raised:
        daf.load_model(loader, "EL_PASO")
    assert raised.value.reason.startswith("model: ArtifactIntegrityError")
    assert loads == []
    assert loader.served == []


@pytest.mark.parametrize("bad", [float("nan"), 0.0, -5.0, float("inf")])
def test_no_substitute_a_non_finite_or_non_positive_value_is_never_published(monkeypatch, austin_model, bad):
    _stub_forecast_fetch(monkeypatch)
    monkeypatch.setattr(shadow.CoolingCorrectionShadowMethod, "predict", lambda self, frame, geometry: bad)
    with pytest.raises(daf.DayAheadNotIssued) as raised:
        daf.compute_value("AUSTIN", _TARGET, decision_time=_NOW, anchor=_anchor(), model=austin_model)
    assert raised.value.reason.startswith("value:")


def test_no_substitute_a_failing_predict_is_a_named_reason(monkeypatch, austin_model):
    _stub_forecast_fetch(monkeypatch)

    def broken(self, frame, geometry):
        raise ValueError("predicted a non-positive convective term")

    monkeypatch.setattr(shadow.CoolingCorrectionShadowMethod, "predict", broken)
    with pytest.raises(daf.DayAheadNotIssued) as raised:
        daf.compute_value("AUSTIN", _TARGET, decision_time=_NOW, anchor=_anchor(), model=austin_model)
    assert raised.value.reason.startswith("predict: ValueError")


def test_no_substitute_the_module_never_names_another_method_or_loads_a_pickle_itself():
    with open(os.path.join(os.path.dirname(daf.__file__), "day_ahead_forecast.py"), encoding="utf-8") as fh:
        source = fh.read()
    for forbidden in ("RawForecastShadowMethod", "raw_forecast", "WindCorrectionShadowMethod",
                      "Persistence24hShadowMethod", "ReferenceRefit24hShadowMethod", "joblib"):
        assert forbidden not in source, forbidden


def test_a_reason_never_carries_a_connection_string(monkeypatch, austin_model):
    def leaky(*args, **kwargs):
        # assembled at run time so this file holds no credential-shaped text (secret_scan_test)
        raise RuntimeError("could not connect to " + "postgresql" + "://writer:" + "s3cret" + "@db.example.invalid:5432/postgres")

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", leaky)
    with pytest.raises(daf.DayAheadNotIssued) as raised:
        daf.compute_value("AUSTIN", _TARGET, decision_time=_NOW, anchor=_anchor(), model=austin_model)
    assert "s3cret" not in raised.value.reason and "db.example.invalid" not in raised.value.reason


# --------------------------------------------------------------------------------------------------
# identity (D-09, D-11) and out-of-bounds values (log, do not suppress)
# --------------------------------------------------------------------------------------------------

def _row_for(city, amps=1500.0, loader=None):
    loader = loader or daf.make_model_loader()
    _, entry = daf.load_model(loader, city)
    artifact, sha = day_ahead_band.load_verified_band(day_ahead_band.BAND_ARTIFACT_PATH, _MANIFEST_FOR_IDENTITY["path"])
    band = day_ahead_band.band_for(
        None, city, _TARGET, amps, artifact, sha,
        config_fingerprint=supabase_store.rating_config_fingerprint(city),
        cooling_model_sha256=entry["sha256"], decision_time=_NOW,
    )
    run_ctx = {"run_id": "identity-run", "run_attempt": 2, "pipeline_version": "abc1234"}
    row = daf.build_row(city, _TARGET, issued_at=_NOW, amps=amps, band=band, model_entry=entry,
                        anchor=_anchor(), run_ctx=run_ctx)
    return row, entry, band


_MANIFEST_FOR_IDENTITY = {}


@pytest.fixture(autouse=True)
def _identity_manifest(tmp_path_factory):
    if "path" not in _MANIFEST_FOR_IDENTITY:
        directory = tmp_path_factory.mktemp("identity_manifest")
        _MANIFEST_FOR_IDENTITY["path"], _ = _band_manifest(directory)


@pytest.mark.parametrize("city", list(config.LOCATIONS))
def test_identity_row_keys_fingerprint_label_and_model_come_from_the_right_places(city):
    row, entry, band = _row_for(city)
    assert tuple(row) == contract.INSERT_COLUMNS
    assert row["config_fingerprint"] == supabase_store.rating_config_fingerprint(city)
    assert row["config_version"] == config.RATING_CONFIG_VERSION
    assert row["cooling_model_sha256"] == entry["sha256"]
    assert row["cooling_model_source"] == entry["source"]
    assert row["label"] == contract.DAY_AHEAD_LABEL
    assert row["forecast_method"] == "ml_cooling_corrected" and row["horizon_minutes"] == 1440
    assert row["band_artifact_sha256"] == band.artifact_sha256
    assert row["run_id"] == "identity-run" and row["run_attempt"] == 2 and row["schema_version"] == 1
    assert row["valid_time"] - row["forecast_run_init_time"] == timedelta(hours=24)


def test_identity_austin_serves_the_refit_model_and_el_paso_the_frozen_one():
    austin, austin_entry, _ = _row_for("AUSTIN")
    el_paso, el_paso_entry, _ = _row_for("EL_PASO")
    assert (austin["cooling_model_source"], austin["cooling_model_sha256"][:8]) == ("refit", "31fe8d9b")
    assert (el_paso["cooling_model_source"], el_paso["cooling_model_sha256"][:8]) == ("frozen", "f64f9872")
    assert os.path.basename(austin_entry["path"]) == "ml_cooling_corrected_AUSTIN.joblib"
    assert austin_entry["path"] == daf.serving_model_path("AUSTIN")
    assert el_paso_entry["path"] == daf.serving_model_path("EL_PASO")


def test_out_of_bounds_values_are_still_built_into_a_row_and_logged(caplog):
    lower, upper = config.RATING_BOUNDS_BY_LOCATION["AUSTIN"]
    with caplog.at_level("WARNING", logger=daf.logger.name):
        assert daf.out_of_bounds("AUSTIN", upper + 400.0) is True
        assert daf.out_of_bounds("AUSTIN", lower - 100.0) is True
    assert any("outside" in record.getMessage() for record in caplog.records)
    caplog.clear()
    assert daf.out_of_bounds("AUSTIN", (lower + upper) / 2) is False
    assert caplog.records == []

    row, _, _ = _row_for("AUSTIN", amps=upper + 400.0)   # published, not suppressed
    assert row["forecast_amps"] == upper + 400.0
