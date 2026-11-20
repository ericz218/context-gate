import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from console_memory import MemoryLibrary
from console.app import PAGE, make_server


def sample():
    return {'schema_version':2,'generated_at':'2026-10-06T20:00:00+00:00','total':1,'hidden':0,
            'groups':[{'id':'g1','title':'中文主题','path':'','entries':[{'id':'e1','title':'中文记忆','value':'完整事实',
             'reading_text':'完整事实','key':'test','kind':'当前信息','version':1,'recorded_at':'','quotes':[],
             'raw':'{"value":"原始事实"}'}]}]}


class HumanDocsDirTests(unittest.TestCase):
    def test_default_follows_moved_folder_and_env_override(self):
        import console_memory
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            with patch.object(console_memory.Path,'home',return_value=home), patch.dict(console_memory.os.environ,{},clear=False):
                console_memory.os.environ.pop('MEMORY_OS_HUMAN_DIR',None)
                console_memory.os.environ.pop('MEMORY_OS_DIR',None)
                private = home/'Library/Application Support/MemoryOS/ReaderDocuments'
                self.assertEqual(console_memory.human_docs_dir(), private)
                (home/'Documents/AI记忆-人话版').mkdir(parents=True)
                self.assertEqual(console_memory.human_docs_dir(), home/'Documents/AI记忆-人话版')
                private.mkdir(parents=True, mode=0o700)
                self.assertEqual(console_memory.human_docs_dir(), private)
                self.assertEqual(MemoryLibrary(root=private.parent).out, private)
                console_memory.os.environ['MEMORY_OS_HUMAN_DIR']=str(home/'elsewhere')
                self.assertEqual(console_memory.human_docs_dir(),home/'elsewhere')


