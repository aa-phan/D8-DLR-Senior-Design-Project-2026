"""
The PSS/E job's rating input (pss-e-integration Phase 1, plan 01-02: IN-01, D-02, D-06).

Offline: the only network is a loopback fake PostgREST server (psse_fakes.py). Covers the
per-city choice between the newest city_rating row and the static rating, failed reads,
the amps-to-MVA helper and secret redaction.

Follows backend/tests/supabase_schema_doc_test.py's conventions (module-level imports,
plain asserts, no test classes). Every planted key, JWT, reference and database URL is
assembled from pieces so backend/tests/secret_scan_test.py never matches this file.
"""

import ast
import base64
import datetime
import functools
import json
import math
import os
import re
import socket
import sys
import urllib.parse

import pytest

_HERE = os.path.dirname(__file__)
_BACKEND = os.path.abspath(os.path.join(_HERE, ".."))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from psse_fakes import FakeLatestRatingServer, fake_publishable_key, latest_rows  # noqa: E402
from psse_job import constants, redaction, units  # noqa: E402
from psse_job.ratings import (  # noqa: E402
    ReadFailed,
    choose,
    fetch_latest_rating,
    parse_ts,
    ratings_used,
    select_ratings,
)

NOW = datetime.datetime(2026, 10, 28, 12, 20, 0, tzinfo=datetime.timezone.utc)
_STORE_PATH = os.path.join(_BACKEND, "supabase_store.py")


def _env(server, key=None):
    return {
        constants.ENV_SUPABASE_URL: server.url,
        constants.ENV_PUBLISHABLE_KEY: key or fake_publishable_key(),
    }


def _stamp(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"


def _austin(provisional=False, age_minutes=10.0, **overrides):
    return latest_rows(NOW, provisional=provisional, age_minutes=age_minutes, cities=["AUSTIN"], **overrides)[0]


def test_tracer_today_labels_select_static_for_all_four_cities():
    key = fake_publishable_key()
    with FakeLatestRatingServer(rows=latest_rows(NOW, provisional=True, age_minutes=10.0), key=key) as server:
        env = _env(server, key)
        selection = select_ratings(functools.partial(fetch_latest_rating, env=env), NOW)
        requests = list(server.requests)

    assert list(selection.choices) == ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]
    assert selection.read_error is None
    assert selection.ignored_rows == 0
    for city, choice in selection.choices.items():
        static = constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]
        count = constants.SUBCONDUCTORS_PER_PHASE[city]
        assert choice.city == city
        assert choice.source == "static_fallback"
        assert choice.fallback_reason == "provisional"
        assert choice.amps_per_conductor == static
        assert choice.subconductors_per_phase == count
        assert choice.amps_circuit == static * count
        assert choice.row_valid_time is not None
        assert choice.row_computed_at is not None
    assert selection.choices["AUSTIN"].amps_per_conductor == 1825.0
    assert selection.choices["CORPUS_CHRISTI"].amps_per_conductor == 1500.0
    assert selection.choices["MIDLAND"].amps_per_conductor == 1875.0
    assert selection.choices["EL_PASO"].amps_per_conductor == 1320.0

    assert len(requests) == 1
    request = requests[0]
    query = dict(request["query"])
    assert query["select"] == ",".join(constants.LATEST_RATING_SELECT)
    assert query["order"] == "city.asc"
    assert request["headers"]["apikey"] == key
    assert "authorization" not in request["headers"]


# ──────────────────────────────────────────────────────────────────────────────
# choose(): the IN-01 decision matrix
# ──────────────────────────────────────────────────────────────────────────────

def _pop(*names):
    def mutate(row):
        for name in names:
            row.pop(name)
        return row
    return mutate


def _set(**values):
    def mutate(row):
        row.update(values)
        return row
    return mutate


def _at(minutes, seconds=0, **extra):
    """Row whose valid_time is `minutes` (+ `seconds`) before NOW; negative minutes are in the future."""
    valid = NOW - datetime.timedelta(minutes=minutes, seconds=seconds)
    return _set(
        valid_time=_stamp(valid),
        computed_at=_stamp(valid + datetime.timedelta(minutes=6)),
        **extra
    )


