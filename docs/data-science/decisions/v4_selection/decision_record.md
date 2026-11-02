# SEL-04 decision record (signed protocol v4, early model selection)

This file records the project owner's decisions after each read. The owner's words are recorded verbatim, the name is as typed, and the date is the UTC date of the reply. The executor is named only as recorder and decides nothing.

## Read 1 (2026-11-01)

Read 1 (round `v4-read1`, evaluation instant 2026-11-01T00:00:00Z) ran once at 2026-11-02T17:51:56Z. Evidence: `data/shadow/evaluation/v4-read1/reconstructed_frames_20261102T175156Z/` (headline) and `data/shadow/evaluation/v4-read1/shadow_logs_20261102T175210Z/` (live-system check, never pooled). Results for the owner: `read1_results.md`.

**Rule's outcome (from the committed headline report):** no pick. "No candidate qualifies under signed protocol v4: no shadow model replaces ml (D-07). Read 1 names no winner, so the pre-registered re-test v4-read2 runs at or after 2026-11-08T00:00:00Z under the same rules."

**Owner decision (recorded from the owner's replies of 2026-11-02, the last at about 20:30Z):**

- Decision (option chosen): `rule-outcome-ml`. The rule's outcome is accepted: no pick under signed v4. No model replaces `ml` under the rule.
- Interim G6 method: `ml` retrained on projected wind (B2, D-14; models commit `e0a00a9`), checked under D-15 at the go/no-go (plan 07-17).
- Shadow model moving forward: `ml_cooling_corrected` for the day-ahead (24 h) forecast, as the owner's labelled engineering choice. It is explicitly NOT a pick under the signed rule: its best read-1 benefit was 11.89 A against the 27.86 A bar, Holm-adjusted p 0.3624. This follows the precedent of the owner's 2026-10-05 engineering tie-break for `ml_wind_corrected`, "never a claim of statistical superiority".
- Owner's words (verbatim):
  1. "rule-outcome-ml, aaphan"
  2. "for day ahead, let's select cooling, and incorporate it as an additional feature alongside 60 minute, with the understanding that it has more error because its in the future (like any future forecast would in any domain)"
  3. Asked how to record it, the owner chose "Now, as labelled choice": record now that the rule's outcome is no pick and that the owner selects `ml_cooling_corrected` as the day-ahead method as an engineering choice, not a rule pick; read 2 still runs as pre-registered and is reported either way; interim G6 stays `ml` (B2-fixed, 60-minute) under D-15 at the go/no-go.
  4. The owner chose to add the day-ahead feature as a new roadmap phase after Phase 7.
- Departure from the signed rule's outcome (label): **Departure: yes — owner engineering selection outside the signed rule's outcome.** The rule's outcome (no pick) is accepted unchanged; the departure is only that the owner also selects `ml_cooling_corrected` for the day-ahead output. It is a labelled engineering choice, not a statistical finding, and is not entered as a rule pick.
- Supporting evidence (labelled exploratory, not pre-registered, non-FRESH; it did not decide anything under the rule):
  - `docs/data-science/exploratory/2026-11-02_horizon_comparison/REPORT.md` (TEST window): `ml_cooling_corrected` beats the reference by +26.3 A (Holm p 0.001) and the raw forecast by +25.8 A (Holm p 0.001), in all 4 cities. The cost of a 24 h forecast against the 60-minute `ml` is +23.1 A [18.0, 28.3], about 1.7% of rating.
  - `docs/data-science/exploratory/2026-11-02_ml_vs_naive/REPORT.md`: 60-minute `ml` beats naive by +3.9 A pooled [3.1, 4.7] over 2026-01-01 to 2026-09-29, significant in all 4 cities; not significant on the 2-week September replay.
- Scope: the day-ahead forecast is an additional output alongside the 60-minute G6 forecast, understood to carry more error because it is further in the future. Serving it in production is a new roadmap phase after Phase 7 (added by the orchestrator), not part of Phase 7. Nothing in live ratings changes now.
- Read 2 (pre-registered, D-08) still runs at or after 2026-11-08T00:00:00Z (plan 07-15) under the same rules and is reported either way. If `ml_cooling_corrected` is a rule pick there, that supersedes the engineering label.
- Signed by: aaphan, 2026-11-02 (UTC)
- Date (UTC): 2026-11-02
- Recorded by: the executor (07-13)
