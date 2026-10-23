-- supabase/migrations/20261023000000_city_rating_utc_hour_check_and_run_log_comments.sql
--
-- Production-pipeline Phase 4 code-review fixes IN-06 (hour CHECK) and IN-03 (run-log
-- column comments). Additive follow-up to 20261019000000_create_city_rating.sql, which is
-- already applied to the live project and is never edited.
--
-- Idempotent: the constraint is dropped with `if exists` before it is added, and a comment
-- statement simply replaces the previous text, so the file re-applies cleanly.
--
-- Applied with `supabase db push --db-url ...` by the owner (plan 04-12). It adds no
-- column, grant, policy, role or credential: it changes one CHECK expression and two
-- comments.

-- IN-06: the hour check is evaluated in UTC whatever the session time zone. The original
-- form, valid_time = date_trunc('hour', valid_time), truncates in the session zone, so a
-- session at +05:30 or +05:45 refused valid whole-UTC-hour slots and accepted half-hour
-- ones. Converting to UTC first (valid_time at time zone 'UTC') makes the rule mean the same in Studio, manual
-- corrections and Phase 6 jobs.
alter table public.city_rating drop constraint if exists city_rating_valid_time_hour_ck;
alter table public.city_rating add constraint city_rating_valid_time_hour_ck check ((valid_time at time zone 'UTC') = date_trunc('hour', valid_time at time zone 'UTC'));

-- IN-03: run-log column comments (added with the comment statements below).
