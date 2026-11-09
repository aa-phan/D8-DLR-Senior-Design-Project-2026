---
phase: 07-per-city-conductors-shadow-refit-and-early-model-selection
review: 07-REVIEW.md
recorded: 2026-11-08
counts: {critical: 1, warning: 10, info: 4, total: 15}
open: 12
deferred: 3
---

# Phase 07 code review disposition

Every finding starts as `open`. A triaged finding moves to `fixed` (with the commit), `accepted` (with the owner's
reason), or `deferred` (with the phase that takes it).

| ID | Severity | Finding | Disposition | Note |
|---|---|---|---|---|
| CR-01 | critical | One-shot FRESH guard is defeated by `--evidence-root` (and is not atomic) | deferred | both signed reads (v4-read1, v4-read2) are already spent and committed; matters for any future protocol |
| WR-01 | warning | `v4-read2` precondition (read 1 named no winner) not enforced in code | deferred | read 2 ran correctly under the process gate (07-15 preflight) |
| WR-02 | warning | Veto record flags not bound to the source reports they cite | open | |
| WR-03 | warning | Three different "is v4 signed" predicates; the FRESH guard uses the weakest | open | |
| WR-04 | warning | Frozen artifacts deserialized without a hash check on the Drake-parity path | deferred | |
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

Owner decision 2026-11-08 (verify-work 07): CR-01, WR-01 and WR-04 are deferred to "before any new signed protocol
or FRESH read" (see 07-SECURITY.md Known Residuals); the v4 reads they could have affected are spent.

## Incremental review (07-REVIEW-incremental.md, commit 3aa7bf4)

| ID | Severity | Finding | Disposition | Note |
|----|----------|---------|-------------|------|
| WR-01 (inc) | warning | Signature gate is in `main()` only, not in `run_ablation` | accepted | Intentional: T-07-23 registers a CLI refusal; tests drive `run_ablation` directly. Documented in the module docstring |
| WR-02 (inc) | warning | Happy-path CLI test silently depended on the real signing copy being signed | fixed | test now monkeypatches `core.v4_signed` to True |
| IN-01 (inc) | info | Refusal not documented; stderr cited an internal ID | fixed | docstring sentence added; message names the signing copy |
| IN-02 (inc) | info | Unsigned test checks only the explicit out-dir | accepted | `run_ablation` is patched to fail the test if called, so no write path is reachable |
