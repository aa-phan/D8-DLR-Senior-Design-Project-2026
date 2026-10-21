"""
Tests of the DB-03 backfill loader (production-pipeline Phase 4, DB-03, DB-06).

Offline tests use a fake connection that records every statement and keeps a set
of (city, slot) keys, so the DO NOTHING behavior, the transaction and the parity
counts are checked without a database. The live tests (env-gated, like
supabase_live_test.py) load into a throwaway local Postgres as the migration's own
`dlr_writer` role and never touch Supabase.

The Phase 3 fingerprints are evaluated on the sources of the manifest's git
commit. The fixture manifests carry a fake head, so the git-show step is replaced
by a runner that returns the working-tree files; one test calls the real runner
with the repository's own HEAD.

Follows backend/tests/city_rating_test.py's conventions (module-level imports,
plain asserts, no test classes, no network).
"""

import contextlib
import hashlib
import json
import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from urllib.parse import urlsplit

import pandas as pd
import pytest
import requests

import anomaly_detector
import config
import ercot_dlr_merger
import historical_archive
import supabase_load_backfill as loader
import supabase_store

_MIGRATION = os.path.join(
    os.path.dirname(__file__), "..", "..", "supabase", "migrations",
    "20261019000000_create_city_rating.sql",
)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")
_CITIES = tuple(config.LOCATIONS)
_HOURS = 3
_START = "2026-09-08T00:00:00Z"
_END = "2026-09-08T23:00:00Z"
_HEAD = "abcdef1234567"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """
    Replace `requests.get` for every test. The composer and `rate_city` catch
    every provider exception, so raising alone could be swallowed; the teardown
    assert on the recorded attempts cannot be.
    """
    attempts = []

    def boom(url, *args, **kwargs):
        attempts.append(url)
        raise AssertionError("requests.get must not be called in this test")

    monkeypatch.setattr(requests, "get", boom)
    yield
    assert attempts == []


@pytest.fixture(autouse=True)
def _offline_env(tmp_path, monkeypatch):
    # Another test module loads `.env` into the process at import time.
    for name in ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "HISTORICAL_ARCHIVE_PATH", str(tmp_path / "default_archive.csv"))
    # Trained models are git-ignored, so a test must not depend on whether this
    # checkout has them.
    monkeypatch.setattr(anomaly_detector, "_load_city_model_or_none", lambda city: None)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="module")
def _pg_admin_url(tmp_path_factory):
    """
    URL of an empty throwaway database, as a superuser. Either the local
    database the caller named or a private cluster this fixture creates and
    always stops.
    """
    explicit = os.environ.get("DLR_TEST_DATABASE_URL")
    if explicit:
        host = urlsplit(explicit).hostname
        if host not in _LOCAL_HOSTS:
            pytest.fail("DLR_TEST_DATABASE_URL must name a local database (127.0.0.1, localhost or ::1)")
        yield explicit
        return
    if os.environ.get("DLR_TEST_PG_AUTOSTART") != "1":
        pytest.skip("set DLR_TEST_PG_AUTOSTART=1 or DLR_TEST_DATABASE_URL to run the live Postgres tests")

    psycopg = pytest.importorskip("psycopg")
    if shutil.which("initdb") is None or shutil.which("pg_ctl") is None:
        pytest.skip("initdb / pg_ctl not on PATH")

    root = tmp_path_factory.mktemp("pg")
    data = str(root / "data")
    log_file = str(root / "log")
    port = _free_port()
    subprocess.run(
        ["initdb", "-D", data, "-U", "postgres", "-A", "trust", "-E", "UTF8", "--no-locale"],
        check=True, capture_output=True,
    )
    options = (f"-p {port} -c listen_addresses=127.0.0.1 -c unix_socket_directories='' "
               "-c fsync=off -c synchronous_commit=off")
    try:
        subprocess.run(
            ["pg_ctl", "-D", data, "-l", log_file, "-w", "-o", options, "start"],
            check=True, capture_output=True,
        )
        with psycopg.connect(f"postgresql://postgres@127.0.0.1:{port}/postgres", autocommit=True) as conn:
            conn.execute("create database dlr_test")
        yield f"postgresql://postgres@127.0.0.1:{port}/dlr_test"
    finally:
        subprocess.run(["pg_ctl", "-D", data, "-m", "immediate", "stop"], capture_output=True)


