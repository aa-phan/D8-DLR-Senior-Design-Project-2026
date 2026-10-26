"""
Offline tests for backend/supabase_rest.py and backend/e2e_verify_readonly.py
(production-pipeline Phase 6, API-01 live half and E2E-03).

Nothing here touches the network or reads a .env file. Every request goes to an
in-process fake of PostgREST (tests/fake_postgrest.py) bound to 127.0.0.1, or to a
stub opener that raises. Every planted key, token and project reference is assembled
from pieces so backend/tests/secret_scan_test.py never matches this file.
"""

import ast
import base64
import io
import json
import os
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

import config
import e2e_verify_readonly as ev
import latest_rating_contract as contract
import supabase_rest as rest
from fake_postgrest import FakePostgrest, make_rating_rows

NOW = datetime(2026, 10, 26, 12, 30, tzinfo=timezone.utc)
NEWEST = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
KEY = "sb_" + "publishable_" + "TestKey0123456789abcdef"

# A project reference is 20 lowercase characters; built from pieces on purpose.
REF = "".join(["abcd", "efgh", "ijkl", "mnop", "qrst"])
HOST = REF + "." + "supa" + "base" + ".co"
URL = "https://" + HOST
OTHER_KEY = "sb_" + "publishable_" + "Zy9x8w7v6u5t4s3r2q1p"


def _good_rows(slots=3):
    return make_rating_rows(slots, newest=NEWEST)


def _fake(**kwargs):
    kwargs.setdefault("rows", _good_rows())
    kwargs.setdefault("key", KEY)
    kwargs.setdefault("now", NOW)
    return FakePostgrest(**kwargs)


def _cfg(fake, key=KEY):
    return rest.config_from_env({rest.ENV_URL: fake.url, rest.ENV_KEY: key})


def _set_env(monkeypatch, fake, key=KEY):
    monkeypatch.setenv(rest.ENV_URL, fake.url)
    monkeypatch.setenv(rest.ENV_KEY, key)


def _jwt(role):
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode("utf-8")).rstrip(b"=").decode("ascii")

    return ".".join([b64({"alg": "HS256", "typ": "JWT"}), b64({"role": role, "iss": "supabase"}),
                     "c2ln" + "bmF0" + "dXJlMDEyMzQ1"])


def _latest_with(mutate):
    """The view rows the fake would serve, mutated into a contract violation."""
    rows = FakePostgrest(rows=_good_rows(), key=KEY, now=NOW).latest_view_rows()
    mutate(rows)
    return rows


# ---------------------------------------------------------------------------
# Tracer: the whole path, through main()
# ---------------------------------------------------------------------------


def test_tracer_check_read_end_to_end(tmp_path, monkeypatch, capsys):
    out = tmp_path / "evidence.json"
    with _fake() as fake:
        _set_env(monkeypatch, fake)
        code = ev.main(["--check-read", "--check-hidden", "--json-out", str(out)])
    text = capsys.readouterr().out
    assert code == 0, text
    assert "FAIL" not in text
    for city in config.LOCATIONS:
        lines = [line for line in text.splitlines() if line.startswith("city %s " % city)]
        assert len(lines) == 1, text
        for field in ("valid_time", "age_minutes", "is_stale", "status", "rating_amps", "is_provisional"):
            assert field in lines[0]
    assert text.count("PASS") >= 9
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["exit_code"] == 0
    assert report["attempts"] == []
    assert report["checks"] and all(entry["ok"] for entry in report["checks"])
    names = {entry["name"] for entry in report["checks"]}
    assert {"latest_rating_four_cities", "latest_rating_columns", "keyless_request_refused",
            "hidden:public.pipeline_run", "hidden:ops.freshness_log"} <= names
    assert all(set(entry) == {"name", "ok", "detail"} for entry in report["checks"])


# ---------------------------------------------------------------------------
# check_read failure modes
# ---------------------------------------------------------------------------


def _swap_first_two_keys(rows):
    row = rows[1]
    keys = list(row)
    keys[0], keys[1] = keys[1], keys[0]
    rows[1] = {k: row[k] for k in keys}


