# Operator dashboard requirements

**What the dashboard must tell an operator at a glance, which database columns serve that, and the design rules that keep it readable for someone who does not know the system**

|              |                                                                                                                                                                                       |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Status**   | Draft for the Software team. Three choices were confirmed by the Data Science owner on 2026-11-11, as recorded in [`../STATE.md`](../STATE.md) (ch. 5.3, ch. 6.1, ch. 10). |
| **Owner**    | Data Science owner (requirements); Software team (design and build)                                                                                                                  |
| **Scope**    | The first release of the operator dashboard: what it shows, how it looks, how it reads the database. It does not plan phases or choose a tech stack.                                 |
| **Related**  | [`COLUMN-GUIDE.md`](COLUMN-GUIDE.md) (every column in plain language), [`rest-api.md`](../../../../docs/integration/rest-api.md) (the database contract), [`software-team-handoff.md`](../../../../docs/integration/software-team-handoff.md) (access and first request), [`docs/frontend/PRD.md`](../../../../docs/frontend/PRD.md) (the earlier requirements; ch. 3.2 of this document says what it replaces) |
| **Audience** | Software team developers and designers; the operators who test the dashboard                                                                                                         |

---

## 1. Summary

We propose a dashboard with one overview page and one detail view per city. For each of the four cities, the overview answers three questions without a click. Is the rating current? Is it based on today's weather or on the normal rating? How far above or below normal is it?

The city's detail view, one click away, holds the weather behind the rating, the next-hour forecast, the 24-hour history and the day-ahead outlook. A collapsed "Technical details" section holds the engineering diagnostics. Of the 85 columns the dashboard can read, the overview cards show 7, the detail view adds 13, and Technical details holds 22. The rest only drive states and markers, or are unused (ch. 4).

The headline on each card is a percentage against the normal rating, such as "+18% above normal", with the amps figure beneath it. The database's megawatt figure is per wire and would mislead an operator (ch. 5.3).

Four rules carry the project's safety commitment onto the screen:

- A late rating never looks current.
- A fallback to the normal rating is never hidden.
- A rating below normal is never shown as good news.
- The dashboard never combines the four cities' ratings.

## 2. The operator

### 2.1 Who uses it

The primary user is a grid operator at a desk monitor who is not trained in dynamic line rating, thermal models or this system's internals. The source requirement is that operators "correctly interpret dynamic ratings and system alerts without additional guidance" (`docs/System Design Report.md` §3.3, cited in [`docs/frontend/PRD.md`](../../../../docs/frontend/PRD.md) §3). Course graders and the Power Systems team also look at it, but the design serves the operator first.

### 2.2 The questions the dashboard answers

The operator glances at the dashboard to decide whether anything needs their attention. They ask these questions in this order:

1. Is each line's rating current, or has an update been missed?
2. Is the rating based on today's weather, or is the system using the normal rating?
3. How much more (or less) can each line carry than its normal rating?
4. Why is the rating what it is: the weather, or a failed safety check?
5. Where is it heading in the next hour, and tomorrow?
6. What happened over the last day?

Questions 1 to 3 belong on the overview, readable in about five seconds without clicking (UI-03 defines the five-second test). Questions 4 to 6 belong in the detail view.

### 2.3 Plain-language rule

Every word on the operator-facing screen must make sense to someone who has never read the documentation. The rule covers labels, reasons, tooltips and error messages. The "Technical details" section is the one place engineering vocabulary is allowed.

| Show the operator | Never show the operator (outside Technical details) |
| --- | --- |
| rating, normal rating | ampacity, DLR, SLR, static rating |
| weather-based rating | dynamic rating |
| above normal, below normal, same as normal | headroom, uplift |
| normal rating in use | fallback, gate, `G4`, `EXHAUSTED` |
| data late | stale, `is_stale` |
| estimate, planning estimate | provisional (except the badge in STA-05), engineering-selection |
| the plain reasons in [`COLUMN-GUIDE.md`](COLUMN-GUIDE.md) ch. 3 | raw alert text, error messages |
| Central Time clock times, "12 min ago" | UTC, ISO timestamps |
| city names ("Corpus Christi") | city keys (`CORPUS_CHRISTI`) |

This document uses the developer term "dynamic rating" in its own reasoning; the screen says "weather-based rating".

## 3. Grounding

### 3.1 What the database provides

These facts were checked against the repository at commit `54190fb` on 2026-11-11.

