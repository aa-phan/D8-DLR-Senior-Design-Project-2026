# Rating database columns in plain language

**What every column the dashboard can read means, why anyone would care, and whether the dashboard shows it**

|              |                                                                                                                                                                                                                                                       |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Audience** | The Software team building the operator dashboard; anyone who needs to explain a column to an operator                                                                                                                                                |
| **Scope**    | Every column the dashboard's read-only key can read: `city_rating` and its view `latest_rating`, `day_ahead_forecast` and its view `day_ahead_upcoming`, and `day_ahead_status`. Tables the key cannot read are listed in ch. 7 and not explained here. |
| **Authority** | This guide explains; it does not define. The exact definitions are in [`rest-api.md`](../../../../docs/integration/rest-api.md), [`city_rating_v1.md`](../../../../docs/data-science/schema/city_rating_v1.md) and [`day_ahead_forecast_v1.md`](../../../../docs/data-science/schema/day_ahead_forecast_v1.md). Where this guide and those documents disagree, they win and this guide is the bug. |
| **Related**  | [`DASHBOARD-REQUIREMENTS.md`](DASHBOARD-REQUIREMENTS.md) decides what the dashboard shows; this guide tells you what each column means.                                                                                                              |

---

## 1. How to read this guide

Each table row explains one column in three steps: what it is in plain words, why it is useful (or why it is not), and where the dashboard uses it. The "Dashboard use" column uses five values, which [`DASHBOARD-REQUIREMENTS.md`](DASHBOARD-REQUIREMENTS.md) ch. 4 defines in full:

| Dashboard use | Meaning |
| --- | --- |
| **Card** | Shown on the city's overview card, visible without a click |
| **Detail** | Shown in the city's detail view, one click away |
| **Tech details** | Shown only in the collapsed "Technical details" section of the detail view, for engineers and troubleshooting |
| **Logic only** | Read by the dashboard's code to decide something (a state, a marker), but never printed as a value |
| **Not used** | The dashboard neither reads nor shows it |

The column names are the database's own names, for developers. Operators never see a column name.

## 2. Words used in this guide

These eight terms keep one meaning through this guide and the requirements document.

| Term | Meaning |
| --- | --- |
| **Rating** | How much electrical current a power line can safely carry right now, in amperes (A). Hot, still, sunny air lowers it; cool air and wind across the wires raise it. |
| **Normal rating** | The fixed, conservative rating a line is given for all conditions. The database calls it the *static rating*. The dashboard says "normal rating" to operators. |
| **Dynamic rating** | A rating calculated every hour from the current weather. It can be above or below the normal rating. The dashboard calls it a "weather-based rating" on screen. |
| **Wire** | One physical cable. A power line carries three phases; on Austin, Corpus Christi and Midland each phase is a bundle of two wires, and on El Paso one wire. The database says "per conductor" for this. Every amp value in the database is **per wire**, not per line. |
| **Safety checks** | Automatic checks a dynamic rating must pass before it is published. Six are defined (G1 to G6); G5 is switched off, so five apply. Ch. 3 lists them. |
| **Fallback** | When a safety check fails, or no weather is available, the system publishes the normal rating instead of the dynamic one. A fallback is the safe outcome, not an error. |
| **Forecast band** | The range a forecast value is likely to fall in, for example "between 1,900 A and 2,100 A". A wider band means less certainty. |
| **Provisional** | A label on older rows saying the values have not been through the latest re-check. Ch. 4.9 explains when it appears. |

## 3. Safety-check codes

`fallback_gates` holds these codes. Operators should see the plain reason, never the code alone. The checks run in the order shown, and the first one that fails stops the run (`backend/DLRSafetyMonitor.py:35-88`).

| Code | What it checks | Plain reason to show an operator |
| --- | --- | --- |
| `G1` | Did the weather sensor report in time? | "Weather sensor did not report in time" |
| `G2` | Is the data link working? | "Weather data link was lost" |
| `G3` | Are the weather readings within believable limits? | "A weather reading was outside believable limits" |
| `G4` | Is the calculated rating within the believable range for this city? | "The calculated rating was outside the believable range" |
| `G5` | Did the rating jump too far since the last hour? | Does not appear: this check is switched off for the published ratings ([`city_rating_v1.md`](../../../../docs/data-science/schema/city_rating_v1.md), "What fallback means") |
| `G6` | Does the anomaly detector think the reading looks wrong, and did the detector itself work? | "An automatic check found the reading unusual, or could not run" |
| `EXHAUSTED` | Could any weather station near the city be reached? | "No weather station could be reached" |

