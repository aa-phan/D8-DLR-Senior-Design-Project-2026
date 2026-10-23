"""
Tests for the backfill validation trace (`backfill_archive --trace-path`) and the
offline `real_data_validation` analysis that reads it back.

The tracer test runs the whole per-city stack offline (stub providers, no
network), writes a trace, and feeds it to the `completeness` subcommand. The
remaining tests harden the trace: error records, credential redaction, the
provenance record of the rated station, and a resumed run's duplicate records.

Every test writes under `tmp_path`, so no test touches the real backfill
archive, log or trace. Follows backend/tests/backfill_archive_test.py's
conventions (module-level imports, plain asserts, no test classes, stub
providers, no network).
"""

import json

import pandas as pd
import pytest
import requests

import anomaly_detector
import backfill_archive
import config
import observation_composer as oc
import real_data_validation

_CITY = "AUSTIN"
# A day far in the past: the composer then asks the grid/TCEQ providers for whole
# UTC days, which is why the stub providers below return fixed timestamps rather
# than ones derived from the `end` argument.
_DAY = "2025-06-01"


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


def _station_at(city):
    lat, lon = config.CITY_COORDINATES[city]
    return pd.DataFrame([{"stid": "T1", "name": "t", "lat": lat, "lon": lon}])


def _hourly(hours, **values):
    """One row per hour in `hours` on _DAY, with the given constant columns."""
    rows = [{"datetime_utc": pd.Timestamp(f"{_DAY}T{h:02d}:00:00Z"), **values} for h in hours]
    return pd.DataFrame(rows)


def _install_providers(monkeypatch):
    """
    Stub the four providers the composer calls through its module references.
    Values differ by provider so a field's source can be read off the value:
    synoptic for temperature, tceq for wind (with direction), nsrdb for solar,
    and an empty Open-Meteo.
    """
    def synoptic(stids, start, end, provider=None, fallback=None):
        return _hourly(range(8, 13), stid=stids[0], air_temp=30.0, wind_speed=5.0,
                       wind_direction=20.0, solar_radiation=520.0)

    def tceq(cams_id, start, end):
        return _hourly(range(8, 13), air_temp=31.0, wind_speed=6.0, wind_direction=10.0)

    def nsrdb(lat, lon, start, end):
        return _hourly(range(24), solar_radiation=500.0)

    def open_meteo(lat, lon, start, end):
        return pd.DataFrame()

    monkeypatch.setattr(oc.weather_provider, "fetch_weather", synoptic)
    monkeypatch.setattr(oc.tceq_provider, "fetch_tceq", tceq)
    monkeypatch.setattr(oc.nsrdb_provider, "fetch_nsrdb", nsrdb)
    monkeypatch.setattr(oc.open_meteo_provider, "fetch_open_meteo", open_meteo)


def _read_trace(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh.read().splitlines()]


def _run_backfill(tmp_path, **kwargs):
    lines = []
    totals = backfill_archive.backfill(
        f"{_DAY}T10:00:00Z", f"{_DAY}T11:00:00Z",
        archive_path=str(tmp_path / "archive.csv"), log_path=str(tmp_path / "log.csv"),
        cities=[_CITY], stations=_station_at(_CITY), out=lines.append, **kwargs)
    return totals, lines


# ──────────────────────────────────────────────────────────────────────────────
# Tracer: backfill trace -> completeness table, offline
# ──────────────────────────────────────────────────────────────────────────────