| Fact | Source |
| --- | --- |
| Ratings are live: one row per city per hour, readable with a read-only key | [`software-team-handoff.md`](../../../../docs/integration/software-team-handoff.md), opening section |
| `latest_rating` returns exactly four rows, the newest per city, with freshness flags | [`rest-api.md`](../../../../docs/integration/rest-api.md), "Endpoints" |
| A rating is late (stale) when its hour is more than 90 minutes old | [`rest-api.md`](../../../../docs/integration/rest-api.md), "Freshness" |
| A fallback row publishes the city's normal rating and is a valid, safe value, not an error | [`rest-api.md`](../../../../docs/integration/rest-api.md), "Fallback rows" |
| The safety check that could publish a value other than the normal rating (G5) is switched off, so every fallback publishes exactly the normal rating | [`city_rating_v1.md`](../../../../docs/data-science/schema/city_rating_v1.md), "What fallback means" |
| A dynamic rating that passes every check can be below the normal rating: each city's believable range starts below its normal rating (Austin 1,150 to 2,500 A against 1,825 A) | `backend/config.py:41-51`, `backend/config.py:111-116` |
| Calculated ratings fall outside the believable range in roughly 5 to 30% of hours for Austin and Midland and 1 to 3% for Corpus Christi and El Paso, so the normal-rating state is common | `backend/config.py:106-110` (measured on a year of hourly weather) |
| Every amp value is per wire; Austin, Corpus Christi and Midland have two wires per conductor bundle | `backend/config.py:76-81` |
| `latest_rating` does not carry the weather readings; `city_rating` does | `supabase/migrations/20261026195124_expose_latest_rating.sql:47-85` |
| The day-ahead tables became readable with the dashboard's key on 2026-11-09 | `.planning/milestones/ws-production-pipeline-2026-11-09/STATE.md` (plan 08-11 decision) |
| The day-ahead outlook is not validated, has no safety role, and is published even outside the believable range | [`day_ahead_forecast_v1.md`](../../../../docs/data-science/schema/day_ahead_forecast_v1.md), "What it is" |
| The dashboard should poll no faster than every 60 seconds | [`rest-api.md`](../../../../docs/integration/rest-api.md), "Limits and polling" |

The 85 readable columns in ch. 1 are 49 columns of `city_rating`, 3 computed columns of `latest_rating`, 25 columns of `day_ahead_forecast`, 1 computed column of `day_ahead_upcoming` and 7 columns of `day_ahead_status`. Views that repeat a table's columns are not counted twice.

### 3.2 Relationship to the earlier frontend PRD

[`docs/frontend/PRD.md`](../../../../docs/frontend/PRD.md) was last reviewed against the repository on 2026-10-12, when the only data source was CSV files. Its principles still hold, in particular SW-NF1 (fail-safe display) and SW-NF4 (no rating maths in the browser); ch. 5.3 makes one named exception to SW-NF4. Its data-source sections and its list of data gaps (§8, G1 to G8) no longer describe the system. The live database now provides the city, the fallback status, the forecast and the normal rating directly. This document replaces those parts and settles several of its open decisions:

| Earlier open decision | Settled here as | Where |
| --- | --- | --- |
| OD-1 unit of selection | Four city cards; no station selector | ch. 5.1 |
| OD-2 data-feed mechanism | The browser polls the database's REST interface | ch. 7 |
| OD-3 meaning of "trusted duration" | Proposed: "Current until" time, the moment the rating becomes late | ch. 5.4 |
| OD-4 line sag | Out of scope: nothing produces it | ch. 9 |
| OD-5 headline when dynamic is below normal | Show the published rating, labelled "below normal" | ch. 5.2 |
| OD-6 how a fallback is presented | "Normal rating in use", with the plain reason | ch. 5.2 |
| OD-7 display timezone | Central Time, labelled CST or CDT | ch. 6.5 |
| OD-8 MW or amps | Percentage and amps; MW only in Technical details | ch. 5.3 |
| OD-9 PSS/E interface | Deferred requirement | ch. 10 |
| OD-12 shadow-forecast stream | Not used; the database carries the forecast | ch. 9 |

OD-10 (standards beyond ISO 9241), OD-11 (tech stack) and OD-13 (login) stay open; ch. 11 lists them.

## 4. Column selection

Each column the dashboard can read gets one of five uses. [`COLUMN-GUIDE.md`](COLUMN-GUIDE.md) gives the use of every individual column; this chapter gives the rule and the result.

| Use | Rule for putting a column here | What lands here |
| --- | --- | --- |
| **Card** | Answers questions 1 to 3 of ch. 2.2 | City, rating, normal rating, rating state, plain fallback reason, age |
| **Detail** | Answers questions 4 to 6, or explains a card | Weather drivers, next-hour forecast and band, day-ahead outlook with its label, full estimate text |
| **Tech details** | Helps an engineer investigate, but means nothing to an operator | Weather station, weather hour, raw alert text, megawatt figures with caveat, data providers, forecast method, settings version, run identifier, software version |
| **Logic only** | Decides a state, badge or marker, but its raw value would add nothing | Freshness flag, provisional flag, fallback flag, weather-station-unreachable flag, forecast status, settings fingerprints, archive flag, day-ahead late flag |
| **Not used** | Neither shown nor needed by any rule | Station search trail, history counts, day-ahead model and band codes, row-layout versions, insert times |

The operator sees, at most, these values per city:

| On screen | Columns behind it (some only decide the item) | Where the item appears |
| --- | --- | --- |
| City name | `city` | Card |
| State: weather-based, below normal, normal rating in use, or data late | `status`, `is_stale`, `rating_amps`, `static_rating_amps` | Card |
| Headline: "+18% above normal" | `rating_amps`, `static_rating_amps` | Card |
| Rating and normal rating in amps | `rating_amps`, `static_rating_amps` | Card |
| Why the normal rating is in use | `fallback_gates`, `exhausted` | Card |
| "Updated 12 min ago · Current until 3:30 PM CST" | `age_minutes`, `valid_time` | Card |
| A fixed estimate label, and a "Provisional" badge when it applies | `is_provisional` (the label itself is fixed text) | Card |
| Air temperature, wind across the line, sunlight | `air_temp_c`, `wind_perp_ms`, `solar_radiation_wm2` | Detail |
| Next-hour forecast with its range | `forecast_amps`, `forecast_ci_lower_amps`, `forecast_ci_upper_amps`, `forecast_status` | Detail |
| 24-hour or 7-day history chart | `valid_time`, `rating_amps`, `static_rating_amps`, `status`, `config_fingerprint`, `forecast_model_sha256`, `anomaly_model_sha256`, `origin` | Detail |
| Day-ahead outlook with its label | `day_ahead_upcoming`: `city`, `valid_time`, `forecast_amps`, both band columns, `label`; `day_ahead_status.is_late` | Detail |
| About this rating | `rating_basis` | Detail |

