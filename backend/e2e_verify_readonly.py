"""
Read-only exposure checks, run as a consumer (production-pipeline Phase 6: API-01)
===================================================================================
One-command check of the public REST interface, made the way the dashboard and the PSS/E
scripts see it: with the publishable key only, in the `apikey` header only. It reads
SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY from the environment (D-10), refuses a secret key
or a service_role token before any request, and prints no URL, host, project reference or
key: every printed line, error and evidence file passes through supabase_rest.redact_rest.

--check-read (on by default) proves, in plain English: "a person with only the public key
sees exactly one current rating per city, with the documented columns."

  latest_rating_readable     GET /rest/v1/latest_rating answers 200 with a list of rows
  latest_rating_four_cities  exactly four rows, one per config.LOCATIONS city, no repeats
  latest_rating_columns      every row has exactly latest_rating_contract.LATEST_COLUMNS, in order
  latest_rating_values       rating_amps is a number above 0; valid_time is on a whole hour
  latest_rating_flags        is_stale equals age_minutes > 90 and is_provisional equals the
                             word rule on rating_basis / config_version (D-02, D-03)
  latest_rating_count_exact  `Prefer: count=exact` reports the same four rows
  city_rating_readable       the history table is readable with the public key
  keyless_request_refused    a request with no key is refused (401 or 403)
  assert_fresh_answers       rpc/assert_fresh answers 200, or 503 with code PT503

--check-hidden (on by default) proves: "the private run log and the soak log cannot be read
with the public key." public.pipeline_run and ops.freshness_log (Accept-Profile: ops) must
answer 401, 403, 404 or 406. Any 2xx, even an empty list, fails as "readable by the public key".

The per-city lines (city, valid_time, age_minutes, is_stale, status, rating_amps,
is_provisional) are printed so the owner can read the answer, not just the verdict.

Exit codes: 0 every check passed, 1 a check failed, 2 SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY
is missing, or the key is a secret key or a service_role token (no request is made).

The owner runs it from the repository root with the two values in the shell environment:

    export SUPABASE_URL=... SUPABASE_PUBLISHABLE_KEY=...
    PYTHONPATH=backend .venv/bin/python backend/e2e_verify_readonly.py --check-read --check-hidden

Nothing here is run against the live project by the build; that is the owner's step in 06-09.
"""

import argparse
import json
import math
import os
import sys
from collections import namedtuple

import config
import latest_rating_contract
import supabase_rest

CheckResult = namedtuple("CheckResult", ["name", "ok", "detail"])

EXPECTED_CITIES = config.LOCATIONS
HIDDEN_TARGETS = (("public", "pipeline_run"), ("ops", "freshness_log"))
HIDDEN_OK_STATUSES = (401, 403, 404, 406)
KEYLESS_OK_STATUSES = (401, 403)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fail_text(exc, cfg):
    return supabase_rest.redact_rest(str(exc), cfg)


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _city_of(row):
    return str(row.get("city")) if isinstance(row, dict) else "?"


def _joined(problems, ok_text):
    return ("; ".join(problems), False) if problems else (ok_text, True)


# ---------------------------------------------------------------------------
# --check-read
# ---------------------------------------------------------------------------


def _read_latest(cfg, opener, results):
    """GET latest_rating; adds the `latest_rating_readable` result and returns the rows or None."""
    try:
        response = supabase_rest.request(
            cfg, "GET", "latest_rating", [("select", "*"), ("order", "city.asc")], opener=opener)
    except supabase_rest.RestError as exc:
        results.append(CheckResult("latest_rating_readable", False, _fail_text(exc, cfg)))
        return None
    if response.status != 200:
        results.append(CheckResult("latest_rating_readable", False,
                                   "latest_rating answered %s" % supabase_rest.brief(response, cfg)))
        return None
    try:
        rows = response.json()
    except ValueError:
        rows = None
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        results.append(CheckResult("latest_rating_readable", False, "latest_rating did not answer with a list of rows"))
        return None
    results.append(CheckResult("latest_rating_readable", True, "HTTP 200, %d rows" % len(rows)))
    return rows


def _check_cities(rows):
    problems = []
    if len(rows) != len(EXPECTED_CITIES):
        problems.append("%d rows, expected %d (one per city)" % (len(rows), len(EXPECTED_CITIES)))
    cities = [r.get("city") for r in rows]
    for city in sorted({c for c in cities if cities.count(c) > 1}, key=str):
        problems.append("duplicate city %s" % city)
    for city in cities:
        if city not in EXPECTED_CITIES:
            problems.append("unknown city %s" % city)
    for city in EXPECTED_CITIES:
        if city not in cities:
            problems.append("missing city %s" % city)
    detail, ok = _joined(problems, "%d rows, one per city: %s" % (len(rows), ", ".join(EXPECTED_CITIES)))
    return CheckResult("latest_rating_four_cities", ok, detail)


