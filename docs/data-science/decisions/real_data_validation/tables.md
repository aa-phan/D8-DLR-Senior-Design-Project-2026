# VAL-01 tables

PROVISIONAL (OD-5): static ratings, rating bounds and line bearings are unconfirmed assumptions; these tables measure, they do not decide.

Fractions and rates use every expected step of the period as the denominator, so exhausted, errored, untraced and missing steps stay in the rates. Amps are rounded to 1 decimal, fractions to 4, weather inputs to 3. Empty cell = no value.

## val01_ratings_by_city

| city | expected_steps | static_a | lower_a | upper_a | reported_n | reported_min | reported_p05 | reported_p25 | reported_p50 | reported_p75 | reported_p95 | reported_max | reported_mean | frac_reported_above_static | frac_reported_equal_static | frac_reported_below_static | computed_n | computed_min | computed_p05 | computed_p25 | computed_p50 | computed_p75 | computed_p95 | computed_max | computed_mean | frac_computed_below_lower | frac_computed_within | frac_computed_above_upper | frac_computed_below_static |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | 336 | 1825.0 | 1150.0 | 2500.0 | 336 | 1150.5 | 1175.7 | 1296.3 | 1825.0 | 1825.0 | 1825.0 | 1825.0 | 1638.5 | 0.0 | 0.6815 | 0.3185 | 336 | 832.3 | 923.4 | 1015.0 | 1105.0 | 1186.5 | 1316.3 | 1569.5 | 1106.9 | 0.6696 | 0.3304 | 0.0 | 1.0 |
| CORPUS_CHRISTI | 336 | 1500.0 | 800.0 | 2200.0 | 336 | 902.7 | 998.9 | 1190.6 | 1406.0 | 1500.0 | 1551.5 | 1665.6 | 1339.7 | 0.1488 | 0.1101 | 0.7411 | 336 | 902.7 | 998.9 | 1177.7 | 1380.4 | 1459.3 | 1559.3 | 1682.5 | 1325.7 | 0.0 | 1.0 | 0.0 | 0.8363 |
| MIDLAND | 336 | 1875.0 | 1250.0 | 2500.0 | 336 | 1257.4 | 1316.6 | 1471.8 | 1603.2 | 1767.6 | 1875.0 | 1875.0 | 1610.9 | 0.0 | 0.2083 | 0.7917 | 336 | 917.0 | 1070.5 | 1314.4 | 1494.4 | 1620.8 | 1757.4 | 1858.0 | 1458.0 | 0.2024 | 0.7976 | 0.0 | 1.0 |
| EL_PASO | 336 | 1320.0 | 640.0 | 2000.0 | 336 | 856.3 | 938.6 | 1034.1 | 1132.7 | 1270.5 | 1603.4 | 1787.7 | 1179.0 | 0.1935 | 0.003 | 0.8036 | 336 | 856.3 | 938.6 | 1034.1 | 1132.7 | 1270.5 | 1616.3 | 1787.7 | 1180.3 | 0.0 | 1.0 | 0.0 | 0.8036 |

## val01_outcomes_by_city

