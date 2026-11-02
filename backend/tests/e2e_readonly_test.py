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
    # Refusals that do not name their cause prove nothing about the table (review WR-02).
    (401, {"message": "Invalid API key"}, False),
    (403, {"message": "forbidden"}, False),
    (404, {"message": "not found"}, False),
    (406, {"code": "PGRST999", "message": "something else"}, False),
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


def test_check_hidden_with_an_invalid_key_is_not_a_pass():
    # The gateway refuses every request when the key is wrong; that must not read as "table hidden".
    with _fake() as fake:
        results = ev.check_hidden(_cfg(fake, key=OTHER_KEY))
    assert [r.name for r in results] == ["key_sanity"]
    assert not results[0].ok and "no refusal is trusted" in results[0].detail
    assert OTHER_KEY not in results[0].detail


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


# ---------------------------------------------------------------------------
# E2E-03: anon writes are refused and the data is provably unchanged
# ---------------------------------------------------------------------------

CUTOFF = "2026-10-26T11:00:00"  # NOW floored to the hour (12:00) minus one hour
TABLE_ATTEMPTS = ["write:table_insert", "write:table_upsert", "write:table_patch", "write:table_delete"]
VIEW_ATTEMPTS = ["write:view_insert", "write:view_patch", "write:view_delete"]


def _write_rows(newest=NEWEST, slots=6):
    """Four cities x six hourly slots; every slot older than 11:00Z is before the cutoff."""
    return make_rating_rows(slots, newest=newest)


def _before_cutoff(rows):
    return sorted((r for r in rows if r["valid_time"] < CUTOFF), key=lambda r: (r["city"], r["valid_time"]))


def _by_name(results):
    return {r.name: r for r in results}


def _write_requests(fake):
    return [r for r in fake.requests if r["method"] != "GET"]


def _rows_snapshot(fake):
    return json.dumps(fake.rows, sort_keys=True)


def test_check_writes_passes_when_writes_are_refused_by_privilege():
    with _fake(rows=_write_rows(), write_mode="revoked") as fake:
        before = _rows_snapshot(fake)
        results = ev.check_writes(_cfg(fake), now=NOW)
        after = _rows_snapshot(fake)
        writes = _write_requests(fake)
    assert all(r.ok for r in results), results
    names = [r.name for r in results]
    assert set(TABLE_ATTEMPTS + VIEW_ATTEMPTS + ["snapshot_before", "snapshot_unchanged"]) <= set(names)
    assert before == after
    assert [(w["method"], w["path"].rsplit("/", 1)[1]) for w in writes] == [
        ("POST", "city_rating"), ("POST", "city_rating"), ("PATCH", "city_rating"), ("DELETE", "city_rating"),
        ("POST", "latest_rating"), ("PATCH", "latest_rating"), ("DELETE", "latest_rating")]
    assert "refused by privilege" in _by_name(results)["write:table_insert"].detail


def test_rls_only_rejection_fails(monkeypatch, capsys):
    with _fake(rows=_write_rows(), write_mode="rls_only") as fake:
        results = _by_name(ev.check_writes(_cfg(fake), now=NOW))
        _set_env(monkeypatch, fake)
        assert ev.main(["--check-writes"], now=NOW) == 1
    insert = results["write:table_insert"]
    assert not insert.ok and "RLS-only" in insert.detail and "a write grant is still present" in insert.detail
    for name in ("write:table_patch", "write:table_delete"):
        assert not results[name].ok and "write accepted" in results[name].detail
    assert all(results[name].ok for name in VIEW_ATTEMPTS)
    assert results["snapshot_unchanged"].ok  # nothing changed, yet the grants are wrong: the verdict is the attempts
    assert "write:table_patch" in capsys.readouterr().out


def test_accepted_writes_fail_and_print_recovery(monkeypatch, capsys, tmp_path):
    rows = _write_rows()
    target = _before_cutoff(rows)[0]
    out = tmp_path / "evidence.json"
    with _fake(rows=rows, write_mode="open") as fake:
        _set_env(monkeypatch, fake)
        code = ev.main(["--check-writes", "--json-out", str(out)], now=NOW)
    text = capsys.readouterr().out
    assert code == 1
    assert "RECOVERY" in text
    assert target["city"] in text and target["valid_time"] in text
    assert "2000-01-01T00:00:00Z" in text and "delete from public.city_rating" in text
    report = json.loads(out.read_text(encoding="utf-8"))
    verdicts = {c["name"]: c for c in report["checks"]}
    for name in TABLE_ATTEMPTS:
        assert not verdicts[name]["ok"] and "write accepted" in verdicts[name]["detail"]
    assert not verdicts["snapshot_unchanged"]["ok"] and "snapshot changed" in verdicts["snapshot_unchanged"]["detail"]


