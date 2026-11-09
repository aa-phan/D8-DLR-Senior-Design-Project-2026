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

Day-ahead tier (Phase 8, DAY-04, D-13, D-13a): the four served cooling files and the
day-ahead band artifact are listed in the same manifest and verified the same way
(presence, sha256, then a strict load through the hash-checking day-ahead loaders; hash
before any load, so nothing day-ahead is unpickled while a day-ahead hash problem is
open). Their problems are only GitHub `::warning::` lines: the exit code comes from the
eight live models alone, so a day-ahead problem can never stop live ratings. The
day-ahead stage refuses a mismatched file itself, and an offline test fails hard on any
mismatch between the committed manifest and the committed files. That test runs in CI
(.github/workflows/day_ahead_manifest_check.yml) on every pull request and every push to
main, and the job fails if any of its tests is skipped. The
whole tier runs inside one guard (it catches Exception and SystemExit, not
KeyboardInterrupt), so no error inside it can change the exit code.
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
DAY_AHEAD_KINDS: tuple[str, ...] = ("day_ahead_cooling", "day_ahead_band")

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


def required_day_ahead_artifacts() -> list[tuple[str, str, str]]:
    """
    (kind, city, path) for the four served cooling files and the band artifact (D-13, D-14).
    The cooling paths come from `day_ahead_forecast.serving_model_path`, never a re-typed
    template. Both day-ahead modules import this module (directly or through
    forecast_conductor_refit), so they are imported here, inside the function.
    """
    import day_ahead_band
    import day_ahead_forecast

    artifacts = [
        ("day_ahead_cooling", city, day_ahead_forecast.serving_model_path(city))
        for city in config.LOCATIONS
    ]
    artifacts.append(("day_ahead_band", "", day_ahead_band.BAND_ARTIFACT_PATH))
    return artifacts


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


def _read_manifest_state(manifest_path: str) -> tuple[dict[str, str], bool, list[str]]:
    """(entries, manifest_ok, problems) for a manifest file; a bad manifest is one problem, not per-file noise."""
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
    return entries, manifest_ok, problems


def _presence_and_hash_problems(
    artifacts: list[tuple[str, str, str]],
    entries: dict[str, str],
    manifest_ok: bool,
    manifest_path: str,
) -> list[str]:
    """Presence, manifest entry and sha256 problems for `artifacts`; nothing is deserialized."""
    problems: list[str] = []
    for kind, city, path in artifacts:
        label = f"{city} {kind}".strip()
        if not os.path.isfile(path):
            problems.append(f"missing artifact: {path} ({label})")
            continue
        if not manifest_ok:
            continue  # the manifest problem already fails the check; no per-file noise
        expected = entries.get(_key(path))
        if expected is None:
            problems.append(f"manifest {manifest_path} has no entry for {path}")
            continue
        try:
            actual = sha256_file(path)
        except OSError as exc:
            problems.append(f"unreadable artifact: {path} ({label}): {type(exc).__name__}: {exc}")
            continue
        if actual != expected:
            problems.append(f"hash mismatch: {path} ({label}): manifest {expected}, file {actual}")
    return problems


def check(manifest_path: str = MANIFEST_PATH, load: bool = True) -> list[str]:
    """
    Every problem found, as printable lines; an empty list means all eight live
    models are present, match the manifest and (when `load`) load strictly.
    """
    entries, manifest_ok, problems = _read_manifest_state(manifest_path)
    problems += _presence_and_hash_problems(required_artifacts(), entries, manifest_ok, manifest_path)

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


def check_day_ahead(manifest_path: str = MANIFEST_PATH, load: bool = True) -> list[str]:
    """
    Every day-ahead problem found, as printable lines (D-13a: the caller reports them as
    warnings). Presence and sha256 for every day-ahead file come first; only when none is
    open, and `load` is true, each cooling model is loaded strictly through the day-ahead
    hash-checking loader and the band through `load_verified_band`.
    """
    artifacts = required_day_ahead_artifacts()
    if not artifacts:
        return []
    entries, manifest_ok, problems = _read_manifest_state(manifest_path)
    problems += _presence_and_hash_problems(artifacts, entries, manifest_ok, manifest_path)
    if problems or not load:
        return problems

    import day_ahead_band
    import day_ahead_contract
    import day_ahead_forecast

    loader = day_ahead_forecast.make_model_loader()
    for kind, city, path in artifacts:
        try:
            if kind == "day_ahead_cooling":
                loader(city, day_ahead_contract.FORECAST_METHOD)
            else:
                day_ahead_band.load_verified_band(path=path, manifest_path=manifest_path)
        except Exception as exc:  # any failure to load is a day-ahead warning
            label = f"{city} {kind}".strip()
            message = str(exc)[:_MESSAGE_LIMIT]
            problems.append(f"load failed: {label}: {type(exc).__name__}: {message}")
    return problems