def test_backfill_trace_feeds_the_completeness_table_end_to_end(tmp_path, monkeypatch):
    _install_providers(monkeypatch)
    trace_path = tmp_path / "trace.jsonl"

    _run_backfill(tmp_path, trace_path=trace_path)

    assert backfill_archive.TRACE_SCHEMA == real_data_validation.TRACE_SCHEMA
    trace = _read_trace(trace_path)
    assert len(trace) == 2
    assert [r["schema"] for r in trace] == ["backfill_trace/1", "backfill_trace/1"]
    assert [r["city"] for r in trace] == [_CITY, _CITY]
    assert [r["run_end_utc"] for r in trace] == [f"{_DAY}T10:00:00Z", f"{_DAY}T11:00:00Z"]
    for record in trace:
        assert record["sources"] == {
            "air_temp": "synoptic", "wind_speed": "tceq", "solar_radiation": "nsrdb"}
        assert set(record["observation"]) == {"temp", "wind", "wind_raw", "wind_direction", "solar"}
        assert "history_rows" in record["pipeline"]

    out_csv = tmp_path / "completeness.csv"
    code = real_data_validation.main([
        "completeness", "--archive", str(tmp_path / "archive.csv"), "--trace", str(trace_path),
        "--log", str(tmp_path / "log.csv"), "--start", f"{_DAY}T10:00:00Z",
        "--end", f"{_DAY}T11:00:00Z", "--cities", _CITY, "--out", str(out_csv)])

    assert code == 0
    table = pd.read_csv(out_csv)
    assert len(table) == 1
    row = table.iloc[0]
    assert row["city"] == _CITY
    assert {k: int(row[k]) for k in (
        "expected_steps", "trace_records", "archive_rows", "log_rows",
        "exhausted", "errors", "no_trace", "missing")} == {
        "expected_steps": 2, "trace_records": 2, "archive_rows": 2, "log_rows": 2,
        "exhausted": 0, "errors": 0, "no_trace": 0, "missing": 0}


def test_backfill_without_trace_path_writes_no_trace_file(tmp_path, monkeypatch):
    _install_providers(monkeypatch)

    _run_backfill(tmp_path)

    assert sorted(p.name for p in tmp_path.iterdir()) == ["archive.csv", "log.csv"]


# ──────────────────────────────────────────────────────────────────────────────
# Trace hardening: error records, redaction, provenance, resumed steps
# ──────────────────────────────────────────────────────────────────────────────

class _StubFetcher:
    """What `backfill` needs of a composed fetcher: `.provenance` and `.errors`."""

    def __init__(self):
        self.provenance = []
        self.errors = {}

    def __call__(self, *args, **kwargs):  # pragma: no cover - never reached, the pipeline is stubbed
        raise AssertionError("the stub fetcher must not fetch")


def _fake_run(ts_text, station_id="T1", rating=1500.0):
    """A `run_dlr_pipeline` return value with one rated AUSTIN result."""
    result = {
        "city": _CITY, "station_id": station_id, "rating": rating, "status": "OK",
        "fallback": False, "exhausted": False, "archived": False, "alerts": [],
        "observation": {"temp": 30.0, "wind": 1.0, "wind_raw": 2.0, "wind_direction": 10.0,
                        "solar": 500.0},
        "pipeline": {"history_rows": 0, "usable_history_rows": 0, "future_key": 7},
    }
    row = {"city": _CITY, "rating_a": rating, "static_rating_a": 1500.0, "fallback": False,
           "exhausted": False, "archived": False, "fallback_gates": []}
    return {"start": ts_text, "end": ts_text, "provider": "composed", "forecast_method": "naive",
            "results": [result], "summary": [row], "errors": {}}


def _backfill_one_step(tmp_path, trace_path, fetcher, step="10"):
    return backfill_archive.backfill(
        f"{_DAY}T{step}:00:00Z", f"{_DAY}T{step}:00:00Z",
        archive_path=str(tmp_path / "archive.csv"), log_path=str(tmp_path / "log.csv"),
        cities=[_CITY], stations=_station_at(_CITY), fetcher=fetcher, out=lambda *_: None,
        trace_path=trace_path)


