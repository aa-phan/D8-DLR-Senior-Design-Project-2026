---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
review: 07-REVIEW.md
recorded: 2026-11-08
counts: {critical: 1, warning: 10, info: 4, total: 15}
open: 15
---

# Phase 07 code review disposition

Every finding starts as `open`. A triaged finding moves to `fixed` (with the commit), `accepted` (with the owner's
reason), or `deferred` (with the phase that takes it).

| ID | Severity | Finding | Disposition | Note |
|---|---|---|---|---|
| CR-01 | critical | One-shot FRESH guard is defeated by `--evidence-root` (and is not atomic) | open | both signed reads (v4-read1, v4-read2) are already spent and committed; matters for any future protocol |
| WR-01 | warning | `v4-read2` precondition (read 1 named no winner) not enforced in code | open | read 2 ran correctly under the process gate (07-15 preflight) |
| WR-02 | warning | Veto record flags not bound to the source reports they cite | open | |
| WR-03 | warning | Three different "is v4 signed" predicates; the FRESH guard uses the weakest | open | |
| WR-04 | warning | Frozen artifacts deserialized without a hash check on the Drake-parity path | open | |
| WR-05 | warning | `write_manifest` re-blesses every `.joblib` in the directory | open | |
| WR-06 | warning | Credential regex misses key-like names (e.g. `SUPABASE_SERVICE_ROLE_KEY=`) in the public Actions log path | open | pre-existing (Phase 5, 156cdc2); `redact()` masks every REQUIRED_ENV value first, so only secrets outside REQUIRED_ENV are exposed by the regex gap |
| WR-07 | warning | Production conductor ranges too wide to catch unit slips (emissivity/absorptivity accept 0.0) | open | overstated-ampacity direction; no current value is affected |
| WR-08 | warning | B5 fallback skipped when the ml band is degenerate AND the lookback gap applies; untested | open | |
| WR-09 | warning | Live DB rows cannot show whether the naive band gated G6 | open | |
| WR-10 | warning | Nothing ties served ml artifacts to the conductor table they were trained under | open | relevant whenever PRODUCTION_CONDUCTORS changes again (retrain required) |
| IN-01 | info | `forecast_gap_kind` duplicates `forecast_gap_reason`'s conditions | open | |
| IN-02 | info | Stale "provisional" comments after the signed GO | open | |
| IN-03 | info | COND-02 golden test depends on git state and exact library versions; no CI runs pytest | open | |
| IN-04 | info | CLI reports post-guard `ValueError` as "refused"; global config mutation in the frame provider | open | |