# id, row mutation (None: no row), expected (source, reason, uses_row_amps)
_STATIC = "static_fallback"
_ROW = "city_rating"
_MATRIX = [
    ("missing_row", None, (_STATIC, "missing", False)),
    ("invalid_null_rating", _set(rating_amps=None), (_STATIC, "invalid", False)),
    ("invalid_string_rating", _set(rating_amps="2000.0"), (_STATIC, "invalid", False)),
    ("invalid_bool_rating", _set(rating_amps=True), (_STATIC, "invalid", False)),
    ("invalid_nan_rating", _set(rating_amps=float("nan")), (_STATIC, "invalid", False)),
    ("invalid_inf_rating", _set(rating_amps=float("inf")), (_STATIC, "invalid", False)),
    ("invalid_zero_rating", _set(rating_amps=0), (_STATIC, "invalid", False)),
    ("invalid_negative_rating", _set(rating_amps=-5.0), (_STATIC, "invalid", False)),
    ("invalid_naive_valid_time", _set(valid_time="2026-10-28T12:10:00"), (_STATIC, "invalid", False)),
    ("invalid_unparseable_valid_time", _set(valid_time="yesterday"), (_STATIC, "invalid", False)),
    ("invalid_missing_computed_at", _pop("computed_at"), (_STATIC, "invalid", False)),
    ("invalid_string_flag", _set(is_stale="false"), (_STATIC, "invalid", False)),
    ("invalid_missing_flag", _pop("is_provisional"), (_STATIC, "invalid", False)),
    ("invalid_city_mismatch", _set(city="MIDLAND"), (_STATIC, "invalid", False)),
    ("invalid_future_valid_time", _at(-6), (_STATIC, "invalid", False)),
    ("future_within_tolerance", _at(-4), (_ROW, None, True)),
    ("fresh_at_exactly_90", _at(90), (_ROW, None, True)),
    ("stale_at_90_plus_1s", _at(90, 1), (_STATIC, "stale", False)),
    ("stale_by_server_flag", _set(is_stale=True), (_STATIC, "stale", False)),
    ("stale_and_provisional_reports_stale", _at(100, is_stale=True, is_provisional=True), (_STATIC, "stale", False)),
    ("provisional_fresh", _set(is_provisional=True), (_STATIC, "provisional", False)),
    ("fresh_ok_uses_row_amps", _set(), (_ROW, None, True)),
    ("fresh_fallback_status_row_is_city_rating", _set(status="fallback", fallback=True), (_ROW, None, True)),
]


@pytest.mark.parametrize("mutate,expected", [(m, e) for _, m, e in _MATRIX], ids=[i for i, _, _ in _MATRIX])
def test_choose_matrix(mutate, expected):
    source, reason, uses_row = expected
    row = None if mutate is None else mutate(_austin(provisional=False, age_minutes=10.0))
    choice = choose("AUSTIN", row, NOW)

    assert choice.city == "AUSTIN"
    assert choice.source == source
    assert choice.fallback_reason == reason
    static = constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR["AUSTIN"]
    if uses_row:
        assert choice.amps_per_conductor == row["rating_amps"]
        assert choice.amps_per_conductor != static
    else:
        assert choice.amps_per_conductor == static
    assert choice.static_amps_per_conductor == static
    assert choice.subconductors_per_phase == 2
    assert choice.amps_circuit == choice.amps_per_conductor * 2
    if reason in (None, "stale", "provisional"):
        assert choice.row_valid_time is not None and choice.row_computed_at is not None
        assert choice.row_valid_time.utcoffset() == datetime.timedelta(0)
    else:
        for name in ("row_valid_time", "row_computed_at", "row_run_id", "row_status",
                     "row_config_fingerprint", "age_minutes", "server_is_stale", "server_is_provisional"):
            assert getattr(choice, name) is None, name


def test_choose_exact_90_minutes_is_fresh_and_keeps_the_row_link():
    row = _at(90)(_austin(provisional=False, status="fallback"))
    choice = choose("AUSTIN", row, NOW)
    assert choice.source == "city_rating"
    assert choice.age_minutes == 90.0
    assert choice.row_status == "fallback"
    assert choice.row_run_id == "1234567890"
    assert choice.row_config_fingerprint == "ab" * 32


