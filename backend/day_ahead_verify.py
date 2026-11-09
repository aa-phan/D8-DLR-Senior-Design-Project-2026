"""
Read-only first-slot check of the day-ahead forecast store (production-pipeline Phase 8: DAY-08, D-17)
=======================================================================================================
After the day-ahead stage is pushed and the first hourly run has issued rows, this answers the
go-live question in one command: "did every due target get a correct row?" It only reads. It
never inserts, updates or deletes: the whole session is one `BEGIN READ ONLY` transaction that is
rolled back at the end, so it is safe to run against the live database and while the live job runs.

    --check-store --since <UTC time>     the first issuing run after <UTC time>, per city

It needs SUPABASE_DB_URL (the writer connection; it can read `public.day_ahead_forecast` and
`public.pipeline_run` before the table is exposed to the public key). Keep it in the git-ignored
.env: it is loaded from there only when this file is run as a script, never when imported. The
URL, host, user and project reference are never printed and never written to the JSON evidence.

Run it from the repository root, with the time just before you pushed (an ISO time with a `Z` or a
UTC offset, for example 2026-11-09T00:00:00Z):

    PYTHONPATH=backend .venv/bin/python backend/day_ahead_verify.py --check-store \\
        --since 2026-11-09T00:00:00Z --json-out day_ahead_first_slot.json

For each city the first issuing run is the run that wrote the city's earliest `issued_at` at or
after --since. Every row it wrote is judged by these named checks (one PASS or FAIL line each; a
FAIL line names the city and target):

  first_run_found                    every city has a row written since --since
  first_run_covers_every_due_target  every target that was due at the run's decision time has a
                                     row (up to 3 per city, 12 in all: `due_targets(issued_at)`)
  label_is_the_d11_label             the D-11 label on every row
  method_horizon_and_weather_run     ml_cooling_corrected, horizon 1440, and the weather run
                                     initialised exactly 24 h before the target
  band_is_the_test_split_artifact    band_source test-split (the launch band), 196 residuals, and the
                                     band artifact's sha256 equal to the live manifest entry
  cooling_model_matches_the_manifest the cooling model sha256 equals the manifest entry of the file
                                     that city serves, and the source is refit only for refit cities
  config_identity_matches_the_code   the config fingerprint and version are the code's own
  band_brackets_the_value            lower <= value <= upper
  issue_lead_at_most_18h             0 < target - issued_at <= 18 h (a target further out was not due)
  pipeline_run_records_the_stage     the run's `pipeline_run.day_ahead` record exists and its
                                     per-city `issued` list equals the rows the run wrote

Together the coverage and lead checks say the run wrote exactly the due targets: a missing due
target fails the coverage check, a row for a target that was not yet due fails the lead check.

"24 h" is the age of the weather run, not the lead from the moment of issue: a row is issued 0 to
18 h before its target.

Exit codes: 0 every check passed, 1 a check failed (including a database that cannot be reached),
2 configuration (SUPABASE_DB_URL missing, a bad --since, an unreadable manifest).
The JSON report is {checks, rows, since, exit_code}; every text in it passes through
supabase_store.redact. Nothing here is run against the live project by the build; that is the
owner's step in 08-08.

    --check-rest                         the exposed objects, read as a consumer (08-10, D-12, D-17)

After the owner applies the expose migration (08-11) this proves, with only the publishable key in the
`apikey` header, what a dashboard or a PSS/E script sees. It reads SUPABASE_URL and
SUPABASE_PUBLISHABLE_KEY from the environment, refuses a secret key or a service_role token before any
request, and prints and stores no URL, host, project reference or key: every printed line and every
text in the JSON passes through supabase_rest.redact_rest.

  rest_upcoming_rows_are_future_and_ordered   day_ahead_upcoming has rows, every target is in the future
                                              on the 00/06/12/18 UTC grid, ordered by city then time
  rest_upcoming_columns_match_the_contract    every row has exactly UPCOMING_COLUMNS, in order
  rest_status_has_four_cities_none_late       day_ahead_status has the four cities, STATUS_COLUMNS, none late
  rest_table_is_readable                      day_ahead_forecast answers with a row and TABLE_COLUMNS
  rest_assert_fresh_ok_and_armed              rpc/assert_fresh answers 200 and day_ahead_armed is true
  rest_anon_insert_into_table_refused         one sentinel insert (AUSTIN, 2000-01-01T00:00:00Z) is refused
                                              by privilege (401/403, 42501 permission denied)
  rest_anon_write_to_upcoming_view_refused    a write to the view's year-2000 key is refused
  rest_pipeline_run_hidden                    the run log is not readable with the public key

The two write probes name keys in the year 2000, outside any real target, so even an accepted write
could not change a published value. If the insert is ever accepted the report prints the SQL that
deletes exactly that sentinel row, for the owner to run on the admin connection: this script never
deletes or retries anything. Exit codes as above (2: SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY missing
or unsafe; no request is made). Run it from the repository root with the two values in the shell:

    PYTHONPATH=backend .venv/bin/python backend/day_ahead_verify.py --check-rest --json-out <FILE>
"""