| city | period | outcome | count | rate |
| --- | --- | --- | --- | --- |
| AUSTIN | warmup | ok | 44 | 0.2619 |
| AUSTIN | warmup | G1 | 0 | 0.0 |
| AUSTIN | warmup | G2 | 0 | 0.0 |
| AUSTIN | warmup | G3 | 0 | 0.0 |
| AUSTIN | warmup | G4_low | 123 | 0.7321 |
| AUSTIN | warmup | G4_high | 0 | 0.0 |
| AUSTIN | warmup | G5 | 0 | 0.0 |
| AUSTIN | warmup | G6 | 1 | 0.006 |
| AUSTIN | warmup | EXHAUSTED | 0 | 0.0 |
| AUSTIN | warmup | ERROR | 0 | 0.0 |
| AUSTIN | warmup | NO_TRACE | 0 | 0.0 |
| AUSTIN | warmup | MISSING | 0 | 0.0 |
| AUSTIN | scored | ok | 107 | 0.3185 |
| AUSTIN | scored | G1 | 0 | 0.0 |
| AUSTIN | scored | G2 | 0 | 0.0 |
| AUSTIN | scored | G3 | 0 | 0.0 |
| AUSTIN | scored | G4_low | 225 | 0.6696 |
| AUSTIN | scored | G4_high | 0 | 0.0 |
| AUSTIN | scored | G5 | 0 | 0.0 |
| AUSTIN | scored | G6 | 4 | 0.0119 |
| AUSTIN | scored | EXHAUSTED | 0 | 0.0 |
| AUSTIN | scored | ERROR | 0 | 0.0 |
| AUSTIN | scored | NO_TRACE | 0 | 0.0 |
| AUSTIN | scored | MISSING | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | ok | 107 | 0.6369 |
| CORPUS_CHRISTI | warmup | G1 | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G2 | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G3 | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G4_low | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G4_high | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G5 | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | G6 | 61 | 0.3631 |
| CORPUS_CHRISTI | warmup | EXHAUSTED | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | ERROR | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | NO_TRACE | 0 | 0.0 |
| CORPUS_CHRISTI | warmup | MISSING | 0 | 0.0 |
| CORPUS_CHRISTI | scored | ok | 299 | 0.8899 |
| CORPUS_CHRISTI | scored | G1 | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G2 | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G3 | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G4_low | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G4_high | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G5 | 0 | 0.0 |
| CORPUS_CHRISTI | scored | G6 | 37 | 0.1101 |
| CORPUS_CHRISTI | scored | EXHAUSTED | 0 | 0.0 |
| CORPUS_CHRISTI | scored | ERROR | 0 | 0.0 |
| CORPUS_CHRISTI | scored | NO_TRACE | 0 | 0.0 |
| CORPUS_CHRISTI | scored | MISSING | 0 | 0.0 |
| MIDLAND | warmup | ok | 159 | 0.9464 |
| MIDLAND | warmup | G1 | 0 | 0.0 |
| MIDLAND | warmup | G2 | 0 | 0.0 |
| MIDLAND | warmup | G3 | 0 | 0.0 |
| MIDLAND | warmup | G4_low | 6 | 0.0357 |
| MIDLAND | warmup | G4_high | 0 | 0.0 |
| MIDLAND | warmup | G5 | 0 | 0.0 |
| MIDLAND | warmup | G6 | 3 | 0.0179 |
| MIDLAND | warmup | EXHAUSTED | 0 | 0.0 |
| MIDLAND | warmup | ERROR | 0 | 0.0 |
| MIDLAND | warmup | NO_TRACE | 0 | 0.0 |
| MIDLAND | warmup | MISSING | 0 | 0.0 |
| MIDLAND | scored | ok | 266 | 0.7917 |
| MIDLAND | scored | G1 | 0 | 0.0 |
| MIDLAND | scored | G2 | 0 | 0.0 |
| MIDLAND | scored | G3 | 0 | 0.0 |
| MIDLAND | scored | G4_low | 68 | 0.2024 |
| MIDLAND | scored | G4_high | 0 | 0.0 |
| MIDLAND | scored | G5 | 0 | 0.0 |
| MIDLAND | scored | G6 | 2 | 0.006 |
| MIDLAND | scored | EXHAUSTED | 0 | 0.0 |
| MIDLAND | scored | ERROR | 0 | 0.0 |
| MIDLAND | scored | NO_TRACE | 0 | 0.0 |
| MIDLAND | scored | MISSING | 0 | 0.0 |
| EL_PASO | warmup | ok | 166 | 0.9881 |
| EL_PASO | warmup | G1 | 0 | 0.0 |
| EL_PASO | warmup | G2 | 0 | 0.0 |
| EL_PASO | warmup | G3 | 0 | 0.0 |
| EL_PASO | warmup | G4_low | 0 | 0.0 |
| EL_PASO | warmup | G4_high | 0 | 0.0 |
| EL_PASO | warmup | G5 | 0 | 0.0 |
| EL_PASO | warmup | G6 | 2 | 0.0119 |
| EL_PASO | warmup | EXHAUSTED | 0 | 0.0 |
| EL_PASO | warmup | ERROR | 0 | 0.0 |
| EL_PASO | warmup | NO_TRACE | 0 | 0.0 |
| EL_PASO | warmup | MISSING | 0 | 0.0 |
| EL_PASO | scored | ok | 335 | 0.997 |
| EL_PASO | scored | G1 | 0 | 0.0 |
| EL_PASO | scored | G2 | 0 | 0.0 |
| EL_PASO | scored | G3 | 0 | 0.0 |
| EL_PASO | scored | G4_low | 0 | 0.0 |
| EL_PASO | scored | G4_high | 0 | 0.0 |
| EL_PASO | scored | G5 | 0 | 0.0 |
| EL_PASO | scored | G6 | 1 | 0.003 |
| EL_PASO | scored | EXHAUSTED | 0 | 0.0 |
| EL_PASO | scored | ERROR | 0 | 0.0 |
| EL_PASO | scored | NO_TRACE | 0 | 0.0 |
| EL_PASO | scored | MISSING | 0 | 0.0 |

## val01_fallback_direction_by_city

