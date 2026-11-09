"""
Tests of the per-city day-ahead child `backend/dlr_day_ahead.py` (production-pipeline Phase 8,
plan 08-04: DAY-01, DAY-02, DAY-05; D-04, D-13a, D-15, D-16).

The child runs for real here: `main()` is called with the argv the runner builds, against a
throwaway local Postgres migrated through the write-side file only, as role `dlr_writer`
(`supabase_store.connect` is replaced to return that session). The weather run and the anchor
reading are stubbed at the shadow module's leaf functions; the cooling model is the real,
hash-verified MIDLAND file. Temporary manifests stand in for the live one (08-05 adds the
committed entry). Nothing here touches the live Supabase project, the live job or the network.

The local-Postgres tests need `DLR_TEST_PG_AUTOSTART=1` (backend/tests/local_pg.py). A skip proves
nothing, so the plan's verify command treats a skip as a failure.
"""

import hashlib
import json
import os

import pandas as pd
import pytest
import requests

import config
import day_ahead_band
import day_ahead_contract as contract
import day_ahead_forecast as daf
import dlr_day_ahead
import dlr_live_run
import forecast_conductor_refit as fcr
import forecast_shadow_pipeline as shadow
import local_pg
import supabase_store

_STORE_MIGRATION = "20261108120000_day_ahead_forecast_store.sql"
_CITY = "MIDLAND"

# 00:05Z on 2026-11-09: the due targets are 06:00, 12:00 and 18:00Z (18:00 is exactly 18 h away).
_NOW = pd.Timestamp("2026-11-09T00:05:00Z")
_DUE = [pd.Timestamp(f"2026-11-09T{hour:02d}:00:00Z") for hour in (6, 12, 18)]

_RUNNER_KEYS = {
    "city", "decision_time", "outcome", "due", "already_present", "issued", "not_issued",
    "band_sources", "out_of_bounds", "cooling_model_sha256", "duration_s",
}


def _iso(stamp) -> str:
    return pd.Timestamp(stamp).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """`requests.get` fails the test; the teardown assert cannot be swallowed by a broad except."""
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setenv("GITHUB_RUN_ID", "9001")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_SHA", "abc1234def5678")
    yield
    assert attempts == []


# --------------------------------------------------------------------------------------------------
# Stubs: the weather run, the anchor reading, the live band manifest
# --------------------------------------------------------------------------------------------------

def _forecast_row():
    return pd.Series({
        "fcst_air_temp": 31.0, "fcst_wind_speed": 4.5, "fcst_wind_direction": 120.0,
        "fcst_solar_radiation": 620.0, "fcst_relative_humidity": 55.0,
    })


def _anchor(decision_time):
    return pd.Series({
        "anchor_wind_speed": 3.8, "anchor_wind_direction": 110.0, "anchor_air_temp": 29.5,
        "anchor_observation_time": pd.Timestamp(decision_time) - pd.Timedelta(minutes=5),
        "anchor_source": "tceq", "anchor_station": "TEST",
    })


def _stub_weather(monkeypatch, *, unavailable=(), calls=None):
    """Forecast fetch and anchor stubs; a target in `unavailable` has no weather run."""
    unavailable = {pd.Timestamp(t) for t in unavailable}

    def fetch(city, valid_time, horizon_minutes, *, lat, lon, decision_time=None):
        if calls is not None:
            calls.append(pd.Timestamp(valid_time))
        valid_ts = pd.Timestamp(valid_time)
        if valid_ts in unavailable:
            raise shadow.StaleOrMissingDataError("no model run covers this valid time")
        init = valid_ts - pd.Timedelta(minutes=horizon_minutes)
        return _forecast_row(), shadow.ShadowTimestamps(
            initialization_time=init, availability_time=init + pd.Timedelta(hours=6),
            decision_time=decision_time, valid_time=valid_ts, horizon_minutes=horizon_minutes,
        )

    monkeypatch.setattr(shadow, "fetch_live_forecast_for_valid_time", fetch)
    monkeypatch.setattr(shadow, "fetch_live_anchor_observation",
                        lambda city, decision_time, **kw: _anchor(decision_time))


