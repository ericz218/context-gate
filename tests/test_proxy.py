import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gate_proxy import make_server,is_initial_attachment

class ProxyTests(unittest.TestCase):
    def test_every_protocol_two_turns_and_auth_preservation(self):
        seen=[];packs=[]
        class Upstream(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                seen.append((self.path,json.loads(self.rfile.read(int(self.headers['Content-Length']))),self.headers.get('Authorization')))
                b=b'{"ok":true}';self.send_response(200);self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        def packer(job):
            packs.append(job);return {'ready_to_send':True,'prompt':'CURRENT PACK '+str(len(packs)),'metrics':{}}
        job={'root':'/tmp','memory':['/tmp/m.md'],'agent_id':'a','session_id':'s','task_id':'t','platform':'generic','request':'inspect'}
        gate=make_server(0,'http://127.0.0.1:'+str(upstream.server_port),job,b'secret',packer)
        gate.model_override='explicit-test-model'
        gate.initial_prompt='OLD INITIAL PACK\nSecond line\n'
        gate.initial_prompt_path='/tmp/pack.txt'
        projection='<system-reminder>\nCalled the Read tool with the following input: {"file_path":"/tmp/pack.txt"}\nResult of calling the Read tool:\n1\tOLD INITIAL PACK\n2\tSecond line\n3\t\n</system-reminder>'
        for s in (upstream,gate):threading.Thread(target=s.serve_forever,daemon=True).start()
        try:
            base='http://127.0.0.1:'+str(gate.server_port)+'/'+gate.local_token
            for path,field in (('/v1/responses','input'),('/v1/chat/completions','messages'),('/v1/messages','messages')):
                body={field:[{'role':'user','content':projection}], 'model':'test'}
                for _ in range(2):
                    req=urllib.request.Request(base+path,json.dumps(body).encode(),{'Authorization':'Bearer upstream-auth','Content-Type':'application/json'})
                    with urllib.request.urlopen(req) as r:self.assertEqual(json.load(r),{'ok':True})
                    body=seen[-1][1]
                wire=json.dumps(body)
                self.assertEqual(wire.count('CURRENT PACK'),1)
                self.assertNotIn('OLD INITIAL PACK',wire)
                self.assertEqual(seen[-1][2],'Bearer upstream-auth')
                self.assertEqual(body['model'],'explicit-test-model')
            self.assertEqual(len(packs),6)
            for event in gate.events:
                self.assertGreater(event['managed_tokens_removed_estimated'],0)
                self.assertGreaterEqual(event['prepare_ms'],0)
                self.assertGreaterEqual(event['first_response_byte_ms'],event['upstream_headers_ms'])
                self.assertGreaterEqual(event['upstream_total_ms'],event['first_response_byte_ms'])
                self.assertGreater(event['response_bytes'],0)
            bad=urllib.request.Request(base+'/v1/messages',b'{}',{'Origin':'https://foreign.example'})
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(bad)
            self.assertEqual(e.exception.code,403)
            self.assertEqual(len(seen),6)
        finally:
            for s in (gate,upstream):s.shutdown();s.server_close()

    def test_only_complete_trusted_attachment_is_recognized(self):
        initial='line one\r\nline two'
        text='<system-reminder>\nCalled the Read tool with the following input: {"file_path":"/tmp/pack.txt"}\nResult of calling the Read tool:\n1\tline one\n2\tline two\n</system-reminder>'
        self.assertTrue(is_initial_attachment(text,initial,'/tmp/pack.txt'))
        for candidate,path in ((text,'/tmp/other.txt'),(text,None),
                               (text.replace('line two','changed'),'/tmp/pack.txt'),
                               (text.replace('"/tmp/pack.txt"','"/tmp/pack.txt","offset":1'),'/tmp/pack.txt'),
                               (text+'\nUnrelated tool result','/tmp/pack.txt')):
            self.assertFalse(is_initial_attachment(candidate,initial,path))

    def test_native_truncation_is_replaced_only_when_it_matches_our_pack(self):
        initial='one\ntwo\nthree'
        header='<system-reminder>\nCalled the Read tool with the following input: {"file_path":"/tmp/pack.txt"}\nResult of calling the Read tool:\n'
        notice='&lt;system-reminder>The file is too large to display in full (30000 estimated tokens, limit 25000). Showing a partial view of lines 1-2 of 3. Use Read with offset 3 and limit 2000 to continue, or use a search tool to find a specific section.&lt;/system-reminder>\n\n'
        text=header+notice+'1\tone\n2\ttwo\n</system-reminder>'
        self.assertTrue(is_initial_attachment(text,initial,'/tmp/pack.txt'))
        for bad in (text.replace('2\ttwo','2\tunknown'),text.replace('of 3.','of 99.'),text.replace('offset 3','offset 4')):
            self.assertFalse(is_initial_attachment(bad,initial,'/tmp/pack.txt'))
        notice='&lt;system-reminder>The file is too large to display in full (30000 estimated tokens, limit 25000). Showing a partial view of the first line because the first line alone exceeds the token budget. Use Read with a smaller range or use a search tool to find a specific section.&lt;/system-reminder>\n\n'
        text=header+notice+'1\tlong\n</system-reminder>'
        self.assertTrue(is_initial_attachment(text,'long first line','/tmp/pack.txt'))
        self.assertFalse(is_initial_attachment(text,'different first line','/tmp/pack.txt'))
