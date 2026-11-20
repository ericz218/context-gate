# -*- coding: utf-8 -*-
"""Project sync view: one row per project, grouped into plain sections, one on/off switch each."""
CSS = r'''
#git-page{max-width:none}
#git-page button{font:inherit;cursor:pointer;border:1px solid var(--line);background:var(--card);color:var(--text);padding:7px 12px;border-radius:6px;font-size:13px;white-space:nowrap}
#git-page .git-context{font-size:12px;color:var(--muted);margin:0 0 10px}
#git-page .git-live{display:flex;gap:9px;align-items:center;font-size:12px;line-height:1.7;color:var(--muted);margin:0 0 14px}
#git-page .git-live-dot{width:6px;height:6px;border-radius:50%;background:var(--ok);flex-shrink:0}
#git-page .git-summary{font-size:14px;line-height:1.7;margin:0 0 14px}
#git-page .git-summary b{font-weight:600}#git-page .git-summary .bad{color:var(--bad)}
#git-page .git-search{width:100%;max-width:320px;box-sizing:border-box;height:36px;border-radius:9px;border:1px solid var(--line);background:var(--card);color:var(--text);font-size:13px;padding:0 12px;margin:0 0 16px}
#git-page .git-group{border:1px solid transparent;border-radius:8px;background:var(--chip);margin:0 0 12px;overflow:hidden}
#git-page .git-group>summary{list-style:none;display:flex;align-items:center;gap:10px;padding:14px 18px;cursor:pointer;width:auto;font-size:14px;font-weight:600;color:var(--text)}
#git-page .git-group>summary::-webkit-details-marker{display:none}
#git-page .git-group>summary::before{content:'▸';color:var(--muted);font-size:12px;transition:transform .15s}
#git-page .git-group[open]>summary::before{transform:rotate(90deg)}
#git-page .git-group>summary small{font-weight:400;color:var(--muted);font-size:12px}
#git-page .git-group>summary .git-count{margin-left:auto;font-weight:400;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
#git-page .git-group.attention{border-color:var(--bad)}#git-page .git-group.attention>summary{color:var(--bad)}
#git-page .git-row{display:flex;align-items:center;gap:16px;padding:14px 18px;border-top:1px solid var(--line);flex-wrap:wrap}
#git-page .git-row.git-bad{box-shadow:inset 3px 0 var(--bad)}
#git-page .git-main{flex:1 1 220px;min-width:0}
#git-page .git-name{font-size:14px;font-weight:600;overflow-wrap:anywhere}
#git-page .git-branch{font-size:11px;font-weight:400;color:var(--muted);margin-left:8px;overflow-wrap:anywhere}
#git-page .git-state{font-size:13px;color:var(--muted);margin-top:3px;line-height:1.6;display:flex;align-items:center;gap:7px}
#git-page .git-dot{width:7px;height:7px;border-radius:50%;background:var(--muted);flex-shrink:0}
#git-page .git-state.ok .git-dot{background:var(--ok)}#git-page .git-state.bad{color:var(--bad)}#git-page .git-state.bad .git-dot{background:var(--bad)}#git-page .git-state.warn .git-dot{background:var(--warn)}
#git-page .git-switch{display:inline-flex;align-items:center;gap:10px;cursor:pointer;font-size:13px;flex-shrink:0;margin-left:auto;user-select:none}
#git-page .git-switch input{position:absolute;opacity:0;width:1px;height:1px}
#git-page .git-track{width:42px;height:24px;border-radius:12px;background:var(--mutbg);border:1px solid var(--line);position:relative;transition:background .15s;flex-shrink:0;box-sizing:border-box}
#git-page .git-track::after{content:'';position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:var(--text);opacity:.55;transition:transform .15s,opacity .15s}
#git-page .git-switch input:checked+.git-track{background:var(--ok);border-color:var(--ok)}
#git-page .git-switch input:checked+.git-track::after{transform:translateX(18px);opacity:1;background:#fff}
#git-page .git-switch input:focus-visible+.git-track{outline:2px solid var(--accent);outline-offset:2px}
#git-page .git-switch.off{cursor:not-allowed;color:var(--muted)}#git-page .git-switch.off .git-track{opacity:.4}
#git-page .git-switch-label{min-width:52px;color:var(--muted)}
#git-page .git-extra{flex-basis:100%;min-width:0}
#git-page .git-help{border:1px solid var(--line);border-radius:8px;padding:12px 14px;font-size:13px;line-height:1.7;background:var(--card);margin-top:2px}
#git-page .git-help ol{margin:4px 0 0;padding-left:20px}
#git-page .git-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
#git-page .git-row details{margin-top:8px;color:var(--muted);font-size:12px;line-height:1.7}
#git-page .git-row summary{cursor:pointer;width:fit-content}
#git-page .git-details{padding-top:6px;overflow-wrap:anywhere;white-space:pre-wrap;font-size:12px}
#git-page .git-hint{font-size:12px;color:var(--muted);padding:0 18px 12px;margin:-6px 0 0;line-height:1.6}
#git-page .git-empty{padding:24px;text-align:center;font-size:12px;line-height:1.8;color:var(--muted);border-radius:8px;background:var(--chip)}
#git-page .git-note{display:none;margin:0 0 14px;padding:12px 15px;border-radius:10px;background:var(--badbg);color:var(--bad);font-size:12px;line-height:1.7}
#git-page .git-note.show{display:block}
#git-page .git-footer{font-size:12px;line-height:1.8;color:var(--muted);margin:14px 0}
#git-page .git-history>summary{list-style:none;display:flex;align-items:center;gap:10px;font-size:14px;font-weight:600;color:var(--text);cursor:pointer;margin:0 0 8px}
#git-page .git-history>summary::-webkit-details-marker{display:none}
#git-page .git-history>summary::before{content:'▸';color:var(--muted);font-size:12px;transition:transform .15s}
#git-page .git-history[open]>summary::before{transform:rotate(90deg)}
#git-page .git-ev{display:grid;grid-template-columns:1fr auto;gap:12px;padding:10px 0;border-top:1px solid var(--line);font-size:13px;line-height:1.6}
#git-page .git-msg{color:var(--muted);font-size:12px}
#git-page .git-event-time{font-size:12px;color:var(--muted);white-space:nowrap}
@media(max-width:760px){#git-page .git-row{padding:12px 14px;gap:10px}#git-page .git-group>summary{padding:13px 14px}#git-page .git-hint{padding:0 14px 10px}#git-page .git-search{max-width:none}#git-page .git-switch-label{min-width:0;font-size:12px}#git-page .git-main{flex:1 1 0}#git-page .git-switch{gap:6px}#git-page .git-ev{grid-template-columns:1fr}}
'''
HTML = r'''
<section data-view="git" id="git-page" style="display:none">
<div class="git-context">GitHub · <span id="git-device">这台电脑</span></div>
<div id="git-note" class="git-note" role="status" aria-live="polite"></div>
<div class="git-live" id="git-live-state"></div>
<div class="git-summary" id="git-summary"></div>
<input id="git-repo" class="git-search" type="search" placeholder="找一个项目…" aria-label="搜索项目">
<div id="git-repos"></div>
<p class="git-footer">打开开关后，每 5 分钟自动检查一次：你在这台电脑改的内容会保存到 GitHub，GitHub 上的新内容也会取回来。没有变化就什么都不做。</p>
<details class="git-history"><summary>最近发生了什么</summary><div id="git-events"></div></details>
</section>
'''
EN = {'项目同步':'Project sync','刷新状态':'Refresh status','我的项目':'My projects','正在同步':'Syncing','已加入同步':'Included in sync','需要处理':'Needs attention','所有项目':'All projects','已暂停':'Paused','尚未开启':'Not enabled','找一个项目…':'Find a project…','最近发生了什么':'Recent activity','上传到 GitHub':'Upload to GitHub','从 GitHub 更新':'Update from GitHub','上传/push':'Upload / push','下载/pull':'Download / pull','查看详细信息':'View details','查看原始记录':'View original record','已保持一致':'Up to date','这台电脑':'This computer'}
JS = r'''
let gitData=null,gitBusy=false,gitSeq=0;const gitOpen={attention:true,mine:true};
function gitNote(text){const el=$('git-note');if(!el)return;el.textContent=text||'';el.classList.toggle('show',!!text);}
function gitTime(v,empty='还没有同步记录'){return v?new Date(v).toLocaleString(LOCALE(),{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):T(empty);}
function gitAgo(v){if(!v)return '';const m=Math.round((Date.now()-new Date(v).getTime())/60000);if(!(m>=0))return gitTime(v);if(m<1)return T('刚刚');if(m<60)return m+' '+T('分钟前');if(m<1440)return Math.round(m/60)+' '+T('小时前');return Math.round(m/1440)+' '+T('天前');}
function gitFriendly(raw){const s=String(raw||'');
 if(/路径不存在|外接卷/i.test(s))return T('找不到登记的位置。项目可能已移动，或所在硬盘未连接。');
 if(/Authentication|Username|publickey|凭据|鉴权|认证|403|401/i.test(s))return T('尚未连接 GitHub，当前无法上传或取回更新。');
 if(/gitleaks|疑似密钥/i.test(s))return T('发现可能含有密码的文件，已暂停上传。');
 if(/index.lock|正在.*合并|60 秒|最近.*改动/i.test(s))return T('项目正在被修改，下一轮再检查。');
 if(/分支.*不一致|当前分支|检出分支/i.test(s))return T('当前打开的工作版本与自动同步设置不同，需要核对。');
 if(/network|timed out|Could not resolve|Failed to connect|连接.*失败/i.test(s))return T('暂时连接不上 GitHub，稍后会重试。');
 return T('自动同步需要处理，请展开详情查看原因。');}
// 分组：没连 GitHub → 备份副本（外接盘或 --2 结尾）→ 别人的项目（3p-）→ 我的项目
function gitGroup(r){if(r.has_remote===false)return 'noremote';if(r.on_volume||/^\/Volumes\//.test(r.path||'')||/--\d+$/.test(r.name))return 'backup';if(/^3p-/.test(r.name))return 'others';return 'mine';}
function gitIsBad(r){const reason=r.status_reason||r.last_result||'';return r.status!=='disabled'&&(r.is_error||r.status==='conflict'||/路径不存在|外接卷/.test(reason));}
async function loadGit(force=false){if(gitBusy)return null;gitBusy=true;const seq=++gitSeq;
 try{const d=await centerApi('git-sync?'+new URLSearchParams({limit:'200'}).toString());if(seq!==gitSeq)return;gitData=d;gitNote('');renderGit();return true;}
 catch(e){if(seq===gitSeq)gitNote(T('刷新失败，保留上次结果：')+e.message);return false;}finally{if(seq===gitSeq)gitBusy=false;}}
function gitRow(r){const reason=(r.status_reason||r.last_result||'').trim(),bad=gitIsBad(r),h=r.help,canToggle=r.has_remote!==false,on=r.status!=='disabled'&&canToggle;
 const pending=!bad&&on&&(r.pending_changes>0||/未提交改动/.test(reason));
 const st=bad?['bad',r.status==='conflict'?T('出问题了 · 两边改到了同一处'):T('出问题了')]:!canToggle?['',T('没连 GitHub，无法同步')]:r.status==='paused'?['warn',T('已暂停')]:!on?['',T('未开启')]:pending?['warn',T('有新修改，提交后会自动保存到 GitHub')]:['ok',T('已同步')+((r.last_check||r.last_sync)?' · '+gitAgo(r.last_check||r.last_sync):'')];
 const sw='<label class="git-switch'+(canToggle?'':' off')+'"'+(canToggle?'':' title="'+esc(T('没连接 GitHub'))+'"')+'><span class="git-switch-label">'+T(on?'自动同步 开':'自动同步 关')+'</span><input type="checkbox" role="switch" data-git-toggle="'+esc(r.name)+'"'+(on?' checked':'')+(canToggle?'':' disabled')+' aria-label="'+esc(T('自动同步')+' '+r.name)+'"><span class="git-track"></span></label>';
 const names={retry:'重试',pause:'暂停',resume:'恢复',resolve:'标记已解决',reveal:'打开文件夹',locate:'重新定位'};
 let extra='';
 if(bad||r.status==='paused'){const acts=h?(h.actions||[]).slice():[];if(r.status==='paused')acts.push('resume');
  const buttons=[...new Set(acts)].filter(a=>a!=='pause'||r.status!=='paused').map(a=>a==='locate'?'<button type="button" data-git-locate="'+esc(r.name)+'">'+T('重新定位')+'</button>':'<button type="button" data-git-act="'+a+'" data-git-name="'+esc(r.name)+'">'+T(names[a])+'</button>').join('');
  const why=h?esc(T(h.reason)):esc(bad?(r.status==='conflict'?T('两边改到了同一处，已保留双方内容，等待合并。'):gitFriendly(reason)):T('自动同步已暂停'));
  extra+='<div class="git-help"><b>'+T('原因')+'：</b>'+why+(h&&(h.fix||[]).length?'<br><b>'+T('怎么办')+'：</b><ol>'+h.fix.map(x=>'<li>'+esc(T(x))+'</li>').join('')+'</ol>':'')+(buttons?'<div class="git-actions">'+buttons+'</div>':'')+'</div>';}
 const dk='d:'+r.name,mode=r.mode==='pull-only'?T('只取回，不上传'):r.mode==='none'||!on?T('未开启：只取回 GitHub 上的版本信息，不改本机文件'):T('上传和取回');
 extra+='<details data-git-open="'+esc(dk)+'"'+(gitOpen[dk]?' open':'')+'><summary>'+T('详细信息')+'</summary><div class="git-details">'
  +esc(T('上传/push')+'：'+gitTime(r.last_push,'暂无上传记录'))+'<br>'+esc(T('下载/pull')+'：'+gitTime(r.last_pull,'暂无取回记录'))
  +'<br>'+esc(T('方式')+'：'+mode)+'<br>'+esc(T('当前分支')+'：'+(r.branch||'—'))+'<br>'+esc(T('最近检查')+'：'+gitTime(r.last_check||r.last_sync,'尚无检查记录'))
  +(r.path?'<br>'+esc(T('位置')+'：'+r.path):'')+(h&&h.detail?'<br>'+esc(h.detail):'')+(reason?'<br>'+esc(T('原始记录')+'：'+reason):'')+'</div></details>';
 return '<article class="git-row'+(bad?' git-bad':'')+'"><div class="git-main"><div class="git-name">'+esc(r.name)+'<span class="git-branch" title="'+esc(T('当前分支'))+'">'+esc(r.branch||'')+'</span></div><div class="git-state '+st[0]+'"><span class="git-dot"></span><span>'+esc(st[1])+'</span></div></div>'+sw+'<div class="git-extra">'+extra+'</div></article>';}
function renderGit(){const d=gitData;if(!d)return;const s=d.summary||{};$('git-device').textContent=d.device||T('这台电脑');
 const live=d.data_sync||{},liveEl=$('git-live-state');if(liveEl){if(live.at){const liveOk=live.state==='ok'&&Date.now()/1000-(live.at||0)<20;if(liveEl.style)liveEl.style.display='';reconcile(liveEl,'<span class="git-live-dot"'+(liveOk?'':' style="background:var(--muted)"')+'></span><span>'+T(liveOk?'多设备数据共享已连接':'多设备数据共享暂未连通，连接后会自动补齐')+'</span>');}else{if(liveEl.style)liveEl.style.display='none';liveEl.textContent='';}}
 const repos=(d.repos||[]).slice().sort((a,b)=>a.name.localeCompare(b.name)),search=($('git-repo')?.value||'').trim().toLowerCase();
 const onCount=repos.filter(r=>r.status!=='disabled'&&r.has_remote!==false).length,badCount=repos.filter(gitIsBad).length;
 reconcile($('git-summary'),'<b>'+num(onCount)+'</b> '+T('个项目在自动同步')+(badCount?' · <b class="bad">'+num(badCount)+' '+T('个需要处理')+'</b>':' · '+T('都正常'))+(s.last_round?' · '+T('最近检查')+' '+esc(gitAgo(s.last_round)):''));
 const shown=repos.filter(r=>!search||r.name.toLowerCase().includes(search));
 const groups=[['attention','需要处理','',shown.filter(gitIsBad)],['mine','我的项目','',shown.filter(r=>!gitIsBad(r)&&gitGroup(r)==='mine')],['others','别人的项目（只下载）','别人公开的项目，一般不用开自动同步',shown.filter(r=>!gitIsBad(r)&&gitGroup(r)==='others')],['backup','备份副本','外接硬盘或重复的拷贝，一般不用开自动同步',shown.filter(r=>!gitIsBad(r)&&gitGroup(r)==='backup')],['noremote','没连 GitHub','这些文件夹还没有对应的 GitHub 项目',shown.filter(r=>!gitIsBad(r)&&gitGroup(r)==='noremote')]];
 reconcile($('git-repos'),groups.filter(g=>g[3].length).map(([k,title,hint,list])=>'<details class="git-group'+(k==='attention'?' attention':'')+'" data-git-open="'+k+'"'+(gitOpen[k]||search?' open':'')+'><summary>'+T(title)+'<span class="git-count">'+num(list.length)+'</span></summary>'+(hint?'<p class="git-hint">'+T(hint)+'</p>':'')+list.map(gitRow).join('')+'</details>').join('')
  ||'<div class="git-empty">'+T(repos.length?'没有符合条件的项目。':'还没有项目加入同步。')+'</div>');
 const all=d.activity||d.events||[];
 const events=all.filter(e=>e.repo&&!['info','skip'].includes(e.kind)&&!/^结果：/.test(e.message||'')&&(!search||String(e.repo).toLowerCase().includes(search))).slice(0,30);
 const labels={push:'已保存到 GitHub',pull:'已取回 GitHub 上的新内容',merge:'已合并两边修改',commit:'已在这台电脑保存，等待上传',resolved:'已恢复正常',warning:'需要留意',conflict:'出问题了',blocked:'出问题了',error:'出问题了'};
 reconcile($('git-events'),events.map(e=>{const bad=['error','blocked','conflict'].includes(e.kind);
  return '<div class="git-ev"><div><b>'+esc(e.repo)+'</b> · '+esc(T(labels[e.kind]||'需要留意'))+(bad?'<div class="git-msg">'+esc(gitFriendly(e.message))+'</div>':'')+'</div><time class="git-event-time">'+esc(gitTime(e.at))+'</time></div>';
 }).join('')||'<div class="git-empty">'+T('最近没有文件传输。没有改动时不会重复上传或下载。')+'</div>');}
$('git-page')?.addEventListener('toggle',e=>{const k=e.target.dataset&&e.target.dataset.gitOpen;if(k)gitOpen[k]=e.target.open;},true);
$('git-repos')?.addEventListener('change',async e=>{const c=e.target.closest('[data-git-toggle]');if(!c)return;c.disabled=true;try{const d=await centerApi('git-sync/toggle',{name:c.dataset.gitToggle,on:c.checked});gitNote(T(d.message||''));await loadGit(true);}catch(err){c.checked=!c.checked;gitNote(err.message);}finally{c.disabled=false;}});
$('git-repos')?.addEventListener('click',async e=>{const a=e.target.closest('[data-git-act]');if(!a)return;a.disabled=true;try{const d=await centerApi('git-sync/'+a.dataset.gitAct,{name:a.dataset.gitName});gitNote(T(d.message||''));if(a.dataset.gitAct==='retry')setTimeout(()=>loadGit(true),60000);await loadGit(true);}catch(err){gitNote(err.message);}finally{a.disabled=false;}});
$('git-repos')?.addEventListener('click',async e=>{const b=e.target.closest('[data-git-locate]');if(!b)return;b.disabled=true;try{const chosen=await centerApi('center/pick-root',{});if(!chosen.path)return;await centerApi('git-sync/locate',{name:b.dataset.gitLocate,path:chosen.path});await loadGit(true);}catch(err){gitNote(err.message);}finally{b.disabled=false;}});
$('git-repo')?.addEventListener('input',()=>renderGit());
'''
EN.update({'自动同步 开':'Auto sync on','自动同步 关':'Auto sync off','自动同步':'Auto sync','已同步':'Synced','未开启':'Off','出问题了':'Problem','出问题了 · 两边改到了同一处':'Problem · both sides changed the same place',
 '没连 GitHub，无法同步':'Not on GitHub, cannot sync','有新修改，提交后会自动保存到 GitHub':'New edits; saved to GitHub after you commit','刚刚':'just now','分钟前':'min ago','小时前':'h ago','天前':'d ago',
 '原因':'Why','怎么办':'What to do','详细信息':'Details','方式':'Mode','只取回，不上传':'Download only','上传和取回':'Upload and download','位置':'Location','原始记录':'Raw record','最近检查':'Last check',
 '个项目在自动同步':'projects auto-syncing','个需要处理':'need attention','都正常':'all fine',
 '别人的项目（只下载）':"Others' projects (download only)",'备份副本':'Backup copies','没连 GitHub':'Not on GitHub',
 '别人公开的项目，一般不用开自动同步':"Other people's public projects; usually no need to auto sync",'外接硬盘或重复的拷贝，一般不用开自动同步':'Copies on external drives or duplicates; usually no need to auto sync','这些文件夹还没有对应的 GitHub 项目':'These folders have no GitHub project yet',
 '已保存到 GitHub':'Saved to GitHub','已取回 GitHub 上的新内容':'Fetched new content from GitHub','已恢复正常':'Back to normal','打开开关后，每 5 分钟自动检查一次：你在这台电脑改的内容会保存到 GitHub，GitHub 上的新内容也会取回来。没有变化就什么都不做。':'With the switch on, it checks every 5 minutes: edits on this computer are saved to GitHub and new content on GitHub is brought back. Nothing happens if nothing changed.'})

