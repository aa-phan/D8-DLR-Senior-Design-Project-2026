"""
Offline tests for the three consumer examples in docs/integration/examples/
(production-pipeline Phase 6, API-02, D-10, D-11, D-12).

The Python example runs as a subprocess on the oldest local Python 3 (/usr/bin/python3, older
than 3.11 on purpose, so its own timestamp helper is exercised) and on the repository's
interpreter; the curl example runs under bash; the supabase-js example gets a syntax check
(installing supabase-js is not part of this plan). Every run talks to the in-process fake
PostgREST of tests/fake_postgrest.py on 127.0.0.1, so nothing here touches the network, reads a
.env file or contacts the live project. Planted values are assembled from pieces so
backend/tests/secret_scan_test.py never matches this file.
"""

import ast
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import config
import secret_scan_test as scan
import supabase_rest
from fake_postgrest import FakePostgrest, make_rating_rows

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "docs" / "integration" / "examples"
PY_EXAMPLE = EXAMPLES / "read_ratings.py"
CURL_EXAMPLE = EXAMPLES / "curl.sh"
JS_EXAMPLE = EXAMPLES / "supabase_js.mjs"
ALL_EXAMPLES = (PY_EXAMPLE, CURL_EXAMPLE, JS_EXAMPLE)

OLDEST_PYTHON = "/usr/bin/python3"
INTERPRETERS = [
    pytest.param(sys.executable, id="repo-interpreter"),
    pytest.param(
        OLDEST_PYTHON,
        id="oldest-local-python",
        marks=pytest.mark.skipif(not os.path.exists(OLDEST_PYTHON), reason="no /usr/bin/python3 on this machine"),
    ),
]

NEWEST = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
HISTORY_SLOTS = 2500
KEY = "sb_" + "publishable_" + "ExampleKey0123456789abcdef"
WRONG_KEY = "sb_" + "publishable_" + "WrongKey9876543210zyxwvu"


