import copy
import json
import http.client
import threading
from http.server import ThreadingHTTPServer
from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

import console_zcode_sync as z

EMPTY = {'schemaVersion': 1, 'config': {'providerConfigRules': {'providerRules': []}, 'modelConfigRules': {'providerModelRules': [], 'manualProviderModelRules': []}}}
ROUTER = {'providerId': z.PROVIDER_ID, 'config': {'api': {'type': 'openai-compatible', 'baseUrl': z.BASE_URL}, 'access': {'opaque': 'FAKE-PRESERVE'}, 'personalModelIds': ['old'], 'modelOrder': ['old']}}

class FakeRouter:
    def snapshot(self):
        return {'connected': True, 'models': [
            {'modelId': 'alias', 'upstreamModel': 'WRONG-UPSTREAM', 'enabled': True, 'providerEnabled': True, 'displayName': 'Alias'},
            {'modelId': 'disabled', 'enabled': False, 'providerEnabled': True}]}

class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.default = self.home / '.zcode/v2/provider_config.json'
        self.second = self.home / 'zcode-account2/.zcode/v2/provider_config.json'
        self.document = copy.deepcopy(EMPTY)
        self.document['config']['providerConfigRules']['providerRules'] = [copy.deepcopy(ROUTER)]
        self.other = copy.deepcopy(EMPTY)
        self.other['config']['providerConfigRules']['providerRules'] = [{'providerId': 'unrelated', 'config': {'access': {'opaque': 'UNCHANGED'}}}]
        for path, doc in [(self.default, self.document), (self.second, self.other)]:
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(doc))

    def test_merge_apply_private_backup_and_idempotence(self):
        before = self.default.read_bytes()
        preview = z.sync_request(FakeRouter(), self.home, {'model_ids': ['alias']}, apply=False)
        self.assertEqual(self.default.read_bytes(), before)
        self.assertEqual(len(preview['results']), 2)
        result = z.sync_request(FakeRouter(), self.home, {'model_ids': ['alias']})
        self.assertTrue(all(r['ok'] and r['changed'] for r in result['results']))
        self.assertNotIn('FAKE-PRESERVE', json.dumps(result))
        first = z.lmr_rule(json.loads(self.default.read_text()))
        second_doc = json.loads(self.second.read_text())
        second = z.lmr_rule(second_doc)
        self.assertEqual(first['config']['personalModelIds'], ['old', 'alias'])
        self.assertEqual(second['config']['personalModelIds'], ['alias'])
        self.assertEqual(second['config']['access'], ROUTER['config']['access'])
        self.assertEqual(second_doc['config']['providerConfigRules']['providerRules'][0], self.other['config']['providerConfigRules']['providerRules'][0])
        for p in [self.default, self.second]:
            backup = next(p.parent.glob('provider_config.json.lmr-backup-*'))
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertTrue(all(not r['changed'] for r in z.sync(self.home, ['alias'], apply=True)['results']))
        with self.assertRaises(RuntimeError):
            z.commit(self.default, b'stale', b'new')

    def test_white_list_and_invalid_accounts(self):
        for mid in ['WRONG-UPSTREAM', 'disabled', 'invented']:
            with self.assertRaises(ValueError):
                z.sync_request(FakeRouter(), self.home, {'model_ids': [mid]})
        for accounts in ['default', {}, [1], []]:
            with self.assertRaises(ValueError):
                z.sync(self.home, ['alias'], accounts)
        with self.assertRaises(ValueError):
            z.sync_request(FakeRouter(), self.home, {'model_ids': ['alias'], 'account_ids': None})
        opts = z.options(FakeRouter(), self.home)
        self.assertEqual(opts['models'], [{'id': 'alias', 'name': 'Alias'}])
        self.assertEqual(len(opts['accounts']), 2)

    def test_partial_failure_and_duplicate_id(self):
        bad = copy.deepcopy(self.other)
        bad['config']['providerConfigRules']['providerRules'] *= 2
        self.second.write_text(json.dumps(bad))
        result = z.sync(self.home, ['alias'], apply=True)
        self.assertTrue(result['results'][0]['ok'])
        self.assertFalse(result['results'][1]['ok'])
        self.assertNotIn('UNCHANGED', json.dumps(result))

    def test_disabled_provider_is_enabled_for_selected_models(self):
        self.document['config']['providerConfigRules']['providerRules'][0]['enabled'] = False
        self.default.write_text(json.dumps(self.document))
        result = z.sync(self.home, ['alias'], apply=True)
        self.assertTrue(all(r['ok'] for r in result['results']))
        for path in (self.default, self.second):
            self.assertIs(z.lmr_rule(json.loads(path.read_text()))['enabled'], True)

    def test_no_valid_connection_fails_safely(self):
        self.default.write_text('{broken fake-private-material')
        result = z.sync(self.home, ['alias'], apply=True)
        self.assertTrue(all(not r['ok'] for r in result['results']))
        self.assertNotIn('fake-private-material', json.dumps(result))

    def test_symlink_parent_not_discovered(self):
        linked = self.home / 'zcode-account3'
        linked.symlink_to(self.home / 'zcode-account2', target_is_directory=True)
        self.assertEqual(len(z.discover(self.home)), 2)

class HTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Import the real handler, never construct app managers or its main server.
        from console import app
        self.app = app
        SyncTests.setUp(self)
        self.home_patch = patch.object(app.Path, 'home', return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.server.local_token = 'TEST-LOCAL-BOUNDARY'
        self.server.router = FakeRouter()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, method, endpoint, body=None, token=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            payload = None if body is None else json.dumps(body)
            headers = {'Origin': 'http://127.0.0.1:' + str(self.server.server_port),
                       'Connection': 'close'}
            if body is not None:
                headers['Content-Type'] = 'application/json'
            path = '/' + (token or self.server.local_token) + endpoint
            conn.request(method, path, body=payload, headers=headers)
            response = conn.getresponse()
            raw = response.read().decode()
            self.assertNotIn('FAKE-PRESERVE', raw)
            self.assertNotIn('UNCHANGED', raw)
            return response.status, json.loads(raw)
        finally:
            conn.close()

    def account_bytes(self):
        return {p: p.read_bytes() for p in (self.default, self.second)}

    def test_authenticated_options_and_sync(self):
        status, data = self.request('GET', '/v1/router/zcode')
        self.assertEqual(status, 200)
        self.assertEqual(set(data), {'models', 'accounts', 'mode'})
        self.assertEqual(data['models'], [{'id': 'alias', 'name': 'Alias'}])
        self.assertTrue(all(set(a) == {'id', 'label'} for a in data['accounts']))
        self.assertEqual(data['mode'], 'merge')
        status, result = self.request('POST', '/v1/router/zcode/sync', {'model_ids': ['alias']})
        self.assertEqual(status, 200)
        self.assertEqual(result['modelCount'], 1)
        self.assertTrue(all(r['ok'] and r['changed'] for r in result['results']))
        self.assertEqual(z.lmr_rule(json.loads(self.second.read_text()))['config']['personalModelIds'], ['alias'])

    def test_invalid_token_model_or_account_never_writes(self):
        before = self.account_bytes()
        for method, endpoint, body, token, expected in [
            ('GET', '/v1/router/zcode', None, 'WRONG', 403),
            ('POST', '/v1/router/zcode/sync', {'model_ids': ['alias']}, 'WRONG', 403),
            ('POST', '/v1/router/zcode/sync', {'model_ids': ['disabled']}, None, 400),
            ('POST', '/v1/router/zcode/sync', {'model_ids': ['alias'], 'account_ids': []}, None, 400),
        ]:
            with self.subTest(method=method, body=body, token=token):
                status, _ = self.request(method, endpoint, body, token)
                self.assertEqual(status, expected)
                self.assertEqual(self.account_bytes(), before)
                self.assertFalse(list(self.home.glob('**/*.lmr-backup-*')))


if __name__ == '__main__':
    unittest.main()