def test_trace_records_errors_with_credentials_redacted(tmp_path, monkeypatch):
    message = ("GET https://api.example.org/v1?token=abc123&email=me@x.org failed "
               + "x" * 400)

    def failing_run(**kwargs):
        return {"start": kwargs["end"], "end": kwargs["end"], "provider": "composed",
                "forecast_method": "naive", "results": [], "summary": [],
                "errors": {_CITY: message}}

    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", failing_run)
    trace_path = tmp_path / "trace.jsonl"

    _backfill_one_step(tmp_path, trace_path, _StubFetcher())

    (record,) = _read_trace(trace_path)
    assert record["city"] == _CITY
    assert record["run_end_utc"] == f"{_DAY}T10:00:00Z"
    assert "token=REDACTED" in record["error"] and "email=REDACTED" in record["error"]
    assert "abc123" not in record["error"] and "me@x.org" not in record["error"]
    assert len(record["error"]) <= 200
    for key in ("station_id", "rating_a", "static_rating_a", "status", "fallback", "exhausted",
                "archived", "fallback_gates", "alerts", "observation", "observation_hour",
                "sources", "pipeline"):
        assert record[key] is None
    assert backfill_archive._redact(
        "GET https://x/?token=abc123&email=me@x.org failed"
    ) == "GET https://x/?token=REDACTED&email=REDACTED failed"


def test_trace_file_is_closed_when_the_log_cannot_be_opened(tmp_path, monkeypatch):
    opened = []
    real_open = open

    log_path = tmp_path / "log.csv"

    def tracking_open(path, *args, **kwargs):
        if str(path) == str(log_path) and "a" in args[:1]:
            raise PermissionError("log is not writable")  # after the trace is already open
        fh = real_open(path, *args, **kwargs)
        opened.append(fh)
        return fh

    monkeypatch.setattr(backfill_archive, "open", tracking_open, raising=False)
    trace_path = tmp_path / "trace.jsonl"

    with pytest.raises(PermissionError):
        backfill_archive.backfill(
            f"{_DAY}T10:00:00Z", f"{_DAY}T10:00:00Z",
            archive_path=str(tmp_path / "archive.csv"), log_path=str(log_path),
            cities=[_CITY], stations=_station_at(_CITY), fetcher=_StubFetcher(),
            out=lambda *_: None, trace_path=trace_path)

    assert opened and all(fh.closed for fh in opened)


def test_trace_records_refuses_results_and_summary_of_different_lengths():
    run = {"results": [{"city": _CITY}], "summary": [], "errors": {}}

    with pytest.raises(ValueError, match="1 results but 0 summary rows"):
        backfill_archive._trace_records(run, f"{_DAY}T10:00:00Z", "naive", [])


def test_error_text_is_redacted_in_the_backfill_log_too(tmp_path, monkeypatch):
    message = "GET https://api.example.org/v1?token=abc123&email=me@x.org failed"

    def failing_run(**kwargs):
        return {"start": kwargs["end"], "end": kwargs["end"], "provider": "composed",
                "forecast_method": "naive", "results": [], "summary": [],
                "errors": {_CITY: message}}

    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", failing_run)

    _backfill_one_step(tmp_path, tmp_path / "trace.jsonl", _StubFetcher())

    log_text = (tmp_path / "log.csv").read_text(encoding="utf-8")
    assert "abc123" not in log_text and "me@x.org" not in log_text
    assert "token=REDACTED" in log_text


def test_multi_line_error_stays_one_log_row_that_completeness_can_read(tmp_path, monkeypatch):
    message = "boom\nline two; with comma\r\nline three, token=abc123\n"

    def failing_run(**kwargs):
        return {"start": kwargs["end"], "end": kwargs["end"], "provider": "composed",
                "forecast_method": "naive", "results": [], "summary": [],
                "errors": {_CITY: message}}

    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", failing_run)

    _backfill_one_step(tmp_path, tmp_path / "trace.jsonl", _StubFetcher())

    log_path = tmp_path / "log.csv"
    assert len(log_path.read_text(encoding="utf-8").splitlines()) == 2  # header + one row
    log = real_data_validation._read_log(log_path)
    (row,) = log.to_dict("records")
    assert row["city"] == _CITY
    assert row["error"].startswith("boom line two; with comma line three;")
    assert "abc123" not in row["error"]


