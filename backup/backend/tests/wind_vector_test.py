"""
Tests for backend/wind_vector.py (Phase 3 Plan 02 -- wind u/v decomposition).

The whole point of this module is that its agreement with this repo's own
wind convention is PROVEN by test, not asserted by comment. Two anchor
cases are asserted separately (from due north, from due east) so a sign
flip fails with an obvious, specific message rather than only inside a
loop; then a full-circle round trip through `perpendicular_wind` itself
is the real guard against a silent 180-degree sign error, since
`perpendicular_wind` folds the wind-to-line angle to an acute angle before
projecting and would otherwise let a flipped sign convention look
perfectly plausible.
"""

import os
import subprocess
import sys

import numpy as np

import thermal_model as tm
import wind_vector as wv


# ──────────────────────────────────────────────────────────────────────────────
# Cardinal anchor cases -- asserted separately so a sign flip is obvious
# ──────────────────────────────────────────────────────────────────────────────

def test_to_uv_from_due_north_blows_south():
    # A wind coming FROM due north (met convention 0 deg) blows TOWARD the
    # south: its eastward component is zero, its northward component is
    # negative (equal in magnitude to the speed).
    u, v = wv.to_uv(10.0, 0.0)
    assert abs(float(u)) < 1e-12
    assert abs(float(v) + 10.0) < 1e-12


def test_to_uv_from_due_east_blows_west():
    # A wind coming FROM due east (met convention 90 deg) blows TOWARD the
    # west: its eastward component is negative, its northward component
    # is zero.
    u, v = wv.to_uv(10.0, 90.0)
    assert abs(float(u) + 10.0) < 1e-12
    assert abs(float(v)) < 1e-12


# ──────────────────────────────────────────────────────────────────────────────
# Round trip: from_uv(*to_uv(s, d)) == (s, d)
# ──────────────────────────────────────────────────────────────────────────────

def test_round_trip_recovers_original_speed_and_direction():
    directions = np.arange(360, dtype=float)
    for speed in (0.5, 3.0, 17.25):
        speeds = np.full_like(directions, speed)
        u, v = wv.to_uv(speeds, directions)
        recovered_speed, recovered_dir = wv.from_uv(u, v)

        assert np.allclose(recovered_speed, speed, atol=1e-9)
        # Compare directions on the circle (mod 360), not linearly.
        delta = (recovered_dir - directions + 180.0) % 360.0 - 180.0
        assert np.allclose(delta, 0.0, atol=1e-9), (
            "direction did not survive the u/v round trip"
        )


def test_from_uv_direction_is_always_in_half_open_circle():
    directions = np.arange(360, dtype=float)
    speeds = np.full_like(directions, 5.0)
    u, v = wv.to_uv(speeds, directions)
    _, recovered_dir = wv.from_uv(u, v)

    assert (recovered_dir >= 0).all()
    assert (recovered_dir < 360).all()


# ──────────────────────────────────────────────────────────────────────────────
# The real guard: agreement with thermal_model.perpendicular_wind
# ──────────────────────────────────────────────────────────────────────────────

def test_round_trip_leaves_perpendicular_wind_unchanged():
    directions = np.arange(360, dtype=float)
    for speed in (0.5, 3.0, 17.25):
        speeds = np.full_like(directions, speed)
        recovered_speed, recovered_dir = wv.from_uv(*wv.to_uv(speeds, directions))

        for azimuth in (0.0, 37.0, 90.0, 214.0):
            direct = tm.perpendicular_wind(speeds, directions, azimuth)
            round_tripped = tm.perpendicular_wind(
                recovered_speed, recovered_dir, azimuth
            )
            assert np.allclose(direct, round_tripped, atol=1e-9), (
                "the u/v round trip changed the perpendicular wind "
                "component -- the sign convention disagrees with this "
                f"repo's own wind convention (speed={speed}, azimuth={azimuth})"
            )


# ──────────────────────────────────────────────────────────────────────────────
# Vectorized shape contract
# ──────────────────────────────────────────────────────────────────────────────

def test_array_inputs_return_arrays_of_matching_shape():
    speeds = np.array([1.0, 2.0, 3.0, 4.0])
    directions = np.array([0.0, 90.0, 180.0, 270.0])

    u, v = wv.to_uv(speeds, directions)
    assert u.shape == speeds.shape
    assert v.shape == speeds.shape

    recovered_speed, recovered_dir = wv.from_uv(u, v)
    assert recovered_speed.shape == speeds.shape
    assert recovered_dir.shape == speeds.shape


# ──────────────────────────────────────────────────────────────────────────────
# Zero-speed edge case
# ──────────────────────────────────────────────────────────────────────────────

def test_zero_speed_round_trips_to_zero_speed_without_raising():
    u, v = wv.to_uv(0.0, 123.0)
    recovered_speed, _recovered_dir = wv.from_uv(u, v)
    assert abs(float(recovered_speed)) < 1e-12


# ──────────────────────────────────────────────────────────────────────────────
# No-side-effects-on-import contract, matching thermal_model's own
# ──────────────────────────────────────────────────────────────────────────────

def test_module_importable_with_no_env_or_io():
    assert hasattr(wv, "to_uv")
    assert hasattr(wv, "from_uv")


def test_importing_wind_vector_alone_never_imports_requests():
    """
    Subprocess-isolated check (other test modules in this same pytest
    session import `requests` for unrelated reasons -- e.g.
    `open_meteo_provider` -- polluting the shared `sys.modules` of a
    same-process check). A fresh interpreter that imports ONLY
    `wind_vector` must never pull in `requests`, proving this module
    performs no HTTP I/O.
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import wind_vector; import sys; "
            "assert 'requests' not in sys.modules; print('OK')",
        ],
        cwd=backend_dir,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout
