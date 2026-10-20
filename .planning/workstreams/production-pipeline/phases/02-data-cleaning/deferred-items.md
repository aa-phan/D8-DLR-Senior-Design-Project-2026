# Phase 2 deferred items

## From 02-02 (found 2026-10-20)

- **`backend/data_cleaning.py::_parse_utc` has the same mixed-batch parse defect that 02-02 fixed in `historical_archive._parse_utc`.** Under pandas 2.3.3, `pd.to_datetime(..., utc=True, format="ISO8601")` on one Series applies an earlier value's explicit offset to a later naive value (and to a later date-only value): `["2026-01-01T06:00:00+06:00", "2026-01-01T00:00:00"]` parses to 00:00 and `2025-12-31T18:00` UTC. Effect: `clean_history`'s time sort and duplicate-instant rule misplace or miss a naive row that follows an offset-spelled row (only reachable with an archive that mixes spellings, e.g. a manual CLI `--end` with an offset). Out of 02-02's `files_modified`; 02-03 edits `data_cleaning.py` and should fix it the same way (parse rows with an explicit offset and rows without one in separate batches) and add a test.