| city | gate | fallback_steps | upward | downward | none | unknown | upward_rate | overstatement_median | overstatement_p95 | overstatement_max |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | G4_low | 225 | 225 | 0 | 0 | 0 | 0.6696 | 782.6 | 919.2 | 992.7 |
| AUSTIN | G4_high | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| AUSTIN | G6 | 4 | 4 | 0 | 0 | 0 | 0.0119 | 315.0 | 342.2 | 346.7 |
| AUSTIN | all | 229 | 229 | 0 | 0 | 0 | 0.6815 | 780.1 | 919.1 | 992.7 |
| CORPUS_CHRISTI | G4_low | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| CORPUS_CHRISTI | G4_high | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| CORPUS_CHRISTI | G6 | 37 | 32 | 5 | 0 | 0 | 0.0952 | 113.9 | 379.3 | 410.7 |
| CORPUS_CHRISTI | all | 37 | 32 | 5 | 0 | 0 | 0.0952 | 113.9 | 379.3 | 410.7 |
| MIDLAND | G4_low | 68 | 68 | 0 | 0 | 0 | 0.2024 | 717.2 | 904.4 | 958.0 |
| MIDLAND | G4_high | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| MIDLAND | G6 | 2 | 2 | 0 | 0 | 0 | 0.006 | 497.1 | 528.2 | 531.6 |
| MIDLAND | all | 70 | 70 | 0 | 0 | 0 | 0.2083 | 712.3 | 903.6 | 958.0 |
| EL_PASO | G4_low | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| EL_PASO | G4_high | 0 | 0 | 0 | 0 | 0 | 0.0 |  |  |  |
| EL_PASO | G6 | 1 | 0 | 1 | 0 | 0 | 0.0 |  |  |  |
| EL_PASO | all | 1 | 0 | 1 | 0 | 0 | 0.0 |  |  |  |

## val01_outliers