# ──────────────────────────────────────────────────────────────────────────────
# select_ratings()
# ──────────────────────────────────────────────────────────────────────────────

def test_select_empty_response_all_missing():
    selection = select_ratings(lambda: [], NOW)
    assert selection.read_error is None
    assert selection.ignored_rows == 0
    assert list(selection.choices) == list(constants.CITIES)
    for city, choice in selection.choices.items():
        assert (choice.source, choice.fallback_reason) == ("static_fallback", "missing")
        assert choice.amps_per_conductor == constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]


def test_select_read_failed_all_four_static():
    def failed_http():
        raise ReadFailed("latest_rating read failed: HTTP 503")

    selection = select_ratings(failed_http, NOW)
    assert selection.read_error == "latest_rating read failed: HTTP 503"
    assert list(selection.choices) == list(constants.CITIES)
    for city, choice in selection.choices.items():
        assert (choice.source, choice.fallback_reason) == ("static_fallback", "read_failed")
        assert choice.amps_per_conductor == constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]
        assert choice.row_valid_time is None

    planted = "hunter" + "2value"

    def failed_other():
        raise ValueError("bad thing key=" + planted)

    other = select_ratings(failed_other, NOW)
    assert other.read_error.startswith("ValueError: ")
    assert "key=REDACTED" in other.read_error
    assert planted not in other.read_error
    assert all(c.fallback_reason == "read_failed" for c in other.choices.values())

    not_a_list = select_ratings(lambda: {"city": "AUSTIN"}, NOW)
    assert not_a_list.read_error == "latest_rating read failed: response is not a JSON list"
    assert all(c.fallback_reason == "read_failed" for c in not_a_list.choices.values())


def test_select_order_is_fixed_whatever_the_response_order():
    rows = list(reversed(latest_rows(NOW, provisional=False)))
    selection = select_ratings(lambda: rows, NOW)
    assert list(selection.choices) == ["AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO"]
    for city, choice in selection.choices.items():
        assert choice.source == "city_rating"
        assert choice.amps_per_conductor == pytest.approx(constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city] * 1.1)


def test_select_duplicate_city_rows_make_that_city_invalid():
    rows = latest_rows(NOW, provisional=False)
    rows.append(dict(rows[0], rating_amps=1.0))
    selection = select_ratings(lambda: rows, NOW)
    assert (selection.choices["AUSTIN"].source, selection.choices["AUSTIN"].fallback_reason) == (
        "static_fallback", "invalid")
    assert selection.choices["AUSTIN"].amps_per_conductor == 1825.0
    assert selection.choices["AUSTIN"].row_valid_time is None
    for city in ("CORPUS_CHRISTI", "MIDLAND", "EL_PASO"):
        assert selection.choices[city].source == "city_rating"
    assert selection.ignored_rows == 0


def test_select_city_keys_are_exact():
    rows = latest_rows(NOW, provisional=False, cities=["CORPUS_CHRISTI", "MIDLAND", "EL_PASO"])
    rows.append(_austin(city="austin"))
    rows.append(_austin(city=" AUSTIN"))
    selection = select_ratings(lambda: rows, NOW)
    assert selection.ignored_rows == 2
    assert (selection.choices["AUSTIN"].source, selection.choices["AUSTIN"].fallback_reason) == (
        "static_fallback", "missing")


def test_select_ignores_rows_that_are_not_dicts_and_counts_them():
    rows = latest_rows(NOW, provisional=False) + [None, "AUSTIN", 7, {"city": 5}]
    selection = select_ratings(lambda: rows, NOW)
    assert selection.ignored_rows == 4
    assert all(c.source == "city_rating" for c in selection.choices.values())


def test_select_requires_aware_now():
    calls = []

    def fetch():
        calls.append(1)
        return []

    with pytest.raises(ValueError):
        select_ratings(fetch, datetime.datetime(2026, 10, 28, 12, 20, 0))
    with pytest.raises(ValueError):
        select_ratings(fetch, "2026-10-28T12:20:00Z")
    assert calls == []
    select_ratings(fetch, NOW)
    assert calls == [1]


