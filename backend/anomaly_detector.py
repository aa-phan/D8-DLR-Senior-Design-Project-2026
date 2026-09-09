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
multiplier, D-06) — not an independent model.
"""

import math

import config


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

    def check(self, raw_data: dict, rating: float) -> tuple[bool, str]:
        """
        Returns `(is_anomalous, reason)`. `rating` is `float(...)`-wrapped
        on entry (RESEARCH.md Pitfall 2).

        A non-finite `rating` never trips G6 itself — G3/G4 already own
        that failure mode, and G6 duplicating it would produce two
        different alert texts for one condition — so a non-finite input
        resolves to `(False, ...)` naming the non-finite value.

        When `self.forecast` is `None` (cold start), resolves to
        `(False, ...)` naming the cold start: the deterministic gates
        G1-G5 still protect this reading, and a learned layer with no
        history must not manufacture trips it cannot justify.

        Otherwise widens each of the forecast's band edges away from its
        center by `self.k`: lower limit is
        `center + k * (ci_lower_amps - center)`, upper limit is
        `center + k * (ci_upper_amps - center)`. A rating strictly outside
        `[lower, upper]` is anomalous; a rating exactly on either limit is
        not — the same inclusive-boundary convention
        `DLRSafetyMonitor._gate_plausible`/`_gate_delta` already use.
        """
        rating = float(rating)

        if not math.isfinite(rating):
            return False, f"non-finite rating ({rating}) — not a G6 concern, G3/G4 own this"

        if self.forecast is None:
            return False, "cold start — no forecast available yet, G6 defers to G1-G5"

        center = self.forecast.amps
        lower = center + self.k * (self.forecast.ci_lower_amps - center)
        upper = center + self.k * (self.forecast.ci_upper_amps - center)

        if lower <= rating <= upper:
            return False, (
                f"rating {rating:.1f} A within widened band "
                f"[{lower:.1f}, {upper:.1f}] A (center {center:.1f} A)"
            )

        deviation = rating - center
        return True, (
            f"rating {rating:.1f} A deviates {deviation:+.1f} A from forecast center "
            f"{center:.1f} A, outside widened band [{lower:.1f}, {upper:.1f}] A"
        )
