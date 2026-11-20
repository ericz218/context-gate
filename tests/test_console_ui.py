"""Behavior checks for console races, calendar buckets and accessible controls."""
import os
import re
import shutil
import subprocess
import unittest
from html.parser import HTMLParser

from console.app import PAGE


def script_between(start, end):
    return PAGE[PAGE.index(start):PAGE.index(end, PAGE.index(start))]


class ConsoleUITests(unittest.TestCase):
    def test_router_unknown_tokens_and_credit_meter_are_distinct(self):
        self.run_js(script_between('function routerUsageCell(', 'function renderRouterContent(') + r'''
const assert=require('node:assert/strict');
function esc(s){return String(s)}function T(s){return s}function num(n){return String(n)}function nsp(n){return String(n)}
assert.equal(routerUsageCell(0,0,null),'Token 未提供');
assert.equal(routerUsageCell(0,1,null),'0');
assert.equal(routerUsageCell(null,0,.00756),'Token 未提供<small>0.007560 credits</small>');
assert.equal(routerUsageCell(586937,1,null),'586937');
''')

    def run_js(self, script):
        if not shutil.which('node'):
            self.skipTest('Node is needed for browser logic checks')
        result = subprocess.run(['node'], input=script, capture_output=True, text=True,
                                env=dict(os.environ, TZ='America/New_York'), timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_calendar_days_cross_dst_and_zero_savings_is_measured(self):
        self.run_js(script_between('function chartBuckets(', 'function moneyShort(') +
                    script_between('function savingsOf(', "$('refresh').onclick") + r'''
const assert=require('node:assert/strict');
for(const end of ['2026-03-10T00:30:00','2026-11-03T23:30:00']){
 const now=new Date(end);
 for(const [mode,size] of [['7d',7],['month',30]]){
  const days=chartBuckets(mode,[],+now).map(p=>p.day);
  assert.equal(days.length,size);assert.equal(new Set(days).size,size);
  for(let i=0;i<size;i++){
   const d=new Date(now);d.setDate(d.getDate()-(size-i-1));
   const key=d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
   assert.equal(days[i],key);
  }
 }
}
assert.equal(savingsOf({global_ab:{pairs:1},by_platform:[{ab_saved_usd:0}]}),0);
assert.equal(savingsOf({global_ab:{pairs:1},by_platform:[{ab_saved_usd:-1}]}),-1);
assert.equal(savingsOf({global_ab:{pairs:0}}),null);
''')

    def test_late_stats_response_cannot_replace_latest_filter(self):
        self.run_js(r'''
const assert=require('node:assert/strict');
const nodes={period:{value:'all'},platform:{value:'all'},refresh:{setAttribute(){},removeAttribute(){}},banner:{style:{}}};
const $=id=>nodes[id],T=s=>s,modelDetail={key:'old'};let curView='overview',scheduled=0;
const rendered=[],pending=[];
function render(d){rendered.push(d);}function schedule(){scheduled++;}function showReconnect(){throw Error('unexpected');}
global.fetch=(url,options)=>new Promise(resolve=>pending.push({url,options,resolve}));
''' + script_between('let refreshController=', 'function showReconnect(') + r'''
(async()=>{
 const first=refresh();nodes.period.value='today';const second=refresh();
 assert.equal(pending[0].options.signal.aborted,true);
 pending[1].resolve({ok:true,status:200,json:async()=>({period:'today'})});await second;
 pending[0].resolve({ok:true,status:200,json:async()=>({period:'all'})});await first;
 assert.deepEqual(rendered,[{period:'today'}]);assert.equal(scheduled,1);assert.equal(nodes.refresh.disabled,false);
})().catch(e=>{console.error(e);process.exitCode=1;});
''')

    def test_model_detail_speed_panel_reports_tps_or_missing_timing(self):
        helpers=script_between('function money(n){','let refreshController=null')
        self.run_js(r'''
const assert=require('node:assert/strict');
const T=s=>s,LANG='zh',LOCALE=()=>'zh-CN',num=n=>String(n),compact=n=>String(n),Tc=(n,s)=>s,esc=s=>String(s),ms=n=>String(n);
''' + helpers + script_between('function speedPanel(s){','function ensureModelDetail(){') + r'''
const html=speedPanel({requests:20,tps_requests:12,output_tps:35.34,tps_median:29.7,tps_p10:9.5,tps_p90:154.6,mean_ms:25700});
assert.match(html,/测速请求 12 \/ 20/);
assert.match(html,/<b>35\.3<\/b><span>平均 tokens\/s/);
assert.match(html,/<b>9\.5 – 155<\/b>/);
assert.match(html,/<b>25\.7s<\/b><span>平均响应时间/);
assert.match(speedPanel({requests:3,tps_requests:0}),/没有耗时记录/);
assert.equal(speedPanel(null),'');
''')

    def test_latest_model_request_owns_rows_and_error_is_not_empty_success(self):
        self.run_js(r'''
const assert=require('node:assert/strict');const bill={platform:'codex',model:'demo'};
let curView='bill';const $=()=>({value:'all'}),pending=[];function renderBilling(){}
global.fetch=()=>new Promise(resolve=>pending.push(resolve));
''' + script_between("let modelDetail={key:", 'function chartBuckets(') + r'''
(async()=>{
 ensureModelDetail();modelDetail.key='';ensureModelDetail();
 pending[1]({ok:true,json:async()=>({recent:[{id:'new'}]})});
 await new Promise(resolve=>setImmediate(resolve));
 pending[0]({ok:true,json:async()=>({recent:[{id:'old'}]})});
 await new Promise(resolve=>setImmediate(resolve));
 assert.deepEqual(modelDetail.rows,[{id:'new'}]);
 modelDetail.key='';ensureModelDetail();pending[2]({ok:false,status:503});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(modelDetail.error,'HTTP 503');
})().catch(e=>{console.error(e);process.exitCode=1;});
''')

    def test_router_filter_race_keeps_selection_separate_from_console_filters(self):
        from console.router_ui import JS as router_js
        start=router_js.index('let routerData=')
        end=router_js.index('\nasync function routerRun',start)
        self.run_js(r'''
const assert=require('node:assert/strict');
const nodes={'router-note':{textContent:'',classList:{toggle(){}}},'router-main':{hidden:false},'router-launch':{hidden:false},
  'dd-router-period':{},'dd-router-provider':{},period:{value:'month'},platform:{value:'codex'}};
const $=id=>nodes[id],T=s=>s,periodItems=[{v:'all',l:'全部时间'},{v:'today',l:'今天'},{v:'week',l:'本周'},{v:'month',l:'本月'}];
const stored={},localStorage={getItem:k=>stored[k]||null,setItem:(k,v)=>stored[k]=v};let routerContentKey='';const rendered=[],pending=[];
function ddSync(){}function renderRouter(){rendered.push(routerData)}function centerApi(url){return new Promise(resolve=>pending.push({url,resolve}));}
''' + router_js[start:end] + r'''
(async()=>{
 setRouterFilters('today','all');setRouterFilters('all','AMD TokenFactory 2');
 assert.equal(nodes.period.value,'month');assert.equal(nodes.platform.value,'codex');
 assert.equal(stored['cg-router-period'],'all');assert.equal(stored['cg-router-provider'],'AMD TokenFactory 2');
 assert.equal(new URLSearchParams(pending[0].url.split('?')[1]).get('period'),'today');
 pending[0].resolve({connected:true,marker:'stale'});await new Promise(resolve=>setTimeout(resolve,5));
 assert.equal(pending.length,2);
 const finalQuery=new URLSearchParams(pending[1].url.split('?')[1]);
 assert.equal(finalQuery.get('period'),'all');assert.equal(finalQuery.get('provider'),'AMD TokenFactory 2');
 pending[1].resolve({connected:true,marker:'latest'});await new Promise(resolve=>setTimeout(resolve,5));
 assert.deepEqual(rendered.map(x=>x.marker),['latest']);assert.equal(routerPeriod,'all');assert.equal(routerProvider,'AMD TokenFactory 2');
 routerPeriod='today';routerProvider='all';initRouterFilters();assert.equal(routerPeriod,'all');assert.equal(routerProvider,'AMD TokenFactory 2');
})().catch(e=>{console.error(e);process.exitCode=1;});
''')
        self.assertIn('id="dd-router-period"',PAGE)
        self.assertIn('id="dd-router-provider"',PAGE)
        filterchip=script_between('function syncFilterChip(){','\nfunction applyView(')
        self.run_js(r'''
const assert=require('node:assert/strict');let curView='router';const nodes={period:{value:'month'},filterchip:{style:{},textContent:''}};const $=id=>nodes[id],T=s=>s,PERIODS={month:'本月'};
''' + filterchip + r'''
syncFilterChip();assert.equal(nodes.filterchip.style.display,'none');assert.equal(nodes.period.value,'month');
curView='overview';syncFilterChip();assert.equal(nodes.filterchip.style.display,'block');
''')

    def test_navigation_is_focusable_and_modal_uses_native_focus_containment(self):
        class Controls(HTMLParser):
            def __init__(self):super().__init__();self.nav=[];self.dialogs=[];self.ids=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if 'nav-item' in a.get('class','').split():self.nav.append((tag,a))
                if tag=='dialog':self.dialogs.append(a)
                if 'id' in a:self.ids.append(a['id'])
        p=Controls();p.feed(PAGE)
        self.assertEqual(len(p.nav),16)
        self.assertTrue(all(tag=='button' and a.get('type')=='button' for tag,a in p.nav))
        modal=next(x for x in p.dialogs if x.get('id')=='modal')
        self.assertEqual(modal['aria-labelledby'],'modal-title')
        self.assertEqual(len(p.ids),len(set(p.ids)))

    def test_generated_scripts_parse(self):
        for script in re.findall(r'<script>([\s\S]*?)</script>',PAGE):
            if not shutil.which('node'):self.skipTest('Node unavailable')
            result=subprocess.run(['node','--check'],input=script,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_native_selects_get_dd_overlay_and_focus_trap_skips_hidden_native(self):
        # Every native <select> is covered by the dd look via one generic enhancer;
        # the hidden native stays the value source and must not take focus in dialogs.
        self.assertIn('function ddSelect(',PAGE)
        self.assertIn('function ddSelectAll(',PAGE)
        self.assertIn('.dd-native{position:absolute!important;',PAGE)
        self.assertIn('select:not(:disabled):not(.dd-native)',PAGE)

    def test_sidebar_collapse_animates_and_narrow_screens_stay_usable(self):
        # The collapse must animate via max-width/opacity, not display:none
        # (which cannot transition), and the icon must rotate.
        self.assertIn('transition:width',PAGE)
        self.assertIn('body.sidemini .brand span,body.sidemini .nav-item span{max-width:0',PAGE)
        self.assertIn('body.sidemini .nav-toggle svg{transform:rotate(180deg)}',PAGE)
        self.assertIn('transition:margin-left',PAGE)
        self.assertNotIn('body.sidemini .brand span,body.sidemini .nav-item span{display:none}',PAGE)
        # Toggle state persists and announces itself.
        self.assertIn("localStorage.getItem('cg-side')==='mini'",PAGE)
        self.assertIn("localStorage.setItem('cg-side',m?'mini':'full')",PAGE)
        self.assertIn("setAttribute('aria-expanded',String(!document.body.classList.contains('sidemini'))",PAGE)
        # Narrow screens turn the rail into a horizontal bar; labels stay
        # visible there even while body.sidemini is set.
        narrow=script_between('@media (max-width:55em){','@media (max-width:38em){')
        self.assertIn('body.sidemini .nav-item span{max-width:160px;opacity:1;transform:none;visibility:visible',narrow)
        self.assertIn('main,body.sidemini main{margin-left:0',narrow)

    def test_gate_section_show_writes_inline_block_not_empty(self):
        # The stylesheet hides every non-overview view
        # (main [data-view]:not([data-view=overview]){display:none}), so the
        # show path must set an inline 'block'. Writing '' clears applyView's
        # inline display and the section falls back to hidden — the filters
        # and the task list vanish exactly like the details were "lost".
        self.assertIn("main [data-view]:not([data-view=overview]){display:none}",PAGE)
        self.assertIn("sec.style.display='block'",PAGE)
        self.assertNotIn("sec.style.display=''",PAGE)

    def test_group_layout_shows_one_conversation_unless_split(self):
        from console import group_ui
        # Every element the group script looks up must exist in the group markup
        # (the two paging buttons are created inside the native-history modal).
        used=set(re.findall(r"\$\('(group-[\w-]+)'\)",group_ui.JS))-{'group-native-prev','group-native-next'}
        self.assertEqual(used-set(re.findall(r'id="([\w-]+)"',group_ui.HTML)),set())
        # Single pane by default: one of brief/detail is hidden unless .split is on,
        # and narrow screens stack instead of squeezing columns side by side.
        self.assertIn('.group-grid:not(.split):not(.gt-anim).show-member>.group-brief,.group-grid:not(.split):not(.show-member):not(.gt-anim)>.group-detail{display:none}',PAGE)
        self.assertIn('@media(max-width:55em){section[data-view=group]{margin-bottom:16px}.group-grid,.group-grid.split{display:flex;flex-direction:column;height:auto!important',PAGE)
        # Saved pixel column widths are what squeezed the old three-column grid.
        self.assertNotIn('cg-gcols',PAGE)
        # Esc only closes the @ menu; setting [hidden] meant it never opened again.
        self.assertNotIn("$('group-menu').hidden=true",PAGE)
        # The member rail collapses like the main nav and remembers its state;
        # "side by side" stays clickable and explains itself instead of going dead.
        self.assertIn('id="group-side-toggle"',PAGE)
        self.assertIn("localStorage.setItem('cg-gside'",PAGE)
        self.assertIn('.side-mini .gm-abbr{display:block}',PAGE)
        self.assertNotIn("b.disabled=!can",PAGE)
        # The page head is gone from the group view so the conversation starts higher.
        self.assertNotIn('<div class="pagehead" data-view="group">',PAGE)

    def test_group_ratio_clamps_each_pane_and_keeps_saved_preference(self):
        from console import group_ui
        start=group_ui.JS.index('function applyGroupRatio(')
        end=group_ui.JS.index('\nfunction groupLayout()',start)
        self.run_js(r'''
const assert=require('node:assert/strict');
const props={};let grid={clientWidth:1180,style:{getPropertyValue:k=>props[k]||'',setProperty:(k,v)=>props[k]=v}};
global.document={querySelector:()=>grid};
''' + group_ui.JS[start:end] + r'''
function check(width,side,pref){grid.clientWidth=width;props['--gside']=side+'px';const ratio=applyGroupRatio(pref),available=width-side-32;assert.ok(available*ratio>=370);assert.ok(available*(1-ratio)>=370);return ratio;}
assert.ok(check(1180,56,.3)>.3);assert.ok(check(1180,56,.7)<.7);
assert.ok(Math.abs(check(995,219,.3)*744-371)<.01);
const saved=.3;check(1500,248,saved);assert.equal(saved,.3);
''')

    def test_group_toggle_clears_previous_timer_and_skips_reduced_motion(self):
        from console import group_ui
        start=group_ui.JS.index('function groupAnimLayout(')
        end=group_ui.JS.index("\n$('group-side-toggle')",start)
        self.run_js(r'''
const assert=require('node:assert/strict');let groupSideAnimTimer=null,groupSideMini=false,reduceMotion=false,renders=0,next=0;
const active=new Set(),cleared=[];const timers={};
global.setTimeout=(fn)=>{const id=++next;timers[id]=fn;return id};global.clearTimeout=id=>{cleared.push(id)};
global.matchMedia=()=>({matches:reduceMotion});global.localStorage={setItem(){}};global.groupRender=()=>{renders++};
const grid={classList:{toggle:(name,on)=>on?active.add(name):active.delete(name),remove:name=>active.delete(name)}};
global.document={querySelector:()=>grid};
''' + group_ui.JS[start:end] + r'''
for(let i=0;i<20;i++)toggleGroupSide();assert.equal(groupSideMini,false);assert.equal(cleared.length,19);
assert.ok(active.has('gt-anim'));timers[next]();assert.equal(groupSideAnimTimer,null);assert.ok(!active.has('gt-anim'));
reduceMotion=true;const before=next;toggleGroupSide();assert.equal(next,before);assert.ok(!active.has('gt-anim'));assert.equal(renders,22);
''')

    def test_dropdown_menu_opens_with_keyframe_animation(self):
        # The menu toggles display, so a transition never runs; opening must use keyframes.
        self.assertIn('animation:ddIn .22s cubic-bezier(.33,1,.68,1)}',PAGE)
        self.assertIn('@keyframes ddIn{from{opacity:0;transform:translateY(-6px) scaleY(.96)}to{opacity:1;transform:none}}',PAGE)
        # Closing plays its own keyframes (same name would not restart) before the menu is really hidden.
        self.assertIn('.dd.closing:not(.open) .dd-menu{display:block;visibility:visible;pointer-events:none;transform-origin:top;animation:ddOut .16s cubic-bezier(.33,1,.68,1) forwards}',PAGE)
        self.assertIn('@keyframes ddOut{from{opacity:1;transform:none}to{opacity:0;transform:translateY(-6px) scaleY(.96)}}',PAGE)
        self.assertIn("root.classList.add('closing');root.__ddCloseT=setTimeout(hide,180);",PAGE)

    def test_group_split_toggle_animates_on_fixed_three_tracks(self):
        from console import group_ui
        # Split and single view share one three-track template, so the change can interpolate.
        self.assertIn('grid-template-columns:var(--gside) minmax(0,var(--ga,1fr)) minmax(0,var(--gb,0fr))',group_ui.CSS)
        # The "并排/单栏" button goes through the same animated helper as the member rail.
        wide=group_ui.JS[group_ui.JS.index("$('group-wide').onclick="):]
        self.assertIn('groupAnimLayout(',wide[:wide.index('\n')])
        self.assertIn('function toggleGroupSide(){groupAnimLayout(',group_ui.JS)
        # The hidden pane is only removed at rest, so the closing pane can still fade out.
        self.assertIn(':not(.gt-anim)>.group-detail{display:none}',group_ui.CSS)

    def test_group_layout_feed_key_and_collapsed_labels_are_stateful(self):
        from console import group_ui
        key=group_ui.JS[group_ui.JS.index('function groupFeedKey()'):group_ui.JS.index('\nfunction groupBriefAria',group_ui.JS.index('function groupFeedKey()'))]
        brief=group_ui.JS[group_ui.JS.index('function groupBriefAria('):group_ui.JS.index('\n// 并排时两个会话区',group_ui.JS.index('function groupBriefAria('))]
        row_start=group_ui.JS.index(' const row=m=>')+1
        row_end=group_ui.JS.index('\n const live=',row_start)
        row=group_ui.JS[row_start:row_end]
        status=group_ui.JS[group_ui.JS.index('const GROUP_STATUS='):group_ui.JS.index('\nconst groupActive')]
        self.run_js(r'''
const assert=require('node:assert/strict');let groupId='g',groupMember='m',groupFocus='member',split=false;
''' + key + r'''
const old=groupFeedKey();split=true;assert.equal(groupFeedKey(),old);groupMember='n';assert.notEqual(groupFeedKey(),old);
const T=s=>s;
''' + status + r'''
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const shown=()=>false,state=m=>m.status,sub=m=>m.platform+' · '+m.model+' · '+m.effort;
''' + row + r'''
assert.match(row({id:'1',slug:'nova',status:'running',platform:'Codex',model:'model-x',effort:'high'}),/aria-label="@nova · 执行中 · Codex · model-x · high"/);
''' + brief + r'''
assert.equal(groupBriefAria(3),'群内简报 · 3 未读消息');assert.equal(groupBriefAria(0),'群内简报 · 无未读消息');
''')

    def test_backboard_uses_existing_platform_and_model_billing(self):
        self.assertNotIn('id="backboard-billing"', PAGE)
        self.assertNotIn('function renderBackboardBilling(', PAGE)
        self.assertIn("if(m.provider_billed_usd)", PAGE)

    def test_billing_bars_sort_by_tokens_with_both_modes_in_markup(self):
        self.assertIn('id="bill-mode"', PAGE)
        self.assertIn('data-mode="cost"', PAGE)
        helpers=script_between('function tok(n){','let refreshController=null')
        billing=script_between('function renderBilling(){',"\n$('bill-tiles').addEventListener")
        self.run_js(r'''
const assert=require('node:assert/strict');const T=s=>s,LANG='zh',num=n=>String(n||0),compact=n=>String(n||0),Tc=(n,s)=>s,esc=s=>String(s),money=n=>'$'+n;
const els=Object.fromEntries(['bill-sums','bill-viz','bill-back','bill-crumb','bill-tiles','bill-detail','bill-note','period'].map(id=>[id,{style:{},innerHTML:'',value:'all'}]));
const $=id=>els[id],reconcile=(el,html)=>el.innerHTML=html;
let bill={platform:null,model:null},billTargets=[],modelDetail={key:'',rows:null,error:''};
const lastData={by_platform:[
 {platform:'zcode',requests:3,input_tokens:100,output_tokens:50,cost_actual_usd:0.5,unpriced_requests:0},
 {platform:'claude',requests:5,input_tokens:2000,output_tokens:1000,cost_actual_usd:4,unpriced_requests:0},
 {platform:'router',requests:9,input_tokens:90000,output_tokens:10000,cost_actual_usd:0,unpriced_requests:0}
],by_model:[],global_ab:{pairs:0},unpriced_models:[],prices_file:'prices.json'};
''' + helpers + '\n' + billing + r'''
renderBilling();
assert.ok(!('backboard-billing' in els));
const html=els['bill-viz'].innerHTML;
const rows=html.split(/<div[^>]+class="brow"/).slice(1);
assert.equal(rows.length,3);
assert.ok(rows[0].includes('Claude')&&rows[1].includes('Local Model Router')&&rows[2].includes('ZCode'));
rows.forEach(r=>assert.ok(r.includes('data-k="')&&r.includes('--wc:')&&r.includes('--wu:')&&r.includes('data-n=')));
assert.ok(rows[0].includes('--du:1;')&&rows[0].includes('--dc:0"'));
assert.ok(rows[1].includes('--du:-1;')&&rows[1].includes('--dc:1"'));
assert.ok(rows[2].includes('--du:0;')&&rows[2].includes('--dc:-1"'));
assert.ok(rows[1].includes('免费')&&!rows[1].includes('$0'));
assert.ok(rows[1].includes('--wu:100%'));
assert.ok(rows[0].includes('--wc:100%'));
''')

    def test_deepai_billing_shows_access_without_a_cursor_platform(self):
        helpers=script_between('function tok(n){','let refreshController=null')
        billing=script_between('function renderBilling(){',"\n$('bill-tiles').addEventListener")
        self.run_js(r'''
const assert=require('node:assert/strict');const T=s=>s,LANG='zh',num=n=>String(n||0),compact=n=>String(n||0),Tc=(n,s)=>s,esc=s=>String(s),money=n=>'$'+n;
const els=Object.fromEntries(['bill-sums','bill-viz','bill-back','bill-crumb','bill-tiles','bill-detail','bill-note','period'].map(id=>[id,{style:{},innerHTML:'',value:'all'}]));
const $=id=>els[id],reconcile=(el,html)=>el.innerHTML=html;
let bill={platform:null,model:null},billTargets=[],modelDetail={key:'',rows:null,error:''};
const lastData={by_platform:[
 {platform:'deepai',requests:4,input_tokens:1000,output_tokens:10,cost_actual_usd:1.25,unpriced_requests:1},
 {platform:'codex',requests:2,input_tokens:50,output_tokens:5,cost_actual_usd:0.2,unpriced_requests:0}
],by_model:[
 {platform:'deepai',model:'gpt-6.1-sol',free:false,priced:true,requests:2,actual_input:100,actual_output:10,cost_actual_usd:1,sources:['codex']},
 {platform:'deepai',model:'glm-5.3-flash',free:false,priced:true,requests:1,actual_input:80,actual_output:8,cost_actual_usd:0.25,sources:['direct']},
 {platform:'deepai',model:'grok-4.7',free:false,priced:false,requests:1,actual_input:40,actual_output:4,cost_actual_usd:0,sources:['cursor'],unpriced_requests:1}
],global_ab:{pairs:0},unpriced_models:['grok-4.7'],prices_file:'prices.json'};
''' + helpers + '\n' + billing + r'''
renderBilling();
assert.match(els['bill-viz'].innerHTML,/DeepAI Code/);
assert.doesNotMatch(els['bill-viz'].innerHTML,/Cursor</);
bill.platform='deepai';renderBilling();
const tiles=els['bill-tiles'].innerHTML;
assert.match(tiles,/Codex 接入/);
assert.match(tiles,/直接调用/);
assert.match(tiles,/Cursor 接入/);
assert.match(tiles,/gpt-6\.1-sol/);
assert.doesNotMatch(tiles,/data-bill-platform="cursor"/);
''')

    def test_tween_math_and_animation_hooks_exist(self):
        for needle in ('function setNum','function tweenNum','function reconcileKeyed','k-enter','k-leave'):
            self.assertIn(needle,PAGE)
        self.run_js(r'''
const assert=require('node:assert/strict');
''' + script_between('function tweenAt(','function tweenNum(') + r'''
assert.equal(tweenAt(0,100,0),0);assert.equal(tweenAt(0,100,1),100);
const m=tweenAt(0,100,.5);assert.ok(m>0&&m<100);
assert.equal(tweenAt(100,0,0),100);assert.equal(tweenAt(100,0,1),0);
const d=tweenAt(100,0,.5);assert.ok(d>0&&d<100);
''')

    def test_free_same_name_model_drilldown_keeps_its_source(self):
        helpers=script_between('function tok(n){','let refreshController=null')
        billing=script_between('function renderBilling(){',"\n$('bill-tiles').addEventListener")
        detail_key=script_between('function detailKey(){','\nfunction ensureModelDetail()')
        self.run_js(r'''
const assert=require('node:assert/strict');const T=s=>s,LANG='zh',num=n=>String(n||0),compact=n=>String(n||0),Tc=(n,s)=>s,esc=s=>String(s),money=n=>'$'+n;
const els=Object.fromEntries(['bill-sums','bill-viz','bill-back','bill-crumb','bill-tiles','bill-detail','bill-note','period'].map(id=>[id,{style:{},innerHTML:'',value:'all'}]));
const $=id=>els[id],reconcile=(el,html)=>el.innerHTML=html;
let bill={platform:'__free__',model:null},billTargets=[],modelDetail={key:'',rows:null,error:''};
const lastData={by_platform:[{platform:'router',requests:1,cost_actual_usd:0},{platform:'zcode',requests:1,cost_actual_usd:0.1}],by_model:[
 {platform:'router',model:'GLM-5.3-Flash',free:true,priced:true,requests:1,actual_input:100,actual_output:10,cost_actual_usd:0},
 {platform:'zcode',model:'GLM-5.3-Flash',free:false,priced:true,requests:1,actual_input:100,actual_output:10,cost_actual_usd:0.1}
],global_ab:{pairs:0},unpriced_models:[],prices_file:'prices.json'};
''' + helpers + '\n' + billing + '\n' + detail_key + r'''
bill.platform=null;renderBilling();
assert.match(els['bill-viz'].innerHTML,/data-bill-platform="router"/);
assert.match(els['bill-tiles'].innerHTML,/Local Model Router/);
assert.match(els['bill-tiles'].innerHTML,/查看明细/);
assert.match(els['bill-tiles'].innerHTML,/free-shortcut/);
bill.platform='__free__';renderBilling();
assert.deepEqual(billTargets,[{platform:'router',model:'GLM-5.3-Flash'}]);
assert.match(els['bill-tiles'].innerHTML,/Local Model Router/);
bill.platform=billTargets[0].platform;bill.model=billTargets[0].model;
assert.equal(detailKey(),'all|router|GLM-5.3-Flash');
''')

    def test_bedrock_catalog_tab_is_wired(self):
        self.assertIn('data-router-tab="bedrock"', PAGE)
        self.assertIn('list_bedrock_models', PAGE)
        self.assertIn('set_bedrock_model_enabled', PAGE)
        self.assertIn('bedrock_sync_status', PAGE)
        self.assertIn('官方价格页', PAGE)


class SurfaceHierarchyTests(unittest.TestCase):
    def test_surface_css_is_last_style_block(self):
        from console.app import PAGE
        from console.surface_ui import CSS
        self.assertEqual(PAGE.index(CSS) + len(CSS) + 1, PAGE.index('</style>'))
        self.assertIn('main :is(#workbench,#gt-list,section) :is(.wb-item', CSS)
