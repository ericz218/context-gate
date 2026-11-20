import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import usage_import as imp


def iso_now(offset_seconds=0):
    base=time.gmtime(time.time()+offset_seconds)
    return time.strftime('%Y-%m-%dT%H:%M:%S.000Z',base)


def make_zcode_db(folder, completed_at=7000, provider_column=True):
    """A stand-in for the ZCode app ledger with the columns the importer reads."""
    path=Path(folder)/'db.sqlite'
    db=sqlite3.connect(str(path))
    extra=', provider_id TEXT' if provider_column else ''
    db.execute('CREATE TABLE model_usage (id TEXT PRIMARY KEY, model_id TEXT, started_at INTEGER, completed_at INTEGER, duration_ms INTEGER, status TEXT, input_tokens INTEGER, output_tokens INTEGER, cache_read_input_tokens INTEGER, cache_creation_input_tokens INTEGER'+extra+')')
    if provider_column:
        db.execute("INSERT INTO model_usage VALUES ('u1','GLM-5.3-Flash',?,?,6000,'completed',1000,20,900,0,'local-model-router')", (completed_at-6000,completed_at))
        db.execute("INSERT INTO model_usage VALUES ('u2','nvidia/nemotron-3:free',?,?,6000,'completed',500,5,400,0,'account:zai-start-plan')", (completed_at-5000,completed_at+1000))
        db.execute("INSERT INTO model_usage VALUES ('u3','GLM-5.3-Flash',3000,NULL,NULL,'running',10,1,0,0,'builtin:zai-start-plan')")
    else:
        db.execute("INSERT INTO model_usage VALUES ('u1','GLM-5.3-Flash',?,?,6000,'completed',1000,20,900,0)", (completed_at-6000,completed_at))
        db.execute("INSERT INTO model_usage VALUES ('u2','nvidia/nemotron-3:free',?,?,6000,'completed',500,5,400,0)", (completed_at-5000,completed_at+1000))
        db.execute("INSERT INTO model_usage VALUES ('u3','GLM-5.3-Flash',3000,NULL,NULL,'running',10,1,0,0)")
    db.commit();db.close()
    return path


def make_router_db(folder, rows):
    path=Path(folder)/'router.db'
    db=sqlite3.connect(str(path))
    db.execute('CREATE TABLE requests (id INTEGER PRIMARY KEY, ts INTEGER NOT NULL, requested_model TEXT NOT NULL, resolved_model TEXT, status INTEGER NOT NULL, latency_ms INTEGER NOT NULL, prompt_tokens INTEGER, completion_tokens INTEGER, total_tokens INTEGER)')
    db.executemany('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?)',rows)
    db.commit();db.close()
    return path


