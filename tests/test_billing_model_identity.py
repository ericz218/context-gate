import datetime
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

import prices
from console_data import snapshot, request_detail
from token_stats import save


class BillingIdentityTests(unittest.TestCase):
    def test_antigravity_efforts_share_one_model_without_losing_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            for effort in ['low','medium','high']:
                save(effort,'antigravity',{'baseline_tokens_estimated':0,'final_tokens_estimated':0},True,{'input_tokens':1000,'output_tokens':100,'cached_input_tokens':200},tmp,exit_code=0,model='gemini-3.8-flash-'+effort)
            result=snapshot(tmp,health=False,platform='antigravity')
            self.assertEqual(len(result['by_model']),1)
            model=result['by_model'][0]
            self.assertEqual(model['model'],'gemini-3.8-flash');self.assertEqual(model['requests'],3)
            self.assertTrue(model['priced']);self.assertGreater(model['cost_actual_usd'],0)
            detail=snapshot(tmp,health=False,platform='antigravity',model='gemini-3.8-flash')
            self.assertEqual({r['reasoning_effort'] for r in detail['recent']},{'low','medium','high'})
            single=request_detail(tmp,'high')['request']
            self.assertEqual(single['original_model'],'gemini-3.8-flash-high')
            with sqlite3.connect(Path(tmp)/'tokens.sqlite3') as c:
                self.assertEqual(c.execute("select model from turns where id='high'").fetchone()[0],'gemini-3.8-flash-high')

    def test_local_claude_models_move_but_anthropic_models_stay(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ['claude-sonnet-5','qwen2.5-coder:7b','nemotron-3-super-120b-a12b']:
                save(name,'claude',{'baseline_tokens_estimated':0,'final_tokens_estimated':0},True,{'input_tokens':100,'output_tokens':20},tmp,exit_code=0,model=name)
            result=snapshot(tmp,health=False)
            by={m['model']:m for m in result['by_model']}
            self.assertEqual(by['claude-sonnet-5']['platform'],'claude')
            for name in ['qwen2.5-coder:7b','nemotron-3-super-120b-a12b']:
                self.assertEqual(by[name]['platform'],'router');self.assertTrue(by[name]['free'])
                self.assertEqual(by[name]['sources'],['claude'])
            self.assertEqual(result['summary']['requests'],3)

    def test_terra_short_long_and_cache_pricing(self):
        rule=prices.price_for('gpt-6.1-terra')
        self.assertEqual((rule['input'],rule['output'],rule['cache_read']),(1,5,.05))
        # 200k plain + 50k cache + 1k output at standard rates.
        self.assertAlmostEqual(prices.row_cost('gpt-6.1-terra',250000,1000,50000),.2075)
        # Entire 300k prompt uses long-context rates, not only its excess.
        self.assertAlmostEqual(prices.row_cost('gpt-6.1-terra',300000,1000,50000),.5125)
        self.assertEqual(prices.price_for('gpt-6.1-terra',platform='router')['input'],0)

    def test_gemini_verified_promotion_applies_by_request_date(self):
        before=datetime.datetime(2026,12,31,tzinfo=datetime.timezone.utc).timestamp()
        after=datetime.datetime(2027,1,1,tzinfo=datetime.timezone.utc).timestamp()
        self.assertAlmostEqual(prices.row_cost('gemini-3.8-flash',1000000,1000000,100000,at=before),4.4325)
        self.assertAlmostEqual(prices.row_cost('gemini-3.8-flash',1000000,1000000,100000,at=after),8.865)
        self.assertIsNone(prices.price_for('gemini-3.8-flash-tts'))
        self.assertIsNone(prices.price_for('gemini-3.8-flash-lite'))


if __name__=='__main__':unittest.main()
