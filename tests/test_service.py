import concurrent.futures
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from context_gate import Config
from gate_service import Engine, make_server
from gate_run import command


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name);self.root=self.base/'project';self.root.mkdir()
        self.memory=self.root/'memory.md';self.memory.write_text('[CORE_MEMORY_START]\nShared core\n[CORE_MEMORY_END]')
        (self.root/'price.py').write_text('def price():\n    return 7\n')
        self.engine=Engine([self.root],Config(cache_dir=str(self.base/'cache')),state_dir=self.base/'state')
        self.server=make_server(0,'synthetic-token',self.engine)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
    def body(self,agent):
        return {'root':str(self.root),'memory':[str(self.memory)],'request':'Only task '+agent,
                'agent_id':agent,'session_id':'s','task_id':'t-'+agent,'platform':'generic'}
    def test_concurrent_agent_requests_are_isolated(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda a:self.engine.pack(self.body(a)),['one','two','three']))
        for agent,r in zip(['one','two','three'],results):
            self.assertEqual(r['request'],'Only task '+agent)
            self.assertEqual(r['identity']['agent_id'],agent)
            self.assertEqual(r['core_memory'],'[CORE_MEMORY_START]\nShared core\n[CORE_MEMORY_END]')
        log=(self.base/'state/metrics.jsonl').read_text()
        self.assertNotIn('Shared core',log);self.assertNotIn('Only task',log)
    def test_http_requires_authentication(self):
        url='http://127.0.0.1:'+str(self.server.server_port)+'/health'
        with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(url)
        self.assertEqual(e.exception.code,401)
        req=urllib.request.Request(url,headers={'Authorization':'Bearer synthetic-token'})
        with urllib.request.urlopen(req) as r:self.assertEqual(json.load(r)['version'],2)
    def test_memory_and_project_scope(self):
        b=self.body('a');b['root']=str(self.base)
        with self.assertRaises(ValueError):self.engine.pack(b)
        b=self.body('a');b['memory']=[str(self.base/'outside.md')]
        with self.assertRaises(ValueError):self.engine.pack(b)
    def test_native_adapter_shapes(self):
        p=self.base/'prompt.txt';p.write_text('CORE + REQUEST + PACK')
        for platform in ('codex','gpt','claude'):
            argv,env,stdin=command(platform,str(self.root),p)
            self.assertEqual(stdin,p.read_text());self.assertNotIn('--resume',argv)
        argv,env,stdin=command('zcode',str(self.root),p)
        self.assertIn('--attach',argv);self.assertEqual(env['ELECTRON_RUN_AS_NODE'],'1')
