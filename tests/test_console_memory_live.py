import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from console import memory_live
from console.app import PAGE,make_server

class MemoryLiveTests(unittest.TestCase):
 def test_demo_whitelist_and_secrets(self):
  d={'events':[{'text':'Authorization: Bearer secret_token_value_1234567890','status':'已更新'}],'memories':{},'online':True,'api_key':'never-return','run':'ignored'}
  with patch.object(memory_live,'_read',return_value=d):out=memory_live._snapshot()
  self.assertEqual(out['mode'],'live');self.assertNotIn('api_key',out);self.assertNotIn('run',out)
  self.assertNotIn('secret_token_value_1234567890',json.dumps(out))
 def test_offline_does_not_claim_live(self):
  with patch.object(memory_live,'_read',side_effect=OSError),patch.object(memory_live.Path,'read_text',side_effect=OSError):
   out=memory_live._snapshot()
  self.assertEqual(out['mode'],'offline');self.assertFalse(out['online']);self.assertEqual(out['events'],[])
 def test_store_fallback(self):
  d={'recent_events':[{'event_id':'e1','recorded_at':'2026-11-12T00:00:00Z','version':2,'ir':{'action':'supersede','key':'time','value':'周日'}}]}
  with patch.object(memory_live,'_read',side_effect=[OSError(),d]),patch.object(memory_live.Path,'read_text',return_value='{"MEMORY_OS_API_TOKEN":"private"}'):
   out=memory_live._snapshot()
  self.assertEqual(out['mode'],'store');self.assertEqual(out['events'][0]['status'],'已更新');self.assertEqual(out['memories'],[])
 def test_protected_route_and_popup(self):
  self.assertIn('id="memory-live-open"',PAGE);self.assertIn('aria-modal="false"',PAGE);self.assertIn('clearTimeout(memoryLiveTimer)',PAGE)
  with tempfile.TemporaryDirectory() as tmp:
   server=make_server(0,tmp,launch_schedules=False)
   threading.Thread(target=server.serve_forever,daemon=True).start()
   origin='http://127.0.0.1:'+str(server.server_port);url=origin+'/'+server.local_token+'/v1/memory/live'
   try:
    with patch.object(memory_live,'snapshot',return_value={'mode':'live','events':[]}):
     with urllib.request.urlopen(url) as r:self.assertEqual(json.load(r)['mode'],'live')
     for u,headers in [(origin+'/wrong/v1/memory/live',{}),(url,{'Origin':'https://example.invalid'})]:
      with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(urllib.request.Request(u,headers=headers))
      self.assertEqual(e.exception.code,403)
   finally:server.shutdown();server.server_close()
if __name__=='__main__':unittest.main()
