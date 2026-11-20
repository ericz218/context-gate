import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import console_quota as q


class NoticeRoutingTests(unittest.TestCase):
    def run_with(self, app_exists, app_code):
        calls=[]
        def fake_run(command, **kwargs):
            calls.append(command)
            return type('R',(),{'returncode':app_code if command[0]!='/usr/bin/osascript' else 0})()
        with tempfile.TemporaryDirectory() as tmp:
            app=Path(tmp)/'ContextGateConsole'
            if app_exists: app.write_text('')
            with patch.object(q,'CONSOLE_APP',app), patch.object(q.subprocess,'run',fake_run):
                sent=q.post_notice('codex')
        return sent,[('app' if c[0]!='/usr/bin/osascript' else 'osascript',c[1:]) for c in calls]

    def test_resident_app_takes_the_alert_without_applescript(self):
        sent,calls=self.run_with(True,0)
        self.assertTrue(sent); self.assertEqual(calls,[('app',['--notify','codex'])])

    def test_no_resident_instance_or_missing_app_falls_back_to_applescript(self):
        sent,calls=self.run_with(True,2)
        self.assertTrue(sent); self.assertEqual([c[0] for c in calls],['app','osascript'])
        sent,calls=self.run_with(False,0)
        self.assertTrue(sent); self.assertEqual([c[0] for c in calls],['osascript'])

    def test_unknown_platform_sends_nothing(self):
        with patch.object(q.subprocess,'run') as run:
            self.assertFalse(q.post_notice('other')); run.assert_not_called()

    def test_page_switches_are_single_click_toggles_and_native_notice_bridge_exists(self):
        from console import quota_ui
        for ident in ('quota-log-platform','quota-log-tier'):
            self.assertIn('class="modetog" id="'+ident+'" role="switch"',quota_ui.HTML)
        self.assertNotIn('quota-seg',quota_ui.HTML)
        self.assertIn("quotaToggle('quota-log-platform','platform'",quota_ui.JS)
        self.assertIn('messageHandlers.notify',quota_ui.JS)
        shell=(Path(q.__file__).parent/'console/app_bundle/main.swift').read_text()
        for needle in ('name: "notify"','requestAuthorization','Notifications-Settings.extension','"--notify"'):
            self.assertIn(needle,shell)


