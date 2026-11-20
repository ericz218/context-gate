import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import tempfile
import unittest
import urllib.error

import console_capability as cap
from console_capability import CapabilityRegistry, classify, percentile, window_stats, probe_delay, probe_due

DAY = 86400 * 1000
NOW = 1793300000000  # 2026-10-29 local afternoon (ms)


def make_router_db(path, requests):
    db = sqlite3.connect(path)
    db.executescript('''
    create table providers (id integer primary key, name text, base_url text, enabled integer, note text default '',
      key_strategy text default 'priority', created_at integer default 0, updated_at integer default 0);
    create table provider_keys (id integer primary key, provider_id integer, label text default '', priority integer default 1,
      enabled integer default 1, keychain_account text default '', created_at integer default 0);
    create table models (id integer primary key, display_name text, model_id text, provider_id integer, upstream_model text,
      enabled integer, created_at integer default 0, updated_at integer default 0);
    create table requests (id integer primary key autoincrement, ts integer, endpoint text, requested_model text,
      resolved_model text, provider_name text, status integer, latency_ms integer, is_stream integer default 0,
      fallback_from text, prompt_tokens integer, completion_tokens integer, total_tokens integer, error_message text, debug_info text);
    insert into providers (id, name, base_url, enabled) values
      (4, 'NVIDIA', 'https://integrate.api.nvidia.com/v1', 1), (7, 'MetaMuse', 'https://api.meta.ai/v1', 1),
      (1, 'AMD TokenFactory', 'https://developer.amd.com.cn/radeon/api/v1', 1);
    insert into provider_keys (provider_id, keychain_account) values (4, 'pk_4_1'), (7, 'pk_7_1'), (1, 'pk_1_1');
    insert into models (id, display_name, model_id, provider_id, upstream_model, enabled) values
      (14, 'GLM 5.3', 'GLM-5.3', 4, 'z-ai/glm-5.3', 1),
      (16, 'GLM 5.3 Flash (NVIDIA)', 'nvidia/glm-5.3-flash', 4, 'z-ai/glm-5.3-flash', 1),
      (36, 'muse-wonder-1.0', 'muse-wonder-1.0', 7, 'muse-wonder-1.0', 1),
      (37, 'muse-spark-1.3-contributor', 'muse-spark-1.3-contributor', 7, 'muse-spark-1.3-contributor', 1),
      (11, 'Qwen3.8-27B', 'Qwen3.8-27B', 1, 'Qwen3.8-27B', 1),
      (12, 'MiniCPM5-2B', 'MiniCPM5-2B', 1, 'MiniCPM5-2B', 0);
    ''')
    db.executemany('insert into requests (ts, endpoint, requested_model, resolved_model, provider_name, status, latency_ms, error_message) '
                   'values (?, ?, ?, ?, ?, ?, ?, ?)', requests)
    db.commit()
    db.close()


def default_requests():
    rows = []
    # GLM-5.3: four successes, then 410 retirement.
    for i, latency in enumerate((100, 200, 300, 400)):
        rows.append((NOW - 2 * DAY + i, 'chat/completions', 'GLM-5.3', 'GLM-5.3', 'NVIDIA', 200, latency, None))
    rows.append((NOW - 3600_000, 'chat/completions', 'GLM-5.3', 'GLM-5.3', 'NVIDIA', 410, 98,
                 '{"title":"Gone","status":410,"detail":"The model z-ai/glm-5.3 has reached its end of life"}'))
    # nvidia flash: success, then missing key.
    rows.append((NOW - DAY, 'chat/completions', 'nvidia/glm-5.3-flash', 'nvidia/glm-5.3-flash', 'NVIDIA', 200, 900, None))
    rows.append((NOW - 600_000, 'chat/completions', 'nvidia/glm-5.3-flash', 'nvidia/glm-5.3-flash', 'NVIDIA', 500, 0,
                 'Cannot read provider API key from Keychain: Keychain entry not found'))
    # Qwen: timeout, then a later 400 must not hide it.
    rows.append((NOW - DAY, 'chat/completions', 'Qwen3.8-27B', 'Qwen3.8-27B', 'AMD TokenFactory', 200, 1200, None))
    rows.append((NOW - 7200_000, 'chat/completions', 'Qwen3.8-27B', 'Qwen3.8-27B', 'AMD TokenFactory', 504, 180000,
                 'Upstream request timed out: https://example/v1/chat/completions'))
    rows.append((NOW - 3600_000, 'chat/completions', 'Qwen3.8-27B', 'Qwen3.8-27B', 'AMD TokenFactory', 400, 10, 'invalid content-type'))
    # Muse wonder: success (stale request older than the window is ignored for stats).
    rows.append((NOW - 30 * DAY, 'chat/completions', 'muse-wonder-1.0', 'muse-wonder-1.0', 'MetaMuse', 500, 1, 'boom'))
    rows.append((NOW - 3 * 3600_000, 'responses', 'muse-wonder-1.0', 'muse-wonder-1.0', 'MetaMuse', 200, 1181, None))
    return rows


