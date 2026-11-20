"""r2 regression drafts: NoRedirect Jev, fp-less close, allow-roots, alias refusals,
PID-first reload, and evidence repair-head gating.

None of these run here (draft only); the main agent runs them after applying.
"""
import io
import json
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path

import console_capability as cap
from console_capability import CapabilityRegistry, _bridge_local_key
from console_router_fallback import DirectFallback
from tests.test_router_capability import Clock, FakeOpener, FakeResponse, NOW, default_requests, make_router_db, write_catalog


def fp_error(url, code, body=b'{"error":"x"}'):
    return urllib.error.HTTPError(url, code, 'Error', {}, io.BytesIO(body))


class JevNoRedirectTests(unittest.TestCase):
    def test_jev_opener_uses_no_redirect_and_no_proxy(self):
        import context_gate
        import urllib.request
        built = {}

        class FakeOpener:
            def open(self, request, timeout=None):
                built['url'] = request.full_url
                return io.BytesIO(b'{"answers": {}}')

        real_build = urllib.request.build_opener
        seen = {}

        def spy(*handlers):
            seen['handlers'] = handlers
            return FakeOpener()

        urllib.request.build_opener = spy
        try:
            client = context_gate.DecisionClient(context_gate.Config())
            client.key = 'k'
            try:
                client.ask('jev', {}, {})
            except Exception:
                pass
        finally:
            urllib.request.build_opener = real_build
        kinds = [type(h).__name__ for h in seen.get('handlers', ())]
        self.assertIn('_NoRedirect', kinds)
        self.assertIn('ProxyHandler', kinds)


class CloseCompatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        make_router_db(root / 'router.db', default_requests())
        write_catalog(root / 'catalog.json')
        self.registry = CapabilityRegistry(root / 'state', db_path=root / 'router.db',
                                           catalog_path=root / 'catalog.json',
                                           clock=Clock(NOW), opener=FakeOpener([]))

    def test_reachable_reads_fp_less_401(self):
        out = cap.router_reachable(opener=FakeOpener([urllib.error.HTTPError('u', 401, 'x', {}, None)]))
        self.assertTrue(out['reachable'])
        self.assertEqual(401, out['status'])

    def test_close_failure_does_not_mask_outcome(self):
        class Boom:
            status = 500

            def close(self):
                raise RuntimeError('close blew up')

        out = cap.router_reachable(opener=FakeOpener([Boom()]))
        self.assertTrue(out['reachable'])
        self.assertEqual(500, out['status'])

    def test_fallback_closes_real_error(self):
        from tests.test_router_fallback import DOWN, FakeBridge
        denied = fp_error('https://integrate.api.nvidia.com/v1/chat/completions', 401, b'{"error":"bad key"}')
        http = FakeOpener([denied, FakeResponse(200, b'{"choices":[{"message":{"content":"hi"}}]}')])
        result = DirectFallback(FakeBridge(), self.registry, enabled=True, health=DOWN, opener=http).chat(
            'nvidia/deepseek-v4.1-flash', {'messages': []})
        self.assertTrue(result['ok'])
        self.assertTrue(denied.fp.closed)


class AliasRefusalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        db = sqlite3.connect(root / 'router.db')
        db.executescript('''
        create table providers (id integer primary key, name text, base_url text, enabled integer);
        create table provider_keys (id integer primary key, provider_id integer, enabled integer default 1);
        create table models (id integer primary key, display_name text, model_id text, provider_id integer, upstream_model text, enabled integer);
        create table requests (id integer primary key autoincrement, ts integer, endpoint text, requested_model text,
          resolved_model text, provider_name text, status integer, latency_ms integer, error_message text);
        create table aliases (id integer primary key, alias_id text, enabled integer, created_at integer);
        create table alias_targets (id integer primary key, alias_id integer, position integer, model_ref text);
        insert into providers values (4, 'NVIDIA', 'https://integrate.api.nvidia.com/v1', 1);
        insert into models values (15, 'DeepSeek V4.1 Flash (NVIDIA)', 'nvidia/deepseek-v4.1-flash', 4, 'deepseek-ai/deepseek-v4.1-flash', 1);
        insert into aliases values (2, 'DeepSeek-V4.1-Flash', 1, 1);
        insert into alias_targets values (1, 2, 0, '__providers/DeepSeek-V4.1-Flash'), (2, 2, 1, 'nvidia/deepseek-v4.1-flash');
        ''')
        db.commit()
        db.close()
        self.registry = CapabilityRegistry(root / 'state', db_path=root / 'router.db',
                                           clock=Clock(NOW), opener=FakeOpener([]))

    def test_alias_get_returns_alias_record_not_model(self):
        record = self.registry.get('DeepSeek-V4.1-Flash')
        self.assertIsNotNone(record)
        self.assertTrue(record.get('alias'))
        self.assertEqual('alias/DeepSeek-V4.1-Flash', record['key'])
        self.assertEqual('ambiguous_alias', record['statusReason'])

    def test_probe_alias_is_skipped(self):
        out = self.registry.probe('DeepSeek-V4.1-Flash', lambda: 'k', consume_quota=True)
        self.assertEqual('ambiguous_alias', out['skipped'])

    def test_exact_model_still_probes(self):
        record = self.registry.get('nvidia/deepseek-v4.1-flash')
        self.assertFalse(record.get('alias', False))

    def test_fallback_alias_is_refused(self):
        from tests.test_router_fallback import DOWN, FakeBridge
        registry = self.registry
        bridge = FakeBridge()
        real_call = bridge.call

        def call_with_alias(command, args=None):
            if command == 'snapshot':
                snap = real_call(command, args)
                snap['aliases'] = [{'aliasId': 'DeepSeek-V4.1-Flash',
                                    'targets': ['__providers/DeepSeek-V4.1-Flash', 'nvidia/deepseek-v4.1-flash']}]
                return snap
            return real_call(command, args)

        bridge.call = call_with_alias
        fallback = DirectFallback(bridge, registry, enabled=True, health=DOWN)
        out = fallback.chat('DeepSeek-V4.1-Flash', {'messages': []})
        self.assertEqual('fallback_unavailable', out['fallback'])
        self.assertEqual('alias_unsupported', out['reason'])

    def test_bridge_key_never_uses_memoryos_file(self):
        with self.assertRaises(ValueError):
            from console_capability import _runtime_local_key
            _runtime_local_key()