class QuotaTests(unittest.TestCase):
    def test_missing_and_zero_are_distinct(self):
        self.assertIsNone(q.percent(None)); self.assertEqual(q.percent(100),0)
        self.assertIsNone(q.percent(float('nan'))); self.assertIsNone(q.percent(True))
        self.assertEqual(q.parse_claude({'five_hour':{'utilization':10,'resets_at':'2026-10-12T20:00:00Z'}})[0]['remaining'],90)
        self.assertEqual(q.parse_claude({'seven_day':None}),[])
        self.assertIsNone(q.reset_time('2026-10-12T20:00:00'))

    def test_all_codex_buckets_and_duration(self):
        data={'rateLimitsByLimitId':{'a':{'primary':{'usedPercent':103,'windowDurationMins':300},'secondary':{'usedPercent':25,'windowDurationMins':10080}},'b':{'primary':{'usedPercent':None,'windowDurationMins':300}}},'rateLimits':{'primary':{'usedPercent':1,'windowDurationMins':300}}}
        windows=q.parse_codex(data)
        self.assertEqual(len(windows),3); self.assertEqual(windows[0]['remaining'],0)
        self.assertIsNone(windows[2]['remaining']); self.assertEqual(windows[1]['window'],'weekly')

    def test_validation_rejects_credentials_and_bad_numbers(self):
        prefs={p:dict(q.DEFAULT) for p in q.PLATFORMS}
        for val in (0,101,float('nan'),True,'12'):
            bad=json.loads(json.dumps(prefs));bad['claude']['weekly_threshold']=val
            with self.assertRaises(ValueError):q.Quotas.validate(bad)
        bad=json.loads(json.dumps(prefs));bad['claude']['token']='secret'
        with self.assertRaises(ValueError):q.Quotas.validate(bad)
        self.assertEqual(q.INTERVALS,(5,15,30,60,180,300,600,1800))

    def test_settings_permissions_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            manager=q.Quotas(folder); prefs=manager.settings();prefs['claude']['enabled']=True
            manager.settings(prefs)
            self.assertEqual(manager.path.stat().st_mode & 0o777,0o600)
            self.assertEqual(q.Quotas(folder).settings(),prefs)

    def test_backoff_preserves_stale_data_and_manual_cooldown(self):
        clock=[100];calls=[]
        def reader():
            calls.append(1)
            if len(calls)>1:raise q.QuotaError('rate limited',120)
            return [{'window':'five_hour','remaining':20,'resets_at':500,'bucket':'a'}]
        with tempfile.TemporaryDirectory() as folder:
            m=q.Quotas(folder,readers={'codex':reader,'claude':reader},clock=lambda:clock[0])
            m.refresh('codex'); clock[0]=160;m.refresh('codex')
            state=m.snapshot()['platforms']['codex']
            self.assertEqual(state['status'],'error');self.assertEqual(state['updated_at'],100)
            self.assertEqual(state['next_at'],280);self.assertEqual(state['windows'][0]['remaining'],20)
            m.request('codex');self.assertNotIn('codex',m.pending)

    def test_no_concurrent_refresh_and_stop_independent_of_notify(self):
        entered=threading.Event();finish=threading.Event();calls=[];stops=[]
        def reader():
            calls.append(1);entered.set();finish.wait(1)
            return [{'window':'weekly','remaining':1,'resets_at':500,'bucket':'a'}]
        with tempfile.TemporaryDirectory() as folder:
            m=q.Quotas(folder,readers={'codex':reader},stop_handler=lambda p:stops.append(p) or {'ok':False,'error':'uncovered'})
            prefs=m.settings();prefs['codex'].update(stop_all=True,notify=False);m.settings(prefs)
            t=threading.Thread(target=m.refresh,args=('codex',));t.start();entered.wait(1)
            m.refresh('codex');m.request('codex');self.assertNotIn('codex',m.pending)
            finish.set();t.join()
            self.assertEqual(len(calls),1);self.assertEqual(stops,['codex'])
            self.assertFalse(m.snapshot()['platforms']['codex']['stop_result']['ok'])

    def test_stop_precedes_blocked_notification_at_threshold(self):
        notified=threading.Event(); release=threading.Event(); stopped=threading.Event()
        def notice(platform):
            notified.set(); release.wait(2); return True
        with tempfile.TemporaryDirectory() as folder:
            m=q.Quotas(folder, readers={'codex':lambda:[{'bucket':'codex','window':'five_hour','remaining':2,'resets_at':500}]},
                       account_readers={'codex':lambda:'synthetic@test','claude':lambda:None},
                       notifier=notice, stop_handler=lambda p:stopped.set() or {'ok':True})
            prefs=m.settings();prefs['codex'].update(stop_all=True,five_hour_threshold=2);m.settings(prefs)
            thread=threading.Thread(target=m.refresh,args=('codex',));thread.start()
            try:
                self.assertTrue(notified.wait(1))
                self.assertTrue(stopped.is_set())
                self.assertIsNotNone(m.states['codex']['stop_result'])
            finally:
                release.set();thread.join(3)

    def test_stop_retries_low_new_turns_and_notifications_deduplicate(self):
        clock=[100];reset=[500];stops=[]
        def reader():return [{'window':'weekly','remaining':1,'resets_at':reset[0],'bucket':'a'}]
        with tempfile.TemporaryDirectory() as folder:
            m=q.Quotas(folder,readers={'codex':reader},clock=lambda:clock[0],notifier=lambda p:True,stop_handler=lambda p:stops.append(p) or {'ok':False,'error':'uncovered'})
            prefs=m.settings();prefs['codex']['stop_all']=True;m.settings(prefs)
            m.refresh('codex');clock[0]=110;m.refresh('codex')
            self.assertEqual(stops,['codex'])
            clock[0]=140;m.refresh('codex');self.assertEqual(stops,['codex','codex'])
            reset[0]=600;clock[0]=200;m.refresh('codex');self.assertEqual(stops,['codex','codex','codex'])

    def test_controller_exception_does_not_hide_successful_quota(self):
        def stop(p):raise RuntimeError('secret detail')
        def reader():return [{'window':'weekly','remaining':1,'resets_at':500,'bucket':'a'}]
        with tempfile.TemporaryDirectory() as folder:
            m=q.Quotas(folder,readers={'codex':reader},stop_handler=stop,notifier=lambda p:True)
            prefs=m.settings();prefs['codex']['stop_all']=True;m.settings(prefs);m.refresh('codex')
            state=m.snapshot()['platforms']['codex']
            self.assertEqual(state['status'],'ok');self.assertFalse(state['stop_result']['ok'])
            self.assertNotIn('secret',json.dumps(state))

    def test_background_notification_once_and_without_auto_stop(self):
        clock=[100];reset=[500];notices=[]
        def reader():return [{'window':'weekly','remaining':1,'resets_at':reset[0],'bucket':'a'}, {'window':'five_hour','remaining':1,'resets_at':reset[0],'bucket':'a'}]
        with tempfile.TemporaryDirectory() as folder:
            m=q.Quotas(folder,readers={'codex':reader},clock=lambda:clock[0],notifier=lambda p:notices.append(p) or True)
            m.refresh('codex');clock[0]=160;m.refresh('codex');self.assertEqual(notices,['codex'])
            reset[0]=600;clock[0]=220;m.refresh('codex');self.assertEqual(notices,['codex','codex'])
            self.assertIsNone(m.snapshot()['platforms']['codex']['stop_result'])

    def test_no_redirect(self):
        self.assertIsNone(q.NoRedirect().redirect_request(None,None,None,None,None))

    def test_claude_401_does_not_return_token(self):
        proc=type('P',(),{'returncode':0,'stdout':b'{"claudeAiOauth":{"accessToken":"SECRET"}}'})()
        with patch.object(q.subprocess,'run',return_value=proc),patch.object(q.urllib.request,'build_opener') as opener:
            opener.return_value.open.side_effect=q.urllib.error.HTTPError('u',401,'no',{},None)
            with self.assertRaises(q.QuotaError) as e:q.read_claude()
            self.assertNotIn('SECRET',str(e.exception));self.assertIn('登录已过期',str(e.exception))

    def test_huge_retry_after_caps_auto_backoff_and_manual_cooldown(self):
        # A day-long Retry-After used to freeze the card for a day and disable the
        # manual button for the whole backoff window.
        clock=[100.0];calls=[]
        def reader():
            calls.append(1)
            if len(calls)>1:raise q.QuotaError('rate limited',86400)
            return [{'window':'five_hour','remaining':20,'resets_at':500,'bucket':'a'}]
        with tempfile.TemporaryDirectory() as folder:
            m=q.Quotas(folder,readers={'codex':reader,'claude':reader},clock=lambda:clock[0])
            m.refresh('codex');clock[0]=160;m.refresh('codex')
            state=m.snapshot()['platforms']['codex']
            self.assertEqual(state['status'],'error')
            self.assertEqual(state['next_at'],160+1800)
            self.assertEqual(state['retry_at'],160+60)
            clock[0]=220;m.request('codex');self.assertIn('codex',m.pending)

    def test_restart_restores_recent_attributed_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            first=q.Quotas(folder,readers={'codex':lambda:[{'bucket':'codex','window':'five_hour','remaining':42,'resets_at':1500}]},
                           account_readers={'codex':lambda:'a@codex.test','claude':lambda:None},clock=lambda:1000.0)
            first.refresh('codex')
            second=q.Quotas(folder,account_readers={'codex':lambda:'a@codex.test','claude':lambda:None},clock=lambda:1100.0)
            state=second.snapshot()['platforms']['codex']
            self.assertEqual(state['status'],'ok')
            self.assertEqual(state['windows'][0]['remaining'],42)
            self.assertEqual(state['account'],'a@codex.test')
            self.assertIsNone(state['checked_at'])  # display only: no check has run this session
            third=q.Quotas(folder,account_readers={'codex':lambda:'a@codex.test','claude':lambda:None},clock=lambda:1000.0+7200)
            self.assertEqual(third.snapshot()['platforms']['codex']['status'],'not_checked')  # stale history is not restored

if __name__=='__main__':unittest.main()
