"""
Configuration & Parameterization (C1)
==================================================
This module is C1 per `docs/data-science/specs/C1-configuration.md`.

It centralizes values that were previously hardcoded and duplicated
independently across modules — most notably the "two independent 900.0 A
literals" known issue described in the C1 spec: one in
`backend/dlr_pipeline.py`'s `__main__` block (`static_rating=900.0`) and a
second, wholly independent one in `backend/ercot_dlr_merger.py` (used to
compute `static_capacity_mw`). Because those two literals could be edited
independently, they could silently drift out of agreement with no test or
check to catch it. This module gives every component a single source to
read from instead.

Importing this module has no side effects (no file I/O, no network calls,
no pipeline execution) — it is safe to import without triggering any of
`backend/dlr_pipeline.py`'s `__main__` behavior.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Per-location static line ratings (Amps)
# ──────────────────────────────────────────────────────────────────────────────
# These four cities (Houston, Austin, Dallas, Fort Worth) do not have a source
# that differentiates a per-city static rating — two independent research
# passes across ERCOT filings, utility (transmission owner) filings, PUCT
# dockets, and FERC filings turned up nothing city-specific for them. 900 A is
# the commonly-cited nominal normal rating for a single 795 kcmil "Drake" ACSR
# conductor at 138 kV, which also matches this project's own
# `ConductorConfig` defaults (see `backend/dlr_pipeline.py`'s `ConductorConfig`,
# diameter_m=0.02814 — Drake ACSR). This is flagged explicitly as an honest
# uniform baseline, NOT as city-differentiated evidence — consistent with how
# this project's docs (see `docs/data-science/PRD.md`, "Documentation
# Discrepancies" section) always flag approximations rather than presenting
# them as verified.
#
# Note on Dallas/Fort Worth specifically: a real sourced number DOES exist
# (the Oncor Wilmer 345/138kV project, per an ERCOT filing), but it describes
# a modern-rebuild TARGET spec using 3200A/5000A-class HTLS conductor — not
# representative of this project's typical-existing-conductor assumption — so
# it was deliberately excluded here rather than used.
STATIC_RATINGS: dict[str, float] = {
    "SAN_ANTONIO": 1761.0,  # ERCOT Board Item 11.2 (Aug 2023), "CPS Energy - San
    # Antonio South Reliability RPG Project": existing single-circuit 345kV
    # J.K. Spruce-Pawnee path, 1,051 MVA normal capacity => ~1,761 A at 345kV.
    # https://www.ercot.com/files/docs/2023/08/24/11.2%20CPS%20Energy%20San%20Antonio%20South%20Reliability%20Regional%20Planning%20Group%20Project%20(Template)%20v3.pdf
    "HOUSTON": 900.0,
    "AUSTIN": 900.0,
    "DALLAS": 900.0,
    "FORT_WORTH": 900.0,
}

# Fallback static rating (Amps) for any location not present in
# STATIC_RATINGS. Preserves current behavior for stations outside the five
# cities above.
DEFAULT_STATIC_RATING: float = 900.0

# ──────────────────────────────────────────────────────────────────────────────
# Conductor properties
# ──────────────────────────────────────────────────────────────────────────────
# Exact kwargs previously hardcoded in `backend/dlr_pipeline.py`'s __main__
# block for constructing a ConductorConfig. Kept as a plain dict (rather than
# changing ConductorConfig itself) so callers can do:
#     ConductorConfig(**DEFAULT_CONDUCTOR_CONFIG_KWARGS)
DEFAULT_CONDUCTOR_CONFIG_KWARGS: dict = {
    "diameter_m": 0.02814,      # 795 kcmil Drake ACSR
    "resistance_ac": 0.0726,    # Ω/km at 25°C
    "emissivity": 0.8,
    "absorptivity": 0.8,
    "max_temp_c": 75.0,
    "line_azimuth": 90.0,       # set to actual line bearing
    "elevation_m": 900.0,       # West Texas Permian Basin avg elevation
}

# ──────────────────────────────────────────────────────────────────────────────
# Analysis window & station source
# ──────────────────────────────────────────────────────────────────────────────
# Today's hardcoded __main__ values from backend/dlr_pipeline.py, moved here
# unchanged.
DEFAULT_STATION_SOURCE: str = "data/wtm_stations_austin.csv"
DEFAULT_START: str = "2025-07-01T00:00:00Z"
DEFAULT_END: str = "2025-07-04T23:55:00Z"

# ──────────────────────────────────────────────────────────────────────────────
# Line electrical parameters
# ──────────────────────────────────────────────────────────────────────────────
# Previously module-level constants at the top of backend/ercot_dlr_merger.py
# (lines 10-11), moved here since centralizing exactly this kind of value is
# C1's job.
LINE_VOLTAGE_KV: float = 345.0  # ERCOT West Texas standard backbone
POWER_FACTOR: float = 0.95      # Standard conservative assumption for grid power
