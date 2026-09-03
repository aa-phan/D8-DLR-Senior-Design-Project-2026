import config
import thermal_model


class DLRSafetyMonitor:
    """
    Encapsulates all 5 pipeline safety gates for DLR data validation.
    Call run_check() each measurement cycle; it returns a SafetyResult.
    """

    WIND_BOUNDS   = (0, 50)     # m/s, per IEEE 738
    TEMP_BOUNDS   = (-20, 60)   # °C
    SOLAR_BOUNDS  = (0, 1400)   # W/m²

    def __init__(self, static_rating: float, conductor=None, solar_altitude_deg: float = 45.0,
                 rating_bounds=None, delta_fraction=None, logger=None):
        self.static_rating   = static_rating
        self.conductor        = conductor if conductor is not None else thermal_model.ConductorConfig(
            **config.DEFAULT_CONDUCTOR_CONFIG_KWARGS)
        self.solar_altitude_deg = solar_altitude_deg
        self.rating_bounds    = rating_bounds if rating_bounds is not None else config.DEFAULT_RATING_BOUNDS
        self.delta_fraction   = delta_fraction if delta_fraction is not None else config.DELTA_FRACTION
        self.last_good_rating = static_rating
        self.logger           = logger or print

    def run_check(self, raw_data: dict) -> dict:
        result = {"status": "unknown", "rating": None, "fallback": False, "alerts": []}

        # G1 — Sensor availability
        if not self._gate_sensor(raw_data):
            return self._fallback(result, "G1", "sensor timeout", self.static_rating)

        # G2 — Communication link
        if not self._gate_link(raw_data):
            return self._fallback(result, "G2", "link lost", self.static_rating)

        # G3 — Range validation
        if not self._gate_range(raw_data):
            return self._fallback(result, "G3", "out-of-range", self.static_rating)

        # G4 — Ampacity plausibility
        rating = self._compute_ampacity(raw_data)
        if not self._gate_plausible(rating):
            return self._fallback(result, "G4", f"implausible ({rating:.0f} A)", self.static_rating)

        # G5 — Delta check. A large swing is a fail-safe fallback (DS-NF5),
        # never an optimistic guess: report min(computed, static_rating), and
        # update last_good_rating to the freshly computed value first so a
        # genuine sustained weather change resolves in one cycle rather than
        # latching the monitor in permanent fallback (T-03-05).
        if not self._gate_delta(rating):
            previous = self.last_good_rating
            self.last_good_rating = rating
            return self._fallback(
                result, "G5", f"rating swing {abs(rating - previous):.0f} A",
                min(rating, self.static_rating),
            )

        self.last_good_rating  = rating
        result["status"]       = "ok"
        result["rating"]       = rating
        return result

    def _gate_sensor(self, d):
        return d.get("sensor_status") == "ok" and d.get("wind") is not None and d.get("temp") is not None and d.get("solar") is not None

    def _gate_link(self, d):
        return d.get("link_status") == "ok"

    def _gate_range(self, d):
        return (self.WIND_BOUNDS[0]  <= d["wind"]  <= self.WIND_BOUNDS[1]  and
                self.TEMP_BOUNDS[0]  <= d["temp"]  <= self.TEMP_BOUNDS[1]  and
                self.SOLAR_BOUNDS[0] <= d["solar"] <= self.SOLAR_BOUNDS[1])

    def _gate_plausible(self, rating):
        return self.rating_bounds[0] <= rating <= self.rating_bounds[1]

    def _gate_delta(self, rating) -> bool:
        # Inclusive boundary, matching _gate_plausible/_gate_range's
        # inclusive convention: a delta exactly equal to the threshold is
        # not a swing.
        return abs(rating - self.last_good_rating) <= self.delta_fraction * self.static_rating

    def _compute_ampacity(self, d):
        return float(thermal_model.ieee738_ampacity(
            T_amb_c=d["temp"],
            wind_perp_ms=d["wind"],
            ghi_wm2=d["solar"],
            conductor=self.conductor,
            solar_altitude_deg=self.solar_altitude_deg,
        ))

    def _fallback(self, result, gate, reason, rating):
        msg = f"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"
        self.logger(msg)
        result.update({"status": "fallback", "rating": rating, "fallback": True,
                        "alerts": [msg]})
        return result