def _z(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


START = _z(NEWEST - timedelta(hours=HISTORY_SLOTS - 1))
END = _z(NEWEST + timedelta(hours=1))


def _history_rows(cities=config.LOCATIONS):
    """AUSTIN with 2,500 hourly rows (more than two pages of 1,000), every other city with 3."""
    rows = []
    if "AUSTIN" in cities:
        slots = [NEWEST - timedelta(hours=i) for i in range(HISTORY_SLOTS)]
        rows += make_rating_rows(slots, cities=("AUSTIN",))
    others = tuple(c for c in cities if c != "AUSTIN")
    if others:
        # Since the Phase 7 go the current live label is not provisional; older live rows still are, so the
        # other cities carry a pre-go version label to exercise the example's PROVISIONAL line.
        rows += make_rating_rows(3, cities=others, newest=NEWEST, config_version="v2-provisional-2026-11-02")
    return rows


def _fake(**kwargs):
    kwargs.setdefault("rows", _history_rows())
    kwargs.setdefault("key", KEY)
    kwargs.setdefault("now", NEWEST + timedelta(minutes=20))
    return FakePostgrest(**kwargs)


def _env(fake, **extra):
    env = {k: v for k, v in os.environ.items() if not k.startswith("SUPABASE_")}
    env["SUPABASE_URL"] = fake.url
    env["SUPABASE_PUBLISHABLE_KEY"] = KEY
    env.update(extra)
    return env


def _run(argv, env, cwd):
    return subprocess.run(argv, env=env, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=180)


def _city_requests(requests):
    return [r for r in requests if r["path"].endswith("/city_rating")]


def _offsets(requests):
    return [int(dict(r["query"])["offset"]) for r in requests if "offset" in dict(r["query"])]


@pytest.fixture(scope="module")
def example():
    spec = importlib.util.spec_from_file_location("read_ratings_example", str(PY_EXAMPLE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Tracer: the Python example, as written, against the in-process server
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("interpreter", INTERPRETERS)
def test_tracer_read_ratings_runs_against_the_fake(interpreter, tmp_path):
    with _fake() as fake:
        done = _run([interpreter, "-I", str(PY_EXAMPLE), "--city", "AUSTIN", "--start", START, "--end", END],
                    _env(fake), tmp_path)
        requests = list(fake.requests)
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    cities = [m.group(1) for m in (re.match(r"^([A-Z_]+)\s+[\d.]+ A ", line) for line in done.stdout.splitlines()) if m]
    assert cities == list(config.LOCATIONS)
    assert "AUSTIN rows from %s to %s: 2500" % (START, END) in done.stdout
    assert "PROVISIONAL" in done.stdout
    assert _offsets(_city_requests(requests)) == [0, 1000, 2000, 2500]
    assert [r["path"] for r in requests if r["path"].endswith("/latest_rating")] == ["/rest/v1/latest_rating"]
    assert sorted(os.listdir(str(tmp_path))) == []  # no local file written


# ---------------------------------------------------------------------------
# D-11: standard library only, Python 3.7 grammar, parse_ts
# ---------------------------------------------------------------------------


def test_read_ratings_is_stdlib_only_and_parses_as_python_37():
    source = PY_EXAMPLE.read_text(encoding="utf-8")
    tree = ast.parse(source, feature_version=(3, 7))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0 and node.module
            imported.add(node.module.split(".")[0])
    assert imported, "the example imports nothing?"
    assert imported <= set(sys.stdlib_module_names), sorted(imported - set(sys.stdlib_module_names))
    assert "def parse_ts(" in source
    # the gate is real: the same call rejects syntax newer than 3.7
    with pytest.raises(SyntaxError):
        ast.parse("if (n := 1):\n    pass\n", feature_version=(3, 7))
    # and the example avoids the other newer spellings explicitly
    assert ":=" not in source
    assert "removeprefix" not in source and "removesuffix" not in source
    assert not re.search(r"\bf[\"']", source), "f-strings are avoided so the file stays easy to read on old interpreters"


def test_parse_ts_matches_the_backend_helper(example):
    stamps = [
        "2026-10-25T01:00:00Z",
        "2026-10-25T01:00:00+00",
        "2026-10-25T01:00:00+0000",
        "2026-10-25T01:00:00+00:00",
        "2026-10-25T01:00:00-05:00",
        "2026-10-25 01:00:00+00:00",
        "2026-10-25T01:00:00",
    ]
    for digits in range(0, 7):
        fraction = "." + "123456"[:digits] if digits else ""
        for offset in ("Z", "+00:00", "-05:00"):
            stamps.append("2026-10-25T01:00:14%s%s" % (fraction, offset))
    for stamp in stamps:
        mine = example.parse_ts(stamp)
        theirs = supabase_rest.parse_ts(stamp)
        assert mine == theirs, stamp
        assert mine.utcoffset() == theirs.utcoffset(), stamp
        assert mine.tzinfo is not None
    with pytest.raises(ValueError):
        example.parse_ts("yesterday")


def test_default_window_is_seven_days_back_to_one_hour_ahead(example):
    now = datetime(2026, 10, 26, 12, 34, 56, tzinfo=timezone.utc)
    assert example.default_window(now) == ("2026-10-19T12:00:00Z", "2026-10-26T13:00:00Z")


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


def test_read_ratings_fails_on_three_cities_or_http_error(example, monkeypatch, capsys):
    three = _history_rows(cities=("AUSTIN", "CORPUS_CHRISTI", "MIDLAND"))
    with _fake(rows=three) as fake:
        monkeypatch.setenv("SUPABASE_URL", fake.url)
        monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", KEY)
        code = example.main(["--city", "AUSTIN", "--start", START, "--end", END])
    captured = capsys.readouterr()
    assert code == 1
    assert "EL_PASO" in captured.err

    with _fake() as fake:
        monkeypatch.setenv("SUPABASE_URL", fake.url)
        monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", WRONG_KEY)
        code = example.main(["--city", "AUSTIN", "--start", START, "--end", END])
        url = fake.url
    captured = capsys.readouterr()
    assert code == 1
    assert "401" in captured.err
    for text in (captured.out, captured.err):
        assert WRONG_KEY not in text and KEY not in text and url not in text


def test_read_ratings_missing_env_exits_2(tmp_path):
    with _fake() as fake:
        base = _env(fake)
        for name in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"):
            env = {k: v for k, v in base.items() if k != name}
            done = _run([sys.executable, "-I", str(PY_EXAMPLE)], env, tmp_path)
            assert done.returncode == 2, done.stderr
            assert name in done.stderr
            assert done.stdout == ""
        assert fake.requests == []  # nothing was sent before the check


def test_read_ratings_survives_a_server_cap_below_the_page_size(example, monkeypatch, capsys):
    with _fake(max_rows=400) as fake:
        monkeypatch.setenv("SUPABASE_URL", fake.url)
        monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", KEY)
        code = example.main(["--city", "AUSTIN", "--start", START, "--end", END])
        offsets = _offsets(_city_requests(fake.requests))
    assert code == 0, capsys.readouterr().err
    assert "rows from %s to %s: 2500" % (START, END) in capsys.readouterr().out
    assert offsets == [0, 400, 800, 1200, 1600, 2000, 2400, 2500]


def test_read_ratings_keeps_certificate_verification():
    source = PY_EXAMPLE.read_text(encoding="utf-8")
    for needle in ("_create_unverified_context", "_create_default_https_context", "CERT_NONE",
                   "check_hostname", "verify=False", "import ssl", "from ssl", "context="):
        assert needle not in source, needle
    assert "urllib.request.urlopen(" in source


# ---------------------------------------------------------------------------
# curl and supabase-js
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("curl")), reason="bash and curl are required")
def test_curl_example_pages_past_the_cap(tmp_path):
    subprocess.run(["bash", "-n", str(CURL_EXAMPLE)], check=True)
    text = CURL_EXAMPLE.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text
    code = [line for line in text.splitlines() if not line.lstrip().startswith("#")]
    invocations = [line for line in code if re.search(r"\bcurl\b", line)]
    assert len(invocations) == 3  # latest_rating, the HEAD count, and the paging loop
    assert all(re.search(r"\bcurl -fsS", line) for line in invocations)  # -f: an HTTP error stops the script
    with _fake() as fake:
        env = _env(fake, CITY="AUSTIN", START=START, END=END)
        done = _run(["bash", str(CURL_EXAMPLE)], env, tmp_path)
        requests = list(fake.requests)
    assert done.returncode == 0, done.stderr
    for city in config.LOCATIONS:
        assert city in done.stdout
    assert "total rows: 2500" in done.stdout
    assert {r["method"] for r in requests} <= {"GET", "HEAD"}
    city_requests = _city_requests(requests)
    heads = [r for r in city_requests if r["method"] == "HEAD"]
    assert len(heads) == 1
    assert heads[0]["headers"].get("prefer") == "count=exact"
    data = [r for r in city_requests if r["method"] == "GET"]
    assert _offsets(data) == [0, 1000, 2000]
    for request in data:
        query = dict(request["query"])
        assert query["order"] == "valid_time.asc" and query["limit"] == "1000"
    assert sorted(os.listdir(str(tmp_path))) == []


def test_curl_example_stops_when_the_row_count_cannot_be_read(tmp_path):
    if not (shutil.which("bash") and shutil.which("curl")):
        pytest.skip("bash and curl are required")
    with _fake(route_overrides={"city_rating": (200, [])}) as fake:
        done = _run(["bash", str(CURL_EXAMPLE)], _env(fake, CITY="AUSTIN", START=START, END=END), tmp_path)
    assert done.returncode != 0  # set -e plus the explicit check: never a quiet success on a missing total


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("curl")), reason="bash and curl are required")
def test_curl_example_fails_on_an_http_error(tmp_path):
    with _fake() as fake:
        env = _env(fake, CITY="AUSTIN", START=START, END=END, SUPABASE_PUBLISHABLE_KEY=WRONG_KEY)
        done = _run(["bash", str(CURL_EXAMPLE)], env, tmp_path)
    assert done.returncode != 0  # curl -f turns the 401 into a failure, set -e stops the script
    assert WRONG_KEY not in done.stdout + done.stderr