> **Why & What - under a quarter shown to operators**
>
> **What:** Show 7 columns on the overview and 13 more in the detail view; put 22 diagnostic columns in Technical details and leave the rest to logic or unused.
>
> **Why:** The operator's decision is "does anything need my attention?", and every extra number on the overview slows that decision. Most columns exist for audit and troubleshooting (which run, which model file, which station), and an operator cannot act on them. Technical details keeps the 22 columns an engineer needs to trace a row to its run, station and settings, one click deeper. This choice does not cover the remaining diagnostic columns, such as the station search trail; an engineer reads those from the database directly.
>
> **Alternatives considered:**
> - *Show everything in a full table:* nothing is hidden, and an engineer gets every answer on one screen. It fails the five-second test (UI-03) and makes the operator learn the data model.
>
> **Fallback:** If testing shows operators miss something, promote that one value from Detail to Card; the tiers make that a small change.

## 5. Information requirements

Each requirement has an ID for tracking and a "Done when" test a reviewer can check against fixed test data (a fixture). The deferred requirement in ch. 10 gets its test when it is taken up. [`../REQUIREMENTS.md`](../REQUIREMENTS.md) lists the same IDs as a checklist.

### 5.1 Overview page

- **OVR-01** The overview shows one card per city for all four cities, side by side, in a fixed order: Austin, Corpus Christi, Midland, El Paso. There is no city selector on the overview, and no fifth "all cities" card.
  *Done when:* for each of the four state fixtures in ch. 5.2, all four cards are visible without scrolling in a 1366 by 768 browser viewport, in that order.
- **OVR-02** A summary line above the cards counts the cities in each state, using the state labels of ch. 5.2. An example is "2 weather-based · 1 normal rating in use · 1 data late". It names the cities that are below normal or late. Counting cities per state is allowed; combining their ratings is not (DATA-06).
  *Done when:* for a fixture with one late city and one below-normal city, the line names both, and no rating or capacity value on the page is a sum, average or minimum across cities.
- **OVR-03** Clicking a card, or pressing Enter on it, opens that city's detail view; a back control returns to the overview.
  *Done when:* each card opens its own city's detail view by mouse and by keyboard.

### 5.2 City states

Every card is in exactly one of four states, decided in this order. The first condition that matches wins. "Percentage" means the headline percentage of HEAD-01, after rounding.

| Order | Condition | State label | Headline | Status role (UI-05) |
| --- | --- | --- | --- | --- |
| 1 | No row for the city, or the rating is late (FRESH-02) | **Data late** | "Use normal rating" and the normal rating in amps | Caution |
| 2 | `status` is `fallback` | **Normal rating in use** | "At normal rating" and the amps | Neutral |
| 3 | `status` is `ok` and the percentage is -1% or lower | **Below normal** | "12% below normal" and the amps | Caution |
| 4 | `status` is `ok` otherwise | **Weather-based rating** | "+18% above normal", or "Same as normal" at 0%, and the amps | Informational |

- **STA-01** The card shows the state label in words and an icon, in addition to colour.
  *Done when:* each state is identifiable on a greyscale screenshot.
- **STA-02** In the **Data late** state the card does not show the old dynamic value as the headline. It shows the normal rating as the value that applies, and when the last update was ("Last updated 3 h 10 min ago"). This follows the earlier PRD's fail-safe rule SW-NF1. It also follows the project's commitment to "default back to the conservative static rating immediately" (`docs/Project Definition.md`, Ethical Considerations).
  *Done when:* a fixture row 91 minutes old shows "Data late", the normal rating, and no dynamic value on the card.
- **STA-03** In the **Normal rating in use** state the card shows the plain reason from [`COLUMN-GUIDE.md`](COLUMN-GUIDE.md) ch. 3. The reason follows these rules:
  - When `exhausted` is true, the only reason shown is "No weather station could be reached".
  - Otherwise one line is shown per code in `fallback_gates`, in check order (G1 first).
  - A code the dashboard does not recognise shows "A safety check failed"; the code itself appears only in Technical details.
  - When `fallback_gates` is empty (archive rows), the reason is "Reason not recorded".

  The state is not styled as an error, because it is the safe outcome.
  *Done when:* fixtures with `G4`, with `EXHAUSTED` and `exhausted` true, with an unknown code `G9`, and with an empty list each show the reasons above. A synthetic row with `G1` and `G4` shows two lines; live rows carry one code, so this case is defensive. None of these uses the caution or error styling.