import argparse
import json
import os
import sys
from collections import namedtuple
from datetime import datetime, timezone
from urllib.parse import unquote, urlsplit

import pandas as pd

import config
import day_ahead_band
import day_ahead_contract as contract
import day_ahead_forecast
import dlr_live_check_models
import e2e_verify_readonly
import supabase_rest
import supabase_store

CheckResult = namedtuple("CheckResult", ["name", "ok", "detail"])

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(REPO_ROOT, dlr_live_check_models.MANIFEST_PATH)

# D-12 and the research: a target is issued 0 to 18 h before it is due (24 h weather age minus the
# 6 h publication lag).
MAX_LEAD = pd.Timedelta(hours=18)
WEATHER_RUN_AGE = pd.Timedelta(minutes=contract.HORIZON_MINUTES)
# The launch band is built from the TEST split's residuals: 196 per city and target hour.
TEST_BAND_N = 196

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
_DB_URL_NAMES = ("SUPABASE_DB_URL", "SUPABASE_ADMIN_DB_URL")

CHECK_NAMES = (
    "first_run_found",
    "first_run_covers_every_due_target",
    "label_is_the_d11_label",
    "method_horizon_and_weather_run",
    "band_is_the_test_split_artifact",
    "cooling_model_matches_the_manifest",
    "config_identity_matches_the_code",
    "band_brackets_the_value",
    "issue_lead_at_most_18h",
    "pipeline_run_records_the_stage",
)

REST_CHECK_NAMES = (
    "rest_upcoming_rows_are_future_and_ordered",
    "rest_upcoming_columns_match_the_contract",
    "rest_status_has_four_cities_none_late",
    "rest_table_is_readable",
    "rest_assert_fresh_ok_and_armed",
    "rest_anon_insert_into_table_refused",
    "rest_anon_write_to_upcoming_view_refused",
    "rest_pipeline_run_hidden",
)

# The write probes name this key in the year 2000: never a real target, never shown by the upcoming
# view (which lists future targets only), so an accepted write could not change a published value.
REST_SENTINEL_CITY = "AUSTIN"
REST_SENTINEL_VALID_TIME = "2000-01-01T00:00:00Z"
REST_SENTINEL_RUN_ID = "day-ahead-rest-sentinel"
# The view filters on the server's clock; this much clock difference between the owner's machine and
# the server is not a failure.
REST_PAST_TOLERANCE = pd.Timedelta(minutes=2)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _iso(value) -> str:
    return _utc(value).strftime(_TS_FMT)


def _secrets() -> list:
    """Everything in the connection URLs that names the project: the URL, password, host, user, reference."""
    found = []
    for name in _DB_URL_NAMES:
        url = os.environ.get(name)
        if not url or not url.strip():
            continue
        url = url.strip()
        found.append(url)
        try:
            parts = urlsplit(url)
            password, host, user = parts.password, parts.hostname, parts.username
        except ValueError:
            continue
        if password:
            found.extend([password, unquote(password)])
        if host and len(host) >= 3:
            found.append(host)
        if user:
            user = unquote(user)
            if "." in user:
                found.append(user)
                found.append(user.split(".", 1)[1])
    return found


def _clean(text) -> str:
    """Text with every connection secret removed; the cut is made after redaction (limit is large)."""
    return supabase_store.redact(text, _secrets(), limit=10 ** 9)


def _clean_object(value, clean=None):
    """Every string in a JSON-ready structure, redacted, so a value never survives inside the file."""
    clean = clean or _clean
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, list):
        return [_clean_object(v, clean) for v in value]
    if isinstance(value, dict):
        return {k: _clean_object(v, clean) for k, v in value.items()}
    return value


