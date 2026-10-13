"""
City point (C8, per-city rating location)
==================================================
Each project city is one independent rating point: its own coordinate
(`config.CITY_COORDINATES`), static rating (`config.STATIC_RATINGS`),
plausibility bounds (`config.RATING_BOUNDS_BY_LOCATION`) and line bearing
(`config.CITY_LINE_BEARING_DEG`). There is no corridor, no pairing of cities
and no min()-reduction across points -- see
`docs/data-science/decisions/point_scope.md`.

`city_point(city)` replaces the retired `corridor_discretization.
corridor_geometry(corridor)` for every production, shadow and training
caller. Importing this module has no side effects.
"""

import config
import thermal_model


class CityPoint:
    """
    A city's resolved rating point: coordinate, line bearing, a
    `ConductorConfig` carrying that bearing, and the city's own static
    rating and plausibility bounds. Plain-class, explicit-`__init__` style
    matching `thermal_model.ConductorConfig`.
    """

    def __init__(
        self,
        name: str,
        coord: tuple[float, float],
        bearing_deg: float,
        conductor: thermal_model.ConductorConfig,
        static_rating: float,
        rating_bounds: tuple[float, float],
    ):
        self.name = name
        self.coord = coord
        self.bearing_deg = bearing_deg
        self.conductor = conductor
        self.static_rating = static_rating
        self.rating_bounds = rating_bounds


def city_point(city: str) -> CityPoint:
    """
    Resolve a city (a key in `config.LOCATIONS`) into its `CityPoint`.

    Raises:
        KeyError: if `city` is not in `config.LOCATIONS`, naming the valid
            city keys. This is also the closed-set guard model-artifact path
            builders rely on (T-01-03).
    """
    if city not in config.LOCATIONS:
        raise KeyError(
            f"Unknown city {city!r}. Valid cities: {sorted(config.LOCATIONS)}"
        )

    bearing_deg = config.CITY_LINE_BEARING_DEG[city]
    conductor = thermal_model.ConductorConfig(**config.conductor_kwargs_for(bearing_deg))

    return CityPoint(
        name=city,
        coord=config.CITY_COORDINATES[city],
        bearing_deg=bearing_deg,
        conductor=conductor,
        static_rating=config.STATIC_RATINGS[city],
        rating_bounds=config.RATING_BOUNDS_BY_LOCATION[city],
    )