def test_constraint_rejection_is_inconclusive():
    body = {"code": "23502", "message": "null value in column \"rating_amps\" violates not-null constraint"}
    with _fake(rows=_write_rows(), table_write_response=(400, body)) as fake:
        results = _by_name(ev.check_writes(_cfg(fake), now=NOW))
    for name in TABLE_ATTEMPTS:
        assert not results[name].ok and "inconclusive" in results[name].detail
    assert all(results[name].ok for name in VIEW_ATTEMPTS)


def test_403_permission_denied_passes_like_401():
    body = {"code": "42501", "message": "permission denied for table city_rating"}
    with _fake(rows=_write_rows(), table_write_response=(403, body)) as fake:
        results = ev.check_writes(_cfg(fake), now=NOW)
    assert all(r.ok for r in results), results


@pytest.mark.parametrize("status,body,expect_ok", [
    (401, {"message": "x"}, True), (405, {"message": "x"}, True),
    (500, {"code": "55000", "message": "cannot change view"}, True),  # what the live service answers
    (500, {"message": "x"}, False), (504, {"message": "x"}, False),   # a 5xx with no database code proves nothing
    (200, [], False), (201, [], False)])
def test_view_write_verdicts(status, body, expect_ok):
    with _fake(rows=_write_rows(), view_write_response=(status, body)) as fake:
        results = _by_name(ev.check_writes(_cfg(fake), now=NOW))
    for name in VIEW_ATTEMPTS:
        assert results[name].ok is expect_ok, results[name]
        if not expect_ok:
            assert ("write accepted" if status < 300 else "inconclusive") in results[name].detail
    assert all(results[name].ok for name in TABLE_ATTEMPTS)


def test_rows_after_the_cutoff_do_not_break_the_snapshot():
    rows = make_rating_rows(6, newest=NEWEST - timedelta(hours=1))  # 11:00 and older; nothing at 12:00 yet
    live_upsert = make_rating_rows(1, newest=NEWEST, cities=("AUSTIN",))  # the current-hour slot (OD-7)

    def hook(fake, record):
        if record["method"] != "GET" and not getattr(fake, "_hooked", False):
            fake._hooked = True
            fake.rows.extend(live_upsert)

    with _fake(rows=rows, before_request=hook) as fake:
        results = ev.check_writes(_cfg(fake), now=NOW)
        assert len(fake.rows) == len(rows) + 1
    assert all(r.ok for r in results), results


def test_change_before_the_cutoff_fails():
    def hook(fake, record):
        if record["method"] != "GET" and not getattr(fake, "_hooked", False):
            fake._hooked = True
            _before_cutoff(fake.rows)[-1]["rating_amps"] += 5.0

    lines = []
    with _fake(rows=_write_rows(), before_request=hook) as fake:
        results = _by_name(ev.check_writes(_cfg(fake), now=NOW, lines=lines))
    changed = results["snapshot_unchanged"]
    assert not changed.ok and "snapshot changed" in changed.detail
    assert "backfill load" in changed.detail and "manual past-slot re-run" in changed.detail
    assert any("RECOVERY" in line for line in lines)


@pytest.mark.parametrize("label,rows", [
    ("no_rows_at_all", []),
    ("only_rows_after_the_cutoff", make_rating_rows(2, newest=NEWEST)),  # 12:00 and 11:00: neither is before 11:00
])
def test_empty_table_fails_without_writing(label, rows):
    with _fake(rows=rows) as fake:
        results = ev.check_writes(_cfg(fake), now=NOW)
        assert _write_requests(fake) == []
    assert len(results) == 1 and not results[0].ok
    assert "nothing to prove unchanged" in results[0].detail


def test_check_writes_is_idempotent():
    with _fake(rows=_write_rows(), write_mode="revoked") as fake:
        start = _rows_snapshot(fake)
        first = ev.check_writes(_cfg(fake), now=NOW)
        second = ev.check_writes(_cfg(fake), now=NOW)
        assert _rows_snapshot(fake) == start
        deletes = [w for w in _write_requests(fake) if w["method"] == "DELETE"]
    assert [tuple(r) for r in first] == [tuple(r) for r in second]
    assert all(r.ok for r in first)
    assert len(deletes) == 4  # two attempts per run, two runs; the script retries nothing itself


