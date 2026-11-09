#!/usr/bin/env bash
# Read the current dynamic line rating of every city, one city's history, and the day-ahead
# forecast, with curl.
#
# 1. The current row of each city from the view latest_rating.
# 2. One city's rows between START and END from the table city_rating, read in pages of 1000
#    rows (the service returns at most 1000 per request), ordered by valid_time ascending so no
#    row repeats or is skipped, after one HEAD request that reads the total row count.
# 3. The day-ahead forecast: the upcoming targets of every city from the view day_ahead_upcoming
#    (the targets issued so far at 00, 06, 12 or 18 UTC; a value appears about 18 h before its target,
#    so at most three per city; ordered by city then target time),
#    then one status row per city from the view day_ahead_status (upcoming_count, is_late and
#    missing_targets). Day-ahead values carry the label
#    day-ahead-24h; engineering-selection; not-validated, are not the live rating, and never gate it.
#
# Environment (the Data Science owner gives you both values; never write them into a file):
#   SUPABASE_URL              the project URL
#   SUPABASE_PUBLISHABLE_KEY  the publishable key, sent as the apikey header (read-only)
# Optional: CITY (default AUSTIN), START and END (UTC timestamps ending in Z).
#
# Only GET and HEAD requests are made; nothing is written anywhere. Rating values are PROVISIONAL
# (see docs/integration/rest-api.md); a row whose status is fallback is a valid published rating.
#
#   export SUPABASE_URL="<value from the DS owner>"
#   export SUPABASE_PUBLISHABLE_KEY="<value from the DS owner>"
#   CITY=MIDLAND START=2026-10-25T00:00:00Z END=2026-11-01T00:00:00Z bash curl.sh
set -euo pipefail

: "${SUPABASE_URL:?set SUPABASE_URL (the Data Science owner gives you the value)}"
: "${SUPABASE_PUBLISHABLE_KEY:?set SUPABASE_PUBLISHABLE_KEY (the Data Science owner gives you the value)}"
CITY="${CITY:-AUSTIN}"
START="${START:-2026-10-25T00:00:00Z}"
END="${END:-2026-11-01T00:00:00Z}"
BASE="${SUPABASE_URL%/}/rest/v1"
PAGE=1000
H=(-H "apikey: ${SUPABASE_PUBLISHABLE_KEY}" -H "Accept: application/json")

echo "== Current rating per city (view latest_rating) =="
curl -fsS "${BASE}/latest_rating?select=city,valid_time,rating_amps,rating_mw,status,fallback_gates,age_minutes,is_stale,is_provisional&order=city" "${H[@]}"
echo

echo "== ${CITY} from ${START} to ${END} (table city_rating, ${PAGE} rows per page) =="
QUERY="city=eq.${CITY}&select=valid_time,rating_amps&valid_time=gte.${START}&valid_time=lt.${END}&order=valid_time.asc"

# One HEAD request: Content-Range looks like "0-0/2500"; the number after the slash is the total.
total=$(curl -fsSI "${BASE}/city_rating?${QUERY}" "${H[@]}" \
          -H "Prefer: count=exact" -H "Range-Unit: items" -H "Range: 0-0" \
        | awk 'BEGIN {FS = "/"} tolower($1) ~ /^content-range/ {gsub(/[[:space:]]/, "", $2); print $2}')
case "$total" in
  ''|*[!0-9]*) echo "could not read the row count from Content-Range (got: '${total}')" >&2; exit 1 ;;
esac
echo "total rows: ${total}"

offset=0
while [ "$offset" -lt "$total" ]; do
  echo "-- rows ${offset} and after --"
  curl -fsS "${BASE}/city_rating?${QUERY}&limit=${PAGE}&offset=${offset}" "${H[@]}"
  echo
  offset=$((offset + PAGE))
done

echo "== Day-ahead forecast: upcoming targets (view day_ahead_upcoming) =="
curl -fsS "${BASE}/day_ahead_upcoming?select=city,valid_time,issued_at,lead_minutes,forecast_amps,forecast_ci_lower_amps,forecast_ci_upper_amps,band_source,band_n,label&order=city,valid_time" "${H[@]}"
echo

echo "== Day-ahead status per city (view day_ahead_status) =="
curl -fsS "${BASE}/day_ahead_status?select=city,next_target_time,upcoming_count,newest_issued_at,missing_targets,is_late&order=city" "${H[@]}"
echo

echo "== Day-ahead note =="
echo "label: day-ahead-24h; engineering-selection; not-validated"
echo "this is not the live rating: it never sets or checks it, and it is not validated"