class MemoryLibraryTests(unittest.TestCase):
    def test_access_check_reads_catalog_without_parsing_and_reports_permission_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib = MemoryLibrary(out=tmp, root=tmp)
            self.assertEqual(lib.access_status(), 'missing')
            (Path(tmp)/'catalog.json').write_text('the access check does not parse this')
            self.assertEqual(lib.access_status(), 'readable')
            with patch.object(Path, 'open', side_effect=PermissionError):
                self.assertEqual(lib.access_status(), 'denied')
                self.assertEqual(lib.snapshot()['error_code'], 'permission_denied')

    def test_release_requires_token_denied_access_and_idle_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = make_server(0, tmp, launch_schedules=False)
            server.memory = MemoryLibrary(out=tmp, root=tmp)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            origin = f'http://127.0.0.1:{server.server_port}'
            base = f'{origin}/{server.local_token}/v1/console/'

            def release(pid, url=base+'release', request_origin=origin):
                request = urllib.request.Request(url, data=json.dumps({'pid': pid}).encode(),
                                                 headers={'Origin': request_origin})
                with urllib.request.urlopen(request, timeout=5) as response:
                    return response.status

            def refuse(status, *args, **kwargs):
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    release(*args, **kwargs)
                self.assertEqual(caught.exception.code, status)

            try:
                with urllib.request.urlopen(base+'health', timeout=5) as response:
                    health = json.load(response)
                self.assertEqual(health['pid'], os.getpid())
                self.assertEqual(health['memory_documents'], 'missing')
                refuse(403, os.getpid(), url=origin+'/wrong/v1/console/release')
                refuse(403, os.getpid(), request_origin='https://example.invalid')
                refuse(409, os.getpid())
                with patch.object(server.memory, 'access_status', return_value='denied'):
                    refuse(409, os.getpid()+1)
                    with patch('console_reload.precheck', side_effect=RuntimeError('active work')):
                        refuse(409, os.getpid())
                    self.assertFalse(server.releasing)
                    with patch('console_reload.precheck'):
                        self.assertEqual(release(os.getpid()), 202)
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
            finally:
                server.shutdown()
                server.server_close()

    def test_snapshot_cache_failure_and_no_truncation(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=MemoryLibrary(out=tmp,root=tmp)
            self.assertIsNone(lib.snapshot()['catalog'])
            self.assertIn('同步记忆',lib.snapshot()['error'])
            path=Path(tmp)/'catalog.json';data=sample();path.write_text(json.dumps(data))
            self.assertEqual(lib.snapshot()['catalog']['total'],1)
            self.assertIsNone(lib.snapshot(data['generated_at'])['catalog'])
            path.write_text('{bad')
            self.assertTrue(lib.snapshot()['error'])
            self.assertEqual(lib.snapshot()['catalog']['groups'][0]['entries'][0]['value'],'完整事实')
            big=sample();big['groups'][0]['entries'][0]['value']='x'*(16*1024*1024+1)
            path.write_text(json.dumps(big))
            self.assertEqual(lib.snapshot()['error'],'')
            self.assertEqual(lib.snapshot()['catalog']['total'],1)
            with patch.dict('console_memory.os.environ',{'MEMORY_OS_CATALOG_MAX_BYTES':'1048576'}):
                lib.stamp=None
                self.assertIn('MEMORY_OS_CATALOG_MAX_BYTES',lib.snapshot()['error'])
                self.assertEqual(lib.snapshot()['catalog']['total'],1)

    def test_fixed_sync_command_and_start_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            lib=MemoryLibrary(out=tmp,root=tmp)
            with patch('console_memory.subprocess.Popen',side_effect=OSError) as launch:
                self.assertEqual(lib.sync()['status'],'error')
                self.assertEqual(launch.call_args.args[0],[str(Path(tmp)/'venv/bin/python'),str(Path(tmp)/'humanize_sync.py')])
                reader = Path(tmp)/'ReaderDocuments'
                reader.mkdir()
                self.assertEqual(MemoryLibrary(root=tmp).sync()['status'], 'error')
                self.assertEqual(launch.call_args.args[0][-1], '--reader-only')

    def test_protected_routes_and_sidebar_order(self):
        self.assertLess(PAGE.index('data-v="memory"'), PAGE.index('data-v="sys"'))
        self.assertLess(PAGE.index('data-v="memory"'), PAGE.index('id="side-toggle"'))
        self.assertIn('memory:["memory"]',PAGE)
        self.assertIn('.memory-list[hidden]{display:none}',PAGE)
        with tempfile.TemporaryDirectory() as tmp:
            data=sample();(Path(tmp)/'catalog.json').write_text(json.dumps(data))
            server=make_server(0,tmp,launch_schedules=False);server.memory=MemoryLibrary(out=tmp,root=tmp)
            threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
            origin='http://127.0.0.1:'+str(server.server_port);base=origin+'/'+server.local_token
            try:
                with urllib.request.urlopen(base+'/v1/memory',timeout=5) as response:
                    result=json.load(response);self.assertEqual(result['catalog']['total'],1)
                for url,headers in [(origin+'/wrong/v1/memory',{}),(base+'/v1/memory',{'Origin':'http://elsewhere.invalid'})]:
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=5)
                    self.assertEqual(caught.exception.code,403)
                with patch('console.app.run_open',return_value=True) as opener:
                    req=urllib.request.Request(base+'/v1/memory/open-folder',data=b'{"path":"/tmp/untrusted"}',headers={'Content-Type':'application/json','Origin':origin})
                    with urllib.request.urlopen(req,timeout=5) as response:
                        self.assertTrue(json.load(response)['ok'])
                    opener.assert_called_once_with(['/usr/bin/open',tmp])
                with patch('console.app.run_open',return_value=True) as opener:
                    req=urllib.request.Request(base+'/v1/memory/open-folder',data=b'{}',headers={'Content-Type':'application/json','Origin':'http://elsewhere.invalid'})
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(req,timeout=5)
                    self.assertEqual(caught.exception.code,403)
                    opener.assert_not_called()
                dest=Path(tmp)/'导出/记忆-全文.txt'
                with patch.object(server.memory,'export',return_value=dest) as exporter, patch('console.app.run_open',return_value=True) as opener:
                    req=urllib.request.Request(base+'/v1/memory/export',data=b'{"kind":"txt","path":"/tmp/untrusted"}',headers={'Content-Type':'application/json','Origin':origin})
                    with urllib.request.urlopen(req,timeout=5) as response:
                        result=json.load(response);self.assertEqual(result['filename'],dest.name)
                    exporter.assert_called_once_with('txt')
                    opener.assert_called_once_with(['/usr/bin/open','-R',str(dest)])
                with patch.object(server.memory,'export') as exporter:
                    req=urllib.request.Request(base+'/v1/memory/export',data=b'{"kind":"raw"}',headers={'Content-Type':'application/json','Origin':'http://elsewhere.invalid'})
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(req,timeout=5)
                    self.assertEqual(caught.exception.code,403)
                    exporter.assert_not_called()
                with patch('console_memory.subprocess.Popen',side_effect=OSError):
                    req=urllib.request.Request(base+'/v1/memory/sync',data=b'{}',headers={'Content-Type':'application/json','Origin':origin})
                    with urllib.request.urlopen(req,timeout=5) as response:
                        self.assertEqual(json.load(response)['status'],'error')
                req=urllib.request.Request(base+'/v1/memory/sync',data=b'{}',headers={'Content-Type':'application/json','Origin':'http://elsewhere.invalid'})
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(req,timeout=5)
                self.assertEqual(caught.exception.code,403)
            finally:
                server.shutdown();server.server_close()


if __name__ == '__main__':
    unittest.main()
