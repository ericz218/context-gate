import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch

import console_capability as cap
from tests.test_router_capability import default_requests, make_router_db


class CapabilityPageTests(unittest.TestCase):
    def test_tab_and_route_are_wired(self):
        from console.app import PAGE
        self.assertIn('data-router-tab="capabilities"', PAGE)
        self.assertIn("centerApi('router/capabilities')", PAGE)
        self.assertIn('routerCapRow', PAGE)

    def test_capability_route_serves_read_only_table_with_fallback_reason(self):
        from console.app import make_server
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'router.db'
            make_router_db(db, default_requests())
            with patch.object(cap, 'ROUTER_DB', db), patch.object(cap, 'ROUTER_URL', 'http://127.0.0.1:9'):
                server = make_server(0, tmp, launch_schedules=False)
            server.capabilities.router_url = 'http://127.0.0.1:9'
            server.fallback.router_url = 'http://127.0.0.1:9'
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True).start()
            base = 'http://127.0.0.1:' + str(server.server_port) + '/' + server.local_token
            try:
                with urllib.request.urlopen(base + '/v1/router/capabilities') as response:
                    data = json.load(response)
            finally:
                server.shutdown()
                server.server_close()
            keys = {r['key']: r['status'] for r in data['records']}
            self.assertEqual('retired', keys['NVIDIA/GLM-5.3'])
            self.assertFalse(data['router']['reachable'])
            self.assertEqual('fallback_unavailable', data['fallback']['fallback'])
            self.assertEqual('disabled', data['fallback']['reason'])

    @unittest.skipUnless(shutil.which('node'), 'Node is needed for the page renderer')
    def test_row_renderer_marks_status_and_unknowns(self):
        from console.router_ui import JS
        start = JS.index('let routerCaps=null')
        end = JS.index('function renderCapabilities(')
        script = r'''
const assert=require('node:assert/strict');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const T=s=>s,num=n=>String(n),LOCALE=()=>'zh-CN';
''' + JS[start:end] + r'''
const retired=routerCapRow({key:'NVIDIA/GLM-5.3',platform:'NVIDIA',model:'GLM-5.3',upstreamModel:'z-ai/glm-5.3',enabled:true,status:'retired',
 window:{p50Ms:200,p95Ms:12000,errorRate:0.2,failures:1,requests:5,latencySamples:4},lastError:{kind:'gone',status:410,message:'<b>gone</b>',at:1},
 price:null,toolCalls:'unknown',responsesApi:'unknown',probe:null});
assert.match(retired,/router-badge bad">已下线</);
assert.match(retired,/已下线（410） · 410/);
assert.match(retired,/200 ms \/ 12 s/);
assert.match(retired,/20\.0%/);
assert.match(retired,/&lt;b&gt;gone/);
assert.doesNotMatch(retired,/<b>gone/);
assert.match(retired,/工具调用 未知/);
assert.match(retired,/未检查/);
const ok=routerCapRow({key:'MetaMuse/muse-wonder-1.0',platform:'MetaMuse',model:'muse-wonder-1.0',enabled:false,status:'available',window:{},lastError:null,
 price:{input:'4',output:'20',currency:'USD'},toolCalls:'unknown',responsesApi:'supported',probe:{lastAt:1,kind:'timeout',latencyMs:30000}});
assert.match(ok,/router-badge on">可用/);assert.match(ok,/4 \/ 20/);assert.match(ok,/已停用/);assert.match(ok,/Responses 支持/);assert.match(ok,/超时 · 30 s/);
'''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == '__main__':
    unittest.main()
