Exploratory, not pre-registered; does not change signed protocol v4 or read 1. **Post-hoc, descriptive only** (added after seeing the planned results).

## 1. 60-minute arms over every hour of the TEST window (production basis)

| city | n hours | ml60 MAE | naive60 MAE | ml60 MAE at the 4 slot hours only |
|---|---|---|---|---|
| AUSTIN | 4704 | 74.0 | 79.4 | 85.0 |
| CORPUS_CHRISTI | 4704 | 51.7 | 57.4 | 67.7 |
| MIDLAND | 4704 | 77.8 | 81.9 | 91.5 |
| EL_PASO | 4704 | 86.0 | 91.1 | 102.0 |

## 2. MAE by UTC slot hour, production basis, pooled over cities (n = 784 per hour)

| UTC hour (CDT = UTC−5) | ml60 | naive60 | cooling (24 h) | raw (24 h) | cooling − ml60 |
|---|---|---|---|---|---|
| 00 | 99.5 | 106.2 | 113.0 | 131.8 | +13.5 |
| 06 | 80.2 | 82.4 | 102.3 | 129.0 | +22.1 |
| 12 | 85.2 | 88.5 | 116.0 | 146.3 | +30.8 |
| 18 | 81.2 | 91.0 | 107.2 | 134.7 | +26.0 |