EN.update({
 '同步':'Sync','没连接 GitHub':'Not connected to GitHub','未开启：只取回 GitHub 上的版本信息，不改本机文件':'Off: only fetches version info from GitHub; local files are not changed',
 '详细原因':'Why','解决办法':'How to fix','冲突分支':'Conflict branch','重试':'Retry','暂停':'Pause','恢复':'Resume','标记已解决':'Mark resolved','打开文件夹':'Open folder','重新定位':'Relocate','当前分支':'Current branch',
 '待上传的文件里像是有密码或密钥，为了安全没有上传。':'Files waiting to upload look like they contain a password or key, so nothing was uploaded.',
 '点“打开文件夹”，找到下面列出的文件':'Click "Open folder" and find the files listed below','删掉里面的密码，或把这个文件加入 .gitignore':'Remove the secret, or add the file to .gitignore','点“重试”':'Click "Retry"',
 '有文件超过 90MB，GitHub 放不下，这个文件没有上传（其他文件照常同步）。':'A file is over 90MB, too big for GitHub; it was not uploaded (other files still sync).',
 '点“打开文件夹”找到这个文件':'Click "Open folder" to find the file','把它移出项目，或加入 .gitignore':'Move it out of the project, or add it to .gitignore',
 'macOS 不允许同步程序读取这个文件夹。':'macOS does not allow the sync program to read this folder.',
 '打开 系统设置 → 隐私与安全性 → 完全磁盘访问权限':'Open System Settings → Privacy & Security → Full Disk Access','打开 GitSync 的开关':'Turn on GitSync','回到这里点“重试”':'Come back and click "Retry"',
 '找不到登记的项目文件夹：项目可能被移动了，或所在硬盘没有连接。':'The registered project folder is missing: it may have moved, or its drive is not connected.',
 '如果在外接硬盘上，先接上硬盘再点“重试”':'If it is on an external drive, connect it and click "Retry"','如果项目搬了位置，点“重新定位”选新的文件夹':'If the project moved, click "Relocate" and pick the new folder',
 'GitHub 拒绝了登录，这台电脑现在没法上传或取回。':'GitHub rejected the sign-in, so this computer cannot upload or fetch right now.',
 '用 GitHub Desktop 或浏览器重新登录 GitHub':'Sign in to GitHub again with GitHub Desktop or the browser','确认你对这个项目有权限':'Make sure you have access to this project',
 '连不上 GitHub（网络断了或很慢）。':'Cannot reach GitHub (network down or slow).','检查网络是否正常':'Check the network','稍后会自动再试，也可以点“重试”':'It retries automatically; you can also click "Retry"',
 '项目现在没有停在任何分支上（例如正在看某个旧版本），所以只取回不上传。':'The project is not on any branch (e.g. viewing an old version), so it only fetches and does not upload.',
 '在你的 Git 工具里切回一个分支（例如 main）':'Switch back to a branch (e.g. main) in your Git tool',
 '项目正被别的程序（编辑器或 Git 工具）占用，这一轮先跳过。':'The project is busy in another program (editor or Git tool); skipped this round.',
 '等那个操作结束（或关掉卡住的 Git 工具）':'Wait for that operation to finish (or close the stuck Git tool)',
 '这个项目没连接 GitHub，所以无法同步。':'This project is not connected to GitHub, so it cannot sync.',
 '在 GitHub 上建一个项目，并把它设为这个文件夹的远程仓库':'Create a repository on GitHub and set it as this folder\'s remote','刷新本页后勾选“同步”':'Refresh this page and tick "Sync"',
 '这台电脑和 GitHub 改到了同一处。两边内容都保留了，自动同步先停下等你合并。':'This computer and GitHub changed the same place. Both versions are kept; auto sync waits for you to merge.',
 '另一边的版本放在冲突分支里（见下方分支名）':'The other version is in the conflict branch (name below)','用你的 Git 工具把它合并进当前分支':'Merge it into the current branch with your Git tool','合并好后点“标记已解决”':'After merging, click "Mark resolved"',
 '自动同步遇到了问题，原始记录见下方。':'Auto sync hit a problem; the original record is below.','如果还不行，展开“详细信息”把原始记录发给维护的人':'If it still fails, open "Details" and send the record to whoever maintains it',
 '已开启同步，下一轮开始':'Sync on; starts next round','已关闭同步：只取回 GitHub 上的版本信息，不改本机文件':'Sync off: only fetches version info from GitHub; local files are not changed',
 '已开始重新同步，约 1 分钟后刷新查看结果':'Re-sync started; results in about a minute','已暂停自动同步':'Auto sync paused','已恢复自动同步，下一轮开始':'Auto sync resumed; starts next round','已标记解决，下一轮恢复同步':'Marked resolved; sync resumes next round','已在访达中打开':'Opened in Finder',
 '找不到项目文件夹，可能已移动或硬盘未连接':'Project folder not found; it may have moved or the drive is disconnected','这个项目没连接 GitHub，无法开启同步':'This project is not connected to GitHub; sync cannot be turned on',
 '请选择开启或关闭':'Choose on or off','未能更改同步设置':'Could not change the sync setting','操作未完成':'Action did not finish','未知操作':'Unknown action','请选择项目':'Choose a project',
})
