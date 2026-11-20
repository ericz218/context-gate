"""Group UI fragments, sharing the console's theme and native controls."""
CSS = r'''
/* 群组自绘 dd：整行点选（shift 范围选）、「进入」切群、归档/删除两类操作 */
.group-dd-item{display:flex;align-items:center;gap:8px;cursor:pointer;padding-left:6px;padding-right:6px}
.group-dd-item .group-dd-name{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.group-dd-item input.group-dd-check{flex:0 0 auto;width:15px;height:15px;pointer-events:none;accent-color:var(--accent)}
.group-dd-item.archived{opacity:.55;cursor:default}
.group-dd-enter,.group-dd-restore{flex:0 0 auto;font-size:11px;padding:2px 8px}
.group-dd-actions{display:flex;gap:8px;padding:4px 6px 8px;border-bottom:1px solid var(--line);margin-bottom:4px}
.group-dd-actions button{flex:1}
.group-dd-actions button:disabled{opacity:.4;cursor:default}
.group-dd-archived-head{padding:6px;font-size:11px;color:var(--muted);border-top:1px solid var(--line);margin-top:4px}
#group-dd{max-width:320px}#group-dd .dd-menu{min-width:260px}#group-dd .dd-btn{max-width:320px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#group-usage .usage-warning{color:var(--warn);border-left:3px solid var(--warn);padding:6px 10px}
.group-pane[hidden],.group-menu[hidden],#group-stop-menu[hidden]{display:none!important}
/* 版式：顶栏（群管理）＋左侧成员栏＋会话区。会话区默认只显示一个（群内简报或某个成员），够宽时可并排两个。 */
section[data-view=group]{padding:0;border:0;background:none;box-shadow:none;backdrop-filter:none;-webkit-backdrop-filter:none;margin-bottom:-24px;overflow:visible}
:root[data-theme] section[data-view=group]{background:none;border:0;box-shadow:none}
.group-toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.group-top{padding:4px 8px;margin-bottom:16px}.group-top button,.group-top .dd-btn{height:36px;white-space:nowrap}
#group-project{font-size:12px;color:var(--muted);padding:0 4px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#group-note{flex:1 1 200px;min-width:0;margin:0;font-size:12px;line-height:1.4;text-align:right;overflow-wrap:anywhere}#group-note.live{color:var(--text)}
.group-grid{position:relative;display:grid;--gside:clamp(200px,22%,248px);grid-template-columns:var(--gside) minmax(0,var(--ga,1fr)) minmax(0,var(--gb,0fr));gap:16px;height:calc(100dvh - 156px);min-height:440px}
.group-grid.gt-anim>.group-pane{transition:margin .24s cubic-bezier(.2,.75,.25,1),opacity .24s cubic-bezier(.2,.75,.25,1)}
.group-grid.gt-anim{transition:grid-template-columns .24s cubic-bezier(.2,.75,.25,1)}
.group-grid:not(.split):not(.gt-anim).show-member>.group-brief,.group-grid:not(.split):not(.show-member):not(.gt-anim)>.group-detail{display:none}
/* 动画中正在收起的那一栏：保留渲染但淡出、宽度压到 0 */
.group-grid.gt-anim:not(.split).show-member>.group-brief,.group-grid.gt-anim:not(.split):not(.show-member)>.group-detail{opacity:0;overflow:hidden;min-width:0;pointer-events:none}
/* 三栏固定，单栏时空出的那一栏抵掉 16px 列距（负外边距），两种版式才能插值；窄屏是竖排，不用这些规则 */
@media not all and (max-width:55em){.group-side{grid-column:1}.group-brief{grid-column:2}.group-detail{grid-column:3}.group-grid:not(.split):not(.show-member)>.group-brief{margin-right:-16px}.group-grid:not(.split).show-member>.group-detail{margin-left:-16px}}
.group-grid .grip{display:none;position:absolute;top:0;bottom:0;width:12px;cursor:col-resize;z-index:5;touch-action:none}
.group-grid.split .grip{display:block}
.group-grid .grip::after{content:"";position:absolute;left:5px;top:16px;bottom:16px;width:2px;border-radius:1px;background:var(--line2);opacity:0;transition:opacity .12s ease}
.group-grid .grip:hover::after{opacity:1}.group-grid .grip.dragging::after{opacity:1;background:var(--accent)}
.group-grid.gt-anim .grip{display:none}
.group-side{display:flex;flex-direction:column;gap:8px;min-width:0;min-height:0;overflow:hidden;padding:12px;border:1px solid var(--glassline);border-radius:12px;background:var(--cardT);box-shadow:inset 0 1px 0 var(--hl)}
.group-side-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:4px;padding-left:12px}
.group-side-head h3{margin:0;font-size:12px;font-weight:600;color:var(--muted)}
.group-side-head button,.group-side-foot button{font-size:12px;padding:4px 12px;white-space:nowrap}
.group-side-foot{display:flex;gap:8px}.group-side-foot button{flex:1;min-width:0}
#group-members{flex:1;min-height:0;overflow-y:auto;display:flex;flex-direction:column;gap:4px}#group-members>p{margin:0;padding:8px 12px;font-size:12px}
.group-member,.group-channel{display:grid;grid-template-columns:8px minmax(0,1fr) auto;column-gap:8px;align-items:center;flex:none;width:100%;height:auto;min-height:52px;padding:8px 12px;text-align:left;white-space:normal;border-color:transparent;background:transparent;transition:background-color .12s ease,border-color .12s ease}
.group-member:hover,.group-channel:hover{background:var(--rowhover);border-color:transparent}
.group-member.on,.group-channel.on{background:var(--accentbg);border-color:var(--accent)}
.gm-dot{width:8px;height:8px;border-radius:50%;border:1.5px solid var(--muted)}
.gm-dot.all{border-radius:2px;border-color:var(--accent)}.gm-dot.queued{background:var(--warn);border-color:var(--warn)}.gm-dot.stopping{background:var(--bad);border-color:var(--bad)}
.gm-dot.running{background:var(--accent);border-color:var(--accent);animation:gmPulse 1.4s ease-in-out infinite}@keyframes gmPulse{50%{opacity:.35}}
.gm-name{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gm-state{font-size:12px;color:var(--muted);white-space:nowrap}.gm-state.busy{color:var(--accent)}
.gm-sub{grid-column:2/-1;font-size:12px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#group-brief-badge:not(:empty){min-width:20px;padding:0 6px;border-radius:10px;background:var(--accent);color:var(--onaccent);font-weight:600;text-align:center}
.group-removed{margin:4px 0 0}.group-removed summary{padding:8px 12px}.group-removed .group-member{opacity:.62;margin-top:4px}
#group-add{display:inline-flex;align-items:center;gap:4px}
.gm-abbr{display:none;font-weight:600;font-size:12px}
.group-side-toggle{display:flex;align-items:center;justify-content:center;flex:none;min-height:32px;padding:0;border:0;background:transparent;color:var(--muted)}
.group-side-toggle:hover{color:var(--text);background:var(--rowhover)}
.group-side-toggle svg{transition:transform .24s cubic-bezier(.2,.75,.25,1)}
/* 成员栏收起：只留一条 56px 的窄栏，成员显示两字缩写＋状态点，完整信息在悬停提示里。 */
.side-mini .group-side{padding:12px 7px}
.side-mini .group-side-toggle svg{transform:rotate(180deg)}
.side-mini .group-side-head{padding-left:0;margin-top:0;justify-content:center}
.side-mini .group-side-head h3,.side-mini .gs-label,.side-mini .group-side-foot,.side-mini .group-removed,.side-mini .gm-name,.side-mini .gm-sub,.side-mini .group-member .gm-state{display:none}
.side-mini #group-add{width:40px;padding:4px 0;justify-content:center}
.side-mini .group-member,.side-mini .group-channel{position:relative;display:flex;align-items:center;justify-content:center;min-height:40px;padding:0}
.side-mini .gm-abbr{display:block}
.side-mini .group-member .gm-dot{position:absolute;top:4px;right:4px}
.side-mini .gm-dot.all{width:12px;height:12px;border-radius:3px}
.side-mini #group-brief-badge:empty{display:none}
.side-mini #group-brief-badge:not(:empty){position:absolute;top:-2px;right:-2px;min-width:16px;padding:0 4px;font-size:10px;line-height:16px}
#group-wide[aria-disabled=true]{opacity:.5}
.group-pane{border:1px solid var(--glassline);border-radius:12px;background:var(--cardT);box-shadow:inset 0 1px 0 var(--hl);padding:16px;min-width:0;min-height:0;display:flex;flex-direction:column;gap:12px}
.group-pane-head{display:flex;align-items:center;gap:8px 12px;flex-wrap:wrap;min-height:32px}
.group-pane-head h3{margin:0;font-size:16px;font-weight:650;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.gp-tag{font-size:12px;color:var(--muted);padding:2px 8px;border-radius:10px;background:var(--mutbg);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}.gp-tag:empty{display:none}
.gp-actions{margin-left:auto;display:flex;gap:8px}.gp-actions button{font-size:12px;padding:4px 12px;white-space:nowrap}
.group-meta{display:flex;flex-wrap:wrap;gap:4px 16px;font-size:12px;line-height:1.5}.group-meta p{margin:0;overflow-wrap:anywhere}.group-meta p:empty{display:none}
#group-usage{flex-basis:100%}#group-usage:empty{display:none}
#group-usage .usage-warning{color:var(--warn);background:var(--warnbg);border-left:3px solid var(--warn);border-radius:0 6px 6px 0;padding:4px 12px}
.group-feed{min-height:0;overflow-y:auto;flex:1;display:flex;flex-direction:column;gap:12px;padding:4px max(0px,calc((100% - 880px)/2));scrollbar-gutter:stable both-edges}
.group-feed>p.muted{margin:auto;text-align:center}
.group-swap{animation:gswap .18s ease-out}@keyframes gswap{from{opacity:.35;transform:translateY(4px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){.group-swap{animation:none}}
.group-message{flex:none;padding:12px 16px;border-radius:10px;background:var(--chip);box-shadow:inset 0 1px 0 var(--hl);line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere;min-width:0}
.group-message small{display:block;color:var(--muted);font-size:12px;margin-bottom:4px}.group-message.user{border-left:2px solid var(--accent)}
.group-feed .group-message.user{align-self:flex-end;max-width:min(88%,640px);border-left:0;background:var(--accentbg);box-shadow:none}
.group-message.error{border-left:2px solid var(--bad)}.group-message code{font-family:ui-monospace,Menlo,monospace;font-size:.88em;padding:1px 5px;border-radius:4px;background:var(--mutbg)}.group-message strong{font-weight:600}.group-message pre{white-space:pre-wrap;overflow-wrap:anywhere;margin:8px 0 0}
.group-message.tool{padding:8px 16px;background:transparent;box-shadow:none;border:1px solid var(--line)}.group-message.tool small{margin:0}.group-message.tool details{margin:0}
.group-compose{position:relative;flex:none;width:100%;max-width:880px;margin:0 auto}
.group-compose textarea{display:block;width:100%;field-sizing:content;min-height:48px;max-height:40dvh;resize:vertical;background:var(--card2);color:var(--text);border:1px solid var(--line2);border-radius:10px;padding:12px;font:inherit;line-height:1.5}
.group-compose textarea:focus{outline:2px solid var(--accent);outline-offset:2px}
.group-compose .group-menu{position:absolute;bottom:100%;left:0;right:0;max-height:240px;overflow:auto;background:var(--glassbg);backdrop-filter:blur(22px) saturate(160%);-webkit-backdrop-filter:blur(22px) saturate(160%);border:1px solid var(--line2);border-radius:8px;box-shadow:var(--panelshadow);padding:8px;z-index:5;opacity:0;transform:translateY(6px);pointer-events:none;transition:opacity .18s ease-out,transform .18s ease-out}
.group-compose .group-menu.open{opacity:1;transform:none;pointer-events:auto}
.group-compose .group-menu.open button{animation:gmIn .18s ease-out backwards}
.group-compose .group-menu.open button:nth-child(2){animation-delay:60ms}
.group-compose .group-menu.open button:nth-child(3){animation-delay:120ms}
.group-compose .group-menu.open button:nth-child(4){animation-delay:180ms}
@keyframes gmIn{from{opacity:0;transform:translateY(4px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion: reduce){.group-compose .group-menu{transition:none}.group-compose .group-menu.open button{animation:none}}
.group-menu button{display:block;width:100%;text-align:left;margin:4px 0;height:auto;min-height:40px}
.group-compose-row{position:relative;display:flex;align-items:center;gap:8px;margin-top:8px}
.group-compose-row .muted{font-size:12px;margin-right:auto;min-width:0}.group-compose-row button{flex:none;white-space:nowrap}
#group-send,#group-direct-send{background:var(--accent);border-color:transparent;color:var(--onaccent);font-weight:600}
#group-send.group-stop{background:transparent;border-color:var(--bad);color:var(--bad)}
#group-stop-menu{position:absolute;bottom:calc(100% + 8px);right:0;left:auto;width:min(320px,100%);max-height:240px;overflow:auto;background:var(--card);border:1px solid var(--line2);border-radius:10px;padding:8px;z-index:20;box-shadow:var(--panelshadow);transform-origin:bottom right;animation:stopUp .16s ease-out}
@keyframes stopUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
@media(prefers-reduced-motion:reduce){#group-stop-menu{animation:none}}
.group-attachments{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px}.group-attachments:empty{display:none}.group-chip{display:inline-flex;align-items:center;gap:8px;padding:4px 4px 4px 8px;border-radius:8px;background:var(--chip);border:1px solid var(--line2);font-size:12px;max-width:260px}.group-chip.pending{opacity:.6}.group-chip img{width:32px;height:32px;object-fit:cover;border-radius:4px}.group-chip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.group-chip button{min-height:24px;padding:0 8px}#group-form.drag textarea{outline:2px dashed var(--accent);outline-offset:2px}
.group-dialog{color:var(--text);background:var(--card);border:1px solid var(--line2);border-radius:16px;max-width:480px;width:90%;padding:24px}
.group-dialog::backdrop{background:rgba(8,9,12,.42);backdrop-filter:blur(10px) saturate(120%);-webkit-backdrop-filter:blur(10px) saturate(120%)}.group-dialog form{display:grid;gap:16px}#group-dialog-fields{display:grid;gap:12px}.group-dialog label{display:grid;gap:4px}
.group-dialog select,.group-dialog input{width:100%}#gd-fast{width:18px;height:18px;flex:none;margin:0;accent-color:var(--accent)}.group-choice{display:flex!important;align-items:center;gap:8px!important;padding:8px;border-radius:6px;cursor:pointer;transition:background-color .1s ease}.group-choice:hover{background:var(--rowhover)}
.group-choice input{width:auto!important}
/* 窄屏：成员栏叠在会话区上方，整页滚动；不提供并排。 */
@media(max-width:55em){section[data-view=group]{margin-bottom:16px}.group-grid,.group-grid.split{display:flex;flex-direction:column;height:auto!important;min-height:0}#group-members{flex:none;max-height:176px}.group-pane{height:min(84dvh,720px)}#group-wide{display:none}#group-note{flex-basis:100%;text-align:left}.group-side-toggle{display:none}}
'''

