"""
Backfill loader (production-pipeline Phase 4: DB-03, DB-06)
==================================================
Loads the Phase 3 backfill archive into `public.city_rating`, so the forecast and
the detector have history in Postgres from the first scheduled run.

* Only the archive whose sha256 and byte size equal the committed Phase 3 manifest
  (`docs/data-science/decisions/real_data_validation/manifest.json`) is accepted.
* The rows are labelled provisional. Phase 3 recorded a NO-GO; the owner's
  2026-10-21 re-sequencing loads them anyway, and Phase 7's re-validation go
  (REVAL-01) decides when the label is lifted. The label is `PHASE3_CONFIG_VERSION`
  and `backfill_rating_basis(manifest)`, never the live `config.RATING_CONFIG_VERSION`
  or `config.RATING_BASIS`, which Phase 7 will change.
* Every row names the configuration and the models of the Phase 3 run (DB-06): the
  models come from the manifest, and the per-city config fingerprint is the live
  `rating_identity.rating_config_fingerprint` evaluated on `backend/config.py`,
  `city_point.py` and `thermal_model.py` as they were at the manifest's git head
  (materialized with `git show`, run in an isolated child process that proves it
  imported those copies and that no live backend module other than
  `rating_identity` was loaded: the child never imports the live store or what it
  pulls in). A Phase 7 change to the live config, or a live module that reads a
  new config name at import time, therefore cannot relabel Phase 3 rows or break
  the re-run.
* Inserts use `ON CONFLICT (city, valid_time) DO NOTHING`: a backfill never
  overwrites any row, live or backfill (a live retry overwrites under OD-7, a
  backfill never does). The whole load is one transaction, all or nothing.
* Parity is proven per city: the manifest's row count, the CSV's row count (after
  row validation and de-duplication) and the rows now in Postgres at the CSV's
  slots must agree; the exit status is 0 only when every city matches.

Run by the owner from the main checkout (it needs SUPABASE_DB_URL, loaded through
python-dotenv by the owner's command, and a git history holding the manifest's
commit). Prints counts only; it never prints the connection URL.

Exit codes: 0 loaded and every city matches (or a dry run), 1 refused or a
mismatch, 2 a manifest or archive file is missing.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

import pandas as pd

import config
import ercot_dlr_merger
import historical_archive
import rating_identity
import supabase_store

REPORT_SCHEMA = "supabase_backfill_parity/1"
MANIFEST_SCHEMA = "real_data_validation_manifest/1"
DEFAULT_MANIFEST = "docs/data-science/decisions/real_data_validation/manifest.json"

# The label of the rating assumption set at the manifest's git head, the same label
# plan 04-01 gave that set. Fixed here because config.RATING_CONFIG_VERSION will
# move with Phase 7.
PHASE3_CONFIG_VERSION = "v1-provisional-2026-10-13"

INSERT_COLUMNS = (
    "city",
    "valid_time",
    "rating_amps",
    "rating_mw",
    "static_rating_amps",
    "static_rating_mw",
    "line_voltage_kv",
    "power_factor",
    "status",
    "fallback",
    "fallback_gates",
    "alerts",
    "exhausted",
    "air_temp_c",
    "wind_perp_ms",
    "solar_radiation_wm2",
    "forecast_method",
    "rating_basis",
    "config_version",
    "config_fingerprint",
    "forecast_model_sha256",
    "anomaly_model_sha256",
    "origin",
    "run_id",
    "run_attempt",
    "pipeline_version",
    "schema_version",
)
INSERT_SQL = (
    f"insert into {supabase_store.CITY_RATING_TABLE} (\n  "
    + ", ".join(INSERT_COLUMNS)
    + ")\nvalues (\n  "
    + ", ".join(f"%({column})s" for column in INSERT_COLUMNS)
    + ")\non conflict (city, valid_time) do nothing"
)
COUNT_SQL = (
    f"select count(*) from {supabase_store.CITY_RATING_TABLE} "
    "where city = %(city)s and valid_time = any(%(slots)s)"
)

_HEX64 = re.compile(r"[0-9a-f]{64}")
_ARCHIVE_LABEL = "backfill"
# How much of a failing fingerprint child's redacted stderr the ValueError carries.
_CHILD_STDERR_MAX_CHARS = 4000


def _dig(mapping, dotted):
    """`mapping[a][b]...` for 'a.b...'; ValueError naming the first missing key."""
    value = mapping
    walked = []
    for key in dotted.split("."):
        walked.append(key)
        if not isinstance(value, dict) or key not in value:
            raise ValueError(f"manifest is missing {'.'.join(walked)}")
        value = value[key]
    return value


def load_manifest(path) -> dict:
    """Read the Phase 3 manifest; ValueError naming a wrong schema or a missing key."""
    with open(path, encoding="utf-8") as handle:
        manifest = json.load(handle)
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        raise ValueError(f"manifest schema is not {MANIFEST_SCHEMA}")
    for key in (
        "window.start", "window.end", "files.archive.path", "files.archive.bytes",
        "files.archive.sha256", "archive_rows_by_city", "git.head", "forecast_method", "models",
    ):
        _dig(manifest, key)
    return manifest


def backfill_rating_basis(manifest) -> str:
    """
    The provisional label of a backfill row (R3, OD-5). Built only from the manifest,
    never from config.RATING_BASIS.
    """
    window = manifest["window"]
    return (
        "PROVISIONAL (OD-5). Phase 3 backfill, window "
        f"{window['start']} to {window['end']}, code {manifest['git']['head'][:7]}: "
        "per-conductor amperes from the IEEE 738 thermal model at one rating point per city, "
        "one Drake ACSR conductor configuration for every city, owner-supplied static ratings "
        "(345 kV bundle averages divided by assumed subconductor counts) and assumed line bearings. "
        "Not a verified equipment-limited circuit rating. "
        "Provisional until Phase 7's re-validation go (REVAL-01)."
    )


def phase3_model_identity(manifest) -> dict:
    """
    DB-06: per city, the sha256 of the forecast and anomaly model files of the Phase 3
    run, taken from the manifest. The forecast hash is None when the manifest's
    forecast method has no model file. A missing key or a value that is not 64
    lower-case hex characters raises ValueError naming the key.
    """
    models = manifest["models"]
    has_artifact = manifest["forecast_method"] in supabase_store.FORECAST_ARTIFACT_PATHS

    def entry(name):
        if name not in models:
            raise ValueError(f"manifest models has no entry {name}")
        value = models[name]
        if not isinstance(value, str) or not _HEX64.fullmatch(value):
            raise ValueError(f"manifest models entry {name} is not a 64-character lower-case hex sha256")
        return value

    return {
        city: {
            "forecast_model_sha256": entry(f"forecast_{city}.joblib") if has_artifact else None,
            "anomaly_model_sha256": entry(f"anomaly_{city}.joblib"),
        }
        for city in config.LOCATIONS
    }


# The child process of phase3_config_fingerprints. It puts the materialized copies of
# the Phase 3 sources ahead of the live code, proves that config, city_point and
# thermal_model came from them, proves that the only module it loaded from the live
# backend directory is rating_identity (which imports only the standard library, config
# and city_point), and prints one fingerprint per city as JSON. It does not import
# supabase_store, so no other live module (and no config name such a module reads at
# import time) can break it. Run with `python -I`, so neither PYTHONPATH nor the working
# directory can change the import.
_FINGERPRINT_CHILD = """\
import json, os, sys
tmpdir, backend_dir, cities = sys.argv[1], sys.argv[2], sys.argv[3:]
sys.path[:0] = [tmpdir, backend_dir]
import config, city_point, thermal_model, rating_identity
root = os.path.realpath(tmpdir)
for module in (config, city_point, thermal_model):
    if os.path.dirname(os.path.realpath(module.__file__)) != root:
        sys.stderr.write(module.__name__ + " was not imported from the materialized copy\\n")
        sys.exit(3)