def parse_since(text) -> datetime:
    """An ISO time with a `Z` or a UTC offset, as an aware UTC datetime. ValueError otherwise."""
    value = str(text).strip()
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("--since needs a UTC offset or a trailing Z, for example 2026-11-09T00:00:00Z")
    return parsed.astimezone(timezone.utc)


def _list_text(items, limit=6) -> str:
    items = list(items)
    shown = ", ".join(items[:limit])
    return shown + (f" (+{len(items) - limit} more)" if len(items) > limit else "")


# ---------------------------------------------------------------------------
# reading the store (one read-only transaction)
# ---------------------------------------------------------------------------


def fetch(conn, since):
    """
    (rows, runs): every `day_ahead_forecast` row written at or after `since` (dicts with exactly
    `contract.TABLE_COLUMNS`) and `{run_id: pipeline_run.day_ahead}` for the run ids found. Reads only.
    """
    from psycopg.rows import dict_row

    columns = ", ".join(contract.TABLE_COLUMNS)
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"select {columns} from {contract.TABLE} where first_written_at >= %(since)s "
            "order by city, issued_at, valid_time",
            {"since": since},
        )
        rows = cur.fetchall()
    run_ids = sorted({row["run_id"] for row in rows})
    runs = {}
    if run_ids:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("select run_id, day_ahead from public.pipeline_run where run_id = any(%(ids)s)",
                        {"ids": run_ids})
            runs = {rec["run_id"]: rec["day_ahead"] for rec in cur.fetchall()}
    return rows, runs


# ---------------------------------------------------------------------------
# the checks (pure)
# ---------------------------------------------------------------------------


def first_runs(rows) -> dict:
    """
    {city: [rows of the city's first issue]}: the rows carrying the city's earliest `issued_at`
    (one run issues all its targets with its own decision time), earliest target first.
    """
    by_city = {}
    for row in rows:
        by_city.setdefault(row["city"], []).append(row)
    first = {}
    for city, city_rows in by_city.items():
        city_rows = sorted(city_rows, key=lambda r: (_utc(r["issued_at"]), _utc(r["valid_time"])))
        head = city_rows[0]
        first[city] = [r for r in city_rows
                       if _utc(r["issued_at"]) == _utc(head["issued_at"]) and r["run_id"] == head["run_id"]]
    return first


def _where(row) -> str:
    return f"{row['city']} {_iso(row['valid_time'])}"


def _report(problems, ok_text):
    return (False, _list_text(problems)) if problems else (True, ok_text)


