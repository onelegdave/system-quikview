"""Xe regressions: duplicate FDs, multiple engines/devices, resets and access limits."""
import ctypes
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import monitor


def fdinfo(client=7, slot='0000:00:02.0', busy=100, total=1000, capacity=1):
    return (f'drm-driver:\txe\ndrm-client-id:\t{client}\ndrm-pdev:\t{slot}\n'
            f'drm-cycles-rcs:\t{busy}\ndrm-total-cycles-rcs:\t{total}\n'
            f'drm-engine-capacity-rcs:\t{capacity}\n')


class XeTests(unittest.TestCase):
    def test_parse_actual_xe_format(self):
        key, engines = monitor.drm_fdinfo(fdinfo() + 'drm-total-gtt:\t68416 KiB\n')
        self.assertEqual(key, ('0000:00:02.0', 'xe', '7'))
        self.assertEqual(engines, {'cycles:rcs': (100, 1000, 1)})
        self.assertEqual(monitor.drm_fdinfo(fdinfo().replace('drm-engine-capacity-rcs:\t1\n', ''))[1], engines)

    def test_invalid_and_incomplete_counters(self):
        for text in [fdinfo().replace('drm-driver', 'missing'), fdinfo().replace('drm-client-id', 'missing'), '']:
            self.assertIsNone(monitor.drm_fdinfo(text))
        for text in [fdinfo(capacity=0), fdinfo(busy=-1), fdinfo(busy='NaN'), fdinfo().replace('drm-total-cycles', 'missing')]:
            self.assertEqual(monitor.drm_fdinfo(text)[1], {})

    def test_usage_warmup_idle_and_load(self):
        sampler = monitor.DrmUsage()
        self.assertEqual(sampler.sample(dict([monitor.drm_fdinfo(fdinfo())])), {})
        self.assertEqual(sampler.sample(dict([monitor.drm_fdinfo(fdinfo(total=2000))])), {'0000:00:02.0': 0})
        self.assertEqual(sampler.sample(dict([monitor.drm_fdinfo(fdinfo(busy=350, total=3000))])), {'0000:00:02.0': 25})

    def test_capacity_and_concurrent_engines_and_devices(self):
        sampler = monitor.DrmUsage()
        first = {('A', '1'): {'rcs': (0, 1000, 1), 'ccs': (0, 1000, 4)},
                 ('A', '2'): {'rcs': (0, 1000, 1)}, ('B', '1'): {'rcs': (0, 1000, 1)}}
        second = {('A', '1'): {'rcs': (200, 2000, 1), 'ccs': (2000, 2000, 4)},
                  ('A', '2'): {'rcs': (200, 2000, 1)}, ('B', '1'): {'rcs': (900, 2000, 1)}}
        sampler.sample(first)
        self.assertEqual(sampler.sample(second), {'A': 50, 'B': 90})

    def test_counter_regression_keeps_high_water_mark(self):
        sampler = monitor.DrmUsage()
        def sample(busy, total):
            return sampler.sample({('A', '1'): {'rcs': (busy, total, 1)}})
        sample(100, 1000)
        self.assertEqual(sample(50, 1000), {})
        self.assertEqual(sample(50, 2000), {'A': 0})
        self.assertEqual(sample(150, 3000), {'A': 5})
        self.assertEqual(sample(0, 10), {})  # reset/wrap: establish a baseline
        self.assertEqual(sample(50, 110), {'A': 50})
        self.assertEqual(sample(50, 110), {})  # stopped GPU clock

    def test_missing_new_clients_and_failed_scans_need_warmup(self):
        sampler = monitor.DrmUsage()
        a = {('A', '1'): {'cycles:rcs': (100, 1000, 1)}}
        sampler.sample(a)
        self.assertEqual(sampler.sample({}), {})
        self.assertEqual(sampler.sample(a), {})
        self.assertEqual(sampler.sample(None), {})
        self.assertEqual(sampler.sample(a), {})
        self.assertEqual(sampler.sample({('A', '2'): {'rcs': (9000, 10000, 1)}}), {})

    def test_saturated_reading_is_bounded(self):
        sampler = monitor.DrmUsage()
        sampler.sample({('A', '1'): {'rcs': (0, 10, 1)}})
        self.assertEqual(sampler.sample({('A', '1'): {'rcs': (1000, 20, 1)}}), {'A': 100})

    def test_scan_deduplicates_across_processes_and_devices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for pid in ('1', '2'):
                (root / pid / 'fdinfo').mkdir(parents=True)
                (root / pid / 'fd').mkdir()
                for fd, text in [('3', fdinfo()), ('4', fdinfo()), ('5', fdinfo(slot='0000:01:00.0'))]:
                    (root / pid / 'fdinfo' / fd).write_text(text)
                    (root / pid / 'fd' / fd).symlink_to('/dev/dri/renderD128')
                (root / pid / 'fdinfo' / '6').write_text(fdinfo(client=99))
                (root / pid / 'fd' / '6').symlink_to('/dev/null')
            clients = monitor.drm_clients({'0000:00:02.0', '0000:01:00.0'}, root)
            self.assertEqual(len(clients), 2)
            self.assertEqual(len(monitor.drm_clients({'0000:00:02.0'}, root)), 1)
            with patch.object(monitor.os, 'readlink', side_effect=PermissionError):
                self.assertEqual(monitor.drm_clients({'0000:00:02.0'}, root), {})
            with patch.object(monitor.time, 'monotonic', side_effect=[0, 1]):
                self.assertIsNone(monitor.drm_clients({'0000:00:02.0'}, root))

    def test_xe_identity_query_flags_and_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            dev = Path(tmp)
            (dev / 'drm' / 'renderD128').mkdir(parents=True)
            def query(fd, request, buffer):
                self.assertEqual(request, 0xc0286440)
                self.assertEqual(struct.unpack_from('=I', buffer, 8)[0], 2)
                size = struct.unpack_from('=I', buffer, 12)[0]
                if not size:
                    struct.pack_into('=I', buffer, 12, response_size)
                else:
                    ptr = struct.unpack_from('=Q', buffer, 16)[0]
                    ctypes.memmove(ptr, struct.pack('=IIQQ', 2, 0, 0x64a0, flags), 24)
            # A real safe character FD avoids mocking stat and close behavior.
            original_open = os.open
            with patch.object(monitor.os, 'open', side_effect=lambda *a: original_open('/dev/null', os.O_RDONLY)), patch.object(monitor.fcntl, 'ioctl', side_effect=query):
                response_size, flags = 24, 0
                self.assertEqual(monitor.xe_identity(dev), 'integrated')
                flags = 1
                self.assertEqual(monitor.xe_identity(dev), 'dedicated')
                response_size = 8192
                self.assertEqual(monitor.xe_identity(dev), 'unknown')
            with patch.object(monitor.os, 'open', side_effect=PermissionError):
                self.assertEqual(monitor.xe_identity(dev), 'unknown')


if __name__ == '__main__':
    unittest.main()
