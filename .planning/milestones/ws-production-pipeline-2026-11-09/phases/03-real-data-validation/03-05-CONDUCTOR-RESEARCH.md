# Austin-area 345 kV conductor / MOT research (for the DLR model's Austin city point)

Date: 2026-10-21. Web research only. No repository files edited.
Confidence labels: **confirmed** (a primary source says it directly), **likely** (strong inference from primary sources), **unverified**.

## Summary
- **The "954 kcmil Rail" claim is probably a mix-up with 959.6 kcmil ACSS/TW "Suwannee".** LCRA TSC's Clear Springs–Hutto 345 kV line runs through Hays, Travis and Williamson counties. It is listed as **3x2-959.6 ACSS/TW "Suwannee"**: 3 phases, 2 subconductors per phase. Suwannee has about the same diameter as Drake (1.110 in vs 1.108 in) but is ACSS, rated for continuous operation up to 250 °C. I found no Austin-area 345 kV line listed as 954 Rail.
- **"1590 Falcon" is confirmed on at least one LCRA 345 kV line.** The Fayette Power Project 345 kV bus tie is listed as **3x2-1590 kcmil ACSR "Falcon"**. Separately, Oncor rates existing 1590 ACSR at **90 °C** MOT, and an approved project raises it to 150 °C.
- **Drake at 75 °C is the wrong baseline for Austin.** In 2005, Austin Energy said it rated its 345 kV lines (795 ACSR Drake, Lapwing, Condor) at **100 °C**, with 40 °C ambient, 2 ft/s wind and ε = α = 0.5.
- **The 5000 A upper bound is ERCOT's current new-build 345 kV standard.** That is 2,987–2,988 MVA, built with bundled **2×1926.9 kcmil ACSS/TW "Cumberland"**, with 5000 A terminal equipment. It is not a rating of an existing older Austin line. Austin Energy's own Dunlap–Decker project (26RPG022) says Phase II will carry "two 5000 Amps transmission lines operating at 345 kV".
- **The owner's numbers look like an envelope, not a real line rating.** The 3650 A "static" value is exactly (2300 + 5000) / 2, the midpoint of the range.
- **The 900 m elevation is wrong.** Downtown Austin is about **163 m** (USGS 3DEP). This error alone lowers the computed rating by only about 2–3%.

---

## Q1. Who owns or operates 345 kV around Austin, and which lines and substations