def evaluate(rows, runs, manifest) -> list:
    """
    The ten named checks over the rows read from the store. `rows` as returned by `fetch`, `runs`
    `{run_id: pipeline_run.day_ahead or None}`, `manifest` `{path: sha256}` of the live manifest.
    Returns CheckResult tuples in CHECK_NAMES order.
    """
    first = first_runs(rows)
    results = []

    def add(name, ok, detail):
        results.append(CheckResult(name, ok, detail))

    missing_cities = [city for city in config.LOCATIONS if city not in first]
    if missing_cities:
        add("first_run_found", False, "no row written since --since for " + ", ".join(missing_cities))
    else:
        add("first_run_found", True, "a first run for every city: " + ", ".join(
            f"{city} {first[city][0]['run_id']}" for city in config.LOCATIONS))

    cities = [city for city in config.LOCATIONS if city in first]
    refit = day_ahead_forecast.refit_cities()
    band_key = dlr_live_check_models._key(day_ahead_band.BAND_ARTIFACT_PATH)
    band_sha = manifest.get(band_key)

    def run_rows():
        for city in cities:
            for row in first[city]:
                yield row

    def per_row(predicate, ok_text):
        problems = []
        for row in run_rows():
            reason = predicate(row)
            if reason:
                problems.append(f"{_where(row)} {reason}")
        return _report(problems, ok_text)

    def judged(name, outcome):
        if not cities:
            add(name, False, "no first run to check")
        else:
            add(name, *outcome)

    # first_run_covers_every_due_target
    problems = []
    for city in cities:
        decision = _utc(first[city][0]["issued_at"])
        stored = {_utc(r["valid_time"]) for r in first[city]}
        absent = [t for t in day_ahead_forecast.due_targets(decision) if _utc(t) not in stored]
        if absent:
            problems.append(f"{city} decided {_iso(decision)}, no row for " + ", ".join(_iso(t) for t in absent))
    total = sum(len(first[city]) for city in cities)
    judged("first_run_covers_every_due_target",
           _report(problems, f"{total} rows cover every target due at the decision time"))

    judged("label_is_the_d11_label", per_row(
        lambda r: None if r["label"] == contract.DAY_AHEAD_LABEL else "carries another label",
        "every row carries the D-11 label"))

    judged("method_horizon_and_weather_run", per_row(
        lambda r: (None if (r["forecast_method"] == contract.FORECAST_METHOD
                            and r["horizon_minutes"] == contract.HORIZON_MINUTES
                            and _utc(r["forecast_run_init_time"]) == _utc(r["valid_time"]) - WEATHER_RUN_AGE)
                   else "method, horizon or weather run init differs"),
        "ml_cooling_corrected, horizon 1440, weather run 24 h before the target"))

    def band_problem(row):
        if row["band_source"] != "test-split":
            return f"band_source is {row['band_source']}, not test-split"
        if row["band_n"] != TEST_BAND_N:
            return f"band_n is {row['band_n']}, not {TEST_BAND_N}"
        if band_sha is None:
            return "the manifest has no entry for the band artifact"
        if row["band_artifact_sha256"] != band_sha:
            return "band artifact sha256 is not the manifest entry"
        return None

    judged("band_is_the_test_split_artifact", per_row(
        band_problem, f"test-split, {TEST_BAND_N} residuals, band artifact sha256 equals the manifest entry"))

    def cooling_problem(row):
        city = row["city"]
        expected = manifest.get(dlr_live_check_models._key(day_ahead_forecast.serving_model_path(city)))
        if expected is None:
            return "the manifest has no entry for the served cooling model"
        if row["cooling_model_sha256"] != expected:
            return "cooling model sha256 is not the served file's manifest entry"
        source = "refit" if city in refit else "frozen"
        if row["cooling_model_source"] != source:
            return f"cooling model source is {row['cooling_model_source']}, expected {source}"
        return None

    judged("cooling_model_matches_the_manifest", per_row(
        cooling_problem, "cooling model sha256 equals the served file's manifest entry, source as expected"))

    judged("config_identity_matches_the_code", per_row(
        lambda r: (None if (r["config_fingerprint"] == supabase_store.rating_config_fingerprint(r["city"])
                            and r["config_version"] == config.RATING_CONFIG_VERSION)
                   else "config fingerprint or version is not the code's"),
        f"config fingerprint and version equal the code's ({config.RATING_CONFIG_VERSION})"))

    judged("band_brackets_the_value", per_row(
        lambda r: (None if r["forecast_ci_lower_amps"] <= r["forecast_amps"] <= r["forecast_ci_upper_amps"]
                   else "the band does not bracket the value"),
        "lower <= value <= upper on every row"))

    def lead_problem(row):
        lead = _utc(row["valid_time"]) - _utc(row["issued_at"])
        if lead <= pd.Timedelta(0) or lead > MAX_LEAD:
            return f"issue lead is {lead}, outside (0, 18 h]"
        return None

    judged("issue_lead_at_most_18h", per_row(lead_problem, "every row was issued 0 to 18 h before its target"))

    # pipeline_run_records_the_stage
    problems = []
    for city in cities:
        run_id = first[city][0]["run_id"]
        record = runs.get(run_id)
        entry = record.get("cities", {}).get(city) if isinstance(record, dict) and isinstance(
            record.get("cities"), dict) else None
        if not isinstance(entry, dict):
            problems.append(f"{city} run {run_id} has no pipeline_run.day_ahead record")
            continue
        issued = entry.get("issued")
        stored = {_iso(r["valid_time"]) for r in first[city]}
        if not isinstance(issued, list) or set(map(str, issued)) != stored:
            problems.append(f"{city} run {run_id}: the recorded issued list differs from the stored rows")
    judged("pipeline_run_records_the_stage", _report(
        problems, "every first run has a pipeline_run.day_ahead record whose issued list equals its rows"))
    return results


# ---------------------------------------------------------------------------
# --check-rest: the exposed objects as a consumer sees them (08-10)
# ---------------------------------------------------------------------------


