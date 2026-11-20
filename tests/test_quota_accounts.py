import json
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import console_quota as q
import usage_import as imp
import prices

NOW = 1700000000.0
# 时间戳取当前前一小时：usage_import 只给 48 小时内的记录打账户标签，写死日期会过期。
CLAUDE_LINE = json.dumps({'timestamp':time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime(time.time()-3600)),'type':'assistant','requestId':'req_1',
                          'message':{'id':'msg_1','model':'claude-haiku-5-5',
                                     'usage':{'input_tokens':1000,'output_tokens':50,'cache_read_input_tokens':0,'cache_creation_input_tokens':0}}})


def claude_session_line(offset_seconds=0, request_id='req_1'):
    base=time.gmtime(NOW+offset_seconds)
    stamp=time.strftime('%Y-%m-%dT%H:%M:%S.000Z',base)
    return json.dumps({'timestamp':stamp,'type':'assistant','requestId':request_id,
                       'message':{'id':'msg_'+request_id,'model':'claude-haiku-5-5',
                                  'usage':{'input_tokens':1000,'output_tokens':50,
                                           'cache_read_input_tokens':0,'cache_creation_input_tokens':0}}})


class QuotaAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.state=Path(self.tmp.name)
        self.original_state=imp.STATE
        imp.STATE=self.state
        self.original_antigravity_roots=imp.ANTIGRAVITY_ROOTS
        imp.ANTIGRAVITY_ROOTS=(self.state/'missing-antigravity',)
        self.original_deepai_pi=imp.DEEPAI_PI_ROOT
        self.original_deepai_logs=imp.DEEPAI_PROVIDER_LOGS
        imp.DEEPAI_PI_ROOT=self.state/'missing-deepai-pi'
        imp.DEEPAI_PROVIDER_LOGS=self.state/'missing-deepai-logs'
        self.conn=imp.open_ledger()
        self.conn.commit()
        self.manager=q.Quotas(self.state,
                              readers={'codex':lambda:[], 'claude':lambda:[]},
                              account_readers={'codex':lambda:'a@codex.test', 'claude':lambda:'b@claude.test'},
                              login_runner=self.runner, clock=lambda:NOW,
                              ledger=self.state/'tokens.sqlite3')
        self.login_calls=[]

    def tearDown(self):
        self.conn.close()
        imp.STATE=self.original_state
        imp.ANTIGRAVITY_ROOTS=self.original_antigravity_roots
        imp.DEEPAI_PI_ROOT=self.original_deepai_pi
        imp.DEEPAI_PROVIDER_LOGS=self.original_deepai_logs
        self.tmp.cleanup()

    def runner(self):
        self.login_calls.append(1)
        return True

    def add_row(self, row_id, platform, account, at, model='claude-haiku-5-5',
                input_total=1000, output=50, cached=0, creation=0):
        self.conn.execute('INSERT OR REPLACE INTO turns '
                          '(id,at,platform,sent,actual_input,actual_output,cached,cache_creation,model,account) '
                          'VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (row_id, at, platform, 1, input_total, output, cached, creation, model, account))
        self.conn.commit()

    def ledger_rows(self):
        return self.conn.execute('SELECT id,account FROM turns').fetchall()

    def test_open_ledger_adds_account_column(self):
        cols={r[1] for r in self.conn.execute('PRAGMA table_info(turns)')}
        self.assertIn('account', cols)

    def test_reimport_keeps_first_stamp(self):
        projects=Path(self.tmp.name)/'projects'/'p1'
        projects.mkdir(parents=True)
        (projects/'s1.jsonl').write_text(CLAUDE_LINE+'\n')
        original_projects=imp.CLAUDE_PROJECTS
        original_codex=imp.CODEX_SESSIONS
        original_zcode=imp.ZCODE_DB
        original_router=imp.ROUTER_DB
        imp.CLAUDE_PROJECTS=projects.parent
        imp.CODEX_SESSIONS=Path(self.tmp.name)/'no-codex-sessions'
        imp.ZCODE_DB=Path(self.tmp.name)/'no-zcode-db.sqlite'
        imp.ROUTER_DB=Path(self.tmp.name)/'no-router.db'
        try:
            with patch.object(imp,'claude_account',lambda:'first@x.test'), patch.object(imp,'codex_account',lambda:None):
                imp.run()
            (self.state/'usage-import-state.json').unlink()
            with patch.object(imp,'claude_account',lambda:'second@x.test'), patch.object(imp,'codex_account',lambda:None):
                imp.run()
        finally:
            imp.CLAUDE_PROJECTS=original_projects
            imp.CODEX_SESSIONS=original_codex
            imp.ZCODE_DB=original_zcode
            imp.ROUTER_DB=original_router
        rows=self.ledger_rows()
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][1],'first@x.test')

    def test_unattributed_rows_excluded(self):
        self.add_row('r1','codex',None,NOW-100)
        self.add_row('r2','codex','a@codex.test',NOW-100)
        data=self.manager.usage('codex','a@codex.test','all','5h')
        self.assertEqual(data['accounts'],['a@codex.test'])
        self.assertEqual(len(data['windows']),1)
        self.assertEqual(data['windows'][0]['tokens'],1050)

    def test_multi_account_isolation(self):
        self.add_row('r1','codex','a@codex.test',NOW-100,input_total=1000,output=50)
        self.add_row('r2','codex','b@codex.test',NOW-100,input_total=9000,output=900)
        own=self.manager.usage('codex','a@codex.test','all','5h')
        self.assertEqual(own['windows'][0]['tokens'],1050)
        everyone=self.manager.usage('codex','all','all','5h')
        self.assertEqual(everyone['windows'][0]['tokens'],1050+9900)
        usage=self.manager._window_usage('codex',{'window':'five_hour','resets_at':NOW+1000},'a@codex.test')
        self.assertEqual(usage['tokens'],1050)

    def test_rolling_windows_split_after_five_hours(self):
        self.add_row('r1','codex','a@codex.test',NOW)
        self.add_row('r2','codex','a@codex.test',NOW+3600)
        self.add_row('r3','codex','a@codex.test',NOW+6*3600)
        self.add_row('r4','codex','a@codex.test',NOW+7*3600)
        data=self.manager.usage('codex','all','all','5h')
        self.assertEqual(len(data['windows']),2)
        self.assertEqual(data['windows'][0]['start'],NOW)
        self.assertEqual(data['windows'][1]['start'],NOW+6*3600)
        self.assertEqual(data['windows'][0]['tokens'],2100)

    def test_weekly_windows_anchored_at_reset(self):
        anchor=NOW+1000
        self.manager._append_history('codex',[{'bucket':'codex','window':'weekly','remaining':80,'resets_at':anchor}])
        inside=anchor-6*86400
        before=anchor-9*86400
        self.add_row('r1','codex','a@codex.test',inside)
        self.add_row('r2','codex','a@codex.test',before)
        data=self.manager.usage('codex','all','all','week')
        self.assertTrue(data['anchored'])
        self.assertEqual(len(data['windows']),2)
        fresh=q.Quotas(Path(self.tmp.name)/'empty-state',readers={'codex':lambda:[],'claude':lambda:[]},
                       account_readers={'codex':lambda:None,'claude':lambda:None},
                       ledger=self.state/'tokens.sqlite3')
        self.assertFalse(fresh.usage('codex','all','all','week')['anchored'])
        self.assertEqual(data['windows'][-1]['end'],anchor)
        self.assertEqual(data['windows'][-1]['tokens'],1050)
        self.assertEqual(data['windows'][-1]['window_basis'],'estimated')
        self.assertIsNone(data['windows'][-1]['percent'])

    def test_window_percent_from_history(self):
        start=NOW-3600; end=start+q.WINDOW_SECONDS['five_hour']
        self.add_row('r1','codex','a@codex.test',start+10)
        self.manager._append_history('codex',[{'bucket':'codex','window':'five_hour','remaining':88.0,'resets_at':end}], 'a@codex.test')
        data=self.manager.usage('codex','a@codex.test','all','5h')
        self.assertEqual(data['windows'][0]['percent'],12.0)

    def test_history_survives_broken_lines(self):
        path=self.state/'quota-history.jsonl'
        path.write_text('{broken\n'+json.dumps({'platform':'codex','ts':NOW-5,'windows':[{'bucket':'codex','window':'weekly','remaining':70,'resets_at':NOW+9000}]})+'\n\n')
        entries=self.manager._history_windows('codex')
        self.assertEqual(len(entries),1)
        self.assertEqual(entries[0]['windows'][0]['remaining'],70)

    def test_cost_matches_row_cost(self):
        self.add_row('r1','claude','b@claude.test',NOW-100,input_total=100000,output=5000,cached=40000,creation=2000)
        data=self.manager.usage('claude','b@claude.test','all','5h',detail=1,start=NOW-1000,end=NOW+1000)
        window=data['windows'][0]
        rules=prices.load_rules(self.state)
        expected=prices.row_cost('claude-haiku-5-5',100000,5000,40000,rules=rules,state_dir=self.state,cache_creation=2000)
        if expected is None:
            self.assertIsNone(window['cost'])
        else:
            self.assertAlmostEqual(window['cost'],expected,places=6)
        if window.get('models'):
            self.assertAlmostEqual(window['models'][0]['cost'],expected,places=6)

    def test_usage_parameter_validation(self):
        with self.assertRaises(ValueError):
            self.manager.usage('gpt','all','all','5h')
        with self.assertRaises(ValueError):
            self.manager.usage('codex','all','hour','5h')
        with self.assertRaises(ValueError):
            self.manager.usage('codex','all','all','day')
        with self.assertRaises(ValueError):
            self.manager.usage('codex','ghost@x.test','all','5h')

    def test_detail_requires_valid_bounds(self):
        self.add_row('r1','codex','a@codex.test',NOW-100)
        with self.assertRaises(ValueError):
            self.manager.usage('codex','all','all','5h',detail=True,start='abc',end=NOW)
        with self.assertRaises(ValueError):
            self.manager.usage('codex','all','all','5h',detail=True,start=NOW,end=NOW-1)
        window=self.manager.usage('codex','all','all','5h')['windows'][0]
        data=self.manager.usage('codex','all','all','5h',detail=True,start=window['start'],end=window['end'])
        self.assertEqual(data['windows'][0]['models'][0]['tokens'],1050)

    def test_claude_login_debounce_and_fixed_runner(self):
        first=self.manager.claude_login()
        self.assertTrue(first['spawned'])
        second=self.manager.claude_login()
        self.assertFalse(second['spawned'])
        self.assertEqual(len(self.login_calls),1)

    def test_snapshot_carries_account_and_window_usage(self):
        resets=NOW+q.WINDOW_SECONDS['five_hour']
        manager=q.Quotas(self.state,
                         readers={'codex':lambda:[{'bucket':'codex','window':'five_hour','remaining':90.0,'resets_at':resets}],
                                  'claude':lambda:[]},
                         account_readers={'codex':lambda:'a@codex.test', 'claude':lambda:None},
                         login_runner=self.runner, clock=lambda:resets-60,
                         ledger=self.state/'tokens.sqlite3')
        self.add_row('r1','codex','a@codex.test',resets-q.WINDOW_SECONDS['five_hour']+10)
        manager.refresh('codex')
        snap=manager.snapshot()
        state=snap['platforms']['codex']
        self.assertEqual(state['account'],'a@codex.test')
        self.assertEqual(state['windows'][0]['usage']['tokens'],1050)
        self.assertEqual(snap['platforms']['claude']['windows'],[])

    def test_quota_history_capped_by_rewrite(self):
        for index in range(q.HISTORY_KEEP+5):
            self.manager._append_history('codex',[{'bucket':'codex','window':'five_hour','remaining':1,'resets_at':NOW+index}])
        entries=self.manager._history_windows('codex')
        self.assertLessEqual(len(entries),q.HISTORY_KEEP)
        self.assertEqual(entries[-1]['windows'][0]['resets_at'],NOW+q.HISTORY_KEEP+4)

    def test_ui_carries_new_elements_and_defaults(self):
        from console import quota_ui
        self.assertIn('重新登录',quota_ui.EN)
        self.assertIn('data-quota-login',quota_ui.JS)
        self.assertIn('quota-log',quota_ui.HTML)
        self.assertIn("platform:'codex'",quota_ui.JS)
        self.assertIn("tier:'5h'",quota_ui.JS)
        self.assertIn('该条件下没有用量记录',quota_ui.EN)

    def test_pending_usage_copy_explains_ledger_delay_and_reference_price(self):
        from console import quota_ui
        for label in ('等待首次本地同步', '本地用量同步中…', '本地用量同步失败', '同步状态待检查', '本窗口暂无已归属本机记录'):
            self.assertIn(label, quota_ui.JS)
            self.assertIn(label, quota_ui.EN)
        self.assertNotIn("T('暂无本地用量记录')", quota_ui.JS)
        note = '额度按检查更新，用量记录约每 5 秒更新；金额是估算，不代表订阅扣费。'
        self.assertIn(note, quota_ui.HTML)
        self.assertIn('every 5 seconds', quota_ui.EN[note])
        self.assertIn('not subscription charges', quota_ui.EN[note])

    def test_import_does_not_backfill_unattributed_history(self):
        self.add_row('old1','codex',None,NOW-90*86400)
        self.add_row('new1','codex',None,NOW-3600)
        with patch.object(imp,'CLAUDE_PROJECTS',self.state/'no-projects'),patch.object(imp,'CODEX_SESSIONS',self.state/'no-sessions'),patch.object(imp,'ZCODE_DB',self.state/'no.db'),patch.object(imp,'ROUTER_DB',self.state/'no-router.db'),patch.object(imp,'claude_account',lambda:None),patch.object(imp,'codex_account',lambda:'current@test'):
            imp.run()
        self.assertEqual(dict(self.ledger_rows()),{'old1':None,'new1':None})

    def test_switch_without_restart_clears_snapshot_and_refreshes(self):
        account=['a@codex.test']; remaining=[90]
        manager=q.Quotas(self.state,readers={'codex':lambda:{'account':account[0], 'windows':[{'bucket':'codex','window':'five_hour','remaining':remaining[0],'resets_at':NOW+1000}]}},
                         account_readers={'codex':lambda:account[0],'claude':lambda:None},clock=lambda:NOW)
        manager.refresh('codex'); self.assertEqual(manager.snapshot()['platforms']['codex']['account'],account[0])
        account[0]='b@codex.test'; remaining[0]=80
        state=manager.snapshot()['platforms']['codex']
        self.assertEqual(state['account'],account[0]); self.assertEqual(state['windows'],[])
        self.assertEqual(state['status'],'not_checked'); self.assertFalse(state['settings']['enabled'])
        self.assertFalse(state['settings']['stop_all'])
        manager.refresh('codex'); state=manager.snapshot()['platforms']['codex']
        self.assertEqual(state['account'],account[0]); self.assertEqual(state['windows'][0]['remaining'],80)
        self.assertIsNotNone(state['read_duration_ms'])

    def test_failed_read_after_switch_does_not_show_previous_windows(self):
        account=['a@codex.test']; fail=[False]
        def reader():
            if fail[0]: raise q.QuotaError('test failure')
            return [{'bucket':'codex','window':'five_hour','remaining':90,'resets_at':NOW+1000}]
        manager=q.Quotas(self.state,readers={'codex':reader},account_readers={'codex':lambda:account[0],'claude':lambda:None},clock=lambda:NOW)
        manager.refresh('codex'); account[0]='b@codex.test'; fail[0]=True
        manager.snapshot(); manager.refresh('codex')
        state=manager.snapshot()['platforms']['codex']
        self.assertEqual(state['account'],account[0]);self.assertEqual(state['windows'],[])
        self.assertEqual(state['status'],'error');self.assertIsNone(state['updated_at'])

    def test_window_usage_cache_includes_account_and_empty_is_unknown(self):
        window={'window':'five_hour','resets_at':NOW+1000}
        self.add_row('a','codex','a@codex.test',NOW,input_total=100,output=1)
        self.add_row('b','codex','b@codex.test',NOW,input_total=900,output=1)
        self.assertEqual(self.manager._window_usage('codex',window,'a@codex.test')['tokens'],101)
        self.assertEqual(self.manager._window_usage('codex',window,'b@codex.test')['tokens'],901)
        missing=self.manager._window_usage('codex',window,'missing@test')
        self.assertIsNone(missing['tokens']);self.assertEqual(missing['reason'],'not_recorded')

    def test_percent_matches_snapshot_when_estimated_window_is_minutes_off(self):
        start=NOW-3600; end=start+q.WINDOW_SECONDS['five_hour']
        self.manager._append_history('claude',[{'window':'five_hour','remaining':77.0,'resets_at':end-415}],'a@claude.test')
        self.assertEqual(self.manager._window_percent('claude','five_hour',start,end,'a@claude.test'),(23.0,None))
        # A snapshot that already belongs to the next real window must not fill this row.
        self.manager._append_history('claude',[{'window':'five_hour','remaining':99.0,'resets_at':end+q.WINDOW_SECONDS['five_hour']-415}],'a@claude.test')
        self.assertEqual(self.manager._window_percent('claude','five_hour',start,end,'a@claude.test'),(23.0,None))
        self.assertEqual(self.manager._window_percent('claude','five_hour',start,end,'b@claude.test'),(None,'no_snapshot'))

    def test_percent_snapshots_are_account_scoped_and_all_is_unknown(self):
        start=NOW-3600; end=start+q.WINDOW_SECONDS['five_hour']
        windows=[{'window':'five_hour','remaining':80,'resets_at':end}]
        self.manager._append_history('codex',windows,'a@codex.test')
        self.assertEqual(self.manager._window_percent('codex','five_hour',start,end,'a@codex.test'),(20,None))
        self.assertEqual(self.manager._window_percent('codex','five_hour',start,end,'b@codex.test'),(None,'no_snapshot'))
        self.assertEqual(self.manager._window_percent('codex','five_hour',start,end,'all'),(None,'multiple_accounts'))
        self.manager._append_history('codex',windows)
        self.assertEqual(self.manager._window_percent('codex','five_hour',start,end,'b@codex.test'),(None,'unattributed_snapshot'))
        self.assertEqual(self.manager._window_percent('codex','five_hour',start-604800,end-604800,'a@codex.test'),(None,'no_snapshot'))

    def test_reimport_keeps_first_stamp_when_current_account_unknown(self):
        projects=self.state/'projects'/'p';projects.mkdir(parents=True)
        (projects/'s.jsonl').write_text(claude_session_line()+'\n')
        with patch.object(imp,'CLAUDE_PROJECTS',projects.parent),patch.object(imp,'CODEX_SESSIONS',self.state/'none'),patch.object(imp,'ZCODE_DB',self.state/'none.db'),patch.object(imp,'ROUTER_DB',self.state/'none-router.db'),patch.object(imp.time,'time',lambda:NOW):
            with patch.object(imp,'claude_account',lambda:'first@test'),patch.object(imp,'codex_account',lambda:None): imp.run()
            (self.state/'usage-import-state.json').unlink()
            with patch.object(imp,'claude_account',lambda:None),patch.object(imp,'codex_account',lambda:None): imp.run()
        self.assertEqual(self.ledger_rows()[0][1],'first@test')

    def test_old_worker_reply_after_switch_cannot_alert_or_stop(self):
        account=['a@codex.test']; notices=[]; stops=[]
        def reader():
            old=account[0]; account[0]='b@codex.test'
            return {'account':old,'windows':[{'bucket':'codex','window':'five_hour','remaining':1,'resets_at':NOW+1000}]}
        manager=q.Quotas(self.state,readers={'codex':reader},account_readers={'codex':lambda:account[0],'claude':lambda:None},clock=lambda:NOW,
                         notifier=lambda p:notices.append(p),stop_handler=lambda p:stops.append(p))
        prefs=manager.settings();prefs['codex']['stop_all']=True;manager.settings(prefs)
        manager.refresh('codex');state=manager.snapshot()['platforms']['codex']
        self.assertEqual(state['account'],'b@codex.test');self.assertEqual(state['windows'],[])
        self.assertEqual(notices,[]);self.assertEqual(stops,[])

    def test_switch_wakes_enabled_reader_without_changing_settings(self):
        account=['a@codex.test']
        manager=q.Quotas(self.state,account_readers={'codex':lambda:account[0],'claude':lambda:None},clock=lambda:NOW)
        prefs=manager.settings();prefs['codex']['enabled']=True;manager.settings(prefs)
        manager.snapshot();manager.wake.clear();account[0]='b@codex.test';manager.snapshot()
        self.assertTrue(manager.wake.is_set());self.assertEqual(manager.states['codex']['next_at'],NOW)
        self.assertEqual(manager.settings(),prefs)

    def test_codex_account_and_quota_share_one_rpc_process(self):
        class Stream(io.BytesIO):
            def fileno(self): return 999
            def write(self, data):
                messages.append(json.loads(data));return super().write(data)
        class Selector:
            def __enter__(self): return self
            def __exit__(self,*args): return False
            def register(self,*args): pass
            def select(self,*args): return [True]
        for first,last,expected in [('a@test','a@test','a@test'),('a@test','b@test','error'),(None,None,None)]:
            messages=[]
            process=type('Process',(),{'stdin':Stream(),'stdout':Stream(),'poll':lambda self:0})()
            replies=[{'id':1,'result':{}},
                     {'id':2,'result':{'account':{'type':'chatgpt','email':first}}},
                     {'id':3,'result':{'rateLimits':{'primary':{'usedPercent':10,'windowDurationMins':300,'resetsAt':NOW+1000}}}},
                     {'id':4,'result':{'account':{'type':'chatgpt','email':last}}}]
            raw=('\n'.join(json.dumps(row) for row in replies)+'\n').encode()
            with patch.object(q.subprocess,'Popen',return_value=process) as spawn,patch.object(q.selectors,'DefaultSelector',return_value=Selector()),patch.object(q.os,'read',return_value=raw):
                if expected=='error':
                    with self.assertRaises(q.QuotaError): q.read_codex()
                else:
                    result=q.read_codex();self.assertEqual(result['account'],expected)
                    self.assertEqual(result['windows'][0]['remaining'],90)
            self.assertEqual(spawn.call_count,1)
            self.assertEqual([row['method'] for row in messages],['initialize','initialized','account/read','account/rateLimits/read','account/read'])
            self.assertEqual([row['params'] for row in messages if row['method']=='account/read'],[{'refreshToken':False},{'refreshToken':False}])

    def test_refresh_cadence_counts_from_start_and_never_overlaps(self):
        for elapsed in (2,8):
            clock=[100.0]; calls=[]; manager=None
            def reader():
                calls.append(clock[0]); manager.refresh('codex')
                clock[0]+=elapsed
                return [{'bucket':'codex','window':'five_hour','remaining':90,'resets_at':NOW+1000}]
            manager=q.Quotas(self.state,readers={'codex':reader},account_readers={'codex':lambda:'a@test','claude':lambda:None},clock=lambda:clock[0])
            prefs=manager.settings();prefs['codex']['interval']=5;manager.settings(prefs)
            manager.refresh('codex'); state=manager.states['codex']
            expected=max(100+elapsed,105)
            self.assertEqual(state['next_at'],expected);self.assertEqual(state['retry_at'],expected)
            self.assertEqual(calls,[100]);self.assertFalse(state['refreshing'])
            clock[0]=expected;manager.refresh('codex')
            self.assertEqual(calls,[100,expected])

    def test_signed_out_during_rpc_does_not_accept_old_identity(self):
        account=['a@test'];stops=[]
        def reader():
            account[0]=None
            return {'account':'a@test','windows':[{'bucket':'codex','window':'five_hour','remaining':1,'resets_at':NOW+1000}]}
        manager=q.Quotas(self.state,readers={'codex':reader},account_readers={'codex':lambda:account[0],'claude':lambda:None},clock=lambda:NOW,stop_handler=lambda p:stops.append(p))
        prefs=manager.settings();prefs['codex']['stop_all']=True;manager.settings(prefs)
        manager.refresh('codex');state=manager.snapshot()['platforms']['codex']
        self.assertIsNone(state['account']);self.assertEqual(state['windows'],[]);self.assertEqual(stops,[])


if __name__=='__main__':

    unittest.main()
