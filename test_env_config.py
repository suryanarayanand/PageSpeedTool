from pathlib import Path
import tempfile
import unittest

from env_config import load_local_env


class LocalEnvironmentTests(unittest.TestCase):
    def test_loads_local_keys_and_preserves_explicit_environment_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text('# local settings\nPAGESPEED_API_KEY="local-test-key"\n'
                            'CRUX_API_KEY=crux-test-key # optional\nPAGESPEED_COLLECTOR=api\n'
                            'HOME=do-not-change\nGITHUB_TOKEN=do-not-load\n', encoding='utf-8')
            environment = {'PAGESPEED_API_KEY': 'existing-test-key'}
            loaded = load_local_env(path, environment)
            self.assertEqual(environment, {'PAGESPEED_API_KEY': 'existing-test-key',
                                           'CRUX_API_KEY': 'crux-test-key', 'PAGESPEED_COLLECTOR': 'api'})
            self.assertEqual(loaded, {'CRUX_API_KEY', 'PAGESPEED_COLLECTOR'})

    def test_missing_and_blank_files_need_no_key_and_never_expand_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            environment = {}
            self.assertEqual(load_local_env(path, environment), set())
            path.write_text('PAGESPEED_API_KEY=\nCRUX_API_KEY=\n', encoding='utf-8')
            self.assertEqual(load_local_env(path, environment), set())
            path.write_text("PAGESPEED_API_KEY='$(do-not-execute)'\n", encoding='utf-8')
            load_local_env(path, environment)
            self.assertEqual(environment['PAGESPEED_API_KEY'], '$(do-not-execute)')

    def test_invalid_values_do_not_leak_the_file_contents_in_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '.env'
            path.write_text('PAGESPEED_API_KEY="private-test-value\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Invalid quoting') as raised:
                load_local_env(path, {})
            self.assertNotIn('private-test-value', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
