import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import passthrough_proxy as watch


class FakeUpstream(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_POST(self):
        length=int(self.headers.get('Content-Length','0'));self.rfile.read(length)
        if self.path.rstrip('/').endswith('count_tokens'):
            body=b'{"input_tokens":1234}'
        else:
            body=(b'event: message_start\ndata: {"type":"message_start","message":{"model":"GLM-5.3-Flash","usage":{"input_tokens":100,"cache_creation_input_tokens":20,"cache_read_input_tokens":50}}}\n\n'
                  b'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":30}}\n\n')
        self.send_response(200);self.send_header('Content-Type','text/event-stream')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


class PassthroughTests(unittest.TestCase):
    def test_forward_account_and_skip_count_tokens(self):
        with tempfile.TemporaryDirectory() as tmp:
            watch.STATE=Path(tmp)
            upstream=watch.ThreadingHTTPServer(('127.0.0.1',0),FakeUpstream)
            threading.Thread(target=upstream.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
            server=watch.make_server(0,'http://127.0.0.1:'+str(upstream.server_port))
            threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()
            base='http://127.0.0.1:'+str(server.server_port)+server.token_prefix
            try:
                request=urllib.request.Request(base+'/v1/messages',data=json.dumps({'model':'GLM-5.3-Flash','messages':[]}).encode(),headers={'Content-Type':'application/json','x-api-key':'secret-key-value'},method='POST')
                with urllib.request.urlopen(request,timeout=5) as r:
                    payload=r.read().decode()
                self.assertIn('GLM-5.3-Flash',payload);self.assertIn('message_delta',payload)
                import sqlite3
                with sqlite3.connect(str(Path(tmp)/'tokens.sqlite3')) as db:
                    db.row_factory=sqlite3.Row
                    rows=[dict(r) for r in db.execute('SELECT * FROM turns')]
                self.assertEqual(len(rows),1)
                row=rows[0]
                self.assertEqual(row['platform'],'zcode');self.assertEqual(row['model'],'GLM-5.3-Flash')
                # input follows the ledger convention: plain 100 + read 50 + creation 20
                self.assertEqual((row['actual_input'],row['cached'],row['cache_creation'],row['actual_output']),(170,50,20,30))
                self.assertEqual(row['exit_code'],0);self.assertEqual(row['before_est'],row['after_est'])
                self.assertIsNotNone(row['duration_ms']);self.assertGreaterEqual(row['duration_ms'],0)
                request=urllib.request.Request(base+'/v1/messages/count_tokens',data=b'{}',headers={'Content-Type':'application/json'},method='POST')
                with urllib.request.urlopen(request,timeout=5) as r:
                    self.assertIn(b'1234',r.read())
                with sqlite3.connect(str(Path(tmp)/'tokens.sqlite3')) as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM turns').fetchone()[0],1)
                try:
                    urllib.request.urlopen('http://127.0.0.1:'+str(server.server_port)+'/bad/v1/messages',timeout=5);self.fail('expected 403')
                except urllib.error.HTTPError as e:self.assertEqual(e.code,403)
            finally:
                server.shutdown();server.server_close();upstream.shutdown();upstream.server_close()


if __name__=='__main__':unittest.main()
