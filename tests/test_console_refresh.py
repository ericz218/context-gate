"""Refresh outcomes and preservation of an in-progress budget calculation."""
import os
import re
import shutil
import subprocess
import unittest

from console.app import PAGE
from console.wallet_ui import JS as WALLET_JS


class RefreshBehaviorTests(unittest.TestCase):
    def run_js(self, code):
        if not shutil.which('node'):
            self.skipTest('Node unavailable')
        result=subprocess.run(['node'],input=code,text=True,capture_output=True,
                              env=dict(os.environ,TZ='America/New_York'),timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)

    def refresh_js(self):
        return PAGE[PAGE.index('let refreshController='):PAGE.index('function showReconnect(')]

    def test_manual_refresh_waits_for_current_page_and_reports_its_failure(self):
        self.run_js(r'''
const assert=require('node:assert/strict');
const nodes={period:{value:'all'},platform:{value:'all'},banner:{style:{}},'refresh-note':{dataset:{}},refresh:{setAttribute(){},removeAttribute(){}}};
const $=id=>nodes[id],T=s=>s,LOCALE=()=> 'en',modelDetail={};let curView='wallet',done;
const render=()=>{},schedule=()=>{},showReconnect=()=>{};
const loadWallet=()=>new Promise(resolve=>{done=resolve});
global.fetch=async()=>({ok:true,status:200,json:async()=>({})});
''' + self.refresh_js() + r'''
(async()=>{
 const request=refresh();await new Promise(setImmediate);
 assert.equal(nodes.refresh.disabled,true);assert.equal(nodes['refresh-note'].dataset.state,'busy');
 done(false);await request;
 assert.equal(nodes.refresh.disabled,false);assert.equal(nodes['refresh-note'].dataset.state,'error');
 assert.match(nodes['refresh-note'].textContent,/失败/);assert.doesNotMatch(nodes['refresh-note'].textContent,/已更新/);
})().catch(e=>{console.error(e);process.exitCode=1});
''')

    def test_automatic_refresh_is_quiet_and_does_not_duplicate_live_polling(self):
        self.run_js(r'''
const assert=require('node:assert/strict');let calls=0;
global.document={hidden:false};
const button={textContent:'刷新',getAttribute:()=>null,setAttribute(){},removeAttribute(){}};
const note={dataset:{state:'ok'},textContent:'上次手动更新时间'};
const nodes={period:{value:'all'},platform:{value:'all'},banner:{style:{}},'refresh-note':note,refresh:button};
const $=id=>nodes[id],T=s=>s,LOCALE=()=> 'en',modelDetail={};let curView='wallet';
const render=()=>{},schedule=()=>{},showReconnect=()=>{};
const loadWallet=async()=>{calls++;return true};
const loadCenter=async()=>{throw Error('duplicate polling')};
global.fetch=async()=>({ok:true,status:200,json:async()=>({})});
''' + self.refresh_js() + r'''
(async()=>{
 await refresh({automatic:true});assert.equal(calls,1);
 assert.equal(note.textContent,'上次手动更新时间');assert.equal(button.textContent,'刷新');
 curView='center';await refresh({automatic:true});
 assert.equal(note.textContent,'上次手动更新时间');
 document.hidden=true;await refresh({automatic:true});assert.equal(calls,1);
})().catch(e=>{console.error(e);process.exitCode=1});
''')

    def test_page_switch_during_fetch_does_not_claim_new_page_was_updated(self):
        self.run_js(r'''
const assert=require('node:assert/strict');let resolve;
const nodes={period:{value:'all'},platform:{value:'all'},banner:{style:{}},'refresh-note':{dataset:{}},refresh:{setAttribute(){},removeAttribute(){}}};
const $=id=>nodes[id],T=s=>s,LOCALE=()=> 'en',modelDetail={};let curView='overview';
const render=()=>{},schedule=()=>{},showReconnect=()=>{};
global.fetch=()=>new Promise(r=>resolve=r);
''' + self.refresh_js() + r'''
(async()=>{
 const request=refresh();curView='wallet';resolve({ok:true,status:200,json:async()=>({})});await request;
 assert.equal(nodes['refresh-note'].dataset.state,'waiting');assert.match(nodes['refresh-note'].textContent,/已切换页面/);
})().catch(e=>{console.error(e);process.exitCode=1});
''')

    def test_wallet_preserves_edits_and_redraws_deferred_data_later(self):
        start=WALLET_JS.index("let walletRenderedSnapshot=")
        end=WALLET_JS.index('window.loadWallet=',start)
        self.run_js(r'''
const assert=require('node:assert/strict');let editing=false,modalOpen=false,requests=0,renders=0,fail=false,beginEdit=false;
global.document={activeElement:{matches:()=>true}};
const root={innerHTML:'existing calculation',contains:()=>editing,querySelector:()=>null};
const qs=id=>id==='#mw-root'?root:{open:modalOpen};
const bind=()=>{},readCalc=()=>{},readCtx=()=>{},restoreDraft=()=>{throw Error('draft reset')},toast=()=>{},T=s=>s;
let loaded=true,calcRevision=0;
const state={models:[],wallets:[],settings:{},dashboard:{},calc:{budget:'197.5'},result:{estimate:'saved'}};
const reload=async()=>{requests++;if(fail)throw Error('offline');state.wallets=[{balance:requests}];if(beginEdit){editing=true;calcRevision++}};
const render=()=>{renders++};
''' + WALLET_JS[start:end] + r'''
(async()=>{
 editing=true;assert.equal(await loadWallet({automatic:true}),null);assert.equal(requests,0);
 editing=false;modalOpen=true;assert.equal(await loadWallet(),null);assert.equal(requests,0);
 modalOpen=false;beginEdit=true;
 assert.equal(await loadWallet({automatic:true}),null);assert.equal(renders,0);
 beginEdit=false;editing=false;
 assert.equal(await loadWallet({automatic:true}),true);assert.equal(renders,1);
 assert.equal(state.calc.budget,'197.5');assert.deepEqual(state.result,{estimate:'saved'});
 fail=true;assert.equal(await loadWallet(),false);
 assert.equal(root.innerHTML,'existing calculation');assert.equal(renders,1);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


if __name__=='__main__':unittest.main()