def test_ratings_used_has_four_cities_and_fixed_keys():
    rows = latest_rows(NOW, provisional=True, cities=["AUSTIN", "MIDLAND", "EL_PASO"])
    selection = select_ratings(lambda: rows, NOW)
    used = ratings_used(selection)

    assert list(used) == list(constants.CITIES)
    for city in constants.CITIES:
        assert tuple(used[city]) == constants.RATINGS_USED_KEYS
    assert json.loads(json.dumps(used, allow_nan=False)) == used

    austin = used["AUSTIN"]
    assert austin["source"] == "static_fallback"
    assert austin["fallback_reason"] == "provisional"
    assert austin["rating_amps_per_conductor"] == 1825.0
    assert austin["subconductors_per_phase"] == 2
    assert austin["rating_amps_circuit"] == 3650.0
    assert austin["static_rating_amps_per_conductor"] == 1825.0
    assert austin["line_voltage_kv"] is None and austin["rating_mva"] is None
    assert austin["city_rating_valid_time"] == "2026-10-28T12:10:00+00:00"
    assert austin["city_rating_computed_at"] == "2026-10-28T12:16:00+00:00"
    assert austin["city_rating_run_id"] == "1234567890"
    assert austin["city_rating_status"] == "ok"
    assert austin["config_fingerprint"] == "ab" * 32
    assert austin["age_minutes"] == 10.0
    assert austin["server_is_stale"] is False and austin["server_is_provisional"] is True

    missing = used["CORPUS_CHRISTI"]
    assert missing["fallback_reason"] == "missing"
    for name in ("city_rating_valid_time", "city_rating_computed_at", "city_rating_run_id",
                 "city_rating_status", "config_fingerprint", "age_minutes", "server_is_stale",
                 "server_is_provisional"):
        assert missing[name] is None, name
    assert missing["rating_amps_per_conductor"] == 1500.0


# ──────────────────────────────────────────────────────────────────────────────
# parse_ts()
# ──────────────────────────────────────────────────────────────────────────────

def test_parse_ts_accepts_offsets_and_fractions():
    expected = datetime.datetime(2026, 10, 28, 12, 0, 0, tzinfo=datetime.timezone.utc)
    for text in ("2026-10-28T12:00:00Z", "2026-10-28T12:00:00+00:00", "2026-10-28T12:00:00+0000",
                 "2026-10-28T12:00:00+00", "2026-10-28 12:00:00Z", "2026-10-28 12:00:00+00:00"):
        assert parse_ts(text) == expected, text
    assert parse_ts("2026-10-28T07:00:00-05:00") == expected
    assert parse_ts("2026-10-28T07:00:00-0500") == expected
    assert parse_ts("2026-10-28T17:30:00+05:30") == expected
    assert parse_ts("2026-10-28T12:00:00Z").utcoffset() == datetime.timedelta(0)
    assert parse_ts("2026-10-28T07:00:00-05:00").utcoffset() == datetime.timedelta(0)
    for digits in range(1, 10):
        fraction = "123456789"[:digits]
        got = parse_ts("2026-10-28T12:00:00." + fraction + "Z")
        assert got.microsecond == int(fraction[:6].ljust(6, "0")), digits
    assert parse_ts("2026-10-28T12:00:00.5+00:00").microsecond == 500000


@pytest.mark.parametrize("value", [
    "2026-10-28T12:00:00", "2026-10-28", "garbage", "", "2026-13-01T00:00:00Z",
    "2026-10-28T12:00:00+0560", "2026-10-28T12:00:00+25:00", "2026-10-28T12:00:00.Z",
    "2026-10-28T12:00:00 UTC", None, 123, 1.5, True, b"2026-10-28T12:00:00Z",
])
def test_parse_ts_rejects_naive_and_garbage(value):
    with pytest.raises(ValueError):
        parse_ts(value)


# ──────────────────────────────────────────────────────────────────────────────
# fetch_latest_rating(): refusals, failures, and what an error may carry
# ──────────────────────────────────────────────────────────────────────────────

def _no_request_opener(request, timeout=None):
    raise AssertionError("a request was made")


def _service_role_jwt():
    def piece(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode("utf-8")).decode("ascii").rstrip("=")

    return ".".join([piece({"alg": "HS256", "typ": "JWT"}), piece({"role": "service_role", "iss": "x"}), "c2lnbmF0dXJl"])


