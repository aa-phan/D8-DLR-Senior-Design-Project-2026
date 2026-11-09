---
phase: "07"
slug: "per-city-conductors-shadow-refit-and-early-model-selection"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-11-08"
---

# Phase 07 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Signed protocol → evaluation code | The v4 signing copy fixes instants, thresholds and rules; code constants must match it and FRESH runs require the signature | Registry values, signature line |
| FRESH outcomes → anyone before signing / repeated reads | One-shot, signed, instant-gated FRESH reads | Predicted-vs-truth outcomes on or after 2026-09-30 |
| Model artifacts on disk → joblib.load | Refit and frozen artifacts are deserialized; hashes checked against manifests first | Pickled models (code-execution capable) |
| TEST/FRESH rows → model fits | Fits restricted to train/validation rows; leak assertions on every frame | Cached weather frames |
| Owner decisions → records | Verbatim words, name and UTC date; executor is recorder only | GO / SEL-04 decisions |
| Local repo → origin/main and live DB | Owner-reviewed fast-forward push; anon has no write privilege | Code, live rating rows |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-07-01 | Tampering | COND-02 golden | high | mitigate | `golden_shadow_capture.py` import-path assertion from `git archive d71c501`; golden `92a923b` precedes first backend edit; `test_golden_has_power` | closed |
| T-07-02 | Tampering | config.PRODUCTION_CONDUCTORS | medium | mitigate | Closed-set lookup, inclusive ranges, completeness, sources (`config.py:339-396`); see residual WR-07 | closed |
| T-07-03 | Repudiation | rating identity for backfill rows | medium | mitigate | `rating_identity.py:142` getattr fallback; `rating_identity_test.py:222-236` | closed |
| T-07-04 | Repudiation | v4 thresholds and dates | high | mitigate | `protocol_v4_registry_test.py` parity | closed |
| T-07-05 | Tampering | FRESH outcomes during drafting | high | mitigate | Anti-peeking statement in signing copy; all evidence dirs post-date `fbe3948` | closed |
| T-07-06 | Tampering | data/shadow/models | high | mitigate | `refit_dir` refuses frozen dir (`forecast_conductor_refit.py:99-117`); 12/12 frozen hashes OK | closed |
| T-07-07 | Tampering | joblib load of refit/frozen artifacts | high | mitigate | Hash-then-load in `_load_verified_refit` and headline loader (`forecast_conductor_refit.py:327-385`); see residual WR-04 | closed |
| T-07-08 | Information disclosure | TEST/FRESH rows reaching a fit | high | mitigate | `prepare_fit_frame` + `assert_no_test_leak` | closed |
| T-07-09 | Tampering | shadow modules picking up production resolver | high | mitigate | `test_caller_split` (AST over 11 shadow modules); COND-02 golden | closed |
| T-07-10 | Repudiation | identity change without label change | medium | mitigate | `RATING_CONFIG_VERSION` bump `9a5f1db` before any read, retrain or push | closed |
| T-07-11 | Repudiation | v4 thresholds in code | high | mitigate | Registry parity; module committed before read 1; non-default params refused in FRESH | closed |
| T-07-12 | Tampering | override path in check_guard | high | mitigate | Override refused for FRESH (`forecast_shadow_eval_core.py:523-527`); tested | closed |
| T-07-13 | Repudiation | second read under retired v3 dates | high | mitigate | Retired instant refused; per-round one-shot subroots; see residual CR-01 | closed |
| T-07-14 | Information disclosure | FRESH outcomes before signing | high | mitigate | `v4_signed()` in `check_guard` before any network call; see residual WR-03 | closed |
| T-07-15 | Tampering | --vetoes file | high | mitigate | Structure + source-report sha256 checks; hash recorded in report; flags independently cross-checked; see residual WR-02 | closed |
| T-07-16 | Repudiation | live-system check deciding | medium | mitigate | Live label pick None; swapped sources refused | closed |
| T-07-17 | Tampering | forecast_used_by_g6 semantics | medium | mitigate | Trace-only keys; no store/migration diff | closed |
| T-07-18 | Denial of service | naive fallback raising | medium | mitigate | try/except in `city_pipeline.py:144-151`; tested | closed |
| T-07-19 | Tampering | refit artifacts at read time | high | mitigate | Manifest pre-check before network and before load; `scored_artifacts` match manifests (24/24, both reads) | closed |
| T-07-20 | Repudiation | secondary pooled with headline | medium | mitigate | Separate family, label "secondary", pick None | closed |
| T-07-21 | Information disclosure | FRESH-dated cache read by TEST provider | high | mitigate | Path check, frozen-window name, row-date assertion | closed |
| T-07-22 | Repudiation | code constants vs signed values | high | mitigate | Registry parity test; unmapped keys fail | closed |
| T-07-23 | Repudiation | ABLATION/TEST before signing | high | mitigate | TEST CLI refuses (`forecast_test_split_score.py:198`); ABLATION CLI refusal added in `3aa7bf4` with `test_main_when_unsigned_exits_2_before_any_work` | closed |
| T-07-24 | Tampering | Power Systems values | medium | mitigate | Owner-cited values, range checks, divergence test, version bump; see residual WR-07 | closed |
| T-07-25 | Tampering | refit artifacts without manifest | high | mitigate | `write_refit` regenerates manifest; one commit `a933959`; `shasum -c` OK; read pre-check; see residual WR-05 | closed |
| T-07-26 | Tampering | early or repeated read | high | mitigate | Instant, one-shot per round root, no override, clock precondition, owner go; one `run_started.json` per round; see residual CR-01 | closed |
| T-07-27 | Information disclosure | secrets in evidence | low | accept | Public Open-Meteo responses only (verified) | closed |
| T-07-28 | Repudiation | decision record (read 1) | medium | mitigate | `decision_record.md` verbatim, name, UTC date, departure labelled | closed |
| T-07-29 | Denial of service | models committed without manifest | high | mitigate | `e0a00a9` holds both; check mode OK | closed |
| T-07-30 | Information disclosure | FRESH rows in retrain or re-run | medium | mitigate | Complete past years only; re-run window ends 2026-09-28T23:00Z | closed |
| T-07-31 | Tampering | read 2 unauthorised or under changed config | high | mitigate | Recorded no-pick, owner go after preflight, config equality, per-round guard; see residuals CR-01, WR-01 | closed |
| T-07-32 | Repudiation | final decision record | medium | mitigate | `decision_record.md` Read 2 section | closed |
| T-07-33 | Repudiation | GO signed without checklist | medium | mitigate | Checklist `c028af2` precedes GO `bbbe6a0` | closed |
| T-07-34 | Spoofing | label claims more than validated | medium | mitigate | `RATING_BASIS` keeps conductor basis; go-forward-only; no relabel SQL | closed |
| T-07-35 | Tampering | unreviewed push | high | mitigate | Owner "push"; fast-forward `e970549`→`682801d`, never forced | closed |
| T-07-36 | Elevation of privilege | stored-row UPDATE | high | mitigate | No UPDATE prepared or run; anon has no write privilege (migrations) | closed |
| T-07-37 | Information disclosure | credentials in output | high | mitigate | Record grep for connection strings returns 0; see residual WR-06 | closed |
| T-07-38 | Tampering | schema doc concurrent edit | medium | mitigate | `9a5f1db` touches two sections; `supabase_schema_doc_test` | closed |
| T-07-39 | Tampering | B2 change leaking into shadow reference | high | mitigate | Hunks only in `city_training_frame`; shadow sources unchanged | closed |
| T-07-40 | Tampering | read inputs changed between preflight and run | high | mitigate | Wave ordering; clean-tree check in `read1_preflight.json`, re-asserted | closed |
| T-07-SC | Tampering | package installs | low | accept | No dependency manifest changed in Phase 7 (verified) | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-07-01 | T-07-27 | Evidence holds public Open-Meteo responses only; no credential is used by either read command (premise verified by audit) | plan register (07-12, 07-15) | 2026-11-08 |
| AR-07-02 | T-07-SC | No package installed or added in Phase 7; all imports stdlib, pinned or local (premise verified by audit) | plan register (all plans) | 2026-11-08 |

