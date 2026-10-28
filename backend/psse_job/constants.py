"""
Constants of the PSS/E job (pss-e-integration Phase 1).

The values copied from backend/config.py are plain assignments with no annotations,
because the job must not import config (its module-level `dict[str, float]` annotations
break Python 3.7/3.8) and must parse on PSS/E's interpreter (D-05). The vocabularies
below must equal the CHECK lists in docs/data-science/schema/psse_results_v1.sql;
plan 01-03 tests that.
"""

# The four rating locations, in the fixed order every record uses.
# Copy of backend/config.py LOCATIONS; backend/tests/psse_contract_test.py fails if they drift.
CITIES = ("AUSTIN", "CORPUS_CHRISTI", "MIDLAND", "EL_PASO")

# Copy of backend/config.py STATIC_RATINGS (amperes, per conductor);
# backend/tests/psse_contract_test.py fails if they drift.
STATIC_RATINGS_AMPS_PER_CONDUCTOR = {
    "AUSTIN": 1825.0,
    "CORPUS_CHRISTI": 1500.0,
    "MIDLAND": 1875.0,
    "EL_PASO": 1320.0,
}

# Copy of backend/config.py SUBCONDUCTORS_PER_PHASE (count);
# backend/tests/psse_contract_test.py fails if they drift.
SUBCONDUCTORS_PER_PHASE = {
    "AUSTIN": 2,
    "CORPUS_CHRISTI": 2,
    "MIDLAND": 2,
    "EL_PASO": 1,
}

# Copy of backend/config.py LINE_VOLTAGE_KV. Nominal value for the spec's worked table;
# the study always uses the branch's base kV from the case (D-06).
LINE_VOLTAGE_KV_DEFAULT = 345.0

# A latest_rating row older than this many minutes is stale (exactly this age is fresh).
STALE_AFTER_MINUTES = 90
# A valid_time further than this many minutes after the job's clock is not credible.
FUTURE_TOLERANCE_MINUTES = 5

SOURCE_CITY_RATING = "city_rating"
SOURCE_STATIC = "static_fallback"
SOURCES = (SOURCE_CITY_RATING, SOURCE_STATIC)

# Precedence order for one row, then the whole-read reason.
FALLBACK_REASONS = ("missing", "invalid", "stale", "provisional", "read_failed")

OUTCOMES = ("ok", "fallback", "failed")
FAILED_STAGES = (
    "load_case", "mapping", "apply_ratings", "load_flow", "contingency",
    "voltage_margin", "dispatch", "validate_results", "write", "internal",
)
LIMITING_FACTORS = ("dlr_rating", "voltage_stability")
VIOLATION_KINDS = ("thermal_overload", "voltage_low", "voltage_high", "non_convergence")
ELEMENT_TYPES = ("branch", "bus", "contingency")
RESULT_UNITS = ("MVA", "pu")

# The Phase 6 view read through Supabase REST, and the only columns selected from it.
# rating_mw and static_rating_mw are never selected (D-06).
LATEST_RATING_VIEW = "latest_rating"
LATEST_RATING_SELECT = (
    "city", "valid_time", "computed_at", "rating_amps", "static_rating_amps", "status",
    "fallback", "run_id", "config_fingerprint", "age_minutes", "is_stale", "is_provisional",
)

# Keys of one city's entry in psse_run.ratings_used, in order.
RATINGS_USED_KEYS = (
    "source", "fallback_reason", "rating_amps_per_conductor", "subconductors_per_phase",
    "rating_amps_circuit", "static_rating_amps_per_conductor", "line_voltage_kv", "rating_mva",
    "city_rating_valid_time", "city_rating_computed_at", "city_rating_run_id",
    "city_rating_status", "config_fingerprint", "age_minutes", "server_is_stale",
    "server_is_provisional",
)

ENV_SUPABASE_URL = "SUPABASE_URL"
ENV_PUBLISHABLE_KEY = "SUPABASE_PUBLISHABLE_KEY"
ENV_PSSE_DB_URL = "SUPABASE_PSSE_DB_URL"

# Prefix of a Supabase secret key, assembled so this source never holds the literal.
SECRET_KEY_PREFIX = "sb_" + "secret_"

ERROR_MAX_CHARS = 1000
LOG_MAX_CHARS = 300
USER_AGENT = "dlr-psse-job/1.0"
