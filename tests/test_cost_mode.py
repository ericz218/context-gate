"""Console cost-display toggle: 'actual' (free shown as $0) vs 'official'
(every request at the model's official list price; models without an
official price stay unpriced, never $0 and never guessed)."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import prices
import console_data as cd
from console_data import snapshot
from token_stats import save

M = {'baseline_tokens_estimated': 0, 'final_tokens_estimated': 0}


class OfficialPriceRuleTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.tmp = self.folder.name

    def price(self, model, mode, platform=None):
        return prices.price_for(model, state_dir=self.tmp, platform=platform, mode=mode)

    def test_router_requests_free_in_actual_priced_by_model_in_official(self):
        self.assertEqual(self.price('GLM-5.3', 'actual', 'router')['input'], 0)
        self.assertEqual(self.price('GLM-5.3', 'official', 'router')['input'], 1.4)
        self.assertEqual(self.price('gpt-6-astra', 'official', 'router')['output'], 50)
        # Bedrock-style ids match the vendor's own list price by substring.
        self.assertEqual(self.price('us.anthropic.claude-opus-5-5', 'official', 'router')['input'], 4)

    def test_free_to_me_rules_fall_through_to_official_price(self):
        # Kimi K3 is $0 on the owner's free NVIDIA key; official list is $3/$15.
        self.assertEqual(self.price('moonshotai/kimi-k3', 'actual')['input'], 0)
        rule = self.price('moonshotai/kimi-k3', 'official')
        self.assertEqual((rule['input'], rule['output'], rule['cache_read']), (3, 15, 0.3))
        self.assertEqual(self.price('us.xai.grok-4.7', 'official')['output'], 6)
        self.assertEqual(self.price('gpt-5.6-terra', 'actual')['input'], 2)
        self.assertEqual(self.price('gpt-5.6-terra', 'official')['output'], 12)
        self.assertEqual(self.price('gpt-oss-120b-medium', 'actual')['output'], 0.6)
        self.assertEqual(self.price('metamuse/muse-wonder-1.0', 'actual')['input'], 4)
        self.assertEqual(self.price('mercury/mercury-3', 'actual')['output'], 0.7)
        self.assertEqual(self.price('us.anthropic.claude-fable-5-1', 'official')['input'], 10)

    def test_models_without_official_price_stay_unpriced_never_zero(self):
        for model in ('gemini-pro', 'gemini-flash', 'gemini-flash-lite',
                      'qwen14b', 'qwen2.5-coder:7b', 'Hunyuan3', 'Longcat-2.5',
                      'MiniCPM5-2B', 'probe-mantle-gpt'):
            with self.subTest(model=model):
                self.assertIsNone(self.price(model, 'official', 'router'))
                self.assertIsNone(prices.row_cost(model, 1000, 10, 0, state_dir=self.tmp,
                                                  platform='router', mode='official'))

    def test_vendor_listed_zero_price_survives_official_mode(self):
        # Codex auto review is listed as free by OpenAI itself (official_free).
        self.assertEqual(self.price('codex-auto-review', 'official')['output'], 0)

    def test_user_rules_zero_ignored_paid_kept_official_rules_first(self):
        Path(self.tmp, 'prices.json').write_text(json.dumps({
            'rules': [{'match': 'muse-spark', 'input': 0, 'output': 0},
                      {'match': 'gpt-5.6-luna', 'input': 0.2, 'output': 1.2}],
            'official_rules': [{'match': 'mercury-3', 'input': 0.2, 'output': 0.7},
                               {'match': 'file-only-official', 'input': 9, 'output': 9},
                               {'match': 'bad', 'input': 'x', 'output': 1}]}))
        self.assertEqual(self.price('muse-spark-1.3', 'actual')['input'], 0)
        self.assertEqual(self.price('muse-spark-1.3', 'official')['output'],4.25)
        self.assertEqual(self.price('gpt-5.6-luna', 'official')['output'], 1.2)
        self.assertEqual(self.price('mercury-3', 'official', 'router')['output'], 0.7)
        # A verified list price fills 按付费设置 when the owner has no rate.
        # A price that exists only under the file's official_rules does not.
        self.assertEqual(self.price('mercury-3', 'actual')['input'], 0.2)
        self.assertIsNone(self.price('file-only-official', 'actual'))
        self.assertIsNone(self.price('bad-model', 'official'))

    def test_mode_persists_and_bad_values_fall_back_to_actual(self):
        self.assertEqual(prices.load_mode(self.tmp), 'actual')
        prices.save_mode(self.tmp, 'official')
        self.assertEqual(prices.load_mode(self.tmp), 'official')
        self.assertEqual(oct(os.stat(prices.mode_path(self.tmp)).st_mode & 0o777), '0o600')
        with self.assertRaises(ValueError):
            prices.save_mode(self.tmp, 'cheap')
        prices.mode_path(self.tmp).write_text('{"mode":"weird"}')
        self.assertEqual(prices.load_mode(self.tmp), 'actual')
        prices.mode_path(self.tmp).write_text('not json')
        self.assertEqual(prices.load_mode(self.tmp), 'actual')


class OfficialSnapshotTests(unittest.TestCase):
    def seed(self, tmp):
        # Paid Claude row: same price in both modes.
        save('c1', 'claude', M, True, {'input_tokens': 1_000_000, 'output_tokens': 100_000}, tmp,
             exit_code=0, model='claude-sonnet-5')
        # Free route through Local Model Router to a model with an official price.
        save('r1', 'router', M, True, {'input_tokens': 1_000_000, 'output_tokens': 1_000_000}, tmp,
             exit_code=0, model='GLM-5.3')
        # Free route to a model with no official price (local unpriced model).
        save('r2', 'router', M, True, {'input_tokens': 2_000, 'output_tokens': 500}, tmp,
             exit_code=0, model='qwen14b')
        # Free NVIDIA key, priced $0 by the owner, official price exists.
        save('z1', 'zcode', M, True, {'input_tokens': 1_000_000, 'output_tokens': 0}, tmp,
             exit_code=0, model='moonshotai/kimi-k3')

    def test_actual_mode_is_unchanged_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.seed(tmp)
            result = snapshot(tmp, health=False)
            s = result['summary']
            self.assertEqual(result['cost_mode'], 'actual')
            self.assertAlmostEqual(s['cost_actual_usd'], 3.0)  # Sonnet 5 $2 + $1
            self.assertEqual(s['free_requests'], 3)
            self.assertEqual(s['local_router_requests'], 3)
            self.assertEqual(s['unpriced_requests'], 0)
            self.assertEqual(result['unpriced_models'], [])

    def test_official_mode_prices_free_requests_and_flags_unpriced(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.seed(tmp)
            prices.save_mode(tmp, 'official')
            result = snapshot(tmp, health=False)
            s = result['summary']
            self.assertEqual(result['cost_mode'], 'official')
            # 3.0 (Sonnet) + 1.4 + 4.4 (GLM-5.3 via router) + 3.0 (Kimi K3)
            self.assertAlmostEqual(s['cost_actual_usd'], 11.8)
            self.assertEqual(s['free_requests'], 0)
            self.assertEqual(s['unpriced_requests'], 1)
            self.assertEqual(s['unpriced_tokens'], 2_500)
            self.assertEqual(result['unpriced_models'], ['qwen14b'])
            router = next(g for g in result['by_platform'] if g['platform'] == 'router')
            self.assertAlmostEqual(router['cost_actual_usd'], 8.8)
            self.assertEqual(router['unpriced_requests'], 1)
            models = {m['model']: m for m in result['by_model']}
            self.assertFalse(models['qwen14b']['priced'])
            self.assertFalse(models['qwen14b']['free'])
            self.assertTrue(models['GLM-5.3']['priced'])
            # Trend series uses the same mode as the cards.
            self.assertAlmostEqual(sum(p['cost'] for p in result['series']), 11.8, places=3)
            # An explicit override wins over the persisted toggle.
            self.assertEqual(snapshot(tmp, health=False, cost_mode='actual')['summary']['cost_actual_usd'], 3.0)

    def test_cached_snapshot_switches_mode_without_serving_stale_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.seed(tmp)
            cd._snapshot_cache.clear()
            self.addCleanup(cd._snapshot_cache.clear)
            first = cd.snapshot_cached(tmp, 'all', 'all')
            self.assertEqual(first['cost_mode'], 'actual')
            prices.save_mode(tmp, 'official')
            second = cd.snapshot_cached(tmp, 'all', 'all')
            self.assertEqual(second['cost_mode'], 'official')
            self.assertAlmostEqual(second['summary']['cost_actual_usd'], 11.8)
            prices.save_mode(tmp, 'actual')
            self.assertEqual(cd.snapshot_cached(tmp, 'all', 'all')['cost_mode'], 'actual')


class CostModeRouteTests(unittest.TestCase):
    def test_post_cost_mode_persists_and_rejects_unknown(self):
        from console.app import make_server
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(0, tmp)
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True).start()
            base = 'http://127.0.0.1:' + str(server.server_port) + '/' + server.local_token

            def post(payload):
                request = urllib.request.Request(base + '/v1/settings/cost-mode', data=json.dumps(payload).encode(),
                                                 headers={'Content-Type': 'application/json'}, method='POST')
                return urllib.request.urlopen(request, timeout=5)
            try:
                with post({'mode': 'official'}) as r:
                    self.assertEqual(json.load(r), {'ok': True, 'mode': 'official'})
                self.assertEqual(prices.load_mode(tmp), 'official')
                with urllib.request.urlopen(base + '/v1/stats', timeout=10) as r:
                    self.assertEqual(json.load(r)['cost_mode'], 'official')
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post({'mode': 'free-for-all'})
                self.assertEqual(ctx.exception.code, 400)
                self.assertEqual(prices.load_mode(tmp), 'official')
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
