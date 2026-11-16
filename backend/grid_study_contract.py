"""
The published column list of public.latest_grid_study (supabase/migrations/
20261116200000_expose_latest_grid_study.sql), in order.

One-way: a name is never renamed or dropped, and a column is only ever appended after the last
one. backend/tests/grid_study_expose_test.py fails if this list and the view differ.
"""

VIEW = "latest_grid_study"

COLUMNS = (
    "solver",
    "city",
    "slot_time",
    "study_finished_at",
    "run_outcome",
    "rating_source",
    "fallback_reason",
    "city_rating_valid_time",
    "applied_amps_per_conductor",
    "dispatched_amps_per_conductor",
    "subconductors_per_phase",
    "line_voltage_kv",
    "applied_mva",
    "voltage_limit_mva",
    "dispatched_mva",
    "dispatched_mw",
    "usable_pct",
    "limiting_factor",
    "age_minutes",
    "is_stale",
)

# Fields the view must never publish (identifiers, hashes, free text, the raw details).
FORBIDDEN = (
    "run_id", "case_id", "case_sha256", "mapping_sha256", "ratings_used", "error",
    "ratings_read_error", "details", "critical_bus", "job_version",
)

STALE_AFTER_MINUTES = 90