| Owner | Facilities found | Source | Confidence |
|---|---|---|---|
| **LCRA Transmission Services Corp (LCRA TSC)** | **Clear Springs–Hutto 345 kV**: 55.11 mi through Guadalupe, Caldwell, Hays, Travis and Williamson counties. **FPP–Lytton Springs 345 kV (T255)**: 61.12 mi, Bastrop/Caldwell/Fayette. **Fayette Power Project 345 kV bus tie**. **Gilleland Creek** (Pflugerville): its 345 kV switchyard is LCRA TSC's and its 138 kV section connects to Austin Energy. Also Hays Energy–Bergheim–Kendall 345 kV and Zorn–Marion 345 kV. | LCRA TSC Monthly Construction Progress Reports filed at the PUCT: [47927 item 61](https://interchange.puc.texas.gov/Documents/47927_61_970780.PDF), [49066 item 105](https://interchange.puc.texas.gov/Documents/49066_105_1014680.PDF), [49066 item 132](https://interchange.puc.texas.gov/Documents/49066_132_1018233.PDF). Gilleland Creek: PUCT doc [35077_756](https://interchange.puc.texas.gov/Documents/35077_756_952878.PDF), as summarized by search; I did not open it. Hays–Kendall: [ERCOT EIR scope 2022](https://www.ercot.com/files/docs/2022/05/12/EIR-LCRA_TSC_Hays_Energy%E2%80%93Kendall_Corridor_Transmission_Line_Rehabilitation_Projects_Scope.pdf) | confirmed (Gilleland: likely) |
| **Austin Energy (AEN)** | Has 345 kV lines. Austin Energy said in 2005 they were "795 ACSR /Drake, Lapwing, and Condor". The Dunlap–Decker one-line shows the Austrop, Decker, Dunlap, Sand Hill and Lost Pines buses. ERCOT's 2024 RTP lists "Austrop 345/138-kV Transformer Addition (Travis)", "Dunlap 345/138-kV Transformer Addition (Travis)", and "**Lytton Springs (9074) to Garfield (7048) to Austrop (7040) 345-kV Line Upgrades** (Caldwell, Bastrop, Travis)". | [ERCOT ROS 2005 SPWG comments](https://www.ercot.com/files/docs/2005/02/08/ros02102005_7.doc); [26RPG022 overview](https://www.ercot.com/files/docs/2026/07/17/16.-26RPG022-AEN-Dunlap-to-Decker-138-kV-Line-Project-Overview.pdf); RTP list reproduced in [ERCOT Muscovy/Voss Lake EIR status, Apr 2026](https://www.ercot.com/files/docs/2026/04/10/5_EIR-Oncor-and-LCRA-TSC-Muscovy-Voss-_StatusUpdate_April2026_RPG.pdf) | confirmed |
| **Oncor** | Hutto Switch, Round Rock Switch, Salado 345 kV (Williamson/Bell, north of Austin). Co-sponsor with LCRA TSC of the Muscovy/Voss Lake 345 kV project (Phase 2 covers Bastrop, Travis, Caldwell and Hays counties). | [Oncor/LCRA Salado–Hutto RPG (PUCT 55999_63)](https://interchange.puc.texas.gov/Documents/55999_63_1424982.PDF); [ERCOT 25RPG009 Board item](https://www.ercot.com/files/docs/2026/05/22/5.3-25RPG009-Oncor-and-LCRA-TSC-Muscovy-and-Voss-Lake-345_138-kV-Regional-Planning-Group-RPG-Project.pdf) | confirmed |
| AEP Texas, CenterPoint | No Austin-area 345 kV ownership found. | none found | unverified (I found nothing) |

I could not determine which specific line the owner's "near Austin, TX" point stands for. The best candidates are the AEN Austrop–Garfield–Lytton Springs path, the AEN Sand Hill/Decker lines, and the LCRA Clear Springs–Hutto line.

## Q2. Conductors and bundles on Austin-area 345 kV

LCRA TSC construction reports use the format "3x2-<kcmil> <type>", meaning 3 phases × 2 subconductors per phase. All three of the first rows below are 2-conductor bundles, which matches the owner's statement.

| Line | Conductor as filed | Source quote | Confidence |
|---|---|---|---|
| Clear Springs–Hutto 345 kV (passes through Travis) | **2 × 959.6 kcmil ACSS/TW "Suwannee"** | "Clear Springs-Hutto Bolt Tightening … Guadalupe, Caldwell, Hays, Travis, Williamson … 345 345 55.11 … 3x2-959.6 ACSS/TW … 'Suwannee'" ([47927_61](https://interchange.puc.texas.gov/Documents/47927_61_970780.PDF), OCR text) | confirmed (OCR is noisy but clear) |
| Fayette Power Project 345 kV bus tie (Docket 47218) | **2 × 1590 kcmil ACSR "Falcon"** | "Fayette Power Project 345kV BUS Tie (CCN - Docket No 47218) … 3x2- 1590 Kcmil ASCR Falcon" ([47927_61](https://interchange.puc.texas.gov/Documents/47927_61_970780.PDF); [49066_105](https://interchange.puc.texas.gov/Documents/49066_105_1014680.PDF)) | confirmed |
| Fayetteville–Salem 138/345 kV | 2 × 795 ACSR "Condor" & "Drake" | "Fayetteville - Salem TL Storm Hardening … 138/345 … 3x2-795 ACSR 'Condor'" ([49066_105](https://interchange.puc.texas.gov/Documents/49066_105_1014680.PDF)) | confirmed |
| Zorn–Marion 345 kV (Guadalupe, south of Austin) | 2 × 959.6 ACSS/TW | "Zorn-Marion 345kV TL Addition (CCN - Docket No 45601) … 3x2-959.6 … ACSS/TW Steel Poles" ([49066_105](https://interchange.puc.texas.gov/Documents/49066_105_1014680.PDF)) | confirmed |
| FPP–Lytton Springs 345 kV (T255) | ACSR, size not legible in the filing | "FPP - Lytton Springs Storm Hardening (T255) … 345 345 61.12 mi ACSR Steel Lattice" ([49066_132](https://interchange.puc.texas.gov/Documents/49066_132_1018233.PDF)) | confirmed ACSR; size unverified |
| Austin Energy 345 kV system (as of 2005) | 795 ACSR Drake, Lapwing, Condor | "conductors used in our 345 kV lines- 795 ACSR /Drake, Lapwing, and Condor" ([ERCOT 2005](https://www.ercot.com/files/docs/2005/02/08/ros02102005_7.doc)) | confirmed for 2005; may have changed since |
| ERCOT new-build 345 kV (2025–26) | **2 × 1926.9 kcmil ACSS/TW "Cumberland"** | LCRA TSC/CEHE Euclid (26RPG001): "using bundled 1926 ACSS/TW Cumberland conductor (2,988 MVA normal and emergency rating)" ([PUCT 55999_264](https://interchange.puc.texas.gov/Documents/55999_264_1673801.PDF)). Oncor CCN: "1926.9 kcmil … ACSS/TW … Number of conductors per phase: 2 … Continuous Summer Static Current Rating (A): 5,138 A … 3,070 MVA" ([PUCT 56597_3](https://interchange.puc.texas.gov/Documents/56597_3_1395564.PDF)) | confirmed |

**Verdict on the owner's claims:**
- **"954 kcmil Rail" is refuted or unverified for 345 kV.** I found no Austin-area 345 kV line listed as Rail. The 954-class conductor LCRA actually uses is **959.6 ACSS/TW Suwannee**, a high-temperature trapezoidal-wire conductor. Southwire lists its OD as 1110 mils and says it is "designed to operate continuously at elevated temperatures up to 250°C" ([Southwire ACSS/TW Suwannee](https://www.southwire.com/wire-cable/bare-aluminum-overhead-transmission-distribution/acss-tw/p/61203957)). The owner may have confused "959.6" with "954".
- **"1590 kcmil Falcon" is confirmed as ACSR** on at least the FPP 345 kV bus tie.

**Reconductoring or uprating with ACSS / high temperature:**
- LCRA has many "replacing the aging conductor" projects using Suwannee or Merrimack ACSS/TW/HS ([PUCT 57477_142](https://interchange.puc.texas.gov/Documents/57477_142_1499099.PDF)). Those rows are mostly 138 kV.
- Oncor and LCRA's Salado–Hutto project will "increase the maximum operating temperature of the existing 1590 kcmil ACSR conductor from 90°C to 150°C rated at 2064 A (493 MVA)". That is a 138 kV circuit in Williamson County ([PUCT 55999_63](https://interchange.puc.texas.gov/Documents/55999_63_1424982.PDF)).
- ERCOT's 2024 RTP lists "Lytton Springs–Garfield–Austrop 345-kV Line Upgrades". I could not find their conductor or temperature (**unverified**).

## Q3. Maximum operating temperature and static-rating weather assumptions

- **Austin Energy (2005): confirmed.**
  - Conductor temperature: "Assuming conductor temperature of 100 degrees C for the conductors used in our 345 kV lines".
  - Weather: "Air temperature: 40 degree C", "Wind Speed: 2ft/sec", "Angle between wind and conductor: 90 degrees", "Coefficient of emissivity: 0.5", "Coefficient of Absorptivity: 0.5", east-west line, clear atmosphere. The emergency rating is computed with IEEE 738-1993.
  - Normal rating: "we use 90% of the emergency ratings".
  - Terminal equipment: ratings "can still be limited if there are any line terminal equipment" (for example wavetraps).
  - Source: [ERCOT ROS 2005-02-08, SPWG comments on OGRR 154](https://www.ercot.com/files/docs/2005/02/08/ros02102005_7.doc). This is 21 years old; current practice is **unverified**.
- **LCRA TSC (2003): confirmed for 2003.** "LCRA utilizes identical Normal, Emergency, and Load Shed ratings based on electrical safety clearances". Its "design criteria dynamic ratings will, at ambient temperatures greater than forty (40) degrees Celsius, de-rate transmission lines" ([ERCOT OGRR134 LCRA comments](https://www.ercot.com/files/docs/2003/05/07/134ogrr_lcra_comments_050203.doc)). This implies a 40 °C design ambient. No MOT is stated.
- **Oncor / LCRA, 1590 ACSR: confirmed.** Existing MOT is **90 °C**, being raised to 150 °C ([PUCT 55999_63](https://interchange.puc.texas.gov/Documents/55999_63_1424982.PDF)).
- **TXU/Oncor (2005): confirmed for 2005.** Dynamic ratings capped at 125% of static. The static basis corresponds to a 104 °F (40 °C) design ambient. Relay check at 120 °C conductor / 25 °C ambient (same 2005 ERCOT document).
- **ACSS:**
  - Manufacturer limit is 250 °C (Southwire).
  - Typical utility MOT is 200 °C. I found **no Austin-specific filing** stating the MOT used for Suwannee or Cumberland (**unverified**).
  - My back-calculation is consistent with roughly 200 °C. Oncor's 5,138 A for 2×1926.9 ACSS/TW is 2,569 A per subconductor, which my IEEE 738 estimate reaches near 180–200 °C at 40 °C ambient.
- **ERCOT rating definitions: confirmed.**
  - Normal = continuous; Emergency = two-hour; 15-minute rating from a 90% preload. All are "at the applicable ambient temperature".
  - TSPs must "send the methodology used to determine both Static and Dynamic Ratings to ERCOT annually" ([NOGRR 052](https://www.ercot.com/files/docs/2010/09/09/052nogrr_01_conductor_transformer_transmisson_facility_ratin.doc)).
  - The TSPs' current methodology documents are **not public**; I could not find them.
- **Generic basis: confirmed.** EPRI cites 40 °C, 2 ft/s, 96 W/ft² sun, ε = α = 0.5 as common worst-case example values ([EPRI 3002023333](https://restservice.epri.com/publicdownload/000000003002023333/0/Product), from the search summary).

## Q4. Published ampacities

**Southwire ACSR spec 80100 (confirmed, downloaded):** "+Conductor temperature of 75°C, ambient temperature 25°C, emissivity 0.5, wind 2 ft./sec., in sun." ([Southwire spec 80100](https://cabletechsupport.southwire.com/en/cablespec/download_spec/?spec=80100))

| Conductor | OD (in) | Rac 75 °C (Ω/kft) | Southwire ampacity @75 °C |
|---|---|---|---|
| Drake 795 26/7 | 1.107 | 0.0263 | **907 A** |
| Rail 954 45/7 | 1.165 | 0.0225 | **993 A** |
| Falcon 1590 54/19 | 1.544 | 0.0140 | **1359 A** |

Priority Wire's ACSR sheet gives the same numbers (Drake 907 A, Falcon 1,359 A) on the same basis ([prioritywire.com/specs/acsr.pdf](https://www.prioritywire.com/specs/acsr.pdf)).

No manufacturer table I found gives 100 °C values. The table below comes from my own IEEE 738-2006 steady-state calculation. It reproduces Southwire's 75 °C numbers within 0.4% (910 / 997 / 1362 A), which validates it. The solar input is a simplified about 1000 W/m², and the ACSS resistances are estimates. Treat these as **estimates**.

| Conductor | Basis A: Southwire (25 °C, 0.61 m/s, ε = α = 0.5, sea level) | Basis B: Austin Energy 2005 (40 °C, 0.61 m/s, ε = α = 0.5, 163 m) | Basis C: current model (40 °C, 0.61 m/s, ε = α = 0.8, 900 m) |
|---|---|---|---|
| Drake 75 / 100 / 125 °C | 910 / 1124 / 1291 | 731 / 993 / 1185 | 707 / 1008 / 1226 |
| Rail 75 / 100 / 125 °C | 997 / 1228 / 1408 | 800 / 1086 / 1293 | 774 / 1102 / 1339 |
| Falcon 75 / 100 / 125 °C | 1362 / 1681 / 1925 | 1087 / 1484 / 1768 | 1050 / 1514 / 1843 |
| Suwannee ACSS/TW 100 / 150 / 200 °C | 1235 / 1565 / **1815** | 1091 / 1467 / 1739 | 1107 / 1538 / 1858 |
| Cumberland 1926.9 ACSS/TW 150 / 200 / 250 °C (estimated) | 2452 / 2859 / 3211 | 2300 / 2743 / 3117 | not computed |

Published checks on these estimates:
- Oncor 1590 ACSR at 150 °C = 2064 A, published ([PUCT 55999_63](https://interchange.puc.texas.gov/Documents/55999_63_1424982.PDF)). That fits the Falcon trend above.
- 2×1926.9 ACSS/TW = 5,138 A per circuit, published (Oncor CCN).

## Q5. Is 2300–5000 A per bundle (1150–2500 A per subconductor) consistent with real conductors?

Arithmetic: I_bundle = 2 × I_sub, and S = √3 × 345 kV × I.

| Configuration | Per-subconductor current | Bundle current | MVA | Compared with the owner's range |
|---|---|---|---|---|
| 2×Drake @75 °C (current model) | 707–910 A | 1414–1820 A | 845–1088 | **Below 2300 A**, so the observed misses are expected |
| 2×Drake @100 °C (Austin Energy's stated MOT) | 993–1124 A | 1986–2248 A | 1187–1343 | Just below 2300 A at static; DLR hours will mostly exceed it |
| 2×Rail @100 °C | 1086–1228 A | 2172–2456 A | 1298–1468 | Near the lower bound |
| 2×Falcon ACSR @75 / 90 / 100 °C | 1050–1362 / ~1330–1550 / 1484–1681 A | 2100–2724 / ~2660–3100 / 2970–3360 A | — | Inside the range |
| 2×Suwannee ACSS/TW @200 °C | 1739–1858 A | 3478–3716 A | 2078–2220 | **Matches the owner's 3650 A / 1825 A "static" almost exactly** |
| 2×1926.9 ACSS/TW Cumberland (ERCOT standard) | ~2500–2570 A | **5000–5138 A** | 2987–3070 | **This is the 5000 A upper end** |

**What explains the 5000 A upper end (confirmed):** 5000 A is the ERCOT/TSP standard for new 345 kV construction, and 2,987 MVA = √3 × 345 kV × 5000 A.
- In the ERCOT Board recommendation for 25RPG009, new 345 kV lines carry "normal and emergency ratings of at least 2,987 MVA", with terminal equipment that must "meet or exceed 5000 A for 345-kV and 3200 A for 138-kV".
- Older 345 kV elements with legacy terminals are capped at 3200 A: "due to the existing 3200 A terminal equipment … 1,912 MVA" ([ERCOT 25RPG009](https://www.ercot.com/files/docs/2026/05/22/5.3-25RPG009-Oncor-and-LCRA-TSC-Muscovy-and-Voss-Lake-345_138-kV-Regional-Planning-Group-RPG-Project.pdf)).
- Austin Energy plans the same standard for its future Dunlap–Decker 345 kV: "These structures will carry two 5000 Amps transmission lines operating at 345 kV … up to 6000 MVA" ([26RPG022](https://www.ercot.com/files/docs/2026/07/17/16.-26RPG022-AEN-Dunlap-to-Decker-138-kV-Line-Project-Overview.pdf)).

**The 2300 A lower end:** no source. It is about 1374 MVA, and it sits roughly where 2×Drake or 2×Rail at 100 °C would land. The fact that 3650 = (2300 + 5000) / 2 suggests the owner's "static" value is a midpoint, not a utility rating (**likely**).

## Q6. Austin elevation

- USGS 3DEP Elevation Point Query Service at (30.2711, -97.7437) returns **163.05 m** (`https://epqs.nationalmap.gov/v1/json?x=-97.7437&y=30.2711&wkid=4326&units=Meters`). **Confirmed.**
- Open-Meteo's elevation API gives 167 m for the same point.
- NWS station KAUS (Austin-Bergstrom airport) is at 148.1 m and KATT (Camp Mabry) at 199.9 m (api.weather.gov/stations).
- USGS stream gauges in the city range from 412 to 701 ft (126–214 m), for example [Barton Springs 08155500](https://waterdata.usgs.gov/monitoring-location/USGS-08155500/all-graphs) at 412 ft.

**900 m is wrong by about 740 m.** The rating effect is small: Drake @75 °C goes from 707 A to 724 A (+2.4%), and Falcon @100 °C from 1514 A to 1541 A. Fixing elevation alone will not close the gap.

## Q7. Other reasons the Drake @75 °C rating sits below 1150 A

1. **Wrong conductor and MOT (main cause, likely).** Austin Energy itself rated 795 ACSR at 100 °C, not 75 °C. The Travis-crossing LCRA 345 kV line uses ACSS/TW, which is rated for 200 °C or more. Going from 75 °C to 100 °C alone raises Drake's static rating by about 40% (707 → 1008 A).
2. **The range is a planning envelope, not a single line's rating (likely).** 5000 A is the ERCOT new-build / terminal-equipment standard. 3200 A is the legacy terminal limit. 3650 A is the arithmetic midpoint.
3. **Normal vs emergency (confirmed that the concept applies).** Under Austin Energy's 2005 method, Normal = 90% of Emergency. ERCOT Emergency is a two-hour rating. If the owner's numbers are emergency ratings, compare against 0.9× for normal. Many recent ERCOT projects specify identical normal and emergency ratings (for example "2,987 MVA normal and emergency").
4. **Terminal-equipment limits (confirmed in principle).** Line ratings are often capped by terminals (3200 A legacy, 5000 A new), so the conductor's thermal rating is not always the binding limit. That caps the upper end; it cannot make a conductor rating fall below a lower bound.
5. **Per-circuit vs per-phase vs per-corridor (likely source of confusion).** ERCOT amp ratings are per circuit, which equals per phase current. On a double circuit, the "6000 MVA corridor" is two 5000 A circuits. If any number in the owner's range is a two-circuit or corridor total, the per-circuit value is half.
6. **Model parameters (confirmed by my calculation).** ε = α = 0.8 is close to neutral against utility 0.5 / 0.5 for ACSR at 100 °C: it adds radiative cooling and absorbs more sun. At 75 °C it lowers the rating about 3%. Azimuth 173° is close to N–S, versus Austin Energy's assumed E–W line. With real wind directions, a wrong azimuth can move DLR results substantially. The 900 m elevation costs about 2–3%.

## Open questions that need Power Systems or utility confirmation

1. Which specific 345 kV line or circuit does the "Austin" city point represent? Austin Energy (Austrop–Garfield–Lytton Springs, Sand Hill, Decker) or LCRA TSC (Clear Springs–Hutto, Gilleland Creek)?
2. What is that line's actual conductor? Candidates: 2×795 ACSR, 2×1590 ACSR Falcon, 2×959.6 ACSS/TW Suwannee, or 2×1926.9 ACSS/TW Cumberland. Was it reconductored under the RTP 2024 "Lytton Springs–Garfield–Austrop 345-kV Line Upgrades"?
3. What MOT does the TSP use today: Austin Energy's 100 °C for ACSR (2005), Oncor's 90 °C for 1590 ACSR, and an unconfirmed value (likely 200 °C) for ACSS?
4. Where do 2300 / 3650 / 5000 A come from? Are they normal, emergency, or seasonal ratings? Per circuit or per corridor? Is 3650 A just the midpoint?
5. What are the TSP's current static-rating assumptions? The only published values are from 2005 (40 °C, 2 ft/s, ε = α = 0.5), and the annual methodology submitted to ERCOT is not public.
6. What is the real line azimuth? The 173° in the model is a placeholder.

## What I could NOT verify
- The conductor on any specific Austin Energy 345 kV line after 2005, and on the RTP 2024 Lytton Springs–Garfield–Austrop upgrade.
- Any utility filing stating the 200 °C ACSS MOT for LCRA, Austin Energy or Oncor.
- Manufacturer ampacity tables at 100 °C; the 100 °C and higher values in this report are my IEEE 738 estimates.
- A source for the 2300 A lower bound.
- LCRA TSC's and Austin Energy's current facility-rating methodology documents (they don't appear to be public).
- The full size field of the FPP–Lytton Springs ACSR. The LCRA PDFs are OCR'd scans, and some fields are garbled.
