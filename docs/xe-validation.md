# Intel Xe monitoring validation

The Intel `xe` collector change was checked on 2026-09-13 with Core Ultra 200V
integrated graphics (PCI device 8086:64a0). The previous collector detected this
GPU but reported an unknown role and unavailable utilization.

The updated collector identified integrated graphics using the driver's
configuration query. During a short animated QtQuick window test, usage rose
from 0.7% at idle to 25.0–54.2% and returned to 4.1% after the window closed.
Complete telemetry samples took 75–84 ms. This demonstrates responsiveness;
it is not a calibration against an independent whole-device utilization tool.
The estimate covers readable applications owned by the current user.

The driver exposed no GPU hwmon sensor or dedicated VRAM readings. These
remain unavailable; the popup explicitly describes shared system memory.
No elevated GPU permissions, new packages, or driver settings were needed.

Validation completed:

- 54 Python tests, including nine Xe regression tests: duplicate/shared file
  descriptors, multiple GPUs and engine classes, engine capacity, temporary
  counter regression, resets, disappearing clients, scan deadlines, and
  device configuration query failures.
- GPU selection, temperature grouping, layout and palette model tests.
- `bash lint-qml.sh`, `omarchy plugin validate .`, and `git diff --check`.
- 13 telemetry/Xe tests on the Intel machine itself.
- Installed popup: live integrated GPU graph, session estimate explanation,
  shared-memory label, saved settings preserved byte for byte.
- Popup labels inspected in the current dark palette and a temporary light
  shell palette. Original shell palette restored; theme files were not changed.

The full installer security suite must run against actual filesystem ownership;
a remapped agent sandbox can cause its ancestor-ownership assertions to fail.
The suite passed outside that remapped environment without code changes.

Intel discrete Xe and older Intel `i915` hardware have not been tested live.
