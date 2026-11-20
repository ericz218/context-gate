import json
from pathlib import Path
import tempfile
import unittest
import urllib.error

from console_capability import CapabilityRegistry, STATE_NAME
from console_router import RouterManager
from console_router_fallback import DirectFallback
from tests.test_router_capability import Clock, FakeOpener, FakeResponse, NOW, default_requests, make_router_db, write_catalog

UP = lambda: {'reachable': True, 'status': 401}
DOWN = lambda: {'reachable': False, 'detail': 'Connection refused'}
SECRET_A = 'nvapi-' + 'a' * 40
SECRET_B = 'nvapi-' + 'b' * 40


class FakeBridge:
    def __init__(self, base='https://integrate.api.nvidia.com/v1', keys=None, model_enabled=True):
        self.base = base
        self.keys = keys if keys is not None else [{'id': 1, 'enabled': True, 'hasSecret': True}, {'id': 2, 'enabled': True, 'hasSecret': True}]
        self.model_enabled = model_enabled
        self.calls = []

    def call(self, command, args=None):
        self.calls.append(command)
        if command == 'snapshot':
            return {'providers': [{'id': 4, 'name': 'NVIDIA', 'baseUrl': self.base, 'enabled': True}],
                    'models': [{'modelId': 'nvidia/deepseek-v4.1-flash', 'providerId': 4, 'upstreamModel': 'deepseek-ai/deepseek-v4.1-flash', 'enabled': self.model_enabled},
                               {'modelId': 'GLM-5.3', 'providerId': 4, 'upstreamModel': 'z-ai/glm-5.3', 'enabled': True}]}
        if command == 'list_provider_keys':
            return self.keys
        if command == 'reveal_provider_key':
            return {1: SECRET_A, 2: SECRET_B}[args['id']]
        raise AssertionError(command)


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        make_router_db(root / 'router.db', default_requests())
        write_catalog(root / 'catalog.json')
        self.state = root / 'state'
        self.registry = CapabilityRegistry(self.state, db_path=root / 'router.db', catalog_path=root / 'catalog.json',
                                           clock=Clock(NOW), opener=FakeOpener([]))

    def test_router_up_means_no_fallback(self):
        fallback = DirectFallback(FakeBridge(), self.registry, enabled=True, health=UP)
        result = fallback.chat('nvidia/deepseek-v4.1-flash', {'messages': []})
        self.assertEqual('not_needed', result['fallback'])
        self.assertEqual('router_available', fallback.status()['reason'])

    def test_disabled_by_default_returns_explicit_unavailable_and_marks_registry(self):
        bridge = FakeBridge()
        fallback = DirectFallback(bridge, self.registry, health=DOWN)
        result = fallback.chat('nvidia/deepseek-v4.1-flash', {'messages': []})
        self.assertEqual('fallback_unavailable', result['fallback'])
        self.assertEqual('disabled', result['reason'])
        self.assertFalse(result['ok'])
        self.assertEqual([], bridge.calls)
        saved = json.loads((self.state / STATE_NAME).read_text())
        self.assertEqual('disabled', saved['fallback']['reason'])
        self.assertEqual('disabled', self.registry.snapshot(refresh=True, check_router=False)['fallback']['reason'])

    def test_router_app_down_has_no_key_source(self):
        router = RouterManager(Path(self.tmp.name) / 'absent-bridge.json')
        fallback = DirectFallback(router, self.registry, enabled=True, health=DOWN)
        result = fallback.chat('nvidia/deepseek-v4.1-flash', {'messages': []})
        self.assertEqual('fallback_unavailable', result['fallback'])
        self.assertEqual('no_key_source', result['reason'])
        self.assertIn('钥匙串', result['message'])
        self.assertEqual('no_key_source', fallback.status()['reason'])
        self.assertFalse(self.registry.snapshot(refresh=True, check_router=False)['fallback']['available'])

    def test_retired_model_is_refused_before_any_key_is_revealed(self):
        bridge = FakeBridge()
        result = DirectFallback(bridge, self.registry, enabled=True, health=DOWN).chat('GLM-5.3', {'messages': []})
        self.assertEqual('model_unavailable', result['reason'])
        self.assertEqual('retired', result['capability'])
        self.assertNotIn('reveal_provider_key', bridge.calls)

    def test_unknown_disabled_stream_unsafe_and_keyless(self):
        cases = [
            (FakeBridge(), 'absent-model', {}, 'unknown_model'),
            (FakeBridge(model_enabled=False), 'nvidia/deepseek-v4.1-flash', {}, 'model_disabled'),
            (FakeBridge(), 'nvidia/deepseek-v4.1-flash', {'stream': True}, 'stream_unsupported'),
            (FakeBridge(base='http://evil.example/v1'), 'nvidia/deepseek-v4.1-flash', {}, 'unsafe_base_url'),
            (FakeBridge(keys=[{'id': 1, 'enabled': False}, {'id': 2, 'enabled': True, 'hasSecret': False}]), 'nvidia/deepseek-v4.1-flash', {}, 'no_provider_key'),
        ]
        for bridge, model, payload, reason in cases:
            result = DirectFallback(bridge, self.registry, enabled=True, health=DOWN).chat(model, payload)
            self.assertEqual('fallback_unavailable', result['fallback'], reason)
            self.assertEqual(reason, result['reason'])
            self.assertNotIn('reveal_provider_key', bridge.calls)

    def test_direct_call_switches_key_on_401_and_never_returns_secrets(self):
        denied = urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)
        denied.read = lambda size=-1: b'{"error":"bad key ' + SECRET_A.encode() + b'"}'
        http = FakeOpener([denied, FakeResponse(200, b'{"choices":[{"message":{"content":"hi"}}]}')])
        fallback = DirectFallback(FakeBridge(), self.registry, enabled=True, health=DOWN, opener=http)
        result = fallback.chat('NVIDIA/DeepSeek-V4.1-Flash'.lower(), {'messages': [{'role': 'user', 'content': 'hi'}], 'stream': False})
        self.assertTrue(result['ok'])
        self.assertEqual('direct', result['via'])
        self.assertEqual('auth', result['attempts'][0]['kind'])
        self.assertEqual(['https://integrate.api.nvidia.com/v1/chat/completions'] * 2, [r[0] for r in http.requests])
        self.assertEqual('deepseek-ai/deepseek-v4.1-flash', json.loads(http.requests[1][2])['model'])
        dumped = json.dumps(result)
        self.assertNotIn(SECRET_A, dumped)
        self.assertNotIn(SECRET_B, dumped)

    def test_timeout_stops_without_trying_every_key(self):
        import socket
        http = FakeOpener([socket.timeout('timed out')])
        result = DirectFallback(FakeBridge(), self.registry, enabled=True, health=DOWN, opener=http).chat('nvidia/deepseek-v4.1-flash', {})
        self.assertFalse(result['ok'])
        self.assertEqual('failed', result['fallback'])
        self.assertEqual('timeout', result['reason'])
        self.assertEqual(1, len(http.requests))


if __name__ == '__main__':
    unittest.main()
