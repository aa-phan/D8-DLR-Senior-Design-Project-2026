# TEST-split re-score (SEL-03)

## In plain English

The frozen models were fitted on rows before 2026-03-17, so the rows from 2026-03-18T00:00:00+00:00 up to, not including, 2026-09-30T00:00:00+00:00 are data they never saw. Conductor basis: production. This check can only veto a method; it never picks one or confirms one. A method is vetoed when its average error is strictly higher than the plain forecast's (raw_forecast), on the rows both have, in at least 3 of the cities with data; a tie is not a loss.

- ml_wind_corrected: not vetoed. It beats raw_forecast in 4 city(ies) (AUSTIN, CORPUS_CHRISTI, EL_PASO, MIDLAND) and has a higher error in 0.
- ml_cooling_corrected: not vetoed. It beats raw_forecast in 4 city(ies) (AUSTIN, CORPUS_CHRISTI, EL_PASO, MIDLAND) and has a higher error in 0.
- reference_ml_refit_24h: not vetoed. It beats raw_forecast in 3 city(ies) (AUSTIN, CORPUS_CHRISTI, EL_PASO) and has a higher error in 1 (MIDLAND).

## Mean absolute error by city (amps, complete-case pairs)

| candidate | city | MAE candidate | MAE raw_forecast | result |
|---|---|---|---|---|
| ml_wind_corrected | AUSTIN | 126.10 | 133.33 | better than raw |
| ml_wind_corrected | CORPUS_CHRISTI | 88.06 | 110.76 | better than raw |
| ml_wind_corrected | MIDLAND | 122.96 | 129.09 | better than raw |
| ml_wind_corrected | EL_PASO | 130.84 | 168.63 | better than raw |
| ml_cooling_corrected | AUSTIN | 106.48 | 133.33 | better than raw |
| ml_cooling_corrected | CORPUS_CHRISTI | 85.78 | 110.76 | better than raw |
| ml_cooling_corrected | MIDLAND | 119.92 | 129.09 | better than raw |
| ml_cooling_corrected | EL_PASO | 126.33 | 168.63 | better than raw |
| reference_ml_refit_24h | AUSTIN | 122.64 | 133.33 | better than raw |
| reference_ml_refit_24h | CORPUS_CHRISTI | 101.34 | 110.76 | better than raw |
| reference_ml_refit_24h | MIDLAND | 178.20 | 129.09 | worse than raw |
| reference_ml_refit_24h | EL_PASO | 141.42 | 168.63 | better than raw |

Veto rule: `mae_strictly_higher_than_raw_forecast_in_at_least_min_cities_of_the_cities_with_data` with min_cities = 3 (signed registry `test.veto_min_cities`).

TEST can only veto. The window is partly already seen (the corridor-era result on it was read once).