def write_catalog(path):
    Path(path).write_text(json.dumps({'models': [
        {'id': 'meta/muse-wonder-1.0', 'name': 'muse-wonder-1.0', 'apiProvider': 'Meta', 'inputPrice': '4', 'outputPrice': '20', 'currency': 'USD'},
        {'id': 'meta/muse-spark-1.3', 'name': 'muse-spark-1.3', 'apiProvider': 'Meta', 'inputPrice': '1.25', 'outputPrice': '4.25'},
        # Creator price must never be applied to the NVIDIA-hosted copy.
        {'id': 'zai/glm-5.3', 'name': 'glm-5.3', 'apiProvider': 'Z.AI', 'inputPrice': '1.4', 'outputPrice': '4.4'},
    ]}))


class Clock:
    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms / 1000


class StatsTests(unittest.TestCase):
    def test_nearest_rank_percentiles(self):
        self.assertIsNone(percentile([], 50))
        self.assertEqual(7, percentile([7], 95))
        self.assertEqual(200, percentile([400, 100, 300, 200], 50))
        self.assertEqual(400, percentile([400, 100, 300, 200], 95))
        values = list(range(1, 101))
        self.assertEqual(50, percentile(values, 50))
        self.assertEqual(95, percentile(values, 95))
        self.assertEqual(3, percentile([None, 3, None], 50))
        with self.assertRaises(ValueError):
            percentile([1], 0)

    def test_window_stats_error_rate_and_success_only_latency(self):
        stats = window_stats([(200, 100, None), (200, 300, None), (429, 5, 'slow down'), (504, 180000, 'timed out')])
        self.assertEqual(4, stats['requests'])
        self.assertEqual(2, stats['failures'])
        self.assertEqual(0.5, stats['errorRate'])
        self.assertEqual(100, stats['p50Ms'])
        self.assertEqual(300, stats['p95Ms'])
        self.assertEqual(2, stats['latencySamples'])
        self.assertEqual({'rate_limited': 1, 'timeout': 1}, stats['kinds'])
        empty = window_stats([])
        self.assertIsNone(empty['errorRate'])
        self.assertIsNone(empty['p50Ms'])


class ClassifyTests(unittest.TestCase):
    def test_kinds(self):
        cases = [
            (200, '', 'ok'),
            (410, '{"title":"Gone"}', 'gone'),
            (404, "The model 'z-ai/glm-5.3' has reached its end of life", 'gone'),
            (500, 'Cannot read provider API key from Keychain: Keychain entry not found', 'missing_key'),
            (500, 'Cannot read provider API key from Keychain: Cannot locate Keychain helper', 'missing_key'),
            (504, 'Upstream request timed out: https://x', 'timeout'),
            (408, '', 'timeout'),
            (None, 'probe timed out after 30s', 'timeout'),
            (429, '', 'rate_limited'),
            (401, '', 'auth'),
            (403, 'not available for this account', 'forbidden'),
            (404, 'Unknown model: x', 'not_found'),
            (400, 'thinking not supported', 'client_error'),
            (502, 'Upstream request failed', 'network'),
            (None, 'connection refused', 'network'),
            (500, 'internal', 'upstream_error'),
            (None, '', 'error'),
        ]
        for status, message, kind in cases:
            self.assertEqual(kind, classify(status, message), (status, message))

    def test_scrub_hides_credentials_and_bounds_length(self):
        text = cap.scrub('Authorization: Bearer abcdef123456 key sk-' + 'x' * 30 + ' lmr_' + 'y' * 20 + ' ' + 'z' * 500)
        self.assertNotIn('abcdef123456', text)
        self.assertNotIn('sk-xxxx', text)
        self.assertNotIn('lmr_yyyy', text)
        self.assertLessEqual(len(text), 240)