- **STA-04** The **Below normal** state is visibly different from **Weather-based rating**: it uses the caution role and says "below normal" in words. A rating below normal is less capacity than the operator would assume from the normal rating.
  *Done when:* a fixture with `rating_amps` 1,500 and `static_rating_amps` 1,825 shows "18% below normal" in the caution style, and a fixture with 1,824 and 1,825 shows **Weather-based rating** with "Same as normal".
- **STA-05** When `is_provisional` is true, the card shows a small "Provisional" badge beside the state label, with the tooltip "Calculated before the latest re-check of the rating method."
  *Done when:* the badge appears for a provisional fixture row and not for a current one.

### 5.3 Headline number

- **HEAD-01** The headline is the percentage difference between the rating and the normal rating, rounded to a whole percent. It reads "+18% above normal", "12% below normal", or "Same as normal" at 0%. The rating and the normal rating appear beneath it in amps, in smaller type: "2,150 A per wire · normal 1,825 A". Every amp figure on the operator screens says "per wire", with the tooltip "The current on each wire, not the whole line's total". The amps are secondary to the percentage, so the per-wire basis cannot mislead the headline.
  *Done when:* `rating_amps` 2,150 and `static_rating_amps` 1,825 show "+18% above normal" and "2,150 A per wire · normal 1,825 A". Every amp figure on the card and in the detail view carries the "per wire" text and tooltip.

> **Why & What - percentage as the headline**
>
> **What:** Lead each card with "X% above or below normal", calculated in the browser as `rating_amps` divided by `static_rating_amps`, minus one; show amps beneath it.
>
> **Why:** The percentage answers the operator's real question, "how much more than usual can this line carry?", in a form that needs no unit knowledge. It is the same whether counted per wire or per line, so the per-wire basis of the amp values cannot distort it. It does not tell the operator the line's total capacity in megawatts; that number does not exist in the database in a form an operator can use.
>
> **Cost against the earlier PRD:** this percentage is what [`docs/frontend/PRD.md`](../../../../docs/frontend/PRD.md) calls headroom, and its SW-NF4 asks the browser not to recompute headroom. This is a named exception to SW-NF4, chosen by the Data Science owner on 2026-11-11. Q9 in ch. 11 asks whether Data Science should store the percentage as a column, which would remove the exception.
>
> **Alternatives considered:**
> - *Megawatts first:* the unit grid operators know. The database's `rating_mw` uses per-wire amps and a 0.95 power factor, so for three of the four cities it shows about half of what the line could carry ([`COLUMN-GUIDE.md`](COLUMN-GUIDE.md) ch. 4.2). An operator would read it as the line's capacity and be wrong by a factor of two.
> - *Amps first:* the most faithful to the data. "Amps per wire" means little to a non-technical operator, and the four cities' amp values are not comparable with each other.
>
> **Fallback:** If Data Science adds a per-line MVA column, a megawatt figure can join the card without changing the layout.

### 5.4 Freshness and "current until"

- **FRESH-01** Every card shows how old its rating is, in words: "Updated 12 min ago". Every card that is not **Data late** also shows "Current until 3:30 PM CST": the moment the rating becomes late, which is `valid_time` plus 90 minutes.
  *Done when:* a row with `valid_time` `2026-11-11T20:00:00+00:00` shows "Current until 3:30 PM CST", and the card turns to **Data late** after that time without a page reload.
- **FRESH-02** The card's age keeps counting between polls, without trusting the desktop clock. The browser takes `age_minutes` from the last successful poll and adds the time elapsed since that poll, measured with the browser's own timer. A rating is late when `is_stale` is true or this age passes 90 minutes, whichever happens first. The rule keeps working when the browser cannot reach the database.
  *Done when:* with the network disconnected, a card whose rating passes 90 minutes old turns to **Data late** within one minute. With the desktop clock set two hours wrong, every card shows the same state and age as on a correct clock.

> **Why & What - "current until" as trusted duration**
>
> **What:** Show the time at which the current rating stops being current (90 minutes after its hour), and call it "Current until".
>
> **Why:** The course documents ask the dashboard to show a "trusted duration" for the rating ([`docs/frontend/PRD.md`](../../../../docs/frontend/PRD.md) OD-3). The source gives 10 to 20 seconds, which does not fit hourly data. The 90-minute freshness rule is the system's own definition of how long a rating stays usable, so the dashboard reuses it rather than inventing a second one. It does not promise that the weather, or the rating, will stay the same until then.
>
> **Alternatives considered:**
> - *The forecast horizon (60 minutes):* also an existing number, but it describes how far ahead the forecast looks, not how long the current value is valid.
>
> **Fallback:** Drop the "Current until" text and keep "Updated X min ago"; the state change at 90 minutes still protects the operator.

### 5.5 Estimate label

- **LBL-01** Every card shows the fixed label "Model estimate · not a verified line limit". The label is constant text in the dashboard, so a change to `rating_basis` does not change it. The detail view shows the full `rating_basis` text for that city under the heading "About this rating" (DET-05).
  *Done when:* the label is on all four cards, and the detail view's text equals the newest row's `rating_basis`.

