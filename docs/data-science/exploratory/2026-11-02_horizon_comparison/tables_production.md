Exploratory, not pre-registered; does not change signed protocol v4 or read 1.

## Basis: production

### MAE per arm (amps; n = 784 per city, 3136 pooled)

| arm | AUSTIN | CORPUS_CHRISTI | MIDLAND | EL_PASO | POOLED |
|---|---|---|---|---|---|
| ml60 | 85.0 (5.9%) | 67.7 (5.1%) | 91.5 (6.0%) | 102.0 (8.9%) | 86.5 (6.4%) |
| naive60 | 89.8 (6.3%) | 72.6 (5.5%) | 100.3 (6.6%) | 105.4 (9.2%) | 92.0 (6.8%) |
| cooling | 106.5 (7.4%) | 85.8 (6.4%) | 119.9 (7.9%) | 126.3 (11.0%) | 109.6 (8.1%) |
| wind | 126.1 (8.8%) | 88.1 (6.6%) | 123.0 (8.1%) | 130.8 (11.4%) | 117.0 (8.6%) |
| reference | 122.6 (8.6%) | 101.3 (7.6%) | 178.2 (11.8%) | 141.4 (12.3%) | 135.9 (10.0%) |
| raw | 133.3 (9.3%) | 110.8 (8.3%) | 129.1 (8.5%) | 168.6 (14.7%) | 135.5 (10.0%) |
| persist24 | 139.6 (9.7%) | 118.4 (8.9%) | 205.7 (13.6%) | 171.9 (15.0%) | 158.9 (11.7%) |

