# Phase 1: PSS/E Reference Session and Network Parity - Discussion Log

> Audit trail only. Decisions live in 01-CONTEXT.md.

**Date:** 2026-11-16
**Areas discussed:** Session logistics; Where private data lives; Reference answer scope; When numbers don't match

## Session logistics

| Question | Options | Selected |
|---|---|---|
| Which PSS/E machine and person? | Same laptop, same teammate; A different licensed PC; Not sure yet | Same laptop, same teammate |
| How should the teammate run it? | Remote, one script; With you or me guiding live | Remote, one script |
| How do the private output files get back? | One zip, sent privately; USB stick / in person | One zip, sent privately |
| How does the mapping get back onto the laptop? | You send it back privately; Script takes targets typed in | You send it back privately |

## Where private data lives

| Question | Options | Selected |
|---|---|---|
| Converted network data long-term | Decide after parity; Always a GitHub secret; Commit it now | Decide after parity |
| PSS/E reference answers | Only your machine, git-ignored; Also a GitHub secret | Only your machine, git-ignored |
| Private folder location | Inside repo, git-ignored; Outside the repo | Inside repo, git-ignored |

## Reference answer scope

| Question | Options | Selected |
|---|---|---|
| Which solves to export | Base + every outage; Base cases only; Base + a stressed case | Base + every outage |
| Margin limit point per city | Yes, the limit point per city; No | Yes |
| Also dry-run the PSS/E job | No, keep it single-purpose; Yes, add a dry run | No |

## When numbers don't match

| Question | Options | Selected |
|---|---|---|
| A mismatch after data is matched | Explain it or fail; Strict: any miss fails; Loosen tolerance | Explain it or fail |
| Absolute floor for idle lines | Within 2 MVA absolute; Within 5 MVA absolute; You decide | Within 2 MVA absolute |
| Reactive-limit behaviour | Whatever PSS/E was set to; Always enforce limits | Whatever PSS/E was set to |

## Claude's discretion

Export format, file names, parser structure (fail-closed), exact psspy calls for settings, summary wording, code location of the minimal scaling and load flow.

## Deferred ideas

None.