def _sentinel_row() -> dict:
    """A complete, constraint-valid row at the sentinel key, so a wrongly granted INSERT would succeed."""
    zeros = "0" * 64
    values = {
        "city": REST_SENTINEL_CITY,
        "valid_time": REST_SENTINEL_VALID_TIME,
        "issued_at": "1999-12-31T12:00:00Z",
        "forecast_run_init_time": "1999-12-31T00:00:00Z",
        "horizon_minutes": contract.HORIZON_MINUTES,
        "forecast_amps": 1000.0,
        "forecast_ci_lower_amps": 900.0,
        "forecast_ci_upper_amps": 1100.0,
        "band_source": "test-split",
        "band_n": 1,
        "band_pairs_through": None,
        "band_artifact_sha256": zeros,
        "forecast_method": contract.FORECAST_METHOD,
        "cooling_model_sha256": zeros,
        "cooling_model_source": "frozen",
        "anchor_observation_time": "1999-12-31T11:55:00Z",
        "anchor_source": "sentinel",
        "label": contract.DAY_AHEAD_LABEL,
        "config_version": "sentinel",
        "config_fingerprint": zeros,
        "run_id": REST_SENTINEL_RUN_ID,
        "run_attempt": 1,
        "pipeline_version": "sentinel",
        "schema_version": 1,
    }
    return {column: values[column] for column in contract.INSERT_COLUMNS}


def _rest_failure(name, exc, cfg):
    return CheckResult(name, False, supabase_rest.redact_rest(str(exc), cfg, limit=None))


def _answer_text(response, cfg):
    """A short redacted description of an unexpected answer, with PostgREST's `details` when it has one."""
    text = supabase_rest.brief(response, cfg)
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("details"):
        text += " details=" + supabase_rest.redact_rest(str(body["details"]), cfg, limit=300)
    return text


def _column_problem(row, expected):
    keys = list(row) if isinstance(row, dict) else []
    if keys == list(expected):
        return None
    missing = [c for c in expected if c not in keys]
    extra = [c for c in keys if c not in expected]
    if missing or extra:
        return "missing %s, extra %s" % (", ".join(missing) or "none", ", ".join(extra) or "none")
    return "the columns are in another order"


def _check_upcoming_rows(rows, now):
    name = "rest_upcoming_rows_are_future_and_ordered"
    if not rows:
        return CheckResult(name, False, "day_ahead_upcoming returned no rows, so nothing was checked "
                                        "(is the day-ahead feed stalled?)")
    problems, keys = [], []
    for row in rows:
        city = str(row.get("city")) if isinstance(row, dict) else "?"
        try:
            valid = _utc(supabase_rest.parse_ts(row["valid_time"]))
        except (KeyError, TypeError, ValueError):
            problems.append("%s has no readable valid_time" % city)
            continue
        keys.append((city, valid))
        if valid <= _utc(now) - REST_PAST_TOLERANCE:
            problems.append("%s %s is in the past" % (city, _iso(valid)))
        elif valid.hour not in contract.TARGET_HOURS_UTC or valid.minute or valid.second:
            problems.append("%s %s is not a 00/06/12/18 UTC target" % (city, _iso(valid)))
    if keys != sorted(keys):
        problems.append("the rows are not ordered by city then valid_time")
    if problems:
        return CheckResult(name, False, _list_text(problems))
    return CheckResult(name, True, "%d rows, every target in the future, ordered by city then valid_time" % len(rows))


def _check_upcoming_columns(rows):
    name = "rest_upcoming_columns_match_the_contract"
    if not rows:
        return CheckResult(name, False, "day_ahead_upcoming returned no rows, so there is nothing to compare")
    problems = []
    for index, row in enumerate(rows):
        problem = _column_problem(row, contract.UPCOMING_COLUMNS)
        if problem:
            where = "%s %s" % (row.get("city"), row.get("valid_time")) if isinstance(row, dict) else "row %d" % index
            problems.append("%s: %s" % (where, problem))
    if problems:
        return CheckResult(name, False, _list_text(problems))
    return CheckResult(name, True, "every row has exactly the %d contract columns, in order"
                       % len(contract.UPCOMING_COLUMNS))


