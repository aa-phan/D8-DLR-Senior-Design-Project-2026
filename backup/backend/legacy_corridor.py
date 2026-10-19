"""
Legacy corridor geometry -- FROZEN, for the 2026 forecast-correction
experiment modules only.

The production, shadow, training and documentation paths no longer model
corridors (docs/data-science/decisions/point_scope.md, 2026-10-12): each
city is an independent point (`city_point.city_point`). This module keeps the
great-circle geometry that `forecast_experiment.py` and
`forecast_experiment_audit.py` need to reproduce that completed study, copied
verbatim from the retired `corridor_discretization.py`. Do not import it from
anything else.
"""

import math

import config
import thermal_model

_DEFAULT_POINTS = 5

def initial_bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Forward azimuth (initial compass bearing, degrees) from point 1 to point
    2 along the great circle connecting them. Standard formula, stdlib
    `math` only -- matches `station_explorer.haversine_km`'s style; no geo
    library is used or needed.

    Returns a value in [0, 360).
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlam = math.radians(lon2 - lon1)
    y = math.sin(dlam) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlam)
    theta = math.atan2(y, x)
    return (math.degrees(theta) + 360) % 360


def interpolate_great_circle(
    lat1: float, lon1: float, lat2: float, lon2: float, fraction: float
) -> tuple[float, float]:
    """
    Standard great-circle intermediate-point formula: the point that lies
    `fraction` of the way along the great-circle arc from (lat1, lon1) to
    (lat2, lon2). `fraction=0.0` returns point 1 exactly; `fraction=1.0`
    returns point 2 exactly.

    On a great circle, an equal fraction of the arc IS an equal fraction of
    the distance -- so this single formula satisfies both the "equal
    fraction of arc" and "equal distance" readings of D-04's "evenly spaced"
    requirement; CONTEXT.md left the exact interpolation choice to
    discretion, and this identity is why no separate distance-based
    interpolation is needed.

    The central angle `d` below is `station_explorer.haversine_km`'s own
    `2 * asin(sqrt(a))` expression, without that function's Earth-radius
    factor (`d` is in radians here, not km) -- same haversine math, same
    style, different final scaling.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    lam1, lam2 = math.radians(lon1), math.radians(lon2)

    a = (
        math.sin((phi2 - phi1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin((lam2 - lam1) / 2) ** 2
    )
    d = 2 * math.asin(math.sqrt(a))

    # Identical endpoints -> zero arc length. Guard the division before it
    # happens, rather than letting sin(d)=0 raise ZeroDivisionError.
    if d == 0:
        return (lat1, lon1)

    A = math.sin((1 - fraction) * d) / math.sin(d)
    B = math.sin(fraction * d) / math.sin(d)
    x = A * math.cos(phi1) * math.cos(lam1) + B * math.cos(phi2) * math.cos(lam2)
    y = A * math.cos(phi1) * math.sin(lam1) + B * math.cos(phi2) * math.sin(lam2)
    z = A * math.sin(phi1) + B * math.sin(phi2)
    phi_i = math.atan2(z, math.sqrt(x**2 + y**2))
    lam_i = math.atan2(y, x)
    return (math.degrees(phi_i), math.degrees(lam_i))


def discretize_corridor(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    n_points: int = _DEFAULT_POINTS,
) -> list[tuple[float, float]]:
    """
    Discretize the great-circle corridor between (lat1, lon1) and
    (lat2, lon2) into `n_points` evenly-spaced points (D-03/D-04).

    `result[0]` is always endpoint A exactly; `result[-1]` is always
    endpoint B exactly (when `n_points >= 2`).

    Raises:
        ValueError: if `n_points < 1` -- an empty corridor has no
            defensible minimum and must not silently return `[]`.
    """
    if n_points < 1:
        raise ValueError(f"n_points must be >= 1, got {n_points}")

    if n_points == 1:
        return [(lat1, lon1)]

    return [
        interpolate_great_circle(lat1, lon1, lat2, lon2, i / (n_points - 1))
        for i in range(n_points)
    ]


class CorridorGeometry:
    """
    A corridor's resolved geometry: its endpoints, discretized points, its
    own computed bearing, a `ConductorConfig` carrying that bearing, and the
    corridor-level static rating/plausibility bounds. Plain-class,
    explicit-`__init__` style matching `thermal_model.ConductorConfig`.
    """

    def __init__(
        self,
        name: str,
        endpoint_keys: tuple[str, str],
        endpoint_coords: tuple[tuple[float, float], tuple[float, float]],
        points: list[tuple[float, float]],
        bearing_deg: float,
        conductor: thermal_model.ConductorConfig,
        static_rating: float,
        rating_bounds: tuple[float, float],
    ):
        self.name = name
        self.endpoint_keys = endpoint_keys
        self.endpoint_coords = endpoint_coords
        self.points = points
        self.bearing_deg = bearing_deg
        self.conductor = conductor
        self.static_rating = static_rating
        self.rating_bounds = rating_bounds


def corridor_geometry(
    corridor_name: str, n_points: int = _DEFAULT_POINTS
) -> CorridorGeometry:
    """
    Resolve a named corridor (a key in `config.LEGACY_CORRIDOR_ENDPOINTS`) into its
    full geometry: endpoints, discretized points, computed bearing, a
    per-corridor `ConductorConfig`, and the corridor's static rating/bounds.

    Per 03-RESEARCH Pattern 2, the two D-01 corridors differ by roughly 95
    degrees of bearing (Austin-to-Corpus-Christi runs near north-south,
    Midland-to-El-Paso runs near east-west) -- reusing one global
    `line_azimuth` (the module default of 90.0) would systematically
    mis-model wind cooling on whichever corridor isn't near-east-west. Each
    corridor's bearing is computed here from its own endpoints via
    `initial_bearing_deg` and passed through `config.conductor_kwargs_for`.

    The corridor-level static rating and rating bounds take the MORE
    CONSERVATIVE of the two endpoint cities: `min()` of the two
    `STATIC_RATINGS` values, and `(min of the two lower bounds, min of the
    two upper bounds)`. A corridor is only as strong as its weakest end --
    the same weakest-link principle the point-level `min()` reduction in
    `rate_corridor` (Task 2) applies spatially along the corridor.

    Raises:
        KeyError: if `corridor_name` is not in `config.LEGACY_CORRIDOR_ENDPOINTS`,
            naming the valid corridor names.
    """
    if corridor_name not in config.LEGACY_CORRIDOR_ENDPOINTS:
        raise KeyError(
            f"Unknown corridor {corridor_name!r}. Valid corridors: "
            f"{sorted(config.LEGACY_CORRIDOR_ENDPOINTS)}"
        )

    city_a, city_b = config.LEGACY_CORRIDOR_ENDPOINTS[corridor_name]
    coord_a = config.CITY_COORDINATES[city_a]
    coord_b = config.CITY_COORDINATES[city_b]

    bearing_deg = initial_bearing_deg(coord_a[0], coord_a[1], coord_b[0], coord_b[1])
    conductor = thermal_model.ConductorConfig(**config.conductor_kwargs_for(bearing_deg))

    points = discretize_corridor(coord_a[0], coord_a[1], coord_b[0], coord_b[1], n_points)

    static_rating = min(config.STATIC_RATINGS[city_a], config.STATIC_RATINGS[city_b])
    bounds_a = config.RATING_BOUNDS_BY_LOCATION[city_a]
    bounds_b = config.RATING_BOUNDS_BY_LOCATION[city_b]
    rating_bounds = (min(bounds_a[0], bounds_b[0]), min(bounds_a[1], bounds_b[1]))

    return CorridorGeometry(
        name=corridor_name,
        endpoint_keys=(city_a, city_b),
        endpoint_coords=(coord_a, coord_b),
        points=points,
        bearing_deg=bearing_deg,
        conductor=conductor,
        static_rating=static_rating,
        rating_bounds=rating_bounds,
    )
