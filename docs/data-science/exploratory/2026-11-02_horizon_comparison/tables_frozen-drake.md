Exploratory, not pre-registered; does not change signed protocol v4 or read 1.

## Basis: frozen-drake

### MAE per arm (amps; n = 784 per city, 3136 pooled)

| arm | AUSTIN | CORPUS_CHRISTI | MIDLAND | EL_PASO | POOLED |
|---|---|---|---|---|---|
| ml60 | 262.0 (22.2%) | 67.7 (5.1%) | 91.5 (6.0%) | 102.0 (8.9%) | 130.8 (10.1%) |
| naive60 | 78.6 (6.7%) | 72.6 (5.5%) | 100.3 (6.6%) | 105.4 (9.2%) | 89.3 (6.9%) |
| cooling | 91.3 (7.7%) | 85.8 (6.4%) | 119.9 (7.9%) | 126.3 (11.0%) | 105.8 (8.2%) |
| wind | 109.2 (9.3%) | 88.1 (6.6%) | 123.0 (8.1%) | 130.8 (11.4%) | 112.8 (8.7%) |
| reference | 101.7 (8.6%) | 101.3 (7.6%) | 178.2 (11.8%) | 141.4 (12.3%) | 130.7 (10.1%) |
| raw | 114.5 (9.7%) | 110.8 (8.3%) | 129.1 (8.5%) | 168.6 (14.7%) | 130.7 (10.1%) |
| persist24 | 121.4 (10.3%) | 118.4 (8.9%) | 205.7 (13.6%) | 171.9 (15.0%) | 154.3 (11.9%) |

