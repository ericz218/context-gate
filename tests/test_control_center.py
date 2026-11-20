import json
import os
import pwd
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from control_center import Center, digest, ensure_user_env, failure_category, write_json
from console_butler import Butler


class CenterTests(unittest.TestCase):
    def test_failure_category_classifies_from_evidence_only(self):
        self.assertIsNone(failure_category({'status':'pending_review','error':''}))
        self.assertIsNone(failure_category({'status':'pending_review','error':None}))
        self.assertEqual(failure_category({'status':'running','error':''}),'仍在执行，暂无失败事实')
        self.assertEqual(failure_category({'status':'validation_failed','error':''}),'验证未通过（项目检查失败），执行本身已完成')
        self.assertEqual(failure_category({'status':'stopped','error':'SIGTERM'}),'已被手动停止')
        self.assertEqual(failure_category({'status':'failed','error':'The model is not supported when using this account'}),'当前登录不支持所选模型')
        self.assertEqual(failure_category({'status':'failed','error':'HTTP 401 Unauthorized'}),'登录/凭据被拒')
        self.assertEqual(failure_category({'status':'failed','error':'usage limit reached for this account'}),'额度或限流')
        self.assertEqual(failure_category({'status':'failed','error':'connection refused to upstream'}),'网络或本地服务连接')
        self.assertEqual(failure_category({'status':'failed','error':'奇怪的新错误'}),'执行报错（见错误原文）')
        self.assertEqual(failure_category({'status':'failed','error':''}),'进程退出非零，无错误原文')
        self.assertIsNone(failure_category(None))

    def test_rollback_real_worker_flow_conflict_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'project';root.mkdir();state=base/'state';binary=base/'bin';binary.mkdir()
            fake=binary/'codex'
            fake.write_text('#!/usr/bin/env python3\nimport sys,json\nfrom pathlib import Path\na=sys.argv\nPath(a[a.index("-o")+1]).write_text("done")\nPath("report.txt").write_text("task output")\nprint(json.dumps({"type":"thread.started","thread_id":"rb-1"}))\n')
            fake.chmod(0o700)
            center=Center(state,roots=[root])
            def wait(tid):
                for _ in range(100):
                    task=center.get(tid)
                    if task['status'] not in ('starting','running'):return task
                    time.sleep(.1)
                self.fail('worker did not finish')
            with patch.dict(os.environ,{'PATH':str(binary)+os.pathsep+os.environ['PATH']}):
                task=center.create({'root':str(root),'goal':'Write report','platform':'codex'})
                done=wait(task['task_id'])
            self.assertEqual(done['status'],'pending_review')
            self.assertTrue(any(c['path']=='report.txt' for c in done['changes']))
            # 任务结束后其他会话并发修改同一文件：撤回必须拒绝且不动文件
            (root/'report.txt').write_text('concurrent edit after task')
            diffs=center.changes(task['task_id'])
            self.assertTrue(diffs['changes'][0]['conflict'])
            with self.assertRaises(ValueError):center.rollback(task['task_id'])
            self.assertEqual((root/'report.txt').read_text(),'concurrent edit after task')
            self.assertNotIn('rolled_back',done)
            # 恢复到任务结束态：撤回成功；before 无此文件 → 撤回=删除；残留快照在 rollback-backup
            (root/'report.txt').write_text('task output')
            rolled=center.rollback(task['task_id'])
            self.assertIn('rolled_back',rolled)
            self.assertFalse((root/'report.txt').exists())
            rescue=Path(done['log_file']).parent/'rollback-backup'/'report.txt'
            self.assertTrue(rescue.exists())
            # 撤回后再次撤回被拒（幂等保护）
            with self.assertRaises(ValueError):center.rollback(task['task_id'])
            # 备份损坏（before 备份摘要不匹配）→ 拒绝撤回
            file=root/'note.txt';file.write_text('before content')
            task2=center.create({'root':str(root),'goal':'Second','platform':'codex'},launch=False)
            bundle2=center.path(task2['task_id']).parent;(bundle2/'before').mkdir();(bundle2/'before'/'note.txt').write_text('TAMPERED')
            file.write_text('after content')
            task2.update(status='failed',changes=[{'path':'note.txt','before':'deadbeef','after':digest(file)}])
            write_json(center.path(task2['task_id']),task2)
            with self.assertRaises(ValueError):center.rollback(task2['task_id'])
            self.assertEqual(file.read_text(),'after content')

    def test_archive_preview_images_text_pages_hash_and_limits(self):
        import base64
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();c=Center(Path(tmp)/'state',[root])
            task=c.create({'root':str(root),'platform':'claude','goal':'archive'},launch=False)
            tid=task['task_id'];folder=c.path(tid).parent/'artifacts';folder.mkdir()
            def register(raw):
                path=folder/'result';path.write_bytes(raw)
                task['artifacts']=[{'path':'result','sha256':digest(path)}];write_json(c.path(tid),task)
            register(('hello\n'+'x'*33000).encode())
            a=c.artifact(tid,'result');b=c.artifact(tid,'result',a['next_offset'])
            self.assertEqual(33006,a['total']);self.assertEqual(33006,len(a['content'])+len(b['content']));self.assertIsNone(b['next_offset'])
            with self.assertRaises(ValueError):c.artifact(tid,'result',a['total']+1)
            register(b'\x89PNG\r\n\x1a\nfixture')
            image=c.artifact(tid,'result');self.assertEqual('image',image['kind'])
            self.assertEqual((folder/'result').read_bytes(),base64.b64decode(image['data_url'].split(',')[1]))
            (folder/'result').write_bytes(b'tamper')
            with self.assertRaisesRegex(ValueError,'变化'):c.artifact(tid,'result')
            register(b'\x89PNG\r\n\x1a\n'+b'x'*2_000_000)
            with self.assertRaisesRegex(ValueError,'2MB'):c.artifact(tid,'result')
            register(b'x'*8_000_001)
            with self.assertRaisesRegex(ValueError,'8MB.*未截断'):c.artifact(tid,'result')
            register(b'\x00')
            with self.assertRaisesRegex(ValueError,'不是文字'):c.artifact(tid,'result')

    def test_native_usage_partial_dedup_final_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();c=Center(Path(tmp)/'state',[root])
            task=c.create({'root':str(root),'platform':'claude','goal':'usage'},launch=False)
            log=c.path(task['task_id']).parent/'events.jsonl'
            assistant={'type':'assistant','message':{'id':'m1','usage':{'input_tokens':10,'output_tokens':2,'cache_read_input_tokens':100,'cache_creation_input_tokens':20}}}
            log.write_text(json.dumps(assistant)+'\n'+json.dumps(assistant)+'\n')
            u=c.usage(task);self.assertEqual(132,u['total_tokens']);self.assertFalse(u['final'])
            with log.open('a') as f:f.write(json.dumps({'type':'result','usage':{'input_tokens':30,'output_tokens':4,'cache_read_input_tokens':100,'cache_creation_input_tokens':20},'total_cost_usd':0.01})+'\n')
            u=c.usage(task);self.assertEqual(154,u['total_tokens']);self.assertTrue(u['final']);self.assertEqual(0.01,u['reported_usd'])
            task['platform']='codex'
            log.write_text(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'cached_input_tokens':90,'output_tokens':5}})+'\n')
            u=c.usage(task);self.assertEqual('native_thread_total',u['scope']);self.assertEqual(105,u['total_tokens']);self.assertEqual(90,u['cached_input_tokens']);self.assertIsNone(u['reported_usd'])
            log.write_text('not json\n"string event"\n')
            self.assertIsNone(c.usage(task))
            log.write_text(json.dumps({'type':'turn.completed','usage':{'input_tokens':-1,'output_tokens':True}})+'\n')
            self.assertIsNone(c.usage(task))

    def test_usage_alert_settings_persist_and_validate(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=Center(tmp);self.assertEqual(100000,c.usage_settings()['threshold'])
            settings={'enabled':False,'threshold':1234};c.usage_settings(settings)
            self.assertEqual(settings,Center(tmp).usage_settings())
            for invalid in (True,0,1.1,'1000'):
                with self.assertRaises(ValueError):c.usage_settings({'enabled':True,'threshold':invalid})

    def test_compare_verified_archives_and_reject_invalid_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();center=Center(Path(tmp)/'state',[root])
            selections=[]
            for text in ('first report','second report'):
                task=center.create({'root':str(root),'platform':'claude','goal':'compare'},launch=False)
                folder=center.path(task['task_id']).parent/'artifacts';folder.mkdir()
                file=folder/'report.txt';file.write_text(text)
                task['status']='pending_review'
                task['artifacts']=[{'path':'report.txt','sha256':digest(file)}]
                write_json(center.path(task['task_id']),task)
                selections.append({'task':task['task_id'],'path':'report.txt'})
            body={'left':selections[0],'right':selections[1]}
            result=center.compare(body)
            self.assertEqual('first report',result['left']['content']);self.assertFalse(result['equal'])
            self.assertTrue(center.compare({'left':selections[0],'right':selections[0]})['equal'])
            file.write_text('tampered')
            with self.assertRaisesRegex(ValueError,'已变化'):center.compare(body)
            file.write_text('x'*128001)
            task['artifacts'][0]['sha256']=digest(file);write_json(center.path(task['task_id']),task)
            with self.assertRaisesRegex(ValueError,'128KB'):center.compare(body)
            file.write_bytes(b'\x00')
            task['artifacts'][0]['sha256']=digest(file);write_json(center.path(task['task_id']),task)
            with self.assertRaisesRegex(ValueError,'不是文字'):center.compare(body)
            file.write_bytes(b'\x89PNG\r\n\x1a\nimage-data')
            task['artifacts'][0]['sha256']=digest(file);write_json(center.path(task['task_id']),task)
            result=center.compare(body)
            self.assertEqual('image',result['right']['kind'])
            self.assertTrue(result['right']['data_url'].startswith('data:image/png;base64,'))
            with self.assertRaisesRegex(ValueError,'未登记'):center.compare({'left':{'task':task['task_id'],'path':'../task.json'},'right':selections[0]})

    def test_paths_backup_conflicts_and_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();state=Path(tmp)/'state'
            center=Center(state,roots=[root]);file=root/'report.txt';file.write_text('before')
            with self.assertRaises(ValueError):center.file(str(root),'../outside')
            with self.assertRaises(ValueError):center.file(str(root),'.env')
            out=center.write(str(root),'report.txt','after',digest(file))
            self.assertTrue((state/'file-backups'/out['backup_id']/'original').exists())
            with self.assertRaises(ValueError):center.write(str(root),'report.txt','lost','bad-digest')
            task=center.create({'root':str(root),'goal':'Review report','platform':'codex'},launch=False)
            bundle=center.path(task['task_id']).parent;(bundle/'before').mkdir();(bundle/'before'/'report.txt').write_text('before')
            task.update(status='pending_review',changes=[{'path':'report.txt','before':digest(bundle/'before'/'report.txt'),'after':digest(file)}])
            write_json(center.path(task['task_id']),task)
            file.write_text('later edit')
            with self.assertRaises(ValueError):center.rollback(task['task_id'])
            self.assertEqual(file.read_text(),'later edit')
            file.write_text('after');center.rollback(task['task_id']);self.assertEqual(file.read_text(),'before')

    def test_detached_execution_resume_and_failed_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);root=base/'project';root.mkdir();state=base/'state';binary=base/'bin';binary.mkdir()
            fake=binary/'codex'
            fake.write_text('#!/usr/bin/env python3\nimport sys,json\nfrom pathlib import Path\na=sys.argv\nPath(a[a.index("-o")+1]).write_text("verified result")\nprint(json.dumps({"type":"thread.started","thread_id":"test-session"}))\nPath("result.txt").write_text("result")\n')
            fake.chmod(0o700)
            center=Center(state,roots=[root])
            def wait(tid):
                for _ in range(100):
                    task=center.get(tid)
                    if task['status'] not in ('starting','running'):return task
                    time.sleep(.1)
                self.fail('worker did not finish')
            with patch.dict(os.environ,{'PATH':str(binary)+os.pathsep+os.environ['PATH']}):
                task=center.create({'root':str(root),'goal':'Produce result','platform':'codex'})
                done=wait(task['task_id']);self.assertEqual(done['status'],'pending_review')
                self.assertEqual(done['session_id'],'test-session');self.assertEqual(done['final'],'verified result')
                self.assertEqual(done['reasoning'],'medium')
                artifact=center.artifact(task['task_id'],'result.txt')
                self.assertEqual(artifact['content'],'result')
                with self.assertRaises(ValueError):center.artifact(task['task_id'],'../../outside')
                events=[json.loads(line) for line in (state/'operations.jsonl').read_text().splitlines()]
                self.assertTrue(any(e['operation']=='task_finished' and e['session_id']=='test-session' and e['platform']=='gpt' for e in events))
                self.assertTrue(done['artifacts']);self.assertEqual(center.accept(task['task_id'])['status'],'accepted')
                follow=center.create({'root':str(root),'goal':'Continue','platform':'codex','parent':task['task_id'],'checks':['tests']})
                failed=wait(follow['task_id']);self.assertEqual(failed['status'],'validation_failed')
                with self.assertRaises(ValueError):center.accept(follow['task_id'])
                fake.write_text('#!/usr/bin/env python3\nimport json\nprint(json.dumps({"type":"turn.failed","error":{"message":"model not supported"}}))\n')
                broken=center.create({'root':str(root),'goal':'Check provider failure','platform':'codex'})
                error=wait(broken['task_id']);self.assertEqual(error['exit_code'],0)
                self.assertEqual(error['status'],'failed')
                with self.assertRaises(ValueError):center.accept(broken['task_id'])

    def test_reasoning_tiers_and_add_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();state=Path(tmp)/'state'
            center=Center(state,roots=[root])
            self.assertEqual(center.validate_request({'root':str(root),'goal':'g','platform':'claude','reasoning':'xhigh'})['reasoning'],'xhigh')
            self.assertEqual(center.validate_request({'root':str(root),'goal':'g','platform':'claude','reasoning':'max'})['reasoning'],'max')
            self.assertEqual(center.validate_request({'root':str(root),'goal':'g','platform':'codex','reasoning':'light'})['reasoning'],'low')
            self.assertEqual(center.validate_request({'root':str(root),'goal':'g','platform':'codex','reasoning':'mid'})['reasoning'],'medium')
            with self.assertRaises(ValueError):center.validate_request({'root':str(root),'goal':'g','platform':'claude','reasoning':'fast'})
            self.assertEqual(center.validate_request({'root':str(root),'goal':'g','platform':'zcode','reasoning':'fast'})['reasoning'],'unavailable (native interface)')
            from control_center import claude_effort_args
            for platform,model,effort in [('codex','gpt-6.1-sol','ultra'),('codex','gpt-5.6-terra','ultra'),('claude','opus','ultracode'),('claude','fable','ultracode'),('claude','haiku','native')]:
                self.assertEqual(center.validate_request({'root':str(root),'goal':'g','platform':platform,'model':model,'reasoning':effort})['reasoning'],effort)
            for platform,model,effort in [('codex','gpt-6-luna','ultra'),('codex','gpt-5.5','max'),('claude','sonnet','ultra'),('claude','haiku','ultracode'),('codex','sonnet','medium')]:
                with self.assertRaises(ValueError):center.validate_request({'root':str(root),'goal':'g','platform':platform,'model':model,'reasoning':effort})
            self.assertNotIn('--effort',claude_effort_args('native'))
            self.assertEqual(json.loads(claude_effort_args('high')[1]),{'ultracode':False})
            other=Path(tmp)/'other';other.mkdir()
            # 测试目录在 /var/folders 下，把"家目录"指过去再验添加逻辑
            with patch('pathlib.Path.home',return_value=Path(tmp)):
                self.assertTrue(center.add_root({'path':str(other)})['added'])
            self.assertIn(other.resolve(),center.roots)
            with patch('pathlib.Path.home',return_value=Path(tmp)):
                self.assertFalse(center.add_root({'path':str(other)})['added'])
                with self.assertRaises(ValueError):center.add_root({'path':'/Volumes'})
            self.assertTrue((state/'projects.json').exists())
            self.assertIn(other.resolve(),Center(state).roots)  # 重启后仍授权
            with self.assertRaises(ValueError):center.add_root({'path':str(Path(tmp)/'missing')})

    def test_pick_root_uses_system_dialog_then_add_root_checks(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();picked=Path(tmp)/'picked';picked.mkdir()
            center=Center(Path(tmp)/'state',roots=[root])
            run=lambda code,out='',err='':patch('control_center.subprocess.run',return_value=Mock(returncode=code,stdout=out,stderr=err))
            with patch('pathlib.Path.home',return_value=Path(tmp)):
                with run(0,str(picked)+'/\n'):data=center.pick_root({})
                self.assertTrue(data['added']);self.assertEqual(data['path'],str(picked.resolve()))
                self.assertIn(picked.resolve(),center.roots)
                with run(1,err='execution error: User canceled. (-128)'):self.assertTrue(center.pick_root({})['cancelled'])
                with run(1,err='boom'),self.assertRaises(ValueError):center.pick_root({})
                with run(0,'/Volumes/\n'),self.assertRaises(ValueError):center.pick_root({})

    def test_zcode_multiline_events_parsed(self):
        from control_center import Center, json_objects
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();state=Path(tmp)/'state'
            center=Center(state,roots=[root]);tid='e8e8e8e8-1111-2222-3333-444444444444'
            bundle=state/'center-tasks'/tid;bundle.mkdir(parents=True)
            data={'task_id':tid,'platform':'zcode','started_at':time.time()}
            write_json(bundle/'task.json',data)
            # zcode 事件是多行 JSON 对象（非一行一条）
            (bundle/'events.jsonl').write_text(json.dumps({
                'sessionId':'sess_x','response':'这是最终答复','usage':{
                    'source':'provider','inputTokens':52920,'outputTokens':188,
                    'cacheReadTokens':0,'cacheWriteTokens':0}},indent=2),encoding='utf-8')
            objs=list(json_objects((bundle/'events.jsonl').read_text()))
            self.assertEqual(len(objs),1)
            self.assertEqual(objs[0]['response'],'这是最终答复')
            usage=center.usage({'task_id':tid,'platform':'zcode'})
            self.assertEqual(usage['input_tokens'],52920)
            self.assertEqual(usage['output_tokens'],188)
            self.assertTrue(usage['final'])
            self.assertEqual(usage['scope'],'task')

    def test_local_butler_model_selected_from_ollama_tags(self):
        from console_butler import local_model_name
        self.assertEqual(local_model_name(tags=[{'name':'qwen2.5-coder:14b'},{'name':'llama3:8b'}]),'qwen2.5-coder:14b')
        self.assertEqual(local_model_name(tags=[{'name':'qwen2.5:7b'},{'name':'Qwen2.5-Coder-14B-Instruct'}]).lower(),'qwen2.5-coder-14b-instruct')
        self.assertEqual(local_model_name(tags=[{'name':'llama3:8b'}]),'llama3:8b')
        self.assertIsNone(local_model_name(tags=[]))

    def test_agent_tools_are_real_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'project';root.mkdir();state=Path(tmp)/'state';(root/'note.txt').write_text('original')
            center=Center(state,roots=[root]);responses=[]
            def model(messages):
                if len(messages)==1:return json.dumps({'tool':'read_file','args':{'path':'note.txt'}})
                result=json.loads(messages[-1]['content'].split(': ',1)[1])
                if len(messages)==3:
                    args={'path':'note.txt','content':'changed','expected_sha256':result['sha256']};responses.append(args)
                    return json.dumps({'tool':'write_file','args':args})
                return json.dumps({'reply':'文件已修改，摘要已核对。'})
            butler=Butler(state,center,model,model_name='qwen-test');task=butler.start(str(root),'Change note.txt to changed')
            for _ in range(50):
                value=butler.get(task['id'])
                if value['status']!='running':break
                time.sleep(.05)
            self.assertEqual(value['status'],'done');self.assertEqual((root/'note.txt').read_text(),'changed')
            before=len(list((state/'file-backups').iterdir()))
            butler.execute(task['id'],'write_file',responses[0])
            self.assertEqual(len(list((state/'file-backups').iterdir())),before)
            self.assertEqual(len(butler.get(task['id'])['actions']),2)
            self.assertEqual(value['actions'][0]['model'],'qwen-test')
            self.assertEqual(value['platform'],'local')
            self.assertIn('reasoning',value['actions'][0])

    def test_ensure_user_env_fills_missing_user_and_logname(self):
        name=pwd.getpwuid(os.getuid()).pw_name
        env=ensure_user_env({})
        self.assertEqual(env['USER'],name);self.assertEqual(env['LOGNAME'],name)

    def test_ensure_user_env_never_overwrites_existing_values(self):
        self.assertEqual(ensure_user_env({'USER':'alice'}),{'USER':'alice','LOGNAME':'alice'})
        self.assertEqual(ensure_user_env({'USER':'alice','LOGNAME':'bob'}),{'USER':'alice','LOGNAME':'bob'})

    def test_ensure_user_env_leaves_env_untouched_when_pwd_lookup_fails(self):
        with patch('control_center.pwd.getpwuid',side_effect=KeyError):
            env=ensure_user_env({})
        self.assertEqual(env,{})

    def test_import_control_center_fixes_stripped_environment(self):
        name=pwd.getpwuid(os.getuid()).pw_name
        repo=Path(__file__).resolve().parent.parent
        r=subprocess.run([sys.executable,'-c','import os,control_center;print(os.environ["USER"],os.environ["LOGNAME"])'],
                         cwd=str(repo),env={'PATH':'/usr/bin:/bin','HOME':os.environ['HOME']},capture_output=True,text=True,timeout=60)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.split(),[name,name])