| city | rank_kind | rank | run_end_utc | outcome | reported_a | computed_a | obs_temp | obs_wind | obs_wind_raw | obs_wind_direction | obs_solar | temp_source | wind_source | solar_source | observation_hour |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | lowest | 1 | 2026-09-22T13:00:00Z | G4_low | 1825.0 | 832.3 | 26.778 | 0.168 | 0.492 | 188.0 | 23.0 | tceq | tceq | open_meteo | 2026-09-22T13:00:00Z |
| AUSTIN | lowest | 2 | 2026-09-21T00:00:00Z | G4_low | 1825.0 | 853.2 | 32.056 | 0.302 | 0.849 | 194.0 | 115.0 | tceq | tceq | open_meteo | 2026-09-21T00:00:00Z |
| AUSTIN | lowest | 3 | 2026-09-18T09:00:00Z | G4_low | 1825.0 | 853.7 | 24.278 | 0.168 | 0.492 | 159.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-18T09:00:00Z |
| AUSTIN | lowest | 4 | 2026-09-21T19:00:00Z | G4_low | 1825.0 | 865.1 | 34.333 | 0.581 | 1.699 | 154.0 | 768.0 | tceq | tceq | open_meteo | 2026-09-21T19:00:00Z |
| AUSTIN | lowest | 5 | 2026-09-20T00:00:00Z | G4_low | 1825.0 | 865.4 | 31.556 | 0.321 | 0.939 | 167.0 | 124.0 | tceq | tceq | open_meteo | 2026-09-20T00:00:00Z |
| AUSTIN | highest | 1 | 2026-09-21T02:00:00Z | G6 | 1825.0 | 1569.5 | 26.611 | 3.808 | 3.979 | 280.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-21T02:00:00Z |
| AUSTIN | highest | 2 | 2026-09-21T23:00:00Z | G6 | 1825.0 | 1511.6 | 32.5 | 4.369 | 4.426 | 74.0 | 306.0 | tceq | tceq | open_meteo | 2026-09-21T23:00:00Z |
| AUSTIN | highest | 3 | 2026-09-21T03:00:00Z | G6 | 1825.0 | 1508.4 | 25.0 | 3.082 | 3.085 | 261.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-21T03:00:00Z |
| AUSTIN | highest | 4 | 2026-09-20T14:00:00Z | G6 | 1825.0 | 1478.3 | 26.611 | 3.118 | 3.129 | 268.0 | 186.0 | tceq | tceq | open_meteo | 2026-09-20T14:00:00Z |
| AUSTIN | highest | 5 | 2026-09-22T00:00:00Z | ok | 1429.5 | 1429.5 | 30.667 | 3.186 | 3.219 | 75.0 | 120.0 | tceq | tceq | open_meteo | 2026-09-22T00:00:00Z |
| CORPUS_CHRISTI | lowest | 1 | 2026-09-27T08:00:00Z | ok | 902.7 | 902.7 | 27.2 | 0.291 | 0.849 | 192.0 | 0.0 | synoptic | tceq | open_meteo | 2026-09-27T07:00:00Z |
| CORPUS_CHRISTI | lowest | 2 | 2026-09-18T14:00:00Z | ok | 915.3 | 915.3 | 29.444 | 0.367 | 1.073 | 164.0 | 21.0 | asos | tceq | open_meteo | 2026-09-18T13:00:00Z |
| CORPUS_CHRISTI | lowest | 3 | 2026-09-20T12:00:00Z | ok | 927.8 | 927.8 | 23.333 | 0.277 | 0.805 | 153.0 | 0.0 | asos | tceq | open_meteo | 2026-09-20T11:00:00Z |
| CORPUS_CHRISTI | lowest | 4 | 2026-09-16T13:00:00Z | ok | 931.4 | 931.4 | 25.556 | 0.321 | 0.939 | 170.0 | 0.0 | asos | tceq | open_meteo | 2026-09-16T12:00:00Z |
| CORPUS_CHRISTI | lowest | 5 | 2026-09-22T12:00:00Z | ok | 932.2 | 932.2 | 24.444 | 0.303 | 0.805 | 151.0 | 0.0 | asos | tceq | open_meteo | 2026-09-22T11:00:00Z |
| CORPUS_CHRISTI | highest | 1 | 2026-09-18T06:00:00Z | G6 | 1500.0 | 1682.5 | 30.0 | 5.629 | 5.633 | 81.0 | 0.0 | asos | tceq | open_meteo | 2026-09-18T05:00:00Z |
| CORPUS_CHRISTI | highest | 2 | 2026-09-24T19:00:00Z | ok | 1665.6 | 1665.6 | 31.8 | 6.414 | 6.437 | 88.0 | 808.0 | synoptic | tceq | open_meteo | 2026-09-24T18:00:00Z |
| CORPUS_CHRISTI | highest | 3 | 2026-09-18T03:00:00Z | G6 | 1500.0 | 1652.6 | 30.0 | 5.266 | 5.32 | 75.0 | 0.0 | asos | tceq | open_meteo | 2026-09-18T02:00:00Z |
| CORPUS_CHRISTI | highest | 4 | 2026-09-24T20:00:00Z | ok | 1643.0 | 1643.0 | 31.9 | 6.111 | 6.169 | 91.0 | 768.0 | synoptic | tceq | open_meteo | 2026-09-24T19:00:00Z |
| CORPUS_CHRISTI | highest | 5 | 2026-09-24T21:00:00Z | ok | 1634.9 | 1634.9 | 31.7 | 5.978 | 6.035 | 91.0 | 798.0 | synoptic | tceq | open_meteo | 2026-09-24T20:00:00Z |
| MIDLAND | lowest | 1 | 2026-09-20T20:00:00Z | G4_low | 1875.0 | 917.0 | 33.5 | 0.78 | 2.28 | 102.0 | 799.0 | tceq | tceq | open_meteo | 2026-09-20T20:00:00Z |
| MIDLAND | lowest | 2 | 2026-09-20T21:00:00Z | G4_low | 1875.0 | 934.4 | 34.056 | 0.841 | 2.459 | 97.0 | 735.0 | tceq | tceq | open_meteo | 2026-09-20T21:00:00Z |
| MIDLAND | lowest | 3 | 2026-09-27T02:00:00Z | G4_low | 1875.0 | 960.3 | 29.778 | 0.489 | 1.431 | 101.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-27T02:00:00Z |
| MIDLAND | lowest | 4 | 2026-09-27T17:00:00Z | G4_low | 1875.0 | 968.1 | 31.278 | 0.813 | 1.475 | 301.0 | 646.0 | tceq | tceq | open_meteo | 2026-09-27T17:00:00Z |
| MIDLAND | lowest | 5 | 2026-09-27T20:00:00Z | G4_low | 1875.0 | 975.3 | 33.722 | 0.961 | 2.012 | 239.0 | 691.0 | tceq | tceq | open_meteo | 2026-09-27T20:00:00Z |
| MIDLAND | highest | 1 | 2026-09-15T14:00:00Z | ok | 1858.0 | 1858.0 | 26.333 | 7.146 | 7.153 | 175.0 | 115.0 | tceq | tceq | open_meteo | 2026-09-15T14:00:00Z |
| MIDLAND | highest | 2 | 2026-09-15T13:00:00Z | ok | 1835.9 | 1835.9 | 25.444 | 6.559 | 6.571 | 174.0 | 8.0 | tceq | tceq | open_meteo | 2026-09-15T13:00:00Z |
| MIDLAND | highest | 3 | 2026-09-15T15:00:00Z | ok | 1830.5 | 1830.5 | 27.889 | 7.325 | 7.331 | 180.0 | 340.0 | tceq | tceq | open_meteo | 2026-09-15T15:00:00Z |
| MIDLAND | highest | 4 | 2026-09-17T14:00:00Z | ok | 1823.4 | 1823.4 | 25.611 | 6.516 | 7.108 | 154.0 | 134.0 | tceq | tceq | open_meteo | 2026-09-17T14:00:00Z |
| MIDLAND | highest | 5 | 2026-09-17T15:00:00Z | ok | 1816.7 | 1816.7 | 27.0 | 6.905 | 7.242 | 160.0 | 349.0 | tceq | tceq | open_meteo | 2026-09-17T15:00:00Z |
| EL_PASO | lowest | 1 | 2026-09-21T17:00:00Z | ok | 856.3 | 856.3 | 29.722 | 0.398 | 1.162 | 102.0 | 693.0 | tceq | tceq | open_meteo | 2026-09-21T17:00:00Z |
| EL_PASO | lowest | 2 | 2026-09-18T23:00:00Z | ok | 874.4 | 874.4 | 32.556 | 0.443 | 1.296 | 96.0 | 418.0 | tceq | tceq | open_meteo | 2026-09-18T23:00:00Z |
| EL_PASO | lowest | 3 | 2026-09-19T17:00:00Z | ok | 883.3 | 883.3 | 29.0 | 0.427 | 1.073 | 111.0 | 622.0 | tceq | tceq | open_meteo | 2026-09-19T17:00:00Z |
| EL_PASO | lowest | 4 | 2026-09-27T17:00:00Z | ok | 886.8 | 886.8 | 28.833 | 0.443 | 1.296 | 76.0 | 668.0 | tceq | tceq | open_meteo | 2026-09-27T17:00:00Z |
| EL_PASO | lowest | 5 | 2026-09-18T22:00:00Z | ok | 900.5 | 900.5 | 33.111 | 0.657 | 1.922 | 254.0 | 624.0 | tceq | tceq | open_meteo | 2026-09-18T22:00:00Z |
| EL_PASO | highest | 1 | 2026-09-16T08:00:00Z | ok | 1787.7 | 1787.7 | 20.278 | 4.991 | 5.007 | 173.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-16T08:00:00Z |
| EL_PASO | highest | 2 | 2026-09-17T13:00:00Z | ok | 1772.3 | 1772.3 | 21.611 | 5.048 | 5.856 | 28.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-17T13:00:00Z |
| EL_PASO | highest | 3 | 2026-09-18T09:00:00Z | ok | 1761.6 | 1761.6 | 21.778 | 4.962 | 5.409 | 21.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-18T09:00:00Z |
| EL_PASO | highest | 4 | 2026-09-18T11:00:00Z | ok | 1761.4 | 1761.4 | 21.556 | 4.924 | 5.409 | 22.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-18T11:00:00Z |
| EL_PASO | highest | 5 | 2026-09-23T02:00:00Z | ok | 1749.4 | 1749.4 | 19.444 | 4.482 | 5.007 | 24.0 | 0.0 | tceq | tceq | open_meteo | 2026-09-23T02:00:00Z |