class ProbePolicyTests(unittest.TestCase):
    def test_cooldown_and_exponential_backoff(self):
        self.assertEqual(100, probe_delay(0, 'ok', cooldown=100, max_backoff=10000))
        self.assertEqual(100, probe_delay(3, 'client_error', cooldown=100, max_backoff=10000))
        self.assertEqual(200, probe_delay(1, 'timeout', cooldown=100, max_backoff=10000))
        self.assertEqual(400, probe_delay(2, 'timeout', cooldown=100, max_backoff=10000))
        self.assertEqual(10000, probe_delay(30, 'timeout', cooldown=100, max_backoff=10000))
        self.assertEqual(10000, probe_delay(1, 'gone', cooldown=100, max_backoff=10000))

    def test_stale_success_is_not_available(self):
        day = 86400 * 1000
        now = 100 * day
        self.assertEqual(('unknown', 'stale_success'), cap.availability(now - 20 * day, None, stale_before=now - 7 * day))
        self.assertEqual(('available', 'recent_success'), cap.availability(now - 1 * day, None, stale_before=now - 7 * day))
        self.assertEqual(('available', 'recent_success'), cap.availability(now - 20 * day, None))

    def test_probe_due(self):
        self.assertEqual((True, 0, 'never_probed'), probe_due(None, NOW))
        entry = {'lastAt': NOW, 'kind': 'ok', 'consecutiveFailures': 0, 'nextAt': NOW + 60_000}
        self.assertEqual((False, 60, 'cooldown'), probe_due(entry, NOW))
        self.assertEqual((True, 0, 'cooldown_elapsed'), probe_due(entry, NOW + 60_000))
        entry = {'lastAt': NOW, 'kind': 'timeout', 'consecutiveFailures': 2, 'nextAt': NOW + 1000}
        self.assertEqual('backoff', probe_due(entry, NOW)[2])
        entry = {'lastAt': NOW, 'kind': 'gone', 'consecutiveFailures': 1, 'nextAt': NOW + 1000}
        self.assertEqual('retired_backoff', probe_due(entry, NOW)[2])
        # Missing nextAt is derived from the stored failure count.
        self.assertFalse(probe_due({'lastAt': NOW, 'kind': 'timeout', 'consecutiveFailures': 1}, NOW + 1000, cooldown=10)[0])
        self.assertTrue(probe_due({'lastAt': NOW, 'kind': 'timeout', 'consecutiveFailures': 1}, NOW + 20_000, cooldown=10)[0])


