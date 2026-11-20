# -*- coding: utf-8 -*-
"""待办页 UI（独立 *_ui.py 模式，仿 git/router/quota）。

导出 CSS / HTML / JS / EN，由 console/app.py 在 PAGE 组装阶段注入。
后端见 console_todo.py（/v1/todos*）；只复用 app.py 既有前端工具
（esc / reconcile / T / num / centerApi / openModal / closeModal）。
"""

CSS = r'''
#todo-page .todo-top h2{margin:0 0 3px}
#todo-page .todo-top p{margin:0 0 14px;color:var(--muted);font-size:13px}
#todo-page .todo-note{display:none;border-radius:8px;padding:6px 10px;margin-bottom:10px;font-size:12px;background:var(--badbg);color:var(--bad)}
#todo-page .todo-note.show{display:block}
#todo-page .todo-add{display:flex;gap:8px;margin-bottom:12px}
#todo-page .todo-add input{flex:1;min-width:0}
#todo-page .todo-import{margin-bottom:14px;border:1px solid var(--line);border-radius:12px;padding:10px 14px;background:var(--card)}
#todo-page .todo-import summary{cursor:pointer;font-weight:500}
#todo-page .todo-import textarea{display:block;width:100%;box-sizing:border-box;min-height:140px;resize:vertical;margin:10px 0;font-family:ui-monospace,Menlo,monospace;font-size:13px}
#todo-page .todo-row{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
#todo-page .todo-bar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:10px}
#todo-page .todo-bar .todo-grow{flex:1;min-width:8px}
#todo-page .todo-bar input[type=search]{min-width:160px;max-width:260px}
#todo-page .todo-bar button,#todo-page .todo-row button{min-height:32px;padding:0 12px;font-size:12px}
#todo-page .todo-bar button[aria-pressed=true]{border-color:var(--accent);background:var(--accentbg);color:var(--accent)}
#todo-page .todo-list{list-style:none;margin:0;padding:0;border:1px solid var(--line);border-radius:12px;background:var(--card);overflow:hidden}
#todo-page .todo-item{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid var(--line);min-height:44px}
#todo-page .todo-item:last-child{border-bottom:0}
#todo-page .todo-item:hover{background:var(--rowhover)}
#todo-page .todo-item input[type=checkbox]{width:18px;height:18px;flex:none;margin:0;cursor:pointer;accent-color:var(--accent)}
#todo-page .todo-text{flex:1;min-width:0;overflow-wrap:anywhere;line-height:1.45}
#todo-page .todo-item.done .todo-text{text-decoration:line-through;color:var(--muted)}
#todo-page .todo-item.picked{background:var(--accentbg)}
#todo-page .todo-edit{flex:1;min-width:0}
#todo-page .todo-ico{border:0;background:transparent;color:var(--muted);min-width:32px;min-height:32px;padding:0;border-radius:6px;font-size:14px;line-height:1}
#todo-page .todo-ico:hover{color:var(--text);background:var(--rowhover)}
#todo-page .todo-empty{color:var(--muted);text-align:center;padding:22px 0;list-style:none}
@media(pointer:coarse){#todo-page .todo-ico{min-width:44px;min-height:44px}}
#todo-page .todo-top{display:flex;align-items:flex-start;gap:12px}#todo-page .todo-top>div{flex:1;min-width:0}
#todo-page .todo-top button{min-height:32px;padding:0 12px;font-size:12px;flex:none}
/* 原生浮窗（?mini=todo）：只留添加、筛选和列表，其余在完整控制台里做 */
body.todo-mini #sidenav,body.todo-mini main>header,body.todo-mini #banner,body.todo-mini #filterchip,body.todo-mini .skip-link{display:none!important}
body.todo-mini main{margin-left:0;padding:10px 12px 14px}
body.todo-mini #todo-page{border:0;background:none;box-shadow:none;padding:0;backdrop-filter:none;-webkit-backdrop-filter:none}
body.todo-mini #todo-page .todo-top,body.todo-mini #todo-import-box,body.todo-mini #todo-export,body.todo-mini #todo-search,body.todo-mini #todo-bar-select{display:none}
body.todo-mini #todo-page .todo-item{padding:7px 10px;min-height:36px}
body.todo-mini #todo-page .todo-list{border-radius:10px}
'''