## val01_drivers_by_city

| city | group | n | temp_median | solar_median | wind_raw_median | wind_proj_median | perp_fraction_median | wind_open_meteo_share | solar_open_meteo_share | lag_over_1h_share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | below_lower | 225 | 26.778 | 0.0 | 1.699 | 0.78 | 0.3559 | 0.0 | 1.0 | 0.0 |
| AUSTIN | within | 111 | 30.889 | 304.0 | 2.414 | 2.034 | 0.9345 | 0.0 | 1.0 | 0.0 |
| AUSTIN | above_upper | 0 |  |  |  |  |  |  |  |  |
| CORPUS_CHRISTI | below_lower | 0 |  |  |  |  |  |  |  |  |
| CORPUS_CHRISTI | within | 336 | 29.444 | 21.0 | 3.398 | 2.678 | 0.8585 | 0.0 | 1.0 | 0.0357 |
| CORPUS_CHRISTI | above_upper | 0 |  |  |  |  |  |  |  |  |
| MIDLAND | below_lower | 68 | 28.111 | 19.0 | 2.727 | 1.17 | 0.342 | 0.0 | 1.0 | 0.0 |
| MIDLAND | within | 268 | 26.667 | 7.0 | 4.605 | 3.85 | 0.8946 | 0.0 | 1.0 | 0.0 |
| MIDLAND | above_upper | 0 |  |  |  |  |  |  |  |  |
| EL_PASO | below_lower | 0 |  |  |  |  |  |  |  |  |
| EL_PASO | within | 336 | 25.028 | 3.5 | 2.012 | 1.083 | 0.5801 | 0.0 | 1.0 | 0.0 |
| EL_PASO | above_upper | 0 |  |  |  |  |  |  |  |  |

