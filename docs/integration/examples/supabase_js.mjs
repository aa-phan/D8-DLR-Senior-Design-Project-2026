// Read the current dynamic line rating of every city, and one city's history, with supabase-js.
//
// 1. The current row of each city from the view latest_rating.
// 2. One city's rows between START and END from the table city_rating, in pages of 1000 rows
//    (the service returns at most 1000 per request), ordered by valid_time ascending so no row
//    repeats or is skipped, stopping on an empty page.
//
// Install, in your own project (nothing is installed from this repository):
//   npm install @supabase/supabase-js@2
// Node 22 or newer is needed for current 2.x releases. A browser build needs only fetch.
//
// Environment (the Data Science owner gives you both values; never commit them):
//   SUPABASE_URL              the project URL
//   SUPABASE_PUBLISHABLE_KEY  the publishable key (read-only; safe in client code, but handed
//                             over by the owner rather than committed)
// Optional: CITY (default AUSTIN), START and END (UTC timestamps ending in Z).
//
// Only reads are made. Rating values are PROVISIONAL (see docs/integration/rest-api.md); a row
// whose status is fallback is a valid published rating, not an error.
//
//   SUPABASE_URL=... SUPABASE_PUBLISHABLE_KEY=... node supabase_js.mjs
import { createClient } from '@supabase/supabase-js'

const url = process.env.SUPABASE_URL
const key = process.env.SUPABASE_PUBLISHABLE_KEY
for (const [name, value] of [['SUPABASE_URL', url], ['SUPABASE_PUBLISHABLE_KEY', key]]) {
  if (!value) {
    console.error(`${name} is not set (the Data Science owner gives you the value)`)
    process.exit(2)
  }
}

const CITY = process.env.CITY || 'AUSTIN'
const START = process.env.START || '2026-10-25T00:00:00Z'
const END = process.env.END || '2026-11-01T00:00:00Z'
const PAGE = 1000

const supabase = createClient(url, key)

// (1) the current rating of every city
const current = await supabase
  .from('latest_rating')
  .select('city,valid_time,rating_amps,rating_mw,status,fallback_gates,age_minutes,is_stale,is_provisional')
  .order('city')
if (current.error) {
  console.error(current.error.message)
  process.exitCode = 1
} else {
  console.table(current.data)
  if (current.data.length !== 4) {
    console.error(`expected 4 cities, got ${current.data.length}`)
    process.exitCode = 1
  }
}

// (2) one city over a date range, paging past the 1000-row cap (range is 0-based and inclusive)
const rows = []
for (let from = 0; ; from += PAGE) {
  const { data, error } = await supabase
    .from('city_rating')
    .select('valid_time,rating_amps')
    .eq('city', CITY)
    .gte('valid_time', START)
    .lt('valid_time', END)
    .order('valid_time', { ascending: true }) // unique within one city: no repeated or skipped rows
    .range(from, from + PAGE - 1)
  if (error) {
    console.error(error.message)
    process.exitCode = 1
    break
  }
  if (data.length === 0) break
  rows.push(...data)
}
console.log(`${CITY} rows from ${START} to ${END}: ${rows.length}`)