READ_CASES = [
    ("three_rows", {"latest": lambda rows: rows.pop()}, "latest_rating_four_cities", "3 rows"),
    ("duplicate_city", {"latest": lambda rows: rows[1].update(city=rows[0]["city"])},
     "latest_rating_four_cities", "duplicate"),
    ("unknown_city", {"latest": lambda rows: rows[0].update(city="ATLANTIS")},
     "latest_rating_four_cities", "unknown"),
    ("missing_column", {"latest": lambda rows: rows[2].pop("rating_mw")}, "latest_rating_columns", "missing"),
    ("extra_column", {"latest": lambda rows: rows[0].update(surprise=1)}, "latest_rating_columns", "extra"),
    ("reordered_columns", {"latest": _swap_first_two_keys}, "latest_rating_columns", "order"),
    ("non_positive_rating", {"latest": lambda rows: rows[0].update(rating_amps=0)},
     "latest_rating_values", "rating_amps"),
    ("off_the_hour", {"latest": lambda rows: rows[0].update(valid_time="2026-10-26T12:30:00+00:00")},
     "latest_rating_values", "whole hour"),
    ("stale_flag_disagrees", {"latest": lambda rows: rows[0].update(is_stale=True)},
     "latest_rating_flags", "is_stale"),
    ("provisional_flag_disagrees", {"latest": lambda rows: rows[0].update(is_provisional=False)},
     "latest_rating_flags", "is_provisional"),
    ("keyless_request_answered", {"require_key": False}, "keyless_request_refused", "without"),
    ("assert_fresh_missing", {"rpc_available": False}, "assert_fresh_answers", "404"),
]


@pytest.mark.parametrize("label,setup,check_name,expected_text", READ_CASES, ids=[c[0] for c in READ_CASES])
def test_check_read_failures(monkeypatch, label, setup, check_name, expected_text):
    kwargs = {k: v for k, v in setup.items() if k != "latest"}
    if "latest" in setup:
        kwargs["latest_override"] = _latest_with(setup["latest"])
    with _fake(**kwargs) as fake:
        results = ev.check_read(_cfg(fake))
        failing = [r for r in results if not r.ok]
        assert any(r.name == check_name and expected_text in r.detail for r in failing), results
        _set_env(monkeypatch, fake)
        assert ev.main(["--check-read"]) == 1


def test_a_clean_fake_passes_every_read_check():
    with _fake() as fake:
        results = ev.check_read(_cfg(fake))
    assert results and all(r.ok for r in results), results
    names = [r.name for r in results]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Key handling
# ---------------------------------------------------------------------------


def test_requests_carry_the_key_only_in_the_apikey_header():
    with _fake() as fake:
        cfg = _cfg(fake)
        assert all(r.ok for r in ev.check_read(cfg) + ev.check_hidden(cfg))
        recorded = list(fake.requests)
    assert recorded
    keyless = [r for r in recorded if "apikey" not in r["headers"]]
    assert len(keyless) == 1 and keyless[0]["path"].endswith("/latest_rating")
    for record in recorded:
        assert "authorization" not in record["headers"]
        assert KEY not in record["path"] and KEY not in repr(record["query"])
        if record not in keyless:
            assert record["headers"]["apikey"] == KEY


@pytest.mark.parametrize("label,bad_key", [
    ("secret_key", "sb_" + "secret_" + "x" * 24),
    ("service_role_jwt", _jwt("service_role")),
])
def test_secret_or_service_role_key_is_refused_before_any_request(monkeypatch, capsys, label, bad_key):
    with _fake() as fake:
        with pytest.raises(rest.ConfigError) as excinfo:
            rest.config_from_env({rest.ENV_URL: fake.url, rest.ENV_KEY: bad_key})
        assert bad_key not in str(excinfo.value)
        _set_env(monkeypatch, fake, key=bad_key)
        assert ev.main(["--check-read", "--check-hidden"]) == 2
        captured = capsys.readouterr()
        assert bad_key not in captured.out + captured.err
        assert fake.requests == []


def test_an_anon_jwt_and_a_publishable_key_are_accepted():
    for key in (_jwt("anon"), KEY):
        cfg = rest.config_from_env({rest.ENV_URL: "http://127.0.0.1:1", rest.ENV_KEY: key})
        assert cfg.key == key


def test_config_from_env_strips_the_value_and_a_trailing_slash():
    cfg = rest.config_from_env({rest.ENV_URL: "  http://127.0.0.1:9999/\n", rest.ENV_KEY: " " + KEY + "\n"})
    assert cfg.base_url == "http://127.0.0.1:9999"
    assert cfg.key == KEY


def test_missing_env_names_the_variable_not_a_value(monkeypatch, capsys):
    url_only = {rest.ENV_URL: URL}
    with pytest.raises(rest.ConfigError) as excinfo:
        rest.config_from_env(url_only)
    assert rest.ENV_KEY in str(excinfo.value) and URL not in str(excinfo.value)
    with pytest.raises(rest.ConfigError) as excinfo:
        rest.config_from_env({rest.ENV_URL: URL, rest.ENV_KEY: "   "})
    assert rest.ENV_KEY in str(excinfo.value)
    with pytest.raises(rest.ConfigError) as excinfo:
        rest.config_from_env({rest.ENV_KEY: KEY})
    assert rest.ENV_URL in str(excinfo.value) and KEY not in str(excinfo.value)

    monkeypatch.delenv(rest.ENV_URL, raising=False)
    monkeypatch.setenv(rest.ENV_KEY, KEY)
    assert ev.main(["--check-read"]) == 2
    captured = capsys.readouterr()
    assert rest.ENV_URL in captured.err
    assert KEY not in captured.out + captured.err


