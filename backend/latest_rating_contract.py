"""
The published `public.latest_rating` contract (production-pipeline Phase 6, API-01).

`latest_rating` is the view the React dashboard and the PSS/E scripts read: one row per
city, the newest `city_rating` row by `valid_time`, fallback rows included (D-04). This
module is the single Python statement of that contract. The migration
`supabase/migrations/*_expose_latest_rating.sql` writes the same columns and the same
three rules in SQL, and `backend/tests/expose_migration_test.py` fails when the two
drift apart.

The column list is ONE-WAY (D-01, D-02, D-03). Consumers code against these names, so a
name is never renamed or dropped and a column is only ever appended after the last one.
Phase 7's re-validation go (REVAL-01) changes the label text, not this contract.

The three computed columns are:

  age_minutes     whole minutes from valid_time to the moment of the request, rounded
                  UP, so `age_minutes > 90` and `is_stale` can never contradict.
  is_stale        valid_time is STRICTLY more than 90 minutes before the request (OD-4);
                  exactly 90 minutes is fresh. A direct comparison, never derived from
                  the rounded integer.
  is_provisional  the word "provisional" (any case) appears in rating_basis OR
                  config_version (D-03, revised 2026-10-25: live rows begin
                  "Per-conductor amperes ..." and only backfill rows begin with the
                  OD-5 prefix, so a prefix test would read every live row as final).

Standard library only.
"""

from datetime import datetime, timedelta

_MICROSECONDS_PER_MINUTE = 60_000_000

# The 31 columns read straight from public.city_rating, in published order: the 27 planned
# columns, then the four identity and source columns added by D-01.
STORED_COLUMNS: tuple[str, ...] = (
    "city",
    "valid_time",
    "observation_time",
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
    "forecast_method",
    "forecast_status",
    "forecast_amps",
    "forecast_ci_lower_amps",
    "forecast_ci_upper_amps",
    "forecast_horizon_min",
    "detector_signal",
    "rating_basis",
    "config_version",
    "origin",
    "run_id",
    "pipeline_version",
    "computed_at",
    "config_fingerprint",
    "forecast_model_sha256",
    "anomaly_model_sha256",
    "solar_source",
)

# Computed per request from now(), appended after the stored columns (D-02, D-03).
COMPUTED_COLUMNS: tuple[str, ...] = ("age_minutes", "is_stale", "is_provisional")

LATEST_COLUMNS: tuple[str, ...] = STORED_COLUMNS + COMPUTED_COLUMNS

# OD-4: one hourly cadence interval (60) plus a 30 minute grace.
STALE_AFTER_MINUTES: int = 90

# The marker the label text must carry while the values are provisional (OD-5). Phase 7's
# re-validation go (REVAL-01) removes it from BOTH rating_basis and config_version.
PROVISIONAL_WORD: str = "provisional"


def is_provisional(rating_basis, config_version) -> bool:
    """True when the word `provisional` (any case) is in either label. None counts as empty."""
    for text in (rating_basis, config_version):
        if PROVISIONAL_WORD in (text or "").lower():
            return True
    return False


def age_minutes(valid_time: datetime, now: datetime) -> int:
    """Whole minutes from valid_time to now, rounded up (a started minute counts)."""
    elapsed = now - valid_time
    microseconds = elapsed // timedelta(microseconds=1)
    return -(-microseconds // _MICROSECONDS_PER_MINUTE)  # integer ceiling, exact (no float rounding)


def is_stale(valid_time: datetime, now: datetime) -> bool:
    """True when the row is strictly more than 90 minutes old, compared on the timedelta."""
    return (now - valid_time) > timedelta(minutes=STALE_AFTER_MINUTES)