HTML = r'''
<section data-view="group" aria-label="群聊">
<div class="group-toolbar group-top"><div class="dd" id="group-dd"><button class="dd-btn" id="group-dd-btn" type="button" aria-expanded="false" aria-controls="group-dd-menu">选择群聊</button><div class="dd-menu" id="group-dd-menu"></div></div><button id="group-new">新建群聊</button><button id="group-rename">改名/换项目</button><span id="group-project"></span><p id="group-note" class="muted" role="status"></p><button id="group-more" hidden>继续加载历史</button><button id="group-wide" type="button" aria-pressed="false">并排</button></div>
<div class="group-grid"><div class="grip" aria-hidden="true"></div>
<aside class="group-side" aria-label="成员列表"><button type="button" class="group-channel on" id="group-brief-tab"><i class="gm-dot all"></i><span class="gm-name">群内简报</span><span class="gm-state" id="group-brief-badge"></span><span class="gm-sub">发给全部成员</span></button>
<div class="group-side-head"><h3>成员列表</h3><button id="group-add" title="添加成员" aria-label="添加成员"><span aria-hidden="true">＋</span><span class="gs-label">添加成员</span></button></div><div id="group-members"></div>
<div class="group-side-foot"><button id="group-model">换模型</button><button id="group-delete">移出成员</button></div><button type="button" class="group-side-toggle" id="group-side-toggle" aria-label="收起/展开成员栏" aria-expanded="true" title="收起/展开成员栏"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 3L5 8l4.5 5"/></svg></button></aside>
<div class="group-pane group-brief"><div class="group-pane-head"><h3>群内简报</h3></div><div id="group-main" class="group-feed" role="log" aria-label="群内简报"></div>
<form id="group-form" class="group-compose"><div id="group-menu" class="group-menu"></div><textarea id="group-input" aria-label="群聊消息" maxlength="12000" placeholder="输入 @ 指定成员；不指定则发给所有成员。输入 / 查看命令。"></textarea>
<div id="group-attachments" class="group-attachments" aria-live="polite"></div>
<div class="group-compose-row"><small class="muted" id="group-send-hint">发给全部成员</small><button id="group-attach" type="button" title="添加图片或文件（也可以拖进来或粘贴）">附件</button><button id="group-send" type="submit">发送</button><div id="group-stop-menu" hidden></div></div></form></div>
<div class="group-pane group-detail"><div class="group-pane-head"><h3 id="group-detail-title">成员聊天</h3><span class="gp-tag" id="group-detail-tag"></span><span class="gm-state" id="group-detail-state"></span><div class="gp-actions"><button id="group-open-native">打开原平台</button><button id="group-native-history">原平台历史</button></div></div>
<div class="group-meta"><p id="group-session" class="muted"></p><p id="group-actual-model" class="muted"></p><div id="group-usage"></div></div><div id="group-detail" class="group-feed" role="log" aria-label="成员聊天"></div>
<form id="group-direct-form" class="group-compose"><textarea id="group-direct" aria-label="成员消息" maxlength="12000" placeholder="直接给选中的成员发消息"></textarea><div class="group-compose-row"><small class="muted">同一原生聊天继续</small><button id="group-direct-send">发送给成员</button></div></form></div></div>
</section>
<dialog id="group-dialog" aria-labelledby="group-dialog-title" class="group-dialog"><form id="group-dialog-form"><h3 id="group-dialog-title"></h3><div id="group-dialog-fields"></div><p id="group-dialog-error" role="alert"></p><div class="group-toolbar"><button type="button" id="group-dialog-cancel">取消</button><button id="group-dialog-save">保存</button></div></form></dialog>
'''

