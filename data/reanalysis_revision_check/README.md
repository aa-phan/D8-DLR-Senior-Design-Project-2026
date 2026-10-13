# Reanalysis revision check (protocol v2 item; truth vs truth only)

Question: does the Open-Meteo archive revise already-published hours, and how late? Informs the 2026-11-17 scoring cutoff.
No predictions or outcomes are involved.

- Baseline fetch: window 2026-10-01..2026-10-11, all four cities, fetched 2026-10-13 (UTC stamp in each filename).
- Repeat: re-run `fetch_truth.py` for the same window in about 5-7 days (same output dir), then
  `compare_truth.py <baseline.json> <repeat.json>` per city. Run with `python -I` from the repo root.
