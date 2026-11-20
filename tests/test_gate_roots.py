"""Regression: ensure_service allows the migrated ~/Projects root while
keeping root/symlink/secret confinement intact.

Scope guard (from the ask): minimal addition of the controlled Projects path;
never widen allow-root to $HOME or '/'; keep rejecting out-of-root projects
and symlink escapes. No business logic, data, token or config changes.
"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from context_gate import Config
from gate_service import DEFAULT_ALLOW_ROOTS, Engine


def body_for(root, memory):
    return {'root': str(root), 'memory': [str(memory)], 'request': 'task',
            'agent_id': 'a', 'session_id': 's', 'task_id': 't', 'platform': 'generic'}


class GateRootsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.home = self.base / 'home'
        (self.home / 'Documents' / 'proj').mkdir(parents=True)
        (self.home / 'Projects' / 'proj').mkdir(parents=True)
        self.docs_mem = self.home / 'Documents' / 'proj' / 'memory.md'
        self.docs_mem.write_text('doc')
        self.proj_mem = self.home / 'Projects' / 'proj' / 'memory.md'
        self.proj_mem.write_text('doc')
        self.engine = Engine([str(self.home / 'Documents'), str(self.home / 'Projects')],
                             Config(cache_dir=str(self.base / 'cache')),
                             state_dir=self.base / 'state')

    def test_documents_root_still_accepted(self):
        out = self.engine.validate(body_for(self.home / 'Documents' / 'proj', self.docs_mem))
        self.assertEqual((self.home / 'Documents' / 'proj').resolve(), out[0])

    def test_projects_root_now_accepted(self):
        out = self.engine.validate(body_for(self.home / 'Projects' / 'proj', self.proj_mem))
        self.assertEqual((self.home / 'Projects' / 'proj').resolve(), out[0])

    def test_home_itself_is_rejected_not_widened(self):
        home_mem = self.home / 'memory.md'
        home_mem.write_text('doc')
        with self.assertRaises(ValueError):
            self.engine.validate(body_for(self.home, home_mem))

    def test_sibling_outside_roots_is_rejected(self):
        other = self.base / 'other'
        other.mkdir()
        mem = other / 'memory.md'
        mem.write_text('doc')
        with self.assertRaises(ValueError):
            self.engine.validate(body_for(other, mem))

    def test_symlink_escape_is_rejected(self):
        outside = self.base / 'outside'
        outside.mkdir()
        secret = outside / 'memory.md'
        secret.write_text('doc')
        link = (self.home / 'Projects' / 'proj' / 'link.md')
        try:
            link.symlink_to(secret)
        except OSError:
            self.skipTest('symlinks not supported here')
        with self.assertRaises(ValueError):
            self.engine.validate(body_for(self.home / 'Projects' / 'proj', link))

    def test_credential_memory_still_rejected(self):
        creds = self.home / 'Projects' / 'proj' / 'credentials.json'
        creds.write_text('{}')
        with self.assertRaises(ValueError):
            self.engine.validate(body_for(self.home / 'Projects' / 'proj', creds))

    def test_default_roots_are_documents_and_projects_only(self):
        import gate_service
        roots = gate_service.DEFAULT_ALLOW_ROOTS
        self.assertEqual(2, len(roots))
        self.assertEqual(
            tuple(sorted(roots)),
            tuple(sorted((str(Path.home() / 'Documents'), str(Path.home() / 'Projects')))))
        self.assertNotIn(str(Path.home()), roots)
        self.assertNotIn('/', roots)

    def test_spawn_command_lists_both_roots_explicitly(self):
        seen = {}

        class FakePopen:
            def __init__(self, argv, **kwargs):
                seen['argv'] = argv

        import gate_service
        with tempfile.TemporaryDirectory() as state:
            directory = Path(state)
            (directory / 'connection.json').write_text('{}')
            with mock.patch.object(gate_service.subprocess, 'Popen', FakePopen), \
                 mock.patch('time.sleep', return_value=None):
                try:
                    gate_service.ensure_service(directory)
                except RuntimeError:
                    pass
        argv = seen.get('argv', [])
        self.assertIn('--allow-root', argv)
        idx = [i for i, a in enumerate(argv) if a == '--allow-root']
        self.assertEqual(2, len(idx))
        values = [argv[i + 1] for i in idx]
        self.assertIn(str(Path.home() / 'Documents'), values)
        self.assertIn(str(Path.home() / 'Projects'), values)
        self.assertNotIn(str(Path.home()), values)


if __name__ == '__main__':
    unittest.main()