def test_supabase_js_example_syntax_and_contract():
    text = JS_EXAMPLE.read_text(encoding="utf-8")
    assert "createClient" in text and "@supabase/supabase-js" in text
    for name in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY"):
        assert "process.env.%s" % name in text
    assert "'latest_rating'" in text and "'city_rating'" in text
    assert ".range(" in text
    assert re.search(r"\.order\(\s*'valid_time'\s*,\s*\{\s*ascending:\s*true\s*\}\s*\)", text)
    assert re.search(r"data\.length\s*===\s*0", text) and "break" in text
    assert "@2" in text, "the install line pins the major version"
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not on PATH")
    done = subprocess.run([node, "--check", str(JS_EXAMPLE)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, timeout=60)
    assert done.returncode == 0, done.stderr
    # nothing was installed to make that pass
    for stray in ("package.json", "node_modules", "package-lock.json"):
        assert not (REPO / stray).exists()
        assert not (EXAMPLES / stray).exists()


# ---------------------------------------------------------------------------
# Read-only, one credential header, no project values
# ---------------------------------------------------------------------------

# HTTP verbs and curl's short flags are matched case-sensitively (prose may say "delete", and
# `-D`/`-f` are different flags); the rest ignore case.
_WRITE_VERBS = [r"\bPOST\b", r"\bPUT\b", r"\bPATCH\b", r"\bDELETE\b",
                r"(^|\s)-X\b", r"(^|\s)-d\b", r"(^|\s)-F\b", r"(^|\s)-T\b"]
_WRITE_WORDS = [
    r"\.insert\(", r"\.update\(", r"\.upsert\(", r"\.delete\(",
    r"--request\b", r"--data",
    r"\bdata=", r"\bmethod\s*[:=]", r"(?<![A-Za-z_.])open\(", r"writeFile", r"\.write\(",
]
_CREDENTIAL_WORDS = [r"authorization", r"bearer", r"\bcookie\b", r"x-api-key"]


@pytest.mark.skipif(not (shutil.which("bash") and shutil.which("curl")), reason="bash and curl are required")
def test_examples_are_read_only_and_send_one_credential_header(tmp_path):
    for path in ALL_EXAMPLES:
        text = path.read_text(encoding="utf-8")
        for pattern in _WRITE_VERBS:
            assert not re.search(pattern, text), (path.name, pattern)
        for pattern in _WRITE_WORDS:
            assert not re.search(pattern, text, re.IGNORECASE), (path.name, pattern)
        for pattern in _CREDENTIAL_WORDS:
            assert not re.search(pattern, text, re.IGNORECASE), (path.name, pattern)
        assert "apikey" in text or "createClient" in text
    with _fake() as fake:
        env = _env(fake, CITY="AUSTIN", START=START, END=END)
        assert _run([sys.executable, "-I", str(PY_EXAMPLE), "--start", START, "--end", END], env, tmp_path).returncode == 0
        assert _run(["bash", str(CURL_EXAMPLE)], env, tmp_path).returncode == 0
        requests = list(fake.requests)
    assert requests
    for request in requests:
        assert request["method"] in ("GET", "HEAD")
        assert request["body"] is None
        headers = request["headers"]
        assert headers.get("apikey") == KEY
        assert "authorization" not in headers and "cookie" not in headers
    assert sorted(os.listdir(str(tmp_path))) == []  # repeated and concurrent runs leave no state


def test_examples_carry_no_url_or_key():
    host_suffix = "." + "supa" + "base" + "."
    for path in ALL_EXAMPLES:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            assert scan._scan_line(line) == [], (path.name, number)
            assert host_suffix not in line.lower() or "docs" in line.lower(), (path.name, number)
            assert not re.search(r"\beyJ[A-Za-z0-9_-]{7,}\.", line), (path.name, number)
        text = path.read_text(encoding="utf-8")
        assert "SUPABASE_URL" in text and "SUPABASE_PUBLISHABLE_KEY" in text
        assert not re.search(r"https?://[A-Za-z0-9-]{20}\.", text)