Expect `G4` often for Austin and Midland. On a year of hourly weather, calculated ratings fell below those two cities' believable ranges in roughly 5 to 30% of hours (`backend/config.py:106-110`). They rose above the Corpus Christi and El Paso ranges in about 1 to 3% of hours. The believable ranges per city are in `backend/config.py:111-116`: Austin 1,150 to 2,500 A, Corpus Christi 800 to 2,200 A, Midland 1,250 to 2,500 A, El Paso 640 to 2,000 A, per wire.

## 4. Hourly ratings: `city_rating` and `latest_rating`

`city_rating` holds one row per city per hour, the full history. `latest_rating` is the newest row of each city, always four rows, with three extra columns about freshness (ch. 4.4). `latest_rating` carries 31 of the 49 `city_rating` columns; a dash in the "In `latest_rating`" column marks 13 of the 18 it leaves out. The other 5 are the weather readings of ch. 4.5, whose table has no such column because none of them is in `latest_rating`. The dashboard therefore reads the weather from `city_rating` (see [`DASHBOARD-REQUIREMENTS.md`](DASHBOARD-REQUIREMENTS.md) ch. 7).

### 4.1 Which city and which hour

| Column | In plain words | Why it is useful | In `latest_rating` | Dashboard use |
| --- | --- | --- | --- | --- |
| `city` | Which of the four cities the row is about: `AUSTIN`, `CORPUS_CHRISTI`, `MIDLAND` or `EL_PASO` | Every display is per city. The dashboard shows the city's normal name ("Corpus Christi"), never the code. | yes | Card |
| `valid_time` | The hour this rating is for, on the hour, in UTC (world time). A run whose weather window ends at 14:37 UTC writes the 14:00 UTC row. | It is the timestamp of the rating, and the dashboard measures freshness from it. | yes | Card (as "updated X min ago") |
| `observation_time` | The hour of the weather reading the rating was calculated from. It can be an hour or more older than `valid_time` when weather data arrives late. Empty when no weather was available, when the weather source gives no reading time, and on archive rows. | Explains a rating that seems not to match the current weather. Useful for troubleshooting, not for a glance. | yes | Tech details |
| `first_written_at` | When this row was first saved. Never changes. | Record-keeping only. | - | Not used |
| `computed_at` | When this row was last saved. Changes if the same hour is recalculated. | Tells an engineer whether the hour was recalculated. An operator needs `valid_time` instead. | yes | Tech details |

### 4.2 The rating itself

| Column | In plain words | Why it is useful | In `latest_rating` | Dashboard use |
| --- | --- | --- | --- | --- |
| `rating_amps` | The rating in effect for this hour, in amps per wire. It is the dynamic rating when the checks passed, and the normal rating during a fallback. | The rating itself. The dashboard compares it with the normal rating to get the headline percentage. | yes | Card |
| `static_rating_amps` | The city's normal rating in amps per wire: Austin 1,825, Corpus Christi 1,500, Midland 1,875, El Paso 1,320 (`backend/config.py:41-51`). | The baseline every dynamic rating is compared against. "+18% above normal" needs it. | yes | Card |
| `rating_mw` | The rating converted to megawatts using a power factor of 0.95. It uses the per-wire amps, so on the three two-wire cities it shows about half the power the whole line could carry. | Familiar unit to grid engineers, but easy to misread as the line's capacity. | yes | Tech details, with the per-wire caveat |
| `static_rating_mw` | The normal rating converted the same way, with the same per-wire caveat. | Same as `rating_mw`. | yes | Tech details, with the per-wire caveat |
| `line_voltage_kv` | The line's voltage in kilovolts (thousands of volts) used in the megawatt conversion: 345 kV for every city. | Needed only to understand the megawatt figures. | yes | Tech details |
| `power_factor` | An assumed share of the line's power that does useful work (0.95, so 95%), used in the megawatt conversion. | Same as `line_voltage_kv`. | yes | Tech details |

### 4.3 Rating state and fallback reasons

