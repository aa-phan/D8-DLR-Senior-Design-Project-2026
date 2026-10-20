# Data Cleaning Policy

**Status:** Adopted 2026-10-19 with provisional thresholds (production-pipeline Phase 2, CLEAN-01..04). Phase 3 measures flag rates on real data; thresholds change only on that evidence.

**Policy version:** 1

**Decision:** A city's archive history is cleaned at read time, before the forecast and the anomaly detector learn from it. Cleaning flags rows and selects the usable ones; it never changes a value, never adds or drops a row, and never fills a missing hour. Stuck-sensor runs, one-hour spikes, fallback rows, duplicate instants, several rows in one hour, and rows at or after the slot being rated are excluded. A missing hourly slot is marked on the next row and measured in a report, not repaired.

## Where cleaning sits

`historical_archive.read_history` -> `data_cleaning.clean_history(history, as_of=end)` -> `ampacity_forecast.forecast_ampacity` and `AnomalyDetector.for_city`, all inside `city_pipeline.run_city_pipeline`. The forecast and the detector receive the usable rows only, so the band and the baseline that gate the rating learn only from rows that passed.

- `clean_history` is storage-agnostic. It takes any frame shaped like `ARCHIVE_COLUMNS` and imports no storage module; Phase 4 passes a Postgres read of the same shape.
- It works on one city per call. A frame with more than one city raises `ValueError`.
- A cleaning failure is not a rating failure. `run_city_pipeline` logs one WARNING and rates the city with an empty history (cold start) instead of passing unvetted rows to G6.

## What cleaning never does

- It never changes a cell of the input, and it never mutates the input frame.
- It never adds a row to `frame` and never drops one. Excluded rows stay in `frame` with their flags; `usable` is the selection of the rows not excluded.
- It never imputes. A missing hour stays missing and a flagged value is not replaced.
- It never writes to the archive or to any other store.
- Per-row unit and range checks stay with `units_def.validate_pipeline_row`, applied in `read_history`, which drops rows that fail them before this module sees them.

## Marker (CLEAN-04)

`clean_history` appends these columns to `frame` (and so to `usable`). They are never persisted; the archive only ever holds rows as written.

| Column | Meaning |
|---|---|
| `clean_flags` | The names of the rules that fired on the row, joined with `\|` in `FLAG_ORDER` order. `""` means the row is as written and untouched by every rule |
| `clean_excluded` | True when any excluding flag fired; the row is not in `usable` |
| `gap_slots` | Integer. For a usable row, the number of hourly slots missing since the previous usable row (0 for the first); 0 on excluded rows |

One row per flag, in rule order:

| Flag | Rule | Excludes | Requirement |
|---|---|---|---|
| `bad_timestamp` | `datetime_utc` is missing or does not parse | yes | CLEAN-03 |
| `duplicate` | Another row at the same UTC instant came first | yes | CLEAN-03 |
| `fallback` | `fallback` is true (bool or any-case text) | yes | CLEAN-01 |
| `at_or_after_run` | The row's slot is at or after the slot of `as_of` | yes | CLEAN-02 |
| `same_hour` | A later usable row exists in the same hourly slot | yes | CLEAN-02 |
| `stuck_air_temp` | In a run of `STUCK_MIN_RUN_ROWS` or more identical `air_temp` values | yes | CLEAN-01 |
| `stuck_wind_speed` | Same, for `wind_speed` | yes | CLEAN-01 |
| `stuck_solar_radiation` | Same, for `solar_radiation`, except exempt values | yes | CLEAN-01 |
| `spike_air_temp` | One-hour `air_temp` excursion beyond its step on both sides | yes | CLEAN-01 |
| `spike_wind_speed` | Same, for `wind_speed` | yes | CLEAN-01 |
| `spike_solar_radiation` | Same, for `solar_radiation` | yes | CLEAN-01 |
| `after_gap` | The row follows one or more missing hourly slots | no | CLEAN-02, CLEAN-04 |

## Rules, in order

A row's hourly slot is its parsed UTC `datetime_utc` floored to the hour. Row-local rules (1-4) see every row. Cross-row rules (5-8) see only the rows the earlier rules left usable, so a flagged row never changes another row's verdict through a rule that comes later than it.

