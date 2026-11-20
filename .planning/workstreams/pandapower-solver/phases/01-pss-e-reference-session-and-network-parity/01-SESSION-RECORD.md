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
| `switched_shunt` section | read with the revision 33 field table; built as a shunt at its initial setting (A-shunt); remote regulation refused |
| local voltage-control transformer | COD1 1 with a local or unset controlled bus is built at its initial tap (A-tap); every other control mode and a remote bus refused |
| parity | the switched shunts the builder creates are counted and compared on the export side |

A-shunt and A-tap were the owner's choice on 2026-11-19 (fixed at the starting setting; the base-case comparison against PSS/E tests them).

## Parity (NET-02)

Pass: 0 differences in all 11 categories (counts 5, classification 56, names 278, in_service 116, impedance 152, rating 34, voltage_limits 117, setpoints 22, machine_limits 40, loads 38, shunts 4 compared). Converted copy: 25191 bytes (3231 gzip), fits the secret limit.

D-06 evidence (the public pandapower case against the real export): 39 buses matched, 46 branches matched, 1 classification difference; the export has 12 transformers and 34 lines against 11 and 35, and 19 loads against 21; differences beyond 1e-6 in rating 34, voltage_limits 39, machine_limits 10, loads 9, setpoints 7, impedance 2, shunts 0.

## NET-03: FAIL (not yet explained)

Every city fails in both runs, with identical counts, so the failure is not the scaling rule (see below).

| City | Buses compared / failed | Flows compared / failed | Complete |
|------|-------------------------|-------------------------|----------|
| AUSTIN | 39 / 17 | 132 / 72 | no |
| CORPUS_CHRISTI | 39 / 14 | 132 / 78 | no |
| MIDLAND | 39 / 15 | 132 / 70 | no |
| EL_PASO | 39 / 19 | 132 / 81 | no |

- Algorithm run and injected-snapshot run give the same counts in every city. By D-12's attribution, a failure in both means a network or settings problem, not the scaling rule.
- Unexplained deviations per city: 85 to 100; explained: 0. The explained-differences registry is empty.
- Each city has 4 comparison keys with no counterpart (2 branches present under one orientation in pandapower and the opposite in the reference). That alone makes every comparison `incomplete`, so it needs fixing in how the reference names those two branches before any city can pass.
- The failures are reactive: bus voltages (14 to 19 buses per city, largest difference about 0.04 pu), reactive branch flows (39 to 43 per city, up to about 180 Mvar) and the apparent-power flows that follow from them (27 to 37 per city). Real-power flow differences appear in one city only (EL_PASO, 5 flows, about 2 MW at most). Candidate causes, none tested yet: the two switched shunts and the one voltage-control transformer held at their starting step (A-shunt, A-tap) while PSS/E may move them; how reactive limits are enforced; the two branch-orientation keys.

Nothing was changed to make NET-03 pass (R-3, D-12).

## Still open

- NET-03 for all four cities, and the explanation of every unexplained difference (needs the owner).
- ENG-05 (plan 02-07) and Phase 4 depend on NET-03.
