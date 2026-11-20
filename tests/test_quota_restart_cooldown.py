"""Restart-time 429 backoff: fake readers and clock only; no network, no real accounts."""
import json
import tempfile
import unittest
from pathlib import Path
import console_quota as q

WINDOW = {'bucket': 'claude', 'window': 'five_hour', 'remaining': 50, 'resets_at': 99999}


class RestartCooldownTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        self.now = [100]
        self.account = {'claude': 'C', 'codex': 'X'}
        self.claude_reader = self.throttled
        self.managers = []

    def throttled(self):
        raise q.QuotaError('限流', 600)

    def make(self, claude_reader=None):
        manager = q.Quotas(self.dir,
            readers={'codex': lambda: [dict(WINDOW, bucket='codex')], 'claude': claude_reader or self.claude_reader},
            account_readers={'codex': lambda: self.account['codex'], 'claude': lambda: self.account['claude']},
            clock=lambda: self.now[0], notifier=lambda platform: False)
        self.addCleanup(manager.close)
        self.managers.append(manager)
        return manager

    def cooldown_file(self):
        return json.loads((self.dir/'quota-cooldown.json').read_text())

    def fail_once(self):
        first = self.make()
        first.refresh('claude')
        return first

    def test_failed_read_backoff_survives_restart(self):
        first = self.fail_once()
        next_at = first.states['claude']['next_at']
        second = self.make()
        state = second.states['claude']
        self.assertEqual(state['status'], 'error')
        self.assertEqual(state['failures'], 1)
        self.assertEqual(state['next_at'], next_at)
        self.assertEqual(state['account'], 'C')
        self.assertEqual(self.cooldown_file()['version'], 1)

    def test_expired_backoff_is_not_restored(self):
        first = self.fail_once()
        self.now[0] = first.states['claude']['next_at'] + 1
        second = self.make()
        self.assertEqual(second.states['claude']['status'], 'not_checked')
        self.assertIsNone(second.states['claude']['next_at'])

    def test_other_account_does_not_inherit_backoff(self):
        self.fail_once()
        self.account['claude'] = 'D'
        second = self.make()
        self.assertEqual(second.states['claude']['status'], 'not_checked')
        self.assertIsNone(second.states['claude']['next_at'])

    def test_successful_read_leaves_no_backoff_on_disk(self):
        self.fail_once()
        self.now[0] = 200  # past the restored manual-retry minute, before next_at (700)
        self.claude_reader = lambda: [dict(WINDOW)]
        ok = self.make()
        ok.refresh('claude')
        self.assertEqual(ok.states['claude']['status'], 'ok')
        self.assertEqual(self.cooldown_file()['platforms'], {})
        second = self.make()
        self.assertIsNone(second.states['claude']['next_at'])
        self.assertNotEqual(second.states['claude']['status'], 'error')

    def test_fresh_start_without_file_restores_nothing(self):
        second = self.make()
        self.assertIsNone(second.states['claude']['next_at'])
        self.assertFalse((self.dir/'quota-cooldown.json').exists())

    def test_corrupt_file_is_ignored(self):
        (self.dir/'quota-cooldown.json').write_text('not json')
        second = self.make()
        self.assertEqual(second.states['claude']['status'], 'not_checked')
        self.assertIsNone(second.states['claude']['next_at'])

    def test_account_switch_clears_disk_entry(self):
        first = self.fail_once()
        self.assertIn('claude', self.cooldown_file()['platforms'])
        self.account['claude'] = 'D'
        first.snapshot()
        self.assertNotIn('claude', self.cooldown_file()['platforms'])

    def test_validate_raises_claude_interval_floor_only(self):
        data = {p: dict(q.DEFAULT) for p in q.PLATFORMS}
        data['claude']['interval'] = 5
        data['codex']['interval'] = 5
        out = q.Quotas.validate(data)
        self.assertEqual(out['claude']['interval'], 60)
        self.assertEqual(out['codex']['interval'], 5)
        data['claude']['interval'] = 300
        self.assertEqual(q.Quotas.validate(data)['claude']['interval'], 300)


if __name__ == '__main__':
    unittest.main()
