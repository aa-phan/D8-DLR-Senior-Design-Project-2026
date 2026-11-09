Hi Aaron,

Update on the PSS/E hourly job, and one request. Your Phase 6-8 work is done and archived, so this is a new follow-on migration, not a change to a finished plan. This replaces my 2026-10-28 message.

**What changed since then.** The job now runs on real PSS/E 36.4 (the licensed laptop, free Xplore edition, Python 3.14), on the public IEEE 39-bus case with a throwaway mapping:
- selftest passes, the read-only probe passes (27 checks), and the probe's write check passes (29 checks);
- a dry run reads the four live `city_rating` rows through the REST read path with the publishable key, screens 28 contingencies, and validates ok (outcome `ok`, nothing written to the database).

So the study and the ratings read both work. The only thing that cannot run yet is the final write, because the tables and the writer role do not exist.

**The request.** Please add one migration, `supabase/migrations/<UTC ts>_psse_results.sql`, sorted after `20261108120100_expose_day_ahead_forecast.sql`:
1. Its body is the region of `docs/data-science/schema/psse_results_v1.sql` from `-- BEGIN psse_results_v1` to `-- END psse_results_v1`, copied verbatim. It creates four private tables (`psse_run`, `psse_dispatched_capacity`, `psse_voltage_margin`, `psse_contingency_result`) and the role `dlr_psse_writer` without a credential.
2. `dlr_psse_writer` holds exactly INSERT and SELECT on those four tables and nothing on `city_rating`, `pipeline_run`, `latest_rating` or the day-ahead objects. `anon` and `authenticated` hold nothing on the four tables.
3. `supabase/ops/verify_psse_results.sql` (read-only) checks all of the above. The checks are specified in `docs/data-science/decisions/psse_results_phase6_handoff.md`; its pointers to plans 06-01 and 06-09 are from before Phase 6 closed, so read it for the content and ignore the plan numbers.
4. After it is applied, set the `dlr_psse_writer` password yourself and send me the session-pooler connection string directly, not through git or a chat channel. The laptop keeps it only as `SUPABASE_PSSE_DB_URL`.

**How it fits what you already built.** I modelled the DDL on your migrations, so it should read like them: row-level security enabled on every table, `revoke all ... from public, anon, authenticated`, the role created only if it is missing (as `dlr_writer` is in `20261019000000_create_city_rating.sql`), `grant usage on schema public`, and named per-role policies. The ratings side needs nothing new from you: the job reads `city_rating` the way your examples do, through REST with the publishable key, which is why the writer role gets no access to `city_rating` at all. Two deliberate differences, tell me if you want either changed:
- **A separate role, not `dlr_writer`.** `dlr_writer` can insert and update `city_rating` and `pipeline_run`. The PSS/E job runs on another team's laptop, so it gets its own role with INSERT and SELECT on the four new tables only.
- **Append-only, with separate INSERT and SELECT policies** instead of your `for all` policy. A PSS/E run is never rewritten, unlike a `city_rating` hour.

The four tables sit in `public` and grant nothing to `anon` or `authenticated`, so your exposure sweep and `verify_exposure.sql` should not change. I have not run your verifier against it, though; please do.

**Two things to check on your side**
- Your tests may assert an exact migration count or an exact set of files. I did not check; one extra file may need those assertions updated.
- The job reads `rating_amps`, never `rating_mw` (the MW value assumes a 0.95 power factor; the job converts amps to MVA itself at the case's base kV).

**Not blocking you.** The real city-to-branch mapping and Power Systems' case still come from Power Systems; I am raising that with them in person. Until then the job uses a throwaway mapping on the public 39-bus case, and nothing from the real grid is in this repository.

Everything is on branch `feature/pss-e-integration` (merged with the current `main`, no conflicts).

Can you tell me whether you can add the migration, and roughly when?

Thanks,
Tejaswini
