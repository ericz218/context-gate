import json
from pathlib import Path
import tempfile
import unittest
from console_search import search, detail
from token_stats import save


class SearchTests(unittest.TestCase):
    def test_history_paging_and_redaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            save('old-request', 'codex', {'baseline_tokens_estimated': 10, 'final_tokens_estimated': 5}, True, state_dir=tmp, model='known-model')
            folder = Path(tmp) / 'gate-tasks'
            folder.mkdir()
            (folder / 'task.json').write_text(json.dumps({'task_id': 'known-task', 'api_key': 'secret-value'}))
            found = search(tmp, 'old-request')
            self.assertEqual(found['total'], 1)
            self.assertEqual(found['model_calls'], 0)
            self.assertEqual(search(tmp, 'known', limit=1)['total'], 2)
            self.assertEqual(len(search(tmp, 'known', offset=1, limit=1)['results']), 1)
            self.assertEqual(search(tmp, 'secret-value')['total'], 0)
            result=search(tmp, 'known-task')['results'][0]
            self.assertNotIn('secret-value', detail(tmp,result['id'])['content'])
            self.assertEqual(search(tmp, 'missing')['total'], 0)

    def test_full_logs_and_provider_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'service.log').write_text('old-event-identifier\n'+'filler\n'*8000+'recent error\n')
            exact=search(tmp,'old-event-identifier',decide=lambda *a:self.fail('literal query called a model'))
            self.assertEqual(exact['total'],1)
            self.assertIn('old-event-identifier',detail(tmp,exact['results'][0]['id'])['content'])
            calls=[]
            def choose(provider,state,questions):
                calls.append(provider)
                if provider=='laya':raise RuntimeError('offline')
                return {'answers':{k:{'choice':'yes'} for k in questions}}
            fuzzy=search(tmp,'帮我找最近出问题的记录',decide=choose)
            self.assertEqual(calls,['laya','jev'])
            self.assertEqual(fuzzy['mode'],'jev')
            self.assertTrue(fuzzy['results'])
            def broken(*args):raise RuntimeError('offline')
            failed=search(tmp,'帮我找出问题的记录',decide=broken)
            self.assertEqual(failed['mode'],'local-fallback')
            self.assertTrue(any('均不可用' in w for w in failed['warnings']))
            laya=search(tmp,'帮我找那个记录',decide=lambda p,s,q:{'answers':{k:{'choice':'yes'} for k in q}})
            self.assertEqual(laya['mode'],'laya')
            self.assertEqual(laya['model_calls'],1)
