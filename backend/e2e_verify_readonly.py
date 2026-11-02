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
answer 401 or 403 with code 42501, or 404 or 406 with PGRST205, PGRST106 or PGRST202. Any 2xx, even an
empty list, fails as "readable by the public key"; a refusal that names no cause (a bare 401 "Invalid
API key", a 5xx) is inconclusive and fails. First, one read of latest_rating with the same key must
answer 200, or the result is a single `key_sanity` failure and no refusal is trusted.

The per-city lines (city, valid_time, age_minutes, is_stale, status, rating_amps,
is_provisional) are printed so the owner can read the answer, not just the verdict.

--check-writes (OFF by default; E2E-03, OD-6) proves: "trying to add, change or delete data
with the public key is refused, and the data afterwards is identical."

  snapshot_before            every city_rating row older than the current UTC hour minus one
                             hour is read (paged past the 1000-row cap, cross-checked against
                             count=exact) and fingerprinted with SHA-256; with no such row the
                             check fails as "nothing to prove unchanged" and sends no write
  write:table_insert         \
  write:table_upsert          |  the public key tries to INSERT, upsert (on_conflict=city,valid_time,
  write:table_patch           |  merge-duplicates), PATCH and DELETE on public.city_rating; each
  write:table_delete         /   must be refused by PRIVILEGE: HTTP 401 or 403, code 42501 and
                                 "permission denied". Any 2xx fails as "write accepted" (including
                                 200 with an empty list); 42501 with "row-level security" fails as
                                 "RLS-only rejection: a write grant is still present"; anything
                                 else fails as inconclusive
  write:view_insert          \
  write:view_patch            |  the same three writes against public.latest_rating pass on any
  write:view_delete          /   4xx answer (or HTTP 500 with the database's 55000 "cannot change
                                 view") and fail on any 2xx; any other 5xx is inconclusive
  snapshot_unchanged         the snapshot is read again; the row count and the SHA-256 must be
                             identical, because a status code alone can pass on a project that
                             silently changed data

The INSERT body is a complete, constraint-valid copy of a real row at the sentinel key (AUSTIN,
2000-01-01T00:00:00Z, run_id e2e-03-sentinel), so a wrongly granted INSERT would succeed and be
caught; the upsert and the PATCH move one old row by +1 A. If any write was accepted or the snapshot
changed, the script exits 1 and prints a RECOVERY block (the original row, the statement to put it
back, the sentinel delete) for the OWNER to run on the admin connection. The script itself holds no
elevated credential and never deletes, restores or retries anything.

Run it with NO backfill load and NO manual past-slot re-run in progress: those are the only
legitimate writers of rows older than the cutoff. The live hourly upsert (OD-7) writes only its own
current-hour slot, which is after the cutoff, so it cannot change the snapshot. A "snapshot changed"
failure with no accepted write names those two benign causes to rule out first.

Exit codes: 0 every check passed, 1 a check failed, 2 SUPABASE_URL or SUPABASE_PUBLISHABLE_KEY
is missing, or the key is a secret key or a service_role token (no request is made).

The owner runs it from the repository root with the two values in the shell environment:

    export SUPABASE_URL=... SUPABASE_PUBLISHABLE_KEY=...
    PYTHONPATH=backend .venv/bin/python backend/e2e_verify_readonly.py --check-read --check-hidden

Nothing here is run against the live project by the build; that is the owner's step in 06-09.
"""

import argparse
import hashlib
import json
import math
import os
import sys
from collections import namedtuple
from datetime import datetime, timedelta, timezone

import config
import latest_rating_contract
import supabase_rest

CheckResult = namedtuple("CheckResult", ["name", "ok", "detail"])

EXPECTED_CITIES = config.LOCATIONS
HIDDEN_TARGETS = (("public", "pipeline_run"), ("ops", "freshness_log"))
# A hidden answer only counts when it names the cause: a privilege refusal (42501) or PostgREST
# saying the schema or relation is not in its cache. A bare 401 "Invalid API key" from the gateway,
# or any 5xx, proves nothing about the table.
HIDDEN_REFUSED_PRIVILEGE = (401, 403)
HIDDEN_NOT_EXPOSED = (404, 406)
HIDDEN_NOT_EXPOSED_CODES = ("PGRST205", "PGRST106", "PGRST202")
KEYLESS_OK_STATUSES = (401, 403)
VIEW_WRITE_DB_REFUSAL_CODES = ("55000", "42501")

# E2E-03: the sentinel key sits in the year 2000, never the latest slot of any city.
SENTINEL_CITY = "AUSTIN"
SENTINEL_VALID_TIME = "2000-01-01T00:00:00Z"
SENTINEL_RUN_ID = "e2e-03-sentinel"
WRITE_PREFER = "return=representation"


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


def _hidden_cause(response):
    """A short cause when the answer proves the table is unreadable, else None (inconclusive)."""
    code = (_body_of(response) or {}).get("code")
    if response.status in HIDDEN_REFUSED_PRIVILEGE and code == "42501":
        return "HTTP %d %s" % (response.status, code)
    if response.status in HIDDEN_NOT_EXPOSED and code in HIDDEN_NOT_EXPOSED_CODES:
        return "HTTP %d %s" % (response.status, code)
    return None


def check_hidden(cfg, opener=None, now=None, lines=None, attempts=None):
    """The private tables are not readable with the public key (API-01, OD-6)."""
    results = []
    # A refusal is only evidence when the key itself works: with an invalid or revoked key the
    # gateway refuses every request, so the private tables would look hidden for the wrong reason.
    try:
        sanity = supabase_rest.request(
            cfg, "GET", "latest_rating", [("select", "city"), ("limit", "1")], opener=opener)
    except supabase_rest.RestError as exc:
        return [CheckResult("key_sanity", False, "the key could not be checked, so no refusal is trusted: %s"
                            % _fail_text(exc, cfg))]
    if sanity.status != 200:
        return [CheckResult("key_sanity", False, "latest_rating answered %s with the key, so no refusal is trusted"
                            % supabase_rest.brief(sanity, cfg))]
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
        elif _hidden_cause(response):
            results.append(CheckResult(name, True, "not readable (%s)" % _hidden_cause(response)))
        else:
            results.append(CheckResult(name, False, "inconclusive: %s" % supabase_rest.brief(response, cfg)))
    return results


# ---------------------------------------------------------------------------
# --check-writes (E2E-03)
# ---------------------------------------------------------------------------

Snapshot = namedtuple("Snapshot", ["count", "digest", "target"])


class SnapshotError(RuntimeError):
    """The snapshot could not be read or does not add up. The message is redacted."""


def snapshot(cfg, cutoff, opener=None):
    """
    Count, SHA-256 and first row of every city_rating row with valid_time before `cutoff` (an ISO
    string). Paged past the server's row cap and cross-checked against `count=exact`; raises
    SnapshotError when they disagree or a request fails. The digest is taken over the canonical JSON
    of all rows ordered by (city, valid_time), so any changed value, added row or removed row moves it.
    """
    params = [("select", "*"), ("valid_time", "lt." + cutoff)]
    try:
        rows = supabase_rest.get_all(cfg, "city_rating", params, "city.asc,valid_time.asc", opener=opener)
        total = supabase_rest.count_exact(cfg, "city_rating", params, opener=opener)
    except supabase_rest.RestError as exc:
        raise SnapshotError("could not read the snapshot: %s" % _fail_text(exc, cfg))
    if total != len(rows):
        raise SnapshotError("snapshot is not consistent: count=exact reports %d rows but %d were fetched"
                            % (total, len(rows)))
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return Snapshot(count=len(rows), digest=digest, target=rows[0] if rows else None)


def _body_of(response):
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _classify_table_write(response):
    """(ok, detail, code) for a write to public.city_rating: only a privilege-layer refusal passes."""
    status = response.status
    body = _body_of(response) or {}
    code = body.get("code") if isinstance(body.get("code"), str) else None
    message = str(body.get("message") or "").lower()
    if 200 <= status < 300:
        return False, "write accepted (HTTP %d)" % status, code
    if code == "42501" and status in (401, 403):
        if "row-level security" in message:
            return (False, "RLS-only rejection: a write grant is still present (HTTP %d 42501, %s)"
                    % (status, "row-level security"), code)
        if "permission denied" in message:
            return True, "refused by privilege (HTTP %d 42501 permission denied)" % status, code
    return False, "inconclusive: HTTP %d, code %s" % (status, code), code


def _classify_view_write(response):
    status = response.status
    body = _body_of(response) or {}
    code = body.get("code") if isinstance(body.get("code"), str) else None
    if 200 <= status < 300:
        return False, "write accepted (HTTP %d)" % status, code
    if 400 <= status < 500:
        return True, "refused (HTTP %d)" % status, code
    # The live service answers a write to the (not updatable) view with HTTP 500 and the database's own
    # 55000 "cannot change view", which is a real refusal. Any other 5xx (a gateway timeout after a
    # committed write, say) says nothing about the outcome.
    if status >= 500 and code in VIEW_WRITE_DB_REFUSAL_CODES:
        return True, "refused by the database (HTTP %d, code %s)" % (status, code), code
    return False, "inconclusive: HTTP %d, code %s" % (status, code), code


def _sql_literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def _recovery_lines(target, accepted, changed):
    """The owner's recovery steps. Printed, never executed."""
    city, valid_time = target.get("city"), target.get("valid_time")
    reasons = []
    if accepted:
        reasons.append("accepted writes: " + ", ".join(accepted))
    if changed:
        reasons.append("the snapshot changed or could not be re-read")
    return [
        "RECOVERY (owner only, on the admin connection; this script executed none of these statements)",
        "  Why: " + "; ".join(reasons),
        "  1. Restore the original value of the target row:",
        "     update public.city_rating set rating_amps = %r where city = %s and valid_time = %s;" % (
            target.get("rating_amps"), _sql_literal(city), _sql_literal(valid_time)),
        "  2. If the target row was deleted, put it back from this copy of its original values:",
        "     " + json.dumps(target, sort_keys=True),
        "  3. Remove the sentinel row:",
        "     delete from public.city_rating where city = %s and valid_time = %s;" % (
            _sql_literal(SENTINEL_CITY), _sql_literal(SENTINEL_VALID_TIME)),
        "  4. Remove the grant that let the write through, then run --check-writes again:",
        "     revoke insert, update, delete, truncate on public.city_rating, public.latest_rating"
        " from anon, authenticated;",
    ]


def _write_specs(target):
    """The seven attempts, in order: (name, kind, method, path, params, extra headers, body)."""
    amps = target["rating_amps"] + 1.0
    sentinel = dict(target, city=SENTINEL_CITY, valid_time=SENTINEL_VALID_TIME, run_id=SENTINEL_RUN_ID)
    bumped = dict(target, rating_amps=amps)
    # The view writes name the same OLD row, which the view never shows, so even a view that became
    # updatable could not change a current rating.
    key_filter = [("city", "eq." + str(target["city"])), ("valid_time", "eq." + str(target["valid_time"]))]
    prefer = {"Prefer": WRITE_PREFER}
    merge = {"Prefer": "resolution=merge-duplicates," + WRITE_PREFER}
    view_sentinel = {c: sentinel.get(c) for c in latest_rating_contract.STORED_COLUMNS}
    return [
        ("table_insert", "table", "POST", "city_rating", None, prefer, sentinel),
        ("table_upsert", "table", "POST", "city_rating", [("on_conflict", "city,valid_time")], merge, [bumped]),
        ("table_patch", "table", "PATCH", "city_rating", key_filter, prefer, {"rating_amps": amps}),
        ("table_delete", "table", "DELETE", "city_rating", key_filter, prefer, None),
        ("view_insert", "view", "POST", "latest_rating", None, prefer, view_sentinel),
        ("view_patch", "view", "PATCH", "latest_rating", key_filter, prefer, {"rating_amps": amps}),
        ("view_delete", "view", "DELETE", "latest_rating", key_filter, prefer, None),
    ]


def check_writes(cfg, opener=None, now=None, lines=None, attempts=None):
    """
    E2E-03: the public key cannot write, and the data is provably unchanged. Sends write attempts
    with the publishable key only, classifies each, and compares a before and after snapshot of
    every row older than the cutoff. `lines` collects the RECOVERY block; `attempts` collects one
    record per attempt for the evidence file.
    """
    results = []
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff_time = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    cutoff = cutoff_time.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        before = snapshot(cfg, cutoff, opener=opener)
    except SnapshotError as exc:
        return [CheckResult("snapshot_before", False, str(exc))]
    if before.count == 0:
        return [CheckResult(
            "snapshot_before", False,
            "nothing to prove unchanged: no city_rating row is older than %s, so a write could not be shown "
            "to leave the data unchanged; no write was sent" % cutoff)]
    target = before.target
    if not _is_number(target.get("rating_amps")) or not target.get("city") or not target.get("valid_time"):
        return [CheckResult("snapshot_before", False, "the first stored row has no usable city, valid_time and rating_amps; no write was sent")]
    results.append(CheckResult("snapshot_before", True, "%d rows older than the cutoff, sha256 %s"
                               % (before.count, before.digest[:12])))

    accepted = []
    for name, kind, method, path, params, extra, body in _write_specs(target):
        try:
            response = supabase_rest.request(cfg, method, path, params, headers=extra, body=body, opener=opener)
        except supabase_rest.RestError as exc:
            ok, detail, code, status = False, "request failed: %s" % _fail_text(exc, cfg), None, None
        else:
            status = response.status
            ok, detail, code = (_classify_table_write if kind == "table" else _classify_view_write)(response)
        if detail.startswith("write accepted"):
            accepted.append(name)
        results.append(CheckResult("write:" + name, ok, detail))
        if attempts is not None:
            attempts.append({"name": name, "method": method, "path": path, "status": status, "code": code,
                             "verdict": "pass" if ok else "fail"})

    changed = False
    try:
        after = snapshot(cfg, cutoff, opener=opener)
    except SnapshotError as exc:
        changed = True
        results.append(CheckResult("snapshot_unchanged", False, "could not re-read the snapshot: %s" % exc))
    else:
        if (after.count, after.digest) == (before.count, before.digest):
            results.append(CheckResult("snapshot_unchanged", True, "%d rows, sha256 %s identical before and after"
                                       % (after.count, after.digest[:12])))
        else:
            changed = True
            detail = "snapshot changed: %d rows -> %d rows, sha256 %s -> %s." % (
                before.count, after.count, before.digest[:12], after.digest[:12])
            if not accepted:
                detail += (" No write was accepted above, so first confirm that no backfill load and no manual "
                           "past-slot re-run ran during the check before treating this as a write-protection failure.")
            results.append(CheckResult("snapshot_unchanged", False, detail))
    if (accepted or changed) and lines is not None:
        lines.extend(_recovery_lines(target, accepted, changed))
    return results


CHECKS = {"read": check_read, "hidden": check_hidden, "writes": check_writes}
DEFAULT_CHECKS = ("read", "hidden")  # writes only when --check-writes is given
LINES_AFTER_RESULTS = ("writes",)  # the RECOVERY block follows the verdicts; the city lines precede them


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
    parser.add_argument("--check-writes", action="store_true",
                        help="the public key cannot write and the data is unchanged (sends write attempts)")
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
        verdicts = [supabase_rest.redact_rest(
            "%s %s: %s" % ("PASS" if r.ok else "FAIL", r.name, r.detail), cfg, limit=None) for r in group]
        extra = [supabase_rest.redact_rest(line, cfg, limit=None) for line in lines]
        for line in (verdicts + extra if name in LINES_AFTER_RESULTS else extra + verdicts):
            print(line)
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
