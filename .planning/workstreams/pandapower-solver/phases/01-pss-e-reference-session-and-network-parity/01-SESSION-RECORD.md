# 01-10 Session record (the first real PSS/E session)

Versions, counts, statuses, rule names and pass or fail only. No bus number, branch key, name, value or path.

## Session

| Item | Value |
|------|-------|
| Session date (UTC) | 2026-11-20, 00:32 (18:32 on the laptop, 2026-11-19) |
| PSS/E, Python | 36.4.0 (Xplore, 50-bus limit), Python 3.14.0 |
| Outcome | `complete`, exit code 0, every section ok, 135 members |
| Earlier runs | Run 1 `partial` (network and scaling failed: no RAW export). Run 2 `-Only scaling`: network and scaling ok, 15 members. Run 3 (this record) is the full run. |
| RAW revision written | 33, first attempt, after the export fix below |
| Zip handling | Ingest verified all 135 members against the manifest; the member count and every section status equal the teammate's pasted summary. The mapping's sha256 matched the manifest. |

## Section counts

| Section | Result |
|---------|--------|
| network | areas 2, buses 39, lines 34, transformers 12 (three-winding 0, controlling 1), loads 19, machines 10, fixed shunts 0, switched shunts 2 |
| reference | cities 4 (all ok), outages 32 (all converged, 0 not converged), margin points 8, extended reads unavailable 0 |
| settings | fingerprints 32, ok 29; ten settings: read 2, measured 5, unavailable 3; deviations from D-14: 0; `enforce_q_lims` on |
| scaling | experiments 4, all ok |

## Scaling details (PSE-02)

| Detail | Result |
|--------|--------|
| swing machine absorbs the difference in a total-load scale | yes |
| generation clamped at its limits when scaled past them | no |
| reactive load scales with real load | yes |

## Parser and builder changes the real file needed (each a named, exact capability with a synthetic test)

| Rule | Change |
|------|--------|
| session export form | `writerawversion` takes the version as text; the first two forms raised TypeError with an int |
| session header read | the revision sits after `@!` comment lines in revision 35 and later |
| `switched_shunt` section | read with the revision 33 field table; built at its initial setting and, for discrete voltage control (MODSW 1, ADJM 0), stepped one level at a time by the solve until the bus voltage is inside the band (A-shunt); locked shunts stay fixed; other modes, off-level starts, inverted bands and remote control refused (`switched_shunt_control`, `remote_regulation`) |
| local voltage-control transformer | COD1 1 with a local or unset controlled bus is built at its initial tap (A-tap); every other control mode and a remote bus refused |
| parity | the switched shunts the builder creates are counted and compared on the export side |
| comparison join | a branch the reference lists from the opposite end is joined to the net's branch and compared at the net's other end (2 transformers in this case); a branch under both orientations on one side stays missing |

A-shunt and A-tap were first the owner's choice on 2026-11-19 (fixed at the starting setting; the base-case comparison against PSS/E tests them). The first full comparison failed (see below), PSS/E's own solved case showed it moved both shunts in every city and no tap, and the owner then approved step control for the shunts (A-tap stays fixed: no tap moved in any city).

## Parity (NET-02)

Pass: 0 differences in all 11 categories (counts 5, classification 56, names 278, in_service 116, impedance 152, rating 34, voltage_limits 117, setpoints 22, machine_limits 40, loads 38, shunts 4 compared). Converted copy: 25191 bytes (3231 gzip), fits the secret limit.

D-06 evidence (the public pandapower case against the real export): 39 buses matched, 46 branches matched, 1 classification difference; the export has 12 transformers and 34 lines against 11 and 35, and 19 loads against 21; differences beyond 1e-6 in rating 34, voltage_limits 39, machine_limits 10, loads 9, setpoints 7, impedance 2, shunts 0.

## NET-03: PASS (4 of 4 cities)

Both runs pass in every city with nothing failed and no explained-differences entry.

| City | Run | Buses compared / failed | Flows compared / failed | Complete |
|------|-----|-------------------------|-------------------------|----------|
| AUSTIN | algorithm, injected | 39 / 0 | 138 / 0 | yes |
| CORPUS_CHRISTI | algorithm, injected | 39 / 0 | 138 / 0 | yes |
| MIDLAND | algorithm, injected | 39 / 0 | 138 / 0 | yes |
| EL_PASO | algorithm, injected | 39 / 0 | 138 / 0 | yes |

### How it got here (counts only)

1. First comparison, shunts and taps held at their starting setting: every city failed in both runs with identical counts (buses failed 14 to 19, flows failed 70 to 81 of 132), all of it reactive power and voltage, and 4 branch keys per city unjoined (so incomplete).
2. Diagnosis from PSS/E's own pre-solve and solved cases: both switched shunts changed step in all four cities; no transformer tap changed; 0 or 1 of 10 machines sat at a reactive limit. With PSS/E's final shunt steps given to pandapower, every bus voltage matched within 1e-4 pu in every city.
3. A band-stepping rule (a shunt above its band steps down one level, below it steps up one level, repeat until nothing moves) reproduced PSS/E's final step of both shunts in all four cities. It was built into the solve with synthetic tests.
4. With the stepping, buses and flows failed 0 in every city; the remaining incompleteness was the 4 unjoined keys per city (2 transformers listed from the opposite end by PSS/E). They are joined by orientation (see the table above) with a synthetic test, and every comparison became complete.

Nothing was tuned: no tolerance, no network parameter and no registry entry changed (R-3, D-12). The voltage and flow tolerances are untouched.

## Still open

- ENG-05 (plan 02-07) and Phase 4 can proceed: they needed the real settings and a passing NET-03.
- The real run showed `enforce_q_lims` is on (settings classification), with 0 deviations from D-14.