HTML = r'''
<section data-view="todo" id="todo-page" style="display:none">
<div class="todo-top"><button id="todo-float" type="button" hidden title="在屏幕右上角显示或隐藏待办小窗">浮窗</button></div>
<div id="todo-note" class="todo-note" role="status" aria-live="polite"></div>
<form id="todo-add-form" class="todo-add"><input id="todo-new" type="text" maxlength="500" placeholder="添加一条待办，回车保存" aria-label="新待办" autocomplete="off"><button type="submit">添加</button></form>
<details id="todo-import-box" class="todo-import"><summary>批量导入</summary>
<p class="muted">每行一条。可直接粘贴 Markdown 清单（- [ ] / - [x]）、编号或圆点列表、todo.txt（x 日期开头为已完成）和 ~~划线~~ 文字；已划线或已勾选的导入后即为已完成，重复内容自动跳过。</p>
<textarea id="todo-import-text" aria-label="批量导入内容" placeholder="- [ ] 整理项目资料&#10;- [x] 完成本周计划&#10;1. 测试新版应用"></textarea>
<div class="todo-row"><button id="todo-file-pick" type="button">从文件读取</button><input id="todo-file" type="file" accept=".txt,.md,.markdown,.csv" hidden><button id="todo-import-go" type="button">导入</button><span id="todo-import-note" class="muted" role="status"></span></div>
</details>
<div class="todo-bar">
<span role="group" aria-label="筛选"><button type="button" data-todo-filter="all" aria-pressed="true">全部</button> <button type="button" data-todo-filter="open" aria-pressed="false">未完成</button> <button type="button" data-todo-filter="done" aria-pressed="false">已完成</button></span>
<input id="todo-search" type="search" placeholder="搜索待办…" aria-label="搜索待办" autocomplete="off">
<span id="todo-count" class="muted"></span><span class="todo-grow"></span>
<span class="todo-row"><button id="todo-export" type="button">导出</button><button id="todo-clear-done" type="button">清除已完成</button></span>
</div>
<div class="todo-bar" id="todo-bar-select">
<button id="todo-select-toggle" type="button" aria-pressed="false">多选</button>
<span id="todo-batch" class="todo-row" hidden><button id="todo-select-all" type="button">全选</button><button id="todo-batch-done" type="button" disabled>标为完成</button><button id="todo-batch-undo" type="button" disabled>取消完成</button><button id="todo-batch-delete" type="button" disabled>删除所选</button></span>
</div>
<ul id="todo-list" class="todo-list" aria-label="待办列表"></ul>
</section>
'''

EN = {
    '待办': 'To-do',
    '浮窗': 'Float',
    '在屏幕右上角显示或隐藏待办小窗': 'Show or hide the floating to-do window at the top right of the screen',
    '记下要做的事，做完划线；支持批量导入。': 'Jot down what needs doing, strike it through when done; supports bulk import.',
    '新待办': 'New to-do',
    '添加一条待办，回车保存': 'Add a to-do, press Enter to save',
    '添加': 'Add',
    '批量导入': 'Bulk import',
    '每行一条。可直接粘贴 Markdown 清单（- [ ] / - [x]）、编号或圆点列表、todo.txt（x 日期开头为已完成）和 ~~划线~~ 文字；已划线或已勾选的导入后即为已完成，重复内容自动跳过。': 'One per line. Paste a Markdown task list (- [ ] / - [x]), numbered or bulleted list, todo.txt (a leading “x date” means done) or ~~struck~~ text; struck or ticked lines import as done and duplicates are skipped.',
    '批量导入内容': 'Bulk import content',
    '从文件读取': 'Read from file',
    '导入': 'Import',
    '筛选': 'Filter',
    '全部': 'All',
    '未完成': 'Open',
    '已完成': 'Done',
    '搜索待办…': 'Search to-dos…',
    '搜索待办': 'Search to-dos',
    '导出': 'Export',
    '清除已完成': 'Clear done',
    '多选': 'Select',
    '取消多选': 'Cancel select',
    '全选': 'Select all',
    '全不选': 'Select none',
    '标为完成': 'Mark done',
    '取消完成': 'Mark open',
    '删除所选': 'Delete selected',
    '待办列表': 'To-do list',
    '标记完成': 'Mark done',
    '选择此条': 'Select this item',
    '编辑': 'Edit',
    '删除': 'Delete',
    '保存': 'Save',
    '取消': 'Cancel',
    '确认删除': 'Confirm delete',
    '没有待办。': 'No to-dos.',
    '没有符合条件的待办。': 'No matching to-dos.',
    '共 ': 'Total ',
    ' 条 · 未完成 ': ' · open ',
    ' · 已完成 ': ' · done ',
    '请先粘贴要导入的内容': 'Paste something to import first',
    '正在导入…': 'Importing…',
    '导入 ': 'Imported ',
    ' 条': ' item(s)',
    '（其中 ': ' (',
    ' 条已完成）': ' done)',
    '，跳过重复 ': ', skipped duplicates ',
    '，过长未导入 ': ', too long to import ',
    '没有可导入的新内容': 'Nothing new to import',
    '文件最多200KB。': 'Files are limited to 200KB.',
    '文件需为UTF-8文字。': 'The file must be UTF-8 text.',
    '清除已完成待办': 'Clear completed to-dos',
    '将删除以下全部待办，删除后无法恢复：': 'These to-dos will be deleted and cannot be recovered:',
    '没有已完成的待办。': 'No completed to-dos.',
    '导出待办': 'Export to-dos',
    '导出为 Markdown 清单，可原样粘贴回“批量导入”。': 'A Markdown task list; paste it back into “Bulk import” as is.',
    '导出内容': 'Exported content',
    '复制': 'Copy',
    '已复制。': 'Copied.',
    '无法自动复制，内容已选中，请按 ⌘C。': 'Could not copy automatically; the text is selected, press ⌘C.',
}

