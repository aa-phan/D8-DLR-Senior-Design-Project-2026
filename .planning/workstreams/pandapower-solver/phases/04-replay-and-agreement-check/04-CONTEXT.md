# Phase 4: Replay and Agreement Check - Context

**Gathered:** 2026-11-20 (owner answers at the planning checkpoint; no discuss-phase session)
**Status:** Ready for planning

## Phase boundary

A read-only replay of the recorded PSS/E runs through pandapower, with an honest agreement report that can fail. This is the go-live gate for the hourly workflow. It does not write to the database and does not need the Phase 3 migration.

## Decisions (owner, 2026-11-20)

- **D-01 (database route): owner-run SQL export.** The owner of the Supabase project (Aaron) runs one read-only SQL export in the Supabase SQL editor and sends the file. No credential is shared and no database connection is made by the replay. Everything that reads the database is a small separate step that produces a private snapshot file under `data/private/`; the replay compute reads only that snapshot. The plan must provide the export SQL (read-only, counts and the columns the replay needs) and an ingest command that validates the file's shape. - **Reversibility:** reversible; a direct read-only connection or a SELECT-only role can be added later.
- **D-02 (margin floor): `max(2%, stored step or tolerance)`** for margins. Rating-bound margins stop at the first 25 MW step that reaches the rating, so a strict 2% would fail on quantisation. The floor used is printed in the report header. Voltages keep 0.01 pu and flows keep `max(2%, 2 MVA)` from `compare.py`, imported, not redefined. - **Reversibility:** reversible (one constant).
- **D-03 (largest deviation): private report only.** The detailed report on the owner's machine shows the largest deviation even on a pass. CI mode prints counts and pass or fail only. - **Reversibility:** reversible.
- **D-04 (gate rule): at least 1 replayed run, at least 1 non-empty set comparison, no failures.** Violation kinds with no recorded rows are listed as "not exercised". Zero replayed runs or zero non-empty comparisons is "incomplete", not a pass. - **Reversibility:** reversible.

## Defaults taken from the research (not asked)

- The borderline band equals the owner's tolerance (0.01 pu, 2%); a one-sided element within the tolerance of its limit is "borderline", outside it is a failure. Any one-sided non-convergence row is a failure.
- The first export prints counts only: runs by outcome, distinct mapping and case hashes, and how many match the local mapping and the session's recorded case hash.
- If no recorded run matches the current mapping, that is reported as "excluded" with the reason; the options for getting a matching run (one explicit-yes PSS/E run under the current mapping, or the Phase 1 session's per-outage reference files) are outside this phase and are surfaced to the owner.

## Constraints that bind the plan

- Private files under `data/private/` are never printed, quoted or committed. Detailed output stays on the owner's machine; CI output is counts and pass or fail, and a test scans it for identifiers and study values (reuse `backend/private_leak_scan.py`, with a planted identifier proving the test can fire).
- The replay module imports no `psycopg`, `writer` or `job` (proof of "writes nothing" by import scan, a recording fake, and a Postgres-tier test that skips on this Windows machine).
- Tests that need Postgres skip here and run where Postgres exists.
- Research: `04-RESEARCH.md` (medium confidence; the live database was never queried).