def test_snapshot_pages_and_cross_checks_the_count():
    rows = make_rating_rows(625, newest=NEWEST)  # 2500 rows
    old = [r for r in rows if r["valid_time"] < CUTOFF]
    assert 2000 < len(old) < 2500
    with _fake(rows=rows, max_rows=1000) as fake:
        snap = ev.snapshot(_cfg(fake), "2026-10-26T11:00:00Z")
        pages = [dict(r["query"]).get("offset") for r in fake.requests if "offset" in dict(r["query"])]
    first = min(old, key=lambda r: (r["city"], r["valid_time"]))
    assert snap.count == len(old)
    assert (snap.target["city"], snap.target["valid_time"]) == (first["city"], first["valid_time"])
    assert pages == ["0", "1000", "2000", str(len(old))]
    assert len(snap.digest) == 64
    with _fake(rows=rows, max_rows=1000, count_override=len(old) - 1) as fake:
        with pytest.raises(ev.SnapshotError):
            ev.snapshot(_cfg(fake), "2026-10-26T11:00:00Z")
        results = ev.check_writes(_cfg(fake), now=NOW)
        assert _write_requests(fake) == []
    assert len(results) == 1 and not results[0].ok and "count=exact" in results[0].detail


def test_write_requests_headers_and_insert_body():
    rows = _write_rows()
    target = _before_cutoff(rows)[0]
    with _fake(rows=rows) as fake:
        ev.check_writes(_cfg(fake), now=NOW)
        writes = _write_requests(fake)
        everything = list(fake.requests)
    assert len(writes) == 7
    for record in everything:
        assert record["headers"]["apikey"] == KEY and "authorization" not in record["headers"]
    for record in writes:
        assert "return=representation" in record["headers"]["prefer"]
    insert, upsert, patch, delete, view_insert, view_patch, view_delete = writes
    body = json.loads(insert["body"])
    assert set(body) == set(target)
    assert body["city"] == "AUSTIN" and body["valid_time"] == "2000-01-01T00:00:00Z"
    assert body["run_id"] == "e2e-03-sentinel"
    assert dict(upsert["query"])["on_conflict"] == "city,valid_time"
    assert "resolution=merge-duplicates" in upsert["headers"]["prefer"]
    merged = json.loads(upsert["body"])
    assert isinstance(merged, list) and merged[0]["rating_amps"] == target["rating_amps"] + 1.0
    assert merged[0]["city"] == target["city"] and merged[0]["valid_time"] == target["valid_time"]
    for record in (patch, delete):
        filters = dict(record["query"])
        assert filters["city"] == "eq." + target["city"] and filters["valid_time"] == "eq." + target["valid_time"]
    assert json.loads(patch["body"]) == {"rating_amps": target["rating_amps"] + 1.0}
    assert list(json.loads(view_insert["body"])) == list(contract.STORED_COLUMNS)
    for record in (view_patch, view_delete):
        assert dict(record["query"])["city"] == "eq." + target["city"]


def test_writes_json_out_has_no_url_or_key(tmp_path, monkeypatch, capsys):
    import urllib.request

    out = tmp_path / "evidence.json"
    with _fake(rows=_write_rows(), key=OTHER_KEY) as fake:
        monkeypatch.setenv(rest.ENV_URL, URL)
        monkeypatch.setenv(rest.ENV_KEY, OTHER_KEY)

        def redirect_to_fake(request, timeout=None):
            moved = urllib.request.Request(request.full_url.replace(URL, fake.url), data=request.data,
                                           headers=dict(request.header_items()), method=request.get_method())
            return urllib.request.urlopen(moved, timeout=timeout)

        code = ev.main(["--check-writes", "--json-out", str(out)], opener=redirect_to_fake, now=NOW)
    captured = capsys.readouterr()
    assert code == 0, captured.out
    text = out.read_text(encoding="utf-8")
    for blob in (text, captured.out, captured.err):
        assert not any(s in blob for s in (URL, HOST, REF, OTHER_KEY)), blob
    report = json.loads(text)
    assert [a["name"] for a in report["attempts"]] == [n.split(":", 1)[1] for n in TABLE_ATTEMPTS + VIEW_ATTEMPTS]
    for attempt in report["attempts"]:
        assert set(attempt) == {"name", "method", "path", "status", "code", "verdict"}
        assert attempt["path"] in ("city_rating", "latest_rating") and attempt["verdict"] == "pass"


@pytest.mark.parametrize("age,is_stale,expect_ok", [
    (90, False, True),   # exactly 90 minutes is fresh (OD-4)
    (91, True, True),
    (90, True, False),
    (91, False, False),
])
def test_stale_flag_boundary_is_strictly_more_than_90(age, is_stale, expect_ok):
    def mutate(rows):
        rows[0].update(age_minutes=age, is_stale=is_stale)

    with _fake(latest_override=_latest_with(mutate)) as fake:
        flags = next(r for r in ev.check_read(_cfg(fake)) if r.name == "latest_rating_flags")
    assert flags.ok is expect_ok, flags