JS = r'''
const todoMini=new URLSearchParams(location.search).get('mini')==='todo';if(todoMini)document.body.classList.add('todo-mini');
let todoItems=[],todoFilter='all',todoSelecting=false,todoEditing='',todoFocusEdit=false,todoLoaded=false;const todoSelected=new Set();
function todoNote(text){const el=$('todo-note');if(!el)return;if(text){el.textContent=text;el.classList.add('show');}else el.classList.remove('show');}
async function todoCall(path,body){try{const d=await centerApi(path,body);todoNote('');if(d.items){todoItems=d.items;todoRender();}return d;}catch(e){todoNote(e.message);return null;}}
async function loadTodo(){if(todoEditing||$('modal').open)return null;const d=await todoCall('todos');if(d)todoLoaded=true;return !!d;}
function todoVisible(){const q=$('todo-search').value.trim().toLowerCase();return todoItems.filter(x=>(todoFilter==='all'||(todoFilter==='done')===!!x.done)&&(!q||x.text.toLowerCase().includes(q)));}
function todoRow(x){
 const pick=todoSelecting?'<input type="checkbox" data-todo-pick="'+x.id+'"'+(todoSelected.has(x.id)?' checked':'')+' aria-label="'+esc(T('选择此条'))+'">':'';
 const check='<input type="checkbox" data-todo-done="'+x.id+'"'+(x.done?' checked':'')+' aria-label="'+esc(T('标记完成'))+'">';
 if(todoEditing===x.id)return '<li data-k="'+x.id+'" class="todo-item">'+pick+check+'<input class="todo-edit" data-todo-edit-input="'+x.id+'" maxlength="500" value="'+esc(x.text)+'" aria-label="'+esc(T('编辑'))+'"><button type="button" data-todo-save="'+x.id+'">'+T('保存')+'</button><button type="button" data-todo-cancel="1">'+T('取消')+'</button></li>';
 return '<li data-k="'+x.id+'" class="todo-item'+(x.done?' done':'')+(todoSelected.has(x.id)?' picked':'')+'">'+pick+check+'<span class="todo-text" data-todo-text="'+x.id+'">'+esc(x.text)+'</span><button type="button" class="todo-ico" data-todo-edit="'+x.id+'" aria-label="'+esc(T('编辑'))+'" title="'+esc(T('编辑'))+'">✎</button><button type="button" class="todo-ico" data-todo-del="'+x.id+'" aria-label="'+esc(T('删除'))+'" title="'+esc(T('删除'))+'">✕</button></li>';
}
function todoRender(){
 for(const id of [...todoSelected])if(!todoItems.some(x=>x.id===id))todoSelected.delete(id);
 if(!todoItems.length)todoSelecting=false;
 const rows=todoVisible(),open=todoItems.filter(x=>!x.done).length;
 $('todo-count').textContent=T('共 ')+todoItems.length+T(' 条 · 未完成 ')+open+T(' · 已完成 ')+(todoItems.length-open);
 document.querySelectorAll('[data-todo-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.todoFilter===todoFilter)));
 $('todo-select-toggle').hidden=!todoItems.length;$('todo-select-toggle').setAttribute('aria-pressed',String(todoSelecting));$('todo-select-toggle').textContent=T(todoSelecting?'取消多选':'多选');
 $('todo-batch').hidden=!todoSelecting;
 if(todoSelecting){const all=rows.length&&rows.every(x=>todoSelected.has(x.id));$('todo-select-all').textContent=T(all?'全不选':'全选');for(const id of ['todo-batch-done','todo-batch-undo','todo-batch-delete'])$(id).disabled=!todoSelected.size;$('todo-batch-delete').textContent=T('删除所选')+(todoSelected.size?' ('+todoSelected.size+')':'');}
 $('todo-clear-done').disabled=!todoItems.some(x=>x.done);
 reconcile($('todo-list'),rows.map(todoRow).join('')||'<li class="todo-empty">'+T(todoItems.length?'没有符合条件的待办。':'没有待办。')+'</li>');
 if(todoFocusEdit){const el=document.querySelector('[data-todo-edit-input]');if(el){el.focus();el.setSelectionRange(el.value.length,el.value.length);}todoFocusEdit=false;}
}
function todoStartEdit(id){todoEditing=id;todoFocusEdit=true;todoRender();}
async function todoSaveEdit(id){const el=document.querySelector('[data-todo-edit-input="'+id+'"]');if(!el)return;const d=await todoCall('todos/edit',{id,text:el.value});if(d){todoEditing='';todoRender();}}
function todoConfirm(title,names,action){openModal(T(title),'<p>'+T('将删除以下全部待办，删除后无法恢复：')+'</p><ul>'+names.slice(0,20).map(n=>'<li>'+esc(n)+'</li>').join('')+(names.length>20?'<li class="muted">… +'+(names.length-20)+'</li>':'')+'</ul><div class="todo-row"><button type="button" data-todo-do="">'+T('取消')+'</button><button type="button" data-todo-do="'+esc(action)+'">'+T('确认删除')+(names.length>1?' ('+names.length+')':'')+'</button></div>');}
$('todo-add-form').onsubmit=async e=>{e.preventDefault();const input=$('todo-new');if(!input.value.trim())return;const d=await todoCall('todos/add',{text:input.value});if(d){input.value='';todoFilter=todoFilter==='done'?'all':todoFilter;todoRender();}input.focus();};
$('todo-import-go').onclick=async()=>{const text=$('todo-import-text').value;if(!text.trim()){$('todo-import-note').textContent=T('请先粘贴要导入的内容');return;}$('todo-import-note').textContent=T('正在导入…');const d=await todoCall('todos/import',{text});if(!d){$('todo-import-note').textContent='';return;}const r=d.imported;$('todo-import-note').textContent=r.added?T('导入 ')+r.added+T(' 条')+(r.done?T('（其中 ')+r.done+T(' 条已完成）'):'')+(r.duplicates?T('，跳过重复 ')+r.duplicates:'')+(r.too_long?T('，过长未导入 ')+r.too_long:''):T('没有可导入的新内容')+(r.duplicates?T('，跳过重复 ')+r.duplicates:'')+(r.too_long?T('，过长未导入 ')+r.too_long:'');if(r.added)$('todo-import-text').value='';};
$('todo-file-pick').onclick=()=>$('todo-file').click();
$('todo-file').onchange=async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;if(file.size>200000){$('todo-import-note').textContent=T('文件最多200KB。');return;}try{const text=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());const box=$('todo-import-text');box.value=(box.value&&!box.value.endsWith('\n')?box.value+'\n':box.value)+text;$('todo-import-note').textContent='';}catch(err){$('todo-import-note').textContent=T('文件需为UTF-8文字。');}};
document.querySelectorAll('[data-todo-filter]').forEach(b=>b.onclick=()=>{todoFilter=b.dataset.todoFilter;todoRender();});
$('todo-search').oninput=()=>todoRender();
$('todo-select-toggle').onclick=()=>{todoSelecting=!todoSelecting;todoSelected.clear();todoRender();};
$('todo-select-all').onclick=()=>{const rows=todoVisible(),all=rows.length&&rows.every(x=>todoSelected.has(x.id));for(const x of rows)all?todoSelected.delete(x.id):todoSelected.add(x.id);todoRender();};
$('todo-batch-done').onclick=()=>todoCall('todos/done',{ids:[...todoSelected],done:true});
$('todo-batch-undo').onclick=()=>todoCall('todos/done',{ids:[...todoSelected],done:false});
$('todo-batch-delete').onclick=()=>todoConfirm('删除所选',todoItems.filter(x=>todoSelected.has(x.id)).map(x=>x.text),'delete:'+[...todoSelected].join(','));
$('todo-clear-done').onclick=()=>{const done=todoItems.filter(x=>x.done);if(!done.length){todoNote(T('没有已完成的待办。'));return;}todoConfirm('清除已完成待办',done.map(x=>x.text),'clear');};
$('todo-export').onclick=async()=>{const d=await todoCall('todos/export');if(!d)return;openModal(T('导出待办'),'<p class="muted">'+T('导出为 Markdown 清单，可原样粘贴回“批量导入”。')+'</p><textarea id="todo-export-text" rows="14" readonly aria-label="'+esc(T('导出内容'))+'" style="width:100%;box-sizing:border-box"></textarea><div class="todo-row"><button type="button" id="todo-export-copy">'+T('复制')+'</button><span id="todo-export-note" class="muted" role="status"></span></div>');const box=$('todo-export-text');box.value=d.markdown;box.focus();box.select();$('todo-export-copy').onclick=async()=>{box.select();try{await navigator.clipboard.writeText(d.markdown);$('todo-export-note').textContent=T('已复制。');}catch(err){$('todo-export-note').textContent=T('无法自动复制，内容已选中，请按 ⌘C。');}};};
$('modal-body').addEventListener('click',async e=>{const b=e.target.closest('[data-todo-do]');if(!b)return;const action=b.dataset.todoDo;closeModal();if(!action)return;if(action==='clear'){await todoCall('todos/clear_done',{});return;}if(action.startsWith('delete:')){const d=await todoCall('todos/delete',{ids:action.slice(7).split(',').filter(Boolean)});if(d){todoSelected.clear();todoRender();}}});
$('todo-list').addEventListener('change',e=>{const t=e.target;if(t.dataset.todoDone)return todoCall('todos/done',{ids:[t.dataset.todoDone],done:t.checked});if(t.dataset.todoPick){t.checked?todoSelected.add(t.dataset.todoPick):todoSelected.delete(t.dataset.todoPick);todoRender();}});
$('todo-list').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;if(b.dataset.todoEdit)return todoStartEdit(b.dataset.todoEdit);if(b.dataset.todoSave)return todoSaveEdit(b.dataset.todoSave);if(b.dataset.todoCancel){todoEditing='';return todoRender();}if(b.dataset.todoDel)return todoCall('todos/delete',{ids:[b.dataset.todoDel]});});
$('todo-list').addEventListener('dblclick',e=>{const s=e.target.closest('[data-todo-text]');if(s)todoStartEdit(s.dataset.todoText);});
$('todo-list').addEventListener('keydown',e=>{const t=e.target;if(!t.dataset||t.dataset.todoEditInput===undefined)return;if(e.key==='Enter'){e.preventDefault();todoSaveEdit(t.dataset.todoEditInput);}else if(e.key==='Escape'){todoEditing='';todoRender();}});
// 小窗与完整控制台各自显示同一份数据：可见时每 4 秒同步一次，正在编辑或弹窗确认时不刷新。
// 同时跟随另一个窗口切换的深浅色（两个窗口共用 localStorage，浮窗里没有主题按钮）。
setInterval(()=>{
 try{const saved=localStorage.getItem('cg-theme');if(saved&&saved!==document.documentElement.dataset.theme)setTheme(saved);}catch(e){}
 if(!document.hidden&&$('auto').checked&&curView==='todo'&&!todoEditing&&!$('modal').open)loadTodo();
},4000);
const todoShell=window.webkit&&window.webkit.messageHandlers&&window.webkit.messageHandlers.todoPanel;
if(todoShell&&!todoMini){$('todo-float').hidden=false;$('todo-float').onclick=()=>todoShell.postMessage('toggle');}
'''
