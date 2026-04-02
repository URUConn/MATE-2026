"""Generate a printable checkerboard calibration pattern as SVG.

Default output matches the current calibration workflow:
- 9x6 inner corners
- 25 mm square size
"""

import argparse
from pathlib import Path


DEFAULT_INNER_COLUMNS = 9
DEFAULT_INNER_ROWS = 6
DEFAULT_SQUARE_SIZE_MM = 25.0
DEFAULT_MARGIN_MM = 10.0


def build_checkerboard_svg(
    inner_columns: int,
    inner_rows: int,
    square_size_mm: float,
    margin_mm: float,
) -> str:
    """Build checkerboard SVG content with physical dimensions in mm.

    OpenCV chessboard uses inner corners. Number of drawn squares is +1 in each
    dimension.
    """
    if inner_columns < 2 or inner_rows < 2:
        raise ValueError('inner_columns and inner_rows must both be >= 2')
    if square_size_mm <= 0.0:
        raise ValueError('square_size_mm must be > 0')
    if margin_mm < 0.0:
        raise ValueError('margin_mm must be >= 0')

    squares_x = inner_columns + 1
    squares_y = inner_rows + 1

    board_w = squares_x * square_size_mm
    board_h = squares_y * square_size_mm
    svg_w = board_w + 2.0 * margin_mm
    svg_h = board_h + 2.0 * margin_mm

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
            f'width="{svg_w:.3f}mm" height="{svg_h:.3f}mm" '
            f'viewBox="0 0 {svg_w:.3f} {svg_h:.3f}">'
        ),
        f'  <rect x="0" y="0" width="{svg_w:.3f}" height="{svg_h:.3f}" fill="white"/>',
        (
            f'  <rect x="{margin_mm:.3f}" y="{margin_mm:.3f}" '
            f'width="{board_w:.3f}" height="{board_h:.3f}" '
            'fill="white" stroke="black" stroke-width="0.3"/>'
        ),
    ]

    for y in range(squares_y):
        for x in range(squares_x):
            if (x + y) % 2 == 0:
                continue
            rx = margin_mm + x * square_size_mm
            ry = margin_mm + y * square_size_mm
            lines.append(
                f'  <rect x="{rx:.3f}" y="{ry:.3f}" '
                f'width="{square_size_mm:.3f}" height="{square_size_mm:.3f}" fill="black"/>'
            )

    lines.extend(
        [
            '  <!-- Print at 100% scale (no fit-to-page) for accurate square size. -->',
            (
                f'  <!-- Inner corners: {inner_columns}x{inner_rows}, '
                f'square: {square_size_mm:.3f} mm -->'
            ),
            '</svg>',
        ]
    )
    return '\n'.join(lines) + '\n'


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Generate a printable SVG checkerboard for camera calibration.'
    )
    parser.add_argument(
        '--inner-columns',
        type=int,
        default=DEFAULT_INNER_COLUMNS,
        help='Number of inner corners across columns (default: 9).',
    )
    parser.add_argument(
        '--inner-rows',
        type=int,
        default=DEFAULT_INNER_ROWS,
        help='Number of inner corners across rows (default: 6).',
    )
    parser.add_argument(
        '--square-size-mm',
        type=float,
        default=DEFAULT_SQUARE_SIZE_MM,
        help='Physical square size in millimeters (default: 25).',
    )
    parser.add_argument(
        '--margin-mm',
        type=float,
        default=DEFAULT_MARGIN_MM,
        help='White margin around the board in millimeters (default: 10).',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('checkerboard_9x6_25mm.svg'),
        help='Output SVG path.',
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    svg = build_checkerboard_svg(
        inner_columns=args.inner_columns,
        inner_rows=args.inner_rows,
        square_size_mm=args.square_size_mm,
        margin_mm=args.margin_mm,
    )

    output_path = args.output.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(svg, encoding='utf-8')

    print(f'Wrote checkerboard: {output_path}')
    print('Print at 100% scale (disable fit-to-page).')


if __name__ == '__main__':
    main()