> **Why & What - fixed short label on the card**
>
> **What:** Put a fixed one-line summary on the card and the full `rating_basis` paragraph in the detail view.
>
> **Why:** The contract says to show `rating_basis` wherever a value is shown ([`rest-api.md`](../../../../docs/integration/rest-api.md), "Read this first"). The current text runs to about 100 words, and four copies on the overview would bury the numbers. The short label keeps the two caveats an operator must not miss: it is a model estimate, and it is not a verified limit. The full text stays one click away. This bends the contract's wording, so the Data Science owner must confirm it (ch. 11, Q1). The cost: if Data Science changes `rating_basis` in a way that changes those two caveats, someone must update the fixed label by hand.
>
> **Alternatives considered:**
> - *Full text on every card:* follows the contract word for word. It fails the five-second test and trains operators to ignore the label.
>
> **Fallback:** Show the full text in an expandable area on each card.

### 5.6 Detail view

The detail view is for one city. It opens with the same state, headline and freshness as the card, then shows these sections in this order.

- **DET-01 Why the rating is what it is.** In the **Weather-based rating** and **Below normal** states, show the three weather drivers with one fixed line of explanation each:

  | Driver | Shown as | Fixed explanation |
  | --- | --- | --- |
  | `air_temp_c` | Air temperature in °F | "Hotter air lowers the rating." |
  | `wind_perp_ms` | Wind across the line in mph | "Wind across the wires cools them and raises the rating." |
  | `solar_radiation_wm2` | "Sunlight strength" in W/m², with the note "0 at night, highest around midday" | "Strong sun heats the wires and lowers the rating." |

  The explanations describe the physics in general; the dashboard does not claim how much each driver moved this hour's rating. In the **Normal rating in use** state, this section shows the plain reason (STA-03) first and the weather second. When the readings are empty it shows "No weather reading".
  *Done when:* a fixture row shows all three drivers in °F, mph and W/m² with their explanations; a row with empty weather shows "No weather reading" and no zeros.
- **DET-02 Next-hour forecast.** The text depends on `forecast_status`:
  - `ok`: "Next hour: likely between 1,950 A and 2,250 A (most likely 2,100 A)", with the same range as percentages against the normal rating.
  - `cold_start`: "Next-hour forecast not available yet: the system is still collecting history."
  - `failed` or empty: "Next-hour forecast not available this hour."

  A fixed note follows in every case: "If the next hour's rating fails a safety check, the normal rating applies instead."
  *Done when:* fixtures with each `forecast_status` value show their text, and no forecast number appears for `cold_start` or `failed`.
- **DET-03 History chart.** Show the city's rating over the last 24 hours, with a switch to 7 days. UI-09 sets the chart rules.
  *Done when:* the chart's points equal the `city_rating` rows for that city and window.
- **DET-04 Day-ahead outlook.** Show the city's upcoming day-ahead values from `day_ahead_upcoming` as a small separate chart or table. Each entry shows the target time in Central Time, the predicted amps, the band, and the percentage against the current normal rating. The heading is "Tomorrow's outlook", with the label "Planning estimate, not validated. Does not affect the current rating." When `day_ahead_status.is_late` is true, "Outlook delayed" appears above it.
  *Done when:* the outlook shows every upcoming row for the city with its band and label, and a fixture with `is_late` true shows "Outlook delayed".
- **DET-05 About this rating.** Show the full `rating_basis` text of the newest row (LBL-01).
  *Done when:* the text equals the newest `city_rating` row's `rating_basis` for the city, character for character.
- **DET-06 Technical details.** A section collapsed by default, labelled "Technical details", lists these fields for the newest row. Times here may show UTC beside Central Time.

  | Group | Fields |
  | --- | --- |
  | Weather source | `station_id`, `observation_time`, `temp_source`, `wind_source`, `solar_source`, `wind_speed_ms`, `wind_direction_deg` |
  | Safety checks | `alerts` (raw text), `detector_signal` |
  | Megawatts, with the note "per wire, at power factor 0.95; not the line's total capacity" | `rating_mw`, `static_rating_mw`, `line_voltage_kv`, `power_factor` |
  | Forecast | `forecast_method`, `forecast_horizon_min` |
  | Provenance | `config_version`, `run_id`, `pipeline_version`, `computed_at` |
  | Day-ahead | `band_source`, `issued_at`, `missing_targets` |

  *Done when:* the section is collapsed on first open and lists all 22 fields above for a fixture row.

## 6. UI design requirements

### 6.1 Screen and viewing distance

- **UI-01** The primary screen is a desktop monitor (1920 by 1080) at arm's length. The overview must also fit a 1366 by 768 browser viewport without scrolling. Below 768 pixels wide the cards stack in one column and nothing overlaps or is cut off; a phone-optimised layout is not required.
  *Done when:* screenshots at viewports of 1920 by 1080 and 1366 by 768 show the whole overview without scrolling, and a 390 by 844 viewport shows every element with vertical scrolling only.

### 6.2 Hierarchy and the five-second test

- **UI-02** The visual order on each card is: state label and headline first, amps second, freshness third, estimate label last. The headline is the largest text on the page; we propose at least 40 pixels at the primary resolution. Body text is at least 16 pixels.
  *Done when:* the computed font size of the headline is the largest on the page and at least 40 pixels at 1920 by 1080, and no body text is below 16 pixels.
- **UI-03** The overview passes the five-second test. A person who has not used the dashboard sees the overview for five seconds and is then asked which cities are on the normal rating, which are late and which are above normal.
  *Done when:* at least four of five non-technical testers answer correctly for a fixture with all four states present.

### 6.3 Layout stability