---

## Known Residuals (deferred — must be fixed before any new signed protocol or FRESH read)

Owner decision 2026-11-08 (verify-work 07): these weaken mitigations that pass at ASVS L1 and had no effect on the
spent v4 reads. They are deferred, not accepted permanently: fix them before any new signed protocol or FRESH read.

| Finding | Threats | Weakness | Why the v4 reads were unaffected |
|---------|---------|----------|----------------------------------|
| CR-01 | T-07-13, T-07-26, T-07-31 | One-shot guard keyed on `--evidence-root/<round>`; a different root allows a repeat FRESH run; not atomic | Exactly one `run_started.json` per round and row source; `prior_fresh_runs` empty; owner rule forbids further FRESH reads without a new protocol. Fix must still allow the 07-15 worktree case (compare realpaths, don't ban the flag) |
| WR-01 | T-07-31 | Read-2 "read 1 named no winner" precondition is process-only | `read2_preflight.json` recorded no pick; read 1 report `pick None` |
| WR-04 | T-07-07 | Drake-parity path (`forecast_shadow_confirm.py:1113-1119`) loads frozen artifacts without a hash check | AUSTIN differs, so both reads used the verified loader; 24/24 scored artifacts match manifests |
| WR-02 | T-07-15 | Veto flags not bound to source reports in code | All six flags independently matched source reports; hashes match |
| WR-03 | T-07-14, T-07-23 | Three "is v4 signed" predicates; FRESH guard uses the weakest | Signing copy has exactly one complete signature line |
| WR-05 | T-07-25 | `write_manifest` re-blesses every `.joblib` in the directory | Refit manifest and artifacts in one commit; `shasum -c` OK |
| WR-06 | T-07-37 | Credential regex misses key-like names in Actions log path (pre-existing Phase 5) | All four workflow secrets are exact-value masked first |
| WR-07 | T-07-02, T-07-24 | Conductor ranges too wide to catch unit slips | No current value out of band |

Unregistered flag (informational): 07-09 `file_access`, `late_descriptive_status` reads only `rating_config_version`
from the newest v4-read1 `report.json`; the round has never run and is refused while the version is unchanged.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-08 | 41 | 40 | 1 (T-07-23) | gsd-security-auditor (ASVS L1; 738 tests passed, 3 skipped) |
| 2026-11-08 | 41 | 41 | 0 | orchestrator, after `3aa7bf4` closed T-07-23 (53 ablation tests pass) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-08