def test_fetch_refuses_secret_key_before_any_request():
    secret_key = constants.SECRET_KEY_PREFIX + "abcdefghijklmnop12345678"
    with FakeLatestRatingServer(rows=[]) as server:
        env = {constants.ENV_SUPABASE_URL: server.url, constants.ENV_PUBLISHABLE_KEY: secret_key}
        with pytest.raises(ReadFailed) as caught:
            fetch_latest_rating(env=env)
        assert server.requests == []
    assert secret_key not in str(caught.value)
    assert "abcdefghijklmnop" not in str(caught.value)


def test_fetch_refuses_service_role_jwt_before_any_request():
    token = _service_role_jwt()
    with FakeLatestRatingServer(rows=[]) as server:
        env = {constants.ENV_SUPABASE_URL: server.url, constants.ENV_PUBLISHABLE_KEY: token}
        with pytest.raises(ReadFailed) as caught:
            fetch_latest_rating(env=env)
        assert server.requests == []
    assert token not in str(caught.value)
    assert token.split(".")[1] not in str(caught.value)


def test_fetch_accepts_an_anon_role_jwt():
    def piece(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode("utf-8")).decode("ascii").rstrip("=")

    token = ".".join([piece({"alg": "HS256"}), piece({"role": "anon"}), "c2ln"])
    with FakeLatestRatingServer(rows=[]) as server:
        env = {constants.ENV_SUPABASE_URL: server.url, constants.ENV_PUBLISHABLE_KEY: token}
        assert fetch_latest_rating(env=env) == []
        assert len(server.requests) == 1


def test_fetch_refuses_plain_http_to_a_remote_host():
    env = {constants.ENV_SUPABASE_URL: "http://example.invalid", constants.ENV_PUBLISHABLE_KEY: fake_publishable_key()}
    with pytest.raises(ReadFailed) as caught:
        fetch_latest_rating(env=env, opener=_no_request_opener)
    assert "example.invalid" not in str(caught.value)
    assert fake_publishable_key() not in str(caught.value)
    env[constants.ENV_SUPABASE_URL] = "ftp://example.invalid"
    with pytest.raises(ReadFailed):
        fetch_latest_rating(env=env, opener=_no_request_opener)
    env[constants.ENV_SUPABASE_URL] = "not a url"
    with pytest.raises(ReadFailed):
        fetch_latest_rating(env=env, opener=_no_request_opener)


def test_fetch_missing_env_names_the_variable_not_a_value():
    key = fake_publishable_key()
    with pytest.raises(ReadFailed) as caught:
        fetch_latest_rating(env={}, opener=_no_request_opener)
    assert constants.ENV_SUPABASE_URL in str(caught.value)

    with pytest.raises(ReadFailed) as caught:
        fetch_latest_rating(env={constants.ENV_SUPABASE_URL: "https://project.example.invalid"},
                            opener=_no_request_opener)
    assert constants.ENV_PUBLISHABLE_KEY in str(caught.value)
    assert "project.example.invalid" not in str(caught.value)

    with pytest.raises(ReadFailed) as caught:
        fetch_latest_rating(env={constants.ENV_SUPABASE_URL: "   ", constants.ENV_PUBLISHABLE_KEY: key},
                            opener=_no_request_opener)
    assert key not in str(caught.value)


@pytest.mark.parametrize("status", [500, 401, 404])
def test_fetch_http_error_status_is_read_failed(status):
    with FakeLatestRatingServer(rows=[], status=status, body=json.dumps({"message": "boom"})) as server:
        with pytest.raises(ReadFailed) as caught:
            fetch_latest_rating(env=_env(server))
    assert str(caught.value) == "latest_rating read failed: HTTP %d" % status


def test_fetch_wrong_key_is_http_401_read_failed():
    with FakeLatestRatingServer(rows=[], key="a-different-key-value") as server:
        with pytest.raises(ReadFailed) as caught:
            fetch_latest_rating(env=_env(server))
    assert str(caught.value) == "latest_rating read failed: HTTP 401"