# ---------------------------------------------------------------------------
# check_hidden
# ---------------------------------------------------------------------------

HIDDEN_CASES = [
    (401, {"code": "42501", "message": "permission denied"}, True),
    (403, {"code": "42501", "message": "permission denied"}, True),
    (404, {"code": "PGRST205", "message": "not found"}, True),
    (406, {"code": "PGRST106", "message": "schema not exposed"}, True),
    (200, [{"id": 1, "breach": False}], False),
    (200, [], False),
    (500, {"message": "boom"}, False),
]


@pytest.mark.parametrize("status,body,expect_ok", HIDDEN_CASES, ids=["%s-%s" % (c[0], i) for i, c in enumerate(HIDDEN_CASES)])
def test_check_hidden_verdicts(status, body, expect_ok):
    overrides = {"public.pipeline_run": (status, body), "ops.freshness_log": (status, body)}
    with _fake(route_overrides=overrides) as fake:
        results = ev.check_hidden(_cfg(fake))
    assert [r.name for r in results] == ["hidden:public.pipeline_run", "hidden:ops.freshness_log"]
    assert all(r.ok is expect_ok for r in results), results
    if not expect_ok and status == 200:
        assert all("readable by the public key" in r.detail for r in results)


def test_check_hidden_default_fake_hides_both_tables():
    with _fake() as fake:
        results = ev.check_hidden(_cfg(fake))
        profiles = [r["headers"].get("accept-profile") for r in fake.requests]
    assert all(r.ok for r in results), results
    assert "ops" in profiles


# ---------------------------------------------------------------------------
# Client mechanics
# ---------------------------------------------------------------------------


def test_get_all_pages_until_an_empty_page():
    rows = make_rating_rows(625, newest=NEWEST)  # 4 cities x 625 hours = 2500 rows
    assert len(rows) == 2500
    params = [("select", "city,valid_time")]
    order = "city.asc,valid_time.asc"
    with _fake(rows=rows, max_rows=1000) as fake:
        got = rest.get_all(_cfg(fake), "city_rating", params, order)
        offsets = [dict(r["query"]).get("offset") for r in fake.requests]
    assert len(got) == 2500
    assert len({(r["city"], r["valid_time"]) for r in got}) == 2500
    assert offsets == ["0", "1000", "2000", "2500"]  # the fourth page is empty and ends the loop
    # A cap below the page size must not end the loop early (06-RESEARCH Pitfall 6).
    with _fake(rows=rows, max_rows=400) as fake:
        got = rest.get_all(_cfg(fake), "city_rating", params, order)
        assert len(fake.requests) == 8  # seven pages of at most 400, then the empty one
    assert len(got) == 2500


def test_count_exact_reads_the_total_after_the_slash():
    with _fake(rows=make_rating_rows(625, newest=NEWEST), max_rows=1000) as fake:
        assert rest.count_exact(_cfg(fake), "city_rating", [("select", "city")]) == 2500
        assert rest.count_exact(_cfg(fake), "latest_rating", []) == 4


def test_parse_ts_fractions_and_offsets():
    utc = timezone.utc
    expected_base = datetime(2026, 10, 25, 1, 0, 0, tzinfo=utc)
    same_instant = [
        "2026-10-25T01:00:00Z",
        "2026-10-25T01:00:00+00:00",
        "2026-10-25T01:00:00+00",
        "2026-10-25T01:00:00+0000",
        "2026-10-25 01:00:00+00:00",
        "2026-10-25T01:00:00",
        "2026-10-24T20:00:00-05:00",
        "2026-10-25T06:30:00+05:30",
    ]
    for text in same_instant:
        parsed = rest.parse_ts(text)
        assert parsed.utcoffset() is not None, text
        assert parsed == expected_base, text
    fractions = {
        "2026-10-25T01:00:00.1+00:00": 100000,
        "2026-10-25T01:00:00.11297+00:00": 112970,
        "2026-10-25T01:00:00.123456Z": 123456,
        "2026-10-25T01:00:00.1234567+00": 123456,
        "2026-10-25T01:00:00.000001+0000": 1,
    }
    for text, micro in fractions.items():
        assert rest.parse_ts(text) == expected_base.replace(microsecond=micro), text
    assert rest.parse_ts("2026-10-24T20:00:00.5-05:00") == expected_base.replace(microsecond=500000)
    for bad in ("", "yesterday", "2026-10-25", "2026-10-25T01:00"):
        with pytest.raises(ValueError):
            rest.parse_ts(bad)


