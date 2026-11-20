"""snapshot_cached: repeat console polls must not rescan the ledger unless the
underlying data version (DB counters, task files, logs) moves — and even then
the caller gets the previous snapshot immediately while one background thread
refreshes it (stale-while-revalidate), so no poll waits for the ~2s scan."""
import sqlite3, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

import console_data as cd


class SnapshotCacheTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.calls = []
        patcher = patch.object(cd, 'snapshot',
                               lambda state, period='all', platform='all', now=None, health=True,
                               model=None, day=None, cost_mode=None: self.calls.append((period, platform, model, day)) or
                               {'period': period, 'platform': platform, 'model': model, 'day': day,
                                'calls': len(self.calls)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_log(self):
        Path(self.folder.name, 'service.log').write_text('line-%d' % len(self.calls))

    def add_turn_row(self):
        db = Path(self.folder.name, 'tokens.sqlite3')
        with sqlite3.connect(db) as c:
            c.execute('CREATE TABLE IF NOT EXISTS turns (id INTEGER PRIMARY KEY, at REAL, platform TEXT)')
            c.execute("INSERT INTO turns (at, platform) VALUES (1, 'claude')")

    def wait_for_recompute(self, count, timeout=6.0):
        """模拟前端 10 秒级轮询：持续调用直到后台重算完成（免探测窗口过后触发）。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            cd.snapshot_cached(self.folder.name, 'all', 'all')
            if len(self.calls) >= count:
                return
            time.sleep(0.05)
        self.fail('等待第 %d 次后台重算超时' % count)

    def test_first_call_computes_and_repeat_returns_cache(self):
        first = cd.snapshot_cached(self.folder.name, 'all', 'all')
        self.assertEqual(len(self.calls), 1)
        second = cd.snapshot_cached(self.folder.name, 'all', 'all')
        self.assertEqual(first, second)
        self.assertEqual(len(self.calls), 1)

    def test_version_change_serves_stale_then_recomputes_in_background(self):
        stale = cd.snapshot_cached(self.folder.name, 'all', 'all')
        self.add_turn_row()
        served = cd.snapshot_cached(self.folder.name, 'all', 'all')
        self.assertEqual(served, stale)          # 旧数据立即返回，不阻塞
        self.assertEqual(len(self.calls), 1)
        self.wait_for_recompute(2)               # 后台完成重算
        fresh = cd.snapshot_cached(self.folder.name, 'all', 'all')
        self.assertEqual(fresh['calls'], 2)      # 下一轮拿到新数据

    def test_ttl_expiry_serves_stale_then_recomputes(self):
        cd.snapshot_cached(self.folder.name, 'all', 'all')
        with patch.object(cd, 'SNAPSHOT_TTL', 0), patch.object(cd, 'SNAPSHOT_PROBE_SKIP', 0):
            served = cd.snapshot_cached(self.folder.name, 'all', 'all')
            self.assertEqual(served['calls'], 1)
            self.wait_for_recompute(2)

    def test_probe_failure_still_converges_via_background_recompute(self):
        cd.snapshot_cached(self.folder.name, 'all', 'all')
        with patch.object(cd, '_stats_version', return_value=('probe-error', 1)):
            served = cd.snapshot_cached(self.folder.name, 'all', 'all')
            self.assertEqual(served['calls'], 1)
            self.wait_for_recompute(2)

    def test_distinct_params_are_cached_separately(self):
        cd.snapshot_cached(self.folder.name, 'all', 'all')
        cd.snapshot_cached(self.folder.name, 'week', 'all')
        self.assertEqual(len(self.calls), 2)
        cd.snapshot_cached(self.folder.name, 'all', 'all')
        cd.snapshot_cached(self.folder.name, 'week', 'all')
        self.assertEqual(len(self.calls), 2)


if __name__ == '__main__':
    unittest.main()
