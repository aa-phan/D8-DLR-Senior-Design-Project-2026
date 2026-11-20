# pandapower network data: keep the converted copy private

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-11-20 (UTC) |
| **Deciders** | Tejaswini Kalikiri (owner of the pandapower solver work) |

Scope: this record covers where the converted 39-bus network data lives. The solver design, the agreement check and the hourly workflow are recorded elsewhere.

## Decision

The converted 39-bus network stays private. It lives on the owner's machine and is not committed. The hourly workflow gets it from a GitHub secret that is created from the private converted copy and written to the runner's temporary folder only.

The PSS/E reference answers and the per-city mapping also stay private, whichever way this decision had gone. The repository never holds them.

## Context

The PSS/E session exported the 39-bus network from the licensed machine, and the converted copy was built from that export. Four facts bear on whether it can be published.

- **It matches the PSS/E export.** The parity report compared the converted network with the export element by element and found 0 differences in 11 categories (counts 5, classification 56, names 278, in-service status 116, impedance 152, ratings 34, voltage limits 117, setpoints 22, machine limits 40, loads 38, shunts 4 compared).
- **It is not pandapower's public 39-bus case.** Against that case, 39 buses and 46 branches match, with 1 classification difference. The export has 12 transformers and 34 lines against 11 and 35, and 19 loads against 21. Beyond a tolerance of 1e-6, ratings differ in 34 places, voltage limits in 39, machine limits in 10, loads in 9, setpoints in 7, impedance in 2 and shunts in 0.
- **It fits a GitHub secret.** The converted copy is 25,191 bytes (3,231 bytes gzipped), under the 48 KB limit for a secret.
- **Its licence is not established.** The data comes from PSS/E's own example library. Nobody has confirmed whether that example may be republished.

## Consequences

**Positive:** no licence question arises. Nothing leaves the owner's control. The choice can be changed to publication later; the reverse cannot be done.

**Negative:** the hourly workflow depends on a secret that a person must create and keep in step with the private copy. Anyone who runs the study elsewhere needs the secret or the private copy. The secret must stay under 48 KB, and it uses about half of that today. There is no hash-pinned public copy, so a reader cannot check the data against the repository. The owner of the secret is Tejaswini Kalikiri.

**Neutral:** the leak guard needs no allow-list entry, and no network file is added to the repository.

## Alternatives considered

**Publish a sha256-pinned copy in the repository.**
- For: the hourly job and every developer get the exact network from git, checked by its hash, with no secret to manage.
- Against: the repository is public, so the file stays in history permanently. The licence is unconfirmed, and the data is not the public case.
- Why not chosen: publication is a one-way door, and its licence question is open.

## What happens next

The hourly workflow creates its secret from `converted_network.json` in the newest check folder of the approved session, under `data/private/pandapower/sessions/`. That folder is git-ignored. If the owner later confirms the licence and decides to publish, a new dated entry supersedes this one and records how the licence was confirmed.

## References

- Parity and evidence record for the approved session: `.planning/workstreams/pandapower-solver/phases/01-pss-e-reference-session-and-network-parity/01-SESSION-RECORD.md`
- Private data location: `data/private/pandapower/` (git-ignored)