def _check_status(rows):
    name = "rest_status_has_four_cities_none_late"
    problems = []
    cities = sorted(str(r.get("city")) for r in rows if isinstance(r, dict))
    if len(rows) != len(config.LOCATIONS) or cities != sorted(config.LOCATIONS):
        problems.append("expected one row for each of %s, got %s" % (", ".join(sorted(config.LOCATIONS)),
                                                                    ", ".join(cities) or "none"))
    for row in rows:
        problem = _column_problem(row, contract.STATUS_COLUMNS)
        if problem:
            problems.append("%s: %s" % (row.get("city") if isinstance(row, dict) else "?", problem))
        elif row["is_late"] is not False:
            late = row.get("missing_targets")
            problems.append("%s is late, missing %s" % (row["city"], ", ".join(map(str, late)) if late else "?"))
    if problems:
        return CheckResult(name, False, _list_text(problems))
    return CheckResult(name, True, "four cities, the %d contract columns, none late" % len(contract.STATUS_COLUMNS))


def _check_table(cfg, opener):
    name = "rest_table_is_readable"
    try:
        response = supabase_rest.request(
            cfg, "GET", "day_ahead_forecast",
            [("select", "*"), ("order", "valid_time.desc,city.asc"), ("limit", "1")], opener=opener)
    except supabase_rest.RestError as exc:
        return _rest_failure(name, exc, cfg)
    if response.status != 200:
        return CheckResult(name, False, "day_ahead_forecast answered %s" % _answer_text(response, cfg))
    try:
        rows = response.json()
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        return CheckResult(name, False, "day_ahead_forecast did not answer with a list of rows")
    if not rows:
        return CheckResult(name, False, "day_ahead_forecast answered 200 with no rows: the table is empty, or the "
                                        "public read policy is missing")
    problem = _column_problem(rows[0], contract.TABLE_COLUMNS)
    if problem:
        return CheckResult(name, False, "the table's columns differ from the contract: " + problem)
    return CheckResult(name, True, "readable, the %d contract columns, newest target %s" % (
        len(contract.TABLE_COLUMNS), rows[0].get("valid_time")))


def _check_assert_fresh(cfg, opener):
    name = "rest_assert_fresh_ok_and_armed"
    try:
        response = supabase_rest.request(cfg, "GET", "rpc/assert_fresh", opener=opener)
    except supabase_rest.RestError as exc:
        return _rest_failure(name, exc, cfg)
    if response.status != 200:
        return CheckResult(name, False, "rpc/assert_fresh answered %s" % _answer_text(response, cfg))
    try:
        body = response.json()
    except ValueError:
        body = None
    if not isinstance(body, dict) or body.get("ok") is not True:
        return CheckResult(name, False, "rpc/assert_fresh answered 200 without ok true")
    if body.get("day_ahead_armed") is not True:
        return CheckResult(name, False, "day_ahead_armed is %s: the day-ahead alarm clause is not armed (no value "
                                        "stored, or the expose migration is not the current one)"
                           % ("missing" if "day_ahead_armed" not in body else str(body["day_ahead_armed"]).lower()))
    return CheckResult(name, True, "HTTP 200, ok true, day_ahead_armed true")


def _write_probe(cfg, opener, name, method, path, params, body, classify, attempts):
    """One write attempt with the public key: (refused, detail, accepted). Redacted."""
    try:
        response = supabase_rest.request(cfg, method, path, params, headers={"Prefer": "return=minimal"},
                                         body=body, opener=opener)
    except supabase_rest.RestError as exc:
        attempts.append({"name": name, "method": method, "path": path, "status": None, "code": None,
                         "verdict": "fail"})
        return False, supabase_rest.redact_rest(str(exc), cfg, limit=None), False
    ok, detail, code = classify(response)
    attempts.append({"name": name, "method": method, "path": path, "status": response.status, "code": code,
                     "verdict": "pass" if ok else "fail"})
    return ok, detail, detail.startswith("write accepted")


def _check_hidden(cfg, opener):
    name = "rest_pipeline_run_hidden"
    try:
        response = supabase_rest.request(cfg, "GET", "pipeline_run", [("select", "*"), ("limit", "1")], opener=opener)
    except supabase_rest.RestError as exc:
        return _rest_failure(name, exc, cfg)
    if 200 <= response.status < 300:
        return CheckResult(name, False, "public.pipeline_run is readable by the public key (HTTP %d)" % response.status)
    cause = e2e_verify_readonly._hidden_cause(response)
    if cause:
        return CheckResult(name, True, "not readable (%s)" % cause)
    return CheckResult(name, False, "inconclusive: %s" % supabase_rest.brief(response, cfg))


