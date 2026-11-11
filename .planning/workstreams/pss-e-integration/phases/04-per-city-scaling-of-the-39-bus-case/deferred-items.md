# Phase 4 deferred items

Out-of-scope findings logged by plan executors; not fixed in the plan that found them.

## From plan 04-01

- `backend/psse_job/mapping.py` `_parse_city`, `transfer_max_mw` check (pre-existing, not touched by 04-01): an integer too large for a float (for example 400 digits, which fits inside the 65536-byte mapping cap) makes `math.isfinite` raise `OverflowError`, so `parse_mapping` raises `OverflowError` instead of a `MappingError`. The new scaling check (`_positive_finite`) catches it and refuses the value; the same helper could replace the inline test for `transfer_max_mw` in a later plan. Low severity: the private mapping is hand-edited by Power Systems.