## Cleaning activity

| city | rows_in | rows_usable | rows_excluded | missing_slots | bad_timestamp | duplicate | fallback | at_or_after_run | same_hour | stuck_air_temp | stuck_wind_speed | stuck_solar_radiation | spike_air_temp | spike_wind_speed | spike_solar_radiation | after_gap |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | 504 | 151 | 353 | 350 | 0 | 0 | 353 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 56 |
| CORPUS_CHRISTI | 504 | 400 | 104 | 103 | 0 | 0 | 98 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 0 | 33 |
| MIDLAND | 504 | 425 | 79 | 79 | 0 | 0 | 79 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 25 |
| EL_PASO | 504 | 501 | 3 | 3 | 0 | 0 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |

# VAL-02 tables

PROVISIONAL (OD-5): static ratings, rating bounds and line bearings are unconfirmed assumptions; these tables measure, they do not decide.

Populations. `n_g6_evaluated`: scored steps that passed G1-G5 (outcome ok or G6), so the detector ran on them. `n_band` (the coverage population): of those, steps with a forecast whose band is wider than zero and a computed rating, whether or not G6 used the forecast. `coverage_nominal` = computed rating inside the forecast's own 5-95% band (nominal target 0.90), with a day-block bootstrap 95% interval (whole UTC days, 2000 resamples, fixed seed); the interval is empty with fewer than two days. `coverage_widened` is inside the detector's widened band, on `n_used_by_g6` only. Warm-up, steps that fell back at G1-G5 or were exhausted, cold starts, silent forecast failures, zero-width bands and forecasts withheld across a gap are counted in their own columns, never mixed in. `trip_rate` = G6 trips / `n_g6_evaluated`. Rates are exact count ratios; read each with its n.

Method label(s): ml, naive_replay. A `naive_replay` row, when present, is a counterfactual reference (same observations, different forecast method), not what the live system did.

## val02_forecast_by_city

| city | method | n_warmup | n_scored | n_not_g6 | n_g6_evaluated | n_with_forecast | n_cold_start | n_silent_forecast_failure | n_cleaning_failure_suspect | n_degenerate_band | n_no_computed | n_band | n_withheld_gap | n_used_by_g6 | coverage_nominal | nominal_target | coverage_ci_lo | coverage_ci_hi | coverage_widened | width_mean_a | width_median_a | mae_a | bias_a | n_all_computed | coverage_all_computed |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | ml | 168 | 336 | 225 | 111 | 111 | 0 | 0 | 0 | 0 | 0 | 111 | 96 | 15 | 0.8108 | 0.9 | 0.7327 | 0.88 | 1.0 | 257.6 | 262.5 | 104.1 | 87.6 | 336 | 0.4851 |
| AUSTIN | naive_replay | 168 | 336 | 225 | 111 | 111 | 0 | 0 | 0 | 0 | 0 | 111 | 28 | 83 | 0.8649 | 0.9 | 0.7475 | 0.9549 | 1.0 | 225.6 | 228.6 | 62.3 | 0.4 | 336 | 0.503 |
| CORPUS_CHRISTI | ml | 168 | 336 | 0 | 336 | 336 | 0 | 0 | 0 | 0 | 0 | 336 | 103 | 233 | 0.8958 | 0.9 | 0.8452 | 0.9435 | 1.0 | 343.8 | 335.3 | 86.4 | 41.9 | 336 | 0.8958 |
| CORPUS_CHRISTI | naive_replay | 168 | 336 | 0 | 336 | 336 | 0 | 0 | 0 | 0 | 0 | 336 | 20 | 316 | 0.9018 | 0.9 | 0.8661 | 0.9345 | 1.0 | 324.8 | 319.9 | 62.9 | 2.5 | 336 | 0.9018 |
| MIDLAND | ml | 168 | 336 | 68 | 268 | 268 | 0 | 0 | 0 | 0 | 0 | 268 | 99 | 169 | 0.8134 | 0.9 | 0.7719 | 0.8567 | 0.9882 | 268.6 | 261.4 | 94.2 | 49.8 | 336 | 0.6994 |
| MIDLAND | naive_replay | 168 | 336 | 68 | 268 | 268 | 0 | 0 | 0 | 0 | 0 | 268 | 16 | 252 | 0.8097 | 0.9 | 0.7553 | 0.8605 | 1.0 | 273.9 | 263.3 | 80.3 | -0.5 | 336 | 0.6935 |
| EL_PASO | ml | 168 | 336 | 0 | 336 | 336 | 0 | 0 | 0 | 0 | 0 | 336 | 6 | 330 | 0.8839 | 0.9 | 0.8363 | 0.9256 | 1.0 | 444.2 | 454.3 | 126.7 | 77.6 | 336 | 0.8839 |
| EL_PASO | naive_replay | 168 | 336 | 0 | 336 | 336 | 0 | 0 | 0 | 0 | 0 | 336 | 0 | 336 | 0.881 | 0.9 | 0.8274 | 0.9316 | 1.0 | 507.2 | 517.0 | 117.3 | 0.0 | 336 | 0.881 |