@pytest.mark.parametrize("message", [
    '"boom',                         # a leading quote with no partner
    '"',
    '"x" ' * 100,                    # the 120-character cut slices a quoted run
    'say "hi", then "bye',
    "'single 'quoted",
    "nul\x00byte and \x1f separator   line sep",
    ",,,\"\",\"",
    "",
])
def test_any_error_text_leaves_a_log_row_that_read_log_can_parse(tmp_path, monkeypatch, message):
    def failing_run(**kwargs):
        return {"start": kwargs["end"], "end": kwargs["end"], "provider": "composed",
                "forecast_method": "naive", "results": [], "summary": [],
                "errors": {_CITY: message}}

    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", failing_run)

    _backfill_one_step(tmp_path, tmp_path / "trace.jsonl", _StubFetcher())

    log = real_data_validation._read_log(tmp_path / "log.csv")
    (row,) = log.to_dict("records")
    assert row["city"] == _CITY
    printable = "".join(ch if ch.isprintable() else " " for ch in message)
    expected = " ".join(printable.split()).replace(",", ";")[:120]
    got = row["error"] if isinstance(row["error"], str) else ""
    assert got == expected


def test_alert_text_is_redacted_before_it_reaches_the_trace(tmp_path, monkeypatch):
    run = _fake_run(f"{_DAY}T10:00:00Z")
    run["results"][0]["alerts"] = ["G1 FAIL (provider said api_key=SECRET42) - fallback"]
    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", lambda **kwargs: run)
    trace_path = tmp_path / "trace.jsonl"

    _backfill_one_step(tmp_path, trace_path, _StubFetcher())

    (record,) = _read_trace(trace_path)
    assert record["alerts"] == ["G1 FAIL (provider said api_key=REDACTED) - fallback"]


def test_trace_is_written_before_the_log_row_so_an_interrupt_cannot_lose_it(tmp_path, monkeypatch):
    run = _fake_run(f"{_DAY}T10:00:00Z")
    run["summary"][0]["rating_a"] = None  # the log row's `:.1f` format fails after the trace write
    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", lambda **kwargs: run)
    trace_path = tmp_path / "trace.jsonl"

    with pytest.raises(TypeError):
        _backfill_one_step(tmp_path, trace_path, _StubFetcher())

    (record,) = _read_trace(trace_path)
    assert record["city"] == _CITY


@pytest.mark.parametrize("text, secret", [
    ("params={'token': 'abc123', 'a':1}", "abc123"),        # dict / repr form
    ('url?token="abc123"', "abc123"),                       # quoted value
    ('{"api_key": "abc123"}', "abc123"),                    # JSON form
    ("Authorization: Bearer abc123", "abc123"),             # header form
    ("X-Api-Key: abc123", "abc123"),
    ("token%3Dabc123", "abc123"),                           # percent-encoded =
    ("url?api_key=abc,123&x", "123"),                       # comma inside the value
    ("url?token=a)bc", "bc"),                               # bracket inside the value
    ("Bearer abc123", "abc123"),                            # bare bearer token
    ("Authorization: Basic dXNlcjpwYXNz", "dXNlcjpwYXNz"),  # other header schemes
    ("Authorization: Token abc123", "abc123"),
    ("Proxy-Authorization: Basic abc123", "abc123"),
    ('{"token": "ab\\"cd"}', 'cd"'),                        # tail after an escaped quote
    ("params={'token': 'ab\\'cd'}", "cd'"),
    ("url?pwd=abc123", "abc123"),                           # more credential names
    ("url?passwd=xyz789", "xyz789"),
    ("url?auth=abc123", "abc123"),
    ("url?credential=abc123", "abc123"),
    ("url?key=abc123&x=1", "abc123"),                       # bare `key` in query form
    ("key=abc123", "abc123"),
    ('{"key": "abc123"}', "abc123"),                        # bare `key` as a quoted name
    ("secret_key: abc123", "abc123"),                       # compound names, any separator
    ("access-key=abc123", "abc123"),
    ("accessKey=AKIA123", "AKIA123"),                       # camelCase / concatenated key names
    ("SecretKey: abc123", "abc123"),
    ("privatekey=abc123", "abc123"),
    ("accesskey=abcdefg", "abcdefg"),
    ('{"signingKey": "abc123"}', "abc123"),
    ("subscriptionKey=abc123&x=1", "abc123"),
    ('key: "abcdefghij0123456789"', "abcdefghij0123456789"),  # quoted value after a bare `key:`
    ("auth: abc123secret", "abc123secret"),                 # colon form of auth / sig
    ("sig: abcdef0123456789abcdef", "abcdef0123456789abcdef"),
    ('{"body": "{\\"token\\": \\"abc123\\"}"}', "abc123"),  # JSON nested in a JSON string
    ('{\\"api_key\\": \\"abc123\\", \\"x\\": 1}', "abc123"),
    ('token=\\"abc123\\"', "abc123"),                       # escaped-quote value
    ('token="abc123', "abc123"),                            # unterminated quote (cut message)
    ("token='abc123", "abc123"),
    ('token="abc123\\', "abc123"),                          # ... ending in a lone backslash
    ("api_key          =    abc123", "abc123"),             # wide spacing around the separator
    ("key: AIzaSyA1b2C3d4E5f6G7h8I9j0", "AIzaSyA1b2C3d4E5f6G7h8I9j0"),  # credential-looking value
])
def test_redact_masks_every_credential_shape(text, secret):
    assert secret not in backfill_archive._redact(text)
    assert "REDACTED" in backfill_archive._redact(text)


