import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_gate import Config, DecisionClient, Inventory, build_pack, core_memory, parse_answers, scrub


class FakeClient:
    def __init__(self, handler=None):
        self.calls = []
        self.handler = handler

    def ask(self, provider, state, questions):
        self.calls.append((provider, state, questions))
        if self.handler:
            return self.handler(provider, state, questions, len(self.calls))
        return answers(questions)


def answers(questions, overrides=None):
    overrides = overrides or {}
    return {'answers': {k: {'choice': overrides.get(k, 'no' if k.startswith('missing_') or k in ('conflict', 'cross_module') else 'yes'),
                           'confidence': .96} for k in questions}}


class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'repo'
        self.root.mkdir()
        self.memory = self.base / 'memory.md'
        self.core = '[CORE_MEMORY_START]\r\n项目目标：保留 price 接口。\r\n[CORE_MEMORY_END]'
        self.memory.write_bytes(('前文\r\n' + self.core + '\r\n后文').encode())
        (self.root / 'price.py').write_text('from decimal import Decimal\n\ndef price(values):\n    return sum(values, Decimal("0"))\n')
        (self.root / 'test_price.py').write_text('from price import price\n\ndef test_price():\n    assert price([]) == 0\n')
        (self.root / '.env').write_text('API_KEY=never-send-this')
        (self.root / 'other.py').write_text('def unrelated():\n    return 99\n')
        self.config = Config(force_gate=True, cache_dir=str(self.base / 'cache'))

    def build(self, client=None, request='Fix price rounding', **kw):
        return build_pack(self.root, request, [self.memory], self.config, client or FakeClient(), **kw)

    def test_in_project_cache_is_never_retrieved_without_ripgrep(self):
        self.config.cache_dir = str(self.root / 'cache')
        import context_gate
        native_run = context_gate.run
        def without_rg(argv, **kw):
            if argv[0] == 'rg':
                raise FileNotFoundError('rg not installed')
            return native_run(argv, **kw)
        with patch('context_gate.run', side_effect=without_rg):
            for _ in range(3):
                inv = Inventory(self.root, self.config)
                self.assertNotIn(str(inv.cache.relative_to(self.root)), inv.records)
                self.assertTrue(inv.search(['price'], 40))
                result = self.build(request='只读解释 price.py，不要修改')
                self.assertTrue(result['ready_to_send'])

    def test_core_exact_and_no_internal_process_in_prompt(self):
        c = FakeClient()
        result = self.build(c)
        self.assertEqual(result['core_memory'], self.core)
        self.assertTrue(result['prompt'].startswith(self.core))
        self.assertEqual(result['mode'], 'filtered')
        self.assertTrue(result['ready_to_send'])
        self.assertEqual([p for p, _, _ in c.calls], ['jev'])
        self.assertNotIn('never-send-this', result['prompt'])
        self.assertNotIn('unrelated', result['prompt'])
        self.assertNotIn('gate_calls', result['prompt'])
        self.assertIn('test_price.py', result['prompt'])

    def test_readonly_named_file_does_not_match_test_prefix(self):
        c=FakeClient()
        r=self.build(c,request='Read only; do not use tools or change files. Inspect price.py. Explain price only.')
        self.assertEqual(r['mode'],'filtered')
        self.assertEqual([x['path'] for x in c.calls[0][1]['candidates']],['price.py'])
        self.assertNotIn('test_price.py',r['prompt'])

    def test_configuration_rejects_invalid_types_before_review(self):
        for field,value in [('rounds',True),('candidates',1.5),('timeout',float('nan')),('force_gate','false'),('laya_command','python')]:
            c=Config(**{field:value})
            with self.assertRaises(ValueError):c.validate()

    def test_small_context_bypasses_without_remote_call(self):
        self.config.force_gate = False
        c = FakeClient()
        r = self.build(c)
        self.assertEqual(r['mode'], 'bypass_small')
        self.assertEqual(c.calls, [])
        self.assertIn('unrelated', r['prompt'])

    def test_laya_unavailable_secondary_is_jev(self):
        def handler(provider, state, q, n):
            if provider == 'laya':
                raise RuntimeError('unavailable')
            return answers(q)
        c = FakeClient(handler)
        r = self.build(c, request='Refactor public interface price')
        self.assertEqual([p for p, _, _ in c.calls], ['jev', 'laya', 'jev'])
        self.assertEqual(len(c.calls[-1][2]), 4)
        self.assertEqual(r['mode'], 'filtered')
        self.assertIn('Laya 二审不可用', '\n'.join(r['risks']))
        self.assertNotIn('Laya 二审不可用',r['prompt'])

    def test_laya_only_secondary_four_questions(self):
        c = FakeClient()
        r = self.build(c, request='跨模块重构 price')
        self.assertEqual([p for p, _, _ in c.calls], ['jev', 'laya'])
        self.assertEqual(len(c.calls[-1][2]), 4)
        self.assertEqual(r['mode'], 'filtered')

    def test_missing_config_expands_then_succeeds(self):
        (self.root / 'settings.json').write_text('{"rounding": "half_even"}')
        def handler(provider, state, q, n):
            if n == 1:
                return answers(q, {'sufficient': 'no', 'missing_config': 'yes'})
            if n == 2:
                return answers(q, {'sufficient': 'no', 'missing_dependency': 'yes'})
            return answers(q)
        c = FakeClient(handler)
        r = self.build(c)
        self.assertEqual(r['mode'], 'filtered')
        self.assertIn('settings.json', r['prompt'])
        self.assertEqual(len(c.calls), 3)

    def test_repeated_uncertainty_full_fallback(self):
        c = FakeClient(lambda p, s, q, n: answers(q, {'sufficient': 'no', 'missing_dependency': 'yes'}))
        r = self.build(c)
        self.assertEqual(r['mode'], 'full_fallback')
        self.assertIn('unrelated', r['prompt'])
        self.assertLessEqual(len(c.calls), self.config.rounds * 2)

    def test_primary_failure_never_certified_filtered(self):
        c = FakeClient(lambda *args: {'answers': {}})
        r = self.build(c)
        self.assertEqual(r['mode'], 'full_fallback')
        self.assertIn('price.py', r['prompt'])

    def test_window_overflow_blocks_send_without_silent_truncation(self):
        self.config.max_final_tokens = 10
        r = self.build()
        self.assertFalse(r['ready_to_send'])
        self.assertEqual(r['core_memory'], self.core)
        self.assertIn('test_price.py', r['prompt'])

    def test_pack_budget_falls_back_without_dropping_required_files(self):
        self.config.pack_tokens = 1
        r = self.build()
        self.assertEqual(r['mode'], 'full_fallback')
        self.assertIn('test_price.py', r['prompt'])

    def test_path_escape_and_secret_paths_excluded(self):
        outside = self.base / 'private.py'
        outside.write_text('PRIVATE CONTENT')
        (self.root / 'escaped.py').symlink_to(outside)
        (self.root / 'secrets.json').write_text('secret content')
        (self.root / 'trace.log').write_text('irrelevant history')
        self.config.force_gate = False
        r = self.build()
        self.assertNotIn('PRIVATE CONTENT', r['prompt'])
        self.assertNotIn('secret content', r['prompt'])
        self.assertNotIn('irrelevant history', r['prompt'])

    def test_redaction_and_core_remote_only_redaction(self):
        self.memory.write_text('[CORE_MEMORY_START]\npassword=private-value\n[CORE_MEMORY_END]')
        c = FakeClient()
        r = self.build(c)
        self.assertIn('password=private-value', r['core_memory'])
        self.assertNotIn('private-value', json.dumps(c.calls))
        self.assertNotIn('hidden-token', scrub('access_token=hidden-token'))

    def test_core_markers_missing_fail_before_network(self):
        self.memory.write_text('no core markers')
        c = FakeClient()
        with self.assertRaises(ValueError):
            self.build(c)
        self.assertEqual(c.calls, [])

    def test_redaction_flags_apply_to_all_alternatives_and_lines(self):
        text = ('safe context\nAPI_KEY=synthetic-value\nnext line\n'
                'Authorization: bEaReR synthetic-token-123456\n'
                'PASSWORD=another-synthetic-value\nkept context')
        redacted = scrub(text)
        self.assertEqual(redacted, ('safe context\n[REDACTED]\nnext line\n'
                                    'Authorization: [REDACTED]\n'
                                    '[REDACTED]\nkept context'))

    def test_invalid_probability_not_used_as_confidence(self):
        with self.assertRaises(ValueError):
            parse_answers({'answers': {'sufficient': {'choice': 'yes', 'probabilities': {'yes': .99}}}}, {'sufficient': {}})

    def test_cache_refreshes_changed_file(self):
        first = Inventory(self.root, self.config)
        old = first.original_tokens
        (self.root / 'price.py').write_text('x = 1\n' * 1000)
        second = Inventory(self.root, self.config)
        self.assertGreater(second.original_tokens, old)
        with self.assertRaises(ValueError):
            first.text('price.py')

    def test_laya_remote_endpoint_rejected(self):
        self.config.laya_url = 'https://example.com/decide'
        with self.assertRaises(ValueError):
            self.build()

    def test_partial_file_identifies_enclosing_ast_symbol(self):
        (self.root / 'long.py').write_text('def rounding_target():\n' + '    x = 0\n' * 1400 + '    return x\n')
        inventory = Inventory(self.root, self.config)
        item = inventory.item('long.py', {'lines': [500], 'reason': 'symbol'})
        self.assertIn('rounding_target', item['symbol'])
        self.assertEqual(item['end_line'], 1402)

    def test_http_client_contract_and_credential_not_in_pack(self):
        received = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                received.append((self.path, self.headers.get('Authorization'), body))
                data = json.dumps(answers(body['questions'])).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        server = HTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch.dict(os.environ, {'JEV_MCP_API_KEY': 'synthetic-key',
                     'JEV_MCP_BASE_URL': 'http://127.0.0.1:' + str(server.server_port)}):
                r = self.build(DecisionClient(self.config))
            self.assertEqual(r['mode'], 'filtered')
            self.assertEqual(received[0][0], '/systemone')
            self.assertEqual(received[0][1], 'Bearer synthetic-key')
            self.assertIn('state', received[0][2])
            self.assertIn('questions', received[0][2])
            self.assertNotIn('synthetic-key', json.dumps(r))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_git_diff_must_survive_candidate_filter(self):
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        subprocess.run(['git', '-C', str(self.root), 'add', 'price.py'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        (self.root / 'price.py').write_text('def price(values):\n    return 0\n')
        r = self.build()
        diffs = [x for x in r['context_pack'] if x['source_type'] == 'git_diff']
        self.assertEqual(len(diffs), 1)
        self.assertIn('return 0', diffs[0]['content'])

    def test_cli_outputs_final_prompt_separately(self):
        script = Path(__file__).resolve().parents[1] / 'context_gate.py'
        output = self.base / 'deliverable.json'
        p = subprocess.run([sys.executable, str(script), '--root', str(self.root),
                  '--memory', str(self.memory), '--request', 'Fix price', '--output', str(output)],
                  capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = json.loads(output.read_text())
        self.assertEqual(output.with_suffix('.prompt.txt').read_bytes().decode(), data['prompt'])
        metrics = json.loads(output.with_suffix('.metrics.json').read_text())
        self.assertNotIn('core_memory', metrics)
        self.assertTrue(data['ready_to_send'])


if __name__ == '__main__':
    unittest.main()
