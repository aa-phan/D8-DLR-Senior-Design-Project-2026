# ABLATION conductor-invariance re-score (SEL-03)

## Summary (plain English)

Basis: ABLATION (train <= 2025-09-01T18:00Z, validation 2025-09-02..2026-03-16). Cooling and reference were refit on the early rows only and every method was scored on the validation rows, once under each bracketing conductor. This can only disqualify a method (a veto); it can never pick one or confirm one.

Conductors tried besides the control (Drake-75): Drake-100, Falcon-90, Suwannee-150, Suwannee-200, Drake-75-AUSTIN-163m.
Ranking: the order of the five methods is identical under every bracketing conductor, and nothing is vetoed, so the ranking is invariant to the conductor.

- ml_wind_corrected: keeps its standing under every bracketing conductor (no veto).
- ml_cooling_corrected: keeps its standing under every bracketing conductor (no veto).
- reference_ml_refit_24h: keeps its standing under every bracketing conductor (no veto).

Veto rule: `sign_flip_vs_raw_or_default` (the v4 draft's three clauses; see the module docstring).

## Variants

| variant | cities | max temp C | Kendall tau vs control | order, best first |
|---|---|---|---|---|
| Drake-75 | AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO | 75.0 | 1.0 | ml_cooling_corrected > ml_wind_corrected > raw_forecast > reference_ml_refit_24h > persistence_24h |
| Drake-100 | AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO | 100.0 | 1.0 | ml_cooling_corrected > ml_wind_corrected > raw_forecast > reference_ml_refit_24h > persistence_24h |
| Falcon-90 | AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO | 90.0 | 1.0 | ml_cooling_corrected > ml_wind_corrected > raw_forecast > reference_ml_refit_24h > persistence_24h |
| Suwannee-150 (resistance unverified at this temperature) | AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO | 150.0 | 1.0 | ml_cooling_corrected > ml_wind_corrected > raw_forecast > reference_ml_refit_24h > persistence_24h |
| Suwannee-200 (resistance unverified at this temperature) | AUSTIN, CORPUS_CHRISTI, MIDLAND, EL_PASO | 200.0 | 1.0 | ml_cooling_corrected > ml_wind_corrected > raw_forecast > reference_ml_refit_24h > persistence_24h |
| Drake-75-AUSTIN-163m | AUSTIN | 75.0 | 1.0 | ml_cooling_corrected > raw_forecast > ml_wind_corrected > reference_ml_refit_24h > persistence_24h |

## Margins over raw_forecast and over ml_wind_corrected

A positive margin means the candidate has the lower MAE. Amps are pooled over the variant's cities.

### Drake-75
- ml_wind_corrected over raw_forecast: 17.14466447577482 A (12.112 %)
- ml_cooling_corrected over raw_forecast: 23.576721140330122 A (16.657 %)
- reference_ml_refit_24h over raw_forecast: -15.183195905314394 A (-10.727 %)
- ml_cooling_corrected over ml_wind_corrected: 6.432056664555299 A; favoured in 2 of 4 cities
- reference_ml_refit_24h over ml_wind_corrected: -32.32786038108921 A; favoured in 0 of 4 cities

### Drake-100
- ml_wind_corrected over raw_forecast: 20.138388910536456 A (12.463 %)
- ml_cooling_corrected over raw_forecast: 26.848592383860826 A (16.615 %)
- reference_ml_refit_24h over raw_forecast: -16.172505863667872 A (-10.008 %)
- ml_cooling_corrected over ml_wind_corrected: 6.710203473324365 A; favoured in 2 of 4 cities
- reference_ml_refit_24h over ml_wind_corrected: -36.31089477420432 A; favoured in 1 of 4 cities

### Falcon-90
- ml_wind_corrected over raw_forecast: 29.235057226583244 A (12.276 %)
- ml_cooling_corrected over raw_forecast: 39.621666613401665 A (16.638 %)
- reference_ml_refit_24h over raw_forecast: -23.86385854174293 A (-10.021 %)
- ml_cooling_corrected over ml_wind_corrected: 10.38660938681842 A; favoured in 2 of 4 cities
- reference_ml_refit_24h over ml_wind_corrected: -53.09891576832617 A; favoured in 1 of 4 cities

### Suwannee-150
- ml_wind_corrected over raw_forecast: 26.617117995865758 A (12.882 %)
- ml_cooling_corrected over raw_forecast: 34.16739500109003 A (16.536 %)
- reference_ml_refit_24h over raw_forecast: -19.997404623596914 A (-9.678 %)
- ml_cooling_corrected over ml_wind_corrected: 7.5502770052242605 A; favoured in 2 of 4 cities
- reference_ml_refit_24h over ml_wind_corrected: -46.614522619462676 A; favoured in 1 of 4 cities
- Caveat: Suwannee-150 and Suwannee-200 use the catalogue ACSS/TW resistance (0.0597 ohm/km at 25 C) in the repo's linear resistance model; that model's accuracy for ACSS/TW at 150-200 C is unverified (shadow_early_decision_options.md, 'Items I could not verify').

### Suwannee-200
- ml_wind_corrected over raw_forecast: 29.434342557785264 A (13.181 %)
- ml_cooling_corrected over raw_forecast: 37.399558573061974 A (16.748 %)
- reference_ml_refit_24h over raw_forecast: -21.901144182057514 A (-9.807 %)
- ml_cooling_corrected over ml_wind_corrected: 7.965216015276711 A; favoured in 2 of 4 cities
- reference_ml_refit_24h over ml_wind_corrected: -51.33548673984278 A; favoured in 1 of 4 cities
- Caveat: Suwannee-150 and Suwannee-200 use the catalogue ACSS/TW resistance (0.0597 ohm/km at 25 C) in the repo's linear resistance model; that model's accuracy for ACSS/TW at 150-200 C is unverified (shadow_early_decision_options.md, 'Items I could not verify').

### Drake-75-AUSTIN-163m
- ml_wind_corrected over raw_forecast: -3.231713291759851 A (-2.362 %)
- ml_cooling_corrected over raw_forecast: 20.299506369961914 A (14.835 %)
- reference_ml_refit_24h over raw_forecast: -4.0356861244628055 A (-2.949 %)
- ml_cooling_corrected over ml_wind_corrected: 23.531219661721767 A; favoured in 1 of 1 cities
- reference_ml_refit_24h over ml_wind_corrected: -0.8039728327029542 A; favoured in 0 of 1 cities
- compared with the control restricted to AUSTIN (matched control)

## Caveats

- ABLATION is a relative-ordering finding on rows the configurations were selected on; it can veto a candidate and can never confirm one or name a winner (D-02).
- Suwannee-150 and Suwannee-200 use the catalogue ACSS/TW resistance (0.0597 ohm/km at 25 C) in the repo's linear resistance model; that model's accuracy for ACSS/TW at 150-200 C is unverified (shadow_early_decision_options.md, 'Items I could not verify').
