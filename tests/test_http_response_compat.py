"""Regression: fp-less synthetic HTTPError must not break response closing,
and real (fp-backed) HTTPError responses must still be closed.

Context (from the ask): on Python 3.9 the 551-suite third branch raises three
errors because FakeOpener returns urllib.error.HTTPError(..., fp=None), and
``with response`` triggers an AttributeError on fp.closed:
console_capability.router_reachable:229, CapabilityRegistry.probe:517,
DirectFallback.chat:141.

Real urlopen HTTPError objects always carry a live fp and double as the
response, so the implementation closes real responses via close() in a
finally block instead of ``with``; synthetic fp=None errors have nothing to
release but their status must still drive classify/backoff decisions.
"""
import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

import console_capability as cap
from console_capability import CapabilityRegistry
from console_router_fallback import DirectFallback
from tests.test_router_capability import Clock, FakeOpener, FakeResponse, NOW, default_requests, make_router_db, write_catalog


def fp_error(url, code, body=b'{"error":"x"}'):
    """Real-shaped HTTPError: fp is a live readable stream, like urlopen gives."""
    return urllib.error.HTTPError(url, code, 'Error', {}, io.BytesIO(body))


class FpLessCompatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        make_router_db(root / 'router.db', default_requests())
        write_catalog(root / 'catalog.json')
        self.registry = CapabilityRegistry(root / 'state', db_path=root / 'router.db',
                                           catalog_path=root / 'catalog.json',
                                           clock=Clock(NOW), opener=FakeOpener([]))

    def test_router_reachable_reads_fp_less_401(self):
        out = cap.router_reachable(opener=FakeOpener([urllib.error.HTTPError('u', 401, 'x', {}, None)]))
        self.assertTrue(out['reachable'])
        self.assertEqual(401, out['status'])

    def test_router_reachable_closes_real_http_error(self):
        err = fp_error('http://r/v1/models', 401)
        out = cap.router_reachable(opener=FakeOpener([err]))
        self.assertTrue(out['reachable'])
        self.assertEqual(401, out['status'])
        self.assertTrue(err.fp.closed)

    def test_probe_classifies_fp_less_gone_and_applies_retired_backoff(self):
        gone = urllib.error.HTTPError('http://x', 410, 'Gone', {}, None)
        gone.read = lambda size=-1: b'{"title":"Gone","detail":"reached its end of life"}'
        registry = CapabilityRegistry(self.registry.state_path.parent, db_path=self.registry.db_path,
                                      catalog_path=self.registry.catalog_path, clock=Clock(NOW),
                                      opener=FakeOpener([gone]))
        result = registry.probe('muse-spark-1.3-contributor', lambda: 'k', consume_quota=True,
                                cooldown=100, max_backoff=5000)
        self.assertTrue(result['probed'])
        self.assertEqual('gone', result['kind'])
        self.assertEqual(NOW + 5_000_000, result['nextAt'])

    def test_probe_closes_real_http_error_body(self):
        err = fp_error('http://r/v1/chat/completions', 410,
                       b'{"title":"Gone","detail":"reached its end of life"}')
        registry = CapabilityRegistry(self.registry.state_path.parent, db_path=self.registry.db_path,
                                      catalog_path=self.registry.catalog_path, clock=Clock(NOW),
                                      opener=FakeOpener([err]))
        result = registry.probe('muse-spark-1.3-contributor', lambda: 'k', consume_quota=True,
                                cooldown=100, max_backoff=5000)
        self.assertEqual('gone', result['kind'])
        self.assertTrue(err.fp.closed)

    def test_probe_still_records_timeout_backoff(self):
        import socket
        opener = FakeOpener([urllib.error.URLError(socket.timeout('timed out'))])
        registry = CapabilityRegistry(self.registry.state_path.parent, db_path=self.registry.db_path,
                                      catalog_path=self.registry.catalog_path, clock=Clock(NOW),
                                      opener=opener)
        first = registry.probe('muse-spark-1.3-contributor', lambda: 'k', consume_quota=True,
                               cooldown=100, max_backoff=1000)
        self.assertEqual('timeout', first['kind'])
        self.assertEqual(1, first['consecutiveFailures'])
        self.assertEqual(NOW + 200_000, first['nextAt'])

    def test_fallback_auth_retry_with_fp_less_401_keeps_both_attempts(self):
        from tests.test_router_fallback import DOWN, FakeBridge
        denied = urllib.error.HTTPError('u', 401, 'Unauthorized', {}, None)
        denied.read = lambda size=-1: b'{"error":"bad key"}'
        http = FakeOpener([denied, FakeResponse(200, b'{"choices":[{"message":{"content":"hi"}}]}')])
        result = DirectFallback(FakeBridge(), self.registry, enabled=True, health=DOWN, opener=http).chat(
            'nvidia/deepseek-v4.1-flash', {'messages': []})
        self.assertTrue(result['ok'])
        self.assertEqual('direct', result['via'])
        self.assertEqual('auth', result['attempts'][0]['kind'])
        self.assertEqual(2, len(http.requests))

    def test_fallback_closes_real_http_error_before_retry(self):
        from tests.test_router_fallback import DOWN, FakeBridge
        denied = fp_error('https://integrate.api.nvidia.com/v1/chat/completions', 401, b'{"error":"bad key"}')
        http = FakeOpener([denied, FakeResponse(200, b'{"choices":[{"message":{"content":"hi"}}]}')])
        result = DirectFallback(FakeBridge(), self.registry, enabled=True, health=DOWN, opener=http).chat(
            'nvidia/deepseek-v4.1-flash', {'messages': []})
        self.assertTrue(result['ok'])
        self.assertEqual('auth', result['attempts'][0]['kind'])
        self.assertTrue(denied.fp.closed)

    def test_close_helper_never_masks_request_outcome(self):
        class Boom:
            status = 500

            def close(self):
                raise RuntimeError('close blew up')

            def read(self, size=-1):
                return b'{}'
        opener = FakeOpener([Boom()])
        out = cap.router_reachable(opener=opener)
        self.assertTrue(out['reachable'])
        self.assertEqual(500, out['status'])

    def test_negative_rate_limit_and_server_errors_still_classified(self):
        self.assertEqual('rate_limited', cap.classify(429, 'slow down'))
        self.assertEqual('upstream_error', cap.classify(500, 'internal'))
        self.assertEqual('gone', cap.classify(410, 'reached its end of life'))
        dumped = json.dumps({'kind': 'gone', 'status': 410})
        self.assertIn('gone', dumped)


if __name__ == '__main__':
    unittest.main()
