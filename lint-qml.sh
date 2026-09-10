#!/usr/bin/env bash
# Resolve Quickshell's virtual qs import prefix for standalone qmllint.
set -euo pipefail
cd -- "$(dirname -- "$0")"
shell_dir="${OMARCHY_PATH:-/usr/share/omarchy}/shell"
lint_bin="${QMLLINT:-/usr/lib/qt6/bin/qmllint}"
if [[ ! -x "$lint_bin" ]]; then
  lint_bin="$(command -v qmllint)"
fi
[[ -d "$shell_dir/Ui" && -d "$shell_dir/Commons" ]] || {
  echo "Omarchy shell imports not found: $shell_dir" >&2
  exit 1
}
import_dir="$(mktemp -d)"
trap 'rm -rf -- "$import_dir"' EXIT
ln -s -- "$shell_dir" "$import_dir/qs"
"$lint_bin" -I "$import_dir" Panel.qml ThemePalette.qml Sparkline.qml