## val02_coverage_by_residuals

| city | method | period | bucket | n | coverage_nominal | n_zero_width |
| --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | ml | warmup | 0 | 0 |  | 1 |
| AUSTIN | ml | warmup | 1-47 | 28 | 0.6786 | 4 |
| AUSTIN | ml | warmup | 48-167 | 0 |  | 0 |
| AUSTIN | ml | warmup | 168+ | 0 |  | 0 |
| AUSTIN | ml | scored | 0 | 0 |  | 0 |
| AUSTIN | ml | scored | 1-47 | 16 | 0.875 | 0 |
| AUSTIN | ml | scored | 48-167 | 95 | 0.8 | 0 |
| AUSTIN | ml | scored | 168+ | 0 |  | 0 |
| AUSTIN | naive_replay | warmup | 0 | 0 |  | 1 |
| AUSTIN | naive_replay | warmup | 1-47 | 30 | 0.7333 | 2 |
| AUSTIN | naive_replay | warmup | 48-167 | 0 |  | 0 |
| AUSTIN | naive_replay | warmup | 168+ | 0 |  | 0 |
| AUSTIN | naive_replay | scored | 0 | 0 |  | 0 |
| AUSTIN | naive_replay | scored | 1-47 | 15 | 1.0 | 0 |
| AUSTIN | naive_replay | scored | 48-167 | 96 | 0.8438 | 0 |
| AUSTIN | naive_replay | scored | 168+ | 0 |  | 0 |
| CORPUS_CHRISTI | ml | warmup | 0 | 0 |  | 1 |
| CORPUS_CHRISTI | ml | warmup | 1-47 | 70 | 0.8286 | 1 |
| CORPUS_CHRISTI | ml | warmup | 48-167 | 82 | 0.8415 | 0 |
| CORPUS_CHRISTI | ml | warmup | 168+ | 0 |  | 0 |
| CORPUS_CHRISTI | ml | scored | 0 | 0 |  | 0 |
| CORPUS_CHRISTI | ml | scored | 1-47 | 0 |  | 0 |
| CORPUS_CHRISTI | ml | scored | 48-167 | 97 | 0.8454 | 0 |
| CORPUS_CHRISTI | ml | scored | 168+ | 239 | 0.9163 | 0 |
| CORPUS_CHRISTI | naive_replay | warmup | 0 | 0 |  | 1 |
| CORPUS_CHRISTI | naive_replay | warmup | 1-47 | 69 | 0.7971 | 2 |
| CORPUS_CHRISTI | naive_replay | warmup | 48-167 | 82 | 0.7805 | 0 |
| CORPUS_CHRISTI | naive_replay | warmup | 168+ | 0 |  | 0 |
| CORPUS_CHRISTI | naive_replay | scored | 0 | 0 |  | 0 |
| CORPUS_CHRISTI | naive_replay | scored | 1-47 | 0 |  | 0 |
| CORPUS_CHRISTI | naive_replay | scored | 48-167 | 97 | 0.866 | 0 |
| CORPUS_CHRISTI | naive_replay | scored | 168+ | 239 | 0.9163 | 0 |
| MIDLAND | ml | warmup | 0 | 0 |  | 1 |
| MIDLAND | ml | warmup | 1-47 | 37 | 0.8919 | 10 |
| MIDLAND | ml | warmup | 48-167 | 102 | 0.8627 | 0 |
| MIDLAND | ml | warmup | 168+ | 0 |  | 0 |
| MIDLAND | ml | scored | 0 | 0 |  | 0 |
| MIDLAND | ml | scored | 1-47 | 0 |  | 0 |
| MIDLAND | ml | scored | 48-167 | 21 | 0.8095 | 0 |
| MIDLAND | ml | scored | 168+ | 247 | 0.8138 | 0 |
| MIDLAND | naive_replay | warmup | 0 | 0 |  | 1 |
| MIDLAND | naive_replay | warmup | 1-47 | 46 | 0.8043 | 3 |
| MIDLAND | naive_replay | warmup | 48-167 | 100 | 0.88 | 0 |
| MIDLAND | naive_replay | warmup | 168+ | 0 |  | 0 |
| MIDLAND | naive_replay | scored | 0 | 0 |  | 0 |
| MIDLAND | naive_replay | scored | 1-47 | 0 |  | 0 |
| MIDLAND | naive_replay | scored | 48-167 | 22 | 0.7727 | 0 |
| MIDLAND | naive_replay | scored | 168+ | 246 | 0.813 | 0 |
| EL_PASO | ml | warmup | 0 | 0 |  | 1 |
| EL_PASO | ml | warmup | 1-47 | 45 | 0.7556 | 4 |
| EL_PASO | ml | warmup | 48-167 | 106 | 0.9434 | 0 |
| EL_PASO | ml | warmup | 168+ | 0 |  | 0 |
| EL_PASO | ml | scored | 0 | 0 |  | 0 |
| EL_PASO | ml | scored | 1-47 | 0 |  | 0 |
| EL_PASO | ml | scored | 48-167 | 14 | 0.7857 | 0 |
| EL_PASO | ml | scored | 168+ | 322 | 0.8882 | 0 |
| EL_PASO | naive_replay | warmup | 0 | 0 |  | 1 |
| EL_PASO | naive_replay | warmup | 1-47 | 48 | 0.7292 | 1 |
| EL_PASO | naive_replay | warmup | 48-167 | 106 | 0.9528 | 0 |
| EL_PASO | naive_replay | warmup | 168+ | 0 |  | 0 |
| EL_PASO | naive_replay | scored | 0 | 0 |  | 0 |
| EL_PASO | naive_replay | scored | 1-47 | 0 |  | 0 |
| EL_PASO | naive_replay | scored | 48-167 | 14 | 0.7857 | 0 |
| EL_PASO | naive_replay | scored | 168+ | 322 | 0.8851 | 0 |

