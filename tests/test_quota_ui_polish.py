import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from console.app import PAGE
from console.quota_ui import JS, EN
from console.group_ui import JS as GROUP_JS
from group_chat import Groups
from control_center import Center

class QuotaUIPolishTests(unittest.TestCase):
    def js(self,code):
        result=subprocess.run(['node'],input=code,text=True,capture_output=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_quota_toggle_preserves_keyboard_and_motion_changes(self):
        handler=JS[JS.index('const quotaMotion='):JS.index("$('quota-log-list').addEventListener('toggle'")]
        self.js(r'''const assert=require('node:assert/strict');let listener,onMotion,finish;
const classes=new Set(),d={open:false,offsetHeight:0,classList:{contains:k=>classes.has(k),add:k=>classes.add(k),remove:k=>classes.delete(k)}};
const summary={parentElement:d,setAttribute:(k,v)=>summary[k]=v};
const $=()=>({addEventListener:(name,f)=>listener=f}),media={matches:false,addEventListener:(n,f)=>onMotion=f},matchMedia=()=>media;
const document={querySelectorAll:()=>[d]},setTimeout=f=>{finish=f;return 1;},clearTimeout=()=>{};
const e={target:{closest:()=>summary},preventDefault(){}};
''' +handler+r'''
listener(e);assert.equal(d.open,true);assert.equal(summary['aria-expanded'],'true');
listener(e);assert.equal(d.open,true);assert.equal(summary['aria-expanded'],'false');
listener(e);finish();assert.equal(d.open,true);assert(classes.has('quota-expanded'));
listener(e);media.matches=true;onMotion({matches:true});assert.equal(d.open,false);
listener(e);listener(e);assert.equal(d.open,false);
''')
        self.assertIn('grid-template-rows:1fr',PAGE)
        self.assertIn('const previous=new Map',JS)
        self.assertIn('return old;',JS)
        self.assertNotIn('body.scrollHeight',JS)

    def test_group_attention_is_terminal_display_not_active(self):
        code=GROUP_JS[GROUP_JS.index('function groupMemberState'):GROUP_JS.index('const groupActive=')]
        self.js("const assert=require('node:assert/strict');"+code+'''
for(const s of ['attention','uncertain'])assert.equal(groupMemberState({status:'idle',latest_job_status:s}),s);
assert.equal(groupMemberState({status:'running',latest_job_status:'attention'}),'running');
assert.equal(groupMemberState({status:'idle',latest_job_status:'done'}),'idle');
assert.equal(groupMemberState({removed:true,status:'idle',latest_job_status:'uncertain'}),'removed');
''')
        self.assertIn("attention:T('需人工核对'),uncertain:T('启动状态待核对')",PAGE)
        self.assertEqual(EN['需人工核对'],'Needs manual review')
        self.assertEqual(EN['启动状态待核对'],'Start status needs verification')

    def test_snapshot_preserves_latest_status_without_counting_active(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'project';root.mkdir();state=Path(temp)/'state';state.mkdir()
            g=Groups(state,Center(state,[root]),launch=False)
            gid=g.create({'root':str(root),'name':'demo'})['id']
            mid=g.add({'group':gid,'slug':'demo','platform':'codex','model':'gpt-6-sol'})['id']
            with g.connect() as db:
                for i,status in enumerate(['attention','uncertain']):
                    db.execute('INSERT INTO jobs(id,gid,member,text,depth,at,status) VALUES(?,?,?,?,?,?,?)',(str(i),gid,mid,'demo',0,i+1,status))
            data=g.snapshot(gid)
            self.assertEqual(data['members'][0]['status'],'idle')
            self.assertEqual(data['members'][0]['latest_job_status'],'uncertain')
            self.assertEqual(data['jobs'],[])

    def test_browser_alert_survives_reload_and_keeps_account_window_identity(self):
        code=JS[JS.index('function quotaNotify('):JS.index('async function loadQuota(){')]
        self.js(r'''const assert=require('node:assert/strict'),quotaAlertSeen={},stored={};let sent=0;
const sessionStorage={getItem:k=>stored[k],setItem:(k,v)=>stored[k]=v},window={Notification:true},T=s=>s;
function Notification(){sent++;}Notification.permission='granted';
''' +code+r'''
const state={status:'ok',checked_at:1,account:'a',settings:{notify:true,five_hour_threshold:8},alerts:['five_hour'],windows:[{window:'five_hour',resets_at:100,remaining:4}]};
quotaNotify('codex',state);quotaNotify('codex',state);assert.equal(sent,1);
for(const k of Object.keys(quotaAlertSeen))delete quotaAlertSeen[k];quotaNotify('codex',state);assert.equal(sent,1);
quotaNotify('codex',{...state,account:'b'});assert.equal(sent,2);
quotaNotify('codex',{...state,windows:[{window:'five_hour',resets_at:200,remaining:4}]});assert.equal(sent,3);
quotaNotify('codex',{...state,alerts:[],windows:[{window:'five_hour',resets_at:100,remaining:50}]});quotaNotify('codex',state);assert.equal(sent,4);
quotaNotify('claude',{...state,notification_sent:true});assert.equal(sent,5);
quotaNotify('claude',{...state,notification_sent:true,windows:[{window:'five_hour',resets_at:900,remaining:4}]});assert.equal(sent,6);
''')

    def test_individual_quota_buckets_are_not_marked_seen_by_shared_window(self):
        code=JS[JS.index('function quotaNotify('):JS.index('async function loadQuota(){')]
        self.js(r'''const assert=require('node:assert/strict'),quotaAlertSeen={},stored={};let sent=0;
const sessionStorage={getItem:k=>stored[k],setItem:(k,v)=>stored[k]=v},window={Notification:true},T=s=>s;
function Notification(){sent++;}Notification.permission='granted';
''' +code+r'''
const state={status:'ok',checked_at:1,account:'demo',settings:{notify:true,five_hour_threshold:8},alerts:['five_hour']};
const bucket=(name,remaining)=>({window:'five_hour',bucket:name,remaining,resets_at:100});
quotaNotify('codex',{...state,windows:[bucket('A',4),bucket('B',50)]});assert.equal(sent,1);
quotaNotify('codex',{...state,windows:[bucket('A',50),bucket('B',4)]});assert.equal(sent,2);
quotaNotify('codex',{...state,windows:[bucket('A',null),bucket('B',undefined)]});assert.equal(sent,2);
quotaNotify('codex',{...state,settings:{notify:true},windows:[bucket('A',4)]});assert.equal(sent,2);
''')

    def test_equal_summary_account_switch_replaces_model_details(self):
        start=JS.index('const filterKey=JSON.stringify(quotaLogState);')
        end=JS.index('return true;}catch(e)',start)
        self.js(r'''const assert=require('node:assert/strict');
let html='same',quotaLogState={account:'B'};
const old={dataset:{start:'1',end:'2'},querySelector:()=>({innerHTML:'same'}),models:'A-private'};
const fresh={dataset:{start:'1',end:'2'},querySelector:()=>({innerHTML:'same'}),models:'unloaded'};
const list={__h:'same',__filterKey:JSON.stringify({account:'A'}),querySelectorAll:()=>[old],replaceChildren(...rows){this.rows=rows;}};
const document={createElement:()=>({children:[fresh]})};
''' +JS[start:end]+r'''
assert.equal(list.rows[0],fresh);assert.equal(list.__filterKey,JSON.stringify(quotaLogState));
''')

    def test_late_account_response_is_discarded_and_busy_clears(self):
        code=JS[JS.index('async function loadQuotaLog(){'):JS.index('// Grid expansion follows')]
        self.js(r'''const assert=require('node:assert/strict');let quotaLogBusy=false,quotaLogState={platform:'codex',account:'A',range:'all',tier:'5h'},resolve;
const centerApi=q=>new Promise(r=>resolve=r),$=()=>{throw Error('stale response touched UI')};
''' +code+r'''
(async()=>{const pending=loadQuotaLog();quotaLogState.account='B';resolve({accounts:['A'],windows:[{start:1,end:2}]});assert.equal(await pending,false);assert.equal(quotaLogBusy,false);const again=loadQuotaLog();assert.equal(quotaLogBusy,true);quotaLogState.account='C';resolve({windows:[]});await again;assert.equal(quotaLogBusy,false);})().catch(e=>{console.error(e);process.exitCode=1;});
''')

    def test_late_detail_response_is_discarded_and_can_retry(self):
        code=JS[JS.index('async function quotaLoadDetail('):JS.index('async function quotaLogSwitch')]
        self.js(r'''const assert=require('node:assert/strict');let listener,resolve;const quotaLogState={platform:'codex',account:'A',range:'all',tier:'5h'};
const $=()=>({addEventListener:(name,f)=>listener=f}),centerApi=()=>new Promise(r=>resolve=r);
const body={textContent:'original',innerHTML:'original'},d={open:true,isConnected:true,dataset:{loaded:'0',start:'1',end:'2'},classList:{contains:()=>true},querySelector:()=>body};
''' +code+r'''
(async()=>{const p=listener({target:d});quotaLogState.account='B';resolve({windows:[{models:[{model:'A-private'}]}]});await p;assert.equal(body.innerHTML,'original');assert.equal(d.dataset.loaded,'0');const next=listener({target:d});d.isConnected=false;resolve({windows:[]});await next;assert.equal(body.textContent,'original');assert.equal(d.dataset.loaded,'0');})().catch(e=>{console.error(e);process.exitCode=1;});
''')

    def test_failed_check_does_not_reset_alert_dedup(self):
        code=JS[JS.index('function quotaNotify('):JS.index('async function loadQuota(){')]
        self.js(r'''const assert=require('node:assert/strict'),quotaAlertSeen={},stored={};let sent=0;
const sessionStorage={getItem:k=>stored[k],setItem:(k,v)=>stored[k]=v},window={Notification:true},T=s=>s;
function Notification(){sent++;}Notification.permission='granted';
''' +code+r'''
const state={status:'ok',checked_at:100,account:'demo',settings:{notify:true,five_hour_threshold:8},alerts:['five_hour'],windows:[{window:'five_hour',remaining:4,resets_at:200}]};
quotaNotify('codex',state);assert.equal(sent,1);
quotaNotify('codex',{...state,status:'error',alerts:[],windows:[{window:'five_hour',remaining:50,resets_at:200}]});
quotaNotify('codex',state);assert.equal(sent,1);
quotaNotify('codex',{...state,checked_at:null,alerts:[],windows:[{window:'five_hour',remaining:50,resets_at:200}]});
quotaNotify('codex',state);assert.equal(sent,1);
quotaNotify('codex',{...state,alerts:[],windows:[{window:'five_hour',remaining:50,resets_at:200}]});
quotaNotify('codex',state);assert.equal(sent,2);
''')

    def test_summary_update_refreshes_open_detail_with_new_version(self):
        start=JS.index('const filterKey=JSON.stringify(quotaLogState);');end=JS.index('return true;}catch(e)',start)
        self.js(r'''const assert=require('node:assert/strict');const quotaLogState={account:'A'},html='changed';let refreshed;
const summary={innerHTML:'old'},old={dataset:{start:'1',end:'2',loaded:'1'},open:true,querySelector:()=>summary};
const fresh={dataset:{start:'1',end:'2'},querySelector:()=>({innerHTML:'new'})};
const list={__h:'old',__filterKey:JSON.stringify(quotaLogState),querySelectorAll:()=>[old],replaceChildren(...rows){this.rows=rows;}};
const document={createElement:()=>({children:[fresh]})},quotaLoadDetail=d=>refreshed=d;
''' +JS[start:end]+r'''
assert.equal(list.rows[0],old);assert.equal(refreshed,old);assert.equal(old.dataset.loaded,'0');assert.equal(old.dataset.version,'1');assert.equal(summary.innerHTML,'new');
''')

    def test_late_failed_list_response_cannot_clear_current_list(self):
        code=JS[JS.index('async function loadQuotaLog(){'):JS.index('// Grid expansion follows')]
        self.js(r'''const assert=require('node:assert/strict');let quotaLogBusy=false,quotaLogState={account:'A'},reject;
const centerApi=()=>new Promise((r,j)=>reject=j),$=()=>{throw Error('stale rejection touched UI');};
''' +code+r'''
(async()=>{const p=loadQuotaLog();quotaLogState.account='B';reject(Error('A error'));assert.equal(await p,false);assert.equal(quotaLogBusy,false);})().catch(e=>{console.error(e);process.exitCode=1;});
''')

    def test_stale_detail_version_cannot_overwrite_refreshed_models(self):
        code=JS[JS.index('async function quotaLoadDetail('):JS.index("$('quota-log-list').addEventListener('toggle',e=>")]
        self.js(r'''const assert=require('node:assert/strict');const quotaLogState={account:'A'},pending=[];
const centerApi=()=>new Promise(r=>pending.push(r)),T=s=>s,esc=s=>s,quotaTokens=s=>s,quotaMoney=s=>s,quotaLogCache=()=>0;
const body={innerHTML:'original'},d={open:true,isConnected:true,dataset:{loaded:'0',version:'0'},classList:{contains:()=>true},querySelector:()=>body};
''' +code+r'''
(async()=>{const old=quotaLoadDetail(d);d.dataset.version='1';d.dataset.loaded='0';const current=quotaLoadDetail(d);pending[1]({windows:[{models:[{model:'fresh'}]}]});await current;assert(body.innerHTML.includes('fresh'));pending[0]({windows:[{models:[{model:'stale'}]}]});await old;assert(body.innerHTML.includes('fresh'));assert(!body.innerHTML.includes('stale'));assert.equal(d.dataset.loaded,'1');})().catch(e=>{console.error(e);process.exitCode=1;});
''')

    def test_usage_sync_labels_and_existing_tokens_are_preserved(self):
        code=JS[JS.index('function quotaSyncState('):JS.index('function quotaProtectionMessage(')]
        self.js(r'''const assert=require('node:assert/strict'),T=s=>s,esc=s=>s,quotaTokens=s=>String(s),quotaMoney=s=>'$'+s,quotaStamp=s=>String(s);
''' +code+r'''
const empty={tokens:null,reason:'not_recorded'};
assert(quotaWindowUsage(empty,{}).includes('等待首次本地同步'));
assert(quotaWindowUsage(empty,{last_started:Date.now()/1000,last_completed:1}).includes('本地用量同步中'));
assert(quotaWindowUsage(empty,{last_started:2,last_completed:1,error:'failed'}).includes('本地用量同步失败'));
assert(quotaWindowUsage(empty,{last_completed:3}).includes('本窗口暂无已归属本机记录'));
assert(quotaWindowUsage({tokens:123,cost:1},{error:'failed'}).includes('本地消耗 123 tok · $1'));
assert.equal(quotaWindowUsage({tokens:null,reason:'unknown_account'},{}),'');
assert(quotaSyncSummary({last_completed:1,next_due:Date.now()/1000+300}).includes('下次预计'));
assert(!quotaSyncSummary({last_completed:1,next_due:1}).includes('下次预计'));
assert(quotaSyncSummary({last_completed:1,next_due:1}).includes('下次同步时间待确认'));
assert.equal(quotaSyncState({last_started:Date.now()/1000-301,last_completed:1}),'unknown');
assert.equal(quotaSyncState({last_started:'bad',last_completed:1}),'unknown');
assert.equal(quotaSyncState({last_completed:NaN}),'unknown');
assert.equal(quotaSyncState(null),'first');
assert.equal(quotaSyncState({}),'first');
assert(quotaWindowUsage(empty,{last_started:Date.now()/1000-301,last_completed:1}).includes('同步状态待检查'));
assert(quotaSyncSummary({last_started:'bad',last_completed:1}).includes('同步状态待检查'));
''')
        self.assertIn('quotaWindowUsage(w.usage,d.usage_sync)',PAGE)
        for key in ['等待首次本地同步','本窗口暂无已归属本机记录','最近本地同步：','下次预计：']:
            self.assertIn(key,EN)

    def test_glass_bar_reuses_segments_and_totals_have_text(self):
        self.assertIn("if(!prop.children.length)",PAGE)
        self.assertIn("segment.style.flex=pc[key]+' 1 0%'",PAGE)
        self.assertIn("prop.setAttribute('aria-label'",PAGE)
        self.assertIn('prefers-reduced-motion:reduce',PAGE)
        self.assertIn('quota-log-body',PAGE)
