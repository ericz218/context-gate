import tempfile
import unittest
from pathlib import Path

from gate_run import command


class CodexCommandTests(unittest.TestCase):
    def test_explicit_model_and_reasoning_override_are_sent_to_codex(self):
        with tempfile.TemporaryDirectory() as folder:
            prompt = Path(folder) / 'prompt.txt'
            prompt.write_text('Read-only task', encoding='utf-8')
            argv, _, stdin = command('codex', folder, prompt,
                                     model='gpt-6-sol', reasoning_effort='low')
            self.assertIn('--model', argv)
            self.assertEqual(argv[argv.index('--model') + 1], 'gpt-6-sol')
            self.assertIn('model_reasoning_effort="low"', argv)
            self.assertEqual(stdin, 'Read-only task')

    def test_reasoning_override_is_not_silently_ignored_by_other_clients(self):
        with self.assertRaises(ValueError):
            command('claude', '/tmp', Path('/tmp/missing-prompt'),
                    reasoning_effort='low')

    def test_additional_project_writes_are_explicit_native_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            prompt = Path(folder) / 'prompt.txt'
            prompt.write_text('Implement task', encoding='utf-8')
            argv, _, _ = command('codex', folder, prompt, additional_dirs=['/tmp/project'])
            self.assertEqual(argv[argv.index('--add-dir') + 1], '/tmp/project')

    def test_additional_writes_are_not_silently_ignored_by_other_clients(self):
        with self.assertRaises(ValueError):
            command('claude', '/tmp', Path('/tmp/missing-prompt'), additional_dirs=['/tmp/project'])

    def test_memory_context_approval_is_explicit_and_scoped(self):
        with tempfile.TemporaryDirectory() as folder:
            prompt = Path(folder) / 'prompt.txt'
            prompt.write_text('Read task', encoding='utf-8')
            default, _, text = command('codex', folder, prompt)
            self.assertFalse(any('approval_mode' in arg for arg in default))
            self.assertEqual(text, 'Read task')
            approved, _, text = command('codex', folder, prompt, memory_context_approved=True)
            self.assertIn('mcp_servers.memory-os.tools.memory_get_context.approval_mode="approve"', approved)
            self.assertIn('mcp_servers.memory-os.required=true', approved)
            self.assertEqual(approved[approved.index('--sandbox') + 1], 'workspace-write')
            self.assertIn('[REQUIRED_STARTUP]', text)
            self.assertIn('max_bytes=4096', text)
            self.assertIn('max_bytes=262144', text)
            self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', approved)
        with self.assertRaises(ValueError):
            command('claude', '/tmp', Path('/tmp/missing'), memory_context_approved=True)
