"""
Tests of the read-only first-slot check `backend/day_ahead_verify.py` (production-pipeline Phase 8,
plan 08-06: DAY-08, D-17).

The checks run for real here: `main(["--check-store", "--since", T0, ...])` reads a throwaway
local Postgres migrated through the write-side file only, as role `dlr_writer`
(`supabase_store.connect` is replaced to return that session). A temporary manifest stands in for
the live one. Rows are seeded as the administrator with `day_ahead_contract.INSERT_COLUMNS` and a
matching `pipeline_run.day_ahead` record, then one thing at a time is made wrong. Nothing here
touches the live Supabase project, the live job or the network.

The local-Postgres tests need `DLR_TEST_PG_AUTOSTART=1` (backend/tests/local_pg.py). A skip proves
nothing, so the plan's verify command treats a skip as a failure.
"""

import json
import os

import pandas as pd
import pytest

import config
import day_ahead_band
import day_ahead_contract as contract
import day_ahead_forecast as daf
import day_ahead_verify as verify
import dlr_live_check_models as check_models
import local_pg
import supabase_store

_STORE_MIGRATION = "20261108120000_day_ahead_forecast_store.sql"

# 00:05Z on 2026-11-09 is the first run after go-live: the due targets are 06:00, 12:00 and 18:00Z.
_DECISION = pd.Timestamp("2026-11-09T00:05:00Z")
_SINCE = "2026-11-01T00:00:00Z"
_RUN_ID = "9001"
_BAND_SHA = "b1" * 32
_CITIES = tuple(config.LOCATIONS)
_FP_URL_PASSWORD = "pw-" + "s3cr3t-value"
_FP_URL_HOST = "db.fakeprojectref0123456789.example.invalid"
_FP_URL = f"postgresql://dlr_writer.fakeprojectref0123456789:{_FP_URL_PASSWORD}@{_FP_URL_HOST}:5432/postgres"


def _iso(stamp) -> str:
    return pd.Timestamp(stamp).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cooling_sha(city) -> str:
    return f"{_CITIES.index(city) + 1:02x}" * 32


@pytest.fixture
def manifest_file(tmp_path):
    """A temporary live manifest: the band artifact and the four served cooling files, fake hashes."""
    lines = [f"{_BAND_SHA}  {check_models._key(day_ahead_band.BAND_ARTIFACT_PATH)}"]
    for city in _CITIES:
        lines.append(f"{_cooling_sha(city)}  {check_models._key(daf.serving_model_path(city))}")
    path = tmp_path / "LIVE_ARTIFACT_HASHES.sha256"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _good_row(city, valid_time, decision=_DECISION):
    """A row that passes every check for `city`."""
    valid = pd.Timestamp(valid_time)
    return {
        "city": city,
        "valid_time": valid.to_pydatetime(),
        "issued_at": pd.Timestamp(decision).to_pydatetime(),
        "forecast_run_init_time": (valid - pd.Timedelta(hours=24)).to_pydatetime(),
        "horizon_minutes": contract.HORIZON_MINUTES,
        "forecast_amps": 1500.0,
        "forecast_ci_lower_amps": 1400.0,
        "forecast_ci_upper_amps": 1600.0,
        "band_source": "test-split",
        "band_n": verify.TEST_BAND_N,
        "band_pairs_through": None,
        "band_artifact_sha256": _BAND_SHA,
        "forecast_method": contract.FORECAST_METHOD,
        "cooling_model_sha256": _cooling_sha(city),
        "cooling_model_source": "refit" if city in daf.refit_cities() else "frozen",
        "anchor_observation_time": (pd.Timestamp(decision) - pd.Timedelta(minutes=5)).to_pydatetime(),
        "anchor_source": "tceq",
        "label": contract.DAY_AHEAD_LABEL,
        "config_version": config.RATING_CONFIG_VERSION,
        "config_fingerprint": supabase_store.rating_config_fingerprint(city),
        "run_id": _RUN_ID,
        "run_attempt": 1,
        "pipeline_version": "abc1234",
        "schema_version": 1,
    }


def _clean_rows(decision=_DECISION):
    return [_good_row(city, target, decision) for city in _CITIES for target in daf.due_targets(decision)]