def write_manifest(manifest_path: str = MANIFEST_PATH) -> list[str]:
    """
    Hash the eight resolved live artifacts and the day-ahead artifacts (four cooling files
    and the band) into `manifest_path`, sorted by path, under a dated `#` header line that
    says how the file was made. Returns the missing paths as problems, and writes nothing
    when there are any. Never deserializes an artifact.
    """
    artifacts = required_artifacts() + required_day_ahead_artifacts()
    problems = [
        f"missing artifact: {path} ({f'{city} {kind}'.strip()})"
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


def _escape_workflow_data(text: str) -> str:
    """GitHub's escaping for workflow-command data: % to %25, CR to %0D, LF to %0A, so the text stays on one line."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _print_day_ahead_warnings(problems: list[str]) -> None:
    for line in problems:
        print(f"::warning title=day-ahead artifact::{_escape_workflow_data(line)}")
    print(
        f"WARNING: {len(problems)} day-ahead artifact problem(s); live ratings are not affected (D-13a); "
        f"the day-ahead stage will refuse these files"
    )
    sys.stdout.flush()


def _crash_text(exc: BaseException) -> str:
    """One day-ahead problem for an exception raised inside the tier; names the type even if the text fails."""
    name = type(exc).__name__
    try:
        return f"day-ahead check failed: {name}: {str(exc)[:_MESSAGE_LIMIT]}"
    except Exception:  # noqa: BLE001 - str(exc) itself failed
        return f"day-ahead check failed: {name}"


def _day_ahead_tier(manifest_path: str) -> None:
    artifacts = required_day_ahead_artifacts()
    if not artifacts:
        return
    problems = check_day_ahead(manifest_path)
    if problems:
        _print_day_ahead_warnings(problems)
    else:
        print(f"OK: all {len(artifacts)} day-ahead artifacts present and match {manifest_path}")


def _run_day_ahead_tier(manifest_path: str) -> None:
    """
    The whole day-ahead tier under one guard (D-13a): the lazy imports, the artifact list, the
    check and its printing. Exception and SystemExit become one escaped warning; KeyboardInterrupt
    propagates so a cancelled job stops. The caller has already fixed the exit code from the
    live models, and nothing here can change it.
    """
    try:
        _day_ahead_tier(manifest_path)
    except (Exception, SystemExit) as exc:  # noqa: BLE001 - see docstring
        try:
            _print_day_ahead_warnings([_crash_text(exc)])
        except (Exception, SystemExit):  # noqa: BLE001 - even a broken stdout must not change the code
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--write-manifest",
        action="store_true",
        help=f"hash the eight live models and the day-ahead artifacts into {MANIFEST_PATH} (run after promoting a retrain)",
    )
    args = parser.parse_args(argv)

    if args.write_manifest:
        problems = write_manifest(MANIFEST_PATH)
        if problems:
            print(f"ERROR: manifest not written, {len(problems)} artifact(s) missing:", file=sys.stderr)
            for line in problems:
                print(f"  - {line}", file=sys.stderr)
            return 1
        print(f"Wrote {len(required_artifacts()) + len(required_day_ahead_artifacts())} entries to {MANIFEST_PATH}")
        return 0

    # The exit code comes from the eight live models alone (OD-3); the day-ahead tier below cannot change it.
    problems = check(MANIFEST_PATH)
    exit_code = 0
    if problems:
        exit_code = 1
        print(
            f"ERROR: {len(problems)} live model problem(s); a live run must not rate with a missing, "
            f"altered or unloadable model (OD-3):",
            file=sys.stderr,
        )
        for line in problems:
            print(f"  - {line}", file=sys.stderr)
    else:
        print(f"OK: all {len(required_artifacts())} live model artifacts present and match {MANIFEST_PATH}")
    _run_day_ahead_tier(MANIFEST_PATH)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