def test_fetch_non_list_body_is_read_failed():
    expected = "latest_rating read failed: response is not a JSON list"
    for body in (json.dumps({"city": "AUSTIN"}), "not json at all", "", "null"):
        with FakeLatestRatingServer(body=body) as server:
            with pytest.raises(ReadFailed) as caught:
                fetch_latest_rating(env=_env(server))
        assert str(caught.value) == expected, body


def test_fetch_returns_the_decoded_rows_and_strips_a_trailing_slash():
    rows = latest_rows(NOW)
    with FakeLatestRatingServer(rows=rows) as server:
        env = {constants.ENV_SUPABASE_URL: " " + server.url + "/ ", constants.ENV_PUBLISHABLE_KEY: fake_publishable_key()}
        got = fetch_latest_rating(env=env)
        assert server.requests[0]["path"] == "/rest/v1/latest_rating"
    assert got == rows


def test_fetch_errors_never_carry_the_url_or_key():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    base = "http://127.0.0.1:%d" % port
    key = fake_publishable_key()
    with pytest.raises(ReadFailed) as caught:
        fetch_latest_rating(env={constants.ENV_SUPABASE_URL: base, constants.ENV_PUBLISHABLE_KEY: key}, timeout=10)
    message = str(caught.value)
    assert message.startswith("latest_rating read failed: ")
    assert base not in message and key not in message
    assert "127.0.0.1" not in message
    assert len(message) <= len("latest_rating read failed: ") + 80 + constants.LOG_MAX_CHARS
    assert caught.value.__cause__ is None and caught.value.__context__ is None

    # An opener that raises with the URL and key in its text is redacted the same way.
    def leaky(request, timeout=None):
        raise OSError("cannot reach " + base + "/rest/v1/latest_rating with " + key)

    with pytest.raises(ReadFailed) as caught:
        fetch_latest_rating(env={constants.ENV_SUPABASE_URL: base, constants.ENV_PUBLISHABLE_KEY: key}, opener=leaky)
    message = str(caught.value)
    assert message.startswith("latest_rating read failed: OSError: ")
    assert base not in message and key not in message and "127.0.0.1" not in message


# ──────────────────────────────────────────────────────────────────────────────
# Units (D-06): per-circuit MVA, no power factor, never the MW column
# ──────────────────────────────────────────────────────────────────────────────

def test_units_static_circuit_mva_matches_the_spec_table():
    expected = {"AUSTIN": 2181.1, "CORPUS_CHRISTI": 1792.7, "MIDLAND": 2240.8, "EL_PASO": 788.8}
    for city, mva in expected.items():
        got = units.circuit_mva(
            constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city],
            constants.SUBCONDUCTORS_PER_PHASE[city],
            constants.LINE_VOLTAGE_KV_DEFAULT,
        )
        assert round(got, 1) == mva, city


def test_units_no_power_factor_ratio():
    power_factor = 0.95
    for city in constants.CITIES:
        amps = constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]
        count = constants.SUBCONDUCTORS_PER_PHASE[city]
        mva = units.circuit_mva(amps, count, 345.0)
        per_conductor_mw = math.sqrt(3) * 345.0 * amps * power_factor / 1000.0
        assert mva / per_conductor_mw == pytest.approx(count / power_factor)
    austin = units.circuit_mva(1825.0, 2, 345.0)
    assert round(austin / (math.sqrt(3) * 345.0 * 1825.0 * power_factor / 1000.0), 3) == 2.105
    assert units.circuit_amps(1825.0, 2) == 3650.0


def test_units_round_trip():
    for city in constants.CITIES:
        amps = constants.STATIC_RATINGS_AMPS_PER_CONDUCTOR[city]
        count = constants.SUBCONDUCTORS_PER_PHASE[city]
        for kv in (115.0, 138.0, 345.0):
            mva = units.circuit_mva(amps, count, kv)
            assert units.mva_to_circuit_amps(mva, kv) == pytest.approx(amps * count)


