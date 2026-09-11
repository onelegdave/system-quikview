import unittest
from unittest.mock import patch
import monitor

class TelemetryTests(unittest.TestCase):
    def test_cpu_warmup_and_delta(self):
        self.assertIsNone(monitor.cpu_delta(None, [0]*8))
        self.assertEqual(monitor.cpu_delta([0]*8, [20,0,10,60,10,0,0,0]), 30)
        self.assertIsNone(monitor.cpu_delta([1]*8, [1]*8))

    def test_invalid_driver_temperature_limits(self):
        for raw, expected in [('88000', 88), ('65261850', None), ('0', None), ('', None)]:
            with self.subTest(raw=raw), patch.object(monitor, 'read', return_value=raw):
                self.assertEqual(monitor.temperature_limit('/sensor'), expected)

    def test_unreadable_sensor(self):
        with patch.object(monitor, 'read', return_value=''):
            self.assertIsNone(monitor.number('/missing'))

    def test_snapshot_missing_optional_gpu_tool(self):
        with patch.object(monitor, 'tool_output', return_value=None):
            snapshot = monitor.Sampler().sample()
        self.assertIsNone(snapshot['cpu'])
        self.assertGreater(snapshot['memory']['total'], 0)
        self.assertTrue(all(g['usage'] is None or 0 <= g['usage'] <= 100 for g in snapshot['gpus']))

if __name__ == '__main__':
    unittest.main()