_ROLE_SQL = """
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
end
$$;
"""


def _apply_migration(admin_url):
    """
    Create the Supabase roles a plain cluster lacks, then apply the committed
    migration in one transaction.
    """
    import psycopg

    with open(_MIGRATION, encoding="utf-8") as handle:
        sql = handle.read()
    with psycopg.connect(admin_url) as conn:
        conn.execute(_ROLE_SQL)
        conn.execute(sql)


def _writer_url(admin_url):
    """The same database as the migration's `dlr_writer` (trust auth, no credential locally)."""
    parts = urlsplit(admin_url)
    return parts._replace(netloc=f"dlr_writer@{parts.hostname}:{parts.port}").geturl()


def _reset(admin_url):
    """Make sure the schema exists (idempotent), then empty both tables as the superuser."""
    import psycopg

    _apply_migration(admin_url)
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("truncate public.city_rating, public.pipeline_run")


def _admin_rows(admin_url, sql, params=None):
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(admin_url, autocommit=True, row_factory=dict_row) as conn:
        return conn.execute(sql, params).fetchall()


# ──────────────────────────────────────────────────────────────────────────────
# Fixture archive, manifest and runners
# ──────────────────────────────────────────────────────────────────────────────

def _archive_rows(hours=_HOURS):
    rows = []
    for city_index, city in enumerate(_CITIES):
        for hour in range(hours):
            rows.append({
                "datetime_utc": f"2026-09-08T{hour:02d}:00:00Z",
                "city": city,
                "air_temp": 30.0 + hour + city_index,
                "wind_speed": 3.0 + 0.5 * hour,
                "solar_radiation": 400.0 + 10 * hour,
                "dlr_amps": 1500.0 + 10 * hour + 100 * city_index,
                "static_rating": 1000.0 + 100 * city_index,
                "status": "ok" if hour % 2 == 0 else "fallback",
                "fallback": hour % 2 == 1,
                "schema_version": 1,
            })
    return rows


def _write_archive(tmp_path, rows, name="archive.csv"):
    path = tmp_path / name
    pd.DataFrame(rows, columns=historical_archive.ARCHIVE_COLUMNS).to_csv(path, index=False)
    return str(path)


def _sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _manifest_for(path, rows_by_city, **overrides):
    models = {}
    for city in _CITIES:
        for kind in ("forecast", "anomaly"):
            name = f"{kind}_{city}.joblib"
            models[name] = hashlib.sha256(name.encode()).hexdigest()
    manifest = {
        "schema": "real_data_validation_manifest/1",
        "window": {"start": _START, "end": _END, "step_hours": 1.0, "steps_per_city": _HOURS,
                   "warmup_hours": 0.0, "scored_start": _START},
        "files": {"archive": {"path": path, "bytes": os.path.getsize(path), "sha256": _sha256(path)}},
        "archive_rows_by_city": dict(rows_by_city),
        "cities": list(_CITIES),
        "git": {"head": _HEAD, "backend_dirty": False},
        "forecast_method": "ml",
        "models": models,
    }
    manifest.update(overrides)
    return manifest


def _write_manifest(tmp_path, manifest, name="manifest.json"):
    path = tmp_path / name
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return str(path)


@pytest.fixture
def archive(tmp_path):
    """(csv path, manifest dict, manifest path) for 3 hourly rows per city."""
    csv_path = _write_archive(tmp_path, _archive_rows())
    manifest = _manifest_for(csv_path, {city: _HOURS for city in _CITIES})
    return csv_path, manifest, _write_manifest(tmp_path, manifest)


def _working_tree_git_show(commit, path, repo_root):
    with open(os.path.join(repo_root, path), encoding="utf-8", newline="") as handle:
        return handle.read()


@pytest.fixture
def working_tree_sources(monkeypatch):
    """The git-show step returns the working-tree file for any commit, so no test depends on the fake head."""
    monkeypatch.setattr(loader, "_git_show", _working_tree_git_show)


def _live_identity():
    return {
        city: {
            "config_fingerprint": supabase_store.rating_config_fingerprint(city),
            "forecast_model_sha256": hashlib.sha256(f"forecast_{city}.joblib".encode()).hexdigest(),
            "anomaly_model_sha256": hashlib.sha256(f"anomaly_{city}.joblib".encode()).hexdigest(),
        }
        for city in _CITIES
    }


