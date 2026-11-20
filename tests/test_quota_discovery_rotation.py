"""No-owner discovery cache: sweeps stay newest-first, budget-limited sweeps still
reach old threads across calls (the cache itself acts as the cursor), and the app's
explicit no-client-found answer is coverage; App timeout remains uncovered.

A discovery timeout without an answer (client-side TimeoutError) stays an
uncovered error, cached only briefly so it is retried; owned threads are never
cached, so a newly started turn is found on the very next sweep.
"""
import unittest
from unittest.mock import patch
import console_quota_stop as q


class IPC:
    def __init__(self, *args, **kwargs):
        pass

    def close(self):
        pass


def idle_snapshot(thread):
    return {'thread': thread, 'owner': 'owner', 'runtime': {'type': 'idle'}, 'turns': []}


class NoOwnerCacheTests(unittest.TestCase):
    def setUp(self):
        q._noowner_cache.clear()

    def sweep(self, inventory, inspect, budget=10, clock=None, wall=None):
        clock = clock if clock is not None else [0]
        wall = wall if wall is not None else [1000.0]
        with patch.object(q, 'build_supported', return_value=True), \
             patch.object(q, 'DesktopIPC', IPC), \
             patch.object(q, 'thread_inventory', return_value=inventory), \
             patch.object(q, 'inspect_thread', side_effect=inspect), \
             patch.object(q, 'stop_codex_thread', side_effect=lambda ipc, s, enabled: {'state': 'idle'}), \
             patch.object(q.time, 'monotonic', side_effect=lambda: clock[0]), \
             patch.object(q.time, 'time', side_effect=lambda: wall[0]):
            return q.discover_codex(database='synthetic', budget=budget, workers=1)

    def test_budget_limited_sweeps_reach_old_threads_across_calls(self):
        visited = []
        clock = [0]

        def inspect(ipc, thread):
            clock[0] += 1  # one probe eats one budget unit; cache hits are free
            visited.append(thread)
            return {'thread': thread, 'owner': None, 'reason': 'no-client-found'}

        inventory = [('new', 50), ('middle', 30), ('old', 10)]
        first = self.sweep(inventory, inspect, budget=1, clock=clock)
        self.assertEqual(visited, ['new'])
        self.assertFalse(first['discovery_complete'])
        clock[0] = 0
        second = self.sweep(inventory, inspect, budget=1, clock=clock)
        self.assertEqual(visited, ['new', 'middle'])
        self.assertEqual(second['cached_noowner'], 1)
        clock[0] = 0
        third = self.sweep(inventory, inspect, budget=1, clock=clock)
        self.assertEqual(visited, ['new', 'middle', 'old'])
        self.assertEqual(third['cached_noowner'], 2)
        self.assertTrue(third['discovery_complete'])
        self.assertTrue(third['covered'])
        self.assertEqual(third['errors'], [])

    def test_new_thread_event_reprobes_despite_fresh_cache(self):
        visited = []

        def inspect(ipc, thread):
            visited.append(thread)
            return {'thread': thread, 'owner': None, 'reason': 'timeout'}

        inventory = [('new', 50), ('old', 10)]
        self.sweep(inventory, inspect)
        self.assertEqual(visited, ['new', 'old'])
        # a new event in 'new' bumps updated_at: the cached answer no longer applies
        inventory = [('new', 90), ('old', 10)]
        self.sweep(inventory, inspect)
        self.assertEqual(visited, ['new', 'old', 'new'])

    def test_app_answered_timeout_is_ambiguous_not_unowned_coverage(self):
        def inspect(ipc, thread):
            return {'thread': thread, 'owner': None, 'reason': 'timeout'}

        result = self.sweep([('a', 1), ('b', 2)], inspect)
        self.assertEqual(len(result['errors']), 2)
        self.assertFalse(result['discovery_complete'])
        self.assertFalse(result['covered'])
        self.assertTrue(all(not q._noowner_cache['synthetic'][t][2] for t in ('a', 'b')))

    def test_discovery_timeout_stays_uncovered_and_is_retried_after_short_ttl(self):
        def inspect(ipc, thread):
            raise TimeoutError('synthetic timeout')

        inventory = [('a', 1)]
        first = self.sweep(inventory, inspect)
        self.assertFalse(first['covered'])
        self.assertEqual(first['errors'][0]['reason'], 'TimeoutError')
        # inside the short TTL the thread is skipped instead of re-probed, but the
        # skipped ambiguity keeps the sweep's coverage honestly incomplete
        second = self.sweep(inventory, inspect, wall=[1100.0])
        self.assertEqual(second['cached_noowner'], 1)
        self.assertEqual(second['errors'], [])
        self.assertFalse(second['covered'])
        # after the ambiguous TTL the thread is probed and reported again
        third = self.sweep(inventory, inspect, wall=[1400.0])
        self.assertEqual(third['errors'][0]['reason'], 'TimeoutError')
        self.assertFalse(third['covered'])

    def test_owned_threads_are_never_cached_and_reprobed_every_sweep(self):
        visited = []

        def inspect(ipc, thread):
            visited.append(thread)
            if thread == 'live':
                return idle_snapshot(thread)
            return {'thread': thread, 'owner': None, 'reason': 'no-client-found'}

        inventory = [('live', 5), ('dead', 3)]
        self.sweep(inventory, inspect)
        self.sweep(inventory, inspect)
        self.assertEqual(visited, ['live', 'dead', 'live'])
        self.assertNotIn('live', q._noowner_cache['synthetic'])

    def test_deleted_threads_are_pruned_from_the_cache(self):
        def inspect(ipc, thread):
            return {'thread': thread, 'owner': None, 'reason': 'no-client-found'}

        self.sweep([('a', 1), ('b', 2)], inspect)
        self.assertIn('b', q._noowner_cache['synthetic'])
        self.sweep([('a', 1)], inspect)
        self.assertNotIn('b', q._noowner_cache['synthetic'])
