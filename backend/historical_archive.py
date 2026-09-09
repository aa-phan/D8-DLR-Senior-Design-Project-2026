"""
Historical Archive (Phase 4 Wave 0 support for C9, C10)
==================================================
This module is shared support for C9 (ampacity forecasting) and C10
(learned anomaly detection) — it is not a spec component of its own. It
holds one row per corridor per run (D-08's per-corridor granularity), and
it has exactly one write call site, wired in Plan 04-03.

The row shape (`ARCHIVE_COLUMNS`) reuses `units_def.PIPELINE_SCHEMA`'s
column spellings for every numeric field so `validate_pipeline_row` vets
an archive row with no change to that validator and no parallel schema
object (T-04-01, the archive-poisoning mitigation). Storage is an
append-only CSV at `config.HISTORICAL_ARCHIVE_PATH`, unbounded retention
this phase (D-09) — this module does not implement rotation/compaction.

Column list locked at the Plan 04-01 Task 1 checkpoint (D-07 — one-way:
once `ampacity_forecast.py`/`anomaly_detector.py` read this shape and rows
accumulate, changing it means migrating or discarding real history):
    datetime_utc, corridor, air_temp, wind_speed, solar_radiation,
    dlr_amps, static_rating, status, fallback, bottleneck_index,
    schema_version
"""

import logging
import os

import pandas as pd

import config
import units_def

logger = logging.getLogger(__name__)

# D-07 checkpoint decision (Task 1, `proposed` option): the 11-column row
# shape every Phase 4 model reads. schema_version starts at 1.
ARCHIVE_SCHEMA_VERSION: int = 1

ARCHIVE_COLUMNS: list[str] = [
    "datetime_utc",
    "corridor",
    "air_temp",
    "wind_speed",
    "solar_radiation",
    "dlr_amps",
    "static_rating",
    "status",
    "fallback",
    "bottleneck_index",
    "schema_version",
]


def build_archive_row(
    corridor: str,
    datetime_utc,
    observation: dict,
    check_result: dict,
    static_rating: float,
    bottleneck_index=None,
) -> dict:
    """
    Assemble one archive row from a `DLRSafetyMonitor.run_check` cycle.

    `observation` is the reading dict `run_check` consumes (keys `temp`,
    `wind`, `solar` per `corridor_discretization._OBSERVATION_FIELD_MAP`);
    translated here back to the `PIPELINE_SCHEMA` spellings `air_temp`,
    `wind_speed`, `solar_radiation`. `check_result` is the mapping
    `run_check` returned — its rating, status and fallback flag are read
    from it directly, never recomputed here.

    Every numeric field is `float(...)`-wrapped at assignment
    (RESEARCH.md Pitfall 2). Returns keys in `ARCHIVE_COLUMNS` order.
    """
    row = {
        "datetime_utc": datetime_utc,
        "corridor": corridor,
        "air_temp": float(observation["temp"]),
        "wind_speed": float(observation["wind"]),
        "solar_radiation": float(observation["solar"]),
        "dlr_amps": float(check_result["rating"]),
        "static_rating": float(static_rating),
        "status": check_result["status"],
        "fallback": bool(check_result["fallback"]),
        "bottleneck_index": (
            int(bottleneck_index) if bottleneck_index is not None else None
        ),
        "schema_version": ARCHIVE_SCHEMA_VERSION,
    }
    return {col: row[col] for col in ARCHIVE_COLUMNS}


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

    try:
        # PIPELINE_SCHEMA marks wind_direction required=True, but the
        # archive row (ARCHIVE_COLUMNS) deliberately has no direction
        # column at all -- corridor observations only carry the already-
        # resolved perpendicular wind component (`wind_speed` here), never
        # a raw direction. Supply a fixed, in-range placeholder solely so
        # validate_pipeline_row's required-column check doesn't reject
        # every archive row for a column this archive never stores or
        # reads; it is never added to the persisted row itself.
        validation_row = dict(row)
        validation_row.setdefault("wind_direction", 0.0)
        violations = units_def.validate_pipeline_row(validation_row, strict=False)
        if violations:
            corridor = row.get("corridor", "<unknown corridor>")
            for msg in violations:
                logger.warning("historical_archive rejected row for %s: %s", corridor, msg)
            return False

        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)

        pd.DataFrame([row], columns=ARCHIVE_COLUMNS).to_csv(
            path, mode="a", header=not os.path.exists(path), index=False
        )
        return True
    except Exception as exc:
        # str(exc) only, never repr — matches the T-03-02 precedent in
        # corridor_discretization.resolve_point_observation, where a repr
        # could echo request state including a provider token.
        logger.warning("historical_archive append failed (non-fatal): %s", str(exc))
        return False


def read_history(path: str = None, corridor: str = None) -> pd.DataFrame:
    """
    Read the archive back as a DataFrame, sorted ascending by
    `datetime_utc` so downstream time-series code never depends on file
    write order.

    Returns an empty `ARCHIVE_COLUMNS`-shaped frame (not a raised error)
    when `path` does not exist, so a cold-start caller needs no special
    case.
    """
    if path is None:
        path = config.HISTORICAL_ARCHIVE_PATH

    if not os.path.exists(path):
        return pd.DataFrame(columns=ARCHIVE_COLUMNS)

    df = pd.read_csv(path)
    if corridor is not None and "corridor" in df.columns:
        df = df[df["corridor"] == corridor]

    return df.sort_values("datetime_utc", ascending=True).reset_index(drop=True)