# ---------------------------------------------------------------------------
# D-10: no URL, host, project reference or key in any output
# ---------------------------------------------------------------------------


def _raising_opener(factory):
    def opener(request, timeout=None):
        raise factory(request)

    return opener


def _url_error(request):
    return urllib.error.URLError("cannot reach %s with %s" % (request.full_url, OTHER_KEY))


def _http_error(request):
    body = json.dumps({"message": "failed at %s using %s" % (request.full_url, OTHER_KEY), "host": HOST})
    return urllib.error.HTTPError(request.full_url, 500, "boom " + URL, {}, io.BytesIO(body.encode("utf-8")))


@pytest.mark.parametrize("factory", [_url_error, _http_error], ids=["url_error", "http_error_echoing_the_url"])
def test_errors_and_json_out_never_leak_url_or_key(tmp_path, monkeypatch, capsys, factory):
    monkeypatch.setenv(rest.ENV_URL, URL)
    monkeypatch.setenv(rest.ENV_KEY, OTHER_KEY)
    secrets = [URL, HOST, REF, OTHER_KEY]
    cfg = rest.config_from_env({rest.ENV_URL: URL, rest.ENV_KEY: OTHER_KEY})

    # A network failure is a RestError with no value and no chained exception; an HTTP error status
    # comes back as a value whose description is redacted.
    try:
        response = rest.request(cfg, "GET", "latest_rating", opener=_raising_opener(factory))
    except rest.RestError as exc:
        assert factory is _url_error
        assert exc.__cause__ is None and exc.__context__ is None
        assert not any(s in str(exc) for s in secrets)
    else:
        assert factory is _http_error and response.status == 500
        assert URL in response.text  # the planted echo really is in the body ...
        assert not any(s in rest.brief(response, cfg) for s in secrets)  # ... and never in its description

    out = tmp_path / "evidence.json"
    code = ev.main(["--check-read", "--check-hidden", "--json-out", str(out)], opener=_raising_opener(factory))
    assert code == 1
    captured = capsys.readouterr()
    for blob in (captured.out, captured.err, out.read_text(encoding="utf-8")):
        assert not any(s in blob for s in secrets), blob
    assert json.loads(out.read_text(encoding="utf-8"))["exit_code"] == 1


def test_redact_rest_removes_url_host_reference_and_both_key_kinds():
    cfg = rest.config_from_env({rest.ENV_URL: URL, rest.ENV_KEY: OTHER_KEY})
    other_ref_host = "".join(["zzzz", "yyyy", "xxxx", "wwww", "vvvv"]) + "." + "supa" + "base" + ".co"
    secret_prefix_key = "sb_" + "secret_" + "Qw3rTy5uIoP7aSdF9gHj"
    text = "GET %s/rest/v1/x?apikey=%s host=%s other=%s secret=%s ref=%s" % (
        URL, OTHER_KEY, HOST, other_ref_host, secret_prefix_key, REF)
    cleaned = rest.redact_rest(text, cfg, limit=None)
    for value in (URL, HOST, REF, OTHER_KEY, other_ref_host, secret_prefix_key):
        assert value not in cleaned
    assert "REDACTED" in cleaned
    # The cut is made after redaction, so a short limit cannot expose a value.
    short = rest.redact_rest(URL + "/" + OTHER_KEY, cfg, limit=15)
    assert len(short) <= 15 and "https" not in short and OTHER_KEY[:12] not in short
    assert len(rest.redact_rest("x" * 1000, cfg)) == 300


# ---------------------------------------------------------------------------
# The contract is imported, never copied
# ---------------------------------------------------------------------------


def test_latest_columns_come_from_the_contract(monkeypatch):
    path = os.path.join(os.path.dirname(ev.__file__), "e2e_verify_readonly.py")
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    known = set(contract.LATEST_COLUMNS)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Tuple, ast.List)):
            strings = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            assert not (len(strings) >= 5 and set(strings) <= known), "a local copy of the column list"
    # Behaviour follows the contract module: add a column there and the verifier notices.
    monkeypatch.setattr(contract, "LATEST_COLUMNS", contract.LATEST_COLUMNS + ("brand_new_column",))
    with _fake() as fake:
        results = ev.check_read(_cfg(fake))
    assert any(r.name == "latest_rating_columns" and not r.ok and "brand_new_column" in r.detail for r in results)
