import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile,json,io,contextlib
from context_gate import render, ReviewHTTPError
from gate_run import main

class NegativeSavingsTests(unittest.TestCase):
    def test_duplicate_sources_remain_addressable(self):
        text='unique source body '*200
        items=[dict(path='a.md',content=text,source_type='document'),dict(path='b.md',content=text,source_type='document')]
        prompt=render('CORE','TASK',items,[])
        self.assertEqual(prompt.count(text),1)
        self.assertIn('b.md',prompt)
        self.assertIn('Content already included in a.md',prompt)
        self.assertEqual(items[1]['content'],text)

    def test_http_error_contains_status_only(self):
        error=ReviewHTTPError('jev',429)
        self.assertEqual(error.status,429)
        self.assertEqual(str(error),'jev HTTP 429')

    def test_fallback_with_positive_metric_still_never_launches(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp); (p/'root').mkdir()
            pack={'prompt':'p','mode':'full_fallback','ready_to_send':True,'metrics':{'baseline_tokens_estimated':100,'final_tokens_estimated':50,'saved_tokens_estimated':50,'reduction_pct_estimated':50}}
            (p/'pack').write_text(json.dumps(pack))
            argv=['gate_run.py','--platform','codex','--root',str(p/'root'),'--memory',str(p/'root/m.md'),'--request','task','--reuse-pack',str(p/'pack'),'--output',str(p/'out'),'--dry-run']
            with patch('sys.argv',argv),patch('gate_run.subprocess.Popen') as popen,contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main(),3)
                popen.assert_not_called()
