import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rov_slam.checkerboard_generator import build_checkerboard_svg


def test_svg_contains_expected_dimensions_and_metadata() -> None:
    svg = build_checkerboard_svg(
        inner_columns=9,
        inner_rows=6,
        square_size_mm=25.0,
        margin_mm=10.0,
    )

    # 10 squares x 7 squares with 25 mm size + 10 mm margins each side.
    assert 'width="270.000mm"' in svg
    assert 'height="195.000mm"' in svg
    assert 'Inner corners: 9x6, square: 25.000 mm' in svg


def test_svg_has_expected_black_square_count() -> None:
    svg = build_checkerboard_svg(
        inner_columns=9,
        inner_rows=6,
        square_size_mm=25.0,
        margin_mm=10.0,
    )

    # 10*7 checkerboard has 35 black squares plus one black border stroke line.
    assert svg.count('fill="black"') == 35