## val02_detector_by_city

| city | method | n_g6_evaluated | n_g6_trips | trip_rate | trip_rate_ci_lo | trip_rate_ci_hi | forecast_runs | rolling_runs | model_runs | cold_start_runs | forecast_votes | rolling_votes | model_votes | detector_errors | n_g6_trips_unattributed | model_trip_rate | n_detector_model_missing | anomaly_ml_max_false_positive_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUSTIN | ml | 111 | 4 | 0.036 | 0.0 | 0.0935 | 15 | 96 | 111 | 0 | 0 | 4 | 0 | 0 | 0 | 0.0 | 0 | 0.05 |
| AUSTIN | naive_replay | 111 | 0 | 0.0 | 0.0 | 0.0 | 83 | 28 | 111 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | 0.05 |
| CORPUS_CHRISTI | ml | 336 | 37 | 0.1101 | 0.0595 | 0.1637 | 233 | 103 | 336 | 0 | 0 | 0 | 37 | 0 | 0 | 0.1101 | 0 | 0.05 |
| CORPUS_CHRISTI | naive_replay | 336 | 37 | 0.1101 | 0.0595 | 0.1637 | 316 | 20 | 336 | 0 | 0 | 0 | 37 | 0 | 0 | 0.1101 | 0 | 0.05 |
| MIDLAND | ml | 268 | 2 | 0.0075 | 0.0 | 0.0229 | 169 | 99 | 268 | 0 | 2 | 0 | 0 | 0 | 0 | 0.0 | 0 | 0.05 |
| MIDLAND | naive_replay | 268 | 0 | 0.0 | 0.0 | 0.0 | 252 | 16 | 268 | 0 | 0 | 0 | 0 | 0 | 0 | 0.0 | 0 | 0.05 |
| EL_PASO | ml | 336 | 1 | 0.003 | 0.0 | 0.0089 | 330 | 6 | 336 | 0 | 0 | 0 | 1 | 0 | 0 | 0.003 | 0 | 0.05 |
| EL_PASO | naive_replay | 336 | 1 | 0.003 | 0.0 | 0.0089 | 336 | 0 | 336 | 0 | 0 | 0 | 1 | 0 | 0 | 0.003 | 0 | 0.05 |

## G6 trips

The trip list can run to hundreds of rows, so it is CSV-only: `val02_g6_trips.csv` (at most 50 per city and method, ordered by deviation of the computed rating from the forecast centre, then time; each row carries its votes, the widened band and the traced reason).

| city | method | trips_listed |
| --- | --- | --- |
| AUSTIN | ml | 4 |
| CORPUS_CHRISTI | ml | 37 |
| CORPUS_CHRISTI | naive_replay | 37 |
| MIDLAND | ml | 2 |
| EL_PASO | ml | 1 |
| EL_PASO | naive_replay | 1 |
