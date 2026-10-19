# Decisions (from ADR-classified documents)

No documents in this ingest batch (20 total, `.planning/intel/classifications/`) were classified as ADR.

- Zero `locked: true` decisions exist in this ingest set.
- Zero LOCKED-vs-LOCKED contradictions are possible (nothing to compare).
- The closest artifact to a decision record is `docs/data-science/decisions/data_provider.md`, but it was classified DOC (not ADR) because its own `Status` field is explicitly `Open` and it repeatedly states "Not a final recommendation document" / "Explicitly not decided here." Its content is filed under `context.md` (topic: Weather Data Provider Vetting) rather than here. It should be revisited and reclassified as ADR once a final choice is recorded with `Accepted` status.

This file is intentionally near-empty. It is not an extraction error — mark absent rather than fabricate a decision that does not exist in the source set.