class UsageImportTests(unittest.TestCase):
    def setUp(self):
        self.original_globals={name:getattr(imp,name) for name in
                               ('STATE','CLAUDE_PROJECTS','CODEX_SESSIONS','ZCODE_DB','ROUTER_DB','ANTIGRAVITY_ROOTS','DEEPAI_PI_ROOT','DEEPAI_PROVIDER_LOGS')}
        self.router_tmp=tempfile.TemporaryDirectory()
        imp.ROUTER_DB=Path(self.router_tmp.name)/'missing-router.db'
        # Keep tests hermetic: never scan the developer's real Antigravity DBs.
        imp.ANTIGRAVITY_ROOTS=(Path(self.router_tmp.name)/'missing-antigravity',)
        imp.DEEPAI_PI_ROOT=Path(self.router_tmp.name)/'missing-deepai-pi'
        imp.DEEPAI_PROVIDER_LOGS=Path(self.router_tmp.name)/'missing-deepai-logs'

    def tearDown(self):
        for name,value in self.original_globals.items():
            setattr(imp,name,value)
        self.router_tmp.cleanup()

    def test_claude_parser_keeps_duration(self):
        entry={'type':'assistant','timestamp':iso_now(),'durationMs':1234,'requestId':'req_1','message':{'id':'msg_1','model':'claude-opus-5-5','usage':{'input_tokens':10,'cache_creation_input_tokens':30,'cache_read_input_tokens':60,'output_tokens':4}}}
        entries=list(imp.claude_entries(json.dumps(entry)+'\n'))
        self.assertEqual(len(entries),1)
        at,model,input_total,output,cached,creation,duration,key=entries[0]
        self.assertEqual(model,'claude-opus-5-5')
        self.assertEqual((input_total,output,cached,creation),(100,4,60,30))
        self.assertEqual(duration,1234)
        no_duration=list(imp.claude_entries(json.dumps({k:v for k,v in entry.items() if k!='durationMs'})+'\n'))
        self.assertIsNone(no_duration[0][6])

    def test_codex_parser_model_and_usage(self):
        text='\n'.join([
            json.dumps({'type':'session_meta','payload':{'id':'s1'}}),
            json.dumps({'type':'turn_context','payload':{'model':'gpt-6-luna'}}),
            json.dumps({'timestamp':iso_now(),'type':'token_usage_record','payload':{'response_id':'resp_1','usage':{'input_tokens':27833,'cached_input_tokens':100,'cache_write_input_tokens':0,'output_tokens':249}}}),
            json.dumps({'timestamp':iso_now(5),'type':'token_usage_record','payload':{'response_id':'resp_bad','usage':{'output_tokens':1}}}),
        ])+'\n'
        entries,model=imp.codex_entries(text)
        self.assertEqual(model,'gpt-6-luna')
        self.assertEqual(len(entries),1)
        at,entry_model,input_total,output,cached,creation,duration,key=entries[0]
        self.assertEqual((entry_model,input_total,output,cached),('gpt-6-luna',27833,249,100))
        self.assertEqual(key,'resp_1')
        # a chunk starting mid-turn seeds the model from import state
        tail=json.dumps({'timestamp':iso_now(9),'type':'token_usage_record','payload':{'response_id':'resp_2','usage':{'input_tokens':7,'output_tokens':2}}})+'\n'
        entries,model=imp.codex_entries(tail,'gpt-6-luna')
        self.assertEqual(entries[0][1],'gpt-6-luna')
        self.assertEqual(entries[0][2],7)

    def test_zcode_db_rows_completed_only_with_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            imp.ZCODE_DB=make_zcode_db(tmp)
            rows=list(imp.zcode_db_rows(0))
            self.assertEqual(len(rows),2)
            at,model,input_total,output,cached,creation,duration,row_id,marker,provider_id=rows[0]
            self.assertEqual(model,'GLM-5.3-Flash')
            self.assertEqual((input_total,output,cached,creation,duration),(1000,20,900,0,6000.0))
            self.assertEqual(row_id,'u1')
            self.assertEqual(marker,7000)
            self.assertEqual(provider_id,'local-model-router')
            # past the lookback window nothing is re-yielded; the running row never appears
            self.assertEqual(list(imp.zcode_db_rows(8000+imp.ZCODE_DB_LOOKBACK_MS+1)),[])

    def test_zcode_provider_backfill_changes_metadata_only_and_repeats_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/'state'; state.mkdir()
            imp.STATE=state; imp.ZCODE_DB=make_zcode_db(root,7000)
            imp.CLAUDE_PROJECTS=root/'missing-claude'; imp.CODEX_SESSIONS=root/'missing-codex'
            imp.ROUTER_DB=root/'missing-router.db'
            row_id='imp-zcode-'+hashlib.sha1(b'zdb|u1').hexdigest()[:24]
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                db.execute('CREATE TABLE turns (id TEXT PRIMARY KEY, at REAL, platform TEXT, sent INTEGER, before_est INTEGER, after_est INTEGER, jev_est INTEGER, actual_input INTEGER, actual_output INTEGER, cached INTEGER, exit_code INTEGER, model TEXT, duration_ms REAL)')
                db.execute("INSERT INTO turns (id,at,platform,sent,before_est,after_est,jev_est,actual_input,actual_output,cached,exit_code,model,duration_ms) VALUES (?,7,'zcode',1,900,800,0,1000,20,900,0,'GLM-5.3-Flash',55)", (row_id,))
                original=db.execute('SELECT at,platform,sent,before_est,after_est,actual_input,actual_output,cached,exit_code,model,duration_ms FROM turns WHERE id=?',(row_id,)).fetchone()
            offsets={imp.ZCODE_DB_KEY:8000+imp.ZCODE_DB_LOOKBACK_MS+1}
            (state/'usage-import-state.json').write_text(json.dumps(offsets))
            self.assertEqual(imp.run(),(0,0))
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                updated=db.execute('SELECT at,platform,sent,before_est,after_est,actual_input,actual_output,cached,exit_code,model,duration_ms,provider_id FROM turns WHERE id=?',(row_id,)).fetchone()
                count=db.execute('SELECT COUNT(*) FROM turns').fetchone()[0]
            self.assertEqual(updated[:-1],original)
            self.assertEqual(updated[-1],'local-model-router')
            self.assertEqual(count,1)
            saved=json.loads((state/'usage-import-state.json').read_text())
            self.assertIs(saved[imp.ZCODE_PROVIDER_BACKFILL_KEY],True)
            self.assertEqual(imp.run(),(0,0))
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM turns').fetchone()[0],1)
                self.assertEqual(db.execute('SELECT provider_id FROM turns WHERE id=?',(row_id,)).fetchone()[0],'local-model-router')

    def test_zcode_provider_backfill_waits_for_schema_and_lookback_replace_keeps_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/'legacy-state'; state.mkdir()
            imp.STATE=state; imp.ZCODE_DB=make_zcode_db(root,7000,provider_column=False)
            self.assertTrue(all(row[-1] is None for row in imp.zcode_db_rows(0)))
            imp.CLAUDE_PROJECTS=root/'missing-claude'; imp.CODEX_SESSIONS=root/'missing-codex'; imp.ROUTER_DB=root/'missing-router.db'
            (state/'usage-import-state.json').write_text(json.dumps({imp.ZCODE_DB_KEY:8000+imp.ZCODE_DB_LOOKBACK_MS+1}))
            imp.run()
            self.assertNotIn(imp.ZCODE_PROVIDER_BACKFILL_KEY,json.loads((state/'usage-import-state.json').read_text()))

            # A schema with provider_id keeps it through the regular completed-row lookback REPLACE.
            state2=root/'current-state'; state2.mkdir()
            source2=root/'current-source'; source2.mkdir()
            imp.STATE=state2; imp.ZCODE_DB=make_zcode_db(source2, int(time.time()*1000))
            first=imp.run()
            self.assertGreater(first[0],0)
            row_id='imp-zcode-'+hashlib.sha1(b'zdb|u1').hexdigest()[:24]
            with sqlite3.connect(state2/'tokens.sqlite3') as db:
                before=db.execute('SELECT actual_input,actual_output,provider_id FROM turns WHERE id=?',(row_id,)).fetchone()
            self.assertEqual(before,(1000,20,'local-model-router'))
            with sqlite3.connect(imp.ZCODE_DB) as db:
                db.execute("UPDATE model_usage SET provider_id='account:zai-start-plan' WHERE id='u1'")
            imp.run()
            with sqlite3.connect(state2/'tokens.sqlite3') as db:
                after=db.execute('SELECT actual_input,actual_output,provider_id FROM turns WHERE id=?',(row_id,)).fetchone()
                count=db.execute("SELECT COUNT(*) FROM turns WHERE id=?",(row_id,)).fetchone()[0]
            self.assertEqual(after,(1000,20,'account:zai-start-plan'))
            self.assertEqual(count,1)
            old_source=root/'provider-column-missing';old_source.mkdir()
            imp.ZCODE_DB=make_zcode_db(old_source,int(time.time()*1000),provider_column=False)
            imp.run()
            with sqlite3.connect(state2/'tokens.sqlite3') as db:
                self.assertEqual(db.execute('SELECT actual_input,actual_output,provider_id FROM turns WHERE id=?',(row_id,)).fetchone(),
                                 (1000,20,'account:zai-start-plan'))

    def test_full_run_imports_all_sources_and_dedupes(self):
        with tempfile.TemporaryDirectory() as tmp:
            imp.STATE=Path(tmp)
            projects=Path(tmp)/'projects'; (projects/'projA').mkdir(parents=True)
            claude_text=json.dumps({'type':'assistant','timestamp':iso_now(),'durationMs':900,'requestId':'req_1','message':{'id':'msg_1','model':'claude-opus-5-5','usage':{'input_tokens':10,'cache_creation_input_tokens':30,'cache_read_input_tokens':60,'output_tokens':4}}})+'\n'
            (projects/'projA'/'s.jsonl').write_text(claude_text)
            sessions=Path(tmp)/'sessions'; (sessions/'2026'/'10'/'02').mkdir(parents=True)
            codex_text='\n'.join([
                json.dumps({'type':'turn_context','payload':{'model':'gpt-6-luna'}}),
                json.dumps({'timestamp':iso_now(),'type':'token_usage_record','payload':{'response_id':'resp_1','usage':{'input_tokens':132,'cached_input_tokens':100,'cache_write_input_tokens':0,'output_tokens':5}}}),
            ])+'\n'
            (sessions/'2026'/'10'/'02'/'rollout-x.jsonl').write_text(codex_text)
            original=(imp.CLAUDE_PROJECTS,imp.CODEX_SESSIONS,imp.ZCODE_DB)
            imp.CLAUDE_PROJECTS=projects; imp.CODEX_SESSIONS=sessions; imp.ZCODE_DB=make_zcode_db(tmp)
            # a row left by the retired model-io source: same request as zdb u1,
            # different row id — the zdb source must not double-count it
            with sqlite3.connect(str(Path(tmp)/'tokens.sqlite3')) as db:
                db.execute('CREATE TABLE IF NOT EXISTS turns (id TEXT PRIMARY KEY, at REAL, platform TEXT, sent INTEGER, before_est INTEGER, after_est INTEGER, jev_est INTEGER, actual_input INTEGER, actual_output INTEGER, cached INTEGER, exit_code INTEGER, ready INTEGER, model TEXT)')
                db.execute("INSERT INTO turns (id,at,platform,sent,before_est,after_est,jev_est,actual_input,actual_output,cached,exit_code,ready,model) VALUES ('mio-1',7.0,'zcode',1,1000,1000,0,1000,20,900,0,1,'GLM-5.3-Flash')")
            try:
                imported,skipped=imp.run()
                self.assertEqual(imported,3)  # claude + codex + zdb u2
                self.assertEqual(skipped,1)   # zdb u1 deduped against mio-1
                imported,skipped=imp.run()
                # file offsets skip re-reads; the zcode lookback re-records by the
                # same id (idempotent REPLACE), so the ledger count stays at 4.
                self.assertEqual(imported,1); self.assertEqual(skipped,1)
                with sqlite3.connect(str(Path(tmp)/'tokens.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM turns').fetchone()[0],4)
                    # imported rows carry no pack estimates at all
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM turns WHERE id LIKE 'imp-%' AND (before_est IS NOT NULL OR after_est IS NOT NULL)").fetchone()[0],0)
                    rows=dict(db.execute('SELECT id,model FROM turns'))
                    provider_ids=dict(db.execute('SELECT id,provider_id FROM turns'))
                self.assertEqual(rows['imp-zcode-'+hashlib.sha1(b'zdb|u2').hexdigest()[:24]],'nvidia/nemotron-3:free')
                self.assertEqual(rows['imp-codex-'+hashlib.sha1(b'resp_1').hexdigest()[:24]],'gpt-6-luna')
                self.assertEqual(provider_ids['imp-zcode-'+hashlib.sha1(b'zdb|u2').hexdigest()[:24]],'account:zai-start-plan')
                at=str(list(imp.claude_entries(claude_text))[0][0])
                with sqlite3.connect(str(Path(tmp)/'tokens.sqlite3')) as db:
                    duration=dict(db.execute('SELECT id,duration_ms FROM turns'))
                self.assertEqual(duration['imp-claude-'+hashlib.sha1(('msg_1|req_1|'+at).encode()).hexdigest()[:24]],900.0)
                # a watch row identical to the imported claude entry nearby blocks a
                # re-parse from a duplicate file (different row id, same fingerprint).
                from token_stats import save
                save('w1','claude',{'baseline_tokens_estimated':100,'final_tokens_estimated':100},True,{'input_tokens':100,'output_tokens':4,'cached_input_tokens':60},tmp,exit_code=0,model='claude-opus-5-5')
                (projects/'projA'/'s2.jsonl').write_text(claude_text)
                imported,skipped=imp.run()
                self.assertEqual(skipped,2); self.assertEqual(imported,1)
                with sqlite3.connect(str(Path(tmp)/'tokens.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM turns').fetchone()[0],5)
            finally:
                imp.CLAUDE_PROJECTS,imp.CODEX_SESSIONS,imp.ZCODE_DB=original


    def test_subagent_transcripts_are_imported(self):
        # Claude Code writes subagent transcripts one level deeper
        # (projects/<proj>/<session>/subagents/agent-*.jsonl); the watcher
        # never sees that traffic, so the importer is the only source.
        with tempfile.TemporaryDirectory() as tmp:
            imp.STATE=Path(tmp)
            projects=Path(tmp)/'projects'; session=projects/'projA'/'sess-1'
            (session/'subagents').mkdir(parents=True)
            sub_text=json.dumps({'type':'assistant','timestamp':iso_now(),'requestId':'req_sub','message':{'id':'msg_sub','model':'claude-sonnet-5-5','usage':{'input_tokens':200,'cache_read_input_tokens':5000,'output_tokens':30}}})+'\n'
            (session/'subagents'/'agent-1.jsonl').write_text(sub_text)
            (session/'subagents'/'agent-1.meta.json').write_text('{"title":"x"}')
            original=(imp.CLAUDE_PROJECTS,imp.ZCODE_DB,imp.CODEX_SESSIONS)
            imp.CLAUDE_PROJECTS=projects
            imp.ZCODE_DB=Path(tmp)/'missing.sqlite'
            imp.CODEX_SESSIONS=Path(tmp)/'missing-sessions'
            try:
                imported,skipped=imp.run()
                self.assertEqual((imported,skipped),(1,0))
                with sqlite3.connect(str(Path(tmp)/'tokens.sqlite3')) as db:
                    rows=db.execute('SELECT id,model FROM turns').fetchall()
                at=str(list(imp.claude_entries(sub_text))[0][0])
                self.assertEqual(rows,[('imp-claude-'+hashlib.sha1(('msg_sub|req_sub|'+at).encode()).hexdigest()[:24],'claude-sonnet-5-5')])
            finally:
                imp.CLAUDE_PROJECTS,imp.ZCODE_DB,imp.CODEX_SESSIONS=original

    def test_router_history_is_idempotent_and_visible_in_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)
            now=int(time.time()*1000)
            imp.STATE=state
            imp.CLAUDE_PROJECTS=state/'missing-claude'
            imp.CODEX_SESSIONS=state/'missing-codex'
            imp.ZCODE_DB=state/'missing-zcode.db'
            imp.ROUTER_DB=make_router_db(tmp,[
                (11,now,'requested-a','Resolved-Model',200,1250,100,20,120),
                (12,now+1000,'failed-model',None,503,0,None,None,None),
                (13,now+2000,'failed-model','Resolved-Failure',429,12,3,0,3),
            ])
            first=imp.run()
            self.assertEqual(first,(3,0))
            second=imp.run()
            self.assertEqual(second,(3,0))
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                rows=db.execute('SELECT id,at,platform,sent,before_est,after_est,actual_input,actual_output,cached,exit_code,ready,model,cache_creation,duration_ms FROM turns ORDER BY at').fetchall()
            self.assertEqual(len(rows),3)
            self.assertEqual(rows[0][0],f'imp-router-11-{now}')
            self.assertEqual(rows[0][2:13],('router',1,None,None,100,20,0,0,1,'Resolved-Model',None))
            self.assertEqual(rows[0][13],1250)
            self.assertIsNone(rows[1][6]); self.assertIsNone(rows[1][7]); self.assertEqual(rows[1][9],1)
            self.assertEqual((rows[2][6],rows[2][7],rows[2][9]),(3,0,1))
            import console_data
            with patch('console_data.project_rows',return_value={'rows':[],'error':None}):
                data=console_data.snapshot(state,period='all',health=False,now=time.time())
            self.assertIn('router',data['platforms'])
            group=next(g for g in data['by_platform'] if g['platform']=='router')
            self.assertEqual(group['requests'],3)
            self.assertEqual(data['summary']['actual_tokens'],123)
            self.assertEqual(data['summary']['measured_requests'],2)
            self.assertEqual(data['summary']['failed_requests'],2)
            self.assertTrue(data['series'])
            self.assertEqual(sum(day['tokens'] for day in data['series']),123)
            today=console_data.snapshot(state,period='today',health=False,now=time.time())
            day=console_data.snapshot(state,period='all',day=time.strftime('%Y-%m-%d',time.localtime()),health=False,now=time.time())
            self.assertEqual(today['summary']['requests'],3)
            self.assertEqual(day['day_total'],3)
            reuse_dir=state/'router-reuse'; reuse_dir.mkdir()
            imp.ROUTER_DB=make_router_db(reuse_dir,[
                (11,now+3000,'requested-a','Resolved-Model',200,8,1,0,1),
            ])
            imp.run()
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                reused=db.execute("SELECT id FROM turns WHERE platform='router' AND id LIKE 'imp-router-11-%' ORDER BY at").fetchall()
            self.assertEqual(reused,[(f'imp-router-11-{now}',),(f'imp-router-11-{now+3000}',)])

    def test_router_dedupe_is_one_to_one_and_removes_late_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp); now=int(time.time()*1000)
            imp.STATE=state
            imp.CLAUDE_PROJECTS=state/'missing-claude'
            imp.CODEX_SESSIONS=state/'missing-codex'
            imp.ZCODE_DB=state/'missing-zcode.db'
            imp.ROUTER_DB=make_router_db(tmp,[
                (21,now,'glm-5.3-flash',None,200,10,10,2,12),
                (22,now+1000,'GLM-5.3-FLASH',None,200,11,10,2,12),
                (23,now+2000,'DeepSeek-R1',None,200,12,7,2,9),
            ])
            imported,_=imp.run()
            self.assertEqual(imported,3)
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM turns WHERE platform='router'").fetchone()[0],3)
            # The newly visible ZCode row matches request 21. It consumes only
            # that router request; the identical small request 22 remains.
            imp.ZCODE_DB=make_zcode_db(tmp,now)
            with sqlite3.connect(imp.ZCODE_DB) as db:
                db.execute("UPDATE model_usage SET input_tokens=10,output_tokens=2,cache_read_input_tokens=0 WHERE id='u1'")
                db.execute("UPDATE model_usage SET status='running',completed_at=NULL,duration_ms=NULL WHERE id='u2'")
            imp.run()
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                routers=db.execute("SELECT id FROM turns WHERE platform='router' ORDER BY at").fetchall()
                zcode=db.execute("SELECT COUNT(*) FROM turns WHERE platform='zcode' AND model='GLM-5.3-Flash'").fetchone()[0]
                providers=dict(db.execute("SELECT model,provider_id FROM turns WHERE platform='zcode'"))
            self.assertEqual(routers,[(f'imp-router-22-{now+1000}',),(f'imp-router-23-{now+2000}',)])
            self.assertEqual(zcode,1)
            self.assertEqual(providers['GLM-5.3-Flash'],'local-model-router')
            # A later direct paid request has the same model, case and tokens
            # within the dedupe window, but is a distinct source request.
            with sqlite3.connect(imp.ZCODE_DB) as db:
                db.execute("UPDATE model_usage SET model_id='GLM-5.3-Flash',started_at=?,completed_at=?,duration_ms=6000,status='completed',input_tokens=10,output_tokens=2,cache_read_input_tokens=0,provider_id='account:zai-start-plan' WHERE id='u2'",
                           (now-4000,now+1000))
            imp.run()
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                direct=db.execute("SELECT id,provider_id FROM turns WHERE platform='zcode' AND id LIKE 'imp-zcode-%' ORDER BY id").fetchall()
                routers=db.execute("SELECT id FROM turns WHERE platform='router' ORDER BY at").fetchall()
            self.assertEqual(len(direct),2)
            self.assertIn(('imp-zcode-'+hashlib.sha1(b'zdb|u2').hexdigest()[:24],'account:zai-start-plan'),direct)
            self.assertEqual(routers,[(f'imp-router-22-{now+1000}',),(f'imp-router-23-{now+2000}',)])
            # A later full rescan may see a source row for request 23 too; the
            # router-derived row is removed and the non-router detail wins.
            with sqlite3.connect(imp.ZCODE_DB) as db:
                db.execute("UPDATE model_usage SET model_id='deepseek-r1',started_at=?,completed_at=?,duration_ms=6000,status='completed',input_tokens=7,output_tokens=2,cache_read_input_tokens=0,cache_creation_input_tokens=0,provider_id='local-model-router' WHERE id='u3'",
                           (now-4000,now+2000))
            imp.run()
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                routers=db.execute("SELECT id FROM turns WHERE platform='router' ORDER BY at").fetchall()
                zcode=db.execute("SELECT COUNT(*) FROM turns WHERE platform='zcode'").fetchone()[0]
            self.assertEqual(routers,[(f'imp-router-22-{now+1000}',)])
            self.assertEqual(zcode,3)

    def test_router_claude_connection_and_absent_usage_dedupe(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp); now=int(time.time()*1000)
            imp.STATE=state
            imp.ROUTER_DB=make_router_db(tmp,[
                (1,now,'backboard/claude-opus-5-5',None,200,10,10,2,12),
                (2,now+1000,'kiro/claude-opus-5.5',None,200,10,None,None,None),
                (3,now+2000,'kiro/claude-opus-5.5',None,200,10,None,None,None),
                (4,now+3000,'kiro/claude-opus-5.5',None,500,10,None,None,None),
                (5,now+4000,'kiro/claude-opus-5.5',None,200,10,None,None,None),
            ])
            db=imp.open_ledger()
            for row_id,at,model,provider,inputs,outputs in [
                ('client-1',now/1000+.02,'backboard/claude-opus-5-5','lmr-claude',10,2),
                ('client-2',now/1000+1.02,'kiro/claude-opus-5.5','lmr-claude',0,0),
                ('client-3',now/1000+2.02,'kiro/claude-opus-5.5','lmr-claude',0,0),
                ('direct',now/1000+4.02,'kiro/claude-opus-5.5','paid-direct',0,0),
            ]:
                db.execute('INSERT INTO turns (id,at,platform,model,provider_id,sent,exit_code,actual_input,actual_output) VALUES (?,?,?,?,?,1,0,?,?)',
                           (row_id,at,'zcode',model,provider,inputs,outputs))
            self.assertEqual(imp.import_router_rows(db),(2,3))
            self.assertEqual(db.execute("SELECT id FROM turns WHERE platform='router' ORDER BY id").fetchall(),
                             [(f'imp-router-4-{now+3000}',),(f'imp-router-5-{now+4000}',)])
            self.assertEqual(db.execute("SELECT actual_input,actual_output FROM turns WHERE id='client-2'").fetchone(),(None,None))
            self.assertEqual(imp.import_router_rows(db),(2,3))
            # A source arriving late removes the old router copy, too.
            db.execute("UPDATE turns SET provider_id='lmr-claude' WHERE id='direct'")
            self.assertEqual(imp.import_router_rows(db),(1,4))
            self.assertEqual(db.execute("SELECT COUNT(*) FROM turns WHERE platform='router'").fetchone()[0],1)
            db.close()

    def test_router_cache_reconciliation_enriches_the_client_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            imp.STATE=Path(tmp);now=int(time.time()*1000)
            imp.ROUTER_DB=make_router_db(tmp,[(1,now,'backboard/claude-opus-5-5',None,200,10,586656,281,586937)])
            with sqlite3.connect(imp.ROUTER_DB) as raw:
                for name,typ in [('cached_tokens','INTEGER'),('cache_creation_tokens','INTEGER'),('kiro_credits','REAL'),('context_usage_percent','REAL')]:
                    raw.execute('ALTER TABLE requests ADD COLUMN '+name+' '+typ)
                raw.execute('UPDATE requests SET cached_tokens=100,cache_creation_tokens=586552')
            db=imp.open_ledger()
            db.execute("INSERT INTO turns (id,at,platform,model,provider_id,sent,actual_input,actual_output,cached) VALUES ('client',?,'zcode','backboard/claude-opus-5-5','lmr-claude',1,4,281,0)",(now/1000+.02,))
            for _ in range(2):
                self.assertEqual(imp.import_router_rows(db),(0,1))
                self.assertEqual(db.execute('SELECT actual_input,actual_output,cached,cache_creation FROM turns').fetchone(),(586656,281,100,586552))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM turns').fetchone()[0],1)
            db.close()

    def test_identical_same_provider_zcode_requests_keep_distinct_stable_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp); now=int(time.time()*1000)
            imp.STATE=state
            imp.CLAUDE_PROJECTS=state/'missing-claude'; imp.CODEX_SESSIONS=state/'missing-codex'
            imp.ROUTER_DB=state/'missing-router.db'
            imp.ZCODE_DB=make_zcode_db(tmp,now)
            with sqlite3.connect(imp.ZCODE_DB) as db:
                db.execute("UPDATE model_usage SET input_tokens=1000,output_tokens=20,cache_read_input_tokens=0 WHERE id='u1'")
                db.execute("UPDATE model_usage SET status='running',completed_at=NULL,duration_ms=NULL WHERE id='u2'")
            imp.run()
            with sqlite3.connect(imp.ZCODE_DB) as db:
                db.execute("UPDATE model_usage SET model_id='GLM-5.3-Flash',started_at=?,completed_at=?,duration_ms=6000,status='completed',input_tokens=1000,output_tokens=20,cache_read_input_tokens=0,provider_id='local-model-router' WHERE id='u2'",
                           (now-4000,now+1000))
            imp.run()
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                rows=db.execute("SELECT id,provider_id,actual_input,actual_output FROM turns WHERE platform='zcode' ORDER BY id").fetchall()
            self.assertEqual(rows,[
                ('imp-zcode-'+hashlib.sha1(b'zdb|u1').hexdigest()[:24],'local-model-router',1000,20),
                ('imp-zcode-'+hashlib.sha1(b'zdb|u2').hexdigest()[:24],'local-model-router',1000,20),
            ])
            imp.run()
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM turns WHERE platform='zcode'").fetchone()[0],2)

    def test_antigravity_parser_reads_real_tokens_and_model(self):
        # Minimal stand-in for a conversation DB: transcript JSON embedded in
        # step_payload carries the real per-call tokens; gen_metadata carries
        # the model per generation via last_step_index.
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); conversations=root/'conversations'; conversations.mkdir(parents=True)
            transcript='\n'.join([
                '1: '+json.dumps({'step_index':0,'source':'USER_EXPLICIT','type':'USER_INPUT','status':'DONE','created_at':iso_now(),'content':'hi'}),
                '2: '+json.dumps({'step_index':1,'source':'MODEL','type':'PLANNER_RESPONSE','status':'DONE','created_at':iso_now(),'input_tokens':100,'cache_read_tokens':40,'cache_creation_tokens':5,'output_tokens':9,'content':'ok'}),
                '3: '+json.dumps({'step_index':2,'source':'MODEL','type':'PLANNER_RESPONSE','status':'ERROR','created_at':iso_now(),'input_tokens':999,'output_tokens':1,'content':'x'}),
            ])
            gen=sqlite3.connect(str(conversations/'conv-1.db'))
            gen.execute('CREATE TABLE gen_metadata (idx INTEGER, data BLOB, size INTEGER)')
            gen.execute('CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, has_subtrajectory numeric, metadata BLOB, error_details BLOB, permissions BLOB, task_details BLOB, render_info BLOB, step_payload BLOB, step_format INTEGER)')
            meta='last_step_index\x12\x011' + 'model_enum\x12\x16MODEL_PLACEHOLDER_M26' + 'Claude Opus 4.6 (Thinking)'
            gen.execute('INSERT INTO gen_metadata VALUES (0,?,?)',(meta.encode(),len(meta)))
            gen.execute('INSERT INTO steps (idx,step_type,status,step_payload,step_format) VALUES (7,132,1,?,0)',(transcript.encode(),))
            gen.commit(); gen.close()
            entries=list(imp.antigravity_entries(conversations/'conv-1.db'))
            self.assertEqual(len(entries),1)
            at,model,input_total,output,cached,creation,duration,key=entries[0]
            self.assertEqual(model,'claude-opus-4-6-thinking')
            self.assertEqual((input_total,output,cached,creation),(145,9,40,5))
            self.assertIsNone(duration)
            self.assertTrue(key.startswith('conv-1|1|'))
            # Antigravity stamps drop the fractional part ('...Z'); parse_iso must cope.
            self.assertIsNotNone(imp.parse_iso('2026-10-30T02:07:12Z'))

    def test_antigravity_proto_parser_reads_gen_metadata(self):
        # Newer Antigravity builds store per-generation usage in protobuf
        # gen_metadata (field 1.4) instead of transcript JSON. Build the same
        # layout the importer verified against a real conversation DB:
        # usage(1=enum,2=plain input,3=output,10=thinking), 1.9.10.1 =
        # cumulative context incl. cache read, 1.19 = model id, 1.20 =
        # key/value pairs; steps.metadata 1.1 = start epoch, 9.2 = plain input.
        def varint(value):
            out=bytearray()
            while True:
                byte=value & 0x7F; value >>= 7
                out.append(byte | (0x80 if value else 0))
                if not value: return bytes(out)
        def field_var(no, value): return varint((no << 3) | 0) + varint(value)
        def field_msg(no, payload): return varint((no << 3) | 2) + varint(len(payload)) + payload
        def field_str(no, text): return field_msg(no, text.encode())
        at=int(time.time())-60
        usage=field_var(1,1322)+field_var(2,5000)+field_var(3,100)+field_var(10,20)
        gen=(field_msg(1, field_msg(4, usage) + field_msg(9, field_msg(10, field_var(1,9000)))
                        + field_str(19,'gemini-3.8-flash-tiered')
                        + field_msg(20, field_str(1,'last_step_index')+field_str(2,'0'))
                        + field_msg(20, field_str(1,'model_enum')+field_str(2,'MODEL_PLACEHOLDER_M322'))))
        usage2=field_var(1,1322)+field_var(2,6000)+field_var(3,50)+field_var(10,10)
        gen2=(field_msg(1, field_msg(4, usage2) + field_msg(9, field_msg(10, field_var(1,12000)))
                         + field_str(19,'gemini-3.8-flash-tiered')
                         + field_msg(20, field_str(1,'last_step_index')+field_str(2,'2'))))
        step_meta=field_msg(1, field_var(1,at)+field_var(2,1)) + field_msg(9, field_var(2,5000))
        step_meta2=field_msg(1, field_var(1,at+30)+field_var(2,1)) + field_msg(9, field_var(2,6000))
        with tempfile.TemporaryDirectory() as tmp:
            conversations=Path(tmp)/'conversations'; conversations.mkdir(parents=True)
            db=sqlite3.connect(str(conversations/'conv-p.db'))
            db.execute('CREATE TABLE gen_metadata (idx INTEGER, data BLOB, size INTEGER)')
            db.execute('CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, has_subtrajectory numeric, metadata BLOB, error_details BLOB, permissions BLOB, task_details BLOB, render_info BLOB, step_payload BLOB, step_format INTEGER)')
            db.execute('INSERT INTO gen_metadata VALUES (0,?,?)',(gen,len(gen)))
            db.execute('INSERT INTO gen_metadata VALUES (1,?,?)',(gen2,len(gen2)))
            db.execute('INSERT INTO steps (idx,metadata) VALUES (1,?)',(step_meta,))
            db.execute('INSERT INTO steps (idx,metadata) VALUES (3,?)',(step_meta2,))
            db.commit(); db.close()
            entries=list(imp.antigravity_entries(conversations/'conv-p.db'))
            self.assertEqual(len(entries),2)
            first, second=entries
            # Cache read is estimated as context size (9000) - plain input
            # (5000); total input is the full context. Output adds thinking.
            self.assertEqual(first[0],float(at))
            self.assertEqual(first[1],'gemini-3.8-flash')
            self.assertEqual(first[2:6],(9000,120,4000,0))
            self.assertTrue(first[7].startswith('conv-p|p0|'))
            # Second: context 12000, plain 6000 -> read 6000, output 50+10.
            self.assertEqual(second[0],float(at+30))
            self.assertEqual(second[2:6],(12000,60,6000,0))
            self.assertTrue(second[7].startswith('conv-p|p2|'))

    def test_full_run_imports_antigravity_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); state=root/'state'; state.mkdir()
            conversations=root/'ag'/'conversations'; conversations.mkdir(parents=True)
            entry=json.dumps({'step_index':1,'source':'MODEL','type':'PLANNER_RESPONSE','status':'DONE','created_at':iso_now(),'input_tokens':50,'cache_read_tokens':10,'output_tokens':3,'content':'ok'})
            db=sqlite3.connect(str(conversations/'conv-9.db'))
            db.execute('CREATE TABLE gen_metadata (idx INTEGER, data BLOB, size INTEGER)')
            db.execute('CREATE TABLE steps (idx INTEGER, step_type INTEGER, status INTEGER, has_subtrajectory numeric, metadata BLOB, error_details BLOB, permissions BLOB, task_details BLOB, render_info BLOB, step_payload BLOB, step_format INTEGER)')
            meta='last_step_index\x12\x011' + 'gemini-3.8-flash-n'
            db.execute('INSERT INTO gen_metadata VALUES (0,?,?)',(meta.encode(),len(meta)))
            db.execute('INSERT INTO steps (idx,step_type,status,step_payload,step_format) VALUES (3,132,1,?,0)',(('2: '+entry).encode(),))
            db.commit(); db.close()
            imp.STATE=state
            imp.CLAUDE_PROJECTS=root/'missing-claude'; imp.CODEX_SESSIONS=root/'missing-codex'
            imp.ZCODE_DB=root/'missing-zcode.db'; imp.ROUTER_DB=root/'missing-router.db'
            imp.ANTIGRAVITY_ROOTS=(root/'ag',)
            self.assertEqual(imp.run(),(1,0))
            # Full rescan re-records by the same stable id: count stays 1.
            self.assertEqual(imp.run(),(1,0))
            with sqlite3.connect(state/'tokens.sqlite3') as ledger:
                rows=ledger.execute("SELECT platform,model,actual_input,actual_output,cached,cache_creation FROM turns WHERE platform='antigravity'").fetchall()
            self.assertEqual(rows,[('antigravity','gemini-3.8-flash',60,3,10,None)])

    def test_router_missing_and_invalid_schema_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp); imp.STATE=state
            imp.CLAUDE_PROJECTS=state/'missing-claude'; imp.CODEX_SESSIONS=state/'missing-codex'; imp.ZCODE_DB=state/'missing-zcode.db'
            self.assertEqual(imp.run(),(0,0))
            self.assertNotIn(imp.ZCODE_PROVIDER_BACKFILL_KEY,json.loads((state/'usage-import-state.json').read_text()))
            projects=state/'projects'; (projects/'projA').mkdir(parents=True)
            text=json.dumps({'type':'assistant','timestamp':iso_now(),'requestId':'safe','message':{'id':'safe','model':'claude-sonnet-5-5','usage':{'input_tokens':4,'output_tokens':1}}})+'\n'
            (projects/'projA'/'session.jsonl').write_text(text)
            imp.CLAUDE_PROJECTS=projects
            bad=state/'bad.db'; sqlite3.connect(bad).close(); imp.ROUTER_DB=bad
            from contextlib import redirect_stderr
            import io
            errors=io.StringIO()
            with redirect_stderr(errors):
                self.assertEqual(imp.run(),(1,0))
            self.assertIn('router database schema or query failed',errors.getvalue())
            self.assertNotIn('SELECT',errors.getvalue())
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM turns WHERE platform='claude'").fetchone()[0],1)


    def test_deepai_code_keeps_one_ledger_and_existing_price_modes(self):
        self.assertEqual(imp.codex_bill_target('DeepAI Code','openai_token_sharing'),('deepai','codex'))
        self.assertEqual(imp.codex_bill_target('DeepAI Code','openai'),('codex',None))
        self.assertEqual(imp.codex_bill_target('DeepAI Code','deepai-proxy','https://api.openai.com/v1'),('codex',None))
        self.assertEqual(imp.codex_bill_target('Codex Desktop','openai'),('codex',None))
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)
            imp.STATE=state
            imp.CLAUDE_PROJECTS=state/'missing-claude'
            imp.ZCODE_DB=state/'missing-zcode.db'
            sessions=state/'sessions'
            day=sessions/'2026'/'11'/'08'
            day.mkdir(parents=True)
            imp.CODEX_SESSIONS=sessions
            shared='\n'.join([
                json.dumps({'type':'session_meta','payload':{'originator':'DeepAI Code','model_provider':'openai_token_sharing'}}),
                json.dumps({'type':'turn_context','payload':{'model':'gpt-6.1-sol'}}),
                json.dumps({'timestamp':iso_now(),'type':'token_usage_record','payload':{'response_id':'resp_shared','usage':{'input_tokens':1000000,'cached_input_tokens':0,'output_tokens':0}}}),
            ])+'\n'
            fresh='\n'.join([
                json.dumps({'type':'session_meta','payload':{'originator':'DeepAI Code','model_provider':'openai_token_sharing'}}),
                json.dumps({'type':'turn_context','payload':{'model':'gpt-6.1-sol'}}),
                json.dumps({'timestamp':iso_now(30),'type':'token_usage_record','payload':{'response_id':'resp_fresh','usage':{'input_tokens':1000000,'cached_input_tokens':0,'output_tokens':0}}}),
            ])+'\n'
            official='\n'.join([
                json.dumps({'type':'session_meta','payload':{'originator':'DeepAI Code','model_provider':'openai'}}),
                json.dumps({'type':'turn_context','payload':{'model':'gpt-6.1-sol'}}),
                json.dumps({'timestamp':iso_now(60),'type':'token_usage_record','payload':{'response_id':'resp_openai','usage':{'input_tokens':50,'cached_input_tokens':0,'output_tokens':5}}}),
            ])+'\n'
            foreign='\n'.join([
                json.dumps({'type':'session_meta','payload':{'originator':'DeepAI Code','model_provider':'deepai-proxy','base_url':'https://api.openai.com/v1'}}),
                json.dumps({'type':'turn_context','payload':{'model':'gpt-6.1-sol'}}),
                json.dumps({'timestamp':iso_now(90),'type':'token_usage_record','payload':{'response_id':'resp_foreign','usage':{'input_tokens':20,'cached_input_tokens':0,'output_tokens':2}}}),
            ])+'\n'
            shared_path=day/'rollout-shared.jsonl'
            shared_path.write_text(shared)
            (day/'rollout-fresh.jsonl').write_text(fresh)
            (day/'rollout-openai.jsonl').write_text(official)
            (day/'rollout-foreign.jsonl').write_text(foreign)
            shared_id='imp-codex-'+hashlib.sha1(b'resp_shared').hexdigest()[:24]
            ledger=imp.open_ledger(); ledger.commit(); ledger.close()
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                db.execute('INSERT INTO turns (id,at,platform,sent,actual_input,actual_output,cached,exit_code,ready,model) VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (shared_id,time.time(),'codex',1,1000000,0,0,0,1,'gpt-6.1-sol'))
            (state/'usage-import-state.json').write_text(json.dumps({str(shared_path):shared_path.stat().st_size}))
            pi=state/'pi'; pi.mkdir()
            imp.DEEPAI_PI_ROOT=pi
            (pi/'direct.jsonl').write_text('\n'.join([
                json.dumps({'type':'message','id':'m1','timestamp':iso_now(),'message':{'role':'assistant','model':'glm-5.3-flash','responseId':'gen_1','durationMs':50,'usage':{'input':1000000,'output':0,'cacheRead':0,'cacheWrite':0}}}),
                json.dumps({'type':'message','id':'m2','timestamp':iso_now(5),'message':{'role':'assistant','model':'qwen3-14b','responseId':'gen_2','usage':{'input':100,'output':10,'cacheRead':0,'cacheWrite':0}}}),
                json.dumps({'type':'message','id':'m3','timestamp':iso_now(10),'message':{'role':'assistant','model':'mystery-model','responseId':'gen_3','usage':{'input':80,'output':8,'cacheRead':20,'cacheWrite':0}}}),
            ])+'\n')
            logs=state/'logs'; logs.mkdir()
            imp.DEEPAI_PROVIDER_LOGS=logs
            completed={'provider':'cursor','event':{'payload':{'type':'run.completed','result':{
                'id':'run-1','requestId':'req-cursor','status':'finished','durationMs':100,
                'model':{'id':'grok-4.7'},
                'usage':{'inputTokens':100,'outputTokens':10,'cacheReadTokens':40,'cacheWriteTokens':0}}}}}
            ended={'provider':'cursor','event':{'payload':{'type':'interaction.update','update':{
                'type':'turn-ended','usage':{'inputTokens':100,'outputTokens':10}}}}}
            (logs/'events.cursor.log').write_text(
                '[2026-11-08T15:20:45.157Z] NTIVE: '+json.dumps(completed)+'\n'
                '[2026-11-08T15:20:45.200Z] NTIVE: '+json.dumps(ended)+'\n')
            imp.run()
            imp.run()
            with sqlite3.connect(state/'tokens.sqlite3') as db:
                rows=db.execute('SELECT id,platform,provider_id,model,actual_input,actual_output,cached FROM turns').fetchall()
            by_id={row[0]:row[1:] for row in rows}
            self.assertEqual(by_id[shared_id],('deepai','codex','gpt-6.1-sol',1000000,0,0))
            fresh_id='imp-codex-'+hashlib.sha1(b'resp_fresh').hexdigest()[:24]
            self.assertEqual(by_id[fresh_id][0:3],('deepai','codex','gpt-6.1-sol'))
            openai_id='imp-codex-'+hashlib.sha1(b'resp_openai').hexdigest()[:24]
            foreign_id='imp-codex-'+hashlib.sha1(b'resp_foreign').hexdigest()[:24]
            self.assertEqual(by_id[openai_id][0],'codex')
            self.assertEqual(by_id[foreign_id][0],'codex')
            self.assertNotIn('cursor',{row[1] for row in rows})
            direct=[row for row in rows if row[0].startswith('imp-deepai-direct-')]
            self.assertEqual(len(direct),3)
            cursor_rows=[row for row in rows if row[0].startswith('imp-deepai-cursor-')]
            self.assertEqual(len(cursor_rows),1)
            self.assertEqual(cursor_rows[0][1:5],('deepai','cursor','grok-4.7',140))
            auto_line='[2026-11-08T15:17:35.988Z] NTIVE: '+json.dumps({
                'provider':'cursor','event':{'payload':{'type':'run.completed','result':{
                    'id':'run-auto','requestId':'req-auto','status':'finished','durationMs':1914,
                    'model':{'id':'default'},
                    'usage':{'inputTokens':13767,'outputTokens':57,'cacheReadTokens':3968,'cacheWriteTokens':0}}}}})
            self.assertEqual(imp.deepai_cursor_entries(auto_line+'\n')[0][1],'Auto')
            import prices
            self.assertEqual(prices.price_for('Auto', state_dir=state, mode='actual')['input'], 2)
            self.assertEqual(prices.price_for('default', state_dir=state, mode='official')['output'], 6)
            self.assertEqual(prices.price_for('grok-4.7', state_dir=state, mode='actual')['input'], 2)
            self.assertEqual(sum(1 for row in rows if row[0]==shared_id),1)
            import console_data
            with patch('console_data.project_rows',return_value={'rows':[],'error':None}):
                actual=console_data.snapshot(state,health=False,cost_mode='actual')
                official=console_data.snapshot(state,health=False,cost_mode='official')
            names={group['platform'] for group in actual['by_platform']}
            self.assertIn('deepai',names)
            self.assertNotIn('cursor',names)
            deepai=next(group for group in actual['by_platform'] if group['platform']=='deepai')
            codex=next(group for group in actual['by_platform'] if group['platform']=='codex')
            self.assertEqual(codex['requests'],2)
            self.assertGreaterEqual(deepai['requests'],5)
            models={(item['platform'],item['model']):item for item in actual['by_model']}
            self.assertAlmostEqual(models[('deepai','glm-5.3-flash')]['cost_actual_usd'],0.15,places=6)
            self.assertFalse(models[('deepai','glm-5.3-flash')]['free'])
            self.assertTrue(models[('deepai','qwen3-14b')]['free'])
            self.assertEqual(models[('deepai','qwen3-14b')]['cost_actual_usd'],0)
            self.assertEqual(models[('deepai','qwen3-14b')]['sources'],['direct'])
            self.assertFalse(models[('deepai','mystery-model')]['priced'])
            self.assertFalse(models[('deepai','mystery-model')]['free'])
            self.assertEqual(models[('deepai','mystery-model')]['unpriced_requests'],1)
            self.assertEqual(models[('deepai','mystery-model')]['cost_actual_usd'],0)
            self.assertIn('mystery-model',actual['unpriced_models'])
            self.assertEqual(models[('deepai','gpt-6.1-sol')]['sources'],['codex'])
            detail=console_data.snapshot(state,platform='deepai',model='gpt-6.1-sol',health=False,cost_mode='actual')
            self.assertTrue(detail['recent'])
            self.assertTrue(all(row['platform']=='deepai' and row['client_platform']=='codex' for row in detail['recent']))
            official_models={(item['platform'],item['model']):item for item in official['by_model']}
            self.assertFalse(official_models[('deepai','mystery-model')]['priced'])
            self.assertFalse(official_models[('deepai','mystery-model')]['free'])
            self.assertGreater(official_models[('deepai','glm-5.3-flash')]['cost_actual_usd'],0)


if __name__=='__main__':unittest.main()
