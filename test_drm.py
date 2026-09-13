"""Driver-neutral utilization fallback and identification recovery regressions."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import monitor


def timed(driver='i915', busy=0, capacity=1):
    return (f'drm-driver: {driver}\ndrm-pdev: 0000:03:00.0\ndrm-client-id: 42\n'
            f'drm-engine-render: {busy} ns\ndrm-engine-capacity-render: {capacity}\n')


class DrmTests(unittest.TestCase):
    def test_i915_and_other_standard_time_counters(self):
        for driver in ('i915', 'amdgpu', 'nouveau', 'future-driver'):
            with self.subTest(driver=driver):
                usage = monitor.DrmUsage()
                first = monitor.drm_fdinfo(timed(driver), now_ns=1_000_000_000)
                second = monitor.drm_fdinfo(timed(driver, 500_000_000), now_ns=3_000_000_000)
                self.assertEqual(usage.sample(dict([first])), {})
                self.assertEqual(usage.sample(dict([second])), {'0000:03:00.0': 25})

    def test_time_units_capacity_and_driver_transition(self):
        usage = monitor.DrmUsage()
        usage.sample(dict([monitor.drm_fdinfo(timed(capacity=2), now_ns=1_000_000_000)]))
        self.assertEqual(usage.sample(dict([monitor.drm_fdinfo(timed(busy=1_000_000_000, capacity=2), now_ns=2_000_000_000)])), {'0000:03:00.0': 50})
        self.assertEqual(usage.sample(dict([monitor.drm_fdinfo(timed('another-driver', busy=9_000_000_000), now_ns=3_000_000_000)])), {})
        for text in (timed().replace('0 ns', '0 ms'), timed().replace('0 ns', '0'), timed(capacity=0), timed(busy=-1)):
            self.assertEqual(monitor.drm_fdinfo(text)[1], {})

    def test_one_source_per_engine_and_format_changes_warm_up(self):
        both = timed() + 'drm-cycles-render: 10\ndrm-total-cycles-render: 100\n'
        key, engines = monitor.drm_fdinfo(both, now_ns=1000)
        self.assertEqual(engines, {'ns:render': (0, 1000, 1)})
        usage = monitor.DrmUsage()
        usage.sample({key: engines})
        cycles = both.replace('drm-engine-render: 0 ns\n', '')
        self.assertEqual(usage.sample(dict([monitor.drm_fdinfo(cycles)])), {})

    def test_non_pci_device_mapping_and_duplicate_descriptors(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = Path(tmp) / '123'
            (proc / 'fd').mkdir(parents=True)
            (proc / 'fdinfo').mkdir()
            for fd in ('4', '5'):
                (proc / 'fd' / fd).symlink_to('/dev/dri/renderD130')
                (proc / 'fdinfo' / fd).write_text(timed('panfrost').replace('drm-pdev: 0000:03:00.0\n', ''))
            self.assertEqual(monitor.drm_clients({'platform/gpu'}, Path(tmp)), {})
            clients = monitor.drm_clients({'platform/gpu'}, Path(tmp), {'/dev/dri/renderD130': 'platform/gpu'})
            self.assertEqual(list(clients), [('platform/gpu', 'panfrost', '42')])

    def test_identity_failure_is_retried_and_driver_change_reprobes(self):
        with tempfile.TemporaryDirectory() as tmp:
            dev = Path(tmp)
            (dev / 'driver').symlink_to('/sys/bus/pci/drivers/xe')
            (dev / 'device').write_text('0x1234')
            monitor.cached_gpu_identity.cache_clear()
            with patch.object(monitor, 'xe_identity', side_effect=['unknown', 'integrated']) as query, patch.object(monitor, 'tool_output', return_value=None), patch.object(monitor.time, 'monotonic', return_value=1) as clock:
                self.assertEqual(monitor.gpu_identity(tmp, '0x8086', '0000:03:00.0')[0], 'unknown')
                self.assertEqual(monitor.gpu_identity(tmp, '0x8086', '0000:03:00.0')[0], 'unknown')
                self.assertEqual(query.call_count, 1)
                clock.return_value = 31
                self.assertEqual(monitor.gpu_identity(tmp, '0x8086', '0000:03:00.0')[0], 'integrated')
                (dev / 'driver').unlink()
                (dev / 'driver').symlink_to('/sys/bus/pci/drivers/i915')
                self.assertEqual(monitor.gpu_identity(tmp, '0x8086', '0000:03:00.0')[0], 'unknown')
            monitor.cached_gpu_identity.cache_clear()

    def gpu_tree(self, root, vendor, busy=None):
        dev = root / 'device0'
        (dev / 'drm' / 'card7').mkdir(parents=True)
        (dev / 'drm' / 'renderD130').mkdir()
        (dev / 'vendor').write_text(vendor)
        (dev / 'uevent').write_text('PCI_SLOT_NAME=0000:03:00.0')
        if busy is not None:
            (dev / 'gpu_busy_percent').write_text(str(busy))
        card = root / 'drm' / 'card7'
        card.mkdir(parents=True)
        (card / 'device').symlink_to(dev)
        return root / 'drm'

    def test_driver_specific_readings_take_precedence(self):
        for vendor, busy, output, expected in [('0x1002', 12, None, 12), ('0x10de', None, 'NVIDIA GPU, 37, 55, 100, 200', 37)]:
            with self.subTest(vendor=vendor), tempfile.TemporaryDirectory() as tmp:
                drm = self.gpu_tree(Path(tmp), vendor, busy)
                path_class = Path
                def paths(value):
                    return drm if str(value) == '/sys/class/drm' else path_class(value)
                with patch.object(monitor, 'Path', side_effect=paths), patch.object(monitor, 'gpu_identity', return_value=('dedicated', 'GPU')), patch.object(monitor, 'tool_output', return_value=output), patch.object(monitor, 'drm_clients') as fallback:
                    gpu = monitor.gpus(monitor.DrmUsage())[0]
                self.assertEqual(gpu['usage'], expected)
                self.assertNotIn('usageSource', gpu)
                fallback.assert_not_called()

    def test_missing_driver_specific_reading_uses_standard_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            drm = self.gpu_tree(Path(tmp), '0x8086')
            path_class = Path
            def paths(value):
                return drm if str(value) == '/sys/class/drm' else path_class(value)
            frames = [dict([monitor.drm_fdinfo(timed(), now_ns=1000)]), dict([monitor.drm_fdinfo(timed(busy=250), now_ns=2000)]), {}]
            usage = monitor.DrmUsage()
            with patch.object(monitor, 'Path', side_effect=paths), patch.object(monitor, 'gpu_identity', return_value=('unknown', 'Intel GPU')), patch.object(monitor, 'drm_clients', side_effect=frames):
                self.assertIsNone(monitor.gpus(usage)[0]['usage'])
                gpu = monitor.gpus(usage)[0]
                self.assertEqual(gpu['usage'], 25)
                self.assertEqual(gpu['usageSource'], 'drm-fdinfo')
                self.assertIsNone(gpu['used'])
                self.assertEqual(gpu['kind'], 'unknown')
                missing = monitor.gpus(usage)[0]
                self.assertIsNone(missing['usage'])
                self.assertNotIn('usageSource', missing)


if __name__ == '__main__':
    unittest.main()