def _check_columns(rows):
    expected = list(latest_rating_contract.LATEST_COLUMNS)
    problems = []
    for row in rows:
        keys = list(row)
        if keys == expected:
            continue
        missing = [c for c in expected if c not in keys]
        extra = [k for k in keys if k not in expected]
        if missing:
            problems.append("%s: missing columns %s" % (_city_of(row), ", ".join(missing)))
        if extra:
            problems.append("%s: extra columns %s" % (_city_of(row), ", ".join(str(k) for k in extra)))
        if not missing and not extra:
            problems.append("%s: columns out of order" % _city_of(row))
    detail, ok = _joined(problems, "%d columns in the published order on every row" % len(expected))
    return CheckResult("latest_rating_columns", ok, detail)


def _check_values(rows):
    problems = []
    for row in rows:
        city = _city_of(row)
        amps = row.get("rating_amps")
        if not _is_number(amps) or not math.isfinite(amps) or amps <= 0:
            problems.append("%s: rating_amps must be a number above 0 (got %r)" % (city, amps))
        valid_time = row.get("valid_time")
        try:
            stamp = supabase_rest.parse_ts(valid_time)
        except ValueError:
            problems.append("%s: valid_time is not a timestamp (got %r)" % (city, valid_time))
            continue
        if (stamp.minute, stamp.second, stamp.microsecond) != (0, 0, 0):
            problems.append("%s: valid_time %s is not on a whole hour" % (city, valid_time))
    detail, ok = _joined(problems, "rating_amps above 0 and valid_time on a whole hour for every row")
    return CheckResult("latest_rating_values", ok, detail)


def _check_flags(rows):
    stale_after = latest_rating_contract.STALE_AFTER_MINUTES
    problems = []
    for row in rows:
        city = _city_of(row)
        age = row.get("age_minutes")
        stale = row.get("is_stale")
        if not isinstance(age, int) or isinstance(age, bool):
            problems.append("%s: age_minutes must be a whole number (got %r)" % (city, age))
        elif not isinstance(stale, bool) or stale != (age > stale_after):
            problems.append("%s: is_stale is %r but age_minutes is %d (stale means more than %d)"
                            % (city, stale, age, stale_after))
        expected = latest_rating_contract.is_provisional(row.get("rating_basis"), row.get("config_version"))
        provisional = row.get("is_provisional")
        if not isinstance(provisional, bool) or provisional != expected:
            problems.append("%s: is_provisional is %r but the labels say %r" % (city, provisional, expected))
    detail, ok = _joined(problems, "is_stale and is_provisional agree with age_minutes and the labels on every row")
    return CheckResult("latest_rating_flags", ok, detail)


def _describe_rows(rows, lines):
    if lines is None:
        return
    for row in rows:
        lines.append(
            "city %s valid_time %s age_minutes %s is_stale %s status %s rating_amps %s is_provisional %s" % (
                row.get("city"), row.get("valid_time"), row.get("age_minutes"), row.get("is_stale"),
                row.get("status"), row.get("rating_amps"), row.get("is_provisional")))


def _check_count(cfg, opener):
    name = "latest_rating_count_exact"
    try:
        total = supabase_rest.count_exact(cfg, "latest_rating", [], opener=opener)
    except supabase_rest.RestError as exc:
        return CheckResult(name, False, _fail_text(exc, cfg))
    if total != len(EXPECTED_CITIES):
        return CheckResult(name, False, "count=exact reports %d rows, expected %d" % (total, len(EXPECTED_CITIES)))
    return CheckResult(name, True, "count=exact reports %d" % total)


def _check_city_rating(cfg, opener):
    name = "city_rating_readable"
    try:
        response = supabase_rest.request(cfg, "GET", "city_rating", [("select", "city"), ("limit", "1")], opener=opener)
    except supabase_rest.RestError as exc:
        return CheckResult(name, False, _fail_text(exc, cfg))
    if response.status != 200:
        return CheckResult(name, False, "city_rating answered %s" % supabase_rest.brief(response, cfg))
    return CheckResult(name, True, "HTTP 200")


def _check_keyless(cfg, opener):
    name = "keyless_request_refused"
    try:
        response = supabase_rest.request(
            cfg, "GET", "latest_rating", [("select", "city"), ("limit", "1")], opener=opener, send_key=False)
    except supabase_rest.RestError as exc:
        return CheckResult(name, False, _fail_text(exc, cfg))
    if 200 <= response.status < 300:
        return CheckResult(name, False, "latest_rating answered HTTP %d without a key" % response.status)
    if response.status in KEYLESS_OK_STATUSES:
        return CheckResult(name, True, "refused with HTTP %d" % response.status)
    return CheckResult(name, False, "inconclusive: %s" % supabase_rest.brief(response, cfg))


