"""Memory reader integrated with the console's components and dark/warm theme tokens."""
CSS = r'''
.memory-view-controls{margin-left:auto;display:flex;gap:12px;align-items:center}
.memory-nebula .memory-view-controls{margin-left:auto}

.memory-presentation{margin-left:0;display:flex;gap:4px;padding:3px;border:1px solid var(--glassline);border-radius:9px;background:var(--cardT)}
.memory-presentation button{display:grid;place-items:center;width:34px;height:32px;padding:7px;border:0;background:transparent;color:var(--muted);border-radius:6px}
.memory-presentation button svg{width:18px;height:18px;fill:none;stroke:currentColor;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round}
.memory-presentation button[aria-pressed=true]{color:var(--accent);background:var(--accentbg)}
.memory-presentation button:hover{background:var(--rowhover)}
#memory-galaxy-frame{display:block;width:100%;height:calc(100dvh - 200px);min-height:520px;border:1px solid var(--glassline);border-radius:12px;background:var(--cardT)}
#memory-galaxy-frame[hidden]{display:none}
.memory-nebula .memory-tabs,.memory-nebula .memory-text-controls,.memory-nebula .memory-export,.memory-nebula #memory-note,.memory-nebula #memory-layout{display:none}

#memory-page{overflow:visible;contain:style}
.memory-toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.memory-toolbar label{display:flex;align-items:center;gap:8px;flex:1;min-width:220px}
#memory-query{min-width:0;flex:1;width:100%;height:36px;background:var(--cardT);border-color:var(--glassline)}
#memory-note{margin:8px 0 16px;min-height:20px;font-size:13px;color:var(--muted)}
#memory-note.memory-error{color:var(--bad)}
.memory-tabs{margin:0;display:flex;gap:6px}
.memory-tabs button{min-height:32px}
.memory-layout{display:grid;grid-template-columns:240px minmax(0,1fr);gap:16px;align-items:start}
.memory-layout.overview{grid-template-columns:minmax(0,1fr)}
.memory-list{position:sticky;top:16px;align-self:start;min-width:0;max-height:65vh;overflow:auto;overscroll-behavior:contain;display:flex;flex-direction:column;gap:4px;padding:8px;background:var(--chip);border:1px solid var(--glassline);border-radius:8px}
.memory-list[hidden]{display:none}
.memory-list button{display:flex;flex-direction:column;align-items:flex-start;gap:4px;flex:none;width:100%;min-height:60px;text-align:left;padding:12px;border-color:transparent;background:transparent}
.memory-list button:hover{background:var(--rowhover)}
.memory-list button.on{background:var(--accentbg);border-color:var(--accentbg);color:var(--accent)}
.memory-list button span{width:100%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:500}
.memory-list small{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.memory-reader{min-width:0;font-size:var(--memory-font,16px);line-height:1.85;overflow-wrap:anywhere}
.memory-reader h3{font-size:20px;font-weight:600;line-height:1.5;margin:0 0 16px}
.memory-reader h4{font-size:16px;font-weight:600;margin:0 0 12px}
.memory-text{white-space:pre-wrap;overflow-wrap:anywhere;margin:0}
.memory-entry{margin-bottom:16px;padding:20px}
.memory-entry .memory-meta{font-size:12px;color:var(--muted);margin:16px 0}
.mstatbar{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0 4px}
.mstat{background:var(--chip);border:1px solid var(--glassline);border-radius:8px;padding:6px 12px;font-size:12px;color:var(--muted)}
.mstat b{color:var(--text);font-weight:600;font-variant-numeric:tabular-nums}
.mstat.lapsed{border-color:var(--bad);color:var(--bad)}
.memory-reader details{margin-top:12px;border-top:1px solid var(--line);padding-top:12px;font-size:14px}
.memory-reader summary{cursor:pointer;color:var(--accent);font-size:13px}
.memory-reader blockquote{border-left:2px solid var(--accent);margin:12px 0;padding:8px 16px;color:var(--text)}
.memory-reader pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--prebg);color:var(--pretext)}
.memory-topic-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.memory-topic{display:flex;flex-direction:column;gap:12px;min-height:124px;text-align:left;padding:16px;border-radius:8px}
.memory-topic strong{font-weight:600;color:var(--text);font-size:14px;display:flex;justify-content:space-between;gap:16px}
.memory-topic small{white-space:nowrap;font-weight:400;font-size:12px;color:var(--muted)}
.memory-topic .memory-preview{font-size:13px;color:var(--muted);flex:1}
.memory-topic .memory-arrow{font-size:12px;color:var(--accent)}
.memory-directory{display:flex;flex-direction:column;gap:8px}
.memory-directory button{text-align:left;display:flex;justify-content:space-between;gap:16px;padding:12px;background:var(--chip)}
.memory-path{font-size:12px;color:var(--muted);overflow-wrap:anywhere;margin:0 0 16px}
.memory-empty{padding:24px 0;color:var(--muted)}
.memory-text-controls{display:flex;align-items:center;gap:4px;margin-left:0}
.memory-text-controls button{padding:4px 8px;min-height:32px}
.memory-export{margin:0 0 16px;border:1px solid var(--glassline);border-radius:8px;padding:12px 16px;background:var(--chip)}
.memory-export>summary{cursor:pointer;color:var(--text);font-size:14px}
.memory-export-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px;margin-top:16px}
.memory-export-options h3{font-size:14px;margin:0 0 8px}
.memory-export-options p{font-size:13px;color:var(--muted);margin:0 0 12px;line-height:1.6}
.memory-export-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.memory-export-actions select{max-width:100%}
@media(max-width:1100px){.memory-export-options{grid-template-columns:minmax(0,1fr)}}
@media(max-width:1100px){.memory-layout{grid-template-columns:210px minmax(0,1fr)}}
@media(max-width:900px){.memory-layout{grid-template-columns:minmax(0,1fr)}.memory-list{position:static;max-height:220px}.memory-topic-grid{grid-template-columns:minmax(0,1fr)}}
'''
HTML = r'''
<div class="pagehead" data-view="memory"><h2>记忆</h2><p>按主题查找共享记忆，中文要点、完整正文和原文依据放在一起。</p><div class="sums" id="memory-sums"></div></div>
<section data-view="memory" id="memory-page">
<div class="memory-toolbar"><label for="memory-query">搜索记忆<input type="search" id="memory-query" placeholder="标题、内容、项目或关键词" maxlength="300"></label><button id="memory-live-open" type="button" aria-haspopup="dialog" aria-controls="memory-live-window" aria-expanded="false">实时事件 ↗</button><button id="memory-sync" type="button">更新记忆文档</button><button id="memory-open-folder" type="button">打开文档文件夹</button></div>
<div class="memory-toolbar"><div class="charts memory-tabs" role="tablist" aria-label="记忆阅读方式"><button type="button" data-memory-mode="overview" role="tab" class="on" aria-selected="true">总览</button><button type="button" data-memory-mode="directory" role="tab" aria-selected="false">目录</button><button type="button" data-memory-mode="outline" role="tab" aria-selected="false">大纲</button><button type="button" data-memory-mode="detail" role="tab" aria-selected="false">详细</button></div><div class="memory-view-controls"><div class="memory-presentation" role="group" aria-label="记忆显示模式"><button type="button" data-memory-presentation="text" aria-label="文字模式" title="文字模式" aria-pressed="true"><svg viewBox="0 0 20 20"><path d="M7 5h10M7 10h10M7 15h7"/><circle cx="3" cy="5" r=".7"/><circle cx="3" cy="10" r=".7"/><circle cx="3" cy="15" r=".7"/></svg></button><button type="button" data-memory-presentation="nebula" aria-label="星云模式" title="星云模式" aria-pressed="false"><svg viewBox="0 0 20 20"><ellipse cx="10" cy="10" rx="8" ry="3.8" transform="rotate(-35 10 10)"/><circle cx="10" cy="10" r="2"/><path d="M15.5 2v3M14 3.5h3"/></svg></button></div><div class="memory-text-controls"><button type="button" id="memory-smaller" title="减小文字" aria-label="减小文字">A−</button><button type="button" id="memory-larger" title="增大文字" aria-label="增大文字">A＋</button></div></div></div>
<details class="memory-export"><summary>导出记忆</summary><div class="memory-export-options">
<div><h3>一份完整文档</h3><p>合成一份可阅读文档，并附原始记录；包括已归档和到期内容。</p><div class="memory-export-actions"><select id="memory-export-format" aria-label="全文文件格式"><option value="txt">TXT 文本</option><option value="md">Markdown (.md)</option></select><button type="button" data-memory-export="full">导出全文</button></div></div>
<div><h3>分类文档包</h3><p>按主题保存文档、目录和依据，保留文件夹结构。</p><button type="button" data-memory-export="human">导出分类文档</button></div>
<div><h3>原始记录包</h3><p>保留完整原始记录，适合备份或进一步处理。</p><button type="button" data-memory-export="raw">导出原始版</button></div>
</div><p class="muted" style="font-size:12px;margin:16px 0 0">点击后现场生成，保存到文档文件夹中的“导出”，并在访达显示。同步时不会制作导出文件。</p><p id="memory-export-note" role="status" aria-live="polite" style="margin:8px 0 0;font-size:13px"></p></details>
<p id="memory-note" role="status" aria-live="polite">进入记忆页后读取本地文档。</p>
<iframe id="memory-galaxy-frame" title="记忆星云" sandbox="allow-scripts allow-same-origin" hidden></iframe>
<div class="memory-layout overview" id="memory-layout"><div class="memory-list" id="memory-list" aria-label="记忆列表" hidden></div><div class="memory-reader" id="memory-reader"></div></div>
</section>
'''
JS = r'''
let memoryData=null,memoryMode='overview',memorySelected='',memoryRows=[],memoryLoading=false,memoryStamp='',memoryFont=16;
try{memoryFont=Math.max(14,Math.min(22,Number(localStorage.getItem('cg-memory-font'))||16));}catch(e){}
function memoryQuery(){return $('memory-query').value.trim().toLocaleLowerCase();}
function memoryGroupTitle(g){
 const title=String(g.title||''),labels={rules:'使用与协作约定',preferences:'偏好与其他信息',activity:'工作与验证记录',system:'记忆系统与工具',projects:'项目相关记录'};
 if(Object.prototype.hasOwnProperty.call(labels,g.id)&&title===labels[g.id])return T(title);
 if(String(g.id).startsWith('project:')&&title.startsWith('项目 · '))return T('项目')+' · '+title.slice('项目 · '.length);
 return title;
}
function memoryMatches(e,g){const q=memoryQuery();return !q||[e.title,e.value,e.reading_text,e.key,g.title,memoryGroupTitle(g),g.path].join('\n').toLocaleLowerCase().includes(q);}
function memoryStatus(d){const s=d.sync||{},running=s.status==='running';$('memory-sync').disabled=running;$('memory-sync').textContent=running?T('更新中…'):s.status==='error'?T('重试更新'):T('更新记忆文档');const bad=!!d.error||s.status==='error';$('memory-note').classList.toggle('memory-error',bad);const at=memoryData?new Date(memoryData.generated_at).toLocaleString(LOCALE(),{hour12:false}):'';$('memory-note').textContent=(d.error?T(d.error):'')||(s.message?T(s.message)+(at?' · '+T('文档更新于 ')+at:''):at?(T('本地文档 · 更新于 ')+at+' · '+T('每 30 分钟自动同步')):T('点击“更新记忆文档”生成完整阅读文档。'));}

let memoryPresentation='text';try{if(localStorage.getItem('cg-memory-presentation')==='nebula')memoryPresentation='nebula'}catch(e){}
function syncMemoryNebulaVisibility(){const page=$('memory-page'),frame=$('memory-galaxy-frame'),active=memoryPresentation==='nebula'&&page.getClientRects().length>0&&page.style.display!=='none';if(active&&!frame.hasAttribute('src'))frame.src='v1/memory/galaxy-view';if(frame.contentWindow)frame.contentWindow.postMessage({type:'cg-galaxy-active',active},location.origin)}
function applyMemoryPresentation(){const nebula=memoryPresentation==='nebula';$('memory-page').classList.toggle('memory-nebula',nebula);$('memory-galaxy-frame').hidden=!nebula;document.querySelectorAll('[data-memory-presentation]').forEach(b=>{b.setAttribute('aria-pressed',String(b.dataset.memoryPresentation===memoryPresentation));const label=b.dataset.memoryPresentation==='nebula'?(LANG==='en'?'Nebula view':'星云模式'):(LANG==='en'?'Text view':'文字模式');b.title=label;b.setAttribute('aria-label',label)})}
let memorySwitchSerial=0,memorySwitchAnimations=[];
function waitMemorySwitchAnimations(animations,timeout){return new Promise(resolve=>{const timer=setTimeout(resolve,timeout);Promise.all(animations.map(a=>a.finished.catch(()=>{}))).then(()=>{clearTimeout(timer);resolve()})})}

function memoryPresentationElements(){return memoryPresentation==='nebula'?[$('memory-galaxy-frame')]:[$('memory-layout'),document.querySelector('.memory-export'),$('memory-note')].filter(Boolean)}
async function setMemoryPresentation(mode){
 if(!['text','nebula'].includes(mode))return;
 const serial=++memorySwitchSerial;memorySwitchAnimations.forEach(a=>a.cancel());memorySwitchAnimations=[];
 if(mode===memoryPresentation)return;
 const frame=$('memory-galaxy-frame');if(mode==='nebula'&&!frame.hasAttribute('src'))frame.src='v1/memory/galaxy-view';
 const reduce=matchMedia('(prefers-reduced-motion: reduce)').matches,visible=$('memory-page').getClientRects().length>0;
 if(!reduce&&visible){
  memorySwitchAnimations=memoryPresentationElements().map(el=>el.animate([{opacity:1,transform:'translateY(0)'},{opacity:0,transform:'translateY(-4px)'}],{duration:100,easing:'ease-in',fill:'both'}));
  await waitMemorySwitchAnimations(memorySwitchAnimations,220);
  if(serial!==memorySwitchSerial)return;
  memorySwitchAnimations.forEach(a=>a.cancel());memorySwitchAnimations=[];
 }
 memoryPresentation=mode;try{localStorage.setItem('cg-memory-presentation',mode)}catch(e){}
 applyMemoryPresentation();syncMemoryNebulaVisibility();if(mode==='text')loadMemory();
 if(!reduce&&visible){
  memorySwitchAnimations=memoryPresentationElements().map(el=>el.animate([{opacity:0,transform:'translateY(6px) scale(.995)'},{opacity:1,transform:'translateY(0) scale(1)'}],{duration:220,easing:'cubic-bezier(.2,.7,.2,1)',fill:'both'}));
  await waitMemorySwitchAnimations(memorySwitchAnimations,340);
  if(serial===memorySwitchSerial){memorySwitchAnimations.forEach(a=>a.cancel());memorySwitchAnimations=[];}
 }
}

document.querySelectorAll('[data-memory-presentation]').forEach(b=>b.onclick=()=>setMemoryPresentation(b.dataset.memoryPresentation));$('memory-galaxy-frame').onload=syncMemoryNebulaVisibility;new MutationObserver(syncMemoryNebulaVisibility).observe($('memory-page'),{attributes:true,attributeFilter:['style','hidden']});applyMemoryPresentation();

async function loadMemory(force=false){
  applyMemoryPresentation();
  if(memoryPresentation==='nebula'){
    syncMemoryNebulaVisibility();
    if(!force)return true;
    const galaxy=$('memory-galaxy-frame').contentWindow;
    if(typeof galaxy?.load!=='function')return null;
    galaxy.load();
    return null;
  }
  if(memoryLoading){
    if(!force)return memoryLoading;
    await memoryLoading;
  }
  const request=readMemoryCatalog(force);
  memoryLoading=request;
  try{return await request;}
  finally{if(memoryLoading===request)memoryLoading=null;}
}
async function readMemoryCatalog(force){try{const d=await centerApi('memory'+(memoryStamp&&!force?'?since='+encodeURIComponent(memoryStamp):''));if(d.catalog){memoryData=d.catalog;memoryStamp=d.generated_at;renderMemory();}else if(!memoryData){renderMemory();if(d.error){$('memory-reader').replaceChildren();}}memoryStatus(d);return !d.error && d.sync?.status!=='error';}catch(e){$('memory-note').textContent=T('读取记忆失败：')+e.message+T('。请重试刷新。');$('memory-note').classList.add('memory-error');return false;}}

function memoryEntry(e,g,full){let h='<article class="card memory-entry"><div class="muted" style="font-size:12px;margin-bottom:8px">'+esc(memoryGroupTitle(g))+'</div><h4>'+esc(e.title)+'</h4>';if(full){let chips='<span class="mstat">'+T('权重 ')+'<b>'+Number(e.weight??0.5).toFixed(2)+'</b>'+(e.weight_pinned?T(' · 已固定'):'')+'</span>';if(e.confidence!=null){chips+='<span class="mstat">'+T('置信度 ')+'<b>'+Number(e.confidence).toFixed(2)+'</b></span>';if(e.confidence_set_at)chips+='<span class="mstat">'+T('可信程度评估于 ')+'<b>'+esc(new Date(e.confidence_set_at).toLocaleDateString(LOCALE()))+'</b></span>';if(e.confidence_valid_until)chips+='<span class="mstat">'+T('有效期至 ')+'<b>'+esc(new Date(e.confidence_valid_until).toLocaleDateString(LOCALE()))+'</b></span>';}if(e.confidence_lapsed)chips+='<span class="mstat lapsed">'+T('⚠︎ 置信度已过期，建议重新核实')+'</span>';h+='<div class="mstatbar">'+chips+'</div>';}h+='<p class="memory-text">'+esc(e.reading_text||e.value||T('这条记录没有正文，可展开查看原始记录。'))+'</p>';if(full){h+='<p class="memory-meta">'+esc(e.kind)+' · '+(LANG==='en'?('v'+num(e.version)+' · '):('第 '+num(e.version)+' 版 · '))+esc(e.recorded_at?new Date(e.recorded_at).toLocaleString(LOCALE(),{hour12:false}):T('时间待核对'))+'</p>';if(e.reading_text!==e.value)h+='<details><summary>'+T('记录中的完整正文')+'</summary><p class="memory-text">'+esc(e.value)+'</p></details>';if(e.quotes?.length)h+='<details><summary>'+T('原文依据（')+e.quotes.length+T(' 段）')+'</summary>'+e.quotes.map(q=>'<blockquote class="memory-text">'+esc(q)+'</blockquote>').join('')+'</details>';h+='<details><summary>'+T('原始记录（凭据已隐藏）')+'</summary><pre>'+esc(e.raw)+'</pre></details>';}else{h+='<button type="button" data-memory-entry="'+esc(e.id)+'" style="margin-top:16px">'+T('查看原文与依据 →')+'</button>';}return h+'</article>';}
function setMemoryMode(mode,id=''){memoryMode=mode;memorySelected=id;document.querySelectorAll('[data-memory-mode]').forEach(b=>{const on=b.dataset.memoryMode===mode;b.classList.toggle('on',on);b.setAttribute('aria-selected',String(on));});renderMemory();window.scrollTo({top:0});}
function renderMemory(){const reader=$('memory-reader');reader.style.setProperty('--memory-font',memoryFont+'px');const groups=memoryData?.groups||[];if(!memoryData){reader.innerHTML='<div class="memory-empty">'+T('还没有可读取的记忆文档。点击“更新记忆文档”生成。')+'</div>';$('memory-list').hidden=true;return;}
 const matched=groups.map(g=>({g,entries:g.entries.filter(e=>memoryMatches(e,g))})).filter(x=>x.entries.length);
 $('memory-sums').innerHTML='<span class="sum"><b>'+num(memoryData.total)+'</b>'+T('当前记忆')+'</span><span class="sum"><b>'+num(groups.length)+'</b>'+T('主题')+'</span><span class="sum"><b>'+num(memoryData.hidden)+'</b>'+T('归档或到期（原始快照保留）')+'</span>';
 const overview=memoryMode==='overview'&&!memoryQuery();$('memory-layout').classList.toggle('overview',overview);$('memory-list').hidden=overview;
 if(overview){reader.innerHTML='<h3>'+T('从一个主题开始')+'</h3><div class="memory-topic-grid">'+groups.map(g=>'<button type="button" class="card memory-topic" data-memory-group="'+esc(g.id)+'"><strong>'+esc(memoryGroupTitle(g))+'<small>'+g.entries.length+T(' 条')+'</small></strong><span class="memory-preview">'+g.entries.slice(0,3).map(e=>esc(e.title)).join(' · ')+'</span><span class="memory-arrow">'+T('阅读主题 →')+'</span></button>').join('')+'</div><p class="muted" style="font-size:12px;margin:16px 0 0">'+T('中文要点逐条整理，完整原文始终保留。主题和条目随文档同步更新。')+'</p>';return;}
 memoryRows=[];matched.forEach(({g,entries})=>{if(memoryMode==='detail')entries.slice().sort((a,b)=>((b.weight??0.5)-(a.weight??0.5))||a.title.localeCompare(b.title,LOCALE())).forEach(e=>memoryRows.push({id:e.id,g,e}));else memoryRows.push({id:g.id,g,entries});});
 if(!memoryRows.some(r=>r.id===memorySelected))memorySelected=memoryRows[0]?.id||'';
 reconcile($('memory-list'),memoryRows.map(r=>'<button type="button" data-memory-row="'+esc(r.id)+'" class="'+(r.id===memorySelected?'on':'')+'" aria-pressed="'+(r.id===memorySelected)+'" title="'+esc((r.e?r.e.title:memoryGroupTitle(r.g))+'\n'+r.g.path)+'"><span>'+esc(r.e?r.e.title:memoryGroupTitle(r.g))+'</span><small>'+esc(r.e?memoryGroupTitle(r.g):r.entries.length+Tc(r.entries.length,' 条记忆',' memory',' memories'))+'</small></button>').join(''));
 const row=memoryRows.find(r=>r.id===memorySelected);if(!row){reader.innerHTML='<div class="memory-empty"><h3>'+T('没有找到相关记忆')+'</h3><p>'+T('试试更短的关键词，或清空搜索查看全部。')+'</p></div>';return;}
 if(row.e){reader.innerHTML=memoryEntry(row.e,row.g,true);return;}
 let h='<h3>'+esc(memoryGroupTitle(row.g))+'</h3>'+(row.g.path?'<p class="memory-path">'+esc(row.g.path)+'</p>':'');
 if(memoryMode==='directory'){h+='<p class="muted" style="font-size:13px">'+T('选择一条记忆，查看完整内容。')+'</p><div class="memory-directory">'+row.entries.map(e=>'<button type="button" data-memory-entry="'+esc(e.id)+'"><span>'+esc(e.title)+'</span><small class="muted">'+esc(e.kind)+' →</small></button>').join('')+'</div>';}else{h+=row.entries.map(e=>memoryEntry(e,row.g,false)).join('');}reader.innerHTML=h;
}
$('memory-page').addEventListener('click',e=>{const mode=e.target.closest('[data-memory-mode]'),row=e.target.closest('[data-memory-row]'),entry=e.target.closest('[data-memory-entry]'),group=e.target.closest('[data-memory-group]');if(mode)setMemoryMode(mode.dataset.memoryMode);else if(row){memorySelected=row.dataset.memoryRow;renderMemory();const again=[...$('memory-list').querySelectorAll('button')].find(x=>x.dataset.memoryRow===row.dataset.memoryRow);if(again)again.focus();}else if(entry){$('memory-query').value='';setMemoryMode('detail',entry.dataset.memoryEntry);}else if(group){$('memory-query').value='';setMemoryMode('outline',group.dataset.memoryGroup);}});
$('memory-query').addEventListener('input',()=>{if(memoryMode==='overview'&&memoryQuery())setMemoryMode('detail');else renderMemory();});
$('memory-list').addEventListener('keydown',e=>{if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;const buttons=[...$('memory-list').querySelectorAll('button')];if(!buttons.length)return;let i=buttons.indexOf(document.activeElement);i=e.key==='Home'?0:e.key==='End'?buttons.length-1:Math.max(0,Math.min(buttons.length-1,i+(e.key==='ArrowDown'?1:-1)));e.preventDefault();buttons[i].focus();buttons[i].click();const fresh=[...$('memory-list').querySelectorAll('button')];if(fresh[i])fresh[i].focus();});
for(const [id,step] of [['memory-smaller',-1],['memory-larger',1]])$(id).onclick=()=>{memoryFont=Math.max(14,Math.min(22,memoryFont+step));try{localStorage.setItem('cg-memory-font',String(memoryFont));}catch(e){}$('memory-reader').style.setProperty('--memory-font',memoryFont+'px');};
$('memory-open-folder').onclick=async()=>{const b=$('memory-open-folder');b.disabled=true;try{await centerApi('memory/open-folder',{});$('memory-note').classList.remove('memory-error');$('memory-note').textContent=T('已打开文档文件夹，可查看目录、大纲和详细文档。');}catch(e){$('memory-note').classList.add('memory-error');$('memory-note').textContent=e.message;}finally{b.disabled=false;}};
document.querySelectorAll('[data-memory-export]').forEach(b=>{b.onclick=async()=>{const buttons=[...document.querySelectorAll('[data-memory-export]')],note=$('memory-export-note');buttons.forEach(x=>x.disabled=true);note.style.color='var(--muted)';note.textContent=T('正在整理完整文档…');try{const d=await centerApi('memory/export',{kind:b.dataset.memoryExport==='full'?$('memory-export-format').value:b.dataset.memoryExport});note.textContent=T('已生成 ')+d.filename+(d.opened?T('，已在访达显示。'):T('。请用“打开文档文件夹”进入“导出”查看。'));}catch(e){note.style.color='var(--bad)';note.textContent=e.message;}finally{buttons.forEach(x=>x.disabled=false);}};});
$('memory-sync').onclick=async()=>{$('memory-sync').disabled=true;$('memory-note').textContent=T('正在启动同步…');try{const s=await centerApi('memory/sync',{});memoryStatus({sync:s});await loadMemory();}catch(e){memoryStatus({sync:{status:'error',message:T('同步未能启动：')+e.message}});}};

'''

from console.memory_live import CSS as LIVE_CSS, HTML as LIVE_HTML, JS as LIVE_JS
CSS += LIVE_CSS
HTML += LIVE_HTML
JS += LIVE_JS