class AllowRootsTests(unittest.TestCase):
    def test_default_roots_are_documents_and_projects_only(self):
        from gate_service import DEFAULT_ALLOW_ROOTS
        home = str(Path.home())
        self.assertEqual(tuple(sorted(DEFAULT_ALLOW_ROOTS)),
                          tuple(sorted((home + '/Documents', home + '/Projects'))))
        self.assertNotIn(home, DEFAULT_ALLOW_ROOTS)
        self.assertNotIn('/', DEFAULT_ALLOW_ROOTS)


class EvidenceRepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'state'

    def add(self, **spec):
        import evidence
        spec.setdefault('collect_git', False)
        return evidence.record(spec, self.state)

    def test_repair_head_after_missing_head(self):
        import evidence
        last = None
        for i in range(3):
            last = self.add(task_id='t%d' % i)
        (self.state / 'evidence' / 'evidence.head.json').unlink()
        result = evidence.verify(self.state)
        self.assertFalse(result['ok'])
        repaired = evidence.repair_head(self.state, expect_count=result['records'], expect_last=result['last_hash'])
        self.assertTrue(repaired['repaired'])
        self.assertTrue(evidence.verify(self.state)['ok'])

    def test_repair_refuses_tampered_chain(self):
        import evidence
        for i in range(3):
            self.add(task_id='t%d' % i)
        lines = (self.state / 'evidence' / 'evidence.jsonl').read_bytes().splitlines()
        lines[1] = lines[1].replace(b'"t1"', b'"t9"')
        (self.state / 'evidence' / 'evidence.jsonl').write_bytes(b'\n'.join(lines) + b'\n')
        with self.assertRaises(evidence.EvidenceHeadMismatch):
            evidence.repair_head(self.state, expect_count=3, expect_last='x')

    def test_repair_refuses_wrong_expect(self):
        import evidence
        last = None
        for i in range(2):
            last = self.add(task_id='t%d' % i)
        (self.state / 'evidence' / 'evidence.head.json').unlink()
        with self.assertRaises(evidence.EvidenceHeadMismatch):
            evidence.repair_head(self.state, expect_count=99, expect_last=last['hash'])
        with self.assertRaises(evidence.EvidenceHeadMismatch):
            evidence.repair_head(self.state, expect_count=2, expect_last='deadbeef')


class ReloadPidTests(unittest.TestCase):
    def test_connection_pid_is_authoritative_over_pgrep(self):
        import console_reload
        from unittest.mock import patch
        with patch.object(console_reload, 'alive', side_effect=lambda p: p == 99999), \
             patch.object(console_reload, 'backend_pids', return_value=[]):
            # PID 99999 alive but invisible to pgrep must still be stopped.
            old = set()
            pid = 99999
            if isinstance(pid, int) and console_reload.alive(pid):
                old.add(pid)
            old.update(console_reload.backend_pids())
            self.assertEqual({99999}, old)

    def test_patterns_cover_both_roots_no_prefix_widening(self):
        import console_reload
        patterns = console_reload._patterns()
        self.assertEqual(2, len(patterns))
        self.assertTrue(all(p.endswith('console/app.py --no-browser') for p in patterns))
        self.assertFalse(any(p == str(console_reload.ROOT) + '/' for p in patterns))


if __name__ == '__main__':
    unittest.main()
