"""
Provisional Historical Archive Backfill (Track 1)
==================================================
Runs the integrated pipeline once per time step over a past window so
`historical_archive` fills with rows the forecast and detector can use. It is
a PLACEHOLDER archive: rows describe each city's current rating point,
assumed line bearing and static rating, so regenerate it once any of those
change (e.g. real line geometry).

Safe to stop and restart: a (city, timestamp) already in the archive file
is skipped, so rerunning continues where it left off and never duplicates rows.

    python backfill_archive.py                                   # 7 days, hourly
    python backfill_archive.py --start 2025-06-01 --end 2025-06-15
    python backfill_archive.py --step-hours 3 --no-synoptic      # lighter / faster

Needs SYNOPTIC_TOKEN (station locations), NREL_API_KEY and NREL_API_EMAIL.
Writes the archive (default data/historical/provisional_backfill.csv) and a
per-run log (default outputs/backfill_log.csv); never touches
config.HISTORICAL_ARCHIVE_PATH unless you pass it.

With --trace-path it also appends one JSON line per city per executed step
(schema `backfill_trace/1`) holding what the per-city pipeline actually did, for
offline validation by real_data_validation.py. Without it nothing extra is
opened or written.
"""

import argparse
import contextlib
import io
import json
import logging
import os
import re
import sys
import time
import urllib.parse
from collections import Counter

import pandas as pd

import config
import historical_archive
import observation_composer
from dlr_orchestrator import run_dlr_pipeline, _discover_stations

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
DEFAULT_ARCHIVE = os.path.join("data", "historical", "provisional_backfill.csv")
DEFAULT_LOG = os.path.join("outputs", "backfill_log.csv")
_GATE_RE = re.compile(r"\b(G[1-6]) FAIL")

# Per-step validation trace (see `_trace_records`).
TRACE_SCHEMA = "backfill_trace/1"
_OBSERVATION_KEYS = ("temp", "wind", "wind_raw", "wind_direction", "solar")
_TRACE_TEXT_LIMIT = 200
# Environment variables whose actual values are scrubbed wherever they appear
# (plain or percent-encoded), whatever shape the surrounding text has.
_SECRET_ENV_NAMES = ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL")
_MIN_SECRET_LENGTH = 4
# `name<sep>value` where the name ends in a credential-shaped word (token,
# api_key, NREL_API_KEY, access_token, accessKey, secret_key, email, authorization, ...)
# and the separator is `=`, `:` or a percent-encoded `=`, with a quote after the name
# (JSON and dict forms, `"token":` or, inside a JSON string, `\"token\":`) and any
# amount of whitespace around it. The value is, in order: an escaped-quote string
# (`\"abc\"`), a quoted string (backslash escapes allowed), a `Bearer`-style scheme
# plus its credential, or a bare run to the next `&`/whitespace/quote. A quoted value
# with no closing quote (a message cut short) runs to the end of the text, and a comma
# or an inner `)` cannot leave a tail. One trailing `)` is left outside a bare value so
# "(api_key=X)" keeps its bracket.
# The words that are also ordinary diagnostic vocabulary (`key`, `auth`, `sig`)
# only count in query/assignment form (`key=abc`, `%3D`) or as a quoted JSON/dict
# name (`"key": "abc"`), so "missing key: temp" and "hotkey: F5 failed" survive;
# `_bare_colon` below still masks a `key:`/`auth:`/`sig:` followed by a value that looks
# like a credential.
_NAME_QUOTE = r"""(?:\\?["'])?"""
_SECRET_PAIR = re.compile(
    r"""(?<![\w-])("""
    r"""(?:[\w-]*(?:token|api[_-]?key|[_-]key|"""
    r"""(?:access|secret|private|signing|subscription|client|auth|encryption|master)key|"""
    r"""email|password|passwd|pwd|secret|credential|"""
    r"""authorization)""" + _NAME_QUOTE + r"""\s*(?:=|:|%3D)"""
    r"""|(?:key|auth|sig)(?:""" + _NAME_QUOTE + r"""\s*(?:=|%3D)|\\?["']\s*:))"""
    r"""\s*)"""
    r"""(?:\\"(?:(?!\\")[\s\S])*(?:\\"|$)|\\'(?:(?!\\')[\s\S])*(?:\\'|$)|"""
    r""""(?:[^"\\]|\\[\s\S]?)*(?:"|$)|'(?:[^'\\]|\\[\s\S]?)*(?:'|$)|"""
    r"""(?:Bearer|Basic|Token|Digest|Negotiate)\s+[^&\s"']+|[^&\s"']*[^&\s"')])""",
    re.IGNORECASE)


