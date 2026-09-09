"""
Learned Anomaly Detection (C10)
==================================================
This module is C10 per `docs/data-science/specs/C10-anomaly-detection.md`.

This module produces a two-tuple of a boolean and a reason string, and
nothing else. The decision about what a trip means to a reported rating
belongs entirely to `DLRSafetyMonitor` (D-05) — this class must never
build the monitor's own `{status, rating, fallback, alerts}` result
mapping and must never import `DLRSafetyMonitor`.

Per D-04, the primary anomaly signal is the live rating compared against
C9's own empirical residual band (widened by a per-location control-limit
multiplier, D-06) — not an independent model. When no forecast is
available yet (cold start), `check` falls back to a rolling mean ± k ·
rolling-standard-deviation band computed directly over archived
`dlr_amps` history, so the detector still functions before C9 has enough
data to forecast from.
"""

import math

import config

# One full day of hourly observations -- the shortest window over which a
# mean and a standard deviation carry any meaning. Going lower would
# manufacture confidence the data does not support (D-04 cold-start path).
ROLLING_BASELINE_MIN_ROWS: int = 24


class AnomalyDetector:
    """
    Constructor takes explicit arguments with `config`-sourced defaults
    resolved when the argument is `None`, mirroring
    `DLRSafetyMonitor.__init__`'s convention.
    """

    def __init__(self, forecast=None, history=None, k=None, location_key=None, logger=None):
        self.forecast = forecast
        self.history = history
        self.location_key = location_key
        self.k = float(
            k if k is not None
            else config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION.get(
                location_key, config.DEFAULT_ANOMALY_CONTROL_LIMIT_K
            )
        )
        self.logger = logger or print
        # Which branch produced the most recent check() decision -- lets a
        # caller (and a test) see which signal decided without re-deriving
        # it. "not_yet_evaluated" until check() has run at least once.
        self.signal = "not_yet_evaluated"

    @classmethod
    def for_corridor(cls, corridor_name, forecast=None, history=None, logger=None):
        """
        Build a detector for a named corridor (a key in
        `config.CORRIDOR_ENDPOINTS` -- the same mapping
        `corridor_discretization.corridor_geometry` uses, so a corridor's
        cities can never be defined twice).

        Resolves `k` from `config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` for
        each of the corridor's two endpoint cities (falling back to
        `config.DEFAULT_ANOMALY_CONTROL_LIMIT_K` for either), then takes
        the LARGER of the two. This deliberately runs opposite to
        `corridor_geometry`'s `min()` weakest-link reduction: there,
        conservative means the lower rating; here, per D-06, conservative
        means the wider band and fewer false trips. Either direction, a
        G6 trip still resolves to the corridor's static rating -- the
        fallback target is unaffected by which endpoint's k dominates.

        Raises:
            KeyError: if `corridor_name` is not in
                `config.CORRIDOR_ENDPOINTS`, naming the valid corridor
                names -- matches `corridor_geometry`'s existing error
                shape.
        """
        if corridor_name not in config.CORRIDOR_ENDPOINTS:
            raise KeyError(
                f"Unknown corridor {corridor_name!r}. Valid corridors: "
                f"{sorted(config.CORRIDOR_ENDPOINTS)}"
            )

        city_a, city_b = config.CORRIDOR_ENDPOINTS[corridor_name]
        k_a = config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION.get(
            city_a, config.DEFAULT_ANOMALY_CONTROL_LIMIT_K
        )
        k_b = config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION.get(
            city_b, config.DEFAULT_ANOMALY_CONTROL_LIMIT_K
        )
        k = max(k_a, k_b)

        return cls(
            forecast=forecast,
            history=history,
            k=k,
            location_key=corridor_name,
            logger=logger,
        )

    def check(self, raw_data: dict, rating: float) -> tuple[bool, str]:
        """
        Returns `(is_anomalous, reason)`. `rating` is `float(...)`-wrapped
        on entry (RESEARCH.md Pitfall 2).

        A non-finite `rating` never trips G6 itself — G3/G4 already own
        that failure mode, and G6 duplicating it would produce two
        different alert texts for one condition — so a non-finite input
        resolves to `(False, ...)` naming the non-finite value.

        Dispatches to `_check_against_forecast` when `self.forecast` is
        not `None` (the D-04 primary signal), else to
        `_check_against_rolling_baseline` when `self.history` is not
        `None` and has at least `ROLLING_BASELINE_MIN_ROWS` usable
        `dlr_amps` values (the D-04 cold-start path), else resolves to
        `(False, ...)` naming the cold start: the deterministic gates
        G1-G5 still protect this reading, and a learned layer with no
        signal to check against must not manufacture trips it cannot
        justify. `self.signal` is set before every return so a caller —
        and a failing test — can see which branch decided.
        """
        rating = float(rating)

        if not math.isfinite(rating):
            self.signal = "non_finite_guard"
            return False, f"non-finite rating ({rating}) — not a G6 concern, G3/G4 own this"

        if self.forecast is not None:
            return self._check_against_forecast(rating)

        if self.history is not None and "dlr_amps" in self.history.columns:
            usable = self.history["dlr_amps"].dropna()
            if len(usable) >= ROLLING_BASELINE_MIN_ROWS:
                return self._check_against_rolling_baseline(rating)

        self.signal = "cold_start"
        return False, (
            "cold start — no forecast available and history has fewer than "
            f"{ROLLING_BASELINE_MIN_ROWS} usable rows; G6 defers to G1-G5"
        )

    def _check_against_forecast(self, rating: float) -> tuple[bool, str]:
        """
        The D-04 primary signal: widens each of the forecast's band edges
        away from its center by `self.k`. Lower limit is
        `center + k * (ci_lower_amps - center)`, upper limit is
        `center + k * (ci_upper_amps - center)`. A rating strictly outside
        `[lower, upper]` is anomalous; a rating exactly on either limit is
        not — the same inclusive-boundary convention
        `DLRSafetyMonitor._gate_plausible`/`_gate_delta` already use.
        """
        self.signal = "forecast_residual"

        center = self.forecast.amps
        lower = center + self.k * (self.forecast.ci_lower_amps - center)
        upper = center + self.k * (self.forecast.ci_upper_amps - center)

        if lower <= rating <= upper:
            return False, (
                f"rating {rating:.1f} A within widened forecast band "
                f"[{lower:.1f}, {upper:.1f}] A (center {center:.1f} A)"
            )

        deviation = rating - center
        return True, (
            f"rating {rating:.1f} A deviates {deviation:+.1f} A from forecast center "
            f"{center:.1f} A, outside widened band [{lower:.1f}, {upper:.1f}] A"
        )

    def _check_against_rolling_baseline(self, rating: float) -> tuple[bool, str]:
        """
        The D-04 cold-start path: take the `dlr_amps` column from
        `self.history`, drop nulls, compute the mean and the sample
        standard deviation, and treat `rating` as anomalous when it lies
        strictly outside `mean ± self.k * std`. Same inclusive-boundary
        convention as the forecast branch.

        When the standard deviation is zero or non-finite, returns
        `(False, ...)` — a degenerate baseline has no discriminating
        power and tripping on it would fire on every single reading.
        """
        self.signal = "rolling_baseline"

        series = self.history["dlr_amps"].dropna()
        mean = float(series.mean())
        std = float(series.std())

        if not math.isfinite(std) or std == 0.0:
            return False, (
                f"rolling baseline standard deviation is degenerate ({std}) — "
                "no discriminating power, not flagging"
            )

        lower = mean - self.k * std
        upper = mean + self.k * std

        if lower <= rating <= upper:
            return False, (
                f"rating {rating:.1f} A within rolling-baseline band "
                f"[{lower:.1f}, {upper:.1f}] A (mean {mean:.1f} A)"
            )

        deviation = rating - mean
        return True, (
            f"rating {rating:.1f} A deviates {deviation:+.1f} A from rolling baseline mean "
            f"{mean:.1f} A, outside band [{lower:.1f}, {upper:.1f}] A"
        )