| Column | In plain words | Why it is useful | In `latest_rating` | Dashboard use |
| --- | --- | --- | --- | --- |
| `status` | `ok` when the dynamic rating passed every safety check; `fallback` when the normal rating was published instead. | Says whether the rating is weather-based or the normal one; the card's state is built on it. | yes | Card |
| `fallback` | Yes/no version of `status`: yes when the normal rating was published. | Same information as `status`; the dashboard uses one of the two consistently. | yes | Logic only |
| `fallback_gates` | Which safety checks failed this hour, as codes such as `G4`. Empty when none failed. | Turns "using normal rating" into a reason an operator can act on, via the plain reasons in ch. 3. | yes | Card (as the plain reason) |
| `alerts` | The full text of each failed check, for example `G4 FAIL (implausible (1080 A)) - fallback rating 1825 A`. Can contain short error text. | The exact detail an engineer needs to investigate. Too technical for the card. | yes | Tech details |
| `exhausted` | Yes when no weather station near the city could be reached this hour. Always comes with a fallback. | A distinct, actionable reason: the problem is weather data, not the line. | yes | Logic only (feeds the plain reason) |
| `detector_signal` | Which method the anomaly detector (check G6) used this hour, for example `model_clean`, `rolling_baseline` or `cold_start`. | Diagnostic for engineers checking the detector. Means nothing to an operator. | yes | Tech details |
| `detector_model_loaded` | Yes when the detector's trained model was available this run. | Diagnostic only. | - | Not used |

### 4.4 Freshness (only in `latest_rating`)

These three columns do not exist in `city_rating`. The database calculates them at the moment of each request.

| Column | In plain words | Why it is useful | Dashboard use |
| --- | --- | --- | --- |
| `age_minutes` | How many minutes old the city's newest rating is, rounded up. | Shown as "Updated 12 min ago", so the operator knows the number is current. | Card |
| `is_stale` | Yes when the newest rating is more than 90 minutes old. Ratings arrive hourly, so this means at least one hourly update was missed. | Decides the "data late" state. A late dynamic rating must never look current. | Logic only (decides the card state) |
| `is_provisional` | Yes when the row's labels still contain the word "provisional", meaning it has not been through the latest re-check. Rows written after the re-checked settings went live show no (ch. 4.9). | Decides whether the card shows a "Provisional" badge. | Logic only (decides the badge) |

### 4.5 The weather behind the rating

None of these columns is in `latest_rating`. They are all empty when no weather station could be reached.

| Column | In plain words | Why it is useful | Dashboard use |
| --- | --- | --- | --- |
| `air_temp_c` | Air temperature at the weather station, in degrees Celsius. Hotter air lowers the rating. | One of the three reasons the rating is what it is. | Detail |
| `wind_perp_ms` | The part of the wind blowing **across** the line, in metres per second. Wind across the wires cools them the most, so this is the wind the calculation uses. | The biggest single driver of a high or low rating. Shown as "wind across the line". | Detail |
| `solar_radiation_wm2` | Strength of the sunlight, in watts per square metre. Strong sun heats the wires and lowers the rating. | The third driver of the rating. | Detail |
| `wind_speed_ms` | The full measured wind speed, before working out how much of it crosses the line. | Explains why a windy day can still give a modest rating (the wind ran along the line). Too subtle for a glance. | Tech details |
| `wind_direction_deg` | The direction the wind came from, in compass degrees. | Same as `wind_speed_ms`. | Tech details |

### 4.6 Where the weather came from

| Column | In plain words | Why it is useful | In `latest_rating` | Dashboard use |
| --- | --- | --- | --- | --- |
| `station_id` | The code of the weather station that supplied this hour's reading. The station can change from hour to hour. | Lets an engineer check the source station. Meaningless to an operator. | - | Tech details |
| `candidates_probed` | How many nearby stations the system tried before one answered. | Diagnostic only. | - | Not used |
| `probe_trail` | The list of stations tried, with distance and result for each. | Diagnostic only. | - | Not used |
| `temp_source` | Which weather data provider supplied the temperature. | Diagnostic only. | - | Tech details |
| `wind_source` | Which provider supplied the wind. | Diagnostic only. | - | Tech details |
| `solar_source` | Which provider supplied the sunlight figure. | Diagnostic only. | yes | Tech details |

### 4.7 Next-hour forecast

The forecast predicts the dynamic rating one hour ahead. It is empty while the system is still collecting enough history (cold start) or when the forecast failed that hour.

| Column | In plain words | Why it is useful | In `latest_rating` | Dashboard use |
| --- | --- | --- | --- | --- |
| `forecast_amps` | The predicted rating for an hour from now, in amps per wire. | Tells the operator where the rating is heading. | yes | Detail |
| `forecast_ci_lower_amps` | The low end of the forecast band. | Shows how uncertain the forecast is; a forecast without its range overstates confidence. | yes | Detail |
| `forecast_ci_upper_amps` | The high end of the forecast band. | Same as the low end. | yes | Detail |
| `forecast_status` | `ok` (forecast made), `cold_start` (not enough history yet) or `failed`. | Decides whether the dashboard shows the forecast or a plain "not available" message. | yes | Logic only (decides what to show) |
| `forecast_horizon_min` | How far ahead the forecast looks, in minutes: 60. | The dashboard already says "next hour". | yes | Tech details |
| `forecast_method` | The forecasting method used: `naive`, `ewm` or `ml`. | Engineers only. | yes | Tech details |
| `forecast_n_observations` | How many past hours the forecast used. | Diagnostic only. | - | Not used |
| `forecast_used_by_g6` | Yes when the forecast was also fed to the anomaly detector. | Diagnostic only. | - | Not used |
| `history_rows` | How many past rows the system read before cleaning them. | Diagnostic only. | - | Not used |
| `usable_history_rows` | How many past rows were left after cleaning. | Diagnostic only. | - | Not used |

