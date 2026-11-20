"""Workbench project cards: bootstrap only indexes projects, the fields come from /v1/state."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.parse
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import console_memory

TOKEN = 'test-token-0123456789abcdefghij'
ROOT = '/tmp/proj-one'
VALUES = {'current_project_status': '进度：收口完成', 'next_steps': '下一步：验收'}


class FakeState(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.calls.append(self.path)
        if self.headers.get('Authorization') != 'Bearer ' + TOKEN:
            self.send_response(401); self.end_headers(); return
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path != '/v1/state' or query.get('scope') != ['project']:
            self.send_response(404); self.end_headers(); return
        value = VALUES.get(query.get('key', [''])[0]) if query.get('scope_id') == [ROOT] else None
        body = json.dumps({'ir': {'key': query['key'][0], 'value': value}} if value else {}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ProjectRowsTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), FakeState)
        self.server.calls = []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        (self.home / 'Library/Application Support/MemoryOS').mkdir(parents=True)
        (self.home / 'Library/Application Support/MemoryOS/client.json').write_text(json.dumps({
            'MEMORY_OS_HTTP_URL': 'http://127.0.0.1:%d' % self.server.server_port,
            'MEMORY_OS_API_TOKEN': TOKEN}))
        bootstrap = {'state': {}, 'projects': [{'project_id': ROOT, 'state_keys': 2, 'last_recorded': ''}]}

        class Done:
            returncode = 0
            stdout = json.dumps(bootstrap)

        self.run_patch = patch.object(console_memory.subprocess, 'run', return_value=Done())
        self.home_patch = patch.object(console_memory.Path, 'home', return_value=self.home)
        self.run_patch.start()
        self.home_patch.start()
        console_memory._cache.update(rows=[], error='', at=0)

    def tearDown(self):
        self.home_patch.stop()
        self.run_patch.stop()
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def test_bootstrap_index_is_completed_by_scoped_state_reads(self):
        console_memory._refresh()
        rows = console_memory._cache['rows']
        self.assertEqual(console_memory._cache['error'], None)
        self.assertEqual([r['root'] for r in rows], [ROOT])
        self.assertEqual(rows[0]['state_text'], VALUES['current_project_status'])
        self.assertEqual(rows[0]['next'], VALUES['next_steps'])
        self.assertEqual(sorted(rows[0]['values']), sorted(VALUES))
        self.assertTrue(all('scope=project' in path for path in self.server.calls))

    def test_unreachable_state_api_keeps_bootstrap_error(self):
        self.server.shutdown()
        self.server.server_close()
        console_memory._refresh()
        self.assertEqual(console_memory._cache['rows'], [])
        self.assertIn('Memory OS', console_memory._cache['error'])


if __name__ == '__main__':
    unittest.main()