JS = r'''
let groupId=localStorage.getItem('cg-group')||'',groupMember='',groupData=null,groupCursor=0,groupMessages=[],groupLoading=false,groupResetting=false,groupDialogAction='',groupStopOpen=false,groupGeneration=0,groupSending=false,groupHistoryGeneration=0,groupFiles=[];
// 版式状态：groupFocus 单栏时显示哪个会话；groupSplitPref 为 null 表示按宽度自动决定是否并排。
let groupFocus='main',groupSplitPref=null,groupSplitNow=false,groupRemovedOpen=false,groupSeenMain=0,groupSeenKey='',groupSideMini=false,groupCanSplit=false,groupSideAnimTimer=null,groupRatioPref=.5;
try{groupSplitPref=localStorage.getItem('cg-gsplit');groupSideMini=localStorage.getItem('cg-gside')==='mini';}catch(e){}
const groupDeleteSel=new Set(); // 待删除群聊的多选集合（dd 下拉里勾选）
let groupLastSelIndex=null;     // shift 范围选择的锚点（按可见列表序）
const GROUP_STATUS={attention:T('需人工核对'),uncertain:T('启动状态待核对'),idle:T('等待消息'),queued:T('排队中'),running:T('执行中'),stopping:T('停止中'),removed:T('已移出'),remote_queued:T('另一台排队中'),remote_starting:T('另一台准备执行'),remote_running:T('另一台执行中'),remote_stopping:T('另一台停止中')};
function groupMemberState(m){return m.removed?'removed':m.status==='idle'&&['attention','uncertain'].includes(m.latest_job_status)?m.latest_job_status:m.status;}
const groupActive=()=>groupData?.members?.filter(m=>!m.removed)||[];
function groupNotice(t){$('group-note').textContent=t;$('group-note').classList.add('live');}
async function groupLoad(reset=false){
 if(groupLoading&&!reset)return null;
 const generation=++groupGeneration,requestedGroup=groupId;groupLoading=true;const loadingGrid=document.querySelector('section[data-view=group] .group-grid');if(reset){groupResetting=true;if(loadingGrid)loadingGrid.inert=true;}
 if(reset){groupHistoryGeneration++;groupCursor=0;groupStopOpen=false;$('group-stop-menu').hidden=true;$('group-stop-menu').innerHTML='';}
 try{
  let d=await centerApi('groups'+(requestedGroup?'?id='+encodeURIComponent(requestedGroup)+'&after='+groupCursor:''));
  if(generation!==groupGeneration||requestedGroup!==groupId)return;
  groupData=d;if(reset)groupMessages=[];
  // 已删除/已归档的 groupId 自愈：列表里没有就回落到第一个群，避免整页卡死
  if(groupId&&!d.groups.some(g=>g.id===groupId)){groupId=d.groups.length?d.groups[0].id:'';localStorage.setItem('cg-group',groupId);groupLoading=false;return groupLoad(true);}
  renderGroupMenu();
  if(!groupId&&d.groups.length){groupId=d.groups[0].id;groupLoading=false;return groupLoad(true);}
  if(d.messages){groupMessages.push(...d.messages);groupCursor=d.cursor;}
  $('group-more').hidden=!d.has_more;
  if(!d.members?.some(m=>m.id===groupMember))groupMember=groupActive()[0]?.id||d.members?.[0]?.id||'';
  groupRender();return true;
 }catch(e){if(generation===groupGeneration){if(reset){groupData=null;groupMember='';groupMessages=[];groupRender();}groupNotice(e.message);}return false;}finally{if(generation===groupGeneration){groupLoading=false;if(reset){groupResetting=false;if(loadingGrid)loadingGrid.inert=false;}groupButton();}}
}
// 消息里的 **加粗** 与 `行内代码`：先整体转义，再只生成 strong/code 两种标签。
function groupFmt(text){return esc(text).split(/(`[^`\n]+`)/).map((part,i)=>i%2?'<code>'+part.slice(1,-1)+'</code>':part.replace(/\*\*([^*\n]+?)\*\*/g,'<strong>$1</strong>')).join('');}
function groupRender(){
 const members=groupData?.members||[],split=groupLayout(),shown=id=>id===groupMember&&(split||groupFocus==='member');
 const names=Object.fromEntries(members.map(m=>[m.id,m.slug]));
 const state=groupMemberState;
 const sub=m=>m.platform+' · '+m.model+' · '+m.effort+(m.mod_role?' · '+T(m.mod_role):'');
 const row=m=>'<button type="button" class="group-member'+(shown(m.id)?' on" aria-current="true':'')+'" data-member="'+esc(m.id)+'" title="'+esc('@'+m.slug+' · '+sub(m))+'" aria-label="'+esc('@'+m.slug+' · '+(GROUP_STATUS[state(m)]||state(m))+' · '+sub(m))+'"><i class="gm-dot '+esc(state(m))+'"></i><span class="gm-abbr" aria-hidden="true">'+esc(m.slug.slice(0,2).toUpperCase())+'</span><span class="gm-name">@'+esc(m.slug)+'</span><span class="gm-state'+(state(m)==='running'?' busy':'')+'">'+esc(GROUP_STATUS[state(m)]||state(m))+'</span><span class="gm-sub">'+esc(sub(m))+'</span></button>';
 const live=members.filter(m=>!m.removed),gone=members.filter(m=>m.removed);
 if(gone.some(m=>shown(m.id)))groupRemovedOpen=true;
 // 已移出的成员收进折叠区，不再和在岗成员挤在一起。
 reconcile($('group-members'),(live.map(row).join('')||'<p class="muted">'+T('添加一个成员，开始交代任务。')+'</p>')+(gone.length?'<details class="group-removed"'+(groupRemovedOpen?' open':'')+'><summary>'+T('已移出')+' · '+gone.length+'</summary>'+gone.map(row).join('')+'</details>':''));
 function renderFeed(id,rows,forceBottom){const el=$(id),hidden=!el.offsetParent;
  // 只有用户原本停在底部才跟随新消息；上滑看历史时刷新不动滚动位置。
  // 渲染时同步判断（不依赖滚动事件）：位置自上次渲染后被用户动过，才重新认定是否在底部。
  if(el._stick===undefined||(!hidden&&el.dataset.pendingBottom))el._stick=true;else if(!hidden&&el.scrollTop!==el._lastTop)el._stick=el.scrollHeight-el.scrollTop-el.clientHeight<8;
  const bottom=forceBottom||el._stick,top=el.scrollTop;const markup=rows.map(x=>{const label=(x.member?'@'+(names[x.member]||T('已移出成员')):x.role==='user'?T('你'):T('系统'))+' · '+new Date(x.at*1000).toLocaleTimeString(LOCALE());return '<div class="group-message '+esc(x.role)+'"><small>'+esc(label)+'</small>'+(x.role==='tool'?'<details><summary>'+T('工具执行')+'</summary><pre>'+esc(x.text)+'</pre></details>':groupFmt(x.text))+'</div>';}).join('')||'<p class="muted">'+T('消息会保存在这里。')+'</p>';reconcile(el,markup);if(bottom){el._stick=true;if(hidden)el.dataset.pendingBottom='1';else{delete el.dataset.pendingBottom;el.scrollTop=el.scrollHeight;}}else if(!hidden&&el.scrollTop!==top)el.scrollTop=top;if(!hidden)el._lastTop=el.scrollTop;}
 const feedKey=groupFeedKey(),switched=groupRender.lastKey!==feedKey;groupRender.lastKey=feedKey;
 renderFeed('group-main',groupMessages.filter(x=>x.channel==='main'),switched);
 renderFeed('group-detail',groupMessages.filter(x=>x.channel==='detail'&&x.member===groupMember),switched);
 if(switched){for(const id of ['group-main','group-detail']){const el=$(id);el.classList.remove('group-swap');void el.offsetWidth;el.classList.add('group-swap');}}
 const mainRows=groupMessages.filter(x=>x.channel==='main');
 // 单栏看成员时，群内简报的新消息用角标提示；历史还在分页加载时不算新消息。
 if(split||groupFocus==='main'||groupData?.has_more||groupSeenKey!==groupId||mainRows.length<groupSeenMain){groupSeenMain=mainRows.length;groupSeenKey=groupId;}
 const unread=mainRows.length-groupSeenMain;$('group-brief-badge').textContent=unread>0?String(unread):'';$('group-brief-tab').setAttribute('aria-label',groupBriefAria(unread));
 $('group-brief-tab').classList.toggle('on',split||groupFocus==='main');
 const root=groupData?.group?.root||'';$('group-project').textContent=root?T('项目')+' · '+root.split('/').pop():'';$('group-project').title=root;
 const m=members.find(x=>x.id===groupMember),st=m?state(m):'';
 $('group-detail-title').textContent=m?'@'+m.slug:T('成员聊天');
 $('group-detail-tag').textContent=m?sub(m):'';
 $('group-detail-state').textContent=m?(GROUP_STATUS[st]||st):'';$('group-detail-state').classList.toggle('busy',st==='running');
 $('group-session').textContent=m?.session?(T('原应用会话 ')+m.session):T('发送第一条消息后建立原应用会话');
 $('group-open-native').disabled=!m?.session||!!m.removed;
 $('group-native-history').disabled=!m;
 $('group-actual-model').textContent=m?.actual_model?T('最近实际模型：')+m.actual_model:'';$('group-actual-model').title=m?.actual_model?T('最近实际模型：')+m.actual_model+T('。原 App 下拉框的默认选择可能不同。'):'';
 $('group-usage').innerHTML=m?taskUsage(m):'';
 $('group-direct-send').disabled=groupSending||!m||!!m.removed;
 $('group-direct').disabled=!m||!!m.removed;
 $('group-direct').placeholder=(!m||!!m.removed)?T('这个框只发给点选的成员——先在左侧成员列表点一个成员；群消息请到「群内简报」发送'):T('直接给选中的成员发消息');
 groupButton();
}
function groupButton(){const text=$('group-input').value.trim()||(groupFiles.length?' ':''),running=(groupData?.jobs||[]).length>0;const b=$('group-send');b.textContent=text?T('发送'):running?('■ '+T('停止')):T('发送');b.classList.toggle('group-stop',!text&&running);b.disabled=groupResetting||groupSending||!groupData?.group||(!text&&!running);$('group-direct-send').disabled=groupSending||!groupData?.members?.some(m=>m.id===groupMember&&!m.removed);$('group-send-hint').textContent=text.includes('@')?T('发给指定成员'):T('发给全部成员');}
function groupEfforts(platform,want='medium'){
 const tiers=groupData.efforts[platform]?.[$('gd-model').value]||[];
 $('gd-effort').innerHTML=tiers.map(v=>'<option value="'+esc(v)+'">'+esc(effortLabel(v))+'</option>').join('');
 $('gd-effort').value=tiers.includes(want)?want:tiers.includes('medium')?'medium':tiers[0]||'';
}
function groupDialog(action){
 groupDialogAction=action;$('group-dialog-error').textContent='';
 const fields=$('group-dialog-fields');
 const memberList=groupActive().map(m=>'<label class="group-choice"><input type="checkbox" name="members" value="'+esc(m.id)+'">@'+esc(m.slug)+' · '+esc(m.platform)+'</label>').join('');
 if(action==='new'){$('group-dialog-title').textContent=T('新建群聊');fields.innerHTML='<label>'+T('群名')+'<input id="gd-name" required maxlength="80"></label><label>'+T('项目')+'<select id="gd-root">'+(groupData?.projects||[]).map(p=>'<option value="'+esc(p)+'">'+esc(p.split('/').pop())+'</option>').join('')+'<option value="__pick__">'+T('选择其他文件夹…')+'</option></select></label>';}
 else if(action==='rename'){const cur=groupData?.group||{};$('group-dialog-title').textContent=T('改名 / 换项目');fields.innerHTML='<label>'+T('群名')+'<input id="gd-name" maxlength="80" value="'+esc(cur.name||'')+'"></label><label>'+T('项目')+'<select id="gd-root">'+(groupData?.projects||[]).map(p=>'<option value="'+esc(p)+'"'+(p===cur.root?' selected':'')+'>'+esc(p.split('/').pop())+'</option>').join('')+'<option value="__pick__">'+T('选择其他文件夹…')+'</option></select></label><p class="muted">'+T('换项目后下一轮生效；已有原应用会话会带着原项目的上下文继续，建议重要群聊保持项目不变。')+'</p>';}
 else if(action==='add'){$('group-dialog-title').textContent=T('添加成员');fields.innerHTML='<label>'+T('成员名')+'<input id="gd-slug" required maxlength="24" placeholder="'+T('例如 reviewer')+'"></label><label>'+T('平台')+'<select id="gd-platform"><option value="codex">Codex</option><option value="claude">Claude Code</option><option value="zcode">'+T('ZCode · 基础版（能接续会话，暂不能跨发消息）')+'</option></select></label><label>'+T('模型')+'<select id="gd-model"></select></label><label>'+T('思考档位')+'<select id="gd-effort"></select><span id="gd-fast-row" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="gd-fast"> '+T('⚡ 快速（额外推理选项，勾选时不用档位）')+'</span></label>';const fill=()=>{const p=$('gd-platform').value;$('gd-model').innerHTML=(groupData.models[p]||[]).map(v=>'<option>'+esc(v)+'</option>').join('');groupEfforts(p);$('gd-model').onchange=()=>groupEfforts(p,$('gd-effort').value);$('gd-fast-row').style.display=p==='codex'?'':'none';$('gd-fast').checked=false;$('gd-effort').disabled=false;};$('gd-fast').onchange=()=>{$('gd-effort').disabled=$('gd-fast').checked;};$('gd-platform').onchange=fill;fill();}
 else if(action==='mod'){$('group-dialog-title').textContent=T('角色分工');fields.innerHTML='<label>'+T('成员')+'<select id="gd-member">'+groupActive().map(m=>'<option value="'+esc(m.id)+'">@'+esc(m.slug)+' · '+esc(m.platform)+'</option>').join('')+'</select></label><label>'+T('角色')+'<select id="gd-role"><option>'+T('决策')+'</option><option>'+T('执行')+'</option><option>'+T('关闭')+'</option></select></label><label>'+T('模型')+'<select id="gd-model"></select></label><label>'+T('思考档位')+'<select id="gd-effort"></select></label><p class="muted">'+T('启用后，上下文压缩将自动交接到同平台新会话，保留方案、修改与验证结果。Codex：6.1 Sol high；Claude：Sonnet high；ZCode：原生模型。')+'</p>';
 $('gd-role').innerHTML=['决策','执行','关闭'].map(v=>'<option value="'+v+'">'+esc(T(v))+'</option>').join('');
 const current=()=>groupActive().find(x=>x.id===$('gd-member').value);
 const fill=()=>{const m=current();if(!m)return;const role=$('gd-role').value,[model,effort]=groupData.mod_defaults[m.platform][role==='关闭'?'执行':role];$('gd-model').value=model;groupEfforts(m.platform,effort);$('gd-model').disabled=role==='关闭';$('gd-effort').disabled=role==='关闭'||$('gd-effort').options.length===1;};
 $('gd-role').onchange=fill;$('gd-model').onchange=()=>{const m=current();if(m)groupEfforts(m.platform,$('gd-effort').value);};
 const memberFill=()=>{const m=current();if(!m)return;$('gd-model').innerHTML=groupData.models[m.platform].map(v=>'<option>'+esc(v)+'</option>').join('');$('gd-role').value=m.mod_role||'决策';fill();if(m.mod_role){$('gd-model').value=m.model;groupEfforts(m.platform,m.effort);}};$('gd-member').onchange=memberFill;memberFill();}
 else if(action==='model'){$('group-dialog-title').textContent=T('同一聊天换模型');fields.innerHTML='<label>'+T('成员')+'<select id="gd-member">'+groupActive().map(m=>'<option value="'+esc(m.id)+'">@'+esc(m.slug)+' · '+esc(m.platform)+'</option>').join('')+'</select></label><label>模型<select id="gd-model"></select></label><label>思考档位<select id="gd-effort"></select><span id="gd-fast-row" style="display:flex;gap:6px;align-items:center;margin-top:6px"><input type="checkbox" id="gd-fast"> ⚡ 快速（额外推理选项，勾选时不用档位）</span></label><p class="muted">'+T('本轮继续使用当前模型，下一轮在同一聊天应用。')+'</p>';const fill=()=>{const m=groupActive().find(x=>x.id===$('gd-member').value);if(!m)return;$('gd-model').innerHTML=groupData.models[m.platform].map(v=>'<option>'+esc(v)+'</option>').join('');$('gd-model').value=m.model;groupEfforts(m.platform,m.effort);$('gd-model').onchange=()=>groupEfforts(m.platform,$('gd-effort').value);const fast=m.effort==='fast';$('gd-fast-row').style.display=m.platform==='codex'?'':'none';$('gd-fast').checked=fast;$('gd-effort').disabled=fast;if(fast)groupEfforts(m.platform);};$('gd-fast').onchange=()=>{$('gd-effort').disabled=$('gd-fast').checked;};$('gd-member').onchange=fill;fill();}
 else{$('group-dialog-title').textContent=T('移出成员，保留历史');fields.innerHTML=memberList+'<p class="muted">'+T('终止所选成员的工作并移出群聊。聊天记录保留。')+'</p>';}
 dialogOpen($('group-dialog'));
}
dialogCancelAnimation($('group-dialog'));$('group-dialog').addEventListener('close',()=>{if(!$('group-dialog').open)$('group-dialog-fields').replaceChildren();});
$('group-dialog-cancel').onclick=()=>dialogClose($('group-dialog'));
// 项目下拉末项：弹系统选择框，自选文件夹经服务端授权校验后加入并选中。
$('group-dialog-fields').addEventListener('focusin',e=>{if(e.target.id==='gd-root'&&e.target.value!=='__pick__')e.target.dataset.prev=e.target.value;});
$('group-dialog-fields').addEventListener('change',async e=>{const sel=e.target;if(sel.id!=='gd-root')return;if(sel.value!=='__pick__'){sel.dataset.prev=sel.value;return;}
 const prev=sel.dataset.prev||sel.options[0].value,save=$('group-dialog-save');sel.value=prev;sel.disabled=true;save.disabled=true;$('group-dialog-error').textContent='';
 try{const d=await centerApi('center/pick-root',{});if(d.path){if(groupData)groupData.projects=d.roots;if(![...sel.options].some(o=>o.value===d.path)){const o=document.createElement('option');o.value=d.path;o.textContent=d.path.split('/').pop();sel.insertBefore(o,sel.lastElementChild);}sel.value=d.path;sel.dataset.prev=d.path;}}
 catch(err){$('group-dialog-error').textContent=err.message;}finally{sel.disabled=false;save.disabled=false;}});
$('group-dialog-form').onsubmit=async e=>{e.preventDefault();const save=$('group-dialog-save');save.disabled=true;try{let body={group:groupId},path='groups/';if(groupDialogAction==='new'){path+='create';body={name:$('gd-name').value,root:$('gd-root').value};}else if(groupDialogAction==='rename'){path+='rename';Object.assign(body,{name:$('gd-name').value,root:$('gd-root').value});}else if(groupDialogAction==='add'){path+='add';Object.assign(body,{slug:$('gd-slug').value,platform:$('gd-platform').value,model:$('gd-model').value,effort:($('gd-fast').checked?'fast':$('gd-effort').value)});}else if(groupDialogAction==='mod'){path+='mod';Object.assign(body,{member:$('gd-member').value,role:$('gd-role').value,model:$('gd-model').value,effort:$('gd-effort').value});}else if(groupDialogAction==='model'){path+='model';Object.assign(body,{member:$('gd-member').value,model:$('gd-model').value,effort:($('gd-fast').checked?'fast':$('gd-effort').value)});}else{path+='delete';body.members=[...$('group-dialog-fields').querySelectorAll('input:checked')].map(x=>x.value);}const d=await centerApi(path,body);if(groupDialogAction==='new'){groupId=d.id;localStorage.setItem('cg-group',groupId);}dialogClose($('group-dialog'));await groupLoad(true);}catch(err){$('group-dialog-error').textContent=err.message;}finally{save.disabled=false;}};
$('group-new').onclick=()=>groupDialog('new');$('group-add').onclick=()=>groupId?groupDialog('add'):groupNotice(T('先新建群聊'));$('group-model').onclick=()=>groupDialog('model');$('group-delete').onclick=()=>groupDialog('delete');$('group-rename').onclick=()=>groupId?groupDialog('rename'):groupNotice(T('先新建群聊'));
// 群组 dd：整行点选（shift 范围选）、「进入」切群、归档/删除两类批量操作
function renderGroupMenu(){
 const groups=groupData?.groups||[],archived=groupData?.archived_groups||[];
 const sel=[...groupDeleteSel];
 const items=groups.map((g,i)=>'<div class="dd-it group-dd-item'+(g.id===groupId?' on':'')+'" data-i="'+i+'" data-g="'+esc(g.id)+'"><input type="checkbox" class="group-dd-check" aria-label="'+esc(g.name)+'"'+(groupDeleteSel.has(g.id)?' checked':'')+'><span class="group-dd-name">'+esc(g.name)+'</span><button class="group-dd-enter" type="button" data-enter="'+esc(g.id)+'">'+T('进入')+'</button></div>').join('');
 const archivedRows=archived.map(g=>'<div class="dd-it group-dd-item archived"><span class="group-dd-name">'+esc(g.name)+'</span><button class="group-dd-restore" type="button" data-restore="'+esc(g.id)+'">'+T('恢复')+'</button></div>').join('');
 $('group-dd-menu').innerHTML='<div class="group-dd-actions"><button id="group-dd-arc" type="button"'+(sel.length?'':' disabled')+'>'+T('归档所选（')+sel.length+'）</button><button id="group-dd-del" type="button"'+(sel.length?'':' disabled')+'>'+T('删除所选（')+sel.length+'）</button></div>'
  +(items||'<p class="muted" style="margin:6px">'+T('还没有群聊')+'</p>')
  +(archived.length?'<div class="group-dd-archived-head">'+T('已归档（从列表隐藏，可恢复）')+'</div>'+archivedRows:'');
 $('group-dd-btn').textContent=(groups.find(g=>g.id===groupId)?.name)||T('选择群聊');
}
function groupSwitch(gid){groupId=gid;localStorage.setItem('cg-group',groupId);groupMember='';groupFocus='main';groupDeleteSel.clear();groupLastSelIndex=null;ddClose($('group-dd'));groupLoad(true);}
$('group-dd-btn').onclick=e=>{e.stopPropagation();const dd=$('group-dd');if(dd.classList.contains('open')){ddClose(dd);return;}dd.classList.add('open');$('group-dd-btn').setAttribute('aria-expanded','true');};
document.addEventListener('click',e=>{if(!e.target.closest('#group-dd'))ddClose($('group-dd'));});
$('group-dd-menu').addEventListener('click',async e=>{
 e.stopPropagation();
 const restore=e.target.closest('[data-restore]');
 if(restore){try{await centerApi('groups/archive',{groups:[restore.dataset.restore],archived:false});await groupLoad();}catch(err){groupNotice(err.message);}return;}
 const enter=e.target.closest('[data-enter]');
 if(enter){groupSwitch(enter.dataset.enter);return;}
 const del=e.target.closest('#group-dd-del');
 if(del){const ids=[...groupDeleteSel];if(!ids.length)return;
  const ok=await askModal({title:T('删除群聊'),message:T('确认删除所选 ')+ids.length+T(' 个群聊？成员、消息与任务记录将一并删除，不可恢复。')});
  if(!ok)return;
  try{await centerApi('groups/remove',{groups:ids});if(groupId&&ids.includes(groupId))groupId='';groupDeleteSel.clear();groupLastSelIndex=null;ddClose($('group-dd'));await groupLoad(true);}catch(err){groupNotice(err.message);}return;}
 const arc=e.target.closest('#group-dd-arc');
 if(arc){const ids=[...groupDeleteSel];if(!ids.length)return;
  const ok=await askModal({title:T('归档群聊'),message:T('确认归档所选 ')+ids.length+T(' 个群聊？归档后从列表隐藏（记录保留），下拉底部可恢复。')});
  if(!ok)return;
  try{await centerApi('groups/archive',{groups:ids,archived:true});if(groupId&&ids.includes(groupId))groupId='';groupDeleteSel.clear();groupLastSelIndex=null;await groupLoad(true);}catch(err){groupNotice(err.message);}return;}
 const row=e.target.closest('.group-dd-item[data-i]');
 if(row){
  const idx=+row.dataset.i,gid=row.dataset.g,groups=groupData?.groups||[];
  if(e.shiftKey&&groupLastSelIndex!==null){
   const a=Math.min(groupLastSelIndex,idx),b=Math.max(groupLastSelIndex,idx),turnOn=!groupDeleteSel.has(gid);
   for(let k=a;k<=b;k++){const g=groups[k];if(!g)continue;if(turnOn)groupDeleteSel.add(g.id);else groupDeleteSel.delete(g.id);}
  }else if(groupDeleteSel.has(gid))groupDeleteSel.delete(gid);
  else groupDeleteSel.add(gid);
  groupLastSelIndex=idx;
  renderGroupMenu();
 }
});
$('group-members').onclick=e=>{if(groupResetting)return;const b=e.target.closest('[data-member]');if(b){groupHistoryGeneration++;groupMember=b.dataset.member;groupFocus='member';groupRender();}};
$('group-members').addEventListener('toggle',e=>{if(e.target.classList?.contains('group-removed'))groupRemovedOpen=e.target.open;},true);
$('group-brief-tab').onclick=()=>{groupFocus='main';groupRender();};
$('group-wide').onclick=()=>{if(!groupCanSplit){groupNotice(T('窗口不够宽，放不下两栏：把窗口拉宽，或先收起左侧成员栏。'));return;}groupAnimLayout(()=>{groupSplitPref=groupSplitNow?'0':'1';try{localStorage.setItem('cg-gsplit',groupSplitPref);}catch(e){}});};
// 版式切换的公共动画：先加 gt-anim 让网格过渡，change 改状态后重排；280ms 后去掉 gt-anim 再重排一次。减少动态效果时直接到位，连点时清掉上一个定时器。
function groupAnimLayout(change){const grid=document.querySelector('.group-grid');if(groupSideAnimTimer!==null){clearTimeout(groupSideAnimTimer);groupSideAnimTimer=null;}const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;grid.classList.toggle('gt-anim',!reduce);change();groupRender();if(reduce){grid.classList.remove('gt-anim');return;}groupSideAnimTimer=setTimeout(()=>{groupSideAnimTimer=null;grid.classList.remove('gt-anim');groupRender();},280);}
// 成员栏收放：和主导航一样记住状态；动画期间先藏起分隔条，结束后再按最终宽度重排一次。
function toggleGroupSide(){groupAnimLayout(()=>{groupSideMini=!groupSideMini;try{localStorage.setItem('cg-gside',groupSideMini?'mini':'full');}catch(e){}});}
$('group-side-toggle').onclick=toggleGroupSide;
// 版式计算：会话区高度铺到窗口底部（页面不出第二条滚动条）；成员栏宽度由这里给出，收放才能平滑过渡；放得下两栏才允许并排。返回当前是否并排。
function applyGroupRatio(r){const grid=document.querySelector('.group-grid'),side=parseFloat(grid.style.getPropertyValue('--gside'))||0,available=Math.max(1,grid.clientWidth-side-32),min=Math.max(.3,Math.min(.5,371/available)),ratio=Math.min(1-min,Math.max(min,r));grid.style.setProperty('--ga',ratio.toFixed(5)+'fr');grid.style.setProperty('--gb',(1-ratio).toFixed(5)+'fr');return ratio;}
function groupLayout(){
 const grid=document.querySelector('.group-grid');if(!grid||!grid.offsetParent)return groupSplitNow;
 const narrow=matchMedia('(max-width:55em)').matches,mini=groupSideMini&&!narrow;
 grid.style.height=narrow?'':Math.max(440,Math.floor(innerHeight-grid.getBoundingClientRect().top-scrollY-24))+'px';
 const w=grid.clientWidth,side=mini?56:Math.round(Math.min(248,Math.max(200,w*.22))),space=w-side-16;
 grid.style.setProperty('--gside',side+'px');grid.classList.toggle('side-mini',mini);$('group-side-toggle').setAttribute('aria-expanded',String(!mini));
 // 两个会话区各有约 370px 以上才允许并排；宽到各约 510px 以上时默认并排。
 groupCanSplit=!narrow&&space>=760;
 groupSplitNow=groupCanSplit&&(groupSplitPref===null?space>=1040:groupSplitPref==='1');
 grid.classList.toggle('split',groupSplitNow);grid.classList.toggle('show-member',groupFocus==='member');
 const b=$('group-wide');b.textContent=groupSplitNow?T('单栏'):T('并排');b.setAttribute('aria-pressed',String(groupSplitNow));b.setAttribute('aria-disabled',String(!groupCanSplit));b.title=groupCanSplit?T('并排时同时显示群内简报和成员聊天'):T('窗口不够宽，放不下两栏：把窗口拉宽，或先收起左侧成员栏。');
 if(groupSplitNow){applyGroupRatio(groupRatioPref);grid.querySelector('.grip').style.left=(grid.querySelector('.group-detail').offsetLeft-14)+'px';}
 else{grid.style.setProperty('--ga',groupFocus==='member'?'0fr':'1fr');grid.style.setProperty('--gb',groupFocus==='member'?'1fr':'0fr');}
 return groupSplitNow;
}
function groupFeedKey(){return groupId+':'+groupMember+':'+groupFocus;}
function groupBriefAria(unread){return T('群内简报')+' · '+(unread>0?unread+' '+T('未读消息'):T('无未读消息'));}
// 并排时两个会话区之间的分隔条：拖动调比例（30%–70%），双击恢复对半。
function gripWire(){
 const grid=document.querySelector('.group-grid'),g=grid.querySelector('.grip');
 const apply=r=>{groupRatioPref=r;applyGroupRatio(r);};
 try{const r=parseFloat(localStorage.getItem('cg-gratio'));if(r>=.3&&r<=.7)groupRatioPref=r;}catch(e){}
 g.addEventListener('pointerdown',e=>{
  e.preventDefault();g.classList.add('dragging');
  const a=grid.querySelector('.group-brief').getBoundingClientRect(),b=grid.querySelector('.group-detail').getBoundingClientRect();let r=a.width/(a.width+b.width);
  const move=ev=>{r=Math.min(.7,Math.max(.3,(ev.clientX-a.left-8)/(b.right-a.left-16)));apply(r);groupLayout();};
  const up=()=>{g.classList.remove('dragging');['pointermove','pointerup','pointercancel'].forEach((t,i)=>document.removeEventListener(t,i?up:move));try{localStorage.setItem('cg-gratio',groupRatioPref.toFixed(3));}catch(err){}};
  document.addEventListener('pointermove',move);document.addEventListener('pointerup',up);document.addEventListener('pointercancel',up);
 });
 g.addEventListener('dblclick',()=>{groupRatioPref=.5;grid.style.removeProperty('--ga');grid.style.removeProperty('--gb');try{localStorage.removeItem('cg-gratio');}catch(e){}groupLayout();});
}
window.addEventListener('resize',()=>groupRender());
$('group-open-native').onclick=async()=>{try{const d=await centerApi('groups/open',{group:groupId,member:groupMember});groupNotice(d.note||(T('已请求打开 ')+(d.platform==='claude'?'Claude':'Codex')+T(' 原 App 的同一聊天。')));}catch(e){groupNotice(e.message);}};
async function groupNativeHistory(offset=0){
 const gid=groupId,mid=groupMember,generation=++groupHistoryGeneration;
 try{
  const d=await centerApi('groups/native?id='+encodeURIComponent(gid)+'&member='+encodeURIComponent(mid)+'&offset='+offset);
  if(generation!==groupHistoryGeneration||gid!==groupId||mid!==groupMember)return;
  const name=groupData?.members?.find(m=>m.id===mid)?.slug||'成员';
  openModal('@'+name+' · '+T('原平台聊天记录'),'<p class="muted">'+esc(d.source)+' · '+T('本页位置 ')+offset+' · '+T('共 ')+(d.total||0)+Tc(d.total||0,' 条',' entries',' entries')+'</p>'+d.messages.map(m=>'<div class="group-message '+esc(m.role)+'"><small>'+esc(m.role)+'</small>'+(m.role==='tool'?'<details><summary>'+T('工具与结果')+'</summary><pre>'+esc(m.text)+'</pre></details>':esc(m.text))+'</div>').join('')+'<div class="group-toolbar">'+(offset>0?'<button id="group-native-prev">'+T('上一页')+'</button>':'')+(d.next_offset!==null?'<button id="group-native-next">'+T('下一页')+'</button>':'')+'</div>');
  if(offset>0)$('group-native-prev').onclick=()=>groupNativeHistory(Math.max(0,offset-200));
  if(d.next_offset!==null)$('group-native-next').onclick=()=>groupNativeHistory(d.next_offset);
 }catch(e){if(generation===groupHistoryGeneration&&gid===groupId&&mid===groupMember)groupNotice(e.message);}
}
$('group-native-history').onclick=()=>groupNativeHistory();
$('group-more').onclick=()=>groupLoad();
$('group-input').oninput=()=>{
 groupButton();const text=$('group-input').value;const mention=text.match(/@([\w-]*)$/);const command=text.match(/^\/(\w*)$/);const menu=$('group-menu');
 if(mention){menu.innerHTML=groupActive().filter(m=>m.slug.startsWith(mention[1])).map(m=>'<button type="button" data-mention="'+esc(m.slug)+'">@'+esc(m.slug)+' · '+esc(m.platform+' / '+m.model+' / '+m.effort)+'</button>').join('');menu.classList.toggle('open',!!menu.innerHTML);}
 else if(command){menu.innerHTML=[['mod',T('角色分工 · 决策 / 执行 / 自动交接')],['delete',T('移出成员，终止工作并保留历史')],['model',T('在同一聊天换模型')],['add','＋ '+T('添加成员')]].filter(x=>x[0].startsWith(command[1])).map(x=>'<button type="button" data-command="'+x[0]+'">/'+x[0]+' · '+x[1]+'</button>').join('');menu.classList.toggle('open',!!menu.innerHTML);}else menu.classList.remove('open');
};
$('group-menu').onclick=e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.mention){$('group-input').value=$('group-input').value.replace(/@[\w-]*$/,'@'+b.dataset.mention+' ');}else{groupDialog(b.dataset.command);$('group-input').value='';}$('group-menu').classList.remove('open');groupButton();$('group-input').focus();};
async function groupSend(text,members){
 if(groupResetting||groupSending||!groupData?.group)return false;
 const sentGroup=groupId;groupSending=true;groupButton();
 try{
  const payload={group:sentGroup,text,...(members?{members}:{})};
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(JSON.stringify(payload)));
  const key='cg-send-'+[...new Uint8Array(bytes)].map(x=>x.toString(16).padStart(2,'0')).join('');
  const request_id=sessionStorage.getItem(key)||crypto.randomUUID();sessionStorage.setItem(key,request_id);
  const result=await centerApi('groups/send',{...payload,request_id});sessionStorage.removeItem(key);
  if(sentGroup!==groupId)return false;
  groupNotice(result.replayed?T('消息此前已登记，已确认原请求；没有重复派发。'):T('消息已登记，成功接收后成员会确认。'));
  await groupLoad();return true;
 }catch(e){if(sentGroup===groupId)groupNotice(e.message+T('；同内容重试会核对原请求。'));return false;}
 finally{groupSending=false;groupButton();}
}
function groupStopMenu(){groupStopOpen=true;const ids=new Set((groupData?.jobs||[]).map(j=>j.member));$('group-stop-menu').innerHTML=groupActive().filter(m=>ids.has(m.id)).map(m=>'<label class="group-choice"><input type="checkbox" value="'+esc(m.id)+'">@'+esc(m.slug)+' · '+esc(GROUP_STATUS[m.status]||m.status)+'</label>').join('')+'<small class="muted">'+T('选择后再次点停止。未选择时双击停止全部。')+'</small>';$('group-stop-menu').hidden=false;}
async function groupStop(all=false){const selected=[...$('group-stop-menu').querySelectorAll('input:checked')].map(x=>x.value);const ids=all?[...new Set((groupData?.jobs||[]).map(j=>j.member))]:selected;if(!ids.length){groupNotice(T('请选择成员；未选择时双击停止全部。'));return;}try{await centerApi('groups/stop',{group:groupId,members:ids});groupStopOpen=false;$('group-stop-menu').hidden=true;await groupLoad();}catch(e){groupNotice(e.message);}}
// 附件：点按钮、拖入或粘贴；文件先存进群聊项目内，发送时把路径附在消息末尾，成员按路径读取。
function groupFilesRender(){$('group-attachments').innerHTML=groupFiles.map((f,i)=>'<span class="group-chip'+(f.path?'':' pending')+'">'+(f.url?'<img src="'+esc(f.url)+'" alt="">':'')+'<span>'+esc(f.name)+'</span><button type="button" data-drop-file="'+i+'" aria-label="'+esc(T('移除'))+'">×</button></span>').join('');groupButton();}
async function groupAttach(list){
 if(!groupData?.group)return;const gid=groupId;
 for(const file of [...list]){
  if(file.size>8*1024*1024||!file.size){groupNotice(T('附件每份最多8MB'));continue;}
  const item={name:file.name||'image.png',url:file.type.startsWith('image/')?URL.createObjectURL(file):'',path:''};groupFiles.push(item);groupFilesRender();
  try{const data=await new Promise((ok,bad)=>{const r=new FileReader();r.onload=()=>ok(String(r.result).split(',')[1]||'');r.onerror=()=>bad(new Error(T('附件无效')));r.readAsDataURL(file);});
   const d=await centerApi('groups/attach',{group:gid,name:item.name,data});item.path=d.path;item.name=d.name;}
  catch(err){groupFiles=groupFiles.filter(x=>x!==item);if(item.url)URL.revokeObjectURL(item.url);groupNotice(err.message);}
  groupFilesRender();
 }
}
// 原生壳没有网页文件选择框，按钮改由后端弹系统选择框并直接存入项目。
$('group-attach').onclick=async e=>{if(!groupData?.group)return;const b=e.currentTarget;b.disabled=true;try{const d=await centerApi('groups/pick-files',{group:groupId});for(const f of d.files||[])groupFiles.push({name:f.name,url:'',path:f.path});if(d.errors?.length)groupNotice(d.errors.join('；'));groupFilesRender();}catch(err){groupNotice(err.message);}finally{b.disabled=false;}};
$('group-attachments').onclick=e=>{const b=e.target.closest('[data-drop-file]');if(!b)return;const [f]=groupFiles.splice(Number(b.dataset.dropFile),1);if(f?.url)URL.revokeObjectURL(f.url);groupFilesRender();};
$('group-form').addEventListener('dragover',e=>{if([...e.dataTransfer.types].includes('Files')){e.preventDefault();$('group-form').classList.add('drag');}});
$('group-form').addEventListener('dragleave',()=>$('group-form').classList.remove('drag'));
$('group-form').addEventListener('drop',e=>{$('group-form').classList.remove('drag');if(e.dataTransfer.files.length){e.preventDefault();groupAttach(e.dataTransfer.files);}});
$('group-input').addEventListener('paste',e=>{if(e.clipboardData?.files?.length){e.preventDefault();groupAttach(e.clipboardData.files);}});
$('group-form').onsubmit=async e=>{e.preventDefault();if(groupResetting)return;let text=$('group-input').value.trim();
 if(groupFiles.length&&!/^\/(model|delete|add|mod)$/.test(text)){if(groupFiles.some(f=>!f.path)){groupNotice(T('附件还在上传，请稍候'));return;}text=(text||T('请查看附件。'))+'\n\n'+T('附件（已保存在项目内，可按路径直接读取）：')+'\n'+groupFiles.map(f=>'- '+f.path).join('\n');}
 if(text){if(/^\/(model|delete|add|mod)$/.test(text)){groupDialog(text.slice(1));return;}if(await groupSend(text)){$('group-input').value='';groupFiles.forEach(f=>f.url&&URL.revokeObjectURL(f.url));groupFiles=[];groupFilesRender();}groupButton();}else if(!groupStopOpen)groupStopMenu();else await groupStop();};
$('group-send').ondblclick=async e=>{if(!$('group-input').value.trim()&&!$('group-stop-menu').querySelector('input:checked')){e.preventDefault();await groupStop(true);}};
$('group-direct-form').onsubmit=async e=>{e.preventDefault();if(groupResetting)return;const text=$('group-direct').value.trim();if(text==='/mod'){groupDialog('mod');if($('gd-member').querySelector('option[value="'+groupMember+'"]'))$('gd-member').value=groupMember;if($('gd-member').onchange)$('gd-member').onchange();$('group-direct').value='';return;}if(text==='/model'){groupDialog('model');$('gd-member').value=groupMember;$('gd-member').onchange();$('group-direct').value='';return;}if(text==='/stop'){try{await centerApi('groups/stop',{group:groupId,members:[groupMember]});$('group-direct').value='';await groupLoad();}catch(err){groupNotice(err.message);}return;}if(text==='/help'){groupNotice(T('成员指令：/model 在同一聊天换模型；/stop 停止此成员；其余原生指令请点“打开原平台”使用。'));return;}if(text.startsWith('/')){groupNotice(T('此原生指令请在“打开原平台”中使用，避免当普通消息发送。'));return;}if(text&&groupMember&&await groupSend(text,[groupMember]))$('group-direct').value='';};
// 视图隐藏期间渲染的流（尺寸为 0 滚不动）：切到群聊视图后统一落到最底部最新消息
function flushGroupFeeds(){document.querySelectorAll('section[data-view="group"] .group-feed[data-pending-bottom]').forEach(el=>{delete el.dataset.pendingBottom;el.scrollTop=el.scrollHeight;});}
document.querySelectorAll('.nav-item').forEach(n=>n.addEventListener('click',()=>{if(n.dataset.v==='group')requestAnimationFrame(()=>{const was=groupSplitNow;groupLayout();flushGroupFeeds();if(was!==groupSplitNow)groupRender();});}));
document.addEventListener('click',e=>{if(!groupStopOpen)return;if(e.target.closest('#group-stop-menu')||e.target.closest('#group-send'))return;$('group-stop-menu').hidden=true;groupStopOpen=false;});
$('group-input').onkeydown=e=>{if(e.key==='Escape'){$('group-menu').classList.remove('open');$('group-stop-menu').hidden=true;groupStopOpen=false;}if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){$('group-form').requestSubmit();e.preventDefault();}};
$('group-direct').onkeydown=e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){$('group-direct-form').requestSubmit();e.preventDefault();}};
gripWire();groupLoad();setInterval(()=>{if(curView==='group'){if($('auto').checked&&!document.hidden)groupLoad();groupLayout();}},2000);
'''
