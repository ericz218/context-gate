"""Bounded, read-only live memory view. All HTTP access stays on loopback."""
import ipaddress
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from console_data import redact_text

_lock = threading.Lock()
_cached = None
_at = 0

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('redirect forbidden')

def _read(url, token=None):
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer '+token} if token else {})
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=3) as response:
        raw = response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('response too large')
    data=json.loads(raw)
    if not isinstance(data,dict):raise ValueError('invalid snapshot')
    return data

def clean(value):
    if isinstance(value,str):return redact_text(value)
    if isinstance(value,list):return [clean(x) for x in value]
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k.lower() not in ('token','api_key','password','authorization')}
    return value

def _loopback_url(url):
    if not isinstance(url, str) or not url:
        return ''
    parsed = urllib.parse.urlparse(url)
    try:
        local = parsed.hostname == 'localhost' or ipaddress.ip_address(parsed.hostname or '').is_loopback
    except ValueError:
        local = False
    return url.rstrip('/') if local and parsed.scheme in ('http', 'https') else ''


def _snapshot():
    live_url = _loopback_url(os.environ.get('MEMORY_OS_LIVE_URL', 'http://127.0.0.1:18766'))
    if live_url:
        try:
            d=_read(live_url + '/api/state')
            if not isinstance(d.get('events'),list) or not isinstance(d.get('memories'),dict):raise ValueError('not memory live')
            return clean({'mode':'live','online':bool(d.get('online')),'busy':bool(d.get('busy')),'paused':bool(d.get('paused')),
                'events':d['events'][-50:],'memories':list(d['memories'].values()),'recall':d.get('recall'),'sources':d.get('sources',{}),
                'note':'实时输入、写入、修改与召回 · 仅观察，不向聊天模型注入内容。','at':time.time()})
        except (OSError,ValueError,TypeError):pass
    try:
        mem_dir = Path(os.environ.get('MEMORY_OS_DIR') or (Path.home()/'Library/Application Support/MemoryOS')).expanduser()
        http_url = _loopback_url(os.environ.get('MEMORY_OS_HTTP_URL', ''))
        token = os.environ.get('MEMORY_OS_API_TOKEN', '')
        if not (http_url and token):
            for fname in ('client.json', 'runtime.json'):
                fp = mem_dir / fname
                if fp.is_file():
                    config = json.loads(fp.read_text())
                    http_url = http_url or _loopback_url(config.get('MEMORY_OS_HTTP_URL', 'http://127.0.0.1:18089'))
                    token = token or config.get('MEMORY_OS_API_TOKEN', '')
                    if http_url and token:
                        break
        if not (http_url and token):
            raise FileNotFoundError('optional memory service not configured')
        d=_read(http_url + '/v1/context?query=&max_bytes=262144',token)
        events=[]
        for item in d.get('recent_events',[]):
            ir=item.get('ir',{})
            events.append({'id':item.get('event_id'),'kind':'write','at':item.get('recorded_at'),
                'status':{'supersede':'已更新','create':'已记住','reinforce':'已确认','archive':'已归档'}.get(ir.get('action'),'记忆变化'),
                'source':'Memory OS','host':'共享记忆库','text':ir.get('value'),'key':ir.get('key'),'version':item.get('version')})
        return clean({'mode':'store','online':True,'busy':False,'events':list(reversed(events)),'memories':[],
            'recall':None,'sources':{},'note':'演示监听未运行；显示记忆库最近 10 条事件。此模式不记录输入或召回。','at':time.time()})
    except (OSError,ValueError,KeyError,TypeError):
        return {'mode':'offline','online':False,'events':[],'memories':[],'sources':{},'recall':None,
            'note':'未检测到可选的实时监听或 Memory OS 本地服务。如需启用请参考 docs/LOCAL_INTERFACES.md。','at':time.time()}

def snapshot():
    global _cached,_at
    with _lock:
        if _cached is None or time.monotonic()-_at>=1.5:
            _cached=_snapshot();_at=time.monotonic()
        return _cached

