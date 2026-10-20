"""Fan telemetry: kernel RPM first, optional read-only publisher file second."""
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import patch

import monitor


def hwmon(root, name, files):
    folder = root / name
    folder.mkdir()
    for filename, content in files.items():
        (folder / filename).write_text(content)
    return folder


class HwmonFanTests(unittest.TestCase):
    def test_real_zero_nonzero_labels_and_unusable_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hwmon(root, 'hwmon0', {'name': 'acpi_fan\n', 'fan1_input': '0\n'})
            hwmon(root, 'hwmon1', {'name': 'nct6775\n', 'fan2_input': '1234\n', 'fan2_label': 'CPU fan\n',
                                   'fan3_input': '900\n', 'fan3_fault': '1\n', 'fan4_input': '-1\n',
                                   'fan5_input': '\n', 'fan6_input': 'abc\n', 'fan7_input': '999999\n',
                                   'fan8_input': '١٢\n'})
            readings = monitor.fans(root)
        self.assertEqual([(f['chip'], f['label'], f['rpm']) for f in readings],
                         [('acpi_fan', 'Fan 1', 0), ('nct6775', 'CPU fan', 1234)])
        self.assertTrue(all(f['source'] == 'hwmon' and type(f['rpm']) is int for f in readings))

    def test_no_hwmon_fans(self):
        with tempfile.TemporaryDirectory() as temp:
            hwmon(Path(temp), 'hwmon0', {'name': 'coretemp\n', 'temp1_input': '40000\n'})
            self.assertEqual(monitor.fans(Path(temp)), [])

    def test_hwmon_rpm_has_priority_over_bridge(self):
        rpm = [{'source': 'hwmon', 'rpm': 0}]
        with patch.object(monitor, 'fans', return_value=rpm), patch.object(monitor, 'fan_bridge') as bridge:
            self.assertEqual(monitor.fan_readings(), rpm)
        bridge.assert_not_called()

    def test_bridge_only_without_usable_rpm(self):
        reading = {'source': 'bridge', 'percent': 40.0}
        for fans in ([], OSError('sysfs')):
            kwargs = {'side_effect': fans} if isinstance(fans, Exception) else {'return_value': fans}
            with self.subTest(fans=fans), patch.object(monitor, 'fans', **kwargs), \
                    patch.object(monitor, 'fan_bridge', return_value=reading):
                self.assertEqual(monitor.fan_readings(), [reading])

    def test_optional_failures_leave_other_metrics(self):
        for error in (FileNotFoundError(), PermissionError(), ValueError('bad'), monitor.ToolUnavailable('unsafe'),
                      UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'bad'), RecursionError()):
            with self.subTest(error=error), patch.object(monitor, 'fans', return_value=[]), \
                    patch.object(monitor, 'fan_bridge', side_effect=error), \
                    patch.object(monitor, 'tool_output', return_value=None):
                self.assertEqual(monitor.fan_readings(), [])
                snapshot = monitor.Sampler().sample()
                self.assertEqual(snapshot['fans'], [])
                self.assertGreater(snapshot['memory']['total'], 0)


class BridgeSchemaTests(unittest.TestCase):
    def test_valid_readings_keep_percent_and_state(self):
        cases = [({'raw': 120, 'percent': 47, 'state': 'on'}, 47),
                 ({'raw': 0, 'percent': 0, 'state': 'off'}, 0),
                 ({'raw': 255, 'percent': 99.96, 'state': 'on'}, 100.0),
                 ({'raw': None, 'percent': None, 'state': 'unknown'}, None),
                 ({'raw': 30, 'percent': 12.5, 'state': 'unknown', 'extra': 'ignored'}, 12.5)]
        for data, percent in cases:
            with self.subTest(data=data):
                reading = monitor.fan_bridge_reading(json.dumps(data))
                self.assertEqual((reading['source'], reading['state'], reading['percent']), ('bridge', data['state'], percent))
                self.assertNotIn('rpm', reading)

    def test_invalid_types_ranges_and_documents(self):
        bad = ['{"raw": true, "percent": 10, "state": "on"}', '{"raw": 10, "percent": false, "state": "on"}',
               '{"raw": 10, "percent": NaN, "state": "on"}', '{"raw": 10, "percent": Infinity, "state": "on"}',
               '{"raw": 10, "percent": -Infinity, "state": "on"}', '{"raw": 10, "percent": 1e400, "state": "on"}',
               '{"raw": 10, "percent": -1, "state": "on"}', '{"raw": 10, "percent": 100.01, "state": "on"}',
               '{"raw": 256, "percent": 10, "state": "on"}', '{"raw": -1, "percent": 10, "state": "on"}',
               '{"raw": 10.0, "percent": 10, "state": "on"}', '{"raw": "10", "percent": 10, "state": "on"}',
               '{"raw": 10, "percent": "10", "state": "on"}', '{"raw": 10, "percent": 10, "state": "ON"}',
               '{"raw": 10, "percent": 10, "state": 1}', '{"raw": 10, "percent": 10, "state": ["on"]}',
               '{"raw": 10, "percent": 10, "state": "off"}', '{"raw": 10, "percent": 10}',
               '{"raw": 10, "percent": 10, "state": "on", "state": "off"}', '[10, 10, "on"]', '"on"', '42',
               '{"raw": 10, "percent": 1' + '0' * 5000 + ', "state": "on"}', '', '{', 'null']
        for text in bad:
            with self.subTest(text=text[:60]), self.assertRaises(ValueError):
                monitor.fan_bridge_reading(text)