(MAE as % of the city's mean truth ampacity in brackets.)

### Other descriptive metrics, pooled (amps)

| arm | n | bias | RMSE | p95 abs err | over-prediction rate |
|---|---|---|---|---|---|
| ml60 | 3136 | +9.0 | 125.6 | 260.5 | 0.521 |
| naive60 | 3136 | +2.3 | 136.6 | 296.6 | 0.516 |
| cooling | 3136 | +4.5 | 151.1 | 315.5 | 0.496 |
| wind | 3136 | -24.3 | 164.9 | 353.7 | 0.448 |
| reference | 3136 | +16.5 | 177.2 | 365.9 | 0.536 |
| raw | 3136 | +7.7 | 187.2 | 396.7 | 0.501 |
| persist24 | 3136 | +0.8 | 216.1 | 463.4 | 0.484 |

### Family A: paired differences (margin = MAE_B − MAE_A; > 0 means A is better)

| A vs B | scope | n | MAE A | MAE B | margin (A) | 95% CI | % of mean truth | p | Holm p |
|---|---|---|---|---|---|---|---|---|---|
| **cooling vs reference** | **pooled** | 3136 | 109.6 | 135.9 | **+26.3** | [13.1, 49.0] | +1.9% | 0.0002 | **0.0012** |
| cooling vs reference | AUSTIN | 784 | 106.5 | 122.6 | +16.2 | [8.2, 22.5] | +1.1% | 0.0002 | 0.0012 |
| cooling vs reference | CORPUS_CHRISTI | 784 | 85.8 | 101.3 | +15.6 | [9.4, 21.8] | +1.2% | 0.0002 | 0.0012 |
| cooling vs reference | MIDLAND | 784 | 119.9 | 178.2 | +58.3 | [46.8, 73.3] | +3.9% | 0.0002 | 0.0012 |
| cooling vs reference | EL_PASO | 784 | 126.3 | 141.4 | +15.1 | [9.7, 20.7] | +1.3% | 0.0002 | 0.0012 |
| **wind vs reference** | **pooled** | 3136 | 117.0 | 135.9 | **+18.9** | [0.5, 44.8] | +1.4% | 0.0410 | **0.0410** |
| wind vs reference | AUSTIN | 784 | 126.1 | 122.6 | -3.5 | [-13.3, 6.8] | -0.2% | 0.5063 | 0.5063 |
| wind vs reference | CORPUS_CHRISTI | 784 | 88.1 | 101.3 | +13.3 | [6.0, 20.3] | +1.0% | 0.0004 | 0.0012 |
| wind vs reference | MIDLAND | 784 | 123.0 | 178.2 | +55.2 | [42.5, 72.8] | +3.7% | 0.0002 | 0.0012 |
| wind vs reference | EL_PASO | 784 | 130.8 | 141.4 | +10.6 | [2.2, 19.4] | +0.9% | 0.0122 | 0.0122 |
| **cooling vs raw** | **pooled** | 3136 | 109.6 | 135.5 | **+25.8** | [13.7, 37.8] | +1.9% | 0.0002 | **0.0012** |
| cooling vs raw | AUSTIN | 784 | 106.5 | 133.3 | +26.9 | [20.9, 34.8] | +1.9% | 0.0002 | 0.0012 |
| cooling vs raw | CORPUS_CHRISTI | 784 | 85.8 | 110.8 | +25.0 | [20.0, 30.0] | +1.9% | 0.0002 | 0.0012 |
| cooling vs raw | MIDLAND | 784 | 119.9 | 129.1 | +9.2 | [4.5, 13.4] | +0.6% | 0.0002 | 0.0012 |
| cooling vs raw | EL_PASO | 784 | 126.3 | 168.6 | +42.3 | [32.8, 50.7] | +3.7% | 0.0002 | 0.0012 |
| **wind vs raw** | **pooled** | 3136 | 117.0 | 135.5 | **+18.5** | [6.2, 32.4] | +1.4% | 0.0002 | **0.0012** |
| wind vs raw | AUSTIN | 784 | 126.1 | 133.3 | +7.2 | [0.1, 17.1] | +0.5% | 0.0462 | 0.0924 |
| wind vs raw | CORPUS_CHRISTI | 784 | 88.1 | 110.8 | +22.7 | [18.2, 27.3] | +1.7% | 0.0002 | 0.0012 |
| wind vs raw | MIDLAND | 784 | 123.0 | 129.1 | +6.1 | [2.2, 9.9] | +0.4% | 0.0034 | 0.0034 |
| wind vs raw | EL_PASO | 784 | 130.8 | 168.6 | +37.8 | [26.1, 49.5] | +3.3% | 0.0002 | 0.0012 |
| **cooling vs persist24** | **pooled** | 3136 | 109.6 | 158.9 | **+49.3** | [31.6, 74.8] | +3.6% | 0.0002 | **0.0012** |
| cooling vs persist24 | AUSTIN | 784 | 106.5 | 139.6 | +33.2 | [24.9, 42.1] | +2.3% | 0.0002 | 0.0012 |
| cooling vs persist24 | CORPUS_CHRISTI | 784 | 85.8 | 118.4 | +32.6 | [22.8, 41.8] | +2.5% | 0.0002 | 0.0012 |
| cooling vs persist24 | MIDLAND | 784 | 119.9 | 205.7 | +85.7 | [68.7, 105.3] | +5.7% | 0.0002 | 0.0012 |
| cooling vs persist24 | EL_PASO | 784 | 126.3 | 171.9 | +45.6 | [37.5, 54.6] | +4.0% | 0.0002 | 0.0012 |
| **wind vs persist24** | **pooled** | 3136 | 117.0 | 158.9 | **+41.9** | [19.1, 71.0] | +3.1% | 0.0002 | **0.0012** |
| wind vs persist24 | AUSTIN | 784 | 126.1 | 139.6 | +13.5 | [3.8, 24.3] | +0.9% | 0.0068 | 0.0204 |
| wind vs persist24 | CORPUS_CHRISTI | 784 | 88.1 | 118.4 | +30.3 | [20.7, 39.0] | +2.3% | 0.0002 | 0.0012 |
| wind vs persist24 | MIDLAND | 784 | 123.0 | 205.7 | +82.7 | [64.7, 104.3] | +5.5% | 0.0002 | 0.0012 |
| wind vs persist24 | EL_PASO | 784 | 130.8 | 171.9 | +41.1 | [31.1, 53.9] | +3.6% | 0.0002 | 0.0012 |

Pooled CI = widest 95% over both schemes and block lengths 1/4/8/28; pooled p = max over the same (PD-04 style); Holm across the family's pooled tests. Per-city: 1-D moving-block bootstrap, CI widest and p max over L; 'Holm p' for a city row is Holm within (family × city), descriptive.

Pooled by scheme (city-clustered two-stage is the conservative one with 4 cities):

| A vs B | joint-time p max | joint-time 95% CI | city-cluster p max | city-cluster 95% CI |
|---|---|---|---|---|
| cooling vs reference | 0.0002 | [21.5, 31.8] | 0.0002 | [13.1, 49.0] |
| wind vs reference | 0.0002 | [13.2, 26.4] | 0.0410 | [0.5, 44.8] |
| cooling vs raw | 0.0002 | [22.1, 29.9] | 0.0002 | [13.7, 37.8] |
| wind vs raw | 0.0002 | [14.8, 22.9] | 0.0002 | [6.2, 32.4] |
| cooling vs persist24 | 0.0002 | [41.1, 58.3] | 0.0002 | [31.6, 74.8] |
| wind vs persist24 | 0.0002 | [33.8, 52.0] | 0.0002 | [19.1, 71.0] |

### Family B: paired differences (margin = MAE_B − MAE_A; > 0 means A is better)

| A vs B | scope | n | MAE A | MAE B | margin (A) | 95% CI | % of mean truth | p | Holm p |
|---|---|---|---|---|---|---|---|---|---|
| **ml60 vs cooling** | **pooled** | 3136 | 86.5 | 109.6 | **+23.1** | [18.0, 28.3] | +1.7% | 0.0002 | **0.0014** |
| ml60 vs cooling | AUSTIN | 784 | 85.0 | 106.5 | +21.5 | [15.3, 27.6] | +1.5% | 0.0002 | 0.0014 |
| ml60 vs cooling | CORPUS_CHRISTI | 784 | 67.7 | 85.8 | +18.1 | [12.1, 24.0] | +1.4% | 0.0002 | 0.0014 |
| ml60 vs cooling | MIDLAND | 784 | 91.5 | 119.9 | +28.4 | [18.8, 36.4] | +1.9% | 0.0002 | 0.0014 |
| ml60 vs cooling | EL_PASO | 784 | 102.0 | 126.3 | +24.4 | [16.8, 31.6] | +2.1% | 0.0002 | 0.0014 |
| **ml60 vs wind** | **pooled** | 3136 | 86.5 | 117.0 | **+30.5** | [21.8, 38.8] | +2.2% | 0.0002 | **0.0014** |
| ml60 vs wind | AUSTIN | 784 | 85.0 | 126.1 | +41.1 | [31.5, 49.3] | +2.9% | 0.0002 | 0.0014 |
| ml60 vs wind | CORPUS_CHRISTI | 784 | 67.7 | 88.1 | +20.4 | [13.7, 27.6] | +1.5% | 0.0002 | 0.0014 |
| ml60 vs wind | MIDLAND | 784 | 91.5 | 123.0 | +31.5 | [21.3, 40.1] | +2.1% | 0.0002 | 0.0014 |
| ml60 vs wind | EL_PASO | 784 | 102.0 | 130.8 | +28.9 | [20.2, 37.0] | +2.5% | 0.0002 | 0.0014 |
| **ml60 vs reference** | **pooled** | 3136 | 86.5 | 135.9 | **+49.4** | [33.2, 74.6] | +3.6% | 0.0002 | **0.0014** |
| ml60 vs reference | AUSTIN | 784 | 85.0 | 122.6 | +37.6 | [29.5, 44.7] | +2.6% | 0.0002 | 0.0014 |
| ml60 vs reference | CORPUS_CHRISTI | 784 | 67.7 | 101.3 | +33.7 | [26.2, 40.8] | +2.5% | 0.0002 | 0.0014 |
| ml60 vs reference | MIDLAND | 784 | 91.5 | 178.2 | +86.7 | [71.9, 101.5] | +5.7% | 0.0002 | 0.0014 |
| ml60 vs reference | EL_PASO | 784 | 102.0 | 141.4 | +39.5 | [30.1, 48.2] | +3.4% | 0.0002 | 0.0014 |
| **ml60 vs raw** | **pooled** | 3136 | 86.5 | 135.5 | **+48.9** | [37.2, 61.2] | +3.6% | 0.0002 | **0.0014** |
| ml60 vs raw | AUSTIN | 784 | 85.0 | 133.3 | +48.3 | [40.1, 58.5] | +3.4% | 0.0002 | 0.0014 |
| ml60 vs raw | CORPUS_CHRISTI | 784 | 67.7 | 110.8 | +43.1 | [35.9, 50.3] | +3.2% | 0.0002 | 0.0014 |
| ml60 vs raw | MIDLAND | 784 | 91.5 | 129.1 | +37.6 | [26.2, 46.4] | +2.5% | 0.0002 | 0.0014 |
| ml60 vs raw | EL_PASO | 784 | 102.0 | 168.6 | +66.7 | [56.6, 76.6] | +5.8% | 0.0002 | 0.0014 |
| **ml60 vs persist24** | **pooled** | 3136 | 86.5 | 158.9 | **+72.4** | [50.7, 100.6] | +5.3% | 0.0002 | **0.0014** |
| ml60 vs persist24 | AUSTIN | 784 | 85.0 | 139.6 | +54.7 | [43.0, 67.1] | +3.8% | 0.0002 | 0.0014 |
| ml60 vs persist24 | CORPUS_CHRISTI | 784 | 67.7 | 118.4 | +50.7 | [39.4, 61.2] | +3.8% | 0.0002 | 0.0014 |
| ml60 vs persist24 | MIDLAND | 784 | 91.5 | 205.7 | +114.2 | [93.3, 134.1] | +7.6% | 0.0002 | 0.0014 |
| ml60 vs persist24 | EL_PASO | 784 | 102.0 | 171.9 | +70.0 | [59.0, 83.1] | +6.1% | 0.0002 | 0.0014 |
| **ml60 vs naive60** | **pooled** | 3136 | 86.5 | 92.0 | **+5.5** | [2.9, 8.2] | +0.4% | 0.0002 | **0.0014** |
| ml60 vs naive60 | AUSTIN | 784 | 85.0 | 89.8 | +4.8 | [1.3, 8.3] | +0.3% | 0.0064 | 0.0064 |
| ml60 vs naive60 | CORPUS_CHRISTI | 784 | 67.7 | 72.6 | +5.0 | [1.9, 8.4] | +0.4% | 0.0016 | 0.0016 |
| ml60 vs naive60 | MIDLAND | 784 | 91.5 | 100.3 | +8.8 | [5.0, 12.2] | +0.6% | 0.0002 | 0.0014 |
| ml60 vs naive60 | EL_PASO | 784 | 102.0 | 105.4 | +3.5 | [-0.6, 7.5] | +0.3% | 0.0982 | 0.0982 |
| **naive60 vs cooling** | **pooled** | 3136 | 92.0 | 109.6 | **+17.6** | [11.9, 22.5] | +1.3% | 0.0002 | **0.0014** |
| naive60 vs cooling | AUSTIN | 784 | 89.8 | 106.5 | +16.7 | [9.0, 24.2] | +1.2% | 0.0002 | 0.0014 |
| naive60 vs cooling | CORPUS_CHRISTI | 784 | 72.6 | 85.8 | +13.1 | [5.7, 20.1] | +1.0% | 0.0004 | 0.0014 |
| naive60 vs cooling | MIDLAND | 784 | 100.3 | 119.9 | +19.6 | [10.1, 28.5] | +1.3% | 0.0002 | 0.0014 |
| naive60 vs cooling | EL_PASO | 784 | 105.4 | 126.3 | +20.9 | [10.7, 30.7] | +1.8% | 0.0002 | 0.0014 |

Pooled CI = widest 95% over both schemes and block lengths 1/4/8/28; pooled p = max over the same (PD-04 style); Holm across the family's pooled tests. Per-city: 1-D moving-block bootstrap, CI widest and p max over L; 'Holm p' for a city row is Holm within (family × city), descriptive.

Pooled by scheme (city-clustered two-stage is the conservative one with 4 cities):

| A vs B | joint-time p max | joint-time 95% CI | city-cluster p max | city-cluster 95% CI |
|---|---|---|---|---|
| ml60 vs cooling | 0.0002 | [18.7, 26.5] | 0.0002 | [18.0, 28.3] |
| ml60 vs wind | 0.0002 | [25.3, 34.3] | 0.0002 | [21.8, 38.8] |
| ml60 vs reference | 0.0002 | [42.0, 56.3] | 0.0002 | [33.2, 74.6] |
| ml60 vs raw | 0.0002 | [44.2, 53.2] | 0.0002 | [37.2, 61.2] |
| ml60 vs persist24 | 0.0002 | [61.8, 82.7] | 0.0002 | [50.7, 100.6] |
| ml60 vs naive60 | 0.0002 | [3.3, 7.7] | 0.0002 | [2.9, 8.2] |
| naive60 vs cooling | 0.0002 | [11.9, 22.0] | 0.0002 | [12.2, 22.5] |