@pytest.fixture
def fast_fingerprints(monkeypatch):
    """Skip the child process in tests that are not about it: the live fingerprints stand in."""
    monkeypatch.setattr(
        loader, "phase3_config_fingerprints",
        lambda manifest, repo_root=None, git_show=None: {
            city: supabase_store.rating_config_fingerprint(city) for city in _CITIES
        },
    )


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def fetchone(self):
        return (self._value,)


class _FakeCursor:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def executemany(self, sql, params_seq):
        params_seq = list(params_seq)
        self._conn.sent.append(("executemany", sql, params_seq))
        for params in params_seq:
            self._conn.keys.add((params["city"], params["valid_time"]))

    def execute(self, sql, params=None):
        self._conn.sent.append(("execute", sql, params))
        return _FakeResult(0)


class _FakeConn:
    """Records every statement and keeps the (city, slot) keys that an insert with DO NOTHING would hold."""

    def __init__(self, existing=()):
        self.sent = []
        self.events = []
        self.keys = set(existing)
        self.closed = False

    @contextlib.contextmanager
    def transaction(self):
        self.events.append("begin")
        yield
        self.events.append("commit")

    def cursor(self):
        return _FakeCursor(self)

    def execute(self, sql, params=None):
        self.sent.append(("execute", sql, params))
        if "select count(*)" in sql:
            wanted = {(params["city"], slot) for slot in params["slots"]}
            return _FakeResult(len(wanted & self.keys))
        raise AssertionError(f"the loader sent an unexpected statement: {sql!r}")

    def close(self):
        self.closed = True