- **UI-04** Values update in place when new data arrives. The layout does not shift, cards do not reorder by state, and numbers do not animate or count up.
  *Done when:* a poll that changes every card's state moves no card's position.

### 6.4 Colour and status

- **UI-05** The design uses four status roles, each shown with an icon and a word as well as a colour:

  | Role | Used for | Proposed hue |
  | --- | --- | --- |
  | Informational | Weather-based rating | Blue |
  | Neutral | Normal rating in use | Grey |
  | Caution | Below normal; Data late | Amber |
  | Error | Database unreachable (UI-14) | Red, only for this |

  The design phase chooses the exact colours. Every text colour meets WCAG 2.1 AA contrast: 4.5 to 1 for text, and 3 to 1 for icons and chart lines.
  *Done when:* an automated contrast check passes for every state in the theme (or themes) the team ships.

> **Why & What - no traffic-light colours**
>
> **What:** Show the weather-based rating in blue, not green, and keep red for "the dashboard cannot reach its data".
>
> **Why:** Green and red read as "safe" and "unsafe". The dashboard does not judge grid safety: a line above normal is not safe because of the rating alone, and a fallback to the normal rating is the safe outcome, not a failure. Blue says "more capacity than usual" without saying "go". This choice does not stop an operator reading the amber caution states quickly, because amber keeps its usual meaning.
>
> **Alternatives considered:**
> - *Green, amber, red:* the colours operators know best, readable with no learning. They would imply a safety judgment the system does not make, and would colour the common, safe fallback as a problem.
>
> **Fallback:** If usability testing shows operators misread blue, test green for the weather-based rating while keeping the fallback neutral.

### 6.5 Numbers, units and time

- **UI-06** Amps are whole numbers with a thousands separator and the unit: "2,150 A". Percentages are whole numbers with a sign. Temperature is in °F and wind in mph on the operator screens; Technical details may add °C and m/s.
  *Done when:* fixture values 2150.4 A, 18.6% above normal, 30 °C and 5 m/s display as "2,150 A", "+19% above normal", "86 °F" and "11 mph".
- **UI-07** Clock times are in US Central Time and labelled with the correct abbreviation, "CST" or "CDT". El Paso is on Mountain Time, but the dashboard uses one clock for all four cities so times can be compared; the El Paso detail view says "Times in Central Time". Ages are relative: "12 min ago", "3 h 10 min ago".
  *Done when:* a `valid_time` of `2026-11-11T20:00:00+00:00` displays as 2:00 PM CST, and `2026-07-15T20:00:00+00:00` as 3:00 PM CDT.
- **UI-08** A missing value shows a dash, with "No data" on hover and for screen readers. It never shows 0.
  *Done when:* a fixture row with empty `air_temp_c` shows a dash and no 0 anywhere for that value.

### 6.6 Charts

- **UI-09** The history chart plots the rating as a solid line and the normal rating as a labelled dashed line, on an amps axis.
  - Hours in the **Normal rating in use** state are shaded neutral; segments whose percentage is -1% or lower use the caution role, the same threshold as the **Below normal** state.
  - Missing hours are gaps, never joined across.
  - A vertical marker labelled "Settings changed" appears where `config_fingerprint`, `forecast_model_sha256` or `anomaly_model_sha256` differs from the previous hour. The contract asks for this marker ([`city_rating_v1.md`](../../../../docs/data-science/schema/city_rating_v1.md), "What produced each row").
  - Archive rows (`origin` is `backfill`) are labelled "Archive" when the window includes them.
  - Hovering a point shows the time, the amps, the percentage and the state.

  *Done when:* a fixture with a two-hour gap, a fallback hour, a below-normal hour and a fingerprint change shows each feature.
- **UI-10** The next-hour forecast band may appear at the right edge of the history chart as a shaded range with its point. The day-ahead outlook is a separate chart or table, so its lower certainty is not mistaken for the next-hour forecast's.
  *Done when:* no day-ahead value appears inside the history chart.

### 6.7 Motion and alerts

- **UI-11** Nothing blinks or flashes. A state change is shown by the new state's styling alone. The dashboard respects the operating system's "reduce motion" setting.
  *Done when:* no CSS animation or transition runs on a state change with "reduce motion" switched on, and none loops at any time.
- **UI-12** The first release has no sound, pop-up alarms or acknowledgement workflow. The summary line (OVR-02) is the alert surface.
  *Done when:* a state change to **Data late** plays no sound and opens no dialog.

### 6.8 Loading, error and empty states

- **UI-13** While the first data loads, the cards show their layout with a "Loading" label and no numbers.
  *Done when:* with the first request held open, every card shows "Loading" and no digits.
- **UI-14** When a poll fails, a red banner reads "Can't reach the rating database since 2:05 PM CST. Ratings below are from the last successful update." The cards keep their last values and keep ageing, so they turn to **Data late** on time (FRESH-02).
  *Done when:* blocking the database's address shows the banner within one poll interval, and the cards stay visible.
- **UI-15** A city with no row at all shows the **Data late** state with "No rating received yet" instead of an age.
  *Done when:* a fixture with only three cities shows the fourth card as **Data late** with "No rating received yet".

### 6.9 Accessibility