def _recovery_lines(accepted) -> list:
    """The owner's recovery steps for an accepted write probe. Printed, never executed."""
    return [
        "RECOVERY (owner only, on the admin connection; this script executed none of these statements)",
        "  Why: the public key was allowed to write (accepted: " + ", ".join(accepted) + ")",
        "  1. Remove the sentinel row if it was stored:",
        "     delete from public.day_ahead_forecast where city = '%s' and valid_time = '%s';" % (
            REST_SENTINEL_CITY, REST_SENTINEL_VALID_TIME),
        "  2. Remove the grant that let the write through, then run --check-rest again:",
        "     revoke insert, update, delete, truncate on public.day_ahead_forecast, public.day_ahead_upcoming,"
        " public.day_ahead_status from anon, authenticated;",
    ]


def check_rest(cfg, opener=None, now=None, lines=None, attempts=None) -> list:
    """The eight consumer-side checks of the exposed day-ahead objects (D-12, D-17)."""
    now = now or datetime.now(timezone.utc)
    attempts = attempts if attempts is not None else []
    results = []

    try:
        upcoming = supabase_rest.get_all(cfg, "day_ahead_upcoming", [("select", "*")], "city.asc,valid_time.asc",
                                         opener=opener)
    except supabase_rest.RestError as exc:
        results.append(_rest_failure(REST_CHECK_NAMES[0], exc, cfg))
        results.append(_rest_failure(REST_CHECK_NAMES[1], exc, cfg))
    else:
        results.append(_check_upcoming_rows(upcoming, now))
        results.append(_check_upcoming_columns(upcoming))

    try:
        status_rows = supabase_rest.get_all(cfg, "day_ahead_status", [("select", "*")], "city.asc", opener=opener)
    except supabase_rest.RestError as exc:
        results.append(_rest_failure(REST_CHECK_NAMES[2], exc, cfg))
    else:
        results.append(_check_status(status_rows))

    results.append(_check_table(cfg, opener))
    results.append(_check_assert_fresh(cfg, opener))

    accepted = []
    ok, detail, was_accepted = _write_probe(
        cfg, opener, "anon_insert_into_table", "POST", "day_ahead_forecast", None, _sentinel_row(),
        e2e_verify_readonly._classify_table_write, attempts)
    results.append(CheckResult(REST_CHECK_NAMES[5], ok, detail))
    if was_accepted:
        accepted.append("insert into day_ahead_forecast")
    key_filter = [("city", "eq." + REST_SENTINEL_CITY), ("valid_time", "eq." + REST_SENTINEL_VALID_TIME)]
    ok, detail, was_accepted = _write_probe(
        cfg, opener, "anon_write_to_upcoming_view", "PATCH", "day_ahead_upcoming", key_filter,
        {"forecast_amps": 1.0}, e2e_verify_readonly._classify_view_write, attempts)
    results.append(CheckResult(REST_CHECK_NAMES[6], ok, detail))
    if was_accepted:
        accepted.append("write to day_ahead_upcoming")

    results.append(_check_hidden(cfg, opener))
    if accepted and lines is not None:
        lines.extend(_recovery_lines(accepted))
    return results


def _run_rest(args, opener, now) -> int:
    try:
        cfg = supabase_rest.config_from_env()
    except supabase_rest.ConfigError as exc:
        print(supabase_rest.redact_rest(str(exc)), file=sys.stderr)
        return 2

    def clean(text):
        return supabase_rest.redact_rest(text, cfg, limit=None)

    lines, attempts = [], []
    results = check_rest(cfg, opener=opener, now=now, lines=lines, attempts=attempts)
    for result in results:
        print(clean("%s %s: %s" % ("PASS" if result.ok else "FAIL", result.name, result.detail)))
    for line in lines:
        print(clean(line))
    failed = [r.name for r in results if not r.ok]
    code = 1 if failed else 0
    print("DAY-AHEAD REST OK" if not failed else "DAY-AHEAD REST FAILED: " + ", ".join(failed))
    if args.json_out:
        _write_report(args.json_out, {
            "checks": [{"name": r.name, "ok": r.ok, "detail": r.detail} for r in results],
            "attempts": attempts,
            "exit_code": code,
        }, clean)
    return code


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def _row_line(row) -> str:
    return "%s  valid %s  issued %s  %.1f A  [%.1f, %.1f]  %s" % (
        row["city"], _iso(row["valid_time"]), _iso(row["issued_at"]), row["forecast_amps"],
        row["forecast_ci_lower_amps"], row["forecast_ci_upper_amps"], row["band_source"])


