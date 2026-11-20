import contextlib
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evidence
from token_stats import save, totals
from context_gate import Config
from gate_service import Engine, make_server

METRICS = {'baseline_tokens_estimated': 100, 'final_tokens_estimated': 40}


def _append_many(state, worker, n):
    for i in range(n):
        evidence.record({'kind': 'external', 'task_id': 'w{}-{}'.format(worker, i), 'collect_git': False}, state)


def git(root, *args):
    subprocess.run(['git', '-C', str(root), *args], check=True, capture_output=True,
                   env=dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
                            GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid'))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.state = self.base / 'state'
        self.log = self.state / 'evidence' / 'evidence.jsonl'

    def quiet(self, argv):
        with contextlib.redirect_stdout(io.StringIO()):
            return evidence.main(argv)

    def add(self, **spec):
        spec.setdefault('collect_git', False)
        return evidence.record(spec, self.state)

    # -- chain -----------------------------------------------------------
    def test_append_builds_hash_chain_and_verifies(self):
        first, second, third = (self.add(task_id='t%d' % i) for i in range(3))
        self.assertEqual([first['seq'], second['seq'], third['seq']], [1, 2, 3])
        self.assertEqual(first['prev_hash'], evidence.GENESIS)
        self.assertEqual(second['prev_hash'], first['hash'])
        self.assertEqual(third['prev_hash'], second['hash'])
        result = evidence.verify(self.state)
        self.assertTrue(result['ok'], result)
        self.assertEqual((result['records'], result['last_hash']), (3, third['hash']))
        self.assertTrue(evidence.verify(self.state, expect_head=third['hash'])['ok'])
        self.assertFalse(evidence.verify(self.state, expect_head=first['hash'])['ok'])
        self.assertEqual(len(self.log.read_text().splitlines()), 3)

    def test_single_byte_change_is_detected(self):
        for i in range(3):
            self.add(task_id='task-%d' % i, note='value 5')
        lines = self.log.read_bytes().split(b'\n')
        self.assertIn(b'value 5', lines[1])
        lines[1] = lines[1].replace(b'value 5', b'value 6')
        self.log.write_bytes(b'\n'.join(lines))
        result = evidence.verify(self.state)
        self.assertFalse(result['ok'])
        self.assertIn({'line': 2, 'reason': 'hash_mismatch'}, result['errors'])

    def test_rehashed_record_breaks_the_next_link(self):
        for i in range(3):
            self.add(task_id='t%d' % i)
        lines = self.log.read_bytes().splitlines()
        forged = json.loads(lines[0])
        forged['task_id'] = 'forged'
        forged['hash'] = evidence.record_hash(forged)
        lines[0] = evidence.canonical(forged).encode()
        self.log.write_bytes(b'\n'.join(lines) + b'\n')
        reasons = {(e['line'], e['reason']) for e in evidence.verify(self.state)['errors']}
        self.assertIn((2, 'chain_broken'), reasons)

    def test_whitespace_and_truncation_and_tail_edits_are_detected(self):
        for i in range(3):
            self.add(task_id='t%d' % i)
        original = self.log.read_bytes()
        self.log.write_bytes(original.replace(b'"kind":', b'"kind": ', 1))
        self.assertIn('not_canonical_bytes', {e['reason'] for e in evidence.verify(self.state)['errors']})
        # Dropping the last record keeps a valid chain; only the head catches it.
        self.log.write_bytes(b''.join(original.splitlines(keepends=True)[:2]))
        result = evidence.verify(self.state)
        self.assertFalse(result['ok'])
        self.assertTrue(any(e['reason'].startswith('truncated') for e in result['errors']))
        with self.assertRaises(evidence.EvidenceError):
            self.add(task_id='after-truncation')
        # A tampered tail refuses further appends instead of chaining onto it.
        self.log.write_bytes(original.replace(b'"t2"', b'"t9"'))
        with self.assertRaises(evidence.EvidenceError):
            self.add(task_id='after-edit')
        self.assertEqual(self.log.read_bytes(), original.replace(b'"t2"', b'"t9"'))

    def test_files_are_private_even_with_permissive_umask(self):
        old = os.umask(0o022)
        try:
            self.add(task_id='t')
        finally:
            os.umask(old)
        folder = self.state / 'evidence'
        self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
        for name in ('evidence.jsonl', 'evidence.head.json', 'evidence.lock'):
            self.assertEqual(stat.S_IMODE((folder / name).stat().st_mode), 0o600, name)
        self.assertEqual(evidence.verify(self.state)['warnings'], [])

    def test_concurrent_processes_and_threads_append_without_forks(self):
        context = multiprocessing.get_context('spawn')
        procs = [context.Process(target=_append_many, args=(str(self.state), w, 10)) for w in range(4)]
        threads = [threading.Thread(target=_append_many, args=(self.state, 10 + w, 10)) for w in range(4)]
        for item in procs + threads:
            item.start()
        for item in procs + threads:
            item.join(60)
        self.assertTrue(all(p.exitcode == 0 for p in procs))
        result = evidence.verify(self.state)
        self.assertTrue(result['ok'], result['errors'][:3])
        rows = evidence.read_records(self.state)
        self.assertEqual(len(rows), 80)
        self.assertEqual(sorted(r['seq'] for r in rows), list(range(1, 81)))
        self.assertEqual(len({r['task_id'] for r in rows}), 80)

    # -- ledger references ---------------------------------------------------
    def test_ledger_references_do_not_bill_twice(self):
        save('row-a', 'claude', METRICS, True, {'input_tokens': 1000, 'output_tokens': 200, 'cached_input_tokens': 400,
                                                 'cache_creation_input_tokens': 100}, state_dir=self.state, model='claude-sonnet-5-5')
        save('row-b', 'codex', METRICS, True, {'input_tokens': 500, 'output_tokens': 50, 'cached_input_tokens': 0},
             state_dir=self.state, model='unknown-model-x')
        db = self.state / 'tokens.sqlite3'
        before_rows = sqlite3.connect(db).execute('SELECT * FROM turns ORDER BY id').fetchall()
        before_totals = totals(self.state)
        first = self.add(task_id='t1', ledger_ids=['row-a', 'row-a', 'row-b', 'row-gone'])
        second = self.add(task_id='t2', ledger_ids=['row-a'])
        self.assertEqual(sqlite3.connect(db).execute('SELECT * FROM turns ORDER BY id').fetchall(), before_rows)
        self.assertEqual(totals(self.state), before_totals)
        ledger = first['ledger']
        self.assertEqual((ledger['ids'], ledger['missing'], ledger['found']), (['row-a', 'row-b', 'row-gone'], ['row-gone'], 2))
        self.assertEqual(first['tokens'], {'input_tokens': 1500, 'output_tokens': 250, 'cached_input_tokens': 400,
                                           'cache_creation_tokens': 100, 'source': 'ledger'})
        # sonnet-5-5: 500 plain*2 + 100 write*2.5 + 400 read*0.2 + 200 out*10 (per 1M); row-b has no price.
        expected = round((500 * 2 + 100 * 2.5 + 400 * 0.2 + 200 * 10) / 1e6, 6)
        self.assertEqual(first['cost_usd'], {'value': expected, 'source': 'ledger+prices', 'unpriced_rows': 1})
        self.assertEqual(second['tokens']['input_tokens'], 1000)
        overall = evidence.summary(self.state)
        self.assertEqual((overall['ledger_refs_total'], overall['ledger_refs_unique']), (4, 3))
        self.assertEqual(overall['ledger']['input_tokens'], 1500)

    def test_missing_fields_stay_null_with_sources(self):
        row = self.add(kind='external')
        self.assertEqual(row['tokens'], {'input_tokens': None, 'output_tokens': None, 'cached_input_tokens': None,
                                         'cache_creation_tokens': None, 'source': None})
        self.assertEqual(row['cost_usd'], {'value': None, 'source': None})
        self.assertEqual(row['duration_ms'], {'value': None, 'source': None})
        self.assertIsNone(row['model']['model'])
        self.assertIsNone(row['model']['model_source'])
        self.assertEqual(row['missing'], ['task_id', 'root', 'git.commit', 'model', 'tokens', 'cost_usd', 'duration_ms', 'tests', 'ci'])
        reported = self.add(task_id='t', platform='codex', model='gpt-6.1-sol', tokens={'input_tokens': 10, 'output_tokens': 2},
                            cost_usd=0.5, duration_ms=1200)
        self.assertEqual(reported['tokens']['source'], 'reported')
        self.assertEqual(reported['model']['provider'], 'openai')
        self.assertEqual(reported['model']['provider_source'], 'platform_map')
        self.assertEqual(reported['cost_usd'], {'value': 0.5, 'source': 'reported'})
        with self.assertRaises(ValueError):
            evidence.build({'tokens': {'input_tokens': -1}}, self.state)
        with self.assertRaises(ValueError):
            evidence.build({'ci_run_url': 'http://user:pw@example.com/x'}, self.state)

    def test_secrets_and_signed_query_strings_are_not_stored(self):
        row = self.add(task_id='t', note='token sk-abcdefghijklmnopqrstuv end',
                       ci_artifact_urls=['https://github.com/o/r/actions/runs/1/artifacts/2?sig=SECRETSIG'])
        text = self.log.read_text()
        self.assertNotIn('sk-abcdefghijklmnopqrstuv', text)
        self.assertNotIn('SECRETSIG', text)
        self.assertEqual(row['ci']['artifact_urls'], ['https://github.com/o/r/actions/runs/1/artifacts/2'])

    def test_claude_transcript_references_one_row_per_call(self):
        lines = []
        for stamp in ('2026-10-29T10:00:00.100Z', '2026-10-29T10:00:01.200Z'):
            lines.append(json.dumps({'type': 'assistant', 'timestamp': stamp, 'requestId': 'req1', 'message': {
                'id': 'msg1', 'model': 'claude-sonnet-5-5',
                'usage': {'input_tokens': 10, 'cache_creation_input_tokens': 5, 'cache_read_input_tokens': 85, 'output_tokens': 7}}}))
        lines.append(json.dumps({'type': 'assistant', 'timestamp': '2026-10-29T10:05:00.000Z', 'requestId': 'req2', 'message': {
            'id': 'msg2', 'model': 'claude-sonnet-5-5', 'usage': {'input_tokens': 3, 'output_tokens': 1}}}))
        path = self.base / 'session.jsonl'
        path.write_text('\n'.join(lines) + '\n')
        import usage_import
        ids = []
        for at, model, total, out, cached, creation, duration, key in usage_import.claude_entries(path.read_text()):
            ids.append('imp-claude-' + hashlib.sha1(key.encode()).hexdigest()[:24])
        # The importer stores both content-block lines of msg1; msg2 is not imported yet.
        for row_id in ids[:2]:
            save(row_id, 'claude', METRICS, True, {'input_tokens': 100, 'output_tokens': 7, 'cached_input_tokens': 85,
                                                    'cache_creation_input_tokens': 5}, state_dir=self.state, model='claude-sonnet-5-5')
        row = self.add(task_id='t', transcripts=[str(path)])
        self.assertEqual(row['transcripts']['calls'], 2)
        self.assertEqual(row['transcripts']['ledger_duplicate_rows'], 1)
        self.assertEqual(row['transcripts']['unmatched']['entries'], 1)
        self.assertEqual(row['ledger']['ids'], [ids[0]])
        self.assertEqual(row['tokens']['input_tokens'], 100)

    # -- tests -----------------------------------------------------------------
    def test_parses_unittest_and_pytest_summaries(self):
        ok = evidence.parse_test_output('...\n----\nRan 492 tests in 51.2s\n\nOK (skipped=3)\n')
        self.assertEqual((ok['total'], ok['passed'], ok['failed'], ok['errors'], ok['skipped']), (492, 489, 0, 0, 3))
        bad = evidence.parse_test_output('Ran 10 tests in 1s\n\nFAILED (failures=2, errors=1)\n')
        self.assertEqual((bad['passed'], bad['failed'], bad['errors']), (7, 2, 1))
        py = evidence.parse_test_output('===== 5 passed, 1 failed, 2 skipped in 0.12s =====\n')
        self.assertEqual((py['framework'], py['total'], py['passed'], py['failed']), ('pytest', 8, 5, 1))
        self.assertEqual(evidence.parse_test_output('no summary'), {})

    def test_runs_real_test_command_without_shell(self):
        suite = self.base / 'suite'
        suite.mkdir()
        (suite / 'test_x.py').write_text('import unittest\nclass T(unittest.TestCase):\n'
                                         '    def test_a(self): pass\n    def test_b(self): self.assertEqual(1, 2)\n')
        result = evidence.run_test(sys.executable + ' -m unittest discover -s . -p "test_*.py"', suite)
        self.assertEqual((result['exit_code'], result['total'], result['passed'], result['failed']), (1, 2, 1, 1))
        self.assertEqual(result['source'], 'executed')
        missing = evidence.run_test('definitely-not-a-command-xyz', suite)
        self.assertEqual((missing['exit_code'], missing['error']), (None, 'command_not_found'))
        # Shell syntax is not interpreted.
        evidence.run_test(sys.executable + ' -c "pass" ; touch hacked', suite)
        self.assertFalse((suite / 'hacked').exists())

    # -- git, CLI, hooks, HTTP -----------------------------------------------
    def test_cli_records_real_git_and_verify_detects_edit(self):
        repo = self.base / 'repo'
        repo.mkdir()
        git(repo, 'init', '-q')
        (repo / 'a.txt').write_text('a')
        git(repo, 'add', 'a.txt')
        git(repo, 'commit', '-qm', 'init')
        sha = subprocess.run(['git', '-C', str(repo), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        (repo / 'b.txt').write_text('dirty')
        code = self.quiet(['--state-dir', str(self.state), 'record', '--task-id', 'cli-1', '--root', str(repo),
                              '--model', 'claude-sonnet-5-5', '--platform', 'claude', '--test-cmd', 'make test',
                              '--test-exit', '0', '--test-passed', '4', '--test-failed', '0', '--duration-ms', '10'])
        self.assertEqual(code, 0)
        row = evidence.read_records(self.state)[0]
        self.assertEqual((row['git']['commit'], row['git']['dirty'], row['git']['untracked']), (sha, True, 1))
        self.assertEqual(row['tests'][0]['source'], 'reported')
        self.assertEqual(self.quiet(['--state-dir', str(self.state), 'verify']), 0)
        data = self.log.read_bytes()
        self.log.write_bytes(data.replace(b'"make test"', b'"make tesT"'))
        self.assertEqual(self.quiet(['--state-dir', str(self.state), 'verify']), 1)

    def test_gate_task_hook_uses_turn_ledger_ids(self):
        save('pack-1', 'claude', METRICS, False, state_dir=self.state)
        save('turn-1', 'claude', METRICS, True, {'input_tokens': 300, 'output_tokens': 30, 'cached_input_tokens': 0},
             state_dir=self.state, model='claude-sonnet-5-5')
        state = {'task_id': 'g1', 'platform': 'claude', 'root': str(self.base), 'requested_model': None,
                 'started_at': 100.0, 'ended_at': 103.5, 'status': 'done', 'exit_code': 0, 'accounting_id': 'pack-1',
                 'turns': [{'endpoint': '/v1/messages', 'ledger_id': 'turn-1'}, {'local_status': 400}],
                 'usage': {'input_tokens': 999, 'output_tokens': 9}}
        row = evidence.record_gate_task(state, self.state)
        self.assertEqual(row['ledger']['ids'], ['pack-1', 'turn-1'])
        self.assertEqual((row['tokens']['input_tokens'], row['tokens']['source']), (300, 'ledger'))
        self.assertEqual(row['tokens_reported']['input_tokens'], 999)
        self.assertEqual((row['model']['model'], row['model']['model_source']), ('claude-sonnet-5-5', 'ledger'))
        self.assertEqual(row['duration_ms'], {'value': 3500.0, 'source': 'task'})
        self.assertIsNone(evidence.record_gate_task(None, self.state))  # fail-open

    def test_center_task_hook_parses_check_output(self):
        data = {'task_id': 'c1', 'root': str(self.base), 'platform': 'zcode', 'model': 'zcode', 'reasoning': 'native',
                'started_at': 1.0, 'ended_at': 2.0, 'status': 'pending_review', 'exit_code': 0,
                'validation': [{'name': 'tests', 'exit_code': 0, 'output': 'Ran 3 tests in 0.1s\n\nOK\n'},
                               {'name': 'git_status', 'exit_code': 0, 'output': ''}]}
        usage = {'input_tokens': 50, 'output_tokens': 5, 'cached_input_tokens': 0, 'cache_write_input_tokens': 0, 'reported_usd': None}
        row = evidence.record_center_task(data, usage, {'tests': ['python3', '-m', 'unittest']}, self.state)
        self.assertEqual(len(row['tests']), 1)
        self.assertEqual((row['tests'][0]['passed'], row['tests'][0]['command']), (3, 'python3 -m unittest'))
        self.assertEqual(row['tokens']['source'], 'native_task_log')
        self.assertIsNone(row['model']['provider'])

    def test_http_endpoint_records_reported_values_only(self):
        root = self.base / 'project'
        root.mkdir()
        engine = Engine([root], Config(cache_dir=str(self.base / 'cache')), state_dir=self.state)
        server = make_server(0, 'synthetic-token', engine)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url = 'http://127.0.0.1:%d' % server.server_port

        def call(path, body=None, token='synthetic-token', origin=None):
            headers = {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'}
            if origin:
                headers['Origin'] = origin
            request = urllib.request.Request(url + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as exc:
                return exc.code, json.load(exc)

        status, body = call('/v1/evidence', {'task_id': 'h1', 'root': str(root), 'model': 'm',
                                             'tests': [{'command': 'pytest', 'exit_code': 0, 'passed': 2, 'source': 'executed'}]})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['seq'], 1)
        row = evidence.read_records(self.state)[0]
        self.assertEqual((row['tests'][0]['source'], row['origin'], row['git']['error']), ('reported', 'http', 'not_a_git_repo_or_no_commit'))
        self.assertEqual(call('/v1/evidence', {'root': str(self.base)})[0], 400)
        self.assertEqual(call('/v1/evidence', {'kind': 'gate_run'})[0], 400)
        self.assertEqual(call('/v1/evidence', {'run_tests': ['rm -rf /']})[0], 400)
        self.assertEqual(call('/v1/evidence', {'task_id': 'x'}, token='wrong')[0], 401)
        self.assertEqual(call('/v1/evidence', {'task_id': 'x'}, origin='https://evil.example')[0], 403)
        status, result = call('/v1/evidence/verify')
        self.assertEqual((status, result['ok'], result['records']), (200, True, 1))
        status, listing = call('/v1/evidence?task_id=h1&limit=5')
        self.assertEqual((status, len(listing['records']), listing['records'][0]['task_id']), (200, 1, 'h1'))
        self.assertEqual(call('/v1/evidence/verify', origin='https://evil.example')[0], 403)


if __name__ == '__main__':
    unittest.main()
