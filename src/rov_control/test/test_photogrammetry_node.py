import math

import numpy as np

from rov_control.photogrammetry_node import PhotogrammetryNode


def test_rotation_matrix_to_quaternion_identity():
    quat = PhotogrammetryNode.rotation_matrix_to_quaternion(np.eye(3))
    x, y, z, w = quat
    assert math.isclose(x, 0.0, abs_tol=1e-8)
    assert math.isclose(y, 0.0, abs_tol=1e-8)
    assert math.isclose(z, 0.0, abs_tol=1e-8)
    assert math.isclose(w, 1.0, abs_tol=1e-8)


def test_rotation_matrix_to_quaternion_z_90deg():
    theta = math.pi / 2.0
    matrix = np.array(
        [
            [math.cos(theta), -math.sin(theta), 0.0],
            [math.sin(theta), math.cos(theta), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )

    x, y, z, w = PhotogrammetryNode.rotation_matrix_to_quaternion(matrix)

    assert math.isclose(x, 0.0, abs_tol=1e-6)
    assert math.isclose(y, 0.0, abs_tol=1e-6)
    assert math.isclose(z, math.sqrt(0.5), rel_tol=1e-6)
    assert math.isclose(w, math.sqrt(0.5), rel_tol=1e-6)

