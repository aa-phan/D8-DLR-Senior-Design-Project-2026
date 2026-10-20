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

One row per finding in `02-REVIEW.md`. All findings were resolved on 2026-10-20 after owner decisions on WR-01, WR-02 and WR-04. WR-01 to WR-04 are behavioral: the cleaning rules either drop valid data or keep a forecast out of G6 when they shouldn't. WR-05 is a test-strength issue.

| ID | Severity | Finding | Disposition |
|----|----------|---------|-------------|
| WR-01 | warning | A fallback row written first blocks the later computed reading for that slot (slot guard and `duplicate` rule ignore fallback status) | fixed in 88e3229 (owner, 2026-10-20: a computed row may follow a fallback row; write guard and read-side `duplicate` rule) |
| WR-02 | warning | `STUCK_EXEMPT_VALUES` exempts only solar 0.0, so calm wind (0.0 m/s) is flagged stuck and excluded | fixed in 88e3229 (owner: exempt wind 0.0; policy v2) |
| WR-03 | warning | The stuck rule counts rows, not consecutive hours, so identical readings days apart are flagged | fixed in 88e3229 (a missing hour ends a stuck run; excluded rows still bridge) |
| WR-04 | warning | Slots use `floor("h")` but rows are stamped with a 5-minute-floored `end`, so run-time jitter looks like a missing hour and can withhold an `ml` forecast from G6 | fixed in 88e3229 by documentation (owner: slot = run end's own hour, OD-7; live dispatch at hh:05) plus a pinning test; no logic change |
| WR-05 | warning | Policy-doc/code agreement test matches numeric constants by substring (1 and 7 match 10 and 17) | fixed in 88e3229 (values matched as whole table cells; mutation-checked) |
| IN-01 | info | `_parse_utc` / `_EXPLICIT_OFFSET` duplicated in `data_cleaning.py` and `historical_archive.py` | fixed in 88e3229 (parity test across both parsers; modules stay separate) |
| IN-02 | info | `fallback` rule matches only text "true"; "1"/"yes" are not flagged (unreachable from current writer) | fixed in 88e3229 by documentation (strict "true" contract stated; writer emits bool only) |
| IN-03 | info | Slot-guard check and append are not atomic across concurrent writers | fixed in 88e3229 by documentation (guard described as best effort) |