class FakeResponse:
    def __init__(self, status, body=b'{}'):
        self.status = status
        self.body = body

    def read(self, size=-1):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append((request.full_url, dict(request.headers), request.data))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.db = root / 'router.db'
        make_router_db(self.db, default_requests())
        self.catalog = root / 'catalog.json'
        write_catalog(self.catalog)
        self.state = root / 'state'
        self.clock = Clock(NOW)

    def registry(self, opener=None):
        return CapabilityRegistry(self.state, db_path=self.db, catalog_path=self.catalog, clock=self.clock,
                                  router_url='http://127.0.0.1:9', opener=opener or FakeOpener([]))

    def records(self, registry):
        return {r['key']: r for r in registry.snapshot(refresh=True, check_router=False)['records']}

    def test_snapshot_classifies_real_failure_shapes(self):
        records = self.records(self.registry())
        glm = records['NVIDIA/GLM-5.3']
        self.assertEqual('retired', glm['status'])
        self.assertEqual('gone', glm['lastError']['kind'])
        self.assertEqual(410, glm['lastError']['status'])
        self.assertEqual(200, glm['window']['p50Ms'])
        self.assertEqual(400, glm['window']['p95Ms'])
        self.assertEqual(0.2, glm['window']['errorRate'])
        self.assertIsNone(glm['price'])  # Z.AI creator price is not applied to NVIDIA hosting
        flash = records['NVIDIA/nvidia/glm-5.3-flash']
        self.assertEqual('missing_key', flash['status'])
        qwen = records['AMD TokenFactory/Qwen3.8-27B']
        self.assertEqual('timeout', qwen['status'])
        self.assertEqual('client_error', qwen['lastError']['kind'])  # display the newest error, decide on the hard one
        muse = records['MetaMuse/muse-wonder-1.0']
        self.assertEqual('available', muse['status'])
        self.assertEqual({'requests': 1, 'failures': 0}, {k: muse['window'][k] for k in ('requests', 'failures')})
        self.assertEqual('4', muse['price']['input'])
        self.assertEqual('20', muse['price']['output'])
        self.assertEqual('supported', muse['responsesApi'])
        self.assertEqual('unknown', muse['toolCalls'])
        spark = records['MetaMuse/muse-spark-1.3-contributor']
        self.assertEqual('unknown', spark['status'])
        self.assertIsNone(spark['price'])  # no exact catalog entry -> unknown, not guessed
        self.assertIsNone(spark['window']['errorRate'])
        self.assertFalse(records['AMD TokenFactory/MiniCPM5-2B']['enabled'])

    def test_router_db_is_opened_read_only_and_state_is_private(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        registry = self.registry()
        registry.snapshot(refresh=True, check_router=False)
        self.assertEqual(before, hashlib.sha256(self.db.read_bytes()).hexdigest())
        path = self.state / cap.STATE_NAME
        self.assertTrue(path.is_file())
        self.assertEqual(0o600, stat.S_IMODE(path.stat().st_mode))
        saved = json.loads(path.read_text())
        self.assertEqual(cap.STATE_VERSION, saved['version'])
        self.assertTrue(saved['snapshot']['records'])
        with self.assertRaises(sqlite3.OperationalError):
            with registry._connect() as db:
                db.execute("insert into providers (id, name, base_url, enabled) values (99, 'x', 'https://x', 1)")

    def test_missing_db_reports_error_without_crashing(self):
        registry = CapabilityRegistry(self.state, db_path=Path(self.tmp.name) / 'absent.db', catalog_path=self.catalog,
                                      clock=self.clock, opener=FakeOpener([]))
        data = registry.snapshot(refresh=True, check_router=False)
        self.assertEqual([], data['records'])
        self.assertIn('router.db', data['error'])

    def test_probe_requires_quota_ack_and_obeys_cooldown_and_backoff(self):
        secret = 'lmr_' + 'k' * 40
        timeout = urllib.error.URLError(socket.timeout('timed out'))
        opener = FakeOpener([timeout, timeout, FakeResponse(200, b'{"choices":[]}')])
        registry = self.registry(opener)
        skipped = registry.probe('muse-spark-1.3-contributor', lambda: secret)
        self.assertEqual('quota_not_acknowledged', skipped['skipped'])
        self.assertEqual([], opener.requests)

        first = registry.probe('muse-spark-1.3-contributor', lambda: secret, consume_quota=True, cooldown=100, max_backoff=1000)
        self.assertTrue(first['probed'])
        self.assertEqual('timeout', first['kind'])
        self.assertEqual(1, first['consecutiveFailures'])
        self.assertEqual(NOW + 200_000, first['nextAt'])
        url, headers, body = opener.requests[0]
        self.assertEqual('http://127.0.0.1:9/v1/chat/completions', url)
        payload = json.loads(body)
        self.assertEqual('muse-spark-1.3-contributor', payload['model'])
        self.assertLessEqual(payload['max_tokens'], 16)
        self.assertFalse(payload['stream'])

        blocked = registry.probe('muse-spark-1.3-contributor', lambda: secret, consume_quota=True, cooldown=100, max_backoff=1000)
        self.assertEqual('backoff', blocked['skipped'])
        self.assertEqual(200, blocked['retryInSeconds'])
        self.assertEqual(1, len(opener.requests))

        self.clock.ms = NOW + 200_000
        second = registry.probe('muse-spark-1.3-contributor', lambda: secret, consume_quota=True, cooldown=100, max_backoff=1000)
        self.assertEqual(2, second['consecutiveFailures'])
        self.assertEqual(self.clock.ms + 400_000, second['nextAt'])
        record = self.records(registry)['MetaMuse/muse-spark-1.3-contributor']
        self.assertEqual('timeout', record['status'])
        self.assertEqual('probe', record['lastError']['source'])

        third = registry.probe('muse-spark-1.3-contributor', lambda: secret, consume_quota=True, force=True, cooldown=100, max_backoff=1000)
        self.assertEqual('ok', third['kind'])
        self.assertEqual(0, third['consecutiveFailures'])
        self.assertEqual(self.clock.ms + 100_000, third['nextAt'])
        self.assertEqual('available', self.records(registry)['MetaMuse/muse-spark-1.3-contributor']['status'])
        state_text = (self.state / cap.STATE_NAME).read_text()
        self.assertNotIn(secret, state_text)
        self.assertNotIn(secret, json.dumps(third))

    def test_probe_gone_backs_off_to_cap_and_router_down_does_not_blame_model(self):
        gone = urllib.error.HTTPError('http://x', 410, 'Gone', {}, None)
        gone.read = lambda size=-1: b'{"title":"Gone","detail":"reached its end of life"}'
        opener = FakeOpener([gone, urllib.error.URLError(ConnectionRefusedError(61, 'Connection refused'))])
        registry = self.registry(opener)
        result = registry.probe('muse-spark-1.3-contributor', lambda: 'k', consume_quota=True, cooldown=100, max_backoff=5000)
        self.assertEqual('gone', result['kind'])
        self.assertEqual(NOW + 5_000_000, result['nextAt'])
        self.assertEqual('retired', self.records(registry)['MetaMuse/muse-spark-1.3-contributor']['status'])
        down = registry.probe('muse-wonder-1.0', lambda: 'k', consume_quota=True)
        self.assertEqual('router_unavailable', down['kind'])
        self.assertEqual('available', self.records(registry)['MetaMuse/muse-wonder-1.0']['status'])

    def test_unknown_or_keyless_probe_is_skipped(self):
        registry = self.registry()
        self.assertEqual('unknown_model', registry.probe('nope', lambda: 'k', consume_quota=True)['skipped'])
        self.assertEqual('no_local_key', registry.probe('muse-wonder-1.0', lambda: '', consume_quota=True)['skipped'])

    def test_candidates_filter_and_order(self):
        registry = self.registry()
        keys = [r['key'] for r in registry.candidates()]
        self.assertEqual(['MetaMuse/muse-wonder-1.0'], keys)
        self.assertEqual([], registry.candidates(require_tools=True))
        self.assertEqual(['MetaMuse/muse-wonder-1.0'], [r['key'] for r in registry.candidates(require_responses=True, prefer='cheap')])
        self.assertEqual([], registry.candidates(max_p95_ms=1000))
        self.assertEqual('MetaMuse/muse-wonder-1.0', registry.get('MUSE-WONDER-1.0')['key'])
        self.assertIsNone(registry.get('absent'))

    def test_router_reachability_check(self):
        reachable = cap.router_reachable(opener=FakeOpener([urllib.error.HTTPError('u', 401, 'x', {}, None)]))
        self.assertTrue(reachable['reachable'])
        self.assertEqual(401, reachable['status'])
        down = cap.router_reachable(opener=FakeOpener([urllib.error.URLError(ConnectionRefusedError(61, 'refused'))]))
        self.assertFalse(down['reachable'])

    def test_corrupt_state_file_is_replaced(self):
        self.state.mkdir(parents=True)
        (self.state / cap.STATE_NAME).write_text('{not json')
        registry = self.registry()
        self.assertEqual({}, registry.state['probes'])
        registry.snapshot(refresh=True, check_router=False)
        self.assertEqual(cap.STATE_VERSION, json.loads((self.state / cap.STATE_NAME).read_text())['version'])


if __name__ == '__main__':
    unittest.main()