@pytest.mark.parametrize("bad", [0, -1.0, float("nan"), float("inf"), True, "5", None, 10 ** 400])
def test_units_reject_bad_inputs(bad):
    with pytest.raises(ValueError):
        units.circuit_amps(bad, 2)
    with pytest.raises(ValueError):
        units.circuit_mva(bad, 2, 345.0)
    with pytest.raises(ValueError):
        units.circuit_mva(1825.0, 2, bad)
    with pytest.raises(ValueError):
        units.mva_to_circuit_amps(bad, 345.0)
    with pytest.raises(ValueError):
        units.mva_to_circuit_amps(100.0, bad)


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, "2", None])
def test_units_reject_bad_subconductor_counts(bad):
    with pytest.raises(ValueError):
        units.circuit_amps(1825.0, bad)
    with pytest.raises(ValueError):
        units.circuit_mva(1825.0, bad, 345.0)


class _NoMwRow(dict):
    """A row that fails the test if anything touches the rating_mw column."""

    def __getitem__(self, key):
        assert key != "rating_mw", "rating_mw was read"
        return dict.__getitem__(self, key)

    def get(self, key, default=None):
        assert key != "rating_mw", "rating_mw was read"
        return dict.get(self, key, default)

    def __contains__(self, key):
        assert key != "rating_mw", "rating_mw was probed"
        return dict.__contains__(self, key)


def test_units_choose_never_reads_the_mw_field():
    row = _NoMwRow(_austin(provisional=False, age_minutes=10.0, rating_mw=1.0, static_rating_mw=2.0))
    choice = choose("AUSTIN", row, NOW)
    assert choice.source == "city_rating"
    assert choice.amps_per_conductor == row["rating_amps"]


def test_units_select_list_has_no_mw_column():
    with FakeLatestRatingServer(rows=latest_rows(NOW)) as server:
        fetch_latest_rating(env=_env(server))
        select = dict(server.requests[0]["query"])["select"]
    assert "rating_mw" not in select
    assert "static_rating_mw" not in select
    assert select.split(",") == list(constants.LATEST_RATING_SELECT)


# ──────────────────────────────────────────────────────────────────────────────
# Redaction
# ──────────────────────────────────────────────────────────────────────────────

def _planted_environment():
    scheme = "postgres" + "ql://"
    reference = "abcdefghij" + "klmnopqrst"
    decoded_password = "p@ss/w0rd#" + "Zq9Lk2"
    encoded_password = urllib.parse.quote(decoded_password, safe="")
    db_host = "db-" + "test.example.invalid"
    db_url = scheme + "dlr_psse_writer." + reference + ":" + encoded_password + "@" + db_host + ":5432/postgres"
    api_host = reference + ".supabase.example.invalid"
    return {
        "db_url": db_url,
        "reference": reference,
        "decoded_password": decoded_password,
        "encoded_password": encoded_password,
        "db_host": db_host,
        "api_host": api_host,
        "api_url": "https://" + api_host,
        "key": fake_publishable_key(),
    }


def test_redact_removes_psse_env_secrets(monkeypatch):
    plant = _planted_environment()
    monkeypatch.setenv(constants.ENV_PSSE_DB_URL, plant["db_url"])
    monkeypatch.setenv(constants.ENV_SUPABASE_URL, plant["api_url"])
    monkeypatch.setenv(constants.ENV_PUBLISHABLE_KEY, plant["key"])
    text = " | ".join([
        "connect failed for " + plant["db_url"],
        "password " + plant["encoded_password"],
        "decoded " + plant["decoded_password"],
        "host " + plant["db_host"],
        "user dlr_psse_writer." + plant["reference"],
        "api " + plant["api_url"] + "/rest/v1/latest_rating",
        "api host " + plant["api_host"],
        "header apikey " + plant["key"],
    ])
    for source in (redaction.redact(text, limit=5000), redaction.redact(text, secrets=redaction.env_secrets(), limit=5000)):
        for name in ("db_url", "reference", "decoded_password", "encoded_password", "db_host", "api_host", "api_url", "key"):
            assert plant[name] not in source, name
    secrets = redaction.env_secrets()
    for name in ("db_url", "reference", "decoded_password", "encoded_password", "db_host", "api_host", "api_url", "key"):
        assert plant[name] in secrets, name


