import unittest
from unittest.mock import patch
from console_router import RouterManager, probe_url


class FakeResponse:
    def __init__(self, status=200):
        self.status = status

    def read(self, size=-1):
        return b''

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeHttp:
    def __init__(self):
        self.urls = []

    def open(self, request, timeout=None):
        self.urls.append(request.full_url)
        return FakeResponse(200)


class ProbeUrlTests(unittest.TestCase):
    def test_bedrock_runtime_maps_to_control_plane(self):
        self.assertEqual('https://bedrock.us-east-2.amazonaws.com/foundation-models',
                         probe_url('https://bedrock-runtime.us-east-2.amazonaws.com/openai/v1'))
        self.assertEqual('https://bedrock.eu-west-1.amazonaws.com/foundation-models',
                         probe_url('https://bedrock-runtime.eu-west-1.amazonaws.com/openai/v1/'))
        self.assertEqual('https://bedrock.ap-northeast-1.amazonaws.com/foundation-models',
                         probe_url('https://bedrock-runtime.ap-northeast-1.amazonaws.com'))
        self.assertEqual('https://bedrock.us-east-1.amazonaws.com/foundation-models',
                         probe_url('https://bedrock-runtime.us-east-1.amazonaws.com/'))

    def test_ordinary_openai_compatible_urls_keep_models_suffix(self):
        self.assertEqual('https://api.openai.com/v1/models', probe_url('https://api.openai.com/v1'))
        self.assertEqual('https://api.openai.com/v1/models', probe_url('https://api.openai.com/v1/'))
        self.assertEqual('http://127.0.0.1:11434/v1/models', probe_url('http://127.0.0.1:11434/v1'))

    def test_lookalike_and_plaintext_hosts_are_not_remapped(self):
        for base in ('https://bedrock-runtime.us-east-2.amazonaws.com.evil.example/v1',
                     'http://bedrock-runtime.us-east-2.amazonaws.com/openai/v1',
                     'https://bedrock-runtime.us-east-2.amazonaws.com.evil.example',
                     'https://evil.example/bedrock-runtime.us-east-2.amazonaws.com/v1',
                     'https://xbedrock-runtime.us-east-2.amazonaws.com/v1'):
            self.assertEqual(base + '/models', probe_url(base), base)


class TestKeysUsesProbeUrlTests(unittest.TestCase):
    def test_test_keys_requests_control_plane_for_bedrock(self):
        router = RouterManager('/nonexistent/console-bridge.json')
        fake_http = FakeHttp()
        router.http = fake_http

        def fake_call(command, args=None):
            if command == 'snapshot':
                return {'providers': [{'id': 'bedrock', 'baseUrl': 'https://bedrock-runtime.us-east-2.amazonaws.com/openai/v1'}]}
            if command == 'list_provider_keys':
                return [{'id': 1, 'label': 'main', 'enabled': True}]
            if command == 'reveal_provider_key':
                return 'k'
            raise AssertionError('unexpected command ' + command)

        with patch.object(router, 'call', side_effect=fake_call):
            results = router.test_keys('bedrock')
        self.assertEqual(['https://bedrock.us-east-2.amazonaws.com/foundation-models'], fake_http.urls)
        self.assertEqual(1, len(results))
        self.assertTrue(results[0]['ok'])
        self.assertEqual(200, results[0]['status'])
        self.assertEqual('可用', results[0]['message'])


if __name__ == '__main__':
    unittest.main()