class BridgeFileTests(unittest.TestCase):
    """Exercise the real descriptor checks on files this test user owns.

    Ancestors above the private fixture directory (such as a sticky /tmp) are
    modelled as trusted root directories; fixture nodes keep their real modes.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name) / 'run'
        self.base.mkdir(mode=0o755)
        self.path = self.base / 'omarchy-fan-speed'
        self.owners = (0, os.getuid())
        above = set()
        for folder in Path(self.temp.name).parents:
            info = os.stat(folder)
            above.add((info.st_dev, info.st_ino))
        tmp = os.stat(self.temp.name)
        above.add((tmp.st_dev, tmp.st_ino))
        actual_stat, actual_fstat = os.stat, os.fstat

        def model(info):
            if (info.st_dev, info.st_ino) not in above:
                return info
            fields = list(info)
            fields[0] &= ~0o7022
            fields[4] = 0
            return os.stat_result(fields)
        self.patches = [patch.object(monitor.os, 'stat', side_effect=lambda *a, **k: model(actual_stat(*a, **k))),
                        patch.object(monitor.os, 'fstat', side_effect=lambda fd: model(actual_fstat(fd)))]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in self.patches:
            item.stop()
        self.temp.cleanup()

    def write(self, content, mode=0o644, age=0):
        self.path.write_bytes(content if isinstance(content, bytes) else content.encode())
        self.path.chmod(mode)
        when = time.time() - age
        os.utime(self.path, (when, when))

    def read(self, **kwargs):
        return monitor.fan_bridge(str(self.path), owners=kwargs.pop('owners', self.owners), **kwargs)

    def test_valid_file(self):
        self.write('{"raw": 87, "percent": 34, "state": "on"}\n')
        reading = self.read()
        self.assertEqual((reading['percent'], reading['raw'], reading['state']), (34, 87, 'on'))

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            self.read()

    def test_freshness_and_future_policy(self):
        for age, accepted in ((0, True), (monitor.FAN_BRIDGE_MAX_AGE - 1, True), (monitor.FAN_BRIDGE_MAX_AGE + 1, False),
                              (-(monitor.FAN_BRIDGE_FUTURE_SLACK - 1), True), (-(monitor.FAN_BRIDGE_FUTURE_SLACK + 3), False),
                              (3600, False), (-86400, False)):
            with self.subTest(age=age):
                self.write('{"raw": 1, "percent": 1, "state": "on"}', age=age)
                if accepted:
                    self.assertEqual(self.read()['percent'], 1)
                else:
                    with self.assertRaisesRegex(ValueError, 'stale'):
                        self.read()

    def test_size_limit(self):
        valid = '{"raw": 1, "percent": 1, "state": "on"}'
        self.write(valid + ' ' * (monitor.FAN_BRIDGE_LIMIT - len(valid)))
        self.assertEqual(self.read()['raw'], 1)
        self.write(valid + ' ' * (monitor.FAN_BRIDGE_LIMIT + 1 - len(valid)))
        with self.assertRaisesRegex(ValueError, 'too large'):
            self.read()

    def test_malformed_and_non_utf8(self):
        original = monitor.fan_bridge
        for content in (b'{"raw": 1, "percent": 1, "state": "on"', b'\xff\xfe', b'{"raw": true, "percent": 1, "state": "on"}',
                        b'[' * 3000 + b']' * 3000):
            with self.subTest(content=content[:20]):
                self.write(content)
                with self.assertRaises((ValueError, RecursionError)):
                    self.read()
                with patch.object(monitor, 'fans', return_value=[]), \
                        patch.object(monitor, 'fan_bridge', lambda: original(str(self.path), owners=self.owners)):
                    self.assertEqual(monitor.fan_readings(), [])

    def test_symlinked_file_and_ancestor(self):
        real = self.base / 'real'
        real.write_text('{"raw": 1, "percent": 1, "state": "on"}')
        self.path.symlink_to(real)
        with self.assertRaises((OSError, monitor.ToolUnavailable)):
            self.read()
        linked = Path(self.temp.name) / 'linked'
        linked.symlink_to(self.base, target_is_directory=True)
        self.path.unlink()
        self.write('{"raw": 1, "percent": 1, "state": "on"}')
        with self.assertRaises((OSError, monitor.ToolUnavailable)):
            monitor.fan_bridge(str(linked / self.path.name), owners=self.owners)
        self.assertEqual(self.read()['percent'], 1)

    def test_fifo_is_refused_without_blocking(self):
        os.mkfifo(self.path, 0o644)
        started = time.monotonic()
        with self.assertRaises(monitor.ToolUnavailable):
            self.read()
        self.assertLess(time.monotonic() - started, 1)

    def test_device_like_nodes_refused(self):
        info = list(os.stat(__file__))
        info[4] = 0
        for kind in (stat.S_IFCHR, stat.S_IFBLK, stat.S_IFSOCK, stat.S_IFIFO, stat.S_IFDIR):
            info[0] = kind | 0o644
            with self.subTest(kind=kind), self.assertRaises(monitor.ToolUnavailable):
                monitor.trusted_node(os.stat_result(info))

    def test_writable_or_untrusted_file_and_ancestor(self):
        for mode in (0o664, 0o646, 0o4644, 0o2644):
            with self.subTest(mode=oct(mode)):
                self.write('{"raw": 1, "percent": 1, "state": "on"}', mode=mode)
                with self.assertRaises(monitor.ToolUnavailable):
                    self.read()
        self.write('{"raw": 1, "percent": 1, "state": "on"}')
        with self.assertRaises(monitor.ToolUnavailable):
            self.read(owners=(0,))
        for mode in (0o775, 0o757, 0o1777):
            with self.subTest(directory=oct(mode)):
                self.base.chmod(mode)
                try:
                    with self.assertRaises(monitor.ToolUnavailable):
                        self.read()
                finally:
                    self.base.chmod(0o755)
        self.assertEqual(self.read()['percent'], 1)

    def test_file_changed_or_growing_while_reading_is_refused(self):
        original = '{"raw": 1, "percent": 1, "state": "on"}'
        actual_read = os.read
        for growth in (b' ', b' ' * (2 * monitor.FAN_BRIDGE_LIMIT)):
            with self.subTest(growth=len(growth)):
                self.write(original)
                calls = []

                def appending(fd, size):
                    if not calls:
                        with open(self.path, 'ab') as stream:
                            stream.write(growth)
                    calls.append(size)
                    return actual_read(fd, size)
                with patch.object(monitor.os, 'read', side_effect=appending):
                    with self.assertRaises(ValueError):
                        self.read()

    def test_in_place_rewrite_same_size_is_refused(self):
        self.write('{"raw": 1, "percent": 1, "state": "on"}', age=5)
        actual_read = os.read

        def rewriting(fd, size):
            data = actual_read(fd, size)
            if data:
                self.path.write_text('{"raw": 2, "percent": 2, "state": "on"}')
            return data
        with patch.object(monitor.os, 'read', side_effect=rewriting):
            with self.assertRaisesRegex(ValueError, 'changed'):
                self.read()

    def test_atomic_replacement_reads_one_complete_inode(self):
        self.write('{"raw": 1, "percent": 1, "state": "on"}')
        actual_read = os.read
        replacement = self.base / 'next'

        def replacing(fd, size):
            if not replacement.exists():
                replacement.write_text('{"raw": 2, "percent": 2, "state": "on"}')
                os.replace(replacement, self.path)
            return actual_read(fd, size)
        with patch.object(monitor.os, 'read', side_effect=replacing):
            self.assertEqual(self.read()['raw'], 1)
        self.assertEqual(self.read()['raw'], 2)


if __name__ == '__main__':
    unittest.main()
