"""
Historical Archive (Phase 4 Wave 0 support for C9, C10)
==================================================
This module is shared support for C9 (ampacity forecasting) and C10
(learned anomaly detection) — it is not a spec component of its own. It
holds one row per city per run (one rating point per city, see
`docs/data-science/decisions/point_scope.md`), and it has exactly one write
call site, `city_rating._archive_city_result`.

The row shape (`ARCHIVE_COLUMNS`) reuses `units_def.PIPELINE_SCHEMA`'s
column spellings for every numeric field so `validate_pipeline_row` vets
an archive row with no change to that validator and no parallel schema
object (T-04-01, the archive-poisoning mitigation). Storage is an
append-only CSV at `config.HISTORICAL_ARCHIVE_PATH`, unbounded retention
this phase (D-09) — this module does not implement rotation/compaction.

Column list locked at the Plan 04-01 Task 1 checkpoint (D-07 — one-way:
once `ampacity_forecast.py`/`anomaly_detector.py` read this shape and rows
accumulate, changing it means migrating or discarding real history):
    datetime_utc, city, air_temp, wind_speed, solar_radiation,
    dlr_amps, static_rating, status, fallback, schema_version

Point-scope change: the `corridor` column is now `city` (same position), and
the corridor-era `bottleneck_index` column (always null for per-city rows) was
dropped on 2026-10-13. Archive files written earlier (header has `corridor`
and/or `bottleneck_index`) are still readable: `read_history` exposes
`corridor` as `city` and returns any extra legacy column as it is, and
`append_observation` appends in the file's existing header order so columns
never misalign (a legacy `bottleneck_index` is written as empty).
"""

import logging
import os

import pandas as pd

import config
import units_def

logger = logging.getLogger(__name__)

# D-07 checkpoint decision (Task 1, `proposed` option): the 10-column row
# shape every Phase 4 model reads. schema_version starts at 1.
ARCHIVE_SCHEMA_VERSION: int = 1

ARCHIVE_COLUMNS: list[str] = [
    "datetime_utc",
    "city",
    "air_temp",
    "wind_speed",
    "solar_radiation",
    "dlr_amps",
    "static_rating",
    "status",
    "fallback",
    "schema_version",
]


def build_archive_row(
    city: str,
    datetime_utc,
    observation: dict,
    check_result: dict,
    static_rating: float,
) -> dict:
    """
    Assemble one archive row from a `DLRSafetyMonitor.run_check` cycle.

    `observation` is the reading dict `run_check` consumes (keys `temp`,
    `wind`, `solar` per `city_rating._OBSERVATION_FIELD_MAP`);
    translated here back to the `PIPELINE_SCHEMA` spellings `air_temp`,
    `wind_speed`, `solar_radiation`. `check_result` is the mapping
    `run_check` returned — its rating, status and fallback flag are read
    from it directly, never recomputed here.

    Every numeric field is `float(...)`-wrapped at assignment
    (RESEARCH.md Pitfall 2). Returns keys in `ARCHIVE_COLUMNS` order.
    """
    row = {
        "datetime_utc": datetime_utc,
        "city": city,
        "air_temp": float(observation["temp"]),
        "wind_speed": float(observation["wind"]),
        "solar_radiation": float(observation["solar"]),
        "dlr_amps": float(check_result["rating"]),
        "static_rating": float(static_rating),
        "status": check_result["status"],
        "fallback": bool(check_result["fallback"]),
        "schema_version": ARCHIVE_SCHEMA_VERSION,
    }
    return {col: row[col] for col in ARCHIVE_COLUMNS}


def _validation_row(row: dict) -> dict:
    """
    Build a validation-only copy of an archive row with a placeholder
    `wind_direction`, satisfying `units_def.PIPELINE_SCHEMA`'s
    required-column check for a column this archive never stores or
    reads (city observations only ever carry the already-resolved
    perpendicular wind component, `wind_speed`, never a raw direction).
    Shared by `append_observation` and `read_history` so the placeholder
    has exactly one definition.
    """
    validation_row = dict(row)
    validation_row.setdefault("wind_direction", 0.0)
    return validation_row


def _normalize_row_keys(row: dict) -> dict:
    """Accept a corridor-era row (`corridor` key) by exposing it as `city`."""
    if "city" not in row and "corridor" in row:
        row = dict(row)
        row["city"] = row.pop("corridor")
    return row