# --------------------------------------------------------------------------------------------------
# Local Postgres: the write-side migration only (the expose migration is plan 08-09's)
# --------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_url(tmp_path_factory):
    local_pg.require_local_pg()
    with local_pg.cluster(tmp_path_factory) as url:
        paths = [p for p in local_pg.migration_files() if os.path.basename(p) <= _STORE_MIGRATION]
        assert os.path.basename(paths[-1]) == _STORE_MIGRATION, [os.path.basename(p) for p in paths]
        local_pg.apply_migrations(url, paths=paths)
        yield url


class _Spy:
    """Delegates everything to a real connection and records `rollback` and `close` calls."""

    def __init__(self, conn):
        object.__setattr__(self, "_conn", conn)
        object.__setattr__(self, "rollbacks", 0)
        object.__setattr__(self, "closes", 0)

    def rollback(self):
        object.__setattr__(self, "rollbacks", self.rollbacks + 1)
        return self._conn.rollback()

    def close(self):
        object.__setattr__(self, "closes", self.closes + 1)
        return self._conn.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        setattr(self._conn, name, value)


@pytest.fixture
def store(pg_url, monkeypatch, manifest_file):
    """An empty store; `supabase_store.connect` hands out a fresh dlr_writer session wrapped in a spy."""
    import psycopg

    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://example.invalid/placeholder")
    with psycopg.connect(pg_url, autocommit=True) as admin:
        admin.execute("truncate public.day_ahead_forecast")
        admin.execute("delete from public.pipeline_run")
    opened = []

    def connect(url=None):
        conn = psycopg.connect(pg_url, autocommit=True)
        conn.execute("set timezone = 'UTC'")
        conn.execute("set role dlr_writer")
        spy = _Spy(conn)
        opened.append(spy)
        return spy

    monkeypatch.setattr(supabase_store, "connect", connect)

    class Store:
        url = pg_url
        sessions = opened

        @staticmethod
        def seed(rows=None, record=True, record_mutator=None):
            """Insert `rows` and a pipeline_run record built from them (what the runner would have stored)."""
            rows = _clean_rows() if rows is None else rows
            with psycopg.connect(pg_url, autocommit=True) as admin:
                for row in rows:
                    admin.execute(
                        f"insert into {contract.TABLE} ({', '.join(contract.INSERT_COLUMNS)}) values ("
                        + ", ".join(f"%({c})s" for c in contract.INSERT_COLUMNS) + ")", row)
                if record:
                    cities = {}
                    for row in rows:
                        entry = cities.setdefault(row["city"], {"outcome": "issued", "issued": [], "due": []})
                        entry["issued"].append(_iso(row["valid_time"]))
                        entry["due"].append(_iso(row["valid_time"]))
                    day_ahead = {"started_at": "x", "finished_at": "y", "budget_s": 900, "cities": cities}
                    if record_mutator:
                        record_mutator(day_ahead)
                    admin.execute("insert into public.pipeline_run (run_id, day_ahead) values (%s, %s::jsonb)",
                                  (_RUN_ID, json.dumps(day_ahead)))

        @staticmethod
        def counts():
            with psycopg.connect(pg_url, autocommit=True) as admin:
                return (admin.execute(f"select count(*) from {contract.TABLE}").fetchone()[0],
                        admin.execute("select count(*) from public.pipeline_run").fetchone()[0])

    return Store


def _run(tmp_path, manifest_file, since=_SINCE):
    out = tmp_path / "evidence.json"
    code = verify.main(["--check-store", "--since", since, "--json-out", str(out)], manifest_path=manifest_file)
    return code, json.loads(out.read_text(encoding="utf-8"))


def _by_name(report):
    return {c["name"]: c for c in report["checks"]}


def _failing(report):
    return {c["name"] for c in report["checks"] if not c["ok"]}


def _rows_with(changes_by_city_hour):
    """Clean rows with `changes` applied to the rows matching (city, UTC hour of the target)."""
    rows = _clean_rows()
    for (city, hour), changes in changes_by_city_hour.items():
        for row in rows:
            if row["city"] == city and pd.Timestamp(row["valid_time"]).hour == hour:
                row.update(changes)
    return rows


