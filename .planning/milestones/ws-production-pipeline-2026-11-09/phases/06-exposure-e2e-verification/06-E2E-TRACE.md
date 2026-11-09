| city | cron-job.org execution | Actions run | SQL row | REST row | match | current or superseded |
|---|---|---|---|---|---|---|
| AUSTIN | 2026-10-27T04:05:02Z HTTP 204 | 40447756754 success | 2026-10-27T04:00:00Z 1825.0 A | 2026-10-27T04:00:00Z 1825 A | yes | current |
| CORPUS_CHRISTI | 2026-10-27T04:05:02Z HTTP 204 | 40447756754 success | 2026-10-27T04:00:00Z 1520.0913199525 A | 2026-10-27T04:00:00Z 1520.0913199525 A | yes | current |
| MIDLAND | 2026-10-27T04:05:02Z HTTP 204 | 40447756754 success | 2026-10-27T04:00:00Z 1465.62365478361 A | 2026-10-27T04:00:00Z 1465.62365478361 A | yes | current |
| EL_PASO | 2026-10-27T04:05:02Z HTTP 204 | 40447756754 success | 2026-10-27T04:00:00Z 1281.16494535577 A | 2026-10-27T04:00:00Z 1281.16494535577 A | yes | current |

PASS cron-job.org execution: 2026-10-27T04:05:02Z answered HTTP 204
PASS Actions run: run 40447756754 created 2026-10-27T04:05:05Z
PASS Actions run result: concluded success in workflow 'DLR Live Ratings' as a workflow_dispatch
PASS SQL rows: 4 rows for run 40447756754, one per city
PASS pipeline_run: cities_ok lists all 4 cities
PASS REST rows: 4 rows for run 40447756754
PASS SQL equals REST: 31 columns for each of 4 cities are equal
PASS is_provisional: equals the word rule on rating_basis and config_version for all 4 cities

E2E TRACE OK