def test_redact_env_secrets_skips_unset_and_blank():
    assert redaction.env_secrets({}) == []
    assert redaction.env_secrets({constants.ENV_PUBLISHABLE_KEY: "   ", constants.ENV_SUPABASE_URL: ""}) == []
    assert redaction.connection_identifiers(None) == []
    assert redaction.connection_identifiers("not a url") == []
    short = "postgres" + "ql://ab:pw@h:5432/db"
    assert redaction.connection_identifiers(short) == []


def test_redact_patterns_and_cut_after_redaction():
    scheme = "postgres" + "ql://"
    sb_publishable = "sb_" + "publishable_" + "AbCdEf012345"
    sb_secret = "sb_" + "secret_" + "ZyXwVu987654"
    piece = lambda text: base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")  # noqa: E731
    token = ".".join([piece('{"alg":"HS256"}'), piece('{"role":"anon"}'), "c2lnbmF0dXJl"])
    assert token.startswith("eyJ")

    out = redaction.redact("a " + scheme + "user:pw@host:5432/db b", secrets=[])
    assert out == "a postgresql://REDACTED b"
    out = redaction.redact("password=hunter2 TOKEN=abc;key=zzz apikey=q&secret=s", secrets=[])
    assert out == "password=REDACTED TOKEN=REDACTED;key=REDACTED apikey=REDACTED&secret=REDACTED"
    out = redaction.redact("x " + sb_publishable + " y " + sb_secret + " z", secrets=[])
    assert out == "x sb_REDACTED y sb_REDACTED z"
    out = redaction.redact("bearer " + token + " end", secrets=[])
    assert out == "bearer JWT_REDACTED end"
    out = redaction.redact("connection to server at host (10.20.30.40), port 5432 or (2600:1f18::1) failed", secrets=[])
    assert out == "connection to server at host (REDACTED), port 5432 or (REDACTED) failed"
    assert redaction.redact(None, secrets=[]) == ""

    secret = "Zx9Qw7" + "Lk2Mn"
    text = "x" * 290 + secret + " tail"
    out = redaction.redact(text, secrets=[secret], limit=300)
    assert out == "x" * 290 + "REDACTED tail"[:10]
    assert secret[:5] not in out
    assert len(redaction.redact("y" * 5000, secrets=[], limit=1000)) == 1000


def _store_redact():
    """backend/supabase_store.py's own redact, compiled from its source without importing the module.

    The module imports pandas at the top, which the laptop does not have (and a bare test
    environment may not either); the rules under test are four top-level names and two
    functions, so those nodes are executed in an empty namespace.
    """
    with open(_STORE_PATH, encoding="utf-8") as handle:
        tree = ast.parse(handle.read(), _STORE_PATH)
    wanted_assigns = {"_URL_RE", "_KEY_VALUE_RE", "_ENV_URL_NAMES", "_MAX_MESSAGE_CHARS"}
    wanted_functions = {"_url_secrets", "redact"}
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id in wanted_assigns for t in node.targets):
            nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted_functions:
            nodes.append(node)
    assert len(nodes) == len(wanted_assigns) + len(wanted_functions)
    namespace = {"re": re, "os": os, "unquote": urllib.parse.unquote, "urlsplit": urllib.parse.urlsplit}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), _STORE_PATH, "exec"), namespace)
    return namespace["redact"]


def test_redact_parity_with_supabase_store():
    store_redact = _store_redact()
    scheme = "postgres" + "ql://"
    cases = [
        ("connect " + scheme + "user:pw@host:5432/db failed", [], 300),
        ("connect " + scheme.upper() + "user:pw@host:5432/db failed", [], 300),
        ("password=hunter2 and token=abc; key=zzz", [], 300),
        ("API_KEY=abc&Token=xyz,secret='q'", [], 300),
        ("the value Zx9Qw7Lk2 appears twice: Zx9Qw7Lk2", ["Zx9Qw7Lk2"], 300),
        ("abcdef abc abcdefgh", ["abc", "abcdef"], 300),
        ("x" * 100 + " password=hunter2", [], 50),
        ("z" * 400, [], 1000),
        ("nothing to hide", [], 300),
        ("", ["x"], 300),
        (None, [], 300),
        ("plain text with blank secrets", ["", None], 300),
    ]
    for text, secrets, limit in cases:
        assert redaction.redact(text, secrets, limit) == store_redact(text, secrets, limit), (text, secrets, limit)
