---
phase: 06-exposure-e2e-verification
review: 06-REVIEW.md
recorded: 2026-11-01
fix_report: 06-REVIEW-FIX.md
counts: {critical: 0, warning: 6, info: 6, total: 12}
open: 6
round_2: {review_commit: 2eb2f8c, critical: 0, warning: 2, info: 3, total: 5, open: 5}
---

# Phase 06 code review disposition

Every finding starts as `open`. A triaged finding moves to `fixed` (with the commit), `accepted` (with the owner's
reason), or `deferred` (with the phase that takes it).

| ID | Severity | Finding | Disposition | Note |
|---|---|---|---|---|
| WR-01 | warning | `verify_exposure.sql` cannot see column-level grants or inherited privileges | fixed (d5bddba) | verify_exposure.sql now has 18 checks (was 17); confirm the new one on the live DB at next run |
| WR-02 | warning | Refusal checks can pass for the wrong reason (invalid key, missing table, 5xx) | fixed (99674cd) | needs human check: 5xx view writes pass only with 55000/42501 (matches live 06-09/06-13 evidence) |
| WR-03 | warning | Detector exception text is published to `anon`; docs say none is stored | fixed (29aa85c) | writer redacts + caps alerts; detector still embeds raw exception text (file paths survive redaction); stored rows need a one-off owner check |
| WR-04 | warning | Read-only session guard does not hold on a transaction-pooler URL | fixed (e8ab256) | no risk today (bound SELECTs only) |
| WR-05 | warning | Soak "late run" rule explains exactly the breach it detects | fixed (f65062c) | needs human check: late-run cause no longer excuses a breach without owner annotation |
| WR-06 | warning | `http://` accepted for any host; `apikey` follows redirects | fixed (efe3fbd) | |
| IN-01 | info | `ops.log_freshness()` comment says it reads "as the calling role" | open | applied migration is pinned: fix only via a new additive migration or a runbook note |
| IN-02 | info | Malformed `fallback` cell silently read as false | open | |
| IN-03 | info | Report CLI edge cases fail with a traceback or a silent default | open | |
| IN-04 | info | `_slot_window` does not match its docstring | open | |
| IN-05 | info | Consumer examples have small robustness and hygiene gaps | open | |
| IN-06 | info | Two statements in `api-contract.md` are stale after Phase 6 | open | |

## Round 2 (review of the fix commits d5bddba..efe3fbd, 06-REVIEW.md at 2eb2f8c)

Round 2 reuses the ids WR-01.., IN-01..; they are different findings from round 1 above. Round 1's report is 06-REVIEW.md at fced310.

| ID | Severity | Finding | Disposition | Note |
|---|---|---|---|---|
| WR-01 | warning | 300-char alert cap cuts the `— fallback rating N A` suffix on long G6 exceptions | open | test asserts the cut, not that the suffix survives |
| WR-02 | warning | Any 4xx on a view write counts as a refusal (400/404/429/bare 401 would pass) | open | same false-pass class as round-1 WR-02; live verdicts unaffected (live answer is 500/55000) |
| IN-01 | info | `begin_read_only` never confirms the transaction is read-only | open | live trace on 2026-11-02 worked; no committed real-Postgres test |
| IN-02 | info | New privilege check in `verify_exposure.sql` skips sequences | open | |
| IN-03 | info | 404 PGRST205 passes on a renamed table; default opener reads proxy env at import | open | |