@pytest.mark.parametrize("text", [
    "missing key: temp",                                    # diagnostic prose is evidence,
    "no data for key: wind_speed in window",                # not a credential: pin that
    "Max key: 5 reached",
    "hotkey: F5 failed",
    "auth: failed",
    "author: bob",
    "monkey: see; turkey=dinner; hotkey F5 failed",         # `key` only as a credential suffix
    "keyboard=us",
    "missing key: 'temp'",                                  # quotes alone do not make a secret
    "auth: 401",
    "sig: ok",
])
def test_redact_leaves_diagnostic_text_that_only_mentions_a_key(text):
    assert backfill_archive._redact(text) == text


def test_redact_keeps_the_text_around_a_secret_and_leaves_plain_text_alone():
    assert backfill_archive._redact("url?api_key=abc,123&x") == "url?api_key=REDACTED&x"
    assert backfill_archive._redact("KeyError: 'missing'") == "KeyError: 'missing'"


def test_redact_removes_configured_secret_values_in_any_shape(monkeypatch):
    monkeypatch.setenv("SYNOPTIC_TOKEN", "s3cr&t tok")
    monkeypatch.setenv("NREL_API_EMAIL", "me@example.org")
    monkeypatch.setenv("NREL_API_KEY", "abc")  # shorter than the minimum: ignored
    text = "raw s3cr&t tok, encoded s3cr%26t%20tok, plus s3cr%26t+tok, mail me%40example.org"
    redacted = backfill_archive._redact(text)
    assert "s3cr" not in redacted and "example" not in redacted
    assert backfill_archive._redact("abc stays") == "abc stays"


def test_resumed_run_starts_on_a_fresh_line_after_a_torn_trace_line(tmp_path, monkeypatch):
    trace_path = tmp_path / "trace.jsonl"
    trace_path.write_text('{"schema": "backfill_trace/1", "city": "AUS', encoding="utf-8")  # torn
    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline",
                        lambda **kwargs: _fake_run(kwargs["end"]))

    _backfill_one_step(tmp_path, trace_path, _StubFetcher())

    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and lines[0].endswith('"AUS')
    assert json.loads(lines[1])["city"] == _CITY  # the new record is intact, not glued on
    frame = real_data_validation.load_trace(trace_path)
    assert len(frame) == 1 and frame.attrs["unparseable"] == 1


