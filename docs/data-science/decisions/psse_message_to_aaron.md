Hi Aaron,

The PSS/E integration work (the hourly job that applies our ratings to Power Systems' case) has a result-table spec that your Phase 6 migration needs. It is written and checked against a local Postgres. You decide whether to adopt it.

Where it is (branch `feature/pss-e-integration` on origin):
- `docs/data-science/schema/psse_results_v1.md` is the spec, and `psse_results_v1.sql` is the reference DDL.
- `docs/data-science/decisions/psse_results_phase6_handoff.md` is the hand-off note listing what Phase 6 must add.

What Phase 6 needs to add:
1. Four tables: the run record, contingency results, dispatched capacity, and voltage margins.
2. A `dlr_psse_writer` role with exactly INSERT and SELECT on those four tables, and nothing on `city_rating`, `pipeline_run` or `latest_rating`.
3. Read access to the latest `city_rating` row for that role's reader path (the job reads ratings).
4. The verify script for the above.

One conflict for you to decide: plan 06-09 pins "exactly two migration files". Adding the PSS/E tables either changes that pin or goes into one of the two files. I did not touch your plans or `supabase/migrations`.

Two things the job relies on:
- It reads `rating_amps`, never `rating_mw`. `rating_mw` uses a power factor of 0.95, and the job converts amps to MVA itself at the case's base kV.
- Every `city_rating` row is provisional until Phase 7's go, so until then the job uses each city's static rating and records that.

Status: the study code (mapping, load flow, N-1, voltage margin, dispatched capacity) is built and tested against a fake `psspy` only. It has not run on real PSS/E. That needs Power Systems' case file, the city-to-branch mapping, and the laptop. The open questions for Power Systems are in `docs/data-science/decisions/psse_study_definitions.md`.

Can you tell me whether Phase 6 can take the tables, and how you want to handle the 06-09 pin?

Thanks,
Tejaswini
