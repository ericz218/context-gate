"""Verified public rates, exact aliases, cache arithmetic and displayed provenance."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import prices
from console_data import snapshot
from token_stats import save

M={'baseline_tokens_estimated':0,'final_tokens_estimated':0}


class RouterOfficialPricesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def rule(self,model):
        return prices.price_for(model,state_dir=self.root,platform='router',mode='official')

    def test_vendor_models_and_external_prefixes_have_verified_rates(self):
        expected={
            'muse-wonder-1.0':(4,20,.2), 'meta/muse-spark-1.3':(1.25,4.25,.15),
            'muse-spark-1.3-contributor':(.1,.2,.002),
            'DeepSeek-V4-Flash':(.3,1.2,.006),'DeepSeek-V4-Flash-Vision-Exp':(.3,1.2,.006),
            'nvidia/deepseek-v4.1-flash':(.3,1.2,.006), 'deepseek-flash':(.3,1.2,.006),
            'mercury-3':(.2,.7,.02),'Qwen3.8-27B':(.5,3,.1),
            'Qwen3.8-Flash-Next':(.15,.47,.016),'xiaomi/MiMo-V2.6-Flash':(.14,.28,.0028),
            'nvidia/step-5-preview':(1,2.7,.1),
        }
        for name,rates in expected.items():
            with self.subTest(name=name):
                rule=self.rule(name)
                self.assertEqual(tuple(rule[k] for k in ('input','output','cache_read')),rates)
                self.assertEqual(rule['price_basis'],'vendor')
                self.assertTrue(rule['source'].startswith('https://'))
                self.assertEqual(rule['verified_at'],'2026-10-31')

    def test_contributor_and_free_aliases_use_the_same_model_not_nearby_names(self):
        ultra=self.rule('nvidia/nemotron-3-ultra-550b-a55b:free')
        self.assertEqual((ultra['input'],ultra['output'],ultra['cache_read']),(.5,2.2,.1))
        self.assertEqual(ultra['source_name'],'DeepInfra via OpenRouter')
        self.assertEqual(ultra['price_basis'],'provider')
        self.assertEqual(self.rule('nemotron-3-super-120b-a12b')['source_name'],'Crusoe via OpenRouter')
        for name in ('muse-spark-1.3-unknown','muse-wonder-full','muse-wonder-2.0','qwen3.8-270b',
                     'qwen3.8-flash-next-experimental','mimo-v2.6-flash-lite','nemotron-3-ultra-550b-a55b-v2'):
            with self.subTest(name=name):self.assertIsNone(self.rule(name))

    def test_every_new_rule_is_free_on_router_in_configured_cost_mode(self):
        rules=[r for r in prices.OFFICIAL_RULES if r.get('model_ids')]
        for rule in rules:
            for model in rule['model_ids']:
                with self.subTest(model=model):
                    price=prices.price_for(model,state_dir=self.root,platform='router',mode='actual')
                    self.assertTrue(prices.is_free(price))
                    self.assertEqual(prices.row_cost(model,1000000,100000,900000,state_dir=self.root,platform='router'),0)

    def test_cached_input_is_not_double_charged_and_list_basis_is_explicit(self):
        for model,cost in [('muse-wonder-1.0',2.58),('DeepSeek-V4.1-Flash',.1554),
                           ('mercury-3',.108),('Qwen3.8-27B',.44),('nemotron-3-ultra-550b-a55b',.36)]:
            with self.subTest(model=model):
                result=prices.row_cost(model,1000000,100000,900000,state_dir=self.root,platform='router',mode='official')
                self.assertAlmostEqual(result,cost)
        self.assertEqual(self.rule('mercury-3')['price_note'],'standard_list')
        self.assertEqual(self.rule('DeepSeek-V4-Flash')['price_note'],'peak_reference')
        self.assertEqual(self.rule('Qwen3.8-27B')['price_note'],'implicit_cache')
        self.assertEqual(self.rule('qwen3-14b')['cache_read'],self.rule('qwen3-14b')['input'])

    def test_paid_override_and_explicit_official_override_keep_precedence(self):
        (self.root/'prices.json').write_text(json.dumps({'rules':[{'match':'muse-spark','input':0,'output':0}],
            'official_rules':[{'match':'muse-spark-1.3-contributor','input':9,'output':11}]}))
        self.assertEqual(self.rule('muse-spark-1.3')['input'],1.25)
        self.assertEqual(self.rule('muse-spark-1.3-contributor')['input'],9)
        self.assertEqual(prices.price_for('muse-spark-1.3',state_dir=self.root)['input'],0)

    def test_snapshot_prices_old_records_without_rewriting_them_or_the_mode(self):
        for model in ['muse-wonder-1.0','muse-spark-1.3-contributor','nvidia/nemotron-3-ultra-550b-a55b:free','probe-mantle-gpt']:
            save(model,'router',M,True,{'input_tokens':1000000,'output_tokens':100000,'cached_input_tokens':900000},self.root,exit_code=0,model=model)
        with sqlite3.connect(self.root/'tokens.sqlite3') as db:
            before=db.execute('select * from turns order by id').fetchall()
        official=snapshot(self.root,health=False,cost_mode='official')
        models={m['model']:m for m in official['by_model']}
        self.assertGreater(official['summary']['cost_actual_usd'],0)
        self.assertEqual(official['unpriced_models'],['probe-mantle-gpt'])
        source=models['nvidia/nemotron-3-ultra-550b-a55b:free']['price_sources'][0]
        self.assertEqual(source['price_basis'],'provider');self.assertIn('DeepInfra',source['source_name'])
        self.assertFalse(models['probe-mantle-gpt']['free'])
        actual=snapshot(self.root,health=False,cost_mode='actual')
        self.assertEqual(actual['summary']['cost_actual_usd'],0)
        self.assertTrue(all(not m['price_sources'] for m in actual['by_model']))
        self.assertEqual(prices.load_mode(self.root),'actual')
        with sqlite3.connect(self.root/'tokens.sqlite3') as db:
            self.assertEqual(before,db.execute('select * from turns order by id').fetchall())


if __name__=='__main__':unittest.main()