# --------------------------------------------------------------------------------------------------
# pass
# --------------------------------------------------------------------------------------------------


def test_pass_every_check_is_ok_and_the_exit_code_is_zero(store, manifest_file, tmp_path, capsys):
    store.seed()
    code, report = _run(tmp_path, manifest_file)
    assert code == 0
    assert [c["name"] for c in report["checks"]] == list(verify.CHECK_NAMES)
    assert all(c["ok"] for c in report["checks"]), report["checks"]
    assert report["exit_code"] == 0
    assert report["since"] == _SINCE
    assert len(report["rows"]) == 12
    assert {row["city"] for row in report["rows"]} == set(_CITIES)
    out = capsys.readouterr().out
    for name in verify.CHECK_NAMES:
        assert f"PASS {name}" in out
    assert out.count("A  [") == 12  # one line per row


def test_the_refit_city_expects_the_refit_source_and_the_others_frozen(store, manifest_file, tmp_path):
    # AUSTIN serves the refit file today; serving it as 'frozen' flips only the cooling check.
    assert "AUSTIN" in daf.refit_cities()
    store.seed(_rows_with({("AUSTIN", 6): {"cooling_model_source": "frozen"}}))
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"cooling_model_matches_the_manifest"}


# --------------------------------------------------------------------------------------------------
# each failure flips exactly its own check
# --------------------------------------------------------------------------------------------------


def test_a_missing_due_target_fails_coverage_and_names_the_city_and_target(store, manifest_file, tmp_path, capsys):
    rows = [r for r in _clean_rows()
            if not (r["city"] == "AUSTIN" and pd.Timestamp(r["valid_time"]).hour == 18)]
    store.seed(rows)  # the stage recorded what it issued (2), so only coverage is wrong
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"first_run_covers_every_due_target"}
    detail = _by_name(report)["first_run_covers_every_due_target"]["detail"]
    assert "AUSTIN" in detail and "2026-11-09T18:00:00Z" in detail
    assert "FAIL first_run_covers_every_due_target" in capsys.readouterr().out


def test_a_wrong_label_fails_only_the_label_check(store, manifest_file, tmp_path):
    store.seed(_rows_with({("MIDLAND", 12): {"label": "day-ahead; validated"}}))
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"label_is_the_d11_label"}


def test_band_source_live_rolling_at_launch_fails_only_the_band_check(store, manifest_file, tmp_path):
    store.seed(_rows_with({("AUSTIN", 6): {
        "band_source": "live-rolling",
        "band_pairs_through": pd.Timestamp("2026-11-08T12:00:00Z").to_pydatetime()}}))
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"band_is_the_test_split_artifact"}


def test_a_band_hash_that_is_not_the_manifest_entry_fails_only_the_band_check(store, manifest_file, tmp_path):
    store.seed(_rows_with({("CORPUS_CHRISTI", 18): {"band_artifact_sha256": "ee" * 32}}))
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"band_is_the_test_split_artifact"}
    assert "CORPUS_CHRISTI" in _by_name(report)["band_is_the_test_split_artifact"]["detail"]


def test_a_cooling_hash_that_is_not_the_served_files_entry_fails_only_the_cooling_check(
        store, manifest_file, tmp_path):
    store.seed(_rows_with({("MIDLAND", 6): {"cooling_model_sha256": "dd" * 32}}))
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"cooling_model_matches_the_manifest"}


def test_a_config_fingerprint_that_is_not_the_codes_fails_only_the_config_check(store, manifest_file, tmp_path):
    store.seed(_rows_with({("EL_PASO", 6): {"config_fingerprint": "ff" * 32}}))
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"config_identity_matches_the_code"}


def test_a_config_version_that_is_not_the_codes_fails_only_the_config_check(store, manifest_file, tmp_path):
    store.seed(_rows_with({("EL_PASO", 6): {"config_version": "v0-old"}}))
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"config_identity_matches_the_code"}


def test_a_lead_over_18_hours_fails_only_the_lead_check(store, manifest_file, tmp_path):
    # A fourth row for a target that was not yet due at the run's decision time (23 h 55 min away).
    rows = _clean_rows()
    rows.append(_good_row("AUSTIN", "2026-11-10T00:00:00Z"))
    store.seed(rows)
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"issue_lead_at_most_18h"}
    assert "2026-11-10T00:00:00Z" in _by_name(report)["issue_lead_at_most_18h"]["detail"]