1. `bad_timestamp`: `datetime_utc` is missing, empty or does not parse as an ISO-8601 instant. Naive values read as UTC. Values with an explicit offset and values without one are parsed in separate batches, because pandas 2.3 otherwise applies an earlier value's offset to a later naive one. Unparseable rows sort last.
2. `duplicate`: among rows with a timestamp, every row after the first at one UTC instant, in input order. The first row written owns the instant, matching `append_observation`.
3. `fallback`: `fallback` is a bool true or text equal to "true" in any case. A fallback cycle archives the static rating as `dlr_amps`; learning from it makes the naive forecast equal the static rating and latches G6.
4. `at_or_after_run`: only when `as_of` is given. The row has a timestamp and its slot is at or after `as_of` floored to the hour. The history a run learns from ends before the slot it rates, so a rerun or an out-of-order backfill sees what the first in-order run saw (no look-ahead). Without `as_of` no row is excluded for its time.
5. `same_hour`: of the rows still usable in one slot, the one with the latest timestamp stays and the others are flagged (a fresher reading suits a 60-minute-ahead forecast). A fallback row is excluded earlier and never displaces a computed row in its hour.
6. `stuck_air_temp`, `stuck_wind_speed`, `stuck_solar_radiation`: over the rows left usable by rule 5, in time order, a run is consecutive rows with an identical value of the field. A run of `STUCK_MIN_RUN_ROWS` or more whose value is not in the field's `STUCK_EXEMPT_VALUES` flags every row in it. A run continues across rows excluded by earlier rules. A missing value never equals another, so it never forms a run. A field whose column is absent is skipped. The three fields are judged against the same rows.
7. `spike_air_temp`, `spike_wind_speed`, `spike_solar_radiation`: over the rows left usable by rule 6, a row is flagged when its previous and next usable rows sit on the hourly slots exactly one hour before and after its own, and its value differs from both by more than `SPIKE_MAX_STEP` for the field, in the same direction. A difference equal to the step is not a spike. Steps, ramps, rows next to a gap and the first and last usable rows are never spikes. Every row is judged against the same set, so an oscillating sensor flags every interior row. A missing value never flags. The three fields are judged against the same rows.
8. `after_gap`: over the rows left usable by rule 7, `gap_slots` is the hours between the row's slot and the previous usable row's slot, minus one; rows with `gap_slots` above 0 carry `after_gap`. This flag marks the row and does not exclude it.

`clean_history(..., stuck_min_run_rows=, spike_max_step=)` overrides the defaults for tests and sensitivity checks. An overriding `spike_max_step` dict replaces the table; a field it omits is not spike-checked.

## Thresholds (provisional)

None of these values was derived from or tuned on real archives. Each is a stated engineering judgment; Phase 3 measures the per-city flag rates before anyone relies on them. Changing any constant or rule bumps `CLEANING_POLICY_VERSION`, so a validation result can name the policy behind its flags.

| Constant | Field | Value | Unit | Reasoning |
|---|---|---|---|---|
| `CLEANING_POLICY_VERSION` | - | 1 | - | Version of the rules and constants in this document |
| `STUCK_MIN_RUN_ROWS` | - | 6 | rows | Hourly temperature at whole-degree resolution can repeat for a few hours overnight; six identical hourly readings of one field is beyond that, and equals the ML forecast's six-row lookback |
| `STUCK_EXEMPT_VALUES` | `solar_radiation` | 0.0 | W/m2 | Solar radiation is exactly 0.0 every night, for far more than six hours |
| `SPIKE_MAX_STEP` | `air_temp` | 10.0 | degC per hour | A front is a step that stays; a swing this large that returns within the hour is more likely a sensor fault |
| `SPIKE_MAX_STEP` | `wind_speed` | 10.0 | m/s per hour | Archived wind is the line-perpendicular component, so direction swings move it; a larger swing that returns is suspect |
| `SPIKE_MAX_STEP` | `solar_radiation` | 700.0 | W/m2 per hour | Clouds swing hourly solar widely, so only a larger excursion counts |

Tuple and set constants, by name and members:

- `STUCK_FIELDS`: `air_temp`, `wind_speed`, `solar_radiation`
- `SPIKE_FIELDS`: `air_temp`, `wind_speed`, `solar_radiation`
- `FLAG_ORDER`: `bad_timestamp`, `duplicate`, `fallback`, `at_or_after_run`, `same_hour`, `stuck_air_temp`, `stuck_wind_speed`, `stuck_solar_radiation`, `spike_air_temp`, `spike_wind_speed`, `spike_solar_radiation`, `after_gap`
- `EXCLUDING_FLAGS`: every member of `FLAG_ORDER` except `after_gap`, i.e. `bad_timestamp`, `duplicate`, `fallback`, `at_or_after_run`, `same_hour`, `stuck_air_temp`, `stuck_wind_speed`, `stuck_solar_radiation`, `spike_air_temp`, `spike_wind_speed`, `spike_solar_radiation`
- `MARKER_COLUMNS`: `clean_flags`, `clean_excluded`, `gap_slots`