### 4.8 What produced the row

These columns identify the settings and models behind a row. When one of them changes between two hours of the same city, the calculation changed at that hour, so a jump in the chart may come from new settings rather than weather.

| Column | In plain words | Why it is useful | In `latest_rating` | Dashboard use |
| --- | --- | --- | --- | --- |
| `config_version` | A readable name for the set of assumptions behind the rating, for example `v3-powersystems-2026-11-02`. | Names the settings an engineer is looking at. | yes | Tech details |
| `config_fingerprint` | An automatic code that changes whenever any assumption for this city changes. | The reliable way to spot a settings change. The dashboard marks such hours on the history chart. | yes | Logic only (chart marker) |
| `forecast_model_sha256` | An automatic code identifying the forecast model file. Empty when no file is used. | Spots a forecast-model change. | yes | Logic only (chart marker) |
| `anomaly_model_sha256` | An automatic code identifying the anomaly-detector model file. Empty when none was loaded. | Spots a detector-model change. | yes | Logic only (chart marker) |
| `rating_basis` | A paragraph saying what the numbers are and are not: a model estimate at one point per city, not a verified line limit. | The contract requires it to be available wherever a value is shown. The card shows a fixed short label instead, and the detail view shows this full text (see [`DASHBOARD-REQUIREMENTS.md`](DASHBOARD-REQUIREMENTS.md) ch. 5.5). | yes | Detail (full text) |
| `origin` | `live` for rows the hourly system wrote, `backfill` for historical rows loaded from an archive covering 2026-09-08 to 2026-09-28. | Separates real-time history from the loaded archive. | yes | Logic only (labels archive rows on long charts) |
| `run_id` | The identifier of the run that wrote the row. | Lets an engineer find the run's log. | yes | Tech details |
| `run_attempt` | Which attempt of that run wrote the row. | Diagnostic only. | - | Not used |
| `pipeline_version` | A short code identifying the version of the software that wrote the row. | Engineers only. | yes | Tech details |
| `schema_version` | The version of the row layout: 1. | For software compatibility only. | - | Not used |

### 4.9 The provisional label

`is_provisional` is yes for backfill rows and for live rows written before the re-checked settings went live, because their labels contain the word "provisional". The owner signed the re-check on 2026-11-02, and rows written after the new settings went live carry labels without that word, so `is_provisional` is no. Every value, provisional or not, is still a model estimate rather than a verified line limit, which is why the card always shows the short estimate label ([`city_rating_v1.md`](../../../../docs/data-science/schema/city_rating_v1.md), "Provisional label").

## 5. Day-ahead outlook: `day_ahead_forecast` and `day_ahead_upcoming`

The day-ahead outlook predicts each city's rating at each 6-hour mark: midnight, 6 AM, noon and 6 PM UTC. In Central Time those marks are 6 PM, midnight, 6 AM and noon in winter (CST), and one hour later in summer (CDT). The dashboard shows Central Time for all four cities. Each value is issued up to about 18 hours before its mark ([`day_ahead_forecast_v1.md`](../../../../docs/data-science/schema/day_ahead_forecast_v1.md), "When values appear"). It is a planning aid with no safety role, and it is not validated: every row carries the label `day-ahead-24h; engineering-selection; not-validated`. Unlike the hourly rating, it is published even when it falls outside a city's believable range ([`day_ahead_forecast_v1.md`](../../../../docs/data-science/schema/day_ahead_forecast_v1.md), "What it is").

`day_ahead_forecast` keeps every value ever issued. `day_ahead_upcoming` shows only targets still in the future and adds one column, `lead_minutes`.

