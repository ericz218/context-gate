import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from console_data import gate_tasks


def write_task(folder, name, payload):
    path = Path(folder) / (name + '.json')
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


class GateTaskTests(unittest.TestCase):
    def test_live_recent_and_stale_tasks(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            (state / 'gate-tasks').mkdir()
            dead = subprocess.Popen(['true']); dead.wait()
            now = time.time()
            write_task(state/'gate-tasks', 'a-live', {'task_id': 'a', 'pid': os.getpid(), 'status': 'running', 'started_at': now-60, 'root': '/tmp/x', 'platform': 'claude'})
            write_task(state/'gate-tasks', 'b-dead', {'task_id': 'b', 'pid': dead.pid, 'status': 'running', 'started_at': now-600, 'root': '/tmp/x'})
            write_task(state/'gate-tasks', 'c-done', {'task_id': 'c', 'pid': 1, 'status': 'done', 'started_at': now-7000, 'ended_at': now-3600,
                                                      'turns': [{'endpoint': '/v1/messages', 'at': now-3600, 'request_before_tokens_estimated': 100, 'request_after_tokens_estimated': 30}]})
            write_task(state/'gate-tasks', 'd-stale', {'task_id': 'd', 'pid': 1, 'status': 'done', 'started_at': now-200000, 'ended_at': now-172800})
            write_task(state/'gate-tasks', 'e-broken', None)  # unparseable json
            (state/'gate-tasks'/'not-json.txt').write_text('x')
            tasks = gate_tasks(state)
            # running first; rest newest-started first. Tasks older than 24h stay
            # in the payload (the console filters by time client-side); only
            # unparseable entries are dropped.
            self.assertEqual([t['task_id'] for t in tasks], ['a', 'b', 'c', 'd'])
            by_id = {t['task_id']: t for t in tasks}
            self.assertEqual(by_id['a']['display_status'], 'running')
            self.assertEqual(by_id['b']['display_status'], 'interrupted')
            self.assertEqual(by_id['c']['display_status'], 'done')
            self.assertEqual(by_id['c']['turns'][0]['request_after_tokens_estimated'], 30)
            self.assertEqual(by_id['d']['display_status'], 'done')


if __name__ == '__main__':
    unittest.main()
