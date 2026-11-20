import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from control_center import Center
from group_chat import Groups, worker, run_codex, run_claude, run_zcode


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'project';self.root.mkdir()
        self.state=Path(self.temp.name)/'state';self.state.mkdir()
        self.g=Groups(self.state,Center(self.state,[self.root]),launch=False)
        self.gid=self.g.create({'root':str(self.root),'name':'test'})['id']
        self.a=self.g.add({'group':self.gid,'slug':'alpha','platform':'codex','model':'gpt-6-sol'})['id']
        self.b=self.g.add({'group':self.gid,'slug':'beta','platform':'claude','model':'sonnet'})['id']

    def test_deleted_selected_group_still_returns_available_groups(self):
        data=self.g.snapshot('00000000-0000-0000-0000-000000000000')
        self.assertTrue(data['missing_group'])
        self.assertIn(self.gid,[g['id'] for g in data['groups']])
        self.assertNotIn('members',data)

    def test_effort_tiers_per_platform(self):
        c1=self.g.add({'group':self.gid,'slug':'g1','platform':'claude','model':'sonnet','effort':'xhigh'})['id']
        c2=self.g.add({'group':self.gid,'slug':'g2','platform':'codex','model':'gpt-6-sol','effort':'max'})['id']
        with self.g.connect() as db:
            self.assertEqual(self.g.member(db,self.gid,c1)['effort'],'xhigh')
            self.assertEqual(self.g.member(db,self.gid,c2)['effort'],'max')
        with self.assertRaises(ValueError):self.g.add({'group':self.gid,'slug':'g3','platform':'claude','model':'sonnet','effort':'fast'})
        self.g.model({'group':self.gid,'member':self.a,'model':'gpt-6-sol','effort':'ultra'})
        with self.g.connect() as db:self.assertEqual(self.g.member(db,self.gid,self.a)['effort'],'ultra')
        for model in ('gpt-6-luna','gpt-5.6-luna','gpt-5.5'):
            with self.assertRaises(ValueError):self.g.model({'group':self.gid,'member':self.a,'model':model,'effort':'ultra'})
        for i,model in enumerate(('gpt-6.1-sol','gpt-6-astra','gpt-5.6-sol','gpt-5.6-terra')):
            self.g.add({'group':self.gid,'slug':'u'+str(i),'platform':'codex','model':model,'effort':'ultra'})
        self.g.model({'group':self.gid,'member':self.b,'model':'sonnet','effort':'ultracode'})
        with self.assertRaises(ValueError):self.g.model({'group':self.gid,'member':self.b,'model':'haiku','effort':'ultracode'})
        self.g.add({'group':self.gid,'slug':'native','platform':'claude','model':'haiku'})
        snap=self.g.snapshot(self.gid)
        self.assertEqual(snap['members'][-1]['effort'],'native')
        self.assertEqual(snap['efforts']['claude']['haiku'],('native',))
        self.assertIn('ultra',snap['efforts']['codex']['gpt-6.1-sol'])

    def test_mod_role_switch_keeps_session_and_validates_override(self):
        from group_chat import mod_instructions
        with self.g.connect() as db:db.execute("UPDATE members SET session='old-session' WHERE id=?",(self.a,))
        self.g.mod({'group':self.gid,'member':self.a,'role':'决策'})
        m=self.g.snapshot(self.gid)['members'][0]
        self.assertEqual((m['model'],m['effort'],m['session'],m['auto_handoff']),('gpt-6-astra','high','old-session',1))
        self.assertIn('Architect',mod_instructions(m))
        self.g.mod({'group':self.gid,'member':self.a,'role':'执行','model':'gpt-6.1-sol','effort':'max'})
        m=self.g.snapshot(self.gid)['members'][0]
        self.assertEqual((m['model'],m['effort'],m['session']),('gpt-6.1-sol','max','old-session'))
        self.assertIn('Implementer',mod_instructions(m))
        self.g.mod({'group':self.gid,'member':self.b,'role':'执行'})
        self.assertEqual(self.g.snapshot(self.gid)['members'][1]['model'],'sonnet')
        with self.assertRaises(ValueError):self.g.mod({'group':self.gid,'member':self.a,'role':'执行','model':'gpt-6-luna','effort':'ultra'})
        self.g.mod({'group':self.gid,'member':self.a,'role':'关闭'})
        m=self.g.snapshot(self.gid)['members'][0]
        self.assertEqual(m['auto_handoff'],0);self.assertEqual(mod_instructions(m),'')

    def test_mod_handoff_stopped_and_invalid_summary_preserve_session(self):
        self.g.mod({'group':self.gid,'member':self.a,'role':'执行'})
        self.g.send({'group':self.gid,'text':'@alpha task'})
        job=self.jobs()[0]
        with self.g.connect() as db:
            db.execute("UPDATE members SET session='old' WHERE id=?",(self.a,))
            m=self.g.member(db,self.gid,self.a)
        for summary in ('','x'*32001):
            with self.assertRaises(RuntimeError):self.g.handoff(m,job,summary)
        with self.g.connect() as db:db.execute('UPDATE jobs SET stop=1 WHERE id=?',(job['id'],))
        self.assertFalse(self.g.handoff(m,job,'未完成任务'))
        self.assertEqual(self.g.snapshot(self.gid)['members'][0]['session'],'old')
        self.assertEqual(len(self.jobs()),1)

    def test_claude_mod_compaction_resumes_for_summary_and_hands_off(self):
        import io
        from unittest.mock import Mock
        self.g.mod({'group':self.gid,'member':self.b,'role':'决策'})
        self.g.send({'group':self.gid,'text':'@beta task'})
        job=self.jobs()[0];m=self.g.snapshot(self.gid)['members'][1];m['root']=str(self.root)
        init={'type':'system','subtype':'init','session_id':'claude-old'}
        compact={'type':'system','subtype':'compact_boundary','session_id':'claude-old','compact_metadata':{}}
        end={'type':'result','subtype':'success','result':'交接：已完成A，未完成B，约束C'}
        def proc(events,code):
            p=Mock(stdin=io.StringIO(),stdout=io.StringIO('\n'.join(json.dumps(e) for e in events)+'\n'))
            p.wait.return_value=code;p.poll.return_value=code;return p
        with patch('group_chat.subprocess.Popen',side_effect=[proc([init,compact],-15),proc([init,end],0)]) as popen,patch('group_chat.os.killpg'):
            status,summary=run_claude(self.g,m,job,lambda:False)
        self.assertEqual(status,'handed_off');self.assertIn('未完成B',summary)
        argv=popen.call_args_list[1].args[0]
        self.assertIn('--resume',argv);self.assertIn('claude-old',argv)
        self.assertEqual(argv[argv.index('--permission-mode')+1],'plan')
        self.assertIn('Architect',argv[argv.index('--append-system-prompt')+1])
        after=self.g.snapshot(self.gid)['members'][1]
        self.assertEqual((after['platform'],after['model'],after['effort'],after['session']),('claude','sonnet','high',None))
        self.assertEqual(len(self.jobs()),2)

    def test_zcode_mod_compaction_stream_and_native_handoff(self):
        import io
        from unittest.mock import Mock
        mid=self.g.add({'group':self.gid,'slug':'zcmod','platform':'zcode','model':'zcode','effort':'native'})['id']
        self.g.mod({'group':self.gid,'member':mid,'role':'执行'})
        self.g.send({'group':self.gid,'text':'@zcmod task'})
        job=self.jobs()[0];m=self.g.snapshot(self.gid)['members'][-1];m['root']=str(self.root)
        stream=[{'type':'session.created','sessionId':'sess_old'}, {'type':'turn.started','sessionId':'sess_old','turnId':'t1'},
                {'type':'session.updated','sessionId':'sess_old','turnId':'t1','payload':{'status':'completed','boundaryId':'b1','summaryMessageId':'s1'}}]
        def proc(events):
            p=Mock(stdout=io.StringIO('\n'.join(json.dumps(e) for e in events)+'\n'),stderr=io.StringIO(''))
            p.poll.return_value=0;p.wait.return_value=0;p.returncode=0;return p
        def gate(*args,**kwargs):
            self.assertIn('Implementer',Path(args[2]).read_text())
            return ['zcode'],{},None
        with patch('group_chat.gate_command',side_effect=gate),patch('group_chat.subprocess.Popen',side_effect=[proc(stream),proc([{'sessionId':'sess_old','response':'交接正文：完成A，下一步B'}])]) as popen:
            status,summary=run_zcode(self.g,m,job,lambda:False)
        self.assertEqual(status,'handed_off');self.assertIn('下一步B',summary)
        self.assertIn('--output-format',popen.call_args_list[0].args[0])
        self.assertIn('--resume',popen.call_args_list[1].args[0])
        after=self.g.snapshot(self.gid)['members'][-1]
        self.assertEqual((after['platform'],after['model'],after['effort'],after['session']),('zcode','zcode','native',None))
        self.assertEqual(len(self.jobs()),2)

    def test_mod_native_compaction_handoff_is_once_and_same_platform(self):
        self.g.mod({'group':self.gid,'member':self.a,'role':'执行'})
        self.g.send({'group':self.gid,'text':'@alpha finish project'})
        job=self.jobs()[0];m=self.g.snapshot(self.gid)['members'][0];m['root']=str(self.root)
        calls=[]
        class Native:
            def __init__(self,root,event,config):self.event=event;self.turn=0
            def call(self,method,params):
                calls.append((method,params))
                if method=='thread/start':return {'thread':{'id':'old-session','path':None}}
                if method=='turn/interrupt':return {}
                if method=='turn/start':
                    self.turn+=1;tid='turn'+str(self.turn)
                    self.event({'method':'thread/compacted','params':{'threadId':'unrelated','turnId':tid}})
                    self.event({'method':'item/completed','params':{'threadId':'old-session','turnId':tid,'item':{'type':'contextCompaction'}}})
                    if self.turn==2:self.event({'method':'item/completed','params':{'threadId':'old-session','turnId':tid,'item':{'type':'agentMessage','text':'目标：finish project。已完成A，测试通过。下一步B，禁止重做A。'}}})
                    self.event({'method':'turn/completed','params':{'threadId':'old-session','turn':{'id':tid,'status':'interrupted' if self.turn==1 else 'completed'}}})
                    return {'turn':{'id':tid}}
            def close(self):pass
        with patch('group_chat.Codex',Native):status,summary=run_codex(self.g,m,job,lambda:False)
        self.assertEqual(status,'handed_off')
        after=self.g.snapshot(self.gid)['members'][0]
        self.assertEqual((after['platform'],after['model'],after['effort'],after['session']),('codex','gpt-6.1-sol','high',None))
        queued=self.jobs()[-1]
        self.assertIn(summary,queued['text']);self.assertIn('禁止重复',queued['text'])
        self.assertEqual(len([x for x in calls if x[0]=='turn/interrupt']),1)
        self.assertEqual(len([x for x in calls if x[0]=='turn/start']),2)
        self.assertFalse(self.g.handoff({**m,'session':None},job,summary))
        self.assertEqual(len(self.jobs()),2)

    def test_zcode_member_roundtrip_session_and_validation(self):
        import io
        from unittest.mock import Mock
        mz=self.g.add({'group':self.gid,'slug':'zc','platform':'zcode','model':'zcode','effort':'native'})['id']
        with self.assertRaises(ValueError):
            self.g.add({'group':self.gid,'slug':'zc2','platform':'zcode','model':'sonnet','effort':'native'})
        with self.assertRaises(ValueError):
            self.g.add({'group':self.gid,'slug':'zc3','platform':'zcode','model':'zcode','effort':'high'})
        m=self.g.snapshot(self.gid)['members'][-1];m.update(root=str(self.root))
        fake=json.dumps({'sessionId':'sess_z1','response':'第一轮回复','usage':{'inputTokens':10,'outputTokens':2}},indent=2)
        proc=Mock(stdout=io.StringIO(fake),stderr=io.StringIO(''));proc.wait.return_value=0;proc.poll.return_value=0
        captured={}
        def fake_gate(platform,root,prompt_path,model=None,proxy_factory=None,zcode_mode='plan',request=None,**kw):
            captured['request']=request;captured['mode']=zcode_mode
            return (['fake-zcode','--json'],'env',None)
        with patch('group_chat.gate_command',side_effect=fake_gate),patch('group_chat.subprocess.Popen',return_value=proc):
            status,final=run_zcode(self.g,m,{'text':'@zc 第一轮','depth':0},lambda:False)
        self.assertEqual(('done','第一轮回复'),(status,final))
        self.assertEqual(captured['mode'],'plan')
        self.assertIn('第一轮',captured['request'])
        with self.g.connect() as db:
            self.assertEqual(self.g.member(db,self.gid,mz)['session'],'sess_z1')
        # 第二轮：会话接续（--resume sess_z1）
        m['session']='sess_z1'
        fake2=json.dumps({'sessionId':'sess_z1','response':'第二轮回复','usage':{'inputTokens':20,'outputTokens':4}},indent=2)
        proc2=Mock(stdout=io.StringIO(fake2),stderr=io.StringIO(''));proc2.wait.return_value=0;proc2.poll.return_value=0
        with patch('group_chat.gate_command',side_effect=fake_gate),patch('group_chat.subprocess.Popen',return_value=proc2) as popen_mock:
            status,final=run_zcode(self.g,m,{'text':'@zc 第二轮','depth':0},lambda:False)
        argv_used=popen_mock.call_args[0][0]
        self.assertIn('--resume',argv_used);self.assertIn('sess_z1',argv_used)
        self.assertEqual(('done','第二轮回复'),(status,final))
        with self.g.connect() as db:
            self.assertEqual(self.g.member(db,self.gid,mz)['session'],'sess_z1')

    def test_zcode_native_history_and_workspace_open(self):
        mz=self.g.add({'group':self.gid,'slug':'zh','platform':'zcode','model':'zcode','effort':'native'})['id']
        sess='sess_3f3f3f3f-1111-2222-3333-444444444444'
        roll=Path(__file__).resolve().parents[1]/'work'/'zcode-headless-data'/'storage'/'cli'/'rollout'
        roll.mkdir(parents=True,exist_ok=True)
        target=roll/('model-io-'+sess+'.jsonl')
        target.write_text(json.dumps({'completedAt':'2026-10-04T12:00:00Z','response':{'finishReason':'stop','text':'第一轮答复'},'sessionId':sess})+'\n'
                          +json.dumps({'completedAt':'2026-10-04T12:01:00Z','response':{'finishReason':'tool-calls'},'sessionId':sess})+'\n',encoding='utf-8')
        try:
            with self.g.connect() as db:
                db.execute('UPDATE members SET session=? WHERE id=?',(sess,mz))
            h=self.g.native_history(self.gid,mz,0)
            self.assertIn('隔离库',h['source'])
            texts=[x['text'] for x in h['messages']]
            self.assertTrue(any('第一轮答复' in t for t in texts))
            self.assertTrue(any('工具调用' in t for t in texts))
            self.assertEqual(h['total'],2)
        finally:
            target.unlink(missing_ok=True)
        h3=self.g.native_history(self.gid,mz,0)
        self.assertIn('未留存',h3['source'])
        with patch('group_chat.subprocess.run') as run_mock:
            run_mock.return_value.returncode=0
            d=self.g.open_native({'group':self.gid,'member':mz})
            self.assertTrue(d['opened'])
            self.assertIn('zcode://workspace/open?path=',run_mock.call_args[0][0][1])

    def test_worker_archives_completed_failed_and_stopped_changes(self):
        for status in ('done','failed','stopped'):
            with self.subTest(status=status):
                file=self.root/'result.txt';file.write_text('before')
                (self.root/'deleted.txt').write_text('delete me')
                self.g.send({'group':self.gid,'text':'@alpha '+status})
                def native(*args):
                    file.write_text(status+' <script>literal</script>')
                    (self.root/'deleted.txt').unlink()
                    (self.root/'.env').write_text('excluded')
                    if status=='failed':raise RuntimeError('native failed')
                    return status,'result'
                with patch('group_chat.run_codex',side_effect=native):worker(self.state,self.a)
                job=self.jobs()[-1];self.assertEqual(status,job['status'])
                outcome=json.loads(job['outcome']);self.assertEqual(['result.txt'],[x['path'] for x in outcome['artifacts']])
                self.assertEqual(['deleted.txt','result.txt'],[x['path'] for x in outcome['changes']])
                self.assertEqual(status+' <script>literal</script>',self.g.artifact(job['id'],'result.txt')['content'])
                archive=self.g.folder/'outcomes'/job['id']/'artifacts'/'result.txt'
                self.assertEqual(0o600,archive.stat().st_mode&0o777)
                file.write_text('later');self.assertTrue(self.g.artifact(job['id'],'result.txt')['content'].startswith(status))
                archive.write_text('tampered')
                with self.assertRaisesRegex(ValueError,'已变化'):self.g.artifact(job['id'],'result.txt')
        self.g.stop({'group':self.gid,'members':[self.a]},remove=True)
        self.assertEqual(3,len(self.g.outcomes()))
        with self.assertRaisesRegex(ValueError,'未登记'):self.g.artifact(job['id'],'../secret')

    def test_archive_failure_preserves_native_result_and_reports_warning(self):
        self.g.send({'group':self.gid,'text':'@alpha check'})
        from control_center import manifest
        def scan(root,backup=None):
            if backup is None:raise OSError('scan failed')
            return manifest(root,backup)
        with patch('group_chat.manifest',side_effect=scan),patch('group_chat.run_codex',return_value=('done','ok')):worker(self.state,self.a)
        job=self.jobs()[0];self.assertEqual('done',job['status'])
        self.assertEqual('scan failed',json.loads(job['outcome'])['archive_error'])
        self.assertTrue(any('成果归档失败' in x['text'] for x in self.g.snapshot(self.gid)['messages']))

    def test_compare_group_and_center_snapshots_with_source_validation(self):
        from control_center import manifest,write_json
        selections=[]
        for text in ('first','second'):
            self.g.send({'group':self.gid,'text':'@alpha '+text})
            before=manifest(self.root);(self.root/'result.txt').write_text(text)
            job=self.jobs()[-1];m=self.g.snapshot(self.gid)['members'][0];m['root']=str(self.root)
            self.g.archive(m,job,before)
            selections.append({'source':'group','task':job['id'],'path':'result.txt'})
        result=self.g.center.compare({'left':selections[0],'right':selections[1]},self.g)
        self.assertFalse(result['equal']);self.assertEqual('first',result['left']['content'])
        self.assertEqual('group',result['left']['source'])
        task=self.g.center.create({'root':str(self.root),'platform':'claude','goal':'fixture'},launch=False)
        folder=self.g.center.path(task['task_id']).parent/'artifacts';folder.mkdir()
        file=folder/'result.txt';file.write_text('second')
        import hashlib
        task['artifacts']=[{'path':'result.txt','sha256':hashlib.sha256(file.read_bytes()).hexdigest()}]
        write_json(self.g.center.path(task['task_id']),task)
        center={'task':task['task_id'],'path':'result.txt'}
        self.assertTrue(self.g.center.compare({'left':center,'right':selections[1]},self.g)['equal'])
        with self.assertRaisesRegex(ValueError,'来源无效'):self.g.center.compare({'left':{**center,'source':'unknown'},'right':selections[0]},self.g)
        with self.assertRaisesRegex(ValueError,'未登记'):self.g.center.compare({'left':{**selections[0],'path':'../secret'},'right':center},self.g)
        other=self.root.parent/'other';other.mkdir();self.g.center.roots.append(other.resolve())
        with self.g.connect() as db:db.execute('UPDATE groups SET root=? WHERE id=?',(str(other),self.gid))
        with self.assertRaisesRegex(ValueError,'同一项目'):self.g.center.compare({'left':center,'right':selections[1]},self.g)
        with self.g.connect() as db:db.execute('UPDATE groups SET root=? WHERE id=?',(str(self.root),self.gid))
        (self.g.folder/'outcomes'/selections[0]['task']/'artifacts'/'result.txt').write_text('tampered')
        with self.assertRaisesRegex(ValueError,'已变化'):self.g.center.compare({'left':selections[0],'right':center},self.g)

    def jobs(self):
        with self.g.connect() as db:return [dict(x) for x in db.execute('SELECT * FROM jobs')]

    def test_send_retry_persists_one_job_even_after_member_removed(self):
        body={'group':self.gid,'text':'@alpha check','request_id':'retry-request-0001'}
        first=self.g.send(body);self.g.stop({'group':self.gid,'members':[self.a]},remove=True)
        restored=Groups(self.state,self.g.center,launch=False)
        replay=restored.send(body)
        self.assertTrue(replay['replayed']);self.assertEqual(first['jobs'],replay['jobs'])
        self.assertEqual(1,len(self.jobs()))
        with self.assertRaisesRegex(ValueError,'不同消息'):restored.send({**body,'text':'@alpha different'})
        with self.assertRaisesRegex(ValueError,'编号无效'):restored.send({**body,'request_id':123})
        self.assertEqual(1,len(self.jobs()))

    def test_concurrent_identical_send_claims_once_and_starts_once(self):
        from concurrent.futures import ThreadPoolExecutor
        self.g.launch=True
        body={'group':self.gid,'text':'@alpha check','request_id':'concurrent-request-01'}
        with patch.object(self.g,'start_worker') as start:
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(self.g.send,[body,body]))
            start.assert_called_once_with(self.a)
        self.assertEqual(1,len(self.jobs()))
        self.assertEqual([False,True],sorted(x['replayed'] for x in results))
        self.assertEqual(results[0]['jobs'],results[1]['jobs'])

    def test_send_request_scoped_to_group_and_source(self):
        key='scoped-request-0001'
        body={'group':self.gid,'text':'@beta check','request_id':key}
        self.g.send(body)
        self.g.send(body,source=self.a,depth=1)
        self.assertEqual(2,len(self.jobs()))
        other=self.g.create({'root':str(self.root),'name':'other'})['id']
        self.g.add({'group':other,'slug':'beta','platform':'claude','model':'sonnet'})
        self.g.send({**body,'group':other})
        self.assertEqual(3,len(self.jobs()))
        with self.assertRaisesRegex(ValueError,'此群组'):self.g.send(body,source='unknown-source')

    def test_codex_group_usage_absolute_snapshots_ignore_duplicates_and_other_turns(self):
        self.g.send({'group':self.gid,'text':'@alpha check'})
        job=self.jobs()[0];m=self.g.snapshot(self.gid)['members'][0]
        m.update(root=str(self.root),session='session1',effort='ultra')
        class Native:
            def __init__(self,root,event,config):self.event=event
            def call(self,method,params):
                if method=='thread/resume':return {'thread':{'id':'session1'}}
                if method=='turn/start':
                    assert params['effort']=='ultra'
                    for tid,inputs in [('other',999),('turn1',100),('turn1',100),('turn1',90)]:
                        self.event({'method':'thread/tokenUsage/updated','params':{'threadId':'session1','turnId':tid,'tokenUsage':{'total':{'inputTokens':inputs,'outputTokens':5,'cachedInputTokens':80},'last':{'inputTokens':20,'outputTokens':1}}}})
                    self.event({'method':'turn/completed','params':{'turn':{'id':'turn1','status':'completed'}}})
                    return {'turn':{'id':'turn1'}}
            def close(self):pass
        with patch('group_chat.Codex',Native):run_codex(self.g,m,job,lambda:False)
        usage=self.g.snapshot(self.gid)['members'][0]['usage']
        self.assertEqual(105,usage['total_tokens']);self.assertEqual('native_thread_total',usage['scope']);self.assertTrue(usage['final'])

    def test_claude_group_usage_dedup_and_final_override(self):
        import io
        from unittest.mock import Mock
        self.g.send({'group':self.gid,'text':'@beta check'})
        job=self.jobs()[0];m=self.g.snapshot(self.gid)['members'][1];m.update(root=str(self.root),effort='ultracode')
        part={'type':'assistant','message':{'id':'m1','content':[],'usage':{'input_tokens':1,'output_tokens':2,'cache_read_input_tokens':10}}}
        result={'type':'result','result':'ok','usage':{'input_tokens':3,'output_tokens':4,'cache_read_input_tokens':10},'total_cost_usd':0.001}
        proc=Mock(stdin=io.StringIO(),stdout=io.StringIO('\n'.join(json.dumps(x) for x in [part,part,result])+'\n'))
        proc.wait.return_value=0
        with patch('group_chat.subprocess.Popen',return_value=proc) as popen:
            run_claude(self.g,m,job,lambda:False)
            argv=popen.call_args.args[0]
            self.assertEqual(argv[argv.index('--effort')+1],'ultracode')
            self.assertEqual(json.loads(argv[argv.index('--settings')+1]),{'ultracode':True})
        usage=self.g.snapshot(self.gid)['members'][1]['usage']
        self.assertEqual(17,usage['total_tokens']);self.assertEqual(0.001,usage['reported_usd']);self.assertTrue(usage['final'])
        self.g.send({'group':self.gid,'text':'@beta next'})
        self.assertIsNone(self.g.snapshot(self.gid)['members'][1]['usage'])

    def test_claude_zero_exit_without_result_and_error_subtype_are_not_complete(self):
        import io
        from unittest.mock import Mock
        m=self.g.snapshot(self.gid)['members'][1];m['root']=str(self.root)
        for event in [{'type':'assistant','message':{'content':[{'type':'text','text':'partial'}]}},
                      {'type':'result','subtype':'error_max_turns','result':'limit'}]:
            proc=Mock(stdin=io.StringIO(),stdout=io.StringIO(json.dumps(event)+'\n'))
            proc.wait.return_value=0;proc.poll.return_value=0
            with self.subTest(event=event['type']),patch('group_chat.subprocess.Popen',return_value=proc):
                with self.assertRaises(RuntimeError):run_claude(self.g,m,{'text':'check','depth':0},lambda:False)

    def test_claude_result_only_keeps_full_detail_and_short_main_brief(self):
        import io
        from unittest.mock import Mock
        self.g.send({'group':self.gid,'text':'@beta check'})
        result='full result '+('x'*700)
        proc=Mock(stdin=io.StringIO(),stdout=io.StringIO(json.dumps({'type':'result','subtype':'success','result':result})+'\n'))
        proc.wait.return_value=0;proc.poll.return_value=0
        with patch('group_chat.subprocess.Popen',return_value=proc):worker(self.state,self.b)
        messages=self.g.snapshot(self.gid)['messages']
        self.assertTrue(any(m['channel']=='detail' and m['text']==result for m in messages))
        brief=next(m['text'] for m in messages if m['channel']=='main' and m['text'].startswith('完成了'))
        self.assertLess(len(brief),len(result));self.assertIn('完整结果见成员聊天',brief)

    def test_codex_ignores_other_turn_items_and_unknown_completion_is_not_done(self):
        m=self.g.snapshot(self.gid)['members'][0];m.update(root=str(self.root),session='session1')
        class Native:
            status='completed'
            def __init__(self,root,event,config):self.event=event
            def call(self,method,params):
                if method=='thread/resume':return {'thread':{'id':'session1'}}
                if method=='turn/start':
                    for sid,tid,text in [('other','turn1','wrong thread'),('session1','other','wrong turn'),('session1','turn1','correct')]:
                        self.event({'method':'item/completed','params':{'threadId':sid,'turnId':tid,'item':{'type':'agentMessage','text':text}}})
                    self.event({'method':'turn/completed','params':{'turn':{'id':'turn1','status':self.status}}})
                    return {'turn':{'id':'turn1'}}
            def close(self):pass
        with patch('group_chat.Codex',Native):
            self.assertEqual(('done','correct'),run_codex(self.g,m,{'text':'check','depth':0},lambda:False))
            Native.status=None
            with self.assertRaisesRegex(RuntimeError,'明确完成状态'):run_codex(self.g,m,{'text':'check','depth':0},lambda:False)
        details=[x['text'] for x in self.g.snapshot(self.gid)['messages'] if x['channel']=='detail']
        self.assertNotIn('wrong thread',details);self.assertNotIn('wrong turn',details)

    def test_mention_broadcast_and_unknown(self):
        self.g.send({'group':self.gid,'text':'@beta check'})
        self.assertEqual([self.b],[x['member'] for x in self.jobs()])
        self.g.send({'group':self.gid,'text':'all check'})
        self.assertEqual(3,len(self.jobs()))
        with self.assertRaises(ValueError):self.g.send({'group':self.gid,'text':'@stranger'})
        self.assertEqual(3,len(self.jobs()))

    def test_stop_requires_selection_and_delete_keeps_history(self):
        self.g.send({'group':self.gid,'text':'hello'})
        with self.assertRaises(ValueError):self.g.stop({'group':self.gid,'members':[]})
        self.g.stop({'group':self.gid,'members':[self.a]},remove=True)
        self.assertEqual('stopped',self.jobs()[0]['status'])
        self.assertTrue(any(m['member']==self.a for m in self.g.snapshot(self.gid)['messages']))
        with self.assertRaises(ValueError):self.g.send({'group':self.gid,'text':'@alpha new'})

    def test_model_preserves_session_and_platform(self):
        with self.g.connect() as db:db.execute('UPDATE members SET session=? WHERE id=?',('native-1',self.a))
        result=self.g.model({'group':self.gid,'member':self.a,'model':'gpt-6-luna','effort':'low'})
        self.assertEqual('native-1',result['session'])
        with self.assertRaises(ValueError):self.g.model({'group':self.gid,'member':self.a,'model':'sonnet','effort':'low'})

    def test_queued_model_refreshes_after_backup_and_keeps_native_session(self):
        from control_center import manifest
        with self.g.connect() as db:db.execute('UPDATE members SET session=? WHERE id=?',('same-native',self.a))
        self.g.send({'group':self.gid,'text':'@alpha check'})
        def backup(root,dest=None):
            result=manifest(root,dest)
            if dest is not None:self.g.model({'group':self.gid,'member':self.a,'model':'gpt-6-luna','effort':'low'})
            return result
        with patch('group_chat.manifest',side_effect=backup),patch('group_chat.run_codex',return_value=('done','ok')) as native:
            worker(self.state,self.a)
        member=native.call_args.args[1]
        self.assertEqual(('gpt-6-luna','low','same-native'),(member['model'],member['effort'],member['session']))

    def test_remove_during_backup_prevents_native_launch(self):
        from control_center import manifest
        self.g.send({'group':self.gid,'text':'@alpha check'})
        def backup(root,dest=None):
            result=manifest(root,dest)
            if dest is not None:self.g.stop({'group':self.gid,'members':[self.a]},remove=True)
            return result
        with patch('group_chat.manifest',side_effect=backup),patch('group_chat.run_codex') as native:
            worker(self.state,self.a)
        native.assert_not_called();self.assertEqual('stopped',self.jobs()[0]['status'])

    def test_other_group_atomicity_and_coordination_budget(self):
        other=self.g.create({'root':str(self.root),'name':'other'})['id']
        with self.assertRaises(ValueError):self.g.stop({'group':other,'members':[self.a]})
        with self.assertRaises(ValueError):self.g.send({'group':self.gid,'text':'@beta work'},source=self.a,depth=5)
        self.assertFalse(self.jobs())

    def test_history_pagination(self):
        with self.g.connect() as db:
            for n in range(205):self.g.message(db,self.gid,self.a,'tool',str(n))
        first=self.g.snapshot(self.gid)
        self.assertEqual(200,len(first['messages']));self.assertTrue(first['has_more'])
        second=self.g.snapshot(self.gid,after=first['cursor'])
        self.assertFalse(second['has_more'])
        self.assertGreater(second['messages'][0]['id'],first['cursor'])

    def test_worker_failure_not_complete_and_backup(self):
        (self.root/'example.txt').write_text('original')
        self.g.send({'group':self.gid,'text':'@alpha check'})
        # Worker reuses the authorized project stored by the application.
        with patch('group_chat.run_codex',side_effect=RuntimeError('usage limit')):
            worker(self.state,self.a)
        self.assertEqual('failed',self.jobs()[0]['status'])
        messages=self.g.snapshot(self.gid)['messages']
        self.assertTrue(any(m['role']=='error' and 'usage limit' in m['text'] for m in messages))
        self.assertFalse(any(m['text'].startswith('完成了') for m in messages))
        self.assertEqual('original',(self.g.folder/'backups'/self.jobs()[0]['id']/'example.txt').read_text())

    def test_interrupted_process_not_replayed(self):
        self.g.send({'group':self.gid,'text':'@alpha work'})
        with self.g.connect() as db:
            db.execute("UPDATE jobs SET status='running'")
            db.execute("UPDATE members SET status='running' WHERE id=?",(self.a,))
        snap=self.g.snapshot(self.gid)
        self.assertEqual('interrupted',self.jobs()[0]['status'])
        self.assertTrue(any('未自动重派' in m['text'] for m in snap['messages']))

    def test_native_history_path_is_confined(self):
        with self.g.connect() as db:
            db.execute('UPDATE members SET session=?,native_path=? WHERE id=?',('native','/etc/passwd',self.a))
        with self.assertRaises(ValueError):self.g.native_history(self.gid,self.a)

    def test_native_history_pagination_and_unreadable_records_are_visible(self):
        home=Path(self.temp.name)/'home';path=home/'.codex/history.jsonl';path.parent.mkdir(parents=True)
        records=['not-json','[]',json.dumps({'payload':[]})]
        records.extend(json.dumps({'type':'response_item','payload':{'type':'message','role':'assistant','content':[{'type':'output_text','text':str(i)}]}}) for i in range(205))
        path.write_text('\n'.join(records)+'\n')
        with self.g.connect() as db:db.execute('UPDATE members SET session=?,native_path=? WHERE id=?',('native',str(path),self.a))
        with patch('group_chat.Path.home',return_value=home):
            first=self.g.native_history(self.gid,self.a);last=self.g.native_history(self.gid,self.a,200)
        self.assertEqual(205,first['total']);self.assertEqual(200,first['next_offset'])
        self.assertEqual(3,first['unreadable_records']);self.assertIn('无法解析',first['source'])
        self.assertEqual('204',last['messages'][-1]['text']);self.assertIsNone(last['next_offset'])

    def test_native_history_rejects_oversize_record_and_page_without_truncation(self):
        home=Path(self.temp.name)/'home';path=home/'.codex/history.jsonl';path.parent.mkdir(parents=True)
        with self.g.connect() as db:db.execute('UPDATE members SET session=?,native_path=? WHERE id=?',('native',str(path),self.a))
        path.write_text('x'*2_000_001)
        with patch('group_chat.Path.home',return_value=home):
            with self.assertRaisesRegex(ValueError,'单条.*未截断'):self.g.native_history(self.gid,self.a)
        record=json.dumps({'type':'response_item','payload':{'type':'message','role':'assistant','content':[{'type':'output_text','text':'x'*700000}]}})
        path.write_text((record+'\n')*3)
        with patch('group_chat.Path.home',return_value=home):
            with self.assertRaisesRegex(ValueError,'本页.*未截断'):self.g.native_history(self.gid,self.a)

    def test_stop_queued_member_returns_idle(self):
        self.g.send({'group':self.gid,'text':'@alpha work'})
        self.g.stop({'group':self.gid,'members':[self.a]})
        with self.g.connect() as db:
            self.assertEqual('idle',db.execute('SELECT status FROM members WHERE id=?',(self.a,)).fetchone()[0])

    def test_recover_queued_only_when_worker_lock_is_free(self):
        import fcntl
        self.g.send({'group':self.gid,'text':'@alpha queued'})
        self.g.launch=True
        with patch.object(self.g,'start_worker') as start:
            with (self.g.folder/(self.a+'.lock')).open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                self.g.recover()
                start.assert_not_called()
            self.g.recover()
            start.assert_called_once_with(self.a)
        self.assertEqual('queued',self.jobs()[0]['status'])

    def test_removed_native_history_remains_readable_but_cannot_send(self):
        self.g.stop({'group':self.gid,'members':[self.a]},remove=True)
        self.assertEqual([],self.g.native_history(self.gid,self.a)['messages'])
        with self.assertRaises(ValueError):self.g.send({'group':self.gid,'text':'hello','members':[self.a]})

    def test_nontext_message_rejected_without_jobs(self):
        with self.assertRaises(ValueError):self.g.send({'group':self.gid,'text':{'command':'invalid'}})
        self.assertFalse(self.jobs())

    def test_native_stop_waits_for_turn_started_and_keeps_session(self):
        m=self.g.snapshot(self.gid)['members'][0]
        m.update(root=str(self.root),session='original-session')
        calls=[]
        class Native:
            def __init__(self,root,event,config):self.event=event
            def call(self,method,params):
                calls.append((method,params))
                if method=='thread/resume':return {'thread':{'id':'original-session'}}
                if method=='turn/start':
                    self.event({'method':'turn/started','params':{'turn':{'id':'turn1'}}})
                    return {'turn':{'id':'turn1'}}
                if method=='turn/interrupt':
                    self.event({'method':'turn/completed','params':{'turn':{'id':'turn1','status':'interrupted'}}})
                    return {}
            def close(self):pass
        with patch('group_chat.Codex',Native):
            status,_=run_codex(self.g,m,{'text':'@alpha stop','depth':0},lambda:True)
        self.assertEqual('stopped',status)
        self.assertEqual(['thread/resume','turn/start','turn/interrupt'],[x[0] for x in calls])
        self.assertEqual('original-session',calls[-1][1]['threadId'])
        self.assertEqual('stop',calls[1][1]['input'][0]['text'])

    def test_mcp_history_exposes_only_member_group_and_identity(self):
        import subprocess
        import sys
        other=self.g.create({'root':str(self.root),'name':'private-other-group'})['id']
        request={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'group_history','arguments':{}}}
        process=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'group_chat.py'),'mcp','--state',str(self.state),'--member',self.a],input=json.dumps(request)+'\n',capture_output=True,text=True,timeout=10)
        response=json.loads(process.stdout)['result']['content'][0]['text']
        result=json.loads(response)
        self.assertEqual(self.gid,result['group']['id'])
        self.assertEqual({'id':self.a,'slug':'alpha'},result['self'])
        self.assertNotIn(other,response)


if __name__=='__main__':unittest.main()
