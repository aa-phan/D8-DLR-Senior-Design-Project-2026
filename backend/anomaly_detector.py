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

v1.3 Phase 2 (02-01, ANOM-01) adds a third, genuinely trained signal:
`_check_against_model`, an additive branch that judges the RAW `wind`/
`temp`/`solar` readings in `raw_data` against a fitted `scikit-learn`
outlier estimator's learned per-variable envelope — never the derived
`rating` the two existing branches judge (D-01). This branch is additive
and one-directional (D-05/D-06): it runs alongside whichever of
`_check_against_forecast`/`_check_against_rolling_baseline` also ran
(never replacing either), and the combined verdict is the logical OR of
every branch that ran — a model's not-anomalous verdict can never
suppress an existing branch's trip, it can only ever add caution on top
of what already exists. This module still must never import
`DLRSafetyMonitor` and still must never catch, swallow, or neutralize an
exception anywhere in it: a broken model — a raising prediction entry
point, a corrupt artifact, a feature-count mismatch — propagates
uncaught, all the way to `DLRSafetyMonitor.run_check`'s existing G6
`except Exception -> _fallback` handler, the single fail-safe boundary
this module relies on. Handling it one layer lower would make a broken
model fail OPEN (silently report not-anomalous) instead of failing SAFE
(resolve to the city's static rating).
"""

import logging
import math
import os

import config

logger = logging.getLogger(__name__)

# One full day of hourly observations -- the shortest window over which a
# mean and a standard deviation carry any meaning. Going lower would
# manufacture confidence the data does not support (D-04 cold-start path).
ROLLING_BASELINE_MIN_ROWS: int = 24


def _model_path_for(city: str) -> str:
    """
    Resolve `city`'s persisted anomaly-model artifact path.

    Raises `ValueError` naming the sorted valid cities when `city`
    is absent from `config.LOCATIONS` -- the closed-set check
    happens unconditionally, as the very first thing this function does,
    so a caller can never coax a filesystem path out of an unvalidated
    string (T-02-02). Only then is the path built, and only from
    `config.ANOMALY_ML_MODEL_DIR` joined with `config.ANOMALY_ML_MODEL_
    FILENAME_TEMPLATE` formatted with the now-validated city -- no
    function on this path ever accepts a caller-supplied filesystem path.
    """
    if city not in config.LOCATIONS:
        raise ValueError(
            f"_model_path_for: unknown city {city!r}; valid "
            f"cities: {sorted(config.LOCATIONS)}"
        )
    filename = config.ANOMALY_ML_MODEL_FILENAME_TEMPLATE.format(city=city)
    return os.path.join(config.ANOMALY_ML_MODEL_DIR, filename)


# Per-city fitted-anomaly-model cache, populated by
# `_load_city_model`. Mirrors `ampacity_forecast._MODEL_CACHE`'s
# load-once-then-cache discipline (RESEARCH.md "Don't Hand-Roll") -- no
# per-call reload, no per-request refit.
_MODEL_CACHE: dict = {}


def _load_city_model(city: str):
    """
    Load (and cache) the persisted fitted anomaly estimator for
    `city`. Strict: raises `FileNotFoundError` naming the city,
    the expected path, and the exact training command when the artifact
    does not exist on disk. Any other failure -- a corrupt artifact, a
    deserialization error -- propagates unmodified.

    Imports `joblib` lazily, inside this function body, which is what
    keeps `import anomaly_detector` free of file I/O, network calls and
    any `sklearn`/`joblib` import -- the two heuristic branches keep
    working in an environment where `scikit-learn` is absent.
    """
    if city in _MODEL_CACHE:
        return _MODEL_CACHE[city]

    path = _model_path_for(city)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"_load_city_model: no trained anomaly model for city "
            f"{city!r} at {path!r}. Train one with: "
            f".venv/bin/python3 backend/anomaly_training.py --city {city}"
        )

    import joblib  # lazy -- keeps `import anomaly_detector` sklearn-free

    model = joblib.load(path)
    _MODEL_CACHE[city] = model
    return model


def _load_city_model_or_none(city: str):
    """
    `_load_city_model`, but an absent artifact resolves to `None`
    (emitting exactly one `logger.warning` naming the city, the
    expected path, and the training command) instead of raising --
    an unprovisioned model leaves `for_city`'s behavior identical to
    today's two-branch detector, since the additive branch was never
    provisioned in the first place (A-04).

    Any OTHER failure -- a corrupt artifact, a deserialization error, an
    unknown city -- is NOT converted to `None`; it propagates
    unmodified. The split is deliberate: an absent file means the branch
    was never provisioned; a present-but-broken file is a real failure
    that must reach G6, not a silently skipped branch.
    """
    path = _model_path_for(city)
    if not os.path.exists(path):
        logger.warning(
            "_load_city_model_or_none: no trained anomaly model for "
            "city %r at %r -- model branch not provisioned. Train "
            "one with: .venv/bin/python3 backend/anomaly_training.py "
            "--city %s",
            city, path, city,
        )
        return None
    return _load_city_model(city)


class AnomalyDetector:
    """
    Constructor takes explicit arguments with `config`-sourced defaults
    resolved when the argument is `None`, mirroring
    `DLRSafetyMonitor.__init__`'s convention.
    """

    def __init__(self, forecast=None, history=None, model=None, k=None,
                 location_key=None, logger=None):
        self.forecast = forecast
        self.history = history
        # v1.3 Phase 2 (ANOM-01): a fitted scikit-learn outlier estimator,
        # or None when the additive model branch is not provisioned.
        # `model_source` names the artifact path `for_city` actually
        # loaded, so a caller/test can see whether the branch is real
        # without re-deriving the path itself. Stays `None` for a bare
        # constructor call and for `for_city(..., load_model=False)`.
        self.model = model
        self.model_source = None
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
    def for_city(cls, city, forecast=None, history=None, logger=None,
                      model=None, load_model=True):
        """
        Build a detector for one city (a key in `config.LOCATIONS`).

        Resolves `k` from `config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION` for
        that city alone, falling back to
        `config.DEFAULT_ANOMALY_CONTROL_LIMIT_K`. A G6 trip resolves to the
        city's own static rating.

        `model`/`load_model` (v1.3 Phase 2, ANOM-01): when `model` is not
        supplied and `load_model` is true (the default), this method
        attempts to lazily load a fitted per-city outlier estimator
        via `_load_city_model_or_none` and passes it into the
        constructed instance. `load_model=False` is the explicit opt-out
        for a caller that wants a heuristics-only detector regardless of
        whether an artifact exists on disk. The returned instance's
        `model_source` attribute names the resolved artifact path when a
        model was actually loaded, or stays `None` otherwise.

        Raises:
            KeyError: if `city` is not in `config.LOCATIONS`, naming the
                valid city keys -- matches `city_point.city_point`'s error
                shape. This check fires before any model-loading attempt.
        """
        if city not in config.LOCATIONS:
            raise KeyError(
                f"Unknown city {city!r}. Valid cities: "
                f"{sorted(config.LOCATIONS)}"
            )

        k = config.ANOMALY_CONTROL_LIMIT_K_BY_LOCATION.get(
            city, config.DEFAULT_ANOMALY_CONTROL_LIMIT_K
        )

        if model is None and load_model:
            model = _load_city_model_or_none(city)

        instance = cls(
            forecast=forecast,
            history=history,
            model=model,
            k=k,
            location_key=city,
            logger=logger,
        )
        if model is not None:
            instance.model_source = _model_path_for(city)
        return instance

    def check(self, raw_data: dict, rating: float) -> tuple[bool, str]:
        """
        Returns `(is_anomalous, reason)`. `rating` is `float(...)`-wrapped
        on entry (RESEARCH.md Pitfall 2).

        A non-finite `rating` never trips G6 itself — G3/G4 already own
        that failure mode, and G6 duplicating it would produce two
        different alert texts for one condition — so a non-finite input
        resolves to `(False, ...)` naming the non-finite value, and the
        model branch (which takes no `rating`) is deliberately not
        consulted on this path either; skipping it here costs nothing.

        Otherwise, up to three branches may run. `_check_against_forecast`
        runs when `self.forecast` is not `None` (the D-04 primary
        signal); else `_check_against_rolling_baseline` runs when
        `self.history` is not `None` and has at least
        `ROLLING_BASELINE_MIN_ROWS` usable `dlr_amps` values (the D-04
        cold-start path) -- these two remain mutually exclusive, exactly
        as before v1.3 Phase 2. Separately and unconditionally,
        `_check_against_model` runs whenever `self.model` is not `None`
        (v1.3 Phase 2, ANOM-01) -- a genuinely new, additive third signal
        that judges the RAW `wind`/`temp`/`solar` readings in `raw_data`,
        never the derived `rating` the first two branches judge (D-01).

        Every branch that ran contributes one `(is_anomalous, reason)`
        result; the combined verdict is `any(...)` over all of them
        (D-06) -- the model branch can only ever ADD a trip on top of
        whichever existing branch also ran, it can never suppress one.
        When exactly one branch ran, the returned reason and `self.signal`
        are that branch's own, verbatim -- unchanged from before this
        phase. When more than one branch ran, the reason joins (with
        `"; "`) the reasons of the branches that voted anomalous when the
        combined verdict is anomalous, or every branch's reason otherwise;
        `self.signal` joins every observed signal with `"+"`.

        When no branch ran at all, resolves to `(False, ...)` naming the
        cold start: the deterministic gates G1-G5 still protect this
        reading, and a learned layer with no signal to check against must
        not manufacture trips it cannot justify. `self.signal` is set
        before every return so a caller — and a failing test — can see
        which branch(es) decided.
        """
        rating = float(rating)

        if not math.isfinite(rating):
            self.signal = "non_finite_guard"
            return False, f"non-finite rating ({rating}) — not a G6 concern, G3/G4 own this"

        verdicts = []
        reasons = []
        signals = []

        if self.forecast is not None:
            is_anom, reason = self._check_against_forecast(rating)
            verdicts.append(is_anom)
            reasons.append(reason)
            signals.append(self.signal)
        elif self.history is not None and "dlr_amps" in self.history.columns:
            usable = self.history["dlr_amps"].dropna()
            if len(usable) >= ROLLING_BASELINE_MIN_ROWS:
                is_anom, reason = self._check_against_rolling_baseline(rating)
                verdicts.append(is_anom)
                reasons.append(reason)
                signals.append(self.signal)

        if self.model is not None:
            is_anom, reason = self._check_against_model(raw_data)
            verdicts.append(is_anom)
            reasons.append(reason)
            signals.append(self.signal)

        if not verdicts:
            self.signal = "cold_start"
            return False, (
                "cold start — no forecast, history, or model signal "
                f"available; G6 defers to G1-G5"
            )

        self.signal = signals[0] if len(signals) == 1 else "+".join(signals)

        is_anomalous = bool(any(verdicts))
        if is_anomalous:
            composed_reason = "; ".join(r for r, v in zip(reasons, verdicts) if v)
        else:
            composed_reason = "; ".join(reasons)

        return is_anomalous, composed_reason

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

    def _check_against_model(self, raw_data: dict) -> tuple[bool, str]:
        """
        The v1.3 Phase 2 additive third branch (D-01, ANOM-01): judges
        the RAW `wind`/`temp`/`solar` readings in `raw_data` against
        `self.model` -- a fitted `scikit-learn` outlier estimator's
        learned per-variable envelope -- never the derived `rating` the
        two existing branches judge.

        Collects every key in `config.ANOMALY_ML_RAW_DATA_KEYS` whose
        value is absent, `None`, or not finite, and raises `ValueError`
        naming that list and this method when the list is non-empty --
        never a default, never a zero, never a skipped prediction
        (T-02-04). A not-anomalous verdict can therefore only ever
        accompany three real, finite readings this estimator actually
        scored.

        Builds a single-row two-dimensional feature matrix by reading
        `raw_data[key]` for each key in `config.ANOMALY_ML_RAW_DATA_KEYS`
        order (positionally the `config.ANOMALY_ML_FEATURE_COLUMNS` order
        the estimator was fitted on), each coerced through `float`. Calls
        the estimator's prediction entry point and applies the
        scikit-learn outlier convention literally: a returned `-1` is an
        outlier, `+1` an inlier. Also reads the estimator's
        `decision_function` for the same row so the reason carries the
        continuous score (negative == outside the learned envelope).

        No handler of any kind: an estimator whose prediction entry point
        raises, a feature-count mismatch, or an unpickled object with no
        prediction entry point at all must all propagate uncaught, to
        G6's existing fail-safe boundary (T-02-03).
        """
        missing = [
            key for key in config.ANOMALY_ML_RAW_DATA_KEYS
            if raw_data.get(key) is None or not math.isfinite(float(raw_data.get(key)))
        ]
        if missing:
            raise ValueError(
                f"_check_against_model: raw_data is missing or has a "
                f"non-finite value for required field(s) {missing}"
            )

        row = [[float(raw_data[key]) for key in config.ANOMALY_ML_RAW_DATA_KEYS]]

        prediction = self.model.predict(row)[0]
        score = float(self.model.decision_function(row)[0])
        is_anomalous = bool(prediction == -1)
        self.signal = "model_trip" if is_anomalous else "model_clean"

        readings = ", ".join(
            f"{feature_col}={raw_data[raw_key]:.2f}"
            for feature_col, raw_key in zip(
                config.ANOMALY_ML_FEATURE_COLUMNS, config.ANOMALY_ML_RAW_DATA_KEYS
            )
        )

        if is_anomalous:
            return True, (
                f"model flagged reading ({readings}) as outside the learned "
                f"per-variable envelope, decision score {score:.4f} "
                f"(negative == outside envelope)"
            )
        return False, (
            f"model judged reading ({readings}) within the learned "
            f"per-variable envelope, decision score {score:.4f} "
            f"(negative == outside envelope)"
        )
