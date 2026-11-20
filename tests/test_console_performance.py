"""Navigation scheduling, ledger equivalence and concurrent cache behavior."""
import concurrent.futures
import os
import random
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

import console_data as cd
from console.app import PAGE


def between(start, end):
    return PAGE[PAGE.index(start):PAGE.index(end, PAGE.index(start))]


class LedgerPerformanceTests(unittest.TestCase):
    def test_single_pass_summary_preserves_missing_zero_and_failed_metrics(self):
        rng=random.Random(107)
        rows=[dict(sent=rng.choice([0,1]),ready=rng.choice([0,1]),
                   exit_code=rng.choice([None,0,1,137]),
                   **{k:rng.choice([None,0,1,1200]) for k in (
                       'before_est','after_est','actual_input','actual_output','cached',
                       'jev_actual_input','jev_actual_output','total_ms','duration_ms')})
              for _ in range(3000)]
        for sample in ([],rows[:1],rows):
            sent=[r for r in sample if r['sent']]
            measured=[r for r in sent if r['actual_input'] is not None]
            complete=[r for r in sent if r['exit_code']==0 and cd.row_latency(r) is not None]
            total=lambda rs,k:sum(r.get(k) or 0 for r in rs)
            before=total(sent,'before_est');after=total(sent,'after_est')
            jev=total(sample,'jev_actual_input')+total(sample,'jev_actual_output')
            expected=dict(requests=len(sent),measured_requests=len(measured),
                          failed_requests=sum(r['exit_code'] not in (None,0) for r in sent),
                          pending_requests=sum(r['exit_code'] is None for r in sent),
                          prepared_requests=sum(not r['sent'] and r['ready'] for r in sample),
                          blocked_requests=sum(not r['ready'] for r in sample),
                          input_tokens=total(measured,'actual_input'),output_tokens=total(measured,'actual_output'),
                          cached_tokens=total(measured,'cached'),jev_tokens=jev,
                          actual_tokens=total(measured,'actual_input')+total(measured,'actual_output')+jev,
                          estimated_before=before,estimated_after=after,estimated_saved=before-after,
                          estimated_reduction_pct=round(100*(before-after)/before,2) if before else None,
                          mean_ms=round(sum(cd.row_latency(r) for r in complete)/len(complete),2) if complete else None,
                          timed_requests=len(complete),
                          **cd.speed_stats([(r['actual_output'],cd.row_latency(r)) for r in complete
                                            if (r['actual_output'] or 0)>0 and cd.row_latency(r)>0]))
            self.assertEqual(cd.summarize(sample),expected)

    def test_concurrent_cold_filters_share_one_computation(self):
        with tempfile.TemporaryDirectory() as state:
            started=threading.Event();release=threading.Event();calls=[]
            def compute(*args,**kwargs):
                calls.append(1);started.set()
                self.assertTrue(release.wait(3))
                return {'requests':42}
            with patch.object(cd,'snapshot',side_effect=compute), concurrent.futures.ThreadPoolExecutor(4) as pool:
                first=pool.submit(cd.snapshot_cached,state)
                self.assertTrue(started.wait(2))
                rest=[pool.submit(cd.snapshot_cached,state) for _ in range(3)]
                release.set()
                self.assertEqual([f.result(3) for f in [first,*rest]],[{'requests':42}]*4)
                self.assertEqual(len(calls),1)

    def test_slow_version_probe_does_not_block_cached_or_other_filters(self):
        with tempfile.TemporaryDirectory() as state:
            probing=threading.Event();release=threading.Event();finished=threading.Event()
            def version(*args):
                if threading.current_thread() is not threading.main_thread():
                    probing.set();release.wait(3);finished.set()
                return ('same',)
            with patch.object(cd,'snapshot',return_value={'requests':42}), patch.object(cd,'_stats_version',side_effect=version):
                first=cd.snapshot_cached(state)
                try:
                    with patch.object(cd,'SNAPSHOT_PROBE_SKIP',0):
                        self.assertIs(cd.snapshot_cached(state),first)
                        self.assertTrue(probing.wait(2))
                        self.assertIs(cd.snapshot_cached(state),first)
                        self.assertEqual(cd.snapshot_cached(state,'today'),first)
                finally:
                    release.set();self.assertTrue(finished.wait(2))

    def test_failed_cold_computation_releases_waiters_and_allows_retry(self):
        with tempfile.TemporaryDirectory() as state:
            with patch.object(cd,'snapshot',side_effect=ValueError('bad ledger')):
                with self.assertRaisesRegex(ValueError,'bad ledger'):cd.snapshot_cached(state)
            self.assertFalse(any(k[0]==state for k in cd._snapshot_inflight))
            with patch.object(cd,'snapshot',return_value={'requests':7}):
                self.assertEqual(cd.snapshot_cached(state),{'requests':7})


