import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tarfile
import unittest
from unittest.mock import patch

import engine
import server
from progressive_report import update_progressive
from test_progressive import saved_run
from export_cloud_data import export_data


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.config_patch = patch.dict(server.app.config, {
            'CLOUD_MODE': True, 'PUBLIC_REPORTS': True, 'REQUIRE_HTTPS': True,
            'ALLOW_BROWSER': False, 'ALLOWED_REPORT_HOSTS': {'reports.example.com'},
            'ADMIN_USERNAME': 'owner', 'ADMIN_PASSWORD': 'test-management-password',
        })
        self.output_patch = patch.object(server, 'OUTPUT', Path(self.temporary.name))
        self.active_patch = patch.object(server, 'active', None)
        self.config_patch.start()
        self.output_patch.start()
        self.active_patch.start()
        self.client = server.app.test_client()
        self.base_url = 'https://reports.example.com'
        self.auth = {'Authorization': 'Basic ' + base64.b64encode(b'owner:test-management-password').decode()}

    def tearDown(self):
        self.active_patch.stop()
        self.output_patch.stop()
        self.config_patch.stop()
        self.temporary.cleanup()

    def test_public_report_links_need_no_login_and_root_has_no_audit_controls(self):
        response = self.client.get('/', base_url=self.base_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Daily PageSpeed reports', response.data)
        self.assertNotIn(b'Generate report', response.data)
        self.assertNotIn(server.TOKEN.encode(), response.data)
        update_progressive(saved_run('saved', '2026-10-27T09:00:00+00:00'), server.OUTPUT)
        self.assertEqual(self.client.get('/progressive/status', base_url=self.base_url).get_json()['runs'], 1)
        response = self.client.get('/progressive/report.xlsx', base_url=self.base_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[:2], b'PK')
        response.close()
        response = self.client.get('/progressive/report.html', base_url=self.base_url)
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_management_and_audit_start_require_credentials_and_request_token(self):
        self.assertEqual(self.client.get('/manage', base_url=self.base_url).status_code, 401)
        page = self.client.get('/manage', base_url=self.base_url, headers=self.auth)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Generate report', page.data)
        self.assertNotIn(b'PageSpeed website (background)', page.data)
        self.assertEqual(self.client.post('/runs', base_url=self.base_url, json={},
                                         headers={'X-Report-Token': server.TOKEN}).status_code, 401)
        self.assertEqual(self.client.post('/runs', base_url=self.base_url, json={}, headers=self.auth).status_code, 403)
        config = saved_run('saved', '2026-10-27T09:00:00+00:00')['config']
        config.update(collector='api', psi_key='run-only-key')
        headers = dict(self.auth, **{'X-Report-Token': server.TOKEN})
        with patch('server.threading.Thread') as thread:
            response = self.client.post('/runs', base_url=self.base_url, json=config, headers=headers)
            self.assertEqual(response.status_code, 202)
            thread.return_value.start.assert_called_once()
            with patch('server.run') as audit:
                thread.call_args.kwargs['target']()
                self.assertEqual(audit.call_args.kwargs['psi_key'], 'run-only-key')

    def test_public_viewers_cannot_rebuild_history_or_enable_a_browser(self):
        self.assertEqual(self.client.post('/progressive/rebuild', base_url=self.base_url,
                                         headers={'X-Report-Token': server.TOKEN}).status_code, 401)
        config = saved_run('saved', '2026-10-27T09:00:00+00:00')['config']
        response = self.client.post('/runs', base_url=self.base_url, json=config,
                                    headers=dict(self.auth, **{'X-Report-Token': server.TOKEN}))
        self.assertEqual(response.status_code, 400)
        self.assertIn('Google API collector', response.get_json()['error'])

    def test_https_host_validation_and_missing_admin_configuration(self):
        response = self.client.get('/', base_url='http://reports.example.com')
        self.assertEqual(response.status_code, 308)
        self.assertTrue(response.headers['Location'].startswith('https://reports.example.com'))
        self.assertEqual(self.client.get('/', base_url='https://untrusted.example.com').status_code, 403)
        with patch.dict(server.app.config, {'ADMIN_PASSWORD': ''}):
            self.assertEqual(self.client.get('/', base_url=self.base_url).status_code, 503)
            self.assertEqual(self.client.get('/health', base_url=self.base_url).status_code, 503)

    def test_private_mode_can_still_require_login_for_report_downloads(self):
        with patch.dict(server.app.config, {'PUBLIC_REPORTS': False}):
            self.assertEqual(self.client.get('/progressive/report.xlsx', base_url=self.base_url).status_code, 401)

    def test_storage_uses_the_persistent_cloud_volume(self):
        environment = dict(os.environ, PAGESPEED_DATA_DIR=self.temporary.name)
        result = subprocess.run([sys.executable, '-c',
                                 'import json; from engine import OUTPUT; from progressive_report import history_root; '
                                 'print(json.dumps([str(OUTPUT), str(history_root(OUTPUT))]))'],
                                cwd=engine.ROOT, env=environment, text=True, capture_output=True, check=True)
        paths = json.loads(result.stdout)
        self.assertEqual(paths, [str(Path(self.temporary.name).resolve() / name) for name in ('reports', 'history')])

    def test_old_container_checkpoint_is_interrupted_even_if_pid_is_reused(self):
        state = saved_run('old-worker', '2026-10-27T09:00:00+00:00')
        state.update(status='Running', worker_pid=os.getpid(), worker_instance='previous-container')
        path = Path(self.temporary.name) / 'run.json'
        path.write_text(json.dumps(state))
        with patch('server.process_running', return_value=True):
            self.assertEqual(server.read_state(path)['status'], 'Interrupted')

    def test_run_remains_in_progress_until_daily_export_is_published(self):
        state = saved_run('finalizing', '2026-10-27T09:00:00+00:00')
        path = Path(self.temporary.name) / 'run.json'
        path.write_text(json.dumps(state))
        with patch.object(server, 'active', 'finalizing'):
            self.assertEqual(server.read_state(path)['status'], 'Running')
        self.assertEqual(server.read_state(path)['status'], 'Complete')

    def test_migration_export_excludes_credentials_profiles_and_active_runs(self):
        root = Path(self.temporary.name)
        (root / 'history/runs').mkdir(parents=True)
        (root / 'history/runs/saved.json').write_text(json.dumps(saved_run('saved', '2026-10-27T09:00:00+00:00')))
        (root / 'history/report.xlsx').write_bytes(b'PK-saved-workbook')
        (root / 'browser_profile').mkdir()
        (root / 'browser_profile/passwords.txt').write_text('do-not-export')
        (root / '.env.cloud').write_text('PRIVATE_KEY=do-not-export')
        for name, status in [('complete', 'Complete'), ('active', 'Running')]:
            folder = root / 'reports' / name
            folder.mkdir(parents=True)
            state = saved_run(name, '2026-10-27T09:00:00+00:00')
            state['status'] = status
            (folder / 'run.json').write_text(json.dumps(state))
        target = root / 'transfer.tar.gz'
        manifest = export_data(target, root)
        with tarfile.open(target) as archive:
            names = archive.getnames()
            self.assertIn('history/report.xlsx', names)
            self.assertIn('reports/complete/run.json', names)
            self.assertNotIn('reports/active/run.json', names)
            self.assertFalse(any('browser_profile' in name or '.env' in name for name in names))
            self.assertEqual(json.load(archive.extractfile('migration.json'))['files'], manifest['files'])

    def test_migration_export_does_not_write_inside_report_storage(self):
        root = Path(self.temporary.name)
        with self.assertRaises(ValueError):
            export_data(root / 'history/backup.tar.gz', root)


if __name__ == '__main__':
    unittest.main()
