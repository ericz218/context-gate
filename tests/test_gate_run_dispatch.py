from pathlib import Path
import json
import sys
import tempfile
import unittest
import contextlib
import io
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gate_run import (CHILD_POLL_SECONDS, default_codex_model, dispatch_cost_usd,
                      estimate_line, load_pack, main, process_table, track_descendants,
                      wait_children)


METRICS={'baseline_tokens_estimated':54660,'final_tokens_estimated':56549,
         'saved_tokens_estimated':-1889,'reduction_pct_estimated':-3.46,
         'jev_input_tokens_estimated':0}


class DispatchEstimateTests(unittest.TestCase):
    def test_fallback_reads_as_cost_not_saving(self):
        line=estimate_line('full_fallback',METRICS,'gpt-6-sol')
        self.assertIn('未压缩回退',line)
        self.assertIn('56549',line)
        self.assertNotIn('节省 -',line)
        self.assertIn('$0.14',line)  # 56549/1e6 * 2.5 cache-write

    def test_packed_line_keeps_saving_format(self):
        m=dict(METRICS,final_tokens_estimated=5000,saved_tokens_estimated=49660,
               reduction_pct_estimated=90.85)
        line=estimate_line('filtered',m,'gpt-6-sol')
        self.assertIn('压缩前 54660',line)
        self.assertIn('Pack 5000',line)
        self.assertIn('$0.01',line)

    def test_unknown_model_omits_money(self):
        line=estimate_line('filtered',dict(METRICS,final_tokens_estimated=100),None)
        self.assertNotIn('$',line)

    def test_dispatch_cost_uses_cache_write_rate(self):
        self.assertEqual(dispatch_cost_usd('gpt-6-sol',56549),0.1414)
        self.assertIsNone(dispatch_cost_usd('no-such-model-xyz',56549))
        self.assertIsNone(dispatch_cost_usd(None,56549))
        self.assertIsNone(dispatch_cost_usd('gpt-6-sol',0))


class DefaultModelTests(unittest.TestCase):
    def test_reads_local_default_and_survives_missing_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            config=Path(tmp)/'.codex/config.toml'
            config.parent.mkdir()
            config.write_text('model = "gpt-6-sol"\nmodel_reasoning_effort = "high"\n')
            with patch('gate_run.Path.home',return_value=Path(tmp)):
                self.assertEqual(default_codex_model(),'gpt-6-sol')
                config.unlink()
                self.assertIsNone(default_codex_model())


class ReusePackTests(unittest.TestCase):
    def test_load_pack_rejects_blocked_or_malformed_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'result.json'
            path.write_text(json.dumps({'prompt':'x','metrics':{},'ready_to_send':False,'mode':'full_fallback'}))
            with self.assertRaises(ValueError):
                load_pack(str(path))
            path.write_text(json.dumps({'prompt':'x'}))
            with self.assertRaises(ValueError):
                load_pack(str(path))
            path.write_text(json.dumps({'prompt':'x','metrics':METRICS,'ready_to_send':True,'mode':'filtered'}))
            self.assertEqual(load_pack(str(path))['mode'],'filtered')

    def test_reuse_dispatch_never_calls_the_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir()
            pack=Path(tmp)/'pack.json'
            pack.write_text(json.dumps({'prompt':'PACK','metrics':METRICS,
                                        'ready_to_send':True,'mode':'full_fallback'}))
            out=Path(tmp)/'out.json'
            argv=['gate_run.py','--platform','codex','--root',str(root),'--memory',str(root/'m.md'),
                  '--request','retry task','--output',str(out),'--reuse-pack',str(pack),'--dry-run',
                  '--allow-fallback']
            with patch('sys.argv',argv),patch('gate_run.call_service') as packer, \
                 contextlib.redirect_stderr(io.StringIO()) as err:
                code=main()
            self.assertEqual(code,0)
            packer.assert_not_called()  # a retry must not re-run retrieval + Jev screening
            self.assertEqual(json.loads(out.read_text())['prompt'],'PACK')
            self.assertIn('未压缩回退',err.getvalue())


class ChildCompletionTests(unittest.TestCase):
    def test_track_descendants_walks_the_whole_tree(self):
        table={1:(0,'launchd'),10:(1,'codex exec'),11:(10,'zsh'),12:(11,'Unity'),
               20:(1,'unrelated')}
        with patch('gate_run.process_table',return_value=table):
            kids=track_descendants(10)
        self.assertEqual(set(kids),{11,12})
        self.assertEqual(kids[12],'Unity')

    def test_wait_children_blocks_until_background_work_ends(self):
        polls=iter([{100:(999,'/usr/bin/unity'),200:(100,'validate')},
                    {200:(1,'validate')},
                    {}])
        with patch('gate_run.process_table',side_effect=lambda:next(polls)), \
             patch('gate_run.CHILD_POLL_SECONDS',0):
            remaining=wait_children({100:'/usr/bin/unity'},60)
        self.assertEqual(remaining,{})

    def test_wait_children_treats_pid_reuse_as_exit(self):
        with patch('gate_run.process_table',return_value={100:(999,'some other binary')}), \
             patch('gate_run.CHILD_POLL_SECONDS',0):
            remaining=wait_children({100:'/usr/bin/unity'},60)
        self.assertEqual(remaining,{})

    def test_zero_timeout_reports_survivors_without_waiting(self):
        with patch('gate_run.process_table') as probe:
            remaining=wait_children({7:'/usr/bin/unity'},0)
        self.assertEqual(remaining,{7:'/usr/bin/unity'})
        probe.assert_not_called()