Phase 3 is expected to look first at wind stuck runs on calm nights (El Paso, Midland) and at solar spikes on cloudy days.

## Missing hourly slots (CLEAN-02)

The slot is the UTC hour of `datetime_utc`. The strategy is **mark, never fill**: a missing slot is never imputed and no row is invented. Invented points would enter `backtest_residuals` and the detector's rolling baseline and narrow the band that gates the rating, which is the unsafe direction.

- `after_gap` and `gap_slots` mark the first usable row after a gap. A skipped cycle (hourly rows 00:00-09:00 with 05:00 missing) puts `after_gap` and `gap_slots` 1 on the 06:00 row; the row stays usable.
- An excluded row leaves its hour missing, so the usable row after it carries `after_gap` too.
- `at_or_after_run` keeps the history strictly before the slot being rated. `same_hour` leaves one row per hour.
- The report carries three gap fields, all plain ints (or None): `missing_slots` is the sum of `gap_slots` over usable rows; `trailing_gap_slots` is the number of hourly slots between the newest usable row's slot and `as_of`'s slot (0 when the newest usable row is the hour before; None without `as_of` or without usable rows); `contiguous_tail_rows` counts the newest usable rows on consecutive hourly slots (0 when none).

What a gap does to each consumer of the usable frame:

| Consumer | Effect of a gap |
|---|---|
| `naive` forecast | Takes the last value, which is older than one hour when the trailing gap is above 0 |
| `ewm` forecast | Time-aware (`times=series.index`), so it weights by real elapsed time and discounts across the gap |
| `ml` forecast | Lags and the rolling mean use positional `shift`, so they misalign across a gap; the model was trained on gap-free hours |
| Walk-forward band (`backtest_residuals`) | A residual after a gap spans more than one hour, so the band widens, the conservative direction |
| Rolling baseline (`AnomalyDetector`) | Time-insensitive: mean and standard deviation over all usable `dlr_amps` |

How a forecast built across a gap is used by G6 is set in the next section.

## One row per slot (CLEAN-03)

- **CSV write side.** `append_observation` refuses a second row for a (city, UTC instant) in any ISO-8601 spelling. The first write wins; it returns False and logs INFO. Corridor-era files are matched on `corridor`.
- **Read side.** The `duplicate` rule keeps the first row in `read_history`'s stable time order.
- **Why first-write-wins in the CSV.** The file is append-only, so replacing a row would mean rewriting it inside a best-effort path that must never raise, and the CSV only has to make reruns and backfill resumes safe.
- **A deliberate CSV-only divergence, not the Phase 4 contract.** Owner decision OD-7 (REQUIREMENTS.md) governs the Postgres rating table: `valid_time` is the hour-truncated UTC run slot of the window end, a same-slot retry overwrites (`ON CONFLICT (city, valid_time) DO UPDATE`, with `first_written_at` immutable), and the aligned weather hour is stored separately as `observation_time`.
- **The key semantics differ.** The CSV key is the exact `datetime_utc` instant; the Postgres key is the run's hour. On the read side the `same_hour` rule keeps the latest reading in an hour, so the models see one row per hour from either store, the same row an OD-7 overwrite would leave.
- Phase 4 decides how its backfill loader maps CSV rows onto hour slots.

## Using it for validation (Phase 3)

Per city, run `clean_history(read_history(path, city=c), as_of=None)`. `frame["clean_flags"]` and `report["flag_counts"]` give per-rule rates. Raw and usable rows can be compared directly because nothing is overwritten.

## Known limitations

- A row `read_history` drops as invalid still holds its slot for `append_observation`.
- Consumers parse `datetime_utc` themselves and cleaning does not rewrite it, so an archive mixing tz-aware and naive spellings makes `ewm` fall back to row order and `ml` fail to a no-forecast run. Rows from `dlr_orchestrator` and `backfill_archive` are always `%Y-%m-%dT%H:%M:%SZ`.
- A two-hour excursion is not a spike.
- A stuck sensor that repeats within fewer than six rows is not flagged.
- Frames with several cities are rejected, not split.
