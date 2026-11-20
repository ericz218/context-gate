from pathlib import Path
import sys
import tempfile
import unittest
import contextlib
import io
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from gate_run import command,main


class RunTests(unittest.TestCase):
    def test_zcode_cannot_silently_use_truncating_initial_only_mode(self):
        with patch('sys.argv',['gate_run.py','--platform','zcode','--root','/tmp/test','--memory','/tmp/test/m.md','--request','inspect','--output','/tmp/out.json','--initial-only']),patch('gate_run.call_service') as packer,contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as result:main()
        self.assertEqual(result.exception.code,2)
        self.assertIn('原生附件截断',err.getvalue())
        packer.assert_not_called()

    def test_core_newlines_survive_native_stdin_preparation(self):
        with tempfile.TemporaryDirectory() as tmp:
            prompt=Path(tmp)/'pack.txt';raw=b'[CORE_MEMORY_START]\r\nCore\r\n[CORE_MEMORY_END]'
            prompt.write_bytes(raw)
            for platform in ('codex','claude'):
                _,_,stdin=command(platform,tmp,prompt)
                self.assertEqual(stdin.encode('utf-8'),raw)

    def test_zcode_receives_exact_task_without_global_config_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            config=root/'.zcode/v2/runtime/provider/test/zcode-builtin.json'
            config.parent.mkdir(parents=True);config.write_text('{}')
            prompt=root/'pack.txt';prompt.write_text('context')
            task='Read only. Return one sentence.'
            with patch('gate_run.__file__',str(root/'gate_run.py')),patch('gate_run.Path.home',return_value=root):
                args,env,stdin=command('zcode',str(root),prompt,request=task)
            self.assertTrue(args[args.index('--prompt')+1].startswith(task+'\n\n'))
            self.assertEqual(args[args.index('--attach')+1],str(prompt))
            self.assertEqual(config.read_text(),'{}')
            self.assertIsNone(stdin)
