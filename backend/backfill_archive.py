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
"""

import argparse
import contextlib
import io
import logging
import os
import re
import sys
import time
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


def backfill(start, end, step_hours=1.0, archive_path=DEFAULT_ARCHIVE, log_path=DEFAULT_LOG,
             cities=None, forecast_method="naive", skip_synoptic=False,
             stations=None, fetcher=None, out=print) -> dict:
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
              "fallback": Counter(), "exhausted": Counter(), "gates": Counter(), "errors": Counter()}
    t0 = time.time()
    n = len(times)

    with open(log_path, "a", encoding="utf-8") as log_fh:
        if write_header:
            log_fh.write(_LOG_HEADER + "\n")
        try:
            for i, ts in enumerate(times, 1):
                todo = [c for c in cities if ts not in done.get(c, set())]
                if not todo:
                    totals["skipped"] += 1
                    continue
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):  # the safety monitor prints each gate failure
                    run = run_dlr_pipeline(
                        cities=todo, end=ts.strftime(_TS_FMT), window_hours=1.0,
                        provider="composed", forecast_method=forecast_method, archive=True,
                        archive_path=archive_path, stations=stations, fetcher=fetcher)
                gates = Counter(_GATE_RE.findall(buf.getvalue()))
                totals["gates"].update(gates)
                totals["runs"] += 1
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
                    log_fh.write(f"{ts.strftime(_TS_FMT)},{c},,,,,,{msg.replace(',', ';')[:120]}\n")
                    parts.append(f"{c[:6]} ERROR")
                log_fh.flush()
                elapsed = time.time() - t0
                eta = elapsed / max(totals["runs"], 1) * (n - i)
                out(f"[{i}/{n}] {ts.strftime(_TS_FMT)}  " + " | ".join(parts) + f"   (eta {eta/60:.0f} min)")
        except KeyboardInterrupt:
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
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s | %(message)s")
    totals = backfill(args.start, args.end, args.step_hours, args.archive_path, args.log_path,
                      args.cities, args.forecast_method, args.no_synoptic)
    _print_summary(totals, args.archive_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