| Column | In plain words | Why it is useful | Dashboard use |
| --- | --- | --- | --- |
| `city` | Which city. | Per-city display. | Detail |
| `valid_time` | The future hour the prediction is for. | The time axis of the outlook. | Detail |
| `issued_at` | When the prediction was made. A late prediction shows a later time. | Tells an engineer whether a value arrived late. | Tech details |
| `forecast_run_init_time` | When the weather forecast behind the prediction started: exactly 24 hours before `valid_time`. | Engineers only. | Not used |
| `horizon_minutes` | Always 1440 (24 hours): the age of that weather forecast at the target hour. | Constant; adds nothing on screen. | Not used |
| `forecast_amps` | The predicted rating for that hour, in amps per wire. | The value of the outlook. | Detail |
| `forecast_ci_lower_amps` | The low end of the band the value should fall in 90% of the time (the 5-95% band). | Shows the uncertainty, which is larger than for the next-hour forecast. | Detail |
| `forecast_ci_upper_amps` | The high end of the band. | Same as the low end. | Detail |
| `band_source` | Where the band came from: `test-split` (historical testing) or `live-rolling` (recent real performance). | Engineers only. A change of source can change the band width without the forecast changing. | Tech details |
| `band_n` | How many past errors the band is built from. | Diagnostic only. | Not used |
| `band_pairs_through` | The newest hour used to build a `live-rolling` band. Empty for `test-split`. | Diagnostic only. | Not used |
| `band_artifact_sha256` | A code identifying the file behind the test band. | Diagnostic only. | Not used |
| `forecast_method` | Always `ml_cooling_corrected`. | Constant; adds nothing on screen. | Not used |
| `cooling_model_sha256` | A code identifying the model file. | Diagnostic only. | Not used |
| `cooling_model_source` | `refit` (a model retrained for the city's current wire type) or `frozen` (the earlier model, kept unchanged). | Diagnostic only. | Not used |
| `anchor_observation_time` | When the real weather reading used to correct the prediction was taken. | Diagnostic only. | Not used |
| `anchor_source` | Which provider supplied that reading. | Diagnostic only. | Not used |
| `label` | `day-ahead-24h; engineering-selection; not-validated`, the same on every row. | Must be shown with the outlook. The dashboard shows it in plain words: "Planning estimate, not validated". | Detail (plain-words form) |
| `config_version` | The readable name of the assumption set, as in ch. 4.8. | Engineers only. | Not used |
| `config_fingerprint` | The automatic settings code, as in ch. 4.8. | Diagnostic only. | Not used |
| `run_id` | The run that issued the value. | Diagnostic only. | Not used |
| `run_attempt` | Which attempt of that run. | Diagnostic only. | Not used |
| `pipeline_version` | The software version that issued the value. | Diagnostic only. | Not used |
| `schema_version` | The row layout version: 1. | Software compatibility only. | Not used |
| `first_written_at` | When the row was saved. Rows are never changed. | Record-keeping only. | Not used |
| `lead_minutes` | Only in `day_ahead_upcoming`: minutes from now until the target hour. | The dashboard shows target times as clock times, so this adds nothing. | Not used |

## 6. Day-ahead feed status: `day_ahead_status`

Always four rows, one per city, calculated at the moment of the request. It answers one question: is the day-ahead outlook arriving on time?

| Column | In plain words | Why it is useful | Dashboard use |
| --- | --- | --- | --- |
| `city` | Which city. | Per-city display. | Logic only |
| `checked_at` | The moment of the request. | Every other column is "as of" this moment. | Not used |
| `next_target_time` | The next 6-hour mark after now. | Engineers only. | Not used |
| `upcoming_count` | How many future predictions are stored for the city. | Engineers only. | Not used |
| `newest_issued_at` | When the city's newest prediction was made. Empty if it has none. | Engineers only. | Not used |
| `missing_targets` | Upcoming 6-hour marks within the next 12 hours that have no prediction yet. | Names exactly which outlook values are missing. | Tech details |
| `is_late` | Yes when a prediction due within the next 12 hours is missing. It only switches on once the first outlook value has ever been stored, so an empty feed does not raise a false alarm. | Decides the "Outlook delayed" message in the detail view. | Logic only (decides the message) |

## 7. Tables the dashboard cannot read

The dashboard's key is refused on these tables, so they are not part of this guide:

- `pipeline_run`, the internal log of each hourly run ([`city_rating_v1.md`](../../../../docs/data-science/schema/city_rating_v1.md), "Run log").
- `ops.freshness_log`, the internal log of the five-minute freshness check (comments in `supabase/migrations/20261026204258_soak_freshness_log.sql`).
- `psse_run`, `psse_dispatched_capacity`, `psse_voltage_margin` and `psse_contingency_result`, the grid-study results Power Systems' job writes (comments in `supabase/migrations/20261109233541_psse_results.sql`). The dashboard's planned use of them is a deferred requirement in [`DASHBOARD-REQUIREMENTS.md`](DASHBOARD-REQUIREMENTS.md) ch. 10. This guide gains a chapter for them if they are opened to the dashboard.
