import datetime
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from console_data import snapshot,safe_log,request_detail
from token_stats import save,save_comparison


class ConsoleTests(unittest.TestCase):
    def test_verified_backboard_bill_merges_router_model_summary_and_chart_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            date = datetime.date(2026, 11, 14)
            now = datetime.datetime.combine(date, datetime.time(18)).timestamp()
            model = 'backboard/claude-opus-5-5'
            for row_id, platform, name, inputs, outputs in [
                ('covered', 'router', model, 1000000, 100000),
                ('later', 'router', model, 500000, 50000),
                ('other', 'codex', 'gpt-6.1-sol', 1000000, 0),
            ]:
                save(row_id, platform, {'baseline_tokens_estimated':0,'final_tokens_estimated':0}, True, {'input_tokens':inputs, 'output_tokens':outputs},
                     tmp, exit_code=0, model=name)
            with sqlite3.connect(Path(tmp) / 'tokens.sqlite3') as db:
                db.execute('UPDATE turns SET at=?', (now,))
            bill = {'date':date.isoformat(), 'model':model, 'usd':8.0, 'requests':1,
                    'tokens':5100000, 'input_tokens':5000000, 'output_tokens':100000,
                    'cached_tokens':4000000, 'cache_creation_tokens':0, 'covered_ids':['covered']}
            (Path(tmp) / 'backboard-billing.json').write_text(json.dumps([bill]))
            result = snapshot(tmp, 'today', now=now, health=False)
            router = next(g for g in result['by_platform'] if g['platform']=='router')
            item = next(m for m in result['by_model'] if m['model']==model)
            self.assertAlmostEqual(router['cost_actual_usd'], 11)
            self.assertAlmostEqual(item['cost_actual_usd'], 11)
            self.assertAlmostEqual(result['summary']['cost_actual_usd'], 13)
            self.assertEqual(router['actual_tokens'], 5650000)
            self.assertEqual(item['actual_input']+item['actual_output'], 5650000)
            self.assertEqual(result['summary']['actual_tokens'], 6650000)
            self.assertEqual(result['summary']['requests'], 3)
            self.assertEqual(result['series'][0]['tokens'], 6650000)
            self.assertAlmostEqual(result['series'][0]['cost'], 13)
            self.assertFalse(item['free'])
            self.assertEqual(item['provider_billed_usd'], 8)
            # Original request records keep their measured inputs and outputs.
            self.assertEqual(next(r for r in result['recent'] if r['id']=='covered')['actual_input'], 1000000)
            detail = snapshot(tmp, 'today', 'router', now=now, model=model, health=False)
            self.assertAlmostEqual(detail['summary']['cost_actual_usd'], 11)
            official = snapshot(tmp, 'today', now=now, cost_mode='official', health=False)
            self.assertAlmostEqual(official['summary']['cost_actual_usd'], 11.8)
            self.assertEqual(official['summary']['actual_tokens'], 6650000)
            codex = snapshot(tmp, 'today', 'codex', now=now, health=False)
            self.assertAlmostEqual(codex['summary']['cost_actual_usd'], 2)
            tomorrow = snapshot(tmp, 'today', now=now+86400, health=False)
            self.assertEqual(tomorrow['summary']['cost_actual_usd'], 0)
            self.assertAlmostEqual(tomorrow['series'][0]['cost'], 13)
            old_day = snapshot(tmp, day='2026-11-13', health=False)
            self.assertEqual(old_day['summary']['cost_actual_usd'], 0)

    def test_actual_estimated_cached_and_failures_are_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics={'baseline_tokens_estimated':100,'final_tokens_estimated':30,'jev_input_tokens_actual':5,'jev_output_tokens_actual':2}
            save('a','zcode',metrics,True,{'input_tokens':40,'output_tokens':10,'cached_input_tokens':20},tmp,exit_code=0,timing={'total_ms':1000})
            save('b','claude',{'baseline_tokens_estimated':10,'final_tokens_estimated':20},True,state_dir=tmp,exit_code=502,timing={'total_ms':20000})
            save('c','codex',metrics,False,state_dir=tmp,ready=False)
            save_comparison('pair','zcode',100,40,tmp)
            result=snapshot(tmp,health=False);s=result['summary']
            self.assertEqual(s['actual_tokens'],64)
            self.assertEqual(s['cached_tokens'],20)
            self.assertEqual(s['failed_requests'],1)
            self.assertEqual(s['blocked_requests'],1)
            self.assertEqual(s['mean_ms'],1000)
            self.assertEqual(s['estimated_saved'],60)
            self.assertEqual(result['global_ab']['saved'],60)
            filtered=snapshot(tmp,platform='zcode',health=False)
            self.assertEqual(filtered['summary']['requests'],1)
            self.assertEqual(filtered['summary']['actual_tokens'],57)
            self.assertEqual(len(filtered['recent']),1)
            self.assertEqual(snapshot(tmp,now=0,period='week',health=False)['summary']['requests'],2)
            with self.assertRaises(ValueError):snapshot(tmp,period='unknown')

    def test_output_speed_uses_timed_successful_requests_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            m={'baseline_tokens_estimated':0,'final_tokens_estimated':0}
            for rid,out,ms,code in [('a',100,1000.0,0),('b',300,2000.0,0),('c',50,1000.0,0),
                                    ('failed',900,1000.0,1),('untimed',900,None,0),('empty',0,1000.0,0)]:
                save(rid,'claude',m,True,{'input_tokens':10,'output_tokens':out},tmp,exit_code=code,model='claude-opus-5-5',duration_ms=ms)
            save('other','codex',m,True,{'input_tokens':10,'output_tokens':400},tmp,exit_code=0,model='gpt-6.1-sol',duration_ms=1000.0)
            result=snapshot(tmp,health=False)
            claude=next(g for g in result['by_platform'] if g['platform']=='claude')
            self.assertEqual({k:claude[k] for k in ('output_tps','tps_requests','tps_median','tps_p10','tps_p90')},
                             {'output_tps':112.5,'tps_requests':3,'tps_median':100.0,'tps_p10':50.0,'tps_p90':150.0})
            self.assertEqual((result['summary']['output_tps'],result['summary']['tps_requests']),(170.0,4))
            model=next(x for x in result['by_model'] if x['model']=='claude-opus-5-5')
            self.assertEqual((model['output_tps'],model['tps_requests']),(112.5,3))
            speeds={r['id']:r['output_tps'] for r in result['recent']}
            self.assertEqual((speeds['b'],speeds['failed'],speeds['untimed'],speeds['empty']),(150.0,None,None,None))
            detail=snapshot(tmp,platform='claude',model='claude-opus-5-5',health=False)['summary']
            self.assertEqual((detail['output_tps'],detail['tps_median']),(112.5,100.0))
            save('ag','antigravity',m,True,{'input_tokens':10,'output_tokens':400},tmp,exit_code=0,model='gemini-4-neon')
            untimed=snapshot(tmp,platform='antigravity',health=False)['summary']
            self.assertEqual((untimed['output_tps'],untimed['tps_requests'],untimed['tps_median']),(None,0,None))

    def test_platform_savings_series_free_and_generic_hidden(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics={'baseline_tokens_estimated':100,'final_tokens_estimated':60}
            save('g1','generic',metrics,True,{'input_tokens':10,'output_tokens':1},tmp,exit_code=0,model='x')
            save('f1','zcode',metrics,True,{'input_tokens':1_000_000,'output_tokens':100_000},tmp,exit_code=0,model='nvidia/nemotron-3:free')
            save('p1','zcode',metrics,True,{'input_tokens':500_000,'output_tokens':50_000},tmp,exit_code=0,model='GLM-5.3-Flash',duration_ms=1500.0)
            save('p2','zcode',metrics,True,{'input_tokens':400_000,'output_tokens':40_000},tmp,exit_code=0,model='GLM-5.3-Flash',duration_ms=500.0)
            save_comparison('ab1','zcode',1_000_000,600_000,tmp)
            result=snapshot(tmp,health=False)
            # generic (pack endpoint default label) never reaches the console
            self.assertNotIn('generic',result['platforms'])
            self.assertNotIn('generic',[g['platform'] for g in result['by_platform']])
            zcode=[g for g in result['by_platform'] if g['platform']=='router'][0]
            self.assertEqual(zcode['ab_pairs'],1)
            self.assertEqual(zcode['ab_saved_tokens'],400_000)
            # savings money at the platform's realized input rate:
            # GLM rows cost 0.10+0.08, output part 90_000*$0.5/1M=0.045 →
            # input cost 0.135 over 1.9M input tokens; free rows add nothing.
            self.assertAlmostEqual(zcode['ab_saved_usd'],0.028421,places=5)
            self.assertEqual(zcode['mean_ms'],1000.0)
            models={m['model']:m for m in result['by_model']}
            self.assertTrue(models['nvidia/nemotron-3:free']['free'])
            self.assertFalse(models['GLM-5.3-Flash']['free'])
            self.assertEqual(result['summary']['actual_tokens'],2_090_000)
            self.assertEqual(len(result['series']),1)
            self.assertEqual(result['series'][0]['tokens'],2_090_000)
            self.assertAlmostEqual(result['series'][0]['cost'],0.18,places=4)
            self.assertNotIn('history',result)

    def test_router_group_preserves_native_paid_costs_and_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics={'baseline_tokens_estimated':100,'final_tokens_estimated':60}
            usage={'input_tokens':1000,'output_tokens':100}
            save('router-client','zcode',metrics,True,usage,tmp,exit_code=0,model='GLM-5.3-Flash')
            save('zcode-paid','zcode',metrics,True,usage,tmp,exit_code=0,model='GLM-5.3-Flash')
            save('zcode-unknown','zcode',metrics,True,{'input_tokens':40,'output_tokens':4},tmp,exit_code=0,model='direct-unknown-model')
            save('router-unknown','router',metrics,True,{'input_tokens':3,'output_tokens':1},tmp,exit_code=0,model='unlisted-router-model')
            with sqlite3.connect(Path(tmp)/'tokens.sqlite3') as conn:
                conn.execute('ALTER TABLE turns ADD COLUMN provider_id TEXT')
                conn.execute("UPDATE turns SET provider_id='local-model-router' WHERE id='router-client'")
                conn.execute("UPDATE turns SET provider_id='account:zai-start-plan' WHERE id IN ('zcode-paid','zcode-unknown')")
            result=snapshot(tmp,health=False)
            models={(m['platform'],m['model']):m for m in result['by_model']}
            combined=models[('router','GLM-5.3-Flash')]
            self.assertEqual(combined['requests'],2)
            self.assertTrue(combined['priced']);self.assertFalse(combined['free'])
            self.assertAlmostEqual(combined['cost_actual_usd'],0.0002)
            self.assertEqual(combined['sources'],['zcode'])
            self.assertEqual(result['platforms'],['router'])
            self.assertEqual(result['summary']['requests'],4)
            self.assertEqual(result['summary']['free_requests'],2)
            self.assertEqual(result['summary']['free_tokens'],1104)
            self.assertEqual(result['summary']['local_router_requests'],4)
            self.assertEqual(result['summary']['actual_tokens'],2248)
            self.assertEqual(result['unpriced_models'],['direct-unknown-model'])
            detail=snapshot(tmp,platform='router',model='GLM-5.3-Flash',health=False)
            self.assertEqual({r['id'] for r in detail['recent']},{'router-client','zcode-paid'})
            source=request_detail(tmp,'router-client')['request']
            self.assertEqual(source['platform'],'router');self.assertEqual(source['client_platform'],'zcode')

    def test_platform_alias_ab_pct_and_model_detail(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics={'baseline_tokens_estimated':100,'final_tokens_estimated':60}
            save('a1','anthropic',metrics,True,{'input_tokens':100,'output_tokens':10},tmp,exit_code=0,model='claude-sonnet-5')
            save('o1','openai',metrics,True,{'input_tokens':50,'output_tokens':5},tmp,exit_code=0,model='gpt-6-luna')
            save('m1','zcode',metrics,True,{'input_tokens':10,'output_tokens':1},tmp,exit_code=0,model='GLM-5.3-Flash')
            save('m2','zcode',metrics,True,{'input_tokens':11,'output_tokens':1},tmp,exit_code=0,model='GLM-5.3-Flash')
            save_comparison('ab','claude',100,70,tmp)
            result=snapshot(tmp,health=False)
            names=[g['platform'] for g in result['by_platform']]
            # gate acceptance rows report under the daily-driver platform
            self.assertNotIn('anthropic',names);self.assertNotIn('openai',names)
            claude=[g for g in result['by_platform'] if g['platform']=='claude'][0]
            self.assertEqual(claude['requests'],1)  # the anthropic gate row merged in
            self.assertEqual(claude['ab_pairs'],1)
            self.assertEqual(claude['ab_reduction_pct'],30.0)
            # dedicated per-model detail returns that model's own latest rows
            detail=snapshot(tmp,health=False,model='GLM-5.3-Flash')
            self.assertEqual([r['id'] for r in detail['recent']],['m2','m1'])
            unknown=snapshot(tmp,health=False,model='未知模型')
            self.assertEqual(unknown['recent'],[])

    def test_legacy_rows_without_model_get_no_model_card(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics={'baseline_tokens_estimated':100,'final_tokens_estimated':50}
            save('legacy','claude',metrics,True,{'input_tokens':10,'output_tokens':1},tmp,exit_code=0)
            save('new','claude',metrics,True,{'input_tokens':10,'output_tokens':1},tmp,exit_code=0,model='claude-haiku-5-5')
            result=snapshot(tmp,health=False)
            # the legacy request still counts in totals, but has no model card and no unpriced warning
            self.assertEqual(result['summary']['requests'],2)
            self.assertEqual([m['model'] for m in result['by_model']],['claude-haiku-5-5'])
            self.assertEqual(result['unpriced_models'],[])
            self.assertEqual(result['summary']['unpriced_requests'],0)

    def test_series_hitrate_handover_audit(self):
        import console_data
        with tempfile.TemporaryDirectory() as tmp:
            metrics={'baseline_tokens_estimated':100,'final_tokens_estimated':60}
            save('h1','zcode',metrics,True,{'input_tokens':1000,'output_tokens':10,'cached_input_tokens':800},tmp,exit_code=0,model='GLM-5.3-Flash',duration_ms=100.0)
            result=snapshot(tmp,health=False)
            self.assertEqual(result['series'][0]['hitrate'],80.0)
        # handoff overview: latest entry wins, excerpts are redacted
        with tempfile.TemporaryDirectory() as outer:
            proj=Path(outer)/'proj'; (proj/'memory').mkdir(parents=True)
            (proj/'memory'/'HANDOFF.md').write_text(
                '## [2026-10-02 18:00] ZCode\n\n**做了什么**：修了 sk-abcdefghijklmnop123456 泄漏。\n'
                '**当前状态**：能跑\n**下一步**：继续推进\n**注意**：无\n\n'
                '## [2026-10-01 09:00] 旧条目\n\n**做了什么**：旧的。\n')
            index=Path(outer)/'索引.md'
            index.write_text('| 项目 | 状态 | 路径 | memory |\n|---|---|---|---|\n'
                             f'| 测试项目 | 🟢 运行中 | {proj} | memory/HANDOFF.md |\n'
                             '|---|---|---|---|\n| 项目 | 🟢 | /nonexistent | memory/HANDOFF.md |\n')
            rows=console_data.handoff_overview(index_path=index)
            self.assertEqual(len(rows),1)
            row=rows[0]
            self.assertEqual(row['project'],'测试项目')
            self.assertEqual(row['updated'],'[2026-10-02 18:00] ZCode')
            self.assertEqual(row['done'],'修了 [REDACTED] 泄漏。')
            self.assertEqual(row['next'],'继续推进')
            self.assertNotIn('sk-abcdefghijklmnop',json.dumps(rows,ensure_ascii=False))
            self.assertFalse(row['doing'])
        # credential audit: state entries checked for mode, home entries tolerated missing
        with tempfile.TemporaryDirectory() as tmp:
            import os
            token=Path(tmp)/'access-token'; token.write_text('secret-token-value')
            os.chmod(token,0o644)
            loose=Path(tmp)/'console-connection.json'; loose.write_text('{}')
            os.chmod(loose,0o644)
            rows=console_data.credential_audit(tmp)
            by={r['file']:r for r in rows}
            self.assertTrue(by['access-token']['exists'])
            self.assertEqual(by['access-token']['mode'],'644')
            self.assertEqual(by['access-token']['warn'],'权限过宽')
            self.assertTrue(by['access-token']['has_key'])
            self.assertEqual(by['connection.json']['warn'],'缺失')
            self.assertIn('~/.zshrc',[r['file'] for r in rows])

    def test_platform_without_comparison_reports_no_ab(self):
        with tempfile.TemporaryDirectory() as tmp:
            save('q1','claude',{'baseline_tokens_estimated':10,'final_tokens_estimated':5},True,{'input_tokens':10,'output_tokens':1},tmp,exit_code=0,model='claude-sonnet-5')
            result=snapshot(tmp,health=False)
            claude=[g for g in result['by_platform'] if g['platform']=='claude'][0]
            self.assertEqual(claude['ab_pairs'],0)
            self.assertEqual(claude['ab_saved_tokens'],0)
            self.assertIsNone(claude['ab_saved_usd'])

    def test_empty_database_and_log_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=snapshot(tmp,health=False)
            self.assertEqual(result['summary']['requests'],0)
            self.assertIsNone(result['summary']['mean_ms'])
            p=Path(tmp)/'service.log'
            p.write_text('Authorization: Bearer private-value\napi_key=sk-abcdefgh123456789\nhttp://127.0.0.1:1234/'+('x'*43))
            text=safe_log(Path(tmp),'service.log')
            self.assertNotIn('private-value',text)
            self.assertNotIn('abcdefgh',text)
            self.assertNotIn('x'*43,text)

    def test_cache_creation_priced_at_cache_write_rate(self):
        with tempfile.TemporaryDirectory() as tmp:
            metrics={'baseline_tokens_estimated':100,'final_tokens_estimated':50}
            save('w1','claude',metrics,True,{'input_tokens':1_000_000,'output_tokens':100_000,'cached_input_tokens':300_000,'cache_creation_input_tokens':200_000},tmp,exit_code=0,model='claude-sonnet-4-5')
            result=snapshot(tmp,health=False)
            # plain 0.5M*3 + creation 0.2M*3.75 + read 0.3M*0.3 + output 0.1M*15
            self.assertAlmostEqual(result['summary']['cost_actual_usd'],3.84)

    def test_malformed_price_config_never_crashes_or_creates_free_prices(self):
        import prices
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'prices.json'
            for raw in ('[]','null','"text"','{"rules":null}'):
                path.write_text(raw)
                self.assertEqual(prices.price_for('claude-sonnet-4',state_dir=tmp)['input'],3)
            for value in (float('inf'),float('nan'),-1,True,'2',None):
                path.write_text(json.dumps({'rules':[{'match':'custom','input':value,'output':2}]}))
                self.assertIsNone(prices.row_cost('custom',100,10,0,state_dir=tmp))
            path.write_text(json.dumps({'rules':[{'match':'','input':0,'output':0},
                                                {'match':'custom','input':1,'output':2}]}))
            self.assertIsNone(prices.price_for('unknown-model',state_dir=tmp))
            self.assertEqual(prices.row_cost('custom',1000000,1000000,0,state_dir=tmp),3)

    def test_pricing_grouping_and_unpriced_models(self):
        from prices import price_for
        self.assertEqual(price_for('claude-sonnet-4-5-20250929')['input'],3)
        self.assertEqual(price_for('claude-sonnet-5-2026xxxx')['input'],2)
        self.assertEqual(price_for('claude-opus-5-5')['input'],4)
        self.assertEqual(price_for('NVIDIA/nemotron-x:free')['input'],0)
        self.assertEqual(price_for('moonshotai/kimi-k3')['output'],0)
        self.assertEqual(price_for('gpt-6-luna')['input'],0.1)
        self.assertEqual(price_for('gpt-5.5')['output'],30)
        self.assertEqual(price_for('gpt-6-astra')['input'],10)
        self.assertEqual(price_for('gpt-6-astra')['output'],50)
        self.assertEqual(price_for('gpt-6-astra')['cache_read'],1)
        self.assertEqual(price_for('gpt-6-astra')['cache_write'],12.5)
        self.assertEqual(price_for('codex-auto-review')['input'],0)
        self.assertEqual(price_for('codex-auto-review')['output'],0)
        self.assertIsNone(price_for('mystery-model'))
        self.assertEqual(price_for('claude-haiku-5-5')['input'],0.1)
        self.assertEqual(price_for('claude-haiku-5-5')['output'],0.5)
        self.assertEqual(price_for('DeepSeek-V4-Flash')['output'],0)
        self.assertEqual(price_for('qwen3-14b')['input'],0)
        with tempfile.TemporaryDirectory() as tmp:
            metrics={'baseline_tokens_estimated':2_000_000,'final_tokens_estimated':800_000}
            save('p1','zcode',metrics,True,{'input_tokens':1_000_000,'output_tokens':100_000,'cached_input_tokens':500_000},tmp,exit_code=0,model='claude-sonnet-4-5')
            save('p2','claude',metrics,True,state_dir=tmp,exit_code=0,model='mystery-model')
            save('p3','claude',metrics,False,state_dir=tmp,ready=False,model='mystery-model')
            save('p4','zcode',metrics,True,{'input_tokens':10,'output_tokens':1},tmp,exit_code=502,model='claude-sonnet-4-5')
            result=snapshot(tmp,health=False);s=result['summary']
            # priced rows only: p1 plain 0.5M*3 + read 0.5M*0.3 + output 0.1M*15 = 3.15
            # plus p4's measured 10*3/1M + 1*15/1M = 0.000045
            self.assertAlmostEqual(s['cost_actual_usd'],3.150045)
            # sent priced rows (p1,p4): before 2M+2M=4M tokens * $3 = 12; after 0.8M+0.8M * $3 = 4.8
            self.assertAlmostEqual(s['cost_before_usd'],12.0)
            self.assertAlmostEqual(s['cost_after_est_usd'],4.8)
            self.assertEqual(s['unpriced_requests'],1)
            zcode=[g for g in result['by_platform'] if g['platform']=='router'][0]
            self.assertAlmostEqual(zcode['cost_actual_usd'],3.150045)
            self.assertEqual(zcode['unpriced_requests'],0)
            claude=[g for g in result['by_platform'] if g['platform']=='claude'][0]
            self.assertEqual(claude['unpriced_requests'],1)
            self.assertAlmostEqual(claude['cost_before_usd'],0)
            models=result['by_model']
            sonnet=[m for m in models if m['model']=='claude-sonnet-4-5'][0]
            self.assertEqual(sonnet['platform'],'router');self.assertTrue(sonnet['priced'])
            self.assertEqual(sonnet['requests'],2);self.assertEqual(sonnet['measured_requests'],2)
            mystery=[m for m in models if m['model']=='mystery-model'][0]
            self.assertFalse(mystery['priced']);self.assertEqual(mystery['requests'],1)
            self.assertEqual(result['unpriced_models'],['mystery-model'])
            self.assertTrue(result['prices_file'].endswith('prices.json'))
            rows={r['id']:r for r in result['recent']}
            self.assertEqual(rows['p1']['model'],'claude-sonnet-4-5')