live = os.path.realpath(backend_dir)
extra = sorted(
    name for name, module in list(sys.modules.items())
    if getattr(module, "__file__", None)
    and os.path.dirname(os.path.realpath(module.__file__)) == live
    and name != "rating_identity"
)
if extra:
    sys.stderr.write("live backend modules were imported: " + ", ".join(extra) + "\\n")
    sys.exit(3)
print(json.dumps({city: rating_identity.rating_config_fingerprint(city) for city in cities}))
"""


def _repository_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _git_show(commit, path, repo_root) -> str:
    """`git show <commit>:<path>` (fixed argv); ValueError naming the commit and path on any failure."""
    try:
        return subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=repo_root, capture_output=True, text=True, timeout=10, check=True,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        raise ValueError(f"could not read {path} at commit {commit} with git show") from None


def _redacted_head_and_tail(text) -> str:
    """
    `text` redacted whole (the cut comes after redaction, so a longer limit never lets
    a secret through), then, past `_CHILD_STDERR_MAX_CHARS`, its first lines and its
    last lines: a traceback's call site is at the top and its exception at the bottom.
    """
    redacted = supabase_store.redact(text, limit=10 * len(text) + 100)
    if len(redacted) <= _CHILD_STDERR_MAX_CHARS:
        return redacted
    head = _CHILD_STDERR_MAX_CHARS // 4
    tail = _CHILD_STDERR_MAX_CHARS - head
    return redacted[:head] + "\n[...]\n" + redacted[-tail:]


def phase3_config_fingerprints(manifest, repo_root=None, git_show=None) -> dict:
    """
    DB-06: each city's `rating_identity.rating_config_fingerprint` evaluated on the
    sources of the manifest's git head, so live and backfill fingerprints are
    comparable and the recipe is not copied by hand.

    The three `rating_identity.RATING_CONFIG_SOURCE_FILES` are read with `git_show(commit, path)` (default:
    `_git_show`, looked up at call time), written under their base names into a
    temporary directory and evaluated in an isolated child process that refuses to
    answer unless it imported them from there. ValueError on any failure.
    """
    commit = manifest["git"]["head"]
    root = repo_root or _repository_root()
    if git_show is None:
        def git_show(c, p):
            return _git_show(c, p, root)

    backend_dir = os.path.dirname(os.path.abspath(__file__))
    with tempfile.TemporaryDirectory() as tmpdir:
        for path in rating_identity.RATING_CONFIG_SOURCE_FILES:
            text = git_show(commit, path)
            with open(os.path.join(tmpdir, os.path.basename(path)), "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        try:
            done = subprocess.run(
                [sys.executable, "-I", "-c", _FINGERPRINT_CHILD, tmpdir, backend_dir, *config.LOCATIONS],
                capture_output=True, text=True, timeout=120,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            raise ValueError(
                "could not evaluate the Phase 3 config fingerprints: "
                + supabase_store.redact(type(exc).__name__)
            ) from None
    if done.returncode != 0:
        # The whole stderr (a traceback names the module and the first lines name the call),
        # redacted before it is cut, never only its last line.
        stderr = (done.stderr or "").strip() or f"child exited with status {done.returncode}"
        raise ValueError(
            "could not evaluate the Phase 3 config fingerprints: " + _redacted_head_and_tail(stderr)
        )
    try:
        fingerprints = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise ValueError("the Phase 3 fingerprint child printed no JSON") from None
    if (
        not isinstance(fingerprints, dict)
        or set(fingerprints) != set(config.LOCATIONS)
        or not all(isinstance(v, str) and _HEX64.fullmatch(v) for v in fingerprints.values())
    ):
        raise ValueError("the Phase 3 fingerprint child did not return a 64-hex fingerprint for every city")
    return {city: fingerprints[city] for city in config.LOCATIONS}


def _parse_fallback(value) -> bool:
    """The archive's fallback flag, read back as a bool or as text in any case."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def prepare_rows(csv_path, manifest, identity):
    """
    The archive as `INSERT_COLUMNS` rows plus the counts the parity report needs.

    `identity` holds, per city, config_fingerprint, forecast_model_sha256 and
    anomaly_model_sha256. Rows the archive's own row check rejects are dropped and
    counted. Any row that is not on a whole UTC hour or lies outside the manifest
    window, belongs to another city, or has no usable rating raises ValueError
    naming the count, before anything is sent to a database. Two or more rows for
    one city and UTC instant keep the first computed row in file order, and only
    when every row is a fallback row the first fallback row; the others are counted
    per city and the kept rows stay in file order. This is the archive's own rule
    (`historical_archive.append_observation`: a computed row may follow fallback
    rows and then owns the slot) and the rule Phase 2's `duplicate` flag applies
    (`data_cleaning.clean_history` judges it over computed rows only), so a
    fallback row followed by a computed row loads the computed row.
    """
    rows_read = len(historical_archive.read_history(csv_path, validate=False))
    frame = historical_archive.read_history(csv_path, validate=True)
    dropped_by_validation = rows_read - len(frame)

    window_start = pd.Timestamp(manifest["window"]["start"])
    window_end = pd.Timestamp(manifest["window"]["end"])
    window_start = window_start.tz_localize("UTC") if window_start.tzinfo is None else window_start.tz_convert("UTC")
    window_end = window_end.tz_localize("UTC") if window_end.tzinfo is None else window_end.tz_convert("UTC")

    times = pd.to_datetime(frame["datetime_utc"], utc=True, format="ISO8601", errors="coerce")
    bad_time = times.isna() | (times != times.dt.floor("h")) | (times < window_start) | (times > window_end)
    if bad_time.any():
        raise ValueError(
            f"{int(bad_time.sum())} archive row(s) are not on a whole UTC hour or lie outside the "
            f"manifest window [{manifest['window']['start']}, {manifest['window']['end']}]"
        )
    outside = ~frame["city"].isin(config.LOCATIONS)
    if outside.any():
        raise ValueError(f"{int(outside.sum())} archive row(s) name a city outside config.LOCATIONS")

    amps = pd.to_numeric(frame["dlr_amps"], errors="coerce")
    static = pd.to_numeric(frame["static_rating"], errors="coerce")
    unusable = ~(amps.map(lambda v: supabase_store.finite(v) is not None and v > 0)
                 & static.map(lambda v: supabase_store.finite(v) is not None and v > 0))
    if unusable.any():
        raise ValueError(f"{int(unusable.sum())} archive row(s) have no finite positive dlr_amps or static_rating")

    frame = frame.assign(_time=times)
    # The first computed row of a slot owns it, and a fallback row owns it only when no
    # computed row exists (the archive's rule and Phase 2's `duplicate` flag). read_history
    # sorts stably, so rows for one instant are still in file order here. Rank computed
    # rows ahead of fallback rows with a stable sort (file order kept inside each class),
    # mark duplicates keep-first over that ranking, then map the mark back to the original
    # index so the kept rows stay in file order.
    is_fallback = frame["fallback"].map(_parse_fallback)
    ranked = frame.assign(_is_fallback=is_fallback).sort_values("_is_fallback", kind="mergesort")
    duplicate = ranked.duplicated(subset=["city", "_time"], keep="first").reindex(frame.index)
    duplicates_dropped = {city: int(((frame["city"] == city) & duplicate).sum()) for city in config.LOCATIONS}
    frame = frame[~duplicate]

    voltage = float(config.LINE_VOLTAGE_KV)
    power_factor = float(config.POWER_FACTOR)
    basis = backfill_rating_basis(manifest)
    sha = supabase_store.file_sha256(csv_path)
    run_id = f"{_ARCHIVE_LABEL}-{sha[:12]}"
    version = manifest["git"]["head"][:7]
    method = manifest["forecast_method"]

    rows = []
    for record in frame.to_dict(orient="records"):
        city = record["city"]
        rating = float(record["dlr_amps"])
        static_rating = float(record["static_rating"])
        ident = identity[city]
        rows.append({
            "city": city,
            "valid_time": record["_time"].to_pydatetime(),
            "rating_amps": rating,
            "rating_mw": float(ercot_dlr_merger.amps_to_mw(rating, voltage, power_factor)),
            "static_rating_amps": static_rating,
            "static_rating_mw": float(ercot_dlr_merger.amps_to_mw(static_rating, voltage, power_factor)),
            "line_voltage_kv": voltage,
            "power_factor": power_factor,
            "status": str(record["status"]),
            "fallback": _parse_fallback(record["fallback"]),
            "fallback_gates": [],
            "alerts": [],
            "exhausted": False,
            "air_temp_c": supabase_store.finite(record["air_temp"]),
            # The archive's wind_speed is the component projected across the line.
            "wind_perp_ms": supabase_store.finite(record["wind_speed"]),
            "solar_radiation_wm2": supabase_store.finite(record["solar_radiation"]),
            "forecast_method": method,
            "rating_basis": basis,
            "config_version": PHASE3_CONFIG_VERSION,
            "config_fingerprint": ident["config_fingerprint"],
            "forecast_model_sha256": ident["forecast_model_sha256"],
            "anomaly_model_sha256": ident["anomaly_model_sha256"],
            "origin": "backfill",
            "run_id": run_id,
            "run_attempt": 1,
            "pipeline_version": version,
            "schema_version": 1,
        })
    csv_rows = {city: sum(1 for row in rows if row["city"] == city) for city in config.LOCATIONS}
    stats = {
        "rows_read": rows_read,
        "rows_dropped_by_validation": dropped_by_validation,
        "duplicates_dropped": duplicates_dropped,
        "csv_rows": csv_rows,
    }
    return rows, stats


