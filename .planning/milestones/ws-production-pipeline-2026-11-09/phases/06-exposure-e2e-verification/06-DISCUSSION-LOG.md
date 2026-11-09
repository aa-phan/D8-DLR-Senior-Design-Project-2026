# Phase 6: Exposure & E2E Verification - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-25
**Phase:** 06-exposure-e2e-verification
**Areas discussed:** latest_rating columns, Soak timing vs Phase 5/7, Public repo & examples, Monitoring after the soak

Pre-step: 7 plans (2026-10-19) existed without context. The owner chose "Continue and replan after".

---

## latest_rating columns

| Option | Description | Selected |
|--------|-------------|----------|
| Planned 27 + DB-06 identity | Add config_fingerprint, model hashes, solar_source; diagnostics stay in city_rating | ✓ |
| Every city_rating column | Mirror the table, diagnostics become contract | |
| Lean consumer view | ~12 columns | |

| Option | Description | Selected |
|--------|-------------|----------|
| Add age_minutes + is_stale | Computed at query time, 90-min OD-4 rule | ✓ |
| Only is_stale | One boolean | |
| No column; document it | Consumers compute from valid_time | |

| Option | Description | Selected |
|--------|-------------|----------|
| Add is_provisional boolean | Derived from rating_basis; flipped by Phase 7 GO | ✓ |
| rating_basis text only | No new column | |

| Option | Description | Selected |
|--------|-------------|----------|
| Newest row, fallback included | The published, safe value | ✓ |
| Prefer the newest computed row | Shows a value the system rejected | |

---

## Soak timing vs Phase 5/7

| Option | Description | Selected |
|--------|-------------|----------|
| Use existing live rows | Dry soak from city_rating since 10-25 00:05 | ✓ |
| Fresh practice run | Wait 12-24 h after monitoring is on | |
| Skip the practice run | Start 72 h at once | |

| Option | Description | Selected |
|--------|-------------|----------|
| Allow deploys; annotate them | Breaches they cause still count | ✓ |
| Freeze live changes during soak | No pushes for 72 h | |
| Restart the soak after a deploy | Reset the clock | |

| Option | Description | Selected |
|--------|-------------|----------|
| Separate re-check after 10-30 | Fold in T-04-22 | ✓ |
| Stretch the soak past 10-30 | ~5-day soak | |

| Option | Description | Selected |
|--------|-------------|----------|
| Build offline now, go live after 05-08 | Live steps gated on Phase 5 sign-off | ✓ |
| Wait for 05-08 first | Strict order | |

---

## Public repo & examples

| Option | Description | Selected |
|--------|-------------|----------|
| Neither committed; env vars | Owner sends values to the teams | ✓ |
| Commit both | Zero setup, world-queryable | |
| Commit URL only | Key shared privately | |

| Option | Description | Selected |
|--------|-------------|----------|
| Python 3.7+, no 2.7 | Covers PSS/E 35 and PSS/E 34 Python 3 | ✓ |
| Wait for Power Systems' answer | Blocks API-02 sign-off | |
| Support 2.7 too | urllib2 fallback | |

| Option | Description | Selected |
|--------|-------------|----------|
| Latest + one city's time range | With paging past 1000 rows | ✓ |
| Latest only | Smallest | |
| Latest + range + freshness check | Adds assert_fresh 503 handling | |

---

## Monitoring after the soak

| Option | Description | Selected |
|--------|-------------|----------|
| Keep the alarm, stop the 5-min log | Alarm permanent; log job removed | ✓ |
| Keep both permanently | Needs a retention rule | |
| Tear both down (as planned) | Relies on red Actions runs | |

| Option | Description | Selected |
|--------|-------------|----------|
| Owner only | cron-job.org account email | ✓ |
| Owner + team list | Shared address | |

| Option | Description | Selected |
|--------|-------------|----------|
| Every 15 min, 2 in a row | ~30 min to alert, recovery email | ✓ |
| Every 5 min, first failure | Fastest, noisiest | |
| Hourly, first failure | Up to an hour of lag | |

---

## Claude's Discretion

- SQL form of is_provisional / age_minutes, column placement of derived columns, how the dry-soak report is produced from existing rows, whether a short probe smoke check precedes the 72 h clock, how deploy annotations are captured.

## Deferred Ideas

- Python 2.7 PSS/E example (only on a 2.7 answer); team alert address; permanent freshness history.
