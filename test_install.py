import unittest
from install import migrate_settings, PLUGIN_ID, LEGACY_ID


class MigrationTests(unittest.TestCase):
    def test_preserve_position_preferences_and_other_widgets(self):
        original = {'bar': {'layout': {'right': [{'id': 'before'}, {'id': LEGACY_ID, 'metric': 'GPU temperature', 'collapsed': ['cpu']}, {'id': 'after'}]}}, 'idle': {'lock': 1200}}
        result = migrate_settings(original)
        entries = result['bar']['layout']['right']
        self.assertEqual([e['id'] for e in entries], ['before', PLUGIN_ID, 'after'])
        self.assertEqual(entries[1]['metric'], 'GPU temperature')
        self.assertEqual(entries[1]['collapsed'], ['cpu'])
        self.assertEqual(result['idle'], original['idle'])
        self.assertEqual(original['bar']['layout']['right'][1]['id'], LEGACY_ID)
        self.assertEqual(migrate_settings(result), result)

    def test_existing_new_plugin_wins_without_duplicates(self):
        settings = {'bar': {'layout': {'left': [{'id': LEGACY_ID}], 'right': [{'id': PLUGIN_ID, 'metric': 'Memory'}]}}}
        result = migrate_settings(settings)
        self.assertEqual(result['bar']['layout']['left'], [])
        self.assertEqual(result['bar']['layout']['right'][0]['metric'], 'Memory')

    def test_fresh_install(self):
        self.assertEqual(migrate_settings({}), {})


if __name__ == '__main__':
    unittest.main()
