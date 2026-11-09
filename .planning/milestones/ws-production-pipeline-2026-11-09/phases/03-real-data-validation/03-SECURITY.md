---
phase: "03"
slug: "real-data-validation"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-21"
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Provider APIs → backfill | Synoptic, NSRDB, Open-Meteo, TCEQ, ASOS responses and error strings enter the backfill and are persisted to the trace and log | Weather observations (public); error text that may carry query-string credentials (sensitive) |
| Owner shell → backfill | Only the owner's checkpoint command loads `.env` (SYNOPTIC_TOKEN, NREL_API_KEY, NREL_API_EMAIL) via python-dotenv | API credentials (secret) |
| Git-ignored raw outputs → committed artifacts | Raw archive, trace, log and console stay under `data/historical/`; only derived aggregates, the manifest and the doc are committed | Aggregates (public); raw rows (not committed) |
| Offline analysis → shadow/experiment data | `real_data_validation.py` must not read shadow or experiment data (anti-peeking before the 2026-11-24 evaluation) | Forecast-vs-truth outcomes (embargoed) |
| Owner → VAL-03 record | The go/no-go and signature come only from the owner at a blocking-human checkpoint | Decision and signature (authorship) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-03-01 | Information disclosure | backfill trace error/alert text | medium | mitigate | `_redact` (`backfill_archive.py:54,57-58,91-99`) on alerts (`:133`) and city error (`:143`), 200-char cut after redaction; tests `backfill_trace_test.py:201-239`; `/data/historical/` git-ignored; 0 credential-shaped hits in the 11 raw files. Residuals CR-01, WR-01 below | closed |
| T-03-02 | Tampering | archive/trace consumed by the analysis | medium | mitigate | `read_history(validate=True)` with dropped-row counts; self-checks make `report` exit 1 (`real_data_validation.py:1441-1444`); tests `real_data_validation_test.py:359-400` | closed |
| T-03-03 | Tampering (anti-peeking) | real_data_validation.py | high | mitigate | Acceptance grep for shadow/experiment names exits 1; imports `:42-62` only; all reads on CLI paths | closed |
| T-03-04 | Elevation of privilege | config/safety modules | medium | mitigate | `git log 01f46c1..HEAD` over policy and frozen files is empty | closed |
| T-03-05 | Information disclosure | tests → live providers | medium | mitigate | `_no_network` / `_offline_env` fixtures (`backfill_trace_test.py:35-61`, `real_data_validation_val02_test.py:33-59`); 41 tests pass | closed |
| T-03-06 | Information disclosure | `.env` | high | mitigate | No dotenv load in implementation or tests; owner command template only; `.env` git-ignored | closed |
| T-03-07 | Information disclosure | committed manifest/completeness | medium | mitigate | Commit `fadf9b0` holds exactly the two files; credential grep 0 hits | closed |
| T-03-08 | Tampering | archive used by Phase 4 | medium | mitigate | `manifest.json` pins sha256, bytes and per-city rows; recomputed 2026-10-21, all match | closed |
| T-03-09 | Repudiation | which code produced the data | medium | mitigate | Manifest `git.head=175b32b`, `backend_dirty=false`; `git diff 175b32b HEAD -- backend` empty | closed |
| T-03-10 | Denial of service | provider quotas / multi-hour run | low | accept | See Accepted Risks Log AR-03-01 | closed |
| T-03-11 | Tampering (silent degradation) | replay without anomaly models | medium | mitigate | `ReplayRefused` at `real_data_validation.py:1239-1245`, exit 2 at `:1604-1606`; test `val02_test.py:677-698` | closed |
| T-03-12 | Tampering | replay overwriting outputs | medium | mitigate | `_refuse_existing` (`:1214-1218`) on all four outputs; test `val02_test.py:691-698` | closed |
| T-03-13 | Repudiation (misattribution) | naive numbers read as live | medium | mitigate | `naive_replay` label (`:1120,1383-1390`); counterfactual wording in `tables.md:215`; fidelity 2016 compared, 0 mismatches | closed |
| T-03-14 | Tampering (anti-peeking) | real_data_validation.py | high | mitigate | As T-03-03; VAL-02 uses the `city_pipeline` trace only | closed |
| T-03-15 | Information disclosure | tests → providers/env | low | mitigate | `test_replay_never_touches_the_network` (`val02_test.py:706-726`) | closed |
| T-03-16 | Tampering | analysis input archive | medium | mitigate | Hash gate before analysis (`03-04-SUMMARY.md:101`); re-verified; self-checks 0 | closed |
| T-03-17 | Repudiation | go/no-go authorship | high | mitigate | At `431c7ec` the Decision section held only "Pending owner decision."; decision recorded in `614e395` | closed |
| T-03-18 | Information disclosure | committed tables/doc | low | mitigate | Aggregates only; G6 trip list capped at 50 per city with redacted text; credential grep 0 hits | closed |
| T-03-19 | Tampering (misreporting) | doc numbers | medium | mitigate | All 278 `tables.md` rows appear verbatim in the doc | closed |
| T-03-20 | Spoofing / Repudiation | VAL-03 signature | high | mitigate | `checkpoint:decision gate="blocking-human"`, no `auto_select`; signed "Aaron Phan, 2026-10-21"; owner confirmed at UAT test 1 | closed |
| T-03-21 | Tampering | owner's wording | medium | mitigate | Doc blockquote matches the SUMMARY quote word for word | closed |
| T-03-22 | Elevation of privilege | Phase 4 start on a no-go | high | mitigate | Phase 4 sentence at `real_data_validation.md:886`; Blockers entry in STATE.md | closed |
| T-03-SC | Tampering | package installs | low | accept | See Accepted Risks Log AR-03-02 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

### Residual findings (non-blocking, not counted in threats_open)

| Ref | Threat | Finding | Action |
|-----|--------|---------|--------|
| CR-01 | T-03-01 | `_SECRET_PAIR` is a shape denylist: dict, JSON, quoted, header (`Authorization: Bearer`, `X-Api-Key`) and `%3D`-encoded forms pass unchanged; a value containing `,` `;` `)` leaks its tail | Fix before the post-NO-GO re-validation reuses this code: also redact the known secret values from the environment, and widen the pattern |
| WR-01 | T-03-01 | `backfill_archive.py:207` writes unredacted error text (`msg[:120]`) to the log CSV (pre-existing line, commit `151aac26`) | Use one redacted string for both log and trace |
| — | informational | `dlr_orchestrator.py:161` logs the raw exception to the console file (pre-existing; console hashed in the manifest, 0 credential hits) | Route through the same redaction when CR-01 is fixed |
| WR-02, WR-04 | T-03-02 | A torn trace line crashes the analysis; an interrupt can leave a step archived but untraced. Both fail visibly (`JSONDecodeError`, `no_trace > 0`); the real run had 0 untraced steps | Track in `03-REVIEW-DISPOSITION.md` |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-10 | Provider quota exhaustion or a multi-hour run failing midway: a smoke run goes first, the backfill skips archived steps on resume (`backfill_archive.py:182`), and NSRDB circuit-breaks after 3 failures (`observation_composer.py:78`) | Plan-time disposition (03-02-PLAN threat model) | 2026-10-21 |
| AR-03-02 | T-03-SC | No package was installed in this phase; no dependency file changed in `01f46c1..HEAD`; the only subprocess is a fixed-argv `git` call with no shell (`real_data_validation.py:1463`) | Plan-time disposition (03-01..03-05 PLAN threat models) | 2026-10-21 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-21 | 23 | 23 | 0 | gsd-security-auditor (ASVS L1; L2 depth on T-03-01) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-21
