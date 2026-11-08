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


def _clean_object(value):
    """Every string in a JSON-ready structure, redacted, so a value never survives inside the file."""
    if isinstance(value, str):
        return _clean(value)
    if isinstance(value, list):
        return [_clean_object(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean_object(v) for k, v in value.items()}
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


def _write_report(path, report):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(_clean_object(report), indent=2) + "\n")


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


def main(argv=None, manifest_path=None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only check that the first issuing day-ahead run wrote every due target correctly.")
    parser.add_argument("--check-store", action="store_true",
                        help="read the live write side (read-only) and check the first issuing run")
    parser.add_argument("--since", default=None,
                        help="ISO time (UTC, with Z or an offset): judge the first issuing run at or after it")
    parser.add_argument("--json-out", default=None, help="write the check results JSON here")
    args = parser.parse_args(argv)

    if not args.check_store:
        print("nothing to do: pass --check-store", file=sys.stderr)
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
