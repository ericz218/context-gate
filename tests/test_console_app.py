import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from console.app import make_server
from token_stats import save


class ConsoleAppTests(unittest.TestCase):
    def test_routes_token_origin_and_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            save('r1','zcode',{'baseline_tokens_estimated':100,'final_tokens_estimated':30},True,state_dir=tmp,exit_code=0)
            server=make_server(0,tmp)
            threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
            base='http://127.0.0.1:'+str(server.server_port)+'/'+server.local_token
            def get(path,headers=None):
                request=urllib.request.Request(base+path,headers=headers or {})
                return urllib.request.urlopen(request,timeout=5)
            try:
                with get('/') as r:
                    self.assertEqual(r.status,200)
                    self.assertIn('text/html',r.headers['Content-Type'])
                    self.assertIn('no-store',r.headers.get('Cache-Control',''))
                    self.assertIn('Context Gate 控制台',r.read().decode())
                with get('/v1/stats') as r:
                    data=json.load(r)
                self.assertEqual(data['summary']['requests'],1)
                # series must carry the hitrate inputs the chart toggles on
                self.assertIn('cached', data['series'][0])
                self.assertIn('input', data['series'][0])
                self.assertIn('hitrate', data['series'][0])
                with get('/v1/stats?period=week&platform=zcode') as r:
                    data=json.load(r)
                self.assertEqual(data['summary']['requests'],1)
                self.assertEqual(data['service'],'offline')
                for path,code in (('/v1/stats?period=bogus',400),('/nope',404)):
                    try:get(path);self.fail('expected '+str(code))
                    except urllib.error.HTTPError as e:self.assertEqual(e.code,code)
                bare='http://127.0.0.1:'+str(server.server_port)+'/wrong-token/'
                try:urllib.request.urlopen(bare,timeout=5);self.fail('expected 403')
                except urllib.error.HTTPError as e:self.assertEqual(e.code,403)
                try:get('/',{'Origin':'http://example.invalid'});self.fail('expected 403')
                except urllib.error.HTTPError as e:self.assertEqual(e.code,403)
            finally:
                server.shutdown();server.server_close()

    def test_stats_day_drilldown(self):
        import datetime
        import sqlite3
        from console_data import snapshot
        def ts(y,m,d):
            return datetime.datetime(y,m,d,10,0,0).timestamp()
        with tempfile.TemporaryDirectory() as tmp:
            save('d1','zcode',{'baseline_tokens_estimated':100,'final_tokens_estimated':30},True,state_dir=tmp,exit_code=0,model='m1')
            save('d2','zcode',{'baseline_tokens_estimated':50,'final_tokens_estimated':20},True,state_dir=tmp,exit_code=0,model='m1')
            save('d3','claude',{'baseline_tokens_estimated':80,'final_tokens_estimated':10},True,state_dir=tmp,exit_code=0,model='m2')
            with sqlite3.connect(Path(tmp)/'tokens.sqlite3') as c:
                c.execute('UPDATE turns SET at=? WHERE id=?',(ts(2026,1,15),'d1'))
                c.execute('UPDATE turns SET at=? WHERE id=?',(ts(2026,1,20),'d2'))
            data=snapshot(Path(tmp),day='2026-01')
            self.assertEqual(data['day_total'],2)
            self.assertEqual([r['id'] for r in data['day_recent']],['d2','d1'])
            data=snapshot(Path(tmp),day='2026-01-15')
            self.assertEqual(data['day_total'],1)
            self.assertEqual([r['id'] for r in data['day_recent']],['d1'])
            # day ignores the header period filter, like the chart does
            data=snapshot(Path(tmp),'today',day='2026-01-15')
            self.assertEqual(data['day_total'],1)
            server=make_server(0,tmp)
            threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
            base='http://127.0.0.1:'+str(server.server_port)+'/'+server.local_token
            try:
                with urllib.request.urlopen(base+'/v1/stats?day=2026-01-15',timeout=5) as r:
                    self.assertEqual(json.load(r)['day_total'],1)
                for path,code in (('/v1/stats?day=2026-13',400),('/v1/stats?day=bogus',400)):
                    try:urllib.request.urlopen(base+path,timeout=5);self.fail('expected '+str(code))
                    except urllib.error.HTTPError as e:self.assertEqual(e.code,code)
            finally:
                server.shutdown();server.server_close()

    def test_gate_task_output_route(self):
        import json as _json
        with tempfile.TemporaryDirectory() as tmp:
            gt = Path(tmp) / 'gate-tasks'
            gt.mkdir()
            out_file = Path(tmp) / 'out.md'
            out_file.write_text('# 报告内容\n验收暗号 XYZ', encoding='utf-8')
            (gt / 'abc12345-1111-1111-1111-111111111111.json').write_text(
                _json.dumps({'task_id': 'abc12345-1111-1111-1111-111111111111', 'output': str(out_file)}), encoding='utf-8')
            gone = Path(tmp) / 'gone.md'
            (gt / 'dead1111-1111-1111-1111-111111111111.json').write_text(
                _json.dumps({'task_id': 'dead1111-1111-1111-1111-111111111111', 'output': str(gone)}), encoding='utf-8')
            server = make_server(0, tmp)
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True).start()
            base = 'http://127.0.0.1:' + str(server.server_port) + '/' + server.local_token
            try:
                with urllib.request.urlopen(base + '/v1/gate-task-output?id=abc12345-1111-1111-1111-111111111111', timeout=5) as r:
                    d = _json.load(r)
                self.assertIn('验收暗号 XYZ', d['content'])
                self.assertEqual(d['file'], str(out_file))
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(base + '/v1/gate-task-output?id=dead1111-1111-1111-1111-111111111111', timeout=5)
                self.assertEqual(ctx.exception.code, 404)
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(base + '/v1/gate-task-output?id=zz', timeout=5)
                self.assertEqual(ctx.exception.code, 400)
            finally:
                server.shutdown(); server.server_close()

    def test_gate_output_and_raw_log_redact_credentials(self):
        from unittest.mock import patch
        import console.app as app
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'gate-tasks';folder.mkdir()
            tid='11111111-2222-3333-4444-555555555555'
            secret='sk-'+('syntheticvalue'*3)
            output=root/'output.md';output.write_text('result '+secret)
            (folder/(tid+'.json')).write_text(json.dumps({'output':str(output)}))
            server=make_server(0,tmp,launch_schedules=False)
            threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
            base='http://127.0.0.1:'+str(server.server_port)+'/'+server.local_token
            try:
                with urllib.request.urlopen(base+'/v1/gate-task-output?id='+tid) as response:
                    data=json.load(response)
                self.assertNotIn(secret,data['content']);self.assertIn('[REDACTED]',data['content'])
                self.assertEqual(output.read_text(),'result '+secret)
                with patch.object(app,'gate_stream_event',return_value={'raw':'token '+secret}):
                    with urllib.request.urlopen(base+'/v1/gate-task-log?id='+tid+'&i=0') as response:
                        data=json.load(response)
                    self.assertNotIn(secret,data['raw']);self.assertIn('[REDACTED]',data['raw'])
            finally:
                server.shutdown();server.server_close()

    def test_request_detail_route(self):
        import sqlite3
        from console_data import request_detail
        with tempfile.TemporaryDirectory() as tmp:
            # 两个统计差异明显的 id；一个带时序，一个只有账本行（证明不混行）。
            save('req-imp-AAAA1111','anthropic',{'baseline_tokens_estimated':1000,'final_tokens_estimated':400},
                 True,state_dir=tmp,exit_code=0,model='m-slow',
                 usage={'input_tokens':900,'output_tokens':110,'cached_input_tokens':300},
                 timing={'endpoint':'/v1/messages','prepare_ms':1.5,'upstream_headers_ms':40,
                         'first_response_byte_ms':120,'upstream_total_ms':500,'total_ms':502,
                         'upstream_status':200,'stream_completed':1})
            save('req-imp-BBBB2222','zcode',{'baseline_tokens_estimated':10,'final_tokens_estimated':5},
                 True,state_dir=tmp,exit_code=None,model='apik'+('x'*24))
            # gate 派发行：id 回退为 task_id 时，注册表是可证明的关联日志来源。
            gate_id='11111111-2222-3333-4444-555555555555'
            save(gate_id,'claude',{'baseline_tokens_estimated':500,'final_tokens_estimated':200},
                 True,state_dir=tmp,exit_code=0,model='m-gate')
            gt=Path(tmp)/'gate-tasks';gt.mkdir()
            (gt/(gate_id+'.json')).write_text(json.dumps({'task_id':gate_id,'request':'压缩这个任务','status':'done'}),encoding='utf-8')
            (gt/(gate_id+'.stream.jsonl')).write_text('{"type":"result"}\n',encoding='utf-8')
            # 精确命中：id、脱敏后模型、时序、平台别名
            d=request_detail(Path(tmp),'req-imp-AAAA1111')
            self.assertEqual(d['request']['model'],'m-slow')
            self.assertEqual(d['request']['platform'],'claude')  # anthropic 别名归并
            self.assertEqual(d['request']['status'],'success')
            self.assertEqual(d['timing']['total_ms'],502)
            self.assertEqual(d['logs'],[])
            self.assertIn('未保存',d['notice'])
            # 另一行数据不被串：带时序的查不到别人的值
            d2=request_detail(Path(tmp),'req-imp-BBBB2222')
            self.assertIsNone(d2['timing'])
            self.assertEqual(d2['request']['status'],'pending')
            self.assertEqual(d2['request']['model'],'apik'+('x'*24))
            # gate 注册表关联：只有 id 即 task_id 的行才有
            d3=request_detail(Path(tmp),gate_id)
            self.assertEqual(len(d3['logs']),1)
            self.assertIn('gate-tasks/',d3['logs'][0]['source'])
            self.assertEqual(d3['logs'][0]['request'],'压缩这个任务')
            self.assertEqual(d3['notice'],'')
            # 未知 id → KeyError；坏 id（控制字符/超长）→ ValueError
            with self.assertRaises(KeyError):request_detail(Path(tmp),'no-such-id')
            with self.assertRaises(ValueError):request_detail(Path(tmp),'bad\x01id')
            with self.assertRaises(ValueError):request_detail(Path(tmp),'x'*201)
            # 脱敏：值里的 key 形态字符串必须被打码（经 public 的 HTTP 响应）
            # 无 request_timings 表的库：timing 诚实为 None
            with tempfile.TemporaryDirectory() as tmp2:
                save('plain','zcode',{'baseline_tokens_estimated':1,'final_tokens_estimated':1},True,state_dir=tmp2,exit_code=0)
                with sqlite3.connect(Path(tmp2)/'tokens.sqlite3') as c:
                    c.execute('DROP TABLE IF EXISTS request_timings')
                self.assertIsNone(request_detail(Path(tmp2),'plain')['timing'])
            server=make_server(0,tmp)
            threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
            base='http://127.0.0.1:'+str(server.server_port)+'/'+server.local_token
            try:
                with urllib.request.urlopen(base+'/v1/request-detail?id=req-imp-BBBB2222',timeout=5) as r:
                    data=json.load(r)
                self.assertIn('[REDACTED]',data['request']['model'])
                self.assertNotIn('apik',data['request']['model'])
                with urllib.request.urlopen(base+'/v1/request-detail?id='+gate_id,timeout=5) as r:
                    data=json.load(r)
                self.assertEqual(data['logs'][0]['status'],'done')
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(base+'/v1/request-detail?id=no-such-id',timeout=5)
                self.assertEqual(ctx.exception.code,404)
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(base+'/v1/request-detail?id=',timeout=5)
                self.assertEqual(ctx.exception.code,400)
            finally:
                server.shutdown();server.server_close()

    def test_external_outcomes_and_day_scoped_snapshot(self):
        import datetime
        import sqlite3
        from console_data import external_outcomes, snapshot
        with tempfile.TemporaryDirectory() as tmp:
            # 空状态：无注册表 → 空
            self.assertEqual(external_outcomes(Path(tmp)),[])
            gt=Path(tmp)/'gate-tasks';gt.mkdir()
            out1=Path(tmp)/'out-a.txt';out1.write_text('成果A内容',encoding='utf-8')
            (gt/'11111111-aaaa-bbbb-cccc-000000000001.json').write_text(json.dumps({
                'task_id':'11111111-aaaa-bbbb-cccc-000000000001','root':'/tmp/proj-a','platform':'claude',
                'request':'整理外部成果','status':'done','output':str(out1),'started_at':200,'ended_at':300}),encoding='utf-8')
            # output 文件缺失的注册表不进列表
            (gt/'11111111-aaaa-bbbb-cccc-000000000002.json').write_text(json.dumps({
                'task_id':'11111111-aaaa-bbbb-cccc-000000000002','output':'/tmp/definitely-gone.txt'}),encoding='utf-8')
            rows=external_outcomes(Path(tmp))
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['task_id'],'11111111-aaaa-bbbb-cccc-000000000001')
            self.assertEqual(rows[0]['file'],str(out1))
            self.assertEqual(rows[0]['source'],'external')
            # day 下推：快照整体只含该日行，日界两侧互不串
            def ts(y,m,d):return datetime.datetime(y,m,d,10,0,0).timestamp()
            save('in-day','claude',{'baseline_tokens_estimated':100,'final_tokens_estimated':10},True,state_dir=tmp,exit_code=0,model='m1')
            save('out-month','claude',{'baseline_tokens_estimated':100,'final_tokens_estimated':10},True,state_dir=tmp,exit_code=0,model='m2')
            with sqlite3.connect(Path(tmp)/'tokens.sqlite3') as c:
                c.execute('UPDATE turns SET at=? WHERE id=?',(ts(2026,3,15),'in-day'))
                c.execute('UPDATE turns SET at=? WHERE id=?',(datetime.datetime(2026,4,2,10).timestamp(),'out-month'))
            data=snapshot(Path(tmp),day='2026-03-15')
            self.assertEqual(data['day_total'],1)
            self.assertEqual([r['id'] for r in data['day_recent']],['in-day'])
            # 快照其余聚合也被限定在该日：请求数=1、series 只有一天
            self.assertEqual(data['summary']['requests'],1)
            self.assertEqual([s['day'] for s in data['series']],['2026-03-15'])
            self.assertEqual(data['workbench'],None)
            month=snapshot(Path(tmp),day='2026-03')
            self.assertEqual(month['day_total'],1)
            data=snapshot(Path(tmp))
            self.assertEqual(data['summary']['requests'],2)  # 无 day 参数时不受影响
            server=make_server(0,tmp)
            threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
            base='http://127.0.0.1:'+str(server.server_port)+'/'+server.local_token
            try:
                with urllib.request.urlopen(base+'/v1/center/tasks',timeout=5) as r:
                    data=json.load(r)
                self.assertEqual(len(data['external_outcomes']),1)
                self.assertEqual(data['external_outcomes'][0]['goal'],'整理外部成果')
                with urllib.request.urlopen(base+'/v1/stats?day=2026-03-15',timeout=5) as r:
                    self.assertEqual(json.load(r)['day_total'],1)
            finally:
                server.shutdown();server.server_close()

    def test_gate_stream_new_codex_format_and_request_cap(self):
        # Newer Codex CLI writes thread/turn/item lifecycle events; the old
        # parser only knew assistant/user/result, so those tasks showed
        # "no per-turn records" and the details looked lost.
        from console_data import _stream_events, gate_tasks
        with tempfile.TemporaryDirectory() as tmp:
            gt=Path(tmp)/'gate-tasks';gt.mkdir()
            tid='11111111-aaaa-bbbb-cccc-000000000003'
            stream=gt/(tid+'.stream.jsonl')
            events=[
                {'type':'thread.started','thread_id':'t1'},
                {'type':'turn.started'},
                {'type':'item.completed','item':{'id':'i0','type':'error','message':'不稳定功能警告'}},
                {'type':'item.completed','item':{'id':'i1','type':'agent_message','text':'先核对当前状态再动手'}},
                {'type':'item.completed','item':{'id':'i2','type':'command_execution','command':'/bin/zsh -lc "pwd"'}},
                {'type':'item.completed','item':{'id':'i3','type':'file_change','changes':[{'path':'/p/a.cs','kind':'update'}],'status':'completed'}},
                {'type':'item.completed','item':{'id':'i4','type':'reasoning','text':'内部推理不该出现'}},
                {'type':'error','message':'上游 400'},
                {'type':'turn.failed','error':{'message':'上游 400'}},
                {'type':'assistant','message':{'content':[{'type':'text','text':'旧格式轮'}]}},
                {'type':'user','message':{'content':[{'type':'tool_result','content':'旧格式结果'}]}},
                {'type':'result','result':'旧格式完成'},
            ]
            stream.write_text('\n'.join(json.dumps(e,ensure_ascii=False) for e in events)+'\n',encoding='utf-8')
            rows=_stream_events(stream)
            kinds=[r['k'] for r in rows]
            self.assertIn('错误',kinds);self.assertIn('失败',kinds);self.assertIn('AI',kinds)
            self.assertIn('结果',kinds);self.assertIn('完成',kinds)
            self.assertFalse(any('内部推理' in r['s'] for r in rows))
            self.assertEqual(len([r for r in rows if '先核对当前状态' in r['s']]),1)
            self.assertEqual(len([r for r in rows if 'pwd' in r['s']]),1)
            self.assertEqual(len([r for r in rows if '/p/a.cs' in r['s']]),1)
            # registry keeps up to 100K; the stats payload caps at 20K
            (gt/(tid+'.json')).write_text(json.dumps({
                'task_id':tid,'root':'/tmp/p','platform':'codex',
                'request':'细'*25000,'status':'done','started_at':1}),encoding='utf-8')
            tasks=gate_tasks(Path(tmp))
            self.assertEqual(len(tasks),1)
            self.assertEqual(len(tasks[0]['request']),20000)

    def test_persistent_token_keeps_pages_alive_across_restarts(self):
        import os
        from console.app import apply_persistent_token
        with tempfile.TemporaryDirectory() as tmp:
            s1=make_server(0,tmp)
            apply_persistent_token(s1,tmp,True)
            token1=s1.local_token
            mode=oct(os.stat(Path(tmp)/'console-token').st_mode & 0o777)
            self.assertEqual(mode,'0o600')
            s1.server_close()
            s2=make_server(0,tmp)  # 模拟重启后的新进程
            apply_persistent_token(s2,tmp,True)
            self.assertEqual(s2.local_token,token1)  # 旧页签的 URL 依然有效
            s2.server_close()
            s3=make_server(0,tmp)
            apply_persistent_token(s3,tmp,False)  # 随机端口实例不持久化、不沿用
            self.assertNotEqual(s3.local_token,token1)
            s3.server_close()
            self.assertTrue((Path(tmp)/'console-token').exists())  # 固定端口实例写的文件仍在

    def test_post_routes_hotkey_openapp_and_origin(self):
        import os
        import console.app as cap
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(0, tmp)
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True).start()
            base = 'http://127.0.0.1:' + str(server.server_port) + '/' + server.local_token
            def post(path, payload, headers=None):
                request = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                                 headers={'Content-Type': 'application/json', **(headers or {})}, method='POST')
                return urllib.request.urlopen(request, timeout=5)
            try:
                # 有效快捷键：写入 state 目录，权限 0600
                with post('/v1/settings/hotkey', {'key': 'J', 'ctrl': True, 'cmd': True}) as r:
                    data = json.load(r)
                self.assertTrue(data['ok'])
                hotkey_path = Path(tmp) / 'hotkey.json'
                self.assertEqual(json.loads(hotkey_path.read_text())['key'], 'J')
                self.assertEqual(oct(os.stat(hotkey_path).st_mode & 0o777), '0o600')
                # 裸字母（无 ⌃/⌘）与非法键被拒
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post('/v1/settings/hotkey', {'key': 'J', 'ctrl': False, 'cmd': False})
                self.assertEqual(ctx.exception.code, 400)
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post('/v1/settings/hotkey', {'key': 'F5', 'cmd': True})
                self.assertEqual(ctx.exception.code, 400)
                # 外站 Origin 一律 403
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post('/v1/settings/hotkey', {'key': 'K', 'ctrl': True, 'cmd': True},
                         {'Origin': 'http://evil.example'})
                self.assertEqual(ctx.exception.code, 403)
                # open-app：白名单外 400；白名单内走注入的桩，不真开 App
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    post('/v1/open-app', {'app': 'Finder'})
                self.assertEqual(ctx.exception.code, 400)
                called = []
                original = cap.run_open
                cap.run_open = lambda command: called.append(command) or True
                try:
                    with post('/v1/open-app', {'app': 'claude'}) as r:
                        self.assertTrue(json.load(r)['ok'])
                finally:
                    cap.run_open = original
                self.assertEqual(called, [['/usr/bin/open', '-a', 'Claude']])
            finally:
                server.shutdown(); server.server_close()


if __name__=='__main__':unittest.main()
