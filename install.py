#!/usr/bin/env python3
"""Install or update System QuikView, preserving the user's bar position and preferences."""
import copy
import json
import os
from pathlib import Path
import stat
import secrets
from contextlib import contextmanager, ExitStack

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


# Linux-only installer, like the telemetry collector. Every destination is
# addressed relative to an opened directory, never through a joined write path.
MAX_CONFIG = 1024 * 1024
MAX_FILE = 32 * 1024 * 1024
MAX_BACKUP = 128 * 1024 * 1024
MAX_ENTRIES = 4096


class UnsafePath(ValueError):
    pass


def validate(info, directory=False, ancestor=False):
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    owners = (0, os.getuid()) if ancestor else (os.getuid(),)
    if not expected(info.st_mode) or info.st_uid not in owners:
        raise UnsafePath('Refusing a path with an unexpected type or owner')
    if directory and info.st_mode & 0o022:
        raise UnsafePath('Refusing a group/world-writable directory')
    if not directory and (info.st_nlink != 1 or info.st_mode & 0o022):
        raise UnsafePath('Refusing a hard-linked or group/world-writable file')


def component(name):
    if not name or name in ('.', '..') or '/' in name:
        raise UnsafePath('Invalid path component')


def inspect(parent, name, directory=False):
    component(name)
    try:
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    except FileNotFoundError:
        return None
    validate(info, directory)
    return info


@contextmanager
def directory(parent, name, create=False):
    component(name)
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent)
        except FileExistsError:
            pass
    fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        validate(os.fstat(fd), directory=True)
        yield fd
    finally:
        os.close(fd)


@contextmanager
def home_directory(path):
    # Do not resolve(): resolving would silently accept symlinked components.
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise UnsafePath('Home must be an absolute path without traversal')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            # Ancestors may be root-owned. A sticky /tmp is permitted only as
            # an ancestor (for isolated installs/tests), never as the home.
            info = os.fstat(fd)
            if info.st_uid == 0 and info.st_mode & stat.S_ISVTX:
                if not stat.S_ISDIR(info.st_mode):
                    raise UnsafePath('Invalid ancestor')
            else:
                validate(info, directory=True, ancestor=True)
        validate(os.fstat(fd), directory=True)
        yield fd
    finally:
        os.close(fd)


def signature(info):
    if info is None:
        return None
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_file(parent, name, limit=MAX_FILE):
    info = inspect(parent, name)
    if info is None:
        return None, None
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    try:
        current = os.fstat(fd)
        validate(current)
        if signature(current) != signature(info):
            raise UnsafePath('File changed while opening: ' + name)
        if current.st_size > limit:
            raise UnsafePath('File exceeds size limit: ' + name)
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b''.join(chunks)
        if len(data) > limit or signature(os.fstat(fd)) != signature(info):
            raise UnsafePath('File grew or changed while reading: ' + name)
        return data, info
    finally:
        os.close(fd)


