#!/usr/bin/env python3
"""Read-only Linux telemetry. One JSON snapshot per line; no external Python packages."""
import argparse
import csv
import ctypes
from functools import lru_cache
import shlex
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def read(path, default=""):
    try:
        return Path(path).read_text().strip()
    except (OSError, ValueError):
        return default


def number(path, scale=1):
    try:
        return float(read(path)) / scale
    except ValueError:
        return None


def cpu_delta(previous, current):
    if previous is None:
        return None
    total = sum(current) - sum(previous)
    idle = current[3] + current[4] - previous[3] - previous[4]
    return round(max(0, min(100, 100 * (total - idle) / total)), 1) if total > 0 else None


def temperature_limit(path):
    value = number(path, 1000)
    # Some drivers expose sentinel values (e.g. NVMe 65535 K) for no limit.
    return value if value is not None and 0 < value <= 150 else None


def temperatures():
    result = []
    for hw in sorted(Path('/sys/class/hwmon').glob('hwmon*')):
        name = read(hw / 'name', hw.name)
        for sensor in sorted(hw.glob('temp*_input')):
            value = number(sensor, 1000)
            if value is not None and -20 < value < 150:
                label = read(sensor.with_name(sensor.name.replace('_input', '_label')), sensor.stem.replace('_input', ''))
                device_path = (hw / 'device').resolve() if (hw / 'device').exists() else hw.resolve().parent
                device = device_path.name
                result.append({'name': name + ' · ' + label, 'label': label,
                               'id': str(device_path / sensor.name), 'device': device,
                               'value': round(value, 1), 'chip': name,
                               'maximum': temperature_limit(sensor.with_name(sensor.name.replace('_input', '_max'))),
                               'critical': temperature_limit(sensor.with_name(sensor.name.replace('_input', '_crit')))})
    return result


class AmdDevicePrefix(ctypes.Structure):
    """Stable prefix of drm_amdgpu_info_device through ids_flags (libdrm ABI)."""
    _fields_ = [(name, ctypes.c_uint32) for name in (
        'device_id', 'chip_rev', 'external_rev', 'pci_rev', 'family',
        'num_shader_engines', 'num_shader_arrays_per_engine', 'gpu_counter_freq')]
    _fields_ += [('max_engine_clock', ctypes.c_uint64), ('max_memory_clock', ctypes.c_uint64),
                 ('cu_active_number', ctypes.c_uint32), ('cu_ao_mask', ctypes.c_uint32),
                 ('cu_bitmap', ctypes.c_uint32 * 16)]
    _fields_ += [(name, ctypes.c_uint32) for name in (
        'enabled_rb_pipes_mask', 'num_rb_pipes', 'num_hw_gfx_contexts', 'pcie_gen')]
    _fields_ += [('ids_flags', ctypes.c_uint64)]


def amd_identity(dev):
    """Ask the AMD driver whether this is an APU; never guess from VRAM size."""
    render = next((dev / 'drm').glob('renderD*'), None)
    if render is None:
        return None, None
    handle = ctypes.c_void_p()
    fd = None
    lib = None
    try:
        lib = ctypes.CDLL('libdrm_amdgpu.so.1')
        lib.amdgpu_device_initialize.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_void_p)]
        lib.amdgpu_device_deinitialize.argtypes = [ctypes.c_void_p]
        lib.amdgpu_query_info.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
        lib.amdgpu_get_marketing_name.argtypes = [ctypes.c_void_p]
        lib.amdgpu_get_marketing_name.restype = ctypes.c_char_p
        fd = os.open('/dev/dri/' + render.name, os.O_RDWR | os.O_CLOEXEC)
        major, minor = ctypes.c_uint32(), ctypes.c_uint32()
        if lib.amdgpu_device_initialize(fd, ctypes.byref(major), ctypes.byref(minor), ctypes.byref(handle)):
            return None, None
        info = AmdDevicePrefix()
        if lib.amdgpu_query_info(handle, 0x16, ctypes.sizeof(info), ctypes.byref(info)):
            return None, None
        name = lib.amdgpu_get_marketing_name(handle)
        return ('integrated' if info.ids_flags & 1 else 'dedicated'), name.decode(errors='replace') if name else None
    except (OSError, AttributeError):
        return None, None
    finally:
        if handle.value and lib:
            lib.amdgpu_device_deinitialize(handle)
        if fd is not None:
            os.close(fd)


@lru_cache(maxsize=32)
def gpu_identity(device_path, vendor, slot):
    dev = Path(device_path)
    role, name = ('dedicated' if vendor == '0x10de' else 'unknown'), None
    if vendor == '0x1002':
        role, name = amd_identity(dev)
        role = role or 'unknown'
    if not name and shutil.which('lspci') and slot:
        try:
            output = subprocess.run(['lspci', '-Dmm', '-s', slot], capture_output=True, text=True, timeout=1)
            fields = shlex.split(output.stdout)
            if len(fields) >= 4:
                name = fields[3]
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return role, name or {'0x1002': 'AMD GPU', '0x8086': 'Intel GPU', '0x10de': 'NVIDIA GPU'}.get(vendor, 'Graphics device')


