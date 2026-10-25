# Phase 7: Per-City Conductors, Shadow Refit and Early Model Selection - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-25
**Phase:** 07-per-city-conductors-shadow-refit-and-early-model-selection
**Areas discussed:** FRESH-read conductor & evidence weight; v4 numbers & no-winner rule; Provisional conductors per city; Interim G6 method, B4/B5, go/no-go

---

## FRESH-read conductor & evidence weight

| Option | Description | Selected |
|--------|-------------|----------|
| Production conductors | Headline under per-city production config with SEL-02 refits; Drake frozen artifacts as labelled secondary | ✓ |
| Drake, as v3 designed | Headline scores the 12 frozen Drake artifacts | |
| Both as co-headlines | Must qualify under both | |

| Option | Description | Selected |
|--------|-------------|----------|
| FRESH decides, earlier ones veto | ABLATION and TEST are pre-registered vetoes | ✓ |
| TEST decides, FRESH confirms | TEST picks, FRESH must not contradict | |
| Pooled weighted rule | One combined score | |

| Option | Description | Selected |
|--------|-------------|----------|
| Stands if ABLATION showed invariance | Otherwise conductor-conditional plus a descriptive re-score that can flag but not overturn | ✓ |
| Always stands | | |
| Pre-registered second read | | |

| Option | Description | Selected |
|--------|-------------|----------|
| One method, 3-of-4 rule | v3 decision 8 | ✓ |
| Per-city winners | | |
| One method, any city can veto | | |

---

## v4 numbers & no-winner rule

The owner asked for a plain-language explanation of the dates question before answering.

| Option | Description | Selected |
|--------|-------------|----------|
| 1-week gap (cutoff 10-25, instant 11-01) | Same as v3, about 100 rows per city | ✓ |
| 2 days if verified | About 116 rows, needs a truth re-fetch diff | |

| Option | Description | Selected |
|--------|-------------|----------|
| 0.5% | Same bar as old 5 A | |
| 1% | | |
| 2% | About what 100 rows can resolve | ✓ |

| Option | Description | Selected |
|--------|-------------|----------|
| Keep wind-corrected default | | |
| Use the plain forecast | | |
| No pick yet; re-test later | | ✓ |

Re-test: options 11-24 / mid-December / other → **User's choice: 2026-11-08** (free text). Data: **all rows, pre-registered** (selected) vs only new rows.

---

## Provisional conductors per city

| Option | Description | Selected |
|--------|-------------|----------|
| Suwannee at 200 °C | Matches the 1825 A static | |
| Drake at 100 °C | Austin Energy 2005 practice | |
| Keep Drake at 75 °C | No change until Power Systems | ✓ |

Other cities: **Drake 75 °C like Austin** (selected) vs quick research per city.
Elevation: measured elevations vs **keep 900 m until Power Systems** (selected).
Early Power Systems answer: lock Drake at signing vs **yes, if by a set date** (selected).
Deadline: 10-29 / 10-27 / **end of 10-30** (selected).
GO on the Drake guess: **yes, labelled provisional** (selected) vs no GO until real values.

---

## Interim G6 method, B4/B5, go/no-go

G6 method: naive / **ml retrained on cross-wind** (selected) / retrain then pick the better one.

B4: the owner asked why B4 is an issue, then asked about the impact of retraining later. After the explanation: **accept now, retrain with the wire update** (selected) vs accept only vs retrain this phase.

B5: **naive band fills in** (selected) / count fallback hours in history / accept the gap and make it visible.

Retrained ml still loses to naive: switch to naive / keep ml / **decide when I see it** (selected).

GO bar: **checklist, then owner's call** (selected) / owner call only / strict numeric bars.

---

## Claude's Discretion

- v4 text: exact ABLATION invariance and TEST veto criteria; "qualifies" definition; Holm family carried from v3.
- Partial Power Systems answers: per-city switch default (flagged).
- Fallback date for the CORPUS_CHRISTI detector refit.
- What happens if the 11-08 re-test also names no winner (default suggested for owner confirmation).

## Deferred Ideas

- CORPUS_CHRISTI detector refit on station data, bundled with the conductor retrain.
- Real elevations and AUSTIN conductor alternatives: wait for Power Systems.
