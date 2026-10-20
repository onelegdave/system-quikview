# Fan telemetry validation

Version 0.4.7 adds fan readings (issue #1). Checked on 2026-10-19.

## What changed

- The collector reads kernel hwmon `fanN_input` tachometers in RPM. A reading
  of 0 is kept as a real zero. Faulted, unreadable, non-decimal and implausibly
  large values are omitted, not shown as zero.
- Only when no hwmon RPM reading exists, it may read the optional file
  `/run/omarchy-fan-speed` written by a separate publisher. The README
  describes the schema and refusal rules. The percentage is shown as duty,
  never as RPM. Raw values are not converted.
- The popup shows a **Fans** card inside Temperatures. No section key, saved
  order, collapse setting, GPU selection or temperature reading changed.
- Qt 6.12 resolves an unqualified `Color` to its own type instead of the
  Omarchy `qs.Commons` singleton. In 0.4.6 this left the popup text, accent and
  derived palette colors undefined (rendered black) and logged 12 warnings.
  `Panel.qml` and `ThemePalette.qml` now use `Commons.Color`, as the Omarchy
  shell does. The new card needed this to render in theme colors.

## Validation

- 19 new Python tests: real 0 and nonzero RPM, labels, faults and invalid
  values, hwmon priority, bridge schema (booleans, NaN/Infinity, overflow,
  ranges, state values, duplicate keys, contradictory `off`), missing,
  malformed, non-UTF-8, oversized, stale and future files, symlinked files and
  ancestors, FIFOs, device-like nodes, group/world-writable or untrusted
  files and directories, a file growing or rewritten during the read, atomic
  replacement, and other readings continuing after a refusal.
- The full suite passed (80 Python tests), with model tests, QML lint and
  `omarchy-plugin-validate`.
- Model tests check that duty is never labeled RPM and unknown is never 0.
- On a Samsung laptop running Omarchy 4.0.5-1, Quickshell 0.3.2 and Qt 6.12.0,
  the live collector reported the kernel `acpi_fan` tachometer as 0 RPM.
- The real popup was rendered on that machine with invented snapshots in a dark
  and a light theme: two hwmon fans, a duty reading, an unknown state, and no
  fan reading. The rendered card texts matched expectations, with no QML
  warnings. Section order and default visible text were unchanged from 0.4.6
  apart from the About credit; the card appears only when Temperatures is
  expanded.

## Limits

No HP EliteBook or physical fan-duty publisher was available. The duty path was
tested with test files and invented snapshots, not that hardware or service.
QuikView relies on the publisher rewriting the file at least every 10 seconds.
No other hwmon fan drivers were hardware-validated.