def _existing_header(path: str):
    """Header columns of an existing non-empty CSV at `path`, else None."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    return list(pd.read_csv(path, nrows=0).columns)


def append_observation(row: dict, path: str = None) -> bool:
    """
    Append one archive row to the CSV at `path` (defaults to
    `config.HISTORICAL_ARCHIVE_PATH`).

    Archival is best-effort, the rating path is not (RESEARCH.md
    Pitfall 6, T-04-03): the entire body is wrapped in one
    `try`/`except Exception` covering validation, directory creation and
    the write itself, so a disk problem degrades to "not archived this
    cycle," never to "no rating this cycle." This function is incapable
    of raising.

    A row that fails `units_def.validate_pipeline_row` (T-04-01 — the
    archive-poisoning mitigation) is logged and rejected, not persisted.
    """
    if path is None:
        path = config.HISTORICAL_ARCHIVE_PATH

    # RESEARCH.md Pitfall 6 / T-04-03: archival is best-effort, the rating
    # path is not. The whole body -- validation, makedirs, and the write
    # itself -- lives inside this one try/except so a disk problem
    # degrades to "not archived this cycle," never to "no rating this
    # cycle."
    try:
        row = _normalize_row_keys(row)
        # PIPELINE_SCHEMA marks wind_direction required=True, but the
        # archive row (ARCHIVE_COLUMNS) deliberately has no direction
        # column at all -- see _validation_row's docstring. The placeholder
        # it adds is never persisted to the actual archive row.
        violations = units_def.validate_pipeline_row(_validation_row(row), strict=False)
        if violations:
            city = row.get("city", "<unknown city>")
            for msg in violations:
                logger.warning("historical_archive rejected row for %s: %s", city, msg)
            return False

        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        existing_header = _existing_header(path)
        if existing_header is None:
            pd.DataFrame([row], columns=ARCHIVE_COLUMNS).to_csv(
                path, mode="a", header=True, index=False
            )
        else:
            # Append in the file's own column order. A corridor-era file has
            # `corridor` where `city` now sits; write the city under it.
            legacy_row = dict(row)
            if "corridor" in existing_header and "city" not in existing_header:
                legacy_row["corridor"] = legacy_row.pop("city")
            pd.DataFrame([legacy_row], columns=existing_header).to_csv(
                path, mode="a", header=False, index=False
            )
        return True
    except Exception as exc:
        # str(exc) only, never repr — matches the T-03-02 precedent in
        # city_rating.resolve_point_observation, where a repr
        # could echo request state including a provider token.
        logger.warning("historical_archive append failed (non-fatal): %s", str(exc))
        return False


def read_history(
    path: str = None, city: str = None, validate: bool = True, corridor: str = None
) -> pd.DataFrame:
    """
    Read the archive back as a DataFrame, sorted ascending by
    `datetime_utc` so downstream time-series code never depends on file
    write order.

    Returns an empty `ARCHIVE_COLUMNS`-shaped frame (not a raised error)
    when `path` does not exist, so a cold-start caller needs no special
    case.

    `validate` defaults to `True`: every loaded row is run through
    `units_def.validate_pipeline_row(row, strict=False)` (via the same
    `_validation_row` placeholder `append_observation` uses) and rows
    with any error are dropped before the frame is returned. This closes
    the training-side half of the archive-poisoning threat (T-04-07,
    RESEARCH.md Security Domain: validate both before persisting and
    before training) -- `append_observation` already covers the write
    side, but this covers a file edited or corrupted outside the
    pipeline after it was written. If any rows are dropped, one
    warning-level log line names the count, the path and the first
    offending message -- one line per call, not one per row, so a
    corrupted file cannot flood the log. `validate=False` returns the
    frame unfiltered, preserving an escape hatch for forensic inspection.

    `city` filters to one city's rows. Corridor-era files (a `corridor`
    column instead of `city`) are read with that column exposed as `city`;
    their values are corridor names, so a per-city filter matches none of
    them. `corridor` is a deprecated alias for `city`.
    """
    if city is None:
        city = corridor
    if path is None:
        path = config.HISTORICAL_ARCHIVE_PATH

    if not os.path.exists(path):
        return pd.DataFrame(columns=ARCHIVE_COLUMNS)

    df = pd.read_csv(path)
    if "city" not in df.columns and "corridor" in df.columns:
        df = df.rename(columns={"corridor": "city"})

    if validate and len(df) > 0:
        row_dicts = df.to_dict(orient="records")
        error_lists = [
            units_def.validate_pipeline_row(_validation_row(r), strict=False)
            for r in row_dicts
        ]
        keep_mask = pd.Series([len(errs) == 0 for errs in error_lists], index=df.index)
        dropped = int((~keep_mask).sum())
        if dropped:
            first_bad_pos = next(i for i, errs in enumerate(error_lists) if errs)
            logger.warning(
                "historical_archive dropped %d invalid row(s) reading %s: %s",
                dropped, path, error_lists[first_bad_pos][0],
            )
        df = df[keep_mask]

    if city is not None and "city" in df.columns:
        df = df[df["city"] == city]

    return df.sort_values("datetime_utc", ascending=True).reset_index(drop=True)