def _bare_colon(names: str, min_length: int):
    """
    `<name>: <value>` for the words that are usually diagnostic vocabulary
    ("missing key: temp", "auth: failed"): only a value of `min_length`+
    credential-alphabet characters that contains a digit is a secret. The value may
    sit in quotes; the quotes stay.
    """
    return re.compile(
        r"(?<![\w-])((?:" + names + r")\s*:\s*[\"']?)"
        r"(?=[\w.~+/=-]{" + str(min_length) + r",}(?![\w.~+/=-]))(?=[\w.~+/=-]*\d)[\w.~+/=-]+",
        re.IGNORECASE)


_BARE_COLON_PATTERNS = (_bare_colon("key", 20), _bare_colon("auth|sig", 8))
_BEARER = re.compile(r"\bBearer\s+[\w.~+/=-]+", re.IGNORECASE)
_NULL_RECORD_KEYS = (
    "station_id", "rating_a", "static_rating_a", "status", "fallback", "exhausted", "archived",
    "fallback_gates", "alerts", "observation", "observation_hour", "sources", "pipeline")


_LOG_HEADER = "run_end_utc,city,rating_a,fallback,exhausted,archived,gates,error"


def _retire_stale_log(log_path: str) -> None:
    """
    If an existing log has a different header (e.g. the corridor-era format),
    move it aside so new rows are never appended under the wrong header.
    """
    if not os.path.exists(log_path) or os.path.getsize(log_path) == 0:
        return
    with open(log_path, "r", encoding="utf-8") as fh:
        first = fh.readline().strip()
    if first != _LOG_HEADER:
        os.replace(log_path, log_path + ".legacy")


def _already_archived(path: str) -> dict:
    """{city: set of UTC timestamps} already present in the archive file."""
    hist = historical_archive.read_history(path=path, validate=False)
    done: dict = {}
    if len(hist):
        ts = pd.to_datetime(hist["datetime_utc"], utc=True)
        for city, t in zip(hist["city"], ts):
            done.setdefault(city, set()).add(t)
    return done


def _known_secrets() -> list:
    """
    The configured credential values (and their percent-encoded forms), longest
    first so a secret that contains another is replaced whole. Read from the
    environment on every call so a value set after import is still covered.
    """
    values = set()
    for name in _SECRET_ENV_NAMES:
        value = os.environ.get(name, "")
        if len(value) >= _MIN_SECRET_LENGTH:
            values.update({value, urllib.parse.quote(value, safe=""),
                           urllib.parse.quote_plus(value)})
    return sorted(values, key=len, reverse=True)


