"""No real accounts, native stop adapters, credentials or quota settings."""
import tempfile
import threading
import unittest
from pathlib import Path
import console_quota as q

WINDOW = {'bucket': 'test', 'window': 'five_hour', 'remaining': 1, 'resets_at': 99999}

class AccountSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.account = ['A']
        self.now = [100]
        self.pauses = []
        self.manager = q.Quotas(self.temp.name,
            readers={'codex': lambda: {'account': self.account[0], 'windows': [dict(WINDOW)]}, 'claude': lambda: []},
            account_readers={'codex': lambda: self.account[0], 'claude': lambda: 'C'},
            clock=lambda: self.now[0], stop_handler=lambda platform: self.pauses.append(self.account[0]) or {'ok': True},
            notifier=lambda platform: False)
        self.addCleanup(self.manager.close)
        self.manager.prefs['codex'].update(enabled=True, stop_all=True, interval=300)
        self.manager.prefs['claude']['enabled'] = False

    def test_new_low_account_does_not_inherit_success_cooldown_or_stop_retry(self):
        self.manager.refresh('codex')
        self.account[0] = 'B'
        self.manager.refresh('codex')  # same clock, no GET snapshot
        self.assertEqual(self.pauses, ['A', 'B'])
        self.assertEqual(self.manager.states['codex']['account'], 'B')

    def test_new_account_does_not_inherit_old_429_backoff(self):
        self.manager.refresh('codex')
        self.manager.states['codex'].update(status='error', retry_at=160, next_at=1900)
        self.account[0] = 'B'
        self.manager.refresh('codex')
        self.assertEqual(self.pauses, ['A', 'B'])

    def test_background_run_observes_switch_without_open_quota_page(self):
        self.manager.refresh('codex')
        self.manager.states['codex'].update(retry_at=160, next_at=1900)
        self.account[0] = 'B'
        def stop(platform):
            self.pauses.append(self.account[0]); self.manager.closed.set()
            return {'ok': True}
        self.manager.stop_handler = stop
        worker = threading.Thread(target=self.manager.run, daemon=True)
        worker.start()
        worker.join(.3)
        self.manager.closed.set(); self.manager.wake.set(); worker.join(1)
        self.assertEqual(self.pauses, ['A', 'B'])

    def test_repeated_switches_immediately_stop_each_low_account(self):
        for account in ['A', 'B', 'A', 'B']:
            self.account[0] = account
            self.manager.refresh('codex')
        self.assertEqual(self.pauses, ['A', 'B', 'A', 'B'])

    def test_reconcile_does_not_use_old_healthy_account_after_switch(self):
        self.manager.refresh('codex')
        self.manager.states['codex']['windows'][0]['remaining'] = 80
        observed = []
        class Protection:
            def reconcile(inner, states, prefs, live=None):
                observed.append((states['codex']['account'], states['codex']['status']))
                self.account[0] = 'A'  # switch again at the commit boundary
                updated, _ = live()
                observed.append((updated['codex']['account'], updated['codex']['status']))
        self.manager.protection = Protection()
        self.account[0] = 'B'
        self.manager._reconcile_now()
        self.assertEqual(observed, [('B', 'not_checked'), ('A', 'not_checked')])

    def test_late_old_read_cannot_publish_new_account_or_stale_stop(self):
        entered = threading.Event(); release = threading.Event()
        def old():
            entered.set(); release.wait(1)
            return {'account': 'A', 'windows': [dict(WINDOW)]}
        self.manager.readers['codex'] = old
        worker = threading.Thread(target=self.manager.refresh, args=('codex',))
        worker.start(); self.assertTrue(entered.wait(.3))
        self.account[0] = 'B'
        self.manager.request('codex')
        release.set(); worker.join(1)
        self.assertEqual(self.pauses, [])
        self.assertEqual(self.manager.states['codex']['account'], 'B')
        self.assertEqual(self.manager.states['codex']['windows'], [])
        self.manager.readers['codex'] = lambda: {'account': 'B', 'windows': [dict(WINDOW)]}
        self.manager.refresh('codex')
        self.assertEqual(self.pauses, ['B'])

if __name__ == '__main__': unittest.main()
