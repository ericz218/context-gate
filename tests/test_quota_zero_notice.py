import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import subprocess
import console_quota as q
from console.quota_ui import JS


class ZeroNoticeTests(unittest.TestCase):
    def test_zero_survives_reset_unknown_restart_and_rearms_per_account(self):
        account=['a'];remaining=[0];reset=[100];sent=[];clock=[1000]
        def read():return {'account':account[0],'windows':[{'window':'five_hour','bucket':'main','remaining':remaining[0],'resets_at':reset[0]}]}
        with tempfile.TemporaryDirectory() as folder:
            def monitor():return q.Quotas(folder,clock=lambda:clock[0],readers={'codex':read},account_readers={'codex':lambda:account[0]},notifier=lambda p:sent.append((p,account[0])) or True)
            def refresh(m):
                clock[0]+=120
                m.refresh('codex')
            m=monitor();refresh(m);reset[0]=101;refresh(m);self.assertEqual(sent,[('codex','a')])
            remaining[0]=None;refresh(m);remaining[0]=0;refresh(m);self.assertEqual(len(sent),1)
            m=monitor();reset[0]=999;refresh(m);self.assertEqual(len(sent),1)
            account[0]='b';refresh(m);self.assertEqual(sent[-1],('codex','b'))
            account[0]='a';refresh(m);self.assertEqual(len(sent),2)
            remaining[0]=50;refresh(m);remaining[0]=0;refresh(m);self.assertEqual(len(sent),3)
            # Recovery and re-exhaustion of another bucket are independent.
            account[0]='b';refresh(m);self.assertEqual(len(sent),3)

    def test_browser_zero_persists_and_native_is_not_duplicated(self):
        code=JS[JS.index('function quotaNotify('):JS.index('async function loadQuota(){')]
        script=r'''const assert=require('node:assert/strict'),quotaAlertSeen={},stored={};let sent=0;
const localStorage={getItem:k=>stored[k],setItem:(k,v)=>stored[k]=v},window={Notification:true},T=s=>s;
function Notification(){sent++;}Notification.permission='granted';
''' +code+r'''
const state={status:'ok',checked_at:1,account:'a',settings:{notify:true,five_hour_threshold:8},alerts:['five_hour'],windows:[{window:'five_hour',bucket:'main',resets_at:100,remaining:0}]};
quotaNotify('codex',state);quotaNotify('codex',{...state,windows:[{...state.windows[0],resets_at:200}]});assert.equal(sent,1);
for(const k of Object.keys(quotaAlertSeen))delete quotaAlertSeen[k];quotaNotify('codex',state);assert.equal(sent,1);
quotaNotify('codex',{...state,windows:[{...state.windows[0],remaining:null}]});quotaNotify('codex',state);assert.equal(sent,1);
quotaNotify('codex',{...state,account:'b'});assert.equal(sent,2);
quotaNotify('codex',{...state,windows:[{...state.windows[0],remaining:50}],alerts:[]});quotaNotify('codex',state);assert.equal(sent,3);
window.webkit={messageHandlers:{notify:{}}};quotaNotify('claude',state);assert.equal(sent,3);
'''
        subprocess.run(['node','-e',script],check=True,capture_output=True,text=True)
