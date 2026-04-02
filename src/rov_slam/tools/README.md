# Checkerboard Generator

Use the `rov_slam` checkerboard helper to generate a print-ready SVG for camera calibration.

Default output matches the calibration node defaults:
- inner corners: `9 x 6`
- square size: `25 mm`

## Quick Run

```bash
cd ~/MATE-2026
source install/setup.bash
ros2 run rov_slam generate_checkerboard
```

This writes `checkerboard_9x6_25mm.svg` in the current directory.

## Custom Run

```bash
ros2 run rov_slam generate_checkerboard -- \
  --inner-columns 9 \
  --inner-rows 6 \
  --square-size-mm 25 \
  --margin-mm 10 \
  --output ~/checkerboards/rov_checkerboard.svg
```

Print with **100% scale** (disable fit-to-page) so square dimensions stay accurate.

