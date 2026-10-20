---
phase: 02-data-cleaning
review: 02-REVIEW.md
recorded: 2026-10-20
counts:
  critical: 0
  warning: 5
  info: 3
---

# Phase 2: Review Disposition

One row per finding in `02-REVIEW.md`. `open` means the finding was seen at the code-review gate and nobody has acted on it yet. WR-01 to WR-04 are behavioral: the cleaning rules either drop valid data or keep a forecast out of G6 when they shouldn't. WR-05 is a test-strength issue.

| ID | Severity | Finding | Disposition |
|----|----------|---------|-------------|
| WR-01 | warning | A fallback row written first blocks the later computed reading for that slot (slot guard and `duplicate` rule ignore fallback status) | open |
| WR-02 | warning | `STUCK_EXEMPT_VALUES` exempts only solar 0.0, so calm wind (0.0 m/s) is flagged stuck and excluded | open |
| WR-03 | warning | The stuck rule counts rows, not consecutive hours, so identical readings days apart are flagged | open |
| WR-04 | warning | Slots use `floor("h")` but rows are stamped with a 5-minute-floored `end`, so run-time jitter looks like a missing hour and can withhold an `ml` forecast from G6 | open |
| WR-05 | warning | Policy-doc/code agreement test matches numeric constants by substring (1 and 7 match 10 and 17) | open |
| IN-01 | info | `_parse_utc` / `_EXPLICIT_OFFSET` duplicated in `data_cleaning.py` and `historical_archive.py` | open |
| IN-02 | info | `fallback` rule matches only text "true"; "1"/"yes" are not flagged (unreachable from current writer) | open |
| IN-03 | info | Slot-guard check and append are not atomic across concurrent writers | open |
