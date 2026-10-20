# Fan telemetry validation

Version 0.4.7 adds fan readings (issue #1). Checked on 2026-10-19.

## What changed

- The collector reads kernel hwmon `fanN_input` tachometers in RPM. A reading
  of 0 is kept as a real zero. Faulted, unreadable, non-decimal and implausibly
  large values are omitted, not shown as zero.
- Only when no hwmon RPM reading exists, it may read the optional file
  `/run/omarchy-fan-speed` written by a separate publisher. The README
  describes the schema and refusal rules. The percentage is shown as duty,
  never as RPM. Raw values are not converted. Only an `on` or `off` state
  makes the percentage a reading: an `unknown` state is unavailable (shown
  as —, with no gauge) even when the file still holds a number such as 0.
  The collector drops that number and the popup model ignores it as well.
- The popup shows a **Fans** card inside Temperatures. No section key, saved
  order, collapse setting, GPU selection or temperature reading changed.
  While readings are stale, the fan value and summary show unavailable and no
  duty gauge is drawn.
- Qt 6.12 resolves an unqualified `Color` to its own type instead of the
  Omarchy `qs.Commons` singleton. In 0.4.6 this left the popup text, accent and
  derived palette colors undefined (rendered black) and logged 12 warnings.
  `Panel.qml` and `ThemePalette.qml` now use `Commons.Color`, as the Omarchy
  shell does. The new card needed this to render in theme colors.

## Validation

- 21 new Python tests: real 0 and nonzero RPM, labels, faults and invalid
  values, hwmon priority, bridge schema (booleans, NaN/Infinity, overflow,
  ranges, state values, duplicate keys, contradictory `off`, `unknown` with 0,
  a positive number or null kept unavailable), missing,
  malformed, non-UTF-8, oversized, stale and future files, symlinked files and
  ancestors, FIFOs, device-like nodes, group/world-writable or untrusted
  files and directories, a file growing or rewritten during the read, atomic
  replacement, and other readings continuing after a refusal.
- The full suite passed (82 Python tests), with model tests, QML lint and
  `omarchy-plugin-validate`.
- Model tests check that duty is never labeled RPM, that `off` with 0 reads
  0% duty, and that unknown, unexpected or contradictory states never yield a
  percentage or gauge, including in the card summary.
- On a Samsung laptop running Omarchy 4.0.5-1, Quickshell 0.3.2 and Qt 6.12.0,
  the live collector reported the kernel `acpi_fan` tachometer as 0 RPM.
- The real popup was rendered on that machine with invented snapshots in a dark
  and a light theme: two hwmon fans, a duty reading, an unknown state, and no
  fan reading. Unknown states carrying 0 and 40 in `percent`, and `off` with
  0, were also rendered: unknown showed — with no gauge, and off showed 0%
  duty. A stale render showed no duty number or gauge. The rendered card
  texts matched expectations, with no QML warnings. Section order and default visible text were unchanged from 0.4.6
  apart from the About credit; the card appears only when Temperatures is
  expanded.

## Limits

Independent release review on 19 October 2026 reran all 82 Python tests, the Node model tests, QML lint and plugin validation against `8193fe8a78a4ba331c2b001dafb3e12546a18df1`; all passed. Focused native dark/light renders independently checked unknown states with numeric 0 and 40, explicit off with 0, known on duty and kernel RPM. Eight native render/capture scenarios completed without QML errors. Artwork and documentation changes do not change those runtime files; the promotional cover and its source captures use simulated readings.

No HP EliteBook or physical fan-duty publisher was available. The duty path was
tested with test files and invented snapshots, not that hardware or service.
QuikView relies on the publisher rewriting the file at least every 10 seconds.
No other hwmon fan drivers were hardware-validated.
