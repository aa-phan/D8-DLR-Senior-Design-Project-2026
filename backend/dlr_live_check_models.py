"""
Pre-flight for the live workflow (production-pipeline Phase 5, PIPE-02, OD-3,
OD-10): fail the job, before any city is rated, when a per-city ML model is
missing, altered or unloadable.

The runner gets the eight live models (`forecast_{CITY}.joblib` and
`anomaly_{CITY}.joblib` for every city in `config.LOCATIONS`) only through
`actions/checkout`: `data/models/` is otherwise git-ignored, and the runner can
neither retrain nor reach the owner's machine (OD-10 commits exactly these files
through a `.gitignore` carve-out, following `data/shadow/models`). A missing model
would not stop a run -- the pipeline would continue without an ML forecast and the
detector would lose its model branch, silently -- so this check turns that into a
red job.

Three layers, in order:

1. Presence: every required path exists.
2. Integrity: each file's SHA-256 equals its line in
   `data/models/LIVE_ARTIFACT_HASHES.sha256` (sha256sum format, repo-relative
   paths). A retrain changes the hash, so promoting a retrained model means
   regenerating the manifest with `--write-manifest` and committing both.
3. Strict load: only when layers 1 and 2 found nothing, the production loaders
   (`ampacity_forecast._load_model`, `anomaly_detector._load_city_model`) run for
   every city, so an artifact that hashes correctly but will not deserialize under
   the pinned scikit-learn is also caught.

Why hashes come before any load: a joblib file is a pickle, and unpickling runs
code inside a process that holds the database URL and provider secrets. Nothing is
deserialized until every required artifact has matched the manifest. The manifest
is tracked in the same commit as the artifacts, so it defends against a stray or
accidental artifact change (a local retrain committed without promotion), not
against a collaborator who can edit both -- that trust is the same as for code.

Artifact paths come from the two production resolvers, never a re-typed filename
template. Exit 0 = all eight verified; exit 1 = the full list of problems.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from datetime import datetime, timezone

import ampacity_forecast
import anomaly_detector
import config

MANIFEST_PATH = os.path.join("data", "models", "LIVE_ARTIFACT_HASHES.sha256")

KINDS: tuple[str, ...] = ("forecast", "anomaly")

_MANIFEST_LINE = re.compile(r"^([0-9a-f]{64}) [ *](\S.*)$")
_MESSAGE_LIMIT = 300


def _key(path: str) -> str:
    """Manifest paths use forward slashes whatever the platform."""
    return path.replace(os.sep, "/")


def required_artifacts() -> list[tuple[str, str, str]]:
    """(kind, city, path) for every live model, paths from the production resolvers."""
    resolvers = {
        "forecast": ampacity_forecast._model_path_for,
        "anomaly": anomaly_detector._model_path_for,
    }
    return [
        (kind, city, resolvers[kind](city))
        for city in config.LOCATIONS
        for kind in KINDS
    ]


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest(path: str) -> dict[str, str]:
    """
    {path: sha256 hex} from a sha256sum-format file. `#` comments and blank lines
    are ignored. Raises OSError when the file cannot be read and ValueError for a
    malformed line or a path listed twice with different hashes.
    """
    entries: dict[str, str] = {}
    with open(path, encoding="utf-8") as fh:
        for number, raw in enumerate(fh, start=1):
            line = raw.rstrip("\r\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = _MANIFEST_LINE.match(line)
            if not match:
                raise ValueError(f"line {number} is not '<64 hex>  <path>'")
            digest, target = match.group(1), match.group(2)
            if entries.get(target, digest) != digest:
                raise ValueError(f"line {number} lists {target} again with a different hash")
            entries[target] = digest
    return entries


def check(manifest_path: str = MANIFEST_PATH, load: bool = True) -> list[str]:
    """
    Every problem found, as printable lines; an empty list means all eight live
    models are present, match the manifest and (when `load`) load strictly.
    """
    problems: list[str] = []
    entries: dict[str, str] = {}
    manifest_ok = True
    try:
        entries = read_manifest(manifest_path)
    except OSError as exc:
        manifest_ok = False
        problems.append(f"manifest missing or unreadable: {manifest_path}: {type(exc).__name__}: {exc}")
    except ValueError as exc:
        manifest_ok = False
        problems.append(f"manifest malformed: {manifest_path}: {exc}")
    else:
        if not entries:
            manifest_ok = False
            problems.append(f"manifest has no entries: {manifest_path}")

    for kind, city, path in required_artifacts():
        if not os.path.isfile(path):
            problems.append(f"missing artifact: {path} ({city} {kind})")
            continue
        if not manifest_ok:
            continue  # the manifest problem above already fails the run; no per-file noise
        expected = entries.get(_key(path))
        if expected is None:
            problems.append(f"manifest {manifest_path} has no entry for {path}")
            continue
        try:
            actual = sha256_file(path)
        except OSError as exc:
            problems.append(f"unreadable artifact: {path} ({city} {kind}): {type(exc).__name__}: {exc}")
            continue
        if actual != expected:
            problems.append(f"hash mismatch: {path} ({city} {kind}): manifest {expected}, file {actual}")

    if problems or not load:
        return problems

    loaders = (
        ("forecast", ampacity_forecast._load_model),
        ("anomaly", anomaly_detector._load_city_model),
    )
    for city in config.LOCATIONS:
        for kind, loader in loaders:
            try:
                loader(city)
            except Exception as exc:  # any failure to deserialize is a failed pre-flight
                message = str(exc)[:_MESSAGE_LIMIT]
                problems.append(f"load failed: {city} {kind}: {type(exc).__name__}: {message}")
    return problems


def write_manifest(manifest_path: str = MANIFEST_PATH) -> list[str]:
    """
    Hash the eight resolved artifacts into `manifest_path`, sorted by path, under a
    dated `#` header line that says how the file was made. Returns
    the missing paths as problems, and writes nothing when there are any. Never
    deserializes an artifact.
    """
    artifacts = required_artifacts()
    problems = [
        f"missing artifact: {path} ({city} {kind})"
        for kind, city, path in artifacts
        if not os.path.isfile(path)
    ]
    if problems:
        return problems
    header = (
        f"# {datetime.now(timezone.utc).date().isoformat()} SHA-256 of the models promoted to the live workflow "
        f"(regenerate with: PYTHONPATH=backend python backend/dlr_live_check_models.py --write-manifest)"
    )
    lines = [header] + [
        f"{sha256_file(path)}  {_key(path)}" for path in sorted(_key(path) for _, _, path in artifacts)
    ]
    with open(manifest_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help=f"hash the eight live models into {MANIFEST_PATH} (run after promoting a retrain)",
    )
    args = parser.parse_args(argv)

    if args.write_manifest:
        problems = write_manifest(MANIFEST_PATH)
        if problems:
            print(f"ERROR: manifest not written, {len(problems)} live model artifact(s) missing:", file=sys.stderr)
            for line in problems:
                print(f"  - {line}", file=sys.stderr)
            return 1
        print(f"Wrote {len(required_artifacts())} entries to {MANIFEST_PATH}")
        return 0

    problems = check(MANIFEST_PATH)
    if problems:
        print(
            f"ERROR: {len(problems)} live model problem(s); a live run must not rate with a missing, "
            f"altered or unloadable model (OD-3):",
            file=sys.stderr,
        )
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
        return 1
    print(f"OK: all {len(required_artifacts())} live model artifacts present and match {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