- **UI-16** The dashboard meets WCAG 2.1 level AA:
  - Every control is reachable and usable by keyboard, with a visible focus outline.
  - Each card's state is announced to screen readers in words, for example "Austin, weather-based rating, 18% above normal, updated 12 minutes ago".
  - No information depends on colour alone.

  *Done when:* an automated accessibility scan reports no level A or AA failures, and a keyboard-only walk-through reaches every card, the detail view and Technical details.

## 7. Data access requirements

[`rest-api.md`](../../../../docs/integration/rest-api.md) is the contract for every call; [`software-team-handoff.md`](../../../../docs/integration/software-team-handoff.md) covers getting the key. The tests in this chapter read the browser's network log.

- **DATA-01** The dashboard reads with the publishable key only, sent in the `apikey` header. It never holds the secret key or a `service_role` token.
  *Done when:* every request carries the key in `apikey` and none has an `Authorization` header or a key in the URL.
- **DATA-02** The overview reads `latest_rating` with only the columns the cards need: `city`, `valid_time`, `rating_amps`, `static_rating_amps`, `status`, `fallback_gates`, `exhausted`, `age_minutes`, `is_stale`, `is_provisional`. It polls every 2 minutes.
  *Done when:* the request's `select` lists exactly those columns and repeats every 2 minutes.
- **DATA-03** The detail view reads the city's `city_rating` rows for the chosen window (`city=eq.<CITY>`, `valid_time=gte.<start>`, `order=valid_time.asc`). The newest of those rows supplies the weather drivers, the forecast, "About this rating" and Technical details, because `latest_rating` does not carry all of them. Seven days is 168 rows per city, inside the 1,000-row limit of one request. While open, the view refreshes every 10 minutes, and also as soon as the overview poll returns a newer `valid_time` for the city.
  *Done when:* after a fixture's `latest_rating.valid_time` advances, the detail view shows the new hour's weather within one overview poll.
- **DATA-04** The detail view reads `day_ahead_upcoming` (filtered to the city) and `day_ahead_status` on open and every 10 minutes.
  *Done when:* both requests appear on open and repeat every 10 minutes.
- **DATA-05** No request repeats faster than every 60 seconds, and the dashboard does not call `rpc/assert_fresh`, which is the Data Science owner's alarm.
  *Done when:* a 10-minute network log shows at most one request per endpoint per 60 seconds and no call to `rpc/assert_fresh`.
- **DATA-06** The dashboard never combines cities' rating or capacity values: no sum, average, minimum or "total capacity" across cities, in any view or calculation. Counting cities per state (OVR-02) is allowed.
  *Done when:* code review finds no expression that combines `rating_amps`, `static_rating_amps` or a value derived from them across cities.
- **DATA-07** The browser does no rating calculation beyond the display arithmetic this document names: the percentage (HEAD-01, the named exception in ch. 5.3), "Current until" (FRESH-01), the age between polls (FRESH-02), and unit conversions (UI-06). It never recalculates a rating, a forecast or a fallback decision.
  *Done when:* code review finds no arithmetic on rating values other than those four.
- **DATA-08** The dashboard ignores columns it does not know, because the contract allows new columns to be added ([`rest-api.md`](../../../../docs/integration/rest-api.md), "Compatibility").
  *Done when:* a fixture with an extra unknown column renders the same as without it.

## 8. Design and build resources

The team may be starting with only the GSD workflow installed. The tools below give design guidance that GSD alone does not. Use these or similar tools; none is mandatory.