CSS=r'''
#memory-live-window{position:fixed;z-index:1100;right:24px;top:96px;width:440px;max-width:calc(100vw - 32px);max-height:calc(100dvh - 120px);overflow:auto;overscroll-behavior:contain;border:1px solid var(--glassline);border-radius:16px;background:var(--bg);color:var(--text);box-shadow:0 16px 56px #0005;padding:20px}
#memory-live-window[hidden]{display:none}.ml-head{display:flex;align-items:center;gap:12px;position:sticky;top:-20px;background:var(--bg);padding:12px 0;z-index:1}.ml-head h3{margin:0;font-size:16px;flex:1}.ml-head button{min-width:40px;min-height:36px}.ml-note,.ml-meta{font-size:12px;color:var(--muted)}.ml-card{padding:16px;background:var(--cardT);border:1px solid var(--glassline);border-radius:12px;margin:12px 0}.ml-value{font-size:20px;font-weight:600;margin:8px 0;overflow-wrap:anywhere}.ml-chip{color:var(--accent);font-size:12px}.ml-event{border-left:2px solid var(--glassline);padding:0 0 16px 12px;margin-top:12px}.ml-event p{margin:6px 0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}.ml-history{font-size:12px;color:var(--muted);margin-top:12px}.ml-history p{margin:4px 0}.ml-history s{opacity:.8}.ml-empty{padding:20px 0;color:var(--muted);font-size:13px}#memory-live-window summary{cursor:pointer}#memory-live-window button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}@media(max-width:600px){#memory-live-window{right:16px;top:72px;max-height:calc(100dvh - 88px)}}
'''
HTML=r'''
<section id="memory-live-window" role="dialog" aria-modal="false" aria-labelledby="memory-live-title" hidden>
<div class="ml-head"><h3 id="memory-live-title">记忆实时事件</h3><button type="button" id="memory-live-freeze" aria-pressed="false">暂停刷新</button><button type="button" id="memory-live-close" aria-label="关闭实时事件">×</button></div>
<p id="memory-live-note" class="ml-note" role="status" aria-live="polite">连接中…</p><div id="memory-live-content"></div>
</section>
'''
JS=r'''
let memoryLiveTimer=null,memoryLiveFrozen=false,memoryLiveOpen=false,memoryLiveSerial=0,memoryLiveStamp='';
function memoryLiveTime(value){const d=new Date(typeof value==='number'?value*1000:value);return isNaN(d)?'':d.toLocaleTimeString(LOCALE(),{hour12:false});}
function memoryLiveRender(d){
 $('memory-live-note').textContent=(d.busy?T('模型正在处理')+' · ':'')+T(d.note||'');
 const stamp=JSON.stringify([d.events,d.memories,d.recall,d.sources]);if(stamp===memoryLiveStamp)return;memoryLiveStamp=stamp;
 const memories=(d.memories||[]).slice().sort((a,b)=>(b.updated||0)-(a.updated||0));
 let h='';const cards=memories.map(m=>'<article class="ml-card"><span class="ml-chip">'+T('当前记忆')+' · v'+esc(m.version)+'</span><div class="ml-value">'+esc(m.value)+'</div><div class="ml-meta">'+esc(m.host||'')+' · '+esc(m.source||'')+'</div>'+((m.history||[]).length>1?'<details class="ml-history" open><summary>'+T('版本历史')+'</summary>'+m.history.slice().reverse().map((x,i)=>'<p>v'+esc(x.version)+' · '+(i?'<s>':'')+esc(x.value)+(i?'</s>':'')+'</p>').join('')+'</details>':'')+'</article>').join('');
 if(d.recall)h+='<article class="ml-card"><span class="ml-chip">'+T('独立召回')+' · '+esc(d.recall.seconds)+'s</span><p class="ml-meta">'+esc(d.recall.question)+'</p><div class="ml-value">'+esc(d.recall.answer)+'</div><p class="ml-meta">'+T('全新请求，未携带原对话')+'</p></article>';
 const recallCard=h;h='';const entries=(d.events||[]).slice(-20).reverse();h+='<h4>'+T('最近事件')+'</h4>'+(entries.length?entries.map(e=>'<article class="ml-event"><div class="ml-chip">'+esc(T(e.status||e.kind||''))+(e.seconds!=null?' · '+esc(e.seconds)+'s':'')+' <span class="ml-meta">'+esc(memoryLiveTime(e.at))+'</span></div><p>'+esc(e.text||e.question||(e.changes||[]).map(x=>x.value).join('；')||e.reason||'')+'</p><div class="ml-meta">'+esc(e.host||'')+' · '+esc(e.source||'')+(e.version?' · v'+esc(e.version):'')+'</div></article>').join(''):'<p class="ml-empty">'+T('等待下一条记忆事件…')+'</p>');
 h+=recallCard;if(memories.length)h+='<details class="ml-history"><summary>'+T('当前记忆与版本历史')+' · '+memories.length+'</summary>'+cards+'</details>';
 if(Object.keys(d.sources||{}).length)h+='<details class="ml-history"><summary>'+T('输入来源')+'</summary>'+Object.entries(d.sources).map(([host,s])=>'<p>'+esc(host)+' · '+T(Date.now()/1000-s.at<25?'已连接':'连接中断')+'</p>'+s.items.map(x=>'<p>'+esc(x.name)+' · '+T(x.status==='listening'?'监听中':x.status==='hook_required'?'待接入':x.status==='error'?'读取异常':'暂无记录')+'</p>').join('')).join('')+'</details>';
 $('memory-live-content').innerHTML=h;
}
async function memoryLivePoll(){
 clearTimeout(memoryLiveTimer);if(!memoryLiveOpen||memoryLiveFrozen)return;
 const serial=memoryLiveSerial;
 try{const d=await centerApi('memory/live');if(memoryLiveOpen&&serial===memoryLiveSerial)memoryLiveRender(d);}
 catch(e){if(memoryLiveOpen&&serial===memoryLiveSerial)$('memory-live-note').textContent=T('连接中断，正在重试…');}
 if(memoryLiveOpen&&!memoryLiveFrozen&&serial===memoryLiveSerial)memoryLiveTimer=setTimeout(memoryLivePoll,2000);
}
function closeMemoryLive(){memoryLiveOpen=false;memoryLiveSerial++;clearTimeout(memoryLiveTimer);$('memory-live-window').hidden=true;$('memory-live-open').setAttribute('aria-expanded','false');$('memory-live-open').focus();}
$('memory-live-open').onclick=()=>{if(memoryLiveOpen){$('memory-live-close').focus();return;}memoryLiveOpen=true;memoryLiveSerial++;$('memory-live-window').hidden=false;$('memory-live-open').setAttribute('aria-expanded','true');$('memory-live-close').focus();memoryLivePoll();};
$('memory-live-close').onclick=closeMemoryLive;
$('memory-live-window').addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();closeMemoryLive();}});
$('memory-live-freeze').onclick=()=>{memoryLiveFrozen=!memoryLiveFrozen;memoryLiveSerial++;clearTimeout(memoryLiveTimer);$('memory-live-freeze').textContent=T(memoryLiveFrozen?'恢复刷新':'暂停刷新');$('memory-live-freeze').setAttribute('aria-pressed',String(memoryLiveFrozen));if(!memoryLiveFrozen)memoryLivePoll();else $('memory-live-note').textContent=T('已暂停刷新；后台记忆处理继续。');};
'''
