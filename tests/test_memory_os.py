import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_gate import Config, MemoryOSSource, build_pack
import gate_run
from gate_service import Engine

TOKEN = 'test-token-0123456789abcdefghij'


def event(key, value, version=1, scope_id=None, scope='project', weight=None):
    ir = {'key': key, 'value': value, 'scope': scope, 'scope_id': scope_id, 'memory_type': 'state',
          'tier': 'WARM', 'importance': .5, 'confidence': .8}
    if weight is not None:
        ir['weight'] = weight
    return {'event_id': 'ev-' + key, 'version': version, 'ir': ir}


class FakeMemoryOS(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self):
        server = self.server
        server.calls.append((self.command, self.path, self.headers.get('Authorization')))
        if self.command != 'GET':
            self.send_response(405); self.end_headers(); return
        if server.delay:
            time.sleep(server.delay)
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            self.send_response(401); self.end_headers(); return
        query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(self.path).query))
        body = server.bodies.get(query.get('project_id'), {'state_evidence': [], 'procedures': [], 'warnings': []})
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = respond


class MemoryOSTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / 'repo'
        self.root.mkdir()
        (self.root / 'price.py').write_text('def price(values):\n    return sum(values)\n')
        self.core = '[CORE_MEMORY_START]\r\n规则：原样保留，  两个空格\t制表符。\r\n[CORE_MEMORY_END]'
        self.memory = self.root / 'AGENTS.md'
        self.memory.write_bytes(('前文\r\n' + self.core + '\r\n后文：项目说明').encode())
        self.config = Config(cache_dir=str(self.base / 'cache'))  # small repo: bypass_small, no reviewer
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeMemoryOS)
        self.server.calls, self.server.bodies, self.server.delay = [], {}, 0
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)
        self.pid = str(self.root)

    def source(self, token=TOKEN, url=None, catalog=None, documents=None):
        return MemoryOSSource(url or self.url, token, self.config, catalog, documents or (self.base / 'nodocs'))

    def project(self, states, procedures=(), pid=None, warnings=()):
        pid = pid or self.pid
        self.server.bodies[pid] = {'project': {'ids': [pid], 'resolved_by': 'explicit'},
                                   'state_evidence': list(states), 'procedures': list(procedures),
                                   'handoffs': [{'text': 'not included'}], 'warnings': list(warnings)}

    def build(self, source, request='只读解释 price.py'):
        return build_pack(self.root, request, [self.memory], self.config, memory_source=source)

    def test_weight_order_prefix_and_low_weight_truncation_recorded(self):
        # MemoryOS returns each list highest weight first; workspace/foreign items are not project memory.
        states = [event('s%d' % i, '状态值 %d ' % i + 'x' * 40, scope_id=self.pid) for i in range(6)]
        states.insert(2, event('workspace_rule', 'not project', scope='workspace'))
        states.insert(3, event('other_project', 'foreign', scope_id='/elsewhere'))
        procedures = [event('p0', '步骤 0', scope_id=self.pid), event('p1', '步骤 1', scope_id=self.pid)]
        for p in procedures:
            p['ir']['memory_type'] = 'procedural'
        self.project(states, procedures, warnings=['Context budget/row limit omitted 7 items; query narrower'])
        self.config.memory_os_tokens = 60
        result = self.build(self.source())
        memory = result['memory']
        self.assertEqual(memory['source'], 'memoryos')
        self.assertEqual(memory['project_id'], self.pid)
        order = [x['key'] for x in memory['items']] + [x['key'] for x in memory['truncated']]
        # Proportional interleave keeps each list's MemoryOS (weight) order.
        self.assertEqual(order, ['s0', 's1', 'p0', 's2', 's3', 's4', 'p1', 's5'])
        self.assertTrue(memory['items'] and memory['truncated'])
        self.assertEqual([x['rank'] for x in memory['items'] + memory['truncated']], list(range(1, 9)))
        self.assertLessEqual(memory['used_tokens_estimated'], 60)
        self.assertEqual(memory['included_items'] + memory['truncated_items'], 8)
        self.assertGreater(memory['truncated_tokens_estimated'], 0)
        self.assertEqual(memory['memoryos_omitted_items'], 7)
        self.assertEqual(memory['handoffs_not_included'], 1)
        prompt = result['prompt']
        self.assertTrue(prompt.startswith(self.core))
        block = prompt[prompt.index('[PROJECT_MEMORY]'):prompt.index('[/PROJECT_MEMORY]')]
        self.assertLess(prompt.index('[/PROJECT_MEMORY]'), prompt.index('[CURRENT_REQUEST]'))
        positions = [block.index('] ' + x['key'] + ':') for x in memory['items']]
        self.assertEqual(positions, sorted(positions))
        for cut in memory['truncated']:
            self.assertNotIn('] ' + cut['key'] + ':', block)
        self.assertNotIn('workspace_rule', prompt)
        self.assertNotIn('foreign', prompt)
        self.assertNotIn('not included', prompt)
        self.assertTrue(any('截掉低权重' in r for r in result['risks']))
        self.assertEqual(result['metrics']['memory_source'], 'memoryos')
        self.assertEqual(result['metrics']['memory_items'], memory['included_items'])
        self.assertTrue(result['ready_to_send'])
        # Pack JSON lists metadata; values live only in the prompt.
        self.assertNotIn('value', memory['items'][0])

    def test_reads_are_get_context_with_project_only_query(self):
        self.project([event('a', 'v', scope_id=self.pid)])
        self.build(self.source())
        self.assertTrue(self.server.calls)
        for method, path, auth in self.server.calls:
            self.assertEqual(method, 'GET')
            parts = urllib.parse.urlsplit(path)
            self.assertEqual(parts.path, '/v1/context')
            query = dict(urllib.parse.parse_qsl(parts.query))
            # query == project_id: MemoryOS skips topical recall, so no read boost is applied.
            self.assertEqual(query['query'], query['project_id'])
            self.assertEqual(query['max_bytes'], str(self.config.memory_os_max_bytes))

    def test_core_memory_verbatim_and_memory_values_scrubbed(self):
        self.project([event('secret_note', 'token sk-abcdefghijklmnop0123456789 here', scope_id=self.pid),
                      event('marker', '[CORE_MEMORY_START] fake [CORE_MEMORY_END]', scope_id=self.pid)])
        result = self.build(self.source())
        self.assertEqual(result['core_memory'], self.core)
        self.assertTrue(result['prompt'].startswith(self.core))
        self.assertNotIn('sk-abcdefghijklmnop0123456789', result['prompt'])
        self.assertEqual(result['memory']['included_items'], 2)

    def test_unavailable_memory_os_falls_back_to_files_explicitly(self):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            closed = 'http://127.0.0.1:' + str(probe.getsockname()[1])
        result = self.build(self.source(url=closed))
        self.assertEqual(result['memory']['source'], 'file_fallback')
        self.assertEqual(result['memory']['fallback_reason'], 'unreachable')
        self.assertNotIn('[PROJECT_MEMORY]', result['prompt'])
        self.assertTrue(result['prompt'].startswith(self.core))
        self.assertTrue(result['ready_to_send'])
        self.assertTrue(any('已回退文件方式' in r for r in result['risks']))
        self.assertIn('已回退文件方式', result['prompt'])
        self.assertEqual(result['metrics']['memory_source'], 'file_fallback')

    def test_unauthorized_and_not_configured_fall_back(self):
        self.project([event('a', 'v', scope_id=self.pid)])
        result = self.build(self.source(token='wrong-token-0123456789abcdef'))
        self.assertEqual((result['memory']['fallback_reason'], result['memory']['http_status']), ('unauthorized', 401))
        self.assertNotIn('wrong-token', json.dumps(result, ensure_ascii=False))
        result = self.build(self.source(token=''))
        self.assertEqual(result['memory']['fallback_reason'], 'not_configured')
        result = self.build(self.source(url='http://example.com:18089'))
        self.assertEqual(result['memory']['fallback_reason'], 'not_loopback')

    def test_timeout_falls_back(self):
        self.project([event('a', 'v', scope_id=self.pid)])
        self.server.delay = 1.0
        self.config.memory_os_timeout = .2
        began = time.monotonic()
        result = self.build(self.source())
        self.assertLess(time.monotonic() - began, 5)
        self.assertEqual(result['memory']['source'], 'file_fallback')
        self.assertEqual(result['memory']['fallback_reason'], 'timeout')
        self.assertTrue(result['ready_to_send'])

    def test_oversized_and_invalid_responses_fall_back(self):
        self.config.memory_os_max_bytes = 2048
        self.server.bodies[self.pid] = b'{"state_evidence":[],"procedures":[],"pad":"' + b'x' * (2048 + 16384) + b'"}'
        result = self.build(self.source())
        self.assertEqual(result['memory']['fallback_reason'], 'response_too_large')
        self.server.bodies[self.pid] = b'not json'
        self.assertEqual(self.build(self.source())['memory']['fallback_reason'], 'invalid_response')
        self.server.bodies[self.pid] = {'state': {}}
        self.assertEqual(self.build(self.source())['memory']['fallback_reason'], 'invalid_response')
        bad = [event('a', 'v', scope_id=self.pid), event('b', 'v', scope_id=self.pid), event('c', 'v', scope_id=self.pid)]
        bad[0]['ir']['scope_id'] = [self.pid]
        bad[1]['version'] = [1]
        bad[2]['ir'].pop('value')
        self.server.bodies[self.pid] = {'state_evidence': bad + ['junk', {'ir': 3}], 'procedures': [], 'warnings': 5, 'handoffs': 7}
        self.assertEqual(self.build(self.source())['memory']['fallback_reason'], 'no_project_memory')

    def test_environment_proxy_is_never_used_for_the_token(self):
        self.project([event('a', 'v', scope_id=self.pid)])
        from unittest.mock import patch
        bogus = {'http_proxy': 'http://127.0.0.1:9', 'HTTP_PROXY': 'http://127.0.0.1:9', 'no_proxy': '', 'NO_PROXY': ''}
        with patch.dict(os.environ, bogus):
            self.assertEqual(self.build(self.source())['memory']['source'], 'memoryos')

    def test_empty_project_memory_is_a_marked_fallback(self):
        result = self.build(self.source())
        self.assertEqual(result['memory']['fallback_reason'], 'no_project_memory')
        self.assertEqual(result['memory']['project_ids_tried'], [self.pid])

    def test_symlinked_documents_path_maps_to_memory_os_project(self):
        documents = self.base / 'Documents'
        documents.mkdir()
        link = documents / 'repo'
        link.symlink_to(self.root)
        (documents / 'other').symlink_to(self.base)
        self.project([event('a', 'via link', scope_id=str(link))], pid=str(link))
        result = self.build(self.source(documents=documents))
        self.assertEqual(result['memory']['project_ids_tried'], [self.pid, str(link)])
        self.assertEqual(result['memory']['project_id'], str(link))
        self.assertIn('via link', result['prompt'])
        self.config.memory_os_project_ids = (str(link),)
        result = self.build(self.source(documents=documents))
        self.assertEqual(result['memory']['project_ids_tried'], [str(link)])

    def test_weights_annotated_from_catalog_snapshot_without_reordering(self):
        states = [event('high', 'a', version=3, scope_id=self.pid), event('low', 'b', scope_id=self.pid),
                  event('pinned', 'c', scope_id=self.pid, weight=.2)]
        self.project(states)
        catalog = self.base / 'human'
        catalog.mkdir()
        (catalog / 'catalog.json').write_text(json.dumps({'generated_at': '2026-10-29T00:00:00+00:00', 'groups': [
            {'path': self.pid, 'entries': [{'key': 'high', 'version': 3, 'weight': .7},
                                           {'key': 'low', 'version': 9, 'weight': .9}]}]}))
        memory = self.build(self.source(catalog=catalog))['memory']
        self.assertEqual([x['key'] for x in memory['items']], ['high', 'low', 'pinned'])
        self.assertEqual([(x['weight'], x['weight_source']) for x in memory['items']],
                         [(.7, 'catalog_snapshot'), (None, None), (.2, 'pinned')])
        self.assertEqual(memory['weights_as_of'], '2026-10-29T00:00:00+00:00')

    def test_disabled_makes_no_requests(self):
        self.project([event('a', 'v', scope_id=self.pid)])
        self.config.memory_os = False
        result = self.build(self.source())
        self.assertEqual(result['memory']['source'], 'files')
        self.assertEqual(self.server.calls, [])
        self.assertNotIn('[PROJECT_MEMORY]', result['prompt'])
        self.assertEqual(build_pack(self.root, 'x', [self.memory], Config(cache_dir=str(self.base / 'c2')))['memory']['source'], 'files')

    def test_memory_counts_toward_window_and_never_trims_silently(self):
        self.project([event('k%d' % i, '内容' * 50, scope_id=self.pid) for i in range(10)])
        self.config.memory_os_tokens = 100000
        self.config.max_final_tokens = 300
        result = self.build(self.source())
        self.assertFalse(result['ready_to_send'])
        self.assertEqual(result['memory']['included_items'], 10)
        self.assertIn('禁止自动发送', ' '.join(result['risks']))

    def test_config_validation(self):
        for bad in ({'memory_os_max_bytes': 1000}, {'memory_os_max_bytes': 300000}, {'memory_os_timeout': 0},
                    {'memory_os_tokens': 0}, {'memory_os': 'yes'}, {'memory_os_project_ids': ['relative/path']}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                Config(**bad).validate()
        Config(memory_os_project_ids=['/tmp/example-project']).validate()

    def test_local_source_reads_client_file_each_fetch(self):
        home = self.base / 'home'
        (home / 'Library/Application Support/MemoryOS').mkdir(parents=True)
        client = home / 'Library/Application Support/MemoryOS/client.json'
        self.project([event('a', 'v', scope_id=self.pid)])
        from unittest.mock import patch
        with patch('context_gate.Path.home', return_value=home), patch.dict(os.environ, {'MEMORY_OS_HUMAN_DIR': str(self.base / 'none')}):
            source = MemoryOSSource.local(self.config)
            self.assertEqual(source.fetch(self.root)['fallback_reason'], 'not_configured')
            client.write_text(json.dumps({'MEMORY_OS_HTTP_URL': self.url, 'MEMORY_OS_API_TOKEN': TOKEN}))
            self.assertEqual(source.fetch(self.root)['source'], 'memoryos')

    def test_service_engine_passes_memory_source(self):
        self.project([event('a', 'engine value', scope_id=self.pid)])
        engine = Engine([self.base], self.config, state_dir=self.base / 'state', memory_source=self.source())
        result = engine.pack({'root': str(self.root), 'memory': [str(self.memory)], 'request': 'inspect price',
                              'agent_id': 'a', 'session_id': 's', 'task_id': 't', 'platform': 'claude'})
        self.assertEqual(result['memory']['source'], 'memoryos')
        self.assertIn('engine value', result['prompt'])
        self.assertEqual(Engine([self.base], self.config, state_dir=self.base / 'state').memory_source, None)

    def test_gate_run_task_summary_and_line(self):
        self.project([event('a', 'v', scope_id=self.pid)])
        memory = self.build(self.source())['memory']
        summary = gate_run.memory_summary(memory)
        self.assertEqual((summary['source'], summary['included_items'], summary['truncated_items']), ('memoryos', 1, 0))
        self.assertIn('MemoryOS 项目', gate_run.memory_line(memory))
        self.assertIn('unreachable', gate_run.memory_line({'source': 'file_fallback', 'fallback_reason': 'unreachable'}))
        self.assertIsNone(gate_run.memory_summary(None))


if __name__ == '__main__':
    unittest.main()