class ProcessTableTests(unittest.TestCase):
    def test_parses_ps_output_and_skips_garbage(self):
        fake='  1     0 /sbin/launchd\n  42     1 codex exec --json\nbad line\n  7  2\n'
        with patch('gate_run.subprocess.run') as run:
            run.return_value.stdout=fake
            table=process_table()
        self.assertEqual(table[42],(1,'codex exec --json'))
        self.assertNotIn(7,table)


class DeclineUnprofitableTests(unittest.TestCase):
    PACK=dict(prompt='PACK',metrics=METRICS,ready_to_send=True,mode='full_fallback')

    def _write_pack(self,tmp):
        pack=Path(tmp)/'pack.json'
        pack.write_text(json.dumps(self.PACK))
        return pack

    def test_dry_run_declines_unprofitable_pack_without_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir()
            argv=['gate_run.py','--platform','codex','--root',str(root),'--memory',str(root/'m.md'),
                  '--request','t','--output',str(Path(tmp)/'out.json'),
                  '--reuse-pack',str(self._write_pack(tmp)),'--dry-run']
            with patch('sys.argv',argv),patch('gate_run.call_service') as packer, \
                 patch('gate_run.subprocess.Popen') as popen, \
                 contextlib.redirect_stderr(io.StringIO()) as err, \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                code=main()
            self.assertEqual(code,3)
            packer.assert_not_called()
            popen.assert_not_called()
            self.assertIn('拦截',err.getvalue())
            self.assertIn('不自动派发',err.getvalue())
            self.assertIn('"declined": true',stdout.getvalue())

    def test_real_dispatch_declines_and_marks_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir()
            task=Path(tmp)/'task.json'
            task.write_text(json.dumps({'status':'running'}))
            argv=['gate_run.py','--platform','codex','--root',str(root),'--memory',str(root/'m.md'),
                  '--request','t','--output',str(Path(tmp)/'out.json')]
            with patch('sys.argv',argv), \
                 patch('gate_run.call_service',return_value=dict(self.PACK)), \
                 patch('gate_run.register_task',return_value=task), patch('gate_run.STATE',Path(tmp)), \
                 patch('gate_run.save') as save, \
                 patch('gate_run.subprocess.Popen') as popen, \
                 contextlib.redirect_stderr(io.StringIO()):
                code=main()
            self.assertEqual(code,3)
            popen.assert_not_called()  # the money is spent at launch: do not launch
            save.assert_called_once()  # the pack did happen; its metrics stay accounted
            self.assertEqual(json.loads(task.read_text())['status'],'declined')

    def test_allow_fallback_override_still_dispatches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir()
            argv=['gate_run.py','--platform','codex','--root',str(root),'--memory',str(root/'m.md'),
                  '--request','t','--output',str(Path(tmp)/'out.json'),
                  '--reuse-pack',str(self._write_pack(tmp)),'--dry-run','--allow-fallback']
            with patch('sys.argv',argv),patch('gate_run.call_service') as packer, \
                 contextlib.redirect_stderr(io.StringIO()) as err, \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                code=main()
            self.assertEqual(code,0)
            packer.assert_not_called()
            self.assertIn('未压缩回退',err.getvalue())
            self.assertNotIn('"declined": true',stdout.getvalue())

    def test_profitable_pack_is_never_declined(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir()
            pack=Path(tmp)/'pack.json'
            good=dict(self.PACK,mode='filtered',metrics=dict(
                METRICS,final_tokens_estimated=5000,saved_tokens_estimated=49660,
                reduction_pct_estimated=90.85))
            pack.write_text(json.dumps(good))
            argv=['gate_run.py','--platform','codex','--root',str(root),'--memory',str(root/'m.md'),
                  '--request','t','--output',str(Path(tmp)/'out.json'),'--reuse-pack',str(pack),'--dry-run']
            with patch('sys.argv',argv),patch('gate_run.call_service') as packer, \
                 contextlib.redirect_stdout(io.StringIO()) as stdout:
                code=main()
            self.assertEqual(code,0)
            packer.assert_not_called()
            self.assertNotIn('"declined": true',stdout.getvalue())


if __name__=='__main__':
    unittest.main()