def _manifest(tmp_path, digest=None):
    """A temporary manifest naming the band artifact (the live manifest is plan 08-05's)."""
    path = day_ahead_band.BAND_ARTIFACT_PATH
    if digest is None:
        with open(day_ahead_band._resolve(path), "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
    manifest = tmp_path / "bands.sha256"
    manifest.write_text(f"{digest}  {path.replace(os.sep, '/')}\n", encoding="utf-8")
    return str(manifest), digest


def _trust_band(monkeypatch, tmp_path, digest=None):
    """Make the child's default-path band check use a temporary manifest instead of the live one."""
    manifest, sha = _manifest(tmp_path, digest)
    original = day_ahead_band.load_verified_band
    monkeypatch.setattr(day_ahead_band, "load_verified_band",
                        lambda *a, **k: original(day_ahead_band.BAND_ARTIFACT_PATH, manifest))
    return sha


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


@pytest.fixture
def store(pg_url, monkeypatch):
    """An empty table; `supabase_store.connect` returns a fresh dlr_writer session (autocommit)."""
    import psycopg

    with psycopg.connect(pg_url, autocommit=True) as admin:
        admin.execute("truncate public.day_ahead_forecast")
    opened = []

    def connect(url=None):
        conn = _session(pg_url, "dlr_writer")
        opened.append(conn)
        return conn

    monkeypatch.setattr(supabase_store, "connect", connect)
    yield pg_url
    for conn in opened:
        if not conn.closed:
            conn.close()


def _rows(url):
    import psycopg

    with psycopg.connect(url, autocommit=True) as admin:
        return admin.execute(
            "select city, valid_time, issued_at, forecast_amps, forecast_ci_lower_amps, "
            "forecast_ci_upper_amps, band_source, cooling_model_sha256, run_id "
            "from public.day_ahead_forecast order by valid_time"
        ).fetchall()


def _run(tmp_path, now=_NOW, city=_CITY, extra=()):
    """Run the child the way the runner does and return (exit code, output document)."""
    out = str(tmp_path / f"{city}.{_iso(now)}.json")
    argv = dlr_live_run.day_ahead_child_argv(city, out)[2:] + list(extra)
    code = dlr_day_ahead.main(argv, now=now)
    with open(out, encoding="utf-8") as fh:
        return code, json.load(fh)


# --------------------------------------------------------------------------------------------------
# contract
# --------------------------------------------------------------------------------------------------

def test_contract_the_runner_argv_is_accepted_and_its_output_is_classified_issued(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)

    code, output = _run(tmp_path)

    assert code == 0
    assert set(output) == _RUNNER_KEYS
    assert output["outcome"] == "issued"
    assert output["city"] == _CITY
    assert output["decision_time"] == _iso(_NOW)
    assert output["due"] == [_iso(t) for t in _DUE]
    assert output["issued"] == output["due"] and output["already_present"] == []
    assert output["not_issued"] == {}
    assert set(output["band_sources"]) == set(output["issued"])
    assert set(output["band_sources"].values()) == {"test-split"}
    assert isinstance(output["duration_s"], float)
    assert len(output["cooling_model_sha256"]) == 64

    record = dlr_live_run.classify_day_ahead(_CITY, 0, output, "", env={})
    assert record["outcome"] == "issued"
    assert record["issued"] == output["issued"] and record["missing"] == []
    assert record["cooling_model_sha256"] == output["cooling_model_sha256"]


def test_contract_the_child_argv_parser_rejects_a_missing_or_unknown_argument(tmp_path):
    with pytest.raises(SystemExit) as raised:
        dlr_day_ahead.main(["--city", _CITY], now=_NOW)
    assert raised.value.code == 2
    with pytest.raises(SystemExit) as raised:
        dlr_day_ahead.main(["--city", "ATLANTIS", "--output", str(tmp_path / "x.json")], now=_NOW)
    assert raised.value.code == 2


# --------------------------------------------------------------------------------------------------
# none_due, catchup, idempotent (D-04: the table is the state)
# --------------------------------------------------------------------------------------------------

def test_none_due_when_every_due_target_is_stored_and_nothing_is_fetched_or_loaded(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    assert _run(tmp_path)[1]["outcome"] == "issued"

    fetched, loaded = [], []
    _stub_weather(monkeypatch, calls=fetched)
    monkeypatch.setattr(daf, "make_model_loader", lambda: loaded.append(1))

    code, output = _run(tmp_path, now=_NOW + pd.Timedelta(minutes=5))

    assert code == 0
    assert output["outcome"] == "none_due"
    assert output["issued"] == [] and output["not_issued"] == {}
    assert output["already_present"] == [_iso(t) for t in _DUE]
    assert fetched == [] and loaded == []


def test_catchup_inserts_only_the_missing_target_with_the_decision_time_as_issued_at(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    earlier = pd.Timestamp("2026-11-08T23:55:00Z")  # due then: 00:00, 06:00, 12:00
    assert _run(tmp_path, now=earlier)[1]["issued"] == [
        "2026-11-09T00:00:00Z", "2026-11-09T06:00:00Z", "2026-11-09T12:00:00Z"]

    fetched = []
    _stub_weather(monkeypatch, calls=fetched)
    code, output = _run(tmp_path)  # 00:05Z: due 06:00, 12:00, 18:00; two are stored

    assert code == 0
    assert output["outcome"] == "issued"
    assert output["already_present"] == ["2026-11-09T06:00:00Z", "2026-11-09T12:00:00Z"]
    assert output["issued"] == ["2026-11-09T18:00:00Z"]
    assert fetched == [pd.Timestamp("2026-11-09T18:00:00Z")]  # only the missing one was fetched
    stored = {row[1]: row for row in _rows(store)}
    assert len(stored) == 4
    assert stored[pd.Timestamp("2026-11-09T18:00:00Z").to_pydatetime()][2] == _NOW.to_pydatetime()
    assert stored[pd.Timestamp("2026-11-09T06:00:00Z").to_pydatetime()][2] == earlier.to_pydatetime()


def test_idempotent_a_second_run_inserts_nothing_and_leaves_the_first_row_unchanged(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    first_code, first = _run(tmp_path)
    before = _rows(store)
    assert first["outcome"] == "issued" and len(before) == 3

    second_code, second = _run(tmp_path, now=_NOW + pd.Timedelta(minutes=10))

    assert (first_code, second_code) == (0, 0)
    assert second["outcome"] == "none_due"
    assert _rows(store) == before  # issued_at and amps both unchanged


# --------------------------------------------------------------------------------------------------
# no_substitute (D-16, D-13a): a refusal publishes nothing and nothing else is used
# --------------------------------------------------------------------------------------------------

def test_no_substitute_a_missing_anchor_reading_gives_error_and_no_rows(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)

    def anchor_down(city, decision_time, **kw):
        raise shadow.StaleOrMissingDataError("no recent station reading")

    monkeypatch.setattr(shadow, "fetch_live_anchor_observation", anchor_down)

    code, output = _run(tmp_path)

    assert code == 0
    assert output["outcome"] == "error"
    assert output["issued"] == []
    assert set(output["not_issued"]) == {_iso(t) for t in _DUE}
    assert all(reason.startswith("anchor") for reason in output["not_issued"].values())
    assert _rows(store) == []


def test_no_substitute_one_unavailable_weather_run_gives_partial_and_the_others_are_issued(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch, unavailable=[_DUE[1]])
    _trust_band(monkeypatch, tmp_path)

    code, output = _run(tmp_path)

    assert code == 0
    assert output["outcome"] == "partial"
    assert output["issued"] == [_iso(_DUE[0]), _iso(_DUE[2])]
    assert list(output["not_issued"]) == [_iso(_DUE[1])]
    assert output["not_issued"][_iso(_DUE[1])].startswith("forecast")
    assert [row[1] for row in _rows(store)] == [_DUE[0].to_pydatetime(), _DUE[2].to_pydatetime()]
    # The runner counts the refused target as missing, not as present.
    record = dlr_live_run.classify_day_ahead(_CITY, 0, output, "", env={})
    assert record["outcome"] == "partial" and record["missing"] == [_iso(_DUE[1])]


def test_no_substitute_a_band_artifact_that_does_not_match_the_manifest_refuses_before_any_model_loads(
        store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path, digest="0" * 64)
    loaded = []
    monkeypatch.setattr(daf, "make_model_loader", lambda: loaded.append(1))

    code, output = _run(tmp_path)

    assert code == 0
    assert output["outcome"] == "error"
    assert set(output["not_issued"]) == {_iso(t) for t in _DUE}
    assert all("hash mismatch" in reason for reason in output["not_issued"].values())
    assert loaded == []
    assert output["cooling_model_sha256"] is None
    assert _rows(store) == []


def test_no_substitute_the_live_manifest_without_the_band_entry_is_a_refusal_not_a_crash(store, tmp_path, monkeypatch):
    """Until 08-05 pins the band artifact in the live manifest the child must refuse, never use the file."""
    _stub_weather(monkeypatch)
    manifest = tmp_path / "empty.sha256"
    manifest.write_text("", encoding="utf-8")
    original = day_ahead_band.load_verified_band
    monkeypatch.setattr(day_ahead_band, "load_verified_band",
                        lambda *a, **k: original(day_ahead_band.BAND_ARTIFACT_PATH, str(manifest)))

    code, output = _run(tmp_path)

    assert code == 0 and output["outcome"] == "error"
    assert all("no entry in the manifest" in reason for reason in output["not_issued"].values())
    assert _rows(store) == []


def test_no_substitute_a_cooling_model_hash_refusal_gives_error_and_no_rows(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)

    def loader(city, method):
        raise fcr.ArtifactIntegrityError(f"{city} {method}: sha256 differs from the manifest; not loading it")

    loader.served = []
    monkeypatch.setattr(daf, "make_model_loader", lambda: loader)
    fetched = []
    _stub_weather(monkeypatch, calls=fetched)

    code, output = _run(tmp_path)

    assert code == 0
    assert output["outcome"] == "error"
    assert set(output["not_issued"]) == {_iso(t) for t in _DUE}
    assert all(reason.startswith("model") and "ArtifactIntegrityError" in reason
               for reason in output["not_issued"].values())
    assert fetched == []  # no value was computed
    assert _rows(store) == []


def test_a_database_that_cannot_be_reached_is_an_error_with_a_database_reason(tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)

    def down(url=None):
        raise supabase_store.StoreError("database connection failed: could not connect")

    monkeypatch.setattr(supabase_store, "connect", down)

    code, output = _run(tmp_path)

    assert code == 0
    assert output["outcome"] == "error"
    assert set(output["not_issued"]) == {_iso(t) for t in _DUE}
    assert all(reason.startswith("database") for reason in output["not_issued"].values())


# --------------------------------------------------------------------------------------------------
# redaction (OD-6, T-08-11)
# --------------------------------------------------------------------------------------------------

def test_redaction_a_url_and_a_token_in_a_provider_message_never_reach_the_output_or_the_table(
        store, tmp_path, monkeypatch, caplog):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    url = "postgresql://" + "svc_user:" + "hunter2hunter2" + "@db.projectref1234.example.com:5432/postgres"
    token = "tok_" + "ABCDEF123456"
    monkeypatch.setenv("SUPABASE_DB_URL", url)
    monkeypatch.setenv("SYNOPTIC_TOKEN", token)

    def leaky(city, decision_time, **kw):
        raise shadow.StaleOrMissingDataError(f"GET failed for {url}: bad credentials {token} (token={token})")

    monkeypatch.setattr(shadow, "fetch_live_anchor_observation", leaky)

    with caplog.at_level("INFO"):
        code, output = _run(tmp_path)

    out_path = str(tmp_path / f"{_CITY}.{_iso(_NOW)}.json")
    with open(out_path, encoding="utf-8") as fh:
        text = fh.read()
    assert code == 0 and output["outcome"] == "error"
    for secret in (url, token, "hunter2hunter2", "projectref1234"):
        assert secret not in text
        assert secret not in caplog.text
    assert all(reason.startswith("anchor") for reason in output["not_issued"].values())
    assert _rows(store) == []


def test_redaction_an_unexpected_error_is_named_by_type_and_redacted(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    token = "tok_" + "ZZZZ9999"
    monkeypatch.setenv("SYNOPTIC_TOKEN", token)

    def boom(*args, **kwargs):
        raise RuntimeError(f"surprise carrying {token}")

    monkeypatch.setattr(daf, "build_row", boom)

    code, output = _run(tmp_path)

    assert code == 0 and output["outcome"] == "error"
    for reason in output["not_issued"].values():
        assert reason.startswith("unexpected: RuntimeError")
        assert token not in reason
    assert _rows(store) == []


def test_a_failing_live_band_query_still_issues_every_target_on_the_test_band(store, tmp_path, monkeypatch):
    """WR-01: a live-band query fault falls back to the TEST band; it does not block publication."""
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)

    def boom(*args, **kwargs):
        raise RuntimeError("live pairs query failed")

    monkeypatch.setattr(day_ahead_band, "live_pairs", boom)

    code, output = _run(tmp_path)

    assert code == 0 and output["outcome"] == "issued"
    assert output["issued"] == [_iso(t) for t in _DUE] and output["not_issued"] == {}
    assert set(output["band_sources"].values()) == {"test-split"}
    assert {row[6] for row in _rows(store)} == {"test-split"} and len(_rows(store)) == len(_DUE)


# --------------------------------------------------------------------------------------------------
# no_store, out_of_bounds
# --------------------------------------------------------------------------------------------------

def test_no_store_never_connects_computes_with_the_test_band_and_inserts_nothing(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    connects = []
    monkeypatch.setattr(supabase_store, "connect", lambda url=None: connects.append(1))

    code, output = _run(tmp_path, extra=["--no-store"])

    assert code == 0
    assert connects == []
    assert output["dry_run"] is True
    assert output["issued"] == [] and output["not_issued"] == {}
    assert set(output["computed"]) == {_iso(t) for t in _DUE}
    for entry in output["computed"].values():
        assert entry["band_source"] == "test-split"
        assert entry["lower"] < entry["amps"] < entry["upper"]
    assert _rows(store) == []


def test_no_store_has_no_dry_run_key_when_the_store_is_used(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    _, output = _run(tmp_path)
    assert "dry_run" not in output and "computed" not in output


def test_out_of_bounds_a_value_outside_the_rating_bounds_is_still_inserted_and_listed(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    upper = config.RATING_BOUNDS_BY_LOCATION[_CITY][1]
    monkeypatch.setattr(daf, "compute_value", lambda *a, **k: upper + 1000.0)

    code, output = _run(tmp_path)

    assert code == 0
    assert output["outcome"] == "issued"
    assert output["out_of_bounds"] == output["issued"] == [_iso(t) for t in _DUE]
    assert len(_rows(store)) == 3
    assert {row[3] for row in _rows(store)} == {upper + 1000.0}


# --------------------------------------------------------------------------------------------------
# output
# --------------------------------------------------------------------------------------------------

def test_an_output_path_that_cannot_be_written_is_exit_one(store, tmp_path, monkeypatch):
    _stub_weather(monkeypatch)
    _trust_band(monkeypatch, tmp_path)
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    argv = ["--city", _CITY, "--output", str(blocker / "nested" / "out.json")]
    assert dlr_day_ahead.main(argv, now=_NOW) == 1


def test_the_child_names_no_embargoed_data_and_no_free_text_reaches_a_row():
    """Every stored column is a typed value; the reason strings exist only in the output document."""
    assert not [c for c in contract.TABLE_COLUMNS if "reason" in c or "error" in c or "message" in c]
    with open(os.path.join(os.path.dirname(dlr_day_ahead.__file__), "dlr_day_ahead.py"), encoding="utf-8") as fh:
        source = fh.read()
    for text in ("data/shadow/predictions", "read_city_log_entries", "anchored_pair_frame", "2026-09-30_"):
        assert text not in source
