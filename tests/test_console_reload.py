import json
import subprocess
import unittest
from unittest.mock import MagicMock, patch

import console_reload
from console_reload import ROOT, backend_pids, precheck

BASE = 'http://127.0.0.1:9/token-value/'


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.status = 200

    def read(self):
        return json.dumps(self.payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_opener(routes):
    requested = []
    opener = MagicMock()

    def open_(url, timeout=None):
        requested.append(url)
        if url not in routes:
            raise AssertionError('unexpected request ' + url)
        return FakeResponse(routes[url])

    opener.open.side_effect = open_
    return opener, requested


def clear_routes(**overrides):
    routes = {
        BASE.rstrip('/') + '/v1/quota': {'platforms': {'claude': {'protection': {'paused_count': 0}}}},
        BASE.rstrip('/') + '/v1/center/tasks': {'tasks': [{'id': 't1', 'status': 'stopped'}]},
        BASE.rstrip('/') + '/v1/groups': {'groups': [{'id': 'g1'}]},
        BASE.rstrip('/') + '/v1/groups?id=g1': {'group': {'id': 'g1'}, 'jobs': [{'id': 'j1', 'status': 'completed'}]},
    }
    routes.update(overrides)
    return routes


class PrecheckTests(unittest.TestCase):
    def run_precheck(self, routes):
        opener, requested = fake_opener(routes)
        with patch.object(console_reload, '_OPENER', opener):
            precheck(BASE)
        return requested

    def test_paused_quota_is_refused(self):
        routes = clear_routes(**{BASE.rstrip('/') + '/v1/quota':
                                 {'platforms': {'codex': {'protection': {'paused_count': 2}}}}})
        with self.assertRaisesRegex(RuntimeError, '有暂停中的任务'):
            self.run_precheck(routes)

    def test_running_center_task_is_refused(self):
        routes = clear_routes(**{BASE.rstrip('/') + '/v1/center/tasks':
                                 {'tasks': [{'id': 't1', 'status': 'stopped'}, {'id': 't2', 'status': 'running'}]}})
        with self.assertRaisesRegex(RuntimeError, '有执行中的任务'):
            self.run_precheck(routes)

    def test_active_group_job_is_refused(self):
        routes = clear_routes(**{BASE.rstrip('/') + '/v1/groups?id=g1':
                                 {'group': {'id': 'g1'}, 'jobs': [{'id': 'j1', 'status': 'queued'}]}})
        with self.assertRaisesRegex(RuntimeError, '有执行中的群聊任务'):
            self.run_precheck(routes)

    def test_clear_state_passes_and_uses_control_paths(self):
        requested = self.run_precheck(clear_routes())
        self.assertEqual([
            'http://127.0.0.1:9/token-value/v1/quota',
            'http://127.0.0.1:9/token-value/v1/center/tasks',
            'http://127.0.0.1:9/token-value/v1/groups',
            'http://127.0.0.1:9/token-value/v1/groups?id=g1',
        ], requested)


class BackendPidsTests(unittest.TestCase):
    def test_parses_pgrep_output(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout='123\n456\n', stderr='')
        with patch.object(console_reload.subprocess, 'run', return_value=completed) as run:
            self.assertEqual([123, 456], backend_pids())
        patterns = [call[0][0][2] for call in run.call_args_list]
        self.assertEqual([
            str(ROOT / 'console' / 'app.py') + ' --no-browser',
            str(console_reload.Path.home() / 'Documents' / 'context-gate' / 'console' / 'app.py') + ' --no-browser',
        ], patterns)
        for args in (call[0][0] for call in run.call_args_list):
            self.assertEqual(['pgrep', '-f'], args[:2])

    def test_single_pattern_is_still_accepted(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout='123\n', stderr='')
        with patch.object(console_reload.subprocess, 'run', return_value=completed) as run:
            self.assertEqual([123], backend_pids('custom-pattern --no-browser'))
        self.assertEqual('custom-pattern --no-browser', run.call_args[0][0][2])

    def test_exit_code_one_means_no_backend(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout='', stderr='')
        with patch.object(console_reload.subprocess, 'run', return_value=completed):
            self.assertEqual([], backend_pids())


class MemoryAccessTests(unittest.TestCase):

    def test_health_distinguishes_denied_and_missing_and_checks_process(self):
        info = {'base_url': BASE, 'pid': 42}
        health = {'service': 'context-gate-console', 'pid': 42, 'memory_documents': 'denied'}
        with patch.object(console_reload, '_get_json', return_value=health) as get:
            self.assertEqual(console_reload.memory_access(info), 'denied')
            get.assert_called_once_with(BASE + 'v1/console/health', timeout=2)
            health['memory_documents'] = 'missing'
            self.assertEqual(console_reload.memory_access(info), 'missing')
            self.assertIsNone(console_reload.memory_access(dict(info, pid=43)))

    def test_invalid_registration_never_contacts_external_host(self):
        with patch.object(console_reload, '_get_json') as get:
            self.assertIsNone(console_reload.memory_access({'base_url': 'https://example.invalid/', 'pid': 42}))
            get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