(MAE as % of the city's mean truth ampacity in brackets.)

### Other descriptive metrics, pooled (amps)

| arm | n | bias | RMSE | p95 abs err | over-prediction rate |
|---|---|---|---|---|---|
| ml60 | 3136 | +72.5 | 178.6 | 362.9 | 0.636 |
| naive60 | 3136 | +2.2 | 132.7 | 287.0 | 0.513 |
| cooling | 3136 | +4.8 | 146.4 | 306.1 | 0.492 |
| wind | 3136 | -22.7 | 159.0 | 337.5 | 0.448 |
| reference | 3136 | +15.2 | 171.9 | 354.9 | 0.536 |
| raw | 3136 | +7.2 | 181.2 | 387.0 | 0.501 |
| persist24 | 3136 | +0.9 | 210.8 | 450.2 | 0.488 |

### Family A: paired differences (margin = MAE_B − MAE_A; > 0 means A is better)

| A vs B | scope | n | MAE A | MAE B | margin (A) | 95% CI | % of mean truth | p | Holm p |
|---|---|---|---|---|---|---|---|---|---|
| **cooling vs reference** | **pooled** | 3136 | 105.8 | 130.7 | **+24.8** | [10.7, 48.4] | +1.9% | 0.0002 | **0.0012** |
| cooling vs reference | AUSTIN | 784 | 91.3 | 101.7 | +10.4 | [4.3, 15.6] | +0.9% | 0.0018 | 0.0072 |
| cooling vs reference | CORPUS_CHRISTI | 784 | 85.8 | 101.3 | +15.6 | [9.4, 21.8] | +1.2% | 0.0002 | 0.0012 |
| cooling vs reference | MIDLAND | 784 | 119.9 | 178.2 | +58.3 | [46.8, 73.3] | +3.9% | 0.0002 | 0.0012 |
| cooling vs reference | EL_PASO | 784 | 126.3 | 141.4 | +15.1 | [9.7, 20.7] | +1.3% | 0.0002 | 0.0012 |
| **wind vs reference** | **pooled** | 3136 | 112.8 | 130.7 | **+17.9** | [-2.1, 44.6] | +1.4% | 0.0900 | **0.0900** |
| wind vs reference | AUSTIN | 784 | 109.2 | 101.7 | -7.5 | [-15.1, 0.3] | -0.6% | 0.0624 | 0.1248 |
| wind vs reference | CORPUS_CHRISTI | 784 | 88.1 | 101.3 | +13.3 | [6.0, 20.3] | +1.0% | 0.0004 | 0.0012 |
| wind vs reference | MIDLAND | 784 | 123.0 | 178.2 | +55.2 | [42.5, 72.8] | +3.7% | 0.0002 | 0.0012 |
| wind vs reference | EL_PASO | 784 | 130.8 | 141.4 | +10.6 | [2.2, 19.4] | +0.9% | 0.0122 | 0.0122 |
| **cooling vs raw** | **pooled** | 3136 | 105.8 | 130.7 | **+24.9** | [13.0, 37.1] | +1.9% | 0.0002 | **0.0012** |
| cooling vs raw | AUSTIN | 784 | 91.3 | 114.5 | +23.2 | [18.1, 29.5] | +2.0% | 0.0002 | 0.0012 |
| cooling vs raw | CORPUS_CHRISTI | 784 | 85.8 | 110.8 | +25.0 | [20.0, 30.0] | +1.9% | 0.0002 | 0.0012 |
| cooling vs raw | MIDLAND | 784 | 119.9 | 129.1 | +9.2 | [4.5, 13.4] | +0.6% | 0.0002 | 0.0012 |
| cooling vs raw | EL_PASO | 784 | 126.3 | 168.6 | +42.3 | [32.8, 50.7] | +3.7% | 0.0002 | 0.0012 |
| **wind vs raw** | **pooled** | 3136 | 112.8 | 130.7 | **+18.0** | [5.3, 32.3] | +1.4% | 0.0002 | **0.0012** |
| wind vs raw | AUSTIN | 784 | 109.2 | 114.5 | +5.2 | [-0.9, 13.7] | +0.4% | 0.0946 | 0.1248 |
| wind vs raw | CORPUS_CHRISTI | 784 | 88.1 | 110.8 | +22.7 | [18.2, 27.3] | +1.7% | 0.0002 | 0.0012 |
| wind vs raw | MIDLAND | 784 | 123.0 | 129.1 | +6.1 | [2.2, 9.9] | +0.4% | 0.0034 | 0.0034 |
| wind vs raw | EL_PASO | 784 | 130.8 | 168.6 | +37.8 | [26.1, 49.5] | +3.3% | 0.0002 | 0.0012 |
| **cooling vs persist24** | **pooled** | 3136 | 105.8 | 154.3 | **+48.5** | [30.1, 74.4] | +3.8% | 0.0002 | **0.0012** |
| cooling vs persist24 | AUSTIN | 784 | 91.3 | 121.4 | +30.1 | [22.5, 38.2] | +2.6% | 0.0002 | 0.0012 |
| cooling vs persist24 | CORPUS_CHRISTI | 784 | 85.8 | 118.4 | +32.6 | [22.8, 41.8] | +2.5% | 0.0002 | 0.0012 |
| cooling vs persist24 | MIDLAND | 784 | 119.9 | 205.7 | +85.7 | [68.7, 105.3] | +5.7% | 0.0002 | 0.0012 |
| cooling vs persist24 | EL_PASO | 784 | 126.3 | 171.9 | +45.6 | [37.5, 54.6] | +4.0% | 0.0002 | 0.0012 |
| **wind vs persist24** | **pooled** | 3136 | 112.8 | 154.3 | **+41.6** | [18.2, 71.0] | +3.2% | 0.0002 | **0.0012** |
| wind vs persist24 | AUSTIN | 784 | 109.2 | 121.4 | +12.2 | [3.7, 22.1] | +1.0% | 0.0056 | 0.0168 |
| wind vs persist24 | CORPUS_CHRISTI | 784 | 88.1 | 118.4 | +30.3 | [20.7, 39.0] | +2.3% | 0.0002 | 0.0012 |
| wind vs persist24 | MIDLAND | 784 | 123.0 | 205.7 | +82.7 | [64.7, 104.3] | +5.5% | 0.0002 | 0.0012 |
| wind vs persist24 | EL_PASO | 784 | 130.8 | 171.9 | +41.1 | [31.1, 53.9] | +3.6% | 0.0002 | 0.0012 |

Pooled CI = widest 95% over both schemes and block lengths 1/4/8/28; pooled p = max over the same (PD-04 style); Holm across the family's pooled tests. Per-city: 1-D moving-block bootstrap, CI widest and p max over L; 'Holm p' for a city row is Holm within (family × city), descriptive.

Pooled by scheme (city-clustered two-stage is the conservative one with 4 cities):

| A vs B | joint-time p max | joint-time 95% CI | city-cluster p max | city-cluster 95% CI |
|---|---|---|---|---|
| cooling vs reference | 0.0002 | [20.1, 30.3] | 0.0002 | [10.7, 48.4] |
| wind vs reference | 0.0002 | [12.3, 25.3] | 0.0900 | [-2.1, 44.6] |
| cooling vs raw | 0.0002 | [21.2, 28.7] | 0.0002 | [13.0, 37.1] |
| wind vs raw | 0.0002 | [14.4, 22.2] | 0.0002 | [5.3, 32.3] |
| cooling vs persist24 | 0.0002 | [40.5, 57.4] | 0.0002 | [30.1, 74.4] |
| wind vs persist24 | 0.0002 | [33.6, 51.5] | 0.0002 | [18.2, 71.0] |

### Family B: paired differences (margin = MAE_B − MAE_A; > 0 means A is better)

| A vs B | scope | n | MAE A | MAE B | margin (A) | 95% CI | % of mean truth | p | Holm p |
|---|---|---|---|---|---|---|---|---|---|
| **ml60 vs cooling** | **pooled** | 3136 | 130.8 | 105.8 | **-24.9** | [-122.8, 27.4] | -1.9% | 0.6279 | **1.0000** |
| ml60 vs cooling | AUSTIN | 784 | 262.0 | 91.3 | -170.7 | [-185.3, -154.2] | -14.5% | 0.0002 | 0.0014 |
| ml60 vs cooling | CORPUS_CHRISTI | 784 | 67.7 | 85.8 | +18.1 | [12.1, 24.0] | +1.4% | 0.0002 | 0.0014 |
| ml60 vs cooling | MIDLAND | 784 | 91.5 | 119.9 | +28.4 | [18.8, 36.4] | +1.9% | 0.0002 | 0.0014 |
| ml60 vs cooling | EL_PASO | 784 | 102.0 | 126.3 | +24.4 | [16.8, 31.6] | +2.1% | 0.0002 | 0.0014 |
| **ml60 vs wind** | **pooled** | 3136 | 130.8 | 112.8 | **-18.0** | [-109.2, 31.1] | -1.4% | 0.6279 | **1.0000** |
| ml60 vs wind | AUSTIN | 784 | 262.0 | 109.2 | -152.8 | [-169.6, -135.7] | -13.0% | 0.0002 | 0.0014 |
| ml60 vs wind | CORPUS_CHRISTI | 784 | 67.7 | 88.1 | +20.4 | [13.7, 27.6] | +1.5% | 0.0002 | 0.0014 |
| ml60 vs wind | MIDLAND | 784 | 91.5 | 123.0 | +31.5 | [21.3, 40.1] | +2.1% | 0.0002 | 0.0014 |
| ml60 vs wind | EL_PASO | 784 | 102.0 | 130.8 | +28.9 | [20.2, 37.0] | +2.5% | 0.0002 | 0.0014 |
| **ml60 vs reference** | **pooled** | 3136 | 130.8 | 130.7 | **-0.1** | [-110.5, 72.7] | -0.0% | 0.9815 | **1.0000** |
| ml60 vs reference | AUSTIN | 784 | 262.0 | 101.7 | -160.3 | [-175.7, -144.5] | -13.6% | 0.0002 | 0.0014 |
| ml60 vs reference | CORPUS_CHRISTI | 784 | 67.7 | 101.3 | +33.7 | [26.2, 40.8] | +2.5% | 0.0002 | 0.0014 |
| ml60 vs reference | MIDLAND | 784 | 91.5 | 178.2 | +86.7 | [71.9, 101.5] | +5.7% | 0.0002 | 0.0014 |
| ml60 vs reference | EL_PASO | 784 | 102.0 | 141.4 | +39.5 | [30.1, 48.2] | +3.4% | 0.0002 | 0.0014 |
| **ml60 vs raw** | **pooled** | 3136 | 130.8 | 130.7 | **-0.0** | [-99.9, 59.1] | -0.0% | 0.9929 | **1.0000** |
| ml60 vs raw | AUSTIN | 784 | 262.0 | 114.5 | -147.5 | [-162.5, -129.3] | -12.5% | 0.0002 | 0.0014 |
| ml60 vs raw | CORPUS_CHRISTI | 784 | 67.7 | 110.8 | +43.1 | [35.9, 50.3] | +3.2% | 0.0002 | 0.0014 |
| ml60 vs raw | MIDLAND | 784 | 91.5 | 129.1 | +37.6 | [26.2, 46.4] | +2.5% | 0.0002 | 0.0014 |
| ml60 vs raw | EL_PASO | 784 | 102.0 | 168.6 | +66.7 | [56.6, 76.6] | +5.8% | 0.0002 | 0.0014 |
| **ml60 vs persist24** | **pooled** | 3136 | 130.8 | 154.3 | **+23.6** | [-89.5, 98.0] | +1.8% | 0.5285 | **1.0000** |
| ml60 vs persist24 | AUSTIN | 784 | 262.0 | 121.4 | -140.6 | [-160.0, -119.2] | -11.9% | 0.0002 | 0.0014 |
| ml60 vs persist24 | CORPUS_CHRISTI | 784 | 67.7 | 118.4 | +50.7 | [39.4, 61.2] | +3.8% | 0.0002 | 0.0014 |
| ml60 vs persist24 | MIDLAND | 784 | 91.5 | 205.7 | +114.2 | [93.3, 134.1] | +7.6% | 0.0002 | 0.0014 |
| ml60 vs persist24 | EL_PASO | 784 | 102.0 | 171.9 | +70.0 | [59.0, 83.1] | +6.1% | 0.0002 | 0.0014 |
| **ml60 vs naive60** | **pooled** | 3136 | 130.8 | 89.3 | **-41.5** | [-136.5, 7.8] | -3.2% | 0.6279 | **1.0000** |
| ml60 vs naive60 | AUSTIN | 784 | 262.0 | 78.6 | -183.4 | [-196.6, -168.0] | -15.6% | 0.0002 | 0.0014 |
| ml60 vs naive60 | CORPUS_CHRISTI | 784 | 67.7 | 72.6 | +5.0 | [1.9, 8.4] | +0.4% | 0.0016 | 0.0016 |
| ml60 vs naive60 | MIDLAND | 784 | 91.5 | 100.3 | +8.8 | [5.0, 12.2] | +0.6% | 0.0002 | 0.0014 |
| ml60 vs naive60 | EL_PASO | 784 | 102.0 | 105.4 | +3.5 | [-0.6, 7.5] | +0.3% | 0.0982 | 0.0982 |
| **naive60 vs cooling** | **pooled** | 3136 | 89.3 | 105.8 | **+16.6** | [11.1, 22.0] | +1.3% | 0.0002 | **0.0014** |
| naive60 vs cooling | AUSTIN | 784 | 78.6 | 91.3 | +12.7 | [5.9, 19.3] | +1.1% | 0.0004 | 0.0014 |
| naive60 vs cooling | CORPUS_CHRISTI | 784 | 72.6 | 85.8 | +13.1 | [5.7, 20.1] | +1.0% | 0.0004 | 0.0014 |
| naive60 vs cooling | MIDLAND | 784 | 100.3 | 119.9 | +19.6 | [10.1, 28.5] | +1.3% | 0.0002 | 0.0014 |
| naive60 vs cooling | EL_PASO | 784 | 105.4 | 126.3 | +20.9 | [10.7, 30.7] | +1.8% | 0.0002 | 0.0014 |

Pooled CI = widest 95% over both schemes and block lengths 1/4/8/28; pooled p = max over the same (PD-04 style); Holm across the family's pooled tests. Per-city: 1-D moving-block bootstrap, CI widest and p max over L; 'Holm p' for a city row is Holm within (family × city), descriptive.

Pooled by scheme (city-clustered two-stage is the conservative one with 4 cities):

| A vs B | joint-time p max | joint-time 95% CI | city-cluster p max | city-cluster 95% CI |
|---|---|---|---|---|
| ml60 vs cooling | 0.0002 | [-29.9, -20.8] | 0.6279 | [-122.8, 27.4] |
| ml60 vs wind | 0.0002 | [-24.1, -13.7] | 0.6279 | [-109.2, 31.1] |
| ml60 vs reference | 0.9571 | [-8.5, 8.1] | 0.9815 | [-110.5, 72.7] |
| ml60 vs raw | 0.9667 | [-5.3, 4.5] | 0.9929 | [-99.9, 59.1] |
| ml60 vs persist24 | 0.0004 | [11.4, 35.6] | 0.5285 | [-89.5, 98.0] |
| ml60 vs naive60 | 0.0002 | [-45.8, -36.9] | 0.6279 | [-136.5, 7.8] |
| naive60 vs cooling | 0.0002 | [11.1, 20.9] | 0.0002 | [11.1, 22.0] |

### Family B_three_parity_cities: paired differences (margin = MAE_B − MAE_A; > 0 means A is better)

| A vs B | scope | n | MAE A | MAE B | margin (A) | 95% CI | % of mean truth | p | Holm p |
|---|---|---|---|---|---|---|---|---|---|
| **ml60 vs cooling** | **pooled** | 2352 | 87.0 | 110.7 | **+23.6** | [17.1, 29.9] | +1.8% | 0.0002 | **0.0014** |
| ml60 vs cooling | CORPUS_CHRISTI | 784 | 67.7 | 85.8 | +18.1 | [12.1, 24.0] | +1.4% | 0.0002 | 0.0014 |
| ml60 vs cooling | MIDLAND | 784 | 91.5 | 119.9 | +28.4 | [18.8, 36.4] | +1.9% | 0.0002 | 0.0014 |
| ml60 vs cooling | EL_PASO | 784 | 102.0 | 126.3 | +24.4 | [16.8, 31.6] | +2.1% | 0.0002 | 0.0014 |
| **ml60 vs wind** | **pooled** | 2352 | 87.0 | 114.0 | **+26.9** | [19.4, 33.8] | +2.0% | 0.0002 | **0.0014** |
| ml60 vs wind | CORPUS_CHRISTI | 784 | 67.7 | 88.1 | +20.4 | [13.7, 27.6] | +1.5% | 0.0002 | 0.0014 |
| ml60 vs wind | MIDLAND | 784 | 91.5 | 123.0 | +31.5 | [21.3, 40.1] | +2.1% | 0.0002 | 0.0014 |
| ml60 vs wind | EL_PASO | 784 | 102.0 | 130.8 | +28.9 | [20.2, 37.0] | +2.5% | 0.0002 | 0.0014 |
| **ml60 vs reference** | **pooled** | 2352 | 87.0 | 140.3 | **+53.3** | [31.9, 85.6] | +4.0% | 0.0002 | **0.0014** |
| ml60 vs reference | CORPUS_CHRISTI | 784 | 67.7 | 101.3 | +33.7 | [26.2, 40.8] | +2.5% | 0.0002 | 0.0014 |
| ml60 vs reference | MIDLAND | 784 | 91.5 | 178.2 | +86.7 | [71.9, 101.5] | +5.7% | 0.0002 | 0.0014 |
| ml60 vs reference | EL_PASO | 784 | 102.0 | 141.4 | +39.5 | [30.1, 48.2] | +3.4% | 0.0002 | 0.0014 |
| **ml60 vs raw** | **pooled** | 2352 | 87.0 | 136.2 | **+49.1** | [34.4, 65.7] | +3.7% | 0.0002 | **0.0014** |
| ml60 vs raw | CORPUS_CHRISTI | 784 | 67.7 | 110.8 | +43.1 | [35.9, 50.3] | +3.2% | 0.0002 | 0.0014 |
| ml60 vs raw | MIDLAND | 784 | 91.5 | 129.1 | +37.6 | [26.2, 46.4] | +2.5% | 0.0002 | 0.0014 |
| ml60 vs raw | EL_PASO | 784 | 102.0 | 168.6 | +66.7 | [56.6, 76.6] | +5.8% | 0.0002 | 0.0014 |
| **ml60 vs persist24** | **pooled** | 2352 | 87.0 | 165.3 | **+78.3** | [50.3, 112.9] | +5.9% | 0.0002 | **0.0014** |
| ml60 vs persist24 | CORPUS_CHRISTI | 784 | 67.7 | 118.4 | +50.7 | [39.4, 61.2] | +3.8% | 0.0002 | 0.0014 |
| ml60 vs persist24 | MIDLAND | 784 | 91.5 | 205.7 | +114.2 | [93.3, 134.1] | +7.6% | 0.0002 | 0.0014 |
| ml60 vs persist24 | EL_PASO | 784 | 102.0 | 171.9 | +70.0 | [59.0, 83.1] | +6.1% | 0.0002 | 0.0014 |
| **ml60 vs naive60** | **pooled** | 2352 | 87.0 | 92.8 | **+5.8** | [2.5, 9.2] | +0.4% | 0.0006 | **0.0014** |
| ml60 vs naive60 | CORPUS_CHRISTI | 784 | 67.7 | 72.6 | +5.0 | [1.9, 8.4] | +0.4% | 0.0016 | 0.0016 |
| ml60 vs naive60 | MIDLAND | 784 | 91.5 | 100.3 | +8.8 | [5.0, 12.2] | +0.6% | 0.0002 | 0.0014 |
| ml60 vs naive60 | EL_PASO | 784 | 102.0 | 105.4 | +3.5 | [-0.6, 7.5] | +0.3% | 0.0982 | 0.0982 |
| **naive60 vs cooling** | **pooled** | 2352 | 92.8 | 110.7 | **+17.9** | [11.2, 23.9] | +1.3% | 0.0002 | **0.0014** |
| naive60 vs cooling | CORPUS_CHRISTI | 784 | 72.6 | 85.8 | +13.1 | [5.7, 20.1] | +1.0% | 0.0004 | 0.0014 |
| naive60 vs cooling | MIDLAND | 784 | 100.3 | 119.9 | +19.6 | [10.1, 28.5] | +1.3% | 0.0002 | 0.0014 |
| naive60 vs cooling | EL_PASO | 784 | 105.4 | 126.3 | +20.9 | [10.7, 30.7] | +1.8% | 0.0002 | 0.0014 |

Pooled CI = widest 95% over both schemes and block lengths 1/4/8/28; pooled p = max over the same (PD-04 style); Holm across the family's pooled tests. Per-city: 1-D moving-block bootstrap, CI widest and p max over L; 'Holm p' for a city row is Holm within (family × city), descriptive.

Pooled by scheme (city-clustered two-stage is the conservative one with 4 cities):

| A vs B | joint-time p max | joint-time 95% CI | city-cluster p max | city-cluster 95% CI |
|---|---|---|---|---|
| ml60 vs cooling | 0.0002 | [18.5, 27.7] | 0.0002 | [17.1, 29.9] |
| ml60 vs wind | 0.0002 | [21.5, 31.3] | 0.0002 | [19.4, 33.8] |
| ml60 vs reference | 0.0002 | [44.9, 61.3] | 0.0002 | [31.9, 85.6] |
| ml60 vs raw | 0.0002 | [43.6, 54.1] | 0.0002 | [34.4, 65.7] |
| ml60 vs persist24 | 0.0002 | [67.1, 89.0] | 0.0002 | [50.3, 112.9] |
| ml60 vs naive60 | 0.0002 | [3.3, 8.2] | 0.0006 | [2.5, 9.2] |
| naive60 vs cooling | 0.0002 | [11.5, 22.7] | 0.0002 | [11.2, 23.9] |
