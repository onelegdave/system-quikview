# Contributing to System QuikView

Bug reports, hardware compatibility reports, and small focused improvements are welcome.

For a useful report, include your Omarchy and Quickshell versions, the affected section, expected vs. actual behavior, and any relevant GPU vendor/driver. A cropped screenshot is helpful for layout or theme issues. Do not include tokens, private configuration, or process command lines.

## Local workflow

```sh
python3 -m unittest -v
node test_model.cjs
./lint-qml.sh
omarchy-plugin-validate .
python3 install.py
```

Use a local user-plugin installation for development; never edit `/usr/share/omarchy/`. The installer backs up previous local files and configuration. User plugin code should reload automatically; `omarchy restart shell` clears stale components when necessary.

Before sending a change, exercise its actual behavior in the popup. Check both dark and light themes for visual changes. Preserve saved selections and layout order, including when a device disappears or a new one is detected.

The QML lint script uses the installed Omarchy and Quickshell types. It maps the virtual `qs` import prefix in a temporary directory and leaves warning checks enabled. Run it on an Omarchy machine; the Ubuntu CI job covers the Python and JavaScript tests.

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

## Publishing an update

Keep the version consistent across the plugin, GitHub, and the marketplace:

1. Update `manifest.json` for a new plugin version and document the changes.
2. Run the Python tests, model tests, QML lint, and Omarchy manifest validation above. Check affected behavior at runtime.
3. Commit and push using the maintainer's Git identity.
4. Create a matching `vX.Y.Z` Git tag and publish a GitHub Release with that version and clear release notes. Do not move an existing release tag.
5. Update the marketplace submission or its current update process with the same version and a link to the GitHub Release. The marketplace reads the displayed plugin version from `manifest.json`; GitHub's Releases area requires a published release.
6. Verify the release, pushed commit, automated checks, and marketplace status before announcing completion.

For System QuikView, the repository is https://github.com/onelegdave/system-quikview and the initial marketplace submission is https://github.com/omacom/omarchy-plugin-marketplace/issues/6136.
