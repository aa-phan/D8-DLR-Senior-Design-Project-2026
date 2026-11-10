# Phase 4 context: per-city scaling of the 39-bus case

Decided with the user on 2026-11-09, before planning. No city load figures are recorded here: they come from Power Systems' scaling files and live in the private mapping on the laptop.

## Decisions

- **One network, one case copy per city.** The IEEE 39-bus system stands in for each city. The job takes a fresh copy of the base case for each city, scales it to that city's targets, then runs the existing study on it. The four cities are four independent load flows; no city's scaling touches another's solve. (The user's concern was cross-talk if the cities were areas of one case; this design avoids that by construction.)
- **Scaling targets are data in the mapping.** Per city: a target net load (MW), a target generation (MW), and the load reactive target (Mvar) that the recorded scale step also carries. The job applies them through its own scaling call. It does not run the `.idv` files: they are GUI-recorded scripts, and executing script files named in a config is a risk the job has so far avoided.
- **What the recorded scale step does** (read from PSS/E's own dialog for one city's script): it sets the case's net load to the first number and its generation to the second, and the last number is the load Mvar. The base case totals are about 5,857 MW load, 2,781 Mvar load and 5,914 MW generation.
- **Basis of the targets: average load** for the three cities that have files. Record the basis (average or peak) next to every city's targets in the mapping.
- **El Paso has no scaling file yet.** Proposal: scale it on its average load from the EIA-861 sales table (2025, utility 5701, retail MWh divided by 8,760 h; 2024 gives the same to within 0.1%), generation set from the same load-to-generation ratio the other cities use. Fallback if the user prefers: its peak, labelled as a placeholder. To be confirmed by the user and Power Systems.
- **The same lines can map in every city's copy** (to be confirmed with Power Systems); only the scaling differs.
- **The case must be unconverted** (a converted dynamics case fails the load flow with `fnsl ierr 2`). The free Xplore edition allows at most 50 buses.

## Open questions for planning

1. The exact `psspy` call and argument order that reproduces the recorded scale step (the existing job already uses the combined scale call `scal_2` for sink-load scaling, proven on the laptop). Planning must verify against the real signature on the laptop before relying on it.
2. How the run record, the result rows and the dispatch table carry the per-city case (the schema is per run and per city already; check whether a per-city case label or scaling record is needed in `psse_run`, and whether that needs a new migration from the data owner).
3. Mapping file schema version bump and the placeholder example update.
4. Solve time and failure handling: one city's scaled case failing to converge must not hide the other three (compare the current per-city failure behaviour).

## Out of scope

Real Power Systems mapping and case review (Phase 3, step 7); the real proof write (Phase 3, step 9); changing the task XML encoding.