def _check_assert_fresh(cfg, opener):
    name = "assert_fresh_answers"
    try:
        response = supabase_rest.request(cfg, "GET", "rpc/assert_fresh", opener=opener)
    except supabase_rest.RestError as exc:
        return CheckResult(name, False, _fail_text(exc, cfg))
    if response.status == 200:
        return CheckResult(name, True, "HTTP 200 (every city is fresh)")
    if response.status == 503:
        try:
            body = response.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and body.get("code") == "PT503":
            return CheckResult(name, True, "HTTP 503 PT503 (a city is stale; the alarm would fire)")
    return CheckResult(name, False, "rpc/assert_fresh answered %s" % supabase_rest.brief(response, cfg))


def check_read(cfg, opener=None, now=None, lines=None, attempts=None):
    """The read contract as a consumer sees it (API-01). `lines` collects the per-city output lines."""
    results = []
    rows = _read_latest(cfg, opener, results)
    if rows is not None:
        results.extend([_check_cities(rows), _check_columns(rows), _check_values(rows), _check_flags(rows)])
        _describe_rows(rows, lines)
    results.append(_check_count(cfg, opener))
    results.append(_check_city_rating(cfg, opener))
    results.append(_check_keyless(cfg, opener))
    results.append(_check_assert_fresh(cfg, opener))
    return results


# ---------------------------------------------------------------------------
# --check-hidden
# ---------------------------------------------------------------------------


def check_hidden(cfg, opener=None, now=None, lines=None, attempts=None):
    """The private tables are not readable with the public key (API-01, OD-6)."""
    results = []
    for schema, table in HIDDEN_TARGETS:
        name = "hidden:%s.%s" % (schema, table)
        profile = None if schema == "public" else schema
        try:
            response = supabase_rest.request(
                cfg, "GET", table, [("select", "*"), ("limit", "1")], profile=profile, opener=opener)
        except supabase_rest.RestError as exc:
            results.append(CheckResult(name, False, _fail_text(exc, cfg)))
            continue
        if 200 <= response.status < 300:
            results.append(CheckResult(name, False, "%s.%s is readable by the public key (HTTP %d)"
                                       % (schema, table, response.status)))
        elif response.status in HIDDEN_OK_STATUSES:
            results.append(CheckResult(name, True, "not readable (HTTP %d)" % response.status))
        else:
            results.append(CheckResult(name, False, "inconclusive: %s" % supabase_rest.brief(response, cfg)))
    return results


CHECKS = {"read": check_read, "hidden": check_hidden}
DEFAULT_CHECKS = ("read", "hidden")


# ---------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------


def _redact_object(value, cfg):
    """Every string in a JSON-ready structure, redacted, so a value never survives inside the file."""
    if isinstance(value, str):
        return supabase_rest.redact_rest(value, cfg, limit=None)
    if isinstance(value, list):
        return [_redact_object(v, cfg) for v in value]
    if isinstance(value, dict):
        return {k: _redact_object(v, cfg) for k, v in value.items()}
    return value


def _write_report(path, report, cfg):
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    text = json.dumps(_redact_object(report, cfg), indent=2) + "\n"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(supabase_rest.redact_rest(text, cfg, limit=None))


def main(argv=None, opener=None, now=None):
    parser = argparse.ArgumentParser(description="Check the public REST interface as a consumer (read-only).")
    parser.add_argument("--check-read", action="store_true", help="the latest_rating read contract")
    parser.add_argument("--check-hidden", action="store_true", help="the private tables are not readable")
    parser.add_argument("--json-out", default=None, help="write the check results JSON here")
    args = parser.parse_args(argv)
    selected = [name for name in CHECKS if getattr(args, "check_%s" % name, False)]
    if not selected:
        selected = list(DEFAULT_CHECKS)

    try:
        cfg = supabase_rest.config_from_env()
    except supabase_rest.ConfigError as exc:
        print(supabase_rest.redact_rest(str(exc)), file=sys.stderr)
        return 2

    results = []
    attempts = []
    for name in selected:
        lines = []
        group = CHECKS[name](cfg, opener=opener, now=now, lines=lines, attempts=attempts)
        for line in lines:
            print(supabase_rest.redact_rest(line, cfg, limit=None))
        for result in group:
            print(supabase_rest.redact_rest(
                "%s %s: %s" % ("PASS" if result.ok else "FAIL", result.name, result.detail), cfg, limit=None))
        results.extend(group)

    failed = [r.name for r in results if not r.ok]
    code = 1 if failed else 0
    print("E2E READONLY OK" if not failed else "E2E READONLY FAILED: " + ", ".join(failed))
    if args.json_out:
        report = {
            "checks": [{"name": r.name, "ok": r.ok, "detail": r.detail} for r in results],
            "attempts": attempts,
            "exit_code": code,
        }
        _write_report(args.json_out, report, cfg)
    return code


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    sys.exit(main())
