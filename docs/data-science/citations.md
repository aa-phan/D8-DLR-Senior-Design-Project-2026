# Research Citations

Bibliography for external sources found via AI-assisted web research across this project's implementation sessions (2026-08-24, 2026-08-25). Companion to `ACKNOWLEDGEMENTS.md`, which discloses that this research was AI-sourced and **has not yet been independently confirmed by a team member** — per that document's policy, treat every citation below as needing human verification before it's relied on in the research paper or any graded submission, especially the ERCOT filing behind the San Antonio value. **Note (2026-10-08):** `backend/config.py::STATIC_RATINGS` has since been re-keyed to the four project cities (Austin, Corpus Christi, Midland, El Paso) with `DEFAULT_STATIC_RATING = 900.0` as fallback; the San Antonio entry and the 5-city table described below no longer exist in code, so those sections are historical research.

Organized by what the research was for. Within each section: sources actually **used** in the codebase, then sources **checked but excluded or inconclusive** — kept here rather than discarded, so nobody re-runs the same dead-end search later.

---

## 1. Static Line Ratings (`backend/config.py::STATIC_RATINGS`)

Goal: representative static line ratings (Amps) for 5 Texas metros (Houston, Austin, Dallas, Fort Worth, San Antonio), for the per-location config lookup.

### Used

**ERCOT Board Item 11.2 (Aug 2023) — "CPS Energy – San Antonio South Reliability RPG Project," including Attachment A (ERCOT's Independent Review report).**
https://www.ercot.com/files/docs/2023/08/24/11.2%20CPS%20Energy%20San%20Antonio%20South%20Reliability%20Regional%20Planning%20Group%20Project%20(Template)%20v3.pdf
Used for: San Antonio's `STATIC_RATINGS` value (1,761 A). States the existing single-circuit 345kV J.K. Spruce–Pawnee path has 1,051 MVA normal capacity, converted to ≈1,761 A at 345kV. This is the only genuinely city-specific, sourced rating found across two research passes — everything else converged on a uniform baseline or was excluded as non-representative (see below).

**AEP Texas transmission capacity upgrade — TD World, "AEP Raises Transmission Capacity."**
https://www.tdworld.com/overhead-transmission/article/20963095/aep-raises-transmission-capacity
Used for: corroborating evidence for the uniform 900 A baseline (Houston/Austin/Dallas/Fort Worth). Documents AEP Texas's Lon Hill–North Edinburg and Lon Hill–Rio Hondo 345kV lines (South Texas — not one of the 5 target cities) using a bundled 2×795 kcmil Drake ACSR conductor at ~1,769 A normal summer rating (before a later ACCC reconductoring raised it to ~3,099 A). Roughly ~880 A per single conductor, consistent with the independently-sourced ~900 A single-conductor baseline.

### Checked, excluded as non-representative

**ERCOT Board Item 9.3.4 (Feb 2025) — "Oncor Wilmer 345/138-kV Switch Project," including Attachment A independent review.**
https://www.ercot.com/files/docs/2025/01/27/9-3-4-oncor-wilmer-345-138-kv-switch-project.pdf
Found real, dated, sourced ratings for the Dallas/Fort Worth load zone (rebuilt 138kV lines ≥764 MVA ≈3,200 A; new/rebuilt 345kV circuits ≥2,988 MVA ≈5,000 A) — but these are modern-rebuild TARGET specs sized for HTLS-class conductor, not representative of this project's typical-existing-conductor (795 kcmil Drake ACSR) assumption. Excluded from `STATIC_RATINGS` per your explicit decision; Dallas/Fort Worth use the uniform 900 A baseline instead. Kept here so this isn't re-investigated as if it were still an open lead.

### Checked, no usable numbers found

- **Houston (CenterPoint Energy) / CNP Baytown Area Load Addition** — ERCOT project name located, but no line-level MVA/Amp rating extracted.
- **Austin (Austin Energy / LCRA) / LCRA-CEHE Euclid 765kV project, Oncor/LCRA TSC Muscovy–Voss Lake project** — ERCOT project names located, no per-line rating specific to Austin's service territory extracted.
- **PUCT interchange filings** (interchange.puc.texas.gov) — one utility filing PDF was downloaded but could not be parsed in this environment (no PDF text-extraction tooling available at the time); not a source-availability problem, an environment limitation.
- **FERC Form 715 filings** (elibrary.ferc.gov) — utilities are required to file detailed transmission line inventories including ratings, but Form 715 content is CEII-restricted and was not accessible via search/fetch in this environment.
- **DOE, "Grid-Enhancing Technologies: A Case Study on Ratepayer Impact"** (already cited elsewhere in this project's Prior Art Report) — re-checked specifically for an ERCOT static-rating figure; the report's focus is NYISO, not ERCOT. Could not confirm it contains an ERCOT-applicable number — do not cite it for a Texas-specific rating.
- General manufacturer/distributor ampacity reference tables (Southwire and similar cable-spec-sheet sources) and a secondary IEEE 738 worked-example source (a non-standard, non-primary example computing ~689 A for a single 138kV Drake conductor under different assumed conditions) — both informed the initial ~900 A convergence in the first research pass, but specific URLs were not preserved from that pass. If this number needs re-verification, re-run the search rather than trust this note as a citation.

---

## 2. IEEE 738 Validation (`backend/thermal_model.py`, `backend/tests/thermal_model_test.py`)

Goal: a citable, published worked example to validate `ieee738_ampacity` against — this is how the `np.pi` bug (see `docs/data-science/PRD.md` §9) was found.

### Used

**IEEE Std 738-2023, "IEEE Standard for Calculating the Current-Temperature Relationship of Bare Overhead Conductors," Clause 4.6.1 ("Problem statement" through 4.6.1.7 "Steady-state thermal rating"), pp. 28–31.**
Used for: the entire validation test in `backend/tests/thermal_model_test.py::test_ieee738_worked_example_795kcmil_drake_acsr`. This is the standard's own official worked example — read directly from the primary source (PDF text-extracted and the relevant clause read in full, not inferred from a secondary mention). Conductor: 795 kcmil 26/7 Drake ACSR, exactly matching this project's default `ConductorConfig`. Full input set and the published answer (1025 A) are reproduced in the test file's comments; see that file for the complete derivation, including the resistance-model tolerance justification.

This is the same standard already cited generally throughout this project's course deliverables and `docs/data-science/` specs (e.g. `Project Definition.md` reference [4]); this citation adds a specific clause/page reference for the worked example specifically, which the prior general citations didn't have.

---

## Verification status

Per `ACKNOWLEDGEMENTS.md` §4: none of the citations above have been independently opened and confirmed by a team member yet. Before using any of these in the research paper or a graded submission:
1. Open the ERCOT Board Item 11.2 PDF directly and confirm the 1,051 MVA / San Antonio figure independently.
2. Confirm the IEEE Std 738-2023 clause 4.6.1 worked example against a copy of the actual standard (e.g. via UT Austin's IEEE Xplore access) — the values above were extracted from a fetched PDF, not hand-checked against a second source.
3. Treat the "checked, no usable numbers found" entries as leads for someone with PUCT/FERC filing access or a library research consult, not as dead ends — they may still contain real answers a human researcher could extract where automated fetch/parse failed.
