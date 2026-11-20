import json
from pathlib import Path
import sys
import tempfile
import unittest
import threading
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from token_stats import UsageCollector, measured_usage, save, save_comparison, totals

class TokenTests(unittest.TestCase):
    def test_stream_completion_and_persistent_timing(self):
        c=UsageCollector('anthropic')
        c.feed('event: message_stop\ndata: {"type":"message_')
        self.assertFalse(c.completed)
        c.feed('stop"}\n\n');self.assertTrue(c.completed)
        c.feed('{"type":"error","error":{"type":"overloaded"}}');self.assertTrue(c.has_error)
        with tempfile.TemporaryDirectory() as folder:
            metrics={'baseline_tokens_estimated':10,'final_tokens_estimated':5}
            save('one','zcode',metrics,True,state_dir=folder,timing={'endpoint':'/v1/messages','prepare_ms':20})
            save('one','zcode',metrics,True,state_dir=folder,exit_code=0,timing={'endpoint':'/v1/messages','prepare_ms':20,'total_ms':100,'stream_completed':True})
            save('two','zcode',metrics,True,state_dir=folder,exit_code=0,duration_ms=4321.0)
            import sqlite3
            with sqlite3.connect(str(Path(folder)/'tokens.sqlite3')) as db:
                row=db.execute('SELECT prepare_ms,total_ms,stream_completed FROM request_timings').fetchone()
                turns=dict(db.execute('SELECT id,duration_ms FROM turns'))
            self.assertEqual(row,(20,100,1));self.assertEqual(totals(folder)['sent_turns'],2)
            # gate timing falls back into turns.duration_ms; an explicit value wins
            self.assertEqual(turns['one'],100.0);self.assertEqual(turns['two'],4321.0)

    def test_totals_tolerates_import_rows_without_estimates(self):
        with tempfile.TemporaryDirectory() as t:
            import sqlite3
            with sqlite3.connect(str(Path(t)/'tokens.sqlite3')) as db:
                db.execute('CREATE TABLE turns (id TEXT PRIMARY KEY, at REAL, platform TEXT, sent INTEGER, before_est INTEGER, after_est INTEGER, jev_est INTEGER, actual_input INTEGER, actual_output INTEGER, cached INTEGER, exit_code INTEGER)')
                db.execute("INSERT INTO turns VALUES ('imp1',0,'zcode',1,NULL,NULL,0,10,2,0,0)")
            a=totals(t)
            self.assertEqual(a['sent_turns'],1)
            self.assertEqual(a['before_tokens_estimated'],0)
            self.assertEqual(a['provider_actual_input_tokens'],10)

    def test_parallel_first_writes_do_not_race_schema_migrations(self):
        with tempfile.TemporaryDirectory() as folder:
            barrier=threading.Barrier(8)
            def write(i):
                barrier.wait()
                save(str(i),'agent',{'baseline_tokens_estimated':10,'final_tokens_estimated':5},True,
                     {'input_tokens':5,'output_tokens':1},state_dir=folder)
            with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(write,range(8)))
            result=totals(folder)
            self.assertEqual(result['sent_turns'],8)
            self.assertEqual(result['provider_actual_input_tokens'],40)

    def test_cache_accounting_differs_by_provider(self):
        a=measured_usage('claude',{'type':'result','usage':{'input_tokens':2,'cache_read_input_tokens':100,'cache_creation_input_tokens':30,'output_tokens':5}})
        b=measured_usage('codex',{'type':'turn.completed','usage':{'input_tokens':132,'cached_input_tokens':100,'output_tokens':5}})
        self.assertEqual(a['input_tokens'],132);self.assertEqual(b['input_tokens'],132)
    def test_chunked_pretty_zcode_and_stream_events(self):
        c=UsageCollector('zcode');text='banner\n'+json.dumps({'usage':{'inputTokens':50,'outputTokens':7}},indent=2)
        for character in text:c.feed(character)
        self.assertEqual(c.usage['input_tokens'],50)
        c=UsageCollector('codex')
        event=json.dumps({'type':'turn.completed','usage':{'input_tokens':10,'output_tokens':2}})
        c.feed(event+'\n'+event);self.assertEqual(c.usage['input_tokens'],20)
    def test_unknown_and_invalid_usage_not_zero(self):
        self.assertIsNone(measured_usage('codex',{'type':'turn.failed'}))
        self.assertIsNone(measured_usage('zcode',{'usage':{'inputTokens':-5}}))
    def test_cumulative_idempotent_blocked_and_negative_savings(self):
        with tempfile.TemporaryDirectory() as t:
            m={'baseline_tokens_estimated':100,'final_tokens_estimated':120,'jev_input_tokens_estimated':10}
            save('one','codex',m,True,{'input_tokens':140,'output_tokens':7},t)
            save('one','codex',m,True,{'input_tokens':140,'output_tokens':7},t)
            save('two','claude',m,False,state_dir=t)
            a=totals(t)
            self.assertEqual(a['sent_turns'],1);self.assertEqual(a['blocked_turns'],1)
            self.assertEqual(a['saved_pack_tokens_estimated'],-20)
            self.assertEqual(a['net_saved_including_jev_estimated'],-30)
            self.assertEqual(a['provider_actual_input_tokens'],140)
            self.assertIsNone(a['actual_savings'])

    def test_actual_ab_is_idempotent_and_keeps_negative_savings(self):
        with tempfile.TemporaryDirectory() as t:
            save_comparison('one','codex',100,90,t)
            save_comparison('one','codex',100,90,t)
            save_comparison('two','claude',50,70,t)
            a=totals(t)
            self.assertEqual(a['actual_savings'],-10)
            self.assertEqual(a['actual_ab_pairs'],2)
            self.assertEqual(a['sent_turns'],0)
            with self.assertRaises(ValueError):save_comparison('bad','codex',True,5,t)

    def test_api_stream_usage_not_double_counted(self):
        c=UsageCollector('anthropic')
        c.feed(json.dumps({'type':'message_start','message':{'usage':{'input_tokens':10,'cache_read_input_tokens':20,'output_tokens':1}}}))
        c.feed(json.dumps({'type':'message_delta','usage':{'output_tokens':5}}))
        self.assertEqual(c.usage,{'input_tokens':30,'cached_input_tokens':20,'output_tokens':5,'cache_creation_input_tokens':0})
        c=UsageCollector('openai')
        c.feed(json.dumps({'type':'response.completed','response':{'usage':{'input_tokens':10,'input_tokens_details':{'cached_tokens':3},'output_tokens':5}}}))
        self.assertEqual(c.usage['input_tokens'],10)
        self.assertEqual(c.usage['cached_input_tokens'],3)
        self.assertEqual(c.usage['cache_creation_input_tokens'],0)

    def test_cache_creation_tracked_separately_for_claude(self):
        c=UsageCollector('claude')
        c.feed(json.dumps({'type':'result','usage':{'input_tokens':10,'cache_creation_input_tokens':30,'cache_read_input_tokens':20,'output_tokens':4}}))
        self.assertEqual(c.usage,{'input_tokens':60,'cached_input_tokens':20,'output_tokens':4,'cache_creation_input_tokens':30})
        with tempfile.TemporaryDirectory() as t:
            metrics={'baseline_tokens_estimated':10,'final_tokens_estimated':5}
            save('cc1','claude',metrics,True,c.usage,t)
            import sqlite3
            with sqlite3.connect(str(Path(t)/'tokens.sqlite3')) as db:
                row=db.execute('SELECT actual_input,cached,cache_creation FROM turns').fetchone()
            self.assertEqual(row,(60,20,30))

    def test_nullable_usage_does_not_break_stream_or_invent_input(self):
        c=UsageCollector('anthropic')
        c.feed(json.dumps({'type':'message_start','message':{'usage':{'input_tokens':None,'output_tokens':None}}}))
        c.feed(json.dumps({'type':'message_delta','usage':{'output_tokens':4}}))
        self.assertIsNone(c.usage)
        c.feed(json.dumps({'type':'message_start','message':{'usage':{'input_tokens':20,'cache_read_input_tokens':None,'output_tokens':None}}}))
        self.assertEqual(c.usage['input_tokens'],20)

    def test_model_extracted_from_streams_and_stored(self):
        c=UsageCollector('claude')
        c.feed(json.dumps({'type':'message_start','message':{'model':'claude-sonnet-4-5','usage':{'input_tokens':1,'output_tokens':1}}}))
        self.assertEqual(c.model,'claude-sonnet-4-5')
        c=UsageCollector('zcode')
        c.feed(json.dumps({'model_id':'nvidia/nemotron:free','response':'纯文本回答，不是字典'}))
        self.assertEqual(c.model,'nvidia/nemotron:free')
        c=UsageCollector('codex')
        c.feed(json.dumps({'type':'turn.completed','usage':{'input_tokens':1,'output_tokens':1}}))
        self.assertIsNone(c.model)
        with tempfile.TemporaryDirectory() as t:
            metrics={'baseline_tokens_estimated':10,'final_tokens_estimated':5}
            save('m1','claude',metrics,True,{'input_tokens':1,'output_tokens':1},t,model='claude-sonnet-4-5')
            save('m2','codex',metrics,True,state_dir=t)
            import sqlite3
            with sqlite3.connect(str(Path(t)/'tokens.sqlite3')) as db:
                rows=dict(db.execute('SELECT id,model FROM turns').fetchall())
            self.assertEqual(rows['m1'],'claude-sonnet-4-5');self.assertIsNone(rows['m2'])

    def test_legacy_database_without_model_column_migrates(self):
        with tempfile.TemporaryDirectory() as t:
            import sqlite3
            with sqlite3.connect(str(Path(t)/'tokens.sqlite3')) as db:
                db.execute('CREATE TABLE turns (id TEXT PRIMARY KEY, at REAL, platform TEXT, sent INTEGER, before_est INTEGER, after_est INTEGER, jev_est INTEGER, actual_input INTEGER, actual_output INTEGER, cached INTEGER, exit_code INTEGER)')
                db.execute("INSERT INTO turns VALUES ('old','0','claude','1','100','50','0','10','2','0','0')")
            metrics={'baseline_tokens_estimated':100,'final_tokens_estimated':50}
            save('new','claude',metrics,True,{'input_tokens':10,'output_tokens':2},t,model='claude-haiku-4-5')
            result=totals(t)
            self.assertEqual(result['sent_turns'],2)
            with sqlite3.connect(str(Path(t)/'tokens.sqlite3')) as db:
                rows=dict(db.execute('SELECT id,model FROM turns').fetchall())
            self.assertEqual(rows['new'],'claude-haiku-4-5');self.assertIsNone(rows['old'])
