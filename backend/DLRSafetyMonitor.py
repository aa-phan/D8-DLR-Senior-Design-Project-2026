class DLRSafetyMonitor:
    """
    Encapsulates all 5 pipeline safety gates for DLR data validation.
    Call run_check() each measurement cycle; it returns a SafetyResult.
    """

    WIND_BOUNDS   = (0, 50)     # m/s, per IEEE 738
    TEMP_BOUNDS   = (-20, 60)   # °C
    SOLAR_BOUNDS  = (0, 1400)   # W/m²
    RATING_BOUNDS = (400, 1800) # A — plausibility check
    DELTA_THRESH  = 150         # A — alert threshold

    def __init__(self, static_rating: float, logger=None):
        self.static_rating   = static_rating
        self.last_good_rating = static_rating
        self.logger           = logger or print

    def run_check(self, raw_data: dict) -> dict:
        result = {"status": "unknown", "rating": None, "fallback": False, "alerts": []}

        # G1 — Sensor availability
        if not self._gate_sensor(raw_data):
            return self._fallback(result, "G1", "sensor timeout", self.last_good_rating)

        # G2 — Communication link
        if not self._gate_link(raw_data):
            return self._fallback(result, "G2", "link lost", self.last_good_rating)

        # G3 — Range validation
        if not self._gate_range(raw_data):
            return self._fallback(result, "G3", "out-of-range", self.static_rating)

        # G4 — Ampacity plausibility
        rating = self._compute_ampacity(raw_data)
        if not self._gate_plausible(rating):
            return self._fallback(result, "G4", f"implausible ({rating:.0f} A)", self.static_rating)

        # G5 — Delta check
        delta = abs(rating - self.last_good_rating)
        if delta > self.DELTA_THRESH:
            result["alerts"].append(f"Rating change {delta:.0f} A exceeds threshold")

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
        return self.RATING_BOUNDS[0] <= rating <= self.RATING_BOUNDS[1]

    def _compute_ampacity(self, d):
        # Simplified IEEE 738 — replace with your full thermal model
        return 900 + d["wind"] * 30 - (d["temp"] - 20) * 4 - d["solar"] * 0.05

    def _fallback(self, result, gate, reason, rating):
        msg = f"{gate} FAIL ({reason}) — fallback rating {rating:.0f} A"
        self.logger(msg)
        result.update({"status": "fallback", "rating": rating, "fallback": True,
                        "alerts": [msg]})
        return result