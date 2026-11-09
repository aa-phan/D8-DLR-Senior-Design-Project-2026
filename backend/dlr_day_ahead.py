"""
One city's day-ahead run: issue the day-ahead cooling forecast for every due target the table does
not hold yet (production-pipeline Phase 8, DAY-01, DAY-02, DAY-05; D-01, D-02, D-04, D-13a, D-15, D-16).

Started only by `dlr_live_run`'s day-ahead stage, one child per city, after the ratings have fixed the
job's exit code, and killed by the runner at its time budget. A run does this, in order:

    1. due       the 00/06/12/18 UTC grid targets in (now, now + 18 h] (`due_targets`)
    2. existing  the city's future keys already in public.day_ahead_forecast (the table is the only
                 state; there is no file, no cache and no marker)
    3. missing   due minus existing, earliest first. Nothing missing is `none_due`: no model is
                 loaded and nothing is fetched
    4. trust     the band artifact is hashed against the live manifest before it is parsed (D-13a),
                 the cooling model is loaded through the hash-verified loader, and the "now" station
                 reading is taken once for the run. A refusal at this step gives every missing target
                 a named reason and no row, and nothing else is used in its place (D-16)
    5. issue     for each missing target, earliest first: value (`compute_value`), band (`band_for`,
                 through the writer connection), row (`issued_at` = this run's decision time),
                 `insert_row` (ON CONFLICT DO NOTHING: first write wins)

One target that cannot be computed (an unavailable weather run, a non-finite value) is `not_issued`
with its reason while the others are still issued. A value outside the city's rating bounds is
logged and still published (`out_of_bounds`).

Output (`--output PATH`, JSON, always written): city, decision_time, outcome (none_due | issued |
partial | error), due, already_present, issued, not_issued {iso: reason}, band_sources {iso:
source}, out_of_bounds, cooling_model_sha256, duration_s. Targets are ISO UTC strings
(`2026-11-09T18:00:00Z`). Every reason is redacted (the database URL, the provider tokens, key=value
secrets) and cut before it is written or logged; reasons exist only here and in the runner's
`pipeline_run.day_ahead`, never in the table (OD-6, T-08-11).

`--no-store` is a local check: no database is opened, the band is the TEST artifact, nothing is
inserted, and the output carries `"dry_run": true` and a `computed` map {iso: {amps, lower, upper,
band_source}}. The outcome then counts computed targets like issued ones, and `issued` stays empty.
The runner never passes it.

Exit codes: 0 whenever the output was written, whatever the outcome (the runner reads the outcome,
not the exit code); 1 when the output could not be written; 2 a usage error (argparse). A crash
before the output exists is the runner's `error`.

CLI (local runs read `.env` through python-dotenv; tests never do):

    python backend/dlr_day_ahead.py --city MIDLAND --output out.json [--no-store]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
import time

import pandas as pd

import config
import day_ahead_band
import day_ahead_contract as contract
import day_ahead_forecast
import supabase_store

log = logging.getLogger("dlr_day_ahead")

_TS_FMT = "%Y-%m-%dT%H:%M:%SZ"
_REASON_LIMIT = 300
_MIN_SECRET_CHARS = 4
# Provider credentials and the database URLs: their values are removed from every reason (the store's
# redaction also reads the two database URLs from the environment on its own).
_SECRET_ENV = ("SYNOPTIC_TOKEN", "NREL_API_KEY", "NREL_API_EMAIL", "SUPABASE_DB_URL", "SUPABASE_ADMIN_DB_URL")


def _utc(value) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def _iso(value) -> str:
    return _utc(value).strftime(_TS_FMT)


def _redact(text) -> str:
    """
    `text` with the provider credentials of the environment removed, then the store's redaction
    (database URLs and their passwords, `key=value` secrets), then cut. The cut comes last, so a
    longer text never lets a secret through.
    """
    text = "" if text is None else str(text)
    for name in _SECRET_ENV:
        value = (os.environ.get(name) or "").strip()
        if len(value) >= _MIN_SECRET_CHARS:
            text = text.replace(value, "REDACTED")
    return supabase_store.redact(text, limit=_REASON_LIMIT)


def _reason(step: str, exc: BaseException) -> str:
    """The named, redacted reason for a failure: `step: ExceptionType: message`."""
    if isinstance(exc, day_ahead_forecast.DayAheadNotIssued):
        return _redact(exc.reason)
    detail = _redact(str(exc))
    return f"{step}: {type(exc).__name__}: {detail}" if detail else f"{step}: {type(exc).__name__}"


class _Run:
    """What one run has decided so far; `document()` is the output JSON."""

    def __init__(self, city: str, decision_time: pd.Timestamp, dry_run: bool):
        self.city = city
        self.decision_time = decision_time
        self.dry_run = dry_run
        self.conn = None
        self.due: list = []
        self.already_present: list = []
        self.issued: list = []
        self.not_issued: dict = {}
        self.band_sources: dict = {}
        self.out_of_bounds: list = []
        self.computed: dict = {}
        self.cooling_model_sha256 = None
        self.explicit_outcome = None
        self.already_present_race = False

    def refuse(self, targets, reason: str) -> None:
        """No row for these targets, for this one named reason (D-16)."""
        for target in targets:
            self.not_issued[_iso(target)] = reason
            log.error("%s %s: not issued: %s", self.city, _iso(target), reason)

    def outcome(self) -> str:
        if self.explicit_outcome is not None:
            return self.explicit_outcome
        succeeded = bool(self.issued or self.computed)
        if not self.not_issued:
            return "issued" if succeeded else "none_due"
        return "partial" if (succeeded or self.already_present_race) else "error"

    def document(self, duration_s: float) -> dict:
        document = {
            "city": self.city,
            "decision_time": _iso(self.decision_time),
            "outcome": self.outcome(),
            "due": [_iso(t) for t in self.due],
            "already_present": list(self.already_present),
            "issued": list(self.issued),
            "not_issued": {iso: _redact(reason) for iso, reason in self.not_issued.items()},
            "band_sources": dict(self.band_sources),
            "out_of_bounds": list(self.out_of_bounds),
            "cooling_model_sha256": self.cooling_model_sha256,
            "duration_s": round(duration_s, 1),
        }
        if self.dry_run:
            document["dry_run"] = True
            document["computed"] = dict(self.computed)
        return document


def _issue(run: _Run, missing: list, *, artifact, band_sha, model, model_entry, anchor, run_ctx) -> None:
    """Value, band, row and insert for each missing target, earliest first (D-04)."""
    city, decision = run.city, run.decision_time
    fingerprint = supabase_store.rating_config_fingerprint(city)
    for target in missing:
        iso = _iso(target)
        try:
            amps = day_ahead_forecast.compute_value(
                city, target, decision_time=decision, anchor=anchor, model=model)
            band = day_ahead_band.band_for(
                run.conn, city, target, amps, artifact, band_sha,
                config_fingerprint=fingerprint, cooling_model_sha256=model_entry["sha256"],
                decision_time=decision,
            )
            if day_ahead_forecast.out_of_bounds(city, amps):
                run.out_of_bounds.append(iso)  # logged by out_of_bounds, never suppressed
            if run.dry_run:
                run.computed[iso] = {"amps": amps, "lower": band.lower_amps, "upper": band.upper_amps,
                                     "band_source": band.source}
                log.info("%s %s: computed %.1f A (dry run, not stored)", city, iso, amps)
                continue
            row = day_ahead_forecast.build_row(
                city, target, issued_at=decision, amps=amps, band=band, model_entry=model_entry,
                anchor=anchor, run_ctx=run_ctx)
            if day_ahead_forecast.insert_row(run.conn, row):
                run.issued.append(iso)
                run.band_sources[iso] = band.source
                log.info("%s %s: issued %.1f A, band %s", city, iso, amps, band.source)
            else:
                # Another run stored this key first: first write wins, so it is present, not missing.
                run.already_present.append(iso)
                run.already_present_race = True
                log.info("%s %s: already present (stored by another run)", city, iso)
        except day_ahead_forecast.DayAheadNotIssued as exc:
            run.refuse([target], _reason("not issued", exc))
        except Exception as exc:  # noqa: BLE001 - one target never stops the others
            run.refuse([target], _reason("unexpected", exc))


def _execute(run: _Run) -> None:
    """The whole decision flow of one run (see the module docstring)."""
    city, decision = run.city, run.decision_time
    run.due = day_ahead_forecast.due_targets(decision)

    existing: set = set()
    if not run.dry_run:
        try:
            run.conn = supabase_store.connect()
            existing = day_ahead_forecast.existing_targets(run.conn, city, decision)
        except Exception as exc:  # noqa: BLE001 - a database that cannot be read issues nothing
            run.refuse(run.due, _reason("database", exc))
            return
    missing = day_ahead_forecast.missing_targets(run.due, existing)
    run.already_present = [_iso(t) for t in run.due if _utc(t) in existing]
    if not missing:
        log.info("%s: nothing due that is not already stored (%d due)", city, len(run.due))
        return

    # Trust: every input is verified before anything is computed from it (D-13a, D-16).
    try:
        artifact, band_sha = day_ahead_band.load_verified_band()
    except Exception as exc:  # noqa: BLE001
        run.refuse(missing, _reason("band artifact", exc))
        return
    try:
        loader = day_ahead_forecast.make_model_loader()
        model, model_entry = day_ahead_forecast.load_model(loader, city)
    except Exception as exc:  # noqa: BLE001
        run.refuse(missing, _reason("model", exc))
        return
    run.cooling_model_sha256 = model_entry["sha256"]
    try:
        anchor = day_ahead_forecast.read_anchor(city, decision)
    except Exception as exc:  # noqa: BLE001
        run.refuse(missing, _reason("anchor", exc))
        return
    run_ctx = supabase_store.run_context()

    _issue(run, missing, artifact=artifact, band_sha=band_sha, model=model, model_entry=model_entry,
           anchor=anchor, run_ctx=run_ctx)


def _write_output(path: str, document: dict) -> bool:
    """Write the document atomically; False when it could not be written."""
    directory = os.path.dirname(os.path.abspath(path))
    tmp = None
    try:
        os.makedirs(directory, exist_ok=True)
        handle, tmp = tempfile.mkstemp(dir=directory, prefix=".day_ahead_", suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(document, fh, indent=2)
        os.replace(tmp, path)
        return True
    except OSError as exc:
        log.error("cannot write the output %s: %s", path, type(exc).__name__)
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        return False


def main(argv=None, now=None) -> int:
    parser = argparse.ArgumentParser(
        description="Issue one city's missing day-ahead cooling forecasts (Phase 8; the runner starts this).",
        epilog="exit status: 0 the output was written (whatever the outcome); 1 the output could not "
               "be written; 2 a usage error",
    )
    parser.add_argument("--city", required=True, choices=list(config.LOCATIONS), help="city key")
    parser.add_argument("--output", required=True, help="write the outcome JSON to this path")
    parser.add_argument("--no-store", action="store_true",
                        help="local check only: no database, the TEST band, nothing inserted "
                             "(the runner never passes it)")
    args = parser.parse_args(argv)

    started = time.monotonic()
    decision = _utc(now) if now is not None else pd.Timestamp.now(tz="UTC")
    run = _Run(args.city, decision, dry_run=args.no_store)
    try:
        _execute(run)
    except Exception as exc:  # noqa: BLE001 - whatever escaped is recorded, never lost
        pending = [t for t in run.due if _iso(t) not in run.already_present
                   and _iso(t) not in run.issued and _iso(t) not in run.not_issued]
        run.refuse(pending, _reason("unexpected", exc))
        if not pending and not run.not_issued:
            run.explicit_outcome = "error"
            run.not_issued["run"] = _reason("unexpected", exc)
    finally:
        if run.conn is not None:
            try:
                run.conn.close()
            except Exception:  # noqa: BLE001
                pass
    wrote = _write_output(args.output, run.document(time.monotonic() - started))
    return 0 if wrote else 1


if __name__ == "__main__":
    from dotenv import load_dotenv

    # Script runs only: tests call main() with no credentials and must not load the owner's .env. An
    # existing variable, even an empty one, is not overridden (python-dotenv's default).
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    sys.exit(main())
