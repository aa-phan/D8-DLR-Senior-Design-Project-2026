"""
The day-ahead forecast contract (production-pipeline Phase 8, DAY-05, D-09, D-11).

`public.day_ahead_forecast` holds one day-ahead `ml_cooling_corrected` value per city and per
00/06/12/18 UTC target hour, issued from the Open-Meteo run that started exactly 24 h before the
target. It is its own table next to `city_rating`; the 60-minute forecast stays a field of the
rating record because it gates G6, and the day-ahead value never gates anything. This module is the
single Python statement of the names and constants. The migration
`supabase/migrations/20261108120000_day_ahead_forecast_store.sql` writes the same columns in SQL,
and the tests fail when the two drift apart.

ONE-WAY RULE (D-09): once published, the table and view columns are a consumer contract
(`docs/integration/rest-api.md`). A name is never renamed or dropped; a column is only ever
appended after the last one, through a new additive migration and a contract revision. The two
database CHECKs on `horizon_minutes` (1440) and `forecast_method` (ml_cooling_corrected) make a
plural change (hourly issuance at several leads, a second method) fail loudly instead of silently
overwriting a row: that change needs a promote to a key that includes the horizon or the method.

Amperes only. There are no MW columns; the documentation states how to convert.

Standard library only.
"""

# D-11: the short, stable label every row carries. The plain-English paragraph lives in the docs.
DAY_AHEAD_LABEL: str = "day-ahead-24h; engineering-selection; not-validated"

# D-16: every published value is this method's own prediction; there is no substitute method.
FORECAST_METHOD: str = "ml_cooling_corrected"

# The weather run is initialised exactly this many minutes before the target (24 h). It is the age
# of the weather run, not the lead from the moment of issue (a row is issued 0 to 18 h before it).
HORIZON_MINUTES: int = 1440

# D-01: one target every six hours on the UTC grid, at minute zero.
GRID_HOURS: int = 6
TARGET_HOURS_UTC: tuple[int, ...] = (0, 6, 12, 18)

# D-05: where a row's band came from. The launch band is the hashed TEST-split artifact.
BAND_SOURCES: tuple[str, ...] = ("test-split", "live-rolling")

# D-12: a target due within this many hours with no row marks the city late.
LATE_WINDOW_HOURS: int = 12

# D-05 switch-over (Claude's discretion, stated in the contract doc): a band switches from the TEST
# artifact to the live rolling band once this many live pairs exist, using the newest
# LIVE_BAND_WINDOW pairs, and only when the live band straddles zero.
LIVE_BAND_MIN_PAIRS: int = 60
LIVE_BAND_WINDOW: int = 120

TABLE: str = "public.day_ahead_forecast"
UPCOMING_VIEW: str = "public.day_ahead_upcoming"
STATUS_VIEW: str = "public.day_ahead_status"

# The 25 stored columns, in table order.
TABLE_COLUMNS: tuple[str, ...] = (
    "city",
    "valid_time",
    "issued_at",
    "forecast_run_init_time",
    "horizon_minutes",
    "forecast_amps",
    "forecast_ci_lower_amps",
    "forecast_ci_upper_amps",
    "band_source",
    "band_n",
    "band_pairs_through",
    "band_artifact_sha256",
    "forecast_method",
    "cooling_model_sha256",
    "cooling_model_source",
    "anchor_observation_time",
    "anchor_source",
    "label",
    "config_version",
    "config_fingerprint",
    "run_id",
    "run_attempt",
    "pipeline_version",
    "schema_version",
    "first_written_at",
)

# first_written_at is the database default, never written by the runner.
INSERT_COLUMNS: tuple[str, ...] = TABLE_COLUMNS[:-1]

# The upcoming-targets view: every stored column plus the lead from now, in minutes.
UPCOMING_COLUMNS: tuple[str, ...] = TABLE_COLUMNS + ("lead_minutes",)

# The status view: one row per city, always four rows, with the missing/late flag.
STATUS_COLUMNS: tuple[str, ...] = (
    "city",
    "checked_at",
    "next_target_time",
    "upcoming_count",
    "newest_issued_at",
    "missing_targets",
    "is_late",
)