def atomic_write(parent, name, data, expected=None, mode=0o600):
    if signature(inspect(parent, name)) != signature(expected):
        raise UnsafePath('Destination changed before writing: ' + name)
    temporary = '.quikview-' + secrets.token_hex(16)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                 0o600, dir_fd=parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            validate(os.fstat(output.fileno()))
            output.write(data)
            output.flush()
            os.fchmod(output.fileno(), mode & 0o777 & ~0o022)
            os.fsync(output.fileno())
        if signature(inspect(parent, name)) != signature(expected):
            raise UnsafePath('Destination changed before replacement: ' + name)
        # rename replaces the directory entry itself; it cannot follow a
        # symlink substituted after the validation above.
        os.replace(temporary, name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass


def snapshot_tree(parent, budget=None, depth=0):
    if budget is None:
        budget = [MAX_BACKUP, MAX_ENTRIES]
    if depth > 32:
        raise UnsafePath('Backup nesting limit exceeded')
    result = {}
    for name in os.listdir(parent):
        budget[1] -= 1
        if budget[1] < 0:
            raise UnsafePath('Too many backup entries')
        info = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            with directory(parent, name) as child:
                result[name] = snapshot_tree(child, budget, depth + 1)
        else:
            data, info = read_file(parent, name, min(MAX_FILE, budget[0]))
            if info is None:
                raise UnsafePath('Backup entry disappeared')
            budget[0] -= len(data)
            result[name] = (data, stat.S_IMODE(info.st_mode))
    return result


def write_tree(parent, tree):
    for name, value in tree.items():
        if isinstance(value, dict):
            # Backup destinations must be new; never merge into a preexisting tree.
            os.mkdir(name, 0o700, dir_fd=parent)
            with directory(parent, name) as child:
                write_tree(child, value)
        else:
            atomic_write(parent, name, value[0], mode=value[1])


def install_files(home, source):
    # Preload the fixed deliverable with bounded, nofollow reads.
    with home_directory(source) as source_fd:
        deliverable = {}
        for name in FILES:
            data, info = read_file(source_fd, name)
            if info is None:
                raise UnsafePath('Missing plugin file: ' + name)
            deliverable[name] = (data, stat.S_IMODE(info.st_mode))
    if json.loads(deliverable['manifest.json'][0])['id'] != PLUGIN_ID:
        raise UnsafePath('Manifest ID does not match installer')

    with ExitStack() as stack:
        home_fd = stack.enter_context(home_directory(home))
        config_parent = stack.enter_context(directory(home_fd, '.config', create=True))
        config = stack.enter_context(directory(config_parent, 'omarchy', create=True))
        plugins = stack.enter_context(directory(config, 'plugins', create=True))
        backups = stack.enter_context(directory(config, 'plugin-backups', create=True))
        raw, shell_info = read_file(config, 'shell.json', MAX_CONFIG)
        settings = json.loads(raw) if raw is not None else {}
        migrated = migrate_settings(settings)
        entries = [entry for section in migrated.get('bar', {}).get('layout', {}).values() for entry in section]
        if not any(entry.get('id') == PLUGIN_ID for entry in entries):
            migrated.setdefault('bar', {}).setdefault('layout', {}).setdefault('right', []).append({'id': PLUGIN_ID})
            if 'disabledPlugins' in migrated:
                migrated['disabledPlugins'] = [name for name in migrated['disabledPlugins'] if name != PLUGIN_ID]
        # Validate ALL existing trees before overwriting any installed file.
        trees = {}
        targets = {}
        for name in (PLUGIN_ID, LEGACY_ID):
            if inspect(plugins, name, directory=True) is not None:
                targets[name] = stack.enter_context(directory(plugins, name))
                trees[name] = snapshot_tree(targets[name])
                if name == PLUGIN_ID:
                    for filename in FILES:
                        inspect(targets[name], filename)
        stamp = secrets.token_hex(16)
        for name, tree in trees.items():
            backup_name = name + '-' + stamp
            os.mkdir(backup_name, 0o700, dir_fd=backups)
            with directory(backups, backup_name) as backup:
                write_tree(backup, tree)
        if raw is not None:
            atomic_write(config, 'shell.json.bak-quikview-' + stamp, raw,
                         mode=stat.S_IMODE(shell_info.st_mode))
        if PLUGIN_ID not in targets:
            # Refuse a concurrent/pre-positioned target instead of opening it.
            os.mkdir(PLUGIN_ID, 0o700, dir_fd=plugins)
            targets[PLUGIN_ID] = stack.enter_context(directory(plugins, PLUGIN_ID))
        target = targets[PLUGIN_ID]
        for name, (data, mode) in deliverable.items():
            atomic_write(target, name, data, expected=inspect(target, name), mode=mode)
        if migrated != settings:
            atomic_write(config, 'shell.json', (json.dumps(migrated, indent=2) + '\n').encode(),
                         expected=shell_info, mode=stat.S_IMODE(shell_info.st_mode) if shell_info else 0o600)
        if LEGACY_ID in targets:
            # Archive by rename within the validated plugins directory; no
            # recursive deletion and no traversal through the old tree.
            current = inspect(plugins, LEGACY_ID, directory=True)
            opened = os.fstat(targets[LEGACY_ID])
            if current is None or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
                raise UnsafePath('Legacy target changed before archival')
            os.rename(LEGACY_ID, '.' + LEGACY_ID + '.retired-' + stamp,
                      src_dir_fd=plugins, dst_dir_fd=plugins)
        return migrated


def install():
    home = Path.home()
    install_files(home, Path(__file__).absolute().parent)
    print('Installed:', home / '.config/omarchy/plugins' / PLUGIN_ID)
    print('To load or refresh the plugin, run: omarchy restart shell')


if __name__ == '__main__':
    try:
        install()
    except (OSError, ValueError) as error:
        raise SystemExit('Installation refused: ' + str(error)) from error
