import json,tempfile,threading,time,unittest
from pathlib import Path
from unittest.mock import patch
import console_quota as q
import console_quota_stop as stop
import console_quota_ipc as ipc_module
import os,stat

WINDOW={'bucket':'test','window':'five_hour','remaining':1,'resets_at':99999}

class BackendRevisionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        self.account=['account-a'];self.clock=[100];self.stops=[];self.notices=[]
        self.manager=q.Quotas(self.folder.name,readers={'codex':lambda:{'account':self.account[0],'windows':[dict(WINDOW)]},'claude':lambda:{'account':'claude','windows':[dict(WINDOW,remaining=80)]}},
            account_readers={'codex':lambda:self.account[0],'claude':lambda:'claude'},clock=lambda:self.clock[0],
            stop_handler=lambda p:self.stops.append(p) or {'ok':True},notifier=lambda p:self.notices.append(p) or True)
        prefs=self.manager.settings();prefs['codex'].update(stop_all=True);self.manager.settings(prefs)
        self.addCleanup(self.manager.close)

    def queued(self):
        self.manager.action_thread=threading.Thread()  # mark service mode, do not run actions yet
        self.manager.refresh('codex')
        return self.manager.actions.pop('codex')

    def test_queued_old_account_and_aba_actions_are_discarded(self):
        action=self.queued();self.account[0]='account-b';self.manager.snapshot()
        self.account[0]='account-a';self.manager.snapshot()
        self.manager._act('codex',action)
        self.assertEqual(self.stops,[]);self.assertEqual(self.notices,[])
        self.manager.action_thread=None

    def test_settings_disable_and_recovery_discard_queued_actions(self):
        action=self.queued();prefs=self.manager.settings();prefs['codex'].update(stop_all=False,notify=False);self.manager.settings(prefs)
        self.manager._act('codex',action);self.assertEqual(self.stops,[]);self.assertEqual(self.notices,[])
        self.manager.action_thread=None

    def test_quota_recovery_discards_queued_actions(self):
        action=self.queued();self.manager.states['codex']['windows'][0]['remaining']=80
        self.manager._act('codex',action);self.assertEqual(self.stops,[]);self.assertEqual(self.notices,[])
        self.manager.action_thread=None

    def test_slow_stop_does_not_delay_other_platform_and_d10(self):
        entered=threading.Event();release=threading.Event();read=threading.Event();outside=[]
        class Protection:
            def snapshot(*args):return {p:{'status':'idle'} for p in q.PLATFORMS}
            def reconcile(*args,**kwargs): pass
            def pause(inner,payload):
                acquired=[]
                def take():
                    ok=self.manager.lock.acquire(timeout=.5);acquired.append(ok)
                    if ok:self.manager.lock.release()
                t=threading.Thread(target=take);t.start();t.join(1);outside.extend(acquired)
                entered.set();release.wait(2);return {'ok':True}
        self.manager.protection=Protection()
        self.manager.readers['claude']=lambda:read.set() or {'account':'claude','windows':[dict(WINDOW,remaining=80)]}
        self.manager.start()
        self.manager.request('codex');self.assertTrue(entered.wait(1))
        self.manager.request('claude');self.assertTrue(read.wait(.5));self.assertEqual(outside,[True])
        release.set();self.manager.close()

    def test_slow_stop_old_result_does_not_write_new_account(self):
        entered=threading.Event();release=threading.Event()
        self.manager.stop_handler=lambda p:entered.set() or release.wait(2) or {'old':True}
        action=self.queued();t=threading.Thread(target=self.manager._act,args=('codex',action));t.start()
        self.assertTrue(entered.wait(1));self.account[0]='account-b';self.manager.snapshot()
        release.set();t.join(2)
        self.assertIsNone(self.manager.states['codex']['stop_result']);self.assertEqual(self.notices,[])
        self.manager.action_thread=None

    def test_close_discards_pending_action(self):
        action=self.queued();self.manager.closed.set();self.manager._act('codex',action)
        self.assertEqual(self.stops,[]);self.assertEqual(self.notices,[]);self.manager.action_thread=None

    def test_notification_persists_but_stop_retries_after_restart(self):
        self.manager.refresh('codex');self.assertEqual(len(self.notices),1)
        other=q.Quotas(self.folder.name,readers=self.manager.readers,account_readers=self.manager.account_readers,
                       clock=lambda:140,stop_handler=lambda p:self.stops.append(p),notifier=lambda p:self.notices.append(p) or True)
        other.refresh('codex');self.assertEqual(len(self.notices),1);self.assertEqual(len(self.stops),2)
        self.assertEqual(other.notice_path.stat().st_mode & 0o777,0o600)

    def test_unsent_notification_retries_and_healthy_read_clears_disk_dedupe(self):
        self.manager.notifier=lambda p:False;self.manager.refresh('codex');self.assertEqual(self.manager.notify_seen['codex'],set())
        self.clock[0]=110;self.manager.notifier=lambda p:self.notices.append(p) or True;self.manager.refresh('codex')
        self.clock[0]=120;self.manager.readers['codex']=lambda:{'account':self.account[0],'windows':[dict(WINDOW,remaining=80)]};self.manager.refresh('codex')
        self.assertEqual(json.loads(self.manager.notice_path.read_text())['codex'],[])

    def test_transient_account_absence_retries_but_logout_clears(self):
        self.manager.refresh('codex');calls=iter([None,'account-a'])
        self.manager.account_readers['codex']=lambda:next(calls)
        self.assertEqual(self.manager.snapshot()['platforms']['codex']['status'],'ok')
        self.manager.account_readers['codex']=lambda:None
        self.assertEqual(self.manager.snapshot()['platforms']['codex']['windows'],[])

    def test_old_reader_after_observed_aba_switch_cannot_publish(self):
        entered=threading.Event();release=threading.Event()
        def reader():
            entered.set();release.wait(2)
            return {'account':'account-a','windows':[dict(WINDOW)]}
        self.manager.readers['codex']=reader
        t=threading.Thread(target=self.manager.refresh,args=('codex',));t.start()
        self.assertTrue(entered.wait(1))
        self.account[0]='account-b';self.manager.snapshot()
        self.account[0]='account-a';self.manager.snapshot()
        release.set();t.join(2)
        self.assertEqual(self.manager.states['codex']['windows'],[])
        self.assertIsNone(self.manager.states['codex']['checked_at'])
        self.assertEqual(self.stops,[]);self.assertEqual(self.notices,[])

    def test_transient_account_exception_retries(self):
        self.manager.refresh('codex')
        with patch.dict(self.manager.account_readers,{'codex':unittest.mock.Mock(side_effect=[OSError('rewrite'), 'account-a'])}):
            self.assertEqual(self.manager.snapshot()['platforms']['codex']['status'],'ok')

    def test_unknown_account_notification_also_restores_after_restart(self):
        for manager in (self.manager,):
            manager.account_readers['codex']=lambda:None
            manager.readers['codex']=lambda:{'account':None,'windows':[dict(WINDOW)]}
        self.manager.refresh('codex')
        other=q.Quotas(self.folder.name,readers=self.manager.readers,account_readers=self.manager.account_readers,
                       clock=lambda:140,notifier=lambda p:self.notices.append(p) or True)
        other.refresh('codex');self.assertEqual(len(self.notices),1)

    def test_ipc_initialization_failure_closes_socket(self):
        owner=os.getuid()
        sock_stat=type('Stat',(),{'st_uid':owner,'st_mode':stat.S_IFSOCK|0o600})()
        dir_stat=type('Stat',(),{'st_uid':owner,'st_mode':stat.S_IFDIR|0o700})()
        for failure in ('connect','initialize','schema'):
            connection=unittest.mock.Mock()
            if failure=='connect':connection.connect.side_effect=OSError('synthetic connection error')
            with patch.object(Path,'lstat',return_value=sock_stat),patch.object(Path,'stat',return_value=dir_stat),patch.object(ipc_module.socket,'socket',return_value=connection),patch.object(ipc_module.DesktopIPC,'request',side_effect=TimeoutError('synthetic init') if failure=='initialize' else None,return_value={}):
                with self.assertRaises((OSError,KeyError)):
                    ipc_module.DesktopIPC('/synthetic/ipc.sock')
            connection.close.assert_called_once()

    def test_usage_sync_missing_never_infers_completion_from_import_marker(self):
        Path(self.folder.name,'usage-import-state.json').write_text('{}')
        self.assertEqual(self.manager.snapshot()['usage_sync'],{})

    def test_usage_sync_normal_metadata_is_whitelisted(self):
        data={'last_started':100.5,'last_completed':102,'next_due':400.5,'imported':3,'skipped':2,'error':None,'secret':'not returned'}
        Path(self.folder.name,'usage-import-status.json').write_text(json.dumps(data))
        expected=dict(data);expected.pop('secret')
        self.assertEqual(self.manager.snapshot()['usage_sync'],expected)
        data['last_completed']=None;data['error']='database_busy'
        Path(self.folder.name,'usage-import-status.json').write_text(json.dumps(data))
        expected['last_completed']=None;expected['error']='database_busy'
        self.assertEqual(self.manager.snapshot()['usage_sync'],expected)

    def test_usage_sync_first_running_and_failed_attempt_preserves_metadata(self):
        path=Path(self.folder.name,'usage-import-status.json')
        data={'last_started':100,'last_completed':None,'imported':None,'skipped':None,'error':None,'next_due':400}
        path.write_text(json.dumps(data))
        self.assertEqual(self.manager.snapshot()['usage_sync'],data)
        data['error']='io_error';path.write_text(json.dumps(data))
        self.assertEqual(self.manager.snapshot()['usage_sync'],data)

    def test_usage_sync_malformed_values_do_not_leak_or_invent_status(self):
        path=Path(self.folder.name,'usage-import-status.json')
        for data in ('broken','[]','{"error":"raw secret error"}','{"last_started":NaN}','{"last_completed":-1}','{"next_due":true}','{"imported":1.5}','{"skipped":false}','{"imported":-1}'):
            path.write_text(data)
            self.assertEqual(self.manager.snapshot()['usage_sync'],{})
        path.write_text(' '*5000)
        self.assertEqual(self.manager.snapshot()['usage_sync'],{})

    def test_parallel_discovery_owns_and_closes_independent_sockets(self):
        connections=[];lock=threading.Lock();active=[0];maximum=[0]
        class IPC:
            def __init__(inner,*args,**kwargs):inner.closed=False;connections.append(inner)
            def close(inner):inner.closed=True
        def inspect(ipc,thread):
            with lock:active[0]+=1;maximum[0]=max(maximum[0],active[0])
            time.sleep(.03)
            with lock:active[0]-=1
            return {'thread':thread,'owner':None,'reason':'no-client-found'}
        with patch.object(stop,'build_supported',return_value=True),patch.object(stop,'DesktopIPC',IPC),patch.object(stop,'thread_inventory',return_value=[(str(i),i) for i in range(8)]),patch.object(stop,'inspect_thread',side_effect=inspect):
            result=stop.discover_codex(database='revision-parallel',budget=1)
        self.assertEqual(maximum[0],4);self.assertEqual(len(connections),9);self.assertTrue(all(x.closed for x in connections));self.assertTrue(result['covered'])

    def test_budget_stops_new_batches_and_inflight_connections_close(self):
        connections=[]
        class IPC:
            def __init__(inner,*args,**kwargs):inner.closed=False;connections.append(inner)
            def close(inner):inner.closed=True
        def inspect(ipc,thread):
            time.sleep(.03);return {'thread':thread,'owner':None,'reason':'no-client-found'}
        with patch.object(stop,'build_supported',return_value=True),patch.object(stop,'DesktopIPC',IPC),patch.object(stop,'thread_inventory',return_value=[(str(i),i) for i in range(12)]),patch.object(stop,'inspect_thread',side_effect=inspect):
            result=stop.discover_codex(database='revision-budget',budget=.01)
        self.assertEqual(len(connections),5);self.assertTrue(all(x.closed for x in connections));self.assertFalse(result['covered'])
