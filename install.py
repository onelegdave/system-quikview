#!/usr/bin/env python3
"""Install or update System QuikView, preserving the user's bar position and preferences."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

PLUGIN_ID = 'onelegdave.system-quikview'
LEGACY_ID = 'onelegdave.btop'
FILES = ('manifest.json', 'Panel.qml', 'Sparkline.qml', 'ThemePalette.qml', 'Model.js', 'monitor.py', 'README.md', 'LICENSE')


def migrate_settings(settings):
    result = copy.deepcopy(settings)
    layout = result.get('bar', {}).get('layout', {})
    has_new = any(entry.get('id') == PLUGIN_ID for entries in layout.values() for entry in entries)
    for section, entries in layout.items():
        migrated = []
        for entry in entries:
            if entry.get('id') == LEGACY_ID:
                if has_new:
                    continue
                entry['id'] = PLUGIN_ID
                has_new = True
            migrated.append(entry)
        layout[section] = migrated
    for entry in result.get('plugins', []):
        if entry.get('id') == LEGACY_ID:
            entry['id'] = PLUGIN_ID
    if 'disabledPlugins' in result:
        result['disabledPlugins'] = list(dict.fromkeys(PLUGIN_ID if value == LEGACY_ID else value for value in result['disabledPlugins']))
    return result


def install():
    source = Path(__file__).resolve().parent
    config = Path.home() / '.config/omarchy'
    target = config / 'plugins' / PLUGIN_ID
    legacy = config / 'plugins' / LEGACY_ID
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-' + str(time.time_ns() % 1000000000)
    shell = config / 'shell.json'
    # Validate deliverable before changing the running configuration.
    for name in FILES:
        if not (source / name).is_file():
            raise SystemExit('Missing plugin file: ' + name)
    manifest = json.loads((source / 'manifest.json').read_text())
    if manifest['id'] != PLUGIN_ID:
        raise SystemExit('Manifest ID does not match installer')
    config.mkdir(parents=True, exist_ok=True)
    if shell.exists():
        shutil.copy2(shell, config / ('shell.json.bak-quikview-' + stamp))
    backup_root = config / 'plugin-backups'
    if target.exists():
        shutil.copytree(target, backup_root / (PLUGIN_ID + '-' + stamp))
    target.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        shutil.copy2(source / name, target / name)
    # Read just before mutation so settings chosen while installing survive.
    settings = json.loads(shell.read_text()) if shell.exists() else {}
    migrated = migrate_settings(settings)
    if migrated != settings:
        fd, temp = tempfile.mkstemp(dir=config, prefix='.quikview-')
        try:
            with os.fdopen(fd, 'w') as output:
                json.dump(migrated, output, indent=2)
                output.write('\n')
            if shell.exists():
                shutil.copymode(shell, temp)
            os.replace(temp, shell)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    if legacy.exists():
        backup_root.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(backup_root / (LEGACY_ID + '-' + stamp)))
    subprocess.run(['omarchy-shell', 'shell', 'rescanPlugins'], check=True)
    entries = [entry for section in migrated.get('bar', {}).get('layout', {}).values() for entry in section]
    if not any(entry.get('id') == PLUGIN_ID for entry in entries):
        subprocess.run(['omarchy', 'plugin', 'enable', PLUGIN_ID, '--section', 'right'], check=True)
    print('Installed:', target)
    print('If old code remains cached, run: omarchy restart shell')


if __name__ == '__main__':
    install()
