---
phase: "05"
slug: "scheduled-live-runs"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
created: "2026-10-26"
---

# Phase 05 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Built from the `<threat_model>` blocks of 05-01 to 05-08 and the SUMMARY Threat Flags. Evidence is
> L1 (code read and grep, plus the named tests, which pass on the post-review tree: 338 tests across
> the phase's test files on 2026-10-26).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| cron-job.org → GitHub API | Hourly `workflow_dispatch` POST with a fine-grained token | Dispatch token (secret), `fault_city` input (untrusted) |
| Workflow inputs → runner | `inputs.fault_city` reaches `dlr_live_run.py` | Untrusted string, env mapping only |
| Runner → child processes | One orchestrator child per city | Provider credentials (secret), child stdout/stderr |
| Runner → Actions log and step summary | Public logs (repository is public since 2026-10-24) | Error text, which may carry credentials before redaction |
| Runner → Supabase Postgres | `SUPABASE_DB_URL`, `production` environment only | `city_rating`, `pipeline_run` rows |
| PostgREST anon/authenticated → tables | Consumer access path | `pipeline_run`, `city_rating` (no grants) |
| Git → runner | Committed joblib pickles loaded on the runner | Code-executing artifacts |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation | Status |
|-----------|----------|-----------|----------|-------------|------------|--------|
| T-05-01 | Tampering / Elevation | `fault_city` input | high | mitigate | `DLR_LIVE_FAULT_CITY: ${{ inputs.fault_city }}` env mapping only (`dlr_live.yml:77`); `run_live` and argparse reject values not in `config.LOCATIONS` (`dlr_live_run.py:373,518`); `test_every_required_secret_is_mapped_and_inputs_never_reach_a_run_script`, `test_unknown_fault_city_is_a_usage_error` | closed |
| T-05-02 | Information disclosure | child stderr, step summary, record `error` | high | mitigate | `redact()` (`dlr_live_run.py:158`) plus `_defang` for workflow commands; WR-03 fix routes child streams through `redact()`; `test_redact_removes_secret_values_query_credentials_and_db_urls`, `test_child_streams_are_redacted_before_they_reach_the_log`, `test_step_summary_lists_cities_in_order_with_redacted_errors` | closed |
| T-05-03 | Denial of service | hung provider call | high | mitigate | `CITY_TIMEOUT_S = 300` (`dlr_live_run.py:75`); `timeout-minutes: 30`; concurrency `dlr-live`, `cancel-in-progress: false`; `test_a_hung_city_is_killed_at_the_timeout_and_the_rest_still_run` | closed |
| T-05-04 | Elevation of privilege | GITHUB_TOKEN scope | medium | mitigate | `permissions: contents: read` (`dlr_live.yml:25-26`); workflow test | closed |
| T-05-05 | Information disclosure | `load_dotenv()` in tests | medium | mitigate | `load_dotenv()` only under `if __name__ == "__main__"` (`dlr_live_run.py:539-542`) | closed |
| T-05-06 | Information disclosure | `.env` loaded during tests (orchestrator) | medium | mitigate | `test_dotenv_is_loaded_only_when_run_as_a_script` | closed |
| T-05-07 | Repudiation | backfill gate counts | medium | mitigate | `test_backfill_counts_gate_failures_the_monitor_logs`, `test_backfill_logs_one_row_per_city_and_per_error_and_counts_printed_gates` | closed |
| T-05-08 | Tampering (data quality) | NSRDB skip | medium | mitigate | Current-UTC-year rule; `test_nsrdb_unpublished_year_boundaries`, `test_past_year_window_still_calls_nsrdb_and_breaker_still_opens` | closed |
| T-05-09 | Information disclosure | `forecast_error` text | low | accept | See Accepted Risks AR-01 | closed |
| T-05-10 | Tampering | shadow collection via `dlr_pipeline` | medium | mitigate | 05-02 SUMMARY: empty diff on shadow modules/workflow; verifier re-checked `git diff --stat fde51cd..HEAD` empty | closed |
| T-05-11 | Information disclosure | `pipeline_run` error fields | high | mitigate | Runner redacts first; `build_run_row` truncates (`live_run_log.py:121-124`); `test_run_row_error_text_is_redacted_and_bounded` | closed |
| T-05-12 | Information disclosure | `pipeline_run` via PostgREST anon | high | mitigate | No grant changed; verifier ran `has_table_privilege` for anon/authenticated (all false), RLS on, only `dlr_writer_all` policy | closed |
| T-05-13 | Tampering (SQL injection) | `upsert_run_row` | high | mitigate | Bound parameters only; `test_values_are_bound_parameters_never_sql_text` with quote and `drop table` strings | closed |
| T-05-14 | Repudiation | run-log write failure | medium | mitigate | Failure logged redacted and exit 1 (`dlr_live_run.py:428`); step summary lists every city | closed |
| T-05-15 | Tampering (lost record) | children overwriting the run row | medium | mitigate | Children get `--no-run-row` (`STORE_ARGS`, `dlr_live_run.py:81`); `test_run_row_is_written_at_start_after_each_city_and_at_the_end` | closed |
| T-05-16 | Tampering → Elevation | committed joblib pickles | high | mitigate | SHA-256 manifest checked before any `joblib.load` (`dlr_live_check_models.py:107-139`); `test_tampered_artifact_fails_before_any_load`; `shasum -c` passes | closed |
| T-05-17 | Tampering | unpromoted local retrain | medium | mitigate | Hash mismatch fails the pre-flight step, which runs before "Run live pipeline" (`dlr_live.yml:69`) | closed |
| T-05-18 | Denial of service (silent degradation) | missing model | high | mitigate | Pre-flight fails the job; runner marks failed forecast / missing anomaly model unhealthy (`live_run_log.is_healthy`) | closed |
| T-05-19 | Information disclosure | over-broad `.gitignore` carve-out | medium | mitigate | Per-file `!` lines (`.gitignore:20-29`); `git ls-files data/models` lists exactly the nine paths; training frame, corridor model and bakeoff report still ignored | closed |
| T-05-20 | Information disclosure | models in git history | low | accept | See Accepted Risks AR-02 (rationale updated for the public repository) | closed |
| T-05-21 | Information disclosure | committed text files | high | mitigate | `test_phase5_files_contain_no_secret_values`; 05-06 credential scan of all 904 commits found nothing | closed |
| T-05-22 | Elevation of privilege | cron-job.org dispatch token | high | mitigate | Runbook section 2 prescribes repo-scoped, Actions read/write, expiring token; owner confirmed in 05-UAT test 2 | closed |
| T-05-23 | Denial of service | Actions minutes exhaustion | high | mitigate | Runbook section 12 (measured ~2,880 live + ~600 shadow min / 30 days); owner confirmed usage flat since public in 05-UAT test 1 | closed |
| T-05-24 | Tampering (SQL injection) | window check `fetch_rows` | medium | mitigate | Read-only SELECTs with `%(start)s`/`%(end)s` (`dlr_live_window_check.py:65-71,282`); `test_fetch_rows_binds_parameters` | closed |
| T-05-25 | Repudiation | runbook drift | medium | mitigate | `dlr_live_runbook_test.py` pins runbook constants to the modules and workflow | closed |
| T-05-26 | Tampering | push of unreviewed commits | high | mitigate | 05-06: owner `approve-push`, fast-forward `702a833..d71c501` | closed |
| T-05-27 | Information disclosure | secrets during setup | high | mitigate | Owner entered values; `gh secret list` names only; `SUPABASE_DB_URL` only in environment `production` | closed |
| T-05-28 | Denial of service | Actions minutes exhaustion | high | mitigate | Quota read before go-live (05-06); see T-05-23 | closed |
| T-05-29 | Information disclosure | `pipeline_run` readable by consumers | medium | mitigate | Equivalent evidence via privileges (see T-05-12); live REST refusal to be exercised by Phase 6 plans 06-04 and 06-09 | closed |
| T-05-30 | Elevation of privilege | dispatch token held by cron-job.org | high | mitigate | Fine-grained, single repo, Actions read/write, expiry mid-December 2026; owner confirmed in 05-UAT test 2 | closed |
| T-05-31 | Spoofing / Tampering | unauthorized dispatch with `fault_city` | medium | mitigate | Only token holders and collaborators can dispatch; `fault_city` validated (T-05-01); drill visible as red run and in `pipeline_run.cities_failed` | closed |
| T-05-32 | Tampering (data quality) | drill rows mixed with scheduled rows | low | accept | See Accepted Risks AR-03 | closed |
| T-05-33 | Repudiation | window evidence | medium | mitigate | 05-08 SUMMARY copies checker output verbatim; verifier re-ran the checker (24/24 ok) | closed |
| T-05-34 | Denial of service | minutes overrun found late | high | mitigate | Measured projection recorded at 05-08 sign-off; see T-05-23 | closed |
| T-05-35 | Tampering | docs push | low | mitigate | Owner approval at 05-08, fast-forward only | closed |
| T-05-SC | Tampering | npm/pip/cargo installs | low | accept | See Accepted Risks AR-04 | closed |
| TF-05-06 | Information disclosure | repository made public (05-06 threat flag) | medium | accept | See Accepted Risks AR-05 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01 | T-05-09 | Forecast-path exceptions name a city, a model path and a training command; the runner redacts again before storing | Plan 05-02 threat model | 2026-10-26 |
| AR-02 | T-05-20 | Models encode weather/ampacity relationships with no personal or secret data. The plan-time rationale ("private repo") no longer holds since the repository went public on 2026-10-24; the acceptance stands on the content alone | Plan 05-04 threat model; owner (public flip) | 2026-10-26 |
| AR-03 | T-05-32 | Drill rows are real ratings for three cities at the current slot and overwrite that hour (OD-7); `pipeline_run` marks the drill | Plan 05-07 threat model | 2026-10-26 |
| AR-04 | T-05-SC | No new packages; the workflow installs the existing pinned `requirements.txt` | Plans 05-01 to 05-08 | 2026-10-26 |
| AR-05 | TF-05-06 | Owner made the repository public so Actions minutes are free. Models, data, planning files and history are world-readable; a credential scan of all 904 commits found nothing. Actions logs are public, which is why the WR-03 redaction of child streams was fixed | Owner (05-06) | 2026-10-26 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-26 | 37 | 37 | 0 | gsd-secure-phase (orchestrator, ASVS L1 short-circuit) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-26