def _row_json(row) -> dict:
    out = {}
    for key, value in row.items():
        out[key] = _iso(value) if isinstance(value, (datetime, pd.Timestamp)) else value
    return out


def _write_report(path, report, clean=None):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_clean_object(report, clean), indent=2) + "\n")


def _finish(results, rows, since, json_out) -> int:
    for result in results:
        print(_clean("%s %s: %s" % ("PASS" if result.ok else "FAIL", result.name, result.detail)))
    failed = [r.name for r in results if not r.ok]
    code = 1 if failed else 0
    print("DAY-AHEAD FIRST SLOT OK" if not failed else "DAY-AHEAD FIRST SLOT FAILED: " + ", ".join(failed))
    if json_out:
        _write_report(json_out, {
            "checks": [{"name": r.name, "ok": r.ok, "detail": r.detail} for r in results],
            "rows": [_row_json(row) for row in rows],
            "since": _iso(since),
            "exit_code": code,
        })
    return code


def main(argv=None, manifest_path=None, opener=None, now=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the day-ahead forecast: the first issuing run (--check-store, read-only, writer "
                    "connection) or the exposed objects as a consumer (--check-rest, publishable key).")
    parser.add_argument("--check-store", action="store_true",
                        help="read the live write side (read-only) and check the first issuing run")
    parser.add_argument("--check-rest", action="store_true",
                        help="read the exposed day-ahead objects with the publishable key and prove the public "
                             "key cannot write (sends one sentinel insert and one view write, both expected to "
                             "be refused)")
    parser.add_argument("--since", default=None,
                        help="ISO time (UTC, with Z or an offset): judge the first issuing run at or after it")
    parser.add_argument("--json-out", default=None, help="write the check results JSON here")
    args = parser.parse_args(argv)

    if args.check_rest and args.check_store:
        print("--check-store and --check-rest are separate runs (one needs SUPABASE_DB_URL, the other the "
              "publishable key): run them one at a time", file=sys.stderr)
        return 2
    if args.check_rest:
        return _run_rest(args, opener, now)
    if not args.check_store:
        print("nothing to do: pass --check-store or --check-rest", file=sys.stderr)
        return 2
    if args.since is None:
        print("--since is required with --check-store", file=sys.stderr)
        return 2
    try:
        since = parse_since(args.since)
    except ValueError as exc:
        print(_clean("bad --since: %s" % exc), file=sys.stderr)
        return 2
    manifest_file = manifest_path or DEFAULT_MANIFEST
    try:
        manifest = dlr_live_check_models.read_manifest(manifest_file)
    except (OSError, ValueError) as exc:
        print(_clean("cannot read the live manifest %s: %s" % (
            dlr_live_check_models.MANIFEST_PATH.replace(os.sep, "/"), type(exc).__name__)), file=sys.stderr)
        return 2
    url = os.environ.get("SUPABASE_DB_URL")
    if url is None or not url.strip():
        print("SUPABASE_DB_URL is not set (put it in the git-ignored .env or export it)", file=sys.stderr)
        return 2

    conn = None
    try:
        conn = supabase_store.connect()
        supabase_store.begin_read_only(conn)
        rows, runs = fetch(conn, since)
    except Exception as exc:  # noqa: BLE001 - reported as a failed check, redacted
        results = [CheckResult("database_read", False, "%s: %s" % (type(exc).__name__, exc))]
        return _finish(results, [], since, args.json_out)
    finally:
        if conn is not None:
            try:
                conn.rollback()
                conn.close()
            except Exception:  # noqa: BLE001 - nothing was written; closing is best effort
                pass

    results = evaluate(rows, runs, manifest)
    print("Day-ahead first-slot check since %s: %d rows" % (_iso(since), len(rows)))
    first = first_runs(rows)
    for city in config.LOCATIONS:
        for row in first.get(city, []):
            print(_clean(_row_line(row)))
    return _finish(results, [row for city in config.LOCATIONS for row in first.get(city, [])], since,
                   args.json_out)


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
