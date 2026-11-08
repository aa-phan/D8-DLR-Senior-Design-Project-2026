# Phase 8: Day-Ahead Cooling Forecast Alongside 60-Minute G6 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-08
**Phase:** 08-day-ahead-cooling-forecast-alongside-60-minute-g6
**Areas discussed:** When & how it runs, Uncertainty band, Storage & what consumers see, Model files & failure policy

---

## When & how it runs

**Cadence**

| Option | Description | Selected |
|--------|-------------|----------|
| 4×/day, as tested | 00/06/12/18 UTC targets from the exactly-24 h-old run; matches TEST and reads 1-2 | ✓ |
| Every hour | Newest run, 24-29 h leads; 20 of 24 daily values untested | |
| 4×/day now, hourly later | Ship tested version; hourly deferred | |

**Which job**

| Option | Description | Selected |
|--------|-------------|----------|
| Inside the hourly live job | Separate step after ratings; no new cron; cannot delay ratings | ✓ |
| Its own workflow | New dispatch workflow + cron-job.org job + alarm | |
| You decide | Planner chooses | |

**Fidelity**

| Option | Description | Selected |
|--------|-------------|----------|
| Match the shadow exactly | Shadow's own functions, parity test | ✓ |
| Reuse the live run's reading | Saves a call; inputs differ from what was tested | |

**Missed slot**

| Option | Description | Selected |
|--------|-------------|----------|
| Catch up if still ahead | Later run issues it from the same run; issue time recorded | ✓ |
| Skip it | Gaps after outages | |
| You decide | Planner picks | |

---

## Uncertainty band

**Band source**

| Option | Description | Selected |
|--------|-------------|----------|
| TEST to start, then live | Fixed hashed TEST band, switch to live misses vs live rating | ✓ |
| TEST only, fixed | Never learns from live | |
| Live only, no band at first | No band for the first weeks | |

**Band split**

| Option | Description | Selected |
|--------|-------------|----------|
| Per city × target hour | 16 bands, ~196 TEST misses each | ✓ |
| Per city only | 4 bands, wrong width at some hours | |

**Band width**

| Option | Description | Selected |
|--------|-------------|----------|
| 5–95%, same as 60-min | Read both bands the same way | ✓ |
| Wider (2.5–97.5%) | More cautious, harder to compare | |
| Publish both | More columns | |

**Actual =**

| Option | Description | Selected |
|--------|-------------|----------|
| Computed rating; skip fallbacks | Measures forecast skill; matches 60-min history rule | ✓ |
| Published rating | Mixes fallback policy into error | |

---

## Storage & what consumers see

**Storage**

| Option | Description | Selected |
|--------|-------------|----------|
| New table + new view | Keyed (city, target hour); 34-column contract untouched | ✓ |
| Extra columns on city_rating | Mostly blank rows; contract changes | |

**View shape**

| Option | Description | Selected |
|--------|-------------|----------|
| All upcoming targets | ~3 per city, ~12 rows | ✓ |
| Next target only | One row per city | |
| You decide | Planner chooses | |

**Label**

| Option | Description | Selected |
|--------|-------------|----------|
| Plain label + numbers in doc | `day-ahead-24h; engineering-selection; not-validated` + paragraph with TEST figures | ✓ |
| Label only, no numbers | No exploratory figures quoted | |

**Monitoring**

| Option | Description | Selected |
|--------|-------------|----------|
| Flag in view + extend alarm | Same failure email; no new cron | ✓ |
| Flag in view only | No email | |
| Run log only | No consumer flag or alarm | |

---

## Model files & failure policy

**Model files**

| Option | Description | Selected |
|--------|-------------|----------|
| Use in place, add to live manifest | No copies; pre-flight hash check | ✓ |
| Copy into data/models/ | Self-contained but duplicated bytes | |

**Failure**

| Option | Description | Selected |
|--------|-------------|----------|
| Green, but logged | Exit code reflects live ratings only; per-city day-ahead outcome in pipeline_run | ✓ |
| Red | Flaky API makes healthy ratings look broken | |
| Separate job step (continue-on-error) | Visible failure, run stays green | |

**Fallback**

| Option | Description | Selected |
|--------|-------------|----------|
| Nothing; log why | Every published value is the selected method | ✓ |
| raw_forecast, labelled | Fewer gaps, worse method mixed in | |

**Go-live**

| Option | Description | Selected |
|--------|-------------|----------|
| Push, verify, then expose | Verify first slot + parity, then grant SELECT and publish doc | ✓ |
| Short soak first | ~3 days hidden, owner sign-off | |
| Expose immediately | Grant in same push | |

---

## Claude's Discretion

- Table/view/column names; exact missing/late rule; band artifact format.
- Live-band switch-over threshold and granularity.
- Isolation of the day-ahead stage inside the live job (in-process vs child with timeout).
- Due-time rule given the ~6 h publication lag; catch-up detection.
- Whether live residual pairs are computed on the fly or stored.

## Deferred Ideas

- Hourly day-ahead issuance (24-29 h leads) once evidence exists.
- Statistical validation or rule-based re-selection (needs a new signed protocol, v4 O3).
- Periodic day-ahead calibration/coverage report.