def gpus():
    result = []
    for card in sorted(Path('/sys/class/drm').glob('card[0-9]*')):
        if '-' in card.name or not (card / 'device').exists():
            continue
        dev = card / 'device'
        vendor = read(dev / 'vendor')
        slot = next((line.split('=', 1)[1] for line in read(dev / 'uevent').splitlines() if line.startswith('PCI_SLOT_NAME=')), '')
        role, name = gpu_identity(str(dev.resolve()), vendor, slot)
        entry = {'id': slot or str(dev.resolve()), 'card': card.name, 'name': name, 'kind': role,
                 'usage': number(dev / 'gpu_busy_percent'), 'temp': None,
                 'used': number(dev / 'mem_info_vram_used'), 'total': number(dev / 'mem_info_vram_total')}
        for hw in sorted((dev / 'hwmon').glob('hwmon*')):
            entry['temp'] = number(hw / 'temp1_input', 1000)
        if vendor == '0x10de' and shutil.which('nvidia-smi') and slot:
            try:
                output = subprocess.run(['nvidia-smi', '-i', slot, '--query-gpu=name,utilization.gpu,temperature.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=1.5)
                if output.returncode != 0:
                    raise ValueError('GPU telemetry unavailable')
                row = next(csv.reader(output.stdout.splitlines()))
                if len(row) != 5:
                    raise ValueError('Unexpected GPU telemetry')
                entry['name'] = row[0].strip()
                for key, value, scale in zip(('usage', 'temp', 'used', 'total'), row[1:], (1, 1, 1024**2, 1024**2)):
                    try:
                        entry[key] = float(value.strip()) * scale
                    except ValueError:
                        entry[key] = None
            except (OSError, subprocess.TimeoutExpired, StopIteration, IndexError, ValueError):
                pass
        result.append(entry)
    return result


class Sampler:
    def __init__(self):
        self.cpus = {}
        self.net = {}
        self.procs = {}
        self.when = None
        self.ticks = os.sysconf('SC_CLK_TCK')

    def sample(self):
        now = time.monotonic()
        elapsed = now - self.when if self.when is not None else None
        cpu = {}
        for line in read('/proc/stat').splitlines():
            fields = line.split()
            if fields and fields[0].startswith('cpu'):
                cpu[fields[0]] = list(map(int, fields[1:9]))  # guest times already included
        usages = {key: cpu_delta(self.cpus.get(key), value) for key, value in cpu.items()}
        self.cpus = cpu
        mem = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in read('/proc/meminfo').splitlines()}
        total = mem.get('MemTotal', 0)
        used = total - mem.get('MemAvailable', total)
        net, networks = {}, []
        for line in read('/proc/net/dev').splitlines()[2:]:
            name, rest = line.split(':', 1)
            name = name.strip()
            if name == 'lo':
                continue
            fields = rest.split()
            net[name] = (int(fields[0]), int(fields[8]))
            old = self.net.get(name)
            rates = [max(0, (net[name][i] - old[i]) / elapsed) for i in (0, 1)] if old and elapsed else [None, None]
            interface = Path('/sys/class/net') / name
            kind = 'Wi-Fi' if (interface / 'wireless').exists() else 'Ethernet' if (interface / 'device').exists() else 'Virtual'
            networks.append({'name': name, 'down': rates[0], 'up': rates[1],
                             'state': read(interface / 'operstate', 'unknown'), 'kind': kind,
                             'received': net[name][0], 'sent': net[name][1]})
        self.net = net
        processes, proc_now = [], {}
        for path in Path('/proc').glob('[0-9]*'):
            stat = read(path / 'stat')
            try:
                end = stat.rindex(')')
                parts = stat[end + 2:].split()
                ticks = int(parts[11]) + int(parts[12])
                key = (path.name, parts[19])  # PID plus start time avoids PID reuse
                proc_now[key] = ticks
                usage = max(0, (ticks - self.procs[key]) / self.ticks / elapsed * 100) if key in self.procs and elapsed else 0
                processes.append({'pid': int(path.name), 'name': stat[stat.index('(') + 1:end], 'cpu': round(usage, 1), 'memory': int(parts[21]) * os.sysconf('SC_PAGE_SIZE')})
            except (ValueError, IndexError):
                continue
        self.procs = proc_now
        processes.sort(key=lambda p: (p['cpu'], p['memory']), reverse=True)
        disks, seen = [], set()
        for line in read('/proc/mounts').splitlines():
            fields = line.split()
            if len(fields) < 3 or not fields[0].startswith('/dev/'):
                continue
            device, mount = fields[0], fields[1].replace('\\040', ' ')
            if device in seen:
                continue
            try:
                usage = shutil.disk_usage(mount)
                seen.add(device)
                disks.append({'name': mount, 'used': usage.used, 'total': usage.total, 'percent': round(100 * usage.used / usage.total, 1)})
            except OSError:
                pass
        temps = temperatures()
        cpu_temps = [t['value'] for t in temps if t['chip'] in ('k10temp', 'coretemp', 'zenpower', 'cpu_thermal')]
        self.when = now
        return {'time': time.time(), 'cpu': usages.get('cpu'), 'cores': [v for k, v in usages.items() if k != 'cpu'],
                'load': list(os.getloadavg()), 'uptime': float(read('/proc/uptime', '0').split()[0]),
                'memory': {'used': used, 'total': total, 'percent': round(100 * used / total, 1) if total else None,
                           'swapUsed': mem.get('SwapTotal', 0) - mem.get('SwapFree', 0), 'swapTotal': mem.get('SwapTotal', 0)},
                'gpus': gpus(), 'temperatures': temps, 'cpuTemp': max(cpu_temps) if cpu_temps else None,
                'networks': networks, 'disks': disks, 'processes': processes[:8]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--interval', type=float, default=2)
    args = parser.parse_args()
    sampler = Sampler()
    if args.once:
        sampler.sample()
        time.sleep(.25)
        print(json.dumps(sampler.sample(), allow_nan=False))
        return
    while True:
        started = time.monotonic()
        try:
            print(json.dumps(sampler.sample(), allow_nan=False), flush=True)
        except BrokenPipeError:
            return
        time.sleep(max(.1, max(1, args.interval) - (time.monotonic() - started)))


if __name__ == '__main__':
    main()