def _no_connection(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("no connection may be opened")

    monkeypatch.setattr(supabase_store, "connect", boom)


# ──────────────────────────────────────────────────────────────────────────────
# Offline tests
# ──────────────────────────────────────────────────────────────────────────────

def test_loader_refuses_an_archive_that_does_not_match_the_manifest(tmp_path, archive, monkeypatch, capsys):
    csv_path, manifest, manifest_path = archive
    _no_connection(monkeypatch)

    # One extra byte: the sha256 (and the size) no longer match the manifest.
    with open(csv_path, "ab") as handle:
        handle.write(b"\n")
    assert loader.main(["--manifest", manifest_path]) == 1
    captured = capsys.readouterr()
    assert "does not match the Phase 3 manifest" in captured.out + captured.err

    # Same size, one character changed: only the sha256 can tell.
    with open(csv_path, "rb+") as handle:
        handle.truncate(os.path.getsize(csv_path) - 1)
        handle.seek(0)
        original = handle.read()
        assert b"1500.0" in original
        handle.seek(0)
        handle.write(original.replace(b"1500.0", b"1599.0", 1))
    assert os.path.getsize(csv_path) == manifest["files"]["archive"]["bytes"]
    assert loader.main(["--manifest", manifest_path]) == 1
    assert "does not match the Phase 3 manifest (sha256)" in "".join(capsys.readouterr())
    with open(csv_path, "rb+") as handle:
        handle.write(original)

    # The same bytes under a manifest that states another size: refused as well.
    manifest["files"]["archive"]["bytes"] += 7
    wrong_size = _write_manifest(tmp_path, manifest, "wrong_size.json")
    assert loader.main(["--manifest", wrong_size]) == 1
    assert "does not match the Phase 3 manifest" in "".join(capsys.readouterr())

    # A missing archive or manifest exits 2 and names the path.
    missing_csv = str(tmp_path / "gone.csv")
    assert loader.main(["--manifest", manifest_path, "--csv", missing_csv]) == 2
    assert missing_csv in capsys.readouterr().err
    missing_manifest = str(tmp_path / "no_manifest.json")
    assert loader.main(["--manifest", missing_manifest]) == 2
    assert missing_manifest in capsys.readouterr().err


def test_rows_map_to_city_rating_columns_with_backfill_labels(archive, working_tree_sources):
    csv_path, manifest, _ = archive
    identity = _live_identity()
    rows, stats = loader.prepare_rows(csv_path, manifest, identity)

    assert len(rows) == len(_CITIES) * _HOURS
    assert all(tuple(row) == loader.INSERT_COLUMNS for row in rows)
    austin = [row for row in rows if row["city"] == "AUSTIN"]
    by_hour = {row["valid_time"].hour: row for row in austin}
    first = by_hour[0]
    assert first["valid_time"] == datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    assert first["rating_amps"] == 1500.0
    assert first["static_rating_amps"] == 1000.0
    assert first["rating_mw"] == float(ercot_dlr_merger.amps_to_mw(1500.0, 345.0, 0.95))
    assert first["static_rating_mw"] == float(ercot_dlr_merger.amps_to_mw(1000.0, 345.0, 0.95))
    assert first["line_voltage_kv"] == 345.0 and first["power_factor"] == 0.95
    # The archive's wind_speed is the projected component.
    assert first["wind_perp_ms"] == 3.0
    assert "wind_speed_ms" not in first and "wind_direction_deg" not in first
    assert first["air_temp_c"] == 30.0 and first["solar_radiation_wm2"] == 400.0
    assert first["status"] == "ok" and first["fallback"] is False
    assert by_hour[1]["status"] == "fallback" and by_hour[1]["fallback"] is True
    assert first["fallback_gates"] == [] and first["alerts"] == [] and first["exhausted"] is False
    sha = _sha256(csv_path)
    assert first["origin"] == "backfill"
    assert first["run_id"] == "backfill-" + sha[:12]
    assert first["run_attempt"] == 1 and first["schema_version"] == 1
    assert first["pipeline_version"] == _HEAD[:7]
    assert stats["rows_read"] == len(rows) and stats["rows_dropped_by_validation"] == 0
    assert stats["csv_rows"] == {city: _HOURS for city in _CITIES}
    assert stats["duplicates_dropped"] == {city: 0 for city in _CITIES}

    # fallback reads back as bool or text, in any case.
    assert [loader._parse_fallback(v) for v in (True, False, "True", "false", " TRUE ", "FALSE")] == [
        True, False, True, False, True, False
    ]


def test_backfill_rows_carry_provisional_labels_and_phase3_model_hashes(archive, monkeypatch):
    csv_path, manifest, _ = archive
    # The live labels move with Phase 7; a backfill row must not follow them (R3, DB-06).
    monkeypatch.setattr(config, "RATING_CONFIG_VERSION", "v9-live-2099")
    monkeypatch.setattr(config, "RATING_BASIS", "LIVE BASIS TEXT")

    identity = loader.phase3_model_identity(manifest)
    assert set(identity) == set(_CITIES)
    for city in _CITIES:
        assert identity[city]["forecast_model_sha256"] == manifest["models"][f"forecast_{city}.joblib"]
        assert identity[city]["anomaly_model_sha256"] == manifest["models"][f"anomaly_{city}.joblib"]
        identity[city]["config_fingerprint"] = "c" * 64
    rows, _ = loader.prepare_rows(csv_path, manifest, identity)

    for row in rows:
        city = row["city"]
        assert row["config_version"] == loader.PHASE3_CONFIG_VERSION == "v1-provisional-2026-10-13"
        assert row["config_version"] != config.RATING_CONFIG_VERSION
        basis = row["rating_basis"]
        assert basis.startswith("PROVISIONAL (OD-5)")
        assert _START in basis and _HEAD[:7] in basis and "Drake" in basis and "REVAL-01" in basis
        assert "LIVE BASIS TEXT" not in basis
        assert row["forecast_method"] == "ml"
        assert row["config_fingerprint"] == "c" * 64
        assert row["forecast_model_sha256"] == manifest["models"][f"forecast_{city}.joblib"]
        assert row["anomaly_model_sha256"] == manifest["models"][f"anomaly_{city}.joblib"]
    assert loader.backfill_rating_basis(manifest) == rows[0]["rating_basis"]

    # A method without a model file stores no forecast hash.
    naive = dict(manifest, forecast_method="naive")
    assert all(v["forecast_model_sha256"] is None for v in loader.phase3_model_identity(naive).values())
    assert all(v["anomaly_model_sha256"] for v in loader.phase3_model_identity(naive).values())

    # A missing entry or a malformed value stops the load, naming the key, before any statement.
    for key, broken in (("forecast_MIDLAND.joblib", None), ("anomaly_EL_PASO.joblib", None),
                        ("forecast_AUSTIN.joblib", "ABC"), ("anomaly_AUSTIN.joblib", "g" * 64)):
        models = dict(manifest["models"])
        if broken is None:
            del models[key]
        else:
            models[key] = broken
        with pytest.raises(ValueError, match=key.replace(".", r"\.")):
            loader.phase3_model_identity(dict(manifest, models=models))


def test_phase3_fingerprints_come_from_the_manifest_commit(archive, monkeypatch):
    _, manifest, _ = archive
    live = {city: supabase_store.rating_config_fingerprint(city) for city in _CITIES}

    # The git-shown files equal the working tree: the fingerprints equal the live ones.
    calls = []

    def working_tree(commit, path):
        calls.append((commit, path))
        return _working_tree_git_show(commit, path, _REPO_ROOT)

    assert loader.phase3_config_fingerprints(manifest, git_show=working_tree) == live
    assert calls == [(_HEAD, path) for path in supabase_store.RATING_CONFIG_SOURCE_FILES]

    # One conductor value differs in the commit's config.py: all four differ from the live ones.
    def edited(commit, path):
        text = working_tree(commit, path)
        if path == "backend/config.py":
            assert '"max_temp_c": 75.0,' in text
            text = text.replace('"max_temp_c": 75.0,', '"max_temp_c": 100.0,')
        return text

    changed = loader.phase3_config_fingerprints(manifest, git_show=edited)
    assert set(changed) == set(_CITIES)
    assert all(changed[city] != live[city] for city in _CITIES)
    assert len(set(changed.values())) == len(_CITIES)

    # The child refuses to answer when config was not imported from the materialized copy.
    original = loader._FINGERPRINT_CHILD
    swapped = original.replace("[tmpdir, backend_dir]", "[backend_dir, tmpdir]")
    assert swapped != original
    monkeypatch.setattr(loader, "_FINGERPRINT_CHILD", swapped)
    with pytest.raises(ValueError, match="materialized copy"):
        loader.phase3_config_fingerprints(manifest, git_show=working_tree)
    monkeypatch.setattr(loader, "_FINGERPRINT_CHILD", original)

    # A git failure names the commit and the path, nothing else.
    with pytest.raises(ValueError, match=r"backend/config\.py at commit 0{40}"):
        loader._git_show("0" * 40, "backend/config.py", _REPO_ROOT)

    # The real runner on this repository's own HEAD returns four 64-hex values.
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()
    real = loader.phase3_config_fingerprints(dict(manifest, git={"head": head, "backend_dirty": False}))
    assert set(real) == set(_CITIES)
    assert all(len(value) == 64 and set(value) <= set("0123456789abcdef") for value in real.values())


def test_same_hour_duplicates_keep_the_first_row_and_are_counted(tmp_path, archive):
    _, manifest, _ = archive
    rows = _archive_rows()
    # A second AUSTIN row for 01:00 with other values, further down the file.
    extra = dict(rows[1], dlr_amps=2222.0, air_temp=41.0)
    csv_path = _write_archive(tmp_path, rows + [extra], "dup.csv")
    prepared, stats = loader.prepare_rows(csv_path, manifest, _live_identity())

    austin_01 = [r for r in prepared if r["city"] == "AUSTIN" and r["valid_time"].hour == 1]
    assert len(austin_01) == 1
    assert austin_01[0]["rating_amps"] == rows[1]["dlr_amps"] and austin_01[0]["air_temp_c"] == rows[1]["air_temp"]
    assert stats["duplicates_dropped"]["AUSTIN"] == 1
    assert sum(stats["duplicates_dropped"].values()) == 1
    assert stats["csv_rows"]["AUSTIN"] == _HOURS
    assert stats["rows_read"] == len(rows) + 1 and stats["rows_dropped_by_validation"] == 0

    # Rows the archive's own row check rejects are counted, not hidden.
    bad = dict(rows[2], air_temp=999.0)
    csv_bad = _write_archive(tmp_path, [bad] + [r for i, r in enumerate(rows) if i != 2], "invalid.csv")
    prepared, stats = loader.prepare_rows(csv_bad, manifest, _live_identity())
    assert stats["rows_dropped_by_validation"] == 1
    assert stats["csv_rows"]["AUSTIN"] == _HOURS - 1


def test_off_hour_or_out_of_window_rows_stop_the_load(tmp_path, archive, monkeypatch, capsys, fast_fingerprints):
    _, manifest, _ = archive
    rows = _archive_rows()
    cases = {
        "off_hour": dict(rows[0], datetime_utc="2026-09-08T10:30:00Z"),
        "after_window": dict(rows[0], datetime_utc="2026-09-09T00:00:00Z"),
        "before_window": dict(rows[0], datetime_utc="2026-09-07T23:00:00Z"),
    }
    for name, bad_row in cases.items():
        csv_path = _write_archive(tmp_path, rows + [bad_row], f"{name}.csv")
        with pytest.raises(ValueError, match=r"1 archive row"):
            loader.prepare_rows(csv_path, manifest, _live_identity())

        # main stops before connecting, names the count, and exits 1.
        _no_connection(monkeypatch)
        broken = _manifest_for(csv_path, {city: _HOURS for city in _CITIES})
        manifest_path = _write_manifest(tmp_path, broken, f"{name}.json")
        assert loader.main(["--manifest", manifest_path]) == 1
        assert "1 archive row" in capsys.readouterr().out


def test_insert_is_do_nothing_with_bound_parameters_in_one_transaction(archive):
    csv_path, manifest, _ = archive
    rows, _ = loader.prepare_rows(csv_path, manifest, _live_identity())
    conn = _FakeConn()
    counts = loader.load(conn, rows)

    inserts = [entry for entry in conn.sent if entry[0] == "executemany"]
    assert len(inserts) == 1
    _, sql, params = inserts[0]
    assert sql == loader.INSERT_SQL
    assert "on conflict (city, valid_time) do nothing" in sql
    assert " ".join(sql.split()).startswith("insert into public.city_rating (")
    assert sql.count("%(") == len(loader.INSERT_COLUMNS)
    for value in ("AUSTIN", "backfill", "PROVISIONAL", "2026-09"):
        assert value not in sql  # values only in params
    assert params == rows

    # Every other statement is a count: the loader never updates or removes a row.
    others = [entry for entry in conn.sent if entry[0] != "executemany"]
    assert others and all(entry[1].lstrip().lower().startswith("select count(*)") for entry in others)
    assert conn.events == ["begin", "commit"]
    assert counts == {city: {"before": 0, "after": _HOURS} for city in _CITIES}

    # A second load sends the insert again and changes nothing.
    again = loader.load(conn, rows)
    assert again == {city: {"before": _HOURS, "after": _HOURS} for city in _CITIES}

    # A dry run counts and sends no insert.
    dry = _FakeConn()
    loader.load(dry, rows, dry_run=True)
    assert not [entry for entry in dry.sent if entry[0] == "executemany"]
    assert dry.keys == set()


def test_parity_report_is_deterministic_and_flags_any_mismatch(tmp_path, archive, monkeypatch, capsys, fast_fingerprints):
    csv_path, manifest, manifest_path = archive
    identity = _live_identity()
    rows, stats = loader.prepare_rows(csv_path, manifest, identity)
    sha = _sha256(csv_path)
    counts = {city: {"before": 0, "after": _HOURS} for city in _CITIES}

    report = loader.parity_report(manifest, sha, stats, counts, identity)
    again = loader.parity_report(manifest, sha, stats, counts, identity)
    dumped = json.dumps(report, indent=2, sort_keys=True)
    assert dumped == json.dumps(again, indent=2, sort_keys=True)
    assert report["schema"] == loader.REPORT_SCHEMA == "supabase_backfill_parity/1"
    assert report["all_match"] is True
    assert list(report["per_city"]) == list(_CITIES)
    for city in _CITIES:
        entry = report["per_city"][city]
        assert entry == {"manifest_rows": _HOURS, "csv_rows": _HOURS, "duplicates_dropped": 0,
                         "db_rows_at_csv_slots": _HOURS, "inserted": _HOURS, "skipped_existing": 0,
                         "match": True}
    identity_block = report["identity"]
    assert identity_block["config_commit"] == _HEAD
    assert identity_block["config_version"] == loader.PHASE3_CONFIG_VERSION
    assert identity_block["forecast_method"] == "ml"
    assert identity_block["per_city"]["MIDLAND"] == identity["MIDLAND"]
    assert report["archive"] == {"path": csv_path, "sha256": sha, "bytes": os.path.getsize(csv_path)}
    assert report["rows_read"] == len(rows) and report["rows_dropped_by_validation"] == 0

    # A dry run claims no match and no insert.
    dry = loader.parity_report(manifest, sha, stats, {c: {"before": 0, "after": 0} for c in _CITIES}, identity, dry_run=True)
    assert dry["all_match"] is None and dry["per_city"]["AUSTIN"]["inserted"] is None
    assert dry["per_city"]["AUSTIN"]["match"] is None

    # One row fewer in the database than in the CSV: that city and the whole report do not match.
    short = {city: dict(value) for city, value in counts.items()}
    short["EL_PASO"]["after"] = _HOURS - 1
    bad = loader.parity_report(manifest, sha, stats, short, identity)
    assert bad["per_city"]["EL_PASO"]["match"] is False
    assert bad["per_city"]["AUSTIN"]["match"] is True
    assert bad["all_match"] is False

    # A manifest that counts one more row than the CSV holds is a mismatch even when the database equals the CSV.
    manifest_more = dict(manifest, archive_rows_by_city=dict(manifest["archive_rows_by_city"], AUSTIN=_HOURS + 1))
    assert loader.parity_report(manifest_more, sha, stats, counts, identity)["per_city"]["AUSTIN"]["match"] is False

    # main: any mismatch exits 1 and is printed; the report file is written either way.
    conn = _FakeConn()
    monkeypatch.setattr(supabase_store, "connect", lambda url=None: conn)
    more_path = _write_manifest(tmp_path, manifest_more, "more.json")
    report_path = tmp_path / "out" / "report.json"
    assert loader.main(["--manifest", more_path, "--report", str(report_path)]) == 1
    printed = capsys.readouterr().out
    assert "AUSTIN" in printed and "MISMATCH" in printed.upper()
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["all_match"] is False and written["per_city"]["AUSTIN"]["match"] is False
    assert conn.closed is True
    assert "go/no-go" not in printed.lower() and "passed" not in printed.lower()  # no go/no-go claim (DB-06)

    # The matching manifest on a fresh fake database loads and exits 0; the report bytes are stable.
    for attempt in ("a", "b"):
        fresh = _FakeConn()
        monkeypatch.setattr(supabase_store, "connect", lambda url=None, fresh=fresh: fresh)
        path = tmp_path / f"report_{attempt}.json"
        assert loader.main(["--manifest", manifest_path, "--report", str(path)]) == 0
    assert (tmp_path / "report_a.json").read_bytes() == (tmp_path / "report_b.json").read_bytes()
    capsys.readouterr()


# ──────────────────────────────────────────────────────────────────────────────
# Live tests (throwaway local Postgres, as dlr_writer)
# ──────────────────────────────────────────────────────────────────────────────

def _load_live(admin_url, manifest_path, report_path, monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", _writer_url(admin_url))
    code = loader.main(["--manifest", manifest_path, "--report", str(report_path)])
    return code, json.loads(report_path.read_text(encoding="utf-8"))


def test_loading_twice_inserts_nothing_the_second_time(tmp_path, archive, _pg_admin_url, monkeypatch, working_tree_sources):
    _, _, manifest_path = archive
    _reset(_pg_admin_url)
    code, first = _load_live(_pg_admin_url, manifest_path, tmp_path / "first.json", monkeypatch)
    assert code == 0 and first["all_match"] is True
    assert all(entry["inserted"] == _HOURS for entry in first["per_city"].values())
    total = _admin_rows(_pg_admin_url, "select count(*) as n from public.city_rating")[0]["n"]
    assert total == len(_CITIES) * _HOURS

    code, second = _load_live(_pg_admin_url, manifest_path, tmp_path / "second.json", monkeypatch)
    assert code == 0 and second["all_match"] is True
    for city in _CITIES:
        entry = second["per_city"][city]
        assert entry["inserted"] == 0 and entry["skipped_existing"] == _HOURS
        assert entry["db_rows_at_csv_slots"] == first["per_city"][city]["db_rows_at_csv_slots"] == _HOURS
    assert _admin_rows(_pg_admin_url, "select count(*) as n from public.city_rating")[0]["n"] == total


def test_backfill_never_overwrites_a_live_row(tmp_path, archive, _pg_admin_url, monkeypatch, working_tree_sources):
    _, _, manifest_path = archive
    _reset(_pg_admin_url)
    slot = datetime(2026, 9, 8, 1, 0, tzinfo=timezone.utc)
    live_result = {
        "city": "AUSTIN", "station_id": "T_AUSTIN", "candidates_probed": 1, "probe_trail": [],
        "rating": 1234.5, "status": "ok", "fallback": False, "alerts": [],
        "observation": {"temp": 21.0, "wind": 2.0, "solar": 100.0, "wind_direction": 10.0, "wind_raw": 2.0},
        "exhausted": False,
        "pipeline": {"history_rows": 1, "usable_history_rows": 1, "forecast_method": "naive",
                     "forecast_used_by_g6": False, "forecast": None, "detector_signal": "cold_start",
                     "detector_model": None},
    }
    live_row = supabase_store.build_rating_row(
        live_result, slot, {"run_id": "live-test", "run_attempt": 1, "pipeline_version": "abcdef1"}
    )
    live_row["config_fingerprint"] = "f" * 64
    with supabase_store.connect(_writer_url(_pg_admin_url)) as writer:
        supabase_store.upsert_rating(writer, live_row)

    code, report = _load_live(_pg_admin_url, manifest_path, tmp_path / "report.json", monkeypatch)
    assert code == 0 and report["all_match"] is True
    austin = report["per_city"]["AUSTIN"]
    assert austin["inserted"] == _HOURS - 1 and austin["skipped_existing"] == 1
    assert austin["db_rows_at_csv_slots"] == austin["csv_rows"] == _HOURS

    kept = _admin_rows(_pg_admin_url, "select * from public.city_rating where city = 'AUSTIN' and valid_time = %s", (slot,))
    assert len(kept) == 1
    assert kept[0]["rating_amps"] == 1234.5 and kept[0]["origin"] == "live"
    assert kept[0]["run_id"] == "live-test" and kept[0]["config_fingerprint"] == "f" * 64
    assert kept[0]["air_temp_c"] == 21.0
    neighbours = _admin_rows(_pg_admin_url, "select origin from public.city_rating where city = 'AUSTIN' and valid_time <> %s", (slot,))
    assert [r["origin"] for r in neighbours] == ["backfill"] * (_HOURS - 1)


def test_db_counts_match_the_csv_per_city(tmp_path, archive, _pg_admin_url, monkeypatch, working_tree_sources):
    csv_path, manifest, manifest_path = archive
    _reset(_pg_admin_url)
    code, report = _load_live(_pg_admin_url, manifest_path, tmp_path / "report.json", monkeypatch)
    assert code == 0 and report["all_match"] is True
    for city in _CITIES:
        entry = report["per_city"][city]
        assert entry["db_rows_at_csv_slots"] == entry["csv_rows"] == entry["manifest_rows"] == _HOURS
        assert entry["match"] is True

    rows = _admin_rows(_pg_admin_url, "select * from public.city_rating order by city, valid_time")
    assert len(rows) == len(_CITIES) * _HOURS
    sha = _sha256(csv_path)
    for row in rows:
        city = row["city"]
        assert row["origin"] == "backfill"
        assert row["config_version"] == loader.PHASE3_CONFIG_VERSION
        assert row["rating_basis"].startswith("PROVISIONAL (OD-5)")
        assert row["config_fingerprint"] == supabase_store.rating_config_fingerprint(city)
        assert row["forecast_method"] == "ml" and row["forecast_status"] is None
        assert row["forecast_model_sha256"] == manifest["models"][f"forecast_{city}.joblib"]
        assert row["anomaly_model_sha256"] == manifest["models"][f"anomaly_{city}.joblib"]
        assert row["run_id"] == "backfill-" + sha[:12]
        assert row["wind_speed_ms"] is None and row["wind_direction_deg"] is None
        assert row["station_id"] is None and row["observation_time"] is None
        assert row["fallback_gates"] == [] and row["alerts"] == []
    assert report["identity"]["per_city"]["AUSTIN"]["config_fingerprint"] == supabase_store.rating_config_fingerprint("AUSTIN")