def test_resumed_run_starts_on_a_fresh_line_after_a_torn_log_row(tmp_path, monkeypatch):
    log_path = tmp_path / "log.csv"
    log_path.write_text(backfill_archive._LOG_HEADER + "\n2025-06-01T09:00:00Z,AUSTIN,15",
                        encoding="utf-8")  # killed mid-row, no trailing newline
    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline",
                        lambda **kwargs: _fake_run(kwargs["end"]))

    _backfill_one_step(tmp_path, tmp_path / "trace.jsonl", _StubFetcher())

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3 and lines[1].endswith(",AUSTIN,15")
    assert lines[2].startswith(f"{_DAY}T10:00:00Z,{_CITY},1500.0,")  # not glued onto the fragment


def test_trace_takes_the_last_provenance_record_of_the_rated_station(tmp_path, monkeypatch):
    fetcher = _StubFetcher()
    earlier = {"stid": "OTHER", "hour": f"{_DAY}T09:00:00Z", "air_temp": "synoptic",
               "wind_speed": "synoptic", "solar_radiation": "synoptic"}
    fetcher.provenance.append(earlier)  # before the step: must never be sliced in

    def run_with_provenance(**kwargs):
        fetcher.provenance.append({"stid": "T1", "hour": f"{_DAY}T08:00:00Z", "air_temp": "synoptic",
                                   "wind_speed": "synoptic", "solar_radiation": "synoptic"})
        fetcher.provenance.append({"stid": "T1", "hour": f"{_DAY}T10:00:00Z", "air_temp": "tceq",
                                   "wind_speed": "tceq", "solar_radiation": "nsrdb"})
        fetcher.provenance.append({"stid": "OTHER", "hour": f"{_DAY}T10:00:00Z",
                                   "air_temp": "open_meteo", "wind_speed": "open_meteo",
                                   "solar_radiation": "open_meteo"})
        return _fake_run(kwargs["end"])

    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", run_with_provenance)
    trace_path = tmp_path / "trace.jsonl"
    _backfill_one_step(tmp_path, trace_path, fetcher)

    (record,) = _read_trace(trace_path)
    assert record["observation_hour"] == f"{_DAY}T10:00:00Z"
    assert record["sources"] == {"air_temp": "tceq", "wind_speed": "tceq", "solar_radiation": "nsrdb"}
    assert record["pipeline"]["future_key"] == 7  # the whole pipeline dict flows through

    # No provenance record for the rated station: both fields are None.
    unmatched = tmp_path / "unmatched.jsonl"
    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline",
                        lambda **kwargs: _fake_run(kwargs["end"], station_id="NOPE"))
    _backfill_one_step(tmp_path, unmatched, _StubFetcher(), step="11")
    (record,) = _read_trace(unmatched)
    assert record["observation_hour"] is None and record["sources"] is None


def test_resumed_step_keeps_the_last_trace_record(tmp_path, monkeypatch):
    _install_providers(monkeypatch)
    real_run = backfill_archive.run_dlr_pipeline
    state = {"fail": True}

    def flaky_run(**kwargs):
        if state["fail"]:
            return {"start": kwargs["end"], "end": kwargs["end"], "provider": "composed",
                    "forecast_method": "naive", "results": [], "summary": [],
                    "errors": {_CITY: "boom"}}
        return real_run(**kwargs)

    monkeypatch.setattr(backfill_archive, "run_dlr_pipeline", flaky_run)
    trace_path = tmp_path / "trace.jsonl"

    _run_backfill(tmp_path, trace_path=trace_path)  # both steps error
    state["fail"] = False
    _run_backfill(tmp_path, trace_path=trace_path)  # resume: the same steps are re-rated

    assert len(_read_trace(trace_path)) == 4
    trace = real_data_validation.load_trace(trace_path)
    assert len(trace) == 2
    assert trace.attrs == {"duplicates": 2, "records": 4, "unparseable": 0}
    assert trace["error"].isna().all()
    assert (trace["rating_a"] > 0).all()
    assert list(trace["run_end_utc"]) == [pd.Timestamp(f"{_DAY}T10:00:00Z"),
                                          pd.Timestamp(f"{_DAY}T11:00:00Z")]
    for column in ("obs_temp", "obs_wind", "temp_source", "usable_history_rows", "history_rows"):
        assert column in trace.columns
