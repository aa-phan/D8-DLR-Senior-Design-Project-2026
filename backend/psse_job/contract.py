"""
The Python mirror of docs/data-science/schema/psse_results_v1.sql, and the study contract
for Phase 2 (pss-e-integration Phase 1: WB-01, WB-02, D-03, D-04).

Table names and the client column tuples live here, in DDL order. Every INSERT the job runs
is built from these tuples only (never from a key of a row), and every value is a bound
parameter. A client column is every column of a table except the two the database fills
itself (DB_DEFAULT_COLUMNS). backend/tests/psse_run_record_test.py fails when a tuple drifts
from the reference DDL.

The study contract (Phase 2 implements it): a study is a callable `study(selection, context)`
that returns StudyResults, or raises StudyFailed(stage, message). `dispatch`, `margins` and
`contingencies` are lists of dicts keyed by DISPATCH_COLUMNS, MARGIN_COLUMNS and
CONTINGENCY_COLUMNS without run_id and run_outcome; dispatch and margins hold one row per city.

The solver tag (DB-02): every run is stored with the solver that produced it. PSS/E is the
default and the only tag registered here; the second solver's package registers its own name
and run-id prefix on import with `register_solver_tag`, next to `study.register_solver`.
There are two run INSERTs. A PSS/E run keeps the 17-column INSERT_RUN_SQL, so it still works
on a database where the solver-tag migration has not been applied yet. Another solver's run
uses the 19-column INSERT_RUN_TAGGED_SQL (adds solver and solver_version) and needs migration
20261118200000.

Standard library only, Python 3.7 syntax (D-05).
"""

import collections

PSSE_RUN_TABLE = "public.psse_run"
DISPATCH_TABLE = "public.psse_dispatched_capacity"
MARGIN_TABLE = "public.psse_voltage_margin"
CONTINGENCY_TABLE = "public.psse_contingency_result"
# Insert order after the run row (the composite foreign key needs the run row first).
RESULT_TABLES = (DISPATCH_TABLE, MARGIN_TABLE, CONTINGENCY_TABLE)

# Filled by the database, never by the job.
DB_DEFAULT_COLUMNS = ("schema_version", "created_at")

PSSE_RUN_COLUMNS = (
    "run_id", "slot_time", "started_at", "finished_at", "outcome", "failed_stage", "error",
    "ratings_read_error", "case_id", "case_sha256", "mapping_sha256", "rate_set",
    "ratings_used", "n_contingencies", "n_contingencies_with_results", "job_version",
    "psse_version",
)

# The solver tag. SOLVER_PSSE is the default; RUN_ID_PREFIXES maps each registered solver name
# to its run-id prefix (a run id is `<prefix>-<stamp>-<8 hex>`).
SOLVER_PSSE = "psse"
RUN_ID_PREFIXES = {SOLVER_PSSE: "psse"}

# The two columns the solver-tag migration adds; only a run of another solver carries them.
SOLVER_RUN_COLUMNS = ("solver", "solver_version")
TAGGED_RUN_COLUMNS = PSSE_RUN_COLUMNS + SOLVER_RUN_COLUMNS


def register_solver_tag(name, prefix):
    """
    Register a solver `name` with its run-id `prefix`. The second solver's package calls it
    once on import (rules finished with the tests: an existing name or prefix is never
    re-bound).
    """
    if name not in RUN_ID_PREFIXES:
        RUN_ID_PREFIXES[name] = prefix


DISPATCH_COLUMNS = (
    "run_id", "run_outcome", "city", "rating_source", "fallback_reason",
    "city_rating_valid_time", "city_rating_computed_at", "applied_amps_per_conductor",
    "subconductors_per_phase", "applied_amps_circuit", "line_voltage_kv", "applied_mva",
    "voltage_limit_mva", "dispatched_mva", "dispatched_amps_circuit",
    "dispatched_amps_per_conductor", "power_factor", "dispatched_mw", "limiting_factor",
    "details",
)

MARGIN_COLUMNS = (
    "run_id", "run_outcome", "city", "method", "base_transfer_mw", "limit_transfer_mw",
    "margin_mw", "margin_pct", "voltage_limit_mva", "critical_bus", "min_voltage_pu",
    "details",
)

CONTINGENCY_COLUMNS = (
    "run_id", "run_outcome", "contingency_id", "violation_kind", "element_type",
    "element_id", "city", "limit_value", "observed_value", "exceeded_by", "unit", "details",
)

TABLE_COLUMNS = {
    PSSE_RUN_TABLE: PSSE_RUN_COLUMNS,
    DISPATCH_TABLE: DISPATCH_COLUMNS,
    MARGIN_TABLE: MARGIN_COLUMNS,
    CONTINGENCY_TABLE: CONTINGENCY_COLUMNS,
}

# Bound as json text and cast with ::jsonb.
JSONB_COLUMNS = ("ratings_used", "details")


def insert_sql(table, suffix="", columns=None):
    """
    `insert into <table> (<columns>) values (<placeholders>) <suffix>`, built from
    TABLE_COLUMNS only (or from `columns`, a fixed tuple of this module such as
    TAGGED_RUN_COLUMNS); an unknown table raises ValueError. JSONB columns get `::jsonb`.
    """
    if table not in TABLE_COLUMNS:
        raise ValueError("not a PSS/E result table: %r" % (table,))
    if columns is None:
        columns = TABLE_COLUMNS[table]
    placeholders = [
        ("%%(%s)s::jsonb" if column in JSONB_COLUMNS else "%%(%s)s") % column
        for column in columns
    ]
    sql = "insert into %s (%s) values (%s)" % (table, ", ".join(columns), ", ".join(placeholders))
    if suffix:
        sql = sql + " " + suffix
    return sql


# One run row, once; a row that is already there (a retry after a lost commit
# acknowledgement) is left alone and reported by returning no row (D-04).
INSERT_RUN_SQL = insert_sql(PSSE_RUN_TABLE, "on conflict (run_id) do nothing returning run_id")

# The same run row with the solver tag (19 columns), for a run of another solver.
INSERT_RUN_TAGGED_SQL = insert_sql(
    PSSE_RUN_TABLE, "on conflict (run_id) do nothing returning run_id", TAGGED_RUN_COLUMNS)

INSERT_RESULT_SQL = dict((table, insert_sql(table)) for table in RESULT_TABLES)

# What the job knows at start: run_id (stamped once, reused on a retry), the start instant,
# the case label and hashes, the job version label and the solver tag (default PSS/E).
RunContext = collections.namedtuple(
    "RunContext",
    ["run_id", "started_at", "case_id", "case_sha256", "mapping_sha256", "job_version", "solver"],
    defaults=(SOLVER_PSSE,),
)

# What a successful study returns; `solver` names the solver that produced it (default PSS/E)
# and `solver_version` is that solver's version text (None for PSS/E, which has psse_version).
StudyResults = collections.namedtuple(
    "StudyResults",
    ["dispatch", "margins", "contingencies", "n_contingencies", "rate_set", "psse_version",
     "solver", "solver_version"],
    defaults=(SOLVER_PSSE, None),
)

# A failed run: the stage (one of constants.FAILED_STAGES) and a message.
Failure = collections.namedtuple("Failure", ["stage", "message"])


class StudyFailed(Exception):
    """A study could not finish; Phase 2 raises it with the stage that failed."""

    def __init__(self, stage, message):
        Exception.__init__(self, "%s: %s" % (stage, message))
        self.stage = stage
        self.message = message


class ResultsInvalid(ValueError):
    """A study result is malformed; the message names the first problem."""