def count_at_slots(conn, rows) -> dict:
    """Per city, the rows now in the table at that city's slots (any origin)."""
    counts = {}
    for city in config.LOCATIONS:
        slots = [row["valid_time"] for row in rows if row["city"] == city]
        if not slots:
            counts[city] = 0
            continue
        counts[city] = int(conn.execute(COUNT_SQL, {"city": city, "slots": slots}).fetchone()[0])
    return counts


def load(conn, rows, dry_run=False) -> dict:
    """
    Insert `rows` with DO NOTHING inside one transaction and return, per city, the
    number of rows at the CSV's slots before and after. A dry run counts and sends
    no insert.
    """
    with conn.transaction():
        before = count_at_slots(conn, rows)
        if not dry_run:
            with conn.cursor() as cursor:
                cursor.executemany(INSERT_SQL, rows)
        after = count_at_slots(conn, rows)
    return {city: {"before": before[city], "after": after[city]} for city in config.LOCATIONS}


def parity_report(manifest, csv_sha256, stats, counts, identity, dry_run=False) -> dict:
    """
    The deterministic parity report (no timestamp). A city matches only when the
    rows in Postgres at the CSV's slots, the CSV's rows and the manifest's rows are
    equal. `dry_run` leaves the inserted, skipped and match fields None.
    """
    archive = manifest["files"]["archive"]
    per_city = {}
    for city in config.LOCATIONS:
        manifest_rows = int(manifest["archive_rows_by_city"].get(city, 0))
        csv_rows = int(stats["csv_rows"][city])
        before = int(counts[city]["before"])
        after = int(counts[city]["after"])
        inserted = after - before
        per_city[city] = {
            "manifest_rows": manifest_rows,
            "csv_rows": csv_rows,
            "duplicates_dropped": int(stats["duplicates_dropped"][city]),
            "db_rows_at_csv_slots": after,
            "inserted": None if dry_run else inserted,
            "skipped_existing": None if dry_run else csv_rows - inserted,
            "match": None if dry_run else (after == csv_rows == manifest_rows),
        }
    return {
        "schema": REPORT_SCHEMA,
        "archive": {"path": archive["path"], "sha256": csv_sha256, "bytes": int(archive["bytes"])},
        "window": dict(manifest["window"]),
        "rows_read": int(stats["rows_read"]),
        "rows_dropped_by_validation": int(stats["rows_dropped_by_validation"]),
        "per_city": per_city,
        "identity": {
            "config_commit": manifest["git"]["head"],
            "config_version": PHASE3_CONFIG_VERSION,
            "forecast_method": manifest["forecast_method"],
            "per_city": {city: dict(identity[city]) for city in config.LOCATIONS},
        },
        "all_match": None if dry_run else all(entry["match"] for entry in per_city.values()),
    }