class NavigationPerformanceTests(unittest.TestCase):
    def run_js(self,script):
        if not shutil.which('node'):self.skipTest('Node unavailable')
        r=subprocess.run(['node'],input=script,text=True,capture_output=True,
                         env=dict(os.environ,TZ='America/New_York'),timeout=10)
        self.assertEqual(r.returncode,0,r.stderr)

    def test_only_active_view_renders_and_return_uses_latest_snapshot(self):
        self.run_js(r'''
const assert=require('node:assert/strict');let curView='overview',calls=[];
let lastData={updated_at:1,period:'all',platform:'all',cost_mode:'official'};
const renderSummary=()=>calls.push('summary'),renderChart=()=>calls.push('chart'),renderOverview=()=>calls.push('overview');
const renderBilling=()=>calls.push('bill'),renderPlatformTable=()=>calls.push('table'),renderPlatformViz=()=>calls.push('platform');
const renderRecent=()=>calls.push('recent'),renderRequestSummary=()=>calls.push('requests'),renderWorkbench=()=>calls.push('wb');
const renderSystem=()=>calls.push('sys'),renderAudit=()=>calls.push('audit'),renderGateTasks=()=>calls.push('gt');
''' + between('const renderedStats=', 'function render(d,') + r'''
renderActiveStats();assert.deepEqual(calls,['summary','chart','overview']);
calls=[];renderActiveStats();assert.deepEqual(calls,[]);
renderActiveStats(true);assert.deepEqual(calls,['summary','chart','overview']);calls=[];
curView='bill';renderActiveStats();assert.deepEqual(calls,['bill']);
lastData={...lastData,updated_at:2};calls=[];renderActiveStats();assert.deepEqual(calls,['bill']);
curView='overview';calls=[];renderActiveStats();assert.deepEqual(calls,['summary','chart','overview']);
curView='wallet';calls=[];renderActiveStats();assert.deepEqual(calls,[]);
''')

    def test_rapid_navigation_cancels_obsolete_work_without_layout_reads(self):
        self.run_js(r'''
const assert=require('node:assert/strict');const frames=[],jobs=[],loaded=[],rendered=[];
let curView='overview';const VIEWS={overview:['overview'],memory:['memory'],git:['git']};
const viewSections=Object.keys(VIEWS).map(view=>({dataset:{view},style:{display:view==='overview'?'block':'none'},classList:{contains:()=>false},animate(){}}));
for(const el of viewSections)Object.defineProperty(el,'offsetWidth',{get(){throw Error('forced layout')}});
const document={querySelectorAll:()=>[]},window={matchMedia:()=>({matches:false})},matchMedia=window.matchMedia;
const nodes=new Proxy({},{get:()=>({})}),$=id=>nodes[id];let viewRenderGeneration=0;
const requestAnimationFrame=cb=>frames.push(cb),setTimeout=cb=>jobs.push(cb);
const syncFilterChip=()=>{},updatePageGuide=()=>{},syncRouterFilters=()=>{},ddClose=()=>{};
const renderActiveStats=()=>rendered.push(curView),loadView=v=>loaded.push(v);
''' + between('function applyView(v){','function loadView(v){') + r'''
applyView('memory');assert.equal(curView,'memory');assert.equal(viewSections[1].style.display,'block');assert.deepEqual(loaded,[]);
applyView('git');frames.forEach(f=>f());jobs.forEach(f=>f());
assert.deepEqual(loaded,['git']);assert.deepEqual(rendered,['git']);
assert.equal(viewSections[1].style.display,'none');assert.equal(viewSections[2].style.display,'block');
''')

    def test_billing_navigation_takes_effect_without_wait_or_click_lock(self):
        self.run_js(r'''
const assert=require('node:assert/strict');let renders=0,cancelled=0;
const bill={platform:null,model:null},REDUCE=()=>false;
const page={querySelectorAll:()=>[],animate:()=>({cancel(){cancelled++}})};
const $=id=>id==='bill-page'?page:{focus(){}},renderBilling=()=>renders++;
''' + between('let billNavigation=', 'function applyThemeAttr(') + r'''
navigateBilling('router',null,'forward');assert.equal(bill.platform,'router');assert.equal(renders,1);
navigateBilling('router','model','forward');assert.equal(bill.model,'model');assert.equal(renders,2);assert.equal(cancelled,1);
navigateBilling(null,null,'back');assert.equal(bill.platform,null);assert.equal(renders,3);
''')

    def test_closed_task_does_not_build_its_logs(self):
        self.run_js(r'''
const assert=require('node:assert/strict');let gtOpen=null,details=0;
const T=s=>s,Tc=(n,s)=>s,esc=s=>String(s),num=String,fmtAt=()=>'',GT_STATUS={done:'done'},gtCost=()=>'';
const gtDetailHTML=()=>{details++;return 'LOG CONTENT'};
''' + between('function gtRowItem(', 'function gtDetailHTML(') + r'''
const task={root:'/project',display_status:'done',turns:[],estimates:{}};
const closed=gtRowItem(task,0);assert.equal(details,0);assert.doesNotMatch(closed,/LOG CONTENT/);
gtOpen=0;assert.match(gtRowItem(task,0),/LOG CONTENT/);assert.equal(details,1);
''')

    def test_model_response_after_leaving_is_ready_on_return_without_hidden_render(self):
        self.run_js(r'''
const assert=require('node:assert/strict');let curView='bill',renders=0,resolve;
const bill={platform:'router',model:'demo'},$=()=>({value:'all'}),renderBilling=()=>renders++;
const renderedStats=new Map([['bill','last-render']]);
global.fetch=()=>new Promise(r=>resolve=r);
''' + between("let modelDetail={key:", 'function chartBuckets(') + r'''
(async()=>{
 ensureModelDetail();curView='overview';
 resolve({ok:true,json:async()=>({recent:[{id:'latest'}]})});
 await new Promise(setImmediate);
 assert.equal(renders,0);assert.equal(renderedStats.has('bill'),false);
 assert.deepEqual(modelDetail.rows,[{id:'latest'}]);
})().catch(e=>{console.error(e);process.exitCode=1});
''')


if __name__=='__main__':unittest.main()