def test_no_pipeline_run_record_fails_only_the_stage_record_check(store, manifest_file, tmp_path):
    store.seed(record=False)
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"pipeline_run_records_the_stage"}


def test_a_recorded_issued_list_that_differs_from_the_rows_fails_only_the_stage_record_check(
        store, manifest_file, tmp_path):
    def drop_one(day_ahead):
        day_ahead["cities"]["AUSTIN"]["issued"].pop()

    store.seed(record_mutator=drop_one)
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert _failing(report) == {"pipeline_run_records_the_stage"}


def test_a_city_with_no_row_fails_first_run_found_and_names_the_city(store, manifest_file, tmp_path):
    store.seed([r for r in _clean_rows() if r["city"] != "EL_PASO"])
    code, report = _run(tmp_path, manifest_file)
    assert code == 1
    assert "first_run_found" in _failing(report)
    assert "EL_PASO" in _by_name(report)["first_run_found"]["detail"]


def _evaluate_in_memory(rows):
    """The checks over rows held in memory (for states the table's own CHECKs refuse to store)."""
    manifest = {check_models._key(day_ahead_band.BAND_ARTIFACT_PATH): _BAND_SHA}
    manifest.update({check_models._key(daf.serving_model_path(c)): _cooling_sha(c) for c in _CITIES})
    record = {"cities": {c: {"issued": [_iso(r["valid_time"]) for r in rows if r["city"] == c]} for c in _CITIES}}
    results = {r.name: r for r in verify.evaluate(rows, {_RUN_ID: record}, manifest)}
    return [name for name, result in results.items() if not result.ok]


def test_the_in_memory_baseline_passes_every_check():
    assert _evaluate_in_memory(_clean_rows()) == []


def test_a_band_that_does_not_bracket_the_value_fails_only_the_bracket_check():
    # The table's CHECK refuses such a row, so the check is proven on rows held in memory.
    rows = _clean_rows()
    rows[0]["forecast_ci_upper_amps"] = rows[0]["forecast_amps"] - 1.0
    assert _evaluate_in_memory(rows) == ["band_brackets_the_value"]


def test_a_weather_run_that_is_not_24_hours_old_fails_only_the_weather_run_check():
    rows = _clean_rows()
    rows[0]["forecast_run_init_time"] = pd.Timestamp(rows[0]["valid_time"]).to_pydatetime() - pd.Timedelta(hours=18)
    assert _evaluate_in_memory(rows) == ["method_horizon_and_weather_run"]


def test_a_wrong_method_or_horizon_fails_only_the_weather_run_check():
    for change in ({"forecast_method": "persistence_24h"}, {"horizon_minutes": 60}):
        rows = _clean_rows()
        rows[3].update(change)
        assert _evaluate_in_memory(rows) == ["method_horizon_and_weather_run"], change


# --------------------------------------------------------------------------------------------------
# nothing, config, redaction, read only
# --------------------------------------------------------------------------------------------------


def test_nothing_written_since_the_time_fails_first_run_found(store, manifest_file, tmp_path):
    store.seed()
    code, report = _run(tmp_path, manifest_file, since="2999-01-01T00:00:00Z")
    assert code == 1
    assert _by_name(report)["first_run_found"]["ok"] is False
    assert report["rows"] == []
    # no first run means nothing can be called correct: no check passes vacuously
    assert _failing(report) == set(verify.CHECK_NAMES)


def test_a_missing_database_url_is_exit_two_naming_the_variable(monkeypatch, manifest_file, capsys):
    monkeypatch.delenv("SUPABASE_DB_URL", raising=False)
    monkeypatch.delenv("SUPABASE_ADMIN_DB_URL", raising=False)
    code = verify.main(["--check-store", "--since", _SINCE], manifest_path=manifest_file)
    assert code == 2
    err = capsys.readouterr().err
    assert "SUPABASE_DB_URL" in err and "postgres" not in err.lower().replace("supabase_db_url", "")