def _print_table(report) -> None:
    print(f"{'city':<16}{'manifest':>9}{'csv':>7}{'dups':>6}{'db':>7}{'inserted':>10}{'skipped':>9}  match")
    for city, entry in report["per_city"].items():
        match = "dry run" if entry["match"] is None else ("yes" if entry["match"] else "MISMATCH")
        inserted = "-" if entry["inserted"] is None else entry["inserted"]
        skipped = "-" if entry["skipped_existing"] is None else entry["skipped_existing"]
        print(
            f"{city:<16}{entry['manifest_rows']:>9}{entry['csv_rows']:>7}{entry['duplicates_dropped']:>6}"
            f"{entry['db_rows_at_csv_slots']:>7}{inserted:>10}{skipped:>9}  {match}"
        )
    print(f"rows read: {report['rows_read']}, dropped by validation: {report['rows_dropped_by_validation']}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Load the Phase 3 backfill archive into public.city_rating.")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--csv", default=None, help="archive path (default: the manifest's files.archive.path)")
    parser.add_argument("--report", default=None, help="write the parity report JSON here")
    parser.add_argument("--dry-run", action="store_true", help="count only; insert nothing")
    args = parser.parse_args(argv)

    if not os.path.exists(args.manifest):
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    try:
        manifest = load_manifest(args.manifest)
    except (ValueError, OSError) as exc:
        print(f"unusable manifest {args.manifest}: {exc}")
        return 1
    csv_path = args.csv or manifest["files"]["archive"]["path"]
    if not os.path.exists(csv_path):
        print(f"archive not found: {csv_path}", file=sys.stderr)
        return 2

    expected = manifest["files"]["archive"]
    csv_sha = supabase_store.file_sha256(csv_path)
    if csv_sha != expected["sha256"]:
        print("archive does not match the Phase 3 manifest (sha256)")
        return 1
    if os.path.getsize(csv_path) != int(expected["bytes"]):
        print("archive does not match the Phase 3 manifest (bytes)")
        return 1

    try:
        identity = phase3_model_identity(manifest)
        fingerprints = phase3_config_fingerprints(manifest)
        for city in config.LOCATIONS:
            identity[city]["config_fingerprint"] = fingerprints[city]
        rows, stats = prepare_rows(csv_path, manifest, identity)
    except ValueError as exc:
        print(f"backfill stopped before any insert: {exc}")
        return 1

    print(f"Phase 3 identity: code {manifest['git']['head'][:7]}, config_version {PHASE3_CONFIG_VERSION}, "
          f"forecast_method {manifest['forecast_method']}")
    for city in config.LOCATIONS:
        print(f"  {city}: config_fingerprint {identity[city]['config_fingerprint'][:12]}")

    try:
        conn = supabase_store.connect()
    except supabase_store.StoreError as exc:
        print(str(exc))
        return 1
    try:
        counts = load(conn, rows, dry_run=args.dry_run)
    except Exception as exc:  # noqa: BLE001 - reported redacted; the transaction was rolled back
        print(f"backfill load failed and was rolled back: {type(exc).__name__}: {supabase_store.redact(str(exc))}")
        return 1
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    report = parity_report(manifest, csv_sha, stats, counts, identity, dry_run=args.dry_run)
    _print_table(report)
    if args.report:
        directory = os.path.dirname(args.report)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.dry_run:
        print("dry run: nothing was inserted")
        return 0
    if report["all_match"]:
        print("parity: every city matches")
        return 0
    print("parity: MISMATCH -- see the table above")
    return 1


if __name__ == "__main__":
    sys.exit(main())
