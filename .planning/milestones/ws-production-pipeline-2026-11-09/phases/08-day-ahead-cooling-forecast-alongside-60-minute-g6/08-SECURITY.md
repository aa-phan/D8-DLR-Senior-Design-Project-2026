---
phase: "08"
slug: "day-ahead-cooling-forecast-alongside-60-minute-g6"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-09"
---

# Phase 08 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Model and band files on disk → process holding DB URL and provider secrets | joblib files are pickles; loading runs code. Hashes are checked against the manifest before any load or parse | Model pickles, band JSON |
| Repository modules → protocol rules | Day-ahead code must not read embargoed FRESH outcomes or compute skill statistics | TEST-window rows only |
| Day-ahead child → runner exit code and logs | A child failure, hang or noisy output must not change the ratings job's result or leak secrets into logs | Exit code, redacted text |
| Row values → SQL | City and timestamps reach the database through bound parameters only | Forecast rows, live residual pairs |
| Owner admin connection → production schema and grants | Two migrations: the private store, then the read-only exposure and alarm | DDL, grants, `assert_fresh` |
| Anon (publishable key) → PostgREST → public schema | Three new readable objects; no write privilege or policy | Day-ahead table and two views |
| Owner's .env / publishable key → verify scripts and examples → committed evidence | URL and keys travel only in the apikey header and are never printed or committed | Check results, counts |
| Local main → origin/main (public repo, hourly CI with secrets) | Owner-approved, rehearsed fast-forward pushes only | Code, docs, examples |
| Docs and examples → consumers' decisions | The day-ahead value must never be read as the live or a validated rating | Label, lead time, band notes |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-08-01 | Tampering / Elevation | cooling model load in day_ahead_forecast.make_model_loader | high | mitigate | hash check before joblib.load (`forecast_conductor_refit.py:336-385`); `day_ahead_forecast_test.py:519,557` | closed |
| T-08-02 | Tampering | data/day_ahead/day_ahead_bands_v1.json via load_verified_band | medium | mitigate | hash-then-parse (`day_ahead_band.py:214-240`); tamper test `day_ahead_forecast_test.py:208` | closed |
| T-08-03 | Tampering | insert_row / existing_targets SQL | medium | mitigate | bound params + `contract.INSERT_COLUMNS` (`day_ahead_forecast.py:169-175,285-299`); city CHECK | closed |
| T-08-04 | Information disclosure (protocol) | band builder reading outcomes after 2026-09-29 | high | mitigate | TEST window refusal (`day_ahead_band.py:115-118`); `day_ahead_band_test.py:126,132` | closed |
| T-08-05 | Denial of service | dlr_live_run.run_live day-ahead stage and main() output | high | mitigate | exit code fixed first (`dlr_live_run.py:628-633`); guarded stage, kill timeout, 60 s floor; isolation tests | closed |
| T-08-06 | Information disclosure | classify_day_ahead reasons, step summary, pipeline_run.day_ahead | high | mitigate | `redact` (`dlr_live_run.py:182-213`), `_emit` defang; planted-secret tests | closed |
| T-08-07 | Denial of service | rating-stage pipeline_run writes vs a missing day_ahead column | medium | mitigate | `build_run_row` has no day_ahead key; separate write (`live_run_log.py:147-184`); migration before push | closed |
| T-08-08 | Tampering (integrity of a published value) | band_for live branch | medium | mitigate | D-08 filters, 60-pair minimum, straddle (`day_ahead_band.py:281-337`); filter tests | closed |
| T-08-09 | Tampering | live_pairs SQL | low | mitigate | one bound-parameter statement on the writer connection (`day_ahead_band.py:281-311`) | closed |
| T-08-10 | Tampering | dlr_writer privileges on public.day_ahead_forecast | medium | mitigate | select+insert only; on conflict do nothing; 42501 test `day_ahead_migration_test.py:357` | closed |
| T-08-11 | Information disclosure | reasons from providers and the database | high | mitigate | `_redact` (`dlr_day_ahead.py:100-122`); no free-text column; `dlr_day_ahead_test.py:407` | closed |
| T-08-12 | Denial of service | a hung provider call in the child | medium | mitigate | kill timeout; autocommit; catch-up and idempotent tests | closed |
| T-08-13 | Information disclosure | anon reading the table before the expose step | medium | mitigate | revoke all from anon/authenticated (store migration :71); `day_ahead_migration_test.py:412` | closed |
| T-08-14 | Tampering / Elevation | check_day_ahead strict load | high | mitigate | presence+sha256 before load (`dlr_live_check_models.py:213-243`); pre-flight step has no secrets | closed |
| T-08-15 | Denial of service | pre-flight exit code | high | mitigate | day-ahead tier guarded, exit code from live models first (`dlr_live_check_models.py:308-358`) | closed |
| T-08-16 | Denial of service | circular import between the pre-flight and the refit module | high | mitigate | lazy imports; fresh-interpreter import-order tests | closed |
| T-08-17 | Information disclosure | day_ahead_verify.py output and JSON | high | mitigate | `_clean`/`_clean_object` (`day_ahead_verify.py:164-204,724-729`); hostile-row test | closed |
| T-08-18 | Tampering | day_ahead_verify.py session | medium | mitigate | `begin_read_only` + rollback; write-refused test `day_ahead_verify_test.py:471` | closed |
| T-08-19 | Repudiation | runbook instructions vs code | low | mitigate | `dlr_live_runbook_test.py:147` pins section 17 to the code | closed |
| T-08-20 | Tampering | applying the wrong set (for example an expose migration early, or a partial apply) | high | mitigate | 08-07 SUMMARY: one file applied, store 10/10, exposure 18/18, second dry run empty | closed |
| T-08-21 | Tampering | an applied migration edited afterwards | medium | mitigate | sha256 pin `day_ahead_migration_test.py:38-40`; hash re-verified | closed |
| T-08-22 | Information disclosure | project URL, reference or key in the committed note or SUMMARY (public repo) | high | mitigate | stand-ins only in 08-07 PREFLIGHT/SUMMARY; shape scan clean | closed |
| T-08-23 | Tampering | pushing an unrehearsed or different commit | high | mitigate | rehearsal at `38f438f`, owner `approve-push`, fast-forward confirmed | closed |
| T-08-24 | Denial of service | the stage harming live ratings after the push | high | mitigate | exit code first; first run 42543631399 green; rollback in 08-08 PUSH-NOTE | closed |
| T-08-25 | Information disclosure | evidence JSON or SUMMARY leaking the writer URL | high | mitigate | redaction; evidence JSON grep clean | closed |
| T-08-26 | Information disclosure | views bypassing RLS | medium | mitigate | security_invoker views, select-only policy; `day_ahead_expose_test.py:134,536` | closed |
| T-08-27 | Tampering | anon writes through the new table or views | high | mitigate | revoke all, grant select only, no write policy; anon/authenticated write tests | closed |
| T-08-28 | Denial of service | alarm URL broken by an assert_fresh overload (HTTP 300) | high | mitigate | `create or replace`, same signature; one `pg_proc` row test; `verify_exposure.sql:289` | closed |
| T-08-29 | Denial of service | false alarm storm toward cron-job.org's 25-failure auto-disable | medium | mitigate | armed only by a row; precondition all cities `none_due` (08-11) | closed |
| T-08-30 | Information disclosure | new and edited docs | high | mitigate | `day_ahead_consumer_docs_test.py:200`; docs shape scan clean | closed |
| T-08-31 | Information disclosure | day_ahead_verify.py --check-rest output and JSON | high | mitigate | `config_from_env` refuses secret keys; `redact_rest`; tests `day_ahead_verify_test.py:797,808` | closed |
| T-08-32 | Tampering | the live write-refusal probe changing data | low | mitigate | year-2000 sentinel; recovery SQL printed, never run; tests | closed |
| T-08-33 | Repudiation (contract) | consumers reading the value as validated or as a 24 h lead | medium | mitigate | `rest_api_doc_test.py:387,400` pin label and band notes to the contract | closed |
| T-08-34 | Tampering | exposing before the first slot is verified, or a changed contract | high | mitigate | 08-11 PREFLIGHT; contract unchanged since `14eb365` | closed |
| T-08-35 | Tampering | warning text parsed as a workflow command | low | mitigate | escape %, CR, LF (`dlr_live_check_models.py:273-285`); tests | closed |
| T-08-36 | Denial of service | alarm starting red after the apply | medium | mitigate | armed only by a row; runbook section 14 test | closed |
| T-08-37 | Information disclosure | live evidence or SUMMARY leaking the URL or key | high | mitigate | evidence JSON holds counts only; grep clean | closed |
| T-08-38 | Tampering | the applied expose migration edited later | medium | mitigate | sha256 pin `day_ahead_expose_test.py:35-37`; hash re-verified | closed |
| T-08-39 | Information disclosure (protocol) | every backend/*day_ahead*.py module, including ones added after 08-01 | high | mitigate | run-time glob of `backend/*day_ahead*.py` (text and imports) `day_ahead_band_test.py:241-255` | closed |
| T-08-40 | Information disclosure | the three examples and four docs | high | mitigate | examples read only URL + publishable key, apikey header; `example_read_ratings_test.py:344,369` | closed |
| T-08-41 | Tampering | examples issuing writes | medium | mitigate | GET/HEAD only, no body; `example_read_ratings_test.py:344` | closed |
| T-08-42 | Repudiation (misuse) | a consumer treating the value as the live rating or as validated | medium | mitigate | all three examples print the label and the not-live-rating line (curl.sh fixed in `49131d4`); handoff docs carry the phrases | closed |
| T-08-43 | Information disclosure | publishing the examples and docs before the expose step is verified (D-17) | medium | mitigate | nothing pushed before expose; REST 8/8 then publishing push (08-11) | closed |
| T-08-44 | Denial of service | breaking PSS/E's existing read path on an old interpreter | medium | mitigate | Python 3.7 grammar, stdlib only; live run on 3.9.6 `-I` | closed |
| T-08-45 | Tampering | publishing examples that fail against the live views (D-18) | medium | mitigate | four live example runs exit 0 before the publishing push (08-11) | closed |
| T-08-SC | Tampering | npm/pip/cargo installs | low | accept | accepted: no package installed; no dependency manifest changed in `01c383d..HEAD` | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-08-01 | T-08-SC | No package is installed by any Phase 8 plan; supabase-js is reused outside the repo from the 06-11 approved install. Auditor confirmed no dependency manifest changed in `01c383d..HEAD` | Plan registers (08-01..08-12) | 2026-11-09 |

---

## Audit Notes

- **T-08-42 closed during this audit.** The auditor found `curl.sh` printed the "not the live rating" line only in a header comment. Commit `49131d4` adds a "Day-ahead note" section that prints the label and that line, matching the Python and JS examples.
- **Secret-scan regression fixed.** The WR-01 review fix (`1d090de`) added a literal fake connection string to `backend/tests/day_ahead_band_test.py`, which made `secret_scan_test.py::test_tracked_files_hold_no_credentials` fail. Commit `1047814` assembles it at run time like the sibling tests. The scan passes again.
- **Owner-local exact-value scan not run.** `test_tracked_files_hold_no_real_project_values_from_env` needs the real values exported in a shell and was skipped in every recorded run. Shape-pattern scans and evidence-file greps stand in for it.
- **Verbal confirmations.** The owner confirmed the dry run and push of both migrations verbally (08-07, 08-11). The applied state is shown by the SQL checks and the second dry run, not by pasted output.
- **For a possible L2 pass:** in the frozen-model branch the hash is checked, then `load_correction_model` re-reads the file; the refit branch unpickles the exact hashed bytes. Acceptable at L1 on a CI checkout.
- **WR-05 workflow** (`day_ahead_manifest_check.yml`, added after the register): `contents: read`, no secrets, `pull_request` (not `pull_request_target`), `persist-credentials: false`. No new attack surface.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-09 | 46 | 46 | 0 | gsd-security-auditor (sonnet), T-08-42 closed by orchestrator fix `49131d4` |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-09