def _terminate_last_line(path) -> None:
    """
    If an existing file does not end in a newline (a run killed mid-write left a
    torn last line), add one, so the next appended record starts on its own line
    instead of being glued onto the fragment and lost with it.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return
    with open(path, "rb+") as fh:
        fh.seek(-1, os.SEEK_END)
        if fh.read(1) != b"\n":
            fh.write(b"\n")


def _redact(text, limit=_TRACE_TEXT_LIMIT) -> str:
    """
    Remove credentials from `text`, then cut it to `limit` characters (None for
    no cut). Two passes: every configured secret value is replaced wherever it
    appears, then every credential-shaped `name=value` / `name: value` pair and
    `Bearer` token is masked by shape. Redaction runs first so a cut can never
    leave half of a secret behind. Applied to every alert and error string written
    to the trace and the log, because a requests error can echo a query string,
    a kwargs dict or a header.
    """
    out = str(text)
    for secret in _known_secrets():
        out = out.replace(secret, "REDACTED")
    out = _SECRET_PAIR.sub(r"\1REDACTED", out)
    for pattern in _BARE_COLON_PATTERNS:
        out = pattern.sub(r"\1REDACTED", out)
    out = _BEARER.sub("Bearer REDACTED", out)
    return out if limit is None else out[:limit]


def _trace_records(run: dict, ts_text: str, forecast_method: str, provenance: list) -> list:
    """
    One trace record per city the step rated, built from the raw
    `run_city_pipeline` results zipped with their summary rows. `provenance` is
    the slice of the composed fetcher's provenance this step added; the record of
    the rated station (the last one, if several) names the aligned observation
    hour and the provider of each input.
    """
    records = []
    for result, row in zip(run["results"], run["summary"]):
        obs = result.get("observation")
        stid = result.get("station_id")
        match = None
        if stid is not None:
            for rec in provenance:
                if str(rec.get("stid")) == str(stid):
                    match = rec
        records.append({
            "schema": TRACE_SCHEMA,
            "run_end_utc": ts_text,
            "city": result["city"],
            "forecast_method": run.get("forecast_method", forecast_method),
            "error": None,
            "station_id": stid,
            "rating_a": result["rating"],
            "static_rating_a": row["static_rating_a"],
            "status": result["status"],
            "fallback": result["fallback"],
            "exhausted": result["exhausted"],
            "archived": result["archived"],
            "fallback_gates": row["fallback_gates"],
            "alerts": [_redact(a) for a in result["alerts"]],
            "observation": None if obs is None else {k: float(obs[k]) for k in _OBSERVATION_KEYS},
            "observation_hour": None if match is None else match.get("hour"),
            "sources": None if match is None else {
                k: match.get(k) for k in ("air_temp", "wind_speed", "solar_radiation")},
            "pipeline": result.get("pipeline"),
        })
    for city, message in run.get("errors", {}).items():
        record = {"schema": TRACE_SCHEMA, "run_end_utc": ts_text, "city": city,
                  "forecast_method": run.get("forecast_method", forecast_method),
                  "error": _redact(message)}
        record.update({key: None for key in _NULL_RECORD_KEYS})
        records.append(record)
    return records


def backfill(start, end, step_hours=1.0, archive_path=DEFAULT_ARCHIVE, log_path=DEFAULT_LOG,
             cities=None, forecast_method="naive", skip_synoptic=False,
             stations=None, fetcher=None, out=print, trace_path=None) -> dict:
    cities = list(cities) if cities else list(config.LOCATIONS)
    times = pd.date_range(pd.Timestamp(start, tz="UTC") if pd.Timestamp(start).tzinfo is None else pd.Timestamp(start).tz_convert("UTC"),
                          pd.Timestamp(end, tz="UTC") if pd.Timestamp(end).tzinfo is None else pd.Timestamp(end).tz_convert("UTC"),
                          freq=pd.Timedelta(hours=step_hours))
    if stations is None:
        stations = _discover_stations("composed")
    if fetcher is None:
        priority = {f: tuple(p for p in order if not (skip_synoptic and p == "synoptic"))
                    for f, order in observation_composer.FIELD_PRIORITY.items()}
        fetcher = observation_composer.make_composed_fetcher(stations, field_priority=priority)

    done = _already_archived(archive_path)
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    _retire_stale_log(log_path)
    write_header = not os.path.exists(log_path)
    totals = {"runs": 0, "skipped": 0, "archived": Counter(), "not_archived": Counter(),
              "fallback": Counter(), "exhausted": Counter(), "gates": Counter(), "errors": Counter(),
              "interrupted": False}
    t0 = time.time()
    n = len(times)

    trace_cm = contextlib.nullcontext()
    if trace_path:
        os.makedirs(os.path.dirname(str(trace_path)) or ".", exist_ok=True)
        _terminate_last_line(trace_path)
        trace_cm = open(trace_path, "a", encoding="utf-8")

    with open(log_path, "a", encoding="utf-8") as log_fh, trace_cm as trace_fh:
        if write_header:
            log_fh.write(_LOG_HEADER + "\n")
        try:
            for i, ts in enumerate(times, 1):
                todo = [c for c in cities if ts not in done.get(c, set())]
                if not todo:
                    totals["skipped"] += 1
                    continue
                prov_start = len(fetcher.provenance) if trace_fh is not None else 0
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):  # the safety monitor prints each gate failure
                    run = run_dlr_pipeline(
                        cities=todo, end=ts.strftime(_TS_FMT), window_hours=1.0,
                        provider="composed", forecast_method=forecast_method, archive=True,
                        archive_path=archive_path, stations=stations, fetcher=fetcher)
                gates = Counter(_GATE_RE.findall(buf.getvalue()))
                totals["gates"].update(gates)
                totals["runs"] += 1
                # The trace goes first: `run_dlr_pipeline` has already appended the archive
                # row, and on resume a step in the archive is skipped, so an interrupt
                # between the archive write and the trace write would lose this step's
                # trace for good. Writing it before the log/summary lines keeps that
                # window as small as it can be.
                if trace_fh is not None:
                    for record in _trace_records(run, ts.strftime(_TS_FMT), forecast_method,
                                                 fetcher.provenance[prov_start:]):
                        trace_fh.write(json.dumps(record, default=str, sort_keys=True) + "\n")
                    trace_fh.flush()
                parts = []
                for row in run["summary"]:
                    c = row["city"]
                    totals["archived" if row["archived"] else "not_archived"][c] += 1
                    totals["fallback"][c] += bool(row["fallback"])
                    totals["exhausted"][c] += int(bool(row["exhausted"]))
                    log_fh.write(f"{ts.strftime(_TS_FMT)},{c},{row['rating_a']:.1f},{row['fallback']},"
                                 f"{row['exhausted']},{row['archived']},{'|'.join(row['fallback_gates'])},\n")
                    parts.append(f"{c[:6]} {row['rating_a']:.0f}A{'*' if row['fallback'] else ''}{'' if row['archived'] else ' (not archived)'}")
                for c, msg in run["errors"].items():
                    totals["errors"][c] += 1
                    # redact before the cut so no partial secret survives; collapse
                    # whitespace so a multi-line message stays one CSV row
                    msg_safe = " ".join(_redact(msg, limit=None).split())
                    log_fh.write(f"{ts.strftime(_TS_FMT)},{c},,,,,,{msg_safe.replace(',', ';')[:120]}\n")
                    parts.append(f"{c[:6]} ERROR")
                log_fh.flush()
                elapsed = time.time() - t0
                eta = elapsed / max(totals["runs"], 1) * (n - i)
                out(f"[{i}/{n}] {ts.strftime(_TS_FMT)}  " + " | ".join(parts) + f"   (eta {eta/60:.0f} min)")
        except KeyboardInterrupt:
            totals["interrupted"] = True  # callers that cannot resume (replay) must stop
            out("\nInterrupted -- progress is saved; rerun the same command to continue.")

    totals["provider_issues"] = dict(fetcher.errors)
    totals["sources"] = observation_composer.summarize_sources(fetcher.provenance)
    return totals


def _print_summary(t: dict, archive_path: str, out=print) -> None:
    out("\n=== Backfill summary ===")
    out(f"runs executed: {t['runs']}   steps already archived (skipped): {t['skipped']}")
    for c in sorted(set(t["archived"]) | set(t["not_archived"]) | set(t["errors"])):
        out(f"  {c}: archived {t['archived'][c]}, not archived {t['not_archived'][c]}, "
            f"fallback runs {t['fallback'][c]}, exhausted runs {t['exhausted'][c]}, errors {t['errors'][c]}")
    if t["gates"]:
        out(f"  safety gates that fired (point-level counts): {dict(t['gates'])}")
    for field, counts in t["sources"].items():
        out(f"  sources[{field}]: {counts}")
    for what, n in t["provider_issues"].items():
        out(f"  provider issue: {what} x{n}")
    hist = historical_archive.read_history(path=archive_path)
    out(f"archive rows now: {hist.groupby('city').size().to_dict() if len(hist) else {}}  ({archive_path})")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Backfill a provisional historical archive.")
    p.add_argument("--start", default="2025-06-01", help="first hour (UTC), default 2025-06-01")
    p.add_argument("--end", default="2025-06-08", help="last hour (UTC), default 2025-06-08")
    p.add_argument("--step-hours", type=float, default=1.0)
    p.add_argument("--archive-path", default=DEFAULT_ARCHIVE)
    p.add_argument("--log-path", default=DEFAULT_LOG)
    p.add_argument("--cities", nargs="*")
    p.add_argument("--forecast-method", default="naive")
    p.add_argument("--no-synoptic", action="store_true",
                   help="skip Synoptic/ASOS (far fewer requests for old windows with no station data)")
    p.add_argument("--trace-path", default=None,
                   help="append one JSON line per city per step for offline validation "
                        "(default: no trace)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s | %(message)s")
    totals = backfill(args.start, args.end, args.step_hours, args.archive_path, args.log_path,
                      args.cities, args.forecast_method, args.no_synoptic,
                      trace_path=args.trace_path)
    _print_summary(totals, args.archive_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