@pytest.mark.parametrize("since", ["yesterday", "2026-11-09T00:00:00", "2026-13-40T00:00:00Z", ""])
def test_a_bad_since_is_exit_two(since, monkeypatch, manifest_file, capsys):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://example.invalid/placeholder")
    assert verify.main(["--check-store", "--since", since], manifest_path=manifest_file) == 2
    assert "--since" in capsys.readouterr().err


def test_since_with_an_offset_is_converted_to_utc():
    assert verify.parse_since("2026-11-08T18:00:00-06:00") == verify.parse_since("2026-11-09T00:00:00Z")


def test_an_unreadable_manifest_is_exit_two(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SUPABASE_DB_URL", "postgresql://example.invalid/placeholder")
    code = verify.main(["--check-store", "--since", _SINCE], manifest_path=str(tmp_path / "missing.sha256"))
    assert code == 2
    assert "manifest" in capsys.readouterr().err


def test_a_connection_failure_prints_and_stores_no_url_host_or_password(
        monkeypatch, manifest_file, tmp_path, capsys):
    monkeypatch.setenv("SUPABASE_DB_URL", _FP_URL)

    def refuse(url=None):
        raise RuntimeError(f"could not connect to server at {_FP_URL_HOST} using {_FP_URL} "
                           f"(password={_FP_URL_PASSWORD}) as user dlr_writer.fakeprojectref0123456789")

    monkeypatch.setattr(supabase_store, "connect", refuse)
    out = tmp_path / "evidence.json"
    code = verify.main(["--check-store", "--since", _SINCE, "--json-out", str(out)], manifest_path=manifest_file)
    assert code == 1
    shown = capsys.readouterr()
    stored = out.read_text(encoding="utf-8")
    for text in (shown.out, shown.err, stored):
        for secret in (_FP_URL, _FP_URL_PASSWORD, _FP_URL_HOST, "fakeprojectref0123456789"):
            assert secret not in text
    assert json.loads(stored)["checks"][0]["name"] == "database_read"


def test_the_report_has_no_connection_text_even_when_a_row_value_carries_it(store, manifest_file, tmp_path,
                                                                           monkeypatch):
    # A hostile value in a text column must not carry a connection string into the evidence file.
    monkeypatch.setenv("SUPABASE_DB_URL", _FP_URL)
    store.seed(_rows_with({("AUSTIN", 6): {"anchor_source": _FP_URL}}))
    code, report = _run(tmp_path, manifest_file)
    assert code == 0
    text = (tmp_path / "evidence.json").read_text(encoding="utf-8")
    assert _FP_URL not in text and _FP_URL_PASSWORD not in text and _FP_URL_HOST not in text


def test_the_session_is_read_only_changes_nothing_and_is_rolled_back(store, manifest_file, tmp_path):
    import psycopg

    store.seed()
    before = store.counts()
    code, _ = _run(tmp_path, manifest_file)
    assert code == 0
    assert store.counts() == before
    assert len(store.sessions) == 1
    spy = store.sessions[0]
    assert spy.rollbacks >= 1 and spy.closes >= 1
    assert spy.read_only is True and spy.autocommit is False


def test_a_write_inside_the_scripts_connection_is_refused(store, manifest_file, monkeypatch):
    """The session the script opens refuses a write even for a role that holds INSERT (T-08-18)."""
    import psycopg

    seen = {}

    def attempt_write(conn, since):
        try:
            conn.execute(f"insert into {contract.TABLE} ({', '.join(contract.INSERT_COLUMNS)}) values ("
                         + ", ".join(f"%({c})s" for c in contract.INSERT_COLUMNS) + ")",
                         _good_row("AUSTIN", "2026-11-09T06:00:00Z"))
        except psycopg.errors.ReadOnlySqlTransaction:
            seen["refused"] = True
        return [], {}

    monkeypatch.setattr(verify, "fetch", attempt_write)
    verify.main(["--check-store", "--since", _SINCE], manifest_path=manifest_file)
    assert seen == {"refused": True}
    assert store.counts() == (0, 0)


def test_help_names_the_flags(capsys):
    with pytest.raises(SystemExit) as stop:
        verify.main(["--help"])
    assert stop.value.code == 0
    text = capsys.readouterr().out
    for flag in ("--check-store", "--since", "--json-out"):
        assert flag in text
