# Contributing to System QuikView

Bug reports, hardware compatibility reports, and small focused improvements are welcome.

For a useful report, include your Omarchy and Quickshell versions, the affected section, expected vs. actual behavior, and any relevant GPU vendor/driver. A cropped screenshot is helpful for layout or theme issues. Do not include tokens, private configuration, or process command lines.

## Local workflow

```sh
python3 -m unittest -v
node test_model.cjs
omarchy-plugin-validate .
python3 install.py
```

Use a local user-plugin installation for development; never edit `/usr/share/omarchy/`. The installer backs up previous local files and configuration. User plugin code should reload automatically; `omarchy restart shell` clears stale components when necessary.

Before sending a change, exercise its actual behavior in the popup. Check both dark and light themes for visual changes. Preserve saved selections and layout order, including when a device disappears or a new one is detected.

## Useful diagnostics

```sh
omarchy version
quickshell --version
omarchy-shell shell ping
python3 monitor.py --once
omarchy-shell onelegdave.system-quikview status
omarchy-shell onelegdave.system-quikview open
omarchy-shell onelegdave.system-quikview customize
omarchy-shell onelegdave.system-quikview close
```

The `status` output includes the displayed and rendered section order, active colors, selected GPU, and popup geometry. Telemetry output includes local hardware identifiers and process names; review it before attaching it to a public issue.

Other controls:

```sh
omarchy-shell onelegdave.system-quikview metric 'GPU temperature'
omarchy-shell onelegdave.system-quikview source auto
omarchy-shell onelegdave.system-quikview move network -1
omarchy-shell onelegdave.system-quikview scrollBy 200
```

Keep the collector read-only, avoid new required dependencies when the kernel already provides the information, and report unavailable values explicitly.