| Tool | Kind | Use it for | How to get it |
| --- | --- | --- | --- |
| `frontend-design` | Claude Code plugin (Anthropic's official marketplace) | Choosing a deliberate visual direction and avoiding a templated look | `/plugin install frontend-design@claude-plugins-official` |
| `impeccable` | Claude Code skill (version 4.1.3, Apache 2.0) | Designing, critiquing, auditing and polishing the interface: hierarchy, typography, colour, states, accessibility | Install from [github.com/pbakaus/impeccable](https://github.com/pbakaus/impeccable), following its README |
| `craft` | Claude Code skill | Applying concrete visual-craft rules to CSS and components (spacing, states, elevation, no gratuitous effects) | Ask the Data Science owner for a copy |
| `accessibility` | Claude Code skill | A WCAG 2.1 review of screens and flows (checks UI-16) | Ask the Data Science owner for a copy |
| `ux-heuristics-review` | Claude Code skill | A critique against the 10 usability heuristics | Ask the Data Science owner for a copy |
| `cognitive-load-conversion` | Claude Code skill | Cutting what an operator has to think about on a screen (supports UI-03) | Ask the Data Science owner for a copy |
| `dieter-rams-principles` | Claude Code skill | A restraint check: is anything on screen that does not earn its place? | Ask the Data Science owner for a copy |
| `dataviz` | Claude Code built-in skill, where available | Chart colours, stat tiles and chart marks that read as one system (supports UI-09) | Built into some Claude Code installations; otherwise use a similar charting guide |
| `/gsd-sketch` | GSD command | Throwaway HTML mock-ups of the overview and detail view before building | Included with GSD |
| `/gsd-ui-phase` | GSD command | Writing a UI design contract (UI-SPEC.md) for a phase before coding | Included with GSD |
| `/gsd-ui-review` | GSD command | A visual audit of built screens | Included with GSD |

Personal skills install by copying the skill's folder into `~/.claude/skills/`. The `awwwards` and `jury` skills, if you have them, target showcase websites and are the wrong bar for an operator tool.

We propose this order of use:

1. Sketch the overview with `/gsd-sketch`.
2. Settle the visual direction with `frontend-design` or `impeccable`.
3. Write the UI contract with `/gsd-ui-phase`.
4. Build.
5. Check with `/gsd-ui-review`, `accessibility` and `ux-heuristics-review` before the usability test (UI-03).

## 9. Non-goals

The first release does not:

- Control anything. It is read-only; operators cannot change ratings, acknowledge alarms or trigger runs.
- Show line sag. Nothing in the system calculates it ([`docs/frontend/PRD.md`](../../../../docs/frontend/PRD.md) OD-4).
- Use the shadow-forecast files or the CSV exports. The database is the only data source.
- Show a per-station view or let the operator pick a weather station.
- Show megawatts as a headline (ch. 5.3).
- Show the internal run log, the freshness log or the PSS/E results (the last is deferred, ch. 10).
- Send notifications by email, text message or sound.

## 10. Deferred: grid-study results

Power Systems' study job applies our ratings to their grid model and writes four result tables. The tables have existed in the database since 2026-11-09 (`supabase/migrations/20261109233541_psse_results.sql`). The most useful result for an operator is the **dispatched capacity**: how much of the rating the grid can use once voltage limits are considered. The study also records which of the two, the rating or voltage, is the limit.

- **DEF-01** A later release shows, per city, the usable share of the rating and its limiting factor in plain words. An example is "Grid can use 92% of this rating; voltage is the limit". It also shows the study's time, and an explicit "No grid study available" state.

This requirement is blocked on two things outside the Software team. First, the result tables are private, so the Data Science owner must decide to open read access to the dashboard. Second, the study job has not yet run on real PSS/E: it waits for Power Systems' case file and city-to-branch mapping (`docs/data-science/decisions/psse_message_to_aaron.md` on the `feature/pss-e-integration` branch). Nothing is built for it in the first release, and the layout does not reserve space for it.

## 11. Open questions

| # | Question | Owner |
| --- | --- | --- |
| Q1 | Is a fixed short label on the card, with the full `rating_basis` one click away, acceptable under the contract (ch. 5.5)? If yes, [`rest-api.md`](../../../../docs/integration/rest-api.md) should say so. | Data Science owner |
| Q2 | Should `latest_rating` gain `air_temp_c`, `wind_perp_ms` and `solar_radiation_wm2`, so the detail view needs one request fewer? The contract allows adding columns. | Data Science owner |
| Q3 | Does the team accept "Current until" (90 minutes after the rating's hour) as the trusted duration (ch. 5.4)? | Software team, with the Data Science owner |
| Q4 | Who are the five non-technical testers for the five-second test (UI-03)? | Software team |
| Q5 | Which standards beyond ISO 9241 apply to the dashboard (earlier PRD OD-10)? | Software team |
| Q6 | Which framework, charting library and hosting does the dashboard use (earlier PRD OD-11)? | Software team |
| Q7 | Does an operator tool need a login, given that the data is public by owner decision (earlier PRD OD-13)? | Software team, with the Data Science owner |
| Q8 | Should Data Science add a per-line MVA column, so megawatts could be shown honestly (ch. 5.3)? | Data Science owner, with Power Systems |
| Q9 | Should Data Science store the percentage against the normal rating as a column, so the browser no longer calculates it (ch. 5.3)? | Data Science owner |

## 12. Benefits and costs

The proposal gives operators a screen they can read in five seconds, and gives the Software team a fixed list of columns and states to build against, with a test for each. It reuses the database's own rules (the 90-minute freshness limit, the fallback to the normal rating), so the dashboard and the data cannot disagree about what "late" or "fallback" means.

The costs:

- Engineers lose a one-screen view of every column; they must open Technical details, city by city.
- The percentage headline is a value the database does not store. It is an exception to the earlier PRD's SW-NF4, and the team must test its calculation and rounding (HEAD-01).
- The fixed estimate label depends on the Data Science owner's agreement (Q1). If it is refused, the cards get longer; if it is kept, someone must keep it in step with `rating_basis`.
- Blue for the weather-based rating is less familiar than green, so operators may need one explanation. The usability test will show whether it costs reading speed.
- Four states with a fixed order, and a browser-side age that ignores the desktop clock, are more work to build and test than a single status flag.

## 13. Residual risks and what not to do

- Do not show a late dynamic rating as the headline (STA-02). A rating more than 90 minutes old is not current, whatever its value.
- Do not hide or soften the **Normal rating in use** state, and do not style it as a failure (STA-03).
- Do not show `rating_mw` on the card or describe it as the line's capacity (ch. 5.3).
- Do not add, average or take the minimum of cities' ratings, anywhere (DATA-06).
- Do not show raw codes (`G4`, `EXHAUSTED`) or alert text outside Technical details.
- Do not present the day-ahead outlook as a commitment or mix it into the history chart (DET-04, UI-10).
- Do not poll faster than every 60 seconds, and do not use the secret key (DATA-01, DATA-05).
- Do not recalculate ratings in the browser (DATA-07).

---

*Chapters 2.1, 3 and 4 and the column facts are drawn from the repository and the database contract at commit `54190fb`. The states, layout, colours, sizes and resource order are proposals for the Software team to test and adjust. Input is wanted on the open questions in ch. 11.*
