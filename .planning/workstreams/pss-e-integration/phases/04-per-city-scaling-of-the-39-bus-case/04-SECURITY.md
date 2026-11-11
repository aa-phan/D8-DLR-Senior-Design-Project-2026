---
phase: "04"
slug: "per-city-scaling-of-the-39-bus-case"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-11"
---

# Phase 04 - Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> This is an automated audit (gsd-security-auditor, ASVS level 1, block on high), run read-only against the repository tree. It is not a human security review, and it could not see the laptop's private files, the real case or the real targets.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| private mapping file -> job | the per-city targets live in a private file on the laptop, outside the repository | city load and generation targets (sensitive, from Power Systems' files) |
| job -> PSS/E (`psspy`) | the job applies targets with its own scaling call; it never runs a recorded `.idv` or response file | scaling arguments, totals read back |
| laptop output -> chat -> repository | anything pasted can be committed | probe rows, counts, run figures |
| probe write check -> case copy | the case changes in memory during the check and is reloaded | in-memory case state (never saved) |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-04-01 | Information disclosure | example mapping and tests | high | mitigate | only synthetic targets in the committed example and the tests; the example is marked placeholder; secret scan passes | closed |
| T-04-02 | Tampering | mapping scaling block | medium | mitigate | strict parser: closed key set, positive finite numbers only, size cap, duplicate-key and NaN refusals | closed |
| T-04-03 | Information disclosure | mapping refusal text | medium | mitigate | messages name the field, never the submitted value | closed |
| T-04-04 | Elevation of privilege | job and PSS/E surface | high | mitigate | no `run*` function in the call surface; unknown call names refused; unknown configuration keys refused; no setting can name a script | closed |
| T-04-05 | Information disclosure | adapter errors | medium | mitigate | errors carry function, ierr and meaning only; bad targets refused before any call | closed |
| T-04-06 | Tampering | scaling layout | high | mitigate | one layout table; factor bounds checked before the call and the read-back after it, both before the solve; probe row `scale_to_target`; shown working on the laptop | closed |
| T-04-07 | Tampering | cross-city leakage | high | mitigate | a fresh case load per city; ratings applied to that city only | closed |
| T-04-08 | Tampering | Power Systems' case file | high | mitigate | saves refused onto the loaded file; solved copies go to a private temporary folder removed afterwards; case hash unchanged in tests | closed |
| T-04-09 | Denial of service | kW-for-MW typo, ignored scaling | medium | mitigate | tolerance and factor bounds, read-back before the solve | closed |
| T-04-10 | Information disclosure | stored rows and run record | medium | mitigate | details carry basis and method only; no target or realised total stored | closed |
| T-04-11 | Repudiation | partial result set under a failed run | high | mitigate | one combined failure before any result is built; a failed run has no result rows; a complete run must have one dispatch and one margin row per city | closed |
| T-04-12 | Information disclosure | error text, logs, dry-run output | medium | mitigate | the dry run prints counts only; the failure line is redacted and scrubbed; tests search output for the synthetic targets | closed |
| T-04-13 | Denial of service | four studies exhaust the time budget | low | mitigate | one shared budget; cities that cannot start are marked not attempted | closed |
| T-04-14 | Tampering | probe write check | high | mitigate | the case is reloaded in a `finally` block and the totals compared; the probe never saves | closed |
| T-04-15 | Information disclosure | probe output and pasted notes | medium | mitigate | probe rows are figure-free; identifiers only with an explicit flag; runbook pasting rules | closed |
| T-04-16 | Elevation of privilege | runbook instructions | high | mitigate | the runbook says never to open, run or paste a recorded city script | closed |
| T-04-17 | Information disclosure | laptop record | high | mitigate | the record holds positions, outcomes and counts only; an identifier gate and the secret scan pass | closed |
| T-04-18 | Elevation of privilege | laptop session | high | mitigate | same runbook text and test as T-04-16; the record never mentions opening a recorded script | closed |
| T-04-19 | Tampering | known-wrong layout read as evidence | medium | mitigate | the first probe failure was recorded, diagnosed and fixed (commit 5a30c63), not read as evidence | closed |
| T-04-SC | Tampering | package installs (one row in each of the six plans) | low | accept | no package was installed; no dependency manifest changed since the phase began; the import allow-list test passes | closed |

*Status: open · closed · open - below high threshold (non-blocking)*
*Severity: critical > high > medium > low - only open threats at or above `workflow.security_block_on` (high) count toward `threats_open`*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-1 | T-04-01 (history) | The totals of PSS/E's public 39-bus example case remain in two pushed commits (6e59341 and 1f60eb5, in the phase context and research notes) and were removed from the tree in 128cf3d. They belong to a public example case, not to Power Systems. History was not rewritten. The live mitigation is the tree rule: no city target and no case total in the tree. | the user | 2026-11-11 |
| AR-2 | T-04-SC | Nothing was installed in any plan of this phase; accepted at plan time because there was nothing to install. | plans 04-01 to 04-06 | 2026-11-10 |

*Accepted risks do not resurface in future audit runs.*

---

## Observations (not register items)

- **Verification report wording (low, non-blocking).** The second and third verification reports described their search patterns using the leading digits of the example case's totals. That narrows the totals more than the tree rule intends. The next verification pass regenerates the report and has been told to describe the patterns without digits.
- **Existing behaviour from Phase 2 (info).** Rating-application messages can put mapped branch keys (bus numbers) and per-circuit MVA into a stored error or the dry-run failure line. They are not city targets, and the runbook's pasting rules already forbid pasting bus numbers.
- **Laptop-side finding (operational, outside the repository).** A stray configuration line holding another database role's connection string was found on the laptop and removed from the configuration and its backups. The audit could not verify that from here. The launcher refuses an unknown configuration key, which is what caught it. Whether that credential needs rotating is the owner's decision if it was ever shared.
- **Could not be verified from the repository:** the private mapping, the real case, the real targets, what was pasted into chat, whether anyone opened a recorded script on the laptop, and the database-backed tests behind T-04-11 and T-04-12 (the orchestrator ran those green separately).

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-11 | 25 | 25 | 0 | gsd-security-auditor (read-only), written up by the orchestrator |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in the Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-11 (automated audit; no human security review)
